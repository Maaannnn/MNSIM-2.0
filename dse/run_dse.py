#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_dse.py — Concurrent DSE Runner for MNSIM-2.0

Runs multiple DSE algorithms (and/or multiple random seeds) in parallel
using ProcessPoolExecutor. After all trials complete, computes a shared
hypervolume reference point and generates a unified comparison report.

Usage example:
  # Compare NSGA-II and MOBO across 3 seeds (multi-objective track)
  # Omit --output-root (default AUTO) → new dir <repo>/dse_runs/run_YYYYMMDD_HHMMSS each run
  python dse/run_dse.py \
    --algos nsga2 mobo \
    --seeds 42 43 44 \
    --budget 24 --init-evals 6 \
    --nn vgg8 --weights cifar10_vgg8_params.pth \
    --base-config SimConfig.ini \
    --workers 3 \
    --plots

  # Regenerate figures only (needs matplotlib); must pass an existing run directory
  python dse/run_dse.py --plot-only --output-root dse_runs/run_20260101_120000

  # Single-objective BO (scalarized)
  python dse/run_dse.py \
    --algos bo_gp \
    --seeds 42 43 44 \
    --budget 20 --init-evals 6 \
    --nn vgg8 --weights cifar10_vgg8_params.pth \
    --base-config SimConfig.ini \
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
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path when invoked as "python dse/run_dse.py"
_PROJ_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

