package dev.preflight.app.ui

import android.graphics.Color
import android.text.InputType
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import dev.preflight.app.domain.*
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/** Native screen rendering; all decision/evidence data comes from the server. */
class Screens(private val widgets: Widgets, private val model: PreflightViewModel,
              private val pickFile: (Boolean) -> Unit) {
    private val w get() = widgets

    fun render(body: LinearLayout, state: AppState) {
        if (state.error != null) body.addView(w.card(w.status("REVIEW").first).apply {
            addView(w.text("Could not complete the request", 17, w.ink, true, true))
            addView(w.text(state.error, 14, w.muted))
            addView(w.button("Connection settings", !state.busy, true) { model.navigate(Screen.CONNECTION) })
        })
        state.notice?.let { body.addView(w.card(w.status("PASS").first).apply { addView(w.text(it)) }) }
        when (state.screen) {
            Screen.CHECK -> upload(body, state)
            Screen.RESULT -> result(body, state)
            Screen.LEDGER -> ledger(body, state)
            Screen.CONNECTION -> connection(body, state)
            Screen.APPROVAL -> approval(body, state)
        }
        body.addView(w.gap(16))
        body.addView(w.text("Preflight checks the evidence.\nYou make the payment decision.", 12, w.muted))
    }

    private fun upload(body: LinearLayout, state: AppState) {
        body.addView(w.badge(if (state.extractor == null) "Server not connected"
            else if (state.extractor == "FakeExtractor") "Fixture extractor" else "Live extractor"))
        body.addView(w.text("A second look.\nBefore you pay.", 35, bold = true, heading = true))
        body.addView(w.text("Check the numbers, the sender and the bank details. Every finding comes with evidence.", 15, w.muted))
        body.addView(w.card().apply {
            addView(w.text("Your invoice", 20, bold = true, heading = true))
            addView(w.text("PDF, PNG or JPEG · up to 10 MiB", 13, w.muted))
            state.invoice?.let { addView(w.text(it.name, 15, w.indigo, true)) }
            addView(w.button(if (state.invoice == null) "Choose an invoice" else "Change invoice", !state.busy, true) { pickFile(false) })
            addView(w.gap(12))
            addView(w.text("Original email", 16, bold = true))
            addView(w.text("Optional .eml · up to 10 MiB. Adds sender and Reply-To checks.", 13, w.muted))
            state.email?.let { addView(w.text(it.name, 14, w.indigo)) }
            addView(w.button(if (state.email == null) "Add original email" else "Change email", !state.busy, true) { pickFile(true) })
            if (state.email != null) addView(w.button("Remove email", !state.busy, true) { model.clearEmail() })
            addView(w.gap(12))
            val selected = state.vendors.find { it.id == state.vendorId }
            addView(w.text("Compare with vendor", 16, bold = true))
            addView(w.button(selected?.name ?: "Match an exact ledger name", !state.busy, true) {
                val choices = listOf("Match an exact ledger name") + state.vendors.map { it.name }
                MaterialAlertDialogBuilder(w.context).setTitle("Compare with vendor")
                    .setItems(choices.toTypedArray()) { _, index ->
                        model.selectVendor(if (index == 0) null else state.vendors[index - 1].id)
                    }.show()
            })
            addView(w.button(if (state.busy) "Checking…" else "Check invoice", !state.busy && state.invoice != null) { model.check() })
        })
        body.addView(w.button("Try a sample invoice", !state.busy, true) {
            val labels = arrayOf("Clean invoice", "Changed bank account", "Lookalike sender", "Duplicate invoice", "Arithmetic tamper", "Prompt injection + bank change")
            MaterialAlertDialogBuilder(w.context).setTitle("Synthetic sample invoices")
                .setItems(labels) { _, index -> model.selectSample(PreflightViewModel.SAMPLES[index]) }
                .setNegativeButton("Cancel", null).show()
        })
        if (model.lastReportId != null) body.addView(w.button("Open last result", !state.busy, true) { model.lastResult() })
        body.addView(w.gap(12))
        body.addView(w.text("What the verdict means", 20, bold = true, heading = true))
        for ((name, description) in listOf(
            "PASS" to "No blocking findings. Verification gaps stay visible.",
            "REVIEW" to "A closer look or more evidence is needed.",
            "BLOCK" to "A critical issue needs independent verification.")) {
            val colors = w.status(name)
            body.addView(w.text("${symbol(name)} $name", 14, colors.second, true))
            body.addView(w.text(description, 13, w.muted))
        }
        body.addView(w.text(if (state.extractor == "FakeExtractor")
            "Demo fixtures only. Unrecognised invoices return REVIEW. Configure a live extractor on the server for your own documents."
            else "The model extracts fields. Deterministic server checks decide the verdict. No payments are made here.", 13, w.muted))
    }

    private fun result(body: LinearLayout, state: AppState) {
        val report = state.report ?: return
        body.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        body.addView(w.text("Invoice check", 29, bold = true, heading = true))
        body.addView(w.text(report.filename, 14, w.muted))
        val colors = w.status(report.verdict.name)
        body.addView(w.card(colors.first).apply {
            addView(w.text("${symbol(report.verdict.name)} ${report.verdict.name}", 30, colors.second, true, true))
            addView(w.text(when (report.verdict) {
                Verdict.BLOCK -> "Hold payment. Verify critical findings through a trusted channel."
                Verdict.REVIEW -> "Take a closer look before paying. Resolve findings and missing evidence."
                Verdict.PASS -> "No blocking findings. Read the verification gaps before deciding to pay."
            }, 15, colors.second))
        })
        report.invoice?.let { invoice ->
            body.addView(w.card().apply {
                addView(w.text(invoice.vendor, 20, bold = true))
                addView(w.text(invoice.number, 13, w.muted))
                addView(w.text("${invoice.currency} ${invoice.amount}", 26, bold = true))
                addView(w.text("Policy score ${report.score}", 12, w.muted))
            })
        }
        body.addView(w.card(Color.rgb(237, 240, 248)).apply {
            addView(w.text("Could not be verified", 20, bold = true, heading = true))
            addView(w.text("A PASS never removes these gaps.", 13, w.muted))
            if (report.gaps.isEmpty()) addView(w.text("No verification gaps reported.", 14))
            report.gaps.forEach { addView(w.text("• ${gapLabel(it)}", 14)) }
            report.detail?.let { addView(w.text(it, 14)) }
        })
        body.addView(w.gap())
        body.addView(w.text("Findings & evidence", 22, bold = true, heading = true))
        val findings = report.findings.filter { it.status == "observed" }
        for (severity in listOf("critical", "high", "low", "info")) {
            val group = findings.filter { it.severity == severity }
            if (group.isEmpty()) continue
            body.addView(w.text("${severity.replaceFirstChar { it.uppercase() }} · ${group.size}", 16, bold = true, heading = true))
            group.forEach { finding ->
                body.addView(w.card().apply {
                    addView(w.text(finding.message, 16, bold = true))
                    addView(w.text(finding.checkId, 12, w.muted))
                    val citations = w.column().apply {
                        finding.evidence.forEach { evidence ->
                            addView(w.text(evidence.field + (evidence.page?.let { " · Page $it" } ?: ""), 12, w.muted, true))
                            addView(w.text(evidence.snippet, 14))
                        }
                        visibility = View.GONE
                    }
                    val toggle = w.button("Show evidence", outlined = true) {}
                    toggle.setOnClickListener {
                        val visible = citations.visibility != View.VISIBLE
                        citations.visibility = if (visible) View.VISIBLE else View.GONE
                        toggle.text = if (visible) "Hide evidence" else "Show evidence"
                        toggle.contentDescription = "${toggle.text}: ${finding.message}"
                    }
                    addView(toggle); addView(citations)
                })
            }
        }
        if (findings.isEmpty()) body.addView(w.text("Extraction must succeed before checks can run.", 14, w.muted))
        body.addView(w.text("Extracted by ${report.extractor}. This report is a snapshot; later approvals do not rewrite it.", 12, w.muted))
        body.addView(w.button("Review vendor bank details", !state.busy, true) { model.navigate(Screen.LEDGER) })
        body.addView(w.button("Check another invoice", !state.busy) { model.navigate(Screen.CHECK) })
    }

    private fun ledger(body: LinearLayout, state: AppState) {
        body.addView(w.text("A baseline\nyou trust.", 35, bold = true, heading = true))
        body.addView(w.text("Known vendors, remembered payment details and invoice history. Stored in Supabase by your server.", 15, w.muted))
        body.addView(w.button("Refresh ledger", !state.busy, true) { model.refreshLedger() })
        if (state.vendors.isEmpty()) body.addView(w.card().apply {
            addView(w.text("Your ledger starts with the first check.", 18, bold = true))
            addView(w.text("Upload an invoice to record its vendor and observed payment details.", 14, w.muted))
        })
        state.vendors.forEach { vendor ->
            body.addView(w.card().apply {
                addView(w.text(vendor.name, 24, bold = true, heading = true))
                addView(w.text(vendor.domains.joinToString().ifBlank { "No known domain baseline" }, 13, w.muted))
                addView(w.text("Bank details", 18, bold = true, heading = true))
                if (vendor.accounts.isEmpty()) addView(w.text("No accounts observed.", 14, w.muted))
                vendor.accounts.forEach { account ->
                    addView(w.text(account.identifier, 15, bold = true))
                    addView(w.text(if (account.approved) "✓ Approved by ${account.approvedBy ?: "Legacy local user"}\n${account.approvedAt ?: ""}"
                        else "! Observed only · not an approved baseline", 13,
                        w.status(if (account.approved) "PASS" else "REVIEW").second))
                    addView(w.button(if (account.approved) "Review approval" else "Approve bank details", !state.busy, true) {
                        model.requestApproval(vendor, account)
                    })
                    addView(w.gap())
                }
                addView(w.text("Invoice history · ${vendor.history.size}", 18, bold = true, heading = true))
                vendor.history.reversed().forEach { item ->
                    addView(w.text(item.number, 14, bold = true))
                    addView(w.text("${item.currency} ${item.amount}  ·  ${item.verdict}", 14,
                        w.status(item.verdict.name).second))
                    addView(w.text(item.receivedAt.take(10), 12, w.muted))
                }
            })
        }
    }

    private fun approval(body: LinearLayout, state: AppState) {
        val target = state.approval ?: return
        body.addView(w.text("Trust starts outside\nthe invoice.", 32, bold = true, heading = true))
        body.addView(w.text("Confirm these exact details using a contact you already trust.", 15, w.muted))
        body.addView(w.card().apply {
            addView(w.text("Approve and remember bank details", 21, bold = true, heading = true))
            addView(w.text("Vendor", 12, w.muted)); addView(w.text(target.vendor.name, 22, bold = true))
            addView(w.text("Exact account identifier", 12, w.muted))
            addView(w.text(target.account.identifier, 18, bold = true))
            addView(w.text("Approval changes future baselines. It does not approve a payment or clear an existing report. Uploaded email and model output cannot verify account ownership.", 14, w.muted))
            val name = EditText(w.context).apply {
                id = dev.preflight.app.R.id.approver_name
                hint = "Your name"; contentDescription = "Your name"
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
                maxLines = 1; filters = arrayOf(android.text.InputFilter.LengthFilter(200))
                setTextColor(w.ink); setHintTextColor(w.muted)
                minHeight = w.dp(56)
            }
            addView(name)
            addView(w.text("A self-reported local audit note; there is no authentication.", 12, w.muted))
            val confirm = CheckBox(w.context).apply {
                id = dev.preflight.app.R.id.approval_checkbox
                text = w.context.getString(dev.preflight.app.R.string.approval_confirmation)
                setTextColor(w.ink); minHeight = w.dp(64)
            }
            addView(confirm)
            addView(w.button("Approve and remember", !state.busy) { model.approve(name.text.toString(), confirm.isChecked) })
            addView(w.button("Cancel", !state.busy, true) { model.navigate(Screen.LEDGER) })
        })
    }

    private fun connection(body: LinearLayout, state: AppState) {
        body.addView(w.text("Your server.\nYour workspace.", 33, bold = true, heading = true))
        body.addView(w.text("Preflight verifies invoices on your Python server, which stores the ledger in Supabase. No database or model keys are kept in this app.", 15, w.muted))
        body.addView(w.card().apply {
            addView(w.text("Server connection", 21, bold = true, heading = true))
            val address = EditText(w.context).apply {
                id = dev.preflight.app.R.id.server_address
                setText(model.address); contentDescription = "Server address"
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                setTextColor(w.ink); minHeight = w.dp(56); setSingleLine(true)
                filters = arrayOf(android.text.InputFilter.LengthFilter(300))
            }
            addView(address)
            addView(w.button("Save and connect", !state.busy) { model.saveAddress(address.text.toString()) })
            addView(w.text(if (state.extractor == null) "Not connected. No invoice verdict has been assumed."
                else "Connected · ${state.extractor}", 14, w.muted))
        })
        body.addView(w.text("Connect locally", 21, bold = true, heading = true))
        body.addView(w.text("1. Start docker compose up on your computer.\n2. Connect an emulator or USB device.\n3. Run adb reverse tcp:8000 tcp:8000.\n4. Keep the default address and tap Save and connect.", 15, w.muted))
        body.addView(w.text("There is no authentication. Use this local workspace with your own device. An HTTPS server address is supported; credentials and query strings are rejected.", 13, w.muted))
        body.addView(w.text("Extraction mode", 21, bold = true, heading = true))
        body.addView(w.text("Fixture mode recognises only the bundled sample PDFs. Your own documents need a live extractor configured on the server. Images without verifiable text require REVIEW.", 14, w.muted))
    }

    private fun symbol(verdict: String) = when (verdict) { "PASS" -> "✓"; "BLOCK" -> "×"; else -> "!" }
    private fun gapLabel(value: String): String = when (value) {
        "identifiers.bank.iban" -> "IBAN validity (optional payment rail)"
        "identifiers.bank.upi_vpa" -> "UPI validity (optional payment rail)"
        "sender" -> "Sender integrity: original email missing"
        "sender.authentication_trust" -> "Email authentication lacks a trusted receiver attestation"
        "amount_anomaly" -> "Amount history: insufficient baseline"
        "bank_change" -> "Payment details: no comparison baseline"
        "required_fields" -> "Required invoice fields missing"
        else -> value.replace('_', ' ')
    }
}
