#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure data definitions for DSE space presets.

This module is intentionally dependency-free so reporting / CSV analysis
scripts can load design-space metadata without importing the heavy MNSIM
runtime stack from dse.core.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


RRAM_PRESETS: Dict[str, Dict[str, Dict[str, str]]] = {
    "P0": {
        "Device level": {
            "Device_Resistance": "1e6,1e4",
            "Device_Variation": "0.5",
            "Device_SAF": "0.01,0.01",
        },
    },
    "P1": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "1.0",
            "Device_SAF": "0.05,0.05",
        },
    },
    "P2": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "3.0",
            "Device_SAF": "0.05,0.05",
        },
    },
    "P3": {
        "Device level": {
            "Device_Resistance": "1e6,2e4",
            "Device_Variation": "1.5",
            "Device_SAF": "0.5,0.5",
        },
    },
    "P4": {
        "Device level": {
            "Device_Resistance": "5e5,5e4",
            "Device_Variation": "5.0",
            "Device_SAF": "1.0,1.0",
        },
    },
}


SPACE_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "rram_full": {
        "rram_preset": {
            "values": list(RRAM_PRESETS.keys()),
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (256, 256), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7, 8],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 64, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [1, 2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1, 2, 4],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4), (8, 8)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [0, 1, 2, 3],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [10, 20, 40, 80],
        },
    },
    "rram_v2": {
        "rram_preset": {
            "values": ["P0", "P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2, 3],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [40, 80],
        },
    },
    "rram_formal_v3": {
        "rram_preset": {
            "values": ["P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [80],
        },
    },
    "rram_guidance_v4": {
        "rram_preset": {
            "values": ["P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (256, 256), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0, 1],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2, 3],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [40, 80],
        },
    },
    # Frozen canonical space for clean re-run experiments (2026-04-27).
    # Any change requires bumping the version suffix; old data is then
    # auto-detected as different SPACE via space_hash().
    "clean_v1": {
        "rram_preset": {
            "values": ["P0", "P1", "P2", "P3"],
        },
        "xbar_size": {
            "section": "Crossbar level",
            "key": "Xbar_Size",
            "values": [(128, 128), (256, 256), (512, 512)],
        },
        "adc_choice": {
            "section": "Interface level",
            "key": "ADC_Choice",
            "values": [4, 6, 7],
        },
        "dac_num": {
            "section": "Process element level",
            "key": "DAC_Num",
            "values": [32, 128],
        },
        "xbar_polarity": {
            "section": "Process element level",
            "key": "Xbar_Polarity",
            "values": [1, 2],
        },
        "sub_position": {
            "section": "Process element level",
            "key": "Sub_Position",
            "values": [0],
        },
        "group_num": {
            "section": "Process element level",
            "key": "Group_Num",
            "values": [1],
        },
        "pe_num": {
            "section": "Tile level",
            "key": "PE_Num",
            "values": [(2, 2), (4, 4)],
        },
        "tile_connection": {
            "section": "Architecture level",
            "key": "Tile_Connection",
            "values": [2],
        },
        "inter_tile_bw": {
            "section": "Tile level",
            "key": "Inter_Tile_Bandwidth",
            "values": [80],
        },
    },
}


def space_hash(profile_name: str) -> str:
    """SHA-256 (truncated) of a SPACE_PROFILES entry.

    Embed in run manifests so historical data with a different SPACE
    definition is auto-detectable instead of silently mixed.
    """
    space = SPACE_PROFILES[profile_name]
    canonical = json.dumps(space, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def space_size(profile_name: str) -> int:
    n = 1
    for d in SPACE_PROFILES[profile_name].values():
        n *= len(d["values"])
    return n
