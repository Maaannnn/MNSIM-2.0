"""
Translate a ChipProfile into MNSIM's ``SimConfig.ini`` format.

Design notes
------------
MNSIM reads the INI via ``configparser``.  Section names and keys are
exact; values are strings parsed downstream.  We emit one block per MNSIM
section, in the order MNSIM's default SimConfig.ini uses, so a human can
diff our output against a hand-edited baseline.

Every emitted key carries an inline ``# [kind] source — note`` comment
when the underlying field has non-trivial provenance, so the generated
INI is self-auditing.
"""

from __future__ import annotations

from io import StringIO
from typing import Any, Iterable

from mnsim_adapter.chip import ChipProfile
from mnsim_adapter.circuit import ADCProfile, DACProfile, DigitalModuleSpec
from mnsim_adapter.device import DeviceProfile
from mnsim_adapter.provenance import Traced


def _fmt_num(value: Any) -> str:
    """Render a scalar for MNSIM's INI parser.

    MNSIM reads most fields with ``int(...)`` or ``float(...)``. We pass
    through ``%g`` for floats to avoid ``1e-06`` becoming ``1e-6`` oddness.
    """
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _fmt_tuple(values: Iterable[Any]) -> str:
    return ",".join(_fmt_num(v) for v in values)


def _emit(buf: StringIO, key: str, value: str, comment: str | None = None) -> None:
    # MNSIM's ConfigParser does NOT strip inline '#' comments, so provenance
    # notes must go on their own comment-line above the key=value line.
    if comment:
        buf.write(f"# {comment}\n")
    buf.write(f"{key} = {value}\n")


def _emit_traced(buf: StringIO, key: str, traced: Traced | None, *, default: str = "0") -> None:
    if traced is None:
        _emit(buf, key, default, comment="[missing] no value registered")
        return
    if isinstance(traced.value, tuple):
        rendered = _fmt_tuple(traced.value)
    else:
        rendered = _fmt_num(traced.value)
    _emit(buf, key, rendered, comment=traced.format_inline_comment())


def _render_device_section(buf: StringIO, chip: ChipProfile) -> None:
    d = chip.device
    buf.write("[Device level]\n")
    _emit_traced(buf, "Device_Tech", d.tech_node_nm)
    _emit_traced(buf, "Device_Type", d.device_type)
    _emit_traced(buf, "Device_Area", d.device_area_um2)
    _emit_traced(buf, "Read_Level", d.read_level)
    _emit_traced(buf, "Read_Voltage", d.read_voltage_v)
    _emit_traced(buf, "Write_Level", d.write_level)
    _emit_traced(buf, "Write_Voltage", d.write_voltage_v)
    _emit_traced(buf, "Read_Latency", d.read_latency_ns)
    _emit_traced(buf, "Write_Latency", d.write_latency_ns)
    _emit_traced(buf, "Device_Level", d.device_level)

    if d.resistance is not None:
        _emit(
            buf,
            "Device_Resistance",
            _fmt_tuple(d.resistance.as_mnsim_tuple()),
            comment=f"[{d.resistance.provenance.kind}] {d.resistance.provenance.source}".strip(),
        )
    else:
        _emit(buf, "Device_Resistance", "1e6,1e4", comment="[proxy] no resistance registered — using MNSIM generic default")

    # Device_Variation: MNSIM only reads a single CV% number. When the
    # profile uses asymmetric variation, we emit the HRS value here (the
    # conservative upper bound) and mark the other states in a comment
    # so the asymmetric pair is picked up by the pim_sim overlay path,
    # not by MNSIM.
    if d.variation is not None:
        if d.variation.kind == "symmetric_gaussian":
            _emit(
                buf,
                "Device_Variation",
                _fmt_num(d.variation.cv_pct),  # type: ignore[attr-defined]
                comment=f"[{d.variation.provenance.kind}] {d.variation.provenance.source}".strip(),
            )
        else:
            cv_hrs = d.variation.state_cv_pct[0]  # type: ignore[attr-defined]
            _emit(
                buf,
                "Device_Variation",
                _fmt_num(cv_hrs),
                comment=(
                    f"[{d.variation.provenance.kind}] "
                    f"asymmetric HRS CV for MNSIM path; full state_cv_pct="
                    f"{list(d.variation.state_cv_pct)} — consumed by pim_sim overlay"  # type: ignore[attr-defined]
                ),
            )
    else:
        _emit(buf, "Device_Variation", "1", comment="[proxy] no variation model registered — MNSIM default 1%")

    if d.saf is not None:
        _emit(
            buf,
            "Device_SAF",
            _fmt_tuple(d.saf.as_mnsim_tuple()),
            comment=f"[{d.saf.provenance.kind}] {d.saf.provenance.source}".strip(),
        )
    else:
        _emit(buf, "Device_SAF", "0.1,0.1", comment="[proxy] no SAF registered — MNSIM default 0.1/0.1")

    if d.read_energy_j is not None:
        _emit_traced(buf, "Read_Energy", d.read_energy_j)
    else:
        _emit(buf, "Read_Energy", "1.12e-15", comment="[proxy] SRAM default (unused for NVM)")
    if d.write_energy_j is not None:
        _emit_traced(buf, "Write_Energy", d.write_energy_j)
    else:
        _emit(buf, "Write_Energy", "1.6e-15", comment="[proxy] SRAM default (unused for NVM)")

    buf.write("\n")


