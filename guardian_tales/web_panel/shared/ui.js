export const $ = id => document.getElementById(id);

export function feedback(message, error = false) {
  const node = $("feedback");
  node.textContent = message;
  node.dataset.error = String(error);
  node.hidden = !message;
}

export function setArtwork(image, url) {
  if (image.getAttribute("src") === url) return;
  image.hidden = true;
  if (!url) {
    image.removeAttribute("src");
    return;
  }
  image.onload = () => { image.hidden = false; };
  image.onerror = () => { image.hidden = true; };
  image.src = url;
}

export function elementIcon(element, available) {
  const image = document.createElement("img");
  image.className = "element-icon";
  image.alt = "";
  image.hidden = true;
  if (available && element) setArtwork(image, "/elements/" + encodeURIComponent(element) + ".png");
  return image;
}
