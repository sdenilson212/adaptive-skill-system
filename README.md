# Adaptive Skill System

**三层递进 AI Skill 引擎 — 让 AI 在复杂问题上自动学习进化**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-394%20passed-brightgreen.svg)](#运行测试)


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

class MyKBClient(KBClient):
    def search(self, query, top_k=5):
        return []
    def save(self, entry):
        pass

class MyLTMClient(LTMClient):
    def search(self, query, max_results=10):
        return []
    def save(self, content, category, tags):
        pass

system = AdaptiveSkillSystem(
    kb_client=MyKBClient(),
    ltm_client=MyLTMClient()
)

result = system.solve("如何制定一份针对 Z 世代的运营策略？")
print(f"状态: {result.status}")
print(f"使用层级: Layer {result.layer_used}")
print(f"置信度: {result.skill.metadata.confidence_score:.0%}")
```

### 反馈驱动学习

```python
result2 = system.solve(
    "如何制定一份针对 Z 世代的运营策略？",
    feedback="方案里没有考虑预算约束，能加上吗？"
)
# 系统会自动将修改后的方案保存到 KB，下次更快更准
```

### Harness Reporting CLI

安装为可编辑包后，可以直接把持久化的 `BatchResult.to_dict()` JSON 转成 P4 报告：

```bash
adaptive-skill-report path/to/batch-result.json --output-dir reports
```

如果已经锁定 baseline，还可以顺手做 regression check：

```bash
adaptive-skill-report path/to/batch-result.json \
  --baseline harness_baselines/v1.0.0.json \
  --output-dir reports \
  --fail-on-regression
```

产出物：
- `*.json`：结构化报告 payload
- `*.md`：适合 review / CI artifact 的文本报告
- `*.html`：可直接打开浏览的可视化报告

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
python -m pytest tests -q
```

当前主线期望输出：
```
353 passed
```

### GitHub Actions CI

仓库现在自带 `.github/workflows/ci.yml`，默认会在 push / pull request / workflow_dispatch 时执行四段链路：

1. `python -m pytest tests -q` —— 真实代码主线门禁
2. `python scripts/run_harness_ci_suite.py` —— 生成确定性的 harness smoke batch + metrics
3. `python scripts/run_harness_real_benchmark.py --baseline harness_baselines/real-benchmark-v2.json` —— 生成真实 solver 的 seeded benchmark artifact，并附带 advisory regression 结果
4. `adaptive-skill-report ... --baseline harness_baselines/ci-smoke-v1.json --fail-on-regression` —— 产出 JSON / Markdown / HTML 报告，并在 smoke baseline 回归时让 CI 直接失败

CI artifact 会上传到 `.ci-artifacts/`，其中包含：
- `pytest.xml`
- `harness/harness-batch-result.json`
- `harness/harness-metrics.json`
- `reports/adaptive-skill-harness-ci.{json,md,html}`
- `real-benchmark/real-benchmark-batch-result.json`
- `real-benchmark/real-benchmark-metrics.json`
- `real-benchmark/reports/adaptive-skill-harness-real-benchmark.{json,md,html}`

说明：
- smoke batch 仍然是唯一强 gate，用来稳定覆盖 reporting / baseline / regression 主链路
- seeded real benchmark 现在也会随 CI 一起产出，但当前只作为观察真实 solver 表现的 artifact，不直接卡 workflow
- 真正的仓库代码正确性仍以 `pytest tests -q` 为准

### Seeded Real Benchmark

除了 CI smoke suite，仓库现在还提供一条面向真实 solver 的 seeded benchmark 链路：

```bash
python scripts/run_harness_real_benchmark.py \
  --output-dir .benchmark-artifacts/real-benchmark \
  --baseline-out harness_baselines/real-benchmark-v2.json
```

这条链路的特点：
- 跑的是真实 `AdaptiveSkillSystem.solve()`，不是合成结果
- KB/LTM 使用内存 seed，不依赖开发机本地 memory bank
- 固定覆盖 6 个代表性 case：Layer 1 × 1、Layer 2 × 2、Layer 3 × 3
- 新增覆盖面包括：Layer 2 多源组合边界、Layer 3 稀疏上下文、Layer 3 list-shaped recall 回归保护
- 会同时产出 `BatchResult`、`Metrics`、JSON/Markdown/HTML 报告，以及可提交的 baseline

当前基线：`harness_baselines/real-benchmark-v2.json`

本地做 regression check：

```bash
python scripts/run_harness_real_benchmark.py \
  --output-dir .benchmark-artifacts/real-benchmark-check \
  --baseline harness_baselines/real-benchmark-v2.json \
  --fail-on-regression
```

说明：real benchmark 默认把 `p95_latency_increase_pct` 放宽到 `200%`，因为这条链路的单次耗时只有几毫秒，机器抖动很容易把默认 `50%` 阈值打穿；这里更关注 solver 行为回归，而不是微小的本地延迟波动。

当前 benchmark v2 基线表现：
- `pass_rate = 1.0000`
- `avg_score = 0.8417`
- `layer_distribution = {1:1, 2:2, 3:3}`

### Release Claim Gate（对外口径）

如果要更新 README、release note、里程碑总结或任何对外 capability claim，当前统一先跑：

```bash
python scripts/run_release_claim_gate.py \
  --output-dir .benchmark-artifacts/release-claim-gate \
  --include-real-benchmark
```

这条收口命令会固定执行：
1. `pytest tests -q --tb=short`
2. `ci-smoke-v1` batch + regression report
3. `claim-benchmark-v2` release gate（当前正式对外证据）
4. `real-benchmark-v2` advisory diagnostics（可选观察项，不直接阻断 claim）

当前对外口径约定：
- 只有 `release-claim-gate-summary` 的 `overall_verdict` 为 `PASS` 或 `PASS_WITH_ADVISORY`，才允许更新 README / release note / 外部说明。
- `claim-benchmark-v2`（36-case seeded suite）是当前唯一的 release-grade evidence source。
- `claim-benchmark-v1` 已冻结，只保留历史对照职责，不再作为默认对外 claim 口径。

当前可引用的 v2 证据口径：
- `claim-benchmark-v2`: `36/36` passed
- `pass_rate = 1.0000`
- `avg_score = 0.9333`
- Wilson 95% CI lower bound = `0.9036`
- 旧口径 `claim-benchmark-v1`: `18/18` passed，仅保留为历史对照，不再代表当前默认 claim

更完整的 benchmark 治理说明见：`docs/BENCHMARK_GOVERNANCE.md`


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
│   ├── BENCHMARK_GOVERNANCE.md
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

## License

MIT © [sdenilson212](https://github.com/sdenilson212)

---

<a name="english"></a>

## English

**Adaptive Skill System** — A three-layer progressive AI Skill engine that enables AI to automatically learn and evolve when facing complex problems.

### The Problem

Traditional AI only "gives answers". When a problem exceeds its capability, it either hallucinates or gives up.

**Adaptive Skill System** changes this:

> When AI cannot answer directly, instead of failing, it **automatically combines existing knowledge** or **generates a new solution strategy**.

---

### Three-Layer Architecture

```
User query
    │
    ▼
┌─────────────────────────────────────┐
│  Layer 1: Direct hit  (< 1s)        │
│  Search KB cache, return cached Skill│
└──────────────┬──────────────────────┘
               │ Cache miss
               ▼
┌─────────────────────────────────────┐
│  Layer 2: Composition  (10-30s)     │
│  Search LTM fragments, combine      │
└──────────────┬──────────────────────┘
               │ Confidence too low
               ▼
┌─────────────────────────────────────┐
│  Layer 3: Auto-generation  (1-5min) │
│  4 strategies × 7-dimension scoring │
│  Auto-save to KB on pass            │
└─────────────────────────────────────┘
```

| Layer | Response Time | Reliability | Trigger |
|-------|--------------|-------------|---------|
| Layer 1 | < 1s | Highest | KB hit rate ≥ 40% |
| Layer 2 | 10-30s | High | LTM composable |
| Layer 3 | 1-5min | Medium | Layers 1 & 2 both failed |

---

### Quick Start

```bash
git clone https://github.com/sdenilson212/adaptive-skill-system.git
cd adaptive-skill-system
pip install -e .
```

```python
from adaptive_skill import AdaptiveSkillSystem, KBClient, LTMClient

# Implement your own clients (or use the built-in Mock)
class MyKBClient(KBClient):
    def search(self, query, top_k=5):
        return []  # connect to your knowledge base
    def save(self, entry):
        pass

class MyLTMClient(LTMClient):
    def search(self, query, max_results=10):
        return []  # connect to your long-term memory
    def save(self, content, category, tags):
        pass

system = AdaptiveSkillSystem(
    kb_client=MyKBClient(),
    ltm_client=MyLTMClient()
)

result = system.solve("How to design a marketing strategy for Gen Z?")

print(f"Status:      {result.status}")
print(f"Layer used:  Layer {result.layer_used}")
print(f"Confidence:  {result.skill.metadata.confidence_score:.0%}")
for step in result.skill.steps:
    print(f"  Step {step.step_number}: {step.name}")
```

### Feedback-Driven Learning

```python
# User is not satisfied with the initial result
result2 = system.solve(
    "How to design a marketing strategy for Gen Z?",
    feedback="The plan doesn't consider budget constraints, can you add that?"
)
# The improved plan is automatically saved to KB — next query is faster and more accurate
```

---

### Four Generation Strategies (Layer 3)

| Strategy | Best For | Description |
|----------|---------|-------------|
| Template | Structured problems | Apply an existing framework template |
| Analogy | Cross-domain transfer | Borrow ideas from a similar field |
| Decomposition | Complex large problems | Break into sub-problems and solve each |
| Hybrid | High complexity | Combine all three strategies above |

Strategy selection is fully automatic, based on problem keywords, history, and complexity score.

---

### 7-Dimension Quality Evaluation

Every auto-generated Skill is scored across 7 dimensions. **A total score ≥ 0.70 is required for auto-save**:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Completeness | 15% | Does the solution cover all aspects? |
| Clarity | 15% | Is the solution clearly expressed? |
| Feasibility | 20% | Are the steps actionable? |
| Evidence | 15% | Is the solution backed by solid reasoning? |
| Generalizability | 10% | Can it be reused for similar problems? |
| Novelty | 10% | Does it offer unique insight? |
| Risk Mitigation | 15% | Does it address potential risks? |

---

### Running Tests

```bash
python -m pytest tests/ -v
# Expected: 23 passed
```

---

### Relationship with AI Memory System

This project is the **execution layer** built on top of [AI Memory System](https://github.com/sdenilson212/ai-memory-system):

```
AI Memory System  (memory layer — stores LTM + KB)
        ↕
Adaptive Skill System  (execution layer — this project)
        ↕
Your AI application
```

Both systems can be used independently, or together for maximum effect.

---

### License

MIT © [sdenilson212](https://github.com/sdenilson212)
