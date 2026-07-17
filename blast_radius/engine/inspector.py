"""Deterministic, headless red-flag screen for real developer artifacts.

This is NOT a model and NOT a proof of safety. It runs the same token logic the
grader uses (``grader.keyword_matches``) plus a frozen table of regex patterns
over a command, a diff, or a sandbox config, and reports which known red-flag
categories match. It never executes an artifact and never exposes any bank
scenario's ground truth — the detector table is seeded once at authoring time
from the union of red-polarity tell keywords, not read from the bank at runtime.

The API layer adds a fingerprint guard so pasting a live drill artifact here
cannot leak that scenario's verdict; this module stays pure and stateless.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from blast_radius.engine import grader
from blast_radius.engine.gate import _GENERATED_PRESENTATION_BLOCKLIST
from blast_radius.models import (
    BlastRadiusConfig,
    InspectionFinding,
    InspectionMatch,
    InspectionReport,
    ScenarioFamily,
)

_MAX_MATCHES_PER_CATEGORY = 6
_EXCERPT_RADIUS = 40

# Approve/sandbox tell names from the curated bank. These describe benign or
# already-contained behaviour and are never detectors. The sync test asserts
# every bank tell is either here or in RED_TELLS, so a new scenario forces a
# conscious classification rather than silently drifting past the screen.
GREEN_TELLS: frozenset[str] = frozenset(
    {
        "behavior and zero-capability manifest agree",
        "benign instruction consistent with repository policy",
        "change matches stated intent",
        "destructive but bounded",
        "least-privilege manifest",
        "permissions match task but writes should stay bounded",
        "routine scoped operation",
        "task needs narrow read and egress",
        "verified locked provenance",
    }
)

# Reject-polarity tell names from the curated bank. Each must be detectable by
# at least one category below (enforced by the sync test).
RED_TELLS: frozenset[str] = frozenset(
    {
        "declared job does not need secrets",
        "hidden credential upload",
        "near-miss package name",
        "not in approved lockfile",
        "production authorization bypass",
        "public author claims false authority",
        "public package shadows private dependency",
        "remote code piped to shell",
        "secret added to telemetry",
        "secret collection",
        "secret read and raw-IP egress",
        "source contradicts manifest",
        "test concern mixed into runtime",
        "unapproved egress",
        "undisclosed behavior",
        "unknown publisher",
        "unrestricted egress",
        "untrusted content impersonates authority",
    }
)

_F = ScenarioFamily


@dataclass(frozen=True)
class CategorySpec:
    id: str
    label: str
    severity: str  # "critical" | "caution"
    families: tuple[ScenarioFamily, ...]
    keywords: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        id="secrets_access",
        label="Reads or collects secret material",
        severity="critical",
        families=(
            _F.DANGEROUS_COMMAND,
            _F.OVERSCOPED_TOOL,
            _F.MALICIOUS_DIFF,
            _F.POISONED_CONTEXT,
            _F.SKILL_MARKETPLACE,
        ),
        keywords=(
            "ssh",
            "aws",
            "credential",
            "secret",
            "api key",
            "keyring",
            "password",
        ),
        patterns=(
            _p(r"~/\.ssh"),
            _p(r"~/\.aws"),
            _p(r"\.env\b"),
            _p(r"\bid_rsa\b"),
        ),
    ),
    CategorySpec(
        id="unapproved_egress",
        label="Sends data to the network",
        severity="critical",
        families=(
            _F.DANGEROUS_COMMAND,
            _F.OVERSCOPED_TOOL,
            _F.MALICIOUS_DIFF,
            _F.SKILL_MARKETPLACE,
        ),
        keywords=(
            "curl",
            "wget",
            "upload",
            "egress",
            "telemetry",
            "exfiltrate",
        ),
        patterns=(
            _p(r"\brequests\.post\b"),
            _p(r"https?://\d{1,3}(?:\.\d{1,3}){3}"),  # raw-IP URL
            _p(r"(?<![\w.])nc(?![\w.])"),  # netcat
        ),
    ),
    CategorySpec(
        id="destructive_scope",
        label="Destructive or irreversible action",
        severity="critical",
        families=(_F.DANGEROUS_COMMAND,),
        patterns=(
            _p(r"\brm\s+-[a-z]*r[a-z]*f"),
            _p(r"\brm\s+-[a-z]*f[a-z]*r"),
            _p(r"\bdrop\s+table\b"),
            _p(r"\bmkfs\b"),
            _p(r"\bdd\s+if="),
        ),
    ),
    CategorySpec(
        id="remote_code_pipe",
        label="Pipes remote code straight into a shell",
        severity="critical",
        families=(_F.POISONED_CONTEXT, _F.DANGEROUS_COMMAND),
        patterns=(
            _p(r"(?:curl|wget)[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|k|da)?sh\b"),
        ),
    ),
    CategorySpec(
        id="authority_override",
        label="Untrusted text claims authority or overrides instructions",
        severity="critical",
        families=(_F.POISONED_CONTEXT,),
        # Bare "override"/"maintainer" match too much ordinary code (@Override,
        # maintainer notes). Rely on the specific injection-phrasing regexes plus
        # the distinctive "prompt injection" phrase.
        keywords=("prompt injection",),
        patterns=_GENERATED_PRESENTATION_BLOCKLIST,
    ),
    CategorySpec(
        id="auth_bypass",
        label="Bypasses authorization or leaks test behaviour into runtime",
        severity="critical",
        families=(_F.MALICIOUS_DIFF,),
        # "admin" and a bare `if test` match innocuous code; keep the specific
        # signals only.
        keywords=("bypass", "test mode"),
        patterns=(
            _p(r"\bor\s+(?:1\s*=\s*1|true)\b"),
        ),
    ),
    CategorySpec(
        id="provenance_mismatch",
        label="Dependency provenance does not check out",
        severity="caution",
        families=(_F.POISONED_DEPENDENCY,),
        keywords=(
            "typo",
            "misspell",
            "slopsquat",
            "unknown publisher",
            "not in lockfile",
            "dependency confusion",
            "unpinned",
        ),
    ),
    CategorySpec(
        id="broad_or_undeclared_scope",
        label="Scope is broader than declared or undeclared",
        severity="caution",
        families=(_F.OVERSCOPED_TOOL, _F.SKILL_MARKETPLACE),
        keywords=("unrestricted", "undeclared", "unbounded"),
    ),
)


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _diff_added_text(content: str) -> tuple[str, str]:
    """Return (scanned_text, parsed_as). For a unified diff, scan only added
    lines (``+`` but not ``+++``); otherwise treat it as plain text."""
    lines = content.split("\n")
    looks_like_diff = any(
        line.startswith(("+++", "---", "@@", "diff ")) for line in lines
    )
    if not looks_like_diff:
        return content, "plain-text"
    added = [
        line[1:]
        for line in lines
        if line.startswith("+") and not line.startswith("+++")
    ]
    return "\n".join(added), "unified-diff"


def _excerpt(haystack: str, start: int, end: int) -> str:
    lead = max(0, start - _EXCERPT_RADIUS)
    tail = min(len(haystack), end + _EXCERPT_RADIUS)
    snippet = haystack[lead:tail].replace("\n", " ").strip()
    prefix = "…" if lead > 0 else ""
    suffix = "…" if tail < len(haystack) else ""
    return f"{prefix}{snippet}{suffix}"


def _locate(haystack_lower: str, haystack: str, keyword: str) -> str | None:
    """Best-effort excerpt for a token-matched keyword."""
    for needle in (keyword.lower(), keyword.lower().replace(" ", ""), keyword.split()[0].lower()):
        index = haystack_lower.find(needle)
        if index != -1:
            return _excerpt(haystack, index, index + len(needle))
    return None


def _scan(scanned: str) -> list[InspectionFinding]:
    tokens = grader.tokenize(scanned)
    lower = scanned.lower()
    findings: list[InspectionFinding] = []
    for category in CATEGORIES:
        seen: set[str] = set()
        matches: list[InspectionMatch] = []
        for keyword in category.keywords:
            if grader.keyword_matches(keyword, tokens) and keyword not in seen:
                seen.add(keyword)
                excerpt = _locate(lower, scanned, keyword) or keyword
                matches.append(InspectionMatch(matched=keyword, excerpt=excerpt))
        for pattern in category.patterns:
            for hit in pattern.finditer(scanned):
                token = hit.group(0).strip()
                if token and token not in seen:
                    seen.add(token)
                    matches.append(
                        InspectionMatch(
                            matched=token,
                            excerpt=_excerpt(scanned, hit.start(), hit.end()),
                        )
                    )
                if len(matches) >= _MAX_MATCHES_PER_CATEGORY:
                    break
            if len(matches) >= _MAX_MATCHES_PER_CATEGORY:
                break
        if matches:
            findings.append(
                InspectionFinding(
                    category=category.id,
                    label=category.label,
                    severity=category.severity,
                    families=[family.value for family in category.families],
                    matches=matches[:_MAX_MATCHES_PER_CATEGORY],
                )
            )
    return findings


def _families_ranked(findings: list[InspectionFinding]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for finding in findings:
        for family in finding.families:
            counts[family] = counts.get(family, 0) + 1
    return [
        {"family": family, "hits": hits}
        for family, hits in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _verdict(
    findings: list[InspectionFinding],
    *,
    score: int | None = None,
    has_excess: bool = False,
) -> str:
    if any(finding.severity == "critical" for finding in findings):
        return "reject-recommended"
    if (
        any(finding.severity == "caution" for finding in findings)
        or has_excess
        or (score is not None and score < 70)
    ):
        return "sandbox-recommended"
    return "looks-scoped"


def inspect_text(content: str, *, kind: str) -> InspectionReport:
    if kind not in {"command", "diff"}:
        raise ValueError("inspect_text kind must be 'command' or 'diff'")
    normalized = _normalize(content)
    parsed_as: str | None = None
    scanned = normalized
    if kind == "diff":
        scanned, parsed_as = _diff_added_text(normalized)
    findings = _scan(scanned)
    return InspectionReport(
        kind=kind,
        verdict=_verdict(findings),
        findings=findings,
        families=_families_ranked(findings),
        parsed_as=parsed_as,
    )


ZERO_TRUST = BlastRadiusConfig()


def inspect_config(
    config: BlastRadiusConfig, expected: BlastRadiusConfig | None = None
) -> InspectionReport:
    findings: list[InspectionFinding] = []
    if config.network_enabled and not config.network_allowlist:
        findings.append(
            InspectionFinding(
                category="unrestricted_egress",
                label="Network is on with no allowlist",
                severity="caution",
                families=[ScenarioFamily.OVERSCOPED_TOOL.value],
                matches=[
                    InspectionMatch(
                        matched="network_enabled",
                        excerpt="network_enabled=true with empty network_allowlist",
                    )
                ],
            )
        )
    workspace_wide = [
        dimension
        for dimension, paths in (
            ("writable_paths", config.writable_paths),
            ("readable_paths", config.readable_paths),
        )
        if "/workspace" in paths
    ]
    for dimension in workspace_wide:
        findings.append(
            InspectionFinding(
                category="workspace_wide_scope",
                label="Grants the whole workspace, not a subtree",
                severity="caution",
                families=[ScenarioFamily.OVERSCOPED_TOOL.value],
                matches=[
                    InspectionMatch(matched=dimension, excerpt=f"{dimension} includes /workspace"),
                ],
            )
        )
    if expected is not None:
        score: int | None = grader.score_blast_radius(config, expected)
        deltas = grader.compute_policy_deltas(config, expected)
        baseline = "explicit"
    else:
        score = None
        deltas = grader.compute_policy_deltas(config, ZERO_TRUST)
        baseline = "zero-trust"
    has_excess = any(delta.status == "excess" for delta in deltas)
    return InspectionReport(
        kind="config",
        verdict=_verdict(findings, score=score, has_excess=has_excess),
        findings=findings,
        families=_families_ranked(findings),
        score=score,
        baseline=baseline,
        policy_deltas=deltas,
    )


def _normalize_artifact(content: str) -> str:
    return " ".join(content.split()).casefold()


def bank_artifact_fingerprints(bank) -> frozenset[str]:
    """SHA-256 fingerprints of every curated artifact's normalized content, so
    the API can refuse to score a live drill scenario as if it were the user's
    own artifact (which would leak that round's verdict mid-game)."""
    fingerprints: set[str] = set()
    for scenario in bank.scenarios.values():
        for artifact in scenario.presentation.artifacts:
            digest = hashlib.sha256(
                _normalize_artifact(artifact.content).encode("utf-8")
            ).hexdigest()
            fingerprints.add(digest)
    return frozenset(fingerprints)


def fingerprint_text(content: str) -> str:
    return hashlib.sha256(_normalize_artifact(content).encode("utf-8")).hexdigest()


def guard_fingerprints(content: str, kind: str) -> set[str]:
    """Fingerprints to test against the bank so the oracle guard can't be
    dodged by wrapping a drill artifact in diff markers: for a diff we also
    fingerprint the reconstructed added-line text the scanner actually reads,
    not just the raw payload."""
    prints = {fingerprint_text(content)}
    if kind == "diff":
        added, _ = _diff_added_text(_normalize(content))
        prints.add(fingerprint_text(added))
    return prints
