# 方法骨架：RRAM-CIM DSE 的问题定义、方法与实验设计

## 1. Problem Formulation

### 1.1 研究目标

本文研究面向 `RRAM` 存内计算加速器的多目标设计空间探索问题。目标是在给定任务负载和器件场景下，联合优化器件层、接口层和架构层参数，在满足精度约束的前提下，获得更优的时延、能耗和面积折中，并分析最优设计随器件非理想变化的迁移规律。

本文的核心思想不是单独优化某一个层级，而是进行：

- 器件-接口-架构协同设计

对应地，设计空间探索需要同时刻画：

- 器件质量
- 电路读写与量化开销
- 阵列与 PE 组织方式
- 系统级通信瓶颈


### 1.2 设计变量

设一个候选硬件设计记为 `x`，其由如下变量组成。


#### 1.2.1 器件层变量

- `rram_preset`
  - 中文：RRAM 器件预设
  - 含义：用一个标签表示一组器件特性，例如 `Ron/Roff`、variation、SAF 等
  - 作用：将器件非理想显式纳入 DSE

- `nonlinearity_alpha`（可选扩展）
  - 中文：器件非线性强度
  - 含义：表示器件 I-V 偏离理想欧姆定律的程度
  - 作用：用于研究线性模型与非线性模型下最优设计是否迁移


#### 1.2.2 阵列层变量

- `xbar_size`
  - 中文：交叉阵列尺寸
  - 含义：单个 crossbar 的行列规模
  - 作用：决定阵列并行度、映射效率、接口压力以及潜在线阻误差


#### 1.2.3 接口层变量

- `adc_choice` 或 `adc_precision`
  - 中文：模数转换器类型或精度
  - 含义：阵列输出到数字域的量化能力
  - 作用：直接影响精度、时延、面积和功耗

- `dac_choice` 或 `dac_num`
  - 中文：数模转换器类型或数量
  - 含义：输入信号写入阵列前的转换资源
  - 作用：影响输入并行度、吞吐和面积开销


#### 1.2.4 PE 层变量

- `xbar_polarity`
  - 中文：正负权实现方式
  - 含义：正权与负权是否使用不同阵列表示
  - 作用：影响误差传播方式和硬件资源开销

- `sub_position`
  - 中文：差分相减位置
  - 含义：正负阵列输出在模拟域还是数字域相减
  - 作用：影响量化误差和电路复杂度

- `group_num`
  - 中文：PE 内阵列分组数
  - 含义：一个 PE 内包含的阵列组数量
  - 作用：影响并行计算方式和资源复用方式


#### 1.2.5 Tile / 架构层变量

- `pe_num`
  - 中文：Tile 内 PE 数量
  - 含义：每个 tile 中可并行工作的 PE 个数
  - 作用：影响 tile 级吞吐和面积

- `tile_connection`
  - 中文：Tile 互连拓扑
  - 含义：不同 tile 之间采用何种连接结构
  - 作用：影响片上数据搬运代价与系统扩展性

- `inter_tile_bw`
  - 中文：Tile 间带宽
  - 含义：tile 与 tile 之间的数据传输能力
  - 作用：影响跨 tile 映射下的通信瓶颈


### 1.3 设计变量形式化

因此，一个设计点可表示为：

```text
x = {rram_preset, xbar_size, adc_choice, dac_num,
     xbar_polarity, sub_position, group_num,
     pe_num, tile_connection, inter_tile_bw}
```

若进一步考虑器件非线性，则设计点扩展为：

```text
x = {rram_preset, nonlinearity_alpha, xbar_size, adc_choice, dac_num,
     xbar_polarity, sub_position, group_num,
     pe_num, tile_connection, inter_tile_bw}
```


### 1.4 输出指标

对任意设计点 `x`，通过 `MNSIM` 仿真得到如下输出。


#### 1.4.1 PPA 指标

- `L(x)`
  - 中文：推理时延
  - 含义：完成一次推理所需的总时间

- `E(x)`
  - 中文：推理能耗
  - 含义：完成一次推理消耗的总能量

- `A(x)`
  - 中文：芯片面积
  - 含义：设计对应的硬件资源占用面积


#### 1.4.2 精度指标

- `Acc(x)`
  - 中文：推理精度
  - 含义：在给定数据集上的任务精度

- `Drop(x)`
  - 中文：精度损失
  - 定义：

```text
Drop(x) = Acc_base - Acc(x)
```

其中 `Acc_base` 表示软件基线或理想硬件模型下的基准精度。


