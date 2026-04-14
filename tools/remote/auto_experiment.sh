#!/usr/bin/env bash
set -euo pipefail
# Auto-select experiment size by GPU availability and launch with nohup in tmux.

MODE="${1:-}"  # measured|formal_v3|guidance_v4
if [[ -z "${MODE}" ]]; then
  echo "Usage: $0 <mode: measured|formal_v3|guidance_v4>" >&2
  exit 1
fi

GPU_UTIL_MAX="${GPU_UTIL_MAX:-35}"    # below => considered idle
GPU_UTIL_BUSY="${GPU_UTIL_BUSY:-60}"  # above => considered busy
GPU_MIN_FREE_GB="${GPU_MIN_FREE_GB:-8}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
cd "${ROOT_DIR}"

log_dir="artifacts/dse/search_runs/logs"
mkdir -p "${log_dir}"
STAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${log_dir}/${MODE}_${STAMP}.log"

has_nvidia() {
  command -v nvidia-smi >/dev/null 2>&1
}

count_free_gpus() {
  local free=0
  local total=0
  if ! has_nvidia; then echo "0 0"; return; fi
  while IFS=, read -r idx util mem_used mem_total; do
    util="${util//[[:space:]]/}"
    mem_used="${mem_used//[[:space:]]/}"
    mem_total="${mem_total//[[:space:]]/}"
    local free_gb=$(( (mem_total - mem_used) / 1024 ))
    (( total++ ))
    if (( util < GPU_UTIL_MAX && free_gb > GPU_MIN_FREE_GB )); then
      (( free++ ))
    fi
  done < <(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits || true)
  echo "${free} ${total}"
}

choose_scaling() {
  local free=$1; local total=$2
  if (( free <= 0 || total <= 0 )); then
    echo "cpu 2 18" # device workers budget
    return
  fi
  if (( free >= 3 )); then echo "cuda 3 48"; return; fi
  if (( free == 2 )); then echo "cuda 2 36"; return; fi
  echo "cuda 1 24"
}

FREE_TOTAL=( $(count_free_gpus) )
FREE=${FREE_TOTAL[0]:-0}
TOTAL=${FREE_TOTAL[1]:-0}
read -r DEVICE WORKERS BUDGET < <(choose_scaling "$FREE" "$TOTAL")

# If device=cuda but torch w/ CUDA not available, downgrade to cpu
CHECK_PY="${PYTHON_BIN:-python3}"
"${CHECK_PY}" - <<'PY' || DEVICE_FALLBACK=1
import sys
try:
    import torch
    ok = torch.cuda.is_available()
    sys.exit(0 if ok else 1)
except Exception:
    sys.exit(1)
PY
if [[ "${DEVICE_FALLBACK:-0}" == "1" ]]; then DEVICE="cpu"; fi

export BASE_CONFIG_PATH="${BASE_CONFIG_PATH:-configs/SimConfig.ini}"
export WEIGHTS_PATH="${WEIGHTS_PATH:-weights/cifar10_vgg8_params.pth}"
export PYTHON_BIN="${PYTHON_BIN:-python3}"

case "${MODE}" in
  measured)
    export DEVICE WORKERS BASE_CONFIG_PATH WEIGHTS_PATH PYTHON_BIN
    nohup bash artifacts/dse/scripts/run_measured_matrix_experiments.sh \
      >> "${LOG_FILE}" 2>&1 &
    ;;
  formal_v3)
    export DEVICE WORKERS BUDGET BASE_CONFIG_PATH WEIGHTS_PATH PYTHON_BIN
    nohup bash artifacts/dse/scripts/run_formal_v3_search.sh \
      >> "${LOG_FILE}" 2>&1 &
    ;;
  guidance_v4)
    export DEVICE WORKERS BUDGET BASE_CONFIG_PATH WEIGHTS_PATH PYTHON_BIN
    nohup bash artifacts/dse/scripts/run_guidance_v4_search.sh \
      >> "${LOG_FILE}" 2>&1 &
    ;;
  *) echo "Unknown mode: ${MODE}" >&2; exit 2 ;;

esac

echo "[auto] mode=${MODE} device=${DEVICE} workers=${WORKERS} budget=${BUDGET} log=${LOG_FILE}"
