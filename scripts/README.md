# Scripts Directory

Smoke checks and evaluation/report workflows. All paths default to `var/` runtime dirs.

| Script | Purpose |
|--------|---------|
| `scripts/benchmark/smoke_test.py` | Quick end-to-end session against configured provider |
| `scripts/reporting/analyze_traces.py` | Summarize JSONL traces (SR, CER, qualitative metrics) |
| `scripts/reporting/generate_report.py` | Produce curated markdown evaluation report |
| `scripts/reporting/make_repro_bundle.py` | Bundle cited traces + manifests for reproduction |

## Examples

```bash
python scripts/benchmark/smoke_test.py

python scripts/reporting/analyze_traces.py --trace var/traces/D_humaneval_hard.jsonl

python scripts/reporting/generate_report.py --traces-dir var/traces

python scripts/reporting/make_repro_bundle.py --traces-dir var/traces --output var/repro
```

These are contributor utilities and may assume repository-local paths.
