#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

GUIDANCE_GPU="${GUIDANCE_GPU:-0}"
FORMAL_GPU="${FORMAL_GPU:-1}"

GUIDANCE_SEEDS="${GUIDANCE_SEEDS:-42 43 44}"
FORMAL_SEEDS="${FORMAL_SEEDS:-42 43 44}"

GUIDANCE_BUDGET="${GUIDANCE_BUDGET:-48}"
FORMAL_BUDGET="${FORMAL_BUDGET:-24}"

GUIDANCE_INIT_EVALS="${GUIDANCE_INIT_EVALS:-8}"
FORMAL_INIT_EVALS="${FORMAL_INIT_EVALS:-6}"

GUIDANCE_POPULATION="${GUIDANCE_POPULATION:-16}"
FORMAL_POPULATION="${FORMAL_POPULATION:-12}"

GUIDANCE_EVALS_PER_GEN="${GUIDANCE_EVALS_PER_GEN:-4}"
FORMAL_EVALS_PER_GEN="${FORMAL_EVALS_PER_GEN:-4}"

GUIDANCE_WORKERS="${GUIDANCE_WORKERS:-1}"
FORMAL_WORKERS="${FORMAL_WORKERS:-1}"

MAX_ACC_BATCHES="${MAX_ACC_BATCHES:-4}"
ACCURACY_TARGET="${ACCURACY_TARGET:-0.88}"

NN_NAME="${NN_NAME:-vgg8}"
WEIGHTS_PATH="${WEIGHTS_PATH:-cifar10_vgg8_params.pth}"
BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-SimConfig.ini}"

GUIDANCE_OUTPUT_ROOT="${GUIDANCE_OUTPUT_ROOT:-artifacts/dse/search_runs/rram_guidance_v4_gpu${GUIDANCE_GPU}}"
FORMAL_OUTPUT_ROOT="${FORMAL_OUTPUT_ROOT:-artifacts/dse/search_runs/rram_formal_v3_gpu${FORMAL_GPU}}"

GUIDANCE_LOG="${GUIDANCE_LOG:-${GUIDANCE_OUTPUT_ROOT}.log}"
FORMAL_LOG="${FORMAL_LOG:-${FORMAL_OUTPUT_ROOT}.log}"

mkdir -p "$(dirname "${GUIDANCE_LOG}")" "$(dirname "${FORMAL_LOG}")"

echo "[dual-a100] root            : ${ROOT_DIR}"
echo "[dual-a100] python          : ${PYTHON_BIN}"
echo "[dual-a100] guidance gpu    : ${GUIDANCE_GPU}"
echo "[dual-a100] formal gpu      : ${FORMAL_GPU}"
echo "[dual-a100] guidance out    : ${GUIDANCE_OUTPUT_ROOT}"
echo "[dual-a100] formal out      : ${FORMAL_OUTPUT_ROOT}"
echo "[dual-a100] guidance log    : ${GUIDANCE_LOG}"
echo "[dual-a100] formal log      : ${FORMAL_LOG}"

nohup env CUDA_VISIBLE_DEVICES="${GUIDANCE_GPU}" "${PYTHON_BIN}" dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds ${GUIDANCE_SEEDS} \
  --budget "${GUIDANCE_BUDGET}" \
  --init-evals "${GUIDANCE_INIT_EVALS}" \
  --population "${GUIDANCE_POPULATION}" \
  --evals-per-gen "${GUIDANCE_EVALS_PER_GEN}" \
  --workers "${GUIDANCE_WORKERS}" \
  --nn "${NN_NAME}" \
  --weights "${WEIGHTS_PATH}" \
  --base-config "${BASE_CONFIG_PATH}" \
  --space-profile rram_guidance_v4 \
  --run-accuracy \
  --max-acc-batches "${MAX_ACC_BATCHES}" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root "${GUIDANCE_OUTPUT_ROOT}" \
  --plots \
  > "${GUIDANCE_LOG}" 2>&1 &
GUIDANCE_PID=$!

nohup env CUDA_VISIBLE_DEVICES="${FORMAL_GPU}" "${PYTHON_BIN}" dse/run_dse.py \
  --algos random nsga2 mobo \
  --seeds ${FORMAL_SEEDS} \
  --budget "${FORMAL_BUDGET}" \
  --init-evals "${FORMAL_INIT_EVALS}" \
  --population "${FORMAL_POPULATION}" \
  --evals-per-gen "${FORMAL_EVALS_PER_GEN}" \
  --workers "${FORMAL_WORKERS}" \
  --nn "${NN_NAME}" \
  --weights "${WEIGHTS_PATH}" \
  --base-config "${BASE_CONFIG_PATH}" \
  --space-profile rram_formal_v3 \
  --run-accuracy \
  --max-acc-batches "${MAX_ACC_BATCHES}" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --enable-saf \
  --enable-variation \
  --device cuda:0 \
  --output-root "${FORMAL_OUTPUT_ROOT}" \
  --plots \
  > "${FORMAL_LOG}" 2>&1 &
FORMAL_PID=$!

echo "[dual-a100] guidance pid    : ${GUIDANCE_PID}"
echo "[dual-a100] formal pid      : ${FORMAL_PID}"
echo "[dual-a100] check logs with :"
echo "  tail -f ${GUIDANCE_LOG}"
echo "  tail -f ${FORMAL_LOG}"
echo "[dual-a100] check gpu with  :"
echo "  watch -n 1 nvidia-smi"

