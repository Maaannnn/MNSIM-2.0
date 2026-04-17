# 补充建议：面向 RRAM 论文的 MNSIM + DSE 设计建议

本文档保留为补充参考版本。当前主入口已经收敛到：

- [RRAM_DSE_Problem_Formulation_And_Method.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/RRAM_DSE_Problem_Formulation_And_Method.md)

## 1. 目标定位

本文档面向这样一类论文目标：

- 使用 `MNSIM + DSE` 为 **RRAM 存内计算加速器**提供设计指导
- 关注 **PPA + Accuracy** 的多目标折中
- 进一步强调 **器件非理想下的鲁棒性**

结论先行：

- 目前仓库中的 DSE 更适合做“体系结构参数的 PPA 搜索”
- 若论文要突出 **RRAM 特性**，则设计空间必须从“架构参数空间”扩展为“器件-接口-架构协同空间”
- 若论文还想再上一个层次，最值得补的方向不是更复杂的优化算法，而是 **非理想器件建模**，尤其是 **非线性导通行为**


## 2. 当前 DSE 的定位与局限

当前代码中的 DSE 设计空间定义在 [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py#L31)。

现有采样维度包括：

- `xbar_size`
- `adc_choice`
- `dac_choice`
- `pe_num`
- `tile_connection`
- `inter_tile_bw`
- `intra_tile_bw`

这些维度的特点是：

- 主要集中在 **阵列规模、接口选择、tile/NoC 连接**
- 更偏向 **架构层和接口层**
- 没有把 `RRAM` 最关键的 **器件非理想参数** 放进设计空间

另外，当前主优化目标实际上是：

- `latency`
- `energy`
- `area`

对应逻辑见 [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py#L153)。

虽然系统支持运行 `accuracy`，但 `accuracy` 没有真正进入多目标主搜索闭环，只是附加结果。因此现阶段更像：

- “PPA DSE”

而不是：

- “PPA + Accuracy + Robustness 的 RRAM 协同设计”


## 3. 适合 RRAM 论文的新 SPACE

建议不要直接把所有参数都离散展开，否则空间会膨胀得太快。更合适的方法是建立一个 **分层 SPACE**：

- A 类：论文主采样维度，直接进入 DSE
- B 类：场景配置维度，不一定进同一个 DSE，但必须作为实验轴
- C 类：固定背景参数，用于定义对比基线


### 3.1 建议的主 SPACE

下面这组参数足以支撑一篇“RRAM 导向的 DSE 设计指导”论文。

| 参数名 | 中文解释 | 所在层级 | 作用 | 建议取值 |
|---|---|---|---|---|
| `xbar_size` | 交叉阵列尺寸 | 阵列层 / Crossbar level | 决定并行度、阵列复用效率、IR drop 风险、ADC 压力 | `(128,128)`, `(256,256)`, `(512,512)` |
| `adc_choice` 或 `adc_precision` | ADC 类型/精度 | 接口层 / Interface level | 决定读出精度、面积、功耗、时延，是模拟 CIM 的关键瓶颈 | `4`, `6`, `7`, `8` 或等效精度档 |
| `dac_choice` 或 `dac_num` | DAC 类型/数量 | 接口层 / Interface level / PE level | 决定输入展开并行度、吞吐和面积能耗 | `1`, `2`, `3`, `4` 或 `32`, `64`, `128` |
| `xbar_polarity` | 正负权实现方式 | PE 层 / Process element level | 决定正负权是否拆分到不同阵列，影响面积和误差传播 | `1`, `2` |
| `sub_position` | 正负阵列相减位置 | PE 层 / Process element level | 决定在模拟域还是数字域做减法，影响精度与开销 | `0`, `1` |
| `group_num` | PE 内交叉阵列组数 | PE 层 / Process element level | 决定并行分组和资源复用方式 | `1`, `2`, `4` |
| `pe_num` | Tile 内 PE 个数 | Tile 层 / Tile level | 决定 tile 级并行度和面积 | `(2,2)`, `(4,4)`, `(8,8)` |
| `tile_connection` | Tile 互连拓扑选择 | 架构层 / Architecture level | 决定片上通信模式和带宽瓶颈 | `0`, `1`, `2`, `3` |
| `inter_tile_bw` | Tile 间带宽 | Tile 层 / Tile level | 决定跨 tile 数据搬运瓶颈 | `10`, `20`, `40`, `80` |
| `rram_preset` | RRAM 器件非理想预设 | 器件层 / Device level | 统一抽象器件特性，避免直接展开连续器件参数 | `P0`, `P1`, `P2`, `P3` |


### 3.2 为什么引入 `rram_preset`

我不建议第一版就直接把以下连续变量全部丢进 SPACE：

- `Device_Resistance`
- `Device_Variation`
- `Device_SAF`
- `Read_Voltage`
- `Read_Latency`
- `Device_Area`

原因很简单：

- 空间会爆炸
- 多数参数强相关
- 难以形成论文上的“设计区间”结论

更好的办法是先构造 **器件预设**：

| `rram_preset` | 中文含义 | 典型含义 |
|---|---|---|
| `P0` | 理想器件基线 | 高 `Ron/Roff`，低 variation，低 SAF |
| `P1` | 中等非理想 | 中等 `Ron/Roff`，低中等 variation |
| `P2` | 高变化器件 | variation 高，读出稳定性差 |
| `P3` | 高缺陷器件 | SAF 高，代表制造偏差更明显 |

这样你在论文中可以研究：

- “最优架构是否会随着器件质量下降而迁移”
- “什么架构在器件退化下仍然鲁棒”

这比单纯扫一堆器件数值更容易形成设计指导。


## 4. 推荐的实验矩阵

我建议采用“三阶段实验矩阵”，每一阶段回答一个清晰问题。


### 阶段一：理想器件下的架构趋势

目的：

- 先在理想或轻非理想条件下建立 PPA 主趋势
- 找到高潜力区域

设置：

- `rram_preset = P0`
- 不开或弱开 `variation/SAF`
- workload 先用 `CIFAR10 + VGG8`

主采样 SPACE：

- `xbar_size`
- `adc_choice`
- `dac_num`
- `xbar_polarity`
- `group_num`
- `pe_num`
- `tile_connection`
- `inter_tile_bw`

回答的问题：

- 大阵列是否总能带来更好的能效
- ADC 是否成为主导瓶颈
- 最优点更受阵列规模还是互连约束影响


### 阶段二：非理想器件下的最优设计迁移

目的：

- 研究 RRAM 非理想增强后，设计最优点如何变化

设置：

- `rram_preset = P0/P1/P2/P3`
- 开启 `run_accuracy`
- 开启 `enable_variation`
- 开启 `enable_saf`

主问题：

- 当器件变差时，最优 `xbar_size` 是否从 `512` 退到 `256` 或 `128`
- 高 ADC 精度是否能抵消部分器件非理想
- `xbar_polarity=2` 是否比 `1` 更稳健


### 阶段三：鲁棒设计而不是单点最优

目的：

- 不是只找“平均最好”的点
- 而是找“在多次随机器件扰动下仍然稳定”的点

设置：

- 对每个候选配置重复多个 noise seed
- 记录均值、最差值、方差

建议记录：

- `mean_latency`
- `mean_energy`
- `mean_area`
- `mean_accuracy`
- `worst_accuracy`
- `accuracy_std`

回答的问题：

- 哪些架构是“脆弱最优”
- 哪些架构是“鲁棒次优”
- 在论文中，后者通常更有指导意义


## 5. 推荐的论文实验轴

建议不要只做一个网络。

更合理的实验轴如下：

| 实验轴 | 建议 |
|---|---|
| 工作负载 | `VGG8` + `VGG16`，或者 `VGG8` + 小型 `ResNet` |
| 器件场景 | `P0/P1/P2/P3` |
| 评价目标 | `latency`, `energy`, `area`, `accuracy_drop`, `worst_accuracy` |
| 优化形式 | `PPA` 最小化 + `accuracy` 约束 |

这里我建议论文主线采用：

- **约束优化**

即：

- 最小化 `latency/energy/area`
- 满足 `accuracy_drop <= 1%` 或 `accuracy >= baseline - delta`

原因是：

- 比直接做四目标 Pareto 更稳定
- 更适合形成工程指导
- 更容易讨论“在给定精度预算下，应该选什么设计”


## 6. 每个关键参数的中文解释与层级归属

这一节可以直接放论文方法部分。


### 6.1 器件层 Device level

#### `rram_preset`

- 中文：RRAM 器件特性预设
- 含义：用一个标签统一表示某组器件参数，例如 `Ron/Roff`、variation、SAF
- 作用：把器件非理想显式引入 DSE

#### `Device_Resistance`

- 中文：器件电阻状态
- 所在层级：器件层
- 含义：表示 HRS/LRS 或多级电阻状态
- 作用：影响导电电流、读出电压分布、功耗和读出可分辨性

#### `Device_Variation`

- 中文：器件阻值波动
- 所在层级：器件层
- 含义：表示实际阻值相对理想值的随机偏差
- 作用：直接影响模拟计算误差与精度退化

#### `Device_SAF`

- 中文：器件卡死故障比例
- 所在层级：器件层
- 含义：器件 stuck-at-HRS / stuck-at-LRS 的概率
- 作用：影响可靠性和权重映射正确性

#### `Device_Level`

- 中文：器件可表示电导级数
- 所在层级：器件层
- 含义：表示二值或多值存储能力
- 作用：决定单器件可承载的量化信息量


### 6.2 阵列层 Crossbar level

#### `xbar_size`

- 中文：交叉阵列尺寸
- 所在层级：阵列层
- 含义：单个 crossbar 的行列规模
- 作用：
  - 阵列越大，并行度越高
  - 但更容易出现 IR drop、线阻影响、读出困难
  - 同时会增加 ADC 压力和映射复杂度


### 6.3 接口层 Interface level

#### `adc_choice` / `adc_precision`

- 中文：模数转换器类型/精度
- 所在层级：接口层
- 含义：将阵列模拟输出转换成数字值的能力
- 作用：
  - 精度越高，理论精度更好
  - 但面积、功耗、延迟更大
  - 在模拟 RRAM-CIM 中通常是主要瓶颈之一

#### `dac_choice` / `dac_num`

- 中文：数模转换器类型/数量
- 所在层级：接口层 / PE 层
- 含义：负责将数字输入激励变成阵列可读入的模拟信号
- 作用：
  - 决定输入并行度
  - 影响面积、功耗和吞吐


### 6.4 PE 层 Process Element level

#### `xbar_polarity`

- 中文：正负权实现方式
- 所在层级：PE 层
- 含义：正权和负权是否分开映射到不同阵列
- 作用：
  - 影响面积开销
  - 影响误差叠加方式
  - 会改变精度与能耗的折中

#### `sub_position`

- 中文：差分相减位置
- 所在层级：PE 层
- 含义：正负阵列输出在模拟域还是数字域相减
- 作用：
  - 影响接口设计
  - 影响精度和时延

#### `group_num`

- 中文：PE 内阵列分组数
- 所在层级：PE 层
- 含义：一个 PE 内包含多少阵列组
- 作用：
  - 决定并行映射能力
  - 决定资源共享与复用方式


### 6.5 Tile 层 Tile level

#### `pe_num`

- 中文：Tile 中 PE 数量
- 所在层级：Tile 层
- 含义：每个 tile 内的并行处理单元数量
- 作用：
  - 决定 tile 级吞吐和面积
  - 也决定局部互连与缓存压力

#### `inter_tile_bw`

- 中文：Tile 间带宽
- 所在层级：Tile 层
- 含义：不同 tile 之间传输数据的带宽能力
- 作用：
  - 决定多 tile 映射时是否会被通信瓶颈限制

#### `intra_tile_bw`

- 中文：Tile 内带宽
- 所在层级：Tile 层
- 含义：PE 之间或本地数据通路的带宽能力
- 作用：
  - 影响局部并行效率


### 6.6 架构层 Architecture level

#### `tile_connection`

- 中文：Tile 互连拓扑
- 所在层级：架构层
- 含义：Tile 之间采用何种连接模式
- 作用：
  - 影响全局数据搬运代价
  - 影响延迟、带宽利用率和可扩展性

#### `tile_num`

- 中文：Tile 总数量
- 所在层级：架构层
- 含义：芯片整体可用 tile 数量
- 作用：
  - 决定全芯片峰值并行度
  - 也影响总面积和 NoC 复杂度


## 7. 建议的新实验矩阵

下面给出一版可直接执行的矩阵。


### 7.1 主实验矩阵

| 类别 | 参数 | 建议取值 |
|---|---|---|
| 器件层 | `rram_preset` | `P0`, `P1`, `P2`, `P3` |
| 阵列层 | `xbar_size` | `128`, `256`, `512` |
| 接口层 | `adc_choice` | `4`, `6`, `7`, `8` |
| 接口/PE层 | `dac_num` | `32`, `64`, `128` |
| PE层 | `xbar_polarity` | `1`, `2` |
| PE层 | `group_num` | `1`, `2`, `4` |
| Tile层 | `pe_num` | `(2,2)`, `(4,4)`, `(8,8)` |
| 架构层 | `tile_connection` | `0`, `1`, `2`, `3` |
| Tile层 | `inter_tile_bw` | `10`, `20`, `40`, `80` |

这套空间已经足够大，因此不要直接全枚举。


### 7.2 推荐采样流程

#### 第一步：分层随机采样

- 保证每个 `rram_preset`
- 每个 `xbar_size`
- 每个 `adc_choice`

都有足够覆盖

#### 第二步：代理模型搜索

- 用 NSGA-II 或 MOBO 搜索高潜力区

#### 第三步：精度与鲁棒性复评估

- 对 Pareto 候选做多次 noise seed 复评估


## 8. 是否值得补“器件非线性建模”

我认为：**值得，而且很可能是一个亮点。**

但前提是你要明确它的定位。


### 8.1 现在 MNSIM 的问题

从当前实现看，MNSIM 更偏向：

- 理想欧姆导通
- 阻值扰动
- SAF
- 有限级数映射

但没有真正描述很多实际 RRAM 会出现的：

- I-V 非线性
- 读电压依赖导通
- 状态相关非线性
- sneak path 下的非线性放大/抑制

因此它更像：

- “线性导通 + 随机扰动”的近似模型

而不是：

- “非线性器件行为参与计算结果”的模型


### 8.2 这会不会是亮点

会，而且比“换一个 DSE 算法”更像亮点。

因为你可以回答一个很有价值的问题：

- **如果忽略 RRAM 非线性，现有 DSE 得出的最优设计会不会是错的？**

这句话本身就像论文标题中的核心问题。

更具体地说，你可以做：

1. 线性器件模型下做 DSE，得到最优设计
2. 加入非线性器件模型后重新评估这些设计
3. 比较：
   - Pareto front 是否迁移
   - 最优 `xbar_size` 是否变化
   - 高并行大阵列是否因为非线性而失去优势

如果出现显著迁移，这就是一个很强的结论。


### 8.3 但要不要现在就做

我的建议是：

- 如果你想先尽快完成一篇“稳妥可写”的论文，先做 **RRAM preset + accuracy/robustness DSE**
- 如果你想做更强一点的贡献，再加 **非线性建模**

换句话说：

- `第一优先级`：把 RRAM 非理想和 accuracy 真正纳入 DSE
- `第二优先级`：补器件非线性

原因是：

- 如果连器件 preset 和 accuracy constraint 都没进 DSE，直接讲非线性会显得主线发散
- 先把框架搭完整，再加非线性，会形成更清晰的故事线


### 8.4 非线性建模最合适的切入方式

不建议你第一版就做很复杂的物理模型拟合。

建议做一个 **参数化非线性导通模型**，例如：

- `I = G * V`
- 改成
- `I = G * f(V)`

其中 `f(V)` 可以是简单的非线性函数族，例如：

- 幂函数型
- 指数近似型
- 分段线性型

然后定义一个 `nonlinearity_alpha`

- `alpha = 0` 表示线性
- `alpha` 增大表示非线性增强

论文里就可以研究：

- 非线性强度上升时，最佳阵列尺寸如何变化
- ADC 精度需求是否上升
- 鲁棒最优点是否迁移

这是一个非常适合 DSE 讲故事的维度。


## 9. 我对你论文路线的建议

如果你要兼顾可落地性和亮点，我建议这样排优先级：

### 路线 A：稳妥版

- 重构 DSE 空间
- 引入 `rram_preset`
- 加入 `accuracy` 约束
- 做鲁棒性复评估

这条路线已经足以写一篇不错的“设计指导”型论文。


### 路线 B：增强版

在路线 A 基础上再加：

- 参数化非线性导通模型

这时你的贡献就可以写成：

- 提出一个面向 RRAM 非理想与非线性器件的 MNSIM-DSE 协同设计框架

这比单纯做架构扫参更有研究味道。


## 10. 最终建议

一句话总结：

- **要做 RRAM 论文，就必须把“器件差异”变成 DSE 的一等公民。**

具体落地上，建议先做：

1. 新 SPACE：加入 `rram_preset`
2. 新目标：`PPA + accuracy constraint`
3. 新评价：加入 robustness
4. 新实验：比较不同器件场景下 Pareto 最优点迁移

然后，如果时间和精力允许，再把：

5. 非线性导通模型

加进去作为亮点增强。
