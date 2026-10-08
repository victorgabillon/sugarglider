package io.github.victorgabillon.sugarglider

import org.json.JSONObject

/** Envelopes carry unvalidated text, never canonical route or participant authority. */
internal object ExternalItineraryProtocol {
    fun draft(requestId: String, draft: ExternalItineraryIntentParser.Pending): String =
        envelope(requestId, "external_itinerary_draft")
            .put("text", draft.rawText).put("source_kind", draft.sourceKind.wireValue).toString()

    fun stateReply(requestId: String, open: Boolean): String =
        envelope(requestId, "itinerary_dialog_state_result").put("open", open).toString()

    fun back(requestId: String): String = envelope(requestId, "itinerary_dialog_back").toString()

    private fun envelope(requestId: String, type: String): JSONObject = JSONObject()
        .put("schema_version", 1).put("request_id", requestId).put("type", type)
}
