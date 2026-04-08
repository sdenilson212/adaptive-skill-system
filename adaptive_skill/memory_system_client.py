"""
adaptive_skill/memory_system_client.py — KB/LTM 持久层适配器

职责
----
将 AdaptiveSkillSystem 内部使用的接口（ltm.recall / ltm.save / kb.search / kb.get /
kb.update）桥接到 ai-memory-system 的真实持久层实现（LTMManager / KBManager）。

为什么需要这个层
--------------
1. ai-memory-system 的 LTMManager.search()  — adaptive_skill 内部调用 ltm.recall()
2. ai-memory-system 的 LTMManager.save()    — adaptive_skill 内部调用 ltm.save({...})
3. ai-memory-system 的 KBManager.search()   — adaptive_skill 内部调用 kb.search(query, top_k)
4. ai-memory-system 的 KBManager.get/update — adaptive_skill 内部调用 kb.get/kb.update

适配器将以上不一致的签名统一对齐，同时做好 graceful fallback：
- memory_dir 不存在 → 降级为 None 客户端，系统继续运行但无持久化
- 依赖库未安装      → 同上降级

此文件不依赖任何 adaptive_skill 内部模块，可安全被 core.py 引入。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LTM 适配层
# ---------------------------------------------------------------------------

class LTMClientAdapter:
    """
    把 LTMManager 的接口适配为 AdaptiveSkillSystem 期望的接口。

    AdaptiveSkillSystem 内部调用约定
    ---------------------------------
    - ltm.recall(query=problem)   → 关键词搜索，返回 list | dict
    - ltm.save({content, category, tags})  → 保存记忆条目
    """

    def __init__(self, ltm_manager) -> None:
        self._ltm = ltm_manager

    def recall(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        搜索 LTM，返回与 query 相关的记忆条目列表。

        返回格式统一为 list[dict]，与 SeededBenchmarkLTMClient 兼容：
            [{"id": ..., "content": ..., "category": ..., "tags": [...]}, ...]
        """
        try:
            results = self._ltm.search(query, max_results=max_results)
            return [self._entry_to_dict(e) for e in results]
        except Exception as exc:
            logger.debug(f"LTM recall 失败，返回空列表: {exc}")
            return []

    def save(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        保存记忆条目。

        data 格式（adaptive_skill 内部约定）：
            {"content": str, "category": str, "tags": list[str]}
        """
        content = data.get("content", "")
        if not content or not content.strip():
            return None

        category = data.get("category", "other")
        tags = data.get("tags") or []

        # LTMManager.save 要求 category 在白名单内，做一次安全转换
        _VALID_LTM_CATEGORIES = {
            "profile", "preference", "project", "decision", "habit", "credential", "other"
        }
        if category not in _VALID_LTM_CATEGORIES:
            category = "other"

        try:
            entry = self._ltm.save(
                content=content,
                category=category,
                source="ai-detected",
                tags=list(tags),
            )
            return self._entry_to_dict(entry)
        except Exception as exc:
            logger.debug(f"LTM save 失败: {exc}")
            return None

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry) -> Dict[str, Any]:
        """将 LTMEntry dataclass 或 dict 统一转为 dict。"""
        if isinstance(entry, dict):
            return entry
        # LTMEntry dataclass
        return {
            "id": getattr(entry, "id", ""),
            "content": getattr(entry, "content", ""),
            "category": getattr(entry, "category", "other"),
            "tags": list(getattr(entry, "tags", [])),
            "created_at": getattr(entry, "created_at", ""),
        }


# ---------------------------------------------------------------------------
# KB 适配层
# ---------------------------------------------------------------------------

class KBClientAdapter:
    """
    把 KBManager 的接口适配为 AdaptiveSkillSystem 期望的接口。

    AdaptiveSkillSystem 内部调用约定
    ---------------------------------
    - kb.search(query, top_k)   → 返回 list[dict]（有 id/title/content/tags 字段）
    - kb.get(skill_id)          → 返回单个条目 dict 或 None
    - kb.update(skill_id, obj)  → 更新条目（此处做 best-effort：只记录日志）
    """

    def __init__(self, kb_manager) -> None:
        self._kb = kb_manager

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索 KB，返回 list[dict] 格式。"""
        try:
            results = self._kb.search(query=query, top_k=top_k)
            return [self._entry_to_dict(e) for e in results]
        except Exception as exc:
            logger.debug(f"KB search 失败，返回空列表: {exc}")
            return []

    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取 KB 条目，不存在时返回 None。"""
        try:
            # KBManager 没有直接的 get(id) — 通过 list_all 过滤
            entries = self._kb.list_all(limit=10000)
            for e in entries:
                eid = getattr(e, "id", None) or (e.get("id") if isinstance(e, dict) else None)
                if eid == entry_id:
                    return self._entry_to_dict(e)
            return None
        except Exception as exc:
            logger.debug(f"KB get 失败: {exc}")
            return None

    def update(self, entry_id: str, updated_skill: Any) -> None:
        """
        将更新后的 Skill 写回 KB。

        KBManager.update() 只支持 title/content/tags 字段更新。
        这里把 Skill 序列化后写入 content 字段，保留搜索能力。
        """
        try:
            # 取出要写入的文本内容
            if hasattr(updated_skill, "to_dict"):
                import json
                content = json.dumps(updated_skill.to_dict(), ensure_ascii=False)
                name = updated_skill.name
            elif isinstance(updated_skill, dict):
                import json
                content = json.dumps(updated_skill, ensure_ascii=False)
                name = updated_skill.get("name", "updated")
            else:
                content = str(updated_skill)
                name = entry_id

            self._kb.update(entry_id=entry_id, title=name, content=content)
        except Exception as exc:
            logger.debug(f"KB update 失败（best-effort，忽略）: {exc}")

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry) -> Dict[str, Any]:
        """将 KBEntry dataclass 或 dict 统一转为 dict。"""
        if isinstance(entry, dict):
            return entry
        return {
            "id": getattr(entry, "id", ""),
            "title": getattr(entry, "title", ""),
            "content": getattr(entry, "content", ""),
            "category": getattr(entry, "category", "personal"),
            "tags": list(getattr(entry, "tags", [])),
            "source": getattr(entry, "source", ""),
            "confidence": getattr(entry, "confidence", "high"),
            "confirmed": getattr(entry, "confirmed", True),
            "created_at": getattr(entry, "created_at", ""),
        }


# ---------------------------------------------------------------------------
# MemorySystemClient — 顶层门面
# ---------------------------------------------------------------------------

class MemorySystemClient:
    """
    顶层门面：接受 memory_dir 路径，初始化真实持久层，
    并暴露 .kb 和 .ltm 两个适配后的客户端给 AdaptiveSkillSystem 使用。

    初始化失败时（路径不存在、依赖缺失等）自动降级为 None 客户端，
    不会抛出异常，让系统以无持久化模式继续运行。

    Parameters
    ----------
    memory_dir : str | Path
        ai-memory-system 的 memory-bank 目录路径，或其父目录。
        支持两种约定：
          - 直接指向 memory-bank/（含 knowledge-base.md）
          - 指向 memory-bank/ 的父目录（自动拼接 memory-bank/）
    """

    def __init__(self, memory_dir: str) -> None:
        self.memory_dir = Path(memory_dir)
        self.kb: Optional[KBClientAdapter] = None
        self.ltm: Optional[LTMClientAdapter] = None
        self._initialized = False

        self._try_init()

    def _try_init(self) -> None:
        """尝试加载真实持久层；失败时静默降级。"""

        # 解析 memory_dir：优先寻找实际包含 knowledge-base.md 的目录
        candidate_dirs = [
            self.memory_dir,
            self.memory_dir / "memory-bank",
        ]
        resolved_dir: Optional[Path] = None
        for d in candidate_dirs:
            if d.exists() and (d / "knowledge-base.md").exists():
                resolved_dir = d
                break
        # 若 knowledge-base.md 不存在但目录存在，仍允许继续（首次使用）
        if resolved_dir is None:
            for d in candidate_dirs:
                if d.exists():
                    resolved_dir = d
                    break

        if resolved_dir is None:
            logger.info(
                f"memory_dir 路径不存在，持久层降级为 None 客户端: {self.memory_dir}"
            )
            return

        # 将 ai-memory-system 的 engine/ 目录加入 sys.path，以便导入其 core 模块
        engine_dir = _find_engine_dir(resolved_dir)
        if engine_dir and str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))

        try:
            from core.ltm import LTMManager
            from core.kb import KBManager

            ltm_raw = LTMManager(resolved_dir)
            kb_raw = KBManager(resolved_dir)

            self.ltm = LTMClientAdapter(ltm_raw)
            self.kb = KBClientAdapter(kb_raw)
            self._initialized = True

            logger.info(
                f"MemorySystemClient 初始化成功，memory_dir={resolved_dir}"
            )
        except ImportError as exc:
            logger.warning(
                f"无法导入 core.ltm / core.kb（ai-memory-system 未安装？），"
                f"持久层降级为 None 客户端: {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"MemorySystemClient 初始化异常，持久层降级为 None 客户端: {exc}"
            )

    @property
    def is_available(self) -> bool:
        """返回持久层是否成功初始化。"""
        return self._initialized


# ---------------------------------------------------------------------------
# 路径探测辅助
# ---------------------------------------------------------------------------

def _find_engine_dir(memory_bank_dir: Path) -> Optional[Path]:
    """
    从 memory-bank 目录向上查找 ai-memory-system engine 目录。

    期望目录结构：
        ai-memory-system/engine/memory-bank/   ← memory_bank_dir
        ai-memory-system/engine/core/          ← 需要加入 sys.path 的 engine dir
    """
    # memory-bank 的父目录就是 engine/（或自定义同级）
    parent = memory_bank_dir.parent
    if (parent / "core" / "ltm.py").exists():
        return parent

    # 再往上一层
    grandparent = parent.parent
    if (grandparent / "core" / "ltm.py").exists():
        return grandparent

    return None


# ---------------------------------------------------------------------------
# 快速冒烟测试（仅 __main__ 时运行）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.DEBUG)

    # 默认指向本机 ai-memory-system 路径
    # __file__ = .../output/adaptive-skill-system/adaptive_skill/memory_system_client.py
    # parent   = adaptive_skill/
    # parent^2 = adaptive-skill-system/
    # parent^3 = output/
    # parent^4 = Claw/
    # 所以 memory-bank 在 output/ 下，需要 parent^3 / "ai-memory-system/..."
    _DEFAULT_MEMORY_DIR = (
        Path(__file__).resolve().parent.parent.parent
        / "ai-memory-system" / "engine" / "memory-bank"
    )

    print(f"尝试连接 memory_dir: {_DEFAULT_MEMORY_DIR}")
    client = MemorySystemClient(str(_DEFAULT_MEMORY_DIR))

    if client.is_available:
        print("持久层已就绪")

        # 测试 LTM recall
        hits = client.ltm.recall("运营策略", max_results=3)
        print(f"LTM recall 结果: {len(hits)} 条")
        for h in hits:
            print(f"  [{h.get('id', '?')}] {h.get('content', '')[:60]}")

        # 测试 KB search
        kb_hits = client.kb.search("策略", top_k=3)
        print(f"KB search 结果: {len(kb_hits)} 条")
        for h in kb_hits:
            print(f"  [{h.get('id', '?')}] {h.get('title', '')}")
    else:
        print("持久层不可用，系统将以无持久化模式运行（这在单元测试场景是正常的）")
