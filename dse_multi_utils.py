#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED — dse_multi_utils.py

This file is kept for backward compatibility only.
All symbols are re-exported from the canonical locations:

  dse.core    → SPACE, EvalResult, evaluate_config, write_temp_config
  dse.metrics → pareto_indices, dominates, obj_vector, weighted_log_objective

Migrate your imports:
  OLD: from dse_multi_utils import SPACE, evaluate_config, pareto_indices
  NEW: from dse.core import SPACE, evaluate_config
       from dse.metrics import pareto_indices
"""
import warnings
warnings.warn(
    "dse_multi_utils is deprecated. Import from dse.core and dse.metrics instead.",
    DeprecationWarning,
    stacklevel=2,
)

from dse.core import (  # noqa: F401
    SPACE,
    DIM_NAMES,
    EvalResult,
    evaluate_config,
    write_temp_config,
    encode_dim_value,
    decode_dim_value,
)
from dse.metrics import (  # noqa: F401
    dominates,
    pareto_indices,
    scalarize_log as weighted_log_objective,
)


def obj_vector(res: EvalResult):
    """Compatibility shim — use res.obj_vector() directly."""
    return res.obj_vector()
