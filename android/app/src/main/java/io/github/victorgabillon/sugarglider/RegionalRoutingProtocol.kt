package io.github.victorgabillon.sugarglider

import org.json.JSONObject

internal object RegionalRoutingProtocol {
    private val base = setOf("schema_version", "request_id", "type", "operation_id")

    fun parse(value: JSONObject, requestId: String, pageNonce: String): BridgeRequest? {
        val operationId = value.opt("operation_id") as? String ?: return null
        if (!RegionalRoutingOperations.validOperationId(operationId)) return null
        val type = value.optString("type")
        if (type == "regional_routing_remove_region") {
            if (value.keys().asSequence().toSet() != base + "region_id") return null
            val regionId = value.opt("region_id") as? String ?: return null
            val command = RegionalRoutingRegionRemoval(operationId, regionId)
            return command.takeIf { it.isValid() }?.let { BridgeRequest.RegionalWork(requestId, pageNonce, it) }
        }
        if (type == "regional_routing_remove_version") {
            if (value.keys().asSequence().toSet() != base + "regional_version") return null
            val version = RegionalRoutingVersion.parse(value.optJSONObject("regional_version")) ?: return null
            return BridgeRequest.RegionalWork(requestId, pageNonce, RegionalRoutingVersionRemoval(operationId, version))
        }
        if (type in setOf("regional_routing_status", "regional_routing_cancel")) {
            if (value.keys().asSequence().toSet() != base) return null
            return BridgeRequest.RegionalStatus(requestId, pageNonce, operationId, type == "regional_routing_cancel")
        }
        val action = when (type) {
            "regional_routing_inspect" -> RegionalRoutingAction.INSPECT
            "regional_routing_install" -> RegionalRoutingAction.INSTALL
            "regional_routing_remove" -> RegionalRoutingAction.REMOVE
            else -> return null
        }
        val expected = base + "regional_reference" + if (action == RegionalRoutingAction.INSTALL) setOf("manifest_url") else emptySet()
        if (value.keys().asSequence().toSet() != expected) return null
        val reference = RegionalRoutingPackReference.parse(value.optJSONObject("regional_reference")) ?: return null
        val url = if (action == RegionalRoutingAction.INSTALL) {
            val source = value.opt("manifest_url") as? String ?: return null
            // The downloader validates the configured HTTPS/development policy.
            if (source.length !in 1..2_048) return null
            source
        } else null
        return BridgeRequest.RegionalWork(requestId, pageNonce,
            RegionalRoutingCommand(operationId, action, reference, url))
    }

    fun reply(requestId: String, status: RegionalRoutingOperationStatus): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", requestId)
        .put("type", "regional_routing_result")
        .put("operation_id", status.operationId)
        .put("state", status.state)
        .put("received_bytes", status.receivedBytes)
        .put("total_bytes", status.totalBytes)
        .put("code", status.code?.wireValue ?: JSONObject.NULL)
        .toString()
}
