import { $, feedback } from "/panel.js";

const endpoint = "/api/tetis";
const format = new Intl.NumberFormat("en");
let state, season, points, stale = false;

function translated(key, fallback) {
  return state.labels[key] || fallback;
}

function nodeName(node) {
  return translated(node.name, "Skill " + node.id);
}

function branchName(node) {
  return translated(node.categoryName, "Branch " + node.category).replace(/ Season Specialty Category$/, "");
}

function numbersValid() {
  return [$("floor"), $("level"), $("experience")].every(input => input.disabled || input.validity.valid)
    && Object.values(points).every(value => Number.isInteger(value) && value >= 0)
    && season.nodes.every(node => points[node.id] <= node.maxPoints);
}

function changes() {
  const result = {};
  if ($("floor").valueAsNumber !== season.clearedFloor) result.clearedFloor = $("floor").valueAsNumber;
  if (season.nodes.length && $("experience").valueAsNumber !== season.experience) result.experience = $("experience").valueAsNumber;
  if (season.nodes.some(node => points[node.id] !== node.points)) {
    result.abilities = Object.fromEntries(Object.entries(points).filter(([, count]) => count > 0));
  }
  return result;
}

function update() {
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
  const spent = Object.values(points).reduce((sum, count) => sum + (count || 0), 0);
  const earned = Math.min(state.maxPoints, Math.floor(level / state.levelPerPoint));
  $("budget").textContent = season.nodes.length && Number.isFinite(earned)
    ? spent + " / " + earned + " points assigned" : "";
  $("budget").dataset.error = String(spent > earned);
  const dirty = Object.keys(changes()).length > 0 || !numbersValid();
  $("apply").disabled = stale || !dirty || !numbersValid() || (season.nodes.length > 0 && spent > earned);
  $("discard").disabled = !dirty;
  $("season").disabled = dirty;
}

function renderBranch() {
  const category = Number($("branch").value);
  const nodes = season.nodes.filter(node => node.category === category);
  const rows = [];
  const branches = nodes[0]?.requiredCategories || [];
  if (branches.length) {
    const conditions = branches.map(rule => {
      const other = season.nodes.find(node => node.category === rule.id);
      return rule.points + " points in " + (other ? branchName(other) : "branch " + rule.id);
    });
    const hint = document.createElement("p");
    hint.className = "tree-note";
    hint.textContent = "Requires " + conditions.join(" and ") + ".";
    rows.push(hint);
  }
  let tier;
  for (const node of nodes) {
    if (tier !== node.step) {
      tier = node.step;
      const heading = document.createElement("h3");
      heading.className = "skill-tier";
      heading.textContent = "Tier " + tier + (node.requiredPoints ? " · " + node.requiredPoints + " points in earlier tiers" : "");
      rows.push(heading);
    }
    const row = document.createElement("div");
    row.className = "skill-row";
    const label = document.createElement("label");
    label.htmlFor = "skill-" + node.id;
    label.textContent = nodeName(node);
    if (node.requiresNodes?.length) {
      const prerequisite = document.createElement("small");
      prerequisite.textContent = "Requires max rank in " + node.requiresNodes.map(id => {
        const other = season.nodes.find(n => n.id === id);
        return other ? nodeName(other) : "skill " + id;
      }).join(", ");
      label.append(prerequisite);
    }
    const input = document.createElement("input");
    input.id = label.htmlFor;
    input.type = "number";
    input.min = 0;
    input.step = 1;
    input.max = node.maxPoints;
    input.required = true;
    input.value = points[node.id] ?? "";
    input.oninput = () => { points[node.id] = input.valueAsNumber; update(); };
    const limit = document.createElement("small");
    limit.textContent = "/ " + node.maxPoints;
    row.append(label, input, limit);
    rows.push(row);
  }
  $("nodes").replaceChildren(...rows);
}

function renderSeason() {
  season = state.seasons.find(row => row.id === Number($("season").value));
  points = Object.fromEntries(season.nodes.map(node => [node.id, node.points]));
  $("floor").max = season.maxFloor;
  $("floor").value = season.clearedFloor;
  $("level").max = state.levelStarts.length;
  $("level").value = season.level;
  $("experience").max = state.maxExperience;
  $("experience").value = season.experience;
  $("training").hidden = $("level").disabled = $("experience").disabled = season.nodes.length === 0;
  $("skills").hidden = season.nodes.length === 0;
  $("no-skills").hidden = !$("skills").hidden;
  const categories = new Map(season.nodes.map(node => [node.category, branchName(node)]));
  $("branch").replaceChildren(...Array.from(categories, ([id, name]) => new Option(name, id)));
  renderBranch();
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
$("branch").onchange = renderBranch;
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
