import { $ } from "/panel.js";

const api = "/api/orbital-lift/boards";
const positions = Array.from({length: 20}, (_, i) => i - i % 4 + 4 - i % 4);
const message = text => { $("board-message").textContent = text; };
const elementNames = {None: "Basic", Darkness: "Dark", Ice: "Water", Nebula: "Space"};

function artwork(src, className, lazy = false) {
  const image = document.createElement("img");
  image.className = className;
  image.alt = "";
  image.draggable = false;
  image.loading = lazy ? "lazy" : "eager";
  image.onerror = () => { image.hidden = true; };
  image.src = src;
  return image;
}

function addEnemyArt(tile, enemy, lazy = false) {
  if (enemy.sprite) tile.append(artwork("/orbital-lift/enemies/" + encodeURIComponent(enemy.sprite) + ".png", "enemy-portrait", lazy));
  const element = elementNames[enemy.element] ?? enemy.element;
  if (element) tile.append(artwork("/elements/" + encodeURIComponent(element.toLowerCase()) + ".png", "cell-element", lazy));
  if (enemy.boss) tile.append(artwork("/orbital-lift/boss-crown.png", "cell-crown", lazy));
}

function enemyChooser(onPick) {
  const dialog = $("enemy-picker"), gallery = $("enemy-choices");
  const search = $("enemy-search"), element = $("enemy-element");
  let roster, renderedRoster;

  function resetFilters() {
    search.value = "";
    element.value = "";
    filter();
  }

  function filter() {
    const query = search.value.trim().toLowerCase();
    let count = 0;
    for (const card of gallery.children) {
      const matches = query.startsWith("#") ? card.dataset.id === query.slice(1) : card.dataset.search.includes(query);
      card.hidden = !matches ||
        (element.value !== "" && card.dataset.element !== element.value);
      if (!card.hidden) count++;
    }
    gallery.scrollTop = 0;
    gallery.hidden = count === 0;
    $("no-enemies").hidden = count !== 0;
    $("enemy-results").textContent = count + (count === 1 ? " enemy" : " enemies");
  }

  function buildGallery() {
    const elements = new Set();
    const cards = [];
    for (const enemy of roster) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "enemy-card";
      card.dataset.id = enemy.id;
      card.dataset.element = elementNames[enemy.element] ?? (enemy.element || "Unknown");
      card.dataset.search = enemy.name.toLowerCase() + " " + enemy.id;
      elements.add(card.dataset.element);
      const name = document.createElement("strong");
      name.textContent = enemy.name;
      const id = document.createElement("span");
      id.className = "card-id";
      id.textContent = "#" + enemy.id;
      card.title = [enemy.name, card.dataset.element, id.textContent].join(" · ");
      card.setAttribute("aria-label", card.title);
      addEnemyArt(card, enemy, true);
      card.append(name, id);
      card.onclick = () => { dialog.close(); onPick(enemy.id); };
      cards.push(card);
    }
    gallery.replaceChildren(...cards);
    element.replaceChildren(new Option("All elements", ""), ...[...elements].sort().map(e => new Option(e, e)));
    renderedRoster = roster;
  }

  search.oninput = element.onchange = filter;
  $("reset-enemy-filters").onclick = () => { resetFilters(); search.focus(); };
  $("picker-close").onclick = () => dialog.close();
  dialog.onclick = event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right ||
        event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  };
  return {
    setRoster(enemies) { roster = enemies; },
    close() { if (dialog.open) dialog.close(); },
    open(floor, cell, enemy) {
      if (renderedRoster !== roster) buildGallery();
      $("enemy-picker-title").textContent = enemy ? "Replace enemy" : "Add an enemy";
      $("enemy-picker-target").textContent = "Floor " + floor + " · Cell " + cell +
        (enemy ? " · " + enemy.name : "");
      $("board-move").hidden = $("board-remove").hidden = !enemy;
      $("board-edit-elite").hidden = !enemy?.elites?.length;
      for (const card of gallery.children) {
        card.setAttribute("aria-pressed", String(Number(card.dataset.id) === enemy?.id));
      }
      resetFilters();
      dialog.showModal();
      if (matchMedia("(pointer: fine)").matches) search.focus();
    },
  };
}

