"""
Fixture: Layer 3 — Auto-generate a new Skill.

Scenario
--------
The problem is highly specific and unlikely to match any existing KB Skill or
be directly composable from LTM. The system should fall through to Layer 3
and auto-generate a new Skill.

Expected behaviour:
  - response.layer == 3
  - response.status in {"success", "partial"}
  - response.result is not None
  - response.confidence >= 0.60 (quality threshold for Layer 3)
  - metadata["layer_3_auto_generated"] == True
"""

from adaptive_skill.harness.specs import CaseSpec, GraderSpec

# ── Case definition ──────────────────────────────────────────────────────────
case = CaseSpec(
    case_id="fix-layer3-generate-v1",
    title="Layer 3 Auto-generate — 超马周期化训练计划",
    description=(
        "高度专属的超马跑步问题，不大可能命中 KB 或从 LTM 直接组合，"
        "期望强制触发 Layer 3 自动生成新 Skill。"
    ),
    task_type="skill_generation",
    input_payload={
        "problem": (
            "请帮我设计一套针对超马跑步运动员的赛季周期化训练计划，"
            "包含基础期、专项期、比赛期和恢复期四个阶段，"
            "每阶段给出训练量、强度分布和关键课次示例。"
        )
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=["layer3", "auto-generate", "novel-domain"],
    metadata={
        "fixture_version": "1.0",
        "description": (
            "Highly specific ultra-marathon periodisation problem — "
            "not expected to be in KB, forces Layer 3 auto-generation."
        ),
    },
)

# ── Grader definition ────────────────────────────────────────────────────────
grader = GraderSpec(
    grader_id="grader-layer3-generate-v1",
    name="Layer 3 auto-generation grader",
    grading_mode="scored",
    pass_threshold=0.60,
    dimensions=[
        {
            "name": "layer_is_3",
            "type": "exact_match",
            "weight": 0.35,
            "hard_fail": True,
            "config": {
                "field": "layer",
                "expected": 3,
                "description": "Must fall through to Layer 3 auto-generation",
            },
        },
        {
            "name": "has_result",
            "type": "non_empty",
            "weight": 0.30,
            "hard_fail": True,
            "config": {
                "field": "result",
                "description": "Auto-generated Skill must return a non-None, non-empty result",
            },
        },
        {
            "name": "confidence_60pct",
            "type": "threshold",
            "weight": 0.20,
            "hard_fail": False,
            "config": {
                "field": "confidence",
                "min_value": 0.60,
                "description": "Layer 3 auto-generation quality should be >= 0.60",
            },
        },
        {
            "name": "auto_generated_flag",
            "type": "contains_key",
            "weight": 0.15,
            "hard_fail": False,
            "config": {
                "field": "metadata",
                "key": "layer_3_auto_generated",
                "description": "metadata must carry layer_3_auto_generated flag",
            },
        },
    ],
    metadata={
        "fixture_version": "1.0",
        "notes": (
            "Lower passing_score (0.60 vs 0.70) reflects the inherent uncertainty "
            "of auto-generation for novel domains."
        ),
    },
)
