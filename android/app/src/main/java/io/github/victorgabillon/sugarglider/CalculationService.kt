package io.github.victorgabillon.sugarglider

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

/** Bounded data fetch/local-file processing, started only by visible Generate. */
class CalculationService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val operations get() = (application as SugargliderApplication).calculations
    private var ownedId: String? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val timeout = Runnable { ownedId?.let { operations.cancel(it, "timeout") }; stopSelf() }
    private val idle: () -> Unit = { if (operations.activeId == null) { releaseResources(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() } }
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val id = intent?.getStringExtra(EXTRA_ID)
        if (intent?.action == ACTION_CANCEL) {
            if (id != null) operations.cancel(id)
            if (operations.activeId == null) stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action != ACTION_START || id == null || operations.activeId != id) { stopSelf(startId); return START_NOT_STICKY }
        // Re-delivery never resets the bound or acquires another lock.
        if (ownedId == id) return START_NOT_STICKY
        ownedId = id
        operations.onIdle = idle
        try {
            val manager = getSystemService(NotificationManager::class.java)
            val language = ApplicationLanguage.context(this)
            manager.createNotificationChannel(NotificationChannel(CHANNEL, language.getString(R.string.calculation_channel), NotificationManager.IMPORTANCE_LOW))
            val returnToApp = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val cancel = PendingIntent.getService(this, 1, Intent(this, CalculationService::class.java).setAction(ACTION_CANCEL).putExtra(EXTRA_ID, id),
                PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val notification = NotificationCompat.Builder(this, CHANNEL).setSmallIcon(R.drawable.sugarglider_app_icon)
                .setContentTitle(language.getString(R.string.calculation_title)).setContentText(language.getString(R.string.calculation_text))
                .setContentIntent(returnToApp).setOngoing(true).setSilent(true).setOnlyAlertOnce(true)
                .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
                .addAction(0, language.getString(R.string.calculation_cancel), cancel).build()
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification,
                if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0)
            // CPU may suspend during screen lock even with an FGS. One bounded
            // partial lock covers only this explicitly requested calculation.
            wakeLock = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Sugarglider:calculation").apply {
                setReferenceCounted(false); acquire(MAX_DURATION_MS)
            }
            handler.postDelayed(timeout, MAX_DURATION_MS)
            operations.ready(id)
        } catch (_: Exception) { operations.cancel(id, "interrupted"); stopSelf() }
        return START_NOT_STICKY
    }
    override fun onTimeout(startId: Int, fgsType: Int) { ownedId?.let { operations.cancel(it, "timeout") }; stopSelf() }
    override fun onTaskRemoved(rootIntent: Intent?) { ownedId?.let { operations.cancel(it, "interrupted") }; stopSelf() }
    private fun releaseResources() {
        handler.removeCallbacks(timeout)
        wakeLock?.let { if (it.isHeld) it.release() }; wakeLock = null
    }
    override fun onDestroy() {
        releaseResources()
        if (operations.onIdle === idle) operations.onIdle = null
        ownedId?.let { operations.cancel(it, "interrupted") }
        super.onDestroy()
    }
    companion object {
        internal const val ACTION_START = "io.github.victorgabillon.sugarglider.CALCULATION_START"
        internal const val ACTION_CANCEL = "io.github.victorgabillon.sugarglider.CALCULATION_CANCEL"
        internal const val EXTRA_ID = "operation_id"
        internal const val MAX_DURATION_MS = 600_000L
        private const val CHANNEL = "calculations"
        private const val NOTIFICATION_ID = 119
    }
}
