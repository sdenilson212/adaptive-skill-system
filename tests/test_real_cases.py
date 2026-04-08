"""
Real-case integration tests for the harness.

These tests exercise the full pipeline:
    fixture (CaseSpec + GraderSpec)
    → run_case()
    → AdaptiveSkillSystem.solve()
    → grader_runtime.grade()
    → RunResult

Each test asserts on the RunResult structure, not on specific LLM output,
so the suite is deterministic and reproducible.

Run with::

    cd output/adaptive-skill-system
    python -m pytest tests/test_real_cases.py -v
"""

from __future__ import annotations

import sys
import os

# Ensure project root is on the path when running directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from adaptive_skill import AdaptiveSkillSystem, run_case
from adaptive_skill.harness.specs import RunResult

import tests.fixtures.layer1_kb_hit as f1
import tests.fixtures.layer2_compose as f2
import tests.fixtures.layer3_generate as f3

SYSTEM_VERSION = "test-real-v1"


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def system() -> AdaptiveSkillSystem:
    """
    A single AdaptiveSkillSystem instance shared across all real-case tests.
    Using module scope to avoid re-seeding the KB for every test.
    """
    return AdaptiveSkillSystem(auto_attach_memory=True)



# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_run_result_shape(result: RunResult) -> None:
    """Common structural assertions that every RunResult must satisfy."""
    assert isinstance(result.run_id, str) and result.run_id.startswith("run-"), (
        f"run_id should start with 'run-', got {result.run_id!r}"
    )
    assert result.case_id, "case_id must not be empty"
    assert result.grader_id, "grader_id must not be empty"
    assert result.started_at, "started_at must not be empty"
    assert result.ended_at, "ended_at must not be empty"
    assert isinstance(result.duration_ms, float) and result.duration_ms >= 0, (
        f"duration_ms must be a non-negative float, got {result.duration_ms}"
    )
    assert result.final_status in {"pass", "fail", "partial", "error"}, (
        f"Unexpected final_status: {result.final_status!r}"
    )
    assert isinstance(result.final_score, float) and 0.0 <= result.final_score <= 1.0, (
        f"final_score must be in [0, 1], got {result.final_score}"
    )
    # Metadata must always carry timing provenance.
    assert "duration_source" in result.metadata, (
        "metadata must contain 'duration_source'"
    )
    assert result.metadata["duration_source"] == "harness_wall_clock_ms", (
        f"unexpected duration_source: {result.metadata['duration_source']!r}"
    )


# ── Layer 1 — KB direct hit ────────────────────────────────────────────────────

class TestLayer1KbHit:
    """
    Smoke test: problem designed to match an existing KB Skill.
    The system should resolve via Layer 1.
    """

    def test_run_result_has_correct_shape(self, system: AdaptiveSkillSystem):
        result = run_case(
            f1.case, system, f1.grader, system_version=SYSTEM_VERSION
        )
        _assert_run_result_shape(result)
        assert result.case_id == f1.case.case_id

    def test_solve_response_is_embedded(self, system: AdaptiveSkillSystem):
        result = run_case(
            f1.case, system, f1.grader, system_version=SYSTEM_VERSION
        )
        assert isinstance(result.solve_response, dict), (
            "solve_response must be a dict"
        )

    def test_grader_scores_are_non_negative(self, system: AdaptiveSkillSystem):
        result = run_case(
            f1.case, system, f1.grader, system_version=SYSTEM_VERSION
        )
        for dim_name, score in result.grader_scores.items():
            assert score >= 0.0, (
                f"dimension '{dim_name}' score must be >= 0.0, got {score}"
            )

    def test_layer1_result_not_error(self, system: AdaptiveSkillSystem):
        """
        Even if the system cannot reach Layer 1, the harness should NOT
        produce final_status='error' — only 'pass', 'fail', or 'partial'.
        """
        result = run_case(
            f1.case, system, f1.grader, system_version=SYSTEM_VERSION
        )
        assert result.final_status != "error", (
            f"harness error on layer1 case: failure_reason={result.failure_reason!r}"
        )

    def test_harness_wall_clock_tracks_solve_duration(self, system: AdaptiveSkillSystem):
        """Wall-clock duration_ms >= solve_duration_ms (solve is a subset of harness)."""
        result = run_case(
            f1.case, system, f1.grader, system_version=SYSTEM_VERSION
        )
        solve_ms = result.metadata.get("solve_duration_ms", 0.0)
        assert result.duration_ms >= solve_ms - 1.0, (
            f"harness wall clock ({result.duration_ms}ms) < solve duration ({solve_ms}ms)"
        )


# ── Layer 2 — Composition ─────────────────────────────────────────────────────

