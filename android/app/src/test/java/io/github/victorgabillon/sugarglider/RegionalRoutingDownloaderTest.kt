package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.nio.file.Files
import java.security.MessageDigest
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

class RegionalRoutingDownloaderTest {
    private lateinit var temporary: File
    private lateinit var store: RegionalRoutingPackStore
    private val connections = mutableListOf<FakeConnection>()
    private var configure: (FakeConnection) -> Unit = {}
    private val archive = ByteArray(128 * 1_024 + 512).also {
        "index.bin".toByteArray().copyInto(it)
        "ustar".toByteArray().copyInto(it, 257)
    }
    private val manifest = JSONObject().put("schema_version", 2).put("pack_id", "fixture-routing")
        .put("engine", "valhalla").put("engine_version", "3.6.3")
        .put("access_modes", JSONArray(listOf("foot", "bicycle")))
        .put("bounds", JSONObject().put("west", 1.0).put("south", 48.0).put("east", 2.0).put("north", 49.0))
        .toString().toByteArray()
    private val reference = RegionalRoutingPackReference("fixture", "a".repeat(64), "fixture-routing",
        RoutingPackBounds(1.0, 48.0, 2.0, 49.0), identity(manifest), identity(archive))
    private val source = "https://packs.example/regions/fixture/manifest.json"
    private val factory = RegionalConnectionFactory { url ->
        FakeConnection(url, if (url.path.endsWith("/manifest.json")) manifest else archive)
            .also { configure(it); connections += it }
    }

    @Before
    fun setup() {
        temporary = Files.createTempDirectory("regional-download-").toFile()
        store = RegionalRoutingPackStore(File(temporary, "native-regions")) { Long.MAX_VALUE }
    }

    @After
    fun cleanup() { temporary.deleteRecursively() }

    @Test
    fun staticDirectoryUrlsAreCanonicalAndCannotCarryAuthorityOrAmbiguousPaths() {
        val location = requireNotNull(RegionalDownloadLocation.parse(source))
        assertEquals("https://packs.example/regions/fixture/routing/manifest.json", location.manifest.toString())
        assertEquals("https://packs.example/regions/fixture/routing/valhalla_tiles.tar", location.archive.toString())
        assertEquals("https://packs.example/routing/manifest.json",
            requireNotNull(RegionalDownloadLocation.parse("https://PACKS.EXAMPLE:443/manifest.json")).manifest.toString())
        for (invalid in listOf(
            "https://user:secret@packs.example/manifest.json", "$source?token=fixture", "$source#secret",
            "file:///tmp/manifest.json", "http://packs.example/manifest.json", " $source",
            "https://packs.example/../manifest.json", "https://packs.example/./manifest.json",
            "https://packs.example/%2e%2e/manifest.json", "https://packs.example//manifest.json",
            "https://packs.example/manifest.json/extra", "https://packs.example/manifest.txt",
            "https://packs.example/a%2fb/manifest.json", "https://packs.example/" + "x".repeat(2048) + "/manifest.json",
        )) assertNull(invalid, RegionalDownloadLocation.parse(invalid))
        assertNull(RegionalDownloadLocation.parse("http://127.0.0.1:8000/manifest.json"))
        assertTrue(RegionalDownloadLocation.parse("http://127.0.0.1:8000/manifest.json", true) != null)
        assertNull(RegionalDownloadLocation.parse("http://packs.example/manifest.json", true))
    }

    @Test
    fun downloadUsesOnlyTwoDeclaredFilesAndStrictUnauthenticatedTransportSettings() {
        val progress = mutableListOf<Long>()
        val result = downloader().install(reference, source, onProgress = progress::add)
        assertArrayEquals(archive, result.tileArchive.readBytes())
        assertEquals(archive.size.toLong(), progress.last())
        assertEquals(listOf("/regions/fixture/routing/manifest.json", "/regions/fixture/routing/valhalla_tiles.tar"),
            connections.map { it.url.path })
        for (connection in connections) {
            assertEquals("GET", connection.requestMethod)
            assertFalse(connection.instanceFollowRedirects)
            assertFalse(connection.useCaches)
            assertFalse(connection.doOutput)
            assertEquals(15_000, connection.connectTimeout)
            assertEquals(15_000, connection.readTimeout)
            assertEquals(mapOf("Accept" to listOf("application/octet-stream"), "Accept-Encoding" to listOf("identity"), "Cookie" to listOf("")), connection.requestProperties)
            assertTrue(connection.closed)
            assertTrue(connection.disconnected)
        }
        val before = connections.size
        assertEquals(result, downloader().install(reference, source))
        assertEquals(before, connections.size)
    }

    @Test
    fun rejectionAndPreCancellationMakeNoConnection() {
        expect(RegionalPackFailure.INVALID_SOURCE) { downloader().install(reference, "$source?token=fixture") }
        expect(RegionalPackFailure.INVALID_REFERENCE) { downloader().install(reference.copy(regionId = "../outside"), source) }
        expect(RegionalPackFailure.CANCELLED) { downloader().install(reference, source, cancelled = { true }) }
        assertTrue(connections.isEmpty())
    }

