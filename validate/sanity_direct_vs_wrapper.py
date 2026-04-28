#!/usr/bin/env python3
"""Sanity check: dse.core.evaluate_config vs direct MNSIM call.

Goal: prove that evaluate_config produces identical PPA numbers to a
hand-rolled MNSIM call mimicking main.py. Without this, no historical
or future DSE data is trustworthy.

Compare hardware-only metrics (latency, area, power, energy). Skip
accuracy because variation/SAF are stochastic.

Usage:
    python validate/sanity_direct_vs_wrapper.py [--config CONFIG]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from MNSIM.Interface.interface import TrainTestInterface
from MNSIM.Mapping_Model.Tile_connection_graph import TCG
from MNSIM.Latency_Model.Model_latency import Model_latency
from MNSIM.Area_Model.Model_Area import Model_area
from MNSIM.Power_Model.Model_inference_power import Model_inference_power
from MNSIM.Energy_Model.Model_energy import Model_energy

from dse.core import apply_space_profile, evaluate_config, write_temp_config
from dse.space_catalog import space_hash


# A mid-range config drawn from clean_v1 SPACE
TEST_CONFIG = {
    "rram_preset": "P1",
    "xbar_size": (256, 256),
    "adc_choice": 6,
    "dac_num": 32,
    "xbar_polarity": 2,
    "sub_position": 0,
    "group_num": 1,
    "pe_num": (2, 2),
    "tile_connection": 2,
    "inter_tile_bw": 80,
}


def run_direct(sim_config_path: str, weights: str, nn_name: str = "vgg8"):
    """Mimic main.py's hardware-only path."""
    test_if = TrainTestInterface(
        network_module=nn_name,
        dataset_module="MNSIM.Interface.cifar10",
        SimConfig_path=sim_config_path,
        weights_file=weights,
        device="cpu",
    )
    structure = test_if.get_structure()
    tcg = TCG(structure, sim_config_path)

    latency = Model_latency(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    latency.calculate_model_latency(mode=1)
    latency_ns = float(max(max(latency.finish_time)))

    area = Model_area(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    power = Model_inference_power(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    energy = Model_energy(
        NetStruct=structure, SimConfig_path=sim_config_path,
        TCG_mapping=tcg, model_latency=latency, model_power=power,
    )

    return {
        "latency_ns": latency_ns,
        "area_um2": float(area.arch_total_area),
        "power_w": float(power.arch_total_power),
        "energy_nj": float(energy.arch_total_energy),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", default=str(REPO_ROOT / "SimConfig.ini"))
    parser.add_argument("--weights", default=str(REPO_ROOT / "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--rel-tol", type=float, default=1e-9,
                        help="Relative tolerance below which a metric counts as MATCH.")
    args = parser.parse_args()

    apply_space_profile("clean_v1")
    print(f"SPACE profile: clean_v1 (hash={space_hash('clean_v1')})")
    print(f"Test config: {TEST_CONFIG}")
    print(f"Base SimConfig: {args.base_config}")
    print(f"Weights: {args.weights}")
    print()

    # 1. Generate the temp SimConfig once, both runs use the same file.
    temp_path = write_temp_config(args.base_config, TEST_CONFIG)
    print(f"Generated temp SimConfig: {temp_path}")

    try:
        print("\n=== [A] Direct MNSIM call ===")
        direct = run_direct(temp_path, args.weights, args.nn)
        for k, v in direct.items():
            print(f"  {k}: {v:.6e}")

        print("\n=== [B] dse.core.evaluate_config ===")
        res = evaluate_config(
            sim_config_path=temp_path,
            nn_name=args.nn,
            weights_path=args.weights,
            config_values=TEST_CONFIG,
            run_accuracy=False,
            device="cpu",
        )
        wrapper = {
            "latency_ns": res.latency_ns,
            "area_um2": res.area_um2,
            "power_w": res.power_w,
            "energy_nj": res.energy_nj,
        }
        for k, v in wrapper.items():
            print(f"  {k}: {v:.6e}")
    finally:
        os.remove(temp_path)

    print("\n=== Diff ===")
    all_match = True
    for k in ("latency_ns", "area_um2", "power_w", "energy_nj"):
        d, w = direct[k], wrapper[k]
        rel = abs(d - w) / max(abs(d), 1e-12)
        marker = "MATCH" if rel < args.rel_tol else "MISMATCH"
        if rel >= args.rel_tol:
            all_match = False
        print(f"  {k}: direct={d:.6e}, wrapper={w:.6e}, rel_diff={rel:.2e}  {marker}")

    print()
    if all_match:
        print(">>> Sanity check PASSED: wrapper output is bit-identical to direct MNSIM.")
        return 0
    print(">>> Sanity check FAILED: see MISMATCH lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
