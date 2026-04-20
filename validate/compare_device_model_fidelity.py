#!/usr/bin/env python3
"""
Leave-one-wafer-out validation for device-model fidelity on measured RRAM data.

Goal
----
Quantify whether pim_sim's asymmetric variation model better matches our wafer
measurements than an MNSIM-compatible symmetric Gaussian baseline.

Important boundary
------------------
- This script validates the *device variation model* only.
- It does not claim anything about external literature chips.
- It intentionally excludes SAF-heavy outlier tails from the primary metric via
  conservative IQR filtering, because the current SAF mapping is still a proxy.

Outputs
-------
- validate/output/device_fidelity/leave_one_wafer_out.csv
- validate/output/device_fidelity/leave_one_wafer_out_summary.txt
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pim_sim.device.model import AsymmetricGaussianModel, SymmetricGaussianModel


@dataclass(frozen=True)
class WaferState:
    wafer_id: str
    state: str
    mean_ohm: float
    cv_pct: float
    n_raw: int
    n_filtered: int
    filtered_fraction_pct: float
    samples: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare MNSIM symmetric vs pim_sim asymmetric device models on measured wafers."
    )
    parser.add_argument(
        "--wafer-dir",
        default=str(ROOT / "test_data" / "2T1R_cycle"),
        help="Directory containing wafer_xy*.csv files",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=50_000,
        help="Maximum rows to read per wafer CSV",
    )
    parser.add_argument(
        "--n-eval-samples",
        type=int,
        default=5_000,
        help="Synthetic sample count per state when computing distribution metrics",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Random seed for synthetic sampling",
    )
    parser.add_argument(
        "--output-csv",
        default=str(ROOT / "validate" / "output" / "device_fidelity" / "leave_one_wafer_out.csv"),
        help="Per-wafer CSV output path",
    )
    parser.add_argument(
        "--output-summary",
        default=str(ROOT / "validate" / "output" / "device_fidelity" / "leave_one_wafer_out_summary.txt"),
        help="Summary report output path",
    )
    return parser.parse_args()


def _safe_float(v: object) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _iqr_filter(arr: np.ndarray, factor: float = 10.0) -> np.ndarray:
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    lo, hi = q1 - factor * iqr, q3 + factor * iqr
    filtered = arr[(arr >= lo) & (arr <= hi)]
    return filtered if len(filtered) > 10 else arr


def load_wafer_states(csv_path: Path, max_rows: int) -> list[WaferState]:
    hrs_raw: list[float] = []
    lrs_raw: list[float] = []
    read_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if read_count >= max_rows:
                break
            resistance = _safe_float(row.get("R_cell"))
            if resistance is None or resistance <= 0:
                continue
            curve = (row.get("Curve Name") or "").strip()
            if curve == "teERS":
                hrs_raw.append(resistance)
            elif curve == "bePGM":
                lrs_raw.append(resistance)
            read_count += 1

    if not hrs_raw or not lrs_raw:
        raise ValueError(f"missing HRS/LRS data in {csv_path}")

    result: list[WaferState] = []
    for state_name, raw_values in (("hrs", hrs_raw), ("lrs", lrs_raw)):
        raw_arr = np.asarray(raw_values, dtype=float)
        filtered_arr = _iqr_filter(raw_arr)
        mean_ohm = float(np.mean(filtered_arr))
        cv_pct = float(np.std(filtered_arr) / mean_ohm * 100.0)
        filtered_fraction_pct = (1.0 - len(filtered_arr) / len(raw_arr)) * 100.0
        result.append(
            WaferState(
                wafer_id=csv_path.stem,
                state=state_name,
                mean_ohm=mean_ohm,
                cv_pct=cv_pct,
                n_raw=int(len(raw_arr)),
                n_filtered=int(len(filtered_arr)),
                filtered_fraction_pct=filtered_fraction_pct,
                samples=filtered_arr,
            )
        )
    return result


def wasserstein_mean_abs_diff(a: np.ndarray, b: np.ndarray, n_quantiles: int = 1024) -> float:
    q = np.linspace(0.0, 1.0, n_quantiles)
    qa = np.quantile(a, q)
    qb = np.quantile(b, q)
    return float(np.mean(np.abs(qa - qb)))


def deterministic_seed(base_seed: int, *parts: str) -> int:
    acc = int(base_seed)
    for part in parts:
        for ch in part.encode("utf-8"):
            acc = (acc * 131 + ch) % (2**32)
    return acc


def fit_train_models(train_states: list[WaferState]) -> tuple[float, float, float]:
    hrs_cvs = [s.cv_pct for s in train_states if s.state == "hrs"]
    lrs_cvs = [s.cv_pct for s in train_states if s.state == "lrs"]
    symmetric_variation_pct = float(np.mean(hrs_cvs + lrs_cvs))
    asymmetric_hrs_cv = float(np.mean(hrs_cvs))
    asymmetric_lrs_cv = float(np.mean(lrs_cvs))
    return symmetric_variation_pct, asymmetric_hrs_cv, asymmetric_lrs_cv


def evaluate_model(
    model_name: str,
    state: WaferState,
    sample_values: np.ndarray,
    train_params: dict[str, float],
) -> dict[str, object]:
    pred_mean = float(np.mean(sample_values))
    pred_cv = float(np.std(sample_values) / pred_mean * 100.0)
    cv_abs_error_pctpt = abs(pred_cv - state.cv_pct)
    wasserstein_pct_of_mean = wasserstein_mean_abs_diff(sample_values, state.samples) / state.mean_ohm * 100.0
    return {
        "wafer_id": state.wafer_id,
        "state": state.state,
        "model_name": model_name,
        "truth_mean_ohm": f"{state.mean_ohm:.6f}",
        "truth_cv_pct": f"{state.cv_pct:.6f}",
        "pred_mean_ohm": f"{pred_mean:.6f}",
        "pred_cv_pct": f"{pred_cv:.6f}",
        "cv_abs_error_pctpt": f"{cv_abs_error_pctpt:.6f}",
        "wasserstein_pct_of_mean": f"{wasserstein_pct_of_mean:.6f}",
        "n_raw": state.n_raw,
        "n_filtered": state.n_filtered,
        "filtered_fraction_pct": f"{state.filtered_fraction_pct:.6f}",
        "train_symmetric_variation_pct": f"{train_params['sym']:.6f}",
        "train_asym_hrs_cv_pct": f"{train_params['asym_hrs']:.6f}",
        "train_asym_lrs_cv_pct": f"{train_params['asym_lrs']:.6f}",
        "evaluation_note": (
            "LOO robust-wafer validation. Nominal resistance is set to the held-out wafer mean "
            "to isolate variation-model fidelity; SAF-heavy tails are excluded by conservative IQR filtering."
        ),
    }


def aggregate_model(rows: list[dict[str, object]], model_name: str, metric_key: str) -> float:
    values = [float(r[metric_key]) for r in rows if r["model_name"] == model_name]
    return float(np.mean(values)) if values else float("nan")


def aggregate_model_state(
    rows: list[dict[str, object]],
    model_name: str,
    metric_key: str,
    state: str,
) -> float:
    values = [
        float(r[metric_key])
        for r in rows
        if r["model_name"] == model_name and r["state"] == state
    ]
    return float(np.mean(values)) if values else float("nan")


def main() -> int:
    args = parse_args()
    wafer_dir = Path(args.wafer_dir)
    csv_files = sorted(wafer_dir.glob("wafer_xy*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"no wafer_xy*.csv files found in {wafer_dir}")

    all_states: list[WaferState] = []
    for csv_path in csv_files:
        all_states.extend(load_wafer_states(csv_path, max_rows=args.max_rows))

    rows: list[dict[str, object]] = []
    for heldout_csv in csv_files:
        heldout_states = [s for s in all_states if s.wafer_id == heldout_csv.stem]
        train_states = [s for s in all_states if s.wafer_id != heldout_csv.stem]
        sym_var, asym_hrs, asym_lrs = fit_train_models(train_states)
        sym_model = SymmetricGaussianModel(variation_pct=sym_var)
        asym_model = AsymmetricGaussianModel(state_cv_pct=[asym_hrs, asym_lrs])

        for state in heldout_states:
            state_index = 0 if state.state == "hrs" else 1
            n_eval = min(args.n_eval_samples, len(state.samples))
            rng_sym = np.random.default_rng(deterministic_seed(args.seed, state.wafer_id, state.state, "sym"))
            rng_asym = np.random.default_rng(deterministic_seed(args.seed, state.wafer_id, state.state, "asym"))
            sym_samples = sym_model.sample_resistance(
                nominal_resistance=state.mean_ohm,
                state_index=state_index,
                shape=n_eval,
                rng=rng_sym,
            )
            asym_samples = asym_model.sample_resistance(
                nominal_resistance=state.mean_ohm,
                state_index=state_index,
                shape=n_eval,
                rng=rng_asym,
            )
            train_params = {"sym": sym_var, "asym_hrs": asym_hrs, "asym_lrs": asym_lrs}
            rows.append(evaluate_model("mnsim_symmetric_fit", state, sym_samples, train_params))
            rows.append(evaluate_model("pim_sim_asymmetric_fit", state, asym_samples, train_params))

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    sym_cv_mae = aggregate_model(rows, "mnsim_symmetric_fit", "cv_abs_error_pctpt")
    asym_cv_mae = aggregate_model(rows, "pim_sim_asymmetric_fit", "cv_abs_error_pctpt")
    sym_wass = aggregate_model(rows, "mnsim_symmetric_fit", "wasserstein_pct_of_mean")
    asym_wass = aggregate_model(rows, "pim_sim_asymmetric_fit", "wasserstein_pct_of_mean")
    cv_improvement_pct = (sym_cv_mae - asym_cv_mae) / sym_cv_mae * 100.0 if sym_cv_mae > 0 else 0.0
    wass_improvement_pct = (sym_wass - asym_wass) / sym_wass * 100.0 if sym_wass > 0 else 0.0
    state_lines: list[str] = []
    for state in ("hrs", "lrs"):
        state_sym_cv = aggregate_model_state(rows, "mnsim_symmetric_fit", "cv_abs_error_pctpt", state)
        state_asym_cv = aggregate_model_state(rows, "pim_sim_asymmetric_fit", "cv_abs_error_pctpt", state)
        state_cv_gain = (state_sym_cv - state_asym_cv) / state_sym_cv * 100.0 if state_sym_cv > 0 else 0.0
        state_sym_wass = aggregate_model_state(rows, "mnsim_symmetric_fit", "wasserstein_pct_of_mean", state)
        state_asym_wass = aggregate_model_state(rows, "pim_sim_asymmetric_fit", "wasserstein_pct_of_mean", state)
        state_wass_gain = (state_sym_wass - state_asym_wass) / state_sym_wass * 100.0 if state_sym_wass > 0 else 0.0
        state_lines.extend(
            [
                f"- {state.upper()} CV absolute error: {state_sym_cv:.4f} -> {state_asym_cv:.4f} pct-pts "
                f"({state_cv_gain:.2f}% reduction)",
                f"- {state.upper()} normalized Wasserstein: {state_sym_wass:.4f}% -> {state_asym_wass:.4f}% "
                f"({state_wass_gain:.2f}% reduction)",
            ]
        )

    summary_lines = [
        "Device Model Fidelity Validation",
        "=" * 60,
        "",
        f"Wafer directory: {wafer_dir}",
        f"Wafers processed: {len(csv_files)}",
        f"Rows per wafer cap: {args.max_rows}",
        f"Synthetic eval samples per state: {args.n_eval_samples}",
        "",
        "Models compared:",
        "- mnsim_symmetric_fit: single fitted Device_Variation shared by HRS and LRS",
        "- pim_sim_asymmetric_fit: separate fitted HRS/LRS CV values",
        "",
        "Primary metric:",
        f"- mean state CV absolute error: {sym_cv_mae:.4f} -> {asym_cv_mae:.4f} pct-pts "
        f"({cv_improvement_pct:.2f}% reduction)",
        "",
        "Secondary metric:",
        f"- mean normalized Wasserstein distance: {sym_wass:.4f}% -> {asym_wass:.4f}% "
        f"({wass_improvement_pct:.2f}% reduction)",
        "",
        "State breakdown:",
        *state_lines,
        "",
        "Boundary conditions:",
        "- Nominal resistance is fixed to the held-out wafer mean to isolate variation-model fidelity.",
        "- Robust IQR filtering excludes SAF-heavy outlier tails from the primary metric.",
        "- This validates our measured-device path only; it is not evidence about external literature chips.",
        "",
        f"Detailed rows: {output_csv}",
    ]

    output_summary = Path(args.output_summary)
    output_summary.parent.mkdir(parents=True, exist_ok=True)
    output_summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
