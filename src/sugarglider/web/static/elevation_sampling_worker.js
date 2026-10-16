import { sampleElevationGeometry } from "./elevation_sampling.js";
self.onmessage = async ({data}) => {
  try { self.postMessage({result: await sampleElevationGeometry(data.geometry, data.distance)}); }
  catch(error) { self.postMessage({error: error.message}); }
};
