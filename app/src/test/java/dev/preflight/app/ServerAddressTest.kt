package dev.preflight.app

import dev.preflight.app.data.ServerAddress
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** Local URL validation never opens sockets or reads credentials. */
class ServerAddressTest {
    @Test fun deviceLoopbackIsDefault() {
        assertEquals("http://127.0.0.1:8000", ServerAddress.DEFAULT)
    }
    @Test fun normalizesTrailingSlash() {
        assertEquals("http://localhost:8000", ServerAddress.normalize(" http://localhost:8000/ "))
    }
    @Test fun acceptsHttpsServer() {
        assertEquals("https://preflight.example", ServerAddress.normalize("https://preflight.example"))
    }
    @Test fun rejectsCleartextOutsideLoopback() {
        for (value in listOf("http://10.0.2.2:8000", "http://192.168.1.5:8000", "http://preflight.example")) {
            assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize(value) }
        }
    }
    @Test fun rejectsEmbeddedCredentials() {
        assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize("https://user:synthetic@preflight.example") }
    }
    @Test fun rejectsFragmentsAndQueries() {
        for (value in listOf("https://preflight.example?key=synthetic", "https://preflight.example#fragment")) {
            assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize(value) }
        }
    }
    @Test fun rejectsUnsupportedSchemesAndPorts() {
        for (value in listOf("file:///invoice.pdf", "ftp://preflight.example", "http://localhost:99999", "http://localhost:0")) {
            assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize(value) }
        }
    }
    @Test fun requiresServerRoot() {
        assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize("https://preflight.example/api") }
    }
}
