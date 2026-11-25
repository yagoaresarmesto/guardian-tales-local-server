import { $, feedback, setArtwork } from "/panel.js";

const endpoint = "/api/expedition";
let state;
let areaFilter = "";

function stageInfo(row) {
  const key = typeof row.name === "string" ? row.name : "";
  const match = /^expedition_battle_chosenone_(\d+)_(.+)$/.exec(key);
  if (match) {
    const suffix = match[2];
    const name = /^\d+$/.test(suffix) ? "Stage " + suffix : titleWords(suffix);
    let kind = "stage";
    if (suffix === "boss" || suffix === "unexplored") kind = suffix;
    else if (suffix.startsWith("hidden_")) kind = "hidden";
    return {area: "Area " + match[1], name, kind};
  }
  if (key.startsWith("expedition_event_")) {
    return {area: "Events", name: titleWords(key.slice("expedition_event_".length)), kind: "event"};
  }
  return {area: "Other stages", name: titleWords(key.replace(/^expedition_/, "")) || "Stage " + row.stage_id, kind: "stage"};
}

function titleWords(key) {
  return key.replaceAll("_", " ").replace(/\b[a-z]/g, letter => letter.toUpperCase());
}

function levelRange(rows, key) {
  const values = rows.map(row => row[key]);
  const min = Math.min(...values), max = Math.max(...values);
  return min === max ? String(min) : min + "–" + max;
}

function isGlobal() {
  return $("editor").elements.scope.value === "all";
}

function renderTarget() {
  const all = isGlobal();
  const selected = state.stages.filter(row => all || row.stage_id === Number($("stage").value));
  $("stage-field").hidden = all;
  const current = selected.length ? levelRange(selected, "enemy_level") : "";
  $("current").textContent = current || "—";
  $("original").textContent = selected.length ? levelRange(selected, "original_level") : "—";
  $("level").value = /^\d+$/.test(current) ? current : "";
  $("level").disabled = !state.trial_enabled;
  $("apply").disabled = !state.trial_enabled || !selected.length;
  $("apply").textContent = all ? "Apply to all " + selected.length + " stages" : "Apply to stage";
  $("restore").textContent = all ? "Restore all original levels" : "Restore original level";
  $("restore").disabled = !selected.some(row => row.overridden);
  const row = selected[0];
  $("target-area").textContent = all ? "All areas" : row?.area || "";
  $("target-name").textContent = all ? selected.length + " stages" : row?.name || "No stage selected";
  const rift = !all && row?.kind === "unexplored";
  setArtwork($("target-art"), state.hasArt ? (rift ? "/expedition/rift.png" : "/expedition/camp.jpg") : null);
  for (const card of $("rows").children) {
    card.setAttribute("aria-pressed", String(!all && card.dataset.stage === $("stage").value));
  }
}

function renderAreas() {
  const areas = ["", ...new Set(state.stages.map(row => row.area))];
  if (!areas.includes(areaFilter)) areaFilter = "";
  $("areas").replaceChildren(...areas.map(area => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.area = area;
    button.textContent = area || "All areas";
    button.setAttribute("aria-pressed", String(areaFilter === area));
    return button;
  }));
}

function renderRows() {
  const query = $("search").value.toLowerCase().replaceAll("·", " ").replace(/\s+/g, " ").trim();
  const filtered = state.stages.filter(row =>
    (!areaFilter || row.area === areaFilter) && (!$("only-custom").checked || row.overridden)
    && [row.stage_id, row.key, row.area, row.name].join(" ").toLowerCase().includes(query)
  );
  const nodes = filtered.map(row => {
    const card = $("stage-card").content.firstElementChild.cloneNode(true);
    card.dataset.stage = row.stage_id;
    card.dataset.kind = row.kind;
    card.toggleAttribute("data-custom", row.overridden);
    card.setAttribute("aria-pressed", String(!isGlobal() && String(row.stage_id) === $("stage").value));
    const label = row.area + " · " + row.name;
    card.setAttribute("aria-label", label + ", original level " + row.original_level + ", configured level " + row.enemy_level + (row.overridden ? ", customized" : ""));
    card.title = label + " · " + row.stage_id;
    card.querySelector("small").textContent = row.area;
    card.querySelector("strong").textContent = row.name;
    card.querySelector(".original").textContent = row.original_level;
    card.querySelector(".stage-levels b").textContent = row.enemy_level;
    return card;
  });
  $("rows").replaceChildren(...nodes);
  $("rows").parentElement.scrollTop = 0;
  $("empty").hidden = filtered.length > 0;
  $("count").textContent = filtered.length + " of " + state.stages.length + " stages";
}