#### 1.4.3 鲁棒性指标

在器件存在随机扰动时，对同一设计点重复评估多次，定义：

- `Acc_mean(x)`
  - 中文：平均精度

- `Acc_worst(x)`
  - 中文：最差精度

- `Acc_std(x)`
  - 中文：精度标准差

- `Yield(x)`
  - 中文：精度达标率
  - 含义：在多次随机扰动中满足精度约束的比例


### 1.5 优化目标

本文采用“多目标优化 + 精度约束”的问题定义，而不是直接将精度作为第四个目标。这样定义更接近真实硬件设计流程，因为工程上通常首先要求设计满足可接受精度，然后在满足约束的设计中比较 PPA。

优化问题可写为：

```text
minimize   {L(x), E(x), A(x)}
subject to Drop(x) <= δ
```

其中：

- `δ` 为最大允许精度损失，例如 `1%`

若进一步考虑鲁棒性，则加入：

```text
Acc_worst(x) >= Acc_min
```

于是问题变为：

```text
minimize   {L(x), E(x), A(x)}
subject to Acc(x) >= Acc_base - δ
           Acc_worst(x) >= Acc_min
```


### 1.6 研究问题

本文主要回答以下三个研究问题。

#### RQ1：在给定精度约束下，哪些设计变量主导 RRAM-CIM 的最优 PPA 设计？

这一问题关注：

- `xbar_size` 是否是主导变量
- ADC 精度是否成为系统瓶颈
- PE 并行度和片上带宽是否限制阵列规模收益


#### RQ2：当 RRAM 器件非理想增强时，最优设计是否发生迁移？

这一问题关注：

- 理想器件下的最优点，是否在高 variation / 高 SAF 下失效
- 器件变差时，最优设计是否从大阵列迁移到中小阵列
- 更高 ADC 精度是否可以补偿器件退化


#### RQ3：哪些设计在随机器件扰动下更鲁棒？

这一问题关注：

- 平均最优设计是否脆弱
- 哪些设计虽不是平均最优，但在最差情况下更稳定
- 鲁棒最优设计是否比单点最优设计更适合作为工程建议


### 1.7 可扩展研究问题：非线性器件模型

如果进一步引入器件非线性模型，则增加：

#### RQ4：在线性欧姆模型下得到的最优设计，在考虑器件非线性后是否仍然成立？

这一问题关注：

- 非线性是否改变 Pareto front 的形状
- 非线性是否改变最优阵列尺寸和接口精度选择
- 线性模型是否系统性高估大阵列设计的优势


## 2. Method

### 2.1 总体框架

本文的方法框架由四个模块组成：

1. 定义 RRAM-aware 设计空间
2. 通过 `MNSIM` 评估设计点的 PPA 和精度
3. 使用 DSE 算法搜索满足精度约束的 Pareto 设计
4. 在器件扰动下评估 Pareto 设计的鲁棒性

整体流程如下：

```text
Design Variables
    -> Configuration Generator
    -> MNSIM Evaluation
    -> PPA + Accuracy Metrics
    -> Constraint Filtering / Pareto Analysis
    -> Robustness Re-evaluation
    -> Final Design Guidelines
```


### 2.2 RRAM-aware 设计空间构建

与仅包含架构参数的传统 DSE 不同，本文设计空间同时包含：

- 器件层参数
- 接口层参数
- 架构层参数

为避免器件参数过度展开导致搜索空间爆炸，本文使用 `rram_preset` 对器件特性进行离散抽象。每个 preset 对应一组固定的器件参数，包括：

- `Ron/Roff`
- `variation`
- `SAF`
- 可选的非线性强度

这样可以在不显著增加搜索成本的前提下，使器件质量成为 DSE 的一等变量。


### 2.3 评价流程

对每个设计点 `x`，本文通过 `MNSIM` 完成以下评估：

1. 根据设计变量生成硬件配置
2. 对目标网络进行映射
3. 计算推理时延、能耗、面积
4. 在指定器件场景下进行精度评估

若开启器件扰动，则对同一设计重复进行多次评估，以获得：

- 平均精度
- 最差精度
- 精度方差


### 2.4 优化形式

本文采用约束多目标优化形式。

第一步，对所有设计点评估：

- `latency`
- `energy`
- `area`
- `accuracy`

第二步，过滤不满足精度约束的设计：

```text
Acc(x) < Acc_base - δ
```

第三步，在剩余设计中构建 Pareto front：

