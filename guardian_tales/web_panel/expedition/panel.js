import { $, feedback } from "/panel.js";

const endpoint = "/api/expedition";
let state;

function stageName(row) {
  const key = typeof row.name === "string" ? row.name : "";
  const match = /^expedition_battle_chosenone_(\d+)_(.+)$/.exec(key);
  if (match) {
    const stage = /^\d+$/.test(match[2]) ? "Stage " + match[2] : titleWords(match[2]);
    return "Area " + match[1] + " · " + stage;
  }
  return titleWords(key.replace(/^expedition_/, "")) || "Stage " + row.stage_id;
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
}

function renderRows() {
  const query = $("search").value.trim().toLowerCase();
  const filtered = state.stages.filter(row =>
    [row.stage_id, row.name, stageName(row)].join(" ").toLowerCase().includes(query)
  );
  const nodes = filtered.map(row => {
    const tr = document.createElement("tr");
    tr.toggleAttribute("data-custom", row.overridden);
    const name = tr.insertCell();
    const pick = document.createElement("button");
    pick.type = "button";
    pick.dataset.stage = row.stage_id;
    pick.textContent = stageName(row);
    pick.title = "Edit this stage";
    const id = document.createElement("small");
    id.textContent = row.stage_id;
    name.append(pick, id);
    tr.insertCell().textContent = row.original_level;
    tr.insertCell().textContent = row.enemy_level;
    return tr;
  });
  $("rows").replaceChildren(...nodes);
  $("empty").hidden = filtered.length > 0;
  const custom = state.stages.filter(row => row.overridden).length;
  $("count").textContent = filtered.length + " of " + state.stages.length + " stages · " + custom + " customized";
}

function display(next) {
  state = next;
  const previous = $("stage").value;
  $("stage").replaceChildren(...state.stages.map(row => new Option(stageName(row) + " · " + row.stage_id, row.stage_id)));
  if (state.stages.some(row => String(row.stage_id) === previous)) $("stage").value = previous;
  $("bounds").textContent = "(1–" + state.max_enemy_level + ")";
  $("level").max = state.max_enemy_level;
  $("forest").hidden = !state.hasArt;
  $("trial").textContent = state.trial_enabled ? "Expedition trial enabled" : "Trial disabled · Enable the Expedition trial to apply levels.";
  renderTarget();
  renderRows();
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
  if (event.target.name === "scope" || event.target.id === "stage") renderTarget();
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
  ($("level").disabled ? $("stage") : $("level")).focus();
});
$("reload").addEventListener("click", () => refresh());
$("search").addEventListener("input", () => { if (state) renderRows(); });
refresh();
