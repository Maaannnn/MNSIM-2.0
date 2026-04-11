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

from dse.core import (
    DIM_NAMES,
    SPACE,
    accuracy_violation,
    evaluate_config,
    pareto_indices_with_accuracy,
    write_temp_config,
)
from dse.output import DSERecord, DSERunResult, RunConfig
from dse.progress import try_make_tqdm, update_progress


def run(cfg: RunConfig) -> DSERunResult:
    """
    Run random sampling DSE.

    Uses:
      cfg.budget: number of sampled configurations (unique)
      cfg.run_accuracy: whether to compute accuracy per evaluation (slow)
    """
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)
    accuracy_target = cfg.algo_kwargs.get("accuracy_target", None)
    if accuracy_target is not None and not cfg.run_accuracy:
        raise ValueError("accuracy_target requires --run-accuracy for random sampling.")

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
    pbar = try_make_tqdm(n_iter, tag)
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
                max_acc_batches=cfg.max_acc_batches,
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
            extra={"accuracy_violation": accuracy_violation(res.accuracy, accuracy_target)},
        )
        records.append(rec)
        postfix = {
            "lat": f"{rec.latency_ns:.2e}",
            "en": f"{rec.energy_nj:.2e}",
            "area": f"{rec.area_um2:.2e}",
        }
        if cfg.run_accuracy and rec.accuracy is not None:
            postfix["acc"] = f"{rec.accuracy:.4f}"
        update_progress(pbar, tag=tag, done=k, total=n_iter, t_start=t_start, postfix=postfix)
    if pbar is not None:
        pbar.close()

    nd_idx = pareto_indices_with_accuracy(records, accuracy_target)
    for i in nd_idx:
        records[i].is_pareto = True

    wall_time_s = time.time() - t_start
    finished_at = datetime.now(timezone.utc).isoformat()
    n_feasible = sum(
        1 for r in records
        if accuracy_target is None or (r.accuracy is not None and r.accuracy >= float(accuracy_target))
    )
    print(f"{tag} Done. evaluated={len(records)} feasible={n_feasible} pareto={len(nd_idx)} wall={wall_time_s:.1f}s")

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
