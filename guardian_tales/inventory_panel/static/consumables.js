import { $, el, image } from "/inventory-dom.js";

const api = "/api/game/consumables";
const format = new Intl.NumberFormat("en-GB");
const query = new URLSearchParams(location.hash.slice(1));
let rows = [], selected = null, hasIcons = false, writable = false, saving = false, statusRequest = 0;
$("search").value = query.get("q") || "";

function art(item, container) {
  const fallback = () => container.replaceChildren(el("span", "fallback", item.name.split(/\s+/).slice(0,2).map(w => w[0]).join("")));
  if (!hasIcons) { fallback(); return; }
  const icon = image("/icon/" + item.spec + ".png");
  icon.onerror = fallback;
  container.replaceChildren(icon);
}

function setAccess(allowed, text = "Close Guardian Tales and stop the backend to apply quantity changes.") {
  writable = allowed === true;
  $("access").hidden = writable;
  if (!writable) $("access").textContent = text;
  updateForm();
}

async function checkAccess() {
  if (saving || document.hidden) return;
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

function updateForm() {
  const amount = $("quantity").valueAsNumber;
  const changed = selected && $("quantity").validity.valid && amount !== selected.amount;
  $("apply").disabled = !changed || !writable || saving;
  $("comparison").textContent = changed ? format.format(selected.amount) + " → " + format.format(amount) : "";
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
  $("message").hidden = true;
  if (item) {
    $("detail-name").textContent = item.name;
    $("category").textContent = item.category;
    $("owned").textContent = format.format(item.amount);
    $("quantity").max = item.maximum;
    $("quantity").value = item.amount;
    art(item, $("portrait"));
  }
  updateForm();
  syncUrl();
}

function draw() {
  const search = $("search").value.trim().replace(/^#(?=\d)/, "").toLowerCase();
  const group = $("filter").value;
  const visible = rows.filter(item => (!group || item.category === group) &&
    [item.name, item.id, item.spec].join(" ").toLowerCase().includes(search));
  if (selected && !visible.includes(selected)) showItem(null);
  const buttons = visible.map(item => {
    const button = el("button", "tile");
    button.type = "button";
    button.setAttribute("aria-pressed", String(item === selected));
    button.title = item.name + " · " + format.format(item.amount);
    button.setAttribute("aria-label",button.title);
    const wrap = el("span", "tile-art");
    art(item, wrap);
    const quantity = format.format(item.amount);
    const count = el("span", "stack-size", quantity);
    count.classList.toggle("long", quantity.length > 8);
    button.append(wrap, count);
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
  $("range").textContent = visible.length + (visible.length === 1 ? " stack" : " stacks");
  syncUrl();
}

async function load(id, group) {
  const response = await fetch(api, {cache:"no-store"});
  if (!response.ok) throw new Error("Could not load the consumable inventory.");
  const data = await response.json();
  rows = data.rows;
  hasIcons = data.hasIcons;
  const categories = [...new Set(rows.map(r => r.category))];
  $("filter").replaceChildren(new Option("All types",""), ...categories.map(c => new Option(c,c)));
  $("filter").value = categories.includes(group) ? group : "";
  ++statusRequest;
  setAccess(data.writable);
  showItem(rows.find(r => r.id === id) || null);
  draw();
}

$("quantity").oninput = () => { $("message").hidden = true; updateForm(); };
$("search").oninput = $("filter").onchange = draw;
$("editor").onsubmit = async event => {
  event.preventDefault();
  if ($("apply").disabled) return;
  const item = selected, amount = $("quantity").valueAsNumber;
  saving = true;
  ++statusRequest;
  document.querySelector(".workspace").inert = true;
  updateForm();
  try {
    const response = await fetch(api, {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:item.id, version:item.version, amount})});
    const result = await response.json();
    if (response.status === 423) setAccess(false);
    if (response.status === 409) await load(item.id, $("filter").value);
    if (!response.ok) throw new Error(result.error || "Could not save the quantity.");
    item.amount = result.amount;
    item.version = result.version;
    showItem(item); draw();
    $("message").textContent = "Quantity saved.";
    $("message").classList.remove("error");
  } catch (error) {
    $("message").textContent = error.message;
    $("message").classList.add("error");
    if (!selected) $("range").textContent = error.message;
  } finally {
    $("message").hidden = false;
    saving = false;
    document.querySelector(".workspace").inert = false;
    updateForm();
  }
};
load(Number(query.get("id")), query.get("type")).catch(error => { $("range").textContent = error.message; });
window.setInterval(checkAccess, 2500);
document.addEventListener("visibilitychange", checkAccess);
window.addEventListener("focus", checkAccess);