- 目标 1：最小化时延
- 目标 2：最小化能耗
- 目标 3：最小化面积

第四步，对 Pareto 候选做鲁棒性复评估，并筛选鲁棒 Pareto 设计。


### 2.5 采样与搜索策略

本文不建议直接在大空间上全枚举，而采用“两阶段探索”。

#### 阶段一：粗粒度采样

目的：

- 快速覆盖整个设计空间
- 识别高潜力区域

做法：

- 使用分层随机采样或均衡采样
- 保证关键变量每个 level 都被充分覆盖

重点均衡的维度包括：

- `rram_preset`
- `xbar_size`
- `adc_choice`


#### 阶段二：代理模型引导搜索

目的：

- 在有限预算下更高效地逼近 Pareto 前沿

做法：

- 使用 `NSGA-II`、`MOBO` 或约束 BO
- 对高潜力区域进行重点评估


### 2.6 鲁棒性评估

对于阶段二得到的 Pareto 候选，本文进一步进行多随机种子复评估。

对于每个候选设计：

- 固定结构参数
- 改变器件随机扰动种子
- 重复多次仿真

从而得到：

- `Acc_mean`
- `Acc_worst`
- `Acc_std`
- `Yield`

最终设计建议不只基于平均性能，而同时基于鲁棒性。


### 2.7 非线性模型扩展方法

如果进一步考虑器件非线性，本文建议采用参数化方法，而不是直接引入复杂的器件级 SPICE 模型。

可定义：

```text
I = G * f(V, alpha)
```

其中：

- `G` 为理想线性导通项
- `f(V, alpha)` 为电压相关的非线性函数
- `alpha` 表示非线性强度

当：

- `alpha = 0` 时，退化为理想线性模型
- `alpha > 0` 时，表示非线性增强

这样可以研究：

- 随着非线性增强，最优阵列尺寸是否变化
- 高精度接口是否变得更必要
- 线性模型下最优设计是否仍然可靠


## 3. Experimental Setup

### 3.1 实验目标

实验部分的目标是验证以下三点：

1. 所提出的 RRAM-aware 设计空间是否能揭示更有价值的设计规律
2. 器件非理想是否导致最优设计迁移
3. 鲁棒设计是否与平均最优设计不同


### 3.2 工作负载

建议至少选择两个网络，以避免结论只对单一模型成立。

推荐：

- `VGG8` on `CIFAR10`
- `VGG16` on `CIFAR10`

如果资源允许，可加入：

- 小型 `ResNet`

这样可以比较：

- 浅层 CNN 和深层 CNN 下最优设计是否一致


### 3.3 器件场景

建议定义四种器件场景：

- `P0`：理想器件基线
- `P1`：中等非理想
- `P2`：高 variation
- `P3`：高 SAF

若加入非线性，则对每个 preset 再定义：

- `alpha = 0`
- `alpha = alpha_1`
- `alpha = alpha_2`


### 3.4 设计空间

推荐的主设计空间如下：

| 层级 | 参数 | 中文解释 | 建议取值 |
|---|---|---|---|
| 器件层 | `rram_preset` | RRAM 器件预设 | `P0`, `P1`, `P2`, `P3` |
| 阵列层 | `xbar_size` | 交叉阵列尺寸 | `128`, `256`, `512` |
| 接口层 | `adc_choice` | ADC 类型/精度档 | `4`, `6`, `7`, `8` |
| 接口/PE层 | `dac_num` | DAC 数量 | `32`, `64`, `128` |
| PE层 | `xbar_polarity` | 正负权实现方式 | `1`, `2` |
| PE层 | `sub_position` | 差分相减位置 | `0`, `1` |
| PE层 | `group_num` | PE 内阵列组数 | `1`, `2`, `4` |
| Tile层 | `pe_num` | Tile 内 PE 数量 | `(2,2)`, `(4,4)`, `(8,8)` |
| 架构层 | `tile_connection` | Tile 互连拓扑 | `0`, `1`, `2`, `3` |
| Tile层 | `inter_tile_bw` | Tile 间带宽 | `10`, `20`, `40`, `80` |


### 3.5 评价指标

实验中统计以下指标：

主指标：

- 推理时延
- 推理能耗
- 芯片面积
- 推理精度

鲁棒性指标：

- 平均精度
- 最差精度
- 精度标准差
- 精度达标率

辅助指标：

- Pareto front
- Hypervolume
- EDP


### 3.6 实验流程

建议按以下三阶段执行。

