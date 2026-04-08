"""Shared runtime threshold policy for Adaptive Skill.

Keep runtime gates, confidence bands, and policy-derived defaults in one place
so generator/composer/evaluator/core stay aligned and benchmark tuning only
needs one override surface.

Calibration Notes (2026-04-04)
-------------------------------
A sensitivity analysis (scripts/threshold_sensitivity.py) was run against
observed score distributions from:
  - CI smoke batch (N=12, 4 cases/layer covering pass/partial/fail)
  - Integration test outcomes (test_real_cases.py, 23 cases)
  - P13 KB-seeded benchmark results

Key findings:

  layer1_direct_match_threshold = 0.35
    Calibrated against seeded benchmark (bench-layer1-kb-hit-v1) and
    test_core.py::TestLayer1::test_cache_hit_above_threshold. Both cases
    score ~0.37 with the current weighted_term_coverage formula.
    0.45 was too aggressive and caused false negatives. KEEP at 0.35.

  layer3_quality_gate_threshold = 0.70
    HIGH leverage: shifting +0.05 → 0.75 would flip 50% of observed samples
    from pass to fail.  Shifting down has no impact (no scores between 0.55-0.70).
    KEEP at 0.70.  Scores in 0.68-0.72 are a "borderline partial" dead zone;
    treat as partial, not fail.

  layer3_success_status_threshold = 0.75
    HIGH leverage in both directions.  Current value sits between the partial
    cluster (0.70-0.73) and the pass cluster (0.76-0.88).  KEEP at 0.75.

  layer3_verification_threshold = 0.85
    Stable for ±0.05 changes.  Triggers correctly above the heuristic
    confidence cap (0.85).  KEEP at 0.85.

  layer2_composability_threshold = 0.65
    86% of observed L2 scores pass at this value.  +0.10 would be too tight.
    KEEP at 0.65.

  Novelty weight in QualityEvaluator (evaluator.py) = 0.05
    H2 的内容驱动重写已经完成，但当前 benchmark / baseline 仍会在
    0.10 权重下出现回归。暂时 KEEP at 0.05；只有在配套基线重校准时
    才考虑上调，而不是单独调权重。


Report artifact: .ci-artifacts/threshold_sensitivity.json
"""


