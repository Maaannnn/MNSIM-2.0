"""
pim_sim.device.calibrate
========================
Extract device statistics from real RRAM test data and build
calibrated DeviceModel instances.

Two entry points:
  1. calibrate_from_measured_presets_csv  — fast; uses the already-extracted
     summary CSV produced by dse/extras/extract_measured_presets.py
  2. calibrate_from_wafer_csv            — slower; reads raw wafer cycle CSV
     and computes per-state statistics from scratch

Both return a dict mapping preset_name → AsymmetricGaussianModel.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from pim_sim.device.model import (
    AsymmetricGaussianModel,
    EmpiricalDeviceModel,
    DeviceModel,
)


# ---------------------------------------------------------------------------
# 1. Fast path: from measured_presets.csv
# ---------------------------------------------------------------------------

def calibrate_from_measured_presets_csv(
    presets_csv: str | Path,
) -> Dict[str, AsymmetricGaussianModel]:
    """Build per-preset AsymmetricGaussianModels from the extracted presets CSV.

    The CSV is produced by ``dse/extras/extract_measured_presets.py`` and
    lives at ``artifacts/dse/testdata_runs/<run>/measured_presets.csv``.

    Expected columns (subset used here):
        preset_name, hrs_mean_ohm / lrs_mean_ohm are NOT directly in the file;
        instead we use ``resistance_window_ratio`` and the summary JSON if needed.

    The CSV from extract_measured_presets actually contains the *aggregate*
    stats across the wafers in each cluster (strong/typical/weak).  The column
    ``device_variation_pct_suggested`` is the *symmetric* variation extracted
    by the old pipeline.

    This function reads per-wafer stats from the per-wafer summary CSV
    (``summary.json`` sibling) when available, falling back to a heuristic
    split otherwise.

    Parameters
    ----------
    presets_csv:
        Path to ``measured_presets.csv``.

    Returns
    -------
    Dict[str, AsymmetricGaussianModel]
        Keys are preset names (e.g. 'meas_cycle_strong').
    """
    presets_csv = Path(presets_csv)
    models: Dict[str, AsymmetricGaussianModel] = {}

    # Try to load the companion per-wafer summary.json for richer stats
    wafer_stats = _load_wafer_stats_from_summary_json(presets_csv.parent)

    with open(presets_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("preset_name", "").strip()
            if not name:
                continue

            # Try to get asymmetric CV% from per-wafer stats
            if name in wafer_stats and wafer_stats[name]["hrs_cv_pct"] is not None:
                hrs_cv = wafer_stats[name]["hrs_cv_pct"]
                lrs_cv = wafer_stats[name]["lrs_cv_pct"]
            else:
                # Fallback: use device_variation_pct_suggested for both
                # and apply a heuristic split (HRS ≈ 2× LRS from literature)
                sym_var = _safe_float(row.get("device_variation_pct_suggested", ""))
                if sym_var is None:
                    sym_var = _safe_float(row.get("device_variation", "")) or 10.0
                # Heuristic: HRS CV ≈ 1.8× LRS CV for RRAM (from Wang et al. 2020)
                hrs_cv = sym_var * 1.4
                lrs_cv = sym_var * 0.6

            model = AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])
            models[name] = model
            print(
                f"  [calibrate] {name}: HRS_CV={hrs_cv:.1f}%  LRS_CV={lrs_cv:.1f}%"
            )

    return models


def _load_wafer_stats_from_summary_json(
    run_dir: Path,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Extract per-preset HRS/LRS CV% from the companion summary.json."""
    import json

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {}

    with open(summary_path, encoding="utf-8") as f:
        data = json.load(f)

    # summary.json has a list of wafer entries under "cycle_files"
    cycle_files = data.get("cycle_files", [])
    # Group by state (cycle_strong / cycle_weak / cycle_typical)
    grouped: Dict[str, List[dict]] = {}
    for entry in cycle_files:
        state = entry.get("state", "unknown")
        # map e.g. "cycle_strong" -> "meas_cycle_strong"
        preset_name = f"meas_{state}" if not state.startswith("meas_") else state
        grouped.setdefault(preset_name, []).append(entry)

    result: Dict[str, Dict[str, Optional[float]]] = {}
    for preset_name, entries in grouped.items():
        hrs_cvs = [
            _safe_float(e.get("hrs_cv_pct"))
            for e in entries
            if _safe_float(e.get("hrs_cv_pct")) is not None
        ]
        lrs_cvs = [
            _safe_float(e.get("lrs_cv_pct"))
            for e in entries
            if _safe_float(e.get("lrs_cv_pct")) is not None
        ]
        result[preset_name] = {
            "hrs_cv_pct": float(np.median(hrs_cvs)) if hrs_cvs else None,
            "lrs_cv_pct": float(np.median(lrs_cvs)) if lrs_cvs else None,
        }

    return result


