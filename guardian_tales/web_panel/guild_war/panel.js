import { $, feedback, setArtwork } from "/panel.js";

const endpoint = "/api/guild-war";
const phases = {
  "coop-offense": {group: "Cooperative", action: "Attack", art: "attack"},
  "coop-defense": {group: "Cooperative", action: "Defense", art: "defense"},
  "multi-offense": {group: "Fortress", action: "Siege", art: "outpost"},
  "multi-defense": {group: "Fortress", action: "Defense", art: "fortress"}
};
const roundLabels = {auto: "Automatic", prep: "Preparation", combat: "Combat"};
const editor = $("editor");
let state;

function phaseLabel(phase) {
  return phases[phase].group + " " + phases[phase].action.toLowerCase();
}

function buildPhaseCards() {
  $("phase-cards").replaceChildren(...state.phases.map(phase => {
    const {group, action, art} = phases[phase];
    const card = $("phase-card").content.firstElementChild.cloneNode(true);
    card.dataset.phase = phase;
    card.querySelector("input").value = phase;
    card.querySelector("input").setAttribute("aria-label", phaseLabel(phase));
    card.querySelector(".phase-group").textContent = group;
    card.querySelector("strong").textContent = action;
    setArtwork(card.querySelector(".tile-art img"), state.hasArt ? "/guild-war/" + art + ".png" : null);
    return card;
  }));
}

function draft() {
  const phase = editor.elements.phase.value;
  const fortress = isFortress(phase);
  return {phase, round: fortress ? $("round").value : "auto",
    castle: fortress ? Number($("castle").value) : 0};
}

function preview() {
  const {phase, round, castle} = draft();
  const saved = state.selection;
  const matchesCastle = !isFortress(phase) || (saved.round_mode === round
    && (saved.local_attack_castle || saved.local_defense_castle || 0) === castle);
  const active = saved.enabled && saved.phase_name === phase && matchesCastle;
  $("preview-state").textContent = active ? "Active" : "Preview";
  $("preview").dataset.active = String(active);
  $("preview-phase").textContent = phaseLabel(phase);
  const target = $("preview-target");
  target.hidden = !isFortress(phase);
  if (!target.hidden) {
    target.textContent = roundLabels[round] + " · " + $("castle").selectedOptions[0].text;
  }
  $("preview").hidden = false;
}

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
  editor.elements.phase.value = phase;
  $("dispute").hidden = !isFortress(phase);
  $("round").value = round;
  const attacking = phase === "multi-offense";
  $("castle-label").textContent = attacking ? "Siege target" : "Owned castle";
  $("castle").replaceChildren(new Option(attacking ? "No marked target" : "No owned castle", "0"));
  for (const row of state.castles) $("castle").add(new Option(castleLabel(row.id), row.id));
  $("castle").value = state.castles.some(row => row.id === castle) ? String(castle) : "0";
}

function display(next) {
  state = next;
  const saved = state.selection;
  buildPhaseCards();
  $("round").replaceChildren(...state.rounds.map(key => new Option(roundLabels[key], key)));
  const castle = saved.local_attack_castle || saved.local_defense_castle;
  showPhase(saved.phase_name || "coop-offense", saved.round_mode || "auto", castle);
  $("war-status").textContent = saved.enabled ? "Season " + saved.season_id + " enabled" : "Guild Wars disabled";
  $("war-status").dataset.enabled = String(saved.enabled);
  $("inactive-note").hidden = saved.enabled;
  $("disable").hidden = !saved.enabled;
  $("details").replaceChildren();
  $("details").hidden = !saved.enabled;
  if (saved.enabled) {
    addDetail("Phase", phaseLabel(saved.phase_name));
    if (isFortress(saved.phase_name)) {
      addDetail("Round", roundLabels[saved.round_mode]);
      addDetail(saved.phase_name === "multi-offense" ? "Siege target" : "Owned castle", castle ? castleLabel(castle) : "None");
    }
    addDetail("Basic course", saved.skip_basic_requirement ? "Skipped" : "Required");
    addDetail("Season window (UTC)", saved.period.from.slice(0, 10) + " → " + saved.period.to.slice(0, 10));
  }
  $("apply").textContent = saved.enabled ? "Apply settings" : "Enable Guild Wars";
  $("defense-preset").disabled = !state.castles.some(row => row.id === 21);
  for (const image of document.querySelectorAll(".war-art [data-art]")) {
    setArtwork(image, state.hasArt ? "/guild-war/" + image.dataset.art + ".jpg" : null);
  }
  preview();
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
  if (action === "enable") Object.assign(body, draft(), {skipBasic: true});
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
  preview();
  feedback("Preset selected. Apply it to save.");
}

$("attack-preset").addEventListener("click", () => preset("multi-offense", 0));
$("defense-preset").addEventListener("click", () => preset("multi-defense", 21));
editor.addEventListener("change", event => {
  if (event.target.name === "phase") showPhase(event.target.value);
  preview();
  feedback("");
});
editor.addEventListener("submit", event => {
  event.preventDefault();
  if (!$("controls").disabled) submit("enable");
});
$("disable").addEventListener("click", () => submit("disable"));
$("reload").addEventListener("click", () => refresh());
refresh();
