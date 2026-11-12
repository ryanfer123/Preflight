"""Native-client JSON routes over the same signed forms and deterministic pipeline."""

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from preflight.database import open_ledger
from preflight.pipeline import Report


def native_router(
    database: str | Path,
    extractor_name: str,
    *,
    new_token: Callable[[], str],
    check_handler: Callable[[Request], Awaitable[RedirectResponse]],
    approve_handler: Callable[[Request, int], Awaitable[RedirectResponse]],
) -> APIRouter:
    """Reuse web mutation handlers so native clients cannot bypass CSRF or validation."""
    router = APIRouter(prefix="/api/v1")

    def report_payload(report_id: str) -> dict[str, object]:
        with open_ledger(database) as ledger:
            stored = ledger.get_report(report_id)
        if stored is None:
            raise HTTPException(404, "Report not found")
        filename, raw = stored
        return {
            "report_id": report_id,
            "filename": filename,
            "report": Report.model_validate_json(raw).model_dump(mode="json"),
        }

    @router.get("/session")
    def session() -> JSONResponse:
        token = new_token()
        response = JSONResponse(
            {
                "api_version": 1,
                "csrf": token,
                "extractor": extractor_name,
                "max_file_bytes": 10 * 1024 * 1024,
            }
        )
        response.set_cookie("preflight_csrf", token, httponly=True, samesite="strict", path="/")
        return response

    @router.get("/vendors")
    def vendors() -> dict[str, object]:
        with open_ledger(database) as ledger:
            entries = [
                {
                    **vendor.model_dump(mode="json"),
                    "accounts": [
                        asdict(account) for account in ledger.bank_accounts(vendor.id)
                    ],
                    "history": [
                        item.model_dump(mode="json") for item in ledger.list_history(vendor.id)
                    ],
                }
                for vendor in ledger.list_vendors()
            ]
        return {"vendors": entries}

    @router.get("/reports/{report_id}")
    def report(report_id: str) -> dict[str, object]:
        return report_payload(report_id)

    @router.post("/check", status_code=201)
    async def check(request: Request) -> dict[str, object]:
        response = await check_handler(request)
        report_id = response.headers["location"].rsplit("/", 1)[-1]
        return report_payload(report_id)

    @router.post("/vendors/{vendor_id}/approve")
    async def approve(request: Request, vendor_id: int) -> dict[str, bool]:
        await approve_handler(request, vendor_id)
        return {"approved": True}

    return router
