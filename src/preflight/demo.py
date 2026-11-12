"""Create reproducible synthetic demo samples and seed a local ledger safely."""

import argparse
import json
from pathlib import Path

from preflight.database import configured_database, open_ledger
from preflight.eval.cases import NOW, generate, seed_ledger
from preflight.extract.documents import ingest
from preflight.extract.fake import fixture_key

SAMPLE_KINDS = {
    "clean": "clean",
    "bank-change": "bank_change",
    "lookalike": "lookalike",
    "duplicate": "duplicate",
    "arithmetic-tamper": "arithmetic_tamper",
    "prompt-injection": "prompt_injection",
}


def prepare_samples(directory: Path) -> None:
    """Write six text-layer PDFs, their original emails and exact fixture extractions."""
    directory.mkdir(parents=True, exist_ok=True)
    cases = generate(per_group=3)
    fixtures: dict[str, object] = {}
    for filename, kind in SAMPLE_KINDS.items():
        # Index 2 is a correctly extracted bank change, not an extraction-noise case.
        case = next(item for item in cases if item.kind == kind and item.id.endswith("002"))
        (directory / (filename + ".pdf")).write_bytes(case.document.data)
        (directory / (filename + ".eml")).write_bytes(case.email.data)
        document = ingest(case.document)
        fixtures[fixture_key(document.text, list(document.images))] = json.loads(
            case.extraction.model_dump_json()
        )
    (directory / "fixtures.json").write_text(json.dumps(fixtures, indent=2) + "\n")


def seed_demo(database: str | Path) -> None:
    """Add synthetic trusted history without deleting uploads, approvals or existing data."""
    cases = generate(per_group=3)
    clean = next(item for item in cases if item.kind == "clean")
    duplicate = next(
        item for item in cases if item.kind == "duplicate" and item.id.endswith("002")
    )
    with open_ledger(database) as ledger:
        vendor = ledger.find_vendor("Acme")
        if vendor is None:
            seed_ledger(ledger, clean)
            vendor = ledger.find_vendor("Acme")
        assert vendor is not None
        if not any(
            item.invoice_number == duplicate.truth.invoice_number
            for item in ledger.list_history(vendor.id)
        ):
            assert duplicate.truth.invoice_number and duplicate.truth.total is not None
            ledger.record_invoice(
                vendor.id,
                duplicate.truth.invoice_number,
                duplicate.truth.total,
                "INR",
                "original-demo-duplicate",
                NOW,
                "PASS",
            )


def main() -> None:
    """Prepare an idempotent local demonstration; never start a provider automatically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=None)
    parser.add_argument("--samples", type=Path, default=Path("samples"))
    args = parser.parse_args()
    prepare_samples(args.samples)
    seed_demo(args.database or configured_database())
    print(f"Synthetic samples: {args.samples}; ledger seeded. Start: make serve")


if __name__ == "__main__":
    main()
