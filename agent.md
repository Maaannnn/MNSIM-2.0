# MNSIM-2.0 论文实验 Agent（计划与清单）

本文档给出一套可落地的论文级实验方案与执行清单，充分利用当前仓库资产与实验室 `test_data/` 的真实测试数据，形成“Measured-in-the-loop（真实测量驱动）”的创新主线。所有命令均在仓库根目录执行，默认本机 MPS/CPU，可切换到服务器 CUDA。

## 论文主线与贡献点
- RQ1 基线可解性：在正式空间（`rram_formal_v3`）内，Pareto 前沿与可行域（acc≥0.88）的真实形态是什么？
- RQ2 算法效率：随机/NSGA-II/MOBO 在同等评估预算下的帕累托质量差异与收敛特性？
- RQ3 设计指导：在更大空间（`rram_guidance_v4`）中，矩阵实验结论是否稳健（如 512×512 + 2×2 + 高带宽 + ADC=6 + DAC=128）？
- RQ4 Measured-in-the-loop：用 `test_data/` 真实数据导出的“器件状态预设（measured presets）”替代/对比默认器件预设，评估 PPA 与可行域变化，并进行鲁棒搜索（multi-scenario）。
- RQ5 跨网络泛化：在 LeNet/VGG16/ResNet18 等权重下，指导结论是否保持？

创新性
- 以 `test_data/` 驱动的“Measured Preset → 自动补丁 SimConfig.ini → 矩阵/搜索一体化”流水线（仓库已内置脚本）。
- 鲁棒优化评估：在多个 measured preset 场景下，比较设计点/搜索算法的“稳健 HV（min/均值-HV）”与“可行率”。
- 设计补偿策略验证：系统性评估 ADC/DAC 档位与减法位置（analog vs digital）对抗器件劣化/SAF 的补偿效果。

## 仓库资产（已就绪）
- 权重与配置：`weights/*.pth`、`configs/SimConfig.ini`（根目录提供符号链接保证兼容）。
- 真实数据：`test_data/`（与 `测试数据/` 同步镜像，真实器件测试更有价值）。
- 脚本（关键）：
  - 穷举与搜索：`dse/run_matrix_csv.py`、`dse/run_dse.py`；脚本封装见 `artifacts/dse/scripts/*.sh`。
  - measured 流水线：`artifacts/dse/scripts/run_testdata_analysis.sh`、`dse/extras/run_measured_matrix.py`。
  - 可视化/数据库：`app/server.py`（本地 SQLite `app/dse_records.db`）。
- Chip 描述层：`mnsim_adapter/`（四层 ChipProfile + provenance 标注 + 两个确定性翻译器）。详见 `docs/simulator/chip_profile_schema.md`。

## mnsim_adapter：结构化的 Chip 描述层（新）

`mnsim_adapter` 把 MNSIM 的 `SimConfig.ini` 从扁平 flat file 抽象成四层 frozen dataclass，每个字段都携带 `Provenance(kind, source, note)`——解决 INI 无法区分 **physical / design / empirical / fitted / proxy / missing** 的问题。

- **入口**：`from mnsim_adapter import load_chip, load_measured_device, available_chips, available_measured_presets`
- **两个翻译器**：
  - `chip.to_mnsim_ini(path)` → 生成带 provenance 注释的 MNSIM-compatible INI；经 `ProcessElement` 验证与 `configs/SimConfig_issc2020_33p2.ini` 逐位一致（3.3914 mm² / 53.79 ns / 74.65 TOPS/W）。
  - `chip.to_pim_sim_overlay()` → 返回 `dse.core.evaluate_config` 的 kwargs（`pim_sim_model`, `ir_drop_model`, `adc_model`, `chip_profile_id`）。
- **消融辅助**：`chip.with_adc(...)`, `chip.with_dac(...)`, `chip.with_variation(...)`, `chip.with_device/with_circuit/with_architecture(...)` 都返回新 dataclass，不改原对象。
- **内置芯片**：`rram_isscc2020_33p2`（ISSCC 2020 Paper 33.2 Liu 等 RRAM macro）+ 20 个 wafer measured preset（由 `pim_sim/device/calibrated_presets.py` 包装）。
- **已接入**：`validate/literature_anchor_baseline.py`、`validate/literature_anchor_ablation.py` 通过 `resolve_config_path(chip_id)` 生成 INI，不再依赖 `configs/SimConfig_*.ini`。

