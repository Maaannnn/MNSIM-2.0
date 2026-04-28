"""
pim_sim.device.factory
======================
Pure factory: ``mnsim_adapter.VariationModel`` → ``pim_sim.DeviceModel``.

Why a separate factory module
-----------------------------
``mnsim_adapter.overlay.build_overlay`` already wraps the full
ChipProfile → (DeviceModel, IRDropModel, WaldenADCModel) mapping, but the
per-field "VariationModel → DeviceModel" logic was previously inlined
there. Extracting it lets:

* unit tests exercise every variation kind in isolation without touching
  the rest of a ChipProfile,
* external scripts that hold a raw ``VariationModel`` (e.g. fab-data
  ablation sweeps) construct a pim_sim DeviceModel without re-implementing
  the dispatch.

This factory does NOT handle ``EmpiricalDeviceModel``. Empirical models
need raw wafer sample arrays that ``mnsim_adapter.VariationModel`` does
not currently carry; callers with CDF samples should instantiate
``EmpiricalDeviceModel`` directly.
"""

from __future__ import annotations

from typing import Optional

from mnsim_adapter.device import (
    AsymmetricVariation,
    SymmetricVariation,
    VariationModel,
)

from pim_sim.device.model import (
    AsymmetricGaussianModel,
    DeviceModel,
    SymmetricGaussianModel,
)


def device_model_from_variation(variation: Optional[VariationModel]) -> Optional[DeviceModel]:
    """Map a ``VariationModel`` to the matching pim_sim ``DeviceModel``.

    Parameters
    ----------
    variation:
        A ``SymmetricVariation`` / ``AsymmetricVariation`` instance from
        ``mnsim_adapter.device``, or ``None``.

    Returns
    -------
    ``SymmetricGaussianModel`` / ``AsymmetricGaussianModel`` / ``None``.
    Returning ``None`` tells ``pim_sim_weight_inject`` to fall through to
    MNSIM's native ``Weight_update.weight_update`` (the Gaussian σ/μ path
    described in ``pim_sim.accuracy.weight_inject``'s module docstring).

    Raises
    ------
    ValueError
        If ``variation`` has an unrecognised ``kind``.
    """
    if variation is None:
        return None
    if isinstance(variation, AsymmetricVariation):
        return AsymmetricGaussianModel(
            state_cv_pct=list(float(v) for v in variation.state_cv_pct)
        )
    if isinstance(variation, SymmetricVariation):
        return SymmetricGaussianModel(variation_pct=float(variation.cv_pct))
    raise ValueError(
        f"Unsupported VariationModel kind={variation.kind!r}; "
        "extend device_model_from_variation() to handle it."
    )
