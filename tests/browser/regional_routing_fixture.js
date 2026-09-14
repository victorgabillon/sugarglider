// Wire identity only. Placeholder hashes never identify real regional data.
export const syntheticRegionalReference = Object.freeze({
  region_id: "marly-fixture", build_id: "a".repeat(64), pack_id: "marly-dev-v1",
  bounds: Object.freeze([2, 48.8, 2.16, 48.94]),
  manifest: Object.freeze({ byte_size: 270, sha256: "b".repeat(64) }),
  archive: Object.freeze({ byte_size: 512, sha256: "c".repeat(64) }),
});
