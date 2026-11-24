import { $, el } from "/inventory-dom.js";

const api = "/api/game/mastery";
const number = new Intl.NumberFormat("en-GB");
const fields = new Map(), groups = new Map();
let activeGroup;
let state, writable = false, busy = false, stale = false;
let previewBody, timer, generation = 0, statusRequest = 0;

function show(id, text = "") {
  $(id).textContent = text;
  $(id).hidden = !text;
}

function buttons() {
  $("apply").disabled = busy || stale || !writable || !previewBody;
}

function access(allowed, reason = "Close Guardian Tales and stop the backend to apply mastery changes.") {
  writable = allowed === true;
  show("access", writable ? "" : reason);
  buttons();
}

async function checkAccess() {
  if (!state || busy || document.hidden) return;
  const request = ++statusRequest;
  try {
    const res = await fetch("/api/game/status", {cache: "no-store", signal: AbortSignal.timeout(4000)});
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (request === statusRequest) access(data.writable);
  } catch {
    if (request === statusRequest) access(false, "Cannot check the game save. Apply is locked until the panel reconnects.");
  }
}

async function json(url, body) {
  const options = {cache: "no-store"};
  if (body) Object.assign(options, {method: "POST", headers: {"Content-Type": "application/json"}, body});
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "Cannot read mastery data.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function problem(error) {
  $("review").hidden = false;
  show("issue", error.message);
  if (error.status === 409) {
    stale = true;
    $("reload").hidden = false;
  }
  if (error.status === 423) access(false);
  buttons();
}

const classArt = {Warrior: "warrior", Ranged: "ranged", Tank: "tank", Support: "support"};
const skillIcons = {ATK: "⚔", HP: "♥", DEF: "⛨", "Skill damage": "✦"};

function selectClass(id) {
  activeGroup = id;
  for (const [key, group] of groups) {
    group.panel.hidden = key !== id;
    group.button.setAttribute("aria-pressed", String(key === id));
  }
  $("skills-heading").textContent = groups.get(id).name + " skills";
}

function addClass(skill) {
  const name = skill.className, button = el("button", "class-button");
  button.type = "button";
  const icon = el("span", "class-icon", name.slice(0, 1));
  icon.setAttribute("aria-hidden", "true");
  if (classArt[name]) {
    const sprite = el("img");
    sprite.alt = "";
    sprite.onload = () => icon.replaceChildren(sprite);
    sprite.src = "/type-icon/" + classArt[name] + ".png";
  }
  const text = el("span", "class-name", name), total = el("span", "class-total");
  text.append(total);
  button.append(icon, text);
  const panel = el("div", "class-skills");
  panel.id = "class-" + skill.group;
  button.setAttribute("aria-controls", panel.id);
  button.onclick = () => selectClass(skill.group);
  $("classes").append(button);
  $("skills").append(panel);
  groups.set(skill.group, {name, button, panel, total, count: 0});
}

function stepButton(label, step, input, name) {
  const button = el("button", "level-step", label);
  button.type = "button";
  button.setAttribute("aria-label", (step > 0 ? "Increase " : "Decrease ") + name);
  button.onclick = () => {
    const value = Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : 0;
    input.value = Math.max(0, Math.min(state.maxLevel, value + step));
    input.dispatchEvent(new Event("input", {bubbles: true}));
  };
  return button;
}

function renderSkills() {
  fields.clear(); groups.clear();
  $("classes").replaceChildren(); $("skills").replaceChildren();
  for (const skill of state.skills) {
    if (!groups.has(skill.group)) addClass(skill);
    const group = groups.get(skill.group);
    group.count++;
    const row = el("div", "skill-row");
    const text = el("div", "skill-copy"), icon = el("span", "skill-icon", skillIcons[skill.name] || "◆");
    icon.setAttribute("aria-hidden", "true");
    const title = el("h3", "", skill.name + (skillIcons[skill.name] ? " Increase" : ""));
    const bonus = el("span"), change = el("span", "bonus-change");
    const description = el("p"); description.append(bonus, change);
    text.append(title, description);
    const cost = el("span", "skill-cost"), costText = el("span");
    const point = el("span", "point-icon"); point.setAttribute("aria-hidden", "true");
    cost.append(point, costText);
    const name = skill.className + " " + skill.name;
    const input = el("input");
    input.type = "number"; input.required = true; input.min = 0; input.max = state.maxLevel; input.step = 1;
    input.inputMode = "numeric"; input.value = skill.level; input.setAttribute("aria-label", name);
    const down = stepButton("−", -1, input, name), up = stepButton("+", 1, input, name);
    const controls = el("div", "level-control");
    const stepper = el("div", "stepper"); stepper.append(down, input, up);
    controls.append(el("span", "level-label", "Level"), stepper);
    row.append(icon, text, cost, controls);
    group.panel.append(row);
    fields.set(skill.id, {input, bonus, change, down, up, cost, costText});
  }
  if (groups.size) selectClass(groups.has(activeGroup) ? activeGroup : groups.keys().next().value);
}

