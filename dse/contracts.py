#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared experiment contract utilities for DSE workflows.

This module centralises:
  - resource resolution (weights/config fallbacks)
  - scenario description and config patch materialisation
  - experiment manifest writing

The goal is to keep nominal DSE, measured-matrix runs, and robustness replays
on one extensible I/O contract instead of each script inventing its own schema.
"""
from __future__ import annotations

import configparser as cp
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


EXPERIMENT_SCHEMA_VERSION = "ws5a_v1"
REPO_ROOT = Path(__file__).resolve().parent.parent


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path | str, payload: Dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def read_json(path: Path | str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_resource(path_like: str, kind: str, *, repo_root: Path = REPO_ROOT) -> str:
    """
    Return an existing absolute path for weights/config when possible.

    Search order:
      1) as-given (absolute or cwd-relative)
      2) <repo>/weights/<name>   (for kind == 'weights')
      3) <repo>/configs/<name>   (for kind == 'config')
      4) <repo>/<name>           (legacy root fallback)
      5) original expanded path  (when no fallback exists)
    """
    p = Path(os.path.expanduser(str(path_like)))
    if p.exists():
        return str(p.resolve())

    name = Path(str(path_like)).name
    candidates: list[Path] = []
    if kind == "weights":
        candidates.extend([repo_root / "weights" / name, repo_root / name])
    elif kind == "config":
        candidates.extend([repo_root / "configs" / name, repo_root / name])
    else:
        candidates.append(repo_root / name)

    for cand in candidates:
        if cand.exists():
            return str(cand.resolve())
    return str(p)


def make_nominal_scenario(base_config_path: str, *, name: str = "nominal") -> Dict[str, Any]:
    return {
        "kind": "nominal",
        "name": name,
        "base_config_path": str(Path(base_config_path).expanduser().resolve()),
        "config_patch": {},
    }


def make_measured_scenario(row: Dict[str, str], *, measured_presets_csv: str) -> Dict[str, Any]:
    patch: Dict[str, Dict[str, str]] = {}
    dev_patch: Dict[str, str] = {}

    def _take(key: str, target_key: str) -> None:
        value = str(row.get(key, "")).strip()
        if value:
            dev_patch[target_key] = value

    _take("device_resistance", "Device_Resistance")
    _take("device_variation", "Device_Variation")
    saf = str(row.get("device_saf_heuristic", "")).strip()
    if saf:
        dev_patch["Device_SAF"] = f"{saf},{saf}"
    if dev_patch:
        patch["Device level"] = dev_patch

    measured_fields = {
        k: v
        for k, v in row.items()
        if str(v).strip()
    }
    return {
        "kind": "measured_preset",
        "name": str(row.get("preset_name", "measured")).strip() or "measured",
        "source": {
            "measured_presets_csv": str(Path(measured_presets_csv).expanduser().resolve()),
        },
        "config_patch": patch,
        "measured_fields": measured_fields,
    }


def write_patched_config(base_config_path: Path | str, config_patch: Dict[str, Dict[str, str]], output_path: Path | str) -> None:
    parser = cp.ConfigParser()
    parser.read(base_config_path, encoding="UTF-8")
    for section, kvs in config_patch.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in kvs.items():
            parser.set(section, key, str(value))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        parser.write(f)


def build_experiment_manifest(
    *,
    workflow: str,
    entrypoint: str,
    inputs: Dict[str, Any],
    execution: Dict[str, Any],
    outputs: Optional[Dict[str, Any]] = None,
    scenario: Optional[Dict[str, Any]] = None,
    notes: Optional[Iterable[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "created_at": now_utc_iso(),
        "repo_root": str(REPO_ROOT),
        "workflow": workflow,
        "entrypoint": entrypoint,
        "inputs": inputs,
        "execution": execution,
        "scenario": scenario or {},
        "outputs": outputs or {},
        "notes": list(notes or []),
        "extra": extra or {},
    }
