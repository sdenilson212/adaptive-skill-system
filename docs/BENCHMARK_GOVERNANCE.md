# Benchmark Governance

最后更新：2026-04-06

## 1. 这份文档解决什么问题

Adaptive Skill System 现在已经同时拥有四条需要明确治理口径的 benchmark 线，以及两条冻结历史线：

- `ci-smoke-v1`：验证 harness plumbing / reporting / baseline / regression 链路
- `real-benchmark-v2`：验证真实 `AdaptiveSkillSystem.solve()` 主链路在隔离 seed 下是否稳定
- `claim-benchmark-v2`：当前正式的 release-grade claim suite，覆盖 36 个难度分层 case
- `claim-benchmark-v1`：上一代 18-case claim baseline，现已冻结为历史对照
- `real-benchmark-v1`：旧版 seeded real suite，现已冻结为历史对照

如果不把这些线的职责写死，后面很容易出现四个问题：

1. 把 synthetic smoke 当成真实能力 benchmark
2. 把 seeded real benchmark 和 release-grade claim baseline 混用
3. 继续沿用旧的 `claim-benchmark-v1` 口径，但实际上 suite 规模和覆盖范围已经升级到 v2
4. baseline 被“顺手刷新”，但没人说得清为什么该升版、什么结果可以对外引用

这份文档的目标，就是把 suite 分工、baseline 升版、回归门禁、对外 claim 口径一次收口。

---

## 2. 当前 suite 注册表

| Suite ID | 性质 | 数据来源 | 当前规模 | 主用途 | 当前 baseline | 门禁级别 |
|---|---|---|---:|---|---|---|
| `ci-smoke-v1` | synthetic / deterministic | `scripts/run_harness_ci_suite.py` 直接构造 `RunResult` | 12 cases（L1:4 / L2:4 / L3:4） | 保证 reporting、baseline、regression 链路稳定；作为 CI smoke gate | `harness_baselines/ci-smoke-v1.json` | Hard gate |
| `real-benchmark-v2` | seeded real solver benchmark | `scripts/run_harness_real_benchmark.py` + `adaptive_skill/harness/benchmark_suite.py` | 6 cases（L1:1 / L2:2 / L3:3） | 观察真实 solver 主链路是否行为回归；开发期 seeded real baseline | `harness_baselines/real-benchmark-v2.json` | Advisory |
| `claim-benchmark-v2` | seeded release-grade benchmark | `scripts/run_harness_claim_benchmark_v2.py` + `adaptive_skill/harness/claim_benchmark_v2_suite.py` | 36 cases（L1:12 / L2:12 / L3:12） | 当前正式 release note、里程碑总结、对外 capability claim 的可复现证据 | `harness_baselines/claim-benchmark-v2.json` | Release evidence |
| `claim-benchmark-v1` | frozen predecessor release benchmark | `scripts/run_harness_claim_benchmark.py` + `adaptive_skill/harness/claim_benchmark_suite.py` | 18 cases（L1:6 / L2:6 / L3:6） | 历史对照、旧口径复盘、v1→v2 扩容前后对比 | `harness_baselines/claim-benchmark-v1.json` | Frozen release evidence |
| `real-benchmark-v1` | legacy baseline | 旧版 seeded real suite | 3 cases | 历史对照，不再作为主基线 | `harness_baselines/real-benchmark-v1.json` | Frozen |

### 2.1 当前状态快照（2026-04-06）

- `ci-smoke-v1`：N=12，`pass_rate = 0.5000`
- `real-benchmark-v2`：N=6，`pass_rate = 1.0000`，`avg_score = 0.8417`
- `claim-benchmark-v2`：N=36，`pass_rate = 1.0000`，`avg_score = 0.8961`，Wilson 95% CI lower bound = `0.9036`
- `claim-benchmark-v1`：N=18，`pass_rate = 1.0000`，Wilson 95% CI lower bound = `0.8241`（冻结历史基线）

说明：

