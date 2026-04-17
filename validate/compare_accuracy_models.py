#!/usr/bin/env python3
"""
validate/compare_accuracy_models.py
=====================================
Compare MNSIM baseline vs pim_sim accuracy under different device models.

What this script does
---------------------
1. Loads a SimConfig.ini and network weights
2. Runs accuracy evaluation 3 ways:
   a. MNSIM original weight_update (symmetric Gaussian, variation=X%)
   b. pim_sim AsymmetricGaussianModel (HRS_CV != LRS_CV, same mean noise)
   c. pim_sim EmpiricalDeviceModel (from measured wafer data, if available)
3. Reports accuracy for each model and variation level
4. Optionally sweeps variation% to generate accuracy-vs-noise curves

Usage
-----
    # Basic comparison (symmetric vs asymmetric)
    python validate/compare_accuracy_models.py \
        --sim-config SimConfig.ini \
        --weights cifar10_vgg8_params.pth \
        --nn-name vgg8 \
        --variation 10 20 30 \
        --n-trials 3

    # Include wafer CSV calibration
    python validate/compare_accuracy_models.py \
        --sim-config SimConfig.ini \
        --weights cifar10_vgg8_params.pth \
        --nn-name vgg8 \
        --wafer-csv test_data/2T1R_cycle/wafer_xy16.csv \
        --plot

Output
------
    validate/output/accuracy_comparison.csv   — per-trial accuracy results
    validate/output/accuracy_curves.png       — accuracy vs variation (if --plot)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from pim_sim.device.model import (
    SymmetricGaussianModel,
    AsymmetricGaussianModel,
    EmpiricalDeviceModel,
)
from pim_sim.device.calibrate import calibrate_from_wafer_csv
from pim_sim.accuracy.weight_inject import pim_sim_weight_inject


def parse_args():
    p = argparse.ArgumentParser(description="Compare MNSIM vs pim_sim accuracy models")
    p.add_argument("--sim-config", default=str(ROOT / "SimConfig.ini"),
                   help="Path to SimConfig.ini")
    p.add_argument("--weights", default=str(ROOT / "cifar10_vgg8_params.pth"),
                   help="Path to network weights .pth file")
    p.add_argument("--nn-name", default="vgg8",
                   help="Network name (e.g. vgg8, resnet18)")
    p.add_argument("--dataset-module", default="MNSIM.Interface.cifar10")
    p.add_argument("--variation", type=float, nargs="+", default=[10.0, 20.0, 30.0],
                   help="Symmetric variation%% values to test")
    p.add_argument("--hrs-lrs-ratio", type=float, default=1.8,
                   help="HRS_CV / LRS_CV ratio for asymmetric model (default 1.8)")
    p.add_argument("--n-trials", type=int, default=3,
                   help="Number of random trials per condition")
    p.add_argument("--max-batches", type=int, default=5,
                   help="Max eval batches per accuracy run (5 = fast)")
    p.add_argument("--wafer-csv", default=None,
                   help="Wafer CSV for EmpiricalDeviceModel (optional)")
    p.add_argument("--plot", action="store_true")
    p.add_argument("--output-dir", default=str(ROOT / "validate" / "output"))
    return p.parse_args()


def run_accuracy(sim_config_path, weights_path, nn_name, dataset_module,
                 model, max_batches, seed=None):
    """Run accuracy evaluation with given device model."""
    from MNSIM.Interface.interface import TrainTestInterface

    test_if = TrainTestInterface(
        network_module=nn_name,
        dataset_module=dataset_module,
        SimConfig_path=sim_config_path,
        weights_file=weights_path,
        device="cpu",
        max_eval_batches=max_batches,
    )
    bits = test_if.get_net_bits()

    if model is None:
        # MNSIM baseline
        from MNSIM.Accuracy_Model.Weight_update import weight_update
        bits_after = weight_update(sim_config_path, bits, is_Variation=1, is_SAF=0)
    else:
        bits_after = pim_sim_weight_inject(
            sim_config_path, bits,
            is_Variation=1, is_SAF=0,
            pim_sim_model=model,
            rng_seed=seed,
        )

    acc = float(test_if.set_net_bits_evaluate(bits_after, adc_action="SCALE"))
    return acc


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sim_config = args.sim_config
    weights = args.weights
    nn_name = args.nn_name

    if not Path(sim_config).exists():
        print(f"ERROR: SimConfig.ini not found at {sim_config}")
        print("       Set --sim-config to the correct path.")
        sys.exit(1)
    if not Path(weights).exists():
        print(f"ERROR: weights file not found at {weights}")
        sys.exit(1)

    # Build EmpiricalDeviceModel if wafer CSV provided
    empirical_model = None
    if args.wafer_csv and Path(args.wafer_csv).exists():
        print(f"Calibrating EmpiricalDeviceModel from {args.wafer_csv}...")
        _, empirical_model = calibrate_from_wafer_csv(args.wafer_csv, max_rows=100_000)

    results = []
    header = ["variation_pct", "model", "trial", "accuracy", "elapsed_s"]

    print(f"\nRunning accuracy comparison (n_trials={args.n_trials}, "
          f"max_batches={args.max_batches})")
    print("=" * 70)

    for var in args.variation:
        # 1. MNSIM baseline (symmetric)
        # We temporarily patch SimConfig variation — read and warn
        print(f"\nVariation = {var}%")
        print(f"  NOTE: MNSIM model reads Device_Variation from SimConfig.ini")
        print(f"  The --variation flag controls the pim_sim models only.")
        print(f"  For a fair comparison, set Device_Variation={var} in SimConfig.ini")

        # 2. Symmetric model (pim_sim)
        sym_model = SymmetricGaussianModel(variation_pct=var)

        # 3. Asymmetric model: split var into HRS/LRS using given ratio
        r = args.hrs_lrs_ratio
        # HRS_CV * 1/(1+r) + LRS_CV * r/(1+r) = var  — weighted mean
        # simpler: HRS_CV = var * r, LRS_CV = var / r (preserves geometric mean)
        hrs_cv = var * np.sqrt(r)
        lrs_cv = var / np.sqrt(r)
        asym_model = AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])

        models = [
            ("mnsim_original", None),
            (f"sym_gaussian_{var:.0f}pct", sym_model),
            (f"asym_gaussian_{var:.0f}pct", asym_model),
        ]
        if empirical_model is not None:
            models.append(("empirical_wafer", empirical_model))

        for model_name, model in models:
            for trial in range(args.n_trials):
                seed = int(var * 1000 + trial * 7)
                t0 = time.time()
                try:
                    acc = run_accuracy(
                        sim_config, weights, nn_name, args.dataset_module,
                        model, args.max_batches, seed=seed,
                    )
                    elapsed = time.time() - t0
                    print(f"  [{model_name}] trial={trial}  acc={acc:.4f}  ({elapsed:.1f}s)")
                    results.append([var, model_name, trial, acc, round(elapsed, 2)])
                except Exception as exc:
                    print(f"  [{model_name}] trial={trial}  ERROR: {exc}")
                    results.append([var, model_name, trial, None, None])

    # Save CSV
    out_csv = output_dir / "accuracy_comparison.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(results)
    print(f"\nResults saved to: {out_csv}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY (mean accuracy per condition)")
    print("=" * 70)
    from collections import defaultdict
    grouped = defaultdict(list)
    for row in results:
        var, model_name, trial, acc, elapsed = row
        if acc is not None:
            grouped[(var, model_name)].append(acc)
    for (var, model_name), accs in sorted(grouped.items()):
        print(f"  var={var:5.1f}%  {model_name:35s}  "
              f"mean={np.mean(accs):.4f}  std={np.std(accs):.4f}")

    if args.plot:
        _make_plots(results, output_dir)


def _make_plots(results, output_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping plots.")
        return

    from collections import defaultdict
    import re

    # Group by model (strip variation suffix from model name)
    def base_name(name):
        return re.sub(r"_\d+pct$", "", name)

    grouped = defaultdict(lambda: defaultdict(list))
    for row in results:
        var, model_name, trial, acc, elapsed = row
        if acc is not None:
            grouped[base_name(model_name)][var].append(acc)

    fig, ax = plt.subplots(figsize=(10, 6))
    for model_name, var_dict in sorted(grouped.items()):
        vars_sorted = sorted(var_dict.keys())
        means = [np.mean(var_dict[v]) for v in vars_sorted]
        stds = [np.std(var_dict[v]) for v in vars_sorted]
        ax.errorbar(vars_sorted, means, yerr=stds, marker="o", label=model_name, capsize=4)

    ax.set_xlabel("Variation / CV%")
    ax.set_ylabel("Test Accuracy")
    ax.set_title("Accuracy vs Device Variation: MNSIM vs pim_sim models")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out_path = output_dir / "accuracy_curves.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to: {out_path}")


if __name__ == "__main__":
    main()
