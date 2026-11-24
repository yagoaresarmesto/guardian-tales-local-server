import { $, el, image } from "/inventory-dom.js";

const api = "/api/game/account";
const number = new Intl.NumberFormat("en-GB");
const controls = new Map();
let account, writable = false, saving = false, stale = false, statusRequest = 0;

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
  let valid = validName && validTag, changed = identityChanged;
  for (const {item, input, result, note} of controls.values()) {
    const add = input.valueAsNumber, ok = input.disabled || input.validity.valid;
    const total = item.balance + (input.disabled ? 0 : add);
    input.setAttribute("aria-invalid", String(!ok));
    result.textContent = ok ? number.format(total) : "—";
    result.classList.toggle("changed", ok && total !== item.balance);
    note.hidden = ok && item.limit !== null;
    note.textContent = item.limit === null ? "Import the stamina purchase catalog to add reserve coffee."
      : "Enter a whole amount between 0 and " + number.format(Number(input.max)) + ".";
    valid &&= ok;
    changed ||= ok && total !== item.balance;
  }
  $("apply").disabled = !changed || !valid || !account.ready || !writable || saving || stale;
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

function render(data) {
  account = data;
  $("name").value = data.name;
  $("tag").value = data.tag;
  $("saved-identity").textContent = data.name + "#" + data.tag;
  controls.clear();
  const wallet = $("wallet");
  wallet.replaceChildren();
  for (const item of data.wallet) {
    const row = el("div", "wallet-row");
    const identity = el("div", "wallet-item"), icon = image("/icon/" + item.id + ".png");
    icon.onerror = () => icon.remove();
    const detail = el("div");
    detail.append(el("strong", "", item.label), el("small", "", "Saved: " + number.format(item.balance)));
    if (item.limit !== null) detail.append(el("small", "", "Limit: " + number.format(item.limit)));
    identity.append(icon, detail);
    const field = el("div", "wallet-input"), label = el("label", "", "Add"), input = el("input");
    input.id = "add-" + item.key; label.htmlFor = input.id;
    input.type = "number"; input.inputMode = "numeric"; input.required = true;
    input.min = 0; input.step = 1; input.max = Math.max(0, item.limit - item.balance); input.value = 0;
    input.disabled = Number(input.max) === 0;
    input.setAttribute("aria-label", "Add " + item.label.toLowerCase());
    const note = el("p", "field-note");
    note.id = input.id + "-note"; input.setAttribute("aria-describedby", note.id);
    const after = el("div", "wallet-result"), result = el("strong");
    after.append(el("small", "", "After applying"), result);
    field.append(label, input);
    row.append(identity, field, after, note);
    wallet.append(row);
    controls.set(item.key, {item, input, result, note});
  }
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

$("account-form").oninput = () => { if (!stale) $("message").textContent = ""; update(); };
$("reload").onclick = load;
$("account-form").onsubmit = async event => {
  event.preventDefault();
  if ($("apply").disabled) return;
  const add = {};
  for (const [key, {input}] of controls) {
    if (!input.disabled && input.valueAsNumber > 0) add[key] = input.valueAsNumber;
  }
  const body = {version: account.version, name: $("name").value,
    tag: $("tag").value === account.tag ? account.tag : tagValue(), add};
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
