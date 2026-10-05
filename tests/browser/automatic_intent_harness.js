import { state, saveActivePoints, assignRouteEndpoint, setRouteTopology, currentPlanRequest, generationAvailability, switchPlanningMode } from '../../src/sugarglider/web/static/state.js';
import { appendMapIntent, reconcileAutomaticIntent, undoPointEdit, clearPointUndo, pointUndoLabel, routeIntentPresentation } from '../../src/sugarglider/web/static/automatic_intent.js';
const assert = (ok, message) => { if (!ok) throw Error(message); };
const same = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
const initial = structuredClone(state);
const A = {lat:48.798432,lon:2.122484}, B = {lat:48.790122,lon:2.118049}, C = {lat:48.786583,lon:2.105706};
const endpoints = () => state.planningMode === 'auto_tour' ? state.autoTour : state.waypointEndpoints;
function assign(kind, point) {
  saveActivePoints(); assignRouteEndpoint(endpoints(), kind, point);
  if (state.planningMode === 'auto_tour' && kind === 'start') state.points = [point, ...state.autoTour.hardPoints].filter(Boolean);
}
function reset() { Object.assign(state, structuredClone(initial)); state.routingProfile='trail_run'; state.options.targetDistanceKm=10; clearPointUndo(); }
const tap = p => appendMapIntent(p, assign);
const ready = () => generationAvailability({planningMode:state.planningMode,routeTopology:endpoints().routeTopology,start:endpoints().start,end:endpoints().end,mandatoryPointCount:state.points.length,pointValidationMessage:'',profileAvailable:true});
export function runAutomaticIntentHarness() {
 const cases=[];
 try {
  reset(); assert(!ready().enabled,'no Start'); tap(A); assert(ready().enabled,'Start alone enables'); assert(state.planningMode==='auto_tour','Start means discovery'); same(endpoints().start,{name:'Hard start',...A},'exact Start'); assert(routeIntentPresentation().title==='10 km loop from Start','visible discovery intent'); const auto=currentPlanRequest(); cases.push('A_start_infers_auto_and_enables');
  tap(B); assert(state.planningMode==='waypoint_route','stop infers connect'); same(endpoints().start,auto.start,'Start transferred exactly'); assert(state.autoTour.start===null&&state.autoTour.hardPoints.length===0,'no duplicate inactive geometry'); tap(C); same(state.points.map(({lat,lon})=>({lat,lon})),[B,C],'continuous taps preserve order'); assert(ready().enabled,'connect ready'); assert(routeIntentPresentation().title==='Start → 1 → 2 → Start','visible connect intent'); cases.push('B_continuous_taps_transfer_single_authority');
  state.points.pop(); reconcileAutomaticIntent(); state.points.pop(); reconcileAutomaticIntent(); same(currentPlanRequest(),auto,'last stop removal restores exact Auto request'); assert(state.waypointPoints.length===0&&state.waypointEndpoints.start===null,'no duplicate connect geometry'); cases.push('C_last_stop_preserves_start_and_auto_options');
  assign('start',C); reconcileAutomaticIntent(); same(endpoints().start,C,'move Start keeps exact replacement'); assert(state.points.length===1,'moving Start creates no stop'); cases.push('D_move_start_no_extra_stop');
  reset(); tap(A); setRouteTopology(endpoints(),'point_to_point'); assert(!ready().enabled,'missing End'); tap(B); assert(state.planningMode==='waypoint_route'&&state.points.length===0,'explicit End infers connect'); same(endpoints().end,{name:'Hard end',...B},'separate hard End'); tap(C); state.points[0].constraintStrength='best_effort'; state.points[0].maximumBestEffortDistanceM=900; const stop=structuredClone(state.points[0]); setRouteTopology(endpoints(),'loop'); reconcileAutomaticIntent(); same(state.points[0],stop,'topology never strengthens last stop'); assert(endpoints().end===null,'loop has no explicit End'); cases.push('F_open_end_not_soft_stop_topology_roundtrip');
  for(const priority of ['flexible','balanced','strict']) for(const maximum of [null,14]) {
   reset(); state.routingProfile='hike'; Object.assign(state.options,{targetDistanceKm:7.5,toleranceKm:1.3,maximumDistanceKm:maximum,distancePriority:priority,seed:42,candidateCount:2,waypointOrder:'optimize'}); tap(A); const before=currentPlanRequest(); tap(B); const after=currentPlanRequest(); same(after.distance_objective,before.distance_objective,'distance objective exact'); assert(after.routing_profile==='hike'&&after.seed===42&&after.candidate_count===2&&after.waypoint_order==='optimize','common options survive'); same(after.preferences,{nature:'off',path_selection:'shortest',loop_geometry:'off'},'native compatible Connect preferences'); state.points=[]; reconcileAutomaticIntent(); same(currentPlanRequest(),before,'full auto roundtrip'); cases.push(`G_options_${priority}_${maximum}`);
  }
  reset(); tap(A); const expectedAuto=currentPlanRequest(); tap(B); const automatic=currentPlanRequest(); reset(); state.planningStrategy='auto_tour'; assign('start',{name:'Hard start',...A}); same(currentPlanRequest(),expectedAuto,'pre-change manual Auto equivalent'); switchPlanningMode('waypoint_route'); state.options.targetDistanceKm=10; assign('start',{name:'Hard start',...A}); state.points=[{name:'Point 1',...B,originalIndex:0}]; same(currentPlanRequest(),automatic,'manual Connect equivalent'); cases.push('H_exact_manual_canonical_equivalence');
  reset(); tap(A); tap(B);  assert(pointUndoLabel()==='Stop added','Undo named'); assert(undoPointEdit(),'Undo works'); same(currentPlanRequest(),expectedAuto,'Undo transition exact'); assert(!undoPointEdit(),'single undo only'); tap(B); state.savedRouteSnapshotDisplay=true; state.savedRouteSnapshot={}; assert(!undoPointEdit(),'snapshot cannot Undo'); state.savedRouteSnapshotDisplay=false; state.request.status='running'; assert(!undoPointEdit(),'running cannot Undo'); state.request.status='idle'; clearPointUndo(); assert(!undoPointEdit(),'unrelated edit clears undo'); cases.push('undo_atomic_transition_single_level_and_guards');
  reset(); tap(A); state.planningStrategy='auto_tour'; tap(B); assert(state.planningMode==='auto_tour','explicit Auto keeps hard anchor'); const explicit=currentPlanRequest(); reconcileAutomaticIntent(); same(currentPlanRequest(),explicit,'explicit canonical kind preserved'); cases.push('imported_or_manual_auto_anchors_do_not_reinterpret');
  reset(); tap(A); state.autoTour.preferredPoiIds=['node/123']; reconcileAutomaticIntent(); assert(state.planningStrategy==='auto_tour','discovery-only action pins explicit strategy'); assert(state.autoTour.preferredPoiIds[0]==='node/123','preference preserved'); cases.push('discovery_intent_never_discarded');
  reset(); tap(A); tap(B); state.planningStrategy='waypoint_route';
  state.autoTour.start={...C}; state.autoTour.requestedPlaces=[{name:'parked discovery'}]; state.autoTour.preferredPoiIds=['node/old'];
  Object.assign(state.points[0],{constraintStrength:'approach',accessSearchRadiusM:333,maximumBestEffortDistanceM:777,approachOverride:C,id:'stable-id'});
  const rich=currentPlanRequest(); state.planningStrategy='automatic'; reconcileAutomaticIntent(); same(currentPlanRequest(),rich,'soft waypoint metadata retained');
  state.points=[]; reconcileAutomaticIntent(); assert(state.autoTour.requestedPlaces.length===0&&state.autoTour.preferredPoiIds.length===0,'inactive discovery never resurrected');
  cases.push('explicit_to_automatic_retains_soft_metadata_discards_inactive_geometry');
  reset(); state.planningMode='waypoint_route'; state.waypointEndpoints.start={name:'Imported start',...A}; state.options={...state.waypointOptions}; state.points=[];
  reconcileAutomaticIntent(); const firstAuto=currentPlanRequest(); assert(firstAuto.kind==='auto_tour'&&firstAuto.preferences.path_selection==='shortest'&&firstAuto.preferences.nature==='off','import-first fallback retains valid options even without prior Auto draft');
  cases.push('import_first_return_to_auto_has_complete_preferences');
  reset(); tap(A); state.config={max_required_points:2}; tap(B); tap(C); let rejected=false; try{tap(A)}catch{rejected=true} assert(rejected&&state.points.length===2,'stop limit deterministic'); cases.push('maximum_rejects_without_mutating');
 } finally {Object.assign(state,initial);clearPointUndo()}
 return cases;
}
