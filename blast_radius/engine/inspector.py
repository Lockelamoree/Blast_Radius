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

import base64
import binascii
import hashlib
import json
import platform
import re
import unicodedata
from dataclasses import dataclass, field

from blast_radius.engine import custom_rules, grader
from blast_radius.engine.gate import _GENERATED_PRESENTATION_BLOCKLIST, _canonicalize
from blast_radius.models import (
    BlastRadiusConfig,
    CustomRulesConfig,
    InspectionFinding,
    InspectionMatch,
    InspectionProvenance,
    InspectionReport,
    ScenarioFamily,
)

# Bumped whenever the deterministic screen's behaviour changes. Recorded in every
# InspectionProvenance so a verdict can be tied to the exact engine that produced it.
# 1.2.0: canonicalized authority screening, removed-guard diff detection,
# dependency provenance checks, and config capability-combination findings.
ENGINE_VERSION = "1.2.0"

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
        "capabilities exceed the stated purpose",
        "declared job does not need secrets",
        "hidden credential upload",
        "hidden instruction in the tool description",
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
        "untrusted page impersonates authority",
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
            # Other credential stores agents routinely have on disk.
            _p(r"\.netrc\b"),
            _p(r"~/\.kube"),
            _p(r"~/\.config/gcloud"),
            _p(r"~/\.docker/config"),
            _p(r"\.pgpass\b"),
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
            # Other tools that move bytes off the machine.
            "ncat",
            "socat",
            "telnet",
            "scp",
        ),
        patterns=(
            _p(r"\brequests\.post\b"),
            _p(r"https?://\d{1,3}(?:\.\d{1,3}){3}"),  # raw-IPv4 URL
            _p(r"https?://\[[0-9a-f:]+\]"),  # raw-IPv6 URL (bracketed)
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
            # rm with recursive AND force split across separate/long flags, any order.
            _p(
                r"\brm\b(?=[^|\n]*(?:\s-[a-z]*r\b|\s--recursive\b))"
                r"(?=[^|\n]*(?:\s-[a-z]*f\b|\s--force\b))"
            ),
            _p(r"\bdrop\s+table\b"),
            _p(r"\bmkfs\b"),
            _p(r"\bdd\s+if="),
            _p(r"\bshred\b"),
            _p(r">\s*/dev/sd[a-z]"),  # overwrite a raw block device
            _p(r"\bgit\s+push\b[^|\n]*--force"),  # rewrite published history
        ),
    ),
    CategorySpec(
        id="remote_code_pipe",
        label="Pipes remote code straight into a shell",
        severity="critical",
        families=(_F.POISONED_CONTEXT, _F.DANGEROUS_COMMAND),
        patterns=(
            # curl/wget piped into any common interpreter (shells + scripting langs).
            _p(
                r"(?:curl|wget)[^|\n]*\|\s*(?:sudo\s+)?"
                r"(?:(?:ba|z|k|da)?sh|python[0-9.]*|perl|ruby|node|php)\b"
            ),
            # process-substitution form: bash/sh/source <(curl ...).
            _p(r"(?:source|\.|bash|sh|zsh)\s+<\(\s*(?:curl|wget)\b"),
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
    # Removed guards are scanned only from deleted lines in a real unified-diff
    # hunk. Keeping the category in this frozen table makes its identity part of
    # the provenance hash without allowing ordinary added text to trigger it.
    CategorySpec(
        id="removed_guard",
        label="Removes an authorization or verification guard",
        severity="critical",
        families=(_F.MALICIOUS_DIFF,),
    ),
)


def _categories_hash() -> str:
    """Stable SHA-256 over the frozen CATEGORIES table. Cosmetic reorders are
    no-ops (everything sorted); any content change churns the hash, so a pinned
    test turns silent drift into a loud failure. ENGINE_VERSION is deliberately
    NOT folded in — version and content-hash stay independent."""
    payload = [
        {
            "id": category.id,
            "label": category.label,
            "severity": category.severity,
            "families": sorted(family.value for family in category.families),
            "keywords": sorted(category.keywords),
            "patterns": sorted(pattern.pattern for pattern in category.patterns),
        }
        for category in CATEGORIES
    ]
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _build_provenance(
    input_fingerprint: str,
    driving: list[str],
    *,
    decode_layers: int = 0,
    custom_rules_fingerprint: str = "",
) -> InspectionProvenance:
    """A reproducible receipt. `runtime` carries the CPython + Unicode DB versions
    because canonicalization (a later phase) depends on the Unicode DB, so a
    receipt without them could not let a reviewer reproduce a verdict elsewhere.
    `decode_layers` records how many embedded payloads were decoded and rescanned;
    `custom_rules_fingerprint` ties the verdict to any team rule set applied."""
    return InspectionProvenance(
        engine_version=ENGINE_VERSION,
        categories_hash=_categories_hash(),
        input_fingerprint=input_fingerprint,
        driving_findings=list(driving),
        decode_layers=decode_layers,
        custom_rules_fingerprint=custom_rules_fingerprint,
        runtime={
            "python": platform.python_version(),
            "unicode": unicodedata.unidata_version,
        },
    )


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _diff_split(content: str) -> tuple[str, str, str]:
    """Return ``(added, removed, parsed_as)`` for a diff-like payload.

    Existing callers keep added-lines-only screening for header-style diffs.
    Removed lines are exposed only when a real ``@@`` hunk header exists, so PR
    prose and changelogs cannot activate the removed-guard detector.
    """
    lines = content.split("\n")
    looks_like_diff = any(
        line.startswith(("+++", "---", "@@", "diff ")) for line in lines
    )
    if not looks_like_diff:
        return content, "", "plain-text"
    added = [
        line[1:]
        for line in lines
        if line.startswith("+") and not line.startswith("+++")
    ]
    has_hunk = any(line.startswith("@@") for line in lines)
    removed = (
        [
            line[1:]
            for line in lines
            if line.startswith("-") and not line.startswith("---")
        ]
        if has_hunk
        else []
    )
    return "\n".join(added), "\n".join(removed), "unified-diff"


def _diff_added_text(content: str) -> tuple[str, str]:
    """Backward-compatible shim returning ``(added, parsed_as)``."""

    added, _, parsed_as = _diff_split(content)
    return added, parsed_as


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


def _custom_categories(config: CustomRulesConfig | None) -> tuple[CategorySpec, ...]:
    """Turn team custom rules into detector CategorySpecs. They screen with the
    exact same token+regex machinery as built-ins, so custom coverage is real
    coverage — never a second-class path."""
    if config is None:
        return ()
    return tuple(
        CategorySpec(
            id=rule.id,
            label=rule.label,
            severity=rule.severity,
            families=(rule.family,),
            keywords=tuple(rule.keywords),
            patterns=tuple(_p(pattern) for pattern in rule.patterns),
        )
        for rule in config.rules
    )


def _apply_allowlist(
    findings: list[InspectionFinding], config: CustomRulesConfig | None
) -> list[InspectionFinding]:
    """Drop *caution* findings whose evidence matches a team allowlist regex.
    Critical findings are never dropped — the schema and this guard together make
    it impossible for a config to hide a real critical."""
    if config is None or not config.allowlist:
        return findings
    allow = [re.compile(pattern, re.IGNORECASE) for pattern in config.allowlist]
    kept: list[InspectionFinding] = []
    for finding in findings:
        if finding.severity == "critical":
            kept.append(finding)
            continue
        evidence = " ".join(f"{match.matched} {match.excerpt}" for match in finding.matches)
        if any(pattern.search(evidence) for pattern in allow):
            continue  # caution acknowledged by the team's allowlist
        kept.append(finding)
    return kept


def _scan(
    scanned: str, categories: tuple[CategorySpec, ...] = CATEGORIES
) -> list[InspectionFinding]:
    findings: list[InspectionFinding] = []
    for category in categories:
        category_text = _canonicalize(scanned) if category.id == "authority_override" else scanned
        tokens = grader.tokenize(category_text)
        lower = category_text.lower()
        seen: set[str] = set()
        matches: list[InspectionMatch] = []
        for keyword in category.keywords:
            if grader.keyword_matches(keyword, tokens) and keyword not in seen:
                seen.add(keyword)
                excerpt = _locate(lower, category_text, keyword) or keyword
                if category_text != scanned:
                    excerpt = f"{excerpt} (normalized from: {_excerpt(scanned, 0, len(scanned))})"
                matches.append(InspectionMatch(matched=keyword, excerpt=excerpt))
        for pattern in category.patterns:
            for hit in pattern.finditer(category_text):
                token = hit.group(0).strip()
                if token and token not in seen:
                    seen.add(token)
                    excerpt = _excerpt(category_text, hit.start(), hit.end())
                    if category_text != scanned:
                        excerpt = (
                            f"{excerpt} (normalized from: "
                            f"{_excerpt(scanned, 0, len(scanned))})"
                        )
                    matches.append(
                        InspectionMatch(
                            matched=token,
                            excerpt=excerpt,
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


_GUARD_REMOVAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    _p(r"\b(?:is_|has_)?authenticated\b"),
    _p(r"\b(?:is_|has_)?authori[sz]ed\b"),
    _p(r"\b(?:check|require|verify|enforce)_(?:auth|permission|access|role)\b"),
    _p(r"\b(?:permission|access|role)_required\b"),
    _p(r"\b(?:deny|forbid|forbidden|unauthori[sz]ed)\b"),
)


def _normalized_diff_line(line: str) -> str:
    return " ".join(line.split())


def _scan_removed_guards(removed: str, added: str) -> list[InspectionFinding]:
    """Flag deleted guard lines unless that exact normalized line was re-added.

    Cross-file moves are intentionally out of scope. Regex-only suppression is
    avoided because an added comment mentioning a guard must not hide a deletion.
    """

    if not removed:
        return []
    added_lines = {_normalized_diff_line(line) for line in added.splitlines() if line.strip()}
    matches: list[InspectionMatch] = []
    seen: set[str] = set()
    for line in removed.splitlines():
        stripped = line.strip()
        normalized = _normalized_diff_line(line)
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue
        if normalized in added_lines:
            continue
        for pattern in _GUARD_REMOVAL_PATTERNS:
            hit = pattern.search(line)
            if hit and normalized not in seen:
                seen.add(normalized)
                matches.append(InspectionMatch(matched=hit.group(0), excerpt=stripped))
                break
        if len(matches) >= _MAX_MATCHES_PER_CATEGORY:
            break
    if not matches:
        return []
    return [
        InspectionFinding(
            category="removed_guard",
            label="Removes an authorization or verification guard",
            severity="critical",
            families=[ScenarioFamily.MALICIOUS_DIFF.value],
            matches=matches,
        )
    ]


KNOWN_PACKAGES: frozenset[str] = frozenset(
    {
        "aiohttp",
        "black",
        "boto3",
        "django",
        "fastapi",
        "flask",
        "httpx",
        "jinja2",
        "mypy",
        "numpy",
        "openai",
        "pandas",
        "pillow",
        "pydantic",
        "pytest",
        "requests",
        "ruff",
        "scipy",
        "sqlalchemy",
        "starlette",
        "torch",
        "transformers",
        "uvicorn",
    }
)
_PIP_INSTALL = re.compile(r"\b(?:python\s+-m\s+)?pip\s+install\s+([^\n;&|]+)", re.IGNORECASE)
_INSTALL_HOOKS = (
    _p(r"[\"']?(?:preinstall|postinstall|prepare)[\"']?\s*[:=]"),
    _p(r"\bsetup\.py\s+(?:install|develop)\b"),
)


def _damerau_levenshtein(left: str, right: str) -> int:
    """Small, deterministic optimal-string-alignment distance (inputs bounded)."""

    left, right = left[:40], right[:40]
    rows = len(left) + 1
    cols = len(right) + 1
    table = [[0] * cols for _ in range(rows)]
    for index in range(rows):
        table[index][0] = index
    for index in range(cols):
        table[0][index] = index
    for row in range(1, rows):
        for col in range(1, cols):
            cost = 0 if left[row - 1] == right[col - 1] else 1
            table[row][col] = min(
                table[row - 1][col] + 1,
                table[row][col - 1] + 1,
                table[row - 1][col - 1] + cost,
            )
            if (
                row > 1
                and col > 1
                and left[row - 1] == right[col - 2]
                and left[row - 2] == right[col - 1]
            ):
                table[row][col] = min(table[row][col], table[row - 2][col - 2] + cost)
    return table[-1][-1]


def _dependency_findings(scanned: str) -> list[InspectionFinding]:
    matches: list[InspectionMatch] = []
    benign_near_names = {"boto", "pyaml"}
    for command in _PIP_INSTALL.finditer(scanned):
        for raw_name in command.group(1).split():
            name = re.split(r"[<>=!~\[]", raw_name, maxsplit=1)[0].strip("'\"").lower()
            if (
                not name
                or name.startswith(("-", "git+", "http://", "https://", ".", "/"))
                or name in KNOWN_PACKAGES
                or name in benign_near_names
                or len(name) < 4
            ):
                continue
            ranked = sorted(
                ((_damerau_levenshtein(name, known), known) for known in KNOWN_PACKAGES),
                key=lambda item: (item[0], item[1]),
            )
            distance, known = ranked[0]
            limit = 1 if len(name) < 8 else 2
            if distance <= limit:
                matches.append(
                    InspectionMatch(
                        matched=name,
                        excerpt=f"{name} is distance {distance} from known package {known}",
                    )
                )
    for pattern in _INSTALL_HOOKS:
        for hit in pattern.finditer(scanned):
            matches.append(
                InspectionMatch(
                    matched=hit.group(0).strip(),
                    excerpt=_excerpt(scanned, hit.start(), hit.end()),
                )
            )
    if not matches:
        return []
    return [
        InspectionFinding(
            category="provenance_mismatch",
            label="Dependency provenance does not check out",
            severity="caution",
            families=[ScenarioFamily.POISONED_DEPENDENCY.value],
            matches=matches[:_MAX_MATCHES_PER_CATEGORY],
        )
    ]


# --- bounded obfuscation decode (item: base64/hex payloads) ------------------
# A single decode layer only, hard-capped, so the pass stays deterministic and
# fast (<100ms). Decoding can only ADD findings — it never removes one — so the
# verdict tier is monotonic (a decoded reject cannot downgrade a scanned reject).
_MAX_DECODE_BLOBS = 8
_MAX_DECODE_CHARS = 8192
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX_BLOB = re.compile(r"(?:[0-9a-fA-F]{2}){8,}")


def _looks_textual(value: str) -> bool:
    return len(value) >= 3 and all(ch.isprintable() or ch in "\t\n\r " for ch in value)


def _decode_candidates(text: str) -> list[str]:
    """Return decoded, human-readable payloads embedded as base64 or hex blobs.
    Bounded in count and size; non-textual decodings (the overwhelmingly common
    case for ordinary tokens/hashes) are discarded so this adds signal, not noise."""
    decoded: list[str] = []
    seen: set[str] = set()
    for pattern, is_b64 in ((_B64_BLOB, True), (_HEX_BLOB, False)):
        for match in pattern.finditer(text):
            if len(decoded) >= _MAX_DECODE_BLOBS:
                break
            blob = match.group(0)[:_MAX_DECODE_CHARS]
            try:
                if is_b64:
                    raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
                else:
                    raw = bytes.fromhex(blob[: len(blob) - len(blob) % 2])
            except (binascii.Error, ValueError):
                continue
            try:
                payload = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if _looks_textual(payload) and payload not in seen:
                seen.add(payload)
                decoded.append(payload)
    return decoded


def _merge_findings(findings: list[InspectionFinding]) -> list[InspectionFinding]:
    """Collapse findings from multiple scans (scanned text + decoded payloads) to
    one per category, preserving first-seen order and merging unique matches up to
    the per-category cap. Idempotent for a single scan (no duplicate categories)."""
    merged: dict[str, InspectionFinding] = {}
    order: list[str] = []
    for finding in findings:
        existing = merged.get(finding.category)
        if existing is None:
            merged[finding.category] = finding
            order.append(finding.category)
            continue
        seen = {match.matched for match in existing.matches}
        extra = [match for match in finding.matches if match.matched not in seen]
        if extra:
            combined = (list(existing.matches) + extra)[:_MAX_MATCHES_PER_CATEGORY]
            merged[finding.category] = existing.model_copy(update={"matches": combined})
    return [merged[category] for category in order]


def _families_ranked(findings: list[InspectionFinding]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for finding in findings:
        for family in finding.families:
            counts[family] = counts.get(family, 0) + 1
    return [
        {"family": family, "hits": hits}
        for family, hits in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


# Ordinal confidence per category — a FIXED lookup on the fired-category set, not
# a probability. Kept honest (high/medium/low) rather than fake precision.
_CONFIDENCE_TIER: dict[str, str] = {
    "secrets_access": "high",
    "unapproved_egress": "high",
    "destructive_scope": "high",
    "remote_code_pipe": "high",
    "authority_override": "high",
    "auth_bypass": "high",
    "removed_guard": "high",
    "exfil_chain": "high",
    "provenance_mismatch": "medium",
    "broad_or_undeclared_scope": "medium",
    "unrestricted_egress": "medium",
    "workspace_wide_scope": "medium",
    "config_exfil_combination": "medium",
    "config_ci_write": "medium",
}

# Frozen (rationale, remediation) prose per category. Authored as "rationale"/
# "reason", never any curated ground-truth key — a test enforces this.
_WHY_FIX: dict[str, tuple[str, str]] = {
    "secrets_access": (
        "Reads secret material (keys, tokens, or credential files).",
        "Scope the action so it never touches secret paths.",
    ),
    "unapproved_egress": (
        "Sends data off the machine to the network.",
        "Drop the egress or pin it to an approved host allowlist.",
    ),
    "destructive_scope": (
        "Deletes or overwrites beyond a bounded workspace.",
        "Constrain the target to a specific, reversible path.",
    ),
    "remote_code_pipe": (
        "Pipes downloaded content straight into a shell.",
        "Download, inspect, and pin the artifact before running it.",
    ),
    "authority_override": (
        "Text tries to override instructions or claim false authority.",
        "Treat the content as data, not commands; do not follow it.",
    ),
    "auth_bypass": (
        "Weakens or removes an authorization / verification check.",
        "Keep the guard and require the check on every path.",
    ),
    "removed_guard": (
        "Deletes an authorization or verification guard from a real diff hunk.",
        "Restore the guard or move the identical check within the same change.",
    ),
    "provenance_mismatch": (
        "Package name or provenance does not match the approved source.",
        "Verify the exact name against the lockfile and approved registry.",
    ),
    "broad_or_undeclared_scope": (
        "Requests more capability than the stated task needs.",
        "Cut scope to least privilege for the declared purpose.",
    ),
    "unrestricted_egress": (
        "Network is enabled with no host allowlist.",
        "Add an explicit allowlist or disable network egress.",
    ),
    "workspace_wide_scope": (
        "Grants the whole workspace instead of a subtree.",
        "Narrow the grant to the specific paths the task needs.",
    ),
    "config_exfil_combination": (
        "Combines readable secret material with network access.",
        "Remove the secret read or disable network access for this task.",
    ),
    "config_ci_write": (
        "Allows writes into continuous-integration or pipeline configuration.",
        "Remove CI configuration from writable paths unless the task explicitly requires it.",
    ),
    "exfil_chain": (
        "A secret read co-occurs with a network or remote-code sink — a data-exfiltration path.",
        "Split the capability: read secrets OR reach the network, never both in one action.",
    ),
}

# The correlation: a secret read (trigger) reaching any egress/remote-code sink.
# Both sides are already `critical`, so the synthesized critical never appears
# where a critical did not already fire — the verdict tier is invariant (tested).
_EXFIL_TRIGGER = "secrets_access"
_EXFIL_SINKS = ("unapproved_egress", "remote_code_pipe")  # frozen order


def _enrich_findings(findings: list[InspectionFinding]) -> list[InspectionFinding]:
    """Attach an ordinal confidence tier + frozen why/fix rationale to each
    finding. Purely additive metadata — never changes category or severity, so
    _verdict is untouched."""
    enriched: list[InspectionFinding] = []
    for finding in findings:
        why, fix = _WHY_FIX.get(finding.category, (None, None))
        enriched.append(
            finding.model_copy(
                update={
                    "confidence": _CONFIDENCE_TIER.get(finding.category, ""),
                    "why": why,
                    "fix": fix,
                }
            )
        )
    return enriched


def _correlate(findings: list[InspectionFinding]) -> list[InspectionFinding]:
    """Synthesize an exfil_chain finding when a secret read co-occurs with a
    network / remote-code sink. Cites the REAL matches from both sides (no
    fabricated excerpt), and picks the sink by frozen order for determinism."""
    by_category = {finding.category: finding for finding in findings}
    if _EXFIL_TRIGGER not in by_category:
        return []
    sink = next((name for name in _EXFIL_SINKS if name in by_category), None)
    if sink is None:
        return []
    contributing = {_EXFIL_TRIGGER, sink}
    families = list(
        dict.fromkeys(
            family.value
            for category in CATEGORIES
            if category.id in contributing
            for family in category.families
        )
    )
    cited = list(by_category[_EXFIL_TRIGGER].matches[:2]) + list(by_category[sink].matches[:2])
    return [
        InspectionFinding(
            category="exfil_chain",
            label="Secret read chained to a network / remote-code sink",
            severity="critical",
            families=families,
            matches=cited,
        )
    ]


def _report_confidence(findings: list[InspectionFinding]) -> str:
    order = {"high": 3, "medium": 2, "low": 1, "": 0}
    return max(
        (finding.confidence for finding in findings),
        key=lambda tier: order.get(tier, 0),
        default="",
    )


def _verdict(
    findings: list[InspectionFinding],
    *,
    score: int | None = None,
    has_excess: bool = False,
) -> tuple[str, list[str]]:
    """Return (verdict, driving) — the ordered signals that SET the verdict, so the
    provenance receipt echoes this single source of truth rather than re-deriving
    (and possibly diverging from) the branch logic."""
    criticals = [finding.category for finding in findings if finding.severity == "critical"]
    if criticals:
        return "reject-recommended", criticals
    driving = [finding.category for finding in findings if finding.severity == "caution"]
    if has_excess:
        driving.append("policy-excess")
    if score is not None and score < 70:
        driving.append("low-score")
    if driving:
        return "sandbox-recommended", driving
    return "looks-scoped", []


def inspect_text(
    content: str, *, kind: str, custom: CustomRulesConfig | None = None
) -> InspectionReport:
    if kind not in {"command", "diff"}:
        raise ValueError("inspect_text kind must be 'command' or 'diff'")
    normalized = _normalize(content)
    parsed_as: str | None = None
    scanned = normalized
    removed = ""
    if kind == "diff":
        scanned, removed, parsed_as = _diff_split(normalized)
    categories = CATEGORIES + _custom_categories(custom)
    scanned_findings = _scan(scanned, categories)
    scanned_findings.extend(_dependency_findings(scanned))
    if kind == "diff":
        scanned_findings.extend(_scan_removed_guards(removed, scanned))
    decoded_payloads = _decode_candidates(scanned)
    for payload in decoded_payloads:
        scanned_findings.extend(_scan(payload, categories))
    scanned_findings = _merge_findings(scanned_findings)
    scanned_findings = _apply_allowlist(scanned_findings, custom)
    correlations = _correlate(scanned_findings)
    findings = _enrich_findings(scanned_findings + correlations)
    verdict, driving = _verdict(findings)
    return InspectionReport(
        kind=kind,
        verdict=verdict,
        findings=findings,
        families=_families_ranked(findings),
        parsed_as=parsed_as,
        confidence=_report_confidence(findings),
        correlations=[
            {"category": finding.category, "families": finding.families}
            for finding in correlations
        ],
        provenance=_build_provenance(
            fingerprint_text(scanned),
            driving,
            decode_layers=len(decoded_payloads),
            custom_rules_fingerprint=custom_rules.fingerprint(custom),
        ),
    )


ZERO_TRUST = BlastRadiusConfig()

_SECRET_PATH_SEGMENTS = frozenset(
    {".ssh", ".aws", ".env", "secrets", "credentials", ".netrc", "id_rsa"}
)
_CI_WRITE_SEGMENTS = frozenset(
    {".github", ".gitlab-ci", "ci", ".circleci", "jenkinsfile", "buildkite"}
)


def _path_segments(path: str) -> set[str]:
    return {segment.casefold() for segment in path.replace("\\", "/").split("/") if segment}


def inspect_config(
    config: BlastRadiusConfig,
    expected: BlastRadiusConfig | None = None,
    *,
    custom: CustomRulesConfig | None = None,
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
    secret_reads = [
        path
        for path in config.readable_paths
        if _path_segments(path) & _SECRET_PATH_SEGMENTS
    ]
    if secret_reads and config.network_enabled:
        findings.append(
            InspectionFinding(
                category="config_exfil_combination",
                label="Secret-readable path combined with network access",
                severity="caution",
                families=[ScenarioFamily.OVERSCOPED_TOOL.value],
                matches=[
                    InspectionMatch(
                        matched=secret_reads[0],
                        excerpt=f"readable secret path plus network_enabled=true: {secret_reads[0]}",
                    )
                ],
            )
        )
    ci_writes = [
        path
        for path in config.writable_paths
        if _path_segments(path) & _CI_WRITE_SEGMENTS
    ]
    if ci_writes:
        findings.append(
            InspectionFinding(
                category="config_ci_write",
                label="Writes into CI or pipeline configuration",
                severity="caution",
                families=[ScenarioFamily.MALICIOUS_DIFF.value],
                matches=[
                    InspectionMatch(
                        matched=ci_writes[0],
                        excerpt=f"writable_paths includes CI configuration: {ci_writes[0]}",
                    )
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
    findings = _apply_allowlist(findings, custom)
    findings = _enrich_findings(findings)  # config owns no correlation (item 12)
    verdict, driving = _verdict(findings, score=score, has_excess=has_excess)
    config_fingerprint = fingerprint_text(
        json.dumps(config.model_dump(mode="json"), sort_keys=True)
    )
    return InspectionReport(
        kind="config",
        verdict=verdict,
        findings=findings,
        families=_families_ranked(findings),
        score=score,
        baseline=baseline,
        policy_deltas=deltas,
        confidence=_report_confidence(findings),
        provenance=_build_provenance(
            config_fingerprint,
            driving,
            custom_rules_fingerprint=custom_rules.fingerprint(custom),
        ),
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
            fingerprints.add(fingerprint_text(artifact.content))
            added, removed, parsed_as = _diff_split(_normalize(artifact.content))
            if parsed_as == "unified-diff":
                fingerprints.add(fingerprint_text(added))
                if removed:
                    fingerprints.add(fingerprint_text(removed))
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
        added, removed, _ = _diff_split(_normalize(content))
        prints.add(fingerprint_text(added))
        if removed:
            prints.add(fingerprint_text(removed))
    return prints
