import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";
import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { captureRegionalRoutingReference, regionalRoutingReference } from "./regional_routing_reference.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { ELEVATION_SAMPLING_VERSION } from "./elevation_sampling.js";

const ALGORITHM = "distance-box-v1";
const REQUEST_LIMIT = 262144, REPLY_LIMIT = 1048576;
const HEIGHT_REFERENCE = "unresolved vertical datum; verified V2 elevation component manifest";

// Bounded one-worker preparation. Termination owns cancellation during sampling.
export function prepareRouteElevation(geometry, distance, signal) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./elevation_sampling_worker.js", import.meta.url), {type:"module"});
    const timer = setTimeout(() => finish(Error("elevation_sampling_timeout")), 10000);
    const abort = () => finish(new DOMException("Elevation cancelled.", "AbortError"));
    const finish = (error, result) => { clearTimeout(timer); signal?.removeEventListener("abort", abort); worker.terminate(); error ? reject(error) : resolve(result); };
    signal?.addEventListener("abort", abort, {once:true});
    worker.onmessage = ({data}) => finish(data.error ? Error(data.error) : null, data.result);
    worker.onerror = () => finish(Error("elevation_sampling_failed"));
    if (signal?.aborted) abort(); else worker.postMessage({geometry, distance});
  });
}

export function createRouteElevationClient({transport = nativeBridgeTransport} = {}) {
  const owner = Object.freeze({client:"route-elevation"});
  async function analyze(fields) {
    if (JSON.stringify(fields).length + 160 > REQUEST_LIMIT) throw Error("elevation_request_too_large");
    const result = await transport.request("route_elevation", fields, {owner,timeoutMs:65000,parseReply:parseRouteElevationReply});
    if (!result) throw Error("elevation_transport_unavailable");
    if (result.type === "local_elevation_failure") throw Error(result.code);
    if(result.type!=="local_elevation_result")throw Error("elevation_reply_invalid");
    validateBinding(result, fields);
    return deepFreeze(result);
  }
  function cancel(operation) {
    return transport.request("cancel_route_elevation", {operation_id:operation}, {owner,timeoutMs:65000,parseReply:parseRouteElevationReply});
  }
  return Object.freeze({analyze,cancel});
}

