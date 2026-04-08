# -*- coding: utf-8 -*-
"""Chinese labels for DSE outputs (CSV/JSON/report/plots). English remains canonical in code."""

from __future__ import annotations

from typing import Any, Dict

# --- history.csv / pareto.csv column headers (same order as HISTORY_HEADER / PARETO_HEADER) ---
HISTORY_COL_ZH: Dict[str, str] = {
    "algo": "算法",
    "seed": "随机种子",
    "eval_index": "评估序号",
    "phase": "阶段",
    "latency_ns": "延迟_ns",
    "energy_nj": "能耗_nJ",
    "area_um2": "面积_um2",
    "power_w": "功耗_W",
    "accuracy": "精度",
    "elapsed_s": "单次耗时_s",
    "is_pareto": "是否帕累托点",
}

PARETO_EXTRA_COL_ZH: Dict[str, str] = {
    "algo": "算法",
    "seed": "随机种子",
    "eval_index": "评估序号",
    "phase": "阶段",
    "latency_ns": "延迟_ns",
    "energy_nj": "能耗_nJ",
    "area_um2": "面积_um2",
    "power_w": "功耗_W",
    "accuracy": "精度",
    "elapsed_s": "单次耗时_s",
}

# design-space dimension short names (keys stay English in cells)
DIM_COL_ZH: Dict[str, str] = {
    "xbar_size": "交叉阵列尺寸",
    "adc_choice": "ADC档位",
    "dac_choice": "DAC档位",
    "pe_num": "PE阵列规模",
    "tile_connection": "Tile连接方式",
    "inter_tile_bw": "片间带宽",
    "intra_tile_bw": "片内带宽",
}

COMPARISON_COL_ZH: Dict[str, str] = {
    "algo": "算法",
    "track": "优化轨道",
    "seed": "随机种子",
    "total_evaluated": "总评估次数",
    "pareto_size": "帕累托解数量",
    "hypervolume": "超体积_HV",
    "hv_ref_lat": "HV参考_延迟",
    "hv_ref_en": "HV参考_能耗",
    "hv_ref_area": "HV参考_面积",
    "best_scalarized_obj": "最优标量目标",
    "best_latency_ns": "最优延迟_ns",
    "best_energy_nj": "最优能耗_nJ",
    "best_area_um2": "最优面积_um2",
    "best_accuracy": "最优精度",
    "wall_time_s": "墙钟时间_s",
}

SUMMARY_COL_ZH: Dict[str, str] = {
    "algo": "算法",
    "track": "优化轨道",
    "n_seeds": "种子数量",
    "mean_hypervolume": "HV均值",
    "std_hypervolume": "HV标准差",
    "mean_pareto_size": "帕累托规模均值",
    "std_pareto_size": "帕累托规模标准差",
    "mean_best_latency_ns": "最优延迟均值_ns",
    "std_best_latency_ns": "最优延迟标准差_ns",
    "mean_best_energy_nj": "最优能耗均值_nJ",
    "std_best_energy_nj": "最优能耗标准差_nJ",
    "mean_best_area_um2": "最优面积均值_um2",
    "std_best_area_um2": "最优面积标准差_um2",
    "mean_wall_time_s": "墙钟时间均值_s",
}


def track_zh(track: str) -> str:
    return "单目标" if track == "single" else "多目标"


def trial_row_zh(row: Dict[str, Any]) -> Dict[str, Any]:
    """Same values as comparison row; Chinese keys for human-readable export."""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        ck = COMPARISON_COL_ZH.get(k, k)
        if k == "track":
            out[ck] = track_zh(str(v)) if v is not None else None
        else:
            out[ck] = v
    return out


def summary_row_zh(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        ck = SUMMARY_COL_ZH.get(k, k)
        if k == "track":
            out[ck] = track_zh(str(v)) if v is not None else None
        else:
            out[ck] = v
    return out
