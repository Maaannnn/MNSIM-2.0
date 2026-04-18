#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List

from dse.contracts import read_json
from dse.core import SPACE, evaluate_config, write_temp_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline surrogate dataset by full MNSIM simulation")
    cwd = os.getcwd()
    parser.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    parser.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--scenario-json", default=None, help="Optional scenario contract JSON; its config_patch is re-applied after SPACE overrides.")
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=False)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--output-dir", default=os.path.join(cwd, "surrogate_data"))
    args = parser.parse_args()

    # Resolve resources to support new weights/ and configs/ folders
    _PROJ_ROOT = Path(__file__).resolve().parents[2]
    def _resolve_resource(path_like: str, kind: str) -> str:
        p = Path(os.path.expanduser(str(path_like)))
        if p.exists():
            return str(p.resolve())
        name = Path(str(path_like)).name
        if kind == "weights":
            for cand in [_PROJ_ROOT/"weights"/name, _PROJ_ROOT/name]:
                if cand.exists():
                    return str(cand.resolve())
        if kind == "config":
            for cand in [_PROJ_ROOT/"configs"/name, _PROJ_ROOT/name]:
                if cand.exists():
                    return str(cand.resolve())
        return str(p)
    args.weights = _resolve_resource(args.weights, "weights")
    args.base_config = _resolve_resource(args.base_config, "config")
    scenario_patch = None
    if args.scenario_json:
        scenario = read_json(Path(args.scenario_json).expanduser().resolve())
        scenario_patch = scenario.get("config_patch") or None

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
        temp_cfg = write_temp_config(args.base_config, cfg, post_patch=scenario_patch)
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
        "scenario_json": args.scenario_json,
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