// The canonical candidate is never mutated. A selected-result sidecar is the
// future chart's source and cannot enter ranking, snapshots or GPX by accident.
export function createSelectedRouteElevation({versions, client = createRouteElevationClient(), prepare = prepareRouteElevation,
  onChange = () => {}, lifecycleTarget = globalThis, operationId = randomOperationId} = {}) {
  let epoch = 0, context = null, selected = null, active = null, desired = null, destroyed = false;
  let snapshot = deepFreeze({status:"idle",candidate_id:null,result:null,diagnostic:null});
  const cache = new Map();
  let knownRegionKey=null;
  function publish(status, candidate, result = null, diagnostic = null, cacheHit = false) {
    snapshot = deepFreeze({status,candidate_id:candidate?.id ?? null,result,diagnostic,cache_hit:cacheHit}); onChange(snapshot);
  }
  function invalidate() {
    epoch++; desired = null; selected = null; cache.clear();
    if (active) { active.abort.abort(); if (active.operation) void client.cancel(active.operation).catch(()=>{}); }
    publish("idle", null);
  }
  function sync(candidate, generation, regionId) {
    if (destroyed) return;
    if (context !== generation || (selected && selected.regionId !== regionId)) { invalidate(); context = generation; }
    if (!candidate || !generation || candidate.diagnostics?.details?.local_routing?.engine !== "valhalla-mobile") {
      if (selected) invalidate(); return;
    }
    if (selected?.candidate === candidate && selected.regionId === regionId) return;
    epoch++; selected = {candidate,regionId}; desired = {candidate,regionId,epoch};
    if (active) { active.abort.abort(); if (active.operation) void client.cancel(active.operation).catch(()=>{}); }
    publish("loading", candidate);
    void pump();
  }
  async function pump() {
    if (active || !desired || destroyed) return;
    const job = desired; desired = null;
    const owned = {abort:new AbortController(),operation:null}; active = owned;
    const current = () => !destroyed && job.epoch === epoch && !owned.abort.signal.aborted;
    try {
      const prepared = await prepare(job.candidate.route.geometry,job.candidate.route.summary.distance_m,owned.abort.signal);
      if (!current()) return;
      await versions.withCommittedRegions(async rows => {
        if (!current()) return;
        const pinned = job.candidate.diagnostics.details.local_routing.regional_version;
        const row = rows.find(r=>r.region_id===pinned?.region_id && r.status==="committed");
        if (!row || row.manifest.build_id!==pinned.build_id || row.manifest.components.routing.component_id!==pinned.routing_pack_id
          || job.regionId !== null && job.regionId !== row.region_id) throw Error("elevation_region_changed");
        const reference = await regionalRoutingReference(row.manifest);
        if (!current()) return;
        const key = JSON.stringify([job.candidate.id,prepared.geometry_sha256,job.candidate.route.routing_profile,
          job.candidate.route.summary.distance_m,reference,ALGORITHM,ELEVATION_SAMPLING_VERSION,prepared.sampling_interval_m]);
        const cacheHit=cache.has(key);
        let result = cache.get(key);
        if (!result) {
          owned.operation = operationId();
          result = await client.analyze({elevation_version:1,operation_id:owned.operation,candidate_id:job.candidate.id,
            profile:job.candidate.route.routing_profile,distance_m:job.candidate.route.summary.distance_m,
            regional_reference:reference,...prepared});
          if (!current()) return;
          cache.set(key,result); while(cache.size>8) cache.delete(cache.keys().next().value);
        }
        if (current()) publish("ready",job.candidate,result,null,cacheHit);
      });
    } catch(error) { if(current()) publish("unavailable",job.candidate,null,error.message); }
    finally { if(active===owned) active=null; if(desired&&!destroyed) void pump(); }
  }
  lifecycleTarget?.addEventListener?.("pagehide",()=>{destroyed=true;invalidate();},{once:true});
  function cancel() {
    epoch++; desired=null;
    if(active){active.abort.abort();if(active.operation)void client.cancel(active.operation).catch(()=>{});}
    publish("unavailable",selected?.candidate,null,"elevation_cancelled");
  }
  function regionChanged(reference) {
    if(!reference)return;
    const key=referenceKey(reference);
    if(knownRegionKey!==null&&knownRegionKey!==key)invalidate();
    knownRegionKey=key;
  }
  return Object.freeze({sync,invalidate,cancel,regionChanged,snapshot:()=>snapshot});
}

