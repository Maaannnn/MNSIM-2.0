# wafer_xy7 Forensics

## Question

`wafer_xy7.csv` 到底是：

1. 文件坏了 / 解析错了
2. 真的是异常器件 / 异常编程事件
3. 还是当前校准逻辑把异常放大了

对照文件选用：

- 异常候选：[wafer_xy7.csv](/Users/bytedance/workspace/MNSIM-2.0/test_data/2T1R_cycle/wafer_xy7.csv)
- 正常对照：[wafer_xy16.csv](/Users/bytedance/workspace/MNSIM-2.0/test_data/2T1R_cycle/wafer_xy16.csv)

## 1. 结构完整性

两份文件的 CSV 头部字段一致，且都包含相同的关键列：

- `Curve Name`
- `R_cell`
- `verify pulse count`
- `Cyc_Num`
- `dieX`
- `dieY`

两份文件的曲线类别也一致：

- `teERS`
- `bePGM`

行数统计：

- `wafer_xy7.csv`
  - total rows: `228,305`
  - `teERS`: `114,168`
  - `bePGM`: `114,137`
- `wafer_xy16.csv`
  - total rows: `938,253`
  - `teERS`: `469,142`
  - `bePGM`: `469,111`

结论：

- 这不是“字段错位”或“CSV 结构损坏”问题。
- 当前异常不是由文件格式解析错误直接造成的。

## 2. 全量分布对比

### wafer_xy7.csv

- `teERS`
  - mean: `12959.28`
  - CV: `67.96%`
  - median: `11651.62`
  - p95: `20032.05`
  - p99: `27431.08`
  - max: `189573.46`
- `bePGM`
  - mean: `3196.20`
  - CV: `262.64%`
  - median: `2352.39`
  - p95: `4420.67`
  - p99: `6268.81`
  - max: `189573.46`

### wafer_xy16.csv

- `teERS`
  - mean: `14286.07`
  - CV: `30.26%`
  - median: `13525.39`
  - p95: `22321.43`
  - p99: `27491.41`
  - max: `70947.14`
- `bePGM`
  - mean: `2326.55`
  - CV: `3.08%`
  - median: `2334.68`
  - p95: `2352.83`
  - p99: `2581.94`
  - max: `3411.40`

结论：

- `wafer_xy7` 的 `teERS` 明显更散，但还能看成“更差的 HRS”。
- 真正异常的是 `bePGM`：
  - 中位数仍然正常，约 `2352Ω`
  - 但存在极长的高阻尾部，把均值和 CV 拉爆
- 这更像“有一批严重失败或难以编程的 LRS 事件”，而不是整个 wafer 的 LRS 都坏了。

## 3. 采样逻辑是否放大了异常

当前 `pim_sim` 校准脚本默认会截断前 `50,000` 行做统计。

### wafer_xy7.csv

- first 50k
  - `teERS` mean `14037.35`, CV `122.20%`
  - `bePGM` mean `4398.71`, CV `405.01%`
- full file
  - `teERS` mean `12959.28`, CV `67.96%`
  - `bePGM` mean `3196.20`, CV `262.64%`

### wafer_xy16.csv

- first 50k
  - `teERS` mean `14167.30`, CV `27.76%`
  - `bePGM` mean `2312.66`, CV `1.74%`
- full file
  - `teERS` mean `14286.07`, CV `30.26%`
  - `bePGM` mean `2326.55`, CV `3.08%`

结论：

- `wafer_xy7` 的异常是真实存在的。
- 但“只取前 50k 行”的当前采样方法又把异常进一步放大了。
- 所以这里是“双重问题”：
  - 数据里有真实异常事件
  - 现有校准采样口径让异常更严重

## 4. verify pulse count 证据

`wafer_xy7.csv` 中，`bePGM` 高阻尾部和高 `verify pulse count` 高度绑定。

### 原始高阻尾

