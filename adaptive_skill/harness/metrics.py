"""Metrics layer for Adaptive Skill System harness (P3/P2).

Converts BatchResult → BatchMetrics and supports per-case granularity.

Design decisions
----------------
* BatchMetrics is a plain dataclass — fully serialisable to dict/JSON.
* Derived from a BatchResult in a single ``compute_metrics()`` call so
  that metrics are always consistent with the underlying data.
* Per-case detail (``case_metrics``) enables diff-level regression checks
  (did *this specific case* regress, even if aggregate pass_rate is stable?).
* Tag-slice metrics: group cases by tag and compute per-tag pass_rate,
  useful for "layer1 vs layer2 vs layer3" performance tracking.
* Runtime counters (attempt / retry / fallback / token / cost) are read from
  RunResult metadata with missing-safe defaults so older baselines remain
  compatible while newer runs can expose richer operational signals.
* Layer 3 retry telemetry (`generation_attempts`, `generation_info`) is carried
  through per-case metrics so reports can audit recommendations-driven retries.
"""


from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import mean, stdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .batch_runner import BatchResult
from .specs import RunResult


# ── Per-case summary ──────────────────────────────────────────────────────────

@dataclass
class CaseMetrics:
    """Lightweight metrics for a single RunResult."""

    case_id: str
    final_status: str        # pass / fail / partial / error
    final_score: float
    duration_ms: float
    execution_status: str    # success / partial / failed / error
    hard_fail: bool = False
    layer_used: Optional[int] = None  # extracted from execution_trace_summary
    attempt_count: int = 1
    retry_count: int = 0
    fallback_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    grader_scores: Dict[str, float] = field(default_factory=dict)
    assertion_results: List[Dict[str, Any]] = field(default_factory=list)
    grading_notes: List[str] = field(default_factory=list)
    decision_trace: List[Dict[str, Any]] = field(default_factory=list)
    generation_attempts: List[Dict[str, Any]] = field(default_factory=list)
    generation_info: Dict[str, Any] = field(default_factory=dict)


    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)



# ── Aggregate metrics for one batch run ──────────────────────────────────────

@dataclass
class BatchMetrics:
    """Comprehensive metrics derived from a BatchResult."""

    batch_id: str
    system_version: str
    started_at: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    partial: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    score_stdev: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    hard_fail_count: int = 0
    total_attempt_count: int = 0
    avg_attempt_count: float = 0.0
    total_retry_count: int = 0
    avg_retry_count: float = 0.0
    total_fallback_count: int = 0
    avg_fallback_count: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    avg_total_tokens: float = 0.0
    total_estimated_cost: float = 0.0
    avg_estimated_cost: float = 0.0
    runtime_metric_coverage: Dict[str, int] = field(default_factory=dict)
    layer_distribution: Dict[str, int] = field(default_factory=dict)
    tag_slices: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    case_metrics: List[CaseMetrics] = field(default_factory=list)

    def to_dict(self, *, rounded: bool = True) -> Dict[str, Any]:
        """Serialise metrics for JSON output.

        Parameters
        ----------
        rounded:
            When True, round user-facing summary floats for readability.
            When False, keep raw values for persistence/comparison use cases
            such as baseline locking.
        """

        def _maybe_round(value: Any, digits: int) -> Any:
            if not rounded or not isinstance(value, float):
                return value
            return round(value, digits)

        d = {
            "batch_id": self.batch_id,
            "system_version": self.system_version,
            "started_at": self.started_at,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "partial": self.partial,
            "pass_rate": _maybe_round(self.pass_rate, 4),
            "avg_score": _maybe_round(self.avg_score, 4),
            "score_stdev": _maybe_round(self.score_stdev, 4),
            "min_score": _maybe_round(self.min_score, 4),
            "max_score": _maybe_round(self.max_score, 4),
            "avg_duration_ms": _maybe_round(self.avg_duration_ms, 2),
            "p50_duration_ms": _maybe_round(self.p50_duration_ms, 2),
            "p95_duration_ms": _maybe_round(self.p95_duration_ms, 2),
            "hard_fail_count": self.hard_fail_count,
            "total_attempt_count": self.total_attempt_count,
            "avg_attempt_count": _maybe_round(self.avg_attempt_count, 2),
            "total_retry_count": self.total_retry_count,
            "avg_retry_count": _maybe_round(self.avg_retry_count, 2),
            "total_fallback_count": self.total_fallback_count,
            "avg_fallback_count": _maybe_round(self.avg_fallback_count, 2),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "avg_total_tokens": _maybe_round(self.avg_total_tokens, 2),
            "total_estimated_cost": _maybe_round(self.total_estimated_cost, 6),
            "avg_estimated_cost": _maybe_round(self.avg_estimated_cost, 6),
            "runtime_metric_coverage": self.runtime_metric_coverage,
            "layer_distribution": self.layer_distribution,
            "tag_slices": {
                tag: {k: _maybe_round(v, 4) for k, v in sl.items()}
                for tag, sl in self.tag_slices.items()
            },
            "case_metrics": [c.to_dict() for c in self.case_metrics],
        }
        return d


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_layer(run_result: RunResult) -> Optional[int]:
    """Try to read the layer used from execution_trace_summary."""
    trace = run_result.execution_trace_summary
    if not isinstance(trace, dict):
        return None
    layer = trace.get("layer_used") or trace.get("layer")
    if layer is None:
        return None
    try:
        return int(layer)
    except (ValueError, TypeError):
        return None


