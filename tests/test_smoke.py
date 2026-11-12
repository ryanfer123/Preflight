"""Offline smoke-report accounting; live execution is deliberately separate from CI."""

import json
from pathlib import Path

import pytest

from preflight.extract.fake import FakeExtractor
from preflight.extract.openai_compatible import OpenAICompatibleExtractor
from preflight.models import ExtractionFailure, InvoiceExtraction
from preflight.smoke import SmokeConfigurationError, smoke


def test_smoke_requires_explicit_live_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PREFLIGHT_BASE_URL", raising=False)
    monkeypatch.delenv("PREFLIGHT_MODEL", raising=False)
    with pytest.raises(SmokeConfigurationError):
        smoke(Path("samples"), tmp_path / "result.json")


@pytest.mark.parametrize("failure", [False, True])
def test_smoke_report_field_and_schema_accounting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: bool
) -> None:
    registry = json.loads(Path("samples/fixtures.json").read_text())
    fixtures = {
        key: InvoiceExtraction.model_validate_json(json.dumps(value))
        for key, value in registry.items()
    }
    fake = (
        FakeExtractor(
            result=ExtractionFailure(reason="Provider output failed schema validation twice")
        )
        if failure
        else FakeExtractor(fixtures)
    )
    monkeypatch.setenv("PREFLIGHT_BASE_URL", "http://offline.example/v1")
    monkeypatch.setenv("PREFLIGHT_MODEL", "offline-test")
    monkeypatch.setattr(OpenAICompatibleExtractor, "from_env", classmethod(lambda cls: fake))
    output = tmp_path / "smoke.json"
    assert smoke(Path("samples"), output) == (1 if failure else 0)
    result = json.loads(output.read_text())
    assert result["requests"] == 5
    assert result["field_accuracy"]["value"] == ("0.000000" if failure else "1.000000")
    assert result["schema_failure_rate"]["numerator"] == (5 if failure else 0)
    assert result["terminal_extraction_failure_rate"]["numerator"] == (5 if failure else 0)
