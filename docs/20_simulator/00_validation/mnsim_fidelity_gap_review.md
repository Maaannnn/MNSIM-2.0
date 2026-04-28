# 仿真器审视：`MNSIM` 保真度缺口与增强建议

本文档基于当前仓库中的 `MNSIM` 源码、`dse/core.py` 调用方式和现有配置进行审视，目标是回答：

- 当前 `MNSIM` 的主要保真度短板在哪里
- 哪些短板会直接影响你当前的 RRAM DSE / measured preset 研究
- 在不转向 `NeuroSim/CrossSim` 的前提下，我们能做哪些具体增强

## 1. 先给结论

如果目标是“比 `NeuroSim/CrossSim` 快很多，同时又尽量补齐最关键的保真度短板”，当前仓库里最值得优先改的不是重写全套模型，而是这四类增强：

1. 把 `accuracy` 从单次随机注入改成可重复、可统计的多 seed / 多 scenario 评估
2. 把 `IR drop` 从激活无关的简化项升级成输入相关的近似模型
3. 把 `ADC` 从静态均匀量化升级成层感知或运行前校准的量化范围模型
4. 把 `measured preset` 从只改 `variation/SAF/Ron-Roff`，升级成可注入 `drift/retention/nonlinearity` 的轻量参数包

如果只能做一件事，优先做第 1 条。  
如果只能做两件事，做第 1 条和第 2 条。

## 2. 当前 MNSIM 的主要短板

## 2.1 `accuracy` 路径和 `PPA` 路径并没有真正共用同一套物理模型

当前 `dse/core.py` 的评估逻辑是：

- `PPA` 由 `TCG + latency/area/power/energy` 模块计算
- `accuracy` 由 `TrainTestInterface + weight_update + set_net_bits_evaluate` 计算

也就是说，`accuracy` 侧主要依赖：

- 权重扰动
- SAF
- ADC 量化

而 `PPA` 侧主要依赖：

- 解析式的 latency / area / power
- 接口和架构参数查表与组合

它们之间并不是强耦合的“同一物理世界”，而更像：

- 一边是系统级成本估算
- 一边是近似噪声注入后的前向精度评估

这会带来一个问题：

- 某些影响精度的真实物理因素，并不会同步反映到 `PPA` 的成本变化上
- 某些 `PPA` 改动也不一定真实反映到噪声模型的变化中

## 2.2 器件变异建模过于粗糙

`MNSIM/Accuracy_Model/Weight_update.py` 的核心做法是：

- 根据 `Device_Variation` 对目标电阻加高斯扰动
- 再转换成导通值

主要问题：

- 没有区分不同阻态的不同方差模型
- 没有状态依赖、层依赖、时间依赖
- 没有把 variation 和输入分布、读电压、写入精度联系起来
- 只是在权重级静态扰动，没有真正建模“同一器件在运行时的动态行为”

这使它更像：

- “带噪权重注入器”

而不是：

- “器件物理近似器”

## 2.3 `IR drop` 建模明显偏简化

从源码和现有分析文档看，当前 `IR drop` 有两个问题：

1. `Crossbar_accuracy.py` 中的做法非常粗糙  
   直接把 `wire_resistance * (self.row + j - i + 1)` 叠到电阻上

2. 主路径中的 crossbar latency / power 也没有输入相关的电流分布求解  
   当前更接近平均意义或简化解析估算

这意味着当前模型很难表达：

- 激活稀疏度不同导致的 `IR drop` 差异
- 不同输入 pattern 对边缘单元和中心单元的不同影响
- 大阵列在某些层和某些输入下比平均情况更差

而这恰恰是：

- `512x512` 是否还能成立
- `ADC` 是否需要补偿
- measured preset 是否会导致最优点迁移

这些研究问题的核心来源之一。

## 2.4 `ADC/DAC` 模型偏静态查表

`MNSIM/Hardware_Model/ADC.py` 和 `DAC.py` 主要是：

