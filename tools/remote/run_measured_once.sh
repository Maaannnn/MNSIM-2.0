#!/usr/bin/env bash
set -euo pipefail
ROOT="/data/home/jiaqizhao/zcustom/MNSIM-2.0"
cd "$ROOT"
SESSION="mnsim_measured_$(date +%m%d_%H%M)"
LOG="artifacts/dse/search_runs/logs/${SESSION}.log"
mkdir -p "${LOG%/*}"
if command -v tmux >/dev/null 2>&1; then
  (tmux has-session -t "${SESSION}" 2>/dev/null && tmux kill-session -t "${SESSION}") || true
  tmux new-session -d -s "${SESSION}" "bash -lc 'cd ${ROOT} && nohup bash tools/remote/auto_experiment.sh measured >> ${LOG} 2>&1 &'"
  echo "[remote] tmux session=${SESSION} log=${LOG}"
else
  nohup bash tools/remote/auto_experiment.sh measured >> "${LOG}" 2>&1 &
  echo "[remote] nohup started log=${LOG}"
fi
