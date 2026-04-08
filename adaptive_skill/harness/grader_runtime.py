"""P0 grader runtime for single-case harness execution."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .semantic_grader import (
    DEFAULT_SENTENCE_TRANSFORMER_MODEL,
    SUPPORTED_SEMANTIC_METHODS,
    compute_semantic_similarity,
)
from .specs import CaseSpec, GraderSpec, GradingOutput
from .validator import GRADER_RUNTIME_ERROR, HarnessError



def grade(case: CaseSpec, grader: GraderSpec, observation: Dict[str, Any]) -> GradingOutput:
    """Evaluate a normalized observation against a declarative grader spec."""
    try:
        hard_fail, hard_fail_notes = _evaluate_hard_fail_conditions(grader, observation)
        assertion_results = [_evaluate_spec(spec, observation) for spec in grader.assertions]
        dimension_scores = _evaluate_dimensions(grader, observation)

        notes = list(hard_fail_notes)
        notes.extend(result["message"] for result in assertion_results if result["message"])

        if hard_fail:
            return GradingOutput(
                final_status="fail",
                final_score=0.0,
                hard_fail=True,
                dimension_scores=dimension_scores,
                assertion_results=assertion_results,
                notes=notes,
                metadata={"grading_mode": grader.grading_mode},
            )

        if grader.grading_mode == "pass_fail":
            passed = _evaluate_pass_condition(
                assertion_results, grader.pass_condition
            )
            meta: Dict[str, Any] = {"grading_mode": grader.grading_mode}
            if grader.pass_condition != "all":
                meta["pass_condition"] = grader.pass_condition
            return GradingOutput(
                final_status="pass" if passed else "fail",
                final_score=1.0 if passed else 0.0,
                hard_fail=False,
                dimension_scores=dimension_scores,
                assertion_results=assertion_results,
                notes=notes,
                metadata=meta,
            )

        final_score = _weighted_sum(grader, dimension_scores)
        final_status = _score_to_status(final_score, grader.pass_threshold)

        return GradingOutput(
            final_status=final_status,
            final_score=final_score,
            hard_fail=False,
            dimension_scores=dimension_scores,
            assertion_results=assertion_results,
            notes=notes,
            metadata={
                "grading_mode": grader.grading_mode,
                "pass_threshold": grader.pass_threshold,
            },
        )
    except HarnessError:
        raise
    except Exception as exc:
        raise HarnessError(
            f"Grader runtime failed: {exc}",
            error_code=GRADER_RUNTIME_ERROR,
        ) from exc


def _evaluate_hard_fail_conditions(
    grader: GraderSpec,
    observation: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    notes: List[str] = []
    for condition in grader.hard_fail_conditions:
        result = _evaluate_spec(condition, observation)
        if result["passed"]:
            notes.append(f"Hard fail triggered: {result['type']}")
            return True, notes
    return False, notes


def _evaluate_dimensions(grader: GraderSpec, observation: Dict[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for index, dimension in enumerate(grader.dimensions):
        name = dimension.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HarnessError(
                f"Dimension at index {index} is missing a valid name",
                error_code=GRADER_RUNTIME_ERROR,
            )
        if name in scores:
            raise HarnessError(
                f"Duplicate dimension name detected at runtime: {name}",
                error_code=GRADER_RUNTIME_ERROR,
            )
        result = _evaluate_spec(dimension, observation)
        scores[name] = result["score"]
    return scores


def _evaluate_spec(spec: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
    spec_type = spec.get("type")
    expected = spec.get("expected")

    if spec_type == "status_equals":
        expected_value = _expect_non_empty_string(expected, spec_type)
        actual = observation.get("status")
        passed = actual == expected_value
        return _build_result(spec_type, passed, expected_value, actual)

    if spec_type == "layer_in":
        actual = observation.get("layer")
        expected_values = _expect_int_list(expected, spec_type)
        passed = actual in expected_values
        score = 1.0 if passed else 0.0
        return _build_result(
            spec_type,
            passed,
            expected_values,
            actual,
            score=score,
            message="" if passed else f"layer {actual} not in {expected_values}",
        )

    if spec_type == "result_not_empty":
        if expected not in (None, True):
            raise HarnessError(
                "result_not_empty only accepts expected=True when provided",
                error_code=GRADER_RUNTIME_ERROR,
            )
        actual = observation.get("result")
        passed = _result_not_empty(actual)
        return _build_result(
            spec_type,
            passed,
            True,
            actual,
            message="" if passed else "result is empty",
        )

    if spec_type == "result_type":
        expected_value = _expect_non_empty_string(expected, spec_type)
        actual = _infer_result_type(observation.get("result"))
        passed = actual == expected_value
        return _build_result(
            spec_type,
            passed,
            expected_value,
            actual,
            message="" if passed else f"expected result_type={expected_value}, got {actual}",
        )

    if spec_type == "contains_keywords":
        text = _to_text(observation.get("result"))
        expected_keywords = _expect_non_empty_string_list(expected, spec_type)
        matched = [keyword for keyword in expected_keywords if keyword in text]
        score = len(matched) / len(expected_keywords)
        passed = score >= 1.0
        missing = [keyword for keyword in expected_keywords if keyword not in matched]
        message = "" if passed else f"missing keywords: {', '.join(missing)}"
        return _build_result(
            spec_type,
            passed,
            expected_keywords,
            matched,
            score=score,
            message=message,
        )

    # ── Extended types (added for fixture expressiveness) ─────────────────────

    if spec_type == "exact_match":
        # Generic field equality check (generalisation of status_equals).
        config = spec.get("config", {})
        field = config.get("field", "")
        if not isinstance(field, str) or not field.strip():
            raise HarnessError(
                "exact_match requires config.field to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        expected_value = config.get("expected")
        actual = observation.get(field)
        passed = actual == expected_value
        return _build_result(
            spec_type,
            passed,
            expected_value,
            actual,
            message="" if passed else f"field '{field}': expected {expected_value!r}, got {actual!r}",
        )

    if spec_type == "non_empty":
        # Generic non-empty check on any observation field.
        config = spec.get("config", {})
        field = config.get("field", "result")
        if not isinstance(field, str) or not field.strip():
            raise HarnessError(
                "non_empty requires config.field to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        actual = observation.get(field)
        passed = _result_not_empty(actual)
        return _build_result(
            spec_type,
            passed,
            "<non-empty>",
            actual,
            message="" if passed else f"field '{field}' is empty or None",
        )

    if spec_type in ("threshold", "gte"):
        # Numeric field >= min_value.  'gte' is an alias for readability.
        config = spec.get("config", {})
        field = config.get("field", "")
        if not isinstance(field, str) or not field.strip():
            raise HarnessError(
                f"{spec_type} requires config.field to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        min_value = config.get("min_value")
        if min_value is None or not isinstance(min_value, (int, float)):
            raise HarnessError(
                f"{spec_type} requires config.min_value to be a number",
                error_code=GRADER_RUNTIME_ERROR,
            )
        actual = observation.get(field)
        try:
            actual_num = float(actual)
        except (TypeError, ValueError):
            return _build_result(
                spec_type,
                False,
                f">= {min_value}",
                actual,
                score=0.0,
                message=f"field '{field}' value {actual!r} is not numeric",
            )
        passed = actual_num >= float(min_value)
        # Proportional score: 0.0 if below threshold, scales up to 1.0 at threshold,
        # caps at 1.0 above threshold.
        score = min(1.0, actual_num / float(min_value)) if float(min_value) > 0 else (1.0 if passed else 0.0)
        return _build_result(
            spec_type,
            passed,
            f">= {min_value}",
            actual_num,
            score=score,
            message="" if passed else f"field '{field}': {actual_num} < {min_value}",
        )

    if spec_type == "contains_key":
        # Check that a dict field contains a specific key.
        config = spec.get("config", {})
        field = config.get("field", "")
        key = config.get("key", "")
        if not isinstance(field, str) or not field.strip():
            raise HarnessError(
                "contains_key requires config.field to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        if not isinstance(key, str) or not key.strip():
            raise HarnessError(
                "contains_key requires config.key to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        actual = observation.get(field)
        if isinstance(actual, dict):
            passed = key in actual
        else:
            passed = False
        return _build_result(
            spec_type,
            passed,
            f"key '{key}' present",
            list(actual.keys()) if isinstance(actual, dict) else actual,
            message="" if passed else f"field '{field}' does not contain key '{key}'",
        )

    if spec_type == "semantic_similarity":
        config = spec.get("config", {})
        field = config.get("field", "result")
        if not isinstance(field, str) or not field.strip():
            raise HarnessError(
                "semantic_similarity requires config.field to be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
        if "reference" not in config:
            raise HarnessError(
                "semantic_similarity requires config.reference",
                error_code=GRADER_RUNTIME_ERROR,
            )
        reference = config.get("reference")
        if reference is None or (isinstance(reference, str) and not reference.strip()):
            raise HarnessError(
                "semantic_similarity requires config.reference to be non-empty",
                error_code=GRADER_RUNTIME_ERROR,
            )

        min_similarity = config.get("min_similarity")
        if min_similarity is None or isinstance(min_similarity, bool) or not isinstance(min_similarity, (int, float)):
            raise HarnessError(
                "semantic_similarity requires config.min_similarity to be a number",
                error_code=GRADER_RUNTIME_ERROR,
            )
        min_similarity = float(min_similarity)
        if not 0.0 <= min_similarity <= 1.0:
            raise HarnessError(
                "semantic_similarity requires config.min_similarity between 0.0 and 1.0",
                error_code=GRADER_RUNTIME_ERROR,
            )

        method = config.get("method", "sequence_matcher")
        if not isinstance(method, str) or method not in SUPPORTED_SEMANTIC_METHODS:
            raise HarnessError(
                f"semantic_similarity method must be one of {sorted(SUPPORTED_SEMANTIC_METHODS)}",
                error_code=GRADER_RUNTIME_ERROR,
            )

        case_sensitive = config.get("case_sensitive", False)
        if not isinstance(case_sensitive, bool):
            raise HarnessError(
                "semantic_similarity config.case_sensitive must be a boolean",
                error_code=GRADER_RUNTIME_ERROR,
            )
        normalize_whitespace = config.get("normalize_whitespace", True)
        if not isinstance(normalize_whitespace, bool):
            raise HarnessError(
                "semantic_similarity config.normalize_whitespace must be a boolean",
                error_code=GRADER_RUNTIME_ERROR,
            )

        model_name = config.get("model_name", DEFAULT_SENTENCE_TRANSFORMER_MODEL)
        if not isinstance(model_name, str) or not model_name.strip():
            raise HarnessError(
                "semantic_similarity config.model_name must be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )

        actual = observation.get(field)
        similarity = compute_semantic_similarity(
            actual,
            reference,
            method=method,
            case_sensitive=case_sensitive,
            normalize_whitespace=normalize_whitespace,
            model_name=model_name,
        )
        passed = similarity >= min_similarity
        expected_payload: Dict[str, Any] = {
            "reference": reference,
            "min_similarity": min_similarity,
            "method": method,
        }
        if method == "sentence_transformers":
            expected_payload["model_name"] = model_name

        actual_payload: Dict[str, Any] = {
            "field": field,
            "value": actual,
            "similarity": similarity,
        }
        return _build_result(
            spec_type,
            passed,
            expected_payload,
            actual_payload,
            score=similarity,
            message=(
                "" if passed else f"field '{field}' similarity {similarity:.4f} < {min_similarity:.4f}"
            ),
        )

    raise HarnessError(

        f"Unsupported grader spec type: {spec_type}",
        error_code=GRADER_RUNTIME_ERROR,
    )


def _build_result(
    spec_type: str,
    passed: bool,
    expected: Any,
    actual: Any,
    *,
    score: Optional[float] = None,
    message: str = "",
) -> Dict[str, Any]:
    return {
        "type": spec_type,
        "passed": passed,
        "expected": expected,
        "actual": actual,
        "score": 1.0 if score is None and passed else 0.0 if score is None else round(score, 4),
        "message": message,
    }


def _result_not_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _infer_result_type(value: Any) -> str:
    if isinstance(value, str):
        return "text"
    if isinstance(value, dict):
        return "json"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "empty"
    return type(value).__name__.lower()


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _expect_non_empty_string(value: Any, spec_type: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessError(
            f"{spec_type} requires a non-empty string expected value",
            error_code=GRADER_RUNTIME_ERROR,
        )
    return value


def _expect_non_empty_string_list(value: Any, spec_type: str) -> List[str]:
    if not isinstance(value, list) or not value:
        raise HarnessError(
            f"{spec_type} requires a non-empty list of strings",
            error_code=GRADER_RUNTIME_ERROR,
        )
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise HarnessError(
                f"{spec_type} expected[{index}] must be a non-empty string",
                error_code=GRADER_RUNTIME_ERROR,
            )
    return value


def _expect_int_list(value: Any, spec_type: str) -> List[int]:
    if not isinstance(value, list) or not value:
        raise HarnessError(
            f"{spec_type} requires a non-empty list of integers",
            error_code=GRADER_RUNTIME_ERROR,
        )
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise HarnessError(
                f"{spec_type} expected[{index}] must be an integer",
                error_code=GRADER_RUNTIME_ERROR,
            )
    return value


def _weighted_sum(grader: GraderSpec, dimension_scores: Dict[str, float]) -> float:
    if not grader.dimensions:
        return 0.0

    total_weight = sum(float(dimension["weight"]) for dimension in grader.dimensions)
    if total_weight <= 0:
        return 0.0

    weighted_score = 0.0
    for dimension in grader.dimensions:
        name = dimension["name"]
        weight = float(dimension["weight"])
        if name not in dimension_scores:
            raise HarnessError(
                f"Missing dimension score for {name}",
                error_code=GRADER_RUNTIME_ERROR,
            )
        weighted_score += dimension_scores[name] * weight

    return round(weighted_score / total_weight, 4)


def _score_to_status(score: float, pass_threshold: float) -> str:
    if score >= pass_threshold:
        return "pass"
    if score > 0:
        return "partial"
    return "fail"


def _evaluate_pass_condition(
    assertion_results: List[Dict[str, Any]],
    pass_condition: str,
) -> bool:
    """Evaluate the aggregation condition for pass_fail grading mode.

    Supported values:
    - ``"all"`` (default): every assertion must pass (AND semantics).
    - ``"any"``: at least one assertion must pass (OR semantics).
    - ``"at_least_N"`` where N is a positive integer: at least N assertions
      must pass.  E.g. ``"at_least_2"`` requires >= 2 passing assertions.
    """
    results = [r["passed"] for r in assertion_results]
    if not results:
        return False

    if pass_condition == "all":
        return all(results)

    if pass_condition == "any":
        return any(results)

    if pass_condition.startswith("at_least_"):
        try:
            n = int(pass_condition[len("at_least_"):])
        except ValueError:
            raise HarnessError(
                f"Invalid pass_condition '{pass_condition}': "
                "expected 'at_least_<positive_int>'",
                error_code=GRADER_RUNTIME_ERROR,
            )
        if n <= 0:
            raise HarnessError(
                f"Invalid pass_condition '{pass_condition}': N must be a positive integer",
                error_code=GRADER_RUNTIME_ERROR,
            )
        return sum(results) >= n

    raise HarnessError(
        f"Unsupported pass_condition '{pass_condition}': "
        "expected 'all', 'any', or 'at_least_N'",
        error_code=GRADER_RUNTIME_ERROR,
    )


__all__ = ["grade"]
