import { $ } from "/panel.js";
import { createScene, floorPitch, mapData } from "/orbital-tower-scene.js";

const shafts = {
  tetis: {min: 1, max: 1000, step: -1},
  colony: {min: 1001, max: 1500, step: 1},
};
const bounded = (number, min, max) => Math.min(max, Math.max(min, number));

export function startTower() {
  const scroll = $("lift-scroll"), track = $("lift-track"), destination = $("lift-destination");
  let shaft = shafts.tetis, selected = 1, position = 1, scale = 1;
  let progress, catalog, editor, frame = 0, width = 0, height = 0;
  let pendingClick = null;
  const remembered = new Map([[shafts.tetis, 1], [shafts.colony, 1001]]);
  const origin = () => shaft.step < 0 ? shaft.max : shaft.min;
  const pitch = () => floorPitch * scale;

  function redraw() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      draw(width, height, scale, position, shaft === shafts.colony, selected, progress?.clearedFloor, catalog?.floors);
    });
  }
  const draw = createScene($("lift-scene"), redraw);

  function describe() {
    const entry = catalog?.floors[selected];
    const here = progress?.nextFloor === selected;
    $("lift-floor-state").textContent = here ? "Current location" : !progress ? "Floor preview"
      : selected <= progress.clearedFloor ? "Cleared" : "Uncleared";
    $("lift-floor-title").textContent = "Floor " + selected;
    const type = entry?.type === "RecordRoom" ? "Record room" : entry?.type;
    $("lift-encounter").textContent = entry ? type + " · Original level " + entry.level : "";
    const rewards = (entry?.rewards ?? []).map(([id, amount]) => {
      const item = document.createElement("li"), icon = new Image();
      const name = catalog.items[id] ?? "Item " + id;
      icon.alt = name;
      icon.src = "/icon/" + id + ".png";
      item.title = name;
      item.append(icon, document.createTextNode(amount.toLocaleString("en")));
      return item;
    });
    $("lift-rewards").replaceChildren(...rewards);
    scroll.setAttribute("aria-valuenow", selected);
    scroll.setAttribute("aria-valuetext", (shaft === shafts.tetis ? "Tetis" : "Colony") + " floor " + selected);
    if (document.activeElement !== destination) destination.value = selected;
    remembered.set(shaft, selected);
  }

  function focusFloor(number) {
    if (!Number.isInteger(number) || number < 1 || number > 1500) return;
    shaft = number <= 1000 ? shafts.tetis : shafts.colony;
    $("shaft-tetis").setAttribute("aria-pressed", shaft === shafts.tetis);
    $("shaft-colony").setAttribute("aria-pressed", shaft === shafts.colony);
    scroll.setAttribute("aria-valuemin", shaft.min);
    scroll.setAttribute("aria-valuemax", shaft.max);
    track.style.height = height + (shaft.max - shaft.min) * pitch() + "px";
    selected = position = number;
    scroll.scrollTop = (number - origin()) * shaft.step * pitch();
    describe();
    redraw();
  }

  function measure() {
    width = scroll.offsetWidth;
    height = scroll.clientHeight;
    scale = Math.max(.65, Math.min(width / 450, 1.9));
    focusFloor(selected);
  }
  measure();
  new ResizeObserver(measure).observe(scroll);
  window.addEventListener("resize", redraw);

  async function openCabin(number) {
    focusFloor(number);
    if (!editor) {
      pendingClick = number;
      return;
    }
    pendingClick = null;
    const opened = await editor(number, false);
    if (selected === number && opened !== number) focusFloor(opened);
  }

  scroll.onscroll = () => {
    position = bounded(origin() + shaft.step * scroll.scrollTop / pitch(), shaft.min, shaft.max);
    const nearest = Math.round(position);
    if (nearest !== selected) { selected = nearest; describe(); }
    redraw();
  };
  scroll.onclick = event => {
    const bounds = scroll.getBoundingClientRect();
    const y = event.clientY - bounds.top;
    const number = Math.round(position + shaft.step * (y - height / 2) / pitch());
    if (number < shaft.min || number > shaft.max) return;
    const halfWidth = catalog?.floors[number]?.type === "RecordRoom" ? 227 : 144;
    if (Math.abs(event.clientX - bounds.left - width / 2) <= halfWidth * scale) openCabin(number);
  };
  scroll.onkeydown = event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openCabin(selected);
      return;
    }
    const page = Math.max(1, Math.floor(height / pitch()) - 1);
    const next = {ArrowUp: selected - shaft.step, ArrowDown: selected + shaft.step,
      PageUp: selected - page * shaft.step, PageDown: selected + page * shaft.step,
      Home: origin(), End: shaft.step > 0 ? shaft.max : shaft.min}[event.key];
    if (next !== undefined) {
      event.preventDefault();
      focusFloor(bounded(next, shaft.min, shaft.max));
    }
  };
  $("shaft-tetis").onclick = () => focusFloor(remembered.get(shafts.tetis));
  $("shaft-colony").onclick = () => focusFloor(remembered.get(shafts.colony));
  $("lift-jump").onsubmit = event => {
    event.preventDefault();
    focusFloor(destination.valueAsNumber);
    scroll.focus({preventScroll: true});
  };
  const location = () => bounded(progress?.nextFloor ?? progress?.clearedFloor ?? 1, 1, 1500);
  $("lift-locate").onclick = () => focusFloor(location());
  $("lift-edit").onclick = () => editor?.(selected, true);

  mapData("/api/orbital-lift/map").then(data => {
    catalog = {
      items: data.items,
      floors: [null, ...data.floors.map(([type, level, rewards]) => ({type, level, rewards: data.rewardSets[rewards]}))],
    };
    describe();
    redraw();
  }).catch(() => { $("lift-encounter").textContent = "Floor details unavailable"; });

  return {
    setProgress(data) {
      const initial = !progress;
      progress = data;
      $("lift-locate").disabled = false;
      if (initial) focusFloor(location());
      else { describe(); redraw(); }
    },
    setEditor(open) {
      editor = open;
      $("lift-edit").disabled = !open;
      if (open && pendingClick != null) {
        const number = pendingClick;
        pendingClick = null;
        queueMicrotask(() => openCabin(number));
      }
    },
  };
}
