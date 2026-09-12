import {
  exportCanonicalCandidate, fixedCoordinate, localGpxFilename, LocalGpxExportError,
  MAX_GPX_STOPS, MAX_GPX_VERTICES,
} from "../../src/sugarglider/web/static/local_gpx_export.js";
import { PUBLIC_PROFILE_METADATA } from "../../src/sugarglider/web/static/public_profile_metadata.js";
import { createGpxFileSaver, parseSaveReply } from "../../src/sugarglider/web/static/native_gpx_save.js";
import { createNativeBridgeTransport } from "../../src/sugarglider/web/static/native_bridge_transport.js";
import { createLocalGpxExporter } from "../../src/sugarglider/web/static/local_gpx_client.js";

export async function runPr41LocalGpxHarness() {
  const fixture = await (await fetch("/tests/fixtures/pr41_local_gpx.json")).json();
  const candidate = () => structuredClone(fixture.candidate);
  const scenarios = [];
  for (const [name, run] of [
    ["canonical_python_gpx_fields_and_clean_single_track", async () => {
      const { document } = await exported(candidate());
      equal(projection(document), fixture.expected, "Python canonical GPX fields");
      equal(document.querySelectorAll("trk").length, 1, "one track");
      equal(document.querySelectorAll("trkseg").length, 1, "one segment");
      equal(document.querySelectorAll("rte, extensions, ele, time").length, 0, "no invented extensions/elevation/timestamps");
    }],
    ["all_six_public_profiles_preserved", async () => {
      equal(Object.keys(PUBLIC_PROFILE_METADATA).sort(), ["city_bike", "gravel_bike", "hike", "mountain_bike", "road_bike", "trail_run"], "exact public IDs");
      for (const profile of Object.values(PUBLIC_PROFILE_METADATA)) {
        const input = candidate(); input.routing_profile = input.route.routing_profile = profile.id;
        const { document } = await exported(input);
        equal(document.querySelector("trk > name").textContent, `${input.route.name} — ${profile.display_name}`, "profile name");
        equal(document.querySelector("trk > type").textContent, {walking:"hiking",running:"running",cycling:"cycling"}[profile.activity_kind], "activity type");
      }
      assert(Object.isFrozen(PUBLIC_PROFILE_METADATA.hike.capabilities), "generated metadata immutable");
    }],
    ["no_network_or_input_mutation", async () => {
      const input = candidate(), before = JSON.stringify(input), previous = globalThis.fetch;
      try {
        globalThis.fetch = () => { throw new Error("Export attempted a network request"); };
        freeze(input);
        await exported(input);
        equal(JSON.stringify(input), before, "canonical candidate unchanged");
      } finally { globalThis.fetch = previous; }
    }],
    ["reached_and_approximated_stops_interleave_in_visit_order", async () => {
      const { document } = await exported(candidate());
      const stops = [...document.querySelectorAll("wpt")];
      equal(stops.map((stop) => stop.querySelector("name").textContent), ["1. Forêt <ouverte> — approximate", "2. Étape & source"], "actual visit order");
      const approach = fixture.candidate.approximated_stops[0].resolved_approach.coordinate;
      equal(Number(stops[0].getAttribute("lat")), approach.lat, "routed approach, not semantic place");
    }],
    ["dropped_stops_and_private_extra_fields_never_exported", async () => {
      const input = candidate();
      input.dropped_stops.push({id:"dropped",name:"SECRET_DROPPED"});
      input.diagnostics.details.private_test = "SECRET_DIAGNOSTIC";
      input.route.extra_test = "SECRET_EXTRA";
      const { xml } = await exported(input);
      assert(!xml.includes("SECRET_"), "only GPX field allowlist");
      equal(new DOMParser().parseFromString(xml, "application/xml").querySelectorAll("wpt").length, 2, "dropped stop omitted");
    }],
    ["python_float_rounding_including_negative_zero_and_even_ties", () => {
      for (const { value, formatted } of fixture.coordinates) equal(fixedCoordinate(value), formatted, "Python .8f");
      equal(fixedCoordinate(-0), "-0.00000000", "negative zero retained");
    }],
    ["unicode_filename_and_xml_cleaning", async () => {
      for (const { name, filename } of fixture.filenames) equal(localGpxFilename(name), filename, "Python attachment filename");
      const input = candidate(); input.route.name = 'Water & <woods> "été"\u0000\u0009\uFFFE\uFFFF\uD800';
      const { document } = await exported(input);
      equal(document.querySelector("metadata > name").textContent, 'Water & <woods> "été" — Hike', "XML controls/surrogates removed; text escaped");
    }],
    ["forged_arrival_and_reported_distance_rejected", () => {
      const far = candidate(); far.reached_stops[0].resolved_approach.coordinate.lat += 1;
      rejects(() => exportCanonicalCandidate(far), "export_stop_not_reached");
      const falseMeasurement = candidate(); falseMeasurement.reached_stops[0].route_to_approach_m = 3;
      rejects(() => exportCanonicalCandidate(falseMeasurement), "export_stop_not_reached");
    }],
    ["arrival_just_inside_and_outside_tolerance", async () => {
      for (const offset of [24.99, 25.01]) {
        const input = candidate(); input.approximated_stops = [];
        input.route.geometry = [[2, 48], [2.01, 48]];
        const stop = input.reached_stops[0];
        stop.resolved_approach.coordinate = {lon:2.005,lat:48+offset/6_371_008.8*180/Math.PI};
        stop.route_to_approach_m = offset;
        if (offset < 25) await exported(input);
        else rejects(() => exportCanonicalCandidate(input), "export_stop_not_reached");
      }
    }],
    ["invalid_approximation_is_explicit", () => {
      for (const change of [{distance_m:20}, {distance_m:501}, {normal_tolerance_m:NaN}, {configured_maximum_m:-1}]) {
        const input = candidate(); Object.assign(input.approximated_stops[0], change);
        rejects(() => exportCanonicalCandidate(input), "invalid_export_approximation");
      }
    }],
    ["invalid_profile_and_identity_never_fall_back", () => {
      for (const id of ["foot", "bike", "constructor", "unknown", null]) {
        const input = candidate(); input.routing_profile = input.route.routing_profile = id;
        rejects(() => exportCanonicalCandidate(input), "invalid_export_profile");
      }
      const mismatch = candidate(); mismatch.routing_profile = "road_bike";
      rejects(() => exportCanonicalCandidate(mismatch), "invalid_export_profile");
    }],
    ["invalid_geometry_and_segment_breaks_never_repaired", () => {
      for (const geometry of [[], [[2,48]], [[2,48],[NaN,48]], [[2,48],[181,48]], [[2,48],null,[3,48]], [[[2,48],[3,48]],[[4,48],[5,48]]]]) {
        const input = candidate(); input.route.geometry = geometry;
        rejects(() => exportCanonicalCandidate(input), "invalid_export_geometry");
      }
    }],
    ["bounded_vertices_stops_and_arrival_work", () => {
      const tooMany = candidate(); tooMany.route.geometry = Array(MAX_GPX_VERTICES+1).fill([2,48]);
      rejects(() => exportCanonicalCandidate(tooMany), "invalid_export_geometry");
      const stops = candidate(); stops.reached_stops = Array(MAX_GPX_STOPS+1).fill(stops.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(stops), "export_limit_exceeded");
      const work = candidate(); work.route.geometry = Array(MAX_GPX_VERTICES).fill([2,48]);
      work.reached_stops = Array(20).fill(work.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(work), "export_limit_exceeded");
    }],
    ["duplicate_or_conflicting_stop_outcomes_rejected", () => {
      const duplicate = candidate(); duplicate.reached_stops.push(duplicate.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(duplicate), "invalid_export_stops");
      const conflict = candidate(); conflict.dropped_stops.push({id:conflict.reached_stops[0].id});
      rejects(() => exportCanonicalCandidate(conflict), "invalid_export_stops");
    }],
  ]) { await run(); scenarios.push(name); }
  for (const [name, run] of workerScenarios(candidate)) { await run(); scenarios.push(name); }
  for (const [name, run] of documentScenarios(candidate)) { await run(); scenarios.push(name); }
  return scenarios;
}

