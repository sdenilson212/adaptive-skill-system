"""Tests for the release claim gate SOP runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import run_release_claim_gate as gate


class _FakeCompletedProcess(subprocess.CompletedProcess[str]):
    def __init__(self, args, returncode=0, stdout="ok\n", stderr=""):
        super().__init__(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def test_main_writes_summary_and_marks_pass_with_advisory(tmp_path, monkeypatch):
    def fake_run_command(command, *, cwd, log_path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        return _FakeCompletedProcess(command, returncode=0), 0.25

    def fake_enrich(step):
        if step.step_id == "S3":
            step.regression_verdict = "PASS"
            step.metrics = {"pass_rate": 0.5}
        elif step.step_id == "S4":
            step.regression_verdict = "PASS"
            step.metrics = {"pass_rate": 1.0, "avg_score": 0.8961}
        elif step.step_id == "S5":
            step.regression_verdict = "FAIL"
            step.metrics = {"pass_rate": 0.8333}

    monkeypatch.setattr(gate, "_run_command", fake_run_command)
    monkeypatch.setattr(gate, "_enrich_step_result", fake_enrich)

    exit_code = gate.main([
        "--output-dir",
        str(tmp_path),
        "--include-real-benchmark",
    ])

    summary_json = json.loads((tmp_path / "release-claim-gate-summary.json").read_text(encoding="utf-8"))
    summary_md = (tmp_path / "release-claim-gate-summary.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert summary_json["overall_verdict"] == "PASS_WITH_ADVISORY"
    assert len(summary_json["steps"]) == 5
    assert summary_json["steps"][-1]["regression_verdict"] == "FAIL"
    assert "PASS_WITH_ADVISORY" in summary_md
    assert "README / release note / external claim updates" in summary_md


def test_main_stops_after_required_failure_and_marks_later_steps_skipped(tmp_path, monkeypatch):
    def fake_run_command(command, *, cwd, log_path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake log\n", encoding="utf-8")
        command_text = " ".join(command)
        returncode = 2 if "adaptive_skill.harness.cli" in command_text else 0
        return _FakeCompletedProcess(command, returncode=returncode), 0.10

    def fake_enrich(step):
        if step.step_id == "S3":
            step.regression_verdict = "FAIL"
            step.metrics = {"pass_rate": 0.5}

    monkeypatch.setattr(gate, "_run_command", fake_run_command)
    monkeypatch.setattr(gate, "_enrich_step_result", fake_enrich)

    exit_code = gate.main([
        "--output-dir",
        str(tmp_path),
    ])

    summary_json = json.loads((tmp_path / "release-claim-gate-summary.json").read_text(encoding="utf-8"))
    steps = summary_json["steps"]

    assert exit_code == 1
    assert summary_json["overall_verdict"] == "FAIL"
    assert steps[2]["status"] == "failed"
    assert steps[3]["status"] == "skipped"
