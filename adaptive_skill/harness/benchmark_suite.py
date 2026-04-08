"""Seeded real benchmark suite for Adaptive Skill System harness.

This module exists for one specific purpose: run the *real* ``AdaptiveSkillSystem``
solve path against an isolated, reproducible in-memory KB/LTM seed.

Why this exists when CI already has ``run_harness_ci_suite.py``:
- CI smoke is synthetic and deterministic by design; it validates the reporting /
  baseline / regression plumbing, not the solver itself.
- This benchmark runs the actual Layer 1 / 2 / 3 code paths with controlled seed
  data, so it is the closest thing to a stable "system behaviour" baseline that
  does not depend on the developer's local memory-bank contents.

Design notes
------------
- The benchmark seed is deliberately tiny and explicit.
- Layer 1 is exercised via a selective KB match.
- Layer 2 is exercised twice: once for the original composition happy path, and
  once for a mixed-support boundary case that combines three seeded sources.
- Layer 3 is exercised three ways: the canonical ultra-marathon generation path,
  a sparse dict-shaped context, and a list-shaped recall payload used as a
  regression guard.
- The Layer 3 canonical path still intentionally makes the first ultra-marathon
  recall return no composition-ready items, then returns compact generation
  context on the second recall. This mirrors the current core flow:
  Layer 2 recall -> Layer 3 recall with the same problem string.

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..core import AdaptiveSkillSystem
from .batch_runner import BatchJob, BatchResult, run_batch
from .specs import CaseSpec, GraderSpec

BENCHMARK_SUITE_ID = "real-benchmark-v2"
DEFAULT_BATCH_ID = "adaptive-skill-harness-real-benchmark"
DEFAULT_SYSTEM_VERSION = "benchmark-seeded"

PROBLEM_LAYER_2_MIXED_SUPPORT = "请基于 志愿者招募 培训复盘 社群激励 设计一个青年活动运营方案。"
PROBLEM_LAYER_3_PARTIAL_TEMPLATE = "请帮我设计 校园读书会 长期陪伴与打卡反馈机制"
PROBLEM_LAYER_3_LIST_FALLBACK = "请帮我处理 列表回退问题 的陌生任务设计"



def _l3_skill_name_semantic_dimension(reference: str) -> Dict[str, Any]:
    """Build a semantic similarity dimension for Layer-3 generated skill names."""
    return {
        "name": "skill_name_semantic_match",
        "type": "semantic_similarity",
        "weight": 0.30,
        "config": {
            "field": "skill_name",
            "reference": reference,
            "min_similarity": 0.35,
            "method": "sequence_matcher",
        },
    }


@dataclass(frozen=True)

class SeedMemoryItem:
    """Simple value object used by the in-memory LTM seed."""

    item_id: str
    content: str
    category: str
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "content": self.content,
            "category": self.category,
            "tags": list(self.tags),
        }


class SeededBenchmarkKBClient:
    """Minimal KB client that only exposes the methods core.py actually uses."""

    def __init__(self) -> None:
        self._entries: Dict[str, Dict[str, Any]] = {
            "kb-skill-ops": {
                "id": "kb-skill-ops",
                "title": "运营策略分解法",
                "content": "目标定义\n渠道选择\n执行计划\n复盘优化",
                "tags": ["运营", "策略", "分解法"],
            }
        }

    def search(self, query: str, top_k: int = 5):
        normalized = str(query or "")
        if ("运营" in normalized and "策略" in normalized) or "分解法" in normalized:
            return [self._entries["kb-skill-ops"]][:top_k]
        return []

    def get(self, skill_id: str):
        return self._entries.get(skill_id)

    def update(self, skill_id: str, updated_skill: Any) -> None:
        self._entries[skill_id] = updated_skill


class SeededBenchmarkLTMClient:
    """Tiny stateful LTM seed tailored to the benchmark suite.

    The benchmark intentionally mixes multiple recall payload shapes:
    - list payloads for standard Layer 2 composition search
    - dict payloads for compact Layer 3 generation context
    - a dedicated list-shaped full-query fallback to guard against regressions where
      Layer 3 assumes every recall payload is dict-like
    """

    def __init__(self) -> None:
        self._ultra_query_hits = 0
        self._items: Dict[str, SeedMemoryItem] = {
            "psych": SeedMemoryItem(
                item_id="ltm-psych-zgen",
                content="Z世代用户更重视即时反馈、社交认同、成长感和打卡激励。",
                category="insight",
                tags=["Z世代", "心理学", "用户行为"],
            ),
            "data": SeedMemoryItem(
                item_id="ltm-data-retention",
                content="留存分析要关注7日留存、14日留存、完课率、打卡频次和回流率。",
                category="method",
                tags=["数据分析", "留存", "指标"],
            ),
            "community": SeedMemoryItem(
                item_id="ltm-community-loop",
                content="社群挑战、阶段勋章和好友监督可以强化健身App留存。",
                category="discussion",
                tags=["社群", "激励", "健身App"],
            ),
            "volunteer_recruit": SeedMemoryItem(
                item_id="ltm-volunteer-recruit",
                content="青年志愿者招募需要明确岗位、报名门槛和动机设计。",
                category="method",
                tags=["志愿者招募", "岗位设计", "青年活动"],
            ),
            "volunteer_training": SeedMemoryItem(
                item_id="ltm-volunteer-training-retro",
                content="培训和复盘闭环可以提升活动执行一致性，并沉淀下一轮 SOP。",
                category="discussion",
                tags=["培训复盘", "执行闭环", "活动运营"],
            ),
            "volunteer_reward": SeedMemoryItem(
                item_id="ltm-volunteer-reward-loop",
                content="社群激励和荣誉反馈机制可以提高青年活动的参与度与复返率。",
                category="insight",
                tags=["社群激励", "荣誉反馈", "青年活动"],
            ),
            "study_circle": SeedMemoryItem(
                item_id="ltm-study-circle-habit",
                content="读书会长期陪伴机制通常依赖固定打卡、同伴反馈和阶段主题复盘。",
                category="insight",
                tags=["读书会", "打卡反馈", "长期陪伴"],
            ),
            "list_fallback_a": SeedMemoryItem(
                item_id="ltm-list-fallback-a",
                content="陌生任务先拆成目标、约束、反馈回路三个部分再设计方案。",
                category="method",
                tags=["陌生任务", "拆解", "约束"],
            ),
            "list_fallback_b": SeedMemoryItem(
                item_id="ltm-list-fallback-b",
                content="面对没有现成模板的问题时，可以先建立最小可执行版本并保留反馈入口。",
                category="discussion",
                tags=["最小可执行", "反馈入口", "陌生任务"],
            ),
            "ultra_base": SeedMemoryItem(
                item_id="ltm-ultra-periodization",
                content="超马训练通常分为基础期、专项期、比赛期和恢复期。",
                category="method",
                tags=["超马", "周期化", "训练计划"],
            ),
            "ultra_volume": SeedMemoryItem(
                item_id="ltm-ultra-volume",
                content="训练量和强度分布需要按周波动控制，关键课次包括长距离、爬升和补给练习。",
                category="discussion",
                tags=["训练量", "强度", "关键课次"],
            ),
            "ultra_recovery": SeedMemoryItem(
                item_id="ltm-ultra-recovery",
                content="恢复期要明显降量，保留少量强度刺激，并监控疲劳与伤病风险。",
                category="insight",
                tags=["恢复", "疲劳", "伤病"],
            ),
        }

    def recall(self, query: str):
        normalized = str(query or "")

        if normalized == PROBLEM_LAYER_3_PARTIAL_TEMPLATE:
            return {
                "references": [self._items["study_circle"].item_id],
                "enhancements": [],
            }

        if normalized == PROBLEM_LAYER_3_LIST_FALLBACK:
            return [
                self._items["list_fallback_a"].to_dict(),
                self._items["list_fallback_b"].to_dict(),
            ]

        if "超马" in normalized or "周期化" in normalized:
            self._ultra_query_hits += 1
            if self._ultra_query_hits == 1:
                # First call comes from Layer 2 composition check — return empty to
                # force Layer 2 miss and escalate to Layer 3.
                return []
            # Second call (and any subsequent calls) come from Layer 3 feasibility
            # check and/or _find_similar_problems_in_ltm.  Return the rich context
            # every time so that all Layer 3 internal recall invocations get usable
            # data regardless of call count.
            return {
                "references": [
                    self._items["ultra_base"].item_id,
                    self._items["ultra_volume"].item_id,
                    self._items["ultra_recovery"].item_id,
                ],
                "enhancements": [
                    {
                        "source": self._items["ultra_base"].item_id,
                        "applicable_to": "设定目标",
                        "text": "先明确目标赛事、周期长度和阶段目标。",
                    },
                    {
                        "source": self._items["ultra_volume"].item_id,
                        "applicable_to": "制定策略",
                        "text": "安排长距离、爬升、补给和恢复周节奏。",
                    },
                ],
            }

        hits: List[Dict[str, Any]] = []
        if "Z世代" in normalized or "Z 世代" in normalized or "心理学" in normalized:
            hits.append(self._items["psych"].to_dict())
        if "数据分析" in normalized or "留存" in normalized:
            hits.append(self._items["data"].to_dict())
        if "健身App" in normalized or "健身" in normalized or "App" in normalized:
            hits.append(self._items["community"].to_dict())
        if "志愿者招募" in normalized:
            hits.append(self._items["volunteer_recruit"].to_dict())
        if "培训复盘" in normalized:
            hits.append(self._items["volunteer_training"].to_dict())
        if "社群激励" in normalized or "青年活动" in normalized:
            hits.append(self._items["volunteer_reward"].to_dict())

        deduped: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in hits:
            item_id = item["id"]
            if item_id not in seen_ids:
                deduped.append(item)
                seen_ids.add(item_id)
        return deduped



LAYER_1_CASE = CaseSpec(
    case_id="bench-layer1-kb-hit-v1",
    title="Seeded benchmark — Layer 1 direct KB hit",
    description="Use the benchmark seed KB to validate the direct-hit execution path.",
    task_type="skill_execution",
    input_payload={
        "problem": "请用运营策略 分解法 给我一个三步方案，包含目标定义、渠道选择、执行计划。"
    },
    expected_outcome_type="text",
    expected_layer=[1],
    tags=["benchmark", "real", "layer1", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_1_GRADER = GraderSpec(
    grader_id="grader-bench-layer1-kb-hit-v1",
    name="Seeded benchmark Layer 1 grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {
            "name": "layer_is_1",
            "type": "exact_match",
            "weight": 0.40,
            "config": {"field": "layer", "expected": 1},
        },
        {
            "name": "has_result",
            "type": "non_empty",
            "weight": 0.35,
            "config": {"field": "result"},
        },
        {
            "name": "confidence_gte_080",
            "type": "threshold",
            "weight": 0.25,
            "config": {"field": "confidence", "min_value": 0.80},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_2_CASE = CaseSpec(
    case_id="bench-layer2-compose-v1",
    title="Seeded benchmark — Layer 2 composition",
    description="Use multiple seeded LTM items to validate the composition path.",
    task_type="skill_composition",
    input_payload={
        "problem": "请基于 Z世代 心理学 数据分析 健身App 留存，给我一个提升方案。"
    },
    expected_outcome_type="text",
    expected_layer=[2],
    tags=["benchmark", "real", "layer2", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_2_GRADER = GraderSpec(
    grader_id="grader-bench-layer2-compose-v1",
    name="Seeded benchmark Layer 2 grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {
            "name": "layer_is_2",
            "type": "exact_match",
            "weight": 0.40,
            "config": {"field": "layer", "expected": 2},
        },
        {
            "name": "has_result",
            "type": "non_empty",
            "weight": 0.35,
            "config": {"field": "result"},
        },
        {
            "name": "confidence_gte_080",
            "type": "threshold",
            "weight": 0.25,
            "config": {"field": "confidence", "min_value": 0.80},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_3_CASE = CaseSpec(
    case_id="bench-layer3-generate-v1",
    title="Seeded benchmark — Layer 3 auto-generation",
    description="Force composition miss first, then validate Layer 3 generation with compact seed context.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我设计一套针对超马跑步运动员的赛季周期化训练计划，包含基础期、专项期、比赛期和恢复期四个阶段。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=["benchmark", "real", "layer3", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_3_GRADER = GraderSpec(
    grader_id="grader-bench-layer3-generate-v1",
    name="Seeded benchmark Layer 3 grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {
            "name": "layer_is_3",
            "type": "exact_match",
            "weight": 0.35,
            "config": {"field": "layer", "expected": 3},
        },
        _l3_skill_name_semantic_dimension(
            "超马跑步 赛季周期化训练计划 四阶段 解决方案"
        ),
        {
            "name": "confidence_gte_070",
            "type": "threshold",
            "weight": 0.20,
            "config": {"field": "confidence", "min_value": 0.70},
        },
        {
            "name": "auto_generated_flag",
            "type": "contains_key",
            "weight": 0.15,
            "config": {"field": "metadata", "key": "layer_3_auto_generated"},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)


LAYER_2_EXTENDED_CASE = CaseSpec(
    case_id="bench-layer2-mixed-support-v1",
    title="Seeded benchmark — Layer 2 multi-source composition",
    description="Validate Layer 2 composition across three seeded LTM sources with divergent tags.",
    task_type="skill_composition",
    input_payload={"problem": PROBLEM_LAYER_2_MIXED_SUPPORT},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=["benchmark", "real", "layer2", "boundary", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_2_EXTENDED_GRADER = GraderSpec(
    grader_id="grader-bench-layer2-mixed-support-v1",
    name="Seeded benchmark Layer 2 extended grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {
            "name": "layer_is_2",
            "type": "exact_match",
            "weight": 0.40,
            "config": {"field": "layer", "expected": 2},
        },
        {
            "name": "has_result",
            "type": "non_empty",
            "weight": 0.35,
            "config": {"field": "result"},
        },
        {
            "name": "confidence_gte_080",
            "type": "threshold",
            "weight": 0.25,
            "config": {"field": "confidence", "min_value": 0.80},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_3_SPARSE_CASE = CaseSpec(
    case_id="bench-layer3-sparse-context-v1",
    title="Seeded benchmark — Layer 3 sparse generation context",
    description="Force Layer 3 generation with only one LTM reference returned as compact dict context.",
    task_type="skill_generation",
    input_payload={"problem": PROBLEM_LAYER_3_PARTIAL_TEMPLATE},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=["benchmark", "real", "layer3", "threshold", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_3_SPARSE_GRADER = GraderSpec(
    grader_id="grader-bench-layer3-sparse-context-v1",
    name="Seeded benchmark Layer 3 sparse context grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {
            "name": "layer_is_3",
            "type": "exact_match",
            "weight": 0.35,
            "config": {"field": "layer", "expected": 3},
        },
        _l3_skill_name_semantic_dimension(
            "校园读书会 长期陪伴与打卡反馈机制 解决方案"
        ),
        {
            "name": "confidence_gte_070",
            "type": "threshold",
            "weight": 0.20,
            "config": {"field": "confidence", "min_value": 0.70},
        },
        {
            "name": "auto_generated_flag",
            "type": "contains_key",
            "weight": 0.15,
            "config": {"field": "metadata", "key": "layer_3_auto_generated"},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)


LAYER_3_LIST_FALLBACK_CASE = CaseSpec(
    case_id="bench-layer3-list-fallback-v1",
    title="Seeded benchmark — Layer 3 list-shaped LTM recall regression guard",
    description="Regression guard validating that Layer 3 generation handles list-shaped recall payloads, not only dict context.",
    task_type="skill_generation",
    input_payload={"problem": PROBLEM_LAYER_3_LIST_FALLBACK},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=["benchmark", "real", "layer3", "regression", "seeded"],
    metadata={"suite": BENCHMARK_SUITE_ID},
)

LAYER_3_LIST_FALLBACK_GRADER = GraderSpec(
    grader_id="grader-bench-layer3-list-fallback-v1",
    name="Seeded benchmark Layer 3 list fallback grader",
    grading_mode="scored",
    pass_threshold=0.60,
    dimensions=[
        {
            "name": "layer_is_3",
            "type": "exact_match",
            "weight": 0.35,
            "config": {"field": "layer", "expected": 3},
        },
        _l3_skill_name_semantic_dimension(
            "列表回退问题 陌生任务设计 解决方案"
        ),
        {
            "name": "confidence_gte_060",
            "type": "threshold",
            "weight": 0.30,
            "config": {"field": "confidence", "min_value": 0.60},
        },
    ],
    metadata={"suite": BENCHMARK_SUITE_ID},
)



def build_seeded_system() -> AdaptiveSkillSystem:

    """Return a fresh benchmark-scoped system instance."""

    return AdaptiveSkillSystem(
        kb_client=SeededBenchmarkKBClient(),
        ltm_client=SeededBenchmarkLTMClient(),
    )


def build_benchmark_jobs() -> List[BatchJob]:
    """Return the canonical benchmark jobs in fixed order."""

    return [
        BatchJob(case=LAYER_1_CASE, grader=LAYER_1_GRADER),
        BatchJob(case=LAYER_2_CASE, grader=LAYER_2_GRADER),
        BatchJob(case=LAYER_2_EXTENDED_CASE, grader=LAYER_2_EXTENDED_GRADER),
        BatchJob(case=LAYER_3_CASE, grader=LAYER_3_GRADER),
        BatchJob(case=LAYER_3_SPARSE_CASE, grader=LAYER_3_SPARSE_GRADER),
        BatchJob(case=LAYER_3_LIST_FALLBACK_CASE, grader=LAYER_3_LIST_FALLBACK_GRADER),
    ]



def run_seeded_real_benchmark(
    *,
    system_version: str = DEFAULT_SYSTEM_VERSION,
    batch_id: str = DEFAULT_BATCH_ID,
) -> BatchResult:
    """Execute the seeded real benchmark suite end-to-end."""

    return run_batch(
        build_benchmark_jobs(),
        build_seeded_system(),
        system_version=system_version,
        batch_id=batch_id,
        metadata={
            "suite": BENCHMARK_SUITE_ID,
            "seed_mode": "in-memory-kb-ltm",
            "note": "Stable real-solver benchmark using isolated benchmark seed data.",
        },
    )


__all__ = [
    "BENCHMARK_SUITE_ID",
    "DEFAULT_BATCH_ID",
    "DEFAULT_SYSTEM_VERSION",
    "LAYER_1_CASE",
    "LAYER_1_GRADER",
    "LAYER_2_CASE",
    "LAYER_2_GRADER",
    "LAYER_2_EXTENDED_CASE",
    "LAYER_2_EXTENDED_GRADER",
    "LAYER_3_CASE",
    "LAYER_3_GRADER",
    "LAYER_3_SPARSE_CASE",
    "LAYER_3_SPARSE_GRADER",
    "LAYER_3_LIST_FALLBACK_CASE",
    "LAYER_3_LIST_FALLBACK_GRADER",
    "build_seeded_system",
    "build_benchmark_jobs",
    "run_seeded_real_benchmark",
]

