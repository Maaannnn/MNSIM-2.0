"""
pim_sim.array.adc_library
=========================
Named ADC presets calibrated to Murmann ADC Performance Survey subsets.

Why
---
``WaldenADCModel`` exposes two FoM constants whose defaults (20 fJ/conv-step,
8 µm² per 2^ENOB/GSa/s) were fit to MNSIM's 9-entry 28 nm reference table.
Silicon survey cross-check (``validate/walden_murmann_validation.py``, 438
Nyquist ADCs from ISSCC+VLSI, 1997-2026) shows the defaults are only
accurate once stratified by ``(ARCHITECTURE, ERA)``; e.g. a 0.18 µm flash
chip and a 28 nm SAR chip cannot share one FoM. This module surfaces that
stratification as named presets.

Source of truth
---------------
``validate/output/walden_murmann/adc_preset_library_seed.csv``. Regenerate
via ``python validate/walden_murmann_validation.py``. A parity test
(``tests/test_adc_library.py``) guards the embedded values against drift.

ERA convention: ``modern`` = YEAR ≥ 2015 (FoM_W plateaus at ~26 fJ from
2015 onward). ``legacy`` = YEAR < 2015. A technology-node cutoff remains
an open question; see ``docs/simulator/pluggable_adc_library.md`` §6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from pim_sim.array.adc_model import WaldenADCModel


_SOURCE = "Murmann ADC Survey rev20260314 (validate/walden_murmann_validation.py)"


@dataclass(frozen=True)
class ADCPreset:
    """Named ADC FoM preset drawn from a Murmann survey subset."""

    preset_id: str
    architecture: str
    era: str
    fom_walden_j_per_conv: float
    fom_area_um2: float
    n_silicon_points: int
    source: str = _SOURCE

    def to_model(self, enob: float, sample_rate_gsps: float) -> WaldenADCModel:
        return WaldenADCModel(
            enob=float(enob),
            sample_rate_gsps=float(sample_rate_gsps),
            fom_walden_j_per_conv=self.fom_walden_j_per_conv,
            fom_area_um2=self.fom_area_um2,
        )


# (architecture_label, era, fomw_fj_median, foma_um2_median, n_silicon_points)
# ``n_silicon_points`` is ``min(n_power, n_area)`` so the reported provenance
# never over-claims coverage.  Values are silicon medians from the seed CSV.
_SEED_ROWS = [
    ("SAR",           "legacy",   31.355717459161177,     1.2560351038486965,    36),
    ("SAR, TI",       "legacy",  433.27588607263755,   8469.80615795555,         20),
    ("Pipe",          "legacy",  798.958947120066,      110.740298774136,        82),
    ("Two-Step",      "legacy", 1521.30203562735,       102.2497346529679,        8),
    ("Pipe, TI",      "legacy", 3111.3555721233647,    2980.9406532277408,       18),
    ("Folding",       "legacy", 4042.574103459811,      929.5627325795356,       16),
    ("Flash",         "legacy", 5431.366309599128,     6209.4493912982825,       23),
    ("Pipe, SAR",     "modern",    6.157038570013642,     0.8721586791785093,    21),
    ("SAR, Pipe",     "modern",   13.477013927197776,     3.746127704773852,     10),
    ("SAR",           "modern",   20.356254829535946,     0.23675876788064382,   32),
    ("Pipe",          "modern",   21.722409498576994,   145.882871923474,        10),
    ("Pipe, SAR, TI", "modern",   53.726858288081154,  6947.308640369715,         9),
    ("SAR, TI",       "modern",   64.22555113685725,   7747.898862325919,        29),
    ("Pipe, TI",      "modern",  153.92698354804187,   6952.351078163303,        11),
]


def _normalize_arch(label: str) -> str:
    """``"SAR, TI"`` → ``"sar_ti"``; ``"Two-Step"`` → ``"two_step"``."""
    return (
        label.lower()
        .replace(", ", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _build_registry() -> Dict[str, ADCPreset]:
    reg: Dict[str, ADCPreset] = {}
    for arch_label, era, fomw_fj, foma_um2, n in _SEED_ROWS:
        preset_id = f"{_normalize_arch(arch_label)}_{era}"
        reg[preset_id] = ADCPreset(
            preset_id=preset_id,
            architecture=arch_label,
            era=era,
            fom_walden_j_per_conv=fomw_fj * 1e-15,
            fom_area_um2=foma_um2,
            n_silicon_points=n,
        )
    return reg


REGISTRY: Dict[str, ADCPreset] = _build_registry()


def get_preset(preset_id: str) -> ADCPreset:
    try:
        return REGISTRY[preset_id]
    except KeyError as exc:
        avail = ", ".join(sorted(REGISTRY))
        raise KeyError(
            f"Unknown ADC preset {preset_id!r}; available: {avail}"
        ) from exc
