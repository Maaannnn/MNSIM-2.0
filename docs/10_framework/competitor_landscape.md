# 竞品对比：CIM/PIM DSE 与仿真框架

Status: 2026-04-27 首发版。维护人参考 `00_roadmap/current_research_todo.md`。
范围：行为级 / 电路级 / 系统级 CIM-PIM DSE 框架的横向对比，用于
论文 positioning、reviewer 应对、差异化定位。

## 1. 执行摘要

五个直接竞品的一句话定位：

- **CIMFlow** (DAC '25, 北航 + 北大) — 数字 CIM 的 ISA + MLIR 编译器
  + SystemC 周期精确仿真器；公开点名 MNSIM 2.0 "tightly-coupled, 不灵活"。
- **SEGA-DCIM** (DATE '25, 北大 + UCSD) — 多精度数字 CIM 自动综合
  (INT2-16 / FP) + NSGA-II DSE。用户在前文写的 "SegADCIM" 大概率指此项目。
- **EasyACIM** (DAC '24, 北大) — 模拟 CIM 端到端模板化 P&R 到 GDS
  + MOGA DSE；输出 50–750 TOPS/W。
- **AutoDCIM** (DAC '23, HKUST) — 数字 CIM 宏自动综合编译器，
  奠基性工作，被上述工作引为 baseline。
- **Eva-CiM** (TCAD '20, 圣母大学 + 浙大) — GEM5 + McPAT + DESTINY
  评估 CPU + CiM 异构系统能耗，开源在 GitHub。

**MNSIM 2.0 + pim_sim 的差异化定位**：少数同时具备
"行为级 NN 端到端 PPA + 准确率" + "wafer 校准的非对称变异 / IR-drop / Walden ADC 物理修正"
+ "多目标 DSE (NSGA-II / MOBO) 在共享 reference point 下的可比 HV"
+ "measured-in-the-loop robust search" 的栈。竞品要么停在宏级
(EasyACIM / AutoDCIM / SEGA-DCIM)，要么停在系统级但缺 NN 准确率 (CIMFlow / Eva-CiM)。

## 2. 项目卡片

### CIMFlow (DAC 2025)

- 作者 / 单位：Yingjie Qi, Jianlei Yang 等，北航 (BUAA CI-LAB) + 北大
- 目标：为数字 CIM 提供 "ISA + MLIR 编译器 + SystemC 周期精确仿真"
  端到端栈，替代 NeuroSim / MNSIM 在数字 CIM 上的不足。
- 器件 / 电路：仅数字 CIM (SRAM)，不涉及 RRAM / 模拟。
- 设计空间：MG 大小、核数 (默认 64)、NoC 带宽 / flit、本地 SRAM 容量
  (默认 512KB)、宏阵列维度 (512×64, 子单元 32×8)。核心是数据流 / 划分映射，
  非器件 / 精度。
- 保真度：周期精确 SystemC (IF / DE / EX 三级流水)；宏 PPA 来自
  post-layout + 商用 memory compiler + PrimeTime PX；NoC 用 Noxim。
- 优化方法：动态规划划分 (workload partitioning)。**不是** BO / GA / RL；
  属于"编译器优化"非"DSE 搜索"。
- silicon 数据：无；商业流程 post-layout。
- 代码：承诺开源在 cimflow.org，许可证未声明。
- 影响：DAC '25 新作，明确把 NeuroSim V1.4 / MNSIM 2.0 列为
  "fixed datapath / tightly-coupled" 的对照面。

来源：https://arxiv.org/abs/2505.01107 ；
https://www.ci-lab.net/uploads/paper/dac25_cimflow.pdf ；
https://www.cimflow.org/

### SEGA-DCIM (DATE 2025 / arXiv 2505.09451)

- 作者 / 单位：Haikang Diao, Haoyi Zhang, Xiyuan Tang 等，北大 + UCSD。
- 目标：模板法自动生成多精度数字 CIM netlist 与 layout，做
  area / power / delay 多目标 DSE。
- 器件 / 电路：数字 SRAM CIM。
- 设计空间：列数 N、列高 H、权重共享 L、每周期输入位 k、Bw / Bx / BE / BM；
  精度覆盖 INT2-INT16、FP8 / FP16 / FP32 / BF16。
- 保真度：模板生成 Verilog → Innovus 综合 + P&R 拿 PPA，TSMC 28nm 验证。
- 优化方法：NSGA-II (MOGA)。
- silicon 数据：无；对照 ISSCC '23 已发表数据。
- 代码：未提及开源。
- 备注：用户列的 "SegADCIM" 在公开搜索里没找到完全同名工作，最接近
  命中即此 SEGA-DCIM。如果指的是另一篇请补充作者 / 会议关键词。

来源：https://arxiv.org/abs/2505.09451 ；
https://ieeexplore.ieee.org/document/10993192/

### EasyACIM (DAC 2024)

- 作者 / 单位：Haoyi Zhang, Jiahao Song, Xiaohan Gao, Xiyuan Tang,
  Yibo Lin, Runsheng Wang, Ru Huang，北大。
- 目标：模拟 CIM 端到端布图自动生成 + DSE，破解 ACIM
  "拓扑不可缩放、依赖人工"。
- 器件 / 电路：模拟 CIM (SRAM 基础)。
- 设计空间：阵列规模 + 自定义单元库；输出能效范围 50–750 TOPS/W。
- 保真度：模板化层次化 P&R 直到 GDS；电路级 (post-layout)，
  不涉及器件物理或 NN 精度。
- 优化方法：MOGA。
- silicon 数据：未声明。
- 代码：未公开。
- NN 精度：未支持。

来源：https://arxiv.org/abs/2404.13062 ；
https://dl.acm.org/doi/10.1145/3649329.3656229 ；
https://gaoxiaohan.com/publication/dac24_easyacim/

### AutoDCIM (DAC 2023)

- 作者 / 单位：J. Chen, F. Tu, K. Shao 等，HKUST。
- 目标：数字 CIM 宏自动综合编译器，开数字 CIM 自动化设计先河。
- 器件 / 电路：数字 SRAM CIM 宏。
- 设计空间：自定义存储单元 + 逻辑组件，自动化生成宏。
- 保真度：电路级 / 商业 EDA 流程。
- 优化方法：编译器 / 综合驱动；DSE 细节未在公开摘要中详述。
- silicon 数据：未声明。
- 代码：未公开。
- 影响：被 SEGA-DCIM、EasyACIM 等 DAC '24 / '25 工作引为 baseline。

来源：https://ieeexplore.ieee.org/document/10247976/ ；
https://dl.acm.org/doi/10.1109/DAC56929.2023.10247976 ；
https://fengbintu.github.io/publications/

### Eva-CiM (TCAD 2020)

- 作者 / 单位：Di Gao, Dayane Reis, Xiaobo Sharon Hu (圣母大学),
  Cheng Zhuo (浙大)。
- 目标：CPU + CiM 异构系统的程序级能耗 / 性能评估，回答
  "CiM 卸载值不值"。
- 器件 / 电路：SRAM-CiM、FeFET-RAM；面向通用程序而非 NN。
- 设计空间：内存层级、器件技术、CiM 阵列规格、负载特征。
- 保真度：系统级 — GEM5 (功能 + 时序) + McPAT (功耗) + DESTINY (memory)。
- 优化方法：无形式化搜索算法，提供"快速 DSE"的对比分析能力。
- silicon 数据：仅与 DESTINY 对标。
- 代码：GitHub `skycrapers/Eva-CiM` 开源 (C++ 73.8% / Python 16.8%)，
  许可证未明。
- 影响：CIM 早期系统级评估代表作，被广泛引用作为 NeuroSim 之外的
  "非 NN 中心" baseline。

来源：https://arxiv.org/abs/1901.09348 ；
https://github.com/skycrapers/Eva-CiM ；
TCAD 2020 DOI 10.1109/TCAD.2020.2966484

## 3. 对比矩阵

| 轴 | CIMFlow | SEGA-DCIM | EasyACIM | AutoDCIM | Eva-CiM | **MNSIM 2.0 + pim_sim** |
|---|---|---|---|---|---|---|
| 保真度 | 周期精确 + post-layout | RTL → Innovus | 模板化 P&R → GDS | 商业 EDA | 系统级 | **行为级 + wafer 校准物理修正** |
| 器件 | 数字 SRAM | 数字 SRAM | 模拟 SRAM | 数字 SRAM | SRAM / FeFET | **RRAM (主) + SRAM 锚点** |
| 优化方法 | DP 划分 | NSGA-II | MOGA | 综合驱动 | 比较分析 | **NSGA-II + MOBO + measured-in-the-loop** |
| Silicon 数据 | 无 | 无 | 无 | 无 | 无 | **wafer preset + Murmann 438 ADC** |
| NN 准确率 | 无 | 无 | 无 | 无 | 无 (面向通用程序) | **CIFAR / ImageNet top-1 闭环** |
| 多目标 HV 可比 | 否 | 是 (NSGA-II) | 是 (MOGA) | 否 | 否 | **是 (跨 trial 共享 ref point)** |
| 代码可得 | 承诺开源 | 未公开 | 未公开 | 未公开 | GitHub 开源 | 本仓库 |

## 4. 五条差异化机会

1. **NN 端到端准确率闭环**：5 家全部停在 PPA 或系统能耗，没有把
   "非对称变异 / IR-drop / ADC 量化"传到 top-1。我们能做。
2. **measured-in-the-loop**：没有竞品把 silicon / wafer 数据反向
   patch 进 SimConfig 再重新搜索；这是 pim_sim 的工作流（
   `dse/extras/run_measured_matrix.py` + 多 preset 跨场景排序）独占的方法学。
3. **RRAM 模拟 CIM 的多目标 DSE**：EasyACIM 是 SRAM 模拟，
   CIMFlow / SEGA-DCIM / AutoDCIM 全是数字 CIM；Eva-CiM 不覆盖 RRAM。
   这条赛道竞品稀疏。
4. **Walden FOM + Murmann 438 silicon ADC 校准**：竞品的 ADC 都是查表
   或固定假设；14 个 (architecture × era) preset 是文献里没看到的对应物。
5. **跨工艺 / 跨器件 surrogate**：所有竞品都是单工艺单器件假设；
   surrogate 训练 + 跨工艺 / 跨器件 transfer DSE 是空白带。

## 5. 五条威胁与警示

- **CIMFlow 直接点名 MNSIM 2.0** "tightly-coupled" → 论文叙事不要再写
  "基于 MNSIM 拓展"，要写"MNSIM 之上的物理 / 数据增强层 + DSE 闭环"。
- **EasyACIM / SEGA-DCIM** 已占据 "MOGA / NSGA-II on CIM" 的标题位 →
  我们卖点要落在"准确率 + 真实变异"而非"GA + CIM"。
- **CiMLoop** (arXiv 2405.07259) 自称 "flexible, accurate, fast CIM
  modeling"，与我们定位高度相似，需要单独排查。
- **NeuroSim V1.5** (arXiv 2505.02314, 2025) 强调 "device and
  circuit-level non-idealities improved"，与 pim_sim 卖点重叠最深；
  详细逐项对比见 `20_simulator/00_validation/neurosim_v15_vs_pim_sim.md`。
- **ChatNeuroSim** (LLM-agent for CIM DSE) 出现 → LLM-driven DSE
  是新护城河也是新威胁；下一轮调研重点。

## 6. 下一轮排查清单

- CiMLoop (arXiv 2405.07259) — 与 Timeloop / Accelergy 同源，最直接对手。
- NeuroSim V1.5 vs pim_sim — 已落地，见
  [`20_simulator/00_validation/neurosim_v15_vs_pim_sim.md`](../20_simulator/00_validation/neurosim_v15_vs_pim_sim.md)。
- ChatNeuroSim (LLM agent for CIM) — 评估 LLM-driven DSE 路径。
- IBM AIHWKit — 模拟 CIM 训练 + 推理框架，与 pim_sim 在 noise injection
  上重叠度待评估。
- Sandia CrossSim — wafer 数据驱动 + 多设备物理，最早期方法学对手。
