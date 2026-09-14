package io.github.victorgabillon.sugarglider

import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RegionalRoutingRepositoryTest {
    private val reference = RegionalRoutingPackReference("fixture", "a".repeat(64), "fixture-routing",
        RoutingPackBounds(1.0, 48.0, 2.0, 49.0), RegionalFileIdentity(270, "b".repeat(64)),
        RegionalFileIdentity(512, "c".repeat(64)))
    private val pack = RoutingPack(RoutingPackManifest(2, reference.packId, "valhalla", "3.6.3",
        reference.bounds, LocalRouteAccessMode.entries), File("synthetic-unused-path"), 512, 0)

    @Test
    fun leaseCoversTheCompleteNativeCallbackAndBlocksStaleSamePathRemoval() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val removed = mutableListOf<RegionalRoutingPackReference>()
        val repository = RegionalRoutingRepository({ assertEquals(reference, it); pack }, removed::add, {}, {})
        val executor = Executors.newSingleThreadExecutor()
        try {
            val pending = executor.submit<String> {
                repository.withPack(reference) {
                    assertEquals(pack, it); entered.countDown(); check(release.await(5, TimeUnit.SECONDS)); "completed"
                }
            }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            busy { repository.remove(reference) }
            busy { repository.remove(reference.copy(archive = reference.archive.copy(sha256 = "0".repeat(64)))) }
            val other = reference.copy(buildId = "d".repeat(64))
            repository.remove(other)
            assertEquals(listOf(other), removed)
            release.countDown()
            assertEquals("completed", pending.get(5, TimeUnit.SECONDS))
            repository.remove(reference)
            assertEquals(listOf(other, reference), removed)
        } finally { release.countDown(); executor.shutdownNow() }
    }

    @Test
    fun failedOpenAndFailedNativeWorkReleaseTheirLease() {
        var failOpen = true
        var removals = 0
        val repository = RegionalRoutingRepository({
            if (failOpen) throw RegionalPackException(RegionalPackFailure.UNAVAILABLE)
            pack
        }, { removals++ }, {}, {})
        try { repository.withPack(reference) { error("Failed open must not call native work") } }
        catch (error: RegionalPackException) { assertEquals(RegionalPackFailure.UNAVAILABLE, error.code) }
        repository.remove(reference)
        failOpen = false
        try { repository.withPack(reference) { throw IllegalStateException("synthetic native failure") } }
        catch (_: IllegalStateException) { /* The caller classifies engine failures. */ }
        repository.remove(reference)
        assertEquals(2, removals)
    }

    @Test
    fun concurrentLeasesAreBoundedAndNoPackIsSelectedOrCachedImplicitly() {
        val opened = mutableListOf<RegionalRoutingPackReference>()
        val repository = RegionalRoutingRepository({ opened += it; pack }, {}, {}, {})
        fun nested(depth: Int) {
            if (depth == 16) { busy { repository.withPack(reference) {} }; return }
            repository.withPack(reference) { nested(depth + 1) }
        }
        nested(0)
        assertEquals(16, opened.size)
        repository.withPack(reference) {}
        assertEquals(17, opened.size)
        assertTrue(opened.all { it == reference })
    }

    @Test
    fun removalAndSubsequentReadHaveOneDefiniteOrder() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        var exists = true
        val opened = CountDownLatch(1)
        val repository = RegionalRoutingRepository({
            opened.countDown()
            if (!exists) throw RegionalPackException(RegionalPackFailure.UNAVAILABLE)
            pack
        }, { entered.countDown(); check(release.await(5, TimeUnit.SECONDS)); exists = false }, {}, {})
        val executor = Executors.newFixedThreadPool(2)
        try {
            val removal = executor.submit { repository.remove(reference) }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val reading = executor.submit<RegionalPackFailure> {
                try { repository.withPack(reference) {}; error("Removed version must remain unavailable") }
                catch (error: RegionalPackException) { error.code }
            }
            assertFalse(opened.await(50, TimeUnit.MILLISECONDS))
            release.countDown(); removal.get(5, TimeUnit.SECONDS)
            assertEquals(RegionalPackFailure.UNAVAILABLE, reading.get(5, TimeUnit.SECONDS))
        } finally { release.countDown(); executor.shutdownNow() }
    }

    private fun busy(action: () -> Unit) {
        try { action(); throw AssertionError("Expected busy") }
        catch (error: RegionalPackException) { assertEquals(RegionalPackFailure.BUSY, error.code) }
    }

    @Test fun versionRecoveryCannotDeleteAnyPackWithAnActiveLease() {
        val removed = mutableListOf<RegionalRoutingVersion>()
        val repository = RegionalRoutingRepository({ pack }, {}, removed::add, {})
        val version = RegionalRoutingVersion(reference.regionId, reference.buildId)
        repository.withPack(reference) {
            busy { repository.removeVersion(version) }
            repository.removeVersion(version.copy(buildId = "d".repeat(64)))
        }
        repository.removeVersion(version)
        assertEquals(listOf(version.copy(buildId = "d".repeat(64)), version), removed)
    }

    @Test fun wholeRegionRecoveryKeepsOtherRegionsAndEveryActiveVersionLease() {
        val removed = mutableListOf<String>()
        val repository = RegionalRoutingRepository({ pack }, {}, {}, removed::add)
        repository.withPack(reference) {
            busy { repository.removeRegion(reference.regionId) }
            repository.removeRegion("another-region")
        }
        repository.removeRegion(reference.regionId)
        assertEquals(listOf("another-region", reference.regionId), removed)
    }
}
