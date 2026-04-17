from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

from .shared import ARTIFACTS_ROOT, DB_PATH, META_COLS, load_trial_manifest, safe_float


def sync_data() -> Dict[str, int]:
    """
    Scan artifacts/dse/{search,matrix}_runs for result.json+history.csv pairs
    and import any runs not yet in the DB.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()
    imported = refreshed = skipped = errors = 0

    def md5(path: str, length: int = 32) -> str:
        p = Path(path).expanduser().resolve()
        data = p.read_bytes() if p.exists() else b""
        return hashlib.md5(data).hexdigest()[:length]

    def sha1(obj: Any, length: int = 12) -> str:
        s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(s.encode()).hexdigest()[:length]

    def ensure_sim_config(cfg_path: str) -> int:
        p = Path(cfg_path).expanduser().resolve()
        name = p.stem
        content_hash = md5(cfg_path)
        content = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        cur.execute(
            "INSERT OR IGNORE INTO sim_configs (name, content_hash, content) VALUES (?,?,?)",
            (name, content_hash, content),
        )
        return cur.execute(
            "SELECT id FROM sim_configs WHERE content_hash=?", (content_hash,)
        ).fetchone()["id"]

    def ensure_eval_context(sim_config_id: int, rc: Dict[str, Any]) -> int:
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
        ctx_hash = sha1(payload)
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

    def ensure_design_point(space_profile: str, params: Dict[str, Any]) -> int:
        norm = {k: str(v) for k, v in sorted(params.items())}
        params_hash = sha1(norm)
        params_json = json.dumps(norm, sort_keys=True)
        cur.execute(
            "INSERT OR IGNORE INTO design_points (space_profile, params_hash, params_json) VALUES (?,?,?)",
            (space_profile, params_hash, params_json),
        )
        return cur.execute(
            "SELECT id FROM design_points WHERE space_profile=? AND params_hash=?",
            (space_profile, params_hash),
        ).fetchone()["id"]

    def upsert_measurement(dp_id: int, ctx_id: int, row: Dict[str, str]) -> int:
        cur.execute("""
            INSERT OR IGNORE INTO measurements
              (design_point_id, eval_context_id, latency_ns, energy_nj,
               area_um2, power_w, accuracy, elapsed_s)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            dp_id, ctx_id,
            safe_float(row.get("latency_ns")),
            safe_float(row.get("energy_nj")),
            safe_float(row.get("area_um2")),
            safe_float(row.get("power_w")),
            safe_float(row.get("accuracy")),
            safe_float(row.get("elapsed_s")),
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

            try:
                with open(result_path, encoding="utf-8") as f:
                    res = json.load(f)
            except Exception as e:
                print(f"[sync] skip {result_path}: {e}")
                errors += 1
                continue

            rc = res.get("run_config", {})
            manifest = load_trial_manifest(trial_dir)
            if manifest:
                if not rc.get("scenario") and manifest.get("scenario"):
                    rc["scenario"] = manifest.get("scenario")
                if not rc.get("contract_version") and manifest.get("schema_version"):
                    rc["contract_version"] = manifest.get("schema_version")
            ak = rc.get("algo_kwargs", {})
            parts = set(trial_dir.parts)
            source_type = "matrix" if "matrix_runs" in parts else "search"
            run_group = trial_dir.parent.name

            existing = cur.execute(
                "SELECT id, run_config_json FROM opt_runs WHERE trial_dir=?", (str(trial_dir),)
            ).fetchone()
            if existing:
                try:
                    old_rc = json.loads(existing["run_config_json"] or "{}")
                except Exception:
                    old_rc = {}
                old_scenario = old_rc.get("scenario") or {}
                new_scenario = rc.get("scenario") or {}
                old_contract = old_rc.get("contract_version")
                new_contract = rc.get("contract_version")
                if old_contract == new_contract and old_scenario == new_scenario:
                    skipped += 1
                    continue
                cur.execute(
                    "UPDATE opt_runs SET run_config_json=?, hypervolume=?, hv_reference_point=?, wall_time_s=?, started_at=?, finished_at=? WHERE id=?",
                    (
                        json.dumps(rc),
                        res.get("hypervolume"),
                        json.dumps(res["hv_reference_point"]) if res.get("hv_reference_point") else None,
                        res.get("wall_time_s"),
                        res.get("started_at"),
                        res.get("finished_at"),
                        existing["id"],
                    ),
                )
                con.commit()
                refreshed += 1
                print(f"[sync] ~ refresh {trial_dir.name}")
                continue

            try:
                cfg_path = rc.get("base_config_path", "SimConfig.ini")
                sim_config_id = ensure_sim_config(cfg_path)
                ctx_id = ensure_eval_context(sim_config_id, rc)
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

                with open(history_csv, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        params = {k: v for k, v in row.items() if k not in META_COLS and v not in ("", None)}
                        dp_id = ensure_design_point(space_profile, params)
                        meas_id = upsert_measurement(dp_id, ctx_id, row)
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
    return {"imported": imported, "refreshed": refreshed, "skipped": skipped, "errors": errors}
