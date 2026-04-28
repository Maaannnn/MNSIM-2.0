# ChipProfile schema (`mnsim_adapter`)

**Status:** active (replaces the earlier `UnifiedRRAMProfile` in `pim_sim/rram_profile.py`, which has been removed).
**Location:** `mnsim_adapter/` (package at repo root).
**Purpose:** give every MNSIM-driven experiment a single structured, provenance-tagged description of "the chip under simulation", from which both an MNSIM `SimConfig.ini` *and* the `pim_sim` enhancement-layer overlay kwargs can be derived deterministically.

## Why this layer exists

MNSIM's `SimConfig.ini` mixes three disjoint kinds of information into one flat file:

1. **Physical** — e.g. `Device_Tech=130` (process node is a device property).
2. **Design** — e.g. `Xbar_Size=784,100` (macro layout choice).
3. **Empirical / fitted / proxy** — e.g. `Device_Resistance=2e7,6e4` (rough-read from Fig. S1), `ADC_Area=0` (meaning "use MNSIM's builtin CACTI lookup").

Consumers — PPA evaluators, ablation studies, paper supplements — all need to know *which kind* a given field is so they can decide whether it is reproducible, whether it should be varied in a sensitivity sweep, and whether it can be swapped for a measured value. The INI format alone cannot carry that information.

`ChipProfile` is a thin *structured* descriptor on top of MNSIM. It does **not** re-implement MNSIM's simulation; it is purely a better input format, with two deterministic translators:

- `ChipProfile.to_mnsim_ini(path)` → regenerates an MNSIM-compatible `SimConfig.ini`.
- `ChipProfile.to_pim_sim_overlay()` → returns kwargs (`pim_sim_model`, `adc_model`, …) consumable by `dse.core.evaluate_config`.

## Four-layer composition

```
ChipProfile
├── DeviceProfile          (Layer 1 — mnsim_adapter/device.py)
├── CircuitComponents      (Layer 2 — mnsim_adapter/circuit.py)
└── ArchitectureProfile    (Layer 3 — mnsim_adapter/architecture.py)
    ├── XbarProfile
    ├── PEProfile
    ├── TileProfile
    └── ArchLevelProfile
```

`ChipProfile` itself (Layer 4 — `mnsim_adapter/chip.py`) is just the composition + cross-layer validation + emitters.

### Layer 1 — DeviceProfile

Everything that describes a single memory cell: tech node, device type (NVM / SRAM), cell layout (1T1R / 0T1R / SW-2T2R / 2T2R / SRAM_6T), resistance states, variation model, SAF pair, per-bit read/write latency and voltage.

- `ResistancePair(hrs_ohm, lrs_ohm, provenance)` — emits `Device_Resistance` as `HRS,LRS` (MNSIM convention).
- `VariationModel` has two subclasses:
  - `SymmetricVariation(cv_pct)` — MNSIM-native single-σ model.
  - `AsymmetricVariation(state_cv_pct)` — per-state CV (HRS, LRS[, intermediate]) for the pim_sim enhancement path. When rendered to INI, only the HRS CV goes into `Device_Variation=` (MNSIM only reads one number); the full tuple is written into a comment above the line *and* returned to the `pim_sim` overlay so the accuracy path uses the asymmetric model.

### Layer 2 — CircuitComponents

- `ADCProfile` is dual-mode: either a `preset_id` in `1..9` that selects an MNSIM builtin (choice 9 = the LPAR-ADC "Qi Liu" preset), or a user-defined quadruple (precision_bit, area_um2, power_w, sample_rate_gsps). Optional Walden-FOM parameters (`walden_enob`, `walden_fom_w`, `walden_fom_a_um2`) drive the pim_sim `WaldenADCModel` overlay.
- `DACProfile` follows the same dual-mode pattern. Empirically, `DAC_Choice=1` inflates latency via 8× time multiplexing and `DAC_Choice=6` has a power-scale issue in MNSIM's current path, so calibrated chips prefer user-defined.
- `DigitalModules` wraps the five digital units MNSIM cares about (adder, multiplier, shift_reg, reg, joint_module); each `DigitalModuleSpec` carries tech/area/power. Area/power `= 0` means "use MNSIM's builtin tech-node lookup".

### Layer 3 — ArchitectureProfile

- `XbarProfile` enforces `rows % subarray_size == 0` at construction.
- `PEProfile`: `pim_type ∈ {0=analog, 1=digital}`, `xbar_polarity`, `dac_num`, `adc_num`, input buffer.
- `TileProfile`: PE grid, pooling unit, tile-level adders/shift-regs, buffers, bandwidths.
- `ArchLevelProfile`: global buffer, LUT, tile grid, NoC enable, simulation level.

