package io.github.victorgabillon.sugarglider

import java.io.Closeable
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketTimeoutException
import java.nio.charset.StandardCharsets

/** A temporary OAuth callback listener, not an application HTTP service. */
internal class ChatGptLoopback : Closeable {
    private val socket = ServerSocket(0, 4, InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1)))
    val port: Int get() = socket.localPort

    fun awaitCode(transaction: ChatGptAuthorization, cancelled: () -> Boolean): ChatGptCode {
        val deadline = System.nanoTime() + 180_000_000_000L
        socket.soTimeout = 500
        var attempts = 0
        while (!cancelled() && System.nanoTime() < deadline && attempts < 32) {
            val connection = try { socket.accept() } catch (_: SocketTimeoutException) { continue }
            connection.use { client ->
                attempts += 1
                client.soTimeout = 3000
                try {
                    require(client.inetAddress.isLoopbackAddress)
                    val input = client.getInputStream()
                    var total = 0
                    fun line(): String {
                        val result = StringBuilder()
                        while (true) {
                            val c = input.read()
                            require(c >= 0 && ++total <= 16_384) { "Invalid callback request." }
                            if (c == 10) return result.toString().removeSuffix("\r")
                            require(c in 32..126 || c == 13) { "Invalid callback request." }
                            result.append(c.toChar())
                        }
                    }
                    val request = line().split(' ')
                    require(request.size == 3 && request[0] == "GET" && request[2] in setOf("HTTP/1.0", "HTTP/1.1"))
                    var host: String? = null
                    while (true) {
                        val header = line()
                        if (header.isEmpty()) break
                        if (header.substringBefore(':').equals("Host", ignoreCase = true)) {
                            require(host == null)
                            host = header.substringAfter(':').trim()
                        }
                    }
                    require(host == "127.0.0.1:$port" && request[1].startsWith("/auth/callback?"))
                    val code = transaction.receive("http://127.0.0.1:$port${request[1]}")
                    val body = "<!doctype html><meta name=viewport content='width=device-width'><title>Sugarglider</title><p>Sign-in received. Return to Sugarglider to finish connecting.</p>".toByteArray(StandardCharsets.UTF_8)
                    val headers = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src 'none'\r\nConnection: close\r\nContent-Length: ${body.size}\r\n\r\n"
                    client.getOutputStream().write(headers.toByteArray(StandardCharsets.US_ASCII) + body)
                    return code
                } catch (_: Exception) {
                    runCatching { client.getOutputStream().write("HTTP/1.1 400 Bad Request\r\nCache-Control: no-store\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray(StandardCharsets.US_ASCII)) }
                    if (!transaction.isActive()) throw IllegalStateException("ChatGPT sign-in was not completed.")
                }
            }
        }
        transaction.cancel()
        throw IllegalStateException("ChatGPT sign-in cancelled or timed out.")
    }

    override fun close(): Unit = socket.close()
}
