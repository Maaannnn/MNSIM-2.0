# Registering your fab chip in MNSIM + pim_sim

This is a short how-to for running a **tape-out chip of your own** through
the validation pipeline that `validate/literature_anchor_baseline.py` and
`validate/literature_anchor_ablation.py` use for Liu 33.2 / Yan 11.7.

It is not a tutorial on MNSIM internals. It only covers the input contract
between your silicon measurement data and the simulator.

---

## 1. What data you need

See `docs/simulator/registering_your_fab_chip.md` (this doc) and the
reply in the chat for the full tier breakdown. TL;DR:

**Tier 1 — required (without these you can't run):**
tech_node_nm, device_type (NVM / SRAM), cell_type (1T1R / 2T2R / SRAM_6T),
device_area_um2, xbar.rows × xbar.cols, group_num, dac_num, adc_num,
read_voltage_v, read_latency_ns, pim_type.

**Tier 2 — strongly recommended (drives RRAM quality modeling):**
HRS / LRS resistance, variation CV (ideally **per-state** from wafer data),
SAF rates, ADC preset or Walden ENOB+FOM.

**Tier 3 — needed only for vs-silicon error validation:**
Your reported silicon area (mm²), performance (GOPS) or latency (ns),
energy efficiency (TOPS/W). Without these you can still compare
MNSIM-vs-pim_sim, just not vs-silicon.

**Tier 4 — leave as MNSIM defaults** unless you have a specific reason:
CACTI buffer parameters, digital-module templates (45/65 nm), NoC
topology, tile grid. `mnsim_adapter` fills these from MNSIM's builtin
tables.

---

## 2. Where to put the data

Add one function in `mnsim_adapter/registry.py` modelled on `_liu_chip()`
or `_yan_chip()`, then register it in `_LITERATURE_CHIPS`. Every numeric
field is wrapped in `Traced(value, Provenance(kind=..., source=...))` —
the `kind` tags how much you can defend the number:

- `physical`  — directly measured or specified (tech node, layout)
- `empirical` — from this chip's own characterization report
- `design`    — architectural choice (array size, PIM type)
- `fitted`    — tuned to make a specific metric match
- `proxy`     — MNSIM builtin default, not really your chip
- `missing`   — placeholder; flag for follow-up

Use these honestly. Tier-2 overlay C in the validation pipeline emits a
warning when a profile is loaded with `proxy` or `missing` values on
Tier-1/Tier-2 fields, so wrong tags surface in the report.

---

## 3. Minimal worked example

Say your tape-out is a 28 nm 2T2R RRAM macro with 128 × 128 arrays,
measured HRS/LRS = 1 MΩ / 20 kΩ, per-state CVs `(25 %, 13 %)` from wafer
data. In `mnsim_adapter/registry.py`:

```python
_MYFAB_SRC = "Internal Fab Report 2026Q2-rev1"


def _myfab_device() -> DeviceProfile:
    phys = Provenance(kind="physical", source=_MYFAB_SRC)
    emp  = Provenance(kind="empirical", source=_MYFAB_SRC)
    design = Provenance(kind="design",  source=_MYFAB_SRC)

    resistance = ResistancePair(
        hrs_ohm=1.0e6, lrs_ohm=2.0e4,
        provenance=emp,
    )

    # Per-state CV from our own wafer data — this is Tier-2 gold.
    variation = AsymmetricVariation(
        kind="asymmetric_gaussian",
        state_cv_pct=(25.0, 13.0),
        provenance=emp,
    )

    return DeviceProfile(
        tech_node_nm=Traced(28, phys),
        device_type=Traced("NVM", phys),
        cell_type=Traced("2T2R", design),
        transistor_tech_nm=Traced(28, phys),
        device_area_um2=Traced(0.12, emp),
        device_level=Traced(2, design),
        read_level=Traced(2, design),
        read_voltage_v=Traced((0.0, 0.3), emp),
        read_latency_ns=Traced(5.0, emp),
        write_level=Traced(2, design),
        write_voltage_v=Traced((0.0, 2.5), emp),
        write_latency_ns=Traced(50.0, emp),
        resistance=resistance,
        variation=variation,
        saf=None,
        label="My 28nm 2T2R fab chip",
    )


def _myfab_circuit() -> CircuitComponents: ...
def _myfab_architecture() -> ArchitectureProfile: ...


def _myfab_chip() -> ChipProfile:
    return ChipProfile(
        chip_id="myfab_28nm_2t2r_v1",
        label="Internal 28 nm 2T2R RRAM CIM macro",
        source_kind="measured",
        source_ref=_MYFAB_SRC,
        device=_myfab_device(),
        circuit=_myfab_circuit(),
        architecture=_myfab_architecture(),
    )


# Register it:
_LITERATURE_CHIPS["myfab_28nm_2t2r_v1"] = _myfab_chip
```

Then:

```bash
python validate/literature_anchor_baseline.py --chip myfab_28nm_2t2r_v1
python validate/literature_anchor_ablation.py --chip myfab_28nm_2t2r_v1
```

The baseline CSV goes to
`validate/output/literature_anchor/baseline_myfab_28nm_2t2r_v1.csv`,
the ablation CSV to
`ablation_myfab_28nm_2t2r_v1.csv`. The ablation will include:

- `mnsim_local_repro` — MNSIM baseline on your ChipProfile
- `pim_sim_chip_profile` — MNSIM + pim_sim Layer-2 overlays (asymmetric
  variation from your Tier-2 CVs + IR-drop + Walden ADC)
- `pim_sim_adc_walden` — ADC-only sensitivity row

If you also filled in Tier-3 `mnsim_table_iv` / `silicon_published`
fields in `validate/literature_anchor_baseline.py::CHIPS`, the ablation
additionally reports `abs_rel_error_vs_silicon_pct` per variant.

---

## 4. How the variation data becomes runtime behavior

Once `ChipProfile.device.variation` is filled:

1. `ChipProfile.to_pim_sim_overlay()` calls
   `mnsim_adapter.overlay.build_overlay(chip)`.
2. That calls `pim_sim.device.factory.device_model_from_variation(v)`
   (the pure factory), which returns:
   - `SymmetricGaussianModel(variation_pct=cv_pct)` for Tier-1 CV inputs
   - `AsymmetricGaussianModel(state_cv_pct=[...])` for Tier-2 per-state CVs
   - `None` if the profile has no variation (e.g. SRAM).
3. That `DeviceModel` is passed into `pim_sim_weight_inject`, which
   replaces MNSIM's symmetric Gaussian injection in
   `Weight_update.py:41` for the accuracy path.

`EmpiricalDeviceModel` (raw wafer-sample CDF) is not auto-constructed
because `mnsim_adapter.VariationModel` does not carry sample arrays.
If you want empirical CDF noise, instantiate `EmpiricalDeviceModel`
directly and pass it to `evaluate_config(pim_sim_model=...)` —
bypassing the overlay factory.

---

## 5. Common pitfalls

- **`device_level` for SRAM must be 2.** MNSIM `Device.py` checks this
  and the INI renderer warns.
- **Digital PIM (`pim_type=1`) forces `ADC_Choice=8`.** Whatever you set
  in CircuitComponents.adc gets overridden at runtime by MNSIM.
- **`xbar.rows × xbar.cols` is the per-compartment array**, not the total
  macro. `group_num` is the number of compartments in one PE.
- **`pim_sim` IR-drop is RRAM + analog PIM only.** For SRAM or digital
  PIM, `build_overlay` returns `ir_drop_model=None` by construction (see
  `mnsim_adapter/overlay.py:_build_ir_drop_model`).

---

## 6. Regression safety

After adding your chip, run:

```bash
python -m unittest tests.test_variation_factory -v
python validate/literature_anchor_ablation.py --chip rram_isscc2020_33p2
python validate/literature_anchor_ablation.py --chip sram_isscc2022_11p7
```

All should still produce the numbers committed under
`validate/output/literature_anchor/`. If any literature-anchor number
changed, you've touched a shared code path by accident — not a clean
"add a new chip" change.
