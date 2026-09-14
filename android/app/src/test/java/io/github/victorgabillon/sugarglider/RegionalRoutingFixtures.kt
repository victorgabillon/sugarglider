package io.github.victorgabillon.sugarglider

// Protocol identity only; these placeholder digests never identify real map data.
internal fun syntheticRegionalRoutingReference() = RegionalRoutingPackReference(
    regionId = "marly-fixture", buildId = "a".repeat(64), packId = "marly-dev-v1",
    bounds = RoutingPackBounds(2.0, 48.8, 2.16, 48.94),
    manifest = RegionalFileIdentity(270, "b".repeat(64)),
    archive = RegionalFileIdentity(512, "c".repeat(64)),
)
