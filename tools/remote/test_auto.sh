#!/usr/bin/env bash
set -euo pipefail
ROOT="/data/home/jiaqizhao/zcustom/MNSIM-2.0"
cd "$ROOT"
PATH="$PATH:$HOME/.local/bin:$HOME/.local/usr/bin"
which bash || true
bash --version | head -n1 || true
bash tools/remote/auto_experiment.sh measured || true
echo RC:$?
ls -l artifacts/dse/search_runs/logs || true
