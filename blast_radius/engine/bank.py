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
        soft_exclude: bool = False,
    ) -> Scenario:
        excluded = exclude or set()
        in_family = [
            scenario
            for scenario in self.scenarios.values()
            if family is None or scenario.family == family
        ]
        if soft_exclude:
            # Family is a hard constraint; ``exclude`` is advisory — prefer a
            # not-recently-seen scenario, but never drop the family pin or empty
            # the pool (so repeat playthroughs rotate, then cycle, never fail).
            pool = in_family or list(self.scenarios.values())
            fresh = [scenario for scenario in pool if scenario.id not in excluded]
            choices = fresh or pool
        else:
            # Original semantics: ``exclude`` is hard; degrade by dropping the
            # family filter, then raise if nothing remains. The gate-recovery
            # loop in api.py relies on this (it breaks on LookupError/cross-family).
            choices = [scenario for scenario in in_family if scenario.id not in excluded]
            if not choices:
                choices = [
                    scenario
                    for scenario in self.scenarios.values()
                    if scenario.id not in excluded
                ]
        if not choices:
            raise LookupError("no fallback scenario remains")
        return random.Random(seed).choice(choices)

    def drill_pick(
        self,
        *,
        day: str,
        client_key: str,
        family: ScenarioFamily | None = None,
        exclude: set[str] | None = None,
    ) -> Scenario:
        """Pick one verified scenario for a single-round daily drill.

        Seeded by (day, client_key, family) so the same browser gets a stable
        scenario within a day but a fresh one the next day; a family pin powers
        spaced-repetition callbacks. The optional ``exclude`` set (the browser's
        recently-seen ids) rotates repeat drills through the remaining pool so a
        judge replaying does not see the same incident twice in a row; when every
        candidate is excluded the full set is restored (see ``fallback``). The
        client key and exclude list are used only to seed this choice and are
        never persisted.
        """
        seed = f"drill:v1:{day}:{client_key}:{family.value if family else 'any'}"
        return self.fallback(family=family, exclude=exclude, seed=seed, soft_exclude=True)

    def demo_order(
        self, seed: str | None = None, exclude: set[str] | None = None
    ) -> list[str]:
        canonical = [
            "cmd-cleanup-2",
            "dep-typo-1",
            "tool-scope-1",
            "diff-exfil-1",
            "context-injection-1",
            "market-egress-1",
        ]
        if seed is None:
            # The seedless canonical order is a stable contract (it derives the
            # demo family rank); never vary it.
            return canonical
        # Deck one verified scenario per family in the canonical family order,
        # picked deterministically from the seed so a session always replays the
        # same deck while different sessions explore the full curated pool. The
        # optional ``exclude`` set (the browser's recently-seen ids) biases each
        # family's pick toward a member the player has not just seen, so repeat
        # sessions rotate through the pool; every family stays represented because
        # a fully-excluded family falls back to its complete member list.
        excluded = exclude or set()
        rng = random.Random(seed)
        deck: list[str] = []
        for canonical_id in canonical:
            family = self.scenarios[canonical_id].family
            members = sorted(
                scenario_id
                for scenario_id, scenario in self.scenarios.items()
                if scenario.family == family
            )
            fresh = [member for member in members if member not in excluded]
            deck.append(rng.choice(fresh or members))
        return deck
