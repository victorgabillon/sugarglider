import { parseItineraryDraft, itineraryDraftToCanonical, buildItineraryPrompt, ITINERARY_MAX_BYTES } from "./itinerary_draft.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";

export function initializeItineraryDialog({ root, launcher, maximumStops, capability, promptSettings, canImport, onImport,
  copyText = text => navigator.clipboard.writeText(text) }) {
  const element = id => root.querySelector(`#itinerary-${id}`);
  let reviewed = null, fileOperation = 0;
  const openSubscribers = new Set();
  const notifyOpen = () => openSubscribers.forEach(callback => callback(root.open));
  const error = message => { element("error").textContent = message; };
  function stage(review) {
    element("input-stage").hidden = review; element("review-stage").hidden = !review;
    element("review").hidden = review; element("back").hidden = !review; element("confirm").hidden = !review;
    root.querySelector(".itinerary-body").scrollTop = 0;
  }
  function close() { reviewed = null; fileOperation += 1; root.close(); }
  function paragraph(parent, text, tag = "p") {
    const node = document.createElement(tag); node.textContent = text; parent.append(node); return node;
  }
  function open(rawText = "", sourceKind = null) {
    if (!sourceKind && !canImport()) return false;
    reviewed = null; fileOperation += 1; stage(false); error("");
    element("text").value = rawText; element("file").value = "";
    element("preview").replaceChildren();
    element("prompt-area").hidden = true; element("prompt").value = ""; element("copy-status").textContent = "";
    root.querySelector(".itinerary-prompt-helper").open = false;
    element("source").hidden = !sourceKind;
    element("source").textContent = sourceKind === "opened_json_file" ? "Opened JSON document" : sourceKind ? "Shared from another app" : "";
    if (!root.open) root.showModal(); element("text").focus();
    if (sourceKind) { element("text").setSelectionRange(0, 0); element("text").scrollTop = 0; }
    notifyOpen(); return true;
  }
  launcher.addEventListener("click", () => open());
  root.addEventListener("close", () => { if (root.open) return; reviewed = null; fileOperation += 1; notifyOpen(); launcher.focus({ preventScroll: true }); });
  root.addEventListener("cancel", () => { fileOperation += 1; });
  element("cancel").addEventListener("click", close);
  element("choose-file").addEventListener("click", () => element("file").click());
  element("file").addEventListener("change", async () => {
    const file = element("file").files[0]; if (!file) return;
    const operation = ++fileOperation;
    try {
      if (file.size > ITINERARY_MAX_BYTES) throw new Error("Itinerary JSON must be at most 64 KiB.");
      const raw = await file.text();
      if (!root.open || operation !== fileOperation) return;
      element("text").value = raw; error(""); element("text").focus();
    } catch (failure) { if (root.open && operation === fileOperation) error(failure.message); }
  });
  element("review").addEventListener("click", () => {
    try {
      const draft = parseItineraryDraft(element("text").value, { maximumStops: maximumStops() });
      const request = itineraryDraftToCanonical(draft);
      const preview = element("preview"); preview.replaceChildren();
      paragraph(preview, draft.name, "h3");
      paragraph(preview, `${PUBLIC_PROFILE_METADATA[draft.activity].display_name} · ${draft.topology === "loop" ? "Loop" : "Point to point"} · ${draft.target_distance_km} km (±${draft.tolerance_km} km)`);
      paragraph(preview, `Order: ${draft.order === "optimize" ? "Optimize stops" : "As given"}`);
      paragraph(preview, "Start", "h4"); paragraph(preview, `${draft.start.name} (${draft.start.lat}, ${draft.start.lon})`);
      paragraph(preview, "Stops", "h4");
      const list = document.createElement("ol"); preview.append(list);
      for (const point of draft.stops) {
        const item = document.createElement("li"); list.append(item);
        paragraph(item, `${point.name} (${point.lat}, ${point.lon})`, "strong");
        if (point.reason) paragraph(item, `Suggested because: ${point.reason}`);
      }
      if (!draft.stops.length) paragraph(preview, "No interior stops.");
      if (draft.end) { paragraph(preview, "End", "h4"); paragraph(preview, `${draft.end.name} (${draft.end.lat}, ${draft.end.lon})`); }
      element("capability").textContent = capability(request);
      reviewed = { draft, request }; error(""); stage(true); element("confirm").focus({ preventScroll: true });
    } catch (failure) { reviewed = null; error(failure.message); }
  });
  element("back").addEventListener("click", () => { reviewed = null; stage(false); error(""); element("text").focus(); });
  element("confirm").addEventListener("click", () => {
    if (!reviewed) return;
    if (!canImport()) { error("This plan cannot be replaced right now. Cancel and try again when it is editable."); return; }
    try { onImport(reviewed.request, reviewed.draft); close(); }
    catch (failure) { error(failure.message); }
  });
  element("create-prompt").addEventListener("click", () => {
    element("prompt").value = buildItineraryPrompt(promptSettings());
    element("prompt-area").hidden = false; element("copy-status").textContent = ""; element("prompt").focus();
  });
  element("copy-prompt").addEventListener("click", async () => {
    const operation = fileOperation;
    try {
      await copyText(element("prompt").value);
      if (root.open && operation === fileOperation) element("copy-status").textContent = "Prompt copied. Paste it into an assistant of your choice.";
    } catch { if (root.open && operation === fileOperation) element("copy-status").textContent = "Copy unavailable. Select the prompt text and copy it manually."; }
  });
  return Object.freeze({
    openWithText(rawText, { sourceKind = "shared_text" } = {}) {
      if (typeof rawText !== "string" || rawText.length > ITINERARY_MAX_BYTES
        || new TextEncoder().encode(rawText).byteLength > ITINERARY_MAX_BYTES
        || !["shared_text", "shared_json_file", "opened_json_file"].includes(sourceKind)) return false;
      return open(rawText, sourceKind);
    },
    isOpen: () => root.open,
    cancel: () => { if (root.open) close(); },
    subscribeOpenChange(callback) { openSubscribers.add(callback); return () => openSubscribers.delete(callback); },
  });

}
