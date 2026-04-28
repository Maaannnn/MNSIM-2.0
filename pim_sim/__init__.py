"""
pim_sim — MNSIM Enhancement Layer
==================================
A drop-in accuracy/PPA enhancement layer that addresses three
specific weaknesses in MNSIM's default models:

  1. Device variation  : MNSIM uses *symmetric* Gaussian noise with the
                         same σ/R ratio for every resistance state.
                         pim_sim supports *asymmetric* models where σ_HRS
                         and σ_LRS are calibrated independently from real
                         wafer measurements.

  2. IR-drop on accuracy: MNSIM's main evaluation path (Weight_update.py)
                          has *no* IR-drop effect on accuracy.
                          pim_sim adds a first-order input-pattern-aware
                          IR-drop correction that scales with array size.

  3. ADC model         : MNSIM hard-codes 9 ADC presets (lookup table).
                         pim_sim provides a Walden-FOM parametric model
                         that treats ADC bits as a continuous design axis.

Integration
-----------
pim_sim is *not* a fork of MNSIM.  It plugs into dse/core.py via the
``pim_sim_weight_inject`` function, which is a drop-in replacement for
``MNSIM.Accuracy_Model.Weight_update.weight_update``.

Usage in dse/core.evaluate_config
----------------------------------
Pass ``pim_sim_model=<DeviceModel instance>`` to evaluate_config to
activate the enhanced accuracy path.  PPA numbers come from pim_sim.ppa
and optionally replace the MNSIM-computed values.
"""

__version__ = "0.1.0"

from pim_sim.device.model import (
    SymmetricGaussianModel,
    AsymmetricGaussianModel,
    EmpiricalDeviceModel,
    PartialSumADCNoiseModel,
)
from pim_sim.device.calibrate import (
    calibrate_from_measured_presets_csv,
    calibrate_from_wafer_csv,
)
from pim_sim.device.factory import device_model_from_variation
from pim_sim.accuracy.weight_inject import pim_sim_weight_inject
from pim_sim.array.ir_drop import IRDropModel
from pim_sim.array.adc_model import WaldenADCModel
from pim_sim.ppa.chip_profiles import ChipPPAProfile, get_chip_profile
from pim_sim.ppa.chip_specific_overlays import FittedConstant

__all__ = [
    "SymmetricGaussianModel",
    "AsymmetricGaussianModel",
    "EmpiricalDeviceModel",
    "PartialSumADCNoiseModel",
    "calibrate_from_measured_presets_csv",
    "calibrate_from_wafer_csv",
    "device_model_from_variation",
    "pim_sim_weight_inject",
    "IRDropModel",
    "WaldenADCModel",
    "ChipPPAProfile",
    "FittedConstant",
    "get_chip_profile",
]
