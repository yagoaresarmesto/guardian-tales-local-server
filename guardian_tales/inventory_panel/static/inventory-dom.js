export const $ = id => document.getElementById(id);
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
export function image(url) {
  const img = el("img");
  img.alt = "";
  img.src = url;
  return img;
}

export function sizeItemSprite(img, maxScale = 1) {
  // A 45px sprite fills its allotted space. Keep tiny artwork legible on narrow cards.
  const nativeEdge = Math.max(img.naturalWidth, img.naturalHeight);
  const scale = Math.max(0.55, maxScale * Math.min(1, nativeEdge / 45));
  img.style.setProperty("--sprite-scale", String(scale));
}

// Use the same labels and counts for the desktop rail and compact selector.
export function renderTypeFilters(rail, select, filters) {
  rail.replaceChildren();
  select.replaceChildren();
  for (const {key, name, count, iconUrl} of filters) {
    const button = el("button", "type-button");
    button.type = "button";
    button.dataset.type = key;
    if (iconUrl) {
      const icon = image(iconUrl);
      icon.onerror = () => icon.remove();
      button.append(icon);
    }
    button.append(el("span", "", name), el("small", "", count));
    rail.append(button);
    select.add(new Option(name + " (" + count + ")", key));
  }
}

export function selectTypeFilter(rail, select, key) {
  for (const button of rail.children) {
    button.setAttribute("aria-pressed", String(button.dataset.type === key));
  }
  select.value = key;
}

// The header, artwork, name and footer occupy the same tracks on every card.
export function inventoryTile({ id, name, art, selected, level, stars, quantity,
  locked, equipped, training, socketed }) {
  const button = el("button", "tile");
  button.type = "button";
  button.dataset.id = id;
  button.setAttribute("aria-pressed", String(selected));
  const description = [name];
  const header = el("span", "tile-header");
  if (level != null) {
    header.append(el("span", "tile-level", "Lv. " + level));
    description.push("Level " + level);
  }
  const badges = el("span", "tile-badges");
  if (locked) {
    const lock = image("/type-icon/lock.png");
    lock.className = "tile-lock";
    lock.title = "Locked";
    lock.onerror = () => lock.replaceWith(el("span", "tile-badge", "L"));
    badges.append(lock);
    description.push("Locked");
  }
  for (const [visible, mark, label] of [
    [equipped, "E", "Equipped"], [training, "T", "Training Room"], [socketed, "◆", "Socketed jewel"],
  ]) {
    if (visible) {
      const badge = el("span", "tile-badge", mark);
      badge.title = label;
      badges.append(badge);
      description.push(label);
    }
  }
  header.append(badges);
  const caption = el("span", "tile-caption");
  caption.append(el("span", "tile-name", name));
  const rating = Number.isInteger(stars) && stars >= 1 && stars <= 6;
  const footer = quantity != null
    ? el("span", "stack-size", quantity)
    : el("span", "tile-stars", rating ? "★".repeat(stars) : "");
  if (quantity != null) description.push("Quantity " + quantity);
  if (rating) description.push(stars + " stars");
  description.push("Copy #" + id);
  button.title = description.join(" · ");
  button.setAttribute("aria-label", button.title);
  button.append(header, art, caption, footer);
  return button;
}

// Page through four complete rows at the current grid width.
export function watchGridPageSize(grid, resizePage) {
  let lastColumns = 0;
  function measure() {
    const tracks = getComputedStyle(grid).gridTemplateColumns;
    if (!grid.clientWidth || tracks === "none") return;
    const columns = tracks.split(/\s+/).length;
    if (columns !== lastColumns) {
      lastColumns = columns;
      resizePage(columns * 4);
    }
  }
  measure();
  new ResizeObserver(measure).observe(grid);
}
