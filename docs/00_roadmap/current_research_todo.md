# 研究状态：执行总表 (Execution TODO)

本文档**只管执行**：下一步跑什么命令、结果去哪、状态如何、失败记录。

**不管的事**：问题定义、科研假设、统计计划、baseline 论证、threats to validity。这些全部在 [`experiment_protocol.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/status/experiment_protocol.md)。

如果你发现需要回答「我们想证明什么」「怎么算 effect size」「为什么选这个 scenario」——去 protocol 找，不在这里展开。

---

## 1. 本文档怎么用

### 状态标签

- `done`：任务跑通，且有产物路径
- `ready`：可立即执行，命令已就位
- `in_progress`：正在跑或正在回填产物
- `pending`：有前置依赖未满足
- `null`：已得到 pre-registered 的 null result（按 protocol §4.5 处理）
- `blocked`：遇到阻塞，已记录原因

### 更新规则

- 任务跑通 → 补产物目录路径 + 关键数字
- 任务失败 → 补失败原因，**不要删**
- 任务被 protocol 的假设证伪 → 改状态为 `null` 并引用 protocol 相应 §
- 如果某条判断是分析结论而非实验事实，在句首标 **「判断：」**

### 真源优先级

1. [`experiment_protocol.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/status/experiment_protocol.md)（科研层）
2. 本文档（执行层）
3. [`agent.md`](/Users/bytedance/workspace/MNSIM-2.0/agent.md)（roadmap）
4. 具体脚本与结果目录

---

## 2. 已有资产（事实记录，不是计划）

### 代码入口

- [`dse/core.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py)
- [`dse/run_dse.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/run_dse.py)
- [`dse/run_matrix_csv.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py)
- [`dse/extras/extract_measured_presets.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/extract_measured_presets.py)
- [`dse/extras/run_measured_matrix.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_measured_matrix.py)
- [`dse/extras/run_robustness.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_robustness.py)
- [`dse/extras/run_cross_scenario_robustness.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_cross_scenario_robustness.py)
- [`dse/extras/backfill_experiment_contracts.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/backfill_experiment_contracts.py)
- [`dse/contracts.py`](/Users/bytedance/workspace/MNSIM-2.0/dse/contracts.py)

### 资产目录

- `artifacts/dse/matrices/rram_v2/`（matrix A–E CSV）
- `artifacts/dse/search_runs/`（算法搜索输出）
- `artifacts/dse/matrix_runs/`（矩阵/measured 输出）
- `artifacts/dse/datasets/`（采样数据集，含 800 样本版）
- `artifacts/dse/testdata_runs/`（measured preset 提取输出）
- `artifacts/dse/testdata_analysis/`（测试数据聚合）
- `artifacts/dse/invalidation_registry.json`（失效注册表）

---

## 3. 工作流总板

| 工作流 | 名称 | 当前状态 | 优先级 | 依赖 |
|---|---|---|---|---|
| WS0 | 研究边界与文档基线 | `done` | P0 | 无 |
| WS1 | measured preset 提取 | `done` | P0 | `test_data/` |
| WS2 | nominal / measured matrix 实验 | `done (first-look)` | P0 | WS1 |
| WS3 | robust ranking 与重复评估 | `in_progress` | P0 | WS2 |
| WS4 | 会议子课题收敛 | `pending` | P0 | WS1–WS3 + protocol H1/H2 裁决 |
| WS5A | 实验接口与输入输出收束 | `done (v1)` | P1 | 无 |
| WS5B | 物理建模轻量增强 | `pending` | P1 | protocol §2.H5 判断 noise floor 是否卡结论 |
| WS6 | 论文写作与组会资产 | `pending` | P1 | WS3 + protocol 各假设结论 |

