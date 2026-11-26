import { $, el, inventoryTile, watchGridPageSize } from "/inventory-dom.js";

const api = "/api/game/heroes";
let heroes = [], selected = null, detail = null, page = 0, pageSize = 24;
let generation = 0, applying = false, writable = false;
let pendingReset = null;

async function json(url, body) {
  const options = { cache: "no-store" };
  if (body) Object.assign(options, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "Could not load the roster.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function tell(text = "", error = false) {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
  $("message").hidden = !text;
}

function updateAccess(allowed) {
  writable = allowed;
  $("access").hidden = writable;
  $("access").textContent = "Close Guardian Tales and stop the game backend to edit heroes.";
  $("apply").disabled = applying || !writable || !detail?.actions[$("action").value];
  $("max-hero").disabled = applying || !writable || !detail || !Object.keys(detail.actions).length;
  $("hero-reset").disabled = applying || !writable || !detail?.reset.target;
  $("reset-confirm").disabled = $("hero-reset").disabled || !pendingReset;
  $("reset-access").hidden = writable;
}

async function checkAccess() {
  if (document.hidden) return;
  try { updateAccess((await json("/api/game/status")).writable === true); }
  catch { updateAccess(false); }
}

function sprite(hero, className) {
  const box = el("span", className);
  if (hero.sprite || hero.spriteFallback) {
    const img = el("img");
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.onerror = () => {
      img.onerror = () => img.remove();
      if (hero.sprite && hero.spriteFallback) img.src = hero.spriteFallback;
      else img.remove();
    };
    img.src = hero.sprite || hero.spriteFallback;
    box.append(img);
  }
  return box;
}

function rarityLabel(hero) {
  switch (hero.starStyle) {
    case "collab": return hero.form ? "Collaboration " + hero.form : "Collaboration";
    case "promote_silver": return hero.form === "Myth" ? "Ascended Myth" : "Ascended";
    case "bronze": return "Normal";
    case "silver": return "Rare";
    case "gold": return "Unique";
    default: return hero.form;
  }
}

function rankStars(hero) {
  const row = el("span", "rank-stars");
  if (!hero.stars) return row;
  row.dataset.starStyle = hero.starStyle || "";
  row.title = [hero.stars + (hero.stars === 1 ? " star" : " stars"), rarityLabel(hero)].filter(Boolean).join(" · ");
  row.setAttribute("role", "img");
  row.setAttribute("aria-label", row.title);
  const fallback = () => el("span", "rank-star fallback-star");
  for (let i = 0; i < hero.stars; i++) {
    if (hero.starStyle) {
      const img = el("img", "rank-star");
      img.alt = "";
      img.onerror = () => img.replaceWith(fallback());
      img.src = "/heroes/stars/" + hero.starStyle + ".png";
      row.append(img);
    } else row.append(fallback());
  }
  return row;
}

function draw() {
  const query = $("search").value.trim().toLowerCase();
  const element = $("element").value;
  const items = heroes.filter(h => (!element || h.element === element)
    && (!$("upgradable").checked || h.upgradable)
    && [h.name, h.id, h.spec, h.form].some(v => String(v).toLowerCase().includes(query)));
  const sort = $("sort").value;
  items.sort((a, b) => (sort === "low" ? a.level - b.level : sort === "high" ? b.level - a.level : 0)
    || a.name.localeCompare(b.name) || a.id - b.id);
  page = Math.max(0, Math.min(page, Math.ceil(items.length / pageSize) - 1));
  const start = page * pageSize;
  const cards = items.slice(start, start + pageSize).map(h => {
    const card = inventoryTile({ id: h.id, idLabel: "Hero #", name: h.name, art: sprite(h, "tile-art"),
      selected: h.id === selected, level: h.level, stars: h.stars });
    if (h.element) {
      const icon = el("img", "element-icon");
      icon.alt = h.element;
      icon.src = "/elements/" + h.element.toLowerCase() + ".png";
      card.querySelector(".tile-header").append(icon);
    }
    card.dataset.starStyle = h.starStyle || "";
    card.querySelector(".tile-stars").replaceChildren(rankStars(h));
    const rarity = rarityLabel(h);
    if (rarity) {
      card.title += " · " + rarity;
      card.setAttribute("aria-label", card.title);
    }
    card.disabled = applying;
    return card;
  });
  $("tiles").replaceChildren(...cards);
  $("empty").hidden = items.length > 0;
  $("range").textContent = items.length ? (start + 1) + "–" + (start + cards.length) + " of " + items.length : "0 heroes";
  $("previous").disabled = page === 0;
  $("next").disabled = start + pageSize >= items.length;
}

function targets() {
  const option = detail?.actions[$("action").value];
  $("target").replaceChildren(...(option?.choices || []).map(c => new Option(c.label, c.value)));
  updateAccess(writable);
}

function display(result, preferredAction) {
  detail = result;
  const hero = result.hero;
  $("placeholder").hidden = true;
  $("detail").hidden = false;
  $("hero-art").replaceChildren(...sprite(hero).childNodes);
  $("copy-id").textContent = "#" + hero.id;
  $("hero-name").textContent = hero.name;
  $("hero-element").textContent = [hero.element, rarityLabel(hero)].filter(Boolean).join(" · ");
  $("hero-stars").replaceChildren(rankStars(hero));
  $("facts").replaceChildren(...Object.entries(result.stats).map(([label, value]) => {
    const row = el("div");
    row.append(el("dt", "", label), el("dd", "", value));
    return row;
  }));
  const options = Object.entries(result.actions);
  $("action").replaceChildren(...options.map(([key, option]) => new Option(option.label, key)));
  if (preferredAction && result.actions[preferredAction]) $("action").value = preferredAction;
  $("training").hidden = !result.trainingRoom;
  $("upgrade").hidden = options.length === 0;
  $("unavailable").hidden = options.length > 0;
  $("reset-reason").textContent = result.reset.reason || "";
  $("reset-reason").hidden = !result.reset.reason;
  targets();
}

async function selectHero(id, scroll = false) {
  if (applying) return;
  const ticket = ++generation;
  selected = id;
  detail = null;
  tell();
  $("copy-id").textContent = "";
  $("detail").hidden = true;
  $("placeholder").hidden = false;
  $("placeholder").textContent = "Loading hero…";
  draw();
  if (scroll && matchMedia("(max-width:680px)").matches) $("inspector").scrollIntoView({ block: "start" });
  try {
    const result = await json(api + "/" + id);
    if (generation === ticket) display(result);
  } catch (error) {
    if (generation === ticket) $("placeholder").textContent = error.message;
  }
}

async function load() {
  if (applying) return;
  const ticket = ++generation;
  const prior = selected;
  detail = null;
  updateAccess(writable);
  try {
    const data = await json(api);
    if (ticket !== generation) return;
    heroes = data.heroes;
    const previousElement = $("element").value;
    const elements = [...new Set(heroes.map(h => h.element).filter(Boolean))].sort();
    $("element").replaceChildren(new Option("All elements", ""), ...elements.map(e => new Option(e, e)));
    if (elements.includes(previousElement)) $("element").value = previousElement;
    $("owned-count").hidden = false;
    $("owned-count").textContent = heroes.length + " owned";
    updateAccess(data.writable);
    draw();
    if (heroes.some(h => h.id === prior)) await selectHero(prior);
    else {
      selected = null;
      $("detail").hidden = true;
      $("placeholder").hidden = false;
      $("placeholder").textContent = "Select a hero to view their progress.";
    }
  } catch (error) {
    if (ticket === generation) $("range").textContent = error.message;
  }
}

$("tiles").onclick = event => {
  const card = event.target.closest("button[data-id]");
  if (card) selectHero(Number(card.dataset.id), true);
};
function applyUpgrade(maxHero) {
  if (applying || !writable || !detail) return;
  const action = maxHero ? "max" : $("action").value;
  const body = { id: selected, version: detail.version, action };
  let message = detail.hero.name + " · All available upgrades applied.";
  if (!maxHero) {
    const target = $("target").selectedOptions[0];
    body.value = Number(target.value);
    message = detail.hero.name + " · " + target.text + " applied.";
  }
  return applyChange(body, message, maxHero ? "Applying all available upgrades…" : "");
}

async function applyChange(body, message, progress) {
  if (applying || !writable || !detail || body.id !== selected || body.version !== detail.version) return;
  applying = true;
  $("action").disabled = $("target").disabled = $("refresh").disabled = true;
  tell(progress);
  updateAccess(writable);
  draw();
  try {
    const result = await json(api, body);
    const index = heroes.findIndex(h => h.id === selected);
    heroes[index] = { ...result.hero, upgradable: Object.keys(result.actions).length > 0 };
    display(result, body.action);
    tell(message);
  } catch (error) {
    if (error.status === 409) detail = null;
    if (error.status === 423) updateAccess(false);
    tell(error.message, true);
  } finally {
    applying = false;
    $("action").disabled = $("target").disabled = $("refresh").disabled = false;
    updateAccess(writable);
    draw();
  }
}
$("upgrade").onsubmit = event => { event.preventDefault(); applyUpgrade(false); };
$("max-hero").onclick = () => applyUpgrade(true);
$("hero-reset").onclick = () => {
  if (applying || !writable || !detail?.reset.target) return;
  const target = detail.reset.target;
  pendingReset = { id: selected, version: detail.version, action: "reset" };
  $("reset-heading").textContent = "Reset " + detail.hero.name + "?";
  $("reset-name").textContent = target.name + " · #" + selected;
  $("reset-result").replaceChildren("After reset · Level " + target.level + " · ", rankStars(target));
  $("reset-art").replaceChildren(...sprite(target).childNodes);
  updateAccess(writable);
  $("reset-dialog").showModal();
};
$("reset-cancel").onclick = () => $("reset-dialog").close();
$("reset-dialog").onclose = () => { if (!$("reset-dialog").open) pendingReset = null; };
$("reset-confirm").onclick = () => {
  if (!pendingReset || $("reset-confirm").disabled) return;
  const body = pendingReset;
  $("reset-dialog").close();
  applyChange(body, detail.hero.name + " · Hero reset applied.", "Resetting hero…");
};
$("search").oninput = $("element").onchange = $("sort").onchange = $("upgradable").onchange = () => { page = 0; draw(); };
$("action").onchange = () => { targets(); tell(); };
$("previous").onclick = () => { page--; draw(); };
$("next").onclick = () => { page++; draw(); };
$("refresh").onclick = load;
watchGridPageSize($("tiles"), count => { pageSize = count; draw(); });
window.addEventListener("focus", checkAccess);
setInterval(checkAccess, 5000);
load();
