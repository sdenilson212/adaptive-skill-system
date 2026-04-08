"""Tests for semantic_similarity grader support."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from adaptive_skill.harness.grader_runtime import grade
from adaptive_skill.harness.semantic_grader import compute_semantic_similarity, normalize_semantic_text
from adaptive_skill.harness.specs import CaseSpec, GraderSpec
from adaptive_skill.harness.validator import GraderValidationError, HarnessError, validate_grader


def _case() -> CaseSpec:
    return CaseSpec(
        case_id="semantic-case",
        title="semantic similarity case",
        description="semantic similarity grading",
        task_type="test",
        input_payload={"problem": "dummy"},
        expected_outcome_type="text",
    )


def _semantic_assertion(*, reference: object, min_similarity: float = 0.8, method: str = "sequence_matcher") -> dict:
    return {
        "type": "semantic_similarity",
        "config": {
            "field": "result",
            "reference": reference,
            "min_similarity": min_similarity,
            "method": method,
        },
    }


def _pass_fail_grader(assertions: list[dict]) -> GraderSpec:
    return GraderSpec(
        grader_id="semantic-pass-fail",
        name="semantic pass/fail grader",
        grading_mode="pass_fail",
        assertions=assertions,
    )


class TestSemanticHelpers:
    def test_normalize_semantic_text_applies_nfkc_casefold_and_whitespace(self):
        text = "  ＡI\n   Planner  "
        assert normalize_semantic_text(text) == "ai planner"

    def test_compute_semantic_similarity_returns_high_score_for_equivalent_text(self):
        actual = "Write a clean release summary with bullet points"
        reference = " write a clean release summary with bullet points "
        assert compute_semantic_similarity(actual, reference) == pytest.approx(1.0)

    def test_compute_semantic_similarity_supports_structured_values(self):
        actual = {"title": "weekly review", "status": "done"}
        reference = {"status": "done", "title": "weekly review"}
        assert compute_semantic_similarity(actual, reference) == pytest.approx(1.0)


class TestSemanticValidator:
    def test_validate_grader_accepts_semantic_similarity(self):
        grader = _pass_fail_grader([
            _semantic_assertion(reference="balanced training plan", min_similarity=0.7),
        ])
        validate_grader(grader)

    def test_validate_grader_rejects_invalid_min_similarity(self):
        grader = _pass_fail_grader([
            _semantic_assertion(reference="balanced training plan", min_similarity=1.5),
        ])
        with pytest.raises(GraderValidationError, match="between 0.0 and 1.0"):
            validate_grader(grader)

    def test_validate_grader_rejects_unknown_method(self):
        grader = _pass_fail_grader([
            _semantic_assertion(
                reference="balanced training plan",
                min_similarity=0.7,
                method="embedding_magic",
            ),
        ])
        with pytest.raises(GraderValidationError, match="config.method"):
            validate_grader(grader)


class TestSemanticRuntime:
    def test_pass_fail_semantic_similarity_passes_when_above_threshold(self):
        grader = _pass_fail_grader([
            _semantic_assertion(
                reference="Plan a balanced marathon training schedule with recovery days.",
                min_similarity=0.8,
            ),
        ])
        observation = {
            "status": "success",
            "layer": 1,
            "result": " plan a balanced marathon training schedule with recovery days ",
        }

        output = grade(_case(), grader, observation)
        assert output.final_status == "pass"
        assert output.final_score == 1.0
        assert output.assertion_results[0]["score"] >= 0.99


    def test_pass_fail_semantic_similarity_fails_when_below_threshold(self):
        grader = _pass_fail_grader([
            _semantic_assertion(
                reference="Plan a balanced marathon training schedule with recovery days.",
                min_similarity=0.8,
            ),
        ])
        observation = {
            "status": "success",
            "layer": 1,
            "result": "Return only the database migration SQL script.",
        }

        output = grade(_case(), grader, observation)
        assert output.final_status == "fail"
        assert output.final_score == 0.0
        assert output.assertion_results[0]["score"] < 0.8
        assert "similarity" in output.assertion_results[0]["message"]

    def test_scored_dimension_uses_similarity_score(self):
        grader = GraderSpec(
            grader_id="semantic-scored",
            name="semantic scored grader",
            grading_mode="scored",
            dimensions=[
                {
                    "name": "semantic_match",
                    "type": "semantic_similarity",
                    "weight": 1.0,
                    "config": {
                        "field": "result",
                        "reference": "Summarise the release in concise bullet points.",
                        "min_similarity": 0.6,
                    },
                }
            ],
            pass_threshold=0.6,
        )
        observation = {
            "status": "success",
            "layer": 1,
            "result": "Summarise the release in concise bullet points.",
        }

        output = grade(_case(), grader, observation)
        assert output.final_status == "pass"
        assert output.dimension_scores["semantic_match"] == pytest.approx(1.0)
        assert output.final_score == pytest.approx(1.0)

    def test_runtime_wraps_backend_errors(self, monkeypatch):
        grader = _pass_fail_grader([
            _semantic_assertion(
                reference="balanced training plan",
                min_similarity=0.7,
                method="sentence_transformers",
            ),
        ])

        def _boom(*args, **kwargs):
            raise RuntimeError("embedding backend unavailable")

        monkeypatch.setattr(
            "adaptive_skill.harness.grader_runtime.compute_semantic_similarity",
            _boom,
        )

        with pytest.raises(HarnessError, match="embedding backend unavailable"):
            grade(
                _case(),
                grader,
                {"status": "success", "layer": 1, "result": "balanced training plan"},
            )
