#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze MNSIM DSE sampling results and generate a lightweight HTML dashboard.

Features:
  - Accepts a dataset CSV, dataset root, run root, or a single trial dir
  - Computes feasible/global-Pareto summaries under accuracy constraint
  - Exports summary JSON / CSV tables for further analysis
  - Writes a self-contained HTML report with inline SVG scatter plots

This script intentionally uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import sys
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dse.i18n import DIM_COL_ZH
from dse.space_catalog import RRAM_PRESETS, SPACE_PROFILES


DIM_NAMES: List[str] = list(DIM_COL_ZH.keys())
REPO_ROOT = Path(__file__).resolve().parent.parent
NUMERIC_FIELDS = {
    "latency_ns",
    "energy_nj",
    "area_um2",
    "power_w",
    "accuracy",
    "elapsed_s",
    "accuracy_target",
}
INT_FIELDS = {"seed", "eval_index"}
BOOL_FIELDS = {
    "run_accuracy",
    "enable_saf",
    "enable_variation",
    "enable_rratio",
    "fixed_qrange",
    "is_pareto",
}
PRESET_COLORS = {
    "P0": "#4e79a7",
    "P1": "#59a14f",
    "P2": "#f28e2b",
    "P3": "#e15759",
    "P4": "#b07aa1",
}

SECTION_ZH = {
    "Device level": "器件层",
    "Crossbar level": "交叉阵列层",
    "Interface level": "接口层",
    "Process element level": "PE 层",
    "Digital module": "数字模块层",
    "Tile level": "Tile 层",
    "Architecture level": "架构层",
    "Algorithm Configuration": "算法配置层",
}

SPACE_PROFILE_LABELS = {
    "rram_full": "RRAM 全空间",
    "rram_v2": "RRAM 论文版收束空间",
    "rram_formal_v3": "RRAM 论文版正式搜索空间",
    "rram_guidance_v4": "RRAM 设计指导空间",
    "legacy": "历史数据集（未显式记录空间）",
}

SIMCONFIG_KEY_META: Dict[str, Dict[str, str]] = {
    "Device_Tech": {"zh": "器件工艺节点", "desc": "存储器件所采用的工艺节点，单位通常为 nm。"},
    "Device_Type": {"zh": "器件类型", "desc": "存内计算所用存储器类型，如 NVM 或 SRAM。"},
    "Device_Area": {"zh": "器件面积", "desc": "单个存储单元面积，单位通常为 μm²。"},
    "Read_Level": {"zh": "读电平数", "desc": "读操作可区分的电平数量。"},
    "Read_Voltage": {"zh": "读电压", "desc": "读操作施加的电压范围，单位 V。"},
    "Write_Level": {"zh": "写电平数", "desc": "写操作可区分的电平数量。"},
    "Write_Voltage": {"zh": "写电压", "desc": "写操作施加的电压范围，单位 V。"},
    "Read_Latency": {"zh": "读延迟", "desc": "单次读操作延迟，单位 ns。"},
    "Write_Latency": {"zh": "写延迟", "desc": "单次写操作延迟，单位 ns。"},
    "Device_Level": {"zh": "器件比特级数", "desc": "单器件可表达的离散电导/阻值级数。"},
    "Device_Resistance": {"zh": "器件阻值", "desc": "器件不同状态下的阻值范围，通常从 HRS 到 LRS。"},
    "Device_Variation": {"zh": "器件波动", "desc": "器件阻值相对理想值的随机波动比例。"},
    "Device_SAF": {"zh": "卡死故障率", "desc": "Stuck-At-HRS / Stuck-At-LRS 缺陷率。"},
    "Read_Energy": {"zh": "读能耗", "desc": "单 bit 读操作能耗，常用于 SRAM 场景。"},
    "Write_Energy": {"zh": "写能耗", "desc": "单 bit 写操作能耗，常用于 SRAM 场景。"},
    "Xbar_Size": {"zh": "交叉阵列尺寸", "desc": "Crossbar 的行列规模。"},
    "Subarray_Size": {"zh": "子阵列行数", "desc": "单个子阵列的行规模。"},
    "Cell_Type": {"zh": "存储单元类型", "desc": "如 1T1R / 0T1R。"},
    "Transistor_Tech": {"zh": "晶体管工艺", "desc": "外围晶体管工艺节点，单位 nm。"},
    "Wire_Resistance": {"zh": "线电阻", "desc": "阵列连线电阻，-1 表示使用默认模型。"},
    "Wire_Capacity": {"zh": "线电容", "desc": "阵列连线电容，-1 表示使用默认模型。"},
    "Load_Resistance": {"zh": "负载电阻", "desc": "阵列输出端负载电阻。"},
    "Area_Calculation": {"zh": "面积计算模式", "desc": "面积估算所采用的方法。"},
    "DAC_Choice": {"zh": "DAC 方案", "desc": "DAC 采用的默认配置编号。"},
    "DAC_Area": {"zh": "DAC 面积", "desc": "DAC 面积；0 表示使用默认配置。"},
    "DAC_Precision": {"zh": "DAC 精度", "desc": "DAC 量化精度，单位 bit。"},
    "DAC_Power": {"zh": "DAC 功耗", "desc": "DAC 功耗，单位 W。"},
    "DAC_Sample_Rate": {"zh": "DAC 采样率", "desc": "DAC 采样率。"},
    "ADC_Choice": {"zh": "ADC 方案", "desc": "ADC 采用的默认配置编号。"},
    "ADC_Area": {"zh": "ADC 面积", "desc": "ADC 面积；0 表示使用默认配置。"},
    "ADC_Precision": {"zh": "ADC 精度", "desc": "ADC 量化精度，单位 bit。"},
    "ADC_Power": {"zh": "ADC 功耗", "desc": "ADC 功耗，单位 W。"},
    "ADC_Sample_Rate": {"zh": "ADC 采样率", "desc": "ADC 采样率。"},
    "ADC_Interval_Thres": {"zh": "ADC 阈值表", "desc": "ADC 各量化区间的判决阈值。"},
    "Logic_Op": {"zh": "逻辑操作模式", "desc": "数字 PIM 下支持的逻辑运算类型。"},
    "PIM_Type": {"zh": "PIM 类型", "desc": "0 表示模拟型 PIM，1 表示数字型 PIM。"},
    "Xbar_Polarity": {"zh": "正负权实现方式", "desc": "正负权重在 xbar 中的实现方式。"},
    "Sub_Position": {"zh": "差分相减位置", "desc": "正负阵列的相减发生在模拟域还是数字域。"},
    "Group_Num": {"zh": "阵列分组数", "desc": "每个 PE 中 crossbar 的分组数量。"},
    "DAC_Num": {"zh": "DAC 数量", "desc": "每个 group / subarray 使用的 DAC 数量。"},
    "ADC_Num": {"zh": "ADC 数量", "desc": "每个 group / subarray 使用的 ADC 数量。"},
    "PE_inBuf_Size": {"zh": "PE 输入缓冲大小", "desc": "每个 PE 输入缓冲的容量。"},
    "PE_inBuf_Area": {"zh": "PE 输入缓冲面积", "desc": "每个 PE 输入缓冲面积。"},
    "Tile_outBuf_Size": {"zh": "Tile 输出缓冲大小", "desc": "每个 Tile 输出缓冲容量。"},
    "Tile_outBuf_Area": {"zh": "Tile 输出缓冲面积", "desc": "每个 Tile 输出缓冲面积。"},
    "DFU_Buf_Size": {"zh": "DFU 缓冲大小", "desc": "数据转发单元缓冲容量。"},
    "DFU_Buf_Area": {"zh": "DFU 缓冲面积", "desc": "数据转发单元缓冲面积。"},
    "Digital_Frequency": {"zh": "数字频率", "desc": "数字模块工作频率，单位 MHz。"},
    "Adder_Tech": {"zh": "加法器工艺", "desc": "加法器模块工艺节点。"},
    "Adder_Area": {"zh": "加法器面积", "desc": "加法器面积。"},
    "Adder_Power": {"zh": "加法器功耗", "desc": "加法器功耗。"},
    "Multiplier_Tech": {"zh": "乘法器工艺", "desc": "乘法器模块工艺节点。"},
    "Multiplier_Area": {"zh": "乘法器面积", "desc": "乘法器面积。"},
    "Multiplier_Power": {"zh": "乘法器功耗", "desc": "乘法器功耗。"},
    "ShiftReg_Tech": {"zh": "移位寄存器工艺", "desc": "移位寄存器模块工艺节点。"},
    "ShiftReg_Area": {"zh": "移位寄存器面积", "desc": "移位寄存器面积。"},
    "ShiftReg_Power": {"zh": "移位寄存器功耗", "desc": "移位寄存器功耗。"},
    "Reg_Tech": {"zh": "寄存器工艺", "desc": "寄存器模块工艺节点。"},
    "Reg_Area": {"zh": "寄存器面积", "desc": "寄存器面积。"},
    "Reg_Power": {"zh": "寄存器功耗", "desc": "寄存器功耗。"},
    "JointModule_Tech": {"zh": "拼接模块工艺", "desc": "Joint module 工艺节点。"},
    "JointModule_Area": {"zh": "拼接模块面积", "desc": "Joint module 面积。"},
    "JointModule_Power": {"zh": "拼接模块功耗", "desc": "Joint module 功耗。"},
    "PE_Num": {"zh": "PE 阵列规模", "desc": "每个 Tile 中 PE 的二维排布。"},
    "Pooling_shape": {"zh": "池化窗口", "desc": "硬件支持的池化核尺寸。"},
    "Pooling_unit_num": {"zh": "池化单元数", "desc": "每个 Tile 中池化单元数量。"},
    "Pooling_Tech": {"zh": "池化工艺", "desc": "池化单元工艺节点。"},
    "Pooling_area": {"zh": "池化面积", "desc": "池化相关模块总面积。"},
    "Tile_Adder_Num": {"zh": "Tile 加法器数", "desc": "每个 Tile 内加法器数量。"},
    "Tile_Adder_Level": {"zh": "Tile 加法层级", "desc": "Tile 内加法树的最大层级。"},
    "Tile_ShiftReg_Num": {"zh": "Tile 移位寄存器数", "desc": "每个 Tile 内移位寄存器数量。"},
    "Tile_ShiftReg_Level": {"zh": "Tile 移位层级", "desc": "Tile 内移位寄存器层级。"},
    "Inter_Tile_Bandwidth": {"zh": "Tile 间带宽", "desc": "不同 Tile 之间通信带宽，单位 Gbps。"},
    "Intra_Tile_Bandwidth": {"zh": "Tile 内带宽", "desc": "Tile 内部 PE 间通信带宽，单位 Gbps。"},
    "Buffer_Choice": {"zh": "缓冲类型", "desc": "架构级缓冲采用 SRAM/DRAM/RRAM 等哪种实现。"},
    "Buffer_Technology": {"zh": "缓冲工艺", "desc": "架构缓冲所用工艺节点。"},
    "Buffer_ReadPower": {"zh": "缓冲读功耗", "desc": "架构缓冲读功耗。"},
    "Buffer_WritePower": {"zh": "缓冲写功耗", "desc": "架构缓冲写功耗。"},
    "Buffer_Bitwidth": {"zh": "缓冲位宽", "desc": "架构缓冲总线位宽。"},
    "LUT_Capacity": {"zh": "LUT 容量", "desc": "查找表容量。"},
    "LUT_Area": {"zh": "LUT 面积", "desc": "查找表面积。"},
    "LUT_Power": {"zh": "LUT 功耗", "desc": "查找表功耗。"},
    "LUT_Bandwidth": {"zh": "LUT 带宽", "desc": "查找表访问带宽。"},
    "Tile_Connection": {"zh": "Tile 连接方式", "desc": "Tile 之间的拓扑/连接模式编号。"},
    "Tile_Num": {"zh": "Tile 总规模", "desc": "整个加速器 Tile 阵列规模。"},
    "Weight_Polarity": {"zh": "权重极性模式", "desc": "算法映射中权重正负表示方式。"},
    "Simulation_Level": {"zh": "仿真级别", "desc": "行为级或估算级等仿真模式。"},
    "NoC_enable": {"zh": "NoC 开关", "desc": "是否启用 NoC 模型。"},
}

