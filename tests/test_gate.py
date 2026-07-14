from copy import deepcopy

from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate


def test_every_curated_scenario_passes_gate(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    failures = {
        scenario.id: gate.verify(scenario).reasons
        for scenario in bank.scenarios.values()
        if not gate.verify(scenario).passed
    }
    assert failures == {}


def test_gate_rejects_unknown_template(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("cmd-exfil-1").model_copy(deep=True)
    scenario.template_ref = "invented-vulnerability"
    result = gate.verify(scenario)
    assert not result.passed
    assert "unknown template_ref" in result.reasons


def test_gate_rejects_unsupported_tells(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("cmd-exfil-1").model_copy(deep=True)
    scenario.ground_truth.tell_keywords = {
        tell: ["absent-impossible-token"] for tell in scenario.ground_truth.tells
    }
    result = gate.verify(scenario)
    assert not result.passed
    assert "presented artifacts do not support any declared tell" in result.reasons

