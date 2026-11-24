import { $, el, image, inventoryTile, renderTypeFilters, selectTypeFilter, watchGridPageSize } from "/inventory-dom.js";

let size = 24;
const groups = {
  main: {pools: "mainPools", container: "basic"},
  bonus: {pools: "pools", container: "slots"},
};
const initialQuery = new URLSearchParams(location.hash.slice(1));
let selected = Number(initialQuery.get("id")), family = initialQuery.get("type") || "";
let page = 0, data, visible = [], draft = [], saving = false;
const relicApi = "/api/game/relics";
let writable = false, statusRequest = 0;
$("search").value = initialQuery.get("q") || "";
if (["equipped", "imbued", "empty"].includes(initialQuery.get("show"))) $("show").value = initialQuery.get("show");

const current = () => visible.find(r => r.id === selected);
const stat = (id, level) => {
  const effect = data.effects[id];
  if (!effect) return "Level " + level;
  return Number((effect.base + effect.step * level).toFixed(5)) + effect.unit;
};
const effectName = id => data.effects[id]?.name ?? ("Option #" + id);
const summary = (id, level) => effectName(id) + " · " + stat(id, level);
function note(text = "", error = false) {
  $("message").hidden = !text; $("message").textContent = text;
  $("message").classList.toggle("error", error);
}
function syncUrl() {
  const q = new URLSearchParams();
  if (selected) q.set("id", selected);
  if (family) q.set("type", family);
  if ($("search").value) q.set("q", $("search").value);
  if ($("show").value !== "all") q.set("show", $("show").value);
  history.replaceState(null, "", location.pathname + (q.size ? "#" + q : ""));
}
function drawFamilies() {
  const groups = new Map([["", {count: data.copies.length}]]);
  for (const row of data.copies) {
    const name = data.specs[row.spec].family;
    if (!groups.has(name)) groups.set(name, {spec: row.spec, count: 0});
    groups.get(name).count++;
  }
  if (!groups.has(family)) family = "";
  renderTypeFilters($("types"), $("mobile-types"), Array.from(groups, ([key, {spec, count}]) => ({
    key, name: key || "All relics", count,
    iconUrl: spec ? "/icon/" + spec + ".png" : "/type-icon/all.png",
  })));
}
function tile(r) {
  const spec = data.specs[r.spec];
  const art = el("span", "tile-art"), icon = image("/icon/" + r.spec + ".png");
  icon.onerror = () => art.replaceChildren(el("span","fallback",spec.family.slice(0,2)));
  art.append(icon);
  const button = inventoryTile({ ...r, name: spec.name, stars: spec.stars, art,
    socketed: r.jewels > 0, selected: selected === r.id });
  button.dataset.stars = spec.stars;
  return button;
}
function drawGrid() {
  const start = page * size;
  $("tiles").replaceChildren(...visible.slice(start, start + size).map(tile));
  $("empty").hidden = !!visible.length;
  $("range").textContent = visible.length ? (start + 1) + "–" + Math.min(start + size,visible.length) + " of " + visible.length + " relics" : "0 relics";
  $("prev").disabled = page === 0; $("next").disabled = start + size >= visible.length;
  selectTypeFilter($("types"), $("mobile-types"), family);
}
function changedSlots() {
  const row = current();
  return draft.filter(({group, slot, option, level}) => {
    const saved = row[group][slot];
    return option !== saved.OptionId || level !== saved.Level;
  });
}
function slotPool(row, {group, slot}) {
  return data.specs[row.spec][groups[group].pools]?.[slot];
}
function editable(row, entry) {
  const opt = row[entry.group][entry.slot], bounds = slotPool(row,entry)?.[opt.OptionId];
  return !row.pending && !opt.Locked && !!bounds && opt.Level >= bounds[0] && opt.Level <= bounds[1];
}
function updateApplyButton() {
  $("save").disabled = saving || !writable || !changedSlots().length;
}
function setAccess(available, message = "") {
  writable = available === true;
  $("access").hidden = writable;
  const text = message || "Apply is locked while the game save is in use. Close Guardian Tales and stop the backend to enable it.";
  if (!writable && $("access").textContent !== text) $("access").textContent = text;
  if (current()) updateApplyButton();
}
async function checkAccess() {
  if (document.hidden || saving) return;
  const request = ++statusRequest;
  try {
    const response = await fetch(relicApi + "/status", {cache:"no-store", signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error();
    const status = await response.json();
    if (request === statusRequest) setAccess(status.writable);
  } catch {
    if (request === statusRequest) setAccess(false, "The editor cannot check the game save. Apply is locked until it reconnects.");
  }
}
function slotEditor(row, entry) {
  const {group, slot: index} = entry;
  const source = row[group][index], pool = slotPool(row, entry);
  const section = el("div", "relic-slot");
  const label = el("span", "slot-label", "Slot " + (index + 1) + (source.Locked ? " · Locked" : ""));
  label.id = group + "-slot-" + index;
  section.setAttribute("role", "group");
  section.setAttribute("aria-labelledby", label.id);
  section.append(label);
  if (!editable(row, entry)) {
    section.append(el("span","slot-summary",summary(source.OptionId, source.Level))); return section;
  }
  const controls = el("div","slot-controls"), effect = el("select"), value = el("select");
  const slotName = (group === "main" ? "basic slot " : "bonus slot ") + (index + 1);
  effect.setAttribute("aria-label","Effect for " + slotName);
  value.setAttribute("aria-label","Value for " + slotName);
  for (const id of Object.keys(pool)) effect.add(new Option(effectName(id),id));
  effect.value = String(entry.option); effect.disabled = Object.keys(pool).length === 1;
  const range = el("small","editor-note"), compare = el("small","edit-diff");
  function showChange() {
    compare.hidden = entry.option === source.OptionId && entry.level === source.Level;
    compare.textContent = summary(source.OptionId,source.Level) + " → " + summary(entry.option,entry.level);
    updateApplyButton();
  }
  function values() {
    const [low, high] = pool[entry.option];
    value.replaceChildren();
    for (let i = low; i <= high; i++) value.add(new Option(stat(entry.option,i),i));
    value.value = String(entry.level);
    range.textContent = "Range " + stat(entry.option,low) + " – " + stat(entry.option,high);
    showChange();
  }
  effect.onchange = () => {
    entry.option = Number(effect.value);
    entry.level = entry.option === source.OptionId ? source.Level : pool[entry.option][0];
    values(); note();
  };
  value.onchange = () => { entry.level = Number(value.value); showChange(); note(); };
  values(); controls.append(effect,value); section.append(controls, range, compare);
  return section;
}
function drawEditor() {
  const row = current(); $("detail").hidden = !row; $("placeholder").hidden = !!row;
  $("copy-id").textContent = row ? "#" + row.id : "";
  if (!row) { draft = []; return; }
  draft = Object.keys(groups).flatMap(group => row[group].map((o, slot) =>
    ({group, slot, option:o.OptionId, level:o.Level})));
  const spec = data.specs[row.spec];
  const portrait = image("/icon/" + row.spec + ".png");
  portrait.onerror = () => portrait.replaceWith(el("span", "fallback", spec.family.slice(0, 2)));
  $("portrait").replaceChildren(portrait);
  $("family").textContent = spec.family; $("name").textContent = spec.name; $("stars").textContent = "★".repeat(spec.stars);
  $("stars").setAttribute("aria-label", spec.stars + " stars");
  $("equipped").textContent = row.equipped ? "Yes" : "No";
  $("protection").textContent = row.locked ? "Locked" : "Unlocked";
  $("jewels").textContent = row.jewels;
  $("basic").parentElement.hidden = !row.main.length;
  for (const [group, layout] of Object.entries(groups)) {
    $(layout.container).replaceChildren(...draft.filter(e => e.group === group).map(e => slotEditor(row,e)));
  }
  const reason = row.pending ? "This relic has a pending in-game option change." : !row.bonus.length ? "This relic has no rolled sub-options." : "";
  $("unavailable").hidden = !reason; $("unavailable").textContent = reason;
  updateApplyButton();
}
function filter() {
  const search = $("search").value.trim().toLowerCase().replace(/^#(?=\d)/, ""), mode = $("show").value;
  visible = data.copies.filter(r => {
    const s = data.specs[r.spec];
    return (!family || family === s.family) && (mode !== "equipped" || r.equipped) &&
      (mode !== "imbued" || r.bonus.length) && (mode !== "empty" || !r.bonus.length) &&
      [r.id, r.spec, s.name, s.family].join(" ").toLowerCase().includes(search);
  }).sort((a,b) => data.specs[b.spec].stars - data.specs[a.spec].stars || a.id - b.id);
  const index = visible.findIndex(r => r.id === selected);
  if (index < 0) selected = visible[0]?.id;
  page = Math.floor(Math.max(index,0)/size);
  drawGrid(); drawEditor(); syncUrl();
}
async function load() {
  const response = await fetch(relicApi, {cache:"no-store"});
  if (!response.ok) throw new Error("Could not load your relics.");
  data = await response.json(); drawFamilies(); filter(); setAccess(data.writable);
}
function navigate(action) {
  action(); note();
}
$("tiles").onclick = e => {
  const btn = e.target.closest("button[data-id]"); if (!btn || selected === Number(btn.dataset.id)) return;
  navigate(() => {
    selected = Number(btn.dataset.id);
    for (const other of $("tiles").children) other.setAttribute("aria-pressed", String(other === btn));
    drawEditor(); syncUrl();
    if (matchMedia("(max-width:680px)").matches) document.querySelector(".inspector").scrollIntoView();
  });
};
for (const [id, step] of [["prev",-1],["next",1]]) $(id).onclick = () => navigate(() => {
  page += step; selected = visible[page*size].id; drawGrid(); drawEditor(); syncUrl();
});
$("types").onclick = e => {
  const btn = e.target.closest("button[data-type]"); if (btn) navigate(() => { family=btn.dataset.type; filter(); });
};
$("mobile-types").onchange = e => navigate(() => { family=e.target.value; filter(); });
$("search").oninput = $("show").onchange = () => { if (data) navigate(filter); };
$("editor").onsubmit = async e => {
  e.preventDefault();
  const changes = changedSlots(); if (saving || !writable || !changes.length) return;
  ++statusRequest;
  saving = true; document.querySelector(".workspace").inert = true; updateApplyButton();
  try {
    const id = selected;
    const response = await fetch(relicApi,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id, revision:data.revision, version:current().version, changes})});
    const result = await response.json();
    if (response.status === 423) setAccess(false);
    if (response.status === 409) await load();
    if (!response.ok) throw new Error(result.error || "Could not save these relic options.");
    try {
      await load(); note("Changes saved to relic #" + id + " in your game save.");
    } catch {
      setAccess(false, "Reload the editor to see the saved values.");
      note("Changes saved to relic #" + id + ". Reload to refresh its details.");
    }
  } catch (error) { note(error.message, true); }
  finally { saving = false; document.querySelector(".workspace").inert = false; if (current()) updateApplyButton(); }
};
watchGridPageSize($("tiles"), pageSize => {
  size = pageSize;
  if (!visible.length) return;
  page = Math.floor(Math.max(0, visible.findIndex(row => row.id === selected)) / size);
  drawGrid();
});
load().catch(error => { $("error").hidden = false; $("error").textContent = error.message; $("range").textContent = "Relics unavailable"; });
window.setInterval(checkAccess, 2500);
document.addEventListener("visibilitychange", checkAccess);
window.addEventListener("focus", checkAccess);