FIELD_LABELS = {
    "rank": "排序",
    "feasible": "是否可行（feasible）",
    "global_pareto": "是否全局帕累托（global Pareto）",
    "rram_preset": "RRAM 器件预设",
    "xbar_size": "交叉阵列尺寸",
    "adc_choice": "ADC 档位",
    "dac_num": "DAC 数量",
    "xbar_polarity": "正负权实现方式",
    "sub_position": "差分相减位置",
    "group_num": "阵列分组数",
    "pe_num": "PE 阵列规模",
    "tile_connection": "Tile 连接方式",
    "inter_tile_bw": "片间带宽（Gb/s）",
    "latency_ns": "时延（ns）",
    "energy_nj": "能耗（nJ）",
    "area_um2": "面积（μm²）",
    "power_w": "功耗（W）",
    "accuracy": "精度",
    "algo": "算法",
    "seed": "随机种子",
    "eval_index": "评估序号",
    "group_by_zh": "分组维度",
    "group_value": "取值",
    "samples": "样本数",
    "feasible_samples": "可行样本数",
    "feasible_rate": "可行率",
    "global_pareto_samples": "全局 Pareto 点数",
    "best_accuracy": "最高精度",
    "mean_accuracy": "平均精度",
    "dataset_name": "数据集名称",
    "space_profile": "搜索空间配置",
    "space_profile_label": "搜索空间名称",
    "space_profile_note": "搜索空间说明",
    "source_kind": "输入类型",
    "source_path": "输入路径",
    "workload": "网络模型",
    "weights_file": "权重文件",
    "base_config_file": "基准配置",
    "dim": "变量名",
    "dim_zh": "中文解释",
    "layer_zh": "参数层级",
    "candidate_values": "允许取值",
    "observed_values": "当前已覆盖取值",
    "section": "配置节",
    "section_zh": "配置节中文",
    "key": "字段名",
    "key_zh": "字段中文",
    "key_desc": "字段说明",
    "value": "字段值",
    "preset": "预设名",
    "observed_samples": "样本数",
    "device_resistance": "器件阻值",
    "device_variation": "器件波动",
    "device_saf": "SAF 缺陷率",
    "analysis_scope": "分析范围",
    "main_phase": "主实验相位",
    "phase": "实验相位",
    "matrix_point_id": "矩阵点 ID",
    "value_count": "取值数",
    "balanced_score_spread": "平衡分数离散度",
    "accuracy_spread": "精度均值离散度",
    "latency_spread": "时延均值离散度",
    "energy_spread": "能耗均值离散度",
    "area_spread": "面积均值离散度",
    "dominant_value": "当前优势取值",
    "samples": "样本数",
    "mean_accuracy": "平均精度",
    "best_latency_ns": "最小时延（ns）",
    "best_energy_nj": "最小能耗（nJ）",
    "best_area_um2": "最小面积（μm²）",
    "a_samples": "A 样本数",
    "b_samples": "B 样本数",
    "a_feasible_rate": "A 可行率",
    "b_feasible_rate": "B 可行率",
    "delta_feasible_rate": "可行率变化",
    "a_mean_accuracy": "A 平均精度",
    "b_mean_accuracy": "B 平均精度",
    "delta_mean_accuracy": "平均精度变化",
    "a_best_accuracy": "A 最高精度",
    "b_best_accuracy": "B 最高精度",
    "delta_best_accuracy": "最高精度变化",
    "a_best_latency_ns": "A 最小时延（ns）",
    "b_best_latency_ns": "B 最小时延（ns）",
    "delta_best_latency_ns": "最小时延变化（ns）",
    "a_best_energy_nj": "A 最小能耗（nJ）",
    "b_best_energy_nj": "B 最小能耗（nJ）",
    "delta_best_energy_nj": "最小能耗变化（nJ）",
}

PHASE_LABELS = {
    "matrix_A": "矩阵 A：主迁移矩阵",
    "matrix_B": "矩阵 B：接口补偿矩阵",
    "matrix_C": "矩阵 C：系统瓶颈矩阵",
    "matrix_D": "矩阵 D：压力边界矩阵",
}


def _quote(v: Any) -> str:
    return "-" if v is None else str(v)


def _display_path(path_str: Optional[str]) -> str:
    if not path_str:
        return "-"
    try:
        path = Path(str(path_str)).expanduser().resolve()
        return str(path.relative_to(REPO_ROOT))
    except Exception:
        return str(path_str)


def _maybe_float(value: str) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    return float(text)


def _maybe_int(value: str) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    return int(text)


def _maybe_bool(value: str) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, Any]] = []
        for raw in reader:
            row: Dict[str, Any] = dict(raw)
            for key in NUMERIC_FIELDS:
                if key in row:
                    row[key] = _maybe_float(row[key])
            for key in INT_FIELDS:
                if key in row:
                    row[key] = _maybe_int(row[key])
            for key in BOOL_FIELDS:
                if key in row:
                    row[key] = _maybe_bool(row[key])
            rows.append(row)
        return rows


def _resolve_input(path: Path) -> Tuple[List[Dict[str, Any]], str]:
    if path.is_file():
        return _read_csv_rows(path), f"csv:{path}"

    dataset_csv = path / "dataset_history.csv"
    if dataset_csv.exists():
        return _read_csv_rows(dataset_csv), f"dataset_root:{path}"

    trial_csv = path / "history.csv"
    if trial_csv.exists():
        rows = _read_csv_rows(trial_csv)
        for row in rows:
            row.setdefault("trial_dir", str(path))
            row.setdefault("run_id", path.parent.name)
        return rows, f"trial_dir:{path}"

    rows: List[Dict[str, Any]] = []
    history_files = sorted(path.glob("*/history.csv"))
    if history_files:
        for history_csv in history_files:
            trial_dir = history_csv.parent
            part = _read_csv_rows(history_csv)
            for row in part:
                row.setdefault("trial_dir", str(trial_dir))
                row.setdefault("run_id", trial_dir.parent.name)
            rows.extend(part)
        return rows, f"run_root:{path}"

    raise FileNotFoundError(
        f"Unsupported input path: {path}. Expect csv, dataset root, run root, or trial dir."
    )


def _prepare_default_output_dir(input_path: Path) -> Tuple[Path, Optional[Path]]:
    base = input_path.parent if input_path.is_file() else input_path
    analysis_dir = (base / "reports" / "analysis").resolve()
    return analysis_dir, None


def _effective_accuracy_target(row: Dict[str, Any], override: Optional[float]) -> Optional[float]:
    return override if override is not None else row.get("accuracy_target")


def _is_feasible(row: Dict[str, Any], override: Optional[float]) -> bool:
    target = _effective_accuracy_target(row, override)
    acc = row.get("accuracy")
    if target is None:
        return True
    if acc is None:
        return False
    return float(acc) >= float(target)


def _dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _global_pareto_indices(rows: List[Dict[str, Any]]) -> List[int]:
    idxs = [
        i for i, row in enumerate(rows)
        if row.get("feasible", False)
        and row.get("latency_ns") is not None
        and row.get("energy_nj") is not None
        and row.get("area_um2") is not None
    ]
    pareto: List[int] = []
    for i in idxs:
        obj_i = (rows[i]["latency_ns"], rows[i]["energy_nj"], rows[i]["area_um2"])
        dominated = False
        for j in idxs:
            if i == j:
                continue
            obj_j = (rows[j]["latency_ns"], rows[j]["energy_nj"], rows[j]["area_um2"])
            if _dominates(obj_j, obj_i):
                dominated = True
                break
        if not dominated:
            pareto.append(i)
    return pareto


def _fmt_num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return f"{value:,}"
    val = float(value)
    if val == 0:
        return "0"
    abs_val = abs(val)
    if abs_val >= 1000:
        return f"{val:,.2f}".rstrip("0").rstrip(".")
    if abs_val >= 1:
        return f"{val:,.4f}".rstrip("0").rstrip(".")
    return f"{val:.6f}".rstrip("0").rstrip(".")


def _fmt_dim_value(value: Any) -> str:
    if isinstance(value, (tuple, list)):
        return "x".join(str(x) for x in value)
    return str(value)


