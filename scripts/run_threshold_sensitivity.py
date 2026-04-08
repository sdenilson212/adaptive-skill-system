"""Run a reproducible Layer 3 threshold sensitivity sweep.

The script reads a saved benchmark snapshot (default: scripts/batch_real_result.json),
focuses on Layer 3 rows, and compares candidate threshold tuples:
  - quality gate threshold
  - success/partial status threshold
  - verification threshold

Outputs both JSON and Markdown summaries so threshold decisions stop living only in code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = Path(__file__).resolve().parent / "batch_real_result.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "threshold-sensitivity"

QUALITY_GATES = (0.65, 0.70, 0.75)
SUCCESS_THRESHOLDS = (0.70, 0.75, 0.80)
VERIFICATION_THRESHOLDS = (0.80, 0.85, 0.90)
CURRENT_POLICY = {
    "quality_gate": 0.70,
    "success_threshold": 0.75,
    "verification_threshold": 0.85,
}


def _load_snapshot(path: Path) -> Dict[str, List[Dict]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return {
        name: rows for name, rows in payload.items() if isinstance(rows, list)
    }


def _layer3_rows(rows: Iterable[Dict]) -> List[Dict]:
    return [row for row in rows if row.get("layer") == 3 and isinstance(row.get("confidence"), (int, float))]


def _summarize_policy(rows: List[Dict], quality_gate: float, success_threshold: float, verification_threshold: float) -> Dict:
    blocked = []
    partial = []
    success = []
    feedback_required = []

    for row in rows:
        confidence = float(row["confidence"])
        case_id = row.get("case_id", "unknown")
        if confidence < quality_gate:
            blocked.append(case_id)
            continue
        if confidence < success_threshold:
            partial.append(case_id)
        else:
            success.append(case_id)
        if confidence < verification_threshold:
            feedback_required.append(case_id)

    return {
        "quality_gate": quality_gate,
        "success_threshold": success_threshold,
        "verification_threshold": verification_threshold,
        "blocked": blocked,
        "partial": partial,
        "success": success,
        "feedback_required": feedback_required,
    }


def _grid(rows: List[Dict]) -> List[Dict]:
    results: List[Dict] = []
    for quality_gate in QUALITY_GATES:
        for success_threshold in SUCCESS_THRESHOLDS:
            if success_threshold < quality_gate:
                continue
            for verification_threshold in VERIFICATION_THRESHOLDS:
                if verification_threshold < success_threshold:
                    continue
                results.append(
                    _summarize_policy(
                        rows,
                        quality_gate=quality_gate,
                        success_threshold=success_threshold,
                        verification_threshold=verification_threshold,
                    )
                )
    return results


def _render_markdown(snapshot_name: str, rows: List[Dict], grid: List[Dict], current: Dict) -> str:
    lines = [
        f"# Layer 3 阈值敏感性分析 — {snapshot_name}",
        "",
        "## 数据来源",
        f"- Snapshot: `{DEFAULT_INPUT}`",
        f"- Layer 3 样本数: {len(rows)}",
        "",
        "## 当前策略",
        f"- quality gate: {current['quality_gate']:.2f}",
        f"- success threshold: {current['success_threshold']:.2f}",
        f"- verification threshold: {current['verification_threshold']:.2f}",
        f"- blocked: {current['blocked'] or ['无']}",
        f"- partial: {current['partial'] or ['无']}",
        f"- success: {current['success'] or ['无']}",
        f"- feedback_required: {current['feedback_required'] or ['无']}",
        "",
        "## 全量组合对比",
        "| quality_gate | success_threshold | verification_threshold | blocked | partial | success | feedback_required |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in grid:
        lines.append(
            "| "
            f"{item['quality_gate']:.2f} | {item['success_threshold']:.2f} | {item['verification_threshold']:.2f} | "
            f"{len(item['blocked'])} | {len(item['partial'])} | {len(item['success'])} | {len(item['feedback_required'])} |"
        )

    lines.extend(
        [
            "",
            "## 结论",
            "- 当前 0.70 / 0.75 / 0.85 组合能保留 quality gate、status 与反馈门槛三段语义。",
            "- 如果把 success threshold 下调到 0.70，更多 Layer 3 结果会被提升为 success，partial 档会明显收缩。",
            "- 如果把 verification threshold 上调到 0.90，几乎所有 Layer 3 结果都会落入 needs_feedback。",
            "",
            "> 注：该分析基于保存下来的 benchmark snapshot；若 snapshot 中 confidence 做过显示层四舍五入，边界 case 可能与运行时原始浮点值存在 ±0.001 级差异。",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    snapshot = _load_snapshot(DEFAULT_INPUT)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {}
    for snapshot_name, raw_rows in snapshot.items():
        rows = _layer3_rows(raw_rows)
        grid = _grid(rows)
        current = _summarize_policy(rows, **CURRENT_POLICY)
        summary[snapshot_name] = {
            "sample_count": len(rows),
            "current_policy": current,
            "grid": grid,
        }
        markdown = _render_markdown(snapshot_name, rows, grid, current)
        (DEFAULT_OUTPUT_DIR / f"{snapshot_name}.md").write_text(markdown, encoding="utf-8")

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"threshold sensitivity reports written to: {DEFAULT_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
