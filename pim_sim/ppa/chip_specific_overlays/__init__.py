"""
pim_sim.ppa.chip_specific_overlays
==================================
Layer-3 chip-specific PPA overlays.

Each submodule here owns one published chip's overlay plus the
:class:`FittedConstant` entries documenting which of its numeric parameters
were fit to that chip's silicon data. Code in this subpackage must never be
used as evidence that pim_sim's Layer-2 (universal) contributions
generalize — that is the whole reason the chip-specific code is quarantined
here rather than living alongside the universal models.

See :mod:`pim_sim.ppa.chip_specific_overlays._provenance` for the layering
explanation.
"""

from pim_sim.ppa.chip_specific_overlays._provenance import FittedConstant

from pim_sim.ppa.chip_specific_overlays import (
    liu_isscc2020_33p2,
    null_control,
)

__all__ = [
    "FittedConstant",
    "liu_isscc2020_33p2",
    "null_control",
]
