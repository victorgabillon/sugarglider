import { initializeAdventureDialog } from '../../src/sugarglider/web/static/adventure_dialog.js';
import { setLanguage } from '../../src/sugarglider/web/static/i18n.js';
import { frame, accounts } from './adventure_ui_harness.js';
import { setup } from './adventure_controller_harness.js';
const assert = (ok, message) => { if (!ok) throw Error(message); };
const equal = (a,b,message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
async function until(check) { for(let i=0;i<500;i++){if(check()) return; await new Promise(r=>setTimeout(r,10));} throw Error('Pin context did not settle'); }
export async function runPinContextHarness() {
  const cases=[];
  for(const language of ['fr','en']) for(const count of [0,1,16,17]) for(const include of [false,true]) {
    const r=await setup(), f=await frame(360,640,2), sent=[], reads=[];
    await setLanguage(language,{persist:false,document:f.doc});
    const pin = index => ({kind:index===0?'start':index===count-1?'end':'waypoint',id:`private-pin-${index}`,name:`Private ${index}`,order:index+1,
      coordinate:{name:`Private ${index}`,lat:48.111111+index*.00001,lon:1.222222+index*.00001}});
    const pins=Array.from({length:count},(_,i)=>pin(i));
    const context={...r.input.context, contextualPins:pins, hardWaypoints:pins.filter(p=>p.kind==='waypoint'),
      start:pins[0]?.coordinate??null,end:count>1?pins.at(-1).coordinate:null,
      localPlaces:[{osm_id:'private-derived-poi',location:{lat:48.765432,lon:1.987654}}],
      geometry:[[1.54321,48.54321]],gps:{lat:48.9999,lon:1.9999},suggested_profile:'trail_run'};
    const original=JSON.stringify(context);
    const model=accounts({...r.model,infer:async input=>{sent.push(input);throw Object.assign(Error('network'),{code:'network'});}});
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById('plan-with-ai'),planner:r.planner,model,
      speech:{cancel(){}},elevation:{clear(){}},getContext:async options=>{reads.push(options??{});return context;},onChooseStart(){},onChooseEnd(){},
      onResult(){throw Error('Failed inference must not publish');}});
    try {
      await dialog.open();
      assert(!f.byId('include-pins').checked&&!f.byId('keep-start').checked&&!f.byId('keep-end').checked&&!f.byId('keep-waypoints').checked,'every new request excludes pins and constraints');
      assert(reads.every(x=>!x.includeMapPins),'opening cannot request manual pins');
      equal(f.byId('include-pins').parentElement.textContent.trim(),language==='fr'?'Inclure les points actuels de la carte':'Include current map pins','localized visible opt-in');
      f.byId('text').value='A new adventure in the selected region'; f.byId('text').dispatchEvent(new Event('input'));
      await until(()=>!f.byId('generate').disabled);
      if(include){f.byId('include-pins').click();await until(()=>count>16?Boolean(f.byId('error').textContent):!f.byId('generate').disabled);}
      assert(!sent.length&&!r.nativeCalls.length,'opt-in never infers or routes');
      if(include&&count>16){assert(f.byId('generate').disabled,'oversized snapshot cannot silently truncate');continue;}
      const captured=structuredClone(pins);
      // Editing after opt-in cannot change the single captured snapshot.
      if(include&&pins.length) pins[0].coordinate.lat=49.999999;
      f.byId('generate').click();await until(()=>sent.length===1&&!dialog.busy());
      const payload=JSON.parse(sent[0].input).planning_context;
      equal(payload.contextual_pins,include?captured:[],'exact contextual snapshot names IDs coordinates and order');
      equal(payload.exact_points,[],'including pins alone never imposes exact waypoints');
      assert(payload.start===null&&payload.end===null&&!payload.start_is_fixed&&!payload.end_is_fixed,'including pins alone never fixes endpoints');
      equal(payload.local_places,[],'no automatically derived geographic inventory');
      assert(!sent[0].input.includes('private-derived-poi')&&!sent[0].input.includes('48.9999')&&!sent[0].input.includes('48.54321'),'GPS geometry and nearby features absent');
      if(!include){assert(!sent[0].input.includes('48.111111')&&!sent[0].input.includes('1.222222')&&!sent[0].input.includes('private-pin'),'unchecked payload contains no inherited pin coordinates or identities');equal(JSON.stringify(context),original,'manual context untouched');}
      assert(r.nativeCalls.length===0,'failure never routes');
      f.byId('close').click();await dialog.open();
      assert(!f.byId('include-pins').checked&&!f.byId('keep-waypoints').checked,'reopen resets consent');
      assert(!f.byId('pin-status').textContent.includes('Private'),'reopen never displays old snapshot pins');
      cases.push(`payload_${language}_${count}_${include}`);
    } finally {dialog.clear();r.planner.invalidate();f.element.remove();}
  }
  {
    const r=await setup(),f=await frame();let sent;
    const waypoints=Array.from({length:14},(_,i)=>({id:`required-${i}`,name:`Required ${i}`,coordinate:{name:`Required ${i}`,lat:.006+i*.0001,lon:.005}}));
    const context={...r.input.context,hardWaypoints:waypoints,contextualPins:waypoints.map((p,i)=>({...p,kind:'waypoint',order:i+1}))};
    const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById('plan-with-ai'),planner:r.planner,
      model:accounts({...r.model,infer:async input=>{sent=JSON.parse(input.input);throw Error('synthetic failure');}}),speech:{cancel(){}},elevation:{clear(){}},getContext:async()=>context,
      onChooseStart(){},onChooseEnd(){},onResult(){}});
    try {await dialog.open();f.byId('text').value='Explicitly keep my required stops';f.byId('text').dispatchEvent(new Event('input'));await until(()=>!f.byId('generate').disabled);
      f.byId('include-pins').click();await until(()=>!f.byId('generate').disabled);
      f.byId('keep-start').click();f.byId('keep-end').click();f.byId('keep-waypoints').click();f.byId('generate').click();await until(()=>sent&&!dialog.busy());
      equal(sent.planning_context.exact_points,waypoints,'all fourteen exact constraints retain identity and order after explicit selection');
      equal(sent.planning_context.start,context.start,'explicit fixed Start');equal(sent.planning_context.end,context.end,'explicit fixed End');
      cases.push('separate_explicit_endpoint_and_fourteen_waypoint_constraints');
    }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  }
  // Explicit map selection works without disclosing any other manual pin.
  const r=await setup(),f=await frame();let sent;
  const dialog=initializeAdventureDialog({root:f.root,launcher:f.doc.getElementById('plan-with-ai'),planner:r.planner,
    model:accounts({...r.model,infer:async input=>{sent=JSON.parse(input.input);throw Error('synthetic failure');}}),speech:{cancel(){}},elevation:{clear(){}},getContext:async()=>r.input.context,
    onChooseStart(){},onChooseEnd(){},onResult(){}});
  try {await dialog.open(undefined,{selectedEndpoint:{kind:'start',coordinate:{name:'Explicit new location',lat:.004,lon:.004}}});
    f.byId('text').value='Start at my explicitly chosen location';f.byId('text').dispatchEvent(new Event('input'));await until(()=>!f.byId('generate').disabled);
    f.byId('generate').click();await until(()=>sent&&!dialog.busy());
    assert(sent.planning_context.start.name==='Explicit new location'&&sent.planning_context.end===null&&sent.planning_context.contextual_pins.length===0,'only the explicitly chosen endpoint is fixed and disclosed');
    cases.push('explicit_map_choice_without_pin_consent');
  }finally{dialog.clear();r.planner.invalidate();f.element.remove();}
  return cases;
}
