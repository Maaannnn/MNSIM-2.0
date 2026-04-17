#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSEDbWriter — real-time evaluation writer for the shared SQLite DSE database.

Each algorithm trial (running in a subprocess) creates one DSEDbWriter.
Every completed evaluation is written immediately — partial runs are preserved.

Deduplication rules
───────────────────
  sim_configs      UNIQUE(content_hash)
                   → same file content always maps to the same row, even if
                     the file is renamed (accidental copies are merged).

  eval_contexts    UNIQUE(context_hash)
                   → unique combination of sim_config + nn + dataset + all
                     non-ideal flags.  Different algos / seeds with identical
                     settings share the same context row.

  design_points    UNIQUE(space_profile, params_hash)
                   → same hardware params in the same space = same row,
                     regardless of which algo or run found it.

  measurements     UNIQUE(design_point_id, eval_context_id)
                   → deterministic evaluation: same design point + same
                     context always produces the same physical metrics.
                     If nsga2 and mobo both evaluate point X with the same
                     SimConfig/nn/flags, they share one measurement row.
                     INSERT OR IGNORE silently deduplicates.

  opt_runs         UNIQUE(trial_dir)
                   → one row per (algo, seed, output directory) trial.

  run_evaluations  UNIQUE(run_id, eval_index)
                   → each step in a trial is written once; re-runs of the
                     same step (crash recovery) are silently ignored.

Usage
─────
  from dse.db_writer import DSEDbWriter
  writer = DSEDbWriter(db_path, cfg, trial_dir)
  writer.record_eval(res, eval_index=1, phase="init")
  writer.update_pareto([1, 3, 7])
  writer.finalize(hypervolume=hv, hv_ref=ref, wall_time_s=t, finished_at=ts)
  writer.close()
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from dse.core import EvalResult
    from dse.output import RunConfig

_DB_TIMEOUT = 30  # seconds SQLite waits on a locked file


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sim_configs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    content_hash TEXT    NOT NULL UNIQUE,
    content      TEXT,
    created_at   TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eval_contexts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    context_hash     TEXT    NOT NULL UNIQUE,
    sim_config_id    INTEGER REFERENCES sim_configs(id),
    nn               TEXT,
    dataset_module   TEXT,
    weights_path     TEXT,
    run_accuracy     INTEGER DEFAULT 0,
    enable_saf       INTEGER DEFAULT 0,
    enable_variation INTEGER DEFAULT 0,
    enable_rratio    INTEGER DEFAULT 0,
    fixed_qrange     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS design_points (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    space_profile TEXT NOT NULL,
    params_hash   TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    UNIQUE(space_profile, params_hash)
);

CREATE TABLE IF NOT EXISTS measurements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    design_point_id  INTEGER REFERENCES design_points(id),
    eval_context_id  INTEGER REFERENCES eval_contexts(id),
    latency_ns       REAL,
    energy_nj        REAL,
    area_um2         REAL,
    power_w          REAL,
    accuracy         REAL,
    elapsed_s        REAL,
    measured_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(design_point_id, eval_context_id)
);

CREATE TABLE IF NOT EXISTS opt_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_dir           TEXT    UNIQUE,
    run_group           TEXT,
    source_type         TEXT,
    algo                TEXT,
    seed                INTEGER,
    space_profile       TEXT,
    eval_context_id     INTEGER REFERENCES eval_contexts(id),
    accuracy_target     REAL,
    budget              INTEGER,
    status              TEXT    DEFAULT 'running',
    total_evaluated     INTEGER DEFAULT 0,
    pareto_size         INTEGER DEFAULT 0,
    hypervolume         REAL,
    hv_reference_point  TEXT,
    wall_time_s         REAL,
    started_at          TEXT,
    finished_at         TEXT,
    run_config_json     TEXT,
    imported_at         TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_evaluations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER REFERENCES opt_runs(id) ON DELETE CASCADE,
    measurement_id INTEGER REFERENCES measurements(id),
    eval_index     INTEGER,
    phase          TEXT,
    is_pareto      INTEGER DEFAULT 0,
    UNIQUE(run_id, eval_index)
);