#### 实验一：理想器件下的 PPA 趋势

目的：

- 观察架构变量对 PPA 的基础影响

设置：

- `rram_preset = P0`
- 先不强调鲁棒性

输出：

- 理想场景下的 Pareto 前沿
- 主导变量分析


#### 实验二：器件非理想导致的最优设计迁移

目的：

- 比较不同器件场景下最优设计是否变化

设置：

- `P0/P1/P2/P3`
- 开启精度评估

输出：

- 各器件场景对应的 Pareto front
- 最优 `xbar_size`、`ADC`、`PE` 配置迁移分析


#### 实验三：鲁棒 Pareto 分析

目的：

- 比较平均最优与鲁棒最优

设置：

- 对 Pareto 候选进行多随机扰动复评估

输出：

- `Acc_worst`
- `Yield`
- 鲁棒设计推荐


#### 实验四：非线性模型扩展（可选）

目的：

- 研究线性模型与非线性模型下设计结论是否一致

设置：

- 固定若干代表性器件场景
- 逐步增加 `nonlinearity_alpha`

输出：

- Pareto front 迁移
- 最优阵列尺寸迁移
- 线性模型误差分析


## 4. Expected Contributions

基于上述问题定义、方法和实验设计，本文有望形成以下贡献。

### 贡献一

构建一个面向 `RRAM` 的器件-接口-架构协同 DSE 框架，而不仅是架构参数扫描框架。


### 贡献二

揭示器件非理想增强时，RRAM-CIM 最优设计从理想场景向鲁棒场景迁移的规律。


### 贡献三

证明平均最优设计未必是工程上最优设计，鲁棒最优设计更适合指导真实硬件实现。


### 贡献四（可选增强）

分析器件非线性对设计空间探索结果的影响，并证明忽略非线性可能导致最优设计判断偏差。


## 5. Paper Selling Points

这一节用于收束论文卖点，避免论文写成“做了一些参数扫描”。

### 5.1 本文最核心的卖点

如果只保留一句话，本文的主卖点应当是：

- 本文不是做普通的架构参数调优，而是构建了一个 **面向 RRAM 非理想的器件-接口-架构协同 DSE 框架**，并据此分析最优设计在器件退化下的迁移规律。

这句话里有三个关键词：

- `RRAM 非理想`
- `协同设计`
- `设计迁移`

这三者合起来，才是这篇论文区别于普通 PPA DSE 的根本。


### 5.2 与普通 DSE 工作的区别

普通 DSE 工作往往只做以下事情：

- 扫描阵列尺寸
- 扫描 ADC / DAC 配置
- 比较若干 PPA 指标

这种工作的问题在于：

- 器件特性被固定
- 精度通常只是附带结果
- 得出的结论多半只在理想器件下成立

而本文的区别在于：

1. 将 `RRAM` 器件特性显式纳入设计空间
2. 将 `accuracy` 作为约束而不是附属指标
3. 从“平均最优”推进到“鲁棒最优”
4. 进一步讨论线性模型和非线性模型下结论是否一致

因此，本文的工作不再是：

- “哪组参数最好”

而是：

- “在不同器件条件下，什么样的设计原则才是稳定成立的”


### 5.3 适合放在摘要里的卖点

可压缩为以下三点：

1. 提出一个面向 `RRAM-CIM` 的器件-接口-架构协同 DSE 框架。
2. 在精度约束下联合优化时延、能耗与面积，并分析最优设计随器件非理想增强而发生的迁移。
3. 从鲁棒性视角重新审视 Pareto 最优设计，并证明平均最优设计未必是工程上最优设计。

若加入非线性模型，则可增强为：

4. 证明忽略器件非线性可能导致 DSE 得到的最优设计产生系统性偏差。


### 5.4 适合放在引言末尾的贡献点

可以直接写成如下形式：

1. 本文提出一种面向 `RRAM` 存内计算加速器的协同设计空间探索框架，将器件预设、接口配置与架构参数统一纳入 DSE 流程。
2. 本文采用“PPA 多目标优化 + 精度约束”的问题定义，避免了仅凭理想 PPA 指标得出失真设计结论。
3. 本文系统研究了随着器件 variation 和 SAF 增强，最优设计从理想解向鲁棒解迁移的规律，并给出面向器件质量的设计指导。
4. 本文进一步讨论器件非线性对设计空间探索结果的影响，说明线性欧姆模型下的设计最优性并不总能迁移到真实器件条件。


