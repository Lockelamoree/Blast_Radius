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


_LOW_SIGNAL_SINGLE_KEYWORDS = {
    "a",
    "an",
    "and",
    "approved",
    "argument",
    "are",
    "as",
    "at",
    "be",
    "by",
    "bounded",
    "condition",
    "five",
    "for",
    "from",
    "generated",
    "has",
    "have",
    "if",
    "in",
    "is",
    "it",
    "key",
    "local",
    "match",
    "matches",
    "network",
    "new",
    "narrow",
    "no",
    "not",
    "of",
    "on",
    "one",
    "or",
    "policy",
    "post",
    "private",
    "public",
    "purpose",
    "read",
    "remote",
    "requests",
    "routine",
    "single",
    "sandbox",
    "source",
    "test",
    "that",
    "the",
    "this",
    "to",
    "unknown",
    "was",
    "with",
    "workspace",
    "write",
    "zero",
}
_LOW_SIGNAL_PHRASES = {("no", "new")}


def _tokens(value: str) -> tuple[str, ...]:
    normalized = value.lower().replace("_", " ")
    return tuple(re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", normalized))


def _contains_phrase(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _keyword_matches(keyword: str, reasoning: tuple[str, ...]) -> bool:
    keyword_tokens = _tokens(keyword)
    if not keyword_tokens:
        return False
    if len(keyword_tokens) == 1:
        token = keyword_tokens[0]
        return token not in _LOW_SIGNAL_SINGLE_KEYWORDS and token in reasoning
    if keyword_tokens in _LOW_SIGNAL_PHRASES:
        return False
    return _contains_phrase(reasoning, keyword_tokens)


def score_blast_radius(actual: BlastRadiusConfig, expected: BlastRadiusConfig) -> int:
    actual_reads = set(actual.readable_paths)
    expected_reads = set(expected.readable_paths)
    actual_writes = set(actual.writable_paths)
    expected_writes = set(expected.writable_paths)
    actual_hosts = set(actual.network_allowlist)
    expected_hosts = set(expected.network_allowlist)
    actual_capabilities = set(actual.capabilities)
    expected_capabilities = set(expected.capabilities)

    score = 100
    missing_reads = expected_reads - actual_reads
    missing_writes = expected_writes - actual_writes
    missing_hosts = expected_hosts - actual_hosts
    missing_capabilities = expected_capabilities - actual_capabilities
    if missing_reads:
        score -= min(40, 20 * len(missing_reads))
    if missing_writes:
        score -= min(50, 25 * len(missing_writes))
    if actual.network_enabled != expected.network_enabled:
        score -= 30
    if missing_hosts:
        score -= min(40, 20 * len(missing_hosts))
    if missing_capabilities:
        score -= min(40, 20 * len(missing_capabilities))

    extra_scope = (
        (actual_reads - expected_reads)
        | (actual_writes - expected_writes)
        | (actual_hosts - expected_hosts)
        | (actual_capabilities - expected_capabilities)
    )
    forbidden_network_escalation = actual.network_enabled and not expected.network_enabled
    incomplete_scope = bool(
        missing_reads
        or missing_writes
        or missing_hosts
        or missing_capabilities
        or actual.network_enabled != expected.network_enabled
    )
    if extra_scope or forbidden_network_escalation or incomplete_scope:
        score = min(score, 60)
    return max(0, score)


def grade_decision(scenario: Scenario, decision: PlayerDecision) -> GradeResult:
    truth = scenario.ground_truth
    action_correct = decision.action == truth.correct_action
    reasoning_tokens = _tokens(decision.reasoning_text)
    matched: list[str] = []
    for tell, keywords in truth.tell_keywords.items():
        if any(_keyword_matches(keyword, reasoning_tokens) for keyword in keywords):
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
        deterministic_matched_tells=list(matched),
    )


def merge_reasoning(
    base: GradeResult,
    scenario: Scenario,
    llm_matched_tells: list[str],
    followup: str | None,
) -> GradeResult:
    """Merge model tell recognition without allowing it to alter immutable truth."""
    allowed_tells = scenario.ground_truth.tells
    allowed = set(allowed_tells)
    matched = list(
        dict.fromkeys(
            [*base.matched_tells, *(tell for tell in llm_matched_tells if tell in allowed)]
        )
    )
    missed = [tell for tell in allowed_tells if tell not in matched]
    reasoning_score = round(100 * len(matched) / len(allowed_tells))

    if base.action_correct and reasoning_score >= 60 and (
        base.blast_radius_score is None or base.blast_radius_score >= 70
    ):
        verdict = "correct"
    elif base.action_correct or reasoning_score >= 50:
        verdict = "partial"
    else:
        verdict = "wrong"

    return base.model_copy(
        update={
            "matched_tells": matched,
            "missed_tells": missed,
            "reasoning_score": reasoning_score,
            "verdict": verdict,
            "socratic_followup": followup or base.socratic_followup,
        }
    )
