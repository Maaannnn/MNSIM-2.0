#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Random sampling baseline (data collection).

Track: "multi" (produces Pareto set over (latency, energy, area))

This algorithm does NOT do any optimisation. It simply samples `budget`
unique configurations uniformly at random from the full discrete design space,
evaluates them with MNSIM, and writes the same unified outputs as other algos.
"""
from __future__ import annotations

import itertools
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

from dse.core import DIM_NAMES, SPACE, evaluate_config, write_temp_config
from dse.metrics import pareto_indices
from dse.output import DSERecord, DSERunResult, RunConfig


def _fmt_s(sec: float) -> str:
    sec = max(0.0, float(sec))
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _try_make_tqdm(total: int, desc: str):
    """Create a tqdm progress bar if available; otherwise return None."""
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm(
            total=total,
            desc=desc,
            dynamic_ncols=True,
            leave=True,
            unit="it",
            smoothing=0.1,
        )
    except Exception:
        return None


def run(cfg: RunConfig) -> DSERunResult:
    """
    Run random sampling DSE.

    Uses:
      cfg.budget: number of sampled configurations (unique)
      cfg.run_accuracy: whether to compute accuracy per evaluation (slow)
    """
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    dim_names = DIM_NAMES
    dim_values = [SPACE[d]["values"] for d in dim_names]
    candidates = [dict(zip(dim_names, combo)) for combo in itertools.product(*dim_values)]
    n_total = len(candidates)
    n_iter = min(cfg.budget, n_total)

    tag = f"[random|s{cfg.seed}]"
    print(f"{tag} space={n_total} budget={n_iter}")

    idxs = list(range(n_total))
    random.shuffle(idxs)
    chosen = idxs[:n_iter]

    records: List[DSERecord] = []
    pbar = _try_make_tqdm(n_iter, tag)
    for k, idx in enumerate(chosen, start=1):
        cfg_vals = candidates[idx]
        temp_path = write_temp_config(cfg.base_config_path, cfg_vals)
        try:
            res = evaluate_config(
                sim_config_path=temp_path,
                nn_name=cfg.nn,
                weights_path=cfg.weights_path,
                config_values=cfg_vals,
                run_accuracy=cfg.run_accuracy,
                enable_saf=cfg.enable_saf,
                enable_variation=cfg.enable_variation,
                enable_rratio=cfg.enable_rratio,
                fixed_qrange=cfg.fixed_qrange,
                device=cfg.device,
                dataset_module=cfg.dataset_module,
            )
        finally:
            os.remove(temp_path)

        rec = DSERecord(
            algo="random",
            seed=cfg.seed,
            eval_index=len(records) + 1,
            phase="random",
            latency_ns=res.latency_ns,
            energy_nj=res.energy_nj,
            area_um2=res.area_um2,
            power_w=res.power_w,
            accuracy=res.accuracy,
            elapsed_s=res.elapsed_s,
            config=res.config,
        )
        records.append(rec)
        if pbar is not None:
            postfix = {
                "lat": f"{rec.latency_ns:.2e}",
                "en": f"{rec.energy_nj:.2e}",
                "area": f"{rec.area_um2:.2e}",
            }
            if cfg.run_accuracy and rec.accuracy is not None:
                postfix["acc"] = f"{rec.accuracy:.4f}"
            pbar.set_postfix(postfix, refresh=False)
            pbar.update(1)
        elif k == 1 or k == n_iter or (k % 5 == 0):
            elapsed = time.time() - t_start
            avg = elapsed / max(1, k)
            remain = max(0, n_iter - k)
            eta = remain * avg
            pct = 100.0 * k / max(1, n_iter)
            speed = 1.0 / avg if avg > 0 else 0.0
            if cfg.run_accuracy and rec.accuracy is not None:
                print(
                    f"{tag} [{k:>3}/{n_iter}] {pct:6.2f}% | {speed:5.2f} it/s | "
                    f"elapsed={_fmt_s(elapsed)} eta={_fmt_s(eta)} | "
                    f"lat={rec.latency_ns:.3e} en={rec.energy_nj:.3e} area={rec.area_um2:.3e} acc={rec.accuracy:.4f}"
                )
            else:
                print(
                    f"{tag} [{k:>3}/{n_iter}] {pct:6.2f}% | {speed:5.2f} it/s | "
                    f"elapsed={_fmt_s(elapsed)} eta={_fmt_s(eta)} | "
                    f"lat={rec.latency_ns:.3e} en={rec.energy_nj:.3e} area={rec.area_um2:.3e}"
                )
    if pbar is not None:
        pbar.close()

    vecs = [r.obj_vector() for r in records]
    nd_idx = pareto_indices(vecs)
    for i in nd_idx:
        records[i].is_pareto = True

    wall_time_s = time.time() - t_start
    finished_at = datetime.now(timezone.utc).isoformat()
    print(f"{tag} Done. evaluated={len(records)} pareto={len(nd_idx)} wall={wall_time_s:.1f}s")

    return DSERunResult(
        run_config=cfg,
        records=records,
        pareto_record_indices=nd_idx,
        hypervolume=None,
        hv_reference_point=None,
        wall_time_s=wall_time_s,
        started_at=started_at,
        finished_at=finished_at,
    )

