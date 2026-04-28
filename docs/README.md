# 文档导航

`docs/` 已在 2026-04-27 重组为编号目录。原 `framework/` `status/`
`simulator/` `notes/` 子目录全部归位；旧入口 README 与陈旧文档保留在
`_archive/`。

## 顶层结构

| 目录 | 用途 |
|---|---|
| [`00_roadmap/`](00_roadmap/) | 路线图、状态板、TODO、组会讲稿、仓库结构 |
| [`10_framework/`](10_framework/) | 研究框架、选题定位、问题定义、竞品 landscape |
| [`20_simulator/`](20_simulator/) | MNSIM / pim_sim 技术文档（验证、架构、ADC 库、芯片接入） |
| [`30_optimization/`](30_optimization/) | DSE 形式化、measured-device 验证 |
| [`40_notes/`](40_notes/) | 实验数据笔记 |
| [`references/`](references/) | 原始文献 PDF / DOCX |
| [`_archive/`](_archive/) | 已被替代或陈旧的文档（保留供溯源） |

## 00_roadmap — 当前状态

执行真源（最高权威）：

- [`current_research_todo.md`](00_roadmap/current_research_todo.md) — 执行总表
- [`experiment_protocol.md`](00_roadmap/experiment_protocol.md) — 科研协议、统计假设
- 根目录 `agent.md` — RQ1–RQ5 / E0–E9 实验路线图

辅助导航：

- [`status_weekly_summary.md`](00_roadmap/status_weekly_summary.md) — 一页摘要（原 `current_status_board.md`）
- [`group_meeting_navigation.md`](00_roadmap/group_meeting_navigation.md) — 历次组会讲稿索引
- [`group_meeting_talk.md`](00_roadmap/group_meeting_talk.md) — 当前可用的组会讲稿
- [`REPO_STRUCTURE.md`](00_roadmap/REPO_STRUCTURE.md) — 仓库目录概览

## 10_framework — 研究框架与选题

- [`SCIENTIFIC_CODEX_FRAMEWORK.md`](10_framework/SCIENTIFIC_CODEX_FRAMEWORK.md) — 总框架、5 条主线、Codex 职责
- [`robustmap_cim_positioning.md`](10_framework/robustmap_cim_positioning.md) — `RobustMap-CIM` 选题学术边界
- [`RRAM_DSE_Problem_Formulation_And_Method.md`](10_framework/RRAM_DSE_Problem_Formulation_And_Method.md) — 设计变量、目标、formal / guidance space
- [`competitor_landscape.md`](10_framework/competitor_landscape.md) — CIMFlow / SEGA-DCIM / EasyACIM / AutoDCIM / Eva-CiM 对比

## 20_simulator — 仿真器技术文档

按工作流分四段：

### `00_validation/` — 验证与缺口

- [`mnsim_validation_replication_plan.md`](20_simulator/00_validation/mnsim_validation_replication_plan.md) — T8.1 baseline 复现计划
- [`mnsim_fidelity_gap_review.md`](20_simulator/00_validation/mnsim_fidelity_gap_review.md) — MNSIM vs SPICE / NeuroSim 缺口
- [`neurosim_lessons_for_mnsim.md`](20_simulator/00_validation/neurosim_lessons_for_mnsim.md) — NeuroSim 高保真特性、可借鉴清单
- [`neurosim_v15_vs_pim_sim.md`](20_simulator/00_validation/neurosim_v15_vs_pim_sim.md) — NeuroSim V1.5 逐项对比（最深威胁）

### `01_mnsim_arch/` — MNSIM 架构与上游

- [`MNSIM_group_meeting_report.md`](20_simulator/01_mnsim_arch/MNSIM_group_meeting_report.md) — 系统综述
- [`mnsim_upstream_diff.md`](20_simulator/01_mnsim_arch/mnsim_upstream_diff.md) — 本地 vs `thu-nics` upstream byte-level diff

### `02_adc_library/` — ADC 库

- [`pluggable_adc_library.md`](20_simulator/02_adc_library/pluggable_adc_library.md) — 14 个 (architecture × era) preset，Murmann survey 校准

### `03_chip_integration/` — 芯片接入

- [`chip_profile_schema.md`](20_simulator/03_chip_integration/chip_profile_schema.md) — `mnsim_adapter` 四层 ChipProfile + Provenance
- [`registering_your_fab_chip.md`](20_simulator/03_chip_integration/registering_your_fab_chip.md) — 流片芯片接入 4-tier 入口
- [`measured_preset_mapping_audit_20260417.md`](20_simulator/03_chip_integration/measured_preset_mapping_audit_20260417.md) — wafer→preset 映射审计

## 30_optimization — DSE 与方法

- [`minlp_formulation.md`](30_optimization/minlp_formulation.md) — 多目标约束优化形式化
- [`pim_sim_measured_device_validation.md`](30_optimization/pim_sim_measured_device_validation.md) — measured-device 验证协议

## 40_notes — 实验数据笔记

- [`wafer_xy7_forensics.md`](40_notes/wafer_xy7_forensics.md) — wafer xy7 数据集分析

## references — 原始文献

外部文献（PDF / DOCX 原稿）放在 [`references/`](references/)。

## _archive — 已归档

- `_archive/framework/` — `masters_thesis_to_dac_subtopics.md`、
  `RRAM_DSE_设计建议文档.md`、旧 framework README
- `_archive/status/` — 旧 status README
- `_archive/simulator/` — 旧 simulator README
- `_archive/notes/` — 旧 notes README
- `20_simulator/_archive/` — `aime_mnsim.md`、`MNSIM_完整技术分析报告.md`
- `40_notes/_archive/` — `docx_insights_framework_selection.md`、
  `pdf_insights_rram_cim_nonidealities.md`

## 内容缺口（按优先级）

下列内容仍缺失，对应 `current_research_todo.md` 中的待办：

- **H** Provenance 规范 — 每个常数的来源 / N / 不确定性硬性要求
- **H** 跨工艺缩放协议 — 28→14→7 nm 怎么外推
- **H** ADC silicon 校准流程 — wafer→preset 映射步骤
- **H** 端到端 measured-in-the-loop 案例 — wafer→preset→matrix→robust ranking
- **M** IR-drop & mismatch 量化模型
- **M** 跨网络泛化结论
- **M** 工艺标准库
