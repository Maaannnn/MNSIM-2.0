#!/usr/bin/env python3
"""
MNSIM DSE 实验记录查询服务

Usage:
    python app/server.py           # 默认 http://localhost:5001
    PORT=8080 python app/server.py
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    where, params = [], []

    for field, col in [("algo", "r.algo"), ("space", "r.space_profile"),
                       ("group", "r.run_group"), ("source", "r.source_type"),
                       ("status", "r.status")]:
        val = request.args.get(field)
        if val:
            where.append(f"{col}=?")
            params.append(val)

    q = request.args.get("q", "").strip()
    if q:
        where.append("(r.algo LIKE ? OR r.run_group LIKE ? OR r.space_profile LIKE ?)")
        params += [f"%{q}%"] * 3

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
        SELECT re.eval_index, re.phase, re.is_pareto,
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
