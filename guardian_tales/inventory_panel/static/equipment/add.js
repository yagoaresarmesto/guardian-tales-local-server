import { $, el, watchGridPageSize } from "/inventory-dom.js";

export function equipmentCatalog(types, tile, drawEquipmentArt, onAdded) {
  const dialog = $("equipment-catalog"), choices = $("catalog-items");
  const search = $("catalog-search"), type = $("catalog-type"), confirm = $("catalog-add");
  const status = $("catalog-status");
  let items = [], filtered = [], version, writable, spaceAvailable, busy = false;
  let message = "", request = 0;
  let stars = 0, index = 0, pageSize = 10;
  type.add(new Option("All types", "all"));
  for (const [key, label] of types) type.add(new Option(label, key));
  for (let rating = 0; rating <= 6; rating++) {
    const button = el("button", "", rating ? rating + "★" : "All stars");
    button.type = "button";
    button.setAttribute("aria-label", rating ? rating + (rating === 1 ? " star" : " stars") : "All stars");
    button.onclick = () => { stars = rating; filter(); };
    $("catalog-ratings").append(button);
  }

  function state() {
    confirm.disabled = busy || !version || !filtered[index] || !writable || !spaceAvailable;
    $("catalog-close").disabled = busy;
    dialog.querySelector(".catalog-body").inert = busy;
    status.textContent = message || (!writable ? "Close Guardian Tales and stop the backend to add equipment." :
      !spaceAvailable ? "An available equipment slot is required." : "");
  }

  function preview() {
    const item = filtered[index];
    $("catalog-preview").hidden = !item;
    if (item) {
      drawEquipmentArt($("catalog-art"), item);
      $("catalog-name").textContent = item.name;
      $("catalog-stars").textContent = "★".repeat(item.stars);
      $("catalog-stars").setAttribute("aria-label", item.stars + " stars");
      $("catalog-facts").textContent = "Lv. 1 · #" + item.spec;
      $("catalog-kind").textContent = types.get(item.kind);
      $("catalog-exclusive").hidden = !item.exclusiveHero;
      $("catalog-exclusive").textContent = item.exclusiveHero ? "Exclusive to " +
        (item.exclusiveHeroName || "hero #" + item.exclusiveHero) : "";
    }
    state();
  }

  function drawPage() {
    const start = Math.floor(index / pageSize) * pageSize;
    const page = filtered.slice(start, start + pageSize);
    choices.replaceChildren(...page.map(item => tile({...item, id: item.spec},
      item === filtered[index], "Catalog #")));
    $("catalog-empty").hidden = !!page.length || !version;
    $("catalog-range").textContent = page.length ? (start + 1) + "–" + (start + page.length) +
      " of " + filtered.length : "0 items";
    $("catalog-previous").disabled = start === 0;
    $("catalog-next").disabled = start + page.length >= filtered.length;
    preview();
  }

  function filter() {
    const previous = filtered[index];
    const query = search.value.trim().replace(/^#/, "").toLowerCase();
    filtered = items.filter(i => (!stars || i.stars === stars) && (type.value === "all" || i.kind === type.value) &&
      (i.name.toLowerCase().includes(query) || String(i.spec).includes(query)));
    index = Math.max(0, filtered.indexOf(previous));
    Array.from($("catalog-ratings").children).forEach((button, rating) =>
      button.setAttribute("aria-pressed", String(rating === stars)));
    drawPage();
  }

  search.oninput = type.onchange = filter;
  choices.onclick = event => {
    const button = event.target.closest("button[data-id]");
    if (!button) return;
    index = filtered.findIndex(i => i.spec === Number(button.dataset.id));
    for (const choice of choices.children) choice.setAttribute("aria-pressed", String(choice === button));
    preview();
  };
  function turnPage(delta) {
    index = (Math.floor(index / pageSize) + delta) * pageSize;
    drawPage();
  }
  $("catalog-previous").onclick = () => turnPage(-1);
  $("catalog-next").onclick = () => turnPage(1);
  watchGridPageSize(choices, size => { pageSize = size; drawPage(); }, 2);
  $("catalog-close").onclick = () => dialog.close();
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  confirm.onclick = async () => {
    if (confirm.disabled) return;
    const item = filtered[index];
    busy = true;
    message = "Adding " + item.name + "…";
    state();
    try {
      const response = await fetch("/api/game/equipment/add", {method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({spec: item.spec, version})});
      const data = await response.json();
      if (!response.ok) {
        message = data.error || "Could not add equipment.";
        if (response.status === 409) message += " Reopen the catalog to refresh it.";
        if (response.status === 423) {
          writable = false;
        } else {
          version = null;
        }
        return;
      }
      dialog.close();
      await onAdded(data.id, item);
    } catch {
      version = null;
      message = "Could not confirm the result. Reload Equipment to check your inventory.";
    } finally {
      busy = false;
      state();
    }
  };

  return {
    setWritable(allowed) {
      if (allowed && !writable && version) message = "";
      writable = allowed;
      if (dialog.open) state();
    },
    async open(kind, allowed) {
      if (dialog.open || busy) return;
      const current = ++request;
      items = [];
      version = null;
      writable = allowed;
      message = "Loading equipment…";
      stars = 0;
      type.value = types.has(kind) ? kind : "all";
      search.value = "";
      filter();
      dialog.showModal();
      search.focus();
      try {
        const res = await fetch("/api/game/equipment/catalog", {cache: "no-store"});
        if (!res.ok) throw new Error("Could not load the equipment catalog.");
        const data = await res.json();
        if (current !== request || !dialog.open) return;
        items = data.items.sort((a, b) => a.name.localeCompare(b.name) || a.stars - b.stars || a.spec - b.spec);
        version = data.version;
        spaceAvailable = data.spaceAvailable;
        writable = data.writable;
        message = "";
        filter();
      } catch (error) {
        if (current !== request || !dialog.open) return;
        message = error.message;
        state();
      }
    },
  };
}
