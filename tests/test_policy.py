"""Exhaustive deterministic policy branches and validated configuration."""

import pytest
from pydantic import ValidationError

from preflight.checks.common import finding
from preflight.models import Severity
from preflight.policy import decide, load_policy
from tests.factories import context


@pytest.mark.parametrize(
    ("severities", "expected", "score"),
    [
        ([Severity.INFO], "PASS", 0),
        ([Severity.LOW] * 4, "PASS", 4),
        ([Severity.LOW] * 5, "REVIEW", 5),
        ([Severity.LOW] * 6, "REVIEW", 6),
        ([Severity.HIGH], "REVIEW", 5),
        ([Severity.CRITICAL], "BLOCK", 10),
        ([Severity.CRITICAL, Severity.HIGH], "BLOCK", 15),
        ([], "REVIEW", 0),
    ],
)
def test_policy_branches(severities: list[Severity], expected: str, score: int) -> None:
    findings = [
        finding(context(), "test", "total", "Observation", value) for value in severities
    ]
    decision = decide(findings, load_policy())
    assert decision.verdict == expected
    assert decision.score == score


def test_high_and_critical_ignore_weights() -> None:
    policy = load_policy()
    weights = policy.severity_weights.model_copy(update={"high": 0, "critical": 0})
    policy = policy.model_copy(update={"severity_weights": weights})
    for severity, expected in ((Severity.HIGH, "REVIEW"), (Severity.CRITICAL, "BLOCK")):
        assert (
            decide([finding(context(), "x", "total", "x", severity)], policy).verdict
            == expected
        )


def test_unverifiable_is_visible_and_not_sufficient_for_pass() -> None:
    unknown = finding(context(), "sender", "document", "unverifiable", unverifiable=True)
    decision = decide([unknown], load_policy())
    assert decision.verdict == "REVIEW"
    assert decision.unverifiable_checks == ("sender",)
    known = finding(context(), "arithmetic", "total", "Verified")
    decision = decide([unknown, known], load_policy())
    assert decision.verdict == "PASS"
    assert decision.unverifiable_checks == ("sender",)


def test_pressure_cannot_force_review_alone() -> None:
    findings = [
        finding(context(), "pressure_language", "document", "Urgent", Severity.LOW)
        for _ in range(100)
    ]
    decision = decide(findings, load_policy())
    assert decision.score == 2
    assert decision.verdict == "PASS"


@pytest.mark.parametrize(
    "change",
    [
        {"review_threshold": 0},
        {"pressure_cap": -1},
        {"arithmetic_tolerance": "-0.1"},
        {"anomaly_threshold": "NaN"},
        {"unknown": True},
        {"pressure_patterns": [""]},
        {"pressure_patterns": ["["]},
    ],
)
def test_bad_config(change: dict[str, object]) -> None:
    import json

    policy = load_policy().model_dump(mode="json")
    policy.update(change)
    with pytest.raises((ValidationError, ValueError)):
        load_policy().model_validate_json(json.dumps(policy))
