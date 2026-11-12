"""Explicit, non-CI five-invoice live endpoint check with no document/secret logging."""

import argparse
import json
import os
from pathlib import Path

from preflight.extract.documents import Upload, ingest
from preflight.extract.evidence import evidence_error, invoice_fields
from preflight.extract.fake import fixture_key
from preflight.extract.openai_compatible import OpenAICompatibleExtractor
from preflight.models import ExtractionFailure, InvoiceExtraction


class SmokeConfigurationError(ValueError):
    """The requested live provider has not been explicitly configured."""


def smoke(samples: Path, output: Path) -> int:
    """Send five synthetic documents to a real endpoint and measure field/schema accuracy."""
    if not os.environ.get("PREFLIGHT_BASE_URL") or not os.environ.get("PREFLIGHT_MODEL"):
        raise SmokeConfigurationError("Set PREFLIGHT_BASE_URL and PREFLIGHT_MODEL first")
    provider = OpenAICompatibleExtractor.from_env()
    registry = json.loads((samples / "fixtures.json").read_text())
    results: list[dict[str, object]] = []
    matched, fields, failures, ungrounded, schema_failures = 0, 0, 0, 0, 0
    for name in ("clean", "bank-change", "duplicate", "arithmetic-tamper", "prompt-injection"):
        print("Live extraction: " + name, flush=True)
        document = ingest(Upload(name + ".pdf", (samples / (name + ".pdf")).read_bytes()))
        expected = InvoiceExtraction.model_validate_json(
            json.dumps(registry[fixture_key(document.text, list(document.images))])
        )
        actual = provider.extract(document.text, list(document.images))
        truth = invoice_fields(expected.invoice)
        fields += len(truth)
        if isinstance(actual, ExtractionFailure):
            failures += 1
            schema_failures += "schema validation" in actual.reason
            results.append(
                {"sample": name, "status": "extraction_failed", "reason": actual.reason}
            )
            continue
        got = invoice_fields(actual.invoice)
        correct = sum(got.get(key) == value for key, value in truth.items())
        matched += correct
        citation_failure = evidence_error(actual, document)
        ungrounded += citation_failure is not None
        results.append(
            {
                "sample": name,
                "status": "success",
                "correct_fields": correct,
                "expected_fields": len(truth),
                "citation_error": citation_failure,
                "extra_fields": sorted(set(got) - set(truth)),
            }
        )
    # Import lazily so the web path does not depend on evaluation/report generation.
    from preflight.eval.metrics import rate

    report = {
        "samples": results,
        "requests": 5,
        "model": os.environ["PREFLIGHT_MODEL"],
        "provider": "OpenAICompatibleExtractor",
        "output_token_limit": 2048,
        "field_accuracy": rate(matched, fields).model_dump(),
        "terminal_extraction_failure_rate": rate(failures, 5).model_dump(),
        "schema_failure_rate": rate(schema_failures, 5).model_dump(),
        "provider_failure_rate": rate(failures - schema_failures, 5).model_dump(),
        "ungrounded_extractions": ungrounded,
        "limitation": "Terminal failures include provider/HTTP/schema failure. "
        "Schema retry events are not observable through the Extractor protocol. "
        "Successful retries are not counted. "
        "No verdict accuracy or real invoice quality claim is made.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if failures or ungrounded else 0


def main() -> int:
    """Run only by explicit invocation; absent configuration exits with a clear reason."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("samples"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/live-smoke.json"))
    args = parser.parse_args()
    try:
        return smoke(args.samples, args.output)
    except SmokeConfigurationError as error:
        print(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
