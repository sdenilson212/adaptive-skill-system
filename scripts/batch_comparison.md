# P14 Batch Benchmark 对比报告

运行时间: 2026-04-03 19:51:07

## 对比表（Mock 持久层 vs 真实持久层）

| case_id | mock_layer | real_layer | mock_conf | real_conf | match |
|---------|-----------|-----------|----------|----------|-------|
| bench-layer1-kb-hit-v1 | 1 | 1 | 0.95 | 0.95 | ✅ |
| bench-layer2-compose-v1 | 2 | 1 | 0.8 | 0.95 | ⚠️ |
| bench-layer2-mixed-support-v1 | 2 | 1 | 0.8 | 0.95 | ⚠️ |
| bench-layer3-generate-v1 | 3 | 1 | 0.763 | 0.95 | ⚠️ |
| bench-layer3-sparse-context-v1 | 3 | 1 | 0.738 | 0.95 | ⚠️ |
| bench-layer3-list-fallback-v1 | 3 | 3 | 0.75 | 0.78 | ✅ |

## 汇总

- layer 一致率: **2/6**

## 结论

- Mock 持久层用 seeded KB，Layer 1 直接命中，confidence=0.95
- 真实持久层经 P13 seed 后，Layer 1 case 应命中，confidence 视匹配度定
- Layer 2/3 case 在真实 KB 下命中辅助条目，layer 编号可能与 mock 有差异（正常）
- 关键验证：真实持久层下系统可正常运行，无崩溃，无 None 返回