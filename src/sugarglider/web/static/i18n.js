import { readLanguagePreference, writeLanguagePreference } from "./pwa_store.js";
import { FRENCH } from "./translations.js";

let language = "fr", choiceVersion = 0, writes = Promise.resolve();
const listeners = new Set();
const textBindings = new WeakMap();
const initializedDocuments = new WeakSet();
export const getLanguage = () => language;
export const speechDefaultLanguage = () => language === "fr" ? "fr-FR" : "en-GB";

// English source messages are stable keys. Only complete declared messages are
// translated; user text, place names, licence notices and canonical data never
// pass through a substring replacement or a DOM text scanner.
export function t(key, parameters = {}) {
  const message = language === "fr" ? FRENCH[key] ?? key : key;
  return String(message).replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(parameters, name) ? String(parameters[name]) : match);
}
export function tr(parts, ...values) {
  return t(parts.reduce((text, part, index) => text + (index ? `{${index - 1}}` : "") + part, ""), values);
}
export function onLanguageChange(listener) { listeners.add(listener); return () => listeners.delete(listener); }

// Explicit bindings retain the message and parameters, never the rendered
// wording. Detached nodes can be collected without keeping old route views.
export function setLocalizedText(node, render) {
  node.setAttribute("data-localized-text", "");
  textBindings.set(node, render);
  node.textContent = render();
}

export function translateDocument(root = globalThis.document) {
  if (!root?.querySelectorAll) return;
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const attribute of ["aria-label", "title", "placeholder", "alt"]) {
    for (const node of root.querySelectorAll(`[data-i18n-${attribute}]`)) node.setAttribute(attribute, t(node.getAttribute(`data-i18n-${attribute}`)));
  }
  for (const node of root.querySelectorAll("[data-localized-text]")) {
    const render = textBindings.get(node);
    if (render) node.textContent = render();
  }
}
function apply(value, root) {
  language = value === "en" ? "en" : "fr";
  if (root?.documentElement) root.documentElement.lang = language;
  translateDocument(root);
  const selector = root?.querySelector?.("#application-language");
  if (selector) selector.value = language;
  for (const listener of listeners) listener(language);
}
export async function setLanguage(value, { persist = true, document = globalThis.document } = {}) {
  choiceVersion++;
  apply(value, document);
  if (!persist) return true;
  const selected = language;
  const result = writes.then(() => writeLanguagePreference(selected));
  writes = result.catch(() => false);
  const stored = await result;
  const status = document?.querySelector?.("#language-storage-status");
  if (status) { status.hidden = stored; status.textContent = stored ? "" : t("Language changed for this session. Storage is unavailable."); }
  return stored;
}
export async function initializeLocalization(document = globalThis.document) {
  if (document && !initializedDocuments.has(document)) {
    initializedDocuments.add(document);
    document.querySelector?.("#application-language")?.addEventListener("change", event => { void setLanguage(event.target.value, { document }); });
  }
  const owned = choiceVersion;
  const saved = await readLanguagePreference();
  if (owned === choiceVersion) apply(saved, document);
}
