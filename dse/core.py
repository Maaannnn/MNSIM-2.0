#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core DSE infrastructure: design space definition, evaluation, and data types.

This is the single source of truth for SPACE and EvalResult.
All algorithms import from here — never define SPACE or evaluate_config locally.
"""
from __future__ import annotations

import configparser as cp
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from MNSIM.Interface.interface import TrainTestInterface
from MNSIM.Accuracy_Model.Weight_update import weight_update
from MNSIM.Mapping_Model.Tile_connection_graph import TCG
from MNSIM.Latency_Model.Model_latency import Model_latency
from MNSIM.Area_Model.Model_Area import Model_area
from MNSIM.Power_Model.Model_inference_power import Model_inference_power
from MNSIM.Energy_Model.Model_energy import Model_energy


# ---------------------------------------------------------------------------
# Design Space Definition
# ---------------------------------------------------------------------------

SPACE: Dict[str, Dict[str, Any]] = {
    "xbar_size": {
        "section": "Crossbar level",
        "key": "Xbar_Size",
        # must satisfy xbar_row % Subarray_Size == 0 (default Subarray_Size=256)
        "values": [(256, 256), (512, 512)],
    },
    "adc_choice": {
        "section": "Interface level",
        "key": "ADC_Choice",
        "values": [4, 6, 7, 8],
    },
    "dac_choice": {
        "section": "Interface level",
        "key": "DAC_Choice",
        "values": [1, 2, 3, 4],
    },
    "pe_num": {
        "section": "Tile level",
        "key": "PE_Num",
        "values": [(2, 2), (4, 4), (8, 8)],
    },
    "tile_connection": {
        "section": "Architecture level",
        "key": "Tile_Connection",
        "values": [0, 1, 2, 3],
    },
    "inter_tile_bw": {
        "section": "Tile level",
        "key": "Inter_Tile_Bandwidth",
        "values": [10, 20, 40, 80],
    },
    "intra_tile_bw": {
        "section": "Tile level",
        "key": "Intra_Tile_Bandwidth",
        "values": [512, 1024, 2048],
    },
}

DIM_NAMES: list[str] = list(SPACE.keys())


def space_size() -> int:
    """Total number of configurations in the design space."""
    n = 1
    for d in DIM_NAMES:
        n *= len(SPACE[d]["values"])
    return n


# ---------------------------------------------------------------------------
# Value serialisation helpers
# ---------------------------------------------------------------------------

def encode_dim_value(v: Any) -> str:
    """Encode a SPACE dimension value to a safe CSV string (no commas in tuples)."""
    if isinstance(v, tuple):
        return "x".join(str(x) for x in v)
    return str(v)


def decode_dim_value(dim: str, s: str) -> Any:
    """Decode a CSV string back to the original SPACE value type."""
    original = SPACE[dim]["values"][0]
    if isinstance(original, tuple):
        parts = s.split("x")
        return tuple(int(p) for p in parts)
    elif isinstance(original, int):
        return int(s)
    elif isinstance(original, float):
        return float(s)
    return s


def _to_ini_value(v: Any) -> str:
    """Convert a SPACE value to ConfigParser format."""
    if isinstance(v, tuple):
        return ",".join(str(x) for x in v)
    return str(v)


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def write_temp_config(base_config: str, config_values: Dict[str, Any]) -> str:
    """
    Write a temporary .ini file with overridden SPACE parameters.
    Caller is responsible for deleting the returned path.
    """
    parser = cp.ConfigParser()
    parser.read(base_config, encoding="UTF-8")
    for dim, v in config_values.items():
        meta = SPACE[dim]
        parser.set(meta["section"], meta["key"], _to_ini_value(v))
    fd, path = tempfile.mkstemp(prefix="mnsim_dse_", suffix=".ini")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)
    return path


# ---------------------------------------------------------------------------
# Result data type
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """
    Raw hardware simulation result for one configuration.

    Algorithm-agnostic: no scalarized objective, no penalty.
    Algorithms derive their own metrics from these fields locally.
    """
    latency_ns: float
    area_um2: float
    power_w: float
    energy_nj: float
    accuracy: Optional[float]  # None when run_accuracy=False
    elapsed_s: float
    config: Dict[str, Any]     # config dict matching SPACE keys

    def obj_vector(self) -> Tuple[float, float, float]:
        """Canonical 3-objective vector (minimize all): (latency, energy, area)."""
        return (self.latency_ns, self.energy_nj, self.area_um2)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_config(
    sim_config_path: str,
    nn_name: str,
    weights_path: str,
    config_values: Dict[str, Any],
    run_accuracy: bool = False,
    enable_saf: bool = True,
    enable_variation: bool = False,
    enable_rratio: bool = False,
    fixed_qrange: bool = False,
    device: str = "cpu",
    dataset_module: str = "MNSIM.Interface.cifar10",
) -> EvalResult:
    """
    Evaluate a single hardware configuration by running the MNSIM simulator.

    Returns an EvalResult with all hardware metrics.
    Accuracy simulation is optional (slow, ~5-10× slower than hardware-only).
    """
    t0 = time.time()

    test_if = TrainTestInterface(
        network_module=nn_name,
        dataset_module=dataset_module,
        SimConfig_path=sim_config_path,
        weights_file=weights_path,
        device=device,
    )
    structure = test_if.get_structure()
    tcg = TCG(structure, sim_config_path)

    latency = Model_latency(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    latency.calculate_model_latency(mode=1)
    latency_ns = float(max(max(latency.finish_time)))

    area = Model_area(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    power = Model_inference_power(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    energy = Model_energy(
        NetStruct=structure,
        SimConfig_path=sim_config_path,
        TCG_mapping=tcg,
        model_latency=latency,
        model_power=power,
    )
    area_um2 = float(area.arch_total_area)
    power_w = float(power.arch_total_power)
    energy_nj = float(energy.arch_total_energy)

    accuracy = None
    if run_accuracy:
        bits = test_if.get_net_bits()
        bits_after = weight_update(
            sim_config_path,
            bits,
            is_Variation=enable_variation,
            is_SAF=enable_saf,
            is_Rratio=enable_rratio,
        )
        adc_action = "FIX" if fixed_qrange else "SCALE"
        accuracy = float(test_if.set_net_bits_evaluate(bits_after, adc_action=adc_action))

    return EvalResult(
        latency_ns=latency_ns,
        area_um2=area_um2,
        power_w=power_w,
        energy_nj=energy_nj,
        accuracy=accuracy,
        elapsed_s=time.time() - t0,
        config=dict(config_values),
    )
