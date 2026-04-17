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

from dse.contracts import EXPERIMENT_SCHEMA_VERSION
from dse.core import DIM_NAMES, SPACE, decode_dim_value, encode_dim_value
from dse.i18n import (
    COMPARISON_COL_ZH,
    DIM_COL_ZH,
    HISTORY_COL_ZH,
    SUMMARY_COL_ZH,
    summary_row_zh,
    track_zh,
    trial_row_zh,
)


# ---------------------------------------------------------------------------
# Algorithm track
# ---------------------------------------------------------------------------

ALGO_TRACK: Dict[str, str] = {
    "bo_gp": "single",
    "nsga2": "multi",
    "mobo": "multi",
    "random": "multi",
    "matrixcsv": "multi",
}


# ---------------------------------------------------------------------------
# Run configuration (shared across all algorithms)
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    """Everything needed to reproduce one algorithm trial."""
    algo: str                 # "bo_gp" | "nsga2" | "mobo"
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
    max_acc_batches: int = 11
    space_profile: str = "rram_v2"
    contract_version: str = EXPERIMENT_SCHEMA_VERSION
    scenario: Dict[str, Any] = field(default_factory=dict)
    # Algorithm-specific extras (flat dict to keep RunConfig generic)
    algo_kwargs: Dict[str, Any] = field(default_factory=dict)
    # BO+GP: w_latency, w_energy, w_area, two_stage, topk_accuracy,
    #        accuracy_target, accuracy_penalty
    # NSGA-II: population, evals_per_gen
    # MOBO: (no extras)

    # Live DB writing (optional).  Set by run_dse._run_trial before calling run().
    db_path:   str = ""   # path to shared SQLite DB; empty = disabled
    trial_dir: str = ""   # absolute path of this trial's output directory

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


def _col_header_zh(col: str) -> str:
    if col in HISTORY_COL_ZH:
        return HISTORY_COL_ZH[col]
    if col in DIM_COL_ZH:
        return DIM_COL_ZH[col]
    if col == "extra_json":
        return "附加JSON"
    return col


def _history_headers_zh() -> list:
    return [_col_header_zh(c) for c in HISTORY_HEADER]


def _pareto_headers_zh() -> list:
    return [_col_header_zh(c) for c in PARETO_HEADER]


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


def write_history_csv_zh(result: DSERunResult, path: str) -> None:
    """Chinese header row; same data as history.csv."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_history_headers_zh())
        for r in result.records:
            writer.writerow(_record_to_history_row(r))


def write_pareto_csv(result: DSERunResult, path: str) -> None:
    """Write only the Pareto-optimal records to a CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(PARETO_HEADER)
        for r in result.pareto_records:
            writer.writerow(_record_to_pareto_row(r))


