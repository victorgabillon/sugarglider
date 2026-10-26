package io.github.victorgabillon.sugarglider

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import org.json.JSONObject
import java.util.Locale

internal enum class AdventureSpeechMode { ON_DEVICE, PLATFORM, UNAVAILABLE }

internal object AdventureSpeechPolicy {
    fun mode(api: Int, onDevice: Boolean, platform: Boolean): AdventureSpeechMode = when {
        api >= 31 && onDevice -> AdventureSpeechMode.ON_DEVICE
        platform -> AdventureSpeechMode.PLATFORM
        else -> AdventureSpeechMode.UNAVAILABLE
    }
    fun language(value: String): Boolean = value.length <= 35 && value.matches(Regex("[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}"))
    fun transcript(value: String?): String? = value?.trim()?.takeIf {
        it.length in 1..8000 && it.none { character -> character.isISOControl() && character !in "\n\r\t" }
    }
    fun reply(requestId: String, status: String, mode: AdventureSpeechMode, text: String? = null): String = JSONObject()
        .put("schema_version", SCHEMA_VERSION).put("request_id", requestId).put("type", "adventure_speech_result")
        .put("status", status).put("mode", mode.name.lowercase()).put("text", text ?: JSONObject.NULL).toString()
}

/** Only editable text is retained. Partial hypotheses replace one another, never accumulate. */
internal class AdventureSpeechTranscript {
    private var confirmed = ""
    private var partial = ""
    fun segment(value: String?): Boolean {
        val text = AdventureSpeechPolicy.transcript(value) ?: return false
        val joined = listOf(confirmed, text).filter(String::isNotEmpty).joinToString(" ")
        if (joined.length > 8000) return false
        confirmed = joined; partial = ""
        return true
    }
    fun partial(value: String?) { partial = AdventureSpeechPolicy.transcript(value).orEmpty() }
    fun finalResult(value: String?): String? = confirmed.ifEmpty { AdventureSpeechPolicy.transcript(value).orEmpty() }.ifEmpty { null }
    fun draft(): String? = AdventureSpeechPolicy.transcript(listOf(confirmed, partial).filter(String::isNotEmpty).joinToString(" "))
        ?: confirmed.ifEmpty { null }
}

/** One explicit, bounded foreground dictation. No audio files, background service or model I/O. */
internal class AdventureSpeechInput(private val activity: Activity, private val visible: () -> Boolean) {
    private enum class Phase { PERMISSION, READY, DISCLOSURE, PLATFORM, LISTENING, FINALIZING }
    private class Operation(val serial: Int, val language: String, val mode: AdventureSpeechMode,
        val complete: (String, AdventureSpeechMode, String?) -> Unit, var phase: Phase) {
        val transcript = AdventureSpeechTranscript()
    }
    private val handler = Handler(Looper.getMainLooper())
    private var active: Operation? = null
    private var serial = 0
    private var recognizer: SpeechRecognizer? = null
    private var disclosure: AlertDialog? = null
    private val timeout = Runnable { active?.let {
        if (it.phase == Phase.LISTENING) stop() else finishDraft(it, "timeout")
    } }

