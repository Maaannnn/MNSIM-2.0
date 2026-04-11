#!/usr/bin/env bash
# ============================================================
# 后处理脚本：重建 comparison + 生成 HTML 分析报告
#
# 用法（单个实验目录）：
#   bash artifacts/dse/scripts/finalize_search_run.sh <run_root> [accuracy_target] [topk]
#
# 用法（合并多个实验目录进行联合分析）：
#   MERGE_INPUTS="dir1 dir2 dir3" \
#   bash artifacts/dse/scripts/finalize_search_run.sh <primary_run_root> 0.88 30
#
# 示例：合并穷举结果 + 搜索结果 联合分析
#   MERGE_INPUTS="artifacts/dse/matrix_runs/exp_formal_v3_exhaustive artifacts/dse/search_runs/exp01_formal_v3" \
#   bash artifacts/dse/scripts/finalize_search_run.sh artifacts/dse/search_runs/exp01_formal_v3 0.88 30
# ============================================================
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash artifacts/dse/scripts/finalize_search_run.sh <run_root> [accuracy_target] [topk]"
  echo "       MERGE_INPUTS=\"dir1 dir2\" bash ... (optional: merge multiple sources)"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

RUN_ROOT="$1"
ACCURACY_TARGET="${2:-0.88}"
TOPK="${3:-30}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
MERGE_INPUTS="${MERGE_INPUTS:-}"   # space-separated extra input dirs (optional)

if [[ ! -d "${RUN_ROOT}" ]]; then
  echo "[finalize] ERROR: run root not found: ${RUN_ROOT}"
  exit 1
fi

echo "[finalize] root            : ${ROOT_DIR}"
echo "[finalize] python          : ${PYTHON_BIN}"
echo "[finalize] run root        : ${RUN_ROOT}"
echo "[finalize] accuracy target : ${ACCURACY_TARGET}"
echo "[finalize] topk            : ${TOPK}"
[[ -n "${MERGE_INPUTS}" ]] && echo "[finalize] merge inputs    : ${MERGE_INPUTS}"

echo
echo "[finalize] Step 1/3: rebuild comparison and plots ..."
"${PYTHON_BIN}" dse/run_dse.py \
  --compare-only \
  --plots \
  --output-root "${RUN_ROOT}"

echo
echo "[finalize] Step 2/3: build HTML analysis ..."
if [[ -z "${MERGE_INPUTS}" ]]; then
  "${PYTHON_BIN}" dse/analyze_results.py \
    --input "${RUN_ROOT}" \
    --output-dir "${RUN_ROOT}/analysis" \
    --accuracy-target "${ACCURACY_TARGET}" \
    --topk "${TOPK}"
else
  # shellcheck disable=SC2086
  "${PYTHON_BIN}" dse/analyze_results.py \
    --input "${RUN_ROOT}" ${MERGE_INPUTS} \
    --output-dir "${RUN_ROOT}/analysis" \
    --accuracy-target "${ACCURACY_TARGET}" \
    --topk "${TOPK}"
fi

echo
echo "[finalize] Step 3/3: done."
echo "[finalize] comparison dir  : ${RUN_ROOT}/comparison"
echo "[finalize] analysis html   : ${RUN_ROOT}/analysis/index.html"
echo "[finalize] summary json    : ${RUN_ROOT}/analysis/summary.json"
echo "[finalize] top configs csv : ${RUN_ROOT}/analysis/top_configs.csv"
