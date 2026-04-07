#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Objective Bayesian Optimization — ParEGO (Pareto Expected Improvement via GP).

Track: "multi"

Each BO iteration:
  1. Sample a random weight vector from Dirichlet distribution.
  2. Normalize objective history and compute Tchebycheff scalarization.
  3. Fit a GP to the scalarized values.
  4. Maximize Expected Improvement to select the next candidate.

The random weight vector changes each iteration, giving coverage of the
Pareto front over multiple acquisitions.

Final output: Pareto front extracted from all evaluated points.
"""
from __future__ import annotations

import itertools
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Tuple

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

from dse.core import DIM_NAMES, SPACE, evaluate_config, write_temp_config
from dse.metrics import normalize_objectives, pareto_indices, tchebycheff_normalized
from dse.output import DSERecord, DSERunResult, RunConfig


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


def run(cfg: RunConfig) -> DSERunResult:
    """
    Run MOBO (ParEGO) multi-objective DSE.

    algo_kwargs recognised:
      (none — ParEGO has no user-facing hyperparameters beyond common ones)
    """
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

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

    tag = f"[mobo|s{cfg.seed}]"
    print(f"{tag} space={n_total} budget={n_iter} init={n_init}")

    chosen: List[int] = []
    records: List[DSERecord] = []
    Y_list: List[Tuple[float, float, float]] = []

    # --- Random initialisation ---
    init_pool = list(range(n_total))
    random.shuffle(init_pool)
    for idx in init_pool[:n_init]:
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

        chosen.append(idx)
        Y_list.append(res.obj_vector())
        records.append(
            DSERecord(
                algo="mobo",
                seed=cfg.seed,
                eval_index=len(records) + 1,
                phase="init",
                latency_ns=res.latency_ns,
                energy_nj=res.energy_nj,
                area_um2=res.area_um2,
                power_w=res.power_w,
                accuracy=res.accuracy,
                elapsed_s=res.elapsed_s,
                config=res.config,
            )
        )
        print(f"{tag} [init {len(chosen)}/{n_iter}] lat={res.latency_ns:.3e} en={res.energy_nj:.3e} area={res.area_um2:.3e}")

    # --- Build GP ---
    kernel = (
        ConstantKernel(1.0, (1e-3, 1e3))
        * Matern(length_scale=np.ones(len(dim_names)), nu=2.5)
        + WhiteKernel(noise_level=1e-6, noise_level_bounds=(1e-9, 1e-1))
    )
    gp = GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        random_state=cfg.seed,
        n_restarts_optimizer=3,
    )

    chosen_set = set(chosen)

    # --- ParEGO acquisition loop ---
    while len(chosen) < n_iter:
        Y = np.array(Y_list, dtype=float)
        Y_norm = normalize_objectives(Y)

        # Random weight vector from Dirichlet for this BO step
        w = np.random.dirichlet(np.ones(Y_norm.shape[1]))
        ys = tchebycheff_normalized(Y_norm, w=w)

        X_obs = X_all[chosen]
        gp.fit(X_obs, ys)

        remain = [i for i in range(n_total) if i not in chosen_set]
        ei = _expected_improvement(gp, X_all[remain], y_best=float(np.min(ys)))
        next_idx = remain[int(np.argmax(ei))]

        cfg_vals = candidates[next_idx]
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

        chosen.append(next_idx)
        chosen_set.add(next_idx)
        Y_list.append(res.obj_vector())
        nd_now = len(pareto_indices(Y_list))
        records.append(
            DSERecord(
                algo="mobo",
                seed=cfg.seed,
                eval_index=len(records) + 1,
                phase="mobo",
                latency_ns=res.latency_ns,
                energy_nj=res.energy_nj,
                area_um2=res.area_um2,
                power_w=res.power_w,
                accuracy=res.accuracy,
                elapsed_s=res.elapsed_s,
                config=res.config,
                extra={"parego_weight": w.tolist()},
            )
        )
        print(
            f"{tag} [mobo {len(chosen)}/{n_iter}] lat={res.latency_ns:.3e} "
            f"en={res.energy_nj:.3e} area={res.area_um2:.3e} pareto={nd_now}"
        )

    # --- Final Pareto front ---
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
