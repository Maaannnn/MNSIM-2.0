"""
Provenance sanity check for ChipProfile loads.

Why this module exists
----------------------
Every field in a ChipProfile is tagged with a ``Provenance.kind``. Two of
those kinds — ``proxy`` (a deliberate stand-in for a value we don't have)
and ``missing`` (no defensible value at all) — are fine on *low-tier*
bookkeeping fields like CACTI buffer power, which MNSIM always overrides
with its builtin lookup tables anyway. But on the **Tier-1 / Tier-2**
inputs that drive physical behaviour (tech node, xbar dimensions, device
resistance, variation, ADC spec…), a ``proxy`` tag silently turns the
downstream MNSIM / pim_sim number into "whatever MNSIM's default looked
like when nobody was watching".

For users registering a fab tape-out chip (see
``docs/simulator/registering_your_fab_chip.md``) the usual failure mode
is forgetting to flip a ``proxy`` label after plugging in real numbers,
or keeping the MNSIM default intact on a field they *could* have sourced.
Either way the validation pipeline should surface it, not silently
accept it.

What this module does
---------------------
Walks a ``ChipProfile`` and collects every Tier-1 / Tier-2 field whose
``Provenance.kind`` is ``proxy`` or ``missing``. Emits them as
``UserWarning`` via Python's ``warnings`` machinery so (a) they show up
in validation logs, (b) tests can capture them with
``warnings.catch_warnings``.

The tier split matches the contract documented in
``docs/simulator/registering_your_fab_chip.md``. Tier-3 (silicon-area /
TOPS/W reporting) and Tier-4 (CACTI / NoC / digital-module builtins)
are intentionally **not** checked — they're expected to carry ``proxy``
for literature-anchor chips.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mnsim_adapter.provenance import Provenance, Traced

if TYPE_CHECKING:
    from mnsim_adapter.chip import ChipProfile


WEAK_KINDS = frozenset({"proxy", "missing"})


@dataclass(frozen=True)
class WeakField:
    """One Tier-1 / Tier-2 field whose provenance is ``proxy`` or ``missing``."""

    path: str          # dotted field path, e.g. "device.variation"
    tier: int          # 1 or 2
    kind: str          # "proxy" or "missing"
    source: str
    note: str

    def format_line(self) -> str:
        tag = f"[Tier-{self.tier} {self.kind}]"
        parts = [tag, self.path]
        if self.source:
            parts.append(f"<- {self.source}")
        if self.note:
            parts.append(f"({self.note})")
        return " ".join(parts)


def _check_traced(
    path: str,
    tier: int,
    traced: Traced | None,
) -> WeakField | None:
    if traced is None:
        return WeakField(path=path, tier=tier, kind="missing",
                         source="", note="field is None")
    prov = traced.provenance
    if prov.kind not in WEAK_KINDS:
        return None
    return WeakField(path=path, tier=tier, kind=prov.kind,
                     source=prov.source, note=prov.note)


def _check_provenance(
    path: str,
    tier: int,
    prov: Provenance | None,
) -> WeakField | None:
    if prov is None:
        return WeakField(path=path, tier=tier, kind="missing",
                         source="", note="object is None")
    if prov.kind not in WEAK_KINDS:
        return None
    return WeakField(path=path, tier=tier, kind=prov.kind,
                     source=prov.source, note=prov.note)


def collect_weak_fields(chip: "ChipProfile") -> list[WeakField]:
    """Return every Tier-1 / Tier-2 field tagged proxy/missing."""
    weak: list[WeakField] = []
    dev = chip.device
    arch = chip.architecture
    circ = chip.circuit

    # ---- Tier 1: without these you can't run ----
    tier1: list[tuple[str, Traced | None]] = [
        ("device.tech_node_nm", dev.tech_node_nm),
        ("device.device_type", dev.device_type),
        ("device.cell_type", dev.cell_type),
        ("device.device_area_um2", dev.device_area_um2),
        ("device.read_voltage_v", dev.read_voltage_v),
        ("device.read_latency_ns", dev.read_latency_ns),
        ("architecture.xbar.rows", arch.xbar.rows),
        ("architecture.xbar.cols", arch.xbar.cols),
        ("architecture.pe.group_num", arch.pe.group_num),
        ("architecture.pe.dac_num", arch.pe.dac_num),
        ("architecture.pe.adc_num", arch.pe.adc_num),
        ("architecture.pe.pim_type", arch.pe.pim_type),
    ]
    for path, traced in tier1:
        wf = _check_traced(path, tier=1, traced=traced)
        if wf is not None:
            weak.append(wf)

    # ---- Tier 2: strongly recommended (drives RRAM quality) ----
    # resistance / variation / saf carry their own Provenance on the
    # composite object (not a Traced wrapper). ADC is the same.
    # For NVM chips we want resistance + variation; SAF is optional.
    # For SRAM chips variation is legitimately None (MNSIM convention),
    # so skip the None-is-weak check there.
    if dev.is_nvm():
        wf = _check_provenance(
            "device.resistance",
            tier=2,
            prov=dev.resistance.provenance if dev.resistance else None,
        )
        if wf is not None:
            weak.append(wf)
        wf = _check_provenance(
            "device.variation",
            tier=2,
            prov=dev.variation.provenance if dev.variation else None,
        )
        if wf is not None:
            weak.append(wf)
    else:
        # SRAM: only flag resistance if it's proxy/missing tagged by the
        # author (expected for Yan 11.7 — MNSIM SRAM equivalent R).
        if dev.resistance is not None and dev.resistance.provenance.kind in WEAK_KINDS:
            weak.append(
                WeakField(
                    path="device.resistance",
                    tier=2,
                    kind=dev.resistance.provenance.kind,
                    source=dev.resistance.provenance.source,
                    note=dev.resistance.provenance.note,
                )
            )

    # SAF is optional — only flag if present-and-weak, don't require it.
    if dev.saf is not None and dev.saf.provenance.kind in WEAK_KINDS:
        weak.append(
            WeakField(
                path="device.saf",
                tier=2,
                kind=dev.saf.provenance.kind,
                source=dev.saf.provenance.source,
                note=dev.saf.provenance.note,
            )
        )

    # ADC spec itself carries provenance; we flag only if weak.
    if circ.adc.provenance.kind in WEAK_KINDS:
        weak.append(
            WeakField(
                path="circuit.adc",
                tier=2,
                kind=circ.adc.provenance.kind,
                source=circ.adc.provenance.source,
                note=circ.adc.provenance.note,
            )
        )

    return weak


class ProvenanceWarning(UserWarning):
    """Dedicated warning category so callers can filter specifically."""


def warn_weak_fields(chip: "ChipProfile") -> list[WeakField]:
    """Emit a single ``ProvenanceWarning`` if the chip has any weak fields.

    Returns the list of weak fields so callers that want programmatic
    access (tests, validation scripts) don't have to re-collect.
    """
    weak = collect_weak_fields(chip)
    if not weak:
        return weak
    lines = [f"  - {w.format_line()}" for w in weak]
    msg = (
        f"ChipProfile '{chip.chip_id}' has {len(weak)} Tier-1/Tier-2 "
        f"field(s) tagged proxy/missing:\n" + "\n".join(lines) + "\n"
        "These drive physical behaviour; proxy values silently fall back "
        "to MNSIM defaults. If this chip is yours, replace them with "
        "physical/empirical numbers from your characterisation data."
    )
    warnings.warn(msg, ProvenanceWarning, stacklevel=2)
    return weak
