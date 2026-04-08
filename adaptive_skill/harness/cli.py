"""Command-line entry point for Adaptive Skill System harness reporting.

This CLI turns a persisted ``BatchResult.to_dict()`` JSON payload into the P4
report bundle (JSON + Markdown + HTML), and can optionally compare the batch
against a locked baseline to surface regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .baseline import BaselineRecord
from .batch_runner import BatchResult, BatchSummary
from .metrics import compute_metrics
from .reporting import write_report_bundle
from .regression import RegressionThresholds, check_regression
from .specs import RunResult


def _load_json_file(path: Path) -> Dict[str, Any]:
    """Load a JSON object from *path* with user-friendly errors."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{path}（{exc.msg}）") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"JSON 根节点必须是对象：{path}")
    return payload


def _ensure_dict(value: Any) -> Dict[str, Any]:
    """Return *value* when it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _ensure_list_of_dicts(value: Any, field_name: str) -> List[Dict[str, Any]]:
    """Validate a JSON list-of-objects field."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"字段 `{field_name}` 必须是数组")

    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"字段 `{field_name}` 的第 {index} 项必须是对象")
        rows.append(item)
    return rows


def _to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion for tolerant JSON loading."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    """Best-effort int conversion for tolerant JSON loading."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rebuild_summary_fallback(results: List[RunResult]) -> BatchSummary:
    """Derive a BatchSummary from RunResult rows when JSON lacks one."""
    total = len(results)
    passed = sum(1 for row in results if row.final_status == "pass")
    failed = sum(1 for row in results if row.final_status == "fail")
    errored = sum(1 for row in results if row.final_status == "error")
    partial = sum(1 for row in results if row.final_status == "partial")
    hard_fail_count = sum(1 for row in results if row.metadata.get("hard_fail") is True)
    avg_score = sum(row.final_score for row in results) / total if total else 0.0
    avg_duration_ms = sum(row.duration_ms for row in results) / total if total else 0.0
    pass_rate = passed / total if total else 0.0
    return BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        partial=partial,
        pass_rate=pass_rate,
        avg_score=avg_score,
        avg_duration_ms=avg_duration_ms,
        hard_fail_count=hard_fail_count,
    )


def load_batch_result(path: str) -> BatchResult:
    """Reconstruct a BatchResult from the JSON emitted by ``to_dict()``.

    Parameters
    ----------
    path:
        Path to the persisted batch JSON file.
    """
    source = Path(path)
    payload = _load_json_file(source)

    if "report_data" in payload and "results" not in payload:
        raise ValueError(
            "输入文件看起来是 report bundle JSON，不是 BatchResult JSON。"
            "请传入 `BatchResult.to_dict()` 持久化后的原始批次结果文件。"
        )

    raw_results = _ensure_list_of_dicts(payload.get("results"), "results")
    if not raw_results:
        raise ValueError("BatchResult JSON 缺少 `results`，无法生成报告")

    results = [
        RunResult(
            run_id=str(item.get("run_id", "")),
            case_id=str(item.get("case_id", "")),
            grader_id=str(item.get("grader_id", "")),
            system_version=str(item.get("system_version", payload.get("system_version", ""))),
            started_at=str(item.get("started_at", "")),
            ended_at=str(item.get("ended_at", "")),
            duration_ms=_to_float(item.get("duration_ms"), 0.0),
            execution_status=str(item.get("execution_status", "error")),
            final_status=str(item.get("final_status", "error")),
            final_score=_to_float(item.get("final_score"), 0.0),
            solve_response=_ensure_dict(item.get("solve_response")),
            execution_trace_summary=_ensure_dict(item.get("execution_trace_summary")),
            decision_trace=_ensure_list_of_dicts(item.get("decision_trace"), "decision_trace"),
            grader_scores=_ensure_dict(item.get("grader_scores")),

            failure_reason=item.get("failure_reason"),
            error_code=item.get("error_code"),
            metadata=_ensure_dict(item.get("metadata")),
        )
        for item in raw_results
    ]

    fallback_summary = _rebuild_summary_fallback(results)
    raw_summary = payload.get("summary")
    if raw_summary is not None and not isinstance(raw_summary, dict):
        raise ValueError("字段 `summary` 必须是对象")
    raw_summary = raw_summary or {}

    summary = BatchSummary(
        total=_to_int(raw_summary.get("total"), fallback_summary.total),
        passed=_to_int(raw_summary.get("passed"), fallback_summary.passed),
        failed=_to_int(raw_summary.get("failed"), fallback_summary.failed),
        errored=_to_int(raw_summary.get("errored"), fallback_summary.errored),
        partial=_to_int(raw_summary.get("partial"), fallback_summary.partial),
        pass_rate=_to_float(raw_summary.get("pass_rate"), fallback_summary.pass_rate),
        avg_score=_to_float(raw_summary.get("avg_score"), fallback_summary.avg_score),
        avg_duration_ms=_to_float(raw_summary.get("avg_duration_ms"), fallback_summary.avg_duration_ms),
        hard_fail_count=_to_int(raw_summary.get("hard_fail_count"), fallback_summary.hard_fail_count),
    )

    return BatchResult(
        batch_id=str(payload.get("batch_id", source.stem)),
        system_version=str(payload.get("system_version", "unknown")),
        started_at=str(payload.get("started_at", "")),
        ended_at=str(payload.get("ended_at", "")),
        duration_ms=_to_float(payload.get("duration_ms"), 0.0),
        summary=summary,
        results=results,
        runner_errors=_ensure_list_of_dicts(payload.get("runner_errors"), "runner_errors"),
        metadata=_ensure_dict(payload.get("metadata")),
    )


