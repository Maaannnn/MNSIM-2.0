#!/usr/bin/env python3
"""
PE-level literature-anchor baseline for MNSIM validation.

Current scope:
    - ISSCC 2020 Paper 33.2 RRAM macro (Q. Liu et al.)

This script intentionally uses MNSIM's ProcessElement path instead of main.py so
T8.1 can reproduce macro-level PPA without first adding a custom MLP/MNIST
network definition. The output is a CSV under validate/output/literature_anchor/.
"""

from __future__ import annotations

import argparse
import csv
import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from MNSIM.Hardware_Model.PE import ProcessElement


@dataclass(frozen=True)
class ChipSpec:
    chip_id: str
    label: str
    config_path: Path
    assumption_note: str
    mnsim_table_iv: dict[str, float]
    silicon_published: dict[str, float]


CHIPS: dict[str, ChipSpec] = {
    "rram_isscc2020_33p2": ChipSpec(
        chip_id="rram_isscc2020_33p2",
        label="ISSCC 2020 Paper 33.2 RRAM macro",
        config_path=ROOT / "configs" / "SimConfig_issc2020_33p2.ini",
        assumption_note=(
            "PE-level macro baseline. Device_Resistance uses a Fig. 33.2.S1-"
            "derived approximate pair (20 MOhm / 60 kOhm) from the tighter "
            "\"five 10ns\" distribution; Device_Variation stays at 1%; "
            "ADC_Choice=9 uses the built-in Qi Liu preset; DAC is user-defined "
            "8-bit to avoid DAC_Choice=1 time-multiplex inflation and "
            "DAC_Choice=6 power-scale issues in the current code path. "
            "TODO: replace calibrated PE-level placeholders with the original "
            "MNSIM validation config if recovered."
        ),
        mnsim_table_iv={
            "area_mm2": 3.50,
            "latency_ns": 53.38,
            "energy_efficiency_tops_per_w": 74.44,
        },
        silicon_published={
            "area_mm2": 3.77,
            "latency_ns": 51.10,
            "energy_efficiency_tops_per_w": 78.40,
        },
    ),
}

METRICS = (
    ("area_mm2", "Area", "mm^2"),
    ("latency_ns", "Latency", "ns"),
    ("energy_efficiency_tops_per_w", "Energy efficiency", "TOPS/W"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chip",
        default="rram_isscc2020_33p2",
        choices=sorted(CHIPS.keys()),
        help="Literature-anchor chip to evaluate.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(ROOT / "validate" / "output" / "literature_anchor" / "baseline_mnsim_vs_issc.csv"),
        help="CSV output path.",
    )
    return parser.parse_args()


def rel_error_pct(pred: float, ref: float) -> float:
    if ref == 0:
        return 0.0
    return (pred - ref) / ref * 100.0


def evaluate_rram_pe(config_path: Path) -> dict[str, float]:
    pe = ProcessElement(str(config_path))
    with redirect_stdout(io.StringIO()):
        pe.calculate_PE_area(str(config_path))
        pe.calculate_PE_read_power_fast(
            pe.xbar_size[1],
            pe.xbar_size[0],
            pe.group_num,
            str(config_path),
        )
        pe.calculate_PE_energy_efficiency(str(config_path))

    total_ops = 2.0 * pe.PE_group_DAC_num * pe.PE_group_ADC_num
    macro_area_mm2 = (
        pe.PE_xbar_area + pe.PE_ADC_area + pe.PE_DAC_area + pe.PE_digital_area
    ) / 1e6
    return {
        "area_mm2": pe.PE_area / 1e6,
        "macro_area_mm2": macro_area_mm2,
        "latency_ns": total_ops / pe.equ_power,
        "performance_gops": pe.equ_power,
        "energy_efficiency_tops_per_w": pe.equ_energy_efficiency / 1000.0,
    }


def main() -> int:
    args = parse_args()
    spec = CHIPS[args.chip]
    if not spec.config_path.exists():
        raise FileNotFoundError(f"missing config: {spec.config_path}")

    observed = evaluate_rram_pe(spec.config_path)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for metric_key, metric_label, unit in METRICS:
        pred = observed[metric_key]
        mnsim_ref = spec.mnsim_table_iv[metric_key]
        silicon_ref = spec.silicon_published[metric_key]
        rows.append(
            {
                "chip_id": spec.chip_id,
                "chip_label": spec.label,
                "metric_key": metric_key,
                "metric_label": metric_label,
                "unit": unit,
                "predicted_value": f"{pred:.6f}",
                "mnsim_table_iv_value": f"{mnsim_ref:.6f}",
                "silicon_published_value": f"{silicon_ref:.6f}",
                "rel_error_vs_mnsim_pct": f"{rel_error_pct(pred, mnsim_ref):.4f}",
                "rel_error_vs_silicon_pct": f"{rel_error_pct(pred, silicon_ref):.4f}",
                "config_path": str(spec.config_path),
                "pe_macro_area_mm2": f"{observed['macro_area_mm2']:.6f}",
                "performance_gops": f"{observed['performance_gops']:.6f}",
                "assumption_note": spec.assumption_note,
            }
        )

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(spec.label)
    print(f"config: {spec.config_path}")
    print(f"output: {output_csv}")
    print(
        "summary: "
        f"area={observed['area_mm2']:.4f} mm^2, "
        f"latency={observed['latency_ns']:.4f} ns, "
        f"eff={observed['energy_efficiency_tops_per_w']:.4f} TOPS/W"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
