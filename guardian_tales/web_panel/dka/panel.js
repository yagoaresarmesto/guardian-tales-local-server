import { $, elementIcon, feedback, setArtwork } from "/panel.js";

const elements = {None: "Basic", Darkness: "Dark", Ice: "Water", Nebula: "Space"};
const weaknesses = {Down: "Downed", Poison: "Injured", Aerial: "Airborne"};
let state;

function elementName(day) {
  return elements[day.element] || day.element;
}

function weakness(day) {
  return "Weak to " + (weaknesses[day.weak_point] || day.weak_point);
}

function showSlime(image, day) {
  const element = elementName(day).toLowerCase();
  setArtwork(image, state.hasSlimeSprites ? "/dka/slimes/" + encodeURIComponent(element) + ".png" : null);
}

function renderDays(variant, chosenDay) {
  $("days").replaceChildren();
  variant.days.forEach((day, index) => {
    const label = document.createElement("label");
    const radio = document.createElement("input");
    radio.className = "sr";
    radio.type = "radio";
    radio.name = "day";
    radio.value = String(index + 1);
    radio.checked = index + 1 === chosenDay;
    const card = $("day-card").content.firstElementChild.cloneNode(true);
    card.dataset.element = elementName(day).toLowerCase();
    showSlime(card.querySelector(".slime"), day);
    card.querySelector(".day-number").append("Day " + (index + 1), elementIcon(card.dataset.element, state.hasElementIcons));
    card.querySelector("strong").textContent = elementName(day) + " Slime";
    card.querySelector("small").textContent = weakness(day);
    label.append(radio, card);
    $("days").append(label);
  });
}

function display(next) {
  state = next;
  const active = state.active;
  const variant = active ? state.variants.find(row => row.id === active.variant) : state.variants[0];
  $("variant").replaceChildren();
  state.variants.forEach(row => {
    $("variant").add(new Option("Variant " + row.id + " · Season " + row.season_id, row.id));
  });
  $("variant").value = String(variant.id);
  renderDays(variant, active ? active.day : 1);
  $("saved-encounter").hidden = !active;
  if (active) {
    const day = variant.days[active.day - 1];
    $("saved-status").textContent = "Variant " + active.variant + " · Season " + variant.season_id + " · Day " + active.day;
    $("saved-encounter").dataset.element = elementName(day).toLowerCase();
    showSlime($("saved-encounter").querySelector(".slime"), day);
    $("saved-slime").replaceChildren(elementIcon($("saved-encounter").dataset.element, state.hasElementIcons), elementName(day) + " Slime");
    $("saved-weakness").textContent = weakness(day);
  } else {
    $("saved-status").textContent = "No practice rotation selected yet.";
  }
  if (state.hasArt && $("arena-art").hidden) {
    $("arena-art").src = "/arena.jpg";
    $("arena-art").hidden = false;
  }
}

async function refresh(message = "") {
  $("controls").disabled = true;
  $("reload").disabled = true;
  try {
    const response = await fetch("/api/dka", {cache: "no-store"});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load the arena catalog.");
    display(result);
    $("controls").disabled = false;
    feedback(message);
  } catch (error) {
    feedback([message, error.message].filter(Boolean).join(" "), true);
  } finally {
    $("reload").disabled = false;
  }
}

$("variant").addEventListener("change", () => {
  const variant = state.variants.find(row => row.id === Number($("variant").value));
  renderDays(variant, Number($("editor").elements.day.value));
});
$("editor").addEventListener("change", () => feedback(""));
$("reload").addEventListener("click", () => refresh());
$("editor").addEventListener("submit", async event => {
  event.preventDefault();
  if ($("controls").disabled) return;
  const body = {
    variant: Number($("variant").value), day: Number($("editor").elements.day.value), revision: state.revision
  };
  $("controls").disabled = true;
  $("reload").disabled = true;
  feedback("Preparing the arena calendar…");
  try {
    const response = await fetch("/api/dka", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      const result = await response.json();
      $("controls").disabled = response.status === 409;
      feedback(result.error || "Could not apply the arena selection.", true);
      return;
    }
    await refresh("Selection applied. Fully close and reopen Guardian Tales.");
  } catch (error) {
    feedback("Reload the saved selection before trying again. " + error.message, true);
  } finally {
    $("reload").disabled = false;
  }
});

refresh();
