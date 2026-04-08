"""Tests for the claim benchmark v1 suite.

Covers:
- Job list structure (18 jobs, correct IDs and layer split)
- End-to-end run: all 18 cases execute without error, layer routing is correct
- KB/LTM seed client contract tests (search, recall)
"""

from __future__ import annotations

import pytest

from adaptive_skill.harness.claim_benchmark_suite import (
    CLAIM_BENCHMARK_SUITE_ID,
    DEFAULT_BATCH_ID,
    ClaimBenchmarkKBClient,
    ClaimBenchmarkLTMClient,
    build_claim_benchmark_jobs,
    build_claim_benchmark_system,
    run_claim_benchmark,
)


# ---------------------------------------------------------------------------
# Job list structure
# ---------------------------------------------------------------------------


class TestBuildClaimBenchmarkJobs:
    def test_returns_18_jobs(self):
        jobs = build_claim_benchmark_jobs()
        assert len(jobs) == 18

    def test_layer_split_is_6_6_6(self):
        jobs = build_claim_benchmark_jobs()
        l1 = [j for j in jobs if j.case.expected_layer == [1]]
        l2 = [j for j in jobs if j.case.expected_layer == [2]]
        l3 = [j for j in jobs if j.case.expected_layer == [3]]
        assert len(l1) == 6
        assert len(l2) == 6
        assert len(l3) == 6

    def test_case_ids_are_unique(self):
        jobs = build_claim_benchmark_jobs()
        ids = [j.case.case_id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_grader_ids_are_unique(self):
        jobs = build_claim_benchmark_jobs()
        ids = [j.grader.grader_id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_all_cases_tagged_claim_benchmark(self):
        jobs = build_claim_benchmark_jobs()
        for job in jobs:
            assert "claim-benchmark" in job.case.tags

    def test_suite_id_in_metadata(self):
        jobs = build_claim_benchmark_jobs()
        for job in jobs:
            assert job.case.metadata.get("suite") == CLAIM_BENCHMARK_SUITE_ID

    def test_layer1_case_ids(self):
        jobs = build_claim_benchmark_jobs()
        l1_ids = [j.case.case_id for j in jobs if j.case.expected_layer == [1]]
        assert set(l1_ids) == {
            "claim-l1-content-strategy-v1",
            "claim-l1-meeting-facilitation-v1",
            "claim-l1-okr-goal-setting-v1",
            "claim-l1-onboarding-checklist-v1",
            "claim-l1-bug-triage-v1",
            "claim-l1-feedback-loop-v1",
        }

    def test_layer2_case_ids(self):
        jobs = build_claim_benchmark_jobs()
        l2_ids = [j.case.case_id for j in jobs if j.case.expected_layer == [2]]
        assert set(l2_ids) == {
            "claim-l2-product-launch-v1",
            "claim-l2-remote-team-v1",
            "claim-l2-growth-funnel-v1",
            "claim-l2-content-calendar-v1",
            "claim-l2-perf-review-v1",
            "claim-l2-event-planning-v1",
        }

    def test_layer3_case_ids(self):
        jobs = build_claim_benchmark_jobs()
        l3_ids = [j.case.case_id for j in jobs if j.case.expected_layer == [3]]
        assert set(l3_ids) == {
            "claim-l3-ai-product-roadmap-v1",
            "claim-l3-crossfunc-kickoff-v1",
            "claim-l3-data-culture-v1",
            "claim-l3-brand-new-market-v1",
            "claim-l3-tech-debt-v1",
            "claim-l3-community-led-growth-v1",
        }


# ---------------------------------------------------------------------------
# KB client contract
# ---------------------------------------------------------------------------


class TestClaimBenchmarkKBClient:
    def setup_method(self):
        self.kb = ClaimBenchmarkKBClient()

    def test_search_content_strategy_returns_skill(self):
        results = self.kb.search("内容策略 分解法 渠道")
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "kb-content-strategy" in ids

    def test_search_meeting_returns_skill(self):
        results = self.kb.search("会议 议程 行动项")
        ids = [r["id"] for r in results]
        assert "kb-meeting-facilitation" in ids

    def test_search_okr_returns_skill(self):
        results = self.kb.search("OKR 目标管理 量化")
        ids = [r["id"] for r in results]
        assert "kb-okr-goal-setting" in ids

    def test_search_onboarding_returns_skill(self):
        results = self.kb.search("入职 新人 试用期")
        ids = [r["id"] for r in results]
        assert "kb-onboarding-checklist" in ids

    def test_search_bug_triage_returns_skill(self):
        results = self.kb.search("Bug 分级 P0 P1 迭代")
        ids = [r["id"] for r in results]
        assert "kb-bug-triage" in ids

    def test_search_feedback_loop_returns_skill(self):
        results = self.kb.search("用户反馈 闭环 SLA")
        ids = [r["id"] for r in results]
        assert "kb-feedback-loop" in ids

    def test_search_unrelated_returns_empty(self):
        results = self.kb.search("超马跑步训练计划周期化")
        assert results == []

    def test_get_existing_skill(self):
        skill = self.kb.get("kb-content-strategy")
        assert skill is not None
        assert skill["id"] == "kb-content-strategy"

    def test_get_nonexistent_returns_none(self):
        assert self.kb.get("nonexistent-id") is None


# ---------------------------------------------------------------------------
# LTM client contract
# ---------------------------------------------------------------------------


class TestClaimBenchmarkLTMClient:
    def setup_method(self):
        self.ltm = ClaimBenchmarkLTMClient()

    # Layer 2 recalls
    def test_recall_product_launch_returns_list(self):
        result = self.ltm.recall("产品上线 GTM策略 发布渠道")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-product-launch-gtm" in ids
        assert "ltm-product-launch-channels" in ids

    def test_recall_remote_team_returns_list(self):
        result = self.ltm.recall("远程团队 异步协作 跨时区")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-remote-async-comms" in ids
        assert "ltm-remote-timezone" in ids

    def test_recall_growth_funnel_returns_list(self):
        result = self.ltm.recall("用户增长 CAC 激活率 TTV")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-growth-acquisition" in ids
        assert "ltm-growth-activation" in ids

    def test_recall_content_calendar_returns_list(self):
        result = self.ltm.recall("内容日历 内容复用 内容规划")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-content-calendar-themes" in ids
        assert "ltm-content-calendar-reuse" in ids

    def test_recall_perf_review_returns_list(self):
        result = self.ltm.recall("绩效评审 360度 绩效校准")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-perf-review-360" in ids
        assert "ltm-perf-review-calibration" in ids

    def test_recall_event_planning_returns_list(self):
        result = self.ltm.recall("活动筹备 线下活动 活动互动")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-event-logistics" in ids
        assert "ltm-event-engagement" in ids

    # Layer 3 stateful: first call returns [] to force L2 miss
    @pytest.mark.parametrize("problem", [
        "请帮我设计一套 AI产品路线图，包含能力边界评估、数据依赖分析和季度迭代节奏规划。",
        "请帮我设计一套 跨职能 项目启动 流程，包含RACI矩阵、决策权边界和沟通频率协议。",
        "请帮我制定一套 数据文化 建设方案，从基础设施、指标体系共识到数据素养培训三条线并进。",
        "请帮我制定一套进入 新市场 的 品牌策略，包含本地化定位、差异化信息和早期社群建设。",
        "请帮我设计一套 技术债务 管理体系，涵盖可见化清单、业务价值挂钩的偿还计划和新增防线。",
        "请帮我构建一套 社区驱动增长 的飞轮模型，涵盖核心用户激励、内容共创和口碑传播机制。",
    ])
    def test_layer3_first_recall_returns_empty(self, problem):
        ltm = ClaimBenchmarkLTMClient()  # fresh instance per parametrize
        result = ltm.recall(problem)
        assert result == [], f"First recall for L3 case should be empty, got: {result!r}"

    @pytest.mark.parametrize("problem", [
        "请帮我设计一套 AI产品路线图，包含能力边界评估、数据依赖分析和季度迭代节奏规划。",
        "请帮我设计一套 跨职能 项目启动 流程，包含RACI矩阵、决策权边界和沟通频率协议。",
        "请帮我制定一套 数据文化 建设方案，从基础设施、指标体系共识到数据素养培训三条线并进。",
        "请帮我制定一套进入 新市场 的 品牌策略，包含本地化定位、差异化信息和早期社群建设。",
        "请帮我设计一套 技术债务 管理体系，涵盖可见化清单、业务价值挂钩的偿还计划和新增防线。",
        "请帮我构建一套 社区驱动增长 的飞轮模型，涵盖核心用户激励、内容共创和口碑传播机制。",
    ])
    def test_layer3_second_recall_returns_dict_context(self, problem):
        ltm = ClaimBenchmarkLTMClient()
        ltm.recall(problem)          # first call — returns []
        result = ltm.recall(problem)  # second call — should return context dict
        assert isinstance(result, dict), f"Second recall should be dict context, got: {type(result)}"
        assert "references" in result


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------


class TestRunClaimBenchmark:
    """Full end-to-end run of the 18-case claim benchmark suite.

    These are the authoritative acceptance tests for the suite.  They verify:
    - No runner errors
    - All 18 cases execute
    - Layer routing is correct for every case
    - No cases result in execution 'error' status
    - Overall pass-rate meets or exceeds 15/18 (≥ 83.3%)
    """

    @pytest.fixture(scope="class")
    def batch(self):
        return run_claim_benchmark(
            system_version="test-claim-benchmark",
            batch_id=DEFAULT_BATCH_ID,
        )

    def test_no_runner_errors(self, batch):
        assert batch.runner_errors == []

    def test_18_results(self, batch):
        assert len(batch.results) == 18

    def test_suite_id_in_batch_metadata(self, batch):
        assert batch.metadata["suite"] == CLAIM_BENCHMARK_SUITE_ID

    def test_layer1_cases_route_to_layer1(self, batch):
        l1_cases = [
            "claim-l1-content-strategy-v1",
            "claim-l1-meeting-facilitation-v1",
            "claim-l1-okr-goal-setting-v1",
            "claim-l1-onboarding-checklist-v1",
            "claim-l1-bug-triage-v1",
            "claim-l1-feedback-loop-v1",
        ]
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        for case_id in l1_cases:
            assert layer_map[case_id] == 1, f"{case_id} expected layer 1, got {layer_map[case_id]}"

    def test_layer2_cases_route_to_layer2(self, batch):
        l2_cases = [
            "claim-l2-product-launch-v1",
            "claim-l2-remote-team-v1",
            "claim-l2-growth-funnel-v1",
            "claim-l2-content-calendar-v1",
            "claim-l2-perf-review-v1",
            "claim-l2-event-planning-v1",
        ]
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        for case_id in l2_cases:
            assert layer_map[case_id] == 2, f"{case_id} expected layer 2, got {layer_map[case_id]}"

    def test_layer3_cases_route_to_layer3(self, batch):
        l3_cases = [
            "claim-l3-ai-product-roadmap-v1",
            "claim-l3-crossfunc-kickoff-v1",
            "claim-l3-data-culture-v1",
            "claim-l3-brand-new-market-v1",
            "claim-l3-tech-debt-v1",
            "claim-l3-community-led-growth-v1",
        ]
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        for case_id in l3_cases:
            assert layer_map[case_id] == 3, f"{case_id} expected layer 3, got {layer_map[case_id]}"

    def test_no_error_execution_status(self, batch):
        errors = [r for r in batch.results if r.execution_status == "error"]
        assert errors == [], f"Error cases: {[r.case_id for r in errors]}"

    def test_layer3_cases_expose_semantic_grader_scores(self, batch):
        l3_results = [
            result for result in batch.results
            if result.execution_trace_summary.get("layer") == 3
        ]
        assert len(l3_results) == 6
        for result in l3_results:
            assert "skill_name_semantic_match" in result.grader_scores, (
                f"{result.case_id} should expose semantic grader score"
            )
            assert 0.0 <= result.grader_scores["skill_name_semantic_match"] <= 1.0

    def test_all_final_scores_non_negative(self, batch):
        for result in batch.results:
            assert result.final_score >= 0.0

    def test_pass_rate_gte_83_pct(self, batch):

        """At least 15/18 cases must pass for the claim benchmark to be credible."""
        n_passed = sum(1 for r in batch.results if r.final_status == "pass")
        n_total = len(batch.results)
        pass_rate = n_passed / n_total
        assert pass_rate >= 15 / 18, (
            f"Claim benchmark pass rate {pass_rate:.1%} ({n_passed}/{n_total}) "
            f"is below the minimum threshold of 83.3% (15/18)."
        )
