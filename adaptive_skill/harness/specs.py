"""Single-case harness contracts for Adaptive Skill System.

P0 focus: stabilize the single-run evaluation contract before batch runner,
metrics, regression, or reporting layers are added.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_GRADING_MODES = {"pass_fail", "scored", "hybrid"}
ALLOWED_FINAL_STATUSES = {"pass", "partial", "fail", "error"}
ALLOWED_EXECUTION_STATUSES = {"success", "partial", "failed", "error"}


@dataclass
class CaseSpec:
    """Stable description of a single benchmark case."""

    case_id: str
    title: str
    description: str
    task_type: str
    input_payload: Dict[str, Any]
    expected_outcome_type: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    grader_ref: str = ""
    expected_layer: Optional[List[int]] = None
    difficulty: str = "unknown"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def problem(self) -> str:
        """Return the canonical problem string consumed by AdaptiveSkillSystem."""
        value = self.input_payload.get("problem", "")
        return value if isinstance(value, str) else str(value)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraderSpec:
    """Declarative grading contract for a case."""

    grader_id: str
    name: str
    grading_mode: str
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    dimensions: List[Dict[str, Any]] = field(default_factory=list)
    pass_threshold: float = 1.0
    hard_fail_conditions: List[Dict[str, Any]] = field(default_factory=list)
    aggregation_rule: str = "weighted_sum"
    # pass_condition controls how assertion results are aggregated in pass_fail mode.
    # Values: "all" (default, AND), "any" (OR), "at_least_N" (e.g. "at_least_2").
    pass_condition: str = "all"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GradingOutput:
    """Normalized output from the harness grader runtime."""

    final_status: str
    final_score: float
    hard_fail: bool = False
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    assertion_results: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    """Final artifact emitted by one standardized case run."""

    run_id: str
    case_id: str
    grader_id: str
    system_version: str
    started_at: str
    ended_at: str
    duration_ms: float
    execution_status: str
    final_status: str
    final_score: float
    solve_response: Dict[str, Any]
    execution_trace_summary: Dict[str, Any]
    decision_trace: List[Dict[str, Any]] = field(default_factory=list)
    grader_scores: Dict[str, float] = field(default_factory=dict)
    failure_reason: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = [
    "ALLOWED_GRADING_MODES",
    "ALLOWED_FINAL_STATUSES",
    "ALLOWED_EXECUTION_STATUSES",
    "CaseSpec",
    "GraderSpec",
    "GradingOutput",
    "RunResult",
]
