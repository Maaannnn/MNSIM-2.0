"""
pim_sim.ppa.chip_specific_overlays.liu_isscc2020_33p2
=====================================================
Layer-3 chip-specific overlay for the Q. Liu et al. ISSCC 2020 Paper 33.2
RRAM compute-in-memory macro.

These corrections are **fitted to one chip** and therefore cannot be used as
evidence that pim_sim's Layer-2 (universal) contributions generalize. They
are kept here, isolated from ``pim_sim.ppa.estimator`` and
``pim_sim.accuracy``, so the paper can cleanly point at which code paths are
chip-specific fits vs. which are universal claims.

Public-data-backed corrections applied here
-------------------------------------------
1. **4 KB output buffer area overlay** — Fig. 33.2.2 shows an explicit
   output buffer on the macro boundary, but MNSIM's ``PE_area`` only
   accounts for the PE input buffer. We therefore add one default 4 KB
   tile-level output buffer as a macro-boundary area correction.
2. **1.9× SW-2T2R current-suppression correction** — the paper reports the
   SW-2T2R chip consumes 1.9× lower power than a 1T1R baseline at the same
   VDD/VREAD and explicitly states LPAR-ADC power is controlled by the
   integrator/comparator reference current. MNSIM's PE baseline still
   approximates the cell as 1T1R, so we scale ``1/1.9`` on the
   current-dependent readout path (ADC + xbar read energy) only.
"""

from __future__ import annotations

from pathlib import Path

from MNSIM.Hardware_Model.Buffer import buffer

from pim_sim.ppa.estimator import PPADelta
from pim_sim.ppa.chip_specific_overlays._provenance import FittedConstant


CHIP_ID = "rram_isscc2020_33p2"
SOURCE = "Q. Liu et al., ISSCC 2020 Paper 33.2"


FITTED_CONSTANTS: tuple[FittedConstant, ...] = (
    FittedConstant(
        name="sw_2t2r_current_suppression_ratio",
        value=1.9,
        unit="ratio",
        fitted_to_chip_id=CHIP_ID,
        source_citation=f"{SOURCE}, Fig. 33.2.3 (SW-2T2R vs 1T1R power comparison)",
        note=(
            "Applied as 1/1.9 energy scale on the current-dependent readout "
            "path (ADC + xbar read) only; not applied to digital energy."
        ),
    ),
    FittedConstant(
        name="output_buffer_size_kb",
        value=4.0,
        unit="KB",
        fitted_to_chip_id=CHIP_ID,
        source_citation=f"{SOURCE}, Fig. 33.2.2 (macro block diagram)",
        note=(
            "MNSIM PE_area only includes the PE input buffer. A single "
            "default-size output buffer at buf_level=2 is added as a "
            "macro-boundary area correction."
        ),
    ),
)


def delta(config_path: Path, baseline: dict[str, float]) -> PPADelta:
    """Return the Layer-3 PPADelta for the Liu ISSCC 2020 33.2 chip."""
    outbuf = buffer(str(config_path), buf_level=2, default_buf_size=4)
    outbuf.calculate_buf_area()
    area_um2 = outbuf.buf_area

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
