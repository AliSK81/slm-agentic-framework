# Scripts Directory

This directory contains project utilities for smoke checks, diagnostics, and
evaluation/report workflows.

Implementations are grouped by purpose:

- `scripts/reporting/`: trace analysis and report generation
- `scripts/benchmark/`: smoke and benchmark execution helpers
- `scripts/maintenance/`: maintenance and data hygiene utilities

Top-level script paths are kept as compatibility wrappers so existing commands
and imports continue to work.

For new code, import from grouped paths (`scripts.reporting.*`,
`scripts.benchmark.*`, `scripts.maintenance.*`) instead of wrapper modules.

## Common Scripts

- `smoke_test.py`: quick end-to-end task run against configured provider
- `analyze_traces.py`: summarize and inspect trace artifacts
- `generate_report.py`: produce curated summary reports
- `diagnose_e2e.py`: troubleshoot e2e setup and provider connectivity
- `run_benchmark_batch.py`: execute benchmark batches

These scripts are contributor utilities and may assume repository-local paths.
