#!/usr/bin/env python3
"""
validate/compare_accuracy_models.py
=====================================
Compare MNSIM baseline vs pim_sim accuracy under different device models.

Efficiency note
---------------
TrainTestInterface initialization (dataset load) takes ~3s but evaluation
takes ~140s per batch (CPU). This script loads the interface ONCE and reuses
it across all model/variation/trial combinations.

Usage
-----
    python validate/compare_accuracy_models.py \
        --sim-config SimConfig.ini \
        --weights cifar10_vgg8_params.pth \
        --variation 10 20 30 \
        --n-trials 3 \
        --max-batches 2

Output
------
    validate/output/accuracy_comparison.csv
    validate/output/accuracy_curves.png  (if --plot)
"""

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from pim_sim.device.model import SymmetricGaussianModel, AsymmetricGaussianModel
from pim_sim.device.calibrate import calibrate_from_wafer_csv
from pim_sim.accuracy.weight_inject import pim_sim_weight_inject


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-config", default=str(ROOT / "SimConfig.ini"))
    p.add_argument("--weights", default=str(ROOT / "cifar10_vgg8_params.pth"))
    p.add_argument("--nn-name", default="vgg8")
    p.add_argument("--dataset-module", default="MNSIM.Interface.cifar10")
    p.add_argument("--variation", type=float, nargs="+", default=[10.0, 20.0, 30.0])
    p.add_argument("--hrs-lrs-ratio", type=float, default=10.0,
                   help="HRS_CV / LRS_CV ratio from real wafer data (default 10)")
    p.add_argument("--n-trials", type=int, default=3)
    p.add_argument("--max-batches", type=int, default=2,
                   help="Eval batches per run (2 = ~1000 samples, ~5min per trial)")
    p.add_argument("--wafer-csv", default=None)
    p.add_argument("--plot", action="store_true")
    p.add_argument("--output-dir", default=str(ROOT / "validate" / "output"))
    return p.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for f in [args.sim_config, args.weights]:
        if not Path(f).exists():
            print(f"ERROR: not found: {f}")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Load interface ONCE
    # ------------------------------------------------------------------
    print("Loading TrainTestInterface (once)...")
    t0 = time.time()
    from MNSIM.Interface.interface import TrainTestInterface
    from MNSIM.Accuracy_Model.Weight_update import weight_update

    test_if = TrainTestInterface(
        network_module=args.nn_name,
        dataset_module=args.dataset_module,
        SimConfig_path=args.sim_config,
        weights_file=args.weights,
        device="cpu",
        max_eval_batches=args.max_batches,
    )
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # Baseline (no noise)
    bits_clean = test_if.get_net_bits()
    t1 = time.time()
    acc_clean = float(test_if.set_net_bits_evaluate(bits_clean, adc_action="SCALE"))
    print(f"  Baseline (no noise): {acc_clean:.4f}  ({time.time()-t1:.1f}s/eval)")

    # Optional empirical model
    empirical_model = None
    if args.wafer_csv and Path(args.wafer_csv).exists():
        print(f"Calibrating EmpiricalDeviceModel from {args.wafer_csv}...")
        _, empirical_model = calibrate_from_wafer_csv(args.wafer_csv, max_rows=100_000)

    # ------------------------------------------------------------------
    # Build model list for each variation level
    # ------------------------------------------------------------------
    results = []
    r = args.hrs_lrs_ratio  # HRS/LRS CV ratio from wafer data

    print(f"\nRunning {len(args.variation)} variation × "
          f"{args.n_trials} trials × models  (max_batches={args.max_batches})")
    print(f"HRS/LRS ratio = {r}x  (from real wafer: ~10×)")
    print("=" * 70)

    for var in args.variation:
        hrs_cv = var * np.sqrt(r)
        lrs_cv = var / np.sqrt(r)

        models_to_run = [
            # (name, model_or_None_for_mnsim)
            ("mnsim_sym",      None),
            (f"sym_hrs{var:.0f}_lrs{var:.0f}",  SymmetricGaussianModel(variation_pct=var)),
            (f"asym_hrs{hrs_cv:.0f}_lrs{lrs_cv:.0f}", AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])),
        ]
        if empirical_model is not None:
            models_to_run.append(("empirical", empirical_model))

        print(f"\nVariation={var}%  (asym: HRS_CV={hrs_cv:.1f}%  LRS_CV={lrs_cv:.1f}%)")

        for model_name, model in models_to_run:
            trial_accs = []
            for trial in range(args.n_trials):
                seed = int(var * 1000 + trial * 7)
                t0 = time.time()
                bits = test_if.get_net_bits()  # fresh copy each time

                if model is None:
                    bits_after = weight_update(
                        args.sim_config, bits, is_Variation=1, is_SAF=0
                    )
                else:
                    bits_after = pim_sim_weight_inject(
                        args.sim_config, bits,
                        is_Variation=1, is_SAF=0,
                        pim_sim_model=model,
                        rng_seed=seed,
                    )

                acc = float(test_if.set_net_bits_evaluate(bits_after, adc_action="SCALE"))
                elapsed = time.time() - t0
                trial_accs.append(acc)
                results.append([var, model_name, trial, acc, round(elapsed, 1)])
                print(f"  [{model_name:18s}] trial={trial}  acc={acc:.4f}  ({elapsed:.0f}s)")

            mean_acc = np.mean(trial_accs)
            drop = acc_clean - mean_acc
            print(f"  → mean={mean_acc:.4f}  drop={drop:+.4f} vs clean")

    # ------------------------------------------------------------------
    # Save CSV
    # ------------------------------------------------------------------
    out_csv = output_dir / "accuracy_comparison.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["variation_pct", "model", "trial", "accuracy", "elapsed_s"])
        writer.writerows(results)

    # Summary table
    print("\n" + "=" * 70)
    print(f"SUMMARY  (baseline clean acc = {acc_clean:.4f})")
    print(f"{'variation':>10}  {'model':>22}  {'mean_acc':>10}  {'drop':>8}  {'std':>7}")
    print("-" * 70)
    grouped = defaultdict(list)
    for var, mname, _, acc, _ in results:
        grouped[(var, mname)].append(acc)
    for (var, mname), accs in sorted(grouped.items()):
        mean_a = np.mean(accs)
        drop = acc_clean - mean_a
        print(f"{var:>10.0f}  {mname:>22}  {mean_a:>10.4f}  {drop:>+8.4f}  {np.std(accs):>7.4f}")

    print(f"\nResults saved to: {out_csv}")

    if args.plot:
        _make_plots(results, acc_clean, output_dir)