# Default --output-root: new directory each run (no overwrite). See _resolve_output_root.
AUTO_OUTPUT_ROOT = "AUTO"


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _slug(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    txt = "".join(out).strip("_")
    return txt or "x"


def _auto_dataset_root_from_args(args: argparse.Namespace) -> Path:
    """
    Build a deterministic dataset root from sampling/version parameters.

    Example:
      dse_datasets/cifar10_vgg8_cifar10_vgg8_params_SimConfig_ppa_saf1_var0_rr0_qfix0
    """
    ds = str(args.dataset_module).split(".")[-1]
    nn = str(args.nn)
    w_stem = Path(str(args.weights)).stem
    cfg_stem = Path(str(args.base_config)).stem
    acc_tag = "acc" if bool(args.run_accuracy) else "ppa"
    flags = f"saf{int(bool(args.enable_saf))}_var{int(bool(args.enable_variation))}_rr{int(bool(args.enable_rratio))}_qfix{int(bool(args.fixed_qrange))}"
    name = "_".join([_slug(ds), _slug(nn), _slug(w_stem), _slug(cfg_stem), acc_tag, flags])
    return _PROJ_ROOT / "dse_datasets" / name


def _resolve_output_root(raw: str) -> Path:
    """
    AUTO → <repo>/dse_runs/run_YYYYMMDD_HHMMSS (created).
    Other values → absolute path (cwd-relative names resolved from cwd).
    """
    if raw == AUTO_OUTPUT_ROOT:
        stamp = _timestamp()
        out = _PROJ_ROOT / "dse_runs" / f"run_{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        return out
    return Path(os.path.abspath(os.path.expanduser(raw)))


from dse.metrics import compute_reference_point, hypervolume_3d
from dse.output import DSERunResult, RunConfig, print_report, print_report_zh, write_all, write_comparison


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
            enable_saf=rc_data.get("enable_saf", True),
            enable_variation=rc_data.get("enable_variation", False),
            enable_rratio=rc_data.get("enable_rratio", False),
            fixed_qrange=rc_data.get("fixed_qrange", False),
            device=rc_data.get("device", "cpu"),
            dataset_module=rc_data.get("dataset_module", "MNSIM.Interface.cifar10"),
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


# --- Optional comparison plots (matplotlib) ---------------------------------

_ALGO_COLORS: Dict[str, str] = {
    "bo_gp": "#d62728",
    "nsga2": "#1f77b4",
    "mobo": "#2ca02c",
    "random": "#9467bd",
}


def _matplotlib_zh_font() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Heiti SC",
        "Songti SC",
        "SimHei",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def _plot_pareto_projections(results: List[DSERunResult], out_path: Path, *, zh: bool = False) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if zh:
        _matplotlib_zh_font()
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    if zh:
        pairs = [
            (0, 1, "延迟 (ns)", "能耗 (nJ)"),
            (0, 2, "延迟 (ns)", "面积 (µm²)"),
            (1, 2, "能耗 (nJ)", "面积 (µm²)"),
        ]
        supt = "帕累托集（大点）与全部评估点（淡点）"
    else:
        pairs = [
            (0, 1, "Latency (ns)", "Energy (nJ)"),
            (0, 2, "Latency (ns)", "Area (µm²)"),
            (1, 2, "Energy (nJ)", "Area (µm²)"),
        ]
        supt = "Pareto sets (large) vs all evaluated points (faint)"
    ax_flat = axes.ravel()
    for ax, (i, j, xl, yl) in zip(ax_flat[:3], pairs):
        for r in results:
            algo = r.run_config.algo
            color = _ALGO_COLORS.get(algo, "#7f7f7f")
            label = f"{algo} 种子{r.run_config.seed}" if zh else f"{algo} seed{r.run_config.seed}"
            pts = [rec.obj_vector() for rec in r.records]
            if pts:
                xs = [p[i] for p in pts]
                ys = [p[j] for p in pts]
                ax.scatter(xs, ys, s=12, alpha=0.25, color=color, marker="o", linewidths=0)
            pfront = [rec.obj_vector() for rec in r.pareto_records]
            if pfront:
                xs = [p[i] for p in pfront]
                ys = [p[j] for p in pfront]
                ax.scatter(
                    xs, ys, s=55, alpha=0.9, color=color, edgecolors="white", linewidths=0.6, label=label
                )
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(fontsize=7, loc="best")
    axes[1, 1].axis("off")
    fig.suptitle(supt, fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_convergence_history(results: List[DSERunResult], out_path: Path, *, zh: bool = False) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if zh:
        _matplotlib_zh_font()
    fig, ax = plt.subplots(figsize=(8, 5))
    for r in results:
        algo = r.run_config.algo
        color = _ALGO_COLORS.get(algo, "#7f7f7f")
        tag = f"{algo} 种{r.run_config.seed}" if zh else f"{algo} s{r.run_config.seed}"
        bests: List[float] = []
        best = float("inf")
        for rec in r.records:
            v = rec.obj_vector()
            cur = np.log(v[0]) + np.log(v[1]) + np.log(max(v[2], 1e-30))
            best = min(best, cur)
            bests.append(best)
        xs = list(range(1, len(bests) + 1))
        ax.plot(xs, bests, color=color, alpha=0.85, label=tag)
    if zh:
        ax.set_xlabel("评估序号")
        ax.set_ylabel("最优 log(延迟×能耗×面积)（越小越好）")
        ax.set_title("至今最优标量进展（诊断用）")
    else:
        ax.set_xlabel("Evaluation index")
        ax.set_ylabel("Best log(lat×en×area) (lower is better)")
        ax.set_title("Best-so-far scalar progress (diagnostic)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_hypervolume_bar(comparison_json: Path, out_path: Path, *, zh: bool = False) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if zh:
        _matplotlib_zh_font()
    with open(comparison_json, encoding="utf-8") as f:
        data = json.load(f)
    trials: List[Dict[str, Any]] = data.get("trials", [])
    multi = [t for t in trials if t.get("track") == "multi" and t.get("hypervolume") is not None]
    if not multi:
        return
    if zh:
        labels = [f'{t["algo"]}\n种子{t["seed"]}' for t in multi]
    else:
        labels = [f'{t["algo"]}\n{t["seed"]}' for t in multi]
    vals = [float(t["hypervolume"]) for t in multi]
    colors = [_ALGO_COLORS.get(t["algo"], "#7f7f7f") for t in multi]
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.9), 4.5))
    x = np.arange(len(labels))
    ax.bar(x, vals, color=colors, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    if zh:
        ax.set_ylabel("超体积 HV（共享参考点）")
        ax.set_title("多目标轨道 — 各试验超体积")
    else:
        ax.set_ylabel("Hypervolume (shared reference)")
        ax.set_title("Multi-objective track — hypervolume by trial")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def write_comparison_plots(output_root: Path, plots_dir: Optional[Path] = None) -> None:
    """
    Write pareto/convergence/HV PNGs under comparison/plots/ or plots/.
    Requires matplotlib (pip install matplotlib).
    """
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("[runner] matplotlib not installed; skip plots. pip install matplotlib")
        return

    results = load_results_from_dir(str(output_root))
    if not results:
        print(f"[runner] No trial results under {output_root}; skip plots.")
        return

    if plots_dir is not None:
        plot_dir = plots_dir
    else:
        cmp_sub = output_root / "comparison"
        plot_dir = cmp_sub / "plots" if cmp_sub.is_dir() else output_root / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    pareto_png = plot_dir / "pareto_projections.png"
    pareto_png_zh = plot_dir / "pareto_projections_zh.png"
    conv_png = plot_dir / "convergence_scalar.png"
    conv_png_zh = plot_dir / "convergence_scalar_zh.png"
    _plot_pareto_projections(results, pareto_png, zh=False)
    _plot_pareto_projections(results, pareto_png_zh, zh=True)
    _plot_convergence_history(results, conv_png, zh=False)
    _plot_convergence_history(results, conv_png_zh, zh=True)

    cmp_json = output_root / "comparison" / "comparison.json"
    if cmp_json.is_file():
        hv_png = plot_dir / "hypervolume_by_trial.png"
        hv_png_zh = plot_dir / "hypervolume_by_trial_zh.png"
        _plot_hypervolume_bar(cmp_json, hv_png, zh=False)
        _plot_hypervolume_bar(cmp_json, hv_png_zh, zh=True)
        print(
            f"[runner] Plots (EN+ZH): {pareto_png.name}, {pareto_png_zh.name}, "
            f"{conv_png.name}, {conv_png_zh.name}, {hv_png.name}, {hv_png_zh.name}"
        )
    else:
        print(f"[runner] Plots (EN+ZH): {pareto_png.name}, {pareto_png_zh.name}, {conv_png.name}, {conv_png_zh.name}")


def _append_dataset_history(dataset_root: Path, run_dir: Path, completed_results: List[DSERunResult]) -> None:
    """
    Append all evaluated points from a finished run into a standardized dataset CSV.

    Created/updated under dataset_root:
      - dataset_history.csv / dataset_history_zh.csv  (append-only, clean schema)
      - dataset_meta.json (schema + signature + counts + last_run)

    Per-run provenance remains in run_dir/ (trial folders + comparison/ + plots).
    A strict dataset_signature check prevents mixing incompatible versions:
      nn / dataset_module / weights_path / base_config_path / non-ideal flags.
    """
    import hashlib

    from dse.core import DIM_NAMES, encode_dim_value

    dataset_root.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    if not completed_results:
        print("[runner] dataset-append: no completed results; skip append.")
        return

    # ---- version/signature (must stay homogeneous inside one dataset root) ----
    first_cfg = completed_results[0].run_config
    signature_payload = {
        "nn": first_cfg.nn,
        "dataset_module": first_cfg.dataset_module,
        "weights_path": os.path.abspath(first_cfg.weights_path),
        "base_config_path": os.path.abspath(first_cfg.base_config_path),
        "run_accuracy": bool(first_cfg.run_accuracy),
        "enable_saf": bool(first_cfg.enable_saf),
        "enable_variation": bool(first_cfg.enable_variation),
        "enable_rratio": bool(first_cfg.enable_rratio),
        "fixed_qrange": bool(first_cfg.fixed_qrange),
    }
    signature_str = json.dumps(signature_payload, sort_keys=True, ensure_ascii=False)
    dataset_signature = hashlib.sha1(signature_str.encode("utf-8")).hexdigest()[:12]

    # verify all trials match this signature
    for rr in completed_results:
        rc = rr.run_config
        cur = {
            "nn": rc.nn,
            "dataset_module": rc.dataset_module,
            "weights_path": os.path.abspath(rc.weights_path),
            "base_config_path": os.path.abspath(rc.base_config_path),
            "run_accuracy": bool(rc.run_accuracy),
            "enable_saf": bool(rc.enable_saf),
            "enable_variation": bool(rc.enable_variation),
            "enable_rratio": bool(rc.enable_rratio),
            "fixed_qrange": bool(rc.fixed_qrange),
        }
        if cur != signature_payload:
            raise RuntimeError(
                "dataset-append requires one consistent version/signature per run. "
                "Found mixed configs across trials; split runs by version."
            )

    # ---- clean schema: X / conditions / y / meta / version ----
    x_cols = list(DIM_NAMES)
    cond_cols = ["run_accuracy", "enable_saf", "enable_variation", "enable_rratio", "fixed_qrange"]
    y_cols = ["latency_ns", "energy_nj", "area_um2", "power_w", "accuracy"]
    meta_cols = ["run_id", "trial_dir", "algo", "seed", "eval_index", "phase", "elapsed_s", "is_pareto"]
    ver_cols = ["nn", "dataset_module", "weights_path", "base_config_path", "device", "dataset_signature"]
    out_cols = x_cols + cond_cols + y_cols + meta_cols + ver_cols

    zh = {
        "xbar_size": "交叉阵列尺寸",
        "adc_choice": "ADC档位",
        "dac_choice": "DAC档位",
        "pe_num": "PE阵列规模",
        "tile_connection": "Tile连接方式",
        "inter_tile_bw": "片间带宽",
        "intra_tile_bw": "片内带宽",
        "run_accuracy": "运行条件_精度仿真",
        "enable_saf": "运行条件_SAF",
        "enable_variation": "运行条件_器件变异",
        "enable_rratio": "运行条件_Rratio",
        "fixed_qrange": "运行条件_固定量化范围",
        "latency_ns": "标签_延迟_ns",
        "energy_nj": "标签_能耗_nJ",
        "area_um2": "标签_面积_um2",
        "power_w": "标签_功耗_W",
        "accuracy": "标签_精度",
        "run_id": "元信息_运行ID",
        "trial_dir": "元信息_试验目录",
        "algo": "元信息_算法",
        "seed": "元信息_随机种子",
        "eval_index": "元信息_评估序号",
        "phase": "元信息_阶段",
        "elapsed_s": "元信息_单次耗时_s",
        "is_pareto": "元信息_是否帕累托点",
        "nn": "版本_网络",
        "dataset_module": "版本_数据集模块",
        "weights_path": "版本_权重路径",
        "base_config_path": "版本_SimConfig路径",
        "device": "版本_设备",
        "dataset_signature": "版本_签名",
    }
    out_cols_zh = [zh.get(c, c) for c in out_cols]

    dst = dataset_root / "dataset_history.csv"
    dst_zh = dataset_root / "dataset_history_zh.csv"
    need_header = not dst.exists()
    need_header_zh = not dst_zh.exists()

    # existing meta compatibility check
    meta_path = dataset_root / "dataset_meta.json"
    old_meta: Dict[str, Any] = {}
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                old_meta = json.load(f)
        except Exception:
            old_meta = {}
    old_sig = old_meta.get("dataset_signature")
    if old_sig and old_sig != dataset_signature:
        raise RuntimeError(
            "dataset-append signature mismatch.\n"
            f"existing: {old_sig}\nnew     : {dataset_signature}\n"
            "Use a different --output-root for another dataset version."
        )

    appended = 0
    with open(dst, "a", newline="", encoding="utf-8") as fo, open(dst_zh, "a", newline="", encoding="utf-8") as fozh:
        w = csv.DictWriter(fo, fieldnames=out_cols)
        wzh = csv.writer(fozh)
        if need_header:
            w.writeheader()
        if need_header_zh:
            wzh.writerow(out_cols_zh)

        for rr in completed_results:
            rc = rr.run_config
            trial_dir_name = f"{rc.algo}_seed{rc.seed}"
            for rec in rr.records:
                out_row: Dict[str, Any] = {}
                # X
                for d in x_cols:
                    out_row[d] = encode_dim_value(rec.config.get(d, ""))
                # conditions
                out_row["run_accuracy"] = int(bool(rc.run_accuracy))
                out_row["enable_saf"] = int(bool(rc.enable_saf))
                out_row["enable_variation"] = int(bool(rc.enable_variation))
                out_row["enable_rratio"] = int(bool(rc.enable_rratio))
                out_row["fixed_qrange"] = int(bool(rc.fixed_qrange))
                # y
                out_row["latency_ns"] = rec.latency_ns
                out_row["energy_nj"] = rec.energy_nj
                out_row["area_um2"] = rec.area_um2
                out_row["power_w"] = rec.power_w
                out_row["accuracy"] = "" if rec.accuracy is None else rec.accuracy
                # meta
                out_row["run_id"] = run_id
                out_row["trial_dir"] = trial_dir_name
                out_row["algo"] = rec.algo
                out_row["seed"] = rec.seed
                out_row["eval_index"] = rec.eval_index
                out_row["phase"] = rec.phase
                out_row["elapsed_s"] = rec.elapsed_s
                out_row["is_pareto"] = int(bool(rec.is_pareto))
                # version
                out_row["nn"] = rc.nn
                out_row["dataset_module"] = rc.dataset_module
                out_row["weights_path"] = os.path.abspath(rc.weights_path)
                out_row["base_config_path"] = os.path.abspath(rc.base_config_path)
                out_row["device"] = rc.device
                out_row["dataset_signature"] = dataset_signature

                w.writerow(out_row)
                wzh.writerow([out_row[c] for c in out_cols])
                appended += 1

    total = int(old_meta.get("total_rows", 0) or 0) + appended
    meta = {
        "dataset_root": str(dataset_root),
        "dataset_signature": dataset_signature,
        "dataset_signature_payload": signature_payload,
        "schema_version": "v2_clean_sampling",
        "schema_columns": out_cols,
        "last_run": run_id,
        "last_run_dir": str(run_dir),
        "appended_rows": appended,
        "total_rows": total,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"[runner] dataset-append: +{appended} rows → {dst}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Concurrent DSE runner for MNSIM-2.0",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    cwd = os.getcwd()

    p.add_argument(
        "--algos", nargs="+", default=["nsga2", "mobo"],
        choices=["bo_gp", "nsga2", "mobo", "random"],
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

    p.add_argument(
        "--output-root",
        default=AUTO_OUTPUT_ROOT,
        help=(
            f"Root directory for trials (<algo>_seed<N>/). "
            f"Default {AUTO_OUTPUT_ROOT}: create {_PROJ_ROOT / 'dse_runs' / 'run_<timestamp>'} "
            "each run so plots and CSV are never overwritten. "
            "For --compare-only / --plot-only, pass an existing directory explicitly."
        ),
    )
    p.add_argument(
        "--dataset-append",
        action="store_true",
        help=(
            "Append-only dataset collection mode. Treat --output-root as a persistent dataset root. "
            "Each run writes a new run directory under <output-root>/runs/run_<timestamp>/ (never overwrites), "
            "then appends all history rows into <output-root>/dataset_history.csv and dataset_history_zh.csv."
        ),
    )
    p.add_argument(
        "--no-dataset-append",
        action="store_true",
        help=(
            "Disable auto dataset append for random sampling. "
            "By default, when --algos is exactly [random], dataset append is enabled automatically "
            "and output_root is auto-composed from dataset/nn/weights/simconfig/flags."
        ),
    )

    p.add_argument("--compare-only", action="store_true",
                   help="Skip running algorithms; load existing results from --output-root and regenerate comparison.")

    p.add_argument("--plots", action="store_true",
                   help="Write comparison PNGs after run or --compare-only (pip install matplotlib).")
    p.add_argument("--plot-only", dest="plot_only", action="store_true",
                   help="Only write PNGs from existing results under --output-root; no simulation.")

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Auto behavior: pure random sampling defaults to append-only dataset mode.
    auto_dataset_append = set(args.algos) == {"random"} and (not args.no_dataset_append)
    if auto_dataset_append and not args.dataset_append:
        args.dataset_append = True
        if args.output_root == AUTO_OUTPUT_ROOT:
            args.output_root = str(_auto_dataset_root_from_args(args))
        print(f"[runner] Auto dataset-append enabled for random sampling. output_root={args.output_root}")
        print("[runner] Mode: sampling (random only, append-only dataset)")
    elif set(args.algos) != {"random"}:
        print("[runner] Mode: optimisation/search (bo_gp/nsga2/mobo)")

    if args.output_root == AUTO_OUTPUT_ROOT and (args.plot_only or args.compare_only):
        parser.error(
            f"--plot-only / --compare-only require a concrete existing path; "
            f"do not use default {AUTO_OUTPUT_ROOT}. Example: --output-root dse_runs/run_20260101_120000"
        )

    if args.dataset_append and (args.plot_only or args.compare_only):
        parser.error("--dataset-append cannot be combined with --plot-only / --compare-only.")
    if args.dataset_append and set(args.algos) != {"random"}:
        parser.error("--dataset-append is only allowed with --algos random to keep clean sampling semantics.")

    base_root = _resolve_output_root(args.output_root)
    if args.dataset_append:
        # Always create a new run dir under the dataset root.
        output_root = base_root / "runs" / f"run_{_timestamp()}"
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        output_root = base_root
    compare_dir = output_root / "comparison"

    if args.plot_only:
        if args.compare_only:
            print("[runner] Ignoring --compare-only with --plot-only.")
        write_comparison_plots(output_root)
        return

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
        if args.plots:
            write_comparison_plots(output_root)
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
        print_report_zh(r)

    write_comparison(completed_results, str(compare_dir))
    print(f"\n[runner] Total wall time: {total_wall:.1f}s")
    print(f"[runner] Comparison output: {compare_dir}")
    if args.plots:
        write_comparison_plots(output_root)
    if args.dataset_append:
        _append_dataset_history(base_root, output_root, completed_results)
        print(f"[runner] Dataset root: {base_root}")
        print(f"[runner] This run dir : {output_root}")


if __name__ == "__main__":
    main()