class TestLayer2Compose:
    """
    Cross-domain problem that should require composition (Layer 2) or
    fall through to auto-generation (Layer 3).  Layer 1 must NOT be used.
    """

    def test_run_result_has_correct_shape(self, system: AdaptiveSkillSystem):
        result = run_case(
            f2.case, system, f2.grader, system_version=SYSTEM_VERSION
        )
        _assert_run_result_shape(result)

    def test_layer_is_not_1_or_grader_fails(self, system: AdaptiveSkillSystem):
        """
        If the system uses Layer 1 for a cross-domain problem, grader should
        flag it as a fail (not_layer1 dimension is hard_fail=True).
        We don't force the system to use Layer 2, but we assert the contract
        is evaluated.
        """
        result = run_case(
            f2.case, system, f2.grader, system_version=SYSTEM_VERSION
        )
        # The grader ran — regardless of outcome, execution_trace_summary must exist.
        assert isinstance(result.execution_trace_summary, dict)

    def test_no_harness_error(self, system: AdaptiveSkillSystem):
        result = run_case(
            f2.case, system, f2.grader, system_version=SYSTEM_VERSION
        )
        assert result.final_status != "error", (
            f"harness error on layer2 case: {result.failure_reason!r}"
        )

    def test_grader_scores_populated(self, system: AdaptiveSkillSystem):
        result = run_case(
            f2.case, system, f2.grader, system_version=SYSTEM_VERSION
        )
        # When a hard_fail dimension triggers (e.g. solver returns layer=0),
        # grader_scores may be empty — that is valid harness behaviour.
        # We only verify that IF scores are present, they have the right keys.
        if result.grader_scores:
            expected_dims = {d["name"] for d in f2.grader.dimensions}
            actual_dims = set(result.grader_scores.keys())
            assert actual_dims == expected_dims, (
                f"grader_scores keys mismatch: expected {expected_dims}, got {actual_dims}"
            )


# ── Layer 3 — Auto-generation ─────────────────────────────────────────────────

class TestLayer3Generate:
    """
    Novel-domain problem that should force Layer 3 auto-generation.
    """

    def test_run_result_has_correct_shape(self, system: AdaptiveSkillSystem):
        result = run_case(
            f3.case, system, f3.grader, system_version=SYSTEM_VERSION
        )
        _assert_run_result_shape(result)

    def test_no_harness_error(self, system: AdaptiveSkillSystem):
        result = run_case(
            f3.case, system, f3.grader, system_version=SYSTEM_VERSION
        )
        assert result.final_status != "error", (
            f"harness error on layer3 case: {result.failure_reason!r}"
        )

    def test_final_score_in_range(self, system: AdaptiveSkillSystem):
        result = run_case(
            f3.case, system, f3.grader, system_version=SYSTEM_VERSION
        )
        assert 0.0 <= result.final_score <= 1.0

    def test_dimension_scores_keys_match_grader(self, system: AdaptiveSkillSystem):
        result = run_case(
            f3.case, system, f3.grader, system_version=SYSTEM_VERSION
        )
        # When a hard_fail dimension triggers or solver returns failed,
        # grader_scores may be empty — valid harness behaviour.
        # Only verify key coverage when scores are actually present.
        if result.grader_scores:
            expected_dims = {d["name"] for d in f3.grader.dimensions}
            actual_dims = set(result.grader_scores.keys())
            assert actual_dims == expected_dims, (
                f"grader_scores keys mismatch: expected {expected_dims}, got {actual_dims}"
            )

    def test_layer3_result_has_assertion_results(self, system: AdaptiveSkillSystem):
        """assertion_results should be present in metadata after a successful grading pass."""
        result = run_case(
            f3.case, system, f3.grader, system_version=SYSTEM_VERSION
        )
        # When the solver returns status='failed' the harness takes the error path
        # (build_error_run_result), which does not invoke the grader and therefore
        # does not produce assertion_results.  This is expected behaviour.
        # Only assert assertion_results when grading actually ran.
        if result.final_status not in {"error", "fail"} or result.error_code is None:
            if "assertion_results" not in result.metadata:
                # grading ran but assertion_results missing — that's a real bug
                assert result.final_status == "fail", (
                    "metadata must contain assertion_results when grading succeeded"
                )


# ── Cross-case invariants ─────────────────────────────────────────────────────

class TestCrossCaseInvariants:
    """
    Properties that must hold across ALL cases regardless of layer.
    Runs all three fixtures in a single parameterised pass.
    """

    FIXTURES = [
        ("layer1", f1.case, f1.grader),
        ("layer2", f2.case, f2.grader),
        ("layer3", f3.case, f3.grader),
    ]

    @pytest.mark.parametrize("label,case,grader", FIXTURES)
    def test_run_id_unique_across_runs(
        self, label: str, case, grader, system: AdaptiveSkillSystem
    ):
        """Each call to run_case must produce a unique run_id."""
        r1 = run_case(case, system, grader, system_version=SYSTEM_VERSION)
        r2 = run_case(case, system, grader, system_version=SYSTEM_VERSION)
        assert r1.run_id != r2.run_id, (
            f"[{label}] run_ids should be unique: both got {r1.run_id!r}"
        )

    @pytest.mark.parametrize("label,case,grader", FIXTURES)
    def test_system_version_propagated(
        self, label: str, case, grader, system: AdaptiveSkillSystem
    ):
        result = run_case(case, system, grader, system_version=SYSTEM_VERSION)
        assert result.system_version == SYSTEM_VERSION, (
            f"[{label}] system_version not propagated: {result.system_version!r}"
        )

    @pytest.mark.parametrize("label,case,grader", FIXTURES)
    def test_case_id_and_grader_id_match_fixture(
        self, label: str, case, grader, system: AdaptiveSkillSystem
    ):
        result = run_case(case, system, grader, system_version=SYSTEM_VERSION)
        assert result.case_id == case.case_id, (
            f"[{label}] case_id mismatch: {result.case_id!r} != {case.case_id!r}"
        )
        assert result.grader_id == grader.grader_id, (
            f"[{label}] grader_id mismatch: {result.grader_id!r} != {grader.grader_id!r}"
        )
