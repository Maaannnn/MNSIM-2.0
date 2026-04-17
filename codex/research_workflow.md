# Research Codex Workflow

This file defines how Codex should operate in this repository when helping with experiments or paper writing.

The workflow is grounded in the local proposal document `开题报告v3-11.14.docx`, but adapted to the current repository reality: this repo is strongest as a reproducible research workspace around `MNSIM + DSE + measured presets`, not as a full product-scale microservice platform.

## Modes of work

### 1. Experiment execution

Use this mode when the task is to run, debug, or extend DSE and measured-data workflows.

Checklist:

- identify the entry script first
- confirm required config, weights, and dataset paths
- avoid destructive overwrites
- capture seeds, budget, device, and accuracy settings
- write outputs into the existing artifact tree

Typical entry points:

- `dse/run_dse.py`
- `dse/run_matrix_csv.py`
- `dse/extras/run_measured_matrix.py`
- `artifacts/dse/scripts/*.sh`

### 2. Result analysis

Use this mode when the task is to compare algorithms, interpret Pareto fronts, summarize measured effects, or prepare paper tables and figures.

Checklist:

- locate the exact run directories first
- distinguish observed outcomes from hypotheses
- report limitations such as small budget, missing seeds, or partial accuracy evaluation
- prefer concise markdown reports stored under `docs/` or `artifacts/`

### 3. Manuscript support

Use this mode when the task is to turn experiment structure or findings into paper-ready writing.

Checklist:

- map prose to actual experiments already present in the repo
- use `TODO:` where citation or evidence is missing
- keep sections modular rather than collapsing everything into one file
- reflect the current research state honestly

### 4. Literature search

Use this mode when the task is to position the work, expand related work, identify baselines, or track methods from adjacent communities.

Checklist:

- search beyond simulator-specific keywords
- cover both hardware/EDA venues and ML/optimization venues when the topic crosses boundaries
- group papers by problem role, not just by publication year
- connect each paper to the local research question or design decision
- record what is still missing from the search

Default venue horizon for this repository:

- `IEEE TVLSI`
- `DAC`
- `ICCAD`
- `DATE`
- `IEDM`
- `ISSCC`
- `NeurIPS`
- `ICML`
- `AAAI`

## Canonical research storyline

The current paper-oriented arc is:

1. problem formulation in a constrained formal design space
2. algorithm comparison under fixed evaluation budgets
3. design-guideline discovery in a wider space
4. measured-preset extraction from real device data
5. measured-in-the-loop robust optimization and compensation analysis
6. cross-network generalization

The corresponding framing from the proposal should be interpreted as:

- modeling and problem formulation first
- automated search and design guidance second
- measured-in-the-loop robustness as the strongest innovation line
- systemization only insofar as it improves reproducibility and scientific output
- literature search should span both CIM hardware venues and general optimization / ML venues where useful methods may appear

## Output conventions

- Use repository-relative artifact paths already established by the project.
- Prefer markdown for notes and reports.
- Keep generated assets out of top-level clutter.
- When adding a new report, include enough context that a future session can read it without replaying the entire chat.

## When to update handoff or prompts

Update `codex/session_handoff.md` or files in `prompts/` when:

- a new recurring workflow appears
- a fragile command sequence should be preserved
- a manuscript task benefits from a repeatable prompt pattern
- a future Codex session would otherwise need to rediscover project context

## Avoid over-scoping

Do not default to building heavyweight platform layers such as:

- distributed task systems
- database-heavy service architectures
- SLO and operations dashboards
- product-style frontend/backend abstractions

unless the user explicitly asks for them and they are necessary for the research outcome.

For the current repository, prioritize:

- experiment validity
- analysis quality
- literature breadth
- paper alignment
- session continuity
