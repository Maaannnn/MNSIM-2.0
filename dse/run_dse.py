#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_dse.py — Concurrent DSE Runner for MNSIM-2.0

Runs multiple DSE algorithms (and/or multiple random seeds) in parallel
using ProcessPoolExecutor. After all trials complete, computes a shared
hypervolume reference point and generates a unified comparison report.

Usage example:
  # Compare NSGA-II and MOBO across 3 seeds (multi-objective track)
  python dse/run_dse.py \
    --algos nsga2 mobo \
    --seeds 42 43 44 \
    --budget 24 --init-evals 6 \
    --nn vgg8 --weights cifar10_vgg8_params.pth \
    --base-config SimConfig.ini \
    --output-root dse_output/run01 \
    --workers 3

  # Single-objective BO (scalarized)
  python dse/run_dse.py \
    --algos bo_gp \
    --seeds 42 43 44 \
    --budget 20 --init-evals 6 \
    --nn vgg8 --weights cifar10_vgg8_params.pth \
    --base-config SimConfig.ini \
    --output-root dse_output/run01 \
    --w-latency 1.0 --w-energy 1.0 --w-area 0.2

Comparison note:
  - bo_gp (track=single) vs nsga2/mobo (track=multi) is NOT a direct comparison.
    They optimise different problem formulations (scalar vs vector objectives).
  - Within multi-track: nsga2 vs mobo are compared via Hypervolume.
  - bo_gp remains a single-objective track; keep it separate from multi-objective HV.
  - Cross-track supplementary: Pareto front quality from bo_gp can be visualised
    alongside nsga2/mobo fronts, but their HV values use different semantics.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is on sys.path when invoked as "python dse/run_dse.py"
_PROJ_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from dse.metrics import compute_reference_point, hypervolume_3d
from dse.output import DSERunResult, RunConfig, print_report, write_all, write_comparison


def _run_trial(algo: str, seed: int, run_cfg_dict: Dict[str, Any], output_dir: str) -> str:
    """
    Execute one (algo, seed) trial inside a subprocess.

    Returns the path to result.json on success.
    Raises on failure (exception propagates through the Future).
    """
    from dse.algorithms import REGISTRY
    from dse.output import RunConfig, write_all

    cfg = RunConfig(**run_cfg_dict)
    module = REGISTRY[algo]
    result = module.run(cfg)

    os.makedirs(output_dir, exist_ok=True)
    write_all(result, output_dir)
    return os.path.join(output_dir, "result.json")


def _apply_global_hv(results: List[DSERunResult]) -> Tuple[Tuple[float, float, float], List[DSERunResult]]:
    """Compute global reference point from all observations and update HV for each result."""
    all_vecs = []
    for r in results:
        all_vecs.extend(rec.obj_vector() for rec in r.records)

    if not all_vecs:
        return (1.0, 1.0, 1.0), results

    ref = compute_reference_point(all_vecs, inflate=1.1)

    updated = []
    for r in results:
        pareto_vecs = [r.records[i].obj_vector() for i in r.pareto_record_indices]
        hv = hypervolume_3d(pareto_vecs, ref) if pareto_vecs else 0.0
        updated.append(
            DSERunResult(
                run_config=r.run_config,
                records=r.records,
                pareto_record_indices=r.pareto_record_indices,
                hypervolume=hv,
                hv_reference_point=ref,
                wall_time_s=r.wall_time_s,
                started_at=r.started_at,
                finished_at=r.finished_at,
            )
        )

    return ref, updated


