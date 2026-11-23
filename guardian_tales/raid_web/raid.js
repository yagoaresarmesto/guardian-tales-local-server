"use strict";

const $ = id => document.getElementById(id);
const modes = [...document.querySelectorAll('input[name="mode"]')];
const number = new Intl.NumberFormat("en-US");
let data;
let applying = false;

function title(name) {
  return name.replace(/\b\w/g, char => char.toUpperCase());
}

function feedback(message, error = false) {
  const node = $("feedback");
  node.textContent = message;
  node.dataset.error = String(error);
  node.hidden = !message;
}

async function readState() {
  const response = await fetch("/api/raid", {cache: "no-store"});
  const state = await response.json();
  if (!response.ok) throw new Error(state.error || "Could not load the Raid catalog.");
  return state;
}

function showBosses(container, bosses) {
  container.replaceChildren();
  bosses.forEach((slot, index) => {
    const row = document.createElement("li");
    const order = document.createElement("span");
    order.className = "slot-num";
    order.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("span");
    name.className = "boss-name";
    name.textContent = slot.boss ? title(slot.boss) : "Stage " + slot.stage;
    row.append(order, name);
    if (slot.element) {
      const element = document.createElement("span");
      element.className = "element";
      element.dataset.element = slot.element;
      element.textContent = title(slot.element);
      row.append(element);
    }
    container.append(row);
  });
}

function choice(label, names, selected, index) {
  const wrapper = document.createElement("label");
  const text = document.createElement("span");
  text.textContent = label;
  const select = document.createElement("select");
  select.setAttribute("aria-label", label + " for slot " + (index + 1));
  select.required = true;
  select.add(new Option("Choose " + label.toLowerCase(), ""));
  names.forEach(name => select.add(new Option(title(name), name)));
  select.value = selected || "";
  wrapper.append(text, select);
  return wrapper;
}

function renderEditor() {
  const custom = modes.find(input => input.checked).value === "custom";
  $("stock").hidden = custom;
  $("custom").hidden = !custom;
  $("hp").disabled = !custom;
  $("season").disabled = custom;
  $("slots").querySelectorAll("select").forEach(input => { input.disabled = !custom; });
  const season = data.seasons.find(item => item.id === Number($("season").value));
  showBosses($("preview"), season.bosses);
}

function display(state) {
  data = state;
  const active = data.active;
  const kind = data.custom ? "Custom lineup" : "Original rotation";
  $("season-status").textContent = (data.prepared ? "Active season " : "Catalog default · Season ") + active.id;
  $("active-season").textContent = "Season " + active.id + " · " + kind;
  $("active-hp").textContent = number.format(active.hpPerBar);
  showBosses($("active-bosses"), active.bosses);
  if (data.hasMap && $("map").hidden) {
    $("map").src = "/map.png";
    $("map").hidden = false;
  }
  $("season").replaceChildren();
  data.seasons.forEach(item => $("season").add(new Option("Season " + item.id, item.id)));
  $("season").value = String(active.id);
  const base = data.seasons[0];
  $("base").textContent = "Custom rotations use Season " + base.id + " as their base.";
  $("hp").placeholder = "Original values (round 1: " + number.format(base.hpPerBar) + ")";
  $("hp").value = data.customHp ? active.hpPerBar : "";
  $("slots").replaceChildren();
  active.bosses.forEach((slot, index) => {
    const row = document.createElement("div");
    row.className = "slot-row";
    const order = document.createElement("span");
    order.className = "slot-num";
    order.textContent = String(index + 1).padStart(2, "0");
    row.append(order, choice("Boss", data.bossNames, slot.boss, index),
      choice("Element", data.elementNames, slot.element, index));
    $("slots").append(row);
  });
  modes[data.custom ? 1 : 0].checked = true;
  renderEditor();
}

async function reload() {
  $("controls").disabled = true;
  $("reload").disabled = true;
  try {
    display(await readState());
    $("controls").disabled = false;
    feedback("");
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("reload").disabled = false;
  }
}

modes.forEach(input => input.addEventListener("change", renderEditor));
$("season").addEventListener("change", renderEditor);
$("reload").addEventListener("click", reload);
$("editor").addEventListener("submit", async event => {
  event.preventDefault();
  if (applying || !data) return;
  const mode = modes.find(input => input.checked).value;
  const body = {mode, revision: data.revision};
  if (mode === "stock") {
    body.season = Number($("season").value);
  } else {
    body.lineup = [...$("slots").children].map(row =>
      [...row.querySelectorAll("select")].map(select => select.value));
    if (new Set(body.lineup.map(pair => JSON.stringify(pair))).size !== 4) {
      feedback("Each slot needs a different boss and element combination.", true);
      return;
    }
    body.hpPerBar = $("hp").value === "" ? null : $("hp").valueAsNumber;
  }

  applying = true;
  $("controls").disabled = true;
  $("reload").disabled = true;
  feedback("Preparing the Raid tables…");
  let needsReload = false;
  let applied = false;
  try {
    const response = await fetch("/api/raid", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      needsReload = response.status === 409;
      const answer = await response.json();
      throw new Error(answer.error || "Could not apply the rotation.");
    }
    applied = true;
    display(await readState());
    feedback("Rotation applied. Fully close and reopen Guardian Tales.");
  } catch (error) {
    feedback(applied ? "Rotation saved. Reload the panel to see the active lineup." : error.message, true);
  } finally {
    $("controls").disabled = needsReload || (applied && $("feedback").dataset.error === "true");
    $("reload").disabled = false;
    applying = false;
  }
});

reload();
