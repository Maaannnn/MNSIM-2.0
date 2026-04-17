"""
pim_sim.accuracy.weight_inject
===============================
Drop-in replacement for MNSIM's ``Weight_update.weight_update`` that adds:

  1. Asymmetric per-state device noise  (DeviceModel, default: AsymmetricGaussianModel)
  2. First-order IR-drop correction     (IRDropModel, optional)

Signature compatibility
-----------------------
MNSIM call site in dse/core.py (line ~529):

    bits_after = weight_update(
        sim_config_path, bits,
        is_Variation=enable_variation,
        is_SAF=enable_saf,
        is_Rratio=enable_rratio,
    )

pim_sim replacement:

    bits_after = pim_sim_weight_inject(
        sim_config_path, bits,
        is_Variation=enable_variation,
        is_SAF=enable_saf,
        is_Rratio=enable_rratio,
        pim_sim_model=<DeviceModel instance>,
        ir_drop_model=<IRDropModel instance | None>,
        rng_seed=<int | None>,
    )

If ``pim_sim_model`` is None the function falls back to MNSIM's original
``weight_update`` so the change is fully transparent.

Weight tensor layout
--------------------
MNSIM's ``weight`` is a list of dicts:
    weight[layer_idx][label] = np.ndarray of QUANTISED INDICES
                               (integer values 0..device_level-1)
    - 0  → HRS (highest resistance, lowest conductance)
    - device_level-1 → LRS (lowest resistance, highest conductance)

After weight_update these indices are converted to *conductance* values
(unit conductance scale).  pim_sim replicates this transformation with
asymmetric noise.
"""

from __future__ import annotations

import configparser as cp
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from pim_sim.device.model import DeviceModel, AsymmetricGaussianModel
from pim_sim.array.ir_drop import IRDropModel


def pim_sim_weight_inject(
    sim_config_path: str,
    weight: List[Optional[Dict[str, np.ndarray]]],
    is_SAF: int = 0,
    is_Variation: int = 0,
    is_Rratio: int = 0,
    pim_sim_model: Optional[DeviceModel] = None,
    ir_drop_model: Optional[IRDropModel] = None,
    rng_seed: Optional[int] = None,
) -> List[Optional[Dict[str, np.ndarray]]]:
    """Apply device noise and optional IR-drop to MNSIM weight tensors.

    Parameters
    ----------
    sim_config_path:
        Path to MNSIM SimConfig.ini.
    weight:
        List of layer weight dicts (quantised indices, as returned by
        ``TrainTestInterface.get_net_bits()``).
    is_SAF, is_Variation, is_Rratio:
        Same semantics as MNSIM ``weight_update``.
    pim_sim_model:
        Custom DeviceModel instance.  If None, falls back to MNSIM.
    ir_drop_model:
        IRDropModel instance.  If None, no IR-drop correction is applied.
    rng_seed:
        Optional seed for reproducibility.

    Returns
    -------
    Modified weight list (same structure, float conductance values).
    """
    # ------------------------------------------------------------------ #
    # Fallback: if no pim_sim model provided, delegate to MNSIM original  #
    # ------------------------------------------------------------------ #
    if pim_sim_model is None:
        from MNSIM.Accuracy_Model.Weight_update import weight_update
        return weight_update(
            sim_config_path, weight,
            is_SAF=is_SAF, is_Variation=is_Variation, is_Rratio=is_Rratio,
        )

    # ------------------------------------------------------------------ #
    # Load config                                                          #
    # ------------------------------------------------------------------ #
    cfg = cp.ConfigParser()
    cfg.read(sim_config_path, encoding="UTF-8")

    SAF_dist = list(map(float, cfg.get("Device level", "Device_SAF").split(",")))
    device_level = int(cfg.get("Device level", "Device_Level"))
    device_resistance = np.array(
        list(map(float, cfg.get("Device level", "Device_Resistance").split(",")))
    )
    assert device_level == len(device_resistance), "NVM resistance setting error"

    # MNSIM conductance normalisation (same as original)
    max_value = 2 ** math.floor(math.log2(device_level)) - 1
    unit_conductance = max_value / (1.0 / device_resistance[-1])

    rng = np.random.default_rng(rng_seed)

    # ------------------------------------------------------------------ #
    # Process each layer                                                   #
    # ------------------------------------------------------------------ #
    for i in range(len(weight)):
        if weight[i] is None:
            continue
        for label, value in weight[i].items():
            if is_Variation or is_Rratio:
                # Replace quantised indices with perturbed conductance values
                conductance = np.zeros_like(value, dtype=float)
                for j in range(device_level):
                    mask = value == j
                    if not np.any(mask):
                        continue
                    r_nominal = device_resistance[j]
                    r_perturbed = pim_sim_model.sample_resistance(
                        nominal_resistance=r_nominal,
                        state_index=j,
                        shape=mask.sum().item() if hasattr(mask.sum(), 'item') else int(mask.sum()),
                        rng=rng,
                    )
                    # Avoid division by zero / negative resistance
                    r_perturbed = np.maximum(r_perturbed, r_nominal * 0.01)
                    conductance[mask] = (1.0 / r_perturbed) * unit_conductance

                # Apply IR-drop correction (row-wise scaling)
                if ir_drop_model is not None:
                    conductance = _apply_ir_drop(conductance, ir_drop_model)

                value = conductance

            else:
                # No variation: just convert indices to conductance
                for j in range(device_level):
                    value = np.where(
                        value == j,
                        (1.0 / device_resistance[j]) * unit_conductance,
                        value,
                    )

            # ---------------------------------------------------------- #
            # SAF (Stuck-At Fault) — identical to MNSIM                   #
            # ---------------------------------------------------------- #
            if is_SAF:
                SAF = rng.random(value.shape)
                value_bkp = value.copy()
                value = np.where(SAF < float(SAF_dist[0] / 100), 0.0, value)
                value = np.where(SAF > 1 - float(SAF_dist[-1] / 100), float(max_value), value)

            weight[i].update({label: value.astype(float)})

    return weight


# ---------------------------------------------------------------------------
# IR-drop helper
# ---------------------------------------------------------------------------

def _apply_ir_drop(
    conductance: np.ndarray,
    ir_drop_model: IRDropModel,
) -> np.ndarray:
    """Apply row-wise IR-drop scale factors to a conductance tensor.

    Handles 2-D (rows × cols) and higher-rank tensors by treating the
    first two dimensions as (rows, cols) and leaving remaining dims alone.

    For weight tensors that are NOT perfectly aligned with xbar_rows
    (e.g. partial tiles), we rescale the model on the fly.
    """
    if conductance.ndim < 2:
        return conductance  # 1-D or scalar; no row concept

    n_rows = conductance.shape[0]
    scales = ir_drop_model._row_scales_for_n(n_rows)

    # Broadcast scales over all dimensions beyond axis 0
    shape = (n_rows,) + (1,) * (conductance.ndim - 1)
    return conductance * scales.reshape(shape)
