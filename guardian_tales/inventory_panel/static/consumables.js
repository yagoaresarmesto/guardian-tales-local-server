import { $, el, image, inventoryTile, renderTypeFilters, selectTypeFilter, sizeItemSprite, watchGridPageSize } from "/inventory-dom.js";

import { quantityEditor, quantityFormat as format } from "/quantity-editor.js";

const api = "/api/game/consumables";
const query = new URLSearchParams(location.hash.slice(1));
let visible = [], page = 0, pageSize = 24;
let rows = [], selected = null, hasIcons = false, statusRequest = 0;
$("search").value = query.get("q") || "";

const editor = quantityEditor($("editor"), {
  api, accessId: "access",
  lock: () => { ++statusRequest; setAccess(false); },
  reload: () => load(selected?.id, $("filter").value),
  saved: item => { showItem(item); drawGrid(); },
});

function art(item, container) {
  const fallback = () => el("span", "fallback", item.name.split(/\s+/).slice(0,2).map(w => w[0]).join(""));
  if (!hasIcons) { container.replaceChildren(fallback()); return; }
  const icon = image("/icon/" + item.spec + ".png");
  icon.onload = () => sizeItemSprite(icon, 0.8);
  icon.onerror = () => icon.replaceWith(fallback());
  container.replaceChildren(icon);
}

function setAccess(allowed, text = "Close Guardian Tales and stop the backend to apply quantity changes.") {
  const writable = allowed === true;
  $("access").hidden = writable;
  if (!writable) $("access").textContent = text;
  editor.setWritable(writable);
}

async function checkAccess() {
  if (editor.saving || document.hidden) return;
  const request = ++statusRequest;
  try {
    const response = await fetch("/api/game/status", {cache:"no-store", signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error();
    const access = await response.json();
    if (request === statusRequest) setAccess(access.writable);
  } catch {
    if (request === statusRequest) setAccess(false, "Reconnect to the local save editor to apply changes.");
  }
}

function syncUrl() {
  const params = new URLSearchParams();
  if (selected) params.set("id", selected.id);
  if ($("search").value) params.set("q", $("search").value);
  if ($("filter").value) params.set("type", $("filter").value);
  history.replaceState(null, "", location.pathname + (params.size ? "#" + params : ""));
}

function showItem(item) {
  selected = item;
  $("detail").hidden = !item;
  $("placeholder").hidden = !!item;
  $("copy-id").textContent = item ? "#" + item.id : "";
  editor.select(item);
  if (item) {
    $("detail-name").textContent = item.name;
    $("category").textContent = item.category;
    $("catalog-id").textContent = item.spec;
    $("owned").textContent = format.format(item.amount);
    art(item, $("portrait"));
  }
  syncUrl();
}

function filter() {
  const search = $("search").value.trim().replace(/^#(?=\d)/, "").toLowerCase();
  const group = $("filter").value;
  visible = rows.filter(item => (!group || item.category === group) &&
    [item.name, item.id, item.spec].join(" ").toLowerCase().includes(search));
  if (!selected || !visible.includes(selected)) showItem(visible[0] || null);
  page = Math.floor(Math.max(0, visible.indexOf(selected)) / pageSize);
  selectTypeFilter($("types"), $("filter"), group);
  drawGrid();
  syncUrl();
}

function drawGrid() {
  const start = page * pageSize;
  const buttons = visible.slice(start, start + pageSize).map(item => {
    const wrap = el("span", "tile-art");
    art(item, wrap);
    const button = inventoryTile({ id: item.id, name: item.name, art: wrap,
      selected: item === selected, quantity: format.format(item.amount) });
    button.onclick = () => {
      if (item !== selected) {
        $("tiles").querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed","false");
        button.setAttribute("aria-pressed","true");
        showItem(item);
      }
      if (matchMedia("(max-width:680px)").matches) document.querySelector(".inspector").scrollIntoView();
    };
    return button;
  });
  $("tiles").replaceChildren(...buttons);
  $("empty").hidden = !!visible.length;
  const end = Math.min(start + pageSize, visible.length);
  $("range").textContent = visible.length
    ? (start + 1) + "–" + end + " of " + visible.length + (visible.length === 1 ? " stack" : " stacks")
    : "0 stacks";
  $("prev").disabled = page === 0;
  $("next").disabled = end >= visible.length;
}

async function load(id, group) {
  const response = await fetch(api, {cache:"no-store"});
  if (!response.ok) throw new Error("Could not load the consumable inventory.");
  const data = await response.json();
  rows = data.rows;
  hasIcons = data.hasIcons;
  const categories = new Map();
  for (const item of rows) {
    if (!categories.has(item.category)) {
      categories.set(item.category, {key: item.category, name: item.category, count: 0,
        iconUrl: hasIcons ? "/icon/" + item.spec + ".png" : null});
    }
    categories.get(item.category).count++;
  }
  renderTypeFilters($("types"), $("filter"), [
    {key: "", name: "All types", count: rows.length, iconUrl: "/type-icon/all.png"},
    ...categories.values(),
  ]);
  $("filter").value = categories.has(group) ? group : "";
  ++statusRequest;
  setAccess(data.writable);
  showItem(rows.find(r => r.id === id) || null);
  filter();
}

$("search").oninput = $("filter").onchange = filter;
$("types").onclick = event => {
  const button = event.target.closest("button[data-type]");
  if (button) { $("filter").value = button.dataset.type; filter(); }
};
for (const [id, step] of [["prev", -1], ["next", 1]]) {
  $(id).onclick = () => {
    page += step;
    showItem(visible[page * pageSize]);
    drawGrid();
  };
}
watchGridPageSize($("tiles"), size => {
  pageSize = size;
  page = Math.floor(Math.max(0, visible.indexOf(selected)) / pageSize);
  if (visible.length) drawGrid();
});
load(Number(query.get("id")), query.get("type")).catch(error => { $("range").textContent = error.message; });
window.setInterval(checkAccess, 2500);
document.addEventListener("visibilitychange", checkAccess);
window.addEventListener("focus", checkAccess);
