"""Focused tests for Layer 1 / Layer 2 retrieval behaviour."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill import (
    AdaptiveSkillSystem,
    Skill,
    SkillMetadata,
    SkillStatus,
    SkillStep,
    SkillType,
    GenerationInfo,
    QualityMetrics,
    SkillComposer,
)
from adaptive_skill.retrieval import build_query_variants, expand_query_terms, extract_query_terms



class FakeLTMClient:
    def recall(self, query: str):
        normalized = str(query or "")
        if "青年活动志愿者招募" in normalized:
            return [
                {
                    "id": "ltm-1",
                    "content": "青年志愿者招募需要明确岗位、报名门槛和动机设计。",
                    "category": "method",
                    "tags": ["志愿者招募", "岗位设计"],
                },
                {
                    "id": "ltm-2",
                    "content": "培训和复盘闭环可以提升活动执行一致性。",
                    "category": "discussion",
                    "tags": ["培训复盘", "活动运营"],
                },
            ]
        if normalized in {"青年活动志愿者招募", "志愿者招募"}:
            return [
                {
                    "id": "ltm-1",
                    "content": "青年志愿者招募需要明确岗位、报名门槛和动机设计。",
                    "category": "method",
                    "tags": ["志愿者招募", "岗位设计"],
                }
            ]
        if normalized in {"培训复盘", "活动运营"}:
            return [
                {
                    "id": "ltm-2",
                    "content": "培训和复盘闭环可以提升活动执行一致性。",
                    "category": "discussion",
                    "tags": ["培训复盘", "活动运营"],
                }
            ]
        return []


class FusionLTMClient:
    def recall(self, query: str):
        normalized = str(query or "")
        if normalized == "如何设计供应商评估与续约机制":
            return [
                {
                    "id": "broad-memory",
                    "content": "供应商管理通常包括筛选、价格谈判和基本绩效跟踪。",
                    "category": "discussion",
                    "tags": ["供应商管理", "绩效跟踪"],
                },
                {
                    "id": "focused-memory",
                    "content": "供应商评估与续约机制要拆开看：先定义评分维度，再设计续约门槛、预警和复盘节奏。",
                    "category": "method",
                    "tags": ["供应商评估", "续约机制"],
                },
            ]
        if normalized in {"供应商评估", "续约机制", "供应商评估 续约机制"}:
            return [
                {
                    "id": "focused-memory",
                    "content": "供应商评估与续约机制要拆开看：先定义评分维度，再设计续约门槛、预警和复盘节奏。",
                    "category": "method",
                    "tags": ["供应商评估", "续约机制"],
                }
            ]
        return []


class VariantOnlyKBClient:
    def search(self, query: str, top_k: int = 8):
        normalized = str(query or "")
        if normalized in {"季度运营目标拆解", "复盘机制", "季度运营目标拆解 复盘机制"}:
            return [
                {
                    "id": "kb-quarterly-review",
                    "title": "季度运营目标拆解与复盘机制",
                    "content": "季度运营目标拆解需要先拆业务目标，再定义里程碑、复盘节奏和负责人。\n复盘机制要覆盖指标回看、偏差解释、动作调整。",
                    "tags": ["季度运营", "目标拆解", "复盘机制"],
                }
            ]
        return []






def make_skill(skill_id: str, name: str, description: str) -> Skill:
    return Skill(
        skill_id=skill_id,
        name=name,
        description=description,
        version="1.0",
        status=SkillStatus.ACTIVE,
        steps=[
            SkillStep(1, "分析", "分析问题", "框架"),
            SkillStep(2, "执行", description, "记忆"),
        ],
        required_inputs=["problem"],
        outputs=["result"],
        parameters={},
        metadata=SkillMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="test",
        ),
        generation_info=GenerationInfo(skill_type=SkillType.MANUAL, confidence=0.85),
        quality_metrics=QualityMetrics(usage_count=8, success_rate=0.9),
    )


class TestSharedQueryExtraction:
    def test_extract_query_terms_handles_chinese_without_spaces(self):
        terms = extract_query_terms("如何制定季度运营策略")
        assert "运营策略" in terms
        assert "季度运营" in terms or "季度运营策略" in terms

    def test_extract_query_terms_keeps_english_phrase(self):
        terms = extract_query_terms("How to improve user retention strategy")
        assert "user retention" in terms
        assert "retention strategy" in terms

    def test_build_query_variants_adds_semantic_core(self):
        variants = build_query_variants("如何设计季度运营目标拆解和复盘机制")
        queries = [item.query for item in variants]
        assert "如何设计季度运营目标拆解和复盘机制" in queries
        assert any("季度运营目标拆解" in query and "复盘机制" in query for query in queries)

    def test_expand_query_terms_keeps_semantic_core_terms_deduped(self):
        terms = expand_query_terms("如何设计季度运营目标拆解和复盘机制")
        assert any("季度运营目标拆解" in term for term in terms)
        assert "复盘机制" in terms
        assert len(terms) == len(set(terms))



class TestLayer1Ranking:

    def test_layer1_prefers_more_specific_skill(self):
        system = AdaptiveSkillSystem(auto_attach_memory=False)

        system.skills_cache["generic"] = make_skill(
            "generic",
            "策略 Skill",
            "通用策略方法，适合泛化问题。",
        )
        system.skills_cache["specific"] = make_skill(
            "specific",
            "季度运营策略拆解 Skill",
            "围绕季度运营策略，覆盖目标定义、渠道选择和执行计划。",
        )

        result, matched_skill = system._try_layer_1("如何制定季度运营策略")

        assert result is not None
        assert matched_skill is not None
        assert matched_skill.skill_id == "specific"

    def test_layer1_can_recall_kb_entry_from_query_variant(self):
        system = AdaptiveSkillSystem(
            kb_client=VariantOnlyKBClient(),
            auto_attach_memory=False,
        )

        result, matched_skill = system._try_layer_1("如何设计季度运营目标拆解和复盘机制")

        assert result is not None
        assert matched_skill is not None
        assert matched_skill.skill_id == "kb-quarterly-review"


class TestLayer2Search:

    def test_search_ltm_dedupes_and_ranks_results(self):
        composer = SkillComposer(ltm_client=FakeLTMClient())
        keywords = composer._extract_keywords("如何设计青年活动志愿者招募与培训复盘机制")

        results = composer.search_ltm(
            "如何设计青年活动志愿者招募与培训复盘机制",
            keywords,
            max_results=10,
        )

        memory_ids = [item.memory_id for item in results]
        assert memory_ids.count("ltm-1") == 1
        assert memory_ids.count("ltm-2") == 1
        assert results[0].relevance_score >= results[1].relevance_score
        assert set(memory_ids[:2]) == {"ltm-1", "ltm-2"}

    def test_search_ltm_fuses_multi_query_hits(self):
        composer = SkillComposer(ltm_client=FusionLTMClient())
        problem = "如何设计供应商评估与续约机制"
        keywords = composer._extract_keywords(problem)

        results = composer.search_ltm(problem, keywords, max_results=5)

        assert results[0].memory_id == "focused-memory"
        assert results[0].relevance_score > results[1].relevance_score