function workerScenarios(candidate) {
  const fake = () => {
    const workers = [], timers = [], lifecycle = new EventTarget();
    const client = createLocalGpxExporter({
      createWorker: () => {
        const value = { terminated:false, postMessage(data) { this.sent=data; }, terminate() { this.terminated=true; } };
        workers.push(value); return value;
      },
      lifecycleTarget:lifecycle,
      schedule:(callback) => { timers.push(callback); return timers.length; },
      cancelScheduled:() => {},
    });
    const reply = () => {
      const worker = workers.at(-1), result=exportCanonicalCandidate(worker.sent.candidate);
      worker.onmessage({data:{type:"result",id:worker.sent.id,...result}});
    };
    return {client,workers,timers,lifecycle,reply};
  };
  return [
    ["real_worker_matches_canonical_output", async () => {
      const client=createLocalGpxExporter({lifecycleTarget:null});
      try {
        assert(client.prepare(), "module worker available");
        const result=await client.exportCandidate(candidate());
        equal(await result.blob.text(), await exportCanonicalCandidate(candidate()).blob.text(), "real worker preserves exact GPX bytes");
      } finally { client.invalidate(); }
    }],
    ["large_export_keeps_main_thread_responsive", async () => {
      const client=createLocalGpxExporter({lifecycleTarget:null}), input=candidate();
      input.reached_stops=[];input.approximated_stops=[];
      input.route.geometry=Array.from({length:20000},(_,i)=>[2+(i%2)*.001,48+(i%3)*.001]);
      let ticked=false;
      const timer=setTimeout(()=>{ticked=true;},0);
      try {
        const result=await client.exportCandidate(input);
        assert(ticked, "UI timer ran while worker formatted track");
        equal(new DOMParser().parseFromString(await result.blob.text(),"application/xml").querySelectorAll("trkpt").length,20000,"no simplified geometry");
      } finally {clearTimeout(timer);client.invalidate();}
    }],
    ["worker_snapshots_only_export_fields_and_is_single_flight", async () => {
      const h=fake(), input=candidate(); input.capability_test="never transfer";
      const first=h.client.exportCandidate(input);
      input.route.geometry[0][0]+=1;
      assert(!JSON.stringify(h.workers[0].sent).includes("never transfer"),"private extra omitted");
      assert(!Object.hasOwn(h.workers[0].sent.candidate.route,"analysis"),"analysis omitted");
      equal(h.workers[0].sent.candidate.route.geometry[0],candidate().route.geometry[0],"captured geometry unchanged by caller");
      await asyncRejects(h.client.exportCandidate(candidate()),"export_busy");
      h.reply();await first;h.client.invalidate();
    }],
    ["pagehide_cancels_and_old_worker_callbacks_cannot_touch_new_export", async () => {
      const h=fake();const first=h.client.exportCandidate(candidate());
      const rejected=first.catch((error)=>error.name), oldError=h.workers[0].onerror;
      h.lifecycle.dispatchEvent(new Event("pagehide"));
      equal(await rejected,"AbortError","pagehide cancellation");
      assert(h.workers[0].terminated,"old worker released");
      const second=h.client.exportCandidate(candidate());
      oldError();h.reply();await second;h.client.invalidate();
    }],
    ["worker_timeout_and_late_timer_ownership", async () => {
      const h=fake(), first=h.client.exportCandidate(candidate());
      h.reply();await first;
      const second=h.client.exportCandidate(candidate());
      h.timers[0]();h.reply();await second;
      const third=h.client.exportCandidate(candidate());
      const rejected=asyncRejects(third,"export_timed_out");h.timers[2]();await rejected;
      assert(h.workers[0].terminated,"timed-out worker released");h.client.invalidate();
    }],
    ["worker_failure_or_unavailability_never_runs_inline_fallback", async () => {
      const unavailable=createLocalGpxExporter({createWorker:()=>{throw new Error("unsupported");},lifecycleTarget:null});
      await asyncRejects(unavailable.exportCandidate(candidate()),"export_worker_unavailable");
      const h=fake(), pending=h.client.exportCandidate(candidate());
      const rejected=asyncRejects(pending,"export_worker_unavailable");h.workers[0].onerror();await rejected;
      assert(h.workers[0].terminated,"failed worker released");h.client.invalidate();
    }],
  ];
}

