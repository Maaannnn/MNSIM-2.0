#!/usr/bin/env bash
# ============================================================
# 实验 0：rram_formal_v3 穷举评估（Ground Truth）
#
# 目的：对 formal_v3 空间全部 36 个设计点逐一评估，
#       得到真实 Pareto Front，用于验证搜索算法结果。
#
# 使用方式（本机 MPS）：
#   bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh
#
# 使用方式（服务器 CUDA）：
#   DEVICE=cuda PYTHON_BIN=python bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
DEVICE="${DEVICE:-mps}"
MAX_ACC_BATCHES="${MAX_ACC_BATCHES:-4}"
ACCURACY_TARGET="${ACCURACY_TARGET:-0.88}"
MATRIX_CSV="${MATRIX_CSV:-artifacts/dse/matrices/rram_v2/matrix_E.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-artifacts/dse/matrix_runs/exp_formal_v3_exhaustive}"
NN_NAME="${NN_NAME:-vgg8}"
WEIGHTS_PATH="${WEIGHTS_PATH:-cifar10_vgg8_params.pth}"
BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-SimConfig.ini}"

echo "[exhaustive] root           : ${ROOT_DIR}"
echo "[exhaustive] python         : ${PYTHON_BIN}"
echo "[exhaustive] device         : ${DEVICE}"
echo "[exhaustive] matrix csv     : ${MATRIX_CSV}"
echo "[exhaustive] output root    : ${OUTPUT_ROOT}"
echo "[exhaustive] accuracy target: ${ACCURACY_TARGET}"

"${PYTHON_BIN}" dse/run_matrix_csv.py \
  --matrix-csv "${MATRIX_CSV}" \
  --base-config "${BASE_CONFIG_PATH}" \
  --nn "${NN_NAME}" \
  --weights "${WEIGHTS_PATH}" \
  --run-accuracy \
  --max-acc-batches "${MAX_ACC_BATCHES}" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --enable-saf \
  --enable-variation \
  --device "${DEVICE}" \
  --output-root "${OUTPUT_ROOT}"

echo
echo "[exhaustive] done."
echo "[exhaustive] results: ${OUTPUT_ROOT}"
echo
echo "[exhaustive] next: run analysis"
echo "  bash artifacts/dse/scripts/finalize_search_run.sh ${OUTPUT_ROOT} ${ACCURACY_TARGET}"