export function parseRouteElevationReply(payload) {
  if (typeof payload!=="string" || payload.length>REPLY_LIMIT) return null;
  try {
    const v=JSON.parse(payload);
    if(v.schema_version!==1 || typeof v.request_id!=="string") return null;
    if(v.type==="local_elevation_failure") return exact(v,["schema_version","request_id","type","operation_id","code"])
      && (v.operation_id===null || /^[a-f0-9]{32}$/.test(v.operation_id)) && /^elevation_[a-z_]+$|^invalid_elevation_request$/.test(v.code) ? v:null;
    if(v.type==="local_elevation_cancel_result") return exact(v,["schema_version","request_id","type","operation_id","accepted"])
      && /^[a-f0-9]{32}$/.test(v.operation_id) && typeof v.accepted==="boolean" ? v:null;
    if(v.type!=="local_elevation_result" || !exact(v,["schema_version","request_id","type","elevation_version","operation_id","candidate_id","regional_reference","sampling_interval_m","sample_coordinates","analysis","measurements"])) return null;
    captureRegionalRoutingReference(v.regional_reference);
    if(v.elevation_version!==1 || !/^geometry:[a-f0-9]{64}$/.test(v.candidate_id) || !/^[a-f0-9]{32}$/.test(v.operation_id)
      || !Number.isFinite(v.sampling_interval_m) || v.sampling_interval_m<50 || v.sampling_interval_m>100) return null;
    const a=v.analysis;
    if(!exact(a,["schema_version","algorithm_version","parameters","source_sha256","geometry_sha256","profile_sha256","routing_profile","route_distance_m","height_reference","coverage","available_sample_count","analyzed_distance_m","unknown_distance_m","raw_observed_ascent_m","raw_observed_descent_m","observed_ascent_m","observed_descent_m","total_ascent_m","total_descent_m","minimum_height_m","maximum_height_m","segments","samples"]) || a.schema_version!==1 || a.algorithm_version!==ALGORITHM
      || !["complete","partial","unavailable"].includes(a.coverage) || a.source_sha256!==v.regional_reference.elevation.manifest.sha256
      || !/^[a-f0-9]{64}$/.test(a.geometry_sha256) || !/^[a-f0-9]{64}$/.test(a.profile_sha256) || a.height_reference!==HEIGHT_REFERENCE
      || !Object.hasOwn(PUBLIC_PROFILE_METADATA,a.routing_profile)
      || !Number.isFinite(a.route_distance_m) || a.route_distance_m<=0 || a.route_distance_m>200000) return null;
    if(!exact(a.parameters,["smoothing_radius_m","maximum_gap_m","boundary_policy","missing_policy"]) || a.parameters.smoothing_radius_m!==50 || a.parameters.maximum_gap_m!==100
      || a.parameters.boundary_policy!=="constant-extension-retain-endpoints" || a.parameters.missing_policy!=="split-no-fill") return null;
    if(!Array.isArray(a.samples)||a.samples.length<2||a.samples.length>2048||!Array.isArray(a.segments)||a.segments.length>a.samples.length
      ||!Array.isArray(v.sample_coordinates)||v.sample_coordinates.length!==a.samples.length) return null;
    for(let i=0;i<a.samples.length;i++) {const p=a.samples[i],c=v.sample_coordinates[i];
      if(!exact(p,["index","distance_m","height_m","filtered_height_m","segment_index"])||p.index!==i||!Number.isFinite(p.distance_m)||p.distance_m<0||p.distance_m>a.route_distance_m
        ||i>0&&p.distance_m<=a.samples[i-1].distance_m || !height(p.height_m)||!height(p.filtered_height_m)
        ||(p.height_m===null)!==(p.filtered_height_m===null) || !(p.segment_index===null||Number.isInteger(p.segment_index)&&p.segment_index>=0&&p.segment_index<a.segments.length)
        ||!Array.isArray(c)||c.length!==2||!Number.isFinite(c[0])||Math.abs(c[0])>180||!Number.isFinite(c[1])||Math.abs(c[1])>90) return null;
    }
    let previousEnd=-1;
    for(let index=0;index<a.segments.length;index++){
      const segment=a.segments[index];
      if(!exact(segment,["first_index","last_index","distance_m"])||!Number.isInteger(segment.first_index)||!Number.isInteger(segment.last_index)
        ||segment.first_index<=previousEnd||segment.last_index<segment.first_index||segment.last_index>=a.samples.length
        ||segment.distance_m!==a.samples[segment.last_index].distance_m-a.samples[segment.first_index].distance_m)return null;
      for(let i=segment.first_index;i<=segment.last_index;i++)if(a.samples[i].height_m===null||a.samples[i].segment_index!==index
        ||i>segment.first_index&&a.samples[i].distance_m-a.samples[i-1].distance_m>100)return null;
      previousEnd=segment.last_index;
    }
    if(a.samples.some((p,i)=>p.height_m===null ? p.segment_index!==null : p.segment_index===null||i<a.segments[p.segment_index].first_index||i>a.segments[p.segment_index].last_index))return null;
    const complete=a.segments.length===1&&a.segments[0].first_index===0&&a.segments[0].last_index===a.samples.length-1;
    if(a.coverage!== (complete?"complete":a.available_sample_count?"partial":"unavailable")
      ||complete&&(a.total_ascent_m===null||a.total_descent_m===null))return null;
    if(a.samples[0].distance_m!==0||a.samples.at(-1).distance_m!==a.route_distance_m) return null;
    for(const key of ["raw_observed_ascent_m","raw_observed_descent_m","observed_ascent_m","observed_descent_m","total_ascent_m","total_descent_m"])
      if(a[key]!==null&&(!Number.isFinite(a[key])||a[key]<0))return null;
    if(!height(a.minimum_height_m)||!height(a.maximum_height_m)||!Number.isInteger(a.available_sample_count)||a.available_sample_count!==a.samples.filter(p=>p.height_m!==null).length
      ||![a.analyzed_distance_m,a.unknown_distance_m].every(n=>Number.isFinite(n)&&n>=0&&n<=a.route_distance_m)
      ||a.coverage!=="complete"&&(a.total_ascent_m!==null||a.total_descent_m!==null))return null;
    if((a.minimum_height_m===null)!==(a.available_sample_count===0)||(a.maximum_height_m===null)!==(a.available_sample_count===0)
      ||a.minimum_height_m!==null&&a.minimum_height_m>a.maximum_height_m
      ||Math.abs(a.analyzed_distance_m+a.unknown_distance_m-a.route_distance_m)>1e-7
      ||Math.abs(a.segments.reduce((sum,s)=>sum+s.distance_m,0)-a.analyzed_distance_m)>1e-7)return null;
    const observed=a.segments.some(s=>s.last_index>s.first_index);
    for(const key of ["raw_observed_ascent_m","raw_observed_descent_m","observed_ascent_m","observed_descent_m"])
      if((a[key]!==null)!==observed)return null;
    if(observed&&(a.observed_ascent_m>a.raw_observed_ascent_m+1e-7||a.observed_descent_m>a.raw_observed_descent_m+1e-7))return null;
    for(const segment of a.segments)for(const i of [segment.first_index,segment.last_index])
      if(a.samples[i].height_m!==a.samples[i].filtered_height_m)return null;
    if(!exact(v.measurements,["native_height_ms","analysis_ms","total_ms","pss_bytes","cold_start"])||typeof v.measurements.cold_start!=="boolean"
      ||!["native_height_ms","analysis_ms","total_ms","pss_bytes"].every(k=>Number.isSafeInteger(v.measurements[k])&&v.measurements[k]>=0))return null;
    return v;
  }catch{return null;}
}
function validateBinding(result,fields) {
  const a=result.analysis;
  if(result.operation_id!==fields.operation_id||result.candidate_id!==fields.candidate_id||a.routing_profile!==fields.profile||a.geometry_sha256!==fields.geometry_sha256
    ||a.route_distance_m!==fields.distance_m||result.sampling_interval_m!==fields.sampling_interval_m
    ||referenceKey(result.regional_reference)!==referenceKey(fields.regional_reference)
    ||a.samples.length!==fields.samples.length||a.samples.some((p,i)=>p.distance_m!==fields.samples[i][0]||result.sample_coordinates[i][0]!==fields.samples[i][2]||result.sample_coordinates[i][1]!==fields.samples[i][1])) throw Error("elevation_identity_mismatch");
}
function randomOperationId(){return [...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,"0")).join("");}
function exact(v,fields){return v&&typeof v==="object"&&!Array.isArray(v)&&Object.keys(v).length===fields.length&&fields.every(k=>Object.hasOwn(v,k));}
function height(v){return v===null||Number.isFinite(v)&&v>=-16384&&v<=16384;}

function referenceKey(value){const r=captureRegionalRoutingReference(value);return JSON.stringify([r.region_id,r.build_id,r.pack_id,r.bounds,r.manifest.byte_size,r.manifest.sha256,r.archive.byte_size,r.archive.sha256,r.elevation.component_id,r.elevation.manifest.byte_size,r.elevation.manifest.sha256,r.elevation.tiles.map(t=>[t.path,t.byte_size,t.sha256])]);}