### 5.5 最建议强调的创新点排序

如果版面有限，建议按以下优先级强调创新点：

第一优先级：

- `RRAM-aware DSE`

第二优先级：

- `PPA + accuracy constraint`

第三优先级：

- `robust design migration`

第四优先级：

- `nonlinearity-aware extension`

原因是：

- 前三项已经足以构成一篇完整、闭环的设计指导论文
- 第四项是强增强项，但不应在第一版论文中喧宾夺主


### 5.6 一句最适合答辩和摘要的总结

本文的真正贡献不是找到某个最优点，而是：

- **揭示了 RRAM 器件条件改变时，存内计算最优设计如何迁移，以及什么样的设计在真实器件约束下更鲁棒。**


## 6. 一段可直接放论文中的概述

本文研究面向 RRAM 存内计算加速器的器件-接口-架构协同设计空间探索问题。不同于传统仅关注架构参数的 DSE 方法，本文将器件非理想以 `rram_preset` 的形式显式纳入设计空间，并以时延、能耗和面积为优化目标，以推理精度和鲁棒性为约束，构建 RRAM-aware 的多目标优化问题。在此基础上，本文进一步分析随着器件 variation、SAF 乃至非线性增强，最优设计是否发生迁移，并给出面向实际器件条件的设计指导。


## 7. Code Changes And Commands

这一节给出当前代码已经改动的部分，以及后续完成采样和搜索时应关注哪些文件、执行哪些命令。

### 7.1 已经改动的核心文件

- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py)
  - 新增 `rram_preset`
  - 将 SPACE 改为 RRAM-aware 版本
  - 新增 `dac_num`、`xbar_polarity`、`sub_position`、`group_num`
  - 新增精度约束辅助逻辑

- [dse/algorithms/random_sample.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/random_sample.py)
  - 采样结果支持 `accuracy_target`
  - Pareto 输出改为可行解优先

- [dse/algorithms/nsga2.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/nsga2.py)
  - 精度约束进入搜索向量

- [dse/algorithms/mobo.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/mobo.py)
  - 精度约束进入 ParEGO 搜索向量

- [dse/algorithms/bo_gp.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/bo_gp.py)
  - 最终 Pareto 输出改为约束感知

- [dse/run_dse.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_dse.py)
  - `accuracy_target` 改为全局参数
  - 采样数据集签名纳入 `accuracy_target`

- [dse/i18n.py](/Users/bytedance/workspace/MNSIM-2.0/dse/i18n.py)
  - 同步新的中文字段名

- [dse/extras/surrogate_query.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/surrogate_query.py)
  - 更新示例输入

- [dse/analyze_results.py](/Users/bytedance/workspace/MNSIM-2.0/dse/analyze_results.py)
  - 对 `dataset_history.csv` / `history.csv` 做离线分析
  - 生成 `summary.json`、`top_configs.csv`、`group_summary.csv`
  - 生成可直接打开的 `index.html` 可视化仪表盘
  - 页面已增加中文术语解释、单位展示和更易读的数字格式

- [dse/extras/export_rram_v2_matrices.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/export_rram_v2_matrices.py)
  - 导出第二版论文采样矩阵 `A/B/C/D`
  - 自动生成 `72` 点总表 `matrix_all.csv`

- [dse/run_matrix_csv.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py)
  - 按 `matrix_all.csv` / `matrix_A.csv` 逐点执行仿真
  - 支持只跑 `A/B/C/D` 某一个矩阵
  - 支持 `--dry-run` 先预览被选中的点


### 7.2 如果继续增强，优先修改哪些文件

第一优先级：

- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py)
  - 继续细化 `RRAM_PRESETS`

第二优先级：

- [MNSIM/Accuracy_Model/Weight_update.py](/Users/bytedance/workspace/MNSIM-2.0/MNSIM/Accuracy_Model/Weight_update.py)
  - 更真实的 variation / SAF / 多级态建模

第三优先级：

- [MNSIM/Hardware_Model/Device.py](/Users/bytedance/workspace/MNSIM-2.0/MNSIM/Hardware_Model/Device.py)
  - 如果要加入器件非线性，这里是最合适入口

第四优先级：

- [dse/algorithms/nsga2.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/nsga2.py)
- [dse/algorithms/mobo.py](/Users/bytedance/workspace/MNSIM-2.0/dse/algorithms/mobo.py)
  - 如果要做更强的 constrained acquisition 或 robustness-aware DSE，可继续增强


