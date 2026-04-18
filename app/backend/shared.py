from __future__ import annotations

import csv
import configparser as cp
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


APP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_DIR.parent
DB_PATH = APP_DIR / "dse_records.db"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "dse"
PORT = int(os.environ.get("PORT", 5001))


META_COLS = {
    "algo", "seed", "eval_index", "phase",
    "latency_ns", "energy_nj", "area_um2", "power_w", "accuracy",
    "elapsed_s", "is_pareto", "extra_json",
    "run_id", "trial_dir", "dataset_module", "weights_path",
    "base_config_path", "device", "space_profile", "dataset_signature",
    "nn", "run_accuracy", "enable_saf", "enable_variation",
    "enable_rratio", "fixed_qrange", "accuracy_target", "source_dir",
}

TABLE_BROWSER_TABLES = (
    "opt_runs",
    "run_evaluations",
    "measurements",
    "design_points",
    "eval_contexts",
    "sim_configs",
)

DIM_TO_INI = {
    "adc_choice": ("Interface level", "ADC_Choice"),
    "dac_num": ("Process element level", "DAC_Num"),
    "xbar_polarity": ("Process element level", "Xbar_Polarity"),
    "sub_position": ("Process element level", "Sub_Position"),
    "group_num": ("Process element level", "Group_Num"),
    "pe_num": ("Tile level", "PE_Num"),
    "tile_connection": ("Architecture level", "Tile_Connection"),
    "inter_tile_bw": ("Tile level", "Inter_Tile_Bandwidth"),
}

RRAM_PRESETS = {
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

ANALYSIS_GROUP_FIELDS = (
    {"key": "algo", "kind": "field", "zh": "算法", "en": "Algorithm"},
    {"key": "space_profile", "kind": "field", "zh": "设计空间", "en": "Space Profile"},
    {"key": "run_group", "kind": "field", "zh": "实验组", "en": "Run Group"},
    {"key": "source_type", "kind": "field", "zh": "来源类型", "en": "Source Type"},
    {"key": "rram_preset", "kind": "param", "zh": "RRAM 预设", "en": "RRAM Preset"},
    {"key": "xbar_size", "kind": "param", "zh": "交叉阵列尺寸", "en": "Crossbar Size"},
    {"key": "adc_choice", "kind": "param", "zh": "ADC 选择", "en": "ADC Choice"},
    {"key": "dac_num", "kind": "param", "zh": "DAC 数量", "en": "DAC Number"},
    {"key": "xbar_polarity", "kind": "param", "zh": "阵列极性", "en": "Crossbar Polarity"},
    {"key": "sub_position", "kind": "param", "zh": "子阵位置", "en": "Sub Position"},
    {"key": "group_num", "kind": "param", "zh": "组数", "en": "Group Number"},
    {"key": "pe_num", "kind": "param", "zh": "PE 数量", "en": "PE Number"},
    {"key": "tile_connection", "kind": "param", "zh": "Tile 连接方式", "en": "Tile Connection"},
    {"key": "inter_tile_bw", "kind": "param", "zh": "Tile 间带宽", "en": "Inter-Tile Bandwidth"},
)


def safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except Exception:
        return None


def load_trial_manifest(trial_dir: Path) -> Optional[Dict[str, Any]]:
    manifest_path = trial_dir / "experiment_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def table_columns(db, table_name: str) -> List[str]:
    return [r["name"] for r in db.execute(f"PRAGMA table_info({table_name})").fetchall()]


def make_parser_from_content(content: str) -> cp.ConfigParser:
    parser = cp.ConfigParser()
    parser.optionxform = str
    parser.read_string(content or "")
    return parser


def to_ini_value(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    s = str(v)
    if "x" in s and all(p.strip("-").isdigit() for p in s.split("x")):
        return ",".join(part.strip() for part in s.split("x"))
    return s


def derive_effective_config(
    base_content: str,
    params: Dict[str, Any],
    *,
    scenario_patch: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    parser = make_parser_from_content(base_content)
    overrides: List[Dict[str, Any]] = []

    def apply_override(section: str, key: str, new_value: Any, source: str, dim: str) -> None:
        if not parser.has_section(section):
            parser.add_section(section)
        old_value = parser.get(section, key, fallback=None)
        parser.set(section, key, str(new_value))
        overrides.append({
            "dim": dim,
            "section": section,
            "key": key,
            "old_value": old_value,
            "new_value": str(new_value),
            "source": source,
        })

    for dim, value in params.items():
        if dim == "rram_preset":
            preset = RRAM_PRESETS.get(str(value), {})
            for section, kv in preset.items():
                for key, new_value in kv.items():
                    apply_override(section, key, new_value, "rram_preset", dim)
            continue

        if dim == "xbar_size":
            ini_value = to_ini_value(value)
            apply_override("Crossbar level", "Xbar_Size", ini_value, "design_point", dim)
            try:
                row = int(str(value).split("x")[0]) if "x" in str(value) else int(str(value).split(",")[0])
                cur_sub = int(parser.get("Crossbar level", "Subarray_Size", fallback=str(row)))
                apply_override("Crossbar level", "Subarray_Size", min(cur_sub, row), "xbar_size_guard", dim)
            except Exception:
                pass
            continue

        target = DIM_TO_INI.get(dim)
        if target:
            section, key = target
            apply_override(section, key, to_ini_value(value), "design_point", dim)

    if scenario_patch:
        for section, kv in scenario_patch.items():
            for key, new_value in kv.items():
                apply_override(section, key, new_value, "scenario_post_patch", "scenario")

    buf = io.StringIO()
    parser.write(buf)
    sections = []
    for section in parser.sections():
        items = [{"key": k, "value": v} for k, v in parser.items(section)]
        sections.append({"name": section, "items": items})

    return {
        "content": buf.getvalue(),
        "sections": sections,
        "overrides": overrides,
    }


def coerce_csv_cell(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if any(ch in lowered for ch in (".", "e")):
            return float(text)
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def read_typed_csv(path: Path) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            {key: coerce_csv_cell(value) for key, value in row.items()}
            for row in csv.DictReader(f)
        ]
