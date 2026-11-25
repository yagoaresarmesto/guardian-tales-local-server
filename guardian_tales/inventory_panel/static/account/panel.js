import { $, el } from "/inventory-dom.js";

const api = "/api/game/account";
const number = new Intl.NumberFormat("en-GB");
const controls = new Map();
const materialPickers = {
  "Hero Evolution Stones": {
    id: "evolution-stone-picker", label: "Evolution stone", all: "All evolution stones",
    region: "Evolution stone balances",
  },
  "Hero Myth Stones": {
    id: "myth-stone-picker", label: "Myth hero", all: "All heroes", region: "Myth stone balances",
  },
  "Purple Coins": {
    id: "purple-coin-picker", label: "World", all: "All worlds", region: "Purple Coin balances by world",
  },
};
let account, writable = false, saving = false, stale = false, statusRequest = 0;
let groupsBeforeSearch = null;

function tagValue() {
  return $("tag").value.replace(/^#/, "").toUpperCase();
}

function update() {
  if (!account) return;
  const name = $("name").value, rawTag = $("tag").value;
  const tag = rawTag === account.tag ? rawTag : tagValue();
  const validName = name === account.name || (name.length >= 2 && name.length <= 10 && !/[\x00-\x1f\x7f]/.test(name));
  const validTag = rawTag === account.tag || /^#?[a-zA-Z0-9]{5}$/.test(rawTag);
  $("name").setAttribute("aria-invalid", String(!validName));
  $("tag").setAttribute("aria-invalid", String(!validTag));
  const identityChanged = name !== account.name || tag !== account.tag;
  const preview = $("identity-preview");
  preview.hidden = !identityChanged;
  preview.textContent = !validName ? "Enter a valid nickname." : !validTag ? "Enter five letters or digits." : "After applying: " + name + "#" + tag;
  let valid = validName && validTag;
  let changeCount = Number(name !== account.name) + Number(tag !== account.tag);
  const materialEdits = [];
  for (const {item, input, result, note, setTotal, row} of controls.values()) {
    const ok = input.disabled || input.validity.valid;
    const total = setTotal ? (input.value === "" ? item.balance : input.valueAsNumber)
      : item.balance + (input.disabled ? 0 : input.valueAsNumber);
    input.setAttribute("aria-invalid", String(!ok));
    result.textContent = ok ? number.format(total) : "—";
    result.classList.toggle("changed", ok && total !== item.balance);
    note.hidden = ok && item.limit !== null;
    note.textContent = item.limit === null ? "Import the stamina purchase catalog to add reserve coffee."
      : "Enter a whole amount between 0 and " + number.format(Number(input.max)) + ".";
    valid &&= ok;
    const edited = !ok || total !== item.balance;
    row.toggleAttribute("data-edited", edited);
    if (edited) changeCount++;
    if (item.key.startsWith("material-") && edited) {
      materialEdits.push(item.label + " → " + (ok ? number.format(total) : "check amount"));
    }
  }
  $("material-edits").hidden = !materialEdits.length;
  $("material-edits").textContent = materialEdits.length ? "Pending: " + materialEdits.join(" · ") : "";
  $("change-count").textContent = changeCount ? changeCount + " pending change" + (changeCount === 1 ? "" : "s") : "No pending changes";
  $("change-count").classList.toggle("changed", changeCount > 0);
  $("apply").disabled = !changeCount || !valid || !account.ready || !writable || saving || stale;
}

function access(allowed, message = "Close Guardian Tales and stop the backend to enable Apply.") {
  writable = allowed === true;
  const notice = $("access");
  notice.hidden = writable && account.ready;
  notice.textContent = account.ready ? message : "Complete the prologue or import an account before editing.";
  update();
}

async function checkAccess() {
  if (!account || saving || document.hidden) return;
  const request = ++statusRequest;
  try {
    const response = await fetch("/api/game/status", {cache: "no-store", signal: AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error();
    const status = await response.json();
    if (request === statusRequest) access(status.writable);
  } catch {
    if (request === statusRequest) access(false, "Cannot verify save access. Reconnect to enable Apply.");
  }
}

function balanceColumns(action) {
  const columns = el("div", "balance-columns");
  columns.setAttribute("aria-hidden", "true");
  for (const title of ["Resource", "Saved", action, "After applying"]) columns.append(el("span", "", title));
  return columns;
}

function balanceRow(item, setTotal) {
  const row = el("div", "wallet-row");
  const identity = el("div", "wallet-item"), icon = el("img");
  icon.alt = "";
  icon.loading = "lazy";
  icon.onerror = () => icon.remove();
  icon.src = "/icon/" + item.id + ".png";
  const detail = el("div");
  detail.append(el("strong", "", item.choice || item.label));
  if (item.limit !== null) detail.append(el("small", "", "Max " + number.format(item.limit)));
  identity.append(icon, detail);
  const saved = el("div", "wallet-saved");
  saved.append(el("span", "compact-label", "Saved"), el("span", "", number.format(item.balance)));
  const action = setTotal ? "Set total" : "Add";
  const field = el("div", "wallet-input"), label = el("label", "compact-label", action), input = el("input");
  input.id = (setTotal ? "set-" : "add-") + item.key; label.htmlFor = input.id;
  input.type = "number"; input.inputMode = "numeric"; input.required = !setTotal;
  input.min = 0; input.step = 1;
  input.max = setTotal ? item.limit : Math.max(0, item.limit - item.balance);
  input.value = setTotal ? (item.balance <= item.limit ? item.balance : "") : 0;
  input.placeholder = String(item.balance);
  input.disabled = !setTotal && Number(input.max) === 0;
  input.setAttribute("aria-label", setTotal ? item.label + " total" : "Add " + item.label.toLowerCase());
  const note = el("p", "field-note");
  note.id = input.id + "-note"; input.setAttribute("aria-describedby", note.id);
  const after = el("div", "wallet-result"), result = el("strong");
  after.append(el("span", "compact-label", "After applying"), result);
  field.append(label, input);
  row.append(identity, saved, field, after, note);
  if (item.key.startsWith("material-")) {
    row.dataset.search = [item.label, item.group, item.choice, ...(item.searchAliases || [])].filter(Boolean).join(" ").toLowerCase();
    row.dataset.material = item.key;
  }
  controls.set(item.key, {item, input, result, note, setTotal, row});
  return row;
}

function expandedGroups() {
  return new Set(Array.from($("material-groups").querySelectorAll("details[open]"), node => node.dataset.group));
}

function filterBalances(container, words, selectedKey = "") {
  let count = 0;
  for (const row of container.querySelectorAll("[data-material]")) {
    const matches = (!selectedKey || row.dataset.material === selectedKey)
      && words.every(word => row.dataset.search.includes(word));
    row.hidden = !matches;
    if (matches) count++;
  }
  return count;
}

function filterMaterials() {
  const words = $("material-search").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length && !groupsBeforeSearch) groupsBeforeSearch = expandedGroups();
  const groups = $("material-groups");
  for (const group of groups.children) {
    const picker = group.querySelector(".material-picker select");
    if (picker) picker.parentElement.hidden = words.length > 0;
    const count = filterBalances(group, words, words.length ? "" : picker?.value);
    group.hidden = !count;
    group.querySelector("summary small").textContent = number.format(count);
    if (words.length) group.open = count > 0;
    else if (groupsBeforeSearch) group.open = groupsBeforeSearch.has(group.dataset.group);
  }
  if (!words.length) groupsBeforeSearch = null;
  const common = $("common-materials");
  common.hidden = !filterBalances(common, words);
  groups.hidden = !groups.querySelector("details:not([hidden])");
  $("material-empty").hidden = !(common.hidden && groups.hidden);
}

function materialPicker(config, entries, previous) {
  const field = el("div", "material-picker");
  const label = el("label", "", config.label);
  const select = el("select");
  select.id = config.id;
  label.htmlFor = select.id;
  select.add(new Option(config.all, ""));
  for (const item of entries) select.add(new Option(item.choice, item.key, false, item.key === previous));
  field.append(label, select);
  return field;
}

function renderMaterials(items) {
  const container = $("material-groups");
  const expanded = groupsBeforeSearch || expandedGroups();
  const previousSelections = new Map();
  for (const picker of container.querySelectorAll(".material-picker select")) {
    previousSelections.set(picker.id, picker.value);
  }
  const compare = new Intl.Collator("en", {numeric: true}).compare;
  const groups = new Map();
  const common = [];
  for (const item of items) {
    // An already running game backend can still serve the previous Account catalog.
    if (item.catalogOnly) continue;
    if (!item.group) {
      common.push(item);
      continue;
    }
    if (!groups.has(item.group)) groups.set(item.group, []);
    groups.get(item.group).push(item);
  }
  $("materials-section").hidden = !items.length;
  common.sort((a, b) => compare(a.label, b.label));
  $("common-materials").replaceChildren(balanceColumns("Set total"), ...common.map(item => balanceRow(item, true)));
  container.replaceChildren();
  for (const group of Array.from(groups.keys()).sort(compare)) {
    const entries = groups.get(group);
    entries.sort((a, b) => Number(b.preferred) - Number(a.preferred) || compare(a.choice, b.choice));
    const section = el("details", "material-group");
    section.dataset.group = group;
    section.open = expanded.has(group);
    const summary = el("summary", "", group);
    summary.append(el("small", "", number.format(entries.length)));
    const list = el("div", "balance-list");
    list.append(balanceColumns("Set total"), ...entries.map(item => balanceRow(item, true)));
    section.append(summary);
    const config = materialPickers[group];
    if (config) {
      section.append(materialPicker(config, entries, previousSelections.get(config.id)));
      list.classList.add("material-balance-list");
      list.tabIndex = 0;
      list.setAttribute("role", "region");
      list.setAttribute("aria-label", config.region);
    }
    section.append(list);
    container.append(section);
  }
  filterMaterials();
}

function render(data) {
  account = data;
  $("name").value = data.name;
  $("tag").value = data.tag;
  $("saved-identity").textContent = data.name + "#" + data.tag;
  controls.clear();
  $("wallet").replaceChildren(balanceColumns("Add"), ...data.wallet.map(item => balanceRow(item, false)));
  const summoning = data.summoning || [];
  $("summoning").replaceChildren(balanceColumns("Set total"), ...summoning.map(item => balanceRow(item, true)));
  $("summoning-section").hidden = !summoning.length;
  renderMaterials(data.materials || []);
  $("reload").hidden = true;
  stale = false;
  access(data.writable);
}

async function load() {
  ++statusRequest; account = null;
  $("account-form").hidden = true;
  $("loading").hidden = false; $("loading").textContent = "Loading account…";
  try {
    const response = await fetch(api, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Cannot load the account.");
    render(data);
    $("message").textContent = "";
    $("loading").hidden = true; $("account-form").hidden = false;
  } catch (error) {
    $("loading").textContent = error.message;
  }
}

$("account-form").oninput = event => {
  if (event.target === $("material-search") || event.target.matches(".material-picker select")) {
    filterMaterials();
    const scope = event.target.closest(".material-group") || $("materials");
    for (const list of scope.querySelectorAll(".material-balance-list")) list.scrollTop = 0;
    return;
  }
  if (!stale) $("message").textContent = "";
  update();
};
$("material-search").onkeydown = event => {
  if (event.key === "Enter") event.preventDefault();
};
$("reload").onclick = load;
$("account-form").onsubmit = async event => {
  event.preventDefault();
  if ($("apply").disabled) return;
  const add = {}, set = {};
  for (const [key, {item, input, setTotal}] of controls) {
    if (input.disabled || input.value === "") continue;
    if (setTotal) {
      if (input.valueAsNumber !== item.balance) set[key] = input.valueAsNumber;
    } else if (input.valueAsNumber > 0) add[key] = input.valueAsNumber;
  }
  const body = {version: account.version, name: $("name").value,
    tag: $("tag").value === account.tag ? account.tag : tagValue(), add};
  if (Object.keys(set).length) body.set = set;
  saving = true; ++statusRequest;
  $("account-form").inert = true; update();
  try {
    const response = await fetch(api, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json();
    if (response.status === 423) access(false);
    if (response.status === 409) { stale = true; $("reload").hidden = false; }
    if (!response.ok) throw new Error(data.error || "Could not apply the changes.");
    render({...data, ready: account.ready, writable});
    $("message").textContent = "Account changes saved.";
  } catch (error) {
    $("message").textContent = error.message;
  } finally {
    saving = false; $("account-form").inert = false; update();
    checkAccess();
  }
};

load();
window.setInterval(checkAccess, 2500);
window.addEventListener("focus", checkAccess);
document.addEventListener("visibilitychange", checkAccess);
