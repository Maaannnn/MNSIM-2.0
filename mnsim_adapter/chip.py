"""
Layer 4: ChipProfile
====================
Composes DeviceProfile (Layer 1) + CircuitComponents (Layer 2) +
ArchitectureProfile (Layer 3) into a single object that knows how to:

- emit an MNSIM-compatible SimConfig.ini (``to_mnsim_ini``)
- emit pim_sim overlay kwargs (``to_pim_sim_overlay``)
- validate cross-layer invariants (``validate``)
- dump a paper-supplement JSON (``to_json``)
- produce ablation variants (``with_adc`` / ``with_device`` / ``with_arch``)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Any

from mnsim_adapter.architecture import ArchitectureProfile
from mnsim_adapter.circuit import ADCProfile, CircuitComponents, DACProfile
from mnsim_adapter.device import DeviceProfile, VariationModel
from mnsim_adapter.provenance import Provenance, Traced


@dataclass(frozen=True)
class ChipProfile:
    """Top-level composition. Describes one chip (literature or measured)."""

    chip_id: str
    label: str
    source_kind: str  # "literature" | "measured" | "synthetic"
    source_ref: str
    device: DeviceProfile
    circuit: CircuitComponents
    architecture: ArchitectureProfile
    note: str = ""

    # ---------- ablation helpers ----------

    def with_device(self, device: DeviceProfile) -> "ChipProfile":
        return replace(self, device=device)

    def with_circuit(self, circuit: CircuitComponents) -> "ChipProfile":
        return replace(self, circuit=circuit)

    def with_architecture(self, architecture: ArchitectureProfile) -> "ChipProfile":
        return replace(self, architecture=architecture)

    def with_adc(self, adc: ADCProfile) -> "ChipProfile":
        return self.with_circuit(self.circuit.with_adc(adc))

    def with_dac(self, dac: DACProfile) -> "ChipProfile":
        return self.with_circuit(self.circuit.with_dac(dac))

    def with_variation(self, variation: VariationModel) -> "ChipProfile":
        return self.with_device(self.device.with_variation(variation))

    # ---------- cross-layer validation ----------

    def validate(self) -> list[str]:
        """Return a list of problems; empty list means the profile is consistent.

        We deliberately keep this to a handful of high-value checks and do
        NOT try to re-implement MNSIM's internal consistency rules.
        """
        problems: list[str] = []

        pe = self.architecture.pe
        xbar = self.architecture.xbar

        # Digital PIM must use xbar_polarity=1 (see SimConfig.ini comment).
        if pe.pim_type.value == 1 and pe.xbar_polarity.value != 1:
            problems.append(
                "PE.pim_type=1 (digital) requires xbar_polarity=1; "
                f"got polarity={pe.xbar_polarity.value}"
            )

        # NVM device + 0T1R cell only makes physical sense for NVM.
        if self.device.cell_type.value == "0T1R" and not self.device.is_nvm():
            problems.append("cell_type=0T1R requires device_type=NVM")

        # SRAM-only energies must be present iff SRAM.
        if self.device.is_sram():
            if self.device.read_energy_j is None or self.device.write_energy_j is None:
                problems.append(
                    "SRAM device must specify read_energy_j and write_energy_j"
                )

        # Subarray divisibility (already enforced in XbarProfile.__post_init__
        # but re-checked here so the aggregate validation message is complete)
        if xbar.rows.value % xbar.subarray_size.value != 0:
            problems.append(
                f"xbar.rows={xbar.rows.value} not divisible by "
                f"subarray_size={xbar.subarray_size.value}"
            )

        # ADC precision sanity: if user-defined, must be >=1
        adc = self.circuit.adc
        if adc.is_user_defined():
            if adc.precision_bit is None or adc.precision_bit.value < 1:
                problems.append("user-defined ADC.precision_bit must be >= 1")

        return problems

    # ---------- emit artefacts ----------

    def to_mnsim_ini(self, path: str | Path) -> Path:
        """Write an MNSIM-compatible SimConfig.ini to ``path`` and return it."""
        from mnsim_adapter.mnsim_ini import render_ini

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_ini(self), encoding="utf-8")
        return out

    def to_pim_sim_overlay(self) -> dict[str, Any]:
        """Return kwargs consumable by ``dse/core.evaluate_config``.

        Keys:
          pim_sim_model: a DeviceModel instance or None
          ir_drop_model: an IRDropModel instance or None
          chip_profile_id: string tag for provenance
        """
        from mnsim_adapter.overlay import build_overlay

        return build_overlay(self)

    def weak_provenance_fields(self) -> list[Any]:
        """List Tier-1/Tier-2 fields tagged proxy/missing (side-effect-free).

        Use this for programmatic checks (tests, reports). The overlay
        builder calls ``warn_weak_fields`` instead so runs surface the
        same information via Python's warnings system.
        """
        from mnsim_adapter.provenance_check import collect_weak_fields

        return collect_weak_fields(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable dict suitable for JSON / paper supplement."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
