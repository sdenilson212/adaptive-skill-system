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
from .generator import (
    SkillGenerator,
    OllamaSkillProvider,
    SkillGenerationProvider,
    ProviderRouter,
    ProviderHealthStatus,
)

from .thresholds import RuntimeThresholdPolicy, DEFAULT_THRESHOLD_POLICY

from .protocols import (

    TaskSpec,
    ContextSpec,
    DecisionTrace,
    ExecutionResult as ProtocolExecutionResult,
    task_spec_from_case,
    execution_result_from_solve_response,
    solve_task_with_protocol,
)


from .harness import (

    CaseSpec,
    GraderSpec,
    GradingOutput,
    RunResult,
    ReportBundle,
    WrittenReportBundle,
    build_report_bundle,
    build_report_data,
    render_html_report,
    render_markdown_report,
    write_report_bundle,
    run_case,
    normalize_response,
    grade,
    SUPPORTED_SEMANTIC_METHODS,
    DEFAULT_SENTENCE_TRANSFORMER_MODEL,
    normalize_semantic_text,
    compute_semantic_similarity,
)



# Alias for backward compatibility
SolveResult = SolveResponse

# 新增模块导出
from .adapters import (
    KBAdapter,
    FeishuKBAdapter,
    ConfluenceKBAdapter,
    NotionKBAdapter,
    GenericKBAdapter,
    MemoryKBAdapter,
    KBDocument,
    KBCredential,
    KBProvider,
    create_kb_adapter,
)

from .feedback import (
    FeedbackCollector,
    FeedbackEntry,
    FeedbackType,
    FeedbackStatus,
    FeedbackStorage,
    FeedbackAnalyzer,
)
from .observability import (
    MetricsCollector,
    DashboardData,
    AlertManager,
    MetricType,
    MetricEntry,
    SystemMetrics,
    LayerMetrics,
)
from .multi_tenant import (
    TenantContext,
    TenantManager,
    TenantIsolation,
    AccessControl,
    TenantConfig,
    Permission,
    Role,
)

__version__ = "1.2.0"

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
    "SkillGenerationProvider",
    "OllamaSkillProvider",
    "ProviderRouter",
    "ProviderHealthStatus",

    "RuntimeThresholdPolicy",
    "DEFAULT_THRESHOLD_POLICY",
    "TaskSpec",
    "DecisionTrace",

    "ContextSpec",

    "ProtocolExecutionResult",
    "task_spec_from_case",
    "execution_result_from_solve_response",
    "solve_task_with_protocol",
    "CaseSpec",


    "GraderSpec",
    "GradingOutput",
    "RunResult",
    "ReportBundle",
    "WrittenReportBundle",
    "build_report_data",
    "render_markdown_report",
    "render_html_report",
    "build_report_bundle",
    "write_report_bundle",
    "run_case",
    "normalize_response",
    "grade",
    "SUPPORTED_SEMANTIC_METHODS",
    "DEFAULT_SENTENCE_TRANSFORMER_MODEL",
    "normalize_semantic_text",
    "compute_semantic_similarity",
    
    # 知识库适配器
    "KBAdapter",
    "FeishuKBAdapter",
    "ConfluenceKBAdapter",
    "NotionKBAdapter",
    "GenericKBAdapter",
    "MemoryKBAdapter",
    "KBDocument",

    "KBCredential",
    "KBProvider",
    "create_kb_adapter",
    
    # 用户反馈
    "FeedbackCollector",
    "FeedbackEntry",
    "FeedbackType",
    "FeedbackStatus",
    "FeedbackStorage",
    "FeedbackAnalyzer",
    
    # 可观测性
    "MetricsCollector",
    "DashboardData",
    "AlertManager",
    "MetricType",
    "MetricEntry",
    "SystemMetrics",
    "LayerMetrics",
    
    # 多租户
    "TenantContext",
    "TenantManager",
    "TenantIsolation",
    "AccessControl",
    "TenantConfig",
    "Permission",
    "Role",
]



