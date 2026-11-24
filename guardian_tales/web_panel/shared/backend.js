const button = document.getElementById("restart-backend");
const status = document.getElementById("restart-status");

async function backend() {
  const response = await fetch("/api/backend", {cache: "no-store", signal: AbortSignal.timeout(3000)});
  if (!response.ok) throw new Error("Backend unavailable");
  return response.json();
}

async function enableRestart() {
  let current;
  try { current = await backend(); } catch { return; }
  if (!current.canRestart) return;
  button.hidden = false;
  button.onclick = async () => {
    button.disabled = true;
    status.textContent = "Restarting…";
    try {
      const reply = await fetch("/api/backend/restart", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({instance: current.instance}),
      });
      if (!reply.ok) throw new Error((await reply.json()).error);
      for (let attempt = 0; attempt < 35; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 700));
        let next;
        try { next = await backend(); } catch { continue; }
        if (next.instance !== current.instance) {
          current = next;
          status.textContent = "Backend restarted.";
          return;
        }
      }
      throw new Error("Backend has not returned. Check its PyCharm tab.");
    } catch (error) {
      status.textContent = error.message;
      try { current = await backend(); } catch { /* Keep the last known instance. */ }
    } finally {
      button.disabled = false;
    }
  };
}

enableRestart();
