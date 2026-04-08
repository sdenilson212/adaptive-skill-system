"""Single-case harness execution shell for Adaptive Skill System."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from ..core import AdaptiveSkillSystem, SolveResponse
from ..protocols import ExecutionResult as ProtocolExecutionResult, execution_result_from_solve_response


from .grader_runtime import grade

from .specs import CaseSpec, GraderSpec, GradingOutput, RunResult
from .validator import (
    HARNESS_RUNTIME_ERROR,
    SOLVER_EXECUTION_FAILED,
    HarnessError,
    PersistenceError,
    validate_binding,
    validate_case,
    validate_grader,
)


class ResultStoreProtocol(Protocol):
    """Minimal persistence hook used by the P0 shell."""

    def persist(self, run_result: RunResult) -> None:
        ...


def _maybe_persist(
    run_result: RunResult,
    *,
    persist: bool,
    result_store: Optional[ResultStoreProtocol],
) -> RunResult:
    """Persist run_result if requested; return it unconditionally."""
    if persist:
        if result_store is None:
            raise PersistenceError("persist=True requires result_store to be provided")
        try:
            result_store.persist(run_result)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Failed to persist RunResult: {exc}") from exc
    return run_result


def run_case(
    case: CaseSpec,
    system: AdaptiveSkillSystem,
    grader: GraderSpec,
    *,
    system_version: str,
    persist: bool = False,
    result_store: Optional[ResultStoreProtocol] = None,
) -> RunResult:
    """Run one case end-to-end through validate -> solve -> grade -> assemble."""
    started_at = now_iso()
    wall_clock_start = time.perf_counter()
    response: Optional[SolveResponse] = None
    observation: Dict[str, Any] = {}
    decision_trace: list[Dict[str, Any]] = []

    try:
        validate_case(case)
        validate_grader(grader)
        validate_binding(case, grader)

        response = system.solve(problem=case.problem, verbose=False)
        protocol_result = _build_protocol_result(case, response)
        observation = protocol_result.to_observation(case_id=case.case_id)
        decision_trace = _extract_decision_trace(protocol_result)

        if response.status == "failed":
            failure_reason = _extract_failure_reason(response)
            error_run_result = build_error_run_result(
                case=case,
                grader=grader,
                system_version=system_version,
                started_at=started_at,
                wall_clock_start=wall_clock_start,
                execution_status=response.status,
                failure_reason=failure_reason,
                error_code=SOLVER_EXECUTION_FAILED,
                response=response,
                observation=observation,
                decision_trace=decision_trace,
                final_status="fail",
            )

            return _maybe_persist(error_run_result, persist=persist, result_store=result_store)

        # NOTE: response.status == "partial" (Layer 3 quality < 0.75) falls through
        # to the normal grade() path below.  This is intentional: the system produced
        # a real result, just with lower confidence.  The observation dict carries
        # status="partial" so graders can apply dimension-level penalties if needed.
        # The execution_trace_summary also surfaces confidence for grader inspection.

        grading = grade(case, grader, observation)
        run_result = assemble_run_result(
            case=case,
            grader=grader,
            response=response,
            observation=observation,
            decision_trace=decision_trace,
            grading=grading,
            system_version=system_version,
            started_at=started_at,
            wall_clock_start=wall_clock_start,
        )

        return _maybe_persist(run_result, persist=persist, result_store=result_store)

    except HarnessError as exc:
        execution_status = response.status if response is not None else "error"
        error_run_result = build_error_run_result(
            case=case,
            grader=grader,
            system_version=system_version,
            started_at=started_at,
            wall_clock_start=wall_clock_start,
            execution_status=execution_status,
            failure_reason=str(exc),
            error_code=exc.error_code,
            response=response,
            observation=observation,
            decision_trace=decision_trace,
            final_status="error" if exc.error_code != SOLVER_EXECUTION_FAILED else "fail",
        )

        return _maybe_persist(error_run_result, persist=persist, result_store=result_store)
    except Exception as exc:
        execution_status = response.status if response is not None else "error"
        error_run_result = build_error_run_result(
            case=case,
            grader=grader,
            system_version=system_version,
            started_at=started_at,
            wall_clock_start=wall_clock_start,
            execution_status=execution_status,
            failure_reason=str(exc),
            error_code=HARNESS_RUNTIME_ERROR,
            response=response,
            observation=observation,
            decision_trace=decision_trace,
            final_status="error",
        )

        return _maybe_persist(error_run_result, persist=persist, result_store=result_store)


def _build_protocol_result(case: CaseSpec, response: SolveResponse) -> ProtocolExecutionResult:
    """Adapt SolveResponse once so harness layers can reuse observation + evidence."""
    return execution_result_from_solve_response(
        response,
        task_id=case.case_id,
        trace_id=str(case.metadata.get("trace_id", case.case_id)),
        run_id=str(case.metadata.get("run_id", f"run-{case.case_id}")),
    )



def _extract_decision_trace(protocol_result: ProtocolExecutionResult) -> list[Dict[str, Any]]:
    """Normalize protocol evidence into a stable list of decision-trace dicts."""
    raw_trace = protocol_result.evidence.get("decision_trace", [])
    if not isinstance(raw_trace, list):
        return []
    return [item for item in raw_trace if isinstance(item, dict)]



def normalize_response(case: CaseSpec, response: SolveResponse) -> Dict[str, Any]:
    """Project SolveResponse into a stable grader-facing observation."""
    protocol_result = _build_protocol_result(case, response)
    return protocol_result.to_observation(case_id=case.case_id)



def _extract_runtime_metrics(

    response: Optional[SolveResponse],
    observation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Copy optional runtime counters and Layer 3 retry telemetry from metadata."""
    metric_keys = {
        "attempt_count",
        "retry_count",
        "fallback_count",
        "framework_fallback_count",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost",
        "cost",
        "cost_usd",
        "generation_attempts",
        "generation_info",
    }

    merged: Dict[str, Any] = {}

    candidate_sources = []
    if response is not None and isinstance(response.metadata, dict):
        candidate_sources.append(response.metadata)
    if isinstance(observation, dict):
        observation_metadata = observation.get("metadata")
        if isinstance(observation_metadata, dict):
            candidate_sources.append(observation_metadata)

    for source in candidate_sources:
        for key in metric_keys:
            if key in source and key not in merged:
                merged[key] = source[key]

    if "estimated_cost" not in merged:
        if "cost" in merged:
            merged["estimated_cost"] = merged.pop("cost")
        elif "cost_usd" in merged:
            merged["estimated_cost"] = merged.pop("cost_usd")

    if "fallback_count" not in merged and "framework_fallback_count" in merged:
        merged["fallback_count"] = merged["framework_fallback_count"]

    if "total_tokens" not in merged:
        prompt_tokens = merged.get("prompt_tokens")
        completion_tokens = merged.get("completion_tokens")
        if isinstance(prompt_tokens, (int, float)) or isinstance(completion_tokens, (int, float)):
            merged["total_tokens"] = int(prompt_tokens or 0) + int(completion_tokens or 0)

    return merged


