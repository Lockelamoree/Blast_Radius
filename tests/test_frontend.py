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
    assert "TRANSFER CHECK / ${total} NEW QUESTIONS" in app
    assert "SAME ${total} SIGNALS" not in app
    assert template.index('class="proof-strip"') < template.index('class="hero-actions"')


def test_caddy_security_policy_does_not_require_inline_code() -> None:
    root = Path(__file__).parents[1]
    caddy = (root / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "Strict-Transport-Security" in caddy
    assert "Content-Security-Policy" in caddy
    assert "script-src 'self'" in caddy
    assert "'unsafe-inline'" not in caddy
    assert "request_body" in caddy
    assert "max_size 128KB" in caddy
    assert "output stderr" in caddy
    assert "format json" in caddy


def test_accessibility_and_honest_live_mode_are_wired_without_overlays() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    assert template.count('aria-live="polite"') == 1
    assert 'id="app-status"' in template
    assert 'data-start="live" disabled' in template
    assert 'id="reset-decision"' in template
    assert "Time expired" in app
    assert "Decision controls remain available" in app
    assert "$$('.action').forEach(button=>button.disabled=true)" not in app
    assert "target.focus" in app
    assert "prompt.focus" in app
    assert "Question ${state.questionIndex+1} of ${total}" in app
    assert "if(state.testSubmitting)return" in app
    assert "const finalAnswers=[...state.answers,answer]" in app
    assert "state.testSubmitting=true;submitButton.disabled=true" in app
    assert "state.testSubmitting=false;submitButton.disabled=false" in app
    assert "health.live_generation" in app
    assert "health.live_generation_reason" in app
    assert "liveGenerationAvailable" in app
    assert "MODEL BUDGET EXHAUSTED" in app
    assert "grade.graded_by===grade.critic_model" in app
    assert "startsWith('gpt-5.6-sol')?'sol':'verified model'" in app
    assert ".split('-').pop()" not in app
    assert ":focus-visible" in css
    assert ".sr-only" in css
    assert 'id="round-provenance"' in template
    assert "AI-GENERATED VARIATION" in app
    assert "never sent to the reasoning critic" in app
    assert 'id="result-generated"' in template


def test_decision_controls_serialize_capabilities_and_expose_selected_state() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert 'id="capabilities"' in template
    assert "capabilities:csv($('#capabilities').value)" in app
    assert template.count('aria-pressed="false"') == 3
    assert 'aria-controls="sandbox-config"' in template
    assert 'aria-expanded="false"' in template
    assert "setAttribute('aria-pressed',String(selected))" in app
    assert "setAttribute('aria-expanded',String(sandboxSelected))" in app
    assert 'minlength="8"' in template
    assert 'aria-describedby="reason-requirement"' in template
    assert "minimum 8 characters" in template
    assert ".trim().replace(/\\s+/g,' ')" in app


def test_assessment_and_score_labels_are_accessible_and_honest() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    integrity = (root / "blast_radius" / "static" / "integrity-check.js").read_text(
        encoding="utf-8"
    )

    assert '<fieldset class="question-set">' in template
    assert '<legend id="test-prompt"' in template
    assert template.count("tell coverage") >= 2
    assert "reasoning score" not in template
    assert "tell coverage.`" in app
    assert "tell coverage`)" in app
    assert "BLOCKED BEFORE DISPLAY" in integrity
    assert "PLANTED HALLUCINATION" in integrity
    assert "FAILED INVARIANT" in integrity
    assert "case=${selectedCase}" in integrity
    assert "review.planted_claim" in integrity


def test_social_metadata_and_static_assets_are_cache_busted() -> None:
    template = (
        Path(__file__).parents[1] / "blast_radius" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert 'rel="icon" href="data:image/svg+xml' in template
    assert 'property="og:title"' in template
    assert 'name="twitter:card"' in template
    assert "/static/styles.css?v=" in template
    assert "/static/improvements.css?v=" in template
    assert "/static/app.js?v=" in template
    assert "/static/integrity-check.js?v=" in template
