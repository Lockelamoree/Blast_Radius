// Team board — developer-only, read-only. Renders finished-session summaries
// from /api/team/summary with createElement + textContent (no innerHTML).
(function () {
  const $ = (selector) => document.querySelector(selector);

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function dash(value) {
    return value === null || value === undefined ? "—" : String(value);
  }

  function signed(value) {
    if (value === null || value === undefined) return "—";
    return value >= 0 ? `+${value}` : String(value);
  }

  function shortDate(iso) {
    if (!iso) return "—";
    return iso.slice(0, 16).replace("T", " ");
  }

  function renderRoster(rows) {
    const body = $("#team-roster tbody");
    body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(row.handle),
        cell(row.sessions),
        cell(signed(row.best_delta)),
        cell(dash(row.weakest)),
        cell(row.families_cleared),
        cell(`${row.average_reasoning}%`),
        cell(shortDate(row.latest_finished_at))
      );
      body.append(tr);
    });
  }

  function renderRecent(rows) {
    const body = $("#team-recent tbody");
    body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(row.operator_handle || "anonymous"),
        cell(row.mode),
        cell(row.pretest),
        cell(dash(row.posttest)),
        cell(signed(row.delta)),
        cell(row.rounds_played),
        cell(`${row.average_reasoning}%`),
        cell(shortDate(row.finished_at))
      );
      body.append(tr);
    });
  }

  async function load() {
    try {
      const response = await fetch("/api/team/summary", {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const detail = response.status === 403
          ? "Developer access is required for the team board."
          : `Could not load the team board (status ${response.status}).`;
        const errorEl = $("#team-error");
        errorEl.textContent = detail;
        errorEl.classList.remove("hidden");
        return;
      }
      const data = await response.json();
      if (!data.summaries.length) {
        $("#team-empty").classList.remove("hidden");
      }
      renderRoster(data.roster);
      renderRecent(data.summaries);
    } catch (error) {
      const errorEl = $("#team-error");
      errorEl.textContent = "Could not reach the server.";
      errorEl.classList.remove("hidden");
    }
  }

  load();
})();
