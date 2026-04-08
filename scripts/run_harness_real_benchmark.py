"""Run the seeded real benchmark suite for Adaptive Skill System harness.

Compared with ``run_harness_ci_suite.py``:
- this script executes the *real* solver path instead of emitting synthetic rows
- it still uses isolated seed data, so the run is reproducible across machines
- it can optionally lock a baseline and/or compare against an existing baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adaptive_skill import __version__
from adaptive_skill.harness.baseline import BaselineRecord
from adaptive_skill.harness.benchmark_suite import (
    BENCHMARK_SUITE_ID,
    DEFAULT_BATCH_ID,
    run_seeded_real_benchmark,
)
from adaptive_skill.harness.cli import load_baseline_record
from adaptive_skill.harness.metrics import compute_metrics
from adaptive_skill.harness.regression import RegressionThresholds, check_regression
from adaptive_skill.harness.reporting import write_report_bundle

DEFAULT_OUTPUT_DIR = ".benchmark-artifacts/real-benchmark"
DEFAULT_BATCH_FILE = "real-benchmark-batch-result.json"
DEFAULT_METRICS_FILE = "real-benchmark-metrics.json"
DEFAULT_FILE_STEM = "adaptive-skill-harness-real-benchmark"
DEFAULT_REPORT_TITLE = "Adaptive Skill Harness Real Benchmark"
DEFAULT_BASELINE_ID = "real-benchmark-v2"
DEFAULT_BASELINE_LABEL = "real-benchmark-v2"
DEFAULT_P95_LATENCY_INCREASE_PCT = 200.0




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行 seeded real benchmark，生成 BatchResult / Metrics / Report，并可锁 baseline。"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--batch-file",
        default=DEFAULT_BATCH_FILE,
        help=f"BatchResult 输出文件名，默认 {DEFAULT_BATCH_FILE}",
    )
    parser.add_argument(
        "--metrics-file",
        default=DEFAULT_METRICS_FILE,
        help=f"Metrics 输出文件名，默认 {DEFAULT_METRICS_FILE}",
    )
    parser.add_argument(
        "--file-stem",
        default=DEFAULT_FILE_STEM,
        help=f"报告文件名前缀，默认 {DEFAULT_FILE_STEM}",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_REPORT_TITLE,
        help=f"报告标题，默认 {DEFAULT_REPORT_TITLE}",
    )
    parser.add_argument(
        "--system-version",
        default=__version__,
        help="写入 BatchResult/Baseline 的 system_version，默认 adaptive_skill.__version__",
    )
    parser.add_argument(
        "--batch-id",
        default=DEFAULT_BATCH_ID,
        help=f"批次 ID，默认 {DEFAULT_BATCH_ID}",
    )
    parser.add_argument(
        "--baseline-out",
        help="可选：把本次 metrics 额外锁定成 baseline JSON 到指定路径",
    )
    parser.add_argument(
        "--baseline-id",
        default=DEFAULT_BASELINE_ID,
        help=f"配合 --baseline-out 使用的 baseline_id，默认 {DEFAULT_BASELINE_ID}",
    )
    parser.add_argument(
        "--baseline-label",
        default=DEFAULT_BASELINE_LABEL,
        help=f"配合 --baseline-out 使用的 baseline label，默认 {DEFAULT_BASELINE_LABEL}",
    )
    parser.add_argument(
        "--baseline",
        help="可选：已有 baseline JSON 路径。提供后会执行 regression check 并把结果写进 report bundle。",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="当 regression verdict=FAIL 时返回退出码 2。",
    )

    thresholds = parser.add_argument_group("Regression thresholds")
    thresholds.add_argument("--pass-rate-drop", type=float, default=0.05)
    thresholds.add_argument("--avg-score-drop", type=float, default=0.05)
    thresholds.add_argument("--hard-fail-increase", type=int, default=0)
    thresholds.add_argument("--error-rate-increase", type=float, default=0.05)
    thresholds.add_argument(
        "--p95-latency-increase-pct",
        type=float,
        default=DEFAULT_P95_LATENCY_INCREASE_PCT,
    )

    thresholds.add_argument("--case-score-drop", type=float, default=0.10)
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_thresholds(args: argparse.Namespace) -> RegressionThresholds:
    return RegressionThresholds(
        pass_rate_drop=args.pass_rate_drop,
        avg_score_drop=args.avg_score_drop,
        hard_fail_increase=args.hard_fail_increase,
        error_rate_increase=args.error_rate_increase,
        p95_latency_increase_pct=args.p95_latency_increase_pct,
        case_score_drop=args.case_score_drop,
    )


def _build_baseline(metrics, *, baseline_id: str, label: str, system_version: str) -> BaselineRecord:
    return BaselineRecord(
        baseline_id=baseline_id,
        label=label,
        system_version=system_version,
        locked_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics,
        notes=(
            "Locked from the seeded real benchmark suite generated by "
            "scripts/run_harness_real_benchmark.py."
        ),
        metadata={
            "suite": BENCHMARK_SUITE_ID,
            "generated_by": "scripts/run_harness_real_benchmark.py",
            "seed_mode": "in-memory-kb-ltm",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    batch_path = output_dir / args.batch_file
    metrics_path = output_dir / args.metrics_file
    reports_dir = output_dir / "reports"

    batch = run_seeded_real_benchmark(
        system_version=args.system_version,
        batch_id=args.batch_id,
    )
    metrics = compute_metrics(batch)

    _write_json(batch_path, batch.to_dict())
    _write_json(metrics_path, metrics.to_dict(rounded=False))

    baseline = load_baseline_record(args.baseline) if args.baseline else None
    regression_report = None
    if baseline is not None:
        regression_report = check_regression(metrics, baseline, thresholds=_build_thresholds(args))

    written = write_report_bundle(
        str(reports_dir),
        batch,
        metrics=metrics,
        baseline=baseline,
        regression_report=regression_report,
        title=args.title,
        file_stem=args.file_stem,
    )

    print("Seeded real benchmark completed:")
    print(f"  BatchResult : {batch_path}")
    print(f"  Metrics     : {metrics_path}")
    print(f"  Report JSON : {written.json_path}")
    print(f"  Report MD   : {written.markdown_path}")
    print(f"  Report HTML : {written.html_path}")
    print(
        "  Summary     : "
        f"total={batch.summary.total}, passed={batch.summary.passed}, "
        f"failed={batch.summary.failed}, partial={batch.summary.partial}, errored={batch.summary.errored}, "
        f"pass_rate={batch.summary.pass_rate:.4f}, avg_score={batch.summary.avg_score:.4f}"
    )

    if args.baseline_out:
        baseline_path = Path(args.baseline_out)
        record = _build_baseline(
            metrics,
            baseline_id=args.baseline_id,
            label=args.baseline_label,
            system_version=args.system_version,
        )
        _write_json(baseline_path, record.to_dict())
        print(f"  Baseline    : {baseline_path}")

    if regression_report is not None:
        print(f"Regression verdict: {regression_report.verdict}")
        print(f"Regression summary: {regression_report.summary}")
        if args.fail_on_regression and not regression_report.passed:
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
