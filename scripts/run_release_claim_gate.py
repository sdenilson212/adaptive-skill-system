"""Run the release-grade claim gate for Adaptive Skill System.

This script codifies the release/pre-claim SOP around claim-benchmark-v2 so the
team does not have to remember the sequence manually. The fixed gate is:

1. `pytest tests -q --tb=short`
2. `ci-smoke-v1` batch generation + regression report against `ci-smoke-v1`
3. `claim-benchmark-v2` benchmark + regression check against
   `claim-benchmark-v2`
4. Optional `real-benchmark-v2` advisory run for extra diagnostics

The script writes a bundle with command logs, artifact paths, and a Markdown/JSON
summary so release evidence has a single review point.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ".benchmark-artifacts/release-claim-gate"


@dataclass
class StepResult:
    step_id: str
    title: str
    required: bool
    command: list[str]
    returncode: int | None = None
    status: str = "pending"
    log_path: str | None = None
    duration_seconds: float | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    regression_verdict: str | None = None
    note: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "运行 Adaptive Skill System 的发布前 claim gate：pytest → "
            "ci-smoke-v1 回归门禁 → claim-benchmark-v2 release gate，"
            "并输出统一 summary。"
        )
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"产物输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="用于执行各子命令的 Python 解释器，默认使用当前解释器",
    )
    parser.add_argument(
        "--include-real-benchmark",
        action="store_true",
        help="额外执行 real-benchmark-v2（advisory，不因 regression verdict 直接失败）",
    )
    return parser


def _cmd_display(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def _write_log(log_path: Path, command: list[str], completed: subprocess.CompletedProcess[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        f"$ {_cmd_display(command)}\n"
        f"[returncode] {completed.returncode}\n\n"
        "[stdout]\n"
        f"{completed.stdout or ''}\n\n"
        "[stderr]\n"
        f"{completed.stderr or ''}\n"
    )
    log_path.write_text(payload, encoding="utf-8")


def _run_command(command: list[str], *, cwd: Path, log_path: Path) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration_seconds = time.perf_counter() - started
    _write_log(log_path, command, completed)
    return completed, duration_seconds


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics_excerpt(path: Path) -> dict[str, Any]:
    payload = _load_json_if_exists(path) or {}
    wanted = [
        "total",
        "passed",
        "failed",
        "errored",
        "partial",
        "pass_rate",
        "avg_score",
        "hard_fail_count",
        "avg_duration_ms",
        "p95_duration_ms",
    ]
    return {key: payload[key] for key in wanted if key in payload}


def _regression_verdict(path: Path) -> str | None:
    payload = _load_json_if_exists(path) or {}
    regression = payload.get("regression")
    if isinstance(regression, dict):
        verdict = regression.get("verdict")
        return str(verdict) if verdict is not None else None
    return None


def _markdown_summary(
    *,
    generated_at: str,
    overall_verdict: str,
    output_dir: Path,
    results: list[StepResult],
) -> str:
    lines = [
        "# Release Claim Gate Summary",
        "",
        f"- Generated at: {generated_at}",
        f"- Overall verdict: `{overall_verdict}`",
        f"- Bundle root: `{output_dir}`",
        "",
        "## Step results",
        "",
        "| Step | Required | Status | Return code | Regression | Duration (s) |",
        "|---|---|---|---:|---|---:|",
    ]
    for item in results:
        lines.append(
            "| "
            f"{item.step_id} | "
            f"{'yes' if item.required else 'no'} | "
            f"{item.status} | "
            f"{'' if item.returncode is None else item.returncode} | "
            f"{item.regression_verdict or ''} | "
            f"{'' if item.duration_seconds is None else f'{item.duration_seconds:.2f}'} |"
        )

    for item in results:
        lines.extend([
            "",
            f"## {item.step_id} — {item.title}",
            "",
            f"- Required: `{'yes' if item.required else 'no'}`",
            f"- Status: `{item.status}`",
            f"- Command: `{_cmd_display(item.command)}`",
        ])
        if item.returncode is not None:
            lines.append(f"- Return code: `{item.returncode}`")
        if item.log_path:
            lines.append(f"- Log: `{item.log_path}`")
        if item.regression_verdict:
            lines.append(f"- Regression verdict: `{item.regression_verdict}`")
        if item.note:
            lines.append(f"- Note: {item.note}")
        if item.metrics:
            lines.append("- Metrics snapshot:")
            for key, value in item.metrics.items():
                lines.append(f"  - `{key}` = `{value}`")
        if item.artifacts:
            lines.append("- Artifacts:")
            for name, value in item.artifacts.items():
                lines.append(f"  - `{name}`: `{value}`")

    lines.extend([
        "",
        "## Release decision rule",
        "",
        "- Only proceed to README / release note / external claim updates when overall verdict is `PASS` or `PASS_WITH_ADVISORY`.",
        "- `FAIL` means at least one required gate failed; fix that first before touching outward-facing wording.",
    ])
    return "\n".join(lines) + "\n"


def _summary_payload(*, generated_at: str, overall_verdict: str, output_dir: Path, results: list[StepResult]) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "overall_verdict": overall_verdict,
        "bundle_root": str(output_dir),
        "steps": [asdict(item) for item in results],
    }


def _build_steps(args: argparse.Namespace, output_dir: Path) -> list[StepResult]:
    python_exe = args.python
    smoke_dir = output_dir / "ci-smoke"
    claim_dir = output_dir / "claim-benchmark-v2"
    real_dir = output_dir / "real-benchmark-v2"

    steps = [
        StepResult(
            step_id="S1",
            title="pytest repository gate",
            required=True,
            command=[python_exe, "-m", "pytest", "tests", "-q", "--tb=short"],
            artifacts={"log": str(output_dir / "logs" / "01-pytest.log")},
        ),
        StepResult(
            step_id="S2",
            title="ci-smoke-v1 batch generation",
            required=True,
            command=[python_exe, "scripts/run_harness_ci_suite.py", "--output-dir", str(smoke_dir)],
            artifacts={
                "batch": str(smoke_dir / "harness-batch-result.json"),
                "metrics": str(smoke_dir / "harness-metrics.json"),
                "log": str(output_dir / "logs" / "02-ci-smoke-batch.log"),
            },
        ),
        StepResult(
            step_id="S3",
            title="ci-smoke-v1 regression report",
            required=True,
            command=[
                python_exe,
                "-m",
                "adaptive_skill.harness.cli",
                str(smoke_dir / "harness-batch-result.json"),
                "--output-dir",
                str(smoke_dir / "reports"),
                "--baseline",
                "harness_baselines/ci-smoke-v1.json",
                "--fail-on-regression",
                "--file-stem",
                "adaptive-skill-harness-ci-smoke",
            ],
            artifacts={
                "report_json": str(smoke_dir / "reports" / "adaptive-skill-harness-ci-smoke.json"),
                "report_md": str(smoke_dir / "reports" / "adaptive-skill-harness-ci-smoke.md"),
                "report_html": str(smoke_dir / "reports" / "adaptive-skill-harness-ci-smoke.html"),
                "log": str(output_dir / "logs" / "03-ci-smoke-report.log"),
            },
        ),
        StepResult(
            step_id="S4",
            title="claim-benchmark-v2 release gate",
            required=True,
            command=[
                python_exe,
                "scripts/run_harness_claim_benchmark_v2.py",
                "--output-dir",
                str(claim_dir),
                "--baseline",
                "harness_baselines/claim-benchmark-v2.json",
                "--fail-on-regression",
            ],
            artifacts={
                "batch": str(claim_dir / "claim-benchmark-v2-batch-result.json"),
                "metrics": str(claim_dir / "claim-benchmark-v2-metrics.json"),
                "report_json": str(claim_dir / "reports" / "adaptive-skill-harness-claim-benchmark-v2.json"),
                "report_md": str(claim_dir / "reports" / "adaptive-skill-harness-claim-benchmark-v2.md"),
                "report_html": str(claim_dir / "reports" / "adaptive-skill-harness-claim-benchmark-v2.html"),
                "log": str(output_dir / "logs" / "04-claim-benchmark-v2.log"),
            },
        ),
    ]
    if args.include_real_benchmark:
        steps.append(
            StepResult(
                step_id="S5",
                title="real-benchmark-v2 advisory diagnostics",
                required=False,
                command=[
                    python_exe,
                    "scripts/run_harness_real_benchmark.py",
                    "--output-dir",
                    str(real_dir),
                    "--baseline",
                    "harness_baselines/real-benchmark-v2.json",
                ],
                artifacts={
                    "batch": str(real_dir / "real-benchmark-batch-result.json"),
                    "metrics": str(real_dir / "real-benchmark-metrics.json"),
                    "report_json": str(real_dir / "reports" / "adaptive-skill-harness-real-benchmark.json"),
                    "report_md": str(real_dir / "reports" / "adaptive-skill-harness-real-benchmark.md"),
                    "report_html": str(real_dir / "reports" / "adaptive-skill-harness-real-benchmark.html"),
                    "log": str(output_dir / "logs" / "05-real-benchmark-v2.log"),
                },
                note="Advisory only: regression verdict should be reviewed, but does not directly block claim publication.",
            )
        )
    return steps


def _enrich_step_result(step: StepResult) -> None:
    metrics_path = step.artifacts.get("metrics")
    if metrics_path:
        step.metrics = _metrics_excerpt(Path(metrics_path))
    report_json = step.artifacts.get("report_json")
    if report_json:
        step.regression_verdict = _regression_verdict(Path(report_json))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)

    steps = _build_steps(args, output_dir)
    overall_verdict = "PASS"
    stop_required_flow = False

    for index, step in enumerate(steps, start=1):
        if stop_required_flow:
            step.status = "skipped"
            continue

        log_path = Path(step.artifacts["log"])
        completed, duration_seconds = _run_command(step.command, cwd=PROJECT_ROOT, log_path=log_path)
        step.returncode = completed.returncode
        step.duration_seconds = duration_seconds
        step.log_path = str(log_path)
        step.status = "passed" if completed.returncode == 0 else "failed"
        _enrich_step_result(step)

        if completed.returncode != 0 and step.required:
            overall_verdict = "FAIL"
            stop_required_flow = True
        elif completed.returncode != 0 and not step.required:
            overall_verdict = "FAIL"
        elif not step.required and step.regression_verdict == "FAIL" and overall_verdict == "PASS":
            overall_verdict = "PASS_WITH_ADVISORY"

    generated_at = datetime.now(timezone.utc).isoformat()
    summary_json_path = output_dir / "release-claim-gate-summary.json"
    summary_md_path = output_dir / "release-claim-gate-summary.md"

    summary_json_path.write_text(
        json.dumps(
            _summary_payload(
                generated_at=generated_at,
                overall_verdict=overall_verdict,
                output_dir=output_dir,
                results=steps,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_md_path.write_text(
        _markdown_summary(
            generated_at=generated_at,
            overall_verdict=overall_verdict,
            output_dir=output_dir,
            results=steps,
        ),
        encoding="utf-8",
    )

    print("Release claim gate completed:")
    print(f"  Overall verdict : {overall_verdict}")
    print(f"  Summary JSON    : {summary_json_path}")
    print(f"  Summary MD      : {summary_md_path}")

    return 0 if overall_verdict in {"PASS", "PASS_WITH_ADVISORY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
