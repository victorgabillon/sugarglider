package io.github.victorgabillon.sugarglider

import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import org.junit.Assert.*
import org.junit.Test

class ChatGptForegroundGateTest {
    @Test fun callbackWaitsForExplicitActivityReturn() {
        val gate = ChatGptForegroundGate()
        val worker = Executors.newSingleThreadExecutor()
        val started = CountDownLatch(1)
        try {
            val result = worker.submit<Unit> { started.countDown(); gate.awaitForeground(5000) { false } }
            assertTrue(started.await(5,TimeUnit.SECONDS))
            assertThrows(TimeoutException::class.java) { result.get(30,TimeUnit.MILLISECONDS) }
            gate.resumed()
            result.get(5,TimeUnit.SECONDS)
        } finally { gate.close(); worker.shutdownNow() }
    }
    @Test fun cancellationWinsOverAVisibleActivity() {
        val gate = ChatGptForegroundGate(); gate.resumed()
        val error = assertThrows(ChatGptException::class.java) { gate.awaitForeground(5000) { true } }
        assertEquals(ChatGptFailureKind.CANCELLED,error.kind)
    }
    @Test fun expiredBrowserBudgetDoesNotStartAnotherWait() {
        val gate = ChatGptForegroundGate()
        val error = assertThrows(ChatGptException::class.java) { gate.awaitForeground(0) { false } }
        assertEquals(ChatGptFailureKind.AUTH_TIMEOUT,error.kind)
    }
    @Test fun pauseInvalidatesThePreviousForegroundAndDestructionReleasesTheWait() {
        val gate = ChatGptForegroundGate(); gate.resumed(); gate.paused()
        val worker = Executors.newSingleThreadExecutor()
        val started = CountDownLatch(1)
        try {
            val result = worker.submit<Unit> { started.countDown(); gate.awaitForeground(5000) { false } }
            assertTrue(started.await(5,TimeUnit.SECONDS))
            assertThrows(TimeoutException::class.java) { result.get(30,TimeUnit.MILLISECONDS) }
            gate.close()
            val error = assertThrows(ExecutionException::class.java) { result.get(5,TimeUnit.SECONDS) }
            assertEquals(ChatGptFailureKind.CANCELLED,(error.cause as ChatGptException).kind)
        } finally { gate.close(); worker.shutdownNow() }
    }
}
