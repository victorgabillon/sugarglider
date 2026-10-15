package io.github.victorgabillon.sugarglider

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Bounded random reads: validate indexed TAR and actual 3.9.1 tile headers. */
internal fun validV2ValhallaArchive(file: File): Boolean = try {
    RandomAccessFile(file, "r").use { archive ->
        check(archive.length() >= 2_048 && archive.length() % 512L == 0L)
        var offset = 0L
        var indexOffset = -1L
        var indexEntries = 0L
        var tiles = 0L
        var records = 0
        val names = mutableSetOf<String>()
        while (offset + 512 <= archive.length()) {
            check(++records <= 200_002)
            archive.seek(offset)
            val header = ByteArray(512)
            archive.readFully(header)
            if (header.all { it == 0.toByte() }) break
            fun text(start: Int, length: Int): String = header.copyOfRange(start, start + length)
                .toString(Charsets.US_ASCII).substringBefore('\u0000').trim()
            fun octal(start: Int, length: Int): Long = text(start, length).ifEmpty { "0" }.toLong(8)
            check(text(257, 5) == "ustar" && text(345, 155).isEmpty())
            check(octal(108, 8) == 0L && octal(116, 8) == 0L && octal(136, 12) == 0L)
            val checksum = header.indices.sumOf { if (it in 148..155) 32 else header[it].toInt() and 255 }
            check(octal(148, 8) == checksum.toLong())
            val size = octal(124, 12)
            val data = offset + 512
            check(size > 0 && size <= archive.length() - data)
            val name = text(0, 100).removePrefix("./")
            val kind = header[156].toInt().toChar()
            if (kind == 'x' || kind == 'g') {
                check(size == 11L)
                val metadata = ByteArray(11)
                archive.readFully(metadata)
                check(metadata.toString(Charsets.US_ASCII) == "11 mtime=0\n")
            } else {
                check(kind == '0' || kind == '\u0000')
                check(names.add(name))
                if (name == "index.bin") {
                    check(tiles == 0L && indexOffset < 0 && size % 16L == 0L && size / 16 in 1..100_000)
                    indexOffset = data
                    indexEntries = size / 16
                } else {
                    check(indexOffset >= 0 && tiles < indexEntries)
                    check(Regex("[0-3]/(?:[0-9]{3}/)*[0-9]{3}\\.gph").matches(name) && size >= 272)
                    val tileId = (name.substringAfter('/').removeSuffix(".gph").replace("/", "").toLong() shl 3) or
                        name.substringBefore('/').toLong()
                    archive.seek(indexOffset + tiles * 16)
                    val bytes = ByteArray(16)
                    archive.readFully(bytes)
                    val entry = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
                    check(entry.long == data && (entry.int.toLong() and 0xffffffffL) == tileId &&
                        (entry.int.toLong() and 0xffffffffL) == size)
                    archive.seek(data)
                    val tile = ByteArray(32)
                    archive.readFully(tile)
                    val identity = ByteBuffer.wrap(tile).order(ByteOrder.LITTLE_ENDIAN).long
                    check(identity and (1L shl 62) != 0L)
                    check(identity and ((1L shl 46) - 1) == tileId)
                    check(tile.copyOfRange(16, 32).toString(Charsets.US_ASCII).substringBefore('\u0000') == "3.9.1")
                    tiles++
                }
            }
            offset = data + ((size + 511) / 512) * 512
        }
        check(tiles == indexEntries && tiles > 0)
        true
    }
} catch (_: Exception) { false }