def write_pareto_csv_zh(result: DSERunResult, path: str) -> None:
    """Chinese header row; same data as pareto.csv."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_pareto_headers_zh())
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
            "contract_version": cfg.contract_version,
            "nn": cfg.nn,
            "init_evals": cfg.init_evals,
            "weights_path": cfg.weights_path,
            "base_config_path": cfg.base_config_path,
            "run_accuracy": cfg.run_accuracy,
            "enable_saf": cfg.enable_saf,
            "enable_variation": cfg.enable_variation,
            "enable_rratio": cfg.enable_rratio,
            "fixed_qrange": cfg.fixed_qrange,
            "device": cfg.device,
            "dataset_module": cfg.dataset_module,
            "max_acc_batches": cfg.max_acc_batches,
            "space_profile": cfg.space_profile,
            "scenario": cfg.scenario,
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


def write_result_json_zh(result: DSERunResult, path: str) -> None:
    """Same numbers as result.json; top-level keys in Chinese for readability."""
    cfg = result.run_config

    def _best(metric: str) -> Optional[dict]:
        r = result.best_by_metric(metric)
        if r is None:
            return None
        return {
            "数值": getattr(r, metric),
            "评估序号": r.eval_index,
            "配置": {k: encode_dim_value(v) for k, v in r.config.items()},
        }

    payload: Dict[str, Any] = {
        "算法": cfg.algo,
        "优化轨道": track_zh(cfg.track),
        "随机种子": cfg.seed,
        "预算评估次数": cfg.budget,
        "总评估次数": result.total_evaluated,
        "帕累托解数量": result.pareto_size,
        "超体积": result.hypervolume,
        "HV参考点": list(result.hv_reference_point) if result.hv_reference_point else None,
        "墙钟时间_s": result.wall_time_s,
        "开始时间_UTC": result.started_at,
        "结束时间_UTC": result.finished_at,
        "运行配置": {
            "契约版本": cfg.contract_version,
            "网络": cfg.nn,
            "初始化评估": cfg.init_evals,
            "权重路径": cfg.weights_path,
            "基础配置": cfg.base_config_path,
            "启用精度仿真": cfg.run_accuracy,
            "设备": cfg.device,
            "精度评估批次数上限": cfg.max_acc_batches,
            "设计空间配置": cfg.space_profile,
            "场景": cfg.scenario,
            "算法参数": cfg.algo_kwargs,
        },
        "各目标最优": {
            "延迟_ns": _best("latency_ns"),
            "能耗_nJ": _best("energy_nj"),
            "面积_um2": _best("area_um2"),
        },
        "单目标最优": None,
    }

    if cfg.track == "single":
        best_obj = result.best_scalarized_obj()
        if best_obj is not None:
            best_r = min(result.records, key=lambda r: r.extra.get("scalarized_obj", float("inf")))
            payload["单目标最优"] = {
                "标量目标": best_obj,
                "评估序号": best_r.eval_index,
                "配置": {k: encode_dim_value(v) for k, v in best_r.config.items()},
            }

    if cfg.run_accuracy:
        payload["各目标最优"]["精度"] = _best("accuracy")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_all(result: DSERunResult, output_dir: str) -> None:
    """Write history/pareto/result CSV+JSON in English and Chinese variants."""
    os.makedirs(output_dir, exist_ok=True)
    write_history_csv(result, os.path.join(output_dir, "history.csv"))
    write_history_csv_zh(result, os.path.join(output_dir, "history_zh.csv"))
    write_pareto_csv(result, os.path.join(output_dir, "pareto.csv"))
    write_pareto_csv_zh(result, os.path.join(output_dir, "pareto_zh.csv"))
    write_result_json(result, os.path.join(output_dir, "result.json"))
    write_result_json_zh(result, os.path.join(output_dir, "result_zh.json"))


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


def print_report_zh(result: DSERunResult) -> None:
    """中文控制台摘要（与 print_report 数值一致）。"""
    cfg = result.run_config
    tr = track_zh(cfg.track)
    print(f"\n{'='*60}")
    print(f"DSE 结果（中文）: {cfg.algo} （种子={cfg.seed}）")
    print(f"{'='*60}")
    print(f"  优化轨道       : {tr}")
    print(f"  预算           : {cfg.budget}  （初始化={cfg.init_evals}）")
    print(f"  已完成评估     : {result.total_evaluated}")
    print(f"  帕累托解数量   : {result.pareto_size}")
    if result.hypervolume is not None:
        print(f"  超体积 HV      : {result.hypervolume:.4e}")
        ref = result.hv_reference_point
        if ref:
            print(f"  HV 参考点      : 延迟={ref[0]:.3e}  能耗={ref[1]:.3e}  面积={ref[2]:.3e}")
    if cfg.track == "single":
        best_obj = result.best_scalarized_obj()
        if best_obj is not None:
            print(f"  最优标量目标   : {best_obj:.4f}")
    for metric, label in [
        ("latency_ns", "最优延迟"),
        ("energy_nj", "最优能耗"),
        ("area_um2", "最优面积"),
    ]:
        r = result.best_by_metric(metric)
        if r:
            print(f"  {label:<16}: {getattr(r, metric):.4e}")
    if cfg.run_accuracy:
        r = result.best_by_metric("accuracy")
        if r and r.accuracy is not None:
            print(f"  最优精度         : {r.accuracy:.4f}")
    print(f"  墙钟时间       : {result.wall_time_s:.1f}s")
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
    """Write comparison CSV/JSON/report in English and Chinese (*_zh) variants."""
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

    # --- Chinese mirrors (same numbers) ---
    zh_fields = [COMPARISON_COL_ZH[h] for h in COMPARISON_HEADER]
    with open(os.path.join(output_dir, "comparison_zh.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=zh_fields)
        w.writeheader()
        for row in rows:
            w.writerow({COMPARISON_COL_ZH[k]: trial_row_zh(row)[COMPARISON_COL_ZH[k]] for k in COMPARISON_HEADER})

    zh_sum_fields = [SUMMARY_COL_ZH[h] for h in SUMMARY_HEADER]
    with open(os.path.join(output_dir, "comparison_summary_zh.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=zh_sum_fields)
        w.writeheader()
        for row in summary_rows:
            sr = summary_row_zh(row)
            w.writerow({SUMMARY_COL_ZH[k]: sr[SUMMARY_COL_ZH[k]] for k in SUMMARY_HEADER})

    with open(os.path.join(output_dir, "comparison_zh.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "说明": "与 comparison.json 数值一致，键名为中文便于阅读。",
                "试验": [trial_row_zh(r) for r in rows],
                "汇总": [summary_row_zh(r) for r in summary_rows],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    _write_report_txt_zh(summary_rows, rows, os.path.join(output_dir, "report_zh.txt"))


def _write_report_txt_zh(summary_rows, trial_rows, path: str) -> None:
    lines = []
    lines.append("=" * 80)
    lines.append("MNSIM-2.0 DSE 对比报告（中文）")
    lines.append("=" * 80)

    tracks = sorted(set(r["track"] for r in summary_rows))
    for track in tracks:
        track_label = "单目标轨道（BO+GP）" if track == "single" else "多目标轨道（NSGA-II、MOBO）"
        lines.append(f"\n【{track_label}】")
        lines.append("-" * 60)

        track_rows = [r for r in summary_rows if r["track"] == track]

        if track == "single":
            lines.append(
                f"{'算法':<12} {'种子数':>5} {'标量目标均值':>14} {'延迟均值_ns':>14} {'能耗均值_nJ':>12} {'面积均值':>12}"
            )
            for r in track_rows:
                best_obj_rows = [t for t in trial_rows if t["algo"] == r["algo"] and t["best_scalarized_obj"] is not None]
                mean_obj = (
                    sum(t["best_scalarized_obj"] for t in best_obj_rows) / len(best_obj_rows)
                    if best_obj_rows
                    else float("nan")
                )
                lines.append(
                    f"{r['algo']:<12} {r['n_seeds']:>5} {mean_obj:>14.4f} "
                    f"{r['mean_best_latency_ns']:>14.3e} {r['mean_best_energy_nj']:>12.3e} "
                    f"{r['mean_best_area_um2']:>12.3e}"
                )
        else:
            lines.append(
                f"{'算法':<12} {'种子数':>5} {'HV均值':>14} {'HV标准差':>12} {'帕累托规模':>10} {'延迟均值_ns':>14} {'墙钟_s':>8}"
            )
            for r in track_rows:
                hv_mean = r["mean_hypervolume"] if r["mean_hypervolume"] is not None else float("nan")
                hv_std = r["std_hypervolume"] if r["std_hypervolume"] is not None else float("nan")
                psize = r["mean_pareto_size"] if r["mean_pareto_size"] is not None else float("nan")
                lat = r["mean_best_latency_ns"] if r["mean_best_latency_ns"] is not None else float("nan")
                wall = r["mean_wall_time_s"] if r["mean_wall_time_s"] is not None else float("nan")
                lines.append(
                    f"{r['algo']:<12} {r['n_seeds']:>5} {hv_mean:>14.3e} {hv_std:>12.3e} "
                    f"{psize:>10.1f} {lat:>14.3e} {wall:>8.1f}"
                )

    lines.append("\n" + "=" * 80)
    lines.append("说明：")
    lines.append("  - 单目标（bo_gp）：按标量目标比较（越小越好）")
    lines.append("  - 多目标（nsga2、mobo）：按超体积 HV 比较（越大越好）")
    lines.append("  - HV 使用所有试验共享的全局参考点（各目标最大值的 1.1 倍）")
    lines.append("  - 请勿将单目标最优标量与多目标 HV 直接等同对比")
    lines.append("  - 可将各方法的帕累托前沿作为补充对比")
    lines.append("=" * 80)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))


def _write_report_txt(summary_rows, trial_rows, path: str) -> None:
    lines = []
    lines.append("=" * 80)
    lines.append("MNSIM-2.0 DSE Comparison Report")
    lines.append("=" * 80)

    # Group by track
    tracks = sorted(set(r["track"] for r in summary_rows))
    for track in tracks:
        track_label = "Single-Objective Track (BO+GP)" if track == "single" else "Multi-Objective Track (NSGA-II, MOBO)"
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
    lines.append("  - Multi-track (nsga2, mobo): comparison via Hypervolume indicator (higher is better)")
    lines.append("  - HV computed with shared global reference point (max*1.1 across all trials)")
    lines.append("  - Do NOT compare single-track best_obj with multi-track HV directly")
    lines.append("  - You CAN compare Pareto fronts across all methods as a supplementary analysis")
    lines.append("=" * 80)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Also print to stdout
    print("\n".join(lines))