def assemble_run_result(
    *,
    case: CaseSpec,
    grader: GraderSpec,
    response: SolveResponse,
    observation: Dict[str, Any],
    decision_trace: list[Dict[str, Any]],
    grading: GradingOutput,
    system_version: str,
    started_at: str,
    wall_clock_start: float,
) -> RunResult:

    """Assemble the final run artifact after a successful grading pass."""
    ended_at = now_iso()
    duration_ms = elapsed_ms(wall_clock_start)
    runtime_metrics = _extract_runtime_metrics(response, observation)
    return RunResult(
        run_id=build_run_id(),
        case_id=case.case_id,
        grader_id=grader.grader_id,
        system_version=system_version,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        execution_status=response.status,
        final_status=grading.final_status,
        final_score=grading.final_score,
        solve_response=response.to_dict(),
        execution_trace_summary=observation,
        decision_trace=list(decision_trace or []),
        grader_scores=grading.dimension_scores,

        failure_reason=None,
        error_code=None,
        metadata={
            "harness_version": "p0",
            "hard_fail": grading.hard_fail,
            "grading_notes": grading.notes,
            "assertion_results": grading.assertion_results,
            "grading_metadata": grading.metadata,
            "duration_source": "harness_wall_clock_ms",
            "solve_duration_ms": response.execution_time_ms,
            **runtime_metrics,
        },
    )


def build_error_run_result(
    *,
    case: CaseSpec,
    grader: GraderSpec,
    system_version: str,
    started_at: str,
    wall_clock_start: float,
    execution_status: str,
    failure_reason: str,
    error_code: str,
    response: Optional[SolveResponse] = None,
    observation: Optional[Dict[str, Any]] = None,
    decision_trace: Optional[list[Dict[str, Any]]] = None,
    final_status: str = "error",
) -> RunResult:

    """Build a stable RunResult even when validation, solve, grading, or persistence fails."""
    ended_at = now_iso()
    duration_ms = elapsed_ms(wall_clock_start)
    metadata = {
        "harness_version": "p0",
        "duration_source": "harness_wall_clock_ms",
        **_extract_runtime_metrics(response, observation),
    }
    if response is not None:
        metadata["solve_duration_ms"] = response.execution_time_ms

    return RunResult(
        run_id=build_run_id(),
        case_id=getattr(case, "case_id", "unknown-case") or "unknown-case",
        grader_id=getattr(grader, "grader_id", "unknown-grader") or "unknown-grader",
        system_version=system_version,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        execution_status=execution_status,
        final_status=final_status,
        final_score=0.0,
        solve_response=response.to_dict() if response is not None else {},
        execution_trace_summary=observation or {},
        decision_trace=list(decision_trace or []),
        grader_scores={},

        failure_reason=failure_reason,
        error_code=error_code,
        metadata=metadata,
    )


def build_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_ms(wall_clock_start: float) -> float:
    return round((time.perf_counter() - wall_clock_start) * 1000, 3)


def _extract_failure_reason(response: SolveResponse) -> str:
    reason = response.metadata.get("reason") if isinstance(response.metadata, dict) else None
    if reason:
        return str(reason)
    return "AdaptiveSkillSystem returned status='failed'"


__all__ = [
    "ResultStoreProtocol",
    "run_case",
    "normalize_response",
    "assemble_run_result",
    "build_error_run_result",
    "build_run_id",
    "now_iso",
    "elapsed_ms",
]