    @Test
    fun redirectsPartialResponsesEncodingAndWrongLengthFailBeforeOpeningBody() {
        val mutations: List<Pair<(FakeConnection) -> Unit, RegionalPackFailure>> = listOf(
            { connection: FakeConnection -> connection.status = 302 } to RegionalPackFailure.TRANSFER_FAILED,
            { connection: FakeConnection -> connection.status = 206 } to RegionalPackFailure.TRANSFER_FAILED,
            { connection: FakeConnection -> connection.status = 401 } to RegionalPackFailure.TRANSFER_FAILED,
            { connection: FakeConnection -> connection.encoding = "gzip" } to RegionalPackFailure.ENCODED_TRANSFER,
            { connection: FakeConnection -> connection.declaredLength = "1" } to RegionalPackFailure.SIZE_MISMATCH,
            { connection: FakeConnection -> connection.declaredLength = "not-a-size" } to RegionalPackFailure.SIZE_MISMATCH,
        )
        for ((mutation, failure) in mutations) {
            configure = mutation
            expect(failure) { downloader().install(reference, source) }
            assertFalse(connections.last().bodyOpened)
            assertTrue(connections.last().disconnected)
        }
    }

    @Test
    fun absentLengthIsAllowedButActualShortAndLongManifestBodiesAreRejected() {
        for (length in listOf(manifest.size - 1, manifest.size + 1)) {
            configure = { it.declaredLength = null; it.bytes = manifest.copyOf(length) }
            expect(RegionalPackFailure.SIZE_MISMATCH) { downloader().install(reference, source) }
            assertTrue(connections.last().closed && connections.last().disconnected)
        }
        configure = { it.declaredLength = null }
        assertEquals(reference.packId, downloader().install(reference, source).packId)
    }

    @Test
    fun manifestHashFailureNeverStartsArchiveAndArchiveFailurePreservesPreviousVersion() {
        val previous = store.stage(reference, manifest, { ByteArrayInputStream(archive) })
        val next = reference.copy(buildId = "b".repeat(64))
        configure = { if (it.url.path.endsWith("manifest.json")) it.bytes = manifest.copyOf().also { b -> b[0] = 0 } }
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) { downloader().install(next, source) }
        assertEquals(1, connections.size)
        configure = { if (it.url.path.endsWith(".tar")) it.bytes = archive.copyOf().also { b -> b[b.lastIndex] = 1 } }
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) { downloader().install(next, source) }
        assertArrayEquals(archive, store.open(reference).tileArchive.readBytes())
        assertEquals(previous, store.open(reference))
        assertTrue(connections.all { it.disconnected })
    }

    @Test
    fun cancellationDuringArchiveAndSocketTimeoutKeepFailureCodesGeneric() {
        var cancel = false
        expect(RegionalPackFailure.CANCELLED) {
            downloader().install(reference, source, cancelled = { cancel }, onProgress = { cancel = true })
        }
        assertTrue(connections.all { it.closed && it.disconnected })
        configure = { it.readFailure = SocketTimeoutException("precise private fixture detail") }
        expect(RegionalPackFailure.TRANSFER_TIMEOUT) { downloader().install(reference, source) }
        configure = { it.readFailure = IOException("secret URL must not escape") }
        expect(RegionalPackFailure.TRANSFER_FAILED) { downloader().install(reference, source) }
        assertTrue(connections.all { it.disconnected })
    }

    @Test
    fun elapsedDeadlineIsCheckedAfterReadAndBeforeCompletion() {
        var now = 0L
        configure = { connection -> connection.afterRead = { now = 30 * 60 * 1_000_000_000L } }
        expect(RegionalPackFailure.TRANSFER_TIMEOUT) {
            RegionalRoutingDownloader(store, factory, nanoTime = { now }).install(reference, source)
        }
        assertEquals(1, connections.size)
        assertTrue(connections[0].closed && connections[0].disconnected)
        expect(RegionalPackFailure.UNAVAILABLE) { store.open(reference) }
    }

    @Test
    fun corruptedCompletedArchiveIsNotSilentlyOverwrittenOrDownloadedAgain() {
        val pack = store.stage(reference, manifest, { ByteArrayInputStream(archive) })
        pack.tileArchive.writeBytes(archive.copyOf().also { it[it.lastIndex] = 1 })
        expect(RegionalPackFailure.CHECKSUM_MISMATCH) { downloader().install(reference, source) }
        assertTrue(connections.isEmpty())
    }

    private fun downloader() = RegionalRoutingDownloader(store, factory)

    private fun identity(bytes: ByteArray) = RegionalFileIdentity(bytes.size.toLong(),
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })

    private fun expect(code: RegionalPackFailure, action: () -> Any?) {
        try { action(); throw AssertionError("Expected ${code.wireValue}") }
        catch (error: RegionalPackException) {
            assertEquals(code, error.code); assertEquals(code.wireValue, error.message); assertNull(error.cause)
        }
    }

    private class FakeConnection(url: URL, var bytes: ByteArray) : HttpURLConnection(url) {
        var status = 200
        var encoding: String? = null
        var declaredLength: String? = bytes.size.toString()
        var readFailure: IOException? = null
        var afterRead: () -> Unit = {}
        var disconnected = false
        var bodyOpened = false
        var closed = false
        override fun connect() {}
        override fun disconnect() { disconnected = true }
        override fun usingProxy(): Boolean = false
        override fun getResponseCode(): Int = status
        override fun getHeaderField(name: String): String? = when (name) {
            "Content-Encoding" -> encoding
            "Content-Length" -> declaredLength
            else -> null
        }
        override fun getInputStream(): InputStream {
            bodyOpened = true
            return object : ByteArrayInputStream(bytes) {
                override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                    readFailure?.let { throw it }
                    val result = super.read(buffer, offset, length); afterRead(); return result
                }
                override fun close() { closed = true; super.close() }
            }
        }
    }
}
