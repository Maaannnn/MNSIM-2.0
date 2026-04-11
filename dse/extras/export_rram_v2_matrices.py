#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export paper-oriented RRAM v2 experiment matrices as CSV files.

Matrices:
  A - design migration across device presets
  B - interface compensation study
  C - system bottleneck study
  D - stress boundary study
"""
from __future__ import annotations

import argparse
import csv
import itertools
from pathlib import Path
from typing import Dict, Iterable, List


def encode_dim_value(v: object) -> str:
    if isinstance(v, tuple):
        return "x".join(str(x) for x in v)
    return str(v)


DIM_ORDER = [
    "rram_preset",
    "xbar_size",
    "adc_choice",
    "dac_num",
    "xbar_polarity",
    "sub_position",
    "group_num",
    "pe_num",
    "tile_connection",
    "inter_tile_bw",
]


def _expand_matrix(matrix_name: str, purpose: str, variable_axes: Dict[str, List[object]], fixed_axes: Dict[str, object]) -> List[Dict[str, object]]:
    keys = list(variable_axes.keys())
    rows: List[Dict[str, object]] = []
    for idx, combo in enumerate(itertools.product(*[variable_axes[k] for k in keys]), start=1):
        row: Dict[str, object] = {
            "matrix_name": matrix_name,
            "matrix_purpose": purpose,
            "matrix_point_id": f"{matrix_name}_{idx:03d}",
        }
        row.update(fixed_axes)
        row.update(dict(zip(keys, combo)))
        rows.append(row)
    return rows


def _matrix_definitions() -> Dict[str, List[Dict[str, object]]]:
    matrices: Dict[str, List[Dict[str, object]]] = {}
    matrices["A"] = _expand_matrix(
        "A",
        "主迁移矩阵：观察器件退化下的最优设计迁移",
        {
            "rram_preset": ["P0", "P1", "P2", "P3"],
            "xbar_size": [(128, 128), (512, 512)],
            "adc_choice": [4, 6],
            "pe_num": [(2, 2), (4, 4)],
        },
        {
            "dac_num": 32,
            "xbar_polarity": 2,
            "sub_position": 1,
            "group_num": 1,
            "tile_connection": 2,
            "inter_tile_bw": 80,
        },
    )
    matrices["B"] = _expand_matrix(
        "B",
        "接口补偿矩阵：观察 DAC 与减法位置是否补偿器件退化",
        {
            "rram_preset": ["P1", "P2"],
            "xbar_size": [(128, 128), (512, 512)],
            "dac_num": [32, 128],
            "sub_position": [0, 1],
        },
        {
            "adc_choice": 6,
            "xbar_polarity": 2,
            "group_num": 1,
            "pe_num": (2, 2),
            "tile_connection": 2,
            "inter_tile_bw": 80,
        },
    )
    matrices["C"] = _expand_matrix(
        "C",
        "系统瓶颈矩阵：观察并行度与互连是否限制大阵列收益",
        {
            "rram_preset": ["P1", "P2"],
            "pe_num": [(2, 2), (4, 4)],
            "tile_connection": [2, 3],
            "inter_tile_bw": [40, 80],
        },
        {
            "xbar_size": (512, 512),
            "adc_choice": 6,
            "dac_num": 32,
            "xbar_polarity": 2,
            "sub_position": 1,
            "group_num": 1,
        },
    )
    matrices["D"] = _expand_matrix(
        "D",
        "压力边界矩阵：观察高非理想器件下设计何时失效",
        {
            "rram_preset": ["P3", "P4"],
            "xbar_size": [(128, 128), (512, 512)],
            "adc_choice": [6, 7],
        },
        {
            "dac_num": 32,
            "xbar_polarity": 2,
            "sub_position": 1,
            "group_num": 1,
            "pe_num": (2, 2),
            "tile_connection": 2,
            "inter_tile_bw": 80,
        },
    )
    return matrices


def _serialize_rows(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        cur = dict(row)
        for key in DIM_ORDER:
            cur[key] = encode_dim_value(cur[key])
        out.append(cur)
    return out


def _write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    headers = ["matrix_name", "matrix_point_id", "matrix_purpose"] + DIM_ORDER
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})


def main() -> None:
    parser = argparse.ArgumentParser(description="Export paper-oriented RRAM v2 experiment matrices.")
    parser.add_argument("--output-dir", default="artifacts/dse/matrices/rram_v2", help="Directory to write matrix CSV files.")
    args = parser.parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    matrices = _matrix_definitions()
    combined: List[Dict[str, object]] = []
    for name, rows in matrices.items():
        serial = _serialize_rows(rows)
        _write_csv(out_dir / f"matrix_{name}.csv", serial)
        combined.extend(serial)
        print(f"[matrix] {name}: {len(serial)} points -> {out_dir / f'matrix_{name}.csv'}")

    _write_csv(out_dir / "matrix_all.csv", combined)
    print(f"[matrix] all: {len(combined)} points -> {out_dir / 'matrix_all.csv'}")


if __name__ == "__main__":
    main()
