"""
Build pim_sim overlay kwargs from a ChipProfile.

Contract
--------
Returns a dict with these keys (any may be ``None`` if the profile
does not request the corresponding enhancement):

- ``pim_sim_model``   : DeviceModel instance (accuracy-path overlay)
- ``ir_drop_model``   : IRDropModel instance (accuracy-path overlay)
- ``adc_model``       : WaldenADCModel or None (ppa-path overlay)
- ``chip_profile_id`` : str tag for logging / provenance

Callers pass these into ``dse/core.evaluate_config`` or the
literature-anchor ablation script.
"""

from __future__ import annotations

import math
from typing import Any

from mnsim_adapter.chip import ChipProfile


# MNSIM defaults for the "-1 means use built-in" sentinels on xbar wiring.
# See MNSIM/Hardware_Model/Crossbar.py and configs/SimConfig.ini comments.
_MNSIM_DEFAULT_WIRE_RESISTANCE_OHM = 2.82
_MNSIM_DEFAULT_LOAD_RESISTANCE_IS_SQRT_RON_ROFF = True


def _build_device_model(chip: ChipProfile):
    """Derive the accuracy-path DeviceModel for ``chip``.

    Base model comes from ``chip.device.variation`` (symmetric / asymmetric
    Gaussian, or None). If ``chip.circuit.adc.accuracy_bits`` is set AND
    the chip is an analog RRAM macro (NVM + pim_type=0), the base model
    is wrapped in ``PartialSumADCNoiseModel`` to route NeuroSim-style
    partial-sum ADC quantization onto the accuracy path.

    Digital PIM (`pim_type=1`) and SRAM chips skip the wrapper by
    construction: NeuroSim's partial-sum quantization is meaningful only
    for analog-domain MACs where the ADC reads a multi-level bitline.
    """
    from pim_sim.device.factory import device_model_from_variation
    from pim_sim.device.model import (
        PartialSumADCNoiseModel,
        SymmetricGaussianModel,
    )

    base = device_model_from_variation(chip.device.variation)
    adc = chip.circuit.adc
    if adc.accuracy_bits is None:
        return base

    # Guard: only analog RRAM benefits from partial-sum ADC noise.
    if not chip.device.is_nvm():
        return base
    if chip.architecture.pe.pim_type.value != 0:
        return base
    if chip.device.resistance is None:
        return base

    bits = float(adc.accuracy_bits.value)
    activity = (
        float(adc.accuracy_input_activity.value)
        if adc.accuracy_input_activity is not None
        else 0.5
    )
    g_lrs = 1.0 / float(chip.device.resistance.lrs_ohm)
    n_rows = int(chip.architecture.xbar.rows.value)

    # Inner must not be None — wrap a zero-variation symmetric model
    # so PartialSumADCNoiseModel.sample_resistance always has a base.
    inner = base if base is not None else SymmetricGaussianModel(variation_pct=0.0)

    return PartialSumADCNoiseModel(
        inner=inner,
        adc_bits=bits,
        subarray_rows=n_rows,
        g_lrs_siemens=g_lrs,
        input_activity=activity,
    )


def _build_adc_model(chip: ChipProfile):
    adc = chip.circuit.adc
    if adc.walden_enob is None:
        return None
    from pim_sim.array.adc_model import WaldenADCModel

    kwargs: dict[str, Any] = {"enob": float(adc.walden_enob)}
    if adc.walden_fom_w is not None:
        kwargs["fom_w"] = float(adc.walden_fom_w)
    if adc.walden_fom_a_um2 is not None:
        kwargs["fom_a_um2"] = float(adc.walden_fom_a_um2)
    if adc.sample_rate_gsps is not None:
        kwargs["sample_rate_gsps"] = float(adc.sample_rate_gsps.value)
    return WaldenADCModel(**kwargs)


def _build_ir_drop_model(chip: ChipProfile):
    """Derive an IRDropModel from chip-profile xbar + device fields.

    Prerequisites for a meaningful model:
      - NVM device with a resistance pair (SRAM has no R_HRS/R_LRS semantic)
      - analog PIM (``pim_type == 0``); digital PIM has no physical IR path

    Returns None for chips that don't satisfy these (SRAM, digital PIM, or
    missing resistance data) — in which case the accuracy path runs without
    IR-drop correction and matches the MNSIM baseline behaviour.
    """
    if not chip.device.is_nvm():
        return None
    if chip.architecture.pe.pim_type.value != 0:
        return None
    if chip.device.resistance is None:
        return None

    from pim_sim.array.ir_drop import IRDropModel

    xbar = chip.architecture.xbar
    wire_r_raw = float(xbar.wire_resistance_ohm.value)
    wire_r = (
        _MNSIM_DEFAULT_WIRE_RESISTANCE_OHM if wire_r_raw < 0 else wire_r_raw
    )
    r_hrs = float(chip.device.resistance.hrs_ohm)
    r_lrs = float(chip.device.resistance.lrs_ohm)
    r_avg = math.sqrt(r_hrs * r_lrs)

    read_v = chip.device.read_voltage_v.value
    input_v = float(read_v[-1]) if read_v else 0.2

    return IRDropModel(
        xbar_rows=int(xbar.rows.value),
        wire_resistance_per_cell_ohm=wire_r,
        device_resistance_avg_ohm=r_avg,
        input_voltage=input_v,
    )


def build_overlay(chip: ChipProfile) -> dict[str, Any]:
    """Assemble pim_sim overlay kwargs for ``chip``.

    Emits a ``ProvenanceWarning`` if the chip has Tier-1 / Tier-2 fields
    tagged ``proxy`` or ``missing`` — see
    ``mnsim_adapter/provenance_check.py`` for the tier contract.
    """
    from mnsim_adapter.provenance_check import warn_weak_fields

    warn_weak_fields(chip)
    return {
        "pim_sim_model": _build_device_model(chip),
        "ir_drop_model": _build_ir_drop_model(chip),
        "adc_model": _build_adc_model(chip),
        "chip_profile_id": chip.chip_id,
    }
