"""
pim_sim.device.model
====================
Device noise models for RRAM crossbar arrays.

MNSIM baseline (Weight_update.py line 41)
------------------------------------------
  temp_resistance = np.random.normal(0, device_resistance[j] * variation / 100)

This applies the *same* variation% to every resistance state (HRS, LRS, and
all MLC intermediate states).  Real RRAM measurements consistently show that
HRS has a much larger CV% than LRS, so a symmetric model underestimates HRS
noise and overestimates LRS noise.

Model hierarchy
---------------
  SymmetricGaussianModel   — exactly replicates MNSIM (baseline / comparison)
  AsymmetricGaussianModel  — separate σ_frac per resistance state (recommended)
  EmpiricalDeviceModel     — uses empirical CDF sampled from wafer measurements
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

class DeviceModel:
    """Abstract base for device noise models.

    Subclasses must implement ``sample_resistance``.
    """

    name: str = "base"

    def sample_resistance(
        self,
        nominal_resistance: float,
        state_index: int,
        shape: tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Return a noise-perturbed resistance array of ``shape``.

        Parameters
        ----------
        nominal_resistance:
            The ideal resistance for this quantisation state (Ω).
        state_index:
            Index into the device_resistance list (0 = HRS, -1 = LRS for 2-level).
        shape:
            Output array shape.
        rng:
            NumPy random generator (for reproducibility).
        """
        raise NotImplementedError

    def summary(self) -> dict:
        """Return a JSON-serialisable summary of model parameters."""
        return {"model": self.name}


# ---------------------------------------------------------------------------
# Symmetric Gaussian (MNSIM baseline)
# ---------------------------------------------------------------------------

@dataclass
class SymmetricGaussianModel(DeviceModel):
    """Replicates MNSIM's Weight_update.py noise model exactly.

    Gaussian noise with σ = nominal_resistance × variation_pct / 100,
    applied uniformly to every resistance state.

    Parameters
    ----------
    variation_pct:
        Percentage of nominal resistance used as Gaussian σ.
        Matches ``Device_Variation`` in SimConfig.ini.
    """

    variation_pct: float = 1.0
    name: str = field(default="symmetric_gaussian", init=False)

    def sample_resistance(
        self,
        nominal_resistance: float,
        state_index: int,
        shape: tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        sigma = nominal_resistance * self.variation_pct / 100.0
        return np.full(shape, nominal_resistance) + rng.normal(0.0, sigma, shape)

    def summary(self) -> dict:
        return {"model": self.name, "variation_pct": self.variation_pct}


# ---------------------------------------------------------------------------
# Asymmetric Gaussian
# ---------------------------------------------------------------------------

@dataclass
class AsymmetricGaussianModel(DeviceModel):
    """Per-state Gaussian noise calibrated from real wafer measurements.

    From 2T1R cycle data (wafer_xy16-25), typical values:
      HRS CV ≈ 20-35 %   (larger because filament dissolution is stochastic)
      LRS CV ≈ 10-19 %   (smaller because filament formation is more controlled)

    Parameters
    ----------
    state_cv_pct:
        List of CV% values, one per resistance state.
        Index 0 = HRS (highest resistance), last index = LRS (lowest resistance).
        If fewer values are given than states, the last value is repeated.
    """

    state_cv_pct: List[float] = field(default_factory=lambda: [25.0, 13.0])
    name: str = field(default="asymmetric_gaussian", init=False)

    def _cv_for_state(self, state_index: int, n_states: int) -> float:
        """Return CV% for the given state, handling MLC by interpolation."""
        cvs = self.state_cv_pct
        if len(cvs) == 0:
            return 1.0
        if state_index < len(cvs):
            return cvs[state_index]
        # Interpolate between first and last entry for MLC intermediate states
        t = state_index / max(1, n_states - 1)
        return cvs[0] + t * (cvs[-1] - cvs[0])

    def sample_resistance(
        self,
        nominal_resistance: float,
        state_index: int,
        shape: tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        # n_states is unknown here; use len(state_cv_pct) as proxy
        n_states = len(self.state_cv_pct)
        cv = self._cv_for_state(state_index, n_states)
        sigma = nominal_resistance * cv / 100.0
        return np.full(shape, nominal_resistance) + rng.normal(0.0, sigma, shape)

    def summary(self) -> dict:
        return {"model": self.name, "state_cv_pct": self.state_cv_pct}


# ---------------------------------------------------------------------------
# Empirical (CDF-based) model
# ---------------------------------------------------------------------------

@dataclass
class EmpiricalDeviceModel(DeviceModel):
    """Uses empirical CDFs sampled from raw wafer resistance measurements.

    For each state, the model stores sorted resistance samples drawn from real
    devices.  New samples are drawn by inverse-transform sampling (quantile
    interpolation), preserving the true distribution shape (including
    non-Gaussian heavy tails observed in RRAM data).

    Parameters
    ----------
    state_samples:
        List of 1-D arrays, one per resistance state.
        Index 0 = HRS, last = LRS.  Each array should contain ≥ 100 samples.
    nominal_resistances:
        Nominal R for each state (used for fallback if state_samples is empty).
    """

    state_samples: List[np.ndarray] = field(default_factory=list)
    nominal_resistances: List[float] = field(default_factory=list)
    name: str = field(default="empirical", init=False)

    def __post_init__(self) -> None:
        # Pre-sort samples for fast quantile lookup
        self._sorted: List[np.ndarray] = [np.sort(s) for s in self.state_samples]

    def sample_resistance(
        self,
        nominal_resistance: float,
        state_index: int,
        shape: tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        if state_index >= len(self._sorted) or len(self._sorted[state_index]) == 0:
            # Fallback to 5% symmetric Gaussian
            sigma = nominal_resistance * 0.05
            return np.full(shape, nominal_resistance) + rng.normal(0.0, sigma, shape)

        sorted_samples = self._sorted[state_index]
        n = len(sorted_samples)
        # Draw uniform random numbers and map through empirical quantile function
        u = rng.uniform(0.0, 1.0, shape)
        # Linear interpolation in sorted array
        indices = u * (n - 1)
        lo = np.floor(indices).astype(int)
        hi = np.minimum(lo + 1, n - 1)
        frac = indices - lo
        return sorted_samples[lo] * (1.0 - frac) + sorted_samples[hi] * frac

    def summary(self) -> dict:
        return {
            "model": self.name,
            "n_states": len(self.state_samples),
            "sample_counts": [len(s) for s in self.state_samples],
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def model_from_measured_preset(
    hrs_cv_pct: float,
    lrs_cv_pct: float,
    hrs_mean_ohm: Optional[float] = None,
    lrs_mean_ohm: Optional[float] = None,
) -> AsymmetricGaussianModel:
    """Build an AsymmetricGaussianModel from measured_presets.csv values.

    Parameters
    ----------
    hrs_cv_pct, lrs_cv_pct:
        Coefficient of variation (%) for HRS and LRS states from wafer data.
    hrs_mean_ohm, lrs_mean_ohm:
        Optional mean resistance values (only used for logging / summary).
    """
    return AsymmetricGaussianModel(state_cv_pct=[hrs_cv_pct, lrs_cv_pct])


def mnsim_compatible_model(variation_pct: float) -> SymmetricGaussianModel:
    """Build a SymmetricGaussianModel that matches a given Device_Variation value."""
    return SymmetricGaussianModel(variation_pct=variation_pct)
