package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.nio.file.Files

class RoutingPackRegistryTest {
    private lateinit var root: File

    @Before
    fun createRoot() {
        root = Files.createTempDirectory("routing-pack-registry-").toFile()
    }

    @After
    fun removeRoot() {
        root.deleteRecursively()
    }

    @Test
    fun validManifestIsStrictVersionedAndDirectoryBound() {
        val payload = manifest("marly-dev-v1", MARLY)
        val parsed = requireNotNull(RoutingPackManifest.parse(payload, "marly-dev-v1"))
        assertEquals(ROUTING_PACK_MANIFEST_SCHEMA_VERSION, parsed.schemaVersion)
        assertEquals(ROUTING_PACK_ENGINE, parsed.engine)
        assertEquals(ROUTING_PACK_ENGINE_VERSION, parsed.engineVersion)
        assertEquals(MARLY, parsed.bounds)

        assertNull(RoutingPackManifest.parse("not-json", "marly-dev-v1"))
        assertNull(
            RoutingPackManifest.parse(
                JSONObject(payload).put("unexpected", true).toString(),
                "marly-dev-v1",
            ),
        )
        assertNull(
            RoutingPackManifest.parse(
                JSONObject(payload).put("schema_version", 2).toString(),
                "marly-dev-v1",
            ),
        )
        assertNull(RoutingPackManifest.parse(payload, "different-dev-v1"))
        assertNull(
            RoutingPackManifest.parse(
                manifest("../outside", MARLY),
                "../outside",
            ),
        )
    }

    @Test
    fun unsupportedEngineVersionAndInvalidBoundsAreRejected() {
        val payload = JSONObject(manifest("marly-dev-v1", MARLY))
        assertNull(
            RoutingPackManifest.parse(
                JSONObject(payload.toString()).put("engine", "graphhopper").toString(),
                "marly-dev-v1",
            ),
        )
        assertNull(
            RoutingPackManifest.parse(
                JSONObject(payload.toString()).put("engine_version", "4.0.0").toString(),
                "marly-dev-v1",
            ),
        )
        val invalidBounds = JSONObject(payload.toString()).put(
            "bounds",
            bounds(MARLY.copy(west = MARLY.east)),
        )
        assertNull(RoutingPackManifest.parse(invalidBounds.toString(), "marly-dev-v1"))
        val nonNumericBounds = JSONObject(payload.toString())
            .getJSONObject("bounds")
            .put("north", "48.94")
        assertNull(
            RoutingPackManifest.parse(
                JSONObject(payload.toString()).put("bounds", nonNumericBounds).toString(),
                "marly-dev-v1",
            ),
        )
        assertFalse(RoutingPackBounds(-181.0, 0.0, 1.0, 1.0).isValid())
        assertFalse(RoutingPackBounds(0.0, Double.NaN, 1.0, 1.0).isValid())
    }

    @Test
    fun containmentIncludesEveryManifestBoundary() {
        val bounds = RoutingPackBounds(west = 2.0, south = 48.0, east = 3.0, north = 49.0)
        for (coordinate in listOf(
            LocalRouteCoordinate(48.0, 2.0),
            LocalRouteCoordinate(49.0, 3.0),
            LocalRouteCoordinate(48.0, 3.0),
            LocalRouteCoordinate(49.0, 2.0),
        )) {
            assertTrue(bounds.contains(coordinate))
        }
        assertFalse(bounds.contains(LocalRouteCoordinate(49.000001, 2.5)))
        assertFalse(bounds.contains(LocalRouteCoordinate(48.5, 3.000001)))
    }

    @Test
    fun registryRequiresStrictManifestAndNonemptyFixedArchive() {
        installPack("valid-dev-v1", MARLY)
        installPack("empty-dev-v1", PARIS, tilePayload = byteArrayOf())
        installPack("corrupt-dev-v1", PARIS, tilePayload = "not-a-tar".toByteArray())
        installPack("missing-tiles-dev-v1", PARIS, createArchive = false)
        val missingManifest = File(root, "missing-manifest-dev-v1").apply { mkdirs() }
        File(missingManifest, "valhalla_tiles.tar").writeText("tiles")
        val mismatch = File(root, "directory-dev-v1").apply { mkdirs() }
        File(mismatch, "manifest.json").writeText(manifest("other-dev-v1", PARIS))
        File(mismatch, "valhalla_tiles.tar").writeText("tiles")

        assertEquals(listOf("valid-dev-v1"), registry().installedPacks().map { it.packId })
    }

    @Test
    fun selectionRequiresOnePackToContainBothEndpoints() {
        installPack("marly-dev-v1", MARLY)
        installPack("paris-dev-v1", PARIS)
        val registry = registry()
        assertEquals(
            "marly-dev-v1",
            registry.select(MARLY_ORIGIN, MARLY_DESTINATION)?.packId,
        )
        assertEquals(
            "paris-dev-v1",
            registry.select(PARIS_ORIGIN, PARIS_DESTINATION)?.packId,
        )
        assertNull(registry.select(MARLY_ORIGIN, PARIS_DESTINATION))
        assertNull(
            registry.select(
                LocalRouteCoordinate(47.0, 1.0),
                LocalRouteCoordinate(47.1, 1.1),
            ),
        )
    }

