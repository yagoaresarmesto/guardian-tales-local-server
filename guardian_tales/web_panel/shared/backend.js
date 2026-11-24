const root = document.getElementById("service-controls");

async function services() {
  const response = await fetch("/api/services", {cache: "no-store", signal: AbortSignal.timeout(2500)});
  if (!response.ok) throw new Error("Could not read local services.");
  return (await response.json()).services;
}

if (root) {
  const menu = document.createElement("details");
  menu.className = "service-menu";
  const heading = document.createElement("summary");
  heading.textContent = "Services";
  const popover = document.createElement("div");
  popover.className = "service-popover";
  const list = document.createElement("div");
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  popover.append(list, status);
  menu.append(heading, popover);
  root.append(menu);
  let pending = false;

  function render(rows) {
    list.replaceChildren();
    for (const row of rows) {
      const line = document.createElement("div");
      line.className = "service-row";
      const label = document.createElement("span");
      const repeated = rows.filter(other => other.id === row.id).length > 1;
      label.textContent = row.label + (repeated ? " (" + row.port + ")" : "");
      const action = document.createElement("button");
      action.type = "button";
      action.disabled = pending || !row.instance;
      action.textContent = row.instance ? "Restart" : "Offline";
      action.setAttribute("aria-label", "Restart " + label.textContent);
      action.onclick = () => restart(row);
      line.append(label, action);
      list.append(line);
    }
  }

  async function restart(row) {
    if (pending) return;
    pending = true;
    for (const btn of list.querySelectorAll("button")) btn.disabled = true;
    status.textContent = "Restarting " + row.label + "…";
    try {
      const reply = await fetch("/api/services/restart", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: row.id, instance: row.instance}), signal: AbortSignal.timeout(5000),
      });
      if (!reply.ok) throw new Error((await reply.json()).error);
      for (let attempt = 0; attempt < 45; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 750));
        let rows;
        try { rows = await services(); } catch { continue; }
        const fresh = rows.find(s => s.id === row.id && s.port === row.port && s.instance !== row.instance);
        if (fresh) {
          status.textContent = row.label + " restarted.";
          return;
        }
      }
      throw new Error(row.label + " has not returned. Check its terminal.");
    } catch (error) {
      status.textContent = error.message;
    } finally {
      pending = false;
      try { render(await services()); } catch { list.replaceChildren(); }
    }
  }

  menu.addEventListener("toggle", async () => {
    if (menu.open && !pending) {
      try { render(await services()); } catch (error) { status.textContent = error.message; }
    }
  });
  menu.addEventListener("keydown", event => {
    if (event.key === "Escape") { menu.open = false; heading.focus(); }
  });
  document.addEventListener("pointerdown", event => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
}
