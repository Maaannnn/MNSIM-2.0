#!/usr/bin/env bash
set -euo pipefail

# Fair multi-objective benchmark runner for:
# 1) BO+GP (single-objective baseline)
# 2) NSGA-II + Surrogate
# 3) MOBO (ParEGO)
#
# Design goal: keep REAL evaluation budget comparable.
#
# Usage:
#   bash run_fair_moo_benchmark.sh
#   bash run_fair_moo_benchmark.sh --weights "/abs/path/to/cifar10_vgg8_params.pth" --nn vgg8 --repeats 3 --budget 24

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

NN="vgg8"
WEIGHTS="${ROOT_DIR}/cifar10_vgg8_params.pth"
BASE_CONFIG="${ROOT_DIR}/SimConfig.ini"
REPEATS=3
SEED_START=42
BUDGET=24
BO_INIT=6
MOBO_INIT=6
NSGA_INIT=6
NSGA_EVALS_PER_GEN=3
OUT_ROOT="${ROOT_DIR}/dse_fair_benchmark"
RUN_ACCURACY=0
BO_TWO_STAGE=1
BO_TOPK_ACCURACY=3
ACCURACY_TARGET=0.90
ACCURACY_PENALTY=120
ENABLE_SAF=1
ENABLE_VARIATION=0
ENABLE_RRATIO=0
FIXED_QRANGE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nn) NN="$2"; shift 2 ;;
    --weights) WEIGHTS="$2"; shift 2 ;;
    --base-config) BASE_CONFIG="$2"; shift 2 ;;
    --repeats) REPEATS="$2"; shift 2 ;;
    --seed-start) SEED_START="$2"; shift 2 ;;
    --budget) BUDGET="$2"; shift 2 ;;
    --bo-init) BO_INIT="$2"; shift 2 ;;
    --mobo-init) MOBO_INIT="$2"; shift 2 ;;
    --nsga-init) NSGA_INIT="$2"; shift 2 ;;
    --nsga-evals-per-gen) NSGA_EVALS_PER_GEN="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --run-accuracy) RUN_ACCURACY=1; shift 1 ;;
    --bo-no-two-stage) BO_TWO_STAGE=0; shift 1 ;;
    --bo-topk-accuracy) BO_TOPK_ACCURACY="$2"; shift 2 ;;
    --accuracy-target) ACCURACY_TARGET="$2"; shift 2 ;;
    --accuracy-penalty) ACCURACY_PENALTY="$2"; shift 2 ;;
    --disable-saf) ENABLE_SAF=0; shift 1 ;;
    --enable-variation) ENABLE_VARIATION=1; shift 1 ;;
    --enable-rratio) ENABLE_RRATIO=1; shift 1 ;;
    --fixed-qrange) FIXED_QRANGE=1; shift 1 ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if [[ ! -f "${WEIGHTS}" ]]; then
  echo "Weights not found: ${WEIGHTS}" >&2
  exit 1
fi
if [[ ! -f "${BASE_CONFIG}" ]]; then
  echo "Config not found: ${BASE_CONFIG}" >&2
  exit 1
fi

if (( BO_INIT > BUDGET || MOBO_INIT > BUDGET || NSGA_INIT > BUDGET )); then
  echo "init evaluations cannot exceed budget" >&2
  exit 1
fi

NSGA_GENS=$(( (BUDGET - NSGA_INIT + NSGA_EVALS_PER_GEN - 1) / NSGA_EVALS_PER_GEN ))
if (( NSGA_GENS < 1 )); then
  NSGA_GENS=1
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_ROOT="${OUT_ROOT}/run_${TIMESTAMP}"
mkdir -p "${RUN_ROOT}"

