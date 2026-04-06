"""Claim Benchmark Suite v2 for Adaptive Skill System.

Purpose
-------
Expands the release-grade benchmark evidence base from 18 to 36 cases.

Key differences from claim-benchmark-v1:
- 36 cases: Layer1×12, Layer2×12, Layer3×12
- Three difficulty tiers per layer: easy (4), medium (4), hard (4)
- Covers new task domains not in v1:
  * L1: hiring, crisis-comms, pricing, A/B-test, API-design, knowledge-mgmt
  * L2: competitive-analysis, supply-chain, customer-success, investor-deck, ml-ops, dev-sprint
  * L3: org-design, regulatory-strategy, m&a-integration, ecosystem-partnerships,
         ai-safety-review, platform-architecture
- Independent seed data (no overlap with v1 KB/LTM items)
- Backward-compatible: inherits ClaimBenchmarkKBClient / ClaimBenchmarkLTMClient interfaces

Difficulty tier definitions:
  easy   — single-domain, well-defined goal, high KB/LTM recall signal
  medium — requires combining 2-3 concepts, moderate ambiguity
  hard   — cross-domain synthesis, requires multi-step reasoning, lower signal
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

CLAIM_BENCHMARK_V2_SUITE_ID = "claim-benchmark-v2"
DEFAULT_BATCH_ID_V2 = "adaptive-skill-harness-claim-benchmark-v2"
DEFAULT_SYSTEM_VERSION_V2 = "claim-benchmark-v2-seeded"


def _l3_semantic_dim(reference: str) -> Dict[str, Any]:
    """Build a semantic similarity dimension for L3 generated skill names."""
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
    """Simple value object for in-memory LTM/KB seed entries."""

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
# Seeded KB client (Layer 1 — 12 skills across 3 difficulty tiers)
# ---------------------------------------------------------------------------


class ClaimBenchmarkV2KBClient:
    """KB client seeded with 12 skills covering new domains, difficulty-stratified."""

    def __init__(self) -> None:
        self._skills: Dict[str, Dict[str, Any]] = {

            # ── EASY tier (L1-easy-A to L1-easy-D) ──────────────────────────

            # L1-easy-A: hiring pipeline
            "kb-hiring-pipeline": {
                "id": "kb-hiring-pipeline",
                "title": "招聘流程设计 — 岗位定义 简历筛选 面试轮次 Offer决策",
                "content": (
                    "招聘流程四阶段：明确岗位画像与评分标准，建立简历筛选评分卡，"
                    "设计面试轮次（HR初筛→技术面→终面），最终依据综合评分做Offer决策。"
                ),
                "tags": ["招聘", "面试", "岗位", "简历筛选", "Offer", "招聘流程"],
            },

            # L1-easy-B: crisis communication
            "kb-crisis-comms": {
                "id": "kb-crisis-comms",
                "title": "危机沟通框架 — 第一时间响应 信息透明 责任声明 后续跟进",
                "content": (
                    "危机沟通四步法：第一时间发布简短事实性声明，承认已知影响，"
                    "承诺透明更新节奏，48小时内出完整调查结果与补救措施。"
                ),
                "tags": ["危机沟通", "公关", "声明", "透明", "响应", "危机管理"],
            },

            # L1-easy-C: pricing strategy (basic)
            "kb-pricing-basic": {
                "id": "kb-pricing-basic",
                "title": "定价策略基础 — 成本加成 竞品对标 价值定价",
                "content": (
                    "三种基础定价逻辑：成本加成（成本+目标毛利率），竞品对标（市场锚点±差异化溢价），"
                    "价值定价（用户愿意支付的最高价）。B2B产品通常以价值定价为主。"
                ),
                "tags": ["定价", "定价策略", "成本加成", "竞品对标", "价值定价", "毛利率"],
            },

            # L1-easy-D: A/B test setup
            "kb-ab-test-setup": {
                "id": "kb-ab-test-setup",
                "title": "A/B 测试设计 — 假设 指标 样本量 显著性",
                "content": (
                    "A/B 测试四要素：明确假设（改变X能提升Y），选定核心指标，"
                    "用功效分析确定最小样本量，设定显著性水平α=0.05并避免过早停止测试。"
                ),
                "tags": ["A/B测试", "假设检验", "样本量", "显著性", "功效分析", "统计"],
            },

            # ── MEDIUM tier (L1-medium-A to L1-medium-D) ────────────────────

            # L1-medium-A: API design principles
            "kb-api-design": {
                "id": "kb-api-design",
                "title": "API 设计规范 — RESTful 命名 版本控制 错误码 文档",
                "content": (
                    "API 设计关键规范：使用名词复数资源路径，HTTP 方法语义准确，"
                    "版本号放 URL 前缀（/v1/）或 Header，统一错误码结构（code/message/detail），"
                    "强制输出 OpenAPI 文档并用 Changelog 管理变更。"
                ),
                "tags": ["API设计", "RESTful", "版本控制", "错误码", "OpenAPI", "接口"],
            },

            # L1-medium-B: knowledge management
            "kb-knowledge-mgmt": {
                "id": "kb-knowledge-mgmt",
                "title": "知识管理体系 — 捕获 整理 检索 传播 更新",
                "content": (
                    "知识管理五环：捕获（决策记录/会议纪要/复盘），整理（统一入口+分类标签），"
                    "检索（全文搜索+知识图谱），传播（内部分享会+异步阅读），更新（定期 review + 过期归档）。"
                ),
                "tags": ["知识管理", "知识库", "文档", "捕获", "检索", "传播"],
            },

            # L1-medium-C: sprint retrospective
            "kb-sprint-retro": {
                "id": "kb-sprint-retro",
                "title": "Sprint 复盘框架 — 做得好 可改进 行动项 跟踪",
                "content": (
                    "Sprint 复盘标准流程：热身破冰（5min），收集贴纸（做得好/可改进/行动项），"
                    "分组聚类投票，提炼3条高优先级行动项，指定负责人与完成时间，下次 retro 开始时 review。"
                ),
                "tags": ["Sprint复盘", "复盘", "迭代", "敏捷", "行动项", "持续改进"],
            },

            # L1-medium-D: stakeholder map
            "kb-stakeholder-map": {
                "id": "kb-stakeholder-map",
                "title": "干系人 分析 — 识别相关方 影响力 关注度分类 制定沟通策略",
                "content": (
                    "干系人分析四步：识别相关方，按影响力×关注度做关注度分类并画2×2矩阵，"
                    "再为不同象限制定沟通策略，尤其针对高影响高关注方建立密切沟通节奏。"
                ),
                "tags": ["干系人", "干系人分析", "识别相关方", "制定沟通策略", "影响力", "关注度分类", "关注度", "关系管理", "项目管理"],
            },

            # ── HARD tier (L1-hard-A to L1-hard-D) ──────────────────────────

            # L1-hard-A: pricing strategy (complex multi-segment)
            "kb-pricing-advanced": {
                "id": "kb-pricing-advanced",
                "title": "高级定价策略 — 分层定价 动态定价 价格歧视 捆绑销售",
                "content": (
                    "高级定价策略矩阵：用户分层定价（Freemium/Pro/Enterprise）对应价值台阶，"
                    "动态定价（时间/库存敏感型产品），价格歧视（地区/场景差异化定价），"
                    "捆绑销售提升 ARPU；需结合 LTV 模型验证定价可持续性。"
                ),
                "tags": ["定价策略", "分层定价", "动态定价", "捆绑销售", "Freemium", "ARPU", "高级定价"],
            },

            # L1-hard-B: ML model deployment checklist
            "kb-ml-deploy-checklist": {
                "id": "kb-ml-deploy-checklist",
                "title": "ML 模型上线清单 — 数据校验 性能基线 监控 回滚",
                "content": (
                    "ML 模型上线前检查清单：数据管道校验（分布漂移/空值率），"
                    "离线性能基线（AUC/F1 不低于阈值），在线影子测试（流量分流不影响线上），"
                    "监控配置（PSI/特征重要性/预测分布），发布后1小时监控窗口，回滚方案预演。"
                ),
                "tags": ["ML部署", "模型上线", "数据漂移", "监控", "回滚", "机器学习"],
            },

            # L1-hard-C: compliance framework
            "kb-compliance-framework": {
                "id": "kb-compliance-framework",
                "title": "合规框架设计 — 风险识别 控制措施 审计 报告",
                "content": (
                    "企业合规框架四层：风险识别（法规清单+差距分析），控制措施（流程+技术+人员），"
                    "内部审计（定期+专项），合规报告（管理层+监管机构双线）。"
                    "数字化合规建议引入 GRC 工具，避免电子表格管理失控。"
                ),
                "tags": ["合规", "风险识别", "内部审计", "GRC", "法规", "合规框架"],
            },

            # L1-hard-D: security threat model
            "kb-threat-model": {
                "id": "kb-threat-model",
                "title": "威胁建模 — STRIDE 资产识别 攻击面分析 缓解措施",
                "content": (
                    "STRIDE 威胁建模流程：识别系统资产与信任边界，绘制数据流图，"
                    "按 STRIDE 六类（欺骗/篡改/否认/信息泄露/拒绝服务/权限提升）枚举威胁，"
                    "对每个威胁评分（DREAD），制定缓解措施并纳入开发 Backlog。"
                ),
                "tags": ["威胁建模", "STRIDE", "安全", "攻击面", "缓解措施", "信息安全"],
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
# Seeded LTM client (Layer 2 & Layer 3 — new domains)
# ---------------------------------------------------------------------------


class ClaimBenchmarkV2LTMClient:
    """LTM client seeded with items for L2 composition and L3 generation, new domains."""

    def __init__(self) -> None:
        self._call_counts: Dict[str, int] = {}

        self._items: Dict[str, _SeedItem] = {

            # === Layer 2 seed items (easy/medium/hard per domain) ===

            # L2-easy-A: competitive analysis
            "ltm-competitive-positioning": _SeedItem(
                "ltm-competitive-positioning",
                "竞品分析框架：从产品功能、定价、目标市场、分发渠道四个维度绘制竞品矩阵，找到差异化空间；"
                "在产品优化场景里先做需求分析与用户研究，明确现有产品面对的竞争压力和用户选择原因。",
                "method", ["竞品分析", "竞品矩阵", "差异化", "定位", "需求分析", "用户研究", "现有产品"],
            ),
            "ltm-competitive-moat": _SeedItem(
                "ltm-competitive-moat",
                "竞争护城河识别：网络效应、转换成本、规模经济、品牌、专利是五类主要护城河；"
                "识别后要判断每类护城河的可持续性和被颠覆的难度，用于现有产品的竞争壁垒评估并给出加固建议，"
                "再通过设计迭代、测试验证和发布前动作把护城河加固方案落地。",
                "insight", ["护城河", "竞争优势", "网络效应", "转换成本", "竞品分析", "竞争壁垒", "加固建议", "设计迭代", "测试验证", "发布", "现有产品"],
            ),


            # L2-easy-B: supply chain basics
            "ltm-supply-chain-basics": _SeedItem(
                "ltm-supply-chain-basics",
                "供应链基础管理：需求预测（历史数据+季节性）→采购计划→库存管控（EOQ模型）→配送优化；"
                "关键指标：库存周转率、缺货率、交货准时率。",
                "method", ["供应链", "库存管控", "需求预测", "采购", "配送"],
            ),
            "ltm-supply-chain-resilience": _SeedItem(
                "ltm-supply-chain-resilience",
                "供应链韧性建设：多源采购降低单点依赖，安全库存缓冲需求波动，"
                "供应商关系分层（战略/关键/普通），定期压力测试供应中断场景。",
                "discussion", ["供应链韧性", "多源采购", "安全库存", "供应商", "风险"],
            ),

            # L2-medium-A: customer success
            "ltm-customer-success-health": _SeedItem(
                "ltm-customer-success-health",
                "客户健康度评分模型：产品使用深度（DAU/MAU/功能覆盖率）、"
                "支持工单频率（负向）、NPS/CSAT、合同续约状态，综合加权打分0-100，并用于提前90天预警流失风险；"
                "可先用于问题定义与原因分析，定位续约风险来源。",
                "method", ["客户成功", "健康度", "客户健康度", "NPS", "续约", "用户活跃", "流失预警", "问题定义", "原因分析"],
            ),

            "ltm-customer-success-playbook": _SeedItem(
                "ltm-customer-success-playbook",
                "客户成功Playbook：入网引导（Onboarding）→价值实现（Adoption）→"
                "扩张（Expansion）→续约（Renewal）；每阶段配置触发条件、CSM行动和成功指标，并预留流失干预与续约保卫动作，"
                "能够承接客户健康度评分模型的输出，直接展开为提前90天预警流失的干预方案，并补上方案设计、方案评估与执行计划。",
                "insight", ["客户成功", "Playbook", "Onboarding", "续约", "扩张", "续约Playbook", "流失干预", "干预方案", "预警流失", "客户健康度", "评分模型", "方案设计", "方案评估", "执行计划"],
            ),


            # L2-medium-B: investor deck structure
            "ltm-investor-deck-story": _SeedItem(
                "ltm-investor-deck-story",
                "投资人PPT叙事结构：问题（市场痛点）→解决方案→产品演示→市场规模（TAM/SAM/SOM）→"
                "商业模式→增长数据→团队→融资计划；控制在15页以内，并可直接展开为融资展示大纲框架。",
                "method", ["投资人", "融资", "PPT", "商业计划", "TAM", "路演", "融资展示", "大纲框架"],
            ),

            "ltm-investor-deck-metrics": _SeedItem(
                "ltm-investor-deck-metrics",
                "投资人关注的核心指标：MRR增速、NDR（净收入留存）>100%、"
                "CAC Payback Period<12个月、毛利率（SaaS>70%）、烧钱率与Runway；适合作为融资展示中的数据证明层。",
                "insight", ["投资人", "MRR", "NDR", "CAC", "Runway", "SaaS指标", "融资展示", "核心指标"],
            ),


            # L2-medium-C: MLOps pipeline
            "ltm-mlops-pipeline": _SeedItem(
                "ltm-mlops-pipeline",
                "MLOps流水线设计：数据版本控制（DVC）→实验追踪（MLflow）→"
                "模型注册中心→CI/CD自动触发训练→线上A/B发布→监控回滚；全链路可重现，适合从实验到生产的端到端方案。"
                "在重训练场景下，可把数据漂移监控接到触发自动重训练的阈值与流程中，并直接展开为方案设计、方案评估与执行计划。",
                "method", ["MLOps", "机器学习", "机器学习流水线", "流水线", "数据版本", "实验追踪", "CI/CD", "端到端", "实验到生产", "数据漂移", "自动重训练", "触发自动重训练", "方案设计", "方案评估", "执行计划"],
            ),

            "ltm-mlops-monitoring": _SeedItem(
                "ltm-mlops-monitoring",
                "ML模型线上监控体系：数据漂移检测（PSI/KS检验）、预测分布监控、"
                "业务指标关联（CTR/转化率）、告警阈值自动触发重训练或人工审核；可先用于问题定义与原因分析，识别漂移来源和阈值。",
                "discussion", ["MLOps", "模型监控", "数据漂移", "重训练", "告警", "问题定义", "原因分析"],
            ),

            # L2-hard-A: dev sprint planning (complex capacity + dependencies)
            "ltm-dev-sprint-capacity": _SeedItem(
                "ltm-dev-sprint-capacity",
                "研发Sprint容量规划：以历史速率（velocity）为基准，扣除假期/会议/技术债偿还后得净容量；"
                "Bug修复预留20%buffer，新功能不超过净容量的70%，避免过度承诺。",
                "method", ["Sprint规划", "容量规划", "研发", "velocity", "技术债"],
            ),
            "ltm-dev-sprint-dependencies": _SeedItem(
                "ltm-dev-sprint-dependencies",
                "跨团队依赖管理：在Sprint规划前完成依赖梳理（输入/输出/时间），"
                "关键路径依赖要提前一个Sprint通知，阻塞依赖升级到PO/PM层处理，不允许在Sprint中途加入。",
                "insight", ["Sprint规划", "依赖管理", "跨团队", "关键路径", "研发"],
            ),

            # L2-hard-B: competitive intelligence (deep)
            "ltm-competitive-intel-signals": _SeedItem(
                "ltm-competitive-intel-signals",
                "竞争情报信号源：招聘JD（反映产品方向）、专利申请（技术路线）、"
                "产品changelog、客户评论（G2/Capterra）、社交媒体动态、融资公告；"
                "汇总进竞品战情室每月更新。",
                "method", ["竞争情报", "竞品分析", "招聘JD", "专利", "情报"],
            ),
            "ltm-competitive-response": _SeedItem(
                "ltm-competitive-response",
                "竞品响应策略：特性跟随（防御）vs 差异化强化（进攻）vs 重新定位（逃逸）；"
                "选择取决于竞品特性是否在我方护城河范围内，以及客户重叠度。",
                "discussion", ["竞品响应", "竞争策略", "差异化", "重新定位", "竞品分析"],
            ),

            # === Layer 3 seed items (6 new domains for generation) ===

            # L3-A: org design
            "ltm-org-design-principles": _SeedItem(
                "ltm-org-design-principles",
                "组织设计原则：结构跟随战略（Chandler），最小化跨团队协调成本，"
                "每个团队应对自己的输出有完整控制权（Team Topologies 逆向康威定律）。",
                "method", ["组织设计", "架构", "团队拓扑", "协调成本", "战略"],
            ),

            # L3-B: regulatory strategy
            "ltm-regulatory-strategy": _SeedItem(
                "ltm-regulatory-strategy",
                "监管策略路径：合规先行（建立信任，低风险）vs 游说影响（参与规则制定）vs "
                "监管套利（利用模糊地带）；AI/数据类产品通常建议合规先行+主动参与政策咨询。",
                "method", ["监管策略", "合规", "政策", "AI监管", "监管"],
            ),
            "ltm-regulatory-policy-engagement": _SeedItem(
                "ltm-regulatory-policy-engagement",
                "政策参与打法：建立监管议题地图，按征求意见、行业协会、试点沙盒、定期沟通四条路径参与，"
                "输出统一立场文件和外部沟通节奏，避免被动应对。",
                "playbook", ["政策参与", "监管沟通", "行业协会", "沙盒", "立场文件"],
            ),
            "ltm-regulatory-risk-tiering": _SeedItem(
                "ltm-regulatory-risk-tiering",
                "监管风险分级：按业务场景、数据敏感度、自动化决策强度、跨境影响度分为高/中/低三级，"
                "分别绑定审查深度、审批层级与监控频率。",
                "framework", ["监管风险", "风险分级", "合规评估", "审批", "监控频率"],
            ),


            # L3-C: M&A integration
            "ltm-ma-integration": _SeedItem(
                "ltm-ma-integration",
                "并购整合优先级：Day1必须（法务/财务/员工保留），30天内（品牌对齐/IT整合计划），"
                "90天内（产品路线图合并/客户迁移计划），6个月内（组织架构定型/文化融合）。",
                "insight", ["并购", "M&A", "整合", "员工保留", "品牌整合"],
            ),
            "ltm-ma-it-cutover": _SeedItem(
                "ltm-ma-it-cutover",
                "并购整合中的IT切换：Day1只切关键报表、权限与财务主数据；30天内完成身份系统、主数据和协作工具迁移，避免一次性大爆炸切换。",
                "method", ["并购", "IT整合", "Day1", "主数据", "权限切换", "系统迁移"],
            ),
            "ltm-ma-customer-migration": _SeedItem(
                "ltm-ma-customer-migration",
                "并购后的客户迁移节奏：先划分高价值客户与高风险客户，设置90天沟通节奏、服务连续性SLA和迁移里程碑，再推进产品与合同迁移。",
                "playbook", ["并购", "客户迁移", "SLA", "90天", "里程碑", "服务连续性"],
            ),

            # L3-D: ecosystem partnerships
            "ltm-ecosystem-partnerships": _SeedItem(
                "ltm-ecosystem-partnerships",
                "生态伙伴体系构建：技术集成伙伴（API互通）、渠道分销伙伴（GTM杠杆）、"
                "战略联盟（市场共建）；每类伙伴需设计不同的激励机制和联合运营SLA。",
                "method", ["生态", "合作伙伴", "API", "渠道", "联盟", "GTM", "技术集成伙伴"],
            ),
            "ltm-ecosystem-revenue-share": _SeedItem(
                "ltm-ecosystem-revenue-share",
                "伙伴商业化分润模型：按线索贡献、成单归因、交付深度和续费留存拆分收益，避免单一签约返佣导致劣币驱逐良币。",
                "framework", ["商业化", "分润模型", "伙伴收益", "续费留存", "归因"],
            ),
            "ltm-ecosystem-tiering": _SeedItem(
                "ltm-ecosystem-tiering",
                "伙伴分级机制：注册伙伴→认证伙伴→联合增长伙伴三级，分别绑定技术认证、线索共享、联合营销和专属支持权益。",
                "playbook", ["伙伴分级", "晋升机制", "认证伙伴", "联合增长", "激励结构"],
            ),

            # L3-E: AI safety review
            "ltm-ai-safety-review": _SeedItem(
                "ltm-ai-safety-review",
                "AI安全审查框架：模型偏见测试（公平性指标），对抗性输入压力测试，"
                "隐私合规（数据最小化），可解释性要求（高风险决策必须可解释），人工审查节点设计。",
                "insight", ["AI安全", "模型偏见", "对抗性测试", "隐私", "可解释性", "安全审查"],
            ),
            "ltm-ai-fairness-metrics": _SeedItem(
                "ltm-ai-fairness-metrics",
                "公平性指标设计：至少同时跟踪 demographic parity、equal opportunity 和 false positive gap，并按受保护属性拆分评估。",
                "method", ["公平性指标", "demographic parity", "equal opportunity", "模型偏见", "受保护属性"],
            ),
            "ltm-ai-release-review": _SeedItem(
                "ltm-ai-release-review",
                "模型上线前审核：先构造代表性测试集和高风险切片，再做红线阈值复核、人工审批和上线后回滚预案。",
                "playbook", ["上线前审核", "测试集设计", "高风险切片", "人工审批", "回滚预案"],
            ),

            # L3-F: platform architecture
            "ltm-platform-architecture": _SeedItem(
                "ltm-platform-architecture",
                "平台架构演进：单体→微服务（按业务边界拆分）→平台化（API Gateway+统一认证+数据总线）；"
                "平台化时机：当集成需求>3个且接口协议不统一，优先建平台而非继续点对点集成。",
                "method", ["平台架构", "微服务", "API Gateway", "集成", "平台化"],
            ),
            "ltm-platform-open-tiering": _SeedItem(
                "ltm-platform-open-tiering",
                "API开放度分级：公共API开放基础查询，合作API开放写入与事件订阅，战略API开放联合解决方案能力，并按等级绑定速率、审计和支持策略。",
                "framework", ["API开放度", "开放分级", "公共API", "合作API", "战略API"],
            ),
            "ltm-platform-governance": _SeedItem(
                "ltm-platform-governance",
                "平台治理规则：开发者准入、应用审核、滥用处罚、生态激励和核心能力保留要同时设计，避免开放后侵蚀核心竞争力。",
                "playbook", ["平台治理", "开发者生态", "准入审核", "核心竞争力", "生态激励"],
            ),
        }

    def recall(self, query: str) -> Any:
        q = str(query or "")
        self._call_counts[q] = self._call_counts.get(q, 0) + 1
        call_n = self._call_counts[q]

        # ── Layer 3 stateful flows (force Layer-2 miss on 1st call) ──────────

        # L3-A: org design
        if "组织设计" in q or ("团队拓扑" in q and "结构" in q):
            if call_n == 1:
                return []
            return {
                "references": ["ltm-org-design-principles"],
                "enhancements": [{
                    "source": "ltm-org-design-principles",
                    "applicable_to": "组织架构设计",
                    "text": "结构跟随战略，最小化协调成本，逆向康威定律。",
                }],
            }

        # L3-B: regulatory strategy
        if (
            "监管策略" in q
            or "监管风险" in q
            or ("合规先行" in q and "政策" in q)
            or "欧盟AI法案" in q
            or "算法推荐" in q
        ):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-regulatory-strategy",
                    "ltm-regulatory-policy-engagement",
                    "ltm-regulatory-risk-tiering",
                ],
                "enhancements": [
                    {
                        "source": "ltm-regulatory-strategy",
                        "applicable_to": "监管路径选择",
                        "text": "合规先行建立信任，主动参与政策咨询以影响规则制定，监管套利只适合短期。",
                    },
                    {
                        "source": "ltm-regulatory-policy-engagement",
                        "applicable_to": "政策参与计划",
                        "text": "建立监管议题地图，按征求意见、行业协会、试点沙盒、定期沟通四条路径参与，并维护统一立场文件。",
                    },
                    {
                        "source": "ltm-regulatory-risk-tiering",
                        "applicable_to": "监管风险分级管理",
                        "text": "按业务场景、数据敏感度、自动化决策强度、跨境影响度进行高/中/低三级分层，并绑定审批与监控节奏。",
                    },
                ],
            }


        # L3-C: M&A integration
        if "并购整合" in q or ("M&A" in q and "整合" in q) or ("并购" in q and "Day1" in q):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-ma-integration",
                    "ltm-ma-it-cutover",
                    "ltm-ma-customer-migration",
                ],
                "enhancements": [
                    {
                        "source": "ltm-ma-integration",
                        "applicable_to": "整合计划",
                        "text": "用 Day1 / 30天 / 90天 / 6个月 四个阶段排定整合优先级，先稳住法务、财务和关键员工。",
                    },
                    {
                        "source": "ltm-ma-it-cutover",
                        "applicable_to": "IT整合切换",
                        "text": "IT 切换不要一次性爆炸迁移，先保关键报表、权限和主数据，再滚动推进系统整合。",
                    },
                    {
                        "source": "ltm-ma-customer-migration",
                        "applicable_to": "客户迁移节奏",
                        "text": "按客户价值和迁移风险分层，给出90天沟通节奏、服务连续性SLA和迁移里程碑。",
                    },
                ],
            }

        # L3-D: ecosystem partnerships
        if (
            "生态伙伴" in q
            or ("合作伙伴体系" in q)
            or ("技术集成伙伴" in q and "渠道" in q)
            or ("技术集成伙伴" in q and "商业化" in q)
            or "分润模型" in q
            or "伙伴分级" in q
        ):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-ecosystem-partnerships",
                    "ltm-ecosystem-revenue-share",
                    "ltm-ecosystem-tiering",
                ],
                "enhancements": [
                    {
                        "source": "ltm-ecosystem-partnerships",
                        "applicable_to": "伙伴结构设计",
                        "text": "先拆成技术集成、渠道分销、战略联盟三类伙伴，再分别设计协作边界和联合运营SLA。",
                    },
                    {
                        "source": "ltm-ecosystem-revenue-share",
                        "applicable_to": "分润模型",
                        "text": "分润不要只看签约返佣，要把线索贡献、成单归因、交付深度和续费留存一起纳入收益分配。",
                    },
                    {
                        "source": "ltm-ecosystem-tiering",
                        "applicable_to": "伙伴晋升机制",
                        "text": "把伙伴做成注册、认证、联合增长三级，用认证、线索共享和专属支持驱动升级。",
                    },
                ],
            }

        # L3-E: AI safety review
        if (
            "AI安全审查" in q
            or ("模型偏见" in q and "对抗" in q)
            or ("AI安全" in q and "框架" in q)
            or ("AI安全" in q and "模型偏见" in q)
            or "公平性指标" in q
            or "上线前审核" in q
        ):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-ai-safety-review",
                    "ltm-ai-fairness-metrics",
                    "ltm-ai-release-review",
                ],
                "enhancements": [
                    {
                        "source": "ltm-ai-safety-review",
                        "applicable_to": "安全审查设计",
                        "text": "把偏见测试、对抗压测、隐私合规、可解释性和人工审查节点做成统一审核框架。",
                    },
                    {
                        "source": "ltm-ai-fairness-metrics",
                        "applicable_to": "公平性指标定义",
                        "text": "公平性至少同时看 demographic parity、equal opportunity 和 false positive gap，并按受保护属性拆分。",
                    },
                    {
                        "source": "ltm-ai-release-review",
                        "applicable_to": "上线前审核流程",
                        "text": "上线前先构造代表性测试集和高风险切片，再过人工审批和回滚预案。",
                    },
                ],
            }

        # L3-F: platform architecture
        if (
            "平台架构" in q
            or ("API Gateway" in q and "平台化" in q)
            or ("平台化" in q and "集成" in q)
            or ("平台化" in q and "开放策略" in q)
            or "API开放度" in q
            or ("开发者生态" in q and "平台治理" in q)
        ):
            if call_n == 1:
                return []
            return {
                "references": [
                    "ltm-platform-architecture",
                    "ltm-platform-open-tiering",
                    "ltm-platform-governance",
                ],
                "enhancements": [
                    {
                        "source": "ltm-platform-architecture",
                        "applicable_to": "平台化边界",
                        "text": "先明确什么时候该平台化：当集成需求持续增加且协议不统一时，平台化比点对点扩张更稳。",
                    },
                    {
                        "source": "ltm-platform-open-tiering",
                        "applicable_to": "API开放度分级",
                        "text": "把 API 开放拆成公共、合作、战略三级，并给每级绑定速率、审计和支持策略。",
                    },
                    {
                        "source": "ltm-platform-governance",
                        "applicable_to": "生态治理",
                        "text": "开放策略必须同时写清开发者准入、应用审核、滥用处罚和核心能力保留规则。",
                    },
                ],
            }

        # ── Layer 2 keyword-based recall ──────────────────────────────────────

        hits: List[Dict[str, Any]] = []

        # L2-easy-A: competitive analysis
        if "竞品分析" in q or "竞品矩阵" in q or "护城河" in q or "差异化" in q:
            hits.extend([
                self._items["ltm-competitive-positioning"].to_dict(),
                self._items["ltm-competitive-moat"].to_dict(),
            ])

        # L2-easy-B: supply chain
        if "供应链" in q or "库存管控" in q or "需求预测" in q:
            hits.extend([
                self._items["ltm-supply-chain-basics"].to_dict(),
                self._items["ltm-supply-chain-resilience"].to_dict(),
            ])

        # L2-medium-A: customer success
        if "客户成功" in q or "健康度" in q or "Playbook" in q or "续约" in q:
            hits.extend([
                self._items["ltm-customer-success-health"].to_dict(),
                self._items["ltm-customer-success-playbook"].to_dict(),
            ])

        # L2-medium-B: investor deck
        if "投资人" in q or "融资" in q or "路演" in q or "TAM" in q:
            hits.extend([
                self._items["ltm-investor-deck-story"].to_dict(),
                self._items["ltm-investor-deck-metrics"].to_dict(),
            ])

        # L2-medium-C: MLOps
        if "MLOps" in q or "机器学习流水线" in q or "模型监控" in q or "数据漂移" in q:
            hits.extend([
                self._items["ltm-mlops-pipeline"].to_dict(),
                self._items["ltm-mlops-monitoring"].to_dict(),
            ])

        # L2-hard-A: dev sprint planning
        if "Sprint规划" in q or "容量规划" in q or "依赖管理" in q or "研发Sprint" in q:
            hits.extend([
                self._items["ltm-dev-sprint-capacity"].to_dict(),
                self._items["ltm-dev-sprint-dependencies"].to_dict(),
            ])

        # L2-hard-B: competitive intelligence (deep)
        if "竞争情报" in q or "情报源" in q or "竞品响应" in q:
            hits.extend([
                self._items["ltm-competitive-intel-signals"].to_dict(),
                self._items["ltm-competitive-response"].to_dict(),
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


def build_claim_benchmark_v2_system() -> AdaptiveSkillSystem:
    """Return a fresh claim-benchmark-v2–scoped system instance."""
    return AdaptiveSkillSystem(
        kb_client=ClaimBenchmarkV2KBClient(),
        ltm_client=ClaimBenchmarkV2LTMClient(),
    )


# ---------------------------------------------------------------------------
# Shared grader factories
# ---------------------------------------------------------------------------


def _l1_grader(grader_id: str, name: str, meta: Dict[str, Any]) -> GraderSpec:
    return GraderSpec(
        grader_id=grader_id,
        name=name,
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
        metadata=meta,
    )


def _l2_grader(grader_id: str, name: str, meta: Dict[str, Any]) -> GraderSpec:
    return GraderSpec(
        grader_id=grader_id,
        name=name,
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
        metadata=meta,
    )


def _l3_grader(
    grader_id: str,
    name: str,
    semantic_ref: str,
    meta: Dict[str, Any],
) -> GraderSpec:
    return GraderSpec(
        grader_id=grader_id,
        name=name,
        grading_mode="scored",
        pass_threshold=0.65,
        dimensions=[
            {"name": "layer_is_3", "type": "exact_match", "weight": 0.35,
             "config": {"field": "layer", "expected": 3}},
            _l3_semantic_dim(semantic_ref),
            {"name": "confidence_gte_070", "type": "threshold", "weight": 0.20,
             "config": {"field": "confidence", "min_value": 0.70}},
            {"name": "auto_generated_flag", "type": "contains_key", "weight": 0.15,
             "config": {"field": "metadata", "key": "layer_3_auto_generated"}},
        ],
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Layer 1 cases (12 cases — easy×4, medium×4, hard×4)
# ---------------------------------------------------------------------------

_L1_SUITE = CLAIM_BENCHMARK_V2_SUITE_ID
_L1_TAGS = ["claim-benchmark-v2", "layer1", "seeded"]
_L1_META = {"suite": _L1_SUITE}

# ── EASY ────────────────────────────────────────────────────────────────────

L1_EASY_A_CASE = CaseSpec(
    case_id="claim-v2-l1-easy-hiring-pipeline",
    title="Claim v2 L1-easy-A — Hiring pipeline",
    description="Layer-1 KB hit for hiring pipeline process.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 招聘流程 设计，涵盖岗位定义、简历筛选、面试轮次和Offer决策。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["hiring", "easy"],
    metadata={**_L1_META, "difficulty": "easy"},
)
L1_EASY_A_GRADER = _l1_grader(
    "grader-v2-l1-easy-hiring-pipeline",
    "Claim v2 L1-easy-A grader",
    {**_L1_META, "difficulty": "easy"},
)

L1_EASY_B_CASE = CaseSpec(
    case_id="claim-v2-l1-easy-crisis-comms",
    title="Claim v2 L1-easy-B — Crisis communication",
    description="Layer-1 KB hit for crisis communication framework.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 危机沟通 框架，包含第一时间响应、信息透明、责任声明和后续跟进。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["crisis-comms", "easy"],
    metadata={**_L1_META, "difficulty": "easy"},
)
L1_EASY_B_GRADER = _l1_grader(
    "grader-v2-l1-easy-crisis-comms",
    "Claim v2 L1-easy-B grader",
    {**_L1_META, "difficulty": "easy"},
)

L1_EASY_C_CASE = CaseSpec(
    case_id="claim-v2-l1-easy-pricing-basic",
    title="Claim v2 L1-easy-C — Pricing strategy basics",
    description="Layer-1 KB hit for basic pricing strategy.",
    task_type="skill_execution",
    input_payload={"problem": "请解释三种基础 定价策略：成本加成、竞品对标、价值定价，并给出适用场景。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["pricing", "easy"],
    metadata={**_L1_META, "difficulty": "easy"},
)
L1_EASY_C_GRADER = _l1_grader(
    "grader-v2-l1-easy-pricing-basic",
    "Claim v2 L1-easy-C grader",
    {**_L1_META, "difficulty": "easy"},
)

L1_EASY_D_CASE = CaseSpec(
    case_id="claim-v2-l1-easy-ab-test-setup",
    title="Claim v2 L1-easy-D — A/B test setup",
    description="Layer-1 KB hit for A/B test design fundamentals.",
    task_type="skill_execution",
    input_payload={"problem": "请给我 A/B测试 设计的四个要素：假设、核心指标、样本量确定和显著性水平设定。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["ab-test", "easy"],
    metadata={**_L1_META, "difficulty": "easy"},
)
L1_EASY_D_GRADER = _l1_grader(
    "grader-v2-l1-easy-ab-test-setup",
    "Claim v2 L1-easy-D grader",
    {**_L1_META, "difficulty": "easy"},
)

# ── MEDIUM ───────────────────────────────────────────────────────────────────

L1_MEDIUM_A_CASE = CaseSpec(
    case_id="claim-v2-l1-medium-api-design",
    title="Claim v2 L1-medium-A — API design",
    description="Layer-1 KB hit for API design principles.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 API 设计 规范，覆盖RESTful命名、版本控制、错误码和文档要求。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["api-design", "medium"],
    metadata={**_L1_META, "difficulty": "medium"},
)
L1_MEDIUM_A_GRADER = _l1_grader(
    "grader-v2-l1-medium-api-design",
    "Claim v2 L1-medium-A grader",
    {**_L1_META, "difficulty": "medium"},
)

L1_MEDIUM_B_CASE = CaseSpec(
    case_id="claim-v2-l1-medium-knowledge-mgmt",
    title="Claim v2 L1-medium-B — Knowledge management",
    description="Layer-1 KB hit for knowledge management system.",
    task_type="skill_execution",
    input_payload={"problem": "请设计一套 知识管理 体系，涵盖捕获、整理、检索、传播、更新五个环节。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["knowledge-mgmt", "medium"],
    metadata={**_L1_META, "difficulty": "medium"},
)
L1_MEDIUM_B_GRADER = _l1_grader(
    "grader-v2-l1-medium-knowledge-mgmt",
    "Claim v2 L1-medium-B grader",
    {**_L1_META, "difficulty": "medium"},
)

L1_MEDIUM_C_CASE = CaseSpec(
    case_id="claim-v2-l1-medium-sprint-retro",
    title="Claim v2 L1-medium-C — Sprint retrospective",
    description="Layer-1 KB hit for Sprint retrospective framework.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 Sprint 复盘 框架，包含做得好、可改进、行动项三类以及跟踪机制。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["sprint-retro", "medium"],
    metadata={**_L1_META, "difficulty": "medium"},
)
L1_MEDIUM_C_GRADER = _l1_grader(
    "grader-v2-l1-medium-sprint-retro",
    "Claim v2 L1-medium-C grader",
    {**_L1_META, "difficulty": "medium"},
)

L1_MEDIUM_D_CASE = CaseSpec(
    case_id="claim-v2-l1-medium-stakeholder-map",
    title="Claim v2 L1-medium-D — Stakeholder map",
    description="Layer-1 KB hit for stakeholder mapping.",
    task_type="skill_execution",
    input_payload={"problem": "请帮我做一个 干系人 分析，识别相关方，按影响力×关注度分类，制定沟通策略。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["stakeholder", "medium"],
    metadata={**_L1_META, "difficulty": "medium"},
)
L1_MEDIUM_D_GRADER = _l1_grader(
    "grader-v2-l1-medium-stakeholder-map",
    "Claim v2 L1-medium-D grader",
    {**_L1_META, "difficulty": "medium"},
)

# ── HARD ──────────────────────────────────────────────────────────────────────

L1_HARD_A_CASE = CaseSpec(
    case_id="claim-v2-l1-hard-pricing-advanced",
    title="Claim v2 L1-hard-A — Advanced pricing strategy",
    description="Layer-1 KB hit for complex multi-segment pricing.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 高级定价策略，涵盖分层定价、动态定价、价格歧视和捆绑销售，并结合LTV验证。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["pricing-advanced", "hard"],
    metadata={**_L1_META, "difficulty": "hard"},
)
L1_HARD_A_GRADER = _l1_grader(
    "grader-v2-l1-hard-pricing-advanced",
    "Claim v2 L1-hard-A grader",
    {**_L1_META, "difficulty": "hard"},
)

L1_HARD_B_CASE = CaseSpec(
    case_id="claim-v2-l1-hard-ml-deploy-checklist",
    title="Claim v2 L1-hard-B — ML model deployment checklist",
    description="Layer-1 KB hit for ML deployment checklist.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一份 ML 模型上线 清单，覆盖数据校验、性能基线、监控配置和回滚方案。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["ml-deploy", "hard"],
    metadata={**_L1_META, "difficulty": "hard"},
)
L1_HARD_B_GRADER = _l1_grader(
    "grader-v2-l1-hard-ml-deploy-checklist",
    "Claim v2 L1-hard-B grader",
    {**_L1_META, "difficulty": "hard"},
)

L1_HARD_C_CASE = CaseSpec(
    case_id="claim-v2-l1-hard-compliance-framework",
    title="Claim v2 L1-hard-C — Compliance framework",
    description="Layer-1 KB hit for enterprise compliance framework.",
    task_type="skill_execution",
    input_payload={"problem": "请给我一套 企业合规 框架，涵盖风险识别、控制措施、内部审计和报告四层设计。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["compliance", "hard"],
    metadata={**_L1_META, "difficulty": "hard"},
)
L1_HARD_C_GRADER = _l1_grader(
    "grader-v2-l1-hard-compliance-framework",
    "Claim v2 L1-hard-C grader",
    {**_L1_META, "difficulty": "hard"},
)

L1_HARD_D_CASE = CaseSpec(
    case_id="claim-v2-l1-hard-threat-model",
    title="Claim v2 L1-hard-D — Security threat modeling",
    description="Layer-1 KB hit for STRIDE threat modeling.",
    task_type="skill_execution",
    input_payload={"problem": "请用 STRIDE 方法帮我做 威胁建模，包含资产识别、攻击面分析和缓解措施。"},
    expected_outcome_type="text",
    expected_layer=[1],
    tags=_L1_TAGS + ["threat-model", "hard"],
    metadata={**_L1_META, "difficulty": "hard"},
)
L1_HARD_D_GRADER = _l1_grader(
    "grader-v2-l1-hard-threat-model",
    "Claim v2 L1-hard-D grader",
    {**_L1_META, "difficulty": "hard"},
)


# ---------------------------------------------------------------------------
# Layer 2 cases (12 cases — easy×4 [2 domains×2], medium×4 [2 domains×2], hard×4 [2 domains×2])
# ---------------------------------------------------------------------------

_L2_TAGS = ["claim-benchmark-v2", "layer2", "seeded"]
_L2_META = {"suite": _L1_SUITE}

# ── EASY ────────────────────────────────────────────────────────────────────

L2_EASY_A_CASE = CaseSpec(
    case_id="claim-v2-l2-easy-competitive-analysis",
    title="Claim v2 L2-easy-A — Competitive analysis",
    description="Layer-2 composition: competitive positioning + moat.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 竞品分析 和 护城河 识别，帮我制定一套差异化竞争策略。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["competitive", "easy"],
    metadata={**_L2_META, "difficulty": "easy"},
)
L2_EASY_A_GRADER = _l2_grader(
    "grader-v2-l2-easy-competitive-analysis",
    "Claim v2 L2-easy-A grader",
    {**_L2_META, "difficulty": "easy"},
)

L2_EASY_B_CASE = CaseSpec(
    case_id="claim-v2-l2-easy-supply-chain",
    title="Claim v2 L2-easy-B — Supply chain management",
    description="Layer-2 composition: supply chain basics + resilience.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 供应链 库存管控 需求预测 和 供应链韧性 多源采购，给我一套降低断供风险的综合管理方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["supply-chain", "easy"],
    metadata={**_L2_META, "difficulty": "easy"},
)
L2_EASY_B_GRADER = _l2_grader(
    "grader-v2-l2-easy-supply-chain",
    "Claim v2 L2-easy-B grader",
    {**_L2_META, "difficulty": "easy"},
)

L2_EASY_C_CASE = CaseSpec(
    case_id="claim-v2-l2-easy-supply-chain-risk",
    title="Claim v2 L2-easy-C — Supply chain risk mitigation",
    description="Layer-2 composition: supply chain resilience + inventory.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 供应链韧性 安全库存 和 供应链 多源采购，给我一套供应商风险缓解方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["supply-chain", "easy"],
    metadata={**_L2_META, "difficulty": "easy"},
)
L2_EASY_C_GRADER = _l2_grader(
    "grader-v2-l2-easy-supply-chain-risk",
    "Claim v2 L2-easy-C grader",
    {**_L2_META, "difficulty": "easy"},
)

L2_EASY_D_CASE = CaseSpec(
    case_id="claim-v2-l2-easy-competitive-moat",
    title="Claim v2 L2-easy-D — Competitive moat strategy",
    description="Layer-2 composition: competitive positioning + moat for existing product.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 竞品矩阵 和 护城河 分析，帮我评估现有产品的竞争壁垒并给出加固建议。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["competitive", "easy"],
    metadata={**_L2_META, "difficulty": "easy"},
)
L2_EASY_D_GRADER = _l2_grader(
    "grader-v2-l2-easy-competitive-moat",
    "Claim v2 L2-easy-D grader",
    {**_L2_META, "difficulty": "easy"},
)

# ── MEDIUM ───────────────────────────────────────────────────────────────────

L2_MEDIUM_A_CASE = CaseSpec(
    case_id="claim-v2-l2-medium-customer-success",
    title="Claim v2 L2-medium-A — Customer success program",
    description="Layer-2 composition: customer success health + playbook.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 客户成功 健康度评分 和 Playbook 设计，给我一套提升NDR的客户运营体系。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["customer-success", "medium"],
    metadata={**_L2_META, "difficulty": "medium"},
)
L2_MEDIUM_A_GRADER = _l2_grader(
    "grader-v2-l2-medium-customer-success",
    "Claim v2 L2-medium-A grader",
    {**_L2_META, "difficulty": "medium"},
)

L2_MEDIUM_B_CASE = CaseSpec(
    case_id="claim-v2-l2-medium-investor-deck",
    title="Claim v2 L2-medium-B — Investor pitch deck",
    description="Layer-2 composition: investor deck story + metrics.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 投资人 路演PPT 叙事结构和 关键数据 MRR NDR，帮我准备一个融资展示的大纲框架。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["investor-deck", "medium"],
    metadata={**_L2_META, "difficulty": "medium"},
)
L2_MEDIUM_B_GRADER = _l2_grader(
    "grader-v2-l2-medium-investor-deck",
    "Claim v2 L2-medium-B grader",
    {**_L2_META, "difficulty": "medium"},
)

L2_MEDIUM_C_CASE = CaseSpec(
    case_id="claim-v2-l2-medium-mlops-pipeline",
    title="Claim v2 L2-medium-C — MLOps pipeline",
    description="Layer-2 composition: MLOps pipeline + monitoring.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 MLOps 机器学习流水线 和 模型监控 体系，给我一套从实验到生产的端到端方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["mlops", "medium"],
    metadata={**_L2_META, "difficulty": "medium"},
)
L2_MEDIUM_C_GRADER = _l2_grader(
    "grader-v2-l2-medium-mlops-pipeline",
    "Claim v2 L2-medium-C grader",
    {**_L2_META, "difficulty": "medium"},
)

L2_MEDIUM_D_CASE = CaseSpec(
    case_id="claim-v2-l2-medium-customer-renewal",
    title="Claim v2 L2-medium-D — Customer renewal strategy",
    description="Layer-2 composition: customer health + renewal playbook.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 客户健康度 评分模型 和 续约 Playbook，给我一套提前90天预警流失的干预方案。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["customer-success", "medium"],
    metadata={**_L2_META, "difficulty": "medium"},
)
L2_MEDIUM_D_GRADER = _l2_grader(
    "grader-v2-l2-medium-customer-renewal",
    "Claim v2 L2-medium-D grader",
    {**_L2_META, "difficulty": "medium"},
)

# ── HARD ──────────────────────────────────────────────────────────────────────

L2_HARD_A_CASE = CaseSpec(
    case_id="claim-v2-l2-hard-dev-sprint",
    title="Claim v2 L2-hard-A — Dev sprint planning",
    description="Layer-2 composition: sprint capacity + dependencies.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 研发Sprint 容量规划 和 跨团队依赖管理，给我一套避免过度承诺的Sprint规划框架。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["dev-sprint", "hard"],
    metadata={**_L2_META, "difficulty": "hard"},
)
L2_HARD_A_GRADER = _l2_grader(
    "grader-v2-l2-hard-dev-sprint",
    "Claim v2 L2-hard-A grader",
    {**_L2_META, "difficulty": "hard"},
)

L2_HARD_B_CASE = CaseSpec(
    case_id="claim-v2-l2-hard-competitive-intel",
    title="Claim v2 L2-hard-B — Competitive intelligence",
    description="Layer-2 composition: competitive intel signals + response strategy.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 竞争情报 信号源 和 竞品响应 策略，帮我建立一套竞品战情室和快速响应机制。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["competitive-intel", "hard"],
    metadata={**_L2_META, "difficulty": "hard"},
)
L2_HARD_B_GRADER = _l2_grader(
    "grader-v2-l2-hard-competitive-intel",
    "Claim v2 L2-hard-B grader",
    {**_L2_META, "difficulty": "hard"},
)

L2_HARD_C_CASE = CaseSpec(
    case_id="claim-v2-l2-hard-mlops-retrain",
    title="Claim v2 L2-hard-C — MLOps retraining strategy",
    description="Layer-2 composition: MLOps monitoring + retraining trigger design.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 数据漂移 监控 和 MLOps 流水线，设计一套触发自动重训练的阈值与流程。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["mlops", "hard"],
    metadata={**_L2_META, "difficulty": "hard"},
)
L2_HARD_C_GRADER = _l2_grader(
    "grader-v2-l2-hard-mlops-retrain",
    "Claim v2 L2-hard-C grader",
    {**_L2_META, "difficulty": "hard"},
)

L2_HARD_D_CASE = CaseSpec(
    case_id="claim-v2-l2-hard-sprint-dependencies",
    title="Claim v2 L2-hard-D — Sprint cross-team dependencies",
    description="Layer-2 composition: sprint capacity + dependency escalation.",
    task_type="skill_composition",
    input_payload={"problem": "请基于 Sprint规划 容量规划 和 依赖管理 升级机制，帮我设计一套跨团队阻塞快速解决SOP。"},
    expected_outcome_type="text",
    expected_layer=[2],
    tags=_L2_TAGS + ["dev-sprint", "hard"],
    metadata={**_L2_META, "difficulty": "hard"},
)
L2_HARD_D_GRADER = _l2_grader(
    "grader-v2-l2-hard-sprint-dependencies",
    "Claim v2 L2-hard-D grader",
    {**_L2_META, "difficulty": "hard"},
)


# ---------------------------------------------------------------------------
# Layer 3 cases (12 cases — easy×4, medium×4, hard×4)
# ---------------------------------------------------------------------------

_L3_TAGS = ["claim-benchmark-v2", "layer3", "seeded"]
_L3_META = {"suite": _L1_SUITE}

# ── EASY ────────────────────────────────────────────────────────────────────

L3_EASY_A_CASE = CaseSpec(
    case_id="claim-v2-l3-easy-org-design",
    title="Claim v2 L3-easy-A — Org design",
    description="Force L2 miss, validate L3 generation for org design.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我做一套 组织设计 方案，基于逆向康威定律降低团队协调成本，适配当前战略阶段。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["org-design", "easy"],
    metadata={**_L3_META, "difficulty": "easy"},
)
L3_EASY_A_GRADER = _l3_grader(
    "grader-v2-l3-easy-org-design",
    "Claim v2 L3-easy-A grader",
    "组织设计 团队拓扑 协调成本 战略对齐 解决方案",
    {**_L3_META, "difficulty": "easy"},
)

L3_EASY_B_CASE = CaseSpec(
    case_id="claim-v2-l3-easy-regulatory-strategy",
    title="Claim v2 L3-easy-B — Regulatory strategy",
    description="Force L2 miss, validate L3 generation for regulatory strategy.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我制定一套 监管策略 路径，包含合规先行评估、政策参与计划和监管风险分级管理体系。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["regulatory", "easy"],
    metadata={**_L3_META, "difficulty": "easy"},
)
L3_EASY_B_GRADER = _l3_grader(
    "grader-v2-l3-easy-regulatory-strategy",
    "Claim v2 L3-easy-B grader",
    "AI监管策略 合规路径 政策参与 风险评估 解决方案",
    {**_L3_META, "difficulty": "easy"},
)

L3_EASY_C_CASE = CaseSpec(
    case_id="claim-v2-l3-easy-ma-integration",
    title="Claim v2 L3-easy-C — M&A integration",
    description="Force L2 miss, validate L3 generation for M&A integration.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计一套 并购整合 计划，从Day1到6个月内按优先级分阶段完成整合。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["ma-integration", "easy"],
    metadata={**_L3_META, "difficulty": "easy"},
)
L3_EASY_C_GRADER = _l3_grader(
    "grader-v2-l3-easy-ma-integration",
    "Claim v2 L3-easy-C grader",
    "并购整合 Day1 分阶段计划 员工保留 品牌整合 解决方案",
    {**_L3_META, "difficulty": "easy"},
)

L3_EASY_D_CASE = CaseSpec(
    case_id="claim-v2-l3-easy-ecosystem-partnerships",
    title="Claim v2 L3-easy-D — Ecosystem partnerships",
    description="Force L2 miss, validate L3 generation for ecosystem partner program.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我构建一套 生态伙伴 体系，分层管理技术集成伙伴、渠道分销伙伴和战略联盟。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["partnerships", "easy"],
    metadata={**_L3_META, "difficulty": "easy"},
)
L3_EASY_D_GRADER = _l3_grader(
    "grader-v2-l3-easy-ecosystem-partnerships",
    "Claim v2 L3-easy-D grader",
    "生态伙伴体系 分层管理 技术集成 渠道分销 战略联盟 解决方案",
    {**_L3_META, "difficulty": "easy"},
)

# ── MEDIUM ───────────────────────────────────────────────────────────────────

L3_MEDIUM_A_CASE = CaseSpec(
    case_id="claim-v2-l3-medium-ai-safety-review",
    title="Claim v2 L3-medium-A — AI safety review",
    description="Force L2 miss, validate L3 for AI safety review framework.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计一套 AI安全审查 框架，涵盖模型偏见测试、对抗性输入测试、隐私合规和可解释性要求。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["ai-safety", "medium"],
    metadata={**_L3_META, "difficulty": "medium"},
)
L3_MEDIUM_A_GRADER = _l3_grader(
    "grader-v2-l3-medium-ai-safety-review",
    "Claim v2 L3-medium-A grader",
    "AI安全审查 模型偏见 对抗性测试 隐私合规 可解释性 解决方案",
    {**_L3_META, "difficulty": "medium"},
)

L3_MEDIUM_B_CASE = CaseSpec(
    case_id="claim-v2-l3-medium-platform-architecture",
    title="Claim v2 L3-medium-B — Platform architecture",
    description="Force L2 miss, validate L3 for platform architecture evolution.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计一套 平台架构 演进方案，从单体到微服务再到平台化，包含API Gateway和数据总线设计。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["platform-arch", "medium"],
    metadata={**_L3_META, "difficulty": "medium"},
)
L3_MEDIUM_B_GRADER = _l3_grader(
    "grader-v2-l3-medium-platform-architecture",
    "Claim v2 L3-medium-B grader",
    "平台化 API Gateway 微服务演进 集成 架构 解决方案",
    {**_L3_META, "difficulty": "medium"},
)

L3_MEDIUM_C_CASE = CaseSpec(
    case_id="claim-v2-l3-medium-ai-safety-bias",
    title="Claim v2 L3-medium-C — AI bias mitigation",
    description="Force L2 miss, validate L3 for AI bias mitigation strategy.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我制定一套 AI安全 模型偏见 缓解计划，包含公平性指标定义、测试集设计和上线前审核流程。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["ai-safety", "medium"],
    metadata={**_L3_META, "difficulty": "medium"},
)
L3_MEDIUM_C_GRADER = _l3_grader(
    "grader-v2-l3-medium-ai-safety-bias",
    "Claim v2 L3-medium-C grader",
    "AI模型偏见 公平性指标 测试集 审核流程 缓解方案",
    {**_L3_META, "difficulty": "medium"},
)

L3_MEDIUM_D_CASE = CaseSpec(
    case_id="claim-v2-l3-medium-platform-integration",
    title="Claim v2 L3-medium-D — Platform integration governance",
    description="Force L2 miss, validate L3 for platform integration governance.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计 平台化 集成治理机制，包含API版本管理、接入审批流程和服务SLA监控体系。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["platform-arch", "medium"],
    metadata={**_L3_META, "difficulty": "medium"},
)
L3_MEDIUM_D_GRADER = _l3_grader(
    "grader-v2-l3-medium-platform-integration",
    "Claim v2 L3-medium-D grader",
    "平台集成治理 API版本管理 接入审批 SLA监控 解决方案",
    {**_L3_META, "difficulty": "medium"},
)

# ── HARD ──────────────────────────────────────────────────────────────────────

L3_HARD_A_CASE = CaseSpec(
    case_id="claim-v2-l3-hard-ma-cultural-integration",
    title="Claim v2 L3-hard-A — M&A cultural integration",
    description="Force L2 miss, validate L3 for complex M&A cultural integration.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计一套 并购整合 中的文化融合方案，包含文化诊断、冲突识别、统一叙事和变革管理。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["ma-integration", "hard"],
    metadata={**_L3_META, "difficulty": "hard"},
)
L3_HARD_A_GRADER = _l3_grader(
    "grader-v2-l3-hard-ma-cultural-integration",
    "Claim v2 L3-hard-A grader",
    "并购 文化融合 文化诊断 变革管理 统一叙事 解决方案",
    {**_L3_META, "difficulty": "hard"},
)

L3_HARD_B_CASE = CaseSpec(
    case_id="claim-v2-l3-hard-ecosystem-monetization",
    title="Claim v2 L3-hard-B — Ecosystem monetization strategy",
    description="Force L2 miss, validate L3 for complex ecosystem monetization.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我构建 技术集成伙伴 生态 的商业化方案，包含分润模型、激励结构和伙伴分级晋升机制。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["partnerships", "hard"],
    metadata={**_L3_META, "difficulty": "hard"},
)
L3_HARD_B_GRADER = _l3_grader(
    "grader-v2-l3-hard-ecosystem-monetization",
    "Claim v2 L3-hard-B grader",
    "生态商业化 分润模型 激励结构 伙伴分级 技术集成 解决方案",
    {**_L3_META, "difficulty": "hard"},
)

L3_HARD_C_CASE = CaseSpec(
    case_id="claim-v2-l3-hard-regulatory-multimarket",
    title="Claim v2 L3-hard-C — Multi-market regulatory strategy",
    description="Force L2 miss, validate L3 for multi-market regulatory compliance strategy.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我制定一套多市场 监管策略，同时覆盖欧盟AI法案和中国算法推荐管理规定，设计统一监管风险管控框架和合规先行操作流程。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["regulatory", "hard"],
    metadata={**_L3_META, "difficulty": "hard"},
)
L3_HARD_C_GRADER = _l3_grader(
    "grader-v2-l3-hard-regulatory-multimarket",
    "Claim v2 L3-hard-C grader",
    "多市场AI合规 欧盟AI法案 算法推荐 统一管控框架 解决方案",
    {**_L3_META, "difficulty": "hard"},
)

L3_HARD_D_CASE = CaseSpec(
    case_id="claim-v2-l3-hard-platform-openness",
    title="Claim v2 L3-hard-D — Platform openness strategy",
    description="Force L2 miss, validate L3 for platform openness and developer ecosystem.",
    task_type="skill_generation",
    input_payload={"problem": "请帮我设计 平台化 开放策略，包含API开放度分级、开发者生态建设和平台治理规则，同时保障核心竞争力不被侵蚀。"},
    expected_outcome_type="text",
    expected_layer=[3],
    tags=_L3_TAGS + ["platform-arch", "hard"],
    metadata={**_L3_META, "difficulty": "hard"},
)
L3_HARD_D_GRADER = _l3_grader(
    "grader-v2-l3-hard-platform-openness",
    "Claim v2 L3-hard-D grader",
    "平台开放策略 API分级 开发者生态 平台治理 核心竞争力 解决方案",
    {**_L3_META, "difficulty": "hard"},
)


# ---------------------------------------------------------------------------
# Build jobs
# ---------------------------------------------------------------------------


def build_claim_benchmark_v2_jobs() -> List[BatchJob]:
    """Return all 36 claim benchmark v2 jobs in canonical order."""
    return [
        # ── Layer 1: easy ────
        BatchJob(case=L1_EASY_A_CASE, grader=L1_EASY_A_GRADER),
        BatchJob(case=L1_EASY_B_CASE, grader=L1_EASY_B_GRADER),
        BatchJob(case=L1_EASY_C_CASE, grader=L1_EASY_C_GRADER),
        BatchJob(case=L1_EASY_D_CASE, grader=L1_EASY_D_GRADER),
        # ── Layer 1: medium ──
        BatchJob(case=L1_MEDIUM_A_CASE, grader=L1_MEDIUM_A_GRADER),
        BatchJob(case=L1_MEDIUM_B_CASE, grader=L1_MEDIUM_B_GRADER),
        BatchJob(case=L1_MEDIUM_C_CASE, grader=L1_MEDIUM_C_GRADER),
        BatchJob(case=L1_MEDIUM_D_CASE, grader=L1_MEDIUM_D_GRADER),
        # ── Layer 1: hard ────
        BatchJob(case=L1_HARD_A_CASE, grader=L1_HARD_A_GRADER),
        BatchJob(case=L1_HARD_B_CASE, grader=L1_HARD_B_GRADER),
        BatchJob(case=L1_HARD_C_CASE, grader=L1_HARD_C_GRADER),
        BatchJob(case=L1_HARD_D_CASE, grader=L1_HARD_D_GRADER),
        # ── Layer 2: easy ────
        BatchJob(case=L2_EASY_A_CASE, grader=L2_EASY_A_GRADER),
        BatchJob(case=L2_EASY_B_CASE, grader=L2_EASY_B_GRADER),
        BatchJob(case=L2_EASY_C_CASE, grader=L2_EASY_C_GRADER),
        BatchJob(case=L2_EASY_D_CASE, grader=L2_EASY_D_GRADER),
        # ── Layer 2: medium ──
        BatchJob(case=L2_MEDIUM_A_CASE, grader=L2_MEDIUM_A_GRADER),
        BatchJob(case=L2_MEDIUM_B_CASE, grader=L2_MEDIUM_B_GRADER),
        BatchJob(case=L2_MEDIUM_C_CASE, grader=L2_MEDIUM_C_GRADER),
        BatchJob(case=L2_MEDIUM_D_CASE, grader=L2_MEDIUM_D_GRADER),
        # ── Layer 2: hard ────
        BatchJob(case=L2_HARD_A_CASE, grader=L2_HARD_A_GRADER),
        BatchJob(case=L2_HARD_B_CASE, grader=L2_HARD_B_GRADER),
        BatchJob(case=L2_HARD_C_CASE, grader=L2_HARD_C_GRADER),
        BatchJob(case=L2_HARD_D_CASE, grader=L2_HARD_D_GRADER),
        # ── Layer 3: easy ────
        BatchJob(case=L3_EASY_A_CASE, grader=L3_EASY_A_GRADER),
        BatchJob(case=L3_EASY_B_CASE, grader=L3_EASY_B_GRADER),
        BatchJob(case=L3_EASY_C_CASE, grader=L3_EASY_C_GRADER),
        BatchJob(case=L3_EASY_D_CASE, grader=L3_EASY_D_GRADER),
        # ── Layer 3: medium ──
        BatchJob(case=L3_MEDIUM_A_CASE, grader=L3_MEDIUM_A_GRADER),
        BatchJob(case=L3_MEDIUM_B_CASE, grader=L3_MEDIUM_B_GRADER),
        BatchJob(case=L3_MEDIUM_C_CASE, grader=L3_MEDIUM_C_GRADER),
        BatchJob(case=L3_MEDIUM_D_CASE, grader=L3_MEDIUM_D_GRADER),
        # ── Layer 3: hard ────
        BatchJob(case=L3_HARD_A_CASE, grader=L3_HARD_A_GRADER),
        BatchJob(case=L3_HARD_B_CASE, grader=L3_HARD_B_GRADER),
        BatchJob(case=L3_HARD_C_CASE, grader=L3_HARD_C_GRADER),
        BatchJob(case=L3_HARD_D_CASE, grader=L3_HARD_D_GRADER),
    ]


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def run_claim_benchmark_v2(
    *,
    system_version: str = DEFAULT_SYSTEM_VERSION_V2,
    batch_id: str = DEFAULT_BATCH_ID_V2,
) -> BatchResult:
    """Execute the claim benchmark v2 suite end-to-end (36 cases).

    A fresh ``AdaptiveSkillSystem`` instance is created for each call so the
    seeded LTM call-count state resets correctly.
    """
    return run_batch(
        jobs=build_claim_benchmark_v2_jobs(),
        system=build_claim_benchmark_v2_system(),
        batch_id=batch_id,
        system_version=system_version,
        metadata={
            "suite": CLAIM_BENCHMARK_V2_SUITE_ID,
            "seed_mode": "in-memory-kb-ltm",
            "n_cases": 36,
            "layer_split": "L1:12 / L2:12 / L3:12",
            "difficulty_split": "easy:4 / medium:4 / hard:4 per layer",
            "note": "Expanded claim benchmark with difficulty stratification and new task domains.",
        },
    )
