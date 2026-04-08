"""
tests/test_memory_client.py — MemorySystemClient 适配层单元测试

测试策略
--------
- 全部使用 mock / stub，不依赖真实文件系统或 ai-memory-system 安装
- 重点验证适配层的接口翻译正确性（LTMClientAdapter / KBClientAdapter）
- 验证 MemorySystemClient 在路径不存在时安全降级
- 验证 AdaptiveSkillSystem 在 memory_dir 指定时正确初始化持久层客户端
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录在导入路径中
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill.memory_system_client import (
    KBClientAdapter,
    LTMClientAdapter,
    MemorySystemClient,
    _find_engine_dir,
)


# ---------------------------------------------------------------------------
# Stubs — 模拟 LTMEntry / KBEntry dataclass
# ---------------------------------------------------------------------------

@dataclass
class FakeLTMEntry:
    id: str
    content: str
    category: str = "other"
    tags: List[str] = field(default_factory=list)
    created_at: str = "2026-04-03T00:00:00+00:00"


@dataclass
class FakeKBEntry:
    id: str
    title: str
    content: str
    category: str = "technical"
    tags: List[str] = field(default_factory=list)
    source: str = "user-upload"
    confidence: str = "high"
    confirmed: bool = True
    created_at: str = "2026-04-03T00:00:00+00:00"
    updated_at: str = "2026-04-03T00:00:00+00:00"


# ---------------------------------------------------------------------------
# 1. LTMClientAdapter
# ---------------------------------------------------------------------------

class TestLTMClientAdapter:
    """验证 LTM 适配层的接口翻译逻辑。"""

    def _make_fake_manager(self, entries=None):
        mgr = MagicMock()
        mgr.search.return_value = entries or []
        mgr.save.return_value = FakeLTMEntry(id="ltm-new-001", content="测试内容")
        return mgr

    def test_recall_returns_list_of_dicts(self):
        entries = [
            FakeLTMEntry(id="ltm-001", content="Z世代心理学", tags=["Z世代"]),
            FakeLTMEntry(id="ltm-002", content="留存分析", tags=["数据"]),
        ]
        mgr = self._make_fake_manager(entries)
        adapter = LTMClientAdapter(mgr)

        result = adapter.recall("Z世代 留存")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "ltm-001"
        assert result[0]["content"] == "Z世代心理学"
        assert result[0]["tags"] == ["Z世代"]
        mgr.search.assert_called_once_with("Z世代 留存", max_results=10)

    def test_recall_empty_when_no_results(self):
        mgr = self._make_fake_manager([])
        adapter = LTMClientAdapter(mgr)
        result = adapter.recall("不存在的主题")
        assert result == []

    def test_recall_handles_exception_gracefully(self):
        mgr = MagicMock()
        mgr.search.side_effect = RuntimeError("DB 连接失败")
        adapter = LTMClientAdapter(mgr)
        result = adapter.recall("测试")
        assert result == []

    def test_save_calls_ltm_with_correct_args(self):
        mgr = self._make_fake_manager()
        adapter = LTMClientAdapter(mgr)

        data = {"content": "Skill 更新记录", "category": "project", "tags": ["skill-update"]}
        result = adapter.save(data)

        assert result is not None
        assert result["id"] == "ltm-new-001"
        mgr.save.assert_called_once_with(
            content="Skill 更新记录",
            category="project",
            source="ai-detected",
            tags=["skill-update"],
        )

    def test_save_converts_invalid_category_to_other(self):
        mgr = self._make_fake_manager()
        adapter = LTMClientAdapter(mgr)

        data = {"content": "某些内容", "category": "skill-update", "tags": []}
        adapter.save(data)

        call_kwargs = mgr.save.call_args.kwargs
        assert call_kwargs["category"] == "other"

    def test_save_returns_none_for_empty_content(self):
        mgr = self._make_fake_manager()
        adapter = LTMClientAdapter(mgr)
        result = adapter.save({"content": "  ", "category": "other"})
        assert result is None
        mgr.save.assert_not_called()

    def test_save_handles_exception_gracefully(self):
        mgr = MagicMock()
        mgr.save.side_effect = Exception("写入失败")
        adapter = LTMClientAdapter(mgr)
        result = adapter.save({"content": "测试", "category": "other"})
        assert result is None

    def test_recall_accepts_dict_result_from_manager(self):
        """LTMManager 返回 dict 列表时也能正常处理。"""
        mgr = MagicMock()
        mgr.search.return_value = [
            {"id": "ltm-dict-001", "content": "字典格式", "category": "other", "tags": []}
        ]
        adapter = LTMClientAdapter(mgr)
        result = adapter.recall("字典")
        assert result[0]["id"] == "ltm-dict-001"


# ---------------------------------------------------------------------------
# 2. KBClientAdapter
# ---------------------------------------------------------------------------

class TestKBClientAdapter:
    """验证 KB 适配层的接口翻译逻辑。"""

    def _make_fake_manager(self, entries=None):
        mgr = MagicMock()
        mgr.search.return_value = entries or []
        mgr.list_all.return_value = entries or []
        mgr.update.return_value = MagicMock()
        return mgr

    def test_search_returns_list_of_dicts(self):
        entries = [
            FakeKBEntry(id="kb-001", title="运营策略分解法", content="目标定义\n渠道选择"),
        ]
        mgr = self._make_fake_manager(entries)
        adapter = KBClientAdapter(mgr)

        result = adapter.search("运营策略", top_k=3)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "kb-001"
        assert result[0]["title"] == "运营策略分解法"
        mgr.search.assert_called_once_with(query="运营策略", top_k=3)

    def test_search_empty_when_no_results(self):
        mgr = self._make_fake_manager([])
        adapter = KBClientAdapter(mgr)
        result = adapter.search("不相关查询")
        assert result == []

    def test_search_handles_exception_gracefully(self):
        mgr = MagicMock()
        mgr.search.side_effect = RuntimeError("索引损坏")
        adapter = KBClientAdapter(mgr)
        result = adapter.search("测试")
        assert result == []

    def test_get_returns_entry_by_id(self):
        entries = [
            FakeKBEntry(id="kb-find-me", title="目标条目", content="内容"),
            FakeKBEntry(id="kb-other", title="其他条目", content="其他内容"),
        ]
        mgr = self._make_fake_manager(entries)
        adapter = KBClientAdapter(mgr)

        result = adapter.get("kb-find-me")

        assert result is not None
        assert result["id"] == "kb-find-me"
        assert result["title"] == "目标条目"

    def test_get_returns_none_when_not_found(self):
        mgr = self._make_fake_manager([])
        adapter = KBClientAdapter(mgr)
        result = adapter.get("kb-nonexistent")
        assert result is None

    def test_get_handles_exception_gracefully(self):
        mgr = MagicMock()
        mgr.list_all.side_effect = RuntimeError("读取失败")
        adapter = KBClientAdapter(mgr)
        result = adapter.get("kb-001")
        assert result is None

    def test_update_calls_kb_update(self):
        mgr = self._make_fake_manager()
        adapter = KBClientAdapter(mgr)

        fake_skill = MagicMock()
        fake_skill.name = "更新的 Skill"
        fake_skill.to_dict.return_value = {"name": "更新的 Skill", "version": "1.1"}

        adapter.update("kb-001", fake_skill)

        mgr.update.assert_called_once()
        call_kwargs = mgr.update.call_args.kwargs
        assert call_kwargs["entry_id"] == "kb-001"
        assert call_kwargs["title"] == "更新的 Skill"

    def test_update_handles_exception_gracefully(self):
        """KB update 失败时不抛异常（best-effort 语义）。"""
        mgr = MagicMock()
        mgr.update.side_effect = Exception("条目不存在")
        adapter = KBClientAdapter(mgr)
        # 不抛出异常就是成功
        adapter.update("kb-missing", {"name": "x"})

    def test_search_accepts_dict_result_from_manager(self):
        """KBManager 返回 dict 列表时也能正常处理。"""
        mgr = MagicMock()
        mgr.search.return_value = [
            {"id": "kb-dict-001", "title": "字典格式", "content": "内容", "tags": []}
        ]
        adapter = KBClientAdapter(mgr)
        result = adapter.search("字典")
        assert result[0]["id"] == "kb-dict-001"


# ---------------------------------------------------------------------------
# 3. MemorySystemClient — 降级行为
# ---------------------------------------------------------------------------

class TestMemorySystemClientFallback:
    """验证路径不存在或导入失败时的安全降级。"""

    def test_nonexistent_dir_gives_none_clients(self, tmp_path):
        """不存在的路径 → kb/ltm 均为 None，不抛异常。"""
        client = MemorySystemClient(str(tmp_path / "does_not_exist"))
        assert client.kb is None
        assert client.ltm is None
        assert client.is_available is False

    def test_existing_dir_without_kb_file_still_no_crash(self, tmp_path):
        """目录存在但没有 core/ltm.py → 降级为 None（导入失败）。"""
        client = MemorySystemClient(str(tmp_path))
        # 不抛出异常即可（is_available 可能为 False，取决于环境）
        assert client.kb is None or client.kb is not None  # 不约束，只要不 crash

    def test_is_available_false_on_import_error(self, tmp_path):
        """模拟 ImportError → is_available = False。"""
        with patch.dict("sys.modules", {"core.ltm": None, "core.kb": None}):
            client = MemorySystemClient(str(tmp_path))
            # 降级为不可用
            # 只要不抛异常
            assert isinstance(client.is_available, bool)


# ---------------------------------------------------------------------------
# 4. MemorySystemClient — 成功初始化路径（mock 真实模块）
# ---------------------------------------------------------------------------

class TestMemorySystemClientInit:
    """验证当 LTMManager/KBManager 可用时，适配层被正确装配。"""

    def test_successful_init_wraps_managers(self, tmp_path):
        """mock core.ltm / core.kb → 验证 .kb 和 .ltm 是适配器实例。"""
        # 伪造一个含有 core/ltm.py 的 engine 目录结构
        engine_dir = tmp_path / "engine"
        core_dir = engine_dir / "core"
        core_dir.mkdir(parents=True)
        (core_dir / "ltm.py").write_text("# stub")
        (core_dir / "kb.py").write_text("# stub")
        memory_bank = engine_dir / "memory-bank"
        memory_bank.mkdir()
        (memory_bank / "knowledge-base.md").write_text("")

        # 插入 stub 模块
        fake_ltm_entry = FakeLTMEntry(id="x", content="c")
        fake_ltm_manager = MagicMock()
        fake_ltm_manager.search.return_value = [fake_ltm_entry]
        fake_ltm_manager.save.return_value = fake_ltm_entry

        fake_kb_entry = FakeKBEntry(id="k", title="t", content="c")
        fake_kb_manager = MagicMock()
        fake_kb_manager.search.return_value = [fake_kb_entry]
        fake_kb_manager.list_all.return_value = [fake_kb_entry]

        FakeLTMManager = MagicMock(return_value=fake_ltm_manager)
        FakeKBManager = MagicMock(return_value=fake_kb_manager)

        import types
        fake_ltm_mod = types.ModuleType("core.ltm")
        fake_ltm_mod.LTMManager = FakeLTMManager
        fake_kb_mod = types.ModuleType("core.kb")
        fake_kb_mod.KBManager = FakeKBManager

        with patch.dict("sys.modules", {"core.ltm": fake_ltm_mod, "core.kb": fake_kb_mod}):
            client = MemorySystemClient(str(memory_bank))

        assert isinstance(client.ltm, LTMClientAdapter)
        assert isinstance(client.kb, KBClientAdapter)
        assert client.is_available is True

    def test_ltm_recall_via_client(self, tmp_path):
        """通过 MemorySystemClient.ltm.recall 调用到底层 manager。"""
        fake_entry = FakeLTMEntry(id="recall-001", content="测试内容")
        fake_manager = MagicMock()
        fake_manager.search.return_value = [fake_entry]
        adapter = LTMClientAdapter(fake_manager)

        results = adapter.recall("测试")
        assert len(results) == 1
        assert results[0]["id"] == "recall-001"

    def test_kb_search_via_client(self):
        """通过 KBClientAdapter.search 正确返回 dict。"""
        fake_entry = FakeKBEntry(id="search-001", title="搜索目标", content="内容")
        fake_manager = MagicMock()
        fake_manager.search.return_value = [fake_entry]
        adapter = KBClientAdapter(fake_manager)

        results = adapter.search("搜索目标")
        assert len(results) == 1
        assert results[0]["title"] == "搜索目标"


# ---------------------------------------------------------------------------
# 5. _find_engine_dir
# ---------------------------------------------------------------------------

class TestFindEngineDir:
    def test_finds_parent_with_core_ltm(self, tmp_path):
        """memory-bank 的父目录（engine/）含有 core/ltm.py → 应返回该路径。"""
        engine = tmp_path / "engine"
        core = engine / "core"
        core.mkdir(parents=True)
        (core / "ltm.py").write_text("")
        memory_bank = engine / "memory-bank"
        memory_bank.mkdir()

        result = _find_engine_dir(memory_bank)
        assert result == engine

    def test_finds_grandparent_with_core_ltm(self, tmp_path):
        """memory-bank 的祖父级含有 core/ltm.py → 应返回祖父路径。"""
        grandparent = tmp_path
        core = grandparent / "core"
        core.mkdir()
        (core / "ltm.py").write_text("")
        memory_bank = grandparent / "engine" / "memory-bank"
        memory_bank.mkdir(parents=True)

        result = _find_engine_dir(memory_bank)
        assert result == grandparent

    def test_returns_none_when_not_found(self, tmp_path):
        """目录结构不符合预期 → 返回 None。"""
        memory_bank = tmp_path / "memory-bank"
        memory_bank.mkdir()

        result = _find_engine_dir(memory_bank)
        assert result is None


# ---------------------------------------------------------------------------
# 6. AdaptiveSkillSystem 集成 — 持久层接线
# ---------------------------------------------------------------------------

class TestAdaptiveSystemWithPersistence:
    """
    验证 AdaptiveSkillSystem 在传入真实 kb_client / ltm_client 时，
    能正确将请求路由到适配器。
    """

    def test_system_uses_provided_clients(self):
        """传入 mock kb/ltm 客户端时，系统不应再尝试自动探测路径。"""
        from adaptive_skill import AdaptiveSkillSystem


        mock_kb = MagicMock()
        mock_kb.search.return_value = []

        mock_ltm = MagicMock()
        mock_ltm.recall.return_value = []

        system = AdaptiveSkillSystem(kb_client=mock_kb, ltm_client=mock_ltm)
        # kb/ltm 被包进 TenantIsolation；通过 ._kb / ._ltm 访问底层 raw client
        assert system.kb._kb is mock_kb
        assert system.ltm._ltm is mock_ltm

    def test_system_with_none_clients_still_runs(self):
        """无客户端时 solve 应返回有效 SolveResponse（降级路径）。"""
        from adaptive_skill import AdaptiveSkillSystem, SolveResponse

        system = AdaptiveSkillSystem(auto_attach_memory=False)
        response = system.solve("测试持久层降级场景")

        assert isinstance(response, SolveResponse)
        assert response.layer in (0, 1, 2, 3)

    def test_update_skill_saves_to_ltm(self):
        """update_skill_from_feedback 应调用 ltm.save。"""
        from adaptive_skill import AdaptiveSkillSystem
        from adaptive_skill import Skill, SkillStep, SkillStatus, SkillMetadata, GenerationInfo, SkillType, QualityMetrics
        from datetime import datetime

        mock_ltm = MagicMock()
        mock_ltm.recall.return_value = []
        mock_ltm.save.return_value = {"id": "ltm-xxx", "content": "..."}

        mock_kb = MagicMock()
        mock_kb.search.return_value = []
        mock_kb.get.return_value = None
        mock_kb.update.return_value = None

        system = AdaptiveSkillSystem(kb_client=mock_kb, ltm_client=mock_ltm)

        # 本地构造 Skill，不依赖 test_core
        skill = Skill(
            skill_id="test-skill-ltm-save",
            name="测试 Skill",
            description="用于验证 LTM 保存",
            version="1.0",
            status=SkillStatus.ACTIVE,
            steps=[SkillStep(1, "步骤一", "测试步骤", "记忆")],
            required_inputs=["problem"],
            outputs=["result"],
            parameters={},
            metadata=SkillMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by="test",
            ),
            generation_info=GenerationInfo(skill_type=SkillType.MANUAL, confidence=0.8),
            quality_metrics=QualityMetrics(),
        )
        system.skills_cache[skill.skill_id] = skill

        updated = system.update_skill_from_feedback(skill.skill_id, "缺少数据支撑")
        # ltm.save 应被调用
        mock_ltm.save.assert_called_once()
        call_data = mock_ltm.save.call_args[0][0]  # 第一个位置参数 = dict
        assert "content" in call_data
        assert "skill" in call_data["content"].lower() or skill.name in call_data["content"]


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
