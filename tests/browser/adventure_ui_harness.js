// This existing fixture exercises explicit English output. French defaults and
// both-language state preservation are covered by localization_harness and the
// full bundled-app acceptance, with strict canonical and GPX comparisons.
import { setLanguage } from "../../src/sugarglider/web/static/i18n.js";
import { createAdventureSpeech } from "../../src/sugarglider/web/static/adventure_speech.js";
import { initializeAdventureDialog } from "../../src/sugarglider/web/static/adventure_dialog.js";
import { createAdventureResults, forestAdventureLimitation, adventureTradeoffLabels } from "../../src/sugarglider/web/static/adventure_results.js";
import { renderRouteChoices } from "../../src/sugarglider/web/static/route_results.js";
import { exportCanonicalCandidate } from "../../src/sugarglider/web/static/local_gpx_export.js";
import { readSpeechProviderPreference, writeSpeechProviderPreference, openPwaStore, PWA_STORES } from "../../src/sugarglider/web/static/pwa_store.js";
import { setup } from "./adventure_controller_harness.js";
import { state } from "../../src/sugarglider/web/static/state.js";
const assert = (ok, message) => { if (!ok) throw Error(message); };
async function until(check, label) {
  for (let i = 0; i < 500; i++) { if (check()) return; await new Promise(resolve => setTimeout(resolve, 10)); }
  throw Error(`Did not settle: ${label}`);
}

export async function frame(width = 390, height = 844, scale = 1) {
  const markup = new DOMParser().parseFromString(await (await fetch("/src/sugarglider/web/static/index.html")).text(), "text/html");
  markup.querySelectorAll("script,link[rel=manifest]").forEach(node => node.remove());
  for (const node of markup.querySelectorAll("link[href],img[src]")) {
    const field = node.tagName === "LINK" ? "href" : "src", value = node.getAttribute(field);
    if (value.startsWith("/static/")) node.setAttribute(field, `/src/sugarglider/web${value}`);
  }
  const element = document.createElement("iframe"); element.style.cssText = `width:${width}px;height:${height}px;border:0`;
  const loaded = new Promise(resolve => element.addEventListener("load", resolve, { once: true }));
  element.srcdoc = markup.documentElement.outerHTML; document.body.append(element); await loaded;
  const doc = element.contentDocument; doc.documentElement.style.fontSize = `${16 * scale}px`;
  doc.getElementById("adventure-launch").hidden = false;
  return { element, doc, root: doc.getElementById("adventure-dialog"), byId: id => doc.getElementById(`adventure-${id}`) };
}
export function accounts(model, initiallyConnected = true) {
  let connected = initiallyConnected;
  const state = () => ({ accounts: connected ? [{ id: "oaiapp_synthetic", label: "Synthetic account", connected: true, plan_usage: true }] : [],
    selected_account: connected ? "oaiapp_synthetic" : null, models: connected ? [{ id: "synthetic-model", label: "Synthetic available model" }] : [] });
  return { ...model, status: async () => state(), models: async () => state(),
    signIn: async () => { connected = true; return state(); }, select: async () => state(), signOut: async () => { connected = false; return state(); } };
}

