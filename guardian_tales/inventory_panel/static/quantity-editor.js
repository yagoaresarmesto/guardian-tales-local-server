import { $ } from "/inventory-dom.js";

export const quantityFormat = new Intl.NumberFormat("en-GB");

export function quantityEditor(form, {api, accessId, lock, reload, saved}) {
  form.innerHTML = `
    <section aria-labelledby="quantity-heading">
      <h4 id="quantity-heading"><label for="quantity">Quantity</label></h4>
      <div class="option-group stack-editor">
        <input type="number" id="quantity" required min="1" step="1" inputmode="numeric" aria-describedby="quantity-range">
        <p id="quantity-range" class="editor-note"></p>
        <p id="comparison" class="edit-diff" aria-live="polite"></p>
      </div>
    </section>
    <footer class="inspector-actions">
      <button type="submit" id="apply" class="apply-button" disabled>Apply</button>
      <p id="quantity-message" role="status" hidden></p>
    </footer>`;
  const quantity = $("quantity"), apply = $("apply"), comparison = $("comparison");
  const message = $("quantity-message");
  apply.setAttribute("aria-describedby", accessId);
  let item = null, writable = false, saving = false;

  function update() {
    const changed = item && quantity.validity.valid && quantity.valueAsNumber !== item.amount;
    apply.disabled = !changed || !writable || saving;
    comparison.textContent = changed
      ? quantityFormat.format(item.amount) + " → " + quantityFormat.format(quantity.valueAsNumber) : "";
  }

  function select(next) {
    form.hidden = !next;
    if (item === next) return;
    item = next;
    message.hidden = true;
    if (item) {
      quantity.max = item.maximum;
      quantity.value = item.amount;
      $("quantity-range").textContent = "Range 1 – " + quantityFormat.format(item.maximum);
    }
    update();
  }

  quantity.oninput = () => { message.hidden = true; update(); };
  form.onsubmit = async event => {
    event.preventDefault();
    if (apply.disabled) return;
    const stack = item, amount = quantity.valueAsNumber;
    const workspace = form.closest(".workspace");
    saving = true;
    workspace.inert = true;
    update();
    try {
      const response = await fetch(api, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: stack.id, version: stack.version, amount})});
      const result = await response.json();
      if (response.status === 423) lock();
      if (response.status === 409) await reload();
      if (!response.ok) throw new Error(result.error || "Could not save the quantity.");
      stack.amount = result.amount;
      stack.version = result.version;
      saved(stack);
      message.textContent = "Quantity saved.";
      message.classList.remove("error");
    } catch (error) {
      message.textContent = error.message;
      message.classList.add("error");
      if (!item) $("range").textContent = error.message;
    } finally {
      message.hidden = false;
      saving = false;
      workspace.inert = false;
      update();
    }
  };

  return {
    select,
    setWritable(allowed) { writable = allowed === true; update(); },
    get saving() { return saving; },
  };
}
