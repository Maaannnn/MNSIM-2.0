"""
mnsim_adapter
=============
Structured, provenance-preserving input schema for MNSIM-based PIM simulation.

Why this package exists
-----------------------
MNSIM's native input (SimConfig.ini) is a flat ~200-line INI file that mixes:

- physical/process constants (tech node, supply voltages),
- architectural choices (crossbar size, tile count),
- empirical lookup values from specific published chips (ADC/DAC presets,
  digital-module area/power tables, device R/latency/energy),
- hardcoded fallbacks that activate on ``-1`` / ``0`` sentinels.

This makes provenance invisible and makes extension (new ADC model, new
device model, swap-one-layer ablation) fragile.

What this package provides
--------------------------
A four-layer composable schema:

    Layer 1  DeviceProfile          (tech, cell, R, V, variation, SAF)
    Layer 2  CircuitComponents      (ADC, DAC, digital modules)
    Layer 3  ArchitectureProfile    (xbar, PE, tile, architecture-level)
    Layer 4  ChipProfile            composes 1-3, emits MNSIM INI + pim_sim overlay

Every field is wrapped in ``Traced(value, Provenance)``, where ``Provenance``
records whether the value is physical / design / empirical / fitted / proxy /
missing, plus a human-readable ``source``.

What this package deliberately does NOT do
------------------------------------------
- It does not modify MNSIM source. It only generates MNSIM's INI input.
- It does not re-implement device/ADC physics. It just describes which
  MNSIM or pim_sim model to use, with parameters.
- It does not cover workload/training. Net-structure is out of scope for
  this iteration (see ``docs/simulator/chip_profile_schema.md``).
"""

from __future__ import annotations

from mnsim_adapter.provenance import Provenance, Traced
from mnsim_adapter.device import (
    DeviceProfile,
    ResistancePair,
    VariationModel,
    SymmetricVariation,
    AsymmetricVariation,
    SAFPair,
)
from mnsim_adapter.circuit import (
    ADCProfile,
    DACProfile,
    DigitalModules,
    DigitalModuleSpec,
    CircuitComponents,
)
from mnsim_adapter.architecture import (
    XbarProfile,
    PEProfile,
    TileProfile,
    ArchLevelProfile,
    ArchitectureProfile,
)
from mnsim_adapter.chip import ChipProfile
from mnsim_adapter.provenance_check import (
    ProvenanceWarning,
    WeakField,
    collect_weak_fields,
    warn_weak_fields,
)
from mnsim_adapter.registry import (
    available_chips,
    available_measured_presets,
    load_chip,
    load_measured_device,
)

__all__ = [
    "Provenance",
    "Traced",
    "DeviceProfile",
    "ResistancePair",
    "VariationModel",
    "SymmetricVariation",
    "AsymmetricVariation",
    "SAFPair",
    "ADCProfile",
    "DACProfile",
    "DigitalModules",
    "DigitalModuleSpec",
    "CircuitComponents",
    "XbarProfile",
    "PEProfile",
    "TileProfile",
    "ArchLevelProfile",
    "ArchitectureProfile",
    "ChipProfile",
    "ProvenanceWarning",
    "WeakField",
    "collect_weak_fields",
    "warn_weak_fields",
    "available_chips",
    "available_measured_presets",
    "load_chip",
    "load_measured_device",
]
