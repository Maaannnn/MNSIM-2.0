# 实验协议 (Experiment Protocol)

本文档是 `MNSIM + DSE + measured preset + robust evaluation` 课题的**科研层**协议，与 [`current_research_todo.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/status/current_research_todo.md) 的**执行层**明确分开：

- 本文档回答：问题怎么定义、假设是什么、场景怎么选、统计怎么算、对照怎么比、哪里会翻车
- TODO 文档回答：接下来要跑什么命令、产物放在哪、状态如何

本文档属于 pre-registration 性质：**在跑出结果前就固定**。如果需要修改，必须在本文档底部 Changelog 里显式记录「修改了什么、为什么、修改时是否已经看过对应结果」——后者是避免 p-hacking 的最低标准。

---

## 1. Formal Problem Statement

### 1.1 基本记号

| 记号 | 含义 |
|---|---|
| $x \in \mathcal{X}$ | 硬件设计变量（`xbar_size`, `pe_num`, `adc_choice`, `dac_num`, `sub_position`, `weight_bit`, `input_bit` 等） |
| $\mathcal{X}$ | 离散设计空间，目前主要两档：`rram_formal_v3`（36 点穷举用）与 `rram_guidance_v4`（搜索用，见 `dse/core.py:SPACE_PROFILES`） |
| $s \in \mathcal{S}$ | 非理想场景对象（scenario），包含 `Device_Resistance`、`Device_Variation`、`Device_SAF` 等字段（当前 contract v1 定义见 `dse/contracts.py`） |
| $w$ | 固定网络权重（首轮：`cifar10_vgg8_params.pth`） |
| $\xi$ | 噪声随机源（`weight_update` 中的高斯扰动、SAF 随机位置等） |
| $f(x, s; w, \xi) \in \mathbb{R}^3$ | PPA 向量：$(\text{latency\_ns}, \text{energy\_nJ}, \text{area\_um}^2)$ |
| $a(x, s; w, \xi) \in [0, 1]$ | 分类精度（CIFAR-10 top-1） |
| $\tau$ | 精度下限（当前 $\tau = 0.88$，见 `--accuracy-target`） |

### 1.2 三种问题变体

**(P1) Nominal Search**

$$
\min_{x \in \mathcal{X}} \; \mathbb{E}_\xi [f(x, s_0; w, \xi)] \quad \text{s.t.} \quad \mathbb{E}_\xi [a(x, s_0; w, \xi)] \geq \tau
$$

其中 $s_0$ 为默认 `SimConfig.ini` 的名义场景。这是 MNSIM 既有工作的默认设定。

**(P2) Robust Search（核心目标）**

给定场景集合 $\mathcal{S}_{\text{train}} \subseteq \mathcal{S}$ 和聚合算子 $\mathrm{Agg}_s$：

$$
\min_{x \in \mathcal{X}} \; \mathrm{Agg}_{s \in \mathcal{S}_{\text{train}}} \mathbb{E}_\xi [f(x, s; w, \xi)] \quad \text{s.t.} \quad \mathrm{Agg}_{s \in \mathcal{S}_{\text{train}}} \mathbb{E}_\xi [a(x, s; w, \xi)] \geq \tau
$$

本课题**必须在论文里显式选定一个**（不是两个都做）$\mathrm{Agg}$：

- **(P2.a) worst-case (minimax)**：$\mathrm{Agg} = \max$ 对目标、$\min$ 对精度约束
- **(P2.b) mean-case**：$\mathrm{Agg} = \mathbb{E}$
- **(P2.c) feasibility-aware**：目标为 $\mathbb{E}$，约束改为 feasibility rate $\Pr_{s}[a(x, s) \geq \tau] \geq \rho$（默认 $\rho = 0.8$）

**当前默认选择：(P2.c)**，理由：
- feasibility rate 是 measured-in-the-loop 研究中对下游部署最有意义的量
- `worst-case` 在当前只有 3 个 preset 时统计意义太弱（最差那个 preset 往往决定一切）
- `mean-case` 不能区分「偶尔小幅失败」和「频繁大幅失败」

Fallback：若 (P2.c) 在 3-preset 场景下 feasibility rate 全部贴近 1.0 或全部贴近 0，则回退到 (P2.a) + 报告 `acc_worst`。

**(P3) Calibration-Aware Evaluation**

这不是一个独立的优化问题，而是一个**评估口径**：

$$
a_{\text{calib}}(x, s; w, \xi) := a(x, s; w, \xi \mid M_{\text{calib}}(x, s; w))
$$

其中 $M_{\text{calib}}$ 表示用少量 calibration batch 在该 $(x, s)$ 下估计每层 ADC range / 量化范围等。`pim_sim/` 层给出了 asymmetric variation 模型、Walden ADC 模型和 IR-drop proxy 三个可注入 $M_{\text{calib}}$ 的部件。P3 的位置：用来做 **sensitivity check**（P2 的结论在 P3 评估口径下是否还成立），不用来直接构造最终 claim。

### 1.3 Rank Migration 的定义

这是论文的**关键实证量**。给定两个场景集合 $\mathcal{S}_A$、$\mathcal{S}_B$ 和设计点集合 $X \subseteq \mathcal{X}$：

$$
\pi_A: X \to \{1, \ldots, |X|\}, \quad \pi_B: X \to \{1, \ldots, |X|\}
$$

其中 $\pi_A(x)$ 是 $x$ 在 $\mathcal{S}_A$ 下按 (P2.c) 排序后的名次。定义：

- **Spearman 秩相关** $\rho(\pi_A, \pi_B)$：整体迁移强度
- **Top-k overlap** $|\text{top-}k(\pi_A) \cap \text{top-}k(\pi_B)| / k$：决策相关迁移
- **Kendall's tau**：抗 ties 的稳健补充

**论文主实证 claim**：$\mathcal{S}_A = \{s_0\}$（nominal）、$\mathcal{S}_B = \{$measured presets$\}$、$X$ = Pareto front under (P1)，期望 $\rho < 0.5$（弱相关），Top-5 overlap $< 60\%$。

---

## 2. 假设与证伪条件

每条假设都必须写清：**H**（陈述）、**H0**（零假设）、**ES**（最小可接受效应量）、**FC**（证伪条件）。未达到 ES 的结果一律按 null result 汇报，不得隐瞒。

### H1：Nominal-optimal 在 measured 场景下发生系统性迁移

- **H**：Nominal top-5 设计点中，至少 2 个在 measured preset 下的 (P2.c) ranking 里跌出 top-5。
- **H0**：Nominal top-5 与 measured top-5 的 overlap $\geq 80\%$（即最多 1 个迁移，属于随机扰动）。
- **ES**：Top-5 overlap $\leq 60\%$，且 Spearman $\rho \leq 0.5$（双指标同时满足）。
- **FC**：若两指标都不达标，本假设按 null 报告；论文不得把 "observed aggregation 里 4x4 排第 1" 这类单 metric 结果当成支持证据（当前 `cross_scenario_observed` 就只有这一个线索）。
- **Power 需求**：见 §4 样本量计算。

### H2：Measured preset 比 synthetic single-factor 更能揭示迁移

- **H**：用 `P1/P2/P3/P4` 这类合成 single-factor preset（`dse/core.py:RRAM_PRESETS`）得到的 rank migration 小于 measured preset（strong/typical/weak）得到的 migration。
- **H0**：两种 scenario 集合给出的 migration 在统计上等价（双 Spearman 差 $\leq 0.1$）。
- **ES**：$|\rho_{\text{synthetic}} - \rho_{\text{measured}}| \geq 0.2$，且方向为 measured 更小。
- **FC**：若 measured 未比 synthetic 明显差，则**不可**作为论文的 measured-preset novelty claim；需回到 positioning 文档把 claim 降级到版本 A（见 `robustmap_cim_positioning.md` §4.2）。

### H3：Robust search 优于 nominal search 在 held-out measured preset 上的表现

- **H**：用 (P2.c) 在 $\mathcal{S}_{\text{train}} = \{$strong, weak$\}$ 上搜索得到的 $x^\star_{\text{robust}}$，在 held-out $s_{\text{typical}}$ 上的 feasibility rate 高于 nominal 搜索得到的 $x^\star_{\text{nominal}}$。
- **H0**：两者在 $s_{\text{typical}}$ 上 feasibility rate 差 $\leq 0.05$。
- **ES**：feasibility rate 差 $\geq 0.15$，或 `acc_worst` 差 $\geq 0.02$。
- **FC**：当前只有 3 个 measured preset，所以 held-out 只能留 1 个，样本量先天不足。如果 H3 用 3-preset 拆 2+1 不能通过，必须在论文里如实写 limitation，不得把 train-test 合并的结果当成 generalization 证据。

### H4：ADC / sub_position 是 measured 场景下的补偿变量

- **H**：固定其他变量，`adc_choice`、`sub_position` 对 feasibility rate 的边际贡献在 measured preset 下显著高于 nominal（操作化：两因子 ANOVA 的 preset × ADC 交互项 $p < 0.05$）。
- **H0**：交互项 $p \geq 0.05$ 或效应方向相反。
- **ES**：交互项 $\eta^2 \geq 0.06$（中等效应量）。
- **FC**：当前仅 `ws2_a12_adc4` 单档数据，不能检验本假设；必须补 E6 小网格（见 TODO §8.T2.4）才能检验。在此之前，论文**不得**写「ADC 是 measured 场景下的主要补偿手段」。

### H5：nominal-ranking vs robust-ranking 的分歧不是 simulator noise

- **H**：H1 观察到的 top-5 迁移量超过 **simulator noise floor** 可解释的量。
- **Noise floor**：
  - PPA 侧：MNSIM 2.0 对流片宏单元的建模误差 3.8–5.5%（TCAD 2023 §IV；见 `docs/simulator/reference/MNSIM_完整技术分析报告.md:1546-1563`）。
  - Accuracy 侧：**无硅级 ground truth**。用同一 $(x, s)$、不同 $\xi$ 多次重复的 `std(a)` 作为**下界**。首轮 WS3 重复评估显示 $\text{std}(a) \approx 0.005$（3 repeats），这是**乐观**下界。
- **H0**：观察到的 ranking 差异可由 (PPA 建模误差) + (accuracy 注入噪声) 双重解释。
- **ES**：目标/精度差异量 $\geq 2 \times$ 对应 noise floor。
- **FC**：若迁移幅度 $< 2 \times$ noise floor，论文**不得**把它当 effect，必须在 threats to validity 段显式写出。这是为什么当前 strong-best 0.9473 vs weak-best 0.9453（相差 0.2%）**不能**单独作为 migration 证据——它远在 accuracy 噪声 std 的 2σ 之内。

---

## 3. Scenario Set 设计

### 3.1 三层 scenario

本课题采用三层 scenario 结构（源于 `robustmap_cim_positioning.md` §5.3）：

| 层级 | 代号 | 来源 | 当前资产 |
|---|---|---|---|
| L1 Nominal | $s_0$ | `configs/SimConfig.ini` | 稳定 |
| L2 Synthetic single-factor | $\mathcal{S}_{\text{syn}} = \{P_0, \ldots, P_4\}$ | `dse/core.py:RRAM_PRESETS` 人工构造 | 已编码 |
| L3 Measured / coupled | $\mathcal{S}_{\text{meas}}$ | `artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv` | **仅 3 个 preset** |

### 3.2 Measured preset 当前覆盖（如实记录）

- **共 3 个 preset**：`meas_cycle_strong`, `meas_cycle_typical`, `meas_cycle_weak`。
- **来源**：各自由 5 块 wafer 的 2T1R cycle 数据聚合得到（wafer_xy 编号见 CSV 第 2 列）。
- **字段只注入 3 项**：`Device_Resistance`、`Device_Variation`、`Device_SAF`。
- **已知局限**（见 CSV `note` 列）：
  - SAF 是 write-failure 数据的 **heuristic lower-bound**，不是真实 stuck-at 比例。
  - `retention_typical` 是所有 3 个 preset 的**默认且唯一**档位，retention 维度当前**没有**被当独立因子展开。
  - `typical` preset 的 `Device_Variation = 100.0` 已被 `pim_sim_todo.md` 判定为异常簇，WS1-T1.4 已排除出首轮 robust 评估。
- **对 H1/H2 的含义**：
  - $|\mathcal{S}_{\text{meas}}| = 3$，用于 (P2.c) aggregation 的统计功效很弱。
  - 3 个 preset 来自**同一批工艺、同一测试结构**（2T1R cycle）——本身不是独立同分布样本，更像 3 个快照。
  - 因此论文必须限定 claim 范围：「在该工艺 / 该测试结构下」，**不得**外推到任意 RRAM。

### 3.3 Scenario 扩展计划（用以改善功效）

按优先级：

1. 若 retention 能从 `retention_phase_summary.csv` 正式进入执行链（见 `pim_sim_todo.md`、TODO §T5B.2），$|\mathcal{S}_{\text{meas}}|$ 可扩展到 3 (cycle) × N (retention phase)。
2. 按单 wafer 而非 5-wafer 聚合得到更多 preset（最多 15 个），但代价是每个 preset 样本量更小。
3. 引入 `P0..P4` 作为 synthetic anchor，同时在论文里诚实标注「synthetic 不能代替 measured」。

### 3.4 $\mathcal{S}_{\text{train}} / \mathcal{S}_{\text{held-out}}$ 划分（pre-registered）

- **首轮**：$\mathcal{S}_{\text{train}} = \{\text{strong}, \text{weak}\}$，$\mathcal{S}_{\text{held-out}} = \{\text{typical}\}$。
  - 注：typical 的 variation=100 是已知异常，用它做 held-out 本身是个弱设计，但当前只有这 3 个 preset。
- **若扩展到 retention 维度**：train 用 cycle-only，held-out 用 cycle × retention。
- 此划分在任何 robust search 开跑前固定；修改划分必须记入 Changelog。

---

## 4. 统计计划

### 4.1 随机性来源与控制

| 随机源 | 来源 | 控制手段 |
|---|---|---|
| Weight noise $\xi$ | `weight_update` 高斯扰动、SAF 位置 | `noise_seed`（`dse/core.py:evaluate_config` 已新增，见 `pim_sim_todo.md` T5A.4） |
| Algorithm seed | NSGA-II / MOBO 采样 | `--seeds 42 43 44`（现有） |
| Calibration batch | `max_acc_batches` | 固定 `--max-acc-batches 4` |

### 4.2 样本量 pre-commitment

以下数字是 pre-registered，后续若实际用了更少，必须在 Changelog 说明原因：

| 量 | 首轮承诺 | 备注 |
|---|---|---|
| Algorithm seeds | **3**（最低） / 5（目标）| 当前 `rram_formal_v3_gpu1` / `rram_guidance_v4_gpu0` 已达 3 |
| Noise repeats per $(x, s)$ | **5**（最低）/ 10（目标）| 当前 WS3 只有 3，不达标，会导致 std 估计本身 CI 很宽 |
| Measured presets | **3**（已是上限） | 见 §3.2，无法在首轮提高 |
| Candidate 设计点集 (for H1/H3) | **≥ 16**（formal_v3 的 36 点 / E0 Pareto 子集）| 当前只有 4 点（matrix A 前 4），**严重不足** |

### 4.3 统计检验

- **H1（rank migration）**：Spearman $\rho$ + bootstrap 95% CI（1000 次）；Top-k overlap 通过 hypergeometric test 给 p-value。
- **H2（measured vs synthetic）**：配对比较 → Wilcoxon signed-rank（non-parametric，因 $\rho$ 分布未知）。
- **H3（train/held-out generalization）**：paired t-test on $\Delta$feasibility；由于 held-out 只有 1 preset，实质上只能给定性结论。
- **H4（ADC × preset 交互）**：two-way ANOVA，$\eta^2$ 作为效应量。
- **多重比较**：H1–H4 共 4 个预注册假设，Bonferroni 修正后的显著性阈值 $\alpha = 0.0125$。

### 4.4 Noise floor 承诺

- 任何 ranking / PPA / accuracy 差异 **必须**与 noise floor 比较：
  - PPA 差 $\geq 2 \times 5.5\% = 11\%$ 才算 effect。
  - Accuracy 差 $\geq 2 \times \hat{\sigma}_a$，其中 $\hat{\sigma}_a$ 用当前 $(x, s)$ 下 $\geq 5$ repeats 的 std（首轮用 0.005 为下界）。
- **已标记违规**：当前「strong best_acc=0.9473 vs weak best_acc=0.9453」差 0.002 ≈ 0.4 σ，**不构成** effect，论文不得引用此差异作为 migration 证据。

### 4.5 何时停止

- **H1 确认**：按 pre-registered ES 显著 → 推进 §5 baseline 对比。
- **H1 驳回（null）**：诚实报告，切换到 `StateCalib-MNSIM` 子课题 or 降级 claim（`robustmap_cim_positioning.md` §4.2 版本 A）。
- **不确定**（p 在 0.0125–0.05 之间）：追加 noise repeats 到目标档（10）并重跑；重跑一次后仍不确定，按 null 报告。

---

## 5. Baseline 清单

Baseline 的作用是定义**比较轴**，不是单纯「跑个别人的代码」。

### 5.1 主比较轴 (within-simulator)

| Baseline | 定义 | 实现路径 |
|---|---|---|
| **B1 NominalSearch** | 只在 $s_0$ 上按 (P1) 搜索，返回 top-k | `dse/run_dse.py --space-profile rram_formal_v3`（无 measured preset） |
| **B2 SingleScenarioAware** | 只在某一个 $P_k \in \mathcal{S}_{\text{syn}}$ 上搜索 | `dse/run_dse.py` + 修改 `scenario_json` 指向单一 synthetic preset |
| **B3 MeasuredOnly** | 只在 $\mathcal{S}_{\text{meas}}$ 上按 (P2.c) 搜索 | `dse/extras/run_measured_matrix.py` + cross-scenario 聚合 |
| **B4 RobustMap-CIM (ours)** | 在 $\mathcal{S}_{\text{syn}} \cup \mathcal{S}_{\text{meas}}$ 上按 (P2.c) 搜索 | 待实现：需扩展 `run_dse.py` 支持多 scenario 列表输入 |
| **B5 WorstCase (ablation)** | (P2.a) minimax on $\mathcal{S}_{\text{meas}}$ | 同 B3，改聚合算子 |

### 5.2 文献锚点 (cross-work)

下面是 `robustmap_cim_positioning.md` §2 已列出的相邻工作；论文 related work 必须与这些直接对位：

| 工作 | 类别 | 我们与它的差异 |
|---|---|---|
| NACIM ([1911.00139](https://arxiv.org/abs/1911.00139)) | variation-aware NAS | 我们固定 NN，做配置搜索，不做 NAS |
| Dense/Sparse DSE ([2201.06703](https://arxiv.org/abs/2201.06703)) | non-ideality × mapping trade-off | 我们做 **multi-scenario** 排序，它是 single-scenario trade-off |
| PR-CIM ([2110.09962](https://arxiv.org/abs/2110.09962)) | variation-aware training | 我们不改训练，改 design search objective |
| D-NAT | data-driven training compensation | 同上，工具路径不同 |

**禁止的 baseline 用法**：
- 不得把 NeuroSim 的 absolute accuracy 和 MNSIM 比（§7.2 of positioning）。
- 不得把 B1–B4 的 `absolute latency/energy` 与文献工作直接拼——只比 B1–B4 之间的**相对 ranking**。

### 5.3 论文最核心的 5 张比较图（不多不少）

1. **Fig.A**：Nominal Pareto vs Robust Pareto（2D 投影：latency vs energy，accuracy 作颜色）
2. **Fig.B**：Top-k rank migration matrix（行：B1 top-k；列：B3/B4 top-k；单元格：是否还在 top-k）
3. **Fig.C**：Feasibility rate comparison bar chart（B1–B5 在 held-out preset 上）
4. **Fig.D**：Robust objective (P2.c) improvement under same eval budget（B1 vs B4 的 HV 曲线）
5. **Fig.E**：Knob sensitivity heatmap（preset severity × `adc_choice` × `sub_position`）

每张图的原始数据必须能从 `artifacts/dse/` 的具体 run 目录溯源，不得从聚合 CSV 反推。

---

## 6. Threats to Validity

### 6.1 Construct validity（测量什么 = 想要的量？）

| 威胁 | 现状 | 缓解 |
|---|---|---|
| "Robustness" 的操作化是否合理 | (P2.c) feasibility-aware 已选定 | 同时报告 (P2.a) worst-case 作为 robustness check |
| Measured preset 是否真代表 "real device" | 3 个 preset × 5 wafer 聚合，来自**同一工艺同一测试结构**（2T1R cycle）| 论文 scope 限定为「该工艺」；不得外推 |
| SAF 字段 | 当前值是 write-failure 的 heuristic lower-bound（CSV note 已标注）| 论文必须在 §methodology 显式说明 SAF 是 proxy，不是真实 stuck-at 统计 |
| Retention 维度缺失 | `retention_typical` 固定一档 | 要么扩展到多档（见 §3.3），要么在 §limitations 诚实说明 |
| 分类精度的硅级 ground truth | **无**（见 CLAUDE 问答）| 论文必须写：end-to-end accuracy 仍是 simulator 输出；硅级 end-to-end 验证超出本工作范围 |

### 6.2 Internal validity（因果链是否可信？）

| 威胁 | 现状 | 缓解 |
|---|---|---|
| Ranking 差异是物理还是 simulator noise | MNSIM PPA 建模误差 3.8–5.5%，accuracy 无 ground truth | §4.4 noise floor 硬性约束：差异 $< 2\times$ floor 不算 effect |
| P-hacking / selective reporting | 当前 TODO 里已经出现「先跑 observed，发现 typical 排第 1 就当 evidence」的苗头 | 本文档 §2 的预注册假设 + Changelog 机制 |
| Confounding：measured preset 中变的不止一个变量 | `Device_Resistance`、`Device_Variation`、`Device_SAF` 同时变 | 做 H4 的单变量 ablation；B2（single-factor synthetic）专门用来做 attribution |
| Accuracy 侧只 1 次 forward 的偏差 | 当前 WS3 只 3 repeats | §4.2 承诺 $\geq 5$ repeats，目标 10 |

### 6.3 External validity（能泛化到哪？）

| 威胁 | 现状 | 缓解 |
|---|---|---|
| 只用 vgg8 + CIFAR-10 | 当前所有 run 都是 | E7 必须做 LeNet + ResNet18 的对照；若不做，论文 claim 限定为「on VGG8/CIFAR-10」 |
| 只用一组权重 | 无 adversarial / quantization-aware-trained 权重 | 不在本工作 scope；`limitations` 提一句 |
| 只用 MNSIM 一个 simulator | 无 NeuroSim / CrossSim cross-validation | §6.1 已说明 end-to-end 验证超出 scope；`pim_sim` 增强层可以作为 **internal** 敏感性分析（P3），不是 cross-tool |
| 3 个 measured preset 来自同一工艺 | 见 §3.2 | 严格限定 claim 范围 |

### 6.4 Conclusion validity（统计推断是否可信？）

| 威胁 | 现状 | 缓解 |
|---|---|---|
| 样本量不足 | §4.2 表已标出「4 candidate 严重不足」「3 noise repeats 不达标」 | E0（formal_v3 36 点穷举）+ 补 repeats 到 5 |
| 多重比较 | 4 个 pre-registered 假设 | Bonferroni $\alpha = 0.0125$ |
| 对同一数据做探索 + 检验 | TODO 里 `cross_scenario_observed` 已基于同一首轮数据得出「4x4 排第 1」| 本文档发布后，该结论**作废**（归入 exploratory），必须用新一批 repeats 重新检验 H1 |
| std 估计本身 CI 过宽 | 3 repeats 的 std CI 非常宽 | 统计功效检验前必须先把 repeats 提到 5+ |

---

## 7. 与 TODO 文档的接口

本文档定义「要证明什么」。TODO 文档定义「怎么跑到那里」。两者的映射：

| 本文档章节 | 对应 TODO 执行块 |
|---|---|
| §1 问题定义 | TODO §8.WS2 / WS3 的 scenario 注入、aggregation 脚本 |
| §2.H1 (migration) | TODO §8.WS3.T3.3 跨场景聚合；待补 E0 穷举 + 扩 candidate 集 |
| §2.H2 (measured vs synthetic) | 待在 TODO 新增任务：用 `RRAM_PRESETS` 跑一轮 single-factor 对照 |
| §2.H3 (train/held-out) | 待在 TODO 新增任务：robust search × 3 preset 的 held-out 划分 |
| §2.H4 (ADC × preset) | TODO §8.WS2.T2.4 补偿因子小网格（E6） |
| §2.H5 (noise floor) | TODO §8.WS3.T3.2 多 seed repeat 提到 5+ |
| §3.3 scenario 扩展 | TODO §8.WS5B retention scenario fields |
| §5 baseline 实现 | B4 需要 `run_dse.py` 扩展支持 multi-scenario；暂未在 TODO |

若发现有映射空缺（上面列出的 "待在 TODO 新增"），必须先补进 TODO 再执行，避免本文档和 TODO 脱节。

---

## 8. Changelog

| 日期 | 变更 | 是否在看过新数据后修改 | 理由 |
|---|---|---|---|
| 2026-04-20 | 初版（从 `current_research_todo.md` 剥离科研层）| 否（基于已有 WS1–WS3 first-look 证据）| 原 TODO 把问题定义、假设、统计计划和执行列表糅在一起，专业度不足 |

---

## 9. 本文档的使用约定

- 本文档是 pre-registered，不许**先看结果再改假设 / ES / scenario 划分**。任何这类修改都要在 Changelog 写「在看过 X 数据之后修改」。
- 论文写作阶段，Introduction 与 Methods 段落可以直接引用本文档 §1–§5；Limitations 段落直接对应 §6。
- 若决定切换子课题（见 `robustmap_cim_positioning.md` §10 的 `StateCalib-MNSIM` 分支），需要在本文档新建 §1bis / §2bis，而不是覆盖既有章节——保留历史假设可追溯。
