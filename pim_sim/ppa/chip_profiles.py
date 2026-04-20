"""
pim_sim.ppa.chip_profiles
=========================
Chip-specific PPA profiles for literature-anchor evaluation.

Why this exists
---------------
Generic pim_sim overlays such as the Walden ADC model are useful for broad
sensitivity analysis, but they can be the wrong abstraction for a specific
published chip.  For literature-anchor validation we therefore support
registered chip profiles that carry paper-backed device/ADC metadata and apply
only the PPA corrections justified by the public record.

Current policy
--------------
- If MNSIM already contains a chip-specific implementation (for example
  ``ADC_Choice = 9`` for the Qi Liu ISSCC 2020 RRAM macro), the registered
  profile may intentionally apply **no** extra PPA correction.
- This is still useful: it makes the chip-specific assumption explicit and
  prevents the wrong generic overlay from silently changing the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from MNSIM.Hardware_Model.Buffer import buffer
from pim_sim.ppa.estimator import PPADelta


@dataclass(frozen=True)
class ChipPPAProfile:
    chip_id: str
    label: str
    device_resistance_ohm: tuple[float, ...] | None
    device_variation_pct: float | None
    saf_pct: tuple[float, float] | None
    note: str
    delta_fn: Callable[[Path, dict[str, float]], PPADelta]


def _zero_delta(_: Path, __: dict[str, float]) -> PPADelta:
    return PPADelta()


def _liu_isscc2020_delta(config_path: Path, baseline: dict[str, float]) -> PPADelta:
    # Public-data-backed corrections only:
    # 1. Fig. 33.2.2 shows an output buffer on the macro boundary, but PE_area
    #    only includes the PE input buffer. We therefore add one default 4KB
    #    tile-level output buffer as a macro-boundary area correction.
    outbuf = buffer(str(config_path), buf_level=2, default_buf_size=4)
    outbuf.calculate_buf_area()
    area_um2 = outbuf.buf_area

    # 2. The paper reports the SW-2T2R chip consumes 1.9x lower power than the
    #    1T1R version at the same VDD/VREAD, and explicitly states LPAR-ADC
    #    power is controlled by the integrator/comparator reference current.
    #    Since the current PE baseline still approximates the cell as 1T1R, we
    #    apply the 1.9x reduction only to the current-dependent readout path:
    #    ADC energy and xbar read energy.
    energy_scale = 1.0 / 1.9
    adc_energy = float(baseline.get("adc_energy_nj", 0.0))
    xbar_energy = float(baseline.get("xbar_energy_nj", 0.0))
    delta_energy_nj = (adc_energy + xbar_energy) * (energy_scale - 1.0)

    return PPADelta(
        energy_nj=delta_energy_nj,
        area_um2=area_um2,
        power_w=0.0,
        latency_ns=0.0,
    )


REGISTRY: dict[str, ChipPPAProfile] = {
    "rram_isscc2020_33p2": ChipPPAProfile(
        chip_id="rram_isscc2020_33p2",
        label="ISSCC 2020 Paper 33.2 RRAM macro",
        device_resistance_ohm=(2.0e7, 6.0e4),
        device_variation_pct=1.0,
        saf_pct=None,
        note=(
            "Chip-specific ppa profile for Q. Liu ISSCC 2020 33.2. "
            "The baseline already uses MNSIM's dedicated Qi Liu ADC implementation "
            "via ADC_Choice=9 and a paper-backed Device_Resistance pair. "
            "The additional pim_sim correction is limited to two public-data-backed "
            "effects: a 4KB output-buffer macro-boundary area overlay from Fig. 33.2.2 "
            "and a 1.9x SW-2T2R current-suppression correction applied only to "
            "current-dependent ADC/xbar energy."
        ),
        delta_fn=_liu_isscc2020_delta,
    ),
}


def get_chip_profile(chip_id: str) -> ChipPPAProfile:
    if chip_id not in REGISTRY:
        raise KeyError(f"Unknown chip profile '{chip_id}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[chip_id]


def profile_delta(chip_id: str, config_path: Path, baseline: dict[str, float]) -> PPADelta:
    profile = get_chip_profile(chip_id)
    return profile.delta_fn(config_path, baseline)
