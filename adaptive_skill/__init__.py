"""
Adaptive Skill System — 自适应 Skill 系统

三层递进架构，让 AI 能够在处理复杂问题时自动学习和进化：
  Layer 1: 直接命中 KB 缓存（< 1s）
  Layer 2: 从 LTM 组合生成新方案（10-30s）
  Layer 3: 自动生成全新 Skill（1-5min）

Usage:
    from adaptive_skill import AdaptiveSkillSystem, KBClient, LTMClient

    system = AdaptiveSkillSystem(kb_client=kb, ltm_client=ltm)
    result = system.solve("如何制定一份完整的运营策略？")
"""

from .core import (
    AdaptiveSkillSystem,
    Skill,
    SkillStep,
    SkillMetadata,
    SkillStatus,
    SkillType,
    SolveResult,
    SolveStatus,
    FeedbackSignal,
    KBClient,
    LTMClient,
)
from .evaluator import QualityEvaluator, QualityAssessment
from .composer import SkillComposer
from .generator import SkillGenerator

__version__ = "1.0.0"
__author__ = "sdenilson212"
__all__ = [
    "AdaptiveSkillSystem",
    "Skill",
    "SkillStep",
    "SkillMetadata",
    "SkillStatus",
    "SkillType",
    "SolveResult",
    "SolveStatus",
    "FeedbackSignal",
    "KBClient",
    "LTMClient",
    "QualityEvaluator",
    "QualityAssessment",
    "SkillComposer",
    "SkillGenerator",
]
