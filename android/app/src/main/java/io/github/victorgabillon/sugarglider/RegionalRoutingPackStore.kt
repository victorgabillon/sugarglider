package io.github.victorgabillon.sugarglider

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.nio.channels.OverlappingFileLockException
import java.nio.file.FileVisitResult
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.SimpleFileVisitor
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.BasicFileAttributes
import java.security.MessageDigest
import org.json.JSONObject

internal enum class RegionalPackFailure(val wireValue: String) {
    INVALID_REFERENCE("invalid_regional_routing_reference"),
    UNAVAILABLE("regional_routing_unavailable"),
    INCOMPLETE("regional_routing_incomplete"),
    BUSY("regional_routing_busy"),
    CANCELLED("regional_install_cancelled"),
    SIZE_MISMATCH("regional_size_mismatch"),
    CHECKSUM_MISMATCH("regional_checksum_mismatch"),
    IDENTITY_MISMATCH("regional_identity_mismatch"),
    UNSUPPORTED("regional_routing_unsupported"),
    INVALID_ARCHIVE("regional_routing_invalid"),
    INSUFFICIENT_STORAGE("regional_insufficient_storage"),
    STORAGE_UNAVAILABLE("regional_storage_unavailable"),
    STORAGE_LIMIT("regional_storage_limit"),
    TRANSFER_FAILED("regional_transfer_failed"),
    INVALID_SOURCE("invalid_regional_source"),
    TRANSFER_TIMEOUT("regional_transfer_timeout"),
    ENCODED_TRANSFER("regional_encoded_download"),
}

internal class RegionalPackException(val code: RegionalPackFailure) :
    Exception(code.wireValue)

