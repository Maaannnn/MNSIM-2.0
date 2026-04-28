"""
Walden ADC FoM validation against Murmann ADC Performance Survey.

Purpose
-------
pim_sim.array.adc_model.WaldenADCModel uses two constants fitted to
MNSIM's 9-entry 28 nm reference table:
    FoM_W = 20 fJ/conv-step (energy FoM)
    FoM_A = 8   µm² per (2^ENOB / GSa/s)

This script tests whether those defaults generalise to silicon by
comparing them to Murmann's 770+ ISSCC + VLSI ADC entries (1997-2026).
We report:
  - Silicon FoM_W / FoM_A distribution (median, p25, p75).
  - pim_sim predicted power vs silicon measured power (R², MAPE).
  - pim_sim predicted area vs silicon measured area (R², MAPE).
  - Per-technology-node breakdown.

Data source:
    artifacts/external/murmann_adc_survey/xls/ADCsurvey_rev20260314.xlsx
    (Bernhard Murmann, "ADC Performance Survey", CC BY 4.0)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pim_sim.array.adc_model import WaldenADCModel  # noqa: E402


SURVEY_XLSX = (
    REPO_ROOT
    / "artifacts/external/murmann_adc_survey/xls/ADCsurvey_rev20260314.xlsx"
)
OUTPUT_DIR = REPO_ROOT / "validate/output/walden_murmann"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_survey() -> pd.DataFrame:
    """Load ISSCC + VLSI sheets, concatenate, filter to Nyquist ADCs."""
    frames = []
    for sheet in ("ISSCC", "VLSI"):
        df = pd.read_excel(SURVEY_XLSX, sheet_name=sheet, header=0)
        df["VENUE"] = sheet
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    # Nyquist ADCs only (exclude oversampled / bandpass)
    df = df[df["TYPE"] == "NQ"].copy()
    return df


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Derive ENOB, silicon FoM_A, drop rows with missing critical fields."""
    df["P_W"] = _to_numeric(df["P [W]"])
    df["FS_HZ"] = _to_numeric(df["fsnyq [Hz]"])
    df["AREA_MM2"] = _to_numeric(df["AREA [mm^2]"])
    df["SNDR_DB"] = _to_numeric(df["SNDR_plot [dB]"])
    df["FOMW_HF_FJ"] = _to_numeric(df["FOMW_hf [fJ/conv-step]"])
    df["ENOB"] = (df["SNDR_DB"] - 1.76) / 6.02

    required = ["P_W", "FS_HZ", "SNDR_DB", "ENOB"]
    df = df.dropna(subset=required)
    df = df[(df["P_W"] > 0) & (df["FS_HZ"] > 0) & (df["ENOB"] > 0)]

    # Silicon Walden FoM from raw P / fs / ENOB (for cross-check with survey column)
    df["FOMW_DERIVED_FJ"] = (
        df["P_W"] / (df["FS_HZ"] * (2.0 ** df["ENOB"]))
    ) * 1e15  # → fJ/conv-step

    # Silicon area FoM (µm² per 2^ENOB / GSa/s)
    area_mask = df["AREA_MM2"] > 0
    df.loc[area_mask, "FOMA_DERIVED_UM2"] = (
        df.loc[area_mask, "AREA_MM2"] * 1e6  # mm² → µm²
        / ((2.0 ** df.loc[area_mask, "ENOB"]) / (df.loc[area_mask, "FS_HZ"] / 1e9))
    )
    return df


def pim_sim_predict(df: pd.DataFrame) -> pd.DataFrame:
    """Predict power/area for each survey entry using pim_sim's Walden model."""
    preds_p = []
    preds_a = []
    for enob, fs_hz in zip(df["ENOB"], df["FS_HZ"]):
        model = WaldenADCModel(enob=float(enob), sample_rate_gsps=float(fs_hz) / 1e9)
        preds_p.append(model.power_w())
        preds_a.append(model.area_um2())
    df = df.copy()
    df["P_W_PRED"] = preds_p
    df["AREA_UM2_PRED"] = preds_a
    return df


def metrics(measured: np.ndarray, predicted: np.ndarray) -> dict:
    """R², MAPE, bias ratio between measured and predicted (in log space)."""
    # Work in log10 space — ADC P & area span 6+ decades; linear fit dominated by outliers.
    log_m = np.log10(measured)
    log_p = np.log10(predicted)
    ss_res = np.sum((log_m - log_p) ** 2)
    ss_tot = np.sum((log_m - log_m.mean()) ** 2)
    r2_log = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    mape = np.mean(np.abs(predicted - measured) / measured) * 100.0
    median_ratio = float(np.median(predicted / measured))
    return {
        "n": int(len(measured)),
        "r2_log10": float(r2_log),
        "mape_pct": float(mape),
        "median_pred_over_meas": median_ratio,
    }


def distribution(values: np.ndarray) -> dict:
    v = values[np.isfinite(values) & (values > 0)]
    return {
        "n": int(len(v)),
        "median": float(np.median(v)),
        "p25": float(np.percentile(v, 25)),
        "p75": float(np.percentile(v, 75)),
        "geomean": float(np.exp(np.mean(np.log(v)))) if len(v) > 0 else float("nan"),
    }


