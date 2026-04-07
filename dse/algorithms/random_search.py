#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Random Search DSE baseline.

Samples the design space uniformly at random without replacement.
Serves as:
  - A baseline for multi-objective comparison (hypervolume lower bound)
  - An exploration budget reference
  - A source for the global HV reference point estimation
"""
from __future__ import annotations

import itertools
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Tuple

from dse.core import DIM_NAMES, SPACE, evaluate_config, write_temp_config
from dse.metrics import pareto_indices
from dse.output import DSERecord, DSERunResult, RunConfig


def run(cfg: RunConfig) -> DSERunResult:
    """Run random search for cfg.budget evaluations."""
    random.seed(cfg.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    # Build full candidate list and shuffle
    all_combos = list(itertools.product(*[SPACE[d]["values"] for d in DIM_NAMES]))
    random.shuffle(all_combos)
    selected = all_combos[: cfg.budget]

    records: List[DSERecord] = []
    tag = f"[random|s{cfg.seed}]"

    for i, combo in enumerate(selected, start=1):
        config_values = dict(zip(DIM_NAMES, combo))
        temp_cfg = write_temp_config(cfg.base_config_path, config_values)
        try:
            res = evaluate_config(
                sim_config_path=temp_cfg,
                nn_name=cfg.nn,
                weights_path=cfg.weights_path,
                config_values=config_values,
                run_accuracy=cfg.run_accuracy,
                enable_saf=cfg.enable_saf,
                enable_variation=cfg.enable_variation,
                enable_rratio=cfg.enable_rratio,
                fixed_qrange=cfg.fixed_qrange,
                device=cfg.device,
                dataset_module=cfg.dataset_module,
            )
        finally:
            os.remove(temp_cfg)

        records.append(
            DSERecord(
                algo="random",
                seed=cfg.seed,
                eval_index=i,
                phase="random",
                latency_ns=res.latency_ns,
                energy_nj=res.energy_nj,
                area_um2=res.area_um2,
                power_w=res.power_w,
                accuracy=res.accuracy,
                elapsed_s=res.elapsed_s,
                config=res.config,
            )
        )
        print(
            f"{tag} [{i}/{cfg.budget}] lat={res.latency_ns:.3e} "
            f"en={res.energy_nj:.3e} area={res.area_um2:.3e}"
        )

    # Compute Pareto front
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
        hypervolume=None,   # set by runner after global reference is computed
        hv_reference_point=None,
        wall_time_s=wall_time_s,
        started_at=started_at,
        finished_at=finished_at,
    )
