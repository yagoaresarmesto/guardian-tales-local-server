import { $, el, image } from "/inventory-dom.js";

export function bulkSelection({api, version, focusId, describe, onProtection, reload}) {
  const workspace = document.querySelector(".workspace"), toolbar = $("bulk-toolbar");
  document.querySelector(".collection-bar").after(toolbar);
  const dialog = $("bulk-dialog"), marked = new Map();
  let pageRows = [], selecting = false, available = false, writable = false, busy = false;
  let reviewError = "";

  function status(text = "", error = false) {
    $("bulk-status").hidden = !text;
    $("bulk-status").textContent = text;
    $("bulk-status").classList.toggle("error", error);
  }
  function deleteBlock(row) {
    if (row.locked) return "Locked";
    if (row.jewels) return "Socketed jewel";
    if (row.training) return "Training Room";
    return "";
  }
  function update() {
    const active = selecting && available;
    const rows = [...marked.values()];
    workspace.classList.toggle("selecting-copies", active);
    $("bulk-toggle").hidden = !available;
    $("bulk-toggle").setAttribute("aria-pressed", String(active));
    $("bulk-toggle").textContent = active ? "Done" : "Select items";
    toolbar.hidden = !active;
    $("bulk-count").textContent = rows.length + " selected";
    $("bulk-page").disabled = !pageRows.length;
    $("bulk-page").textContent = pageRows.length && pageRows.every(r => marked.has(r.id)) ? "Deselect page" : "Select page";
    $("bulk-clear").disabled = !rows.length;
    $("bulk-lock").disabled = busy || !writable || !rows.some(r => !r.locked);
    $("bulk-unlock").disabled = busy || !writable || !rows.some(r => r.locked);
    $("bulk-delete").disabled = busy || !rows.length;
    for (const button of $("tiles").children) {
      const id = Number(button.dataset.id);
      button.setAttribute("aria-pressed", String(active ? marked.has(id) : id === focusId()));
    }
    if (dialog.open) {
      const reason = reviewError || (rows.some(deleteBlock) ? "Omit protected copies or release their protection first." :
        !writable ? "Close Guardian Tales and stop the backend to delete these copies." : "");
      $("bulk-problem").hidden = !reason;
      $("bulk-problem").textContent = reason;
      $("bulk-confirm").disabled = busy || !rows.length || !!reason;
      $("bulk-cancel").disabled = busy;
    }
  }
  function review() {
    const rows = [...marked.values()];
    const count = rows.length, copies = count === 1 ? "copy" : "copies";
    const equipped = rows.filter(row => row.equipped).length;
    $("bulk-warning").textContent = "Permanently delete " + count + " " + copies + "?" +
      (equipped ? " This will also unequip " + equipped + "." : "");
    $("bulk-confirm").textContent = "Delete " + count + " " + copies;
    $("bulk-review").replaceChildren(...rows.map(row => {
      const {name, stars} = describe(row);
      const line = el("li"), icon = image("/icon/" + row.spec + ".png");
      icon.loading = "lazy";
      const identity = el("div");
      identity.append(el("strong", "", name), el("small", "", [stars ? stars + "★" : "", "Copy #" + row.id,
        row.equipped ? "Equipped" : "", deleteBlock(row)].filter(Boolean).join(" · ")));
      const omit = el("button", "bulk-omit", "×");
      omit.type = "button";
      omit.dataset.id = row.id;
      omit.setAttribute("aria-label", "Omit copy #" + row.id);
      line.append(icon, identity, omit);
      return line;
    }));
    update();
  }
  $("bulk-toggle").onclick = () => {
    selecting = !selecting;
    marked.clear(); status(); update();
  };
  $("bulk-page").onclick = () => {
    const deselect = pageRows.every(row => marked.has(row.id));
    for (const row of pageRows) {
      if (deselect) marked.delete(row.id); else marked.set(row.id, row);
    }
    status(); update();
  };
  $("bulk-clear").onclick = () => { marked.clear(); status(); update(); };
  $("bulk-delete").onclick = () => {
    reviewError = "";
    dialog.showModal(); review(); $("bulk-cancel").focus();
  };
  $("bulk-review").onclick = e => {
    const button = e.target.closest("button[data-id]");
    if (busy || !button) return;
    marked.delete(Number(button.dataset.id)); reviewError = "";
    if (marked.size) review();
    else { dialog.close(); update(); }
  };
  $("bulk-cancel").onclick = () => dialog.close();
  dialog.oncancel = e => { if (busy) e.preventDefault(); };

  async function apply(action) {
    if (busy || !writable || !marked.size) return;
    const rows = [...marked.values()];
    busy = true; workspace.inert = true; update();
    try {
      const response = await fetch(api + "/" + action, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({copies:rows.map(({id, spec}) => ({id, spec})), version:version()}),
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 423) writable = false;
        if (response.status === 409) {
          if (dialog.open) dialog.close();
          marked.clear();
          await reload();
        }
        throw new Error(result.error || "Could not update the selected copies.");
      }
      const count = rows.length + (rows.length === 1 ? " copy" : " copies");
      if (action === "delete") {
        marked.clear(); dialog.close();
        try { await reload(); }
        catch { status(count + " deleted. Reload the inventory to refresh the list.", true); return; }
        status(count + " deleted.");
      } else {
        for (const row of rows) row.locked = result.locked;
        onProtection(result);
        status(count + (result.locked ? " locked." : " unlocked."));
      }
    } catch (error) {
      if (dialog.open) reviewError = error.message;
      else status(error.message, true);
    } finally {
      busy = false; workspace.inert = false; update();
    }
  }
  $("bulk-lock").onclick = () => apply("lock");
  $("bulk-unlock").onclick = () => apply("unlock");
  $("bulk-confirm").onclick = () => apply("delete");

  return {
    page(rows, enabled = true) {
      pageRows = rows; available = enabled; update();
    },
    toggle(id) {
      if (!selecting || !available) return false;
      const row = pageRows.find(row => row.id === id);
      if (row) {
        if (marked.has(id)) marked.delete(id); else marked.set(id, row);
        status(); update();
      }
      return true;
    },
    reset() { marked.clear(); status(); },
    setWritable(value) { if (writable !== value) { writable = value; update(); } },
  };
}
