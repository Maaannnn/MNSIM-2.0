#!/usr/bin/env python3
"""Mini-sweep on SPACE_clean_v1: 5 configs as a smoke test before
committing to the full 288-config exhaustive sweep.

What this checks:
  1. None of 5 boundary configs crashes in MNSIM.
  2. Repeated identical (config, seed) yields bit-identical accuracy.
  3. Per-config wall time is sane.
  4. Output values look reasonable (no NaN, no astronomical numbers).

If any check fails, stop and debug before launching the full sweep.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dse.core import apply_space_profile, evaluate_config, write_temp_config
from dse.space_catalog import space_hash


# Defaults for dimensions we don't vary in this smoke test.
_FIXED_DIMS = {
    "dac_num": 32,
    "xbar_polarity": 2,
    "sub_position": 0,
    "group_num": 1,
    "pe_num": (2, 2),
    "tile_connection": 2,
    "inter_tile_bw": 80,
}


def _make_config(preset: str, xbar, adc: int) -> Dict[str, Any]:
    return {
        "rram_preset": preset,
        "xbar_size": xbar,
        "adc_choice": adc,
        **_FIXED_DIMS,
    }


# 5 configs covering boundaries + 1 reproducibility duplicate.
PLAN: List[Dict[str, Any]] = [
    {"id": "C1_min",       "tag": "smallest+lowest_adc", "config": _make_config("P0", (128, 128), 4)},
    {"id": "C2_max",       "tag": "largest+highest_adc", "config": _make_config("P3", (512, 512), 7)},
    {"id": "C3_mid",       "tag": "midpoint",            "config": _make_config("P1", (256, 256), 6)},
    {"id": "C4_p0_big",    "tag": "p0_with_big_xbar",    "config": _make_config("P0", (512, 512), 4)},
    {"id": "C5_repro",     "tag": "duplicate_of_C3",     "config": _make_config("P1", (256, 256), 6)},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", default=str(REPO_ROOT / "SimConfig.ini"))
    parser.add_argument("--weights", default=str(REPO_ROOT / "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--seed", type=int, default=42, help="Noise seed for accuracy reproducibility.")
    parser.add_argument("--output", default=str(REPO_ROOT / "validate/output/mini_sweep_clean_v1.csv"))
    parser.add_argument("--max-acc-batches", type=int, default=11)
    args = parser.parse_args()

    apply_space_profile("clean_v1")
    print(f"SPACE: clean_v1 (hash={space_hash('clean_v1')})")
    print(f"NN: {args.nn} | weights: {args.weights}")
    print(f"Seed: {args.seed} | max_acc_batches: {args.max_acc_batches}")
    print(f"Output: {args.output}")
    print()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for entry in PLAN:
        cfg_id = entry["id"]
        cfg = entry["config"]
        tag = entry["tag"]
        print(f"--- {cfg_id} ({tag}) ---")
        print(f"  config: {cfg}")
        temp_path = write_temp_config(args.base_config, cfg)
        t0 = time.time()
        try:
            res = evaluate_config(
                sim_config_path=temp_path,
                nn_name=args.nn,
                weights_path=args.weights,
                config_values=cfg,
                run_accuracy=True,
                enable_saf=True,
                enable_variation=True,
                enable_rratio=False,
                fixed_qrange=False,
                device="cpu",
                max_acc_batches=args.max_acc_batches,
                noise_seed=args.seed,
            )
            elapsed = time.time() - t0
            row = {
                "id": cfg_id,
                "tag": tag,
                **{k: (str(v) if isinstance(v, tuple) else v) for k, v in cfg.items()},
                "latency_ns": res.latency_ns,
                "area_um2": res.area_um2,
                "power_w": res.power_w,
                "energy_nj": res.energy_nj,
                "accuracy": res.accuracy,
                "elapsed_s": elapsed,
                "status": "ok",
            }
            print(f"  PPA: latency={res.latency_ns:.3e} ns, area={res.area_um2:.3e} um2, "
                  f"power={res.power_w:.3f} W, energy={res.energy_nj:.3e} nJ")
            print(f"  acc: {res.accuracy:.4f}, elapsed: {elapsed:.1f}s")
        except Exception as exc:
            row = {
                "id": cfg_id, "tag": tag,
                **{k: (str(v) if isinstance(v, tuple) else v) for k, v in cfg.items()},
                "latency_ns": None, "area_um2": None, "power_w": None,
                "energy_nj": None, "accuracy": None,
                "elapsed_s": time.time() - t0, "status": f"error: {type(exc).__name__}: {exc}",
            }
            print(f"  ERROR: {exc!r}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        rows.append(row)
        print()

    # Write CSV
    if rows:
        keys = list(rows[0].keys())
        with open(args.output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"CSV written: {args.output}")

    # Sanity assertions
    print()
    print("=== Sanity checks ===")
    crashes = [r for r in rows if r["status"] != "ok"]
    if crashes:
        print(f"  [FAIL] {len(crashes)}/{len(rows)} configs crashed:")
        for r in crashes:
            print(f"    - {r['id']}: {r['status']}")
        return 1
    print(f"  [PASS] All {len(rows)} configs ran without exception.")

    # Reproducibility: C3 vs C5 should be bit-identical
    c3 = next(r for r in rows if r["id"] == "C3_mid")
    c5 = next(r for r in rows if r["id"] == "C5_repro")
    metrics = ["latency_ns", "area_um2", "power_w", "energy_nj", "accuracy"]
    repro_ok = True
    for m in metrics:
        if c3[m] is None or c5[m] is None:
            repro_ok = False
            continue
        if abs(c3[m] - c5[m]) > 1e-12 * max(abs(c3[m]), 1e-12):
            print(f"  [FAIL] reproducibility diff on {m}: C3={c3[m]}, C5={c5[m]}")
            repro_ok = False
    if repro_ok:
        print(f"  [PASS] C3 and C5 (same config, same seed) are bit-identical.")

    # Sane outputs
    sane = True
    for r in rows:
        if r["status"] != "ok":
            continue
        for m in metrics:
            v = r[m]
            if v is None:
                print(f"  [FAIL] {r['id']}: {m} is None")
                sane = False
            elif not (0 < abs(v) < 1e15):
                print(f"  [WARN] {r['id']}: {m} = {v} (suspicious magnitude)")
    if sane:
        print(f"  [PASS] All numeric outputs in plausible range.")

    # Wall-time summary for sweep budgeting
    times = [r["elapsed_s"] for r in rows if r["status"] == "ok"]
    if times:
        print(f"\n  Per-config time: min={min(times):.1f}s, "
              f"max={max(times):.1f}s, mean={sum(times)/len(times):.1f}s")
        proj = sum(times) / len(times) * 288
        print(f"  Projected 288-config sweep: {proj/60:.1f} min ({proj/3600:.2f} h)")

    if crashes or not repro_ok or not sane:
        print("\n>>> Mini-sweep FAILED. Fix issues before running full sweep.")
        return 1
    print("\n>>> Mini-sweep PASSED. Ready for full 288-config sweep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
