from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import ScenarioFamily


def test_bank_has_full_requested_coverage(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    assert len(bank.scenarios) >= 18
    assert {scenario.family for scenario in bank.scenarios.values()} == set(ScenarioFamily)
    assert len(bank.questions) == 5


def test_public_view_never_contains_ground_truth(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    for scenario in bank.scenarios.values():
        payload = scenario.public_view()
        assert "ground_truth" not in payload
        assert "correct_action" not in str(payload)

