import { $ } from "/inventory-dom.js";

export function copyUnlock(api, version, onUnlocked, reload, note) {
  const button = $("unlock-copy"), workspace = document.querySelector(".workspace");
  let selected, writable = false, busy = false;

  function update() {
    button.hidden = selected?.locked !== true;
    button.disabled = busy || !writable;
  }

  button.onclick = async () => {
    if (!selected?.locked || busy || !writable) return;
    const copy = selected;
    busy = true;
    workspace.inert = true;
    update();
    try {
      const response = await fetch(api + "/unlock", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: copy.id, spec: copy.spec, version: version()}),
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 423) writable = false;
        if (response.status === 409) await reload();
        note(result.error || "Could not unlock this copy.", true);
        return;
      }
      copy.locked = false;
      onUnlocked(result);
      note("Copy #" + copy.id + " unlocked.");
    } catch {
      note("Could not verify the unlock. Reload the inventory to check this copy.", true);
    } finally {
      workspace.inert = false;
      busy = false;
      update();
    }
  };

  return {
    select(copy) { selected = copy; update(); },
    setWritable(value) { writable = value; update(); },
  };
}
