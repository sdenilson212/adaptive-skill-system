"""Tests for the seeded real benchmark suite."""

from __future__ import annotations

from adaptive_skill.harness.benchmark_suite import (
    BENCHMARK_SUITE_ID,
    DEFAULT_BATCH_ID,
    build_benchmark_jobs,
    run_seeded_real_benchmark,
)


class TestBenchmarkSuite:
    def test_build_benchmark_jobs_returns_six_jobs(self):
        jobs = build_benchmark_jobs()

        assert len(jobs) == 6
        assert [job.case.case_id for job in jobs] == [
            "bench-layer1-kb-hit-v1",
            "bench-layer2-compose-v1",
            "bench-layer2-mixed-support-v1",
            "bench-layer3-generate-v1",
            "bench-layer3-sparse-context-v1",
            "bench-layer3-list-fallback-v1",
        ]

    def test_run_seeded_real_benchmark_covers_extended_layer_suite(self):
        batch = run_seeded_real_benchmark(system_version="test-benchmark", batch_id=DEFAULT_BATCH_ID)

        assert batch.batch_id == DEFAULT_BATCH_ID
        assert batch.metadata["suite"] == BENCHMARK_SUITE_ID
        assert len(batch.results) == 6
        assert batch.runner_errors == []

        layer_map = {
            result.case_id: result.execution_trace_summary.get("layer")
            for result in batch.results
        }
        assert layer_map == {
            "bench-layer1-kb-hit-v1": 1,
            "bench-layer2-compose-v1": 2,
            "bench-layer2-mixed-support-v1": 2,
            "bench-layer3-generate-v1": 3,
            "bench-layer3-sparse-context-v1": 3,
            "bench-layer3-list-fallback-v1": 3,
        }

        execution_statuses = {
            result.case_id: result.execution_status for result in batch.results
        }
        assert execution_statuses["bench-layer1-kb-hit-v1"] == "success"
        assert execution_statuses["bench-layer2-compose-v1"] == "success"
        assert execution_statuses["bench-layer2-mixed-support-v1"] == "success"
        # Heuristic-only Layer 3 generation (no LLM) on a limited benchmark seed
        # produces quality ~0.71, which maps to "partial" (success requires >= 0.75).
        # This is the expected behaviour: partial means the gate passed but the
        # result warrants user review before being committed to the skill library.
        assert execution_statuses["bench-layer3-generate-v1"] == "partial"
        assert execution_statuses["bench-layer3-sparse-context-v1"] == "partial"
        # list-fallback also uses heuristic Layer 3 generation and lands in
        # the partial zone (~0.70-0.74); "partial" is expected without an LLM.
        assert execution_statuses["bench-layer3-list-fallback-v1"] in ("partial", "success")

        l3_results = {
            result.case_id: result
            for result in batch.results
            if result.execution_trace_summary.get("layer") == 3
        }
        for case_id, result in l3_results.items():
            assert "skill_name_semantic_match" in result.grader_scores, (
                f"{case_id} should expose semantic grader score"
            )
            assert 0.0 <= result.grader_scores["skill_name_semantic_match"] <= 1.0

        for result in batch.results:
            assert result.final_status != "error"
            assert result.final_score >= 0.0


