import { createCalculationOperations } from '../../src/sugarglider/web/static/calculation_operation.js';
import { setup } from './adventure_controller_harness.js';
import { exportCanonicalCandidate } from '../../src/sugarglider/web/static/local_gpx_export.js';
const assert=(ok,message)=>{if(!ok)throw Error(message);};
async function until(check){for(let i=0;i<600;i++){if(check())return;await new Promise(r=>setTimeout(r,5));}throw Error('Operation did not settle');}
function fakeNative(){
  const calls=[];let subscriber,receipt=null,active=null;
  return {calls,get receipt(){return receipt;},transport:{nativeAvailable:true,subscribeUnsolicited(fn){subscriber=fn;return()=>{subscriber=null;};},
    request:async(type,fields,options)=>{
      calls.push({type,...structuredClone(fields)});
      if(type==='calculation_begin'){active=fields.operation_id;receipt={schema_version:1,operation_id:active,kind:fields.kind,prompt:fields.prompt,state:'interrupted'};}
      const state=type==='calculation_begin'?'running':fields.state??'idle';
      if(type==='calculation_finish'){active=null;if(['completed','cancelled'].includes(state))receipt=null;}
      return options.parseReply(JSON.stringify({schema_version:1,request_id:'synthetic',type:'calculation_result',operation_id:fields.operation_id??null,state,recovery:type==='calculation_recovery'?receipt:null}));
    }},cancel(id=active){subscriber?.(JSON.stringify({schema_version:1,request_id:'native-synthetic',type:'calculation_result',operation_id:id,state:'cancelled',recovery:null}));}}
}
async function workflow(){
  const r=await setup(),native=fakeNative(),lifecycle=new EventTarget(),operations=createCalculationOperations({transport:native.transport,lifecycleTarget:lifecycle});
  const infer=r.model.infer,route=r.region.bridge.route;let phase=null,release=null,modelCalls=0,routed=false;
  const hold=stage=>new Promise(resolve=>{phase=stage;release=resolve;});
  r.model.infer=async(input,signal)=>{modelCalls++;await hold(modelCalls===1?'initial':'refinement');return infer(input,signal);};
  r.region.bridge.route=async input=>{if(!routed){routed=true;await hold('routing');}return route(input);};
  const promise=operations.run({kind:'adventure',prompt:r.input.prompt},(signal,operationId)=>r.controller.run({...r.input,operationId},signal));
  // Attach rejection immediately, including cancellation before the caller awaits it.
  const outcome=promise.then(output=>({output}),error=>({error}));
  return{r,native,lifecycle,operations,outcome,get phase(){return phase;},get modelCalls(){return modelCalls;},release:()=>{const finish=release;release=null;phase=null;finish?.();},
    close(){operations.close();r.controller.cancel();r.planner.invalidate();}};
}
export async function runCalculationHarness(){
  const cases=[];
  for(const transition of ['foreground','home_transition','return_while_background_routing','lock_unlock','return_during_inference','return_after_completion']){
    const w=await workflow();try{
      await until(()=>w.phase==='initial');const id=w.operations.activeId();
      if(transition!=='foreground'){w.lifecycle.dispatchEvent(new Event('blur'));w.lifecycle.dispatchEvent(new Event('visibilitychange'));}
      if(transition==='return_during_inference')w.lifecycle.dispatchEvent(new Event('focus'));
      assert(w.modelCalls===1&&w.operations.activeId()===id,'background and return retain the same initial request');
      w.release();await until(()=>w.phase==='routing');
      assert(w.operations.activeId()===id,'native routing retains the same operation');
      w.release();await until(()=>w.phase==='refinement');
      assert(w.modelCalls===2&&w.operations.activeId()===id,'second inference remains inside the same lease while backgrounded');
      w.release();const {output,error}=await w.outcome;assert(!error&&output?.chosen.result.candidates.length,'full pipeline completes');
      const before=w.r.nativeCalls.length,models=w.modelCalls;
      const candidate=output.chosen.result.candidates[0];const xml=await exportCanonicalCandidate(candidate).blob.text();
      w.lifecycle.dispatchEvent(new Event('focus'));w.lifecycle.dispatchEvent(new Event('visibilitychange'));
      assert(xml===await exportCanonicalCandidate(candidate).blob.text()&&before===w.r.nativeCalls.length&&models===w.modelCalls,'return and GPX never rerun model or native work');
      assert(w.r.calls.every(c=>c.operation_id===id),'both exact outgoing model requests carry the immutable identity');
      assert(w.native.calls.filter(c=>c.type==='calculation_begin').length===1&&w.native.calls.at(-1).state==='completed','one begin and one completed operation');
      assert(output.routing_diagnostics.budget.total_used<=16&&output.routing_diagnostics.cache.backend_call_count===before,'original native budgets and cache facts retained');
      cases.push(transition+'_full_pipeline');
    }finally{w.close();}
  }
  for(const phase of ['initial','routing','refinement']){
    const w=await workflow();try{
      await until(()=>w.phase==='initial');if(phase!=='initial'){w.release();await until(()=>w.phase==='routing');}
      if(phase==='refinement'){w.release();await until(()=>w.phase==='refinement');}
      const id=w.operations.activeId();w.native.cancel('0'.repeat(32));assert(w.operations.activeId()===id,'stale notification cannot cancel current operation');
      w.native.cancel();w.release();const outcome=await w.outcome;assert(outcome.error?.name==='AbortError'&&!outcome.output,'cancelled late response never publishes');
      assert(w.native.calls.at(-1).state==='cancelled','cancel finishes native lease');cases.push('notification_cancel_'+phase);
    }finally{w.close();}
  }
  {
    const w=await workflow();try{
      await until(()=>w.phase==='initial');const original=w.r.input.prompt;
      w.lifecycle.dispatchEvent(new Event('pagehide'));w.release();await w.outcome;
      assert(w.native.calls.at(-1).state==='interrupted'&&w.native.receipt.prompt===original,'page destruction preserves only original text and identity for explicit retry');
      const restored=createCalculationOperations({transport:w.native.transport,lifecycleTarget:new EventTarget()});
      const before=w.modelCalls;const receipt=await restored.recovery();assert(receipt.prompt===original&&w.modelCalls===before,'recovery never repeats billable inference');restored.close();
      cases.push('recreation_process_death_receipt_is_not_an_executable_job');
    }finally{w.close();}
  }
  for(const kind of ['failed','notifications_required']){
    const native=fakeNative();let executed=false;
    const transport=kind==='failed'?native.transport:{...native.transport,request:async(type,fields,options)=>type==='calculation_begin'
      ?options.parseReply(JSON.stringify({schema_version:1,request_id:'x',type:'calculation_result',operation_id:fields.operation_id,state:'notifications_required',recovery:null}))
      :native.transport.request(type,fields,options)};
    const operations=createCalculationOperations({transport,lifecycleTarget:null});
    const error=await operations.run({kind:'offline'},async()=>{executed=true;throw Error('synthetic network loss');}).catch(e=>e);
    assert(error instanceof Error&&(kind==='failed'?executed:!executed),'failure or permission denial cannot leave work running');
    assert(native.calls.at(-1).state==='failed','failed work releases lease');operations.close();cases.push(kind+'_releases_operation');
  }
  return cases;
}
