const root = document.getElementById("service-controls");

async function services() {
  const response = await fetch("/api/services", {cache: "no-store", signal: AbortSignal.timeout(2500)});
  if (!response.ok) throw new Error("Could not read local services.");
  return (await response.json()).services;
}

const expiryFormat = new Intl.DateTimeFormat(undefined, {
  year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
});

function certificateDates(expiry) {
  const dates = document.createElement("dl");
  dates.className = "service-certificates";
  for (const [key, label] of [["server", "Server certificate expires"], ["authority", "Certificate authority expires"]]) {
    const term = document.createElement("dt");
    term.textContent = label;
    const value = document.createElement("dd");
    const timestamp = Date.parse(expiry?.[key]);
    if (Number.isFinite(timestamp)) {
      const time = document.createElement("time");
      time.dateTime = expiry[key];
      time.textContent = expiryFormat.format(timestamp);
      value.append(time);
    } else {
      value.textContent = "Unavailable";
    }
    dates.append(term, value);
  }
  return dates;
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
      label.textContent = row.label + (repeated ? " (" + row.port + ")" : "") +
        (row.stopped ? " (stopped)" : "");
      const actions = document.createElement("div");
      actions.className = "service-actions";
      if (row.id === "game") {
        const stop = document.createElement("button");
        stop.type = "button";
        stop.disabled = pending || !row.canStop;
        stop.textContent = "Stop";
        stop.setAttribute("aria-label", "Stop " + row.label);
        stop.title = "Close Guardian Tales, then stop the backend for inventory edits.";
        stop.onclick = () => control(row, "stop");
        actions.append(stop);
      }
      const action = document.createElement("button");
      action.type = "button";
      action.disabled = pending || !row.instance;
      action.textContent = row.instance ? "Restart" : "Offline";
      action.setAttribute("aria-label", "Restart " + label.textContent);
      action.onclick = () => control(row, "restart");
      actions.append(action);
      line.append(label, actions);
      if (row.id === "game" && row.instance) line.append(certificateDates(row.certificateExpiry));
      list.append(line);
    }
  }

  async function control(row, action) {
    if (pending) return;
    pending = true;
    for (const btn of list.querySelectorAll("button")) btn.disabled = true;
    const stopping = action === "stop";
    status.textContent = (stopping ? "Stopping " : "Restarting ") + row.label + "…";
    try {
      const reply = await fetch("/api/services/" + action, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: row.id, instance: row.instance}), signal: AbortSignal.timeout(5000),
      });
      if (!reply.ok) throw new Error((await reply.json()).error);
      for (let attempt = 0; attempt < 45; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 750));
        let rows;
        try { rows = await services(); } catch { continue; }
        const ready = rows.find(s => s.id === row.id && s.port === row.port &&
          (stopping ? s.stopped : s.instance && s.instance !== row.instance));
        if (ready) {
          status.textContent = stopping ? "Game backend stopped. Inventory editing is available. " +
            "Choose Restart when finished, then reopen Guardian Tales." : row.label + " restarted.";
          return;
        }
      }
      throw new Error(row.label + (stopping ? " has not stopped." : " has not returned.") + " Check its terminal.");
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
