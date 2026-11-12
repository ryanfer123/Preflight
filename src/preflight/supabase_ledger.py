"""Supabase Postgres persistence; all access stays on the trusted Python server."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Self

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import DictRow, dict_row

from preflight.checks.common import normalise_identifier
from preflight.context import HistoricalInvoice, Vendor
from preflight.ledger import BankAccount


class SupabaseLedger:
    """Use direct/session-pooler PostgreSQL URLs; no service key reaches a browser."""

    def __init__(self, url: str) -> None:
        settings = conninfo_to_dict(url)
        host = settings.get("host", "")
        if host not in {"127.0.0.1", "localhost", "supabase-db"}:
            if settings.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("Hosted Supabase connections require TLS")
        self._url = url
        self._connection: psycopg.Connection[DictRow] | None = None

    def __enter__(self) -> Self:
        """Open a bounded server connection; schema changes are explicit migrations."""
        if self._connection is not None:
            raise RuntimeError("Ledger is already open")
        self._connection = psycopg.connect(
            self._url,
            row_factory=dict_row,
            connect_timeout=10,
            prepare_threshold=None,
            options="-c search_path=preflight,pg_catalog -c statement_timeout=10000",
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close explicitly; each mutation commits atomically."""
        del exc_type, exc, traceback
        self.connection.close()
        self._connection = None

    @property
    def connection(self) -> psycopg.Connection[DictRow]:
        """Reject queries outside the context manager."""
        if self._connection is None:
            raise RuntimeError("Use SupabaseLedger as a context manager")
        return self._connection

    def _vendor(self, row: DictRow) -> Vendor:
        return Vendor(
            id=row["id"],
            name=row["name"],
            known_domains=tuple(json.loads(row["known_domains"])),
            created_at=row["created_at"],
        )

    def add_vendor(self, name: str, known_domains: tuple[str, ...] = ()) -> Vendor:
        """Insert an explicitly established local vendor baseline."""
        if not name.strip():
            raise ValueError("Vendor name cannot be blank")
        row = self.connection.execute(
            "INSERT INTO vendors(name,known_domains,created_at) VALUES (%s,%s,%s) RETURNING *",
            (name, json.dumps(known_domains), datetime.now(UTC)),
        ).fetchone()
        self.connection.commit()
        assert row is not None
        return self._vendor(row)

    def get_vendor(self, vendor_id: int) -> Vendor | None:
        """Read one vendor by server-assigned identity."""
        row = self.connection.execute(
            "SELECT * FROM vendors WHERE id=%s", (vendor_id,)
        ).fetchone()
        return self._vendor(row) if row else None

    def find_vendor(self, name: str) -> Vendor | None:
        """Match exact names; extracted names do not authenticate identity."""
        row = self.connection.execute("SELECT * FROM vendors WHERE name=%s", (name,)).fetchone()
        return self._vendor(row) if row else None

    def list_vendors(self) -> tuple[Vendor, ...]:
        """Return vendors in stable name order."""
        return tuple(
            self._vendor(row)
            for row in self.connection.execute("SELECT * FROM vendors ORDER BY name")
        )

    def observe_bank_account(
        self, vendor_id: int, account_identifier: str, first_seen: datetime
    ) -> None:
        """Remember observations without ever granting approval."""
        account = normalise_identifier(account_identifier)
        if not account or first_seen.tzinfo is None:
            raise ValueError("Account observations need an identifier and timezone")
        self.connection.execute(
            "INSERT INTO vendor_bank_accounts "
            "(vendor_id,account_identifier_normalised,first_seen) "
            "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (vendor_id, account, first_seen),
        )
        self.connection.commit()

    def approve_bank_account(
        self, vendor_id: int, account_identifier: str, *, approved_by: str = "local user"
    ) -> None:
        """Record explicit human approval and self-reported actor/time audit details."""
        account = normalise_identifier(account_identifier)
        if not account or not approved_by.strip() or len(approved_by) > 200:
            raise ValueError("Account and approver name are required")
        now = datetime.now(UTC)
        self.connection.execute(
            "INSERT INTO vendor_bank_accounts (vendor_id,account_identifier_normalised,"
            "first_seen,approved_by_user,approved_at,approved_by_name) "
            "VALUES (%s,%s,%s,true,%s,%s) "
            "ON CONFLICT(vendor_id,account_identifier_normalised) DO UPDATE SET "
            "approved_by_user=true,approved_at=excluded.approved_at,"
            "approved_by_name=excluded.approved_by_name",
            (vendor_id, account, now, now, approved_by.strip()),
        )
        self.connection.commit()

    def approved_accounts(self, vendor_id: int) -> tuple[str, ...]:
        """Expose only human-approved canonical baselines to the checks."""
        return tuple(
            row["account_identifier_normalised"]
            for row in self.connection.execute(
                "SELECT account_identifier_normalised FROM vendor_bank_accounts "
                "WHERE vendor_id=%s AND approved_by_user ORDER BY first_seen",
                (vendor_id,),
            )
        )

    def bank_accounts(self, vendor_id: int) -> tuple[BankAccount, ...]:
        """List both observations and approvals with their audit details."""
        return tuple(
            BankAccount(
                identifier=row["account_identifier_normalised"],
                approved=row["approved_by_user"],
                approved_at=row["approved_at"].isoformat() if row["approved_at"] else None,
                approved_by=row["approved_by_name"],
            )
            for row in self.connection.execute(
                "SELECT * FROM vendor_bank_accounts WHERE vendor_id=%s ORDER BY first_seen",
                (vendor_id,),
            )
        )

    def record_invoice(
        self,
        vendor_id: int,
        invoice_number: str,
        amount: Decimal,
        currency: str,
        content_hash: str,
        received_at: datetime,
        verdict: str,
    ) -> int:
        """Store finite Decimal as text, without PostgreSQL numeric coercion."""
        if not isinstance(amount, Decimal) or not amount.is_finite():
            raise ValueError("Amount must be a finite Decimal")
        if received_at.tzinfo is None or not invoice_number.strip():
            raise ValueError("Invoice requires a timezone-aware date and number")
        row = self.connection.execute(
            "INSERT INTO invoices(vendor_id,invoice_number,amount,currency,content_hash,"
            "received_at,verdict) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                vendor_id,
                invoice_number,
                str(amount),
                currency,
                content_hash,
                received_at,
                verdict,
            ),
        ).fetchone()
        self.connection.commit()
        assert row is not None
        return int(row["id"])

    def list_history(self, vendor_id: int | None = None) -> tuple[HistoricalInvoice, ...]:
        """Read exact amounts and timezone-aware history for deterministic checks."""
        rows = (
            self.connection.execute("SELECT * FROM invoices ORDER BY received_at,id")
            if vendor_id is None
            else self.connection.execute(
                "SELECT * FROM invoices WHERE vendor_id=%s ORDER BY received_at,id",
                (vendor_id,),
            )
        )
        return tuple(
            HistoricalInvoice(
                id=row["id"],
                vendor_id=row["vendor_id"],
                invoice_number=row["invoice_number"],
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                content_hash=row["content_hash"],
                received_at=row["received_at"],
                verdict=row["verdict"],
            )
            for row in rows
        )

    def save_report(self, report_id: str, filename: str, report_json: str) -> None:
        """Persist a report without retaining the uploaded file."""
        self.connection.execute(
            "INSERT INTO reports VALUES (%s,%s,%s)", (report_id, filename, report_json)
        )
        self.connection.commit()

    def get_report(self, report_id: str) -> tuple[str, str] | None:
        """Return an immutable report snapshot by its opaque identifier."""
        row = self.connection.execute(
            "SELECT filename,report FROM reports WHERE id=%s", (report_id,)
        ).fetchone()
        return None if row is None else (row["filename"], row["report"])

    def invoice_vendor(self, invoice_id: int) -> Vendor | None:
        """Resolve the persisted vendor even when selected explicitly at upload."""
        row = self.connection.execute(
            "SELECT vendors.* FROM vendors JOIN invoices ON vendors.id=invoices.vendor_id "
            "WHERE invoices.id=%s",
            (invoice_id,),
        ).fetchone()
        return self._vendor(row) if row else None
