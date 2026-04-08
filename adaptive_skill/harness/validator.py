"""Validation and error boundaries for the single-case harness."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .semantic_grader import SUPPORTED_SEMANTIC_METHODS
from .specs import CaseSpec, GraderSpec


CASE_INVALID = "CASE_INVALID"
GRADER_INVALID = "GRADER_INVALID"
CASE_GRADER_MISMATCH = "CASE_GRADER_MISMATCH"
SOLVER_EXECUTION_FAILED = "SOLVER_EXECUTION_FAILED"
GRADER_RUNTIME_ERROR = "GRADER_RUNTIME_ERROR"
RESULT_PERSIST_FAILED = "RESULT_PERSIST_FAILED"
HARNESS_RUNTIME_ERROR = "HARNESS_RUNTIME_ERROR"

SUPPORTED_ASSERTION_TYPES = {
    # Original types (P0)
    "status_equals",
    "layer_in",
    "result_not_empty",
    "result_type",
    "contains_keywords",
    # Extended types (P1 fixtures)
    "exact_match",         # generic field == expected via config.field / config.expected
    "non_empty",           # generic non-empty check via config.field
    "threshold",           # field >= min_value via config.field / config.min_value
    "gte",                 # alias for threshold
    "contains_key",        # dict field contains key via config.field / config.key
    "semantic_similarity", # field ~ reference via config.field / config.reference / config.min_similarity
}

SUPPORTED_GRADING_MODES = {"pass_fail", "scored", "hybrid"}
SUPPORTED_AGGREGATION_RULES = {"weighted_sum"}


class HarnessError(Exception):
    """Base error type for harness failures."""

    default_error_code = HARNESS_RUNTIME_ERROR

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code or self.default_error_code


class HarnessValidationError(HarnessError):
    default_error_code = CASE_INVALID


class GraderValidationError(HarnessError):
    default_error_code = GRADER_INVALID


class BindingValidationError(HarnessError):
    default_error_code = CASE_GRADER_MISMATCH


class PersistenceError(HarnessError):
    default_error_code = RESULT_PERSIST_FAILED


def validate_case(case: CaseSpec) -> None:
    _require_non_empty(case.case_id, "case.case_id", HarnessValidationError)
    _require_non_empty(case.title, "case.title", HarnessValidationError)
    _require_non_empty(case.description, "case.description", HarnessValidationError)
    _require_non_empty(case.task_type, "case.task_type", HarnessValidationError)
    _require_non_empty(case.expected_outcome_type, "case.expected_outcome_type", HarnessValidationError)
    # grader_ref is optional: when provided it must be non-empty; when absent, binding is skipped.
    if case.grader_ref and not case.grader_ref.strip():
        raise HarnessValidationError("case.grader_ref must not be an empty/blank string when provided")

    if not isinstance(case.input_payload, dict):
        raise HarnessValidationError("case.input_payload must be a dict")

    if "problem" not in case.input_payload:
        raise HarnessValidationError("case.input_payload must contain a 'problem' field")

    if not isinstance(case.input_payload["problem"], str) or not case.input_payload["problem"].strip():
        raise HarnessValidationError("case.input_payload['problem'] must be a non-empty string")

    if case.expected_layer is not None:
        _require_non_empty_int_list(
            case.expected_layer,
            "case.expected_layer",
            HarnessValidationError,
        )


def validate_grader(grader: GraderSpec) -> None:
    _require_non_empty(grader.grader_id, "grader.grader_id", GraderValidationError)
    _require_non_empty(grader.name, "grader.name", GraderValidationError)

    if grader.grading_mode not in SUPPORTED_GRADING_MODES:
        raise GraderValidationError(
            f"grader.grading_mode must be one of {sorted(SUPPORTED_GRADING_MODES)}"
        )

    if grader.aggregation_rule not in SUPPORTED_AGGREGATION_RULES:
        raise GraderValidationError(
            f"grader.aggregation_rule must be one of {sorted(SUPPORTED_AGGREGATION_RULES)}"
        )

    if isinstance(grader.pass_threshold, bool) or not isinstance(grader.pass_threshold, (int, float)):
        raise GraderValidationError("grader.pass_threshold must be a number")
    if not 0.0 <= grader.pass_threshold <= 1.0:
        raise GraderValidationError("grader.pass_threshold must be between 0.0 and 1.0")

    _validate_specs(grader.assertions, label="grader.assertions")
    _validate_specs(grader.hard_fail_conditions, label="grader.hard_fail_conditions")
    _validate_dimensions(grader.dimensions)

    if grader.grading_mode == "pass_fail" and not grader.assertions:
        raise GraderValidationError("pass_fail grader requires at least one assertion")

    if grader.grading_mode == "pass_fail":
        _validate_pass_condition(grader.pass_condition, len(grader.assertions))

    if grader.grading_mode in {"scored", "hybrid"} and not grader.dimensions:
        raise GraderValidationError(
            f"{grader.grading_mode} grader requires at least one dimension"
        )


def validate_binding(case: CaseSpec, grader: GraderSpec) -> None:
    # Only enforce grader_ref ↔ grader_id match when grader_ref is explicitly set.
    if case.grader_ref and case.grader_ref != grader.grader_id:
        raise BindingValidationError(
            f"case.grader_ref='{case.grader_ref}' does not match grader.grader_id='{grader.grader_id}'"
        )

    result_type_assertions = [
        spec for spec in _iter_all_specs(grader) if spec.get("type") == "result_type"
    ]
    for spec in result_type_assertions:
        expected = spec.get("expected")
        if expected and expected != case.expected_outcome_type:
            raise BindingValidationError(
                "case.expected_outcome_type conflicts with grader result_type expectation"
            )

    layer_specs = [spec for spec in _iter_all_specs(grader) if spec.get("type") == "layer_in"]
    if case.expected_layer and layer_specs:
        for spec in layer_specs:
            expected_layers = spec.get("expected") or []
            if not set(case.expected_layer) & set(expected_layers):
                raise BindingValidationError(
                    "case.expected_layer does not overlap with grader layer_in expectation"
                )


def _validate_specs(specs: List[Dict[str, Any]], *, label: str) -> None:
    if not isinstance(specs, list):
        raise GraderValidationError(f"{label} must be a list")

    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise GraderValidationError(f"{label}[{index}] must be a dict")
        _validate_spec_shape(spec, label=f"{label}[{index}]")


def _validate_dimensions(dimensions: List[Dict[str, Any]]) -> None:
    if not isinstance(dimensions, list):
        raise GraderValidationError("grader.dimensions must be a list")

    total_weight = 0.0
    seen_names = set()
    for index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise GraderValidationError(f"grader.dimensions[{index}] must be a dict")

        name = dimension.get("name")
        _require_non_empty(name, f"grader.dimensions[{index}].name", GraderValidationError)
        if name in seen_names:
            raise GraderValidationError(
                f"grader.dimensions[{index}].name duplicates an earlier dimension: {name}"
            )
        seen_names.add(name)

        dim_type = dimension.get("type")
        if dim_type not in SUPPORTED_ASSERTION_TYPES:
            raise GraderValidationError(
                f"grader.dimensions[{index}].type must be one of {sorted(SUPPORTED_ASSERTION_TYPES)}"
            )

        weight = dimension.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise GraderValidationError(
                f"grader.dimensions[{index}].weight must be a positive number"
            )
        total_weight += float(weight)

        _validate_spec_shape(dimension, label=f"grader.dimensions[{index}]")

    if dimensions and total_weight <= 0:
        raise GraderValidationError("grader.dimensions total weight must be positive")


def _validate_spec_shape(spec: Dict[str, Any], *, label: str) -> None:
    spec_type = spec.get("type")
    if spec_type not in SUPPORTED_ASSERTION_TYPES:
        raise GraderValidationError(
            f"{label}.type must be one of {sorted(SUPPORTED_ASSERTION_TYPES)}"
        )

    expected_label = f"{label}.expected"
    if spec_type == "status_equals":
        _require_non_empty(spec.get("expected"), expected_label, GraderValidationError)
        return

    if spec_type == "layer_in":
        _require_non_empty_int_list(spec.get("expected"), expected_label, GraderValidationError)
        return

    if spec_type == "result_not_empty":
        if "expected" in spec and spec.get("expected") is not True:
            raise GraderValidationError(f"{expected_label} must be True when provided")
        return

    if spec_type == "result_type":
        _require_non_empty(spec.get("expected"), expected_label, GraderValidationError)
        return

    if spec_type == "contains_keywords":
        _require_non_empty_string_list(spec.get("expected"), expected_label, GraderValidationError)
        return

    # ── Extended types (P1 fixtures) ──────────────────────────────────────────

    if spec_type == "exact_match":
        config = spec.get("config") or {}
        _require_non_empty(config.get("field"), f"{label}.config.field", GraderValidationError)
        if "expected" not in config:
            raise GraderValidationError(f"{label}.config.expected is required for exact_match")
        return

    if spec_type == "non_empty":
        config = spec.get("config") or {}
        _require_non_empty(config.get("field"), f"{label}.config.field", GraderValidationError)
        return

    if spec_type in ("threshold", "gte"):
        config = spec.get("config") or {}
        _require_non_empty(config.get("field"), f"{label}.config.field", GraderValidationError)
        min_value = config.get("min_value")
        if min_value is None or isinstance(min_value, bool) or not isinstance(min_value, (int, float)):
            raise GraderValidationError(
                f"{label}.config.min_value must be a number for {spec_type}"
            )
        return

    if spec_type == "contains_key":
        config = spec.get("config") or {}
        _require_non_empty(config.get("field"), f"{label}.config.field", GraderValidationError)
        _require_non_empty(config.get("key"), f"{label}.config.key", GraderValidationError)
        return

    if spec_type == "semantic_similarity":
        config = spec.get("config") or {}
        _require_non_empty(config.get("field"), f"{label}.config.field", GraderValidationError)
        if "reference" not in config:
            raise GraderValidationError(f"{label}.config.reference is required for semantic_similarity")
        reference = config.get("reference")
        if reference is None or (isinstance(reference, str) and not reference.strip()):
            raise GraderValidationError(
                f"{label}.config.reference must be a non-empty value for semantic_similarity"
            )
        min_similarity = config.get("min_similarity")
        if min_similarity is None or isinstance(min_similarity, bool) or not isinstance(min_similarity, (int, float)):
            raise GraderValidationError(
                f"{label}.config.min_similarity must be a number for semantic_similarity"
            )
        if not 0.0 <= float(min_similarity) <= 1.0:
            raise GraderValidationError(
                f"{label}.config.min_similarity must be between 0.0 and 1.0"
            )

        method = config.get("method", "sequence_matcher")
        if not isinstance(method, str) or method not in SUPPORTED_SEMANTIC_METHODS:
            raise GraderValidationError(
                f"{label}.config.method must be one of {sorted(SUPPORTED_SEMANTIC_METHODS)}"
            )

        for flag in ("case_sensitive", "normalize_whitespace"):
            value = config.get(flag)
            if value is not None and not isinstance(value, bool):
                raise GraderValidationError(f"{label}.config.{flag} must be a boolean when provided")

        model_name = config.get("model_name")
        if model_name is not None and (not isinstance(model_name, str) or not model_name.strip()):
            raise GraderValidationError(
                f"{label}.config.model_name must be a non-empty string when provided"
            )
        return





def _iter_all_specs(grader: GraderSpec):
    yield from grader.assertions
    yield from grader.dimensions
    yield from grader.hard_fail_conditions


def _require_non_empty(value: Any, label: str, error_cls) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_cls(f"{label} must be a non-empty string")


def _require_non_empty_string_list(value: Any, label: str, error_cls) -> None:
    if not isinstance(value, list) or not value:
        raise error_cls(f"{label} must be a non-empty list of strings")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise error_cls(f"{label}[{index}] must be a non-empty string")


def _require_non_empty_int_list(value: Any, label: str, error_cls) -> None:
    if not isinstance(value, list) or not value:
        raise error_cls(f"{label} must be a non-empty list of integers")
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise error_cls(f"{label}[{index}] must be an integer")


def _validate_pass_condition(pass_condition: str, assertion_count: int) -> None:
    """Validate the pass_condition field for pass_fail graders."""
    if pass_condition in ("all", "any"):
        return

    if pass_condition.startswith("at_least_"):
        suffix = pass_condition[len("at_least_"):]
        try:
            n = int(suffix)
        except ValueError:
            raise GraderValidationError(
                f"grader.pass_condition '{pass_condition}' is invalid: "
                "expected 'at_least_<positive_int>'"
            )
        if n <= 0:
            raise GraderValidationError(
                f"grader.pass_condition '{pass_condition}' is invalid: N must be a positive integer"
            )
        if n > assertion_count:
            raise GraderValidationError(
                f"grader.pass_condition '{pass_condition}' requires {n} assertions "
                f"but only {assertion_count} are defined"
            )
        return

    raise GraderValidationError(
        f"grader.pass_condition '{pass_condition}' is not supported; "
        "expected 'all', 'any', or 'at_least_N'"
    )


__all__ = [
    "CASE_INVALID",
    "GRADER_INVALID",
    "CASE_GRADER_MISMATCH",
    "SOLVER_EXECUTION_FAILED",
    "GRADER_RUNTIME_ERROR",
    "RESULT_PERSIST_FAILED",
    "HARNESS_RUNTIME_ERROR",
    "SUPPORTED_ASSERTION_TYPES",
    "SUPPORTED_GRADING_MODES",
    "SUPPORTED_AGGREGATION_RULES",
    "HarnessError",
    "HarnessValidationError",
    "GraderValidationError",
    "BindingValidationError",
    "PersistenceError",
    "validate_case",
    "validate_grader",
    "validate_binding",
]
