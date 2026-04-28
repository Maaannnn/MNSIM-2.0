# NeuroSim V1.5 vs pim_sim 逐项对比

Status: 2026-04-27 首发版。读前先看
[`competitor_landscape.md`](../../10_framework/competitor_landscape.md) §5
（NeuroSim V1.5 是当前威胁等级最高的同方向项目）。

## 1. NeuroSim V1.5 关键变更摘要

NeuroSim V1.5 (arXiv 2505.02314, 2025-05；CC-BY-NC-4.0；
GitHub `neurosim/NeuroSim`) 是 Shimeng Yu 组对 V1.4 的"软件骨干"重写，
定位仍是 ACIM 加速器的行为级 benchmark。四个头条变更：

1. **TensorRT 后训练量化集成** — 任意 PyTorch 预训练模型（含 Vision
   Transformer）无需重训练即可跑硬件评估；input / weight / ADC 三段
   calibration（max + histogram 两种方法）显式入流水线。
2. **柔性噪声注入** — 器件状态 mean / std 与 ADC 输出 mean / std 抽象为
   外部 CSV (`mem_states.csv`, `output_noise.csv`)，既可装 SPICE Monte
   Carlo 数据，也可装 silicon 测量数据。论文用 CIM A / B (FeFET, SPICE) 与
   CIM C (RRAM tape-out) / CIM D (nvCap) 四个 case 演示。
3. **器件谱拓宽到 nvCap** — charge-domain 电容式 NVM 加入。
4. **运行时 6.5× 加速** — GPU 路径优化，**非 surrogate**。

retention / drift 仍以幂律 G(t) = G₀(t/t₀)^v 显式建模，drift 与 SAF 在
`macro.py` 一次前向中显式注入；详见
[`neurosim_lessons_for_mnsim.md`](neurosim_lessons_for_mnsim.md) 第 96–119 行。

论文强调 V1.5 让 PPA + accuracy 联合 DSE 变得"系统化"，给出 Pareto 分析
（典型最优 ADC 精度 5–8 bit），但**未集成 NSGA-II / MOBO / surrogate
任何具体优化器**。

## 2. 完整对比矩阵

