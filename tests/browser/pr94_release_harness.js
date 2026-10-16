import { appendTerrainAttribution } from '../../src/sugarglider/web/static/terrain_attribution.js';
const assert=(value,message)=>{if(!value)throw Error(message);};
export async function run(){
 const fixture=await(await fetch('../fixtures/pr94_terrain_attribution.json')).json();
 const parent=document.createElement('div');
 assert(!appendTerrainAttribution(parent,null)&&!parent.children.length,'unknown data never receives a fabricated attribution');
 const manifest={components:{elevation:{files:[{},...fixture.derived_sha256.map(sha256=>({sha256}))]}}};
 assert(appendTerrainAttribution(parent,manifest),'exact known DEM identified');
 assert(parent.querySelector('summary').textContent==='Elevation source and license','discoverable credit');
 assert(parent.textContent.includes('Surface model')&&parent.textContent.includes('EGM2008 to EGM96'),'surface and transformation explicit');
 assert(parent.textContent.includes(fixture.attribution)&&parent.textContent.includes(fixture.disclaimer),'full required notices');
 assert(parent.querySelector('a').href===fixture.license_url,'official license');
 const altered=structuredClone(manifest);altered.components.elevation.files[1].sha256='f'.repeat(64);
 assert(!appendTerrainAttribution(document.createElement('div'),altered),'another DEM never receives Copernicus credit');
 altered.components.elevation.files.pop();assert(!appendTerrainAttribution(document.createElement('div'),altered),'incomplete source cannot match');
 return ['exact_dataset_identity','missing_and_mismatched_sources','discoverable_complete_attribution','surface_datum_and_official_license'];
}
