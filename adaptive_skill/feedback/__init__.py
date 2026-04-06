"""
用户反馈闭环模块

提供收集、存储、分析用户反馈的能力：
- FeedbackCollector: 收集点赞/点踩、人工标注、修正建议
- FeedbackStorage: 持久化反馈数据
- FeedbackAnalyzer: 分析反馈趋势，生成优化建议
"""

from .collector import (
    FeedbackCollector,
    FeedbackEntry,
    FeedbackType,
    FeedbackStatus,
    FeedbackStorage,
    FeedbackAnalyzer,
)

__all__ = [
    "FeedbackCollector",
    "FeedbackEntry",
    "FeedbackType",
    "FeedbackStatus",
    "FeedbackStorage",
    "FeedbackAnalyzer",
]
