#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NSGA-II with Random Forest surrogate (multi-objective).

Track: "multi"

Per generation:
  1. Train RF surrogates on all evaluated points (one model per objective).
  2. Generate offspring via crossover + mutation.
  3. Predict on offspring, keep non-dominated candidates.
  4. True-evaluate a subset of evals_per_gen candidates.
  5. Update archive and re-select population via NSGA-II.

Final output: Pareto front from all evaluated points.
"""
from __future__ import annotations

import itertools
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from dse.core import DIM_NAMES, SPACE, evaluate_config, write_temp_config
from dse.metrics import nsga2_select, pareto_indices
from dse.output import DSERecord, DSERunResult, RunConfig


# ---------------------------------------------------------------------------
# Genetic operators
# ---------------------------------------------------------------------------

def _mutate(x: List[int], dim_sizes: List[int], pm: float) -> List[int]:
    y = list(x)
    for i, size in enumerate(dim_sizes):
        if random.random() < pm:
            y[i] = random.randint(0, size - 1)
    return y


def _crossover(a: List[int], b: List[int]) -> Tuple[List[int], List[int]]:
    if len(a) < 2:
        return list(a), list(b)
    p = random.randint(1, len(a) - 1)
    return a[:p] + b[p:], b[:p] + a[p:]


# ---------------------------------------------------------------------------
# Main algorithm
# ---------------------------------------------------------------------------

def run(cfg: RunConfig) -> DSERunResult:
    """
    Run NSGA-II + RF surrogate multi-objective DSE.

    algo_kwargs recognised:
      population    (int, default 20) — population size
      evals_per_gen (int, default 4)  — real evaluations per generation
    """
    kw = cfg.algo_kwargs
    pop_size: int = int(kw.get("population", 20))
    evals_per_gen: int = int(kw.get("evals_per_gen", 4))

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    dim_names = DIM_NAMES
    dim_sizes = [len(SPACE[d]["values"]) for d in dim_names]
    all_points = [list(p) for p in itertools.product(*[range(s) for s in dim_sizes])]

    def decode(idx_vec: List[int]) -> Dict[str, Any]:
        return {d: SPACE[d]["values"][idx_vec[i]] for i, d in enumerate(dim_names)}

    n_init = min(cfg.init_evals, len(all_points))
    # Compute max generations such that total evals ≈ budget
    remaining_budget = cfg.budget - n_init
    n_gens = max(1, remaining_budget // evals_per_gen) if remaining_budget > 0 else 0

    tag = f"[nsga2|s{cfg.seed}]"
    print(f"{tag} space={len(all_points)} budget={cfg.budget} init={n_init} gens={n_gens} evals/gen={evals_per_gen}")

    # Evaluated archive
    X_eval: List[List[int]] = []
    Y_eval: List[Tuple[float, float, float]] = []
    records: List[DSERecord] = []

    pool = list(range(len(all_points)))
    random.shuffle(pool)

    # --- Random initialisation ---
    for t in range(n_init):
        x = all_points[pool[t]]
        cfg_vals = decode(x)
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

        X_eval.append(x)
        Y_eval.append(res.obj_vector())
        records.append(
            DSERecord(
                algo="nsga2",
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
                extra={"generation": 0},
            )
        )
        print(f"{tag} [init {t+1}/{n_init}] lat={res.latency_ns:.3e} en={res.energy_nj:.3e} area={res.area_um2:.3e}")

    # Initial population selection via NSGA-II
    all_idx = list(range(len(X_eval)))
    pop_indices = nsga2_select(all_idx, Y_eval, min(pop_size, len(all_idx)))

    # --- Generational loop ---
    for gen in range(1, n_gens + 1):
        # Train RF surrogate per objective
        X_np = np.array(X_eval, dtype=float)
        y_np = np.array(Y_eval, dtype=float)
        surrogate_models = []
        for j in range(y_np.shape[1]):
            m = RandomForestRegressor(n_estimators=200, random_state=cfg.seed + gen * 10 + j, n_jobs=1)
            m.fit(X_np, y_np[:, j])
            surrogate_models.append(m)

        # Generate offspring
        seen = {tuple(x) for x in X_eval}
        offspring: List[List[int]] = []
        attempts = 0
        while len(offspring) < pop_size * 4 and attempts < pop_size * 40:
            attempts += 1
            a = X_eval[random.choice(pop_indices)]
            b = X_eval[random.choice(pop_indices)]
            c1, c2 = _crossover(a, b)
            c1 = _mutate(c1, dim_sizes, pm=1.0 / len(dim_names))
            c2 = _mutate(c2, dim_sizes, pm=1.0 / len(dim_names))
            for child in (c1, c2):
                if tuple(child) not in seen:
                    offspring.append(child)
                    seen.add(tuple(child))

        if not offspring:
            print(f"{tag} [gen {gen}] no new offspring, stopping early")
            break

        # Predict on offspring, filter to non-dominated
        X_off = np.array(offspring, dtype=float)
        pred_matrix = np.column_stack([m.predict(X_off) for m in surrogate_models])
        pred_vecs = [tuple(float(v) for v in row) for row in pred_matrix]
        nd_off = pareto_indices(pred_vecs)
        nd_candidates = [offspring[i] for i in nd_off] or offspring

        # True-evaluate a subset
        random.shuffle(nd_candidates)
        n_eval = min(evals_per_gen, len(nd_candidates))
        for x in nd_candidates[:n_eval]:
            cfg_vals = decode(x)
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

            X_eval.append(x)
            Y_eval.append(res.obj_vector())
            records.append(
                DSERecord(
                    algo="nsga2",
                    seed=cfg.seed,
                    eval_index=len(records) + 1,
                    phase=f"gen_{gen}",
                    latency_ns=res.latency_ns,
                    energy_nj=res.energy_nj,
                    area_um2=res.area_um2,
                    power_w=res.power_w,
                    accuracy=res.accuracy,
                    elapsed_s=res.elapsed_s,
                    config=res.config,
                    extra={"generation": gen},
                )
            )
            print(f"{tag} [gen {gen}] lat={res.latency_ns:.3e} en={res.energy_nj:.3e} area={res.area_um2:.3e}")

        # Re-select population
        all_idx = list(range(len(X_eval)))
        pop_indices = nsga2_select(all_idx, Y_eval, min(pop_size, len(all_idx)))
        nd_now = pareto_indices(Y_eval)
        print(f"{tag} [gen {gen}] total={len(X_eval)} pareto={len(nd_now)}")

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
