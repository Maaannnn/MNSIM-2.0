#!/usr/bin/env bash
# One-shot DSE: three algorithms, one seed, comparison plots.
# Output directory: default AUTO in run_dse.py → <repo>/dse_runs/run_<timestamp>/ (never overwrites old runs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
cd "$ROOT"
"${PYTHON}" dse/run_dse.py \
  --algos bo_gp nsga2 mobo \
  --seeds 42 \
  --budget 24 \
  --init-evals 6 \
  --nn vgg8 \
  --weights "${ROOT}/cifar10_vgg8_params.pth" \
  --base-config "${ROOT}/SimConfig.ini" \
  --plots
