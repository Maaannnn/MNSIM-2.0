#!/usr/bin/env python3
"""
MNSIM DSE 实验记录查询服务

Usage:
    python app/server.py           # 默认 http://localhost:5001
    PORT=8080 python app/server.py
    cd app && python server.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, List

from flask import Flask, g, jsonify, request, send_from_directory

# Allow both:
# 1) `python app/server.py` from repo root
# 2) `cd app && python server.py`
BOOTSTRAP_APP_DIR = Path(__file__).resolve().parent
BOOTSTRAP_REPO_ROOT = BOOTSTRAP_APP_DIR.parent
if str(BOOTSTRAP_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_REPO_ROOT))

from app.backend.analysis import (
    analysis_base_rows_for_run,
    analysis_base_rows_for_runs,
    build_analysis_payload,
    build_run_analysis,
    build_run_filter_clause,
)
from app.backend.reports import (
    build_cross_scenario_report_payload,
    list_cross_scenario_reports,
    list_legacy_analysis_reports,
    resolve_artifact_path,
)
from app.backend.shared import (
    APP_DIR,
    ARTIFACTS_ROOT,
    DB_PATH,
    PORT,
    REPO_ROOT,
    TABLE_BROWSER_TABLES,
    derive_effective_config,
    load_trial_manifest,
    table_columns,
)
from app.backend.sync import sync_data

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
    where, params = build_run_filter_clause(request.args)

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
    payload = []
    for row in rows:
        item = dict(row)
        try:
            rc = json.loads(item.get("run_config_json") or "{}")
        except Exception:
            rc = {}
        scenario = rc.get("scenario") or {}
        item["contract_version"] = rc.get("contract_version")
        item["scenario_name"] = scenario.get("name") or ""
        item["scenario_kind"] = scenario.get("kind") or ""
        payload.append(item)
    return jsonify(payload)


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
    d["experiment_manifest"] = load_trial_manifest(Path(d["trial_dir"]))
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
    effective = derive_effective_config(data.pop("base_config_content") or "", params)

    return jsonify({
        **data,
        "params": params,
        "effective_config": effective,
    })


@app.route("/api/runs/<int:run_id>/analysis")
def api_run_analysis(run_id: int):
    db = get_db()
    try:
        run, rows = analysis_base_rows_for_run(db, run_id)
    except KeyError:
        return jsonify({"error": "not found"}), 404
    return jsonify(build_run_analysis(run, rows))


@app.route("/api/analysis/global")
def api_global_analysis():
    db = get_db()
    where, params = build_run_filter_clause(request.args)
    sql = "SELECT r.id, r.run_group, r.algo, r.seed, r.space_profile, r.source_type, r.status FROM opt_runs r"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.started_at DESC, r.id DESC"
    run_rows = db.execute(sql, params).fetchall()
    run_dicts = [dict(row) for row in run_rows]
    run_ids = [int(row["id"]) for row in run_rows]
    rows = analysis_base_rows_for_runs(db, run_ids)
    payload = build_analysis_payload({
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
    for table_name in TABLE_BROWSER_TABLES:
        columns = table_columns(db, table_name)
        count = db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        result.append({
            "name": table_name,
            "count": count,
            "columns": columns,
        })
    return jsonify(result)


@app.route("/api/db/tables/<table_name>")
def api_db_table_rows(table_name: str):
    if table_name not in TABLE_BROWSER_TABLES:
        return jsonify({"error": "table not found"}), 404

    db = get_db()
    columns = table_columns(db, table_name)
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

    # Auto-parse JSON string columns for readability
    _json_cols = {"params_json", "run_config_json", "hv_reference_point"}
    parsed_rows = []
    for r in rows:
        row_dict = dict(r)
        for col in _json_cols:
            if col in row_dict and isinstance(row_dict[col], str):
                try:
                    row_dict[col] = json.loads(row_dict[col])
                except Exception:
                    pass
        parsed_rows.append(row_dict)

    return jsonify({
        "table": table_name,
        "columns": columns,
        "rows": parsed_rows,
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


@app.route("/api/cross-scenario/reports")
def api_cross_scenario_reports():
    return jsonify(list_cross_scenario_reports())


@app.route("/api/cross-scenario/reports/<path:relpath>")
def api_cross_scenario_report(relpath: str):
    target = resolve_artifact_path(relpath)
    if target is None:
        return jsonify({"error": "forbidden"}), 403
    payload = build_cross_scenario_report_payload(target, include_rows=True)
    if not payload:
        return jsonify({"error": "not found"}), 404
    return jsonify(payload)


@app.route("/api/legacy-analysis/reports")
def api_legacy_analysis_reports():
    return jsonify(list_legacy_analysis_reports())


@app.route("/legacy-analysis/<path:relpath>")
def legacy_analysis_file(relpath: str):
    target = resolve_artifact_path(relpath)
    if target is None:
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
