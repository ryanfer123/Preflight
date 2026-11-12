package dev.preflight.app.ui

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import dev.preflight.app.PreflightApplication
import dev.preflight.app.data.HttpRepository
import dev.preflight.app.data.ServerAddress
import dev.preflight.app.domain.*
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.Executors

enum class Screen { CHECK, RESULT, LEDGER, CONNECTION, APPROVAL }
data class SelectedDocument(val location: String, val name: String, val sample: Boolean = false)
data class Approval(val vendor: Vendor, val account: BankAccount)
data class AppState(
    val screen: Screen = Screen.CHECK, val busy: Boolean = false,
    val extractor: String? = null, val error: String? = null,
    val invoice: SelectedDocument? = null, val email: SelectedDocument? = null,
    val vendors: List<Vendor> = emptyList(), val vendorId: Long? = null,
    val report: Report? = null, val approval: Approval? = null,
    val notice: String? = null
)

/** Retain selections/results across rotation and keep file/network work off the UI thread. */
class PreflightViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("preflight", 0)
    private val worker = Executors.newSingleThreadExecutor()
    private val mutable = MutableLiveData(AppState())
    val state: LiveData<AppState> = mutable
    var address: String = preferences.getString("server", ServerAddress.DEFAULT) ?: ServerAddress.DEFAULT
        private set
    private var repository: PreflightRepository = (application as PreflightApplication).repositoryFactory(address)
    val lastReportId: String? get() = preferences.getString("last_report", null)

    init { connect() }

    private fun update(block: (AppState) -> AppState) { mutable.value = block(mutable.value!!) }
    private fun work(block: (AppState) -> AppState) {
        val previous = mutable.value!!
        if (previous.busy) return
        mutable.value = previous.copy(busy = true, error = null, notice = null)
        worker.execute {
            val result = try { block(previous).copy(busy = false, error = null) }
            catch (error: Exception) {
                val message = when (error) {
                    is java.net.ConnectException, is java.net.UnknownHostException ->
                        "Cannot reach the server. Start Docker Compose and connect this device using adb reverse."
                    is java.net.SocketTimeoutException -> "The server took too long. Check the connection and retry."
                    is IOException, is IllegalArgumentException -> error.message?.take(250) ?: "The request could not be completed."
                    else -> "The server returned an unreadable response. No result has been assumed."
                }
                previous.copy(busy = false, error = message)
            }
            mutable.postValue(result)
        }
    }

    fun connect() = work { previous ->
        val session = repository.connect()
        previous.copy(extractor = session.extractor, vendors = repository.vendors())
    }
    fun navigate(screen: Screen) {
        if (mutable.value!!.busy) return
        update { it.copy(screen = screen, error = null, notice = null) }
        if (screen == Screen.LEDGER) refreshLedger()
    }
    fun selectDocument(document: SelectedDocument, email: Boolean) = update {
        if (email) it.copy(email = document, error = null) else it.copy(invoice = document, error = null)
    }
    fun clearEmail() = update { it.copy(email = null) }
    fun selectVendor(id: Long?) = update { it.copy(vendorId = id) }
    fun selectSample(name: String) = update {
        require(name in SAMPLES) { "Unknown sample" }
        it.copy(invoice = SelectedDocument("samples/$name.pdf", "$name.pdf", true),
            email = SelectedDocument("samples/$name.eml", "$name.eml", true), error = null)
    }
    fun showError(message: String) = update { it.copy(error = message) }

    private fun read(selected: SelectedDocument): Attachment {
        val application = getApplication<Application>()
        val input = if (selected.sample) application.assets.open(selected.location)
                    else application.contentResolver.openInputStream(Uri.parse(selected.location))
        val bytes = ByteArrayOutputStream()
        input?.use {
            val buffer = ByteArray(8192)
            while (true) {
                val count = it.read(buffer)
                if (count < 0) break
                require(bytes.size() + count <= HttpRepository.MAX_FILE) { "Each file must be at most 10 MiB." }
                bytes.write(buffer, 0, count)
            }
        } ?: throw IOException("This file is no longer available. Select it again.")
        require(bytes.size() > 0) { "The selected file is empty." }
        return Attachment(selected.name, bytes.toByteArray())
    }
    fun check() = work { previous ->
        val selected = previous.invoice ?: throw IllegalArgumentException("Choose an invoice first.")
        val report = repository.check(read(selected), previous.email?.let { read(it) }, previous.vendorId)
        preferences.edit().putString("last_report", report.id).apply()
        previous.copy(screen = Screen.RESULT, report = report,
            vendors = runCatching { repository.vendors() }.getOrDefault(previous.vendors))
    }
    fun lastResult() = work { previous ->
        previous.copy(screen = Screen.RESULT, report = repository.report(lastReportId ?: error("No report")))
    }
    fun refreshLedger() = work { previous -> previous.copy(vendors = repository.vendors()) }
    fun requestApproval(vendor: Vendor, account: BankAccount) = update {
        it.copy(screen = Screen.APPROVAL, approval = Approval(vendor, account), error = null)
    }
    fun approve(actor: String, confirmed: Boolean) = work { previous ->
        val approval = previous.approval ?: error("No approval selected")
        repository.approve(approval.vendor.id, approval.account.identifier, actor, confirmed)
        previous.copy(screen = Screen.LEDGER, vendors = repository.vendors(), approval = null,
            notice = "Bank details remembered. Existing reports remain unchanged.")
    }
    fun saveAddress(value: String) {
        try {
            val normalized = ServerAddress.normalize(value)
            repository = getApplication<PreflightApplication>().repositoryFactory(normalized)
            address = normalized
            preferences.edit().putString("server", normalized).remove("last_report").apply()
            update { AppState(screen = Screen.CONNECTION) }
            connect()
        } catch (error: Exception) { showError(error.message ?: "Enter a valid server address.") }
    }
    override fun onCleared() { worker.shutdownNow() }

    companion object {
        val SAMPLES = listOf("clean", "bank-change", "lookalike", "duplicate", "arithmetic-tamper", "prompt-injection")
    }
}
