"""Evaluation harness package for Adaptive Skill System.

P0: single-case contract (specs, validator, grader_runtime, single_case)
P1: real fixtures + extended grader types
P2: batch runner + persistence sinks
P3: metrics, baseline store, regression detection
P4: report generation (JSON / Markdown / HTML)
"""

from .baseline import BaselineRecord, BaselineStore
from .batch_runner import BatchJob, BatchResult, BatchSummary, run_batch
from .grader_runtime import grade
from .metrics import BatchMetrics, CaseMetrics, compute_metrics
from .semantic_grader import (
    DEFAULT_SENTENCE_TRANSFORMER_MODEL,
    SUPPORTED_SEMANTIC_METHODS,
    compute_semantic_similarity,
    normalize_semantic_text,
)
from .reporting import (

    ReportBundle,
    WrittenReportBundle,
    build_report_bundle,
    build_report_data,
    render_html_report,
    render_markdown_report,
    write_report_bundle,
)
from .regression import (

    RegressionFinding,
    RegressionReport,
    RegressionThresholds,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    check_regression,
    check_regression_from_store,
)
from .single_case import normalize_response, run_case
from .sinks import InMemorySink, JsonlSink, JsonSink
from .specs import CaseSpec, GraderSpec, GradingOutput, RunResult
from .validator import (
    CASE_GRADER_MISMATCH,
    CASE_INVALID,
    GRADER_INVALID,
    GRADER_RUNTIME_ERROR,
    HARNESS_RUNTIME_ERROR,
    RESULT_PERSIST_FAILED,
    SOLVER_EXECUTION_FAILED,
    BindingValidationError,
    GraderValidationError,
    HarnessError,
    HarnessValidationError,
    PersistenceError,
    validate_binding,
    validate_case,
    validate_grader,
)

__all__ = [
    # Specs
    "CaseSpec",
    "GraderSpec",
    "GradingOutput",
    "RunResult",
    # Single-case
    "grade",
    "run_case",
    "normalize_response",
    # Batch runner (P2)
    "BatchJob",
    "BatchSummary",
    "BatchResult",
    "run_batch",
    # Sinks (P2)
    "InMemorySink",
    "JsonlSink",
    "JsonSink",
    # Metrics (P3)
    "CaseMetrics",
    "BatchMetrics",
    "compute_metrics",
    # Baseline (P3)
    "BaselineRecord",
    "BaselineStore",
    # Reporting (P4)
    "ReportBundle",
    "WrittenReportBundle",
    "build_report_data",
    "render_markdown_report",
    "render_html_report",
    "build_report_bundle",
    "write_report_bundle",
    # Semantic grader helpers
    "SUPPORTED_SEMANTIC_METHODS",
    "DEFAULT_SENTENCE_TRANSFORMER_MODEL",
    "normalize_semantic_text",
    "compute_semantic_similarity",
    # Regression (P3)
    "RegressionThresholds",

    "RegressionFinding",
    "RegressionReport",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "check_regression",
    "check_regression_from_store",
    # Error codes
    "CASE_INVALID",
    "GRADER_INVALID",
    "CASE_GRADER_MISMATCH",
    "SOLVER_EXECUTION_FAILED",
    "GRADER_RUNTIME_ERROR",
    "RESULT_PERSIST_FAILED",
    "HARNESS_RUNTIME_ERROR",
    # Exceptions
    "HarnessError",
    "HarnessValidationError",
    "GraderValidationError",
    "BindingValidationError",
    "PersistenceError",
    # Validators
    "validate_case",
    "validate_grader",
    "validate_binding",
]
