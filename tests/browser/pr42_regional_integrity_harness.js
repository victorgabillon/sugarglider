import { REGIONAL_HASH_READ_BYTES, regionalFileIntegrity, verifyRegionalFile } from "../../src/sugarglider/web/static/regional_integrity.js";
import { sha256 } from "../../src/sugarglider/web/static/vendor/noble-hashes-2.4.0/sha2.js";

export async function runPr42RegionalIntegrityHarness() {
  const scenarios = [];
  const encode = (text) => new TextEncoder().encode(text);
  equal(hex(sha256(new Uint8Array())), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "empty SHA-256 vector");
  equal(hex(sha256(encode("abc"))), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "abc SHA-256 vector");
  scenarios.push("known_sha256_vectors");

  for (const length of [1, 55, 56, 63, 64, 65, REGIONAL_HASH_READ_BYTES - 1, REGIONAL_HASH_READ_BYTES, REGIONAL_HASH_READ_BYTES + 1]) {
    const bytes = fixture(length), descriptor = await identity(bytes);
    equal((await verifyRegionalFile(new Blob([bytes]), descriptor)).sha256, descriptor.sha256, "WebCrypto cross-check at padding/read boundary");
  }
  scenarios.push("padding_and_read_boundaries_match_webcrypto");

  const bytes = fixture(REGIONAL_HASH_READ_BYTES * 9 + 13), descriptor = await identity(bytes);
  let reads = 0, total = 0, inFlight = 0;
  const progress = [];
  const file = { size: bytes.length, slice(start, end) {
    assert(end - start <= REGIONAL_HASH_READ_BYTES && end > start, "bounded positive read");
    equal(start, total, "contiguous, nonoverlapping reads");
    total += end - start; reads += 1;
    return { async arrayBuffer() { equal(inFlight++, 0, "single read in flight");
      await Promise.resolve(); inFlight -= 1; return bytes.slice(start, end).buffer; } };
  } };
  const checked = await verifyRegionalFile(file, descriptor, { onProgress: (value) => progress.push(value) });
  equal(total, bytes.length, "each byte read once"); equal(reads, 10, "bounded read count");
  assert(Object.isFrozen(checked), "immutable result");
  scenarios.push("bounded_sequential_reads_without_whole_file_buffer");
  equal(progress.at(-1).verified_bytes, bytes.length, "complete progress");
  assert(progress.every((value, i) => value.byte_size === bytes.length && (!i || value.verified_bytes > progress[i - 1].verified_bytes)), "monotonic progress");
  scenarios.push("monotonic_bounded_progress");

  await rejects(() => verifyRegionalFile(new Blob([bytes]), { ...descriptor, sha256: "0".repeat(64) }), "regional_checksum_mismatch");
  scenarios.push("same_size_corruption_rejected");
  let touched = false;
  await rejects(() => verifyRegionalFile({ size: 1, slice() { touched = true; } }, descriptor), "regional_size_mismatch");
  assert(!touched, "wrong size fails before reading"); scenarios.push("size_mismatch_before_reads");
  for (const invalid of [null, {}, { ...descriptor, byte_size: 0 }, { ...descriptor, byte_size: 2 ** 31 + 1 }, { ...descriptor, byte_size: NaN }, { ...descriptor, sha256: "A".repeat(64) }, { ...descriptor, sha256: "../file" }]) {
    await rejects(() => Promise.resolve().then(() => regionalFileIntegrity(invalid)), "invalid_regional_file");
  }
  scenarios.push("invalid_descriptors_rejected");

  const pre = new AbortController(); pre.abort();
  await rejects(() => verifyRegionalFile({ size: bytes.length, slice() { touched = true; } }, descriptor, { signal: pre.signal }), "AbortError");
  assert(!touched, "pre-abort performs no read"); scenarios.push("preabort_before_reads");
  const during = new AbortController(); let reported = false;
  await rejects(() => verifyRegionalFile({ size: bytes.length, slice(start, end) { return { async arrayBuffer() {
    during.abort(); return bytes.slice(start, end).buffer;
  } }; } }, descriptor, { signal: during.signal, onProgress: () => { reported = true; } }), "AbortError");
  assert(!reported, "aborted pending read never updates progress"); scenarios.push("abort_owns_pending_read");
  const last = new AbortController();
  await rejects(() => verifyRegionalFile(new Blob([bytes]), descriptor, { signal: last.signal, onProgress: (p) => {
    if (p.verified_bytes === bytes.length) last.abort();
  } }), "AbortError"); scenarios.push("abort_after_last_read_prevents_success");

  const timed = new AbortController(); let immediateReads = 0;
  setTimeout(() => timed.abort(), 0);
  await rejects(() => verifyRegionalFile({ size: bytes.length, slice(start, end) { immediateReads += 1; return { arrayBuffer: async () => bytes.slice(start, end).buffer }; } }, descriptor, { signal: timed.signal }), "AbortError");
  assert(immediateReads <= 8, "timers can cancel immediately resolved reads"); scenarios.push("cancellation_yields_to_worker_events");

  const badRead = { size: bytes.length, slice() { return { async arrayBuffer() { throw new Error("private-path-must-not-escape"); } }; } };
  const error = await rejects(() => verifyRegionalFile(badRead, descriptor), "regional_read_failed");
  assert(!error.message.includes("private-path"), "read errors stay generic"); scenarios.push("read_failure_is_explicit_and_redacted");
  await rejects(() => verifyRegionalFile({ size: bytes.length, slice() { return { arrayBuffer: async () => new ArrayBuffer(1) }; } }, descriptor), "regional_size_mismatch");
  scenarios.push("short_snapshot_read_rejected");

  const mutable = { ...descriptor };
  const immutable = await verifyRegionalFile(new Blob([bytes]), mutable, { onProgress: () => { mutable.sha256 = "0".repeat(64); mutable.byte_size = 1; } });
  equal(immutable.sha256, descriptor.sha256, "descriptor captured before first asynchronous read");
  scenarios.push("descriptor_mutation_cannot_change_expected_identity");

  const root = await navigator.storage.getDirectory();
  const name = `pr42-integrity-${crypto.randomUUID()}`;
  try {
    const handle = await root.getFileHandle(name, { create: true });
    const writer = await handle.createWritable(); await writer.write(bytes); await writer.close();
    const result = await verifyRegionalFile(await handle.getFile(), descriptor);
    equal(result.sha256, descriptor.sha256, "actual OPFS file verified");
    equal((await handle.getFile()).size, bytes.length, "verification is read-only");
  } finally { await root.removeEntry(name); }
  scenarios.push("real_opfs_file_verification_and_owned_cleanup");
  return scenarios;
}
function fixture(length) { return Uint8Array.from({ length }, (_, i) => (i * 37 + 11) % 251); }
function hex(bytes) { return Array.from(bytes, (x) => x.toString(16).padStart(2, "0")).join(""); }
async function identity(bytes) { return { byte_size: bytes.length, sha256: hex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))) }; }
function assert(value, message) { if (!value) throw new Error(message); }
function equal(actual, expected, message) { assert(actual === expected, `${message}: ${actual} != ${expected}`); }
async function rejects(action, code) {
  try { await action(); } catch (error) { equal(error.name === "AbortError" ? error.name : error.code ?? error.name, code, "explicit failure"); return error; }
  throw new Error(`Expected failure: ${code}`);
}
