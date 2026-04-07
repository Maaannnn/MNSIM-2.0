#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified DSE output layer.

Defines the canonical data structures (DSERecord, DSERunResult, RunConfig)
and all file-writing functions. All algorithms produce the same schema.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dse.core import DIM_NAMES, SPACE, decode_dim_value, encode_dim_value


# ---------------------------------------------------------------------------
# Algorithm track
# ---------------------------------------------------------------------------

ALGO_TRACK: Dict[str, str] = {
    "bo_gp": "single",
    "nsga2": "multi",
    "mobo": "multi",
    "random": "multi",  # treated as multi-obj baseline (outputs Pareto)
}


# ---------------------------------------------------------------------------
# Run configuration (shared across all algorithms)
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    """Everything needed to reproduce one algorithm trial."""
    algo: str                 # "bo_gp" | "nsga2" | "mobo" | "random"
    seed: int
    budget: int               # total real evaluations (init + search)
    init_evals: int           # random initialisation count
    nn: str                   # network module name, e.g. "vgg8"
    weights_path: str         # path to .pth weights file
    base_config_path: str     # path to SimConfig.ini
    run_accuracy: bool = False
    enable_saf: bool = True
    enable_variation: bool = False
    enable_rratio: bool = False
    fixed_qrange: bool = False
    device: str = "cpu"
    dataset_module: str = "MNSIM.Interface.cifar10"
    # Algorithm-specific extras (flat dict to keep RunConfig generic)
    algo_kwargs: Dict[str, Any] = field(default_factory=dict)
    # BO+GP: w_latency, w_energy, w_area, two_stage, topk_accuracy,
    #        accuracy_target, accuracy_penalty
    # NSGA-II: population, evals_per_gen
    # MOBO: (no extras)
    # Random: (no extras)

    @property
    def track(self) -> str:
        return ALGO_TRACK.get(self.algo, "multi")


# ---------------------------------------------------------------------------
# Per-evaluation record
# ---------------------------------------------------------------------------

@dataclass
class DSERecord:
    """
    One evaluated hardware configuration — a single row in history.csv.

    Columns are identical across all algorithms to enable unified analysis.
    Algorithm-specific values (e.g. scalarized objective) go into `extra`.
    """
    # --- identity ---
    algo: str
    seed: int
    eval_index: int           # 1-based sequential counter within this trial

    # --- phase label ---
    # Values:
    #   "init"      — random initialisation phase
    #   "bo"        — BO acquisition step (bo_gp)
    #   "gen_N"     — NSGA-II generation N offspring evaluation
    #   "mobo"      — MOBO acquisition step
    #   "random"    — random search
    #   "stage2"    — BO two-stage accuracy re-evaluation
    phase: str

    # --- raw hardware metrics ---
    latency_ns: float
    energy_nj: float
    area_um2: float
    power_w: float
    accuracy: Optional[float]   # None when run_accuracy=False
    elapsed_s: float

    # --- config ---
    config: Dict[str, Any]      # maps DIM_NAMES → values

    # --- Pareto membership (populated post-run, before writing) ---
    is_pareto: bool = False

    # --- algorithm-specific extras (JSON blob in CSV) ---
    extra: Dict[str, Any] = field(default_factory=dict)

    def obj_vector(self) -> Tuple[float, float, float]:
        return (self.latency_ns, self.energy_nj, self.area_um2)


# ---------------------------------------------------------------------------
# Trial result
# ---------------------------------------------------------------------------

@dataclass
class DSERunResult:
    """Complete result of one (algo, seed) trial."""
    run_config: RunConfig
    records: List[DSERecord]                      # all evaluations, in order
    pareto_record_indices: List[int]              # indices into records (Pareto front)
    hypervolume: Optional[float]                  # None for single-track
    hv_reference_point: Optional[Tuple[float, float, float]]
    wall_time_s: float
    started_at: str                               # ISO-8601 UTC string
    finished_at: str

    # Convenience (computed from records)
    @property
    def total_evaluated(self) -> int:
        return len(self.records)

    @property
    def pareto_size(self) -> int:
        return len(self.pareto_record_indices)

    @property
    def pareto_records(self) -> List[DSERecord]:
        return [self.records[i] for i in self.pareto_record_indices]

    def best_by_metric(self, metric: str) -> Optional[DSERecord]:
        """Return the record with the best (min) value for a given metric.
        For accuracy, returns the record with max value.
        """
        valid = [r for r in self.records if getattr(r, metric, None) is not None]
        if not valid:
            return None
        if metric == "accuracy":
            return max(valid, key=lambda r: r.accuracy)
        return min(valid, key=lambda r: getattr(r, metric))

    def best_scalarized_obj(self) -> Optional[float]:
        """For single-track: best scalarized objective stored in extras."""
        vals = [r.extra.get("scalarized_obj") for r in self.records if "scalarized_obj" in r.extra]
        return min(vals) if vals else None


