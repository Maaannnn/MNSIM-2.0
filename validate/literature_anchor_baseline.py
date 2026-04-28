#!/usr/bin/env python3
"""
PE-level literature-anchor baseline for MNSIM validation.

Current scope:
    - ISSCC 2020 Paper 33.2 RRAM macro (Q. Liu et al.)
    - ISSCC 2022 Paper 11.7 SRAM CIM macro (J.-W. Yan et al.)

This script intentionally uses MNSIM's ProcessElement path instead of main.py so
T8.1 can reproduce macro-level PPA without first adding a custom MLP/MNIST
network definition. The output is a CSV under validate/output/literature_anchor/.

Per-chip metrics: RRAM anchor reports Latency (ns); SRAM anchor reports
Performance (GOPS) — matching MNSIM 2.0 Table IV's heterogeneous metric set.
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
from mnsim_adapter import available_chips, load_chip


GENERATED_CONFIG_DIR = ROOT / "validate" / "output" / "literature_anchor" / "generated_configs"


@dataclass(frozen=True)
class ChipSpec:
    """Bundle of reference-value metadata for a literature-anchor chip.

    The SimConfig.ini is *not* stored here — it is regenerated on demand
    from ``mnsim_adapter.load_chip(chip_id)`` via :func:`resolve_config_path`.

    ``metrics`` picks which of the three (area, latency OR performance,
    energy efficiency) triples this chip reports — MNSIM Table IV uses
    Latency for analog RRAM macros and Performance (GOPS) for digital
    SRAM macros. ``applicable_variants`` filters which ablation variants
    make sense (e.g. the Walden ADC correction is N/A for ADC-less SRAM).
    """

    chip_id: str
    label: str
    assumption_note: str
    mnsim_table_iv: dict[str, float]
    silicon_published: dict[str, float]
    metrics: tuple[tuple[str, str, str], ...]
    applicable_variants: tuple[str, ...]


def resolve_config_path(chip_id: str) -> Path:
    """Render the ChipProfile for ``chip_id`` to a cached INI and return it."""
    if chip_id not in available_chips():
        raise KeyError(
            f"Chip '{chip_id}' is not registered in mnsim_adapter; "
            f"available: {available_chips()}"
        )
    GENERATED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_CONFIG_DIR / f"SimConfig__{chip_id}.ini"
    load_chip(chip_id).to_mnsim_ini(out)
    return out


RRAM_METRICS: tuple[tuple[str, str, str], ...] = (
    ("area_mm2", "Area", "mm^2"),
    ("latency_ns", "Latency", "ns"),
    ("energy_efficiency_tops_per_w", "Energy efficiency", "TOPS/W"),
)

SRAM_METRICS: tuple[tuple[str, str, str], ...] = (
    ("area_mm2", "Area", "mm^2"),
    ("performance_gops", "Performance", "GOPS"),
    ("energy_efficiency_tops_per_w", "Energy efficiency", "TOPS/W"),
)

# Default ablation variants (matches VARIANTS in literature_anchor_ablation.py).
# Chips that cannot meaningfully use a variant (e.g. ADC-less SRAM and the
# Walden-FOM ADC overlay) override this tuple.
_DEFAULT_VARIANTS = (
    "mnsim_table_iv_cited",
    "mnsim_local_repro",
    "pim_sim_chip_profile",
    "pim_sim_adc_walden",
)


CHIPS: dict[str, ChipSpec] = {
    "rram_isscc2020_33p2": ChipSpec(
        chip_id="rram_isscc2020_33p2",
        label="ISSCC 2020 Paper 33.2 RRAM macro",
        assumption_note=(
            "PE-level macro baseline. Device_Resistance uses a Fig. 33.2.S1-"
            "derived approximate pair (20 MOhm / 60 kOhm) from the tighter "
            "\"five 10ns\" distribution; Device_Variation stays at 1%; "
            "ADC_Choice=9 uses the built-in Qi Liu preset; DAC is user-defined "
            "8-bit to avoid DAC_Choice=1 time-multiplex inflation and "
            "DAC_Choice=6 power-scale issues in the current code path. "
            "Config regenerated from mnsim_adapter.load_chip('rram_isscc2020_33p2')."
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
        metrics=RRAM_METRICS,
        applicable_variants=_DEFAULT_VARIANTS,
    ),
    "rram_isscc2020_15p4": ChipSpec(
        chip_id="rram_isscc2020_15p4",
        label="ISSCC 2020 Paper 15.4 RRAM macro (TSMC 22 nm)",
        assumption_note=(
            "Second RRAM silicon anchor (not in MNSIM 2.0 Table IV). 22 nm "
            "TSMC foundry 1T1R SLC ReRAM, 2 Mb testchip. Silicon-published "
            "operating point is 4bIN-4bW-11bOUT at VDD=0.8 V (tAC=18.3 ns, "
            "EF=28.93 TOPS/W). Area=6 mm^2 is the testchip (2x3 mm including "
            "IO pads and testmodes); pure macro area not disclosed. "
            "HRS/LRS (1 MΩ / 10 kΩ), cell area (0.10 um^2), and digital "
            "frequency (1 GHz) are proxies scaled from Liu 33.2. DbSO-CSA "
            "modelled as user-defined 6-bit ADC (3 cycles x 2b)."
        ),
        # Chip is not in MNSIM Table IV; duplicating silicon here keeps the
        # baseline CSV schema stable, and applicable_variants drops the
        # mnsim_table_iv_cited ablation variant.
        mnsim_table_iv={
            "area_mm2": 6.00,
            "latency_ns": 18.30,
            "energy_efficiency_tops_per_w": 28.93,
        },
        silicon_published={
            "area_mm2": 6.00,
            "latency_ns": 18.30,
            "energy_efficiency_tops_per_w": 28.93,
        },
        metrics=RRAM_METRICS,
        applicable_variants=(
            "mnsim_local_repro",
            "pim_sim_chip_profile",
            "pim_sim_adc_walden",
        ),
    ),
    "rram_vlsi2018_mochida": ChipSpec(
        chip_id="rram_vlsi2018_mochida",
        label="VLSI 2018 Mochida Panasonic analog ReRAM (40 nm)",
        assumption_note=(
            "Third RRAM silicon anchor (not in MNSIM 2.0 Table IV). 40 nm "
            "Panasonic 1T-1R analog ReRAM, 4 M synapses / 2 M weights. "
            "Silicon-published 40 nm row of Table I: Area=2.71 mm^2, 0.66 "
            "TOPS, EF=66.5 TOPS/W at 1.1 V on MNIST 14x14 MLP (196-64-10). "
            "MNSIM models this as a binary-cell analog PIM with a 1-bit "
            "current-comparator SA; the Walden-FoM ADC overlay is N/A. "
            "Large silicon vs MNSIM gap is expected — the chip is truly "
            "analog (30 µA cell-current dynamic range), and MNSIM only "
            "models binary cell states. This anchor's role is to surface "
            "that modeling-scope boundary."
        ),
        mnsim_table_iv={
            "area_mm2": 2.71,
            "performance_gops": 660.0,
            "energy_efficiency_tops_per_w": 66.50,
        },
        silicon_published={
            "area_mm2": 2.71,
            "performance_gops": 660.0,
            "energy_efficiency_tops_per_w": 66.50,
        },
        metrics=SRAM_METRICS,  # report Performance (GOPS), like Yan — paper's headline metric is TOPS not latency.
        # 1-bit SA readout: Walden-FoM ADC overlay is N/A (no multi-bit ADC to replace).
        applicable_variants=(
            "mnsim_local_repro",
            "pim_sim_chip_profile",
        ),
    ),
    "sram_isscc2022_11p7": ChipSpec(
        chip_id="sram_isscc2022_11p7",
        label="ISSCC 2022 Paper 11.7 SRAM CIM macro",
        assumption_note=(
            "SRAM null-control anchor. 28 nm 6T bitcell (Device_Area=0.25 um^2 per "
            "MNSIM SimConfig.ini line 12); 32 compartments x 16-row x 64-col per "
            "MNSIM Table III; digital PIM (PIM_Type=1) forces ADC_Choice=8 (SA); "
            "Logic_Op=0 (AND); 333 MHz clock. Config regenerated from "
            "mnsim_adapter.load_chip('sram_isscc2022_11p7'). pim_sim overlays are "
            "deliberately zero-delta here — the three pillars are all RRAM-specific."
        ),
        mnsim_table_iv={
            "area_mm2": 0.034,
            "performance_gops": 16.22,
            "energy_efficiency_tops_per_w": 28.23,
        },
        silicon_published={
            "area_mm2": 0.030,
            "performance_gops": 16.00,
            "energy_efficiency_tops_per_w": 27.38,
        },
        metrics=SRAM_METRICS,
        # ADC-less chip: Walden-FOM ADC overlay is N/A.
        applicable_variants=(
            "mnsim_table_iv_cited",
            "mnsim_local_repro",
            "pim_sim_chip_profile",
        ),
    ),
}

# Backwards-compat alias; downstream scripts may still import METRICS for
# legacy single-chip paths. Per-chip evaluation should use spec.metrics.
METRICS = RRAM_METRICS


def default_baseline_output_path(chip_id: str) -> Path:
    suffix = "baseline_mnsim_vs_issc.csv" if chip_id == "rram_isscc2020_33p2" else f"baseline_{chip_id}.csv"
    return ROOT / "validate" / "output" / "literature_anchor" / suffix


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
        default=None,
        help="CSV output path. Defaults to baseline_<chip>.csv alongside the RRAM anchor.",
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


def _summary_line(spec: ChipSpec, observed: dict[str, float]) -> str:
    parts = [f"area={observed['area_mm2']:.4f} mm^2"]
    for metric_key, metric_label, unit in spec.metrics:
        if metric_key == "area_mm2":
            continue
        parts.append(f"{metric_label.lower()}={observed[metric_key]:.4f} {unit}")
    return "summary: " + ", ".join(parts)


def main() -> int:
    args = parse_args()
    spec = CHIPS[args.chip]
    config_path = resolve_config_path(spec.chip_id)

    observed = evaluate_rram_pe(config_path)

    output_csv = Path(args.output_csv) if args.output_csv else default_baseline_output_path(spec.chip_id)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for metric_key, metric_label, unit in spec.metrics:
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
                "config_path": str(config_path),
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
    print(f"config: {config_path}")
    print(f"output: {output_csv}")
    print(_summary_line(spec, observed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
