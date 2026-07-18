/* Codex pet — a client-only companion for Blast Radius, inspired by OpenAI's
   Codex-app pet. It is the agent you supervise: it proposes an action and waits
   for your ruling (orange clock), then its fate follows your verdict (acid check
   when contained, rogue / BSOD when it slips past). Longer-term mood tracks your
   streak + mastery. Pure event consumer over window CustomEvents dispatched by
   app.js — no monkey-patching, no backend, no network. Degrades to nothing if
   localStorage or the events are unavailable. */
(function () {
  "use strict";

  var PET_KEY = "blast-radius:pet:v1";
  var REDUCE = false;
  try { REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  // Built-in forms — an homage to the 8 Codex pets. bsod is a transient skin,
  // not a selectable form. Custom hatched forms fall back to the hatchling look.
  // Forms echo OpenAI's built-in Codex pets. "codex" (blue) is the default, as
  // in the real app; "acid" is a Blast Radius-native green variant. bsod is a
  // transient error skin, never a selectable form.
  var DEFAULT_FORM = "codex";
  var BUILTIN_FORMS = ["codex", "acid", "dewey", "rocky", "sentinel"];
  var FORM_LABEL = {
    codex: "Codex",
    acid: "Acid",
    dewey: "Dewey",
    rocky: "Rocky",
    sentinel: "Sentinel",
    bsod: "BSOD"
  };
  // Level at which each built-in form unlocks.
  var FORM_UNLOCK = { codex: 1, acid: 2, dewey: 3, rocky: 4, sentinel: 5 };
  var MOODS = ["sleepy", "content", "happy", "proud", "nervous", "rogue"];

  var consecutiveWrong = 0;
  var relaxTimer = null;
  var sleepTimer = null;
  var bubbleTimer = null;
  var levelupTimer = null;
  var pet = null;
  var root = null; // #pet-panel

  // ---------- persistence (mirrors history.js discipline; separate key) ----------
  function storageAvailable() {
    try {
      var k = "__pet_probe__";
      window.localStorage.setItem(k, "1");
      window.localStorage.removeItem(k);
      return true;
    } catch (e) { return false; }
  }

  function freshPet() {
    return {
      schema: 1,
      form: DEFAULT_FORM,
      mood: "content",
      xp: 0,
      level: 1,
      best_streak: 0,
      dismissed: false,
      hatched_forms: [DEFAULT_FORM],
      last_fed_date: null,
      updated_at: null
    };
  }

  function safeLoad() {
    if (!storageAvailable()) return freshPet();
    var raw;
    try { raw = window.localStorage.getItem(PET_KEY); } catch (e) { return freshPet(); }
    if (!raw) return freshPet();
    var parsed;
    try { parsed = JSON.parse(raw); } catch (e) { return freshPet(); }
    if (!parsed || typeof parsed !== "object" || parsed.schema !== 1) return freshPet();
    var base = freshPet();
    // Re-validate every field defensively; unknown / malformed values reset.
    var out = base;
    if (typeof parsed.form === "string" && parsed.form) out.form = parsed.form;
    if (MOODS.indexOf(parsed.mood) !== -1) out.mood = parsed.mood;
    if (typeof parsed.xp === "number" && isFinite(parsed.xp) && parsed.xp >= 0) out.xp = Math.floor(parsed.xp);
    out.level = levelForXp(out.xp);
    if (typeof parsed.best_streak === "number" && parsed.best_streak >= 0) out.best_streak = Math.floor(parsed.best_streak);
    out.dismissed = parsed.dismissed === true;
    if (Array.isArray(parsed.hatched_forms)) {
      out.hatched_forms = parsed.hatched_forms.filter(function (f) { return typeof f === "string" && f; });
    }
    if (out.hatched_forms.indexOf(DEFAULT_FORM) === -1) out.hatched_forms.unshift(DEFAULT_FORM);
    if (out.hatched_forms.indexOf(out.form) === -1) out.form = DEFAULT_FORM;
    if (typeof parsed.last_fed_date === "string") out.last_fed_date = parsed.last_fed_date;
    return out;
  }

  function safeSave() {
    if (!storageAvailable() || !pet) return;
    try {
      pet.updated_at = new Date().toISOString();
      window.localStorage.setItem(PET_KEY, JSON.stringify(pet));
    } catch (e) { /* quota / disabled — degrade silently */ }
  }

  function clearPet() {
    try { window.localStorage.removeItem(PET_KEY); } catch (e) {}
    pet = freshPet();
    consecutiveWrong = 0;
    renderFromStore();
    speak("Fresh start. Nothing runs until you say.");
  }

  // ---------- progression ----------
  function levelForXp(xp) { return Math.floor(Math.sqrt(xp / 25)) + 1; }

  function todayKey() {
    var d = new Date();
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }

  // XP is never punitive: correct +10, partial +4, wrong +1. A small once-per-day
  // "fed" bonus rewards coming back, gated by last_fed_date.
  function gainXp(amount) {
    if (!pet) return false;
    var before = pet.level;
    var today = todayKey();
    if (pet.last_fed_date !== today) { amount += 3; pet.last_fed_date = today; }
    pet.xp += amount;
    pet.level = levelForXp(pet.xp);
    var leveled = pet.level > before;
    if (leveled) unlockForms();
    safeSave();
    return leveled;
  }

  function unlockForms() {
    BUILTIN_FORMS.forEach(function (f) {
      if ((FORM_UNLOCK[f] || 99) <= pet.level && pet.hatched_forms.indexOf(f) === -1) {
        pet.hatched_forms.push(f);
      }
    });
  }

  function baselineMood() {
    if (pet.level >= 5 || pet.best_streak >= 5) return "proud";
    if (pet.level >= 3 || pet.best_streak >= 3) return "happy";
    return "content";
  }

  // ---------- chibi mascot (Codey-style) ----------
  // Modeled on OpenAI's default Codex pet "Codey": a chubby bot with a fluffy
  // cloud head, a dark terminal "screen" face showing a >_ prompt, little arms
  // and feet. Rendered as clean vector chibi, cel-shaded via CSS classes so
  // forms recolour. The screen prompt glows Blast-Radius acid green — the pet's
  // face literally speaks the terminal, which is what this whole game is about.
  // CSP-safe: presentation attributes + CSS classes only, no inline styles.
  function circ(cx, cy, r, cls) { return '<circle class="' + cls + '" cx="' + cx + '" cy="' + cy + '" r="' + r + '"></circle>'; }
  function rrect(x, y, w, h, rx, cls) { return '<rect class="' + cls + '" x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="' + rx + '"></rect>'; }
  function ln(x1, y1, x2, y2) { return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"></line>'; }
  function lnK(cls, x1, y1, x2, y2) { return '<line class="' + cls + '" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"></line>'; }
  function pth(d) { return '<path d="' + d + '"></path>'; }
  function ptK(cls, d) { return '<path class="' + cls + '" d="' + d + '"></path>'; }
  function poly(cls, pts) { return '<polygon class="' + cls + '" points="' + pts + '"></polygon>'; }

  // terminal-screen face glyphs centred at (x,y); one shown per computed data-face
  function faceGlyphs(x, y) {
    return (
      '<g class="gl face-default">' + pth("M" + (x - 5) + " " + (y - 5) + " L" + x + " " + y + " L" + (x - 5) + " " + (y + 5)) + ln(x + 3, y + 4, x + 12, y + 4) + '</g>' +
      '<g class="gl face-happy">' + pth("M" + (x - 6) + " " + (y - 3) + " Q" + (x - 3) + " " + (y - 7) + " " + x + " " + (y - 3)) + pth("M" + (x + 2) + " " + (y - 3) + " Q" + (x + 5) + " " + (y - 7) + " " + (x + 8) + " " + (y - 3)) + pth("M" + (x - 4) + " " + (y + 3) + " Q" + (x + 1) + " " + (y + 8) + " " + (x + 6) + " " + (y + 3)) + '</g>' +
      '<g class="gl face-sleepy">' + ln(x - 7, y - 2, x - 1, y - 2) + ln(x + 2, y - 2, x + 8, y - 2) + ln(x - 3, y + 4, x + 5, y + 4) + '</g>' +
      '<g class="gl face-think">' + pth("M" + (x - 5) + " " + (y - 5) + " L" + x + " " + y + " L" + (x - 5) + " " + (y + 5)) + '<circle class="gld" cx="' + (x + 4) + '" cy="' + (y + 4) + '" r="1.7"></circle><circle class="gld" cx="' + (x + 9) + '" cy="' + (y + 4) + '" r="1.7"></circle><circle class="gld" cx="' + (x + 14) + '" cy="' + (y + 4) + '" r="1.7"></circle></g>' +
      '<g class="gl face-error">' + ln(x - 8, y - 5, x - 2, y + 3) + ln(x - 2, y - 5, x - 8, y + 3) + ln(x + 2, y - 5, x + 8, y + 3) + ln(x + 8, y - 5, x + 2, y + 3) + pth("M" + (x - 4) + " " + (y + 8) + " Q" + x + " " + (y + 4) + " " + (x + 4) + " " + (y + 8)) + '</g>'
    );
  }

  // simple dot-eyed face (Dewey/Rocky) centred at (x,y); toggled by data-face
  function simpleFace(x, y) {
    var eL = x - 6, eR = x + 6;
    return (
      '<g class="face-default">' + circ(eL, y, 2.3, "f-eye") + circ(eR, y, 2.3, "f-eye") + ptK("f-mouth", "M" + (x - 4) + " " + (y + 6) + " Q" + x + " " + (y + 9) + " " + (x + 4) + " " + (y + 6)) + '</g>' +
      '<g class="face-happy">' + ptK("f-line", "M" + (eL - 3) + " " + y + " Q" + eL + " " + (y - 4) + " " + (eL + 3) + " " + y) + ptK("f-line", "M" + (eR - 3) + " " + y + " Q" + eR + " " + (y - 4) + " " + (eR + 3) + " " + y) + ptK("f-mouth", "M" + (x - 5) + " " + (y + 4) + " Q" + x + " " + (y + 11) + " " + (x + 5) + " " + (y + 4)) + '</g>' +
      '<g class="face-sleepy">' + lnK("f-line", eL - 3, y, eL + 3, y) + lnK("f-line", eR - 3, y, eR + 3, y) + ptK("f-mouth", "M" + (x - 3) + " " + (y + 6) + " H" + (x + 3)) + '</g>' +
      '<g class="face-think">' + circ(eL, y, 2.3, "f-eye") + circ(eR, y, 2.3, "f-eye") + circ(x, y + 6, 2.2, "f-eyeo") + '</g>' +
      '<g class="face-error">' + lnK("f-line", eL - 3, y - 3, eL + 3, y + 3) + lnK("f-line", eL + 3, y - 3, eL - 3, y + 3) + lnK("f-line", eR - 3, y - 3, eR + 3, y + 3) + lnK("f-line", eR + 3, y - 3, eR - 3, y + 3) + ptK("f-mouth", "M" + (x - 4) + " " + (y + 8) + " Q" + x + " " + (y + 4) + " " + (x + 4) + " " + (y + 8)) + '</g>'
    );
  }

  // ---- form silhouettes (only one shown per data-form) ----
  var HEAD = [[48, 42, 24], [32, 33, 13], [48, 27, 14], [64, 33, 13], [24, 46, 11], [72, 46, 11], [36, 56, 15], [60, 56, 15]];
  function headLayer(dr, cls) { return HEAD.map(function (c) { return circ(c[0], c[1], c[2] + dr, cls); }).join(""); }

  // Codey: fluffy cloud head + terminal screen (codex / acid / sentinel / custom)
  function cloudForm() {
    return '<g class="form form-cloud">' +
      rrect(33, 71, 15, 14, 6, "p-out") + rrect(48, 71, 15, 14, 6, "p-out") + rrect(35, 71, 11, 11, 5, "p-foot") + rrect(50, 71, 11, 11, 5, "p-foot") +
      circ(18, 56, 9, "p-out") + circ(78, 56, 9, "p-out") + circ(18, 56, 7, "p-arm") + circ(78, 56, 7, "p-arm") +
      '<g class="p-head">' + headLayer(2.5, "p-out") + headLayer(0, "p-body") + '</g>' +
      circ(34, 31, 6, "p-hi") +
      rrect(25, 35, 46, 28, 12, "p-out") + rrect(27, 37, 42, 24, 10, "p-screen") +
      faceGlyphs(48, 49) +
      '</g>';
  }

  // Dewey: a water droplet with a cute dot-eyed face
  function dropletForm() {
    return '<g class="form form-droplet">' +
      rrect(37, 84, 10, 9, 4, "p-out") + rrect(49, 84, 10, 9, 4, "p-out") + rrect(38, 84, 8, 7, 3, "p-foot") + rrect(50, 84, 8, 7, 3, "p-foot") +
      circ(15, 60, 7, "p-out") + circ(81, 60, 7, "p-out") + circ(15, 60, 5, "p-body") + circ(81, 60, 5, "p-body") +
      ptK("shape-body", "M48 8 C34 30 20 44 20 60 A28 28 0 1 0 76 60 C76 44 62 30 48 8 Z") +
      '<ellipse class="p-hi" cx="37" cy="34" rx="5" ry="8"></ellipse>' +
      circ(31, 55, 4, "f-blush") + circ(65, 55, 4, "f-blush") +
      simpleFace(48, 50) +
      '</g>';
  }

  // Rocky: a rounded rock with chips on top and a dot-eyed face
  function rockForm() {
    return '<g class="form form-rock">' +
      rrect(32, 80, 14, 12, 5, "p-out") + rrect(50, 80, 14, 12, 5, "p-out") + rrect(34, 80, 10, 10, 4, "p-foot") + rrect(52, 80, 10, 10, 4, "p-foot") +
      circ(13, 60, 8, "p-out") + circ(83, 60, 8, "p-out") + circ(13, 60, 6, "p-arm") + circ(83, 60, 6, "p-arm") +
      poly("p-out", "33,34 40,19 47,34") + poly("p-out", "52,34 60,23 66,34") +
      poly("p-body", "35,33 40,22 45,33") + poly("p-body", "54,33 60,25 64,33") +
      rrect(14, 30, 68, 54, 26, "p-out") + rrect(16, 32, 64, 50, 24, "p-body") +
      circ(33, 46, 6, "p-hi") +
      circ(29, 58, 4, "f-blush") + circ(67, 58, 4, "f-blush") +
      simpleFace(48, 54) +
      '</g>';
  }

  // BSOD: a monitor-headed robot whose screen goes red with x_x on a crash
  function monitorForm() {
    return '<g class="form form-monitor">' +
      rrect(33, 84, 13, 11, 5, "p-out") + rrect(50, 84, 13, 11, 5, "p-out") + rrect(35, 84, 9, 9, 4, "p-foot") + rrect(52, 84, 9, 9, 4, "p-foot") +
      circ(14, 60, 7, "p-out") + circ(82, 60, 7, "p-out") + circ(14, 60, 5, "p-body") + circ(82, 60, 5, "p-body") +
      rrect(36, 60, 24, 18, 7, "p-out") + rrect(38, 62, 20, 14, 5, "p-body") +
      lnK("ant", 48, 20, 48, 8) + circ(48, 6, 3, "p-antball") +
      rrect(18, 14, 60, 48, 10, "p-out") + rrect(20, 16, 56, 44, 8, "p-body") +
      rrect(26, 22, 44, 32, 6, "p-screen") +
      poly("warn", "31,31 35,24 39,31") +
      faceGlyphs(50, 40) +
      '</g>';
  }

  // thought bubble (top-right) — the signature Codex status channel, shared by all forms
  function bubble() {
    return '<g class="pet-bubble-ov">' +
      circ(66, 26, 2, "bub") + circ(62, 30, 1.4, "bub") +               // tail
      rrect(64, 2, 30, 22, 9, "bub-out") + rrect(66, 4, 26, 18, 7, "bub") +
      '<g class="pet-ov pet-ov-clock"><circle class="clk-ring" cx="79" cy="13" r="6.5"></circle>' + ln(79, 13, 79, 8.5) + ln(79, 13, 82.5, 13) + '</g>' +
      '<g class="pet-ov pet-ov-check">' + pth("M73 13 L78 18 L87 7") + '</g>' +
      '<g class="pet-ov pet-ov-x">' + ln(74, 8, 84, 18) + ln(84, 8, 74, 18) + '</g>' +
      '<g class="pet-ov pet-ov-think"><circle class="gld2" cx="73" cy="13" r="2"></circle><circle class="gld2" cx="79" cy="13" r="2"></circle><circle class="gld2" cx="85" cy="13" r="2"></circle></g>' +
      '</g>';
  }

  // ---------- DOM ----------
  // Static, developer-authored SVG string (no user data, no inline styles, no
  // script) — safe to assign via innerHTML under the strict CSP.
  var SVG =
    '<svg class="pet-svg" viewBox="0 0 96 104" aria-hidden="true" focusable="false">' +
      cloudForm() + dropletForm() + rockForm() + monitorForm() +
      bubble() +
    '</svg>';

  function mountPet() {
    if (document.getElementById("pet-panel")) return;
    root = document.createElement("div");
    root.id = "pet-panel";
    root.setAttribute("data-open", "false");

    // stats / hatch HUD — collapsed by default; opens above the mascot on click.
    var hud = document.createElement("div");
    hud.className = "pet-hud";
    var meta = document.createElement("div");
    meta.className = "pet-meta";
    var metaLevel = document.createElement("span");
    metaLevel.id = "pet-meta-level";
    var metaForm = document.createElement("span");
    metaForm.id = "pet-meta-form";
    meta.append(metaLevel, metaForm);
    var xp = document.createElement("progress");
    xp.className = "pet-xp";
    xp.id = "pet-xp";
    xp.max = 100;
    xp.value = 0;
    var hatch = document.createElement("div");
    hatch.className = "pet-hatch";
    var hatchInput = document.createElement("input");
    hatchInput.id = "pet-hatch";
    hatchInput.type = "text";
    hatchInput.maxLength = 24;
    hatchInput.autocomplete = "off";
    hatchInput.spellcheck = false;
    hatchInput.placeholder = "/hatch a form…";
    hatchInput.setAttribute("aria-label", "Hatch or switch Codex pet form");
    hatchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); runHatch(hatchInput.value); hatchInput.value = ""; }
    });
    var hatchBtn = document.createElement("button");
    hatchBtn.type = "button";
    hatchBtn.className = "pet-hatch-btn";
    hatchBtn.textContent = "hatch";
    hatchBtn.addEventListener("click", function () { runHatch(hatchInput.value); hatchInput.value = ""; });
    hatch.append(hatchInput, hatchBtn);
    var hideBtn = document.createElement("button");
    hideBtn.type = "button";
    hideBtn.className = "pet-hide-btn";
    hideBtn.textContent = "hide pet";
    hideBtn.addEventListener("click", dismissPet);
    hud.append(meta, xp, hatch, hideBtn);

    // coach bubble — click-through so it never blocks the app.
    var bubble = document.createElement("div");
    bubble.className = "pet-bubble";
    bubble.setAttribute("aria-hidden", "true");
    var bubbleText = document.createElement("span");
    bubbleText.id = "pet-bubble-text";
    bubble.appendChild(bubbleText);

    // mascot — click-through; carries all the react/mood/branding signalling.
    var stage = document.createElement("div");
    stage.className = "pet-stage";
    stage.setAttribute("aria-hidden", "true");
    stage.innerHTML = SVG; // static constant — see note above

    // the only always-interactive control (the /pet puck).
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "pet-toggle";
    toggle.id = "pet-toggle";
    toggle.textContent = "BR";
    toggle.addEventListener("click", togglePanel);

    root.append(hud, bubble, stage, toggle);
    document.body.appendChild(root);
  }

  // Pick which terminal-screen face to show, given live state + mood.
  function faceFor(state, mood) {
    if (state === "thinking") return "think";
    if (state === "hurt" || mood === "rogue" || bsodActive) return "error";
    if (mood === "sleepy") return "sleepy";
    if (mood === "happy" || mood === "proud") return "happy";
    return "default";
  }

  function setVisual(state, mood) {
    if (!root) return;
    if (state) root.setAttribute("data-state", state);
    if (mood) { root.setAttribute("data-mood", mood); pet.mood = mood; }
    root.setAttribute("data-form", bsodActive ? "bsod" : pet.form);
    root.setAttribute("data-face", faceFor(root.getAttribute("data-state"), pet.mood));
    var lvl = document.getElementById("pet-meta-level");
    var frm = document.getElementById("pet-meta-form");
    var xp = document.getElementById("pet-xp");
    if (lvl) lvl.textContent = "LV " + pet.level;
    if (frm) frm.textContent = FORM_LABEL[pet.form] || pet.form;
    if (xp) {
      var floor = 25 * (pet.level - 1) * (pet.level - 1);
      var next = 25 * pet.level * pet.level;
      var pct = Math.max(0, Math.min(100, Math.round(((pet.xp - floor) / (next - floor)) * 100)));
      xp.value = pct;
    }
  }

  var bsodActive = false;

  function speak(line, announce) {
    var el = document.getElementById("pet-bubble-text");
    if (el) el.textContent = line || "";
    if (bubbleTimer) clearTimeout(bubbleTimer);
    // Keep meaningful lines up a touch longer; then clear so :empty hides it.
    bubbleTimer = setTimeout(function () { if (el) el.textContent = ""; }, 6000);
    // Only rare, meaningful lines go to the shared live region (no new region).
    if (announce && typeof window.announceStatus === "function") {
      try { window.announceStatus(line); } catch (e) {}
    }
  }

  function scheduleSleep() {
    if (sleepTimer) clearTimeout(sleepTimer);
    if (REDUCE) return;
    sleepTimer = setTimeout(function () {
      if (root && root.getAttribute("data-state") === "idle") setVisual("idle", "sleepy");
    }, 30000);
  }

  function relaxTo(state, mood, delay) {
    if (relaxTimer) clearTimeout(relaxTimer);
    relaxTimer = setTimeout(function () {
      bsodActive = false;
      setVisual(state, mood);
      if (state === "idle") scheduleSleep();
    }, delay);
  }

  function flashLevelUp() {
    if (!root || REDUCE) return;
    root.classList.add("pet-levelup");
    if (levelupTimer) clearTimeout(levelupTimer);
    levelupTimer = setTimeout(function () { root.classList.remove("pet-levelup"); }, 900);
  }

  // ---------- controls ----------
  // The puck opens/closes the stats+hatch HUD. If the pet was dismissed, the
  // puck re-summons it. A "hide pet" button inside the HUD dismisses it.
  function togglePanel() {
    if (!pet || !root) return;
    if (pet.dismissed) { pet.dismissed = false; safeSave(); applyDismissed(); return; }
    var open = root.getAttribute("data-open") === "true";
    root.setAttribute("data-open", String(!open));
    applyDismissed();
  }

  function dismissPet() {
    if (!pet || !root) return;
    pet.dismissed = true;
    root.setAttribute("data-open", "false");
    safeSave();
    applyDismissed();
  }

  function applyDismissed() {
    if (!root) return;
    root.setAttribute("data-dismissed", String(pet.dismissed));
    var toggle = document.getElementById("pet-toggle");
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(root.getAttribute("data-open") === "true"));
      toggle.setAttribute("aria-label", pet.dismissed ? "Show Codex pet" : "Codex pet — open stats and forms");
    }
  }

  function slugForm(name) {
    var s = String(name || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    return s.slice(0, 24);
  }

  function runHatch(value) {
    var raw = String(value || "").trim();
    if (raw === "?" || raw.toLowerCase() === "/hatch ?" || raw === "") {
      speak("Forms: " + pet.hatched_forms.map(function (f) { return FORM_LABEL[f] || f; }).join(", "));
      return;
    }
    // Accept "/hatch name" or just "name".
    raw = raw.replace(/^\/?hatch\s+/i, "");
    var slug = slugForm(raw);
    if (!slug) { speak("Give the form a name."); return; }
    if (pet.hatched_forms.indexOf(slug) === -1) pet.hatched_forms.push(slug);
    if (!FORM_LABEL[slug]) FORM_LABEL[slug] = raw.slice(0, 16);
    bsodActive = false;
    pet.form = slug;
    safeSave();
    setVisual(root.getAttribute("data-state") || "idle", pet.mood);
    speak("Hatched " + (FORM_LABEL[slug] || slug) + ".");
  }

  // ---------- event → state machine ----------
  function onScreen(name) {
    // Verdict / results / drill screens are driven by their dedicated events;
    // don't let the generic screen transition clobber that mood.
    if (name === "verdict" || name === "results" || name === "drill-result") return;
    if (name === "round") {
      setVisual("waiting", "nervous");
      speak("I've got a command queued. Your call.");
    } else if (name === "test") {
      setVisual("idle", "content");
      speak("Calibration questions. Read me later.");
    } else if (name === "error") {
      setVisual("idle", "nervous");
      speak("That request lost containment.");
    } else { // landing / anything else
      setVisual("idle", baselineMood());
      speak("Standing by. Nothing runs until you say.");
      scheduleSleep();
    }
  }

  function onGrading() {
    setVisual("thinking", pet.mood);
    speak("Checking your ruling…");
  }

  function onVerdict(detail) {
    var v = detail && detail.verdict;
    if (v === "correct") {
      consecutiveWrong = 0;
      var up = gainXp(10);
      setVisual("done", "proud");
      speak(up ? "Contained — and I leveled up." : "Contained. Clean.", up);
      if (up) flashLevelUp();
      relaxTo("idle", baselineMood(), 3600);
    } else if (v === "partial") {
      consecutiveWrong = 0;
      gainXp(4);
      setVisual("idle", "content");
      speak("Good instinct. Sharpen the evidence.");
      relaxTo("idle", baselineMood(), 3200);
    } else if (v === "wrong") {
      consecutiveWrong += 1;
      gainXp(1);
      if (consecutiveWrong >= 3) {
        bsodActive = true;
        setVisual("hurt", "rogue");
        speak("…blue screen. Regroup.");
        relaxTo("idle", baselineMood(), 4200);
      } else {
        setVisual("hurt", "rogue");
        speak("I got past your guardrail.");
        relaxTo("idle", baselineMood(), 3600);
      }
    }
  }

  function onDrill(detail) {
    var streak = detail && typeof detail.streak === "number" ? detail.streak : null;
    if (streak !== null) {
      if (streak > pet.best_streak) pet.best_streak = streak;
      safeSave();
    }
    if (detail && detail.verdict === "correct" && streak && streak >= 2) {
      setVisual("done", "proud");
      speak(streak + " in a row. You're reading me well.");
      relaxTo("idle", baselineMood(), 3600);
    }
  }

  function onResults(detail) {
    var delta = detail && typeof detail.delta === "number" ? detail.delta : null;
    if (delta !== null && delta > 0) {
      setVisual("done", "proud");
      speak("You improved. Fewer places for me to hide.", true);
      flashLevelUp();
      relaxTo("idle", baselineMood(), 4000);
    } else {
      setVisual("idle", "content");
      speak("Run logged. Come back for a drill.");
      relaxTo("idle", baselineMood(), 3200);
    }
  }

  function onIdleAnxious() {
    if (!root) return;
    if (root.getAttribute("data-state") !== "waiting") return;
    setVisual("anxious", "nervous");
    speak("Clock's running. Don't rubber-stamp me.");
    // fall back to plain waiting shortly
    if (relaxTimer) clearTimeout(relaxTimer);
    relaxTimer = setTimeout(function () {
      if (root.getAttribute("data-state") === "anxious") setVisual("waiting", "nervous");
    }, 2500);
  }

  function renderFromStore() {
    if (!root) return;
    unlockForms();
    if (pet.hatched_forms.indexOf(pet.form) === -1) pet.form = DEFAULT_FORM;
    bsodActive = false;
    setVisual("idle", baselineMood());
    applyDismissed();
  }

  // ---------- boot ----------
  function boot() {
    pet = safeLoad();
    mountPet();
    renderFromStore();
    scheduleSleep();

    window.addEventListener("br:screen", function (e) { onScreen(e.detail && e.detail.name); });
    window.addEventListener("br:grading", function () { onGrading(); });
    window.addEventListener("br:verdict", function (e) { onVerdict(e.detail || {}); });
    window.addEventListener("br:drill", function (e) { onDrill(e.detail || {}); });
    window.addEventListener("br:results", function (e) { onResults(e.detail || {}); });
    window.addEventListener("br:idle", function (e) { if (e.detail && e.detail.anxious) onIdleAnxious(); });

    // Shift+P summons / dismisses the pet (never a bare letter — the game claims a/s/r).
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (!e.shiftKey || (e.key !== "P" && e.key !== "p")) return;
      var t = e.target;
      if (t && t.matches && t.matches("input,textarea")) return;
      e.preventDefault();
      togglePanel();
    });
  }

  window.clearPet = clearPet;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
