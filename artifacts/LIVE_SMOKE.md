# Live model smoke test

Generated from `live-smoke.json`; five synthetic samples, local Ollama with `qwen2.5:0.5b`. No user invoices or remote provider were used.

| Measure | Observed |
|---|---|
| field_accuracy | 70.00% (49/70) |
| schema_failure_rate | 20.00% (1/5) |
| provider_failure_rate | 0.00% (0/5) |
| terminal_extraction_failure_rate | 20.00% (1/5) |

Incomplete/invalid citation sets: 4. Schema success does not establish semantic accuracy or citation completeness. Every sample in this run would require REVIEW at extraction/citation validation; none constitutes a usable payment decision.

## Observed fix

The initial run in `live-smoke-initial.json` exhausted bounded transport retries on all five samples. An explicit output-token budget bounds generation. Supplying the trusted extraction schema in user-message context outside the untrusted document block removed transport failures on the subsequent run. The system prompt stayed constant and contains no document text.

The very small model still omitted fields/citations and failed schema validation on one sample. This is a compatibility probe, not a model quality recommendation. See README to reproduce; schema retries that later succeed are not counted as terminal schema failures.
