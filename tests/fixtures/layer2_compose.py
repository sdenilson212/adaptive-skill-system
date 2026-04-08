"""
Fixture: Layer 2 — Composition from LTM.

Scenario
--------
The problem does NOT directly match any single KB Skill, but the system can
compose an answer from LTM fragments. We expect:
  - response.layer in {2, 3}   (2 preferred, fall-through to 3 is allowed)
  - response.status in {"success", "partial"}
  - response.result is not None
  - response.confidence >= 0.50

Note: Because the real system may skip Layer 2 and fall straight to Layer 3
depending on LTM content, the layer assertion uses 'gte' (>= 2) rather than
'exact_match'. The important invariant is that Layer 1 was NOT used.
"""

from adaptive_skill.harness.specs import CaseSpec, GraderSpec

# ── Case definition ──────────────────────────────────────────────────────────
case = CaseSpec(
    case_id="fix-layer2-compose-v1",
    title="Layer 2 Composition — Z世代健身App留存",
    description=(
        "跨领域问题，需要结合心理学原理与数据分析，"
        "不大可能是单一 KB Skill 的直接命中，期望触发 Layer 2 组合或 Layer 3 生成。"
    ),
    task_type="skill_composition",
    input_payload={
        "problem": (
            "如何结合心理学原理和数据分析，"
            "为一款面向 Z 世代的健身 App 制定用户留存提升方案？"
        )
    },
    expected_outcome_type="text",
    expected_layer=[2, 3],
    tags=["layer2", "compose", "cross-domain"],
    metadata={
        "fixture_version": "1.0",
        "description": (
            "Cross-domain problem requiring composition of psychology knowledge "
            "and data analysis — unlikely to be a single KB hit."
        ),
    },
)

# ── Grader definition ────────────────────────────────────────────────────────
grader = GraderSpec(
    grader_id="grader-layer2-compose-v1",
    name="Layer 2 composition grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {
            "name": "not_layer1",
            "type": "gte",
            "weight": 0.40,
            "hard_fail": True,
            "config": {
                "field": "layer",
                "min_value": 2,
                "description": "Layer 1 (direct KB hit) must NOT be used for this cross-domain problem",
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
            "name": "confidence_acceptable",
            "type": "threshold",
            "weight": 0.25,
            "hard_fail": False,
            "config": {
                "field": "confidence",
                "min_value": 0.50,
                "description": "Composition confidence should be >= 0.50",
            },
        },
    ],
    metadata={
        "fixture_version": "1.0",
        "notes": (
            "Layer 2 composition test. "
            "If system falls through to Layer 3, the 'not_layer1' assertion still passes."
        ),
    },
)
