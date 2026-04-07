#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import random
from typing import Any, Dict, List

from dse_multi_utils import SPACE, evaluate_config, write_temp_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline surrogate dataset by full MNSIM simulation")
    cwd = os.getcwd()
    parser.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    parser.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=False)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--output-dir", default=os.path.join(cwd, "surrogate_data"))
    args = parser.parse_args()

    random.seed(args.seed)
    os.makedirs(args.output_dir, exist_ok=True)

    dim_names = list(SPACE.keys())
    all_candidates = [
        dict(zip(dim_names, combo))
        for combo in itertools.product(*[SPACE[d]["values"] for d in dim_names])
    ]
    random.shuffle(all_candidates)
    n = min(args.samples, len(all_candidates))
    picked = all_candidates[:n]

    rows: List[Dict[str, Any]] = []
    for i, cfg in enumerate(picked, start=1):
        temp_cfg = write_temp_config(args.base_config, cfg)
        try:
            res = evaluate_config(
                sim_config_path=temp_cfg,
                nn_name=args.nn,
                weights_path=args.weights,
                run_accuracy=True,
                enable_saf=args.enable_saf,
                enable_variation=args.enable_variation,
                enable_rratio=args.enable_rratio,
                fixed_qrange=args.fixed_qrange,
                device=args.device,
                config_values=cfg,
            )
        finally:
            os.remove(temp_cfg)

        row: Dict[str, Any] = {
            "id": i,
            "latency_ns": res.latency_ns,
            "energy_nj": res.energy_nj,
            "area_um2": res.area_um2,
            "power_w": res.power_w,
            "accuracy": res.accuracy,
            "elapsed_s": res.elapsed_s,
        }
        for d in dim_names:
            row[d] = json.dumps(cfg[d], ensure_ascii=False)
            row[f"{d}__idx"] = SPACE[d]["values"].index(cfg[d])
        rows.append(row)
        print(
            f"[{i}/{n}] lat={res.latency_ns:.1f} en={res.energy_nj:.1f} "
            f"area={res.area_um2:.1f} acc={res.accuracy:.6f}"
        )

    out_csv = os.path.join(args.output_dir, "dataset.csv")
    fields = (
        ["id"] +
        dim_names +
        [f"{d}__idx" for d in dim_names] +
        ["latency_ns", "energy_nj", "area_um2", "power_w", "accuracy", "elapsed_s"]
    )
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    meta = {
        "num_samples": n,
        "seed": args.seed,
        "nn": args.nn,
        "weights": args.weights,
        "base_config": args.base_config,
        "dims": dim_names,
        "output_csv": out_csv,
    }
    out_meta = os.path.join(args.output_dir, "dataset_meta.json")
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("\n=== Dataset Build Done ===")
    print(f"dataset csv : {out_csv}")
    print(f"meta json   : {out_meta}")


if __name__ == "__main__":
    main()
