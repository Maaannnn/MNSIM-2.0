"""
Layer 1: DeviceProfile
======================
Everything at the single-device level: process node, cell structure,
resistance states, read/write voltages and latencies, variation model,
SAF rates. One DeviceProfile corresponds to one published (or measured)
device characterisation.

Maps to MNSIM ``[Device level]`` + ``Cell_Type`` / ``Transistor_Tech`` /
``Wire_Resistance`` etc. from ``[Crossbar level]`` (the latter are
device-level in a physical sense, even though MNSIM stores them in the
crossbar section).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mnsim_adapter.provenance import Provenance, Traced


CellType = Literal["1T1R", "0T1R", "SW-2T2R", "2T2R", "SRAM_6T"]


@dataclass(frozen=True)
class ResistancePair:
    """HRS/LRS resistance in ohms with provenance.

    MNSIM stores this as a comma-separated list ``Device_Resistance``
    ordered from HRS to LRS.  For a two-level device this is
    ``R_hrs, R_lrs``.  Multi-level devices may extend the tuple.
    """

    hrs_ohm: float
    lrs_ohm: float
    provenance: Provenance
    intermediate_ohm: tuple[float, ...] = ()

    def as_mnsim_tuple(self) -> tuple[float, ...]:
        """Return an HRS->LRS ordered tuple for ``Device_Resistance``."""
        return (self.hrs_ohm, *self.intermediate_ohm, self.lrs_ohm)


@dataclass(frozen=True)
class VariationModel:
    """Base type for device-level variation models."""

    kind: Literal["symmetric_gaussian", "asymmetric_gaussian"]
    provenance: Provenance


@dataclass(frozen=True)
class SymmetricVariation(VariationModel):
    """MNSIM's default: one CV% applies to every resistance state."""

    cv_pct: float = 1.0

    def __post_init__(self) -> None:
        if self.kind != "symmetric_gaussian":
            raise ValueError("SymmetricVariation.kind must be 'symmetric_gaussian'")


@dataclass(frozen=True)
class AsymmetricVariation(VariationModel):
    """pim_sim's enhancement: per-state CV%, calibrated from wafer data.

    ``state_cv_pct`` is ordered consistently with ``ResistancePair.as_mnsim_tuple``:
    HRS first, LRS last.  For a two-level device: ``(cv_hrs, cv_lrs)``.
    """

    state_cv_pct: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.kind != "asymmetric_gaussian":
            raise ValueError("AsymmetricVariation.kind must be 'asymmetric_gaussian'")
        if len(self.state_cv_pct) < 2:
            raise ValueError(
                "AsymmetricVariation.state_cv_pct needs at least (cv_hrs, cv_lrs)"
            )


@dataclass(frozen=True)
class SAFPair:
    """Stuck-at-HRS / Stuck-at-LRS fraction (not percent)."""

    saf_hrs: float
    saf_lrs: float
    provenance: Provenance

    def as_mnsim_tuple(self) -> tuple[float, float]:
        return (self.saf_hrs, self.saf_lrs)


@dataclass(frozen=True)
class DeviceProfile:
    """Single-device characterisation used by MNSIM + pim_sim."""

    tech_node_nm: Traced[int]
    device_type: Traced[Literal["NVM", "SRAM"]]
    cell_type: Traced[CellType]
    transistor_tech_nm: Traced[int]

    device_area_um2: Traced[float]
    device_level: Traced[int]

    read_level: Traced[int]
    read_voltage_v: Traced[tuple[float, ...]]
    read_latency_ns: Traced[float]

    write_level: Traced[int]
    write_voltage_v: Traced[tuple[float, ...]]
    write_latency_ns: Traced[float]

    resistance: ResistancePair | None
    variation: VariationModel | None
    saf: SAFPair | None

    # SRAM-only:
    read_energy_j: Traced[float] | None = None
    write_energy_j: Traced[float] | None = None

    label: str = ""
    note: str = ""

    def is_nvm(self) -> bool:
        return self.device_type.value == "NVM"

    def is_sram(self) -> bool:
        return self.device_type.value == "SRAM"

    def with_variation(self, variation: VariationModel) -> "DeviceProfile":
        """Return a copy with variation swapped (for ablation sweeps)."""
        from dataclasses import replace

        return replace(self, variation=variation)

    def with_resistance(self, resistance: ResistancePair) -> "DeviceProfile":
        from dataclasses import replace

        return replace(self, resistance=resistance)
