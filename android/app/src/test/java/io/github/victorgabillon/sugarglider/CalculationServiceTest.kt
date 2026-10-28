package io.github.victorgabillon.sugarglider

import android.app.NotificationManager
import android.content.Intent
import android.os.Looper
import java.time.Duration
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], application = SugargliderApplication::class)
class CalculationServiceTest {
    @Test fun notificationReadinessThreeMinutesTimeoutAndExplicitCancel() {
        val app = RuntimeEnvironment.getApplication() as SugargliderApplication
        val operation = app.calculations
        // Isolate Android Keystore I/O; service, notification and clocks are real shadows.
        CalculationOperation::class.java.getDeclaredField("persist").apply { isAccessible = true }
            .set(operation, { _: JSONObject -> Unit })
        val id = "a".repeat(32); val owner = "b".repeat(32)
        var ready = 0; var cancelled = 0
        operation.begin(id, owner, "adventure", "Private location description", { ready++ }) { cancelled++ }
        val controller = Robolectric.buildService(CalculationService::class.java).create()
        val service = controller.get()
        val start = Intent(app, CalculationService::class.java).setAction(CalculationService.ACTION_START).putExtra(CalculationService.EXTRA_ID, id)
        assertEquals(android.app.Service.START_NOT_STICKY, service.onStartCommand(start, 0, 1))
        assertEquals(1, ready)
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMinutes(1))
        assertEquals(id, operation.activeId)
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMinutes(2))
        assertEquals(id, operation.activeId)
        val notifications = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications
        assertEquals(1, notifications.size)
        assertFalse(notifications[0].extras.toString().contains("Private location description"))
        assertEquals(1, notifications[0].actions.size)
        service.onStartCommand(start, 0, 2); assertEquals(1, ready)
        service.onStartCommand(Intent(app, CalculationService::class.java).setAction(CalculationService.ACTION_CANCEL)
            .putExtra(CalculationService.EXTRA_ID, "c".repeat(32)), 0, 3)
        assertEquals(id, operation.activeId)
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMinutes(7))
        assertNull(operation.activeId); assertEquals(1, cancelled)
        controller.destroy()
    }
    @Test fun destroyedServiceNeverRestartsOrReplaysWork() {
        val app = RuntimeEnvironment.getApplication() as SugargliderApplication
        val service = Robolectric.buildService(CalculationService::class.java).create().get()
        assertEquals(android.app.Service.START_NOT_STICKY, service.onStartCommand(null, 0, 1))
        assertNull(app.calculations.activeId)
        service.onTimeout(1, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        service.onDestroy()
    }
}
