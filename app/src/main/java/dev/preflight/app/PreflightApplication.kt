package dev.preflight.app

import android.app.Application
import dev.preflight.app.data.HttpRepository
import dev.preflight.app.domain.PreflightRepository

/** One composition root; instrumented tests replace only the repository boundary. */
class PreflightApplication : Application() {
    var repositoryFactory: (String) -> PreflightRepository = { HttpRepository(it) }
}
