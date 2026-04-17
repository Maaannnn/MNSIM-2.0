# 子课题拆解：从硕士毕业论文到 DAC 方向

本文档结合以下上下文整理：

- 你的硕士毕业论文主线：基于 `MNSIM` 的 RRAM/PIM/CIM 设计空间探索、measured-in-the-loop、PPA-ACC 联合优化
- 本地建议材料：
  - [基于MNSIM的PIM_CIM架构顶会论文学术建议报告.docx](/Users/bytedance/workspace/MNSIM-2.0/基于MNSIM的PIM_CIM架构顶会论文学术建议报告.docx)
  - 当前仓库中的问题定义、实验计划和对 `MNSIM` / `NeuroSim` 的审视文档

目标不是给出“能写很多东西”的大题，而是给出几条真正能从毕业论文中拆出来、适合冲 `DAC/ICCAD/TCAD` 风格会议的子命题。

## 1. 先给核心判断

你的硕士毕业论文可以有一条比较完整的大主线：

- `MNSIM + DSE + measured preset + robust optimisation + paper writing`

但如果要从中拆出可投稿子课题，最适合 `DAC` 风格的不是“大而全系统”，而是下面这类更窄、更方法导向的题：

1. `MNSIM` 的增强型方法学
2. 精度约束下的编译/映射优化
3. measured preset 驱动的鲁棒 DSE
4. 快速低保真平台如何接近高保真趋势

换句话说：

- 毕业论文讲“全局研究故事”
- 子课题讲“一个明确的方法创新 + 一个明确的实验协议 + 一个明确的比较基线”

## 2. 这份 docx 带来的主要启发

这份建议报告的价值，不在于具体细节全都要照搬，而在于它把可投稿方向分得比较清楚：

- 偏架构
- 偏算法/编译
- 偏工具/方法学

对你当前最现实、最适合 `DAC` 风格会议的，不是最偏架构那条，也不是最重型的多保真全平台那条，而是中间两类：

- 偏算法/编译
- 偏工具/方法学

原因很简单：

- 你已经有 `MNSIM` 和 `DSE` 代码基础
- 你有 measured preset 这条差异化路线
- 你还没有完整的高保真闭环平台和大量硅后校准

所以最该拆出来的子命题，应当建立在你已经能较快做深做透的东西上。

## 3. 我建议优先考虑的 4 个子命题

下面按“可做性 + DAC 风格契合度 + 与毕业论文兼容度”综合排序。

## 3.1 子命题 A：精度约束下的鲁棒映射/配置搜索

### 一句话标题方向

`RobustMap-CIM: Accuracy-Constrained Mapping and Configuration Search for RRAM CIM under Device Non-Idealities`

### 这题讲什么

不是泛泛做 DSE，而是明确聚焦：

- 在器件非理想和精度约束存在时
- 如何搜索更鲁棒的映射 / 架构配置
- 而不是只找 nominal 最优点

### 为什么适合 DAC

这很像典型 `DAC/ICCAD/TCAD` 风格问题：

- 有明确优化目标
- 有设计变量
- 有约束
- 有算法或搜索方法贡献

### 你已有的基础

- `dse/run_dse.py`
- measured preset
- `accuracy_target`
- 现成的 RRAM preset / guidance space / formal space

### 最小创新点

你不一定要发明全新 RL。  
只要做出下面任意一个，就已经像一个子课题：

- 将 `accuracy_target + worst-case accuracy + feasibility rate` 引入搜索目标
- 引入“多 preset 场景聚合”的 robust objective
- 在映射或参数搜索中加入 coupled non-ideality penalty

### 论文核心 claim 可以怎么写

- 现有 MNSIM-based search mostly optimizes nominal PPA
- 我们提出一种 accuracy-constrained robust search formulation
- 在多个 measured / preset 场景下能找到更稳定的设计点

### 风险

- 如果只做普通 NSGA-II 套壳，会显得方法味不够

### 如何避免

- 明确提出 robust objective / scenario aggregation / feasibility-aware ranking
- 不要只报 Pareto 图，要报 robust ranking 改善

## 3.2 子命题 B：面向 MNSIM 的轻量高保真增强方法

### 一句话标题方向

`StateCalib-MNSIM: Lightweight State-LUT and Calibration Extensions for Fidelity-Aware CIM Design Exploration`

### 这题讲什么

核心不是“做新仿真器”，而是：

- 给 `MNSIM` 增加最关键的精度后端增强
- 例如：
  - `device_states.csv`
  - `ADC calibration`
  - code-dependent ADC noise
  - drift / retention preset

### 为什么适合 DAC/TCAD/ICCAD

这是很典型的工具/方法学论文：

- 不是硬做大系统
- 而是增强已有 low-fidelity 框架的研究有效性

### 为什么你适合做

前面我们已经明确：

- `MNSIM` 的短板你看清了
- `NeuroSim` 的可借鉴机制你也看过了

你完全可以做出一个：

- “仍然快，但对非理想更敏感”的增强版 MNSIM

### 最小创新点

只要把下面两项做扎实，就已经足够像一篇方法论文：

- state-aware device LUT
- calibration-aware ADC quantization

### 论文核心 claim

- 与原始 MNSIM 相比
- 我们保持近似相同量级速度
- 但显著改善非理想敏感性和统计稳定性

### 风险

- 如果没有对照，只会像工程 patch

### 如何避免

要设计清楚对照：

