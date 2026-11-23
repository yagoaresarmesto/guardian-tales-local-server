import { $, feedback } from "/panel.js";

const endpoint = "/api/kamazone";
const phaseLabels = {
  active: "Active in Events", "reward-period": "Post-season · still visible in Events",
  expired: "Expired · select the season again to renew it",
  scheduled: "Scheduled", "pack-mismatch": "Content pack changed · select a season again or restore the calendar",
  disabled: "Using the original Events calendar"
};
const dateFormat = new Intl.DateTimeFormat("en-GB", {dateStyle: "medium", timeZone: "UTC"});
let state;

function updateChoice() {
  const choice = $("seasons").querySelector("input:checked")?.value;
  const same = Boolean(choice) && Number(choice) === state.seasonId;
  $("apply").disabled = !choice || (same && state.phase === "active");
  $("apply").textContent = same && state.phase === "active" ? "Season active" :
    same && ["expired", "reward-period"].includes(state.phase) ? "Renew season" : "Apply season";
}

function display(next) {
  state = next;
  $("seasons").replaceChildren();
  for (const season of state.seasons) {
    const label = document.createElement("label");
    label.className = "season-choice";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "season";
    radio.value = String(season.id);
    radio.checked = season.id === state.seasonId;
    const text = document.createElement("span");
    const id = document.createElement("small");
    id.textContent = "Season " + season.id;
    const name = document.createElement("strong");
    name.textContent = season.name;
    text.append(id, name);
    label.append(radio, text);
    $("seasons").append(label);
  }
  const selected = state.seasons.find(row => row.id === state.seasonId);
  $("current").textContent = state.seasonId === null ? "No local season selected" :
    "Season " + state.seasonId + (selected ? " · " + selected.name : "");
  $("phase").textContent = phaseLabels[state.phase];
  $("period").hidden = !state.period;
  if (state.period) {
    for (const [id, key] of [["starts", "From"], ["ends", "To"], ["leaves", "RewardUntil"]]) {
      const date = state.period[key];
      $(id).textContent = dateFormat.format(new Date(date)) + " UTC";
      $(id).title = date;
    }
  }
  $("restore").hidden = state.seasonId === null;
  $("mall-art").hidden = !state.hasArt;
  updateChoice();
}

function lockControls() {
  $("controls").disabled = true;
  $("restore").disabled = true;
  $("reload").disabled = true;
}

async function refresh(message = "") {
  lockControls();
  try {
    const response = await fetch(endpoint, {cache: "no-store"});
    const next = await response.json();
    if (!response.ok) throw new Error(next.error || "Could not load the season calendar.");
    display(next);
    $("controls").disabled = false;
    $("restore").disabled = false;
    feedback(message);
  } catch (error) {
    feedback([message, error.message].filter(Boolean).join(" "), true);
  } finally {
    $("reload").disabled = false;
  }
}

async function save(action) {
  const body = {action, revision: state.revision};
  if (action === "select") body.seasonId = Number($("editor").elements.season.value);
  lockControls();
  feedback("Saving season calendar…");
  try {
    const response = await fetch(endpoint, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      const result = await response.json();
      if (response.status === 400) {
        $("controls").disabled = false;
        $("restore").disabled = false;
      }
      throw new Error(result.error || "Reload the calendar and try again.");
    }
    await refresh("Calendar saved. Restart the backend and reopen the game.");
  } catch (error) {
    feedback(error.message, true);
  } finally {
    $("reload").disabled = false;
  }
}

$("editor").addEventListener("change", () => { updateChoice(); feedback(""); });
$("editor").addEventListener("submit", event => {
  event.preventDefault();
  if (!$("controls").disabled && !$("apply").disabled) save("select");
});
$("restore").addEventListener("click", () => save("disable"));
$("reload").addEventListener("click", () => refresh());
refresh();