    @Test
    fun overlappingSelectionPrefersSmallestBoundsThenStablePackId() {
        val broad = RoutingPackBounds(1.0, 47.0, 4.0, 50.0)
        val specific = RoutingPackBounds(2.0, 48.0, 3.0, 49.0)
        installPack("broad-dev-v1", broad)
        installPack("z-specific-dev-v1", specific)
        installPack("a-specific-dev-v1", specific)

        assertEquals(
            "a-specific-dev-v1",
            registry().select(MARLY_ORIGIN, MARLY_DESTINATION)?.packId,
        )
    }

    @Test
    fun actorLifecycleIsBoundedAcrossAABBASequence() {
        installPack("marly-dev-v1", MARLY)
        installPack("paris-dev-v1", PARIS)
        val packs = registry().installedPacks().associateBy(RoutingPack::packId)
        val created = mutableListOf<String>()
        val holder = SingleCurrentRoutingPackActor { pack ->
            "${pack.packId}#${created.size + 1}".also(created::add)
        }
        val marly = requireNotNull(packs["marly-dev-v1"])
        val paris = requireNotNull(packs["paris-dev-v1"])
        val selections = listOf(marly, marly, paris, paris, marly).map(holder::actorFor)

        assertEquals(listOf(true, false, true, false, true), selections.map { it.coldStart })
        assertEquals(
            listOf(
                "marly-dev-v1#1",
                "marly-dev-v1#1",
                "paris-dev-v1#2",
                "paris-dev-v1#2",
                "marly-dev-v1#3",
            ),
            selections.map { it.actor },
        )
        assertEquals("marly-dev-v1", holder.currentPackId())
        assertEquals(3, created.size)
    }

    @Test
    fun failedPackSwitchCannotReplaceTheCurrentActor() {
        installPack("marly-dev-v1", MARLY)
        installPack("paris-dev-v1", PARIS)
        val packs = registry().installedPacks().associateBy(RoutingPack::packId)
        val holder = SingleCurrentRoutingPackActor { pack ->
            if (pack.packId == "paris-dev-v1") error("synthetic initialization failure")
            "marly-actor"
        }
        val marly = requireNotNull(packs["marly-dev-v1"])
        val paris = requireNotNull(packs["paris-dev-v1"])

        assertTrue(holder.actorFor(marly).coldStart)
        assertTrue(runCatching { holder.actorFor(paris) }.isFailure)
        val retained = holder.actorFor(marly)
        assertFalse(retained.coldStart)
        assertEquals("marly-actor", retained.actor)
        assertEquals("marly-dev-v1", holder.currentPackId())
    }

    private fun registry(): RoutingPackRegistry = RoutingPackRegistry(root)

    private fun installPack(
        packId: String,
        packBounds: RoutingPackBounds,
        tilePayload: ByteArray = validTileArchive(),
        createArchive: Boolean = true,
    ) {
        val directory = File(root, packId).apply { mkdirs() }
        File(directory, "manifest.json").writeText(manifest(packId, packBounds))
        if (createArchive) File(directory, "valhalla_tiles.tar").writeBytes(tilePayload)
    }

    private fun manifest(packId: String, packBounds: RoutingPackBounds): String = JSONObject()
        .put("schema_version", ROUTING_PACK_MANIFEST_SCHEMA_VERSION)
        .put("pack_id", packId)
        .put("engine", ROUTING_PACK_ENGINE)
        .put("engine_version", ROUTING_PACK_ENGINE_VERSION)
        .put("bounds", bounds(packBounds))
        .toString()

    private fun bounds(value: RoutingPackBounds): JSONObject = JSONObject()
        .put("west", value.west)
        .put("south", value.south)
        .put("east", value.east)
        .put("north", value.north)

    private fun validTileArchive(): ByteArray = ByteArray(512).also { header ->
        "index.bin".toByteArray().copyInto(header)
        "ustar".toByteArray().copyInto(header, destinationOffset = 257)
    }

    private companion object {
        val MARLY = RoutingPackBounds(2.00, 48.80, 2.16, 48.94)
        val PARIS = RoutingPackBounds(2.25, 48.80, 2.42, 48.92)
        val MARLY_ORIGIN = LocalRouteCoordinate(48.8715, 2.0965)
        val MARLY_DESTINATION = LocalRouteCoordinate(48.8983, 2.0969)
        val PARIS_ORIGIN = LocalRouteCoordinate(48.8584, 2.2945)
        val PARIS_DESTINATION = LocalRouteCoordinate(48.8606, 2.3376)
    }
}
