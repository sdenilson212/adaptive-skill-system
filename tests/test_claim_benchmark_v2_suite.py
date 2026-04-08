"""Tests for the claim benchmark v2 suite.

Covers:
- Job list structure (36 jobs, correct IDs and layer/difficulty split)
- End-to-end run: all 36 cases execute without error, layer routing is correct
- KB/LTM seed client contract tests
- Difficulty-tier slicing
"""

from __future__ import annotations

import pytest

from adaptive_skill.harness.claim_benchmark_v2_suite import (
    CLAIM_BENCHMARK_V2_SUITE_ID,
    DEFAULT_BATCH_ID_V2,
    ClaimBenchmarkV2KBClient,
    ClaimBenchmarkV2LTMClient,
    build_claim_benchmark_v2_jobs,
    build_claim_benchmark_v2_system,
    run_claim_benchmark_v2,
)


# ---------------------------------------------------------------------------
# Job list structure
# ---------------------------------------------------------------------------


class TestBuildClaimBenchmarkV2Jobs:
    def test_returns_36_jobs(self):
        jobs = build_claim_benchmark_v2_jobs()
        assert len(jobs) == 36

    def test_layer_split_is_12_12_12(self):
        jobs = build_claim_benchmark_v2_jobs()
        l1 = [j for j in jobs if j.case.expected_layer == [1]]
        l2 = [j for j in jobs if j.case.expected_layer == [2]]
        l3 = [j for j in jobs if j.case.expected_layer == [3]]
        assert len(l1) == 12
        assert len(l2) == 12
        assert len(l3) == 12

    def test_difficulty_split_easy_4_per_layer(self):
        jobs = build_claim_benchmark_v2_jobs()
        for layer in ([1], [2], [3]):
            easy = [
                j for j in jobs
                if j.case.expected_layer == layer
                and j.case.metadata.get("difficulty") == "easy"
            ]
            assert len(easy) == 4, f"Layer {layer} should have 4 easy cases"

    def test_difficulty_split_medium_4_per_layer(self):
        jobs = build_claim_benchmark_v2_jobs()
        for layer in ([1], [2], [3]):
            medium = [
                j for j in jobs
                if j.case.expected_layer == layer
                and j.case.metadata.get("difficulty") == "medium"
            ]
            assert len(medium) == 4, f"Layer {layer} should have 4 medium cases"

    def test_difficulty_split_hard_4_per_layer(self):
        jobs = build_claim_benchmark_v2_jobs()
        for layer in ([1], [2], [3]):
            hard = [
                j for j in jobs
                if j.case.expected_layer == layer
                and j.case.metadata.get("difficulty") == "hard"
            ]
            assert len(hard) == 4, f"Layer {layer} should have 4 hard cases"

    def test_case_ids_are_unique(self):
        jobs = build_claim_benchmark_v2_jobs()
        ids = [j.case.case_id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_grader_ids_are_unique(self):
        jobs = build_claim_benchmark_v2_jobs()
        ids = [j.grader.grader_id for j in jobs]
        assert len(ids) == len(set(ids))

    def test_all_cases_tagged_claim_benchmark_v2(self):
        jobs = build_claim_benchmark_v2_jobs()
        for job in jobs:
            assert "claim-benchmark-v2" in job.case.tags

    def test_suite_id_in_metadata(self):
        jobs = build_claim_benchmark_v2_jobs()
        for job in jobs:
            assert job.case.metadata.get("suite") == CLAIM_BENCHMARK_V2_SUITE_ID

    def test_no_overlap_with_v1_case_ids(self):
        """v2 cases must be completely independent from v1."""
        v1_ids = {
            "claim-l1-content-strategy-v1",
            "claim-l1-meeting-facilitation-v1",
            "claim-l1-okr-goal-setting-v1",
            "claim-l1-onboarding-checklist-v1",
            "claim-l1-bug-triage-v1",
            "claim-l1-feedback-loop-v1",
            "claim-l2-product-launch-v1",
            "claim-l2-remote-team-v1",
            "claim-l2-growth-funnel-v1",
            "claim-l2-content-calendar-v1",
            "claim-l2-perf-review-v1",
            "claim-l2-event-planning-v1",
            "claim-l3-ai-product-roadmap-v1",
            "claim-l3-crossfunc-kickoff-v1",
            "claim-l3-data-culture-v1",
            "claim-l3-brand-new-market-v1",
            "claim-l3-tech-debt-v1",
            "claim-l3-community-led-growth-v1",
        }
        jobs = build_claim_benchmark_v2_jobs()
        v2_ids = {j.case.case_id for j in jobs}
        overlap = v1_ids & v2_ids
        assert overlap == set(), f"v2 should not share case IDs with v1: {overlap}"


# ---------------------------------------------------------------------------
# KB client contract
# ---------------------------------------------------------------------------


class TestClaimBenchmarkV2KBClient:
    def setup_method(self):
        self.kb = ClaimBenchmarkV2KBClient()

    def test_search_hiring_returns_skill(self):
        results = self.kb.search("招聘流程 简历筛选 Offer")
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "kb-hiring-pipeline" in ids

    def test_search_crisis_comms_returns_skill(self):
        results = self.kb.search("危机沟通 声明 透明")
        ids = [r["id"] for r in results]
        assert "kb-crisis-comms" in ids

    def test_search_pricing_basic_returns_skill(self):
        results = self.kb.search("定价策略 成本加成 价值定价")
        ids = [r["id"] for r in results]
        assert "kb-pricing-basic" in ids

    def test_search_ab_test_returns_skill(self):
        results = self.kb.search("A/B测试 样本量 显著性")
        ids = [r["id"] for r in results]
        assert "kb-ab-test-setup" in ids

    def test_search_api_design_returns_skill(self):
        results = self.kb.search("API设计 版本控制 错误码")
        ids = [r["id"] for r in results]
        assert "kb-api-design" in ids

    def test_search_knowledge_mgmt_returns_skill(self):
        results = self.kb.search("知识管理 捕获 检索")
        ids = [r["id"] for r in results]
        assert "kb-knowledge-mgmt" in ids

    def test_search_sprint_retro_returns_skill(self):
        results = self.kb.search("Sprint复盘 行动项 敏捷")
        ids = [r["id"] for r in results]
        assert "kb-sprint-retro" in ids

    def test_search_stakeholder_map_returns_skill(self):
        results = self.kb.search("干系人 影响力 沟通策略")
        ids = [r["id"] for r in results]
        assert "kb-stakeholder-map" in ids

    def test_search_pricing_advanced_returns_skill(self):
        results = self.kb.search("高级定价策略 分层定价 捆绑销售")
        ids = [r["id"] for r in results]
        assert "kb-pricing-advanced" in ids

    def test_search_ml_deploy_returns_skill(self):
        results = self.kb.search("ML模型上线 数据漂移 回滚")
        ids = [r["id"] for r in results]
        assert "kb-ml-deploy-checklist" in ids

    def test_search_compliance_returns_skill(self):
        results = self.kb.search("企业合规 风险识别 内部审计")
        ids = [r["id"] for r in results]
        assert "kb-compliance-framework" in ids

    def test_search_threat_model_returns_skill(self):
        results = self.kb.search("威胁建模 STRIDE 攻击面")
        ids = [r["id"] for r in results]
        assert "kb-threat-model" in ids

    def test_search_unrelated_returns_empty(self):
        results = self.kb.search("黄浦江边跑步5公里配速")
        assert results == []

    def test_get_existing_skill(self):
        skill = self.kb.get("kb-hiring-pipeline")
        assert skill is not None
        assert skill["id"] == "kb-hiring-pipeline"

    def test_get_nonexistent_returns_none(self):
        assert self.kb.get("nonexistent-v2-skill") is None


# ---------------------------------------------------------------------------
# LTM client contract
# ---------------------------------------------------------------------------


class TestClaimBenchmarkV2LTMClient:
    def setup_method(self):
        self.ltm = ClaimBenchmarkV2LTMClient()

    # Layer 2 recalls
    def test_recall_competitive_analysis_returns_list(self):
        result = self.ltm.recall("竞品分析 护城河 差异化")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-competitive-positioning" in ids
        assert "ltm-competitive-moat" in ids

    def test_recall_supply_chain_returns_list(self):
        result = self.ltm.recall("供应链 库存管控 需求预测")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-supply-chain-basics" in ids
        assert "ltm-supply-chain-resilience" in ids

    def test_recall_customer_success_returns_list(self):
        result = self.ltm.recall("客户成功 健康度 续约")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-customer-success-health" in ids
        assert "ltm-customer-success-playbook" in ids

    def test_recall_investor_deck_returns_list(self):
        result = self.ltm.recall("投资人 融资 TAM MRR")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-investor-deck-story" in ids
        assert "ltm-investor-deck-metrics" in ids

    def test_recall_mlops_returns_list(self):
        result = self.ltm.recall("MLOps 机器学习流水线 数据漂移")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-mlops-pipeline" in ids
        assert "ltm-mlops-monitoring" in ids

    def test_recall_sprint_planning_returns_list(self):
        result = self.ltm.recall("Sprint规划 容量规划 依赖管理")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-dev-sprint-capacity" in ids
        assert "ltm-dev-sprint-dependencies" in ids

    def test_recall_competitive_intel_returns_list(self):
        result = self.ltm.recall("竞争情报 竞品响应 情报源")
        assert isinstance(result, list)
        ids = [r["id"] for r in result]
        assert "ltm-competitive-intel-signals" in ids
        assert "ltm-competitive-response" in ids

    # Layer 3 stateful: first call returns [] to force L2 miss
    @pytest.mark.parametrize("problem", [
        "请帮我做一套 组织设计 方案，基于逆向康威定律降低团队协调成本，适配当前战略阶段。",
        "请帮我制定一套 AI产品 监管策略 路径，包含合规先行、政策参与和监管风险评估。",
        "请帮我设计一套 并购整合 计划，从Day1到6个月内按优先级分阶段完成整合。",
        "请帮我构建一套 生态伙伴 体系，分层管理技术集成伙伴、渠道分销伙伴和战略联盟。",
        "请帮我设计一套 AI安全审查 框架，涵盖模型偏见测试、对抗性输入测试、隐私合规和可解释性要求。",
        "请帮我设计一套 平台架构 演进方案，从单体到微服务再到平台化，包含API Gateway和数据总线设计。",
    ])
    def test_layer3_first_recall_returns_empty(self, problem):
        ltm = ClaimBenchmarkV2LTMClient()
        result = ltm.recall(problem)
        assert result == [], f"First recall for L3 case should be empty, got: {result!r}"

    @pytest.mark.parametrize("problem", [
        "请帮我做一套 组织设计 方案，基于逆向康威定律降低团队协调成本，适配当前战略阶段。",
        "请帮我制定一套 AI产品 监管策略 路径，包含合规先行、政策参与和监管风险评估。",
        "请帮我设计一套 并购整合 计划，从Day1到6个月内按优先级分阶段完成整合。",
        "请帮我构建一套 生态伙伴 体系，分层管理技术集成伙伴、渠道分销伙伴和战略联盟。",
        "请帮我设计一套 AI安全审查 框架，涵盖模型偏见测试、对抗性输入测试、隐私合规和可解释性要求。",
        "请帮我设计一套 平台架构 演进方案，从单体到微服务再到平台化，包含API Gateway和数据总线设计。",
    ])
    def test_layer3_second_recall_returns_dict_context(self, problem):
        ltm = ClaimBenchmarkV2LTMClient()
        ltm.recall(problem)          # first call — returns []
        result = ltm.recall(problem)  # second call — should return context dict
        assert isinstance(result, dict), f"Second recall should be dict, got: {type(result)}"
        assert "references" in result


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------


class TestRunClaimBenchmarkV2:
    """Full end-to-end run of the 36-case claim benchmark v2 suite.

    Verifies:
    - No runner errors
    - All 36 cases execute
    - Layer routing correct for every case
    - No cases result in 'error' execution status
    - Overall pass-rate >= 30/36 (83.3%)
    - L3 cases expose semantic grader scores
    - Difficulty slice pass-rates: easy >= 100%, medium >= 75%, hard >= 50%
    """

    @pytest.fixture(scope="class")
    def batch(self):
        return run_claim_benchmark_v2(
            system_version="test-claim-benchmark-v2",
            batch_id=DEFAULT_BATCH_ID_V2,
        )

    def test_no_runner_errors(self, batch):
        assert batch.runner_errors == []

    def test_36_results(self, batch):
        assert len(batch.results) == 36

    def test_suite_id_in_batch_metadata(self, batch):
        assert batch.metadata["suite"] == CLAIM_BENCHMARK_V2_SUITE_ID

    def test_layer1_cases_route_to_layer1(self, batch):
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        l1_results = [r for r in batch.results if "l1" in r.case_id]
        assert len(l1_results) == 12
        for r in l1_results:
            assert layer_map[r.case_id] == 1, (
                f"{r.case_id} expected layer 1, got {layer_map[r.case_id]}"
            )

    def test_layer2_cases_route_to_layer2(self, batch):
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        l2_results = [r for r in batch.results if "l2" in r.case_id]
        assert len(l2_results) == 12
        for r in l2_results:
            assert layer_map[r.case_id] == 2, (
                f"{r.case_id} expected layer 2, got {layer_map[r.case_id]}"
            )

    def test_layer3_cases_route_to_layer3(self, batch):
        layer_map = {
            r.case_id: r.execution_trace_summary.get("layer")
            for r in batch.results
        }
        l3_results = [r for r in batch.results if "l3" in r.case_id]
        assert len(l3_results) == 12
        for r in l3_results:
            assert layer_map[r.case_id] == 3, (
                f"{r.case_id} expected layer 3, got {layer_map[r.case_id]}"
            )

    def test_no_error_execution_status(self, batch):
        errors = [r for r in batch.results if r.execution_status == "error"]
        assert errors == [], f"Error cases: {[r.case_id for r in errors]}"

    def test_layer3_cases_expose_semantic_grader_scores(self, batch):
        l3_results = [
            r for r in batch.results
            if r.execution_trace_summary.get("layer") == 3
        ]
        assert len(l3_results) == 12
        for r in l3_results:
            assert "skill_name_semantic_match" in r.grader_scores, (
                f"{r.case_id} should expose semantic grader score"
            )
            assert 0.0 <= r.grader_scores["skill_name_semantic_match"] <= 1.0

    def test_all_final_scores_non_negative(self, batch):
        for r in batch.results:
            assert r.final_score >= 0.0

    def test_pass_rate_gte_83_pct(self, batch):
        """At least 30/36 cases must pass (83.3%)."""
        n_passed = sum(1 for r in batch.results if r.final_status == "pass")
        n_total = len(batch.results)
        pass_rate = n_passed / n_total
        assert pass_rate >= 30 / 36, (
            f"v2 benchmark pass rate {pass_rate:.1%} ({n_passed}/{n_total}) "
            f"is below minimum threshold of 83.3% (30/36)."
        )

    def test_easy_cases_pass_rate_high(self, batch):
        """Easy cases should all pass (100%)."""
        easy_results = [r for r in batch.results if "easy" in r.case_id]
        assert len(easy_results) == 12
        n_passed = sum(1 for r in easy_results if r.final_status == "pass")
        assert n_passed == 12, (
            f"Easy cases: {n_passed}/12 passed, expected 12/12"
        )

    def test_supply_chain_easy_cases_pass_after_composition(self, batch):
        target_ids = {
            "claim-v2-l2-easy-supply-chain",
            "claim-v2-l2-easy-supply-chain-risk",
        }
        target_results = [r for r in batch.results if r.case_id in target_ids]
        assert {r.case_id for r in target_results} == target_ids
        for result in target_results:
            assert result.final_status == "pass", f"{result.case_id} should pass after supply-chain composition tuning"
            assert result.execution_trace_summary.get("layer") == 2
            assert result.execution_trace_summary.get("confidence", 0.0) >= 0.80

    def test_medium_cases_pass_rate_gte_75_pct(self, batch):

        """Medium cases: at least 75% pass rate (9/12)."""
        medium_results = [r for r in batch.results if "medium" in r.case_id]
        assert len(medium_results) == 12
        n_passed = sum(1 for r in medium_results if r.final_status == "pass")
        assert n_passed >= 9, (
            f"Medium cases: {n_passed}/12 passed, expected >= 9"
        )

    def test_hard_cases_pass_rate_gte_50_pct(self, batch):
        """Hard cases: at least 50% pass rate (6/12)."""
        hard_results = [r for r in batch.results if "hard" in r.case_id]
        assert len(hard_results) == 12
        n_passed = sum(1 for r in hard_results if r.final_status == "pass")
        assert n_passed >= 6, (
            f"Hard cases: {n_passed}/12 passed, expected >= 6"
        )