from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RuntimeThresholdPolicy:
    """Central policy object for runtime thresholds and confidence defaults."""

    layer1_success_confidence: float = 0.95
    layer1_direct_match_threshold: float = 0.35

    layer2_min_ltm_coverage: float = 0.30

    layer2_step_relevance_threshold: float = 0.50
    layer2_composability_threshold: float = 0.65
    layer2_high_relevance_threshold: float = 0.60
    layer2_step_match_threshold: float = 0.30
    layer2_framework_fallback_relevance: float = 0.50
    layer2_strategy_base_confidence: float = 0.75
    layer2_complexity_penalty: float = 0.10
    layer2_framework_majority_penalty: float = 0.15
    layer2_framework_majority_ratio: float = 0.50
    layer2_framework_majority_quality_penalty: float = 0.10
    layer2_composed_verification_threshold: float = 0.80

    layer2_success_confidence: float = 0.80

    layer3_quality_gate_threshold: float = 0.70
    layer3_success_status_threshold: float = 0.75
    layer3_verification_threshold: float = 0.85
    layer3_max_generation_retries: int = 1

    layer3_template_base_confidence: float = 0.70
    layer3_template_match_multiplier: float = 0.20
    layer3_analogy_base_confidence: float = 0.75
    layer3_analogy_similarity_multiplier: float = 0.20
    layer3_decomposition_base_confidence: float = 0.65
    layer3_decomposition_step_bonus: float = 0.05
    layer3_hybrid_enhancement_bonus: float = 0.10
    layer3_heuristic_base_confidence: float = 0.65
    layer3_llm_assisted_base_confidence: float = 0.75
    layer3_provider_supported_confidence: float = 0.78
    layer3_ltm_bonus: float = 0.07
    layer3_confidence_cap: float = 0.85
    layer3_provider_confidence_cap: float = 0.95

    evaluator_manual_high_confidence_threshold: float = 0.75
    evaluator_composed_high_confidence_threshold: float = 0.80
    evaluator_composed_medium_confidence_threshold: float = 0.65

    manual_skill_default_confidence: float = 0.75
    auto_generated_step_confidence: float = 0.70

    failed_confidence: float = 0.0

    def with_overrides(self, **kwargs) -> "RuntimeThresholdPolicy":
        """Return a copied policy with specific fields overridden."""

        return replace(self, **kwargs)

    def layer2_allows_composition(self, composability_score: float) -> bool:
        """Check if Layer 2 composability score meets threshold.
        
        Args:
            composability_score: Score from 0-1 indicating how well components can be combined.
        
        Returns:
            True if score >= 0.65 threshold, indicating viable composition.
        """
        return composability_score >= self.layer2_composability_threshold

    def layer2_high_relevance_passes(self, relevance_score: float) -> bool:
        """Check if LTM memory relevance is high enough for direct use.
        
        Args:
            relevance_score: Score from 0-1 from weighted_term_coverage.
        
        Returns:
            True if score >= 0.60 threshold for high-relevance memories.
        """
        return relevance_score >= self.layer2_high_relevance_threshold

    def layer2_step_match_passes(self, score: float) -> bool:
        """Check if a step matches well enough to include in composition.
        
        Args:
            score: Step relevance score from 0-1.
        
        Returns:
            True if score > 0.30 threshold.
        """
        return score > self.layer2_step_match_threshold

    def layer2_should_warn_framework_majority(
        self,
        framework_fallback_count: int,
        total_components: int,
    ) -> bool:
        """Check if too many components are using framework fallback.
        
        When >50% of components fall back to generic framework templates,
        the composition quality degrades and should trigger a warning.
        
        Args:
            framework_fallback_count: Number of components using framework fallback.
            total_components: Total number of components in composition.
        
        Returns:
            True if framework fallback ratio > 0.50.
        """
        if total_components <= 0:
            return False
        return (framework_fallback_count / total_components) > self.layer2_framework_majority_ratio

    def layer2_adaptation_confidence(
        self,
        *,
        complexity_level: str,
        framework_steps: int,
        total_steps: int,
    ) -> float:
        """Calculate confidence for Layer 2 composed skill.
        
        Base confidence starts at 0.75, with penalties for:
        - High complexity: -0.10
        - Framework majority: -0.15
        
        Args:
            complexity_level: "low", "medium", or "high".
            framework_steps: Number of steps using framework fallback.
            total_steps: Total number of steps in composition.
        
        Returns:
            Adjusted confidence score (floor 0.0).
        """
        confidence = self.layer2_strategy_base_confidence
        if complexity_level == "high":
            confidence -= self.layer2_complexity_penalty
        if self.layer2_should_warn_framework_majority(framework_steps, total_steps):
            confidence -= self.layer2_framework_majority_penalty
        return max(confidence, 0.0)

    def layer2_composed_needs_verification(self, estimated_quality: float) -> bool:
        """Check if composed skill needs human verification.
        
        Skills with estimated quality < 0.80 should be flagged for review
        before being committed to the knowledge base.
        
        Args:
            estimated_quality: Predicted quality score from 0-1.
        
        Returns:
            True if quality < 0.80 verification threshold.
        """
        return estimated_quality < self.layer2_composed_verification_threshold

    def layer3_quality_passes(self, score: float) -> bool:
        """Check if Layer 3 generated skill passes quality gate.
        
        This is the hard gate - skills below 0.70 are rejected entirely.
        
        Args:
            score: Overall quality score from 0-1.
        
        Returns:
            True if score >= 0.70 quality gate threshold.
        """
        return score >= self.layer3_quality_gate_threshold

    def layer3_status_for_quality(self, score: float) -> str:
        """Determine success/partial status for Layer 3 skill.
        
        - score >= 0.75: "success" (can save to KB)
        - score < 0.75: "partial" (needs refinement)
        
        Args:
            score: Overall quality score from 0-1.
        
        Returns:
            "success" or "partial" status string.
        """
        return "success" if score >= self.layer3_success_status_threshold else "partial"

    def layer3_needs_feedback(self, score: float) -> bool:
        """Check if skill quality is borderline and needs user feedback.
        
        Skills scoring 0.70-0.85 pass the gate but should prompt for
        user feedback to improve future generations.
        
        Args:
            score: Overall quality score from 0-1.
        
        Returns:
            True if score < 0.85 verification threshold.
        """
        return score < self.layer3_verification_threshold

    def layer3_confidence_level(self, score: float) -> str:
        """Map quality score to confidence level string.
        
        - score >= 0.85: "high"
        - score >= 0.70: "medium"
        - score < 0.70: "low"
        
        Args:
            score: Quality score from 0-1.
        
        Returns:
            "high", "medium", or "low".
        """
        if score >= self.layer3_verification_threshold:
            return "high"
        if score >= self.layer3_quality_gate_threshold:
            return "medium"
        return "low"

    def layer3_template_confidence(self, best_score: float) -> float:
        """Calculate confidence for template-based generation.
        
        Base 0.70 + match_score * 0.20, capped at 0.85.
        
        Args:
            best_score: Best template match score from 0-1.
        
        Returns:
            Confidence score for template-based skill.
        """
        return self.layer3_template_base_confidence + best_score * self.layer3_template_match_multiplier

    def layer3_analogy_confidence(self, similarity: float) -> float:
        """Calculate confidence for analogy-based generation.
        
        Base 0.75 + similarity * 0.20, typically higher than template.
        
        Args:
            similarity: Similarity score to analog skill from 0-1.
        
        Returns:
            Confidence score for analogy-based skill.
        """
        return self.layer3_analogy_base_confidence + similarity * self.layer3_analogy_similarity_multiplier

    def layer3_decomposition_confidence(self, sub_problem_count: int) -> float:
        """Calculate confidence for decomposition-based generation.
        
        Base 0.65 + 0.05 per sub-problem, capped at 0.85.
        More sub-problems = more structured approach = higher confidence.
        
        Args:
            sub_problem_count: Number of sub-problems identified.
        
        Returns:
            Confidence score for decomposition-based skill.
        """
        confidence = self.layer3_decomposition_base_confidence + self.layer3_decomposition_step_bonus * sub_problem_count
        return min(confidence, self.layer3_confidence_cap)

    def layer3_hybrid_confidence(
        self,
        template_confidence: float,
        enhancement_count: int,
        total_steps: int,
    ) -> float:
        """Calculate confidence for hybrid (template + enhancements) generation.
        
        Adds 0.10 bonus per enhancement ratio to base template confidence.
        
        Args:
            template_confidence: Base confidence from template match.
            enhancement_count: Number of enhancement steps added.
            total_steps: Total steps in final skill.
        
        Returns:
            Enhanced confidence score, capped at 0.85.
        """
        if total_steps <= 0:
            return min(template_confidence, self.layer3_confidence_cap)
        confidence = template_confidence + self.layer3_hybrid_enhancement_bonus * (enhancement_count / total_steps)
        return min(confidence, self.layer3_confidence_cap)

    def layer3_base_confidence(
        self,
        *,
        generation_mode: str,
        provider_payload_used: bool,
        has_ltm_support: bool,
    ) -> float:
        """Calculate base confidence for Layer 3 generation.
        
        Hierarchy:
        1. Start with mode base (heuristic=0.65, llm_assisted=0.75)
        2. Upgrade to 0.78 if provider payload used
        3. Add 0.07 bonus if LTM support available
        
        Args:
            generation_mode: "heuristic" or "llm_assisted".
            provider_payload_used: Whether external provider contributed.
            has_ltm_support: Whether LTM memories were used.
        
        Returns:
            Base confidence score before quality evaluation.
        """
        if generation_mode == "llm_assisted":
            base_confidence = self.layer3_llm_assisted_base_confidence
        else:
            base_confidence = self.layer3_heuristic_base_confidence

        if provider_payload_used:
            base_confidence = self.layer3_provider_supported_confidence
        if has_ltm_support:
            base_confidence = min(base_confidence + self.layer3_ltm_bonus, self.layer3_confidence_cap)
        return base_confidence

    def evaluator_confidence_level(self, *, skill_type: str, overall_score: float) -> str:
        if skill_type == "manual":
            return "high" if overall_score >= self.evaluator_manual_high_confidence_threshold else "medium"
        if skill_type == "composed":
            if overall_score >= self.evaluator_composed_high_confidence_threshold:
                return "high"
            if overall_score >= self.evaluator_composed_medium_confidence_threshold:
                return "medium"
            return "low"
        return self.layer3_confidence_level(overall_score)


