# Preflight

Evidence-based pre-payment invoice verification. Deterministic code decides;
language models only extract and explain.

Current scope: M0 tooling and M1 typed models/identifier validators.
Web, ledger, extraction, policy, evaluation and Docker are scheduled for M2-M5.

## Development

```sh
uv sync --locked --group dev
make check
```

Requires Python 3.12 and uv. Tests prohibit network connections.
See [DESIGN.md](DESIGN.md) and [AGENTS.md](AGENTS.md).

## Limitations

Identifier syntax and checksums cannot prove registration, ownership or invoice
authenticity. Missing inputs are unverifiable. IBAN validation covers generic ISO
shape and mod-97, not country-specific lengths/BBAN patterns. GST state consistency
uses registration state, not place of supply. Historical GST codes are accepted.
Existing Android starter files remain local and are outside the Python project.