export function startBoard(nextFloor, onSave) {
  let state, enemies, units, originalDraft, selected = positions[0], moving = null;
  let current = nextFloor >= 1 && nextFloor <= 1500 ? nextFloor : 1;
  const level = $("board-level"), picker = $("board-floor");
  const unitAt = pos => units.find(unit => unit.position === pos);
  const originalElite = unit => state.floor.originalElites?.[unit?.origin] ?? null;
  const eliteOf = unit => unit && Object.hasOwn(unit, "elite") ? unit.elite : originalElite(unit);
  const modifier = $("unit-modifier");
  const draft = () => JSON.stringify([units, level.value]);
  const chooser = enemyChooser(enemy => {
    const idx = units.findIndex(unit => unit.position === selected);
    if (idx !== -1 && units[idx].enemy === enemy) return;
    const replacement = {position: selected, enemy};
    if (idx < 0) units.push(replacement);
    else units[idx] = replacement;
    message("");
    render();
  });

  function buttons() {
    const dirty = draft() !== originalDraft;
    $("board-dirty").hidden = !dirty;
    $("board-save").disabled = !dirty || !level.validity.valid ||
      (!units.length && state.floor.type !== "RecordRoom");
    $("board-restore").disabled = !state.custom;
  }

  function move(from, to) {
    const a = unitAt(from), b = unitAt(to);
    if (a && from !== to) {
      a.position = to;
      if (b) b.position = from;
    }
    moving = null;
    selected = to;
    message("");
    render();
  }

  const cells = positions.map(pos => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "board-cell";
    button.dataset.position = pos;
    button.onclick = () => {
      if (moving !== null) move(moving, pos);
      else {
        selected = pos;
        render();
        chooser.open(current, pos, enemies.get(unitAt(pos)?.enemy));
      }
    };
    button.ondragstart = event => event.dataTransfer.setData("application/x-orbital-cell", String(pos));
    button.ondragover = event => event.preventDefault();
    button.ondrop = event => {
      event.preventDefault();
      const from = Number(event.dataTransfer.getData("application/x-orbital-cell"));
      if (!$("board-controls").disabled && unitAt(from)) move(from, pos);
    };
    return button;
  });
  $("board-grid").replaceChildren(...cells);

  function render() {
    for (const button of cells) {
      const pos = Number(button.dataset.position);
      const unit = unitAt(pos);
      const enemy = enemies.get(unit?.enemy);
      const elite = eliteOf(unit);
      const element = elementNames[enemy?.element] ?? enemy?.element;
      button.draggable = Boolean(enemy);
      button.dataset.occupied = String(button.draggable);
      button.dataset.elite = String(elite !== null);
      button.setAttribute("aria-pressed", String(pos === selected));
      button.setAttribute("aria-haspopup", moving === null ? "dialog" : "false");
      button.title = ["Cell " + pos, enemy?.name ?? "Empty", element, enemy?.boss ? "Boss" : "", state.eliteNames?.[elite]].filter(Boolean).join(" · ");
      button.setAttribute("aria-label", button.title);
      const ident = String(enemy?.id ?? "");
      if (button.dataset.enemy === ident) continue;
      button.dataset.enemy = ident;
      const number = document.createElement("span");
      number.className = "cell-number";
      number.textContent = pos;
      const label = document.createElement("span");
      label.className = "cell-name";
      label.textContent = enemy?.name ?? "+";
      button.replaceChildren(number);
      if (enemy) {
        addEnemyArt(button, enemy);
      } else {
        button.append(artwork("/orbital-lift/empty-cell.png", "empty-emblem"));
      }
      button.append(label);
    }
    const unit = unitAt(selected), enemy = enemies.get(unit?.enemy);
    $("modifier-field").hidden = !enemy;
    if (enemy) {
      const allowed = enemy.elites ?? [];
      $("modifier-target").textContent = "Cell " + selected + " · " + enemy.name;
      modifier.replaceChildren(new Option("None", ""), ...allowed.map(id => new Option(state.eliteNames[id], id)));
      modifier.value = eliteOf(unit) ?? "";
      modifier.disabled = !allowed.length;
    }
    $("board-count").textContent = units.length + (units.length === 1 ? " enemy" : " enemies");
    $("board-cancel-move").hidden = moving === null;
    $("board-hint").textContent = moving !== null ? "Choose a destination to move or swap the enemy in cell " + moving + "."
      : !units.length && state.floor.type !== "RecordRoom" ? "Add at least one enemy to save this combat floor."
      : !units.length && state.floor.type === "RecordRoom" ? "Select a cell to add an enemy and turn this room into a combat floor."
      : "Select a cell to change its enemy or elite modifier. Drag enemies to swap positions.";
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

  function showModifiedFloors() {
    const floors = state.modifiedFloors;
    $("modified-floors").hidden = !floors;
    if (!floors) return;
    $("modified-count").textContent = floors.length;
    const list = $("modified-list");
    list.replaceChildren(...floors.map(number => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Floor " + number;
      if (number === current) button.setAttribute("aria-current", "true");
      button.onclick = () => {
        if (number !== current) requestFloor(number);
        else {
          picker.value = current;
          busy(false);
        }
      };
      return button;
    }));
    if (!floors.length) list.textContent = "No floors have individual changes.";
    $("modified-global").hidden = state.globalLevel == null;
    $("modified-global").textContent = "Global enemy level: " + state.globalLevel;
  }

  function busy(value) {
    if (value) chooser.close();
    $("modified-floors").disabled = $("board-controls").disabled = $("board-open").disabled = picker.disabled = value;
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
    chooser.setRoster(data.enemies);
    openFloor(number);
    showModifiedFloors();
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

  function requestFloor(number) {
    if (draft() !== originalDraft && !window.confirm("Discard the unsaved board changes?")) {
      picker.value = current;
      busy(false);
      return;
    }
    message("");
    refresh(false, number).catch(error => {
      picker.value = current;
      busy(false);
      message(error.message);
    });
  }
  $("board-picker").onsubmit = event => {
    event.preventDefault();
    if (!picker.disabled && picker.validity.valid) requestFloor(picker.valueAsNumber);
  };
  picker.oninput = () => {
    $("board-controls").disabled = picker.valueAsNumber !== current;
    $("board-open").disabled = !picker.validity.valid;
  };
  level.oninput = () => { message(""); buttons(); };
  modifier.onchange = () => {
    const unit = unitAt(selected);
    const elite = modifier.value === "" ? null : Number(modifier.value);
    if (elite === originalElite(unit)) delete unit.elite;
    else unit.elite = elite;
    message("");
    render();
  };
  $("board-edit-elite").onclick = () => { chooser.close(); modifier.focus(); };
  $("board-remove").onclick = () => {
    chooser.close();
    units = units.filter(unit => unit.position !== selected);
    message("");
    render();
  };
  $("board-move").onclick = () => { chooser.close(); moving = selected; render(); };
  $("board-cancel-move").onclick = () => { moving = null; render(); cells[positions.indexOf(selected)].focus(); };
  $("board-save").onclick = () => save(false);
  $("board-restore").onclick = () => save(true);
  document.addEventListener("orbital-global-level", () => refresh(true).catch(error => message(error.message)));
  refresh().catch(error => message(error.message));
}
