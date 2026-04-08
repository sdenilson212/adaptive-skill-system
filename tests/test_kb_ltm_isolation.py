"""
KB / LTM 隔离回归测试

验证目标：
  1. self.kb 和 self.ltm 必须是两个独立的对象（不共享同一个 TenantIsolation 实例）
  2. 写入 KB 的数据不会出现在 LTM 搜索结果里
  3. 写入 LTM 的数据不会出现在 KB 搜索结果里
  4. 当只提供 kb_client 时，self.ltm 应为 None；反之亦然
  5. SkillComposer / SkillGenerator 接收到的是各自独立的客户端引用
"""

import pytest
from unittest.mock import MagicMock, call


# ─────────────────────────────────────────────
# Stub clients
# ─────────────────────────────────────────────

class StubKBClient:
    """最简 KB stub：记录写入、支持搜索回放"""
    def __init__(self, name="kb"):
        self.name = name
        self._docs = {}

    def save(self, doc):
        key = getattr(doc, "doc_id", None) or doc.get("doc_id", id(doc))
        self._docs[key] = doc
        return True

    def search(self, query, top_k=5, filters=None):
        # 只返回 doc_id 包含 query 子串的结果（简单匹配）
        results = []
        for doc_id, doc in self._docs.items():
            content = getattr(doc, "content", "") or doc.get("content", "")
            if query.lower() in str(content).lower():
                results.append(doc)
        return results[:top_k]

    def get(self, doc_id):
        return self._docs.get(doc_id)

    def update(self, doc_id, updates):
        if doc_id in self._docs:
            doc = self._docs[doc_id]
            if isinstance(doc, dict):
                doc.update(updates)
            return True
        return False

    def delete(self, doc_id):
        return self._docs.pop(doc_id, None) is not None


class StubLTMClient:
    """最简 LTM stub：记录写入、支持 recall 回放"""
    def __init__(self, name="ltm"):
        self.name = name
        self._memories = []

    def save(self, entry):
        self._memories.append(entry)
        return True

    def recall(self, query, max_results=10):
        results = []
        for m in self._memories:
            content = m.get("content", "") if isinstance(m, dict) else str(m)
            if query.lower() in content.lower():
                results.append(m)
        return results[:max_results]


# ─────────────────────────────────────────────
# 导入被测对象
# ─────────────────────────────────────────────

from adaptive_skill import AdaptiveSkillSystem
from adaptive_skill.multi_tenant.context import TenantIsolation


# ─────────────────────────────────────────────
# Test Group 1 — 实例独立性
# ─────────────────────────────────────────────

class TestKBLTMInstanceIsolation:
    """self.kb 和 self.ltm 必须是不同对象"""

    def test_kb_and_ltm_are_different_objects(self):
        """核心回归：两者不能是同一个 TenantIsolation 实例"""
        sys = AdaptiveSkillSystem(
            kb_client=StubKBClient(),
            ltm_client=StubLTMClient(),
        )
        assert sys.kb is not sys.ltm, (
            "self.kb 和 self.ltm 指向同一对象——KB/LTM 隔离失效！"
        )

    def test_kb_isolation_wraps_only_kb_adapter(self):
        """self.kb 的 TenantIsolation 内部 _kb 应是 kb_client，_ltm 应为 None"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)
        assert sys.kb._kb is kb
        assert sys.kb._ltm is None, (
            "KB TenantIsolation 不应持有 LTM adapter"
        )

    def test_ltm_isolation_wraps_only_ltm_adapter(self):
        """self.ltm 的 TenantIsolation 内部 _ltm 应是 ltm_client，_kb 应为 None"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)
        assert sys.ltm._ltm is ltm
        assert sys.ltm._kb is None, (
            "LTM TenantIsolation 不应持有 KB adapter"
        )

    def test_only_kb_client_provided_ltm_is_none(self):
        """只提供 kb_client 时，self.ltm 应为 None"""
        sys = AdaptiveSkillSystem(kb_client=StubKBClient())
        assert sys.ltm is None, "未提供 ltm_client 时 self.ltm 应为 None"
        assert sys.kb is not None

    def test_only_ltm_client_provided_kb_is_none(self):
        """只提供 ltm_client 时，self.kb 应为 None"""
        sys = AdaptiveSkillSystem(ltm_client=StubLTMClient())
        assert sys.kb is None, "未提供 kb_client 时 self.kb 应为 None"
        assert sys.ltm is not None

    def test_neither_client_provided_both_none(self):
        """两者均未提供时都应为 None（无 memory_dir 情况下）"""
        sys = AdaptiveSkillSystem()
        assert sys.kb is None
        assert sys.ltm is None


