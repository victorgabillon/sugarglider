// Private, read-only replay. Inputs/results stay local; stdout has no geometry.
// Node 22+: node --experimental-default-type=module --expose-gc <this file> ...
import { readFile, stat, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { parseRegionalManifest } from "../src/sugarglider/web/static/regional_manifest.js";
import { createPartitionedRegionData, decodeNatureDirectory,
  NATURE_CACHE_MAX_PARTITIONS } from "../src/sugarglider/web/static/nature_partitions.js";
import { beginRegionalProfile, finishRegionalProfile } from "../src/sugarglider/web/static/regional_performance.js";

const args = process.argv.slice(2), options = new Map();
for (let index = 0; index < args.length; index += 2) {
  if (!["--region", "--routes", "--cache-partitions", "--repetitions", "--output"].includes(args[index])
    || !args[index + 1] || options.has(args[index])) throw Error("Invalid benchmark arguments");
  options.set(args[index], args[index + 1]);
}
if (!options.has("--region") || !options.has("--routes")) throw Error("Specify --region and --routes");
const capacity = Number(options.get("--cache-partitions") ?? NATURE_CACHE_MAX_PARTITIONS), repetitions = Number(options.get("--repetitions") ?? 3);
if (!Number.isInteger(capacity) || capacity < 1 || capacity > NATURE_CACHE_MAX_PARTITIONS
  || !Number.isInteger(repetitions) || repetitions < 1 || repetitions > 5) throw Error("Invalid benchmark bounds");
const root = resolve(options.get("--region")), input = resolve(options.get("--routes"));
if ((await stat(input)).size > 16 * 1024 * 1024) throw Error("Route fixture too large");
const routes = JSON.parse(await readFile(input, "utf8"));
if (!Array.isArray(routes) || routes.length < 1 || routes.length > 16) throw Error("Expected one to sixteen frozen routed candidates");
const manifest = await parseRegionalManifest(await readFile(resolve(root, "manifest.json"), "utf8"));
const directory = await decodeNatureDirectory(await readFile(resolve(root, "nature/partitions.json")), manifest);
const rows = [];
for (let repetition = 0; repetition < repetitions; repetition++) {
  const session = createPartitionedRegionData(manifest, null, directory,
    descriptor => readFile(resolve(root, descriptor.path)), { cachePartitions: capacity });
  global.gc?.();
  for (let index = 0; index < routes.length; index++) {
    const cpu = process.cpuUsage(), started = performance.now();
    beginRegionalProfile(true);
    const result = await session.analyzeNature(routes[index]);
    const wallMs = performance.now() - started, used = process.cpuUsage(cpu), profile = finishRegionalProfile();
    global.gc?.();
    rows.push({ repetition, route_index: index, available: result.available,
      result_sha256: createHash("sha256").update(JSON.stringify(result)).digest("hex"),
      wall_ms: wallMs, cpu_ms: (used.user + used.system) / 1000,
      retained_heap_bytes: process.memoryUsage().heapUsed,
      process_max_rss_bytes: process.resourceUsage().maxRSS * 1024, profile });
  }
}
const output = { schema_version: 1, runtime: process.version, cpu_scope: "node_process_all_threads",
  android_lifecycle_proof: false, opfs_measurement: false, explicit_gc: typeof global.gc === "function",
  cache_partitions: capacity, repetitions, rows };
const encoded = JSON.stringify(output, null, 2) + "\n";
if (options.has("--output")) await writeFile(resolve(options.get("--output")), encoded, { mode: 0o600, flag: "wx" });
else process.stdout.write(encoded);
