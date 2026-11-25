import { $, feedback } from "/panel.js";

const endpoint = "/api/orbital-lift";
const format = new Intl.NumberFormat("en");
const floor = $("floor");
let saved, allowed = new Set();

function preview() {
  const target = floor.valueAsNumber;
  const valid = floor.validity.valid && allowed.has(target);
  $("apply").disabled = !saved?.writable || !valid || target === saved.nextFloor;
  $("preview").textContent = valid
    ? "Highest cleared floor after applying: " + format.format(target - 1) + "."
    : "Choose a floor from the installed Orbital Lift catalog.";
}

async function load(message = "") {
  $("controls").disabled = $("reload").disabled = true;
  try {
    const res = await fetch(endpoint, {cache: "no-store"});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not load Orbital Lift progress.");
    saved = data;
    allowed = new Set(data.floors);
    $("cleared").textContent = format.format(data.clearedFloor);
    $("next").textContent = data.nextFloor == null ? "—" : format.format(data.nextFloor);
    floor.value = allowed.has(data.nextFloor) ? data.nextFloor : "";
    $("access").hidden = data.writable;
    $("controls").disabled = false;
    preview();
    feedback(message);
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("reload").disabled = false;
  }
}

floor.oninput = () => { feedback(""); preview(); };
$("reload").onclick = () => load();
$("editor").onsubmit = async event => {
  event.preventDefault();
  if ($("controls").disabled || $("apply").disabled) return;
  $("controls").disabled = $("reload").disabled = true;
  try {
    const res = await fetch(endpoint, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({version: saved.version, nextFloor: floor.valueAsNumber}),
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || "Could not save Orbital Lift progress.");
    await load("Progress saved.");
  } catch (error) {
    feedback(error.message + " Reload saved progress to continue.", true);
  } finally {
    $("reload").disabled = false;
  }
};
load();
