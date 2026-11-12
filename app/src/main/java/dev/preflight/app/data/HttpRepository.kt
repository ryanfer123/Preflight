package dev.preflight.app.data

import dev.preflight.app.domain.*
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

/** Bounded, server-only API client with a private signed-CSRF session. No backend keys. */
class HttpRepository(address: String) : PreflightRepository {
    private val base = ServerAddress.normalize(address)
    private var csrf = ""
    private var cookie = ""

    override fun connect(): Session {
        val payload = request("/api/v1/session")
        require(payload.getInt("api_version") == 1) { "This server API version is not supported." }
        csrf = payload.getString("csrf")
        return Session(payload.getString("extractor"))
    }

    private fun requireSession() { if (csrf.isEmpty()) connect() }
    override fun vendors(): List<Vendor> = JsonModels.vendors(request("/api/v1/vendors"))
    override fun report(id: String): Report = JsonModels.report(request("/api/v1/reports/${encode(id)}"))

    override fun check(invoice: Attachment, email: Attachment?, vendorId: Long?): Report {
        requireSession()
        require(invoice.bytes.size in 1..MAX_FILE && (email == null || email.bytes.size in 1..MAX_FILE)) {
            "Each selected file must contain at most 10 MiB."
        }
        val boundary = "Preflight" + UUID.randomUUID().toString().replace("-", "")
        val body = ByteArrayOutputStream()
        fun text(value: String) { body.write(value.toByteArray(Charsets.UTF_8)) }
        fun field(name: String, value: String) {
            text("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n")
        }
        fun file(field: String, attachment: Attachment) {
            val name = attachment.name.substringAfterLast('/').substringAfterLast('\\')
                .replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(100).ifBlank { "upload" }
            text("--$boundary\r\nContent-Disposition: form-data; name=\"$field\"; filename=\"$name\"\r\n")
            text("Content-Type: application/octet-stream\r\n\r\n")
            body.write(attachment.bytes); text("\r\n")
        }
        field("csrf", csrf)
        if (vendorId != null) field("vendor", vendorId.toString())
        file("invoice", invoice)
        email?.let { file("eml", it) }
        text("--$boundary--\r\n")
        return JsonModels.report(request("/api/v1/check", body.toByteArray(), "multipart/form-data; boundary=$boundary"))
    }

    override fun approve(vendorId: Long, account: String, actor: String, confirmed: Boolean) {
        require(confirmed && actor.isNotBlank() && actor.length <= 200) {
            "Confirm independent verification and enter your name."
        }
        requireSession()
        val fields = mapOf("csrf" to csrf, "account" to account, "actor" to actor, "confirmed" to "yes")
        val body = fields.entries.joinToString("&") { "${encode(it.key)}=${encode(it.value)}" }
        request("/api/v1/vendors/$vendorId/approve", body.toByteArray(), "application/x-www-form-urlencoded")
    }

    private fun request(path: String, body: ByteArray? = null, contentType: String = ""): JSONObject {
        val connection = URL(base + path).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 10_000
            connection.readTimeout = 210_000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("Accept", "application/json")
            if (cookie.isNotEmpty()) connection.setRequestProperty("Cookie", cookie)
            if (body != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", contentType)
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }
            val code = connection.responseCode
            connection.getHeaderField("Set-Cookie")?.let {
                if (it.startsWith("preflight_csrf=")) cookie = it.substringBefore(';')
            }
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val bytes = ByteArrayOutputStream()
            stream?.use { input ->
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (bytes.size() + count > MAX_RESPONSE) throw IOException("Server response is too large.")
                    bytes.write(buffer, 0, count)
                }
            }
            val raw = bytes.toString("UTF-8")
            if (code !in 200..299) {
                if (code == 403) { csrf = ""; cookie = "" }
                val detail = runCatching { JSONObject(raw).optString("detail") }.getOrDefault("")
                throw IOException(when (code) {
                    403 -> "Your server session expired. Try the action again."
                    413 -> "Each file must be at most 10 MiB."
                    400 -> detail.take(250).ifBlank { "The server could not read this file." }
                    else -> "The server could not complete this request (HTTP $code)."
                })
            }
            return JSONObject(raw)
        } finally { connection.disconnect() }
    }

    companion object {
        const val MAX_FILE = 10 * 1024 * 1024
        private const val MAX_RESPONSE = 4 * 1024 * 1024
        private fun encode(value: String) = URLEncoder.encode(value, "UTF-8")
    }
}
