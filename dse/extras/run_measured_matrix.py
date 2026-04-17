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
import csv
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dse.contracts import (
    build_experiment_manifest,
    make_measured_scenario,
    resolve_resource,
    write_json,
    write_patched_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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


def _build_cmd(args: argparse.Namespace, patched_config_path: Path, scenario_json_path: Path, output_root: Path) -> List[str]:
    cmd = [
        args.python_bin,
        "dse/run_matrix_csv.py",
        "--matrix-csv",
        args.matrix_csv,
        "--scenario-json",
        str(scenario_json_path),
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
    if args.accuracy_target is not None and not args.run_accuracy:
        parser.error("--accuracy-target requires --run-accuracy.")

    measured_path = Path(args.measured_presets_csv).expanduser().resolve()
    base_config_path = Path(resolve_resource(args.base_config, "config", repo_root=REPO_ROOT)).expanduser().resolve()
    args.weights = resolve_resource(args.weights, "weights", repo_root=REPO_ROOT)
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
    scenarios_dir = output_root / "scenarios"
    root_manifest = build_experiment_manifest(
        workflow="measured_matrix",
        entrypoint="dse/extras/run_measured_matrix.py",
        inputs={
            "measured_presets_csv": str(measured_path),
            "base_config_path": str(base_config_path),
            "weights_path": str(Path(args.weights).resolve()),
            "nn": args.nn,
            "dataset_module": args.dataset_module,
            "matrix_csv": str(Path(args.matrix_csv).expanduser()),
            "selected_presets": [row["preset_name"] for row in rows],
        },
        execution={
            "space_profile": args.space_profile,
            "run_accuracy": bool(args.run_accuracy),
            "accuracy_target": args.accuracy_target,
            "enable_saf": bool(args.enable_saf),
            "enable_variation": bool(args.enable_variation),
            "enable_rratio": bool(args.enable_rratio),
            "fixed_qrange": bool(args.fixed_qrange),
            "seed": args.seed,
            "workers": args.workers,
            "max_points": args.max_points,
            "batch_size": args.batch_size,
            "num_batches": args.num_batches,
            "batch_index": args.batch_index,
            "matrix_name": args.matrix_name or [],
            "point_id": args.point_id or [],
        },
        outputs={"output_root": str(output_root)},
        notes=[
            "Each preset produces one patched SimConfig and one scenario JSON under this output root.",
            "Downstream run_matrix_csv.py receives the scenario contract explicitly.",
        ],
    )
    write_json(output_root / "experiment_manifest.json", root_manifest)

    for row in rows:
        preset_name = row["preset_name"].strip()
        preset_output = output_root / preset_name
        patched_config_path = configs_dir / f"{preset_name}.ini"
        scenario = make_measured_scenario(row, measured_presets_csv=str(measured_path))
        scenario_json_path = scenarios_dir / f"{preset_name}.json"
        write_json(scenario_json_path, scenario)
        write_patched_config(base_config_path, scenario.get("config_patch", {}), patched_config_path)

        cmd = _build_cmd(args, patched_config_path, scenario_json_path, preset_output)
        print(f"[measured-matrix] run preset={preset_name}")
        print(f"[measured-matrix] command={' '.join(cmd)}")
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)

    print(f"[measured-matrix] done -> {output_root}")


if __name__ == "__main__":
    main()
