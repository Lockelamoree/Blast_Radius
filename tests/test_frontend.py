import json
import re
from pathlib import Path

from blast_radius.models import BlastRadiusConfig, ScenarioFamily


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
    # The self-catch reads as a trust win, not an error: blocked, plainly why,
    # and closing on the payoff that the same gate runs on everything shown.
    assert "BLOCKED BEFORE DISPLAY" in integrity
    assert "you never saw the fake" in integrity
    assert "you can trust what you do see" in integrity
    assert "case=${selectedCase}" in integrity
    assert "review.planted_claim" in integrity
    # Three numbered beats make the plant visible: real scenario, injected lie,
    # then the deterministic (no-AI) catch. Lock the full labels, not fragments.
    assert "1 · THE REAL SCENARIO YOU WOULD SEE" in integrity
    assert "2 · WE PLANTED THIS LIE" in integrity
    assert "3 · HOW THE GATE CAUGHT IT · NO AI" in integrity
    assert "reqeusts==2.32.0" in integrity


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
    assert app.count("apiRetry(`/api/sessions/") == 5
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
    assert "classList.toggle('bad',data.delta<=-3)" in app
    assert "strong.bad" in css
    # The Chromium-dropped grouped progress rule stays split.
    assert "progress.mastery-track::-webkit-progress-value {" in css
    assert "progress.mastery-track::-moz-progress-bar {" in css
    assert "::-webkit-progress-value,\nprogress.mastery-track::-moz-progress-bar" not in css
    # Grading wait is announced and visually prominent; ghost buttons show disabled.
    assert 'id="grading-status" class="microcopy hidden" aria-live="polite"' in template
    assert "#grading-status::before" in css
    assert ".button:disabled" in css
    # Self-catch result: the raw gate log is surfaced verbatim as a receipt, and
    # the panel cycles to the next plant.
    assert "review.reasons.join(' · ')" in integrity
    assert "gate log ·" in integrity
    assert "next plant" in integrity
    # Beat styling: the lie beat is danger-orange, the gate beat is acid, and the
    # verdict carries the trust-payoff sub-line.
    assert ".gate-beat.step-lie" in css
    assert ".gate-beat.step-gate" in css
    assert ".gate-verdict-sub" in css
    # Static assets share one current cache-bust version.
    versions = set(re.findall(r"\?v=([\w-]+)", template))
    assert len(versions) == 1, f"static cache-bust versions diverged: {versions}"
    assert len(re.findall(r"\?v=", template)) == 9
    # The first assessment question is announced (screen active before render).
    assert app.count("show('test');renderQuestion();") == 2
    assert "renderQuestion();show('test');" not in app
    # Explicit smooth scroll respects the reduced-motion preference.
    assert "matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'" in app
    # The share button reverts so a second copy gives feedback.
    assert "setTimeout(()=>{event.target.textContent='Copy result';},2000)" in app


def test_codex_pet_is_wired_and_client_only() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    pet = (root / "blast_radius" / "static" / "pet.js").read_text(encoding="utf-8")
    pet_css = (root / "blast_radius" / "static" / "pet.css").read_text(encoding="utf-8")
    history = (root / "blast_radius" / "static" / "history.js").read_text(encoding="utf-8")

    # Both pet assets ship, cache-busted, sharing the single version string.
    assert "/static/pet.css?v=" in template
    assert "/static/pet.js?v=" in template
    versions = set(re.findall(r"\?v=([\w-]+)", template))
    assert len(versions) == 1, f"static cache-bust versions diverged: {versions}"

    # The pet must not add a third live region or a fourth aria-pressed control
    # (those exact counts are pinned by other tests); it lives on document.body,
    # not in the template, and is decorative.
    assert "pet-panel" not in template
    assert template.count('aria-live="polite"') == 2
    assert template.count('aria-pressed="false"') == 3

    # app.js dispatches decoupled CustomEvents the pet consumes; it never names a
    # pet symbol beyond the fire-and-forget helper.
    assert "petEmit" in app
    assert 'new CustomEvent("br:"+t' in app
    assert "petEmit('screen',{name})" in app
    assert "petEmit('grading',{})" in app
    assert "petEmit('verdict'," in app
    assert "petEmit('drill'," in app
    assert "petEmit('results'," in app

    # The pet is a pure event consumer: listens to the bus, no network, its own
    # localStorage key, and never touches the history blob.
    assert 'window.addEventListener("br:verdict"' in pet
    assert 'window.addEventListener("br:screen"' in pet
    assert "blast-radius:pet:v1" in pet
    assert "blast-radius:v1" not in pet
    assert "fetch(" not in pet
    # The only innerHTML assignment is the static, developer-authored SVG scaffold.
    assert pet.count(".innerHTML =") == 1
    assert "stage.innerHTML = SVG" in pet
    assert "window.clearPet" in pet
    assert "prefers-reduced-motion" in pet

    # Clearing local progress also resets the pet.
    assert "if (window.clearPet) window.clearPet();" in history

    # Styling exists and honours reduced motion.
    assert "#pet-panel" in pet_css
    assert "prefers-reduced-motion" in pet_css


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


