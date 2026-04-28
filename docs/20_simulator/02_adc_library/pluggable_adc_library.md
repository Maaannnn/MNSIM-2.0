# Pluggable ADC/DAC Device Library — Stage-2 Design Note

Status: **Stage-2A landed** (2026-04-22) — module + tests live at
`pim_sim/array/adc_library.py`, `tests/test_adc_library.py`.
Stage-2B (DSE variable) and Stage-2C (ChipProfile binding) remain
proposals below.
Scope: seeds the broader `pim+sim+dse` unified simulator goal — front-end /
back-end / algorithm studies all sharing the same pluggable device layer.

## 1. Why a preset library

`pim_sim.array.adc_model.WaldenADCModel` uses a single pair of global
constants fitted to MNSIM's 9-entry 28 nm reference table:

| Constant | pim_sim default |
|----------|-----------------|
| FoM_W | 20.0 fJ/conv-step |
| FoM_A | 8.0 µm² per (2^ENOB / GSa/s) |

Silicon validation against Murmann ADC Performance Survey
(`artifacts/external/murmann_adc_survey`, 438 Nyquist ADCs, 1997–2026)
shows two things:

1. **The global defaults are not universally valid.** Median silicon
   FoM_W = 138 fJ and median FoM_A = 123 µm² — pim_sim underestimates
   both by ~7× and ~15× respectively on the full corpus.
2. **The defaults *are* accurate for the architecture CIM actually uses.**
   Stratifying by `(ARCHITECTURE, ERA)` recovers tight fits on the
   subsets that matter for CIM:

   | Subset | N | FoM_W median (fJ) | FoM_A median (µm²) |
   |--------|---|-------------------|--------------------|
   | SAR · modern (≥2015) | 37 | **20.4** | 0.24 |
   | Pipe·SAR · modern    | 21 | 6.2 | 0.87 |
   | Pipe · modern        | 11 | 21.7 | 146 |
   | Flash · legacy       | 23 | 5431 | 6209 |

   The **single hardcoded constant hides this structure**: a 28 nm SAR
   CIM chip and a 0.18 µm flash CIM chip cannot share one FoM.

The preset library fixes (1) without regressing (2): each chip picks a
preset appropriate to its architecture/era; the user sees a *named*
choice instead of a silent global.

Raw seed data: `validate/output/walden_murmann/adc_preset_library_seed.csv`.

## 2. Interface

Two layers, matching existing ChipProfile discipline:

### Layer A — `pim_sim.array.adc_library` (landed)

```python
@dataclass(frozen=True)
class ADCPreset:
    preset_id: str                 # e.g. "sar_modern", "pipe_sar_modern"
    architecture: str              # raw Murmann label, e.g. "SAR", "Pipe, SAR"
    era: str                       # "legacy" | "modern" (year >= 2015)
    fom_walden_j_per_conv: float
    fom_area_um2: float
    n_silicon_points: int          # min(n_power, n_area) from Murmann subset
    source: str = "Murmann ADC Survey rev20260314 …"

    def to_model(self, enob: float, sample_rate_gsps: float) -> WaldenADCModel:
        ...

REGISTRY: dict[str, ADCPreset]     # 14 presets
```

Two departures from the original proposal:

- **`preset_id` does not encode tech node.** Stratification is
  `(architecture, era)` only — era is year-based (≥ 2015 = modern), not
  node-based. A node-based split is still an open question (§6).
- **Seed data is embedded in the module** rather than loaded from CSV
  at import time. Parity with
  `validate/output/walden_murmann/adc_preset_library_seed.csv` is
  guarded by `tests/test_adc_library.py::ADCPresetSeedParityTest`; the
  CSV remains the regenerable source of truth.
- `enob_support` / `sample_rate_support_gsps` deferred — not in the
  seed CSV, not required by any current consumer.

### Layer B — ChipProfile binding

`ChipPPAProfile` grows one optional field:

```python
adc_preset_id: str | None = None      # falls back to Walden global default
```

`pim_sim.ppa.estimator.adc_ppa_delta` then looks up the preset when
building `WaldenADCModel` instead of constructing it with the hardcoded
defaults. When `adc_preset_id` is `None`, behaviour is unchanged — this
keeps every currently-passing validation regression-safe.

## 3. DSE integration (same module, no re-plumb)

`dse/core.SPACE_PROFILES` already carries ADC-related knobs. We add one
categorical variable:

```python
"adc_preset_id": ["sar_28nm_modern", "pipe_sar_28nm_modern", ...]
```

The DSE runner then passes it through to `evaluate_config`, which
patches `pim_sim_model.adc_preset` before calling MNSIM. No change to
search algorithms or metrics.

## 4. What *not* to do in Stage-2

- **Do not** replace `_MNSIM_ADC_TABLE` or any MNSIM ADC.py logic. The
  preset library is an overlay exposed only through `pim_sim_model=`.
- **Do not** add a DAC preset library in the same PR. DAC validation
  data from Murmann is thinner; ship ADC first, measure reviewer
  reaction, then decide.
- **Do not** auto-select a preset for registered chips that currently
  use `ADC_Choice=9` (Liu). The matched MNSIM implementation is already
  chip-specific; an overlay would double-count.
- **Do not** create a new validation script. Extend the existing
  `validate/walden_murmann_validation.py` if more stratification is
  needed.

## 5. Verifiable acceptance criteria

1. `artifacts/external/murmann_adc_survey/xls/ADCsurvey_rev20260314.xlsx`
   is the single source of truth for preset FoMs; running
   `validate/walden_murmann_validation.py` regenerates the seed CSV
   bit-identically. **Status: met.**
2. `pim_sim.array.adc_library.REGISTRY["sar_modern"]` returns a preset
   whose `fom_walden_j_per_conv` rounds to 20.36 fJ (silicon median).
   **Status: met** — see
   `tests/test_adc_library.py::test_sar_modern_matches_acceptance_criterion`.
3. `validate/literature_anchor_baseline.py` results for Liu and Yan are
   bit-identical after Stage-2C lands with `adc_preset_id=None`
   (null-overlay invariant). **Status: not started** (Stage-2C).
4. Stage-2A integration test covers preset lookup + WaldenADCModel
   construction + parity with seed CSV. **Status: met** — 8 tests in
   `tests/test_adc_library.py`. `adc_ppa_delta` integration deferred to
   Stage-2C.

## 6. Open questions for user confirmation

1. **Scope of the first PR.** Stage-2A = `adc_library` module + seed CSV
   + tests only; Stage-2B = DSE `adc_preset_id` variable; Stage-2C =
   ChipProfile binding for new chip registrations. Recommend shipping
   2A first, alone, to de-risk.
2. **Era cutoff.** 2015 was chosen because FoM_W stabilises at ~26 fJ
   after that year. An alternative would be a 28 nm/65 nm technology
   split. Need user pick before freezing preset_ids.
3. **DAC parity.** Same treatment for DACs is deferred pending user
   direction — the PIM path currently only exercises DAC bits, not a
   parametric model.
