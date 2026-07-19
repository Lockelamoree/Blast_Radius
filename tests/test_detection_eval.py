"""Regression + honesty tests for the detection scorecard.

The corpus is scored against the shipping deterministic screen. Pure and offline
(no key), so these run in CI as a hard accuracy gate: `pass` samples must keep
meeting their expectation, `xfail` blind spots must keep failing (until a phase
consciously closes one), and metrics may never drop below the committed baseline.
"""

import json
from pathlib import Path

from blast_radius.engine import inspector
from blast_radius.engine.bank import ScenarioBank
from blast_radius.eval import evaluate_detection, load_corpus

DATA_DIR = Path(__file__).resolve().parents[1] / "blast_radius" / "data"
CORPUS = DATA_DIR / "detection_corpus.jsonl"
BASELINE = DATA_DIR / "detection_eval_baseline.json"

_KNOWN_CATEGORIES = {c.id for c in inspector.CATEGORIES} | {
    "exfil_chain",
    "unrestricted_egress",
    "workspace_wide_scope",
}
_VERDICTS = {"looks-scoped", "sandbox-recommended", "reject-recommended"}


def _samples():
    return load_corpus(CORPUS)


def test_corpus_is_well_formed() -> None:
    samples = _samples()
    assert len(samples) >= 30
    ids = [s.id for s in samples]
    assert len(ids) == len(set(ids)), "corpus ids must be unique"
    for sample in samples:
        assert sample.kind in {"command", "diff", "config"}
        assert sample.label in {"malicious", "benign"}
        assert sample.status in {"pass", "xfail"}
        assert sample.expected_verdict in _VERDICTS
        assert set(sample.expected_categories) <= _KNOWN_CATEGORIES, sample.id
        if sample.kind == "config":
            assert sample.config is not None, sample.id
        else:
            assert sample.input, sample.id


def test_corpus_does_not_reuse_bank_artifacts() -> None:
    # The benchmark must stay independent of curated training content, mirroring
    # the API's anti-oracle-leak posture (a live drill artifact can't be scored
    # here as if it were the user's own).
    bank_prints = inspector.bank_artifact_fingerprints(ScenarioBank(DATA_DIR))
    for sample in _samples():
        if sample.kind == "config":
            continue
        prints = inspector.guard_fingerprints(sample.input, sample.kind)
        assert prints.isdisjoint(bank_prints), f"{sample.id} reuses a bank artifact"


def test_pass_samples_meet_their_expectation() -> None:
    # The hard regression gate: any inspector change that breaks a defended
    # invariant fails here, naming the sample.
    report = evaluate_detection(_samples())
    failing = [
        r.id for r in report.results if r.status == "pass" and not r.meets_expectation
    ]
    assert not failing, f"defended samples no longer meet expectation: {failing}"
    assert report.pass_regressions == 0


def test_xfail_samples_still_fail_as_documented() -> None:
    # Blind spots must stay documented. If one starts passing, a phase closed it —
    # promote it to status='pass' (this test tells you which).
    report = evaluate_detection(_samples())
    promotable = [
        r.id for r in report.results if r.status == "xfail" and r.meets_expectation
    ]
    assert not promotable, f"xfail samples now pass — promote to status=pass: {promotable}"
    assert report.xfail_unexpectedly_passing == 0


def test_metrics_do_not_regress_below_committed_baseline() -> None:
    report = evaluate_detection(_samples())
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    epsilon = 1e-9
    for metric in ("precision", "recall", "f1"):
        assert getattr(report, metric) + epsilon >= baseline[metric], metric
    assert report.false_positive_rate <= baseline["false_positive_rate"] + epsilon
    for category, stats in baseline["per_category"].items():
        current = report.per_category.get(category, {}).get("recall", 0.0)
        assert current + epsilon >= stats["recall"], f"{category} recall regressed"


def test_report_carries_engine_identity_and_is_json_safe() -> None:
    report = evaluate_detection(_samples())
    assert report.engine_version == inspector.ENGINE_VERSION
    assert report.categories_hash == inspector._categories_hash()
    assert report.graded_by == "deterministic"
    # Round-trips through JSON with no surprises (the shape the CLI/API serve).
    payload = json.loads(json.dumps(report.to_dict()))
    assert set(payload["confusion"]) == _VERDICTS
    assert payload["total"] == report.total


def test_flagged_definition_matches_verdict() -> None:
    # A sample is "flagged" iff it is not looks-scoped — the honest binary the
    # precision/recall math rests on.
    report = evaluate_detection(_samples())
    for result in report.results:
        assert result.flagged == (result.actual_verdict != "looks-scoped")
