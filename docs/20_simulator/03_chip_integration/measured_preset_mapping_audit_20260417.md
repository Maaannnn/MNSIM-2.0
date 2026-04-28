# `measured preset` 映射审计（2026-04-17）

这份笔记只回答一个问题：

- 当前仓库里的 `measured preset -> MNSIM` 接入链，哪些部分已经被代码和 artifact 支持，哪些部分仍然不能当论文证据。

## 1. 先给结论

当前最重要的结论不是“`measured preset` 已经跑通”，而是下面 4 点：

1. `Device_Variation` 在 MNSIM 里确实是阻值百分比噪声，不是抽象等级。
2. 但当前 `variation_proxy_pct -> Device_Variation` 的映射仍然没有被物理校准，最多只能叫 `proxy`，不能叫“已验证器件参数”。
3. `meas_cycle_typical` 的 `Device_Variation=100` 主要是重尾 / 异常 wafer 把统计量顶爆后又被代码 cap 到 100，不应当作为“典型器件场景”。
4. 更关键的是，在当前代码路径下，只要 design point 里还带 `rram_preset=P0/P1/P2/...`，`write_temp_config()` 就会把 measured scenario 里的 `Device_Resistance / Device_Variation / Device_SAF` 覆盖回标称 preset。也就是说，当前 measured matrix / robustness 结果还不能当成可复现实验结论。

## 2. `Device_Variation` 到底是什么

直接证据来自 MNSIM 源码：

- [MNSIM/Accuracy_Model/Weight_update.py](/Users/bytedance/workspace/MNSIM-2.0/MNSIM/Accuracy_Model/Weight_update.py:19) 读取 `Device_Variation`
- [MNSIM/Accuracy_Model/Weight_update.py](/Users/bytedance/workspace/MNSIM-2.0/MNSIM/Accuracy_Model/Weight_update.py:40) 用 `np.random.normal(scale=device_resistance[j] * variation / 100)` 注入噪声

这说明它的工作含义是：

- 对目标阻值 `R_nominal`
- 加一个标准差为 `variation% * R_nominal` 的高斯扰动

所以这里的问题不是“单位完全错了”，而是：

- 当前脚本把 wafer 级的 `CV%` 代理量直接拿来当单一高斯 `sigma`
- 这个映射没有经过 MNSIM 语义校准
- 也没有证明 2T1R 数据里的离散性能够直接等价为 MNSIM 的静态权重扰动

换句话说：

- `CV`：变异系数，等于标准差除以均值
- `sigma`：高斯噪声的标准差

这两个量在“百分比”层面是相通的，但不等于“可以不经校准直接替换”。

## 3. 为什么 `meas_cycle_typical=100` 不可信

当前提取逻辑在 [dse/extras/extract_measured_presets.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/extract_measured_presets.py:226) 先按 `quality_score` 把 wafer 分成 `weak / typical / strong`，然后在 [dse/extras/extract_measured_presets.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/extract_measured_presets.py:252) 对 `variation` 做 `min(v, 100.0)`。

对应 artifact 显示：

- [artifacts/dse/testdata_runs/run_20260417_142758/cycle_state_summary.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/testdata_runs/run_20260417_142758/cycle_state_summary.csv:3)
  - `cycle_typical.device_variation_pct_raw_median = 248.826`
  - `cycle_typical.device_variation_pct_suggested = 100.000`
- [artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv:3)
  - `meas_cycle_typical.device_variation = 100.000`

进一步抽查原始 wafer 可见，`typical` 组里至少有明显重尾：

- `wafer_xy20.csv`
  - `bePGM` 中位数仍在约 `2335Ω`
  - 但最大值达到 `12.5MΩ`
- `wafer_xy24.csv`
  - `bePGM` 中位数仍在约 `2327Ω`
  - 但最大值达到 `12.5MΩ`

这说明当前 `typical=100` 更像：

- 少量极端值把普通 `CV%` 统计量拉爆
- 再被脚本上限截断

而不是：

- 一个自然、可信、可直接进入论文主线的“典型器件状态”

TODO:

- 重新定义 `variation_proxy` 的稳健统计量，例如 trimmed CV、winsorized CV，或基于分位数的 robust spread
- 在输出中显式保留 `raw_median / capped_median / cap_hit_count`

## 4. 阻值量级差异仍然没有被解释

当前 nominal preset 与 measured preset 的阻值量级差异非常大：

- nominal `P0/P1/P2`
  - `HRS ~ 1e6Ω`
  - `LRS ~ 1e4Ω` 或 `2e4Ω`
