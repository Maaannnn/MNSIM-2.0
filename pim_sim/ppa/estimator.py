"""
pim_sim.ppa.estimator
=====================
Parametric PPA (Power-Performance-Area) estimator that replaces
MNSIM's hardcoded ADC lookup with the Walden FOM model.

Purpose
-------
MNSIM computes PPA by instantiating hardware model objects
(ADC, Crossbar, Buffer, etc.) from SimConfig.ini and summing their
contributions.  The ADC component is constrained to 9 choices.

pim_sim.ppa.estimator provides:
  1. ``adc_ppa_delta`` — computes the PPA *difference* between the
     MNSIM baseline ADC and a WaldenADCModel, which can be applied
     as a correction to MNSIM's PPA output.
  2. ``parametric_adc_sweep`` — sweeps ADC bits and returns PPA curves
     for sensitivity analysis.

Integration pattern
-------------------
In dse/core.evaluate_config, after computing MNSIM PPA:

    from pim_sim.ppa.estimator import adc_ppa_delta

    delta = adc_ppa_delta(
        sim_config_path,
        target_enob=config_values.get("adc_bits", 6),
        xbar_cols=config_values.get("xbar_cols", 128),
        n_xbars=<total xbar count from structure>,
    )
    energy_nj += delta.energy_nj
    area_um2  += delta.area_um2
    power_w   += delta.power_w
"""

from __future__ import annotations

import configparser as cp
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from MNSIM.Hardware_Model.ADC import ADC as MNSIMADC
from pim_sim.array.adc_model import WaldenADCModel, _MNSIM_ADC_TABLE


@dataclass
class PPADelta:
    """Signed PPA correction: positive = pim_sim model costs more than MNSIM."""
    energy_nj: float = 0.0
    area_um2: float = 0.0
    power_w: float = 0.0
    latency_ns: float = 0.0

    def as_dict(self) -> dict:
        return {
            "delta_energy_nj": self.energy_nj,
            "delta_area_um2": self.area_um2,
            "delta_power_w": self.power_w,
            "delta_latency_ns": self.latency_ns,
        }


def adc_ppa_delta(
    sim_config_path: str,
    target_enob: float,
    xbar_cols: int,
    n_xbars: int,
    sample_rate_gsps: float = 1.0,
) -> PPADelta:
    """Return the PPA delta between MNSIM ADC and a parametric ADC.

    One ADC is instantiated per column of each crossbar.  The delta
    accounts for the total ADC population across all xbars.

    Parameters
    ----------
    sim_config_path:
        Path to SimConfig.ini (used to read the current ADC_Choice).
    target_enob:
        Desired ADC bits in the pim_sim model.
    xbar_cols:
        Number of columns per crossbar (= ADC count per xbar).
    n_xbars:
        Total number of crossbars in the design.
    sample_rate_gsps:
        Desired ADC sample rate for parametric model.

    Returns
    -------
    PPADelta with signed differences (pim_sim - MNSIM).
    """
    # MNSIM baseline from the actual hardware model implementation.
    # This is important for ADC_Choice=9 ("Qi Liu"), whose latency path
    # is special-cased in MNSIM and does not follow the generic (bits+2)/fs formula.
    baseline_adc = MNSIMADC(sim_config_path)
    baseline_adc.calculate_ADC_area()
    baseline_adc.calculate_ADC_power()
    baseline_adc.calculate_ADC_latency()
    mnsim_power = baseline_adc.ADC_power
    mnsim_area = baseline_adc.ADC_area
    mnsim_latency = baseline_adc.ADC_latency
    mnsim_energy = mnsim_latency * mnsim_power   # nJ = ns × W

    # pim_sim parametric
    pim_adc = WaldenADCModel(enob=target_enob, sample_rate_gsps=sample_rate_gsps)
    pim_power = pim_adc.power_w()
    pim_area = pim_adc.area_um2()
    pim_latency = pim_adc.latency_ns()
    pim_energy = pim_latency * pim_power   # nJ = ns × W

    total_adcs = xbar_cols * n_xbars

    return PPADelta(
        energy_nj=(pim_energy - mnsim_energy) * total_adcs,
        area_um2=(pim_area - mnsim_area) * total_adcs,
        power_w=(pim_power - mnsim_power) * total_adcs,
        latency_ns=pim_latency - mnsim_latency,
    )


def parametric_adc_sweep(
    enob_values: List[float],
    xbar_cols: int,
    n_xbars: int,
    sample_rate_gsps: float = 1.0,
) -> List[dict]:
    """Sweep ADC bits and return per-bit PPA totals.

    Parameters
    ----------
    enob_values:
        List of ENOB values to sweep (e.g. [4, 6, 8, 10]).
    xbar_cols, n_xbars:
        Same as adc_ppa_delta.
    sample_rate_gsps:
        ADC sample rate for all models.

    Returns
    -------
    List of dicts with keys: enob, total_power_mw, total_area_mm2,
    total_energy_nj_per_inference, latency_ns.
    """
    total_adcs = xbar_cols * n_xbars
    results = []
    for enob in enob_values:
        adc = WaldenADCModel(enob=enob, sample_rate_gsps=sample_rate_gsps)
        results.append({
            "enob": enob,
            "total_power_mw": adc.power_w() * total_adcs * 1e3,
            "total_area_mm2": adc.area_um2() * total_adcs * 1e-6,
            "total_energy_nj_per_cycle": adc.energy_j() * total_adcs * 1e9,
            "latency_ns": adc.latency_ns(),
            "single_adc_summary": adc.summary(),
        })
    return results
