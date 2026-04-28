# MINLP Formulation of the PIM Design-Space Problem — Draft v0.1

Status: **draft for thesis RC2.** Goal is to give the design-space
search problem a formal MINLP statement grounded in the code currently
running under `dse/`, and to make explicit what stops us from handing
it to an off-the-shelf solver today.

Not a specification. Not a runtime artefact. A mapping between the
thesis language (RC2: *MINLP 形式化 + GA/SA/BO 混合优化 + DP 初始解*)
and `dse/core.py` + `pim_sim/` + MNSIM. Update this doc when the code
moves; flag drift with `TODO:` rather than re-writing from scratch.

## 1. Why state an MINLP at all

The DSE layer today (`dse/run_dse.py` with `bo_gp`, `nsga2`, `mobo`)
treats the problem as black-box Bayesian / evolutionary search over
`SPACE_PROFILES`. That works, but three things are lost:

- **Structural constraints are invisible to the searcher.** For
  example, `xbar_size × pe_num × tile_count` must be large enough to
  hold the mapped network weights. MNSIM enforces this implicitly at
  mapping time — the searcher sees the cost of a bad pick as "mapping
  failed / huge latency" rather than as a constraint to respect.
- **Initial solutions are random.** `dse/run_dse.py --init-evals 6`
  samples the space uniformly; a DP-derived initial solution based on
  analytical bounds (RC2 goal) would be strictly better.
- **No shared objective.** `bo_gp` scalarises; `nsga2`/`mobo` treat
  the problem as multi-objective. Neither writes down the objective
  symbolically, so we cannot cross-compare tracks beyond Hypervolume.

The MINLP form is the contract that lets the three knobs above coexist:
one objective definition, one constraint set, one variable encoding.

## 2. Decision variables

Current dimensions live in `dse/core.py::SPACE_PROFILES`. Each
profile is a restriction of the full variable list. The `rram_full`
profile is closest to the formal domain; `rram_v2`, `rram_formal_v3`,
`rram_guidance_v4` are fixed-budget subsets for specific experiments.

| Symbol | Name | Type | Domain | Source |
|--------|------|------|--------|--------|
| `p`    | `rram_preset`     | categorical | `{P0..P4}`           | `core.RRAM_PRESETS` |
| `x_s`  | `xbar_size`       | discrete 2D | `{128², 256², 512²}` | `SPACE["xbar_size"]` |
| `a`    | `adc_choice`      | ordinal     | `{4, 6, 7, 8}`       | `SPACE["adc_choice"]` |
| `d`    | `dac_num`         | integer     | `{32, 64, 128}`      | `SPACE["dac_num"]` |
| `q`    | `xbar_polarity`   | binary      | `{1, 2}`             | `SPACE["xbar_polarity"]` |
| `u`    | `sub_position`    | binary      | `{0, 1}`             | `SPACE["sub_position"]` |
| `g`    | `group_num`       | integer     | `{1, 2, 4}`          | `SPACE["group_num"]` |
| `x_p`  | `pe_num`          | discrete 2D | `{2², 4², 8²}`       | `SPACE["pe_num"]` |
| `t`    | `tile_connection` | categorical | `{0, 1, 2, 3}`       | `SPACE["tile_connection"]` |
| `b`    | `inter_tile_bw`   | ordinal     | `{10, 20, 40, 80}`   | `SPACE["inter_tile_bw"]` |

Encoding for a standard solver (Gurobi, SCIP, BARON):

- Categorical (`p`, `t`) → one-hot binary indicators.
- Discrete 2D (`x_s`, `x_p`) → one-hot over the enumerated tuples,
  or two separate integer variables with product constraints.
- Ordinal / integer (`a`, `d`, `g`, `b`) → integer with branch cuts
  to forbid off-grid values, **or** one-hot (simpler, loses ordering).

Continuous extensions already supported by `pim_sim`:

- `adc_preset_id ∈ ADCPreset.REGISTRY` (Stage-2A, 14 named presets).
  Adds FoM_W and FoM_A as constants per category.
