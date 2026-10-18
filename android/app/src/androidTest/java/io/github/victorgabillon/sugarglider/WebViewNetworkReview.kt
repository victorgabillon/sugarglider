package io.github.victorgabillon.sugarglider

import android.app.Instrumentation
import android.content.Intent
import android.net.TrafficStats
import android.os.Process
import android.os.SystemClock
import java.io.File
import org.json.JSONObject

/** Metadata-only time series. A measurement is not a privacy acceptance pass. */
internal object WebViewNetworkReview {
    /** Trace starts on a blank anchor before the controlled page exists. */
    fun formControl(instrumentation: Instrumentation, root: File) {
        val uid = Process.myUid()
        val tx = TrafficStats.getUidTxBytes(uid)
        val rx = TrafficStats.getUidRxBytes(uid)
        check(tx >= 0 && rx >= 0)
        fun waitFor(name: String) {
            val deadline = SystemClock.elapsedRealtime() + 90_000
            while (!File(root, name).exists() && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(100)
            check(File(root, name).isFile) { "Host deadline: $name" }
        }
        instrumentation.runOnMainSync { android.webkit.WebView.setWebContentsDebuggingEnabled(true) }
        val anchor = instrumentation.startActivitySync(Intent().setClassName(instrumentation.targetContext,
            "io.github.victorgabillon.sugarglider.WebViewReviewActivity").putExtra("control", "blank")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        File(root, "preload-ready").writeText("ready")
        waitFor("preload-start")
        val mode = File(root, "control-mode").readText().trim()
        check(mode in setOf("html", "planner"))
        val beforePageTx = TrafficStats.getUidTxBytes(uid)
        val beforePageRx = TrafficStats.getUidRxBytes(uid)
        val activity = instrumentation.startActivitySync(Intent().setClassName(instrumentation.targetContext,
            "io.github.victorgabillon.sugarglider." + if (mode == "planner") "MainActivity" else "AutofillControlActivity")
            .putExtra("research_id", root.name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        instrumentation.runOnMainSync { activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        val views = org.json.JSONArray()
        instrumentation.runOnMainSync {
            val pending = java.util.ArrayDeque<android.view.View>()
            pending.add(activity.window.decorView)
            while (pending.isNotEmpty()) {
                val view = pending.removeFirst()
                if (view is android.webkit.WebView) views.put(JSONObject()
                    .put("important_for_autofill", view.importantForAutofill)
                    .put("javascript_enabled", view.settings.javaScriptEnabled))
                if (view is android.view.ViewGroup) for (i in 0 until view.childCount) pending.add(view.getChildAt(i))
            }
        }
        File(root, "page-visible").writeText("ready")
        SystemClock.sleep(60_000)
        val beforeDestroyTx = TrafficStats.getUidTxBytes(uid)
        val beforeDestroyRx = TrafficStats.getUidRxBytes(uid)
        instrumentation.runOnMainSync { activity.finish() }
        File(root, "page-destroyed").writeText("ready")
        SystemClock.sleep(15_000)
        val finalTx = TrafficStats.getUidTxBytes(uid)
        val finalRx = TrafficStats.getUidRxBytes(uid)
        val passed = finalTx == tx && finalRx == rx
        val provider = android.webkit.WebView.getCurrentWebViewPackage()
        File(root, "control-result.json").writeText(JSONObject().put("uid", uid).put("pid", Process.myPid())
            .put("api", android.os.Build.VERSION.SDK_INT).put("webview_package", provider?.packageName)
            .put("webview_version", provider?.versionName).put("mode", mode)
            .put("tx_delta_bytes", finalTx - tx).put("rx_delta_bytes", finalRx - rx)
            .put("setup_tx_bytes", beforePageTx - tx).put("setup_rx_bytes", beforePageRx - rx)
            .put("visible_tx_bytes", beforeDestroyTx - beforePageTx).put("visible_rx_bytes", beforeDestroyRx - beforePageRx)
            .put("after_destroy_tx_bytes", finalTx - beforeDestroyTx).put("after_destroy_rx_bytes", finalRx - beforeDestroyRx)
            .put("strict_zero_passed", passed).put("actual_webviews", views).toString())
        File(root, "preload-finished").writeText("ready")
        waitFor("preload-collected")
        instrumentation.runOnMainSync { anchor.finish() }
        check(passed) { "form-control network counters: tx=${finalTx - tx} rx=${finalRx - rx}" }
    }

    // Keep an empty WebView alive while host CDP starts metadata tracing, then
    // launch the unchanged real planner. The empty page owns no native bridge.
    fun preload(instrumentation: Instrumentation, root: File) {
        instrumentation.runOnMainSync { android.webkit.WebView.setWebContentsDebuggingEnabled(true) }
        val blank = instrumentation.startActivitySync(Intent().setClassName(instrumentation.targetContext,
            "io.github.victorgabillon.sugarglider.WebViewReviewActivity").putExtra("control", "blank")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        File(root, "preload-ready").writeText("ready")
        fun waitFor(name: String) {
            val deadline = SystemClock.elapsedRealtime() + 90_000
            while (!File(root, name).exists() && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(100)
            check(File(root, name).isFile) { "Host trace deadline: $name" }
        }
        waitFor("preload-start")
        val uid = Process.myUid()
        val tx = TrafficStats.getUidTxBytes(uid)
        val rx = TrafficStats.getUidRxBytes(uid)
        check(tx >= 0 && rx >= 0)
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        instrumentation.runOnMainSync { activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        SystemClock.sleep(60_000)
        instrumentation.runOnMainSync { activity.finish() }
        SystemClock.sleep(15_000)
        File(root, "preload-result.json").writeText(JSONObject().put("uid", uid)
            .put("tx_delta_bytes", TrafficStats.getUidTxBytes(uid) - tx)
            .put("rx_delta_bytes", TrafficStats.getUidRxBytes(uid) - rx).toString())
        File(root, "preload-finished").writeText("ready")
        waitFor("preload-collected")
        instrumentation.runOnMainSync { blank.finish() }
    }

    fun run(instrumentation: Instrumentation, root: File) {
        val mode = File(root, "control-mode").readText().trim()
        check(mode in setOf("native", "webview", "blank", "assets", "planner"))
        val uid = Process.myUid()
        val output = File(root, "network-control.jsonl")
        check(!output.exists())
        val start = SystemClock.elapsedRealtime()
        fun sample(stage: String) {
            val tx = TrafficStats.getUidTxBytes(uid)
            val rx = TrafficStats.getUidRxBytes(uid)
            check(tx >= 0 && rx >= 0) { "UID traffic counters unavailable" }
            output.appendText(JSONObject().put("elapsed_ms", SystemClock.elapsedRealtime() - start)
                .put("stage", stage).put("mode", mode).put("uid", uid).put("pid", Process.myPid())
                .put("tx_bytes", tx).put("rx_bytes", rx)
                .put("pss_bytes", android.os.Debug.getPss() * 1024L).toString() + "\n")
        }
        sample("before_activity")
        var trace: android.webkit.TracingController? = null
        instrumentation.runOnMainSync {
            if (mode in setOf("assets", "planner") && android.os.Build.VERSION.SDK_INT >= 28) {
                trace = android.webkit.TracingController.getInstance().also {
                    it.start(android.webkit.TracingConfig.Builder().addCategories("netlog")
                        .setTracingMode(android.webkit.TracingConfig.RECORD_UNTIL_FULL).build())
                }
            }
        }
        val activityClass = if (mode == "planner") "MainActivity" else "WebViewReviewActivity"
        val intent = Intent().setClassName(instrumentation.targetContext, "io.github.victorgabillon.sugarglider.$activityClass")
            .putExtra("control", mode).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val activity = instrumentation.startActivitySync(intent)
        instrumentation.runOnMainSync {
            activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
        repeat(60) { sample("visible"); SystemClock.sleep(1_000) }
        instrumentation.runOnMainSync { activity.finish() }
        repeat(15) { sample("after_destroy"); SystemClock.sleep(1_000) }
        sample("finished")
        if (trace != null) {
            val executor = java.util.concurrent.Executors.newSingleThreadExecutor()
            val completed = java.util.concurrent.CountDownLatch(1)
            instrumentation.runOnMainSync {
                check(requireNotNull(trace).stop(MetadataTraceOutput(File(root, "network-trace.json")) {
                    completed.countDown()
                }, executor))
            }
            val finished = completed.await(30, java.util.concurrent.TimeUnit.SECONDS)
            executor.shutdown()
            check(finished) { "Trace completion deadline" }
            check(executor.awaitTermination(30, java.util.concurrent.TimeUnit.SECONDS))
            check(File(root, "network-trace.json").isFile)
        }
    }
}

/** Default netlog also includes TLS handshake fields; persist an allowlist only. */
private class MetadataTraceOutput(private val destination: File, private val completed: () -> Unit) : java.io.ByteArrayOutputStream() {
    override fun close() {
        try {
        val trace = JSONObject(toString(Charsets.UTF_8.name()))
        val events = trace.getJSONArray("traceEvents")
        val allowed = setOf("source_start_time", "source_dependency", "byte_count", "net_error",
            "host", "hostname", "method", "priority", "load_flags", "privacy_mode")
        for (index in 0 until events.length()) {
            val event = events.getJSONObject(index)
            if (!event.optString("cat").contains("netlog")) continue
            val args = event.optJSONObject("args") ?: continue
            val original = args.optJSONObject("params") ?: continue
            val metadata = JSONObject()
            for (key in allowed) if (original.has(key)) metadata.put(key, original.get(key))
            for (key in listOf("url", "server")) {
                val uri = runCatching { java.net.URI(original.getString(key)) }.getOrNull()
                if (uri?.host != null) metadata.put("${key}_origin", "${uri.scheme}://${uri.host}")
            }
            args.put("params", metadata)
        }
        destination.writeText(trace.toString())
        super.close()
        } finally { completed() }
    }
}
