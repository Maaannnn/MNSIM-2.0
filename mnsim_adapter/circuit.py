"""
Layer 2: CircuitComponents
==========================
ADC, DAC, and per-module digital primitives that sit between the
crossbar and the digital post-processing path.  One of the main points
of this package is that swapping any of these is a one-field change
instead of editing MNSIM's hard-coded lookup tables.

Design choice: ``ADCProfile`` and ``DACProfile`` carry both a "preset"
selector (MNSIM's built-in 1..9 / 1..7 indices) AND explicit
``area / precision / power / sample_rate`` fields.  When ``preset_id``
is set we tell MNSIM to use its own preset and ignore the explicit
fields.  When ``preset_id`` is ``None`` (user-defined), we forward the
explicit fields into MNSIM.

This keeps backwards compatibility with every existing SimConfig.ini
while exposing the Walden-FoM parametric path pim_sim cares about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mnsim_adapter.provenance import Provenance, Traced


ADCPresetId = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9]
DACPresetId = Literal[1, 2, 3, 4, 5, 6, 7]


@dataclass(frozen=True)
class ADCProfile:
    """ADC characterisation.

    Two valid modes:
      1. ``preset_id`` in 1..9 selects MNSIM's built-in preset (see
         ``MNSIM/Hardware_Model/ADC.py``).  Explicit fields are ignored.
      2. ``preset_id`` is ``None`` and all of (area, precision, power,
         sample_rate) are set.  This becomes ``ADC_Choice = -1`` in
         MNSIM.
    """

    preset_id: ADCPresetId | None
    provenance: Provenance
    label: str = ""

    precision_bit: Traced[int] | None = None
    area_um2: Traced[float] | None = None
    power_w: Traced[float] | None = None
    sample_rate_gsps: Traced[float] | None = None
    interval_thres: Traced[tuple[float, ...]] | None = None

    # pim_sim-side overlay. When set, pim_sim's Walden-FoM ADC model can
    # override MNSIM's numbers downstream.  We don't apply it here; we
    # just record it so the overlay builder can pick it up.
    walden_enob: float | None = None
    walden_fom_w: float | None = None
    walden_fom_a_um2: float | None = None

    # Opt-in accuracy overlay inspired by NeuroSim's per-slice partial-sum
    # quantization (see pim_sim.device.model.PartialSumADCNoiseModel).
    # When None (default), no partial-sum ADC noise is injected and the
    # accuracy path stays byte-identical to prior literature-anchor runs.
    # When set, the overlay builder wraps the DeviceModel with
    # PartialSumADCNoiseModel(bits=accuracy_bits, ...).
    accuracy_bits: Traced[int] | None = None
    accuracy_input_activity: Traced[float] | None = None

    def is_user_defined(self) -> bool:
        return self.preset_id is None

    def __post_init__(self) -> None:
        if self.preset_id is None:
            missing = [
                name
                for name in ("precision_bit", "area_um2", "power_w", "sample_rate_gsps")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    "ADCProfile without preset_id must specify: "
                    + ", ".join(missing)
                )


@dataclass(frozen=True)
class DACProfile:
    """DAC characterisation. Same two-mode contract as ADCProfile."""

    preset_id: DACPresetId | None
    provenance: Provenance
    label: str = ""

    precision_bit: Traced[int] | None = None
    area_um2: Traced[float] | None = None
    power_w: Traced[float] | None = None
    sample_rate_gsps: Traced[float] | None = None

    def is_user_defined(self) -> bool:
        return self.preset_id is None

    def __post_init__(self) -> None:
        if self.preset_id is None:
            missing = [
                name
                for name in ("precision_bit", "area_um2", "power_w", "sample_rate_gsps")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    "DACProfile without preset_id must specify: "
                    + ", ".join(missing)
                )


@dataclass(frozen=True)
class DigitalModuleSpec:
    """One digital primitive: adder, multiplier, shiftreg, reg, joint module.

    ``area_um2`` / ``power_w`` are ``Traced[float]`` with value ``0`` when
    we want MNSIM to use its default lookup (``0`` is MNSIM's sentinel
    for 'use built-in default').  That default itself is empirical; the
    provenance should record that.
    """

    tech_nm: Traced[int]
    area_um2: Traced[float]
    power_w: Traced[float]
    label: str = ""


@dataclass(frozen=True)
class DigitalModules:
    """All digital modules as a group, one per MNSIM field family."""

    adder: DigitalModuleSpec
    multiplier: DigitalModuleSpec
    shift_reg: DigitalModuleSpec
    reg: DigitalModuleSpec
    joint_module: DigitalModuleSpec
    digital_frequency_mhz: Traced[float]


@dataclass(frozen=True)
class CircuitComponents:
    """Layer 2 root: bundles ADC + DAC + digital modules."""

    adc: ADCProfile
    dac: DACProfile
    digital: DigitalModules
    logic_op: Traced[int]  # -1=none, 0=AND, 1=OR, 2=XOR (MNSIM convention)

    def with_adc(self, adc: ADCProfile) -> "CircuitComponents":
        from dataclasses import replace

        return replace(self, adc=adc)

    def with_dac(self, dac: DACProfile) -> "CircuitComponents":
        from dataclasses import replace

        return replace(self, dac=dac)
