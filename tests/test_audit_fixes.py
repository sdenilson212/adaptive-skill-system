"""Focused regression tests for the 2026-04-03 audit fix pass."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill import AdaptiveSkillSystem, ExecutionResult

from adaptive_skill.composer import LTMSearchResult, SkillComposer
from adaptive_skill.errors import Layer2CoverageError, Layer3QualityGateError
from adaptive_skill.generator import GenerationContext, GenerationStrategy, SkillGenerationProvider, SkillGenerator

from adaptive_skill.skill_lineage import resolve_default_db_path
from adaptive_skill.thresholds import (
    LAYER3_QUALITY_GATE_THRESHOLD,
    RuntimeThresholdPolicy,
    layer3_confidence_level,
    layer3_needs_feedback,
    layer3_status_for_quality,
)



class FakeLTMClient:
    def recall(self, query: str):
        return [{
            "id": "m-1",
            "content": "泛泛而谈的记忆",
            "category": "project",
            "tags": ["generic"],
            "created_at": datetime.now().isoformat(),
        }]


class FakeProvider:
    provider_name = "fake"

    def generate_skill_payload(self, context, strategy):
        return {
            "name": "自定义草稿",
            "description": "用于测试可配置阈值策略",
            "rationale": "测试 provider 辅助生成",
            "confidence": 0.79,
            "steps": [
                {
                    "name": "步骤 1",
                    "description": "先分析问题背景，再整理关键约束与可执行路径。",
                },
                {
                    "name": "步骤 2",
                    "description": "根据上下文给出方案，并保留验证与复盘环节。",
                },
            ],
            "verification_checklist": ["检查步骤完整性", "检查约束映射"],
            "potential_issues": ["上下文不足", "需要人工确认边界"],
        }





def test_resolve_default_db_path_prefers_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit_db = tmp_path / "custom" / "skill_lineage.db"
    monkeypatch.setenv("ADAPTIVE_SKILL_LINEAGE_DB", str(explicit_db))
    monkeypatch.delenv("MEMORY_DIR", raising=False)
    monkeypatch.delenv("ADAPTIVE_SKILL_MEMORY_DIR", raising=False)

    assert resolve_default_db_path() == explicit_db


def test_layer2_coverage_guard_raises_custom_exception() -> None:
    composer = SkillComposer()
    ltm_results = [
        LTMSearchResult(
            memory_id="m-1",
            content="只有一点点泛化信息",
            category="project",
            tags=["generic"],
            relevance_score=0.20,
            timestamp=datetime.now(),
        )
    ]

    with pytest.raises(Layer2CoverageError, match="coverage guard"):
        composer.create_composition_plan(
            "请制定一套完整的商业计划",
            ltm_results,
            {"problem_type": "business_planning", "complexity_level": "medium", "required_expertise": []},
        )


def test_layer3_generator_raises_custom_quality_gate_error(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = SkillGenerator()
    context = generator.analyze_generation_context("设计一个几乎没有上下文的新任务")

    monkeypatch.setattr(
        generator,
        "_generate_by_decomposition",
        lambda context: ([{"name": "步骤 1", "description": "非常短"}], "低质量草稿", 0.25),
    )

    with pytest.raises(Layer3QualityGateError) as exc_info:
        generator.generate_skill_draft(context, GenerationStrategy.DECOMPOSITION)

    assert exc_info.value.quality_threshold == LAYER3_QUALITY_GATE_THRESHOLD


def test_generator_respects_custom_quality_gate_policy() -> None:
    policy = RuntimeThresholdPolicy().with_overrides(layer3_quality_gate_threshold=0.80)
    generator = SkillGenerator(llm_provider=FakeProvider(), threshold_policy=policy)
    context = generator.analyze_generation_context("请设计一个具有上下文约束的新任务流程", available_ltm_info=[{"id": "m-1"}])

    with pytest.raises(Layer3QualityGateError) as exc_info:
        generator.generate_skill_draft(context, GenerationStrategy.HYBRID)

    assert exc_info.value.quality_threshold == pytest.approx(0.80)
    assert exc_info.value.confidence == pytest.approx(0.79)



def test_core_try_layer2_surfaces_policy_exception(monkeypatch: pytest.MonkeyPatch) -> None:

    from adaptive_skill import composer as composer_module

    monkeypatch.setattr(composer_module.SkillComposer, "analyze_problem", lambda self, problem: {"keywords": ["商业计划"]})
    monkeypatch.setattr(composer_module.SkillComposer, "search_ltm", lambda self, problem, keywords: ["dummy"])
    monkeypatch.setattr(composer_module.SkillComposer, "assess_composability", lambda self, ltm_results, problem: (True, {"score": 0.9}))
    monkeypatch.setattr(
        composer_module.SkillComposer,
        "create_composition_plan",
        lambda self, problem, ltm_results, problem_analysis: (_ for _ in ()).throw(
            Layer2CoverageError(
                actual_coverage=0.2,
                minimum_coverage=0.3,
                framework_step_count=5,
                ltm_supported_count=1,
            )
        ),
    )

    system = AdaptiveSkillSystem(ltm_client=FakeLTMClient(), auto_attach_memory=False)
    with pytest.raises(Layer2CoverageError, match="coverage guard"):
        system._try_layer_2("请制定一套完整的商业计划")


def test_solve_keeps_layer2_block_reason_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    block = Layer2CoverageError(
        actual_coverage=0.2,
        minimum_coverage=0.3,
        framework_step_count=5,
        ltm_supported_count=1,
    )
    system = AdaptiveSkillSystem(auto_attach_memory=False)

    monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
    monkeypatch.setattr(system, "_try_layer_2", lambda problem: (_ for _ in ()).throw(block))
    monkeypatch.setattr(
        system,
        "_try_layer_3",
        lambda problem: (
            ExecutionResult(
                success=True,
                output="generated answer",
                duration_seconds=0.001,
                steps_completed=1,
                total_steps=1,
            ),

            None,
            {"quality": 0.82, "strategy": "decomposition", "generation_mode": "heuristic", "provider_used": None},
        ),
    )

    response = system.solve("请制定一套完整的商业计划", verbose=False)

    assert response.layer == 3
    assert response.metadata["layer_2_block"]["error_type"] == "Layer2CoverageError"
    assert response.metadata["layer_2_block"]["actual_coverage"] == pytest.approx(0.2)


def test_solve_returns_structured_failure_after_layer2_and_layer3_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    block = Layer2CoverageError(
        actual_coverage=0.2,
        minimum_coverage=0.3,
        framework_step_count=5,
        ltm_supported_count=1,
    )
    system = AdaptiveSkillSystem(auto_attach_memory=False)

    monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
    monkeypatch.setattr(system, "_try_layer_2", lambda problem: (_ for _ in ()).throw(block))
    monkeypatch.setattr(
        system,
        "_try_layer_3",
        lambda problem: (
            None,
            None,
            {
                "quality": 0.68,
                "blocked_reason": "quality gate",
                "blocked_stage": "draft_generation",
                "generation_mode": "blocked_before_draft",
            },
        ),
    )

    response = system.solve("请制定一套完整的商业计划", verbose=False)

    assert response.layer == 0
    assert response.status == "failed"
    assert response.confidence == pytest.approx(0.0)
    assert response.metadata["layer_2_block"]["error_type"] == "Layer2CoverageError"
    assert response.metadata["layer_3_attempt"]["blocked_reason"] == "quality gate"
    assert response.metadata["layer_3_attempt"]["blocked_stage"] == "draft_generation"



def test_solve_still_honors_legacy_layer1_override(monkeypatch: pytest.MonkeyPatch) -> None:
    system = AdaptiveSkillSystem(auto_attach_memory=False)
    legacy_result = ExecutionResult(
        success=True,
        output="legacy layer 1 result",
        duration_seconds=0.001,
        steps_completed=1,
        total_steps=1,
    )

    monkeypatch.setattr(system, "_try_layer_1", lambda problem: (legacy_result, None))

    response = system.solve("任意问题", verbose=False)

    assert response.layer == 1
    assert response.status == "success"
    assert response.result == "legacy layer 1 result"
    assert response.metadata["decision_trace"] == []



def test_lineage_runtime_register_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:


    class BrokenLineage:
        def register(self, *args, **kwargs):
            raise RuntimeError("db locked")

    system = AdaptiveSkillSystem(auto_attach_memory=False)
    system.lineage = BrokenLineage()
    skill = system._skill_from_kb_entry({"id": "kb-1", "title": "测试 Skill", "content": "步骤一\n步骤二"})

    with caplog.at_level("WARNING"):
        system._register_lineage_skill(skill, stage="layer_1_match")

    assert "SkillLineage register 失败" in caplog.text
    assert "db locked" in caplog.text


def test_layer3_threshold_helpers_stay_consistent() -> None:

    assert layer3_status_for_quality(0.76) == "success"
    assert layer3_status_for_quality(0.74) == "partial"
    assert layer3_needs_feedback(0.84) is True
    assert layer3_needs_feedback(0.85) is False
    assert layer3_confidence_level(0.90) == "high"
    assert layer3_confidence_level(0.72) == "medium"
    assert layer3_confidence_level(0.60) == "low"



def test_generation_context_to_dict_treats_empty_ltm_payload_as_unavailable() -> None:
    context = GenerationContext(
        problem="请设计一个新流程",
        keywords=["设计", "流程"],
        domain="business",
        complexity="medium",
        available_frameworks=[],
        ltm_info={},
    )

    assert context.to_dict()["ltm_info_available"] is False



def test_generation_history_records_final_confidence_not_raw_strategy_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = SkillGenerator()
    context = generator.analyze_generation_context(
        "请为一个已有训练资料的复杂场景设计执行流程",
        available_ltm_info={"references": ["m-1"], "enhancements": []},
    )

    monkeypatch.setattr(
        generator,
        "_generate_hybrid",
        lambda context: (
            [
                {
                    "step": 1,
                    "name": "分析问题",
                    "description": "先梳理目标、约束和验证方式，再进入执行设计。",
                    "source": "hybrid",
                },
                {
                    "step": 2,
                    "name": "执行方案",
                    "description": "输出可执行步骤，并保留验证与复盘检查点。",
                    "source": "hybrid",
                },
            ],
            "使用混合法构建一个带验证闭环的方案。",
            0.95,
        ),
    )

    draft = generator.generate_skill_draft(context, GenerationStrategy.HYBRID)
    expected_confidence = generator.threshold_policy.layer3_base_confidence(
        generation_mode="heuristic",
        provider_payload_used=False,
        has_ltm_support=True,
    )

    assert draft.confidence == pytest.approx(expected_confidence)
    assert generator.generation_history[-1]["confidence"] == pytest.approx(draft.confidence)
    assert generator.generation_history[-1]["confidence"] != pytest.approx(0.95)



def test_generate_hybrid_uses_ltm_enhancement_text_not_dict_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = SkillGenerator()
    context = generator.analyze_generation_context(
        "请设计一套超马训练计划",
        available_ltm_info={
            "references": ["ultra-base"],
            "enhancements": [
                {
                    "source": "ultra-base",
                    "applicable_to": "设定目标",
                    "text": "先明确目标赛事、周期长度和阶段目标。",
                }
            ],
        },
    )

    monkeypatch.setattr(
        generator,
        "_generate_from_template",
        lambda context: (
            [
                {
                    "step": 1,
                    "name": "设定目标",
                    "description": "先确定本轮训练的总体方向。",
                    "source": "template_base",
                }
            ],
            "模板基础方案",
            0.70,
        ),
    )

    steps, _, _ = generator._generate_hybrid(context)

    assert "先明确目标赛事、周期长度和阶段目标。" in steps[0]["description"]
    assert "{'source':" not in steps[0]["description"]
    assert steps[0]["ltm_source"] == "ultra-base"

