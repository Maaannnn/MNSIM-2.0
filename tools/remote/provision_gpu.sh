#!/usr/bin/env bash
set -euo pipefail
ROOT="/data/home/jiaqizhao/zcustom/MNSIM-2.0"
cd "$ROOT"
PY=python3
$PY -m pip install --user --break-system-packages -q virtualenv || true
$PY -m virtualenv .venv
.venv/bin/python -m pip install -q --upgrade pip
for IDX in cu124 cu121 cu122; do
  echo "[provision] trying index cu=${IDX}"
  if .venv/bin/python -m pip install --no-cache-dir -q --index-url https://download.pytorch.org/whl/${IDX} torch torchvision; then
    if .venv/bin/python - <<'PY'
import torch
print('version', torch.__version__)
print('cuda', torch.cuda.is_available())
PY
    then
      echo "[provision] installed torch with ${IDX}"
      exit 0
    fi
  fi
  echo "[provision] failed with ${IDX}, continuing"
done
echo "[provision] GPU wheel not available; leaving CPU setup."
exit 1
