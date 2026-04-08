"""Shared runtime protocol contracts for Adaptive Skill System.

These contracts are intentionally separated from harness evaluation artifacts.
`ExecutionResult` describes runtime execution. `RunResult` remains the
standardized harness artifact produced after grading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .core import SolveResponse
    from .harness.specs import CaseSpec


ALLOWED_TASK_SOURCES = {"user", "automation", "benchmark", "bridge", "api"}
ALLOWED_PRIORITIES = {"low", "normal", "high", "critical"}
ALLOWED_EXECUTION_MODES = {"direct", "compose", "generate", "coordinate"}
ALLOWED_RUNTIME_STATUSES = {"success", "partial", "failed", "error", "unknown"}


@dataclass
class TaskSpec:
    """Stable runtime input contract shared across agent and harness entrypoints."""

    task_id: str
    task_text: str
    task_type: str
    input_payload: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    source: str = "user"
    priority: str = "normal"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.input_payload = dict(self.input_payload or {})
        self.constraints = dict(self.constraints or {})
        self.tags = list(self.tags or [])
        self.metadata = dict(self.metadata or {})
        if "problem" not in self.input_payload and self.task_text:
            self.input_payload["problem"] = self.task_text

    @property
    def problem(self) -> str:
        """Return the canonical problem string consumed by the runtime."""
        value = self.input_payload.get("problem", self.task_text)
        return value if isinstance(value, str) else str(value)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_case(
        cls,
        case: CaseSpec,
        *,
        source: str = "benchmark",
        priority: str = "normal",
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskSpec:
        """Lift a harness CaseSpec into the shared runtime task contract."""
        merged_metadata = dict(case.metadata or {})
        if metadata:
            merged_metadata.update(metadata)
        return cls(
            task_id=task_id or case.case_id,
            task_text=case.problem,
            task_type=case.task_type,
            input_payload=dict(case.input_payload),
            constraints=dict(case.constraints),
            source=source,
            priority=priority,
            tags=list(case.tags),
            metadata=merged_metadata,
        )


@dataclass
class ContextSpec:
    """Runtime envelope assembled around a TaskSpec before execution begins."""

    trace_id: str
    task_id: str
    session_id: Optional[str] = None
    agent: Dict[str, Any] = field(default_factory=dict)
    routing: Dict[str, Any] = field(default_factory=dict)
    skill: Dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "direct"
    memory_context: Dict[str, Any] = field(default_factory=dict)
    plan_context: Dict[str, Any] = field(default_factory=dict)
    policy_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 多租户字段
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None  # "viewer", "member", "editor", "admin", "owner"

    def __post_init__(self) -> None:
        self.agent = dict(self.agent or {})
        self.routing = dict(self.routing or {})
        self.skill = dict(self.skill or {})
        self.memory_context = dict(self.memory_context or {})
        self.plan_context = dict(self.plan_context or {})
        self.policy_context = dict(self.policy_context or {})
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTrace:
    """Structured evidence describing why one routing layer was selected or rejected."""

    layer: int
    action: str
    trigger: str
    score: Optional[float] = None
    candidates_evaluated: int = 0
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    rejection_detail: Dict[str, Any] = field(default_factory=dict)
    coverage_score: Optional[float] = None
    composability_score: Optional[float] = None
    framework_used: Optional[str] = None
    generation_strategy: Optional[str] = None
    quality_gate_passed: Optional[bool] = None
    evaluator_score: Optional[float] = None
    evaluator_dimensions: Dict[str, float] = field(default_factory=dict)
    selected_skill_id: Optional[str] = None
    selected_skill_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    """Unified runtime output contract prior to harness grading."""

    run_id: str
    task_id: str
    trace_id: str
    status: str
    success: bool
    result: Any = None
    output: Any = None
    agent_id: Optional[str] = None
    skill_id: Optional[str] = None
    skill_version: Optional[str] = None
    layer_used: int = 0
    confidence: float = 0.0
    execution_time_ms: float = 0.0
    steps_completed: int = 0
    total_steps: int = 0
    error_message: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


    def __post_init__(self) -> None:
        self.artifacts = list(self.artifacts or [])
        self.evidence = dict(self.evidence or {})
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_observation(self, *, case_id: Optional[str] = None) -> Dict[str, Any]:
        """Project the runtime result into the stable harness-facing observation."""
        observation: Dict[str, Any] = {
            "result": self.result,
            "layer": self.layer_used,
            "status": self.status,
            "confidence": self.confidence,
            "execution_time_ms": self.execution_time_ms,
            "skill_id": self.skill_id,
            "skill_name": self.metadata.get("skill_name"),
            "metadata": self.metadata,
        }
        if case_id is not None:
            observation["case_id"] = case_id
        return observation

    @classmethod
    def from_solve_response(
        cls,
        response: SolveResponse,
        *,
        task_id: str,
        trace_id: str,
        run_id: str,
        output: Any = None,
        agent_id: Optional[str] = None,
        steps_completed: Optional[int] = None,
        total_steps: Optional[int] = None,
        error_message: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Lift SolveResponse into the shared runtime result contract."""
        skill = response.skill_used
        merged_metadata = dict(response.metadata or {})
        if skill is not None:
            merged_metadata.setdefault("skill_name", skill.name)
        if metadata:
            merged_metadata.update(metadata)

        resolved_steps_completed = (
            steps_completed
            if steps_completed is not None
            else int(merged_metadata.get("steps_completed", 0) or 0)
        )
        resolved_total_steps = (
            total_steps
            if total_steps is not None
            else int(merged_metadata.get("total_steps", 0) or 0)
        )
        resolved_error_message = error_message or merged_metadata.get("error_message")
        resolved_decision_trace = _normalize_decision_trace_items(
            merged_metadata.get("decision_trace")
        )
        if resolved_decision_trace:
            merged_metadata["decision_trace"] = resolved_decision_trace

        resolved_evidence = dict(evidence or {})
        if "decision_trace" in resolved_evidence:
            resolved_evidence["decision_trace"] = _normalize_decision_trace_items(
                resolved_evidence.get("decision_trace")
            )
        elif resolved_decision_trace:
            resolved_evidence["decision_trace"] = resolved_decision_trace

        return cls(

            run_id=run_id,
            task_id=task_id,
            trace_id=trace_id,
            status=response.status,
            success=response.status in {"success", "partial"} and not resolved_error_message,
            result=response.result,
            output=response.result if output is None else output,
            agent_id=agent_id,
            skill_id=skill.skill_id if skill is not None else None,
            skill_version=skill.version if skill is not None else None,
            layer_used=response.layer,
            confidence=response.confidence,
            execution_time_ms=response.execution_time_ms,
            steps_completed=resolved_steps_completed,
            total_steps=resolved_total_steps,
            error_message=resolved_error_message,
            artifacts=list(artifacts or []),
            evidence=resolved_evidence,
            metadata=merged_metadata,
        )





