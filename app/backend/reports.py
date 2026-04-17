from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .shared import ARTIFACTS_ROOT, read_typed_csv


def cross_scenario_mode_info(manifest: Dict[str, Any]) -> Dict[str, str]:
    use_summary = bool(manifest.get("execution", {}).get("use_robustness_summary"))
    if use_summary:
        return {
            "mode_key": "robustness",
            "mode_label": "Cross-Scenario Robustness",
            "mode_label_zh": "跨场景鲁棒聚合",
            "mode_short_label": "repeat-summary",
            "description": "先在每个 measured preset 内做 repeat robustness，再跨 preset 聚合。",
        }
    return {
        "mode_key": "observed",
        "mode_label": "Cross-Scenario Observed",
        "mode_label_zh": "跨场景观测聚合",
        "mode_short_label": "observed",
        "description": "直接用各 measured preset 的观测结果聚合，更适合看最优设计迁移。",
    }


def build_cross_scenario_report_payload(report_dir: Path, *, include_rows: bool = False) -> Optional[Dict[str, Any]]:
    manifest_path = report_dir / "experiment_manifest.json"
    summary_path = report_dir / "summary.csv"
    per_scenario_path = report_dir / "per_scenario.csv"
    if not manifest_path.exists() or not summary_path.exists() or not per_scenario_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if manifest.get("workflow") != "cross_scenario_robustness":
        return None

    try:
        summary_rows = read_typed_csv(summary_path)
    except Exception:
        return None
    per_scenario_rows: List[Dict[str, Any]] = []
    if include_rows:
        try:
            per_scenario_rows = read_typed_csv(per_scenario_path)
        except Exception:
            return None

    meta_path = report_dir / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except Exception:
        meta = {}

    mode = cross_scenario_mode_info(manifest)
    members = manifest.get("scenario", {}).get("members", []) or []
    scenario_names = [str(member.get("name", "")).strip() for member in members if str(member.get("name", "")).strip()]
    if not scenario_names:
        scenario_names = [
            str(item.get("scenario_name", "")).strip()
            for item in per_scenario_rows
            if str(item.get("scenario_name", "")).strip()
        ]
        scenario_names = list(dict.fromkeys(scenario_names))

    root_name = str(manifest.get("scenario", {}).get("name", "")).strip()
    if not root_name:
        root_name = Path(str(manifest.get("inputs", {}).get("scenario_root", report_dir.parent))).name

    top_candidate = summary_rows[0] if summary_rows else None
    runner_up = summary_rows[1] if len(summary_rows) > 1 else None
    full_match_candidates = sum(
        1
        for row in summary_rows
        if row.get("scenario_count") is not None and row.get("matched_scenarios") == row.get("scenario_count")
    )
    updated_at = datetime.fromtimestamp(summary_path.stat().st_mtime).isoformat()
    relpath = report_dir.resolve().relative_to(ARTIFACTS_ROOT.resolve()).as_posix()

    report = {
        "id": relpath,
        "relpath": relpath,
        "label": f"{root_name} · {mode['mode_label_zh']}",
        "root_name": root_name,
        "mode_key": mode["mode_key"],
        "mode_label": mode["mode_label"],
        "mode_label_zh": mode["mode_label_zh"],
        "mode_short_label": mode["mode_short_label"],
        "description": mode["description"],
        "updated_at": updated_at,
        "candidate_count": len(summary_rows),
        "scenario_count": len(scenario_names),
        "scenario_names": scenario_names,
        "top_candidate": top_candidate,
        "source": manifest.get("execution", {}).get("source"),
        "topk": manifest.get("execution", {}).get("topk"),
        "accuracy_target": manifest.get("execution", {}).get("accuracy_target"),
    }

    payload = {
        "report": report,
        "summary": {
            "mode_key": mode["mode_key"],
            "mode_label": mode["mode_label"],
            "mode_label_zh": mode["mode_label_zh"],
            "description": mode["description"],
            "scenario_count": len(scenario_names),
            "candidate_count": len(summary_rows),
            "full_match_candidates": full_match_candidates,
            "top_candidate": top_candidate,
            "runner_up": runner_up,
        },
        "manifest": manifest,
        "meta": meta,
    }
    if include_rows:
        payload["summary_rows"] = summary_rows
        payload["per_scenario_rows"] = per_scenario_rows
    return payload


def list_cross_scenario_reports() -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for manifest_path in ARTIFACTS_ROOT.glob("**/experiment_manifest.json"):
        report_dir = manifest_path.parent
        try:
            relpath = report_dir.resolve().relative_to(ARTIFACTS_ROOT.resolve()).as_posix()
        except Exception:
            continue
        if relpath in seen:
            continue
        payload = build_cross_scenario_report_payload(report_dir, include_rows=False)
        if not payload:
            continue
        seen.add(relpath)
        reports.append(payload["report"])

    reports.sort(key=lambda item: item["updated_at"], reverse=True)
    return reports


def list_legacy_analysis_reports() -> List[Dict[str, Any]]:
    scan_patterns = [
        "datasets/*/reports/analysis/**/index.html",
        "search_runs/*/reports/analysis/**/index.html",
        "search_runs/reports/*/**/index.html",
        "matrix_runs/*/reports/analysis/**/index.html",
    ]
    seen: set[str] = set()
    reports: List[Dict[str, Any]] = []
    for pattern in scan_patterns:
        for file_path in ARTIFACTS_ROOT.glob(pattern):
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
            group_name = parts[1] if len(parts) > 1 else "unknown"
            scope = "汇总报告" if parts[-2] == "analysis" else parts[-2]
            stat = resolved.stat()
            reports.append({
                "id": rel_str,
                "dataset": group_name,
                "scope": scope,
                "relpath": rel_str,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size,
            })

    reports.sort(key=lambda item: item["updated_at"], reverse=True)
    return reports


def resolve_artifact_path(relpath: str) -> Optional[Path]:
    root = ARTIFACTS_ROOT.resolve()
    target = (root / relpath).resolve()
    if root not in target.parents and target != root:
        return None
    return target
