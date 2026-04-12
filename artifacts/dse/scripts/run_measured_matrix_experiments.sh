#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -x ".venv/bin/python" ]]; then
  DEFAULT_PYTHON=".venv/bin/python"
else
  DEFAULT_PYTHON="python3"
fi

PYTHON_BIN="${PYTHON_BIN:-${DEFAULT_PYTHON}}"
STAMP="$(date '+%Y%m%d_%H%M%S')"
MEASURED_PRESETS_CSV="${MEASURED_PRESETS_CSV:-artifacts/dse/testdata_analysis/measured_presets.csv}"
MATRIX_CSV="${MATRIX_CSV:-artifacts/dse/matrices/rram_v2/matrix_all.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-artifacts/dse/matrix_runs/measured_run_${STAMP}}"
BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-SimConfig.ini}"
WEIGHTS_PATH="${WEIGHTS_PATH:-cifar10_vgg8_params.pth}"
NN_NAME="${NN_NAME:-vgg8}"
DEVICE="${DEVICE:-cpu}"
DATASET_MODULE="${DATASET_MODULE:-MNSIM.Interface.cifar10}"
SPACE_PROFILE="${SPACE_PROFILE:-rram_v2}"
MAX_ACC_BATCHES="${MAX_ACC_BATCHES:-4}"
ACCURACY_TARGET="${ACCURACY_TARGET:-0.88}"
SEED="${SEED:-42}"
WORKERS="${WORKERS:-1}"
PRESET_NAMES="${PRESET_NAMES:-}"
MATRIX_NAMES="${MATRIX_NAMES:-}"
MAX_POINTS="${MAX_POINTS:-}"
DRY_RUN="${DRY_RUN:-0}"
FAIL_FAST="${FAIL_FAST:-0}"

echo "[measured-matrix] root         : ${ROOT_DIR}"
echo "[measured-matrix] python       : ${PYTHON_BIN}"
echo "[measured-matrix] presets csv  : ${MEASURED_PRESETS_CSV}"
echo "[measured-matrix] matrix csv   : ${MATRIX_CSV}"
echo "[measured-matrix] output root  : ${OUTPUT_ROOT}"
echo "[measured-matrix] device       : ${DEVICE}"
echo "[measured-matrix] workers      : ${WORKERS}"

CMD=(
  "${PYTHON_BIN}" dse/extras/run_measured_matrix.py
  --measured-presets-csv "${MEASURED_PRESETS_CSV}"
  --matrix-csv "${MATRIX_CSV}"
  --base-config "${BASE_CONFIG_PATH}"
  --weights "${WEIGHTS_PATH}"
  --nn "${NN_NAME}"
  --device "${DEVICE}"
  --dataset-module "${DATASET_MODULE}"
  --space-profile "${SPACE_PROFILE}"
  --max-acc-batches "${MAX_ACC_BATCHES}"
  --run-accuracy
  --accuracy-target "${ACCURACY_TARGET}"
  --enable-saf
  --enable-variation
  --seed "${SEED}"
  --workers "${WORKERS}"
  --python-bin "${PYTHON_BIN}"
  --output-root "${OUTPUT_ROOT}"
)

if [[ -n "${PRESET_NAMES}" ]]; then
  # shellcheck disable=SC2206
  PRESET_NAMES_ARR=(${PRESET_NAMES})
  CMD+=(--preset-name "${PRESET_NAMES_ARR[@]}")
fi

if [[ -n "${MATRIX_NAMES}" ]]; then
  # shellcheck disable=SC2206
  MATRIX_NAMES_ARR=(${MATRIX_NAMES})
  CMD+=(--matrix-name "${MATRIX_NAMES_ARR[@]}")
fi

if [[ -n "${MAX_POINTS}" ]]; then
  CMD+=(--max-points "${MAX_POINTS}")
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  CMD+=(--dry-run)
fi

if [[ "${FAIL_FAST}" == "1" ]]; then
  CMD+=(--fail-fast)
fi

"${CMD[@]}"
