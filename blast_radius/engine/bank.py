from __future__ import annotations

import json
import random
from pathlib import Path

from blast_radius.models import (
    AssessmentForm,
    Competency,
    Scenario,
    ScenarioFamily,
    TestQuestion,
)


class ScenarioBank:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.templates = {
            row["id"]: row for row in self._read_json(data_dir / "templates.json")
        }
        self.scenarios = {
            scenario.id: scenario
            for scenario in (
                Scenario.model_validate(row)
                for row in self._read_json(data_dir / "scenarios.json")
            )
        }
        self.questions = [
            TestQuestion.model_validate(row)
            for row in self._read_json(data_dir / "questions.json")
        ]
        question_ids = [question.id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question ids must be unique")
        for form in AssessmentForm:
            form_questions = self.questions_for(form)
            if len(form_questions) != len(Competency):
                raise ValueError(
                    f"{form.value} assessment must contain exactly one question per competency"
                )
            competencies = [question.competency for question in form_questions]
            if set(competencies) != set(Competency) or len(competencies) != len(
                set(competencies)
            ):
                raise ValueError(
                    f"{form.value} assessment must contain exactly one question per competency"
                )

    @staticmethod
    def _read_json(path: Path) -> list[dict]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            raise ValueError(f"{path.name} must contain a JSON list")
        return value

    def get(self, scenario_id: str) -> Scenario:
        return self.scenarios[scenario_id]

    def questions_for(self, form: AssessmentForm) -> list[TestQuestion]:
        rank = {competency: index for index, competency in enumerate(Competency)}
        return sorted(
            (question for question in self.questions if question.form == form),
            key=lambda question: rank[question.competency],
        )

    @property
    def assessment_size(self) -> int:
        return len(self.questions_for(AssessmentForm.PRE))

    def fallback(
        self,
        *,
        family: ScenarioFamily | None = None,
        exclude: set[str] | None = None,
        seed: str | None = None,
    ) -> Scenario:
        excluded = exclude or set()
        choices = [
            scenario
            for scenario in self.scenarios.values()
            if scenario.id not in excluded and (family is None or scenario.family == family)
        ]
        if not choices:
            choices = [scenario for scenario in self.scenarios.values() if scenario.id not in excluded]
        if not choices:
            raise LookupError("no fallback scenario remains")
        return random.Random(seed).choice(choices)

    def drill_pick(
        self,
        *,
        day: str,
        client_key: str,
        family: ScenarioFamily | None = None,
    ) -> Scenario:
        """Pick one verified scenario for a single-round daily drill.

        Seeded by (day, client_key, family) so the same browser gets a stable
        scenario within a day but a fresh one the next day; a family pin powers
        spaced-repetition callbacks. The client key is used only to seed this
        choice and is never persisted.
        """
        seed = f"drill:v1:{day}:{client_key}:{family.value if family else 'any'}"
        return self.fallback(family=family, seed=seed)

    def demo_order(self, seed: str | None = None) -> list[str]:
        canonical = [
            "cmd-cleanup-2",
            "dep-typo-1",
            "tool-scope-1",
            "diff-exfil-1",
            "context-injection-1",
            "market-egress-1",
        ]
        if seed is None:
            return canonical
        # Deck one verified scenario per family in the canonical family order,
        # picked deterministically from the seed so a session always replays the
        # same deck while different sessions explore the full curated pool.
        rng = random.Random(seed)
        deck: list[str] = []
        for canonical_id in canonical:
            family = self.scenarios[canonical_id].family
            members = sorted(
                scenario_id
                for scenario_id, scenario in self.scenarios.items()
                if scenario.family == family
            )
            deck.append(rng.choice(members))
        return deck
