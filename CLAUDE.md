# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo identity

This repo is **both** the original MNSIM-2.0 PIM simulator **and** a research workspace built on top of it. The research layer (`AGENTS.md`, `agent.md`, `codex/`, `prompts/`, `docs/`) sets rules for experiment/paper work; it does not replace the simulator. Two important files beyond this one:

- `AGENTS.md` — evidence-discipline and file-discipline rules for any work here. Read before making structural changes or writing research prose.
- `agent.md` — the current experiment roadmap (RQ1–RQ5, E0–E9). Reflects what the user is actively running.

Do not fabricate experimental metrics, citations, or conclusions. Mark evidence gaps with `TODO:` rather than implying a run exists.

## Commands

Python env is `.venv/` at repo root. A typical invocation uses the venv's `python` directly.

### Simulator end-to-end (single config)
```
python main.py -NN vgg8 -Weights cifar10_vgg8_params.pth -HWdes SimConfig.ini
```
`SimConfig.ini` and `techfile.txt` at repo root are symlinks to `configs/`. Scripts in `artifacts/dse/scripts/` already handle path resolution.

### DSE: multi-algorithm, multi-seed search
```
python dse/run_dse.py --algos bo_gp nsga2 mobo --seeds 42 43 44 \
  --budget 24 --init-evals 6 --nn vgg8 \
  --weights cifar10_vgg8_params.pth --base-config SimConfig.ini \
  --workers 3 --plots
```
Default `--output-root AUTO` creates `artifacts/dse/search_runs/run_YYYYMMDD_HHMMSS/` (never overwrites). Add `--run-accuracy` for NN accuracy eval (slow). Regenerate plots from an existing run with `--plot-only --output-root <run dir>`.

### DSE: CSV matrix sweeps and measured-preset flows
- `python dse/run_matrix_csv.py ...` — exhaustive/deterministic sweeps from a CSV of configs.
- `bash artifacts/dse/scripts/run_testdata_analysis.sh` — extract measured presets from `test_data/` into `artifacts/dse/testdata_runs/run_*/measured_presets.csv`.
- `python dse/extras/run_measured_matrix.py --measured-presets-csv ... --matrix-csv ...` — run a matrix under patched SimConfigs derived from measured presets.
- Canned recipes: `artifacts/dse/scripts/run_formal_v3_{exhaustive,search}.sh`, `run_guidance_v4_search.sh`, `run_measured_matrix_experiments.sh`.

### Tests
```
python -m unittest discover -s tests -v
python -m unittest tests.test_app_validity -v   # single module
```
Tests use `unittest` (no pytest config).

### Dashboard
```
PORT=5001 python app/server.py       # http://localhost:5001
```
Backs onto the local SQLite cache at `app/dse_records.db` (gitignored; auto-created).

### Cleanup
```
bash tools/clean.sh
```

## Architecture

### MNSIM core simulator (`MNSIM/`)
Pipeline invoked by `main.py`: `Interface.TrainTestInterface` loads net + weights → `Mapping_Model.TCG` maps NN onto tiles → `Latency_Model`, `Area_Model`, `Power_Model`, `Energy_Model` produce PPA → optionally `Accuracy_Model.Weight_update.weight_update` injects device non-idealities (SAF, variation, R-ratio) and `Interface.set_net_bits_evaluate` reports accuracy. Hardware config is a ConfigParser INI (`configs/SimConfig.ini`); hardware primitives (Crossbar, ADC, DAC, PE, Tile, Buffer, etc.) live under `MNSIM/Hardware_Model/`.

