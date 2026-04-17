# pim_sim — Enhancement Layer TODO & Progress

> **Purpose**: Drop-in accuracy/PPA enhancement layer for MNSIM.
> Fills three specific gaps in MNSIM's default models without forking the simulator.
>
> **Integration point**: `dse/core.py:evaluate_config` — pass `pim_sim_model=<DeviceModel>` to activate.

---

## Status Overview

| Module | Status | Notes |
|---|---|---|
| `pim_sim/device/model.py` | ✅ Done | SymmetricGaussianModel, AsymmetricGaussianModel, EmpiricalDeviceModel |
| `pim_sim/device/calibrate.py` | ✅ Done | calibrate_from_wafer_csv, calibrate_from_measured_presets_csv |
| `pim_sim/array/ir_drop.py` | ✅ Done | IRDropModel — first-order row-wise IR-drop correction |
| `pim_sim/array/adc_model.py` | ✅ Done | WaldenADCModel — parametric Walden FOM ADC |
| `pim_sim/accuracy/weight_inject.py` | ✅ Done | pim_sim_weight_inject — drop-in for weight_update() |
| `pim_sim/ppa/estimator.py` | ✅ Done | adc_ppa_delta, parametric_adc_sweep |
| `dse/core.py` modification | ✅ Done | evaluate_config gains pim_sim_model + ir_drop_model params |
| `validate/calibrate_from_testdata.py` | ✅ Done | Validate calibration against wafer CSV |
| `validate/compare_accuracy_models.py` | ✅ Done | MNSIM vs pim_sim accuracy comparison |
| `validate/sweep_xbar_sensitivity.py` | ✅ Done | IR-drop sensitivity vs array size |
| `validate/compare_adc_models.py` | ✅ Done | MNSIM lookup vs Walden FOM parametric |

---

## Gap 1: Asymmetric Device Variation

### Problem
MNSIM `Weight_update.py` line 41:
```python
temp_resistance = np.random.normal(loc=0, scale=device_resistance[j] * variation / 100)
```
Same `variation%` applied to ALL resistance states (HRS, LRS, and any MLC intermediate).

### Real RRAM (from wafer_xy16–25 data):
- HRS CV ≈ 20–35%  (filament dissolution is stochastic → high variance)
- LRS CV ≈ 10–19%  (filament formation is more controlled → lower variance)
- Ratio HRS/LRS ≈ 1.8–2.5×

### Fix implemented
`AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])` with per-state σ.

### How to use
```python
from pim_sim.device.calibrate import calibrate_from_measured_presets_csv
from dse.core import evaluate_config

models = calibrate_from_measured_presets_csv(
    "artifacts/dse/testdata_runs/<run>/measured_presets.csv"
)
result = evaluate_config(
    sim_config_path, nn_name, weights_path, config_values,
    run_accuracy=True, enable_variation=True,
    pim_sim_model=models["meas_cycle_strong"],
)
```

### Validation
```bash
python validate/calibrate_from_testdata.py --wafer-dir test_data/2T1R_cycle --plot
python validate/compare_accuracy_models.py --sim-config SimConfig.ini \
    --weights cifar10_vgg8_params.pth --variation 10 20 30 --plot
```

### Expected finding
At variation=20%, AsymmetricGaussian (HRS_CV=25%, LRS_CV=13%) shows
**higher accuracy drop** than symmetric (20% both states) because real
HRS noise is underestimated by the symmetric model.

---

## Gap 2: IR-Drop on Accuracy

### Problem
MNSIM's `evaluate_config` accuracy path has NO IR-drop.
`Crossbar_accuracy.py` (unused in DSE) has a partial model but
uses UNIFORM distribution (inconsistent with Weight_update) and
only a linear row-offset, not a physics-based correction.

### Physics
For N-row crossbar, row i sees voltage:
```
V_eff(i) ≈ V_in × (1 - α × i/N)
α = N × R_wire_segment / R_device_avg
```
- 128-row, R_wire=0.5Ω, R_dev=5000Ω → α=0.013 (1.3% mean loss)
- 512-row, R_wire=0.5Ω, R_dev=5000Ω → α=0.051 (5.1% mean loss)

### Fix implemented
`IRDropModel.apply_to_weight_matrix()` scales row weights by row position.

### How to use
```python
from pim_sim.array.ir_drop import IRDropModel

ir_model = IRDropModel(
    xbar_rows=128,
    wire_resistance_per_cell_ohm=0.5,
    device_resistance_avg_ohm=5000.0,
)
result = evaluate_config(
    ...,
    pim_sim_model=asym_model,
    ir_drop_model=ir_model,
)
```

### Validation
```bash
python validate/sweep_xbar_sensitivity.py --plot
```

### Key experiment for paper
Compare accuracy degradation at 128×128 vs 256×256 vs 512×512 — IR-drop
effect is quadratic in N, so large arrays degrade significantly more.
Use this to argue that MNSIM systematically *overestimates* accuracy
for large xbar configurations.

---

## Gap 3: Parametric ADC Model

### Problem
MNSIM has 9 hardcoded ADC presets. ADC bits is discrete, interpolation impossible.