// This store stages immutable native archives. Only the web coordinator's
// committed reference may be used for planning; directory discovery is not
// activation. The caller supplies a bounded, credential-free download stream.
internal class RegionalRoutingPackStore(
    private val rootDirectory: File,
    private val prepareArchive: (FileOutputStream, Long) -> Unit = { _, _ -> },
    private val availableBytes: () -> Long,
) {
    fun stage(
        reference: RegionalRoutingPackReference,
        manifestBytes: ByteArray,
        archiveSource: () -> InputStream,
        cancelled: () -> Boolean = { false },
        onProgress: (Long) -> Unit = {},
    ): RoutingPack {
        requireReference(reference)
        requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
        requireCondition(manifestBytes.size.toLong() == reference.manifest.byteSize, RegionalPackFailure.SIZE_MISMATCH)
        val manifest = manifestBytes.copyOf()
        verifyBytes(manifest, reference.manifest)
        validateManifest(manifest, reference)
        return mutate {
            val directory = packDirectory(reference, create = false)
            if (directory != null) {
                requireCondition(File(directory, COMPLETION).isFile, RegionalPackFailure.INCOMPLETE)
                return@mutate open(reference, cancelled)
            }
            val free = availableBytes()
            requireCondition(free >= 0, RegionalPackFailure.STORAGE_UNAVAILABLE)
            requireCondition(free >= reference.archive.byteSize + manifest.size + 4_096L,
                RegionalPackFailure.INSUFFICIENT_STORAGE)
            val owned = packDirectory(reference, create = true)
                ?: throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
            var complete = false
            try {
                requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                writeFile(owned, MANIFEST, manifest)
                val part = confinedFile(owned, "$ARCHIVE.part")
                FileOutputStream(part).use { output ->
                    prepareArchive(output, reference.archive.byteSize)
                    output.channel.position(0)
                    requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                    archiveSource().use { input ->
                        val hash = MessageDigest.getInstance("SHA-256")
                        val buffer = ByteArray(READ_BYTES)
                        var count = 0L
                        while (true) {
                            requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                            val length = input.read(buffer)
                            requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                            if (length < 0) break
                            requireCondition(length > 0, RegionalPackFailure.TRANSFER_FAILED)
                            count += length
                            requireCondition(count <= reference.archive.byteSize, RegionalPackFailure.SIZE_MISMATCH)
                            output.write(buffer, 0, length)
                            hash.update(buffer, 0, length)
                            onProgress(count)
                        }
                        requireCondition(count == reference.archive.byteSize, RegionalPackFailure.SIZE_MISMATCH)
                        requireCondition(hex(hash.digest()) == reference.archive.sha256, RegionalPackFailure.CHECKSUM_MISMATCH)
                        output.fd.sync()
                    }
                }
                requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                Files.move(part.toPath(), confinedFile(owned, ARCHIVE).toPath(), StandardCopyOption.ATOMIC_MOVE)
                val pack = RoutingPackRegistry(requireNotNull(owned.parentFile)).installedPacks()
                    .singleOrNull { it.packId == reference.packId }
                    ?: throw RegionalPackException(RegionalPackFailure.INVALID_ARCHIVE)
                requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                writeFile(owned, COMPLETION, reference.toJson().toString().toByteArray(Charsets.UTF_8))
                complete = true
                pack
            } catch (error: Exception) {
                if (cancelled()) throw RegionalPackException(RegionalPackFailure.CANCELLED)
                if (error is RegionalPackException) throw error
                throw RegionalPackException(RegionalPackFailure.TRANSFER_FAILED)
            } finally {
                // A killed process leaves an explicit incomplete directory. An
                // ordinary failure cleans only the directory created by this call.
                if (!complete) runCatching { removeTree(owned); pruneEmptyParents(reference) }
            }
        }
    }

    fun open(
        reference: RegionalRoutingPackReference,
        cancelled: () -> Boolean = { false },
    ): RoutingPack {
        requireReference(reference)
        try {
            requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
            val directory = packDirectory(reference, create = false)
                ?: throw RegionalPackException(RegionalPackFailure.UNAVAILABLE)
            val completion = confinedFile(directory, COMPLETION)
            requireCondition(completion.isFile && completion.length() in 1..MAX_COMPLETION_BYTES,
                RegionalPackFailure.INCOMPLETE)
            val stored = RegionalRoutingPackReference.parse(JSONObject(completion.readText(Charsets.UTF_8)))
            requireCondition(stored == reference, RegionalPackFailure.IDENTITY_MISMATCH)
            val manifest = confinedFile(directory, MANIFEST)
            requireCondition(manifest.isFile && manifest.length() == reference.manifest.byteSize,
                RegionalPackFailure.SIZE_MISMATCH)
            val bytes = manifest.readBytes()
            verifyBytes(bytes, reference.manifest)
            validateManifest(bytes, reference)
            val archive = confinedFile(directory, ARCHIVE)
            requireCondition(archive.isFile && archive.length() == reference.archive.byteSize,
                RegionalPackFailure.SIZE_MISMATCH)
            val hash = MessageDigest.getInstance("SHA-256")
            archive.inputStream().use { input ->
                val buffer = ByteArray(READ_BYTES)
                var count = 0L
                while (true) {
                    requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                    val length = input.read(buffer)
                    requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
                    if (length < 0) break
                    requireCondition(length > 0, RegionalPackFailure.UNAVAILABLE)
                    count += length
                    requireCondition(count <= reference.archive.byteSize, RegionalPackFailure.SIZE_MISMATCH)
                    hash.update(buffer, 0, length)
                }
                requireCondition(count == reference.archive.byteSize, RegionalPackFailure.SIZE_MISMATCH)
            }
            requireCondition(hex(hash.digest()) == reference.archive.sha256, RegionalPackFailure.CHECKSUM_MISMATCH)
            requireCondition(!cancelled(), RegionalPackFailure.CANCELLED)
            return RoutingPackRegistry(requireNotNull(directory.parentFile)).installedPacks()
                .singleOrNull { it.packId == reference.packId }
                ?: throw RegionalPackException(RegionalPackFailure.INVALID_ARCHIVE)
        } catch (error: Exception) {
            if (error is RegionalPackException) throw error
            throw RegionalPackException(RegionalPackFailure.UNAVAILABLE)
        }
    }

    // The coordinator must first deactivate this version under its request lock.
    // A valid different identity is never removed by a stale cleanup operation.
    fun remove(reference: RegionalRoutingPackReference) {
        requireReference(reference)
        mutate {
            val directory = packDirectory(reference, create = false)
            if (directory == null) { pruneEmptyParents(reference); return@mutate }
            val completion = confinedFile(directory, COMPLETION)
            if (completion.isFile && completion.length() in 1..MAX_COMPLETION_BYTES) {
                val stored = runCatching {
                    RegionalRoutingPackReference.parse(JSONObject(completion.readText(Charsets.UTF_8)))
                }.getOrNull()
                requireCondition(stored == null || stored == reference, RegionalPackFailure.IDENTITY_MISMATCH)
            }
            removeTree(directory)
            pruneEmptyParents(reference)
        }
    }

    private fun pruneEmptyParents(reference: RegionalRoutingPackReference) {
        val region = confinedFile(root(), reference.regionId)
        if (!region.isDirectory) return
        val version = confinedFile(region, reference.buildId)
        version.delete() // Only succeeds for an empty version; never recursive.
        region.delete() // Only succeeds after the region has become empty.
    }

    fun removeVersion(version: RegionalRoutingVersion) {
        requireCondition(version.isValid(), RegionalPackFailure.INVALID_REFERENCE)
        mutate {
            val region = confinedFile(root(), version.regionId)
            if (!region.exists()) return@mutate
            requireCondition(region.isDirectory, RegionalPackFailure.STORAGE_UNAVAILABLE)
            val directory = confinedFile(region, version.buildId)
            if (directory.exists()) {
                requireCondition(directory.isDirectory, RegionalPackFailure.STORAGE_UNAVAILABLE)
                requireRemovalTree(directory, 3, MAX_DIRECTORY_ENTRIES)
                removeTree(directory)
            }
            region.delete() // Empty only; another immutable version is retained.
        }
    }

    fun removeRegion(regionId: String) {
        requireCondition(isRoutingPackId(regionId) && !regionId.contains(".."), RegionalPackFailure.INVALID_REFERENCE)
        mutate {
            val region = confinedFile(root(), regionId)
            if (!region.exists()) return@mutate
            requireCondition(region.isDirectory, RegionalPackFailure.STORAGE_UNAVAILABLE)
            requireRemovalTree(region, 4, MAX_DIRECTORY_ENTRIES * MAX_VERSIONS + 1)
            removeTree(region)
        }
    }

    private fun requireRemovalTree(directory: File, depth: Int, maximum: Int) {
        // Validate a bounded tree before any deletion. No symlink is followed.
        var entries = 0
        Files.walkFileTree(directory.toPath(), java.util.EnumSet.noneOf(java.nio.file.FileVisitOption::class.java), depth,
            object : SimpleFileVisitor<Path>() {
                override fun preVisitDirectory(path: Path, attributes: BasicFileAttributes): FileVisitResult {
                    requireCondition(++entries <= maximum, RegionalPackFailure.STORAGE_LIMIT)
                    return FileVisitResult.CONTINUE
                }
                override fun visitFile(path: Path, attributes: BasicFileAttributes): FileVisitResult {
                    requireCondition(++entries <= maximum && !attributes.isDirectory, RegionalPackFailure.STORAGE_LIMIT)
                    return FileVisitResult.CONTINUE
                }
            })
    }

    private fun packDirectory(reference: RegionalRoutingPackReference, create: Boolean): File? {
        val root = root()
        var parent = root
        for ((level, name) in listOf(reference.regionId, reference.buildId, reference.packId).withIndex()) {
            val child = confinedFile(parent, name)
            if (!child.exists()) {
                if (!create) return null
                requireDirectorySlot(parent, level)
                requireCondition(child.mkdir(), RegionalPackFailure.STORAGE_UNAVAILABLE)
            }
            requireCondition(child.isDirectory, RegionalPackFailure.STORAGE_UNAVAILABLE)
            parent = child
        }
        return parent
    }

    private fun requireDirectorySlot(parent: File, level: Int) {
        var scanned = 0
        var directories = 0
        Files.newDirectoryStream(parent.toPath()).use { entries ->
            for (entry in entries) {
                requireCondition(++scanned <= MAX_DIRECTORY_ENTRIES, RegionalPackFailure.STORAGE_LIMIT)
                if (Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS)) directories++
            }
        }
        val maximum = when (level) { 0 -> MAX_REGIONS; 1 -> MAX_VERSIONS; else -> 1 }
        requireCondition(directories < maximum, RegionalPackFailure.STORAGE_LIMIT)
    }

    private fun root(): File {
        if (!rootDirectory.exists()) requireCondition(rootDirectory.mkdirs(), RegionalPackFailure.STORAGE_UNAVAILABLE)
        requireCondition(rootDirectory.isDirectory, RegionalPackFailure.STORAGE_UNAVAILABLE)
        return rootDirectory.canonicalFile
    }

    private fun <T> mutate(action: () -> T): T {
        try {
            val lockFile = confinedFile(root(), ".mutation.lock")
            return FileOutputStream(lockFile, true).channel.use { channel ->
                val lock = try { channel.tryLock() } catch (_: OverlappingFileLockException) { null }
                    ?: throw RegionalPackException(RegionalPackFailure.BUSY)
                lock.use { action() }
            }
        } catch (error: Exception) {
            if (error is RegionalPackException) throw error
            throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
        }
    }

    private fun validateManifest(bytes: ByteArray, reference: RegionalRoutingPackReference) {
        val manifest = RoutingPackManifest.parse(bytes.toString(Charsets.UTF_8), reference.packId)
        requireCondition(manifest != null && manifest.schemaVersion == 2 && manifest.bounds == reference.bounds
            && manifest.accessModes == LocalRouteAccessMode.entries, RegionalPackFailure.UNSUPPORTED)
    }

    private fun verifyBytes(bytes: ByteArray, identity: RegionalFileIdentity) {
        requireCondition(bytes.size.toLong() == identity.byteSize, RegionalPackFailure.SIZE_MISMATCH)
        requireCondition(hex(MessageDigest.getInstance("SHA-256").digest(bytes)) == identity.sha256,
            RegionalPackFailure.CHECKSUM_MISMATCH)
    }

    private fun writeFile(directory: File, name: String, bytes: ByteArray) {
        val part = confinedFile(directory, "$name.part")
        FileOutputStream(part).use { output -> output.write(bytes); output.fd.sync() }
        Files.move(part.toPath(), confinedFile(directory, name).toPath(), StandardCopyOption.ATOMIC_MOVE)
    }

    private fun confinedFile(parent: File, name: String): File {
        val file = File(parent, name)
        requireCondition(file.canonicalFile == file.absoluteFile && !Files.isSymbolicLink(file.toPath()),
            RegionalPackFailure.STORAGE_UNAVAILABLE)
        return file
    }

    private fun requireReference(reference: RegionalRoutingPackReference) {
        requireCondition(reference.isValid(), RegionalPackFailure.INVALID_REFERENCE)
    }

    private fun requireCondition(condition: Boolean, code: RegionalPackFailure) {
        if (!condition) throw RegionalPackException(code)
    }

    private fun removeTree(directory: File) {
        Files.walkFileTree(directory.toPath(), object : SimpleFileVisitor<Path>() {
            override fun visitFile(file: Path, attributes: BasicFileAttributes): FileVisitResult {
                Files.delete(file)
                return FileVisitResult.CONTINUE
            }

            override fun postVisitDirectory(path: Path, error: IOException?): FileVisitResult {
                if (error != null) throw error
                Files.delete(path)
                return FileVisitResult.CONTINUE
            }
        })
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    private companion object {
        const val READ_BYTES = 64 * 1_024
        const val MAX_COMPLETION_BYTES = 4_096L
        const val MAX_DIRECTORY_ENTRIES = 64
        const val MAX_REGIONS = 8
        const val MAX_VERSIONS = 2
        const val MANIFEST = "manifest.json"
        const val ARCHIVE = "valhalla_tiles.tar"
        const val COMPLETION = "complete.json"
    }
}