export async function runAdventureUiHarness() {
  await setLanguage("en", { persist: false, document: null });
  const cases = [];
  for (const language of ["fr", "en"]) {
    const r=await setup(), f=await frame(360,640,2);let forgotten=0;
    await setLanguage(language,{persist:false,document:f.doc});
    const receipt={operation_id:"a".repeat(32),prompt:"Original user request",state:"interrupted",kind:"adventure",schema_version:1};
    const operations={cancel(){},recovery:async()=>receipt,forget:async id=>{assert(id===receipt.operation_id,"forget is bound to the interrupted identity");forgotten++;return true;},run(){throw Error("Recovery must never execute work");}};
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById("plan-with-ai"),planner:r.planner,operations,
      model:accounts(r.model),speech:{cancel(){}},elevation:{clear(){}},getContext:async()=>r.input.context,onChooseStart(){},onChooseEnd(){},onResult(){}});
    try{
      f.byId("text").value="A newer unsent draft";await dialog.open();await until(()=>!f.byId("restore-request").disabled&&!f.byId("restore-request").hidden,"recovery choice");
      assert(f.byId("text").value==="A newer unsent draft"&&r.calls.length===0&&r.nativeCalls.length===0,"recovery cannot replace new text or rerun work");
      assert(f.byId("progress").textContent.includes(language==="fr"?"Rien ne redémarre automatiquement":"Nothing restarts automatically"),"explicit retry warning localized");
      f.byId("restore-request").click();assert(f.byId("text").value===receipt.prompt,"explicitly restore original description");
      f.byId("forget-request").click();await until(()=>forgotten===1&&f.byId("restore-request").hidden,"forget receipt");
      assert(!f.byId("text").value&&r.calls.length===0&&r.nativeCalls.length===0,"forget removes recovered text without inference or routing");
      cases.push(`interrupted_request_explicit_restore_forget_${language}`);
    }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  }

  for (const language of ["fr", "en"]) {
    const r = await setup(), f = await frame(); await setLanguage(language, { persist: false, document: f.doc });
    r.input.context.start = null; r.proposal.intent.start = { name: "Ambiguous local start", lat: null, lon: null };
    const getData = r.region.getRegionData;
    r.region.getRegionData = async () => {
      const data = await getData();
      return { ...data, searchPlaceNames: async name => name === "Ambiguous local start"
        ? { identity: data.identity, results: [.005, .006].map(lat => ({ name, lat, lon: .005 })) } : data.searchPlaceNames(name) };
    };
    let output = null;
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { measure: async () => ({}), clear() {} },
      getContext: async () => r.input.context, onChooseStart() {}, onChooseEnd() {}, onResult(value) { output = value; },
      geocoding: () => ({ available: true }), searchLocations() { throw Error("Local disambiguation must not search online"); } });
    try {
      await dialog.open(); f.byId("text").value = "Start at Ambiguous local start"; f.byId("text").dispatchEvent(new Event("input"));
      f.byId("refine").checked = false;
      await until(() => !f.byId("generate").disabled, "ambiguous Start ready"); f.byId("generate").click();
      await until(() => !f.byId("endpoint-search").hidden, "local disambiguation");
      assert(f.byId("endpoint-explanation").textContent.includes(language === "fr" ? "Plusieurs lieux" : "Several locations"), "Ambiguity is localized");
      assert(f.byId("endpoint-results").children.length === 2 && r.nativeCalls.length === 0, "Neither ambiguous point is chosen automatically");
      f.byId("endpoint-results").firstElementChild.click();
      await until(() => !f.byId("review").hidden, "selected local endpoint review");
      assert(r.nativeCalls.length === 0, "Selected search result still needs explicit endpoint review");
      f.byId("confirm").click(); await until(() => output !== null, "confirmed local result routed");
      assert(output.chosen.endpoint_resolution.start.evidence === "selected_local_result" && r.calls.length === 1, "Explicit disambiguation keeps provenance and avoids another model call");
      cases.push(`ambiguous_local_start_requires_selection_and_review_${language}`);
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  await setLanguage("en", { persist: false, document: null });
  for (const language of ["fr", "en"]) for (const name of ["Bastille", "Place de la Bastille, Paris"]) {
    const r = await setup(), f = await frame();
    await setLanguage(language, { persist: false, document: f.doc });
    r.input.context.start = null; r.proposal.intent.start = { name, lat: null, lon: null };
    let lookups = 0, regionViews = 0, publications = 0;
    const before = JSON.stringify(state), contextBefore = JSON.stringify(r.input.context);
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { measure: async () => ({}), clear() {} },
      getContext: async () => r.input.context, onChooseStart() {}, onChooseEnd() {}, onResult() { publications++; },
      onRegions() { regionViews++; }, geocoding: () => ({ available: true, attribution: "IGN Géoplateforme · BAN / BD TOPO" }),
      searchLocations: async query => {
        assert(query === name, "Only the named place crosses the disclosed geocoder boundary"); lookups++;
        return { local: [], localMessage: "", remoteMessage: "", remote: [{ name: "Place de la Bastille", lat: 48.853, lon: 2.369, source: "online" }] };
      } });
    try {
      await dialog.open(); f.byId("text").value = "Un tour autour de " + name; f.byId("text").dispatchEvent(new Event("input"));
      await until(() => !f.byId("generate").disabled, "named place ready"); f.byId("generate").click();
      await until(() => !f.byId("endpoint-search").hidden, "disclosed named place lookup");
      assert(lookups === 0 && r.calls.length === 1 && r.nativeCalls.length === 0, "No automatic IGN, model retry or route call");
      assert(f.byId("endpoint-explanation").textContent.includes(language === "fr" ? "n’a pas été trouvé" : "was not found"), "Unresolved name is localized and distinct from missing Start");
      f.byId("search-ign").click(); await until(() => f.byId("endpoint-results").querySelector("button"), "IGN results");
      f.byId("endpoint-results").querySelector("button").click();
      await until(() => !dialog.busy(), "outside coverage failure");
      assert(f.byId("error").textContent.includes(language === "fr" ? "en dehors de la région hors ligne" : "outside the selected offline region"), "Outside coverage is localized");
      assert(f.byId("error").textContent.includes("Place de la Bastille") && !f.byId("regions").hidden, "Found name and region action remain useful");
      assert(f.byId("regions").textContent === (language === "fr" ? "Voir les régions" : "View regions"), "Region action localized");
      assert(lookups === 1 && r.calls.length === 1 && r.nativeCalls.length === 0 && publications === 0 && regionViews === 0, "Failure never downloads, switches, generates or publishes");
      assert(JSON.stringify(state) === before && JSON.stringify(r.input.context) === contextBefore, "Route, selection and editor preserved");
      f.byId("regions").click(); await until(() => regionViews === 1, "explicit region review");
      assert(!f.root.open && r.calls.length === 1, "Region review closes AI without another model call");
      cases.push(`named_bastille_explicit_ign_outside_region_preserves_state_${language}_${name}`);
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  for (const language of ["fr", "en"]) for (const conflict of [false, true]) {
    const r = await setup(), f = await frame(); await setLanguage(language, { persist: false, document: f.doc });
    r.proposal.intent.start = conflict ? { name: "Bastille", lat: null, lon: null } : null;
    if (!conflict) r.input.context.start = null;
    const before = JSON.stringify(r.input.context);
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { measure: async () => ({}), clear() {} },
      getContext: async () => r.input.context, onChooseStart() {}, onChooseEnd() {}, onResult() { throw Error("Failure cannot publish"); } });
    try {
      await dialog.open();
      if (conflict) { await until(() => !f.byId("include-pins").disabled, "account ready"); f.byId("include-pins").click(); await until(() => !f.byId("include-pins").disabled && !f.byId("keep-start").parentElement.hidden, "captured endpoints"); f.byId("keep-start").click(); }
      f.byId("text").value = "Un petit tour"; f.byId("text").dispatchEvent(new Event("input"));
      await until(() => !f.byId("generate").disabled, "failure ready"); f.byId("generate").click();
      await until(() => !dialog.busy() && f.byId("error").textContent, "localized failure");
      const expected = conflict ? (language === "fr" ? "ne correspond pas" : "conflicts with") : (language === "fr" ? "Où souhaitez-vous partir" : "Where would you like to start");
      assert(f.byId("error").textContent.includes(expected), "Missing and conflicting Start have separate localized errors");
      assert(JSON.stringify(r.input.context) === before && r.calls.length === 1 && r.nativeCalls.length === 0, "Failure preserves the chosen endpoint without retry");
      cases.push(`missing_or_conflicting_start_localized_${language}_${conflict}`);
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  await setLanguage("en", { persist: false, document: null });
  {
    const place = id => ({ canonical_id: id, status: "reached", local_category: "ruins" });
    const round = { proposal: { wishes: [{ metric: "woodland", goal: "maximize", importance: "high", value: null }] },
      result: { candidates: ["forest", "history", "other"].map(id => ({ id, diagnostics: { within_tolerance: true } })) },
      assessment: { assessments: [{ candidate_id: "forest", nature: { woodland: .55 }, places: [] },
        { candidate_id: "history", nature: { woodland: .51 }, places: [place("a"), place("b")] },
        { candidate_id: "other", nature: { woodland: .3 }, places: [] }] } };
    const before = JSON.stringify(round), labels = adventureTradeoffLabels(round);
    assert(labels.get("forest") === "Forest-focused" && labels.get("history") === "Historical highlights" && !labels.has("other"), "only measured tradeoffs earn labels; no manufactured third category");
    assert(JSON.stringify(round) === before, "tradeoff labels never mutate immutable results");
    round.assessment.assessments.forEach(item => { item.nature = null; });
    assert(adventureTradeoffLabels(round).size === 0, "unknown woodland never earns a forest label");
    round.assessment.assessments.forEach(item => { item.nature = { woodland: .8 }; item.loop_geometry = { severe_out_and_back: true }; });
    assert(adventureTradeoffLabels(round).size === 0 && forestAdventureLimitation(round).includes("No reasonably shaped"), "forest cannot make an unacceptable loop earn a quality label");
    cases.push("tradeoff_labels_use_checked_places_and_measured_forest_without_relabeling_unknowns");
  }
  {
    const round={proposal:{wishes:[{metric:"woodland",goal:"maximize",value:null}]},result:{candidates:[{id:"a",diagnostics:{within_tolerance:true}}]},assessment:{assessments:[{candidate_id:"a",nature:{woodland:.37}}]}};
    assert(forestAdventureLimitation(round).includes("37.0%"),"partial forest preference is visibly unsatisfied");
    round.assessment.assessments[0].nature=null;
    assert(forestAdventureLimitation(round).includes("unknown"),"missing nature cannot establish forest success");
    round.assessment.assessments[0].nature={woodland:.6};assert(forestAdventureLimitation(round)==="","actually measured predominant forest can satisfy qualitative wording");
    cases.push("forest_limitations_distinguish_partial_unknown_and_measured_coverage");
  }

  {
    const calls = []; let finish;
    const transport = { nativeAvailable: true, cancelOwner() { finish?.(null); }, request: async type => {
      calls.push(type);
      if (type === "adventure_speech_start") return new Promise(resolve => { finish = resolve; });
      return null;
    } };
    const speech = createAdventureSpeech({ transport, origin: "https://appassets.androidplatform.net" });
    speech.cancel(); assert(calls.length === 0, "idle cleanup must not send a native speech command at startup");
    const abort = new AbortController(), started = speech.start("fr-FR", "on_device", abort.signal).catch(error => error);
    abort.abort(); speech.cancel();
    assert((await started).name === "AbortError" && calls.filter(type => type === "adventure_speech_cancel").length === 1,
      "owned recording cancellation is sent once and discards late transcription");
    cases.push("idle_speech_cleanup_is_silent_and_owned_abort_is_single_flight");
  }
  {
    const calls = []; let finish, cancellations = 0;
    const transport = { nativeAvailable: true, cancelOwner() { cancellations++; }, request: async (type, fields, options) => {
      calls.push({ type, fields });
      if (type.endsWith("_start")) return new Promise(resolve => { finish = text => resolve(options.parseReply(JSON.stringify({ schema_version: 1,
        request_id: "synthetic", type: "adventure_speech_result", status: "partial", mode: "on_device", text }))); });
      return null;
    } };
    const speech = createAdventureSpeech({ transport, origin: "https://appassets.androidplatform.net" });
    await speech.stop(); assert(!calls.length, "idle Done never contacts native speech");
    const started = speech.start("en-GB", "platform");
    await speech.stop();
    assert(calls[0].fields.language === "en-GB" && calls[0].fields.mode === "platform", "explicit language and provider cross the strict bridge");
    assert(calls[1].type === "adventure_speech_stop" && cancellations === 0, "Done waits for recognition rather than aborting its result");
    finish("A useful unfinished draft");
    assert((await started).status === "partial", "an interrupted transcript is labelled partial");
    cases.push("speech_done_keeps_ownership_and_partial_drafts_are_explicit");
  }
  {
    const r = await setup(), f = await frame(), { byId } = f;
    const calls = []; let finish, reject, stopCount = 0;
    const speech = { status: async () => ({ mode: "on_device" }), cancel() {},
      start: (language, mode) => { calls.push({ language, mode }); return new Promise((resolve, fail) => { finish = resolve; reject = fail; }); },
      stop: async () => { stopCount++; finish({ status: "completed", text: "Avec des châteaux.", mode: "on_device" }); } };
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"),
      planner: r.planner, getContext: async () => r.input.context, model: accounts(r.model), speech,
      elevation: { clear() {} }, onResult() {}, onChooseStart() {}, onChooseEnd() {} });
    try {
      await dialog.open(); await until(() => !byId("microphone").disabled, "speech controls ready");
      assert(byId("language").closest("details").id === "adventure-speech-settings" && byId("language").options[0].textContent.includes("en-GB"), "interface language is suggested in dedicated speech settings");
      byId("language").value = "fr-FR"; byId("text").value = "Je veux courir.";
      byId("microphone").click(); await until(() => calls.length === 1, "first dictation");
      byId("text").value += " En forêt."; byId("finish-speech").click();
      await until(() => !byId("microphone").disabled, "Done returns editable transcript");
      assert(stopCount === 1 && byId("text").value === "Je veux courir. En forêt.\nAvec des châteaux.", "Done appends and preserves concurrent manual edits");
      byId("speech-service").value = "platform"; byId("language").value = "en-US";
      byId("microphone").click(); await until(() => calls.length === 2, "additional phrase");
      assert(byId("finish-speech").hidden && calls[1].mode === "platform" && calls[1].language === "en-US", "platform UI owns completion, selected language is exact");
      finish({ status: "partial", text: "Another viewpoint.", mode: "platform" });
      await until(() => !byId("microphone").disabled, "partial added");
      assert(byId("text").value.endsWith("\nAnother viewpoint.") && byId("speech-status").textContent.includes("draft carefully"), "successive recordings append and uncertain text is visible");
      const saved = byId("text").value;
      byId("microphone").click(); await until(() => calls.length === 3, "cancelled recording");
      const cancelledReject = reject;
      byId("stop-speech").click();
      assert(byId("text").value === saved, "Cancel keeps earlier text");
      byId("text").value = "x".repeat(7999);
      byId("microphone").click(); await until(() => calls.length === 4, "bounded combined transcript");
      cancelledReject(new DOMException("Cancelled", "AbortError"));
      await new Promise(resolve => setTimeout(resolve, 0));
      assert(byId("microphone").disabled && !byId("speech-status").textContent.includes("cancelled"), "old cancellation cannot overwrite a newer recording or release its controls");
      finish({ status: "completed", text: "Keep this phrase too", mode: "platform" });
      await until(() => byId("text").value.length > 8000, "oversized editor draft preserved");
      assert(byId("generate").disabled && byId("microphone").disabled && byId("text").value.endsWith("Keep this phrase too"), "oversized combined draft keeps text and prevents sending or more recording");
      assert(r.calls.length === 0 && r.nativeCalls.length === 0, "speech has no model, geographic or route calls");
      cases.push("visible_language_provider_done_append_cancel_and_text_bound");
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  {
    const r=await setup(),f=await frame(),prior=await readSpeechProviderPreference();let recordings=0;
    const speech={status:async()=>({mode:"on_device"}),cancel(){},start:async()=>{recordings++;return {status:"cancelled",mode:"platform",text:null};}};
    await writeSpeechProviderPreference("platform");
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById("plan-with-ai"),planner:r.planner,getContext:async()=>r.input.context,model:accounts(r.model),speech,elevation:{clear(){}},onResult(){},onChooseStart(){},onChooseEnd(){}});
    try {
      await until(()=>f.byId("speech-service").value==="platform","explicit provider restored");
      assert(recordings===0&&r.calls.length===0,"remembered provider cannot start recording or inference");
      const store=await openPwaStore();
      const record=await store.get(PWA_STORES.publicRuntime,"adventure-speech-provider");store.close();
      assert(JSON.stringify(record)==='{"schema_version":1,"mode":"platform"}',"remembered choice stores only schema and provider enum");
      f.byId("speech-service").value="";f.byId("speech-service").dispatchEvent(new Event("change"));
      for(let i=0;i<100&&await readSpeechProviderPreference()!=="device";i++)await new Promise(resolve=>setTimeout(resolve,10));
      assert(await readSpeechProviderPreference()==="device","explicit switch back to local is remembered");
      cases.push("explicit_provider_preference_restores_without_recording_or_consent_bypass");
    } finally {
      dialog.clear();r.planner.invalidate();f.element.remove();
      if(prior)await writeSpeechProviderPreference(prior);else {const store=await openPwaStore();await store.remove(PWA_STORES.publicRuntime,"adventure-speech-provider");store.close();}
    }
  }
  for (const [width, height, scale] of [[360, 800, 1], [390, 844, 1], [1280, 800, 1], [360, 640, 2]]) {
    const r = await setup(), f = await frame(width, height, scale), { byId } = f;
    let output = null, selected = null, returned = false, spoken = 0;
    const busy = [], speech = { status: async () => ({ mode: "on_device" }),
      start: async () => { spoken++; return { status: "completed", text: "Une aventure historique de 2,2 km", mode: "on_device" }; }, cancel() {} };
    const results = createAdventureResults({ root: f.doc.getElementById("adventure-result"), candidatesRoot: f.doc.getElementById("candidate-list"),
      onManual: () => { returned = true; }, onShowMap: () => {} });
    const choose = id => { selected = output.chosen.result.candidates.find(c => c.id === id);
      renderRouteChoices(f.doc.getElementById("candidate-list"), output.chosen.result.candidates, id, choose); results.render(output, selected); };
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"),
      planner: r.planner, getContext: async () => r.input.context, model: accounts(r.model, false), speech,
      elevation: { measure: async () => ({}), clear() {} }, onBusy: value => busy.push(value),
      onChooseStart() {}, onChooseEnd() {}, onResult: value => { output = value; choose(value.chosen.result.candidates[0].id); } });
    try {
      await dialog.open(); await until(() => !byId("connect").disabled, "disconnected account ready");
      assert(byId("generate").disabled && r.calls.length === 0, "opening panel does not infer or route");
      byId("connect").click(); await until(() => byId("model").value === "synthetic-model" && !byId("microphone").disabled, "account models");
      byId("microphone").click(); await until(() => byId("text").value.startsWith("Une aventure"), "editable transcription");
      assert(spoken === 1 && r.calls.length === 0 && r.nativeCalls.length === 0, "microphone sends no model request or route call");
      byId("text").value += " avec de beaux points de vue"; byId("text").dispatchEvent(new Event("input"));
      assert(!byId("generate").disabled, "one explicit Generate action available");
      assert(f.root.querySelector(".adventure-body").clientHeight >= 100, "Header and footer leave a usable scroll area at large text");
      assert(f.root.scrollWidth <= f.root.clientWidth + 1 && f.doc.documentElement.scrollWidth <= width + 1, `no horizontal overflow ${width}/${scale}`);
      const body = f.root.querySelector(".adventure-body"), pinLabel = byId("include-pins").labels[0];
      const labelBounds = pinLabel.getBoundingClientRect(), textBounds = pinLabel.querySelector("span").getBoundingClientRect();
      assert(body.scrollWidth <= body.clientWidth + 1, `dialog content must not scroll sideways ${width}/${scale}`);
      assert(textBounds.left >= labelBounds.left && textBounds.right <= labelBounds.right + 1,
        `pin label text stays inside its control ${width}/${scale}`);
      byId("generate").click(); await until(() => !byId("review").hidden, "review text endpoints"); byId("confirm").click(); await until(() => output !== null && !f.root.open, "normal proposal-to-GPX UI");
      assert(r.calls.length === 2 && busy[0] && busy.at(-1) === false, "one bounded AI operation");
      const interesting = output.chosen.result.candidates.find(candidate => candidate.reached_stops.length > 0);
      const alternate = [...f.doc.querySelectorAll(".candidate-select")].find(button => button.dataset.candidateId === interesting.id); alternate.click();
      assert(selected.id === interesting.id && selected.reached_stops.length > 0, "ordinary candidate selection owns the adventure route");
      assert(f.doc.querySelectorAll(".adventure-card-summary").length === output.chosen.result.candidates.length, "comparison annotations do not duplicate");
      byId("stories-open").click(); assert(!byId("stories").hidden && byId("stories").textContent.includes("AI story"), "story provenance visible");
      assert(byId("stories").querySelector("article strong").textContent.includes("reached") && byId("stories").textContent.includes("No historical claim has been independently verified"), "reached stories lead and citation matching is not independent verification");
      assert([...byId("stories").querySelectorAll("a")].every(link => link.protocol === "https:" && link.rel.includes("noopener")), "links are safe explicit actions");
      const xml = new DOMParser().parseFromString(await exportCanonicalCandidate(selected).blob.text(), "application/xml");
      assert(xml.getElementsByTagName("trkpt").length === selected.route.geometry.length, "selected UI GPX is canonical native geometry");
      byId("return-manual").click(); assert(returned, "explicit manual-plan return is wired");
      cases.push(`account_voice_edit_generate_places_select_gpx_${width}_${scale}`);
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  {
    const r = await setup(), f = await frame(); r.proposal.places[0].importance = "mandatory";
    let output = null;
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { measure: async () => ({}), clear() {} },
      getContext: async () => r.input.context, onChooseStart() {}, onChooseEnd() {}, onResult: value => { output = value; } });
    try {
      await dialog.open(); f.byId("text").value = "Keep the castle required"; f.byId("text").dispatchEvent(new Event("input"));
      await until(() => !f.byId("generate").disabled, "connected"); f.byId("generate").click();
      await until(() => !f.byId("review").hidden, "mandatory review");
      assert(f.byId("confirm").disabled && r.nativeCalls.length === 0, "no automatic mandatory acceptance");
      f.byId("required").querySelector("input").click(); f.byId("confirm").click();
      await until(() => Boolean(output), "accepted required stop");
      assert(output.chosen.request.waypoints.some(p => p.constraint_strength === "exact" && p.id === "adventure/castle"), "explicit required point preserved");
      cases.push("mandatory_review_requires_user_checkbox_before_routing");
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  {
    const r = await setup(), f = await frame(); let output = null;
    r.input.context.end = null; r.proposal.intent.end = { name: "Fixture 2", lat: null, lon: null };
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { measure: async () => ({}), clear() {} },
      getContext: async () => r.input.context, onChooseStart() {}, onChooseEnd() {}, onResult: value => { output = value; } });
    try {
      await dialog.open(); f.byId("text").value = "Finish at Fixture 2"; f.byId("text").dispatchEvent(new Event("input")); f.byId("refine").checked = false;
      await until(() => !f.byId("generate").disabled, "connected"); f.byId("generate").click();
      await until(() => !f.byId("review").hidden, "End review");
      assert(f.byId("required").textContent.includes("End found on this device: Fixture 2") && r.nativeCalls.length === 0, "local destination needs explicit review before routing");
      f.byId("confirm").click(); await until(() => Boolean(output), "confirmed local End");
      assert(output.chosen.request.end.name === "Fixture 2" && output.chosen.endpoint_resolution.end.evidence === "unique_exact_local_name", "End comes from the local index, not guessed coordinates");
      cases.push("named_end_resolved_locally_and_reviewed_before_routing");
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  {
    const r = await setup(), f = await frame(); let output = null;
    r.input.context.start = null;r.input.context.end = null;
    const dialog = initializeAdventureDialog({ root:f.root, launcher:f.doc.getElementById('plan-with-ai'), planner:r.planner,
      model:accounts(r.model),speech:{cancel(){}},elevation:{measure:async()=>({}),clear(){}},
      getContext:async()=>r.input.context,onChooseStart(){},onChooseEnd(){},onResult:value=>{output=value;} });
    try {
      await dialog.open();f.byId('text').value='Run from the described Start to the described End';f.byId('text').dispatchEvent(new Event('input'));f.byId('refine').checked=false;
      await until(()=>!f.byId('generate').disabled,'optional endpoints allow Generate');
      assert(f.byId('start').textContent.includes('from your description')&&r.calls.length===0,'opening without endpoints requests no location or model');
      f.byId('generate').click();await until(()=>!f.byId('review').hidden,'both endpoint proposals reviewed');
      assert(f.byId('required').textContent.includes('Proposed Start')&&f.byId('required').textContent.includes('Proposed End')&&r.nativeCalls.length===0,'unverified coordinates are labelled and do not route yet');
      assert(!f.byId('choose-start').disabled&&!f.byId('choose-end').disabled,'map selection remains available during endpoint review');
      f.byId('confirm').click();await until(()=>Boolean(output),'reviewed endpoints routed');
      cases.push('no_manual_endpoints_text_or_speech_can_propose_both_for_review');
    }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  }
  {
    const r=await setup(),f=await frame();let output=null;const contextOptions=[];
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById('plan-with-ai'),planner:r.planner,
      model:accounts(r.model),speech:{cancel(){}},elevation:{measure:async()=>({}),clear(){}},getContext:async options=>{contextOptions.push(options);return r.input.context;},
      onChooseStart(){},onChooseEnd(){},onResult:value=>{output=value;}});
    try{
      await dialog.open();f.byId('text').value='Use places from my description';f.byId('text').dispatchEvent(new Event('input'));f.byId('refine').checked=false;
      await until(()=>!f.byId('generate').disabled,'chosen endpoint controls ready');
      f.byId('generate').click();
      await until(()=>!f.byId('review').hidden,'explicitly released manual endpoints reviewed');f.byId('confirm').click();await until(()=>Boolean(output),'new reviewed endpoints accepted');
      const sent=JSON.parse(r.calls[0].input).planning_context;
      assert(sent.start===null&&sent.end===null&&r.input.context.start!==null&&r.input.context.end!==null,'choosing inference leaves the manual planner untouched');
      assert(!contextOptions.some(options=>options?.includeMapPins || options?.includePlaces),'released manual endpoints are not used to select the online landmark context');
      cases.push('explicit_prompt_endpoint_choice_preserves_manual_draft');
    }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  }
  {
    const r = await setup(), f = await frame(); let contextCalls = 0, finish;
    const busy = [];
    const dialog = initializeAdventureDialog({ root: f.root, launcher: f.doc.getElementById("plan-with-ai"), planner: r.planner,
      model: accounts(r.model), speech: { cancel() {} }, elevation: { clear() {} }, onBusy: value => busy.push(value),
      getContext: () => ++contextCalls === 1 ? Promise.resolve(r.input.context) : new Promise(resolve => { finish = resolve; }),
      onChooseStart() {}, onChooseEnd() {}, onResult: () => { throw Error("Cancelled context must not commit"); } });
    try {
      await dialog.open(); f.byId("text").value = "Synthetic adventure"; f.byId("text").dispatchEvent(new Event("input"));
      await until(() => !f.byId("generate").disabled, "ready"); f.byId("generate").click();
      await until(() => Boolean(finish), "waiting for context"); f.byId("cancel").click(); finish(r.input.context);
      await until(() => busy.at(-1) === false, "cancel drain");
      assert(r.calls.length === 0 && r.nativeCalls.length === 0, "cancel before context cannot start model work");
      cases.push("cancel_before_region_context_never_starts_model");
    } finally { dialog.clear(); r.planner.invalidate(); f.element.remove(); }
  }
  {
    const r=await setup(),f=await frame();let contextCalls=0,finish,mapChoices=0;const busy=[];
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById('plan-with-ai'),planner:r.planner,
      model:accounts(r.model),speech:{cancel(){}},elevation:{clear(){}},onBusy:value=>busy.push(value),
      getContext:()=>++contextCalls===2?new Promise(resolve=>{finish=resolve;}):Promise.resolve(r.input.context),
      onChooseStart(){assert(busy.at(-1)===false,'map selection waits for the cancelled operation to drain');mapChoices++;r.input.context.start={name:'New map Start',lat:.006,lon:.005};},
      onChooseEnd(){},onResult(){throw Error('Cancelled endpoint change must not commit');}});
    try{
      await dialog.open();f.byId('text').value='Keep this description while I choose the Start';f.byId('text').dispatchEvent(new Event('input'));
      await until(()=>!f.byId('generate').disabled,'ready to start');f.byId('generate').click();await until(()=>Boolean(finish),'context pending');
      f.byId('choose-start').click();assert(!f.root.open&&mapChoices===0,'map choice cancels before taking over planner controls');
      finish(r.input.context);await until(()=>mapChoices===1,'cancel drained before map choice');
      await dialog.open(undefined, {selectedEndpoint:{kind:'start',coordinate:r.input.context.start}});await until(()=>!f.byId('generate').disabled,'resumed after map selection');
      assert(f.byId('text').value==='Keep this description while I choose the Start'&&f.byId('start').textContent.includes('New map Start')&&r.calls.length===0&&r.nativeCalls.length===0,'description and updated manual endpoint return without hidden generation');
      cases.push('choose_endpoint_during_planning_drains_and_preserves_description');
    }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  }
  return cases;
}
