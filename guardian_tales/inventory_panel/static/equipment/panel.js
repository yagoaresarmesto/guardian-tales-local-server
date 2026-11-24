import { $, el, image, inventoryTile, renderTypeFilters, selectTypeFilter, sizeItemSprite, watchGridPageSize } from "/inventory-dom.js";
import { equipmentOptions, showLimitBreakFact } from "/equipment-options.js";
import { quantityEditor, quantityFormat } from "/quantity-editor.js";

const preview = location.pathname === "/equipment/preview";
const hammerEditor = preview ? null : quantityEditor($("hammer-editor"), {
  api: "/api/game/equipment/hammers", accessId: "equipment-access",
  lock: () => editor.lock(), reload: load, saved: () => draw(),
});
const editor = preview ? null : equipmentOptions(load, hammerEditor.setWritable);
document.body.classList.toggle("live-equipment", !preview);
if (preview) {
  document.querySelector(".context").textContent = "Save preview";
  document.querySelector(".temporary").textContent = "Temporary save copy";
  $("end").hidden = false;
  $("preview-link").textContent = "Game save editor";
  $("preview-link").href = "/equipment";
}
const types = new Map(Object.entries({
  onehandsword: "One-Handed Sword", twohandsword: "Two-Handed Sword", assaultrifle: "Rifle",
  bow: "Bow", basket: "Basket", staff: "Staff", gauntlet: "Gauntlet",
  claw: "Claw", shield: "Shield", accessory: "Accessory",
}));
const typeName = key => types.get(key) || key || "Other equipment";
const params = new URLSearchParams(location.hash.slice(1));
// Old necklace bookmarks carry the inventory copy ID as a bare fragment.
const initialSearch = new URLSearchParams(location.search).get("q");
if (initialSearch && /^#\d+$/.test(location.hash)) {
  params.set("id", location.hash.slice(1));
}
let pageSize = 24;
const collator = new Intl.Collator("en", {numeric: true, sensitivity: "base"});
let items = [], hammers = [], visible = [], page = 0, revision, hasIcons = false, saving = false;
let kind = params.get("type") || "all", selected = Number(params.get("id")) || null;
$("search").value = params.get("q") || initialSearch || "";
if (["rating", "name", "id"].includes(params.get("sort"))) $("sort").value = params.get("sort");