def load_results_from_dir(output_root: str) -> List[DSERunResult]:
    """
    Load all trial results from an output root directory.

    Looks for subdirectories named <algo>_seed<N>/ containing result.json + history.csv.
    Useful for regenerating the comparison report without re-running experiments.
    """
    import csv
    from dse.core import decode_dim_value, DIM_NAMES
    from dse.output import DSERecord, RunConfig

    results = []
    root = Path(output_root)
    for trial_dir in sorted(root.iterdir()):
        result_json = trial_dir / "result.json"
        history_csv = trial_dir / "history.csv"
        if not result_json.exists() or not history_csv.exists():
            continue
        with open(result_json, encoding="utf-8") as f:
            rj = json.load(f)

        rc_data = rj.get("run_config", {})
        algo = rj["algo"]
        seed = rj["seed"]
        cfg = RunConfig(
            algo=algo,
            seed=seed,
            budget=rj.get("budget", 0),
            init_evals=0,
            nn=rc_data.get("nn", ""),
            weights_path=rc_data.get("weights_path", ""),
            base_config_path=rc_data.get("base_config_path", ""),
            run_accuracy=rc_data.get("run_accuracy", False),
            device=rc_data.get("device", "cpu"),
            algo_kwargs=rc_data.get("algo_kwargs", {}),
        )

        records = []
        with open(history_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                config = {d: decode_dim_value(d, row[d]) for d in DIM_NAMES}
                extra = json.loads(row.get("extra_json", "{}") or "{}")
                records.append(DSERecord(
                    algo=row["algo"],
                    seed=int(row["seed"]),
                    eval_index=int(row["eval_index"]),
                    phase=row["phase"],
                    latency_ns=float(row["latency_ns"]),
                    energy_nj=float(row["energy_nj"]),
                    area_um2=float(row["area_um2"]),
                    power_w=float(row["power_w"]),
                    accuracy=float(row["accuracy"]) if row["accuracy"] else None,
                    elapsed_s=float(row["elapsed_s"]),
                    config=config,
                    is_pareto=bool(int(row.get("is_pareto", 0))),
                    extra=extra,
                ))

        pareto_idx = [i for i, r in enumerate(records) if r.is_pareto]
        results.append(DSERunResult(
            run_config=cfg,
            records=records,
            pareto_record_indices=pareto_idx,
            hypervolume=rj.get("hypervolume"),
            hv_reference_point=tuple(rj["hv_reference_point"]) if rj.get("hv_reference_point") else None,
            wall_time_s=rj.get("wall_time_s", 0.0),
            started_at=rj.get("started_at", ""),
            finished_at=rj.get("finished_at", ""),
        ))
    return results


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Concurrent DSE runner for MNSIM-2.0",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    cwd = os.getcwd()

    p.add_argument(
        "--algos", nargs="+", default=["nsga2", "mobo"],
        choices=["bo_gp", "nsga2", "mobo"],
        help="Algorithms to run. Multi-track: nsga2/mobo. Single-track: bo_gp.",
    )
    p.add_argument("--seeds", nargs="+", type=int, default=[42],
                   help="Random seeds (one trial per algo×seed combination).")

    p.add_argument("--budget", type=int, default=24,
                   help="Total MNSIM evaluations per trial.")
    p.add_argument("--init-evals", type=int, default=6,
                   help="Random initialisation evaluations before algorithm-guided search.")

    p.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    p.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    p.add_argument("--nn", default="vgg8")
    p.add_argument("--device", default="cpu")
    p.add_argument("--dataset-module", default="MNSIM.Interface.cifar10")

    p.add_argument("--run-accuracy", action="store_true",
                   help="Include accuracy simulation (slower but includes acc metric).")
    p.add_argument("--enable-saf", action="store_true", default=True)
    p.add_argument("--enable-variation", action="store_true", default=False)
    p.add_argument("--enable-rratio", action="store_true", default=False)
    p.add_argument("--fixed-qrange", action="store_true", default=False)

    p.add_argument("--w-latency", type=float, default=1.0,
                   help="[bo_gp] Weight for log-latency in scalarization.")
    p.add_argument("--w-energy", type=float, default=1.0,
                   help="[bo_gp] Weight for log-energy in scalarization.")
    p.add_argument("--w-area", type=float, default=0.2,
                   help="[bo_gp] Weight for log-area in scalarization.")
    p.add_argument("--two-stage", action="store_true",
                   help="[bo_gp] Hardware-only BO in stage-1, accuracy rerank in stage-2.")
    p.add_argument("--topk-accuracy", type=int, default=3,
                   help="[bo_gp] Number of candidates for stage-2 accuracy rerank.")
    p.add_argument("--accuracy-target", type=float, default=None,
                   help="[bo_gp] Accuracy constraint (penalise below this value).")
    p.add_argument("--accuracy-penalty", type=float, default=100.0,
                   help="[bo_gp] Penalty coefficient for accuracy constraint.")

    p.add_argument("--population", type=int, default=20,
                   help="[nsga2] Population size.")
    p.add_argument("--evals-per-gen", type=int, default=4,
                   help="[nsga2] True evaluations per generation.")

    p.add_argument("--workers", type=int, default=0,
                   help="Max parallel processes. 0 = min(n_trials, cpu_count//2).")
    p.add_argument("--fail-fast", action="store_true",
                   help="Abort all remaining trials on first failure.")

    p.add_argument("--output-root", default=os.path.join(cwd, "dse_output"),
                   help="Root directory. Trials go in <output-root>/<algo>_seed<N>/")

    p.add_argument("--compare-only", action="store_true",
                   help="Skip running algorithms; load existing results from --output-root and regenerate comparison.")

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    output_root = Path(args.output_root)
    compare_dir = output_root / "comparison"

    if args.compare_only:
        print(f"[runner] Loading existing results from {output_root} ...")
        results = load_results_from_dir(str(output_root))
        if not results:
            print("[runner] No results found. Run without --compare-only first.")
            sys.exit(1)
        _, results = _apply_global_hv(results)
        for r in results:
            trial_dir = output_root / f"{r.run_config.algo}_seed{r.run_config.seed}"
            if trial_dir.exists():
                from dse.output import write_result_json
                write_result_json(r, str(trial_dir / "result.json"))
        write_comparison(results, str(compare_dir))
        return

    trials: List[Tuple[str, int, str]] = []
    for algo in args.algos:
        for seed in args.seeds:
            trial_dir = str(output_root / f"{algo}_seed{seed}")
            trials.append((algo, seed, trial_dir))

    n_trials = len(trials)
    max_workers = args.workers if args.workers > 0 else max(1, min(n_trials, (os.cpu_count() or 2) // 2))
    print(f"[runner] {n_trials} trials × {max_workers} parallel workers")
    print(f"[runner] output root: {output_root}")
    print(f"[runner] algorithms: {args.algos}  seeds: {args.seeds}  budget: {args.budget}")
    print(f"[runner] Multi-track: {[a for a in args.algos if a != 'bo_gp']}")
    print(f"[runner] Single-track: {[a for a in args.algos if a == 'bo_gp']}")
    if "bo_gp" in args.algos and any(a in args.algos for a in ["nsga2", "mobo"]):
        print("[runner] NOTE: bo_gp (single-obj) and nsga2/mobo (multi-obj) are on different tracks.")
        print("[runner]       Their results will be reported separately. HV is for multi-track only.")

    bo_kwargs: Dict[str, Any] = {
        "w_latency": args.w_latency,
        "w_energy": args.w_energy,
        "w_area": args.w_area,
        "two_stage": args.two_stage,
        "topk_accuracy": args.topk_accuracy,
        "accuracy_target": args.accuracy_target,
        "accuracy_penalty": args.accuracy_penalty,
    }
    nsga2_kwargs: Dict[str, Any] = {
        "population": args.population,
        "evals_per_gen": args.evals_per_gen,
    }
    algo_kwargs_map = {"bo_gp": bo_kwargs, "nsga2": nsga2_kwargs, "mobo": {}}

    def _make_run_cfg_dict(algo: str, seed: int) -> Dict[str, Any]:
        return {
            "algo": algo,
            "seed": seed,
            "budget": args.budget,
            "init_evals": args.init_evals,
            "nn": args.nn,
            "weights_path": args.weights,
            "base_config_path": args.base_config,
            "run_accuracy": args.run_accuracy,
            "enable_saf": args.enable_saf,
            "enable_variation": args.enable_variation,
            "enable_rratio": args.enable_rratio,
            "fixed_qrange": args.fixed_qrange,
            "device": args.device,
            "dataset_module": args.dataset_module,
            "algo_kwargs": algo_kwargs_map.get(algo, {}),
        }

    t0 = time.time()
    completed_results: List[DSERunResult] = []
    failed: List[Tuple[str, int, Exception]] = []

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        future_to_trial = {
            pool.submit(_run_trial, algo, seed, _make_run_cfg_dict(algo, seed), trial_dir): (algo, seed, trial_dir)
            for algo, seed, trial_dir in trials
        }

        done_count = 0
        for future in as_completed(future_to_trial):
            algo, seed, trial_dir = future_to_trial[future]
            done_count += 1
            try:
                future.result()
                loaded = load_results_from_dir(str(Path(trial_dir).parent))
                for r in loaded:
                    if r.run_config.algo == algo and r.run_config.seed == seed:
                        completed_results.append(r)
                        print(
                            f"[runner] [{done_count}/{n_trials}] DONE  {algo}+seed{seed}"
                            f" | pareto={r.pareto_size}  wall={r.wall_time_s:.1f}s"
                        )
                        break
            except Exception as exc:
                failed.append((algo, seed, exc))
                print(f"[runner] [{done_count}/{n_trials}] FAIL  {algo}+seed{seed}: {exc}")
                if args.fail_fast:
                    pool.shutdown(wait=False, cancel_futures=True)
                    print("[runner] --fail-fast: aborting remaining trials.")
                    break

    total_wall = time.time() - t0

    if failed:
        print(f"\n[runner] {len(failed)} trial(s) failed:")
        for algo, seed, exc in failed:
            print(f"  {algo}+seed{seed}: {exc}")

    if not completed_results:
        print("[runner] No successful results to compare. Exiting.")
        sys.exit(1 if failed else 0)

    print(f"\n[runner] Computing global hypervolume reference ({len(completed_results)} trials)...")
    ref, completed_results = _apply_global_hv(completed_results)
    print(f"[runner] HV reference: lat={ref[0]:.3e}  en={ref[1]:.3e}  area={ref[2]:.3e}")

    for r in completed_results:
        trial_dir = output_root / f"{r.run_config.algo}_seed{r.run_config.seed}"
        if trial_dir.exists():
            from dse.output import write_result_json
            write_result_json(r, str(trial_dir / "result.json"))

    for r in sorted(completed_results, key=lambda r: (r.run_config.algo, r.run_config.seed)):
        print_report(r)

    write_comparison(completed_results, str(compare_dir))
    print(f"\n[runner] Total wall time: {total_wall:.1f}s")
    print(f"[runner] Comparison output: {compare_dir}")


if __name__ == "__main__":
    main()