def main() -> None:
    print(f"Loading survey from {SURVEY_XLSX.name}")
    df = load_survey()
    df = prepare(df)
    print(f"  Nyquist ADCs with complete P/fs/SNDR: {len(df)}")

    df = pim_sim_predict(df)

    # ---- Silicon FoM distributions ----
    fomw = df["FOMW_DERIVED_FJ"].to_numpy()
    foma = df["FOMA_DERIVED_UM2"].dropna().to_numpy()

    print("\nSilicon FoM_W [fJ/conv-step]:")
    for k, v in distribution(fomw).items():
        print(f"  {k:>8}: {v}")
    print("pim_sim default FoM_W: 20.0 fJ")

    print("\nSilicon FoM_A [µm² per 2^ENOB / GSa/s]:")
    for k, v in distribution(foma).items():
        print(f"  {k:>8}: {v}")
    print("pim_sim default FoM_A: 8.0 µm²")

    # ---- pim_sim prediction vs silicon ----
    print("\npim_sim Walden POWER prediction vs silicon:")
    p_metrics = metrics(df["P_W"].to_numpy(), df["P_W_PRED"].to_numpy())
    for k, v in p_metrics.items():
        print(f"  {k:>22}: {v}")

    area_df = df.dropna(subset=["AREA_MM2"])
    area_df = area_df[area_df["AREA_MM2"] > 0]
    area_measured_um2 = area_df["AREA_MM2"].to_numpy() * 1e6
    print("\npim_sim Walden AREA prediction vs silicon:")
    a_metrics = metrics(area_measured_um2, area_df["AREA_UM2_PRED"].to_numpy())
    for k, v in a_metrics.items():
        print(f"  {k:>22}: {v}")

    # ---- Per-year breakdown (groups of 5) ----
    print("\nFoM_W median by year bucket (silicon):")
    df["YEAR_BUCKET"] = (_to_numeric(df["YEAR"]) // 5 * 5).astype("Int64")
    year_table = (
        df.dropna(subset=["YEAR_BUCKET"])
        .groupby("YEAR_BUCKET")["FOMW_DERIVED_FJ"]
        .agg(["count", "median"])
        .reset_index()
    )
    print(year_table.to_string(index=False))

    # ---- Preset library: (architecture, era) → (FoM_W, FoM_A) ----
    print("\nPreset-library candidates (architecture x era, N>=8):")
    df["ERA"] = np.where(_to_numeric(df["YEAR"]) >= 2015, "modern", "legacy")
    preset_rows = []
    for (arch, era), group in df.groupby(["ARCHITECTURE", "ERA"]):
        if len(group) < 8:
            continue
        fomw_vals = group["FOMW_DERIVED_FJ"].dropna().to_numpy()
        foma_vals = group["FOMA_DERIVED_UM2"].dropna().to_numpy()
        if len(fomw_vals) < 8 or len(foma_vals) < 8:
            continue
        preset_rows.append({
            "architecture": arch,
            "era": era,
            "n_power": int(len(fomw_vals)),
            "n_area": int(len(foma_vals)),
            "fomw_fj_median": float(np.median(fomw_vals)),
            "fomw_fj_p25": float(np.percentile(fomw_vals, 25)),
            "fomw_fj_p75": float(np.percentile(fomw_vals, 75)),
            "foma_um2_median": float(np.median(foma_vals)),
            "foma_um2_p25": float(np.percentile(foma_vals, 25)),
            "foma_um2_p75": float(np.percentile(foma_vals, 75)),
        })
    preset_df = pd.DataFrame(preset_rows).sort_values(["era", "fomw_fj_median"])
    print(preset_df.to_string(index=False))
    preset_csv = OUTPUT_DIR / "adc_preset_library_seed.csv"
    preset_df.to_csv(preset_csv, index=False)
    print(f"Wrote: {preset_csv}")

    # ---- Write outputs ----
    per_entry_cols = [
        "YEAR", "ID", "ARCHITECTURE", "TECHNOLOGY", "VENUE",
        "ENOB", "FS_HZ", "P_W", "P_W_PRED",
        "AREA_MM2", "AREA_UM2_PRED",
        "FOMW_DERIVED_FJ", "FOMA_DERIVED_UM2",
    ]
    out_csv = OUTPUT_DIR / "walden_vs_murmann_per_entry.csv"
    df[per_entry_cols].to_csv(out_csv, index=False)

    summary = {
        "n_entries": len(df),
        "silicon_fomw_fj": distribution(fomw),
        "silicon_foma_um2": distribution(foma),
        "pim_sim_vs_silicon_power": p_metrics,
        "pim_sim_vs_silicon_area": a_metrics,
        "pim_sim_defaults": {"fom_walden_fj": 20.0, "fom_area_um2": 8.0},
        "pim_sim_default_offsets": {
            "fomw_default_over_silicon_median": 20.0 / distribution(fomw)["median"],
            "foma_default_over_silicon_median": 8.0 / distribution(foma)["median"],
        },
    }
    import json
    out_json = OUTPUT_DIR / "walden_vs_murmann_summary.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote: {out_csv}")
    print(f"Wrote: {out_json}")


if __name__ == "__main__":
    main()
