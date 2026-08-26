package io.github.victorgabillon.sugarglider

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

class LocationSharingService : Service() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var application: SugargliderApplication
    private lateinit var scheduler: NativeTaskScheduler
    private lateinit var engine: NativeTrackingEngine
    private val startIdGuard = ServiceStartIdGuard()
    private var foregroundStarted = false
    private var destroyed = false

    override fun onCreate() {
        super.onCreate()
        application = getApplication() as SugargliderApplication
        scheduler = ExecutorTaskScheduler()
        createNotificationChannel()
        engine = NativeTrackingEngine(
            store = application.secureStore,
            publisher = NativeOutingApi(),
            locationSource = AndroidLocationSource(this),
            scheduler = scheduler,
            clock = SystemAppClock(),
            statusSink = { session, status ->
                val serviceStatus = if (!status.active && status.state == "stopped") {
                    status.copy(state = "stopping")
                } else {
                    status
                }
                application.statusRepository.updateForSession(session, serviceStatus)
            },
            terminalSink = { failedSession, code, clearCurrentStatus ->
                application.statusRepository.recordTerminalFailure(
                    failedSession,
                    code,
                    clearCurrentStatus,
                )
            },
            notificationSink = ::updateNotification,
            stoppedSink = ::stopFromEngine,
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                startIdGuard.recordStart(startId)
                startFromExplicitActivity()
            }
            ACTION_STOP -> {
                startIdGuard.recordStop(startId)
                if (!engine.stop()) stopFromEngine()
            }
            else -> {
                startIdGuard.recordStop(startId)
                if (!engine.stop()) stopFromEngine()
            }
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        if (!destroyed) {
            destroyed = true
            engine.destroy()
        }
        application.statusRepository.completeServiceShutdown()
        removeForegroundNotification()
        super.onDestroy()
    }

    private fun startFromExplicitActivity() {
        if (
            checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            application.statusRepository.update(NativeTrackingStatus.stopped())
            stopFromEngine()
            return
        }
        val starting = application.statusRepository.current().takeIf { it.active }
            ?: NativeTrackingStatus(
                outingSlug = null,
                participantId = null,
                active = true,
                state = "starting",
                lastPublishedAt = null,
                pendingSample = false,
                stopWarning = null,
            )
        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification(starting),
                if (Build.VERSION.SDK_INT >= 29) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
                } else {
                    0
                },
            )
            foregroundStarted = true
        } catch (_: Exception) {
            application.statusRepository.update(
                NativeTrackingStatus.stopped(SafeText.STORAGE_FAILURE),
            )
            stopFromEngine()
            return
        }
        engine.startStored()
    }

    private fun createNotificationChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.notification_channel_description)
                setShowBadge(false)
            },
        )
    }

    private fun notification(status: NativeTrackingStatus): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
            ),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stopIntent = PendingIntent.getService(
            this,
            2,
            Intent(this, LocationSharingService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(R.drawable.sugarglider_app_icon)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(SafeText.notification(status.state, status.lastPublishedAt))
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .addAction(0, getString(R.string.notification_open), openIntent)
            .addAction(0, getString(R.string.notification_stop), stopIntent)
            .build()
    }

    private fun updateNotification(status: NativeTrackingStatus) {
        if (!foregroundStarted) return
        getSystemService(NotificationManager::class.java).notify(
            NOTIFICATION_ID,
            notification(status),
        )
    }

    private fun stopFromEngine(session: ParticipantSession? = null) {
        if (!application.statusRepository.markServiceShutdownPending(session)) return
        val capturedStartId = startIdGuard.captureStopStartId()
        mainHandler.post {
            if (!startIdGuard.stopStillOwnsService(capturedStartId)) return@post
            if (stopSelfResult(capturedStartId)) removeForegroundNotification()
        }
    }

    private fun removeForegroundNotification() {
        if (!foregroundStarted) return
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        foregroundStarted = false
    }

    companion object {
        internal const val ACTION_START =
            "io.github.victorgabillon.sugarglider.action.START_LOCATION_SHARING"
        internal const val ACTION_STOP =
            "io.github.victorgabillon.sugarglider.action.STOP_LOCATION_SHARING"
        private const val NOTIFICATION_CHANNEL_ID = "sugarglider_live_location"
        private const val NOTIFICATION_ID = 27
    }
}
