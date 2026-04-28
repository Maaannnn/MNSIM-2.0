# 仿真器文档

这一组文档聚焦 `MNSIM`、`NeuroSim`、`CrossSim` 以及 fidelity gap 的分析。按 **Live 规范 / 设计笔记 / 组会材料 / 背景参考** 四类组织：

## Live 规范（读码 / 写实验前先读）

- [`chip_profile_schema.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/chip_profile_schema.md)：`mnsim_adapter` 四层 ChipProfile schema + provenance 体系。任何新芯片/新实验都经这层。
- [`mnsim_upstream_diff.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/mnsim_upstream_diff.md)：本仓库 `MNSIM/` vs `thu-nics/MNSIM-2.0@ca39ccb` 的 byte-level diff 与材料性判断。
- [`mnsim_validation_replication_plan.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/mnsim_validation_replication_plan.md)：T8.1 复现计划 + Baseline 口径策略（§5 是 RRAM 文献锚点的过关标准，必读）。

## 设计笔记（pim_sim / enhancement layer 的设计背景）

- [`mnsim_fidelity_gap_review.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/mnsim_fidelity_gap_review.md)：当前 `MNSIM` 的保真度短板审视 — 驱动 `pim_sim/` 的三大支柱设计。
- [`neurosim_lessons_for_mnsim.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/neurosim_lessons_for_mnsim.md)：从 `NeuroSim` 吸收可迁移机制的整理。
- [`pim_sim_measured_device_validation.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/pim_sim_measured_device_validation.md)：measured preset 从 wafer 数据注入 `pim_sim` 的验证流。
- [`measured_preset_mapping_audit_20260417.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/measured_preset_mapping_audit_20260417.md)：`measured preset` 映射、异常统计与执行链覆盖问题审计。
- [`aime_mnsim.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/aime_mnsim.md)：RRAM CIM 非理想性的 L1–L4 体系化研究报告（参考型深度笔记）。

## 组会材料

- [`MNSIM_group_meeting_report.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/MNSIM_group_meeting_report.md)：组会汇报底稿。

## 背景参考

- [`reference/MNSIM_完整技术分析报告.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/reference/MNSIM_完整技术分析报告.md)：完整源码/框架分析报告（含层次建模、PPA 方法、SimConfig 参数、已知缺陷与优化方向）。
