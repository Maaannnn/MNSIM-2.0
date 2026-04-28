"""
pim_sim.ppa.chip_specific_overlays._provenance
==============================================
Provenance tagging for chip-specific overlay constants.

Purpose
-------
pim_sim is organized into three layers:

* **Layer 1 (物理)** — user-provided physical quantities entering via
  ``mnsim_adapter`` ChipProfile (tech node, cell type, device resistance,
  xbar/DAC/ADC geometry, ...).
* **Layer 2 (通用经验)** — pim_sim's universal modeling defaults that apply
  uniformly to every chip (``pim_sim.ppa.estimator`` Walden ADC,
  ``pim_sim.accuracy`` asymmetric device noise / IR-drop). These are the
  claimed generic contribution and must be validated on unseen chips.
* **Layer 3 (chip-specific overlays)** — per-chip corrections justified by
  the published record of a single silicon data point. Because they are fit
  to one chip, they **cannot** count as evidence for the generic Layer 2
  claim. :class:`FittedConstant` makes that explicit so the paper can point
  at the tagged constants and say "these do not generalize".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FittedConstant:
    """A numeric overlay parameter fitted to a single chip's published data.

    Attributes
    ----------
    name:
        Human-readable identifier (e.g. ``"sw_2t2r_current_suppression_ratio"``).
    value:
        The numeric value as applied in the overlay.
    unit:
        SI unit string, or ``"ratio"``/``"dimensionless"`` when applicable.
    fitted_to_chip_id:
        The ``chip_id`` whose silicon data motivated this constant. This is
        the source of the Layer-3 overfitting risk: the constant is not a
        generic pim_sim claim.
    source_citation:
        Short human-readable citation of the public document that backs the
        value (paper section / figure / table).
    note:
        Optional one-line justification for the value.
    """

    name: str
    value: float
    unit: str
    fitted_to_chip_id: str
    source_citation: str
    note: str = ""
