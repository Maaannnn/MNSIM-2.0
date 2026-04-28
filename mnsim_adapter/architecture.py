"""
Layer 3: ArchitectureProfile
============================
How a chip is organised above the single device: crossbar size,
PE-level composition, tile-level composition, architecture-level buffer
and LUT choices.

Maps to MNSIM sections ``[Crossbar level]`` (most of it), ``[Process
element level]``, ``[Tile level]``, ``[Architecture level]``, and the
``Simulation_Level`` / ``NoC_enable`` flags under ``[Algorithm
Configuration]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mnsim_adapter.provenance import Provenance, Traced


@dataclass(frozen=True)
class XbarProfile:
    """One crossbar."""

    rows: Traced[int]
    cols: Traced[int]
    subarray_size: Traced[int]

    wire_resistance_ohm: Traced[float]  # -1 triggers MNSIM default 2.82 ohm
    wire_capacity_ff: Traced[float]  # -1 triggers MNSIM default 1 fF
    load_resistance_ohm: Traced[float]  # -1 triggers sqrt(R_on*R_off)

    area_calculation_method: Traced[int]  # 0 or 1 (MNSIM)

    def __post_init__(self) -> None:
        if self.rows.value % self.subarray_size.value != 0:
            raise ValueError(
                f"Xbar rows ({self.rows.value}) must be divisible by "
                f"subarray_size ({self.subarray_size.value})"
            )


@dataclass(frozen=True)
class PEProfile:
    """Process element: groups of crossbars + interface + input buffer."""

    pim_type: Traced[int]  # 0 analog, 1 digital
    xbar_polarity: Traced[int]  # 1 or 2
    sub_position: Traced[int]  # 0 analog sub, 1 digital sub
    group_num: Traced[int]
    dac_num: Traced[int]  # per subarray per group
    adc_num: Traced[int]  # per subarray per group
    in_buf_size_kb: Traced[float]  # 0 -> MNSIM default
    in_buf_area_um2: Traced[float]  # 0 -> MNSIM default


@dataclass(frozen=True)
class TileProfile:
    """Tile: arrangement of PEs + pooling + tile-level buffers + bandwidth."""

    pe_num: Traced[tuple[int, int]]  # (x, y); (0,0) -> default 4x4
    pooling_shape: Traced[tuple[int, int]]  # (kh, kw); (0,0) -> default 3x3
    pooling_unit_num: Traced[int]
    pooling_tech_nm: Traced[int]
    pooling_area_um2: Traced[float]
    tile_adder_num: Traced[int]
    tile_adder_level: Traced[int]
    tile_shiftreg_num: Traced[int]
    tile_shiftreg_level: Traced[int]
    inter_tile_bandwidth_gbps: Traced[float]
    intra_tile_bandwidth_gbps: Traced[float]
    out_buf_size_kb: Traced[float]
    out_buf_area_um2: Traced[float]
    dfu_buf_size_kb: Traced[float]
    dfu_buf_area_um2: Traced[float]


@dataclass(frozen=True)
class ArchLevelProfile:
    """Architecture level: global buffer, LUT, tile grid, NoC, simulation mode."""

    buffer_choice: Traced[int]  # 0 user / 1 SRAM / 2 DRAM / 3 RRAM
    buffer_tech_nm: Traced[int]
    buffer_read_power_mw: Traced[float]
    buffer_write_power_mw: Traced[float]
    buffer_bitwidth_bit: Traced[int]

    lut_capacity_mb: Traced[float]
    lut_area_mm2: Traced[float]
    lut_power_mw: Traced[float]
    lut_bandwidth_mb_per_s: Traced[float]

    tile_connection: Traced[int]
    tile_num: Traced[tuple[int, int]]  # (x, y); (0,0) -> default 8x8

    weight_polarity: Traced[int]  # 1 or 2
    simulation_level: Traced[int]  # 0 behavior / 1 estimation
    noc_enable: Traced[int]  # 0 / 1


@dataclass(frozen=True)
class ArchitectureProfile:
    """Layer 3 root: xbar + PE + tile + architecture-level."""

    xbar: XbarProfile
    pe: PEProfile
    tile: TileProfile
    arch: ArchLevelProfile

    def with_xbar(self, xbar: XbarProfile) -> "ArchitectureProfile":
        from dataclasses import replace

        return replace(self, xbar=xbar)

    def with_tile_grid(self, tile_num: Traced[tuple[int, int]]) -> "ArchitectureProfile":
        from dataclasses import replace

        return replace(self, arch=replace(self.arch, tile_num=tile_num))
