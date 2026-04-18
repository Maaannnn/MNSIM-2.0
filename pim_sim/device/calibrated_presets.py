"""
pim_sim.device.calibrated_presets
===================================
Hard-coded calibrated device model presets derived from real RRAM wafer data.

Source
------
15 wafers (wafer_xy1–25) from test_data/2T1R_cycle/,
100k rows per wafer, IQR-robust calibration (factor=10).
Calibrated 2026-04-18.

Key finding
-----------
HRS and LRS variation are HIGHLY asymmetric in this RRAM process:
  HRS CV ≈ 31.5% (range 27.7–39.3%)
  LRS CV ≈  3.1% (range  1.4– 8.2%)
  Ratio ≈ 10×  (literature typically assumes 1.8–2.5×)

This means MNSIM's symmetric model SEVERELY overestimates LRS noise
and moderately underestimates HRS noise.

Usage
-----
    from pim_sim.device.calibrated_presets import PRESETS, get_preset

    model = get_preset("strong")   # HRS_CV=30.3%, LRS_CV=2.8%
    model = get_preset("typical_robust")  # HRS_CV=31.5%, LRS_CV=3.1%
    model = get_preset("weak")     # HRS_CV=31.7%, LRS_CV=18.9%

    # Or use dict directly
    for name, m in PRESETS.items():
        print(name, m.state_cv_pct)
"""

from __future__ import annotations
from typing import Dict

from pim_sim.device.model import AsymmetricGaussianModel


# ---------------------------------------------------------------------------
# Per-wafer calibrated models (robust IQR, 100k rows each)
# ---------------------------------------------------------------------------

WAFER_MODELS: Dict[str, AsymmetricGaussianModel] = {
    "wafer_xy1":  AsymmetricGaussianModel(state_cv_pct=[29.2, 1.4]),
    "wafer_xy3":  AsymmetricGaussianModel(state_cv_pct=[32.5, 1.5]),
    "wafer_xy7":  AsymmetricGaussianModel(state_cv_pct=[31.4, 17.6]),  # SAF-affected
    "wafer_xy12": AsymmetricGaussianModel(state_cv_pct=[35.0, 1.6]),
    "wafer_xy15": AsymmetricGaussianModel(state_cv_pct=[39.1, 2.1]),
    "wafer_xy16": AsymmetricGaussianModel(state_cv_pct=[28.3, 2.8]),
    "wafer_xy17": AsymmetricGaussianModel(state_cv_pct=[27.7, 1.7]),
    "wafer_xy18": AsymmetricGaussianModel(state_cv_pct=[30.4, 2.4]),
    "wafer_xy19": AsymmetricGaussianModel(state_cv_pct=[29.5, 1.6]),
    "wafer_xy20": AsymmetricGaussianModel(state_cv_pct=[30.6, 1.5]),
    "wafer_xy21": AsymmetricGaussianModel(state_cv_pct=[28.3, 2.2]),
    "wafer_xy22": AsymmetricGaussianModel(state_cv_pct=[31.4, 1.9]),
    "wafer_xy23": AsymmetricGaussianModel(state_cv_pct=[30.8, 2.0]),
    "wafer_xy24": AsymmetricGaussianModel(state_cv_pct=[39.3, 4.2]),  # defective outliers removed
    "wafer_xy25": AsymmetricGaussianModel(state_cv_pct=[29.0, 1.9]),
}

# ---------------------------------------------------------------------------
# Named scenario presets
# ---------------------------------------------------------------------------

PRESETS: Dict[str, AsymmetricGaussianModel] = {
    # From measured_presets.csv (cross-wafer cluster extraction pipeline)
    "strong":  AsymmetricGaussianModel(state_cv_pct=[30.3,  2.8]),  # meas_cycle_strong
    "weak":    AsymmetricGaussianModel(state_cv_pct=[31.7, 18.9]),  # meas_cycle_weak

    # Derived from robust per-wafer calibration (mean of 13 healthy wafers)
    # Use this instead of meas_cycle_typical which has anomalous values
    "typical_robust": AsymmetricGaussianModel(state_cv_pct=[31.5, 3.1]),

    # Worst-case (p95 of healthy wafers)
    "worst_case": AsymmetricGaussianModel(state_cv_pct=[39.1, 8.2]),

    # MNSIM equivalent (for comparison baseline)
    # MNSIM Device_Variation=1 from SimConfig.ini → symmetric 1%
    "mnsim_default": AsymmetricGaussianModel(state_cv_pct=[1.0, 1.0]),
}


def get_preset(name: str) -> AsymmetricGaussianModel:
    """Return a calibrated preset by name.

    Available names: strong, weak, typical_robust, worst_case, mnsim_default,
    and all wafer_xy* keys.
    """
    all_models = {**PRESETS, **WAFER_MODELS}
    if name not in all_models:
        raise KeyError(
            f"Unknown preset '{name}'. Available: {sorted(all_models.keys())}"
        )
    return all_models[name]


def list_presets() -> None:
    """Print all available presets with their CV values."""
    print("Named presets:")
    for name, m in PRESETS.items():
        print(f"  {name:20s}  HRS_CV={m.state_cv_pct[0]:.1f}%  LRS_CV={m.state_cv_pct[1]:.1f}%")
    print("Per-wafer models:")
    for name, m in WAFER_MODELS.items():
        print(f"  {name:20s}  HRS_CV={m.state_cv_pct[0]:.1f}%  LRS_CV={m.state_cv_pct[1]:.1f}%")


if __name__ == "__main__":
    list_presets()
