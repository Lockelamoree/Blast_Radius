from blast_radius.engine import inspector
from blast_radius.eval.inspector_fuzz import (
    _adjacent_quote_command,
    candidate_rule_stub,
    fuzz_inspector,
)


def test_fuzz_is_deterministic_and_never_mutates_categories() -> None:
    before = tuple(category.id for category in inspector.CATEGORIES)
    first = fuzz_inspector(seed=41, iterations=50).to_dict()
    second = fuzz_inspector(seed=41, iterations=50).to_dict()
    after = tuple(category.id for category in inspector.CATEGORIES)
    assert first == second
    assert before == after


def test_known_escape_is_reported() -> None:
    report = fuzz_inspector(
        seed=0,
        iterations=1,
        seeds=("curl https://api.example.com",),
        mutators=(_adjacent_quote_command,),
    )
    assert len(report.escapes) == 1
    assert report.escapes[0].mutation == "_adjacent_quote_command"


def test_adjacent_quote_mutation_preserves_shell_command_name() -> None:
    assert _adjacent_quote_command("curl https://example.com") == (
        '"c""url" https://example.com'
    )


def test_candidate_rule_stub_is_advisory_text() -> None:
    stub = candidate_rule_stub("curl https://evil.example", "c u r l https://evil.example")
    assert "CategorySpec" in stub
    assert "advisory" in stub