协议层的对应在 [`experiment_protocol.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/status/experiment_protocol.md) §7 表格。

---

## 4. 详细任务分解

### WS0 研究边界与文档基线

- **T0.1** 固定主线表述 — `done`。输出：`docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md` + 本文档 §3。
- **T0.2** 固定术语边界 — `done`。输出：`docs/simulator/mnsim_fidelity_gap_review.md`。
- **T0.3** 维护本文档与 protocol — `ready`。每完成一个任务回填状态 + 路径；任何假设改动同步 Changelog。

### WS1 measured preset 提取

- **T1.1** 跑通提取主脚本 — `done`。
  - 产物：`artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv`, `summary.json`, `cycle_state_summary.csv`, `retention_phase_summary.csv`
  - 命令：`bash artifacts/dse/scripts/run_testdata_analysis.sh`
- **T1.2** 备用脚本路径差异核对 — `done`。当前主流水线统一读 `testdata_runs/run_20260417_142758/measured_presets.csv`。
- **T1.3** Sanity check — `done`。当前 3 个 preset：`meas_cycle_strong`, `meas_cycle_typical`, `meas_cycle_weak`。典型 preset variation=100 异常，已排除。
- **T1.4** 固定首轮 preset 集 — `done`。首轮使用：`strong` + `weak`。held-out：`typical`。（详见 protocol §3.4）

### WS2 nominal / measured matrix 实验

- **T2.1** 明确矩阵子集 — `done`。首轮：`matrix_name=A`, `max_points=4`。
- **T2.2** 用 measured preset 跑 1–2 个点 — `purged 2026-04-20，需重跑`。
  - 历史产物 `artifacts/dse/matrix_runs/ws2_firstlook_20260417/` 已于 2026-04-20 物理删除（2026-04-17 measured-preset override bug 影响），审计见 `invalidation_registry.json` 的 `purged` 段。
  - 历史摘要（不再作为证据）：strong `best_acc=0.9473`, weak `best_acc=0.9453`，差 0.002 在 noise floor 内。
  - post-fix 重跑命令模板：
    ```bash
    .venv/bin/python dse/extras/run_measured_matrix.py \
      --measured-presets-csv artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv \
      --preset-name meas_cycle_strong meas_cycle_weak \
      --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
      --matrix-name A --max-points 4 \
      --base-config SimConfig.ini --weights cifar10_vgg8_params.pth --nn vgg8 \
      --device mps --dataset-module MNSIM.Interface.cifar10 \
      --space-profile rram_v2 --max-acc-batches 2 \
      --run-accuracy --accuracy-target 0.88 \
      --enable-saf --enable-variation \
      --seed 42 --workers 1 \
      --output-root artifacts/dse/matrix_runs/ws2_firstlook_20260417
    ```
- **T2.3** 扩展到 3 preset × 小批矩阵点 — `in_progress`。
  - 当前仅 `strong/weak` 各 4 点，candidate 集**严重不足**（protocol §4.2 要求 ≥ 16）。
  - 下一步：`matrix_name ∈ {A,B,C}` × `max_points=4` × `strong/weak/typical`。
- **T2.4** 补偿策略小网格（E6）— `ready`。
  - `ADC ∈ {4,6,7} × DAC ∈ {32,128} × sub_position ∈ {0,1}` × `strong/weak` = 24 点
  - 历史占位 `ws2_a12_adc4_20260417_202725` 已 purged 2026-04-20，需从零开始跑。
- **T2.5** formal / guidance 空间主线实验 — `done (first pass)`。
  - 产物：
    - `artifacts/dse/search_runs/rram_formal_v3_gpu1/comparison/`（random/nsga2/mobo × 3 seed；HV 打平）
    - `artifacts/dse/search_runs/rram_guidance_v4_gpu0/comparison/`（同上；有分化）
  - 缺：formal_v3 的 36 点穷举 Ground Truth（E0）；目录 `matrix_runs/exp_formal_v3_exhaustive/` 存在但**只有 configs，没有结果**。
- **T2.6** 〔新〕E0 穷举跑满 — `ready`。P0。
  - 命令：`bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh DEVICE=mps MAX_ACC_BATCHES=4`
  - 目标：为 H1 提供足够大的 candidate 集（16+ 点）。

### WS3 robust ranking 与重复评估

- **T3.0** 审查结论回写 — `done`。
  - `--input-root` 指向 preset 根目录，不是 `matrixcsv_seed42/`
  - `run_robustness.py` 的 `sys.path` bug 已修
  - measured preset 当前只注入 `Device_Resistance / Variation / SAF`；retention 停在摘要层
- **T3.1** 固定 robust 指标 — `done`（协议层见 protocol §1.2）。
  - 指标：`accuracy_mean`, `accuracy_worst`, `accuracy_std`, `feasibility_rate`。默认聚合：(P2.c) feasibility-aware。
- **T3.2** 跑 1 组重复评估 — `purged 2026-04-20，需重跑`。
  - 历史产物 `ws2_firstlook_20260417/.../robustness/` 已删除，原因同 T2.2。
  - 历史记录（仅供 protocol §6.4 的 exploratory 下调参考）：3 repeats，strong 与 weak 的 `pe_num=2x2` / `4x4` 两个 candidate 的 `mean/worst/yield` 完全相同。
  - post-fix 重跑目标：repeats ≥ 5（最低档），目标 10。
- **T3.3** nominal vs robust ranking 对比 — `purged 2026-04-20，需重跑`。
  - 历史 `cross_scenario_observed/summary.csv` 和 `cross_scenario_robustness/summary.csv` 已与父 run 一起删除。
  - 历史结论「4x4 排第 1」按 protocol §6.4 原本就归入 exploratory，purge 只是消除对其的误引用风险。
  - 下一步：T2.6 穷举 + T3.2 扩 repeats 完成后，用新 candidate 集重跑 cross-scenario 聚合。
- **T3.4** 〔新〕Synthetic single-factor 对照（H2 所需）— `ready`。
  - 在 `dse/core.py:RRAM_PRESETS` 的 `P0..P4` 上做同一套 candidate 评估，与 measured preset 对照
  - 产物目标：`artifacts/dse/matrix_runs/synth_vs_meas_<date>/`
- **T3.5** 〔新〕Held-out generalization（H3 所需）— `pending (依赖 T3.4)`。
  - train = {strong, weak}, held-out = {typical}
  - 在 held-out 上评估 B1（nominal-optimal）vs B4（robust-optimal）的 feasibility
- **T3.6** 判断 robust 证据是否足够 — `pending`。
  - 输入：T2.6 + T3.2 + T3.3 + T3.4 + T3.5 结果
  - 输出：protocol §4.5 的「继续 / 收缩 claim / 切 StateCalib」决策，写入 protocol Changelog

### WS4 会议子课题收敛

- **T4.1** 比较两个候选方向 — `ready`。
  - 候选：`RobustMap-CIM` / `StateCalib-MNSIM`
  - 判据：protocol §2 的 H1 + H2 结果
- **T4.2** 固定主方向 — `pending (依赖 T3.6)`。
- **T4.3** 写最小论文包（title / problem / contributions / baselines / experiments）— `pending`。

### WS5A 接口与输入输出收束

- **T5A.1** 统一 experiment manifest — `done (v1)`。`dse/contracts.py` 已上线。
- **T5A.2** 统一 measured scenario 输入口 — `done (v1)`。`scenarios/<preset>.json` + `--scenario-json` 已接入。
- **T5A.3** 结果 schema 与路径解析 — `done (v1)`。`load_results_from_dir()` 做本地 fallback。
- **T5A.4** 显式 seed 与复现实验口径 — `done (v1)`。`noise_seed` 已接入 `evaluate_config`/`run_matrix_csv`/`run_robustness`。
- **T5A.5** 先做小范围收束再扩实验 — `in_progress`。
  - smoke 验证历史目录（`ws5a_measured_smoke_acc` 等）已 purged 2026-04-20；contract/scenario schema 本身（T5A.1–T5A.4）已在代码中固化，不需要历史 smoke 目录。
- **T5A.6** 旧 run 回填 contract — `done (key runs first batch, 23 trials)`。
  - 命令：见 `dse/extras/backfill_experiment_contracts.py` 的 `--help`

### WS5B 物理建模轻量增强

**进入条件（硬性）**：以下**同时**成立才能进入，否则停在 pending：

- WS5A 已收束（✅）
- protocol §2.H5 判定当前主结论**被 simulator noise floor 卡住**（当前：未判定）
- 候选增强的数据资产齐全（retention / ADC calib batch / state LUT）
- 有 nominal regression / 速度开销 / 解释增益 三指标定义

候选顺序（见 `mnsim_fidelity_gap_review.md` §4）：
1. device state LUT
2. ADC CALIB
3. drift / retention scenario fields
4. IR-drop proxy

**独立进展（与 WS5B 平行）**：`pim_sim/` 增强层已完成 dev（见 `pim_sim_todo.md`），但**未接入主实验 run**。若 WS4 收敛到 `StateCalib-MNSIM`，`pim_sim` 接入 E1/E5/E6 的工作立即升为 P0。

### WS5C pim_sim 精度验证与下游 DSE 闭环

**目的**：把 `pim_sim/` 从"存在性证明"升级为"可审稿的保真度证据"。直接落 pim_sim_todo.md 的 HIGH PRIORITY 两条 + 精度饱和问题。

**前提诊断**：`validate/output/accuracy_comparison.csv` 表明 VGG8/CIFAR-10 在 strong/weak preset 下精度相同（均 0.942x，差值 < noise floor）。要让 pim_sim 的 claim 成立必须换更敏感的网络。决策（2026-04-20）：**focus ResNet-20 INT4 + CIFAR-10**；如时间允许再做 32×32 小阵列。

- **T7.1** ResNet-20 + INT4 QAT 训练 — `ready`。P0。
  - 新脚本：`scripts/train_resnet20_int4.py`（参考 `MNSIM/NetStruct/resnet18.py` 加 4-bit QAT）
  - 产物：`weights/cifar10_resnet20_int4_params.pth`，baseline float accuracy ≥ 0.91
  - 估时：~1 天（含训练收敛）
- **T7.2** ResNet-20 集成进 MNSIM Interface — `ready`。P0。
  - 新增：`MNSIM/NetStruct/resnet20_cifar10.py`
  - 注册：`MNSIM/Interface/network.py` 的 `get_net` 分支
  - 冒烟：`python main.py -NN resnet20 -Weights cifar10_resnet20_int4_params.pth -HWdes SimConfig.ini`
  - 估时：0.5 天
- **T7.3** 重跑 accuracy_comparison on ResNet-20 INT4 — `pending (T7.1, T7.2)`。P0。
  - 命令：`.venv/bin/python -u validate/compare_accuracy_models.py --nn resnet20 --weights weights/cifar10_resnet20_int4_params.pth --trials 5 --max-batches 3`
  - 产物：`validate/output/accuracy_comparison_resnet20_int4.csv`
  - 通过条件（protocol §4.4）：strong vs weak 均值差 ≥ 2σ；否则走 null 路径切 32×32（T7.5）
  - 估时：0.5 天
- **T7.4** DSE 闭环：pim_sim-patched 噪声模型替换 MNSIM 默认 — `pending (T7.3 通过)`。P1。
  - 修改：`dse/run_matrix_csv.py` + `dse/extras/run_measured_matrix.py` 加 `--pim-sim-preset {strong,weak,typical_robust}`
  - 目标：对 T2.6 产出的 formal_v3 36 点 candidate 集，分别用 `MNSIM-sym`(baseline) 和 `pim_sim-asym` 评估，比较 Pareto 前沿 + rank migration (Spearman / Top-k overlap / Kendall，按 protocol §1.2)
  - 产物：`artifacts/dse/matrix_runs/formal_v3_pimsim_<date>/{mnsim_sym,pim_sim_asym}/`
  - 这是 pim_sim_todo.md "Paper Claim 5：pim_sim 改变 DSE Pareto 前沿形状" 的唯一证据来源
- **T7.5** (条件触发) 32×32 小阵列补充验证 — `pending (T7.3 通过后视时间)`。P2。
  - 修改：SimConfig.ini 的 `Xbar_Size = 32,32`；只改 scenario patch，不改 baseline
  - 产物：`validate/output/accuracy_comparison_xbar32.csv`
  - 目的：验证 IR-drop 效应反向 null 控制（阵列越小 α 越小）
- **T7.6** Paper claim checklist 收束 — `pending (T7.4)`。
  - 对 `pim_sim_todo.md` 末尾 checklist 的最后两条（DSE Pareto 前沿形状 + 大阵列精度被 MNSIM 高估）给出 ✅ / ⬜ / null 判定
  - 写入 `experiment_protocol.md` Changelog 一条

### WS8 文献芯片锚定 + Ablation（保真度证据主线）

**目的**：回答审稿人"如果没有自己的 silicon，凭什么说 pim_sim 比 MNSIM 更准？哪一项改进贡献了多少？"——用 MNSIM 原论文 §VII.B 一模一样的方法论，拿公开 ISSCC 芯片的 published PPA breakdown 作 ground truth，加 ablation 拆贡献。

**关键背景**（校正 2026-04-20 之前的错误认知）：MNSIM TCAD 2023 §VII.B 的两颗验证芯片是**公开 ISSCC 论文**，不是汪玉组内部未披露芯片：
- Ref [10] = B. Yan et al., "A 1.041-Mb/mm² 27.38-TOPS/W signed-INT8 dynamic-logic-based ADC-less SRAM CIM macro in 28nm", **ISSCC 2022 Paper 11.7**
- Ref [27] = Q. Liu et al., "A fully integrated analog ReRAM based 78.4 TOPS/W compute-in-memory chip", **ISSCC 2020 Paper 33.2**

验证粒度：macro 级 PPA，不是 end-to-end CNN accuracy。

- **T8.1** 复现 MNSIM 原论文 3.8% / 5.5% — `ready`。P0（阻塞 T8.2 全部后续）。
  - 输入：ISSCC 2022 Paper 11.7 + ISSCC 2020 Paper 33.2 的 device/circuit 参数
  - 产物：
    - `docs/simulator/mnsim_validation_replication_plan.md`：两篇 ISSCC 论文参数到 `SimConfig.ini` key 的映射表
    - `validate/output/literature_anchor/baseline_mnsim_vs_issc.csv`：MNSIM 预测 vs 论文 published 值的误差表
  - 通过条件：复现出的 relative error 落在 [2.5%, 5.0%]（SRAM）+ [4.0%, 7.0%]（RRAM），证明参数映射正确
  - 未通过：说明参数抄错 / MNSIM 版本偏移，不能进 T8.2

- **T8.2** pim_sim ablation（5 配置 × 2 芯片 = 10 次仿真）— `pending (T8.1 通过)`。P0。
  - 共同输出：`validate/output/literature_anchor/ablation_<chip>.csv`（列：config, metric, mnsim_pred, pim_sim_pred, chip_meas, rel_error）
  - **T8.2a** 配置 B — 只开 `AsymmetricGaussianModel`（HRS=31.5%, LRS=3.1%） — `pending`
  - **T8.2b** 配置 C — 只开 `IRDropModel`（R_wire=0.5Ω, R_dev=5kΩ，按芯片实际尺寸） — `pending`
  - **T8.2c** 配置 D — 只开 `WaldenADCModel`（FOM_W=20 fJ/conv, FOM_A=8 µm²） — `pending`
  - **T8.2d** 配置 E — 三项全开 — `pending`
  - 预期 ablation 结论：误差下降分解成 3 个 axis 的独立贡献 + 可能的交互项；每项贡献需 ≥ 0.2%（否则写 "not isolable from noise"）

- **T8.3** 扩展到 3 颗额外 ISSCC/Nature chip — `pending (T8.2 至少有 1 颗跑通)`。P1。
  - 候选（全部公开，可下载）：
    - **NeuRRAM** — Wan et al., Nature 2022，48-core RRAM CIM（重量级，breakdown 公开）
    - **ISSCC 2021 Paper 14.2** — Jia et al., 28nm SRAM-CIM
    - **ISSCC 2023 Paper 7.1 / 7.2** — 最新一代 RRAM-CIM（根据参数披露完整度择优）
  - 工作量：每颗 ~0.5 天（参数抄取 + 5 配置 ablation）
  - 目标：5 颗样本跨 SRAM/RRAM 两类，写 "across N=5 published CIM chips, pim_sim reduces modeling error from avg X% to avg Y%"

- **T8.4** Ablation 表与攻防问答 — `pending (T8.2, T8.3)`。P1。
  - 产物 1：论文 "money table" —— 芯片 × 配置 × metric 的 ablation 矩阵（LaTeX table + CSV source）
  - 产物 2：`docs/simulator/reviewer_qa_prep.md`，对以下 3 个典型质疑预备答案：
    - Q1: 如果 asym device 贡献 < 0.5%，为什么还留？（答：INT4 / MLC 下主导；wafer 直接证据）
    - Q2: 如何排除 cross-contamination？（答：ablation 定义即隔离；B/C/D 单开实验已隔离）
    - Q3: 为什么不做 drift / retention？（答：无温控长时测量数据，诚实声明范围）

- **T8.5** WS8 与 WS7（ResNet-20 INT4）的整合 claim — `pending (T7.6, T8.4)`。
  - 两条独立证据链：macro-level（T8.1–T8.4） + downstream-DSE（T7.4）
  - 最终论文 Section 4 骨架：4.1 literature-anchored PPA ablation / 4.2 DSE Pareto migration / 4.3 threats to validity
  - 输出：`docs/paper/section_4_outline.md`

### WS6 论文写作与组会资产

- **T6.1** 固定章节映射 — `ready`。依 protocol §1–§6 对应章节。
- **T6.2** 固定图表清单 — `ready`。直接用 protocol §5.3 的 5 张核心图。
- **T6.3** 讲稿底稿 — `pending`。

---

## 5. 两周执行清单

### 第 1 周（本周）

- **P0**：T8.1（复现 MNSIM 原论文 3.8%/5.5%，阻塞 T8.2 全部）
- **P0**：T7.1 + T7.2 + T7.3（ResNet-20 INT4 训练 → 集成 → accuracy_comparison 重跑）
- **P0**：T2.6（E0 穷举跑满）
- **P1**：T2.2 / T2.3 post-fix 重跑 measured matrix（strong + weak + typical，matrix A+B+C × max_points=4）
- **P1**：T3.2 重跑 repeats = 5（最低档），目标 10

### 第 2 周

- **P0**：T8.2a–d（pim_sim ablation 5 配置 × 2 芯片）
- T7.4 DSE 闭环（MNSIM-sym vs pim_sim-asym 的 Pareto 前沿对比）
- T8.3 扩展到额外 3 颗 ISSCC/Nature 芯片（至少 1 颗跑通）
- T3.3 用新 candidate 集 + 新 repeats 正式检验 H1（按 protocol §2）
- T3.4 synthetic single-factor 对照（H2 准备）
- T3.5 held-out generalization（H3）
- T3.6 / T7.6 综合判断；更新 protocol Changelog
- T8.4 / T8.5 ablation money table + 攻防问答准备
- 准备 T4.1 决策材料

---

## 6. 立即可执行的 6 件事

1. **T8.1 参数抄取**：下载 ISSCC 2022 Paper 11.7 + ISSCC 2020 Paper 33.2，抄参数到 `docs/simulator/mnsim_validation_replication_plan.md`，MNSIM 复现跑 relative error
2. ResNet-20 INT4 训练：新写 `scripts/train_resnet20_int4.py`（T7.1）
3. 穷举 formal_v3：`bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh DEVICE=mps MAX_ACC_BATCHES=4`
4. post-fix 重跑首轮 measured matrix：`dse/extras/run_measured_matrix.py --preset-name meas_cycle_strong meas_cycle_weak --matrix-name A --max-points 4 --output-root artifacts/dse/matrix_runs/meas_firstlook_<date>`
5. 补 candidate：`run_measured_matrix.py` 用 `matrix_name=A,B,C` × `max_points=4`
6. ResNet-20 accuracy_comparison（依赖 #2）：`validate/compare_accuracy_models.py --nn resnet20 --trials 5`

**合并最小命令链**见 protocol §7 映射表对应的脚本路径，不在这里重复展开。

---

## 7. 风险与停止条件

完整 threats to validity 见 [`experiment_protocol.md`](/Users/bytedance/workspace/MNSIM-2.0/docs/status/experiment_protocol.md) §6。本节只列**执行层**风险。

### 执行风险

| 风险 | 触发表现 | 控制动作 |
|---|---|---|
| 范围膨胀 | 同时推进 WS2 扩点 + WS5B 建模增强 + WS4 收敛 | 先把 WS3 的 H1/H2 跑出裁决结果再决定 WS4 和 WS5B |
| measured preset 退化成参数替换 | 只改 variation/SAF，没统计解释 | 必须同时提供来源 + 摘要 + ranking 变化 |
| 强行 robust claim | 只有单次结果就写「鲁棒」 | 无 mean/worst/yield + feasibility rate 不得用 robust 结论 |
| H1 数据已经部分 peek 过 | `cross_scenario_observed` 已基于首轮数据得出「4x4 排第 1」 | 已在 protocol §6.4 降级为 exploratory；必须新数据重测 |

### 停止条件

- **WS1**：若 `measured_presets.csv` 不稳定生成 → 停在数据筛选
- **WS2**：若 preset 注入 SimConfig 跑不通 → 查兼容性，不解释成器件退化
- **WS3**：若 H1 按 protocol §2 判 null → 诚实报告，切 `StateCalib-MNSIM` 或降级 claim
- **WS5B**：若 WS5A 未收束 → 不进入
- **WS5B**：若升级后只「更复杂」不增强解释力 → 停止

### 明确不做

- 不同时推两条完整会议线
- 不把 `dse/` 误写成 MNSIM 原生模块
- 不把 MNSIM 轻量升级包装成「完整替代 NeuroSim/CrossSim」
- 不把单次结果包装成 robust claim
- 不在 H1 未裁决前默认「大阵列最优点迁移」存在

---

## 8. 验收速查

| 工作流 | 最低验收 | 对应 protocol |
|---|---|---|
| WS1 | 生成可审计的 `measured_presets.csv` | §3.2 |
| WS2 | ≥ 3 preset × ≥ 16 candidate × ≥ 3 matrix class 跑通 | §4.2 |
| WS3 | H1/H2 结论（confirmed / null）+ Changelog 更新 | §2 + §8 |
| WS4 | 一句话讲清子课题 problem statement（引用 protocol §1） | §5 |
| WS5A | 新旧 run 都带 contract v1 | — |
| WS5B | nominal regression 通过，主结论解释力提升 | §2.H5 |
| WS6 | protocol §5.3 的 5 张图全部有原始 run 溯源 | §5 |

---

## 9. 本文档持续回填

每次任务推进，优先回填：

- 任务状态
- 真实产物目录 + 关键数字
- 失败记录
- 是否命中 protocol 某条假设（confirmed / null / undetermined）
- 是否影响 WS4 子课题选择
