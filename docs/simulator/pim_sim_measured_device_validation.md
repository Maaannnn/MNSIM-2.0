# `pim_sim` measured-device validation

## Purpose

This note records the **measured-device** validation path for `pim_sim`.

It is intentionally separate from the literature-anchor path:

- **literature anchor**: reproduce MNSIM's published error against external ISSCC chips
- **measured-device anchor**: test whether `pim_sim` matches **our own** wafer data better than an MNSIM-compatible symmetric variation model

This separation avoids mixing our `test_data/` wafer statistics into external-chip claims.

## Method

Script:

- [compare_device_model_fidelity.py](/Users/bytedance/workspace/MNSIM-2.0/validate/compare_device_model_fidelity.py)

Data:

- `test_data/2T1R_cycle/wafer_xy*.csv`

Protocol:

1. Leave one wafer out
2. Fit a **single** symmetric `Device_Variation` on the remaining wafers
3. Fit separate **HRS/LRS CV** values on the remaining wafers
4. Evaluate both models on the held-out wafer
5. Use the held-out wafer mean resistance as the nominal value so the comparison isolates **variation-model fidelity**
6. Apply conservative IQR filtering to exclude SAF-heavy tails from the **primary** metric

## Current outputs

- CSV: [leave_one_wafer_out.csv](/Users/bytedance/workspace/MNSIM-2.0/validate/output/device_fidelity/leave_one_wafer_out.csv)
- Summary: [leave_one_wafer_out_summary.txt](/Users/bytedance/workspace/MNSIM-2.0/validate/output/device_fidelity/leave_one_wafer_out_summary.txt)

## Current result snapshot

Using 15 wafers, `max_rows=50000`, `n_eval_samples=5000`:

- Mean state CV absolute error: `14.5075 -> 1.5299 pct-pts` (`89.45%` reduction)
- Mean normalized Wasserstein distance: `11.6890% -> 3.7919%` (`67.56%` reduction)

State breakdown:

- HRS CV absolute error: `14.5143 -> 2.5998 pct-pts` (`82.09%` reduction)
- HRS normalized Wasserstein: `11.3766% -> 6.7435%` (`40.73%` reduction)
- LRS CV absolute error: `14.5007 -> 0.4601 pct-pts` (`96.83%` reduction)
- LRS normalized Wasserstein: `12.0013% -> 0.8403%` (`93.00%` reduction)

## Interpretation boundary

These numbers support the claim that:

- for **our measured wafer distributions**,
- `pim_sim`'s asymmetric variation model matches reality better than an MNSIM-compatible symmetric Gaussian baseline

These numbers do **not** support the claim that:

- `pim_sim` is already more accurate than MNSIM for **external published chips**

That claim still requires a separate literature-anchor path with chip-specific public parameters.
