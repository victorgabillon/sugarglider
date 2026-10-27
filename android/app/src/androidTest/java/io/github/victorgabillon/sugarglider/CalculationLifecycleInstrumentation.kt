package io.github.victorgabillon.sugarglider

import android.app.Instrumentation
import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.webkit.WebView
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONArray
import org.json.JSONObject

/** Opt-in test APK only. No socket, real account read, region install or live inference. */
class CalculationLifecycleInstrumentation : Instrumentation() {
    private var arguments = Bundle()
    override fun onCreate(arguments: Bundle?) { super.onCreate(arguments); this.arguments = arguments ?: Bundle(); start() }
    override fun onStart() {
        val result = Bundle()
        var exitCode = 1
        var restore: (() -> Unit)? = null
        var page: WebView? = null
        var ownedApp: SugargliderApplication? = null
        try {
            check(BuildConfig.DEBUG)
            val fixtureId = arguments.getString("fixture_id").orEmpty()
            require(fixtureId.matches(Regex("[a-z0-9-]{1,64}")))
            val root = File(targetContext.cacheDir, fixtureId).canonicalFile
            require(root.parentFile == targetContext.cacheDir.canonicalFile)
            val fixtureFile = File(root, "calculation.json")
            require(fixtureFile.length() in 1..131_072)
            val fixture = JSONObject(fixtureFile.readText())
            require(!fixture.getBoolean("live_inference_allowed"))
            require(fixture.getBoolean("confirm_proposed_endpoints"))
            val transition = arguments.getString("transition", "foreground")
            require(transition in setOf("foreground", "home_60", "home_180", "lock_180"))
            val delay = fixture.getLong("model_delay_ms").also { require(it in 0..90_000) }
            val proposals = fixture.getJSONArray("proposals").also { require(it.length() == 2) }
            val prompt = fixture.getString("prompt").also { require(it.length in 3..8000) }
            val calls = AtomicInteger()
            val accounts = TestAccounts()
            val connection = ChatGptConnection(accounts, ChatGptHttp(ConnectionFactory { url ->
                when (url.toString()) {
                    ChatGptHttp.MODELS -> FakeReply(url, """{"models":[{"slug":"deterministic","display_name":"Deterministic device test — no live inference","visibility":"list"}]}""", 0, false)
                    ChatGptHttp.RESPONSES -> {
                        val index = calls.getAndIncrement()
                        require(index < 2) { "Model budget exceeded" }
                        val completion = JSONObject().put("type", "response.completed").put("response", JSONObject().put("status", "completed")
                            .put("output", JSONArray().put(JSONObject().put("type", "message").put("role", "assistant").put("status", "completed")
                                .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", proposals.getJSONObject(index).toString()))))))
                        FakeReply(url, "data: $completion\n\n", delay, true)
                    }
                    else -> error("Unexpected endpoint: fake transport never opens a socket")
                }
            }))
            val app = targetContext.applicationContext as SugargliderApplication
            ownedApp = app
            // Replace only this test process's lazy connection; never decrypt or
            // alter the installed account store. Restore the untouched lazy value.
            val field = SugargliderApplication::class.java.getDeclaredField("chatGpt\$delegate").apply { isAccessible = true }
            val original = field.get(app)
            field.set(app, lazyOf(connection))
            restore = {
                connection.cancel()
                val drained = CountDownLatch(1)
                app.chatGptExecutor.execute { drained.countDown() }
                // A queued test command must never acquire the real connection.
                check(drained.await(10, TimeUnit.SECONDS))
                field.set(app, original)
            }
            val activity = startActivitySync(Intent(targetContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            val webField = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
            lateinit var web: WebView
            runOnMainSync { web = webField.get(activity) as WebView }; page = web
            waitUntil(120_000) { evaluate(web, "document.querySelector('#regional-status')?.dataset.state === 'regional_ready'") == "true" }
            // A test cannot silently grant notification permission or install data.
            check(targetContext.getSystemService(android.app.NotificationManager::class.java).areNotificationsEnabled())
            evaluate(web, "(async()=>{const {pwaRuntime}=await import('/static/pwa_runtime.js');globalThis.__calculationSavedBefore=await (await pwaRuntime()).adventures.read();globalThis.__calculationEditorBefore=document.querySelector('#adventure-text').value;globalThis.__calculationBackupReady=true;})()")
            waitUntil(10_000) { evaluate(web, "globalThis.__calculationBackupReady===true") == "true" }
            evaluate(web, "document.querySelector('#plan-with-ai').click();true")
            waitUntil(10_000) { evaluate(web, "document.querySelector('#adventure-model')?.value === 'deterministic'") == "true" }
            evaluate(web, "document.querySelector('#adventure-text').value=${JSONObject.quote(prompt)};document.querySelector('#adventure-text').dispatchEvent(new Event('input'));document.querySelector('#adventure-research').checked=false;document.querySelector('#adventure-refine').checked=true;true")
            waitUntil(10_000) { evaluate(web, "!document.querySelector('#adventure-generate').disabled") == "true" }
            // The fixture explicitly approves only its proposed endpoints. A hard
            // place or unsupported requirement still fails this test for review.
            evaluate(web, "globalThis.__calculationReview=new MutationObserver(()=>{const review=document.querySelector('#adventure-review'),button=document.querySelector('#adventure-confirm');if(!review.hidden&&!button.disabled&&!document.querySelector('#adventure-required input'))button.click();});__calculationReview.observe(document.querySelector('#adventure-dialog'),{subtree:true,attributes:true,childList:true});document.querySelector('#adventure-generate').click();true")
            waitUntil(10_000) { calls.get() == 1 }
            val began = SystemClock.elapsedRealtime()
            if (transition?.startsWith("home_") == true) runOnMainSync {
                activity.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            if (transition == "lock_180") shell("input keyevent KEYCODE_SLEEP")
            val backgroundDuration = when (transition) { "home_60" -> 60_000L; "home_180", "lock_180" -> 180_000L; else -> 0L }
            // No WebView evaluations while hidden: they could accidentally wake
            // its renderer and invalidate the background-continuation evidence.
            while (SystemClock.elapsedRealtime() - began < backgroundDuration) SystemClock.sleep(250)
            var active = true
            waitUntil(600_000) { runOnMainSync { active = app.calculations.activeId != null }; !active }
            check(calls.get() == 2) { "The full optional second model request was not reached" }
            if (transition == "lock_180") shell("input keyevent KEYCODE_WAKEUP")
            runOnMainSync { activity.startActivity(Intent(activity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            waitUntil(10_000) { evaluate(web, "!document.querySelector('#adventure-dialog').open") == "true" }
            evaluate(web, "(async()=>{const {state,selectedCandidate}=await import('/static/state.js');const {exportCanonicalCandidate}=await import('/static/local_gpx_export.js');const candidate=selectedCandidate();const a=await exportCanonicalCandidate(candidate).blob.text(),b=await exportCanonicalCandidate(candidate).blob.text();const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(a));globalThis.__calculationProof={same_gpx:a===b,gpx_sha256:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join(''),model_calls:state.adventureResult.model_calls.length,native_calls:state.adventureResult.routing_diagnostics.cache.backend_call_count,distance_m:candidate.route.summary.distance_m};})()")
            waitUntil(10_000) { evaluate(web, "Boolean(globalThis.__calculationProof)") == "true" }
            val proof = evaluate(web, "JSON.stringify(globalThis.__calculationProof)")
            check(calls.get() == 2)
            check(evaluate(web, "__calculationProof.same_gpx&&__calculationProof.model_calls===2&&__calculationProof.native_calls>0") == "true")
            result.putBoolean("passed", true)
            result.putInt("fake_native_model_calls", calls.get())
            result.putLong("background_duration_ms", backgroundDuration)
            result.putString("transition", transition)
            result.putString("ui_proof", proof)
            result.putBoolean("live_inference", false)

            exitCode = 0
        } catch (_: Exception) {
            // Never log prompt, response, route, bearer or account information.
            result.putBoolean("passed", false)
            result.putString("diagnostic", "deterministic_calculation_acceptance_failed")
            result.putBoolean("live_inference", false)
            exitCode = 1
        } finally {
            runCatching { ownedApp?.let { app -> runOnMainSync { app.calculations.activeId?.let { app.calculations.cancel(it) } } } }
            page?.let { web -> runCatching {
                evaluate(web, "globalThis.__calculationReview?.disconnect();document.querySelector('#adventure-close')?.click();document.querySelector('#adventure-return-manual')?.click();(async()=>{const {pwaRuntime}=await import('/static/pwa_runtime.js');const repository=(await pwaRuntime()).adventures;if(globalThis.__calculationSavedBefore)await repository.save(__calculationSavedBefore.output,__calculationSavedBefore.selected_id);else if(globalThis.__calculationBackupReady)await repository.clear();if(typeof globalThis.__calculationEditorBefore==='string')document.querySelector('#adventure-text').value=__calculationEditorBefore;globalThis.__calculationCleanupReady=true;})()")
                waitUntil(10_000) { evaluate(web, "globalThis.__calculationCleanupReady===true") == "true" }
            }.onFailure {
                result.putBoolean("passed", false); result.putString("diagnostic", "manual_state_restoration_failed"); exitCode = 1
            } }
            restore?.invoke()
        }
        finish(exitCode, result)
    }
    private fun evaluate(web: WebView, script: String): String {
        val latch = CountDownLatch(1); var answer: String? = null
        runOnMainSync { web.evaluateJavascript(script) { answer = it; latch.countDown() } }
        check(latch.await(10, TimeUnit.SECONDS)); return requireNotNull(answer)
    }
    private fun waitUntil(timeout: Long, check: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + timeout
        while (!check()) { require(SystemClock.elapsedRealtime() < deadline); SystemClock.sleep(100) }
    }
    private fun shell(command: String) { uiAutomation.executeShellCommand(command).use { descriptor ->
        java.io.FileInputStream(descriptor.fileDescriptor).use { it.readBytes() }
    } }
    private class TestAccounts : ChatGptAccounts {
        private var account = ChatGptAccount("oaiapp_calculationtest", ChatGptIdentity("synthetic", null, "Deterministic device test"),
            ChatGptTokens("synthetic-never-sent", null, "synthetic", setOf("resource.invoke", "chatgpt.tokens.use.direct"), Instant.now().epochSecond + 3600))
        override fun hostId() = "urn:uuid:871494d4-b81b-4523-9626-3547cff2e4cc"
        override fun list() = listOf(account)
        override fun save(account: ChatGptAccount) { this.account = account }
        override fun pendingRegistration(): String? = null
        override fun savePendingRegistration(clientId: String?) = Unit
    }
    private class FakeReply(url: URL, private val body: String, private val delay: Long, private val stream: Boolean) : HttpURLConnection(url) {
        private val closed = AtomicBoolean()
        override fun connect() = Unit
        override fun disconnect() { closed.set(true) }
        override fun usingProxy() = false
        override fun getResponseCode() = 200
        override fun getContentType() = if (stream) "text/event-stream" else "application/json"
        override fun getOutputStream() = ByteArrayOutputStream()
        override fun getInputStream(): InputStream {
            val deadline = SystemClock.elapsedRealtime() + delay
            while (SystemClock.elapsedRealtime() < deadline) {
                if (closed.get()) throw java.io.InterruptedIOException("Cancelled fake reply")
                SystemClock.sleep(50)
            }
            if (closed.get()) throw java.io.InterruptedIOException("Cancelled fake reply")
            return ByteArrayInputStream(body.toByteArray())
        }
    }
}
