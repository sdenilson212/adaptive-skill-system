"""Harness 回归测试：校验 schema 边界、重复 dimension 防护、duration 语义。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill.core import SolveResponse
from adaptive_skill.harness import (
    CaseSpec,
    GraderSpec,
    GraderValidationError,
    HarnessError,
    grade,
    run_case,
    validate_grader,
)


def make_case() -> CaseSpec:
    return CaseSpec(
        case_id="case.training.analysis",
        title="训练效果分析",
        description="分析一次训练并给出简要结论",
        task_type="analysis",
        input_payload={"problem": "分析这次训练效果"},
        expected_outcome_type="text",
        grader_ref="grader.training.analysis",
        expected_layer=[3],
    )


def make_valid_grader() -> GraderSpec:
    return GraderSpec(
        grader_id="grader.training.analysis",
        name="training analysis grader",
        grading_mode="scored",
        dimensions=[
            {
                "name": "keywords",
                "type": "contains_keywords",
                "weight": 1.0,
                "expected": ["训练效果"],
            }
        ],
        pass_threshold=1.0,
    )


class DummySystem:
    def __init__(self, *, delay_seconds: float = 0.02, solve_duration_ms: float = 1.0):
        self.delay_seconds = delay_seconds
        self.solve_duration_ms = solve_duration_ms

    def solve(self, problem: str, verbose: bool = False) -> SolveResponse:
        time.sleep(self.delay_seconds)
        return SolveResponse(
            result="这次训练效果不错",
            skill_used=None,
            layer=3,
            status="success",
            confidence=0.92,
            execution_time_ms=self.solve_duration_ms,
            metadata={"problem": problem, "verbose": verbose},
        )


def test_validate_grader_rejects_empty_contains_keywords() -> None:
    grader = GraderSpec(
        grader_id="grader.empty.keywords",
        name="empty keywords",
        grading_mode="hybrid",
        dimensions=[
            {
                "name": "keywords",
                "type": "contains_keywords",
                "weight": 1.0,
                "expected": [],
            }
        ],
        pass_threshold=0.5,
    )

    with pytest.raises(GraderValidationError, match="non-empty list of strings"):
        validate_grader(grader)


def test_validate_grader_rejects_scalar_layer_in() -> None:
    grader = GraderSpec(
        grader_id="grader.scalar.layer",
        name="scalar layer",
        grading_mode="scored",
        dimensions=[
            {
                "name": "layer",
                "type": "layer_in",
                "weight": 1.0,
                "expected": 3,
            }
        ],
        pass_threshold=0.5,
    )

    with pytest.raises(GraderValidationError, match="non-empty list of integers"):
        validate_grader(grader)


def test_validate_grader_rejects_duplicate_dimension_names() -> None:
    grader = GraderSpec(
        grader_id="grader.duplicate.dimensions",
        name="duplicate dimensions",
        grading_mode="scored",
        dimensions=[
            {
                "name": "dup",
                "type": "contains_keywords",
                "weight": 0.5,
                "expected": ["训练效果"],
            },
            {
                "name": "dup",
                "type": "layer_in",
                "weight": 0.5,
                "expected": [3],
            },
        ],
        pass_threshold=0.5,
    )

    with pytest.raises(GraderValidationError, match="duplicates an earlier dimension"):
        validate_grader(grader)


def test_grade_fails_loudly_on_duplicate_dimension_names_without_prior_validation() -> None:
    grader = GraderSpec(
        grader_id="grader.runtime.duplicate",
        name="runtime duplicate dimensions",
        grading_mode="scored",
        dimensions=[
            {
                "name": "dup",
                "type": "contains_keywords",
                "weight": 0.5,
                "expected": ["训练效果"],
            },
            {
                "name": "dup",
                "type": "layer_in",
                "weight": 0.5,
                "expected": [3],
            },
        ],
        pass_threshold=0.5,
    )
    observation = {"result": "训练效果不错", "layer": 3, "status": "success"}

    with pytest.raises(HarnessError, match="Duplicate dimension name detected at runtime"):
        grade(make_case(), grader, observation)


def test_run_case_records_harness_wall_clock_duration() -> None:
    result = run_case(
        make_case(),
        DummySystem(delay_seconds=0.02, solve_duration_ms=1.0),
        make_valid_grader(),
        system_version="test",
    )

    assert result.final_status == "pass"
    assert result.duration_ms >= 15
    assert result.duration_ms > result.solve_response["execution_time_ms"]
    assert result.metadata["duration_source"] == "harness_wall_clock_ms"
    assert result.metadata["solve_duration_ms"] == 1.0
