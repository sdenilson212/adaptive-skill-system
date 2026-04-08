"""Batch Runner for Adaptive Skill System harness.

P2 layer: drives multiple CaseSpec + GraderSpec pairs through run_case()
and aggregates them into a BatchResult with per-case RunResult records.

Design decisions
----------------
* Sequential by default — avoids GIL / thread-safety concerns with the
  AdaptiveSkillSystem (which holds in-memory state).  Parallel mode is opt-in
  via ``max_workers > 1`` and uses concurrent.futures.ThreadPoolExecutor.
* Fail-fast is opt-in (``fail_fast=True``): by default all cases run even when
  individual ones error, so the aggregate gives a full picture.
* Persistence is injected: BatchRunner accepts an optional ResultStoreProtocol
  that receives each RunResult as it completes (same interface as single_case).
* BatchResult is the single serialisable artefact; its ``summary`` property
  provides quick human-readable stats.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core import AdaptiveSkillSystem
from .single_case import ResultStoreProtocol, run_case
from .specs import CaseSpec, GraderSpec, RunResult


# ── Public types ──────────────────────────────────────────────────────────────

@dataclass
class BatchJob:
    """A single (case, grader) pair to run inside a batch."""

    case: CaseSpec
    grader: GraderSpec

    def validate(self) -> None:
        """Light sanity-check — full validation happens inside run_case()."""
        if not self.case or not self.grader:
            raise ValueError("BatchJob requires both case and grader to be set")


@dataclass
class BatchSummary:
    """Aggregate statistics over a completed batch run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    partial: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    avg_duration_ms: float = 0.0
    hard_fail_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "partial": self.partial,
            "pass_rate": round(self.pass_rate, 4),
            "avg_score": round(self.avg_score, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "hard_fail_count": self.hard_fail_count,
        }


@dataclass
class BatchResult:
    """Full output of a batch run — one record per job."""

    batch_id: str
    system_version: str
    started_at: str
    ended_at: str
    duration_ms: float
    summary: BatchSummary
    results: List[RunResult] = field(default_factory=list)
    # Any jobs that raised an unexpected exception (not covered by run_case's
    # own error handling).
    runner_errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "system_version": self.system_version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": round(self.duration_ms, 2),
            "summary": self.summary.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "runner_errors": self.runner_errors,
            "metadata": self.metadata,
        }

    @property
    def passed(self) -> List[RunResult]:
        return [r for r in self.results if r.final_status == "pass"]

    @property
    def failed(self) -> List[RunResult]:
        return [r for r in self.results if r.final_status in ("fail", "partial")]

    @property
    def errored(self) -> List[RunResult]:
        return [r for r in self.results if r.final_status == "error"]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_summary(results: List[RunResult]) -> BatchSummary:
    total = len(results)
    if total == 0:
        return BatchSummary(total=0)

    passed = sum(1 for r in results if r.final_status == "pass")
    failed = sum(1 for r in results if r.final_status == "fail")
    errored = sum(1 for r in results if r.final_status == "error")
    partial = sum(1 for r in results if r.final_status == "partial")
    hard_fails = sum(
        1 for r in results
        if r.metadata.get("hard_fail") is True
    )
    scores = [r.final_score for r in results]
    durations = [r.duration_ms for r in results]

    return BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        partial=partial,
        pass_rate=passed / total,
        avg_score=sum(scores) / total,
        avg_duration_ms=sum(durations) / total,
        hard_fail_count=hard_fails,
    )


def _run_one(
    job: BatchJob,
    system: AdaptiveSkillSystem,
    system_version: str,
    result_store: Optional[ResultStoreProtocol],
) -> Tuple[RunResult, Optional[Dict[str, Any]]]:
    """Execute a single job.  Returns (result, runner_error_or_None)."""
    try:
        result = run_case(
            case=job.case,
            system=system,
            grader=job.grader,
            system_version=system_version,
            result_store=result_store,
            persist=result_store is not None,
        )
        return result, None
    except Exception as exc:  # noqa: BLE001
        # run_case already tries to catch everything; this is the last safety net.
        error_record: Dict[str, Any] = {
            "case_id": getattr(job.case, "case_id", "unknown"),
            "grader_id": getattr(job.grader, "grader_id", "unknown"),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "timestamp": _now_iso(),
        }
        # Synthesise a minimal RunResult so callers can still iterate results.
        minimal = RunResult(
            run_id=str(uuid.uuid4()),
            case_id=getattr(job.case, "case_id", "unknown"),
            grader_id=getattr(job.grader, "grader_id", "unknown"),
            system_version=system_version,
            started_at=_now_iso(),
            ended_at=_now_iso(),
            duration_ms=0.0,
            execution_status="error",
            final_status="error",
            final_score=0.0,
            solve_response={},
            execution_trace_summary={},
            failure_reason=str(exc),
            error_code="BATCH_RUNNER_UNHANDLED_EXCEPTION",
        )
        return minimal, error_record


