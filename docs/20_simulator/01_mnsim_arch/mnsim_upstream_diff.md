# MNSIM upstream provenance

**Purpose**: document exactly what code drift, if any, exists between this
working tree's `MNSIM/` and the official upstream
`github.com/thu-nics/MNSIM-2.0`. Required to justify every claim of the
form "we ran MNSIM on chip X and got Y" in the pim_sim paper and
supplement.

## Method

```
git clone --depth=1 https://github.com/thu-nics/MNSIM-2.0.git /tmp/.../thu-nics
diff -rq MNSIM/  /tmp/.../thu-nics/MNSIM/
```

Upstream pinned to `thu-nics/MNSIM-2.0@ca39ccb` (Merge PR #9, 2024-11-27).

## Structural result

Two differences, only one material:

| Path | Status | Material? |
|------|--------|-----------|
| `MNSIM/Interface/cifar10/` | local-only directory | No — downloaded CIFAR-10 batches, data not code |
| `MNSIM/Interface/interface.py` | content differs | **Yes** — see below |

**Every other file under `MNSIM/` is byte-identical to upstream.**
This explicitly includes `MNSIM/Hardware_Model/`, which holds all PPA
computation (`Crossbar.py`, `PE.py`, `Tile.py`, `ADC.py`, `DAC.py`,
`Buffer.py`, and the `{Area,Latency,Power,Energy}_Model` trees).

## interface.py — what differs

All four categories of change are authored by `gaoyiman` in commits
`0706566` and `f51b115`. They are all **non-simulator** changes; none
touches MAC / energy / latency / area math.

1. **`_resolve_torch_device()` helper (new)** — parses device specs like
   `"mps"`, `"cuda:1"`, `"0"`. Upstream only supports
   `int → cuda:int` or fall-back-to-cpu. No effect on numerical output.

2. **`_TEST_LOADER_CACHE`, `_WEIGHTS_CACHE` (new)** — module-level caches
   to avoid re-loading weights and dataloader on every
   `TrainTestInterface` construction. Deterministic, identical outputs,
   pure latency optimisation.

3. **`max_eval_batches` constructor parameter (new)** — replaces
   upstream's hard-coded `if i > 10:` batch break with
   `if i >= self.max_eval_batches:`. **Default is 11**, which matches
   upstream's `> 10` (i.e. indices 0..10 inclusive = 11 batches). So
   *with defaults*, behaviour is identical; explicit callers that pass
   `max_eval_batches=N` will diverge from upstream behaviour.

4. **`torch.load(..., weights_only=True)`** — PyTorch security flag.
   Same loaded tensors.

## Impact on reproducibility claims

### PE-level PPA reproduction (ISSCC 2020 33.2, Table IV)

`validate/literature_anchor_baseline.py` calls
`ProcessElement.calculate_PE_area / calculate_PE_read_power_fast /
calculate_PE_energy_efficiency`, all defined in `MNSIM/Hardware_Model/`,
which is **byte-identical to upstream**.

Therefore the reproduced values
`(area, latency, efficiency) = (3.3914 mm², 53.7908 ns, 74.6523 TOPS/W)`
for `rram_isscc2020_33p2` are what **official thu-nics MNSIM@ca39ccb**
produces on our `ChipProfile`-regenerated SimConfig. Any residual vs
Table IV (−3.10% / +0.77% / +0.29%) is **upstream-origin**, not caused
by any local edit.

### Accuracy-path experiments (VGG8 / MLP on pim_sim vs MNSIM)

Pim_sim accuracy experiments go through `TrainTestInterface`, which
does include our `interface.py` deltas. Two points:

- If you pass the default `max_eval_batches=11`, the batch-iteration
  behaviour is identical to upstream.
- If you pass a smaller value for speed (e.g. `--max-acc-batches 3`),
  the reported accuracy is computed over fewer batches than upstream's
  hard-coded 11. This is a **sample-size** difference, not a logic
  difference — the accuracy model itself is unchanged.

For camera-ready comparisons, use the default `max_eval_batches=11` so
the evaluation protocol matches upstream exactly.

## How to pin future runs

Record in any paper supplement or experiment manifest:

```
MNSIM upstream = github.com/thu-nics/MNSIM-2.0@ca39ccb
MNSIM local delta = MNSIM/Interface/interface.py (see
docs/simulator/mnsim_upstream_diff.md for the 4 categories of change;
all non-simulator, default behaviour identical to upstream)
```

Regenerate this check by re-running the diff command above. Any new
divergence that affects `MNSIM/Hardware_Model/` or
`MNSIM/Accuracy_Model/` should trigger a rebaseline of
`validate/output/literature_anchor/`.
