import { $, elementIcon, feedback, setArtwork } from "/panel.js";

const editor = $("editor");
const number = new Intl.NumberFormat("en-US");
let data;
let selectedEncounter = 0;

function title(name) {
  return name.replace(/\b\w/g, char => char.toUpperCase());
}

function bossName(slot) {
  if (slot.boss) return title(slot.boss);
  return slot.stage ? "Stage " + slot.stage : "Choose a boss";
}

function slotNumber(index) {
  return String(index + 1).padStart(2, "0");
}

function showPortrait(image, boss) {
  const frame = data.bossPortraits[boss];
  setArtwork(image, frame ? "/raid/bosses/" + encodeURIComponent(frame) + ".png" : null);
}

function showElement(container, element) {
  if (container.dataset.element === element) return;
  container.dataset.element = element || "";
  container.replaceChildren();
  if (element) container.append(elementIcon(element, data.hasElementIcons), title(element));
}

function isCustom() {
  return editor.elements.mode.value === "custom";
}

function chosenSeason() {
  return isCustom() ? data.seasons[0] : data.seasons.find(season => season.id === Number($("season").value));
}

function customLineup() {
  return [...$("slots").children].map(card => ({
    boss: card.querySelector('[name="boss"]').value,
    element: card.querySelector('[name="element"]').value
  }));
}

function draftBosses() {
  return isCustom() ? customLineup() : chosenSeason().bosses;
}

function updateStatus() {
  const custom = isCustom();
  const season = chosenSeason();
  const hp = $("hp");
  const originalHp = hp.value === "" && !hp.validity.badInput;
  const matchesActive = custom === data.custom && season.id === data.active.id && (!custom || (
    customLineup().every((slot, i) => slot.boss === data.active.bosses[i].boss && slot.element === data.active.bosses[i].element)
    && (originalHp ? !data.customHp : data.customHp && hp.valueAsNumber === data.active.hpPerBar)
  ));
  const status = matchesActive ? (data.prepared ? "Active lineup" : "Catalog default") : "Lineup preview";
  $("season-status").textContent = status + " · Season " + season.id;
  $("season-status").classList.toggle("preview", !matchesActive);
}

function inspect(index, bosses = draftBosses()) {
  selectedEncounter = index;
  const slot = bosses[index];
  $("encounter-detail").hidden = false;
  $("encounter-detail").dataset.element = slot.element || "";
  $("encounter-meta").textContent = "Encounter " + slotNumber(index);
  $("encounter-name").textContent = bossName(slot);
  showPortrait($("encounter-art"), slot.boss);
  showElement($("encounter-element"), slot.element);
  [...$("slots").children].forEach((card, i) => {
    const selected = i === index;
    card.querySelector(".inspect").setAttribute("aria-pressed", String(selected));
    $("map-pins").children[i].setAttribute("aria-pressed", String(selected));
  });
}

function renderLineup() {
  const custom = isCustom();
  const season = chosenSeason();
  const bosses = draftBosses();
  $("stock").hidden = custom;
  $("season").disabled = custom;
  $("base").hidden = !custom;
  $("hp-field").hidden = !custom;
  $("hp").disabled = !custom;
  $("stock-hp").hidden = custom;
  $("stock-hp").querySelector("strong").textContent = number.format(season.hpPerBar);
  bosses.forEach((slot, index) => {
    const card = $("slots").children[index];
    const pin = $("map-pins").children[index];
    const label = "Encounter " + slotNumber(index) + ", " + bossName(slot) + (slot.element ? ", " + title(slot.element) : "");
    card.dataset.element = pin.dataset.element = slot.element || "";
    card.querySelector(".inspect").setAttribute("aria-label", label);
    pin.setAttribute("aria-label", label);
    pin.title = label;
    showPortrait(pin.querySelector(".boss-portrait"), slot.boss);
    showPortrait(card.querySelector(".boss-portrait"), slot.boss);
    showElement(card.querySelector(".card-element"), slot.element);
    const name = card.querySelector(".stock-name");
    name.textContent = bossName(slot);
    name.hidden = custom;
    card.querySelector(".slot-fields").hidden = !custom;
    card.querySelectorAll("select").forEach(select => { select.disabled = !custom; });
  });
  inspect(selectedEncounter, bosses);
  updateStatus();
}

