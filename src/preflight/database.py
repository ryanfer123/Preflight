"""Select Supabase Postgres explicitly; SQLite remains the offline test adapter."""

import os
from pathlib import Path

from preflight.ledger import Ledger
from preflight.supabase_ledger import SupabaseLedger

LedgerBackend = Ledger | SupabaseLedger


def open_ledger(target: str | Path) -> LedgerBackend:
    """Select by explicit URL; never fall back to local data after a database failure."""
    value = str(target)
    if value.startswith(("postgresql://", "postgres://")):
        return SupabaseLedger(value)
    return Ledger(target)


def configured_database() -> str:
    """Require Supabase for the application unless SQLite is explicitly selected."""
    if value := os.environ.get("PREFLIGHT_DATABASE_URL"):
        if not value.startswith(("postgresql://", "postgres://")):
            raise ValueError("PREFLIGHT_DATABASE_URL must be a PostgreSQL connection URL")
        return value
    if value := os.environ.get("PREFLIGHT_DATABASE"):
        return value
    raise ValueError("Configure PREFLIGHT_DATABASE_URL for Supabase; see README quickstart")
