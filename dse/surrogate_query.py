#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

import joblib
import numpy as np


def parse_config_arg(config_str: str) -> Dict[str, Any]:
    cfg = json.loads(config_str)
    if not isinstance(cfg, dict):
        raise ValueError("--config-json must be a JSON object")
    return cfg


def normalize_value(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(v)
    return v


def main() -> None:
    parser = argparse.ArgumentParser(description="Query trained surrogate model (ms-level prediction)")
    cwd = os.getcwd()
    parser.add_argument("--model", default=os.path.join(cwd, "surrogate_models", "surrogate.joblib"))
    parser.add_argument(
        "--config-json",
        required=True,
        help='JSON object, e.g. \'{"xbar_size":[256,256],"adc_choice":6,"dac_choice":1,"pe_num":[4,4],"tile_connection":2,"inter_tile_bw":20,"intra_tile_bw":1024}\'',
    )
    args = parser.parse_args()

    model_obj = joblib.load(args.model)
    dim_names = model_obj["dim_names"]
    space_values = model_obj["space_values"]

    cfg = parse_config_arg(args.config_json)
    x = []
    for d in dim_names:
        if d not in cfg:
            raise ValueError(f"Missing key in config-json: {d}")
        vv = normalize_value(cfg[d])
        values = [normalize_value(v) for v in space_values[d]]
        if vv not in values:
            raise ValueError(f"Invalid value for {d}: {cfg[d]}, allowed={space_values[d]}")
        x.append(float(values.index(vv)))
    X = np.array([x], dtype=float)

    out = {}
    for name, reg in model_obj["regressors"].items():
        out[f"pred_{name}"] = float(reg.predict(X)[0])

    clf = model_obj["classifier"]
    if hasattr(clf, "predict_proba"):
        prob = float(clf.predict_proba(X)[0][1])
    else:
        prob = float(clf.predict(X)[0])
    out["pred_acc_feasible_prob"] = prob
    out["acc_threshold"] = float(model_obj.get("accuracy_threshold", 0.9))
    out["input_config"] = cfg

    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
