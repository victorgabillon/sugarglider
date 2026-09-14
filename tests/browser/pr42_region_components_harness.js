import { createRegionVersionStore } from "../../src/sugarglider/web/static/region_versions.js";
import { createVersionedRegionComponents } from "../../src/sugarglider/web/static/region_components.js";
import { regionalBuildIdentity, sha256Bytes } from "../../src/sugarglider/web/static/regional_manifest.js";
import { manifest as mapManifest, tinyPmtiles } from "./pr36_offline_maps_harness.js";
import { createLocalRegionClient } from "../../src/sugarglider/web/static/local_region_client.js";

export async function runPr42RegionComponentsHarness() {
  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const origin = await navigator.storage.getDirectory(), name = `pr42-components-${crypto.randomUUID()}`;
  const root = await origin.getDirectoryHandle(name, { create: true });
  const storage = { getDirectory: async () => root, estimate: async () => ({ quota: 1e9, usage: 0 }) };
  const versions = createRegionVersionStore({ storage, locks: navigator.locks });
  const cases = [], requests = [];
  let available = true, corrupt = null, current;
  const fetchResource = async (url, options) => {
    assert(available, "No network allowed after fixture shutdown");
    requests.push({ url, options });
    const path = new URL(url).pathname.slice(1);
    let bytes = current.files.get(path);
    assert(bytes, `Only declared component downloads, got ${path}`);
    if (path === corrupt) { bytes = bytes.slice(); bytes[bytes.length - 1] ^= 1; }
    return new Response(bytes, { headers: { "Content-Length": String(bytes.byteLength) } });
  };
  const components = (manifest, directory) => createVersionedRegionComponents({ manifest, directory,
    storage, locks: navigator.locks, fetchResource, pageLocation: { href: "https://app.example/" } });
  try {
    current = await distribution(fixture, "First");
    const original = current;
    const ticket = await versions.stage(JSON.stringify(original.manifest));
    await versions.withStagedVersion(ticket, async ({ manifest, directory }) => {
      const scoped = await components(manifest, directory);
      await scoped.installMap("https://packs.example/manifest.json");
      equal(await versions.read(manifest.region_id), null, "a complete map alone never activates the region");
      await scoped.installIndexes("https://packs.example/manifest.json");
      equal(await versions.read(manifest.region_id), null, "web components remain inactive until the regional commit");
      const paths = await fileNames(directory);
      assert(paths.some((path) => path.endsWith("basemap.pmtiles")), "map stays in shared OPFS layout");
      assert(paths.some((path) => path.endsWith("pois/index.json.gz")), "existing index layout retained");
      assert(!paths.some((path) => path.includes("valhalla") || path.includes("routing/")), "no native archive copy in OPFS");
    });
    cases.push("shared_map_and_index_formats_staged_in_real_opfs_without_native_copy");
    equal(requests.map((entry) => new URL(entry.url).pathname), ["/map/manifest.json", "/map/basemap.pmtiles", "/pois/index.json.gz", "/nature/index.json.gz"], "captured regional manifest is never refetched");
    assert(requests.every(({ options }) => options.credentials === "omit" && options.redirect === "error"
      && options.cache === "no-store" && options.referrerPolicy === "no-referrer"), "credential-free bounded component transport");
    cases.push("captured_manifest_and_credential_free_component_downloads");

    await rejects(() => versions.activate(ticket, { verifyComponent: async (kind) => kind !== "routing" }), "regional_components_unavailable");
    equal(await versions.read(original.manifest.region_id), null, "missing native routing never authorizes activation");
    cases.push("missing_native_component_blocks_regional_activation");
    // Routing is a synthetic acknowledgement here; native archive storage has its
    // own JVM fixtures. This harness establishes web-component behavior only.
    await versions.activate(ticket, { verifyComponent: async (kind, manifest, directory) => {
      const scoped = await components(manifest, directory);
      if (kind === "map") return scoped.verifyMap();
      if (kind === "routing") return true;
      equal((await scoped.openIndexes()).identity.build_id, manifest.build_id, "validated indexes bind exact build");
      return true;
    } });
    available = false;
    await versions.withCommittedRegions(async (snapshot) => {
      const manifest = snapshot[0].manifest;
      const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
      const scoped = await components(manifest, directory);
      await scoped.verifyMap();
      const opened = await scoped.openMap();
      equal(opened.header.specVersion, 3, "actual PMTiles reader survives new instance");
      assert((await opened.source.getBytes(0, 8)).data.byteLength === 8, "bounded map reads after network shutdown");
      const data = await scoped.openIndexes();
      equal(data.identity.poi_count, 5, "golden POI data consumed locally");
      assert(Math.abs(data.analyzeNature(fixture.route).nature_score - fixture.expected.nature_score) < 1e-6, "golden nature result unchanged");
      const mapDirectory = await (await directory.getDirectoryHandle("sugarglider-map-packs")).getDirectoryHandle(manifest.components.map.component_id);
      const stored = await (await mapDirectory.getFileHandle("manifest.json")).getFile();
      equal(await stored.text(), new TextDecoder().decode(original.files.get("map/manifest.json")), "original map manifest bytes retained for restart verification");
    });
    cases.push("new_instance_reopens_exact_map_and_golden_indexes_without_fetch");
    cases.push("original_component_manifest_bytes_preserve_digest_across_restart");

    const worker = createLocalRegionClient();
    try {
      await versions.withCommittedRegions(async () => {
        const manifest = original.manifest;
        const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
        const session = await worker.loadVersion(manifest, directory);
        equal(session.identity.build_id, manifest.build_id, "real worker loads owned OPFS version");
        const analyzed = await session.analyzeNature(fixture.route);
        assert(Math.abs(analyzed.nature_score - fixture.expected.nature_score) < 1e-6, "worker keeps golden nature semantics");
        equal((await worker.loadVersion(manifest, directory)).identity, session.identity, "verified immutable cache reuse");
        const componentRoot = await directory.getDirectoryHandle("sugarglider-region-components");
        const indexVersion = await (await componentRoot.getDirectoryHandle(manifest.region_id)).getDirectoryHandle(manifest.build_id);
        const natureFile = await (await indexVersion.getDirectoryHandle("nature")).getFileHandle("index.json.gz");
        const originalBytes = new Uint8Array(await (await natureFile.getFile()).arrayBuffer());
        const broken = originalBytes.slice(); broken[broken.length - 1] ^= 1;
        let writable = await natureFile.createWritable(); await writable.write(broken); await writable.close();
        await rejects(() => worker.loadVersion(manifest, directory), "regional_checksum_mismatch");
        writable = await natureFile.createWritable(); await writable.write(originalBytes); await writable.close();
      });
      cases.push("real_worker_uses_owned_version_and_detects_disk_corruption_despite_parsed_cache");
    } finally { worker.close(); }

    available = true;
    current = await distribution(fixture, "Corrupt update");
    let next = await versions.stage(JSON.stringify(current.manifest));
    corrupt = "nature/index.json.gz";
    await rejects(() => versions.withStagedVersion(next, async ({ manifest, directory }) => {
      const scoped = await components(manifest, directory);
      await scoped.installMap("https://packs.example/manifest.json");
      await scoped.installIndexes("https://packs.example/manifest.json");
    }), "regional_checksum_mismatch");
    equal((await versions.read(original.manifest.region_id)).build_id, original.manifest.build_id, "bad index update preserves committed version");
    corrupt = null;
    const beforeResume = requests.length;
    await versions.withStagedVersion(next, async ({ manifest, directory }) => {
      const scoped = await components(manifest, directory);
      await scoped.installMap("https://packs.example/manifest.json");
      await scoped.installIndexes("https://packs.example/manifest.json");
    });
    equal(requests.slice(beforeResume).map((entry) => new URL(entry.url).pathname), ["/pois/index.json.gz", "/nature/index.json.gz"], "resume verifies completed map without another archive download");
    await versions.removeInactiveVersion(next.manifest.region_id, next.manifest.build_id);
    cases.push("corrupt_update_preserves_active_and_resumes_verified_map_without_download");

    current = await distribution(fixture, "Cancel update");
    next = await versions.stage(JSON.stringify(current.manifest));
    const cancel = new AbortController();
    await rejects(() => versions.withStagedVersion(next, async ({ manifest, directory }) => {
      const scoped = await components(manifest, directory);
      await scoped.installMap("https://packs.example/manifest.json", { signal: cancel.signal, onProgress: () => cancel.abort() });
    }), "map_pack_download_cancelled");
    equal((await versions.read(original.manifest.region_id)).build_id, original.manifest.build_id, "cancel keeps old active region");
    await versions.removeInactiveVersion(next.manifest.region_id, next.manifest.build_id);
    cases.push("cancelled_map_update_preserves_active_region");

    for (const mutation of ["digest", "identity", "bounds", "schema"]) {
      current = await distribution(fixture, `Invalid ${mutation}`, mutation);
      next = await versions.stage(JSON.stringify(current.manifest));
      const before = requests.length;
      await rejects(() => versions.withStagedVersion(next, async ({ manifest, directory }) => {
        const scoped = await components(manifest, directory);
        await scoped.installMap("https://packs.example/manifest.json");
      }), mutation === "digest" ? "regional_checksum_mismatch" : mutation === "schema" ? "map_pack_invalid" : "regional_identity_mismatch");
      equal(requests.length, before + 1, "bad map manifest rejected before archive transfer");
      await versions.removeInactiveVersion(next.manifest.region_id, next.manifest.build_id);
    }
    cases.push("map_manifest_hash_identity_bounds_and_schema_checked_before_archive");

    available = false;
    await versions.withCommittedRegions(async (snapshot) => {
      const manifest = snapshot[0].manifest;
      const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
      const mapDirectory = await (await directory.getDirectoryHandle("sugarglider-map-packs")).getDirectoryHandle(manifest.components.map.component_id);
      const handle = await mapDirectory.getFileHandle("basemap.pmtiles");
      const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer()); bytes[bytes.length - 1] ^= 1;
      const writer = await handle.createWritable(); await writer.write(bytes); await writer.close();
      const scoped = await components(manifest, directory);
      await rejects(() => scoped.verifyMap(), "regional_checksum_mismatch");
      await rejects(() => scoped.openMap(), "regional_checksum_mismatch");
    });
    cases.push("stored_map_corruption_remains_explicit_on_revalidation");
    await versions.deactivate(original.manifest.region_id, original.manifest.build_id);
    await versions.removeInactiveVersion(original.manifest.region_id, original.manifest.build_id);
    await versions.removeEmptyRegion(original.manifest.region_id);
    equal(await versions.list(), [], "explicit owned cleanup");
    cases.push("explicit_web_component_removal_clears_only_owned_region");
    return cases;
  } finally { await origin.removeEntry(name, { recursive: true }); }
}

