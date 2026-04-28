# 选题定位：`RobustMap-CIM` 的文献边界、贡献与实验设计

本文档的目标不是证明 `RobustMap-CIM` “完全没人做过”，而是更严谨地回答三个问题：

1. 现有工作已经做到哪里
2. 我们还剩下哪些可以成立的创新空间
3. 如何把题目收敛成适合 `DAC/ICCAD/TCAD` 风格投稿的子课题

---

## 1. 先给结论

`RobustMap-CIM` 这个方向不是无人区。

已经存在的相邻研究包括：

- variation-aware 的 `CIM` 设计或训练
- 非理想性下的 mapping / DSE 分析
- measured-data-driven 的 non-ideality compensation

但它也还没有形成一个“标准答案”。

尤其在下面这条链上，仍然有明显空间：

- `MNSIM` 这类快速平台
- `measured preset` 驱动的多场景建模
- `accuracy-constrained robust ranking`
- 针对 `mapping / configuration` 的鲁棒搜索

所以更稳妥的学术表述不是：

- “首次研究器件非理想下的鲁棒设计”

而应该是：

- “首次或较早系统性地将 measured-preset-driven multi-scenario robustness 引入 MNSIM-based RRAM CIM configuration search”

如果后续 related work 看得更全，也可以把 “首次” 再收敛成：

- “to the best of our knowledge, prior MNSIM-based flows mainly optimize nominal designs or analyze isolated non-ideal settings, while our work explicitly searches for robust design points across measured and coupled non-ideal scenarios”

---

## 2. 已有工作的三条相邻路线

## 2.1 路线 A：variation-aware co-exploration / robust architecture search

代表性工作：

