"""Tests for the shared runtime protocol layer."""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adaptive_skill import (
    AdaptiveSkillSystem,
    ContextSpec,
    ProtocolExecutionResult,
    TaskSpec,
    solve_task_with_protocol,
    task_spec_from_case,
)


from adaptive_skill.core import (
    GenerationInfo,
    QualityMetrics,
    Skill,
    SkillMetadata,
    SkillStatus,
    SkillStep,
    SkillType,
    SolveResponse,
)
from adaptive_skill.harness.single_case import normalize_response
from adaptive_skill.harness.specs import CaseSpec
from adaptive_skill.protocols import DecisionTrace, execution_result_from_solve_response



def _sample_skill() -> Skill:
    now = datetime.now()
    return Skill(
        skill_id="skill-protocol-001",
        name="Protocol Skill",
        description="Protocol bridge smoke skill",
        version="1.0",
        status=SkillStatus.ACTIVE,
        steps=[
            SkillStep(
                step_number=1,
                name="collect",
                description="collect context",
                source="framework",
            )
        ],
        required_inputs=["problem"],
        outputs=["summary"],
        parameters={},
        metadata=SkillMetadata(
            created_at=now,
            updated_at=now,
            created_by="test",
        ),
        generation_info=GenerationInfo(skill_type=SkillType.MANUAL),
        quality_metrics=QualityMetrics(),
    )


def test_task_spec_from_case_promotes_harness_case() -> None:
    case = CaseSpec(
        case_id="case-protocol-001",
        title="Protocol task",
        description="Promote harness input into runtime contract",
        task_type="system-design",
        input_payload={"problem": "define a shared protocol layer", "scope": "adaptive-skill"},
        expected_outcome_type="document",
        constraints={"format": "python"},
        tags=["protocol", "runtime"],
        metadata={"origin": "test"},
    )

    task = task_spec_from_case(case, priority="high")

    assert isinstance(task, TaskSpec)
    assert task.task_id == case.case_id
    assert task.task_text == "define a shared protocol layer"
    assert task.problem == "define a shared protocol layer"
    assert task.source == "benchmark"
    assert task.priority == "high"
    assert task.input_payload["scope"] == "adaptive-skill"
    assert task.constraints == {"format": "python"}
    assert task.tags == ["protocol", "runtime"]
    assert task.metadata["origin"] == "test"


def test_execution_result_from_solve_response_keeps_runtime_fields() -> None:
    response = SolveResponse(
        result={"summary": "done"},
        skill_used=_sample_skill(),
        layer=2,
        status="success",
        confidence=0.86,
        execution_time_ms=123.4,
        metadata={"steps_completed": 2, "total_steps": 3},
    )

    execution_result = execution_result_from_solve_response(
        response,
        task_id="task-protocol-001",
        trace_id="trace-protocol-001",
        run_id="run-protocol-001",
        agent_id="后石",
    )

    assert isinstance(execution_result, ProtocolExecutionResult)
    assert execution_result.task_id == "task-protocol-001"
    assert execution_result.trace_id == "trace-protocol-001"
    assert execution_result.run_id == "run-protocol-001"
    assert execution_result.success is True
    assert execution_result.layer_used == 2
    assert execution_result.skill_id == "skill-protocol-001"
    assert execution_result.skill_version == "1.0"
    assert execution_result.steps_completed == 2
    assert execution_result.total_steps == 3
    assert execution_result.metadata["skill_name"] == "Protocol Skill"

    observation = execution_result.to_observation(case_id="case-protocol-001")
    assert observation == {
        "case_id": "case-protocol-001",
        "result": {"summary": "done"},
        "layer": 2,
        "status": "success",
        "confidence": 0.86,
        "execution_time_ms": 123.4,
        "skill_id": "skill-protocol-001",
        "skill_name": "Protocol Skill",
        "metadata": {"steps_completed": 2, "total_steps": 3, "skill_name": "Protocol Skill"},
    }


def test_execution_result_from_solve_response_exposes_decision_trace_in_evidence() -> None:
    response = SolveResponse(
        result={"summary": "trace-aware"},
        skill_used=_sample_skill(),
        layer=3,
        status="success",
        confidence=0.91,
        execution_time_ms=88.0,
        metadata={
            "decision_trace": [
                DecisionTrace(
                    layer=1,
                    action="blocked",
                    trigger="direct_match",
                    score=0.48,
                    rejection_reason="below_threshold",
                ),
                DecisionTrace(
                    layer=3,
                    action="selected",
                    trigger="generation",
                    score=0.81,
                    generation_strategy="analogy",
                    quality_gate_passed=True,
                    evaluator_dimensions={"completeness": 0.82, "clarity": 0.8},
                ),
            ]
        },
    )

    execution_result = execution_result_from_solve_response(
        response,
        task_id="task-protocol-trace",
        trace_id="trace-protocol-trace",
        run_id="run-protocol-trace",
    )

    assert execution_result.evidence["decision_trace"][0]["layer"] == 1
    assert execution_result.evidence["decision_trace"][0]["rejection_reason"] == "below_threshold"
    assert execution_result.evidence["decision_trace"][1]["generation_strategy"] == "analogy"
    assert execution_result.evidence["decision_trace"][1]["quality_gate_passed"] is True
    assert execution_result.metadata["decision_trace"][1]["evaluator_dimensions"]["completeness"] == 0.82



