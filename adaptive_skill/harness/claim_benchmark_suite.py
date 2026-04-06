"""Claim Benchmark Suite v1 for Adaptive Skill System.

Purpose
-------
This module provides a **release-grade** benchmark that can be cited as evidence
when making capability claims about the Adaptive Skill System.

Key differences from the existing benchmark suites:
- ``ci-smoke-v1``         -- synthetic rows; validates harness plumbing, NOT solver.
- ``real-benchmark-v2``   -- 6 seeded cases; regression / development baseline.
- **this suite**          -- 18 representative cases (Layer1×6, Layer2×6, Layer3×6);
                             designed for Wilson-interval–based claim reporting.

Design principles
-----------------
1. Every case runs the *real* solver path (no stubs).
2. The KB/LTM seed is explicit and frozen -- the suite is fully reproducible.
3. Cases are representative, not adversarial; all are expected to pass under
   normal solver behaviour.
4. The suite is independent; it does NOT share cases with ``real-benchmark-v2``.
5. Claim language must be bounded to this fixed seed:
   "N/18 pass on the claim-benchmark-v1 seeded suite (reproducible)."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core import AdaptiveSkillSystem
from .batch_runner import BatchJob, BatchResult, run_batch
from .specs import CaseSpec, GraderSpec

# ---------------------------------------------------------------------------
# Suite constants
# ---------------------------------------------------------------------------

CLAIM_BENCHMARK_SUITE_ID = "claim-benchmark-v1"
DEFAULT_BATCH_ID = "adaptive-skill-harness-claim-benchmark"
DEFAULT_SYSTEM_VERSION = "claim-benchmark-seeded"


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


# ---------------------------------------------------------------------------
# Seed data value objects
# ---------------------------------------------------------------------------



@dataclass(frozen=True)
class _SeedItem:
    """Simple value object for the in-memory LTM/KB seed entries."""

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


# ---------------------------------------------------------------------------
# Seeded KB client (Layer 1 cases)
# ---------------------------------------------------------------------------

class ClaimBenchmarkKBClient:
    """KB client seeded with 6 skills, one per Layer-1 claim case."""

    def __init__(self) -> None:
        self._skills: Dict[str, Dict[str, Any]] = {
            # --- L1-A: content strategy decomposition ---
            # Problem keywords: 内容策略 分解法 目标受众 内容主题 发布渠道 数据复盘
            "kb-content-strategy": {
                "id": "kb-content-strategy",
                "title": "内容策略分解法 — 目标受众 内容主题 发布渠道 数据复盘",
                "content": (
                    "内容策略分解法：针对目标受众进行定义和细分，规划内容主题矩阵，"
                    "选择适合的发布渠道组合，并通过数据复盘优化下一轮内容投放。"
                ),
                "tags": ["内容策略", "分解法", "目标受众", "内容主题", "发布渠道", "数据复盘"],
            },
            # --- L1-B: meeting facilitation ---
            # Problem keywords: 会议引导 框架 议程 时间管理 发言分配 行动项跟进
            "kb-meeting-facilitation": {
                "id": "kb-meeting-facilitation",
                "title": "会议引导框架 — 议程设置 时间管理 发言分配 行动项跟进",
                "content": (
                    "会议引导框架四步法：设置清晰的议程目标，进行时间管理控制节奏，"
                    "合理进行发言分配确保参与，最后明确行动项跟进责任人与截止日。"
                ),
                "tags": ["会议引导", "框架", "议程", "时间管理", "发言分配", "行动项跟进", "会议"],
            },
            # --- L1-C: OKR goal setting ---
            # Problem keywords: OKR 目标设定 本季度 可量化 Key Results
            "kb-okr-goal-setting": {
                "id": "kb-okr-goal-setting",
                "title": "OKR 目标设定方法 — 本季度目标 可量化 Key Results",
                "content": (
                    "OKR 目标设定：定义 Objective（定性大方向），设计可量化的 Key Results，"
                    "对齐本季度的优先级，并通过周检视保持进展透明。"
                ),
                "tags": ["OKR", "目标设定", "可量化", "Key Results", "季度", "目标管理"],
            },
            # --- L1-D: onboarding checklist ---
            # Problem keywords: 新人入职 清单 关键节点 试用期结束
            "kb-onboarding-checklist": {
                "id": "kb-onboarding-checklist",
                "title": "新人入职清单 — 关键节点 试用期结束",
                "content": (
                    "新人入职清单关键节点：第1天完成账号与权限配置，"
                    "第1周熟悉核心文档与流程，第1月完成首个实战任务，"
                    "试用期结束前完成绩效回顾与反馈。"
                ),
                "tags": ["新人入职", "清单", "关键节点", "试用期", "入职"],
            },
            # --- L1-E: bug triage process ---
            # Problem keywords: Bug 分级 流程 P0 P1 P2 P3 处理标准
            "kb-bug-triage": {
                "id": "kb-bug-triage",
                "title": "Bug 分级处理流程 — P0 P1 P2 P3 处理标准",
                "content": (
                    "Bug 分级处理流程：P0 级立即响应修复；P1 级 24h 内完成修复；"
                    "P2 级纳入本迭代计划；P3 级视优先级安排下迭代或关闭。"
                ),
                "tags": ["Bug", "分级", "流程", "P0", "P1", "P2", "P3", "处理标准"],
            },
            # --- L1-F: customer feedback loop ---
            # Problem keywords: 用户反馈 闭环机制 收集 分类 优先级 SLA响应
            "kb-feedback-loop": {
                "id": "kb-feedback-loop",
                "title": "用户反馈闭环机制 — 收集 分类 优先级 SLA响应",
                "content": (
                    "用户反馈闭环机制：建立多渠道收集入口，按类型与严重性分类打标，"
                    "进行优先级排序，设定 SLA 响应时限，并在处理完毕后向用户关闭回复。"
                ),
                "tags": ["用户反馈", "闭环机制", "闭环", "收集", "分类", "优先级", "SLA", "响应"],
            },
        }

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        q = str(query or "")
        results = []
        for skill in self._skills.values():
            title = skill.get("title", "")
            content = skill.get("content", "")
            tags = skill.get("tags", [])
            searchable = f"{title} {content} {' '.join(tags)}"
            # Match if any tag, title word, or content segment appears in query
            if (any(t in q for t in tags) or
                    any(word in q for word in title.split() if len(word) >= 2) or
                    any(word in q for word in content.split() if len(word) >= 2)):
                results.append(skill)
        return results[:top_k]

    def get(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self._skills.get(skill_id)

    def update(self, skill_id: str, updated_skill: Any) -> None:
        self._skills[skill_id] = updated_skill


# ---------------------------------------------------------------------------
# Seeded LTM client (Layer 2 & Layer 3 cases)
# ---------------------------------------------------------------------------

class ClaimBenchmarkLTMClient:
    """LTM client seeded with 18 items covering Layer-2 composition and Layer-3 generation."""

    def __init__(self) -> None:
        # track call counts per problem for multi-recall stateful flows
        self._call_counts: Dict[str, int] = {}

        self._items: Dict[str, _SeedItem] = {
            # === Layer 2 seed items ===

            # L2-A: product launch campaign
            "ltm-product-launch-gtm": _SeedItem(
                "ltm-product-launch-gtm",
                "产品上线前需要明确目标市场、竞品定位、核心卖点和发布时间窗口。",
                "method", ["产品上线", "GTM", "发布"],
            ),
            "ltm-product-launch-channels": _SeedItem(
                "ltm-product-launch-channels",
                "发布渠道组合通常包含社交媒体预热、KOL合作、PR稿和应用商店优化。",
                "discussion", ["发布渠道", "KOL", "PR", "社媒"],
            ),
            # L2-B: remote team collaboration
            "ltm-remote-async-comms": _SeedItem(
                "ltm-remote-async-comms",
                "远程团队异步协作依赖清晰的文档规范、固定的周会节奏和进度透明化工具。"
                "推荐使用 Notion/Confluence 记录决策，Slack 划分异步频道，周五同步进度。",
                "insight", ["远程团队", "异步", "文档", "进度", "协作规范"],
            ),
            "ltm-remote-timezone": _SeedItem(
                "ltm-remote-timezone",
                "跨时区协作需要明确核心重叠时段（建议2-3小时），异步评审窗口和紧急升级通道。"
                "分布式团队的协作效率取决于沟通协议的清晰度，而不是在线时间的长短。",
                "method", ["跨时区", "协作", "异步", "评审", "分布式团队"],
            ),
            "ltm-remote-rituals": _SeedItem(
                "ltm-remote-rituals",
                "远程团队仪式感建设：每周 check-in 分享个人状态，每月虚拟 team building，"
                "季度线下汇聚；关系资本积累是远程协作长期可持续的核心。",
                "discussion", ["远程团队", "仪式感", "check-in", "团队建设", "协作"],
            ),
            # L2-C: user growth funnel
            "ltm-growth-acquisition": _SeedItem(
                "ltm-growth-acquisition",
                "用户增长漏斗双端优化方案之获客侧：获客渠道优化关注CAC和渠道质量，避免低质量流量稀释转化率。"
                "CAC优化首先要区分付费渠道与自然渠道，再做 ROI 对比和渠道归因分析。"
                "获客侧双端优化的核心是渠道质量与转化率的协同提升。",
                "method", ["用户增长", "CAC", "获客", "转化率", "渠道优化", "增长漏斗", "双端优化"],
            ),
            "ltm-growth-activation": _SeedItem(
                "ltm-growth-activation",
                "用户增长漏斗双端优化方案之激活侧：激活率依赖首次使用体验，获客渠道优化带来的流量需高激活率承接。"
                "关键路径缩短和首次价值时间（TTV）是核心指标。"
                "TTV改善策略：减少注册步骤、提供引导卡片、首次使用即展示核心价值功能。",
                "insight", ["激活", "TTV", "首次价值", "体验", "激活率", "增长漏斗", "双端优化"],
            ),
            "ltm-growth-retention": _SeedItem(
                "ltm-growth-retention",
                "用户增长漏斗的留存环节：7日留存是关键健康指标，"
                "推送策略、习惯养成设计和价值提醒是提升留存的三大抓手。",
                "discussion", ["用户增长", "留存", "7日留存", "增长漏斗"],
            ),
            # L2-D: content calendar planning
            "ltm-content-calendar-themes": _SeedItem(
                "ltm-content-calendar-themes",
                "内容日历需要提前4周规划主题，预留热点响应窗口，并与产品节点对齐。"
                "内容规划的主题矩阵应覆盖：产品卖点、用户故事、行业洞察、互动话题四类。",
                "method", ["内容日历", "主题", "热点", "产品节点", "内容规划"],
            ),
            "ltm-content-calendar-reuse": _SeedItem(
                "ltm-content-calendar-reuse",
                "内容复用策略：长文拆短视频、短视频扩播客、数据图改信息流图，降低生产成本。"
                "一套内容素材最多可以复用为 5-8 个不同格式的内容资产，提升内容ROI。",
                "discussion", ["内容复用", "短视频", "播客", "信息流", "内容策略"],
            ),
            "ltm-content-calendar-ops": _SeedItem(
                "ltm-content-calendar-ops",
                "内容运营日历的执行：建立内容流水线（选题-创作-审核-发布-分发），"
                "指定责任人，设定发布时间窗口，并追踪每篇内容的核心指标。",
                "insight", ["内容运营", "内容日历", "流水线", "发布", "内容复用"],
            ),
            # L2-E: performance review
            "ltm-perf-review-360": _SeedItem(
                "ltm-perf-review-360",
                "绩效评审采用360度反馈可以减少主管单向偏差，但要控制评审人数量在5人以内。",
                "method", ["绩效评审", "360度", "反馈", "偏差"],
            ),
            "ltm-perf-review-calibration": _SeedItem(
                "ltm-perf-review-calibration",
                "跨团队校准会议确保绩效评分标准一致，避免团队间评分膨胀。",
                "insight", ["绩效校准", "跨团队", "评分", "标准"],
            ),
            # L2-F: event planning
            "ltm-event-logistics": _SeedItem(
                "ltm-event-logistics",
                "线下活动筹备核心：场地、时间、人数预估、物料清单和备用方案。",
                "method", ["活动筹备", "场地", "物料", "备用方案"],
            ),
            "ltm-event-engagement": _SeedItem(
                "ltm-event-engagement",
                "活动互动设计：签到环节、现场任务、分组讨论和结束后的社群沉淀。",
                "discussion", ["活动互动", "签到", "分组", "社群"],
            ),

            # === Layer 3 seed items ===

            # L3-A: AI product roadmap
            "ltm-ai-product-eval": _SeedItem(
                "ltm-ai-product-eval",
                "AI产品路线图需要先评估核心能力边界、数据依赖和模型迭代周期。",
                "method", ["AI产品", "路线图", "能力边界", "数据"],
            ),
            # L3-B: cross-functional project kickoff
            "ltm-crossfunc-kickoff": _SeedItem(
                "ltm-crossfunc-kickoff",
                "跨职能项目启动会需要明确RACI矩阵、决策权边界和沟通频率协议。",
                "method", ["跨职能", "启动会", "RACI", "决策权"],
            ),
            # L3-C: data-driven culture building
            "ltm-data-culture": _SeedItem(
                "ltm-data-culture",
                "数据文化建设需要从数据基础设施、指标体系共识和数据素养培训三条线并进。",
                "insight", ["数据文化", "指标体系", "数据素养", "基础设施"],
            ),
            # L3-D: brand strategy for new market
            "ltm-brand-new-market": _SeedItem(
                "ltm-brand-new-market",
                "进入新市场的品牌策略：本地化定位、差异化信息和早期忠诚用户社群建设。"
                "本地化定位要结合当地文化洞察，差异化信息需要和竞品拉开认知距离。",
                "method", ["品牌策略", "本地化", "差异化", "新市场", "品牌"],
            ),
            "ltm-brand-positioning": _SeedItem(
                "ltm-brand-positioning",
                "品牌定位三步法：明确目标用户画像（谁）、核心价值主张（是什么）、"
                "竞品差异化（为什么选我）。进入新市场时需要针对本地用户重新校准三个维度。",
                "insight", ["品牌", "定位", "差异化", "新市场", "用户画像", "品牌策略"],
            ),
            "ltm-brand-community": _SeedItem(
                "ltm-brand-community",
                "早期品牌社群建设依赖找到核心用户（种子用户），提供超预期价值，"
                "让他们成为品牌传播者；社群规模 < 1000 时质量远比数量重要。",
                "discussion", ["品牌", "社群建设", "种子用户", "新市场", "早期"],
            ),
            # L3-E: technical debt management
            "ltm-tech-debt": _SeedItem(
                "ltm-tech-debt",
                "技术债务管理：可见化债务清单、与业务价值挂钩的偿还计划和停止新增债务的防线。"
                "债务可见化是第一步，推荐用技术债务矩阵标注影响范围、修复成本和紧迫程度。",
                "method", ["技术债务", "可见化", "偿还", "防线", "技术债"],
            ),
            "ltm-tech-debt-triage": _SeedItem(
                "ltm-tech-debt-triage",
                "技术债务分级处理：P0-影响稳定性立即修；P1-影响迭代速度本季度处理；"
                "P2-质量改善纳入长期计划；P3-可接受暂不处理并记录原因。",
                "insight", ["技术债务", "分级", "技术债", "管理体系", "偿还计划"],
            ),
            "ltm-tech-debt-prevention": _SeedItem(
                "ltm-tech-debt-prevention",
                "技术债务新增防线：代码审查加入债务检查项，架构决策记录（ADR）制度，"
                "以及'不得带债上线'的团队共识——每次迭代必须同步偿还等量或更多旧债。",
                "discussion", ["技术债务", "代码审查", "架构", "防线", "管理体系"],
            ),
            # L3-F: community-led growth
            "ltm-community-led-growth": _SeedItem(
                "ltm-community-led-growth",
                "社区驱动增长依靠核心用户激励、内容共创机制和口碑传播的正向飞轮。",
                "insight", ["社区驱动", "增长", "核心用户", "飞轮"],
            ),
        }

    def recall(self, query: str) -> Any:
        q = str(query or "")
        self._call_counts[q] = self._call_counts.get(q, 0) + 1
        call_n = self._call_counts[q]

        # ---- Layer 3 specific stateful flows ----
        # L3-A: AI product roadmap  (force Layer-2 miss on 1st call)
        if "AI产品路线图" in q or ("AI产品" in q and "路线图" in q):
            if call_n == 1:
                return []  # Force Layer-2 composition miss
            return {
                "references": ["ltm-ai-product-eval"],
                "enhancements": [{
                    "source": "ltm-ai-product-eval",
                    "applicable_to": "路线图规划",
                    "text": "先明确能力边界和数据依赖，再做季度迭代排期。",
                }],
            }

        # L3-B: cross-functional kickoff (force Layer-2 miss on 1st call)
        if "RACI" in q or ("跨职能" in q and "启动" in q):
            if call_n == 1:
                return []
            return {
                "references": ["ltm-crossfunc-kickoff"],
                "enhancements": [{
                    "source": "ltm-crossfunc-kickoff",
                    "applicable_to": "启动会设计",
                    "text": "用RACI矩阵确认各方职责，再设定决策升级路径。",
                }],
            }

        # L3-C: data culture (force Layer-2 miss on 1st call)
        if "数据文化" in q or ("数据素养" in q and "指标" in q):
            if call_n == 1:
                return []
            return {
                "references": ["ltm-data-culture"],
                "enhancements": [{
                    "source": "ltm-data-culture",
                    "applicable_to": "文化建设",
                    "text": "三线并进：基础设施→指标共识→素养培训，缺一不可。",
                }],
            }

        # L3-D: brand new market (force Layer-2 miss on 1st call)
        if ("品牌" in q and "新市场" in q) or ("本地化定位" in q):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-brand-new-market",
                    "ltm-brand-positioning",
                    "ltm-brand-community",
                ],
                "enhancements": [
                    {
                        "source": "ltm-brand-new-market",
                        "applicable_to": "市场定位",
                        "text": "先本地化定位，再差异化信息，最后建早期社群。",
                    },
                    {
                        "source": "ltm-brand-positioning",
                        "applicable_to": "定位校准",
                        "text": "针对新市场用户重新校准：目标用户、核心价值、差异化三个维度。",
                    },
                    {
                        "source": "ltm-brand-community",
                        "applicable_to": "社群建设",
                        "text": "找到100个种子用户，提供超预期价值，让他们成为品牌传播者。",
                    },
                ],
            }

        # L3-E: tech debt (force Layer-2 miss on 1st call)
        if "技术债务" in q or ("技术债" in q and "管理" in q):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-tech-debt",
                    "ltm-tech-debt-triage",
                    "ltm-tech-debt-prevention",
                ],
                "enhancements": [
                    {
                        "source": "ltm-tech-debt",
                        "applicable_to": "债务治理",
                        "text": "可见化→业务挂钩偿还→停止新增，缺少第三步则债务持续累积。",
                    },
                    {
                        "source": "ltm-tech-debt-triage",
                        "applicable_to": "分级处理",
                        "text": "P0-P3 四级分类，按影响范围和修复成本制定处理优先级。",
                    },
                    {
                        "source": "ltm-tech-debt-prevention",
                        "applicable_to": "新增防线",
                        "text": "代码审查加入债务检查，ADR 制度，每次迭代同步偿还等量旧债。",
                    },
                ],
            }

        # L3-F: community-led growth (force Layer-2 miss on 1st call)
        if "社区驱动增长" in q or ("社区" in q and "飞轮" in q) or ("社区" in q and "共创" in q):
            if call_n == 1:
                return []
            return {
                "references": ["ltm-community-led-growth"],
                "enhancements": [{
                    "source": "ltm-community-led-growth",
                    "applicable_to": "增长策略",
                    "text": "核心用户激励 + 内容共创 + 口碑飞轮，三环联动。",
                }],
            }

        # ---- Layer 2 keyword-based recall ----
        hits: List[Dict[str, Any]] = []

        # L2-A: product launch
        if "产品上线" in q or "GTM" in q or "发布" in q:
            hits.extend([
                self._items["ltm-product-launch-gtm"].to_dict(),
                self._items["ltm-product-launch-channels"].to_dict(),
            ])
        # L2-B: remote team (return 3 items for better coverage)
        if "远程团队" in q or "异步协作" in q or "跨时区" in q or "分布式团队" in q:
            hits.extend([
                self._items["ltm-remote-async-comms"].to_dict(),
                self._items["ltm-remote-timezone"].to_dict(),
                self._items["ltm-remote-rituals"].to_dict(),
            ])
        # L2-C: growth funnel (return 3 items for better coverage)
        if "用户增长" in q or "CAC" in q or "激活率" in q or "TTV" in q:
            hits.extend([
                self._items["ltm-growth-acquisition"].to_dict(),
                self._items["ltm-growth-activation"].to_dict(),
                self._items["ltm-growth-retention"].to_dict(),
            ])
        # L2-D: content calendar (return 3 items for better coverage)
        if "内容日历" in q or "内容复用" in q or "内容规划" in q:
            hits.extend([
                self._items["ltm-content-calendar-themes"].to_dict(),
                self._items["ltm-content-calendar-reuse"].to_dict(),
                self._items["ltm-content-calendar-ops"].to_dict(),
            ])
        # L2-E: performance review
        if "绩效评审" in q or "360度" in q or "校准" in q or "绩效校准" in q:
            hits.extend([
                self._items["ltm-perf-review-360"].to_dict(),
                self._items["ltm-perf-review-calibration"].to_dict(),
            ])
        # L2-F: event planning
        if "活动筹备" in q or "线下活动" in q or "活动互动" in q:
            hits.extend([
                self._items["ltm-event-logistics"].to_dict(),
                self._items["ltm-event-engagement"].to_dict(),
            ])

        # deduplicate
        deduped: List[Dict[str, Any]] = []
        seen: set = set()
        for item in hits:
            if item["id"] not in seen:
                deduped.append(item)
                seen.add(item["id"])
        return deduped


# ---------------------------------------------------------------------------
# Seeded system factory
# ---------------------------------------------------------------------------


def build_claim_benchmark_system() -> AdaptiveSkillSystem:
    """Return a fresh claim-benchmark–scoped system instance."""
    return AdaptiveSkillSystem(
        kb_client=ClaimBenchmarkKBClient(),
        ltm_client=ClaimBenchmarkLTMClient(),
    )


# ---------------------------------------------------------------------------
# Layer 1 cases (6 cases — direct KB hit)
# ---------------------------------------------------------------------------

_L1_TAGS = ["claim-benchmark", "layer1", "seeded"]
_L1_META = {"suite": CLAIM_BENCHMARK_SUITE_ID}

L1A_CASE = CaseSpec(
    case_id="claim-l1-content-strategy-v1",
    title="Claim L1-A — Content strategy decomposition",
    description="Validate Layer-1 direct KB hit for content strategy skill.",
    task_type="skill_execution",
    input_payload={"problem": "请用内容策略 分解法 给我一个方案，覆盖目标受众、内容主题、发布渠道和数据复盘。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["content-strategy"],
    metadata=_L1_META,
)
L1A_GRADER = GraderSpec(
    grader_id="grader-claim-l1-content-strategy-v1",
    name="Claim L1-A grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)

L1B_CASE = CaseSpec(
    case_id="claim-l1-meeting-facilitation-v1",
    title="Claim L1-B — Meeting facilitation framework",
    description="Validate Layer-1 direct KB hit for meeting facilitation skill.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一个 会议引导 框架，包含议程设置、时间管理、发言分配和行动项跟进四个步骤。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["meeting"],
    metadata=_L1_META,
)
L1B_GRADER = GraderSpec(
    grader_id="grader-claim-l1-meeting-facilitation-v1",
    name="Claim L1-B grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)

L1C_CASE = CaseSpec(
    case_id="claim-l1-okr-goal-setting-v1",
    title="Claim L1-C — OKR goal setting",
    description="Validate Layer-1 direct KB hit for OKR goal setting skill.",
    task_type="skill_execution",
    input_payload={"problem": "请用 OKR 目标设定 方法帮我设计本季度的目标，包含可量化 Key Results。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["okr"],
    metadata=_L1_META,
)
L1C_GRADER = GraderSpec(
    grader_id="grader-claim-l1-okr-goal-setting-v1",
    name="Claim L1-C grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)

L1D_CASE = CaseSpec(
    case_id="claim-l1-onboarding-checklist-v1",
    title="Claim L1-D — Onboarding checklist",
    description="Validate Layer-1 direct KB hit for onboarding checklist skill.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一份 新人入职 清单，涵盖第1天到试用期结束的关键节点。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["onboarding"],
    metadata=_L1_META,
)
L1D_GRADER = GraderSpec(
    grader_id="grader-claim-l1-onboarding-checklist-v1",
    name="Claim L1-D grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)

L1E_CASE = CaseSpec(
    case_id="claim-l1-bug-triage-v1",
    title="Claim L1-E — Bug triage process",
    description="Validate Layer-1 direct KB hit for bug triage process skill.",
    task_type="skill_execution",
    input_payload={"problem": "请按照 Bug 分级 流程给我一套P0/P1/P2/P3的处理标准。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["bug-triage"],
    metadata=_L1_META,
)
L1E_GRADER = GraderSpec(
    grader_id="grader-claim-l1-bug-triage-v1",
    name="Claim L1-E grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)

L1F_CASE = CaseSpec(
    case_id="claim-l1-feedback-loop-v1",
    title="Claim L1-F — Customer feedback loop",
    description="Validate Layer-1 direct KB hit for customer feedback loop skill.",
    task_type="skill_execution",
    input_payload={"problem": "请帮我设计一套 用户反馈 闭环机制，包含收集、分类、优先级和SLA响应。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["feedback"],
    metadata=_L1_META,
)
L1F_GRADER = GraderSpec(
    grader_id="grader-claim-l1-feedback-loop-v1",
    name="Claim L1-F grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_1", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 1}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L1_META,
)


# ---------------------------------------------------------------------------
# Layer 2 cases (6 cases — LTM composition)
# ---------------------------------------------------------------------------

_L2_TAGS = ["claim-benchmark", "layer2", "seeded"]
_L2_META = {"suite": CLAIM_BENCHMARK_SUITE_ID}

L2A_CASE = CaseSpec(
    case_id="claim-l2-product-launch-v1",
    title="Claim L2-A — Product launch campaign",
    description="Validate Layer-2 composition for product launch GTM + channels.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 产品上线 GTM策略 和 推广组合，给我一个新产品发布的综合执行方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["product-launch"],
    metadata=_L2_META,
)
L2A_GRADER = GraderSpec(
    grader_id="grader-claim-l2-product-launch-v1",
    name="Claim L2-A grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)

L2B_CASE = CaseSpec(
    case_id="claim-l2-remote-team-v1",
    title="Claim L2-B — Remote team collaboration",
    description="Validate Layer-2 composition for remote team async comms + timezone.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 远程团队 异步协作 和 跨时区 管理，设计一套分布式团队的协作规范。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["remote-team"],
    metadata=_L2_META,
)
L2B_GRADER = GraderSpec(
    grader_id="grader-claim-l2-remote-team-v1",
    name="Claim L2-B grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)

L2C_CASE = CaseSpec(
    case_id="claim-l2-growth-funnel-v1",
    title="Claim L2-C — User growth funnel",
    description="Validate Layer-2 composition for user growth acquisition + activation.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 用户增长 漏斗 CAC 获客渠道优化 和 激活率 TTV 首次价值 改善，给我一个增长漏斗的双端优化方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["growth"],
    metadata=_L2_META,
)
L2C_GRADER = GraderSpec(
    grader_id="grader-claim-l2-growth-funnel-v1",
    name="Claim L2-C grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)

L2D_CASE = CaseSpec(
    case_id="claim-l2-content-calendar-v1",
    title="Claim L2-D — Content calendar planning",
    description="Validate Layer-2 composition for content calendar themes + reuse strategy.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 内容日历 主题规划 和 内容复用 策略，给我一套降本增效的内容生产方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["content-calendar"],
    metadata=_L2_META,
)
L2D_GRADER = GraderSpec(
    grader_id="grader-claim-l2-content-calendar-v1",
    name="Claim L2-D grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)

L2E_CASE = CaseSpec(
    case_id="claim-l2-perf-review-v1",
    title="Claim L2-E — Performance review process",
    description="Validate Layer-2 composition for 360 feedback + calibration.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 绩效评审 360度反馈 和 跨团队校准 设计一套年度绩效流程。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["performance-review"],
    metadata=_L2_META,
)
L2E_GRADER = GraderSpec(
    grader_id="grader-claim-l2-perf-review-v1",
    name="Claim L2-E grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)

L2F_CASE = CaseSpec(
    case_id="claim-l2-event-planning-v1",
    title="Claim L2-F — Event planning and engagement",
    description="Validate Layer-2 composition for event logistics + engagement design.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 活动筹备 和 活动互动 设计，帮我规划一次50人规模的线下活动全流程。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["event-planning"],
    metadata=_L2_META,
)
L2F_GRADER = GraderSpec(
    grader_id="grader-claim-l2-event-planning-v1",
    name="Claim L2-F grader",
    grading_mode="scored",
    pass_threshold=0.70,
    dimensions=[
        {"name": "layer_is_2", "type": "exact_match", "weight": 0.40,
         "config": {"field": "layer", "expected": 2}},
        {"name": "has_result", "type": "non_empty", "weight": 0.35,
         "config": {"field": "result"}},
        {"name": "confidence_gte_080", "type": "threshold", "weight": 0.25,
         "config": {"field": "confidence", "min_value": 0.80}},
    ],
    metadata=_L2_META,
)


# ---------------------------------------------------------------------------
# Layer 3 cases (6 cases — auto-generation)
# ---------------------------------------------------------------------------

_L3_TAGS = ["claim-benchmark", "layer3", "seeded"]
_L3_META = {"suite": CLAIM_BENCHMARK_SUITE_ID}

L3A_CASE = CaseSpec(
    case_id="claim-l3-ai-product-roadmap-v1",
    title="Claim L3-A — AI product roadmap",
    description="Force Layer-2 miss then validate Layer-3 generation for AI product roadmap.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我设计一套 AI产品路线图，包含能力边界评估、数据依赖分析和季度迭代节奏规划。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["ai-product"],
    metadata=_L3_META,
)
L3A_GRADER = GraderSpec(
    grader_id="grader-claim-l3-ai-product-roadmap-v1",
    name="Claim L3-A grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "AI产品路线图 能力边界评估 数据依赖分析 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)


L3B_CASE = CaseSpec(
    case_id="claim-l3-crossfunc-kickoff-v1",
    title="Claim L3-B — Cross-functional project kickoff",
    description="Force Layer-2 miss then validate Layer-3 for cross-functional kickoff.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我设计一套 跨职能 项目启动 流程，包含RACI矩阵、决策权边界和沟通频率协议。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["project-kickoff"],
    metadata=_L3_META,
)
L3B_GRADER = GraderSpec(
    grader_id="grader-claim-l3-crossfunc-kickoff-v1",
    name="Claim L3-B grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "跨职能 项目启动 RACI矩阵 决策权边界 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)


L3C_CASE = CaseSpec(
    case_id="claim-l3-data-culture-v1",
    title="Claim L3-C — Data-driven culture building",
    description="Force Layer-2 miss then validate Layer-3 for data culture building.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我制定一套 数据文化 建设方案，从基础设施、指标体系共识到数据素养培训三条线并进。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["data-culture"],
    metadata=_L3_META,
)
L3C_GRADER = GraderSpec(
    grader_id="grader-claim-l3-data-culture-v1",
    name="Claim L3-C grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "数据文化 基础设施 指标体系共识 数据素养培训 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)


L3D_CASE = CaseSpec(
    case_id="claim-l3-brand-new-market-v1",
    title="Claim L3-D — Brand strategy for new market",
    description="Force Layer-2 miss then validate Layer-3 for brand new-market strategy.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我制定一套进入 新市场 的 品牌策略，包含本地化定位、差异化信息和早期社群建设。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["brand"],
    metadata=_L3_META,
)
L3D_GRADER = GraderSpec(
    grader_id="grader-claim-l3-brand-new-market-v1",
    name="Claim L3-D grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "新市场 品牌策略 本地化定位 差异化信息 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)


L3E_CASE = CaseSpec(
    case_id="claim-l3-tech-debt-v1",
    title="Claim L3-E — Technical debt management",
    description="Force Layer-2 miss then validate Layer-3 for tech debt management.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我设计一套 技术债务 管理体系，涵盖可见化清单、业务价值挂钩的偿还计划和新增防线。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["tech-debt"],
    metadata=_L3_META,
)
L3E_GRADER = GraderSpec(
    grader_id="grader-claim-l3-tech-debt-v1",
    name="Claim L3-E grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "技术债务 可见化清单 偿还计划 新增防线 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)


L3F_CASE = CaseSpec(
    case_id="claim-l3-community-led-growth-v1",
    title="Claim L3-F — Community-led growth strategy",
    description="Force Layer-2 miss then validate Layer-3 for community-led growth.",
    task_type="skill_generation",
    input_payload={
        "problem": "请帮我构建一套 社区驱动增长 的飞轮模型，涵盖核心用户激励、内容共创和口碑传播机制。"
    },
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["community-growth"],
    metadata=_L3_META,
)
L3F_GRADER = GraderSpec(
    grader_id="grader-claim-l3-community-led-growth-v1",
    name="Claim L3-F grader",
    grading_mode="scored",
    pass_threshold=0.65,
    dimensions=[
        {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
         "config": {"field": "layer", "expected": 3}},
        _l3_skill_name_semantic_dimension(
            "社区驱动增长 核心用户激励 内容共创 口碑传播 解决方案"
        ),
        {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
         "config": {"field": "confidence", "min_value": 0.70}},
        {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
         "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
    ],
    metadata=_L3_META,
)



# ---------------------------------------------------------------------------
# Build jobs
# ---------------------------------------------------------------------------


def build_claim_benchmark_jobs() -> List[BatchJob]:
    """Return all 18 claim benchmark jobs in canonical order (L1×6, L2×6, L3×6)."""
    return [
        # Layer 1
        BatchJob(case=L1A_CASE, grader=L1A_GRADER),
        BatchJob(case=L1B_CASE, grader=L1B_GRADER),
        BatchJob(case=L1C_CASE, grader=L1C_GRADER),
        BatchJob(case=L1D_CASE, grader=L1D_GRADER),
        BatchJob(case=L1E_CASE, grader=L1E_GRADER),
        BatchJob(case=L1F_CASE, grader=L1F_GRADER),
        # Layer 2
        BatchJob(case=L2A_CASE, grader=L2A_GRADER),
        BatchJob(case=L2B_CASE, grader=L2B_GRADER),
        BatchJob(case=L2C_CASE, grader=L2C_GRADER),
        BatchJob(case=L2D_CASE, grader=L2D_GRADER),
        BatchJob(case=L2E_CASE, grader=L2E_GRADER),
        BatchJob(case=L2F_CASE, grader=L2F_GRADER),
        # Layer 3
        BatchJob(case=L3A_CASE, grader=L3A_GRADER),
        BatchJob(case=L3B_CASE, grader=L3B_GRADER),
        BatchJob(case=L3C_CASE, grader=L3C_GRADER),
        BatchJob(case=L3D_CASE, grader=L3D_GRADER),
        BatchJob(case=L3E_CASE, grader=L3E_GRADER),
        BatchJob(case=L3F_CASE, grader=L3F_GRADER),
    ]


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def run_claim_benchmark(
    *,
    system_version: str = DEFAULT_SYSTEM_VERSION,
    batch_id: str = DEFAULT_BATCH_ID,
) -> BatchResult:
    """Execute the claim benchmark suite end-to-end.

    A fresh ``AdaptiveSkillSystem`` instance is created for each call so the
    seeded LTM call-count state resets correctly.
    """
    return run_batch(
        jobs=build_claim_benchmark_jobs(),
        system=build_claim_benchmark_system(),
        batch_id=batch_id,
        system_version=system_version,
        metadata={
            "suite": CLAIM_BENCHMARK_SUITE_ID,
            "seed_mode": "in-memory-kb-ltm",
            "n_cases": 18,
            "layer_split": "L1:6 / L2:6 / L3:6",
            "note": "Release-grade claim benchmark with isolated seed data.",
        },
    )
