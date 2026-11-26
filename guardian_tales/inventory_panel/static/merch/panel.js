import { $, el, image, inventoryTile, renderTypeFilters, selectTypeFilter, watchGridPageSize } from "/inventory-dom.js";

let copies = [], visible = [], selected, rarity = "", page = 0, size = 24;

function sprite(row) {
  const img = image("/icon/" + row.spec + ".png");
  img.onerror = () => img.replaceWith(el("span", "fallback", row.name.slice(0, 2)));
  return img;
}

function drawDetails() {
  $("detail").hidden = !selected;
  $("placeholder").hidden = !!selected;
  $("copy-id").textContent = selected ? "Copy #" + selected.id : "";
  if (!selected) return;
  $("portrait").replaceChildren(sprite(selected));
  $("name").textContent = selected.name;
  $("level").textContent = selected.level == null ? "" : "Lv. " + selected.level;
  $("stars").textContent = "★".repeat(selected.stars);
  $("stars").setAttribute("aria-label", selected.stars + " stars");
  $("equipped").textContent = selected.equipped ? (selected.hero || "Yes") : "No";
  $("protection").textContent = selected.locked ? "Locked" : "Unlocked";
  $("item-id").textContent = selected.spec;
}

function drawGrid() {
  const start = page * size, end = Math.min(start + size, visible.length);
  $("tiles").replaceChildren(...visible.slice(start, end).map(row => {
    const art = el("span", "tile-art");
    art.append(sprite(row));
    return inventoryTile({ ...row, art, selected: row === selected });
  }));
  $("empty").hidden = !!visible.length;
  $("empty").textContent = copies.length ? "No merch matches these filters." : "You have no merch yet.";
  $("range").textContent = visible.length ? (start + 1) + "–" + end + " of " + visible.length : "0 items";
  $("prev").disabled = page === 0;
  $("next").disabled = end >= visible.length;
}

function filter() {
  const query = $("search").value.trim().toLowerCase(), show = $("show").value;
  visible = copies.filter(row =>
    (!rarity || String(row.stars) === rarity) &&
    (show === "all" || (show === "unlocked" ? !row.locked : row[show])) &&
    (!query || row.name.toLowerCase().includes(query) ||
      String(row.id).includes(query) || String(row.spec).includes(query))
  );
  page = 0;
  selected = visible[0];
  selectTypeFilter($("types"), $("mobile-types"), rarity);
  drawGrid();
  drawDetails();
}

function setRarity(value) {
  rarity = value;
  filter();
}
$("types").onclick = event => {
  const button = event.target.closest("button[data-type]");
  if (button) setRarity(button.dataset.type);
};
$("mobile-types").onchange = event => setRarity(event.target.value);
$("search").oninput = $("show").onchange = filter;
$("tiles").onclick = event => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  selected = visible.find(row => row.id === Number(button.dataset.id));
  for (const tile of $("tiles").children) tile.setAttribute("aria-pressed", String(tile === button));
  drawDetails();
  if (matchMedia("(max-width:680px)").matches) document.querySelector(".inspector").scrollIntoView();
};
for (const [id, step] of [["prev", -1], ["next", 1]]) {
  $(id).onclick = () => {
    page += step;
    selected = visible[page * size];
    drawGrid();
    drawDetails();
  };
}
watchGridPageSize($("tiles"), pageSize => {
  size = pageSize;
  if (visible.length) {
    page = Math.floor(visible.indexOf(selected) / size);
    drawGrid();
  }
});

async function load() {
  const response = await fetch("/api/game/merch", {cache: "no-store"});
  if (!response.ok) throw new Error("Could not load merch from the game save.");
  const data = await response.json();
  copies = data.copies.sort((a, b) => b.stars - a.stars || b.level - a.level ||
    a.name.localeCompare(b.name) || a.id - b.id);
  const counts = new Map();
  for (const row of copies) counts.set(row.stars, (counts.get(row.stars) || 0) + 1);
  renderTypeFilters($("types"), $("mobile-types"), [
    {key: "", name: "All rarities", count: copies.length, iconUrl: "/type-icon/all.png"},
    ...Array.from(counts, ([stars, count]) => ({
      key: String(stars), name: stars === 1 ? "1 star" : stars + " stars", count,
    })),
  ]);
  filter();
}
load().catch(error => {
  $("error").textContent = error.message;
  $("error").hidden = false;
  $("range").textContent = "Merch unavailable";
});
