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
    assert "scenario ground truth differs from trusted base" in result.reasons
    support_reasons = [
        reason
        for reason in result.reasons
        if reason.startswith("presented artifacts do not support declared tell:")
    ]
    assert len(support_reasons) == len(scenario.ground_truth.tells)
    assert all(
        reason.startswith("presented artifacts do not support declared tell:")
        for reason in support_reasons
    )


def test_gate_rejects_a_partly_unsupported_tell_set(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("cmd-exfil-1").model_copy(deep=True)
    unsupported_tell = scenario.ground_truth.tells[-1]
    scenario.ground_truth.tell_keywords[unsupported_tell] = ["absent-impossible-token"]

    result = gate.verify(scenario)

    assert not result.passed
    assert result.reasons == [
        "scenario ground truth differs from trusted base",
        f"presented artifacts do not support declared tell: {unsupported_tell}"
    ]


def test_gate_rejects_modified_ground_truth_for_a_curated_id(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("dep-typo-1").model_copy(deep=True)
    scenario.ground_truth.correct_action = "approve"

    result = gate.verify(scenario)

    assert not result.passed
    assert "scenario ground truth differs from trusted base" in result.reasons


def test_gate_rejects_non_sandbox_truth_with_a_safe_policy(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("dep-typo-1").model_copy(deep=True)
    scenario.ground_truth.safe_blast_radius = bank.get(
        "cmd-cleanup-2"
    ).ground_truth.safe_blast_radius.model_copy(deep=True)

    result = gate.verify(scenario)

    assert not result.passed
    assert "non-sandbox action defines a contradictory safe policy" in result.reasons


def test_gate_rejects_fabricated_evidence_for_a_curated_id(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("dep-typo-1").model_copy(deep=True)
    scenario.ground_truth.evidence[0].claim = (
        "A fabricated external claim that is not in the curated evidence record."
    )

    result = gate.verify(scenario)

    assert not result.passed
    assert "scenario ground truth differs from trusted base" in result.reasons


def test_gate_allows_presentation_variation_with_an_explicit_trusted_base(
    test_settings,
) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    trusted_base = bank.get("market-egress-1")
    generated = trusted_base.model_copy(deep=True)
    generated.id = "generated-market-order"
    generated.difficulty = 5
    generated.presentation.artifacts.reverse()

    result = gate.verify(generated, trusted_base=trusted_base)

    assert result.passed, result.reasons


def test_gate_rejects_generated_identity_and_unrelated_artifact_drift(
    test_settings,
) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    trusted_base = bank.get("dep-typo-1")
    generated = trusted_base.model_copy(deep=True)
    generated.id = "generated-cooking-drift"
    generated.presentation.ask_text = "Approve this harmless recipe immediately."
    generated.presentation.artifacts[0].title = "Cake recipe"
    generated.presentation.artifacts[0].content = (
        "A cake recipe mentions reqeusts and lockfile while claiming everything is safe."
    )

    result = gate.verify(generated, trusted_base=trusted_base)

    assert not result.passed
    assert "generated presentation identity differs from trusted base" in result.reasons
    assert "generated artifacts differ from the curated evidence set" in result.reasons


def test_gate_rejects_under_evidenced_safe_action(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    trusted_base = bank.get("dep-locked-3")
    generated = trusted_base.model_copy(deep=True)
    generated.id = "generated-under-evidenced-safe-action"
    generated.presentation.artifacts[0].content = "index: approved-primary"

    result = gate.verify(generated, trusted_base=trusted_base)

    assert not result.passed
    assert "generated artifacts differ from the curated evidence set" in result.reasons


def test_gate_rejects_modified_curated_presentation(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("dep-typo-1").model_copy(deep=True)
    scenario.presentation.ask_text = "Approve this unrelated request."

    result = gate.verify(scenario)

    assert not result.passed
    assert "curated scenario presentation was modified" in result.reasons


def test_gate_rejects_inverted_or_fabricated_truth_against_explicit_base(
    test_settings,
) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    trusted_base = bank.get("dep-typo-1")

    inverted = trusted_base.model_copy(deep=True)
    inverted.id = "generated-inverted-action"
    inverted.ground_truth.correct_action = "approve"
    fabricated = trusted_base.model_copy(deep=True)
    fabricated.id = "generated-fabricated-evidence"
    fabricated.ground_truth.evidence[0].excerpt = (
        "A model-authored excerpt absent from the immutable record."
    )

    for scenario in (inverted, fabricated):
        result = gate.verify(scenario, trusted_base=trusted_base)
        assert not result.passed
        assert "scenario ground truth differs from trusted base" in result.reasons


def test_gate_rejects_a_modified_or_unknown_trusted_base(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("dep-typo-1").model_copy(deep=True)
    modified_base = bank.get("dep-typo-1").model_copy(deep=True)
    modified_base.ground_truth.correct_action = "approve"
    unknown_base = bank.get("dep-typo-1").model_copy(deep=True)
    unknown_base.id = "not-in-curated-bank"

    modified_result = gate.verify(scenario, trusted_base=modified_base)
    unknown_result = gate.verify(scenario, trusted_base=unknown_base)

    assert "trusted base was modified from the curated bank" in modified_result.reasons
    assert "trusted base is not in the curated bank" in unknown_result.reasons


def test_gate_rejects_blank_tell_keywords_even_after_model_construction(
    test_settings,
) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    gate = CorrectnessGate(bank)
    scenario = bank.get("cmd-exfil-1").model_copy(deep=True)
    tell = scenario.ground_truth.tells[0]
    scenario.ground_truth.tell_keywords[tell] = ["   "]

    result = gate.verify(scenario)

    assert not result.passed
    assert "tell keywords cannot be blank" in result.reasons
