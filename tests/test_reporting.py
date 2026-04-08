"""Tests for harness P4 reporting.

Covers the structured report payload plus Markdown / HTML rendering and the
filesystem bundle writer.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List


from adaptive_skill.harness.batch_runner import BatchResult, BatchSummary
from adaptive_skill.harness.baseline import BaselineRecord
from adaptive_skill.harness.metrics import compute_metrics
from adaptive_skill.harness.regression import check_regression
from adaptive_skill.harness.reporting import (
    build_report_bundle,
    build_report_data,
    render_html_report,
    render_markdown_report,
    write_report_bundle,
)
from adaptive_skill.harness.specs import RunResult


def _make_run_result(
    *,
    case_id: str = "c1",
    final_status: str = "pass",
    final_score: float = 1.0,
    duration_ms: float = 100.0,
    execution_status: str = "success",
    hard_fail: bool = False,
    layer_used: int = 1,
    tags: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    solve_metadata: Dict[str, Any] | None = None,
    grader_scores: Dict[str, float] | None = None,
    assertion_results: List[Dict[str, Any]] | None = None,
    grading_notes: List[str] | None = None,
    decision_trace: List[Dict[str, Any]] | None = None,
) -> RunResult:

    merged_metadata = {
        "hard_fail": hard_fail,
        "tags": tags or [],
        "assertion_results": assertion_results or [],
        "grading_notes": grading_notes or [],
    }
    if metadata:
        merged_metadata.update(metadata)

    solve_response = {"metadata": solve_metadata} if solve_metadata else {}

    return RunResult(
        run_id=str(uuid.uuid4()),
        case_id=case_id,
        grader_id="g1",
        system_version="0.0.1",
        started_at="2026-04-02T00:00:00+00:00",
        ended_at="2026-04-02T00:00:00.100+00:00",
        duration_ms=duration_ms,
        execution_status=execution_status,
        final_status=final_status,
        final_score=final_score,
        solve_response=solve_response,
        execution_trace_summary={"layer_used": layer_used},
        decision_trace=decision_trace or [],
        grader_scores=grader_scores or {},
        metadata=merged_metadata,
    )





def _make_batch_result(results: List[RunResult], system_version: str = "v0.test") -> BatchResult:
    total = len(results)
    passed = sum(1 for r in results if r.final_status == "pass")
    failed = sum(1 for r in results if r.final_status == "fail")
    errored = sum(1 for r in results if r.final_status == "error")
    partial = sum(1 for r in results if r.final_status == "partial")
    hard_fail_count = sum(1 for r in results if r.metadata.get("hard_fail"))
    scores = [r.final_score for r in results]
    durations = [r.duration_ms for r in results]
    summary = BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        partial=partial,
        pass_rate=passed / total if total else 0.0,
        avg_score=sum(scores) / total if total else 0.0,
        avg_duration_ms=sum(durations) / total if total else 0.0,
        hard_fail_count=hard_fail_count,
    )
    return BatchResult(
        batch_id=str(uuid.uuid4()),
        system_version=system_version,
        started_at="2026-04-02T00:00:00+00:00",
        ended_at="2026-04-02T00:01:00+00:00",
        duration_ms=60_000.0,
        summary=summary,
        results=results,
    )


def _make_regression_fixture() -> tuple[BatchResult, BaselineRecord, object]:
    baseline_batch = _make_batch_result([
        _make_run_result(case_id="c1", final_status="pass", final_score=1.0, duration_ms=80.0, tags=["layer1"]),
        _make_run_result(case_id="c2", final_status="pass", final_score=0.9, duration_ms=90.0, tags=["layer2"]),
    ], system_version="v1.0.0")
    current_batch = _make_batch_result([
        _make_run_result(case_id="c1", final_status="fail", final_score=0.5, duration_ms=120.0, tags=["layer1"]),
        _make_run_result(case_id="c2", final_status="pass", final_score=0.9, duration_ms=95.0, tags=["layer2"]),
    ], system_version="v1.0.1")
    baseline_metrics = compute_metrics(baseline_batch)
    baseline = BaselineRecord(
        baseline_id="baseline-v1",
        label="v1.0.0-release",
        system_version="v1.0.0",
        locked_at="2026-04-02T00:00:00+00:00",
        metrics=baseline_metrics,
        notes="stable reference",
    )
    regression = check_regression(compute_metrics(current_batch), baseline)
    return current_batch, baseline, regression


class TestBuildReportData:
    def test_report_data_shape(self):
        batch = _make_batch_result([
            _make_run_result(case_id="alpha", tags=["smoke", "layer1"]),
            _make_run_result(case_id="beta", final_status="partial", final_score=0.6, tags=["layer2"]),
        ])
        report = build_report_data(batch, title="P4 Smoke")

        assert report["title"] == "P4 Smoke"
        assert report["summary"]["total"] == 2
        assert report["metrics"]["total"] == 2
        assert len(report["case_metrics"]) == 2
        assert report["tag_slices"]["smoke"]["total"] == 1
        assert report["overall_status"] == "WARN"

    def test_report_data_includes_runtime_summary(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="alpha",
                metadata={"attempt_count": 3, "retry_count": 2, "fallback_count": 1},
                solve_metadata={
                    "token_usage": {"prompt_tokens": 120, "completion_tokens": 30},
                    "estimated_cost": 0.0123,
                },
            ),
            _make_run_result(case_id="beta"),
        ])
        report = build_report_data(batch, title="Runtime Demo")

        assert report["runtime"]["totals"]["attempt_count"] == 4
        assert report["runtime"]["averages"]["attempt_count"] == 2.0
        assert report["runtime"]["totals"]["total_tokens"] == 150
        assert report["runtime"]["totals"]["estimated_cost"] == 0.0123
        assert report["runtime"]["coverage"]["estimated_cost"] == 1
        assert report["runtime"]["coverage_rates"]["estimated_cost"] == 0.5

    def test_report_data_includes_grader_details(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="semantic-alpha",
                grader_scores={"semantic_similarity": 0.4321, "layer_is_3": 1.0},
                assertion_results=[
                    {
                        "type": "semantic_similarity",
                        "passed": True,
                        "score": 0.4321,
                        "message": "",
                    }
                ],
                grading_notes=["semantic similarity scored against generated skill name"],
            )
        ])
        report = build_report_data(batch, title="Grader Detail Demo")
        case = report["case_metrics"][0]

        assert case["grader_scores"]["semantic_similarity"] == 0.4321
        assert case["assertion_results"][0]["type"] == "semantic_similarity"
        assert case["grading_notes"] == ["semantic similarity scored against generated skill name"]

    def test_report_data_includes_decision_trace(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="trace-alpha",
                decision_trace=[
                    {
                        "layer": 1,
                        "action": "blocked",
                        "trigger": "direct_match",
                        "rejection_reason": "below_threshold",
                    },
                    {
                        "layer": 3,
                        "action": "selected",
                        "trigger": "generation",
                        "generation_strategy": "analogy",
                        "evaluator_dimensions": {"completeness": 0.82},
                    },
                ],
            )
        ])
        report = build_report_data(batch, title="Decision Trace Demo")
        case = report["case_metrics"][0]

        assert case["decision_trace"][0]["rejection_reason"] == "below_threshold"
        assert case["decision_trace"][1]["generation_strategy"] == "analogy"
        assert case["decision_trace"][1]["evaluator_dimensions"]["completeness"] == 0.82

    def test_report_data_includes_generation_telemetry(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="telemetry-alpha",
                metadata={
                    "generation_attempts": [
                        {
                            "attempt": 1,
                            "quality": 0.62,
                            "approved": False,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": ["add evidence"],
                            "failed_draft": {
                                "name": "Layer3 Draft v1",
                                "step_count": 2,
                                "checklist_count": 1,
                            },
                            "failed_draft_persisted": True,
                            "failed_draft_record_id": 7,
                            "persist_error": None,
                        },
                        {
                            "attempt": 2,
                            "quality": 0.81,
                            "approved": True,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": [],
                        },
                    ]
                },


                solve_metadata={
                    "generation_info": {
                        "name": "Layer3 Retry Skill",
                        "generation_attempt": 2,
                        "generation_mode": "llm_assisted",
                        "llm_provider": "ollama:qwen2.5:7b",
                        "generation_info": {
                            "generation_strategy": "analogy",
                            "confidence": 0.81,
                            "evaluator_feedback_applied": ["add evidence"],
                        },
                    }
                },
            )
        ])
        report = build_report_data(batch, title="Generation Telemetry Demo")
        case = report["case_metrics"][0]

        assert len(case["generation_attempts"]) == 2
        assert case["generation_attempts"][0]["recommendations"] == ["add evidence"]
        assert case["generation_attempts"][0]["failed_draft"]["name"] == "Layer3 Draft v1"
        assert case["generation_attempts"][0]["failed_draft"]["step_count"] == 2
        assert case["generation_attempts"][0]["failed_draft_persisted"] is True
        assert case["generation_attempts"][0]["failed_draft_record_id"] == 7
        assert case["generation_info"]["name"] == "Layer3 Retry Skill"

        assert case["generation_info"]["generation_info"]["generation_strategy"] == "analogy"



class TestRenderMarkdown:



    def test_markdown_contains_key_sections(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="alpha",
                tags=["layer1"],
                metadata={
                    "attempt_count": 2,
                    "retry_count": 1,
                    "fallback_count": 1,
                    "generation_attempts": [
                        {
                            "attempt": 1,
                            "quality": 0.62,
                            "approved": False,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": ["add evidence"],
                            "failed_draft": {
                                "name": "Layer3 Draft v1",
                                "step_count": 2,
                                "checklist_count": 1,
                            },
                            "failed_draft_persisted": True,
                            "failed_draft_record_id": 7,
                            "persist_error": None,
                        },
                        {
                            "attempt": 2,
                            "quality": 0.81,
                            "approved": True,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": [],
                        },
                    ],
                },


                solve_metadata={
                    "token_usage": {"prompt_tokens": 80, "completion_tokens": 20},
                    "estimated_cost": 0.01,
                    "generation_info": {
                        "name": "Layer3 Retry Skill",
                        "generation_attempt": 2,
                        "generation_mode": "llm_assisted",
                        "llm_provider": "ollama:qwen2.5:7b",
                        "generation_info": {
                            "generation_strategy": "analogy",
                            "confidence": 0.81,
                            "evaluator_feedback_applied": ["add evidence"],
                        },
                    },
                },
                grader_scores={"semantic_similarity": 0.4321},
                assertion_results=[
                    {
                        "type": "semantic_similarity",
                        "passed": True,
                        "score": 0.4321,
                        "message": "",
                    }
                ],
                grading_notes=["semantic similarity scored against generated skill name"],
                decision_trace=[
                    {
                        "layer": 1,
                        "action": "blocked",
                        "trigger": "direct_match",
                        "score": 0.48,
                        "candidates_evaluated": 3,
                        "rejection_reason": "below_threshold",
                    },
                    {
                        "layer": 3,
                        "action": "selected",
                        "trigger": "generation",
                        "score": 0.81,
                        "generation_strategy": "analogy",
                        "evaluator_score": 0.81,
                        "evaluator_dimensions": {"completeness": 0.82},
                    },
                ],
            ),


            _make_run_result(case_id="beta", final_status="partial", final_score=0.6, tags=["layer2"]),
        ])
        markdown = render_markdown_report(batch, title="Harness Report Demo")

        assert "# Harness Report Demo" in markdown
        assert "## 1. 批次摘要" in markdown
        assert "### 运行指标" in markdown
        assert "| Attempt Count |" in markdown
        assert "## 4. Case 级明细" in markdown
        assert "### Grader 下钻" in markdown
        assert "### Decision Trace 下钻" in markdown
        assert "### Layer 3 Retry Telemetry 下钻" in markdown
        assert "semantic_similarity=0.4321" in markdown
        assert "[1] semantic_similarity | passed=True | score=0.4321 | message=—" in markdown
        assert "[1] L1 | blocked | direct_match | score=0.4800 | candidates=3 | reason=below_threshold" in markdown
        assert "[2] L3 | selected | generation | score=0.8100 | strategy=analogy | evaluator=0.8100" in markdown
        assert "evaluator_dimensions: completeness=0.8200" in markdown
        assert "Final Draft: name=Layer3 Retry Skill | mode=llm_assisted | provider=ollama:qwen2.5:7b | final_attempt=2 | strategy=analogy | confidence=0.8100 | feedback=add evidence" in markdown
        assert "[1] attempt=1 | quality=0.6200 | approved=False | mode=llm_assisted | provider=ollama:qwen2.5:7b | recommendations=add evidence | failed_draft=Layer3 Draft v1 (steps=2, checklist=1) | persisted=True | draft_id=7" in markdown

        assert "[2] attempt=2 | quality=0.8100 | approved=True | mode=llm_assisted | provider=ollama:qwen2.5:7b" in markdown

        assert "| alpha | pass |" in markdown
        assert "| beta | partial |" in markdown
        assert "| alpha | pass | 1.0000 | 100.00 ms | success | False | 1 | 2 | 1 | 1 | 100 | 0.010000 | 2 | semantic_similarity=0.4321 |" in markdown





    def test_markdown_renders_regression_findings(self):
        batch, baseline, regression = _make_regression_fixture()
        markdown = render_markdown_report(
            batch,
            baseline=baseline,
            regression_report=regression,
            title="Regression Demo",
        )

        assert "Baseline：`baseline-v1`" in markdown
        assert "Verdict：**FAIL**" in markdown
        assert "pass_rate" in markdown
        assert "case:c1" in markdown


class TestRenderHtml:
    def test_html_escapes_case_content(self):
        batch = _make_batch_result([
            _make_run_result(
                case_id="<script>alert('x')</script>",
                tags=["layer1"],
                metadata={
                    "attempt_count": 2,
                    "retry_count": 1,
                    "generation_attempts": [
                        {
                            "attempt": 1,
                            "quality": 0.62,
                            "approved": False,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": ["add evidence"],
                            "failed_draft": {
                                "name": "Layer3 Draft v1",
                                "step_count": 2,
                                "checklist_count": 1,
                            },
                            "failed_draft_persisted": True,
                            "failed_draft_record_id": 7,
                            "persist_error": None,
                        },
                        {
                            "attempt": 2,
                            "quality": 0.81,
                            "approved": True,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": [],
                        },
                    ],
                },


                solve_metadata={
                    "token_usage": {"prompt_tokens": 40, "completion_tokens": 10},
                    "estimated_cost": 0.005,
                    "generation_info": {
                        "name": "Layer3 Retry Skill",
                        "generation_attempt": 2,
                        "generation_mode": "llm_assisted",
                        "llm_provider": "ollama:qwen2.5:7b",
                        "generation_info": {
                            "generation_strategy": "analogy",
                            "confidence": 0.81,
                            "evaluator_feedback_applied": ["add evidence"],
                        },
                    },
                },
                grader_scores={"semantic_similarity": 0.4321},
                assertion_results=[
                    {
                        "type": "semantic_similarity",
                        "passed": False,
                        "score": 0.4321,
                        "message": "field 'skill_name' similarity 0.4321 < 0.5000",
                    }
                ],
                decision_trace=[
                    {
                        "layer": 1,
                        "action": "blocked",
                        "trigger": "direct_match",
                        "rejection_reason": "below_threshold",
                    },
                    {
                        "layer": 3,
                        "action": "selected",
                        "trigger": "generation",
                        "generation_strategy": "analogy",
                        "evaluator_dimensions": {"completeness": 0.82},
                    },
                ],
            ),


        ])
        html_report = render_html_report(batch, title="HTML Escape Demo")

        assert "<script>alert('x')</script>" not in html_report
        assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html_report
        assert "运行指标" in html_report
        assert "Attempt Count" in html_report
        assert "Estimated Cost" in html_report
        assert "Gen Attempts" in html_report
        assert "Grader 下钻" in html_report
        assert "Decision Trace 下钻" in html_report
        assert "Layer 3 Retry Telemetry 下钻" in html_report
        assert "semantic_similarity=0.4321" in html_report
        assert "L1 | blocked | direct_match | reason=below_threshold" in html_report
        assert "strategy=analogy" in html_report
        assert "name=Layer3 Retry Skill | mode=llm_assisted | provider=ollama:qwen2.5:7b | final_attempt=2 | strategy=analogy | confidence=0.8100 | feedback=add evidence" in html_report
        assert "attempt=1 | quality=0.6200 | approved=False | mode=llm_assisted | provider=ollama:qwen2.5:7b | recommendations=add evidence | failed_draft=Layer3 Draft v1 (steps=2, checklist=1) | persisted=True | draft_id=7" in html_report

        assert "evaluator_dimensions: completeness=0.8200" in html_report

        assert "field &#x27;skill_name&#x27; similarity 0.4321 &lt; 0.5000" in html_report







class TestBuildAndWriteBundle:
    def test_build_bundle_contains_both_formats(self):
        batch = _make_batch_result([_make_run_result(case_id="alpha")])
        bundle = build_report_bundle(batch, title="Bundle Demo")

        assert bundle.title == "Bundle Demo"
        assert bundle.markdown.startswith("# Bundle Demo")
        assert "<!DOCTYPE html>" in bundle.html

    def test_write_report_bundle_persists_json_markdown_html(self, tmp_path):
        batch, baseline, regression = _make_regression_fixture()
        written = write_report_bundle(
            str(tmp_path / "reports"),
            batch,
            baseline=baseline,
            regression_report=regression,
            file_stem="release-report",
        )

        assert written.markdown_path.endswith("release-report.md")
        assert written.html_path.endswith("release-report.html")
        assert written.json_path.endswith("release-report.json")

        json_payload = json.loads((tmp_path / "reports" / "release-report.json").read_text(encoding="utf-8"))
        assert json_payload["regression"]["verdict"] == "FAIL"
        assert "runtime" in json_payload
        assert "totals" in json_payload["runtime"]
        assert (tmp_path / "reports" / "release-report.md").exists()
        assert (tmp_path / "reports" / "release-report.html").exists()

