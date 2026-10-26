import { encodeAdventureSnapshot, decodeAdventureSnapshot } from "./adventure_snapshot_validation.js";

// One bounded operation per disposable worker. No network, storage or native IO.
self.onmessage = async ({ data }) => {
  try {
    const value = data?.type === "encode" ? await encodeAdventureSnapshot(data.value)
      : data?.type === "decode" ? await decodeAdventureSnapshot(data.value) : null;
    if (!value) throw Error("invalid_adventure_snapshot");
    self.postMessage({ type: "result", value });
  } catch { self.postMessage({ type: "error" }); }
};
