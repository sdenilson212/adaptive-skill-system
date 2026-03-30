"""
Adaptive Skill System — 自适应 Skill 系统

三层递进架构，让 AI 能够在处理复杂问题时自动学习和进化：
  Layer 1: 直接命中 KB 缓存（< 1s）
  Layer 2: 从 LTM 组合生成新方案（10-30s）
  Layer 3: 自动生成全新 Skill（1-5min）

Usage:
    from adaptive_skill import AdaptiveSkillSystem

    system = AdaptiveSkillSystem()
    result = system.solve("如何制定一份完整的运营策略？")
"""

from .core import (
    AdaptiveSkillSystem,
    Skill,
    SkillStep,
    SkillMetadata,
    SkillStatus,
    SkillType,
    SolveResponse,      # 实际类名（原代码写错为 SolveResult）
    ExecutionResult,
    SkillExecutor,
    GenerationInfo,
    QualityMetrics,
)
from .evaluator import QualityEvaluator, QualityAssessment
from .composer import SkillComposer
from .generator import SkillGenerator

# Alias for backward compatibility
SolveResult = SolveResponse

__version__ = "1.0.1"
__author__ = "sdenilson212"
__all__ = [
    "AdaptiveSkillSystem",
    "Skill",
    "SkillStep",
    "SkillMetadata",
    "SkillStatus",
    "SkillType",
    "SolveResponse",
    "SolveResult",      # alias -> SolveResponse
    "ExecutionResult",
    "SkillExecutor",
    "GenerationInfo",
    "QualityMetrics",
    "QualityEvaluator",
    "QualityAssessment",
    "SkillComposer",
    "SkillGenerator",
]
