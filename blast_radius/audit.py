"""Append-only, privacy-safe local record of what the deterministic screen flagged.

Records a fingerprint of each screened artifact plus the verdict and the categories
that drove it — **never** the raw command/diff, match excerpts, paths, or any
secret. It lets a developer review what the daily-driver guard has been seeing
over time without the log itself becoming a place secrets pile up.

Stdlib only (the CLI/hook import path stays dependency-light) and fully fail-open:
any I/O error is swallowed so auditing can never break or slow a screen. The log
lives at ``~/.blastradius/audit.jsonl`` by default; set ``BLAST_RADIUS_AUDIT_LOG``
to relocate it, or ``BLAST_RADIUS_AUDIT=off`` to disable recording entirely.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from blast_radius.models import InspectionReport

_ENV_PATH = "BLAST_RADIUS_AUDIT_LOG"
_ENV_TOGGLE = "BLAST_RADIUS_AUDIT"
_DISABLED = {"0", "off", "false", "no"}


def audit_path() -> Path:
    override = os.environ.get(_ENV_PATH)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".blastradius" / "audit.jsonl"


def is_enabled() -> bool:
    return os.environ.get(_ENV_TOGGLE, "on").strip().lower() not in _DISABLED


def record(report: InspectionReport, *, kind: str, source: str) -> Path | None:
    """Append one privacy-safe entry for a screened artifact. Returns the log path
    on success, or None if disabled or if any I/O failed (fail-open)."""
    if not is_enabled():
        return None
    provenance = report.provenance
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "source": source,  # "cli" | "hook"
        "kind": kind,  # command | diff | config
        "verdict": report.verdict,
        "categories": [finding.category for finding in report.findings],
        "driving": list(provenance.driving_findings) if provenance else [],
        "confidence": report.confidence,
        "fingerprint": provenance.input_fingerprint if provenance else "",
        "engine_version": provenance.engine_version if provenance else "",
        "decode_layers": provenance.decode_layers if provenance else 0,
    }
    try:
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return path
    except OSError:
        return None  # fail open: auditing must never break the screen


def read_entries(limit: int | None = None) -> list[dict]:
    path = audit_path()
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit is not None:
        lines = lines[-limit:]
    return [json.loads(line) for line in lines]


def summarize(entries: list[dict]) -> dict:
    by_verdict: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for entry in entries:
        verdict = entry.get("verdict", "")
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        for category in entry.get("categories", []):
            by_category[category] = by_category.get(category, 0) + 1
    return {
        "total": len(entries),
        "by_verdict": by_verdict,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
