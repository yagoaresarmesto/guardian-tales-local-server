import { $ } from "/inventory-dom.js";

export function copyDeletion(api, selection, reload, note) {
  const dialog = $("delete-dialog"), opener = $("delete-copy"), confirm = $("delete-confirm");
  const force = $("delete-force");
  let target, writable = false, busy = false, blocked = "";

  function update() {
    if (!target) return;
    force.disabled = busy;
    $("delete-force-note").hidden = !force.checked;
    confirm.textContent = force.checked ? "Force delete copy" : "Delete copy";
    const protection = target.locked ? "This copy is locked." : target.jewels ? "This relic has socketed jewels." :
      target.training ? "This copy is in the Training Room." : "";
    const reason = blocked || (!writable ? "Close Guardian Tales and stop the backend to delete this copy." :
      protection && !force.checked ? protection + " Release it or choose Force delete." : "");
    $("delete-status").textContent = reason;
    $("delete-status").hidden = !reason;
    confirm.disabled = busy || !!reason;
    $("delete-cancel").disabled = busy;
  }

  opener.onclick = () => {
    target = selection();
    if (!target || busy) return;
    blocked = "";
    force.checked = false;
    $("delete-name").textContent = target.name;
    $("delete-id").textContent = "Copy #" + target.id;
    $("delete-stars").textContent = "★".repeat(target.stars || 0);
    const icon = $("delete-icon");
    icon.onerror = () => { icon.hidden = true; };
    icon.hidden = false;
    icon.src = "/icon/" + target.spec + ".png";
    $("delete-explanation").textContent = target.equipped
      ? "This will unequip and permanently delete this copy."
      : "This will permanently delete this copy.";
    update();
    dialog.showModal();
    $("delete-cancel").focus();
  };
  force.onchange = () => { blocked = ""; update(); };
  $("delete-cancel").onclick = () => dialog.close();
  dialog.oncancel = e => { if (busy) e.preventDefault(); };
  dialog.onclose = () => { target = null; };
  confirm.onclick = async () => {
    if (!target || confirm.disabled) return;
    const { id, spec, version, name, nextId } = target;
    busy = true;
    update();
    try {
      const response = await fetch(api + (force.checked ? "/force-delete" : "/delete"), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id, spec, version}),
      });
      const result = await response.json();
      if (!response.ok) {
        blocked = result.error || "Could not delete this copy.";
        if (response.status === 409) await reload();
        if (response.status === 423) { writable = false; blocked = ""; }
        return;
      }
      const message = name + " · Copy #" + id + " deleted.";
      try {
        await reload(nextId);
        note(message);
      } catch {
        note(message + " Reload the page to refresh your inventory.", true);
      }
      dialog.close();
    } catch {
      blocked = "Could not verify the result. Reload your inventory before trying again.";
    } finally {
      busy = false;
      update();
    }
  };

  return {
    show(available) { opener.hidden = !available; },
    setWritable(value) { writable = value; update(); },
  };
}
