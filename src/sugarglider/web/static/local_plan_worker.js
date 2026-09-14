import { publishLocalPlan } from "./local_plan_publisher.js";

let busy = false;
self.onmessage = async ({ data }) => {
  if (busy) { self.postMessage({ id: data?.id, type: "error", code: "local_publication_busy" }); return; }
  busy = true;
  try {
    if (data?.type !== "publish") throw new TypeError("Invalid local publication operation.");
    const result = await publishLocalPlan(data.request, data.search, data.regionalReference);
    self.postMessage({ id: data.id, type: "result", result });
  } catch (error) {
    self.postMessage({ id: data?.id, type: "error", code: /^[a-z_]{1,80}$/.test(error.code) ? error.code : "local_publication_failed" });
  } finally { busy = false; }
};
