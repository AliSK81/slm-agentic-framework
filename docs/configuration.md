# Configuration Layout

Configuration files are now grouped by intent:

- `configs/runtime/`: runtime framework and evaluation config
  - `models.yaml`
  - `memory.yaml`
  - `truncation.yaml`
  - `eval.yaml`
- `configs/reporting/`: benchmark and reporting assets
  - `cite_allowlist.yaml`
  - `humaneval_hard_ids.txt`

Compatibility is preserved: legacy paths in `configs/` are still kept so
existing scripts and external references continue to work.