新增实验时的推荐工作流：
1. 在 `mnsim_adapter/registry.py` 里注册新 ChipProfile（literature 或 synthetic），每字段写明 `Provenance`。
2. 用 `chip.validate()` 做跨层一致性检查。
3. 用 `chip.to_mnsim_ini(path)` 或 `chip.to_pim_sim_overlay()` 喂下游。
4. 需要消融时用 `with_*` 构造变体；所有 variant 共享同一个 provenance 链，便于论文 supplement 自动导出。

### 2026-04-21 修复：MNSIM variation 代码路径 + Layer-2 overlay 通用化（A/B/C）

读 MNSIM upstream git log 时发现 `MNSIM/Accuracy_Model/Crossbar_accuracy.py`（2019 uniform-CV 路径）与 `Weight_update.py`（2021 Gaussian 路径）在 upstream 即已互不一致。grep 证明 `Crossbar_accuracy.py` 零引用，是 dead code；`Weight_update.py:41` 才是精度路径上真正活的 Gaussian 注入点。pim_sim 早已 hook 在 `Weight_update.py` 上，所以行为正确。

本轮完成三件事（数值上 bit-identical，仅加文档/工具）：

- **A**：在 `pim_sim/accuracy/weight_inject.py` 顶部注释里写清楚"我们 hook 了哪条、没 hook 哪条、为什么"——包含 upstream commit 哈希证明不是我们 fork 造成的不一致。
- **B**：把 `ChipProfile.device.variation → pim_sim.DeviceModel` 的分派抽成独立纯函数 `pim_sim.device.factory.device_model_from_variation()`，让 `mnsim_adapter/overlay.py` 和外部脚本（fab-data ablation sweep）共享一个翻译入口，并加 6 条单测（`tests/test_variation_factory.py`）。
- **C**：新增 `mnsim_adapter/provenance_check.py`——遍历 Tier-1 / Tier-2 字段、命中 `proxy`/`missing` 就发 `ProvenanceWarning`。`build_overlay()` 和 `ChipProfile.weak_provenance_fields()` 都会调用。Liu 33.2 会吐出 3 条（cell_type、read_latency_ns、variation=MNSIM 默认 1%），Yan 11.7 吐 1 条（SRAM 等效电阻），都是已知的 honest proxies。

Regression：`validate/literature_anchor_{baseline,ablation}.py` 在两个文献锚点上产出的 CSV 与 `/tmp/abc_snapshot/` 完全一致（bit-identical），确认改动纯工具化、无精度路径漂移。

### 2026-04-21 增强：NeuroSim-inspired partial-sum ADC 精度通路

读 NeuroSim 2DInferenceV1.4 源码（`/tmp/neurosim_src/Inference_pytorch/modules/quantization_cpu_np_infer.py:121`、`utee/wage_quantizer.py`）发现 NeuroSim 的精度通路上有一个 MNSIM / pim_sim 此前没有覆盖的非理想性：**每个 weight-slice × input-bit 的 partial-sum 在 shift-add 之前都要过一次 B 比特 ADC 量化**（`LinearQuantizeOut(outputPartial, ADCprecision)`）。MNSIM 2.0 `Accuracy_Model/Weight_update.py` 只做 weight-level Gaussian，低比特 ADC 下精度路径看起来不真实地干净；pim_sim 既有的 `WaldenADCModel` 只接 PPA，不接 accuracy。

本轮把这条通路补上，设计上仍保留 regression-safe 的 opt-in：

- **模型**：`pim_sim/device/model.py` 新增 `PartialSumADCNoiseModel(inner, adc_bits, subarray_rows, g_lrs_siemens, input_activity)`。数学上把 partial-sum 的均匀量化方差 `σ_Y² = (Y_range/L)²/12`（`L=2^B`、`Y_range≈N·a·V_read·G_LRS`）展回每个 cell 的等效 conductance 高斯噪声 `σ_G_adc² ≈ G_LRS² / (12 · L² · N · a)`，叠在 `inner.sample_resistance` 的结果上。`B→∞` 时收敛到 inner 模型（单元测试验证）。
- **Schema**：`mnsim_adapter.circuit.ADCProfile` 新增两个可选字段 `accuracy_bits: Traced[int] | None` 与 `accuracy_input_activity: Traced[float] | None`；默认 `None` → 什么都不包，老文献锚点 CSV 继续 bit-identical。
- **Overlay wiring**：`mnsim_adapter/overlay.py::_build_device_model` 只有在 `accuracy_bits` 显式设置、且 chip 是 analog NVM macro（`device.is_nvm()` + `pim_type==0` + `resistance` 齐全）时才把 base DeviceModel 包进 `PartialSumADCNoiseModel`。SRAM / 数字 PIM / 缺 resistance 一律跳过包装——因为这三种情况下"ADC 读多电平 bitline"的物理前提不成立。
- **测试**：新增 `tests/test_partial_sum_adc.py`（14 条）覆盖参数校验、σ 公式、`B→∞` 极限、opt-out 默认、opt-in 传参、SRAM/NVM 路由。既有 28 条测试全数保持通过。
- **Regression**：4 条 literature-anchor CSV（Liu baseline/ablation + Yan baseline/ablation）与 `/tmp/abc_snapshot/` 继续 bit-identical；因为 Liu/Yan 都没设 `accuracy_bits`，overlay 天然走 opt-out 分支。

