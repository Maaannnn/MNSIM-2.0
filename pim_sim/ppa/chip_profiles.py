"""
pim_sim.ppa.chip_profiles
=========================
Registry mapping literature-anchor ``chip_id`` to its chip-specific PPA
overlay (Layer 3) and metadata.

Layering
--------
This module is a **thin registry**. All fitted-to-one-chip logic lives in
:mod:`pim_sim.ppa.chip_specific_overlays`; all universal modeling lives in
:mod:`pim_sim.ppa.estimator` and :mod:`pim_sim.accuracy`. Keeping
``chip_profiles.py`` free of fit constants makes the Layer-2 vs Layer-3
split auditable at file granularity.

Current policy
--------------
- If MNSIM already contains a chip-specific implementation (for example
  ``ADC_Choice = 9`` for the Qi Liu ISSCC 2020 RRAM macro), the registered
  overlay may intentionally apply **no** additional PPA correction.
- Registering such a profile is still useful: it makes the chip-specific
  assumption explicit and prevents the wrong generic overlay from silently
  changing the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pim_sim.ppa.estimator import PPADelta
from pim_sim.ppa.chip_specific_overlays import (
    FittedConstant,
    liu_isscc2020_33p2,
    null_control,
)


@dataclass(frozen=True)
class ChipPPAProfile:
    """Registered chip-specific Layer-3 overlay descriptor.

    ``fitted_constants`` enumerates every numeric parameter in
    ``delta_fn`` that was fit to this chip's published data. Anything in
    ``pim_sim.ppa.estimator`` or ``pim_sim.accuracy`` that a given chip
    uses unchanged is **not** listed here — those are Layer-2 universal
    defaults and their provenance lives with the model code.
    """

    chip_id: str
    label: str
    device_resistance_ohm: tuple[float, ...] | None
    device_variation_pct: float | None
    saf_pct: tuple[float, float] | None
    note: str
    delta_fn: Callable[[Path, dict[str, float]], PPADelta]
    fitted_constants: tuple[FittedConstant, ...] = field(default_factory=tuple)


REGISTRY: dict[str, ChipPPAProfile] = {
    "rram_isscc2020_33p2": ChipPPAProfile(
        chip_id="rram_isscc2020_33p2",
        label="ISSCC 2020 Paper 33.2 RRAM macro",
        device_resistance_ohm=(2.0e7, 6.0e4),
        device_variation_pct=1.0,
        saf_pct=None,
        note=(
            "Chip-specific Layer-3 overlay for Q. Liu ISSCC 2020 33.2. "
            "The baseline already uses MNSIM's dedicated Qi Liu ADC implementation "
            "via ADC_Choice=9 and a paper-backed Device_Resistance pair. "
            "The additional pim_sim correction is limited to two public-data-backed "
            "effects: a 4KB output-buffer macro-boundary area overlay from Fig. 33.2.2 "
            "and a 1.9x SW-2T2R current-suppression correction applied only to "
            "current-dependent ADC/xbar energy. Both numbers are tagged as "
            "FittedConstant with fitted_to_chip_id='rram_isscc2020_33p2' and "
            "therefore do not count as evidence for the Layer-2 claim."
        ),
        delta_fn=liu_isscc2020_33p2.delta,
        fitted_constants=liu_isscc2020_33p2.FITTED_CONSTANTS,
    ),
    "rram_isscc2020_15p4": ChipPPAProfile(
        chip_id="rram_isscc2020_15p4",
        label="ISSCC 2020 Paper 15.4 RRAM macro (TSMC 22 nm)",
        device_resistance_ohm=(1.0e6, 1.0e4),
        device_variation_pct=1.0,
        saf_pct=None,
        note=(
            "Null-control profile for C.-X. Xue ISSCC 2020 15.4. Paper does "
            "not disclose HRS/LRS / CV / per-ADC characterisation, so there "
            "is no chip-specific fit to add on top of the Layer-2 universal "
            "Walden-FoM overlay. Registering a zero-delta profile keeps the "
            "chip auditable as an unfit second anchor at a different tech "
            "node (22 nm) without leaking silent assumptions."
        ),
        delta_fn=null_control.delta,
        fitted_constants=null_control.FITTED_CONSTANTS,
    ),
    "rram_vlsi2018_mochida": ChipPPAProfile(
        chip_id="rram_vlsi2018_mochida",
        label="VLSI 2018 Mochida Panasonic analog ReRAM (40 nm)",
        device_resistance_ohm=(1.0e7, 1.0e5),
        device_variation_pct=2.0,
        saf_pct=None,
        note=(
            "Null-control profile for R. Mochida VLSI 2018. The chip uses a "
            "current-comparator SA (1-bit readout) so the Walden-FoM ADC "
            "overlay is N/A, and the cell is truly analog so MNSIM's binary "
            "abstraction already captures a modeling-scope limitation the "
            "chip-specific overlay cannot paper over. Zero-delta profile "
            "surfaces this boundary explicitly."
        ),
        delta_fn=null_control.delta,
        fitted_constants=null_control.FITTED_CONSTANTS,
    ),
    "sram_isscc2022_11p7": ChipPPAProfile(
        chip_id="sram_isscc2022_11p7",
        label="ISSCC 2022 Paper 11.7 SRAM CIM macro",
        device_resistance_ohm=None,
        device_variation_pct=None,
        saf_pct=None,
        note=(
            "Null-control profile for J.-W. Yan ISSCC 2022 11.7 (ADC-less SRAM CIM). "
            "pim_sim's three enhancements — asymmetric HRS/LRS variation, IR-drop, "
            "and Walden-FOM ADC — are all RRAM-specific and deliberately N/A here. "
            "Registering a zero-delta profile makes that an explicit claim rather "
            "than silent behaviour, and lets the ablation report a row that "
            "confirms pim_sim reduces to the MNSIM baseline on the SRAM anchor."
        ),
        delta_fn=null_control.delta,
        fitted_constants=null_control.FITTED_CONSTANTS,
    ),
}


def get_chip_profile(chip_id: str) -> ChipPPAProfile:
    if chip_id not in REGISTRY:
        raise KeyError(f"Unknown chip profile '{chip_id}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[chip_id]


def profile_delta(chip_id: str, config_path: Path, baseline: dict[str, float]) -> PPADelta:
    profile = get_chip_profile(chip_id)
    return profile.delta_fn(config_path, baseline)