# ── Main entry point ──────────────────────────────────────────────────────────

def run_batch(
    jobs: List[BatchJob],
    system: AdaptiveSkillSystem,
    system_version: str = "unknown",
    *,
    max_workers: int = 1,
    fail_fast: bool = False,
    result_store: Optional[ResultStoreProtocol] = None,
    on_result: Optional[Callable[[RunResult], None]] = None,
    batch_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> BatchResult:
    """Run a list of BatchJobs and return a BatchResult.

    Parameters
    ----------
    jobs:
        Ordered list of (case, grader) pairs to evaluate.
    system:
        Shared AdaptiveSkillSystem instance.  In parallel mode (max_workers > 1)
        the system is shared across threads — only safe if its solve() method is
        thread-safe.  By default the system is single-threaded, so max_workers=1
        is the safe default.
    system_version:
        Propagated verbatim into every RunResult.
    max_workers:
        1 = sequential (default); > 1 = ThreadPoolExecutor with that many workers.
    fail_fast:
        Stop after the first failure (final_status != "pass").  Has no effect in
        parallel mode (in-flight jobs still complete).
    result_store:
        Optional persistence hook called after each RunResult.
    on_result:
        Optional callback called after each RunResult (useful for progress bars
        or live logging).
    batch_id:
        Optional explicit batch identifier.  Auto-generated UUID if not provided.
    metadata:
        Optional extra metadata attached to the BatchResult.
    """
    batch_id = batch_id or str(uuid.uuid4())
    metadata = metadata or {}
    started_at = _now_iso()
    wall_clock_start = time.monotonic()

    results: List[RunResult] = []
    runner_errors: List[Dict[str, Any]] = []
    abort = False

    if max_workers <= 1:
        # ── Sequential path ──────────────────────────────────────────────────
        for job in jobs:
            if abort:
                break
            result, err = _run_one(job, system, system_version, result_store)
            results.append(result)
            if err:
                runner_errors.append(err)
            if on_result:
                try:
                    on_result(result)
                except Exception:  # noqa: BLE001
                    pass
            if fail_fast and result.final_status != "pass":
                abort = True
    else:
        # ── Parallel path ────────────────────────────────────────────────────
        future_to_job: Dict[Future[Any], BatchJob] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for job in jobs:
                fut = executor.submit(_run_one, job, system, system_version, result_store)
                future_to_job[fut] = job

            for fut in as_completed(future_to_job):
                result, err = fut.result()
                results.append(result)
                if err:
                    runner_errors.append(err)
                if on_result:
                    try:
                        on_result(result)
                    except Exception:  # noqa: BLE001
                        pass
                # fail_fast in parallel mode: we can't stop queued futures, but
                # we record that we intended to abort (for reporting purposes).
                if fail_fast and result.final_status != "pass":
                    abort = True

        # Preserve job order (as_completed returns in completion order).
        job_order = {job.case.case_id: idx for idx, job in enumerate(jobs)}
        results.sort(key=lambda r: job_order.get(r.case_id, 9999))

    wall_clock_end = time.monotonic()
    ended_at = _now_iso()
    duration_ms = (wall_clock_end - wall_clock_start) * 1000.0

    summary = _compute_summary(results)
    if abort:
        metadata = {**metadata, "fail_fast_triggered": True}

    return BatchResult(
        batch_id=batch_id,
        system_version=system_version,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=round(duration_ms, 2),
        summary=summary,
        results=results,
        runner_errors=runner_errors,
        metadata=metadata,
    )


__all__ = [
    "BatchJob",
    "BatchSummary",
    "BatchResult",
    "run_batch",
]
