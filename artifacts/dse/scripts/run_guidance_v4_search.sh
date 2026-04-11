#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
DEVICE="${DEVICE:-mps}"
WORKERS="${WORKERS:-3}"
SEEDS="${SEEDS:-42 43 44}"
BUDGET="${BUDGET:-48}"
INIT_EVALS="${INIT_EVALS:-8}"
POPULATION="${POPULATION:-16}"
EVALS_PER_GEN="${EVALS_PER_GEN:-4}"
MAX_ACC_BATCHES="${MAX_ACC_BATCHES:-4}"
ACCURACY_TARGET="${ACCURACY_TARGET:-0.88}"
OUTPUT_ROOT="${OUTPUT_ROOT:-artifacts/dse/search_runs/rram_guidance_v4_main}"
NN_NAME="${NN_NAME:-vgg8}"
WEIGHTS_PATH="${WEIGHTS_PATH:-cifar10_vgg8_params.pth}"
BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-SimConfig.ini}"
ALGOS="${ALGOS:-random nsga2 mobo}"

echo "[guidance-v4] root        : ${ROOT_DIR}"
echo "[guidance-v4] python      : ${PYTHON_BIN}"
echo "[guidance-v4] device      : ${DEVICE}"
echo "[guidance-v4] workers     : ${WORKERS}"
echo "[guidance-v4] seeds       : ${SEEDS}"
echo "[guidance-v4] budget      : ${BUDGET}"
echo "[guidance-v4] output root : ${OUTPUT_ROOT}"
echo "[guidance-v4] algos       : ${ALGOS}"

"${PYTHON_BIN}" dse/run_dse.py \
  --algos ${ALGOS} \
  --seeds ${SEEDS} \
  --budget "${BUDGET}" \
  --init-evals "${INIT_EVALS}" \
  --population "${POPULATION}" \
  --evals-per-gen "${EVALS_PER_GEN}" \
  --workers "${WORKERS}" \
  --nn "${NN_NAME}" \
  --weights "${WEIGHTS_PATH}" \
  --base-config "${BASE_CONFIG_PATH}" \
  --space-profile rram_guidance_v4 \
  --run-accuracy \
  --max-acc-batches "${MAX_ACC_BATCHES}" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --enable-saf \
  --enable-variation \
  --device "${DEVICE}" \
  --output-root "${OUTPUT_ROOT}" \
  --plots

