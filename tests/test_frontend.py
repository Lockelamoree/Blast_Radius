import re
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

    assert template.count('aria-live="polite"') == 2
    assert 'id="app-status"' in template
    assert 'id="grading-status" class="microcopy hidden" aria-live="polite"' in template
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
    assert "tell coverage, ${$('#tells-named').textContent} tells.`" in app
    assert "tell coverage`)" in app
    assert "BLOCKED BEFORE DISPLAY" in integrity
    assert "PLANTED HALLUCINATION" in integrity
    assert "FAILED INVARIANT" in integrity
    assert "case=${selectedCase}" in integrity
    assert "review.planted_claim" in integrity


def test_judge_path_hotfixes_lock_grading_and_render_honest_states() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )
    integrity = (root / "blast_radius" / "static" / "integrity-check.js").read_text(
        encoding="utf-8"
    )

    # In-flight grading locks every decision input, not just the submit button.
    assert "state.grading=true" in app
    assert "state.grading=false" in app
    assert app.count("if(state.grading)return;") >= 2
    assert "state.grading||!(state.selectedAction" in app
    # Browser/system shortcuts must never flip a decision.
    assert "event.ctrlKey||event.metaKey||event.altKey" in app
    # A hung request must reject instead of freezing the run.
    assert "AbortSignal.timeout(" in app
    # Transient failures retry with backoff; 409s resync instead of erroring.
    assert "async function apiRetry" in app
    assert "error.status=response.status" in app
    assert app.count("apiRetry(`/api/sessions/") == 4
    assert app.count("error.status===409") >= 2
    assert "already recorded — continuing" in app
    # Multi-second round fetches show a busy state; reserved budget is labeled.
    assert "Generating a fresh variation…" in app
    assert "reserved for grading" in app
    # Structured 422 details must never render as [object Object].
    assert "typeof body.detail==='string'" in app
    # Failure states carry the .bad modifier instead of success-green.
    assert "classList.toggle('bad',!grade.action_correct)" in app
    assert "classList.toggle('bad',grade.reasoning_score<50)" in app
    assert "classList.toggle('bad',data.delta<0)" in app
    assert "strong.bad" in css
    # The Chromium-dropped grouped progress rule stays split.
    assert "progress.mastery-track::-webkit-progress-value {" in css
    assert "progress.mastery-track::-moz-progress-bar {" in css
    assert "::-webkit-progress-value,\nprogress.mastery-track::-moz-progress-bar" not in css
    # Grading wait is announced and visually prominent; ghost buttons show disabled.
    assert 'id="grading-status" class="microcopy hidden" aria-live="polite"' in template
    assert "#grading-status::before" in css
    assert ".button:disabled" in css
    # Self-catch result: claim named once, invariant on its own line, cycle hint.
    assert "review.reasons.join(' · ').replace(`: ${review.planted_claim}`, '')" in integrity
    assert "next plant" in integrity
    # Static assets share one current cache-bust version.
    versions = set(re.findall(r"\?v=([\w-]+)", template))
    assert len(versions) == 1, f"static cache-bust versions diverged: {versions}"
    assert len(re.findall(r"\?v=", template)) == 4
    # The first assessment question is announced (screen active before render).
    assert app.count("show('test');renderQuestion();") == 2
    assert "renderQuestion();show('test');" not in app
    # Explicit smooth scroll respects the reduced-motion preference.
    assert "matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'" in app
    # The share button reverts so a second copy gives feedback.
    assert "setTimeout(()=>{event.target.textContent='Copy result';},2000)" in app


def test_verdict_receipt_renders_provenance_tells_and_divergence() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    # Provenance strip: only for a real critic response id, never the sentinel.
    assert 'id="verdict-provenance"' in template
    assert "respId!=='unavailable'" in app
    assert "grade.critic_effort" in app
    assert "grade.critic_latency_ms" in app
    assert "click to copy" in app
    # Tell checklist with echoed reasoning and honest marks.
    assert 'id="verdict-debrief"' in template
    assert 'id="tell-list"' in template
    assert 'id="tells-named"' in template
    assert "state.lastReasoning" in app
    assert "grade.missed_tells.forEach" in app
    # Divergence chip fires only for critic-only matches.
    assert "CAUGHT BY GPT-5.6" in app
    assert "criticSet.has(tell)&&!detSet.has(tell)" in app
    # Non-budget degraded grades are labeled honestly.
    assert "CRITIC UNAVAILABLE" in app
    # Styling exists for the new elements.
    assert ".verdict-provenance" in css
    assert ".tell-chip" in css


def test_social_metadata_and_static_assets_are_cache_busted() -> None:
    template = (
        Path(__file__).parents[1] / "blast_radius" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert 'rel="icon" href="data:image/svg+xml' in template
    assert 'property="og:title"' in template
    assert 'name="twitter:card"' in template
    assert 'property="og:image"' in template
    assert '<meta name="theme-color" content="#090a09">' in template
    assert "/static/styles.css?v=" in template
    assert "/static/improvements.css?v=" in template
    assert "/static/app.js?v=" in template
    assert "/static/integrity-check.js?v=" in template