function art(item, className) {
  const wrap = el("span", className);
  const fallback = el("span", "fallback", item.name.split(/\s+/u).slice(0, 2).map(w => w[0]).join("").toUpperCase());
  wrap.append(fallback);
  if (hasIcons) {
    const img = image("/icon/" + item.spec + ".png");
    img.hidden = true;
    img.onload = () => {
      if (types.has(item.kind)) sizeItemSprite(img);
      fallback.hidden = true;
      img.hidden = false;
    };
    img.onerror = () => img.remove();
    wrap.append(img);
  }
  return wrap;
}
function note(text = "", error = false) {
  $("message").hidden = !text;
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
}
function updateUrl() {
  const query = new URLSearchParams();
  if (selected) query.set("id", selected);
  if (kind !== "all") query.set("type", kind);
  if ($("search").value) query.set("q", $("search").value);
  if ($("sort").value !== "level") query.set("sort", $("sort").value);
  history.replaceState(null, "", location.pathname + (query.size ? "#" + query : ""));
}
function applyType(value) {
  if ((kind === "enhance") !== (value === "enhance")) $("search").value = "";
  kind = value;
  note();
  filter();
}
function drawTypes() {
  const counts = new Map();
  for (const item of items) counts.set(item.kind, (counts.get(item.kind) || 0) + 1);
  const keys = ["all", ...Array.from(types.keys()).filter(key => counts.has(key)),
    ...Array.from(counts.keys()).filter(key => !types.has(key))];
  const filters = keys.map(key => ({
    key, name: key === "all" ? "All types" : typeName(key),
    count: key === "all" ? items.length : counts.get(key),
    iconUrl: "/type-icon/" + (types.has(key) ? key : "all") + ".png",
  }));
  if (!preview) filters.push({
    key: "enhance", name: "Enhance", count: hammers.length,
    iconUrl: hammers.length && hasIcons ? "/icon/" + hammers[0].spec + ".png" : null,
  });
  if (!filters.some(f => f.key === kind)) kind = "all";
  renderTypeFilters($("types"), $("mobile-types"), filters);
}
function stars(item) {
  return item.stars >= 1 && item.stars <= 6 ? "★".repeat(item.stars) : "";
}
function tile(item) {
  const button = inventoryTile({ ...item, art: art(item, "tile-art"), selected: item.id === selected,
    quantity: item.kind === "enhance" ? quantityFormat.format(item.amount) : null });
  button.dataset.grade = item.grade ?? "";
  return button;
}
function fact(label, value) {
  const row = el("div", "fact");
  row.append(el("dt", "", label), el("dd", "", value));
  return row;
}
function drawDetails() {
  const item = visible.find(row => row.id === selected);
  $("detail").hidden = !item; $("placeholder").hidden = !!item;
  $("copy-id").textContent = item ? "#" + item.id : "";
  const enhance = kind === "enhance";
  $("details-heading").textContent = enhance ? "Hammer details" : "Equipment details";
  $("collection-heading").textContent = enhance ? "Enhance" : "Equipment";
  $("empty").textContent = enhance ? "No owned hammers match these filters." : "No equipment matches these filters.";
  $("placeholder").querySelector("p").textContent = enhance ? "Select a hammer to see its quantity." : "Select equipment to see its details.";
  $("tiles").setAttribute("aria-label", enhance ? "Owned hammer stacks" : "Equipment copies");
  $("preview-link").hidden = enhance;
  editor?.select(enhance ? null : item);
  hammerEditor?.select(enhance ? item : null);
  if (!item) return;
  $("hero-art").replaceChildren(...art(item, "").childNodes);
  $("hero-stars").textContent = stars(item);
  $("hero-stars").setAttribute("aria-label", item.stars ? item.stars + " stars" : "Star rating unavailable");
  $("detail-type").textContent = enhance ? item.rarityName : typeName(item.kind);
  $("detail-level").textContent = item.level != null ? "Lv. " + item.level : "";
  $("detail-name").textContent = item.name;
  if (enhance) {
    $("facts").replaceChildren(fact("Catalog ID", item.spec), fact("Owned", quantityFormat.format(item.amount)),
      fact("Protection", item.locked ? "Locked" : "Unlocked"));
    if (item.enhanceExp != null) $("facts").append(fact("EXP per hammer", quantityFormat.format(item.enhanceExp)));
    return;
  }
  $("facts").replaceChildren(
    fact("Catalog ID", item.spec), ...(showLimitBreakFact(item) ? [fact("Limit breaks", item.breaks)] : []),
    fact("Equipped", item.equipped ? "Yes" : "No"),
    fact("Protection", item.locked ? "Locked" : "Unlocked"),
  );
  if (preview && item.original !== item.locked) $("facts").append(fact("Original protection", item.original ? "Locked" : "Unlocked"));
  if (item.training) $("facts").append(fact("Training room", "In session"));
  $("lock").textContent = item.locked ? "Unlock in preview" : "Lock in preview";
  $("lock").hidden = !preview;
  $("lock").disabled = saving;
  if (!preview) $("preview-link").href="/equipment/preview#id=" + item.id;
}
function draw() {
  const start = page * pageSize;
  $("tiles").replaceChildren(...visible.slice(start, start + pageSize).map(tile));
  $("empty").hidden = !!visible.length;
  $("range").textContent = visible.length
    ? (start + 1) + "–" + Math.min(start + pageSize, visible.length) + " of " + visible.length + " items"
    : "0 items";
  $("previous").disabled = page === 0; $("next").disabled = start + pageSize >= visible.length;
  selectTypeFilter($("types"), $("mobile-types"), kind);
  drawDetails(); updateUrl();
}
function filter() {
  const search = $("search").value.trim().toLowerCase().replace(/^#(?=\d)/, "");
  const order = $("sort").value;
  const inventory = kind === "enhance" ? hammers : items;
  visible = inventory.filter(item => (kind === "all" || item.kind === kind) && (!search ||
    [item.name, item.key, typeName(item.kind), item.rarityName, item.level, item.id, item.spec].join(" ").toLowerCase().includes(search)));
  visible.sort((a, b) => {
    if (order === "name") return collator.compare(a.name, b.name) || a.id - b.id;
    if (order === "id") return a.id - b.id;
    const levels = (b.level ?? -1) - (a.level ?? -1), ratings = (b.stars ?? -1) - (a.stars ?? -1);
    return (order === "level" ? levels || ratings : ratings || levels) || (b.grade ?? -1) - (a.grade ?? -1) || a.id - b.id;
  });
  const index = visible.findIndex(row => row.id === selected);
  if (index < 0) selected = visible[0]?.id ?? null;
  page = Math.floor(Math.max(0, index) / pageSize);
  draw();
}
async function load() {
  const res = await fetch(preview ? "/api/inventory" : "/api/game/equipment", {cache: "no-store"});
  if (!res.ok) throw new Error("Could not load the equipment inventory.");
  const data = await res.json();
  revision = data.revision; hasIcons = data.hasIcons;
  items = preview ? data.rows.filter(item => item.group === "Equipment") : data.rows;
  hammers = data.hammers ?? [];
  editor?.load(data);
  drawTypes(); filter();
}
function paginate(delta) {
  page += delta;
  selected = visible[page * pageSize]?.id ?? null;
  note(); draw();
}
$("previous").onclick = () => paginate(-1);
$("next").onclick = () => paginate(1);
$("search").oninput = () => { note(); filter(); };
$("sort").onchange = () => { note(); filter(); };
window.addEventListener("hashchange", () => {
  const query = new URLSearchParams(location.hash.slice(1));
  selected = Number(query.get("id")) || null;
  kind = query.get("type") || "all";
  $("search").value = query.get("q") || "";
  $("sort").value = ["rating","name","id"].includes(query.get("sort")) ? query.get("sort") : "level";
  if (items.length || hammers.length) { drawTypes(); filter(); }
});
$("types").onclick = e => {
  const btn = e.target.closest("button[data-type]");
  if (btn) applyType(btn.dataset.type);
};
$("mobile-types").onchange = e => applyType(e.target.value);
$("tiles").onclick = e => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  selected = Number(btn.dataset.id);
  for (const other of $("tiles").children) other.setAttribute("aria-pressed", String(other === btn));
  note(); drawDetails(); updateUrl();
  if (matchMedia("(max-width:680px)").matches) document.querySelector(".inspector").scrollIntoView({block: "start"});
};
$("lock").onclick = async () => {
  if (saving) return;
  const item = visible.find(row => row.id === selected);
  if (!item) return;
  saving = true; $("lock").disabled = true;
  try {
    const res = await fetch("/api/lock", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: item.id, locked: !item.locked, revision})});
    const result = await res.json();
    if (res.status === 409) await load();
    if (!res.ok) throw new Error(result.error || "Could not change protection.");
    await load();
    note("Copy #" + item.id + (item.locked ? " unlocked" : " locked") + " in the preview.");
  } catch (error) { note(error.message, true); }
  finally { saving = false; $("lock").disabled = false; }
};
$("end").onclick = async () => {
  if (!confirm("Close this preview and discard its temporary changes?")) return;
  try {
    const res = await fetch("/api/close", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
    if (!res.ok) throw new Error("Could not close the preview.");
    $("workspace").hidden = true; $("end").disabled = true;
    note("Preview closed. Launch it again to start a fresh session.");
  } catch (error) { note(error.message, true); }
};
watchGridPageSize($("tiles"), size => {
  pageSize = size;
  if (!visible.length) return;
  page = Math.floor(Math.max(0, visible.findIndex(row => row.id === selected)) / size);
  draw();
});
load().catch(error => note(error.message, true));