function populate(select, names, value) {
  select.add(new Option("Choose " + select.name, ""));
  names.forEach(name => select.add(new Option(title(name), name)));
  select.value = value || "";
}

function buildEncounters() {
  $("slots").replaceChildren();
  $("map-pins").replaceChildren();
  data.active.bosses.forEach((slot, index) => {
    const order = slotNumber(index);
    const card = $("encounter-card").content.firstElementChild.cloneNode(true);
    card.querySelector(".slot-num b").textContent = order;
    card.querySelector(".card-art").dataset.slot = order;
    card.querySelector(".inspect").addEventListener("click", () => inspect(index));
    const boss = card.querySelector('[name="boss"]');
    const element = card.querySelector('[name="element"]');
    populate(boss, data.bossNames, slot.boss);
    populate(element, data.elementNames, slot.element);
    for (const select of [boss, element]) {
      select.setAttribute("aria-label", title(select.name) + " for encounter " + order);
      select.addEventListener("focus", () => inspect(index));
      select.addEventListener("change", () => { selectedEncounter = index; });
    }
    $("slots").append(card);
    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = "map-pin";
    pin.setAttribute("aria-controls", "encounter-detail");
    pin.addEventListener("click", () => inspect(index));
    const image = document.createElement("img");
    image.className = "boss-portrait";
    image.alt = "";
    image.hidden = true;
    const badge = document.createElement("span");
    badge.textContent = order;
    pin.append(image, badge);
    $("map-pins").append(pin);
  });
}

function display(state) {
  data = state;
  const active = data.active;
  $("active-season").textContent = "Season " + active.id + " · " + (data.custom ? "Custom lineup" : "Original season");
  $("active-hp").textContent = number.format(active.hpPerBar);
  $("active-bosses").replaceChildren(...active.bosses.map((slot, index) => {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = bossName(slot);
    const element = document.createElement("span");
    element.className = "element";
    showElement(element, slot.element);
    item.append(slotNumber(index), name, element);
    return item;
  }));
  setArtwork($("map"), data.hasMap ? "/map.png" : null);
  $("season").replaceChildren(...data.seasons.map(s => new Option("Season " + s.id, s.id)));
  $("season").value = String(active.id);
  const base = data.seasons[0];
  $("base").querySelector("strong").textContent = "Season " + base.id;
  $("hp").placeholder = "Original values (round 1: " + number.format(base.hpPerBar) + ")";
  $("hp").value = data.customHp ? active.hpPerBar : "";
  editor.elements.mode.value = data.custom ? "custom" : "stock";
  buildEncounters();
  renderLineup();
}

async function readState() {
  const response = await fetch("/api/raid", {cache: "no-store"});
  const state = await response.json();
  if (!response.ok) throw new Error(state.error || "Could not load the Raid catalog.");
  return state;
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

editor.addEventListener("change", event => {
  if (event.target !== $("hp")) renderLineup();
  feedback("");
});
$("hp").addEventListener("input", () => { updateStatus(); feedback(""); });
$("reload").addEventListener("click", reload);
editor.addEventListener("submit", async event => {
  event.preventDefault();
  if ($("controls").disabled || !data) return;
  const body = {mode: editor.elements.mode.value, revision: data.revision};
  if (isCustom()) {
    body.lineup = customLineup().map(slot => [slot.boss, slot.element]);
    if (new Set(body.lineup.map(pair => JSON.stringify(pair))).size !== 4) {
      feedback("Each slot needs a different boss and element combination.", true);
      return;
    }
    body.hpPerBar = $("hp").value === "" ? null : $("hp").valueAsNumber;
  } else {
    body.season = Number($("season").value);
  }
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
  }
});

reload();
