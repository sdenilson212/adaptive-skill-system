"""
decision_trace 内容质量测试

验证目标：
  1. Layer 1 命中时，trace 包含 skill_id + score + threshold
  2. Layer 1 miss 时，trace 包含 miss 原因
  3. Layer 3 命中时，trace 包含 generation strategy + quality score + dimension scores
  4. 全程走完 3 层时，trace 按顺序包含各层记录
  5. 旧式 monkeypatch lambda 兼容：不传 trace 参数也能正常执行（向后兼容）
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from adaptive_skill import (
    AdaptiveSkillSystem, Skill, SkillStep, SkillMetadata, GenerationInfo,
    QualityMetrics, SkillStatus, SkillType, ExecutionResult, SolveResponse,
)


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def make_skill(skill_id="trace-001", name="trace test skill",
               description="trace testing skill for decision trace tests"):
    return Skill(
        skill_id=skill_id,
        name=name,
        description=description,
        version="1.0",
        status=SkillStatus.ACTIVE,
        steps=[SkillStep(1, "分析", "分析问题", "框架")],
        required_inputs=["problem"],
        outputs=["result"],
        parameters={},
        metadata=SkillMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="test"
        ),
        generation_info=GenerationInfo(skill_type=SkillType.MANUAL, confidence=0.9),
        quality_metrics=QualityMetrics(usage_count=1, success_rate=0.9),
    )


def make_exec_result(skill: Skill):
    return ExecutionResult(
        success=True,
        output={"result": "mock output"},
        duration_seconds=0.01,
        steps_completed=1,
        total_steps=1,
    )


# ─────────────────────────────────────────────
# Test Group 1 — Layer 1 命中 trace
# ─────────────────────────────────────────────

class TestTraceLayer1Hit:
    def test_layer1_hit_trace_has_required_fields(self):
        """Layer 1 命中时，trace 应包含 layer=1, outcome=hit, skill_id, score, threshold"""
        skill = make_skill()
        system = AdaptiveSkillSystem()
        system.skills_cache[skill.skill_id] = skill

        # 传入与 skill name 高度相关的 query，触发命中
        response = system.solve("trace test skill")

        trace = response.metadata.get("decision_trace", [])
        assert len(trace) >= 1, "Layer 1 命中时 trace 应至少有 1 条记录"

        l1_entry = next((e for e in trace if e.get("layer") == 1), None)
        assert l1_entry is not None, "trace 中应有 layer=1 的记录"
        assert l1_entry["outcome"] == "hit"
        assert "skill_id" in l1_entry
        assert "score" in l1_entry
        assert "threshold" in l1_entry
        assert isinstance(l1_entry["score"], float)
        assert l1_entry["score"] >= l1_entry["threshold"], (
            "hit 条目的 score 应 >= threshold"
        )

    def test_layer1_hit_trace_skill_id_matches(self):
        """Layer 1 命中时，trace 中的 skill_id 应与实际命中的 skill 一致"""
        skill = make_skill(skill_id="specific-skill-xyz")
        system = AdaptiveSkillSystem()
        system.skills_cache[skill.skill_id] = skill

        response = system.solve("trace test skill")
        trace = response.metadata.get("decision_trace", [])
        l1_entry = next((e for e in trace if e.get("layer") == 1 and e.get("outcome") == "hit"), None)

        if l1_entry:
            assert l1_entry["skill_id"] == "specific-skill-xyz"


# ─────────────────────────────────────────────
# Test Group 2 — Layer 1 miss trace
# ─────────────────────────────────────────────

class TestTraceLayer1Miss:
    def test_layer1_miss_trace_recorded_when_no_cache(self):
        """没有任何 KB/cache 时，trace 应包含 layer=1, outcome=miss"""
        system = AdaptiveSkillSystem()
        response = system.solve("完全陌生的问题 XYZ")

        trace = response.metadata.get("decision_trace", [])
        l1_entry = next((e for e in trace if e.get("layer") == 1), None)
        assert l1_entry is not None, "trace 中应有 layer=1 的记录"
        assert l1_entry["outcome"] == "miss"
        assert "reason" in l1_entry

    def test_layer1_miss_trace_has_threshold(self):
        """Layer 1 miss 时，trace 中应有 threshold 字段（便于诊断为什么没过）"""
        system = AdaptiveSkillSystem()
        response = system.solve("no skill available for this")

        trace = response.metadata.get("decision_trace", [])
        l1_entry = next((e for e in trace if e.get("layer") == 1), None)
        if l1_entry and l1_entry["outcome"] == "miss":
            assert "threshold" in l1_entry


# ─────────────────────────────────────────────
# Test Group 3 — Layer 3 trace（通过 monkeypatch）
# ─────────────────────────────────────────────

class TestTraceLayer3:
    def test_layer3_hit_via_monkeypatch_produces_trace(self, monkeypatch):
        """Layer 3 命中时，trace 应包含 strategy + overall_score"""
        system = AdaptiveSkillSystem()
        skill = make_skill()
        exec_result = make_exec_result(skill)

        # 用新式 trace-aware lambda
        def fake_l3(problem, trace=None):
            if trace is not None:
                trace.append({
                    "layer": 3,
                    "outcome": "hit",
                    "strategy": "decomposition",
                    "overall_score": 0.81,
                    "quality_gate_threshold": 0.70,
                    "dimension_scores": {"completeness": 0.85, "clarity": 0.78},
                    "ltm_results_count": 3,
                    "skill_draft_steps": 4,
                    "reason": "quality gate passed, skill generated",
                })
            return exec_result, skill, {"quality": 0.81, "confidence": "high",
                                        "strategy": "decomposition", "generation_info": {}}

        monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_2", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_3", fake_l3)

        response = system.solve("生成一个新 Skill")
        assert response.layer == 3

        trace = response.metadata.get("decision_trace", [])
        l3_entry = next((e for e in trace if e.get("layer") == 3), None)
        assert l3_entry is not None, "trace 中应有 layer=3 的记录"
        assert l3_entry["outcome"] == "hit"
        assert "strategy" in l3_entry
        assert "overall_score" in l3_entry

    def test_layer3_quality_gate_rejected_trace(self, monkeypatch):
        """Layer 3 质量门拦截时，trace 应记录 quality_gate_rejected"""
        system = AdaptiveSkillSystem()

        def fake_l3_rejected(problem, trace=None):
            if trace is not None:
                trace.append({
                    "layer": 3,
                    "outcome": "quality_gate_rejected",
                    "strategy": "template",
                    "overall_score": 0.55,
                    "quality_gate_threshold": 0.70,
                    "dimension_scores": {},
                    "ltm_results_count": 1,
                    "reason": "quality gate rejected draft",
                })
            return None, None, {"quality": 0.55, "confidence": "low",
                                 "recommendations": ["add more steps"]}

        monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_2", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_3", fake_l3_rejected)

        response = system.solve("无法解决的问题")
        assert response.status == "failed"

        trace = response.metadata.get("decision_trace", [])
        l3_entry = next((e for e in trace if e.get("layer") == 3), None)
        assert l3_entry is not None
        assert l3_entry["outcome"] == "quality_gate_rejected"


# ─────────────────────────────────────────────
# Test Group 4 — 向后兼容：旧式 lambda 不崩溃
# ─────────────────────────────────────────────

class TestTraceBackwardCompat:
    def test_old_style_monkeypatch_lambda_still_works(self, monkeypatch):
        """旧式 lambda problem: (None, None) monkeypatch 不应因为 trace 参数而崩溃"""
        system = AdaptiveSkillSystem()
        skill = make_skill()
        exec_result = make_exec_result(skill)

        # 旧式 lambda，只接受 problem 参数（没有 trace）
        monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_2", lambda problem: (None, None))
        monkeypatch.setattr(
            system,
            "_try_layer_3",
            lambda problem: (exec_result, skill, {"quality": 0.80}),
        )

        # 不应抛出 TypeError
        response = system.solve("旧式 lambda 兼容测试")
        assert response is not None
        assert response.layer == 3

    def test_old_style_layer1_lambda_does_not_raise(self, monkeypatch):
        """旧式 Layer 1 lambda 命中路径，不因 trace 参数崩溃"""
        system = AdaptiveSkillSystem()
        skill = make_skill()
        exec_result = make_exec_result(skill)

        monkeypatch.setattr(
            system,
            "_try_layer_1",
            lambda problem: (exec_result, skill),
        )

        response = system.solve("任意问题")
        assert response.layer == 1


# ─────────────────────────────────────────────
# Test Group 5 — trace 顺序与完整性
# ─────────────────────────────────────────────

class TestTraceOrdering:
    def test_trace_records_all_layers_in_order(self, monkeypatch):
        """走完 L1 miss → L2 miss → L3 hit 时，trace 至少包含 L3 记录；
        如果 L1/L2 用的是 trace-aware callable，则 trace 会包含全部 3 层。
        注：旧式 lambda 不写 trace，属于向后兼容的已知行为。
        此测试验证：L3 trace 正确产出，且整体 trace 非空。
        """
        system = AdaptiveSkillSystem()
        skill = make_skill()
        exec_result = make_exec_result(skill)

        def fake_l3(problem, trace=None):
            if trace is not None:
                trace.append({
                    "layer": 3, "outcome": "hit",
                    "strategy": "analogy",
                    "overall_score": 0.75,
                    "quality_gate_threshold": 0.70,
                    "dimension_scores": {},
                    "ltm_results_count": 2,
                    "skill_draft_steps": 3,
                    "reason": "quality gate passed",
                })
            return exec_result, skill, {"quality": 0.75, "confidence": "medium",
                                        "strategy": "analogy", "generation_info": {}}

        monkeypatch.setattr(system, "_try_layer_1", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_2", lambda problem: (None, None))
        monkeypatch.setattr(system, "_try_layer_3", fake_l3)

        response = system.solve("测试问题完整流程")
        trace = response.metadata.get("decision_trace", [])

        # trace 应非空
        assert len(trace) >= 1, f"trace 不应为空: {trace}"

        # layer 3 记录应存在
        l3_entry = next((e for e in trace if e.get("layer") == 3), None)
        assert l3_entry is not None, f"trace 中应有 layer=3 的记录: {trace}"
        assert l3_entry["outcome"] == "hit"

        # 在 trace 中如果存在多层记录，layer 3 应是最后一个 layer 值（有序）
        all_layers = [e["layer"] for e in trace if "layer" in e]
        if len(all_layers) > 1:
            idx_3 = next(i for i, e in enumerate(trace) if e.get("layer") == 3)
            earlier_layers = [e["layer"] for e in trace[:idx_3]]
            for l in earlier_layers:
                assert l < 3, f"layer 3 前面出现了比 3 更大的层号: {earlier_layers}"
