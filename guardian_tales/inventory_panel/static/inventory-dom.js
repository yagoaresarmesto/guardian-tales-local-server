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
