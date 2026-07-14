from __future__ import annotations

import json
import random
from pathlib import Path

from blast_radius.models import Scenario, ScenarioFamily, TestQuestion


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

    @staticmethod
    def _read_json(path: Path) -> list[dict]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            raise ValueError(f"{path.name} must contain a JSON list")
        return value

    def get(self, scenario_id: str) -> Scenario:
        return self.scenarios[scenario_id]

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

    def demo_order(self) -> list[str]:
        return [
            "cmd-cleanup-2",
            "dep-typo-1",
            "tool-scope-1",
            "diff-exfil-1",
            "context-injection-1",
            "market-egress-1",
        ]