def test_normalize_response_uses_protocol_adapter_without_shape_change() -> None:
    case = CaseSpec(
        case_id="case-protocol-002",
        title="Normalize via protocol",
        description="Ensure harness adapter keeps observation shape stable",
        task_type="analysis",
        input_payload={"problem": "analyze protocol bridge"},
        expected_outcome_type="json",
        metadata={"trace_id": "trace-protocol-002", "run_id": "run-protocol-002"},
    )
    response = SolveResponse(
        result="bridge-ok",
        skill_used=None,
        layer=1,
        status="partial",
        confidence=0.61,
        execution_time_ms=12.5,
        metadata={"notes": ["fallback"]},
    )


    observation = normalize_response(case, response)

    assert observation == {
        "case_id": "case-protocol-002",
        "result": "bridge-ok",
        "layer": 1,
        "status": "partial",
        "confidence": 0.61,
        "execution_time_ms": 12.5,
        "skill_id": None,
        "skill_name": None,
        "metadata": {"notes": ["fallback"]},
    }

    context = ContextSpec(trace_id="trace-protocol-002", task_id=case.case_id)
    assert context.to_dict()["execution_mode"] == "direct"


class _StubAdaptiveSystem:
    def __init__(self, response: SolveResponse) -> None:
        self.response = response
        self.calls = []

    def solve(
        self,
        problem: str,
        verbose: bool = False,
        tenant_id: str = None,
        user_id: str = None,
        role: str = None,
    ) -> SolveResponse:
        self.calls.append({
            "problem": problem,
            "verbose": verbose,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": role,
        })
        return self.response


def test_solve_task_with_protocol_builds_runtime_golden_path() -> None:
    response = SolveResponse(
        result={"answer": "protocol-run"},
        skill_used=_sample_skill(),
        layer=3,
        status="success",
        confidence=0.91,
        execution_time_ms=88.0,
        metadata={"steps_completed": 1, "total_steps": 2},
    )
    system = _StubAdaptiveSystem(response)
    task = TaskSpec(
        task_id="task-protocol-002",
        task_text="run protocol end to end",
        task_type="integration",
        constraints={"mode": "test"},
        tags=["protocol", "golden-path"],
        metadata={"owner": "test-suite"},
    )
    context = ContextSpec(
        trace_id="trace-protocol-003",
        task_id=task.task_id,
        session_id="session-protocol-001",
        agent={"id": "后石"},
        routing={"entry": "protocol"},
        execution_mode="coordinate",
        metadata={"run_id": "run-protocol-003", "channel": "pytest"},
    )

    execution_result = solve_task_with_protocol(
        system,
        task,
        context=context,
        verbose=True,
        agent_id="后石",
        metadata={"initiator": "test"},
    )

    assert isinstance(execution_result, ProtocolExecutionResult)
    assert system.calls == [{
        "problem": "run protocol end to end",
        "verbose": True,
        "tenant_id": None,
        "user_id": None,
        "role": None,
    }]
    assert execution_result.run_id == "run-protocol-003"
    assert execution_result.trace_id == "trace-protocol-003"
    assert execution_result.task_id == "task-protocol-002"
    assert execution_result.agent_id == "后石"
    assert execution_result.layer_used == 3
    assert execution_result.metadata["task_type"] == "integration"
    assert execution_result.metadata["task_source"] == "user"
    assert execution_result.metadata["task_constraints"] == {"mode": "test"}
    assert execution_result.metadata["execution_mode"] == "coordinate"
    assert execution_result.metadata["session_id"] == "session-protocol-001"
    assert execution_result.metadata["routing"] == {"entry": "protocol"}
    assert execution_result.metadata["channel"] == "pytest"
    assert execution_result.metadata["initiator"] == "test"


def test_adaptive_skill_system_solve_task_exposes_formal_protocol_entry() -> None:
    response = SolveResponse(
        result={"answer": "class-entry"},
        skill_used=_sample_skill(),
        layer=2,
        status="success",
        confidence=0.87,
        execution_time_ms=45.0,
        metadata={"steps_completed": 2, "total_steps": 2},
    )
    system = AdaptiveSkillSystem(auto_attach_memory=False)

    calls = []

    def _fake_solve(problem: str, verbose: bool = False) -> SolveResponse:
        calls.append({"problem": problem, "verbose": verbose})
        return response

    system.solve = _fake_solve  # type: ignore[method-assign]

    task = TaskSpec(
        task_id="task-protocol-003",
        task_text="formal protocol entry",
        task_type="integration",
        metadata={"owner": "core-entry"},
    )
    context = ContextSpec(
        trace_id="trace-protocol-004",
        task_id=task.task_id,
        agent={"id": "adaptive-core"},
        execution_mode="coordinate",
        metadata={"run_id": "run-protocol-004"},
    )

    execution_result = system.solve_task(
        task,
        context=context,
        verbose=True,
        metadata={"entrypoint": "AdaptiveSkillSystem.solve_task"},
    )

    assert isinstance(execution_result, ProtocolExecutionResult)
    assert calls == [{"problem": "formal protocol entry", "verbose": True}]
    assert execution_result.task_id == "task-protocol-003"
    assert execution_result.trace_id == "trace-protocol-004"
    assert execution_result.run_id == "run-protocol-004"
    assert execution_result.agent_id == "adaptive-core"
    assert execution_result.layer_used == 2
    assert execution_result.metadata["owner"] == "core-entry"
    assert execution_result.metadata["execution_mode"] == "coordinate"
    assert execution_result.metadata["entrypoint"] == "AdaptiveSkillSystem.solve_task"