echo "== Fair MOO Benchmark =="
echo "root             : ${ROOT_DIR}"
echo "run_root         : ${RUN_ROOT}"
echo "nn               : ${NN}"
echo "weights          : ${WEIGHTS}"
echo "budget (target)  : ${BUDGET}"
echo "repeats          : ${REPEATS}"
echo "seed_start       : ${SEED_START}"
echo "BO init          : ${BO_INIT}"
echo "MOBO init        : ${MOBO_INIT}"
echo "NSGA init        : ${NSGA_INIT}"
echo "NSGA eval/gen    : ${NSGA_EVALS_PER_GEN}"
echo "NSGA generations : ${NSGA_GENS}"
echo "run accuracy     : ${RUN_ACCURACY}"
echo "BO two-stage     : ${BO_TWO_STAGE}"
echo "BO topk accuracy : ${BO_TOPK_ACCURACY}"
if (( RUN_ACCURACY == 1 )); then
  echo "accuracy target  : ${ACCURACY_TARGET}"
  echo "accuracy penalty : ${ACCURACY_PENALTY}"
fi
echo "enable SAF       : ${ENABLE_SAF}"
echo "enable variation : ${ENABLE_VARIATION}"
echo "enable rratio    : ${ENABLE_RRATIO}"
echo "fixed qrange     : ${FIXED_QRANGE}"
echo

for ((i=0; i<REPEATS; i++)); do
  SEED=$((SEED_START + i))
  REP_DIR="${RUN_ROOT}/seed_${SEED}"
  mkdir -p "${REP_DIR}"

  BO_DIR="${REP_DIR}/bo"
  NSGA_DIR="${REP_DIR}/nsga2"
  MOBO_DIR="${REP_DIR}/mobo"
  CMP_DIR="${REP_DIR}/compare"

  mkdir -p "${BO_DIR}" "${NSGA_DIR}" "${MOBO_DIR}" "${CMP_DIR}"

  echo "---- Repeat $((i+1))/${REPEATS}, seed=${SEED} ----"
  echo "Launching 3 methods in parallel..."

  BO_ACC_ARGS=()
  COMMON_ACC_ARGS=()
  if (( RUN_ACCURACY == 1 )); then
    BO_ACC_ARGS+=(--run-accuracy --accuracy-target "${ACCURACY_TARGET}" --accuracy-penalty "${ACCURACY_PENALTY}")
    COMMON_ACC_ARGS+=(--run-accuracy)
  fi
  if (( BO_TWO_STAGE == 1 )); then
    BO_ACC_ARGS+=(--two-stage --topk-accuracy "${BO_TOPK_ACCURACY}")
  fi
  if (( ENABLE_SAF == 1 )); then
    BO_ACC_ARGS+=(--enable-saf)
    COMMON_ACC_ARGS+=(--enable-saf)
  fi
  if (( ENABLE_VARIATION == 1 )); then
    BO_ACC_ARGS+=(--enable-variation)
    COMMON_ACC_ARGS+=(--enable-variation)
  fi
  if (( ENABLE_RRATIO == 1 )); then
    BO_ACC_ARGS+=(--enable-rratio)
    COMMON_ACC_ARGS+=(--enable-rratio)
  fi
  if (( FIXED_QRANGE == 1 )); then
    BO_ACC_ARGS+=(--fixed-qrange)
    COMMON_ACC_ARGS+=(--fixed-qrange)
  fi

  (
    cd "${ROOT_DIR}"
    "${PYTHON_BIN}" dse_bo_gp.py \
      --base-config "${BASE_CONFIG}" \
      --weights "${WEIGHTS}" \
      --nn "${NN}" \
      --iterations "${BUDGET}" \
      --init-random "${BO_INIT}" \
      --seed "${SEED}" \
      "${BO_ACC_ARGS[@]}" \
      --output-dir "${BO_DIR}" \
      > "${BO_DIR}/run.log" 2>&1
  ) &
  PID_BO=$!

  (
    cd "${ROOT_DIR}"
    "${PYTHON_BIN}" dse_nsga2_surrogate.py \
      --base-config "${BASE_CONFIG}" \
      --weights "${WEIGHTS}" \
      --nn "${NN}" \
      --generations "${NSGA_GENS}" \
      --population 20 \
      --init-evals "${NSGA_INIT}" \
      --evals-per-gen "${NSGA_EVALS_PER_GEN}" \
      --seed "${SEED}" \
      "${COMMON_ACC_ARGS[@]}" \
      --output-dir "${NSGA_DIR}" \
      > "${NSGA_DIR}/run.log" 2>&1
  ) &
  PID_NSGA=$!

  (
    cd "${ROOT_DIR}"
    "${PYTHON_BIN}" dse_mobo_parego.py \
      --base-config "${BASE_CONFIG}" \
      --weights "${WEIGHTS}" \
      --nn "${NN}" \
      --iterations "${BUDGET}" \
      --init-random "${MOBO_INIT}" \
      --seed "${SEED}" \
      "${COMMON_ACC_ARGS[@]}" \
      --output-dir "${MOBO_DIR}" \
      > "${MOBO_DIR}/run.log" 2>&1
  ) &
  PID_MOBO=$!

  FAIL=0
  wait "${PID_BO}" || FAIL=1
  wait "${PID_NSGA}" || FAIL=1
  wait "${PID_MOBO}" || FAIL=1

  if (( FAIL == 1 )); then
    echo "One or more methods failed for seed ${SEED}. Check logs:"
    echo "  ${BO_DIR}/run.log"
    echo "  ${NSGA_DIR}/run.log"
    echo "  ${MOBO_DIR}/run.log"
    exit 1
  fi

  echo "All methods finished. Comparing..."
  (
    cd "${ROOT_DIR}"
    "${PYTHON_BIN}" compare_dse_results.py \
      --bo-dir "${BO_DIR}" \
      --nsga2-dir "${NSGA_DIR}" \
      --mobo-dir "${MOBO_DIR}" \
      --output-dir "${CMP_DIR}" \
      > "${CMP_DIR}/run.log" 2>&1
  )

  echo "Repeat seed=${SEED} done."
  echo