def test_socratic_coach_reflection_is_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    assert 'id="reflect-block"' in template
    assert 'id="reflect-input"' in template
    assert "ASK THE COACH" in template
    assert "rounds/reflect`" in app
    # Bank-only: generated rounds never expose a reflection.
    assert "state.scenario.id.startsWith('live-')" in app
    assert ".reflect-reply" in css


def test_sandbox_policy_debrief_table_is_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    assert 'id="policy-compare"' in template
    assert "Compare your sandbox" in template
    assert 'id="policy-rows"' in template
    assert "grade.policy_deltas" in app
    assert "delta.status==='excess'?'LEAK'" in app
    assert ".policy-row.excess" in css


def test_sandbox_honesty_note_is_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")

    # When the player sandboxed a scenario that has no policy to grade, say so
    # instead of showing a bare "—".
    assert 'id="sandbox-note"' in template
    assert "Sandbox config noted" in app
    assert "state.selectedAction==='sandbox'&&grade.blast_radius_score===null" in app


def test_guardrail_export_is_wired_and_covers_every_family() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    guardrails = (root / "blast_radius" / "static" / "guardrails.js").read_text(
        encoding="utf-8"
    )
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    # Export controls live on the results screen and the script is loaded.
    assert 'id="copy-guardrails"' in template
    assert 'id="download-guardrails"' in template
    assert "/static/guardrails.js?v=" in template
    assert ".guardrail-export" in css
    # The static map covers all six families using the real BlastRadiusConfig fields.
    for family in ScenarioFamily:
        assert family.value in guardrails
    for field in BlastRadiusConfig.model_fields:
        assert field in guardrails
    # Deterministic and honest: reads the finished session, cites https receipts,
    # states it makes no model calls, and never issues a network request.
    assert "state.results" in guardrails
    assert "buildGuardrailDoc" in guardrails
    assert "https://" in guardrails
    assert "no model calls" in guardrails
    assert "fetch(" not in guardrails
    # The AGENTS.md snippet builder rides alongside, still deterministic.
    assert "buildAgentsSnippet" in guardrails
    assert "agents_md" in guardrails
    assert 'id="copy-agents-snippet"' in template


def test_landing_proof_card_cites_the_committed_receipt() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )
    evidence = sorted((root / "evidence").glob("live_grade_*.json"))
    assert evidence, "the committed live-grade receipt must exist"
    receipt = json.loads(evidence[0].read_text(encoding="utf-8"))
    response_id = receipt["critic_proof"]["response_id"]

    # The witnessed grade is folded into the integrity block as its payoff.
    assert 'class="integrity-proof"' in template
    assert ".integrity-proof" in css
    assert 'class="integrity-check"' in template
    # Still static but honest: it names the real graded scenario, the real
    # response id, and links to the committed receipt file — no runtime fetch.
    assert receipt["scenario"]["id"] in template
    assert response_id in template
    assert "evidence/" + evidence[0].name in template


def test_landing_grading_pill_and_revision_are_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    assert 'id="grading-pill"' in template
    assert 'id="grading-pill-label"' in template
    # The verified-bank chip stays as a second pill next to the grading state.
    assert template.count("status-pill") >= 2
    assert "verified scenario bank" in template
    assert 'id="footer-rev"' in template
    assert "GPT-5.6 GRADING LIVE · SOL" in app
    assert "DETERMINISTIC GRADING" in app
    assert "updateGradingPill" in app
    assert "health.revision" in app
    assert "#grading-pill.live" in css


def test_adaptive_focus_line_is_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    assert 'id="adaptive-focus"' in template
    assert "data.adaptive_focus" in app
    assert "targeting your weakest area" in app
    assert ".adaptive-focus" in css


def test_finish_early_link_and_partial_results_are_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    # A quiet round-screen link finishes early; it only appears from round 2 on.
    assert 'id="finish-early"' in template
    assert "see what you've shown so far" in template
    assert "finish-early`,{method:'POST'}" in app
    assert "data.round_number<2" in app
    # Early finish is honest: no fabricated delta, post score, or per-competency post.
    assert "data.finished_early" in app
    assert "post-test skipped — delta not measured" in app
    assert "value.post_score===null" in app
    assert ".linklike" in css


