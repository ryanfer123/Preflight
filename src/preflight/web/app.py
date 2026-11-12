"""Accessible local-only forms over the existing deterministic pipeline."""

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile
from starlette.middleware.trustedhost import TrustedHostMiddleware

from preflight.database import configured_database, open_ledger
from preflight.extract import Extractor
from preflight.extract.documents import MAX_BYTES, IngestionError, Upload, ingest
from preflight.extract.fake import FakeExtractor
from preflight.extract.openai_compatible import OpenAICompatibleExtractor
from preflight.models import InvoiceExtraction, Severity
from preflight.pipeline import Report, run
from preflight.policy import load_policy
from preflight.web.api import native_router
from preflight.web.security import RequestBoundary

ROOT = Path(__file__).parent
CookieToken = Annotated[str, "Signed, host-only CSRF token; never an identity"]


def safe_filename(name: str) -> str:
    """Keep a short display label; never turn any upload name into a path."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name.replace("\\", "/").rsplit("/", 1)[-1])[:100]


def configured_extractor() -> Extractor:
    """Use a configured live provider or exact demo fixtures; never fabricate extraction."""
    if os.environ.get("PREFLIGHT_MODEL"):
        return OpenAICompatibleExtractor.from_env()
    path = Path("samples/fixtures.json")
    fixtures = {}
    if path.exists():
        raw = json.loads(path.read_text())
        fixtures = {
            key: InvoiceExtraction.model_validate_json(json.dumps(value))
            for key, value in raw.items()
        }
    return FakeExtractor(fixtures)


def create_app(
    *, database: str | Path | None = None, extractor: Extractor | None = None
) -> FastAPI:
    """Create a local application with explicit provider and persistent report storage."""
    database_target = database if database is not None else configured_database()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.add_middleware(RequestBoundary)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")
    provider = extractor if extractor is not None else configured_extractor()
    signing_key = secrets.token_bytes(32)

    def token() -> CookieToken:
        nonce = secrets.token_hex(32)
        return nonce + "." + hmac.new(signing_key, nonce.encode(), hashlib.sha256).hexdigest()

    def valid(value: str) -> bool:
        nonce, _, signature = value.partition(".")
        expected = hmac.new(signing_key, nonce.encode(), hashlib.sha256).hexdigest()
        return len(nonce) == 64 and hmac.compare_digest(signature, expected)

    def render(request: Request, name: str, **context: object) -> HTMLResponse:
        csrf = request.cookies.get("preflight_csrf", "")
        if not valid(csrf):
            csrf = token()
        response = templates.TemplateResponse(
            request=request,
            name=name,
            context={
                "csrf": csrf,
                "extractor": type(provider).__name__,
                "fake": isinstance(provider, FakeExtractor),
                "check_labels": {
                    "identifiers.bank.iban": "IBAN validity (optional payment rail)",
                    "identifiers.bank.upi_vpa": "UPI validity (optional payment rail)",
                    "identifiers.bank.ifsc": "Bank routing code",
                    "identifiers.gstin": "GSTIN validity",
                    "identifiers.registration_state": "GST registration state",
                    "sender": "Sender integrity: original email missing",
                    "sender.authentication_trust": "Email receiver trust unverified",
                    "sender.baseline": "Sender domain: no known vendor baseline",
                    "sender.spf": "Email SPF result",
                    "sender.dkim": "Email DKIM result",
                    "sender.dmarc": "Email DMARC result",
                    "bank_change": "Payment details: no comparison baseline",
                    "amount_anomaly": "Amount history: insufficient baseline",
                    "arithmetic": "Arithmetic: incomplete inputs",
                    "required_fields": "Required invoice fields missing",
                },
                **context,
            },
        )
        response.set_cookie("preflight_csrf", csrf, httponly=True, samesite="strict", path="/")
        return response

    async def form_data(request: Request) -> FormData:
        form = await request.form(max_files=2, max_fields=5, max_part_size=MAX_BYTES)
        supplied = form.get("csrf")
        cookie = request.cookies.get("preflight_csrf", "")
        if (
            not isinstance(supplied, str)
            or not valid(cookie)
            or not hmac.compare_digest(supplied, cookie)
        ):
            await form.close()
            raise HTTPException(403, "Invalid form token. Reload the page and try again.")
        return form

    async def upload(form: FormData, field: str, *, optional: bool = False) -> Upload | None:
        value = form.get(field)
        if not isinstance(value, UploadFile) or not value.filename:
            if optional:
                return None
            raise HTTPException(400, "Choose an invoice PDF, PNG or JPEG.")
        content = await value.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "Each file must be at most 10 MiB.")
        result = Upload(safe_filename(value.filename), content)
        try:
            ingested = ingest(result)
        except IngestionError as error:
            raise HTTPException(400, str(error)) from error
        expected = (
            {"message/rfc822"}
            if field == "eml"
            else {"application/pdf", "image/png", "image/jpeg"}
        )
        if ingested.mime not in expected:
            raise HTTPException(400, "Invoice must be PDF/PNG/JPEG; email must be .eml.")
        return result

    def stored(report_id: str) -> tuple[str, Report]:
        with open_ledger(database_target) as ledger:
            row = ledger.get_report(report_id)
        if row is None:
            raise HTTPException(404, "Report not found")
        return row[0], Report.model_validate_json(row[1])

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        with open_ledger(database_target) as ledger:
            vendors = ledger.list_vendors()
        return render(request, "upload.html", vendors=vendors, active="upload")

    def verify(invoice: Upload, email: Upload | None, selected: str) -> str:
        with open_ledger(database_target) as ledger:
            if selected and ledger.get_vendor(int(selected)) is None:
                raise HTTPException(400, "Unknown vendor")
            report = run(
                invoice,
                email,
                ledger=ledger,
                policy=load_policy(),
                extractor=provider,
                vendor_id=int(selected) if selected else None,
            )
            report_id = secrets.token_urlsafe(24)
            ledger.save_report(report_id, invoice.name, report.model_dump_json())
        return report_id

    @app.post("/check")
    async def check(request: Request) -> RedirectResponse:
        form = await form_data(request)
        try:
            invoice = await upload(form, "invoice")
            email = await upload(form, "eml", optional=True)
            assert invoice is not None
            selected = form.get("vendor", "")
            if not isinstance(selected, str) or (selected and not selected.isdecimal()):
                raise HTTPException(400, "Invalid vendor selection")
            report_id = await run_in_threadpool(verify, invoice, email, selected)
            return RedirectResponse("/results/" + report_id, status_code=303)
        finally:
            await form.close()

    @app.get("/results/{report_id}", response_class=HTMLResponse)
    def result(request: Request, report_id: str) -> HTMLResponse:
        filename, report = stored(report_id)
        with open_ledger(database_target) as ledger:
            vendor = (
                ledger.find_vendor(report.invoice.vendor_name)
                if (report.invoice and report.invoice.vendor_name)
                else None
            )
            # Resolve the persisted vendor, including an explicit upload selection.
            if report.invoice_id is not None:
                vendor = ledger.invoice_vendor(report.invoice_id)
        return render(
            request,
            "result.html",
            filename=filename,
            report=report,
            vendor=vendor,
            severities=tuple(reversed(Severity)),
            active="upload",
        )

    @app.get("/ledger", response_class=HTMLResponse)
    def ledger_page(request: Request) -> HTMLResponse:
        with open_ledger(database_target) as ledger:
            entries = [
                (vendor, ledger.bank_accounts(vendor.id), ledger.list_history(vendor.id))
                for vendor in ledger.list_vendors()
            ]
        return render(request, "ledger.html", entries=entries, active="ledger")

    def observed(vendor_id: int, account: str) -> str:
        with open_ledger(database_target) as ledger:
            vendor = ledger.get_vendor(vendor_id)
            accounts = ledger.bank_accounts(vendor_id)
        if vendor is None or account not in {item.identifier for item in accounts}:
            raise HTTPException(404, "Observed vendor account not found")
        return vendor.name

    @app.get("/vendors/{vendor_id}/approve", response_class=HTMLResponse)
    def approval(request: Request, vendor_id: int, account: str) -> HTMLResponse:
        name = observed(vendor_id, account)
        return render(
            request,
            "approve.html",
            vendor_name=name,
            vendor_id=vendor_id,
            account=account,
            active="ledger",
        )

    @app.post("/vendors/{vendor_id}/approve")
    async def approve(request: Request, vendor_id: int) -> RedirectResponse:
        form = await form_data(request)
        try:
            account, actor = form.get("account"), form.get("actor")
            if not isinstance(account, str) or not isinstance(actor, str):
                raise HTTPException(400, "Account and your name are required")
            if form.get("confirmed") != "yes" or not actor.strip() or len(actor) > 200:
                raise HTTPException(400, "Confirm independent verification and enter your name")
            observed(vendor_id, account)
            with open_ledger(database_target) as ledger:
                ledger.approve_bank_account(vendor_id, account, approved_by=actor)
            return RedirectResponse("/ledger", status_code=303)
        finally:
            await form.close()

    app.include_router(
        native_router(
            database_target,
            type(provider).__name__,
            new_token=token,
            check_handler=check,
            approve_handler=approve,
        )
    )
    return app


def application() -> FastAPI:
    """Uvicorn factory; use one worker and a persistent local ledger file."""
    return create_app(database=configured_database())
