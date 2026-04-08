"""
自适应 Skill 系统 - 核心执行引擎
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


# Adapter main path imports
from .adapters import create_kb_adapter, KBProvider, KBCredential
from .multi_tenant.context import TenantIsolation, TenantContext
from .thresholds import DEFAULT_THRESHOLD_POLICY, RuntimeThresholdPolicy



class SkillStatus(Enum):
    """Skill 的状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


class SkillType(Enum):
    """Skill 的生成方式"""
    MANUAL = "manual"
    COMPOSED = "composed"
    AUTO_GENERATED = "auto-generated"


@dataclass
class SkillStep:
    """Skill 中的单个步骤"""
    step_number: int
    name: str
    description: str
    source: str  # "框架" | "记忆" | "自动生成"
    customization: Optional[str] = None
    estimated_duration: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "step": self.step_number,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "customization": self.customization,
            "estimated_duration": self.estimated_duration
        }


@dataclass
class SkillMetadata:
    """Skill 的元数据"""
    created_at: datetime
    updated_at: datetime
    created_by: str  # "user" | "ai-generated"
    update_reason: Optional[str] = None
    last_challenged_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "update_reason": self.update_reason,
            "last_challenged_at": self.last_challenged_at.isoformat() if self.last_challenged_at else None
        }


@dataclass
class GenerationInfo:
    """自动生成相关的信息"""
    skill_type: SkillType
    base_skills: List[str] = field(default_factory=list)
    ltm_references: List[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_verification: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "type": self.skill_type.value,
            "base_skills": self.base_skills,
            "ltm_references": self.ltm_references,
            "confidence": self.confidence,
            "needs_verification": self.needs_verification
        }


@dataclass
class QualityMetrics:
    """Skill 的质量指标"""
    usage_count: int = 0
    success_rate: float = 0.0  # 0-1
    user_satisfaction: float = 0.0  # 1-5
    failure_count: int = 0
    total_failures: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "user_satisfaction": self.user_satisfaction,
            "failure_count": self.failure_count,
            "total_failures": self.total_failures
        }


