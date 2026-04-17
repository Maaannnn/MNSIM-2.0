"""
pim_sim.array.ir_drop
=====================
Input-pattern-aware IR-drop accuracy correction for RRAM crossbar arrays.

Background
----------
MNSIM's main evaluation path (Weight_update.py / evaluate_config) has NO
IR-drop correction.  Crossbar.py uses a simplified wire_latency formula
and Crossbar_accuracy.py (unused in DSE) models only a linear row-offset
correction.

Physics
-------
For an N-row crossbar with word-line wire resistance R_wire_segment per
cell pitch, the voltage seen at row i (0-indexed from top) is approximately:

    V_eff(i) ≈ V_in × (1 - α × i/N)

where α is the IR-drop fraction:

    α = N × R_wire_segment / R_device_avg

This first-order model assumes:
  - All columns are read simultaneously (worst-case input pattern)
  - Load resistance >> R_wire_segment (true for RRAM R ≈ kΩ, wire ≈ Ω)

The resulting error in column current sum:
    ΔI_col / I_col_ideal ≈ α/2 (mean row IR-drop is α/2 × V_in)

This shifts the effective weight value by a factor of (1 - α/2), which
is equivalent to scaling each row's contribution by its row position.

For accuracy modelling we apply a per-row multiplicative correction to
the quantised conductance values before evaluation.

Usage
-----
    from pim_sim.array.ir_drop import IRDropModel

    model = IRDropModel(
        xbar_rows=128,
        wire_resistance_per_cell_ohm=0.5,    # Ω per cell pitch on WL
        device_resistance_avg_ohm=5000.0,    # typical mid-state R
    )
    # scale: shape (xbar_rows,)  row 0 = top (least drop), row N-1 = worst
    row_scales = model.row_scale_factors()
    # Apply to weights before accuracy evaluation
    corrected_weight = weight * row_scales[:, np.newaxis]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class IRDropModel:
    """First-order per-row IR-drop correction for RRAM crossbars.

    Parameters
    ----------
    xbar_rows:
        Number of rows in the crossbar (e.g. 128 or 256).
    wire_resistance_per_cell_ohm:
        Parasitic resistance per cell pitch along the word line (Ω).
        Typical values: 0.1–2 Ω for Cu interconnect at sub-100nm nodes.
        Default 0.5 Ω is a conservative estimate for 28 nm.
    device_resistance_avg_ohm:
        Average device resistance used for normalisation.
        Should match the geometric mean of HRS and LRS:
            R_avg = sqrt(R_HRS × R_LRS)
        Default 5000 Ω covers typical RRAM (HRS≈10kΩ, LRS≈2.5kΩ).
    input_voltage:
        Read voltage (V).  Used only for energy estimation (not accuracy).
    """

    xbar_rows: int = 128
    wire_resistance_per_cell_ohm: float = 0.5
    device_resistance_avg_ohm: float = 5000.0
    input_voltage: float = 0.2

    def ir_drop_fraction(self) -> float:
        """Return α = N × R_wire / R_device_avg (dimensionless).

        α ≈ 0 means negligible IR-drop; α ≈ 1 means severe degradation.
        For a 128-row array: α = 128 × 0.5 / 5000 = 0.0128 (1.3%)
        For a 512-row array: α = 512 × 0.5 / 5000 = 0.0512 (5.1%)
        """
        return (
            self.xbar_rows
            * self.wire_resistance_per_cell_ohm
            / self.device_resistance_avg_ohm
        )

    def row_scale_factors(self) -> np.ndarray:
        """Return per-row voltage scale factors of shape (xbar_rows,).

        row_scale[i] = 1 - alpha * i / N
          i=0 (top row): no drop → scale = 1.0
          i=N-1 (bottom): maximum drop → scale = 1 - alpha*(N-1)/N

        Scales are clipped to [0.5, 1.0] to avoid unphysical values when
        α is unrealistically large.
        """
        n = self.xbar_rows
        alpha = self.ir_drop_fraction()
        i = np.arange(n, dtype=float)
        scales = 1.0 - alpha * i / n
        return np.clip(scales, 0.5, 1.0)

    def apply_to_weight_matrix(self, weight_matrix: np.ndarray) -> np.ndarray:
        """Apply row-wise IR-drop scale to a 2-D weight/conductance matrix.

        Parameters
        ----------
        weight_matrix:
            Shape (xbar_rows, xbar_cols) — quantised conductance values.
            Rows correspond to word-line rows (row 0 = smallest drop).

        Returns
        -------
        np.ndarray
            Scaled weight matrix, same shape.
        """
        if weight_matrix.ndim != 2:
            raise ValueError(
                f"weight_matrix must be 2-D, got shape {weight_matrix.shape}"
            )
        n_rows = weight_matrix.shape[0]
        if n_rows != self.xbar_rows:
            # Rescale model on the fly for mismatched tile sizes
            scales = self._row_scales_for_n(n_rows)
        else:
            scales = self.row_scale_factors()
        return weight_matrix * scales[:, np.newaxis]

    def _row_scales_for_n(self, n: int) -> np.ndarray:
        """Compute scale factors for an arbitrary row count n."""
        alpha = self.ir_drop_fraction()
        i = np.arange(n, dtype=float)
        return np.clip(1.0 - alpha * i / n, 0.5, 1.0)

    def mean_accuracy_loss_pct(self) -> float:
        """Estimate mean accuracy loss % from IR-drop (analytical).

        Accuracy loss ≈ α/2 × 100%  (mean row under-reads by α/2 × V_in).
        This is a rough upper bound; real networks are partially resilient.
        """
        return self.ir_drop_fraction() / 2.0 * 100.0

    def summary(self) -> dict:
        alpha = self.ir_drop_fraction()
        return {
            "model": "ir_drop_first_order",
            "xbar_rows": self.xbar_rows,
            "wire_resistance_per_cell_ohm": self.wire_resistance_per_cell_ohm,
            "device_resistance_avg_ohm": self.device_resistance_avg_ohm,
            "ir_drop_fraction_alpha": round(alpha, 5),
            "mean_accuracy_loss_pct_upper_bound": round(
                self.mean_accuracy_loss_pct(), 3
            ),
        }