- measured cycle presets
  - `HRS ~ 1.27e4Ω - 1.45e4Ω`
  - `LRS ~ 2.3e3Ω - 2.6e3Ω`

这不是一个小扰动，而是跨了两个数量级。

当前仓库里还没有证据证明这是：

- 1T1R 与 2T1R 的正常尺度转换
- 不同工艺节点带来的固定比例变化
- 还是测试数据与 MNSIM 默认器件族本来就不在同一个物理基线

因此，当前 measured preset 更适合被表述为：

- `device proxy`
- `measured-derived scenario`

而不是：

- `validated measured equivalent of P0/P1/P2`

## 5. 当前执行链里还有一个更严重的问题：scenario patch 会被 `rram_preset` 覆盖

这条问题来自当前代码逻辑本身。

### 5.1 代码链

- [dse/run_matrix_csv.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py:155) 调用 `write_temp_config(base_config, cfg_vals)`
- [dse/extras/run_robustness.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_robustness.py:158) 也调用 `write_temp_config(rc.base_config_path, record.config)`
- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py:371) 一旦看到 `rram_preset`，就会 `_apply_rram_preset(parser, str(v))`
- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py:35) 到 `:69` 里的 preset 会重写 `Device_Resistance / Device_Variation / Device_SAF`

### 5.2 直接验证

用当前仓库的 `write_temp_config()` 对下面两个 measured config 做一次最小重放：

- `artifacts/dse/matrix_runs/ws2_firstlook_20260417/configs/meas_cycle_strong.ini`
- `artifacts/dse/matrix_runs/ws2_firstlook_20260417/configs/meas_cycle_weak.ini`

再叠加同一个 design point：

- `rram_preset=P0`
- `xbar_size=128x128`
- `adc_choice=4`
- `dac_num=32`
- `pe_num=2x2`

生成出的临时配置在两个场景下都回到了：

- `Device_Resistance = 1e6,1e4`
- `Device_Variation = 0.5`
- `Device_SAF = 0.01,0.01`

也就是说：

- 当前 measured base config 被 design point 自己的 `rram_preset` 覆盖掉了
- strong / weak 的器件差异没有稳定留到最终执行配置里

## 6. 对现有 artifact 应该怎么解释

这里要非常克制。

我们已经看到：

- [artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_observed/per_scenario.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_observed/per_scenario.csv:2) 到 `:5`
  - strong/weak 的 accuracy 有小幅差异
  - 而且方向不一致
- [artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/robustness/per_repeat.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/robustness/per_repeat.csv:2) 和弱场景对应文件则是逐行一致

因此当前最稳妥的表述是：

- 现有 artifact 说明 measured workflow 已经“走通了目录和 contract”
- 但还不能说明 measured device 参数已经被稳定注入到可复现实验路径
- 在当前代码版本下，任何带 `rram_preset` 的 rerun 都会优先回到 nominal preset

TODO:

- 在修复执行链之前，不要把 `ws2_firstlook_20260417` 作为 measured-in-the-loop 主证据
- 如果必须在组会上展示，只能把它称为“workflow smoke result”

## 7. 最小整改顺序

建议按下面顺序推进，而不是继续堆更多 measured run：

1. 先修执行语义
   - 明确 measured scenario 与 `rram_preset` 的关系
   - 二选一：
     - measured run 中移除 `rram_preset` 维度
     - 或者保留 `rram_preset` 作为 metadata，但最终写配置时让 scenario patch 在最后覆盖 device-level preset
2. 再修 preset 提取
   - 把 `device_variation` 改名为 `device_variation_proxy`
   - 输出 robust spread 辅助列
   - `typical` 一旦 hit cap，直接 warning
3. 再做 sanity sweep
   - 固定一组 architecture
   - 扫 `Device_Variation = 5, 10, 20, 25, 50, 100`
   - 看 accuracy 是否单调下降，以及下降区间从哪开始变陡
4. 最后才做 measured vs nominal
   - 先有 reproducible nominal baseline
   - 再比较 measured scenario 是否真的引起最优点迁移

## 8. 论文层面的安全说法

在修复前，建议只使用下面这种说法：

- 已经构建了 `measured-derived preset extraction` 工作流
- 当前 preset 仍然是 `proxy-level mapping`
- 其物理标定与执行链复现性仍需进一步校准

不建议使用下面这种说法：

- measured preset 已被验证
- measured-in-the-loop robustness 已经得到稳定结论
- `meas_cycle_typical` 代表真实典型器件
