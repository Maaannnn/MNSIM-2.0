from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .shared import ANALYSIS_GROUP_FIELDS, safe_float


def analysis_base_rows_for_run(db: sqlite3.Connection, run_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
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


def build_run_filter_clause(args) -> Tuple[List[str], List[Any]]:
    where: List[str] = []
    params: List[Any] = []

    for field, col in [("algo", "r.algo"), ("space", "r.space_profile"),
                       ("group", "r.run_group"), ("source", "r.source_type")]:
        val = args.get(field)
        if val:
            where.append(f"{col}=?")
            params.append(val)

    q = (args.get("q") or "").strip()
    if q:
        where.append("(r.algo LIKE ? OR r.run_group LIKE ? OR r.space_profile LIKE ?)")
        params += [f"%{q}%"] * 3
    return where, params


def analysis_base_rows_for_runs(db: sqlite3.Connection, run_ids: List[int]) -> List[Dict[str, Any]]:
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


def analysis_is_feasible(row: Dict[str, Any], accuracy_target: Optional[float]) -> bool:
    if accuracy_target is None:
        return True
    acc = row.get("accuracy")
    if acc is None:
        return False
    return float(acc) >= float(accuracy_target)


def analysis_dominates(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def analysis_mark_global_pareto(rows: List[Dict[str, Any]]) -> None:
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
            if analysis_dominates(obj_j, obj_i):
                dominated = True
                break
        if not dominated:
            pareto_indices.append(i)

    pareto_index_set = set(pareto_indices)
    for idx, row in enumerate(rows):
        row["global_pareto"] = idx in pareto_index_set


def analysis_best_record(rows: List[Dict[str, Any]], metric: str, reverse: bool = False) -> Optional[Dict[str, Any]]:
    candidates = [row for row in rows if row.get(metric) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row[metric])) if reverse else min(candidates, key=lambda row: float(row[metric]))


def analysis_score_rows(rows: List[Dict[str, Any]]) -> None:
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


def analysis_top_configs(rows: List[Dict[str, Any]], topk: int = 10) -> List[Dict[str, Any]]:
    analysis_score_rows(rows)

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


def analysis_group_sections(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for field in ANALYSIS_GROUP_FIELDS:
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
            best_latency = analysis_best_record(bucket, "latency_ns")
            best_energy = analysis_best_record(bucket, "energy_nj")
            best_area = analysis_best_record(bucket, "area_um2")
            best_accuracy = analysis_best_record(bucket, "accuracy", reverse=True)
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


def build_analysis_payload(scope: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        row["feasible"] = analysis_is_feasible(row, safe_float(row.get("accuracy_target")))
    analysis_mark_global_pareto(rows)

    feasible_rows = [row for row in rows if row.get("feasible")]
    global_pareto_rows = [row for row in rows if row.get("global_pareto")]
    best_latency = analysis_best_record(rows, "latency_ns")
    best_energy = analysis_best_record(rows, "energy_nj")
    best_area = analysis_best_record(rows, "area_um2")
    best_accuracy = analysis_best_record(rows, "accuracy", reverse=True)

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
        "top_configs": analysis_top_configs(rows, topk=10),
        "group_sections": analysis_group_sections(rows),
    }


def build_run_analysis(run: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        row["run_group"] = run.get("run_group")
        row["algo"] = run.get("algo")
        row["seed"] = run.get("seed")
        row["space_profile"] = run.get("space_profile")
        row["source_type"] = run.get("source_type")
        row["accuracy_target"] = run.get("accuracy_target")

    return build_analysis_payload({
        "mode": "run",
        "run_id": run["id"],
        "run_group": run.get("run_group"),
        "algo": run.get("algo"),
        "seed": run.get("seed"),
        "space_profile": run.get("space_profile"),
        "source_type": run.get("source_type"),
        "accuracy_target": safe_float(run.get("accuracy_target")),
    }, rows)
