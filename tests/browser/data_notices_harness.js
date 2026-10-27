// This existing fixture exercises explicit English output. French defaults and
// both-language state preservation are covered by localization_harness and the
// full bundled-app acceptance, with strict canonical and GPX comparisons.
import { setLanguage } from "../../src/sugarglider/web/static/i18n.js";
import { appendRegionSources } from "../../src/sugarglider/web/static/terrain_attribution.js";
import { DATA_NOTICES } from "../../src/sugarglider/web/static/data_notice_registry.js";
import { appendMapSources, initializeSourceInformation } from "../../src/sugarglider/web/static/data_notices.js";
import { exportCanonicalCandidate } from "../../src/sugarglider/web/static/local_gpx_export.js";

function assert(value, message) { if (!value) throw Error(message); }
export async function run() {
  await setLanguage("en", { persist: false, document: null });
  const cases = [];
  const fixture = await (await fetch("../fixtures/ign_terrain_attribution.json")).json();
  const manifest = structuredClone(fixture.manifest);
  manifest.components.map.files[1] = structuredClone(DATA_NOTICES.map_payload);
  const host = document.getElementById("fixture");
  appendRegionSources(host, manifest);
  const panel = host.querySelector(".region-sources");
  assert(panel.textContent.includes("IGN — RGE ALTI® 5 m") && panel.textContent.includes("ESA WorldCover / Daylight") && panel.textContent.includes("ODbL 1.0"), "map, routing and terrain licences remain separately visible");
  assert(panel.querySelectorAll(".terrain-editions li").length === 17, "seventeen IGN editions preserved");
  assert(panel.textContent.includes("exact raster input inventory are absent") && panel.textContent.includes("provisional") && !panel.textContent.includes("2020 v100 is verified"), "lineage limit is explicit");
  cases.push("exact_map_and_ign_sources_share_offline_inventory_without_publication_claim");
  const headings = DATA_NOTICES.sections.map(source => source.title);
  assert(headings.every(title => panel.textContent.includes(title)), "complete shared inventory rendered");
  assert([...panel.querySelectorAll("pre")].every((pre, i) => pre.textContent === DATA_NOTICES.documents[i].text), "full licence texts agree with canonical source");
  cases.push("all_source_sections_full_documents_and_reading_help_match_shared_registry");
  for (const key of ["sha256", "byte_size", "format", "path"]) {
    const wrong = structuredClone(manifest); wrong.components.map.files[1][key] = key === "byte_size" ? 7 : "unknown";
    const other = document.createElement("div");
    assert(!appendMapSources(other, wrong) && !other.querySelector("a") && other.textContent.includes("unsupported"), "changed identity remains unknown");
  }
  cases.push("changed_map_hash_size_format_and_path_never_inherit_source_claims");
  for (const wrong of [null, {}, {schema_version:2,components:{map:{files:[null,null]}}}]) {
    const other = document.createElement("div"); assert(!appendMapSources(other, wrong) && !other.querySelector("a"), "missing source stays unknown");
  }
  cases.push("missing_or_malformed_map_metadata_is_neutral");
  const hostile = structuredClone(manifest);
  hostile.attribution = '<img src=x onerror=alert(1)>'; hostile.licence_url = "javascript:alert(1)";
  hostile.components.map.files[1].url = "https://attacker.invalid/";
  const other = document.createElement("div"); appendMapSources(other, hostile);
  assert(!other.querySelector("img,script,svg") && !other.textContent.includes("alert(1)"), "untrusted strings ignored");
  const official = new Set(DATA_NOTICES.sections.flatMap(source => source.links.map(link => link.url)));
  for (const a of other.querySelectorAll("a")) assert(official.has(a.href) && a.rel === "noopener noreferrer" && a.target === "_blank", "only deliberate fixed official links");
  cases.push("hostile_html_and_manifest_urls_cannot_change_notice_text_or_destinations");
  initializeSourceInformation(document); initializeSourceInformation(document);
  const dialog = document.getElementById("data-licences-dialog");
  assert(document.querySelectorAll("#data-licences-dialog").length === 1, "one accessible source dialog");
  const before = JSON.stringify(manifest), nativeFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = () => { requests++; throw Error("offline"); };
  const candidate = {routing_profile:"hike",route:{routing_profile:"hike",name:"Source notice regression",geometry:[[2,48],[2.001,48.001]]}, reached_stops:[],approximated_stops:[],dropped_stops:[]};
  const gpx = await exportCanonicalCandidate(candidate).blob.text();
  try {
    for (const button of document.querySelectorAll("[data-source-information]")) {
      button.focus(); button.click(); assert(dialog.open, "entry opens offline");
      assert(dialog.getAttribute("aria-labelledby") === "data-licences-title", "dialog has an accessible name");
      assert(dialog.textContent.includes("existing public V1 offer") && dialog.textContent.includes("No approved V2"), "historical offer is not confused with approval");
      dialog.querySelector("button").click();
      await new Promise(resolve => setTimeout(resolve, 0));
      assert(document.activeElement === button, "close restores entry focus");
    }
    panel.open = true;
    for (const details of panel.querySelectorAll("details")) { details.open = true; details.open = false; }
    assert(requests === 0 && JSON.stringify(manifest) === before, "disclosure uses no fetch, mutation or routing");
    assert(await exportCanonicalCandidate(candidate).blob.text() === gpx, "opening sources leaves GPX bytes unchanged");
    const xml = new DOMParser().parseFromString(gpx, "application/xml");
    assert(xml.querySelectorAll("trk").length === 1 && xml.querySelectorAll("trkseg").length === 1 && !xml.querySelector("rte,extensions,ele"), "clean single-track GPX preserved");
  } finally { globalThis.fetch = nativeFetch; }
  cases.push("map_export_and_footer_entries_open_offline_with_keyboard_focus_restoration");
  cases.push("disclosure_makes_zero_network_or_authority_mutations");
  cases.push("gpx_bytes_single_track_and_segment_and_no_extensions_are_unchanged");
  cases.push("public_v1_offer_and_provisional_v2_identity_remain_distinct");
  panel.open = false;
  window.dataNoticeHarness = {manifest};
  return cases;
}