def test_results_recap_and_fresh_deck_cta_are_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    app = (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    # Per-round recap and weakest-area focus render above the competency map.
    assert 'id="round-recap"' in template
    assert 'id="recap-focus"' in template
    assert "data.rounds" in app
    assert "data.weakest_competency" in app
    assert "round.action_correct" in app
    assert "round.reasoning_score" in app
    assert ".recap-row" in css
    # The replay CTA is honest now that each session decks a fresh scenario mix.
    assert "Run it again — fresh deck →" in template


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
    assert "/static/guardrails.js?v=" in template
    assert "/static/resources.js?v=" in template


def test_learn_and_protect_sections_are_wired() -> None:
    root = Path(__file__).parents[1]
    template = (root / "blast_radius" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    resources = (root / "blast_radius" / "static" / "resources.js").read_text(
        encoding="utf-8"
    )
    css = (root / "blast_radius" / "static" / "improvements.css").read_text(
        encoding="utf-8"
    )

    # Landing entry points and both screens exist.
    assert 'data-open="learn"' in template
    assert 'data-open="protect"' in template
    assert 'data-open="landing"' in template
    assert 'id="screen-learn"' in template
    assert 'id="screen-protect"' in template
    assert 'id="learn-modules"' in template
    assert 'id="toolkit-cards"' in template

    # The controller reuses the app.js globals and hits the read-only endpoints.
    assert "/api/learn" in resources
    assert "/api/toolkit" in resources
    assert "renderLearn" in resources
    assert "renderToolkit" in resources
    assert "escapeFamily" in resources
    assert "noopener noreferrer" in resources

    # Styling exists for the new components.
    assert ".resource-card" in css
    assert ".resource-nav" in css
    assert ".gate-verdict" in css


def _frontend_sources():
    root = Path(__file__).parents[1]
    return {
        "root": root,
        "template": (root / "blast_radius" / "templates" / "index.html").read_text(encoding="utf-8"),
        "app": (root / "blast_radius" / "static" / "app.js").read_text(encoding="utf-8"),
        "css": (root / "blast_radius" / "static" / "improvements.css").read_text(encoding="utf-8"),
    }


def test_keyboard_completion_shortcuts_are_wired() -> None:
    src = _frontend_sources()
    assert "event.key==='Enter'" in src["app"]
    assert "$('#submit-decision').click()" in src["app"]
    assert "closest('textarea,input,button,a,summary" in src["app"]
    assert "state.verdictShownAt" in src["app"]
    assert "Ctrl/⌘" in src["template"]
    assert 'class="microcopy key-hint"' in src["template"]
    assert "minimum 8 characters" in src["template"]  # existing pin survives


def test_critic_eligibility_preview_is_merged_into_provenance() -> None:
    src = _frontend_sources()
    assert "eligible for GPT-5.6 Sol review" in src["app"]
    assert "never sent to the critic (by design)" in src["app"]
    assert "criticEligible" in src["app"]


def test_finish_early_requires_two_step_confirmation() -> None:
    src = _frontend_sources()
    assert "your delta will show as" in src["app"]
    assert "Click again" in src["app"]
    assert "disarmFinishEarly" in src["app"]
    assert ".linklike.armed" in src["css"]
    assert "see what you've shown so far" in src["template"]  # existing template pin
    assert "`/api/sessions/${state.sessionId}/finish-early`" in src["app"]


def test_retry_status_is_visible_without_a_third_live_region() -> None:
    src = _frontend_sources()
    assert 'id="retry-note" class="retry-note hidden" aria-hidden="true"' in src["template"]
    assert src["template"].count('aria-live="polite"') == 2
    assert "retrying (attempt" in src["app"]
    assert ".retry-note" in src["css"]


def test_critic_catch_callout_is_distinct_from_the_tell_chip() -> None:
    src = _frontend_sources()
    assert 'id="critic-callout"' in src["template"]
    assert "A second reviewer caught what keyword matching missed:" in src["template"]
    assert 'id="critic-callout-tells"' in src["template"]
    assert ".critic-callout" in src["css"]
    assert "CAUGHT BY GPT-5.6" in src["app"]  # the chip stays


def test_operator_handle_input_is_optional_and_honest() -> None:
    src = _frontend_sources()
    assert 'id="operator-handle"' in src["template"]
    assert "leave blank to stay anonymous" in src["template"]
    assert "operator_handle" in src["app"]
    assert src["template"].index('class="proof-strip"') < src["template"].index('class="hero-actions"')
    # An invalid optional handle is caught client-side, not bounced to the error
    # screen — the app validates before starting a session.
    assert "HANDLE_RE" in src["app"]


def test_daily_drill_flow_is_wired() -> None:
    src = _frontend_sources()
    assert 'id="start-drill"' in src["template"]
    assert "90-second daily drill" in src["template"]
    assert 'id="screen-drill-result"' in src["template"]
    assert "mode:'drill'" in src["app"]
    assert "client_key" in src["app"]
    assert "window.startDrill" in src["app"]
    # Drill start must not route through the pretest screen (pinned count == 2).
    assert src["app"].count("show('test');renderQuestion();") == 2


def test_history_is_browser_local_and_clearable() -> None:
    root = Path(__file__).parents[1]
    history = (root / "blast_radius" / "static" / "history.js").read_text(encoding="utf-8")
    template = (root / "blast_radius" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "blast-radius:v1" in history
    assert "crypto.randomUUID" in history
    assert "localStorage" in history
    assert "due_date" in history
    assert "fetch(" not in history
    assert "innerHTML" not in history
    assert "/static/history.js?v=" in template
    assert 'id="history-panel"' in template
    assert "stored only in this browser" in template
    assert 'id="history-clear"' in template
    assert 'id="callback-start"' in template


def test_revise_retry_is_wired() -> None:
    src = _frontend_sources()
    assert 'id="revise-block"' in src["template"]
    assert 'id="revise-compare"' in src["template"]
    assert "rounds/retry" in src["app"]
    assert "re-check is deterministic" in src["template"]
    assert "round.retried" in src["app"]  # recap shows the coached-nudge chip
    assert "NAMED AFTER COACHING" in src["app"]
    assert ".nudge-chip" in src["css"]
    # The before/after comparison is deterministic-vs-deterministic, not against
    # a possibly critic-boosted initial score.
    assert "initial_deterministic_score" in src["app"]
    assert "retry_baseline_score" in src["app"]


def test_team_and_author_pages_use_external_assets_only() -> None:
    root = Path(__file__).parents[1]
    team = (root / "blast_radius" / "templates" / "team.html").read_text(encoding="utf-8")
    author = (root / "blast_radius" / "templates" / "author.html").read_text(encoding="utf-8")
    for page in (team, author):
        assert "onclick=" not in page
        assert "<style" not in page
        assert "<script>" not in page
    assert "/static/team.js?v=" in team and "/static/team.css?v=" in team
    assert "/static/author.js?v=" in author and "/static/author.css?v=" in author
    # The embedded starter skeleton validates as a real Scenario.
    author_js = (root / "blast_radius" / "static" / "author.js").read_text(encoding="utf-8")
    match = re.search(r"SCENARIO_SKELETON\s*=\s*'(\{.*?\})';/\*end-skeleton\*/", author_js, re.S)
    assert match, "author.js must embed a grep-able SCENARIO_SKELETON"
    from blast_radius.models import Scenario

    Scenario.model_validate(json.loads(match.group(1)))


def test_round_one_primer_is_wired() -> None:
    src = _frontend_sources()
    assert 'id="round-primer"' in src["template"]
    assert "data.round_number===1" in src["app"]
    assert "name the evidence (the tell)" in src["app"]
    assert ".round-primer" in src["css"]


def test_live_generation_is_surfaced_on_the_landing() -> None:
    src = _frontend_sources()
    # A GPT-5.6 badge on the live button + an invitational note when available.
    assert 'class="badge-new">GPT-5.6' in src["template"]
    assert 'data-start="live" disabled' in src["template"]  # existing pin survives
    assert "GPT-5.6 can reskin a verified scenario live" in src["app"]
    assert ".badge-new" in src["css"]


def test_landing_groups_secondary_calls_to_action() -> None:
    src = _frontend_sources()
    assert 'class="secondary-actions"' in src["template"]
    assert "More ways to play" in src["template"]
    assert ".secondary-actions" in src["css"]
    # The primary CTA stays first; proof strip still precedes the actions.
    assert src["template"].index('data-start="demo"') < src["template"].index('class="secondary-actions"')


def test_oversight_bias_block_is_wired_and_delta_is_demoted() -> None:
    src = _frontend_sources()
    assert 'id="oversight-bias"' in src["template"]
    assert 'id="bias-over-approval"' in src["template"]
    assert 'id="bias-over-restriction"' in src["template"]
    assert "data.oversight_bias" in src["app"]
    assert "bias.dominant==='over_approval'" in src["app"]
    assert ".oversight-bias" in src["css"]
    # The delta is demoted to a secondary stat and no longer the hero, and its
    # caveat marks it as a small-sample calibration.
    assert 'class="delta-block secondary-stat"' in src["template"]
    assert "read as directional" in src["template"]
    assert ".delta-block.secondary-stat strong" in src["css"]
    # Stable coverage stats now lead the delta on the results card.
    assert src["template"].index('class="result-stats"') < src["template"].index('class="delta-block secondary-stat"')