def _render_crossbar_section(buf: StringIO, chip: ChipProfile) -> None:
    x = chip.architecture.xbar
    d = chip.device
    buf.write("[Crossbar level]\n")
    _emit(buf, "Xbar_Size", f"{x.rows.value},{x.cols.value}", comment=x.rows.format_inline_comment())
    _emit_traced(buf, "Subarray_Size", x.subarray_size)
    _emit_traced(buf, "Cell_Type", d.cell_type)
    _emit_traced(buf, "Transistor_Tech", d.transistor_tech_nm)
    _emit_traced(buf, "Wire_Resistance", x.wire_resistance_ohm)
    _emit_traced(buf, "Wire_Capacity", x.wire_capacity_ff)
    _emit_traced(buf, "Load_Resistance", x.load_resistance_ohm)
    _emit_traced(buf, "Area_Calculation", x.area_calculation_method)
    buf.write("\n")


def _render_adc_fields(buf: StringIO, adc: ADCProfile) -> None:
    if adc.preset_id is not None:
        _emit(
            buf,
            "ADC_Choice",
            str(int(adc.preset_id)),
            comment=f"[{adc.provenance.kind}] {adc.provenance.source}",
        )
        # MNSIM ignores explicit fields when preset is picked, but it
        # still reads them, so write zero sentinels.
        _emit(buf, "ADC_Area", "0", comment="[design] unused when preset_id set")
        _emit(buf, "ADC_Precision", "0", comment="[design] unused when preset_id set")
        _emit(buf, "ADC_Power", "0", comment="[design] unused when preset_id set")
        _emit(buf, "ADC_Sample_Rate", "0", comment="[design] unused when preset_id set")
    else:
        _emit(buf, "ADC_Choice", "-1", comment=f"[{adc.provenance.kind}] user-defined ADC")
        _emit_traced(buf, "ADC_Area", adc.area_um2)
        _emit_traced(buf, "ADC_Precision", adc.precision_bit)
        _emit_traced(buf, "ADC_Power", adc.power_w)
        _emit_traced(buf, "ADC_Sample_Rate", adc.sample_rate_gsps)
    if adc.interval_thres is not None:
        _emit_traced(buf, "ADC_Interval_Thres", adc.interval_thres)
    else:
        _emit(buf, "ADC_Interval_Thres", "-1", comment="[design] MNSIM default interval threshold")


