import { $, el, image, inventoryTile, renderTypeFilters, selectTypeFilter, sizeItemSprite, watchGridPageSize } from "/inventory-dom.js";
import { bulkSelection } from "/bulk-selection.js";
import { itemCatalog } from "/catalog-picker.js";

let copies = [], visible = [], selected, rarity = "", page = 0, size = 24;
let version, limits = {}, writable = false, saving = false, accessRequest = 0;
const api = "/api/game/merch";
const bulk = bulkSelection({
  api, version: () => version, focusId: () => selected?.id, describe: row => row,
  onProtection(result) {
    version = result.inventoryVersion;
    filter(selected?.id);
  },
  reload: () => load(selected?.id),
});

function drawStars(target, row) {
  target.dataset.baseStars = row.kind;
  target.setAttribute("role", "img");
  target.setAttribute("aria-label", row.stars === 1 ? "1 star" : row.stars + " stars");
  target.replaceChildren(...Array.from({length: row.stars}, () => {
    const img = image("/type-icon/merch-star-" + row.kind + ".png");
    img.className = "merch-star";
    img.onerror = () => img.replaceWith(el("span", "merch-star", "★"));
    return img;
  }));
}

function drawArt(target, row) {
  target.dataset.baseStars = row.kind;
  target.replaceChildren(sprite(row));
}

function tile(row, pressed, idLabel) {
  const art = el("span", "tile-art");
  art.append(sprite(row));
  const card = inventoryTile({...row, idLabel, art, selected: pressed});
  card.dataset.baseStars = row.kind;
  card.classList.toggle("merch-equipped", !!row.equipped);
  if (row.level != null) card.querySelector(".tile-level").textContent = row.level;
  drawStars(card.querySelector(".tile-stars"), row);
  return card;
}

function note(text, error = false) {
  $("message").hidden = !text;
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
}

function updateMax() {
  const cap = limits[selected?.spec];
  const atMax = cap && selected.stars === cap.stars && selected.level === cap.level;
  $("upgrade").hidden = !cap;
  $("max-merch").disabled = !cap || atMax || !writable || saving || !version;
  $("max-merch").textContent = atMax ? "At maximum" : "Max merch";
  $("max-target").textContent = cap ? "Lv. " + cap.level + " · " + cap.stars + "★ · Free" : "";
}

function setAccess(allowed) {
  writable = allowed === true;
  $("access").hidden = writable;
  picker.setWritable(writable);
  bulk.setWritable(writable);
  updateMax();
}

async function checkAccess() {
  if (document.hidden || saving) return;
  const id = ++accessRequest;
  try {
    const res = await fetch("/api/game/status", {cache: "no-store", signal: AbortSignal.timeout(4000)});
    const status = res.ok && await res.json();
    if (id === accessRequest) setAccess(status.writable);
  } catch {
    if (id === accessRequest) setAccess(false);
  }
}

function sprite(row) {
  const img = image("/icon/" + row.spec + ".png");
  img.onload = () => sizeItemSprite(img, 0.8);
  img.onerror = () => img.replaceWith(el("span", "fallback", row.name.slice(0, 2)));
  return img;
}

function drawDetails() {
  $("detail").hidden = !selected;
  $("placeholder").hidden = !!selected;
  $("copy-id").textContent = selected ? "Copy #" + selected.id : "";
  updateMax();
  if (!selected) return;
  drawArt($("portrait"), selected);
  $("name").textContent = selected.name;
  $("level").textContent = selected.level == null ? "" : "Lv. " + selected.level;
  drawStars($("stars"), selected);
  $("equipped").textContent = selected.equipped ? (selected.hero || "Yes") : "No";
  $("protection").textContent = selected.locked ? "Locked" : "Unlocked";
  $("item-id").textContent = selected.spec;
}

function drawGrid() {
  const start = page * size, end = Math.min(start + size, visible.length);
  const rows = visible.slice(start, end);
  $("tiles").replaceChildren(...rows.map(row => tile(row, row === selected)));
  bulk.page(rows);
  $("empty").hidden = !!visible.length;
  $("empty").textContent = copies.length ? "No merch matches these filters." : "You have no merch yet.";
  $("range").textContent = visible.length ? (start + 1) + "–" + end + " of " + visible.length : "0 items";
  $("prev").disabled = page === 0;
  $("next").disabled = end >= visible.length;
}

