import { validateLocalRegionDocuments, createLocalRegionData } from "../../src/sugarglider/web/static/local_region_data.js";
import { createRegionInstallerClient } from "../../src/sugarglider/web/static/local_region_client.js";

const assert = (value, message) => { if (!value) throw Error(message); };
async function rejects(promise, code) {
  try { await promise; } catch (error) { assert(error.code === code, "expected exact failure"); return; }
  throw Error("Expected rejection");
}

export async function run() {
  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const original = JSON.stringify(fixture);
  validateLocalRegionDocuments(fixture.manifest, fixture);
  assert(JSON.stringify(fixture) === original && !Object.isFrozen(fixture.nature), "validation preserves input without freezing a discarded document");
  const result = createLocalRegionData(fixture.manifest, fixture).analyzeNature(fixture.route);
  assert(Math.abs(result.nature_score - fixture.expected.nature_score) < 1e-6, "runtime analysis retains the Python golden result");
  validateLocalRegionDocuments(fixture.manifest);
  validateLocalRegionDocuments(fixture.manifest, { pois: fixture.pois });
  validateLocalRegionDocuments(fixture.manifest, { nature: fixture.nature });

  const instances = [];
  const installer = createRegionInstallerClient({ createClient: () => {
    const client = { closed: 0, cancelled: 0,
      installVersion: (...args) => { client.args = args; return new Promise((resolve, reject) => { client.resolve = resolve; client.reject = reject; }); },
      cancelInstall: () => { client.cancelled += 1; }, close: () => { client.closed += 1; } };
    instances.push(client); return client;
  } });
  installer.cancelInstall();
  const manifest = {}, directory = {};
  const first = installer.installVersion("https://fixture.invalid/manifest.json", manifest, directory);
  assert(instances[0].args[1] === manifest && instances[0].args[2] === directory, "exact manifest and directory ownership");
  await rejects(installer.installVersion(), "regional_operation_busy");
  installer.cancelInstall();
  assert(instances[0].closed === 0 && instances[0].cancelled === 1, "Cancel waits for the worker's definite write outcome");
  instances[0].resolve(manifest);
  assert(await first === manifest && instances[0].closed === 1, "successful commit wins and closes the installer worker exactly once");
  installer.cancelInstall();
  assert(instances[0].cancelled === 1, "idle cancel cannot reach a stale worker");
  for (const code of ["regional_install_cancelled", "regional_checksum_mismatch", "regional_worker_unavailable"]) {
    const operation = installer.installVersion();
    const client = instances.at(-1);
    client.reject(Object.assign(Error(code), { code }));
    await rejects(operation, code);
    assert(client.closed === 1, "failure releases the owned worker");
  }
  const retry = installer.installVersion();
  assert(instances.length === 5 && instances.slice(0, -1).every((client) => client.closed === 1), "retry uses fresh worker after all outcomes");
  instances.at(-1).resolve("ready");
  assert(await retry === "ready" && instances.at(-1).closed === 1, "retry completes and closes");
  return ["validation_does_not_construct_or_freeze_a_discarded_session", "runtime_nature_golden_unchanged", "missing_optional_documents_stay_optional",
    "installer_preserves_exact_ownership_and_serialization", "cancellation_drains_before_worker_closure", "success_closes_once_and_wins_late_cancel",
    "all_failure_paths_close_worker", "retry_owns_fresh_worker"];
}
