import {parseRegionalManifest, regionalBuildIdentity} from '../../src/sugarglider/web/static/regional_manifest.js';
import {createRegionVersionStore} from '../../src/sugarglider/web/static/region_versions.js';
import {selectCommittedRegion} from '../../src/sugarglider/web/static/regional_planning.js';

function assert(value, message) { if (!value) throw new Error(message); }
async function rejects(action, code) {
  const error=await action().then(()=>null,error=>error);
  assert(error && (!code || error.code===code),`Expected ${code}, got ${error?.code}`);
}
async function write(directory,name,value){const stream=await(await directory.getFileHandle(name,{create:true})).createWritable();await stream.write(JSON.stringify(value));await stream.close();}
export async function runV2RegionsHarness(){
 const fixture=(await(await fetch('../fixtures/pr40_regional_data.json')).json()).manifest;
 const cases=[];
 for(const kind of ['map','routing','pois','nature','elevation']){
  const changed=structuredClone(fixture);delete changed.components[kind];
  changed.build_id=await regionalBuildIdentity(changed);
  await rejects(()=>parseRegionalManifest(JSON.stringify(changed)));
 }
 cases.push('exactly_five_components_no_missing_elevation');
 for(const mutate of [m=>m.components.elevation.files.pop(),m=>m.components.elevation.files[1].path='../escape',
   m=>m.components.elevation.files[1].format='raw-height',m=>m.components.elevation.files[1].byte_size=26_982_979,
   m=>m.publication_allowed=0,m=>m.publication_allowed=true]){
  const changed=structuredClone(fixture);mutate(changed);changed.build_id=await regionalBuildIdentity(changed);
  await rejects(()=>parseRegionalManifest(JSON.stringify(changed)));
 }
 cases.push('strict_elevation_layout_sizes_formats_and_private_publication');
 const vectors=await(await fetch('../fixtures/v2_manifest_identity_vectors.json')).json();
 for(const vector of vectors) assert((await parseRegionalManifest(JSON.stringify(vector.manifest))).build_id===vector.manifest.build_id,vector.name);
 cases.push('python_js_float_unicode_and_southern_tile_identity_vectors');
 const origin=await navigator.storage.getDirectory(),name=`pr90-${crypto.randomUUID()}`;
 const root=await origin.getDirectoryHandle(name,{create:true});
 try{
  const regions=await root.getDirectoryHandle('sugarglider-installed-regions',{create:true});
  const region=await regions.getDirectoryHandle(fixture.region_id,{create:true});
  const oldId='b'.repeat(64),oldDirectory=await region.getDirectoryHandle(oldId,{create:true});
  const old=structuredClone(fixture);old.schema_version=1;old.build_id=oldId;delete old.components.elevation;delete old.publication_allowed;
  await write(oldDirectory,'manifest.json',old);await write(region,'active.json',{schema_version:1,build_id:oldId});
  const store=createRegionVersionStore({storage:{getDirectory:async()=>root},locks:navigator.locks});
  const unavailable=(await store.list())[0];
  assert(unavailable.status==='unavailable' && unavailable.code==='regional_v2_install_required','V1 is explicit');
  await rejects(async()=>selectCommittedRegion([unavailable],fixture.region_id),'regional_v2_install_required');
  const oldBytes=await(await(await oldDirectory.getFileHandle('manifest.json')).getFile()).text();
  const ticket=await store.stage(JSON.stringify(fixture));
  await rejects(()=>store.activate(ticket,{verifyComponent:async kind=>kind!=='elevation'}),'regional_components_unavailable');
  assert(JSON.parse(await(await(await region.getFileHandle('active.json')).getFile()).text()).build_id===oldId,'missing DEM cannot activate');
  const checked=[];await store.activate(ticket,{verifyComponent:async kind=>{checked.push(kind);return true;}});
  assert(checked.join(',')==='map,routing,pois,nature,elevation','all five checked');
  assert((await store.read(fixture.region_id)).build_id===fixture.build_id,'new V2 install committed');
  assert(await(await(await oldDirectory.getFileHandle('manifest.json')).getFile()).text()===oldBytes,'old data retained unchanged');
  cases.push('old_metadata_requires_v2_and_is_retained_during_explicit_new_install');
  cases.push('missing_or_failed_elevation_never_commits_ready');
 }finally{await origin.removeEntry(name,{recursive:true});}
 return cases;
}
