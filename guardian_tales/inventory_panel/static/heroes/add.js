import { $ } from "/inventory-dom.js";

export function heroCatalog(json, heroTile, onAdded) {
  const dialog = $("hero-catalog"), grid = $("missing-heroes"), add = $("recruit-hero");
  const search = $("missing-search");
  const api = "/api/game/heroes";
  let candidates = [], selected = null, version = null, writable = false;
  let busy = false, generation = 0, message = "";

  function controls() {
    add.disabled = busy || !writable || !version || !selected;
    add.textContent = selected ? "Add " + selected.name.trim() : "Add to roster";
    $("catalog-close").disabled = busy;
    grid.inert = busy;
    search.disabled = busy;
    $("hero-catalog-status").textContent = message ||
      (version && !candidates.length ? "You own every available hero." :
        version && !grid.childElementCount ? "No missing heroes match this search." :
        !writable ? "Close Guardian Tales and stop the backend to add a hero." : "");
  }

  function filter() {
    const query = search.value.trim().toLowerCase().replace(/^#/, "");
    const matches = candidates.filter(h => h.name.toLowerCase().includes(query) || String(h.spec).includes(query));
    if (!matches.includes(selected)) selected = null;
    grid.replaceChildren(...matches.map(h => heroTile(h, h === selected, "Catalog #")));
    grid.scrollTop = 0;
    controls();
  }
  search.oninput = filter;

  async function refresh(afterConflict = false) {
    const ticket = ++generation;
    candidates = [];
    selected = version = null;
    grid.replaceChildren();
    message = "Loading missing heroes…";
    controls();
    try {
      const result = await json(api + "/catalog");
      if (ticket !== generation || !dialog.open) return;
      candidates = result.heroes.sort((a, b) => a.name.localeCompare(b.name));
      version = result.version;
      writable = result.writable;
      message = afterConflict && candidates.length ? "The roster changed. Select a hero again." : "";
      filter();
    } catch (error) {
      if (ticket !== generation || !dialog.open) return;
      message = error.message;
    }
    controls();
  }

  $("open-hero-catalog").onclick = () => {
    if (dialog.open || busy) return;
    search.value = "";
    dialog.showModal();
    search.focus();
    refresh();
  };
  $("catalog-close").onclick = () => dialog.close();
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  grid.onclick = event => {
    const button = event.target.closest("button[data-id]");
    if (!button || busy) return;
    selected = candidates.find(h => h.spec === Number(button.dataset.id));
    message = "";
    for (const card of grid.children) card.setAttribute("aria-pressed", String(card === button));
    controls();
  };
  add.onclick = async () => {
    if (add.disabled) return;
    busy = true;
    message = "Adding " + selected.name.trim() + "…";
    controls();
    try {
      const result = await json(api + "/add", {spec: selected.spec, version});
      dialog.close();
      await onAdded(result.id);
    } catch (error) {
      if (error.status === 409) {
        await refresh(true);
      } else if (error.status === 423) {
        writable = false;
        message = "";
      } else {
        version = null;
        message = error.message + " Reopen the catalog to refresh.";
      }
    } finally {
      busy = false;
      controls();
    }
  };
  return { setWritable(value) { writable = value; if (dialog.open) controls(); } };
}