    fun mode(): AdventureSpeechMode {
        val onDevice = Build.VERSION.SDK_INT >= 31 && runCatching { SpeechRecognizer.isOnDeviceRecognitionAvailable(activity) }.getOrDefault(false)
        val platform = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).resolveActivity(activity.packageManager) != null
        return AdventureSpeechPolicy.mode(Build.VERSION.SDK_INT, onDevice, platform)
    }

    fun begin(language: String, requestedMode: AdventureSpeechMode, complete: (String, AdventureSpeechMode, String?) -> Unit) {
        if (!visible() || active != null) { complete(if (active != null) "busy" else "unavailable", mode(), null); return }
        val mode = requestedMode
        val available = when (mode) {
            AdventureSpeechMode.ON_DEVICE -> mode() == AdventureSpeechMode.ON_DEVICE
            AdventureSpeechMode.PLATFORM -> Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).resolveActivity(activity.packageManager) != null
            AdventureSpeechMode.UNAVAILABLE -> false
        }
        if (!available) { complete("unavailable", mode, null); return }
        if (++serial > MAX_SERIAL) { complete("unavailable", mode, null); return }
        val operation = Operation(serial, language, mode, complete, Phase.READY)
        active = operation
        handler.postDelayed(timeout, 60_000)
        when (mode) {
            AdventureSpeechMode.UNAVAILABLE -> finish(operation, "unavailable")
            AdventureSpeechMode.PLATFORM -> {
                operation.phase = Phase.DISCLOSURE
                disclosure = AlertDialog.Builder(activity).setTitle("Use Android speech recognition?")
                    .setMessage("Your configured Android speech service may send audio to its provider. This choice does not require offline processing. The transcription is editable and is not sent to ChatGPT until you choose Generate.")
                    .setPositiveButton("Use speech service") { _, _ -> if (active === operation && visible()) {
                        operation.phase = Phase.PLATFORM
                        try { @Suppress("DEPRECATION") activity.startActivityForResult(intent(operation.language, segmented = false), SPEECH_BASE + operation.serial) }
                        catch (_: Exception) { finish(operation, "unavailable") }
                    } else finish(operation, "cancelled") }
                    .setNegativeButton("Cancel") { _, _ -> finish(operation, "cancelled") }
                    .setOnCancelListener { finish(operation, "cancelled") }.show()
            }
            AdventureSpeechMode.ON_DEVICE -> {
                if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    operation.phase = Phase.PERMISSION
                    activity.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MICROPHONE_BASE + operation.serial)
                } else listen(operation)
            }
        }
    }

    fun permissionResult(requestCode: Int) {
        val operation = active?.takeIf { it.phase == Phase.PERMISSION && requestCode == MICROPHONE_BASE + it.serial } ?: return
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) finish(operation, "permission_denied")
        else { operation.phase = Phase.READY; if (visible()) listen(operation) }
    }
    fun resumed() { active?.takeIf { it.phase == Phase.READY }?.let(::listen) }
    fun paused() {
        // Permission and the explicitly launched platform recognizer own their
        // visible system UI. Our own microphone stops as soon as we lose focus.
        active?.takeIf { it.phase == Phase.LISTENING || it.phase == Phase.FINALIZING || it.phase == Phase.DISCLOSURE }?.let { finish(it, "cancelled") }
    }
    fun activityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        val operation = active?.takeIf { it.phase == Phase.PLATFORM && requestCode == SPEECH_BASE + it.serial } ?: return
        val text = if (resultCode == Activity.RESULT_OK) AdventureSpeechPolicy.transcript(
            data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()) else null
        finish(operation, if (text != null) "completed" else "cancelled", text)
    }
    fun cancel() { active?.let { finish(it, "cancelled") } }
    fun stop() {
        val operation = active ?: return
        if (operation.phase != Phase.LISTENING) {
            if (operation.mode == AdventureSpeechMode.ON_DEVICE && operation.phase != Phase.FINALIZING) finish(operation, "cancelled")
            return
        }
        operation.phase = Phase.FINALIZING
        handler.removeCallbacks(timeout)
        handler.postDelayed(timeout, 3_000)
        try { recognizer?.stopListening() } catch (_: Exception) { finishDraft(operation, "unavailable") }
    }
    private fun finishDraft(operation: Operation, emptyStatus: String) {
        val text = operation.transcript.draft()
        finish(operation, if (text == null) emptyStatus else "partial", text)
    }

    private fun listen(operation: Operation) {
        if (active !== operation || !visible()) return
        if (Build.VERSION.SDK_INT < 31) { finish(operation, "unavailable"); return }
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            finish(operation, "permission_denied"); return
        }
        // Keep the original absolute deadline, including permission/disclosure
        // time, so a delayed system UI cannot outlive the bridge request.
        operation.phase = Phase.LISTENING
        try {
            val created = SpeechRecognizer.createOnDeviceSpeechRecognizer(activity)
            recognizer = created
            created.setRecognitionListener(object : RecognitionListener {
                override fun onResults(results: Bundle?) {
                    if (active !== operation) return
                    val text = operation.transcript.finalResult(recognized(results))
                    if (text == null) finishDraft(operation, "no_match") else finish(operation, "completed", text)
                }
                override fun onSegmentResults(segmentResults: Bundle) {
                    if (active !== operation) return
                    if (!operation.transcript.segment(recognized(segmentResults))) stop()
                }
                override fun onEndOfSegmentedSession() {
                    if (active !== operation) return
                    val text = operation.transcript.finalResult(null)
                    if (text == null) finishDraft(operation, "no_match") else finish(operation, "completed", text)
                }
                override fun onError(error: Int) { if (active === operation) finishDraft(operation, when (error) {
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "permission_denied"
                    SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE, SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> "language_unavailable"
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "no_match"
                    else -> "unavailable"
                }) }
                override fun onReadyForSpeech(params: Bundle?) = Unit
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit
                override fun onPartialResults(partialResults: Bundle?) {
                    if (active === operation) operation.transcript.partial(recognized(partialResults))
                }
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })
            created.startListening(intent(operation.language, segmented = true))
        } catch (_: Exception) { finish(operation, "unavailable") }
    }
    private fun recognized(results: Bundle?): String? = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
    private fun intent(language: String, segmented: Boolean): Intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE, language.ifBlank { Locale.getDefault().toLanguageTag() })
        .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, segmented)
        .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, segmented)
        .also {
            // Request Android's bounded multi-segment mode, rather than fighting
            // its normal single-utterance endpointer with silence overrides.
            // Services may ignore this; a new explicit Speak appends more text.
            if (segmented && Build.VERSION.SDK_INT >= 33) {
                it.putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION, RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS)
                it.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 60_000)
            }
        }

    private fun finish(operation: Operation, status: String, text: String? = null) {
        if (active !== operation) return
        active = null
        handler.removeCallbacks(timeout)
        disclosure?.dismiss(); disclosure = null
        if (operation.phase == Phase.PLATFORM && status != "completed") runCatching { @Suppress("DEPRECATION") activity.finishActivity(SPEECH_BASE + operation.serial) }
        recognizer?.let { runCatching { it.cancel() }; runCatching { it.destroy() } }; recognizer = null
        operation.complete(status, operation.mode, text)
    }
    companion object {
        // Distinct operation codes prevent a cancelled system result from being
        // delivered as a newer utterance. Codes never wrap within an Activity.
        private const val MAX_SERIAL = 8191
        private const val MICROPHONE_BASE = 0x4000
        private const val SPEECH_BASE = 0x6000
        fun handlesPermission(code: Int): Boolean = code in MICROPHONE_BASE + 1..MICROPHONE_BASE + MAX_SERIAL
        fun handlesResult(code: Int): Boolean = code in SPEECH_BASE + 1..SPEECH_BASE + MAX_SERIAL
    }
}
