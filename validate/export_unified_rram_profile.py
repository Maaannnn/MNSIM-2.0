#!/usr/bin/env python3
"""
Export a normalised RRAM profile as JSON.

Examples
--------
python validate/export_unified_rram_profile.py \
    --source literature --profile-id rram_isscc2020_33p2

python validate/export_unified_rram_profile.py \
    --source measured --profile-id typical_robust \
    --output validate/output/profile_schema/measured_typical_robust.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pim_sim.rram_profile import load_unified_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        required=True,
        choices=("literature", "measured"),
        help="Profile source family.",
    )
    parser.add_argument(
        "--profile-id",
        required=True,
        help="Registered literature chip id or measured preset/wafer id.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path. If omitted, prints to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = load_unified_profile(args.source, args.profile_id)
    payload = json.dumps(profile.to_dict(), indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
