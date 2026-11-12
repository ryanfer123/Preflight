"""Generate measured JSON/Markdown and enforce reviewed regression gates."""

import argparse
from pathlib import Path
from time import monotonic_ns

from preflight.eval.harness import calibrate, evaluate, gate_failures, load_gates
from preflight.eval.reporting import markdown


def main() -> int:
    """Run all comparisons offline; only an explicit flag can calibrate fixed gates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=Path("artifacts/eval.json"))
    parser.add_argument("--report", type=Path, default=Path("EVAL.md"))
    parser.add_argument("--gates", type=Path, default=Path("data/eval-gates.json"))
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.calibrate and args.check:
        parser.error("Calibration cannot be combined with CI checks")
    start = monotonic_ns()
    result = evaluate(args.seed)
    if args.calibrate:
        args.gates.parent.mkdir(parents=True, exist_ok=True)
        args.gates.write_text(calibrate(result).model_dump_json(indent=2) + "\n")
    gates = load_gates(args.gates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n")
    args.report.write_text(markdown(result, gates))
    failures = gate_failures(result, gates)
    elapsed_ms = (monotonic_ns() - start) // 1_000_000
    print(
        f"{result.case_count} cases; {elapsed_ms} ms; recall={result.overall.recall.value}; "
        f"precision={result.overall.precision.value}; "
        f"FPR={result.overall.false_positive_rate.value}"
    )
    for failure in failures:
        print(failure)
    print("Gates: " + ("FAIL" if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
