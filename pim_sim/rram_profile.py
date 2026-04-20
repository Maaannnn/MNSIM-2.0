"""
pim_sim.rram_profile
====================
Unified RRAM profile schema for literature-backed chips and measured presets.

Why this exists
---------------
Current repo inputs come from two different worlds:

1. Literature-anchor chips (for example ISSCC 2020 Liu 33.2)
2. Our measured-device presets derived from ``test_data/``

Both should flow through the same normalised structure before being translated
into:

- an MNSIM-compatible baseline
- a pim_sim enhancement overlay

This keeps provenance explicit and avoids mixing "paper-backed", "measured",
"proxy", and "default" values in an ad-hoc way.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pim_sim.device.calibrated_presets import PRESETS, WAFER_MODELS, get_preset
from pim_sim.device.model import AsymmetricGaussianModel, DeviceModel, SymmetricGaussianModel
from pim_sim.ppa.chip_profiles import get_chip_profile


@dataclass(frozen=True)
class EvidenceField:
    """One normalised input field with explicit provenance."""

    value: Any
    provenance: str
    note: str = ""


@dataclass(frozen=True)
class MNSIMBaselineSpec:
    """Inputs needed to instantiate an MNSIM-compatible baseline."""

    device_resistance_ohm: EvidenceField
    device_variation_pct: EvidenceField
    saf_pct: EvidenceField
    config_path: str | None = None

    def simconfig_overrides(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        if self.device_resistance_ohm.value is not None:
            resistance = self.device_resistance_ohm.value
            overrides["Device_Resistance"] = ",".join(f"{float(v):g}" for v in resistance)
        if self.device_variation_pct.value is not None:
            overrides["Device_Variation"] = f"{float(self.device_variation_pct.value):g}"
        if self.saf_pct.value is not None:
            saf = self.saf_pct.value
            overrides["Device_SAF"] = ",".join(f"{float(v):g}" for v in saf)
        return overrides

    def build_device_model(self) -> DeviceModel | None:
        if self.device_variation_pct.value is None:
            return None
        return SymmetricGaussianModel(variation_pct=float(self.device_variation_pct.value))


@dataclass(frozen=True)
class PimSimOverlaySpec:
    """Inputs needed to instantiate a pim_sim enhancement layer."""

    device_model: str
    state_cv_pct: EvidenceField
    current_dependent_energy_scale: EvidenceField
    extra_output_buffer_kb: EvidenceField
    note: str = ""

    def build_device_model(self) -> DeviceModel | None:
        if self.device_model == "none":
            return None
        if self.device_model == "symmetric_gaussian":
            if self.state_cv_pct.value is None:
                return None
            values = list(self.state_cv_pct.value)
            if len(values) == 0:
                return None
            return SymmetricGaussianModel(variation_pct=float(values[0]))
        if self.device_model == "asymmetric_gaussian":
            if self.state_cv_pct.value is None:
                return None
            return AsymmetricGaussianModel(state_cv_pct=list(map(float, self.state_cv_pct.value)))
        raise ValueError(f"Unsupported device_model '{self.device_model}'")


@dataclass(frozen=True)
class UnifiedRRAMProfile:
    """Single input object shared by literature and measured sources."""

    profile_id: str
    label: str
    source_kind: str
    source_ref: str
    mnsim_baseline: MNSIMBaselineSpec
    pimsim_overlay: PimSimOverlaySpec
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_literature_profile(chip_id: str) -> UnifiedRRAMProfile:
    """Normalise a registered literature chip profile."""

    chip = get_chip_profile(chip_id)
    energy_scale = None
    extra_output_buffer_kb = None
    overlay_note = chip.note
    if chip_id == "rram_isscc2020_33p2":
        energy_scale = 1.0 / 1.9
        extra_output_buffer_kb = 4.0
    return UnifiedRRAMProfile(
        profile_id=chip.chip_id,
        label=chip.label,
        source_kind="literature",
        source_ref="ISSCC 2020 Paper 33.2 / MNSIM literature anchor",
        mnsim_baseline=MNSIMBaselineSpec(
            device_resistance_ohm=EvidenceField(
                value=chip.device_resistance_ohm,
                provenance="paper_backed",
                note="Fig. 33.2.S1-derived approximate HRS/LRS pair.",
            ),
            device_variation_pct=EvidenceField(
                value=chip.device_variation_pct,
                provenance="baseline_proxy",
                note="MNSIM-compatible baseline comparator, not chip-measured HRS/LRS asymmetry.",
            ),
            saf_pct=EvidenceField(
                value=chip.saf_pct,
                provenance="missing",
                note="No paper-backed SAF pair registered for this chip.",
            ),
            config_path=None,
        ),
        pimsim_overlay=PimSimOverlaySpec(
            device_model="none",
            state_cv_pct=EvidenceField(
                value=None,
                provenance="missing",
                note="Paper does not provide a registered asymmetric HRS/LRS CV pair.",
            ),
            current_dependent_energy_scale=EvidenceField(
                value=energy_scale,
                provenance="paper_backed" if energy_scale is not None else "none",
                note="Applied only to current-dependent ADC/xbar energy when available.",
            ),
            extra_output_buffer_kb=EvidenceField(
                value=extra_output_buffer_kb,
                provenance="paper_backed" if extra_output_buffer_kb is not None else "none",
                note="Macro-boundary output buffer overlay from published block diagram when available.",
            ),
            note=overlay_note,
        ),
        note="Unified literature-anchor profile. Feed this object into baseline and pim_sim translators instead of ad-hoc per-script assumptions.",
    )


def build_measured_profile(preset_name: str) -> UnifiedRRAMProfile:
    """Normalise a measured-device preset or per-wafer model."""

    model = get_preset(preset_name)
    state_cv_pct = tuple(map(float, model.state_cv_pct))
    if preset_name in PRESETS:
        source_ref = f"test_data calibrated preset: {preset_name}"
        provenance = "measured"
    elif preset_name in WAFER_MODELS:
        source_ref = f"test_data per-wafer model: {preset_name}"
        provenance = "measured"
    else:
        source_ref = f"measured preset: {preset_name}"
        provenance = "measured"
    return UnifiedRRAMProfile(
        profile_id=f"measured::{preset_name}",
        label=f"Measured preset {preset_name}",
        source_kind="measured",
        source_ref=source_ref,
        mnsim_baseline=MNSIMBaselineSpec(
            device_resistance_ohm=EvidenceField(
                value=None,
                provenance="missing",
                note="Current measured preset registry stores variation asymmetry only; nominal HRS/LRS must come from the paired SimConfig or wafer summary.",
            ),
            device_variation_pct=EvidenceField(
                value=1.0,
                provenance="baseline_reference",
                note="Keep an MNSIM-compatible symmetric 1% comparator unless an experiment explicitly redefines the baseline.",
            ),
            saf_pct=EvidenceField(
                value=None,
                provenance="proxy_missing",
                note="SAF remains excluded from the primary measured-device claim in the current repo.",
            ),
            config_path=None,
        ),
        pimsim_overlay=PimSimOverlaySpec(
            device_model="asymmetric_gaussian",
            state_cv_pct=EvidenceField(
                value=state_cv_pct,
                provenance=provenance,
                note="Measured HRS/LRS CV pair used by pim_sim asymmetric device model.",
            ),
            current_dependent_energy_scale=EvidenceField(
                value=None,
                provenance="none",
                note="No measured chip-level current-dependent PPA scale is registered for measured-device presets.",
            ),
            extra_output_buffer_kb=EvidenceField(
                value=None,
                provenance="none",
                note="Measured-device presets do not imply a macro-boundary buffer overlay.",
            ),
            note="Unified measured-device profile. The same schema can be consumed by accuracy-path and future PPA-path translators.",
        ),
        note="Unified measured profile. This keeps the baseline comparator and pim_sim enhancement under one provenance-preserving object.",
    )


def load_unified_profile(source_kind: str, profile_id: str) -> UnifiedRRAMProfile:
    """Dispatch helper for scripts."""

    if source_kind == "literature":
        return build_literature_profile(profile_id)
    if source_kind == "measured":
        return build_measured_profile(profile_id)
    raise ValueError("source_kind must be 'literature' or 'measured'")
