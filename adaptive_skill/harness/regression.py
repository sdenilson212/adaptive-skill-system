"""Regression detection for Adaptive Skill System harness (P3).

Compares a "current" BatchMetrics against a locked BaselineRecord and
surfaces any metric regressions that exceed configurable thresholds.

Design decisions
----------------
* RegressionThresholds: all thresholds have sensible defaults; callers
  override only what they care about.
* RegressionFinding: one finding per violated threshold, with actual /
  baseline values and the computed delta so the report is self-contained.
* RegressionReport: overall PASS / FAIL verdict + ordered finding list +
  per-case regressions (cases that newly failed or dropped in score).
* check_regression(): the primary public API — accepts BatchMetrics +
  BaselineRecord (or BaselineStore + baseline_id) and returns a
  RegressionReport without raising.  Raising is left to the caller.
* Severity tiers: CRITICAL (hard-fail increase), HIGH (pass_rate drop,
  avg_score drop), MEDIUM (partial/error count increase), LOW (latency).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .baseline import BaselineRecord, BaselineStore
from .metrics import BatchMetrics, CaseMetrics


# ── Thresholds ────────────────────────────────────────────────────────────────

@dataclass
class RegressionThresholds:
    """Configurable thresholds for regression detection.

    All values are *maximum allowable deltas*.  A regression is flagged
    when the actual change **exceeds** the threshold in the wrong direction.

    Attributes
    ----------
    pass_rate_drop:
        Maximum tolerated drop in pass_rate (0.0–1.0).
        Default 0.05 → 5 pp drop triggers a HIGH regression.
    avg_score_drop:
        Maximum tolerated drop in avg_score (0.0–1.0).
        Default 0.05 → 0.05 drop triggers a HIGH regression.
    hard_fail_increase:
        Maximum tolerated increase in hard_fail_count.
        Default 0 → any new hard fail is CRITICAL.
    error_rate_increase:
        Maximum tolerated increase in errored/total ratio.
        Default 0.05 → 5 pp increase triggers MEDIUM.
    p95_latency_increase_pct:
        Maximum tolerated percentage increase in p95_duration_ms.
        Default 50.0 → 50 % increase triggers LOW.
    avg_attempt_count_increase:
        Maximum tolerated increase in average attempt count per case.
        Default 0.5 → sustained retry pressure triggers MEDIUM.
    avg_retry_count_increase:
        Maximum tolerated increase in average retry count per case.
        Default 0.5 → higher retry pressure triggers MEDIUM.
    avg_fallback_count_increase:
        Maximum tolerated increase in average framework fallback count per case.
        Default 0.3 → more frequent fallbacks trigger MEDIUM.
    avg_total_tokens_increase_pct:
        Maximum tolerated percentage increase in average total token usage.
        Default 20.0 → efficiency regression triggers LOW.
    avg_estimated_cost_increase_pct:
        Maximum tolerated percentage increase in average estimated cost.
        Default 20.0 → cost regression triggers LOW.
    case_score_drop:
        Per-case maximum tolerated score drop.
        Default 0.1 → any case dropping > 0.1 is listed.
    """

    pass_rate_drop: float = 0.05
    avg_score_drop: float = 0.05
    hard_fail_increase: int = 0
    error_rate_increase: float = 0.05
    p95_latency_increase_pct: float = 50.0
    avg_attempt_count_increase: float = 0.5
    avg_retry_count_increase: float = 0.5
    avg_fallback_count_increase: float = 0.3
    avg_total_tokens_increase_pct: float = 20.0
    avg_estimated_cost_increase_pct: float = 20.0
    case_score_drop: float = 0.1



# ── Finding ───────────────────────────────────────────────────────────────────

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

_SEVERITY_ORDER = {SEVERITY_CRITICAL: 0, SEVERITY_HIGH: 1, SEVERITY_MEDIUM: 2, SEVERITY_LOW: 3}
_EPSILON = 1e-12



@dataclass
class RegressionFinding:
    """A single regression that exceeded its threshold."""

    metric: str           # e.g. "pass_rate", "hard_fail_count", "case:<id>"
    severity: str         # CRITICAL | HIGH | MEDIUM | LOW
    baseline_value: Any
    current_value: Any
    delta: float          # current - baseline (negative = drop, positive = increase)
    threshold: float      # the configured allowable delta
    description: str      # human-readable summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "severity": self.severity,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "delta": round(self.delta, 6),
            "threshold": round(self.threshold, 6),
            "description": self.description,
        }


# ── Report ────────────────────────────────────────────────────────────────────

@dataclass
class RegressionReport:
    """Outcome of comparing a BatchMetrics against a baseline.

    Attributes
    ----------
    passed : bool
        True iff no findings were raised.
    verdict : str
        "PASS" or "FAIL".
    findings : List[RegressionFinding]
        All detected regressions, sorted by severity then metric name.
    case_regressions : List[RegressionFinding]
        Per-case score drops, kept separate for readability.
    current_metrics : BatchMetrics
        The BatchMetrics that was compared.
    baseline_id : str
        ID of the baseline used for comparison.
    baseline_label : str
        Human label of the baseline.
    thresholds : RegressionThresholds
        The thresholds that were applied.
    summary : str
        One-line summary suitable for CI log headers.
    """

    passed: bool
    verdict: str
    findings: List[RegressionFinding] = field(default_factory=list)
    case_regressions: List[RegressionFinding] = field(default_factory=list)
    current_metrics: Optional[BatchMetrics] = None
    baseline_id: str = ""
    baseline_label: str = ""
    thresholds: Optional[RegressionThresholds] = None
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "verdict": self.verdict,
            "baseline_id": self.baseline_id,
            "baseline_label": self.baseline_label,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "case_regressions": [f.to_dict() for f in self.case_regressions],
            "thresholds": asdict(self.thresholds) if self.thresholds else {},
        }

    def _combined_findings(self) -> List[RegressionFinding]:
        return [*self.findings, *self.case_regressions]

    @property
    def has_critical(self) -> bool:
        return any(f.severity == SEVERITY_CRITICAL for f in self._combined_findings())

    @property
    def has_high(self) -> bool:
        return any(f.severity == SEVERITY_HIGH for f in self._combined_findings())

    def findings_by_severity(self) -> List[RegressionFinding]:
        return sorted(
            self._combined_findings(),
            key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.metric),
        )



# ── Internal comparison helpers ───────────────────────────────────────────────

def _check_metric(
    metric: str,
    severity: str,
    baseline_val: float,
    current_val: float,
    threshold: float,
    *,
    higher_is_better: bool = True,
    description_template: str = "",
) -> Optional[RegressionFinding]:
    """Return a RegressionFinding if the change violates the threshold."""
    delta = current_val - baseline_val
    # For higher-is-better: regression when delta < -threshold
    # For lower-is-better: regression when delta > threshold
    # Use a small epsilon so exact-boundary comparisons do not misfire due to
    # floating-point representation noise.
    if higher_is_better:
        violated = delta < (-abs(threshold) - _EPSILON)
    else:
        violated = delta > (abs(threshold) + _EPSILON)


    if not violated:
        return None

    desc = description_template or (
        f"{metric}: {baseline_val:.4f} → {current_val:.4f} "
        f"(delta {delta:+.4f}, threshold ±{threshold:.4f})"
    )
    return RegressionFinding(
        metric=metric,
        severity=severity,
        baseline_value=baseline_val,
        current_value=current_val,
        delta=delta,
        threshold=threshold,
        description=desc,
    )


def _compare_aggregate(
    current: BatchMetrics,
    baseline_metrics: BatchMetrics,
    thresholds: RegressionThresholds,
) -> List[RegressionFinding]:
    """Compare aggregate metrics and return list of findings."""
    findings: List[RegressionFinding] = []

    # pass_rate (HIGH)
    f = _check_metric(
        "pass_rate",
        SEVERITY_HIGH,
        baseline_metrics.pass_rate,
        current.pass_rate,
        thresholds.pass_rate_drop,
        higher_is_better=True,
    )
    if f:
        findings.append(f)

    # avg_score (HIGH)
    f = _check_metric(
        "avg_score",
        SEVERITY_HIGH,
        baseline_metrics.avg_score,
        current.avg_score,
        thresholds.avg_score_drop,
        higher_is_better=True,
    )
    if f:
        findings.append(f)

    # hard_fail_count (CRITICAL): threshold is an integer count delta
    hf_delta = current.hard_fail_count - baseline_metrics.hard_fail_count
    if hf_delta > thresholds.hard_fail_increase:
        findings.append(RegressionFinding(
            metric="hard_fail_count",
            severity=SEVERITY_CRITICAL,
            baseline_value=baseline_metrics.hard_fail_count,
            current_value=current.hard_fail_count,
            delta=float(hf_delta),
            threshold=float(thresholds.hard_fail_increase),
            description=(
                f"hard_fail_count increased by {hf_delta} "
                f"(baseline {baseline_metrics.hard_fail_count} → {current.hard_fail_count})"
            ),
        ))

    # error_rate (MEDIUM)
    base_err_rate = (
        baseline_metrics.errored / baseline_metrics.total
        if baseline_metrics.total > 0
        else 0.0
    )
    curr_err_rate = (
        current.errored / current.total
        if current.total > 0
        else 0.0
    )
    f = _check_metric(
        "error_rate",
        SEVERITY_MEDIUM,
        base_err_rate,
        curr_err_rate,
        thresholds.error_rate_increase,
        higher_is_better=False,
        description_template=(
            f"error_rate: {base_err_rate:.4f} → {curr_err_rate:.4f} "
            f"(+{curr_err_rate - base_err_rate:.4f}, threshold {thresholds.error_rate_increase:.4f})"
        ) if curr_err_rate - base_err_rate > thresholds.error_rate_increase else "",
    )
    if f:
        findings.append(f)

    # p95 latency (LOW): percentage increase
    if baseline_metrics.p95_duration_ms > 0:
        pct_change = (
            (current.p95_duration_ms - baseline_metrics.p95_duration_ms)
            / baseline_metrics.p95_duration_ms
        ) * 100
        if pct_change > (thresholds.p95_latency_increase_pct + _EPSILON):

            findings.append(RegressionFinding(
                metric="p95_duration_ms",
                severity=SEVERITY_LOW,
                baseline_value=baseline_metrics.p95_duration_ms,
                current_value=current.p95_duration_ms,
                delta=current.p95_duration_ms - baseline_metrics.p95_duration_ms,
                threshold=thresholds.p95_latency_increase_pct,
                description=(
                    f"p95 latency increased {pct_change:.1f}% "
                    f"({baseline_metrics.p95_duration_ms:.1f}ms → {current.p95_duration_ms:.1f}ms, "
                    f"threshold {thresholds.p95_latency_increase_pct:.1f}%)"
                ),
            ))

    return findings


def _has_runtime_coverage(metrics: BatchMetrics, key: str) -> bool:
    return metrics.runtime_metric_coverage.get(key, 0) > 0


def _compare_runtime_metrics(
    current: BatchMetrics,
    baseline_metrics: BatchMetrics,
    thresholds: RegressionThresholds,
) -> List[RegressionFinding]:
    """Compare runtime-efficiency metrics when both runs expose telemetry."""
    findings: List[RegressionFinding] = []

    runtime_average_checks = [
        (
            "attempt_count",
            "avg_attempt_count",
            SEVERITY_MEDIUM,
            baseline_metrics.avg_attempt_count,
            current.avg_attempt_count,
            thresholds.avg_attempt_count_increase,
            "attempt pressure increased",
        ),
        (
            "retry_count",
            "avg_retry_count",
            SEVERITY_MEDIUM,
            baseline_metrics.avg_retry_count,
            current.avg_retry_count,
            thresholds.avg_retry_count_increase,
            "retry pressure increased",
        ),
        (
            "fallback_count",
            "avg_fallback_count",
            SEVERITY_MEDIUM,
            baseline_metrics.avg_fallback_count,
            current.avg_fallback_count,
            thresholds.avg_fallback_count_increase,
            "framework fallback rate increased",
        ),
    ]

    for coverage_key, metric_name, severity, baseline_value, current_value, threshold, summary in runtime_average_checks:
        if not (_has_runtime_coverage(current, coverage_key) and _has_runtime_coverage(baseline_metrics, coverage_key)):
            continue
        finding = _check_metric(
            metric_name,
            severity,
            baseline_value,
            current_value,
            threshold,
            higher_is_better=False,
            description_template=(
                f"{metric_name}: {baseline_value:.4f} → {current_value:.4f} "
                f"(delta {current_value - baseline_value:+.4f}, threshold {threshold:.4f}; {summary})"
            ) if current_value - baseline_value > threshold else "",
        )
        if finding:
            findings.append(finding)

    pct_runtime_checks = [
        (
            "total_tokens",
            "avg_total_tokens",
            SEVERITY_LOW,
            baseline_metrics.avg_total_tokens,
            current.avg_total_tokens,
            thresholds.avg_total_tokens_increase_pct,
            "token usage increased",
        ),
        (
            "estimated_cost",
            "avg_estimated_cost",
            SEVERITY_LOW,
            baseline_metrics.avg_estimated_cost,
            current.avg_estimated_cost,
            thresholds.avg_estimated_cost_increase_pct,
            "estimated cost increased",
        ),
    ]

    for coverage_key, metric_name, severity, baseline_value, current_value, threshold_pct, summary in pct_runtime_checks:
        if not (_has_runtime_coverage(current, coverage_key) and _has_runtime_coverage(baseline_metrics, coverage_key)):
            continue

        if baseline_value <= 0:
            if current_value > _EPSILON:
                findings.append(
                    RegressionFinding(
                        metric=metric_name,
                        severity=severity,
                        baseline_value=baseline_value,
                        current_value=current_value,
                        delta=current_value - baseline_value,
                        threshold=0.0,
                        description=(
                            f"{metric_name}: baseline was {baseline_value:.4f}, current is {current_value:.4f} "
                            f"(new measurable runtime load; {summary})"
                        ),
                    )
                )
            continue

        pct_change = ((current_value - baseline_value) / baseline_value) * 100
        if pct_change > (threshold_pct + _EPSILON):
            findings.append(
                RegressionFinding(
                    metric=metric_name,
                    severity=severity,
                    baseline_value=baseline_value,
                    current_value=current_value,
                    delta=current_value - baseline_value,
                    threshold=threshold_pct,
                    description=(
                        f"{metric_name} increased {pct_change:.1f}% "
                        f"({baseline_value:.4f} → {current_value:.4f}, threshold {threshold_pct:.1f}%; {summary})"
                    ),
                )
            )

    return findings


def _compare_cases(

    current: BatchMetrics,
    baseline_metrics: BatchMetrics,
    threshold: float,
) -> List[RegressionFinding]:
    """Compare per-case scores; return findings for cases that regressed."""
    baseline_index: Dict[str, CaseMetrics] = {
        c.case_id: c for c in baseline_metrics.case_metrics
    }
    findings: List[RegressionFinding] = []

    for cm in current.case_metrics:
        base_cm = baseline_index.get(cm.case_id)
        if base_cm is None:
            continue  # new case — not a regression

        delta = cm.final_score - base_cm.final_score
        if delta < (-abs(threshold) - _EPSILON):

            # Also flag status changes: was pass, now fail/error
            severity = SEVERITY_MEDIUM
            if base_cm.final_status == "pass" and cm.final_status in ("fail", "error"):
                severity = SEVERITY_HIGH

            findings.append(RegressionFinding(
                metric=f"case:{cm.case_id}",
                severity=severity,
                baseline_value=base_cm.final_score,
                current_value=cm.final_score,
                delta=delta,
                threshold=threshold,
                description=(
                    f"Case '{cm.case_id}' score dropped {delta:+.4f} "
                    f"({base_cm.final_status}/{base_cm.final_score:.4f} → "
                    f"{cm.final_status}/{cm.final_score:.4f})"
                ),
            ))

    return findings


# ── Public API ────────────────────────────────────────────────────────────────

def check_regression(
    current: BatchMetrics,
    baseline: BaselineRecord,
    thresholds: Optional[RegressionThresholds] = None,
) -> RegressionReport:
    """Compare *current* BatchMetrics against a locked BaselineRecord.

    Parameters
    ----------
    current:
        BatchMetrics from the most recent run.
    baseline:
        The BaselineRecord to compare against.
    thresholds:
        Override default thresholds.  Defaults to RegressionThresholds().

    Returns
    -------
    RegressionReport
        ``report.passed`` is True iff no findings were raised.
        The report never raises; errors in comparison surface as LOW findings.
    """
    if thresholds is None:
        thresholds = RegressionThresholds()

    aggregate_findings = _compare_aggregate(current, baseline.metrics, thresholds)
    runtime_findings = _compare_runtime_metrics(current, baseline.metrics, thresholds)
    case_findings = _compare_cases(current, baseline.metrics, thresholds.case_score_drop)

    all_findings = sorted(
        [*aggregate_findings, *runtime_findings],

        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.metric),
    )
    case_findings_sorted = sorted(
        case_findings,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.metric),
    )

    passed = len(all_findings) == 0 and len(case_findings) == 0
    verdict = "PASS" if passed else "FAIL"

    # Build summary line
    if passed:
        summary = (
            f"PASS — no regressions vs baseline '{baseline.label}' "
            f"(pass_rate {current.pass_rate:.1%}, avg_score {current.avg_score:.4f})"
        )
    else:
        n_findings = len(all_findings) + len(case_findings)
        summary = (
            f"FAIL — {n_findings} regression(s) vs baseline '{baseline.label}' "
            f"(pass_rate {baseline.metrics.pass_rate:.1%} → {current.pass_rate:.1%}, "
            f"avg_score {baseline.metrics.avg_score:.4f} → {current.avg_score:.4f})"
        )

    return RegressionReport(
        passed=passed,
        verdict=verdict,
        findings=all_findings,
        case_regressions=case_findings_sorted,
        current_metrics=current,
        baseline_id=baseline.baseline_id,
        baseline_label=baseline.label,
        thresholds=thresholds,
        summary=summary,
    )


def check_regression_from_store(
    current: BatchMetrics,
    store: BaselineStore,
    baseline_id: str,
    thresholds: Optional[RegressionThresholds] = None,
) -> RegressionReport:
    """Convenience wrapper: load baseline from a BaselineStore then compare.

    Raises
    ------
    FileNotFoundError
        If baseline_id does not exist in the store.
    """
    baseline = store.load(baseline_id)
    return check_regression(current, baseline, thresholds)


__all__ = [
    "RegressionThresholds",
    "RegressionFinding",
    "RegressionReport",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "check_regression",
    "check_regression_from_store",
]
