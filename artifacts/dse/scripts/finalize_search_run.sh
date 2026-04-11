#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash artifacts/dse/scripts/finalize_search_run.sh <search_run_root> [accuracy_target] [topk]"
  echo "Example:"
  echo "  bash artifacts/dse/scripts/finalize_search_run.sh artifacts/dse/search_runs/rram_formal_v3_gpu1 0.88 30"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

RUN_ROOT="$1"
ACCURACY_TARGET="${2:-0.88}"
TOPK="${3:-30}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

if [[ ! -d "${RUN_ROOT}" ]]; then
  echo "[finalize] ERROR: run root not found: ${RUN_ROOT}"
  exit 1
fi

echo "[finalize] root            : ${ROOT_DIR}"
echo "[finalize] python          : ${PYTHON_BIN}"
echo "[finalize] run root        : ${RUN_ROOT}"
echo "[finalize] accuracy target : ${ACCURACY_TARGET}"
echo "[finalize] topk            : ${TOPK}"

echo
echo "[finalize] Step 1/3: rebuild comparison and plots ..."
"${PYTHON_BIN}" dse/run_dse.py \
  --compare-only \
  --plots \
  --output-root "${RUN_ROOT}"

echo
echo "[finalize] Step 2/3: build generic HTML analysis ..."
"${PYTHON_BIN}" dse/analyze_results.py \
  --input "${RUN_ROOT}" \
  --output-dir "${RUN_ROOT}/analysis" \
  --accuracy-target "${ACCURACY_TARGET}" \
  --topk "${TOPK}"

echo
echo "[finalize] Step 3/3: done."
echo "[finalize] comparison dir  : ${RUN_ROOT}/comparison"
echo "[finalize] analysis html   : ${RUN_ROOT}/analysis/index.html"
echo "[finalize] summary json    : ${RUN_ROOT}/analysis/summary.json"
echo "[finalize] top configs csv : ${RUN_ROOT}/analysis/top_configs.csv"

