#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core DSE infrastructure: design space definition, evaluation, and data types.

This is the single source of truth for SPACE and EvalResult.
All algorithms import from here — never define SPACE or evaluate_config locally.
"""
from __future__ import annotations

import configparser as cp
import copy
import os
import random
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

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

RRAM_PRESETS: Dict[str, Dict[str, Dict[str, str]]] = {
    "P0": {
        "Device level": {
            "Device_Resistance": "1e6,1e4",
            "Device_Variation": "0.5",
            "Device_SAF": "0.01,0.01",
        },
    },
    "P1": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "1.0",
            "Device_SAF": "0.05,0.05",
        },
    },
    "P2": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "3.0",
            "Device_SAF": "0.05,0.05",
        },
    },
    "P3": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "1.5",
            "Device_SAF": "0.5,0.5",
        },
    },
    "P4": {
        "Device level": {
            "Device_Resistance": "5e5,5e4",
            "Device_Variation": "5.0",
            "Device_SAF": "1.0,1.0",
        },
    },
}


SPACE_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "rram_full": {
        "rram_preset": {
            "values": list(RRAM_PRESETS.keys()),
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (256, 256), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7, 8],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 64, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [1, 2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1, 2, 4],
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
    },
    "rram_v2": {
        "rram_preset": {
            "values": ["P0", "P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2, 3],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [40, 80],
        },
    },
    "rram_formal_v3": {
        "rram_preset": {
            "values": ["P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [80],
        },
    },
    "rram_guidance_v4": {
        "rram_preset": {
            "values": ["P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (256, 256), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2, 3],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [40, 80],
        },
    },
}

SPACE: Dict[str, Dict[str, Any]] = {}
DIM_NAMES: list[str] = []
ACTIVE_SPACE_PROFILE: str = ""


def available_space_profiles() -> list[str]:
    return sorted(SPACE_PROFILES.keys())


def current_space_profile() -> str:
    return ACTIVE_SPACE_PROFILE


def apply_space_profile(profile: str) -> None:
    """Mutate the global SPACE/DIM_NAMES in-place so imported references stay valid."""
    global ACTIVE_SPACE_PROFILE
    if profile not in SPACE_PROFILES:
        raise KeyError(f"Unknown space profile: {profile}. choices={available_space_profiles()}")
    SPACE.clear()
    SPACE.update(copy.deepcopy(SPACE_PROFILES[profile]))
    DIM_NAMES[:] = list(SPACE.keys())
    ACTIVE_SPACE_PROFILE = profile


DEFAULT_SPACE_PROFILE = os.environ.get("MNSIM_DSE_SPACE_PROFILE", "rram_v2")
apply_space_profile(DEFAULT_SPACE_PROFILE)


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


def _apply_rram_preset(parser: cp.ConfigParser, preset: str) -> None:
    overrides = RRAM_PRESETS[preset]
    for section, kv in overrides.items():
        for key, value in kv.items():
            parser.set(section, key, value)


def _apply_xbar_size(parser: cp.ConfigParser, size: Tuple[int, int]) -> None:
    row, col = size
    parser.set("Crossbar level", "Xbar_Size", f"{row},{col}")
    # Keep the built-in subarray divisibility constraint valid for smaller xbars.
    cur_sub = int(parser.get("Crossbar level", "Subarray_Size"))
    parser.set("Crossbar level", "Subarray_Size", str(min(cur_sub, row)))


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def _apply_config_patch(parser: cp.ConfigParser, config_patch: Optional[Dict[str, Dict[str, Any]]]) -> None:
    if not config_patch:
        return
    for section, kvs in config_patch.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in kvs.items():
            parser.set(section, key, str(value))


def write_temp_config(
    base_config: str,
    config_values: Dict[str, Any],
    *,
    post_patch: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """
    Write a temporary .ini file with overridden SPACE parameters.
    Caller is responsible for deleting the returned path.
    """
    parser = cp.ConfigParser()
    parser.read(base_config, encoding="UTF-8")
    for dim, v in config_values.items():
        if dim == "rram_preset":
            _apply_rram_preset(parser, str(v))
            continue
        if dim == "xbar_size":
            _apply_xbar_size(parser, v)
            continue
        meta = SPACE[dim]
        parser.set(meta["section"], meta["key"], _to_ini_value(v))
    # Re-apply scenario patches after design-space overrides so measured device
    # parameters are not clobbered by nominal preset expansion.
    _apply_config_patch(parser, post_patch)
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


def accuracy_violation(accuracy: Optional[float], accuracy_target: Optional[float]) -> float:
    """Constraint violation amount for minimum accuracy constraint."""
    if accuracy_target is None:
        return 0.0
    if accuracy is None:
        return float("inf")
    return max(0.0, float(accuracy_target) - float(accuracy))


def selection_objective_vector(
    obj_vec: Tuple[float, float, float],
    accuracy: Optional[float],
    accuracy_target: Optional[float],
) -> Tuple[float, ...]:
    """
    Objective vector used inside DSE algorithms.

    Without an accuracy constraint, use the native 3-objective PPA vector.
    With an accuracy constraint, prepend the violation term so the search
    accounts for feasibility before optimizing PPA.
    """
    violation = accuracy_violation(accuracy, accuracy_target)
    if accuracy_target is None:
        return obj_vec
    return (violation,) + obj_vec


def pareto_indices_with_accuracy(records: list[Any], accuracy_target: Optional[float]) -> list[int]:
    """
    Final Pareto set for reporting.

    If an accuracy constraint is active, report the Pareto front among feasible
    points only. If no feasible point exists, fall back to constrained Pareto
    over (violation, latency, energy, area) to expose the least-bad designs.
    """
    from dse.metrics import pareto_indices

    if accuracy_target is None:
        return pareto_indices([r.obj_vector() for r in records])

    feasible = [
        i for i, r in enumerate(records)
        if r.accuracy is not None and r.accuracy >= float(accuracy_target)
    ]
    if feasible:
        local = pareto_indices([records[i].obj_vector() for i in feasible])
        return [feasible[i] for i in local]

    constrained = [
        selection_objective_vector(r.obj_vector(), r.accuracy, accuracy_target)
        for r in records
    ]
    return pareto_indices(constrained)


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
    max_acc_batches: int = 11,
    noise_seed: Optional[int] = None,
    pim_sim_model=None,
    ir_drop_model=None,
) -> EvalResult:
    """
    Evaluate a single hardware configuration by running the MNSIM simulator.

    Returns an EvalResult with all hardware metrics.
    Accuracy simulation is optional (slow, ~5-10× slower than hardware-only).
    """
    t0 = time.time()

    if noise_seed is not None:
        random.seed(int(noise_seed))
        np.random.seed(int(noise_seed))

    test_if = TrainTestInterface(
        network_module=nn_name,
        dataset_module=dataset_module,
        SimConfig_path=sim_config_path,
        weights_file=weights_path,
        device=device,
        max_eval_batches=max_acc_batches,
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
        if pim_sim_model is not None:
            from pim_sim.accuracy.weight_inject import pim_sim_weight_inject
            bits_after = pim_sim_weight_inject(
                sim_config_path,
                bits,
                is_Variation=enable_variation,
                is_SAF=enable_saf,
                is_Rratio=enable_rratio,
                pim_sim_model=pim_sim_model,
                ir_drop_model=ir_drop_model,
                rng_seed=noise_seed,
            )
        else:
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
