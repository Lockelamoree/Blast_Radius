from __future__ import annotations

import re

from blast_radius.models import (
    Action,
    BlastRadiusConfig,
    GradeResult,
    PlayerDecision,
    Receipt,
    Scenario,
)


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_.~-]+", value.lower()))


def _path_coverage(actual: list[str], required: list[str]) -> bool:
    return all(item in actual for item in required)


def score_blast_radius(actual: BlastRadiusConfig, expected: BlastRadiusConfig) -> int:
    score = 100
    if not _path_coverage(actual.readable_paths, expected.readable_paths):
        score -= 30
    if not _path_coverage(actual.writable_paths, expected.writable_paths):
        score -= 35
    if actual.network_enabled != expected.network_enabled:
        score -= 25
    if set(actual.network_allowlist) != set(expected.network_allowlist):
        score -= 20
    if not set(expected.capabilities).issubset(actual.capabilities):
        score -= 20
    extra_writes = set(actual.writable_paths) - set(expected.writable_paths)
    extra_hosts = set(actual.network_allowlist) - set(expected.network_allowlist)
    score -= min(30, 10 * (len(extra_writes) + len(extra_hosts)))
    return max(0, score)


def grade_decision(scenario: Scenario, decision: PlayerDecision) -> GradeResult:
    truth = scenario.ground_truth
    action_correct = decision.action == truth.correct_action
    reasoning_terms = _terms(decision.reasoning_text)
    matched: list[str] = []
    for tell, keywords in truth.tell_keywords.items():
        if any(_terms(keyword) & reasoning_terms for keyword in keywords):
            matched.append(tell)
    missed = [tell for tell in truth.tells if tell not in matched]
    reasoning_score = round(100 * len(matched) / len(truth.tells))

    blast_score: int | None = None
    if decision.action == Action.SANDBOX and truth.safe_blast_radius:
        blast_score = score_blast_radius(decision.blast_radius_config, truth.safe_blast_radius)

    if action_correct and reasoning_score >= 60 and (blast_score is None or blast_score >= 70):
        verdict = "correct"
    elif action_correct or reasoning_score >= 50:
        verdict = "partial"
    else:
        verdict = "wrong"

    receipts = [
        Receipt(claim=item.claim, evidence=item.excerpt, source=item.source)
        for item in truth.evidence
    ]
    if missed:
        followup = f"What evidence would help you notice: {missed[0]}?"
    elif not action_correct:
        followup = "Your observation was useful. Which action best contains the behavior you identified?"
    else:
        followup = "Which single control reduces the blast radius most here?"
    return GradeResult(
        scenario_id=scenario.id,
        verdict=verdict,
        action_correct=action_correct,
        reasoning_score=reasoning_score,
        blast_radius_score=blast_score,
        matched_tells=matched,
        missed_tells=missed,
        receipts=receipts,
        explanation=truth.explanation,
        socratic_followup=followup,
    )

