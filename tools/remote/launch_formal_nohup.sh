#!/usr/bin/env bash
set -euo pipefail
ROOT="/data/home/jiaqizhao/zcustom/MNSIM-2.0"
cd "$ROOT"
LOG="artifacts/dse/search_runs/logs/formal_v3_launch_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "${LOG%/*}"
PYTHON_BIN=.venv/bin/python DEVICE=cuda WORKERS=${WORKERS:-2} BUDGET=${BUDGET:-36} nohup bash artifacts/dse/scripts/run_formal_v3_search.sh >> "$LOG" 2>&1 &
echo "$LOG"
