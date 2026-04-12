#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract measured device-state summaries from test_data/ and suggest
MNSIM-compatible measured presets.

This script does not modify the DSE search space. It only converts raw test
records into:
  1) auditable summaries close to the original measurements
  2) heuristic static presets that can be plugged into MNSIM later

Example:
  python dse/extras/extract_measured_presets.py
  python dse/extras/extract_measured_presets.py --test-data-dir test_data --output-dir artifacts/dse/testdata_analysis
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace("\ufeff", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_int(value: Any) -> Optional[int]:
    num = _safe_float(value)
    if num is None:
        return None
    return int(num)


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    mean = _mean(values)
    assert mean is not None
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _cv_pct(values: Sequence[float]) -> Optional[float]:
    mean = _mean(values)
    std = _std(values)
    if mean in (None, 0.0) or std is None:
        return None
    return std / mean * 100.0


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _fmt_float(value: Optional[float], digits: int = 6) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _read_csv_dicts(path: Path, *, encoding: str = "utf-8") -> Iterable[Dict[str, str]]:
    with open(path, newline="", encoding=encoding, errors="ignore") as f:
        yield from csv.DictReader(f)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    headers: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                headers.append(key)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


@dataclass
class CycleFileSummary:
    file_name: str
    max_cycle: int
    hrs_mean_ohm: Optional[float]
    hrs_cv_pct: Optional[float]
    lrs_mean_ohm: Optional[float]
    lrs_cv_pct: Optional[float]
    variation_proxy_pct: Optional[float]
    resistance_window_ratio: Optional[float]
    te_mean_pmu: Optional[float]
    be_mean_pmu: Optional[float]
    te_mean_verify: Optional[float]
    be_mean_verify: Optional[float]
    te_pmu_delta_early_late: Optional[float]
    be_pmu_delta_early_late: Optional[float]
    quality_score: Optional[float]
    state: str = ""


def _summarize_cycle_file(path: Path) -> CycleFileSummary:
    curve_pmu: Dict[str, List[float]] = {}
    curve_verify: Dict[str, List[float]] = {}
    curve_rcell: Dict[str, List[float]] = {}
    curve_pmu_by_cycle: Dict[str, List[Tuple[int, float]]] = {}
    max_cycle = 0

    for row in _read_csv_dicts(path):
        curve = str(row.get("Curve Name", "")).strip()
        cyc_num = _safe_int(row.get("Cyc_Num")) or 0
        pmu = _safe_float(row.get("PMU Result"))
        verify = _safe_float(row.get("verify pulse count"))
        rcell = _safe_float(row.get("R_cell"))
        if not curve:
            continue
        max_cycle = max(max_cycle, cyc_num)
        if pmu is not None:
            curve_pmu.setdefault(curve, []).append(pmu)
        if verify is not None:
            curve_verify.setdefault(curve, []).append(verify)
        if rcell is not None and rcell > 0:
            curve_rcell.setdefault(curve, []).append(rcell)
        if pmu is not None and cyc_num > 0:
            curve_pmu_by_cycle.setdefault(curve, []).append((cyc_num, pmu))

    hrs_values = curve_rcell.get("teERS", [])
    lrs_values = curve_rcell.get("bePGM", [])
    hrs_mean = _mean(hrs_values)
    lrs_mean = _mean(lrs_values)
    te_verify = _mean(curve_verify.get("teERS", []))
    be_verify = _mean(curve_verify.get("bePGM", []))
    te_mean_pmu = _mean(curve_pmu.get("teERS", []))
    be_mean_pmu = _mean(curve_pmu.get("bePGM", []))
    window_ratio = None
    if hrs_mean and lrs_mean:
        window_ratio = hrs_mean / lrs_mean
    variation_components = [x for x in (_cv_pct(hrs_values), _cv_pct(lrs_values)) if x is not None and x >= 0]
    variation_proxy = _quantile(variation_components, 0.5) if variation_components else None
    late_start = max(1, max_cycle - 50)

    def _window_mean(curve: str, *, start: Optional[int] = None, end: Optional[int] = None) -> Optional[float]:
        values = []
        for cyc_num, pmu in curve_pmu_by_cycle.get(curve, []):
            if start is not None and cyc_num < start:
                continue
            if end is not None and cyc_num > end:
                continue
            values.append(pmu)
        return _mean(values)

    te_early = _window_mean("teERS", end=50)
    te_late = _window_mean("teERS", start=late_start)
    be_early = _window_mean("bePGM", end=50)
    be_late = _window_mean("bePGM", start=late_start)
    te_delta = None if te_early is None or te_late is None else te_late - te_early
    be_delta = None if be_early is None or be_late is None else be_late - be_early

    quality_score = None
    if window_ratio is not None:
        quality_score = (
            window_ratio
            - 0.015 * (be_verify or 0.0)
            - 0.20 * abs(be_delta or 0.0)
            - 0.10 * abs(te_delta or 0.0)
        )

    return CycleFileSummary(
        file_name=path.name,
        max_cycle=max_cycle,
        hrs_mean_ohm=hrs_mean,
        hrs_cv_pct=_cv_pct(hrs_values),
        lrs_mean_ohm=lrs_mean,
        lrs_cv_pct=_cv_pct(lrs_values),
        variation_proxy_pct=variation_proxy,
        resistance_window_ratio=window_ratio,
        te_mean_pmu=te_mean_pmu,
        be_mean_pmu=be_mean_pmu,
        te_mean_verify=te_verify,
        be_mean_verify=be_verify,
        te_pmu_delta_early_late=te_delta,
        be_pmu_delta_early_late=be_delta,
        quality_score=quality_score,
    )


def _label_cycle_states(items: List[CycleFileSummary]) -> None:
    scores = [item.quality_score for item in items if item.quality_score is not None]
    q1 = _quantile(scores, 1.0 / 3.0)
    q2 = _quantile(scores, 2.0 / 3.0)
    for item in items:
        if item.quality_score is None or q1 is None or q2 is None:
            item.state = "cycle_unknown"
        elif item.quality_score <= q1:
            item.state = "cycle_weak"
        elif item.quality_score <= q2:
            item.state = "cycle_typical"
        else:
            item.state = "cycle_strong"


def _aggregate_cycle_states(items: List[CycleFileSummary]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[CycleFileSummary]] = {}
    for item in items:
        grouped.setdefault(item.state, []).append(item)

    rows: List[Dict[str, Any]] = []
    for state, members in sorted(grouped.items()):
        hrs_values = [x.hrs_mean_ohm for x in members if x.hrs_mean_ohm is not None]
        lrs_values = [x.lrs_mean_ohm for x in members if x.lrs_mean_ohm is not None]
        verify_values = [x.be_mean_verify for x in members if x.be_mean_verify is not None]
        raw_variation_values = [x.variation_proxy_pct for x in members if x.variation_proxy_pct is not None]
        capped_variation_values = [min(v, 100.0) for v in raw_variation_values]
        drift_values = [
            abs(x.be_pmu_delta_early_late)
            for x in members
            if x.be_pmu_delta_early_late is not None
        ]
        hrs_mean = _mean(hrs_values)
        lrs_mean = _mean(lrs_values)
        window_ratio = None
        if hrs_mean and lrs_mean:
            window_ratio = hrs_mean / lrs_mean
        rows.append(
            {
                "state": state,
                "source_family": "2T1R_cycle",
                "member_count": len(members),
                "member_files": ", ".join(x.file_name for x in members),
                "hrs_mean_ohm": _fmt_float(hrs_mean, 2),
                "lrs_mean_ohm": _fmt_float(lrs_mean, 2),
                "resistance_window_ratio": _fmt_float(window_ratio, 4),
                "device_variation_pct_raw_median": _fmt_float(_quantile(raw_variation_values, 0.5), 3),
                "device_variation_pct_suggested": _fmt_float(_quantile(capped_variation_values, 0.5), 3),
                "mean_be_verify_pulses": _fmt_float(_mean(verify_values), 3),
                "mean_abs_be_drift_pmu": _fmt_float(_mean(drift_values), 3),
                "note": "Static snapshot derived from real cycle data; good candidate for measured preset replacement.",
            }
        )
    return rows


def _analyze_retention(test_data_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    phase_rows: List[Dict[str, Any]] = []
    retention_dir = test_data_dir / "2T1R_retention"

    for prefix in ("read2", "read9"):
        pre_path = retention_dir / f"{prefix}prebake.csv"
        post_path = retention_dir / f"{prefix}postbake.csv"

        def _load_read_map(path: Path) -> Dict[Tuple[int, int], float]:
            values: Dict[Tuple[int, int], float] = {}
            for row in _read_csv_dicts(path, encoding="utf-8-sig"):
                r = _safe_int(row.get("row"))
                c = _safe_int(row.get("col"))
                v = _safe_float(row.get("pmuresult"))
                if r is None or c is None or v is None:
                    continue
                values[(r, c)] = v
            return values

        pre_map = _load_read_map(pre_path)
        post_map = _load_read_map(post_path)
        common_keys = sorted(set(pre_map).intersection(post_map))
        deltas = [post_map[k] - pre_map[k] for k in common_keys]
        scale = None
        pre_mean = _mean(list(pre_map.values()))
        post_mean = _mean(list(post_map.values()))
        if pre_mean not in (None, 0.0) and post_mean is not None:
            scale = post_mean / pre_mean
        rows.append(
            {
                "retention_view": prefix,
                "pair_count": len(common_keys),
                "pre_mean_pmu": _fmt_float(pre_mean, 4),
                "post_mean_pmu": _fmt_float(post_mean, 4),
                "post_over_pre_scale": _fmt_float(scale, 4),
                "delta_mean_pmu": _fmt_float(_mean(deltas), 4),
                "delta_std_pmu": _fmt_float(_std(deltas), 4),
                "delta_min_pmu": _fmt_float(min(deltas) if deltas else None, 4),
                "delta_max_pmu": _fmt_float(max(deltas) if deltas else None, 4),
            }
        )

    for path in sorted(retention_dir.glob("*pre.csv")):
        if path.name.startswith("read"):
            continue
        i_before: List[float] = []
        i_after: List[float] = []
        flip_count = 0
        pass_count = 0
        total = 0
        for row in _read_csv_dicts(path):
            before = _safe_float(row.get(" I_before"))
            after = _safe_float(row.get(" I_after"))
            no_change = _safe_int(row.get(" state_no_change"))
            passed = _safe_int(row.get(" pass"))
            if before is None or after is None or no_change is None or passed is None:
                continue
            total += 1
            i_before.append(before)
            i_after.append(after)
            flip_count += 0 if no_change else 1
            pass_count += passed
        phase_rows.append(
            {
                "file_name": path.name,
                "sample_count": total,
                "i_before_mean": _fmt_float(_mean(i_before), 4),
                "i_after_mean": _fmt_float(_mean(i_after), 4),
                "delta_mean": _fmt_float(
                    None if not i_before or not i_after else _mean([a - b for a, b in zip(i_after, i_before)]),
                    4,
                ),
                "flip_rate": _fmt_float(None if total == 0 else flip_count / total, 6),
                "pass_rate": _fmt_float(None if total == 0 else pass_count / total, 6),
            }
        )
    return rows, phase_rows


def _summarize_retention_phases(phase_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scored = []
    for row in phase_rows:
        flip_rate = _safe_float(row.get("flip_rate"))
        pass_rate = _safe_float(row.get("pass_rate"))
        if flip_rate is None or pass_rate is None:
            continue
        scored.append((row, pass_rate - flip_rate))
    values = [score for _, score in scored]
    q1 = _quantile(values, 1.0 / 3.0)
    q2 = _quantile(values, 2.0 / 3.0)
    out: List[Dict[str, Any]] = []
    for row, score in scored:
        if q1 is None or q2 is None:
            phase = "retention_unknown"
        elif score <= q1:
            phase = "retention_unstable"
        elif score <= q2:
            phase = "retention_typical"
        else:
            phase = "retention_stable"
        out.append(
            {
                "retention_phase": phase,
                "file_name": row["file_name"],
                "sample_count": row["sample_count"],
                "flip_rate": row["flip_rate"],
                "pass_rate": row["pass_rate"],
                "score": _fmt_float(score, 6),
                "note": "Retention phases are stress labels. They should be used as robustness conditions, not as direct SAF replacements.",
            }
        )
    return out


def _analyze_arbitrary_write(test_data_dir: Path) -> Tuple[List[Dict[str, Any]], Optional[float], Optional[float]]:
    out: List[Dict[str, Any]] = []
    failure_rates: List[float] = []
    abs_errors: List[float] = []
    for path in sorted((test_data_dir / "1T1R_任意值写入").glob("*.csv")):
        total = None
        success = None
        failure = None
        errors: List[float] = []
        target_levels = set()
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f if line.strip()]
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if line.startswith("Device Count:"):
                total = _safe_int(line.split("\t")[-1])
            elif line.startswith("Successfully Count:"):
                success = _safe_int(line.split("\t")[-1])
            elif line.startswith("Failure Count:"):
                failure = _safe_int(line.split("\t")[-1])
            elif line.startswith("CSXROW") and idx + 1 < len(lines) and lines[idx + 1].startswith("Resistance"):
                actual = _safe_float(line.split(",")[-1])
                target = _safe_float(lines[idx + 1].split(",")[-1])
                if actual is not None and target is not None:
                    errors.append(abs(actual - target))
                    target_levels.add(target)
                idx += 1
            idx += 1
        failure_rate = None
        if total not in (None, 0) and failure is not None:
            failure_rate = failure / total
            failure_rates.append(failure_rate)
        abs_errors.extend(errors)
        out.append(
            {
                "file_name": path.name,
                "device_count": total or "",
                "success_count": success or "",
                "failure_count": failure or "",
                "failure_rate": _fmt_float(failure_rate, 6),
                "mean_abs_error": _fmt_float(_mean(errors), 6),
                "p95_abs_error": _fmt_float(_quantile(errors, 0.95), 6),
                "target_levels": ", ".join(str(int(x)) if float(x).is_integer() else str(x) for x in sorted(target_levels)),
            }
        )
    return out, _mean(failure_rates), _mean(abs_errors)


def _suggest_measured_presets(
    cycle_state_rows: List[Dict[str, Any]],
    retention_phase_rows: List[Dict[str, Any]],
    write_failure_rate: Optional[float],
) -> List[Dict[str, Any]]:
    presets: List[Dict[str, Any]] = []
    retention_counts: Dict[str, int] = {}
    for row in retention_phase_rows:
        retention_counts[row["retention_phase"]] = retention_counts.get(row["retention_phase"], 0) + 1
    dominant_retention = max(retention_counts.items(), key=lambda x: x[1])[0] if retention_counts else "retention_typical"

    for row in cycle_state_rows:
        hrs = _safe_float(row.get("hrs_mean_ohm"))
        lrs = _safe_float(row.get("lrs_mean_ohm"))
        variation = _safe_float(row.get("device_variation_pct_suggested"))
        state = str(row["state"])
        if hrs is None or lrs is None:
            continue
        presets.append(
            {
                "preset_name": f"meas_{state}",
                "source_family": row["source_family"],
                "source_members": row["member_files"],
                "device_resistance": f"{hrs:.2f},{lrs:.2f}",
                "device_variation": _fmt_float(variation, 3),
                "device_saf_heuristic": _fmt_float(None if write_failure_rate is None else write_failure_rate * 100.0, 4),
                "resistance_window_ratio": row["resistance_window_ratio"],
                "default_retention_phase": dominant_retention,
                "simconfig_patch_json": json.dumps(
                    {
                        "Device level": {
                            "Device_Resistance": f"{hrs:.2f},{lrs:.2f}",
                            "Device_Variation": None if variation is None else round(variation, 3),
                            "Device_SAF": None if write_failure_rate is None else f"{write_failure_rate * 100.0:.4f},{write_failure_rate * 100.0:.4f}",
                        }
                    },
                    ensure_ascii=False,
                ),
                "note": "SAF is only a heuristic lower-bound from write-failure data. Retention phases should be modeled as separate stress runs.",
            }
        )
    return presets


def _build_summary_payload(
    cycle_rows: List[Dict[str, Any]],
    cycle_state_rows: List[Dict[str, Any]],
    retention_rows: List[Dict[str, Any]],
    retention_phase_rows: List[Dict[str, Any]],
    arbitrary_rows: List[Dict[str, Any]],
    measured_presets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "cycle_files": cycle_rows,
        "cycle_states": cycle_state_rows,
        "retention_read_views": retention_rows,
        "retention_phases": retention_phase_rows,
        "arbitrary_write": arbitrary_rows,
        "measured_presets": measured_presets,
        "usage_note": (
            "Use measured_presets as static device snapshots in MNSIM. "
            "Use retention_phases as separate robustness conditions rather than "
            "direct SAF substitution."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract measured presets from test_data/")
    parser.add_argument("--test-data-dir", default="test_data", help="Directory containing raw measurement CSVs.")
    parser.add_argument("--output-dir", default="artifacts/dse/testdata_analysis", help="Directory for generated summaries.")
    args = parser.parse_args()

    test_data_dir = Path(args.test_data_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cycle_items = [_summarize_cycle_file(path) for path in sorted((test_data_dir / "2T1R_cycle").glob("wafer_xy*.csv"))]
    _label_cycle_states(cycle_items)

    cycle_rows = [
        {
            "file_name": item.file_name,
            "state": item.state,
            "max_cycle": item.max_cycle,
            "hrs_mean_ohm": _fmt_float(item.hrs_mean_ohm, 2),
            "hrs_cv_pct": _fmt_float(item.hrs_cv_pct, 4),
            "lrs_mean_ohm": _fmt_float(item.lrs_mean_ohm, 2),
            "lrs_cv_pct": _fmt_float(item.lrs_cv_pct, 4),
            "variation_proxy_pct": _fmt_float(item.variation_proxy_pct, 4),
            "resistance_window_ratio": _fmt_float(item.resistance_window_ratio, 4),
            "te_mean_pmu": _fmt_float(item.te_mean_pmu, 4),
            "be_mean_pmu": _fmt_float(item.be_mean_pmu, 4),
            "te_mean_verify": _fmt_float(item.te_mean_verify, 4),
            "be_mean_verify": _fmt_float(item.be_mean_verify, 4),
            "te_pmu_delta_early_late": _fmt_float(item.te_pmu_delta_early_late, 4),
            "be_pmu_delta_early_late": _fmt_float(item.be_pmu_delta_early_late, 4),
            "quality_score": _fmt_float(item.quality_score, 6),
        }
        for item in cycle_items
    ]
    cycle_state_rows = _aggregate_cycle_states(cycle_items)

    retention_rows, retention_phase_base = _analyze_retention(test_data_dir)
    retention_phase_rows = _summarize_retention_phases(retention_phase_base)

    arbitrary_rows, write_failure_rate, _ = _analyze_arbitrary_write(test_data_dir)
    measured_presets = _suggest_measured_presets(cycle_state_rows, retention_phase_rows, write_failure_rate)

    _write_csv(output_dir / "cycle_wafer_summary.csv", cycle_rows)
    _write_csv(output_dir / "cycle_state_summary.csv", cycle_state_rows)
    _write_csv(output_dir / "retention_read_summary.csv", retention_rows)
    _write_csv(output_dir / "retention_phase_summary.csv", retention_phase_rows)
    _write_csv(output_dir / "arbitrary_write_summary.csv", arbitrary_rows)
    _write_csv(output_dir / "measured_presets.csv", measured_presets)
    _write_json(
        output_dir / "summary.json",
        _build_summary_payload(
            cycle_rows=cycle_rows,
            cycle_state_rows=cycle_state_rows,
            retention_rows=retention_rows,
            retention_phase_rows=retention_phase_rows,
            arbitrary_rows=arbitrary_rows,
            measured_presets=measured_presets,
        ),
    )

    print(f"[measured-presets] cycle summary -> {output_dir / 'cycle_wafer_summary.csv'}")
    print(f"[measured-presets] cycle states -> {output_dir / 'cycle_state_summary.csv'}")
    print(f"[measured-presets] retention phases -> {output_dir / 'retention_phase_summary.csv'}")
    print(f"[measured-presets] presets -> {output_dir / 'measured_presets.csv'}")
    print(f"[measured-presets] summary -> {output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