### Layer 4 — ChipProfile

Carries `chip_id`, `label`, `source_kind ∈ {literature, measured, synthetic}`, and `source_ref` plus the three sub-profiles. Methods:

- `validate()` — returns a list of problems; empty means consistent. Checks only high-value cross-layer invariants (digital PIM requires polarity=1; 0T1R only for NVM; SRAM requires read/write energies; subarray divisibility; user-defined ADC needs a precision).
- `with_adc`, `with_dac`, `with_variation`, `with_device`, `with_circuit`, `with_architecture` — ablation helpers; each returns a new frozen dataclass so the original profile is preserved.
- `to_mnsim_ini(path)` / `to_pim_sim_overlay()` — the two translators.
- `to_json(indent=2)` — paper-supplement dump.

## Provenance taxonomy

Every scalar in a `ChipProfile` is a `Traced[T](value, Provenance(kind, source, note))`. `kind` is one of:

| kind | meaning |
|------|---------|
| `physical` | dictated by the device/process itself — e.g. tech node, transistor tech |
| `design` | free design choice — e.g. xbar size, PE grid |
| `empirical` | measured or paper-reported — e.g. resistance states, published area |
| `fitted` | derived by fitting a model — e.g. Walden-FOM constants |
| `proxy` | placeholder that stands in for a missing value — e.g. MNSIM builtin defaults, "closest supported cell_type" |
| `missing` | explicitly absent; renderer emits a `[missing]` comment |

This is the information that `SimConfig.ini` loses. The INI emitter writes a `# [kind] source — note` comment *above* each key, so a regenerated INI is self-auditing.

## INI generation gotchas

- MNSIM's `ConfigParser` does **not** strip inline `#` comments. Provenance notes must appear on their own line above the `key = value` line, not after it.
- When a preset ID is set (`ADC_Choice ∈ {1..9}`, `DAC_Choice ∈ {1..7}`), MNSIM still *reads* the explicit area/precision/power/sample-rate fields, so the renderer writes zero sentinels rather than omitting them.
- `Device_Variation` accepts a single number only; for asymmetric variation the renderer emits the HRS CV there and documents the full tuple in the comment above.
- `-1` in MNSIM is a "use default" sentinel for several fields (`Wire_Resistance`, `Wire_Capacity`, `Load_Resistance`, `ADC_Interval_Thres`, `Logic_Op`); these are expressed as `Traced(-1, Provenance(kind="proxy", …))`.

## Registry

`mnsim_adapter/registry.py` ships with two entry points:

- `load_chip("rram_isscc2020_33p2")` — the ISSCC 2020 Paper 33.2 (Q. Liu et al.) RRAM macro, set up for MNSIM Table IV reproduction. Regenerated INI + MNSIM `ProcessElement` reproduces (area, latency, efficiency) = (3.3914 mm², 53.7908 ns, 74.6523 TOPS/W), i.e. within ±0.003% of what the canonical `configs/SimConfig_issc2020_33p2.ini` yields.
- `load_measured_device(preset_name)` — wraps the wafer-calibrated presets in `pim_sim/device/calibrated_presets.py` (both `PRESETS` and per-wafer `WAFER_MODELS`) into a `ChipProfile` whose `device.variation` is asymmetric Gaussian. Architecture + circuit are inherited from the Liu chip as carrier, since measured data only constrains the device-variation field. Enumerate via `available_measured_presets()`.

## Consumers

- `validate/literature_anchor_baseline.py` — reads `resolve_config_path(chip_id)` which regenerates the INI via `load_chip` and caches it under `validate/output/literature_anchor/generated_configs/`.
- `validate/literature_anchor_ablation.py` — same entry point; drives the three-way comparison (MNSIM baseline / pim_sim chip profile / pim_sim ADC Walden).
- `pim_sim.accuracy.weight_inject.pim_sim_weight_inject` and `dse.core.evaluate_config` — receive the `to_pim_sim_overlay()` kwargs.

## Non-goals

- Not a SimConfig super-set. Every INI field that MNSIM reads has a counterpart here; nothing else.
- Not a new simulator. All PPA/accuracy numbers still come from MNSIM (and optionally pim_sim corrections on top).
- Not a replacement for `test_data/` or `pim_sim/device/calibrated_presets.py`. Those remain the source of truth for wafer measurements; this layer only *wraps* them.
