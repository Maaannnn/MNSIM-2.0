#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bayesian Optimization + Gaussian Process surrogate (single-objective).

Track: "single"
Optimizes a weighted log-scalarization of (latency, energy, area).
Supports optional two-stage mode: hardware-only BO first, then accuracy
re-evaluation of top-K candidates.

The scalarized objective is stored in DSERecord.extra["scalarized_obj"].
The Pareto front is still extracted from all evaluations for cross-track analysis.
"""
from __future__ import annotations

import itertools
import math
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

from dse.core import (
    DIM_NAMES,
    SPACE,
    accuracy_violation,
    evaluate_config,
    pareto_indices_with_accuracy,
    write_temp_config,
)
from dse.metrics import pareto_indices, scalarize_log
from dse.output import DSERecord, DSERunResult, RunConfig
from dse.progress import try_make_tqdm, update_progress


def _expected_improvement(
    gp: GaussianProcessRegressor,
    X_candidates: np.ndarray,
    y_best: float,
    xi: float = 0.01,
) -> np.ndarray:
    mu, sigma = gp.predict(X_candidates, return_std=True)
    sigma = np.maximum(sigma, 1e-12)
    imp = y_best - mu - xi
    z = imp / sigma
    return imp * norm.cdf(z) + sigma * norm.pdf(z)


def _build_gp(n_dims: int, seed: int) -> GaussianProcessRegressor:
    kernel = (
        ConstantKernel(1.0, (1e-3, 1e3))
        * Matern(length_scale=np.ones(n_dims), nu=2.5)
        + WhiteKernel(noise_level=1e-6, noise_level_bounds=(1e-9, 1e-1))
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        random_state=seed,
        n_restarts_optimizer=3,
    )


def run(cfg: RunConfig) -> DSERunResult:
    """
    Run BO+GP single-objective DSE.

    algo_kwargs recognised:
      w_latency (float, default 1.0)  — weight for log-latency
      w_energy  (float, default 1.0)  — weight for log-energy
      w_area    (float, default 0.2)  — weight for log-area
      two_stage (bool, default False) — hardware-only BO + top-K accuracy rerank
      topk_accuracy (int, default 3)  — number of candidates for stage-2 rerank
      accuracy_target (float|None)    — accuracy constraint threshold
      accuracy_penalty (float, default 100.0) — penalty coefficient
    """
    kw = cfg.algo_kwargs
    weights: Tuple[float, float, float] = (
        float(kw.get("w_latency", 1.0)),
        float(kw.get("w_energy", 1.0)),
        float(kw.get("w_area", 0.2)),
    )
    two_stage: bool = bool(kw.get("two_stage", False))
    topk_accuracy: int = int(kw.get("topk_accuracy", 3))
    accuracy_target: Optional[float] = kw.get("accuracy_target", None)
    accuracy_penalty: float = float(kw.get("accuracy_penalty", 100.0))

    if two_stage and not cfg.run_accuracy:
        raise ValueError("two_stage requires run_accuracy=True")

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    # Build full candidate index matrix
    dim_names = DIM_NAMES
    dim_values = [SPACE[d]["values"] for d in dim_names]
    candidates = [dict(zip(dim_names, combo)) for combo in itertools.product(*dim_values)]
    X_all = np.array(
        [[SPACE[d]["values"].index(c[d]) for d in dim_names] for c in candidates],
        dtype=float,
    )
    n_total = len(candidates)
    n_iter = min(cfg.budget, n_total)
    n_init = min(cfg.init_evals, n_iter)

    # Stage-1 accuracy: disabled if two_stage (accuracy done in stage-2)
    stage1_accuracy = cfg.run_accuracy and (not two_stage)

    tag = f"[bo_gp|s{cfg.seed}]"
    print(f"{tag} space={n_total} budget={n_iter} init={n_init} two_stage={two_stage}")
    total_steps = n_iter + (max(1, min(topk_accuracy, n_iter)) if two_stage else 0)
    pbar = try_make_tqdm(total_steps, tag)

    chosen: List[int] = []
    records: List[DSERecord] = []

    def _evaluate_and_record(idx: int, phase: str) -> DSERecord:
        cfg_vals = candidates[idx]
        temp_path = write_temp_config(cfg.base_config_path, cfg_vals)
        try:
            res = evaluate_config(
                sim_config_path=temp_path,
                nn_name=cfg.nn,
                weights_path=cfg.weights_path,
                config_values=cfg_vals,
                run_accuracy=stage1_accuracy,
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

        obj_vec = res.obj_vector()
        scal = scalarize_log(obj_vec, weights)

        # Add accuracy penalty for constrained optimisation
        if accuracy_target is not None and res.accuracy is not None and res.accuracy < accuracy_target:
            scal += accuracy_penalty * (accuracy_target - res.accuracy)

        eval_idx = len(records) + 1
        rec = DSERecord(
            algo="bo_gp",
            seed=cfg.seed,
            eval_index=eval_idx,
            phase=phase,
            latency_ns=res.latency_ns,
            energy_nj=res.energy_nj,
            area_um2=res.area_um2,
            power_w=res.power_w,
            accuracy=res.accuracy,
            elapsed_s=res.elapsed_s,
            config=res.config,
            extra={
                "scalarized_obj": scal,
                "weights": list(weights),
                "accuracy_violation": accuracy_violation(res.accuracy, accuracy_target),
            },
        )
        return rec

    # --- Random initialisation ---
    init_pool = list(range(n_total))
    random.shuffle(init_pool)
    for idx in init_pool[:n_init]:
        rec = _evaluate_and_record(idx, phase="init")
        chosen.append(idx)
        records.append(rec)
        best_now = min(r.extra["scalarized_obj"] for r in records)
        postfix = {
            "phase": "init",
            "obj": f"{rec.extra['scalarized_obj']:.4f}",
            "best": f"{best_now:.4f}",
        }
        if rec.accuracy is not None:
            postfix["acc"] = f"{rec.accuracy:.4f}"
        update_progress(pbar, tag=tag, done=len(records), total=total_steps, t_start=t_start, postfix=postfix)

    # --- GP-guided acquisition ---
    gp = _build_gp(n_dims=len(dim_names), seed=cfg.seed)
    chosen_set = set(chosen)

    while len(chosen) < n_iter:
        X_obs = X_all[chosen]
        y_obs = np.array([r.extra["scalarized_obj"] for r in records], dtype=float)
        gp.fit(X_obs, y_obs)

        remain = [i for i in range(n_total) if i not in chosen_set]
        ei = _expected_improvement(gp, X_all[remain], y_best=float(np.min(y_obs)))
        next_idx = remain[int(np.argmax(ei))]

        rec = _evaluate_and_record(next_idx, phase="bo")
        chosen.append(next_idx)
        chosen_set.add(next_idx)
        records.append(rec)

        best_now = min(r.extra["scalarized_obj"] for r in records)
        postfix = {
            "phase": "bo",
            "obj": f"{rec.extra['scalarized_obj']:.4f}",
            "best": f"{best_now:.4f}",
            "lat": f"{rec.latency_ns:.2e}",
        }
        if rec.accuracy is not None:
            postfix["acc"] = f"{rec.accuracy:.4f}"
        update_progress(pbar, tag=tag, done=len(records), total=total_steps, t_start=t_start, postfix=postfix)

    # --- Stage-2: accuracy rerank ---
    if two_stage:
        k = max(1, min(topk_accuracy, len(records)))
        topk = sorted(records, key=lambda r: r.extra["scalarized_obj"])[:k]
        print(f"\n{tag} === Stage-2 accuracy rerank on top-{k} ===")
        for rank, base_rec in enumerate(topk, start=1):
            temp_path = write_temp_config(cfg.base_config_path, base_rec.config)
            try:
                res2 = evaluate_config(
                    sim_config_path=temp_path,
                    nn_name=cfg.nn,
                    weights_path=cfg.weights_path,
                    config_values=base_rec.config,
                    run_accuracy=True,
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

            # Compute final objective with accuracy penalty
            obj_vec = res2.obj_vector()
            final_scal = scalarize_log(obj_vec, weights)
            acc_penalty = 0.0
            if accuracy_target is not None and res2.accuracy is not None and res2.accuracy < accuracy_target:
                acc_penalty = accuracy_penalty * (accuracy_target - res2.accuracy)
            final_scal += acc_penalty

            stage2_rec = DSERecord(
                algo="bo_gp",
                seed=cfg.seed,
                eval_index=len(records) + 1,
                phase="stage2",
                latency_ns=res2.latency_ns,
                energy_nj=res2.energy_nj,
                area_um2=res2.area_um2,
                power_w=res2.power_w,
                accuracy=res2.accuracy,
                elapsed_s=res2.elapsed_s,
                config=base_rec.config,
                extra={
                    "scalarized_obj": final_scal,
                    "stage1_obj": base_rec.extra["scalarized_obj"],
                    "acc_penalty": acc_penalty,
                    "weights": list(weights),
                },
            )
            records.append(stage2_rec)
            postfix = {
                "phase": "stage2",
                "acc": f"{res2.accuracy:.4f}",
                "pen": f"{acc_penalty:.4f}",
                "final": f"{final_scal:.4f}",
            }
            update_progress(pbar, tag=tag, done=len(records), total=total_steps, t_start=t_start, postfix=postfix)

    # --- Pareto front (from all evaluations, for cross-track analysis) ---
    nd_idx = pareto_indices_with_accuracy(records, accuracy_target)
    for i in nd_idx:
        records[i].is_pareto = True

    wall_time_s = time.time() - t_start
    finished_at = datetime.now(timezone.utc).isoformat()
    best_obj = min(r.extra.get("scalarized_obj", float("inf")) for r in records)
    if pbar is not None:
        pbar.close()
    print(f"{tag} Done. evaluated={len(records)} pareto={len(nd_idx)} best_obj={best_obj:.4f} wall={wall_time_s:.1f}s")

    return DSERunResult(
        run_config=cfg,
        records=records,
        pareto_record_indices=nd_idx,
        hypervolume=None,   # set by runner with global reference
        hv_reference_point=None,
        wall_time_s=wall_time_s,
        started_at=started_at,
        finished_at=finished_at,
    )