- `ci-smoke-v1` 故意包含 pass / partial / fail 分布，它的价值是稳定 gate，不是证明 solver 很强
- `real-benchmark-v2` 是真实求解路径的开发期基线，但样本量仍偏小，不能直接拿来做对外 production claim
- `claim-benchmark-v2` 已锁定 `harness_baselines/claim-benchmark-v2.json`，是当前唯一允许用于 release-grade 引用的 benchmark baseline
- `claim-benchmark-v1` 保留为冻结历史证据线，用于解释从 18-case 到 36-case 的 suite 升版过程，不再作为默认对外口径

---

## 3. 分工边界：每条线到底负责什么

### 3.1 `ci-smoke-v1`

**负责：**

- regression 机制本身是否正常工作
- report bundle（JSON / Markdown / HTML）是否能稳定生成
- layer/tag slice 指标是否持续可用
- CI artifacts 是否具备最小可诊断性

**不负责：**

- 证明真实 solver 在代表性任务上的能力
- 支撑外部 capability claim
- 评估真实 KB/LTM 组合行为

一句话：`ci-smoke-v1` 是 harness 工程基线，不是 solver 能力基线。

### 3.2 `real-benchmark-v2`

**负责：**

- 验证真实 `AdaptiveSkillSystem.solve()` 在隔离 seed 下是否出现行为回归
- 覆盖 Layer 2 多源组合边界、Layer 3 稀疏上下文、list-shaped recall 回归保护
- 为开发阶段提供“真实主链路有没有变坏”的观测面

**不负责：**

- 对外发布“生产级能力”结论
- 替代 `pytest` 的代码正确性门禁
- 替代 `claim-benchmark-v2` 的 release-grade 证据职责

一句话：`real-benchmark-v2` 是 seeded real smoke，不是最终 claim 套件。

### 3.3 `claim-benchmark-v2`

**负责：**

- 为版本发布、能力说明、里程碑总结提供可审计、可复现、真实求解路径证据
- 作为当前唯一的 release-grade seeded benchmark 引用源
- 用 36-case、难度分层（easy / medium / hard）的 suite 给出比 v1 更完整、但仍可验证的能力表述
- 约束对外说法必须显式绑定 suite 名称、样本规模、seed 语义和 solver 路径

**不负责：**

- 作为每个 PR 的日常强门禁
- 证明“任意真实世界任务都 production-ready”
- 替代 `ci-smoke-v1` 的快速反馈职责
- 取代详细 case-level 诊断与 `pytest` 失败分析

一句话：`claim-benchmark-v2` 是“当前可正式引用的证据集”，不是“真实世界全覆盖”的证明。

### 3.4 `claim-benchmark-v1`（冻结）

**负责：**

- 保留 v1 发布口径的历史连续性
- 作为 v1→v2 suite 扩容、难度分层和覆盖范围变化的对照参照物
- 在需要解释旧版文档、旧版 release note 或旧版 baseline 时提供冻结事实源

**不负责：**

- 作为当前默认 release-grade evidence source
- 参与每次 CI / milestone 的常规门禁
- 代表已经升级后的 v2 claim 覆盖范围

一句话：`claim-benchmark-v1` 是冻结历史基线，不是当前正式 claim 基线。

---

## 4. 门禁策略：什么是 hard gate，什么只是观察信号

### 4.1 当前正式策略

| 检查项 | 触发场景 | 作用 | 级别 |
|---|---|---|---|
| `python -m pytest tests -q` | 每次 CI / 本地回归 | 仓库代码正确性主门禁 | Hard gate |
| `ci-smoke-v1` + `adaptive-skill-report --fail-on-regression` | 每次 CI | harness reporting / regression 主链路门禁 | Hard gate |
| `real-benchmark-v2 --baseline ...` | 每次 CI 产物 | 真实 solver 行为观察与诊断 | Advisory |
| `claim-benchmark-v2 --baseline ...` | 发布前 / milestone 前 / 对外 claim 前 | 当前 release-grade benchmark 证据 | Required for claim |
| `scripts/run_release_claim_gate.py` | 发布前 / milestone 前 / 对外 claim 前 | 固定执行 `pytest` → `ci-smoke-v1` hard gate → `claim-benchmark-v2` release gate，并产出统一 summary bundle | Recommended wrapper |
| `claim-benchmark-v1 --baseline ...` | 仅在历史复盘或旧口径核对时 | 冻结对照，不参与默认决策 | Frozen reference |


