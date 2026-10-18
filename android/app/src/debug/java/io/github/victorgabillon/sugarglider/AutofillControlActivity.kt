package io.github.victorgabillon.sugarglider

import android.annotation.SuppressLint
import android.app.Activity
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import java.io.File

/** Explicit private HTML controls. No native bridge, external assets or user data. */
class AutofillControlActivity : Activity() {
    private var webView: WebView? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        check(BuildConfig.DEBUG)
        val id = intent.getStringExtra("research_id").orEmpty()
        check(id.matches(Regex("[a-z0-9-]{1,64}")))
        val root = File(cacheDir, id).canonicalFile
        check(root.parentFile == cacheDir.canonicalFile)
        val html = File(root, "control.html")
        check(html.isFile && html.length() in 1..1_048_576)
        val policy = File(root, "view-policy").readText().trim()
        check(policy in setOf("auto", "exclude"))
        val scriptFile = File(root, "javascript-policy")
        val scripts = if (scriptFile.isFile) scriptFile.readText().trim() else "on"
        check(scripts in setOf("on", "off"))
        val content = html.readBytes()
        val address = "https://appassets.androidplatform.net/pr97-control.html"
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        webView = WebView(this).also { view ->
            if (policy == "exclude") view.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            view.settings.apply {
                javaScriptEnabled = scripts == "on"
                domStorageEnabled = true
                allowFileAccess = false
                allowContentAccess = false
                mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            }
            view.webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = true
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse =
                    if (request.isForMainFrame && request.url.toString() == address)
                        WebResourceResponse("text/html", "utf-8", content.inputStream())
                    else WebResourceResponse("text/plain", "utf-8", 404, "Unavailable", emptyMap(), ByteArray(0).inputStream())
            }
            setContentView(view)
            view.loadUrl(address)
        }
    }

    override fun onDestroy() {
        webView?.destroy()
        webView = null
        super.onDestroy()
    }
}
