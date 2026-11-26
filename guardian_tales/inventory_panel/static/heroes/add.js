import { $ } from "/inventory-dom.js";

export function collaborationCatalog(json, heroTile, onAdded) {
  const dialog = $("hero-catalog"), grid = $("missing-heroes"), add = $("recruit-hero");
  const api = "/api/game/heroes";
  let candidates = [], selected = null, version = null, writable = false;
  let busy = false, generation = 0, message = "";

  function controls() {
    add.disabled = busy || !writable || !version || !selected;
    add.textContent = selected ? "Add " + selected.name.trim() : "Add to roster";
    $("catalog-close").disabled = busy;
    grid.inert = busy;
    $("hero-catalog-status").textContent = message ||
      (version && !candidates.length ? "You own every available collaboration hero." :
        !writable ? "Close Guardian Tales and stop the backend to add a hero." : "");
  }

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
      grid.replaceChildren(...candidates.map(h => heroTile(h, false, "Catalog #")));
      message = afterConflict && candidates.length ? "The roster changed. Select a hero again." : "";
    } catch (error) {
      if (ticket !== generation || !dialog.open) return;
      message = error.message;
    }
    controls();
  }

  $("open-hero-catalog").onclick = () => {
    if (dialog.open || busy) return;
    dialog.showModal();
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
