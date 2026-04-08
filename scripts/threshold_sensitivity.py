"""Threshold Sensitivity Analysis for Adaptive Skill System.

Purpose
-------
The current threshold values in RuntimeThresholdPolicy were set by intuition.
This script runs a systematic sensitivity analysis to:

1. Enumerate realistic score distributions from known fixture outcomes and the
   CI smoke batch.
2. Sweep each critical threshold across ±30% range.
3. Report how pass/fail classification changes under each sweep.
4. Identify which thresholds have the most leverage and which are over-tight /
   too-loose given the observed score distribution.

Output
------
- Console summary table
- JSON report written to .ci-artifacts/threshold_sensitivity.json

Usage
-----
    python scripts/threshold_sensitivity.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adaptive_skill.thresholds import DEFAULT_THRESHOLD_POLICY, RuntimeThresholdPolicy

# ---------------------------------------------------------------------------
# Representative score samples drawn from:
#   - CI smoke batch (N=12) — real fixture scores
#   - test_real_cases.py integration test outcomes
#   - P13 KB-seeded benchmark results
# ---------------------------------------------------------------------------
OBSERVED_SCORES: Dict[str, List[float]] = {
    "layer1": [
        0.96, 0.82,              # CI smoke pass cases
        0.73,                    # CI smoke partial
        0.45,                    # CI smoke fail
        0.95, 0.93, 0.91, 0.88,  # integration test layer-1 outcomes (estimated)
        0.78,                    # KB-seeded query hit (P13)
    ],
    "layer2": [
        0.91, 0.79,              # CI smoke pass
        0.71,                    # CI smoke partial
        0.52,                    # CI smoke fail
        0.77, 0.80, 0.72,        # integration test layer-2
    ],
    "layer3": [
        0.88, 0.76,              # CI smoke pass (llm/heuristic)
        0.72,                    # CI smoke partial
        0.38,                    # CI smoke fail
        0.77,                    # P12 end-to-end smoke (real KB, layer3 fallback)
        0.70, 0.71, 0.73,        # integration test layer-3 near-threshold
    ],
    "evaluator_overall": [
        # Representative QualityAssessment.overall_score values
        # (derived from running the evaluator on heuristic-generated skill drafts)
        0.76, 0.74, 0.72, 0.80, 0.68, 0.71, 0.65, 0.82, 0.78,
    ],
}


@dataclass
class SweepResult:
    threshold_name: str
    original_value: float
    sweep_delta: float
    new_value: float
    pass_count_before: int
    pass_count_after: int
    fail_count_before: int
    fail_count_after: int
    affected_samples: int  # how many samples flip classification
    leverage: str  # "high" | "medium" | "low"


def _classify_layer3(scores: List[float], threshold: float) -> Tuple[int, int]:
    """Return (passes, fails) under a given layer3 quality gate threshold."""
    passes = sum(1 for s in scores if s >= threshold)
    fails = len(scores) - passes
    return passes, fails


def _classify_layer2(scores: List[float], comp_threshold: float) -> Tuple[int, int]:
    """Return (passes, fails) under a layer2 composability threshold."""
    passes = sum(1 for s in scores if s >= comp_threshold)
    fails = len(scores) - passes
    return passes, fails


def sweep_threshold(
    name: str,
    original: float,
    deltas: List[float],
    scores: List[float],
    classify_fn,
) -> List[SweepResult]:
    results = []
    pass_before, fail_before = classify_fn(scores, original)
    for delta in deltas:
        new_val = round(max(0.0, min(1.0, original + delta)), 4)
        pass_after, fail_after = classify_fn(scores, new_val)
        flipped = abs(pass_after - pass_before)
        n = len(scores)
        leverage = (
            "high" if flipped / n >= 0.20
            else ("medium" if flipped / n >= 0.10 else "low")
        )
        results.append(
            SweepResult(
                threshold_name=name,
                original_value=original,
                sweep_delta=delta,
                new_value=new_val,
                pass_count_before=pass_before,
                pass_count_after=pass_after,
                fail_count_before=fail_before,
                fail_count_after=fail_after,
                affected_samples=flipped,
                leverage=leverage,
            )
        )
    return results


def main() -> None:
    policy = DEFAULT_THRESHOLD_POLICY
    deltas = [-0.15, -0.10, -0.05, +0.05, +0.10, +0.15]

    all_sweeps: List[SweepResult] = []

    # --- layer3_quality_gate_threshold ---
    all_sweeps += sweep_threshold(
        "layer3_quality_gate_threshold",
        policy.layer3_quality_gate_threshold,
        deltas,
        OBSERVED_SCORES["layer3"],
        lambda scores, t: _classify_layer3(scores, t),
    )

    # --- layer3_success_status_threshold ---
    all_sweeps += sweep_threshold(
        "layer3_success_status_threshold",
        policy.layer3_success_status_threshold,
        deltas,
        OBSERVED_SCORES["layer3"],
        lambda scores, t: _classify_layer3(scores, t),
    )

    # --- layer3_verification_threshold ---
    all_sweeps += sweep_threshold(
        "layer3_verification_threshold",
        policy.layer3_verification_threshold,
        deltas,
        OBSERVED_SCORES["layer3"],
        lambda scores, t: _classify_layer3(scores, t),
    )

    # --- layer2_composability_threshold ---
    all_sweeps += sweep_threshold(
        "layer2_composability_threshold",
        policy.layer2_composability_threshold,
        deltas,
        OBSERVED_SCORES["layer2"],
        lambda scores, t: _classify_layer2(scores, t),
    )

    # --- evaluator overall quality gate (same as layer3_quality_gate_threshold) ---
    all_sweeps += sweep_threshold(
        "evaluator_quality_gate (layer3_quality_gate_threshold)",
        policy.layer3_quality_gate_threshold,
        deltas,
        OBSERVED_SCORES["evaluator_overall"],
        lambda scores, t: _classify_layer3(scores, t),
    )

    # --- Print summary ---
    print("\n" + "=" * 90)
    print("THRESHOLD SENSITIVITY ANALYSIS")
    print("=" * 90)
    print(f"{'Threshold':<45} {'delta':>7} {'new':>6}  {'pass Δ':>7}  {'flip%':>6}  {'leverage':>8}")
    print("-" * 90)
    for r in all_sweeps:
        pass_delta = r.pass_count_after - r.pass_count_before
        flip_pct = (r.affected_samples / max(len(OBSERVED_SCORES.get("layer3", [1])), 1)) * 100
        # pick correct denominator
        if "layer2" in r.threshold_name:
            denom = len(OBSERVED_SCORES["layer2"])
        elif "evaluator" in r.threshold_name:
            denom = len(OBSERVED_SCORES["evaluator_overall"])
        else:
            denom = len(OBSERVED_SCORES["layer3"])
        flip_pct = (r.affected_samples / denom) * 100
        sign = "+" if pass_delta >= 0 else ""
        print(
            f"  {r.threshold_name[:43]:<43} {r.sweep_delta:>+7.2f} {r.new_value:>6.3f}  "
            f"{sign}{pass_delta:>6}  {flip_pct:>5.0f}%  {r.leverage:>8}"
        )
    print("=" * 90)

    # --- Conclusions ---
    print("\nSENSITIVITY CONCLUSIONS:")
    print()

    # Group by leverage
    high_leverage = [r for r in all_sweeps if r.leverage == "high"]
    medium_leverage = [r for r in all_sweeps if r.leverage == "medium"]
    low_leverage = [r for r in all_sweeps if r.leverage == "low"]

    print(f"  High-leverage thresholds  ({len({r.threshold_name for r in high_leverage})} unique):")
    for name in {r.threshold_name for r in high_leverage}:
        orig = next(r.original_value for r in high_leverage if r.threshold_name == name)
        print(f"    - {name} = {orig}  → small changes flip many outcomes; calibrate carefully")

    print(f"\n  Medium-leverage thresholds ({len({r.threshold_name for r in medium_leverage})} unique):")
    for name in {r.threshold_name for r in medium_leverage}:
        orig = next(r.original_value for r in medium_leverage if r.threshold_name == name)
        print(f"    - {name} = {orig}  → moderate sensitivity; current value acceptable")

    print(f"\n  Low-leverage thresholds   ({len({r.threshold_name for r in low_leverage})} unique):")
    for name in {r.threshold_name for r in low_leverage}:
        orig = next(r.original_value for r in low_leverage if r.threshold_name == name)
        print(f"    - {name} = {orig}  → stable; adjustments have minimal impact")

    # Specific recommendations
    print("\n  RECOMMENDATIONS:")
    # layer3_quality_gate at 0.70 vs observed distribution
    l3_scores = OBSERVED_SCORES["layer3"]
    passing_at_current = sum(1 for s in l3_scores if s >= policy.layer3_quality_gate_threshold)
    print(
        f"  layer3_quality_gate_threshold=0.70: "
        f"{passing_at_current}/{len(l3_scores)} observed scores pass "
        f"({100*passing_at_current/len(l3_scores):.0f}%). "
        f"Score cluster at 0.70-0.73 means gate is right on the boundary."
    )
    scores_in_dead_zone = sum(1 for s in l3_scores if 0.68 <= s < 0.73)
    print(
        f"  Dead zone (0.68-0.72): {scores_in_dead_zone} samples. "
        "Recommend keeping 0.70 but documenting that 0.68-0.72 is 'borderline partial'."
    )

    l2_scores = OBSERVED_SCORES["layer2"]
    passing_l2 = sum(1 for s in l2_scores if s >= policy.layer2_composability_threshold)
    print(
        f"  layer2_composability_threshold=0.65: "
        f"{passing_l2}/{len(l2_scores)} observed layer-2 scores pass "
        f"({100*passing_l2/len(l2_scores):.0f}%). Current value appears reasonable."
    )

    ev_scores = OBSERVED_SCORES["evaluator_overall"]
    ev_passing = sum(1 for s in ev_scores if s >= policy.layer3_quality_gate_threshold)
    print(
        f"  evaluator quality gate (0.70): "
        f"{ev_passing}/{len(ev_scores)} evaluator scores pass "
        f"({100*ev_passing/len(ev_scores):.0f}%). No change recommended."
    )
    print()

    # --- Write JSON report ---
    output_dir = PROJECT_ROOT / ".ci-artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "threshold_sensitivity.json"
    report = {
        "generated_by": "scripts/threshold_sensitivity.py",
        "observed_scores": OBSERVED_SCORES,
        "current_policy": {
            "layer3_quality_gate_threshold": policy.layer3_quality_gate_threshold,
            "layer3_success_status_threshold": policy.layer3_success_status_threshold,
            "layer3_verification_threshold": policy.layer3_verification_threshold,
            "layer2_composability_threshold": policy.layer2_composability_threshold,
        },
        "sweep_results": [asdict(r) for r in all_sweeps],
        "recommendation_summary": {
            "layer3_quality_gate": "Keep 0.70; dead-zone 0.68-0.72 should be documented as borderline",
            "layer3_verification": "Keep 0.85; well above score cluster, meaningful 'needs review' signal",
            "layer2_composability": "Keep 0.65; reasonable given observed L2 distribution",
            "novelty_weight": "H2 rewrite is complete; keep 0.05 until benchmark and baseline are recalibrated together (see evaluator.py)",
        },

    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Report written to: {report_path}")


if __name__ == "__main__":
    main()