### 4.2 为什么不是所有 benchmark 都进 CI 强卡

原因不是“它们不重要”，而是几条线的工作目标不同：

- `ci-smoke-v1` 追求稳定、快速、低噪声，适合做每次 PR 的强门禁
- `real-benchmark-v2` 追求真实行为观测，但样本仍少、毫秒级延迟容易受机器抖动影响，更适合作为 advisory
- `claim-benchmark-v2` 追求可引用证据，不应被降级成“每次 push 都跑一下”的日常烟雾测试
- `claim-benchmark-v1` 已冻结，继续把它塞进默认流程只会制造双口径

### 4.3 回归判定的默认解释

当前 regression 默认关注：

- `pass_rate_drop`
- `avg_score_drop`
- `hard_fail_increase`
- `error_rate_increase`
- `p95_latency_increase_pct`
- `case_score_drop`

解释原则：

1. **行为回归优先于时延波动**
   - `hard_fail_count` 增长属于最高优先级
   - `pass_rate` / `avg_score` 下降属于高优先级
2. **毫秒级 seeded benchmark 的 latency 不能过度敏感**
   - 通用 CLI 默认 `p95_latency_increase_pct = 50%`
   - `run_harness_real_benchmark.py`、`run_harness_claim_benchmark.py` 和 `run_harness_claim_benchmark_v2.py` 当前都把默认值放宽到 `200%`
   - 原因不是忽略性能，而是当前 run 本身只在几毫秒量级，机器波动会把 `50%` 阈值轻易打穿
3. **release 讨论时优先看行为指标，再看时延信号**
   - 如果只出现轻微 latency 波动，而行为指标稳定，默认先记为观察项
   - 如果行为指标和 latency 同时恶化，再上升为 release blocker

---

## 5. Baseline 管理规则

### 5.1 Baseline 文件命名

所有 baseline 文件放在：

```text
harness_baselines/{baseline_id}.json
```

推荐要求：

- `baseline_id` 必须和 suite 版本绑定，例如 `ci-smoke-v1`、`real-benchmark-v2`、`claim-benchmark-v2`
- baseline JSON 必须保留 `notes` 和 `metadata`，用于说明数据来源、生成脚本、seed 模式和样本结构

### 5.2 什么时候允许原位刷新同一个 baseline 文件

只有满足以下条件时，才允许继续使用同一个 `baseline_id` 并刷新文件内容：

1. suite 的目标不变
2. case 集合不变，或只做非语义性修复（例如时间戳、注释、输出字段整理）
3. grader 语义没有变化
4. seed 数据语义没有变化
5. 团队明确知道这次刷新是在“重锁同一条基线”，不是偷偷换标准

### 5.3 什么时候必须升版

出现以下任一情况，必须创建新的 `baseline_id` / suite 版本，而不是覆盖旧文件：

1. case 数量变化
2. case 结构变化，导致 suite 覆盖范围变了
3. grader 逻辑或 pass 语义变化
4. seed 数据语义变化，导致 benchmark 验证对象变了
5. 对外 claim 口径要变，或旧口径已经不再准确

示例：

- `real-benchmark-v1`（3 cases）扩展到 6 cases 后，必须升版成 `real-benchmark-v2`
- `claim-benchmark-v1`（18 cases）扩展到 `claim-benchmark-v2`（36 cases，按难度分层）后，必须升版，不能覆盖旧文件
- 如果未来 claim suite 从 36 cases 再扩到 48 cases，或 grader 语义改动到会影响对外说法，应升版为 `claim-benchmark-v3`
- 如果只是用同样的 `claim-benchmark-v2` 规则重新锁一份“同规则下的新 canonical 结果”，才允许保留原 ID