@dataclass
class Skill:
    """Skill 的完整定义"""
    skill_id: str
    name: str
    description: str
    version: str
    status: SkillStatus
    
    # 内容
    steps: List[SkillStep]
    required_inputs: List[str]
    outputs: List[str]
    parameters: Dict[str, Any]
    
    # 元数据
    metadata: SkillMetadata
    generation_info: GenerationInfo
    quality_metrics: QualityMetrics
    
    # 版本历史
    versions: Dict[str, Dict] = field(default_factory=dict)
    
    # 版本 DAG 谱系字段（2026-03-29 新增）
    parent_id: Optional[str] = None          # 父 Skill ID，None 表示原创
    evolution_type: str = "original"          # original | derived | fixed | composed | auto-generated
    
    def to_dict(self) -> Dict:
        """转换为字典（用于存储）"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "status": self.status.value,
            "steps": [step.to_dict() for step in self.steps],
            "required_inputs": self.required_inputs,
            "outputs": self.outputs,
            "parameters": self.parameters,
            "metadata": self.metadata.to_dict(),
            "generation_info": self.generation_info.to_dict(),
            "quality_metrics": self.quality_metrics.to_dict(),
            "versions": self.versions,
            "parent_id": self.parent_id,
            "evolution_type": self.evolution_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Skill':
        """从字典创建 Skill"""
        steps = [
            SkillStep(
                step_number=step['step'],
                name=step['name'],
                description=step['description'],
                source=step['source'],
                customization=step.get('customization'),
                estimated_duration=step.get('estimated_duration')
            )
            for step in data['steps']
        ]
        
        metadata = SkillMetadata(
            created_at=datetime.fromisoformat(data['metadata']['created_at']),
            updated_at=datetime.fromisoformat(data['metadata']['updated_at']),
            created_by=data['metadata']['created_by'],
            update_reason=data['metadata'].get('update_reason'),
            last_challenged_at=datetime.fromisoformat(data['metadata']['last_challenged_at']) 
                if data['metadata'].get('last_challenged_at') else None
        )
        
        generation_info = GenerationInfo(
            skill_type=SkillType(data['generation_info']['type']),
            base_skills=data['generation_info'].get('base_skills', []),
            ltm_references=data['generation_info'].get('ltm_references', []),
            confidence=data['generation_info'].get('confidence', 0.0),
            needs_verification=data['generation_info'].get('needs_verification', False)
        )
        
        quality_metrics = QualityMetrics(
            usage_count=data['quality_metrics'].get('usage_count', 0),
            success_rate=data['quality_metrics'].get('success_rate', 0.0),
            user_satisfaction=data['quality_metrics'].get('user_satisfaction', 0.0),
            failure_count=data['quality_metrics'].get('failure_count', 0),
            total_failures=data['quality_metrics'].get('total_failures', 0)
        )
        
        return cls(
            skill_id=data['skill_id'],
            name=data['name'],
            description=data['description'],
            version=data['version'],
            status=SkillStatus(data['status']),
            steps=steps,
            required_inputs=data['required_inputs'],
            outputs=data['outputs'],
            parameters=data['parameters'],
            metadata=metadata,
            generation_info=generation_info,
            quality_metrics=quality_metrics,
            versions=data.get('versions', {}),
            parent_id=data.get('parent_id', None),
            evolution_type=data.get('evolution_type', 'original'),
        )


@dataclass
class ExecutionResult:
    """Skill 执行的结果"""
    success: bool
    output: Any
    duration_seconds: float
    steps_completed: int
    total_steps: int
    error_message: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
            "duration_seconds": self.duration_seconds,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


@dataclass
class SolveResponse:
    """系统解决问题的最终响应"""
    result: Any
    skill_used: Optional[Skill]
    layer: int  # 1 | 2 | 3 | 0
    status: str  # "success" | "partial" | "failed"
    confidence: float  # 0-1
    execution_time_ms: float
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "result": self.result,
            "skill": self.skill_used.to_dict() if self.skill_used else None,
            "layer": self.layer,
            "status": self.status,
            "confidence": self.confidence,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


class SkillExecutor:
    """Skill 执行引擎"""
    
    def __init__(self):
        self.execution_history = []
    
    def execute(self, skill: Skill, problem: str, inputs: Optional[Dict] = None) -> ExecutionResult:
        """
        执行一个 Skill
        
        Args:
            skill: 要执行的 Skill
            problem: 原始问题
            inputs: 输入参数
        
        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        
        try:
            steps_completed = 0
            outputs = []
            
            # 按顺序执行每个步骤
            for step in skill.steps:
                try:
                    # 这里是 Skill 执行的关键逻辑
                    # 实际应用中需要根据 step.source 调用不同的处理器
                    step_result = self._execute_step(step, problem, inputs, outputs)
                    outputs.append(step_result)
                    steps_completed += 1
                except Exception as e:
                    return ExecutionResult(
                        success=False,
                        output=None,
                        duration_seconds=time.time() - start_time,
                        steps_completed=steps_completed,
                        total_steps=len(skill.steps),
                        error_message=f"Step {step.name} failed: {str(e)}"
                    )
            
            # 整合最终输出
            final_output = self._aggregate_outputs(outputs, skill.outputs)
            
            execution_time = time.time() - start_time
            result = ExecutionResult(
                success=True,
                output=final_output,
                duration_seconds=execution_time,
                steps_completed=steps_completed,
                total_steps=len(skill.steps),
                metadata={
                    "skill_id": skill.skill_id,
                    "skill_version": skill.version,
                    "step_details": [step.name for step in skill.steps]
                }
            )
            
            # 记录到历史
            self.execution_history.append({
                "timestamp": datetime.now(),
                "skill_id": skill.skill_id,
                "result": result.to_dict()
            })
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output=None,
                duration_seconds=execution_time,
                steps_completed=0,
                total_steps=len(skill.steps),
                error_message=f"Skill execution failed: {str(e)}"
            )
    
    def _execute_step(self, step: SkillStep, problem: str, inputs: Optional[Dict], 
                      previous_outputs: List) -> Any:
        """执行单个步骤"""
        # 这是一个占位符，实际实现需要根据 step.source 调用不同的处理器
        
        if step.source == "框架":
            # 调用框架逻辑
            return self._execute_framework_step(step, problem, inputs, previous_outputs)
        elif step.source == "记忆":
            # 从 LTM 中获取并执行
            return self._execute_memory_step(step, problem, inputs, previous_outputs)
        elif step.source == "自动生成":
            # 执行自动生成的步骤
            return self._execute_generated_step(step, problem, inputs, previous_outputs)
        else:
            raise ValueError(f"Unknown step source: {step.source}")
    
    def _execute_framework_step(self, step: SkillStep, problem: str,
                               inputs: Optional[Dict], previous_outputs: List) -> Any:
        """
        执行基于框架的步骤。
        
        框架步骤代表通用方法论（如「收集数据」「分析趋势」「制定策略」），
        执行结果包含：步骤描述、从问题中提取的关键信息、自定义说明。
        """
        # 从前一步骤的输出中聚合上下文
        context_summary = ""
        if previous_outputs:
            prev_messages = [
                str(o.get("output", o.get("message", "")))
                for o in previous_outputs
                if isinstance(o, dict)
            ]
            context_summary = " | ".join(filter(None, prev_messages))[:200]
        
        output_text = step.description
        if step.customization:
            output_text += f"\n调整点：{step.customization}"
        if context_summary:
            output_text += f"\n基于上下文：{context_summary}"
        
        return {
            "step_name": step.name,
            "step_number": step.step_number,
            "source": "framework",
            "status": "completed",
            "output": output_text,
            "estimated_duration": step.estimated_duration
        }
    
    def _execute_memory_step(self, step: SkillStep, problem: str,
                            inputs: Optional[Dict], previous_outputs: List) -> Any:
        """
        执行基于记忆的步骤。
        
        记忆步骤将 LTM 中已有的知识应用到当前问题。
        执行结果将步骤描述与问题关键词结合，生成应用建议。
        """
        # 提取问题核心词（最多 5 个有意义的词）
        problem_tokens = [
            w for w in problem.replace("，", " ").replace("。", " ").split()
            if len(w) > 1
        ][:5]
        
        # 组合应用建议
        applied_text = step.description
        if problem_tokens:
            applied_text += f"\n应用到「{'、'.join(problem_tokens)}」："
            applied_text += f" 根据已有经验，{step.description}"
        if step.customization:
            applied_text += f"\n个性化调整：{step.customization}"
        
        return {
            "step_name": step.name,
            "step_number": step.step_number,
            "source": "memory",
            "status": "completed",
            "output": applied_text,
            "memory_applied": True,
            "problem_keywords": problem_tokens
        }
    
    def _execute_generated_step(self, step: SkillStep, problem: str,
                               inputs: Optional[Dict], previous_outputs: List) -> Any:
        """
        执行自动生成的步骤。
        
        自动生成步骤是系统根据问题特征推断出的行动方案，
        执行时整合问题、步骤描述和已有前置输出，生成结构化建议。
        """
        # 提取所有前置步骤输出
        prior_context = []
        for o in previous_outputs:
            if isinstance(o, dict):
                prior_context.append(o.get("output", o.get("message", "")))
        
        # 构建生成步骤的行动建议
        action_text = f"[自动生成] {step.description}"
        if step.customization:
            action_text += f"\n策略：{step.customization}"
        if prior_context:
            action_text += f"\n基于前序步骤：{' → '.join(str(c)[:80] for c in prior_context if c)}"
        
        return {
            "step_name": step.name,
            "step_number": step.step_number,
            "source": "auto_generated",
            "status": "completed",
            "output": action_text,
            "confidence": 0.70,  # 自动生成步骤默认置信度
            "needs_review": True
        }
    
    def _aggregate_outputs(self, outputs: List, output_specs: List[str]) -> Dict:
        """整合多个步骤的输出"""
        aggregated = {}
        for i, output_spec in enumerate(output_specs):
            if i < len(outputs):
                aggregated[output_spec] = outputs[i]
        return aggregated


