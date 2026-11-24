import { $ } from "/panel.js";

const specialty = "/tetis/specialty/";
const art = name => specialty + name + ".png";

function icon(src, className) {
  const img = document.createElement("img");
  img.alt = "";
  img.className = className;
  img.src = src;
  img.onerror = () => { img.hidden = true; };
  return img;
}

function sum(nodes, points) {
  return nodes.reduce((total, node) => total + points[node.id], 0);
}

export class SpecialtyTree {
  constructor(onChange) {
    this.onChange = onChange;
    $("reset-tree").onclick = () => {
      for (const node of this.nodes) this.points[node.id] = 0;
      this.onChange();
    };
    $("revert-tree").onclick = () => {
      for (const node of this.nodes) this.points[node.id] = node.points;
      this.onChange();
    };
    $("close-node").onclick = () => $("node-dialog").close();
    $("add-point").onclick = () => this.adjust(1);
    $("remove-point").onclick = () => this.adjust(-1);
  }

  openSeason(state, season) {
    this.labels = state.labels;
    this.nodes = season.nodes;
    this.hasArt = state.hasArt;
    this.byId = new Map(this.nodes.map(n => [n.id, n]));
    this.points = Object.fromEntries(this.nodes.map(n => [n.id, n.points]));
    this.categories = [...new Map(this.nodes.map(n => [n.category, n])).values()];
    this.selected = null;
    if ($("node-dialog").open) $("node-dialog").close();
    $("skills").hidden = this.nodes.length === 0;
    $("no-skills").hidden = this.nodes.length > 0;
    $("skills").classList.toggle("with-art", this.hasArt);
    if (!this.nodes.length) return;
    this.branchButtons = new Map();
    const choices = this.categories.map((node, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "branch-button";
      button.dataset.index = index;
      button.title = this.branchName(node);
      button.setAttribute("aria-label", button.title);
      const fallback = document.createElement("span");
      fallback.className = "branch-initial";
      fallback.textContent = button.title[0];
      button.append(fallback);
      if (this.hasArt && node.categorySprite) button.append(icon(art("nodes/" + node.categorySprite), "branch-image"));
      const amount = document.createElement("span");
      amount.className = "branch-rank";
      button.append(amount);
      button.onclick = () => this.openBranch(node.category);
      this.branchButtons.set(node.category, {button, amount});
      return button;
    });
    $("branch-buttons").replaceChildren(...choices);
    this.openBranch(this.categories[0].category);
  }

  branchName(node) {
    return this.labels[node.categoryName] || node.categoryName || "Branch " + node.category;
  }

  nodeName(node) {
    return this.labels[node.name] || "Specialty " + node.id;
  }

  branchRequirement(node, points) {
    for (const rule of node.requiredCategories || []) {
      const branch = this.nodes.filter(n => n.category === rule.id);
      if (sum(branch, points) < rule.points) {
        const name = branch.length ? this.branchName(branch[0]).replace(/ Season Specialty Category$/i, "") : "branch " + rule.id;
        return "Requires " + rule.points + " points in " + name + ".";
      }
    }
    return "";
  }

  requirement(node, points) {
    const branch = this.branchRequirement(node, points);
    if (branch) return branch;
    const earlier = this.nodes.filter(n => n.category === node.category && n.step < node.step);
    if (sum(earlier, points) < node.requiredPoints) {
      return "Requires " + node.requiredPoints + " points in earlier steps of this branch.";
    }
    for (const id of node.requiresNodes || []) {
      const parent = this.byId.get(id);
      if (parent && points[id] < parent.maxPoints) return "Requires max rank in " + this.nodeName(parent) + ".";
    }
    return "";
  }