| 维度 | NeuroSim V1.5 | pim_sim | 证据 |
|---|---|---|---|
| D2D 变异（HRS/LRS 非对称） | 部分 — `mem_states.csv` 每 state 独立 mean/std，理论上可非对称，论文未把"HRS/LRS 非对称"作为头条 finding | **是** — `AsymmetricGaussianModel`，HRS/LRS 独立 σ_frac | NS: arXiv 2505.02314 §"flexible noise injection"；ours: `pim_sim/device/model.py:110-153` |
| C2C 变异 | 未在公开资料中找到明确实现 | 部分 — `EmpiricalDeviceModel` 通过 wafer cycle 数据的经验 CDF 间接吸收 | ours: `pim_sim/device/model.py:292-346` |
| Retention drift | **是** — 幂律 G(t)=G₀(t/t₀)^v；`inference.py` 暴露 `t,v,detect,target`；`macro.py:calc_drift()` | 否 | NS: `neurosim_lessons_for_mnsim.md:96-112`；ours 入口仅 3 模型 |
| Endurance / SAF | 是 (SAF) — 可配置 stuck@min/max 概率；endurance 未单独建模 | 是 (SAF) — 透传 MNSIM 的 `Device_SAF` 双侧概率；endurance 无 | NS: arXiv + macro.py；ours: `pim_sim/accuracy/weight_inject.py:195-199` |
| 电导非线性 | 未在公开资料中明确找到（V1.4 有 nonlinear write，V1.5 摘要未提推理侧 g–v 单独项） | 否 | — |
| IR-drop（一阶 / Elmore / 矩阵） | 部分 — H-tree 互连 RC 估时延能耗；TG 用 `R_TG = R_ON × DropTolerance` 设计裕度；**无显式 per-row crossbar IR-drop 影响 accuracy 的模块** | **是 (一阶)** — α=N·R_wire/R_avg，per-row 线性 scale 注入 conductance | NS: ASPDAC 2024 tutorial T1-1；ours: `pim_sim/array/ir_drop.py:99-145` |
| ADC 模型（查表 / Walden FOM / multi-arch） | 部分 — 动态算所需 ADC 精度（outmax 公式），Pareto 给 5–8 bit；架构层用解析模型 + standard cell 库；**未找到通用 Walden FOM 库或多架构选择器** | **是** — `WaldenADCModel`（连续 ENOB）+ 14-preset (architecture × era) 库 | NS: arXiv P_ADC=⌈log2(outmax)⌉；ours: `pim_sim/array/adc_model.py:62-117` + `adc_library.py:62-77` |
| ADC silicon 校准（Murmann / wafer） | 未找到 — V1.5 强调 "silicon-measured ADC output noise" (CIM C/D)，但是**整条 ADC 输出**的统计，不是 Murmann 类的 FoM 分层校准 | **是** — 14 个 Murmann ADC Survey 子集 (438 Nyquist ADCs, 1997–2026) | ours: `pim_sim/array/adc_library.py:35` 注 `Murmann ADC Survey rev20260314`；脚本 `validate/walden_murmann_validation.py` |
| DAC 建模 | 部分 — 支持可配 PDAC 精度 (PDAC=1 即 bit-serial)，无独立 FoM 库 | 否 — 继承 MNSIM 的 DAC，未做增强 | NS: arXiv §ADC/DAC |
| 电路寄生（SA、外设） | **是** — sense amp / TG / shifter / buffer 都有解析模型，"derived from standard cell libraries" | 否 — 依赖底层 MNSIM Hardware_Model | NS: arXiv §"analytical models for circuit blocks" |
| 精度链路：器件→top-1 | **是** — 量化校准 → 映射 → 噪声注入 → ADC → shift-add → 反量化 → top-1；CIM A–D 案例验证 | **是** — `pim_sim_weight_inject` 是 MNSIM `Weight_update` 的 drop-in 替换，下游走 MNSIM 的 `set_net_bits_evaluate` | NS: arXiv §accuracy chain；ours: `pim_sim/accuracy/weight_inject.py:91-203` |
| 工艺缩放（28→7 nm） | **是** — V1.4 已支持 22→1 nm（含 nanosheet / CFET），V1.5 评估侧重 22 / 28 nm | 部分 — `WaldenADCModel.technology_node_nm` 字段存在但未做主动缩放，PPA overlay 是 per-chip fitted | NS: arXiv + V1.4 release notes；ours: `pim_sim/array/adc_model.py:83` |
| 跨器件类型（RRAM / PCM / MRAM / FeFET / nvCap） | **是 (多)** — RRAM、FeFET、nvCap、SRAM；PCM / MRAM 在更早版本支持 | 否 — 仅 RRAM (calibrated_presets 全是 2T1R wafer) | NS: arXiv §"expanded device support"；ours: `pim_sim/device/calibrated_presets.py:45-61` |
| Wafer measured-in-the-loop | 部分 — V1.5 把 silicon-measured `output_noise.csv` 作为一种 expert-mode 输入 | **是** — 15 wafer preset + `measured_presets.csv` + `dse/extras/run_measured_matrix.py` 把 preset patch 进 SimConfig.ini 跑搜索 | NS: arXiv §"Circuit Expert Mode"；ours: `pim_sim/device/calibrated_presets.py:45-61` + `CLAUDE.md` "measured-in-the-loop" |
| 多目标 DSE (NSGA-II / MOBO) | **否** — 论文称"systematic DSE" + Pareto，但**未集成具体优化器**；ChatNeuroSim 才有 LLM 驱动搜索 | **是** — `dse/algorithms/{nsga2, mobo, bo_gp, random_sample}.py`，HV 共享 reference point | ours: `CLAUDE.md` "DSE layer (`dse/`)" + 仓内目录 |
| Surrogate 模型 | 未找到 — 6.5× 加速来自 GPU，不是 surrogate | 部分 — `dse/extras/` 有 surrogate dataset builder，`artifacts/dse/datasets/` 有数据集；正式训练流水线未声明 | ours: `CLAUDE.md` "datasets/ — surrogate training datasets" |
| 代码可得 + license | 是 — CC-BY-NC-4.0，github.com/neurosim/NeuroSim 公开 | 是 — 本仓库 (MNSIM-2.0 + pim_sim 增强层)，license 随 MNSIM 上游 | https://github.com/neurosim/NeuroSim |
| 与 MNSIM 的关系 | 独立竞品，无引用 | **MNSIM 增强层** — 通过 `pim_sim_model=` kwarg 插入 `dse/core.evaluate_config`，非 fork | ours: `pim_sim/__init__.py:22-33` |

## 3. 重叠点（NeuroSim 已经做、与 pim_sim 重复）

1. **Per-state Gaussian 器件噪声**：NS 的 `mem_states.csv (mean, std)`
   和 ours 的 `AsymmetricGaussianModel(state_cv_pct=[...])` 数学等价。
   NS 用 CSV 注入更通用，ours 用 dataclass 更易于在 DSE 内
   `build_overlay`。
2. **Silicon-measured 输入通道**：NS 把 silicon 测量塞进
   `output_noise.csv` (电路级聚合统计)，ours 塞进 `calibrated_presets.py`
   (器件级 CV%) 和 `measured_presets.csv`。语义层不同，目的一致。
