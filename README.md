# MNSIM-2.0
**Citation Information**: Zhenhua Zhu, Hanbo Sun, Tongxin Xie, Yu Zhu, Guohao Dai, Lixue Xia, Dimin Niu, Xiaoming Chen, Xiaobo Sharon Hu, Yu Cao, Yuan Xie, Huazhong Yang, and Yu Wang, MNSIM 2.0: A Behavior-Level Modeling Tool for Processing-In-Memory Architectures, in IEEE TRANSACTIONS ON COMPUTER-AIDED DESIGN OF INTEGRATED CIRCUITS AND SYSTEMS (TCAD), VOL. 42, NO. 11, NOVEMBER 2023

**Main Contributor**:
Zhenhua Zhu<sup>1*</sup>, Hanbo Sun<sup>1</sup>, Tongxin Xie<sup>1</sup>, Lixue Xia<sup>2</sup>, Gokul Krishnan<sup>6</sup>, Dimin Niu<sup>2</sup>, Qiuwen Lou<sup>3</sup>,

Xiaoming Chen<sup>4</sup>, Yuan Xie<sup>2, 5</sup>, Yu Cao<sup>7</sup>, X. Sharon Hu<sup>3</sup>, Yu Wang<sup>1*</sup>, and Huazhong Yang<sup>1</sup>

<sup>1</sup>Tsinghua University, <sup>2</sup>Alibaba Group, <sup>3</sup>University of Notre Dame, 
<sup>4</sup>Institute of Computing Technology, Chinese Academy of Sciences, 
<sup>5</sup>The Hong Kong University of Science and Technology,
<sup>6</sup>Arizona State University
<sup>7</sup>University of Minnesota System

<sup>*</sup>zhuzhenh18@mails.tsinghua.edu.cn, yu-wang@tsinghua.edu.cn

MNSIM-2.0 aims to model the HW performance and NN computing accuracy of Processing-In-Memory (PIM) architectures. If you have any questions and suggestions about MNSIM-2.0 please contact us via e-mail. We hope that MNSIM-2.0 can be helpful to your research work, and sincerely invite every PIM researcher to add your ideas to MNSIM-2.0 to enlarge its function.

For more information about MNSIM-2.0, please refer to the MNSIM_manual.pdf and the IEEE TCAD paper of MNSIM 2.0.

*Weights File: https://1drv.ms/f/s!AtForEDTP2-PgkzYkCJNONO9xnX6?e=y4s0XG*

## Research Codex Workspace

This repository now includes a lightweight Codex-oriented research workspace inspired by [`jy00295005/decision-grade-memory`](https://github.com/jy00295005/decision-grade-memory), adapted to the MNSIM and RRAM DSE workflow instead of a generic paper-drafting project.

### Start here

- `AGENTS.md`: repository-level rules for research-safe Codex collaboration
- `agent.md`: current experiment roadmap and execution checklist
- `app/README.md`: local dashboard backend/frontend structure
- `docs/README.md`: research and status document index
- `docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md`: research framework distilled from the proposal document and current repo assets
- `codex/session_handoff.md`: short template for resuming work across sessions
- `codex/research_workflow.md`: workflow conventions for experiment, analysis, and writing tasks
- `prompts/README.md`: reusable prompt library for setup, literature, experiment design, analysis, and manuscript drafting

### What this configuration is for

- keeping Codex sessions reproducible across experiment and writing tasks
- preserving evidence discipline for paper-oriented work
- reusing prompt templates instead of restating project context every time
- making measured-in-the-loop and DSE work easier to hand off and resume

### Scope

This workspace layer does not replace the original simulator structure. It adds research-collaboration conventions on top of the existing MNSIM code, scripts, and artifact layout.
