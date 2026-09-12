package io.github.victorgabillon.sugarglider

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Color
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher
import android.webkit.GeolocationPermissions
import android.webkit.HttpAuthHandler
import android.webkit.RenderProcessGoneDetail
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.core.net.toUri
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.time.Instant
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private lateinit var application: SugargliderApplication
    private lateinit var nativeRouteEngine: NativeRouteEngine
    private lateinit var bundledShellAssets: BundledShellAssets
    private var configuredOrigin: String? = null
    private var webView: WebView? = null
    private var activeBridgeChannel: BridgeChannel? = null
    private var bridgeNavigationEpoch = 0L
    private var bridgeStatusCounter = 0L
    private var activityVisible = false
    private var interruptedGpxSave = false
    private var pendingStart: PendingStart? = null
    private var pendingLocalRoute: PendingLocalRoute? = null
    private var pendingLocalCapabilities: BridgeRequest.GetLocalRouteCapabilities? = null
    private var localRouteWorkerBusy = false
    private var pendingDeepLinkSlug: String? = null
    private var backInvokedCallback: OnBackInvokedCallback? = null
    private var outingLeaveDialog: AlertDialog? = null
    private val bridgeLedger = BridgeRequestLedger()
    private val localRouteExecutor = Executors.newSingleThreadExecutor()
    private val documentExecutor = Executors.newSingleThreadExecutor()
    private val gpxDocumentSaver = GpxDocumentSaver(
        showPicker = ::showGpxDocumentPicker,
        execute = { work -> documentExecutor.execute(work) },
        dispatch = { work -> runOnUiThread(work) },
    )
    private val webGeolocationPermissions = WebGeolocationPermissionCoordinator()
    private val statusObserver = NativeStatusRepository.Observer { status, terminalFailure ->
        runOnUiThread {
            broadcastStatus(status)
            if (terminalFailure != null) broadcastTerminalFailure(terminalFailure)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        interruptedGpxSave = savedInstanceState?.getBoolean(STATE_GPX_SAVE_PENDING) == true
        application = getApplication() as SugargliderApplication
        nativeRouteEngine = NativeRouteEngineFactory.create(applicationContext)
        bundledShellAssets = BundledShellAssets(applicationContext)
        application.statusRepository.addObserver(statusObserver)
        registerPredictiveBackCallback()
        pendingDeepLinkSlug = deepLinkSlug(intent)
        if (pendingDeepLinkSlug != null || savedInstanceState?.getBoolean(STATE_SHARING_SCREEN) == true) {
            openSharingServer()
        } else openPlanner()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deepLinkSlug(intent)?.let {
            pendingDeepLinkSlug = it
            openSharingServer()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        // Only an uncertainty flag survives recreation, never file bytes or URI.
        outState.putBoolean(STATE_GPX_SAVE_PENDING, interruptedGpxSave || gpxDocumentSaver.hasPendingWork())
        // Restore only the UI mode, never a URL, capability, or participant identity.
        outState.putBoolean(STATE_SHARING_SCREEN, configuredOrigin != null && configuredOrigin != BundledShellPolicy.ORIGIN)
        super.onSaveInstanceState(outState)
    }

    override fun onResume() {
        super.onResume()
        activityVisible = true
        if (interruptedGpxSave) {
            interruptedGpxSave = false
            AlertDialog.Builder(this)
                .setTitle("Check your GPX file")
                .setMessage("The app restarted during a GPX save. If you selected a file, check it before saving again.")
                .setPositiveButton("OK", null)
                .show()
        }
    }

    override fun onPause() {
        activityVisible = false
        super.onPause()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        // Retain the live page and its in-memory authority across size changes.
        // Never serialize WebView state, reload, reroute, or restart sharing here.
        webView?.invalidate()
        ViewCompat.requestApplyInsets(window.decorView)
    }

    override fun onDestroy() {
        pendingStart = null
        pendingLocalRoute = null
        pendingLocalCapabilities = null
        localRouteExecutor.shutdownNow()
        gpxDocumentSaver.close()
        documentExecutor.shutdown()
        dismissOutingLeaveDialog()
        unregisterPredictiveBackCallback()
        application.statusRepository.removeObserver(statusObserver)
        destroyWebView()
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    private fun showGpxDocumentPicker(filename: String) {
        startActivityForResult(
            Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(GpxDocumentProtocol.MIME_TYPE)
                .putExtra(Intent.EXTRA_TITLE, filename),
            REQUEST_GPX_DOCUMENT,
        )
    }

    @Deprecated("Activity result API for the existing platform Activity")
    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_GPX_DOCUMENT) return
        if (resultCode != RESULT_OK) { gpxDocumentSaver.selected(null); return }
        val uri = data?.data
        gpxDocumentSaver.selected {
            // Only the explicit picker result grants access; never persist its URI
            // or permission, or delete a possibly existing user file on failure.
            require(uri?.scheme == "content")
            contentResolver.openOutputStream(requireNotNull(uri), "wt")
        }
    }

    @Suppress("DEPRECATION")
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_WEB_GEOLOCATION_PERMISSION) {
            val current = webView
            webGeolocationPermissions.complete(
                preciseLocationGranted = checkSelfPermission(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                ) == PackageManager.PERMISSION_GRANTED,
                configuredOrigin = configuredOrigin,
                navigationEpoch = bridgeNavigationEpoch,
                currentWebViewIdentity = current?.let(System::identityHashCode),
            )
            return
        }
        if (requestCode != REQUEST_TRACKING_PERMISSIONS) return
        val operation = pendingStart ?: return
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            AlertDialog.Builder(this)
                .setTitle("Precise location required")
                .setMessage(
                    "Trail sharing requires precise location. Approximate-only permission leaves sharing stopped.",
                ).setPositiveButton("OK", null)
                .show()
            finishPendingStart(operation, "approximate_location")
            return
        }
        if (
            Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            AlertDialog.Builder(this)
                .setTitle("Notifications required")
                .setMessage(
                    "A visible persistent notification is required while screen-off sharing is active.",
                ).setPositiveButton("OK", null)
                .show()
            finishPendingStart(operation, "notification_permission_denied")
            return
        }
        continueStartAfterPermissions(operation)
    }

    @Deprecated("Used only below Android 13")
    @Suppress("DEPRECATION")
    @SuppressLint("GestureBackNavigation")
    override fun onBackPressed() {
        handleAndroidBack(::performLegacySystemBack)
    }

    private fun showServerConfiguration() {
        destroyWebView()
        configuredOrigin = null
        val padding = dp(24)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(padding, padding, padding, padding)
            setBackgroundColor(getColor(R.color.brand_cream))
        }
        root.addView(TextView(this).apply {
            setText(R.string.configure_title)
            textSize = 28f
            setTextColor(getColor(R.color.brand_green))
        })
        root.addView(TextView(this).apply {
            setText(R.string.configure_description)
            textSize = 16f
            setPadding(0, dp(12), 0, dp(12))
        })
        val input = EditText(this).apply {
            hint = "https://sugarglider.example"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(true)
            if (BuildConfig.DEBUG) setText(DEBUG_DEFAULT_ORIGIN)
        }
        val error = TextView(this).apply {
            setTextColor(Color.rgb(170, 25, 25))
            visibility = View.GONE
        }
        val open = Button(this).apply {
            setText(R.string.configure_open)
            setOnClickListener {
                val origin = ServerOrigin.parse(input.text.toString(), BuildConfig.ALLOW_HTTP)
                if (origin == null || BundledShellPolicy.ownsHost(origin.normalized)) {
                    error.text = if (origin != null && BundledShellPolicy.ownsHost(origin.normalized)) {
                        "This address belongs to the local planner. Enter a sharing server address."
                    } else if (BuildConfig.ALLOW_HTTP) {
                        "Enter HTTPS, or debug HTTP on localhost or a private-LAN IP, with no path, credentials, query, or fragment."
                    } else {
                        "Release builds require HTTPS with no path, credentials, query, or fragment."
                    }
                    error.visibility = View.VISIBLE
                } else {
                    getPreferences(MODE_PRIVATE).edit {
                        putString(PREFERENCE_SERVER_ORIGIN, origin.normalized)
                    }
                    openServer(origin.normalized)
                }
            }
        }
        root.addView(input, fullWidthWrap())
        root.addView(error, fullWidthWrap())
        root.addView(open, fullWidthWrap())
        root.addView(Button(this).apply {
            setText(R.string.open_planner)
            setOnClickListener { openPlanner() }
        }, fullWidthWrap())
        setContentView(root)
    }

    private fun openPlanner() {
        pendingDeepLinkSlug = null
        openServer(BundledShellPolicy.ORIGIN)
    }

    private fun openSharingServer() {
        val stored = getPreferences(MODE_PRIVATE).getString(PREFERENCE_SERVER_ORIGIN, null)
        val origin = stored?.let { ServerOrigin.parse(it, BuildConfig.ALLOW_HTTP)?.normalized }
            ?.takeUnless(BundledShellPolicy::ownsHost)
        if (origin == null) showServerConfiguration() else openServer(origin)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun openServer(origin: String) {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        destroyWebView()
        configuredOrigin = origin
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(getColor(R.color.brand_cream))
        }
        val chromeStartPadding = dp(4)
        val chromeTopPadding = dp(8)
        val chromeEndPadding = dp(12)
        val chromeBottomPadding = dp(2)
        val serverChrome = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL or Gravity.END
            setPadding(
                chromeStartPadding,
                chromeTopPadding,
                chromeEndPadding,
                chromeBottomPadding,
            )
            setBackgroundColor(getColor(R.color.brand_green))
        }
        ViewCompat.setOnApplyWindowInsetsListener(serverChrome) { view, insets ->
            val systemBars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or
                    WindowInsetsCompat.Type.displayCutout(),
            )
            root.setPadding(
                systemBars.left,
                0,
                systemBars.right,
                maxOf(systemBars.bottom, insets.getInsets(WindowInsetsCompat.Type.ime()).bottom),
            )
            view.setPadding(
                chromeStartPadding,
                systemBars.top + chromeTopPadding,
                chromeEndPadding,
                chromeBottomPadding,
            )
            insets
        }
        serverChrome.addView(Button(this).apply {
            setText(if (origin == BundledShellPolicy.ORIGIN) R.string.open_sharing else R.string.planner_and_sharing)
            contentDescription = getString(R.string.configure_server_description)
            setTextColor(Color.WHITE)
            textSize = 13f
            isAllCaps = false
            minWidth = 0
            minHeight = dp(40)
            setPadding(dp(12), 0, dp(12), 0)
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener { showServerMenu(origin) }
        })
        serverChrome.addView(Button(this).apply {
            setText(R.string.privacy_title)
            setTextColor(Color.WHITE)
            textSize = 13f
            isAllCaps = false
            minWidth = 0
            minHeight = dp(40)
            setPadding(dp(12), 0, dp(12), 0)
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener { showPrivacyDetails() }
        })
        root.addView(serverChrome, fullWidthWrap())
        val created = WebView(this)
        webView = created
        created.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setGeolocationEnabled(true)
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            setSupportMultipleWindows(false)
        }
        created.setBackgroundColor(getColor(R.color.brand_cream))
        created.webViewClient = originIsolatingClient(origin)
        created.webChromeClient = foregroundGeolocationClient(created)
        android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(created, false)
        installBridge(created, origin)
        root.addView(
            created,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f,
            ),
        )
        setContentView(root)
        ViewCompat.requestApplyInsets(serverChrome)
        loadConfiguredPage()
    }

    private fun showPrivacyDetails() {
        val content = TextView(this).apply {
            setText(R.string.privacy_description)
            textSize = 16f
            setPadding(dp(20), dp(12), dp(20), dp(12))
        }
        val scroll = ScrollView(this).apply { addView(content) }
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.privacy_title)
            .setView(scroll)
            .setPositiveButton(R.string.privacy_close, null)
        if (BuildConfig.PRIVACY_POLICY_URL.isNotEmpty()) {
            dialog.setNeutralButton(R.string.privacy_online) { _, _ ->
                openExternal(BuildConfig.PRIVACY_POLICY_URL.toUri())
            }
        }
        dialog.show()
    }

    private fun showServerMenu(origin: String) {
        if (origin == BundledShellPolicy.ORIGIN) { openSharingServer(); return }
        AlertDialog.Builder(this)
            .setTitle(R.string.configure_server_title)
            .setMessage(origin)
            .setNegativeButton(android.R.string.cancel, null)
            .setNeutralButton(R.string.open_planner) { _, _ -> openPlanner() }
            .setPositiveButton(R.string.configure_change) { _, _ -> requestServerChange() }
            .show()
    }

    private fun requestServerChange() {
        if (!ServerChangePolicy.allowed(application.statusRepository.current())) {
            AlertDialog.Builder(this)
                .setTitle("Stop sharing first")
                .setMessage(
                    "Stop Android background sharing before changing server. Participant authority is never transferred to another origin.",
                ).setPositiveButton("OK", null)
                .show()
            return
        }
        if (configuredOrigin != null) {
            webGeolocationPermissions.invalidate()
            GeolocationPermissions.getInstance().clearAll()
        }
        getPreferences(MODE_PRIVATE).edit { remove(PREFERENCE_SERVER_ORIGIN) }
        showServerConfiguration()
    }

    private fun loadConfiguredPage() {
        val origin = configuredOrigin ?: return
        val slug = pendingDeepLinkSlug.also { pendingDeepLinkSlug = null }
        webView?.loadUrl(if (slug == null) "$origin/" else "$origin/o/$slug")
    }

    private fun originIsolatingClient(origin: String): WebViewClient = object : WebViewClient() {
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
            if (origin == BundledShellPolicy.ORIGIN) bundledShellAssets.intercept(request.url, request.method) else null

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            val wasCurrent = view === webView
            val pendingDocument = wasCurrent && gpxDocumentSaver.hasPendingWork()
            if (wasCurrent) {
                dismissOutingLeaveDialog()
                // Its renderer no longer exists: discard its permission callback without invoking it.
                webGeolocationPermissions.discard()
                invalidateBridgePage()
                webView = null
            }
            // Only dispose the affected instance. A late callback must not close a newer page.
            (view.parent as? ViewGroup)?.removeView(view)
            view.destroy()
            if (wasCurrent && !isFinishing && !isDestroyed) {
                showRendererRecovery(origin, bridgeNavigationEpoch, pendingDocument)
            }
            return true
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            if (view === webView) {
                dismissOutingLeaveDialog()
                invalidateBridgePage()
            }
            super.onPageStarted(view, url, favicon)
        }

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val target = request.url
            val targetOrigin = ServerOrigin.parse(
                "${target.scheme}://${target.encodedAuthority}",
                BuildConfig.ALLOW_HTTP,
            )?.normalized
            if (targetOrigin == origin && target.scheme in setOf("http", "https")) return false
            openExternal(target)
            return true
        }

        override fun onReceivedSslError(
            view: WebView,
            handler: SslErrorHandler,
            error: android.net.http.SslError,
        ) {
            handler.cancel()
        }

        override fun onReceivedHttpAuthRequest(
            view: WebView,
            handler: HttpAuthHandler,
            host: String,
            realm: String,
        ) {
            handler.cancel()
        }
    }

    private fun showRendererRecovery(origin: String, epoch: Long, pendingDocument: Boolean) {
        val padding = dp(24)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(padding, padding, padding, padding)
            setBackgroundColor(getColor(R.color.brand_cream))
        }
        val message = TextView(this).apply {
            text = if (pendingDocument) {
                getString(
                    R.string.page_recovery_with_gpx,
                    getString(R.string.page_recovery_description),
                    getString(R.string.page_recovery_gpx),
                )
            } else getString(R.string.page_recovery_description)
            textSize = 16f
            setTextColor(getColor(R.color.brand_green))
            setPadding(0, 0, 0, dp(16))
        }
        root.addView(message, fullWidthWrap())
        fun ownsRecovery(): Boolean = webView == null && configuredOrigin == origin &&
            bridgeNavigationEpoch == epoch && !isFinishing && !isDestroyed
        root.addView(Button(this).apply {
            setText(R.string.page_recovery_open)
            setOnClickListener {
                if (ownsRecovery()) openServer(origin)
            }
        }, fullWidthWrap())
        if (application.statusRepository.current().isNativeBusy()) {
            root.addView(Button(this).apply {
                setText(R.string.notification_stop)
                setOnClickListener {
                    if (ownsRecovery() && activityVisible) {
                        startService(
                            Intent(this@MainActivity, LocationSharingService::class.java)
                                .setAction(LocationSharingService.ACTION_STOP),
                        )
                        message.setText(R.string.page_recovery_stopping)
                    }
                }
            }, fullWidthWrap())
        }
        setContentView(root)
    }

    private fun foregroundGeolocationClient(created: WebView): WebChromeClient = object :
        WebChromeClient() {
        override fun onGeolocationPermissionsShowPrompt(
            requestedOrigin: String,
            callback: GeolocationPermissions.Callback,
        ) {
            val normalizedRequestedOrigin = ServerOrigin.parse(
                requestedOrigin,
                BuildConfig.ALLOW_HTTP,
            )?.normalized
            if (normalizedRequestedOrigin == null) {
                callback.invoke(requestedOrigin, false, false)
                return
            }
            val current = webView
            val action = webGeolocationPermissions.begin(
                requestedOrigin = normalizedRequestedOrigin,
                configuredOrigin = configuredOrigin,
                navigationEpoch = bridgeNavigationEpoch,
                sourceWebViewIdentity = System.identityHashCode(created),
                currentWebViewIdentity = current?.let(System::identityHashCode),
                activityVisible = activityVisible,
                preciseLocationGranted = checkSelfPermission(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                ) == PackageManager.PERMISSION_GRANTED,
                resolve = { allow -> callback.invoke(requestedOrigin, allow, allow) },
            )
            if (action == WebGeolocationPermissionAction.REQUEST_FOREGROUND_LOCATION) {
                requestPermissions(
                    arrayOf(
                        Manifest.permission.ACCESS_COARSE_LOCATION,
                        Manifest.permission.ACCESS_FINE_LOCATION,
                    ),
                    REQUEST_WEB_GEOLOCATION_PERMISSION,
                )
            }
        }
    }

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE))
        } catch (_: ActivityNotFoundException) {
            // The untrusted target is not loaded into the authenticated WebView.
        }
    }

    private fun installBridge(created: WebView, origin: String) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) return
        WebViewCompat.addWebMessageListener(
            created,
            BridgeProtocol.OBJECT_NAME,
            setOf(origin),
        ) { sourceView: WebView,
            message: WebMessageCompat,
            sourceOrigin: Uri,
            isMainFrame: Boolean,
            replyProxy: JavaScriptReplyProxy ->
            val current = webView
            val canonicalSourceOrigin = ServerOrigin.parse(
                sourceOrigin.toString(),
                BuildConfig.ALLOW_HTTP,
            )?.normalized ?: return@addWebMessageListener
            if (
                current == null ||
                !BridgeGate.accepts(
                    canonicalSourceOrigin,
                    origin,
                    isMainFrame,
                    System.identityHashCode(current),
                    System.identityHashCode(sourceView),
                )
            ) return@addWebMessageListener
            val document = if (message.type == WebMessageCompat.TYPE_ARRAY_BUFFER) {
                if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_ARRAY_BUFFER)) {
                    return@addWebMessageListener
                }
                GpxDocumentProtocol.parse(message.arrayBuffer) ?: return@addWebMessageListener
            } else null
            val payload = if (document != null) document.ledgerPayload else {
                if (message.type != WebMessageCompat.TYPE_STRING) return@addWebMessageListener
                message.data ?: return@addWebMessageListener
            }
            val request = document?.request ?: BridgeProtocol.parse(payload) ?: return@addWebMessageListener
            val channel = acceptBridgePage(request, replyProxy, sourceView) ?: return@addWebMessageListener
            bridgeLedger.lookup(request, payload)?.let {
                replyProxy.postMessage(it)
                return@addWebMessageListener
            }
            if (!bridgeLedger.begin(request, payload)) return@addWebMessageListener
            if (!BundledShellPolicy.acceptsOrigin(request, origin)) {
                completeFailure(request, payload, channel,
                    if (origin == BundledShellPolicy.ORIGIN) "sharing_unavailable" else "local_planning_unavailable")
                return@addWebMessageListener
            }
            when (request) {
                is BridgeRequest.Hello -> completeBridgeRequest(
                    request,
                    payload,
                    channel,
                    "hello_result",
                    if (origin == BundledShellPolicy.ORIGIN) NativeTrackingStatus.stopped()
                    else application.statusRepository.current(),
                )
                is BridgeRequest.SaveGpx -> {
                    val prepared = document ?: return@addWebMessageListener
                    val finish: (GpxSaveStatus) -> Unit = { status ->
                        completeBridgePayload(
                            request, payload, channel,
                            GpxDocumentProtocol.reply(request.requestId, status),
                        )
                    }
                    if (!activityVisible) finish(GpxSaveStatus.UNAVAILABLE)
                    else gpxDocumentSaver.begin(prepared, finish)
                }
                is BridgeRequest.GetStatus -> {
                    completeBridgeRequest(
                        request,
                        payload,
                        channel,
                        "tracking_status",
                        application.statusRepository.current(),
                    )
                    application.statusRepository.terminalFailure()?.let {
                        broadcastTerminalFailure(channel, it)
                    }
                }
                is BridgeRequest.GetLocalRouteCapabilities -> beginLocalCapabilities(request, payload, channel)
                is BridgeRequest.RegionalWork -> {
                    val status = application.regionalRoutingOperations.start(request.pageNonce, request.command)
                    completeBridgePayload(request, payload, channel, RegionalRoutingProtocol.reply(request.requestId, status))
                }
                is BridgeRequest.RegionalStatus -> {
                    val manager = application.regionalRoutingOperations
                    val status = if (request.cancel) manager.cancel(request.pageNonce, request.operationId)
                        else manager.status(request.pageNonce, request.operationId)
                    completeBridgePayload(request, payload, channel, RegionalRoutingProtocol.reply(request.requestId, status))
                }
                is BridgeRequest.LocalRoute -> beginLocalRoute(
                    request,
                    payload,
                    channel,
                )
                is BridgeRequest.RejectedLocalRoute -> completeBridgePayload(
                    request,
                    payload,
                    channel,
                    BridgeProtocol.localRouteFailure(request.requestId, request.code),
                )
                is BridgeRequest.StartTracking -> beginExplicitStart(
                    request,
                    payload,
                    channel,
                )
                is BridgeRequest.StopTracking -> {
                    val currentStatus = application.statusRepository.current()
                    if (
                        currentStatus.isNativeBusy() &&
                        (
                            currentStatus.outingSlug != request.outingSlug ||
                                currentStatus.participantId != request.participantId
                            )
                    ) {
                        completeFailure(
                            request,
                            payload,
                            channel,
                            "different_participant_active",
                            request.outingSlug,
                            request.participantId,
                        )
                        return@addWebMessageListener
                    }
                    if (currentStatus.isNativeBusy()) {
                        startService(
                            Intent(this, LocationSharingService::class.java)
                                .setAction(LocationSharingService.ACTION_STOP),
                        )
                    }
                    val stoppingStatus = if (currentStatus.active) {
                        currentStatus.copy(active = false, state = "stopping")
                    } else {
                        currentStatus
                    }
                    completeBridgeRequest(
                        request,
                        payload,
                        channel,
                        "stop_result",
                        stoppingStatus,
                    )
                }
                is BridgeRequest.AcknowledgeTerminalFailure -> {
                    application.statusRepository.acknowledgeTerminalFailure(
                        request.eventId,
                        request.outingSlug,
                        request.participantId,
                    )
                    completeBridgeRequest(
                        request,
                        payload,
                        channel,
                        "tracking_status",
                        application.statusRepository.current(),
                    )
                }
            }
        }
    }

    private fun beginLocalCapabilities(
        request: BridgeRequest.GetLocalRouteCapabilities,
        payload: String,
        channel: BridgeChannel,
    ) {
        if (localRouteWorkerBusy) {
            completeBridgePayload(request, payload, channel,
                BridgeProtocol.localRouteFailure(request.requestId, NativeRouteFailureCode.ROUTING_BUSY))
            return
        }
        pendingLocalCapabilities = request
        localRouteWorkerBusy = true
        localRouteExecutor.execute {
            val reply = try {
                BridgeProtocol.localRouteCapabilitiesReply(request.requestId,
                    nativeRouteEngine.capabilities(request.regionalReference))
            } catch (_: Exception) {
                BridgeProtocol.localRouteFailure(request.requestId, NativeRouteFailureCode.ROUTING_PACK_UNAVAILABLE)
            }
            runOnUiThread {
                localRouteWorkerBusy = false
                if (pendingLocalCapabilities !== request) return@runOnUiThread
                pendingLocalCapabilities = null
                completeBridgePayload(request, payload, channel, reply)
            }
        }
    }

    private fun beginLocalRoute(
        request: BridgeRequest.LocalRoute,
        payload: String,
        channel: BridgeChannel,
    ) {
        if (pendingLocalRoute != null || localRouteWorkerBusy) {
            completeLocalRouteFailure(
                request,
                payload,
                channel,
                NativeRouteFailureCode.ROUTING_BUSY,
            )
            return
        }
        val operation = PendingLocalRoute(request, payload, channel)
        pendingLocalRoute = operation
        localRouteWorkerBusy = true
        localRouteExecutor.execute {
            val result = nativeRouteEngine.route(request.routeRequest)
            runOnUiThread {
                localRouteWorkerBusy = false
                if (pendingLocalRoute !== operation) return@runOnUiThread
                pendingLocalRoute = null
                when (result) {
                    is NativeRouteResult.Success -> {
                        val reply = BridgeProtocol.localRouteReply(request.requestId, result)
                        if (reply == null) {
                            completeLocalRouteFailure(
                                request,
                                payload,
                                channel,
                                NativeRouteFailureCode.ROUTE_TOO_LARGE,
                            )
                        } else {
                            completeBridgePayload(request, payload, channel, reply)
                        }
                    }
                    is NativeRouteResult.Failure -> completeLocalRouteFailure(
                        request,
                        payload,
                        channel,
                        result.code,
                    )
                }
            }
        }
    }

    private fun completeLocalRouteFailure(
        request: BridgeRequest.LocalRoute,
        payload: String,
        channel: BridgeChannel,
        code: NativeRouteFailureCode,
    ) {
        completeBridgePayload(
            request,
            payload,
            channel,
            BridgeProtocol.localRouteFailure(request.requestId, code),
        )
    }

    private fun beginExplicitStart(
        request: BridgeRequest.StartTracking,
        payload: String,
        channel: BridgeChannel,
    ) {
        val origin = configuredOrigin
        val current = application.statusRepository.current()
        if (!activityVisible || origin == null || request.serverOrigin != origin) {
            completeFailure(
                request,
                payload,
                channel,
                "native_tracking_failure",
                request.outingSlug,
                request.participantId,
            )
            return
        }
        if (pendingStart != null) {
            completeFailure(
                request,
                payload,
                channel,
                "start_in_progress",
                request.outingSlug,
                request.participantId,
            )
            return
        }
        if (current.isNativeBusy()) {
            if (current.state == "stopping") {
                completeFailure(
                    request,
                    payload,
                    channel,
                    "stop_in_progress",
                    request.outingSlug,
                    request.participantId,
                )
                return
            }
            if (
                current.outingSlug == request.outingSlug &&
                current.participantId == request.participantId
            ) {
                completeBridgeRequest(
                    request,
                    payload,
                    channel,
                    "start_result",
                    current,
                )
            } else {
                completeFailure(
                    request,
                    payload,
                    channel,
                    "different_participant_active",
                    request.outingSlug,
                    request.participantId,
                )
            }
            return
        }
        if (!request.outingExpiresAt.isAfter(Instant.now())) {
            completeFailure(
                request,
                payload,
                channel,
                "outing_not_found",
                request.outingSlug,
                request.participantId,
            )
            return
        }
        val operation = PendingStart(request, payload, channel)
        pendingStart = operation
        val disclosure = AlertDialog.Builder(this)
            .setTitle("Share precise location with the screen off?")
            .setMessage(DISCLOSURE)
            .setNegativeButton("Cancel") { _, _ ->
                finishPendingStart(operation, "permission_denied")
            }.setPositiveButton("Continue") { _, _ -> requestTrackingPermissions(operation) }
            .setNeutralButton(R.string.privacy_title, null)
            .setOnCancelListener { finishPendingStart(operation, "permission_denied") }
            .create()
        disclosure.setOnShowListener {
            // Reading privacy details does not dismiss disclosure or grant Start.
            disclosure.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {
                if (pendingStart === operation && activityVisible) showPrivacyDetails()
            }
        }
        disclosure.show()
    }

    private fun requestTrackingPermissions(operation: PendingStart) {
        if (pendingStart !== operation || !activityVisible) {
            finishPendingStart(operation, "permission_denied")
            return
        }
        val permissions = buildList {
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (permissions.isEmpty()) {
            continueStartAfterPermissions(operation)
        } else {
            requestPermissions(permissions.toTypedArray(), REQUEST_TRACKING_PERMISSIONS)
        }
    }

    private fun continueStartAfterPermissions(operation: PendingStart) {
        val manager = getSystemService(LocationManager::class.java)
        val request = operation.request
        val current = application.statusRepository.current()
        val decision = StartPolicy.decide(
            StartConditions(
                explicitRequest = pendingStart === operation,
                disclosureConfirmed = true,
                activityVisible = activityVisible,
                preciseLocationGranted = checkSelfPermission(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                ) == PackageManager.PERMISSION_GRANTED,
                notificationsGranted = Build.VERSION.SDK_INT < 33 || checkSelfPermission(
                    Manifest.permission.POST_NOTIFICATIONS,
                ) == PackageManager.PERMISSION_GRANTED,
                locationServicesEnabled = locationServicesEnabled(manager),
                currentStatus = current,
                requestedIdentity = request.outingSlug to request.participantId,
            ),
        )
        if (decision is StartDecision.Rejected && decision.code == "location_disabled") {
            AlertDialog.Builder(this)
                .setTitle("Turn on location services")
                .setMessage("Device location services must be enabled before sharing can start.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Location settings") { _, _ ->
                    startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
                }.show()
            finishPendingStart(operation, "location_disabled")
            return
        }
        if (decision is StartDecision.Rejected) {
            finishPendingStart(operation, decision.code)
            return
        }
        if (decision is StartDecision.AlreadyActive) {
            pendingStart = null
            completeBridgeRequest(
                request,
                operation.payload,
                operation.channel,
                "start_result",
                current,
            )
            return
        }
        val session = ParticipantSession(
            serverOrigin = request.serverOrigin,
            outingSlug = request.outingSlug,
            participantId = request.participantId,
            participantToken = request.participantToken,
            outingExpiresAt = request.outingExpiresAt,
            lastAcceptedSequence = request.currentSequence,
            startedAt = Instant.now(),
        )
        if (!session.isValid(Instant.now())) {
            finishPendingStart(operation, "native_tracking_failure")
            return
        }
        if (application.secureStore.saveSession(session) != StoreMutationResult.APPLIED) {
            finishPendingStart(operation, "native_tracking_failure")
            return
        }
        val starting = NativeTrackingStatus(
            outingSlug = session.outingSlug,
            participantId = session.participantId,
            active = true,
            state = "starting",
            lastPublishedAt = null,
            pendingSample = false,
            stopWarning = null,
        )
        application.statusRepository.activate(session, starting)
        try {
            ContextCompat.startForegroundService(
                this,
                Intent(this, LocationSharingService::class.java)
                    .setAction(LocationSharingService.ACTION_START),
            )
        } catch (_: Exception) {
            application.secureStore.clearMatchingSession(session)
            application.statusRepository.update(NativeTrackingStatus.stopped())
            finishPendingStart(operation, "native_tracking_failure")
            return
        }
        pendingStart = null
        completeBridgeRequest(
            request,
            operation.payload,
            operation.channel,
            "start_result",
            starting,
        )
    }

    private fun finishPendingStart(operation: PendingStart, code: String) {
        if (pendingStart !== operation) return
        pendingStart = null
        completeFailure(
            operation.request,
            operation.payload,
            operation.channel,
            code,
            operation.request.outingSlug,
            operation.request.participantId,
        )
    }

    private fun completeBridgeRequest(
        request: BridgeRequest,
        payload: String,
        channel: BridgeChannel,
        type: String,
        status: NativeTrackingStatus,
    ) {
        val reply = BridgeProtocol.reply(type, request.requestId, status)
        bridgeLedger.complete(request, payload, reply)
        postToBridge(channel, reply)
    }

    private fun completeBridgePayload(
        request: BridgeRequest,
        payload: String,
        channel: BridgeChannel,
        reply: String,
    ) {
        bridgeLedger.complete(request, payload, reply)
        postToBridge(channel, reply)
    }

    private fun completeFailure(
        request: BridgeRequest,
        payload: String,
        channel: BridgeChannel,
        code: String,
        outingSlug: String? = null,
        participantId: String? = null,
    ) {
        val reply = BridgeProtocol.failure(
            request.requestId,
            code,
            outingSlug = outingSlug,
            participantId = participantId,
        )
        bridgeLedger.complete(request, payload, reply)
        postToBridge(channel, reply)
    }

    private fun broadcastStatus(status: NativeTrackingStatus) {
        if (configuredOrigin == BundledShellPolicy.ORIGIN) return
        val channel = activeBridgeChannel ?: return
        bridgeStatusCounter += 1
        postToBridge(
            channel,
            BridgeProtocol.reply(
                "tracking_status",
                "native-${channel.pageNonce}-$bridgeStatusCounter",
                status,
            ),
        )
    }

    private fun broadcastTerminalFailure(event: NativeTerminalFailureEvent) {
        val channel = activeBridgeChannel ?: return
        broadcastTerminalFailure(channel, event)
    }

    private fun broadcastTerminalFailure(
        channel: BridgeChannel,
        event: NativeTerminalFailureEvent,
    ) {
        if (configuredOrigin == BundledShellPolicy.ORIGIN) return
        bridgeStatusCounter += 1
        postToBridge(
            channel,
            BridgeProtocol.failure(
                "native-${channel.pageNonce}-$bridgeStatusCounter",
                event.code,
                eventId = event.eventId,
                outingSlug = event.outingSlug,
                participantId = event.participantId,
            ),
        )
    }

    private fun postToBridge(channel: BridgeChannel, payload: String) {
        if (
            activeBridgeChannel === channel &&
            webView != null &&
            System.identityHashCode(webView) == channel.webViewIdentity &&
            bridgeNavigationEpoch == channel.navigationEpoch &&
            WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)
        ) channel.replyProxy.postMessage(payload)
    }

    private fun acceptBridgePage(
        request: BridgeRequest,
        replyProxy: JavaScriptReplyProxy,
        sourceView: WebView,
    ): BridgeChannel? {
        val existing = activeBridgeChannel
        if (existing == null) {
            if (request !is BridgeRequest.Hello) return null
            return BridgeChannel(
                pageNonce = request.pageNonce,
                replyProxy = replyProxy,
                webViewIdentity = System.identityHashCode(sourceView),
                navigationEpoch = bridgeNavigationEpoch,
            ).also { activeBridgeChannel = it }
        }
        if (
            existing.pageNonce != request.pageNonce ||
            existing.webViewIdentity != System.identityHashCode(sourceView) ||
            existing.navigationEpoch != bridgeNavigationEpoch
        ) return null
        existing.replyProxy = replyProxy
        return existing
    }

    private fun invalidateBridgePage() {
        activeBridgeChannel?.let { application.regionalRoutingOperations.cancelOwner(it.pageNonce) }
        gpxDocumentSaver.invalidate()
        webGeolocationPermissions.invalidate()
        bridgeNavigationEpoch += 1
        activeBridgeChannel = null
        pendingStart = null
        pendingLocalRoute = null
        pendingLocalCapabilities = null
    }

    private fun destroyWebView() {
        invalidateBridgePage()
        val old = webView ?: return
        webView = null
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            WebViewCompat.removeWebMessageListener(old, BridgeProtocol.OBJECT_NAME)
        }
        old.stopLoading()
        old.webViewClient = WebViewClient()
        old.webChromeClient = WebChromeClient()
        old.removeAllViews()
        old.destroy()
    }

    private fun deepLinkSlug(intent: Intent?): String? {
        val data = intent?.data ?: return null
        if (data.scheme != "sugarglider" || data.host != "o") return null
        val segments = data.pathSegments
        if (segments.size != 1 || data.query != null || data.fragment != null) return null
        return segments.single().takeIf(OUTING_SLUG_PATTERN::matches)
    }

    private fun handleAndroidBack(navigateSystemBack: () -> Unit) {
        val current = webView
        val decision = BackNavigationPolicy.decide(
            currentUrl = current?.url,
            configuredOrigin = configuredOrigin,
            canGoBack = current?.canGoBack() == true,
            trackingStatus = application.statusRepository.current(),
        )
        BackNavigationController.handle(
            decision = decision,
            navigateWebViewBack = {
                if (current === webView && current?.canGoBack() == true) current.goBack()
            },
            navigateSystemBack = navigateSystemBack,
            moveTaskToBackground = { moveTaskToBack(true) },
            showOutingConfirmation = ::showOutingLeaveConfirmation,
        )
    }

    @Suppress("DEPRECATION")
    private fun performLegacySystemBack() {
        super.onBackPressed()
    }

    private fun showOutingLeaveConfirmation(
        decision: BackNavigationDecision.ConfirmOutingLeave,
        leaveScreen: () -> Unit,
    ) {
        if (outingLeaveDialog?.isShowing == true) return
        val message = if (decision.backgroundSharingContinues) {
            getString(R.string.outing_back_sharing_continues)
        } else {
            getString(R.string.outing_back_returns_to_previous)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.outing_back_title)
            .setMessage(message)
            .setPositiveButton(R.string.outing_back_stay, null)
            .setNegativeButton(R.string.outing_back_leave) { _, _ -> leaveScreen() }
            .create()
        outingLeaveDialog = dialog
        dialog.setOnDismissListener {
            if (outingLeaveDialog === dialog) outingLeaveDialog = null
        }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE)?.requestFocus()
        }
        dialog.show()
    }

    private fun dismissOutingLeaveDialog() {
        outingLeaveDialog?.dismiss()
        outingLeaveDialog = null
    }

    private fun registerPredictiveBackCallback() {
        if (Build.VERSION.SDK_INT < 33) return
        val callback = OnBackInvokedCallback {
            handleAndroidBack(::finishAfterTransition)
        }
        backInvokedCallback = callback
        onBackInvokedDispatcher.registerOnBackInvokedCallback(
            OnBackInvokedDispatcher.PRIORITY_DEFAULT,
            callback,
        )
    }

    private fun unregisterPredictiveBackCallback() {
        if (Build.VERSION.SDK_INT < 33) return
        backInvokedCallback?.let(onBackInvokedDispatcher::unregisterOnBackInvokedCallback)
        backInvokedCallback = null
    }

    private fun fullWidthWrap(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    )

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private data class PendingStart(
        val request: BridgeRequest.StartTracking,
        val payload: String,
        val channel: BridgeChannel,
    )

    private data class PendingLocalRoute(
        val request: BridgeRequest.LocalRoute,
        val payload: String,
        val channel: BridgeChannel,
    )

    private class BridgeChannel(
        val pageNonce: String,
        var replyProxy: JavaScriptReplyProxy,
        val webViewIdentity: Int,
        val navigationEpoch: Long,
    )

    companion object {
        private const val PREFERENCE_SERVER_ORIGIN = "server_origin"
        private const val STATE_GPX_SAVE_PENDING = "gpx_save_pending"
        private const val STATE_SHARING_SCREEN = "sharing_screen"
        private const val REQUEST_GPX_DOCUMENT = 41
        private const val REQUEST_TRACKING_PERMISSIONS = 27
        private const val REQUEST_WEB_GEOLOCATION_PERMISSION = 31
        private const val DEBUG_DEFAULT_ORIGIN = "http://10.0.2.2:8000"
        private const val DISCLOSURE =
            "Sugarglider will continuously access and send precise location during this active sharing session, including while the app is minimized or the screen is locked. Anyone holding the unlisted outing link can see your position. The server stores your current position and briefly retains recent updates so viewers can reconnect. This does not create an activity track. A persistent notification is displayed, and you can stop at any time from the app or notification. If server clearing is uncertain, the last position may remain visible until expiry."
    }
}
