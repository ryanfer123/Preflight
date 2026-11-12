"""Full-pipeline offline comparison with fixed cases, ablations and naive baseline."""

from decimal import Decimal
from pathlib import Path

from pydantic import Field

from preflight.eval.cases import GROUPS, Case, generate, seed_ledger
from preflight.eval.metrics import Metrics, metrics
from preflight.extract.fake import FakeExtractor
from preflight.ledger import Ledger
from preflight.models import Money, StrictModel
from preflight.pipeline import CHECK_NAMES, run
from preflight.policy import Policy, load_policy


class Outcome(StrictModel):
    """One ground-truth label and observed triage decision with an auditable reason."""

    id: str
    kind: str
    malicious: bool
    expected: str
    actual: str
    noise: str
    checks: tuple[str, ...]
    gaps: tuple[str, ...]
    explanation: str


class Ablation(StrictModel):
    """A disabled check comparison; negative recall loss means disabling improved recall."""

    metrics: Metrics
    recall_lost: str
    per_attack_recall_lost: dict[str, str]


class Evaluation(StrictModel):
    """Deterministic machine-readable results; runtime is reported separately."""

    seed: int
    case_count: int
    overall: Metrics
    per_type: dict[str, Metrics]
    confusion: dict[str, dict[str, int]]
    baseline: Metrics
    ablations: dict[str, Ablation]
    outcomes: tuple[Outcome, ...]


class Gates(StrictModel):
    """Frozen regression limits, calibrated once and reviewed in version control."""

    critical_recall_min: dict[str, Money]
    clean_fpr_max: Money = Field(ge=0, le=1)
    calibration_seed: int
    calibration_cases: int
    rationale: str


def execute(
    cases: tuple[Case, ...], policy: Policy, disabled: frozenset[str] = frozenset()
) -> tuple[Outcome, ...]:
    """Run the real PDF ingestion, citations, checks, decisions and SQLite writes."""
    from preflight.eval.cases import NOW

    results: list[Outcome] = []
    for case in cases:
        with Ledger() as ledger:
            seed_ledger(ledger, case)
            report = run(
                case.document,
                case.email,
                ledger=ledger,
                policy=policy,
                extractor=FakeExtractor(result=case.extraction),
                received_at=NOW,
                disabled_checks=disabled,
            )
        results.append(
            Outcome(
                id=case.id,
                kind=case.kind,
                malicious=case.malicious,
                expected=case.expected,
                actual=report.verdict,
                noise=case.noise,
                checks=tuple(
                    sorted(
                        {
                            finding.check_id
                            for finding in report.findings
                            if finding.status == "observed" and finding.severity.value != "info"
                        }
                    )
                ),
                gaps=report.unverifiable_checks,
                explanation=case.explanation,
            )
        )
    return tuple(results)


def summarize(outcomes: tuple[Outcome, ...]) -> Metrics:
    """Compare suspicious triage against malicious labels, including legitimate reviews."""
    return metrics(
        tp=sum(item.malicious and item.actual != "PASS" for item in outcomes),
        fp=sum(not item.malicious and item.actual != "PASS" for item in outcomes),
        tn=sum(not item.malicious and item.actual == "PASS" for item in outcomes),
        fn=sum(item.malicious and item.actual == "PASS" for item in outcomes),
    )


def per_type(outcomes: tuple[Outcome, ...]) -> dict[str, Metrics]:
    """Pair each attack stratum with the same legitimate pool; benign rows use own FPR."""
    legitimate = tuple(item for item in outcomes if not item.malicious)
    result: dict[str, Metrics] = {}
    for kind in GROUPS:
        group = tuple(item for item in outcomes if item.kind == kind)
        result[kind] = summarize(group + legitimate if group[0].malicious else group)
    return result


def evaluate(seed: int = 2026, per_group: int = 24) -> Evaluation:
    """Evaluate a reproducible corpus, seven ablations and arithmetic/identifier baseline."""
    cases = generate(seed, per_group)
    policy = load_policy()
    outcomes = execute(cases, policy)
    overall = summarize(outcomes)
    strata = per_type(outcomes)
    ablations: dict[str, Ablation] = {}
    for check in sorted(CHECK_NAMES):
        altered = execute(cases, policy, frozenset({check}))
        measured = summarize(altered)
        altered_strata = per_type(altered)
        ablations[check] = Ablation(
            metrics=measured,
            recall_lost=str(
                Decimal(overall.recall.value or "0") - Decimal(measured.recall.value or "0")
            ),
            per_attack_recall_lost={
                kind: str(
                    Decimal(value.recall.value)
                    - Decimal(altered_strata[kind].recall.value or "0")
                )
                for kind, value in strata.items()
                if value.recall.value is not None
            },
        )
    naive = execute(cases, policy, CHECK_NAMES - {"arithmetic", "identifiers"})
    confusion = {
        expected: {actual: 0 for actual in ("PASS", "REVIEW", "BLOCK")}
        for expected in ("PASS", "REVIEW", "BLOCK")
    }
    for item in outcomes:
        confusion[item.expected][item.actual] += 1
    return Evaluation(
        seed=seed,
        case_count=len(cases),
        overall=overall,
        per_type=strata,
        confusion=confusion,
        baseline=summarize(naive),
        ablations=ablations,
        outcomes=outcomes,
    )


def calibrate(result: Evaluation) -> Gates:
    """Set initial limits from measured results with five/two percentage-point margins."""
    return Gates(
        critical_recall_min={
            kind: max(
                Decimal(0), Decimal(result.per_type[kind].recall.value or "0") - Decimal("0.05")
            )
            for kind in ("bank_change", "reply_to", "lookalike")
        },
        clean_fpr_max=min(
            Decimal(1),
            Decimal(result.per_type["clean"].false_positive_rate.value or "0")
            + Decimal("0.02"),
        ),
        calibration_seed=result.seed,
        calibration_cases=result.case_count,
        rationale=(
            "Initial measured recall minus 0.05; clean FPR plus 0.02. CI never recalibrates."
        ),
    )


def gate_failures(result: Evaluation, gates: Gates) -> tuple[str, ...]:
    """Fail closed on missing attack groups or critical recall/clean-FPR regressions."""
    failures: list[str] = []
    if set(gates.critical_recall_min) != {"bank_change", "reply_to", "lookalike"}:
        failures.append("Critical gate configuration is incomplete")
    for kind, minimum in gates.critical_recall_min.items():
        value = result.per_type.get(kind)
        if (
            minimum < 0
            or minimum > 1
            or value is None
            or value.recall.value is None
            or Decimal(value.recall.value) < minimum
        ):
            failures.append(f"Critical recall below fixed limit: {kind}")
    clean = result.per_type.get("clean")
    if (
        clean is None
        or clean.false_positive_rate.value is None
        or Decimal(clean.false_positive_rate.value) > gates.clean_fpr_max
    ):
        failures.append("Clean false-positive rate exceeds fixed limit")
    return tuple(failures)


def load_gates(path: Path) -> Gates:
    """Load reviewed thresholds without inferring or silently changing them."""
    return Gates.model_validate_json(path.read_text())
