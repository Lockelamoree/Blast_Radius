// Browser-local learner history. Stored ONLY in this browser under a single
// versioned localStorage key — never sent to or stored by the server. No model
// calls, no network requests, and text is rendered with textContent only.
// Degrades to a stateless experience when storage is unavailable (private
// mode). Powers the returning-user panel, the drill streak, and callbacks.
(function () {
  const KEY = "blast-radius:v1";
  const CALLBACK_DAYS = 3;
  const MAX_SESSIONS = 30;
  const $ = (selector) => document.querySelector(selector);

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  // "Daily" is the user's local day, not UTC — otherwise a consecutive-day
  // streak silently resets for anyone west of UTC drilling in the evening.
  function today() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function addDays(iso, days) {
    const [y, m, d] = iso.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    date.setDate(date.getDate() + days);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  function randomId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return `br-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
  }

  function fresh() {
    return { schema: 1, client_id: randomId(), sessions: [], streak: { count: 0, last_drill_date: null }, callbacks: [] };
  }

  function available() {
    try {
      const probe = "__br_probe__";
      window.localStorage.setItem(probe, "1");
      window.localStorage.removeItem(probe);
      return true;
    } catch (error) {
      return false;
    }
  }

  function safeLoad() {
    if (!available()) return null;
    try {
      const raw = window.localStorage.getItem(KEY);
      if (!raw) return fresh();
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.schema > 1) return fresh();
      return {
        schema: 1,
        client_id: parsed.client_id || randomId(),
        sessions: Array.isArray(parsed.sessions) ? parsed.sessions : [],
        streak: parsed.streak && typeof parsed.streak.count === "number" ? parsed.streak : { count: 0, last_drill_date: null },
        callbacks: Array.isArray(parsed.callbacks) ? parsed.callbacks : [],
      };
    } catch (error) {
      return fresh();
    }
  }

  function safeSave(store) {
    if (!available()) return;
    try {
      window.localStorage.setItem(KEY, JSON.stringify(store));
    } catch (error) {
      /* storage full or blocked — degrade silently */
    }
  }

  function pruneCallbacks(store) {
    const cutoff = addDays(today(), -30);
    store.callbacks = store.callbacks.filter((cb) => cb.due_date >= cutoff);
  }

  function clearCallback(store, family) {
    store.callbacks = store.callbacks.filter((cb) => cb.family !== family);
  }

  function upsertCallback(store, family) {
    const due = addDays(today(), CALLBACK_DAYS);
    const existing = store.callbacks.find((cb) => cb.family === family);
    if (existing) {
      if (due < existing.due_date) existing.due_date = due;
    } else {
      store.callbacks.push({ family, due_date: due, created_date: today() });
    }
  }

  function historyClientKey() {
    const store = safeLoad();
    if (!store) return null;
    safeSave(store);
    return store.client_id;
  }

  function recordSessionHistory(results) {
    const store = safeLoad();
    if (!store) return null;
    const missed = new Set();
    const cleared = new Set();
    (results.rounds || []).forEach((round) => {
      if (round.verdict === "wrong" || !round.action_correct) missed.add(round.family);
      else cleared.add(round.family);
    });
    missed.forEach((family) => upsertCallback(store, family));
    cleared.forEach((family) => {
      if (!missed.has(family)) clearCallback(store, family);
    });
    const mastery = {};
    Object.values(results.competency_map || {}).forEach((value) => {
      mastery[value.label] = value.mastery_percent;
    });
    store.sessions.push({
      date: today(),
      mode: "session",
      delta: results.delta === undefined ? null : results.delta,
      average_reasoning_score: results.average_reasoning_score || 0,
      rounds_played: results.rounds_played || 0,
      mastery,
      missed_families: [...missed],
      rounds_needed_nudge: results.rounds_needed_nudge || 0,
      weakest: results.weakest_competency ? results.weakest_competency.label : null,
    });
    store.sessions = store.sessions.slice(-MAX_SESSIONS);
    pruneCallbacks(store);
    safeSave(store);
    return store;
  }

  function recordDrillHistory(drill) {
    const store = safeLoad();
    if (!store) return null;
    const day = today();
    const last = store.streak.last_drill_date;
    if (last === day) {
      /* same-day drill: streak unchanged */
    } else if (last === addDays(day, -1)) {
      store.streak.count += 1;
    } else {
      store.streak.count = 1;
    }
    store.streak.last_drill_date = day;
    let clearedCallback = false;
    let rescheduled = false;
    const family = drill && drill.family;
    const firstAttemptCorrect = drill && drill.verdict === "correct" && drill.action_correct;
    if (family) {
      const hadCallback = store.callbacks.some((cb) => cb.family === family);
      if (firstAttemptCorrect) {
        if (hadCallback) clearedCallback = true;
        clearCallback(store, family);
      } else if (hadCallback) {
        clearCallback(store, family);
        upsertCallback(store, family);
        rescheduled = true;
      }
    }
    pruneCallbacks(store);
    safeSave(store);
    return { streak: store.streak.count, clearedCallback, rescheduled };
  }

  function dueCallbacks(todayIso) {
    const store = safeLoad();
    if (!store) return [];
    const cutoff = todayIso || today();
    return store.callbacks
      .filter((cb) => cb && cb.family && cb.due_date && cb.due_date <= cutoff)
      .sort((a, b) => a.due_date.localeCompare(b.due_date));
  }

  function clearHistory() {
    if (!available()) return;
    try {
      window.localStorage.removeItem(KEY);
    } catch (error) {
      /* ignore */
    }
  }

  function renderReturningPanel() {
    const panel = $("#history-panel");
    if (!panel) return;
    const store = safeLoad();
    if (!store || (!store.sessions.length && !store.streak.count && !store.callbacks.length)) {
      panel.classList.add("hidden");
      return;
    }
    const last = store.sessions[store.sessions.length - 1];
    $("#history-streak").textContent = `${store.streak.count} day${store.streak.count === 1 ? "" : "s"}`;
    $("#history-last-delta").textContent = last && last.delta !== null && last.delta !== undefined
      ? (last.delta >= 0 ? `+${last.delta}` : String(last.delta))
      : "—";
    $("#history-weakest").textContent = last && last.weakest ? last.weakest : "—";
    const due = dueCallbacks();
    const callbackButton = $("#callback-start");
    if (due.length) {
      const family = due[0].family;
      callbackButton.textContent = `Retrain ${family.replaceAll("_", " ").toUpperCase()} — callback due →`;
      callbackButton.classList.remove("hidden");
      callbackButton.onclick = () => {
        if (window.startDrill) window.startDrill(family);
      };
    } else {
      callbackButton.classList.add("hidden");
    }
    panel.classList.remove("hidden");
  }

  window.historyClientKey = historyClientKey;
  window.recordSessionHistory = recordSessionHistory;
  window.recordDrillHistory = recordDrillHistory;
  window.dueCallbacks = dueCallbacks;
  window.clearHistory = clearHistory;
  window.renderReturningPanel = renderReturningPanel;

  const clearButton = $("#history-clear");
  if (clearButton) {
    clearButton.addEventListener("click", () => {
      clearHistory();
      if (window.clearPet) window.clearPet();
      const panel = $("#history-panel");
      if (panel) panel.classList.add("hidden");
      if (window.announceStatus) window.announceStatus("Local progress cleared from this browser.");
    });
  }

  renderReturningPanel();
})();