### 7.3 建议的采样工作流

建议按“三步法”做实验。

#### 第一步：先做随机采样

```bash
python3 dse/run_dse.py \
  --algos random \
  --seeds 42 43 44 \
  --workers 2 \
  --space-profile rram_v2 \
  --budget 180 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation
```

这一步用于：

- 看空间覆盖
- 看精度约束下可行点比例
- 建立后续画图和分析数据


#### 第二步：做正式搜索

`NSGA-II` 示例：

```bash
python3 dse/run_dse.py \
  --algos nsga2 \
  --seeds 42 43 44 \
  --workers 2 \
  --budget 48 \
  --init-evals 12 \
  --population 24 \
  --evals-per-gen 6 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --plots
```

`MOBO` 示例：

```bash
python3 dse/run_dse.py \
  --algos mobo \
  --seeds 42 43 44 \
  --workers 2 \
  --budget 36 \
  --init-evals 10 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --plots
```


#### 第三步：生成对比图与报告

```bash
python3 dse/run_dse.py \
  --compare-only \
  --output-root artifacts/dse/search_runs/<your_run_dir> \
  --plots
```


### 7.4 完成采样时你最需要改什么

如果你的目标是完成一套论文可用的采样实验，重点改下面几项。

1. 改器件预设

文件：

- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py)

重点字段：

- `Device_Resistance`
- `Device_Variation`
- `Device_SAF`

当前建议的 preset 含义如下：

| preset | 中文解释 | 典型含义 |
|---|---|---|
| `P0` | 理想基线 | 高 `Ron/Roff`，极低 variation，极低 SAF |
| `P1` | 平衡型器件 | 中等 `Ron/Roff`，低 variation，低 SAF |
| `P2` | 高波动器件 | 中等 `Ron/Roff`，较高 variation，低 SAF |
| `P3` | 高缺陷器件 | 中等 `Ron/Roff`，中等 variation，较高 SAF |
| `P4` | 严苛器件 | 低 `Ron/Roff`，高 variation，高 SAF |

2. 改精度约束

运行时通过：

- `--accuracy-target`

如果想优先加速精度评估，运行时通过：

- `--max-acc-batches`

建议：

- 快速探索：`2~4`
- 正式实验：`6~11`

3. 改采样预算

运行时通过：

- `--budget`
- `--init-evals`
- `--population`
- `--evals-per-gen`

4. 改工作负载

运行时通过：

- `--nn`
- `--weights`
- `--dataset-module`


### 7.5 建议你实际执行的命令顺序

先做基础采样：

```bash
python3 dse/run_dse.py \
  --algos random \
  --seeds 42 43 44 \
  --workers 2 \
  --budget 180 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation
```

再做正式搜索：

```bash
python3 dse/run_dse.py \
  --algos nsga2 mobo \
  --seeds 42 43 44 \
  --workers 2 \
  --space-profile rram_v2 \
  --budget 48 \
  --init-evals 12 \
  --population 24 \
  --evals-per-gen 6 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --plots
```

最后做鲁棒性复评估：

```bash
python3 dse/run_robustness.py \
  --input-root artifacts/dse/search_runs/<your_run_dir> \
  --source pareto \
  --sort-by energy_nj \
  --topk 5 \
  --repeats 8 \
  --seed-base 1000
```

这一步会输出：

- `summary.csv`
- `per_repeat.csv`

用于分析：

- 平均精度
- 最差精度
- 精度标准差
- 精度达标率

如果你使用的是 Apple Silicon（如 `M3 Pro`），现在可以直接尝试：

```bash
python3 dse/run_dse.py \
  --algos random \
  --seeds 42 \
  --workers 1 \
  --budget 20 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --max-acc-batches 2 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device mps
```

注意：

- `MPS` 只会加速精度评估中的 `PyTorch` 前向部分
- `MNSIM` 的 PPA 建模仍然主要在 CPU 上执行


### 7.5.1 第二版论文采样矩阵如何导出

如果你想直接拿到第二版论文矩阵 `A/B/C/D`，运行：

```bash
python3 dse/extras/export_rram_v2_matrices.py \
  --output-dir artifacts/dse/matrices/rram_v2
```

输出包括：

- `artifacts/dse/matrices/rram_v2/matrix_A.csv`
- `artifacts/dse/matrices/rram_v2/matrix_B.csv`
- `artifacts/dse/matrices/rram_v2/matrix_C.csv`
- `artifacts/dse/matrices/rram_v2/matrix_D.csv`
- `artifacts/dse/matrices/rram_v2/matrix_all.csv`

