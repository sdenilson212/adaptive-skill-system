"""Tests for harness P3: metrics.py, baseline.py, regression.py.

Strategy
--------
* All tests use synthetic BatchResult / RunResult objects — no real
  AdaptiveSkillSystem calls needed.
* BaselineStore tests use a tmp_path (pytest fixture) to avoid
  filesystem pollution.
* Regression tests cover: no-regression (PASS), pass_rate drop (HIGH),
  avg_score drop (HIGH), hard_fail increase (CRITICAL), error_rate
  increase (MEDIUM), p95 latency increase (LOW), per-case score drop,
  tolerance boundary (delta == threshold), custom thresholds.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

from adaptive_skill.harness.batch_runner import BatchResult, BatchSummary
from adaptive_skill.harness.baseline import BaselineRecord, BaselineStore
from adaptive_skill.harness.metrics import BatchMetrics, CaseMetrics, compute_metrics
from adaptive_skill.harness.regression import (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    RegressionThresholds,
    check_regression,
    check_regression_from_store,
)
from adaptive_skill.harness.specs import RunResult


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    trace_metadata: Dict[str, Any] | None = None,
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

    execution_trace_summary: Dict[str, Any] = {"layer_used": layer_used}
    if trace_metadata:
        execution_trace_summary["metadata"] = trace_metadata

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
        execution_trace_summary=execution_trace_summary,
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
    durs = [r.duration_ms for r in results]
    summary = BatchSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        partial=partial,
        pass_rate=passed / total if total else 0.0,
        avg_score=sum(scores) / total if total else 0.0,
        avg_duration_ms=sum(durs) / total if total else 0.0,
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


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: metrics.py
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeMetricsEmpty:
    def test_empty_batch(self):
        br = _make_batch_result([])
        bm = compute_metrics(br)
        assert bm.total == 0
        assert bm.pass_rate == 0.0
        assert bm.avg_score == 0.0
        assert bm.case_metrics == []
        assert bm.tag_slices == {}
        assert bm.layer_distribution == {}


class TestComputeMetricsCounts:
    def setup_method(self):
        results = [
            _make_run_result(case_id="c1", final_status="pass", final_score=1.0),
            _make_run_result(case_id="c2", final_status="fail", final_score=0.4),
            _make_run_result(case_id="c3", final_status="error", final_score=0.0),
            _make_run_result(case_id="c4", final_status="partial", final_score=0.6),
        ]
        self.bm = compute_metrics(_make_batch_result(results))

    def test_counts(self):
        assert self.bm.total == 4
        assert self.bm.passed == 1
        assert self.bm.failed == 1
        assert self.bm.errored == 1
        assert self.bm.partial == 1

    def test_pass_rate(self):
        assert abs(self.bm.pass_rate - 0.25) < 1e-6

    def test_avg_score(self):
        expected = (1.0 + 0.4 + 0.0 + 0.6) / 4
        assert abs(self.bm.avg_score - expected) < 1e-6

    def test_min_max_score(self):
        assert self.bm.min_score == 0.0
        assert self.bm.max_score == 1.0


class TestComputeMetricsScoreStdev:
    def test_single_result_stdev_zero(self):
        bm = compute_metrics(_make_batch_result([
            _make_run_result(final_score=0.8),
        ]))
        assert bm.score_stdev == 0.0

    def test_two_results_stdev(self):
        bm = compute_metrics(_make_batch_result([
            _make_run_result(case_id="a", final_score=0.0),
            _make_run_result(case_id="b", final_score=1.0),
        ]))
        assert bm.score_stdev > 0


class TestComputeMetricsLatency:
    def test_p50_p95(self):
        results = [_make_run_result(case_id=f"c{i}", duration_ms=float(i * 10)) for i in range(1, 11)]
        bm = compute_metrics(_make_batch_result(results))
        assert bm.p50_duration_ms > 0
        assert bm.p95_duration_ms >= bm.p50_duration_ms
        assert bm.avg_duration_ms > 0


class TestComputeMetricsLayerDistribution:
    def test_layer_distribution(self):
        results = [
            _make_run_result(case_id="a", layer_used=1),
            _make_run_result(case_id="b", layer_used=1),
            _make_run_result(case_id="c", layer_used=2),
            _make_run_result(case_id="d", layer_used=3),
        ]
        bm = compute_metrics(_make_batch_result(results))
        assert bm.layer_distribution.get("1", 0) == 2
        assert bm.layer_distribution.get("2", 0) == 1
        assert bm.layer_distribution.get("3", 0) == 1


class TestComputeMetricsTagSlices:
    def test_tag_slices(self):
        results = [
            _make_run_result(case_id="a", final_status="pass", final_score=1.0, tags=["layer1", "smoke"]),
            _make_run_result(case_id="b", final_status="fail", final_score=0.4, tags=["layer1"]),
            _make_run_result(case_id="c", final_status="pass", final_score=0.9, tags=["layer2"]),
        ]
        bm = compute_metrics(_make_batch_result(results))
        assert "layer1" in bm.tag_slices
        assert bm.tag_slices["layer1"]["total"] == 2
        assert bm.tag_slices["layer1"]["passed"] == 1
        assert abs(bm.tag_slices["layer1"]["pass_rate"] - 0.5) < 1e-6
        assert "smoke" in bm.tag_slices
        assert "layer2" in bm.tag_slices


class TestComputeMetricsCaseMetrics:
    def test_case_metrics_shape(self):
        results = [
            _make_run_result(case_id="x1", final_score=0.8, layer_used=2, hard_fail=True),
        ]
        bm = compute_metrics(_make_batch_result(results))
        assert len(bm.case_metrics) == 1
        cm = bm.case_metrics[0]
        assert cm.case_id == "x1"
        assert cm.final_score == 0.8
        assert cm.layer_used == 2
        assert cm.hard_fail is True

    def test_case_metrics_include_grader_details(self):
        results = [
            _make_run_result(
                case_id="semantic-case",
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
            ),
        ]
        bm = compute_metrics(_make_batch_result(results))
        cm = bm.case_metrics[0]

        assert cm.grader_scores == {"semantic_similarity": 0.4321, "layer_is_3": 1.0}
        assert cm.assertion_results[0]["type"] == "semantic_similarity"
        assert cm.grading_notes == ["semantic similarity scored against generated skill name"]

    def test_case_metrics_include_decision_trace(self):
        results = [
            _make_run_result(
                case_id="trace-case",
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
        ]
        bm = compute_metrics(_make_batch_result(results))
        cm = bm.case_metrics[0]

        assert len(cm.decision_trace) == 2
        assert cm.decision_trace[0]["rejection_reason"] == "below_threshold"
        assert cm.decision_trace[1]["generation_strategy"] == "analogy"
        assert cm.decision_trace[1]["evaluator_dimensions"]["completeness"] == 0.82

    def test_case_metrics_include_generation_telemetry(self):
        results = [
            _make_run_result(
                case_id="layer3-telemetry",
                metadata={
                    "generation_attempts": [
                        {
                            "attempt": 1,
                            "quality": 0.62,
                            "approved": False,
                            "generation_mode": "llm_assisted",
                            "provider_used": "ollama:qwen2.5:7b",
                            "recommendations": ["add evidence"],
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
            ),
        ]
        bm = compute_metrics(_make_batch_result(results))
        cm = bm.case_metrics[0]

        assert len(cm.generation_attempts) == 2
        assert cm.generation_attempts[0]["approved"] is False
        assert cm.generation_attempts[1]["quality"] == pytest.approx(0.81)
        assert cm.generation_info["name"] == "Layer3 Retry Skill"
        assert cm.generation_info["generation_info"]["generation_strategy"] == "analogy"


class TestComputeMetricsRuntimeCounters:



    def test_runtime_counters_aggregate_with_missing_safe_defaults(self):
        results = [
            _make_run_result(
                case_id="rt1",
                metadata={
                    "attempt_count": 3,
                    "retry_count": 2,
                    "framework_fallback_count": 1,
                },
                solve_metadata={
                    "token_usage": {"prompt_tokens": 120, "completion_tokens": 30},
                    "costs": {"cost_usd": 0.0123},
                },
            ),
            _make_run_result(case_id="rt2"),
        ]
        bm = compute_metrics(_make_batch_result(results))

        assert bm.total_attempt_count == 4
        assert bm.avg_attempt_count == pytest.approx(2.0)
        assert bm.total_retry_count == 2
        assert bm.avg_retry_count == pytest.approx(1.0)
        assert bm.total_fallback_count == 1
        assert bm.avg_fallback_count == pytest.approx(0.5)
        assert bm.total_prompt_tokens == 120
        assert bm.total_completion_tokens == 30
        assert bm.total_tokens == 150
        assert bm.avg_total_tokens == pytest.approx(75.0)
        assert bm.total_estimated_cost == pytest.approx(0.0123)
        assert bm.avg_estimated_cost == pytest.approx(0.00615)
        assert bm.runtime_metric_coverage == {
            "attempt_count": 1,
            "retry_count": 1,
            "fallback_count": 1,
            "total_tokens": 1,
            "estimated_cost": 1,
        }

        first_case = bm.case_metrics[0]
        assert first_case.attempt_count == 3
        assert first_case.retry_count == 2
        assert first_case.fallback_count == 1
        assert first_case.total_tokens == 150
        assert first_case.estimated_cost == pytest.approx(0.0123)

    def test_runtime_counters_can_be_derived_from_aliases(self):
        result = _make_run_result(
            case_id="derived",
            metadata={"retry_count": 2},
            solve_metadata={
                "usage": {"input_tokens": 7, "output_tokens": 5},
                "cost": 0.5,
            },
        )
        bm = compute_metrics(_make_batch_result([result]))
        case = bm.case_metrics[0]

        assert case.attempt_count == 3
        assert case.retry_count == 2
        assert case.total_tokens == 12
        assert case.estimated_cost == pytest.approx(0.5)
        assert bm.runtime_metric_coverage["attempt_count"] == 1
        assert bm.runtime_metric_coverage["total_tokens"] == 1
        assert bm.runtime_metric_coverage["estimated_cost"] == 1


class TestBatchMetricsToDict:
    def test_to_dict_is_json_serialisable(self):

        results = [_make_run_result(case_id="d1", tags=["t1"])]
        bm = compute_metrics(_make_batch_result(results))
        d = bm.to_dict()
        # Must round-trip through JSON without error
        json.dumps(d)

    def test_to_dict_has_expected_keys(self):
        bm = compute_metrics(_make_batch_result([_make_run_result()]))
        keys = bm.to_dict().keys()
        for k in (
            "pass_rate",
            "avg_score",
            "total",
            "layer_distribution",
            "case_metrics",
            "total_attempt_count",
            "avg_retry_count",
            "total_tokens",
            "total_estimated_cost",
            "runtime_metric_coverage",
        ):
            assert k in keys



# ─────────────────────────────────────────────────────────────────────────────
# Section 2: baseline.py
# ─────────────────────────────────────────────────────────────────────────────

class TestBaselineStoreLockLoad:
    def test_lock_and_load(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        results = [_make_run_result(case_id="b1", final_score=1.0)]
        bm = compute_metrics(_make_batch_result(results))

        rec = store.lock(bm, label="test-baseline", notes="initial")
        assert rec.baseline_id
        assert rec.label == "test-baseline"
        assert rec.notes == "initial"

        loaded = store.load(rec.baseline_id)
        assert loaded.baseline_id == rec.baseline_id
        assert loaded.label == rec.label
        assert loaded.metrics.total == bm.total

    def test_load_missing_raises(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent-id")

    def test_exists(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm = compute_metrics(_make_batch_result([_make_run_result()]))
        rec = store.lock(bm)
        assert store.exists(rec.baseline_id)
        assert not store.exists("phantom")


class TestBaselineStoreOverwrite:
    def test_overwrite_with_same_id(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm1 = compute_metrics(_make_batch_result([_make_run_result(case_id="x", final_score=0.5)]))
        bm2 = compute_metrics(_make_batch_result([_make_run_result(case_id="x", final_score=0.9)]))

        rec1 = store.lock(bm1, baseline_id="stable-id", label="v1")
        rec2 = store.lock(bm2, baseline_id="stable-id", label="v2")

        loaded = store.load("stable-id")
        assert loaded.label == "v2"
        assert abs(loaded.metrics.avg_score - 0.9) < 1e-6


class TestBaselineStoreDelete:
    def test_delete_existing(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm = compute_metrics(_make_batch_result([_make_run_result()]))
        rec = store.lock(bm)
        assert store.delete(rec.baseline_id) is True
        assert not store.exists(rec.baseline_id)

    def test_delete_missing(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        assert store.delete("ghost") is False


class TestBaselineStoreList:
    def test_list_returns_all(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm = compute_metrics(_make_batch_result([_make_run_result()]))
        for i in range(3):
            store.lock(bm, label=f"baseline-{i}")
        recs = store.list_baselines()
        assert len(recs) == 3

    def test_list_empty(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines2"))
        assert store.list_baselines() == []


class TestBaselineRecordRoundTrip:
    def test_to_dict_from_dict_roundtrip(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        results = [
            _make_run_result(
                case_id="rt1",
                final_score=0.7,
                tags=["t1", "t2"],
                decision_trace=[{"layer": 1, "action": "selected", "trigger": "direct_match"}],
            ),
            _make_run_result(case_id="rt2", final_score=0.9, layer_used=2),
        ]

        bm = compute_metrics(_make_batch_result(results))
        rec = store.lock(bm, label="roundtrip-test")
        loaded = store.load(rec.baseline_id)

        assert loaded.metrics.passed == bm.passed
        assert loaded.metrics.pass_rate == bm.pass_rate
        assert len(loaded.metrics.case_metrics) == len(bm.case_metrics)
        assert loaded.metrics.case_metrics[0].decision_trace[0]["trigger"] == "direct_match"


    def test_persistence_keeps_full_precision(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm = BatchMetrics(
            batch_id="batch-precision",
            system_version="v0.test",
            started_at="2026-04-02T00:00:00+00:00",
            total=3,
            passed=2,
            failed=1,
            pass_rate=2 / 3,
            avg_score=2 / 3,
            score_stdev=0.0,
            min_score=0.0,
            max_score=1.0,
            avg_duration_ms=12.3456,
            p50_duration_ms=12.3456,
            p95_duration_ms=12.3456,
        )

        rec = store.lock(bm, baseline_id="precision")
        loaded = store.load(rec.baseline_id)

        assert loaded.metrics.pass_rate == pytest.approx(bm.pass_rate, rel=0, abs=1e-12)
        assert loaded.metrics.avg_score == pytest.approx(bm.avg_score, rel=0, abs=1e-12)
        assert loaded.metrics.avg_duration_ms == pytest.approx(bm.avg_duration_ms, rel=0, abs=1e-12)
        assert loaded.metrics.pass_rate != pytest.approx(round(bm.pass_rate, 4), rel=0, abs=1e-12)
        assert loaded.metrics.avg_duration_ms != pytest.approx(round(bm.avg_duration_ms, 2), rel=0, abs=1e-12)



# ─────────────────────────────────────────────────────────────────────────────
# Section 3: regression.py
# ─────────────────────────────────────────────────────────────────────────────

def _make_baseline(metrics: BatchMetrics, tmp_path: Path) -> BaselineRecord:
    store = BaselineStore(str(tmp_path / "baselines"))
    return store.lock(metrics, label="test-baseline")


class TestRegressionNoRegression:
    def test_identical_metrics_pass(self, tmp_path):
        results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(4)]
        bm = compute_metrics(_make_batch_result(results))
        baseline = _make_baseline(bm, tmp_path)

        report = check_regression(bm, baseline)
        assert report.passed is True
        assert report.verdict == "PASS"
        assert report.findings == []
        assert report.case_regressions == []

    def test_small_score_drop_below_threshold_passes(self, tmp_path):
        results_base = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(4)]
        bm_base = compute_metrics(_make_batch_result(results_base))
        baseline = _make_baseline(bm_base, tmp_path)

        # Drop avg_score by 0.02 — below default threshold of 0.05
        results_curr = [_make_run_result(case_id=f"c{i}", final_score=0.98) for i in range(4)]
        bm_curr = compute_metrics(_make_batch_result(results_curr))

        report = check_regression(bm_curr, baseline)
        assert report.passed is True


class TestRegressionPassRateDrop:
    def test_pass_rate_drop_triggers_high(self, tmp_path):
        # Baseline: 10/10 pass
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(10)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Current: 4/10 pass → pass_rate 0.4 vs baseline 1.0 → drop 0.6 >> 0.05 threshold
        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(4)]
            + [_make_run_result(case_id=f"c{i+4}", final_status="fail", final_score=0.3) for i in range(6)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert report.passed is False
        metrics_names = {f.metric for f in report.findings}
        assert "pass_rate" in metrics_names
        pr_finding = next(f for f in report.findings if f.metric == "pass_rate")
        assert pr_finding.severity == SEVERITY_HIGH


class TestRegressionAvgScoreDrop:
    def test_avg_score_drop_triggers_high(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(5)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [_make_run_result(case_id=f"c{i}", final_score=0.8) for i in range(5)]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        # Drop is 0.2, threshold default 0.05 → should flag
        report = check_regression(bm_curr, baseline)
        assert any(f.metric == "avg_score" for f in report.findings)
        score_finding = next(f for f in report.findings if f.metric == "avg_score")
        assert score_finding.severity == SEVERITY_HIGH


class TestRegressionHardFail:
    def test_new_hard_fail_triggers_critical(self, tmp_path):
        # Baseline: 0 hard fails
        base_results = [_make_run_result(case_id=f"c{i}", hard_fail=False) for i in range(3)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Current: 1 hard fail
        curr_results = [
            _make_run_result(case_id="c0", hard_fail=True, final_status="fail", final_score=0.0),
            _make_run_result(case_id="c1", hard_fail=False),
            _make_run_result(case_id="c2", hard_fail=False),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert any(f.metric == "hard_fail_count" for f in report.findings)
        hf_finding = next(f for f in report.findings if f.metric == "hard_fail_count")
        assert hf_finding.severity == SEVERITY_CRITICAL


class TestRegressionErrorRate:
    def test_error_rate_increase_triggers_medium(self, tmp_path):
        # Baseline: 0 errors / 10 total
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass") for i in range(10)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Current: 3 errors / 10 total → error_rate 0.3 >> threshold 0.05
        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="pass") for i in range(7)]
            + [_make_run_result(case_id=f"e{i}", final_status="error", final_score=0.0, execution_status="error") for i in range(3)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert any(f.metric == "error_rate" for f in report.findings)
        er_finding = next(f for f in report.findings if f.metric == "error_rate")
        assert er_finding.severity == SEVERITY_MEDIUM


class TestRegressionLatency:
    def test_p95_latency_increase_triggers_low(self, tmp_path):
        # Baseline: all 10ms
        base_results = [_make_run_result(case_id=f"c{i}", duration_ms=10.0) for i in range(5)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Current: all 100ms → 10x increase, way above 50% threshold
        curr_results = [_make_run_result(case_id=f"c{i}", duration_ms=100.0) for i in range(5)]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert any(f.metric == "p95_duration_ms" for f in report.findings)
        lat_finding = next(f for f in report.findings if f.metric == "p95_duration_ms")
        assert lat_finding.severity == SEVERITY_LOW


class TestRegressionRuntimeMetrics:
    def test_avg_attempt_retry_and_fallback_increase_trigger(self, tmp_path):
        base_results = [
            _make_run_result(
                case_id="c0",
                metadata={"attempt_count": 1, "retry_count": 0, "framework_fallback_count": 0},
            ),
            _make_run_result(
                case_id="c1",
                metadata={"attempt_count": 1, "retry_count": 0, "framework_fallback_count": 0},
            ),
        ]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(
                case_id="c0",
                metadata={"attempt_count": 3, "retry_count": 2, "framework_fallback_count": 1},
            ),
            _make_run_result(
                case_id="c1",
                metadata={"attempt_count": 2, "retry_count": 1, "framework_fallback_count": 1},
            ),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        findings = {finding.metric: finding for finding in report.findings}
        assert findings["avg_attempt_count"].severity == SEVERITY_MEDIUM
        assert findings["avg_retry_count"].severity == SEVERITY_MEDIUM
        assert findings["avg_fallback_count"].severity == SEVERITY_MEDIUM

    def test_avg_total_tokens_pct_increase_triggers_low(self, tmp_path):
        base_results = [
            _make_run_result(
                case_id="c0",
                solve_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            ),
            _make_run_result(
                case_id="c1",
                solve_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            ),
        ]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(
                case_id="c0",
                solve_metadata={"token_usage": {"prompt_tokens": 150, "completion_tokens": 30}},
            ),
            _make_run_result(
                case_id="c1",
                solve_metadata={"token_usage": {"prompt_tokens": 150, "completion_tokens": 30}},
            ),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        finding = next(f for f in report.findings if f.metric == "avg_total_tokens")
        assert finding.severity == SEVERITY_LOW

    def test_avg_estimated_cost_pct_increase_triggers_low(self, tmp_path):
        base_results = [
            _make_run_result(case_id="c0", solve_metadata={"costs": {"cost_usd": 0.01}}),
            _make_run_result(case_id="c1", solve_metadata={"costs": {"cost_usd": 0.01}}),
        ]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(case_id="c0", solve_metadata={"costs": {"cost_usd": 0.02}}),
            _make_run_result(case_id="c1", solve_metadata={"costs": {"cost_usd": 0.02}}),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        finding = next(f for f in report.findings if f.metric == "avg_estimated_cost")
        assert finding.severity == SEVERITY_LOW

    def test_runtime_metric_regression_skips_when_baseline_has_no_coverage(self, tmp_path):
        base_results = [_make_run_result(case_id="c0"), _make_run_result(case_id="c1")]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(
                case_id="c0",
                metadata={"attempt_count": 4, "retry_count": 3, "framework_fallback_count": 1},
                solve_metadata={"token_usage": {"prompt_tokens": 200, "completion_tokens": 50}},
            ),
            _make_run_result(
                case_id="c1",
                metadata={"attempt_count": 4, "retry_count": 3, "framework_fallback_count": 1},
                solve_metadata={"token_usage": {"prompt_tokens": 200, "completion_tokens": 50}},
            ),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert not any(
            finding.metric in {
                "avg_attempt_count",
                "avg_retry_count",
                "avg_fallback_count",
                "avg_total_tokens",
                "avg_estimated_cost",
            }
            for finding in report.findings
        )


class TestRegressionCaseDrop:
    def test_per_case_score_drop(self, tmp_path):

        base_results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(3)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Case c1 drops from 1.0 → 0.5 (delta 0.5 >> threshold 0.1)
        curr_results = [
            _make_run_result(case_id="c0", final_score=1.0),
            _make_run_result(case_id="c1", final_score=0.5),
            _make_run_result(case_id="c2", final_score=1.0),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert any("c1" in f.metric for f in report.case_regressions)

    def test_case_score_drop_at_exact_threshold_does_not_trigger(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(20)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(case_id="c0", final_score=0.9),
            *[_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(1, 20)],
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert report.case_regressions == []

    def test_new_case_not_flagged(self, tmp_path):
        """Cases that are new (not in baseline) should not be flagged."""
        base_results = [_make_run_result(case_id="old", final_score=1.0)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(case_id="old", final_score=1.0),
            _make_run_result(case_id="new_case", final_score=0.2),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        # new_case should not appear as regression (it has no baseline)
        case_ids = [f.metric for f in report.case_regressions]
        assert not any("new_case" in cid for cid in case_ids)



class TestRegressionThresholdBoundaries:
    def test_pass_rate_drop_at_exact_threshold_does_not_trigger(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(20)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(19)]
            + [_make_run_result(case_id="c19", final_status="fail", final_score=1.0)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert not any(f.metric == "pass_rate" for f in report.findings)

    def test_pass_rate_drop_above_threshold_triggers(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(20)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(18)]
            + [_make_run_result(case_id=f"c{i}", final_status="fail", final_score=1.0) for i in range(18, 20)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert any(f.metric == "pass_rate" for f in report.findings)


class TestRegressionCustomThresholds:
    def test_strict_threshold_triggers(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(4)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Drop by 0.03 — above strict threshold of 0.01 but below default 0.05
        curr_results = [_make_run_result(case_id=f"c{i}", final_score=0.97) for i in range(4)]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        strict = RegressionThresholds(avg_score_drop=0.01)
        report_strict = check_regression(bm_curr, baseline, thresholds=strict)
        assert any(f.metric == "avg_score" for f in report_strict.findings)

        # Same data, default threshold → should pass
        report_default = check_regression(bm_curr, baseline)
        assert not any(f.metric == "avg_score" for f in report_default.findings)



class TestCheckRegressionFromStore:
    def test_convenience_wrapper(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(3)]
        bm = compute_metrics(_make_batch_result(results))
        rec = store.lock(bm, label="conv-test")

        report = check_regression_from_store(bm, store, rec.baseline_id)
        assert report.passed is True

    def test_missing_baseline_raises(self, tmp_path):
        store = BaselineStore(str(tmp_path / "baselines"))
        bm = compute_metrics(_make_batch_result([_make_run_result()]))
        with pytest.raises(FileNotFoundError):
            check_regression_from_store(bm, store, "missing-id")


class TestRegressionReport:
    def test_to_dict_json_serialisable(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_score=1.0) for i in range(3)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [_make_run_result(case_id=f"c{i}", final_score=0.5) for i in range(3)]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        d = report.to_dict()
        json.dumps(d)  # must not raise

    def test_has_critical_property(self, tmp_path):
        # 0 hard fails → 1 → CRITICAL
        base_results = [_make_run_result(case_id=f"c{i}", hard_fail=False) for i in range(2)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = [
            _make_run_result(case_id="c0", hard_fail=True, final_status="fail", final_score=0.0),
            _make_run_result(case_id="c1", hard_fail=False),
        ]
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert report.has_critical is True

    def test_has_high_property_includes_case_regressions(self, tmp_path):
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(40)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0) for i in range(39)]
            + [_make_run_result(case_id="c39", final_status="fail", final_score=0.89)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        assert report.findings == []
        assert len(report.case_regressions) == 1
        assert report.case_regressions[0].severity == SEVERITY_HIGH
        assert report.has_high is True
        assert report.findings_by_severity()[0].metric == "case:c39"

    def test_findings_by_severity_ordering(self, tmp_path):
        """findings_by_severity() must put CRITICAL before HIGH before MEDIUM."""
        base_results = [_make_run_result(case_id=f"c{i}", final_status="pass", final_score=1.0, hard_fail=False) for i in range(10)]
        bm_base = compute_metrics(_make_batch_result(base_results))
        baseline = _make_baseline(bm_base, tmp_path)

        # Trigger multiple severities: hard_fail (CRITICAL), pass_rate drop (HIGH)
        curr_results = (
            [_make_run_result(case_id=f"c{i}", final_status="fail", final_score=0.3) for i in range(7)]
            + [_make_run_result(case_id="c7", hard_fail=True, final_status="fail", final_score=0.0)]
            + [_make_run_result(case_id="c8", final_status="pass", final_score=1.0)]
            + [_make_run_result(case_id="c9", final_status="pass", final_score=1.0)]
        )
        bm_curr = compute_metrics(_make_batch_result(curr_results))

        report = check_regression(bm_curr, baseline)
        ordered = report.findings_by_severity()
        severities = [f.severity for f in ordered]
        # CRITICAL must appear before HIGH if both present
        if SEVERITY_CRITICAL in severities and SEVERITY_HIGH in severities:
            assert severities.index(SEVERITY_CRITICAL) < severities.index(SEVERITY_HIGH)

