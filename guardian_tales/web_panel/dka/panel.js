import { $, elementIcon, feedback, setArtwork } from "/panel.js";

const elements = {None: "Basic", Darkness: "Dark", Ice: "Water", Nebula: "Space"};
const weaknesses = {Down: "Downed", Poison: "Injured", Aerial: "Airborne"};
let state;

function elementName(day) {
  return elements[day.element] || day.element;
}

function slimeName(day) {
  const element = elementName(day);
  return element === "Space" ? "Void Slime" : element + " Slime";
}

function weaknessName(day) {
  return weaknesses[day.weak_point] || day.weak_point;
}

function showSlime(image, day) {
  const element = elementName(day).toLowerCase();
  setArtwork(image, state.hasSlimeSprites ? "/dka/slimes/" + encodeURIComponent(element) + ".png" : null);
}

function preview(variant, dayNumber) {
  const day = variant.days[dayNumber - 1];
  const element = elementName(day).toLowerCase();
  document.querySelector(".arena-banner").dataset.element = element;
  showSlime($("preview-art"), day);
  const saved = state.active?.variant === variant.id && state.active.day === dayNumber;
  $("preview-day").textContent = (saved ? "" : "Preview · ") + "Season " + variant.season_id + " · Day " + dayNumber;
  $("preview-name").replaceChildren(elementIcon(element, state.hasElementIcons), slimeName(day));
  $("preview-weakness").textContent = weaknessName(day);
  $("encounter-preview").hidden = false;
}

function renderDays(variant, chosenDay) {
  preview(variant, chosenDay);
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
    card.querySelector(".day-number").textContent = "Day " + (index + 1);
    card.querySelector(".day-heading").append(elementIcon(card.dataset.element, state.hasElementIcons));
    card.querySelector(".saved-marker").hidden = !(state.active?.variant === variant.id && state.active.day === index + 1);
    card.querySelector("strong").textContent = slimeName(day);
    card.querySelector("small").textContent = "Weak to " + weaknessName(day);
    label.append(radio, card);
    $("days").append(label);
  });
}

function display(next) {
  state = next;
  const art = $("arena-art");
  if (state.hasBackdrop || state.hasArt) {
    const url = state.hasBackdrop ? "/dka/arena-backdrop.jpg" : "/arena.jpg";
    if (art.getAttribute("src") !== url) {
      art.hidden = false;
      art.onerror = () => { art.hidden = true; };
      art.src = url;
    }
  } else {
    art.removeAttribute("src");
    art.hidden = true;
  }
  const active = state.active;
  const variant = active ? state.variants.find(row => row.id === active.variant) : state.variants[0];
  $("variant").replaceChildren();
  state.variants.forEach(row => {
    $("variant").add(new Option("Variant " + row.id + " · Season " + row.season_id, row.id));
  });
  $("variant").value = String(variant.id);
  renderDays(variant, active ? active.day : 1);
  if (active) {
    const day = variant.days[active.day - 1];
    $("saved-status").textContent = "Variant " + active.variant + " · Season " + variant.season_id + " · Day " + active.day + " · " + slimeName(day);
  } else {
    $("saved-status").textContent = "No practice rotation selected yet.";
  }
}

function lockEditor(locked) {
  $("controls").disabled = locked;
  $("apply").disabled = locked;
}

async function refresh(message = "") {
  lockEditor(true);
  $("reload").disabled = true;
  try {
    const response = await fetch("/api/dka", {cache: "no-store"});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load the arena catalog.");
    display(result);
    lockEditor(false);
    feedback(message);
  } catch (error) {
    feedback([message, error.message].filter(Boolean).join(" "), true);
  } finally {
    $("reload").disabled = false;
  }
}

$("editor").addEventListener("change", event => {
  const variant = state.variants.find(row => row.id === Number($("variant").value));
  const day = Number($("editor").elements.day.value);
  if (event.target === $("variant")) renderDays(variant, day);
  else preview(variant, day);
  feedback("");
});
$("reload").addEventListener("click", () => refresh());
$("editor").addEventListener("submit", async event => {
  event.preventDefault();
  if ($("controls").disabled) return;
  const body = {
    variant: Number($("variant").value), day: Number($("editor").elements.day.value), revision: state.revision
  };
  lockEditor(true);
  $("reload").disabled = true;
  feedback("Preparing the arena calendar…");
  try {
    const response = await fetch("/api/dka", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      const result = await response.json();
      lockEditor(response.status === 409);
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