async function asyncRejects(promise, code) {
  let error;try {await promise;}catch(caught){error=caught;}
  assert(error instanceof LocalGpxExportError && error.code===code,`expected ${code}, got ${error}`);
}

async function exported(input) {
  const { blob, filename } = exportCanonicalCandidate(input);
  equal(blob.type, "application/gpx+xml", "GPX MIME");
  const xml = await blob.text();
  const document = new DOMParser().parseFromString(xml, "application/xml");
  assert(!document.querySelector("parsererror"), "valid XML");
  equal(document.documentElement.namespaceURI, "http://www.topografix.com/GPX/1/1", "GPX namespace");
  return { xml, document, filename };
}
function projection(document) {
  return {name:document.querySelector("metadata > name").textContent, description:document.querySelector("metadata > desc").textContent,
    type:document.querySelector("trk > type").textContent,
    points:[...document.querySelectorAll("trkpt")].map(coordinate),
    waypoints:[...document.querySelectorAll("wpt")].map((point)=>({coordinate:coordinate(point),name:point.querySelector("name").textContent,
      description:point.querySelector("desc").textContent,type:point.querySelector("type").textContent}))};
}
function coordinate(element) { return {lat:element.getAttribute("lat"),lon:element.getAttribute("lon")}; }
function freeze(value) { if(value && typeof value === "object") {Object.values(value).forEach(freeze);Object.freeze(value);} }
function rejects(run, code) { let error; try { run(); } catch (caught) { error=caught; } assert(error instanceof LocalGpxExportError && error.code===code, `expected ${code}; got ${error}`); }
function assert(value, message) { if (!value) throw new Error(message); }
function equal(actual, expected, message) { assert(JSON.stringify(actual)===JSON.stringify(expected), `${message}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`); }

