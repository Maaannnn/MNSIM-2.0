---
name: mnsim-research-workflow
description: Research workflow for MNSIM-2.0. Use when the task involves measured-in-the-loop RRAM experiments, DSE planning, result synthesis, or paper-oriented writing in this repository.
---
# MNSIM Research Workflow

## Purpose

Use this skill when working on the research layer of `MNSIM-2.0`, especially for:

- formal-space and guidance-space DSE planning
- measured-preset extraction and analysis
- robust-search experiment organization
- broad literature search across hardware, EDA, and ML venues
- paper-oriented result synthesis and section drafting

## Read first

1. `README.md`
2. `AGENTS.md`
3. `agent.md`
4. `codex/research_workflow.md`

## Operating rules

- Prefer existing scripts under `dse/` and `artifacts/dse/scripts/`.
- Do not invent metrics, conclusions, or citations.
- Keep experiment execution, analysis notes, and manuscript writing distinct.
- Expand literature search beyond narrow CIM keywords and venues.
- Preserve existing artifact paths and non-destructive output conventions.
- Use `TODO:` to mark evidence gaps.

## Common task routing

| Task type | First place to inspect |
| --- | --- |
| Run or debug DSE | `dse/run_dse.py`, `artifacts/dse/scripts/` |
| Matrix or measured runs | `dse/run_matrix_csv.py`, `dse/extras/run_measured_matrix.py` |
| Interpret outputs | run directories under `artifacts/dse/`, then `docs/` |
| Literature search | `prompts/literature/`, then venue-grouped paper notes |
| Draft paper text | `docs/` notes, then target manuscript section |

## Venue horizon for paper search

When helping with related work or method positioning, routinely consider:

- `IEEE TVLSI`
- `DAC`
- `ICCAD`
- `DATE`
- `IEDM`
- `ISSCC`
- `NeurIPS`
- `ICML`
- `AAAI`

## Expected outputs

- reproducible command recommendations
- venue-aware literature maps
- concise experiment plans
- artifact-grounded result summaries
- academically restrained manuscript text
