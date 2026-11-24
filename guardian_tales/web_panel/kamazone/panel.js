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

function draft() {
  if ($("old-mode").checked) {
    return {action: "select-old", seasonId: Number($("old-season").value)};
  }
  const value = $("seasons").querySelector("input:checked")?.value;
  const seasonId = value ? Number(value) : null;
  return state.oldActive && seasonId === state.previousEventId ?
    {action: "leave-old"} : {action: "select", seasonId};
}

function updateChoice() {
  const {action, seasonId} = draft();
  const archived = action === "select-old";
  $("seasons").hidden = archived;
  $("archive-picker").hidden = !archived;
  const rotation = state.oldSeasons.find(row => row.id === seasonId);
  $("old-details").textContent = rotation ?
    "Eight-floor practice · " + dateFormat.format(new Date(rotation.from)) + " – " + dateFormat.format(new Date(rotation.to)) :
    "Choose a historical rotation to practice its eight regular floors.";
  const same = seasonId != null && seasonId === state.seasonId;
  $("apply").disabled = action !== "leave-old" && (!seasonId || (same && state.phase === "active"));
  $("apply").textContent = action === "leave-old" ? "Turn off Old Kamazone" :
    same && state.phase === "active" ? "Season active" :
    same && ["expired", "reward-period"].includes(state.phase) ? "Renew season" :
    archived && !state.oldActive ? "Activate Old Kamazone" : "Apply season";
}

function display(next) {
  state = next;
  $("archive-controls").hidden = !state.oldSeasons.length;
  $("old-mode").checked = state.oldActive;
  $("old-season").replaceChildren(new Option("Choose a rotation", ""));
  for (const row of state.oldSeasons) $("old-season").add(new Option(row.name, String(row.id)));
  if (state.oldActive) $("old-season").value = String(state.seasonId);
  $("seasons").replaceChildren();
  for (const season of state.seasons) {
    const label = document.createElement("label");
    label.className = "season-choice";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "season";
    radio.value = String(season.id);
    radio.checked = season.id === (state.oldActive ? state.previousEventId : state.seasonId);
    if (season.image) {
      const preview = document.createElement("img");
      preview.className = "season-art";
      preview.alt = "";
      preview.width = 520;
      preview.height = 240;
      preview.addEventListener("error", () => preview.remove(), {once: true});
      preview.src = season.image;
      label.append(preview);
    }
    const text = document.createElement("span");
    text.className = "season-copy";
    const id = document.createElement("small");
    id.textContent = "Season " + season.id;
    const name = document.createElement("strong");
    name.textContent = season.name;
    text.append(id, name);
    if (season.theme) {
      const theme = document.createElement("span");
      theme.className = "season-theme";
      theme.textContent = season.theme;
      text.append(theme);
    }
    label.append(text, radio);
    $("seasons").append(label);
  }
  const selected = state.seasons.find(row => row.id === state.seasonId);
  const archive = state.oldSeasons.find(row => row.id === state.seasonId);
  $("current").textContent = archive ? "Old Kamazone · " + archive.name :
    state.seasonId === null ? "No local season selected" :
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

async function save(change) {
  const body = {...change, revision: state.revision};
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
  if (!$("controls").disabled && !$("apply").disabled) save(draft());
});
$("restore").addEventListener("click", () => save({action: "disable"}));
$("reload").addEventListener("click", () => refresh());
refresh();
