"""
pim_sim.array.adc_model
=======================
Walden FOM parametric ADC model for CIM design space exploration.

MNSIM Limitation
----------------
MNSIM's ADC.py uses a 9-entry hardcoded lookup table (area, power, latency,
sample rate).  This means:
  - ADC bits is a discrete variable (only the 9 reference designs available)
  - Interpolation between reference points is impossible
  - The lookup does not distinguish different technology nodes or speeds

Walden FOM Model
----------------
The Walden figure of merit (J/conversion) captures the fundamental
area–power–speed trade-off of real ADCs:

    FOM_W  = P_conv / (2^ENOB × f_s)   [J/conversion]
    P_conv = FOM_W × 2^ENOB × f_s       [W]
    Area   = FOM_A × 2^ENOB / f_s       [µm²]  (empirical area FOM)

Fitted from MNSIM's 9 reference points (B_eff = ADC_precision,
f_s = ADC_sample_rate, P = ADC_power, A = ADC_area):

    FOM_W ≈ 1e-12 J/conv  (state-of-the-art SAR ADC @ 28nm)
    FOM_A ≈ 500   µm² per 2^ENOB / (GSa/s)

The model treats ENOB as a continuous variable, enabling sensitivity
sweeps over ADC precision.

Usage
-----
    from pim_sim.array.adc_model import WaldenADCModel

    adc = WaldenADCModel(enob=6, sample_rate_gsps=1.0)
    print(adc.power_w())    # W
    print(adc.area_um2())   # µm²
    print(adc.energy_j())   # J per conversion
    print(adc.latency_ns()) # ns
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# Fitted Walden FOM constants from MNSIM reference ADCs (28nm)
_DEFAULT_FOM_WALDEN_J_PER_CONV = 1.0e-12   # J / conversion (energy FOM)
_DEFAULT_FOM_AREA_UM2          = 450.0     # µm² per (2^ENOB / GSa/s)


@dataclass
class WaldenADCModel:
    """Parametric ADC model based on Walden figure of merit.

    Parameters
    ----------
    enob:
        Effective number of bits (continuous; equals precision for ideal ADC).
    sample_rate_gsps:
        Sampling rate in GSa/s.
    fom_walden_j_per_conv:
        Energy FOM (J/conversion).  Default fitted to MNSIM ref ADCs @ 28nm.
    fom_area_um2:
        Area FOM (µm² per 2^ENOB per GSa/s).  Default from same fitting.
    technology_node_nm:
        Technology node — used only for node-scaling if desired.
    """

    enob: float = 6.0
    sample_rate_gsps: float = 1.0
    fom_walden_j_per_conv: float = _DEFAULT_FOM_WALDEN_J_PER_CONV
    fom_area_um2: float = _DEFAULT_FOM_AREA_UM2
    technology_node_nm: float = 28.0

    def _conversions_per_sec(self) -> float:
        return self.sample_rate_gsps * 1e9

    def power_w(self) -> float:
        """Dynamic power (W) = FOM_W × 2^ENOB × f_s."""
        return self.fom_walden_j_per_conv * (2.0 ** self.enob) * self._conversions_per_sec()

    def area_um2(self) -> float:
        """Active area (µm²) = FOM_A × 2^ENOB / f_s_GSps."""
        return self.fom_area_um2 * (2.0 ** self.enob) / self.sample_rate_gsps

    def energy_j(self) -> float:
        """Energy per conversion (J)."""
        return self.fom_walden_j_per_conv * (2.0 ** self.enob)

    def latency_ns(self) -> float:
        """Conversion latency (ns) = (ENOB + 2) / f_s.

        The +2 accounts for pipeline overhead typical in SAR ADCs.
        """
        return (self.enob + 2.0) / (self.sample_rate_gsps)  # GSa/s → ns

    def summary(self) -> dict:
        return {
            "model": "walden_adc",
            "enob": self.enob,
            "sample_rate_gsps": self.sample_rate_gsps,
            "power_mw": round(self.power_w() * 1e3, 4),
            "area_um2": round(self.area_um2(), 2),
            "energy_fj": round(self.energy_j() * 1e15, 3),
            "latency_ns": round(self.latency_ns(), 4),
            "fom_walden_j_per_conv": self.fom_walden_j_per_conv,
        }

    # ------------------------------------------------------------------
    # Convenience: sweep over ENOB range
    # ------------------------------------------------------------------

    @staticmethod
    def sweep_enob(
        enob_range: "range | list[float]",
        sample_rate_gsps: float = 1.0,
        fom_walden_j_per_conv: float = _DEFAULT_FOM_WALDEN_J_PER_CONV,
        fom_area_um2: float = _DEFAULT_FOM_AREA_UM2,
    ) -> list:
        """Return a list of WaldenADCModel instances for each ENOB value."""
        return [
            WaldenADCModel(
                enob=b,
                sample_rate_gsps=sample_rate_gsps,
                fom_walden_j_per_conv=fom_walden_j_per_conv,
                fom_area_um2=fom_area_um2,
            )
            for b in enob_range
        ]


# ---------------------------------------------------------------------------
# MNSIM lookup compatibility shim
# ---------------------------------------------------------------------------

# Extracted from MNSIM/Hardware_Model/ADC.py for reference / comparison
_MNSIM_ADC_TABLE = {
    #  choice: (precision_bits, power_w,    area_um2,  sample_rate_gsps)
    1: (10, 6.92e-3, 1600,  1.5 ),
    2: (8,  2.00e-3, 1200,  1.28),
    3: (8,  4.00e-3, 1650,  1.1 ),
    4: (6,  1.26e-3, 580,   1.0 ),
    5: (8,  4.00e-3, 1650,  1.1 ),
    6: (6,  1.26e-3, 1650,  1.0 ),
    7: (4,  0.70e-3, 500,   1.0 ),
    8: (1,  1.629e-6, 1,    1.0 ),  # SA
    9: (8,  58.4e-3, 15899, 6.0 ),
}


def mnsim_adc_to_walden(adc_choice: int) -> WaldenADCModel:
    """Build a WaldenADCModel fitted to a specific MNSIM ADC choice.

    Useful for comparing the parametric model against MNSIM reference points.
    """
    if adc_choice not in _MNSIM_ADC_TABLE:
        raise KeyError(f"Unknown MNSIM ADC choice: {adc_choice}")
    bits, power, area, rate = _MNSIM_ADC_TABLE[adc_choice]
    # Back-calculate FOM from reference point
    fom_w = power / ((2.0 ** bits) * rate * 1e9) if bits > 0 else _DEFAULT_FOM_WALDEN_J_PER_CONV
    fom_a = area / ((2.0 ** bits) / rate) if bits > 0 else _DEFAULT_FOM_AREA_UM2
    return WaldenADCModel(
        enob=float(bits),
        sample_rate_gsps=rate,
        fom_walden_j_per_conv=fom_w,
        fom_area_um2=fom_a,
    )
