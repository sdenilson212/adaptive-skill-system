"""Tests for the harness reporting CLI."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List

from adaptive_skill.harness.baseline import BaselineRecord
from adaptive_skill.harness.batch_runner import BatchResult, BatchSummary
from adaptive_skill.harness.cli import main
from adaptive_skill.harness.metrics import compute_metrics
from adaptive_skill.harness.specs import RunResult


def _make_run_result(
    *,
    case_id: str,
    final_status: str = "pass",
    final_score: float = 1.0,
    duration_ms: float = 100.0,
    layer_used: int = 1,
    tags: List[str] | None = None,
) -> RunResult:
    return RunResult(
        run_id=str(uuid.uuid4()),
        case_id=case_id,
        grader_id="g1",
        system_version="v-test",
        started_at="2026-04-02T00:00:00+00:00",
        ended_at="2026-04-02T00:00:00.100+00:00",
        duration_ms=duration_ms,
        execution_status="success" if final_status != "error" else "error",
        final_status=final_status,
        final_score=final_score,
        solve_response={},
        execution_trace_summary={"layer_used": layer_used},
        grader_scores={},
        metadata={"hard_fail": False, "tags": tags or []},
    )


def _make_batch_result(results: List[RunResult], *, system_version: str) -> BatchResult:
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
        batch_id=str(uuid.uuid4()),
        system_version=system_version,
        started_at="2026-04-02T00:00:00+00:00",
        ended_at="2026-04-02T00:01:00+00:00",
        duration_ms=60_000.0,
        summary=summary,
        results=results,
        metadata={"source": "pytest"},
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class TestReportingCli:
    def test_cli_generates_report_bundle(self, tmp_path, capsys):
        batch = _make_batch_result(
            [
                _make_run_result(case_id="alpha", tags=["layer1", "smoke"]),
                _make_run_result(case_id="beta", final_status="partial", final_score=0.6, tags=["layer2"]),
            ],
            system_version="v1.0.1",
        )
        batch_path = tmp_path / "batch.json"
        out_dir = tmp_path / "reports"
        _write_json(batch_path, batch.to_dict())

        exit_code = main([
            str(batch_path),
            "--output-dir",
            str(out_dir),
            "--title",
            "CLI Demo",
            "--file-stem",
            "cli-demo",
        ])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Generated report bundle" in captured.out
        assert (out_dir / "cli-demo.json").exists()
        assert (out_dir / "cli-demo.md").exists()
        assert (out_dir / "cli-demo.html").exists()

    def test_cli_returns_2_when_regression_detected_and_flag_enabled(self, tmp_path, capsys):
        baseline_batch = _make_batch_result(
            [
                _make_run_result(case_id="alpha", final_score=1.0, duration_ms=80.0, tags=["layer1"]),
                _make_run_result(case_id="beta", final_score=0.9, duration_ms=90.0, tags=["layer2"]),
            ],
            system_version="v1.0.0",
        )
        current_batch = _make_batch_result(
            [
                _make_run_result(case_id="alpha", final_status="fail", final_score=0.4, duration_ms=140.0, tags=["layer1"]),
                _make_run_result(case_id="beta", final_score=0.9, duration_ms=95.0, tags=["layer2"]),
            ],
            system_version="v1.0.1",
        )
        baseline = BaselineRecord(
            baseline_id="baseline-v1",
            label="v1.0.0-release",
            system_version="v1.0.0",
            locked_at="2026-04-02T00:00:00+00:00",
            metrics=compute_metrics(baseline_batch),
            notes="stable release",
        )

        batch_path = tmp_path / "current-batch.json"
        baseline_path = tmp_path / "baseline.json"
        out_dir = tmp_path / "reports"
        _write_json(batch_path, current_batch.to_dict())
        _write_json(baseline_path, baseline.to_dict())

        exit_code = main([
            str(batch_path),
            "--baseline",
            str(baseline_path),
            "--output-dir",
            str(out_dir),
            "--fail-on-regression",
            "--file-stem",
            "cli-regression",
        ])

        captured = capsys.readouterr()
        report_json = json.loads((out_dir / "cli-regression.json").read_text(encoding="utf-8"))
        assert exit_code == 2
        assert "Regression verdict: FAIL" in captured.out
        assert report_json["regression"]["verdict"] == "FAIL"

    def test_cli_rejects_report_bundle_json_input(self, tmp_path, capsys):
        report_bundle_path = tmp_path / "report-bundle.json"
        _write_json(report_bundle_path, {"report_data": {"title": "Not a BatchResult"}})

        exit_code = main([str(report_bundle_path)])

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "BatchResult JSON" in captured.err