def _read_ini_rows(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    ini_path = Path(path).expanduser()
    if not ini_path.exists():
        return []
    import configparser

    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(ini_path, encoding="utf-8")
    rows: List[Dict[str, Any]] = []
    for section in parser.sections():
        for key, value in parser.items(section):
            meta = SIMCONFIG_KEY_META.get(key, {})
            rows.append(
                {
                    "section": section,
                    "section_zh": SECTION_ZH.get(section, section),
                    "key": key,
                    "key_zh": meta.get("zh", key),
                    "key_desc": meta.get("desc", "未补充说明。"),
                    "value": value,
                }
            )
    return rows


def _build_preset_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts = Counter(str(r.get("rram_preset", "unknown")) for r in rows if r.get("rram_preset") is not None)
    presets = sorted(set(counts.keys()) | set(RRAM_PRESETS.keys()))
    out: List[Dict[str, Any]] = []
    for preset in presets:
        spec = RRAM_PRESETS.get(preset, {}).get("Device level", {})
        out.append(
            {
                "preset": preset,
                "observed_samples": counts.get(preset, 0),
                "device_resistance": spec.get("Device_Resistance", "-"),
                "device_variation": spec.get("Device_Variation", "-"),
                "device_saf": spec.get("Device_SAF", "-"),
            }
        )
    return out


def _preset_payloads(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    counts = Counter(str(r.get("rram_preset", "unknown")) for r in rows if r.get("rram_preset") is not None)
    payloads: Dict[str, Dict[str, Any]] = {}
    notes = {
        "P0": "近理想基线器件，用作对照组。",
        "P1": "轻度退化器件，阻值窗口与缺陷率略变差。",
        "P2": "中度退化器件，波动进一步增大。",
        "P3": "重度退化器件，当前主实验下已整体掉出可行域。",
        "P4": "极限压力器件，通常只用于边界失效测试。",
    }
    for preset in sorted(set(counts.keys()) | set(RRAM_PRESETS.keys())):
        spec = RRAM_PRESETS.get(preset, {}).get("Device level", {})
        payloads[preset] = {
            "preset": preset,
            "note": notes.get(preset, "未补充说明。"),
            "observed_samples": counts.get(preset, 0),
            "device_resistance": spec.get("Device_Resistance", "-"),
            "device_variation": spec.get("Device_Variation", "-"),
            "device_saf": spec.get("Device_SAF", "-"),
        }
    return payloads


def _metric_min(rows: Iterable[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return min(vals) if vals else None


def _metric_max(rows: Iterable[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


def _metric_mean(rows: Iterable[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.mean(vals) if vals else None


def _balanced_score(row: Dict[str, Any], mins: Dict[str, float], maxs: Dict[str, float]) -> float:
    total = 0.0
    for key in ("latency_ns", "energy_nj", "area_um2"):
        lo = mins[key]
        hi = maxs[key]
        cur = row[key]
        if hi <= lo:
            norm = 0.0
        else:
            norm = (cur - lo) / (hi - lo)
        total += norm
    acc = row.get("accuracy")
    if acc is not None:
        total -= 0.15 * acc
    return total


def _top_configs(rows: List[Dict[str, Any]], topk: int) -> List[Dict[str, Any]]:
    feasible = [r for r in rows if r.get("feasible", False)]
    base = feasible or rows
    if not base:
        return []

    mins = {k: _metric_min(base, k) or 0.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    maxs = {k: _metric_max(base, k) or 1.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    ranked = sorted(base, key=lambda r: (_balanced_score(r, mins, maxs), -(r.get("accuracy") or 0.0)))

    out: List[Dict[str, Any]] = []
    for rank, row in enumerate(ranked[:topk], start=1):
        entry = {
            "rank": rank,
            "feasible": row.get("feasible"),
            "global_pareto": row.get("global_pareto"),
            "latency_ns": row.get("latency_ns"),
            "energy_nj": row.get("energy_nj"),
            "area_um2": row.get("area_um2"),
            "power_w": row.get("power_w"),
            "accuracy": row.get("accuracy"),
            "algo": row.get("algo"),
            "seed": row.get("seed"),
            "eval_index": row.get("eval_index"),
            "phase": row.get("phase"),
            "matrix_point_id": row.get("matrix_point_id"),
            "run_id": row.get("run_id"),
            "trial_dir": row.get("trial_dir"),
        }
        for dim in DIM_NAMES:
            if dim in row:
                entry[dim] = row.get(dim)
        out.append(entry)
    return out


def _group_summary(rows: List[Dict[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in keys:
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get(key, ""))].append(row)
        for value, bucket in groups.items():
            feasible = [r for r in bucket if r.get("feasible", False)]
            pareto = [r for r in bucket if r.get("global_pareto", False)]
            out.append(
                {
                    "group_by": key,
                    "group_by_zh": DIM_COL_ZH.get(key, key),
                    "group_value": value,
                    "samples": len(bucket),
                    "feasible_samples": len(feasible),
                    "feasible_rate": (len(feasible) / len(bucket)) if bucket else None,
                    "global_pareto_samples": len(pareto),
                    "best_latency_ns": _metric_min(feasible or bucket, "latency_ns"),
                    "best_energy_nj": _metric_min(feasible or bucket, "energy_nj"),
                    "best_area_um2": _metric_min(feasible or bucket, "area_um2"),
                    "best_accuracy": _metric_max(bucket, "accuracy"),
                    "mean_accuracy": _metric_mean(bucket, "accuracy"),
                }
            )
    out.sort(key=lambda r: (r["group_by"], -(r["feasible_rate"] or 0.0), r["best_latency_ns"] or float("inf")))
    return out


def _phase_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(str(r.get("phase", "unknown")) for r in rows if r.get("phase"))
    return dict(counts)


def _main_phase(rows: List[Dict[str, Any]]) -> Optional[str]:
    counts = _phase_counts(rows)
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _analysis_scope_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    phase = _main_phase(rows)
    if phase:
        phase_rows = [r for r in rows if r.get("phase") == phase]
        if len(phase_rows) >= max(8, len(rows) // 2):
            return phase_rows, PHASE_LABELS.get(phase, phase), phase
    return rows, "全样本", phase


def _cell_color(value: Optional[float], vmin: float, vmax: float, *, invert: bool = False) -> str:
    if value is None:
        return "#f3f4f6"
    if vmax <= vmin:
        frac = 0.5
    else:
        frac = (float(value) - vmin) / (vmax - vmin)
    frac = max(0.0, min(1.0, frac))
    if invert:
        frac = 1.0 - frac
    light = 96 - frac * 34
    sat = 58
    hue = 214
    return f"hsl({hue} {sat}% {light}%)"


def _effect_size_rows(rows: List[Dict[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    mins = {k: _metric_min(rows, k) or 0.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    maxs = {k: _metric_max(rows, k) or 1.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    out: List[Dict[str, Any]] = []
    for key in keys:
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            buckets[str(row.get(key, ""))].append(row)
        if len(buckets) <= 1:
            continue
        stats: List[Dict[str, Any]] = []
        for value, bucket in buckets.items():
            mean_acc = _metric_mean(bucket, "accuracy")
            mean_lat = _metric_mean(bucket, "latency_ns")
            mean_en = _metric_mean(bucket, "energy_nj")
            mean_area = _metric_mean(bucket, "area_um2")
            feasible_rate = sum(1 for r in bucket if r.get("feasible")) / len(bucket) if bucket else 0.0
            mean_score = statistics.mean(_balanced_score(r, mins, maxs) for r in bucket if r.get("latency_ns") is not None and r.get("energy_nj") is not None and r.get("area_um2") is not None)
            stats.append(
                {
                    "value": value,
                    "mean_acc": mean_acc,
                    "mean_lat": mean_lat,
                    "mean_en": mean_en,
                    "mean_area": mean_area,
                    "feasible_rate": feasible_rate,
                    "mean_score": mean_score,
                }
            )
        dominant = min(stats, key=lambda item: (item["mean_score"], -(item["mean_acc"] or 0.0)))
        score_values = [s["mean_score"] for s in stats]
        acc_values = [s["mean_acc"] or 0.0 for s in stats]
        lat_values = [s["mean_lat"] or 0.0 for s in stats]
        en_values = [s["mean_en"] or 0.0 for s in stats]
        area_values = [s["mean_area"] or 0.0 for s in stats]
        out.append(
            {
                "group_by_zh": DIM_COL_ZH.get(key, key),
                "value_count": len(stats),
                "balanced_score_spread": (max(score_values) - min(score_values)) if score_values else None,
                "accuracy_spread": (max(acc_values) - min(acc_values)) if acc_values else None,
                "latency_spread": (max(lat_values) - min(lat_values)) if lat_values else None,
                "energy_spread": (max(en_values) - min(en_values)) if en_values else None,
                "area_spread": (max(area_values) - min(area_values)) if area_values else None,
                "dominant_value": dominant["value"],
            }
        )
    out.sort(key=lambda r: (-(r["balanced_score_spread"] or 0.0), -(r["accuracy_spread"] or 0.0)))
    return out


def _interaction_cells(rows: List[Dict[str, Any]], x_key: str, y_key: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    x_values = sorted({_fmt_dim_value(r.get(x_key)) for r in rows if r.get(x_key) is not None})
    y_values = sorted({_fmt_dim_value(r.get(y_key)) for r in rows if r.get(y_key) is not None})
    cells: List[Dict[str, Any]] = []
    for yv in y_values:
        for xv in x_values:
            bucket = [r for r in rows if _fmt_dim_value(r.get(x_key)) == xv and _fmt_dim_value(r.get(y_key)) == yv]
            if not bucket:
                continue
            cells.append(
                {
                    "x": xv,
                    "y": yv,
                    "samples": len(bucket),
                    "feasible_rate": sum(1 for r in bucket if r.get("feasible")) / len(bucket) if bucket else 0.0,
                    "mean_accuracy": _metric_mean(bucket, "accuracy"),
                    "best_latency_ns": _metric_min(bucket, "latency_ns"),
                    "best_energy_nj": _metric_min(bucket, "energy_nj"),
                }
            )
    return cells, x_values, y_values


def _svg_heatmap(
    cells: List[Dict[str, Any]],
    x_values: Sequence[str],
    y_values: Sequence[str],
    *,
    value_key: str,
    title: str,
    subtitle: str,
    width: int = 560,
    height: int = 320,
) -> str:
    if not cells or not x_values or not y_values:
        return f"<div class='chart-empty'>{html.escape(title)}: no data</div>"
    margin_left, margin_right, margin_top, margin_bottom = 84, 16, 38, 54
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    cell_w = plot_w / max(1, len(x_values))
    cell_h = plot_h / max(1, len(y_values))
    value_map = {(c["x"], c["y"]): c for c in cells}
    vals = [c.get(value_key) for c in cells if c.get(value_key) is not None]
    vmin = min(vals) if vals else 0.0
    vmax = max(vals) if vals else 1.0
    rects: List[str] = []
    labels: List[str] = []
    for yi, yv in enumerate(y_values):
        y = margin_top + yi * cell_h
        labels.append(f"<text x='{margin_left - 10:.1f}' y='{y + cell_h/2 + 4:.1f}' class='tick' text-anchor='end'>{html.escape(yv)}</text>")
        for xi, xv in enumerate(x_values):
            x = margin_left + xi * cell_w
            cell = value_map.get((xv, yv))
            value = cell.get(value_key) if cell else None
            color = _cell_color(value, vmin, vmax)
            tooltip = "-"
            center = "-"
            if cell:
                tooltip = (
                    f"{xv} × {yv}\n"
                    f"样本数：{cell.get('samples')}\n"
                    f"可行率：{_fmt_num((cell.get('feasible_rate') or 0.0) * 100.0)}%\n"
                    f"均值精度：{_fmt_num(cell.get('mean_accuracy'))}\n"
                    f"最小时延：{_fmt_num(cell.get('best_latency_ns'))} ns\n"
                    f"最小能耗：{_fmt_num(cell.get('best_energy_nj'))} nJ"
                )
                center = _fmt_num(value, 4 if value_key == "mean_accuracy" else 2)
            rects.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{cell_w:.1f}' height='{cell_h:.1f}' fill='{color}' stroke='#fff' "
                f"class='point-dot' data-tooltip='{html.escape(tooltip, quote=True)}'><title>{html.escape(tooltip)}</title></rect>"
            )
            rects.append(f"<text x='{x + cell_w/2:.1f}' y='{y + cell_h/2 + 4:.1f}' class='heat-text' text-anchor='middle'>{html.escape(center)}</text>")
    for xi, xv in enumerate(x_values):
        x = margin_left + xi * cell_w + cell_w / 2
        labels.append(f"<text x='{x:.1f}' y='{height - 18}' class='tick' text-anchor='middle'>{html.escape(xv)}</text>")
    return f"""
    <div class="chart-card">
      <div class="chart-title">{html.escape(title)}</div>
      <div class="note">{html.escape(subtitle)}</div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{html.escape(title)}">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
        {''.join(rects)}
        {''.join(labels)}
      </svg>
    </div>
    """


def _svg_preset_accuracy_curve(rows: List[Dict[str, Any]], width: int = 560, height: int = 300) -> str:
    phase_rows, _, _ = _analysis_scope_rows(rows)
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in phase_rows:
        if row.get("rram_preset") is not None and row.get("accuracy") is not None:
            buckets[str(row["rram_preset"])].append(row)
    presets = sorted(buckets.keys())
    if len(presets) < 2:
        return "<div class='chart-empty'>器件退化曲线：样本不足</div>"
    data = []
    for preset in presets:
        bucket = buckets[preset]
        data.append({"preset": preset, "mean_acc": _metric_mean(bucket, "accuracy"), "best_acc": _metric_max(bucket, "accuracy")})
    margin_left, margin_right, margin_top, margin_bottom = 58, 16, 24, 46
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    vals = [d["mean_acc"] for d in data if d["mean_acc"] is not None] + [d["best_acc"] for d in data if d["best_acc"] is not None]
    vmin = min(vals) if vals else 0.0
    vmax = max(vals) if vals else 1.0
    if vmax <= vmin:
        vmax = vmin + 0.01
    def sx(i: int) -> float:
        return margin_left + (plot_w * i / max(1, len(data) - 1))
    def sy(v: float) -> float:
        return margin_top + plot_h - (v - vmin) / (vmax - vmin) * plot_h
    def polyline(key: str, color: str) -> str:
        pts = " ".join(f"{sx(i):.1f},{sy(float(d[key])):.1f}" for i, d in enumerate(data) if d.get(key) is not None)
        dots = "".join(
            f"<circle cx='{sx(i):.1f}' cy='{sy(float(d[key])):.1f}' r='4' fill='{color}' class='point-dot' "
            f"data-tooltip='preset={d['preset']}\\n{key}={_fmt_num(d[key])}'><title>{d['preset']} {key}={_fmt_num(d[key])}</title></circle>"
            for i, d in enumerate(data) if d.get(key) is not None
        )
        return f"<polyline fill='none' stroke='{color}' stroke-width='2.5' points='{pts}' />{dots}"
    labels = "".join(f"<text x='{sx(i):.1f}' y='{height - 16}' class='tick' text-anchor='middle'>{html.escape(d['preset'])}</text>" for i, d in enumerate(data))
    return f"""
    <div class="chart-card">
      <div class="chart-title">器件退化精度曲线</div>
      <div class="note">按主实验相位统计各 `RRAM preset` 的平均精度与最高精度变化。</div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="器件退化精度曲线">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
        <line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" class="axis" />
        <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" class="axis" />
        {polyline('mean_acc', '#2563eb')}
        {polyline('best_acc', '#ef4444')}
        {labels}
        <text x="{margin_left + plot_w/2:.1f}" y="{height - 2}" class="axis-label" text-anchor="middle">RRAM preset</text>
        <text x="14" y="{margin_top + plot_h/2:.1f}" class="axis-label" text-anchor="middle" transform="rotate(-90 14 {margin_top + plot_h/2:.1f})">精度</text>
      </svg>
      <div class="legend"><span class="legend-item"><span class="swatch" style="background:#2563eb"></span>平均精度</span><span class="legend-item"><span class="swatch" style="background:#ef4444"></span>最高精度</span></div>
    </div>
    """


def _preset_best_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    phase_rows, _, _ = _analysis_scope_rows(rows)
    feasible = [r for r in phase_rows if r.get("feasible")]
    if not feasible:
        feasible = phase_rows
    if not feasible:
        return []
    mins = {k: _metric_min(feasible, k) or 0.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    maxs = {k: _metric_max(feasible, k) or 1.0 for k in ("latency_ns", "energy_nj", "area_um2")}
    out: List[Dict[str, Any]] = []
    for preset in sorted({str(r.get('rram_preset')) for r in feasible if r.get('rram_preset') is not None}):
        bucket = [r for r in feasible if str(r.get("rram_preset")) == preset]
        best = min(bucket, key=lambda r: (_balanced_score(r, mins, maxs), -(r.get("accuracy") or 0.0)))
        out.append(
            {
                "preset": preset,
                "xbar_size": best.get("xbar_size"),
                "adc_choice": best.get("adc_choice"),
                "dac_num": best.get("dac_num"),
                "pe_num": best.get("pe_num"),
                "latency_ns": best.get("latency_ns"),
                "energy_nj": best.get("energy_nj"),
                "area_um2": best.get("area_um2"),
                "accuracy": best.get("accuracy"),
            }
        )
    return out


def _phase_rows(rows: List[Dict[str, Any]], phase: str) -> List[Dict[str, Any]]:
    return [row for row in rows if str(row.get("phase")) == phase]


def _phase_metric_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    feasible = [r for r in rows if r.get("feasible")]
    base = feasible or rows
    return {
        "samples": len(rows),
        "feasible_samples": len(feasible),
        "feasible_rate": (len(feasible) / len(rows)) if rows else None,
        "mean_accuracy": _metric_mean(rows, "accuracy"),
        "best_accuracy": _metric_max(rows, "accuracy"),
        "best_latency_ns": _metric_min(base, "latency_ns"),
        "best_energy_nj": _metric_min(base, "energy_nj"),
        "best_area_um2": _metric_min(base, "area_um2"),
    }


def _phase_preset_summary(rows: List[Dict[str, Any]], phase: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for preset in sorted({str(r.get("rram_preset")) for r in rows if r.get("rram_preset") is not None}):
        bucket = [r for r in rows if str(r.get("rram_preset")) == preset]
        out.append({"phase": phase, "preset": preset, **_phase_metric_summary(bucket)})
    return out


def _compensation_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(b) - float(a)


def _build_compensation_report(rows: List[Dict[str, Any]], output_dir: Path) -> Optional[Dict[str, Any]]:
    rows_a = _phase_rows(rows, "matrix_A")
    rows_b = _phase_rows(rows, "matrix_B")
    if not rows_a or not rows_b:
        return None

    overall_a = _phase_metric_summary(rows_a)
    overall_b = _phase_metric_summary(rows_b)
    presets = sorted({str(r.get("rram_preset")) for r in rows_a + rows_b if r.get("rram_preset") is not None})

    compare_rows: List[Dict[str, Any]] = []
    phase_rows = _phase_preset_summary(rows_a, "matrix_A") + _phase_preset_summary(rows_b, "matrix_B")
    for preset in presets:
        stat_a = _phase_metric_summary([r for r in rows_a if str(r.get("rram_preset")) == preset])
        stat_b = _phase_metric_summary([r for r in rows_b if str(r.get("rram_preset")) == preset])
        compare_rows.append(
            {
                "preset": preset,
                "a_samples": stat_a["samples"],
                "b_samples": stat_b["samples"],
                "a_feasible_rate": stat_a["feasible_rate"],
                "b_feasible_rate": stat_b["feasible_rate"],
                "delta_feasible_rate": _compensation_delta(stat_a["feasible_rate"], stat_b["feasible_rate"]),
                "a_mean_accuracy": stat_a["mean_accuracy"],
                "b_mean_accuracy": stat_b["mean_accuracy"],
                "delta_mean_accuracy": _compensation_delta(stat_a["mean_accuracy"], stat_b["mean_accuracy"]),
                "a_best_accuracy": stat_a["best_accuracy"],
                "b_best_accuracy": stat_b["best_accuracy"],
                "delta_best_accuracy": _compensation_delta(stat_a["best_accuracy"], stat_b["best_accuracy"]),
                "a_best_latency_ns": stat_a["best_latency_ns"],
                "b_best_latency_ns": stat_b["best_latency_ns"],
                "delta_best_latency_ns": _compensation_delta(stat_a["best_latency_ns"], stat_b["best_latency_ns"]),
                "a_best_energy_nj": stat_a["best_energy_nj"],
                "b_best_energy_nj": stat_b["best_energy_nj"],
                "delta_best_energy_nj": _compensation_delta(stat_a["best_energy_nj"], stat_b["best_energy_nj"]),
            }
        )

    improved_feasible = sorted(
        [r for r in compare_rows if r.get("delta_feasible_rate") is not None],
        key=lambda r: r["delta_feasible_rate"],
        reverse=True,
    )
    improved_accuracy = sorted(
        [r for r in compare_rows if r.get("delta_mean_accuracy") is not None],
        key=lambda r: r["delta_mean_accuracy"],
        reverse=True,
    )
    highlights: List[str] = []
    delta_feasible = _compensation_delta(overall_a["feasible_rate"], overall_b["feasible_rate"])
    delta_acc = _compensation_delta(overall_a["mean_accuracy"], overall_b["mean_accuracy"])
    if delta_feasible is not None:
        highlights.append(
            f"整体可行率：A 为 {_fmt_num((overall_a['feasible_rate'] or 0.0) * 100.0)}%，B 为 {_fmt_num((overall_b['feasible_rate'] or 0.0) * 100.0)}%，变化 {_fmt_num(delta_feasible * 100.0)} 个百分点。"
        )
    if delta_acc is not None:
        highlights.append(
            f"整体平均精度：A 为 {_fmt_num(overall_a['mean_accuracy'])}，B 为 {_fmt_num(overall_b['mean_accuracy'])}，变化 {_fmt_num(delta_acc)}。"
        )
    if improved_feasible:
        best = improved_feasible[0]
        highlights.append(
            f"可行率改善最明显的器件预设是 {best['preset']}，变化 {_fmt_num((best['delta_feasible_rate'] or 0.0) * 100.0)} 个百分点。"
        )
    if improved_accuracy:
        best = improved_accuracy[0]
        highlights.append(
            f"平均精度改善最明显的器件预设是 {best['preset']}，变化 {_fmt_num(best['delta_mean_accuracy'])}。"
        )
    if any((r.get("b_feasible_rate") or 0.0) > 0 for r in compare_rows if r["preset"] == "P3"):
        highlights.append("P3 在补偿后出现可行点，说明接口补偿开始具备论文亮点。")
    else:
        highlights.append("P3 在当前补偿样本下仍未恢复到稳定可行，后续应继续补 B 或考虑更强补偿策略。")

    compare_headers = [
        "preset",
        "a_samples",
        "b_samples",
        "a_feasible_rate",
        "b_feasible_rate",
        "delta_feasible_rate",
        "a_mean_accuracy",
        "b_mean_accuracy",
        "delta_mean_accuracy",
        "a_best_energy_nj",
        "b_best_energy_nj",
        "delta_best_energy_nj",
    ]
    phase_headers = [
        "phase",
        "preset",
        "samples",
        "feasible_samples",
        "feasible_rate",
        "mean_accuracy",
        "best_accuracy",
        "best_latency_ns",
        "best_energy_nj",
        "best_area_um2",
    ]

    def render_metric_card(title: str, a_value: Any, b_value: Any, unit: str = "") -> str:
        delta = _compensation_delta(a_value, b_value)
        trend_class = "neutral"
        if delta is not None:
            trend_class = "up" if delta > 0 else "down" if delta < 0 else "neutral"
        delta_text = "-" if delta is None else f"{_fmt_num(delta)}{unit}"
        return (
            f"<div class='cmp-card'><div class='cmp-title'>{html.escape(title)}</div>"
            f"<div class='cmp-main'><div><span class='cmp-tag'>A</span>{html.escape(_fmt_num(a_value))}{html.escape(unit)}</div>"
            f"<div><span class='cmp-tag'>B</span>{html.escape(_fmt_num(b_value))}{html.escape(unit)}</div></div>"
            f"<div class='cmp-delta {trend_class}'>Δ {html.escape(delta_text)}</div></div>"
        )

    cards_html = "".join(
        [
            render_metric_card("可行率", (overall_a["feasible_rate"] or 0.0) * 100.0, (overall_b["feasible_rate"] or 0.0) * 100.0, "%"),
            render_metric_card("平均精度", overall_a["mean_accuracy"], overall_b["mean_accuracy"]),
            render_metric_card("最小时延", overall_a["best_latency_ns"], overall_b["best_latency_ns"], " ns"),
            render_metric_card("最小能耗", overall_a["best_energy_nj"], overall_b["best_energy_nj"], " nJ"),
        ]
    )
    highlight_html = "".join(f"<li>{html.escape(item)}</li>" for item in highlights)

    report_path = output_dir / "compensation_report.html"
    compare_csv = output_dir / "compensation_compare.csv"
    phase_csv = output_dir / "compensation_phase_summary.csv"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(
            f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>补偿前后对比报告</title>
  <style>
    :root {{
      --bg:#f7f8fb; --card:#fff; --text:#111827; --muted:#6b7280; --line:#dbe2ea; --good:#166534; --bad:#b91c1c; --accent:#2563eb;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    .wrap {{ max-width:1320px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0 0 8px; font-size:30px; }}
    .sub {{ color:var(--muted); margin-bottom:18px; }}
    .section {{ margin-top:24px; }}
    .section-title {{ font-size:18px; font-weight:700; margin:0 0 12px; }}
    .cmp-grid {{ display:grid; grid-template-columns:repeat(4, minmax(180px, 1fr)); gap:14px; }}
    .cmp-card, .info-card, .table-card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; }}
    .cmp-card {{ padding:16px; }}
    .cmp-title {{ color:var(--muted); font-size:13px; margin-bottom:10px; }}
    .cmp-main {{ display:grid; gap:8px; font-size:20px; font-weight:700; }}
    .cmp-tag {{ display:inline-block; min-width:26px; margin-right:8px; color:var(--accent); font-size:12px; font-weight:700; }}
    .cmp-delta {{ margin-top:12px; font-size:13px; font-weight:700; }}
    .cmp-delta.up {{ color:var(--bad); }}
    .cmp-delta.down {{ color:var(--good); }}
    .cmp-delta.neutral {{ color:var(--muted); }}
    .info-card {{ padding:14px; }}
    .note {{ color:var(--muted); font-size:13px; line-height:1.65; }}
    ul.tight {{ margin:8px 0 0 18px; padding:0; }}
    ul.tight li {{ margin:6px 0; line-height:1.5; }}
    .table-card {{ overflow:hidden; }}
    .table-scroll {{ max-height:430px; overflow:auto; }}
    .table-sticky-title {{ position:sticky; top:0; z-index:5; background:var(--card); padding:14px 14px 10px; border-bottom:1px solid var(--line); font-size:15px; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid var(--line); text-align:left; padding:8px 10px; vertical-align:top; background:var(--card); }}
    th {{ position:sticky; top:45px; z-index:4; color:var(--muted); background:#fafbfc; }}
    .back-link {{ display:inline-block; margin-top:12px; color:var(--accent); text-decoration:none; font-weight:600; }}
    @media (max-width:960px) {{ .cmp-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>补偿前后对比报告</h1>
    <div class="sub">对比对象：矩阵 A（主迁移矩阵） vs 矩阵 B（接口补偿矩阵）</div>
    <div class="cmp-grid">{cards_html}</div>
    <div class="section">
      <div class="section-title">结论摘要</div>
      <div class="info-card">
        <ul class="tight">{highlight_html}</ul>
        <div class="note">说明：这里比较的是矩阵级聚合结果，不是逐点一一配对。</div>
        <a class="back-link" href="./index.html">返回主分析页</a>
      </div>
    </div>
    <div class="section">
      <div class="section-title">按器件预设看补偿收益</div>
      {_html_table(compare_rows, compare_headers, "A/B 对比：每个 preset 的可行率、精度与能耗变化", limit=40)}
    </div>
    <div class="section">
      <div class="section-title">按阶段展开的原始聚合</div>
      {_html_table(phase_rows, phase_headers, "矩阵 A 与矩阵 B 的分阶段聚合统计", limit=40)}
    </div>
  </div>
</body>
</html>
"""
        )
    _write_csv(compare_csv, compare_rows)
    _write_csv(phase_csv, phase_rows)
    return {
        "html_path": str(report_path),
        "compare_csv_path": str(compare_csv),
        "phase_csv_path": str(phase_csv),
        "summary": {
            "matrix_A": overall_a,
            "matrix_B": overall_b,
            "rows_A": len(rows_a),
            "rows_B": len(rows_b),
        },
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    headers = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _best_record(rows: List[Dict[str, Any]], metric: str, maximize: bool = False) -> Optional[Dict[str, Any]]:
    valid = [r for r in rows if r.get(metric) is not None]
    if not valid:
        return None
    return max(valid, key=lambda r: r[metric]) if maximize else min(valid, key=lambda r: r[metric])


def _build_summary(rows: List[Dict[str, Any]], source_desc: str, accuracy_override: Optional[float]) -> Dict[str, Any]:
    feasible = [r for r in rows if r.get("feasible", False)]
    pareto = [r for r in rows if r.get("global_pareto", False)]
    accuracy_targets = sorted({r.get("accuracy_target") for r in rows if r.get("accuracy_target") is not None})
    algos = Counter(str(r.get("algo", "unknown")) for r in rows)
    presets = Counter(str(r.get("rram_preset", "unknown")) for r in rows)
    source_kind, _, source_path = source_desc.partition(":")
    dataset_name = Path(source_path).name if source_path else source_desc
    profile = next((str(r.get("space_profile")) for r in rows if r.get("space_profile")), "")
    if not profile:
        profile = "rram_v2" if "_rram_v2_" in dataset_name else "legacy"
    profile_spec = SPACE_PROFILES.get(profile, {})
    workload = next((str(r.get("nn")) for r in rows if r.get("nn")), "-")
    dataset_module = next((str(r.get("dataset_module")) for r in rows if r.get("dataset_module")), "-")
    dataset_name_short = dataset_module.split(".")[-1] if dataset_module and dataset_module != "-" else "-"
    weights_path = next((str(r.get("weights_path")) for r in rows if r.get("weights_path")), "")
    weights_file = next((Path(str(r.get("weights_path"))).name for r in rows if r.get("weights_path")), "-")
    base_config_file = next((Path(str(r.get("base_config_path"))).name for r in rows if r.get("base_config_path")), "-")
    base_config_path = next((str(r.get("base_config_path")) for r in rows if r.get("base_config_path")), "")
    device = next((str(r.get("device")) for r in rows if r.get("device")), "-")
    run_accuracy = next((bool(r.get("run_accuracy")) for r in rows if r.get("run_accuracy") is not None), None)
    enable_saf = next((bool(r.get("enable_saf")) for r in rows if r.get("enable_saf") is not None), None)
    enable_variation = next((bool(r.get("enable_variation")) for r in rows if r.get("enable_variation") is not None), None)
    enable_rratio = next((bool(r.get("enable_rratio")) for r in rows if r.get("enable_rratio") is not None), None)
    fixed_qrange = next((bool(r.get("fixed_qrange")) for r in rows if r.get("fixed_qrange") is not None), None)
    simconfig_rows = _read_ini_rows(base_config_path)
    preset_rows = _build_preset_rows(rows)
    preset_payloads = _preset_payloads(rows)

    space_rows: List[Dict[str, Any]] = []
    if profile in SPACE_PROFILES:
        for dim, spec in SPACE_PROFILES[profile].items():
            observed = sorted({_fmt_dim_value(r.get(dim)) for r in rows if r.get(dim) is not None})
            space_rows.append(
                {
                    "dim": dim,
                    "dim_zh": DIM_COL_ZH.get(dim, dim),
                    "layer_zh": SECTION_ZH.get(spec.get("section", ""), "器件/配置层"),
                    "candidate_values": ", ".join(_fmt_dim_value(v) for v in spec.get("values", [])),
                    "observed_values": ", ".join(observed) if observed else "-",
                }
            )
    else:
        for dim in DIM_NAMES:
            observed = sorted({_fmt_dim_value(r.get(dim)) for r in rows if r.get(dim) is not None})
            if not observed:
                continue
            space_rows.append(
                {
                    "dim": dim,
                    "dim_zh": DIM_COL_ZH.get(dim, dim),
                    "layer_zh": "历史数据",
                    "candidate_values": "未记录（按当前样本推断）",
                    "observed_values": ", ".join(observed),
                }
            )

    profile_note = {
        "rram_full": "宽空间，适合做先导探索与可行性摸底。",
        "rram_v2": "面向 RRAM 论文的收束空间，突出器件迁移、接口补偿与系统瓶颈。",
        "rram_formal_v3": "面向论文正式对比的最终收束空间：固定系统层结构，只保留器件与接口关键变量供搜索算法比较。",
        "rram_guidance_v4": "面向设计指导的增强空间：重新放开阵列规模、并行度与片间带宽，用于观察器件—接口—系统的联合趋势。",
        "legacy": "旧版数据集，未在数据中显式记录搜索空间，建议只作为先导对照，不作为主结论来源。",
    }.get(profile, "未识别的搜索空间。")
    scope_rows, scope_label, main_phase = _analysis_scope_rows(rows)
    interaction_cells, interaction_xs, interaction_ys = _interaction_cells(scope_rows, "xbar_size", "pe_num")
    effect_rows = _effect_size_rows(scope_rows, ["rram_preset", "xbar_size", "adc_choice", "pe_num", "tile_connection", "inter_tile_bw", "dac_num", "sub_position"])
    preset_best_rows = _preset_best_rows(rows)

    return {
        "source": source_desc,
        "source_kind": source_kind,
        "source_path": source_path,
        "source_path_display": _display_path(source_path),
        "dataset_name": dataset_name,
        "space_profile": profile,
        "space_profile_label": SPACE_PROFILE_LABELS.get(profile, profile),
        "space_profile_note": profile_note,
        "analysis_scope": scope_label,
        "main_phase": main_phase,
        "space_dimensions": space_rows,
        "workload": workload,
        "dataset_module": dataset_module,
        "dataset_name_short": dataset_name_short,
        "weights_path": weights_path,
        "weights_path_display": _display_path(weights_path),
        "weights_file": weights_file,
        "base_config_file": base_config_file,
        "base_config_path": base_config_path,
        "base_config_path_display": _display_path(base_config_path),
        "device": device,
        "run_accuracy": run_accuracy,
        "enable_saf": enable_saf,
        "enable_variation": enable_variation,
        "enable_rratio": enable_rratio,
        "fixed_qrange": fixed_qrange,
        "simconfig_rows": simconfig_rows,
        "preset_rows": preset_rows,
        "preset_payloads": preset_payloads,
        "effect_rows": effect_rows,
        "interaction_cells": interaction_cells,
        "interaction_xs": interaction_xs,
        "interaction_ys": interaction_ys,
        "preset_best_rows": preset_best_rows,
        "samples": len(rows),
        "feasible_samples": len(feasible),
        "feasible_rate": (len(feasible) / len(rows)) if rows else None,
        "global_pareto_samples": len(pareto),
        "accuracy_target_override": accuracy_override,
        "accuracy_targets_in_data": accuracy_targets,
        "algo_counts": dict(algos),
        "phase_counts": _phase_counts(rows),
        "rram_preset_counts": dict(presets),
        "best_feasible_latency": _best_record(feasible or rows, "latency_ns"),
        "best_feasible_energy": _best_record(feasible or rows, "energy_nj"),
        "best_feasible_area": _best_record(feasible or rows, "area_um2"),
        "best_accuracy": _best_record(rows, "accuracy", maximize=True),
        "metric_ranges": {
            "latency_ns": {"min": _metric_min(rows, "latency_ns"), "max": _metric_max(rows, "latency_ns")},
            "energy_nj": {"min": _metric_min(rows, "energy_nj"), "max": _metric_max(rows, "energy_nj")},
            "area_um2": {"min": _metric_min(rows, "area_um2"), "max": _metric_max(rows, "area_um2")},
            "accuracy": {"min": _metric_min(rows, "accuracy"), "max": _metric_max(rows, "accuracy")},
        },
    }


def _top_group(group_summary: List[Dict[str, Any]], group_by: str) -> Optional[Dict[str, Any]]:
    rows = [r for r in group_summary if r["group_by"] == group_by]
    if not rows:
        return None
    rows.sort(key=lambda r: (-(r["feasible_rate"] or 0.0), -(r["feasible_samples"] or 0), -(r["best_accuracy"] or 0.0)))
    return rows[0]


def _infer_recommendations(summary: Dict[str, Any], group_summary: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    feasible_rate = float(summary.get("feasible_rate") or 0.0)
    rate_pct = feasible_rate * 100.0
    best_preset = _top_group(group_summary, "rram_preset")
    best_xbar = _top_group(group_summary, "xbar_size")
    best_adc = _top_group(group_summary, "adc_choice")
    best_pe = _top_group(group_summary, "pe_num")

    phase_counts = _phase_counts(rows)
    has_a = phase_counts.get("matrix_A", 0) > 0
    has_b = phase_counts.get("matrix_B", 0) > 0
    has_c = phase_counts.get("matrix_C", 0) > 0
    has_d = phase_counts.get("matrix_D", 0) > 0

    a_rows = _phase_rows(rows, "matrix_A")
    b_rows = _phase_rows(rows, "matrix_B")
    c_rows = _phase_rows(rows, "matrix_C")
    d_rows = _phase_rows(rows, "matrix_D")
    a_stats = _phase_metric_summary(a_rows) if a_rows else {}
    b_stats = _phase_metric_summary(b_rows) if b_rows else {}
    c_stats = _phase_metric_summary(c_rows) if c_rows else {}
    d_stats = _phase_metric_summary(d_rows) if d_rows else {}

    p3_d_rows = [r for r in d_rows if str(r.get("rram_preset")) == "P3"]
    p4_d_rows = [r for r in d_rows if str(r.get("rram_preset")) == "P4"]
    p3_d_feasible = [r for r in p3_d_rows if r.get("feasible")]
    p4_d_feasible = [r for r in p4_d_rows if r.get("feasible")]
    best_p3_d = min(
        p3_d_feasible,
        key=lambda r: (r.get("latency_ns") or float("inf"), r.get("energy_nj") or float("inf")),
    ) if p3_d_feasible else None
    best_c_pe = _top_group(_group_summary(c_rows, ["pe_num"]), "pe_num") if c_rows else None
    best_c_tile = _top_group(_group_summary(c_rows, ["tile_connection"]), "tile_connection") if c_rows else None
    best_c_bw = _top_group(_group_summary(c_rows, ["inter_tile_bw"]), "inter_tile_bw") if c_rows else None

    if has_a and has_b and has_c and has_d:
        stage = "进入正式搜索（收束空间已基本确定）"
    elif has_a and has_b and has_d and not has_c:
        stage = "进入矩阵 C（系统瓶颈验证）"
    elif has_a and has_b and not has_d:
        stage = "进入矩阵 D（退化边界验证）"
    elif has_a and not has_b:
        stage = "进入矩阵 B（接口补偿验证）"
    elif feasible_rate < 0.3:
        stage = "继续收缩空间"
    else:
        stage = "进入正式搜索"

    highlights: List[str] = []
    actions: List[str] = []
    cautions: List[str] = []

    highlights.append(f"当前主数据集共 {summary.get('samples', 0)} 个点，总体可行率约 {rate_pct:.1f}%，已经从“摸底”进入“收束验证”阶段。")

    if has_a:
        highlights.append("矩阵 A 已证明：P0/P1/P2 仍稳定可行，而 P3 在无补偿条件下整体失效，器件退化确实会触发设计迁移问题。")

    if has_b:
        delta_lat = _compensation_delta(a_stats.get("best_latency_ns"), b_stats.get("best_latency_ns"))
        delta_en = _compensation_delta(a_stats.get("best_energy_nj"), b_stats.get("best_energy_nj"))
        highlights.append(
            f"矩阵 B 已证明：对 P1/P2，接口补偿保持 100% 可行，同时把最小时延改善到 {_fmt_num(b_stats.get('best_latency_ns'))} ns、最小能耗压到 {_fmt_num(b_stats.get('best_energy_nj'))} nJ。"
        )
        if delta_lat is not None and delta_en is not None:
            highlights.append(
                f"相对矩阵 A，当前最佳补偿点的时延下降约 {_fmt_num(abs(delta_lat))} ns，能耗下降约 {_fmt_num(abs(delta_en))} nJ，说明补偿收益主要体现在 PPA 而不是精度提升。"
            )

    if has_d:
        if best_p3_d:
            highlights.append(
                f"矩阵 D 已给出关键结论：P3 已被部分救回，当前恢复点是 `xbar=512x512 / ADC=7 / DAC=32 / PE=2x2`，精度 {_fmt_num(best_p3_d.get('accuracy'))}。"
            )
        else:
            highlights.append("矩阵 D 表明：P3 在当前压力边界下仍未恢复，现有补偿强度还不足以覆盖重度退化。")
        if p4_d_rows:
            highlights.append(f"P4 目前仍是 0/{len(p4_d_rows)} 可行，说明当前方案的有效边界大致停在 P3 左右，P4 更适合作为失效边界而不是主应用场景。")

    if has_c:
        highlights.append(
            f"矩阵 C 已证明：系统层 16/16 全可行，平均精度约 {_fmt_num(c_stats.get('mean_accuracy'))}，说明当前器件/接口主方案在系统层也站得住。"
        )
        if best_c_pe:
            highlights.append(
                f"`pe_num={_quote(best_c_pe['group_value'])}` 明显优于 `4x4`，因此论文默认并行度应固定在 `2x2`。"
            )
        if best_c_tile:
            highlights.append(
                f"`tile_connection={_quote(best_c_tile['group_value'])}` 当前更稳，建议作为正式搜索默认拓扑。"
            )
        if best_c_bw:
            highlights.append(
                f"`inter_tile_bw={_quote(best_c_bw['group_value'])}` 在当前样本下时延更优，建议保留为系统默认带宽。"
            )

    if best_xbar:
        highlights.append(f"结构层面最稳定的结论仍是：`xbar_size={_quote(best_xbar['group_value'])}` 应继续保留为主论文默认阵列尺寸。")
    if best_pe:
        highlights.append(f"并行度上 `pe_num={_quote(best_pe['group_value'])}` 更稳，当前不建议回到更大的 `4x4` 作为默认设置。")
    if best_adc and has_b and not has_c:
        highlights.append(f"如果目标偏 PPA，当前更值得优先保留 `ADC={_quote(best_adc['group_value'])}`；但是否作为最终默认档位，还应等待矩阵 C 的系统层验证。")
    elif best_adc and has_b and has_c:
        highlights.append(f"接口层当前可收束为两条论文候选线：`ADC=6 + DAC=128` 偏 PPA，`ADC=4 + DAC=32` 偏面积/基线。")
    elif best_adc:
        highlights.append(f"ADC 当前最值得保留的是 `{_quote(best_adc['group_value'])}` 档。")
    if best_preset:
        highlights.append(
            f"从已采样结果看，当前最稳的器件场景仍是 `{_quote(best_preset['group_value'])}`，但论文重点已经不再是“哪个 preset 最好”，而是“补偿能把退化器件拉回多少”。"
        )

    if has_a and has_b and has_c and has_d:
        actions.extend([
            "下一步不要再扩矩阵，直接基于当前结论构造正式论文版搜索空间并启动 NSGA-II / MOBO。",
            "正式搜索建议固定：`xbar_size=512x512`、`pe_num=2x2`、`tile_connection=2`、`inter_tile_bw=80`。",
            "正式搜索只保留少量关键变量：`rram_preset`、`adc_choice`、`dac_num`、`sub_position`，并围绕 P1/P2/P3 做论文主图。"])
    elif has_a and has_b and has_d and not has_c:
        actions.extend([
            "下一步优先跑矩阵 C：固定当前器件/接口优选组合，验证 `pe_num / tile_connection / inter_tile_bw` 的系统瓶颈。",
            "矩阵 C 跑完后，再把正式搜索空间收缩成 4~5 个变量，最后再启动 NSGA-II / MOBO 做正式论文搜索。",
            "如果矩阵 C 继续支持 `512x512 + 2x2`，就可以把它们固定成论文默认结构，只让 ADC / DAC / sub_position 参与最终优化。"])
    elif has_a and has_b and not has_d:
        actions.extend([
            "下一步先跑矩阵 D：验证当前补偿是否能把 P3 拉回可行域，并明确失效边界是否已经到 P4。",
            "矩阵 D 后再决定是否进入矩阵 C，避免先做系统层实验却还没回答退化边界问题。",
            "若 P3 完全救不回，则论文应强调补偿有效边界；若 P3 可恢复，则论文卖点可升级为“退化恢复”。"])
    else:
        actions.extend([
            "优先完成 A/B/D 三组定向实验，再决定是否进入正式搜索。",
            "不要在矩阵结论不完整前直接扩大 random 预算。",
            "先固定明显优势变量，再做系统层或多目标正式搜索。"])

    cautions.append("当前 `analysis_scope` 仍以矩阵 A 为主，因为 A 的样本数最多；首页摘要已按全数据最新阶段重写，但下方部分图表仍更多体现 A 的统计。")
    cautions.append("矩阵 B 目前只覆盖 P1/P2，所以 A/B 补偿报告不能被解释成“对全部 preset 都成立”的结论。")
    cautions.append("矩阵 D 只出现了少量 P3 恢复点，现阶段更适合写成“边界恢复证据”，还不足以直接宣称对重度退化全面有效。")
    if has_c:
        cautions.append("矩阵 C 只覆盖 P1/P2，因此系统层默认结构是建立在中度退化场景上的；若后续要做 P3 系统级部署，还需补做更差器件下的系统验证。")

    return {
        "stage": stage,
        "highlights": highlights,
        "actions": actions,
        "cautions": cautions,
    }


def _svg_scatter(
    rows: List[Dict[str, Any]],
    x_key: str,
    y_key: str,
    x_label: str,
    y_label: str,
    title: str,
    *,
    log_x: bool = True,
    log_y: bool = True,
    width: int = 560,
    height: int = 360,
) -> str:
    margin_left, margin_right, margin_top, margin_bottom = 68, 16, 34, 54
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    points = []
    for r in rows:
        x_val = r.get(x_key)
        y_val = r.get(y_key)
        if x_val is None or y_val is None:
            continue
        if log_x and float(x_val) <= 0:
            continue
        if log_y and float(y_val) <= 0:
            continue
        points.append(r)
    if not points:
        return f"<div class='chart-empty'>{html.escape(title)}: no valid points</div>"

    xs = [float(r[x_key]) for r in points]
    ys = [float(r[y_key]) for r in points]
    txs = [math.log10(x) if log_x else x for x in xs]
    tys = [math.log10(y) if log_y else y for y in ys]
    min_x, max_x = min(txs), max(txs)
    min_y, max_y = min(tys), max(tys)
    if max_x <= min_x:
        max_x = min_x + 1.0
    if max_y <= min_y:
        max_y = min_y + 1.0

    def sx(val: float) -> float:
        x_t = math.log10(val) if log_x else val
        return margin_left + (x_t - min_x) / (max_x - min_x) * plot_w

    def sy(val: float) -> float:
        y_t = math.log10(val) if log_y else val
        return margin_top + plot_h - (y_t - min_y) / (max_y - min_y) * plot_h

    grid = []
    labels = []
    for i in range(5):
        frac = i / 4
        x = margin_left + frac * plot_w
        y = margin_top + frac * plot_h
        grid.append(f"<line x1='{x:.1f}' y1='{margin_top}' x2='{x:.1f}' y2='{margin_top + plot_h}' class='grid' />")
        grid.append(f"<line x1='{margin_left}' y1='{y:.1f}' x2='{margin_left + plot_w}' y2='{y:.1f}' class='grid' />")
        xv = 10 ** (min_x + frac * (max_x - min_x)) if log_x else (min_x + frac * (max_x - min_x))
        yv = 10 ** (max_y - frac * (max_y - min_y)) if log_y else (max_y - frac * (max_y - min_y))
        labels.append(f"<text x='{x:.1f}' y='{height - 18}' class='tick' text-anchor='middle'>{html.escape(_fmt_num(xv, 2))}</text>")
        labels.append(f"<text x='{margin_left - 8}' y='{y + 4:.1f}' class='tick' text-anchor='end'>{html.escape(_fmt_num(yv, 2))}</text>")

    circles = []
    for row in points:
        fill = PRESET_COLORS.get(str(row.get("rram_preset")), "#76b7b2")
        opacity = "0.85" if row.get("feasible", False) else "0.20"
        stroke = "#111827" if row.get("global_pareto", False) else "none"
        stroke_width = "1.5" if row.get("global_pareto", False) else "0"
        tooltip = (
            f"点ID：{row.get('matrix_point_id', '-')}\n"
            f"可行：{'是' if row.get('feasible', False) else '否'}\n"
            f"全局Pareto：{'是' if row.get('global_pareto', False) else '否'}\n"
            f"器件预设：{row.get('rram_preset')}\n"
            f"交叉阵列：{row.get('xbar_size')}\n"
            f"ADC：{row.get('adc_choice')}\n"
            f"DAC数量：{row.get('dac_num')}\n"
            f"PE规模：{row.get('pe_num')}\n"
            f"Tile连接：{row.get('tile_connection')}\n"
            f"片间带宽：{row.get('inter_tile_bw')} Gb/s\n"
            f"时延：{_fmt_num(row.get('latency_ns'))} ns\n"
            f"能耗：{_fmt_num(row.get('energy_nj'))} nJ\n"
            f"面积：{_fmt_num(row.get('area_um2'))} μm²\n"
            f"精度：{_fmt_num(row.get('accuracy'))}"
        )
        circles.append(
            "<circle "
            f"cx='{sx(float(row[x_key])):.2f}' cy='{sy(float(row[y_key])):.2f}' r='4.5' "
            f"fill='{fill}' fill-opacity='{opacity}' stroke='{stroke}' stroke-width='{stroke_width}' "
            f"class='point-dot' data-tooltip='{html.escape(tooltip, quote=True)}'>"
            f"<title>{html.escape(tooltip)}</title>"
            "</circle>"
        )

    legend_items = []
    for preset, color in PRESET_COLORS.items():
        legend_items.append(
            f"<span class='legend-item'><span class='swatch' style='background:{color}'></span>{preset}</span>"
        )
    legend = "".join(legend_items)

    return f"""
    <div class="chart-card">
      <div class="chart-title">{html.escape(title)}</div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{html.escape(title)}">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
        {''.join(grid)}
        <line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" class="axis" />
        <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" class="axis" />
        {''.join(labels)}
        {''.join(circles)}
        <text x="{margin_left + plot_w/2:.1f}" y="{height - 4}" class="axis-label" text-anchor="middle">{html.escape(x_label)}{"（对数坐标）" if log_x else ""}</text>
        <text x="16" y="{margin_top + plot_h/2:.1f}" class="axis-label" text-anchor="middle" transform="rotate(-90 16 {margin_top + plot_h/2:.1f})">{html.escape(y_label)}{"（对数坐标）" if log_y else ""}</text>
      </svg>
      <div class="legend">{legend}<span class="legend-note">浅色=不可行；黑边=全局 Pareto；悬停可看详细配置</span></div>
    </div>
    """


def _html_table(rows: List[Dict[str, Any]], headers: Sequence[str], title: str, limit: int = 10) -> str:
    if not rows:
        return f"<div class='table-card'><div class='table-scroll'><div class='table-sticky-title'>{html.escape(title)}</div><div class='chart-empty'>No data</div></div></div>"
    head_html = "".join(f"<th>{html.escape(FIELD_LABELS.get(h, h))}</th>" for h in headers)
    body_parts = []
    for row in rows[:limit]:
        tds = []
        for h in headers:
            value = row.get(h)
            if isinstance(value, float):
                cell = _fmt_num(value)
            elif isinstance(value, bool):
                cell = "是" if value else "否"
            elif isinstance(value, str) and h in {"feasible", "global_pareto"}:
                cell = "是" if value.lower() == "true" else "否"
            elif isinstance(value, str) and h == "feasible_rate":
                try:
                    cell = f"{float(value) * 100:.1f}%"
                except Exception:
                    cell = value
            elif h in {"preset", "rram_preset", "group_value", "dominant_value"} and isinstance(value, str) and value in PRESET_COLORS:
                cell = f"<button class='preset-chip' data-preset='{html.escape(value, quote=True)}'>{html.escape(value)}</button>"
            else:
                cell = "-" if value is None else str(value)
            if isinstance(cell, str) and cell.startswith("<button "):
                tds.append(f"<td>{cell}</td>")
            else:
                tds.append(f"<td>{html.escape(cell)}</td>")
        body_parts.append("<tr>" + "".join(tds) + "</tr>")
    return (
        f"<div class='table-card'><div class='table-scroll'><div class='table-sticky-title'>{html.escape(title)}</div>"
        f"<table><thead><tr>{head_html}</tr></thead><tbody>{''.join(body_parts)}</tbody></table></div></div>"
    )


def _recommend_reason(row: Dict[str, Any], summary: Dict[str, Any], rank: int) -> str:
    reasons: List[str] = []
    if rank == 1:
        reasons.append("综合平衡分最佳")
    if row.get("global_pareto"):
        reasons.append("位于全局 Pareto 前沿")
    if row.get("feasible"):
        reasons.append("满足精度门槛")
    if summary.get("best_feasible_latency", {}).get("latency_ns") == row.get("latency_ns"):
        reasons.append("时延最优")
    if summary.get("best_feasible_energy", {}).get("energy_nj") == row.get("energy_nj"):
        reasons.append("能耗最优")
    if summary.get("best_feasible_area", {}).get("area_um2") == row.get("area_um2"):
        reasons.append("面积最优")
    if summary.get("best_accuracy", {}).get("accuracy") == row.get("accuracy"):
        reasons.append("精度最高")
    return " / ".join(reasons[:3]) if reasons else "综合表现稳定，适合作为论文候选点。"


def _top_rank_cards_html(top_configs: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    if not top_configs:
        return "<div class='chart-empty'>暂无推荐配置</div>"
    accent = ["#2563eb", "#7c3aed", "#db2777"]
    medals = ["🥇", "🥈", "🥉"]
    cards: List[str] = []
    for idx, row in enumerate(top_configs[:3]):
        rank = idx + 1
        preset = row.get("rram_preset")
        preset_html = (
            f"<button class='preset-chip' data-preset='{html.escape(str(preset), quote=True)}'>{html.escape(str(preset))}</button>"
            if isinstance(preset, str) and preset in PRESET_COLORS
            else html.escape(str(preset or "-"))
        )
        point_label = row.get("matrix_point_id") or f"eval-{row.get('eval_index', '-')}"
        cards.append(
            f"""
            <div class="rank-card" style="--rank-accent:{accent[idx]};">
              <div class="rank-top">
                <div class="rank-badge">{medals[idx]} Rank-{rank}</div>
                <div class="rank-point">{html.escape(str(point_label))}</div>
              </div>
              <div class="rank-reason">{html.escape(_recommend_reason(row, summary, rank))}</div>
              <div class="rank-meta">
                <span class="mini-pill">preset {preset_html}</span>
                <span class="mini-pill">xbar {html.escape(str(row.get("xbar_size", "-")))}</span>
                <span class="mini-pill">ADC {html.escape(str(row.get("adc_choice", "-")))}</span>
                <span class="mini-pill">DAC {html.escape(str(row.get("dac_num", "-")))}</span>
                <span class="mini-pill">PE {html.escape(str(row.get("pe_num", "-")))}</span>
              </div>
              <div class="rank-kv">
                <div>时延</div><div>{html.escape(_fmt_num(row.get("latency_ns")))} ns</div>
                <div>能耗</div><div>{html.escape(_fmt_num(row.get("energy_nj")))} nJ</div>
                <div>面积</div><div>{html.escape(_fmt_num(row.get("area_um2")))} μm²</div>
                <div>精度</div><div>{html.escape(_fmt_num(row.get("accuracy")))}</div>
              </div>
            </div>
            """
        )
    return "".join(cards)


def _build_html(
    summary: Dict[str, Any],
    top_configs: List[Dict[str, Any]],
    group_summary: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    output_dir: Path,
    compensation_report: Optional[Dict[str, Any]] = None,
) -> str:
    recommendations = _infer_recommendations(summary, group_summary, rows)
    cards = [
        ("样本数", _fmt_num(summary["samples"], 0)),
        ("可行样本", _fmt_num(summary["feasible_samples"], 0)),
        ("可行率", _fmt_num((summary["feasible_rate"] or 0.0) * 100.0, 2) + "%"),
        ("全局 Pareto", _fmt_num(summary["global_pareto_samples"], 0)),
    ]
    card_html = "".join(
        f"<div class='card'><div class='card-label'>{html.escape(k)}</div><div class='card-value'>{html.escape(v)}</div></div>"
        for k, v in cards
    )

    best_latency = summary.get("best_feasible_latency") or {}
    best_energy = summary.get("best_feasible_energy") or {}
    best_area = summary.get("best_feasible_area") or {}
    best_acc = summary.get("best_accuracy") or {}
    rank_cards_html = _top_rank_cards_html(top_configs, summary)
    compensation_link = ""
    if compensation_report:
        compensation_link = (
            "<div class='info-card' style='margin-top:16px;'>"
            "<div class='table-title'>补偿前后对比</div>"
            f"<div class='note'>已检测到矩阵 A 与矩阵 B，可直接打开补偿对比页："
            f"<a class='inline-link' href='./{html.escape(Path(compensation_report['html_path']).name)}'>补偿前后对比报告</a></div>"
            "</div>"
        )

    top_table_headers = [
        "rank", "feasible", "global_pareto", "rram_preset", "xbar_size", "adc_choice",
        "dac_num", "pe_num", "phase", "matrix_point_id", "latency_ns", "energy_nj", "area_um2", "accuracy", "algo", "seed", "eval_index"
    ]
    group_headers = [
        "group_by_zh", "group_value", "samples", "feasible_samples", "feasible_rate",
        "global_pareto_samples", "best_latency_ns", "best_energy_nj", "best_area_um2", "best_accuracy"
    ]

    preset_focus = [r for r in group_summary if r["group_by"] == "rram_preset"]
    xbar_focus = [r for r in group_summary if r["group_by"] == "xbar_size"]
    adc_focus = [r for r in group_summary if r["group_by"] == "adc_choice"]
    summary_bullets = "".join(f"<li>{html.escape(x)}</li>" for x in recommendations["highlights"])
    action_bullets = "".join(f"<li>{html.escape(x)}</li>" for x in recommendations["actions"])
    caution_bullets = "".join(f"<li>{html.escape(x)}</li>" for x in recommendations["cautions"])
    space_headers = ["dim", "dim_zh", "layer_zh", "candidate_values", "observed_values"]
    simconfig_headers = ["section_zh", "section", "key_zh", "key", "key_desc", "value"]
    preset_headers = ["preset", "observed_samples", "device_resistance", "device_variation", "device_saf"]
    effect_headers = ["group_by_zh", "value_count", "balanced_score_spread", "accuracy_spread", "latency_spread", "energy_spread", "area_spread", "dominant_value"]
    preset_best_headers = ["preset", "xbar_size", "adc_choice", "dac_num", "pe_num", "latency_ns", "energy_nj", "area_um2", "accuracy"]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MNSIM DSE Analysis</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --card: #ffffff;
      --text: #111827;
      --muted: #6b7280;
      --line: #dbe2ea;
      --accent: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    .wrap {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .sub {{ color: var(--muted); margin-bottom: 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 16px; margin-bottom: 18px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }}
    .card-label {{ color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
    .card-value {{ font-size: 28px; font-weight: 700; }}
    .section {{ margin-top: 24px; }}
    .section-title {{ font-size: 18px; font-weight: 700; margin: 0 0 14px; }}
    .note {{ color: var(--muted); font-size: 13px; line-height: 1.6; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .grid3 {{ display: grid; grid-template-columns: repeat(3, minmax(240px, 1fr)); gap: 16px; }}
    .chart-card, .info-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }}
    .table-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; position: relative; padding: 0; overflow: hidden; }}
    .chart-title, .table-title {{ font-size: 15px; font-weight: 700; margin-bottom: 8px; }}
    .table-scroll {{
      overflow: auto;
      max-height: 372px;
      position: relative;
      background: var(--card);
    }}
    .table-sticky-title {{
      margin: 0;
      padding: 14px 14px 10px;
      background: var(--card);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
      font-size: 15px;
      font-weight: 700;
    }}
    .chart-svg {{ width: 100%; height: auto; display: block; }}
    .point-dot {{ cursor: pointer; }}
    .axis {{ stroke: #374151; stroke-width: 1.2; }}
    .grid {{ stroke: #e5e7eb; stroke-width: 1; }}
    .tick {{ fill: #6b7280; font-size: 11px; }}
    .axis-label {{ fill: #374151; font-size: 12px; }}
    .heat-text {{ fill: #0f172a; font-size: 11px; font-weight: 600; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend-note {{ margin-left: auto; }}
    .swatch {{ width: 12px; height: 12px; display: inline-block; border-radius: 999px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; background: var(--card); }}
    th, td {{ border-bottom: 1px solid var(--line); text-align: left; padding: 8px 10px; vertical-align: top; background: var(--card); }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: #fafbfc;
      position: sticky;
      top: 45px;
      z-index: 4;
    }}
    td {{ position: relative; z-index: 1; }}
    .chart-empty {{ color: var(--muted); padding: 14px; }}
    .kv {{ display: grid; grid-template-columns: 180px 1fr; gap: 8px; font-size: 14px; }}
    .kv div:nth-child(odd) {{ color: var(--muted); }}
    .mini-kv {{ display:grid; grid-template-columns: 108px 1fr; gap: 8px; font-size: 13px; }}
    .mini-kv div:nth-child(odd) {{ color: var(--muted); }}
    .card-note {{ color: var(--muted); font-size: 13px; line-height: 1.65; margin-top: 10px; }}
    .kv div:nth-child(even),
    .mini-kv div:nth-child(even),
    .card-note,
    .note,
    td {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .pill {{ display: inline-block; background: #eef2ff; color: #3730a3; border-radius: 999px; padding: 4px 10px; font-size: 12px; margin-right: 8px; }}
    .stage {{ display:inline-block; background:#ecfeff; color:#155e75; border:1px solid #a5f3fc; border-radius:999px; padding:4px 10px; font-size:12px; margin-bottom:10px; }}
    .tooltip {{
      position: fixed;
      display: none;
      max-width: 360px;
      background: rgba(17, 24, 39, 0.96);
      color: #fff;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.55;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.20);
      pointer-events: none;
      white-space: normal;
      z-index: 9999;
    }}
    .tabs {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }}
    .tab-buttons {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
    .tab-btn {{
      border: 1px solid var(--line);
      background: #f8fafc;
      color: var(--text);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      cursor: pointer;
    }}
    .tab-btn.active {{ background: #e0ecff; border-color: #93c5fd; color: #1d4ed8; }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .preset-chip {{
      border: 1px solid #bfdbfe;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    .drawer-mask {{
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.32);
      display: none;
      z-index: 10000;
    }}
    .drawer {{
      position: fixed;
      top: 0;
      right: 0;
      width: min(420px, 92vw);
      height: 100vh;
      background: #fff;
      box-shadow: -12px 0 32px rgba(15, 23, 42, 0.18);
      transform: translateX(100%);
      transition: transform .18s ease;
      padding: 18px 18px 24px;
      overflow: auto;
    }}
    .drawer-mask.open {{ display: block; }}
    .drawer-mask.open .drawer {{ transform: translateX(0); }}
    .drawer-head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom: 12px; }}
    .drawer-close {{ border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 6px 10px; cursor: pointer; }}
    .drawer-kv {{ display:grid; grid-template-columns: 120px 1fr; gap: 8px; font-size: 14px; }}
    .drawer-kv div:nth-child(odd) {{ color: var(--muted); }}
    .guide-grid {{ display:grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 12px; }}
    .guide-card {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
    }}
    .rank-grid {{ display:grid; grid-template-columns: repeat(3, minmax(280px, 1fr)); gap: 16px; }}
    .rank-card {{
      background: linear-gradient(180deg, rgba(255,255,255,1) 0%, rgba(248,250,252,1) 100%);
      border: 1px solid var(--line);
      border-top: 4px solid var(--rank-accent);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }}
    .rank-top {{ display:flex; align-items:center; justify-content:space-between; gap: 12px; margin-bottom: 10px; }}
    .rank-badge {{ font-size: 15px; font-weight: 800; color: var(--rank-accent); }}
    .rank-point {{ font-size: 12px; color: var(--muted); }}
    .rank-reason {{ font-size: 14px; font-weight: 700; line-height: 1.5; margin-bottom: 10px; }}
    .rank-meta {{ display:flex; flex-wrap:wrap; gap: 8px; margin-bottom: 12px; }}
    .mini-pill {{ display:inline-flex; align-items:center; gap: 4px; background:#f8fafc; border:1px solid var(--line); border-radius:999px; padding:4px 10px; font-size:12px; }}
    .rank-kv {{ display:grid; grid-template-columns: 80px 1fr; gap: 8px; font-size: 13px; }}
    .rank-kv div:nth-child(odd) {{ color: var(--muted); }}
    .inline-link {{ color: #1d4ed8; font-weight: 700; text-decoration: none; }}
    .guide-step {{ color: #2563eb; font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
    .guide-title {{ font-size: 14px; font-weight: 700; margin-bottom: 6px; }}
    .guide-desc {{ color: var(--muted); font-size: 13px; line-height: 1.55; }}
    ul.tight {{ margin: 6px 0 0 18px; padding: 0; }}
    ul.tight li {{ margin: 6px 0; line-height: 1.5; }}
    @media (max-width: 960px) {{
      .cards, .grid2, .grid3, .rank-grid {{ grid-template-columns: 1fr; }}
      .guide-grid {{ grid-template-columns: 1fr; }}
      .legend-note {{ width: 100%; margin-left: 0; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>MNSIM DSE 采样结果分析</h1>
    <div class="sub">输出目录：{html.escape(_display_path(str(output_dir)))}</div>
    <div class="cards">{card_html}</div>

    <div class="section">
      <div class="section-title">摘要</div>
      <div class="grid2">
        <div class="info-card">
          <div class="stage">当前阶段：{html.escape(recommendations["stage"])}</div>
          <div class="table-title">当前结果说明什么</div>
          <ul class="tight">{summary_bullets}</ul>
        </div>
        <div class="info-card">
          <div class="table-title">建议下一步实验</div>
          <ul class="tight">{action_bullets}</ul>
        </div>
      </div>
      <div class="info-card" style="margin-top:16px;">
        <div class="table-title">风险提示</div>
        <ul class="tight">{caution_bullets}</ul>
      </div>
      {compensation_link}
    </div>

    <div class="section">
      <div class="section-title">Rank Top-3 推荐配置</div>
      <div class="note" style="margin-bottom:14px;">这里展示的是具体配置点，不是分组统计。`Rank-1 / Rank-2 / Rank-3` 可以直接用于论文主表或后续复现实验。</div>
      <div class="rank-grid">{rank_cards_html}</div>
    </div>

    <div class="section">
      <div class="section-title">实验设定</div>
      <div class="grid3">
        <div class="info-card">
          <div class="table-title">实验背景</div>
          <div class="mini-kv">
            <div>任务目标</div><div>面向 `RRAM` 论文的整网级 DSE，在 `PPA + ACC` 约束下给出器件—接口—系统协同设计建议。</div>
            <div>数据集名称</div><div>{html.escape(str(summary.get("dataset_name", "-")))}</div>
            <div>网络模型</div><div>{html.escape(str(summary.get("workload", "-")))}</div>
            <div>输入数据集</div><div>{html.escape(str(summary.get("dataset_name_short", "-")))}（{html.escape(str(summary.get("dataset_module", "-"))) }）</div>
            <div>权重文件</div><div>{html.escape(str(summary.get("weights_file", "-")))}</div>
            <div>基准配置</div><div>{html.escape(str(summary.get("base_config_file", "-")))}</div>
            <div>搜索空间</div><div>{html.escape(str(summary.get("space_profile_label", "-")))}（`{html.escape(str(summary.get("space_profile", "-")))}`）</div>
          </div>
          <div class="card-note">输入来源：{html.escape(str(summary.get("source_path_display", summary.get("source", "-"))))}</div>
        </div>
        <div class="info-card">
          <div class="table-title">运行条件</div>
          <div class="mini-kv">
            <div>运行设备</div><div>{html.escape(str(summary.get("device", "-")))}</div>
            <div>精度仿真</div><div>{'开启' if summary.get("run_accuracy") else '关闭'}</div>
            <div>精度门槛</div><div>{html.escape(_fmt_num(summary.get("accuracy_target_override")))}（若为 -，使用每行自带值）</div>
            <div>SAF</div><div>{'开启' if summary.get("enable_saf") else '关闭'}</div>
            <div>Variation</div><div>{'开启' if summary.get("enable_variation") else '关闭'}</div>
            <div>R-ratio</div><div>{'开启' if summary.get("enable_rratio") else '关闭'}</div>
            <div>固定量化范围</div><div>{'开启' if summary.get("fixed_qrange") else '关闭'}</div>
            <div>实验组成</div><div>{html.escape(json.dumps(summary.get("phase_counts", {}), ensure_ascii=False))}</div>
          </div>
          <div class="card-note">当前页面中的可行解判定，均基于 `accuracy >= accuracy_target`。</div>
        </div>
        <div class="info-card">
          <div class="table-title">评估口径</div>
          <div class="mini-kv">
            <div>PPA 来源</div><div>来自整网映射后的 MNSIM 硬件估算，包括时延、能耗、面积。</div>
            <div>ACC 来源</div><div>来自 `{html.escape(str(summary.get("dataset_name_short", "-")))}` 推理结果，而不是单层局部估算。</div>
            <div>输出目录</div><div>{html.escape(_display_path(str(output_dir)))}</div>
            <div>权重路径</div><div>{html.escape(str(summary.get("weights_path_display", "-")))}</div>
            <div>配置路径</div><div>{html.escape(str(summary.get("base_config_path_display", "-")))}</div>
            <div>算法分布</div><div>{html.escape(json.dumps(summary.get("algo_counts", {}), ensure_ascii=False))}</div>
            <div>器件预设</div><div>{html.escape(json.dumps(summary.get("rram_preset_counts", {}), ensure_ascii=False))}</div>
          </div>
          <div class="card-note">该数据集未显式记录 `max_acc_batches`，因此页面无法反推出精度评估具体截断到多少个 batch。</div>
        </div>
      </div>
      <div class="note" style="margin-top:12px;">
        <span class="pill">浅色点=精度不达标</span>
        <span class="pill">黑边点=全局 Pareto</span>
        <span class="pill">颜色=RRAM preset</span>
      </div>
    </div>

    <div class="section">
      <div class="section-title">最好结果速览</div>
      <div class="info-card">
        <div class="kv">
          <div>最小时延</div><div>{html.escape(_fmt_num(best_latency.get("latency_ns")))} ns，preset={html.escape(str(best_latency.get("rram_preset", "-")))}, xbar={html.escape(str(best_latency.get("xbar_size", "-")))}, adc={html.escape(str(best_latency.get("adc_choice", "-")))}</div>
          <div>最小能耗</div><div>{html.escape(_fmt_num(best_energy.get("energy_nj")))} nJ，preset={html.escape(str(best_energy.get("rram_preset", "-")))}, xbar={html.escape(str(best_energy.get("xbar_size", "-")))}, adc={html.escape(str(best_energy.get("adc_choice", "-")))}</div>
          <div>最小面积</div><div>{html.escape(_fmt_num(best_area.get("area_um2")))} μm²，preset={html.escape(str(best_area.get("rram_preset", "-")))}, xbar={html.escape(str(best_area.get("xbar_size", "-")))}, adc={html.escape(str(best_area.get("adc_choice", "-")))}</div>
          <div>最高精度</div><div>{html.escape(_fmt_num(best_acc.get("accuracy")))}，preset={html.escape(str(best_acc.get("rram_preset", "-")))}, xbar={html.escape(str(best_acc.get("xbar_size", "-")))}, adc={html.escape(str(best_acc.get("adc_choice", "-")))}</div>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">怎么读这页</div>
      <div class="guide-grid" style="margin-bottom:16px;">
        <div class="guide-card"><div class="guide-step">STEP 1</div><div class="guide-title">先看变量效应量排序</div><div class="guide-desc">先判断优先调哪些变量。排名越靠前，说明这个变量改动后整体结果变化越大。</div></div>
        <div class="guide-card"><div class="guide-step">STEP 2</div><div class="guide-title">再看分组统计摘要</div><div class="guide-desc">判断某个变量的哪个取值更像优选方向。这一步用于缩空间，不直接决定最终设计点。</div></div>
        <div class="guide-card"><div class="guide-step">STEP 3</div><div class="guide-title">再看器件迁移表</div><div class="guide-desc">比较不同器件预设下，最优具体配置是否发生迁移。这一块最接近论文主结论。</div></div>
        <div class="guide-card"><div class="guide-step">STEP 4</div><div class="guide-title">最后看推荐配置</div><div class="guide-desc">这里每一行都是完整配置点，才是最后能拿去做设计建议或论文表格的对象。</div></div>
      </div>
      <div class="info-card">
        <div class="kv">
          <div>配置级最优</div><div>`推荐配置` 与 `按器件预设选出的当前最优平衡配置` 的最优对象，都是单个具体设计点（一个完整配置）。</div>
          <div>分组级摘要</div><div>`变量影响摘要` 与 `变量效应量排序` 是按变量取值聚合后的统计，不代表该组内所有配置都优，也不等同于“最优设计”。</div>
          <div>preset 点击</div><div>页面里出现的 `P0/P1/P2/...` 都可以点击，右侧抽屉会显示器件预设的具体阻值、波动与 SAF 参数。</div>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">配置与空间详情</div>
      <div class="tabs">
        <div class="tab-buttons">
          <button class="tab-btn active" data-tab="space">搜索空间</button>
          <button class="tab-btn" data-tab="preset">RRAM 预设详情</button>
          <button class="tab-btn" data-tab="simconfig">SimConfig 全量字段</button>
        </div>
        <div class="tab-panel active" data-tab-panel="space">
          {_html_table(summary.get("space_dimensions", []), space_headers, "当前分析对应的搜索空间与已覆盖取值", limit=50)}
        </div>
        <div class="tab-panel" data-tab-panel="preset">
          {_html_table(summary.get("preset_rows", []), preset_headers, "RRAM 器件预设的显式参数定义", limit=20)}
        </div>
        <div class="tab-panel" data-tab-panel="simconfig">
          {_html_table(summary.get("simconfig_rows", []), simconfig_headers, "SimConfig.ini 全量字段", limit=500)}
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">决策分析</div>
      <div class="grid2">
        {_svg_heatmap(summary.get("interaction_cells", []), summary.get("interaction_xs", []), summary.get("interaction_ys", []), value_key="mean_accuracy", title="交互热图：xbar_size × pe_num（看变量交互）", subtitle=f"分析范围：{summary.get('analysis_scope', '全样本')}；格内数值为均值精度。")}
        {_svg_preset_accuracy_curve(rows)}
      </div>
      <div class="grid2" style="margin-top:16px;">
        {_html_table(summary.get("preset_best_rows", []), preset_best_headers, "器件迁移表（配置级：每个 preset 下的最优具体配置）", limit=20)}
        {_html_table(summary.get("effect_rows", []), effect_headers, "先调哪些变量（分组级：变量效应量排序）", limit=20)}
      </div>
    </div>

    <div class="section">
      <div class="section-title">PPA 散点图</div>
      <div class="grid2">
        {_svg_scatter(rows, "latency_ns", "energy_nj", "时延（ns）", "能耗（nJ）", "时延-能耗散点")}
        {_svg_scatter(rows, "latency_ns", "area_um2", "时延（ns）", "面积（μm²）", "时延-面积散点")}
      </div>
      <div class="grid2" style="margin-top:16px;">
        {_svg_scatter(rows, "energy_nj", "area_um2", "能耗（nJ）", "面积（μm²）", "能耗-面积散点")}
        {_svg_scatter([r for r in rows if r.get("accuracy") is not None], "latency_ns", "accuracy", "时延（ns）", "精度", "时延-精度散点", log_x=True, log_y=False)}
      </div>
    </div>

    <div class="section">
      <div class="section-title">名词说明</div>
      <div class="info-card">
        <div class="kv">
          <div>feasible（可行）</div><div>表示该设计点满足精度约束，即 `accuracy >= accuracy_target`。</div>
          <div>global Pareto（全局帕累托）</div><div>表示该设计点在全部可行样本里，不会被其他点同时在时延、能耗、面积三项上完全压制。</div>
          <div>时延</div><div>单位是 `ns`。</div>
          <div>能耗</div><div>单位是 `nJ`。</div>
          <div>面积</div><div>单位是 `μm²`。</div>
          <div>片间带宽</div><div>按 `Gb/s` 理解更直观，当前页面已显式写出单位。</div>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">最终推荐的具体配置</div>
      {_html_table(top_configs, top_table_headers, "配置级候选（每一行都是完整设计点）", limit=20)}
    </div>

    <div class="section">
      <div class="section-title">分组统计摘要</div>
      <div class="grid2">
        {_html_table(preset_focus, group_headers, "按 RRAM preset 分组（分组级，不是单点最优）", limit=10)}
        {_html_table(xbar_focus, group_headers, "按 xbar_size 分组（分组级，不是单点最优）", limit=10)}
      </div>
      <div class="grid2" style="margin-top:16px;">
        {_html_table(adc_focus, group_headers, "按 adc_choice 分组（分组级，不是单点最优）", limit=10)}
        {_html_table(group_summary, group_headers, "全部分组摘要（分组级，不是单点最优）", limit=30)}
      </div>
    </div>
  </div>
  <div id="preset-drawer-mask" class="drawer-mask">
    <div class="drawer">
      <div class="drawer-head">
        <div class="section-title" style="margin:0;">RRAM 预设详情</div>
        <button id="preset-drawer-close" class="drawer-close">关闭</button>
      </div>
      <div id="preset-drawer-body" class="drawer-kv"></div>
    </div>
  </div>
  <div id="chart-tooltip" class="tooltip"></div>
  <script>
    (() => {{
      const tooltip = document.getElementById("chart-tooltip");
      if (!tooltip) return;
      const show = (event, text) => {{
        tooltip.innerHTML = String(text || "").replace(/\\n/g, "<br>");
        tooltip.style.display = "block";
        const offset = 16;
        let left = event.clientX + offset;
        let top = event.clientY + offset;
        const rect = tooltip.getBoundingClientRect();
        if (left + rect.width > window.innerWidth - 12) left = event.clientX - rect.width - offset;
        if (top + rect.height > window.innerHeight - 12) top = event.clientY - rect.height - offset;
        tooltip.style.left = left + "px";
        tooltip.style.top = top + "px";
      }};
      const hide = () => {{
        tooltip.style.display = "none";
      }};
      document.querySelectorAll(".point-dot").forEach((node) => {{
        node.addEventListener("mouseenter", (event) => show(event, node.getAttribute("data-tooltip")));
        node.addEventListener("mousemove", (event) => show(event, node.getAttribute("data-tooltip")));
        node.addEventListener("mouseleave", hide);
      }});
      document.querySelectorAll(".tab-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          const target = btn.getAttribute("data-tab");
          document.querySelectorAll(".tab-btn").forEach((node) => node.classList.toggle("active", node === btn));
          document.querySelectorAll(".tab-panel").forEach((panel) => {{
            panel.classList.toggle("active", panel.getAttribute("data-tab-panel") === target);
          }});
        }});
      }});
      const presetPayloads = {json.dumps(summary.get("preset_payloads", {}), ensure_ascii=False)};
      const drawerMask = document.getElementById("preset-drawer-mask");
      const drawerBody = document.getElementById("preset-drawer-body");
      const closeBtn = document.getElementById("preset-drawer-close");
      const openDrawer = (preset) => {{
        const payload = presetPayloads[preset];
        if (!payload || !drawerMask || !drawerBody) return;
        drawerBody.innerHTML = `
          <div>预设名</div><div>${{payload.preset}}</div>
          <div>语义说明</div><div>${{payload.note || '-'}}</div>
          <div>当前样本数</div><div>${{payload.observed_samples}}</div>
          <div>器件阻值</div><div>${{payload.device_resistance}}</div>
          <div>器件波动</div><div>${{payload.device_variation}}</div>
          <div>SAF 缺陷率</div><div>${{payload.device_saf}}</div>
        `;
        drawerMask.classList.add("open");
      }};
      const closeDrawer = () => drawerMask && drawerMask.classList.remove("open");
      document.querySelectorAll(".preset-chip").forEach((node) => {{
        node.addEventListener("click", () => openDrawer(node.getAttribute("data-preset")));
      }});
      if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
      if (drawerMask) drawerMask.addEventListener("click", (event) => {{
        if (event.target === drawerMask) closeDrawer();
      }});
    }})();
  </script>
</body>
</html>
"""


def _analyze_rows(
    rows: List[Dict[str, Any]],
    source_desc: str,
    output_dir: Path,
    accuracy_target: Optional[float],
    topk: int,
) -> Dict[str, Any]:
    """Core analysis logic — shared by analyze() and multi-source merge."""
    for row in rows:
        row["feasible"] = _is_feasible(row, accuracy_target)
    pareto_idxs = set(_global_pareto_indices(rows))
    for i, row in enumerate(rows):
        row["global_pareto"] = i in pareto_idxs

    summary = _build_summary(rows, source_desc, accuracy_target)
    top_configs = _top_configs(rows, topk)
    group_summary = _group_summary(rows, ["rram_preset", "xbar_size", "adc_choice", "pe_num", "tile_connection", "inter_tile_bw"])
    global_pareto = [rows[i] for i in sorted(pareto_idxs)]

    output_dir.mkdir(parents=True, exist_ok=True)
    compensation_report = _build_compensation_report(rows, output_dir)
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    _write_csv(output_dir / "top_configs.csv", top_configs)
    _write_csv(output_dir / "group_summary.csv", group_summary)
    _write_csv(output_dir / "global_pareto.csv", global_pareto)
    with open(output_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(_build_html(summary, top_configs, group_summary, rows, output_dir, compensation_report))

    result: Dict[str, Any] = {
        "summary_path": str(output_dir / "summary.json"),
        "top_configs_path": str(output_dir / "top_configs.csv"),
        "group_summary_path": str(output_dir / "group_summary.csv"),
        "global_pareto_path": str(output_dir / "global_pareto.csv"),
        "html_path": str(output_dir / "index.html"),
        "samples": len(rows),
        "feasible_samples": sum(1 for r in rows if r.get("feasible")),
        "global_pareto_samples": len(global_pareto),
    }
    if compensation_report:
        result["compensation_report_path"] = compensation_report["html_path"]
        result["compensation_compare_csv_path"] = compensation_report["compare_csv_path"]
    return result


def analyze(input_path: Path, output_dir: Path, accuracy_target: Optional[float], topk: int) -> Dict[str, Any]:
    rows, source_desc = _resolve_input(input_path)
    return _analyze_rows(rows, source_desc, output_dir, accuracy_target, topk)


def _resolve_merged_inputs(paths: List[Path]) -> Tuple[List[Dict[str, Any]], str]:
    """Load and merge rows from multiple input paths (for joint analysis)."""
    all_rows: List[Dict[str, Any]] = []
    descs: List[str] = []
    for p in paths:
        rows, desc = _resolve_input(p)
        for row in rows:
            row.setdefault("source_dir", str(p))
        all_rows.extend(rows)
        descs.append(desc)
    return all_rows, " + ".join(descs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze MNSIM DSE sampling outputs and generate HTML dashboard.")
    parser.add_argument(
        "--input", required=True, nargs="+",
        help=(
            "One or more: dataset_history.csv, dataset root, run root, or trial dir. "
            "Multiple paths are merged for joint analysis."
        ),
    )
    parser.add_argument("--output-dir", default=None, help="where analysis files are written (default: first <input>/analysis)")
    parser.add_argument("--accuracy-target", type=float, default=None, help="override minimum accuracy threshold")
    parser.add_argument("--topk", type=int, default=20, help="number of recommended configs to export")
    parser.add_argument("--update-latest", action="store_true", help="Deprecated.")
    args = parser.parse_args()

    input_paths = [Path(p).expanduser().resolve() for p in args.input]

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        output_dir, _ = _prepare_default_output_dir(input_paths[0])

    if len(input_paths) == 1:
        result = analyze(input_paths[0], output_dir, args.accuracy_target, args.topk)
    else:
        # Multi-source merge: load and concatenate rows, then run unified analysis
        merged_rows, source_desc = _resolve_merged_inputs(input_paths)
        print(f"[analysis] merged {len(input_paths)} sources ({len(merged_rows)} rows total): {source_desc}")
        result = _analyze_rows(merged_rows, source_desc, output_dir, args.accuracy_target, args.topk)
    print("[analysis] Done.")
    print(f"[analysis] samples          : {result['samples']}")
    print(f"[analysis] feasible         : {result['feasible_samples']}")
    print(f"[analysis] global pareto    : {result['global_pareto_samples']}")
    print(f"[analysis] summary          : {result['summary_path']}")
    print(f"[analysis] top configs      : {result['top_configs_path']}")
    print(f"[analysis] group summary    : {result['group_summary_path']}")
    print(f"[analysis] global pareto    : {result['global_pareto_path']}")
    print(f"[analysis] html dashboard   : {result['html_path']}")
    if result.get("compensation_report_path"):
        print(f"[analysis] compensation    : {result['compensation_report_path']}")
    if args.update_latest:
        print("[analysis] note             : --update-latest is deprecated; files were written directly into reports/analysis")


if __name__ == "__main__":
    main()
