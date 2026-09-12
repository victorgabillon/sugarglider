package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class RegionalRoutingPackStoreTest {
    private lateinit var temporary: File
    private lateinit var root: File
    private lateinit var store: RegionalRoutingPackStore
    // Synthetic header-shaped bytes exercise storage only, never native routing.
    private val archive = ByteArray(256 * 1_024 + 512).also {
        "index.bin".toByteArray().copyInto(it)
        "ustar".toByteArray().copyInto(it, 257)
    }
    private val bounds = RoutingPackBounds(1.0, 48.0, 2.0, 49.0)
    private val manifest get() = JSONObject()
        .put("schema_version", 2).put("pack_id", "test-region-v1")
        .put("engine", "valhalla").put("engine_version", "3.6.3")
        .put("access_modes", JSONArray(listOf("foot", "bicycle")))
        .put("bounds", JSONObject().put("west", bounds.west).put("south", bounds.south)
            .put("east", bounds.east).put("north", bounds.north))
        .toString().toByteArray()

    @Before
    fun setup() {
        temporary = Files.createTempDirectory("regional-routing-store-").toFile()
        root = File(temporary, "regions")
        store = RegionalRoutingPackStore(root) { Long.MAX_VALUE }
    }

    @After
    fun cleanup() {
        // walkFileTree does not follow links, including the escape fixtures.
        Files.walk(temporary.toPath()).use { paths ->
            paths.sorted(Comparator.reverseOrder()).forEach(Files::delete)
        }
    }

    @Test
    fun referenceIsStrictBoundedAndNeverCarriesPathsOrAuthority() {
        val reference = reference()
        assertEquals(reference, RegionalRoutingPackReference.parse(reference.toJson()))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("path", "/tmp")))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("token", "fixture")))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("region_id", "../outside")))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("region_id", "a..b")))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("build_id", "A".repeat(64))))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("bounds", JSONArray(listOf(1, 48, 2, "49")))))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("archive",
            reference.archive.toJson().put("byte_size", archive.size.toString()))))
        assertNull(RegionalRoutingPackReference.parse(reference.toJson().put("archive",
            reference.archive.toJson().put("byte_size", archive.size.toDouble()))))
        for (invalid in listOf(
            reference.copy(archive = reference.archive.copy(byteSize = 0)),
            reference.copy(archive = reference.archive.copy(byteSize = 513)),
            reference.copy(archive = reference.archive.copy(byteSize = MAX_REGIONAL_ROUTING_PACK_BYTES + 512)),
            reference.copy(manifest = reference.manifest.copy(byteSize = MAX_REGIONAL_ROUTING_MANIFEST_BYTES + 1)),
            reference.copy(bounds = bounds.copy(north = 86.0)),
        )) assertFalse(invalid.isValid())
    }

    @Test
    fun streamIsBoundedCompletionIsLastAndRestartUsesExactVersion() {
        val reference = reference()
        val progress = mutableListOf<Long>()
        var maximumRead = 0
        var closed = false
        val input = object : ByteArrayInputStream(archive) {
            override fun read(bytes: ByteArray, offset: Int, length: Int): Int {
                maximumRead = maxOf(maximumRead, length)
                assertFalse(File(directory(reference), "complete.json").exists())
                return super.read(bytes, offset, length)
            }
            override fun close() { closed = true; super.close() }
        }
        val pack = store.stage(reference, manifest, { input }, onProgress = progress::add)
        assertTrue(closed)
        assertEquals(64 * 1_024, maximumRead)
        assertEquals(archive.size.toLong(), progress.last())
        assertTrue(progress.zipWithNext().all { (before, after) -> after > before })
        assertArrayEquals(archive, pack.tileArchive.readBytes())
        assertArrayEquals(manifest, File(directory(reference), "manifest.json").readBytes())
        assertEquals(reference, RegionalRoutingPackReference.parse(JSONObject(
            File(directory(reference), "complete.json").readText())))
        assertEquals(pack, RegionalRoutingPackStore(root) { Long.MAX_VALUE }.open(reference))
        expect(RegionalPackFailure.UNAVAILABLE) { store.open(reference.copy(buildId = "b".repeat(64))) }
        assertEquals(pack, store.stage(reference, manifest, { error("Completed bytes must be reused") }))
    }

    @Test
    fun failedUpdatePreservesPreviousBytesAndNeverCommits() {
        val previous = reference()
        val previousPack = install(previous)
        val next = previous.copy(buildId = "b".repeat(64))
        val corrupt = archive.copyOf().also { it[it.lastIndex] = 1 }
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) {
            store.stage(next, manifest, { ByteArrayInputStream(corrupt) })
        }
        assertFalse(directory(next).exists())
        assertEquals(previousPack, store.open(previous))
        assertArrayEquals(archive, previousPack.tileArchive.readBytes())
        expect(RegionalPackFailure.UNAVAILABLE) { store.open(next) }
        assertFalse(directory(next).parentFile!!.exists())
    }

    @Test
    fun shortLongZeroAndFailedReadsCleanOnlyTheirOwnStage() {
        for ((bytes, expected) in listOf(
            archive.copyOf(archive.size - 1) to RegionalPackFailure.SIZE_MISMATCH,
            archive.copyOf(archive.size + 1) to RegionalPackFailure.SIZE_MISMATCH,
        )) {
            expect(expected) { store.stage(reference(), manifest, { ByteArrayInputStream(bytes) }) }
            assertFalse(directory(reference()).exists())
        }
        for (throws in listOf(false, true)) {
            var closed = false
            val input = object : InputStream() {
                override fun read(): Int = error("Bounded bulk reads expected")
                override fun read(bytes: ByteArray, offset: Int, length: Int): Int {
                    if (throws) throw IOException("private fixture URL must not escape")
                    return 0
                }
                override fun close() { closed = true }
            }
            expect(RegionalPackFailure.TRANSFER_FAILED) { store.stage(reference(), manifest, { input }) }
            assertTrue(closed)
            assertFalse(directory(reference()).exists())
        }
    }

    @Test
    fun cancellationBeforeDuringAndAfterTransferNeverCommits() {
        expect(RegionalPackFailure.CANCELLED) {
            store.stage(reference(), manifest, { error("Pre-cancelled source") }, cancelled = { true })
        }
        assertFalse(root.exists())
        for (threshold in listOf(1L, archive.size.toLong())) {
            var cancelled = false
            expect(RegionalPackFailure.CANCELLED) {
                store.stage(reference(), manifest, { ByteArrayInputStream(archive) },
                    cancelled = { cancelled }, onProgress = { if (it >= threshold) cancelled = true })
            }
            assertFalse(directory(reference()).exists())
        }
        install(reference())
        var checks = 0
        expect(RegionalPackFailure.CANCELLED) { store.open(reference(), cancelled = { ++checks >= 4 }) }
        assertTrue(File(directory(reference()), "complete.json").isFile)
    }

    @Test
    fun manifestMustMatchHashIdentityBoundsVersionAndBothAccessModesBeforeTransfer() {
        val reference = reference()
        expect(RegionalPackFailure.SIZE_MISMATCH) {
            store.stage(reference, manifest + 0, { error("Source must not open") })
        }
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) {
            store.stage(reference.copy(manifest = reference.manifest.copy(sha256 = "0".repeat(64))),
                manifest, { error("Source must not open") })
        }
        for (changed in listOf(
            JSONObject(String(manifest)).put("pack_id", "different"),
            JSONObject(String(manifest)).put("engine_version", "4.0.0"),
            JSONObject(String(manifest)).put("access_modes", JSONArray(listOf("foot"))),
            JSONObject(String(manifest)).put("schema_version", 1).apply { remove("access_modes") },
            JSONObject(String(manifest)).put("bounds", JSONObject().put("west", 0).put("south", 48).put("east", 2).put("north", 49)),
        )) {
            val bytes = changed.toString().toByteArray()
            expect(RegionalPackFailure.UNSUPPORTED) {
                store.stage(reference.copy(manifest = identity(bytes)), bytes, { error("Source must not open") })
            }
        }
        assertFalse(root.exists())
    }

    @Test
    fun matchingHashDoesNotMakeAnUnsupportedArchiveValid() {
        val invalid = ByteArray(512)
        expect(RegionalPackFailure.INVALID_ARCHIVE) {
            store.stage(reference().copy(archive = identity(invalid)), manifest, { ByteArrayInputStream(invalid) })
        }
        assertFalse(directory(reference()).exists())
    }

    @Test
    fun storedCorruptionAndMissingCompletionRemainUnavailable() {
        val reference = reference()
        install(reference)
        val directory = directory(reference)
        val completion = File(directory, "complete.json")
        completion.delete()
        expect(RegionalPackFailure.INCOMPLETE) { store.open(reference) }
        expect(RegionalPackFailure.INCOMPLETE) { install(reference) }
        completion.writeText(reference.toJson().toString())
        val archiveFile = File(directory, "valhalla_tiles.tar")
        archiveFile.writeBytes(archive.copyOf().also { it[it.lastIndex] = 1 })
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) { store.open(reference) }
        archiveFile.writeBytes(archive)
        File(directory, "manifest.json").writeBytes(manifest.copyOf().also { it[0] = 0 })
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) { store.open(reference) }
        store.remove(reference)
        assertFalse(directory.exists())
        install(reference)
    }

    @Test
    fun processInterruptedPartialDataNeedsExplicitRemovalBeforeRetry() {
        val reference = reference()
        val directory = directory(reference).apply { mkdirs() }
        File(directory, "valhalla_tiles.tar.part").writeText("partial")
        expect(RegionalPackFailure.INCOMPLETE) { install(reference) }
        assertEquals("partial", File(directory, "valhalla_tiles.tar.part").readText())
        store.remove(reference)
        install(reference)
        assertTrue(File(directory, "complete.json").isFile)
        val empty = reference.copy(buildId = "b".repeat(64))
        directory(empty).parentFile!!.mkdirs()
        store.remove(empty)
        assertFalse(directory(empty).parentFile!!.exists())
        assertTrue(File(directory, "complete.json").isFile)
    }

    @Test
    fun staleIdentityCannotOpenOverwriteOrRemoveCompletedVersion() {
        val reference = reference()
        install(reference)
        val stale = reference.copy(archive = reference.archive.copy(sha256 = "0".repeat(64)))
        expect(RegionalPackFailure.IDENTITY_MISMATCH) { store.open(stale) }
        expect(RegionalPackFailure.IDENTITY_MISMATCH) { install(stale) }
        expect(RegionalPackFailure.IDENTITY_MISMATCH) { store.remove(stale) }
        assertArrayEquals(archive, store.open(reference).tileArchive.readBytes())
        store.remove(reference)
        store.remove(reference)
        assertFalse(File(root, reference.regionId).exists())
    }

    @Test
    fun storageLimitsAreIndependentOfBrowserAndOldVersionsRemainIntact() {
        val reference = reference()
        expect(RegionalPackFailure.INSUFFICIENT_STORAGE) {
            RegionalRoutingPackStore(root) { archive.size.toLong() }.stage(reference, manifest, { error("No space") })
        }
        assertFalse(directory(reference).exists())
        install(reference)
        install(reference.copy(buildId = "b".repeat(64)))
        expect(RegionalPackFailure.STORAGE_LIMIT) { install(reference.copy(buildId = "c".repeat(64))) }
        for (index in 1..7) install(reference.copy(regionId = "region-$index"))
        expect(RegionalPackFailure.STORAGE_LIMIT) { install(reference.copy(regionId = "region-8")) }
        assertArrayEquals(archive, store.open(reference).tileArchive.readBytes())
    }

    @Test
    fun directoryScanIsBoundedEvenForUnrecognizedEntries() {
        root.mkdirs()
        repeat(64) { File(root, "extra-$it").writeText("") }
        expect(RegionalPackFailure.STORAGE_LIMIT) { install(reference()) }
        assertFalse(directory(reference()).exists())
    }

    @Test
    fun allocationRunsBeforeTransferAndPreallocatedBytesCannotHideAShortRead() {
        var allocated = false
        val reserved = RegionalRoutingPackStore(root, prepareArchive = { output, bytes ->
            assertEquals(reference().archive.byteSize, bytes)
            // Model allocateBytes extending the new file with zeros. Network
            // accounting must still reject a short body despite its full size.
            output.channel.position(bytes - 1)
            output.write(0)
            output.channel.position(0)
            allocated = true
        }, availableBytes = { Long.MAX_VALUE })
        expect(RegionalPackFailure.SIZE_MISMATCH) {
            reserved.stage(reference(), manifest, {
                assertTrue(allocated)
                ByteArrayInputStream(archive.copyOf(archive.size - 512))
            })
        }
        assertFalse(directory(reference()).exists())
        val failed = RegionalRoutingPackStore(root, prepareArchive = { _, _ ->
            throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
        }, availableBytes = { Long.MAX_VALUE })
        expect(RegionalPackFailure.STORAGE_UNAVAILABLE) {
            failed.stage(reference(), manifest, { error("Allocation failure must not open the network") })
        }
        assertFalse(directory(reference()).exists())
    }

    @Test
    fun symlinkCannotImportOrDeleteOutsideFiles() {
        val reference = reference()
        val outside = File(temporary, "outside").apply { mkdir() }
        val sentinel = File(outside, "sentinel").apply { writeText("preserve") }
        root.mkdirs()
        Files.createSymbolicLink(File(root, reference.regionId).toPath(), outside.toPath())
        expect(RegionalPackFailure.STORAGE_UNAVAILABLE) { install(reference) }
        expect(RegionalPackFailure.STORAGE_UNAVAILABLE) { store.remove(reference) }
        Files.delete(File(root, reference.regionId).toPath())
        install(reference)
        Files.createSymbolicLink(File(directory(reference), "extra-link").toPath(), outside.toPath())
        store.remove(reference)
        assertEquals("preserve", sentinel.readText())
    }

    @Test
    fun separateStoreInstancesCannotMutateSameNativeRootConcurrently() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val executor = Executors.newSingleThreadExecutor()
        val previous = reference()
        install(previous)
        val next = previous.copy(buildId = "b".repeat(64))
        try {
            val pending = executor.submit<RoutingPack> {
                store.stage(next, manifest, {
                    entered.countDown()
                    check(release.await(5, TimeUnit.SECONDS))
                    ByteArrayInputStream(archive)
                })
            }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val other = RegionalRoutingPackStore(root) { Long.MAX_VALUE }
            expect(RegionalPackFailure.BUSY) { other.remove(previous) }
            expect(RegionalPackFailure.BUSY) { other.stage(next, manifest, { error("Busy source") }) }
            // Completed immutable data remains readable during unrelated staging.
            assertArrayEquals(archive, other.open(previous).tileArchive.readBytes())
            release.countDown()
            assertEquals(next.packId, pending.get(5, TimeUnit.SECONDS).packId)
        } finally {
            release.countDown()
            executor.shutdownNow()
        }
    }

    private fun reference() = RegionalRoutingPackReference(
        regionId = "test-region", buildId = "a".repeat(64), packId = "test-region-v1",
        bounds = bounds, manifest = identity(manifest), archive = identity(archive),
    )

    private fun identity(bytes: ByteArray) = RegionalFileIdentity(bytes.size.toLong(),
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })

    private fun directory(reference: RegionalRoutingPackReference) =
        File(root, "${reference.regionId}/${reference.buildId}/${reference.packId}")

    private fun install(reference: RegionalRoutingPackReference) =
        store.stage(reference, manifest, { ByteArrayInputStream(archive) })

    private fun expect(code: RegionalPackFailure, action: () -> Any?) {
        try {
            action()
            throw AssertionError("Expected ${code.wireValue}")
        } catch (error: RegionalPackException) {
            assertEquals(code, error.code)
            assertEquals(code.wireValue, error.message)
            assertNull(error.cause)
        }
    }
}
