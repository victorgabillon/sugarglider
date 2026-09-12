import { createRegionVersionStore } from "../../src/sugarglider/web/static/region_versions.js";
import { regionalBuildIdentity } from "../../src/sugarglider/web/static/regional_manifest.js";

export async function runPr42RegionVersionsHarness() {
  const fixture = (await (await fetch("../fixtures/pr40_regional_data.json")).json()).manifest;
  const cases = [], memory = memoryStorage(), store = createRegionVersionStore(memory);
  const original = await proposal(fixture, "Original"), updated = await proposal(fixture, "Updated");
  const ticket = await store.stage(JSON.stringify(original));
  equal(await store.read(original.region_id), null, "staging is not active");
  equal((await store.list())[0].inactive_build_ids, [original.build_id], "incomplete version is explicit");
  assert(Object.isFrozen(ticket) && Object.isFrozen(ticket.manifest), "immutable ticket");
  cases.push("staging_is_inactive_and_ticket_is_immutable");

  const checked = [];
  await store.activate(ticket, { verifyComponent: async (kind) => { checked.push(kind); return true; } });
  equal(checked, ["map", "routing", "pois", "nature"], "all components checked before commit");
  equal((await createRegionVersionStore(memory).read(original.region_id)).build_id, original.build_id, "restart retains commit");
  cases.push("four_component_commit_and_restart");

  const next = await store.stage(JSON.stringify(updated));
  await rejects(() => store.activate(next, { verifyComponent: async (kind) => kind !== "nature" }), "regional_components_unavailable");
  equal((await store.read(original.region_id)).build_id, original.build_id, "failed component preserves old commit");
  cases.push("component_failure_preserves_old_version");
  const abort = new AbortController();
  await rejects(() => store.activate(next, { signal: abort.signal, verifyComponent: async (kind) => {
    if (kind === "nature") abort.abort(); return true;
  } }), "AbortError");
  equal((await store.read(original.region_id)).build_id, original.build_id, "cancel before commit preserves old version");
  cases.push("cancel_after_validation_preserves_old_version");

  memory.failClose = "before";
  await rejects(() => store.activate(next, { verifyComponent: async () => true }), "regional_write_failed");
  equal((await store.read(original.region_id)).build_id, original.build_id, "definite close failure retains old pointer");
  memory.failClose = null;
  cases.push("definite_commit_failure_preserves_old_version");
  memory.failClose = "after";
  await store.activate(next, { verifyComponent: async () => true });
  memory.failClose = null;
  equal((await store.read(original.region_id)).build_id, updated.build_id, "observed new pointer confirms ambiguous close");
  cases.push("observed_commit_wins_over_lost_close_result");
  await rejects(() => store.activate(ticket, { verifyComponent: async () => true }), "regional_version_changed");
  cases.push("stale_ticket_cannot_overwrite_new_commit");
  await rejects(() => store.removeInactiveVersion(updated.region_id, updated.build_id), "regional_version_in_use");
  await rejects(() => store.withStagedVersion(next, () => {}), "regional_version_in_use");
  cases.push("active_version_cannot_be_removed_or_opened_for_staging");

  await store.removeInactiveVersion(original.region_id, original.build_id);
  const third = await store.stage(JSON.stringify(await proposal(fixture, "Third")));
  memory.failClose = "unreadable";
  await rejects(() => store.activate(third, { verifyComponent: async () => true }), "regional_commit_uncertain");
  memory.failClose = null;
  equal((await store.list())[0].inactive_build_ids, [updated.build_id], "uncertain commit retains previous version");
  cases.push("unreadable_commit_outcome_retains_versions");

  const region = await memory.root.getDirectoryHandle("sugarglider-installed-regions").then((root) => root.getDirectoryHandle(original.region_id));
  const active = await region.getFileHandle("active.json");
  await write(active, '{"schema_version":1,"build_id":"../escape"}');
  await rejects(() => store.read(original.region_id), "regional_active_record_invalid");
  equal((await store.list())[0].status, "unavailable", "corrupt pointer never guesses an old version");
  cases.push("corrupt_active_record_is_explicit_without_fallback");
  await store.recoverCorruptRecord(original.region_id);
  equal(await store.read(original.region_id), null, "recovery clears availability without choosing old data");
  equal((await store.list())[0].inactive_build_ids.length, 2, "recovery retains both versions");
  const recovered = await store.stage(JSON.stringify(third.manifest));
  await store.activate(recovered, { verifyComponent: async () => true });
  await rejects(() => store.recoverCorruptRecord(original.region_id), "regional_recovery_not_needed");
  cases.push("explicit_corrupt_pointer_recovery_retains_data_and_rechecks_components");
  await rejects(() => store.deactivate(original.region_id, updated.build_id), "regional_version_changed");
  await store.deactivate(original.region_id, third.manifest.build_id);
  equal(await store.read(original.region_id), null, "deactivation first removes availability");
  await store.removeInactiveVersion(original.region_id, third.manifest.build_id);
  await store.removeInactiveVersion(original.region_id, updated.build_id);
  await store.removeEmptyRegion(original.region_id);
  equal(await store.list(), [], "explicit cleanup frees region slot");
  cases.push("deactivation_cas_and_owned_cleanup");

  const bounded = createRegionVersionStore(memoryStorage());
  for (let i = 0; i < 8; i++) await bounded.stage(JSON.stringify(await proposal(fixture, `Region ${i}`, `region-${i}`)));
  await rejects(async () => bounded.stage(JSON.stringify(await proposal(fixture, "Ninth", "region-8"))), "regional_storage_limit");
  await bounded.stage(JSON.stringify(await proposal(fixture, "Second version", "region-0")));
  await rejects(async () => bounded.stage(JSON.stringify(await proposal(fixture, "Third version", "region-0"))), "regional_staging_limit");
  cases.push("region_and_staging_counts_are_bounded");

  const serialMemory = memoryStorage(), firstStore = createRegionVersionStore(serialMemory), secondStore = createRegionVersionStore(serialMemory);
  const firstTicket = await firstStore.stage(JSON.stringify(original));
  let release, started;
  const entered = new Promise((resolve) => { started = resolve; });
  const waiting = new Promise((resolve) => { release = resolve; });
  const activation = firstStore.activate(firstTicket, { verifyComponent: async (kind) => { if (kind === "map") { started(); await waiting; } return true; } });
  await entered;
  let removed = false;
  const removal = secondStore.removeInactiveVersion(original.region_id, original.build_id).then(() => { removed = true; });
  await Promise.resolve(); assert(!removed, "other store waits behind commit lock"); release(); await activation;
  await rejects(() => removal, "regional_version_in_use");
  cases.push("cross_instance_mutations_are_serialized");

  let releasePlan, startPlan;
  const planStarted = new Promise((resolve) => { startPlan = resolve; });
  const planWait = new Promise((resolve) => { releasePlan = resolve; });
  const plan = firstStore.withCommittedRegions(async (snapshot) => {
    assert(Object.isFrozen(snapshot), "planning snapshot is immutable");
    equal(snapshot[0].manifest.build_id, original.build_id, "request captures committed version");
    startPlan(); await planWait;
    equal((await firstStore.read(original.region_id)).build_id, original.build_id, "commit cannot change while request drains");
  });
  await planStarted;
  let deactivated = false;
  const change = secondStore.deactivate(original.region_id, original.build_id).then(() => { deactivated = true; });
  await Promise.resolve(); assert(!deactivated, "deactivation waits for complete planning promise");
  releasePlan(); await plan; await change;
  equal(await firstStore.read(original.region_id), null, "mutation proceeds after request releases ownership");
  cases.push("committed_version_owned_through_complete_planning_promise");

  const ownership = createRegionVersionStore(memoryStorage());
  const current = await ownership.stage(JSON.stringify(original));
  await ownership.activate(current, { verifyComponent: async () => true });
  const staged = await ownership.stage(JSON.stringify(updated));
  let releaseWriter, enteredWriter;
  const writerEntered = new Promise((resolve) => { enteredWriter = resolve; });
  const writerWait = new Promise((resolve) => { releaseWriter = resolve; });
  const writing = ownership.withStagedVersion(staged, async ({ manifest, directory }) => {
    equal(manifest.build_id, updated.build_id, "writer owns exact inactive version");
    assert(directory.kind === "directory", "scoped OPFS directory supplied");
    enteredWriter(); await writerWait;
  });
  await writerEntered;
  await ownership.withCommittedRegions(async (snapshot) => {
    equal(snapshot[0].manifest.build_id, original.build_id, "downloads do not block planning on current version");
    assert((await ownership.committedDirectory(original.region_id, original.build_id)).kind === "directory", "exact committed reader");
  });
  await rejects(() => ownership.committedDirectory(updated.region_id, updated.build_id), "regional_version_changed");
  cases.push("inactive_writer_does_not_block_committed_planning");
  let committed = false;
  const commit = ownership.activate(staged, { verifyComponent: async () => { committed = true; return true; } });
  await Promise.resolve(); assert(!committed, "activation waits until writer drains");
  releaseWriter(); await writing; await commit;
  equal((await ownership.read(original.region_id)).build_id, updated.build_id, "activation follows completed writes");
  cases.push("activation_waits_for_version_component_writer");
  await ownership.deactivate(updated.region_id, updated.build_id);
  let releaseCleanup, enteredCleanup;
  const cleanupEntered = new Promise((resolve) => { enteredCleanup = resolve; });
  const cleanupWait = new Promise((resolve) => { releaseCleanup = resolve; });
  const draining = ownership.withStagedVersion(staged, async () => { enteredCleanup(); await cleanupWait; });
  await cleanupEntered;
  let cleaned = false;
  const cleanup = ownership.removeInactiveVersion(updated.region_id, updated.build_id).then(() => { cleaned = true; });
  await Promise.resolve(); assert(!cleaned, "cleanup cannot delete beneath a writer");
  releaseCleanup(); await draining; await cleanup;
  cases.push("inactive_cleanup_waits_for_component_writer");

  const noLocks = createRegionVersionStore({ storage: memory.storage, locks: null });
  await rejects(() => noLocks.stage(JSON.stringify(original)), "regional_storage_unavailable");
  await rejects(() => store.read("../escape"), "invalid_region_id");
  const pre = new AbortController(); pre.abort();
  await rejects(() => store.stage(JSON.stringify(original), { signal: pre.signal }), "AbortError");
  equal(await store.list(), [], "pre-abort leaves no staged metadata");
  cases.push("storage_path_and_preabort_failures_are_explicit");
  const originRoot = await navigator.storage.getDirectory();
  const ownedName = `pr42-region-versions-${crypto.randomUUID()}`;
  const isolated = await originRoot.getDirectoryHandle(ownedName, { create: true });
  try {
    const options = { storage: { getDirectory: async () => isolated }, locks: navigator.locks };
    const real = createRegionVersionStore(options);
    const staged = await real.stage(JSON.stringify(original));
    equal(await real.read(original.region_id), null, "real OPFS stage stays inactive");
    await real.activate(staged, { verifyComponent: async () => true });
    equal((await createRegionVersionStore(options).read(original.region_id)).build_id, original.build_id, "actual file replacement survives a new store instance");
    await real.deactivate(original.region_id, original.build_id);
    await real.removeInactiveVersion(original.region_id, original.build_id);
    await real.removeEmptyRegion(original.region_id);
    equal(await real.list(), [], "real OPFS owned removal");
  } finally { await originRoot.removeEntry(ownedName, { recursive: true }); }
  cases.push("real_opfs_metadata_commit_reopen_and_removal");
  return cases;
}
async function proposal(source, name, regionId = source.region_id) {
  const manifest = structuredClone(source); manifest.display_name = name; manifest.region_id = regionId;
  manifest.build_id = await regionalBuildIdentity(manifest); return manifest;
}
function memoryStorage() {
  const memory = { failClose: null, unreadable: false };
  const missing = () => new DOMException("missing", "NotFoundError");
  function directory() {
    const children = new Map();
    return { kind: "directory", entries: async function* () { yield* children.entries(); },
      async getDirectoryHandle(name, { create = false } = {}) {
        if (!children.has(name) && create) children.set(name, directory());
        const value = children.get(name); if (!value || value.kind !== "directory") throw missing(); return value;
      },
      async getFileHandle(name, { create = false } = {}) {
        if (!children.has(name) && create) {
          let committed = new Blob([]);
          children.set(name, { kind: "file", async getFile() {
            if (name === "active.json" && memory.unreadable) { memory.unreadable = false; throw new Error("private-storage-detail"); }
            return committed;
          }, async createWritable() {
            let next;
            return { async write(value) { next = new Blob([value]); }, async close() {
              if (name === "active.json" && memory.failClose === "before") throw new Error("close failed");
              committed = next;
              if (name === "active.json" && memory.failClose) { memory.unreadable = memory.failClose === "unreadable"; throw new Error("close outcome lost"); }
            }, async abort() {} };
          } });
        }
        const value = children.get(name); if (!value || value.kind !== "file") throw missing(); return value;
      }, async removeEntry(name) { if (!children.delete(name)) throw missing(); },
    };
  }
  memory.root = directory(); memory.storage = { getDirectory: async () => memory.root };
  const queues = new Map();
  memory.locks = { request(name, action) {
    const result = (queues.get(name) ?? Promise.resolve()).then(action);
    queues.set(name, result.catch(() => {})); return result;
  } };
  return memory;
}
async function write(handle, text) { const writer = await handle.createWritable(); await writer.write(text); await writer.close(); }
function assert(value, message) { if (!value) throw new Error(message); }
function equal(a, b, message) { assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); }
async function rejects(action, code) {
  try { await action(); } catch (error) { equal(error.name === "AbortError" ? error.name : error.code, code, "explicit failure"); return; }
  throw new Error(`Expected rejection ${code}`);
}