def _render_dac_fields(buf: StringIO, dac: DACProfile) -> None:
    if dac.preset_id is not None:
        _emit(
            buf,
            "DAC_Choice",
            str(int(dac.preset_id)),
            comment=f"[{dac.provenance.kind}] {dac.provenance.source}",
        )
        _emit(buf, "DAC_Area", "0", comment="[design] unused when preset_id set")
        _emit(buf, "DAC_Precision", "0", comment="[design] unused when preset_id set")
        _emit(buf, "DAC_Power", "0", comment="[design] unused when preset_id set")
        _emit(buf, "DAC_Sample_Rate", "0", comment="[design] unused when preset_id set")
    else:
        _emit(buf, "DAC_Choice", "-1", comment=f"[{dac.provenance.kind}] user-defined DAC")
        _emit_traced(buf, "DAC_Area", dac.area_um2)
        _emit_traced(buf, "DAC_Precision", dac.precision_bit)
        _emit_traced(buf, "DAC_Power", dac.power_w)
        _emit_traced(buf, "DAC_Sample_Rate", dac.sample_rate_gsps)


def _render_interface_section(buf: StringIO, chip: ChipProfile) -> None:
    c = chip.circuit
    buf.write("[Interface level]\n")
    _render_dac_fields(buf, c.dac)
    _render_adc_fields(buf, c.adc)
    _emit_traced(buf, "Logic_Op", c.logic_op)
    buf.write("\n")


def _render_pe_section(buf: StringIO, chip: ChipProfile) -> None:
    pe = chip.architecture.pe
    buf.write("[Process element level]\n")
    _emit_traced(buf, "PIM_Type", pe.pim_type)
    _emit_traced(buf, "Xbar_Polarity", pe.xbar_polarity)
    _emit_traced(buf, "Sub_Position", pe.sub_position)
    _emit_traced(buf, "Group_Num", pe.group_num)
    _emit_traced(buf, "DAC_Num", pe.dac_num)
    _emit_traced(buf, "ADC_Num", pe.adc_num)
    _emit_traced(buf, "PE_inBuf_Size", pe.in_buf_size_kb)
    _emit_traced(buf, "PE_inBuf_Area", pe.in_buf_area_um2)
    # MNSIM also reads Tile_outBuf/DFU_Buf defaults from the PE section:
    _emit_traced(buf, "Tile_outBuf_Size", chip.architecture.tile.out_buf_size_kb)
    _emit_traced(buf, "Tile_outBuf_Area", chip.architecture.tile.out_buf_area_um2)
    _emit_traced(buf, "DFU_Buf_Size", chip.architecture.tile.dfu_buf_size_kb)
    _emit_traced(buf, "DFU_Buf_Area", chip.architecture.tile.dfu_buf_area_um2)
    buf.write("\n")


def _render_digital_module(buf: StringIO, prefix: str, spec: DigitalModuleSpec) -> None:
    _emit_traced(buf, f"{prefix}_Tech", spec.tech_nm)
    _emit_traced(buf, f"{prefix}_Area", spec.area_um2)
    _emit_traced(buf, f"{prefix}_Power", spec.power_w)


def _render_digital_section(buf: StringIO, chip: ChipProfile) -> None:
    dm = chip.circuit.digital
    buf.write("[Digital module]\n")
    _emit_traced(buf, "Digital_Frequency", dm.digital_frequency_mhz)
    _render_digital_module(buf, "Adder", dm.adder)
    _render_digital_module(buf, "Multiplier", dm.multiplier)
    _render_digital_module(buf, "ShiftReg", dm.shift_reg)
    _render_digital_module(buf, "Reg", dm.reg)
    _render_digital_module(buf, "JointModule", dm.joint_module)
    buf.write("\n")


