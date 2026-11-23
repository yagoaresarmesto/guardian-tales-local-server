import { $, feedback, setArtwork } from "/panel.js";

const endpoint = "/api/guild-war";
const phaseLabels = {
  "coop-offense": "Cooperative attack", "coop-defense": "Cooperative defense",
  "multi-offense": "Fortress siege", "multi-defense": "Fortress defense"
};
const roundLabels = {auto: "Automatic", prep: "Preparation", combat: "Combat"};
let state;

function addDetail(label, value) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value;
  row.append(term, description);
  $("details").append(row);
}

function castleLabel(id) {
  const castle = state.castles.find(row => row.id === id);
  return castle ? "Castle " + id + " · Grade " + castle.grade : "Castle " + id;
}

function isFortress(phase) {
  return phase === "multi-offense" || phase === "multi-defense";
}

function showPhase(phase, round = "auto", castle = 0) {
  $("phase").value = phase;
  $("dispute").hidden = !isFortress(phase);
  $("round").value = round;
  const attacking = phase === "multi-offense";
  $("castle-label").textContent = attacking ? "Siege target" : "Owned castle";
  $("castle").replaceChildren(new Option(attacking ? "No marked target" : "No owned castle", "0"));
  for (const row of state.castles) $("castle").add(new Option(castleLabel(row.id), row.id));
  $("castle").value = String(castle);
}

function display(next) {
  state = next;
  const saved = state.selection;
  $("phase").replaceChildren(...state.phases.map(key => new Option(phaseLabels[key], key)));
  $("round").replaceChildren(...state.rounds.map(key => new Option(roundLabels[key], key)));
  $("skip-basic").checked = saved.skip_basic_requirement;
  const castle = saved.local_attack_castle || saved.local_defense_castle;
  showPhase(saved.phase_name || "coop-offense", saved.round_mode || "auto", castle);
  $("war-status").textContent = saved.enabled ? "Season " + saved.season_id + " enabled" : "Guild Wars disabled";
  $("war-status").dataset.enabled = String(saved.enabled);
  $("inactive-note").hidden = saved.enabled;
  $("disable").hidden = !saved.enabled;
  $("details").replaceChildren();
  $("details").hidden = !saved.enabled;
  if (saved.enabled) {
    addDetail("Phase", phaseLabels[saved.phase_name]);
    if (isFortress(saved.phase_name)) {
      addDetail("Round", roundLabels[saved.round_mode]);
      addDetail(saved.phase_name === "multi-offense" ? "Siege target" : "Owned castle", castle ? castleLabel(castle) : "None");
    }
    addDetail("Basic course", saved.skip_basic_requirement ? "Skipped" : "Required");
    addDetail("Season window (UTC)", saved.period.from.slice(0, 10) + " → " + saved.period.to.slice(0, 10));
  }
  $("apply").textContent = saved.enabled ? "Apply settings" : "Enable Guild Wars";
  $("defense-preset").disabled = !state.castles.some(row => row.id === 21);
  setArtwork($("fortress-art"), state.hasArt ? "/guild-war/fortress.png" : null);
}

function lockControls() {
  $("controls").disabled = true;
  $("disable").disabled = true;
  $("reload").disabled = true;
}

async function refresh(message = "") {
  lockControls();
  try {
    const response = await fetch(endpoint, {cache: "no-store"});
    const next = await response.json();
    if (!response.ok) throw new Error(next.error || "Could not load Guild Wars.");
    display(next);
    $("controls").disabled = Boolean(next.catalogError);
    $("disable").disabled = false;
    feedback([message, next.catalogError].filter(Boolean).join(" "), Boolean(next.catalogError));
  } catch (error) {
    feedback([message, error.message].filter(Boolean).join(" "), true);
  } finally {
    $("reload").disabled = false;
  }
}

async function submit(action) {
  const body = {action, revision: state.revision};
  if (action === "enable") {
    body.phase = $("phase").value;
    body.skipBasic = $("skip-basic").checked;
    body.round = isFortress(body.phase) ? $("round").value : "auto";
    body.castle = isFortress(body.phase) ? Number($("castle").value) : 0;
  }
  lockControls();
  feedback("Saving Guild Wars settings…");
  try {
    const response = await fetch(endpoint, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      const result = await response.json();
      if (response.status === 400) {
        $("controls").disabled = Boolean(state.catalogError);
        $("disable").disabled = false;
      }
      throw new Error(result.error || "Reload the saved configuration and try again.");
    }
    await refresh("Settings saved. Fully close and reopen Guardian Tales.");
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("reload").disabled = false;
  }
}

function preset(phase, castle) {
  showPhase(phase, "prep", castle);
  $("skip-basic").checked = true;
  feedback("Preset selected. Apply it to save.");
}

$("attack-preset").addEventListener("click", () => preset("multi-offense", 0));
$("defense-preset").addEventListener("click", () => preset("multi-defense", 21));
$("phase").addEventListener("change", () => showPhase($("phase").value));
$("editor").addEventListener("change", () => feedback(""));
$("editor").addEventListener("submit", event => {
  event.preventDefault();
  if (!$("controls").disabled) submit("enable");
});
$("disable").addEventListener("click", () => submit("disable"));
$("reload").addEventListener("click", () => refresh());
refresh();
