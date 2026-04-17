#!/usr/bin/env python3
"""
validate/sweep_xbar_sensitivity.py
====================================
Demonstrate IR-drop sensitivity vs crossbar size.

This script does NOT require MNSIM accuracy evaluation — it shows the
*theoretical* IR-drop effect analytically and via synthetic weight matrices,
which is fast (< 1 second).

What this script shows
----------------------
1. IR-drop fraction α = N × R_wire / R_device_avg for different xbar sizes
2. Row-scale factor profiles for 64×64, 128×128, 256×256, 512×512
3. Effective accuracy loss upper bound per array size
4. Synthetic weight-matrix distortion: compare row-sum before/after IR-drop

Usage
-----
    python validate/sweep_xbar_sensitivity.py
    python validate/sweep_xbar_sensitivity.py --plot --wire-res 1.0
    python validate/sweep_xbar_sensitivity.py \
        --xbar-sizes 64 128 256 512 \
        --wire-res 0.5 1.0 2.0 \
        --device-res 5000

Output
------
    validate/output/ir_drop_sensitivity.csv
    validate/output/ir_drop_profiles.png   (if --plot)
    validate/output/ir_drop_heatmap.png    (if --plot)
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from pim_sim.array.ir_drop import IRDropModel


def parse_args():
    p = argparse.ArgumentParser(description="IR-drop sensitivity vs xbar size")
    p.add_argument("--xbar-sizes", type=int, nargs="+",
                   default=[64, 128, 256, 512],
                   help="Crossbar row counts to sweep")
    p.add_argument("--wire-res", type=float, nargs="+",
                   default=[0.5, 1.0, 2.0],
                   help="Wire resistance per cell pitch (Ω)")
    p.add_argument("--device-res", type=float, default=5000.0,
                   help="Average device resistance (Ω)")
    p.add_argument("--plot", action="store_true")
    p.add_argument("--output-dir", default=str(ROOT / "validate" / "output"))
    return p.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("IR-drop sensitivity analysis")
    print("=" * 60)
    print(f"Device resistance avg: {args.device_res:.0f} Ω")
    print()

    rows_data = []
    header = ["xbar_rows", "wire_res_ohm", "ir_drop_alpha", "mean_loss_pct",
              "bottom_row_scale", "top_row_scale"]

    print(f"{'xbar':>6}  {'R_wire':>8}  {'alpha':>8}  {'mean_loss':>12}  {'bottom_scale':>14}")
    print("-" * 60)

    for n_rows in args.xbar_sizes:
        for r_wire in args.wire_res:
            model = IRDropModel(
                xbar_rows=n_rows,
                wire_resistance_per_cell_ohm=r_wire,
                device_resistance_avg_ohm=args.device_res,
            )
            alpha = model.ir_drop_fraction()
            loss = model.mean_accuracy_loss_pct()
            scales = model.row_scale_factors()
            bottom_scale = float(scales[-1])
            top_scale = float(scales[0])

            print(f"{n_rows:>6}  {r_wire:>6.1f}Ω  {alpha:>8.4f}  "
                  f"{loss:>10.2f}%  {bottom_scale:>14.4f}")

            rows_data.append([n_rows, r_wire, round(alpha, 6), round(loss, 4),
                               round(bottom_scale, 6), round(top_scale, 6)])

    # Save CSV
    out_csv = output_dir / "ir_drop_sensitivity.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows_data)
    print(f"\nResults saved to: {out_csv}")

    # Synthetic weight-matrix distortion test
    print()
    print("Synthetic weight distortion (128×128, R_wire=0.5Ω, R_dev=5000Ω)")
    print("-" * 60)
    model = IRDropModel(xbar_rows=128, wire_resistance_per_cell_ohm=0.5, device_resistance_avg_ohm=5000.0)
    # Uniform weight matrix (all 1s)
    W = np.ones((128, 128))
    W_dropped = model.apply_to_weight_matrix(W)
    row_sums_ideal = W.sum(axis=1)
    row_sums_dropped = W_dropped.sum(axis=1)
    print(f"  Top row (i=0):    ideal={row_sums_ideal[0]:.1f}  dropped={row_sums_dropped[0]:.1f}  "
          f"error={abs(row_sums_dropped[0]-row_sums_ideal[0])/row_sums_ideal[0]*100:.2f}%")
    print(f"  Middle row (i=63): ideal={row_sums_ideal[63]:.1f}  dropped={row_sums_dropped[63]:.1f}  "
          f"error={abs(row_sums_dropped[63]-row_sums_ideal[63])/row_sums_ideal[63]*100:.2f}%")
    print(f"  Bottom row (i=127): ideal={row_sums_ideal[-1]:.1f}  dropped={row_sums_dropped[-1]:.1f}  "
          f"error={abs(row_sums_dropped[-1]-row_sums_ideal[-1])/row_sums_ideal[-1]*100:.2f}%")
    mean_error_pct = np.mean(np.abs(row_sums_dropped - row_sums_ideal) / row_sums_ideal) * 100
    print(f"  Mean row-sum error: {mean_error_pct:.2f}%")

    if args.plot:
        _make_plots(args, output_dir, rows_data, header)


def _make_plots(args, output_dir, rows_data, header):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping plots.")
        return

    # 1. Row scale profiles for different xbar sizes (fixed R_wire = middle value)
    r_wire_mid = sorted(args.wire_res)[len(args.wire_res) // 2]
    fig, ax = plt.subplots(figsize=(10, 6))
    for n_rows in args.xbar_sizes:
        model = IRDropModel(
            xbar_rows=n_rows,
            wire_resistance_per_cell_ohm=r_wire_mid,
            device_resistance_avg_ohm=args.device_res,
        )
        scales = model.row_scale_factors()
        alpha = model.ir_drop_fraction()
        ax.plot(np.linspace(0, 1, n_rows), scales,
                label=f"N={n_rows}, α={alpha:.3f}")
    ax.set_xlabel("Normalised row position (0=top, 1=bottom)")
    ax.set_ylabel("Row voltage scale factor")
    ax.set_title(f"IR-drop row scale profiles\n(R_wire={r_wire_mid}Ω, R_dev={args.device_res:.0f}Ω)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.05)
    out_path = output_dir / "ir_drop_profiles.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Profile plot saved to: {out_path}")

    # 2. Heatmap: mean_loss_pct vs (xbar_size, wire_res)
    import pandas as pd
    df = pd.DataFrame(rows_data, columns=header)
    pivot = df.pivot(index="xbar_rows", columns="wire_res_ohm", values="mean_loss_pct")

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd",
                   vmin=0, vmax=pivot.values.max())
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{c:.1f}Ω" for c in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(r) for r in pivot.index])
    ax.set_xlabel("Wire resistance per cell (Ω)")
    ax.set_ylabel("Crossbar rows")
    ax.set_title("IR-drop mean accuracy loss upper bound (%)")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            ax.text(j, i, f"{pivot.values[i, j]:.2f}%",
                    ha="center", va="center", fontsize=9)
    plt.colorbar(im, ax=ax, label="Mean accuracy loss (%)")
    out_path = output_dir / "ir_drop_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Heatmap saved to: {out_path}")


if __name__ == "__main__":
    main()