function display(next) {
  state = {...next, stages: next.stages.map(row => ({...row, key: row.name, ...stageInfo(row)}))};
  const previous = $("stage").value;
  $("stage").replaceChildren(...state.stages.map(row => new Option(row.area + " · " + row.name + " · " + row.stage_id, row.stage_id)));
  if (state.stages.some(row => String(row.stage_id) === previous)) $("stage").value = previous;
  $("bounds").textContent = "(1–" + state.max_enemy_level + ")";
  $("level").max = state.max_enemy_level;
  document.querySelector(".expedition-page").toggleAttribute("data-art", state.hasArt);
  setArtwork($("journey"), state.hasArt ? "/expedition/journey.jpg" : null);
  const custom = state.stages.filter(row => row.overridden).length;
  $("overview").textContent = state.stages.length + " stages · " + custom + " customized";
  $("trial").textContent = state.trial_enabled ? "Expedition trial enabled" : "Trial disabled · Enable the Expedition trial to apply levels.";
  renderAreas();
  renderRows();
  renderTarget();
}

async function refresh(message = "") {
  $("controls").disabled = $("reload").disabled = true;
  try {
    const response = await fetch(endpoint, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load stage levels.");
    display(data);
    $("controls").disabled = false;
    feedback(message);
  } catch (error) {
    feedback([message, error.message].filter(Boolean).join(" "), true);
  } finally {
    $("reload").disabled = false;
  }
}

async function save(action) {
  const body = {action, revision: state.revision, scope: isGlobal() ? "all" : "stage"};
  if (!isGlobal()) body.stage = Number($("stage").value);
  if (action === "set-level") body.level = $("level").valueAsNumber;
  $("controls").disabled = $("reload").disabled = true;
  feedback("Saving enemy levels…");
  try {
    const response = await fetch(endpoint, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      if (response.status === 400) $("controls").disabled = false;
      const data = await response.json();
      throw new Error(data.error || "Reload the stage list and try again.");
    }
    await refresh("Levels saved. Restart the backend and reopen the game.");
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("reload").disabled = false;
  }
}

$("editor").addEventListener("change", event => {
  if (event.target.name === "scope" || event.target.id === "stage") {
    renderTarget();
    feedback("");
  }
});
$("editor").addEventListener("submit", event => {
  event.preventDefault();
  if (!$("controls").disabled && !$("apply").disabled) save("set-level");
});
$("restore").addEventListener("click", () => save("restore-level"));
$("rows").addEventListener("click", event => {
  const pick = event.target.closest("button[data-stage]");
  if (!pick || $("controls").disabled) return;
  $("editor").elements.scope.value = "stage";
  $("stage").value = pick.dataset.stage;
  renderTarget();
  feedback("");
  ($("level").disabled ? $("stage") : $("level")).focus();
});
$("reload").addEventListener("click", () => refresh());
$("areas").addEventListener("click", event => {
  const pick = event.target.closest("button[data-area]");
  if (!pick) return;
  areaFilter = pick.dataset.area;
  for (const button of $("areas").children) button.setAttribute("aria-pressed", String(button === pick));
  renderRows();
});
$("only-custom").addEventListener("change", () => { if (state) renderRows(); });
$("search").addEventListener("input", () => { if (state) renderRows(); });
refresh();
