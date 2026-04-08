# 简单测试 SkillExecutor 修复
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adaptive_skill.skill_executor_real import RealSkillExecutor, Skill, SkillStep

# 测试 1: 创建执行器
executor = RealSkillExecutor(safe_mode=True)
print("创建执行器成功")

# 测试 2: 创建简单 Skill
skill = Skill(
    skill_id="test-skill-1",
    name="测试 Skill",
    description="测试执行",
    steps=[
        SkillStep(
            name="步骤1",
            step_number=1,
            description="这是一个测试步骤",
            source="框架"
        )
    ]
)

print(f"创建 Skill: {skill.name}")

# 测试 3: 执行
result = executor.execute(skill, "测试问题")
print(f"执行结果: {result.success}")
print(f"步骤完成: {result.steps_completed}/{result.total_steps}")
print(f"输出类型: {type(result.output)}")

if result.success:
    print("测试通过: SkillExecutor 能正常执行")
else:
    print(f"执行失败: {result.error_message}")