### 5.4 升版 checklist

升版前至少满足：

1. `pytest tests -q` 全绿
2. 对应 suite runner 能本地成功产出 BatchResult / Metrics / Report
3. 新 baseline JSON 已写入 `harness_baselines/`
4. 变更说明写清楚：为什么升版、和旧版差异是什么、旧版是否冻结
5. README / docs 中所有引用路径同步更新

---

## 6. 对外 claim 规则

### 6.1 允许的说法

允许使用这种收口后的表达：

- “`claim-benchmark-v2` 的固定 36-case seeded suite 上，系统 36/36 通过。”
- “在可复现的 `claim-benchmark-v2` benchmark 中，当前 pass rate 为 100%，Wilson 95% CI lower bound 为 0.9036。”
- “当前 capability claim 仅限固定 seed、固定 case 集、真实 solver 路径。”
- “`claim-benchmark-v1` 是冻结历史基线；当前正式 release-grade 口径以 `claim-benchmark-v2` 为准。”

### 6.2 不允许的说法

以下说法禁止出现：

- “系统已经对所有真实任务 production-ready”
- “系统在现实世界中 100% 成功”
- “claim-benchmark-v2 证明 Layer 3 泛化已经完全可靠”
- “claim-benchmark-v1 仍然是当前 release-grade evidence source”
- “real-benchmark-v2 或 ci-smoke-v1 可以直接替代 release-grade claim 证据”

### 6.3 Claim baseline 的特殊规则

`harness_baselines/claim-benchmark-v2.json` 是当前唯一的 release-grade evidence baseline，必须满足：

1. 不能用 `ci-smoke` 或 `real-benchmark` 的结果覆盖它
2. 不能把它和 synthetic suite 混合聚合后再对外引用
3. 所有对外引用都必须显式写出 suite 名称和样本范围
4. 如果 suite 结构改了，必须先升版，再重新计算可引用结论
5. `harness_baselines/claim-benchmark-v1.json` 只作为冻结历史对照，不再作为默认外部 evidence source

---

## 7. 推荐运行方式

### 7.1 日常 CI / 本地快速检查

```bash
python -m pytest tests -q
python scripts/run_harness_ci_suite.py
adaptive-skill-report .ci-artifacts/harness/harness-batch-result.json \
  --baseline harness_baselines/ci-smoke-v1.json \
  --fail-on-regression
```

### 7.2 开发期真实 solver 行为观察

```bash
python scripts/run_harness_real_benchmark.py \
  --output-dir .benchmark-artifacts/real-benchmark-check \
  --baseline harness_baselines/real-benchmark-v2.json \
  --fail-on-regression
```

说明：这里的 `--fail-on-regression` 适合本地 review 或 release candidate 阶段；是否把结果升级成 CI hard gate，必须单独评估噪声水平，不能默认推进。

### 7.3 发布前一键门禁（推荐入口）

```bash
python scripts/run_release_claim_gate.py \
  --output-dir .benchmark-artifacts/release-claim-gate \
  --include-real-benchmark
```

这条脚本会固定执行以下顺序：

1. `python -m pytest tests -q --tb=short`
2. `python scripts/run_harness_ci_suite.py --output-dir .benchmark-artifacts/release-claim-gate/ci-smoke`
3. `python -m adaptive_skill.harness.cli ... --baseline harness_baselines/ci-smoke-v1.json --fail-on-regression`
4. `python scripts/run_harness_claim_benchmark_v2.py --output-dir .benchmark-artifacts/release-claim-gate/claim-benchmark-v2 --baseline harness_baselines/claim-benchmark-v2.json --fail-on-regression`
5. （可选）`python scripts/run_harness_real_benchmark.py --output-dir .benchmark-artifacts/release-claim-gate/real-benchmark-v2 --baseline harness_baselines/real-benchmark-v2.json`