CREATE INDEX IF NOT EXISTS idx_design_points_space ON design_points(space_profile);
CREATE INDEX IF NOT EXISTS idx_measurements_dp     ON measurements(design_point_id);
CREATE INDEX IF NOT EXISTS idx_measurements_ctx    ON measurements(eval_context_id);
CREATE INDEX IF NOT EXISTS idx_run_evals_run       ON run_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_run_evals_meas      ON run_evaluations(measurement_id);
CREATE INDEX IF NOT EXISTS idx_opt_runs_algo       ON opt_runs(algo);
CREATE INDEX IF NOT EXISTS idx_opt_runs_group      ON opt_runs(run_group);
CREATE INDEX IF NOT EXISTS idx_opt_runs_space      ON opt_runs(space_profile);
"""


def init_db(db_path: str) -> None:
    """Create all tables and indexes (idempotent)."""
    con = sqlite3.connect(db_path, timeout=_DB_TIMEOUT)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()


# ── Writer class ──────────────────────────────────────────────────────────────

class DSEDbWriter:
    """
    Per-process writer that appends evaluation results to the shared DB.

    Caches entity IDs after first lookup so subsequent writes are fast.
    """

    def __init__(self, db_path: str, cfg: "RunConfig", trial_dir: str) -> None:
        self._db_path = db_path
        self._cfg = cfg
        self._trial_dir = str(trial_dir)
        self._run_id: Optional[int] = None
        self._sim_config_id: Optional[int] = None
        self._eval_context_id: Optional[int] = None
        self._con: Optional[sqlite3.Connection] = None

    # ── Connection ────────────────────────────────────────────────────────────

    def _db(self) -> sqlite3.Connection:
        if self._con is None:
            con = sqlite3.connect(self._db_path, timeout=_DB_TIMEOUT)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> "DSEDbWriter":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Hash helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _sha1(obj: Any, length: int = 12) -> str:
        s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(s.encode()).hexdigest()[:length]

    @staticmethod
    def _md5_file(path: str, length: int = 32) -> str:
        p = Path(path).expanduser().resolve()
        data = p.read_bytes() if p.exists() else b""
        return hashlib.md5(data).hexdigest()[:length]

    # ── Entity upserts (idempotent, cached) ───────────────────────────────────

    def _ensure_sim_config(self) -> int:
        if self._sim_config_id is not None:
            return self._sim_config_id
        cfg_path = self._cfg.base_config_path
        p = Path(cfg_path).expanduser().resolve()
        name = p.stem
        content_hash = self._md5_file(cfg_path)
        content = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        db = self._db()
        with db:
            db.execute(
                "INSERT OR IGNORE INTO sim_configs (name, content_hash, content) VALUES (?,?,?)",
                (name, content_hash, content),
            )
            row = db.execute(
                "SELECT id FROM sim_configs WHERE content_hash=?", (content_hash,)
            ).fetchone()
        self._sim_config_id = int(row["id"])
        return self._sim_config_id

    def _ensure_eval_context(self) -> int:
        if self._eval_context_id is not None:
            return self._eval_context_id
        sim_config_id = self._ensure_sim_config()
        cfg = self._cfg
        payload = {
            "sim_config_id": sim_config_id,
            "nn": cfg.nn,
            "dataset_module": cfg.dataset_module,
            "weights_path": str(cfg.weights_path),
            "run_accuracy": int(bool(cfg.run_accuracy)),
            "enable_saf": int(bool(cfg.enable_saf)),
            "enable_variation": int(bool(cfg.enable_variation)),
            "enable_rratio": int(bool(cfg.enable_rratio)),
            "fixed_qrange": int(bool(cfg.fixed_qrange)),
        }
        context_hash = self._sha1(payload)
        db = self._db()
        with db:
            db.execute("""
                INSERT OR IGNORE INTO eval_contexts
                  (context_hash, sim_config_id, nn, dataset_module, weights_path,
                   run_accuracy, enable_saf, enable_variation, enable_rratio, fixed_qrange)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                context_hash, sim_config_id,
                cfg.nn, cfg.dataset_module, str(cfg.weights_path),
                int(bool(cfg.run_accuracy)), int(bool(cfg.enable_saf)),
                int(bool(cfg.enable_variation)), int(bool(cfg.enable_rratio)),
                int(bool(cfg.fixed_qrange)),
            ))
            row = db.execute(
                "SELECT id FROM eval_contexts WHERE context_hash=?", (context_hash,)
            ).fetchone()
        self._eval_context_id = int(row["id"])
        return self._eval_context_id

    def _ensure_design_point(self, params: Dict[str, Any]) -> int:
        norm = {k: str(v) for k, v in sorted(params.items())}
        params_hash = self._sha1(norm)
        params_json = json.dumps(norm, sort_keys=True)
        db = self._db()
        with db:
            db.execute(
                "INSERT OR IGNORE INTO design_points (space_profile, params_hash, params_json) VALUES (?,?,?)",
                (self._cfg.space_profile, params_hash, params_json),
            )
            row = db.execute(
                "SELECT id FROM design_points WHERE space_profile=? AND params_hash=?",
                (self._cfg.space_profile, params_hash),
            ).fetchone()
        return int(row["id"])

    def _upsert_measurement(self, design_point_id: int, eval_context_id: int,
                             res: "EvalResult") -> int:
        db = self._db()
        with db:
            db.execute("""
                INSERT OR IGNORE INTO measurements
                  (design_point_id, eval_context_id, latency_ns, energy_nj,
                   area_um2, power_w, accuracy, elapsed_s)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                design_point_id, eval_context_id,
                res.latency_ns, res.energy_nj, res.area_um2, res.power_w,
                res.accuracy, res.elapsed_s,
            ))
            row = db.execute(
                "SELECT id FROM measurements WHERE design_point_id=? AND eval_context_id=?",
                (design_point_id, eval_context_id),
            ).fetchone()
        return int(row["id"])

    def _ensure_opt_run(self) -> int:
        if self._run_id is not None:
            return self._run_id
        eval_context_id = self._ensure_eval_context()
        cfg = self._cfg
        trial_path = Path(self._trial_dir)
        # Infer source_type from path
        parts = set(trial_path.parts)
        source_type = "matrix" if "matrix_runs" in parts else "search"
        run_group = trial_path.parent.name
        accuracy_target = cfg.algo_kwargs.get("accuracy_target") if cfg.algo_kwargs else None
        run_config_json = json.dumps({
            "contract_version": cfg.contract_version,
            "nn": cfg.nn,
            "weights_path": str(cfg.weights_path),
            "base_config_path": str(cfg.base_config_path),
            "run_accuracy": cfg.run_accuracy,
            "enable_saf": cfg.enable_saf,
            "enable_variation": cfg.enable_variation,
            "enable_rratio": cfg.enable_rratio,
            "fixed_qrange": cfg.fixed_qrange,
            "space_profile": cfg.space_profile,
            "algo_kwargs": cfg.algo_kwargs,
            "device": cfg.device,
            "dataset_module": cfg.dataset_module,
            "max_acc_batches": cfg.max_acc_batches,
            "scenario": cfg.scenario,
        })
        db = self._db()
        with db:
            db.execute("""
                INSERT OR IGNORE INTO opt_runs
                  (trial_dir, run_group, source_type, algo, seed, space_profile,
                   eval_context_id, accuracy_target, budget, status,
                   started_at, run_config_json)
                VALUES (?,?,?,?,?,?,?,?,?,'running',?,?)
            """, (
                self._trial_dir, run_group, source_type,
                cfg.algo, cfg.seed, cfg.space_profile,
                eval_context_id, accuracy_target, cfg.budget,
                datetime.now(timezone.utc).isoformat(),
                run_config_json,
            ))
            row = db.execute(
                "SELECT id FROM opt_runs WHERE trial_dir=?", (self._trial_dir,)
            ).fetchone()
        self._run_id = int(row["id"])
        return self._run_id

    # ── Public API ────────────────────────────────────────────────────────────

    def record_eval(self, res: "EvalResult", eval_index: int, phase: str) -> None:
        """
        Write one completed evaluation to the DB immediately.

        Safe to call from within a subprocess. If the exact (run_id, eval_index)
        already exists (crash recovery / duplicate call), the insert is silently
        ignored and no data is corrupted.
        """
        run_id = self._ensure_opt_run()
        eval_context_id = self._ensure_eval_context()
        design_point_id = self._ensure_design_point(res.config)
        measurement_id = self._upsert_measurement(design_point_id, eval_context_id, res)
        db = self._db()
        with db:
            db.execute("""
                INSERT OR IGNORE INTO run_evaluations
                  (run_id, measurement_id, eval_index, phase, is_pareto)
                VALUES (?,?,?,?,0)
            """, (run_id, measurement_id, eval_index, phase))
            # Increment counter (only if the row was actually new)
            # Use total rows as the authoritative count to stay consistent
            count = db.execute(
                "SELECT COUNT(*) FROM run_evaluations WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            db.execute(
                "UPDATE opt_runs SET total_evaluated=? WHERE id=?", (count, run_id)
            )

    def update_pareto(self, pareto_eval_indices: List[int]) -> None:
        """
        Reset and re-mark pareto flags after final pareto computation.
        Safe to call at end of run with the definitive pareto set.
        """
        if self._run_id is None:
            return
        db = self._db()
        with db:
            db.execute("UPDATE run_evaluations SET is_pareto=0 WHERE run_id=?", (self._run_id,))
            if pareto_eval_indices:
                ph = ",".join("?" * len(pareto_eval_indices))
                db.execute(
                    f"UPDATE run_evaluations SET is_pareto=1 WHERE run_id=? AND eval_index IN ({ph})",
                    [self._run_id] + list(pareto_eval_indices),
                )
            db.execute(
                "UPDATE opt_runs SET pareto_size=? WHERE id=?",
                (len(pareto_eval_indices), self._run_id),
            )

    def finalize(
        self,
        hypervolume: Optional[float],
        hv_ref: Optional[Tuple[float, float, float]],
        wall_time_s: float,
        finished_at: str,
    ) -> None:
        """Mark the run completed and persist final metrics."""
        if self._run_id is None:
            return
        db = self._db()
        with db:
            db.execute("""
                UPDATE opt_runs
                SET status='completed', hypervolume=?, hv_reference_point=?,
                    wall_time_s=?, finished_at=?
                WHERE id=?
            """, (
                hypervolume,
                json.dumps(list(hv_ref)) if hv_ref else None,
                wall_time_s,
                finished_at,
                self._run_id,
            ))