- 固定 choice -> 固定 area / precision / power / sample_rate
- ADC 区间通过简单公式生成
- 精度路径里的量化主要是 `SCALE` / `FIX` 两种数字近似

问题在于：

- 没有层输出分布驱动的动态范围优化
- 没有 DNL / INL / offset / comparator variation 这类轻量非理想
- `SCALE` 模式其实更接近“理想校准后的动态量化”
- `FIX` 模式虽然更接近部署，但仍然非常理想化

所以当前模型能回答：

- `ADC bit` 大概够不够

但很难回答：

- 某层为什么在 4-bit ADC 下突然失效
- 为什么 measured preset 下需要更高 ADC 裕量
- 自适应量化是否有真正价值

## 2.5 缺少时间维度：`drift / retention / aging`

当前最明显缺的就是时间维度。

你现在的 preset 已经能表达：

- `Ron/Roff`
- `variation`
- `SAF`

但还不能自然表达：

- `drift`
- `retention loss`
- 长期部署后的权重漂移

这意味着 measured preset 目前更像：

- 某一时刻的快照

而不是：

- 某个器件状态随时间演化的场景

## 2.6 没有组合非理想性机制的统一入口

当前可以开：

- `variation`
- `SAF`
- `ADC quantization`

但它们更像几个独立开关。

缺少的是：

- 一个统一的“非理想场景对象”
- 让 `variation + ADC + IR drop + drift` 以一致方式进入前向评估

这会导致后面做 robustness 时容易只是在外层套壳，而不是内核真正理解 scenario。

## 2.7 有些 PPA 子模块本身就带明显经验项

源码里大量 `TODO` 和静态经验式说明：

- `Crossbar.py` 中 wire resistance / capacity 默认值和 latency 公式较硬
- `PE.py` / `Tile.py` 中多处写着 `TODO: add circuits simulation results`
- `Device.py` 里甚至有明显 bug：`assert self.type == "NVM"`，应为 `self.device_type`

这说明当前框架的定位本来就偏：

- 快速系统级估算

而不是：

- 对电路级真实物理现象进行高保真复现

## 3. 结合你当前课题，哪些短板最痛

不是所有短板都同样重要。对你现在这个课题，最痛的是以下 4 个。

## 3.1 `IR drop` 的输入相关性不足

因为你现在很关心：

- 大阵列是否真优
- `ADC` 是否补偿器件退化
- 不同 preset 下最优点是否迁移

如果 `IR drop` 一直是激活无关的平均项，这类问题的结论会偏弱。

## 3.2 `ADC` 模型太理想

因为你已经把 `adc_choice` 当成核心设计变量了。  
如果 `ADC` 本身只是一套静态查表 + 近似量化，后面论文里关于“ADC 是补偿手段”的论证会缺支撑。

## 3.3 缺少 `drift / retention`

因为你手上有真实 `test_data`。  
如果 measured preset 最终只映射成 `variation + SAF + Ron/Roff`，会浪费这批数据的价值。

## 3.4 缺少统计评估规范

因为当前结论如果只来自单次带噪前向，鲁棒优化会显得名不副实。

## 4. 可执行增强项

下面按“投入小 / 收益大”的顺序给出建议。

## 4.1 第一优先级：做“多 seed 统计 accuracy”

### 做法

在 `dse/core.py` 的 `run_accuracy` 路径外，再包一层：

- 多次采样 `weight_update`
- 每次返回 accuracy
- 汇总：
  - `accuracy_mean`
  - `accuracy_std`
  - `accuracy_worst`
  - `feasibility_rate`

### 为什么值

- 不改 MNSIM 内核太多
- 直接让你的 robust search 更可信
- 能马上服务论文

### 涉及位置

- `dse/core.py`
- `MNSIM/Accuracy_Model/Weight_update.py`
- `dse/output.py`
- `dse/analyze_results.py`

### 额外建议

给 `weight_update` 增加显式随机种子参数，保证复现实验。

## 4.2 第二优先级：把 `IR drop` 变成输入相关近似模型

### 做法

