"""Ingest, validate extraction, run pure checks, decide and persist observations."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from preflight.checks import (
    amount_anomaly,
    arithmetic,
    bank_change,
    duplicates,
    identifiers,
    pressure_language,
    sender,
)
from preflight.checks.common import bank_identifiers, finding
from preflight.context import Context
from preflight.extract import Extractor
from preflight.extract.documents import Document, IngestionError, Upload, ingest
from preflight.extract.evidence import evidence_error
from preflight.ledger import Ledger
from preflight.models import Evidence, ExtractionFailure, Finding, Invoice, StrictModel
from preflight.policy import Policy, decide


class Provenance(StrictModel):
    """Record the provider class, document hash and extraction outcome, never secrets."""

    extractor: str
    document_hash: str | None
    mime: str | None
    extraction_status: Literal["success", "extraction_failed", "not_attempted"]
    detail: str | None


class Report(StrictModel):
    """A deterministic verdict that always carries its verification gaps and evidence."""

    verdict: Literal["PASS", "REVIEW", "BLOCK"]
    score: int
    findings: tuple[Finding, ...]
    unverifiable_checks: tuple[str, ...]
    reasons: tuple[str, ...]
    provenance: Provenance
    invoice: Invoice | None
    invoice_id: int | None


def _failure(
    extractor: Extractor,
    reason: str,
    detail: str,
    document: Document | None = None,
    *,
    attempted: bool = False,
) -> Report:
    return Report(
        verdict="REVIEW",
        score=0,
        findings=(),
        unverifiable_checks=(reason,),
        reasons=(reason,),
        provenance=Provenance(
            extractor=type(extractor).__name__,
            document_hash=document.content_hash if document else None,
            mime=document.mime if document else None,
            extraction_status="extraction_failed" if attempted else "not_attempted",
            detail=detail,
        ),
        invoice=None,
        invoice_id=None,
    )


def _select_document(upload: Upload, eml: Upload | None) -> tuple[Document, Document | None]:
    document = ingest(upload)
    email_document = ingest(eml) if eml is not None else None
    if email_document is not None and email_document.email is None:
        raise IngestionError("mime_mismatch", "Original email must be an RFC email")
    if document.email is not None:
        if email_document is not None:
            raise IngestionError("invalid_document", "Two original emails are ambiguous")
        email_document = document
        if len(document.attachments) > 1:
            raise IngestionError("invalid_document", "Select one invoice attachment explicitly")
        if document.attachments:
            document = ingest(document.attachments[0])
    return document, email_document


def _context(
    document: Document,
    email_document: Document | None,
    extraction_evidence: tuple[Evidence, ...],
    invoice: Invoice,
    ledger: Ledger,
    policy: Policy,
    received_at: datetime,
    vendor_id: int | None,
) -> Context:
    vendor = (
        ledger.get_vendor(vendor_id)
        if vendor_id is not None
        else (ledger.find_vendor(invoice.vendor_name) if invoice.vendor_name else None)
    )
    if vendor_id is not None and vendor is None:
        raise ValueError("Unknown selected vendor")
    evidence = list(extraction_evidence)
    email = email_document.email if email_document else None
    if email is not None:
        for field, values in (
            ("email.from", (email.from_address,)),
            ("email.reply_to", (email.reply_to,) if email.reply_to else ()),
            ("email.authentication_results", email.authentication_results),
        ):
            evidence.extend(
                Evidence(field=field, source_snippet=value, page=None)
                for value in values
                if value and value in email.source_text
            )
    source = document.text + ("\n" + email.source_text if email is not None else "")
    return Context(
        source_text=source,
        evidence=tuple(evidence),
        vendor=vendor,
        approved_accounts=ledger.approved_accounts(vendor.id) if vendor else (),
        history=ledger.list_history(vendor.id) if vendor else (),
        all_history=ledger.list_history(),
        email=email,
        content_hash=document.content_hash,
        received_at=received_at,
        tolerance=policy.arithmetic_tolerance,
        anomaly_threshold=policy.anomaly_threshold,
        pressure_patterns=policy.pressure_patterns,
    )


def _checks(invoice: Invoice, context: Context) -> list[Finding]:
    checks: tuple[Callable[[Invoice, Context], list[Finding]], ...] = (
        identifiers.check,
        arithmetic.check,
        bank_change.check,
        sender.check,
        duplicates.check,
        amount_anomaly.check,
        pressure_language.check,
    )
    findings: list[Finding] = []
    verified: list[str] = []
    for check in checks:
        observations = check(invoice, context)
        findings.extend(observations)
        # An absence of pressure cues is not a verification of invoice legitimacy.
        if not observations and check is not pressure_language.check:
            verified.append(check.__module__.rsplit(".", 1)[-1])
    if verified:
        findings.append(
            finding(
                context,
                "verification",
                "document",
                "Completed checks: " + ", ".join(verified),
            )
        )
    return findings


def run(
    document: Upload,
    eml: Upload | None = None,
    *,
    ledger: Ledger,
    policy: Policy,
    extractor: Extractor,
    vendor_id: int | None = None,
    received_at: datetime | None = None,
) -> Report:
    """Verify a document; failures and ungrounded extraction never produce PASS/BLOCK."""
    timestamp = received_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("received_at must include a timezone")
    try:
        ingested, email_document = _select_document(document, eml)
    except IngestionError as error:
        return _failure(extractor, error.code, str(error))
    extraction = extractor.extract(ingested.text, list(ingested.images))
    if isinstance(extraction, ExtractionFailure):
        return _failure(
            extractor,
            "extraction_failed",
            extraction.reason,
            ingested,
            attempted=True,
        )
    citation_error = evidence_error(extraction, ingested)
    if citation_error:
        return _failure(
            extractor,
            citation_error,
            "Extraction citations could not be verified",
            ingested,
            attempted=True,
        )
    invoice = extraction.invoice
    context = _context(
        ingested,
        email_document,
        extraction.evidence,
        invoice,
        ledger,
        policy,
        timestamp,
        vendor_id,
    )
    findings = _checks(invoice, context)
    required = (invoice.vendor_name, invoice.invoice_number, invoice.total, invoice.currency)
    if any(value is None for value in required):
        findings.append(
            finding(
                context,
                "required_fields",
                "document",
                "unverifiable: vendor, number, currency or total missing",
                unverifiable=True,
            )
        )
    decision = decide(findings, policy)
    if any(value is None for value in required) and decision.verdict == "PASS":
        decision = decision.model_copy(
            update={
                "verdict": "REVIEW",
                "reasons": ("required_fields_missing",),
            }
        )
    invoice_id: int | None = None
    if all(value is not None for value in required):
        assert invoice.vendor_name is not None and invoice.invoice_number is not None
        assert invoice.total is not None and invoice.currency is not None
        vendor = context.vendor or ledger.add_vendor(invoice.vendor_name)
        for _, identifier in bank_identifiers(invoice.bank):
            ledger.observe_bank_account(vendor.id, identifier, timestamp)
        invoice_id = ledger.record_invoice(
            vendor.id,
            invoice.invoice_number,
            invoice.total,
            invoice.currency,
            ingested.content_hash,
            timestamp,
            decision.verdict,
        )
    return Report(
        verdict=decision.verdict,
        score=decision.score,
        findings=tuple(findings),
        unverifiable_checks=decision.unverifiable_checks,
        reasons=decision.reasons,
        provenance=Provenance(
            extractor=type(extractor).__name__,
            document_hash=ingested.content_hash,
            mime=ingested.mime,
            extraction_status="success",
            detail=None,
        ),
        invoice=invoice,
        invoice_id=invoice_id,
    )
