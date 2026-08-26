package io.github.victorgabillon.sugarglider

import android.Manifest
import android.app.Application
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import java.net.CookieHandler
import java.time.Instant
import java.util.concurrent.CopyOnWriteArraySet

internal class NativeStatusRepository {
    fun interface Observer {
        fun onStatus(status: NativeTrackingStatus, terminalFailure: NativeTerminalFailureEvent?)
    }

    private val observers = CopyOnWriteArraySet<Observer>()

    @Volatile
    private var current = NativeTrackingStatus.stopped()

    @Volatile
    private var terminalFailure: NativeTerminalFailureEvent? = null

    private var terminalSession: ParticipantSession? = null
    private var activeSession: ParticipantSession? = null
    private var nextEventId = 0L

    fun current(): NativeTrackingStatus = current

    fun terminalFailure(): NativeTerminalFailureEvent? = terminalFailure

    @Synchronized
    fun markServiceShutdownPending(session: ParticipantSession?): Boolean {
        val identityMatches = session != null && (
            activeSession?.identityMatches(session) == true ||
                terminalSession?.identityMatches(session) == true
            )
        if (session != null && current.isNativeBusy() && !identityMatches) return false
        if (current.state == "stopping" && (session == null || identityMatches)) return true
        current = NativeTrackingStatus(
            outingSlug = session?.outingSlug ?: current.outingSlug,
            participantId = session?.participantId ?: current.participantId,
            active = false,
            state = "stopping",
            lastPublishedAt = current.lastPublishedAt,
            pendingSample = false,
            stopWarning = current.stopWarning,
        )
        observers.forEach { it.onStatus(current, null) }
        return true
    }

    @Synchronized
    fun completeServiceShutdown() {
        if (current.state != "stopping") return
        current = NativeTrackingStatus.stopped(current.stopWarning)
        activeSession = null
        observers.forEach { it.onStatus(current, null) }
    }

    fun update(status: NativeTrackingStatus) {
        current = status
        observers.forEach { it.onStatus(status, null) }
    }

    @Synchronized
    fun activate(session: ParticipantSession, status: NativeTrackingStatus) {
        activeSession = session
        current = status
        observers.forEach { it.onStatus(status, null) }
    }

    @Synchronized
    fun updateForSession(
        session: ParticipantSession?,
        status: NativeTrackingStatus,
    ): Boolean {
        if (session == null || activeSession?.identityMatches(session) != true) return false
        current = status
        if (!status.active && status.state !in setOf("stopping", "stopped")) {
            activeSession = null
        }
        observers.forEach { it.onStatus(status, null) }
        return true
    }

    @Synchronized
    fun recordTerminalFailure(
        failedSession: ParticipantSession,
        code: String,
        clearCurrentStatus: Boolean,
    ): NativeTerminalFailureEvent {
        val existing = terminalFailure
        if (
            existing != null &&
            terminalSession?.identityMatches(failedSession) == true &&
            existing.code == SafeText.safeFailureCode(code)
        ) return existing
        nextEventId += 1
        val event = NativeTerminalFailureEvent(
            eventId = nextEventId,
            outingSlug = failedSession.outingSlug,
            participantId = failedSession.participantId,
            code = SafeText.safeFailureCode(code),
        )
        terminalFailure = event
        terminalSession = failedSession
        if (clearCurrentStatus && activeSession?.identityMatches(failedSession) == true) {
            current = NativeTrackingStatus(
                outingSlug = failedSession.outingSlug,
                participantId = failedSession.participantId,
                active = false,
                state = "stopping",
                lastPublishedAt = current.lastPublishedAt,
                pendingSample = false,
                stopWarning = current.stopWarning,
            )
        }
        observers.forEach { it.onStatus(current, event) }
        return event
    }

    @Synchronized
    fun acknowledgeTerminalFailure(
        eventId: Long,
        outingSlug: String,
        participantId: String,
    ): Boolean {
        val event = terminalFailure ?: return false
        if (
            event.eventId != eventId ||
            event.outingSlug != outingSlug ||
            event.participantId != participantId
        ) return false
        terminalFailure = null
        terminalSession = null
        return true
    }

    fun addObserver(observer: Observer) {
        observers += observer
    }

    fun removeObserver(observer: Observer) {
        observers -= observer
    }
}

class SugargliderApplication : Application() {
    internal lateinit var secureStore: AndroidSecureStateStore
        private set
    internal val statusRepository = NativeStatusRepository()

    override fun onCreate() {
        super.onCreate()
        CookieHandler.setDefault(null)
        secureStore = AndroidSecureStateStore(this)
        // A record can survive only to protect the active foreground service's latest
        // sample. A newly created process never treats it as permission to resume.
        secureStore.clearAll()
    }
}

internal class SystemAppClock : AppClock {
    override fun now(): Instant = Instant.now()

    override fun epochMilliseconds(): Long = System.currentTimeMillis()

    override fun elapsedMilliseconds(): Long = SystemClock.elapsedRealtime()
}

internal interface LocationSource {
    fun start(onFix: (RawLocationFix) -> Unit, onUnavailable: () -> Unit): Boolean

    fun stop()
}

internal class AndroidLocationSource(private val context: Context) : LocationSource {
    private val manager = context.getSystemService(LocationManager::class.java)
    private var listener: LocationListener? = null

    override fun start(
        onFix: (RawLocationFix) -> Unit,
        onUnavailable: () -> Unit,
    ): Boolean {
        if (
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) !=
            PackageManager.PERMISSION_GRANTED ||
            !locationServicesEnabled(manager)
        ) return false
        stop()
        val nextListener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                onFix(
                    RawLocationFix(
                        latitude = location.latitude,
                        longitude = location.longitude,
                        accuracyM = location.accuracy.toDouble(),
                        capturedAtEpochMs = location.time,
                        altitudeM = if (location.hasAltitude()) location.altitude else null,
                        speedMS = if (location.hasSpeed()) location.speed.toDouble() else null,
                        headingDeg = if (location.hasBearing()) location.bearing.toDouble() else null,
                    ),
                )
            }

            override fun onProviderDisabled(provider: String) {
                onUnavailable()
            }

            override fun onProviderEnabled(provider: String) = Unit

            @Deprecated("Deprecated by Android")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
        }
        listener = nextListener
        return try {
            manager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                5_000L,
                0f,
                nextListener,
                context.mainLooper,
            )
            true
        } catch (_: SecurityException) {
            listener = null
            false
        } catch (_: IllegalArgumentException) {
            listener = null
            false
        }
    }

    override fun stop() {
        val oldListener = listener ?: return
        listener = null
        try {
            manager.removeUpdates(oldListener)
        } catch (_: SecurityException) {
            // Sampling is already invalidated by ownership before this best-effort removal.
        }
    }
}

internal fun locationServicesEnabled(manager: LocationManager): Boolean = if (Build.VERSION.SDK_INT >= 28) {
    manager.isLocationEnabled
} else {
    manager.isProviderEnabled(LocationManager.GPS_PROVIDER)
}
