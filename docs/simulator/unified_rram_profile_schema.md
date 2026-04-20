# Unified RRAM Profile Schema

## Purpose

`MNSIM` 和 `pim_sim` 现在同时面对两类输入源：

- literature-backed external chips，例如 `ISSCC 2020 33.2`
- measured-device presets，例如 `test_data/` 导出的 `typical_robust`

如果两类输入直接走不同的数据结构，就很容易把：

- paper-backed 参数
- measured 参数
- proxy/default 参数
- chip-specific overlay

混在一起解释。为统一口径，仓库新增了一个标准化输入对象：

- [pim_sim/rram_profile.py](/Users/bytedance/workspace/MNSIM-2.0/pim_sim/rram_profile.py)

## Schema

统一对象是 `UnifiedRRAMProfile`，包含两块：

- `mnsim_baseline`
  - 用来生成 `MNSIM-compatible baseline`
  - 当前字段：`Device_Resistance`、`Device_Variation`、`SAF`
- `pimsim_overlay`
  - 用来生成 `pim_sim enhancement`
  - 当前字段：`state_cv_pct`、`current_dependent_energy_scale`、`extra_output_buffer_kb`

每个字段都用 `EvidenceField` 包一层：

- `value`
- `provenance`
- `note`

这样可以明确区分：

- `paper_backed`
- `measured`
- `baseline_proxy`
- `baseline_reference`
- `missing`
- `none`

## Adapters

当前提供两个 adapter：

- `build_literature_profile(chip_id)`
- `build_measured_profile(preset_name)`

它们都返回同一个 `UnifiedRRAMProfile` 结构。

## Example Exports

导出脚本：

- [validate/export_unified_rram_profile.py](/Users/bytedance/workspace/MNSIM-2.0/validate/export_unified_rram_profile.py)

当前已导出的两个样例：

- literature chip:
  - [rram_isscc2020_33p2.json](/Users/bytedance/workspace/MNSIM-2.0/validate/output/profile_schema/rram_isscc2020_33p2.json)
- measured preset:
  - [measured_typical_robust.json](/Users/bytedance/workspace/MNSIM-2.0/validate/output/profile_schema/measured_typical_robust.json)

## Current Interpretation

对 `Liu 33.2`：

- `mnsim_baseline.device_resistance_ohm` 是 paper-backed
- `mnsim_baseline.device_variation_pct` 是 baseline proxy
- `pimsim_overlay.extra_output_buffer_kb` 和 `current_dependent_energy_scale` 是 chip-specific public-data-backed overlay
- `pimsim_overlay.state_cv_pct` 仍然缺失

对 `typical_robust`：

- `mnsim_baseline.device_variation_pct = 1%` 只是 comparator baseline
- `pimsim_overlay.state_cv_pct = (31.5, 3.1)` 是 measured enhancement
- 没有 chip-level PPA overlay

## Recommended Use

后续所有对比最好都先从 `UnifiedRRAMProfile` 出发，再分别翻译成：

1. `MNSIM baseline config`
2. `pim_sim device model`
3. `pim_sim PPA overlay`

这样写论文时可以统一表述为：

- same profile schema
- different provenance
- different translator path

而不是“论文芯片一套说法、实验室 testdata 一套说法”。
