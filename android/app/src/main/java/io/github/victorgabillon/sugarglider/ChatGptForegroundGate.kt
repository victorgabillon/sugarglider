package io.github.victorgabillon.sugarglider

/** Browser callback receipt is not permission to use a background app's network.
 * Wait on the connection executor until the user returns to this Activity. */
internal class ChatGptForegroundGate {
    private val lock = Object()
    private var visible = false
    private var closed = false

    fun resumed() { synchronized(lock) { visible = true; lock.notifyAll() } }
    fun paused() { synchronized(lock) { visible = false } }
    fun close() { synchronized(lock) { closed = true; lock.notifyAll() } }

    fun awaitForeground(timeoutMillis: Long, cancelled: () -> Boolean) {
        require(timeoutMillis in 0..180_000)
        val deadline = System.nanoTime() + timeoutMillis * 1_000_000
        synchronized(lock) {
            while (true) {
                if (closed || cancelled()) throw ChatGptException(ChatGptFailureKind.CANCELLED)
                if (visible) return
                val remaining = deadline - System.nanoTime()
                if (remaining <= 0) throw ChatGptException(ChatGptFailureKind.AUTH_TIMEOUT)
                lock.wait(minOf(250, (remaining + 999_999) / 1_000_000))
            }
        }
    }
}