3. **SAF**：完全重复，两边都是双侧 stuck@min/max 概率注入。
4. **量化-精度链路**：NS 显式 input / weight / ADC 三段 calibration；
   ours 透传 MNSIM 的 `set_net_bits_evaluate` + `PartialSumADCNoiseModel`
   把 ADC 量化误差等效到 conductance 噪声。两者覆盖同一物理效应，
   ours 是后挂一阶近似，NS 是前向显式建模 — **这一点 NS 更严谨**。
5. **Pareto / DSE 视角**：NS 论文给 Pareto 图；ours 整条 `dse/` 层做同样
   的事但更深入（NSGA-II / MOBO + HV 度量 + measured-in-the-loop robust）。

## 4. pim_sim 仍独有 / 仍可补位的轴

1. **多算法可比 DSE 与共享-ref-point Hypervolume**：NS V1.5 公开资料里
   **没有** NSGA-II / MOBO / BO-GP head-to-head + 共享 reference point HV。
   ours 的 `dse/` 是真正可发表的 DSE 工程框架，NS 在这层是"用户自己接"。
2. **Murmann ADC FoM 分层校准 (438 silicon 点, 14 presets)**：NS 用统计
   输出噪声接 silicon，没有 architecture × era 的 FoM 分层；ours 提供从
   `pipe_sar_modern` 到 `flash_legacy` 的连续插值能力，对 ADC 选型敏感性
   研究是独有手感。
3. **一阶 IR-drop 直接进入 accuracy 路径**：NS 用 `IR_DROP_TOL` 控制设计裕度
   （设计期），但论文没显示 per-row IR-drop scale 进入 accuracy 评估；
   ours 的 `IRDropModel` 把 `α = N·R_wire/R_avg` 直接乘到 conductance 矩阵
   上，与 array-size 扫描天然耦合。
4. **Measured-in-the-loop robust search**：ours 的工作流
   (`run_measured_matrix.py` + 多 preset 跨场景排序) 是 NS "把 silicon 数据
   塞进 CSV" 之上的一层方法学 — 它把 preset 当作搜索的环境扰动，而不是
   单一仿真输入。
5. **MNSIM 上游契约的非破坏性增强**：ours 不是 fork，可以随时落到 None
   回退（`pim_sim_weight_inject` 第 126 行），与 MNSIM byte-identical
   `Hardware_Model` 共存。NS 是独立工具，做不到这种"插拔式"对照实验。
6. **HRS/LRS 10× 非对称的实证证据**：ours 自带 15 wafer 的 robust IQR
   校准，证明 HRS_CV ≈ 31% / LRS_CV ≈ 3% (约 10×，文献多假设 1.8–2.5×)。
   NS 把 mean/std 留给用户填，没有这个跨 wafer 实证 finding。
7. **Retention / drift / nvCap / FeFET / 工艺缩放是 ours 仍空缺的轴** —
   NS V1.5 在这三处明确领先；若要补位，最低成本是把 `mem_states.csv` 风格
   的"状态表 + drift 幂律"加到 `pim_sim/device/model.py` 作为新
   `RetentionDriftModel`，而不是另起一套。

## 5. 论文叙事建议

写 paper 时与 NS V1.5 的对照轴落在三点：

- **DSE 工程化深度**：NSGA-II / MOBO + 共享 HV ref point + 多算法可比，
  这是 NS 没有的"框架级"贡献。
- **measured-in-the-loop**：preset patch 搜索环境，是 NS 之上的方法学
  推广，不要被理解成"我们也支持 silicon 输入"。
- **HRS/LRS 10× 非对称的实证 finding**：用 15 wafer + robust IQR 给出
  跨 wafer 一致结论，NS 的 CSV 接口本身不能代替这个 finding。

避免与 NS 直接抢的轴：

- retention / drift 与 nvCap / FeFET 跨器件 — 短期不补，
  补也是用 NS 的 CSV schema 反向兼容。
- 电路寄生 SA / TG / shifter — 留在 MNSIM Hardware_Model，不重做。

## 来源

- [NeuroSim V1.5 arXiv HTML](https://arxiv.org/html/2505.02314v1)
- [NeuroSim V1.5 arXiv abstract](https://arxiv.org/abs/2505.02314)
- [GitHub neurosim/NeuroSim (CC-BY-NC-4.0)](https://github.com/neurosim/NeuroSim)
- [ASPDAC 2024 NeuroSim Tutorial T1-1 (IR_DROP_TOL, H-tree RC)](https://www.aspdac.com/aspdac2024/archive/pdf/T1-1.pdf)
- [Shimeng Yu Lab Downloads](https://shimeng.ece.gatech.edu/downloads/)
