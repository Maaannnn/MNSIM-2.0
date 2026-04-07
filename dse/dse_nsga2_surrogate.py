#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED — dse_nsga2_surrogate.py

This entry point is kept for backward compatibility.
The algorithm implementation has moved to dse/algorithms/nsga2.py.

Recommended replacement:
  python dse/run_dse.py --algos nsga2 --seeds 42 --budget 24 ...
"""
import warnings
warnings.warn(
    "dse_nsga2_surrogate.py is deprecated. Use: python dse/run_dse.py --algos nsga2",
    DeprecationWarning,
    stacklevel=2,
)

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dse.algorithms.nsga2 import run
from dse.output import RunConfig, print_report, write_all


def main() -> None:
    cwd = os.getcwd()
    parser = argparse.ArgumentParser(description="[DEPRECATED] NSGA-II DSE — use dse/run_dse.py instead")
    parser.add_argument("--base-config", default=os.path.join(cwd, "SimConfig.ini"))
    parser.add_argument("--weights", default=os.path.join(cwd, "cifar10_vgg8_params.pth"))
    parser.add_argument("--nn", default="vgg8")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--init-evals", type=int, default=20)
    parser.add_argument("--evals-per-gen", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--run-accuracy", action="store_true")
    parser.add_argument("--enable-saf", action="store_true", default=True)
    parser.add_argument("--enable-variation", action="store_true", default=False)
    parser.add_argument("--enable-rratio", action="store_true", default=False)
    parser.add_argument("--fixed-qrange", action="store_true", default=False)
    parser.add_argument("--output-dir", default=os.path.join(cwd, "dse_nsga2_surrogate_results"))
    args = parser.parse_args()

    budget = args.init_evals + args.generations * args.evals_per_gen

    cfg = RunConfig(
        algo="nsga2",
        seed=args.seed,
        budget=budget,
        init_evals=args.init_evals,
        nn=args.nn,
        weights_path=args.weights,
        base_config_path=args.base_config,
        run_accuracy=args.run_accuracy,
        enable_saf=args.enable_saf,
        enable_variation=args.enable_variation,
        enable_rratio=args.enable_rratio,
        fixed_qrange=args.fixed_qrange,
        device=args.device,
        algo_kwargs={
            "population": args.population,
            "evals_per_gen": args.evals_per_gen,
        },
    )

    result = run(cfg)
    write_all(result, args.output_dir)
    print_report(result)


if __name__ == "__main__":
    main()
