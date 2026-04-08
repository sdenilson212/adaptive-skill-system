"""
Fixture: Layer 1 — KB direct hit.

Scenario
--------
The AdaptiveSkillSystem already has a Skill in its KB that directly matches
the problem. We expect:
  - response.layer == 1
  - response.status in {"success"}
  - response.confidence >= 0.80
  - response.result is not None  (some output was produced)

Grader dimensions
-----------------
  layer_check  : hard assertion — must be layer 1
  confidence   : score proportional to response.confidence
  has_result   : hard assertion — result must not be None/empty
"""

from adaptive_skill.harness.specs import CaseSpec, GraderSpec

# ── Case definition ──────────────────────────────────────────────────────────
case = CaseSpec(
    case_id="fix-layer1-kb-hit-v1",
    title="Layer 1 KB direct hit — 运营策略分解法",
    description=(
        "问题设计上包含与 KB 中已有 Skill 高度重叠的关键词，"
        "期望系统通过 Layer 1（KB 直接命中）解决。"
    ),
    task_type="skill_execution",
    input_payload={
        "problem": (
            "请用分解法为我制定一份简单的运营策略，"
            "包含目标定义、渠道选择、执行计划三个步骤。"
        )
    },
    expected_outcome_type="text",
    expected_layer=[1],
    tags=["layer1", "kb-hit", "smoke"],
    metadata={
        "fixture_version": "1.0",
    },
)

# ── Grader definition ────────────────────────────────────────────────────────
grader = GraderSpec(
    grader_id="grader-layer1-kb-hit-v1",
    name="Layer 1 KB hit grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {
            "name": "layer_correct",
            "type": "exact_match",
            "weight": 0.40,
            "hard_fail": True,
            "config": {
                "field": "layer",
                "expected": 1,
                "description": "Must be resolved by Layer 1 (KB direct hit)",
            },
        },
        {
            "name": "has_result",
            "type": "non_empty",
            "weight": 0.35,
            "hard_fail": True,
            "config": {
                "field": "result",
                "description": "Solver must return a non-None, non-empty result",
            },
        },
        {
            "name": "confidence_quality",
            "type": "threshold",
            "weight": 0.25,
            "hard_fail": False,
            "config": {
                "field": "confidence",
                "min_value": 0.80,
                "description": "Layer 1 confidence should be >= 0.80",
            },
        },
    ],
    metadata={
        "fixture_version": "1.0",
        "notes": "Layer 1 smoke test — fastest path through the system",
    },
)
