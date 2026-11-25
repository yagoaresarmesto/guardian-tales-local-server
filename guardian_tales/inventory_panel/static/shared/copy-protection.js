import { $ } from "/inventory-dom.js";

export function copyProtection(api, version, onChanged, reload, note) {
  const button = $("copy-protection"), workspace = document.querySelector(".workspace");
  let selected, writable = false, busy = false;

  function update() {
    button.hidden = typeof selected?.locked !== "boolean";
    button.textContent = selected?.locked ? "Unlock" : "Lock";
    button.disabled = busy || !writable;
  }

  button.onclick = async () => {
    if (button.hidden || busy || !writable) return;
    const copy = selected;
    const action = copy.locked ? "unlock" : "lock";
    busy = true;
    workspace.inert = true;
    update();
    try {
      const response = await fetch(api + "/" + action, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: copy.id, spec: copy.spec, version: version()}),
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 423) writable = false;
        if (response.status === 409) await reload();
        note(result.error || "Could not " + action + " this copy.", true);
        return;
      }
      copy.locked = result.locked;
      onChanged(result);
      note("Copy #" + copy.id + (copy.locked ? " locked." : " unlocked."));
    } catch {
      note("Reload the inventory to check this copy’s protection.", true);
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
