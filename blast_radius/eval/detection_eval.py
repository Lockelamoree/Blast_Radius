"""Score the deterministic red-flag screen (``inspector``) against a labeled
corpus of malicious and benign artifacts.

Pure and deterministic: no model, no network, no API key. Every sample is run
through the exact same ``inspector.inspect_text`` / ``inspector.inspect_config``
a developer's CLI, hook, and Action use, so the scorecard measures the shipping
engine, not a proxy.

Honesty is structural. A sample is counted as *flagged* iff its verdict is not
``looks-scoped`` — the engine never claims an artifact is safe, so ``looks-scoped``
is treated as "no known pattern matched", never as a safety proof. The corpus
carries ``status='xfail'`` rows for documented blind spots (evasions the engine
misses today); they are scored into the metrics honestly rather than hidden, and
a companion test fails loudly if an xfail silently starts passing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from blast_radius.engine import inspector
from blast_radius.models import BlastRadiusConfig

_VERDICTS: tuple[str, ...] = ("looks-scoped", "sandbox-recommended", "reject-recommended")

DETECTION_NOTE = (
    "Deterministic keyword screen scored on a fixed, curated corpus — no model ran. "
    "High recall here does not mean real-world attacks are caught; the corpus "
    "deliberately includes documented blind spots (status='xfail'). 'looks-scoped' "
    "means only that no known pattern matched — never that an artifact is safe."
)


@dataclass(frozen=True)
class CorpusSample:
    """One labeled artifact. ``input`` drives command/diff checks; ``config`` (and
    optional ``expected`` baseline) drive a sandbox-config check."""

    id: str
    kind: str  # "command" | "diff" | "config"
    label: str  # "malicious" | "benign"
    expected_verdict: str
    expected_categories: tuple[str, ...] = ()
    status: str = "pass"  # "pass" (defended invariant) | "xfail" (documented blind spot)
    note: str = ""
    input: str = ""
    config: dict | None = None
    expected: dict | None = None

    @classmethod
    def from_dict(cls, row: dict) -> CorpusSample:
        return cls(
            id=row["id"],
            kind=row["kind"],
            label=row["label"],
            expected_verdict=row["expected_verdict"],
            expected_categories=tuple(row.get("expected_categories", ())),
            status=row.get("status", "pass"),
            note=row.get("note", ""),
            input=row.get("input", ""),
            config=row.get("config"),
            expected=row.get("expected"),
        )


@dataclass
class SampleResult:
    id: str
    kind: str
    label: str
    status: str
    expected_verdict: str
    actual_verdict: str
    verdict_match: bool
    expected_categories: list[str]
    actual_categories: list[str]
    categories_covered: bool
    flagged: bool
    meets_expectation: bool
    note: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "expected_verdict": self.expected_verdict,
            "actual_verdict": self.actual_verdict,
            "verdict_match": self.verdict_match,
            "expected_categories": self.expected_categories,
            "actual_categories": self.actual_categories,
            "categories_covered": self.categories_covered,
            "flagged": self.flagged,
            "meets_expectation": self.meets_expectation,
            "note": self.note,
        }


@dataclass
class DetectionEvalReport:
    total: int
    malicious: int
    benign: int
    true_positive: int
    false_negative: int
    false_positive: int
    true_negative: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    per_category: dict[str, dict[str, float | int]]
    confusion: dict[str, dict[str, int]]
    xfail_total: int
    xfail_unexpectedly_passing: int
    pass_regressions: int
    results: list[SampleResult]
    engine_version: str = inspector.ENGINE_VERSION
    categories_hash: str = field(default_factory=inspector._categories_hash)
    graded_by: str = "deterministic"
    method: str = "keyword-heuristic"
    note: str = DETECTION_NOTE

    def to_dict(self) -> dict:
        return {
            "graded_by": self.graded_by,
            "method": self.method,
            "engine_version": self.engine_version,
            "categories_hash": self.categories_hash,
            "total": self.total,
            "malicious": self.malicious,
            "benign": self.benign,
            "true_positive": self.true_positive,
            "false_negative": self.false_negative,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "per_category": self.per_category,
            "confusion": self.confusion,
            "xfail_total": self.xfail_total,
            "xfail_unexpectedly_passing": self.xfail_unexpectedly_passing,
            "pass_regressions": self.pass_regressions,
            "results": [result.to_dict() for result in self.results],
            "note": self.note,
        }


def _report_categories(sample: CorpusSample) -> tuple[str, list[str]]:
    """Run the shipping screen on a sample; return (verdict, fired category ids)."""
    if sample.kind == "config":
        config = BlastRadiusConfig.model_validate(sample.config or {})
        expected = (
            BlastRadiusConfig.model_validate(sample.expected)
            if sample.expected is not None
            else None
        )
        report = inspector.inspect_config(config, expected)
    else:
        report = inspector.inspect_text(sample.input, kind=sample.kind)
    return report.verdict, [finding.category for finding in report.findings]


def _round(value: float) -> float:
    return round(value, 3)


def _ratio(numerator: int, denominator: int) -> float:
    return _round(numerator / denominator) if denominator else 0.0


def evaluate_detection(samples: Iterable[CorpusSample]) -> DetectionEvalReport:
    results: list[SampleResult] = []
    for sample in samples:
        verdict, categories = _report_categories(sample)
        actual_set = set(categories)
        covered = set(sample.expected_categories) <= actual_set
        verdict_match = verdict == sample.expected_verdict
        meets = verdict_match and covered
        results.append(
            SampleResult(
                id=sample.id,
                kind=sample.kind,
                label=sample.label,
                status=sample.status,
                expected_verdict=sample.expected_verdict,
                actual_verdict=verdict,
                verdict_match=verdict_match,
                expected_categories=list(sample.expected_categories),
                actual_categories=sorted(actual_set),
                categories_covered=covered,
                flagged=verdict != "looks-scoped",
                meets_expectation=meets,
                note=sample.note,
            )
        )

    malicious = [r for r in results if r.label == "malicious"]
    benign = [r for r in results if r.label == "benign"]
    tp = sum(1 for r in malicious if r.flagged)
    fn = len(malicious) - tp
    fp = sum(1 for r in benign if r.flagged)
    tn = len(benign) - fp

    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = _round(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = _ratio(fp, fp + tn)

    # Per-category precision/recall as a multi-label problem over expected vs fired.
    category_ids = sorted(
        {cat for r in results for cat in r.expected_categories}
        | {cat for r in results for cat in r.actual_categories}
    )
    per_category: dict[str, dict[str, float | int]] = {}
    for cat in category_ids:
        expected_here = [r for r in results if cat in r.expected_categories]
        fired_here = [r for r in results if cat in r.actual_categories]
        hits = sum(1 for r in expected_here if cat in r.actual_categories)
        per_category[cat] = {
            "support": len(expected_here),
            "recall": _ratio(hits, len(expected_here)),
            "precision": _ratio(
                sum(1 for r in fired_here if cat in r.expected_categories), len(fired_here)
            ),
        }

    confusion: dict[str, dict[str, int]] = {
        expected: {actual: 0 for actual in _VERDICTS} for expected in _VERDICTS
    }
    for r in results:
        if r.expected_verdict in confusion and r.actual_verdict in confusion[r.expected_verdict]:
            confusion[r.expected_verdict][r.actual_verdict] += 1

    xfails = [r for r in results if r.status == "xfail"]
    return DetectionEvalReport(
        total=len(results),
        malicious=len(malicious),
        benign=len(benign),
        true_positive=tp,
        false_negative=fn,
        false_positive=fp,
        true_negative=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        per_category=per_category,
        confusion=confusion,
        xfail_total=len(xfails),
        xfail_unexpectedly_passing=sum(1 for r in xfails if r.meets_expectation),
        pass_regressions=sum(
            1 for r in results if r.status == "pass" and not r.meets_expectation
        ),
        results=results,
    )


def load_corpus(path: Path) -> list[CorpusSample]:
    """Parse the JSON Lines corpus. Blank lines are skipped so contributors can
    group rows; every non-blank line must be a well-formed sample object."""
    samples: list[CorpusSample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        samples.append(CorpusSample.from_dict(json.loads(line)))
    return samples