使用方式（消融实验待用户决定）：构造带 `accuracy_bits=5` 的 Liu 变体，调 `chip.to_pim_sim_overlay()` 就能拿到一个包了 `PartialSumADCNoiseModel` 的 `pim_sim_model`，直接喂给 `dse.core.evaluate_config` 即可在精度路径上复现 NeuroSim 式的 ADC 量化退化。这条通路定位于"MNSIM vs pim_sim 精度差异放大器"，不影响 PPA ablation（PPA 仍由 `WaldenADCModel` / chip profile 承担）。

### 流片芯片接入（fab chip registration）

见 `docs/simulator/registering_your_fab_chip.md`——把自家流片数据跑进 validation pipeline 的 how-to。输入按证据强度分 4 个 tier：

- Tier-1（必填）：tech_node、cell_type、device_area、xbar 维度、group_num、dac/adc_num、read_voltage、read_latency、pim_type。
- Tier-2（强烈推荐，决定 RRAM 建模质量）：HRS/LRS、**per-state CV**（wafer 级）、SAF rate、ADC preset 或 Walden ENOB/FOM。
- Tier-3（只在 vs-silicon 误差对比时需要）：你自己报的 silicon area / GOPS / TOPS/W。
- Tier-4（默认保留 MNSIM 内建）：CACTI buffer、digital modules、NoC、tile grid。

在 `mnsim_adapter/registry.py` 仿 `_liu_chip()` / `_yan_chip()` 写一份 `_myfab_chip()`，然后：

```bash
python validate/literature_anchor_baseline.py --chip myfab_28nm_2t2r_v1
python validate/literature_anchor_ablation.py --chip myfab_28nm_2t2r_v1
```

ablation 会自动吐出 `mnsim_local_repro` / `pim_sim_chip_profile` / `pim_sim_adc_walden` 三条变体；如果填了 Tier-3 silicon 数据，还会报 `abs_rel_error_vs_silicon_pct`。provenance checker 会在 Tier-1/Tier-2 字段还留着 `proxy` 时发警告——如果你自家数据还能填进去，这条警告就是在提醒你别把 MNSIM 默认当成流片特性。

## Baseline 口径规则（必读）

任何 "MNSIM vs pim_sim" / "MNSIM vs silicon" 对比，先按下表决定 baseline 取哪一列，再写代码。细节推导见 `docs/simulator/mnsim_validation_replication_plan.md` §5。

| 场景 | Baseline 取值 | Rationale |
|---|---|---|
| 文献锚点（例：ISSCC 20-33.2, ISSCC 22-11.7） | **MNSIM 2.0 Table IV 引用值**（cited） | Table IV 原始 SimConfig 未披露，local repro 残差包含上游 `Hardware_Model/Crossbar.py` drift（见 `docs/simulator/mnsim_upstream_diff.md`），不应混入 pim_sim 效应 |
| 代码完整性自检 | **本仓库 local repro 值** | 只用于证明 `MNSIM/` 还能跑出合理量级；不计入 pass/fail |
| measured-in-the-loop（如 `test_data/` wafer preset） | **本仓库 local repro 值**（别无选择） | 论文无 "MNSIM 在这个 preset 上的预设值"，只能用 ③ 自比 |

强制命名惯例（写进 variant_id / 表头 / CSV 列名）：

- `mnsim_table_iv_cited` — 引用 MNSIM 2.0 Table IV 的公开数值（场景 1 baseline）
- `mnsim_local_repro` — 本仓库重新渲染 INI 后 MNSIM 实际输出（场景 2/3 baseline）
- 禁用裸名 `mnsim_baseline`——歧义

positive evidence 标准：

```
|rel_error(pim_sim_*, silicon)| < |rel_error(mnsim_table_iv_cited, silicon)|  # RRAM 文献锚点
|pim_sim_* − mnsim_table_iv_cited| / mnsim_table_iv_cited < 1%                # SRAM null control
```

