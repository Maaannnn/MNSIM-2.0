#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run matrix experiments using measured presets extracted from test_data.

Workflow:
  1) Read measured_presets.csv
  2) Materialize one patched SimConfig.ini per measured preset
  3) Invoke dse/run_matrix_csv.py for each preset

This keeps the existing DSE/matrix pipeline unchanged while letting measured
device states drive the experiment.
"""
from __future__ import annotations

import argparse
import configparser as cp
import csv
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

def _resolve_resource(path_like: str, kind: str) -> str:
    p = Path(os.path.expanduser(str(path_like)))
    if p.exists():
        return str(p.resolve())
    name = Path(str(path_like)).name
    if kind == "weights":
        for cand in [REPO_ROOT/"weights"/name, REPO_ROOT/name]:
            if cand.exists():
                return str(cand.resolve())
    if kind == "config":
        for cand in [REPO_ROOT/"configs"/name, REPO_ROOT/name]:
            if cand.exists():
                return str(cand.resolve())
    return str(p)


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _read_rows(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _select_presets(rows: List[Dict[str, str]], names: Optional[List[str]]) -> List[Dict[str, str]]:
    if not names:
        return rows
    wanted = {name.strip() for name in names}
    return [row for row in rows if row.get("preset_name", "").strip() in wanted]


def _patch_config(base_config_path: Path, row: Dict[str, str], output_path: Path) -> None:
    parser = cp.ConfigParser()
    parser.read(base_config_path, encoding="UTF-8")

    device_resistance = row.get("device_resistance", "").strip()
    device_variation = row.get("device_variation", "").strip()
    device_saf = row.get("device_saf_heuristic", "").strip()

    if not device_resistance:
        raise ValueError(f"Missing device_resistance for preset={row.get('preset_name')}")
    parser.set("Device level", "Device_Resistance", device_resistance)

    if device_variation:
        parser.set("Device level", "Device_Variation", device_variation)

    if device_saf:
        parser.set("Device level", "Device_SAF", f"{device_saf},{device_saf}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        parser.write(f)


def _build_cmd(args: argparse.Namespace, patched_config_path: Path, output_root: Path) -> List[str]:
    cmd = [
        args.python_bin,
        "dse/run_matrix_csv.py",
        "--matrix-csv",
        args.matrix_csv,
        "--base-config",
        str(patched_config_path),
        "--nn",
        args.nn,
        "--weights",
        args.weights,
        "--device",
        args.device,
        "--dataset-module",
        args.dataset_module,
        "--space-profile",
        args.space_profile,
        "--max-acc-batches",
        str(args.max_acc_batches),
        "--seed",
        str(args.seed),
        "--workers",
        str(args.workers),
        "--output-root",
        str(output_root),
    ]
    if args.run_accuracy:
        cmd.append("--run-accuracy")
    if args.accuracy_target is not None:
        cmd.extend(["--accuracy-target", str(args.accuracy_target)])
    if args.enable_saf:
        cmd.append("--enable-saf")
    if args.enable_variation:
        cmd.append("--enable-variation")
    if args.enable_rratio:
        cmd.append("--enable-rratio")
    if args.fixed_qrange:
        cmd.append("--fixed-qrange")
    if args.dataset_append:
        cmd.append("--dataset-append")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.fail_fast:
        cmd.append("--fail-fast")
    if args.max_points is not None:
        cmd.extend(["--max-points", str(args.max_points)])
    if args.batch_size is not None:
        cmd.extend(["--batch-size", str(args.batch_size)])
    if args.num_batches is not None:
        cmd.extend(["--num-batches", str(args.num_batches)])
    if args.batch_index is not None:
        cmd.extend(["--batch-index", str(args.batch_index)])
    if args.matrix_name:
        cmd.extend(["--matrix-name", *args.matrix_name])
    if args.point_id:
        cmd.extend(["--point-id", *args.point_id])
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Run matrix experiments with measured presets")
    parser.add_argument("--measured-presets-csv", required=True)
    parser.add_argument("--matrix-csv", default="artifacts/dse/matrices/rram_v2/matrix_all.csv")
    parser.add_argument("--preset-name", nargs="+", default=None, help="Optional subset of measured presets")
    parser.add_argument("--base-config", default="SimConfig.ini")
    parser.add_argument("--weights", default="cifar10_vgg8_params.pth")
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dataset-module", default="MNSIM.Interface.cifar10")
    parser.add_argument("--space-profile", default="rram_v2")
    parser.add_argument("--max-acc-batches", type=int, default=11)
    parser.add_argument("--run-accuracy", action="store_true")
    parser.add_argument("--accuracy-target", type=float, default=None)
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=True)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--dataset-append", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--max-points", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--num-batches", type=int, default=None)
    parser.add_argument("--batch-index", type=int, default=None)
    parser.add_argument("--matrix-name", nargs="+", default=None)
    parser.add_argument("--point-id", nargs="+", default=None)
    args = parser.parse_args()

    measured_path = Path(args.measured_presets_csv).expanduser().resolve()
    base_config_path = Path(_resolve_resource(args.base_config, "config")).expanduser().resolve()
    args.weights = _resolve_resource(args.weights, "weights")
    rows = _select_presets(_read_rows(measured_path), args.preset_name)
    if not rows:
        raise SystemExit("No measured presets selected.")

    if args.output_root:
        output_root = Path(args.output_root).expanduser().resolve()
    else:
        output_root = REPO_ROOT / "artifacts" / "dse" / "matrix_runs" / f"measured_run_{_timestamp()}"
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"[measured-matrix] measured presets : {measured_path}")
    print(f"[measured-matrix] matrix csv       : {args.matrix_csv}")
    print(f"[measured-matrix] output root      : {output_root}")
    print(f"[measured-matrix] selected presets : {', '.join(row['preset_name'] for row in rows)}")

    configs_dir = output_root / "configs"
    for row in rows:
        preset_name = row["preset_name"].strip()
        preset_output = output_root / preset_name
        patched_config_path = configs_dir / f"{preset_name}.ini"
        _patch_config(base_config_path, row, patched_config_path)

        cmd = _build_cmd(args, patched_config_path, preset_output)
        print(f"[measured-matrix] run preset={preset_name}")
        print(f"[measured-matrix] command={' '.join(cmd)}")
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)

    print(f"[measured-matrix] done -> {output_root}")


if __name__ == "__main__":
    main()