function documentScenarios(candidate) {
  const prepared = () => exportCanonicalCandidate(candidate());
  const reply = (status, request_id = "test-1") => ({schema_version:1,request_id,type:"save_gpx_result",status});
  const failure = async (promise, fragment) => {
    let error; try {await promise;} catch (caught) {error=caught;}
    assert(error?.message.includes(fragment), `expected error containing ${fragment}, got ${error}`);
  };
  return [
    ["ordinary_browser_keeps_existing_download", async () => {
      const input=prepared(), saver=createGpxFileSaver({transport:{nativeAvailable:false},lifecycleTarget:null});
      const result=await saver.save(input);
      equal(result.status,"browser","browser download selected");
      assert(result.blob===input.blob,"same immutable Blob");
    }],
    ["native_binary_document_uses_shared_handshake_and_exact_bytes", async () => {
      const input=prepared(), frames=[];
      const port={onmessage:null,postMessage(payload) {
        if (typeof payload==="string") {
          const request=JSON.parse(payload);equal(request.type,"hello","only shared handshake is text");
          queueMicrotask(()=>this.onmessage({data:JSON.stringify({schema_version:1,request_id:request.request_id,
            type:"hello_result",outing_slug:null,participant_id:null,active:false,state:"stopped",
            last_published_at:null,pending_sample:false,stop_warning:null})}));
        } else {
          assert(payload instanceof ArrayBuffer,"binary transport");frames.push(payload);
          const size=new DataView(payload).getUint32(0);
          const header=JSON.parse(new TextDecoder().decode(new Uint8Array(payload,4,size)));
          equal(Object.keys(header).sort(),["byte_count","filename","request_id","schema_version","type"],"bounded metadata only");
          equal(header.filename,input.filename,"same filename");
          equal(header.byte_count,input.blob.size,"exact declared size");
          equal(header.type,"save_gpx","document-only binary protocol");
          queueMicrotask(()=>this.onmessage({data:JSON.stringify(reply("saved",header.request_id))}));
        }
      }};
      const transport=createNativeBridgeTransport({port,pageNonce:"a".repeat(32),lifecycleTarget:null});
      try {
        const saver=createGpxFileSaver({transport,lifecycleTarget:null});
        equal((await saver.save(input)).status,"saved","native confirmed completion");
        equal(frames.length,1,"one binary send");
        const frame=frames[0], offset=4+new DataView(frame).getUint32(0);
        equal(Array.from(new Uint8Array(frame,offset)),Array.from(new Uint8Array(await input.blob.arrayBuffer())),"unchanged GPX bytes");
      } finally {transport.invalidate();}
    }],
    ["native_document_cancel_and_failures_are_explicit", async () => {
      for (const [status, expected] of [["cancelled",null],["busy","picker"],["unavailable","could not open"],["write_failed","completely"]]) {
        let calls=0;
        const transport={nativeAvailable:true,saveGpx:async()=>{calls+=1;return reply(status);}};
        const saver=createGpxFileSaver({transport,lifecycleTarget:null});
        if (expected) await failure(saver.save(prepared()),expected);
        else equal((await saver.save(prepared())).status,"cancelled","cancelled means no success");
        equal(calls,1,"no automatic retry or browser fallback");
      }
    }],
    ["document_reply_rejects_uri_coordinates_and_authority", () => {
      assert(parseSaveReply(JSON.stringify(reply("saved"))),"valid reply");
      for (const field of ["uri","latitude","participant_token","owner_token"]) {
        equal(parseSaveReply(JSON.stringify({...reply("saved"),[field]:"forbidden"})),null,"extra private field rejected");
      }
      equal(parseSaveReply(JSON.stringify(reply("invented"))),null,"unknown outcome");
    }],
    ["pagehide_invalidates_native_save_and_blocks_concurrent_save", async () => {
      const lifecycle=new EventTarget();let finish, owner, calls=0;
      const transport={nativeAvailable:true,saveGpx:(_filename,_bytes,options)=>{
        calls+=1;owner=options.owner;return new Promise((resolve)=>{finish=resolve;});
      },cancelOwner:(value)=>{assert(value===owner,"exact operation cancelled");finish(null);}};
      const saver=createGpxFileSaver({transport,lifecycleTarget:lifecycle});
      const first=saver.save(prepared());
      while (!finish) await new Promise((resolve)=>setTimeout(resolve,0));
      await failure(saver.save(prepared()),"in progress");
      const rejected=first.catch((error)=>error.name);
      lifecycle.dispatchEvent(new Event("pagehide"));
      equal(await rejected,"AbortError","page departure does not claim failure/success on another page");
      equal(calls,1,"one pending save");
    }],
    ["pagehide_during_blob_read_never_dispatches_native_request", async () => {
      const lifecycle=new EventTarget(), input=prepared();let release, calls=0;
      const original=input.blob.arrayBuffer.bind(input.blob);
      input.blob.arrayBuffer=()=>new Promise((resolve)=>{release=()=>original().then(resolve);});
      const saver=createGpxFileSaver({transport:{nativeAvailable:true,saveGpx:()=>{calls+=1;},cancelOwner:()=>{}},lifecycleTarget:lifecycle});
      const first=saver.save(input), rejected=first.catch((error)=>error.name);
      lifecycle.dispatchEvent(new Event("pagehide"));release();
      equal(await rejected,"AbortError","stale buffer result cancelled");equal(calls,0,"no stale send");
    }],
    ["unknown_native_save_outcome_never_claims_saved_or_retries", async () => {
      let calls=0;
      const saver=createGpxFileSaver({transport:{nativeAvailable:true,saveGpx:async()=>{calls+=1;return null;}},lifecycleTarget:null});
      await failure(saver.save(prepared()),"check it before trying again");equal(calls,1,"no retry on uncertain outcome");
    }],
  ];
}
