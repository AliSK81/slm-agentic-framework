# Changelog

## 0.5.0 — framework-only (2026-05-22)

### Removed

- Entire `src/aviona/` CLI product layer, Aviona tests, install/live-gate scripts, and `aviona-daily` model profile.

## 0.4.0 — interactive control protocol (2026-05-21)

### Added

- Framework interactive turn protocol (ICP): turn-type binding, tool results in WM, terminate-after-tool, finalizer, compound edit/run handoffs.
- Expanded interactive integration and failure-mode test coverage.

## 0.3.0 — production session path (2026-05-20)

### Added

- LangGraph production path with SqliteSaver checkpointer.
- Eval harness: ablation A–D, quality gate, manifests, decision JSONL, curated reports.
