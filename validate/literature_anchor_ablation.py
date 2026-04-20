#!/usr/bin/env python3
"""
Literature-anchor ablation for MNSIM baseline vs pim_sim PPA corrections.

Current scope:
    - ISSCC 2020 Paper 33.2 RRAM macro

Current PPA boundary:
    - MNSIM baseline uses the PE-level macro path from validate/literature_anchor_baseline.py
    - pim_sim contributes an ADC-only PPA correction via Walden FOM
    - pim_sim asymmetric device noise / IR-drop remain accuracy-path only in this repo
"""

from __future__ import annotations

import argparse
import csv
import io
from contextlib import redirect_stdout
from dataclasses import dataclass
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import configparser as cp
from MNSIM.Hardware_Model.PE import ProcessElement
from pim_sim.ppa.chip_profiles import get_chip_profile, profile_delta
from pim_sim.ppa.estimator import adc_ppa_delta
from validate.literature_anchor_baseline import CHIPS, METRICS, ChipSpec, rel_error_pct


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    label: str
    note: str


VARIANTS = (
    VariantSpec(
        variant_id="mnsim_baseline",
        label="MNSIM baseline",
        note="Unmodified PE-level MNSIM baseline.",
    ),
    VariantSpec(
        variant_id="pim_sim_chip_profile",
        label="pim_sim chip profile",
        note=(
            "Apply the registered chip-specific pim_sim profile. "
            "This path is the default pim_sim+MNSIM+baseline result for literature-anchor comparison."
        ),
    ),
    VariantSpec(
        variant_id="pim_sim_adc_walden",
        label="pim_sim ADC Walden",
        note=(
            "Apply pim_sim ADC-only Walden-FOM correction on top of the MNSIM baseline. "
            "This remains a generic sensitivity model / negative control here. "
            "Device asymmetry and IR-drop are not included because the current repo "
            "only wires them into the accuracy path."
        ),
    ),
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
        default=str(ROOT / "validate" / "output" / "literature_anchor" / "ablation_rram_isscc2020_33p2.csv"),
        help="CSV output path.",
    )
    return parser.parse_args()


def evaluate_rram_pe_detail(config_path: Path) -> dict[str, float]:
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
    total_energy_nj = total_ops / pe.equ_energy_efficiency
    pe_config = cp.ConfigParser()
    pe_config.read(str(config_path), encoding="UTF-8")
    digital_period = 1 / float(pe_config.get("Digital module", "Digital_Frequency")) * 1e3
    multiple_time = math.ceil(8 / pe.DAC_precision)
    decoder1_8 = 0.27933
    row_per_dac = math.ceil(pe.subarray_size / (pe.PE_group_DAC_num / pe.subarray_num))
    decoder_depth = 1
    while row_per_dac > 0:
        row_per_dac //= 8
        decoder_depth += 1
    decoder_latency = decoder_depth * decoder1_8
    mux8_1 = 32.744 * 1e-3
    column_per_adc = math.ceil(pe.xbar_size[1] / (pe.PE_group_ADC_num / pe.subarray_num))
    mux_depth = 1
    while column_per_adc > 0:
        column_per_adc //= 8
        mux_depth += 1
    mux_latency = mux_depth * mux8_1
    with redirect_stdout(io.StringIO()):
        pe.calculate_xbar_read_latency()
        pe.calculate_DAC_latency()
        pe.calculate_ADC_latency()
    component_energy_nj = {
        "xbar_energy_nj": multiple_time * pe.xbar_read_latency * pe.PE_xbar_read_power,
        "dac_energy_nj": multiple_time * pe.DAC_latency * pe.PE_DAC_read_power,
        "adc_energy_nj": multiple_time * pe.ADC_latency * pe.PE_ADC_read_power,
        "ireg_energy_nj": (digital_period + multiple_time * digital_period) * pe.PE_iReg_read_power,
        "shiftreg_energy_nj": multiple_time * digital_period * pe.PE_shiftreg_read_power,
        "input_demux_energy_nj": multiple_time * decoder_latency * pe.input_demux_read_power,
        "adder_energy_nj": math.ceil(math.log2(pe.group_num)) * digital_period * pe.PE_adder_read_power,
        "output_mux_energy_nj": multiple_time * mux_latency * pe.output_mux_read_power,
        "oreg_energy_nj": digital_period * pe.PE_oReg_read_power,
    }
    return {
        "area_mm2": pe.PE_area / 1e6,
        "latency_ns": total_ops / pe.equ_power,
        "energy_efficiency_tops_per_w": pe.equ_energy_efficiency / 1000.0,
        "total_ops": total_ops,
        "total_energy_nj": total_energy_nj,
        "xbar_cols": pe.PE_group_ADC_num,
        "n_xbars": pe.PE_xbar_num,
        **component_energy_nj,
    }


