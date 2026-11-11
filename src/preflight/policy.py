"""Validated local policy and deterministic verdict decisions."""

import json
import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, field_validator

from preflight.models import Finding, Money, StrictModel


class Weights(StrictModel):
    """Nonnegative integer severity weights; informational observations score zero."""

    info: Literal[0]
    low: Annotated[int, Field(ge=0)]
    high: Annotated[int, Field(ge=0)]
    critical: Annotated[int, Field(ge=0)]


class Policy(StrictModel):
    """Trusted configuration, validated before any check runs."""

    severity_weights: Weights
    review_threshold: Annotated[int, Field(gt=0)]
    pressure_cap: Annotated[int, Field(ge=0)]
    arithmetic_tolerance: Annotated[Money, Field(ge=0)]
    anomaly_threshold: Annotated[Money, Field(gt=0)]
    pressure_patterns: tuple[str, ...]

    @field_validator("pressure_patterns")
    @classmethod
    def validate_patterns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject invalid or empty expressions when loading configuration."""
        for value in values:
            if not value or len(value) > 256:
                raise ValueError("Pressure expressions must contain 1-256 characters")
            try:
                re.compile(value)
            except re.error as error:
                raise ValueError("Invalid pressure expression") from error
        return values


class Decision(StrictModel):
    """Verdict with score and explicit gaps, independent of extraction providers."""

    verdict: Literal["PASS", "REVIEW", "BLOCK"]
    score: int
    unverifiable_checks: tuple[str, ...]
    reasons: tuple[str, ...]


def load_policy(path: str | Path = "data/policy.yaml") -> Policy:
    """Load safe YAML through the strict JSON schema; amounts must be strings."""
    with Path(path).open(encoding="utf-8") as stream:
        data: object = yaml.safe_load(stream)
    return Policy.model_validate_json(json.dumps(data))


def decide(findings: list[Finding], policy: Policy) -> Decision:
    """Critical blocks; high/threshold reviews; empty or all-unverifiable reviews."""
    gaps = tuple(sorted({item.check_id for item in findings if item.status == "unverifiable"}))
    weights = policy.severity_weights.model_dump()
    score = 0
    pressure = 0
    for item in findings:
        if item.status == "unverifiable":
            continue
        weight = int(weights[item.severity.value])
        if item.check_id == "pressure_language":
            pressure += min(weight, policy.severity_weights.low)
        else:
            score += weight
    score += min(pressure, policy.pressure_cap)
    verdict: Literal["PASS", "REVIEW", "BLOCK"] = "PASS"
    reasons: tuple[str, ...] = ()
    if any(item.severity.value == "critical" for item in findings):
        verdict, reasons = "BLOCK", ("critical_finding",)
    elif any(item.severity.value == "high" for item in findings):
        verdict, reasons = "REVIEW", ("high_finding",)
    elif score >= policy.review_threshold:
        verdict, reasons = "REVIEW", ("score_threshold",)
    elif not findings or all(item.status == "unverifiable" for item in findings):
        verdict, reasons = "REVIEW", ("insufficient_verification",)
    return Decision(verdict=verdict, score=score, unverifiable_checks=gaps, reasons=reasons)
