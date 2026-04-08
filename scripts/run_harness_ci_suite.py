"""Build a deterministic harness smoke batch for CI report generation.

Why synthetic instead of running the full solver here?
- `pytest tests -q` is already the main correctness gate for repository code.
- The reporting CLI / baseline / regression path needs a stable, deterministic
  batch input so CI artifacts and regression verdicts do not flap with runtime
  variance or local memory state.

This script therefore emits a curated `BatchResult` + `BatchMetrics` pair that
exercise PASS / PARTIAL / FAIL cases across all three layers (4 cases per layer,
N=12) so that layer-slice pass_rates have minimal statistical meaning and the
regression gate is not trivially satisfied by a single data point.

Design choices:
- N=12 (4 per layer) keeps the smoke suite fast while giving each layer-slice
  enough samples for a meaningful pass_rate.
- Each layer covers: high-confidence pass, mid-confidence pass, borderline
  partial, and an explicit fail — so the baseline captures the realistic
  distribution rather than an artificially optimistic one.
- Timestamps are offset deterministically (not all identical) so duration
  statistics are non-degenerate.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adaptive_skill import __version__
from adaptive_skill.harness.baseline import BaselineRecord
from adaptive_skill.harness.batch_runner import BatchResult, BatchSummary
from adaptive_skill.harness.metrics import compute_metrics
from adaptive_skill.harness.specs import RunResult


DEFAULT_BATCH_FILENAME = "harness-batch-result.json"
DEFAULT_METRICS_FILENAME = "harness-metrics.json"
DEFAULT_BATCH_ID = "adaptive-skill-harness-ci-smoke"
DEFAULT_BASELINE_ID = "ci-smoke-v1"
DEFAULT_BASELINE_LABEL = "ci-smoke-v1"

# 12 cases: 4 per layer, covering pass / partial / fail distribution
FIXTURE_CASE_IDS = [
    # Layer 1 — direct KB lookup
    "ci-layer1-high-conf",
    "ci-layer1-mid-conf",
    "ci-layer1-partial",
    "ci-layer1-fail",
    # Layer 2 — composition
    "ci-layer2-compose-pass",
    "ci-layer2-compose-pass-b",
    "ci-layer2-compose-partial",
    "ci-layer2-compose-fail",
    # Layer 3 — generation
    "ci-layer3-llm-pass",
    "ci-layer3-heuristic-pass",
    "ci-layer3-partial",
    "ci-layer3-fail",
]

# Base timestamp for deterministic but non-degenerate time offsets (ms).
# Each case gets a unique started_at / ended_at derived from its index.
_BASE_TS = "2026-04-02T00:00:00+00:00"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "生成一个确定性的 Adaptive Skill harness smoke batch，"
            "供 CI 的 reporting / baseline / regression 链路使用。"
        )
    )
    parser.add_argument(
        "--output-dir",
        default=".ci-artifacts/harness",
        help="输出目录，默认 .ci-artifacts/harness",
    )
    parser.add_argument(
        "--batch-file",
        default=DEFAULT_BATCH_FILENAME,
        help=f"BatchResult 输出文件名，默认 {DEFAULT_BATCH_FILENAME}",
    )
    parser.add_argument(
        "--metrics-file",
        default=DEFAULT_METRICS_FILENAME,
        help=f"Metrics 输出文件名，默认 {DEFAULT_METRICS_FILENAME}",
    )
    parser.add_argument(
        "--system-version",
        default=__version__,
        help="写入 BatchResult/Baseline 的 system_version，默认取 adaptive_skill.__version__",
    )
    parser.add_argument(
        "--batch-id",
        default=DEFAULT_BATCH_ID,
        help=f"批次 ID，默认 {DEFAULT_BATCH_ID}",
    )
    parser.add_argument(
        "--baseline-out",
        help="可选：把当前 metrics 额外锁定为 baseline JSON 到指定路径",
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
    return parser


def _ts_offset(seconds: float) -> str:
    """Return a deterministic ISO-8601 timestamp offset from the base by `seconds`."""
    from datetime import timedelta
    base = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=seconds)).isoformat()


def _rr(
    *,
    case_id: str,
    grader_id: str,
    system_version: str,
    final_status: str,
    final_score: float,
    duration_ms: float,
    layer_used: int,
    tags: List[str],
    start_offset_s: float = 0.0,
) -> RunResult:
    """Build one deterministic RunResult fixture.

    Args:
        start_offset_s: seconds after base timestamp for started_at; used to
            produce non-degenerate duration statistics across the batch.
    """
    started_at = _ts_offset(start_offset_s)
    ended_at = _ts_offset(start_offset_s + duration_ms / 1000.0)
    # fail cases still executed (execution_status="success"), just graded fail
    execution_status = "error" if final_status == "error" else "success"
    # result_present = 0 for genuine fail/error so grader scores are realistic
    result_present = 0.0 if final_status in ("fail", "error") else 1.0
    return RunResult(
        run_id=f"run-{uuid.uuid4()}",
        case_id=case_id,
        grader_id=grader_id,
        system_version=system_version,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        execution_status=execution_status,
        final_status=final_status,
        final_score=final_score,
        solve_response={
            "status": final_status,
            "result": f"synthetic result for {case_id}",
            "confidence": final_score,
        },
        execution_trace_summary={"layer_used": layer_used},
        grader_scores={
            "result_present": result_present,
            "quality": round(final_score, 4),
        },
        metadata={
            "hard_fail": False,
            "tags": tags,
            "suite": "ci-smoke",
            "duration_source": "synthetic_ci_fixture",
            "layer_3_auto_generated": layer_used == 3,
        },
    )


# ---------------------------------------------------------------------------
# Fixture definitions — 12 cases (4 per layer)
#
# Each layer slice contains:
#   - 2 pass cases  (high-confidence and mid-confidence)
#   - 1 partial     (borderline, score just above quality gate 0.70)
#   - 1 fail        (score below quality gate)
#
# Layer-slice pass_rates: L1=0.50, L2=0.50, L3=0.50 (realistic, not 100%/0%)
# Overall pass_rate: 6/12 = 0.50  avg_score ≈ 0.765
# ---------------------------------------------------------------------------
_CASE_SPECS = [
    # --- Layer 1 ---
    dict(case_id="ci-layer1-high-conf",   grader_id="grader-ci-layer1-high",    final_status="pass",    final_score=0.96, duration_ms=72.0,  layer_used=1, tags=["ci", "layer1", "pass"],    start_offset_s=0.0),
    dict(case_id="ci-layer1-mid-conf",    grader_id="grader-ci-layer1-mid",     final_status="pass",    final_score=0.82, duration_ms=88.0,  layer_used=1, tags=["ci", "layer1", "pass"],    start_offset_s=0.5),
    dict(case_id="ci-layer1-partial",     grader_id="grader-ci-layer1-partial", final_status="partial", final_score=0.73, duration_ms=104.0, layer_used=1, tags=["ci", "layer1", "partial"], start_offset_s=1.0),
    dict(case_id="ci-layer1-fail",        grader_id="grader-ci-layer1-fail",    final_status="fail",    final_score=0.45, duration_ms=61.0,  layer_used=1, tags=["ci", "layer1", "fail"],    start_offset_s=1.5),
    # --- Layer 2 ---
    dict(case_id="ci-layer2-compose-pass",   grader_id="grader-ci-layer2-pass-a",  final_status="pass",    final_score=0.91, duration_ms=118.0, layer_used=2, tags=["ci", "layer2", "pass"],    start_offset_s=2.0),
    dict(case_id="ci-layer2-compose-pass-b", grader_id="grader-ci-layer2-pass-b",  final_status="pass",    final_score=0.79, duration_ms=133.0, layer_used=2, tags=["ci", "layer2", "pass"],    start_offset_s=2.5),
    dict(case_id="ci-layer2-compose-partial",grader_id="grader-ci-layer2-partial", final_status="partial", final_score=0.71, duration_ms=145.0, layer_used=2, tags=["ci", "layer2", "partial"], start_offset_s=3.0),
    dict(case_id="ci-layer2-compose-fail",   grader_id="grader-ci-layer2-fail",    final_status="fail",    final_score=0.52, duration_ms=99.0,  layer_used=2, tags=["ci", "layer2", "fail"],    start_offset_s=3.5),
    # --- Layer 3 ---
    dict(case_id="ci-layer3-llm-pass",    grader_id="grader-ci-layer3-llm",     final_status="pass",    final_score=0.88, duration_ms=210.0, layer_used=3, tags=["ci", "layer3", "pass"],    start_offset_s=4.0),
    dict(case_id="ci-layer3-heuristic-pass", grader_id="grader-ci-layer3-heur",final_status="pass",    final_score=0.76, duration_ms=155.0, layer_used=3, tags=["ci", "layer3", "pass"],    start_offset_s=4.5),
    dict(case_id="ci-layer3-partial",     grader_id="grader-ci-layer3-partial", final_status="partial", final_score=0.72, duration_ms=180.0, layer_used=3, tags=["ci", "layer3", "partial"], start_offset_s=5.0),
    dict(case_id="ci-layer3-fail",        grader_id="grader-ci-layer3-fail",    final_status="fail",    final_score=0.38, duration_ms=140.0, layer_used=3, tags=["ci", "layer3", "fail"],    start_offset_s=5.5),
]


def build_batch(system_version: str, batch_id: str) -> BatchResult:
    results = [
        _rr(system_version=system_version, **spec)
        for spec in _CASE_SPECS
    ]
    total = len(results)
    passed = sum(1 for row in results if row.final_status == "pass")
    failed = sum(1 for row in results if row.final_status == "fail")
    errored = sum(1 for row in results if row.final_status == "error")
    partial = sum(1 for row in results if row.final_status == "partial")
    summary = BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        partial=partial,
        pass_rate=passed / total if total else 0.0,
        avg_score=sum(row.final_score for row in results) / total if total else 0.0,
        avg_duration_ms=sum(row.duration_ms for row in results) / total if total else 0.0,
        hard_fail_count=0,
    )
    return BatchResult(
        batch_id=batch_id,
        system_version=system_version,
        started_at=_ts_offset(0.0),
        ended_at=_ts_offset(6.0),
        duration_ms=6000.0,
        summary=summary,
        results=results,
        metadata={
            "suite": "ci-smoke",
            "generated_by": "scripts/run_harness_ci_suite.py",
            "fixture_case_ids": FIXTURE_CASE_IDS,
            "note": (
                "Deterministic smoke batch (N=12, 4 per layer) for "
                "reporting/regression CI. Each layer covers pass/partial/fail."
            ),
        },
    )


def _build_baseline(metrics, *, baseline_id: str, label: str, system_version: str) -> BaselineRecord:
    return BaselineRecord(
        baseline_id=baseline_id,
        label=label,
        system_version=system_version,
        locked_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics,
        notes=(
            "Locked from the deterministic CI smoke batch generated by "
            "scripts/run_harness_ci_suite.py."
        ),
        metadata={
            "suite": "ci-smoke",
            "fixture_case_ids": FIXTURE_CASE_IDS,
            "generated_by": "scripts/run_harness_ci_suite.py",
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    batch_path = output_dir / args.batch_file
    metrics_path = output_dir / args.metrics_file

    batch = build_batch(system_version=args.system_version, batch_id=args.batch_id)
    metrics = compute_metrics(batch)

    _write_json(batch_path, batch.to_dict())
    _write_json(metrics_path, metrics.to_dict(rounded=False))

    print("Harness CI smoke batch completed:")
    print(f"  BatchResult : {batch_path}")
    print(f"  Metrics     : {metrics_path}")
    print(
        "  Summary     : "
        f"total={batch.summary.total}, passed={batch.summary.passed}, "
        f"failed={batch.summary.failed}, partial={batch.summary.partial}, errored={batch.summary.errored}, "
        f"pass_rate={batch.summary.pass_rate:.4f}, avg_score={batch.summary.avg_score:.4f}"
    )

    if args.baseline_out:
        baseline_path = Path(args.baseline_out)
        baseline = _build_baseline(
            metrics,
            baseline_id=args.baseline_id,
            label=args.baseline_label,
            system_version=args.system_version,
        )
        _write_json(baseline_path, baseline.to_dict())
        print(f"  Baseline    : {baseline_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