export async function distribution(fixture, displayName, mutation = null) {
  const manifest = structuredClone(fixture.manifest), files = new Map();
  manifest.display_name = displayName;
  const archive = tinyPmtiles(manifest.bounds, 0, 14);
  const map = mapManifest(manifest.components.map.component_id, manifest.bounds, archive.length);
  if (mutation === "identity") map.pack_id = "other-map";
  if (mutation === "bounds") map.bounds = [0, 0, .01, .02];
  if (mutation === "schema") map.schema_version = 2;
  // Extra whitespace proves that the exact validated source survives storage.
  files.set("map/manifest.json", new TextEncoder().encode(`\n${JSON.stringify(map)}  \n`));
  files.set("map/basemap.pmtiles", archive);
  for (const kind of ["pois", "nature"]) {
    const compressed = new Blob([JSON.stringify(fixture[kind])]).stream().pipeThrough(new CompressionStream("gzip"));
    files.set(`${kind}/index.json.gz`, new Uint8Array(await new Response(compressed).arrayBuffer()));
  }
  for (const component of ["map", "pois", "nature"]) {
    for (const descriptor of manifest.components[component].files) {
      const bytes = files.get(descriptor.path); descriptor.byte_size = bytes.byteLength; descriptor.sha256 = await sha256Bytes(bytes);
    }
  }
  if (mutation === "digest") manifest.components.map.files[0].sha256 = "0".repeat(64);
  manifest.build_id = await regionalBuildIdentity(manifest);
  return { manifest, files };
}

async function fileNames(directory, prefix = "") {
  const paths = [];
  for await (const [name, handle] of directory.entries()) {
    if (handle.kind === "directory") paths.push(...await fileNames(handle, `${prefix}${name}/`));
    else paths.push(`${prefix}${name}`);
  }
  return paths;
}
function assert(value, message) { if (!value) throw new Error(message); }
function equal(a, b, message) { assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); }
async function rejects(action, code) {
  try { await action(); } catch (error) { equal(error.name === "AbortError" ? error.name : error.code, code, "explicit failure"); return; }
  throw new Error(`Expected rejection ${code}`);
}
