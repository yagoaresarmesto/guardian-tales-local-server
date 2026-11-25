import { $ } from "/panel.js";

const api = "/api/orbital-lift/boards";
const positions = Array.from({length: 20}, (_, i) => i - i % 4 + 4 - i % 4);
const message = text => { $("board-message").textContent = text; };

export function startBoard(nextFloor, onSave) {
  let state, enemies, units, originalDraft, selected = positions[0], moving = null;
  let current = nextFloor >= 1 && nextFloor <= 1500 ? nextFloor : 1;
  const level = $("board-level"), picker = $("board-floor"), select = $("board-enemy");
  const unitAt = pos => units.find(unit => unit.position === pos);
  const draft = () => JSON.stringify([units, level.value]);

  function buttons() {
    $("board-save").disabled = draft() === originalDraft || !level.validity.valid ||
      (!units.length && state.floor.type !== "RecordRoom");
    $("board-restore").disabled = !state.custom;
    $("board-remove").disabled = $("board-move").disabled = !unitAt(selected);
    $("board-place").disabled = Number(select.value) === unitAt(selected)?.enemy;
  }

  function move(from, to) {
    const a = unitAt(from), b = unitAt(to);
    if (a && from !== to) {
      a.position = to;
      if (b) b.position = from;
    }
    moving = null;
    selected = to;
    render();
  }

  function render() {
    const grid = $("board-grid");
    const restoreFocus = grid.contains(document.activeElement);
    grid.replaceChildren();
    for (const pos of positions) {
      const unit = unitAt(pos), enemy = enemies.get(unit?.enemy);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "board-cell";
      button.dataset.position = pos;
      button.dataset.occupied = Boolean(unit);
      button.setAttribute("aria-pressed", String(pos === selected));
      button.title = "Cell " + pos + " · " + (enemy?.name ?? "Empty");
      button.setAttribute("aria-label", button.title);
      if (enemy?.sprite) {
        const image = document.createElement("img");
        image.alt = "";
        image.draggable = false;
        image.onerror = () => { image.hidden = true; };
        image.src = "/orbital-lift/enemies/" + encodeURIComponent(enemy.sprite) + ".png";
        button.append(image);
      }
      const label = document.createElement("span");
      label.textContent = enemy?.name ?? "+";
      button.append(label);
      button.onclick = () => {
        if (moving !== null) move(moving, pos);
        else { selected = pos; render(); }
      };
      button.draggable = Boolean(unit);
      button.ondragstart = event => event.dataTransfer.setData("application/x-orbital-cell", String(pos));
      button.ondragover = event => event.preventDefault();
      button.ondrop = event => {
        event.preventDefault();
        const from = Number(event.dataTransfer.getData("application/x-orbital-cell"));
        if (unitAt(from)) move(from, pos);
      };
      grid.append(button);
    }
    if (restoreFocus) grid.querySelector('[aria-pressed="true"]').focus();
    const unit = unitAt(selected);
    if (unit) select.value = unit.enemy;
    $("cell-title").textContent = "Cell " + selected + " · " + (unit ? enemies.get(unit.enemy).name : "Empty");
    $("board-hint").textContent = moving !== null ? "Choose the destination cell."
      : state.floor.type === "RecordRoom" ? "Adding enemies turns this record room into a normal combat floor."
      : "Drag an enemy to move it or swap two cells.";
    buttons();
  }

  function openFloor(number) {
    current = number;
    picker.value = current;
    const floor = state.floor, custom = state.custom;
    units = structuredClone(custom?.units ?? floor.units);
    level.value = custom?.level ?? "";
    level.max = state.maxLevel;
    level.placeholder = state.globalLevel ?? floor.level;
    $("board-inherit").textContent = "1–" + state.maxLevel + ". Leave blank to inherit level " + level.placeholder + ".";
    $("board-title").textContent = "Floor " + current + " · " + floor.type + (custom ? " · Customized" : "");
    selected = units[0]?.position ?? positions[0];
    moving = null;
    originalDraft = draft();
    render();
  }

  function busy(value) {
    $("board-controls").disabled = $("board-open").disabled = picker.disabled = value;
  }

  async function refresh(keepDraft = false, number = current) {
    busy(true);
    const response = await fetch(api + "/" + number, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load the enemy boards.");
    const preserve = keepDraft && state && draft() !== originalDraft &&
      number === current && JSON.stringify(state.custom) === JSON.stringify(data.custom);
    const pending = preserve ? [units, level.value] : null;
    state = data;
    enemies = new Map(data.enemies.map(enemy => [enemy.id, enemy]));
    select.replaceChildren(...data.enemies.map(enemy => new Option(
      enemy.name + " · " + (enemy.element || "Unknown") + " · #" + enemy.id, enemy.id
    )));
    openFloor(number);
    if (pending) { units = pending[0]; level.value = pending[1]; render(); }
    busy(false);
  }

  async function save(restore) {
    busy(true);
    message("Saving floor " + current + "…");
    try {
      const board = restore ? null : {units, level: level.value === "" ? null : level.valueAsNumber};
      const response = await fetch(api, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({floor: current, board, revision: state.revision})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save the board.");
      await refresh();
      await onSave();
      message("Floor " + current + (restore ? " restored." : " saved.") + " Reopen Guardian Tales to load it.");
    } catch (error) {
      message(error.message + " Reload the page to continue.");
    }
  }

  $("board-picker").onsubmit = event => {
    event.preventDefault();
    if (picker.disabled || !picker.validity.valid) return;
    if (draft() !== originalDraft && !window.confirm("Discard the unsaved board changes?")) {
      picker.value = current;
      $("board-controls").disabled = false;
      return;
    }
    refresh(false, picker.valueAsNumber).catch(error => message(error.message));
    message("");
  };
  picker.oninput = () => {
    $("board-controls").disabled = picker.valueAsNumber !== current;
    $("board-open").disabled = !picker.validity.valid;
  };
  select.onchange = buttons;
  level.oninput = buttons;
  $("board-place").onclick = () => {
    const idx = units.findIndex(unit => unit.position === selected);
    const replacement = {position: selected, enemy: Number(select.value)};
    if (idx < 0) units.push(replacement);
    else units[idx] = replacement;
    moving = null;
    render();
  };
  $("board-remove").onclick = () => { units = units.filter(unit => unit.position !== selected); moving = null; render(); };
  $("board-move").onclick = () => { moving = moving === selected ? null : selected; render(); };
  $("board-save").onclick = () => save(false);
  $("board-restore").onclick = () => save(true);
  document.addEventListener("orbital-global-level", () => refresh(true).catch(error => message(error.message)));
  refresh().catch(error => message(error.message));
}
