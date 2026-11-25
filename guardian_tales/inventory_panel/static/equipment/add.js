import { $ } from "/inventory-dom.js";

export function equipmentCatalog(types, art, onAdded) {
  const dialog = $("equipment-catalog"), choices = $("catalog-items");
  const search = $("catalog-search"), type = $("catalog-type"), confirm = $("catalog-add");
  const status = $("catalog-status");
  let items = [], filtered = [], version, writable, spaceAvailable, busy = false;
  let message = "", request = 0;
  type.add(new Option("All types", "all"));
  for (const [key, label] of types) type.add(new Option(label, key));

  function selected() { return filtered[choices.selectedIndex]; }

  function state() {
    confirm.disabled = busy || !version || !selected() || !writable || !spaceAvailable;
    $("catalog-close").disabled = busy;
    choices.disabled = search.disabled = type.disabled = busy;
    status.textContent = message || (!filtered.length ? "No matching equipment." :
      !writable ? "Close Guardian Tales and stop the backend to add equipment." :
      !spaceAvailable ? "An available equipment slot is required." :
      filtered.length + (filtered.length === 1 ? " item" : " items"));
  }

  function preview() {
    const item = selected();
    $("catalog-preview").hidden = !item;
    if (item) {
      const tile = $("catalog-art");
      tile.dataset.equipmentColor = ["normal", "rare", "unique", "legend", "epic"][item.stars - 1];
      tile.replaceChildren(...art(item, "").childNodes);
      $("catalog-name").textContent = item.name;
      $("catalog-stars").textContent = "★".repeat(item.stars);
      $("catalog-stars").setAttribute("aria-label", item.stars + " stars");
      $("catalog-facts").textContent = "Lv. 1 · #" + item.spec;
    }
    state();
  }

  function filter() {
    const previous = selected()?.spec;
    const query = search.value.trim().replace(/^#/, "").toLowerCase();
    filtered = items.filter(i => (type.value === "all" || i.kind === type.value) &&
      (i.name.toLowerCase().includes(query) || String(i.spec).includes(query)));
    choices.replaceChildren(...filtered.map(i => new Option(i.name, i.spec)));
    if (filtered.length) choices.selectedIndex = Math.max(0, filtered.findIndex(i => i.spec === previous));
    preview();
  }

  search.oninput = type.onchange = filter;
  choices.onchange = preview;
  $("catalog-close").onclick = () => dialog.close();
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  confirm.onclick = async () => {
    if (confirm.disabled) return;
    const item = selected();
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
        items = data.items.sort((a, b) => a.name.localeCompare(b.name) || a.spec - b.spec);
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