def _normalize_decision_trace_items(trace_items: Any) -> List[Dict[str, Any]]:
    """Normalize trace payloads coming from metadata/evidence into plain dicts."""
    if not trace_items:
        return []

    normalized: List[Dict[str, Any]] = []
    for item in trace_items:
        if isinstance(item, DecisionTrace):
            normalized.append(item.to_dict())
        elif isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def task_spec_from_case(

    case: CaseSpec,
    *,
    source: str = "benchmark",
    priority: str = "normal",
    task_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskSpec:
    """Functional wrapper around TaskSpec.from_case()."""
    return TaskSpec.from_case(
        case,
        source=source,
        priority=priority,
        task_id=task_id,
        metadata=metadata,
    )


def execution_result_from_solve_response(
    response: SolveResponse,
    *,
    task_id: str,
    trace_id: str,
    run_id: str,
    output: Any = None,
    agent_id: Optional[str] = None,
    steps_completed: Optional[int] = None,
    total_steps: Optional[int] = None,
    error_message: Optional[str] = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ExecutionResult:
    """Functional wrapper around ExecutionResult.from_solve_response()."""
    return ExecutionResult.from_solve_response(
        response,
        task_id=task_id,
        trace_id=trace_id,
        run_id=run_id,
        output=output,
        agent_id=agent_id,
        steps_completed=steps_completed,
        total_steps=total_steps,
        error_message=error_message,
        artifacts=artifacts,
        evidence=evidence,
        metadata=metadata,
    )


def solve_task_with_protocol(
    system: Any,
    task: TaskSpec,
    *,
    context: Optional[ContextSpec] = None,
    verbose: bool = False,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    output: Any = None,
    steps_completed: Optional[int] = None,
    total_steps: Optional[int] = None,
    error_message: Optional[str] = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ExecutionResult:
    """Execute a TaskSpec through the runtime and normalize it into ExecutionResult."""
    # Extract tenant info for isolation and audit
    tenant_id = None
    user_id = None
    role = None
    
    # Priority: context > task.metadata > metadata param
    if context is not None:
        tenant_id = context.tenant_id
        user_id = context.user_id
        role = context.role
    
    if not tenant_id:
        tenant_id = task.metadata.get("tenant_id")
        user_id = user_id or task.metadata.get("user_id")
        role = role or task.metadata.get("role")
    
    if metadata:
        tenant_id = tenant_id or metadata.get("tenant_id")
        user_id = user_id or metadata.get("user_id")
        role = role or metadata.get("role")
    
    # Pass tenant info to solve() for tenant isolation
    # Only pass non-None values to stay backward-compatible with
    # implementations that haven't yet added tenant parameters.
    tenant_kwargs: Dict[str, Any] = {}
    if tenant_id is not None:
        tenant_kwargs["tenant_id"] = tenant_id
    if user_id is not None:
        tenant_kwargs["user_id"] = user_id
    if role is not None:
        tenant_kwargs["role"] = role

    solve_response = system.solve(
        task.problem,
        verbose=verbose,
        **tenant_kwargs,
    )

    resolved_trace_id = str(
        context.trace_id
        if context is not None
        else task.metadata.get("trace_id", task.task_id)
    )
    context_run_id = context.metadata.get("run_id") if context is not None else None
    resolved_run_id = str(run_id or context_run_id or task.metadata.get("run_id", f"run-{task.task_id}"))

    runtime_metadata: Dict[str, Any] = dict(task.metadata)
    
    # Add tenant info to metadata for audit trail
    if tenant_id:
        runtime_metadata["tenant_id"] = tenant_id
    if user_id:
        runtime_metadata["user_id"] = user_id
    if role:
        runtime_metadata["role"] = role
    
    runtime_metadata.setdefault("task_type", task.task_type)
    runtime_metadata.setdefault("task_source", task.source)
    runtime_metadata.setdefault("task_priority", task.priority)
    runtime_metadata.setdefault("task_tags", list(task.tags))
    runtime_metadata.setdefault("task_constraints", dict(task.constraints))

    if context is not None:
        runtime_metadata.setdefault("execution_mode", context.execution_mode)
        if context.session_id is not None:
            runtime_metadata.setdefault("session_id", context.session_id)
        if context.agent:
            runtime_metadata.setdefault("agent", dict(context.agent))
        if context.routing:
            runtime_metadata.setdefault("routing", dict(context.routing))
        if context.skill:
            runtime_metadata.setdefault("selected_skill", dict(context.skill))
        if context.memory_context:
            runtime_metadata.setdefault("memory_context", dict(context.memory_context))
        if context.plan_context:
            runtime_metadata.setdefault("plan_context", dict(context.plan_context))
        if context.policy_context:
            runtime_metadata.setdefault("policy_context", dict(context.policy_context))
        runtime_metadata.update(context.metadata)

    if metadata:
        runtime_metadata.update(metadata)

    # Resolve agent_id: caller-supplied takes priority, then fall back to context.agent["id"]
    if agent_id is None and context is not None and context.agent:
        agent_id = context.agent.get("id")

    return execution_result_from_solve_response(
        solve_response,
        task_id=task.task_id,
        trace_id=resolved_trace_id,
        run_id=resolved_run_id,
        output=output,
        agent_id=agent_id,
        steps_completed=steps_completed,
        total_steps=total_steps,
        error_message=error_message,
        artifacts=artifacts,
        evidence=evidence,
        metadata=runtime_metadata,
    )


__all__ = [

    "ALLOWED_TASK_SOURCES",
    "ALLOWED_PRIORITIES",
    "ALLOWED_EXECUTION_MODES",
    "ALLOWED_RUNTIME_STATUSES",
    "TaskSpec",
    "ContextSpec",
    "DecisionTrace",
    "ExecutionResult",

    "task_spec_from_case",
    "execution_result_from_solve_response",
    "solve_task_with_protocol",
]

