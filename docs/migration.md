# Migration Notes

This project keeps compatibility shims for older paths while moving toward a
cleaner open-source layout.

## Script Path Compatibility

Script implementations are grouped by purpose:

- `scripts/reporting/`
- `scripts/benchmark/`
- `scripts/maintenance/`

Top-level script entry points under `scripts/` are compatibility wrappers that
forward to the grouped implementations.

## Config Path Compatibility

Canonical config locations:

- `configs/runtime/`
- `configs/reporting/`

Legacy top-level files in `configs/` are still supported by loader fallbacks.
New integrations should target canonical locations.