def load_baseline_record(path: str) -> BaselineRecord:
    """Load a BaselineRecord from the JSON emitted by BaselineRecord.to_dict()."""
    payload = _load_json_file(Path(path))
    return BaselineRecord.from_dict(payload)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="adaptive-skill-report",
        description=(
            "从持久化的 BatchResult JSON 生成 Adaptive Skill Harness 的 "
            "JSON / Markdown / HTML 报告。"
        ),
    )
    parser.add_argument(
        "batch_result",
        help="BatchResult JSON 文件路径（来源：BatchResult.to_dict()）",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="报告输出目录。默认使用 <batch_result 所在目录>/reports",
    )
    parser.add_argument(
        "--baseline",
        help="可选：BaselineRecord JSON 路径。提供后会自动执行 regression check。",
    )
    parser.add_argument(
        "--title",
        help="可选：覆盖报告标题。",
    )
    parser.add_argument(
        "--file-stem",
        help="可选：输出文件名前缀，不含扩展名。",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="当 regression verdict 为 FAIL 时返回退出码 2。",
    )

    thresholds = parser.add_argument_group("Regression thresholds")
    thresholds.add_argument("--pass-rate-drop", type=float, default=0.05, help="允许的 pass_rate 最大下降值，默认 0.05")
    thresholds.add_argument("--avg-score-drop", type=float, default=0.05, help="允许的 avg_score 最大下降值，默认 0.05")
    thresholds.add_argument("--hard-fail-increase", type=int, default=0, help="允许的 hard_fail_count 最大增长值，默认 0")
    thresholds.add_argument("--error-rate-increase", type=float, default=0.05, help="允许的 error rate 最大增长值，默认 0.05")
    thresholds.add_argument("--p95-latency-increase-pct", type=float, default=50.0, help="允许的 P95 延迟最大增长百分比，默认 50")
    thresholds.add_argument("--case-score-drop", type=float, default=0.1, help="允许的单 case 分数最大下降值，默认 0.1")
    return parser


def _build_thresholds(args: argparse.Namespace) -> RegressionThresholds:
    """Translate argparse fields into a RegressionThresholds object."""
    return RegressionThresholds(
        pass_rate_drop=args.pass_rate_drop,
        avg_score_drop=args.avg_score_drop,
        hard_fail_increase=args.hard_fail_increase,
        error_rate_increase=args.error_rate_increase,
        p95_latency_increase_pct=args.p95_latency_increase_pct,
        case_score_drop=args.case_score_drop,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point.

    Returns
    -------
    int
        0 on success, 1 on invalid input or IO failure, 2 when
        ``--fail-on-regression`` is enabled and regression check fails.
    """
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        batch_result = load_batch_result(args.batch_result)
        output_dir = args.output_dir or str(Path(args.batch_result).resolve().parent / "reports")

        baseline = load_baseline_record(args.baseline) if args.baseline else None
        metrics = compute_metrics(batch_result)
        regression_report = None
        if baseline is not None:
            regression_report = check_regression(
                metrics,
                baseline,
                thresholds=_build_thresholds(args),
            )

        written = write_report_bundle(
            output_dir,
            batch_result,
            metrics=metrics,
            baseline=baseline,
            regression_report=regression_report,
            title=args.title,
            file_stem=args.file_stem,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("Generated report bundle:")
    print(f"  JSON : {written.json_path}")
    print(f"  Markdown : {written.markdown_path}")
    print(f"  HTML : {written.html_path}")

    if regression_report is not None:
        print(f"Regression verdict: {regression_report.verdict}")
        print(f"Regression summary: {regression_report.summary}")
        if args.fail_on_regression and not regression_report.passed:
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
