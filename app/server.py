#!/usr/bin/env python3
"""
MNSIM DSE 实验记录查询服务

Usage:
    python app/server.py           # 默认 http://localhost:5001
    PORT=8080 python app/server.py
"""
from __future__ import annotations

import csv
import configparser as cp
import io
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, g, jsonify, request, send_from_directory

APP_DIR = Path(__file__).parent
REPO_ROOT = APP_DIR.parent
DB_PATH = APP_DIR / "dse_records.db"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "dse"
PORT = int(os.environ.get("PORT", 5001))

# Ensure dse module is importable for init_db
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

app = Flask(__name__, static_folder=str(APP_DIR / "static"))


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    from dse.db_writer import init_db as _init
    _init(str(DB_PATH))


# ── columns in history.csv that are NOT design-space parameters ───────────────

_META_COLS = {
    "algo", "seed", "eval_index", "phase",
    "latency_ns", "energy_nj", "area_um2", "power_w", "accuracy",
    "elapsed_s", "is_pareto", "extra_json",
    "run_id", "trial_dir", "dataset_module", "weights_path",
    "base_config_path", "device", "space_profile", "dataset_signature",
    "nn", "run_accuracy", "enable_saf", "enable_variation",
    "enable_rratio", "fixed_qrange", "accuracy_target", "source_dir",
}


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except Exception:
        return None


_TABLE_BROWSER_TABLES = (
    "opt_runs",
    "run_evaluations",
    "measurements",
    "design_points",
    "eval_contexts",
    "sim_configs",
)

_DIM_TO_INI = {
    "adc_choice": ("Interface level", "ADC_Choice"),
    "dac_num": ("Process element level", "DAC_Num"),
    "xbar_polarity": ("Process element level", "Xbar_Polarity"),
    "sub_position": ("Process element level", "Sub_Position"),
    "group_num": ("Process element level", "Group_Num"),
    "pe_num": ("Tile level", "PE_Num"),
    "tile_connection": ("Architecture level", "Tile_Connection"),
    "inter_tile_bw": ("Tile level", "Inter_Tile_Bandwidth"),
}

