from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from .shared import ARTIFACTS_ROOT


INVALIDATION_REGISTRY_PATH = ARTIFACTS_ROOT / "invalidation_registry.json"


@lru_cache(maxsize=1)
def load_invalidation_registry() -> Dict[str, Any]:
    if not INVALIDATION_REGISTRY_PATH.exists():
        return {"schema_version": "artifact_invalidation_v1", "entries": []}
    try:
        return json.loads(INVALIDATION_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "artifact_invalidation_v1", "entries": []}


def _normalize_relpath(relpath: str) -> str:
    return str(relpath or "").strip().strip("/")


def artifact_relpath(target: str | Path) -> Optional[str]:
    path = Path(target)
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        resolved = (ARTIFACTS_ROOT / str(path)).resolve()
    try:
        return resolved.relative_to(ARTIFACTS_ROOT.resolve()).as_posix()
    except Exception:
        rel = _normalize_relpath(str(target))
        return rel or None


def find_invalidation(target: str | Path) -> Optional[Dict[str, Any]]:
    relpath = artifact_relpath(target)
    if not relpath:
        return None
    matched: Optional[Dict[str, Any]] = None
    matched_len = -1
    for entry in load_invalidation_registry().get("entries", []):
        needle = _normalize_relpath(entry.get("relpath", ""))
        if not needle:
            continue
        match_type = entry.get("match_type", "exact")
        ok = relpath == needle if match_type == "exact" else (relpath == needle or relpath.startswith(needle + "/"))
        if ok and len(needle) > matched_len:
            matched = copy.deepcopy(entry)
            matched_len = len(needle)
    if matched is None:
        return None
    matched["artifact_relpath"] = relpath
    return matched


def annotate_artifact(target: str | Path, *, status: Optional[str] = None) -> Dict[str, Any]:
    relpath = artifact_relpath(target)
    invalidation = find_invalidation(target)
    raw_status = status or ""
    effective_status = invalidation.get("status", "invalidated") if invalidation else raw_status
    return {
        "artifact_relpath": relpath,
        "raw_status": raw_status,
        "status": effective_status,
        "is_invalidated": bool(invalidation),
        "invalidation": invalidation,
    }


def annotate_run_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    annotated = annotate_artifact(item.get("trial_dir", ""), status=item.get("status"))
    item["artifact_relpath"] = annotated["artifact_relpath"]
    item["raw_status"] = annotated["raw_status"]
    item["status"] = annotated["status"]
    item["is_invalidated"] = annotated["is_invalidated"]
    item["invalidation"] = annotated["invalidation"]
    return item
