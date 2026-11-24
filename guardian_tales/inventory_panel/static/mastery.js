import { $, el } from "/inventory-dom.js";

const api = "/api/game/mastery";
const number = new Intl.NumberFormat("en-GB");
const fields = new Map(), groups = new Map();
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
  show("issue", error.message);
  if (error.status === 409) {
    stale = true;
    $("reload").hidden = false;
  }
  if (error.status === 423) access(false);
  buttons();
}

function renderSkills() {
  fields.clear();
  groups.clear();
  $("classes").replaceChildren();
  for (const skill of state.skills) {
    if (!groups.has(skill.group)) {
      const card = el("section", "class-card");
      card.dataset.group = skill.group;
      const heading = el("h3", "", skill.className);
      const total = el("span", "class-total"), bar = el("progress");
      bar.setAttribute("aria-label", skill.className + " allocated levels");
      heading.append(total);
      const header = el("header");
      header.append(heading, bar);
      card.append(header);
      $("classes").append(card);
      groups.set(skill.group, {card, total, bar, count: 0});
    }
    const group = groups.get(skill.group);
    group.count++;
    const control = el("label", "skill", skill.name), input = el("input");
    input.type = "number"; input.required = true; input.min = 0; input.max = state.maxLevel; input.step = 1;
    input.inputMode = "numeric"; input.value = skill.level;
    input.setAttribute("aria-label", skill.className + " " + skill.name);
    control.append(input);
    group.card.append(control);
    fields.set(skill.id, input);
  }
}

function edit() {
  clearTimeout(timer);
  const request = ++generation;
  previewBody = null;
  const levels = {}, totals = new Map();
  let dirty = false, valid = true, anyLevel = false;
  for (const skill of state.skills) {
    const input = fields.get(skill.id), value = input.valueAsNumber;
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
    group.bar.max = maximum;
    group.bar.value = Number.isFinite(value) ? value : 0;
    group.total.textContent = (Number.isFinite(value) ? value : "—") + " / " + maximum;
  }
  $("reset").disabled = !anyLevel && valid;
  $("max").disabled = [...fields.values()].every(input => input.valueAsNumber === state.maxLevel);
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

$("classes").oninput = () => { show("message"); edit(); };
for (const id of ["reset", "max", "undo"]) {
  $(id).onclick = () => {
    for (const skill of state.skills) {
      const targets = {reset: 0, max: state.maxLevel, undo: skill.level};
      fields.get(skill.id).value = targets[id];
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

load();
window.setInterval(checkAccess, 2500);
document.addEventListener("visibilitychange", checkAccess);
window.addEventListener("focus", checkAccess);