若任一代码修改让本地 local repro 与历史值 bit-不一致，先查 diff 再决定是 upstream drift、SimConfig 口径，还是真实 regression；Hardware_Model 的改动一律走 fork，不直接覆盖。

## 快速开始（30–90 分钟取样，验证链路）
1) 生成 measured presets（从 test_data 提取）
- `bash artifacts/dse/scripts/run_testdata_analysis.sh`
  - 输出：`artifacts/dse/testdata_runs/run_YYYYMMDD_HHMMSS/` 下的 `measured_presets.csv` 等摘要。

2) 在 measured 场景下跑一小批矩阵点（A/B/C/少量 E 点）
- `python dse/extras/run_measured_matrix.py --measured-presets-csv artifacts/dse/testdata_runs/<run>/measured_presets.csv --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv --preset-name <任选1-2个> --run-accuracy --max-acc-batches 3 --device mps`
  - 输出：`artifacts/dse/matrix_runs/measured_run_YYYYMMDD_HHMMSS/<preset>/...`

3) 在正式空间做小预算算法对比（sanity）
- `bash artifacts/dse/scripts/run_formal_v3_search.sh BUDGET=8 INIT_EVALS=4 WORKERS=2 SEEDS="42" DEVICE=mps`

4) 浏览器查看：
- `PORT=5001 python app/server.py`，打开 `http://localhost:5001`。

## 正式实验清单（论文结果）
下述每条均给出目的、数据、指标、命令与产物位置。建议依序执行；如有 GPU 资源，可并行 1/2、3/4、5/6。

E0. Ground Truth 穷举（RQ1）
- 目的：获得 `rram_formal_v3` 的 36 点真实 Pareto 用作基准。
- 指标：Pareto 大小、(lat, en, area) 最优、可行率（acc≥0.88）。
- 命令：`bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh DEVICE=mps MAX_ACC_BATCHES=4`
- 产物：`artifacts/dse/matrix_runs/exp_formal_v3_exhaustive/`

E1. 算法对比（RQ2，multi vs random）
- 目的：比较 random / nsga2 / mobo 的 HV、收敛曲线、Pareto 质量。
- 设置：预算 18–36，seed=42/43/44。
- 命令：`bash artifacts/dse/scripts/run_formal_v3_search.sh DEVICE=mps BUDGET=18 INIT_EVALS=6 SEEDS="42 43 44" WORKERS=3`
- 产物：`artifacts/dse/search_runs/exp01_formal_v3/`（自动生成对比图与 CSV）。

E2. 设计指导验证（RQ3，`rram_guidance_v4`）
- 目的：在更大空间验证矩阵实验结论的稳定性（xbar、sub_position、ADC/DAC、带宽等）。
- 命令：`bash artifacts/dse/scripts/run_guidance_v4_search.sh DEVICE=mps BUDGET=48 INIT_EVALS=8 SEEDS="42 43 44" WORKERS=3`
- 产物：`artifacts/dse/search_runs/exp02_guidance_v4/`

E3. Measured Presets 提取（RQ4）
- 目的：把 `test_data/` 的真实循环/保持等数据提炼为 `measured_presets.csv`。
- 命令：`bash artifacts/dse/scripts/run_testdata_analysis.sh`
- 产物：`artifacts/dse/testdata_runs/run_*/measured_presets.csv`

E4. Measured 矩阵实验（RQ4-A：可行域/补偿）
- 目的：对每个 measured preset 跑 A/B/C（必要时含 E 的代表点），评估补偿策略（ADC=6、DAC=128、sub_position=0/1）。
- 命令：
  - `python dse/extras/run_measured_matrix.py --measured-presets-csv artifacts/dse/testdata_runs/<run>/measured_presets.csv --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv --run-accuracy --max-acc-batches 4 --device mps`
- 产物：`artifacts/dse/matrix_runs/measured_run_*/<preset>/` 与对比报告。

E5. Measured-in-the-loop 搜索（RQ4-B：鲁棒搜索）
- 目的：在若干代表性 measured preset（如最差/中位/最优三类）下分别运行搜索，随后做“多场景聚合”评估。
- 流程：
  1) 从 E3 的 `measured_presets.csv` 选定 3 个代表 preset。
  2) 为每个 preset 生成 `patched SimConfig.ini`（E4 已内置生成）。
  3) 分别运行：`python dse/run_dse.py --algos nsga2 mobo --seeds 42 43 44 --budget 24 --init-evals 6 --nn vgg8 --weights cifar10_vgg8_params.pth --base-config <preset_config.ini> --run-accuracy --max-acc-batches 4 --device mps --output-root artifacts/dse/search_runs/robust_<preset_name>`
  4) 聚合评价：以“同一设计点在三个 preset 下的最差/均值 PPA 与可行率”排序，计算稳健 HV（min/mean）。
