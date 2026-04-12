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
OUTPUT_ROOT="${OUTPUT_ROOT:-artifacts/dse/testdata_runs/run_${STAMP}}"

if [[ -n "${TEST_DATA_DIR:-}" ]]; then
  RESOLVED_TEST_DATA_DIR="${TEST_DATA_DIR}"
elif [[ -d "test_data" ]]; then
  RESOLVED_TEST_DATA_DIR="test_data"
elif [[ -d "../test_data" ]]; then
  RESOLVED_TEST_DATA_DIR="../test_data"
elif [[ -d "/data/mnsim/test_data" ]]; then
  RESOLVED_TEST_DATA_DIR="/data/mnsim/test_data"
else
  echo "[testdata] error        : test_data directory not found." >&2
  echo "[testdata] hint         : set TEST_DATA_DIR=/path/to/test_data" >&2
  exit 1
fi

echo "[testdata] root         : ${ROOT_DIR}"
echo "[testdata] python       : ${PYTHON_BIN}"
echo "[testdata] test data    : ${RESOLVED_TEST_DATA_DIR}"
echo "[testdata] output root  : ${OUTPUT_ROOT}"

"${PYTHON_BIN}" dse/extras/extract_measured_presets.py \
  --test-data-dir "${RESOLVED_TEST_DATA_DIR}" \
  --output-dir "${OUTPUT_ROOT}"

echo "[testdata] done"
echo "[testdata] summary      : ${OUTPUT_ROOT}/summary.json"
echo "[testdata] presets      : ${OUTPUT_ROOT}/measured_presets.csv"
echo "[testdata] cycle states : ${OUTPUT_ROOT}/cycle_state_summary.csv"
echo "[testdata] retention    : ${OUTPUT_ROOT}/retention_phase_summary.csv"
