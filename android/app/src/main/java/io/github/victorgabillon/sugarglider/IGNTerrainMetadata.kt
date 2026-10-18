package io.github.victorgabillon.sugarglider

import org.json.JSONObject

/** Private IGN69 components bind full original archives and the offline derivation.
 * Publication remains governed by the separate source-specific operator gate.
 */
internal fun validIgnDerivation(value: JSONObject?): Boolean = try {
    requireNotNull(value)
    require(value.keys().asSequence().toSet() == setOf("algorithm", "sources", "prepared_sha256", "transformation_sha256"))
    require(value.opt("algorithm") == "ign-rge-alti-5m-ign69-skadi-v1")
    for (key in listOf("prepared_sha256", "transformation_sha256")) {
        require((value.opt(key) as? String)?.matches(Regex("[a-f0-9]{64}")) == true)
    }
    val sources = value.getJSONObject("sources")
    require(sources.keys().asSequence().toSet() == setOf("schema_version", "product", "horizontal_crs", "vertical_crs", "surface", "license_url", "files"))
    require(sources.opt("schema_version") == 1 && sources.opt("product") == "IGN-RGE-ALTI-5M")
    require(sources.opt("horizontal_crs") == "EPSG:2154" && sources.opt("vertical_crs") == "EPSG:5720")
    require(sources.opt("surface") == "DTM" && sources.opt("license_url") == "https://www.etalab.gouv.fr/licence-ouverte-open-licence/")
    val files = sources.getJSONArray("files")
    require(files.length() in 1..24)
    val departments = mutableSetOf<String>()
    for (index in 0 until files.length()) {
        val file = files.getJSONObject(index)
        require(file.keys().asSequence().toSet() == setOf("filename", "url", "byte_size", "sha256", "acquired_at", "last_modified", "etag", "version_id"))
        val filename = file.getString("filename")
        require(filename.matches(Regex("RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D[0-9]{3}_[0-9]{4}-[0-9]{2}-[0-9]{2}\\.7z")))
        java.time.LocalDate.parse(filename.removeSuffix(".7z").takeLast(10))
        require(departments.add(filename.split('_')[5]))
        require(file.opt("url") == "https://data.geopf.fr/telechargement/download/RGEALTI/${filename.removeSuffix(".7z")}/$filename")
        require(file.opt("sha256") is String && file.getString("sha256").matches(Regex("[a-f0-9]{64}")))
        val size = file.opt("byte_size")
        require((size is Int || size is Long) && (size as Number).toLong() in 1..1_000_000_000L)
        require(file.opt("acquired_at") is String)
        val acquired = file.getString("acquired_at")
        require(acquired.length in 20..40)
        java.time.OffsetDateTime.parse(acquired)
        for (key in listOf("last_modified", "etag", "version_id")) require(file.isNull(key) || file.opt(key) is String)
    }
    true
} catch (_: Exception) { false }
