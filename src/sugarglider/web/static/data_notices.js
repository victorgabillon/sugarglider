import { t, tr } from "./i18n.js";
import { DATA_NOTICES } from "./data_notice_registry.js";

// Trusted packaged copy only. Manifest prose, URLs and publication flags are ignored.
function element(parent, tag, text) {
  const node = parent.ownerDocument.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.append(node); return node;
}

function link(parent, label, url) {
  const node = element(parent, "a", label);
  node.href = url; node.target = "_blank"; node.rel = "noopener noreferrer";
  return node;
}

function sections(parent) {
  for (const section of DATA_NOTICES.sections) {
    element(parent, "h4", section.title);
    for (const text of section.paragraphs) element(parent, "p", text);
    const list = element(parent, "ul");
    for (const item of section.links) link(element(list, "li"), item.label, item.url);
  }
  const documents = element(parent, "details");
  documents.dataset.sourceDisclosure = "licence-documents";
  element(documents, "summary", t("Full data licences and software/font notices"));
  for (const document of DATA_NOTICES.documents) {
    element(documents, "h4", `${document.role} · ${document.licence}`);
    element(documents, "pre", document.text);
  }
  const reading = element(parent, "details");
  reading.dataset.sourceDisclosure = "reading";
  element(reading, "summary", t("Complete database offer and reading guide"));
  for (const text of DATA_NOTICES.reading) element(reading, "p", text);
}

export function appendMapSources(parent, manifest) {
  const files = manifest?.components?.map?.files;
  const known = manifest?.schema_version === 2 && Array.isArray(files) && files.length === 2
    && files[1] !== null && typeof files[1] === "object"
    && Object.entries(DATA_NOTICES.map_payload).every(([key, value]) => files[1][key] === value);
  if (!known) {
    element(parent, "p", t("Map source inventory is unavailable or unsupported for this installed payload. No source edition or licence is inferred."));
    return false;
  }
  element(parent, "p", t("Sources for this exact retained PMTiles payload. The layered notice wording is provisional for publisher review; source recognition is not publication authorization."));
  sections(parent); return true;
}

export function initializeSourceInformation(document) {
  let dialog = document.getElementById("data-licences-dialog");
  if (dialog) return;
  dialog = document.createElement("dialog"); dialog.id = "data-licences-dialog";
  dialog.className = "data-licences-dialog"; dialog.setAttribute("aria-labelledby", "data-licences-title");
  const title = element(dialog, "h2", t("Data sources and licences")); title.id = "data-licences-title";
  const close = element(dialog, "button", t("Close source information")); close.type = "button"; close.className = "button secondary";
  element(dialog, "p", t("Routes use OpenStreetMap data. Installed Regions contain the source information for each exact stored map, routing graph and terrain payload. Elevation results keep their own height reference. Imported GPX data is not assigned a regional source by this notice."));
  element(dialog, "p", t("The following provisional inventory documents the retained V2 map identified below. It does not assert that this map is active, installed, approved or publicly offered. Unrecognized installed data keeps an explicit unknown source. IGN and Copernicus terrain notices remain in installed-region details."));
  element(dialog, "p", tr`Retained V2 map SHA-256: ${DATA_NOTICES.map_payload.sha256}`);
  const published = element(dialog, "p", t("Published regional downloads and immutable manifests: "));
  link(published, t("Sugarglider regional data offer"), "https://victorgabillon.github.io/sugarglider-regions/");
  element(dialog, "p", t("This link is the existing public V1 offer. No approved V2 offer or URL is asserted. Any future public V2 offer must expose all complete component files and its exact bound source notices."));
  sections(dialog); document.body.append(dialog);
  let opener = null;
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { if (opener?.isConnected) opener.focus({preventScroll:true}); });
  for (const button of document.querySelectorAll("[data-source-information]")) {
    button.addEventListener("click", () => { opener = button; dialog.showModal(); close.focus(); });
  }
}
