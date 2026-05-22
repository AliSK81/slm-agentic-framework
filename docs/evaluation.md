# Evaluation Workflows

The benchmark harness is under `eval/` and includes datasets, metrics, and
scenario runners.

## Ablation Dry Run

```bash
python -m eval.scenarios.ablation --dataset humaneval_hard --n 10 --seeds 42 --dry-run
```

## Typical Evaluation Run

```bash
python -m eval.scenarios.ablation --dataset humaneval_hard --n 10 --seeds 42
```

## Output Artifacts

Evaluation runs may write into `traces/`, `logs/`, and `checkpoints/` depending
on scenario settings.
