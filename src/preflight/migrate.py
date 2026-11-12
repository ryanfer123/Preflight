"""Apply reviewed private-schema migrations explicitly to the configured Supabase DB."""

import argparse
from pathlib import Path

from preflight.database import configured_database
from preflight.supabase_ledger import SupabaseLedger


def migrate(directory: Path) -> None:
    """Apply each migration once with an integrity hash and transaction rollback on failure."""
    from hashlib import sha256

    with SupabaseLedger(configured_database()) as ledger:
        connection = ledger.connection
        connection.execute("CREATE SCHEMA IF NOT EXISTS preflight")
        connection.execute("REVOKE ALL ON SCHEMA preflight FROM PUBLIC")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS preflight.schema_migrations "
            "(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL)"
        )
        connection.execute("ALTER TABLE preflight.schema_migrations ENABLE ROW LEVEL SECURITY")
        connection.commit()
        for path in sorted(directory.glob("*.sql")):
            source = path.read_text()
            digest = sha256(source.encode()).hexdigest()
            previous = connection.execute(
                "SELECT sha256 FROM preflight.schema_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if previous:
                if previous["sha256"] != digest:
                    raise ValueError("Applied migration has changed; add a new migration")
                continue
            try:
                connection.execute(source)
                connection.execute(
                    "INSERT INTO preflight.schema_migrations VALUES (%s,%s)",
                    (path.name, digest),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            print("Applied " + path.name)


def main() -> None:
    """Migrations are explicit and never silently run against a hosted database on startup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("supabase/migrations"))
    args = parser.parse_args()
    migrate(args.directory)


if __name__ == "__main__":
    main()
