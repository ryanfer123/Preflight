"""Offline adapter contracts; actual Supabase integration runs outside the socket guard."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from preflight.database import configured_database, open_ledger
from preflight.ledger import Ledger
from preflight.supabase_ledger import SupabaseLedger

URL = "postgresql://postgres:synthetic-local-test@localhost:5432/postgres"


def test_explicit_backend_selection_and_no_silent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert isinstance(open_ledger(URL), SupabaseLedger)
    assert isinstance(open_ledger(":memory:"), Ledger)
    monkeypatch.delenv("PREFLIGHT_DATABASE_URL", raising=False)
    monkeypatch.delenv("PREFLIGHT_DATABASE", raising=False)
    with pytest.raises(ValueError, match="PREFLIGHT_DATABASE_URL"):
        configured_database()
    monkeypatch.setenv("PREFLIGHT_DATABASE_URL", "not-a-postgres-url")
    with pytest.raises(ValueError, match="PostgreSQL"):
        configured_database()
    monkeypatch.setenv("PREFLIGHT_DATABASE_URL", URL)
    assert configured_database() == URL
    with patch("psycopg.connect", side_effect=RuntimeError("unavailable")):
        with pytest.raises(RuntimeError, match="unavailable"), open_ledger(URL):
            pass


def test_hosted_postgres_requires_tls() -> None:
    with pytest.raises(ValueError, match="TLS"):
        SupabaseLedger("postgresql://postgres@db.example/postgres")
    SupabaseLedger("postgresql://postgres@db.example/postgres?sslmode=verify-full")


def test_supabase_lifetime_and_bounded_connection() -> None:
    adapter = SupabaseLedger(URL)
    with pytest.raises(RuntimeError):
        _ = adapter.connection
    with patch("psycopg.connect") as connect:
        with adapter:
            with pytest.raises(RuntimeError, match="already open"):
                adapter.__enter__()
        assert connect.call_args.kwargs["connect_timeout"] == 10
        assert connect.call_args.kwargs["prepare_threshold"] is None
        assert "statement_timeout=10000" in connect.call_args.kwargs["options"]
        connect.return_value.close.assert_called_once()


def test_money_and_sql_parameters_are_preserved() -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = {"id": 1}
    payload = "x'); DROP TABLE invoices;--"
    with patch("psycopg.connect", return_value=connection), SupabaseLedger(URL) as ledger:
        assert (
            ledger.record_invoice(
                1, payload, Decimal("118.001"), "INR", "hash", datetime.now(UTC), "PASS"
            )
            == 1
        )
        query, parameters = connection.execute.call_args.args
        assert payload not in query
        assert parameters[1] == payload
        assert parameters[2] == "118.001"
        with pytest.raises(ValueError):
            ledger.record_invoice(1, "x", Decimal("NaN"), "INR", "h", datetime.now(UTC), "PASS")


def test_observations_cannot_approve() -> None:
    connection = MagicMock()
    with patch("psycopg.connect", return_value=connection), SupabaseLedger(URL) as ledger:
        ledger.observe_bank_account(1, "ACCOUNT:123|IFSC:SBIN0001234", datetime.now(UTC))
        query, parameters = connection.execute.call_args.args
        assert "approved_by_user" not in query
        assert parameters[1] == "account:123|ifsc:sbin0001234"
        ledger.approve_bank_account(1, "ACCOUNT:123|IFSC:SBIN0001234", approved_by="Ryan")
        query, parameters = connection.execute.call_args.args
        assert "approved_by_name" in query
        assert parameters[-1] == "Ryan"


def test_private_schema_has_rls_and_no_browser_grants() -> None:
    migrations = tuple(Path("supabase/migrations").glob("*.sql"))
    assert migrations
    source = "\n".join(path.read_text() for path in migrations)
    for table in ("vendors", "vendor_bank_accounts", "invoices", "reports"):
        assert f"ALTER TABLE preflight.{table} ENABLE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL ON SCHEMA preflight FROM PUBLIC" in source
    assert "GRANT ALL" not in source


def test_report_storage_survives_contexts(tmp_path: Path) -> None:
    database = tmp_path / "offline.sqlite3"
    with open_ledger(database) as ledger:
        ledger.save_report("opaque", "invoice.pdf", '{"verdict":"REVIEW"}')
    with open_ledger(database) as ledger:
        assert ledger.get_report("opaque") == ("invoice.pdf", '{"verdict":"REVIEW"}')
        assert ledger.get_report("missing") is None