- `bePGM > 5000Ω`: `3482` rows
- `bePGM > 10000Ω`: `302` rows
- `bePGM > 5000Ω` 且 `verify pulse count > 10`: `3482` rows

高阻行的 verify count 最高频值：

- `40`: `3482`

也就是说：

- 所有 `>5000Ω` 的异常 LRS 行都对应高 verify count
- 其中绝大多数直接卡在 `40`

高阻样本示例：

- `R_cell=189573.46, verify=40, die=(12,6), cyc=13`
- `R_cell=189573.46, verify=40, die=(12,6), cyc=38`
- `R_cell=186741.36, verify=40, die=(12,6), cyc=13`

对照地，[wafer_xy16.csv](/Users/bytedance/workspace/MNSIM-2.0/test_data/2T1R_cycle/wafer_xy16.csv) 没有类似规模的 `bePGM > 5000Ω` 尾部。

## 5. 过滤高 verify 事件后的变化

对 [wafer_xy7.csv](/Users/bytedance/workspace/MNSIM-2.0/test_data/2T1R_cycle/wafer_xy7.csv) 的 `bePGM` 做过滤：

### 不过滤

- mean: `3196.20`
- CV: `262.64%`
- median: `2352.39`

### `verify pulse count <= 10`

- n: `3023`
- mean: `2334.39`
- CV: `0.79%`
- median: `2339.84`
- p95: `2351.97`

### `verify pulse count <= 5`

- n: `1133`
- mean: `2326.35`
- CV: `1.00%`
- median: `2332.96`
- p95: `2351.53`

结论：

- 一旦剔除高 verify 的 `bePGM` 事件，`wafer_xy7` 的 LRS 立刻恢复到和 `wafer_xy16` 非常接近的水平。
- 这说明问题不在“普通 LRS 分布”，而在“失败/难编程事件被直接当成普通 LRS 样本纳入统计”。

## 6. 空间分布

`wafer_xy7` 的 `bePGM > 5000Ω` 高阻事件不是均匀散开的，而是集中在少数 die：

- `(8, 9)`: `300`
- `(12, 6)`: `299`
- `(11, 10)`: `298`
- `(10, 8)`: `297`
- `(10, 10)`: `286`

而 `bePGM > 10000Ω` 更集中：

- `(12, 6)`: `299`

结论：

- 这更像局部 die/区域异常，或者局部编程质量异常。
- 不像纯随机噪声，也不像解析脚本无差别把所有数据都读坏了。

## Final Diagnosis

综合判断：

1. 不是坏 CSV，也不是简单的解析字段错位。
2. `wafer_xy7` 确实包含异常器件/异常编程事件，尤其是 `bePGM` 的高 verify、高阻尾部。
3. 当前校准/提取逻辑也有问题：
   - 直接把这些高 verify 失败事件当普通 LRS 样本
   - 使用前 `50k` 行采样，进一步放大异常

所以最准确的说法是：

`wafer_xy7` 不是“纯坏数据”，也不是“纯解析错误”；它包含真实异常编程事件，而当前 calibration/preset extraction 逻辑把这些异常事件直接并入普通 LRS 统计，导致异常被显著放大。`

## Suggested Fixes

1. `pim_sim.device.calibrate.calibrate_from_wafer_csv()`
   - 不要默认只读前 `50k/100k` 行
   - 改成全量或分层抽样

2. `dse/extras/extract_measured_presets.py`
   - `bePGM` 统计时增加 `verify pulse count` 过滤或分桶
   - 至少把高 verify 事件单独统计成 stress/failure scenario

3. measured preset 生成
   - `weak` 场景不应直接混入 `wafer_xy7` 的失败事件和普通 LRS 统计
   - 可以拆成：
     - `weak_clean`
     - `weak_with_failures`

4. 统计口径
   - 优先使用 median / trimmed CV / robust percentile
   - 不要只用 raw mean/std
