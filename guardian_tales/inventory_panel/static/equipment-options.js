import { $, el } from "/inventory-dom.js";

const api = "/api/game/equipment";

export function equipmentOptions(reload, onAccess) {
  let catalog, item, rules, before = {}, draft = {}, savedLocks = new Set(), locked = new Set();
  let writable = false, busy = false, check = 0;
  const progression = weaponProgression(() => { message(); state(); }, format, name);

  function optionsChanged() {
    return Object.keys(rules?.options ?? {}).some(id => draft[id] !== before[id] || locked.has(id) !== savedLocks.has(id));
  }

  function format(id, level) {
    if (level == null) return "Not selected";
    const effect = catalog.effects[id];
    if (!effect || effect.unit === "level") return "Lv. " + level;
    return Number((effect.base + effect.step * level).toFixed(5)) + effect.unit;
  }
  function name(id) { return catalog.effects[id]?.name ?? "Option #" + id; }
  function message(text = "", error = false) {
    $("option-message").textContent = text; $("option-message").hidden = !text;
    $("option-message").classList.toggle("error",error);
  }
  function access(allowed, unavailable = false) {
    writable = allowed === true;
    onAccess(writable);
    $("equipment-access").hidden = writable;
    const text = unavailable ? "Cannot check the game save. Apply is locked until the editor reconnects." :
      "Apply is locked while the game save is in use. Close Guardian Tales and stop the backend to enable it.";
    if (!writable && $("equipment-access").textContent !== text) $("equipment-access").textContent = text;
    state();
  }
  async function poll() {
    if (document.hidden || busy) return;
    const request = ++check;
    try {
      const res = await fetch("/api/game/status",{cache:"no-store",signal:AbortSignal.timeout(4000)});
      if (!res.ok) throw new Error();
      const status = await res.json();
      if (request === check) access(status.writable);
    } catch { if (request === check) access(false,true); }
  }
  window.setInterval(poll,2500);
  document.addEventListener("visibilitychange",poll);
  window.addEventListener("focus",poll);

  function state() {
    if (!item) return;
    const entries = Object.entries(rules?.options ?? {});
    const required = entries.filter(([,r]) => r.probability === 1).map(([id]) => id);
    const optional = entries.filter(([,r]) => r.probability < 1).map(([id]) => id);
    const count = Object.keys(draft).length;
    const initialized = required.every(id => draft[id] != null);
    const changed = optionsChanged();
    const editable = !!rules && !item.unavailable;
    const allowed = rules?.counts ?? [];
    $("basic-options").hidden = !required.length;
    const invalid = changed && (!editable || !initialized || !allowed.includes(count));
    $("apply-options").disabled = busy || !writable || invalid || (!changed && !progression.changes());
    const subCounts = allowed.map(n => n - required.length);
    const cap = Math.max(...subCounts);
    const selected = optional.filter(id => draft[id] != null).length;
    $("sub-options").hidden = !optional.length;
    $("roll-count").textContent = editable && optional.length ? selected + " / " + cap + " selected" : "";
    let hint = item.unavailable;
    if (!hint && !initialized) hint = "Choose a value for each basic option.";
    else if (!hint && optional.length && subCounts.length !== cap + 1) {
      hint = "Allowed sub-option counts: " + subCounts.join(", ") + ".";
    }
    $("option-hint").textContent = hint;
    $("option-hint").hidden = !hint;
  }
  function optionRow([id,rule]) {
    const required = rule.probability === 1;
    const row = el("div","sub-row"), stat = el("div","stat-label"), label = el("label","",name(id)), select = el("select");
    label.htmlFor = select.id = "equipment-option-" + id;
    if (!required) select.add(new Option(format(id,null),""));
    else if (draft[id] == null) {
      const prompt = new Option("Choose a value","");
      prompt.disabled = true; select.add(prompt);
    }
    for (let level=rule.low;level<=rule.high;level++) select.add(new Option(format(id,level),level));
    select.value = draft[id] ?? "";
    const range = el("small","sub-range",format(id,rule.low) + " – " + format(id,rule.high));
    range.id = select.id + "-range";
    select.setAttribute("aria-describedby", range.id);
    const lock = el("button","option-lock");
    lock.type = "button";
    lock.setAttribute("aria-label","Lock " + name(id));
    const diff = el("small","sub-diff");
    function updateRow() {
      const isLocked = locked.has(id);
      const disabled = busy || !!item.unavailable;
      select.disabled = disabled || isLocked || (required && rule.low === rule.high && draft[id] != null);
      lock.disabled = disabled || draft[id] == null;
      lock.setAttribute("aria-pressed",String(isLocked));
      lock.title = draft[id] == null ? "Choose a value to lock this option" : (isLocked ? "Unlock " : "Lock ") + name(id);
      const changes = [];
      if (before[id] !== draft[id]) changes.push(format(id,before[id]) + " → " + format(id,draft[id]));
      if (savedLocks.has(id) !== isLocked) changes.push(isLocked ? "Unlocked → Locked" : "Locked → Unlocked");
      diff.hidden = !changes.length;
      diff.textContent = changes.join(" · ");
    }
    lock.onclick = () => {
      if (locked.has(id)) locked.delete(id); else locked.add(id);
      updateRow(); message(); state();
    };
    select.onchange = () => {
      if (select.value === "") delete draft[id]; else draft[id] = Number(select.value);
      updateRow(); message(); state();
    };
    stat.append(label, range);
    row.append(stat, select, lock, diff);
    updateRow();
    return row;
  }
  function draw() {
    if (!item) return;
    const entries = Object.entries(rules?.options ?? {});
    $("basic-stats").replaceChildren(...entries.filter(([,r]) => r.probability === 1).map(optionRow));
    $("sub-stats").replaceChildren(...entries.filter(([,r]) => r.probability < 1).map(optionRow));
    state();
  }
  function select(itemRow) {
    $("option-editor").hidden = !itemRow;
    if (!itemRow) { item=null; return; }
    if (item?.id === itemRow.id && item?.version === itemRow.version && item?.unavailable === itemRow.unavailable) return;
    item=itemRow; rules=catalog.specs[item.spec];
    before=Object.fromEntries(item.options.map(o=>[o.OptionId,o.Level])); draft={...before};
    savedLocks=new Set(item.options.filter(o=>o.Locked).map(o=>String(o.OptionId)));
    locked=new Set(savedLocks);
    progression.select(item);
    message(); draw();
  }
  async function apply() {
    if (!item || busy || $("apply-options").disabled) return;
    busy=true; ++check; $("workspace").inert=true; state();
    const body={id:item.id,version:item.version,revision:catalog.revision};
    if (optionsChanged()) {
      body.options = draft;
      body.lockedValues = Object.fromEntries(Array.from(locked,id=>[id,draft[id]]));
    }
    const upgrades = progression.changes();
    if (upgrades) body.progression = upgrades;
    try {
      const res=await fetch(api,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const result=await res.json();
      if (res.status===423) access(false);
      if (res.status===409) await reload();
      if (!res.ok) throw new Error(result.error || "Could not update equipment options.");
      try { await reload(); message("Changes saved to equipment #" + body.id + "."); }
      catch { message("Changes saved to equipment #" + body.id + ". Reload to see its options."); }
    } catch (error) { message(error.message,true); }
    finally { busy=false; $("workspace").inert=false; draw(); }
  }
  $("apply-options").onclick=apply;
  return {
    load(data) { catalog=data; ++check; access(data.writable); },
    select,
    lock() { ++check; access(false); },
  };
}

function weaponProgression(onChange, format, name) {
  const breaks = $("break-count"), count = $("engrave-count"), tier = $("engrave-tier");
  let item, rules, engraving;

  function choices(select, values, label, selected) {
    select.replaceChildren(...values.map(value => new Option(label(value), value)));
    select.value = values.includes(selected) ? selected : values[0];
    select.disabled = values.length <= 1;
  }

  function drawTier() {
    const target = Number(count.value);
    const current = target === engraving.count;
    const levels = current ? [engraving.level] : engraving.tiers[target];
    const label = value => value ? name(engraving.optionId) + " · " + format(engraving.optionId, value) : "Not engraved";
    choices(tier, levels, label, Number(tier.value));
  }

  function drawEngraving() {
    $("engraving-controls").hidden = !engraving;
    if (!engraving) {
      $("engrave-hint").hidden = true;
      return;
    }
    const maxBreaks = Number(breaks.value) === rules.maxBreaks;
    const targets = maxBreaks ? Object.keys(engraving.tiers).map(Number) : [];
    choices(count, [engraving.count, ...targets], n => n + " / " + engraving.maxCount, Number(count.value));
    drawTier();
    const hint = !maxBreaks ? "Reach maximum limit breaks to engrave this weapon."
      : !engraving.enoughExperience ? "Level up this weapon to unlock engraving."
      : engraving.locked ? "This engraving option is locked."
      : engraving.level === engraving.highest || engraving.count === engraving.maxCount ? "Engraving complete."
      : "";
    $("engrave-hint").textContent = hint;
    $("engrave-hint").hidden = !hint;
  }

  function select(row) {
    item = row;
    rules = row?.progression;
    $("weapon-progression").hidden = !rules;
    if (!rules) return;
    $("upgrades-heading").textContent = row.kind === "accessory" ? "Accessory upgrades" : "Weapon upgrades";
    const values = Array.from({length: rules.maxBreaks - row.breaks + 1}, (_, i) => row.breaks + i);
    choices(breaks, values, n => n + " / " + rules.maxBreaks, row.breaks);
    engraving = rules.engraving;
    count.replaceChildren();
    tier.replaceChildren();
    drawEngraving();
  }

  function changes() {
    if (!rules) return null;
    const result = {};
    if (Number(breaks.value) !== item.breaks) result.breaks = Number(breaks.value);
    if (engraving && Number(count.value) !== engraving.count) {
      result.engraving = {count: Number(count.value), level: Number(tier.value)};
    }
    return Object.keys(result).length ? result : null;
  }

  breaks.onchange = () => { drawEngraving(); onChange(); };
  count.onchange = () => { drawTier(); onChange(); };
  tier.onchange = onChange;
  return { select, changes };
}
