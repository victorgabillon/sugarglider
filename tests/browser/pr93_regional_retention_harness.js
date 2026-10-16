import { createLocalRegionData, createLocalPlacesSession } from "../../src/sugarglider/web/static/local_region_data.js";

const assert = (value, message) => { if (!value) throw Error(message); };
export async function run() {
  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const data = createLocalRegionData(fixture.manifest, structuredClone(fixture));
  const places = createLocalPlacesSession(data);
  assert(Object.isFrozen(places) && Object.keys(places).sort().join() === "identity,searchPlaceNames", "Places retains no full analysis API");
  assert(places.identity === data.identity, "Same immutable regional identity");
  for (const query of ["castle", "water", "test", "unknown place"]) {
    assert(JSON.stringify(places.searchPlaceNames(query)) === JSON.stringify(data.searchPlaceNames(query)), "Search order and metadata unchanged");
  }
  const unavailable = createLocalPlacesSession(createLocalRegionData(fixture.manifest));
  assert(unavailable.searchPlaceNames("castle").available === false, "Missing Places remains unavailable");
  const withNature = data.analyzeNature(fixture.route);
  assert(Math.abs(withNature.nature_score - fixture.expected.nature_score) < 1e-6, "Full analysis retains golden Nature result");
  // The standalone acceptance runner uses explicit CDP collection outside this
  // call's stack. Ordinary browser harnesses never rely on nondeterministic GC.
  window.createRegionalRetentionProbe = async () => {
    const raw = await (await fetch("../fixtures/pr40_regional_data.json")).json();
    const full = createLocalRegionData(raw.manifest, raw);
    window.retainedPlaces = createLocalPlacesSession(full);
    window.retainedNature = new WeakRef(raw.nature);
    return { nature_features: raw.nature.features.length, expected: full.searchPlaceNames("castle") };
  };
  return ["places_session_has_only_name_search_and_immutable_identity", "name_order_metadata_and_missing_semantics_unchanged", "full_nature_analysis_unchanged"];
}