def _render_tile_section(buf: StringIO, chip: ChipProfile) -> None:
    t = chip.architecture.tile
    buf.write("[Tile level]\n")
    _emit(buf, "PE_Num", f"{t.pe_num.value[0]},{t.pe_num.value[1]}", comment=t.pe_num.format_inline_comment())
    _emit(buf, "Pooling_shape", f"{t.pooling_shape.value[0]},{t.pooling_shape.value[1]}", comment=t.pooling_shape.format_inline_comment())
    _emit_traced(buf, "Pooling_unit_num", t.pooling_unit_num)
    _emit_traced(buf, "Pooling_Tech", t.pooling_tech_nm)
    _emit_traced(buf, "Pooling_area", t.pooling_area_um2)
    _emit_traced(buf, "Tile_Adder_Num", t.tile_adder_num)
    _emit_traced(buf, "Tile_Adder_Level", t.tile_adder_level)
    _emit_traced(buf, "Tile_ShiftReg_Num", t.tile_shiftreg_num)
    _emit_traced(buf, "Tile_ShiftReg_Level", t.tile_shiftreg_level)
    _emit_traced(buf, "Inter_Tile_Bandwidth", t.inter_tile_bandwidth_gbps)
    _emit_traced(buf, "Intra_Tile_Bandwidth", t.intra_tile_bandwidth_gbps)
    _emit_traced(buf, "Tile_outBuf_Size", t.out_buf_size_kb)
    _emit_traced(buf, "Tile_outBuf_Area", t.out_buf_area_um2)
    _emit_traced(buf, "DFU_Buf_Size", t.dfu_buf_size_kb)
    _emit_traced(buf, "DFU_Buf_Area", t.dfu_buf_area_um2)
    buf.write("\n")


def _render_arch_section(buf: StringIO, chip: ChipProfile) -> None:
    a = chip.architecture.arch
    buf.write("[Architecture level]\n")
    _emit_traced(buf, "Buffer_Choice", a.buffer_choice)
    _emit_traced(buf, "Buffer_Technology", a.buffer_tech_nm)
    _emit_traced(buf, "Buffer_ReadPower", a.buffer_read_power_mw)
    _emit_traced(buf, "Buffer_WritePower", a.buffer_write_power_mw)
    _emit_traced(buf, "Buffer_Bitwidth", a.buffer_bitwidth_bit)
    _emit_traced(buf, "LUT_Capacity", a.lut_capacity_mb)
    _emit_traced(buf, "LUT_Area", a.lut_area_mm2)
    _emit_traced(buf, "LUT_Power", a.lut_power_mw)
    _emit_traced(buf, "LUT_Bandwidth", a.lut_bandwidth_mb_per_s)
    _emit_traced(buf, "Tile_Connection", a.tile_connection)
    _emit(buf, "Tile_Num", f"{a.tile_num.value[0]},{a.tile_num.value[1]}", comment=a.tile_num.format_inline_comment())
    buf.write("\n")


def _render_algorithm_section(buf: StringIO, chip: ChipProfile) -> None:
    a = chip.architecture.arch
    buf.write("[Algorithm Configuration]\n")
    _emit_traced(buf, "Weight_Polarity", a.weight_polarity)
    _emit_traced(buf, "Simulation_Level", a.simulation_level)
    _emit_traced(buf, "NoC_enable", a.noc_enable)
    buf.write("\n")


def render_ini(chip: ChipProfile) -> str:
    """Return the full SimConfig.ini text for ``chip``."""
    buf = StringIO()
    buf.write("######## Hardware Configuration #####\n")
    buf.write(f"# chip_id       : {chip.chip_id}\n")
    buf.write(f"# label         : {chip.label}\n")
    buf.write(f"# source_kind   : {chip.source_kind}\n")
    buf.write(f"# source_ref    : {chip.source_ref}\n")
    if chip.note:
        buf.write(f"# note          : {chip.note}\n")
    buf.write("# generated by  : mnsim_adapter.mnsim_ini.render_ini\n")
    buf.write("\n")

    _render_device_section(buf, chip)
    _render_crossbar_section(buf, chip)
    _render_interface_section(buf, chip)
    _render_pe_section(buf, chip)
    _render_digital_section(buf, chip)
    _render_tile_section(buf, chip)
    _render_arch_section(buf, chip)
    _render_algorithm_section(buf, chip)
    return buf.getvalue()