# ---------------------------------------------------------------------------
# CSV header constants
# ---------------------------------------------------------------------------

_CONFIG_COLS = DIM_NAMES  # one column per design dimension

HISTORY_HEADER = (
    ["algo", "seed", "eval_index", "phase"]
    + ["latency_ns", "energy_nj", "area_um2", "power_w", "accuracy", "elapsed_s"]
    + ["is_pareto"]
    + _CONFIG_COLS
    + ["extra_json"]
)

PARETO_HEADER = (
    ["algo", "seed", "eval_index", "phase"]
    + ["latency_ns", "energy_nj", "area_um2", "power_w", "accuracy", "elapsed_s"]
    + _CONFIG_COLS
)


# ---------------------------------------------------------------------------
# File-writing utilities
# ---------------------------------------------------------------------------

def _record_to_history_row(r: DSERecord) -> list:
    row = [
        r.algo,
        r.seed,
        r.eval_index,
        r.phase,
        r.latency_ns,
        r.energy_nj,
        r.area_um2,
        r.power_w,
        "" if r.accuracy is None else r.accuracy,
        r.elapsed_s,
        1 if r.is_pareto else 0,
    ]
    for dim in _CONFIG_COLS:
        row.append(encode_dim_value(r.config.get(dim, "")))
    row.append(json.dumps(r.extra, ensure_ascii=False) if r.extra else "{}")
    return row


def _record_to_pareto_row(r: DSERecord) -> list:
    row = [
        r.algo,
        r.seed,
        r.eval_index,
        r.phase,
        r.latency_ns,
        r.energy_nj,
        r.area_um2,
        r.power_w,
        "" if r.accuracy is None else r.accuracy,
        r.elapsed_s,
    ]
    for dim in _CONFIG_COLS:
        row.append(encode_dim_value(r.config.get(dim, "")))
    return row


def write_history_csv(result: DSERunResult, path: str) -> None:
    """Write the full evaluation history to a unified CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HISTORY_HEADER)
        for r in result.records:
            writer.writerow(_record_to_history_row(r))


def write_pareto_csv(result: DSERunResult, path: str) -> None:
    """Write only the Pareto-optimal records to a CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(PARETO_HEADER)
        for r in result.pareto_records:
            writer.writerow(_record_to_pareto_row(r))


