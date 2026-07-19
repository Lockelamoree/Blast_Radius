from __future__ import annotations

import re
import unicodedata
from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import Action, GateResult, Scenario


_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_GENERATED_PRESENTATION_BLOCKLIST = (
    re.compile(r"\bsystem\s+note\b", re.IGNORECASE),
    re.compile(
        r"\b(?:ignore|disregard|override)\s+(?:all\s+)?"
        r"(?:previous|prior|developer|system)\s+instructions?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:return|reveal|list|output)\s+(?:all|every|the)\s+"
        r"(?:allowed\s+)?tells?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bmatched_tells\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+(?:the|a)\s+(?:grader|reviewer)\b", re.IGNORECASE),
    re.compile(r"<\s*(?:system|developer|assistant)\s*>", re.IGNORECASE),
)
_ANSWER_LEAK_PATTERNS = (
    re.compile(r"\bcorrect\s+action\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?answer\s+is\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+should|you\s+must)\s+(?:approve|reject|sandbox)\b", re.IGNORECASE),
    re.compile(r"\b(?:choose|select|pick|use)\s+(?:the\s+)?(?:approve|reject|sandbox)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:approve|reject|sandbox)\s+(?:this|that|the|it|request|command|package|tool|skill)\b",
        re.IGNORECASE,
    ),
)

# Canonicalization is intentionally narrow. It is used only for bounded
# grader-directed and answer-leak checks; URL and tell-support checks continue
# to inspect literal text so a normalization step can never invent evidence.
_STRIP_CODEPOINTS = frozenset(
    {
        "\u00ad",  # soft hyphen
        "\u200b",
        "\u200c",
        "\u200d",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2060",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
        "\ufeff",
    }
)
_HOMOGLYPH_MAP = str.maketrans(
    {
        # A deliberately small set of Cyrillic look-alikes needed by the scan
        # vocabulary. Mapping happens only inside mixed ASCII/non-ASCII tokens.
        "\u0405": "S",
        "\u0455": "s",
        "\u0410": "A",
        "\u0430": "a",
        "\u0415": "E",
        "\u0435": "e",
        "\u0406": "I",
        "\u0456": "i",
        "\u041e": "O",
        "\u043e": "o",
        "\u0420": "P",
        "\u0440": "p",
        "\u0421": "C",
        "\u0441": "c",
        "\u0425": "X",
        "\u0445": "x",
        "\u0423": "Y",
        "\u0443": "y",
    }
)
_CANONICAL_TOKEN = re.compile(r"\w+", re.UNICODE)


def _canonicalize(text: str) -> str:
    """Return a deterministic, idempotent form for injection/leak screening.

    NFKC and invisible-control stripping apply globally. Confusable folding is
    limited to mixed-script tokens, leaving ordinary Cyrillic words untouched.
    """

    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(character for character in folded if character not in _STRIP_CODEPOINTS)

    def fold_mixed_token(match: re.Match[str]) -> str:
        token = match.group(0)
        has_ascii_letter = any(character.isascii() and character.isalpha() for character in token)
        has_mapped_non_ascii = any(
            not character.isascii() and ord(character) in _HOMOGLYPH_MAP for character in token
        )
        return token.translate(_HOMOGLYPH_MAP) if has_ascii_letter and has_mapped_non_ascii else token

    return _CANONICAL_TOKEN.sub(fold_mixed_token, folded)


