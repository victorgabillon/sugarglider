package io.github.victorgabillon.sugarglider

import android.app.Activity
import android.os.Bundle
import android.webkit.WebView
import android.widget.TextView

/** Empty controls: no app assets, routing, map, bridge, URLs or participant data. */
class WebViewReviewActivity : Activity() {
    private var view: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        check(BuildConfig.DEBUG)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val mode = intent.getStringExtra("control")
        check(mode in setOf("native", "webview", "blank", "assets"))
        if (mode == "native") {
            setContentView(TextView(this).apply { text = "Sugarglider network control: native only" })
        } else {
            view = WebView(this).also {
                setContentView(it)
                if (mode == "blank") it.loadUrl("about:blank")
                if (mode == "assets") {
                    it.webViewClient = object : android.webkit.WebViewClient() {
                        override fun shouldInterceptRequest(view: WebView, request: android.webkit.WebResourceRequest): android.webkit.WebResourceResponse =
                            android.webkit.WebResourceResponse("text/html", "utf-8",
                                "<!doctype html><title>Local asset control</title>".byteInputStream())
                    }
                    it.loadUrl("https://appassets.androidplatform.net/")
                }
            }
        }
    }

    override fun onDestroy() {
        view?.destroy()
        view = null
        super.onDestroy()
    }
}
