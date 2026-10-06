// A pointer gesture previews only. A completed drop delegates one canonical edit.
const controllers = new WeakMap();
export function configurePointStripDrag({ root, strip, onReorder, onRemove, canReorder, disabled }) {
  let controller = controllers.get(root);
  if (controller) {
    controller.cancel();
    Object.assign(controller.options, { onReorder, onRemove, canReorder, disabled });
    return;
  }
  const options = { onReorder, onRemove, canReorder, disabled };
  const trash = root.querySelector("#route-drag-trash"), status = root.querySelector("#route-drag-status");
  let gesture = null, ghost = null, frame = null, suppressUntil = 0;
  function clean(cancelled = false) {
    if (!gesture) return;
    const current = gesture; gesture = null;
    if (current.started) {
      suppressUntil = performance.now() + 500;
      status.textContent = cancelled ? "Drag cancelled. Route unchanged." : "";
    }
    cancelAnimationFrame(frame); frame = null;
    ghost?.remove(); ghost = null;
    trash.hidden = true; trash.classList.remove("armed"); root.classList.remove("point-dragging");
    strip.querySelectorAll(".drag-source, .drop-before, .drop-after").forEach(el => el.classList.remove("drag-source", "drop-before", "drop-after"));
    if (current.chip.hasPointerCapture(current.id)) current.chip.releasePointerCapture(current.id);
  }
  function update() {
    if (!gesture?.started) return;
    const g = gesture;
    ghost.style.left = `${g.x - 22}px`; ghost.style.top = `${g.y - 70}px`;
    const t = trash.getBoundingClientRect();
    g.remove = g.x >= t.left && g.x <= t.right && g.y >= t.top && g.y <= t.bottom;
    trash.classList.toggle("armed", g.remove);
    strip.querySelectorAll(".drop-before, .drop-after").forEach(el => el.classList.remove("drop-before", "drop-after"));
    g.to = null;
    const r = strip.getBoundingClientRect();
    const inside = g.x >= r.left && g.x <= r.right && g.y >= r.top - 12 && g.y <= r.bottom + 12;
    if (inside && options.canReorder && !g.remove) {
      const chips = [...strip.querySelectorAll("[data-stop-index]")].filter(el => el !== g.chip);
      const before = chips.find(el => g.x < el.getBoundingClientRect().left + el.getBoundingClientRect().width / 2);
      const after = chips.at(-1);
      const target = before ?? after;
      if (target) {
        const index = Number(target.dataset.stopIndex);
        g.to = before ? index - Number(index > g.from) : index + Number(index < g.from);
        target.classList.add(before ? "drop-before" : "drop-after");
      }
    }
    const message = g.remove ? "Release to remove stop. Undo is available."
      : !options.canReorder ? "Choose As tapped to reorder. Drag to Remove to delete."
      : g.to !== null && g.to !== g.from ? `Release to move to Stop ${g.to + 1}.` : "Drag along the ribbon to reorder, or to Remove.";
    if (status.textContent !== message) status.textContent = message;
  }
  function autoScroll() {
    if (!gesture?.started) return;
    const r = strip.getBoundingClientRect();
    if (!gesture.remove && gesture.y >= r.top - 12 && gesture.y <= r.bottom + 12) {
      const direction = gesture.x < r.left + 24 ? -1 : gesture.x > r.right - 24 ? 1 : 0;
      if (direction) { strip.scrollLeft += direction * 5; update(); }
    }
    frame = requestAnimationFrame(autoScroll);
  }
  strip.addEventListener("pointerdown", event => {
    suppressUntil = 0; // Suppress only the completed gesture's compatibility click.
    // Selected chip has an explicit grip; all other chips retain native scrolling.
    const chip = event.target.closest('[data-stop-index][aria-pressed="true"]');
    if (options.disabled || !chip || gesture || !event.isPrimary || event.button !== 0) return;
    gesture = { id: event.pointerId, chip, from: Number(chip.dataset.stopIndex), startX: event.clientX,
      startY: event.clientY, x: event.clientX, y: event.clientY, started: false, to: null, remove: false };
    chip.setPointerCapture(event.pointerId);
  });
  strip.addEventListener("pointermove", event => {
    if (!gesture || gesture.id !== event.pointerId) return;
    const g = gesture; g.x = event.clientX; g.y = event.clientY;
    if (!g.started && Math.hypot(g.x - g.startX, g.y - g.startY) < 12) return;
    event.preventDefault();
    if (!g.started) {
      g.started = true; g.chip.classList.add("drag-source"); root.classList.add("point-dragging");
      root.querySelectorAll("[popover]:popover-open").forEach(el => el.hidePopover());
      ghost = g.chip.cloneNode(true); ghost.removeAttribute("data-route-chip"); ghost.removeAttribute("data-stop-index");
      ghost.className = "route-chip-ghost"; ghost.setAttribute("aria-hidden", "true"); ghost.tabIndex = -1;
      document.body.append(ghost); trash.hidden = false; frame = requestAnimationFrame(autoScroll);
    }
    update();
  });
  strip.addEventListener("pointerup", event => {
    if (!gesture || gesture.id !== event.pointerId) return;
    const g = gesture;
    if (g.started) { g.x = event.clientX; g.y = event.clientY; update(); }
    const complete = g.started && !options.disabled && root.getClientRects().length;
    clean();
    if (!complete) return;
    g.chip.focus({ preventScroll: true });
    if (g.remove) { options.onRemove(g.from); status.textContent = "Stop removed. Undo is available."; }
    else if (g.to !== null && g.to !== g.from && options.canReorder) {
      options.onReorder(g.from, g.to); status.textContent = "Stop reordered. Undo is available.";
    } else status.textContent = "Route unchanged.";
  });
  strip.addEventListener("pointercancel", () => clean(true));
  strip.addEventListener("lostpointercapture", () => clean(true));
  strip.addEventListener("click", event => {
    if (performance.now() < suppressUntil) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  root.addEventListener("keydown", event => { if (event.key === "Escape" && gesture) { event.preventDefault(); clean(true); } });
  window.addEventListener("blur", () => clean(true));
  window.addEventListener("resize", () => {
    clean(true);
    root.querySelectorAll("[popover]:popover-open").forEach(el => el.hidePopover());
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) clean(true); });
  controller = { options, cancel: () => clean(true) }; controllers.set(root, controller);
}
