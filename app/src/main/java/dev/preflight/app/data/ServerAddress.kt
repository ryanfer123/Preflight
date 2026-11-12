package dev.preflight.app.data

import java.net.URI

/** Reject embedded credentials and restrict insecure transport to device loopback. */
object ServerAddress {
    const val DEFAULT = "http://127.0.0.1:8000"

    fun normalize(value: String): String {
        val uri = URI(value.trim())
        require(uri.userInfo == null && uri.query == null && uri.fragment == null) {
            "Use a server address without credentials, query parameters or fragments."
        }
        require(uri.path.isNullOrEmpty() || uri.path == "/") { "Use the server root address." }
        require(!uri.host.isNullOrBlank() && (uri.port == -1 || uri.port in 1..65535)) { "Enter a valid server address." }
        require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("127.0.0.1", "localhost"))) {
            "Use HTTPS, or localhost with the documented USB/emulator connection."
        }
        return uri.toString().trimEnd('/')
    }
}
