#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run fixed DSE experiment points from a matrix CSV.

Typical use:
  python dse/run_matrix_csv.py \
    --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
    --matrix-name A B \
    --base-config SimConfig.ini \
    --nn vgg8 \
    --weights cifar10_vgg8_params.pth \
    --run-accuracy \
    --accuracy-target 0.88 \
    --enable-saf \
    --enable-variation \
    --device mps
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dse.contracts import (
    build_experiment_manifest,
    make_nominal_scenario,
    read_json,
    resolve_resource,
    write_json,
)
from dse.core import (
    DIM_NAMES,
    available_space_profiles,
    accuracy_violation,
    apply_space_profile,
    current_space_profile,
    decode_dim_value,
    evaluate_config,
    pareto_indices_with_accuracy,
    write_temp_config,
)
from dse.analyze_results import analyze as analyze_dataset_results
from dse.analyze_results import _prepare_default_output_dir
from dse.output import DSERecord, DSERunResult, RunConfig, print_report, print_report_zh, write_all, write_comparison
from dse.progress import try_make_tqdm, update_progress
from dse.run_dse import _append_dataset_history, _apply_global_hv, _auto_dataset_root_from_args, _resolve_output_root, _timestamp


AUTO_OUTPUT_ROOT = "AUTO"

_PROJ_ROOT = Path(__file__).resolve().parent.parent