### DSE layer (`dse/`)
`dse/core.py` is the **single source of truth** for the design-space definition (`SPACE_PROFILES`, `RRAM_PRESETS`) and the `evaluate_config` function that wraps a full MNSIM simulation call. All algorithms (`dse/algorithms/{bo_gp,nsga2,mobo,random_sample}.py`) must import `SPACE` and `evaluate_config` from `core.py` — never re-define locally. `dse/run_dse.py` is the concurrent runner (one subprocess per trial via `ProcessPoolExecutor`); `dse/output.py` + `dse/metrics.py` handle serialisation, reports, and Hypervolume with a globally shared reference point across trials. `dse/contracts.py` defines the `experiment_manifest.json` schema that every run directory must contain. `dse/extras/` holds non-runner utilities (measured-preset extraction, surrogate dataset builder, cross-scenario robustness, backfill of older contracts). `dse/db_writer.py` writes trial summaries into the app SQLite cache.

Track semantics: `bo_gp` is a single-objective (scalarised) track; `nsga2`/`mobo` are multi-objective. Hypervolume is only comparable within the multi-objective track.

### pim_sim enhancement layer (`pim_sim/`)
**Not a fork of MNSIM.** It plugs into `dse/core.evaluate_config` via the `pim_sim_model=` and `ir_drop_model=` kwargs — the function `pim_sim.accuracy.weight_inject.pim_sim_weight_inject` is a drop-in replacement for `MNSIM.Accuracy_Model.Weight_update.weight_update`. Addresses three specific MNSIM gaps: asymmetric HRS/LRS device variation (calibrated per-state from wafer measurements), array-size-dependent IR-drop on accuracy, and a continuous Walden-FOM ADC model in place of MNSIM's 9-entry lookup table. Calibrated wafer presets are hardcoded in `pim_sim/device/calibrated_presets.py`; `validate/` holds validation scripts comparing MNSIM vs `pim_sim`.

### App (`app/`)
Flask entry `server.py` is thin — analysis/report/validity/sync logic lives in `app/backend/{analysis,reports,validity,shared,sync}.py`. Static frontend (`app/static/`) uses Alpine.js with no build step. `artifacts/dse/invalidation_registry.json` is a **non-destructive** invalidation layer: historical run paths listed there are surfaced as `invalidated` in the UI and API instead of being deleted. New analysis views should go through a JSON API in `app/backend/` rather than adding iframe/legacy branches.

### Artifact tree (`artifacts/dse/`)
Outputs are always non-destructive and usually timestamped:
- `search_runs/run_*/` — algorithm-search outputs (from `dse/run_dse.py`).
- `matrix_runs/` — exhaustive/CSV-matrix outputs; `measured_run_*` subdirs are gitignored.
- `testdata_runs/run_*/measured_presets.csv` — outputs from measured-preset extraction (gitignored).
- `datasets/` — surrogate training datasets (deterministic names from sampling args).
- `matrices/rram_v2/` — canonical matrix CSVs (A/B/C/E).
- `scripts/` — the canonical shell wrappers; prefer these over inventing new ones.
- `docs/` — per-space design notes (`rram_formal_v3.md`, `rram_guidance_v4.md`, `server_run_guide.md`).

Do not overwrite prior run directories. Record seeds, budget, device, and accuracy settings whenever you add a run.

### Weights and configs
`cifar10_{lenet,alexnet,vgg8,vgg16,resnet18,resnet_update}_params.pth` live at repo root (gitignored, downloaded separately — see README). Scripts search in order: given path → `weights/` or `configs/` → repo root. `test_data/` holds real device measurement data (gitignored); do not assume it's present on fresh clones.

## Conventions from AGENTS.md worth knowing

- Prefer small verifiable edits over broad rewrites; prefer existing scripts under `dse/` and `artifacts/dse/scripts/` over new ones.
- Separate layers: experiment execution, analysis notes, manuscript writing — don't collapse them.
- Terminology: *formal space* = constrained space for exhaustive comparison; *guidance space* = broader space for guideline discovery; *measured preset* = device-condition preset extracted from `test_data/`; *measured-in-the-loop* = search/eval loop where measured presets patch `SimConfig.ini`; *robust search* = ranking across multiple presets, not one nominal setting.
- When surveying literature, routinely span `IEEE TVLSI / DAC / ICCAD / DATE / IEDM / ISSCC / NeurIPS / ICML / AAAI`, not only CIM/NeuroSim venues.
