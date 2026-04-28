"""
pim_sim.ppa.chip_specific_overlays.null_control
===============================================
Explicit zero overlay.

Used when pim_sim's Layer-2 RRAM-specific enhancements (asymmetric device
noise, IR-drop, Walden-FOM ADC) are all deliberately N/A for a given chip
— e.g. the ADC-less digital SRAM CIM anchor. Registering this instead of
omitting a profile makes "no overlay applies" an explicit claim that the
ablation CSV can verify, rather than silent behaviour.
"""

from __future__ import annotations

from pathlib import Path

from pim_sim.ppa.estimator import PPADelta
from pim_sim.ppa.chip_specific_overlays._provenance import FittedConstant


FITTED_CONSTANTS: tuple[FittedConstant, ...] = ()


def delta(_: Path, __: dict[str, float]) -> PPADelta:
    return PPADelta()
