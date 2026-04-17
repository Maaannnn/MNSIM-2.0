#!/usr/bin/env python3
"""
validate/calibrate_from_testdata.py
====================================
Validate the pim_sim device calibration pipeline against the real RRAM
wafer CSV files in test_data/2T1R_cycle/.

What this script does
---------------------
1. Reads each wafer_xy*.csv file and extracts HRS / LRS resistance distributions
2. Fits AsymmetricGaussianModel and EmpiricalDeviceModel per wafer
3. Plots the resistance histograms with Gaussian fits overlay
4. Reports wafer-to-wafer variation in HRS_CV% and LRS_CV%
5. Optionally reads measured_presets.csv and compares the preset CVs

Usage
-----
    # Quickstart (uses test_data from repo root)
    python validate/calibrate_from_testdata.py

    # Specify wafer directory and/or presets CSV
    python validate/calibrate_from_testdata.py \
        --wafer-dir test_data/2T1R_cycle \
        --presets artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv \
        --max-rows 50000 \
        --plot

Output
------
    validate/output/calibration_report.txt   — text summary
    validate/output/wafer_distributions.png  — histogram plots (if --plot)
    validate/output/wafer_cv_scatter.png     — HRS/LRS CV scatter (if --plot)
"""

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure pim_sim and MNSIM are importable from repo root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from pim_sim.device.calibrate import (
    calibrate_from_wafer_csv,
    calibrate_from_wafer_dir,
    calibrate_from_measured_presets_csv,
)


def parse_args():
    p = argparse.ArgumentParser(description="Calibrate pim_sim device models from wafer data")
    p.add_argument("--wafer-dir", default=str(ROOT / "test_data" / "2T1R_cycle"),
                   help="Directory containing wafer_xy*.csv files")
    p.add_argument("--presets", default=None,
                   help="Path to measured_presets.csv (optional)")
    p.add_argument("--max-rows", type=int, default=50_000,
                   help="Max rows to read per wafer CSV (default 50000)")
    p.add_argument("--plot", action="store_true",
                   help="Generate matplotlib plots (requires matplotlib)")
    p.add_argument("--output-dir", default=str(ROOT / "validate" / "output"),
                   help="Directory for output files")
    return p.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    wafer_dir = Path(args.wafer_dir)
    if not wafer_dir.exists():
        print(f"ERROR: wafer directory not found: {wafer_dir}")
        print("       Set --wafer-dir to point to the 2T1R_cycle CSV directory.")
        sys.exit(1)

    csv_files = sorted(wafer_dir.glob("wafer_xy*.csv"))
    if not csv_files:
        print(f"ERROR: no wafer_xy*.csv files found in {wafer_dir}")
        sys.exit(1)

    print(f"Found {len(csv_files)} wafer CSV files in {wafer_dir}")
    print(f"Max rows per file: {args.max_rows}")
    print("-" * 60)

    # ------------------------------------------------------------------
    # Calibrate per-wafer
    # ------------------------------------------------------------------
    wafer_results = []
    for csv_path in csv_files:
        try:
            asym_model, empirical_model = calibrate_from_wafer_csv(
                csv_path, max_rows=args.max_rows
            )
            wafer_results.append({
                "name": csv_path.stem,
                "hrs_cv": asym_model.state_cv_pct[0],
                "lrs_cv": asym_model.state_cv_pct[1],
                "model": asym_model,
            })
        except Exception as exc:
            print(f"  WARNING: {csv_path.name}: {exc}")

    if not wafer_results:
        print("No wafer data loaded. Exiting.")
        sys.exit(1)

    hrs_cvs = [r["hrs_cv"] for r in wafer_results]
    lrs_cvs = [r["lrs_cv"] for r in wafer_results]

    print()
    print("=" * 60)
    print("WAFER-TO-WAFER SUMMARY")
    print("=" * 60)
    print(f"  HRS CV% — mean={np.mean(hrs_cvs):.1f}%  "
          f"std={np.std(hrs_cvs):.1f}%  "
          f"range=[{min(hrs_cvs):.1f}%, {max(hrs_cvs):.1f}%]")
    print(f"  LRS CV% — mean={np.mean(lrs_cvs):.1f}%  "
          f"std={np.std(lrs_cvs):.1f}%  "
          f"range=[{min(lrs_cvs):.1f}%, {max(lrs_cvs):.1f}%]")
    ratio = np.mean(hrs_cvs) / np.mean(lrs_cvs) if np.mean(lrs_cvs) > 0 else float("nan")
    print(f"  HRS/LRS CV ratio (mean) = {ratio:.2f}x  (literature: ~1.8–2.5x)")

    # Write report
    report_path = output_dir / "calibration_report.txt"
    with open(report_path, "w") as f:
        f.write("pim_sim Calibration Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Wafer directory: {wafer_dir}\n")
        f.write(f"Files processed: {len(wafer_results)}/{len(csv_files)}\n\n")
        f.write("Per-wafer results:\n")
        for r in wafer_results:
            f.write(f"  {r['name']:20s}  HRS_CV={r['hrs_cv']:5.1f}%  LRS_CV={r['lrs_cv']:5.1f}%\n")
        f.write("\nAggregate statistics:\n")
        f.write(f"  HRS CV%: mean={np.mean(hrs_cvs):.2f}  std={np.std(hrs_cvs):.2f}\n")
        f.write(f"  LRS CV%: mean={np.mean(lrs_cvs):.2f}  std={np.std(lrs_cvs):.2f}\n")
        f.write(f"  HRS/LRS ratio: {ratio:.2f}x\n")
    print(f"\nReport written to: {report_path}")

    # ------------------------------------------------------------------
    # Compare against measured_presets.csv (if provided)
    # ------------------------------------------------------------------
    if args.presets:
        presets_path = Path(args.presets)
        if presets_path.exists():
            print()
            print("=" * 60)
            print("MEASURED PRESETS COMPARISON")
            print("=" * 60)
            preset_models = calibrate_from_measured_presets_csv(presets_path)
            for name, model in preset_models.items():
                print(f"  {name}: HRS_CV={model.state_cv_pct[0]:.1f}%  "
                      f"LRS_CV={model.state_cv_pct[1]:.1f}%")
        else:
            print(f"WARNING: presets file not found: {presets_path}")

    # ------------------------------------------------------------------
    # Plots (optional)
    # ------------------------------------------------------------------
    if args.plot:
        _make_plots(wafer_results, hrs_cvs, lrs_cvs, output_dir)


