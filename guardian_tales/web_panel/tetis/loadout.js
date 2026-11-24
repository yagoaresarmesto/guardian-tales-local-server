let source, spellId, artifactId, changed;
const spellCards = new Map();
const artifactCards = new Map();

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

function image(path, sprite) {
  const img = element("img", "loadout-icon");
  img.alt = "";
  if (sprite) {
    img.onerror = () => { img.hidden = true; };
    img.src = path + encodeURIComponent(sprite) + ".png";
  } else {
    img.hidden = true;
  }
  return img;
}

function button(className, text) {
  const el = element("button", className, text);
  el.type = "button";
  return el;
}

function section(title, note, gridClass) {
  const card = element("section", "surface loadout-section");
  const header = element("header", "panel-heading");
  header.append(element("h2", "", title));
  const grid = element("div", "loadout-grid " + gridClass);
  card.append(header, element("p", "loadout-note", note), grid);
  return {card, grid};
}

function selectSpell(id) {
  spellId = spellId === id ? 0 : id;
  changed();
}

function refreshArtifacts() {
  for (const [id, card] of artifactCards) {
    const owned = card.input.validity.valid && card.input.valueAsNumber > 0;
    const selected = owned && artifactId === id;
    card.equip.disabled = !owned;
    card.equip.setAttribute("aria-pressed", String(selected));
    card.equip.textContent = selected ? "Equipped" : "Equip";
    card.row.classList.toggle("equipped", selected);
  }
}

export function renderLoadout(state, seasonId, onChange) {
  const host = document.getElementById("tetis-loadout");
  source = state.loadout;
  changed = onChange;
  spellCards.clear();
  artifactCards.clear();
  host.replaceChildren();
  host.hidden = !source;
  if (!source) return;
  spellId = source.spellId;
  artifactId = source.artifactId;
  const scope = "Season " + source.seasonId;
  const archiveNote = seasonId === source.seasonId ? "" : " This loadout also applies while playing earlier seasons.";
  const spells = section("Guardian spell", scope + " spells. Select a spell to equip it, or select it again to unequip." + archiveNote, "spells");
  const nodes = state.seasons.find(s => s.id === source.seasonId)?.nodes || [];
  for (const spell of source.spells) {
    const name = state.labels[spell.name] || "Spell " + spell.id;
    const card = button("spell-card");
    const status = element("small");
    const requirements = spell.requiredNodes.map(id => {
      const node = nodes.find(item => item.id === id);
      return state.labels[node?.name] || "specialty " + id;
    }).join(" or ");
    card.append(image("/tetis/specialty/spells/", spell.sprite), element("span", "spell-name", name), status);
    card.onclick = () => selectSpell(spell.id);
    spellCards.set(spell.id, {spell, name, card, status, requirements});
    spells.grid.append(card);
  }
  const artifacts = section("Season artifacts", scope + " artifacts. Level 0 is unowned. Raise an artifact’s level to equip it.", "artifacts");
  for (const artifact of source.artifacts) {
    const name = state.labels[artifact.name] || "Artifact " + artifact.id;
    const row = element("article", "artifact-card");
    const input = element("input");
    input.type = "number";
    input.min = 0;
    input.max = source.maxArtifactLevel;
    input.step = 1;
    input.required = true;
    input.value = artifact.level;
    input.setAttribute("aria-label", name + " level");
    const label = element("label", "artifact-level", "Level");
    label.append(input);
    const equip = button("artifact-equip");
    equip.setAttribute("aria-label", "Equip " + name);
    equip.onclick = () => {
      artifactId = artifactId === artifact.id ? 0 : artifact.id;
      refreshArtifacts();
      changed();
    };
    input.oninput = () => { refreshArtifacts(); changed(); };
    row.append(image("/tetis/artifacts/", artifact.sprite), element("h3", "", name), label, equip);
    artifactCards.set(artifact.id, {artifact, input, equip, row});
    artifacts.grid.append(row);
  }
  refreshArtifacts();
  host.append(spells.card, artifacts.card);
}

export function syncLoadoutSkills(seasonId, points) {
  if (!source) return;
  for (const {spell, name, card, status, requirements} of spellCards.values()) {
    const unlocked = seasonId === source.seasonId
      ? !spell.requiredNodes.length || spell.requiredNodes.some(id => points[id] > 0)
      : spell.unlocked;
    const selected = unlocked && spellId === spell.id;
    card.disabled = !unlocked;
    card.setAttribute("aria-pressed", String(selected));
    card.title = unlocked ? name : "Unlock " + requirements + " in season " + source.seasonId;
    status.textContent = selected ? "Equipped" : unlocked ? "" : "Locked";
    card.setAttribute("aria-label", name + (unlocked ? "" : ". " + card.title));
  }
}

export function loadoutValid() {
  return [...artifactCards.values()].every(({input}) => input.validity.valid);
}

export function loadoutChanges() {
  if (!source) return {};
  const result = {};
  const equippedSpell = spellCards.get(spellId)?.card.disabled === false ? spellId : 0;
  const equippedArtifact = artifactCards.get(artifactId)?.equip.disabled === false ? artifactId : 0;
  if (equippedSpell !== source.spellId) result.spellId = equippedSpell;
  if (equippedArtifact !== source.artifactId) result.artifactId = equippedArtifact;
  const levels = {};
  for (const [id, {artifact, input}] of artifactCards) {
    if (input.valueAsNumber !== artifact.level) levels[id] = input.valueAsNumber;
  }
  if (Object.keys(levels).length) result.artifactLevels = levels;
  return result;
}
