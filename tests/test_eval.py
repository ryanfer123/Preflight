"""Offline evaluation integrity: denominators, noise, reproducibility and fixed gates."""

from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from preflight.eval.cases import GROUPS, generate
from preflight.eval.harness import Evaluation, evaluate, gate_failures, load_gates
from preflight.eval.metrics import rate
from preflight.eval.reporting import markdown
from preflight.extract.documents import ingest
from preflight.extract.evidence import evidence_error


@pytest.fixture(scope="module")
def measured() -> Evaluation:
    return evaluate()


def test_corpus_size_labels_and_noise() -> None:
    cases = generate()
    assert len(cases) >= 400
    assert {case.kind for case in cases} == set(GROUPS)
    assert len({case.id for case in cases}) == len(cases)
    assert {case.noise for case in cases} >= {
        "none",
        "wrong_but_cited_bank",
        "wrong_but_cited_amount",
        "dropped_bank",
        "dropped_total",
    }
    assert any(not case.malicious for case in cases if case.kind == "approved_bank_change")


def test_seed_controls_reproducible_documents_and_labels() -> None:
    first, second = generate(per_group=2), generate(per_group=2)
    assert first == second
    assert first != generate(seed=2027, per_group=2)


def test_noise_is_validly_cited_without_fabricated_source() -> None:
    for case in generate(per_group=3):
        assert evidence_error(case.extraction, ingest(case.document)) is None
        if case.noise == "wrong_but_cited_bank":
            assert case.extraction.invoice.bank != case.truth.bank


def test_real_pipeline_reveals_expected_misses(measured: Evaluation) -> None:
    assert measured.case_count == 480
    assert measured.overall.tp + measured.overall.fn == 240
    assert measured.overall.fp + measured.overall.tn == 240
    missed = {
        item.noise for item in measured.outcomes if item.malicious and item.actual == "PASS"
    }
    assert {"wrong_but_cited_bank", "wrong_but_cited_amount", "dropped_bank"} <= missed
    assert measured.per_type["clean"].false_positive_rate.numerator == 0
    assert measured.per_type["constant_changed"].false_positive_rate.numerator > 0
    assert measured.per_type["legitimate_reply_service"].false_positive_rate.numerator > 0


def test_ablation_and_baseline_are_measured(measured: Evaluation) -> None:
    assert len(measured.ablations) == 7
    assert Decimal(measured.ablations["bank_change"].recall_lost) > 0
    assert Decimal(measured.ablations["sender"].recall_lost) > 0
    assert Decimal(measured.overall.recall.value or "0") > Decimal(
        measured.baseline.recall.value or "0"
    )
    assert sum(sum(row.values()) for row in measured.confusion.values()) == measured.case_count


def test_gate_accepts_baseline_and_rejects_regressions(measured: Evaluation) -> None:
    gates = load_gates(Path("data/eval-gates.json"))
    assert gate_failures(measured, gates) == ()
    for kind in ("bank_change", "reply_to", "lookalike"):
        original = measured.per_type[kind]
        changed = original.model_copy(update={"recall": rate(0, 24)})
        broken = measured.model_copy(update={"per_type": {**measured.per_type, kind: changed}})
        assert any(kind in message for message in gate_failures(broken, gates))
    clean = measured.per_type["clean"].model_copy(update={"false_positive_rate": rate(24, 24)})
    broken = measured.model_copy(update={"per_type": {**measured.per_type, "clean": clean}})
    assert any("Clean" in message for message in gate_failures(broken, gates))


def test_gate_cannot_silently_drop_critical_types(measured: Evaluation) -> None:
    gates = load_gates(Path("data/eval-gates.json"))
    assert gate_failures(measured, gates.model_copy(update={"critical_recall_min": {}}))


def test_report_is_generated_from_machine_results(measured: Evaluation) -> None:
    gates = load_gates(Path("data/eval-gates.json"))
    assert Evaluation.model_validate_json(measured.model_dump_json()) == measured
    document = markdown(measured, gates)
    assert "False negatives" in document
    assert "wrong_but_cited_bank" in document
    assert "zero-MAD" in document
    assert markdown(measured, gates) == document


@given(st.integers(min_value=1, max_value=10000), st.integers(min_value=0, max_value=10000))
def test_wilson_interval_contains_estimate(total: int, supplied: int) -> None:
    successes = min(supplied, total)
    result = rate(successes, total)
    assert result.lower is not None and result.upper is not None and result.value is not None
    assert (
        Decimal(0)
        <= Decimal(result.lower)
        <= Decimal(result.value)
        <= Decimal(result.upper)
        <= 1
    )


def test_wilson_boundary_and_undefined_denominators() -> None:
    assert rate(0, 0).value is None
    assert rate(0, 24).lower == "0.000000"
    assert rate(24, 24).upper == "1.000000"
    assert rate(50, 100).lower == "0.403832"
    with pytest.raises(ValueError):
        rate(2, 1)
