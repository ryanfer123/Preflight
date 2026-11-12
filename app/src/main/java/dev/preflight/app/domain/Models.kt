package dev.preflight.app.domain

/** Server-defined decisions. The Android client never computes a verdict. */
enum class Verdict { PASS, REVIEW, BLOCK }

/** Source citations remain plain text and are never rendered as HTML. */
data class Evidence(val field: String, val snippet: String, val page: Int?)
data class Finding(val checkId: String, val severity: String, val status: String,
                   val message: String, val evidence: List<Evidence>)
data class InvoiceSummary(val vendor: String, val number: String, val amount: String,
                          val currency: String)
data class Report(val id: String, val filename: String, val verdict: Verdict,
                  val score: Int, val findings: List<Finding>, val gaps: List<String>,
                  val reasons: List<String>, val extractor: String, val detail: String?,
                  val invoice: InvoiceSummary?)
data class BankAccount(val identifier: String, val approved: Boolean,
                       val approvedBy: String?, val approvedAt: String?)
data class History(val number: String, val amount: String, val currency: String,
                   val receivedAt: String, val verdict: Verdict)
data class Vendor(val id: Long, val name: String, val domains: List<String>,
                  val accounts: List<BankAccount>, val history: List<History>)
data class Session(val extractor: String)
data class Attachment(val name: String, val bytes: ByteArray)

/** The sole data boundary used by the UI; implementors do not decide verdicts. */
interface PreflightRepository {
    fun connect(): Session
    fun vendors(): List<Vendor>
    fun check(invoice: Attachment, email: Attachment?, vendorId: Long?): Report
    fun report(id: String): Report
    fun approve(vendorId: Long, account: String, actor: String, confirmed: Boolean)
}
