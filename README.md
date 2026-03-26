# Adaptive Skill System

**三层递进 AI Skill 引擎 — 让 AI 在复杂问题上自动学习进化**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-23%20passed-brightgreen.svg)](#tests)

[English](#english) | 中文

---

## 核心思想

传统 AI 只会"给答案"。当问题超出能力范围时，它要么胡说，要么放弃。

**Adaptive Skill System** 解决这个问题：

> 当 AI 无法直接解答时，不是认输，而是**自动组合已有经验**或**生成新的解题方案**。

---

## 三层递进架构

```
用户提问
    │
    ▼
┌─────────────────────────────────────┐
│  Layer 1: 直接命中（< 1 秒）         │
│  搜索 KB 缓存，找到已有 Skill 直接用  │
└──────────────┬──────────────────────┘
               │ 未命中
               ▼
┌─────────────────────────────────────┐
│  Layer 2: 组合生成（10-30 秒）       │
│  从 LTM 搜索相关碎片，组合成新方案   │
└──────────────┬──────────────────────┘
               │ 置信度不足
               ▼
┌─────────────────────────────────────┐
│  Layer 3: 自动生成（1-5 分钟）       │
│  4种生成策略 × 7维度质量评估         │
│  通过阈值后自动保存到 KB             │
└─────────────────────────────────────┘
```

| 层级 | 响应时间 | 可靠性 | 触发条件 |
|------|---------|--------|---------|
| Layer 1 | < 1s | 最高 | KB 命中率 ≥ 40% |
| Layer 2 | 10-30s | 较高 | LTM 可组合 |
| Layer 3 | 1-5min | 中等 | 前两层均失败 |

---

## 快速开始

### 安装

```bash
git clone https://github.com/sdenilson212/adaptive-skill-system.git
cd adaptive-skill-system
pip install -e .
```

### 最简使用

```python
from adaptive_skill import AdaptiveSkillSystem, KBClient, LTMClient

# 实现你自己的客户端（或使用内置 Mock）
class MyKBClient(KBClient):
    def search(self, query, top_k=5):
        # 对接你的知识库
        return []

    def save(self, entry):
        pass

class MyLTMClient(LTMClient):
    def search(self, query, max_results=10):
        return []

    def save(self, content, category, tags):
        pass

# 初始化
system = AdaptiveSkillSystem(
    kb_client=MyKBClient(),
    ltm_client=MyLTMClient()
)

# 解题
result = system.solve("如何制定一份针对 Z 世代的运营策略？")

print(f"状态: {result.status}")
print(f"使用层级: Layer {result.layer_used}")
print(f"置信度: {result.skill.metadata.confidence_score:.0%}")
for step in result.skill.steps:
    print(f"  步骤 {step.step_number}: {step.name}")
```

### 反馈驱动学习

```python
# 用户觉得结果不够好
result2 = system.solve(
    "如何制定一份针对 Z 世代的运营策略？",
    feedback="方案里没有考虑预算约束，能加上吗？"
)
# 系统会自动将修改后的方案保存到 KB，下次更快更准
```

---

## 四种生成策略（Layer 3）

| 策略 | 适用场景 | 说明 |
|------|---------|------|
| 模板法 | 结构化问题 | 套用已有框架模板 |
| 类比法 | 跨域迁移 | 从相似领域借鉴思路 |
| 分解法 | 复杂大问题 | 拆分为子问题逐个解决 |
| 混合法 | 高复杂度 | 综合运用以上三种 |

策略选择由系统自动完成，基于问题的关键词、历史记录和复杂度判断。

---

## 7 维度质量评估

每个自动生成的 Skill 都经过严格评分，**总分 ≥ 0.70 才会被自动保存**：

| 维度 | 权重 | 说明 |
|------|------|------|
| 完整性 | 15% | 是否覆盖问题所有方面 |
| 清晰度 | 15% | 表达是否清晰易懂 |
| 可行性 | 20% | 步骤是否可执行 |
| 证据支持 | 15% | 方案是否有依据 |
| 泛化性 | 10% | 是否可复用于类似问题 |
| 新颖性 | 10% | 是否有独特洞见 |
| 风险缓解 | 15% | 是否考虑了潜在风险 |

---

## 运行测试

```bash
cd adaptive-skill-system
python -m pytest tests/ -v
```

期望输出：
```
23 passed in 0.16s
```

---

## 项目结构

```
adaptive-skill-system/
├── adaptive_skill/
│   ├── __init__.py       # 公共 API
│   ├── core.py           # 核心引擎（三层递进，1088行）
│   ├── composer.py       # Layer 2 组合引擎（415行）
│   ├── generator.py      # Layer 3 生成引擎（523行）
│   └── evaluator.py      # 质量评估引擎（414行）
├── tests/
│   └── test_core.py      # 23个单元测试
├── docs/
│   ├── ARCHITECTURE.md   # 完整架构设计（2000+行）
│   ├── IMPLEMENTATION_GUIDE.md
│   └── DEEPENING_SUMMARY.md
├── README.md
├── requirements.txt
└── setup.py
```

---

## 与 AI Memory System 的关系

本项目是 [AI Memory System](https://github.com/sdenilson212/ai-memory-system) 的**独立执行层**：

```
AI Memory System（记忆层）
    ↕ 读写
Adaptive Skill System（执行层）← 本项目
    ↕ 接口
你的 AI 应用
```

两个系统可以单独使用，也可以配合使用获得最大效果。

---

## English

**Adaptive Skill System** — A three-layer progressive AI skill engine that enables AI to automatically learn and evolve when facing complex problems.

### Key Features
- **Layer 1**: Direct KB cache hit (< 1s)
- **Layer 2**: LTM-based composition (10-30s)
- **Layer 3**: Auto-generation with 4 strategies × 7-dimension quality evaluation (1-5min)
- **Feedback-driven learning**: AI improves from user corrections
- **No external dependencies**: Pure Python 3.8+, stdlib only

---

## License

MIT © [sdenilson212](https://github.com/sdenilson212)
