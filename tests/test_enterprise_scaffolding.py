"""Regression tests for enterprise scaffolding modules added in v1.1.0."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill import (
    FeedbackAnalyzer,
    FeedbackCollector,
    FeedbackStorage,
    KBCredential,
    KBDocument,
    KBProvider,
    MemoryKBAdapter,
    TenantContext,
    TenantIsolation,
    create_kb_adapter,
)


def test_memory_provider_factory_returns_memory_adapter_and_honors_filters() -> None:
    adapter = create_kb_adapter(KBProvider.MEMORY, KBCredential(provider=KBProvider.MEMORY))

    assert isinstance(adapter, MemoryKBAdapter)

    adapter.save(
        KBDocument(
            doc_id="doc-tenant-a",
            title="运营手册",
            content="tenant a onboarding guide",
            source=KBProvider.MEMORY,
            metadata={"tenant_id": "tenant-a"},
        )
    )
    adapter.save(
        KBDocument(
            doc_id="doc-tenant-b",
            title="运营手册",
            content="tenant b onboarding guide",
            source=KBProvider.MEMORY,
            metadata={"tenant_id": "tenant-b"},
        )
    )

    docs = adapter.search("运营", filters={"tenant_id": "tenant-a"})

    assert [doc.doc_id for doc in docs] == ["doc-tenant-a"]



def test_tenant_isolation_save_does_not_mutate_input_document() -> None:
    adapter = MemoryKBAdapter()
    isolation = TenantIsolation(kb_adapter=adapter)

    original_doc = KBDocument(
        doc_id="doc-001",
        title="Shared playbook",
        content="playbook for tenant-specific onboarding",
        source=KBProvider.MEMORY,
        category="ops",
        metadata={},
    )
    peer_doc = KBDocument(
        doc_id="doc-002",
        title="Shared playbook",
        content="playbook for another tenant",
        source=KBProvider.MEMORY,
        category="ops",
        metadata={},
    )

    with TenantContext.use("tenant-a"):
        assert isolation.save_kb_doc(original_doc) is True
    with TenantContext.use("tenant-b"):
        assert isolation.save_kb_doc(peer_doc) is True

    assert original_doc.doc_id == "doc-001"
    assert original_doc.metadata == {}

    saved_doc = adapter.get("tenant-a:doc-001")
    assert saved_doc is not None
    assert saved_doc.metadata["tenant_id"] == "tenant-a"

    filters = {"category": "ops"}
    with TenantContext.use("tenant-a"):
        docs = isolation.search_kb("playbook", filters=filters)

    assert filters == {"category": "ops"}
    assert [doc.doc_id for doc in docs] == ["tenant-a:doc-001"]



def test_tenant_isolation_get_and_update_passthrough_without_tenant_context() -> None:
    adapter = MemoryKBAdapter()
    isolation = TenantIsolation(kb_adapter=adapter)

    adapter.save(
        KBDocument(
            doc_id="doc-raw-001",
            title="Raw playbook",
            content="no tenant context should passthrough",
            source=KBProvider.MEMORY,
            metadata={},
        )
    )

    fetched = isolation.get_kb_doc("doc-raw-001")
    assert fetched is not None
    assert fetched.doc_id == "doc-raw-001"
    assert adapter.get("None:doc-raw-001") is None

    assert isolation.update("doc-raw-001", {"title": "Updated raw playbook"}) is True
    assert adapter.get("doc-raw-001").title == "Updated raw playbook"
    assert adapter.get("None:doc-raw-001") is None



def test_tenant_isolation_get_and_update_keep_tenant_prefix_when_context_exists() -> None:
    adapter = MemoryKBAdapter()
    isolation = TenantIsolation(kb_adapter=adapter)

    with TenantContext.use("tenant-a"):
        assert isolation.save_kb_doc(
            KBDocument(
                doc_id="doc-001",
                title="Tenant playbook",
                content="tenant specific content",
                source=KBProvider.MEMORY,
                metadata={},
            )
        ) is True

        fetched = isolation.get_kb_doc("doc-001")
        assert fetched is not None
        assert fetched.doc_id == "tenant-a:doc-001"

        assert isolation.update("doc-001", {"title": "Updated tenant playbook"}) is True

    assert adapter.get("tenant-a:doc-001").title == "Updated tenant playbook"



def test_feedback_analyzer_uses_ratings_when_binary_feedback_is_missing(tmp_path: Path) -> None:
    storage = FeedbackStorage(str(tmp_path / "feedback.db"))
    collector = FeedbackCollector(storage)

    collector.rate(5, skill_id="skill-rating-only", comment="great")

    stats = FeedbackAnalyzer(storage).analyze_skill("skill-rating-only")

    assert stats.avg_rating == pytest.approx(5.0)
    assert stats.satisfaction_rate == pytest.approx(1.0)
    assert stats.recommendation == "表现优秀，继续保持"



def test_feedback_analyzer_still_prefers_binary_feedback_when_available(tmp_path: Path) -> None:

    storage = FeedbackStorage(str(tmp_path / "feedback.db"))
    collector = FeedbackCollector(storage)

    collector.rate(1, skill_id="skill-binary-priority", comment="bad")
    collector.thumbs_up(skill_id="skill-binary-priority")
    collector.thumbs_down(skill_id="skill-binary-priority")

    stats = FeedbackAnalyzer(storage).analyze_skill("skill-binary-priority")

    assert stats.avg_rating == pytest.approx(1.0)
    assert stats.satisfaction_rate == pytest.approx(0.5)
    assert "满意度偏低" in (stats.recommendation or "")