产物约定：

- 统一 summary：`.benchmark-artifacts/release-claim-gate/release-claim-gate-summary.{json,md}`
- 每一步的命令日志：`.benchmark-artifacts/release-claim-gate/logs/`
- smoke / claim / real benchmark 各自保留原始 batch、metrics、report bundle

判定规则：

- 只有 summary verdict 为 `PASS` 或 `PASS_WITH_ADVISORY`，才允许继续写 README、release note 或对外 capability claim
- `PASS_WITH_ADVISORY` 表示 required gate 已通过，但 `real-benchmark-v2` 这类 advisory 观察项出现 regression，需要在发布记录里显式备注
- `FAIL` 表示至少有一条 required gate 没过，先修 gate，再改文案

### 7.4 发布前 / 对外引用前（底层等价命令）

```bash
python scripts/run_harness_claim_benchmark_v2.py \
  --output-dir .benchmark-artifacts/claim-benchmark-v2 \
  --baseline harness_baselines/claim-benchmark-v2.json \
  --fail-on-regression
```

说明：这一条保留给调试、局部复跑或手动检查；真正准备发布或准备更新对外说法时，默认优先跑 `scripts/run_release_claim_gate.py`，避免漏掉 `pytest` 或 `ci-smoke-v1` 的前置门禁。

### 7.5 历史口径复盘（可选）

```bash
python scripts/run_harness_claim_benchmark.py \
  --output-dir .benchmark-artifacts/claim-benchmark-v1 \
  --baseline harness_baselines/claim-benchmark-v1.json \
  --fail-on-regression
```

说明：这一条只用于旧资料核对或 v1→v2 差异复盘，不作为当前默认 release 判断依据。


---

## 8. 未来扩展时的治理约束

后续如果引入以下能力：

- cost / token / retry / fallback 指标
- semantic similarity grader
- 更多 suite（例如 multilingual、stress、adversarial）

必须遵守一个顺序：

1. 先定义这项指标/能力属于哪条 suite 的职责
2. 再决定它是否进入 regression gate
3. 最后才决定要不要改 baseline 版本

不要反过来做：先把新指标塞进 report，再临时解释它应该怎么影响门禁。

一句话：**先治理，再扩指标；先收口语义，再扩能力。**

2026-04-05 补充：以上两项已进入工程实现，但当前治理口径进一步明确为：

- runtime 指标只在 baseline 与 current **都具备 telemetry coverage** 时参与 regression gate，避免旧 baseline 因缺测量而被追溯性打挂
- `semantic_similarity` 已是正式 grader 原语，但是否纳入某条 benchmark suite，仍要逐 suite 明确职责后再决定，不默认直接进入 release claim 口径

---

## 9. 当前正式结论

截至 2026-04-08，Adaptive Skill System 的 benchmark 治理口径固定如下：

1. `pytest` 是仓库代码正确性的主门禁
2. `ci-smoke-v1` 是 harness 工程主门禁，也是当前唯一 CI hard regression gate
3. `real-benchmark-v2` 是 seeded real solver 的开发期观察基线，当前保持 advisory
4. `claim-benchmark-v2` 是当前唯一 release-grade benchmark evidence source
5. `claim-benchmark-v1` 进入冻结历史状态，只保留历史对照职责
6. `real-benchmark-v1` 进入历史冻结状态，不再作为主决策依据

对外 claim 或 release note 变更前，默认先执行：

```bash
python scripts/run_release_claim_gate.py --output-dir .benchmark-artifacts/release-claim-gate --include-real-benchmark
```

只有 gate summary verdict 为 `PASS` / `PASS_WITH_ADVISORY`，才继续改 README、release note 或其他对外说明。

后续若要改变这 6 条中的任意一条，必须同时更新：


- 本文档
- 对应 baseline 文件
- README 中的 benchmark 说明
- 必要的 changelog / release note
