#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
DEVICE="${DEVICE:-mps}"
WORKERS="${WORKERS:-3}"
SEEDS="${SEEDS:-42 43 44}"
BUDGET="${BUDGET:-18}"
INIT_EVALS="${INIT_EVALS:-6}"
POPULATION="${POPULATION:-12}"
EVALS_PER_GEN="${EVALS_PER_GEN:-4}"
MAX_ACC_BATCHES="${MAX_ACC_BATCHES:-4}"
ACCURACY_TARGET="${ACCURACY_TARGET:-0.88}"
OUTPUT_ROOT="${OUTPUT_ROOT:-artifacts/dse/search_runs/exp01_formal_v3}"
NN_NAME="${NN_NAME:-vgg8}"
WEIGHTS_PATH="${WEIGHTS_PATH:-cifar10_vgg8_params.pth}"
BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-SimConfig.ini}"
ALGOS="${ALGOS:-random nsga2 mobo}"

echo "[formal-v3] root         : ${ROOT_DIR}"
echo "[formal-v3] python       : ${PYTHON_BIN}"
echo "[formal-v3] device       : ${DEVICE}"
echo "[formal-v3] workers      : ${WORKERS}"
echo "[formal-v3] seeds        : ${SEEDS}"
echo "[formal-v3] budget       : ${BUDGET}"
echo "[formal-v3] output root  : ${OUTPUT_ROOT}"
echo "[formal-v3] algos        : ${ALGOS}"

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
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches "${MAX_ACC_BATCHES}" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --enable-saf \
  --enable-variation \
  --device "${DEVICE}" \
  --output-root "${OUTPUT_ROOT}" \
  --plots