- [NACIM](https://arxiv.org/abs/1911.00139)

从摘要可以直接看出两点：

- 它已经把 `device variation` 纳入 cross-layer exploration
- 它明确提到寻找 `the most robust neural architectures`

这说明：

- “考虑 variation 的鲁棒搜索” 这个大方向已经有人做过
- 如果我们也做“robust search”，就不能只停留在 slogan 层

但 `NACIM` 的重点更偏：

- architecture co-exploration
- neural architecture search
- variation-aware architecture robustness

它并不等价于你要做的题，因为你现在更接近：

- fixed network or limited network set
- `MNSIM`-based hardware configuration search
- measured preset / multi-scenario robust ranking

所以它是“最近邻”，但不是“同题”。

## 2.2 路线 B：mapping / DSE + non-idealities

代表性工作：

- [Design Space Exploration of Dense and Sparse Mapping Schemes for RRAM Architectures](https://arxiv.org/abs/2201.06703)

这篇工作已经说明：

- `mapping scheme`
- `tile size`
- `non-idealities`

三者之间是有 trade-off 的，而且不同网络和稀疏特征下表现不同。

这意味着：

- “映射方式影响非理想鲁棒性” 不是新发现
- “在非理想场景下研究 mapping” 也不是空白

但它更偏：

- dense vs sparse mapping methodology
- case-study style trade-off quantification

它没有明显把下面这些东西同时拉进来：

- measured preset
- multi-scenario robust objective
- `feasibility rate / worst-case accuracy` 作为正式搜索指标
- `MNSIM` 工作流上的 nominal-optimal vs robust-optimal migration

所以你的机会不在“重新证明 mapping matters”，而在“提出一种更正式、更贴合 measured scenario 的 robust search formulation”。

## 2.3 路线 C：variation-aware training / data-driven compensation

代表性工作：

- [PR-CIM](https://arxiv.org/abs/2110.09962)
- [D-NAT](https://access.ee.ntu.edu.tw/files/journals/%282022%29%20D-NAT%20Data-Driven%20Non-Ideality%20Aware%20Training%20Framework%20for%20Fabricated%20Computing-In-Memory%20Macros.pdf)

这类工作已经做了两件很强的事：

- variation-aware / resilience-aware compensation
- data-driven measured non-ideality modeling

特别是 `D-NAT`，它明确指出 measured data 比 analytical Gaussian model 更贴近真实宏行为，并且用 measured lookup 提升推理精度。

这说明：

- “measured data is valuable” 已经成立
- “analytical model不够” 也已经被公开论证过

所以如果你的工作只停留在：

- “我们也用了 measured preset”

那贡献会不够硬。

你的机会在于把 measured data 的价值转到另一个问题上：

- 不是 training compensation
- 而是 design point search and robust design migration

也就是：

- `measured-data-driven robust DSE`

而不是：

- `measured-data-driven NAT`

---

## 3. 我们真正还能 claim 的空白

结合当前仓库和公开工作，更可能成立的创新空间有 4 个。

## 3.1 空白 A：nominal-optimal 与 robust-optimal 的系统性区分

很多工作会展示：

- 某个设计在 variation 下精度下降
- 某个方法能提升鲁棒性

但较少工作把下面这件事做成设计自动化问题：

- 在多个 non-ideal scenarios 下，nominal Pareto 最优点是否发生系统性迁移

如果你能证明：

- nominal ranking 与 robust ranking 显著不一致
- measured scenarios 下的最优解集合发生迁移

这就不是普通 ablation，而是一个很像 `DAC` 的 design-automation 发现。

## 3.2 空白 B：measured preset 驱动的 multi-scenario search

已有 measured-data 工作，多偏：

- calibration
- training
- device-level modeling

而你可以做的是：

- 从 `test_data` 抽象多个 `measured preset`
- 让每个 design point 在多个 preset 上都被评估
- 用 scenario aggregation 去重新排序设计点

这个点最贴合你当前仓库已有资产，也最容易形成差异化。

## 3.3 空白 C：正式引入 robust metrics，而不是只看 average accuracy

更值得强调的指标不是单一 `Acc`，而是：

- `accuracy_mean`
- `accuracy_worst`
- `accuracy_std`
- `feasibility_rate`
- `robust_hypervolume` 或简化版 robust Pareto coverage

如果你把这些指标正式写进问题定义，文章会更像：

- design under uncertainty

而不是：

- 再做一轮普通 PPA-ACC sweep

## 3.4 空白 D：基于 MNSIM 的轻量鲁棒搜索工作流

`MNSIM` 本身是行为级快速工具，[MNSIM 2.0](https://github.com/thu-nics/MNSIM-2.0) 的公开定位是同时建模 `HW performance` 和 `NN accuracy` 的 `PIM` 评估平台，但它不是专门为：

- measured-data-driven robust DSE
- multi-scenario design ranking
- worst-case feasibility-aware search

这类问题而组织的。

所以如果你把它补成一个：

- 仍然快
- 但能做多场景鲁棒搜索

的工作流，这本身就可以构成较强的方法贡献。

---

## 4. `RobustMap-CIM` 最稳妥的贡献声明

为了避免 related work 一补就把自己顶掉，建议从一开始就用“收敛版 claim”。

## 4.1 不建议的说法

- 首次研究 RRAM CIM 非理想性下的鲁棒设计
- 首次提出 variation-aware CIM optimization
- 首次研究 mapping 在 non-idealities 下的影响

这些说法很容易被已有工作反驳。

## 4.2 建议的说法

可以优先采用以下层级。

### 版本 A：最稳妥

- 我们提出一个 `measured-preset-driven` 的 `MNSIM-based` robust configuration search flow，在精度约束下寻找跨多非理想场景更稳定的设计点。

### 版本 B：稍强一点

- 与主要面向 nominal setting 或单一 non-ideality analysis 的既有流程不同，我们显式将 multiple measured and coupled non-ideal scenarios 引入 design ranking 与 Pareto selection。

### 版本 C：条件满足后可用

- To the best of our knowledge, this is among the first `MNSIM-based` studies to formalize measured-preset-driven robust configuration search with feasibility-aware ranking for RRAM CIM.

这个版本能不能用，要看后面 related work 是否查到直接撞题论文。

---

## 5. 题目怎么收敛才更像 DAC

如果题目太大，会变成：

- 鲁棒系统平台
- 全流程高保真仿真器
- measured data + tool + optimization + architecture 全包

这对当前阶段不利。

更像 `DAC` 投稿的收敛方式是：

## 5.1 问题定义

给定：

- 一个网络或一小组代表网络
- 一个硬件配置空间
- 一组 non-ideal scenarios
- 一个 accuracy target

目标：

- 在满足精度约束的条件下
- 搜索在多场景下更稳的设计点
- 并最小化能耗、时延、面积中的一个或多个目标

形式上可以写成：

- nominal search:
  - maximize or minimize `f(x)` under one nominal scenario
- robust search:
  - optimize `Agg_s f(x, s)` under `Agg_s Acc(x, s) >= target`

其中 `Agg_s` 可以从简单到复杂依次采用：

- worst-case
- mean-worst weighted
- feasibility-rate-aware ranking

## 5.2 设计变量

优先用你当前仓库里已经成熟的变量：

- `xbar_size`
- `sub_position`
- `adc_precision`
- `dac_num`
- `weight_bit`
- `input_bit`
- `PE / tile / mapping-related knobs`

不要一开始把搜索空间扩得太夸张，否则像在做平台 demo。

## 5.3 scenario 设计

建议用三层 scenario：

1. `nominal`
2. `synthetic single-factor`
3. `measured / coupled`

这样实验逻辑会很完整：

- 先证明 nominal optimum 在 synthetic 下已不稳
- 再证明在 measured / coupled 下迁移更明显

## 5.4 评价指标

至少要比普通 `Acc + Energy + Area` 更强一点。

建议正式汇报：

- `energy`
- `latency`
- `area`
- `acc_mean`
- `acc_worst`
- `acc_std`
- `feasibility_rate`
- `rank_migration`

其中 `rank_migration` 很重要，因为它能直接证明：

- nominal-optimal 不是 robust-optimal

---

## 6. 最像论文贡献的三条主贡献

如果最后决定投这条线，论文贡献建议压成 3 条，不要写太散。

## Contribution 1

提出一个 `measured-preset-driven` 的 robust configuration search formulation，将 `worst-case accuracy`、`feasibility rate` 和多场景聚合正式引入 `RRAM CIM` 设计点排序。

## Contribution 2

在 `MNSIM` 上实现一个轻量但可复现的 multi-scenario evaluation flow，支持 nominal、synthetic、measured preset 的统一评估与 robust Pareto selection。

## Contribution 3

系统证明 nominal-optimal 设计在 measured / coupled non-ideal scenarios 下存在显著迁移，并给出对 `ADC / xbar_size / mapping knob` 的鲁棒设计指导。

这样写的好处是：

- 第 1 条是问题与方法
- 第 2 条是实现与工具
- 第 3 条是结论与设计指导

结构比较像顶会方法论文。

---

## 7. 建议的 baseline 与对比方式

不要把 baseline 设计成“和别人一模一样的工具”，而要围绕问题本身。

## 7.1 baseline 排序

建议至少包含：

1. `NominalSearch`
   - 只在 nominal preset 上搜索与排序
2. `SingleScenarioAware`
   - 只在一个 synthetic non-ideality scenario 上排序
3. `RobustMap-CIM`
   - 在多个 scenarios 上联合排序

如果后续实现得动，还可以加：

4. `MeasuredOnly`
   - 只在 measured preset 集合上排序
5. `CoupledScenarioAware`
   - 显式纳入 `IR-drop x ADC` 或 `preset x ADC`

## 7.2 不建议的 baseline

- 和 `NeuroSim` 直接拼 absolute accuracy
- 和完全不同训练框架直接拼最终精度

因为你的题更偏：

- design automation / search formulation

不是：

- 最强精度恢复方法

## 7.3 最核心的比较图

最值得做的图不是越多越好，而是这几类：

1. nominal Pareto vs robust Pareto
2. top-k design rank migration across scenarios
3. feasibility-rate comparison
4. robust objective improvement under same budget
5. knob sensitivity under measured preset severity

---

## 8. 最实际的实验骨架

如果按当前仓库状态出发，我建议实验分 4 组。

## Exp-1：Nominal optimum 是否稳定

流程：

- 在 nominal preset 上跑搜索
- 取 top-k 设计点
- 放到多 scenarios 上复评

要回答：

- nominal top-k 的失稳程度有多大

## Exp-2：Robust ranking 是否更有效

流程：

- 用 nominal ranking、single-scenario ranking、robust ranking 三种方法各自产生 top-k
- 对比它们在 held-out scenarios 上的表现

要回答：

- robust ranking 是否真的更稳，而不是只是在训练场景上过拟合

## Exp-3：Measured preset 的价值

流程：

- 用 synthetic-only scenarios 选点
- 用 measured-aware scenarios 选点
- 在 measured presets 上对比

要回答：

- measured preset 是否会改变 design decision

## Exp-4：设计指导

流程：

- 分析 robust-optimal 点集中出现在哪些 knob 组合

要回答：

- 哪些硬件选择更抗非理想

---

## 9. 当前最推荐的题目版本

如果今天就要写题目，我建议先别写得太大。

可以考虑：

### 版本 1

`RobustMap-CIM: Measured-Preset-Driven Robust Configuration Search for RRAM Compute-in-Memory`

### 版本 2

`Beyond Nominal Optima: Robust Configuration Search for RRAM CIM under Measured and Coupled Non-Idealities`

### 版本 3

`Accuracy-Constrained Robust Design Space Exploration for RRAM CIM with Measured Device Presets`

其中我最推荐版本 2。

因为它最清楚地传达了你的关键立场：

- 我们反对只看 nominal optimum
- 我们强调 measured and coupled non-idealities

---

## 10. 对你当前硕士论文与会议论文的拆分建议

最适合的拆法是：

### 硕士论文

- 保持大主线：
  - `MNSIM` 平台
  - 问题形式化
  - baseline DSE
  - measured preset
  - robust analysis

### 会议论文

- 只收敛成一个窄题：
  - `robust configuration search`

这样做有两个好处：

- 毕业论文不会被会议稿绑死
- 会议稿能更像一个方法贡献，而不是毕业论文压缩版

---

## 11. 当前行动建议

如果这条线继续推进，最该先做的不是立刻写引言，而是先把问题定义和实验协议钉死。

建议按这个顺序推进：

1. 明确 robust objective
2. 明确 scenario set 的来源与层级
3. 在 `MNSIM` 里补 multi-scenario evaluation
4. 先做一个 `nominal vs robust rank migration` 小实验
5. 再决定标题和 claim 强度

这会比先写一个很满的题目更稳。
