#!/usr/bin/env bash
set -euo pipefail
ROOT="/data/home/jiaqizhao/zcustom/MNSIM-2.0"
cd "$ROOT"
STAMP=$(date +%m%d_%H%M)
LOG="artifacts/dse/search_runs/logs/launch_measured_${STAMP}.log"
mkdir -p "${LOG%/*}"
nohup bash tools/remote/auto_experiment.sh measured >> "$LOG" 2>&1 &
echo "$LOG"