# ---------------------------------------------------------------------------
# 2. Raw path: from wafer cycle CSV
# ---------------------------------------------------------------------------

def calibrate_from_wafer_csv(
    wafer_csv_path: str | Path,
    max_rows: int = 200_000,
    hrs_curve: str = "teERS",
    lrs_curve: str = "bePGM",
    resistance_col: str = "R_cell",
) -> Tuple[AsymmetricGaussianModel, EmpiricalDeviceModel]:
    """Calibrate device models directly from a raw 2T1R cycle CSV file.

    The 2T1R cycle files have rows with ``Curve Name`` ∈ {``teERS``, ``bePGM``}
    representing HRS (after ERASE) and LRS (after PROGRAM) states respectively.

    Parameters
    ----------
    wafer_csv_path:
        Path to one wafer CSV, e.g. ``test_data/2T1R_cycle/wafer_xy16.csv``.
    max_rows:
        Maximum rows to read (files are ~1 M rows; 200k is enough for stats).
    hrs_curve, lrs_curve:
        ``Curve Name`` values that identify HRS and LRS rows.
    resistance_col:
        Column name containing the cell resistance (Ω).

    Returns
    -------
    (AsymmetricGaussianModel, EmpiricalDeviceModel)
        Both models calibrated from the same data.
    """
    hrs_values: List[float] = []
    lrs_values: List[float] = []

    with open(wafer_csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            if count >= max_rows:
                break
            r = _safe_float(row.get(resistance_col))
            if r is None or r <= 0:
                continue
            curve = row.get("Curve Name", "").strip()
            if curve == hrs_curve:
                hrs_values.append(r)
            elif curve == lrs_curve:
                lrs_values.append(r)
            count += 1

    if not hrs_values or not lrs_values:
        raise ValueError(
            f"No valid resistance data found in {wafer_csv_path}. "
            f"Check curve names: hrs='{hrs_curve}', lrs='{lrs_curve}'"
        )

    hrs_arr = np.array(hrs_values)
    lrs_arr = np.array(lrs_values)

    hrs_mean = float(np.mean(hrs_arr))
    lrs_mean = float(np.mean(lrs_arr))
    hrs_cv = float(np.std(hrs_arr) / hrs_mean * 100.0)
    lrs_cv = float(np.std(lrs_arr) / lrs_mean * 100.0)

    print(
        f"  [calibrate] {Path(wafer_csv_path).name}: "
        f"HRS mean={hrs_mean:.0f}Ω CV={hrs_cv:.1f}%  "
        f"LRS mean={lrs_mean:.0f}Ω CV={lrs_cv:.1f}%  "
        f"n_hrs={len(hrs_arr)} n_lrs={len(lrs_arr)}"
    )

    asymmetric_model = AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])
    empirical_model = EmpiricalDeviceModel(
        state_samples=[hrs_arr, lrs_arr],
        nominal_resistances=[hrs_mean, lrs_mean],
    )

    return asymmetric_model, empirical_model


# ---------------------------------------------------------------------------
# 3. Multi-wafer calibration
# ---------------------------------------------------------------------------

def calibrate_from_wafer_dir(
    wafer_dir: str | Path,
    pattern: str = "wafer_xy*.csv",
    max_rows_per_file: int = 100_000,
) -> Dict[str, AsymmetricGaussianModel]:
    """Calibrate one model per wafer file found in ``wafer_dir``.

    Useful for visualising wafer-to-wafer variation without going through
    the preset extraction pipeline.
    """
    wafer_dir = Path(wafer_dir)
    models: Dict[str, AsymmetricGaussianModel] = {}
    for csv_path in sorted(wafer_dir.glob(pattern)):
        try:
            asym, _ = calibrate_from_wafer_csv(csv_path, max_rows=max_rows_per_file)
            models[csv_path.stem] = asym
        except Exception as exc:
            print(f"  [calibrate] WARNING: skipping {csv_path.name}: {exc}")
    return models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None
