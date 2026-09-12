import { exportCanonicalCandidate, LocalGpxExportError } from "./local_gpx_export.js";

self.onmessage = ({ data }) => {
  if (!Number.isSafeInteger(data?.id) || data.id < 1 || data.type !== "export") return;
  try {
    const { blob, filename } = exportCanonicalCandidate(data.candidate);
    self.postMessage({ type: "result", id: data.id, blob, filename });
  } catch (error) {
    self.postMessage({ type: "error", id: data.id,
      code: error instanceof LocalGpxExportError ? error.code : "invalid_export_geometry" });
  }
};
self.postMessage({ type: "ready" });
