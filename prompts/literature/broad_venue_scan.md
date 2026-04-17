# Broad Venue Literature Scan

Run a broad literature search for the `MNSIM-2.0` research topic rather than a narrow simulator-only search.

Goal:

- identify papers that matter for problem framing, baseline design, optimization methods, and contribution positioning

Search horizon:

- hardware / architecture / EDA venues:
  - `IEEE TVLSI`
  - `DAC`
  - `ICCAD`
  - `DATE`
  - `IEDM`
  - `ISSCC`
- ML / optimization venues:
  - `NeurIPS`
  - `ICML`
  - `AAAI`

Search topics:

- compute-in-memory / in-memory computing architecture
- RRAM non-idealities and device-aware evaluation
- design space exploration for accelerators
- multi-objective optimization and Pareto search
- surrogate modeling / Bayesian optimization / evolutionary search
- hardware-aware neural architecture search

Output format:

- venue-by-venue scan summary
- grouped paper clusters by role
- strongest directly related papers
- adjacent-community papers worth borrowing methods from
- missing coverage and next search directions

Rules:

- do not stop at one community
- do not claim novelty before checking adjacent venues
- distinguish directly comparable baselines from method inspiration papers