- 产物：`artifacts/dse/search_runs/robust_*/` 与手工聚合报告（脚本化可在 `dse/analyze_results.py` 基础上扩展）。

E6. 关键因子消融（RQ4-C：补偿策略）
- 目的：系统评估 ADC 档位、DAC 数量、sub_position（0/1）对 measured 场景下可行率与 PPA 的影响。
- 方法：固定 xbar=512×512、group_num/pe_num 按论文设置，栅格扫 `ADC={4,6,7}` × `DAC={32,128}` × `sub_position={0,1}`。
- 命令：可用 `matrix_all.csv` 选子集或临时生成一个小型 CSV 后 `run_matrix_csv.py` 运行。
- 推荐路径（adapter 化）：用 `chip = load_chip("rram_isscc2020_33p2")` 做基线，然后 `chip.with_adc(ADCProfile(preset_id=k, …))` 循环生成变体并 `to_mnsim_ini()` 渲染；每个变体的 provenance 链自动保留，便于 supplement 导出。

E7. 跨网络泛化（RQ5）
- 目的：更换 `--nn` 与 `--weights`（LeNet/ResNet18/VGG16），复现 E1/E2 的对比与 E4 的 measured 评估。
- 命令：将 `--weights` 指向 `weights/cifar10_lenet_params.pth`、`weights/cifar10_resnet18_params.pth`、`weights/cifar10_vgg16_params.pth`，其余流程不变。

E8. 采样数据集与替代模型（附加）
- 目的：用 `dse/extras/build_surrogate_dataset.py` 构建 500–2k 样本数据集，探索替代模型回归 PPA 与可行率；分析重要度与交互效应。
- 命令：`python dse/extras/build_surrogate_dataset.py --samples 800 --run-accuracy --device mps --output-dir artifacts/dse/datasets/surrogate_v1`

E9. 复现实验与统计稳健性（附加）
- 目的：多次重复（不同 seed），报告均值±标准差；做 Mann–Whitney U / t-test（脚本外统计）。

## 指标与报告
- 主指标：HV（共享参考点）、Pareto 大小、最优 (lat/en/area)、可行率（acc≥阈值）、wall time。
- 鲁棒指标：稳健 HV（min/mean across presets）、设计点稳健排名、跨 preset 方差。
- 可视化：仓库内置比较图生成；也可用 `app/server.py` 在线浏览 SQL 聚合及图表。

## 你现在还需要补跑的数据（优先级由高到低）
1) E3 + E4：生成 measured presets 并在 1–3 个 preset 上跑矩阵 A/B/C（小批量先验验证）。
2) E0：formal_v3 的 36 点 Ground Truth（若尚未完成）。
3) E1：formal_v3 的算法对比（小预算可先出一版曲线）。
4) E5：在“最差/中位/最优”三类 measured preset 上各跑一次搜索（budget 24）。
5) E6：补偿因子的小型网格扫描（10–20 点即可看到趋势）。
6) E7：换网络的对照实验（先 LeNet/ResNet18 的 1–2 个 preset）。

## 复现与环境
- Python：`.venv` 已就绪；若服务器，设置 `PYTHON_BIN=python DEVICE=cuda` 即可切换。
- 权重/配置：脚本已内置查找顺序（给定路径→`weights/|configs/`→根目录）；根目录存在符号链接，旧命令可直接运行。
- 数据库存取：默认 `app/dse_records.db` 自动创建；.gitignore 已忽略 WAL/SHM。

## 论文结构映射（建议）
- Section 3：Problem Formulation（维度定义与约束，附 matrix A/B/C/E）
- Section 4：Ground Truth & Algorithm Comparison（E0/E1）
- Section 5：Design Guidelines in Wide Space（E2）
- Section 6：Measured-in-the-loop Robust Optimisation（E3/E4/E5/E6）
- Section 7：Cross-NN Generalisation（E7）
- Appendix：Surrogate Dataset & Ablations（E8/E9）

---
如需，我可以把 E5 的“多场景鲁棒聚合”写成脚本，自动读取多个 `robust_*` 目录计算稳健 HV 与排名，并输出 HTML 报告。
