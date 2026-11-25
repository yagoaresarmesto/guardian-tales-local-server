// The client stacks room origins 55 sprite pixels apart; the frames overlap at the seams.
export const floorPitch = 55;
const clamp = (n, low, high) => Math.min(high, Math.max(low, n));

export async function mapData(url) {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Lift catalog unavailable.");
      return await response.json();
    } catch (error) {
      if (attempt || !(error instanceof TypeError)) throw error;
    }
  }
}

function loadImage(url, ready, failed) {
  const image = new Image();
  image.onload = ready;
  image.onerror = () => {
    image.onerror = failed ?? null;
    image.src = url;
  };
  image.src = url;
  return image;
}

export function createScene(canvas, redraw) {
  const ctx = canvas.getContext("2d");
  let sheet, frames, imageReady = false;
  const unavailable = () => { document.getElementById("lift-instructions").textContent = "Tower artwork unavailable"; };
  mapData("/orbital-lift/tower.json").then(data => {
    frames = data;
    sheet = loadImage("/orbital-lift/tower.webp", () => {
      imageReady = true;
      canvas.dataset.art = "ready";
      redraw();
    }, unavailable);
  }).catch(unavailable);
  const icons = new Map();
  const scenery = new Map();

  function sprite(name, cx, cy, width, height) {
    if (!frames) return;
    if (!frames[name]) {
      if (!scenery.has(name)) scenery.set(name, loadImage("/orbital-lift/scenery/" + name + ".webp", redraw));
      const image = scenery.get(name);
      if (image.naturalWidth) {
        width ??= image.naturalWidth;
        height ??= image.naturalHeight;
        ctx.drawImage(image, cx - width / 2, cy - height / 2, width, height);
      }
      return;
    }
    if (!imageReady) return;
    const [x, y, w, h] = frames[name];
    width ??= w;
    height ??= h;
    ctx.drawImage(sheet, x, y, w, h, Math.round(cx - width / 2), Math.round(cy - height / 2), width, height);
  }

  function reward(item, amount, x, y, cleared) {
    if (!icons.has(item)) {
      icons.set(item, loadImage("/icon/" + item + ".png", redraw));
    }
    const image = icons.get(item);
    const quantity = amount.toLocaleString("en");
    const halfWidth = quantity.length > 3 ? 17 : 13;
    ctx.fillStyle = "#263846";
    ctx.fillRect(x - halfWidth, y - 15, halfWidth * 2, 30);
    ctx.fillStyle = cleared ? "#c68e3a" : "#1e3048";
    ctx.fillRect(x - halfWidth + 1, y - 14, halfWidth * 2 - 2, 28);
    if (image.naturalWidth) {
      const scale = 18 / Math.max(image.naturalWidth, image.naturalHeight);
      const w = image.naturalWidth * scale, h = image.naturalHeight * scale;
      ctx.globalAlpha = cleared ? .60 : 1;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(image, x - w / 2, y - 4 - h / 2, w, h);
      ctx.imageSmoothingEnabled = false;
      ctx.globalAlpha = 1;
    }
    ctx.fillStyle = cleared ? "#6a431d" : "#0e1a2b";
    ctx.fillRect(x - halfWidth + 1, y + 5, halfWidth * 2 - 2, 9);
    ctx.fillStyle = "#fff8e8";
    ctx.textAlign = "center";
    ctx.font = "bold 8px 'Segoe UI', sans-serif";
    ctx.fillText(quantity, x, y + 12.5, halfWidth * 2 - 4);
    if (cleared) {
      ctx.strokeStyle = "#fff8d5";
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(x - 5, y - 2); ctx.lineTo(x - 1, y + 2); ctx.lineTo(x + 5, y - 5); ctx.stroke();
    }
  }

  function backdrop(f, colony, w, h) {
    const cx = w / 2, cy = h / 2;
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, colony || f > 600 ? "#080c1c" : "#168ac5");
    gradient.addColorStop(1, colony || f > 600 ? "#203651" : "#a4e1ed");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
    if (colony) {
      const depth = clamp((f - 1001) / 499, 0, 1);
      const height = Math.max(h * 1.4, w * 2.6);
      sprite("mars-bg", cx, height / 2 - (height - h) * depth, w * 1.6, height);
      sprite("mars-main_bg", cx, h * .28 - depth * h, w * .56, w * 1.2);
      if (depth > .88) sprite("mars-bottom", cx, h * (1.75 - (depth - .88) * 7), w, w * .26);
      return;
    }
    // Pan from clouds through the atmosphere to the orbital horizon.
    const skyHeight = Math.max(h, w * 600 / 510);
    sprite("a", cx, h - skyHeight / 2 + Math.min(f - 1, 50) / 50 * (skyHeight - h), w, skyHeight);
    if (f > 6) {
      ctx.globalAlpha = clamp((f - 6) / 44, 0, 1);
      sprite("a1", cx, h - skyHeight / 2 + Math.min(f, 300) / 300 * (skyHeight - h), w, skyHeight);
      ctx.globalAlpha = 1;
    }
    const space = clamp((f - 160) / 520, 0, 1);
    if (space) {
      ctx.globalAlpha = space;
      sprite("c", cx, cy + space * h * .32, w * 1.08, Math.max(h * 1.75, w * .6));
      sprite("stars", cx, cy - 24, w, h);
      if (space > .7) sprite("star2", w * .14, h * .18, 48, 48);
      ctx.globalAlpha = 1;
    }
  }

  function room(f, y, selected, cleared, entry, cx) {
    const record = entry?.type === "RecordRoom";
    const key = record ? "x" : "a";
    const label = f < 1000 ? "0" + f : String(f);
    if (imageReady) {
      sprite("room_" + key + "_back", cx - (record ? .5 : 3), y);
      sprite("room_" + key, cx, y);
      if (cleared != null && f > cleared + 1) sprite("room_" + key + "_disable", cx, y);
      if (!record) {
        [...label].forEach((digit, i) => sprite("number-" + digit, cx - 40 - 12 * (label.length - i - 1), y + 6));
      }
      if (f === selected) sprite("highlight_" + key, cx, y);
    } else {
      ctx.fillStyle = f === selected ? "#315c6f" : "#203c4d";
      ctx.fillRect(cx - 140, y - 25, 280, 50);
      ctx.textAlign = "left"; ctx.fillStyle = "white"; ctx.font = "bold 20px monospace";
      ctx.fillText(String(f), cx - 91, y + 7);
    }
    const items = entry?.rewards ?? [];
    items.forEach(([id, amount], i) => reward(id, amount, cx + 57 + (i - (items.length - 1) / 2) * 26, y - 2, cleared != null && f <= cleared));
  }

  return function draw(width, height, scale, position, colony, selected, cleared, catalog) {
    const w = width / scale, h = height / scale;
    if (!ctx || w < 1 || h < 1) return;
    const pixelWidth = Math.round(width * window.devicePixelRatio);
    const pixelHeight = Math.round(height * window.devicePixelRatio);
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    // Keep native pixel edges while rasterizing labels and item art directly at display resolution.
    ctx.setTransform(pixelWidth / w, 0, 0, pixelHeight / h, 0, 0);
    ctx.imageSmoothingEnabled = false;
    const cx = w / 2;
    const yAt = f => h / 2 + (f - position) * (colony ? 1 : -1) * floorPitch;
    backdrop(position, colony, w, h);
    const baseY = yAt(1), topY = yAt(colony ? 1001 : 1000);
    if (colony && topY > -120) {
      ctx.fillStyle = "#090c0c";
      ctx.fillRect(0, 0, w, Math.max(0, topY + 45));
      ctx.save();
      ctx.translate(cx, topY + 50);
      ctx.scale(1, -1);
      sprite("satellite_back", 0, 0, w * 1.2, w * .26);
      ctx.restore();
    }
    for (const [offset, name] of [[137,"cable"], [117,"cable_b"]]) {
      const start = (yAt(selected) % 36 + 36) % 36 - 36;
      for (let y = start; y < h + 18 && (colony || y < baseY + 80); y += 36) {
        sprite(name, cx - offset, y);
        sprite(name, cx + offset, y);
      }
    }
    if (!colony && baseY < h) {
      sprite("base_back", cx - 55, baseY + 57);
      sprite("base_castle", cx, baseY + 166);
    }
    if (topY > -115 && topY < h + 170) {
      sprite("satellite", cx, topY - 86);
      sprite("ic_tower1000_clear_00", cx, topY - 51, 36, 36);
    }
    const count = Math.ceil(h / (2 * floorPitch)) + 1;
    const first = Math.max(colony ? 1001 : 1, Math.floor(position) - count);
    const last = Math.min(colony ? 1500 : 1000, Math.ceil(position) + count);
    // Draw bottom-up so the lip of each upper room sits over the lower one.
    for (let i = 0; i <= last - first; i++) {
      const f = colony ? last - i : first + i;
      room(f, Math.round(yAt(f)), selected, cleared, catalog?.[f], cx);
    }
  };
}
