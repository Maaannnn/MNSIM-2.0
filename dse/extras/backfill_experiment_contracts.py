#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dse.contracts import (
    EXPERIMENT_SCHEMA_VERSION,
    build_experiment_manifest,
    make_measured_scenario,
    make_nominal_scenario,
    read_json,
    resolve_resource,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_measured_rows(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    if path is None or not path.exists():
        return {}
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {str(row.get("preset_name", "")).strip(): row for row in rows if str(row.get("preset_name", "")).strip()}


def _iter_trial_dirs(root: Path) -> Iterable[Path]:
    for result_json in root.rglob("result.json"):
        trial_dir = result_json.parent
        if (trial_dir / "history.csv").exists():
            yield trial_dir


def _scenario_from_trial(
    trial_dir: Path,
    run_config: Dict[str, Any],
    measured_rows: Dict[str, Dict[str, str]],
    measured_presets_csv: Optional[Path],
) -> Dict[str, Any]:
    if run_config.get("scenario"):
        return run_config["scenario"]

    parent_name = trial_dir.parent.name
    possible_jsons = [
        trial_dir.parent.parent / "scenarios" / f"{parent_name}.json",
        trial_dir.parent / "scenarios" / f"{parent_name}.json",
    ]
    for path in possible_jsons:
        if path.exists():
            try:
                return read_json(path)
            except Exception:
                pass

    if parent_name in measured_rows and measured_presets_csv is not None:
        return make_measured_scenario(measured_rows[parent_name], measured_presets_csv=str(measured_presets_csv))

    base_config = resolve_resource(run_config.get("base_config_path", "SimConfig.ini"), "config", repo_root=REPO_ROOT)
    if parent_name.startswith("meas_"):
        return {
            "kind": "inferred_measured_preset",
            "name": parent_name,
            "base_config_path": str(Path(base_config).expanduser()),
            "config_patch": {},
            "source": {"inferred_from": "trial_dir_parent"},
        }
    return make_nominal_scenario(base_config)


def _manifest_for_trial(trial_dir: Path, result_payload: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    rc = result_payload.get("run_config", {})
    algo = result_payload.get("algo", "")
    workflow = "matrix_csv" if algo == "matrixcsv" else "search_trial"
    inputs = {
        "base_config_path": resolve_resource(rc.get("base_config_path", "SimConfig.ini"), "config", repo_root=REPO_ROOT),
        "weights_path": resolve_resource(rc.get("weights_path", ""), "weights", repo_root=REPO_ROOT),
        "nn": rc.get("nn", ""),
        "dataset_module": rc.get("dataset_module", ""),
    }
    selected_matrix = trial_dir / "selected_matrix.csv"
    if selected_matrix.exists():
        inputs["selected_matrix_csv"] = str(selected_matrix.resolve())

    return build_experiment_manifest(
        workflow=workflow,
        entrypoint=f"dse/{'run_matrix_csv.py' if algo == 'matrixcsv' else 'run_dse.py'}",
        inputs=inputs,
        execution={
            "algo": algo,
            "seed": result_payload.get("seed"),
            "budget": result_payload.get("budget"),
            "space_profile": rc.get("space_profile", ""),
            "run_accuracy": rc.get("run_accuracy", False),
            "accuracy_target": rc.get("algo_kwargs", {}).get("accuracy_target"),
            "enable_saf": rc.get("enable_saf", False),
            "enable_variation": rc.get("enable_variation", False),
            "enable_rratio": rc.get("enable_rratio", False),
            "fixed_qrange": rc.get("fixed_qrange", False),
            "device": rc.get("device", "cpu"),
            "max_acc_batches": rc.get("max_acc_batches", 0),
        },
        outputs={
            "trial_dir": str(trial_dir.resolve()),
            "result_json": str((trial_dir / "result.json").resolve()),
            "history_csv": str((trial_dir / "history.csv").resolve()),
        },
        scenario=scenario,
        notes=["Backfilled from legacy run artifacts."],
    )


def _patch_result_json(trial_dir: Path, result_payload: Dict[str, Any], scenario: Dict[str, Any]) -> bool:
    rc = dict(result_payload.get("run_config", {}))
    changed = False
    if rc.get("contract_version") != EXPERIMENT_SCHEMA_VERSION:
        rc["contract_version"] = EXPERIMENT_SCHEMA_VERSION
        changed = True
    if rc.get("scenario") != scenario:
        rc["scenario"] = scenario
        changed = True

    resolved_weights = resolve_resource(rc.get("weights_path", ""), "weights", repo_root=REPO_ROOT)
    resolved_config = resolve_resource(rc.get("base_config_path", "SimConfig.ini"), "config", repo_root=REPO_ROOT)
    if rc.get("weights_path") != resolved_weights:
        rc["weights_path"] = resolved_weights
        changed = True
    if rc.get("base_config_path") != resolved_config:
        rc["base_config_path"] = resolved_config
        changed = True

    if not changed:
        return False

    result_payload["run_config"] = rc
    write_json(trial_dir / "result.json", result_payload)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill experiment manifests for legacy DSE runs")
    parser.add_argument("--root", nargs="+", required=True, help="One or more run roots to scan")
    parser.add_argument("--measured-presets-csv", default=None, help="Optional measured_presets.csv for recovering measured scenario metadata")
    parser.add_argument("--overwrite-manifest", action="store_true")
    parser.add_argument("--patch-result-json", action="store_true")
    args = parser.parse_args()

    measured_presets_csv = Path(args.measured_presets_csv).expanduser().resolve() if args.measured_presets_csv else None
    measured_rows = _load_measured_rows(measured_presets_csv)

    created = updated = skipped = 0
    for raw_root in args.root:
        root = Path(raw_root).expanduser().resolve()
        if not root.exists():
            continue
        for trial_dir in _iter_trial_dirs(root):
            result_path = trial_dir / "result.json"
            try:
                result_payload = read_json(result_path)
            except Exception:
                continue
            scenario = _scenario_from_trial(trial_dir, result_payload.get("run_config", {}), measured_rows, measured_presets_csv)
            manifest = _manifest_for_trial(trial_dir, result_payload, scenario)
            manifest_path = trial_dir / "experiment_manifest.json"
            if manifest_path.exists() and not args.overwrite_manifest:
                skipped += 1
            else:
                write_json(manifest_path, manifest)
                created += 1
            if args.patch_result_json and _patch_result_json(trial_dir, result_payload, scenario):
                updated += 1

    print(json.dumps({
        "created_manifests": created,
        "updated_result_json": updated,
        "skipped_existing_manifests": skipped,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
