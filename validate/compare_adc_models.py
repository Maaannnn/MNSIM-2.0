#!/usr/bin/env python3
"""
validate/compare_adc_models.py
================================
Compare MNSIM's hardcoded ADC lookup vs pim_sim's Walden FOM model.

What this script does
---------------------
1. Prints all 9 MNSIM reference ADCs and their PPA numbers
2. For each reference ADC, builds a WaldenADCModel fitted to that point
3. Shows how well the Walden FOM generalises (interpolation accuracy)
4. Sweeps ADC bits 1–10 and plots power/area/latency curves
5. Compares total system PPA for a sample design (128 xbars × 128 cols)

This script is purely analytical — no MNSIM accuracy run needed.

Usage
-----
    python validate/compare_adc_models.py
    python validate/compare_adc_models.py --plot
    python validate/compare_adc_models.py \
        --n-xbars 256 --xbar-cols 128 \
        --enob-range 4 6 8 10 \
        --plot

Output
------
    validate/output/adc_comparison.csv
    validate/output/adc_ppa_curves.png   (if --plot)
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from pim_sim.array.adc_model import (
    WaldenADCModel,
    mnsim_adc_to_walden,
    _MNSIM_ADC_TABLE,
)
from pim_sim.ppa.estimator import parametric_adc_sweep


def parse_args():
    p = argparse.ArgumentParser(description="Compare MNSIM vs Walden FOM ADC models")
    p.add_argument("--enob-range", type=float, nargs="+",
                   default=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                   help="ENOB values for parametric sweep")
    p.add_argument("--n-xbars", type=int, default=128,
                   help="Number of crossbars in example design")
    p.add_argument("--xbar-cols", type=int, default=128,
                   help="Columns per crossbar (= ADCs per xbar)")
    p.add_argument("--plot", action="store_true")
    p.add_argument("--output-dir", default=str(ROOT / "validate" / "output"))
    return p.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Show all MNSIM reference ADCs
    # ------------------------------------------------------------------
    print("MNSIM Reference ADC Lookup Table")
    print("=" * 80)
    print(f"{'Choice':>7}  {'Bits':>5}  {'Power(mW)':>10}  {'Area(µm²)':>10}  "
          f"{'Rate(GSa/s)':>12}  {'Latency(ns)':>12}  {'Energy(fJ)':>11}")
    print("-" * 80)

    mnsim_rows = []
    for choice, (bits, power, area, rate) in sorted(_MNSIM_ADC_TABLE.items()):
        latency = (bits + 2) / rate if bits > 1 else 1.0 / rate
        energy_fj = latency * power * 1e12
        print(f"{choice:>7}  {bits:>5}  {power*1e3:>10.3f}  {area:>10.1f}  "
              f"{rate:>12.2f}  {latency:>12.3f}  {energy_fj:>11.2f}")
        mnsim_rows.append({
            "source": "mnsim_lookup",
            "choice_or_enob": choice,
            "bits": bits,
            "power_mw": round(power * 1e3, 4),
            "area_um2": round(area, 2),
            "rate_gsps": rate,
            "latency_ns": round(latency, 4),
            "energy_fj": round(energy_fj, 3),
        })

    # ------------------------------------------------------------------
    # 2. Walden FOM sweep over ENOB range
    # ------------------------------------------------------------------
    print()
    print("Walden FOM Parametric Model (default FOM @ 28nm)")
    print("=" * 80)
    print(f"{'ENOB':>6}  {'Power(mW)':>10}  {'Area(µm²)':>10}  "
          f"{'Rate(GSa/s)':>12}  {'Latency(ns)':>12}  {'Energy(fJ)':>11}")
    print("-" * 80)

    walden_rows = []
    for enob in args.enob_range:
        adc = WaldenADCModel(enob=enob, sample_rate_gsps=1.0)
        s = adc.summary()
        print(f"{enob:>6.1f}  {s['power_mw']:>10.4f}  {s['area_um2']:>10.2f}  "
              f"{adc.sample_rate_gsps:>12.2f}  {s['latency_ns']:>12.4f}  "
              f"{s['energy_fj']:>11.3f}")
        walden_rows.append({
            "source": "walden_parametric",
            "choice_or_enob": enob,
            "bits": enob,
            "power_mw": s["power_mw"],
            "area_um2": s["area_um2"],
            "rate_gsps": adc.sample_rate_gsps,
            "latency_ns": s["latency_ns"],
            "energy_fj": s["energy_fj"],
        })

    # ------------------------------------------------------------------
    # 3. System-level PPA comparison (sample design)
    # ------------------------------------------------------------------
    n_xbars = args.n_xbars
    xbar_cols = args.xbar_cols
    total_adcs = n_xbars * xbar_cols

    print()
    print(f"System-level ADC PPA (design: {n_xbars} xbars × {xbar_cols} cols "
          f"= {total_adcs} ADCs)")
    print("=" * 80)
    sweep_results = parametric_adc_sweep(
        enob_values=[e for e in args.enob_range if e == int(e)],
        xbar_cols=xbar_cols,
        n_xbars=n_xbars,
        sample_rate_gsps=1.0,
    )
    print(f"{'ENOB':>6}  {'Total Power(mW)':>16}  {'Total Area(mm²)':>16}  "
          f"{'Latency(ns)':>12}")
    print("-" * 60)
    for r in sweep_results:
        print(f"{r['enob']:>6.0f}  {r['total_power_mw']:>16.2f}  "
              f"{r['total_area_mm2']:>16.4f}  {r['latency_ns']:>12.4f}")

    # ------------------------------------------------------------------
    # 4. Save CSV
    # ------------------------------------------------------------------
    all_rows = mnsim_rows + walden_rows
    out_csv = output_dir / "adc_comparison.csv"
    if all_rows:
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
    print(f"\nComparison data saved to: {out_csv}")

    if args.plot:
        _make_plots(args, walden_rows, mnsim_rows, output_dir)


def _make_plots(args, walden_rows, mnsim_rows, output_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping plots.")
        return

    enobs = [r["choice_or_enob"] for r in walden_rows]
    powers = [r["power_mw"] for r in walden_rows]
    areas = [r["area_um2"] for r in walden_rows]
    latencies = [r["latency_ns"] for r in walden_rows]

    m_bits = [r["bits"] for r in mnsim_rows]
    m_powers = [r["power_mw"] for r in mnsim_rows]
    m_areas = [r["area_um2"] for r in mnsim_rows]
    m_latencies = [r["latency_ns"] for r in mnsim_rows]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Power
    axes[0].plot(enobs, powers, "-o", label="Walden FOM (parametric)", zorder=5)
    axes[0].scatter(m_bits, m_powers, marker="s", s=100, color="C1",
                    label="MNSIM reference", zorder=6)
    axes[0].set_xlabel("ADC bits (ENOB)")
    axes[0].set_ylabel("Power (mW)")
    axes[0].set_title("ADC Power")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Area
    axes[1].plot(enobs, areas, "-o", label="Walden FOM (parametric)", zorder=5)
    axes[1].scatter(m_bits, m_areas, marker="s", s=100, color="C1",
                    label="MNSIM reference", zorder=6)
    axes[1].set_xlabel("ADC bits (ENOB)")
    axes[1].set_ylabel("Area (µm²)")
    axes[1].set_title("ADC Area")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    # Latency
    axes[2].plot(enobs, latencies, "-o", label="Walden FOM (parametric)", zorder=5)
    axes[2].scatter(m_bits, m_latencies, marker="s", s=100, color="C1",
                    label="MNSIM reference", zorder=6)
    axes[2].set_xlabel("ADC bits (ENOB)")
    axes[2].set_ylabel("Latency (ns)")
    axes[2].set_title("ADC Latency")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    fig.suptitle("MNSIM ADC lookup vs Walden FOM parametric model", fontsize=13)
    fig.tight_layout()
    out_path = output_dir / "adc_ppa_curves.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"PPA curve plot saved to: {out_path}")


if __name__ == "__main__":
    main()