function displayLevel(skill, field) {
  const value = field.input.valueAsNumber, valid = field.input.validity.valid;
  const saved = skill.bonuses?.[skill.level], projected = skill.bonuses?.[value];
  field.bonus.textContent = valid && projected != null
    ? skill.className + " heroes’ " + skill.name + " +" + number.format(projected) + "%"
    : "Saved level " + skill.level;
  const difference = valid && projected != null && saved != null ? projected - saved : 0;
  field.change.textContent = difference ? " (" + (difference > 0 ? "+" : "") + number.format(difference) + "%)" : "";
  field.change.classList.toggle("decrease", difference < 0);
  field.down.disabled = valid && value === 0;
  field.up.disabled = valid && value === state.maxLevel;
  const cost = valid ? state.levelCosts?.[value] : null;
  field.costText.textContent = cost != null ? number.format(cost) : "—";
  field.cost.title = cost != null ? "Next level: " + number.format(cost) + " mastery points" : (value === state.maxLevel ? "Maximum level" : "Next level cost unavailable");
  field.cost.setAttribute("aria-label", field.cost.title);
}

function edit() {
  clearTimeout(timer);
  const request = ++generation;
  previewBody = null;
  const levels = {}, totals = new Map();
  let dirty = false, valid = true, anyLevel = false;
  for (const skill of state.skills) {
    const field = fields.get(skill.id), input = field.input, value = input.valueAsNumber;
    displayLevel(skill, field);
    const changed = value !== skill.level;
    input.classList.toggle("modified", changed);
    dirty ||= changed;
    valid &&= input.validity.valid;
    anyLevel ||= value > 0;
    levels[skill.id] = value;
    totals.set(skill.group, (totals.get(skill.group) ?? 0) + value);
  }
  for (const [id, group] of groups) {
    const value = totals.get(id), maximum = group.count * state.maxLevel;
    group.total.textContent = (Number.isFinite(value) ? value : "—") + " / " + maximum;
  }
  $("review").hidden = !dirty && !stale;
  $("reset").disabled = !anyLevel && valid;
  $("max").disabled = [...fields.values()].every(({input}) => input.valueAsNumber === state.maxLevel);
  $("undo").disabled = !dirty;
  $("delta-label").textContent = "Point change";
  $("delta").textContent = dirty ? "—" : "0";
  $("after").textContent = dirty ? "—" : number.format(state.balance);
  show("excess");
  if (!stale) show("issue");
  buttons();
  if (stale || !dirty) return;
  if (!valid) {
    show("issue", "Enter a whole level from 0 to " + state.maxLevel + " for each skill.");
    return;
  }
  const body = JSON.stringify({version: state.version, levels});
  timer = setTimeout(async () => {
    try {
      const result = await json(api + "/preview", body);
      if (request !== generation) return;
      $("delta-label").textContent = result.delta > 0 ? "Points to spend" : "Points credited";
      $("delta").textContent = number.format(Math.abs(result.balance - state.balance));
      $("after").textContent = number.format(result.balance);
      if (result.excess) show("excess", number.format(result.excess) + " refund points exceed the ceiling and will be discarded if you apply.");
      previewBody = result.changed ? body : null;
      buttons();
    } catch (error) { if (request === generation) problem(error); }
  }, 150);
}

async function load() {
  clearTimeout(timer); ++generation; ++statusRequest;
  state = null; previewBody = null; stale = false;
  $("allocation").hidden = true;
  $("reload").hidden = true;
  show("loading", "Loading mastery…");
  try {
    state = await json(api);
    renderSkills();
    $("level-range").textContent = "Level 0–" + state.maxLevel;
    $("balance").textContent = number.format(state.balance);
    $("ceiling").textContent = "Maxing all skills costs " + number.format(state.maxInvestment) +
      " points. Refunds can bring your balance up to " + number.format(state.refundCeiling) + ".";
    show("message");
    edit(); access(state.writable);
    $("allocation").hidden = false;
    show("loading");
  } catch (error) { show("loading", error.message); }
}

$("skills").oninput = () => { show("message"); edit(); };
for (const id of ["reset", "max", "undo"]) {
  $(id).onclick = () => {
    for (const skill of state.skills) {
      const targets = {reset: 0, max: state.maxLevel, undo: skill.level};
      fields.get(skill.id).input.value = targets[id];
    }
    show("message"); edit();
  };
}
$("reload").onclick = load;
$("allocation").onsubmit = async event => {
  event.preventDefault();
  if ($("apply").disabled) return;
  const body = previewBody;
  busy = true; ++statusRequest; previewBody = null;
  $("allocation").inert = true; buttons();
  try {
    const result = await json(api, body);
    const {levels} = JSON.parse(body);
    state.balance = result.balance;
    state.version = result.version;
    for (const skill of state.skills) skill.level = levels[skill.id];
    $("balance").textContent = number.format(state.balance);
    edit();
    show("message", "Mastery allocation saved.");
  } catch (error) {
    if (error.status !== 409) edit();
    problem(error);
  } finally {
    busy = false; $("allocation").inert = false; buttons();
  }
};

const scene = document.querySelector(".training-scene");
scene.addEventListener("error", () => { scene.hidden = true; });
if (scene.complete && !scene.naturalWidth) scene.hidden = true;

load();
window.setInterval(checkAccess, 2500);
document.addEventListener("visibilitychange", checkAccess);
window.addEventListener("focus", checkAccess);
