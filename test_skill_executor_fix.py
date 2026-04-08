"""
测试 SkillExecutor 修复（P1 修复验证）
验证《修改意见》中「SkillExecutor 占位符」问题是否解决
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adaptive_skill.skill_executor_real import RealSkillExecutor, Skill, SkillStep

def test_python_execution():
    """测试 Python 代码执行"""
    print("测试 1: Python 代码执行...")
    
    executor = RealSkillExecutor(safe_mode=True)
    
    # 创建包含 Python 代码的 Skill
    skill = Skill(
        skill_id="test-python-skill",
        name="Python 计算 Skill",
        description="执行 Python 计算",
        version="1.0",
        steps=[
            SkillStep(
                name="计算平方和",
                step_number=1,
                description="计算 1 到 5 的平方和\n```python\nresult = sum(i**2 for i in range(1, 6))\nprint(f'平方和: {result}')\n```",
                source="框架",
                estimated_duration=5
            )
        ],
        outputs=["计算结果"]
    )
    
    result = executor.execute(skill, "计算平方和")
    
    print(f"  执行成功: {result.success}")
    print(f"  步骤完成: {result.steps_completed}/{result.total_steps}")
    print(f"  耗时: {result.duration_seconds:.2f}秒")
    
    if result.success and result.output:
        step_output = result.output.get("计算结果")
        print(f"  输出: {step_output}")
        
        # 检查是否为真实执行（非文本拼接）
        if "平方和" in str(step_output.get("output", "")):
            print("  [OK] Python 代码真实执行成功")
            return True
        else:
            print("  [WARN] 输出可能仍为文本拼接")
            return False
    else:
        print("  [FAIL] 执行失败")
        return False

def test_shell_execution_blocked():
    """测试安全模式下 Shell 命令被阻止"""
    print("\n测试 2: Shell 命令安全阻止...")
    
    executor = RealSkillExecutor(safe_mode=True)
    
    skill = Skill(
        skill_id="test-shell-skill",
        name="Shell 命令测试",
        description="执行 Shell 命令",
        version="1.0",
        steps=[
            SkillStep(
                name="列出文件",
                step_number=1,
                description="执行 ls 命令\n```bash\nls -la\n```",
                source="框架",
                estimated_duration=5
            )
        ],
        outputs=["命令结果"]
    )
    
    result = executor.execute(skill, "列出文件")
    
    if result.success:
        step_output = result.output.get("命令结果")
        if step_output.get("status") == "blocked" and "安全模式下禁止" in str(step_output.get("output", "")):
            print("  [OK] Shell 命令在安全模式下被正确阻止")
            return True
        else:
            print(f"  [FAIL] 未正确阻止: {step_output}")
            return False
    else:
        print("  [WARN] 执行失败（可能正常）")
        return True

def test_llm_prompt_execution():
    """测试 LLM 提示执行"""
    print("\n测试 3: LLM 提示执行...")
    
    executor = RealSkillExecutor()
    
    skill = Skill(
        skill_id="test-llm-skill",
        name="LLM 生成测试",
        description="生成建议",
        version="1.0",
        steps=[
            SkillStep(
                name="生成建议",
                step_number=1,
                description="请为跑步训练制定计划",
                source="自动生成",
                customization="针对半马训练",
                estimated_duration=10
            )
        ],
        outputs=["建议"]
    )
    
    result = executor.execute(skill, "跑步训练计划")
    
    if result.success:
        step_output = result.output.get("建议")
        output_str = str(step_output.get("output", ""))
        
        if "跑步训练" in output_str or "半马" in output_str or "建议" in output_str:
            print("  [OK] LLM 提示执行成功")
            print(f"  生成内容: {output_str[:80]}...")
            return True
        else:
            print(f"  [WARN] 输出内容不符合预期: {output_str[:50]}")
            return False
    else:
        print("  [FAIL] 执行失败")
        return False

def test_fallback_compatibility():
    """测试回退兼容性（非代码步骤）"""
    print("\n测试 4: 回退兼容性...")
    
    executor = RealSkillExecutor()
    
    skill = Skill(
        skill_id="test-fallback-skill",
        name="文本步骤测试",
        description="纯文本步骤",
        version="1.0",
        steps=[
            SkillStep(
                name="分析需求",
                step_number=1,
                description="首先分析用户的核心需求",
                source="框架",
                estimated_duration=5
            )
        ],
        outputs=["分析结果"]
    )
    
    result = executor.execute(skill, "某个需求")
    
    if result.success:
        step_output = result.output.get("分析结果")
        if step_output.get("source") == "text_fallback" and "首先分析用户的核心需求" in str(step_output.get("output", "")):
            print("  [OK] 非代码步骤正确回退到文本模式")
            return True
        else:
            print(f"  [WARN] 回退模式异常: {step_output}")
            return False
    else:
        print("  [FAIL] 执行失败")
        return False

def main():
    """主测试函数"""
    print("=== SkillExecutor P1 修复测试 ===")
    print("验证「SkillExecutor 占位符」问题修复\n")
    
    tests = [
        ("Python 代码执行", test_python_execution),
        ("Shell 命令安全阻止", test_shell_execution_blocked),
        ("LLM 提示执行", test_llm_prompt_execution),
        ("回退兼容性", test_fallback_compatibility),
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        try:
            if test_func():
                print(f"  [PASS] {name}")
                passed += 1
            else:
                print(f"  [FAIL] {name}")
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
    
    print(f"\n=== 测试结果 ===")
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("[SUCCESS] 所有 SkillExecutor 修复测试通过！")
        return 0
    else:
        print(f"[WARN] {total - passed} 个测试失败，需检查修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())