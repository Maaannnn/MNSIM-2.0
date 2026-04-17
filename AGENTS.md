# AGENTS.md

## Repo mission

Maintain `MNSIM-2.0` as both a usable simulator repository and a decision-grade research workspace for PIM architecture exploration, DSE benchmarking, measured-device analysis, and paper writing.

This repository should support:

- reproducible MNSIM experiments
- measured-in-the-loop RRAM studies
- broad and disciplined literature search
- section-by-section academic writing
- careful result interpretation without overstating evidence

## Current research phase

The active focus is RRAM DSE for paper-ready experiments, especially:

- formal-space ground-truth sweeps
- search-algorithm comparison
- measured preset extraction from `test_data/`
- measured-in-the-loop robustness analysis
- manuscript structuring for problem formulation, method, experiments, and conclusions

## What "done" means in this repo

- The change advances one of the active research threads in a concrete way.
- The output is reproducible, traceable, and stored in a sensible location.
- Claims match the available evidence.
- Follow-up work is captured explicitly when a task is incomplete.

## Core rules for Codex

- Prefer small, verifiable edits over broad rewrites.
- Read local project context before making structural changes.
- Use existing scripts and workflows before inventing new ones.
- Treat literature search as a first-class research task, not an afterthought.
- Keep experiment setup, analysis notes, and manuscript writing clearly separated.
- When evidence is missing, write `TODO:` instead of implying certainty.

## Evidence discipline

- Never fabricate metrics, tables, plots, citations, or conclusions.
- Never describe an experiment as completed unless artifacts or logs exist.
- Distinguish clearly between:
  - planned experiments
  - partially executed experiments
  - validated findings
- If a result depends on a missing run, mark the gap explicitly.

## Editing priorities

When unsure what to improve first, prefer this order:

1. unblock reproducible experiments
2. clarify research framing and assumptions
3. organize outputs and notes
4. tighten manuscript prose
5. add helper automation only if it reduces repeated research friction

## File discipline

- `README.md`: public-facing project entry plus research-workspace navigation
- `agent.md`: high-level experiment plan and execution checklist
- `docs/`: research analysis, design notes, and longer-form planning
- `codex/`: Codex-specific handoff, workflow, and collaboration context
- `prompts/`: reusable prompt templates for literature, experiment, analysis, and writing tasks
- `artifacts/`: experiment outputs and generated research assets
- `dse/`: executable DSE pipelines and analysis code

## Preferred workflow

1. Read `README.md`, `agent.md`, and the relevant document or script.
2. Decide whether the task is about experiment execution, result analysis, or paper writing.
3. Make the smallest useful change in the correct layer.
4. Store outputs in the existing repository structure.
5. Update handoff notes or prompt docs if the change affects future sessions.

## Experiment rules

- Reuse existing scripts under `artifacts/dse/scripts/` and `dse/extras/` whenever possible.
- Keep output directories timestamped or otherwise non-destructive.
- Do not overwrite prior experiment artifacts unless explicitly asked.
- Record assumptions such as device, budget, seeds, and accuracy settings.
- When introducing a new experiment helper, document its intended input and output paths.

## Writing rules

- Maintain academic tone and restrained wording.
- Prefer precise language over promotional framing.
- Separate methodological intent from empirical evidence.
- Avoid claiming robustness, superiority, or generalization without supporting runs.
- Keep section text aligned with the actual repository artifacts.

## Literature search rules

- Codex should help with paper search, venue expansion, and related-work coverage.
- Do not search only for `MNSIM`, `NeuroSim`, or narrow keyword matches.
- Expand searches across architecture, EDA, hardware ML systems, and ML optimization venues when relevant.
- For this repository, literature search should routinely consider venues such as:
  - `IEEE TVLSI`
  - `DAC`
  - `ICCAD`
  - `DATE`
  - `NeurIPS`
  - `ICML`
  - `AAAI`
  - `IEDM`
  - `ISSCC`
- When surveying prior work, organize papers by role:
  - simulator / evaluator
  - design space exploration
  - multi-objective optimization
  - CIM / IMC hardware architecture
  - device-nonideality-aware modeling
  - hardware-aware ML or NAS
- Never imply literature coverage is complete if the search has only touched one venue family.

## What not to do

- Do not invent experimental evidence.
- Do not rewrite the whole paper or repo structure in one pass.
- Do not move core simulator code unless the task requires it.
- Do not add heavyweight tooling just to imitate another repository.
- Do not treat planning notes as validated scientific conclusions.

## Working terminology

- `formal space`: the constrained design space used for exhaustive or near-exhaustive comparison
- `guidance space`: the broader design space used for design-guideline discovery
- `measured preset`: a device-condition preset derived from real measurement data in `test_data/`
- `measured-in-the-loop`: an experiment loop where measured-device characteristics affect simulation or search
- `robust search`: ranking or optimization based on performance across multiple measured presets rather than a single nominal setting