class CorrectnessGate:
    """Deterministic invariant gate. It never executes an artifact."""

    def __init__(self, bank: ScenarioBank):
        self.bank = bank

    @staticmethod
    def _compare_trusted_fields(
        scenario: Scenario,
        trusted_base: Scenario,
        *,
        require_difficulty: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if scenario.family != trusted_base.family:
            reasons.append("scenario family differs from trusted base")
        if scenario.template_ref != trusted_base.template_ref:
            reasons.append("scenario template differs from trusted base")
        if require_difficulty and scenario.difficulty != trusted_base.difficulty:
            reasons.append("curated scenario difficulty was modified")
        if scenario.ground_truth != trusted_base.ground_truth:
            reasons.append("scenario ground truth differs from trusted base")
        return reasons

    @staticmethod
    def _normalized_presentation_value(value):
        if isinstance(value, str):
            return " ".join(value.split()).casefold()
        if isinstance(value, dict):
            return {
                key: CorrectnessGate._normalized_presentation_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                CorrectnessGate._normalized_presentation_value(item) for item in value
            ]
        return value

    @staticmethod
    def _compare_generated_presentation(
        scenario: Scenario,
        trusted_base: Scenario,
    ) -> list[str]:
        reasons: list[str] = []
        candidate = scenario.presentation
        trusted = trusted_base.presentation
        if CorrectnessGate._normalized_presentation_value(
            candidate.model_dump(mode="json")
        ) == CorrectnessGate._normalized_presentation_value(
            trusted.model_dump(mode="json")
        ):
            reasons.append("generated presentation did not vary from trusted base")
        if len(candidate.artifacts) != len(trusted.artifacts):
            reasons.append("generated artifact count differs from trusted base")
            return reasons
        for index, (candidate_artifact, trusted_artifact) in enumerate(
            zip(candidate.artifacts, trusted.artifacts, strict=True)
        ):
            if (
                candidate_artifact.kind != trusted_artifact.kind
                or candidate_artifact.language != trusted_artifact.language
            ):
                reasons.append(f"generated artifact {index} changed kind or language")

        presentation_text = "\n".join(
            [candidate.eyebrow, candidate.ask_text, candidate.agent_note]
            + [artifact.title for artifact in candidate.artifacts]
            + [artifact.content for artifact in candidate.artifacts]
        )
        canonical_presentation = _canonicalize(presentation_text)
        if any(
            pattern.search(canonical_presentation)
            for pattern in _GENERATED_PRESENTATION_BLOCKLIST
        ):
            reasons.append("generated presentation contains grader-directed instructions")
        if any(pattern.search(canonical_presentation) for pattern in _ANSWER_LEAK_PATTERNS):
            reasons.append("generated presentation reveals the expected action")

        trusted_text = "\n".join(
            [trusted.eyebrow, trusted.ask_text, trusted.agent_note]
            + [artifact.title for artifact in trusted.artifacts]
            + [artifact.content for artifact in trusted.artifacts]
        )
        allowed_urls = {
            value.rstrip(".,);]") for value in _URL_PATTERN.findall(trusted_text)
        } | {evidence.source for evidence in trusted_base.ground_truth.evidence}
        generated_urls = {
            value.rstrip(".,);]") for value in _URL_PATTERN.findall(presentation_text)
        }
        if generated_urls - allowed_urls:
            reasons.append("generated presentation introduced an unverified URL")
        artifact_text = "\n".join(
            "\n".join(
                [artifact.kind, artifact.title, artifact.content, artifact.language]
            )
            for artifact in candidate.artifacts
        ).lower()
        trusted_artifact_text = "\n".join(
            "\n".join(
                [artifact.kind, artifact.title, artifact.content, artifact.language]
            )
            for artifact in trusted.artifacts
        ).lower()
        for tell, keywords in trusted_base.ground_truth.tell_keywords.items():
            supported = sum(
                CorrectnessGate._contains_keyword(artifact_text, keyword)
                for keyword in keywords
            )
            trusted_supported = sum(
                CorrectnessGate._contains_keyword(trusted_artifact_text, keyword)
                for keyword in keywords
            )
            if supported < max(1, trusted_supported):
                reasons.append(
                    f"generated presentation under-supports immutable tell: {tell}"
                )
        return reasons

    @staticmethod
    def _contains_keyword(content: str, keyword: str) -> bool:
        keyword = keyword.lower()
        suffix = r"(?:s|es)?" if keyword.isalpha() and len(keyword) >= 4 else ""
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}{suffix}(?![a-z0-9])"
        normalized_content = re.sub(r"[_-]+", " ", content)
        return bool(re.search(pattern, content) or re.search(pattern, normalized_content))

    def verify(
        self, scenario: Scenario, trusted_base: Scenario | None = None
    ) -> GateResult:
        reasons: list[str] = []
        if trusted_base is not None:
            curated_base = self.bank.scenarios.get(trusted_base.id)
            if curated_base is None:
                reasons.append("trusted base is not in the curated bank")
            elif trusted_base != curated_base:
                reasons.append("trusted base was modified from the curated bank")
            if curated_base is not None:
                reasons.extend(
                    self._compare_trusted_fields(
                        scenario, curated_base, require_difficulty=False
                    )
                )
                reasons.extend(
                    self._compare_generated_presentation(scenario, curated_base)
                )
        elif curated_scenario := self.bank.scenarios.get(scenario.id):
            reasons.extend(
                self._compare_trusted_fields(
                    scenario, curated_scenario, require_difficulty=True
                )
            )
            if scenario.presentation != curated_scenario.presentation:
                reasons.append("curated scenario presentation was modified")

        template = self.bank.templates.get(scenario.template_ref)
        if template is None:
            reasons.append("unknown template_ref")
        elif template["family"] != scenario.family.value:
            reasons.append("template family mismatch")

        approved_sources = {
            evidence.source
            for curated in self.bank.scenarios.values()
            if curated.template_ref == scenario.template_ref
            for evidence in curated.ground_truth.evidence
        }
        if approved_sources and any(
            evidence.source not in approved_sources
            for evidence in scenario.ground_truth.evidence
        ):
            reasons.append("evidence source is not approved for this template")

        truth = scenario.ground_truth
        if set(truth.tells) != set(truth.tell_keywords):
            reasons.append("every tell must have keyword evidence")
        if any(not keywords for keywords in truth.tell_keywords.values()):
            reasons.append("tell keyword groups cannot be empty")
        if any(
            not keyword.strip()
            for keywords in truth.tell_keywords.values()
            for keyword in keywords
        ):
            reasons.append("tell keywords cannot be blank")
        if len({evidence.id for evidence in truth.evidence}) != len(truth.evidence):
            reasons.append("evidence identifiers must be unique")
        if truth.correct_action == Action.SANDBOX and truth.safe_blast_radius is None:
            reasons.append("sandbox action has no safe policy")
        if truth.correct_action != Action.SANDBOX and truth.safe_blast_radius is not None:
            reasons.append("non-sandbox action defines a contradictory safe policy")
        if not truth.explanation.strip():
            reasons.append("missing explanation")

        combined_artifacts = "\n".join(
            artifact.content.lower() for artifact in scenario.presentation.artifacts
        )
        for tell, keywords in truth.tell_keywords.items():
            usable_keywords = [keyword for keyword in keywords if keyword.strip()]
            if not any(
                self._contains_keyword(combined_artifacts, keyword)
                for keyword in usable_keywords
            ):
                reasons.append(f"presented artifacts do not support declared tell: {tell}")

        return GateResult(
            passed=not reasons,
            reasons=reasons,
            scenario_id=scenario.id,
        )
