#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bayesian Optimization + Gaussian Process surrogate for MNSIM DSE.
"""
from __future__ import annotations

import argparse
import configparser as cp
import csv
import itertools
import json
import math
import os
import random
import tempfile
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from scipy.stats import norm

from MNSIM.Interface.interface import TrainTestInterface
from MNSIM.Accuracy_Model.Weight_update import weight_update
from MNSIM.Mapping_Model.Tile_connection_graph import TCG
from MNSIM.Latency_Model.Model_latency import Model_latency
from MNSIM.Area_Model.Model_Area import Model_area
from MNSIM.Power_Model.Model_inference_power import Model_inference_power
from MNSIM.Energy_Model.Model_energy import Model_energy


SPACE: Dict[str, Dict[str, Any]] = {
    "xbar_size": {
        "section": "Crossbar level",
        "key": "Xbar_Size",
        # must satisfy xbar_row % Subarray_Size == 0 (default Subarray_Size=256)
        "values": [(256, 256), (512, 512)],
    },
    "adc_choice": {
        "section": "Interface level",
        "key": "ADC_Choice",
        "values": [4, 6, 7, 8],
    },
    "dac_choice": {
        "section": "Interface level",
        "key": "DAC_Choice",
        "values": [1, 2, 3, 4],
    },
    "pe_num": {
        "section": "Tile level",
        "key": "PE_Num",
        "values": [(2, 2), (4, 4), (8, 8)],
    },
    "tile_connection": {
        "section": "Architecture level",
        "key": "Tile_Connection",
        "values": [0, 1, 2, 3],
    },
    "inter_tile_bw": {
        "section": "Tile level",
        "key": "Inter_Tile_Bandwidth",
        "values": [10, 20, 40, 80],
    },
    "intra_tile_bw": {
        "section": "Tile level",
        "key": "Intra_Tile_Bandwidth",
        "values": [512, 1024, 2048],
    },
}


@dataclass
class EvalResult:
    latency_ns: float
    area_um2: float
    power_w: float
    energy_nj: float
    accuracy: float | None
    objective: float
    elapsed_s: float
    config: Dict[str, Any]


@dataclass
class FinalResult:
    base: EvalResult
    final_objective: float
    stage2_accuracy: float | None
    accuracy_penalty: float


def _to_ini_value(v: Any) -> str:
    if isinstance(v, tuple):
        return ",".join(str(x) for x in v)
    return str(v)


def write_temp_config(base_config: str, config_values: Dict[str, Any]) -> str:
    parser = cp.ConfigParser()
    parser.read(base_config, encoding="UTF-8")
    for dim, v in config_values.items():
        meta = SPACE[dim]
        parser.set(meta["section"], meta["key"], _to_ini_value(v))
    fd, path = tempfile.mkstemp(prefix="mnsim_dse_", suffix=".ini")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)
    return path


def evaluate_config(
    sim_config_path: str,
    nn_name: str,
    weights_path: str,
    run_accuracy: bool,
    enable_saf: bool,
    enable_variation: bool,
    enable_rratio: bool,
    fixed_qrange: bool,
    device: str,
    objective_weights: Tuple[float, float, float],
    accuracy_target: float | None,
    accuracy_penalty: float,
    config_values: Dict[str, Any],
) -> EvalResult:
    t0 = time.time()
    test_if = TrainTestInterface(
        network_module=nn_name,
        dataset_module="MNSIM.Interface.cifar10",
        SimConfig_path=sim_config_path,
        weights_file=weights_path,
        device=device,
    )
    structure = test_if.get_structure()
    tcg = TCG(structure, sim_config_path)

    latency = Model_latency(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    latency.calculate_model_latency(mode=1)
    latency_ns = float(max(max(latency.finish_time)))

    area = Model_area(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    power = Model_inference_power(NetStruct=structure, SimConfig_path=sim_config_path, TCG_mapping=tcg)
    energy = Model_energy(
        NetStruct=structure,
        SimConfig_path=sim_config_path,
        TCG_mapping=tcg,
        model_latency=latency,
        model_power=power,
    )
    area_um2 = float(area.arch_total_area)
    power_w = float(power.arch_total_power)
    energy_nj = float(energy.arch_total_energy)

    accuracy = None
    if run_accuracy:
        bits = test_if.get_net_bits()
        bits_after = weight_update(
            sim_config_path,
            bits,
            is_Variation=enable_variation,
            is_SAF=enable_saf,
            is_Rratio=enable_rratio,
        )
        adc_action = "FIX" if fixed_qrange else "SCALE"
        accuracy = float(test_if.set_net_bits_evaluate(bits_after, adc_action=adc_action))

    w_l, w_e, w_a = objective_weights
    base_obj = (
        w_l * math.log1p(latency_ns)
        + w_e * math.log1p(energy_nj)
        + w_a * math.log1p(area_um2)
    )
    penalty = 0.0
    if accuracy_target is not None and accuracy is not None and accuracy < accuracy_target:
        penalty = accuracy_penalty * (accuracy_target - accuracy)
    objective = base_obj + penalty
    elapsed_s = time.time() - t0

    return EvalResult(
        latency_ns=latency_ns,
        area_um2=area_um2,
        power_w=power_w,
        energy_nj=energy_nj,
        accuracy=accuracy,
        objective=objective,
        elapsed_s=elapsed_s,
        config=dict(config_values),
    )


def expected_improvement(
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


def main() -> None:
    parser = argparse.ArgumentParser(description="BO+GP accelerated DSE for MNSIM")
    cwd = os.getcwd()
    parser.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    parser.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--init-random", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--run-accuracy", action="store_true")
    parser.add_argument("--two-stage", action="store_true", help="先硬件BO，再对Top-K做精度复评")
    parser.add_argument("--topk-accuracy", type=int, default=3, help="阶段2做精度复评的候选数")
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=False)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--accuracy-target", type=float, default=None)
    parser.add_argument("--accuracy-penalty", type=float, default=100.0)
    parser.add_argument("--w-latency", type=float, default=1.0)
    parser.add_argument("--w-energy", type=float, default=1.0)
    parser.add_argument("--w-area", type=float, default=0.2)
    parser.add_argument("--output-dir", default=os.path.join(cwd, "dse_bo_results"))
    args = parser.parse_args()

    if args.accuracy_target is not None and not args.run_accuracy:
        raise ValueError("--accuracy-target 需要配合 --run-accuracy 使用")
    if args.two_stage and not args.run_accuracy:
        raise ValueError("--two-stage 需要配合 --run-accuracy 使用")

    random.seed(args.seed)
    np.random.seed(args.seed)
    os.makedirs(args.output_dir, exist_ok=True)

    dim_names = list(SPACE.keys())
    dim_values = [SPACE[k]["values"] for k in dim_names]
    candidates = [dict(zip(dim_names, combo)) for combo in itertools.product(*dim_values)]
    X_all = np.array(
        [[SPACE[d]["values"].index(c[d]) for d in dim_names] for c in candidates],
        dtype=float,
    )

    n_total = len(candidates)
    n_iter = min(args.iterations, n_total)
    n_init = min(args.init_random, n_iter)
    print(f"Total candidates: {n_total}, iterations: {n_iter}, init random: {n_init}")

    chosen: List[int] = []
    results: List[EvalResult] = []

    init_idx = list(range(n_total))
    random.shuffle(init_idx)
    init_idx = init_idx[:n_init]

    weights = (args.w_latency, args.w_energy, args.w_area)

    stage1_run_accuracy = args.run_accuracy and (not args.two_stage)

    for idx in init_idx:
        cfg = candidates[idx]
        temp_cfg = write_temp_config(args.base_config, cfg)
        try:
            res = evaluate_config(
                sim_config_path=temp_cfg,
                nn_name=args.nn,
                weights_path=args.weights,
                run_accuracy=stage1_run_accuracy,
                enable_saf=args.enable_saf,
                enable_variation=args.enable_variation,
                enable_rratio=args.enable_rratio,
                fixed_qrange=args.fixed_qrange,
                device=args.device,
                objective_weights=weights,
                accuracy_target=(args.accuracy_target if stage1_run_accuracy else None),
                accuracy_penalty=(args.accuracy_penalty if stage1_run_accuracy else 0.0),
                config_values=cfg,
            )
        finally:
            os.remove(temp_cfg)
        chosen.append(idx)
        results.append(res)
        print(f"[init {len(chosen)}/{n_iter}] obj={res.objective:.4f} lat={res.latency_ns:.1f}ns en={res.energy_nj:.1f}nJ")

    kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=np.ones(len(dim_names)), nu=2.5) + WhiteKernel(
        noise_level=1e-6, noise_level_bounds=(1e-9, 1e-1)
    )
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=args.seed, n_restarts_optimizer=3)

    while len(chosen) < n_iter:
        X_obs = X_all[chosen]
        y_obs = np.array([r.objective for r in results], dtype=float)
        gp.fit(X_obs, y_obs)

        remain = [i for i in range(n_total) if i not in chosen]
        X_remain = X_all[remain]
        ei = expected_improvement(gp, X_remain, y_best=float(np.min(y_obs)))
        next_idx = remain[int(np.argmax(ei))]

        cfg = candidates[next_idx]
        temp_cfg = write_temp_config(args.base_config, cfg)
        try:
            res = evaluate_config(
                sim_config_path=temp_cfg,
                nn_name=args.nn,
                weights_path=args.weights,
                run_accuracy=stage1_run_accuracy,
                enable_saf=args.enable_saf,
                enable_variation=args.enable_variation,
                enable_rratio=args.enable_rratio,
                fixed_qrange=args.fixed_qrange,
                device=args.device,
                objective_weights=weights,
                accuracy_target=(args.accuracy_target if stage1_run_accuracy else None),
                accuracy_penalty=(args.accuracy_penalty if stage1_run_accuracy else 0.0),
                config_values=cfg,
            )
        finally:
            os.remove(temp_cfg)

        chosen.append(next_idx)
        results.append(res)
        best_obj = min(r.objective for r in results)
        print(f"[bo   {len(chosen)}/{n_iter}] obj={res.objective:.4f} best={best_obj:.4f}")

    stage2_results: List[FinalResult] = []
    if args.two_stage and args.run_accuracy:
        k = max(1, min(args.topk_accuracy, len(results)))
        topk = sorted(results, key=lambda r: r.objective)[:k]
        print(f"\n=== Stage2 accuracy rerank on Top-{k} ===")
        for i, r in enumerate(topk, start=1):
            cfg = r.config
            temp_cfg = write_temp_config(args.base_config, cfg)
            try:
                stage2 = evaluate_config(
                    sim_config_path=temp_cfg,
                    nn_name=args.nn,
                    weights_path=args.weights,
                    run_accuracy=True,
                    enable_saf=args.enable_saf,
                    enable_variation=args.enable_variation,
                    enable_rratio=args.enable_rratio,
                    fixed_qrange=args.fixed_qrange,
                    device=args.device,
                    objective_weights=weights,
                    accuracy_target=None,
                    accuracy_penalty=0.0,
                    config_values=cfg,
                )
            finally:
                os.remove(temp_cfg)
            penalty = 0.0
            if args.accuracy_target is not None and stage2.accuracy is not None and stage2.accuracy < args.accuracy_target:
                penalty = args.accuracy_penalty * (args.accuracy_target - stage2.accuracy)
            final_obj = r.objective + penalty
            stage2_results.append(
                FinalResult(
                    base=r,
                    final_objective=final_obj,
                    stage2_accuracy=stage2.accuracy,
                    accuracy_penalty=penalty,
                )
            )
            print(
                f"[stage2 {i}/{k}] base_obj={r.objective:.4f} "
                f"acc={stage2.accuracy:.6f} penalty={penalty:.4f} final_obj={final_obj:.4f}"
            )

    if stage2_results:
        best_final = min(stage2_results, key=lambda x: x.final_objective)
        best = best_final.base
    else:
        best = min(results, key=lambda r: r.objective)

    csv_path = os.path.join(args.output_dir, "bo_history.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = [
            "iter",
            "objective",
            "latency_ns",
            "energy_nj",
            "area_um2",
            "power_w",
            "accuracy",
            "elapsed_s",
        ] + dim_names
        writer.writerow(header)
        for i, r in enumerate(results, start=1):
            row = [
                i,
                r.objective,
                r.latency_ns,
                r.energy_nj,
                r.area_um2,
                r.power_w,
                r.accuracy if r.accuracy is not None else "",
                r.elapsed_s,
            ] + [r.config[k] for k in dim_names]
            writer.writerow(row)

    best_path = os.path.join(args.output_dir, "best_result.json")
    with open(best_path, "w", encoding="utf-8") as f:
        payload = {
            "objective": best.objective,
            "latency_ns": best.latency_ns,
            "energy_nj": best.energy_nj,
            "area_um2": best.area_um2,
            "power_w": best.power_w,
            "accuracy": best.accuracy,
            "config": best.config,
            "mode": "single_stage" if not stage2_results else "two_stage",
        }
        if stage2_results:
            best_stage2 = min(stage2_results, key=lambda x: x.final_objective)
            payload["stage2"] = {
                "topk": len(stage2_results),
                "accuracy_target": args.accuracy_target,
                "accuracy_penalty_factor": args.accuracy_penalty,
                "final_objective": best_stage2.final_objective,
                "stage2_accuracy": best_stage2.stage2_accuracy,
                "accuracy_penalty": best_stage2.accuracy_penalty,
            }
        json.dump(payload, f, indent=2, ensure_ascii=False)

    if stage2_results:
        stage2_path = os.path.join(args.output_dir, "stage2_rerank.csv")
        with open(stage2_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "base_objective", "stage2_accuracy", "accuracy_penalty", "final_objective"] + dim_names)
            ordered = sorted(stage2_results, key=lambda x: x.final_objective)
            for rank, item in enumerate(ordered, start=1):
                writer.writerow(
                    [
                        rank,
                        item.base.objective,
                        item.stage2_accuracy,
                        item.accuracy_penalty,
                        item.final_objective,
                    ] + [item.base.config[k] for k in dim_names]
                )

    print("\n=== BO Done ===")
    print(f"best objective: {best.objective:.4f}")
    print(f"best latency  : {best.latency_ns:.2f} ns")
    print(f"best energy   : {best.energy_nj:.2f} nJ")
    print(f"best area     : {best.area_um2:.2f} um^2")
    if best.accuracy is not None:
        print(f"best accuracy : {best.accuracy:.6f}")
    if stage2_results:
        best_stage2 = min(stage2_results, key=lambda x: x.final_objective)
        print(f"best final obj(two-stage): {best_stage2.final_objective:.4f}")
        print(f"best stage2 accuracy     : {best_stage2.stage2_accuracy:.6f}")
    print(f"history file  : {csv_path}")
    print(f"best file     : {best_path}")


if __name__ == "__main__":
    main()
