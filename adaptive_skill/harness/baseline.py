"""Baseline store for Adaptive Skill System harness (P3).

Provides lightweight JSON-based persistence for baseline BatchMetrics
snapshots, enabling regression checks between runs.

Design decisions
----------------
* Storage format: one JSON file per baseline, stored in a configurable
  directory (default: harness_baselines/).  Files are named
  ``{baseline_id}.json``.  This avoids a database dependency.
* Baseline locking: ``lock()`` writes the current BatchMetrics as the
  canonical baseline for a given ``baseline_id``.  Overwrites are
  intentional — the caller decides when to promote a new baseline.
* Immutable snapshots: once locked, a baseline should not be mutated;
  update by locking a new one.
* Thread-safety: writes are atomic via write-to-temp + rename (on POSIX)
  and a best-effort rename on Windows; concurrent writes to the *same*
  baseline_id are caller's responsibility.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .metrics import BatchMetrics


# ── Baseline record ───────────────────────────────────────────────────────────

@dataclass
class BaselineRecord:
    """A persisted baseline snapshot."""

    baseline_id: str
    label: str                       # human-readable name (e.g. "v1.0.2-release")
    system_version: str
    locked_at: str                   # ISO-8601
    metrics: BatchMetrics
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "label": self.label,
            "system_version": self.system_version,
            "locked_at": self.locked_at,
            "notes": self.notes,
            "metadata": self.metadata,
            "metrics": self.metrics.to_dict(rounded=False),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaselineRecord":
        """Reconstruct from the JSON dict persisted by to_dict()."""
        raw_metrics = dict(data.get("metrics", {}))
        # Rebuild BatchMetrics (flat scalars only — case_metrics / tag_slices
        # are restored from the nested dicts for equality checks).
        from .metrics import CaseMetrics  # local import to avoid circulars

        case_metrics_raw = raw_metrics.pop("case_metrics", [])
        tag_slices = raw_metrics.pop("tag_slices", {})
        layer_distribution = raw_metrics.pop("layer_distribution", {})


        bm = BatchMetrics(
            batch_id=raw_metrics.get("batch_id", ""),
            system_version=raw_metrics.get("system_version", ""),
            started_at=raw_metrics.get("started_at", ""),
            total=raw_metrics.get("total", 0),
            passed=raw_metrics.get("passed", 0),
            failed=raw_metrics.get("failed", 0),
            errored=raw_metrics.get("errored", 0),
            partial=raw_metrics.get("partial", 0),
            pass_rate=raw_metrics.get("pass_rate", 0.0),
            avg_score=raw_metrics.get("avg_score", 0.0),
            score_stdev=raw_metrics.get("score_stdev", 0.0),
            min_score=raw_metrics.get("min_score", 0.0),
            max_score=raw_metrics.get("max_score", 0.0),
            avg_duration_ms=raw_metrics.get("avg_duration_ms", 0.0),
            p50_duration_ms=raw_metrics.get("p50_duration_ms", 0.0),
            p95_duration_ms=raw_metrics.get("p95_duration_ms", 0.0),
            hard_fail_count=raw_metrics.get("hard_fail_count", 0),
            total_attempt_count=raw_metrics.get("total_attempt_count", 0),
            avg_attempt_count=raw_metrics.get("avg_attempt_count", 0.0),
            total_retry_count=raw_metrics.get("total_retry_count", 0),
            avg_retry_count=raw_metrics.get("avg_retry_count", 0.0),
            total_fallback_count=raw_metrics.get("total_fallback_count", 0),
            avg_fallback_count=raw_metrics.get("avg_fallback_count", 0.0),
            total_prompt_tokens=raw_metrics.get("total_prompt_tokens", 0),
            total_completion_tokens=raw_metrics.get("total_completion_tokens", 0),
            total_tokens=raw_metrics.get("total_tokens", 0),
            avg_total_tokens=raw_metrics.get("avg_total_tokens", 0.0),
            total_estimated_cost=raw_metrics.get("total_estimated_cost", 0.0),
            avg_estimated_cost=raw_metrics.get("avg_estimated_cost", 0.0),
            runtime_metric_coverage=raw_metrics.get("runtime_metric_coverage", {}),
            layer_distribution=layer_distribution,
            tag_slices=tag_slices,
            case_metrics=[
                CaseMetrics(
                    case_id=c["case_id"],
                    final_status=c["final_status"],
                    final_score=c["final_score"],
                    duration_ms=c["duration_ms"],
                    execution_status=c["execution_status"],
                    hard_fail=c.get("hard_fail", False),
                    layer_used=c.get("layer_used"),
                    attempt_count=c.get("attempt_count", 1),
                    retry_count=c.get("retry_count", 0),
                    fallback_count=c.get("fallback_count", 0),
                    prompt_tokens=c.get("prompt_tokens", 0),
                    completion_tokens=c.get("completion_tokens", 0),
                    total_tokens=c.get("total_tokens", 0),
                    estimated_cost=c.get("estimated_cost", 0.0),
                    grader_scores=c.get("grader_scores", {}),
                    assertion_results=c.get("assertion_results", []),
                    grading_notes=c.get("grading_notes", []),
                    decision_trace=c.get("decision_trace", []),
                )


                for c in case_metrics_raw
            ],
        )

        return cls(
            baseline_id=data["baseline_id"],
            label=data.get("label", ""),
            system_version=data.get("system_version", ""),
            locked_at=data.get("locked_at", ""),
            notes=data.get("notes", ""),
            metadata=data.get("metadata", {}),
            metrics=bm,
        )


# ── BaselineStore ─────────────────────────────────────────────────────────────

class BaselineStore:
    """File-backed store for BatchMetrics baselines.

    Parameters
    ----------
    store_dir:
        Directory where ``{baseline_id}.json`` files are written.
        Created automatically if it does not exist.

    Usage
    -----
    >>> store = BaselineStore("harness_baselines")
    >>> record = store.lock(metrics, label="v1.0.3-release")
    >>> loaded = store.load(record.baseline_id)
    >>> store.list_baselines()          # → [BaselineRecord, ...]
    >>> store.delete(record.baseline_id)
    """

    def __init__(self, store_dir: str = "harness_baselines") -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    # ── Write ──

    def lock(
        self,
        metrics: BatchMetrics,
        *,
        baseline_id: Optional[str] = None,
        label: str = "",
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BaselineRecord:
        """Persist *metrics* as a baseline snapshot.

        Parameters
        ----------
        metrics:
            The BatchMetrics to promote to baseline.
        baseline_id:
            Optional stable ID.  If omitted a new UUID is generated.
            Passing the same ID overwrites the previous baseline (intentional).
        label:
            Human-readable tag, e.g. ``"v1.0.3-release"`` or ``"pre-refactor"``.
        notes:
            Free-text annotation.
        metadata:
            Arbitrary key-value pairs stored alongside the snapshot.

        Returns
        -------
        BaselineRecord
            The persisted record.
        """
        record = BaselineRecord(
            baseline_id=baseline_id or str(uuid.uuid4()),
            label=label or f"baseline-{metrics.system_version}",
            system_version=metrics.system_version,
            locked_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics,
            notes=notes,
            metadata=metadata or {},
        )
        self._write(record)
        return record

    # ── Read ──

    def load(self, baseline_id: str) -> BaselineRecord:
        """Load a single baseline by ID.

        Raises
        ------
        FileNotFoundError
            If no baseline with that ID exists.
        """
        path = self._path(baseline_id)
        if not path.exists():
            raise FileNotFoundError(
                f"Baseline '{baseline_id}' not found in {self.store_dir}"
            )
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return BaselineRecord.from_dict(data)

    def list_baselines(self) -> List[BaselineRecord]:
        """Return all persisted baselines, sorted by locked_at ascending."""
        records = []
        for f in self.store_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                records.append(BaselineRecord.from_dict(data))
            except Exception:
                # Skip corrupted files silently — caller can investigate.
                pass
        records.sort(key=lambda r: r.locked_at)
        return records

    def exists(self, baseline_id: str) -> bool:
        return self._path(baseline_id).exists()

    # ── Delete ──

    def delete(self, baseline_id: str) -> bool:
        """Delete a baseline file.  Returns True if deleted, False if not found."""
        path = self._path(baseline_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ── Helpers ──

    def _path(self, baseline_id: str) -> Path:
        # Sanitise to prevent directory traversal
        safe_id = baseline_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.store_dir / f"{safe_id}.json"

    def _write(self, record: BaselineRecord) -> None:
        """Atomic write: temp file → rename."""
        target = self._path(record.baseline_id)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.store_dir, prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(record.to_dict(), fh, ensure_ascii=False, indent=2)
            # os.replace is atomic on POSIX; on Windows it may raise if target
            # is locked, but that is acceptable for our single-writer use case.
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


__all__ = [
    "BaselineRecord",
    "BaselineStore",
]