class AdaptiveSkillSystem:
    """自适应 Skill 系统的核心类"""
    
    def __init__(self, 
                 kb_client=None, 
                 ltm_client=None, 
                 memory_dir=None,
                 feedback_collector=None,
                 kb_provider: Optional[KBProvider] = None,
                 kb_credential: Optional[KBCredential] = None,
                 ltm_provider: Optional[KBProvider] = None,
                 ltm_credential: Optional[KBCredential] = None,
                 auto_attach_memory=None,
                 threshold_policy: RuntimeThresholdPolicy = DEFAULT_THRESHOLD_POLICY):

        """
        初始化系统
        
        Args:
            kb_client: 知识库客户端（如果为 None，将尝试从 memory_dir 创建）
            ltm_client: 长期记忆客户端（如果为 None，将尝试从 memory_dir 创建）
            memory_dir: 记忆系统目录路径
        """
        if kb_client is None and ltm_client is None and memory_dir is None:
            # 尝试从配置获取默认路径
            try:
                import sys
                import os
                from pathlib import Path
                
                # 查找 memory_dir
                possible_paths = [
                    Path.cwd() / "memory-bank",
                    Path(__file__).parent.parent / "memory-bank",
                    Path.home() / ".ai-memory-system" / "memory-bank"
                ]
                
                for path in possible_paths:
                    if path.exists():
                        memory_dir = str(path)
                        break
            except Exception as e:
                logger.warning(f"自动检测记忆目录失败: {e}")
                memory_dir = None
        
        # Adapter main path: provider config -> create_kb_adapter() -> runtime
        # MemorySystemClient is now a compatibility layer
        raw_kb = None
        raw_ltm = None
        self.memory_client = None
        
        # Priority 1: Explicit provider config (main path)
        if kb_provider:
            raw_kb = create_kb_adapter(kb_provider, kb_credential)
        if ltm_provider:
            raw_ltm = create_kb_adapter(ltm_provider, ltm_credential)
        
        # Priority 2: Legacy memory_dir path (compatibility)
        if raw_kb is None and raw_ltm is None and memory_dir:
            from .memory_system_client import MemorySystemClient
            self.memory_client = MemorySystemClient(memory_dir)
            raw_kb = self.memory_client.kb
            raw_ltm = self.memory_client.ltm
        
        # Priority 3: Direct client injection (testing/compatibility)
        if raw_kb is None:
            raw_kb = kb_client
        if raw_ltm is None:
            raw_ltm = ltm_client
        
        # Wrap with TenantIsolation for automatic tenant filtering.
        # IMPORTANT: KB and LTM must be separate TenantIsolation instances so that
        # operations on one store cannot bleed into the other.  Previously both
        # self.kb and self.ltm pointed at the same object which made KB/LTM
        # isolation purely nominal.
        if raw_kb is not None:
            self._kb_isolation = TenantIsolation(kb_adapter=raw_kb, ltm_adapter=None)
            self.kb = self._kb_isolation
        else:
            self._kb_isolation = None
            self.kb = None

        if raw_ltm is not None:
            self._ltm_isolation = TenantIsolation(kb_adapter=None, ltm_adapter=raw_ltm)
            self.ltm = self._ltm_isolation
        else:
            self._ltm_isolation = None
            self.ltm = None
        
        self.executor = SkillExecutor()
        self.skills_cache = {}
        self.skill_composer = None
        self.skill_generator = None
        self.quality_evaluator = None
        self.feedback_collector = feedback_collector
        self.threshold_policy = threshold_policy


        # 版本 DAG 谱系库（2026-03-29 接入）
        try:
            from .skill_lineage import SkillLineage
            self.lineage = SkillLineage()
        except Exception as _e:
            self.lineage = None  # 谱系库不可用时降级，不影响主流程
        
        # 延迟初始化子模块
        self._initialize_submodules()
    
    def _initialize_submodules(self):
        """初始化子模块（延迟加载）"""
        try:
            from .composer import SkillComposer
            from .generator import SkillGenerator
            from .evaluator import QualityEvaluator
            
            self.skill_composer = SkillComposer(
                ltm_client=self.ltm,
                kb_client=self.kb,
                threshold_policy=self.threshold_policy,
            )
            self.skill_generator = SkillGenerator(
                ltm_client=self.ltm,
                threshold_policy=self.threshold_policy,
            )
            self.quality_evaluator = QualityEvaluator(threshold_policy=self.threshold_policy)

            
            # 注：SkillGenerator 预期有 set_composer 方法用于组合，但当前版本尚未实现
            # 暂时注释掉这个连接
            
        except ImportError as e:
            print(f"警告：无法加载子模块，部分功能不可用：{e}")
    
    def solve(self, problem: str, verbose: bool = False,
              tenant_id: Optional[str] = None,
              user_id: Optional[str] = None,
              role: Optional[str] = None) -> SolveResponse:
        """
        主入口：尝试解决用户的问题
        
        Args:
            problem: 用户的问题
            verbose: 是否输出详细信息
            tenant_id: 租户 ID（多租户场景）
            user_id: 用户 ID
            role: 用户角色
        
        Returns:
            SolveResponse: 完整的解决方案响应
        """
        from .multi_tenant.context import TenantContext
        
        # Use tenant context if provided
        if tenant_id:
            with TenantContext.use(tenant_id, user_id=user_id, role=role):
                return self._solve_impl(problem, verbose)
        return self._solve_impl(problem, verbose)
    
    def _solve_impl(self, problem: str, verbose: bool = False) -> SolveResponse:
        """Internal solve implementation."""
        import time
        import inspect
        from .errors import Layer2CoverageError, AdaptiveSkillError
        start_time = time.time()
        # decision_trace accumulates structured evidence from each layer.
        # Each entry is a dict with at minimum {"layer": int, "outcome": str, ...}.
        decision_trace: list = []

        # ── compatibility helpers ──────────────────────────────────────────
        # Tests (and legacy callers) may monkeypatch _try_layer_N with plain
        # lambda problem: ... that only accept a positional 'problem' arg.
        # We detect whether the bound method/callable accepts a 'trace' kwarg
        # and fall back gracefully when it doesn't.

        def _call_l1(p: str):
            fn = self._try_layer_1
            try:
                sig = inspect.signature(fn)
                if "trace" in sig.parameters:
                    return fn(p, trace=decision_trace)
            except (ValueError, TypeError):
                pass
            return fn(p)

        def _call_l2(p: str):
            fn = self._try_layer_2
            try:
                sig = inspect.signature(fn)
                if "trace" in sig.parameters:
                    return fn(p, trace=decision_trace)
            except (ValueError, TypeError):
                pass
            return fn(p)

        def _call_l3(p: str):
            fn = self._try_layer_3
            try:
                sig = inspect.signature(fn)
                if "trace" in sig.parameters:
                    return fn(p, trace=decision_trace)
            except (ValueError, TypeError):
                pass
            return fn(p)
        # ──────────────────────────────────────────────────────────────────

        # 第一层：直接调用
        if verbose:
            print("[Layer 1] 搜索已有 Skill...")
        result_1, skill_1 = _call_l1(problem)
        if result_1:
            return SolveResponse(
                result=result_1.output,
                skill_used=skill_1,
                layer=1,
                status="success",
                confidence=self.threshold_policy.layer1_success_confidence,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={"layer_1_direct_match": True, "decision_trace": decision_trace}
            )


        # 第二层：组合（捕获 Layer2CoverageError 并记录，然后升级到 Layer 3）
        if verbose:
            print("[Layer 2] 尝试从记忆中组合 Skill...")
        layer_2_block_info: dict | None = None
        try:
            result_2, skill_2 = _call_l2(problem)
            if result_2:
                return SolveResponse(
                    result=result_2.output,
                    skill_used=skill_2,
                    layer=2,
                    status="success",
                    confidence=self.threshold_policy.layer2_success_confidence,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    metadata={"layer_2_composed": True, "decision_trace": decision_trace}
                )

        except Layer2CoverageError as exc:
            layer_2_block_info = {
                "error_type": type(exc).__name__,
                "actual_coverage": exc.actual_coverage,
                "minimum_coverage": exc.minimum_coverage,
                "framework_step_count": exc.framework_step_count,
                "ltm_supported_count": exc.ltm_supported_count,
                "message": str(exc),
            }
            if verbose:
                print(f"[Layer 2] 覆盖率不足 ({exc.actual_coverage:.1%} < {exc.minimum_coverage:.1%})，升级到 Layer 3")
        except AdaptiveSkillError as exc:
            layer_2_block_info = {
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            if verbose:
                print(f"[Layer 2] 失败 ({type(exc).__name__})，升级到 Layer 3")

        # 第三层：自动生成
        if verbose:
            print("[Layer 3] 尝试自动生成 Skill...")
        gen_info: dict | None = None
        try:
            result_3, skill_3, gen_info = _call_l3(problem)
        except Exception as exc:
            # Layer3QualityGateError 或其他异常 → 静默，记录 gen_info，走 failed 路径
            from .errors import Layer3QualityGateError
            if isinstance(exc, Layer3QualityGateError):
                gen_info = {
                    "quality": getattr(exc, "confidence", 0.0),
                    "blocked_reason": "quality gate",
                    "blocked_stage": "draft_generation",
                    "generation_mode": "blocked_before_draft",
                    "error_message": str(exc),
                }
            else:
                gen_info = {
                    "blocked_reason": type(exc).__name__,
                    "blocked_stage": "layer_3_execution",
                    "error_message": str(exc),
                }
            if verbose:
                print(f"[Layer 3] 被 {type(exc).__name__} 拦截，走 failed 路径")
            result_3, skill_3 = None, None
        if result_3:
            quality_score = gen_info.get("quality", 0)
            status = self.threshold_policy.layer3_status_for_quality(quality_score)
            confidence = quality_score
            meta: dict = {
                "layer_3_auto_generated": True,
                "generation_quality": quality_score,
                "needs_feedback": self.threshold_policy.layer3_needs_feedback(quality_score),
                "decision_trace": decision_trace,
            }

            if layer_2_block_info:
                meta["layer_2_block"] = layer_2_block_info
            return SolveResponse(
                result=result_3.output,
                skill_used=skill_3,
                layer=3,
                status=status,
                confidence=confidence,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata=meta,
            )

        # Layer 3 也未产出结果（可能是 quality gate 拦截）
        meta_failed: dict = {
            "reason": "Cannot solve this problem with current skills",
            "decision_trace": decision_trace,
        }
        if layer_2_block_info:
            meta_failed["layer_2_block"] = layer_2_block_info
        if gen_info:
            meta_failed["layer_3_attempt"] = gen_info
        return SolveResponse(
            result=None,
            skill_used=None,
            layer=0,
            status="failed",
            confidence=0.0,
            execution_time_ms=(time.time() - start_time) * 1000,
            metadata=meta_failed,
        )
    
    def _try_layer_1(self, problem: str,
                     trace: Optional[list] = None) -> Tuple[Optional[ExecutionResult], Optional[Skill]]:
        """
        第一层：在 KB 中搜索已有 Skill，若置信度足够则直接执行。
        
        匹配逻辑：
        1. 先从本地缓存（skills_cache）中查找
        2. 若有 KB 客户端，搜索 KB
        3. 计算关键词覆盖率作为置信度，阈值由共享 threshold policy 决定

        """
        # 1. 提取问题关键词（中文用字符 2-gram，英文按空格）
        problem_lower = problem.lower()
        
        # 检测是否含中文字符
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in problem_lower)
        
        if has_chinese:
            # 中文：去掉标点后做 2-gram 切片（单字不够区分，2字更精准）
            import re
            cjk_chars = re.sub(r'[^\u4e00-\u9fff]', '', problem_lower)
            # 单字词 + 2字词，确保覆盖率
            keywords = list(set(
                [cjk_chars[i:i+1] for i in range(len(cjk_chars))] +
                [cjk_chars[i:i+2] for i in range(len(cjk_chars) - 1)]
            ))
            # 过滤常见虚词（助词、连词不算关键词）
            stop_chars = {"的", "了", "是", "在", "和", "与", "或", "也", "都", "很",
                          "一", "个", "这", "那", "有", "到", "对", "为", "以", "及"}
            keywords = [k for k in keywords if k not in stop_chars and len(k) >= 1]
        else:
            # 英文：按空格分词
            keywords = [w for w in problem_lower.replace(',', ' ').replace('.', ' ').split()
                       if len(w) > 2]
        
        # 2. 先查本地缓存
        best_skill: Optional[Skill] = None
        best_score: float = 0.0
        
        for skill in self.skills_cache.values():
            if skill.status == SkillStatus.DEPRECATED:
                continue
            score = self._compute_skill_relevance(skill, keywords, problem_lower)
            if score > best_score:
                best_score = score
                best_skill = skill
        
        # 3. 若有 KB 客户端，从知识库搜索（支持 QueryVariant 多路召回）
        if self.kb:
            try:
                # 3a. 尝试用 retrieval 模块生成 query variants 做多路召回
                all_kb_entries: list = []
                seen_ids: set = set()

                def _dedup_add(entries):
                    for e in (entries or []):
                        e_id = (e.get("id") or e.get("doc_id") or id(e)) if isinstance(e, dict) else id(e)
                        if e_id not in seen_ids:
                            seen_ids.add(e_id)
                            all_kb_entries.append(e)

                # 主路：原始 query
                _dedup_add(self.kb.search(query=problem, top_k=5))

                # 多路：query variants（使用 retrieval 模块，失败则静默跳过）
                try:
                    from .retrieval import build_query_variants
                    variants = build_query_variants(problem)
                    for variant in variants:
                        variant_query = getattr(variant, "query", None) or str(variant)
                        if variant_query and variant_query != problem:
                            try:
                                _dedup_add(self.kb.search(query=variant_query, top_k=5))
                            except Exception:
                                pass
                except Exception:
                    pass  # retrieval 模块不可用时降级到单路召回

                for entry in all_kb_entries:
                    # KB 条目可能是 dict（kb_search 返回）
                    entry_dict = entry if isinstance(entry, dict) else (entry.to_dict() if hasattr(entry, 'to_dict') else {})

                    
                    # 尝试从 KB 条目重建 Skill
                    skill_data = entry_dict.get("content_parsed") or entry_dict.get("extra", {})
                    if isinstance(skill_data, dict) and "skill_id" in skill_data:
                        try:
                            skill = Skill.from_dict(skill_data)
                            score = self._compute_skill_relevance(skill, keywords, problem_lower)
                            if score > best_score:
                                best_score = score
                                best_skill = skill
                        except Exception:
                            pass
                    
                    # 若 KB 条目不是 Skill 对象，使用质量评估机制
                    quality_score, quality_level = self._evaluate_kb_match_quality(entry_dict, problem, keywords)
                    
                    # 只有高质量匹配才更新 best_score
                    # 中等质量匹配需要额外验证（暂时跳过，让 L2/L3 处理）
                    if quality_level == "high" and quality_score > best_score:
                        best_score = quality_score
                        best_skill = self._skill_from_kb_entry(entry_dict)
                    elif quality_level == "medium" and quality_score > best_score:
                        # 中等质量：记录但不立即使用，给 L2/L3 机会
                        # 如果后续没有更好的匹配，可以考虑使用
                        pass  # 暂时跳过中等质量匹配
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Layer 1 KB 搜索失败: {e}")
        
        # 4. 阈值判断：统一走共享 threshold policy，避免 core 与 thresholds.py 分叉
        layer1_threshold = self.threshold_policy.layer1_direct_match_threshold
        if best_skill and best_score >= layer1_threshold:
            if trace is not None:
                trace.append({
                    "layer": 1,
                    "outcome": "hit",
                    "skill_id": best_skill.skill_id,
                    "skill_name": best_skill.name,
                    "score": round(best_score, 4),
                    "threshold": layer1_threshold,
                    "reason": f"score {best_score:.4f} >= threshold {layer1_threshold}",
                })
            # 缓存命中的 Skill
            self.skills_cache[best_skill.skill_id] = best_skill
            # 写入谱系库（原创/已有 Skill 的使用记录）
            self._register_lineage_skill(best_skill, stage="layer_1_match")
            result = self.executor.execute(best_skill, problem)
            return result, best_skill

        if trace is not None:
            trace.append({
                "layer": 1,
                "outcome": "miss",
                "best_skill_id": best_skill.skill_id if best_skill else None,
                "best_skill_name": best_skill.name if best_skill else None,
                "best_score": round(best_score, 4),
                "threshold": layer1_threshold,
                "reason": (
                    f"score {best_score:.4f} < threshold {layer1_threshold}"
                    if best_skill else "no skill found in KB or cache"
                ),
            })
        return None, None
    
    def _compute_skill_relevance(self, skill: Skill, keywords: List[str], problem_lower: str) -> float:
        """计算 Skill 与问题的关联分数（0-1），区分匹配质量等级
        
        改进：只使用核心关键词（长度>=2）计算分数，避免单字词误匹配
        """
        skill_text = f"{skill.name} {skill.description} {' '.join(skill.required_inputs)} {' '.join(skill.outputs)}".lower()
        
        # 只使用核心关键词（长度>=2）
        core_keywords = [kw for kw in keywords if len(kw) >= 2]
        if not core_keywords:
            return 0.0
        
        # 基础分数：核心关键词覆盖率
        overlap = sum(1 for kw in core_keywords if kw in skill_text)
        base_score = overlap / max(len(core_keywords), 1)
        
        # 质量加成：检查核心意图匹配度
        name_lower = skill.name.lower() if skill.name else ""
        desc_lower = skill.description.lower() if skill.description else ""
        
        # 计算核心关键词在 name 中的命中数（权重更高）
        name_hits = sum(1 for kw in core_keywords if kw in name_lower)
        desc_hits = sum(1 for kw in core_keywords if kw in desc_lower)
        
        # 核心关键词命中加成
        core_bonus = 0.0
        if name_hits > 0:
            core_bonus += 0.15 * (name_hits / len(core_keywords))
        if desc_hits > 0:
            core_bonus += 0.10 * (desc_hits / len(core_keywords))
        
        # 如果核心关键词全部未命中 name，惩罚分数
        if core_keywords and name_hits == 0:
            penalty = 0.30 * base_score  # 增加惩罚力度
            base_score = max(0, base_score - penalty)
        
        return min(1.0, base_score + core_bonus)
    
    def _evaluate_kb_match_quality(self, entry: Dict, problem: str, keywords: List[str]) -> Tuple[float, str]:
        """
        评估 KB 条目匹配质量，返回 (调整后分数, 质量等级)
        
        关键区分：
        - L1 case：问题关键词与 KB title 高度匹配
        - L2 case：问题关键词与 KB tags 重叠，但 title 不匹配
        
        解决方案：只有 title 匹配才能获得高分
        """
        title = entry.get("title", "").lower()
        tags = " ".join(entry.get("tags", [])).lower()
        
        # 提取问题核心意图词（长度>=2的关键词）
        core_keywords = [kw for kw in keywords if len(kw) >= 2]
        if not core_keywords:
            return 0.0, "low"
        
        # 计算 title 命中率（核心判断）
        title_hits = sum(1 for kw in core_keywords if kw in title)
        title_ratio = title_hits / len(core_keywords)
        
        # 计算 tags 命中率
        tag_hits = sum(1 for kw in core_keywords if kw in tags)
        tag_ratio = tag_hits / len(core_keywords)
        
        # 质量判断：只有 title 匹配才能作为 L1
        if title_ratio >= 0.2:
            # title 匹配：高质量
            return 0.45, "high"
        
        # title 不匹配但 tags 匹配：这是 L2 case 的特征
        if tag_ratio >= 0.2:
            # 降低分数，使其低于 L1 阈值 0.35
            return 0.25, "medium"
        
        # title 和 tags 都不匹配：低质量
        return 0.15, "low"
    
    def _skill_from_kb_entry(self, entry: Dict) -> "Skill":
        """将 KB 条目包装成轻量 Skill，用于 Layer 1 执行"""
        skill_id = entry.get("id", f"kb_{hash(entry.get('title',''))}")
        title = entry.get("title", "KB Skill")
        content = entry.get("content", "")
        
        # 将 KB 内容摘要转换为步骤
        lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")][:5]
        steps = [
            SkillStep(
                step_number=i + 1,
                name=f"步骤 {i+1}",
                description=line,
                source="记忆"
            )
            for i, line in enumerate(lines or ["参考知识库内容解决问题"])
        ]
        
        return Skill(
            skill_id=str(skill_id),
            name=title,
            description=content[:120],
            version="1.0",
            status=SkillStatus.ACTIVE,
            steps=steps,
            required_inputs=[],
            outputs=["result"],
            parameters={"kb_entry": True},
            metadata=SkillMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by="kb-import"
            ),
            generation_info=GenerationInfo(
                skill_type=SkillType.MANUAL,
                confidence=self.threshold_policy.manual_skill_default_confidence
            ),

            quality_metrics=QualityMetrics()
        )
    
    def _register_lineage_skill(self, skill: "Skill", stage: str = "unknown") -> None:
        """写入谱系库；注册失败时记 WARNING 并静默继续，不中断主流程。"""
        import logging
        if not self.lineage:
            return
        try:
            self.lineage.register(skill)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "SkillLineage register 失败 [stage=%s, skill=%s]: %s",
                stage,
                getattr(skill, "skill_id", skill),
                exc,
            )

    def _try_layer_2(self, problem: str,
                     trace: Optional[list] = None) -> Tuple[Optional[ExecutionResult], Optional[Skill]]:
        """第二层：从记忆中组合"""
        try:
            from .composer import SkillComposer
        except ImportError:
            import importlib, sys
            spec = importlib.util.spec_from_file_location(
                "composer",
                str(__import__("pathlib").Path(__file__).parent / "composer.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            SkillComposer = mod.SkillComposer
        
        composer = SkillComposer(
            ltm_client=self.ltm,
            kb_client=self.kb,
            threshold_policy=self.threshold_policy,
        )

        
        # 分析问题
        problem_analysis = composer.analyze_problem(problem)
        
        # 从 LTM 搜索
        keywords = problem_analysis.get("keywords", [])
        ltm_results = composer.search_ltm(problem, keywords)
        
        # 评估是否能组合
        can_compose, assessment = composer.assess_composability(ltm_results, problem)
        if not can_compose:
            if trace is not None:
                trace.append({
                    "layer": 2,
                    "outcome": "miss",
                    "ltm_results_count": len(ltm_results) if ltm_results else 0,
                    "keywords": keywords,
                    "can_compose": False,
                    "assessment_summary": str(assessment)[:200] if assessment else None,
                    "reason": "composability check failed",
                })
            return None, None
        
        # 创建组合计划
        composition_plan = composer.create_composition_plan(problem, ltm_results, problem_analysis)

        if trace is not None:
            plan_summary = {}
            if hasattr(composition_plan, "to_dict"):
                plan_dict = composition_plan.to_dict()
                plan_summary = {
                    "framework": plan_dict.get("framework"),
                    "step_count": len(plan_dict.get("steps", [])),
                    "ltm_references_count": len(plan_dict.get("ltm_references", [])),
                }
            elif isinstance(composition_plan, dict):
                plan_summary = {
                    "framework": composition_plan.get("framework"),
                    "step_count": len(composition_plan.get("steps", [])),
                    "ltm_references_count": len(composition_plan.get("ltm_references", [])),
                }
            trace.append({
                "layer": 2,
                "outcome": "hit",
                "ltm_results_count": len(ltm_results) if ltm_results else 0,
                "keywords": keywords,
                "can_compose": True,
                "composition_plan": plan_summary,
                "reason": "composability check passed, composition plan created",
            })
        
        # 根据组合计划创建 Skill
        composed_skill = self._skill_from_composition_plan(composition_plan, problem)
        
        # 写入谱系库（Layer 2 组合生成的新 Skill）
        if self.lineage:
            try:
                self.lineage.register(composed_skill)
            except Exception:
                pass
        
        # 执行 Skill
        result = self.executor.execute(composed_skill, problem)
        
        return result, composed_skill
    
    def _try_layer_3(self, problem: str,
                     trace: Optional[list] = None) -> Tuple[Optional[ExecutionResult], Optional[Skill], Optional[Dict]]:
        """第三层：自动生成"""
        try:
            from .generator import SkillGenerator
            from .evaluator import QualityEvaluator
        except ImportError:
            import importlib
            _engine_dir = __import__("pathlib").Path(__file__).parent
            
            def _load(name):
                spec = importlib.util.spec_from_file_location(name, str(_engine_dir / f"{name}.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
            
            SkillGenerator = _load("generator").SkillGenerator
            QualityEvaluator = _load("evaluator").QualityEvaluator
        
        generator = SkillGenerator(
            ltm_client=self.ltm,
            threshold_policy=self.threshold_policy,
        )
        evaluator = QualityEvaluator(threshold_policy=self.threshold_policy)

        
        # 检查是否能生成
        available_ltm_info = self.ltm.recall(query=problem) if self.ltm else None
        can_gen, gen_feasibility = generator.can_generate(problem, available_ltm_info)
        
        if not can_gen:
            if trace is not None:
                trace.append({
                    "layer": 3,
                    "outcome": "miss",
                    "reason": "can_generate returned False",
                    "feasibility": str(gen_feasibility)[:200] if gen_feasibility else None,
                    "ltm_available": available_ltm_info is not None,
                })
            return None, None, None
        
        # 分析生成上下文
        context = generator.analyze_generation_context(problem, available_ltm_info)
        
        # 选择生成策略
        strategy = generator.select_generation_strategy(context)
        
        # 生成草稿
        skill_draft = generator.generate_skill_draft(context, strategy)
        
        # 质量评估
        assessment = evaluator.assess_skill_quality(skill_draft.to_dict())

        # 构造维度分数摘要（如果 assessment 暴露了 dimension_scores）
        dimension_scores: dict = {}
        if hasattr(assessment, "dimension_scores") and assessment.dimension_scores:
            dimension_scores = {
                k: round(float(v), 4) for k, v in assessment.dimension_scores.items()
            }
        elif hasattr(assessment, "scores") and assessment.scores:
            dimension_scores = {
                k: round(float(v), 4) for k, v in assessment.scores.items()
            }
        
        # 如果质量不够好，返回部分成功
        if not assessment.is_approved:
            if trace is not None:
                trace.append({
                    "layer": 3,
                    "outcome": "quality_gate_rejected",
                    "strategy": strategy.value if hasattr(strategy, "value") else str(strategy),
                    "overall_score": round(float(assessment.overall_score), 4),
                    "quality_gate_threshold": self.threshold_policy.layer3_quality_gate_threshold,
                    "dimension_scores": dimension_scores,
                    "ltm_results_count": len(available_ltm_info) if available_ltm_info else 0,
                    "reason": "quality gate rejected draft",
                })
            return None, None, {
                "quality": assessment.overall_score,
                "confidence": assessment.confidence_level,
                "recommendations": assessment.recommendations
            }
        
        if trace is not None:
            trace.append({
                "layer": 3,
                "outcome": "hit",
                "strategy": strategy.value if hasattr(strategy, "value") else str(strategy),
                "overall_score": round(float(assessment.overall_score), 4),
                "quality_gate_threshold": self.threshold_policy.layer3_quality_gate_threshold,
                "dimension_scores": dimension_scores,
                "ltm_results_count": len(available_ltm_info) if available_ltm_info else 0,
                "skill_draft_steps": len(skill_draft.steps) if hasattr(skill_draft, "steps") else None,
                "reason": "quality gate passed, skill generated",
            })

        # 将草稿转换为完整 Skill
        generated_skill = self._skill_from_draft(skill_draft)
        
        # 写入谱系库（Layer 3 自动生成的 Skill）
        quality_score = assessment.overall_score
        if self.lineage:
            try:
                self.lineage.register(generated_skill, quality_score=quality_score)
            except Exception:
                pass
        
        # 执行 Skill
        result = self.executor.execute(generated_skill, problem)
        
        return result, generated_skill, {
            "quality": assessment.overall_score,
            "confidence": assessment.confidence_level,
            "strategy": strategy.value,
            "generation_info": skill_draft.to_dict()
        }
    

    def solve_task(self, task, context=None, verbose=False, **kwargs):
        """
        Protocol-based task solving with tenant context extraction.
        
        Args:
            task: TaskSpec or dict with task information
            context: Optional ContextSpec
            verbose: Whether to print verbose output
            **kwargs: Additional arguments passed to solve_task_with_protocol
        
        Returns:
            ExecutionResult with feedback envelope attached
        """
        from .protocols import solve_task_with_protocol, TaskSpec, ContextSpec
        from .multi_tenant.context import TenantContext
        
        # Normalize task to TaskSpec
        if isinstance(task, dict):
            task = TaskSpec(**task)
        
        # Extract tenant info from task metadata or context
        tenant_id = kwargs.pop('tenant_id', None)
        user_id = kwargs.pop('user_id', None)
        role = kwargs.pop('role', None)
        
        if not tenant_id and hasattr(task, 'metadata') and task.metadata:
            tenant_id = task.metadata.get('tenant_id')
            user_id = task.metadata.get('user_id')
            role = task.metadata.get('role')
        
        # Use tenant context if available
        if tenant_id:
            with TenantContext.use(tenant_id, user_id=user_id, role=role):
                result = solve_task_with_protocol(self, task, context=context, verbose=verbose, **kwargs)
        else:
            result = solve_task_with_protocol(self, task, context=context, verbose=verbose, **kwargs)
        
        # Attach feedback envelope
        result = self._attach_feedback_envelope(result, task, context, tenant_id, user_id)
        return result
    
    def _attach_feedback_envelope(self, result, task, context, tenant_id, user_id):
        """Attach feedback methods to ExecutionResult."""
        if not self.feedback_collector:
            return result
        
        result._feedback_collector = self.feedback_collector
        result._feedback_context = {
            "task_id": task.task_id if hasattr(task, 'task_id') else None,
            "skill_id": result.metadata.get("selected_skill", {}).get("id") if hasattr(result, "metadata") and result.metadata else None,
            "layer_used": result.layer if hasattr(result, "layer") else None,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": context.session_id if context else None,
        }
        
        def thumbs_up():
            ctx = result._feedback_context
            return self.feedback_collector.thumbs_up(
                task_id=ctx["task_id"],
                skill_id=ctx["skill_id"],
                session_id=ctx["session_id"],
                layer_used=ctx["layer_used"],
                user_id=ctx["user_id"],
                tenant_id=ctx["tenant_id"],
            )
        
        def thumbs_down(reason=None):
            ctx = result._feedback_context
            return self.feedback_collector.thumbs_down(
                task_id=ctx["task_id"],
                skill_id=ctx["skill_id"],
                session_id=ctx["session_id"],
                layer_used=ctx["layer_used"],
                user_id=ctx["user_id"],
                tenant_id=ctx["tenant_id"],
                reason=reason,
            )
        
        def rate(rating, comment=None):
            ctx = result._feedback_context
            return self.feedback_collector.rate(
                rating=rating,
                task_id=ctx["task_id"],
                skill_id=ctx["skill_id"],
                session_id=ctx["session_id"],
                layer_used=ctx["layer_used"],
                user_id=ctx["user_id"],
                tenant_id=ctx["tenant_id"],
                comment=comment,
            )
        
        result.feedback_thumbs_up = thumbs_up
        result.feedback_thumbs_down = thumbs_down
        result.feedback_rate = rate
        return result
    def update_skill_from_feedback(self, skill_id: str, feedback: str) -> Skill:
        """
        根据用户反馈更新 Skill
        
        Args:
            skill_id: Skill ID
            feedback: 用户反馈
        
        Returns:
            更新后的 Skill
        """
        # 获取原有 Skill
        skill = self.skills_cache.get(skill_id)
        if not skill and self.kb:
            skill = self.kb.get(skill_id)
        
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")
        
        # 分析反馈
        feedback_analysis = self._analyze_feedback(feedback)
        
        # 保存旧 skill_id 作为 parent
        old_skill_id = skill.skill_id
        
        # 更新 Skill
        updated_skill = self._update_skill(skill, feedback_analysis)
        
        # 把旧版本设为父节点（谱系关联）
        updated_skill.parent_id = old_skill_id
        
        # 保存更新
        if self.kb:
            self.kb.update(skill_id, updated_skill)
        
        self.skills_cache[skill_id] = updated_skill
        
        # 注册到谱系库（fixed 进化）
        if self.lineage:
            try:
                self.lineage.register(updated_skill)
            except Exception:
                pass
        
        # 记录到 LTM（通过 _ltm_raw 直接调用，避免 TenantIsolation proxy 走 KB 路径）
        ltm_raw = getattr(self.ltm, "_ltm", None) or (self.ltm if not hasattr(self.ltm, "_ltm") else None)
        if ltm_raw:
            try:
                ltm_raw.save({
                    "content": f"Skill '{skill.name}' updated: {feedback}",
                    "category": "project",
                    "tags": ["skill-update", skill_id]
                })
            except Exception:
                pass
        
        return updated_skill
    
    def _analyze_feedback(self, feedback: str) -> Dict:
        """
        分析用户反馈，提取情感倾向、问题方面和改进建议。
        
        情感三态：
        - positive：用户满意，Skill 可提升置信度
        - negative：用户不满，Skill 需要更新
        - neutral：中性或纯描述性建议，直接追加说明
        """
        text = feedback.lower()
        
        # 正面词（整词匹配，避免被子串误命中）
        positive_signals = ["很好", "太好", "不错", "非常好", "完美", "棒", "对的", "准确",
                            "有用", "great", "perfect", "correct", "useful", "good job",
                            "excellent", "awesome", "well done", "nice work"]
        # 负面词
        negative_signals = ["不对", "错误", "缺少", "没有", "漏掉", "不够", "差",
                            "wrong", "missing", "incorrect", "bad", "fail", "error",
                            "怎么不", "为什么不", "应该", "需要加", "还差", "不全"]
        # 方面词映射
        aspect_keywords = {
            "步骤": ["步骤", "流程", "顺序", "step", "process"],
            "内容": ["内容", "描述", "说明", "detail", "content", "description"],
            "数量": ["太少", "太多", "数量", "count"],
            "方向": ["方向", "思路", "角度", "approach", "direction"],
            "数据": ["数据", "分析", "统计", "data", "analysis"],
            "格式": ["格式", "排版", "结构", "format", "structure"],
        }
        
        # 判断情感
        pos_count = sum(1 for w in positive_signals if w in text)
        neg_count = sum(1 for w in negative_signals if w in text)
        
        if neg_count > pos_count:
            sentiment = "negative"
        elif pos_count > neg_count:
            sentiment = "positive"
        else:
            sentiment = "neutral"
        
        # 提取方面
        aspect = "general"
        for asp, keywords in aspect_keywords.items():
            if any(kw in text for kw in keywords):
                aspect = asp
                break
        
        # 提取改进建议（截取前 200 字）
        suggestion = feedback.strip()[:200]
        
        return {
            "sentiment": sentiment,
            "aspect": aspect,
            "suggestion": suggestion,
            "positive_signals": pos_count,
            "negative_signals": neg_count
        }
    
    def _update_skill(self, skill: Skill, feedback_analysis: Dict) -> Skill:
        """根据反馈更新 Skill"""
        # 更新元数据
        skill.metadata.updated_at = datetime.now()
        skill.metadata.update_reason = feedback_analysis["suggestion"]
        skill.metadata.last_challenged_at = datetime.now()
        
        # 记录旧版本到谱系
        old_version = skill.version
        major, minor = map(int, old_version.split('.')[:2])
        minor += 1
        new_version = f"{major}.{minor}"
        
        # 记录到版本历史
        skill.versions[old_version] = {
            "timestamp": datetime.now().isoformat(),
            "reason": feedback_analysis["suggestion"],
            "skill_id_snapshot": skill.skill_id,  # 记录此时的 ID，供 DAG 回溯
        }
        
        skill.version = new_version
        
        # 更新进化类型（被用户反馈修复 → fixed）
        if feedback_analysis["sentiment"] == "negative":
            skill.evolution_type = "fixed"
        
        return skill
    
    def _skill_from_composition_plan(self, composition_plan: Any, problem: str) -> Skill:
        """从组合计划创建 Skill"""
        skill_id = f"composed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        steps = []
        for i, component in enumerate(composition_plan.components):
            step = SkillStep(
                step_number=i + 1,
                name=component.get("step", f"Step {i + 1}"),
                description=component.get("aspect", ""),
                source="记忆" if component["source"] != "framework" else "框架",
                customization=f"根据问题调整: {problem[:50]}"
            )
            steps.append(step)
        
        adaptation_strategy = composition_plan.adaptation_strategy
        
        skill = Skill(
            skill_id=skill_id,
            name=f"组合 Skill: {problem[:30]}",
            description=f"从 {len([c for c in composition_plan.components if c['source'] != 'framework'])} 个 LTM 源组合生成",
            version="1.0",
            status=SkillStatus.EXPERIMENTAL,
            steps=steps,
            required_inputs=[],
            outputs=["result"],
            parameters={"adaptation_strategy": adaptation_strategy},
            metadata=SkillMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by="ai-generated"
            ),
            generation_info=GenerationInfo(
                skill_type=SkillType.COMPOSED,
                ltm_references=[c.get("source") for c in composition_plan.components if c["source"] != "framework"],
                confidence=composition_plan.estimated_quality,
                needs_verification=self.threshold_policy.layer2_composed_needs_verification(
                    composition_plan.estimated_quality
                )
            ),

            quality_metrics=QualityMetrics()
        )
        
        return skill
    
    def _skill_from_draft(self, skill_draft: Any) -> Skill:
        """从生成的草稿创建完整 Skill"""
        steps = []
        for step_data in skill_draft.steps:
            step = SkillStep(
                step_number=step_data.get("step", 0),
                name=step_data.get("name", ""),
                description=step_data.get("description", ""),
                source=step_data.get("source", "自动生成")
            )
            steps.append(step)
        
        skill = Skill(
            skill_id=skill_draft.skill_id,
            name=skill_draft.name,
            description=skill_draft.description,
            version="1.0-beta",
            status=SkillStatus.EXPERIMENTAL,
            steps=steps,
            required_inputs=[],
            outputs=["result"],
            parameters={
                "strategy": skill_draft.generation_strategy.value,
                "verification_checklist": skill_draft.verification_checklist
            },
            metadata=SkillMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
                created_by="ai-generated",
                update_reason=f"自动生成: {skill_draft.rationale}"
            ),
            generation_info=GenerationInfo(
                skill_type=SkillType.AUTO_GENERATED,
                ltm_references=skill_draft.ltm_references,
                confidence=skill_draft.confidence,
                needs_verification=skill_draft.needs_verification
            ),
            quality_metrics=QualityMetrics()
        )
        
        return skill


if __name__ == "__main__":
    # 示例：创建并执行一个 Skill
    
    # 创建一个简单的 Skill
    skill = Skill(
        skill_id="skill-demo-001",
        name="Demo Skill",
        description="A simple demo skill",
        version="1.0",
        status=SkillStatus.ACTIVE,
        steps=[
            SkillStep(
                step_number=1,
                name="Step 1",
                description="First step",
                source="框架"
            ),
            SkillStep(
                step_number=2,
                name="Step 2",
                description="Second step",
                source="记忆"
            )
        ],
        required_inputs=["input1", "input2"],
        outputs=["output1"],
        parameters={},
        metadata=SkillMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user"
        ),
        generation_info=GenerationInfo(
            skill_type=SkillType.MANUAL
        ),
        quality_metrics=QualityMetrics()
    )
    
    # 执行 Skill
    executor = SkillExecutor()
    result = executor.execute(skill, "Demo problem")
    print(json.dumps(result.to_dict(), indent=2, default=str))
    
    # 创建系统并测试
    system = AdaptiveSkillSystem()
    response = system.solve("How to solve this problem?", verbose=True)
    print(json.dumps(response.to_dict(), indent=2, default=str))