### Fix implemented
`WaldenADCModel(enob=6.0)` — continuous ENOB, fitted to MNSIM reference points.

### How to use
```python
from pim_sim.array.adc_model import WaldenADCModel
from pim_sim.ppa.estimator import adc_ppa_delta

adc = WaldenADCModel(enob=6)
delta = adc_ppa_delta(sim_config_path, target_enob=6,
                      xbar_cols=128, n_xbars=256)
```

### Validation
```bash
python validate/compare_adc_models.py --plot
```

### Key finding
Walden FOM fits MNSIM reference points within ~15% error.
Interpolation between bits levels enables sensitivity curves
that MNSIM's lookup cannot produce.

---

## Remaining Work (not yet implemented)

### HIGH PRIORITY

- [ ] **`meas_cycle_typical` diagnosis**: Device_Variation=100% is capped.
  The 5 typical-cluster wafers have anomalously high variation.
  Run `calibrate_from_wafer_dir` on typical-cluster files and plot
  histograms to understand whether it's a bimodal distribution or
  measurement artifact.
  → File: `dse/extras/diagnose_typical_wafers.py`

- [ ] **Cross-scenario DSE with pim_sim models**: Replace MNSIM symmetric
  variation with calibrated AsymmetricGaussianModel in the existing
  `dse/run_matrix.py` workflow to get realistic accuracy numbers.
  → Modify `dse/run_matrix.py` to accept `--pim-sim-model` flag.

- [ ] **Accuracy saturation fix**: Current CIFAR-10/VGG8 experiments show
  identical accuracy (0.9424) across strong/weak presets → network is
  too robust to distinguish. Options:
  - Use a harder task (e.g. ImageNet subset) or lower-precision weights
  - Reduce xbar size to 32×32 where IR-drop shows more differentiation
  - Use a quantized (4-bit) network more sensitive to device noise
  → Investigate with `compare_accuracy_models.py --variation 30 50 70`

### MEDIUM PRIORITY

- [ ] **Wire resistance calibration from layout**: Current default
  R_wire=0.5Ω/cell is estimated. Calibrate from MNSIM's existing
  `wire_resistance` parameter in SimConfig.ini.
  → Read `Crossbar.py` lines 179-182 to extract actual R_wire value.

- [ ] **MLC support in AsymmetricGaussianModel**: The current implementation
  interpolates CV% linearly for MLC states. Real data shows non-linear
  behavior. Add a polynomial interpolation option.

- [ ] **EmpiricalDeviceModel serialization**: `state_samples` contains large
  arrays. Add `save_to_npz/load_from_npz` for caching calibrated models.

- [ ] **ADC precision as DSE axis**: Add `adc_bits` to the DSE search space
  in `dse/core.py:SPACE` using `WaldenADCModel` for PPA computation.

### LOW PRIORITY (paper polish)

- [ ] **Confidence intervals on accuracy**: Run 10+ trials per condition
  and report mean ± std in results tables.

- [ ] **NeuroSim comparison**: For the thesis, add a reference column
  comparing pim_sim PPA vs NeuroSim for the same design.

- [ ] **Unit tests**: `tests/test_device_models.py` covering:
  - Symmetry test: SymmetricGaussianModel should match MNSIM exactly
  - CV test: AsymmetricGaussianModel σ/mean should equal CV%
  - IR-drop test: top row scale = 1.0, bottom row scale = 1 - alpha*(N-1)/N
  - Walden test: WaldenADCModel power ∝ 2^ENOB

---

## Quick Start for New Experiments

```python
# 1. Calibrate from measured data
from pim_sim.device.calibrate import calibrate_from_measured_presets_csv
models = calibrate_from_measured_presets_csv(
    "artifacts/dse/testdata_runs/<run>/measured_presets.csv"
)

# 2. Build IR-drop model
from pim_sim.array.ir_drop import IRDropModel
ir_model = IRDropModel(xbar_rows=128)

# 3. Evaluate one config
from dse.core import evaluate_config
result = evaluate_config(
    "SimConfig.ini", "vgg8", "cifar10_vgg8_params.pth",
    config_values={"Tile_Num_Row": 4, "Tile_Num_Col": 4, ...},
    run_accuracy=True, enable_variation=True,
    pim_sim_model=models["meas_cycle_strong"],
    ir_drop_model=ir_model,
)
print(result.accuracy, result.energy_nj, result.area_um2)
```

---

## Paper Claim Checklist

| Claim | Evidence needed | Status |
|---|---|---|
| Symmetric model underestimates HRS noise | compare_accuracy_models.py curves | ⬜ pending |
| Asymmetric model improves accuracy prediction | accuracy vs variation comparison | ⬜ pending |
| IR-drop degrades accuracy for N>256 | sweep_xbar_sensitivity + accuracy run | ⬜ pending |
| Walden FOM enables continuous ADC bit sweep | compare_adc_models.py curves | ⬜ pending |
| pim_sim changes Pareto front shape vs MNSIM | DSE run with/without pim_sim | ⬜ pending |

---

*Last updated: 2026-04-17*
