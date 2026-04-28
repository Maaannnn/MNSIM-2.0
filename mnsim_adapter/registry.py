"""
Built-in registry of ChipProfile instances.

Currently covers:
  - ``rram_isscc2020_33p2``            : Q. Liu et al., ISSCC 2020 Paper 33.2,
                                         paper-backed baseline variant.
  - ``rram_isscc2020_33p2_mnsim_fit``  : same chip with 3 undisclosed MNSIM
                                         knobs set by grid search to minimise
                                         residual vs Table IV. Tagged
                                         ``kind='fitted'``.
  - ``rram_isscc2020_15p4``            : C.-X. Xue et al., ISSCC 2020 Paper 15.4,
                                         22 nm TSMC 2 Mb foundry ReRAM macro.
                                         Silicon-published only (not in MNSIM
                                         Table IV) — second RRAM anchor for
                                         cross-node pim_sim overlay sanity.
  - ``rram_vlsi2018_mochida``          : R. Mochida et al., VLSI 2018 Symposium,
                                         40 nm Panasonic 4 M synapses analog
                                         ReRAM NN processor. Silicon-published
                                         only — third RRAM anchor, uses SA
                                         readout so Walden ADC overlay is N/A.
  - ``sram_isscc2022_11p7``            : J.-W. Yan et al., ISSCC 2022 Paper 11.7,
                                         28 nm ADC-less SRAM CIM macro. Acts as
                                         the SRAM null-control literature anchor
                                         for the 3-way MNSIM / pim_sim / silicon
                                         comparison; pim_sim offers no RRAM-
                                         specific overlays here so it should
                                         match MNSIM exactly.
  - measured presets                   : thin adapter on top of
                                         ``pim_sim.device.calibrated_presets.PRESETS``
                                         and ``WAFER_MODELS``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from mnsim_adapter.architecture import (
    ArchitectureProfile,
    ArchLevelProfile,
    PEProfile,
    TileProfile,
    XbarProfile,
)
from mnsim_adapter.chip import ChipProfile
from mnsim_adapter.circuit import (
    ADCProfile,
    CircuitComponents,
    DACProfile,
    DigitalModuleSpec,
    DigitalModules,
)
from mnsim_adapter.device import (
    AsymmetricVariation,
    DeviceProfile,
    ResistancePair,
    SymmetricVariation,
)
from mnsim_adapter.provenance import Provenance, Traced


# ---------------------------------------------------------------------------
# Literature chip: ISSCC 2020 Paper 33.2 (Q. Liu et al.)
# ---------------------------------------------------------------------------

_LIU_SOURCE = "ISSCC 2020 Paper 33.2, Q. Liu et al., DOI 10.1109/ISSCC19947.2020.9062953"
_MNSIM_ADC9_SOURCE = "MNSIM/Hardware_Model/ADC.py choice=9 (labelled 'Qi Liu' preset)"
_FIG_S1_NOTE = (
    "Fig. 33.2.S1 'five 10 ns' distribution, rough-read ±30%; replace when an "
    "official TEM-derived pair becomes available."
)


def _liu_device() -> DeviceProfile:
    phys = Provenance(kind="physical", source=_LIU_SOURCE)
    paper = Provenance(kind="empirical", source=_LIU_SOURCE)
    design = Provenance(kind="design", source=_LIU_SOURCE)

    resistance = ResistancePair(
        hrs_ohm=2.0e7,
        lrs_ohm=6.0e4,
        provenance=Provenance(
            kind="empirical",
            source=f"{_LIU_SOURCE}; {_FIG_S1_NOTE}",
        ),
    )
    variation = SymmetricVariation(
        kind="symmetric_gaussian",
        cv_pct=1.0,
        provenance=Provenance(
            kind="proxy",
            source="MNSIM default",
            note=(
                "Paper does not report a CV%; we keep MNSIM's 1% so the baseline "
                "line in the 3-way comparison is MNSIM-native. pim_sim overlays "
                "calibrated asymmetric CV on top of this."
            ),
        ),
    )
    return DeviceProfile(
        tech_node_nm=Traced(130, phys),
        device_type=Traced("NVM", phys),
        cell_type=Traced(
            "1T1R",
            Provenance(
                kind="proxy",
                source=_LIU_SOURCE,
                note=(
                    "Paper uses SW-2T2R. MNSIM's Crossbar.py only branches on "
                    "'0T1R' vs other; 1T1R is the closest supported cell_type."
                ),
            ),
        ),
        transistor_tech_nm=Traced(130, phys),
        device_area_um2=Traced(
            3.38,
            Provenance(
                kind="empirical",
                source=_LIU_SOURCE,
                note="MNSIM SimConfig.ini comment cites this paper for 3.38.",
            ),
        ),
        device_level=Traced(2, design),
        read_level=Traced(2, design),
        read_voltage_v=Traced((0.0, 0.2), paper),
        read_latency_ns=Traced(
            0.5,
            Provenance(
                kind="proxy",
                source="calibrated PE-level placeholder",
                note="Empirical latency for Table IV reproduction path",
            ),
        ),
        write_level=Traced(2, design),
        write_voltage_v=Traced((0.0, 3.0), paper),
        write_latency_ns=Traced(10.0, Provenance(kind="proxy", source="MNSIM generic default")),
        resistance=resistance,
        variation=variation,
        saf=None,
        label="Liu 33.2 RRAM device (ISSCC 2020)",
        note="Baseline-compatible NVM device descriptor for T8.x validation.",
    )


def _liu_circuit() -> CircuitComponents:
    design = Provenance(kind="design", source=_LIU_SOURCE)

    adc = ADCProfile(
        preset_id=9,
        provenance=Provenance(
            kind="empirical",
            source=_MNSIM_ADC9_SOURCE,
            note=(
                "Choice 9 is labelled 'Qi Liu' and implements the LPAR-ADC "
                "latency model (1 / sample_rate * 2^precision)."
            ),
        ),
        label="MNSIM LPAR-ADC preset (Qi Liu)",
    )

    dac = DACProfile(
        preset_id=None,
        provenance=Provenance(
            kind="proxy",
            source="user-defined placeholder",
            note=(
                "DAC_Choice=1 inflates time-multiplex; DAC_Choice=6 has a "
                "power-scale issue. Keep user-defined 8-bit values for Table IV path."
            ),
        ),
        label="user-defined 8-bit DAC for PE-level PPA",
        precision_bit=Traced(8, design),
        area_um2=Traced(21.248, Provenance(kind="proxy", source="calibrated placeholder")),
        power_w=Traced(0.000354, Provenance(kind="proxy", source="calibrated placeholder")),
        sample_rate_gsps=Traced(1.5, Provenance(kind="proxy", source="calibrated placeholder")),
    )

    dm_default = DigitalModuleSpec(
        tech_nm=Traced(45, Provenance(kind="physical", source="MNSIM default 45 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )
    dm_65 = DigitalModuleSpec(
        tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default 65 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )

    digital = DigitalModules(
        adder=dm_default,
        multiplier=dm_default,
        shift_reg=dm_65,
        reg=dm_default,
        joint_module=dm_default,
        digital_frequency_mhz=Traced(1200.0, Provenance(kind="design", source="PE-level path frequency target")),
    )

    return CircuitComponents(
        adc=adc,
        dac=dac,
        digital=digital,
        logic_op=Traced(-1, Provenance(kind="design", source="analog PIM has no logic op")),
    )


def _liu_architecture() -> ArchitectureProfile:
    design = Provenance(kind="design", source=_LIU_SOURCE)
    xbar_size_note = "MNSIM §VII.B reproduces the first-layer 784x100 RRAM macro"

    xbar = XbarProfile(
        rows=Traced(784, Provenance(kind="design", source=_LIU_SOURCE, note=xbar_size_note)),
        cols=Traced(100, Provenance(kind="design", source=_LIU_SOURCE, note=xbar_size_note)),
        subarray_size=Traced(784, design),
        wire_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 2.82 Ω")),
        wire_capacity_ff=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 1 fF")),
        load_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default sqrt(R_on*R_off)")),
        area_calculation_method=Traced(0, design),
    )

    pe = PEProfile(
        pim_type=Traced(0, design),
        xbar_polarity=Traced(1, design),
        sub_position=Traced(0, design),
        group_num=Traced(1, design),
        dac_num=Traced(784, design),
        adc_num=Traced(100, design),
        in_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        in_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
    )

    tile = TileProfile(
        pe_num=Traced((2, 2), design),
        pooling_shape=Traced((3, 3), design),
        pooling_unit_num=Traced(64, design),
        pooling_tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default")),
        pooling_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        inter_tile_bandwidth_gbps=Traced(20.0, design),
        intra_tile_bandwidth_gbps=Traced(1024.0, design),
        out_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        out_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
    )

    arch = ArchLevelProfile(
        buffer_choice=Traced(1, design),
        buffer_tech_nm=Traced(90, Provenance(kind="physical", source="MNSIM default")),
        buffer_read_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_write_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_bitwidth_bit=Traced(64, design),
        lut_capacity_mb=Traced(1.0, design),
        lut_area_mm2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_bandwidth_mb_per_s=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        tile_connection=Traced(2, design),
        tile_num=Traced((64, 64), Provenance(kind="design", source="MNSIM default 64x64 tile grid")),
        weight_polarity=Traced(1, design),
        simulation_level=Traced(0, Provenance(kind="design", source="behavior level — MNSIM default path")),
        noc_enable=Traced(0, design),
    )

    return ArchitectureProfile(xbar=xbar, pe=pe, tile=tile, arch=arch)


def _liu_chip() -> ChipProfile:
    return ChipProfile(
        chip_id="rram_isscc2020_33p2",
        label="ISSCC 2020 Paper 33.2 RRAM macro",
        source_kind="literature",
        source_ref=_LIU_SOURCE,
        device=_liu_device(),
        circuit=_liu_circuit(),
        architecture=_liu_architecture(),
        note=(
            "Literature-anchor baseline for MNSIM §VII.B Table IV reproduction. "
            "All 'proxy' fields are either MNSIM's own builtin defaults or "
            "calibrated placeholders for the PE-level PPA path. 'empirical' "
            "fields are directly paper-backed."
        ),
    )


def _liu_chip_mnsim_fit() -> ChipProfile:
    """Grid-searched fit to MNSIM 2.0 Table IV.

    Same physical / empirical parameters as ``_liu_chip`` (so the values
    we *can* cite stay paper-backed), but overrides three MNSIM knobs
    that Table IV never disclosed:

      - ``device.read_latency_ns``:   0.5 ns  -> 0.7 ns
      - ``circuit.digital.digital_frequency_mhz``: 1200 -> 1500 MHz
      - ``architecture.arch.buffer_bitwidth_bit``: 64   -> 128 bit

    Under MNSIM@ca39ccb this combination is the closest match to
    Table IV's (3.50, 53.38, 74.44) achievable without violating any
    paper-disclosed field. Residual vs Table IV is ~1.99% (area side).

    Use this variant when an experiment needs the tightest-possible
    reproduction of the published Table IV row; use ``_liu_chip`` for
    the paper-fidelity baseline where every field must be citable.
    """
    base = _liu_chip()
    fit_src = (
        "Fitted by grid search (2026-04-20) of MNSIM-internal knobs that "
        "Table IV did not disclose; chosen to minimise |Table IV residual|."
    )

    new_device = replace(
        base.device,
        read_latency_ns=Traced(
            0.7,
            Provenance(
                kind="fitted",
                source=fit_src,
                note="Original placeholder was 0.5 ns; 0.7 ns shrinks area residual.",
            ),
        ),
    )

    new_digital = replace(
        base.circuit.digital,
        digital_frequency_mhz=Traced(
            1500.0,
            Provenance(
                kind="fitted",
                source=fit_src,
                note="Original design value 1200 MHz; 1500 MHz fits Table IV latency.",
            ),
        ),
    )
    new_circuit = replace(base.circuit, digital=new_digital)

    new_arch_level = replace(
        base.architecture.arch,
        buffer_bitwidth_bit=Traced(
            128,
            Provenance(
                kind="fitted",
                source=fit_src,
                note="Original design value 64 bit; 128 bit pushes buffer-area tier.",
            ),
        ),
    )
    new_arch = replace(base.architecture, arch=new_arch_level)

    return ChipProfile(
        chip_id="rram_isscc2020_33p2_mnsim_fit",
        label="ISSCC 2020 Paper 33.2 RRAM macro (MNSIM Table IV fit)",
        source_kind="literature",
        source_ref=_LIU_SOURCE,
        device=new_device,
        circuit=new_circuit,
        architecture=new_arch,
        note=(
            "Fitted variant of rram_isscc2020_33p2 that minimises residual vs "
            "MNSIM 2.0 Table IV (3.50 mm² / 53.38 ns / 74.44 TOPS/W). Three "
            "undisclosed MNSIM knobs are tagged kind='fitted'; all other "
            "fields inherit the paper-backed values. Residual ~1.99%. See "
            "docs/simulator/mnsim_validation_replication_plan.md §5.1 for "
            "why hard reproduction is infeasible."
        ),
    )


# ---------------------------------------------------------------------------
# Literature chip: ISSCC 2020 Paper 15.4 (C.-X. Xue et al., TSMC 22 nm ReRAM)
# ---------------------------------------------------------------------------
#
# Anchor context:
#   - 22 nm TSMC foundry 1T1R SLC ReRAM, 2 Mb testchip (8 sub-banks of
#     512 rows x 512 cols), VDD=0.8 V.
#   - Silicon-measured 4bIN-4bW-11bOUT operating point used here:
#       tAC = 18.3 ns, EF_MAC = 28.93 TOPS/W, testchip 2x3 = 6 mm^2
#       (testchip includes IO pads and testmodes; macro-only area not
#       disclosed in the paper).
#   - Readout is a 6-bit DbSO-CSA (dual-bit small-offset CSA running 3
#     cycles × 2 b); input side is IA-MBC BL-clamping with 4 levels.
#   - Not listed in MNSIM 2.0 Table IV, so no mnsim_table_iv_cited row —
#     the baseline/ablation scripts filter that variant out.

_XUE_SOURCE = "ISSCC 2020 Paper 15.4, C.-X. Xue et al., DOI 10.1109/ISSCC19947.2020.9063078"


def _xue_device() -> DeviceProfile:
    phys = Provenance(kind="physical", source=_XUE_SOURCE)
    paper = Provenance(kind="empirical", source=_XUE_SOURCE)
    design = Provenance(kind="design", source=_XUE_SOURCE)

    # Foundry 1T1R SLC ReRAM — paper does not disclose HRS/LRS numbers.
    # Use a generic TSMC 22 nm ReRAM proxy pair (HRS/LRS ratio ~100x is
    # typical for foundry eNVM); pim_sim's asymmetric variation overlay
    # can override this for accuracy experiments.
    resistance = ResistancePair(
        hrs_ohm=1.0e6,
        lrs_ohm=1.0e4,
        provenance=Provenance(
            kind="proxy",
            source="TSMC 22 nm foundry ReRAM typical range",
            note=(
                "Paper discloses only 'Foundry 1T1R SLC ReRAM' without HRS/LRS. "
                "100x ratio (1 MΩ / 10 kΩ) is a standard foundry-eNVM proxy."
            ),
        ),
    )
    variation = SymmetricVariation(
        kind="symmetric_gaussian",
        cv_pct=1.0,
        provenance=Provenance(
            kind="proxy",
            source="MNSIM default",
            note="Paper does not report CV%; baseline keeps MNSIM's 1%.",
        ),
    )
    return DeviceProfile(
        tech_node_nm=Traced(22, phys),
        device_type=Traced("NVM", phys),
        cell_type=Traced("1T1R", phys),
        transistor_tech_nm=Traced(22, phys),
        device_area_um2=Traced(
            0.10,
            Provenance(
                kind="proxy",
                source="scaled from Liu 33.2 (3.38 um^2 at 130 nm) to 22 nm",
                note="Scales ~ (22/130)^2 × 3.38 ≈ 0.1 um^2; paper undisclosed.",
            ),
        ),
        device_level=Traced(2, design),
        read_level=Traced(2, design),
        read_voltage_v=Traced((0.0, 0.4), paper),
        read_latency_ns=Traced(
            0.5,
            Provenance(
                kind="proxy",
                source="calibrated PE-level placeholder, same as Liu 33.2 path",
            ),
        ),
        write_level=Traced(2, design),
        write_voltage_v=Traced((0.0, 2.5), Provenance(kind="proxy", source="foundry ReRAM typical")),
        write_latency_ns=Traced(10.0, Provenance(kind="proxy", source="MNSIM generic default")),
        resistance=resistance,
        variation=variation,
        saf=None,
        label="Xue 15.4 RRAM device (ISSCC 2020)",
        note="TSMC 22 nm foundry 1T1R SLC ReRAM; binary-cell abstraction for MNSIM.",
    )


def _xue_circuit() -> CircuitComponents:
    design = Provenance(kind="design", source=_XUE_SOURCE)

    # DbSO-CSA: 6-bit unsigned per column, 3 cycles × 2 b sub-conversion.
    # User-defined precision_bit=6; area/power are MNSIM-compatible
    # sentinels scaled from Liu's LPAR preset (choice=9) at 22 nm.
    adc = ADCProfile(
        preset_id=None,
        provenance=Provenance(
            kind="empirical",
            source=_XUE_SOURCE,
            note=(
                "DbSO-CSA outputs 6b per column (3 cycles × 2b); modelled as "
                "a user-defined 6-bit ADC. Scales directly under pim_sim's "
                "Walden-FoM overlay."
            ),
        ),
        label="user-defined 6-bit DbSO-CSA",
        precision_bit=Traced(6, design),
        area_um2=Traced(
            240.0,
            Provenance(
                kind="proxy",
                source="scaled from MNSIM LPAR-ADC preset (choice=9) at 22 nm",
                note="Paper does not disclose per-ADC area; proxy preserves order of magnitude.",
            ),
        ),
        power_w=Traced(
            2.0e-4,
            Provenance(
                kind="proxy",
                source="scaled from MNSIM LPAR-ADC preset at 22 nm, 0.8 V",
            ),
        ),
        sample_rate_gsps=Traced(
            3.5,
            Provenance(
                kind="empirical",
                source=_XUE_SOURCE,
                note="6b conversion inside tAC=18.3 ns implies ~3 GS/s per DbSO-CSA.",
            ),
        ),
    )

    # IA-MBC BL-clamping acts as a 4-level (2b) VBLC DAC; 4bIN is split
    # into two 2b phases (IN[1:0], IN[3:2]). User-defined 4-bit DAC keeps
    # the aggregate input precision consistent with the silicon-anchored
    # 4bIN-4bW-11bOUT operating point.
    dac = DACProfile(
        preset_id=None,
        provenance=Provenance(
            kind="design",
            source=_XUE_SOURCE,
            note="Aggregate 4-bit input (two 2b sub-phases via IA-MBC).",
        ),
        label="user-defined 4-bit IA-MBC DAC",
        precision_bit=Traced(4, design),
        area_um2=Traced(10.0, Provenance(kind="proxy", source="calibrated placeholder")),
        power_w=Traced(1.5e-4, Provenance(kind="proxy", source="calibrated placeholder")),
        sample_rate_gsps=Traced(0.8, Provenance(kind="proxy", source="one sub-phase per cycle")),
    )

    dm_default = DigitalModuleSpec(
        tech_nm=Traced(45, Provenance(kind="physical", source="MNSIM default 45 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )
    dm_65 = DigitalModuleSpec(
        tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default 65 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )

    digital = DigitalModules(
        adder=dm_default,
        multiplier=dm_default,
        shift_reg=dm_65,
        reg=dm_default,
        joint_module=dm_default,
        digital_frequency_mhz=Traced(
            1000.0,
            Provenance(
                kind="proxy",
                source="PE-level path frequency target; 22 nm node",
            ),
        ),
    )

    return CircuitComponents(
        adc=adc,
        dac=dac,
        digital=digital,
        logic_op=Traced(-1, Provenance(kind="design", source="analog PIM has no logic op")),
    )


def _xue_architecture() -> ArchitectureProfile:
    design = Provenance(kind="design", source=_XUE_SOURCE)
    sub_bank_note = "One 2Mb testchip sub-bank: 512 rows × 512 cols (8 sub-banks × 512 × 512 = 2 Mb)."

    # MNSIM operates on one sub-bank as the xbar; post 8:1 column mux the
    # 512 BLs feed 64 DLs → 64 DbSO-CSAs per sub-bank.
    xbar = XbarProfile(
        rows=Traced(512, Provenance(kind="empirical", source=_XUE_SOURCE, note=sub_bank_note)),
        cols=Traced(512, Provenance(kind="empirical", source=_XUE_SOURCE, note=sub_bank_note)),
        subarray_size=Traced(512, design),
        wire_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 2.82 Ω")),
        wire_capacity_ff=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 1 fF")),
        load_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default sqrt(R_on*R_off)")),
        area_calculation_method=Traced(0, design),
    )

    pe = PEProfile(
        pim_type=Traced(0, design),
        xbar_polarity=Traced(1, design),
        sub_position=Traced(0, design),
        group_num=Traced(1, design),
        # Single WL-on per cycle is the BLIOMC scheme's hallmark; BL-side
        # IA-MBC still needs a DAC per active DL (64 post 8:1 mux).
        dac_num=Traced(64, Provenance(kind="empirical", source=_XUE_SOURCE, note="64 DLs after 8:1 column mux")),
        adc_num=Traced(64, Provenance(kind="empirical", source=_XUE_SOURCE, note="64 DbSO-CSAs per sub-bank")),
        in_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        in_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
    )

    tile = TileProfile(
        # 8 sub-banks aggregate into the 2Mb macro; PE grid (2,4) ≈ 8 sub-banks.
        pe_num=Traced((2, 4), Provenance(kind="design", source=_XUE_SOURCE, note="8 sub-banks")),
        pooling_shape=Traced((3, 3), design),
        pooling_unit_num=Traced(64, design),
        pooling_tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default")),
        pooling_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        inter_tile_bandwidth_gbps=Traced(20.0, design),
        intra_tile_bandwidth_gbps=Traced(1024.0, design),
        out_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        out_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
    )

    arch = ArchLevelProfile(
        buffer_choice=Traced(1, design),
        buffer_tech_nm=Traced(22, Provenance(kind="design", source="22 nm node buffer")),
        buffer_read_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_write_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_bitwidth_bit=Traced(64, design),
        lut_capacity_mb=Traced(1.0, design),
        lut_area_mm2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_bandwidth_mb_per_s=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        tile_connection=Traced(2, design),
        tile_num=Traced((64, 64), Provenance(kind="design", source="MNSIM default 64x64 tile grid")),
        weight_polarity=Traced(1, design),
        simulation_level=Traced(0, Provenance(kind="design", source="behavior level — MNSIM default path")),
        noc_enable=Traced(0, design),
    )

    return ArchitectureProfile(xbar=xbar, pe=pe, tile=tile, arch=arch)


def _xue_chip() -> ChipProfile:
    return ChipProfile(
        chip_id="rram_isscc2020_15p4",
        label="ISSCC 2020 Paper 15.4 RRAM macro (TSMC 22 nm)",
        source_kind="literature",
        source_ref=_XUE_SOURCE,
        device=_xue_device(),
        circuit=_xue_circuit(),
        architecture=_xue_architecture(),
        note=(
            "Second RRAM literature anchor for pim_sim overlay cross-node "
            "sanity at 22 nm. Silicon operating point: 4bIN-4bW-11bOUT, "
            "tAC=18.3 ns, EF=28.93 TOPS/W at VDD=0.8 V. Not in MNSIM 2.0 "
            "Table IV — validation uses silicon-published as the only "
            "reference. HRS/LRS, cell area, and digital frequency are "
            "proxies (foundry paper does not disclose)."
        ),
    )


# ---------------------------------------------------------------------------
# Literature chip: VLSI 2018 (R. Mochida et al., Panasonic 40 nm analog ReRAM)
# ---------------------------------------------------------------------------
#
# Anchor context:
#   - 40 nm Panasonic 1T-1R analog ReRAM, 4 M synapses = 2 M signed weights
#     (two MCs per weight, pos/neg on adjacent BLs). SA compares pos-BL
#     vs neg-BL currents and outputs a 1-bit digital decision.
#   - Silicon-measured 40 nm Table I row: Area=2.71 mm^2, Power=9.9 mW,
#     0.66 TOPS, 66.5 TOPS/W, 1.48 M synapses/mm^2 at 1.1 V.
#   - Benchmark: MNIST 14x14 MLP (196-64-10), 90.8% with MSMA inference.
#   - Readout is a current-comparator SA, not a multi-bit ADC, so the
#     Walden-FoM ADC overlay is N/A here. We model the ADC as a
#     user-defined 1-bit SA.

_MOCHIDA_SOURCE = (
    "Symp. VLSI Technology 2018, R. Mochida et al. (Panasonic), "
    "\"A 4M Synapses integrated Analog ReRAM based 66.5 TOPS/W "
    "Neural-Network Processor\", pp. 175-176"
)


def _mochida_device() -> DeviceProfile:
    phys = Provenance(kind="physical", source=_MOCHIDA_SOURCE)
    paper = Provenance(kind="empirical", source=_MOCHIDA_SOURCE)
    design = Provenance(kind="design", source=_MOCHIDA_SOURCE)

    # Paper reports cell current (not resistance) and at 180 nm: 30 µA
    # linear dynamic range, 0.59 µA σ. At VDD=1.1 V that maps to
    # R_LRS ≈ 1.1 V / 30 µA ≈ 37 kΩ. The 40 nm cell is noted to have
    # *lower* cell current → higher R; as a proxy use R_LRS=100 kΩ and
    # HRS≈10 MΩ (typical 100x ratio for Panasonic TaOx/TiON stacks).
    resistance = ResistancePair(
        hrs_ohm=1.0e7,
        lrs_ohm=1.0e5,
        provenance=Provenance(
            kind="proxy",
            source="scaled from Mochida's 180 nm 30 µA cell current",
            note=(
                "Paper reports analog cell current only (no HRS/LRS). "
                "R_LRS~100 kΩ chosen from 40 nm lower-current regime; "
                "100x ratio is typical for Panasonic TaOx analog ReRAM."
            ),
        ),
    )
    # Paper's σ=0.59 µA at 180 nm over 30 µA span ≈ 2% CV. 40 nm is
    # reported to scale well. Use 2% symmetric Gaussian as a paper-backed
    # proxy that slightly exceeds MNSIM's default 1%.
    variation = SymmetricVariation(
        kind="symmetric_gaussian",
        cv_pct=2.0,
        provenance=Provenance(
            kind="empirical",
            source=_MOCHIDA_SOURCE,
            note="σ=0.59 µA / 30 µA ≈ 2% at 180 nm; 40 nm comparable (Fig 7).",
        ),
    )
    return DeviceProfile(
        tech_node_nm=Traced(40, phys),
        device_type=Traced("NVM", phys),
        cell_type=Traced(
            "1T1R",
            Provenance(
                kind="proxy",
                source=_MOCHIDA_SOURCE,
                note="Paper uses two 1T1R MCs per signed weight (pos/neg BL).",
            ),
        ),
        transistor_tech_nm=Traced(40, phys),
        device_area_um2=Traced(
            0.32,
            Provenance(
                kind="proxy",
                source="scaled from Liu 33.2 (3.38 um^2 at 130 nm) to 40 nm",
                note="3.38 × (40/130)^2 ≈ 0.32 um^2.",
            ),
        ),
        device_level=Traced(2, design),
        read_level=Traced(2, design),
        read_voltage_v=Traced((0.0, 0.5), paper),
        read_latency_ns=Traced(
            0.5,
            Provenance(
                kind="proxy",
                source="calibrated PE-level placeholder, same as Liu 33.2 path",
            ),
        ),
        write_level=Traced(2, design),
        write_voltage_v=Traced((0.0, 2.0), Provenance(kind="proxy", source="analog ReRAM typical")),
        write_latency_ns=Traced(10.0, Provenance(kind="proxy", source="MNSIM generic default")),
        resistance=resistance,
        variation=variation,
        saf=None,
        label="Mochida 40 nm analog RAND device (VLSI 2018)",
        note=(
            "Panasonic 1T-1R analog ReRAM; MNSIM binary-cell abstraction "
            "of a truly analog device. The analog-current fidelity itself "
            "is out-of-scope — we're anchoring PPA, not analog behaviour."
        ),
    )


def _mochida_circuit() -> CircuitComponents:
    design = Provenance(kind="design", source=_MOCHIDA_SOURCE)

    # SA is a current-comparator producing a 1-bit decision per sense.
    # Modelled as user-defined 1-bit ADC so the Walden-FoM overlay is
    # deliberately inapplicable (paper has no multi-bit ADC to replace).
    adc = ADCProfile(
        preset_id=None,
        provenance=Provenance(
            kind="empirical",
            source=_MOCHIDA_SOURCE,
            note=(
                "Readout is a pos/neg-BL current-comparator SA — equivalent "
                "to a 1-bit ADC. Walden-FoM ADC overlay is N/A."
            ),
        ),
        label="user-defined 1-bit current-comparator SA",
        precision_bit=Traced(1, design),
        area_um2=Traced(
            5.0,
            Provenance(kind="proxy", source="1-bit current SA area sentinel"),
        ),
        power_w=Traced(
            1e-5,
            Provenance(kind="proxy", source="1-bit current SA power sentinel"),
        ),
        sample_rate_gsps=Traced(
            0.5,
            Provenance(kind="proxy", source="SA compare rate sentinel"),
        ),
    )

    # Digital 1-bit input interface (XDRV drives WL binary per input),
    # mirrors Yan's user-defined 1-bit DAC choice.
    dac = DACProfile(
        preset_id=None,
        provenance=Provenance(
            kind="design",
            source=_MOCHIDA_SOURCE,
            note="XDRV selects multiple WLs with 1-bit input activation per cycle.",
        ),
        label="user-defined 1-bit WL driver",
        precision_bit=Traced(1, design),
        area_um2=Traced(0.167, Provenance(kind="proxy", source="1-bit WL driver area sentinel")),
        power_w=Traced(1e-6, Provenance(kind="proxy", source="1-bit WL driver power sentinel")),
        sample_rate_gsps=Traced(0.5, Provenance(kind="proxy", source="WL drive rate sentinel")),
    )

    dm_default = DigitalModuleSpec(
        tech_nm=Traced(45, Provenance(kind="physical", source="MNSIM default 45 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )
    dm_65 = DigitalModuleSpec(
        tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default 65 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )

    digital = DigitalModules(
        adder=dm_default,
        multiplier=dm_default,
        shift_reg=dm_65,
        reg=dm_default,
        joint_module=dm_default,
        digital_frequency_mhz=Traced(
            500.0,
            Provenance(
                kind="proxy",
                source="40 nm Panasonic analog ReRAM controller target",
            ),
        ),
    )

    return CircuitComponents(
        adc=adc,
        dac=dac,
        digital=digital,
        logic_op=Traced(-1, Provenance(kind="design", source="analog PIM has no logic op")),
    )


def _mochida_architecture() -> ArchitectureProfile:
    design = Provenance(kind="design", source=_MOCHIDA_SOURCE)

    # MNIST 14x14 MLP (196-64-10) maps naturally into a 256x64 xbar
    # (pad 196→256 for power-of-two alignment). Subarray = 256 so the
    # whole layer fits in a single sub-array per MNSIM's semantics.
    xbar = XbarProfile(
        rows=Traced(256, Provenance(kind="design", source=_MOCHIDA_SOURCE, note="Padded 196-input MLP layer")),
        cols=Traced(64, Provenance(kind="empirical", source=_MOCHIDA_SOURCE, note="64-node middle layer")),
        subarray_size=Traced(256, design),
        wire_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 2.82 Ω")),
        wire_capacity_ff=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 1 fF")),
        load_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default sqrt(R_on*R_off)")),
        area_calculation_method=Traced(0, design),
    )

    pe = PEProfile(
        pim_type=Traced(0, design),
        xbar_polarity=Traced(1, design),
        sub_position=Traced(0, design),
        group_num=Traced(1, design),
        dac_num=Traced(256, design),
        adc_num=Traced(64, design),
        in_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        in_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
    )

    tile = TileProfile(
        pe_num=Traced((2, 2), design),
        pooling_shape=Traced((3, 3), design),
        pooling_unit_num=Traced(64, design),
        pooling_tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default")),
        pooling_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        inter_tile_bandwidth_gbps=Traced(20.0, design),
        intra_tile_bandwidth_gbps=Traced(1024.0, design),
        out_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        out_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
    )

    arch = ArchLevelProfile(
        buffer_choice=Traced(1, design),
        buffer_tech_nm=Traced(40, Provenance(kind="design", source="40 nm node buffer")),
        buffer_read_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_write_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_bitwidth_bit=Traced(64, design),
        lut_capacity_mb=Traced(1.0, design),
        lut_area_mm2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_bandwidth_mb_per_s=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        tile_connection=Traced(2, design),
        tile_num=Traced((64, 64), Provenance(kind="design", source="MNSIM default 64x64 tile grid")),
        weight_polarity=Traced(1, design),
        simulation_level=Traced(0, Provenance(kind="design", source="behavior level — MNSIM default path")),
        noc_enable=Traced(0, design),
    )

    return ArchitectureProfile(xbar=xbar, pe=pe, tile=tile, arch=arch)


def _mochida_chip() -> ChipProfile:
    return ChipProfile(
        chip_id="rram_vlsi2018_mochida",
        label="VLSI 2018 Mochida Panasonic analog ReRAM macro (40 nm)",
        source_kind="literature",
        source_ref=_MOCHIDA_SOURCE,
        device=_mochida_device(),
        circuit=_mochida_circuit(),
        architecture=_mochida_architecture(),
        note=(
            "Third RRAM literature anchor, 40 nm Panasonic 1T-1R analog. "
            "Silicon operating point (40 nm row of Table I): Area=2.71 "
            "mm^2, 0.66 TOPS, EF=66.5 TOPS/W at 1.1 V. Benchmark is a "
            "14x14 MNIST MLP (90.8%). Readout is a current-comparator "
            "SA so the Walden-FoM ADC overlay is N/A (no multi-bit ADC "
            "to replace). Device R, cell area, digital frequency, and "
            "the binary-cell abstraction of the analog device are proxies."
        ),
    )


# ---------------------------------------------------------------------------
# Literature chip: ISSCC 2022 Paper 11.7 (J.-W. Yan et al.)
# ---------------------------------------------------------------------------

_YAN_SOURCE = (
    "ISSCC 2022 Paper 11.7, J.-W. Yan et al., "
    "\"A 1.041-Mb/mm^2 27.38-TOPS/W Signed-INT8 Dynamic-Logic-Based ADC-less "
    "SRAM CIM Macro in 28nm\", DOI 10.1109/ISSCC42614.2022.9731545"
)
_YAN_MNSIM_SRC = (
    "MNSIM 2.0 Table III (ISSCC 22-11.7 row): 32 compartments x 16-row x "
    "64-col, 1 active row x 64 active cols, Res=1, Op=AND"
)


def _yan_device() -> DeviceProfile:
    phys = Provenance(kind="physical", source=_YAN_SOURCE)
    paper = Provenance(kind="empirical", source=_YAN_SOURCE)
    design = Provenance(kind="design", source=_YAN_SOURCE)

    # MNSIM represents SRAM's "resistance" as a symmetric equivalent pair
    # because the rest of Crossbar.py still reads Device_Resistance even
    # when device_type == 'SRAM'. The value has no physical meaning — see
    # configs/SimConfig.ini line 29: "when using SRAM type, the equvilant
    # resistance is: 1.7e6, 1.7e6".
    resistance = ResistancePair(
        hrs_ohm=1.7e6,
        lrs_ohm=1.7e6,
        provenance=Provenance(
            kind="proxy",
            source="MNSIM SRAM equivalent resistance (configs/SimConfig.ini)",
            note="SRAM has no HRS/LRS; MNSIM uses a symmetric 1.7 MΩ pair as placeholder.",
        ),
    )

    return DeviceProfile(
        tech_node_nm=Traced(28, phys),
        device_type=Traced("SRAM", phys),
        cell_type=Traced(
            "SRAM_6T",
            Provenance(
                kind="design",
                source=_YAN_SOURCE,
                note=(
                    "Paper reports a 1.34x compact 6T bitcell of 5.795 x 0.71 um; "
                    "MNSIM only distinguishes SRAM_6T vs NVM cells."
                ),
            ),
        ),
        transistor_tech_nm=Traced(28, phys),
        device_area_um2=Traced(
            0.25,
            Provenance(
                kind="empirical",
                source=_YAN_SOURCE,
                note="MNSIM SimConfig.ini line 12 cites 0.25 um^2 for this paper's bitcell.",
            ),
        ),
        device_level=Traced(
            2,
            Provenance(
                kind="design",
                source="MNSIM SimConfig.ini line 27: SRAM must set Device_Level=2",
            ),
        ),
        read_level=Traced(2, design),
        # 0.8 V supply per paper Fig 11.7.7; single-level read.
        read_voltage_v=Traced((0.0, 0.8), paper),
        # 3 ns per input bit at 333 MHz clock (paper Fig 11.7.7).
        read_latency_ns=Traced(3.0, paper),
        write_level=Traced(2, design),
        write_voltage_v=Traced((0.0, 0.8), paper),
        write_latency_ns=Traced(
            10.0,
            Provenance(
                kind="proxy",
                source="MNSIM generic default",
                note="Write latency is irrelevant to PIM compute path; kept at MNSIM default.",
            ),
        ),
        resistance=resistance,
        # SRAM has no device-to-device resistance variation model in MNSIM.
        variation=None,
        # SRAM has no SAF defect model.
        saf=None,
        read_energy_j=Traced(
            1.12e-15,
            Provenance(
                kind="proxy",
                source="MNSIM default SRAM read energy per bit",
                note=(
                    "Paper reports 27.38 TOPS/W aggregate efficiency but not a "
                    "per-bit read energy; we keep MNSIM's default so the baseline "
                    "line in the 3-way comparison is MNSIM-native."
                ),
            ),
        ),
        write_energy_j=Traced(
            1.6e-15,
            Provenance(
                kind="proxy",
                source="MNSIM default SRAM write energy per bit",
                note="Paper does not report per-bit write energy; MNSIM default.",
            ),
        ),
        label="Yan 11.7 SRAM CIM device (ISSCC 2022)",
        note="28 nm 6T SRAM bitcell for ADC-less DCC compute path.",
    )


def _yan_circuit() -> CircuitComponents:
    design = Provenance(kind="design", source=_YAN_SOURCE)

    # Digital PIM: MNSIM/Hardware_Model/ADC.py forces ADC_choice=8 (SA)
    # whenever PIM_Type=1 regardless of what's configured. Declaring preset 8
    # up front makes the intent explicit and the generated INI self-documenting.
    adc = ADCProfile(
        preset_id=8,
        provenance=Provenance(
            kind="empirical",
            source=(
                "MNSIM/Hardware_Model/ADC.py choice=8 (Sense Amp at 28 nm); "
                "auto-selected by MNSIM whenever PIM_Type=1."
            ),
            note=(
                "Paper is ADC-less (Dynamic Computing Circuit); the MNSIM path "
                "models this as a 1-bit SA per bitline column. The Walden-FoM "
                "overlay is therefore N/A for this chip."
            ),
        ),
        label="MNSIM SA preset (digital PIM forces this)",
    )

    # Digital PIM uses a 1-bit input interface. Using DAC_Choice=1 triggers
    # MNSIM's time-multiplex path which inflates latency spuriously here;
    # user-defined 1-bit DAC with near-zero area/power is the cleanest way
    # to represent the direct 1-bit WL driver.
    dac = DACProfile(
        preset_id=None,
        provenance=Provenance(
            kind="design",
            source=_YAN_SOURCE,
            note=(
                "Digital PIM 1-bit input interface per SimConfig.ini note; "
                "user-defined 1-bit DAC avoids the time-multiplex path."
            ),
        ),
        label="user-defined 1-bit DAC for digital PIM",
        precision_bit=Traced(1, design),
        area_um2=Traced(
            0.167,
            Provenance(
                kind="proxy",
                source="MNSIM preset 1 area; sufficient sentinel for a 1-bit WL driver",
            ),
        ),
        power_w=Traced(
            1e-6,
            Provenance(
                kind="proxy",
                source="1-bit WL driver power sentinel; negligible vs compute path",
            ),
        ),
        sample_rate_gsps=Traced(
            0.333,
            Provenance(
                kind="empirical",
                source=_YAN_SOURCE,
                note="333 MHz clock per paper Fig 11.7.7.",
            ),
        ),
    )

    dm_default = DigitalModuleSpec(
        tech_nm=Traced(45, Provenance(kind="physical", source="MNSIM default 45 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )
    dm_65 = DigitalModuleSpec(
        tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default 65 nm")),
        area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
        power_w=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin lookup")),
    )

    digital = DigitalModules(
        adder=dm_default,
        multiplier=dm_default,
        shift_reg=dm_65,
        reg=dm_default,
        joint_module=dm_default,
        digital_frequency_mhz=Traced(
            333.0,
            Provenance(
                kind="empirical",
                source=_YAN_SOURCE,
                note="333 MHz clock per paper Fig 11.7.7.",
            ),
        ),
    )

    return CircuitComponents(
        adc=adc,
        dac=dac,
        digital=digital,
        logic_op=Traced(
            0,
            Provenance(
                kind="empirical",
                source=_YAN_SOURCE,
                note=(
                    "Paper's default DCC operation is bitwise AND "
                    "(reconfigurable AND/OR/XOR); MNSIM Table III reports Op=AND."
                ),
            ),
        ),
    )


def _yan_architecture() -> ArchitectureProfile:
    design = Provenance(kind="design", source=_YAN_SOURCE)
    mnsim_tbl = Provenance(kind="empirical", source=_YAN_MNSIM_SRC)

    xbar = XbarProfile(
        rows=Traced(16, mnsim_tbl),
        cols=Traced(64, mnsim_tbl),
        subarray_size=Traced(16, design),
        wire_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 2.82 Ω")),
        wire_capacity_ff=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default 1 fF")),
        load_resistance_ohm=Traced(-1.0, Provenance(kind="proxy", source="MNSIM default sqrt(R_on*R_off)")),
        area_calculation_method=Traced(
            0,
            Provenance(
                kind="design",
                source="use Device_Area for area computation, matching Liu 33.2 path",
            ),
        ),
    )

    pe = PEProfile(
        pim_type=Traced(
            1,
            Provenance(
                kind="design",
                source=_YAN_SOURCE,
                note="Digital PIM: DCC performs bitwise compute after 1-bit WL drive.",
            ),
        ),
        # Digital PIM requires polarity=1 (enforced by ChipProfile.validate()).
        xbar_polarity=Traced(1, design),
        sub_position=Traced(0, design),
        group_num=Traced(
            32,
            Provenance(
                kind="empirical",
                source=_YAN_MNSIM_SRC,
                note="32 compartments per paper and MNSIM Table III.",
            ),
        ),
        # 1 active row × 64 active columns per cycle (MNSIM Table III).
        dac_num=Traced(1, mnsim_tbl),
        adc_num=Traced(64, mnsim_tbl),
        in_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        in_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
    )

    tile = TileProfile(
        pe_num=Traced((2, 2), design),
        pooling_shape=Traced((3, 3), design),
        pooling_unit_num=Traced(64, design),
        pooling_tech_nm=Traced(65, Provenance(kind="physical", source="MNSIM default")),
        pooling_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_adder_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_num=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        tile_shiftreg_level=Traced(0, Provenance(kind="proxy", source="MNSIM builtin")),
        inter_tile_bandwidth_gbps=Traced(20.0, design),
        intra_tile_bandwidth_gbps=Traced(1024.0, design),
        out_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        out_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_size_kb=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
        dfu_buf_area_um2=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin")),
    )

    arch = ArchLevelProfile(
        buffer_choice=Traced(1, design),
        buffer_tech_nm=Traced(28, Provenance(kind="design", source="28 nm node buffer")),
        buffer_read_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_write_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM builtin CACTI")),
        buffer_bitwidth_bit=Traced(64, design),
        lut_capacity_mb=Traced(1.0, design),
        lut_area_mm2=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_power_mw=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        lut_bandwidth_mb_per_s=Traced(0.0, Provenance(kind="proxy", source="MNSIM default")),
        tile_connection=Traced(2, design),
        tile_num=Traced((64, 64), Provenance(kind="design", source="MNSIM default 64x64 tile grid")),
        weight_polarity=Traced(1, design),
        simulation_level=Traced(0, Provenance(kind="design", source="behavior level — MNSIM default path")),
        noc_enable=Traced(0, design),
    )

    return ArchitectureProfile(xbar=xbar, pe=pe, tile=tile, arch=arch)


def _yan_chip() -> ChipProfile:
    return ChipProfile(
        chip_id="sram_isscc2022_11p7",
        label="ISSCC 2022 Paper 11.7 SRAM CIM macro",
        source_kind="literature",
        source_ref=_YAN_SOURCE,
        device=_yan_device(),
        circuit=_yan_circuit(),
        architecture=_yan_architecture(),
        note=(
            "Literature-anchor SRAM null-control for MNSIM 2.0 §VII.B Table IV. "
            "28 nm 6T SRAM + ADC-less Dynamic Computing Circuit, so pim_sim's "
            "RRAM-specific overlays (asymmetric CV, IR-drop, Walden ADC) are "
            "deliberately N/A — this chip's role is to confirm pim_sim reduces "
            "to the MNSIM baseline when none of its three pillars apply."
        ),
    )


_LITERATURE_CHIPS: dict[str, Callable[[], ChipProfile]] = {
    "rram_isscc2020_33p2": _liu_chip,
    "rram_isscc2020_33p2_mnsim_fit": _liu_chip_mnsim_fit,
    "rram_isscc2020_15p4": _xue_chip,
    "rram_vlsi2018_mochida": _mochida_chip,
    "sram_isscc2022_11p7": _yan_chip,
}


# ---------------------------------------------------------------------------
# Measured presets — wrap pim_sim.device.calibrated_presets into ChipProfile
# ---------------------------------------------------------------------------


def _measured_chip(preset_name: str) -> ChipProfile:
    from pim_sim.device.calibrated_presets import PRESETS, WAFER_MODELS, get_preset

    model = get_preset(preset_name)
    if preset_name in PRESETS:
        src = f"test_data calibrated preset '{preset_name}' (pim_sim/device/calibrated_presets.py)"
    elif preset_name in WAFER_MODELS:
        src = f"test_data per-wafer model '{preset_name}' (pim_sim/device/calibrated_presets.py)"
    else:
        src = f"measured preset '{preset_name}'"

    base = _liu_chip()  # carrier for architecture + circuit (unchanged by measurement)
    variation = AsymmetricVariation(
        kind="asymmetric_gaussian",
        state_cv_pct=tuple(float(v) for v in model.state_cv_pct),
        provenance=Provenance(kind="empirical", source=src),
    )
    new_device = base.device.with_variation(variation)
    return ChipProfile(
        chip_id=f"measured::{preset_name}",
        label=f"Measured device preset {preset_name}",
        source_kind="measured",
        source_ref=src,
        device=new_device,
        circuit=base.circuit,
        architecture=base.architecture,
        note=(
            "Measured-device profile. The device-variation field is wafer-"
            "calibrated (asymmetric); architecture/circuit inherit from the "
            "literature carrier chip so downstream translators stay simple."
        ),
    )


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def available_chips() -> list[str]:
    return sorted(_LITERATURE_CHIPS.keys())


def available_measured_presets() -> list[str]:
    from pim_sim.device.calibrated_presets import PRESETS, WAFER_MODELS

    return sorted(set(PRESETS.keys()) | set(WAFER_MODELS.keys()))


def load_chip(chip_id: str) -> ChipProfile:
    if chip_id not in _LITERATURE_CHIPS:
        raise KeyError(
            f"Unknown chip '{chip_id}'. Available: {available_chips()}"
        )
    return _LITERATURE_CHIPS[chip_id]()


def load_measured_device(preset_name: str) -> ChipProfile:
    return _measured_chip(preset_name)
