#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Dict, List, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from dse_multi_utils import SPACE


def load_dataset(csv_path: str) -> Tuple[np.ndarray, Dict[str, np.ndarray], List[str]]:
    dim_names = list(SPACE.keys())
    X, y_lat, y_en, y_ar, y_pow, y_acc = [], [], [], [], [], []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            x = [float(r[f"{d}__idx"]) for d in dim_names]
            X.append(x)
            y_lat.append(float(r["latency_ns"]))
            y_en.append(float(r["energy_nj"]))
            y_ar.append(float(r["area_um2"]))
            y_pow.append(float(r["power_w"]))
            y_acc.append(float(r["accuracy"]))
    ys = {
        "latency_ns": np.array(y_lat, dtype=float),
        "energy_nj": np.array(y_en, dtype=float),
        "area_um2": np.array(y_ar, dtype=float),
        "power_w": np.array(y_pow, dtype=float),
        "accuracy": np.array(y_acc, dtype=float),
    }
    return np.array(X, dtype=float), ys, dim_names


def main() -> None:
    parser = argparse.ArgumentParser(description="Train surrogate models from offline MNSIM dataset")
    cwd = os.getcwd()
    parser.add_argument("--dataset-csv", default=os.path.join(cwd, "surrogate_data", "dataset.csv"))
    parser.add_argument("--accuracy-threshold", type=float, default=0.90)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default=os.path.join(cwd, "surrogate_models"))
    args = parser.parse_args()

    X, ys, dim_names = load_dataset(args.dataset_csv)
    os.makedirs(args.output_dir, exist_ok=True)

    idx = np.arange(X.shape[0])
    tr_idx, te_idx = train_test_split(idx, test_size=args.test_size, random_state=args.seed)
    Xtr, Xte = X[tr_idx], X[te_idx]

    regressors = {}
    report = {"regression": {}, "classification": {}}
    for name in ["latency_ns", "energy_nj", "area_um2", "power_w", "accuracy"]:
        ytr, yte = ys[name][tr_idx], ys[name][te_idx]
        rf = RandomForestRegressor(
            n_estimators=300,
            random_state=args.seed,
            n_jobs=-1,
        )
        rf.fit(Xtr, ytr)
        pred = rf.predict(Xte)
        regressors[name] = rf
        report["regression"][name] = {
            "mae": float(mean_absolute_error(yte, pred)),
            "r2": float(r2_score(yte, pred)),
        }

    y_cls = (ys["accuracy"] >= args.accuracy_threshold).astype(int)
    ytr_c, yte_c = y_cls[tr_idx], y_cls[te_idx]
    clf = RandomForestClassifier(
        n_estimators=300,
        random_state=args.seed,
        n_jobs=-1,
        class_weight="balanced",
    )
    clf.fit(Xtr, ytr_c)
    pred_c = clf.predict(Xte)
    report["classification"]["acc_feasible"] = {
        "accuracy": float(accuracy_score(yte_c, pred_c)),
        "f1": float(f1_score(yte_c, pred_c, zero_division=0)),
        "threshold": args.accuracy_threshold,
    }

    model_obj = {
        "dim_names": dim_names,
        "space_values": {k: SPACE[k]["values"] for k in dim_names},
        "regressors": regressors,
        "classifier": clf,
        "accuracy_threshold": args.accuracy_threshold,
    }
    model_path = os.path.join(args.output_dir, "surrogate.joblib")
    joblib.dump(model_obj, model_path)

    report_path = os.path.join(args.output_dir, "train_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=== Surrogate Training Done ===")
    print(f"model : {model_path}")
    print(f"report: {report_path}")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
