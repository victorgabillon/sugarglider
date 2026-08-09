package io.github.victorgabillon.sugarglider

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
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
import android.webkit.HttpAuthHandler
import android.webkit.SslErrorHandler
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.time.Instant

class MainActivity : Activity() {
    private lateinit var application: SugargliderApplication
    private var configuredOrigin: String? = null
    private var webView: WebView? = null
    private var activeBridgeChannel: BridgeChannel? = null
    private var bridgeNavigationEpoch = 0L
    private var bridgeStatusCounter = 0L
    private var activityVisible = false
    private var pendingStart: PendingStart? = null
    private var pendingDeepLinkSlug: String? = null
    private var backInvokedCallback: OnBackInvokedCallback? = null
    private var outingLeaveDialog: AlertDialog? = null
    private val bridgeLedger = BridgeRequestLedger()
    private val statusObserver = NativeStatusRepository.Observer { status, terminalFailure ->
        runOnUiThread {
            broadcastStatus(status)
            if (terminalFailure != null) broadcastTerminalFailure(terminalFailure)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        application = getApplication() as SugargliderApplication
        application.statusRepository.addObserver(statusObserver)
        registerPredictiveBackCallback()
        pendingDeepLinkSlug = deepLinkSlug(intent)
        val stored = getPreferences(MODE_PRIVATE).getString(PREFERENCE_SERVER_ORIGIN, null)
        val validStored = stored?.let {
            ServerOrigin.parse(it, BuildConfig.ALLOW_HTTP)?.normalized
        }
        if (validStored == null) showServerConfiguration() else openServer(validStored)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deepLinkSlug(intent)?.let {
            pendingDeepLinkSlug = it
            loadConfiguredPage()
        }
    }

    override fun onResume() {
        super.onResume()
        activityVisible = true
    }

    override fun onPause() {
        activityVisible = false
        super.onPause()
    }

    override fun onDestroy() {
        pendingStart = null
        dismissOutingLeaveDialog()
        unregisterPredictiveBackCallback()
        application.statusRepository.removeObserver(statusObserver)
        destroyWebView()
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
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
                if (origin == null) {
                    error.text = if (BuildConfig.ALLOW_HTTP) {
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
        setContentView(root)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun openServer(origin: String) {
        destroyWebView()
        configuredOrigin = origin
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(getColor(R.color.brand_cream))
        }
        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(6), dp(8), dp(6))
            setBackgroundColor(getColor(R.color.brand_green))
        }
        toolbar.addView(TextView(this).apply {
            text = origin
            setTextColor(Color.WHITE)
            maxLines = 1
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        toolbar.addView(Button(this).apply {
            setText(R.string.configure_change)
            setOnClickListener {
                if (!ServerChangePolicy.allowed(application.statusRepository.current())) {
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Stop sharing first")
                        .setMessage(
                            "Stop Android background sharing before changing server. Participant authority is never transferred to another origin.",
                        ).setPositiveButton("OK", null)
                        .show()
                } else {
                    getPreferences(MODE_PRIVATE).edit { remove(PREFERENCE_SERVER_ORIGIN) }
                    showServerConfiguration()
                }
            }
        })
        root.addView(toolbar, fullWidthWrap())
        val created = WebView(this)
        webView = created
        created.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            setSupportMultipleWindows(false)
        }
        created.setBackgroundColor(getColor(R.color.brand_cream))
        created.webViewClient = originIsolatingClient(origin)
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
        loadConfiguredPage()
    }

    private fun loadConfiguredPage() {
        val origin = configuredOrigin ?: return
        val slug = pendingDeepLinkSlug.also { pendingDeepLinkSlug = null }
        webView?.loadUrl(if (slug == null) "$origin/" else "$origin/o/$slug")
    }

    private fun originIsolatingClient(origin: String): WebViewClient = object : WebViewClient() {
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
            if (
                current == null ||
                !BridgeGate.accepts(
                    sourceOrigin.toString(),
                    origin,
                    isMainFrame,
                    System.identityHashCode(current),
                    System.identityHashCode(sourceView),
                )
            ) return@addWebMessageListener
            val payload = message.data ?: return@addWebMessageListener
            val request = BridgeProtocol.parse(payload) ?: return@addWebMessageListener
            val channel = acceptBridgePage(request, replyProxy, sourceView) ?: return@addWebMessageListener
            bridgeLedger.lookup(request, payload)?.let {
                replyProxy.postMessage(it)
                return@addWebMessageListener
            }
            if (!bridgeLedger.begin(request, payload)) return@addWebMessageListener
            when (request) {
                is BridgeRequest.Hello -> completeBridgeRequest(
                    request,
                    payload,
                    channel,
                    "hello_result",
                    application.statusRepository.current(),
                )
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
        AlertDialog.Builder(this)
            .setTitle("Share precise location with the screen off?")
            .setMessage(DISCLOSURE)
            .setNegativeButton("Cancel") { _, _ ->
                finishPendingStart(operation, "permission_denied")
            }.setPositiveButton("Continue") { _, _ -> requestTrackingPermissions(operation) }
            .setOnCancelListener { finishPendingStart(operation, "permission_denied") }
            .show()
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
        bridgeNavigationEpoch += 1
        activeBridgeChannel = null
        pendingStart = null
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

    private class BridgeChannel(
        val pageNonce: String,
        var replyProxy: JavaScriptReplyProxy,
        val webViewIdentity: Int,
        val navigationEpoch: Long,
    )

    companion object {
        private const val PREFERENCE_SERVER_ORIGIN = "server_origin"
        private const val REQUEST_TRACKING_PERMISSIONS = 27
        private const val DEBUG_DEFAULT_ORIGIN = "http://10.0.2.2:8000"
        private const val DISCLOSURE =
            "Sugarglider will continuously access precise location during this active sharing session, including while the app is minimized or the screen is locked. Anyone holding the unlisted outing link can see the current position. Only the latest current position is retained, not a historical track. A persistent notification is displayed, and you can stop at any time from the app or notification. If server clearing is uncertain, the last position may remain visible until expiry."
    }
}