def apply_adc_walden_correction(config_path: Path, baseline: dict[str, float]) -> dict[str, float]:
    # Use the active MNSIM ADC sample rate, including the special Qi Liu preset behavior.
    from MNSIM.Hardware_Model.ADC import ADC as MNSIMADC

    adc = MNSIMADC(str(config_path))
    adc.calculate_ADC_precision()
    adc.calculate_ADC_sample_rate()
    target_enob = adc.ADC_precision
    sample_rate_gsps = adc.ADC_sample_rate

    delta = adc_ppa_delta(
        str(config_path),
        target_enob=target_enob,
        xbar_cols=int(baseline["xbar_cols"]),
        n_xbars=int(baseline["n_xbars"]),
        sample_rate_gsps=sample_rate_gsps,
    )
    corrected_total_energy_nj = baseline["total_energy_nj"] + delta.energy_nj
    if corrected_total_energy_nj <= 0:
        raise ValueError(
            f"ADC correction produced non-positive total energy: {corrected_total_energy_nj} nJ"
        )
    return {
        "area_mm2": baseline["area_mm2"] + delta.area_um2 / 1e6,
        "latency_ns": baseline["latency_ns"] + delta.latency_ns,
        "energy_efficiency_tops_per_w": baseline["total_ops"] / corrected_total_energy_nj / 1000.0,
        "delta_area_mm2": delta.area_um2 / 1e6,
        "delta_latency_ns": delta.latency_ns,
        "delta_energy_nj": delta.energy_nj,
    }


def apply_registered_chip_profile(chip_id: str, config_path: Path, baseline: dict[str, float]) -> dict[str, float]:
    delta = profile_delta(chip_id, config_path, baseline)
    corrected_total_energy_nj = baseline["total_energy_nj"] + delta.energy_nj
    if corrected_total_energy_nj <= 0:
        raise ValueError(
            f"chip profile produced non-positive total energy: {corrected_total_energy_nj} nJ"
        )
    return {
        "area_mm2": baseline["area_mm2"] + delta.area_um2 / 1e6,
        "latency_ns": baseline["latency_ns"] + delta.latency_ns,
        "energy_efficiency_tops_per_w": baseline["total_ops"] / corrected_total_energy_nj / 1000.0,
        "delta_area_mm2": delta.area_um2 / 1e6,
        "delta_latency_ns": delta.latency_ns,
        "delta_energy_nj": delta.energy_nj,
    }


def main() -> int:
    args = parse_args()
    spec: ChipSpec = CHIPS[args.chip]
    if not spec.config_path.exists():
        raise FileNotFoundError(f"missing config: {spec.config_path}")

    baseline = evaluate_rram_pe_detail(spec.config_path)
    chip_profile = get_chip_profile(spec.chip_id)
    variant_predictions: dict[str, dict[str, float]] = {
        "mnsim_baseline": {
            "area_mm2": baseline["area_mm2"],
            "latency_ns": baseline["latency_ns"],
            "energy_efficiency_tops_per_w": baseline["energy_efficiency_tops_per_w"],
            "delta_area_mm2": 0.0,
            "delta_latency_ns": 0.0,
            "delta_energy_nj": 0.0,
        },
        "pim_sim_chip_profile": apply_registered_chip_profile(spec.chip_id, spec.config_path, baseline),
        "pim_sim_adc_walden": apply_adc_walden_correction(spec.config_path, baseline),
    }

    baseline_abs_err = {
        metric_key: abs(
            rel_error_pct(
                variant_predictions["mnsim_baseline"][metric_key],
                spec.silicon_published[metric_key],
            )
        )
        for metric_key, _, _ in METRICS
    }

    rows: list[dict[str, object]] = []
    for variant in VARIANTS:
        pred = variant_predictions[variant.variant_id]
        for metric_key, metric_label, unit in METRICS:
            silicon_ref = spec.silicon_published[metric_key]
            rel_vs_silicon = rel_error_pct(pred[metric_key], silicon_ref)
            abs_rel_vs_silicon = abs(rel_vs_silicon)
            baseline_err = baseline_abs_err[metric_key]
            if baseline_err == 0:
                err_reduction_pct = 0.0
            else:
                err_reduction_pct = (baseline_err - abs_rel_vs_silicon) / baseline_err * 100.0
            baseline_value = variant_predictions["mnsim_baseline"][metric_key]
            model_delta_vs_baseline_pct = rel_error_pct(pred[metric_key], baseline_value)
            rows.append(
                {
                    "chip_id": spec.chip_id,
                    "chip_label": spec.label,
                    "variant_id": variant.variant_id,
                    "variant_label": variant.label,
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "unit": unit,
                    "mnsim_baseline_value": f"{baseline_value:.6f}",
                    "predicted_value": f"{pred[metric_key]:.6f}",
                    "silicon_published_value": f"{silicon_ref:.6f}",
                    "rel_error_vs_silicon_pct": f"{rel_vs_silicon:.4f}",
                    "abs_rel_error_vs_silicon_pct": f"{abs_rel_vs_silicon:.4f}",
                    "abs_rel_error_reduction_vs_baseline_pct": f"{err_reduction_pct:.4f}",
                    "model_delta_vs_baseline_pct": f"{model_delta_vs_baseline_pct:.4f}",
                    "delta_area_mm2": f"{pred['delta_area_mm2']:.6f}",
                    "delta_latency_ns": f"{pred['delta_latency_ns']:.6f}",
                    "delta_energy_nj": f"{pred['delta_energy_nj']:.6f}",
                    "config_path": str(spec.config_path),
                    "assumption_note": f"{spec.assumption_note} {variant.note} {chip_profile.note if variant.variant_id == 'pim_sim_chip_profile' else ''}",
                }
            )

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(spec.label)
    print(f"config: {spec.config_path}")
    print(f"output: {output_csv}")
    for variant in VARIANTS:
        pred = variant_predictions[variant.variant_id]
        print(
            f"{variant.variant_id}: "
            f"area={pred['area_mm2']:.4f} mm^2, "
            f"latency={pred['latency_ns']:.4f} ns, "
            f"eff={pred['energy_efficiency_tops_per_w']:.4f} TOPS/W"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
