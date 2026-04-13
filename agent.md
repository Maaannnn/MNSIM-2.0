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
