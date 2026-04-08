"""Reporting layer for Adaptive Skill System harness (P4).

Builds human-readable Markdown / HTML reports from completed harness runs.
The module is intentionally stdlib-only so reports can be generated inside
CI, local scripts, or lightweight research workflows without extra deps.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .baseline import BaselineRecord
from .batch_runner import BatchResult
from .metrics import BatchMetrics, compute_metrics
from .regression import RegressionFinding, RegressionReport


@dataclass
class ReportBundle:
    """In-memory bundle for one rendered report."""

    batch_id: str
    title: str
    generated_at: str
    report_data: Dict[str, Any]
    markdown: str
    html: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "title": self.title,
            "generated_at": self.generated_at,
            "report_data": self.report_data,
            "markdown": self.markdown,
            "html": self.html,
        }


@dataclass
class WrittenReportBundle:
    """Filesystem paths for a persisted report bundle."""

    output_dir: str
    markdown_path: str
    html_path: str
    json_path: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "output_dir": self.output_dir,
            "markdown_path": self.markdown_path,
            "html_path": self.html_path,
            "json_path": self.json_path,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_chip_label(batch_result: BatchResult, regression_report: Optional[RegressionReport]) -> str:
    if regression_report is not None:
        return regression_report.verdict
    if batch_result.summary.errored > 0 or batch_result.summary.hard_fail_count > 0:
        return "FAIL"
    if batch_result.summary.failed > 0 or batch_result.summary.partial > 0:
        return "WARN"
    return "PASS"


def _status_chip_class(label: str) -> str:
    return {
        "PASS": "pass",
        "WARN": "warn",
        "FAIL": "fail",
    }.get(label, "neutral")


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_num(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_ms(value: float) -> str:
    return f"{value:.2f} ms"


def _safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    value = value.strip("-._")
    return value or "report"


def _case_grader_scores(case: Dict[str, Any]) -> Dict[str, float]:
    raw = case.get("grader_scores", {})
    return raw if isinstance(raw, dict) else {}


def _case_assertion_results(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = case.get("assertion_results", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _case_grading_notes(case: Dict[str, Any]) -> List[str]:
    raw = case.get("grading_notes", [])
    if not isinstance(raw, list):
        return []
    return [str(note) for note in raw]


def _case_has_grader_details(case: Dict[str, Any]) -> bool:
    return bool(
        _case_grader_scores(case)
        or _case_assertion_results(case)
        or _case_grading_notes(case)
    )



def _case_decision_trace(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = case.get("decision_trace", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]



def _case_has_decision_trace(case: Dict[str, Any]) -> bool:
    return bool(_case_decision_trace(case))



def _case_generation_attempts(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = case.get("generation_attempts", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]



def _case_generation_info(case: Dict[str, Any]) -> Dict[str, Any]:
    raw = case.get("generation_info", {})
    if not isinstance(raw, dict):
        return {}
    return raw



def _case_generation_attempt_count(case: Dict[str, Any]) -> int:
    attempts = _case_generation_attempts(case)
    if attempts:
        return len(attempts)

    raw_attempt = _case_generation_info(case).get("generation_attempt")
    try:
        return max(int(raw_attempt), 0)
    except (TypeError, ValueError):
        return 0



def _case_has_generation_telemetry(case: Dict[str, Any]) -> bool:
    return bool(_case_generation_attempts(case) or _case_generation_info(case))



def _failed_draft_preview(draft: Any) -> Optional[str]:
    if not isinstance(draft, dict):
        return None

    name = draft.get("name") or draft.get("draft_name") or draft.get("skill_id")
    steps = draft.get("steps")
    checklist = draft.get("verification_checklist")
    step_count = len(steps) if isinstance(steps, list) else draft.get("step_count")
    checklist_count = len(checklist) if isinstance(checklist, list) else draft.get("checklist_count")

    detail_parts = []
    if isinstance(step_count, int):
        detail_parts.append(f"steps={step_count}")
    if isinstance(checklist_count, int):
        detail_parts.append(f"checklist={checklist_count}")

    if name and detail_parts:
        return f"failed_draft={name} ({', '.join(detail_parts)})"
    if name:
        return f"failed_draft={name}"
    if detail_parts:
        return "failed_draft(" + ", ".join(detail_parts) + ")"
    return "failed_draft=present"




def _generation_attempt_summary(attempt: Dict[str, Any]) -> str:
    parts = [f"attempt={attempt.get('attempt', '?')}"]

    quality = attempt.get("quality")
    if isinstance(quality, (int, float)):
        parts.append(f"quality={_fmt_num(float(quality))}")

    approved = attempt.get("approved")
    if isinstance(approved, bool):
        parts.append(f"approved={approved}")

    generation_mode = attempt.get("generation_mode")
    if generation_mode:
        parts.append(f"mode={generation_mode}")

    provider_used = attempt.get("provider_used")
    if provider_used:
        parts.append(f"provider={provider_used}")

    recommendations = attempt.get("recommendations")
    if isinstance(recommendations, list) and recommendations:
        parts.append("recommendations=" + "; ".join(str(item) for item in recommendations))

    draft_preview = _failed_draft_preview(attempt.get("failed_draft"))
    if draft_preview:
        parts.append(draft_preview)

    persisted = attempt.get("failed_draft_persisted")
    if isinstance(persisted, bool):
        parts.append(f"persisted={persisted}")

    draft_record_id = attempt.get("failed_draft_record_id")
    if draft_record_id is not None:
        parts.append(f"draft_id={draft_record_id}")

    persist_error = attempt.get("persist_error")
    if persist_error:
        parts.append(f"persist_error={persist_error}")

    return " | ".join(parts)





def _generation_info_summary(case: Dict[str, Any]) -> str:
    outer = _case_generation_info(case)
    nested = outer.get("generation_info") if isinstance(outer.get("generation_info"), dict) else {}
    final_info = nested or outer
    parts: List[str] = []

    skill_name = outer.get("name")
    if skill_name:
        parts.append(f"name={skill_name}")

    generation_mode = final_info.get("generation_mode") or outer.get("generation_mode")
    if generation_mode:
        parts.append(f"mode={generation_mode}")

    provider = final_info.get("llm_provider") or outer.get("llm_provider")
    if provider:
        parts.append(f"provider={provider}")

    generation_attempt = final_info.get("generation_attempt") or outer.get("generation_attempt")
    if generation_attempt is not None:
        parts.append(f"final_attempt={generation_attempt}")

    strategy = final_info.get("generation_strategy")
    if strategy:
        parts.append(f"strategy={strategy}")

    confidence = final_info.get("confidence")
    if isinstance(confidence, (int, float)):
        parts.append(f"confidence={_fmt_num(float(confidence))}")

    needs_verification = final_info.get("needs_verification")
    if isinstance(needs_verification, bool):
        parts.append(f"needs_verification={needs_verification}")

    feedback = final_info.get("evaluator_feedback_applied") or outer.get("evaluator_feedback_applied")
    if isinstance(feedback, list) and feedback:
        parts.append("feedback=" + "; ".join(str(item) for item in feedback))

    failed_draft_preview = _failed_draft_preview(outer.get("failed_draft"))
    if failed_draft_preview:
        parts.append(failed_draft_preview)

    persisted = outer.get("failed_draft_persisted")
    if isinstance(persisted, bool):
        parts.append(f"persisted={persisted}")

    draft_record_id = outer.get("failed_draft_record_id")
    if draft_record_id is not None:
        parts.append(f"draft_id={draft_record_id}")

    persist_error = outer.get("persist_error")
    if persist_error:
        parts.append(f"persist_error={persist_error}")

    return " | ".join(parts) if parts else "—"




def _decision_trace_summary(trace: Dict[str, Any]) -> str:

    layer = trace.get("layer", "?")
    action = trace.get("action", "unknown")
    trigger = trace.get("trigger", "unknown")
    summary_parts = [f"L{layer}", str(action), str(trigger)]

    score = trace.get("score")
    if isinstance(score, (int, float)):
        summary_parts.append(f"score={_fmt_num(float(score))}")

    candidates = trace.get("candidates_evaluated")
    if isinstance(candidates, int):
        summary_parts.append(f"candidates={candidates}")

    selected_name = trace.get("selected_skill_name")
    if selected_name:
        summary_parts.append(f"selected={selected_name}")

    rejection_reason = trace.get("rejection_reason")
    if rejection_reason:
        summary_parts.append(f"reason={rejection_reason}")

    coverage_score = trace.get("coverage_score")
    if isinstance(coverage_score, (int, float)):
        summary_parts.append(f"coverage={_fmt_num(float(coverage_score))}")

    composability_score = trace.get("composability_score")
    if isinstance(composability_score, (int, float)):
        summary_parts.append(f"composability={_fmt_num(float(composability_score))}")

    generation_strategy = trace.get("generation_strategy")
    if generation_strategy:
        summary_parts.append(f"strategy={generation_strategy}")

    evaluator_score = trace.get("evaluator_score")
    if isinstance(evaluator_score, (int, float)):
        summary_parts.append(f"evaluator={_fmt_num(float(evaluator_score))}")

    return " | ".join(summary_parts)



def _decision_trace_extra_lines(trace: Dict[str, Any]) -> List[str]:
    lines: List[str] = []

    evaluator_dimensions = trace.get("evaluator_dimensions")
    if isinstance(evaluator_dimensions, dict) and evaluator_dimensions:
        dims = ", ".join(
            f"{name}={_fmt_num(score)}"
            for name, score in sorted(evaluator_dimensions.items(), key=lambda item: item[0])
        )
        lines.append(f"evaluator_dimensions: {dims}")

    candidates = trace.get("candidates")
    if isinstance(candidates, list) and candidates:
        lines.append(f"candidate_preview: {json.dumps(candidates, ensure_ascii=False)}")

    rejection_detail = trace.get("rejection_detail")
    if isinstance(rejection_detail, dict) and rejection_detail:
        lines.append(f"rejection_detail: {json.dumps(rejection_detail, ensure_ascii=False)}")

    return lines





def _case_grader_summary(case: Dict[str, Any]) -> str:
    grader_scores = _case_grader_scores(case)
    if not grader_scores:
        return "—"
    return "; ".join(
        f"{name}={_fmt_num(score)}"
        for name, score in sorted(grader_scores.items(), key=lambda item: item[0])
    )


def _assertion_summary(assertion: Dict[str, Any]) -> str:
    spec_type = assertion.get("type", "unknown")
    passed = assertion.get("passed")
    score = assertion.get("score", 0.0)
    message = assertion.get("message") or "—"
    return (
        f"{spec_type} | passed={passed} | score={_fmt_num(score)} | "
        f"message={message}"
    )


def _finding_to_row(finding: RegressionFinding) -> Dict[str, Any]:

    return {
        "metric": finding.metric,
        "severity": finding.severity,
        "baseline_value": finding.baseline_value,
        "current_value": finding.current_value,
        "delta": round(finding.delta, 6),
        "threshold": round(finding.threshold, 6),
        "description": finding.description,
    }


def build_report_data(
    batch_result: BatchResult,
    *,
    metrics: Optional[BatchMetrics] = None,
    regression_report: Optional[RegressionReport] = None,
    baseline: Optional[BaselineRecord] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured report payload from harness artifacts."""
    metrics = metrics or compute_metrics(batch_result)
    generated_at = _now_iso()
    title = title or f"Adaptive Skill Harness Report — {metrics.batch_id}"
    overall_status = _status_chip_label(batch_result, regression_report)

    baseline_record = baseline
    if baseline_record is None and regression_report and regression_report.baseline_id:
        baseline_record = BaselineRecord(
            baseline_id=regression_report.baseline_id,
            label=regression_report.baseline_label,
            system_version="",
            locked_at="",
            metrics=metrics,
        )

    regression_findings = []
    if regression_report is not None:
        regression_findings = [
            _finding_to_row(f) for f in regression_report.findings_by_severity()
        ]

    slowest_cases = sorted(
        metrics.case_metrics,
        key=lambda item: item.duration_ms,
        reverse=True,
    )[:5]
    total_cases = metrics.total
    runtime_coverage = {
        "attempt_count": metrics.runtime_metric_coverage.get("attempt_count", 0),
        "retry_count": metrics.runtime_metric_coverage.get("retry_count", 0),
        "fallback_count": metrics.runtime_metric_coverage.get("fallback_count", 0),
        "total_tokens": metrics.runtime_metric_coverage.get("total_tokens", 0),
        "estimated_cost": metrics.runtime_metric_coverage.get("estimated_cost", 0),
    }
    runtime_totals = {
        "attempt_count": metrics.total_attempt_count,
        "retry_count": metrics.total_retry_count,
        "fallback_count": metrics.total_fallback_count,
        "prompt_tokens": metrics.total_prompt_tokens,
        "completion_tokens": metrics.total_completion_tokens,
        "total_tokens": metrics.total_tokens,
        "estimated_cost": metrics.total_estimated_cost,
    }
    runtime_averages = {
        "attempt_count": metrics.avg_attempt_count,
        "retry_count": metrics.avg_retry_count,
        "fallback_count": metrics.avg_fallback_count,
        "prompt_tokens": (metrics.total_prompt_tokens / total_cases) if total_cases else 0.0,
        "completion_tokens": (metrics.total_completion_tokens / total_cases) if total_cases else 0.0,
        "total_tokens": metrics.avg_total_tokens,
        "estimated_cost": metrics.avg_estimated_cost,
    }
    runtime_coverage_rates = {
        key: (value / total_cases) if total_cases else 0.0
        for key, value in runtime_coverage.items()
    }

    return {

        "title": title,
        "generated_at": generated_at,
        "overall_status": overall_status,
        "status_class": _status_chip_class(overall_status),
        "batch": {
            "batch_id": batch_result.batch_id,
            "system_version": batch_result.system_version,
            "started_at": batch_result.started_at,
            "ended_at": batch_result.ended_at,
            "duration_ms": round(batch_result.duration_ms, 2),
            "metadata": batch_result.metadata,
        },
        "summary": batch_result.summary.to_dict(),
        "metrics": metrics.to_dict(),
        "baseline": (
            {
                "baseline_id": baseline_record.baseline_id,
                "label": baseline_record.label,
                "system_version": baseline_record.system_version,
                "locked_at": baseline_record.locked_at,
                "notes": baseline_record.notes,
                "metadata": baseline_record.metadata,
            }
            if baseline_record is not None
            else None
        ),
        "regression": (
            {
                "verdict": regression_report.verdict,
                "passed": regression_report.passed,
                "summary": regression_report.summary,
                "has_critical": regression_report.has_critical,
                "has_high": regression_report.has_high,
                "thresholds": regression_report.thresholds.__dict__ if regression_report.thresholds else {},
                "findings": regression_findings,
            }
            if regression_report is not None
            else None
        ),
        "case_metrics": [case.to_dict() for case in metrics.case_metrics],
        "slowest_cases": [case.to_dict() for case in slowest_cases],
        "runtime": {
            "case_count": total_cases,
            "totals": runtime_totals,
            "averages": runtime_averages,
            "coverage": runtime_coverage,
            "coverage_rates": runtime_coverage_rates,
        },
        "runner_errors": batch_result.runner_errors,
        "layer_distribution": metrics.layer_distribution,
        "tag_slices": metrics.tag_slices,
    }