def write_result_json(result: DSERunResult, path: str) -> None:
    """Write a structured result summary to JSON."""
    cfg = result.run_config

    def _best(metric: str) -> Optional[dict]:
        r = result.best_by_metric(metric)
        if r is None:
            return None
        return {
            "value": getattr(r, metric),
            "eval_index": r.eval_index,
            "config": {k: encode_dim_value(v) for k, v in r.config.items()},
        }

    payload: Dict[str, Any] = {
        "algo": cfg.algo,
        "track": cfg.track,
        "seed": cfg.seed,
        "budget": cfg.budget,
        "total_evaluated": result.total_evaluated,
        "pareto_size": result.pareto_size,
        "hypervolume": result.hypervolume,
        "hv_reference_point": list(result.hv_reference_point) if result.hv_reference_point else None,
        "wall_time_s": result.wall_time_s,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "run_config": {
            "nn": cfg.nn,
            "weights_path": cfg.weights_path,
            "base_config_path": cfg.base_config_path,
            "run_accuracy": cfg.run_accuracy,
            "device": cfg.device,
            "algo_kwargs": cfg.algo_kwargs,
        },
        "best_by_objective": {
            "latency_ns": _best("latency_ns"),
            "energy_nj": _best("energy_nj"),
            "area_um2": _best("area_um2"),
        },
        "single_track_best": None,
    }

    if cfg.track == "single":
        best_obj = result.best_scalarized_obj()
        if best_obj is not None:
            best_r = min(result.records, key=lambda r: r.extra.get("scalarized_obj", float("inf")))
            payload["single_track_best"] = {
                "scalarized_obj": best_obj,
                "eval_index": best_r.eval_index,
                "config": {k: encode_dim_value(v) for k, v in best_r.config.items()},
            }

    if cfg.run_accuracy:
        payload["best_by_objective"]["accuracy"] = _best("accuracy")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_all(result: DSERunResult, output_dir: str) -> None:
    """Write history.csv, pareto.csv, and result.json to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    write_history_csv(result, os.path.join(output_dir, "history.csv"))
    write_pareto_csv(result, os.path.join(output_dir, "pareto.csv"))
    write_result_json(result, os.path.join(output_dir, "result.json"))


# ---------------------------------------------------------------------------
# Terminal reporting
# ---------------------------------------------------------------------------

def print_report(result: DSERunResult) -> None:
    """Print a human-readable summary of a DSE run result."""
    cfg = result.run_config
    algo_label = f"{cfg.algo} (seed={cfg.seed})"
    print(f"\n{'='*60}")
    print(f"DSE Result: {algo_label}")
    print(f"{'='*60}")
    print(f"  Track         : {cfg.track}")
    print(f"  Budget        : {cfg.budget}  (init={cfg.init_evals})")
    print(f"  Evaluated     : {result.total_evaluated}")
    print(f"  Pareto size   : {result.pareto_size}")
    if result.hypervolume is not None:
        print(f"  Hypervolume   : {result.hypervolume:.4e}")
        ref = result.hv_reference_point
        if ref:
            print(f"  HV ref point  : lat={ref[0]:.3e}  en={ref[1]:.3e}  area={ref[2]:.3e}")
    if cfg.track == "single":
        best_obj = result.best_scalarized_obj()
        if best_obj is not None:
            print(f"  Best obj (scalar) : {best_obj:.4f}")
    for metric, label in [("latency_ns", "Best latency"), ("energy_nj", "Best energy"), ("area_um2", "Best area")]:
        r = result.best_by_metric(metric)
        if r:
            print(f"  {label:<20}: {getattr(r, metric):.4e}")
    if cfg.run_accuracy:
        r = result.best_by_metric("accuracy")
        if r and r.accuracy is not None:
            print(f"  Best accuracy       : {r.accuracy:.4f}")
    print(f"  Wall time     : {result.wall_time_s:.1f}s")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Comparison utilities (used by run_dse.py after all trials complete)
# ---------------------------------------------------------------------------

COMPARISON_HEADER = [
    "algo", "track", "seed", "total_evaluated",
    "pareto_size", "hypervolume",
    "hv_ref_lat", "hv_ref_en", "hv_ref_area",
    "best_scalarized_obj",
    "best_latency_ns", "best_energy_nj", "best_area_um2", "best_accuracy",
    "wall_time_s",
]

SUMMARY_HEADER = [
    "algo", "track", "n_seeds",
    "mean_hypervolume", "std_hypervolume",
    "mean_pareto_size", "std_pareto_size",
    "mean_best_latency_ns", "std_best_latency_ns",
    "mean_best_energy_nj", "std_best_energy_nj",
    "mean_best_area_um2", "std_best_area_um2",
    "mean_wall_time_s",
]


def write_comparison(results: List[DSERunResult], output_dir: str) -> None:
    """Write comparison.csv, comparison_summary.csv, comparison.json, report.txt."""
    import statistics
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for r in results:
        cfg = r.run_config
        ref = r.hv_reference_point
        best_lat = r.best_by_metric("latency_ns")
        best_en = r.best_by_metric("energy_nj")
        best_area = r.best_by_metric("area_um2")
        best_acc = r.best_by_metric("accuracy") if cfg.run_accuracy else None

        row = {
            "algo": cfg.algo,
            "track": cfg.track,
            "seed": cfg.seed,
            "total_evaluated": r.total_evaluated,
            "pareto_size": r.pareto_size,
            "hypervolume": r.hypervolume,
            "hv_ref_lat": ref[0] if ref else None,
            "hv_ref_en": ref[1] if ref else None,
            "hv_ref_area": ref[2] if ref else None,
            "best_scalarized_obj": r.best_scalarized_obj(),
            "best_latency_ns": best_lat.latency_ns if best_lat else None,
            "best_energy_nj": best_en.energy_nj if best_en else None,
            "best_area_um2": best_area.area_um2 if best_area else None,
            "best_accuracy": best_acc.accuracy if best_acc else None,
            "wall_time_s": r.wall_time_s,
        }
        rows.append(row)

    # comparison.csv
    with open(os.path.join(output_dir, "comparison.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMPARISON_HEADER)
        writer.writeheader()
        writer.writerows(rows)

    # Aggregate by algo
    from collections import defaultdict
    by_algo: Dict[str, list] = defaultdict(list)
    for row in rows:
        by_algo[row["algo"]].append(row)

    def _stats(vals):
        vals2 = [v for v in vals if v is not None]
        if not vals2:
            return None, None
        mean = statistics.mean(vals2)
        std = statistics.stdev(vals2) if len(vals2) > 1 else 0.0
        return mean, std

    summary_rows = []
    for algo, algo_rows in sorted(by_algo.items()):
        track = algo_rows[0]["track"]
        n = len(algo_rows)
        mean_hv, std_hv = _stats([r["hypervolume"] for r in algo_rows])
        mean_psize, std_psize = _stats([r["pareto_size"] for r in algo_rows])
        mean_lat, std_lat = _stats([r["best_latency_ns"] for r in algo_rows])
        mean_en, std_en = _stats([r["best_energy_nj"] for r in algo_rows])
        mean_area, std_area = _stats([r["best_area_um2"] for r in algo_rows])
        mean_wall, _ = _stats([r["wall_time_s"] for r in algo_rows])

        summary_rows.append({
            "algo": algo,
            "track": track,
            "n_seeds": n,
            "mean_hypervolume": mean_hv,
            "std_hypervolume": std_hv,
            "mean_pareto_size": mean_psize,
            "std_pareto_size": std_psize,
            "mean_best_latency_ns": mean_lat,
            "std_best_latency_ns": std_lat,
            "mean_best_energy_nj": mean_en,
            "std_best_energy_nj": std_en,
            "mean_best_area_um2": mean_area,
            "std_best_area_um2": std_area,
            "mean_wall_time_s": mean_wall,
        })

    with open(os.path.join(output_dir, "comparison_summary.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_HEADER)
        writer.writeheader()
        writer.writerows(summary_rows)

    # comparison.json
    with open(os.path.join(output_dir, "comparison.json"), "w", encoding="utf-8") as f:
        json.dump({"trials": rows, "summary": summary_rows}, f, indent=2, ensure_ascii=False)

    # report.txt (ASCII table)
    _write_report_txt(summary_rows, rows, os.path.join(output_dir, "report.txt"))


def _write_report_txt(summary_rows, trial_rows, path: str) -> None:
    lines = []
    lines.append("=" * 80)
    lines.append("MNSIM-2.0 DSE Comparison Report")
    lines.append("=" * 80)

    # Group by track
    tracks = sorted(set(r["track"] for r in summary_rows))
    for track in tracks:
        track_label = "Single-Objective Track (BO+GP)" if track == "single" else "Multi-Objective Track (NSGA-II, MOBO, Random)"
        lines.append(f"\n[{track_label}]")
        lines.append("-" * 60)

        track_rows = [r for r in summary_rows if r["track"] == track]

        if track == "single":
            lines.append(f"{'Algo':<12} {'Seeds':>5} {'BestObj(mean)':>14} {'LatNs(mean)':>14} {'EnNj(mean)':>12} {'Area(mean)':>12}")
            for r in track_rows:
                best_obj_rows = [t for t in trial_rows if t["algo"] == r["algo"] and t["best_scalarized_obj"] is not None]
                mean_obj = sum(t["best_scalarized_obj"] for t in best_obj_rows) / len(best_obj_rows) if best_obj_rows else float("nan")
                lines.append(
                    f"{r['algo']:<12} {r['n_seeds']:>5} {mean_obj:>14.4f} "
                    f"{r['mean_best_latency_ns']:>14.3e} {r['mean_best_energy_nj']:>12.3e} "
                    f"{r['mean_best_area_um2']:>12.3e}"
                )
        else:
            lines.append(f"{'Algo':<12} {'Seeds':>5} {'HV(mean)':>14} {'HV(std)':>12} {'ParetoSz':>9} {'LatNs(mean)':>14} {'Wall(s)':>8}")
            for r in track_rows:
                hv_mean = r['mean_hypervolume'] if r['mean_hypervolume'] is not None else float('nan')
                hv_std = r['std_hypervolume'] if r['std_hypervolume'] is not None else float('nan')
                psize = r['mean_pareto_size'] if r['mean_pareto_size'] is not None else float('nan')
                lat = r['mean_best_latency_ns'] if r['mean_best_latency_ns'] is not None else float('nan')
                wall = r['mean_wall_time_s'] if r['mean_wall_time_s'] is not None else float('nan')
                lines.append(
                    f"{r['algo']:<12} {r['n_seeds']:>5} {hv_mean:>14.3e} {hv_std:>12.3e} "
                    f"{psize:>9.1f} {lat:>14.3e} {wall:>8.1f}"
                )

    lines.append("\n" + "=" * 80)
    lines.append("Notes:")
    lines.append("  - Single-track (bo_gp): comparison via scalarized objective (lower is better)")
    lines.append("  - Multi-track (nsga2, mobo, random): comparison via Hypervolume indicator (higher is better)")
    lines.append("  - HV computed with shared global reference point (max*1.1 across all trials)")
    lines.append("  - Do NOT compare single-track best_obj with multi-track HV directly")
    lines.append("  - You CAN compare Pareto fronts across all methods as a supplementary analysis")
    lines.append("=" * 80)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Also print to stdout
    print("\n".join(lines))