_RRAM_PRESETS = {
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

_ANALYSIS_GROUP_KEYS = (
    "rram_preset",
    "xbar_size",
    "adc_choice",
    "dac_num",
    "xbar_polarity",
    "sub_position",
    "group_num",
    "pe_num",
    "tile_connection",
    "inter_tile_bw",
)

_ANALYSIS_GROUP_FIELDS = (
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


def _table_columns(db: sqlite3.Connection, table_name: str) -> List[str]:
    return [r["name"] for r in db.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _make_parser_from_content(content: str) -> cp.ConfigParser:
    parser = cp.ConfigParser()
    parser.optionxform = str
    parser.read_string(content or "")
    return parser


def _to_ini_value(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    s = str(v)
    if "x" in s and all(p.strip("-").isdigit() for p in s.split("x")):
        return ",".join(part.strip() for part in s.split("x"))
    return s


def _derive_effective_config(base_content: str, params: Dict[str, Any]) -> Dict[str, Any]:
    parser = _make_parser_from_content(base_content)
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
            preset = _RRAM_PRESETS.get(str(value), {})
            for section, kv in preset.items():
                for key, new_value in kv.items():
                    apply_override(section, key, new_value, "rram_preset", dim)
            continue

        if dim == "xbar_size":
            ini_value = _to_ini_value(value)
            apply_override("Crossbar level", "Xbar_Size", ini_value, "design_point", dim)
            try:
                row = int(str(value).split("x")[0]) if "x" in str(value) else int(str(value).split(",")[0])
                cur_sub = int(parser.get("Crossbar level", "Subarray_Size", fallback=str(row)))
                apply_override("Crossbar level", "Subarray_Size", min(cur_sub, row), "xbar_size_guard", dim)
            except Exception:
                pass
            continue

        target = _DIM_TO_INI.get(dim)
        if target:
            section, key = target
            apply_override(section, key, _to_ini_value(value), "design_point", dim)

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


def _analysis_base_rows_for_run(db: sqlite3.Connection, run_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    run = db.execute("""
        SELECT r.id, r.run_group, r.algo, r.seed, r.space_profile, r.source_type,
               r.accuracy_target, r.budget, r.total_evaluated, r.pareto_size,
               r.hypervolume, r.wall_time_s, r.started_at, r.finished_at
        FROM opt_runs r
        WHERE r.id = ?
    """, (run_id,)).fetchone()
    if not run:
        raise KeyError(f"run not found: {run_id}")

    rows = db.execute("""
        SELECT re.id AS record_id,
               re.run_id,
               re.eval_index,
               re.phase,
               re.is_pareto AS run_pareto,
               m.id AS measurement_id,
               dp.id AS design_point_id,
               dp.params_json,
               m.latency_ns,
               m.energy_nj,
               m.area_um2,
               m.power_w,
               m.accuracy,
               m.elapsed_s,
               m.measured_at
        FROM run_evaluations re
        JOIN measurements m   ON re.measurement_id = m.id
        JOIN design_points dp ON m.design_point_id = dp.id
        WHERE re.run_id = ?
        ORDER BY re.eval_index
    """, (run_id,)).fetchall()

    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["params"] = json.loads(item.pop("params_json") or "{}")
        parsed_rows.append(item)
    return dict(run), parsed_rows


def _build_run_filter_clause(args) -> Tuple[List[str], List[Any]]:
    where: List[str] = []
    params: List[Any] = []

    for field, col in [("algo", "r.algo"), ("space", "r.space_profile"),
                       ("group", "r.run_group"), ("source", "r.source_type"),
                       ("status", "r.status")]:
        val = args.get(field)
        if val:
            where.append(f"{col}=?")
            params.append(val)

    q = (args.get("q") or "").strip()
    if q:
        where.append("(r.algo LIKE ? OR r.run_group LIKE ? OR r.space_profile LIKE ?)")
        params += [f"%{q}%"] * 3
    return where, params


def _analysis_base_rows_for_runs(db: sqlite3.Connection, run_ids: List[int]) -> List[Dict[str, Any]]:
    if not run_ids:
        return []
    ph = ",".join("?" for _ in run_ids)
    rows = db.execute(f"""
        SELECT re.id AS record_id,
               re.run_id,
               re.eval_index,
               re.phase,
               re.is_pareto AS run_pareto,
               m.id AS measurement_id,
               dp.id AS design_point_id,
               dp.params_json,
               m.latency_ns,
               m.energy_nj,
               m.area_um2,
               m.power_w,
               m.accuracy,
               m.elapsed_s,
               m.measured_at,
               r.run_group,
               r.algo,
               r.seed,
               r.space_profile,
               r.source_type,
               r.accuracy_target
        FROM run_evaluations re
        JOIN measurements m   ON re.measurement_id = m.id
        JOIN design_points dp ON m.design_point_id = dp.id
        JOIN opt_runs r       ON re.run_id = r.id
        WHERE re.run_id IN ({ph})
        ORDER BY r.started_at DESC, re.run_id DESC, re.eval_index
    """, run_ids).fetchall()

    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["params"] = json.loads(item.pop("params_json") or "{}")
        parsed_rows.append(item)
    return parsed_rows


def _analysis_is_feasible(row: Dict[str, Any], accuracy_target: Optional[float]) -> bool:
    if accuracy_target is None:
        return True
    acc = row.get("accuracy")
    if acc is None:
        return False
    return float(acc) >= float(accuracy_target)


def _analysis_dominates(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _analysis_mark_global_pareto(rows: List[Dict[str, Any]]) -> None:
    valid_indices = [
        idx for idx, row in enumerate(rows)
        if row.get("feasible")
        and row.get("latency_ns") is not None
        and row.get("energy_nj") is not None
        and row.get("area_um2") is not None
    ]
    pareto_indices: List[int] = []
    for i in valid_indices:
        obj_i = (
            float(rows[i]["latency_ns"]),
            float(rows[i]["energy_nj"]),
            float(rows[i]["area_um2"]),
        )
        dominated = False
        for j in valid_indices:
            if i == j:
                continue
            obj_j = (
                float(rows[j]["latency_ns"]),
                float(rows[j]["energy_nj"]),
                float(rows[j]["area_um2"]),
            )
            if _analysis_dominates(obj_j, obj_i):
                dominated = True
                break
        if not dominated:
            pareto_indices.append(i)

    pareto_index_set = set(pareto_indices)
    for idx, row in enumerate(rows):
        row["global_pareto"] = idx in pareto_index_set


def _analysis_best_record(rows: List[Dict[str, Any]], metric: str, reverse: bool = False) -> Optional[Dict[str, Any]]:
    candidates = [row for row in rows if row.get(metric) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row[metric])) if reverse else min(candidates, key=lambda row: float(row[metric]))


def _analysis_score_rows(rows: List[Dict[str, Any]]) -> None:
    metric_keys = ("latency_ns", "energy_nj", "area_um2")
    scored_rows = [row for row in rows if all(row.get(key) is not None for key in metric_keys)]
    if not scored_rows:
        for row in rows:
            row["analysis_score"] = None
        return

    mins = {key: min(float(row[key]) for row in scored_rows) for key in metric_keys}
    maxs = {key: max(float(row[key]) for row in scored_rows) for key in metric_keys}
    for row in rows:
        if not all(row.get(key) is not None for key in metric_keys):
            row["analysis_score"] = None
            continue
        score = 0.0
        for key in metric_keys:
            lo = mins[key]
            hi = maxs[key]
            cur = float(row[key])
            score += 0.0 if hi == lo else (cur - lo) / (hi - lo)
        if not row.get("feasible"):
            score += 3.0
        if not row.get("global_pareto"):
            score += 0.5
        row["analysis_score"] = score


def _analysis_top_configs(rows: List[Dict[str, Any]], topk: int = 10) -> List[Dict[str, Any]]:
    _analysis_score_rows(rows)

    def sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
        return (
            0 if row.get("feasible") else 1,
            0 if row.get("global_pareto") else 1,
            row.get("analysis_score") if row.get("analysis_score") is not None else float("inf"),
            row.get("latency_ns") if row.get("latency_ns") is not None else float("inf"),
            row.get("energy_nj") if row.get("energy_nj") is not None else float("inf"),
            row.get("area_um2") if row.get("area_um2") is not None else float("inf"),
            row.get("eval_index") if row.get("eval_index") is not None else float("inf"),
        )

    top_rows = sorted(rows, key=sort_key)[:topk]
    result: List[Dict[str, Any]] = []
    for row in top_rows:
        result.append({
            "record_id": row["record_id"],
            "run_id": row["run_id"],
            "run_group": row.get("run_group"),
            "algo": row.get("algo"),
            "seed": row.get("seed"),
            "space_profile": row.get("space_profile"),
            "measurement_id": row["measurement_id"],
            "design_point_id": row["design_point_id"],
            "eval_index": row["eval_index"],
            "phase": row["phase"],
            "run_pareto": bool(row.get("run_pareto")),
            "global_pareto": bool(row.get("global_pareto")),
            "feasible": bool(row.get("feasible")),
            "latency_ns": row.get("latency_ns"),
            "energy_nj": row.get("energy_nj"),
            "area_um2": row.get("area_um2"),
            "power_w": row.get("power_w"),
            "accuracy": row.get("accuracy"),
            "elapsed_s": row.get("elapsed_s"),
            "analysis_score": row.get("analysis_score"),
            "params": row.get("params", {}),
        })
    return result


def _analysis_group_sections(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for field in _ANALYSIS_GROUP_FIELDS:
        key = field["key"]
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            value = row.get(key) if field["kind"] == "field" else row.get("params", {}).get(key)
            if value in (None, ""):
                continue
            buckets.setdefault(str(value), []).append(row)
        if not buckets:
            continue

        section_rows: List[Dict[str, Any]] = []
        for group_value, bucket in buckets.items():
            feasible = [row for row in bucket if row.get("feasible")]
            global_pareto = [row for row in bucket if row.get("global_pareto")]
            best_latency = _analysis_best_record(bucket, "latency_ns")
            best_energy = _analysis_best_record(bucket, "energy_nj")
            best_area = _analysis_best_record(bucket, "area_um2")
            best_accuracy = _analysis_best_record(bucket, "accuracy", reverse=True)
            section_rows.append({
                "group_value": group_value,
                "samples": len(bucket),
                "feasible_samples": len(feasible),
                "feasible_rate": (len(feasible) / len(bucket)) if bucket else 0.0,
                "global_pareto_samples": len(global_pareto),
                "unique_design_points": len({row["design_point_id"] for row in bucket}),
                "best_latency_ns": best_latency["latency_ns"] if best_latency else None,
                "best_energy_nj": best_energy["energy_nj"] if best_energy else None,
                "best_area_um2": best_area["area_um2"] if best_area else None,
                "best_accuracy": best_accuracy["accuracy"] if best_accuracy else None,
            })

        section_rows.sort(
            key=lambda row: (
                -(row["feasible_rate"] or 0.0),
                -row["global_pareto_samples"],
                -row["samples"],
                row["group_value"],
            )
        )
        result.append({
            "key": key,
            "kind": field["kind"],
            "label_zh": field["zh"],
            "label_en": field["en"],
            "rows": section_rows,
        })
    return result


def _build_analysis_payload(scope: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        row["feasible"] = _analysis_is_feasible(row, _safe_float(row.get("accuracy_target")))
    _analysis_mark_global_pareto(rows)

    feasible_rows = [row for row in rows if row.get("feasible")]
    global_pareto_rows = [row for row in rows if row.get("global_pareto")]
    best_latency = _analysis_best_record(rows, "latency_ns")
    best_energy = _analysis_best_record(rows, "energy_nj")
    best_area = _analysis_best_record(rows, "area_um2")
    best_accuracy = _analysis_best_record(rows, "accuracy", reverse=True)

    return {
        "scope": scope,
        "summary": {
            "samples": len(rows),
            "feasible_samples": len(feasible_rows),
            "feasible_rate": (len(feasible_rows) / len(rows)) if rows else 0.0,
            "global_pareto_samples": len(global_pareto_rows),
            "unique_measurements": len({row["measurement_id"] for row in rows}),
            "unique_design_points": len({row["design_point_id"] for row in rows}),
            "best_latency_ns": best_latency["latency_ns"] if best_latency else None,
            "best_latency_eval_index": best_latency["eval_index"] if best_latency else None,
            "best_energy_nj": best_energy["energy_nj"] if best_energy else None,
            "best_energy_eval_index": best_energy["eval_index"] if best_energy else None,
            "best_area_um2": best_area["area_um2"] if best_area else None,
            "best_area_eval_index": best_area["eval_index"] if best_area else None,
            "best_accuracy": best_accuracy["accuracy"] if best_accuracy else None,
            "best_accuracy_eval_index": best_accuracy["eval_index"] if best_accuracy else None,
        },
        "plot_rows": [
            {
                "record_id": row["record_id"],
                "run_id": row["run_id"],
                "eval_index": row.get("eval_index"),
                "phase": row.get("phase"),
                "run_group": row.get("run_group"),
                "algo": row.get("algo"),
                "seed": row.get("seed"),
                "latency_ns": row.get("latency_ns"),
                "energy_nj": row.get("energy_nj"),
                "area_um2": row.get("area_um2"),
                "accuracy": row.get("accuracy"),
                "feasible": bool(row.get("feasible")),
                "global_pareto": bool(row.get("global_pareto")),
                "rram_preset": (row.get("params") or {}).get("rram_preset"),
                "xbar_size": (row.get("params") or {}).get("xbar_size"),
                "adc_choice": (row.get("params") or {}).get("adc_choice"),
                "dac_num": (row.get("params") or {}).get("dac_num"),
                "pe_num": (row.get("params") or {}).get("pe_num"),
            }
            for row in rows
        ],
        "top_configs": _analysis_top_configs(rows, topk=10),
        "group_sections": _analysis_group_sections(rows),
    }


def _build_run_analysis(run: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        row["run_group"] = run.get("run_group")
        row["algo"] = run.get("algo")
        row["seed"] = run.get("seed")
        row["space_profile"] = run.get("space_profile")
        row["source_type"] = run.get("source_type")
        row["accuracy_target"] = run.get("accuracy_target")

    return _build_analysis_payload({
        "mode": "run",
        "run_id": run["id"],
        "run_group": run.get("run_group"),
        "algo": run.get("algo"),
        "seed": run.get("seed"),
        "space_profile": run.get("space_profile"),
        "source_type": run.get("source_type"),
        "accuracy_target": _safe_float(run.get("accuracy_target")),
    }, rows)


# ── Import / Sync ─────────────────────────────────────────────────────────────

def sync_data() -> Dict[str, int]:
    """
    Scan artifacts/dse/{search,matrix}_runs for result.json+history.csv pairs
    and import any runs not yet in the DB.
    """
    import hashlib

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()
    imported = skipped = errors = 0

    def _md5(path: str, length: int = 32) -> str:
        p = Path(path).expanduser().resolve()
        data = p.read_bytes() if p.exists() else b""
        return hashlib.md5(data).hexdigest()[:length]

    def _sha1(obj: Any, length: int = 12) -> str:
        s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(s.encode()).hexdigest()[:length]

    def _ensure_sim_config(cfg_path: str) -> int:
        p = Path(cfg_path).expanduser().resolve()
        name = p.stem
        content_hash = _md5(cfg_path)
        content = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        cur.execute(
            "INSERT OR IGNORE INTO sim_configs (name, content_hash, content) VALUES (?,?,?)",
            (name, content_hash, content),
        )
        return cur.execute(
            "SELECT id FROM sim_configs WHERE content_hash=?", (content_hash,)
        ).fetchone()["id"]

    def _ensure_eval_context(sim_config_id: int, rc: Dict[str, Any]) -> int:
        payload = {
            "sim_config_id": sim_config_id,
            "nn": rc.get("nn", ""),
            "dataset_module": rc.get("dataset_module", ""),
            "weights_path": str(rc.get("weights_path", "")),
            "run_accuracy": int(bool(rc.get("run_accuracy", False))),
            "enable_saf": int(bool(rc.get("enable_saf", False))),
            "enable_variation": int(bool(rc.get("enable_variation", False))),
            "enable_rratio": int(bool(rc.get("enable_rratio", False))),
            "fixed_qrange": int(bool(rc.get("fixed_qrange", False))),
        }
        ctx_hash = _sha1(payload)
        cur.execute("""
            INSERT OR IGNORE INTO eval_contexts
              (context_hash, sim_config_id, nn, dataset_module, weights_path,
               run_accuracy, enable_saf, enable_variation, enable_rratio, fixed_qrange)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            ctx_hash, sim_config_id,
            payload["nn"], payload["dataset_module"], payload["weights_path"],
            payload["run_accuracy"], payload["enable_saf"], payload["enable_variation"],
            payload["enable_rratio"], payload["fixed_qrange"],
        ))
        return cur.execute(
            "SELECT id FROM eval_contexts WHERE context_hash=?", (ctx_hash,)
        ).fetchone()["id"]

    def _ensure_design_point(space_profile: str, params: Dict[str, Any]) -> int:
        norm = {k: str(v) for k, v in sorted(params.items())}
        params_hash = _sha1(norm)
        params_json = json.dumps(norm, sort_keys=True)
        cur.execute(
            "INSERT OR IGNORE INTO design_points (space_profile, params_hash, params_json) VALUES (?,?,?)",
            (space_profile, params_hash, params_json),
        )
        return cur.execute(
            "SELECT id FROM design_points WHERE space_profile=? AND params_hash=?",
            (space_profile, params_hash),
        ).fetchone()["id"]

    def _upsert_measurement(dp_id: int, ctx_id: int, row: Dict[str, str]) -> int:
        cur.execute("""
            INSERT OR IGNORE INTO measurements
              (design_point_id, eval_context_id, latency_ns, energy_nj,
               area_um2, power_w, accuracy, elapsed_s)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            dp_id, ctx_id,
            _safe_float(row.get("latency_ns")),
            _safe_float(row.get("energy_nj")),
            _safe_float(row.get("area_um2")),
            _safe_float(row.get("power_w")),
            _safe_float(row.get("accuracy")),
            _safe_float(row.get("elapsed_s")),
        ))
        return cur.execute(
            "SELECT id FROM measurements WHERE design_point_id=? AND eval_context_id=?",
            (dp_id, ctx_id),
        ).fetchone()["id"]

    scan_roots = [
        ARTIFACTS_ROOT / "search_runs",
        ARTIFACTS_ROOT / "matrix_runs",
    ]
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for result_path in scan_root.rglob("result.json"):
            trial_dir = result_path.parent
            history_csv = trial_dir / "history.csv"
            if not history_csv.exists():
                continue

            # Skip already-imported runs
            if cur.execute(
                "SELECT 1 FROM opt_runs WHERE trial_dir=?", (str(trial_dir),)
            ).fetchone():
                skipped += 1
                continue

            try:
                with open(result_path, encoding="utf-8") as f:
                    res = json.load(f)
            except Exception as e:
                print(f"[sync] skip {result_path}: {e}")
                errors += 1
                continue

            rc = res.get("run_config", {})
            ak = rc.get("algo_kwargs", {})
            parts = set(trial_dir.parts)
            source_type = "matrix" if "matrix_runs" in parts else "search"
            run_group = trial_dir.parent.name

            try:
                cfg_path = rc.get("base_config_path", "SimConfig.ini")
                sim_config_id = _ensure_sim_config(cfg_path)
                ctx_id = _ensure_eval_context(sim_config_id, rc)
                space_profile = rc.get("space_profile", res.get("space_profile", ""))
                accuracy_target = ak.get("accuracy_target") or res.get("accuracy_target")

                cur.execute("""
                    INSERT OR IGNORE INTO opt_runs
                      (trial_dir, run_group, source_type, algo, seed, space_profile,
                       eval_context_id, accuracy_target, budget, status,
                       total_evaluated, pareto_size, hypervolume, hv_reference_point,
                       wall_time_s, started_at, finished_at, run_config_json)
                    VALUES (?,?,?,?,?,?,?,?,?,'completed',?,?,?,?,?,?,?,?)
                """, (
                    str(trial_dir), run_group, source_type,
                    res.get("algo", ""), res.get("seed", 0), space_profile,
                    ctx_id, accuracy_target,
                    rc.get("budget", res.get("budget", 0)),
                    res.get("total_evaluated", 0),
                    res.get("pareto_size", 0),
                    res.get("hypervolume"),
                    json.dumps(res["hv_reference_point"]) if res.get("hv_reference_point") else None,
                    res.get("wall_time_s"),
                    res.get("started_at"),
                    res.get("finished_at"),
                    json.dumps(rc),
                ))
                run_id = cur.execute(
                    "SELECT id FROM opt_runs WHERE trial_dir=?", (str(trial_dir),)
                ).fetchone()["id"]

                # Import history rows
                with open(history_csv, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        params = {k: v for k, v in row.items()
                                  if k not in _META_COLS and v not in ("", None)}
                        dp_id = _ensure_design_point(space_profile, params)
                        meas_id = _upsert_measurement(dp_id, ctx_id, row)
                        is_p = row.get("is_pareto", "0")
                        cur.execute("""
                            INSERT OR IGNORE INTO run_evaluations
                              (run_id, measurement_id, eval_index, phase, is_pareto)
                            VALUES (?,?,?,?,?)
                        """, (
                            run_id, meas_id,
                            int(row.get("eval_index") or 0),
                            row.get("phase", ""),
                            1 if is_p in ("1", "True", "true") else 0,
                        ))

                con.commit()
                imported += 1
                print(f"[sync] + {trial_dir.name}")
            except Exception as e:
                con.rollback()
                print(f"[sync] error {trial_dir.name}: {e}")
                errors += 1

    con.close()
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    db = get_db()
    return jsonify({
        "total_runs":      db.execute("SELECT COUNT(*) FROM opt_runs").fetchone()[0],
        "total_records":   db.execute("SELECT COUNT(*) FROM run_evaluations").fetchone()[0],
        "total_pareto":    db.execute("SELECT COUNT(*) FROM run_evaluations WHERE is_pareto=1").fetchone()[0],
        "total_design_points": db.execute("SELECT COUNT(*) FROM design_points").fetchone()[0],
        "total_measurements":  db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0],
        "algos":  [r[0] for r in db.execute(
            "SELECT DISTINCT algo FROM opt_runs WHERE algo!='' ORDER BY algo")],
        "spaces": [r[0] for r in db.execute(
            "SELECT DISTINCT space_profile FROM opt_runs WHERE space_profile!='' ORDER BY space_profile")],
        "groups": [r[0] for r in db.execute(
            "SELECT DISTINCT run_group FROM opt_runs ORDER BY run_group")],
        "sim_configs": [dict(r) for r in db.execute(
            "SELECT id, name, content_hash, created_at FROM sim_configs ORDER BY id")],
    })


@app.route("/api/runs")
def api_runs():
    db = get_db()
    where, params = _build_run_filter_clause(request.args)

    sql = """
        SELECT r.*,
               sc.name           AS sim_config_name,
               sc.content_hash   AS sim_config_hash,
               ec.run_accuracy,
               ec.enable_saf,
               ec.enable_variation,
               ec.enable_rratio,
               ec.fixed_qrange,
               ec.nn, ec.dataset_module, ec.weights_path
        FROM opt_runs r
        LEFT JOIN eval_contexts ec ON r.eval_context_id = ec.id
        LEFT JOIN sim_configs sc   ON ec.sim_config_id  = sc.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.started_at DESC, r.id DESC"

    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/runs/<int:run_id>")
def api_run_detail(run_id):
    db = get_db()
    run = db.execute("""
        SELECT r.*,
               sc.name        AS sim_config_name,
               sc.content_hash AS sim_config_hash,
               sc.content     AS sim_config_content,
               ec.nn, ec.dataset_module, ec.weights_path,
               ec.run_accuracy, ec.enable_saf, ec.enable_variation,
               ec.enable_rratio, ec.fixed_qrange
        FROM opt_runs r
        LEFT JOIN eval_contexts ec ON r.eval_context_id = ec.id
        LEFT JOIN sim_configs sc   ON ec.sim_config_id  = sc.id
        WHERE r.id=?
    """, (run_id,)).fetchone()
    if not run:
        return jsonify({"error": "not found"}), 404
    d = dict(run)
    d["run_config"] = json.loads(d.pop("run_config_json") or "{}")
    d["hv_reference_point"] = json.loads(d["hv_reference_point"] or "null")
    return jsonify(d)


@app.route("/api/runs/<int:run_id>/records")
def api_run_records(run_id):
    db = get_db()
    pareto_only = request.args.get("pareto") == "1"
    sql = """
        SELECT re.id AS record_id,
               re.run_id,
               re.eval_index, re.phase, re.is_pareto,
               m.latency_ns, m.energy_nj, m.area_um2, m.power_w,
               m.accuracy, m.elapsed_s, m.measured_at,
               dp.params_json,
               m.id AS measurement_id,
               dp.id AS design_point_id
        FROM run_evaluations re
        JOIN measurements m  ON re.measurement_id = m.id
        JOIN design_points dp ON m.design_point_id = dp.id
        WHERE re.run_id=?
    """
    if pareto_only:
        sql += " AND re.is_pareto=1"
    sql += " ORDER BY re.eval_index"
    rows = db.execute(sql, [run_id]).fetchall()
    result = []
    for row in rows:
        r = dict(row)
        r["params"] = json.loads(r.pop("params_json") or "{}")
        result.append(r)
    return jsonify(result)


@app.route("/api/records/<int:record_id>/effective_config")
def api_record_effective_config(record_id: int):
    db = get_db()
    row = db.execute("""
        SELECT re.id AS record_id,
               re.run_id,
               re.eval_index,
               re.phase,
               re.is_pareto,
               r.space_profile,
               sc.id AS sim_config_id,
               sc.name AS sim_config_name,
               sc.content_hash,
               sc.content AS base_config_content,
               dp.id AS design_point_id,
               dp.params_json
        FROM run_evaluations re
        JOIN opt_runs r        ON re.run_id = r.id
        JOIN measurements m    ON re.measurement_id = m.id
        JOIN design_points dp  ON m.design_point_id = dp.id
        JOIN eval_contexts ec  ON r.eval_context_id = ec.id
        JOIN sim_configs sc    ON ec.sim_config_id = sc.id
        WHERE re.id = ?
    """, (record_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404

    data = dict(row)
    params = json.loads(data.pop("params_json") or "{}")
    effective = _derive_effective_config(data.pop("base_config_content") or "", params)

    return jsonify({
        **data,
        "params": params,
        "effective_config": effective,
    })


@app.route("/api/runs/<int:run_id>/analysis")
def api_run_analysis(run_id: int):
    db = get_db()
    try:
        run, rows = _analysis_base_rows_for_run(db, run_id)
    except KeyError:
        return jsonify({"error": "not found"}), 404
    return jsonify(_build_run_analysis(run, rows))


@app.route("/api/analysis/global")
def api_global_analysis():
    db = get_db()
    where, params = _build_run_filter_clause(request.args)
    sql = "SELECT r.id, r.run_group, r.algo, r.seed, r.space_profile, r.source_type, r.status FROM opt_runs r"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.started_at DESC, r.id DESC"
    run_rows = db.execute(sql, params).fetchall()
    run_dicts = [dict(row) for row in run_rows]
    run_ids = [int(row["id"]) for row in run_rows]
    rows = _analysis_base_rows_for_runs(db, run_ids)
    payload = _build_analysis_payload({
        "mode": "global",
        "filters": {
            "algo": request.args.get("algo") or "",
            "space": request.args.get("space") or "",
            "group": request.args.get("group") or "",
            "source": request.args.get("source") or "",
            "status": request.args.get("status") or "",
            "q": (request.args.get("q") or "").strip(),
        },
        "matched_runs": len(run_rows),
        "run_ids": run_ids,
        "runs": run_dicts,
    }, rows)
    payload["summary"]["matched_runs"] = len(run_rows)
    return jsonify(payload)


@app.route("/api/db/tables")
def api_db_tables():
    db = get_db()
    result = []
    for table_name in _TABLE_BROWSER_TABLES:
        columns = _table_columns(db, table_name)
        count = db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        result.append({
            "name": table_name,
            "count": count,
            "columns": columns,
        })
    return jsonify(result)


@app.route("/api/db/tables/<table_name>")
def api_db_table_rows(table_name: str):
    if table_name not in _TABLE_BROWSER_TABLES:
        return jsonify({"error": "table not found"}), 404

    db = get_db()
    columns = _table_columns(db, table_name)
    limit = min(max(int(request.args.get("limit", 50) or 50), 1), 200)
    offset = max(int(request.args.get("offset", 0) or 0), 0)
    q = request.args.get("q", "").strip()

    where_sql = ""
    params: List[Any] = []
    if q and columns:
        where_sql = " WHERE (" + " OR ".join(
            f"CAST({col} AS TEXT) LIKE ?" for col in columns
        ) + ")"
        params = [f"%{q}%"] * len(columns)

    total = db.execute(
        f"SELECT COUNT(*) FROM {table_name}{where_sql}",
        params,
    ).fetchone()[0]

    order_sql = "id DESC" if "id" in columns else "rowid DESC"
    rows = db.execute(
        f"SELECT * FROM {table_name}{where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return jsonify({
        "table": table_name,
        "columns": columns,
        "rows": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.route("/api/design_points")
def api_design_points():
    """List unique design points, optionally filtered by space_profile."""
    db = get_db()
    space = request.args.get("space")
    if space:
        rows = db.execute(
            "SELECT * FROM design_points WHERE space_profile=? ORDER BY id",
            (space,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM design_points ORDER BY id").fetchall()
    result = []
    for row in rows:
        r = dict(row)
        r["params"] = json.loads(r.pop("params_json") or "{}")
        result.append(r)
    return jsonify(result)


@app.route("/api/design_points/<int:dp_id>/measurements")
def api_dp_measurements(dp_id: int):
    """All measurements for a design point across all contexts."""
    db = get_db()
    rows = db.execute("""
        SELECT m.*,
               ec.context_hash, sc.name AS sim_config_name,
               ec.nn, ec.run_accuracy, ec.enable_saf, ec.enable_variation
        FROM measurements m
        JOIN eval_contexts ec ON m.eval_context_id = ec.id
        JOIN sim_configs sc   ON ec.sim_config_id  = sc.id
        WHERE m.design_point_id=?
        ORDER BY m.id
    """, (dp_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sim_configs")
def api_sim_configs():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, content_hash, created_at FROM sim_configs ORDER BY id"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/legacy-analysis/reports")
def api_legacy_analysis_reports():
    report_files = ARTIFACTS_ROOT.glob("datasets/*/reports/analysis/**/index.html")
    seen: set[str] = set()
    reports: List[Dict[str, Any]] = []
    for file_path in report_files:
        try:
            resolved = file_path.resolve()
        except FileNotFoundError:
            continue
        rel = resolved.relative_to(ARTIFACTS_ROOT.resolve())
        rel_str = rel.as_posix()
        if rel_str in seen:
            continue
        seen.add(rel_str)

        parts = rel.parts
        dataset_name = parts[1] if len(parts) > 1 else "unknown"
        scope = "汇总报告" if parts[-2] == "analysis" else parts[-2]
        stat = resolved.stat()
        reports.append({
            "id": rel_str,
            "dataset": dataset_name,
            "scope": scope,
            "relpath": rel_str,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
        })

    reports.sort(key=lambda item: item["updated_at"], reverse=True)
    return jsonify(reports)


@app.route("/legacy-analysis/<path:relpath>")
def legacy_analysis_file(relpath: str):
    root = ARTIFACTS_ROOT.resolve()
    target = (root / relpath).resolve()
    if root not in target.parents and target != root:
        return jsonify({"error": "forbidden"}), 403
    if not target.exists() or not target.is_file():
        return jsonify({"error": "not found"}), 404
    return send_from_directory(str(target.parent), target.name)


@app.route("/api/sync", methods=["POST"])
def api_sync():
    stats = sync_data()
    return jsonify(stats)


@app.route("/")
def index():
    return send_from_directory(str(APP_DIR / "static"), "index.html")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[app] DB       : {DB_PATH}")
    print(f"[app] Artifacts: {ARTIFACTS_ROOT}")
    init_db()
    stats = sync_data()
    print(f"[app] Sync     : {stats}")
    print(f"[app] Open     : http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