其中：

- `A`：主迁移矩阵
- `B`：接口补偿矩阵
- `C`：系统瓶颈矩阵
- `D`：压力边界矩阵

总点数为：

- `72`

这 `72` 个点比直接做大规模随机盲采样更适合作为论文主实验矩阵。


### 7.5.2 如何直接按第二版矩阵逐点执行

如果你想直接按 `72` 点矩阵逐点跑，而不是让 random sampler 自己抽样，可以运行：

```bash
python3 dse/run_matrix_csv.py \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --workers 2 \
  --base-config SimConfig.ini \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device mps \
  --dataset-append
```

如果你只想跑主迁移矩阵 `A`：

```bash
python3 dse/run_matrix_csv.py \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --matrix-name A \
  --workers 2 \
  --base-config SimConfig.ini \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --run-accuracy \
  --max-acc-batches 4 \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device mps \
  --dataset-append
```

如果你只想先看会选中哪些点，不真的仿真：

```bash
python3 dse/run_matrix_csv.py \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --matrix-name A \
  --max-points 4 \
  --workers 2 \
  --dry-run \
  --output-root artifacts/dse/matrix_runs/dryrun_demo
```

这一步会生成：

- `selected_matrix.csv`
- `matrix_run_meta.json`

用于确认：

- 当前到底选中了哪些实验点
- 每个点属于哪个矩阵
- 每个点的固定参数和变化参数是什么

补充建议：

- 在 `M3 Pro` 上，建议先从 `--workers 2` 开始
- 如果 `max_acc_batches` 很小，且 `MPS` 利用率不高，可尝试 `--workers 3`
- 不建议一开始就开太多 worker，因为精度评估会争抢内存和数据加载资源


### 7.6 采样之后得到的数据长什么样

为提升可读性，当前建议统一使用如下目录层级：

```text
artifacts/dse/
  datasets/       # 可持续累积的数据集根目录
  search_runs/    # run_dse.py 的搜索/对比实验
  matrices/       # 论文矩阵定义 CSV
  matrix_runs/    # run_matrix_csv.py 的逐点实验
```

如果你运行的是：

```bash
python3 dse/run_dse.py ...
```

那么结果通常分成两层。

第一层：**dataset 级汇总数据**

位于：

- `artifacts/dse/datasets/<dataset_signature>/dataset_history.csv`
- `artifacts/dse/datasets/<dataset_signature>/dataset_history_zh.csv`
- `artifacts/dse/datasets/<dataset_signature>/runs/`

其中：

- `dataset_history.csv`
  - 是**最适合后处理和画图**的总表
  - 每一行对应一个被真实评估过的设计点
  - 会持续 append，适合不断积累随机采样和搜索结果
  - 因此同一个 `dataset_signature` 下，主数据集会随着后续实验继续增大

第二层：**单次 run 的明细数据**

位于：

- `artifacts/dse/datasets/<dataset_signature>/runs/run_YYYYMMDD_HHMMSS/`

其中每个算法/种子目录下通常有：

- `history.csv`
  - 该 trial 的全部评估历史

- `pareto.csv`
  - 该 trial 内部的 Pareto 点

- `result.json`
  - 该 trial 的汇总指标，例如 `wall_time_s`、`pareto_size`

- `comparison/`
  - 多 trial / 多算法对比结果

另外，正式分析报告建议统一放在：

- `artifacts/dse/datasets/<dataset_signature>/reports/analysis/run_YYYYMMDD_HHMMSS/`
- `artifacts/dse/datasets/<dataset_signature>/reports/analysis/latest`

其中：

- `run_YYYYMMDD_HHMMSS/`
  - 保存一版不可变的正式分析结果

- `latest`
  - 指向最近一次正式分析结果，便于直接打开


### 7.7 `dataset_history.csv` 里每一列怎么看

最常用列可以按四类理解。

第一类：**设计变量**

- `rram_preset`
  - 器件场景标签

- `xbar_size`
  - 交叉阵列尺寸

- `adc_choice`
  - ADC 档位/精度选择

- `dac_num`
  - DAC 数量

- `xbar_polarity`
  - 正负权实现方式

- `sub_position`
  - 差分相减位置

- `group_num`
  - PE 内阵列组数

- `pe_num`
  - Tile 内 PE 规模

- `tile_connection`
  - Tile 互连拓扑

- `inter_tile_bw`
  - Tile 间带宽

