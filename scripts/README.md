# Scripts Directory

This directory contains project utilities for smoke checks, diagnostics, and
evaluation/report workflows.

Scripts are grouped by purpose:

- `scripts/reporting/`: trace analysis and report generation
- `scripts/benchmark/`: smoke and benchmark execution helpers
- `scripts/maintenance/`: maintenance and data hygiene utilities

## Common Scripts

- `scripts/benchmark/smoke_test.py`: quick end-to-end task run against configured provider
- `scripts/reporting/analyze_traces.py`: summarize and inspect trace artifacts
- `scripts/reporting/generate_report.py`: produce curated summary reports
- `scripts/reporting/diagnose_e2e.py`: troubleshoot e2e setup and provider connectivity
- `scripts/benchmark/run_benchmark_batch.py`: execute benchmark batches

These scripts are contributor utilities and may assume repository-local paths.
