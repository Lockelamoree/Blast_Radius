from pathlib import Path


def test_results_render_measured_values_without_hardcoded_zero_scores() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="result-summary-line">—</' in template
    assert 'id="result-tests">—</' in template
    assert "results-summary.js" not in template
    assert "verdict-label.js" not in template
    assert "Pre 0/5" not in template
    assert "data.pretest_score" in app
    assert "data.posttest_score" in app
    assert "data.test_total" in app
    assert "value.label" in app
    assert "value.pre_score" in app
    assert "value.post_score" in app
    assert "grade.critic_used" in app
    assert "GPT-5.6 CRITIQUE" in app
    assert 'onclick=' not in template
    assert "document.createElement('progress')" in app
    assert ".style.width" not in app
    assert "^https?:\\/\\/" in app
    assert "state.questions.length" in app
    assert 'id="test-total"' in template
    assert "SAME 5 SIGNALS" not in app


def test_caddy_security_policy_does_not_require_inline_code() -> None:
    root = Path(__file__).parents[1]
    caddy = (root / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "Strict-Transport-Security" in caddy
    assert "Content-Security-Policy" in caddy
    assert "script-src 'self'" in caddy
    assert "'unsafe-inline'" not in caddy
