"""
dump_benchmark_cases.py — 把 benchmark cases 的 problem 字符串 dump 到 JSON
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adaptive_skill.harness.benchmark_suite import LAYER_1_CASE, build_benchmark_jobs

data = {
    "layer1_problem": LAYER_1_CASE.problem,
    "jobs": [
        {"id": j.case.case_id, "problem": j.case.problem}
        for j in build_benchmark_jobs()
    ],
}

out = Path(__file__).parent / "tmp_benchmark_cases.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Written to {out}")
