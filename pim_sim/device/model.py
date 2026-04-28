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
class PartialSumADCNoiseModel(DeviceModel):
    """NeuroSim-inspired partial-sum ADC quantization, as per-cell weight noise.

    Context
    -------
    NeuroSim's inference path (``quantization_cpu_np_infer.py:121``,
    ``LinearQuantizeOut(outputPartial, ADCprecision)``) quantizes the
    partial-sum output of every weight-slice × input-bit MAC through a
    finite-precision ADC *before* shift-adding slices back together.
    MNSIM 2.0 has no equivalent on the accuracy path — its only non-ideality
    is weight-level Gaussian variation — so runs at small ADC precision
    look unrealistically clean.

    pim_sim's existing ``WaldenADCModel`` captures ADC precision for PPA
    only. This model routes the same knob onto the **accuracy** path by
    expressing the expected partial-sum quantization error as an
    equivalent additive Gaussian on per-cell conductance.

    Derivation
    ----------
    For a subarray with ``N`` active rows and input activity factor ``a``
    (0..1), the partial-sum range is approximately
    ``Y_range ≈ N · a · V_read · G_LRS``. A B-bit ADC with ``L = 2^B``
    uniform levels introduces quantization error with variance
    ``σ_Y² = (Y_range / L)² / 12`` (uniform-distribution variance).

    Distributing this error back onto ``N·a`` active cells as uncorrelated
    weight-space Gaussian noise gives
    ``σ_G_adc² = σ_Y² / (N·a·V_read)² ≈ G_LRS² / (12 · L² · N · a)``.

    We apply this as an additive per-cell conductance noise term on top
    of the inner DeviceModel's resistance samples. The approximation is
    first-order consistent with NeuroSim's formulation and converges to
    the inner model as ``B → ∞``.

    Limitations
    -----------
    - Assumes uniform per-cell error distribution; NeuroSim's actual
      per-slice quantization leaks unevenly when weight-slices are
      imbalanced. This shows up as a conservative error estimate for
      low-precision cells (MLC > 1 bit).
    - Uses G_LRS as the range normalizer; not valid for digital-PIM
      architectures where the ADC reads a ``1-bit SA`` output. Callers
      should skip this wrapper on digital PIM (and
      ``build_overlay`` does so automatically).
    - Assumes symmetric bipolar input mapping around zero. For unsigned
      input layers the effective ``a`` should be halved.

    Parameters
    ----------
    inner:
        Underlying variation model (``SymmetricGaussianModel``,
        ``AsymmetricGaussianModel``, or ``EmpiricalDeviceModel``).
        Sampling is delegated to ``inner.sample_resistance`` first, then
        the ADC-equivalent noise is composed in conductance space.
    adc_bits:
        ADC precision in bits (``B``). Typical values: 4-8 for analog
        RRAM macros; <3 makes the linearisation unreliable.
    subarray_rows:
        Number of simultaneously-active rows contributing to one partial
        sum. Equal to MNSIM ``Xbar_Size`` × ``DAC_Num``-scaled activity.
        Use the physical crossbar row count as a conservative upper bound.
    g_lrs_siemens:
        On-state conductance ``1 / R_LRS`` in siemens. Used as the
        partial-sum range normalizer.
    input_activity:
        Fraction of rows active per cycle (0 < a ≤ 1). Default 0.5
        (average 50% activation). Lower values → less ADC-equivalent
        noise because the partial-sum range collapses.
    """

    inner: DeviceModel = field(default_factory=lambda: SymmetricGaussianModel(variation_pct=0.0))
    adc_bits: float = 5.0
    subarray_rows: int = 128
    g_lrs_siemens: float = 1.0 / 6.0e4
    input_activity: float = 0.5
    name: str = field(default="partial_sum_adc_noise", init=False)

    def __post_init__(self) -> None:
        if self.adc_bits < 1:
            raise ValueError(f"adc_bits must be >= 1, got {self.adc_bits}")
        if self.subarray_rows < 1:
            raise ValueError(f"subarray_rows must be >= 1, got {self.subarray_rows}")
        if not (0.0 < self.input_activity <= 1.0):
            raise ValueError(
                f"input_activity must be in (0, 1], got {self.input_activity}"
            )
        if self.g_lrs_siemens <= 0:
            raise ValueError(f"g_lrs_siemens must be > 0, got {self.g_lrs_siemens}")

    def sigma_g_adc_equivalent(self) -> float:
        """Return the per-cell equivalent ADC-noise σ in conductance space (S)."""
        levels = 2.0 ** self.adc_bits
        denom = math.sqrt(12.0 * self.subarray_rows * self.input_activity) * levels
        return self.g_lrs_siemens / denom

    def sample_resistance(
        self,
        nominal_resistance: float,
        state_index: int,
        shape: tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        r_base = self.inner.sample_resistance(
            nominal_resistance=nominal_resistance,
            state_index=state_index,
            shape=shape,
            rng=rng,
        )
        # Floor to keep 1/r well-defined; matches pim_sim_weight_inject's guard
        r_base = np.maximum(r_base, nominal_resistance * 0.01)
        g_base = 1.0 / r_base
        sigma_g = self.sigma_g_adc_equivalent()
        g_noisy = g_base + rng.normal(0.0, sigma_g, shape)
        # Clamp conductance to (0, inf) so the reciprocal stays meaningful.
        g_floor = 1.0 / (nominal_resistance * 100.0)
        g_noisy = np.maximum(g_noisy, g_floor)
        return 1.0 / g_noisy

    def summary(self) -> dict:
        return {
            "model": self.name,
            "inner": self.inner.summary(),
            "adc_bits": self.adc_bits,
            "subarray_rows": self.subarray_rows,
            "g_lrs_siemens": self.g_lrs_siemens,
            "input_activity": self.input_activity,
            "sigma_g_adc_siemens": self.sigma_g_adc_equivalent(),
        }


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
