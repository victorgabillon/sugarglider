package io.github.victorgabillon.sugarglider

import android.app.Activity
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
    @Volatile private var latestActivity: MainActivity? = null
    override fun callActivityOnCreate(activity: Activity, state: Bundle?) {
        super.callActivityOnCreate(activity, state)
        if (activity is MainActivity) latestActivity = activity
    }
    override fun onCreate(arguments: Bundle?) { super.onCreate(arguments); this.arguments = arguments ?: Bundle(); start() }
    override fun onStart() {
        val result = Bundle()
        val profileNature = arguments.getString("nature_profile") == "true"
        var exitCode = 1
        val calls = AtomicInteger()
        var phase = "fixture"
        fun mark(name: String) {
            phase = name
            sendStatus(0, Bundle().apply {
                putString("phase", name); putInt("fake_native_model_calls", calls.get())
                putLong("elapsed_realtime_ms", SystemClock.elapsedRealtime())
                if (profileNature) {
                    putLong("wall_clock_ms", System.currentTimeMillis())
                    putLong("main_process_cpu_ms", android.os.Process.getElapsedCpuTime())
                    putLong("main_process_pss_kib", android.os.Debug.getPss())
                }
            })
        }
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
            require(transition in setOf("foreground", "home_60", "home_180", "app_switch_180", "lock_180", "cancel_notification", "cancel_ui", "sign_out", "network_failure", "recreate"))
            val delay = fixture.getLong("model_delay_ms").also { require(it in 0..90_000) }
            val proposals = fixture.getJSONArray("proposals").also { require(it.length() == 2) }
            val prompt = fixture.getString("prompt").also { require(it.length in 3..8000) }
            mark("connection")
            val accounts = TestAccounts()
            val connection = ChatGptConnection(accounts, ChatGptHttp(ConnectionFactory { url ->
                when (url.toString()) {
                    ChatGptHttp.MODELS -> FakeReply(url, """{"models":[{"slug":"deterministic","display_name":"Deterministic device test — no live inference","visibility":"list"}]}""", 0, false)
                    ChatGptHttp.RESPONSES -> {
                        val index = calls.getAndIncrement()
                        require(index < 2) { "Model budget exceeded" }
                        sendStatus(0, Bundle().apply {
                            putString("phase", "fake_model_started")
                            putInt("fake_native_model_calls", index + 1)
                            putLong("elapsed_realtime_ms", SystemClock.elapsedRealtime())
                            if (profileNature) {
                                putLong("wall_clock_ms", System.currentTimeMillis())
                                putLong("main_process_cpu_ms", android.os.Process.getElapsedCpuTime())
                            }
                        })
                        val completion = JSONObject().put("type", "response.completed").put("response", JSONObject().put("status", "completed")
                            .put("output", JSONArray().put(JSONObject().put("type", "message").put("role", "assistant").put("status", "completed")
                                .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", proposals.getJSONObject(index).toString()))))))
                        FakeReply(url, "data: $completion\n\n", delay, true, transition == "network_failure" && index == 0)
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
            mark("activity")
            val activity = startActivitySync(Intent(targetContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            val webField = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
            lateinit var web: WebView
            runOnMainSync { web = webField.get(activity) as WebView }; page = web
            mark("regional_ready")
            waitUntil(120_000) { evaluate(web, "document.querySelector('#regional-status')?.dataset.state === 'regional_ready'") == "true" }
            if (profileNature) {
                evaluate(web, "import('https://appassets.androidplatform.net/static/regional_performance.js').then(m=>{m.enableRegionalProfiling();globalThis.__natureProfilingReady=true;})")
                waitUntil(10_000) { evaluate(web, "globalThis.__natureProfilingReady===true") == "true" }
                runOnMainSync {
                    result.putInt("renderer_requested_priority", web.rendererRequestedPriority)
                    result.putBoolean("renderer_waived_when_hidden", web.rendererPriorityWaivedWhenNotVisible)
                }
            }
            // A test cannot silently grant notification permission or install data.
            check(targetContext.getSystemService(android.app.NotificationManager::class.java).areNotificationsEnabled())
            mark("backup")
            evaluate(web, "(async()=>{const {pwaRuntime}=await import('https://appassets.androidplatform.net/static/pwa_runtime.js');globalThis.__calculationSavedBefore=await (await pwaRuntime()).adventures.read();globalThis.__calculationEditorBefore=document.querySelector('#adventure-text').value;const {state}=await import('https://appassets.androidplatform.net/static/state.js');globalThis.__calculationCanonicalBefore=JSON.stringify({result:state.generationResult,source:state.generationSourceRequest,selected:state.selectedSignature});globalThis.__calculationBackupReady=true;})().catch(e=>{globalThis.__calculationBackupError=e.name;})")
            waitUntil(10_000) {
                val error = evaluate(web, "globalThis.__calculationBackupError??null")
                require(error == "null") { "Test snapshot setup failed" }
                evaluate(web, "globalThis.__calculationBackupReady===true") == "true"
            }
            val canonicalBefore = evaluate(web, "globalThis.__calculationCanonicalBefore")
            val language = arguments.getString("language")
            if (language != null) {
                require(language in setOf("fr", "en"))
                evaluate(web, "import('https://appassets.androidplatform.net/static/i18n.js').then(m=>m.setLanguage(" + JSONObject.quote(language) + "))")
                waitUntil(10_000) { evaluate(web, "document.documentElement.lang === " + JSONObject.quote(language)) == "true" }
            }
            mark("open_dialog")
            evaluate(web, "document.querySelector('#plan-with-ai').click();true")
            mark("models")
            waitUntil(10_000) { evaluate(web, "document.querySelector('#adventure-model')?.value === 'deterministic'") == "true" }
            evaluate(web, "document.querySelector('#adventure-text').value=${JSONObject.quote(prompt)};document.querySelector('#adventure-text').dispatchEvent(new Event('input'));document.querySelector('#adventure-research').checked=false;document.querySelector('#adventure-refine').checked=true;true")
            waitUntil(10_000) { evaluate(web, "!document.querySelector('#adventure-generate').disabled") == "true" }
            mark("generate")
            // The fixture explicitly approves only its proposed endpoints. A hard
            // place or unsupported requirement still fails this test for review.
            evaluate(web, "globalThis.__calculationReview=new MutationObserver(()=>{const review=document.querySelector('#adventure-review'),button=document.querySelector('#adventure-confirm');if(!review.hidden&&!button.disabled&&!document.querySelector('#adventure-required input'))button.click();});__calculationReview.observe(document.querySelector('#adventure-dialog'),{subtree:true,attributes:true,childList:true});document.querySelector('#adventure-generate').click();true")
            mark("first_inference")
            waitUntil(10_000) { calls.get() == 1 }
            mark("transition")
            if (transition in setOf("cancel_notification", "cancel_ui", "sign_out", "recreate")) {
                SystemClock.sleep(500)
                when (transition) {
                    "cancel_notification" -> runOnMainSync {
                        val notification = targetContext.getSystemService(android.app.NotificationManager::class.java).activeNotifications.single { it.id == 119 }
                        notification.notification.actions.single().actionIntent.send()
                    }
                    "cancel_ui" -> evaluate(web, "document.querySelector('#adventure-cancel').click();true")
                    "sign_out" -> evaluate(web, "document.querySelector('#adventure-sign-out').click();true")
                    "recreate" -> {
                        runOnMainSync { activity.recreate() }
                        waitUntil(20_000) { latestActivity != null && latestActivity !== activity }
                        runOnMainSync { web = webField.get(requireNotNull(latestActivity)) as WebView }; page = web
                        waitUntil(120_000) { evaluate(web, "document.querySelector('#regional-status')?.dataset.state === 'regional_ready'") == "true" }
                        evaluate(web, "document.querySelector('#plan-with-ai').click();true")
                        waitUntil(10_000) { evaluate(web, "document.querySelector('#adventure-text').value === " + JSONObject.quote(prompt)) == "true" }
                    }
                }
            }
            val began = SystemClock.elapsedRealtime()
            if (transition?.startsWith("home_") == true) runOnMainSync {
                activity.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            if (transition == "app_switch_180") runOnMainSync {
                activity.startActivity(Intent(android.provider.Settings.ACTION_SETTINGS))
            }
            if (transition == "lock_180") shell("input keyevent KEYCODE_SLEEP")
            val backgroundDuration = when (transition) { "home_60" -> 60_000L; "home_180", "app_switch_180", "lock_180" -> 180_000L; else -> 0L }
            // No WebView evaluations while hidden: they could accidentally wake
            // its renderer and invalidate the background-continuation evidence.
            while (SystemClock.elapsedRealtime() - began < backgroundDuration) SystemClock.sleep(250)
            val backgroundElapsed = if (backgroundDuration == 0L) 0L else SystemClock.elapsedRealtime() - began
            if (backgroundDuration > 0) {
                var completed = false
                runOnMainSync { completed = app.calculations.activeId == null }
                result.putBoolean("completed_before_return", completed)
                result.putInt("model_calls_before_return", calls.get())
                mark("background_interval_end")
            }
            if (transition == "lock_180") shell("input keyevent KEYCODE_WAKEUP")
            // Return at the requested interval, including while the first 75 s
            // reply is still pending in home_60. Never wait for completion first.
            runOnMainSync { activity.startActivity(Intent(activity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            mark("completion")
            var active = true
            waitUntil(600_000) { runOnMainSync { active = app.calculations.activeId != null }; !active }
            val interrupted = transition in setOf("cancel_notification", "cancel_ui", "sign_out", "network_failure", "recreate")
            mark("result")
            if (interrupted) {
                check(calls.get() == 1)
                waitUntil(10_000) { evaluate(web, "document.querySelector('#adventure-dialog').getAttribute('aria-busy') === 'false'") == "true" }
                evaluate(web, "(async()=>{const {state}=await import('https://appassets.androidplatform.net/static/state.js');globalThis.__calculationInterruptedProof={no_adventure:!state.adventureDisplay,no_automatic_retry:true};})()")
                waitUntil(10_000) { evaluate(web, "globalThis.__calculationInterruptedProof?.no_adventure===true") == "true" }
                evaluate(web, "(async()=>{const {state}=await import('https://appassets.androidplatform.net/static/state.js');globalThis.__calculationCanonicalAfter=JSON.stringify({result:state.generationResult,source:state.generationSourceRequest,selected:state.selectedSignature});})()")
                waitUntil(10_000) { evaluate(web, "typeof globalThis.__calculationCanonicalAfter === 'string'") == "true" }
                check(evaluate(web, "globalThis.__calculationCanonicalAfter") == canonicalBefore)
                result.putBoolean("previous_route_unchanged", true)
                if (transition in setOf("network_failure", "recreate")) {
                    check(app.calculationJournal.recovery()?.getString("prompt") == prompt)
                    result.putBoolean("original_request_recoverable", true)
                }
                SystemClock.sleep(1000); check(calls.get() == 1)
                result.putBoolean("expected_interruption", true)
            } else {
                check(calls.get() == 2) { "The full optional second model request was not reached" }
                waitUntil(10_000) { evaluate(web, "!document.querySelector('#adventure-dialog').open") == "true" }
                evaluate(web, "(async()=>{const {state,selectedCandidate}=await import('https://appassets.androidplatform.net/static/state.js');const {exportCanonicalCandidate}=await import('https://appassets.androidplatform.net/static/local_gpx_export.js');const candidate=selectedCandidate();const a=await exportCanonicalCandidate(candidate).blob.text(),b=await exportCanonicalCandidate(candidate).blob.text();const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(a));globalThis.__calculationProof={same_gpx:a===b,gpx_sha256:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join(''),model_calls:state.adventureResult.model_calls.length,native_calls:state.adventureResult.routing_diagnostics.cache.backend_call_count,timings:state.adventureResult.timings,distance_m:candidate.route.summary.distance_m};})()")
                waitUntil(10_000) { evaluate(web, "Boolean(globalThis.__calculationProof)") == "true" }
                val proof = evaluate(web, "JSON.stringify(globalThis.__calculationProof)")
                check(calls.get() == 2)
                check(evaluate(web, "__calculationProof.same_gpx&&__calculationProof.model_calls===2&&__calculationProof.native_calls>0") == "true")
                result.putBoolean("passed", true)
                result.putInt("fake_native_model_calls", calls.get())
                result.putLong("background_duration_ms", backgroundElapsed)
                result.putString("transition", transition)
                result.putString("ui_proof", proof)
            }
            result.putBoolean("passed", true)
            result.putInt("fake_native_model_calls", calls.get())
            result.putString("transition", transition)
            result.putBoolean("live_inference", false)
            if (profileNature && transition != "recreate") {
                evaluate(web, "import('https://appassets.androidplatform.net/static/regional_performance.js').then(m=>{globalThis.__natureProfileResult=JSON.stringify(m.regionalPerformanceSnapshot());})")
                waitUntil(10_000) { evaluate(web, "typeof globalThis.__natureProfileResult==='string'") == "true" }
                result.putString("nature_profile", evaluate(web, "globalThis.__natureProfileResult"))
            }

            exitCode = 0
        } catch (error: Exception) {
            // Never log prompt, response, route, bearer or account information.
            result.putBoolean("passed", false)
            result.putString("diagnostic", "deterministic_calculation_acceptance_failed_" + phase)
            result.putString("failure_type", error.javaClass.simpleName)
            result.putInt("fake_native_model_calls", calls.get())
            result.putBoolean("live_inference", false)
            exitCode = 1
        } finally {
            runCatching { ownedApp?.let { app -> runOnMainSync { app.calculations.activeId?.let { app.calculations.cancel(it) } } } }
            page?.let { web -> runCatching {
                if (profileNature) evaluate(web, "import('https://appassets.androidplatform.net/static/regional_performance.js').then(m=>m.enableRegionalProfiling(false))")
                evaluate(web, "globalThis.__calculationReview?.disconnect();document.querySelector('#adventure-close')?.click();document.querySelector('#adventure-return-manual')?.click();(async()=>{const {pwaRuntime}=await import('https://appassets.androidplatform.net/static/pwa_runtime.js');const repository=(await pwaRuntime()).adventures;if(globalThis.__calculationSavedBefore)await repository.save(__calculationSavedBefore.output,__calculationSavedBefore.selected_id);else if(globalThis.__calculationBackupReady)await repository.clear();if(typeof globalThis.__calculationEditorBefore==='string')document.querySelector('#adventure-text').value=__calculationEditorBefore;globalThis.__calculationCleanupReady=true;})()")
                waitUntil(10_000) { evaluate(web, "globalThis.__calculationCleanupReady===true") == "true" }
            }.onFailure {
                result.putBoolean("passed", false); result.putBoolean("restoration_failed", true); exitCode = 1
            } }
            restore?.invoke()
        }
        result.putInt("fake_native_model_calls", calls.get())
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
    private class FakeReply(url: URL, private val body: String, private val delay: Long, private val stream: Boolean, private val fail: Boolean = false) : HttpURLConnection(url) {
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
            if (fail) throw java.io.IOException("Deterministic simulated network interruption")
            return ByteArrayInputStream(body.toByteArray())
        }
    }
}
