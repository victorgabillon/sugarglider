package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

class RegionalElevationTest {
    private val temporary = Files.createTempDirectory("v2-elevation-test-").toFile()
    private val bounds = RoutingPackBounds(2.0, 48.8, 2.16, 48.94)
    private val fixture = V2ElevationFixture(bounds)
    private val archive = syntheticValhallaArchive()
    private val graph = JSONObject().put("schema_version", 2).put("pack_id", "fixture-routing")
        .put("engine", "valhalla").put("engine_version", "3.9.1")
        .put("access_modes", org.json.JSONArray(listOf("foot", "bicycle")))
        .put("bounds", JSONObject().put("west", bounds.west).put("south", bounds.south)
            .put("east", bounds.east).put("north", bounds.north)).toString().toByteArray()
    private val reference = RegionalRoutingPackReference("fixture-region", "a".repeat(64), "fixture-routing",
        bounds, fixtureIdentity(graph), fixtureIdentity(archive), fixture.reference)
    private val root = File(temporary, "regions")
    private val store = RegionalRoutingPackStore(root) { Long.MAX_VALUE }

    @After fun cleanup() {
        Files.walk(temporary.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }

    @Test fun elevationIsMandatoryAndExactlyMatchesInclusiveBounds() {
        assertEquals(4, elevationTilePaths(RoutingPackBounds(1.1, 48.1, 2.0, 49.0)).size)
        assertTrue(reference.isValid())
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().apply { remove("elevation") }))
        assertFalse(reference.copy(elevation = fixture.reference.copy(tiles = emptyList())).isValid())
        assertFalse(reference.copy(elevation = fixture.reference.copy(tiles = fixture.tiles + fixture.tiles)).isValid())
        assertFalse(reference.copy(elevation = fixture.reference.copy(tiles = listOf(fixture.tiles[0].copy(path = "../outside")))).isValid())
    }

    @Test fun completeNativeTransactionIncludesVerifiedDemAndRejectsWrongIdentity() {
        val pack = install()
        assertEquals(reference, pack.regionalReference)
        assertEquals(File(pack.tileArchive.parentFile, "elevation/skadi").canonicalFile, pack.elevationDirectory)
        assertTrue(File(pack.tileArchive.parentFile, "complete.json").isFile)
        assertEquals(pack, store.open(reference))
        val error = assertThrows(RegionalPackException::class.java) {
            store.open(reference.copy(elevation = fixture.reference.copy(componentId = "wrong-component")))
        }
        assertEquals(RegionalPackFailure.IDENTITY_MISMATCH, error.code)
    }

    @Test fun damagedTileNeverCompletesOrReplacesAnInstalledVersion() {
        val previous = install()
        val next = reference.copy(buildId = "b".repeat(64))
        val corrupt = SyntheticHgt.bytes.copyOf().also { it[it.lastIndex] = (it.last() + 1).toByte() }
        assertThrows(RegionalPackException::class.java) {
            store.stage(next, graph, { ByteArrayInputStream(archive) }, fixture.manifest, { ByteArrayInputStream(corrupt) })
        }
        assertFalse(File(root, "${next.regionId}/${next.buildId}/${next.packId}/complete.json").exists())
        assertEquals(previous, store.open(reference))
    }

    @Test fun cancellationDuringDemTransferRollsBackOwnedFiles() {
        var cancelled = false
        assertThrows(RegionalPackException::class.java) {
            store.stage(reference, graph, { ByteArrayInputStream(archive) }, fixture.manifest,
                { ByteArrayInputStream(SyntheticHgt.bytes) }, { cancelled }, { received ->
                    if (received > graph.size + archive.size.toLong() + fixture.manifest.size) cancelled = true
                })
        }
        assertFalse(File(root, "${reference.regionId}/${reference.buildId}").exists())
    }

    @Test fun missingTileAndSymlinkCannotBeReadAsAValidComponent() {
        val pack = install()
        val tile = File(pack.tileArchive.parentFile, "elevation/" + fixture.tiles.single().path)
        val retained = File(temporary, "retained.hgt.gz")
        assertTrue(tile.renameTo(retained))
        assertThrows(RegionalPackException::class.java) { store.open(reference) }
        Files.createSymbolicLink(tile.toPath(), retained.toPath())
        assertThrows(RegionalPackException::class.java) { store.open(reference) }
        assertTrue(retained.isFile)
    }

    @Test fun actorKeysIncludeTheElevationIdentity() {
        val pack = install()
        val changed = pack.copy(regionalReference = reference.copy(elevation = fixture.reference.copy(
            manifest = fixture.reference.manifest.copy(sha256 = "f".repeat(64)))))
        assertNotEquals(pack.actorKey(), changed.actorKey())
    }

    @Test fun persistentActorLeaseSurvivesCallsAndClosesIdempotently() {
        val repository = RegionalRoutingRepository({ store.open(it) }, { store.remove(it) }, {}, {})
        install()
        val lease = repository.acquire(reference)
        repository.withPack(reference) { assertEquals(lease.pack, it) }
        assertThrows(RegionalPackException::class.java) { repository.remove(reference) }
        lease.close(); lease.close()
        repository.remove(reference)
        assertFalse(File(root, "${reference.regionId}/${reference.buildId}").exists())
    }

    @Test fun oldOrNonEnrichedGraphCannotPassByChangingItsManifestLabel() {
        val file = File(temporary, "graph.tar")
        file.writeBytes(archive)
        assertTrue(validV2ValhallaArchive(file))
        val noElevation = archive.copyOf().also { it[1543] = (it[1543].toInt() and 0xbf).toByte() }
        file.writeBytes(noElevation)
        assertFalse(validV2ValhallaArchive(file))
        val old = archive.copyOf().also { "3.6.3".toByteArray().copyInto(it, 1552) }
        file.writeBytes(old)
        assertFalse(validV2ValhallaArchive(file))
        val wrongTile = archive.copyOf().also { it[1536] = 3 }
        file.writeBytes(wrongTile)
        assertFalse(validV2ValhallaArchive(file))
    }

    @Test fun documentedAndResearchDatumPairsStayStrictAndNativeRepliesAreTruthful() {
        for ((status, datum, publication) in listOf(
            Triple("unresolved", "unresolved", false),
            Triple("documented", "EGM96", false),
            Triple("documented", "EGM96", true),
        )) {
            val metadata = JSONObject(String(fixture.manifest, Charsets.UTF_8))
                .put("provenance_status", status).put("vertical_datum", datum)
                .put("publication_allowed", publication).toString().toByteArray()
            val changed = reference.copy(buildId = (if (publication) "c" else if (status == "documented") "b" else "a").repeat(64),
                elevation = fixture.reference.copy(manifest = fixtureIdentity(metadata)))
            val pack = store.stage(changed, graph, { ByteArrayInputStream(archive) }, metadata,
                { ByteArrayInputStream(SyntheticHgt.bytes) })
            val manifest = File(requireNotNull(pack.elevationDirectory).parentFile, "manifest.json")
            assertEquals(if (status == "documented") ELEVATION_EGM96_REFERENCE else ELEVATION_HEIGHT_REFERENCE,
                verifiedRegionalHeightReference(manifest))
            store.remove(changed) // Each case owns a fresh slot; keep the two-version limit.
        }
        val bad = File(temporary, "bad-datum.json")
        for ((status, datum) in listOf(Pair("documented", "unresolved"), Pair("unresolved", "EGM96"), Pair("documented", "EGM2008"))) {
            bad.writeText(JSONObject().put("provenance_status", status).put("vertical_datum", datum).toString())
            assertThrows(IllegalStateException::class.java) { verifiedRegionalHeightReference(bad) }
        }
    }


    @Test fun privateIgn69BindsCompleteSourceMetadataAndNeverBecomesEgm96() {
        val metadata = JSONObject(String(fixture.manifest, Charsets.UTF_8))
            .put("provenance_status", "documented").put("vertical_datum", "IGN69")
            .put("derivation", syntheticIgnDerivation()).toString().toByteArray()
        val changed = reference.copy(elevation = fixture.reference.copy(manifest = fixtureIdentity(metadata)))
        val pack = store.stage(changed, graph, { ByteArrayInputStream(archive) }, metadata,
            { ByteArrayInputStream(SyntheticHgt.bytes) })
        val manifest = File(requireNotNull(pack.elevationDirectory).parentFile, "manifest.json")
        assertEquals(ELEVATION_IGN69_REFERENCE, verifiedRegionalHeightReference(manifest))
        assertNotEquals(ELEVATION_EGM96_REFERENCE, verifiedRegionalHeightReference(manifest))
        val bad = File(temporary, "bad-ign.json")
        for (mutation in listOf<(JSONObject) -> Unit>(
            { it.put("publication_allowed", true) },
            { it.remove("derivation") },
            { it.getJSONObject("derivation").getJSONObject("sources").put("vertical_crs", "EPSG:5773") },
            { it.getJSONObject("derivation").put("transformation_sha256", "wrong") },
            { it.getJSONObject("derivation").getJSONObject("sources").getJSONArray("files").getJSONObject(0).put("url", "https://other.example/terrain") },
        )) {
            val value = JSONObject(String(metadata, Charsets.UTF_8)); mutation(value)
            bad.writeText(value.toString())
            assertThrows(IllegalStateException::class.java) { verifiedRegionalHeightReference(bad) }
        }
    }

    private fun install(): RoutingPack = store.stage(reference, graph, { ByteArrayInputStream(archive) },
        fixture.manifest, { ByteArrayInputStream(SyntheticHgt.bytes) })
}
