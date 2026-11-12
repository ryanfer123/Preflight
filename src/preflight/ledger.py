"""Local SQLite ledger with explicit connection and transaction lifetimes."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType

from preflight.checks.common import normalise_identifier
from preflight.context import HistoricalInvoice, Vendor

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, report TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    known_domains TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vendor_bank_accounts (
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    account_identifier_normalised TEXT NOT NULL, first_seen TEXT NOT NULL,
    approved_by_user INTEGER NOT NULL DEFAULT 0, approved_at TEXT,
    PRIMARY KEY (vendor_id, account_identifier_normalised)
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    invoice_number TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL,
    content_hash TEXT NOT NULL, received_at TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS', 'REVIEW', 'BLOCK'))
);
"""


@dataclass(frozen=True)
class BankAccount:
    """Observed account and explicit human approval audit details."""

    identifier: str
    approved: bool
    approved_at: str | None
    approved_by: str | None


class Ledger:
    """Use with Ledger(path) as ledger; :memory: retains state within that scope."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> "Ledger":
        """Open a connection and enable referential integrity."""
        if self._connection is not None:
            raise RuntimeError("Ledger is already open")
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(vendor_bank_accounts)")
        }
        if "approved_by_name" not in columns:
            connection.execute(
                "ALTER TABLE vendor_bank_accounts ADD COLUMN approved_by_name TEXT"
            )
            connection.commit()
        self._connection = connection
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection; each mutation is its own atomic transaction."""
        del exc_type, exc, traceback
        self.connection.close()
        self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Reject access outside the context manager."""
        if self._connection is None:
            raise RuntimeError("Use Ledger as a context manager")
        return self._connection

    def add_vendor(self, name: str, known_domains: tuple[str, ...] = ()) -> Vendor:
        """Insert a vendor; duplicate names require an explicit caller decision."""
        if not name.strip():
            raise ValueError("Vendor name cannot be blank")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO vendors(name, known_domains, created_at) VALUES (?, ?, ?)",
                (name, json.dumps(known_domains), datetime.now(UTC).isoformat()),
            )
        assert cursor.lastrowid is not None
        vendor = self.get_vendor(cursor.lastrowid)
        assert vendor is not None
        return vendor

    def get_vendor(self, vendor_id: int) -> Vendor | None:
        """Look up a vendor by local identity."""
        row = self.connection.execute(
            "SELECT * FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if row is None:
            return None
        domains = json.loads(row["known_domains"])
        if not isinstance(domains, list) or not all(
            isinstance(value, str) for value in domains
        ):
            raise ValueError("Invalid domains in ledger")
        return Vendor(
            id=row["id"],
            name=row["name"],
            known_domains=tuple(domains),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def find_vendor(self, name: str) -> Vendor | None:
        """Match exact names; model names never establish authenticated vendor identity."""
        row = self.connection.execute(
            "SELECT id FROM vendors WHERE name = ?", (name,)
        ).fetchone()
        return None if row is None else self.get_vendor(int(row["id"]))

    def observe_bank_account(
        self,
        vendor_id: int,
        account_identifier: str,
        first_seen: datetime,
    ) -> None:
        """Record an untrusted first sighting without granting baseline approval."""
        account = normalise_identifier(account_identifier)
        if not account or first_seen.tzinfo is None:
            raise ValueError("Account observations need an identifier and timezone")
        with self.connection:
            self.connection.execute(
                """INSERT INTO vendor_bank_accounts
                (vendor_id, account_identifier_normalised, first_seen, approved_by_user)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(vendor_id, account_identifier_normalised) DO NOTHING""",
                (vendor_id, account, first_seen.isoformat()),
            )

    def approve_bank_account(
        self, vendor_id: int, account_identifier: str, *, approved_by: str = "local user"
    ) -> None:
        """Remember an explicitly human-approved canonical payment identifier."""
        account = normalise_identifier(account_identifier)
        if not account or not approved_by.strip() or len(approved_by) > 200:
            raise ValueError("Account and approver name are required")
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute(
                """INSERT INTO vendor_bank_accounts
                (vendor_id, account_identifier_normalised, first_seen,
                 approved_by_user, approved_at, approved_by_name)
                VALUES (?, ?, ?, 1, ?, ?) ON CONFLICT(vendor_id, account_identifier_normalised)
                DO UPDATE SET approved_by_user = 1, approved_at = excluded.approved_at,
                approved_by_name = excluded.approved_by_name""",
                (vendor_id, account, now, now, approved_by.strip()),
            )

    def approved_accounts(self, vendor_id: int) -> tuple[str, ...]:
        """Return only explicitly approved bank baselines."""
        rows = self.connection.execute(
            """SELECT account_identifier_normalised FROM vendor_bank_accounts
            WHERE vendor_id = ? AND approved_by_user = 1 ORDER BY first_seen""",
            (vendor_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

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
        """Persist finite Decimal as text with a timezone-aware timestamp."""
        if not isinstance(amount, Decimal) or not amount.is_finite():
            raise ValueError("Amount must be a finite Decimal")
        if received_at.tzinfo is None or not invoice_number.strip():
            raise ValueError("Invoice requires a timezone-aware date and a number")
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO invoices
                (vendor_id, invoice_number, amount, currency,
                 content_hash, received_at, verdict)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    vendor_id,
                    invoice_number,
                    str(amount),
                    currency,
                    content_hash,
                    received_at.isoformat(),
                    verdict,
                ),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def list_history(self, vendor_id: int | None = None) -> tuple[HistoricalInvoice, ...]:
        """Read records without numeric SQLite coercion."""
        if vendor_id is None:
            rows = self.connection.execute("SELECT * FROM invoices ORDER BY received_at, id")
        else:
            rows = self.connection.execute(
                "SELECT * FROM invoices WHERE vendor_id = ? ORDER BY received_at, id",
                (vendor_id,),
            )
        return tuple(
            HistoricalInvoice(
                id=row["id"],
                vendor_id=row["vendor_id"],
                invoice_number=row["invoice_number"],
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                content_hash=row["content_hash"],
                received_at=datetime.fromisoformat(row["received_at"]),
                verdict=row["verdict"],
            )
            for row in rows
        )

    def list_vendors(self) -> tuple[Vendor, ...]:
        """List established local vendor identities in name order."""
        rows = self.connection.execute("SELECT id FROM vendors ORDER BY name").fetchall()
        return tuple(vendor for row in rows if (vendor := self.get_vendor(row[0])) is not None)

    def bank_accounts(self, vendor_id: int) -> tuple[BankAccount, ...]:
        """List observed and approved accounts with their human audit trail."""
        rows = self.connection.execute(
            "SELECT * FROM vendor_bank_accounts WHERE vendor_id = ? ORDER BY first_seen",
            (vendor_id,),
        )
        return tuple(
            BankAccount(
                identifier=row["account_identifier_normalised"],
                approved=bool(row["approved_by_user"]),
                approved_at=row["approved_at"],
                approved_by=row["approved_by_name"],
            )
            for row in rows
        )

    def save_report(self, report_id: str, filename: str, report_json: str) -> None:
        """Persist an immutable report snapshot without storing the original upload."""
        with self.connection:
            self.connection.execute(
                "INSERT INTO reports VALUES (?, ?, ?)", (report_id, filename, report_json)
            )

    def get_report(self, report_id: str) -> tuple[str, str] | None:
        """Read a report snapshot by its opaque identifier."""
        row = self.connection.execute(
            "SELECT filename, report FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return None if row is None else (str(row["filename"]), str(row["report"]))

    def invoice_vendor(self, invoice_id: int) -> Vendor | None:
        """Resolve the actual ledger identity selected for a persisted invoice."""
        row = self.connection.execute(
            "SELECT vendor_id FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        return self.get_vendor(row[0]) if row else None
