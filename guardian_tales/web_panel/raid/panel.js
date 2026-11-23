import { $, elementIcon, feedback, setArtwork } from "/panel.js";

const modes = [...document.querySelectorAll('input[name="mode"]')];
const number = new Intl.NumberFormat("en-US");
let data;
let applying = false;
let selectedEncounter = 0;

function title(name) {
  return name.replace(/\b\w/g, char => char.toUpperCase());
}

async function readState() {
  const response = await fetch("/api/raid", {cache: "no-store"});
  const state = await response.json();
  if (!response.ok) throw new Error(state.error || "Could not load the Raid catalog.");
  return state;
}

function bossName(slot) {
  return slot.boss ? title(slot.boss) : "Stage " + slot.stage;
}

function slotNumber(index) {
  return String(index + 1).padStart(2, "0");
}

function portrait(boss) {
  const image = document.createElement("img");
  image.alt = "";
  image.hidden = true;
  image.className = "boss-portrait";
  const frame = data.bossPortraits[boss];
  if (frame) setArtwork(image, "/raid/bosses/" + encodeURIComponent(frame) + ".png");
  return image;
}

function markEncounter(index) {
  selectedEncounter = index;
  const slot = data.active.bosses[index];
  $("encounter-detail").hidden = false;
  $("encounter-detail").dataset.element = slot.element || "";
  $("encounter-art").replaceChildren(portrait(slot.boss));
  $("encounter-element").replaceChildren(elementIcon(slot.element, data.hasElementIcons));
  $("encounter-name").textContent = bossName(slot);
  $("encounter-meta").textContent = "Encounter " + slotNumber(index) + (slot.element ? " · " + title(slot.element) : "");
  for (const list of [$("map-pins"), $("active-bosses")]) {
    list.querySelectorAll("button").forEach((button, i) => {
      button.setAttribute("aria-pressed", String(index === i));
    });
  }
}

function encounterButton(slot, index) {
  const button = document.createElement("button");
  button.type = "button";
  const label = "Encounter " + (index + 1) + ", " + bossName(slot) +
    (slot.element ? ", " + title(slot.element) : "");
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-controls", "encounter-detail");
  button.addEventListener("click", () => markEncounter(index));
  return button;
}

function showBosses(container, bosses, active = false) {
  container.replaceChildren();
  if (active) $("map-pins").replaceChildren();
  bosses.forEach((slot, index) => {
    const row = document.createElement("li");
    const card = active ? encounterButton(slot, index) : document.createElement("div");
    card.className = "boss-card";
    card.dataset.element = slot.element || "";
    const order = document.createElement("span");
    order.className = "slot-num";
    order.textContent = slotNumber(index);
    const name = document.createElement("strong");
    name.className = "boss-name";
    name.textContent = bossName(slot);
    card.append(order, portrait(slot.boss), name);
    if (slot.element) {
      const element = document.createElement("span");
      element.className = "element";
      element.append(elementIcon(slot.element, data.hasElementIcons), title(slot.element));
      card.append(element);
    }
    row.append(card);
    container.append(row);
    if (active) {
      const pin = encounterButton(slot, index);
      pin.className = "map-pin";
      pin.dataset.element = slot.element || "";
      pin.title = pin.getAttribute("aria-label");
      const number = document.createElement("span");
      number.textContent = slotNumber(index);
      pin.append(portrait(slot.boss), number);
      $("map-pins").append(pin);
    }
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
  showBosses($("active-bosses"), active.bosses, true);
  markEncounter(selectedEncounter);
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
    order.textContent = slotNumber(index);
    const boss = choice("Boss", data.bossNames, slot.boss, index);
    const element = choice("Element", data.elementNames, slot.element, index);
    const bossSelect = boss.querySelector("select");
    const elementSelect = element.querySelector("select");
    const thumbnail = document.createElement("span");
    thumbnail.className = "slot-art";
    const updatePortrait = () => thumbnail.replaceChildren(portrait(bossSelect.value), order);
    const iconSlot = document.createElement("span");
    iconSlot.className = "select-icon";
    const updateElement = () => {
      row.dataset.element = elementSelect.value;
      iconSlot.replaceChildren(elementIcon(elementSelect.value, data.hasElementIcons));
    };
    element.append(iconSlot);
    bossSelect.addEventListener("change", updatePortrait);
    elementSelect.addEventListener("change", updateElement);
    updatePortrait();
    updateElement();
    row.append(thumbnail, boss, element);
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