# ─────────────────────────────────────────────
# Test Group 2 — 数据不互通
# ─────────────────────────────────────────────

class TestKBLTMDataBleed:
    """写入 KB 的数据不能被 LTM 搜到，反之亦然"""

    def _make_kb_doc(self, doc_id: str, content: str):
        """构造一个最简 KBDocument-like 对象"""
        doc = MagicMock()
        doc.doc_id = doc_id
        doc.content = content
        doc.metadata = {}
        return doc

    def test_kb_write_not_visible_in_ltm_search(self):
        """向 KB 写入文档后，LTM recall 不应返回该文档"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)

        unique_token = "UNIQUE_KB_TOKEN_XYZ_777"
        doc = self._make_kb_doc("kb-doc-001", f"这是一段 KB 专属内容 {unique_token}")
        sys.kb.save_kb_doc(doc)

        ltm_results = sys.ltm.search_ltm(unique_token)
        assert len(ltm_results) == 0, (
            f"KB 写入的内容'{unique_token}'出现在 LTM 搜索结果中——数据串漏！"
        )

    def test_ltm_write_not_visible_in_kb_search(self):
        """向 LTM 写入记忆后，KB search 不应返回该条目"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)

        unique_token = "UNIQUE_LTM_TOKEN_ABC_888"
        sys.ltm.save_ltm(
            content=f"这是一段 LTM 专属记忆 {unique_token}",
            category="test",
            tags=["isolation-test"],
        )

        kb_results = sys.kb.search_kb(unique_token)
        assert len(kb_results) == 0, (
            f"LTM 写入的内容'{unique_token}'出现在 KB 搜索结果中——数据串漏！"
        )

    def test_kb_and_ltm_writes_are_independent(self):
        """分别向 KB 和 LTM 写入，各自只从对应存储中能检索到"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)

        kb_token = "KB_ONLY_CONTENT_111"
        ltm_token = "LTM_ONLY_CONTENT_222"

        # 向 KB 写入
        doc = self._make_kb_doc("kb-doc-002", f"KB专用 {kb_token}")
        sys.kb.save_kb_doc(doc)

        # 向 LTM 写入
        sys.ltm.save_ltm(
            content=f"LTM专用 {ltm_token}",
            category="test",
            tags=[],
        )

        # KB token 应在 KB 中可搜到，但不在 LTM 中
        kb_results = sys.kb.search_kb(kb_token)
        ltm_results = sys.ltm.search_ltm(kb_token)
        assert len(kb_results) >= 1, f"KB 写入后在 KB 中搜不到 {kb_token}"
        assert len(ltm_results) == 0, f"KB 写入的内容 {kb_token} 意外出现在 LTM"

        # LTM token 应在 LTM 中可搜到，但不在 KB 中
        ltm_results2 = sys.ltm.search_ltm(ltm_token)
        kb_results2 = sys.kb.search_kb(ltm_token)
        assert len(ltm_results2) >= 1, f"LTM 写入后在 LTM 中搜不到 {ltm_token}"
        assert len(kb_results2) == 0, f"LTM 写入的内容 {ltm_token} 意外出现在 KB"


# ─────────────────────────────────────────────
# Test Group 3 — 子模块接收正确引用
# ─────────────────────────────────────────────

class TestSubmoduleClientBinding:
    """SkillComposer / SkillGenerator 持有的客户端引用应与系统级 kb/ltm 一致"""

    def test_composer_receives_correct_clients(self):
        """SkillComposer.ltm / .kb 应分别指向 sys.ltm 和 sys.kb"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)

        if sys.skill_composer is None:
            pytest.skip("SkillComposer 未初始化，跳过子模块绑定测试")

        # composer.ltm 应是 sys.ltm（TenantIsolation 包装后的 LTM 实例）
        assert sys.skill_composer.ltm is sys.ltm, (
            "SkillComposer.ltm 应指向 sys.ltm，但当前指向其他对象"
        )
        # composer.kb 应是 sys.kb
        assert sys.skill_composer.kb is sys.kb, (
            "SkillComposer.kb 应指向 sys.kb，但当前指向其他对象"
        )

    def test_generator_receives_ltm_not_kb(self):
        """SkillGenerator 只应接受 ltm（不需要 kb）"""
        kb = StubKBClient()
        ltm = StubLTMClient()
        sys = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)

        if sys.skill_generator is None:
            pytest.skip("SkillGenerator 未初始化，跳过子模块绑定测试")

        assert sys.skill_generator.ltm is sys.ltm, (
            "SkillGenerator.ltm 应指向 sys.ltm"
        )