def _read_matrix_rows(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _filter_rows(
    rows: List[Dict[str, str]],
    matrix_names: Optional[List[str]],
    point_ids: Optional[List[str]],
    max_points: Optional[int],
) -> List[Dict[str, str]]:
    out = rows
    if matrix_names:
        wanted = {x.strip() for x in matrix_names}
        out = [r for r in out if r.get("matrix_name") in wanted]
    if point_ids:
        wanted = {x.strip() for x in point_ids}
        out = [r for r in out if r.get("matrix_point_id") in wanted]
    if max_points is not None:
        out = out[:max_points]
    return out


def _slice_batch(
    rows: List[Dict[str, str]],
    *,
    num_batches: Optional[int],
    batch_index: Optional[int],
    batch_size: Optional[int],
) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    """
    Deterministically split selected rows into batches.

    Priority:
      1) batch_size   -> contiguous chunks of that size
      2) num_batches  -> near-even contiguous chunks
    """
    total = len(rows)
    if total == 0:
        return rows, {"total": 0, "num_batches": 1, "batch_index": 1, "start": 0, "end": 0}

    if batch_size is not None and batch_size <= 0:
        raise ValueError("--batch-size must be > 0.")
    if num_batches is not None and num_batches <= 0:
        raise ValueError("--num-batches must be > 0.")
    if batch_index is not None and batch_index <= 0:
        raise ValueError("--batch-index must be 1-based and > 0.")

    if batch_size is None and num_batches is None and batch_index is None:
        return rows, {"total": total, "num_batches": 1, "batch_index": 1, "start": 0, "end": total}

    if batch_size is not None:
        n_batches = (total + batch_size - 1) // batch_size
        bidx = batch_index or 1
        if bidx > n_batches:
            raise ValueError(f"--batch-index={bidx} exceeds total batches={n_batches}.")
        start = (bidx - 1) * batch_size
        end = min(total, start + batch_size)
        return rows[start:end], {"total": total, "num_batches": n_batches, "batch_index": bidx, "start": start, "end": end}

    n_batches = num_batches or 1
    bidx = batch_index or 1
    if bidx > n_batches:
        raise ValueError(f"--batch-index={bidx} exceeds total batches={n_batches}.")

    base = total // n_batches
    rem = total % n_batches
    start = (bidx - 1) * base + min(bidx - 1, rem)
    size = base + (1 if bidx <= rem else 0)
    end = start + size
    return rows[start:end], {"total": total, "num_batches": n_batches, "batch_index": bidx, "start": start, "end": end}


def _row_to_config(row: Dict[str, str]) -> Dict[str, Any]:
    return {dim: decode_dim_value(dim, row[dim]) for dim in DIM_NAMES}


def _write_selected_manifest(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _run_one_point(job: Dict[str, Any]) -> Dict[str, Any]:
    apply_space_profile(str(job["space_profile"]))
    cfg_vals = dict(job["config_values"])
    temp_path = write_temp_config(str(job["base_config"]), cfg_vals)
    try:
        res = evaluate_config(
            sim_config_path=temp_path,
            nn_name=str(job["nn"]),
            weights_path=str(job["weights"]),
            config_values=cfg_vals,
            run_accuracy=bool(job["run_accuracy"]),
            enable_saf=bool(job["enable_saf"]),
            enable_variation=bool(job["enable_variation"]),
            enable_rratio=bool(job["enable_rratio"]),
            fixed_qrange=bool(job["fixed_qrange"]),
            device=str(job["device"]),
            dataset_module=str(job["dataset_module"]),
            max_acc_batches=int(job["max_acc_batches"]),
            noise_seed=int(job["noise_seed"]),
        )
    finally:
        os.remove(temp_path)

    return {
        "source_index": int(job["source_index"]),
        "noise_seed": int(job["noise_seed"]),
        "row": dict(job["row"]),
        "metrics": {
            "latency_ns": res.latency_ns,
            "energy_nj": res.energy_nj,
            "area_um2": res.area_um2,
            "power_w": res.power_w,
            "accuracy": res.accuracy,
            "elapsed_s": res.elapsed_s,
            "config": dict(res.config),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run paper-oriented fixed experiment matrices from CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    cwd = os.getcwd()
    parser.add_argument("--matrix-csv", required=True, help="Path to matrix_all.csv or matrix_A/B/C/D.csv")
    parser.add_argument("--matrix-name", nargs="+", default=None, help="Run only selected matrix names, e.g. A B")
    parser.add_argument("--point-id", nargs="+", default=None, help="Run only selected point IDs, e.g. A_001 A_002")
    parser.add_argument("--max-points", type=int, default=None, help="Limit number of selected points")
    parser.add_argument("--num-batches", type=int, default=None, help="Split selected points into N contiguous batches.")
    parser.add_argument("--batch-index", type=int, default=None, help="Run only the 1-based batch index after splitting.")
    parser.add_argument("--batch-size", type=int, default=None, help="Alternative to --num-batches: fixed points per batch.")

    parser.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    parser.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dataset-module", default="MNSIM.Interface.cifar10")
    parser.add_argument("--space-profile", default="rram_v2", choices=available_space_profiles())
    parser.add_argument("--max-acc-batches", type=int, default=11)
    parser.add_argument("--scenario-json", default=None, help="Optional scenario contract JSON. If omitted, a nominal scenario is used.")

    parser.add_argument("--run-accuracy", action="store_true")
    parser.add_argument("--accuracy-target", type=float, default=None)
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=False)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--seed", type=int, default=42, help="Metadata seed for this matrix run")
    parser.add_argument("--noise-seed-base", type=int, default=None, help="Deterministic base for per-point noise seeds. Default: seed*1000.")
    parser.add_argument("--dry-run", action="store_true", help="Only materialize selected_matrix.csv and print summary; do not run MNSIM.")
    parser.add_argument("--workers", type=int, default=0, help="Parallel worker processes. 0 = min(n_points, cpu_count//2).")
    parser.add_argument("--fail-fast", action="store_true", help="Abort remaining points on first failure.")

    parser.add_argument("--output-root", default=AUTO_OUTPUT_ROOT)
    parser.add_argument("--dataset-append", action="store_true", help="Append selected points to a persistent dataset root")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    # Resolve resources to support new weights/ and configs/ folders
    args.weights = resolve_resource(args.weights, "weights", repo_root=_PROJ_ROOT)
    args.base_config = resolve_resource(args.base_config, "config", repo_root=_PROJ_ROOT)
    apply_space_profile(args.space_profile)
    if args.noise_seed_base is None:
        args.noise_seed_base = int(args.seed) * 1000

    scenario: Dict[str, Any]
    if args.scenario_json:
        scenario = read_json(Path(args.scenario_json).expanduser().resolve())
    else:
        scenario = make_nominal_scenario(args.base_config)

    if args.accuracy_target is not None and not args.run_accuracy:
        parser.error("--accuracy-target requires --run-accuracy.")
    if args.batch_size is not None and args.num_batches is not None:
        parser.error("--batch-size and --num-batches are mutually exclusive.")

    matrix_csv = Path(args.matrix_csv).expanduser().resolve()
    rows = _read_matrix_rows(matrix_csv)
    rows = _filter_rows(rows, args.matrix_name, args.point_id, args.max_points)
    rows, batch_meta = _slice_batch(
        rows,
        num_batches=args.num_batches,
        batch_index=args.batch_index,
        batch_size=args.batch_size,
    )
    if not rows:
        raise SystemExit("[matrix] No rows selected from matrix CSV.")

    if args.dataset_append and args.output_root == AUTO_OUTPUT_ROOT:
        args.output_root = str(_auto_dataset_root_from_args(args))
    elif args.output_root == AUTO_OUTPUT_ROOT:
        args.output_root = str(Path("artifacts") / "dse" / "matrix_runs" / f"run_{_timestamp()}")

    base_root = _resolve_output_root(args.output_root)
    if args.dataset_append:
        output_root = base_root / "runs" / f"run_{_timestamp()}"
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        output_root = base_root
        output_root.mkdir(parents=True, exist_ok=True)

    batch_tag = f"_b{batch_meta['batch_index']}of{batch_meta['num_batches']}" if batch_meta["num_batches"] > 1 else ""
    trial_dir = output_root / f"matrixcsv_seed{args.seed}{batch_tag}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    _write_selected_manifest(trial_dir / "selected_matrix.csv", rows)

    manifest = build_experiment_manifest(
        workflow="matrix_csv",
        entrypoint="dse/run_matrix_csv.py",
        inputs={
            "matrix_csv": str(matrix_csv),
            "selected_rows": len(rows),
            "selected_matrix_csv": str((trial_dir / "selected_matrix.csv").resolve()),
            "base_config_path": str(Path(args.base_config).resolve()),
            "weights_path": str(Path(args.weights).resolve()),
            "nn": args.nn,
            "dataset_module": args.dataset_module,
        },
        execution={
            "space_profile": args.space_profile,
            "seed": args.seed,
            "noise_seed_base": args.noise_seed_base,
            "run_accuracy": bool(args.run_accuracy),
            "accuracy_target": args.accuracy_target,
            "enable_saf": bool(args.enable_saf),
            "enable_variation": bool(args.enable_variation),
            "enable_rratio": bool(args.enable_rratio),
            "fixed_qrange": bool(args.fixed_qrange),
            "device": args.device,
            "max_acc_batches": args.max_acc_batches,
            "batch": batch_meta,
            "workers": args.workers,
        },
        outputs={
            "output_root": str(output_root.resolve()),
            "trial_dir": str(trial_dir.resolve()),
        },
        scenario=scenario,
        notes=[
            "Per-point noise seeds are derived deterministically from noise_seed_base + source_index - 1.",
            "selected_matrix.csv is the exact fixed-point manifest for this matrix run.",
        ],
    )
    write_json(trial_dir / "experiment_manifest.json", manifest)

    run_cfg = RunConfig(
        algo="matrixcsv",
        seed=args.seed,
        budget=len(rows),
        init_evals=0,
        nn=args.nn,
        weights_path=args.weights,
        base_config_path=args.base_config,
        run_accuracy=args.run_accuracy,
        enable_saf=args.enable_saf,
        enable_variation=args.enable_variation,
        enable_rratio=args.enable_rratio,
        fixed_qrange=args.fixed_qrange,
        device=args.device,
        dataset_module=args.dataset_module,
        max_acc_batches=args.max_acc_batches,
        space_profile=args.space_profile,
        scenario=scenario,
        algo_kwargs={
            "accuracy_target": args.accuracy_target,
            "matrix_csv": str(matrix_csv),
            "batch": batch_meta,
            "noise_seed_base": args.noise_seed_base,
        },
    )

    print(f"[matrix] input csv     : {matrix_csv}")
    print(f"[matrix] selected rows : {len(rows)}")
    print(
        f"[matrix] batch         : {batch_meta['batch_index']}/{batch_meta['num_batches']} "
        f"(slice {batch_meta['start'] + 1}-{batch_meta['end']} of {batch_meta['total']})"
    )
    print(f"[matrix] space profile : {current_space_profile()}")
    print(f"[matrix] output root   : {output_root}")
    print(f"[matrix] trial dir     : {trial_dir}")
    print(f"[matrix] scenario      : {scenario.get('name', scenario.get('kind', 'unknown'))}")

    if args.dry_run:
        meta = {
            "matrix_csv": str(matrix_csv),
            "selected_rows": len(rows),
            "batch": batch_meta,
            "matrix_names": sorted({r.get("matrix_name", "") for r in rows}),
            "point_ids": [r.get("matrix_point_id", "") for r in rows],
            "trial_dir": str(trial_dir),
            "space_profile": args.space_profile,
            "dry_run": True,
        }
        with open(trial_dir / "matrix_run_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        manifest["outputs"]["dry_run"] = True
        write_json(trial_dir / "experiment_manifest.json", manifest)
        print("[matrix] dry-run only; no simulation executed.")
        return

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    n_points = len(rows)
    max_workers = args.workers if args.workers > 0 else max(1, min(n_points, (os.cpu_count() or 2) // 2))
    print(f"[matrix] workers       : {max_workers}")

    jobs: List[Dict[str, Any]] = []
    for source_index, row in enumerate(rows, start=1):
        jobs.append(
            {
                "source_index": source_index,
                "row": row,
                "config_values": _row_to_config(row),
                "base_config": args.base_config,
                "nn": args.nn,
                "weights": args.weights,
                "run_accuracy": args.run_accuracy,
                "enable_saf": args.enable_saf,
                "enable_variation": args.enable_variation,
                "enable_rratio": args.enable_rratio,
                "fixed_qrange": args.fixed_qrange,
                "device": args.device,
                "dataset_module": args.dataset_module,
                "max_acc_batches": args.max_acc_batches,
                "space_profile": args.space_profile,
                "noise_seed": args.noise_seed_base + source_index - 1,
            }
        )

    completed: List[Dict[str, Any]] = []
    failures: List[Tuple[str, str]] = []
    pbar = try_make_tqdm(n_points, f"[matrix|s{args.seed}]")
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        future_to_job = {pool.submit(_run_one_point, job): job for job in jobs}
        done_count = 0
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            row = job["row"]
            done_count += 1
            try:
                payload = future.result()
                completed.append(payload)
                metrics = payload["metrics"]
                postfix = {
                    "id": row.get("matrix_point_id", str(job["source_index"])),
                    "lat": f"{float(metrics['latency_ns']):.2e}",
                    "en": f"{float(metrics['energy_nj']):.2e}",
                    "area": f"{float(metrics['area_um2']):.2e}",
                }
                if args.run_accuracy and metrics.get("accuracy") is not None:
                    postfix["acc"] = f"{float(metrics['accuracy']):.4f}"
                update_progress(pbar, tag=f"[matrix|s{args.seed}]", done=done_count, total=n_points, t_start=t0, postfix=postfix)
            except Exception as exc:
                failures.append((row.get("matrix_point_id", "?"), str(exc)))
                postfix = {"id": row.get("matrix_point_id", "?"), "status": "FAIL"}
                update_progress(pbar, tag=f"[matrix|s{args.seed}]", done=done_count, total=n_points, t_start=t0, postfix=postfix)
                print(f"[matrix] FAIL {row.get('matrix_point_id', '?')}: {exc}")
                if args.fail_fast:
                    pool.shutdown(wait=False, cancel_futures=True)
                    print("[matrix] --fail-fast: aborting remaining points.")
                    break
    if pbar is not None:
        pbar.close()

    if not completed:
        raise SystemExit("[matrix] No successful points finished.")

    completed.sort(key=lambda item: int(item["source_index"]))
    records: List[DSERecord] = []
    for eval_index, payload in enumerate(completed, start=1):
        row = payload["row"]
        metrics = payload["metrics"]
        rec = DSERecord(
            algo="matrixcsv",
            seed=args.seed,
            eval_index=eval_index,
            phase=f"matrix_{row.get('matrix_name', 'X')}",
            latency_ns=float(metrics["latency_ns"]),
            energy_nj=float(metrics["energy_nj"]),
            area_um2=float(metrics["area_um2"]),
            power_w=float(metrics["power_w"]),
            accuracy=metrics.get("accuracy"),
            elapsed_s=float(metrics["elapsed_s"]),
            config=dict(metrics["config"]),
            extra={
                "matrix_name": row.get("matrix_name"),
                "matrix_point_id": row.get("matrix_point_id"),
                "matrix_purpose": row.get("matrix_purpose"),
                "source_index": int(payload["source_index"]),
                "noise_seed": int(payload["noise_seed"]),
                "accuracy_violation": accuracy_violation(metrics.get("accuracy"), args.accuracy_target),
            },
        )
        records.append(rec)

    nd_idx = pareto_indices_with_accuracy(records, args.accuracy_target)
    for i in nd_idx:
        records[i].is_pareto = True

    result = DSERunResult(
        run_config=run_cfg,
        records=records,
        pareto_record_indices=nd_idx,
        hypervolume=None,
        hv_reference_point=None,
        wall_time_s=time.time() - t0,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    _, [result] = _apply_global_hv([result])

    write_all(result, str(trial_dir))
    write_comparison([result], str(output_root / "comparison"))
    print_report(result)
    print_report_zh(result)

    meta = {
        "matrix_csv": str(matrix_csv),
        "selected_rows": len(rows),
        "batch": batch_meta,
        "successful_rows": len(completed),
        "failed_rows": len(failures),
        "matrix_names": sorted({r.get("matrix_name", "") for r in rows}),
        "point_ids": [r.get("matrix_point_id", "") for r in rows],
        "trial_dir": str(trial_dir),
        "space_profile": args.space_profile,
        "workers": max_workers,
        "noise_seed_base": args.noise_seed_base,
        "failures": [{"matrix_point_id": pid, "error": err} for pid, err in failures],
    }
    with open(trial_dir / "matrix_run_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    if args.dataset_append:
        _append_dataset_history(base_root, output_root, [result])
        print(f"[matrix] dataset root  : {base_root}")
        try:
            analysis_output_dir, _ = _prepare_default_output_dir(base_root)
            analysis_result = analyze_dataset_results(base_root, analysis_output_dir, args.accuracy_target, topk=20)
            print(f"[matrix] analysis html : {analysis_result['html_path']}")
            print(f"[matrix] analysis dir  : {analysis_output_dir}")
            if analysis_result.get("compensation_report_path"):
                print(f"[matrix] compare html  : {analysis_result['compensation_report_path']}")
        except Exception as exc:
            print(f"[matrix] WARN analysis refresh failed: {exc}")

    if failures:
        print(f"[matrix] failures      : {len(failures)}")
    print(f"[matrix] done. wall={result.wall_time_s:.1f}s pareto={result.pareto_size}")


if __name__ == "__main__":
    main()
