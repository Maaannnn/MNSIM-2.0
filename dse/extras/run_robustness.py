#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from dse.contracts import build_experiment_manifest, write_json
from dse.core import accuracy_violation, encode_dim_value, evaluate_config, write_temp_config  # noqa: E402
from dse.output import DSERecord  # noqa: E402
from dse.progress import try_make_tqdm, update_progress  # noqa: E402
from dse.run_dse import load_results_from_dir  # noqa: E402


def _score_record(record: DSERecord, metric: str) -> float:
    if metric == "accuracy":
        return -(record.accuracy if record.accuracy is not None else float("-inf"))
    if metric == "scalarized_obj":
        return float(record.extra.get("scalarized_obj", float("inf")))
    return float(getattr(record, metric))


def _record_key(record: DSERecord) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((k, encode_dim_value(v)) for k, v in record.config.items()))


def _choose_candidates(
    records: List[DSERecord],
    *,
    source: str,
    topk: int,
    sort_by: str,
) -> List[DSERecord]:
    chosen = [r for r in records if r.is_pareto] if source == "pareto" else list(records)
    dedup: Dict[Tuple[Tuple[str, str], ...], DSERecord] = {}
    for record in chosen:
        key = _record_key(record)
        prev = dedup.get(key)
        if prev is None or _score_record(record, sort_by) < _score_record(prev, sort_by):
            dedup[key] = record
    ranked = sorted(dedup.values(), key=lambda r: _score_record(r, sort_by))
    if topk > 0:
        ranked = ranked[:topk]
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser(description="Robustness re-evaluation for selected DSE configurations")
    parser.add_argument("--input-root", required=True, help="Existing DSE run directory, e.g. artifacts/dse/search_runs/run_20260408_154443")
    parser.add_argument("--output-dir", default=None, help="Default: <input-root>/robustness")
    parser.add_argument("--source", choices=["pareto", "history"], default="pareto")
    parser.add_argument("--sort-by", choices=["latency_ns", "energy_nj", "area_um2", "accuracy", "scalarized_obj"], default="energy_nj")
    parser.add_argument("--topk", type=int, default=5, help="0 means keep all candidates from --source")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--algo", default=None, help="Optional filter, e.g. nsga2")
    parser.add_argument("--seed", type=int, default=None, help="Optional filter for trial seed")
    parser.add_argument("--accuracy-target", type=float, default=None, help="Override accuracy target for yield; default uses trial config if present")
    args = parser.parse_args()

    results = load_results_from_dir(args.input_root)
    if args.algo is not None:
        results = [r for r in results if r.run_config.algo == args.algo]
    if args.seed is not None:
        results = [r for r in results if r.run_config.seed == args.seed]
    if not results:
        raise SystemExit("No matching results found.")

    out_dir = Path(args.output_dir) if args.output_dir else Path(args.input_root) / "robustness"
    out_dir.mkdir(parents=True, exist_ok=True)

    per_repeat_path = out_dir / "per_repeat.csv"
    summary_path = out_dir / "summary.csv"

    manifest = build_experiment_manifest(
        workflow="robustness_replay",
        entrypoint="dse/extras/run_robustness.py",
        inputs={
            "input_root": str(Path(args.input_root).resolve()),
            "selected_trials": [
                {
                    "algo": r.run_config.algo,
                    "seed": r.run_config.seed,
                    "base_config_path": r.run_config.base_config_path,
                    "weights_path": r.run_config.weights_path,
                }
                for r in results
            ],
        },
        execution={
            "source": args.source,
            "sort_by": args.sort_by,
            "topk": args.topk,
            "repeats": args.repeats,
            "seed_base": args.seed_base,
            "accuracy_target": args.accuracy_target,
        },
        outputs={
            "output_dir": str(out_dir.resolve()),
            "summary_csv": str(summary_path.resolve()),
            "per_repeat_csv": str(per_repeat_path.resolve()),
        },
        scenario=results[0].run_config.scenario if results else {},
        notes=[
            "This workflow replays selected configurations with deterministic noise seeds.",
            "Current robustness is within-scenario repeated evaluation, not cross-scenario aggregation.",
        ],
    )
    write_json(out_dir / "experiment_manifest.json", manifest)

    per_repeat_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    candidates_per_trial: List[Tuple[Any, List[DSERecord]]] = []
    total_candidates = 0
    for result in results:
        candidates = _choose_candidates(result.records, source=args.source, topk=args.topk, sort_by=args.sort_by)
        candidates_per_trial.append((result, candidates))
        total_candidates += len(candidates)

    if total_candidates == 0:
        raise SystemExit("No candidate configurations selected for robustness evaluation.")

    total_steps = total_candidates * args.repeats
    pbar = try_make_tqdm(total_steps, "[robustness]")
    done = 0
    t_start = time.time()

    for result, candidates in candidates_per_trial:
        rc = result.run_config
        trial_accuracy_target = args.accuracy_target
        if trial_accuracy_target is None:
            trial_accuracy_target = rc.algo_kwargs.get("accuracy_target", None)

        for cand_idx, record in enumerate(candidates, start=1):
            metrics_lat: List[float] = []
            metrics_en: List[float] = []
            metrics_area: List[float] = []
            metrics_power: List[float] = []
            metrics_acc: List[float] = []
            for repeat_idx in range(args.repeats):
                seed_value = args.seed_base + repeat_idx
                random.seed(seed_value)
                np.random.seed(seed_value)
                temp_path = write_temp_config(rc.base_config_path, record.config)
                try:
                    res = evaluate_config(
                        sim_config_path=temp_path,
                        nn_name=rc.nn,
                        weights_path=rc.weights_path,
                        config_values=record.config,
                        run_accuracy=True,
                        enable_saf=rc.enable_saf,
                        enable_variation=rc.enable_variation,
                        enable_rratio=rc.enable_rratio,
                    fixed_qrange=rc.fixed_qrange,
                    device=rc.device,
                    dataset_module=rc.dataset_module,
                    max_acc_batches=rc.max_acc_batches,
                    noise_seed=seed_value,
                )
                finally:
                    os.remove(temp_path)

                done += 1
                postfix = {
                    "algo": rc.algo,
                    "seed": str(rc.seed),
                    "cfg": str(cand_idx),
                    "rep": f"{repeat_idx + 1}/{args.repeats}",
                }
                if res.accuracy is not None:
                    postfix["acc"] = f"{res.accuracy:.4f}"
                update_progress(pbar, tag="[robustness]", done=done, total=total_steps, t_start=t_start, postfix=postfix)

                metrics_lat.append(res.latency_ns)
                metrics_en.append(res.energy_nj)
                metrics_area.append(res.area_um2)
                metrics_power.append(res.power_w)
                if res.accuracy is not None:
                    metrics_acc.append(res.accuracy)

                row: Dict[str, Any] = {
                    "algo": rc.algo,
                    "trial_seed": rc.seed,
                    "candidate_index": cand_idx,
                    "repeat_index": repeat_idx + 1,
                    "noise_seed": seed_value,
                    "latency_ns": res.latency_ns,
                    "energy_nj": res.energy_nj,
                    "area_um2": res.area_um2,
                    "power_w": res.power_w,
                    "accuracy": res.accuracy,
                    "accuracy_violation": accuracy_violation(res.accuracy, trial_accuracy_target),
                }
                for dim, value in record.config.items():
                    row[dim] = encode_dim_value(value)
                per_repeat_rows.append(row)

            acc_mean = float(np.mean(metrics_acc)) if metrics_acc else None
            acc_std = float(np.std(metrics_acc)) if metrics_acc else None
            acc_worst = float(np.min(metrics_acc)) if metrics_acc else None
            yield_value = None
            if metrics_acc and trial_accuracy_target is not None:
                yield_value = float(np.mean([1.0 if a >= float(trial_accuracy_target) else 0.0 for a in metrics_acc]))

            summary_row: Dict[str, Any] = {
                "algo": rc.algo,
                "trial_seed": rc.seed,
                "candidate_index": cand_idx,
                "source": args.source,
                "sort_by": args.sort_by,
                "repeats": args.repeats,
                "mean_latency_ns": float(np.mean(metrics_lat)),
                "mean_energy_nj": float(np.mean(metrics_en)),
                "mean_area_um2": float(np.mean(metrics_area)),
                "mean_power_w": float(np.mean(metrics_power)),
                "mean_accuracy": acc_mean,
                "std_accuracy": acc_std,
                "worst_accuracy": acc_worst,
                "yield": yield_value,
                "accuracy_target": trial_accuracy_target,
            }
            for dim, value in record.config.items():
                summary_row[dim] = encode_dim_value(value)
            summary_rows.append(summary_row)

    if pbar is not None:
        pbar.close()

    per_fields = list(per_repeat_rows[0].keys()) if per_repeat_rows else []
    with open(per_repeat_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=per_fields)
        writer.writeheader()
        for row in per_repeat_rows:
            writer.writerow(row)

    sum_fields = list(summary_rows[0].keys()) if summary_rows else []
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sum_fields)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_root": str(Path(args.input_root).resolve()),
                "source": args.source,
                "sort_by": args.sort_by,
                "topk": args.topk,
                "repeats": args.repeats,
                "seed_base": args.seed_base,
                "algo": args.algo,
                "seed": args.seed,
                "accuracy_target": args.accuracy_target,
                "total_candidates": total_candidates,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"[robustness] summary -> {summary_path}")
    print(f"[robustness] per-repeat -> {per_repeat_path}")


if __name__ == "__main__":
    main()