- `ir_drop_model=on/off` is currently binary; a continuous
  `wire_resistance_ohm_per_cell` parameter is exposed via
  `pim_sim.array.ir_drop` and could be added.

## 3. Objective vector

`dse/core.EvalResult` returns five raw metrics:

```
latency_ns, area_um2, power_w, energy_nj, accuracy
```

`dse/metrics.py` + algorithm scalarisers build the search objective
on top. The MINLP form:

- **Multi-objective** (matches `nsga2`/`mobo`):
  minimise `[ energy_nj(x),  area_um2(x),  -accuracy(x) ]`
  with `latency_ns(x)` as a hard constraint (§4).
- **Scalarised** (matches `bo_gp`):
  minimise `energy_nj(x) / accuracy(x)` subject to a latency cap — a
  proxy for 1 / (TOPS/W · acc_frac).

Both forms share the same `f : x → EvalResult` function; only the
aggregation differs. Write `f` as the composition:

```
f(x) = EnergyModel( AreaModel( PowerModel( LatencyModel( TCG.map(x, NN) ) ) ) )
       ∘ AccuracyModel.weight_update ∘ pim_sim.accuracy.weight_inject
```

Entry point: `dse/core.evaluate_config()`.

## 4. Constraint set

### 4.1 Structural (closed-form, analytical)

```
(C1)  xbar_rows  * xbar_cols * pe_rows * pe_cols * tile_count
        ≥ Σ_l W_l_bits / q            — weights fit on the array
(C2)  a ≤ log2(xbar_rows * I_cell_max / I_adc_fullscale) + 1
                                        — ADC full-scale not overflown
(C3)  g | xbar_cols                    — group_num divides column count
```

### 4.2 Electrical (nonlinear, simulator-derived)

```
(C4)  IR_drop(x_s, p) ≤ V_drop_budget    — pim_sim.array.ir_drop
(C5)  I_column_worst(x_s, p) ≤ I_adc_fullscale(a)
```

`pim_sim/array/ir_drop.py` treats IR drop as nonlinear in `x_s` (row
count, column count) and in `p` (via `g_lrs`, `g_hrs`). No
closed-form expression; the simulator resolves it numerically per
array geometry.

### 4.3 Budgets (linear in outputs, hard caps)

```
(C6)  area_um2(x)  ≤ A_max           (chip budget)
(C7)  power_w(x)   ≤ P_max           (thermal / package)
(C8)  latency_ns(x) ≤ T_max          (workload SLA)
(C9)  accuracy(x)  ≥ acc_baseline − ε  (task budget)
```

`A_max`, `P_max`, `T_max`, `ε` are deployment inputs, not searcher
outputs. They should live in an `experiment_manifest.json` field
(currently unused, see `dse/contracts.py`).

## 5. Why this is not directly solvable

`f(x)` is not exposed as a closed-form expression. Four components
are black-box:

- **Accuracy.** `MNSIM.Accuracy_Model.Weight_update.weight_update`
  injects device noise into the weight tensor and runs inference.
  The map from `p, x_s, a` to `accuracy` is a stochastic Monte-Carlo
  output with no gradient and no analytical form.
- **Latency.** `MNSIM.Latency_Model.Model_latency` walks the mapping
  graph and sums per-tile latencies; control flow depends on layer
  shapes.
- **IR drop.** Numerical solve per array; `pim_sim.array.ir_drop`
  calls the MNSIM-upstream solver, which is imperative code.
- **Mapping.** `MNSIM.Mapping_Model.Tile_connection_graph.TCG` runs
  a heuristic layout that is *not* declarative.

Off-the-shelf MINLP solvers (Gurobi, SCIP, BARON, Couenne) need
either (i) explicit expressions for `f` and the nonlinear
constraints, or (ii) an oracle model. Neither exists today.

## 6. Hybrid solution strategy (RC2 plan)

Three-stage pipeline:

1. **Analytical DP initial solution.**
   Use closed-form (C1)–(C3) plus bound approximations for C4–C5 to
   solve a *reduced* MINLP where `f(x)` is replaced with analytical
   upper-/lower-bounds:

   - energy ≈ Σ_l (xbar_ops_l × E_MAC(x_s, a, d))
   - area ≈ tile_count × (A_xbar(x_s) + A_adc(a) + A_dac(d))
   - accuracy ≈ 1.0 − k · σ_device(p) (first-order)

   Solve with Gurobi/SCIP; pick `N_init` best distinct solutions.
   Output: seed population for stage 2.
   Code target: new `dse/initial_solution/dp.py`.

2. **Simulator-in-the-loop GA / SA / BO refinement.**
   Feed `N_init` seeds into the existing DSE runner
   (`dse/run_dse.py --init-evals N_init --warm-start ...`). Each
   real evaluation calls `evaluate_config` and updates a surrogate
   (GP / RF) over `f`. This is what the three current algorithms
   already do; the MINLP contribution is (i) shared variable
   encoding, (ii) shared constraints applied as `penalty(x)` in the
   scalariser, (iii) DP-seeded initial population.

3. **Verification.**
   Re-run top-K Pareto solutions with
   `--run-accuracy` and full IR-drop, not just the cached surrogate.
   Discard solutions that violate (C6)–(C9) on the exact simulator.

## 7. What the codebase currently has vs. needs

| Need | State |
|------|-------|
| Unified variable encoding | **Partial.** `SPACE_PROFILES` is the canonical enum; a one-hot encoder for solvers does not exist yet. |
| Constraint module | **Missing.** (C1)–(C9) are implicit, not expressed anywhere. `dse/penalties.py` or similar is the obvious place. |
| DP initial solver | **Missing.** Proposed: `dse/initial_solution/dp.py`. |
| GA track | **Missing.** (`nsga2` is closest, but it is specifically NSGA-II for multi-objective; an SA/GA single-objective with constraint penalties does not exist.) |
| BO track | **Present.** `dse/algorithms/bo_gp.py`. |
| Multi-objective track | **Present.** `dse/algorithms/nsga2.py`, `mobo.py`. |
| Simulator surrogate | **Partial.** Per-algorithm internal GPs exist; no shared surrogate across tracks. |
| Verification pass | **Partial.** `--run-accuracy` exists but is opt-in, not enforced for Pareto tops. |

## 8. Acceptance criteria (thesis-side, not code-side)

This document is sufficient for the 2026.04–06 milestone if:

1. Every variable in `SPACE_PROFILES["rram_full"]` appears in §2 with
   the same name and domain.
2. Every black-box component in §5 points at an actual source file.
3. A reviewer can read §6 and identify three *concrete* engineering
   tasks (stage 1 DP, stage 2 warm-start hook, stage 3 verification
   gate) without further clarification.
4. The doc admits what is *not* done, honestly. `TODO:` markers for:
   - constraint module location,
   - `experiment_manifest.json` budget fields,
   - how to fold `adc_preset_id` from Stage-2A into the MINLP.

## 9. Open questions

1. **Do we want a single objective or a Pareto front in the thesis?**
   RC2 reads Pareto, but a single scalarised formulation is much
   easier to write down.
2. **Is the DP initial solver worth building, or can we warm-start
   from prior `matrix_runs/` outputs?** The latter needs no new code.
3. **Do we formalise the surrogate (e.g., GP prior per variable), or
   stay black-box?** Affects whether §6 stage 2 is "BO with
   constraints" or "GA with penalty".

---
Pointers:
- `dse/core.py` — SPACE_PROFILES, evaluate_config, EvalResult.
- `pim_sim/array/ir_drop.py` — nonlinear constraint source.
- `pim_sim/array/adc_library.py` — Stage-2A continuous ADC presets.
- `MNSIM/Accuracy_Model/Weight_update.py` — black-box accuracy oracle.
- `docs/references/开题报告v3-11.14.docx` — RC2 source requirement.