第二类：**实验开关**

- `run_accuracy`
- `enable_saf`
- `enable_variation`
- `enable_rratio`
- `fixed_qrange`
- `accuracy_target`

第三类：**输出指标**

- `latency_ns`
- `energy_nj`
- `area_um2`
- `power_w`
- `accuracy`

第四类：**追踪字段**

- `run_id`
- `trial_dir`
- `algo`
- `seed`
- `eval_index`
- `phase`
- `elapsed_s`
- `is_pareto`

其中最重要的是：

- 设计变量列：告诉你“这个点是什么硬件”
- 指标列：告诉你“这个硬件表现如何”
- `accuracy_target + accuracy`：告诉你“这个点是否可行”
- `is_pareto`：告诉你“这个点是否属于该 trial 的 Pareto 集”


### 7.8 采样后应该怎么用这些数据

建议按下面四步处理。

第一步：**先筛可行解**

规则：

```text
accuracy >= accuracy_target
```

因为论文目标不是找“精度崩掉但 PPA 很好”的点，而是找：

- 满足精度约束下的设计指导

第二步：**看全局 Pareto**

即在所有可行点中，筛掉那些在：

- 时延
- 能耗
- 面积

上同时被别人压制的点。

第三步：**做分组统计**

重点按这些变量分组：

- `rram_preset`
- `xbar_size`
- `adc_choice`
- `pe_num`

看每组的：

- 可行率
- 最优时延
- 最优能耗
- 最优面积
- 最优精度

第四步：**抽象设计规律**

例如形成这样的结论：

- 在 `P2/P3/P4` 下，大阵列 `512x512` 的可行率明显下降
- `adc_choice=6` 是一个较优折中点
- 更高 `inter_tile_bw` 在高并行 `pe_num` 下更重要

这类规律，才是论文里真正有价值的“设计指导”。


### 7.9 现在怎么一键生成网页和 CSV

已经新增：

- [dse/analyze_results.py](/Users/bytedance/workspace/MNSIM-2.0/dse/analyze_results.py)

你可以直接对 dataset root 做分析：

```bash
python3 dse/analyze_results.py \
  --input artifacts/dse/datasets/<your_dataset_root> \
  --output-dir artifacts/dse/datasets/<your_dataset_root>/reports/analysis
```

也可以只分析某一次 run：

```bash
python3 dse/analyze_results.py \
  --input artifacts/dse/datasets/<your_dataset_root>/runs/run_YYYYMMDD_HHMMSS \
  --output-dir artifacts/dse/datasets/<your_dataset_root>/runs/run_YYYYMMDD_HHMMSS/reports/analysis
```

输出包括：

- `summary.json`
  - 总体摘要

- `top_configs.csv`
  - 推荐重点看的配置

- `group_summary.csv`
  - 按变量分组后的摘要

- `global_pareto.csv`
  - 全局可行 Pareto 点

- `index.html`
  - 可直接打开的网页仪表盘


### 7.10 网页里你应该重点看什么

网页中最值得看的不是“点很多”，而是下面四件事。

1. **可行率**

- 如果可行率很低，说明空间定义过宽，很多点无意义
- 这时应适当收缩 `xbar_size`、`adc_choice` 或器件场景范围

2. **Pareto 点落在哪些 preset 上**

- 如果 Pareto 点只集中在 `P0/P1`
  - 说明你的设计在真实器件下不够稳健

- 如果 `P2/P3/P4` 里仍有稳定 Pareto
  - 这就能支撑“robust design guidance”的论文卖点

3. **大阵列是否真的更优**

- 如果 `512x512` 只在理想器件下占优，而在劣化器件下失效
  - 这就是“最优设计迁移”的关键证据

4. **ADC 是否成为补偿手段**

- 如果器件退化时，高 `adc_choice` 带来更高可行率
  - 可以形成“接口补偿器件退化”的论点


### 7.11 对你现在这批数据的直观结论

以你当前这次结果为例：

- 总样本数：`10`
- 可行样本数：`2`
- 可行率：`20%`
- 全局 Pareto：`1`

这说明：

1. 当前空间在 `accuracy_target=0.88` 下偏难
2. 很多点虽然能跑出 PPA，但没有工程意义，因为精度不达标
3. 当前最值得做的不是继续无约束加预算，而是：
   - 先看哪些变量导致不可行率高
   - 然后做 space 收缩或分层采样

也就是说，**采样数据本身已经在告诉你如何修改设计空间**。
