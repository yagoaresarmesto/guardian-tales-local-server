import { $, feedback } from "/panel.js";
import { SpecialtyTree } from "/tetis-specialty.js";
import { renderLoadout, loadoutChanges, loadoutValid, syncLoadoutSkills } from "/tetis-loadout.js";

const endpoint = "/api/tetis";
const format = new Intl.NumberFormat("en");
const tree = new SpecialtyTree(update);
let state, season, stale = false;

function numbersValid() {
  return [$("floor"), $("level"), $("experience")].every(input => input.disabled || input.validity.valid);
}

function changes() {
  const result = {...tree.changes(), ...loadoutChanges()};
  if ($("floor").valueAsNumber !== season.clearedFloor) result.clearedFloor = $("floor").valueAsNumber;
  if (season.nodes.length && $("experience").valueAsNumber !== season.experience) result.experience = $("experience").valueAsNumber;
  return result;
}

function update() {
  syncLoadoutSkills(season.id, tree.points);
  const floor = $("floor").valueAsNumber;
  $("floor-hint").textContent = $("floor").validity.valid
    ? (floor === season.maxFloor ? "All floors cleared." : "Next unlocked floor: " + format.format(floor + 1) + " of " + format.format(season.maxFloor) + ".")
    : "Choose a floor from 0 to " + format.format(season.maxFloor) + ".";
  const previous = state.seasons.find(row => row.id === season.id - 1);
  if (previous && previous.clearedFloor < previous.maxFloor) {
    $("floor-hint").textContent += " In normal progression, this chapter opens after season " + previous.id + ", floor " + previous.maxFloor + ".";
  }
  const level = $("level").valueAsNumber, xp = $("experience").valueAsNumber;
  const next = state.levelStarts[level];
  $("xp-hint").textContent = season.nodes.length && $("level").validity.valid && $("experience").validity.valid
    ? (next == null ? "Maximum Guardian Tactic Level." : format.format(next - xp) + " XP to level " + (level + 1) + ".") : "";
  const earned = Math.min(state.maxPoints, Math.floor(level / state.levelPerPoint));
  const valid = numbersValid() && loadoutValid() && (!season.nodes.length || tree.spent <= earned);
  const dirty = Object.keys(changes()).length > 0 || !valid;
  const canSave = !stale && dirty && valid;
  $("apply").disabled = !canSave;
  $("discard").disabled = !dirty;
  $("season").disabled = dirty;
  tree.refresh(earned, canSave);
}

function renderSeason() {
  season = state.seasons.find(row => row.id === Number($("season").value));
  $("floor").max = season.maxFloor;
  $("floor").value = season.clearedFloor;
  $("level").max = state.levelStarts.length;
  $("level").value = season.level;
  $("experience").max = state.maxExperience;
  $("experience").value = season.experience;
  $("training").hidden = $("level").disabled = $("experience").disabled = season.nodes.length === 0;
  tree.openSeason(state, season);
  renderLoadout(state, season.id, update);
  update();
}

async function load(message = "") {
  $("editor-controls").disabled = $("refresh").disabled = true;
  try {
    const response = await fetch(endpoint, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load Tetis progression.");
    const previous = $("season").value;
    state = data;
    stale = false;
    document.querySelector(".tetis-banner").toggleAttribute("data-art", data.hasArt);
    $("season").replaceChildren(...data.seasons.map(s =>
      new Option("Season " + s.id + (state.labels[s.title] ? " · " + state.labels[s.title] : ""), s.id)));
    $("season").value = data.seasons.some(s => String(s.id) === previous) ? previous : data.currentSeason;
    if ($("season").selectedIndex < 0) $("season").selectedIndex = 0;
    renderSeason();
    $("editor-controls").disabled = false;
    feedback(message);
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("refresh").disabled = false;
  }
}

$("level").oninput = () => {
  if ($("level").validity.valid) $("experience").value = state.levelStarts[$("level").valueAsNumber - 1];
  update();
};
$("experience").oninput = () => {
  if ($("experience").validity.valid) {
    $("level").value = state.levelStarts.filter(value => value <= $("experience").valueAsNumber).length;
  }
  update();
};
$("floor").oninput = update;
$("season").onchange = renderSeason;
$("discard").onclick = () => { if (stale) load(); else { renderSeason(); feedback(""); } };
$("refresh").onclick = () => load();
$("tetis-form").onsubmit = async event => {
  event.preventDefault();
  if ($("apply").disabled) return;
  const body = {seasonId: season.id, revision: season.revision, ...changes()};
  $("editor-controls").disabled = $("refresh").disabled = true;
  try {
    const response = await fetch(endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    if (!response.ok) {
      stale = response.status === 409;
      throw new Error((await response.json()).error || "Could not save Tetis progression.");
    }
    await load("Progress saved. Reopen the Tetis lobby to load it.");
  } catch (error) {
    feedback(error.message, true);
    $("editor-controls").disabled = false;
    update();
  } finally {
    $("refresh").disabled = false;
  }
};
load();