def _make_plots(results, baseline, output_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available.")
        return

    import re
    from collections import defaultdict

    def base_name(name):
        return re.sub(r"_\d+$", "", name)

    grouped = defaultdict(lambda: defaultdict(list))
    for var, mname, _, acc, _ in results:
        grouped[base_name(mname)][float(var)].append(acc)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axhline(baseline, color="gray", linestyle=":", label=f"clean baseline={baseline:.4f}")

    colors = {"mnsim_sym": "C0", "sym": "C1", "asym": "C2", "empirical": "C3"}
    for mname, var_dict in sorted(grouped.items()):
        vs = sorted(var_dict.keys())
        means = [np.mean(var_dict[v]) for v in vs]
        stds  = [np.std(var_dict[v]) for v in vs]
        color = colors.get(mname, "C4")
        ax.errorbar(vs, means, yerr=stds, marker="o", label=mname,
                    color=color, capsize=4, linewidth=2)

    ax.set_xlabel("Variation / CV% parameter")
    ax.set_ylabel("Test Accuracy")
    ax.set_title("MNSIM symmetric vs pim_sim asymmetric device model\n"
                 f"(HRS/LRS ratio={10}×, VGG8/CIFAR-10)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out = output_dir / "accuracy_curves.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved: {out}")


if __name__ == "__main__":
    main()