function filter(focusId) {
  const query = $("search").value.trim().toLowerCase(), show = $("show").value;
  visible = copies.filter(row =>
    (!rarity || String(row.stars) === rarity) &&
    (show === "all" || (show === "unlocked" ? !row.locked : row[show])) &&
    (!query || row.name.toLowerCase().includes(query) ||
      String(row.id).includes(query) || String(row.spec).includes(query))
  );
  const index = Math.max(0, visible.findIndex(row => row.id === focusId));
  page = Math.floor(index / size);
  selected = visible[index];
  selectTypeFilter($("types"), $("mobile-types"), rarity);
  drawGrid();
  drawDetails();
}

function setRarity(value) {
  rarity = value;
  filter();
}
$("types").onclick = event => {
  const button = event.target.closest("button[data-type]");
  if (button) setRarity(button.dataset.type);
};
$("mobile-types").onchange = event => setRarity(event.target.value);
$("search").oninput = $("show").onchange = () => filter();
$("tiles").onclick = event => {
  const button = event.target.closest("button[data-id]");
  if (!button || bulk.toggle(Number(button.dataset.id))) return;
  selected = visible.find(row => row.id === Number(button.dataset.id));
  for (const tile of $("tiles").children) tile.setAttribute("aria-pressed", String(tile === button));
  drawDetails();
  if (matchMedia("(max-width:680px)").matches) document.querySelector(".inspector").scrollIntoView();
};
for (const [id, step] of [["prev", -1], ["next", 1]]) {
  $(id).onclick = () => {
    page += step;
    selected = visible[page * size];
    drawGrid();
    drawDetails();
  };
}
watchGridPageSize($("tiles"), pageSize => {
  size = pageSize;
  if (visible.length) {
    page = Math.floor(visible.indexOf(selected) / size);
    drawGrid();
  }
});

async function load(focusId) {
  const response = await fetch(api, {cache: "no-store"});
  if (!response.ok) throw new Error("Could not load merch from the game save.");
  const data = await response.json();
  bulk.reset();
  version = data.version;
  limits = data.limits;
  ++accessRequest;
  setAccess(data.writable);
  copies = data.copies.sort((a, b) => b.stars - a.stars || b.level - a.level ||
    a.name.localeCompare(b.name) || a.id - b.id);
  const counts = new Map();
  for (const row of copies) counts.set(row.stars, (counts.get(row.stars) || 0) + 1);
  if (rarity && !counts.has(Number(rarity))) rarity = "";
  renderTypeFilters($("types"), $("mobile-types"), [
    {key: "", name: "All rarities", count: copies.length, iconUrl: "/type-icon/all.png"},
    ...Array.from(counts, ([stars, count]) => ({
      key: String(stars), name: stars === 1 ? "1 star" : stars + " stars", count,
    })),
  ]);
  filter(focusId);
  $("open-merch-catalog").disabled = false;
  $("error").hidden = true;
}

async function showSaved(id, message) {
  rarity = "";
  $("search").value = "";
  $("show").value = "all";
  try {
    await load(id);
    note(message);
  } catch {
    version = null;
    updateMax();
    note(message + " Reload Merch to refresh the inventory.", true);
  }
}

const picker = itemCatalog({
  section: "merch", types: new Map([["1", "1★ base"], ["2", "2★ base"], ["3", "3★ base"]]), tile,
  drawArt, drawStars,
  onAdded: (id, item) => showSaved(id, item.name + " added to inventory."),
});
$("open-merch-catalog").onclick = () => picker.open(null, writable);
$("max-merch").onclick = async () => {
  if ($("max-merch").disabled) return;
  const {id, spec, name} = selected;
  saving = true;
  ++accessRequest;
  document.querySelector(".workspace").inert = true;
  updateMax();
  try {
    const res = await fetch(api + "/max", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id, spec, version})});
    const result = await res.json();
    if (!res.ok) {
      if (res.status === 409) await load(id);
      if (res.status === 423) setAccess(false);
      throw new Error(result.error || "Could not upgrade this merch.");
    }
    await showSaved(id, name + " is now at its maximum.");
  } catch (error) {
    note(error.message, true);
  } finally {
    saving = false;
    document.querySelector(".workspace").inert = false;
    updateMax();
  }
};
load().catch(error => {
  $("error").textContent = error.message;
  $("error").hidden = false;
  $("range").textContent = "Merch unavailable";
});
window.setInterval(checkAccess, 2500);
window.addEventListener("focus", checkAccess);
document.addEventListener("visibilitychange", checkAccess);