def _extract_tags(run_result: RunResult) -> List[str]:
    """Pull tags from metadata.tags if present."""
    tags = run_result.metadata.get("tags", [])
    return list(tags) if isinstance(tags, (list, tuple)) else []


def _expand_metric_dict(candidate: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield candidate
    for key in ("runtime_metrics", "token_usage", "usage", "costs", "metrics"):
        nested = candidate.get(key)
        if isinstance(nested, dict):
            yield nested


def _metric_sources(run_result: RunResult) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    direct_sources = [run_result.metadata]
    if isinstance(run_result.solve_response, dict):
        solve_metadata = run_result.solve_response.get("metadata")
        if isinstance(solve_metadata, dict):
            direct_sources.append(solve_metadata)
    if isinstance(run_result.execution_trace_summary, dict):
        trace_metadata = run_result.execution_trace_summary.get("metadata")
        if isinstance(trace_metadata, dict):
            direct_sources.append(trace_metadata)

    for source in direct_sources:
        if isinstance(source, dict):
            sources.extend(_expand_metric_dict(source))
    return sources


def _find_int_metric(run_result: RunResult, aliases: Tuple[str, ...]) -> Tuple[int, bool]:
    for source in _metric_sources(run_result):
        for key in aliases:
            if key not in source:
                continue
            value = source.get(key)
            try:
                return int(value), True
            except (TypeError, ValueError):
                continue
    return 0, False


def _find_float_metric(run_result: RunResult, aliases: Tuple[str, ...]) -> Tuple[float, bool]:
    for source in _metric_sources(run_result):
        for key in aliases:
            if key not in source:
                continue
            value = source.get(key)
            try:
                return float(value), True
            except (TypeError, ValueError):
                continue
    return 0.0, False


def _extract_attempt_count(run_result: RunResult) -> Tuple[int, bool]:
    attempt_count, attempt_present = _find_int_metric(run_result, ("attempt_count",))
    if attempt_present:
        return max(attempt_count, 1), True

    retry_count, retry_present = _find_int_metric(run_result, ("retry_count",))
    if retry_present:
        return max(retry_count + 1, 1), True

    return 1, False


def _extract_retry_count(run_result: RunResult) -> Tuple[int, bool]:
    retry_count, retry_present = _find_int_metric(run_result, ("retry_count",))
    if retry_present:
        return max(retry_count, 0), True

    attempt_count, attempt_present = _find_int_metric(run_result, ("attempt_count",))
    if attempt_present:
        return max(attempt_count - 1, 0), True

    return 0, False


def _extract_fallback_count(run_result: RunResult) -> Tuple[int, bool]:
    fallback_count, fallback_present = _find_int_metric(
        run_result,
        ("fallback_count", "framework_fallback_count"),
    )
    if fallback_present:
        return max(fallback_count, 0), True
    return 0, False


def _extract_token_metrics(run_result: RunResult) -> Tuple[int, int, int, bool]:
    prompt_tokens, prompt_present = _find_int_metric(run_result, ("prompt_tokens", "input_tokens"))
    completion_tokens, completion_present = _find_int_metric(
        run_result,
        ("completion_tokens", "output_tokens"),
    )
    total_tokens, total_present = _find_int_metric(run_result, ("total_tokens", "token_count"))

    if not total_present and (prompt_present or completion_present):
        total_tokens = max(prompt_tokens, 0) + max(completion_tokens, 0)
        total_present = True

    return (
        max(prompt_tokens, 0),
        max(completion_tokens, 0),
        max(total_tokens, 0),
        total_present,
    )


def _extract_estimated_cost(run_result: RunResult) -> Tuple[float, bool]:
    estimated_cost, cost_present = _find_float_metric(run_result, ("estimated_cost", "cost", "cost_usd"))
    if cost_present:
        return max(estimated_cost, 0.0), True
    return 0.0, False


def _extract_grader_scores(run_result: RunResult) -> Dict[str, float]:
    if not isinstance(run_result.grader_scores, dict):
        return {}

    normalized: Dict[str, float] = {}
    for name, score in run_result.grader_scores.items():
        try:
            normalized[str(name)] = float(score)
        except (TypeError, ValueError):
            continue
    return normalized


def _extract_assertion_results(run_result: RunResult) -> List[Dict[str, Any]]:
    raw = run_result.metadata.get("assertion_results", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _extract_grading_notes(run_result: RunResult) -> List[str]:
    raw = run_result.metadata.get("grading_notes", [])
    if not isinstance(raw, list):
        return []
    return [str(note) for note in raw]



def _extract_decision_trace(run_result: RunResult) -> List[Dict[str, Any]]:
    raw = getattr(run_result, "decision_trace", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _extract_generation_attempts(run_result: RunResult) -> List[Dict[str, Any]]:
    for source in _metric_sources(run_result):
        raw = source.get("generation_attempts")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    return []


def _extract_generation_info(run_result: RunResult) -> Dict[str, Any]:
    for source in _metric_sources(run_result):
        raw = source.get("generation_info")
        if isinstance(raw, dict):
            return dict(raw)
    return {}


def _empty_runtime_metric_coverage() -> Dict[str, int]:


    return {
        "attempt_count": 0,
        "retry_count": 0,
        "fallback_count": 0,
        "total_tokens": 0,
        "estimated_cost": 0,
    }


def _percentile(sorted_values: List[float], p: float) -> float:
    """Interpolated p-th percentile (0 < p <= 100) from a sorted list."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    rank = (p / 100) * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    frac = rank - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


# ── Public API ────────────────────────────────────────────────────────────────

def compute_metrics(batch_result: BatchResult) -> BatchMetrics:
    """Derive a BatchMetrics from a completed BatchResult."""
    results: List[RunResult] = batch_result.results
    total = len(results)

    bm = BatchMetrics(
        batch_id=batch_result.batch_id,
        system_version=batch_result.system_version,
        started_at=batch_result.started_at,
        total=total,
        runtime_metric_coverage=_empty_runtime_metric_coverage(),
    )

    if total == 0:
        return bm

    # ── Counts ──
    bm.passed = sum(1 for r in results if r.final_status == "pass")
    bm.failed = sum(1 for r in results if r.final_status == "fail")
    bm.errored = sum(1 for r in results if r.final_status == "error")
    bm.partial = sum(1 for r in results if r.final_status == "partial")
    bm.pass_rate = bm.passed / total
    bm.hard_fail_count = sum(1 for r in results if r.metadata.get("hard_fail") is True)

    # ── Scores ──
    scores = [r.final_score for r in results]
    bm.avg_score = mean(scores)
    bm.min_score = min(scores)
    bm.max_score = max(scores)
    bm.score_stdev = stdev(scores) if len(scores) >= 2 else 0.0

    # ── Durations ──
    durations = sorted(r.duration_ms for r in results)
    bm.avg_duration_ms = mean(durations)
    bm.p50_duration_ms = _percentile(durations, 50)
    bm.p95_duration_ms = _percentile(durations, 95)

    # ── Layer distribution ──
    layer_dist: Dict[str, int] = {}
    for r in results:
        layer = _extract_layer(r)
        key = str(layer) if layer is not None else "unknown"
        layer_dist[key] = layer_dist.get(key, 0) + 1
    bm.layer_distribution = layer_dist

    # ── Tag slices ──
    tag_buckets: Dict[str, List[RunResult]] = {}
    for r in results:
        for tag in _extract_tags(r):
            tag_buckets.setdefault(tag, []).append(r)

    for tag, bucket in tag_buckets.items():
        n = len(bucket)
        tag_passed = sum(1 for r in bucket if r.final_status == "pass")
        tag_scores = [r.final_score for r in bucket]
        bm.tag_slices[tag] = {
            "total": n,
            "passed": tag_passed,
            "pass_rate": tag_passed / n,
            "avg_score": mean(tag_scores),
        }

    # ── Per-case + runtime metrics ──
    case_metrics: List[CaseMetrics] = []
    for r in results:
        attempt_count, attempt_present = _extract_attempt_count(r)
        retry_count, retry_present = _extract_retry_count(r)
        fallback_count, fallback_present = _extract_fallback_count(r)
        prompt_tokens, completion_tokens, total_tokens, total_tokens_present = _extract_token_metrics(r)
        estimated_cost, estimated_cost_present = _extract_estimated_cost(r)

        if attempt_present:
            bm.runtime_metric_coverage["attempt_count"] += 1
        if retry_present:
            bm.runtime_metric_coverage["retry_count"] += 1
        if fallback_present:
            bm.runtime_metric_coverage["fallback_count"] += 1
        if total_tokens_present:
            bm.runtime_metric_coverage["total_tokens"] += 1
        if estimated_cost_present:
            bm.runtime_metric_coverage["estimated_cost"] += 1

        bm.total_attempt_count += attempt_count
        bm.total_retry_count += retry_count
        bm.total_fallback_count += fallback_count
        bm.total_prompt_tokens += prompt_tokens
        bm.total_completion_tokens += completion_tokens
        bm.total_tokens += total_tokens
        bm.total_estimated_cost += estimated_cost

        case_metrics.append(
            CaseMetrics(
                case_id=r.case_id,
                final_status=r.final_status,
                final_score=r.final_score,
                duration_ms=r.duration_ms,
                execution_status=r.execution_status,
                hard_fail=bool(r.metadata.get("hard_fail", False)),
                layer_used=_extract_layer(r),
                attempt_count=attempt_count,
                retry_count=retry_count,
                fallback_count=fallback_count,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost=estimated_cost,
                grader_scores=_extract_grader_scores(r),
                assertion_results=_extract_assertion_results(r),
                grading_notes=_extract_grading_notes(r),
                decision_trace=_extract_decision_trace(r),
                generation_attempts=_extract_generation_attempts(r),
                generation_info=_extract_generation_info(r),
            )


        )


    bm.case_metrics = case_metrics
    bm.avg_attempt_count = bm.total_attempt_count / total
    bm.avg_retry_count = bm.total_retry_count / total
    bm.avg_fallback_count = bm.total_fallback_count / total
    bm.avg_total_tokens = bm.total_tokens / total
    bm.avg_estimated_cost = bm.total_estimated_cost / total

    return bm


__all__ = [
    "CaseMetrics",
    "BatchMetrics",
    "compute_metrics",
]
