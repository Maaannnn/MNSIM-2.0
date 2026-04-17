# 借鉴清单：从 `NeuroSim` 到 `MNSIM` 的可迁移机制

本文档基于官方 `NeuroSim` 仓库与 `2DInferenceV1.5-dev` 分支的公开源码阅读整理，目标不是评价谁“更好”，而是回答：

- `NeuroSim` 为什么在精度侧更强
- 哪些机制可以迁移到当前 `MNSIM-2.0` 仓库
- 哪些不能直接照搬

主要参考源码与说明：

- 官方仓库 README: [NeuroSim](https://github.com/neurosim/NeuroSim)
- `2DInferenceV1.5-dev` README: [README.md](https://raw.githubusercontent.com/neurosim/NeuroSim/2DInferenceV1.5-dev/README.md)
- 推理入口: [inference.py](https://raw.githubusercontent.com/neurosim/NeuroSim/2DInferenceV1.5-dev/inference.py)
- 量化与校准入口: [quantize.py](https://raw.githubusercontent.com/neurosim/NeuroSim/2DInferenceV1.5-dev/quantize.py)
- 阵列级前向与非理想注入: [macro.py](https://raw.githubusercontent.com/neurosim/NeuroSim/2DInferenceV1.5-dev/pytorch-quantization/pytorch_quantization/cim/modules/macro.py)
- 状态查找表示例: [mem_states.csv](https://raw.githubusercontent.com/neurosim/NeuroSim/2DInferenceV1.5-dev/mem_states.csv)

## 1. 最重要的结论

`NeuroSim` 在精度侧比当前 `MNSIM` 更强，核心不是因为它“更慢”，而是因为它把非理想建模组织成了一个更清晰的前向评估框架。

它的关键特点是：

1. 非理想不是零散开关，而是统一进入阵列级前向路径
2. 量化不是拍脑袋固定范围，而是先做 calibration
3. 器件状态不是只靠一个 `variation%`，而是可以通过状态均值/方差表驱动
4. retention、stuck fault、read noise、output noise 都能进入一次前向
5. 噪声采样是可控的，带种子与可复现思路

这几点正好对准了 MNSIM 当前最弱的地方。

## 2. NeuroSim 为什么精度更强

## 2.1 它先做 calibration，再做 hardware simulation

从 `quantize.py` 可以看到，`NeuroSim` 在跑硬件精度前，不是直接上硬件噪声，而是先做了：

- 输入量化校准
- 权重量化校准
- ADC 量化校准

对应接口：

- `input_calib_method`
- `weight_calib_method`
- `adc_calib_method`

并支持：

- `max`
- `histogram`

这比 MNSIM 当前的：

- `SCALE`
- `FIX`

要强得多，因为它不是单次 batch 的临时缩放，而是先收集分布、再确定量化边界。

## 2.2 它把 memory state 做成了可外部定义的 LUT

这是最值得你学的地方之一。

`NeuroSim` 允许通过 `mem_states.csv` 提供每个 memory state 的：

- `mean`
- `std`

例如示例文件：

```csv
states,mean,std
0,1e-15,0
1,1e-14,0
```

这意味着：

- 它不是只知道 “ON/OFF 两个理想值”
- 而是可以把每个状态当作一个统计分布来采样

然后在 `macro.py` 中：

- `conductance_sampling()` 会基于状态表对每个 cell 采样
- 采样是按 `mean/std` 进行的

这比 MNSIM 当前：

- 读配置中的 `Device_Resistance`
- 再统一乘一个 `variation%`

要细致得多。

## 2.3 它把 retention 和 drift 作为前向里的显式参数

在 `inference.py` 中，直接暴露了：

- `t`
- `v`
- `detect`
- `target`

在 `macro.py` 的 `calc_drift()` 里：

- 对 memory states 和 reference states 做 retention/drift 变换

也就是说：

- drift 不是研究计划里的 TODO
- 而是前向仿真的一等公民

这正是当前 MNSIM 缺的时间维度。

## 2.4 它不仅有 read noise，还有 output noise LUT

在 `macro.py` 的 `ADC_output()` 里可以看到：

- `read_noise` 会直接施加在 `memory_states`
- `output_noise` 可以有两种模式：
  - 常数标准差
  - 从 `output_noise_file` 读取

更关键的是：

- 当 `output_noise == -1` 时，会按理想 ADC 输出码 `ADC_out_ref` 去索引 `output_noise_means` 和 `output_noise_stds`

这非常像一个：

- `ADC code -> noise statistics`

的查找表机制。

这比 MNSIM 当前“统一量化截断”高级很多，因为它允许：

- 噪声和输出码相关
- 高码值和低码值噪声行为不同

## 2.5 它把 stuck-at-fault 也做成了前向可控采样

`macro.py` 里的 `stuck_at_fault_sample()` 不是简单随机改几个权重值，而是：

- 先把权重转成 bit representation
- 再按 bitcell / cells_per_weight 的组织方式插 fault

这意味着它的 fault 注入更贴近：

- bitcell 组织
- 多 bit 权重映射方式

而不是只在最终浮点权重上粗暴盖噪声。

## 2.6 它的量化和阵列划分是一体的

`macro.py` 里 `simulate_array()` 会显式考虑：

- `sub_array`
- `parallel_read`
- `dac_precision`
- `bitcell`
- `cells_per_weight`
- `cycles_per_input`

并在分 bit、分 cell、分 partition 的层面计算部分和。

这让它的精度仿真和阵列执行方式是联动的，而不是分开的。

## 3. 对 MNSIM 最值得学的具体点

下面只列最值得迁移的，不列所有可能性。

## 3.1 第一优先级：把 `mem_states.csv` 机制学过来

### NeuroSim 做法

- 外部 CSV 定义 memory state 的 `mean/std`
- 前向时按状态采样 conductance

### 对 MNSIM 的迁移建议

当前 MNSIM 可以新增一个类似：

- `device_states.csv`

格式建议：

```csv
state,mean_resistance,std_resistance
0,1e6,5e4
1,1e4,8e2
```

如果后面要支持多级态：

```csv
state,mean_conductance,std_conductance
0,...
1,...
2,...
3,...
```

然后把 `Weight_update.py` 的逻辑从：

- `ideal resistance + variation%`

改成：

- 查 state LUT
- 按 state-specific mean/std 采样

### 为什么这件事最值

- 开发代价低
- 直接提升保真度
- 与 measured preset 非常契合
- 很适合从真实 `test_data` 抽统计量

## 3.2 第二优先级：把 `ADC calibration` 机制学过来

### NeuroSim 做法

在 `quantize.py` 中：

- 先对输入/权重/ADC 收集 histogram 或 max statistics
- 再算 `amax`
- 再进入硬件前向

### 对 MNSIM 的迁移建议

当前 MNSIM 至少应新增第三种模式：

- `CALIB`

流程：

1. 用少量 calibration batch 跑一遍
2. 为每层保存激活/部分和分布范围
3. 固定该层 ADC 量化范围
4. 正式评估时使用固定范围

### 为什么值

- 比 `SCALE` 更接近真实部署
- 比 `FIX` 更合理
- 改动集中在软件前端，不用动大块 C++ 硬件模型

## 3.3 第三优先级：把 `output_noise LUT` 思想学过来

### NeuroSim 做法

`ADC_output()` 中支持：

- 理想输出码 -> 均值/方差查表

### 对 MNSIM 的迁移建议

对当前 MNSIM，不一定要完整复刻，但可以做一个轻量版本：

- 新增 `adc_output_noise.csv`

例如：

```csv
code,mean,std
0,0.0,0.02
1,1.0,0.03
2,2.0,0.05
...
```

前向评估时：

- 先得到理想量化码
- 再按该码采样实际输出

### 为什么值

- 可以把 ADC 的非理想从“统一截断”升级成“码相关误差”
- 特别适合研究低 bit ADC 在 measured preset 下的行为

## 3.4 第四优先级：把 drift/retention 做成 preset 的正式字段

### NeuroSim 做法

在命令行层面就支持：

- `t`
- `v`
- `detect`
- `target`

### 对 MNSIM 的迁移建议

当前 measured preset CSV 建议扩展：

- `drift_v`
- `retention_t`
- `drift_mode`
- `drift_target`

然后在前向中用简化版 `calc_drift` 做状态变换。

### 为什么值

- 不需要完整复现 NeuroSim 的实现
- 但能把 measured preset 从静态快照升级成带时间维度的场景

## 3.5 第五优先级：把 fault 注入下沉到 bit/cell 层

### NeuroSim 做法

- fault 是按 cell / bit 分布作用的

### 对 MNSIM 的迁移建议

当前 `Weight_update.py` 是直接对最终量化权重做替换。  
更合理的下一步是：

- 在 bit-split 后的表示上注入 fault
- 让 fault 与 `weight_bit_split_part`、`xbar_polarity`、bitcell 数相关

### 为什么值

- 能让 `SAF` 和映射方式有耦合
- 对“不同编码策略谁更鲁棒”更有解释力

## 4. 哪些东西不能直接照搬

## 4.1 不要直接照搬整个 TensorRT 量化栈

`NeuroSim V1.5` 的量化前端很强，但它依赖：

- `pytorch_quantization`
- TensorRT 风格的 calibration pipeline
- 自定义 `cim` modules

这套东西太重，不适合直接塞进当前 MNSIM 仓库。

更合理的是：

- 借它的思路
- 自己实现一个轻量 calibration 版 MNSIM 前端

## 4.2 不要试图完整复制它的 array simulator

`macro.py` 之所以复杂，是因为它已经把：

- bit-serial input
- bitcell partition
- ADC output
- memory state sampling

都揉到一条前向链里了。

这很强，但如果你现在直接把整套搬到 MNSIM：

- 工程量大
- 会重写很多已有逻辑
- 很可能把“快”这个优势也丢掉

更好的做法是：

- 只移植最关键的统计接口与 LUT 机制

## 4.3 许可证问题不能忽略

官方 README 里明确写了：

- `NeuroSim` 代码按 `CC BY-NC 4.0` 非商业方式开放

所以：

- 学思路、重写自己的实现通常没问题
- 直接大段复制源码、嵌入到未来可能商业化或许可不兼容的项目里，要非常谨慎

对你当前最稳妥的策略是：

- 借鉴机制
- 自己实现
- 在论文和文档中明确说明 inspiration 来源

## 5. 我对 “LUT 能不能拿来用” 的判断

可以学，而且非常值得学。  
但我建议拿的是“机制”，不一定直接拿它的文件原样。

最值得迁移的 LUT 思路有两个：

### 5.1 Memory state LUT

- `state -> mean/std`

这是最值得立刻迁移到 MNSIM 的。

### 5.2 ADC output noise LUT

- `ADC output code -> mean/std`

这是第二值得迁移的。

这两个 LUT 都很适合：

- 从你现有 `test_data` 里抽统计
- 再喂给 MNSIM 的轻量精度后端

## 6. 如果现在就要行动，我建议这样排优先级

### Phase 1

- 在 MNSIM 中新增 `device_states.csv` 机制
- 重写 `Weight_update.py` 让其支持 per-state mean/std

### Phase 2

- 新增 `CALIB` ADC 模式
- 用少量 calibration batch 固定每层量化范围

### Phase 3

- 新增 `adc_output_noise.csv`
- 做 code-dependent ADC output noise

### Phase 4

- 把 `drift / retention` 接入 measured preset

## 7. 一句话结论

`NeuroSim` 最值得你学的，不是把整个框架搬过来，而是学它这套思想：

把非理想性从“几个粗粒度百分比参数”，升级成“前向路径中可校准、可查表、可采样、可复现的统计对象”。

这正是当前 MNSIM 最需要补的地方。