不要一开始追求完整矩阵电路求解。  
先做一个轻量增强版：

- 根据每次前向输入的激活稀疏度、均值、峰值
- 对每个子阵列构造一个 `ir_drop_factor`
- 让该因子影响：
  - 有效读电压
  - 或输出部分和缩放
  - 或 ADC 输入动态范围

可先使用如下近似：

- `ir_drop_factor = f(array_size, active_rows, mean_activation, wire_resistance, load_resistance)`

### 为什么值

- 比当前固定解析式更真实
- 仍然远快于 `CrossSim`
- 特别适合比较不同输入分布和 measured preset 的交互

### 涉及位置

- `MNSIM/Interface/quantize.py`
- 或新增一个 `MNSIM/Accuracy_Model/ir_drop_proxy.py`

## 4.3 第三优先级：给 ADC 加“层感知固定范围校准”

### 做法

保留现有 `SCALE` / `FIX` 两种模式，再新增一个中间模式，例如：

- `CALIB`

逻辑：

1. 用少量 calibration batch 跑一遍网络
2. 为每一层统计输出分布
3. 固定每层 ADC range
4. 正式评估时使用该固定范围，而不是每个 batch 动态缩放

### 为什么值

- 比 `SCALE` 更接近实际部署
- 比 `FIX` 更合理
- 几乎不增加太多运行成本

### 涉及位置

- `MNSIM/Interface/quantize.py`
- `MNSIM/Interface/interface.py`

## 4.4 第四优先级：把 measured preset 扩展到 `drift / retention`

### 做法

在 measured preset CSV 里新增字段，例如：

- `drift_alpha`
- `retention_drop_pct`
- `noise_sigma_read`
- `nonlinearity_alpha`

然后在 `weight_update` 或前向评估中增加轻量模型：

- 漂移：`G(t) = G0 * (t / t0)^(-v)` 的简化版
- retention：按层或全局对 conductance 做衰减
- 读噪声：按状态相关 sigma 注入

### 为什么值

- 这会让 measured preset 真正成为贡献点
- 不需要引入完整物理仿真
- 只要模型形式清楚，就足够支持论文中的“现实场景驱动优化”

## 4.5 第五优先级：显式引入“scenario object”

### 做法

不要再把非理想开关散落成多个布尔量。  
定义统一结构：

- `scenario = {preset, variation_mode, saf_mode, drift_mode, adc_mode, ir_drop_mode, seed}`

然后：

- `evaluate_config` 接收 scenario
- `weight_update` 和 forward 根据 scenario 行为一致

### 为什么值

- 后面做 robustness 会更自然
- 也更方便接 measured preset
- 让实验记录更清晰

## 4.6 第六优先级：修复一些明显实现问题

这些问题不一定是保真度核心，但值得顺手修：

- `Device.py` 中 `assert self.type == "NVM"` 应修成 `self.device_type`
- `Crossbar_accuracy.py` 的 `Device_SAF` 被 `map(int, ...)`，会丢掉小数比例
- `Crossbar_accuracy.py` 的电阻扰动和线阻叠加方式过粗
- `DAC.py` 中 `8-bit` 功耗看起来异常大，建议核对量纲

## 5. 我建议的落地路线

最现实的路线不是“一次把 MNSIM 变成 CrossSim”，而是：

### Phase A：一周内可做

- 多 seed 统计 accuracy
- scenario 结构化
- 修几个明显 bug

### Phase B：两到三周可做

- 层感知 ADC calibration 模式
- 输入相关 IR-drop proxy

### Phase C：后续增强

- measured preset 扩展到 drift / retention / nonlinearity
- 关键结论的 second-tool validation 预留接口

## 6. 一句话建议

你现在最值得做的，不是让 `MNSIM` 变成一个慢版 `CrossSim`，而是让它从“快但偏粗的架构估算器”，升级成“仍然很快，但对 `统计鲁棒性 + 输入相关 IR-drop + ADC 校准 + measured preset` 更敏感的研究型 DSE 引擎”。
