"""H5 — pass_fail grader: OR / at_least_N aggregation semantics.

Tests cover:
  - default "all" (AND) unchanged behaviour
  - "any" (OR) semantics: one passing assertion is enough
  - "at_least_N" semantics: exactly-N threshold gating
  - validator rejects invalid / out-of-range pass_condition values
  - _evaluate_pass_condition runtime error paths
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill.harness.grader_runtime import grade
from adaptive_skill.harness.specs import CaseSpec, GraderSpec
from adaptive_skill.harness.validator import GraderValidationError, validate_grader
from adaptive_skill.harness.validator import HarnessError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _case() -> CaseSpec:
    return CaseSpec(
        case_id="test-pass-condition",
        title="pass_condition test",
        description="pass_condition semantics",
        task_type="test",
        input_payload={"problem": "dummy"},
        expected_outcome_type="text",
    )


def _pf_grader(assertions: list, pass_condition: str = "all") -> GraderSpec:
    return GraderSpec(
        grader_id="grader-pass-condition-test",
        name="pass_condition test grader",
        grading_mode="pass_fail",
        assertions=assertions,
        pass_condition=pass_condition,
    )


def _obs(status: str = "success", layer: int = 1, result="ok") -> dict:
    return {"status": status, "layer": layer, "result": result}


# Two assertions: first passes (status_equals success), second fails (status_equals fail)
_ASSERTIONS_ONE_PASS_ONE_FAIL = [
    {"type": "status_equals", "expected": "success"},
    {"type": "status_equals", "expected": "fail"},
]

# Two assertions: both pass
_ASSERTIONS_BOTH_PASS = [
    {"type": "status_equals", "expected": "success"},
    {"type": "result_not_empty"},
]

# Three assertions: 2 pass (status + result), 1 fails (layer_in 99)
_ASSERTIONS_TWO_PASS_ONE_FAIL = [
    {"type": "status_equals", "expected": "success"},
    {"type": "result_not_empty"},
    {"type": "layer_in", "expected": [99]},
]


# ── Tests: "all" (default AND semantics) ──────────────────────────────────────

class TestPassConditionAll:
    def test_all_pass_when_all_assertions_pass(self):
        grader = _pf_grader(_ASSERTIONS_BOTH_PASS, "all")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "pass"
        assert out.final_score == 1.0

    def test_all_fails_when_any_assertion_fails(self):
        grader = _pf_grader(_ASSERTIONS_ONE_PASS_ONE_FAIL, "all")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "fail"
        assert out.final_score == 0.0

    def test_default_pass_condition_is_all(self):
        # GraderSpec.pass_condition defaults to "all"
        grader = _pf_grader(_ASSERTIONS_ONE_PASS_ONE_FAIL)
        out = grade(_case(), grader, _obs())
        assert out.final_status == "fail"


# ── Tests: "any" (OR semantics) ───────────────────────────────────────────────

class TestPassConditionAny:
    def test_any_passes_when_one_assertion_passes(self):
        grader = _pf_grader(_ASSERTIONS_ONE_PASS_ONE_FAIL, "any")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "pass"
        assert out.final_score == 1.0

    def test_any_fails_when_no_assertion_passes(self):
        assertions = [
            {"type": "status_equals", "expected": "fail"},
            {"type": "layer_in", "expected": [99]},
        ]
        grader = _pf_grader(assertions, "any")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "fail"

    def test_any_passes_when_all_pass(self):
        grader = _pf_grader(_ASSERTIONS_BOTH_PASS, "any")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "pass"

    def test_metadata_records_pass_condition_for_non_default(self):
        grader = _pf_grader(_ASSERTIONS_ONE_PASS_ONE_FAIL, "any")
        out = grade(_case(), grader, _obs())
        assert out.metadata.get("pass_condition") == "any"

    def test_metadata_omits_pass_condition_for_all_default(self):
        grader = _pf_grader(_ASSERTIONS_BOTH_PASS, "all")
        out = grade(_case(), grader, _obs())
        # "all" is default — metadata should not carry a redundant key
        assert "pass_condition" not in out.metadata


# ── Tests: "at_least_N" ───────────────────────────────────────────────────────

class TestPassConditionAtLeastN:
    def test_at_least_1_passes_when_one_assertion_passes(self):
        grader = _pf_grader(_ASSERTIONS_ONE_PASS_ONE_FAIL, "at_least_1")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "pass"

    def test_at_least_2_passes_when_two_assertions_pass(self):
        grader = _pf_grader(_ASSERTIONS_TWO_PASS_ONE_FAIL, "at_least_2")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "pass"

    def test_at_least_3_fails_when_only_two_assertions_pass(self):
        grader = _pf_grader(_ASSERTIONS_TWO_PASS_ONE_FAIL, "at_least_3")
        out = grade(_case(), grader, _obs())
        assert out.final_status == "fail"

    def test_at_least_0_raises_at_runtime(self):
        """at_least_0 should fail validation; but also tested at runtime."""
        # We bypass validator and call grade directly to exercise runtime error path.
        grader = GraderSpec(
            grader_id="grader-at-least-0",
            name="at_least_0 test",
            grading_mode="pass_fail",
            assertions=[{"type": "status_equals", "expected": "success"}],
            pass_condition="at_least_0",
        )
        with pytest.raises(Exception):
            grade(_case(), grader, _obs())


# ── Tests: validator ──────────────────────────────────────────────────────────

class TestValidatorPassCondition:
    def test_valid_all(self):
        grader = _pf_grader([{"type": "status_equals", "expected": "success"}], "all")
        validate_grader(grader)  # should not raise

    def test_valid_any(self):
        grader = _pf_grader([{"type": "status_equals", "expected": "success"}], "any")
        validate_grader(grader)  # should not raise

    def test_valid_at_least_1(self):
        grader = _pf_grader([{"type": "status_equals", "expected": "success"}], "at_least_1")
        validate_grader(grader)  # should not raise

    def test_valid_at_least_2_with_two_assertions(self):
        grader = _pf_grader(_ASSERTIONS_BOTH_PASS, "at_least_2")
        validate_grader(grader)  # should not raise

    def test_invalid_unknown_string_raises(self):
        grader = _pf_grader(
            [{"type": "status_equals", "expected": "success"}],
            pass_condition="majority",
        )
        with pytest.raises(GraderValidationError, match="not supported"):
            validate_grader(grader)

    def test_invalid_at_least_0_raises(self):
        grader = _pf_grader(
            [{"type": "status_equals", "expected": "success"}],
            pass_condition="at_least_0",
        )
        with pytest.raises(GraderValidationError, match="positive integer"):
            validate_grader(grader)

    def test_invalid_at_least_non_int_raises(self):
        grader = _pf_grader(
            [{"type": "status_equals", "expected": "success"}],
            pass_condition="at_least_x",
        )
        with pytest.raises(GraderValidationError, match="invalid"):
            validate_grader(grader)

    def test_at_least_n_exceeds_assertion_count_raises(self):
        """at_least_3 with only 1 assertion is structurally impossible — reject at validation."""
        grader = _pf_grader(
            [{"type": "status_equals", "expected": "success"}],
            pass_condition="at_least_3",
        )
        with pytest.raises(GraderValidationError, match="only 1 are defined"):
            validate_grader(grader)

    def test_pass_condition_ignored_for_scored_mode(self):
        """pass_condition is a pass_fail concern; scored graders ignore it."""
        grader = GraderSpec(
            grader_id="grader-scored-test",
            name="scored grader",
            grading_mode="scored",
            dimensions=[
                {"name": "d", "type": "result_not_empty", "weight": 1.0}
            ],
            pass_threshold=0.5,
            pass_condition="any",  # irrelevant but should not cause error
        )
        validate_grader(grader)  # should not raise
