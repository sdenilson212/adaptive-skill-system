"""H4 — SkillLineage: SQLite WAL mode and busy-timeout hardening.

Verifies:
  - WAL journal mode is activated on new connections (PRAGMA journal_mode=WAL)
  - timeout=5 prevents immediate failure under simulated write contention
  - basic read/write still works after the WAL change
  - concurrent thread writes don't raise 'database is locked'
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill.skill_lineage import SkillLineage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_lineage(tmp_path: Path) -> SkillLineage:
    db = tmp_path / "test_lineage.db"
    return SkillLineage(db_path=str(db))


def _add_skill(lineage: SkillLineage, skill_id: str, parent_id: str = None) -> None:
    lineage.register({
        "skill_id": skill_id,
        "name": f"Test Skill {skill_id}",
        "description": "test",
        "parent_id": parent_id,
        "evolution_type": "original" if parent_id is None else "derived",
    })


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWALMode:
    def test_wal_journal_mode_is_enabled(self, tmp_path):
        """After the first connection, PRAGMA journal_mode should return 'wal'."""
        lineage = _make_lineage(tmp_path)
        with lineage._conn() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
        assert mode == "wal", f"Expected WAL mode, got: {mode!r}"

    def test_wal_persists_across_reconnection(self, tmp_path):
        """WAL mode is a persistent DB setting; a fresh connection should still report wal."""
        lineage = _make_lineage(tmp_path)
        # First connection sets WAL
        with lineage._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        # New connection — mode should still be WAL
        with lineage._conn() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
        assert mode == "wal"


class TestBasicOperationsAfterWAL:
    def test_add_and_get_skill(self, tmp_path):
        lineage = _make_lineage(tmp_path)
        _add_skill(lineage, "SKL-001")
        result = lineage.get("SKL-001")
        assert result is not None
        assert result["id"] == "SKL-001"

    def test_add_derived_skill(self, tmp_path):
        lineage = _make_lineage(tmp_path)
        _add_skill(lineage, "SKL-001")
        _add_skill(lineage, "SKL-002", parent_id="SKL-001")
        tree = lineage.get_lineage_tree("SKL-001")
        # Each child entry is {"skill": {...}, "children": [...]} 
        child_ids = [c["skill"]["id"] for c in tree.get("children", [])]
        assert "SKL-002" in child_ids

    def test_list_roots_works(self, tmp_path):
        lineage = _make_lineage(tmp_path)
        _add_skill(lineage, "ROOT-A")
        _add_skill(lineage, "ROOT-B")
        roots = lineage.list_roots()
        root_ids = {r["id"] for r in roots}
        assert {"ROOT-A", "ROOT-B"}.issubset(root_ids)

    def test_register_failed_draft_roundtrip(self, tmp_path):
        lineage = _make_lineage(tmp_path)
        draft_id = lineage.register_failed_draft(
            problem="为超马训练计划生成 Layer 3 Skill",
            draft={
                "skill_id": "draft-001",
                "name": "超马周期化训练 Skill",
                "steps": [{"name": "分析训练约束"}, {"name": "规划阶段结构"}],
                "verification_checklist": ["确认阶段目标", "确认风险控制"],
            },
            failure_reason="Layer 3 draft rejected by evaluator",
            quality_score=0.58,
            recommendations=["补充更明确的验证清单"],
            extra={"generation_mode": "llm_assisted", "provider_used": "fake-llm"},
        )

        drafts = lineage.list_failed_drafts(limit=5)

        assert draft_id >= 1
        assert len(drafts) == 1
        assert drafts[0]["draft_name"] == "超马周期化训练 Skill"
        assert drafts[0]["recommendations"] == ["补充更明确的验证清单"]
        assert drafts[0]["draft_content"]["steps"][0]["name"] == "分析训练约束"
        assert drafts[0]["extra"]["generation_mode"] == "llm_assisted"
        assert lineage.stats()["failed_draft_count"] == 1



class TestConcurrentWrites:
    def test_concurrent_thread_writes_do_not_raise(self, tmp_path):
        """Multiple threads writing to the same DB should not raise 'database is locked'."""
        lineage = _make_lineage(tmp_path)
        errors: list = []

        def worker(idx: int) -> None:
            try:
                _add_skill(lineage, f"SKL-THREAD-{idx:03d}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent writes raised exceptions: {errors}"

        # Verify all 10 skills were persisted
        all_skills = lineage.list_roots()
        persisted_ids = {s["id"] for s in all_skills}
        expected_ids = {f"SKL-THREAD-{i:03d}" for i in range(10)}
        assert expected_ids.issubset(persisted_ids)
