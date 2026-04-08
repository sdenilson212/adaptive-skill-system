"""
Skill 组合引擎 - Layer 2 实现
用于从 LTM 中搜索、评估和组合多个知识源来生成新 Skill
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import math
from datetime import datetime

from .errors import Layer2CoverageError
from .retrieval import (
    QueryVariant,
    build_query_variants,
    expand_query_terms,
    extract_query_terms,
    normalize_text,
    weighted_term_coverage,
)
from .thresholds import DEFAULT_THRESHOLD_POLICY, RuntimeThresholdPolicy






@dataclass
class LTMSearchResult:
    """LTM 搜索结果"""
    memory_id: str
    content: str
    category: str
    tags: List[str]
    relevance_score: float  # 0-1
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "category": self.category,
            "tags": self.tags,
            "relevance_score": self.relevance_score,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CompositionPlan:
    """Skill 组合计划"""
    base_framework: str  # 使用哪个基础框架
    components: List[Dict]  # 组成部分：[{"source": "记忆ID", "aspect": "价值主张"}]
    adaptation_strategy: Dict  # 适配策略
    estimated_quality: float  # 预计质量评分 0-1
    
    def to_dict(self) -> Dict:
        return {
            "base_framework": self.base_framework,
            "components": self.components,
            "adaptation_strategy": self.adaptation_strategy,
            "estimated_quality": self.estimated_quality
        }


class SkillComposer:
    """
    Skill 组合引擎
    负责从 LTM 中提取和组合信息来生成新 Skill
    """
    
    def __init__(
        self,
        ltm_client=None,
        kb_client=None,
        threshold_policy: RuntimeThresholdPolicy = DEFAULT_THRESHOLD_POLICY,
    ):
        self.ltm = ltm_client
        self.kb = kb_client
        self.threshold_policy = threshold_policy
        self.common_frameworks = {

            "business_planning": {
                "steps": ["市场分析", "竞争分析", "资源评估", "风险评估", "计划制定"],
                "inputs": ["业务目标", "市场信息"],
                "outputs": ["商业计划"]
            },
            "product_optimization": {
                "steps": ["需求分析", "用户研究", "设计迭代", "测试验证", "发布"],
                "inputs": ["产品信息", "用户数据"],
                "outputs": ["优化方案"]
            },
            "marketing_strategy": {
                "steps": ["目标定位", "渠道选择", "内容制定", "预算分配", "效果评估"],
                "inputs": ["产品特征", "目标人群"],
                "outputs": ["营销策略"]
            },
            "supply_chain_management": {
                "steps": ["需求预测", "采购计划", "库存管控", "安全库存", "多源采购"],
                "inputs": ["供应链目标", "风险场景"],
                "outputs": ["供应链管理方案"]
            },
            "problem_solving": {
                "steps": ["问题定义", "原因分析", "方案设计", "方案评估", "执行计划"],
                "inputs": ["问题描述"],
                "outputs": ["解决方案"]
            }
        }

    
    def analyze_problem(self, problem: str) -> Dict:
        """
        分析问题的特征，识别最适合的框架
        
        Args:
            problem: 问题描述
        
        Returns:
            问题分析结果
        """
        analysis = {
            "problem_type": self._classify_problem(problem),
            "keywords": self._extract_keywords(problem),
            "required_expertise": self._identify_expertise(problem),
            "complexity_level": self._assess_complexity(problem)
        }
        return analysis
    
    def search_ltm(self, problem: str, keywords: List[str], max_results: int = 10) -> List[LTMSearchResult]:
        """
        从 LTM 中搜索相关信息。

        改进点：
        1. 用 full query + semantic core + keyword rewrite 做多路召回
        2. 按 memory_id 聚合命中，而不是只保留单次最高分
        3. 对被多条 query 一致命中的记忆给少量融合加成，降低单点偶然命中的噪声
        """
        if not self.ltm:
            return []

        query_terms = self._merge_query_terms(problem, keywords)
        query_variants = self._build_search_variants(problem, query_terms)
        best_hits: Dict[str, Dict[str, Any]] = {}

        for variant in query_variants:
            ltm_results = self.ltm.recall(query=variant.query)
            if isinstance(ltm_results, dict):
                continue
            if not isinstance(ltm_results, list):
                continue

            for rank, ltm_item in enumerate(ltm_results):
                base_relevance = self._calculate_relevance(
                    ltm_item,
                    problem,
                    query_terms=query_terms,
                    query_used=variant.query,
                )
                fused_hit_score = self._score_query_hit(base_relevance, variant, rank)
                memory_id = ltm_item.get("id", "unknown")
                candidate = LTMSearchResult(
                    memory_id=memory_id,
                    content=ltm_item.get("content", ""),
                    category=ltm_item.get("category", "general"),
                    tags=ltm_item.get("tags", []),
                    relevance_score=base_relevance,
                    timestamp=datetime.now(),
                )

                bucket = best_hits.get(memory_id)
                if bucket is None:
                    best_hits[memory_id] = {
                        "candidate": candidate,
                        "scores": [fused_hit_score],
                        "best_base_relevance": base_relevance,
                    }
                    continue

                bucket["scores"].append(fused_hit_score)
                if base_relevance > bucket["best_base_relevance"]:
                    bucket["candidate"] = candidate
                    bucket["best_base_relevance"] = base_relevance

        results: List[LTMSearchResult] = []
        for bucket in best_hits.values():
            candidate = bucket["candidate"]
            candidate.relevance_score = self._fuse_ranked_scores(bucket["scores"])
            results.append(candidate)

        results.sort(key=lambda item: item.relevance_score, reverse=True)
        return results[:max_results]


    
    def assess_composability(self, ltm_results: List[LTMSearchResult], problem: str) -> Tuple[bool, Dict]:
        """
        评估是否能从这些 LTM 结果中组合出 Skill
        
        Args:
            ltm_results: LTM 搜索结果
            problem: 原始问题
        
        Returns:
            (能否组合, 评估信息)
        """
        if not ltm_results:
            return False, {"reason": "No relevant information found"}
        
        # 计算覆盖度
        coverage = self._calculate_coverage(ltm_results, problem)
        
        # 计算多样性（确保信息来自不同维度）
        diversity = self._calculate_diversity(ltm_results)
        
        # 计算整体可组合性
        composability_score = 0.6 * coverage + 0.4 * diversity

        can_compose = self.threshold_policy.layer2_allows_composition(composability_score)

        
        return can_compose, {
            "coverage_score": coverage,
            "diversity_score": diversity,
            "composability_score": composability_score,
            "info_count": len(ltm_results),
            "avg_relevance": sum(r.relevance_score for r in ltm_results) / len(ltm_results)
        }
    
    def create_composition_plan(self, problem: str, ltm_results: List[LTMSearchResult],
                               problem_analysis: Dict) -> CompositionPlan:
        """
        创建组合计划

        Args:
            problem: 问题
            ltm_results: LTM 搜索结果
            problem_analysis: 问题分析结果

        Returns:
            CompositionPlan

        Raises:
            Layer2CoverageError: 当 LTM 覆盖度不足以支撑组合时抛出（P0-3 防护）

        """
        # 选择最适合的框架
        framework_name = self._select_framework(problem_analysis)
        base_framework = self.common_frameworks.get(framework_name)

        if not base_framework:
            framework_name = "problem_solving"
            base_framework = self.common_frameworks[framework_name]

        # ---- P0-3 前置检查：graded LTM coverage guard ----
        # 防止"框架空降"：不用二元阈值去数 memory 条数，而是把每条 LTM 的相关性
        # 折算成 0-1 的 step-equivalent support，再和框架步数比较。
        framework_step_count = len(base_framework["steps"])
        step_support_threshold = max(self.threshold_policy.layer2_step_relevance_threshold, 1e-6)
        ltm_support_units = sum(
            min(1.0, max(float(r.relevance_score), 0.0) / step_support_threshold)
            for r in ltm_results
        )
        ltm_supported_count = sum(1 for r in ltm_results if r.relevance_score > 0)
        actual_coverage = ltm_support_units / framework_step_count if framework_step_count > 0 else 0.0

        if actual_coverage < self.threshold_policy.layer2_min_ltm_coverage:
            raise Layer2CoverageError(
                actual_coverage=actual_coverage,
                minimum_coverage=self.threshold_policy.layer2_min_ltm_coverage,
                framework_step_count=framework_step_count,
                ltm_supported_count=ltm_supported_count,
            )




        # ---- 步骤填充（现在已知 LTM 覆盖度足够） ----
        components = []
        for i, step in enumerate(base_framework["steps"]):
            # 找最相关的 LTM 信息
            relevant_ltm = self._match_ltm_to_step(step, ltm_results)
            if relevant_ltm:
                components.append({
                    "step": step,
                    "source": relevant_ltm.memory_id,
                    "aspect": relevant_ltm.tags[0] if relevant_ltm.tags else "general",
                    "relevance": relevant_ltm.relevance_score,
                    "source_type": "ltm",
                })
            else:
                # 框架填充只在覆盖度检查通过后才发生，且记录清楚
                components.append({
                    "step": step,
                    "source": "framework",
                    "aspect": "template",
                    "relevance": self.threshold_policy.layer2_framework_fallback_relevance,
                    "source_type": "framework_fallback",  # 标记为后备来源
                })


        # 制定适配策略
        adaptation_strategy = self._create_adaptation_strategy(
            framework_name,
            problem_analysis,
            components
        )

        # 估计质量（已知覆盖度足够，质量应合理）
        estimated_quality = self._estimate_composition_quality(components, ltm_results)

        # 超过 50% 框架填充时发出警告（降至警告而非硬拦截，因为 guard 已前置）
        framework_fallback_count = sum(1 for c in components if c["source_type"] == "framework_fallback")
        if self.threshold_policy.layer2_should_warn_framework_majority(
            framework_fallback_count,
            len(components),
        ):
            adaptation_strategy["warnings"] = adaptation_strategy.get("warnings", [])
            adaptation_strategy["warnings"].append(
                f"⚠️ {framework_fallback_count}/{len(components)} 步骤来自框架后备，"
                f"最终质量可能受影响。建议后续补充相关 LTM 记忆。"
            )
            estimated_quality -= self.threshold_policy.layer2_framework_majority_quality_penalty



        return CompositionPlan(
            base_framework=framework_name,
            components=components,
            adaptation_strategy=adaptation_strategy,
            estimated_quality=max(estimated_quality, 0.0),
        )
    
    # ==================== 私有方法 ====================
    
    def _classify_problem(self, problem: str) -> str:
        """分类问题类型"""
        problem_lower = problem.lower()
        
        if any(word in problem_lower for word in ["供应链", "库存", "采购", "断供", "供应商"]):
            return "supply_chain_management"
        if any(word in problem_lower for word in ["商业", "business", "plan", "计划", "策略"]):
            return "business_planning"
        elif any(word in problem_lower for word in ["产品", "product", "优化", "design"]):
            return "product_optimization"
        elif any(word in problem_lower for word in ["营销", "marketing", "推广", "宣传"]):
            return "marketing_strategy"
        else:
            return "problem_solving"

    
    def _extract_keywords(self, problem: str) -> List[str]:
        """从问题中提取关键词，和 Layer 1 使用同一套 query rewrite / term expansion。"""
        return expand_query_terms(problem, max_terms=8)

    def _merge_query_terms(self, problem: str, keywords: List[str]) -> List[str]:
        merged: List[str] = []
        for term in list(keywords or []) + expand_query_terms(problem, max_terms=12):
            cleaned = str(term or "").strip()
            if cleaned and cleaned not in merged:
                merged.append(cleaned)
        return merged

    def _build_search_variants(self, problem: str, query_terms: List[str]) -> List[QueryVariant]:
        variants = build_query_variants(problem, max_terms=6, max_variants=6)
        existing = {normalize_text(item.query) for item in variants}
        for term in query_terms[:4]:
            normalized = normalize_text(term)
            if not normalized or normalized in existing:
                continue
            variants.append(QueryVariant(query=term, weight=0.68, source="seed_keyword"))
            existing.add(normalized)
        return variants

    def _score_query_hit(self, base_relevance: float, variant: QueryVariant, rank: int) -> float:
        rank_bonus = max(0.0, 0.08 - 0.01 * rank)
        return min(1.0, base_relevance * max(0.2, variant.weight) + rank_bonus)

    def _fuse_ranked_scores(self, scores: List[float]) -> float:
        if not scores:
            return 0.0
        ordered = sorted(scores, reverse=True)
        fused = ordered[0]
        for idx, score in enumerate(ordered[1:], start=1):
            fused += score * (0.30 / idx)
        fused += min(0.03 * (len(ordered) - 1), 0.12)
        return min(fused, 1.0)

    def _identify_expertise(self, problem: str) -> List[str]:

        """识别所需的专业领域"""
        problem_lower = problem.lower()
        expertise = []
        
        expertise_map = {
            "psychology": ["心理学", "用户", "行为", "motivation"],
            "data_analysis": ["数据", "分析", "统计", "metrics"],
            "finance": ["预算", "成本", "ROI", "财务"],
            "distribution": ["渠道", "发行", "delivery"],
            "product": ["产品", "特征", "功能"]
        }
        
        for domain, keywords in expertise_map.items():
            if any(keyword in problem_lower for keyword in keywords):
                expertise.append(domain)
        
        return expertise
    
    def _assess_complexity(self, problem: str) -> str:
        """评估问题复杂度"""
        problem_len = len(problem)
        keyword_count = len(self._extract_keywords(problem))
        
        if problem_len < 50:
            return "low"
        elif problem_len < 200 and keyword_count <= 5:
            return "medium"
        else:
            return "high"
    
    def _calculate_relevance(
        self,
        ltm_item: Dict,
        problem: str,
        query_terms: List[str],
        query_used: Optional[str] = None,
    ) -> float:
        """计算 LTM 项与问题的相关性。"""
        content = ltm_item.get("content", "")
        tags = " ".join(ltm_item.get("tags", []))
        category = ltm_item.get("category", "")
        query_specific_terms = expand_query_terms(query_used or "", max_terms=6) or query_terms


        content_score = max(
            weighted_term_coverage(content, query_terms),
            weighted_term_coverage(content, query_specific_terms),
        )
        tag_score = max(
            weighted_term_coverage(tags, query_terms),
            weighted_term_coverage(tags, query_specific_terms),
        )
        category_score = 1.0 if category in ["discussion", "insight", "method"] else 0.4

        score = 0.50 * content_score + 0.30 * tag_score + 0.15 * category_score + 0.05

        problem_normalized = normalize_text(problem)
        combined = normalize_text(f"{content} {tags}")
        if problem_normalized and problem_normalized in combined:
            score += 0.10
        elif query_used and normalize_text(query_used) in combined:
            score += 0.10

        return min(score, 1.0)


    
    def _calculate_coverage(self, ltm_results: List[LTMSearchResult], problem: str) -> float:
        """计算信息覆盖度。"""
        if not ltm_results:
            return 0.0

        high_relevance_threshold = max(self.threshold_policy.layer2_high_relevance_threshold, 1e-6)
        support_units = [
            min(1.0, max(float(result.relevance_score), 0.0) / high_relevance_threshold)
            for result in ltm_results
        ]
        return sum(support_units) / len(support_units)

    
    def _calculate_diversity(self, ltm_results: List[LTMSearchResult]) -> float:
        """计算信息多样性（来自不同维度）"""
        if not ltm_results:
            return 0.0
        
        # 统计不同的标签和分类
        all_tags = set()
        categories = set()
        
        for result in ltm_results:
            all_tags.update(result.tags)
            categories.add(result.category)
        
        # 多样性 = (不同标签 + 不同分类) / (总记忆数 * 2)
        diversity = (len(all_tags) + len(categories)) / (len(ltm_results) * 2)
        
        return min(diversity, 1.0)
    
    def _select_framework(self, problem_analysis: Dict) -> str:
        """根据问题分析选择最适合的框架"""
        problem_type = problem_analysis.get("problem_type", "problem_solving")
        
        if problem_type in self.common_frameworks:
            return problem_type
        else:
            return "problem_solving"
    
    def _match_ltm_to_step(self, step: str, ltm_results: List[LTMSearchResult]) -> Optional[LTMSearchResult]:
        """将 LTM 信息匹配到步骤。"""
        best_match = None
        best_score = 0.0
        step_terms = [step] + expand_query_terms(step, max_terms=4)
        normalized_step = normalize_text(step)

        for ltm_result in ltm_results:
            searchable = f"{ltm_result.content} {' '.join(ltm_result.tags)}"
            normalized_searchable = normalize_text(searchable)
            exact_bonus = 0.45 if normalized_step and normalized_step in normalized_searchable else 0.0
            semantic_overlap = weighted_term_coverage(searchable, step_terms)
            score = min(1.0, 0.65 * semantic_overlap + exact_bonus)
            score *= ltm_result.relevance_score  # 乘以整体相关性

            if score > best_score:
                best_score = score
                best_match = ltm_result

        return best_match if self.threshold_policy.layer2_step_match_passes(best_score) else None


    
    def _create_adaptation_strategy(self, framework_name: str, 
                                    problem_analysis: Dict, 
                                    components: List[Dict]) -> Dict:
        """创建适配策略"""
        framework_steps = sum(1 for c in components if c["source"] == "framework")
        strategy = {
            "framework": framework_name,
            "customizations": [],
            "warnings": [],
            "confidence": self.threshold_policy.layer2_adaptation_confidence(
                complexity_level=problem_analysis.get("complexity_level", "medium"),
                framework_steps=framework_steps,
                total_steps=len(components),
            ),
        }

        # 根据问题复杂度调整
        if problem_analysis.get("complexity_level") == "high":
            strategy["customizations"].append("增加验证步骤")

        # 根据所需专业领域调整
        expertise = problem_analysis.get("required_expertise", [])
        for exp in expertise:
            strategy["customizations"].append(f"加强 {exp} 分析")

        # 检查是否有来自框架的步骤（可能质量较低）
        if self.threshold_policy.layer2_should_warn_framework_majority(framework_steps, len(components)):
            strategy["warnings"].append("超过50%的步骤来自框架模板，质量可能不够高")

        return strategy

    
    def _estimate_composition_quality(self, components: List[Dict], 
                                      ltm_results: List[LTMSearchResult]) -> float:
        """估计组合质量"""
        if not components:
            return 0.0
        
        # 计算平均相关性
        relevances = [c.get("relevance", 0.5) for c in components]
        avg_relevance = sum(relevances) / len(relevances)
        
        # 计算 LTM 支持度（有多少步骤有 LTM 支持）
        ltm_supported = sum(1 for c in components if c["source"] != "framework")
        ltm_support_ratio = ltm_supported / len(components)
        
        # 综合评分
        quality = 0.6 * avg_relevance + 0.4 * ltm_support_ratio
        
        return min(quality, 1.0)