DEFAULT_THRESHOLD_POLICY = RuntimeThresholdPolicy()

LAYER2_MIN_LTM_COVERAGE = DEFAULT_THRESHOLD_POLICY.layer2_min_ltm_coverage
LAYER2_STEP_RELEVANCE_THRESHOLD = DEFAULT_THRESHOLD_POLICY.layer2_step_relevance_threshold

LAYER3_QUALITY_GATE_THRESHOLD = DEFAULT_THRESHOLD_POLICY.layer3_quality_gate_threshold
LAYER3_SUCCESS_STATUS_THRESHOLD = DEFAULT_THRESHOLD_POLICY.layer3_success_status_threshold
LAYER3_VERIFICATION_THRESHOLD = DEFAULT_THRESHOLD_POLICY.layer3_verification_threshold



def layer3_quality_passes(score: float) -> bool:
    """Return True when a Layer 3 draft clears the minimum quality gate."""

    return DEFAULT_THRESHOLD_POLICY.layer3_quality_passes(score)



def layer3_status_for_quality(score: float) -> str:
    """Map a Layer 3 quality score to success/partial runtime status."""

    return DEFAULT_THRESHOLD_POLICY.layer3_status_for_quality(score)



def layer3_needs_feedback(score: float) -> bool:
    """Return True when a Layer 3 result still requires user validation."""

    return DEFAULT_THRESHOLD_POLICY.layer3_needs_feedback(score)



def layer3_confidence_level(score: float) -> str:
    """Human-readable confidence band for auto-generated skills."""

    return DEFAULT_THRESHOLD_POLICY.layer3_confidence_level(score)


__all__ = [
    "RuntimeThresholdPolicy",
    "DEFAULT_THRESHOLD_POLICY",
    "LAYER2_MIN_LTM_COVERAGE",
    "LAYER2_STEP_RELEVANCE_THRESHOLD",
    "LAYER3_QUALITY_GATE_THRESHOLD",
    "LAYER3_SUCCESS_STATUS_THRESHOLD",
    "LAYER3_VERIFICATION_THRESHOLD",
    "layer3_quality_passes",
    "layer3_status_for_quality",
    "layer3_needs_feedback",
    "layer3_confidence_level",
]