def render_markdown_report(
    batch_result: BatchResult,
    *,
    metrics: Optional[BatchMetrics] = None,
    regression_report: Optional[RegressionReport] = None,
    baseline: Optional[BaselineRecord] = None,
    title: Optional[str] = None,
) -> str:
    """Render a human-readable Markdown report."""
    report = build_report_data(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=title,
    )
    summary = report["summary"]
    batch = report["batch"]
    metrics_data = report["metrics"]
    regression = report["regression"]
    runtime = report["runtime"]

    def coverage_text(key: str) -> str:
        covered = runtime["coverage"].get(key, 0)
        case_count = runtime["case_count"]
        rate = runtime["coverage_rates"].get(key, 0.0)
        return f"{covered}/{case_count} ({_fmt_pct(rate)})"

    token_coverage_text = coverage_text("total_tokens")
    cost_coverage_text = coverage_text("estimated_cost")

    lines: List[str] = [

        f"# {report['title']}",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 总体状态：**{report['overall_status']}**",
        f"- Batch ID：`{batch['batch_id']}`",
        f"- System Version：`{batch['system_version']}`",
        f"- 开始时间：`{batch['started_at']}`",
        f"- 结束时间：`{batch['ended_at']}`",
        f"- 总耗时：`{_fmt_ms(batch['duration_ms'])}`",
        "",
        "## 1. 批次摘要",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| Total | {summary['total']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Partial | {summary['partial']} |",
        f"| Errored | {summary['errored']} |",
        f"| Pass Rate | {_fmt_pct(summary['pass_rate'])} |",
        f"| Avg Score | {_fmt_num(summary['avg_score'])} |",
        f"| Avg Duration | {_fmt_ms(summary['avg_duration_ms'])} |",
        f"| Hard Fail Count | {summary['hard_fail_count']} |",
        "",
        "## 2. 指标细项",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| Score StdDev | {_fmt_num(metrics_data['score_stdev'])} |",
        f"| Min Score | {_fmt_num(metrics_data['min_score'])} |",
        f"| Max Score | {_fmt_num(metrics_data['max_score'])} |",
        f"| P50 Duration | {_fmt_ms(metrics_data['p50_duration_ms'])} |",
        f"| P95 Duration | {_fmt_ms(metrics_data['p95_duration_ms'])} |",
        "",
        "### 运行指标",
        "",
        "| 指标 | Total | Avg/Case | Coverage |",
        "|---|---:|---:|---:|",
        f"| Attempt Count | {runtime['totals']['attempt_count']} | {_fmt_num(runtime['averages']['attempt_count'], 2)} | {coverage_text('attempt_count')} |",
        f"| Retry Count | {runtime['totals']['retry_count']} | {_fmt_num(runtime['averages']['retry_count'], 2)} | {coverage_text('retry_count')} |",
        f"| Fallback Count | {runtime['totals']['fallback_count']} | {_fmt_num(runtime['averages']['fallback_count'], 2)} | {coverage_text('fallback_count')} |",
        f"| Prompt Tokens | {runtime['totals']['prompt_tokens']} | {_fmt_num(runtime['averages']['prompt_tokens'], 2)} | {token_coverage_text} |",
        f"| Completion Tokens | {runtime['totals']['completion_tokens']} | {_fmt_num(runtime['averages']['completion_tokens'], 2)} | {token_coverage_text} |",
        f"| Total Tokens | {runtime['totals']['total_tokens']} | {_fmt_num(runtime['averages']['total_tokens'], 2)} | {token_coverage_text} |",
        f"| Estimated Cost | {_fmt_num(runtime['totals']['estimated_cost'], 6)} | {_fmt_num(runtime['averages']['estimated_cost'], 6)} | {cost_coverage_text} |",
        "",
        "### Layer Distribution",

        "",
        "| Layer | Cases |",
        "|---|---:|",
    ]

    if report["layer_distribution"]:
        for layer, count in sorted(report["layer_distribution"].items(), key=lambda item: item[0]):
            lines.append(f"| {layer} | {count} |")
    else:
        lines.append("| — | 0 |")

    lines.extend([
        "",
        "### Tag Slices",
        "",
        "| Tag | Total | Passed | Pass Rate | Avg Score |",
        "|---|---:|---:|---:|---:|",
    ])
    if report["tag_slices"]:
        for tag, slice_data in sorted(report["tag_slices"].items(), key=lambda item: item[0]):
            lines.append(
                f"| {tag} | {slice_data['total']} | {slice_data['passed']} | "
                f"{_fmt_pct(slice_data['pass_rate'])} | {_fmt_num(slice_data['avg_score'])} |"
            )
    else:
        lines.append("| — | 0 | 0 | 0.00% | 0.0000 |")

    lines.extend([
        "",
        "## 3. 回归对比",
        "",
    ])
    if report["baseline"]:
        baseline_data = report["baseline"]
        lines.extend([
            f"- Baseline：`{baseline_data['baseline_id']}` ({baseline_data['label'] or 'unlabelled'})",
            f"- Locked At：`{baseline_data['locked_at'] or 'unknown'}`",
            f"- Notes：{baseline_data['notes'] or '—'}",
            "",
        ])
    else:
        lines.extend([
            "- 未提供 baseline，对比段仅展示当前批次状态。",
            "",
        ])

    if regression is None:
        lines.extend([
            "- 未执行 regression 检查。",
            "",
        ])
    else:
        lines.extend([
            f"- Verdict：**{regression['verdict']}**",
            f"- Summary：{regression['summary'] or '—'}",
            f"- Has Critical：{regression['has_critical']}",
            f"- Has High：{regression['has_high']}",
            "",
            "| Severity | Metric | Baseline | Current | Delta | Threshold | Description |",
            "|---|---|---:|---:|---:|---:|---|",
        ])
        if regression["findings"]:
            for finding in regression["findings"]:
                lines.append(
                    f"| {finding['severity']} | {finding['metric']} | {finding['baseline_value']} | "
                    f"{finding['current_value']} | {finding['delta']} | {finding['threshold']} | "
                    f"{finding['description']} |"
                )
        else:
            lines.append("| — | — | — | — | — | — | 无回归发现 |")
        lines.append("")

    lines.extend([
        "## 4. Case 级明细",
        "",
        "| Case ID | Final Status | Score | Duration | Exec Status | Hard Fail | Layer | Attempts | Retries | Fallbacks | Tokens | Cost | Gen Attempts | Grader Summary |",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for case in report["case_metrics"]:
        lines.append(
            f"| {case['case_id']} | {case['final_status']} | {_fmt_num(case['final_score'])} | "
            f"{_fmt_ms(case['duration_ms'])} | {case['execution_status']} | {case['hard_fail']} | "
            f"{case['layer_used'] if case['layer_used'] is not None else '—'} | {case['attempt_count']} | "
            f"{case['retry_count']} | {case['fallback_count']} | {case['total_tokens']} | "
            f"{_fmt_num(case['estimated_cost'], 6)} | {_case_generation_attempt_count(case) or '—'} | {_case_grader_summary(case)} |"
        )
    if not report["case_metrics"]:
        lines.append("| — | — | 0.0000 | 0.00 ms | — | False | — | 0 | 0 | 0 | 0 | 0.000000 | — | — |")


    lines.extend([
        "",
        "### Grader 下钻",
        "",
    ])
    grader_detail_cases = [case for case in report["case_metrics"] if _case_has_grader_details(case)]
    if grader_detail_cases:
        for case in grader_detail_cases:
            lines.append(f"- `{case['case_id']}`")
            grader_summary = _case_grader_summary(case)
            if grader_summary != "—":
                lines.append(f"  - Dimensions: {grader_summary}")
            assertion_results = _case_assertion_results(case)
            if assertion_results:
                lines.append("  - Assertions:")
                for index, assertion in enumerate(assertion_results, start=1):
                    lines.append(f"    - [{index}] {_assertion_summary(assertion)}")
            grading_notes = _case_grading_notes(case)
            if grading_notes:
                lines.append("  - Notes:")
                for note in grading_notes:
                    lines.append(f"    - {note}")
    else:
        lines.append("- 无 grader 维度下钻数据")

    lines.extend([
        "",
        "### Decision Trace 下钻",
        "",
    ])
    decision_trace_cases = [case for case in report["case_metrics"] if _case_has_decision_trace(case)]
    if decision_trace_cases:
        for case in decision_trace_cases:
            lines.append(f"- `{case['case_id']}`")
            for index, trace in enumerate(_case_decision_trace(case), start=1):
                lines.append(f"  - [{index}] {_decision_trace_summary(trace)}")
                for extra_line in _decision_trace_extra_lines(trace):
                    lines.append(f"    - {extra_line}")
    else:
        lines.append("- 无 decision trace 数据")

    lines.extend([
        "",
        "### Layer 3 Retry Telemetry 下钻",
        "",
    ])
    generation_telemetry_cases = [case for case in report["case_metrics"] if _case_has_generation_telemetry(case)]
    if generation_telemetry_cases:
        for case in generation_telemetry_cases:
            lines.append(f"- `{case['case_id']}`")
            lines.append(f"  - Final Draft: {_generation_info_summary(case)}")
            attempts = _case_generation_attempts(case)
            if attempts:
                lines.append("  - Attempts:")
                for index, attempt in enumerate(attempts, start=1):
                    lines.append(f"    - [{index}] {_generation_attempt_summary(attempt)}")
    else:
        lines.append("- 无 Layer 3 retry telemetry 数据")

    lines.extend([
        "",
        "## 5. 最慢 Cases",

        "",
        "| Case ID | Duration | Final Status | Score |",
        "|---|---:|---|---:|",
    ])


    for case in report["slowest_cases"]:
        lines.append(
            f"| {case['case_id']} | {_fmt_ms(case['duration_ms'])} | {case['final_status']} | {_fmt_num(case['final_score'])} |"
        )
    if not report["slowest_cases"]:
        lines.append("| — | 0.00 ms | — | 0.0000 |")

    lines.extend([
        "",
        "## 6. Runner Errors",
        "",
    ])
    if report["runner_errors"]:
        for err in report["runner_errors"]:
            lines.append(
                f"- `{err.get('case_id', 'unknown')}` / `{err.get('grader_id', 'unknown')}` — "
                f"{err.get('error_type', 'Error')}: {err.get('error_message', '')}"
            )
    else:
        lines.append("- 无 runner 级异常")

    return "\n".join(lines) + "\n"


def render_html_report(
    batch_result: BatchResult,
    *,
    metrics: Optional[BatchMetrics] = None,
    regression_report: Optional[RegressionReport] = None,
    baseline: Optional[BaselineRecord] = None,
    title: Optional[str] = None,
) -> str:
    """Render a standalone HTML report."""
    report = build_report_data(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=title,
    )
    summary = report["summary"]
    batch = report["batch"]
    regression = report["regression"]
    runtime = report["runtime"]

    def esc(value: Any) -> str:

        return html.escape(str(value))

    def table(headers: List[str], rows: List[List[Any]]) -> str:
        thead = "".join(f"<th>{esc(header)}</th>" for header in headers)
        body_rows = []
        for row in rows:
            body_rows.append("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>")
        return (
            "<table><thead><tr>" + thead + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"
        )

    summary_rows = [
        ["Total", summary["total"]],
        ["Passed", summary["passed"]],
        ["Failed", summary["failed"]],
        ["Partial", summary["partial"]],
        ["Errored", summary["errored"]],
        ["Pass Rate", _fmt_pct(summary["pass_rate"])],
        ["Avg Score", _fmt_num(summary["avg_score"])],
        ["Avg Duration", _fmt_ms(summary["avg_duration_ms"])],
        ["Hard Fail Count", summary["hard_fail_count"]],
    ]
    metrics_rows = [
        ["Score StdDev", _fmt_num(report["metrics"]["score_stdev"])],
        ["Min Score", _fmt_num(report["metrics"]["min_score"])],
        ["Max Score", _fmt_num(report["metrics"]["max_score"])],
        ["P50 Duration", _fmt_ms(report["metrics"]["p50_duration_ms"])],
        ["P95 Duration", _fmt_ms(report["metrics"]["p95_duration_ms"])],
    ]

    def coverage_text(key: str) -> str:
        covered = runtime["coverage"].get(key, 0)
        case_count = runtime["case_count"]
        rate = runtime["coverage_rates"].get(key, 0.0)
        return f"{covered}/{case_count} ({_fmt_pct(rate)})"

    token_coverage_text = coverage_text("total_tokens")
    cost_coverage_text = coverage_text("estimated_cost")
    runtime_rows = [
        ["Attempt Count", runtime["totals"]["attempt_count"], _fmt_num(runtime["averages"]["attempt_count"], 2), coverage_text("attempt_count")],
        ["Retry Count", runtime["totals"]["retry_count"], _fmt_num(runtime["averages"]["retry_count"], 2), coverage_text("retry_count")],
        ["Fallback Count", runtime["totals"]["fallback_count"], _fmt_num(runtime["averages"]["fallback_count"], 2), coverage_text("fallback_count")],
        ["Prompt Tokens", runtime["totals"]["prompt_tokens"], _fmt_num(runtime["averages"]["prompt_tokens"], 2), token_coverage_text],
        ["Completion Tokens", runtime["totals"]["completion_tokens"], _fmt_num(runtime["averages"]["completion_tokens"], 2), token_coverage_text],
        ["Total Tokens", runtime["totals"]["total_tokens"], _fmt_num(runtime["averages"]["total_tokens"], 2), token_coverage_text],
        ["Estimated Cost", _fmt_num(runtime["totals"]["estimated_cost"], 6), _fmt_num(runtime["averages"]["estimated_cost"], 6), cost_coverage_text],
    ]

    layer_rows = [[layer, count] for layer, count in sorted(report["layer_distribution"].items(), key=lambda item: item[0])] or [["—", 0]]
    tag_rows = [
        [tag, data["total"], data["passed"], _fmt_pct(data["pass_rate"]), _fmt_num(data["avg_score"])]
        for tag, data in sorted(report["tag_slices"].items(), key=lambda item: item[0])
    ] or [["—", 0, 0, "0.00%", "0.0000"]]
    case_rows = [
        [
            case["case_id"],
            case["final_status"],
            _fmt_num(case["final_score"]),
            _fmt_ms(case["duration_ms"]),
            case["execution_status"],
            case["hard_fail"],
            case["layer_used"] if case["layer_used"] is not None else "—",
            case["attempt_count"],
            case["retry_count"],
            case["fallback_count"],
            case["total_tokens"],
            _fmt_num(case["estimated_cost"], 6),
            _case_generation_attempt_count(case) or "—",
            _case_grader_summary(case),
        ]
        for case in report["case_metrics"]
    ] or [["—", "—", "0.0000", "0.00 ms", "—", False, "—", 0, 0, 0, 0, "0.000000", "—", "—"]]



    slow_rows = [
        [case["case_id"], _fmt_ms(case["duration_ms"]), case["final_status"], _fmt_num(case["final_score"])]
        for case in report["slowest_cases"]
    ] or [["—", "0.00 ms", "—", "0.0000"]]
    regression_rows = []
    if regression is not None:
        regression_rows = [
            [
                finding["severity"],
                finding["metric"],
                finding["baseline_value"],
                finding["current_value"],
                finding["delta"],
                finding["threshold"],
                finding["description"],
            ]
            for finding in regression["findings"]
        ] or [["—", "—", "—", "—", "—", "—", "无回归发现"]]

    runner_errors_html = "".join(
        f"<li><code>{esc(err.get('case_id', 'unknown'))}</code> / <code>{esc(err.get('grader_id', 'unknown'))}</code> — {esc(err.get('error_type', 'Error'))}: {esc(err.get('error_message', ''))}</li>"
        for err in report["runner_errors"]
    ) or "<li>无 runner 级异常</li>"

    baseline_html = "<p>未提供 baseline。</p>"
    if report["baseline"]:
        baseline_html = (
            "<ul>"
            f"<li>Baseline ID: <code>{esc(report['baseline']['baseline_id'])}</code></li>"
            f"<li>Label: {esc(report['baseline']['label'] or 'unlabelled')}</li>"
            f"<li>Locked At: <code>{esc(report['baseline']['locked_at'] or 'unknown')}</code></li>"
            f"<li>Notes: {esc(report['baseline']['notes'] or '—')}</li>"
            "</ul>"
        )

    regression_html = "<p>未执行 regression 检查。</p>"
    if regression is not None:
        regression_html = (
            f"<p><strong>Verdict:</strong> {esc(regression['verdict'])}<br>"
            f"<strong>Summary:</strong> {esc(regression['summary'] or '—')}<br>"
            f"<strong>Has Critical:</strong> {esc(regression['has_critical'])}<br>"
            f"<strong>Has High:</strong> {esc(regression['has_high'])}</p>"
            + table(
                ["Severity", "Metric", "Baseline", "Current", "Delta", "Threshold", "Description"],
                regression_rows,
            )
        )

    grader_detail_html = "<p>无 grader 维度下钻数据</p>"
    grader_detail_blocks = []
    for case in report["case_metrics"]:
        if not _case_has_grader_details(case):
            continue

        summary_html = ""
        grader_summary = _case_grader_summary(case)
        if grader_summary != "—":
            summary_html += f"<p><strong>Dimensions:</strong> {esc(grader_summary)}</p>"

        assertion_results = _case_assertion_results(case)
        if assertion_results:
            assertion_items = "".join(
                f"<li>{esc(_assertion_summary(assertion))}</li>"
                for assertion in assertion_results
            )
            summary_html += f"<p><strong>Assertions:</strong></p><ul>{assertion_items}</ul>"

        grading_notes = _case_grading_notes(case)
        if grading_notes:
            note_items = "".join(f"<li>{esc(note)}</li>" for note in grading_notes)
            summary_html += f"<p><strong>Notes:</strong></p><ul>{note_items}</ul>"

        grader_detail_blocks.append(
            f"<details class=\"grader-detail\"><summary><code>{esc(case['case_id'])}</code> — {esc(case['final_status'])}</summary>{summary_html}</details>"
        )

    if grader_detail_blocks:
        grader_detail_html = "".join(grader_detail_blocks)

    decision_trace_html = "<p>无 decision trace 数据</p>"
    decision_trace_blocks = []
    for case in report["case_metrics"]:
        traces = _case_decision_trace(case)
        if not traces:
            continue

        trace_items = []
        for trace in traces:
            extra_lines = _decision_trace_extra_lines(trace)
            extra_html = ""
            if extra_lines:
                extra_html = "<ul>" + "".join(f"<li>{esc(line)}</li>" for line in extra_lines) + "</ul>"
            trace_items.append(
                f"<li>{esc(_decision_trace_summary(trace))}{extra_html}</li>"
            )

        decision_trace_blocks.append(
            f"<details class=\"grader-detail\"><summary><code>{esc(case['case_id'])}</code> — decision trace</summary><ul>{''.join(trace_items)}</ul></details>"
        )

    if decision_trace_blocks:
        decision_trace_html = "".join(decision_trace_blocks)

    generation_telemetry_html = "<p>无 Layer 3 retry telemetry 数据</p>"
    generation_telemetry_blocks = []
    for case in report["case_metrics"]:
        if not _case_has_generation_telemetry(case):
            continue

        attempts = _case_generation_attempts(case)
        attempts_html = ""
        if attempts:
            attempts_html = "<p><strong>Attempts:</strong></p><ul>" + "".join(
                f"<li>{esc(_generation_attempt_summary(attempt))}</li>"
                for attempt in attempts
            ) + "</ul>"

        generation_telemetry_blocks.append(
            "<details class=\"grader-detail\">"
            f"<summary><code>{esc(case['case_id'])}</code> — layer3 retry telemetry</summary>"
            f"<p><strong>Final Draft:</strong> {esc(_generation_info_summary(case))}</p>"
            f"{attempts_html}"
            "</details>"
        )

    if generation_telemetry_blocks:
        generation_telemetry_html = "".join(generation_telemetry_blocks)

    return f"""<!DOCTYPE html>



<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{esc(report['title'])}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #111831;
      --panel-2: #182241;
      --text: #e8edf7;
      --muted: #9eb0d1;
      --border: #2a3761;
      --pass: #1f8b4c;
      --warn: #a56a00;
      --fail: #a63c3c;
      --neutral: #40507b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }}
    .page {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    .hero, .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 20px; margin-bottom: 16px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .meta {{ color: var(--muted); line-height: 1.7; }}
    .chip {{ display: inline-block; padding: 6px 12px; border-radius: 999px; font-weight: 700; font-size: 12px; letter-spacing: 0.04em; }}
    .chip.pass {{ background: rgba(31,139,76,0.18); color: #7fe5a7; border: 1px solid rgba(127,229,167,0.28); }}
    .chip.warn {{ background: rgba(165,106,0,0.18); color: #ffd279; border: 1px solid rgba(255,210,121,0.28); }}
    .chip.fail {{ background: rgba(166,60,60,0.18); color: #ff9c9c; border: 1px solid rgba(255,156,156,0.28); }}
    .chip.neutral {{ background: rgba(64,80,123,0.25); color: #c8d5f3; border: 1px solid rgba(200,213,243,0.2); }}
    h2 {{ margin-top: 0; font-size: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    code {{ background: var(--panel-2); border-radius: 6px; padding: 2px 6px; }}
    ul {{ margin: 0; padding-left: 20px; }}
    .grader-detail {{ border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; background: var(--panel-2); margin-bottom: 12px; }}
    .grader-detail summary {{ cursor: pointer; font-weight: 600; }}
    .grader-detail p {{ margin: 12px 0 8px; }}
  </style>

</head>
<body>
  <div class=\"page\">
    <section class=\"hero\">
      <div class=\"chip {esc(report['status_class'])}\">{esc(report['overall_status'])}</div>
      <h1>{esc(report['title'])}</h1>
      <div class=\"meta\">
        <div>Batch ID: <code>{esc(batch['batch_id'])}</code></div>
        <div>System Version: <code>{esc(batch['system_version'])}</code></div>
        <div>Started At: <code>{esc(batch['started_at'])}</code></div>
        <div>Ended At: <code>{esc(batch['ended_at'])}</code></div>
        <div>Generated At: <code>{esc(report['generated_at'])}</code></div>
        <div>Total Duration: <code>{esc(_fmt_ms(batch['duration_ms']))}</code></div>
      </div>
    </section>

    <div class=\"grid\">
      <section class=\"panel\">
        <h2>批次摘要</h2>
        {table(["Metric", "Value"], summary_rows)}
      </section>
      <section class=\"panel\">
        <h2>指标细项</h2>
        {table(["Metric", "Value"], metrics_rows)}
      </section>
      <section class=\"panel\">
        <h2>运行指标</h2>
        {table(["Metric", "Total", "Avg/Case", "Coverage"], runtime_rows)}
      </section>
    </div>

    <div class=\"grid\">
      <section class=\"panel\">
        <h2>Layer Distribution</h2>
        {table(["Layer", "Cases"], layer_rows)}
      </section>
      <section class=\"panel\">
        <h2>Tag Slices</h2>
        {table(["Tag", "Total", "Passed", "Pass Rate", "Avg Score"], tag_rows)}
      </section>
    </div>


    <section class=\"panel\">
      <h2>回归对比</h2>
      {baseline_html}
      {regression_html}
    </section>

    <section class=\"panel\">
      <h2>Case 级明细</h2>
      {table(["Case ID", "Final Status", "Score", "Duration", "Exec Status", "Hard Fail", "Layer", "Attempts", "Retries", "Fallbacks", "Tokens", "Cost", "Gen Attempts", "Grader Summary"], case_rows)}


    </section>

    <section class=\"panel\">
      <h2>Grader 下钻</h2>
      {grader_detail_html}
    </section>

    <section class=\"panel\">
      <h2>Decision Trace 下钻</h2>
      {decision_trace_html}
    </section>

    <section class=\"panel\">
      <h2>Layer 3 Retry Telemetry 下钻</h2>
      {generation_telemetry_html}
    </section>

    <section class=\"panel\">
      <h2>最慢 Cases</h2>



      {table(["Case ID", "Duration", "Final Status", "Score"], slow_rows)}
    </section>

    <section class=\"panel\">
      <h2>Runner Errors</h2>
      <ul>{runner_errors_html}</ul>
    </section>
  </div>
</body>
</html>
"""


def build_report_bundle(
    batch_result: BatchResult,
    *,
    metrics: Optional[BatchMetrics] = None,
    regression_report: Optional[RegressionReport] = None,
    baseline: Optional[BaselineRecord] = None,
    title: Optional[str] = None,
) -> ReportBundle:
    """Build report data plus Markdown / HTML renderings."""
    metrics = metrics or compute_metrics(batch_result)
    report_data = build_report_data(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=title,
    )
    markdown = render_markdown_report(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=report_data["title"],
    )
    html_report = render_html_report(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=report_data["title"],
    )
    return ReportBundle(
        batch_id=batch_result.batch_id,
        title=report_data["title"],
        generated_at=report_data["generated_at"],
        report_data=report_data,
        markdown=markdown,
        html=html_report,
    )


def write_report_bundle(
    output_dir: str,
    batch_result: BatchResult,
    *,
    metrics: Optional[BatchMetrics] = None,
    regression_report: Optional[RegressionReport] = None,
    baseline: Optional[BaselineRecord] = None,
    title: Optional[str] = None,
    file_stem: Optional[str] = None,
) -> WrittenReportBundle:
    """Persist JSON + Markdown + HTML reports to *output_dir*."""
    bundle = build_report_bundle(
        batch_result,
        metrics=metrics,
        regression_report=regression_report,
        baseline=baseline,
        title=title,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_slug(file_stem or f"harness-report-{batch_result.batch_id}")

    json_path = out_dir / f"{stem}.json"
    markdown_path = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"

    json_path.write_text(
        json.dumps(bundle.report_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(bundle.markdown, encoding="utf-8")
    html_path.write_text(bundle.html, encoding="utf-8")

    return WrittenReportBundle(
        output_dir=str(out_dir),
        markdown_path=str(markdown_path),
        html_path=str(html_path),
        json_path=str(json_path),
    )


__all__ = [
    "ReportBundle",
    "WrittenReportBundle",
    "build_report_data",
    "render_markdown_report",
    "render_html_report",
    "build_report_bundle",
    "write_report_bundle",
]