- 原始 MNSIM
- 增强版 MNSIM
- 小规模高保真参考趋势

即使只是趋势一致性，也有价值。

## 3.3 子命题 C：measured preset 驱动的鲁棒 DSE

### 一句话标题方向

`Measured-Preset DSE: Device-Condition-Aware Exploration for RRAM CIM beyond Nominal Simulation`

### 这题讲什么

直接把你的差异化优势打出来：

- 不是只用 nominal preset
- 也不是只用 synthetic variation
- 而是从真实 `test_data` 抽出 measured preset
- 再做 DSE / robust evaluation

### 为什么有潜力

很多工作都在做：

- non-ideality-aware

但真正有“现实器件状态抽象 -> DSE”闭环的并不多。

### 为什么适合做成子课题

它和毕业论文主线高度一致，但可独立成文：

- 方法：measured preset abstraction
- 系统：preset-in-the-loop DSE
- 实验：nominal vs measured

### 核心贡献可以是

- measured preset extraction protocol
- preset-aware search or analysis workflow
- evidence that nominal optimum does not remain robust

### 风险

- 如果 measured preset 只是在 config 里改几个参数，创新会显得弱

### 如何避免

- 明确 preset 的统计来源
- 强调 preset 是从真实测试数据抽象而来
- 做 robust ranking / migration analysis，而不只是“换个 preset 再跑一遍”

## 3.4 子命题 D：精度预算分配与补偿策略研究

### 一句话标题方向

`Budgeted Accuracy Loss Allocation for RRAM CIM: Joint Study of ADC, Array Size, and Compensation Knobs`

### 这题讲什么

把“精度损失 <1%”从约束变成研究对象：

- 这 1% 的预算应该如何在不同层级消耗
- 哪些硬件 knob 在 non-ideal 场景下最值得拿来做补偿

### 为什么这题有意思

它比普通 ablation 更像方法问题：

- 不是问谁最好
- 而是问精度预算该如何分配

### 最适合的变量

- `ADC`
- `xbar_size`
- `sub_position`
- `dac_num`
- measured preset severity

### 风险

- 这题如果没有清晰建模，容易变成经验性分析

### 如何避免

- 先定义准确的 budgeted objective
- 再做二因素或三因素交互实验

## 4. 哪个最适合先发 DAC

如果只让我选一个最适合你当前条件、也最像 `DAC` 论文的方向，我会排这样一个顺序：

1. 子命题 A：精度约束下的鲁棒映射/配置搜索
2. 子命题 B：面向 MNSIM 的轻量高保真增强方法
3. 子命题 C：measured preset 驱动的鲁棒 DSE
4. 子命题 D：精度预算分配与补偿策略研究

### 为什么 A 排第一

因为它最像标准 DAC 问题：

- 有算法
- 有约束
- 有设计空间
- 有系统评估

而且它最容易直接从毕业论文里拆出来，不要求你先把工具链重构得非常完整。

### 为什么 B 排第二

因为它方法味很强，但对实验设计要求更严：

- 你需要证明 fidelity 改善
- 需要做一点和高保真工具的趋势对照

### 为什么 C 很有潜力但排第三

因为它最有差异化，但容易被审稿人问：

- measured preset 是否足够普适
- 是否只是 dataset-specific calibration

这题适合在你把 A 或 B 做扎实后，作为第二篇或和毕业论文主文更紧密绑定的一篇。

## 5. 如何让“毕业论文主线”和“子课题投稿”不打架

最好的方式不是把毕业论文拆碎，而是做一个主次结构：

### 毕业论文主线

- 问题定义
- MNSIM 平台
- preset-aware DSE
- robustness
- discussion / future work

### 子课题投稿

从里面只切一个最有方法贡献的点：

- robust search
- lightweight fidelity enhancement
- measured preset methodology

然后：

- 投稿论文讲方法贡献和一个核心实验协议
- 毕业论文保留更大的故事和更多章节

## 6. 对这份 docx 的保留与收敛建议

这份建议报告里有很多“顶会级大故事”，很有启发，但你不必全吃下。

### 建议保留的部分

- MNSIM 应定位为快引擎
- 可以通过多保真或增强模型补可信度
- 需要复合指标或更强的目标定义
- 可以拆成架构 / 编译 / 工具几个方向

### 建议收敛的部分

- 不要一开始就做完整 multi-fidelity platform
- 不要一开始就做 RL + NAS + 多保真 + 编译映射一锅端
- 不要把“顶会叙事”写得比现有代码和实验推进更快

## 7. 我给你的最务实建议

如果目标是：

- 毕业论文稳
- 同时拆一个可投稿 DAC 子课题

那最实际的路线是：

1. 先把毕业论文的大主线固定为：
   - `MNSIM + accuracy constraint + measured preset + robust DSE`
2. 从中拆出一个最窄的方法子题：
   - `robust search / mapping under accuracy constraint`
3. 让这个子题的实验完全复用毕业论文的数据和平台
4. 再把 `MNSIM fidelity enhancement` 作为毕业论文里的加强项，或者第二篇潜在子题

## 8. 一句话结论

这份 docx 最大的启发不是“你可以做很多方向”，而是提醒你：

- 硕士毕业论文需要一条完整主线
- 但拿去发 `DAC` 的子课题必须收窄成一个方法命题
- 对你当前最合适的切法，是从 `MNSIM` 驱动的精度约束鲁棒搜索 / 映射问题里，拆出一篇偏 `DAC/ICCAD` 风格的论文
