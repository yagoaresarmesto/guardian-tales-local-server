export const $ = id => document.getElementById(id);

export function feedback(message, error = false) {
  const node = $("feedback");
  node.textContent = message;
  node.dataset.error = String(error);
  node.hidden = !message;
}