def _make_plots(wafer_results, hrs_cvs, lrs_cvs, output_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping plots.")
        return

    # CV scatter
    fig, ax = plt.subplots(figsize=(8, 6))
    names = [r["name"] for r in wafer_results]
    ax.scatter(hrs_cvs, lrs_cvs, s=80, zorder=5)
    for i, name in enumerate(names):
        ax.annotate(name, (hrs_cvs[i], lrs_cvs[i]), fontsize=7,
                    xytext=(3, 3), textcoords="offset points")
    ax.axvline(np.mean(hrs_cvs), color="C0", linestyle="--", alpha=0.6, label=f"mean HRS CV={np.mean(hrs_cvs):.1f}%")
    ax.axhline(np.mean(lrs_cvs), color="C1", linestyle="--", alpha=0.6, label=f"mean LRS CV={np.mean(lrs_cvs):.1f}%")
    ax.set_xlabel("HRS CV%")
    ax.set_ylabel("LRS CV%")
    ax.set_title("Wafer-to-wafer HRS/LRS CV variation")
    ax.legend()
    ax.grid(True, alpha=0.3)
    scatter_path = output_dir / "wafer_cv_scatter.png"
    fig.savefig(scatter_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Scatter plot saved to: {scatter_path}")

    # CV distributions
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].hist(hrs_cvs, bins=min(10, len(hrs_cvs)), color="C0", edgecolor="black", alpha=0.7)
    axes[0].axvline(np.mean(hrs_cvs), color="red", linestyle="--", label=f"mean={np.mean(hrs_cvs):.1f}%")
    axes[0].set_xlabel("HRS CV%")
    axes[0].set_ylabel("Wafer count")
    axes[0].set_title("HRS CV distribution")
    axes[0].legend()

    axes[1].hist(lrs_cvs, bins=min(10, len(lrs_cvs)), color="C1", edgecolor="black", alpha=0.7)
    axes[1].axvline(np.mean(lrs_cvs), color="red", linestyle="--", label=f"mean={np.mean(lrs_cvs):.1f}%")
    axes[1].set_xlabel("LRS CV%")
    axes[1].set_ylabel("Wafer count")
    axes[1].set_title("LRS CV distribution")
    axes[1].legend()

    fig.suptitle("pim_sim calibration: wafer-level HRS/LRS CV distributions")
    dist_path = output_dir / "wafer_distributions.png"
    fig.savefig(dist_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Distribution plot saved to: {dist_path}")


if __name__ == "__main__":
    main()
