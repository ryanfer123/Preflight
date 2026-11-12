package dev.preflight.app.data

import dev.preflight.app.domain.*
import org.json.JSONArray
import org.json.JSONObject

/** Parse the server contract without converting any monetary value to binary decimals. */
object JsonModels {
    private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
    private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
    private fun JSONObject.nullable(key: String): String? = if (isNull(key)) null else getString(key)

    fun report(payload: JSONObject): Report {
        val source = payload.getJSONObject("report")
        val provenance = source.getJSONObject("provenance")
        val invoice = if (source.isNull("invoice")) null else source.getJSONObject("invoice").let {
            InvoiceSummary(it.nullable("vendor_name") ?: "Not extracted",
                it.nullable("invoice_number") ?: "Not extracted",
                it.nullable("total") ?: "Not extracted", it.nullable("currency") ?: "")
        }
        return Report(payload.getString("report_id"), payload.getString("filename"),
            Verdict.valueOf(source.getString("verdict")), source.getInt("score"),
            source.getJSONArray("findings").objects().map { item ->
                Finding(item.getString("check_id"), item.getString("severity"), item.getString("status"),
                    item.getString("message"), item.getJSONArray("evidence").objects().map { citation ->
                        Evidence(citation.getString("field"), citation.getString("source_snippet"),
                            if (citation.isNull("page")) null else citation.getInt("page"))
                    })
            }, source.getJSONArray("unverifiable_checks").strings(),
            source.getJSONArray("reasons").strings(), provenance.getString("extractor"),
            provenance.nullable("detail"), invoice)
    }

    fun vendors(payload: JSONObject): List<Vendor> = payload.getJSONArray("vendors").objects().map { source ->
        Vendor(source.getLong("id"), source.getString("name"),
            source.getJSONArray("known_domains").strings(),
            source.getJSONArray("accounts").objects().map {
                BankAccount(it.getString("identifier"), it.getBoolean("approved"),
                    it.nullable("approved_by"), it.nullable("approved_at"))
            }, source.getJSONArray("history").objects().map {
                History(it.getString("invoice_number"), it.getString("amount"),
                    it.getString("currency"), it.getString("received_at"),
                    Verdict.valueOf(it.getString("verdict")))
            })
    }
}