  openBranch(category) {
    this.category = category;
    const nodes = this.nodes.filter(n => n.category === category);
    $("branch-name").textContent = this.branchName(nodes[0]);
    const steps = Math.max(...nodes.map(n => n.step));
    const lanes = Math.max(7, ...nodes.map(n => n.position?.[1] || 1));
    const positions = new Map(nodes.map(n => [n.id, {
      x: ((n.position?.[0] || n.step) - .5) * 100 / steps,
      y: (n.position?.[1] || 4) * 100 / (lanes + 1),
    }]));
    const svgNS = "http://www.w3.org/2000/svg";
    const lines = document.createElementNS(svgNS, "svg");
    lines.setAttribute("viewBox", "0 0 100 100");
    lines.setAttribute("preserveAspectRatio", "none");
    this.nodeButtons = new Map();
    const buttons = nodes.map(n => {
      const pos = positions.get(n.id);
      for (const id of n.requiresNodes || []) {
        const parent = positions.get(id);
        if (!parent) continue;
        const line = document.createElementNS(svgNS, "line");
        line.setAttribute("x1", parent.x); line.setAttribute("y1", parent.y);
        line.setAttribute("x2", pos.x); line.setAttribute("y2", pos.y);
        line.dataset.parent = id;
        lines.append(line);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "skill-node";
      button.dataset.skill = n.id;
      button.style.left = pos.x + "%";
      button.style.top = pos.y + "%";
      button.title = this.nodeName(n);
      const face = document.createElement("span");
      face.className = "node-face";
      face.textContent = this.nodeName(n).split(/\s+/).slice(0, 2).map(w => w[0]).join("");
      if (this.hasArt && n.sprite) {
        const picture = icon(art("nodes/" + n.sprite), "node-image");
        picture.onload = () => face.classList.add("has-icon");
        face.append(picture);
      }
      const rank = document.createElement("span");
      rank.className = "rank-badge";
      button.append(face, rank);
      if (n.tier) {
        const tier = document.createElement("span");
        tier.className = "tier-badge";
        tier.textContent = ["", "I", "II", "III"][n.tier] || n.tier;
        if (this.hasArt && n.tier <= 3) {
          const image = icon(art("ic_rogue_chess_perks_num_0" + (n.tier - 1)), "tier-image");
          tier.append(image);
        }
        button.append(tier);
      }
      button.onclick = () => {
        this.selected = n;
        this.updateDialog();
        $("node-dialog").showModal();
      };
      this.nodeButtons.set(n.id, {button, rank});
      return button;
    });
    $("connections").replaceChildren(lines);
    $("nodes").replaceChildren(...buttons);
    const labels = Array.from({length: steps}, (_, i) => {
      const span = document.createElement("span");
      span.textContent = "Step " + (i + 1);
      return span;
    });
    $("step-labels").replaceChildren(...labels);
    this.draw();
  }

  get dirty() {
    return this.nodes.some(n => this.points[n.id] !== n.points);
  }

  get spent() {
    return sum(this.nodes, this.points);
  }

  changes() {
    return this.dirty ? {abilities: Object.fromEntries(Object.entries(this.points).filter(([, value]) => value))} : {};
  }

  refresh(earned, canSave) {
    this.earned = Number.isFinite(earned) ? earned : 0;
    $("save-tree").disabled = !canSave;
    this.draw();
  }

  draw() {
    $("budget").textContent = this.nodes.length ? this.spent + " / " + (this.earned || 0) + " points assigned" : "";
    $("budget").dataset.error = String(this.spent > this.earned);
    if (!this.nodes.length) return;
    $("available-points").textContent = (this.earned || 0) - this.spent;
    $("reset-tree").disabled = this.spent === 0;
    $("revert-tree").disabled = !this.dirty;
    for (const node of this.categories) {
      const {button, amount} = this.branchButtons.get(node.category);
      button.setAttribute("aria-pressed", String(node.category === this.category));
      const locked = this.branchRequirement(node, this.points);
      const count = sum(this.nodes.filter(n => n.category === node.category), this.points);
      button.dataset.locked = String(Boolean(locked));
      amount.textContent = locked ? "🔒" : count;
      button.title = this.branchName(node) + (locked ? " · " + locked : " · " + count + " points");
      button.setAttribute("aria-label", button.title);
    }
    for (const [id, {button, rank}] of this.nodeButtons || []) {
      const node = this.byId.get(id), value = this.points[id];
      button.dataset.locked = String(Boolean(this.requirement(node, this.points)));
      button.dataset.allocated = String(value > 0);
      button.dataset.max = String(value >= node.maxPoints);
      rank.textContent = value + "/" + node.maxPoints;
      button.setAttribute("aria-label", this.nodeName(node) + ", " + value + " of " + node.maxPoints + " points");
    }
    for (const line of $("connections").querySelectorAll("line")) {
      const parent = this.byId.get(Number(line.dataset.parent));
      line.classList.toggle("complete", this.points[parent.id] >= parent.maxPoints);
    }
    if (this.selected && $("node-dialog").open) this.updateDialog();
  }

  updateDialog() {
    const node = this.selected, value = this.points[node.id];
    $("node-title").textContent = this.nodeName(node);
    $("node-location").textContent = this.branchName(node).replace(/ Season Specialty Category$/i, "") + " · Step " + node.step;
    const portrait = $("node-portrait");
    portrait.hidden = !this.hasArt || !node.sprite;
    if (!portrait.hidden) {
      portrait.onerror = () => { portrait.hidden = true; };
      portrait.src = art("nodes/" + node.sprite);
    }
    // Native spell and ability descriptions sometimes require calculated battle effects.
    // Only show a complete localized description when the client text is self-contained.
    const description = (this.labels[node.description] || "").replace(/\[(?:\/?c|-|[a-f\d]{6,8})\]/gi, "");
    $("node-description").hidden = !description || /\{\d+\}/.test(description);
    $("node-description").textContent = description;
    $("node-rank").textContent = value + " / " + node.maxPoints;
    const unmet = this.requirement(node, this.points);
    const full = value >= node.maxPoints;
    $("add-point").disabled = Boolean(unmet || full || this.spent >= this.earned);
    const lowered = {...this.points, [node.id]: value - 1};
    const dependent = value > 0 && this.nodes.find(n => lowered[n.id] > 0 && this.requirement(n, lowered));
    $("remove-point").disabled = value === 0 || Boolean(dependent);
    const notes = [];
    if (unmet) notes.push(unmet);
    else if (full) notes.push("Maximum rank.");
    else if (this.spent >= this.earned) notes.push("No specialty points available.");
    if (dependent) notes.push("Remove points from " + this.nodeName(dependent) + " before lowering this rank.");
    $("node-requirements").textContent = notes.join(" ");
  }

  adjust(delta) {
    if ($(delta > 0 ? "add-point" : "remove-point").disabled) return;
    this.points[this.selected.id] += delta;
    this.onChange();
  }
}
