import { $ } from "/panel.js";

const viewport = $("map-viewport");
const sheet = $("map-sheet");
let layoutRequest;
let latest;
let zoom = 1;
let drag;

async function loadTerrain() {
  const response = await fetch("/expedition/world-map.json");
  if (!response.ok) throw new Error("District layout unavailable");
  const layout = await response.json();
  $("map-terrain").src = "/expedition/world-map.webp";
  await $("map-terrain").decode();
  return layout;
}

function setZoom(next) {
  const cx = (viewport.scrollLeft + viewport.clientWidth / 2) / sheet.offsetWidth;
  const cy = (viewport.scrollTop + viewport.clientHeight / 2) / sheet.offsetHeight;
  zoom = Math.max(1, Math.min(4, next));
  sheet.style.width = (zoom * 100) + "%";
  viewport.toggleAttribute("data-zoomed", zoom > 1);
  viewport.scrollLeft = cx * sheet.offsetWidth - viewport.clientWidth / 2;
  viewport.scrollTop = cy * sheet.offsetHeight - viewport.clientHeight / 2;
  $("zoom-out").disabled = $("zoom-fit").disabled = zoom === 1;
  $("zoom-in").disabled = zoom === 4;
}

export function selectGate(district, area) {
  const gate = [...$("district-gates").children].find(button => Number(button.dataset.district) === district);
  for (const button of $("district-gates").children) button.setAttribute("aria-pressed", String(button === gate));
  $("map-location").textContent = gate?.getAttribute("aria-label") || area || "All districts";
}

function hideMap() {
  $("world-map").hidden = true;
  $("district-gates").replaceChildren();
  $("page-title").textContent = "Enemy levels";
  $("expedition-kicker").textContent = "Solo Expedition";
}

export async function showMap(state, selectedDistrict, area) {
  latest = state;
  if (!state.hasWorldMap) {
    hideMap();
    return;
  }
  try {
    layoutRequest ??= loadTerrain();
    const layout = await layoutRequest;
    if (latest !== state) return;
    const gates = [];
    for (const pin of layout.districts) {
      const stages = state.stages.filter(row => row.district_id === pin.id);
      const number = stages[0]?.district_number;
      if (!number) continue;
      const gate = $("gate-template").content.firstElementChild.cloneNode(true);
      gate.dataset.district = pin.id;
      gate.style.left = (pin.x * 100) + "%";
      gate.style.top = (pin.y * 100) + "%";
      gate.toggleAttribute("data-boss", stages.some(row => row.kind === "boss"));
      gate.querySelector(".gate-label").textContent = "District " + number;
      gate.querySelector(".gate-door").dataset.number = number;
      gate.setAttribute("aria-label", "District " + number + " · " + stages.length + " stages");
      gates.push(gate);
    }
    if (!gates.length) {
      hideMap();
      return;
    }
    const firstView = $("world-map").hidden;
    $("district-gates").replaceChildren(...gates);
    $("world-map").style.setProperty("--map-ratio", layout.width + " / " + layout.height);
    $("world-map").hidden = false;
    $("page-title").textContent = "Expedition";
    $("expedition-kicker").textContent = "District map";
    selectGate(selectedDistrict, area);
    if (firstView) {
      setZoom(Math.max(1, 660 / viewport.clientWidth));
      viewport.scrollTo(0, 0);
    }
  } catch {
    if (latest === state) {
      layoutRequest = undefined;
      hideMap();
    }
    // The stage directory stays available with incomplete or missing local art.
  }
}

$("zoom-out").addEventListener("click", () => setZoom(zoom / 1.5));
$("zoom-in").addEventListener("click", () => setZoom(zoom * 1.5));
$("zoom-fit").addEventListener("click", () => setZoom(1));

viewport.addEventListener("pointerdown", event => {
  if (event.pointerType !== "mouse" || event.button !== 0 || zoom === 1 || event.target.closest("button")) return;
  drag = {x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop};
  viewport.setPointerCapture(event.pointerId);
});
viewport.addEventListener("pointermove", event => {
  if (!drag || !viewport.hasPointerCapture(event.pointerId)) return;
  viewport.scrollTo(drag.left + drag.x - event.clientX, drag.top + drag.y - event.clientY);
});
viewport.addEventListener("lostpointercapture", () => { drag = undefined; });
