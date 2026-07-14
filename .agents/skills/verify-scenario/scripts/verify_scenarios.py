from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT))

from blast_radius.engine.bank import ScenarioBank  # noqa: E402
from blast_radius.engine.gate import CorrectnessGate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Blast Radius production gate.")
    parser.add_argument("--scenario", help="Verify one curated scenario ID.")
    arguments = parser.parse_args()

    bank = ScenarioBank(REPOSITORY_ROOT / "blast_radius" / "data")
    gate = CorrectnessGate(bank)
    scenarios = (
        [bank.get(arguments.scenario)]
        if arguments.scenario
        else list(bank.scenarios.values())
    )

    failures: list[tuple[str, list[str]]] = []
    for scenario in scenarios:
        result = gate.verify(scenario)
        if not result.passed:
            failures.append((scenario.id, result.reasons))

    if failures:
        for scenario_id, reasons in failures:
            print(f"FAIL {scenario_id}: {'; '.join(reasons)}")
        return 1

    print(f"PASS {len(scenarios)} scenario(s) through CorrectnessGate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
