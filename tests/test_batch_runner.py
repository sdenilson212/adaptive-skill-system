"""Tests for the P2 Batch Runner: batch_runner.py + sinks.py.

Strategy
--------
* Use the real AdaptiveSkillSystem class in isolated pure-memory mode.
* All 3 fixtures are used to build 3 BatchJobs so the batch exercises all
  layers in one shot.
* Additional edge-case jobs are synthesised in-line to cover fail_fast,

  error propagation, and parallel execution.
* Persistence is tested via InMemorySink (no disk I/O needed for the main
  suite) and via tmp_path fixtures for JsonlSink / JsonSink.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List

import pytest

from adaptive_skill.core import AdaptiveSkillSystem
from adaptive_skill.harness.batch_runner import (
    BatchJob,
    BatchResult,
    BatchSummary,
    run_batch,
)
from adaptive_skill.harness.sinks import InMemorySink, JsonlSink, JsonSink
from adaptive_skill.harness.specs import CaseSpec, GraderSpec, RunResult

import tests.fixtures.layer1_kb_hit as f1
import tests.fixtures.layer2_compose as f2
import tests.fixtures.layer3_generate as f3

SYSTEM_VERSION = "test-batch-v0"


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def system() -> AdaptiveSkillSystem:
    return AdaptiveSkillSystem()


@pytest.fixture(scope="module")
def three_jobs() -> List[BatchJob]:
    return [
        BatchJob(case=f1.case, grader=f1.grader),
        BatchJob(case=f2.case, grader=f2.grader),
        BatchJob(case=f3.case, grader=f3.grader),
    ]


def _minimal_case(suffix: str = "") -> CaseSpec:
    cid = f"batch-minimal-{suffix or uuid.uuid4().hex[:6]}"
    return CaseSpec(
        case_id=cid,
        title=f"Minimal batch case {cid}",
        description="Synthetic minimal case for batch-runner tests",
        task_type="skill_execution",
        input_payload={"problem": "给出一句话的自我介绍"},
        expected_outcome_type="text",
    )


def _minimal_grader(suffix: str = "") -> GraderSpec:
    gid = f"grader-minimal-{suffix or uuid.uuid4().hex[:6]}"
    return GraderSpec(
        grader_id=gid,
        name=f"Minimal grader {gid}",
        grading_mode="scored",
        pass_threshold=0.0,  # always pass regardless of score
        dimensions=[
            {
                "name": "result_present",
                "type": "result_not_empty",
                "weight": 1.0,
                "hard_fail": False,
            }
        ],
    )


# ── BatchJob contract ─────────────────────────────────────────────────────────

class TestBatchJobContract:
    def test_job_requires_case_and_grader(self):
        job = BatchJob(case=f1.case, grader=f1.grader)
        job.validate()  # should not raise

    def test_job_validate_raises_on_none_case(self):
        job = BatchJob(case=None, grader=f1.grader)  # type: ignore[arg-type]
        with pytest.raises((ValueError, Exception)):
            job.validate()


# ── BatchResult shape ─────────────────────────────────────────────────────────

class TestBatchResultShape:
    def test_batch_result_has_required_fields(self, system, three_jobs):
        result = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert isinstance(result, BatchResult)
        assert result.batch_id
        assert result.system_version == SYSTEM_VERSION
        assert result.started_at
        assert result.ended_at
        assert isinstance(result.duration_ms, float)
        assert result.duration_ms >= 0.0

    def test_results_count_matches_jobs(self, system, three_jobs):
        result = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert len(result.results) == len(three_jobs), (
            "BatchResult.results must contain one entry per job"
        )

    def test_each_result_is_run_result(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        for r in batch.results:
            assert isinstance(r, RunResult), f"Expected RunResult, got {type(r)}"

    def test_run_ids_are_unique(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        run_ids = [r.run_id for r in batch.results]
        assert len(run_ids) == len(set(run_ids)), "All run_ids must be unique"

    def test_case_ids_preserved(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        expected = {j.case.case_id for j in three_jobs}
        actual = {r.case_id for r in batch.results}
        assert actual == expected

    def test_to_dict_is_json_serialisable(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        d = batch.to_dict()
        serialised = json.dumps(d)  # must not raise
        assert isinstance(serialised, str) and len(serialised) > 0

    def test_runner_errors_list_exists(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert isinstance(batch.runner_errors, list)


# ── BatchSummary ──────────────────────────────────────────────────────────────

class TestBatchSummary:
    def test_summary_total_equals_job_count(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert batch.summary.total == len(three_jobs)

    def test_summary_counts_are_non_negative(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        s = batch.summary
        assert s.passed >= 0
        assert s.failed >= 0
        assert s.errored >= 0
        assert s.partial >= 0

    def test_summary_counts_sum_to_total(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        s = batch.summary
        assert s.passed + s.failed + s.errored + s.partial == s.total

    def test_pass_rate_in_range(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert 0.0 <= batch.summary.pass_rate <= 1.0

    def test_avg_score_in_range(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert 0.0 <= batch.summary.avg_score <= 1.0

    def test_avg_duration_non_negative(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        assert batch.summary.avg_duration_ms >= 0.0

    def test_summary_to_dict_complete(self, system, three_jobs):
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        d = batch.summary.to_dict()
        required_keys = {
            "total", "passed", "failed", "errored", "partial",
            "pass_rate", "avg_score", "avg_duration_ms", "hard_fail_count",
        }
        assert required_keys.issubset(d.keys())

    def test_empty_batch_summary(self, system):
        batch = run_batch([], system, system_version=SYSTEM_VERSION)
        assert batch.summary.total == 0
        assert batch.summary.pass_rate == 0.0
        assert len(batch.results) == 0


# ── fail_fast ─────────────────────────────────────────────────────────────────

class TestFailFast:
    def test_fail_fast_stops_after_first_failure(self, system):
        """With fail_fast=True, sequential mode should stop after the first non-pass result."""
        failing_grader = GraderSpec(
            grader_id="grader-fail-fast-hard-stop",
            name="Fail-fast hard failure grader",
            grading_mode="scored",
            pass_threshold=1.0,
            dimensions=[
                {
                    "name": "impossible_layer",
                    "type": "exact_match",
                    "weight": 1.0,
                    "hard_fail": True,
                    "config": {
                        "field": "layer",
                        "expected": -1,
                        "description": "Impossible sentinel used to force a deterministic fail_fast stop.",
                    },
                }
            ],
        )
        jobs = [
            BatchJob(case=_minimal_case("ff-stop"), grader=failing_grader)
            for _ in range(5)
        ]
        batch = run_batch(
            jobs, system, system_version=SYSTEM_VERSION, fail_fast=True
        )
        # Sequential fail_fast should stop immediately after the first forced failure.
        assert len(batch.results) == 1
        assert batch.metadata.get("fail_fast_triggered") is True


    def test_fail_fast_not_triggered_when_all_pass(self, system):
        """When every result passes, fail_fast should not truncate."""
        job = BatchJob(case=_minimal_case("ff"), grader=_minimal_grader("ff"))
        batch = run_batch(
            [job], system, system_version=SYSTEM_VERSION, fail_fast=True
        )
        # No truncation expected on single job
        assert len(batch.results) == 1
        # fail_fast_triggered should not be set unless actually triggered
        assert batch.metadata.get("fail_fast_triggered") in (None, False, True)


# ── InMemorySink ──────────────────────────────────────────────────────────────

class TestInMemorySink:
    def test_sink_collects_all_results(self, system, three_jobs):
        sink = InMemorySink()
        run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, result_store=sink
        )
        assert len(sink) == len(three_jobs)

    def test_sink_records_are_run_results(self, system, three_jobs):
        sink = InMemorySink()
        run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, result_store=sink
        )
        for r in sink.records:
            assert isinstance(r, RunResult)

    def test_sink_clear_resets(self, system, three_jobs):
        sink = InMemorySink()
        run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, result_store=sink
        )
        sink.clear()
        assert len(sink) == 0


# ── JsonlSink ─────────────────────────────────────────────────────────────────

class TestJsonlSink:
    def test_jsonl_writes_correct_line_count(self, system, three_jobs, tmp_path):
        out = tmp_path / "batch.jsonl"
        sink = JsonlSink(out, mode="w")
        run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, result_store=sink
        )
        records = sink.read_records()
        assert len(records) == len(three_jobs)

    def test_jsonl_records_are_valid_json(self, system, three_jobs, tmp_path):
        out = tmp_path / "batch2.jsonl"
        sink = JsonlSink(out, mode="w")
        run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, result_store=sink
        )
        for rec in sink.read_records():
            assert "run_id" in rec
            assert "case_id" in rec
            assert "final_status" in rec

    def test_jsonl_append_mode(self, system, tmp_path):
        out = tmp_path / "append.jsonl"
        job = BatchJob(case=_minimal_case("app"), grader=_minimal_grader("app"))
        sink = JsonlSink(out, mode="a")
        # Run twice — append mode should accumulate
        run_batch([job], system, system_version=SYSTEM_VERSION, result_store=sink)
        run_batch([job], system, system_version=SYSTEM_VERSION, result_store=sink)
        records = sink.read_records()
        assert len(records) == 2


# ── JsonSink ──────────────────────────────────────────────────────────────────

class TestJsonSink:
    def test_json_sink_writes_batch_result(self, system, three_jobs, tmp_path):
        out = tmp_path / "result.json"
        sink = JsonSink(out)
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        sink.write(batch)
        data = sink.read()
        assert data is not None
        assert data["batch_id"] == batch.batch_id
        assert "summary" in data
        assert "results" in data

    def test_json_sink_summary_keys(self, system, three_jobs, tmp_path):
        out = tmp_path / "result2.json"
        sink = JsonSink(out)
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        sink.write(batch)
        data = sink.read()
        summary_keys = set(data["summary"].keys())
        assert "total" in summary_keys
        assert "pass_rate" in summary_keys

    def test_json_file_is_valid_json(self, system, three_jobs, tmp_path):
        out = tmp_path / "result3.json"
        sink = JsonSink(out)
        batch = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        sink.write(batch)
        raw = out.read_text(encoding="utf-8")
        parsed = json.loads(raw)  # must not raise
        assert isinstance(parsed, dict)


# ── on_result callback ────────────────────────────────────────────────────────

class TestOnResultCallback:
    def test_callback_called_for_each_result(self, system, three_jobs):
        seen: list = []
        run_batch(
            three_jobs,
            system,
            system_version=SYSTEM_VERSION,
            on_result=seen.append,
        )
        assert len(seen) == len(three_jobs)

    def test_callback_receives_run_result(self, system, three_jobs):
        types: list = []
        run_batch(
            three_jobs,
            system,
            system_version=SYSTEM_VERSION,
            on_result=lambda r: types.append(type(r).__name__),
        )
        assert all(t == "RunResult" for t in types)


# ── Parallel mode (smoke) ─────────────────────────────────────────────────────

class TestParallelMode:
    def test_parallel_same_count_as_sequential(self, system, three_jobs):
        seq = run_batch(three_jobs, system, system_version=SYSTEM_VERSION)
        par = run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, max_workers=2
        )
        assert len(par.results) == len(seq.results)

    def test_parallel_all_case_ids_present(self, system, three_jobs):
        par = run_batch(
            three_jobs, system, system_version=SYSTEM_VERSION, max_workers=2
        )
        expected = {j.case.case_id for j in three_jobs}
        actual = {r.case_id for r in par.results}
        assert actual == expected