done

echo "Building global summary..."
"${PYTHON_BIN}" - <<'PY' "${RUN_ROOT}"
import csv, glob, os, statistics, json, sys
run_root = sys.argv[1]
paths = glob.glob(os.path.join(run_root, "seed_*", "compare", "compare_summary.csv"))
rows = []
for p in paths:
    with open(p, newline="", encoding="utf-8") as f:
        rows.extend(list(csv.DictReader(f)))
if not rows:
    raise SystemExit("No compare_summary.csv found")

by_method = {}
for r in rows:
    by_method.setdefault(r["method"], []).append(r)

out_csv = os.path.join(run_root, "global_summary.csv")
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["method","runs","mean_evaluated","mean_pareto_size","mean_best_latency_ns","mean_best_energy_nj","mean_best_area_um2"])
    out_json = {}
    for m, rs in by_method.items():
        def vals(k):
            out=[]
            for x in rs:
                v=x.get(k,"")
                if v!="":
                    out.append(float(v))
            return out
        ev = vals("evaluated")
        pa = vals("pareto_size")
        la = vals("best_latency_ns")
        en = vals("best_energy_nj")
        ar = vals("best_area_um2")
        row = [
            m, len(rs),
            statistics.mean(ev) if ev else "",
            statistics.mean(pa) if pa else "",
            statistics.mean(la) if la else "",
            statistics.mean(en) if en else "",
            statistics.mean(ar) if ar else "",
        ]
        w.writerow(row)
        out_json[m] = {
            "runs": len(rs),
            "mean_evaluated": row[2],
            "mean_pareto_size": row[3],
            "mean_best_latency_ns": row[4],
            "mean_best_energy_nj": row[5],
            "mean_best_area_um2": row[6],
        }

out_json_path = os.path.join(run_root, "global_summary.json")
with open(out_json_path, "w", encoding="utf-8") as f:
    json.dump(out_json, f, indent=2, ensure_ascii=False)

print("global summary csv :", out_csv)
print("global summary json:", out_json_path)
PY

echo
echo "Benchmark completed: ${RUN_ROOT}"
