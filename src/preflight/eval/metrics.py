"""Explicit binary triage metrics and Wilson intervals using Decimal arithmetic."""

from decimal import Decimal

from preflight.models import StrictModel


class Rate(StrictModel):
    """Point estimate and Wilson 95% interval; zero denominators are undefined."""

    value: str | None
    lower: str | None
    upper: str | None
    numerator: int
    denominator: int


class Metrics(StrictModel):
    """A non-PASS verdict is a positive triage decision, not proof of fraud."""

    tp: int
    fp: int
    tn: int
    fn: int
    precision: Rate
    recall: Rate
    false_positive_rate: Rate


def rate(successes: int, total: int) -> Rate:
    """Calculate the two-sided Wilson score interval with z=1.959963984540054."""
    if not 0 <= successes <= total:
        raise ValueError("Invalid binomial counts")
    if total == 0:
        return Rate(value=None, lower=None, upper=None, numerator=successes, denominator=total)
    n = Decimal(total)
    p = Decimal(successes) / n
    z = Decimal("1.959963984540054")
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * (p * (1 - p) / n + z * z / (4 * n * n)).sqrt() / denominator
    return Rate(
        value=str(p.quantize(Decimal("0.000001"))),
        lower=str(max(Decimal(0), center - radius).quantize(Decimal("0.000001"))),
        upper=str(min(Decimal(1), center + radius).quantize(Decimal("0.000001"))),
        numerator=successes,
        denominator=total,
    )


def metrics(tp: int, fp: int, tn: int, fn: int) -> Metrics:
    """Keep counts alongside every ratio to make denominators reviewable."""
    return Metrics(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=rate(tp, tp + fp),
        recall=rate(tp, tp + fn),
        false_positive_rate=rate(fp, fp + tn),
    )
