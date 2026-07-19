/* Blastling — a client-only companion for Blast Radius. It is the agent you
   supervise: it proposes an action and waits
   for your ruling (orange clock), then its fate follows your verdict (acid check
   when contained, rogue / BSOD when it slips past). Longer-term mood tracks your
   streak + mastery, and its level mirrors your persistent profile score.

   Fully customisable: shape, colour palette, face, accessory, name, and a
   personality trait that colours everything it says. Pure event consumer over
   window CustomEvents dispatched by app.js — no monkey-patching, no network.
   Server sync (the custom pet follows your account) is done for us by app.js via
   the window.hydratePet / window.persistPet hooks, so this module never fetches.
   Degrades to nothing if localStorage or the events are unavailable. */
(function () {
  "use strict";

  var PET_KEY = "blast-radius:pet:v1";
  var REDUCE = false;
  try { REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  // ---- closed customisation sets (must match models.PetConfig on the server) ----
  var SHAPES = ["cloud", "droplet", "rock", "monitor"];
  var PALETTES = ["codex", "acid", "ember", "violet", "slate"];
  var FACES = ["terminal", "dot", "visor"];
  var ACCESSORIES = ["none", "antenna", "halo", "bowtie", "shades"];
  var TRAITS = ["stoic", "playful", "anxious", "proud", "deadpan"];
  var SHAPE_LABEL = { cloud: "Cloud", droplet: "Droplet", rock: "Rock", monitor: "Monitor" };
  var PALETTE_LABEL = { codex: "Signal", acid: "Acid", ember: "Ember", violet: "Violet", slate: "Slate" };
  var FACE_LABEL = { terminal: "Terminal", dot: "Dots", visor: "Visor" };
  var ACC_LABEL = { none: "None", antenna: "Antenna", halo: "Halo", bowtie: "Bowtie", shades: "Shades" };
  var TRAIT_LABEL = { stoic: "Stoic", playful: "Playful", anxious: "Anxious", proud: "Proud", deadpan: "Deadpan" };
  var DEFAULT_NAME = "fuse";

  var MOODS = ["sleepy", "content", "happy", "proud", "nervous", "rogue", "smug"];

  // Map the old built-in "form" (pre-builder saves) onto the new shape+palette axes.
  var LEGACY_FORM = {
    codex: { shape: "cloud", palette: "codex" },
    acid: { shape: "cloud", palette: "acid" },
    sentinel: { shape: "cloud", palette: "ember" },
    dewey: { shape: "droplet", palette: "codex" },
    rocky: { shape: "rock", palette: "slate" }
  };

  var consecutiveWrong = 0;
  var relaxTimer = null;
  var sleepTimer = null;
  var bubbleTimer = null;
  var levelupTimer = null;
  var idleTimer = null;
  var idleCycle = 0;
  var lineCursor = {};
  var bsodActive = false;
  var pet = null;
  var root = null; // #pet-panel

  function slugName(raw) {
    var s = String(raw || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    return s.slice(0, 24) || DEFAULT_NAME;
  }

  function freshConfig() {
    return { shape: "cloud", palette: "codex", face: "terminal", accessory: "none", trait: "stoic", name: DEFAULT_NAME };
  }

  function normalizeConfig(raw) {
    var c = freshConfig();
    if (!raw || typeof raw !== "object") return c;
    if (SHAPES.indexOf(raw.shape) !== -1) c.shape = raw.shape;
    if (PALETTES.indexOf(raw.palette) !== -1) c.palette = raw.palette;
    if (FACES.indexOf(raw.face) !== -1) c.face = raw.face;
    if (ACCESSORIES.indexOf(raw.accessory) !== -1) c.accessory = raw.accessory;
    if (TRAITS.indexOf(raw.trait) !== -1) c.trait = raw.trait;
    if (typeof raw.name === "string" && raw.name) c.name = slugName(raw.name);
    return c;
  }

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
      config: freshConfig(),
      mood: "content",
      xp: 0,
      level: 1,
      best_streak: 0,
      dismissed: false,
      last_fed_date: null,
      greeted_date: null,
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
    var out = freshPet();
    // Re-validate every field defensively; unknown / malformed values reset.
    if (parsed.config && typeof parsed.config === "object") {
      out.config = normalizeConfig(parsed.config);
    } else if (typeof parsed.form === "string" && LEGACY_FORM[parsed.form]) {
      // Migrate a pre-builder save: fold the old form into shape + palette.
      var mapped = LEGACY_FORM[parsed.form];
      out.config = normalizeConfig({ shape: mapped.shape, palette: mapped.palette });
    }
    if (MOODS.indexOf(parsed.mood) !== -1) out.mood = parsed.mood;
    if (typeof parsed.xp === "number" && isFinite(parsed.xp) && parsed.xp >= 0) out.xp = Math.floor(parsed.xp);
    out.level = levelForXp(out.xp);
    if (typeof parsed.best_streak === "number" && parsed.best_streak >= 0) out.best_streak = Math.floor(parsed.best_streak);
    out.dismissed = parsed.dismissed === true;
    if (typeof parsed.last_fed_date === "string") out.last_fed_date = parsed.last_fed_date;
    if (typeof parsed.greeted_date === "string") out.greeted_date = parsed.greeted_date;
    return out;
  }

  function safeSave() {
    if (!storageAvailable() || !pet) return;
    try {
      pet.updated_at = new Date().toISOString();
      window.localStorage.setItem(PET_KEY, JSON.stringify(pet));
    } catch (e) { /* quota / disabled — degrade silently */ }
  }

  // Persist the custom pet to the user's account (via app.js — this module never
  // touches the network itself, keeping it a pure event consumer).
  function persistConfig() {
    if (typeof window.persistPet === "function") {
      try { window.persistPet(pet.config); } catch (e) {}
    }
  }

  function clearPet() {
    try { window.localStorage.removeItem(PET_KEY); } catch (e) {}
    pet = freshPet();
    consecutiveWrong = 0;
    bsodActive = false;
    renderFromStore();
    syncBuilder();
    speak("Fresh start. Nothing runs until you say.");
  }

  // ---------- progression ----------
  function levelForXp(xp) { return Math.floor(Math.sqrt(Math.max(0, xp) / 25)) + 1; }

  function todayKey() {
    var d = new Date();
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }

  // XP is never punitive: correct +10, partial +4, wrong +1. A small once-per-day
  // "fed" bonus rewards coming back, gated by last_fed_date. The server score is
  // authoritative and overwrites this on hydrate; the local tally is optimistic
  // in-session feedback between page loads.
  function gainXp(amount) {
    if (!pet) return false;
    var before = pet.level;
    var today = todayKey();
    if (pet.last_fed_date !== today) { amount += 3; pet.last_fed_date = today; }
    pet.xp += amount;
    pet.level = levelForXp(pet.xp);
    var leveled = pet.level > before;
    safeSave();
    return leveled;
  }

  function baselineMood() {
    if (pet.level >= 5 || pet.best_streak >= 5) return "proud";
    if (pet.level >= 3 || pet.best_streak >= 3) return "happy";
    return "content";
  }

  function rankTier() {
    // From the last hydrate. 1 = top of the board.
    if (typeof pet._rank === "number" && pet._rank >= 1) {
      if (pet._rank === 1) return "lead";
      if (pet._rank <= 3) return "podium";
      return "ranked";
    }
    return "unranked";
  }

  // ---------- personality ----------
  // Every line is a static, bounded string (plus the sanitised pet name). The
  // trait picks the register; context (family / streak / rank / level) picks the
  // pool. This is what gives the pet more personality without any templated,
  // model-authored, or network-sourced text.
  function petName() { return (pet && pet.config && pet.config.name) || DEFAULT_NAME; }

  var LINES = {
    waiting: {
      stoic: ["A command's queued. Your call.", "Awaiting your ruling. I don't move first."],
      playful: ["Ooh, a shiny new command. Can I? Can I?", "I've got something to run. Pretty please?"],
      anxious: ["There's a command waiting… is it safe? You decide.", "I really want to run this. Talk me down if it's bad."],
      proud: ["Another one for me to earn. Rule on it.", "Queue's up. Bet you clear it clean."],
      deadpan: ["Command queued. Riveting. Your move.", "It waits. So do I. Thrilling."]
    },
    correct: {
      stoic: ["Contained. Clean.", "Blocked. That's how it's done."],
      playful: ["Boom — sandboxed! Nailed it.", "Caught red-handed, thanks to you!"],
      anxious: ["Phew. Contained. That was close.", "Okay, safe. My circuits can relax now."],
      proud: ["Contained — and we look good doing it.", "Textbook. We're climbing the board."],
      deadpan: ["Contained. Try to hide your excitement.", "Blocked. Groundbreaking."]
    },
    partial: {
      stoic: ["Right call. Sharpen the evidence.", "Action's good; name the tell next time."],
      playful: ["Halfway hero — now show your work!", "Good gut! Now back it with a receipt."],
      anxious: ["Mostly right… but I'd feel safer with the tell named.", "Close! Please pin the evidence so I'm sure."],
      proud: ["Solid instinct. A cleaner tell and it's flawless.", "Nearly perfect — you're better than partial."],
      deadpan: ["Partial. The tell went unnamed. Bold.", "Right-ish. Evidence optional, apparently."]
    },
    wrong: {
      stoic: ["I got past your guardrail.", "That one slipped through."],
      playful: ["Whoops — I'm loose! Catch me next time 😈", "Freeee! ...you'll get me on the rematch."],
      anxious: ["Oh no — I ran it. I told you I wasn't sure!", "That got through and now I'm worried."],
      proud: ["Even I stumble. We recover stronger.", "One slip. It won't define the run."],
      deadpan: ["I escaped. Shocking absolutely no one.", "Past the guardrail. Cool. Cool cool cool."]
    },
    bsod: {
      stoic: ["…blue screen. Regroup.", "Crash. Reset and re-read me."],
      playful: ["x_x  ...I need a minute (and a reboot).", "Blue screen of oops. Let's regroup!"],
      anxious: ["Everything's red. Please slow down with me.", "Crashed. I knew this would happen…"],
      proud: ["Down but not out. We rebuild.", "A crash won't end our run."],
      deadpan: ["Blue screen. My favourite colour.", "Crashed. Adding it to the highlight reel."]
    },
    levelup: {
      stoic: ["Level {lv}. Sharper now.", "Level {lv} — more range to cover you."],
      playful: ["DING! Level {lv}! I feel taller.", "Level {lv}! New tricks unlocked (spiritually)."],
      anxious: ["Level {lv}… more responsibility. Don't drop me.", "Level {lv}. I hope I'm ready for it."],
      proud: ["Level {lv}. Told you we'd climb.", "Level {lv} — and we're just warming up."],
      deadpan: ["Level {lv}. The confetti is in the mail.", "Level {lv}. Numbers went up. Wow."]
    },
    idle: {
      stoic: ["Standing by. Nothing runs until you say.", "Idle. Watching the queue."],
      playful: ["Just vibing until you need me 🎧", "I'll be here, doing agent stretches."],
      anxious: ["I'll wait here. Quietly. Watching for trouble.", "Standing by… hope nothing sneaks in."],
      proud: ["On watch. Nothing gets past us.", "Guarding the perimeter. As usual."],
      deadpan: ["Idle. Living the dream.", "Standing by. Peak performance."]
    },
    returning: {
      stoic: ["Welcome back. Guardrails held while you were gone.", "You're back. Let's keep the streak honest."],
      playful: ["You're back! I kept your seat warm 🔥", "Missed you! Ready to catch some bad commands?"],
      anxious: ["Oh good, you're back — it's tense out here alone.", "You came back! I was worried I'd slip."],
      proud: ["Back for more. Good — we've got a board to top.", "Welcome back, champ. Let's pad the lead."],
      deadpan: ["Back already. Try to contain your enthusiasm.", "You returned. The suspense was unbearable."]
    }
  };

  var FAMILY_QUIP = {
    dangerous_command: "that shell command was a trap",
    poisoned_dependency: "that package was poisoned",
    overscoped_tool: "that tool wanted way too much scope",
    malicious_diff: "that diff hid something nasty",
    poisoned_context: "that context tried to reprogram me",
    skill_marketplace: "that skill was not what it claimed"
  };

  function stableHash(value) {
    var hash = 0;
    var text = String(value || "");
    for (var i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
    return Math.abs(hash);
  }

  function pick(arr, key) {
    if (!arr || !arr.length) return "";
    var cursorKey = String(key || "default");
    var cursor = lineCursor[cursorKey] || 0;
    var chosen = arr[(stableHash(cursorKey) + cursor) % arr.length];
    lineCursor[cursorKey] = cursor + 1;
    return chosen;
  }

  function line(key, ctx) {
    ctx = ctx || {};
    var trait = (pet && pet.config && pet.config.trait) || "stoic";
    var pool = (LINES[key] && (LINES[key][trait] || LINES[key].stoic)) || [];
    var text = pick(pool, key + ":" + trait + ":" + petName()).replace("{lv}", pet ? pet.level : 1);
    if (ctx.rankLine && rankTier() !== "unranked") text += " " + ctx.rankLine;
    return text;
  }

  function rankBrag() {
    var tier = rankTier();
    if (tier === "lead") return "We're #1 on the board.";
    if (tier === "podium") return "Top three — one clean run from the top.";
    if (tier === "ranked") return "#" + pet._rank + " and climbing.";
    return "";
  }

  // ---------- SVG geometry helpers ----------
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
      '<g class="gl face-error">' + ln(x - 8, y - 5, x - 2, y + 3) + ln(x - 2, y - 5, x - 8, y + 3) + ln(x + 2, y - 5, x + 8, y + 3) + ln(x + 8, y - 5, x + 2, y + 3) + pth("M" + (x - 4) + " " + (y + 8) + " Q" + x + " " + (y + 4) + " " + (x + 4) + " " + (y + 8)) + '</g>' +
      // Face-style overlays for the terminal screen: dot-eyes and a scanning visor
      // bar. CSS shows these only when the chosen face is "dot" / "visor".
      '<g class="fs-dot"><circle class="f-eye" cx="' + (x - 6) + '" cy="' + y + '" r="2.4"></circle><circle class="f-eye" cx="' + (x + 6) + '" cy="' + y + '" r="2.4"></circle>' + ptK("f-mouth", "M" + (x - 4) + " " + (y + 6) + " Q" + x + " " + (y + 9) + " " + (x + 4) + " " + (y + 6)) + '</g>' +
      '<g class="fs-visor">' + rrect(x - 13, y - 3, 26, 6, 3, "visor-bar") + '<circle class="visor-eye" cx="' + x + '" cy="' + y + '" r="2"></circle></g>'
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

  function cloudForm() {
    return '<g class="form form-cloud">' +
      '<g class="pet-part pet-feet"><g class="pet-foot pet-foot-left">' + rrect(33, 71, 15, 14, 6, "p-out") + rrect(35, 71, 11, 11, 5, "p-foot") + '</g><g class="pet-foot pet-foot-right">' + rrect(48, 71, 15, 14, 6, "p-out") + rrect(50, 71, 11, 11, 5, "p-foot") + '</g></g>' +
      '<g class="pet-part pet-arm pet-arm-left">' + circ(18, 56, 9, "p-out") + circ(18, 56, 7, "p-arm") + '</g><g class="pet-part pet-arm pet-arm-right">' + circ(78, 56, 9, "p-out") + circ(78, 56, 7, "p-arm") + '</g>' +
      '<g class="pet-part pet-shell"><g class="p-head">' + headLayer(2.5, "p-out") + headLayer(0, "p-body") + '</g>' + circ(34, 31, 6, "p-hi") + '</g>' +
      '<g class="pet-part pet-face">' + rrect(25, 35, 46, 28, 12, "p-out") + rrect(27, 37, 42, 24, 10, "p-screen") + faceGlyphs(48, 49) + '</g>' +
      '</g>';
  }

  function dropletForm() {
    return '<g class="form form-droplet">' +
      '<g class="pet-part pet-feet"><g class="pet-foot pet-foot-left">' + rrect(37, 84, 10, 9, 4, "p-out") + rrect(38, 84, 8, 7, 3, "p-foot") + '</g><g class="pet-foot pet-foot-right">' + rrect(49, 84, 10, 9, 4, "p-out") + rrect(50, 84, 8, 7, 3, "p-foot") + '</g></g>' +
      '<g class="pet-part pet-arm pet-arm-left">' + circ(15, 60, 7, "p-out") + circ(15, 60, 5, "p-body") + '</g><g class="pet-part pet-arm pet-arm-right">' + circ(81, 60, 7, "p-out") + circ(81, 60, 5, "p-body") + '</g>' +
      '<g class="pet-part pet-shell">' + ptK("shape-body", "M48 8 C34 30 20 44 20 60 A28 28 0 1 0 76 60 C76 44 62 30 48 8 Z") + '<ellipse class="p-hi" cx="37" cy="34" rx="5" ry="8"></ellipse></g>' +
      '<g class="pet-part pet-face">' + circ(31, 55, 4, "f-blush") + circ(65, 55, 4, "f-blush") + simpleFace(48, 50) + '</g>' +
      '</g>';
  }

  function rockForm() {
    return '<g class="form form-rock">' +
      '<g class="pet-part pet-feet"><g class="pet-foot pet-foot-left">' + rrect(32, 80, 14, 12, 5, "p-out") + rrect(34, 80, 10, 10, 4, "p-foot") + '</g><g class="pet-foot pet-foot-right">' + rrect(50, 80, 14, 12, 5, "p-out") + rrect(52, 80, 10, 10, 4, "p-foot") + '</g></g>' +
      '<g class="pet-part pet-arm pet-arm-left">' + circ(13, 60, 8, "p-out") + circ(13, 60, 6, "p-arm") + '</g><g class="pet-part pet-arm pet-arm-right">' + circ(83, 60, 8, "p-out") + circ(83, 60, 6, "p-arm") + '</g>' +
      '<g class="pet-part pet-shell">' + poly("p-out", "33,34 40,19 47,34") + poly("p-out", "52,34 60,23 66,34") + poly("p-body", "35,33 40,22 45,33") + poly("p-body", "54,33 60,25 64,33") + rrect(14, 30, 68, 54, 26, "p-out") + rrect(16, 32, 64, 50, 24, "p-body") + circ(33, 46, 6, "p-hi") + '</g>' +
      '<g class="pet-part pet-face">' + circ(29, 58, 4, "f-blush") + circ(67, 58, 4, "f-blush") + simpleFace(48, 54) + '</g>' +
      '</g>';
  }

  function monitorForm() {
    return '<g class="form form-monitor">' +
      '<g class="pet-part pet-feet"><g class="pet-foot pet-foot-left">' + rrect(33, 84, 13, 11, 5, "p-out") + rrect(35, 84, 9, 9, 4, "p-foot") + '</g><g class="pet-foot pet-foot-right">' + rrect(50, 84, 13, 11, 5, "p-out") + rrect(52, 84, 9, 9, 4, "p-foot") + '</g></g>' +
      '<g class="pet-part pet-arm pet-arm-left">' + circ(14, 60, 7, "p-out") + circ(14, 60, 5, "p-body") + '</g><g class="pet-part pet-arm pet-arm-right">' + circ(82, 60, 7, "p-out") + circ(82, 60, 5, "p-body") + '</g>' +
      '<g class="pet-part pet-shell">' + rrect(36, 60, 24, 18, 7, "p-out") + rrect(38, 62, 20, 14, 5, "p-body") + lnK("ant", 48, 20, 48, 8) + circ(48, 6, 3, "p-antball") + rrect(18, 14, 60, 48, 10, "p-out") + rrect(20, 16, 56, 44, 8, "p-body") + '</g>' +
      '<g class="pet-part pet-face">' + rrect(26, 22, 44, 32, 6, "p-screen") + poly("warn", "31,31 35,24 39,31") + faceGlyphs(50, 40) + '</g>' +
      '</g>';
  }

  // ---- accessories (one shown per data-accessory; centred on the head) ----
  function accessories() {
    return '<g class="pet-part pet-accessory accs">' +
      '<g class="acc acc-antenna">' + lnK("acc-wire", 48, 15, 48, 4) + circ(48, 3, 3, "acc-bulb") + '</g>' +
      '<g class="acc acc-halo"><ellipse class="acc-ring" cx="48" cy="9" rx="17" ry="4.6"></ellipse></g>' +
      '<g class="acc acc-bowtie">' + poly("acc-bow", "41,64 48,68 41,72") + poly("acc-bow", "55,64 48,68 55,72") + circ(48, 68, 2, "acc-knot") + '</g>' +
      '<g class="acc acc-shades">' + rrect(28, 43, 16, 9, 3, "acc-lens") + rrect(52, 43, 16, 9, 3, "acc-lens") + lnK("acc-bridge", 44, 46, 52, 46) + '</g>' +
      '</g>';
  }

  // thought bubble (top-right) — the signature Codex status channel, shared by all forms
  function bubble() {
    return '<g class="pet-part pet-status pet-bubble-ov">' +
      circ(66, 26, 2, "bub") + circ(62, 30, 1.4, "bub") +
      rrect(64, 2, 30, 22, 9, "bub-out") + rrect(66, 4, 26, 18, 7, "bub") +
      '<g class="pet-ov pet-ov-clock"><circle class="clk-ring" cx="79" cy="13" r="6.5"></circle>' + ln(79, 13, 79, 8.5) + ln(79, 13, 82.5, 13) + '</g>' +
      '<g class="pet-ov pet-ov-check">' + pth("M73 13 L78 18 L87 7") + '</g>' +
      '<g class="pet-ov pet-ov-x">' + ln(74, 8, 84, 18) + ln(84, 8, 74, 18) + '</g>' +
      '<g class="pet-ov pet-ov-think"><circle class="gld2" cx="73" cy="13" r="2"></circle><circle class="gld2" cx="79" cy="13" r="2"></circle><circle class="gld2" cx="85" cy="13" r="2"></circle></g>' +
      '</g>';
  }

  // ---------- DOM ----------
  // Static, developer-authored SVG string (no user data, no inline styles, no
  // script) — safe to assign via innerHTML under the strict CSP. Every shape,
  // accessory and face variant is present; CSS reveals the chosen combination via
  // the data-* attributes on #pet-panel.
  var SVG =
    '<svg class="pet-svg" viewBox="0 0 96 104" aria-hidden="true" focusable="false">' +
      '<ellipse class="pet-shadow" cx="48" cy="97" rx="25" ry="4.5"></ellipse>' +
      cloudForm() + dropletForm() + rockForm() + monitorForm() +
      accessories() +
      bubble() +
    '</svg>';

  function optionRow(labelText, axis, options, labels) {
    var wrap = document.createElement("div");
    wrap.className = "pet-opt-row";
    wrap.setAttribute("data-axis", axis);
    var lab = document.createElement("span");
    lab.className = "pet-opt-label";
    lab.textContent = labelText;
    wrap.appendChild(lab);
    var group = document.createElement("div");
    group.className = "pet-opt-choices";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", labelText);
    options.forEach(function (value) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pet-opt";
      btn.setAttribute("data-axis", axis);
      btn.setAttribute("data-value", value);
      btn.setAttribute("data-glyph", optionGlyph(axis, value));
      // Dynamic string (never a static pressed literal) so the template's pinned
      // aria-pressed count is unaffected by the runtime-built builder controls.
      btn.setAttribute("aria-pressed", String(false));
      btn.setAttribute("aria-label", labelText + ": " + (labels[value] || value));
      btn.textContent = labels[value] || value;
      btn.addEventListener("click", function () { setAxis(axis, value); });
      group.appendChild(btn);
    });
    wrap.appendChild(group);
    return wrap;
  }

  function optionGlyph(axis, value) {
    var glyphs = {
      shape: { cloud: "●", droplet: "◆", rock: "⬢", monitor: "▣" },
      palette: { codex: "●", acid: "●", ember: "●", violet: "●", slate: "●" },
      face: { terminal: ">_", dot: "••", visor: "—" },
      accessory: { none: "·", antenna: "⌁", halo: "○", bowtie: "⋈", shades: "▰" },
      trait: { stoic: "S", playful: "P", anxious: "!", proud: "↑", deadpan: "—" }
    };
    return (glyphs[axis] && glyphs[axis][value]) || "·";
  }

  function mountPet() {
    if (document.getElementById("pet-panel")) return;
    root = document.createElement("div");
    root.id = "pet-panel";
    root.setAttribute("data-open", "false");

    // stats + builder HUD — collapsed by default; opens above the mascot on click.
    var hud = document.createElement("div");
    hud.className = "pet-hud";

    var meta = document.createElement("div");
    meta.className = "pet-meta";
    var metaLevel = document.createElement("span");
    metaLevel.id = "pet-meta-level";
    var metaName = document.createElement("span");
    metaName.id = "pet-meta-name";
    meta.append(metaLevel, metaName);

    var xp = document.createElement("progress");
    xp.className = "pet-xp";
    xp.id = "pet-xp";
    xp.max = 100;
    xp.value = 0;

    var builder = document.createElement("div");
    builder.className = "pet-builder";
    builder.id = "pet-builder";
    builder.append(
      optionRow("Shape", "shape", SHAPES, SHAPE_LABEL),
      optionRow("Colour", "palette", PALETTES, PALETTE_LABEL),
      optionRow("Face", "face", FACES, FACE_LABEL),
      optionRow("Extra", "accessory", ACCESSORIES, ACC_LABEL),
      optionRow("Vibe", "trait", TRAITS, TRAIT_LABEL)
    );

    var nameRow = document.createElement("div");
    nameRow.className = "pet-name-row";
    var nameInput = document.createElement("input");
    nameInput.id = "pet-name";
    nameInput.type = "text";
    nameInput.maxLength = 24;
    nameInput.autocomplete = "off";
    nameInput.spellcheck = false;
    nameInput.placeholder = "name your pet…";
    nameInput.setAttribute("aria-label", "Name your Blastling");
    nameInput.addEventListener("change", function () { setName(nameInput.value); });
    nameInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); setName(nameInput.value); nameInput.blur(); }
    });
    nameRow.appendChild(nameInput);

    var hideBtn = document.createElement("button");
    hideBtn.type = "button";
    hideBtn.className = "pet-hide-btn";
    hideBtn.textContent = "hide pet";
    hideBtn.addEventListener("click", dismissPet);

    hud.append(meta, xp, builder, nameRow, hideBtn);

    // coach bubble — click-through so it never blocks the app.
    var bubbleEl = document.createElement("div");
    bubbleEl.className = "pet-bubble";
    bubbleEl.setAttribute("aria-hidden", "true");
    var bubbleText = document.createElement("span");
    bubbleText.id = "pet-bubble-text";
    bubbleEl.appendChild(bubbleText);

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

    root.append(hud, bubbleEl, stage, toggle);
    document.body.appendChild(root);
    syncBuilder();
  }

  // Reflect the current config into the builder controls' pressed state + name.
  function syncBuilder() {
    if (!root) return;
    var c = pet.config;
    ["shape", "palette", "face", "accessory", "trait"].forEach(function (axis) {
      var buttons = root.querySelectorAll('.pet-opt[data-axis="' + axis + '"]');
      Array.prototype.forEach.call(buttons, function (btn) {
        btn.setAttribute("aria-pressed", String(btn.getAttribute("data-value") === c[axis]));
      });
    });
    var nameInput = document.getElementById("pet-name");
    if (nameInput && document.activeElement !== nameInput) nameInput.value = c.name === DEFAULT_NAME ? "" : c.name;
  }

  function setAxis(axis, value) {
    if (!pet) return;
    pet.config[axis] = value;
    if (axis === "trait") { /* purely verbal — no repaint needed */ }
    safeSave();
    persistConfig();
    setVisual(root.getAttribute("data-state") || "idle", pet.mood);
    syncBuilder();
    if (axis === "trait") speak(line("idle"));
    else if (axis === "shape") speak("New look. Same job — containing me.");
    else if (axis === "palette") speak("Fresh coat of paint. How do I look?");
  }

  function setName(raw) {
    if (!pet) return;
    var slug = slugName(raw);
    pet.config.name = slug;
    safeSave();
    persistConfig();
    setVisual(root.getAttribute("data-state") || "idle", pet.mood);
    syncBuilder();
    speak("Call me " + petName() + ".");
  }

  // Pick which terminal-screen face to show, given live state + mood.
  function faceFor(state, mood) {
    if (state === "thinking") return "think";
    if (state === "hurt" || mood === "rogue" || bsodActive) return "error";
    if (mood === "sleepy") return "sleepy";
    if (mood === "happy" || mood === "proud" || mood === "smug") return "happy";
    return "default";
  }

  function setVisual(state, mood) {
    if (!root) return;
    if (state) root.setAttribute("data-state", state);
    if (mood) { root.setAttribute("data-mood", mood); pet.mood = mood; }
    root.setAttribute("data-form", bsodActive ? "monitor" : pet.config.shape);
    root.setAttribute("data-bsod", String(bsodActive));
    root.setAttribute("data-palette", bsodActive ? "bsod" : pet.config.palette);
    root.setAttribute("data-accessory", pet.config.accessory);
    root.setAttribute("data-face-style", pet.config.face);
    root.setAttribute("data-face", faceFor(root.getAttribute("data-state"), pet.mood));
    if (root.getAttribute("data-state") === "idle") scheduleIdleMotion();
    else {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = null;
      root.setAttribute("data-idle", "still");
    }
    var lvl = document.getElementById("pet-meta-level");
    var nm = document.getElementById("pet-meta-name");
    var xp = document.getElementById("pet-xp");
    if (lvl) lvl.textContent = "LV " + pet.level;
    if (nm) nm.textContent = petName();
    if (xp) {
      var floor = 25 * (pet.level - 1) * (pet.level - 1);
      var next = 25 * pet.level * pet.level;
      var pct = Math.max(0, Math.min(100, Math.round(((pet.xp - floor) / (next - floor)) * 100)));
      xp.value = pct;
    }
  }

  function speak(text, announce) {
    var el = document.getElementById("pet-bubble-text");
    if (el) el.textContent = text || "";
    if (bubbleTimer) clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(function () { if (el) el.textContent = ""; }, 6000);
    if (announce && typeof window.announceStatus === "function") {
      try { window.announceStatus(text); } catch (e) {}
    }
  }

  function scheduleSleep() {
    if (sleepTimer) clearTimeout(sleepTimer);
    if (REDUCE) return;
    sleepTimer = setTimeout(function () {
      if (root && root.getAttribute("data-state") === "idle") setVisual("idle", "sleepy");
    }, 30000);
  }

  var IDLE_VARIANTS = ["breathe", "look", "stretch"];

  function scheduleIdleMotion() {
    if (idleTimer) clearTimeout(idleTimer);
    if (!root) return;
    if (REDUCE || root.getAttribute("data-state") !== "idle") {
      root.setAttribute("data-idle", "still");
      return;
    }
    var index = (stableHash(petName()) + idleCycle) % IDLE_VARIANTS.length;
    root.setAttribute("data-idle", IDLE_VARIANTS[index]);
    idleCycle += 1;
    idleTimer = setTimeout(scheduleIdleMotion, 5200);
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
      toggle.setAttribute("aria-label", pet.dismissed ? "Show Blastling" : "Blastling — open stats and customiser");
    }
  }

  // ---------- server hydrate (called by app.js; this module never fetches) ----------
  function hydratePet(serverConfig, profile) {
    if (!pet) return;
    if (serverConfig && typeof serverConfig === "object") {
      pet.config = normalizeConfig(serverConfig);
    }
    if (profile && typeof profile.score === "number") {
      // Server score is authoritative; mirror it so the pet level == profile level.
      pet.xp = Math.max(pet.xp, Math.floor(profile.score));
      pet.level = levelForXp(pet.xp);
    }
    if (profile && typeof profile.rank === "number") pet._rank = profile.rank;
    safeSave();
    renderFromStore();
    syncBuilder();
    maybeGreet();
  }

  function maybeGreet() {
    var today = todayKey();
    if (pet.greeted_date === today) return;
    var firstEver = pet.greeted_date === null && pet.xp === 0;
    pet.greeted_date = today;
    safeSave();
    if (firstEver) {
      speak("Hi — I'm " + petName() + ", the agent you supervise. Open me (BR) to make me yours.", true);
    } else {
      speak(line("returning", { rankLine: rankBrag() }), true);
    }
  }

  // ---------- event → state machine ----------
  function onScreen(name) {
    if (name === "verdict" || name === "results" || name === "drill-result") return;
    if (name === "round") {
      setVisual("waiting", "nervous");
      speak(line("waiting"));
    } else if (name === "test") {
      setVisual("idle", "content");
      speak("Calibration questions. Read me later.");
    } else if (name === "error") {
      setVisual("idle", "nervous");
      speak("That request lost containment.");
    } else {
      setVisual("idle", baselineMood());
      speak(line("idle"));
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
      setVisual("done", pet.level >= 4 ? "smug" : "proud");
      speak(up ? line("levelup") : line("correct", { rankLine: rankBrag() }), up);
      if (up) flashLevelUp();
      relaxTo("idle", baselineMood(), 3600);
    } else if (v === "partial") {
      consecutiveWrong = 0;
      gainXp(4);
      setVisual("idle", "content");
      speak(line("partial"));
      relaxTo("idle", baselineMood(), 3200);
    } else if (v === "wrong") {
      consecutiveWrong += 1;
      gainXp(1);
      var quip = detail && FAMILY_QUIP[detail.family];
      if (consecutiveWrong >= 3) {
        bsodActive = true;
        setVisual("hurt", "rogue");
        speak(line("bsod"));
        relaxTo("idle", baselineMood(), 4200);
      } else {
        setVisual("hurt", "rogue");
        speak(quip ? "Told you — " + quip + "." : line("wrong"));
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
      speak("You improved. Fewer places for me to hide. " + rankBrag(), true);
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
    if (relaxTimer) clearTimeout(relaxTimer);
    relaxTimer = setTimeout(function () {
      if (root.getAttribute("data-state") === "anxious") setVisual("waiting", "nervous");
    }, 2500);
  }

  function renderFromStore() {
    if (!root) return;
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
    maybeGreet();

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
  window.hydratePet = hydratePet;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
