"""Persistence sinks for harness batch runs.

Sinks implement the ResultStoreProtocol defined in single_case.py, so they
can be plugged in at both the per-run and batch levels.

Available sinks
---------------
InMemorySink   — accumulates RunResults in a list; useful for tests.
JsonlSink      — appends one JSON-line per RunResult to a .jsonl file.
JsonSink       — writes a complete BatchResult dict to a .json file at the end
                 of the batch (not a ResultStoreProtocol; used after run_batch).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .specs import RunResult


# ── InMemorySink ──────────────────────────────────────────────────────────────

class InMemorySink:
    """Accumulates RunResults in memory.  Thread-safe.

    Useful in tests where you want to inspect results without touching disk.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[RunResult] = []

    def persist(self, run_result: RunResult) -> None:
        with self._lock:
            self._records.append(run_result)

    @property
    def records(self) -> List[RunResult]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


# ── JsonlSink ─────────────────────────────────────────────────────────────────

class JsonlSink:
    """Appends one JSON-Lines record per RunResult to a file.

    Each line is a self-contained JSON object (RunResult.to_dict()).
    Suitable for streaming large batches or post-processing with tools like
    ``jq``.

    Parameters
    ----------
    path:
        Target .jsonl file path.  Parent directories are created if needed.
    mode:
        'a' (default) = append; 'w' = overwrite on creation.
    ensure_ascii:
        Passed to json.dumps; set False to preserve unicode (default).
    """

    def __init__(
        self,
        path: str | Path,
        mode: str = "a",
        ensure_ascii: bool = False,
    ) -> None:
        self._path = Path(path)
        self._mode = mode
        self._ensure_ascii = ensure_ascii
        self._lock = threading.Lock()
        # Create parent dirs eagerly so we fail fast if path is invalid.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # If mode='w' truncate on first use (not at construction, so the file
        # is only created when a result actually arrives).
        self._first_write = mode == "w"

    def persist(self, run_result: RunResult) -> None:
        record = json.dumps(run_result.to_dict(), ensure_ascii=self._ensure_ascii)
        with self._lock:
            open_mode = "w" if self._first_write else "a"
            self._first_write = False
            with open(self._path, open_mode, encoding="utf-8") as f:
                f.write(record + "\n")

    @property
    def path(self) -> Path:
        return self._path

    def read_records(self) -> List[Dict[str, Any]]:
        """Read back all records from the file (for testing / inspection)."""
        if not self._path.exists():
            return []
        records = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records


# ── JsonSink ──────────────────────────────────────────────────────────────────

class JsonSink:
    """Writes a complete BatchResult to a single .json file.

    Not a ResultStoreProtocol (it works on BatchResult, not RunResult).
    Call ``write(batch_result)`` after run_batch() completes.

    Parameters
    ----------
    path:
        Target .json file path.  Parent directories are created if needed.
    indent:
        JSON indentation level (default 2).  Pass None for compact output.
    ensure_ascii:
        Passed to json.dumps.
    """

    def __init__(
        self,
        path: str | Path,
        indent: Optional[int] = 2,
        ensure_ascii: bool = False,
    ) -> None:
        self._path = Path(path)
        self._indent = indent
        self._ensure_ascii = ensure_ascii
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, batch_result: "BatchResult") -> None:  # type: ignore[name-defined]
        """Serialise batch_result to the configured path."""
        data = batch_result.to_dict()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=self._indent, ensure_ascii=self._ensure_ascii)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> Optional[Dict[str, Any]]:
        """Read back the written JSON (for testing / inspection)."""
        if not self._path.exists():
            return None
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)


__all__ = [
    "InMemorySink",
    "JsonlSink",
    "JsonSink",
]
