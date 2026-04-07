#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED — compare_dse_results.py

This script is kept for backward compatibility.
Comparison is now built into run_dse.py and produces:
  <output-root>/comparison/comparison.csv
  <output-root>/comparison/comparison_summary.csv
  <output-root>/comparison/comparison.json
  <output-root>/comparison/report.txt

To regenerate the comparison from existing results:
  python run_dse.py --compare-only --output-root <output-root>
"""
import warnings
warnings.warn(
    "compare_dse_results.py is deprecated. "
    "Use: python run_dse.py --compare-only --output-root <dir>",
    DeprecationWarning,
    stacklevel=2,
)

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from run_dse import load_results_from_dir, _apply_global_hv
from dse.output import write_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="[DEPRECATED] Compare DSE results — use run_dse.py --compare-only")
    parser.add_argument("--output-root", required=True, help="Directory containing <algo>_seed<N>/ subdirectories.")
    parser.add_argument("--compare-dir", default=None, help="Output directory for comparison files. Default: <output-root>/comparison/")
    args = parser.parse_args()

    output_root = args.output_root
    compare_dir = args.compare_dir or os.path.join(output_root, "comparison")

    print(f"Loading results from {output_root} ...")
    results = load_results_from_dir(output_root)
    if not results:
        print("No results found.")
        sys.exit(1)

    _, results = _apply_global_hv(results)
    write_comparison(results, compare_dir)
    print(f"Comparison written to {compare_dir}")


if __name__ == "__main__":
    main()
