#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dse.contracts import build_experiment_manifest, read_json, write_json
from dse.core import DIM_NAMES, encode_dim_value
from dse.extras.run_robustness import _choose_candidates
from dse.output import DSERecord
from dse.run_dse import load_results_from_dir


def _config_key_from_config(config: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((dim, encode_dim_value(config.get(dim, ""))) for dim in DIM_NAMES))


def _config_key_from_row(row: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((dim, str(row.get(dim, ""))) for dim in DIM_NAMES))


def _config_dict_from_key(key: Tuple[Tuple[str, str], ...]) -> Dict[str, str]:
    return {dim: value for dim, value in key}


def _scenario_name_for_root(root: Path, results: List[Any]) -> str:
    if results:
        scenario = results[0].run_config.scenario or {}
        if scenario.get("name"):
            return str(scenario["name"])
    return root.name


def _load_summary_rows(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _summary_sort_value(row: Dict[str, str], sort_by: str) -> float:
    mapping = {
        "latency_ns": "mean_latency_ns",
        "energy_nj": "mean_energy_nj",
        "area_um2": "mean_area_um2",
        "accuracy": "mean_accuracy",
    }
    col = mapping.get(sort_by, sort_by)
    value = row.get(col, "")
    if sort_by == "accuracy":
        return -float(value or "-inf")
    return float(value or "inf")


def _select_summary_candidates(rows: List[Dict[str, str]], *, topk: int, sort_by: str) -> List[Dict[str, str]]:
    ranked = sorted(rows, key=lambda row: _summary_sort_value(row, sort_by))
    if topk > 0:
        ranked = ranked[:topk]
    return ranked


def _discover_scenario_dirs(root: Path, names: Optional[Iterable[str]]) -> List[Path]:
    wanted = {name.strip() for name in names or []}
    dirs: List[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if wanted and child.name not in wanted:
            continue
        try:
            results = load_results_from_dir(str(child))
        except Exception:
            continue
        if results:
            dirs.append(child)
    return dirs


def _read_trial_manifest(root: Path) -> Dict[str, Any]:
    for candidate in [
        root / "experiment_manifest.json",
        root.parent / "experiment_manifest.json",
    ]:
        if candidate.exists():
            try:
                return read_json(candidate)
            except Exception:
                continue
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate robustness across measured preset scenarios")
    parser.add_argument("--scenario-root", required=True, help="Root directory containing per-scenario subdirectories")
    parser.add_argument("--preset-name", nargs="+", default=None, help="Optional subset of scenario directory names")
    parser.add_argument("--output-dir", default=None, help="Default: <scenario-root>/cross_scenario_robustness")
    parser.add_argument("--source", choices=["pareto", "history"], default="pareto")
    parser.add_argument("--sort-by", choices=["latency_ns", "energy_nj", "area_um2", "accuracy", "scalarized_obj"], default="energy_nj")
    parser.add_argument("--topk", type=int, default=2, help="Per-scenario candidate count; 0 keeps all")
    parser.add_argument("--accuracy-target", type=float, default=None)
    parser.add_argument("--use-robustness-summary", action="store_true", help="Consume each scenario's robustness/summary.csv when available")
    args = parser.parse_args()

    scenario_root = Path(args.scenario_root).expanduser().resolve()
    scenario_dirs = _discover_scenario_dirs(scenario_root, args.preset_name)
    if not scenario_dirs:
        raise SystemExit("No valid scenario directories found.")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else scenario_root / "cross_scenario_robustness"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_payloads: List[Dict[str, Any]] = []
    candidate_union: Dict[Tuple[Tuple[str, str], ...], Dict[str, str]] = {}

    for scenario_dir in scenario_dirs:
        results = load_results_from_dir(str(scenario_dir))
        if not results:
            continue
        scenario_name = _scenario_name_for_root(scenario_dir, results)
        scenario_contract = results[0].run_config.scenario or {}
        payload: Dict[str, Any] = {
            "scenario_dir": scenario_dir,
            "scenario_name": scenario_name,
            "scenario": scenario_contract,
            "mode": "raw",
            "record_map": {},
            "selected_keys": [],
        }

        if args.use_robustness_summary:
            summary_csv = scenario_dir / "robustness" / "summary.csv"
            if summary_csv.exists():
                rows = _load_summary_rows(summary_csv)
                payload["mode"] = "robust_summary"
                payload["record_map"] = {
                    _config_key_from_row(row): row
                    for row in rows
                }
                chosen_rows = _select_summary_candidates(rows, topk=args.topk, sort_by=args.sort_by)
                payload["selected_keys"] = [_config_key_from_row(row) for row in chosen_rows]
                for key in payload["selected_keys"]:
                    candidate_union.setdefault(key, _config_dict_from_key(key))
                scenario_payloads.append(payload)
                continue

        all_records = [record for result in results for record in result.records]
        chosen: List[DSERecord] = []
        for result in results:
            chosen.extend(_choose_candidates(result.records, source=args.source, topk=args.topk, sort_by=args.sort_by))
        dedup_map = {_config_key_from_config(record.config): record for record in all_records}
        payload["record_map"] = dedup_map
        payload["selected_keys"] = [_config_key_from_config(record.config) for record in chosen]
        for key in payload["selected_keys"]:
            candidate_union.setdefault(key, _config_dict_from_key(key))
        scenario_payloads.append(payload)

    if not scenario_payloads:
        raise SystemExit("No scenario payloads were collected.")

    per_scenario_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for candidate_index, key in enumerate(sorted(candidate_union.keys()), start=1):
        candidate_cfg = candidate_union[key]
        acc_mean_values: List[float] = []
        acc_worst_values: List[float] = []
        yield_values: List[float] = []
        lat_values: List[float] = []
        en_values: List[float] = []
        area_values: List[float] = []
        matched = 0

        for payload in scenario_payloads:
            row: Dict[str, Any] = {
                "candidate_index": candidate_index,
                "scenario_name": payload["scenario_name"],
                "mode": payload["mode"],
            }
            row.update(candidate_cfg)

            obj = payload["record_map"].get(key)
            if obj is None:
                row["matched"] = 0
                per_scenario_rows.append(row)
                continue

            matched += 1
            row["matched"] = 1
            if payload["mode"] == "robust_summary":
                mean_acc = float(obj["mean_accuracy"]) if obj.get("mean_accuracy") else None
                worst_acc = float(obj["worst_accuracy"]) if obj.get("worst_accuracy") else None
                scenario_yield = float(obj["yield"]) if obj.get("yield") else None
                mean_lat = float(obj["mean_latency_ns"])
                mean_en = float(obj["mean_energy_nj"])
                mean_area = float(obj["mean_area_um2"])
            else:
                mean_acc = float(obj.accuracy) if obj.accuracy is not None else None
                worst_acc = mean_acc
                if mean_acc is not None and args.accuracy_target is not None:
                    scenario_yield = 1.0 if mean_acc >= float(args.accuracy_target) else 0.0
                else:
                    scenario_yield = None
                mean_lat = float(obj.latency_ns)
                mean_en = float(obj.energy_nj)
                mean_area = float(obj.area_um2)

            row["mean_accuracy"] = mean_acc
            row["worst_accuracy"] = worst_acc
            row["scenario_yield"] = scenario_yield
            row["latency_ns"] = mean_lat
            row["energy_nj"] = mean_en
            row["area_um2"] = mean_area
            per_scenario_rows.append(row)

            if mean_acc is not None:
                acc_mean_values.append(mean_acc)
            if worst_acc is not None:
                acc_worst_values.append(worst_acc)
            if scenario_yield is not None:
                yield_values.append(scenario_yield)
            lat_values.append(mean_lat)
            en_values.append(mean_en)
            area_values.append(mean_area)

        summary_row: Dict[str, Any] = {
            "candidate_index": candidate_index,
            "scenario_count": len(scenario_payloads),
            "matched_scenarios": matched,
            "mean_accuracy": float(np.mean(acc_mean_values)) if acc_mean_values else None,
            "std_accuracy": float(np.std(acc_mean_values)) if acc_mean_values else None,
            "worst_accuracy": float(np.min(acc_worst_values)) if acc_worst_values else None,
            "mean_yield": float(np.mean(yield_values)) if yield_values else None,
            "mean_latency_ns": float(np.mean(lat_values)) if lat_values else None,
            "mean_energy_nj": float(np.mean(en_values)) if en_values else None,
            "mean_area_um2": float(np.mean(area_values)) if area_values else None,
        }
        summary_row.update(candidate_cfg)
        summary_rows.append(summary_row)

    def _sort_summary(row: Dict[str, Any]) -> Tuple[Any, ...]:
        return (
            -(row["mean_yield"] if row["mean_yield"] is not None else -1.0),
            -(row["worst_accuracy"] if row["worst_accuracy"] is not None else -1.0),
            -(row["mean_accuracy"] if row["mean_accuracy"] is not None else -1.0),
            row["mean_energy_nj"] if row["mean_energy_nj"] is not None else float("inf"),
            row["mean_latency_ns"] if row["mean_latency_ns"] is not None else float("inf"),
            row["mean_area_um2"] if row["mean_area_um2"] is not None else float("inf"),
        )

    summary_rows = sorted(summary_rows, key=_sort_summary)
    for rank, row in enumerate(summary_rows, start=1):
        row["robust_rank"] = rank

    per_fields = list(per_scenario_rows[0].keys()) if per_scenario_rows else ["candidate_index", "scenario_name"]
    with open(out_dir / "per_scenario.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=per_fields)
        writer.writeheader()
        writer.writerows(per_scenario_rows)

    summary_fields = ["robust_rank"] + [field for field in summary_rows[0].keys() if field != "robust_rank"]
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    manifest = build_experiment_manifest(
        workflow="cross_scenario_robustness",
        entrypoint="dse/extras/run_cross_scenario_robustness.py",
        inputs={
            "scenario_root": str(scenario_root),
            "preset_names": [payload["scenario_name"] for payload in scenario_payloads],
        },
        execution={
            "source": args.source,
            "sort_by": args.sort_by,
            "topk": args.topk,
            "accuracy_target": args.accuracy_target,
            "use_robustness_summary": bool(args.use_robustness_summary),
        },
        outputs={
            "output_dir": str(out_dir),
            "summary_csv": str((out_dir / "summary.csv").resolve()),
            "per_scenario_csv": str((out_dir / "per_scenario.csv").resolve()),
        },
        scenario={
            "kind": "cross_scenario",
            "name": scenario_root.name,
            "members": [payload["scenario"] or {"name": payload["scenario_name"]} for payload in scenario_payloads],
        },
        notes=[
            "Candidate union is built from the selected candidates of each scenario.",
            "When --use-robustness-summary is enabled, aggregation uses each scenario's robustness/summary.csv.",
        ],
        extra={"trial_manifest": _read_trial_manifest(scenario_root)},
    )
    write_json(out_dir / "experiment_manifest.json", manifest)
    write_json(
        out_dir / "meta.json",
        {
            "scenario_root": str(scenario_root),
            "scenario_count": len(scenario_payloads),
            "candidate_count": len(summary_rows),
            "use_robustness_summary": bool(args.use_robustness_summary),
        },
    )

    print(f"[cross-scenario] summary -> {out_dir / 'summary.csv'}")
    print(f"[cross-scenario] per-scenario -> {out_dir / 'per_scenario.csv'}")


if __name__ == "__main__":
    main()
