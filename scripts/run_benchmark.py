# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from adaptive_skill.harness.claim_benchmark_v2_suite import ClaimBenchmarkV2Suite, ClaimBenchmarkV2KBClient, ClaimBenchmarkV2LTMClient
from adaptive_skill.core import AdaptiveSkillSystem

# 创建系统
kb = ClaimBenchmarkV2KBClient()
ltm = ClaimBenchmarkV2LTMClient()
system = AdaptiveSkillSystem(kb_provider='memory', kb_credential={}, ltm_provider='memory', ltm_credential={})

# 运行 benchmark
suite = ClaimBenchmarkV2Suite()
batch = suite.run(system)

# 统计结果
total = len(batch.results)
passed = sum(1 for r in batch.results if r.status == 'passed')
failed = sum(1 for r in batch.results if r.status == 'failed')

# 按难度统计
easy_passed = sum(1 for r in batch.results if 'easy' in r.case_id and r.status == 'passed')
easy_total = sum(1 for r in batch.results if 'easy' in r.case_id)
medium_passed = sum(1 for r in batch.results if 'medium' in r.case_id and r.status == 'passed')
medium_total = sum(1 for r in batch.results if 'medium' in r.case_id)
hard_passed = sum(1 for r in batch.results if 'hard' in r.case_id and r.status == 'passed')
hard_total = sum(1 for r in batch.results if 'hard' in r.case_id)

# 按 Layer 统计
layer_counts = {}
for r in batch.results:
    layer = r.metadata.get('layer', 'unknown')
    if layer not in layer_counts:
        layer_counts[layer] = {'passed': 0, 'failed': 0}
    layer_counts[layer][r.status] += 1

print('=' * 60)
print('CLAIM BENCHMARK V2 SCORECARD')
print('=' * 60)
print('Total: ' + str(passed) + '/' + str(total) + ' passed (' + str(round(100*passed/total, 1)) + '%)')
print()
print('By Difficulty:')
print('  Easy:   ' + str(easy_passed) + '/' + str(easy_total) + ' (' + str(round(100*easy_passed/easy_total, 1)) + '%)')
print('  Medium: ' + str(medium_passed) + '/' + str(medium_total) + ' (' + str(round(100*medium_passed/medium_total, 1)) + '%)')
print('  Hard:   ' + str(hard_passed) + '/' + str(hard_total) + ' (' + str(round(100*hard_passed/hard_total, 1)) + '%)')
print()
print('By Layer:')
for layer, counts in sorted(layer_counts.items()):
    total_layer = counts['passed'] + counts['failed']
    pct = round(100 * counts['passed'] / total_layer, 1) if total_layer > 0 else 0
    print('  Layer ' + str(layer) + ': ' + str(counts['passed']) + '/' + str(total_layer) + ' (' + str(pct) + '%)')
print()
print('=' * 60)
