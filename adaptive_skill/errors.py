"""Domain-specific exception hierarchy for adaptive_skill runtime."""

from __future__ import annotations


class AdaptiveSkillError(Exception):
    """Base exception for adaptive_skill runtime policy failures."""


class Layer2CompositionError(AdaptiveSkillError):
    """Base exception for Layer 2 composition failures."""


class Layer2CoverageError(Layer2CompositionError):
    """Raised when Layer 2 lacks enough real LTM support to compose safely."""

    def __init__(
        self,
        *,
        actual_coverage: float,
        minimum_coverage: float,
        framework_step_count: int,
        ltm_supported_count: int,
    ) -> None:
        self.actual_coverage = actual_coverage
        self.minimum_coverage = minimum_coverage
        self.framework_step_count = framework_step_count
        self.ltm_supported_count = ltm_supported_count
        super().__init__(
            "Layer 2 LTM coverage guard 拦截：覆盖度 "
            f"{actual_coverage:.1%} < 阈值 {minimum_coverage:.1%}。"
            f"框架 {framework_step_count} 步中仅 {ltm_supported_count} 步有 LTM 支持。"
            "请补充更多相关记忆，或降级到 Layer 3 自动生成。"
        )


class Layer3GenerationError(AdaptiveSkillError):
    """Base exception for Layer 3 generation failures."""


class Layer3QualityGateError(Layer3GenerationError):
    """Raised when a generated draft is blocked by the Layer 3 quality gate."""

    def __init__(self, *, confidence: float, quality_threshold: float) -> None:
        self.confidence = confidence
        self.quality_threshold = quality_threshold
        super().__init__(
            f"Layer 3 生成置信度 {confidence:.2f} 未达质量阈值 {quality_threshold:.2f}，"
            "Skill 已被质量门禁拦截，请检查生成上下文是否充分。"
        )
