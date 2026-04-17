# 研究状态：当前课题 TODO 总表

这份文档是当前课题的执行总表，不是背景介绍，也不是论文草稿。  
它回答 4 件事：

1. 我们现在到底在做哪条主线
2. 已经有哪些前置工作和证据
3. 接下来具体要做哪些任务，顺序是什么
4. 什么情况下继续推进，什么情况下应该收缩范围

说明：

- `dse/` 是本仓库自己的实验外壳，不是上游 `MNSIM` 原生框架。
- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py) 是当前仓库里实验调度与设计点评估的真源，但这不等于上游 `MNSIM` 原生自带这些能力。
- 这份文档优先服务执行，所有“宏大叙事”都必须落到脚本、目录、结果和验收标准上。

---

## 1. 先看结论

## 1.1 当前总目标

当前总目标有两层：

- 硕士毕业论文主线：`MNSIM + DSE + measured preset + robust evaluation`
- 会议子课题：从主线中拆出一个窄而硬的方法题

## 1.2 当前最重要的判断

- 先打通 measured preset 和 robust evaluation，再决定会议子课题最终落到 `RobustMap-CIM` 还是 `StateCalib-MNSIM`
- 先把证据跑出来，再决定是否需要做 `MNSIM` 轻量增强
- 当前主平台仍然是 `MNSIM`，不是 `NeuroSim/CrossSim`

## 1.3 当前推荐顺序

1. 固定研究边界和术语
2. 跑通 measured preset 提取
3. 跑通 measured matrix 小批量实验
4. 做 robust ranking 与重复评估
5. 收敛会议子课题
6. 只有在主结论确实受限时，再做 `MNSIM` 轻量升级

---

## 2. 这份文档怎么用

## 2.1 状态标签

本文档中的任务默认使用以下状态：

- `done`
- `ready`
- `pending`
- `blocked`
- `defer`

## 2.2 更新规则

- 如果某个任务已经跑通，必须补充结果目录或输出文件路径
- 如果某个任务失败，必须补充失败原因，不要直接删掉
- 如果某个判断只是分析结论，不是实验事实，必须明确写成“判断”或“候选方向”

## 2.3 真源文件

执行层面的真源优先级如下：

1. 这份总表
2. [agent.md](/Users/bytedance/workspace/MNSIM-2.0/agent.md)
3. [docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md)
4. 具体脚本与结果目录

---

## 3. 研究主线与子课题关系

## 3.1 硕士毕业论文主线

毕业论文不是单点方法，而是一条完整研究链：

- 以 `MNSIM-2.0` 为评估底座
- 以 `RRAM CIM` 多目标设计空间探索为对象
- 以 `measured-in-the-loop` 为差异化主线
- 以精度约束下的 `PPA` 优化和鲁棒性分析为核心结论

这个主线已经在以下文档中完成收敛：

- [docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md)
- [agent.md](/Users/bytedance/workspace/MNSIM-2.0/agent.md)
- [docs/framework/RRAM_DSE_Problem_Formulation_And_Method.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/RRAM_DSE_Problem_Formulation_And_Method.md)

## 3.2 会议子课题

会议子课题当前有两个候选方向：

- `RobustMap-CIM`
- `StateCalib-MNSIM`

当前判断：

- `RobustMap-CIM` 更像设计自动化 / 搜索方法论文
- `StateCalib-MNSIM` 更像工具增强 / 方法学论文
- 现阶段不建议同时把两条线都做成完整会议计划

## 3.3 当前建议

当前更稳的策略是：

- 毕业论文保留完整主线
- 会议子课题先保留两个候选
- 等 WP1-WP3 形成稳定证据后，再只保留一个主方向

---

## 4. 已有前置工作与证据

这一节只列“已经有的东西”，不把“计划做”误写成“已经完成”。

## 4.1 已有研究定位文档

这些文档已经给出研究判断和边界：

- [docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md)
- [docs/simulator/MNSIM_group_meeting_report.md](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/MNSIM_group_meeting_report.md)
- [docs/simulator/mnsim_fidelity_gap_review.md](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/mnsim_fidelity_gap_review.md)
- [docs/simulator/neurosim_lessons_for_mnsim.md](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/neurosim_lessons_for_mnsim.md)
- [docs/framework/masters_thesis_to_dac_subtopics.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/masters_thesis_to_dac_subtopics.md)
- [docs/framework/robustmap_cim_positioning.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/robustmap_cim_positioning.md)

这些文档已经支持了以下判断：

- 毕业论文主线是什么
- `MNSIM` 在当前课题中扮演什么角色
- `MNSIM` 相对 `NeuroSim/CrossSim` 的优劣势
- 会议子课题更适合收敛成哪类问题
- `MNSIM` 需要补哪些短板

## 4.2 已有代码入口与脚本

下面这些文件已经存在，说明实验链路有入口：

- [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py)
- [dse/run_dse.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_dse.py)
- [dse/run_matrix_csv.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py)
- [dse/extras/extract_measured_presets.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/extract_measured_presets.py)
- [dse/extras/run_measured_matrix.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_measured_matrix.py)
- [dse/extras/run_robustness.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_robustness.py)

注意：

- “脚本存在”不等于“结果已跑通”
- “目录存在”不等于“已经形成可投稿证据”

## 4.3 已有实验资产

下面这些目录已经能支撑实验组织：

- `artifacts/dse/matrices/rram_v2/`
- `artifacts/dse/search_runs/`
- `artifacts/dse/datasets/`
- `artifacts/dse/testdata_analysis/`
- `artifacts/dse/testdata_runs/`

补充说明：

- measured preset 相关输出目录目前至少有两套默认路径
- 如果直接运行不同脚本，必须显式检查 `measured_presets.csv` 的真实位置

---

## 5. 对 MNSIM 的工作性理解

## 5.1 MNSIM 的定位

`MNSIM` 不是逐电路波形级仿真器，而是面向 `RRAM CIM` 的行为级 / 架构级评估框架。

它组合：

- 网络权重
- 测试数据
- 硬件配置
- 器件非理想

输出：

- `accuracy`
- `latency`
- `area`
- `power`
- `energy`

## 5.2 MNSIM 的数据流

以下是对仓库行为的工作性抽象，不是对真实物理过程的完整等价：

1. 读取网络权重与测试集
2. 读取 `SimConfig`
3. 构造硬件感知网络
4. 将浮点权重转成 bit-level 权重表示
5. 按 crossbar / bitwidth / polarity 拆层
6. 注入 `variation`、`SAF` 等非理想
7. 进行近硬件前向，得到 `accuracy`
8. 根据结构与硬件参数估算 `PPA`

## 5.3 MNSIM 的物理抽象边界

它更接近：

- 写好权重后的推理评估

而不是：

- 完整写入过程
- 完整电路级瞬态求解

它当前做得较强的部分：

- 层拆分
- bit-slice 表示
- 近硬件前向
- 系统级 `PPA` 估算

它当前做得较弱的部分：

- program / verify 写入过程
- state-dependent / time-dependent 器件行为
- 输入相关 `IR drop`
- 细粒度 `ADC` 噪声与校准
- 多场景统计鲁棒性评估

---

## 6. 当前短板与升级边界

## 6.1 短板总表

| 短板 | 当前状态 | 对课题的影响 | 候选升级方向 |
|---|---|---|---|
| 物理抽象偏粗 | `variation` / `SAF` 为主 | 鲁棒性解释弱 | state-LUT / drift / retention |
| `IR drop` 过简化 | 输入相关性弱 | 难解释大阵列失稳 | 输入相关 proxy |
| `ADC` 偏静态 | `SCALE/FIX` 为主 | 补偿策略结论偏弱 | `CALIB` / noise LUT |
| 统计评估不足 | 单次结果多 | robust ranking 不可信 | 多 seed / multi-scenario / yield |
| `accuracy` 与 `PPA` 耦合弱 | 两条支路拼接 | 物理叙事不统一 | scenario object |

## 6.2 为什么要升级

如果不升级，至少会出现三类问题：

- 很难支撑 `RobustMap-CIM`
- measured preset 只能停在参数替换，难形成方法贡献
- 与 `NeuroSim` 的对比只能停留在“谁更细”，不能形成真正增量

## 6.3 当前明确不做的升级

当前只做“补短板式”升级，不做以下事情：

- 不做完整电路级重写
- 不做完整替代 `NeuroSim/CrossSim`
- 不把 `MNSIM` 扩成无边界系统工程
- 不把“更复杂”直接当成“更真实”
- 不在没有统计证据前把“鲁棒”写成结论

---

## 7. 总任务板

这一节只给全景，不展开细节。

| 工作流 | 名称 | 当前状态 | 优先级 | 依赖 | 核心产出 |
|---|---|---|---|---|---|
| WS0 | 研究边界与文档基线 | `ready` | P0 | 无 | 统一总表、统一术语 |
| WS1 | measured preset 提取 | `done` | P0 | `test_data/` | `measured_presets.csv` |
| WS2 | nominal / measured matrix 实验 | `done (first-look)` | P0 | WS1 | measured matrix 结果 |
| WS3 | robust ranking 与重复评估 | `in_progress` | P0 | WS2 | `mean/worst/std/yield` |
| WS4 | 会议子课题收敛 | `pending` | P0 | WS1-WS3 | 只保留一个主方向 |
| WS5 | MNSIM 收束与轻量增强 | `in_progress` | P1 | WS3 或 WS4 发现瓶颈 | 接口契约、design doc、必要 patch |
| WS6 | 论文写作与组会资产 | `pending` | P1 | WS1-WS4 | 章节骨架、图表清单 |

---

## 8. 详细工作分解

## WS0 研究边界与文档基线

目标：

- 让后续所有讨论都以同一套术语和同一份总表为准

### T0.1 固定主线表述

- 状态：`done`
- 输入：
  - [docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md)
  - [agent.md](/Users/bytedance/workspace/MNSIM-2.0/agent.md)
- 动作：
  - 统一硕士论文主线表述
  - 统一会议子课题候选表述
- 输出：
  - 这份总表的第 3 节
- 验收：
  - 之后所有文档不再把主线写成不同版本

### T0.2 固定术语边界

- 状态：`done`
- 动作：
  - 明确 `dse/` 不是上游 `MNSIM`
  - 明确 `MNSIM` 的物理抽象边界
- 输出：
  - 第 1 节、第 5 节、第 6 节
- 验收：
  - 后续不再混淆平台能力和本仓库实验外壳

### T0.3 维护这份总表

- 状态：`ready`
- 动作：
  - 每完成一个任务，就回填状态、结果路径和失败记录
- 输出：
  - 持续更新的总表
- 验收：
  - 文档不再只停留在计划层

## WS1 measured preset 提取

目标：

- 从 `test_data/` 提取可审计、可复用、可解释的 measured presets

### T1.1 跑通 preset 提取主脚本

- 状态：`done`
- 脚本：
  - [artifacts/dse/scripts/run_testdata_analysis.sh](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/scripts/run_testdata_analysis.sh)
- 输入：
  - `test_data/`
- 预期输出：
  - `artifacts/dse/testdata_runs/run_*/measured_presets.csv`
- 本轮输出：
  - `artifacts/dse/testdata_runs/run_20260417_142758/`
  - 已生成：
    - `measured_presets.csv`
    - `summary.json`
    - `cycle_state_summary.csv`
    - `retention_phase_summary.csv`
- 命令：

```bash
bash artifacts/dse/scripts/run_testdata_analysis.sh
```

- 如果要固定输出目录：

```bash
OUTPUT_ROOT=artifacts/dse/testdata_runs/run_manual_firstlook \
bash artifacts/dse/scripts/run_testdata_analysis.sh
```

- 验收：
  - 产出目录存在
  - `measured_presets.csv` 字段完整
  - `summary.json` 可读

### T1.2 核对备用脚本路径差异

- 状态：`done`
- 脚本：
  - [dse/extras/extract_measured_presets.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/extract_measured_presets.py)
- 动作：
  - 核对其默认输出目录与 `run_testdata_analysis.sh` 的差异
- 命令：

```bash
.venv/bin/python dse/extras/extract_measured_presets.py \
  --test-data-dir test_data \
  --output-dir artifacts/dse/testdata_analysis/manual_extract
```

- 风险：
  - 后续脚本默认读错 `measured_presets.csv`
- 验收：
  - 在文档中写明真实输入路径
- 当前结论：
  - 这轮实验统一使用：
    - `artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv`

### T1.3 做一次人工 sanity check

- 状态：`done`
- 动作：
  - 检查 `measured_presets.csv` 的行数、字段、来源路径
  - 抽样检查 1 到 2 个 preset 是否有明显异常
- 验收：
  - 能解释每个 preset 大致来自哪类数据统计
- 当前记录：
  - 当前主要 preset：
    - `meas_cycle_strong`
    - `meas_cycle_typical`
    - `meas_cycle_weak`
  - `retention_phase_summary.csv` 已生成，但 retention 相位目前还未进入执行链，只能先作为场景解释证据

### T1.4 固定“当前采用的 preset 集”

- 状态：`done`
- 动作：
  - 不要一上来用全部 preset
  - 先选 1 到 3 个代表 preset
- 验收：
  - 明确列出选择标准
  - 能复述为什么先用这几个
- 当前选择：
  - 先用：
    - `meas_cycle_strong`
    - `meas_cycle_weak`
  - 暂不纳入首轮：
    - `meas_cycle_typical`
  - 选择原因：
    - 先用强弱两端场景观察 design ranking 是否迁移，再决定是否需要把中间场景加回去

## WS2 nominal / measured matrix 实验

目标：

- 在固定设计点集合上先建立 nominal 与 measured 的对照

### T2.1 明确矩阵实验子集

- 状态：`done`
- 输入：
  - `artifacts/dse/matrices/rram_v2/matrix_all.csv`
- 动作：
  - 先选小批量点，而不是全量扫
- 建议：
  - 先保留 A/B/C 类代表点
- 验收：
  - 有一个明确的“小批量首跑名单”
- 当前选择：
  - `matrix_name=A`
  - `max_points=4`
  - 用作 WS2 首轮贯通测试

### T2.2 用 measured preset 跑 1 到 2 个点

- 状态：`done`
- 脚本：
  - [dse/extras/run_measured_matrix.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_measured_matrix.py)
- 目标：
  - 验证 preset 注入链路真的能跑通
- 建议首跑命令：

```bash
.venv/bin/python dse/extras/run_measured_matrix.py \
  --measured-presets-csv artifacts/dse/testdata_runs/<run>/measured_presets.csv \
  --preset-name meas_cycle_strong meas_cycle_weak \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --matrix-name A \
  --max-points 4 \
  --base-config SimConfig.ini \
  --weights cifar10_vgg8_params.pth \
  --nn vgg8 \
  --device mps \
  --dataset-module MNSIM.Interface.cifar10 \
  --space-profile rram_v2 \
  --max-acc-batches 2 \
  --run-accuracy \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --seed 42 \
  --workers 1 \
  --output-root artifacts/dse/matrix_runs/ws2_firstlook
```

- 本轮实际命令：

```bash
.venv/bin/python dse/extras/run_measured_matrix.py \
  --measured-presets-csv artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv \
  --preset-name meas_cycle_strong meas_cycle_weak \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --matrix-name A \
  --max-points 4 \
  --base-config SimConfig.ini \
  --weights cifar10_vgg8_params.pth \
  --nn vgg8 \
  --device mps \
  --dataset-module MNSIM.Interface.cifar10 \
  --space-profile rram_v2 \
  --max-acc-batches 2 \
  --run-accuracy \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --seed 42 \
  --workers 1 \
  --output-root artifacts/dse/matrix_runs/ws2_firstlook_20260417
```

- 本轮输出：
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/matrixcsv_seed42/`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_weak/matrixcsv_seed42/`
- 当前结果摘要：
  - `meas_cycle_strong`
    - `pareto_size=2`
    - `best_accuracy=0.9473`
    - `wall_time_s≈546.2`
  - `meas_cycle_weak`
    - `pareto_size=2`
    - `best_accuracy=0.9453`
    - `wall_time_s≈559.5`
- 验收：
  - 至少 1 个 preset
  - 至少 1 个矩阵点
  - 成功导出结果

### T2.3 扩展到 1 到 3 个 preset × 一小批矩阵点

- 状态：`in_progress`
- 目标：
  - 形成第一版 measured matrix 结果
- 输出：
  - `artifacts/dse/matrix_runs/measured_run_*/`
- 说明：
  - 每个 preset 会形成一个单独子目录，例如
    - `artifacts/dse/matrix_runs/<run>/meas_cycle_strong/`
    - `artifacts/dse/matrix_runs/<run>/meas_cycle_weak/`
- 验收：
  - 至少能比较 nominal 与 measured 的差异

### T2.4 补偿策略的最小对照

- 状态：`pending`
- 目标：
  - 先验证 `ADC / DAC / sub_position` 是否真的影响 measured 场景
- 建议变量：
  - `ADC={4,6,7}`
  - `DAC={32,128}`
  - `sub_position={0,1}`
- 验收：
  - 至少出现一组可解释差异

### T2.5 formal / guidance 空间的主线实验

- 状态：`pending`
- 脚本：
  - [dse/run_matrix_csv.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py)
  - [dse/run_dse.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_dse.py)
- 目标：
  - 保留毕业论文主线需要的 nominal 基线
- 可直接复用：
  - `artifacts/dse/search_runs/exp01_formal_v3/`
  - `artifacts/dse/search_runs/exp02_guidance_v4/`
- 如需本地补跑最小命令：

```bash
.venv/bin/python dse/run_dse.py \
  --algos random nsga2 \
  --seeds 42 \
  --budget 8 \
  --init-evals 4 \
  --nn vgg8 \
  --weights cifar10_vgg8_params.pth \
  --base-config SimConfig.ini \
  --run-accuracy \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --device mps \
  --space-profile rram_formal_v3 \
  --max-acc-batches 2 \
  --output-root artifacts/dse/search_runs/ws2_nominal_min
```

- 验收：
  - 至少有一版 formal 或 guidance 结果可复述

## WS3 robust ranking 与重复评估

目标：

- 让“鲁棒”从口号变成统计输出

### T3.0 回写本轮 DSE 审查结论

- 状态：`done`
- 当前结论：
  - measured matrix 输出目录可以直接进入 robustness 复评
  - `--input-root` 应该指向每个 preset 根目录，而不是 `matrixcsv_seed42/`
  - [dse/extras/run_robustness.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_robustness.py) 原先存在 `sys.path` 设置错误，已在本仓库修正
  - measured preset 目前只把 `Device_Resistance / Device_Variation / Device_SAF` 接进执行路径，`retention` 仍停留在摘要层
  - 现有 `search_runs` 可以作为 nominal baseline 和组会证据，但部分 `result.json` 使用远端绝对路径，未必能直接在本地做 robustness 复评
  - matrix / measured 路径的随机性控制仍弱于 `run_robustness.py`，后续如需更严格复现性，应考虑显式 per-point seed
- 影响：
  - WS3 现在可以直接执行
  - WS5 是否需要升级，仍要等 WS3 结果再判断

### T3.1 固定 robust 指标

- 状态：`ready`
- 指标：
  - `accuracy_mean`
  - `accuracy_worst`
  - `accuracy_std`
  - `yield / feasibility_rate`
- 验收：
  - 后续所有 robust 讨论都使用同一套指标

### T3.2 跑 1 组重复评估

- 状态：`done (strong/weak first-look)`
- 脚本：
  - [dse/extras/run_robustness.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_robustness.py)
- 输入：
  - 来自 WS2 的 measured 结果
- 命令：

```bash
.venv/bin/python dse/extras/run_robustness.py \
  --input-root artifacts/dse/matrix_runs/<run>/<preset_name> \
  --source pareto \
  --sort-by energy_nj \
  --topk 2 \
  --repeats 3 \
  --seed-base 1000 \
  --accuracy-target 0.88
```

- 本轮已执行命令：

```bash
.venv/bin/python dse/extras/run_robustness.py \
  --input-root artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong \
  --source pareto \
  --sort-by energy_nj \
  --topk 2 \
  --repeats 3 \
  --seed-base 1000 \
  --accuracy-target 0.88
```

- 关键说明：
  - `--input-root` 不是指向 `matrixcsv_seed42/`，而是指向 preset 根目录
  - 例如：
    - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong`
  - 因为 `run_robustness.py` 会在该目录下自动寻找 `matrixcsv_seed42/result.json + history.csv`
- 输出：
  - `per_repeat.csv`
  - `summary.csv`
- 当前已产出：
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/robustness/summary.csv`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/robustness/per_repeat.csv`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_weak/robustness/summary.csv`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_weak/robustness/per_repeat.csv`
- 当前 strong 首轮结果：
  - candidate 1
    - `pe_num=2x2`
    - `mean_accuracy=0.9375`
    - `std_accuracy≈0.0048`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
  - candidate 2
    - `pe_num=4x4`
    - `mean_accuracy=0.9375`
    - `std_accuracy≈0.0048`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
- 当前 weak 首轮结果：
  - candidate 1
    - `pe_num=2x2`
    - `mean_accuracy=0.9375`
    - `std_accuracy≈0.0048`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
  - candidate 2
    - `pe_num=4x4`
    - `mean_accuracy=0.9375`
    - `std_accuracy≈0.0048`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
- 当前解释：
  - 这版 robustness 已经能稳定输出 `mean / std / worst / yield`
  - 但它目前只是在“固定 measured preset 内，换 noise seed 重复评估”
  - 对这两组 candidate 来说，within-preset robustness 暂时没有拉开差异
- 验收：
  - 至少能看到 `mean/worst/yield`

### T3.3 做 nominal ranking vs robust ranking 对比

- 状态：`in_progress`
- 目标：
  - 证明或反证 design migration
- 当前线索：
  - 在 WS2 的 measured matrix 首轮里：
    - `meas_cycle_strong` 的最高精度点是 `pe_num=2x2`
    - `meas_cycle_weak` 的最高精度点是 `pe_num=4x4`
  - 这说明 measured 场景之间已经出现 ranking 翻转苗头，值得继续做 robust 对比
  - 在 WS3 的 within-preset repeat 里：
    - `strong/weak` 两边的两个 candidate 都得到相同的 `mean/worst/yield`
  - 这说明“多 seed 重复评估”本身还不足以替代“跨 measured preset 聚合”的 robust ranking
- 当前新增工具：
  - [dse/extras/run_cross_scenario_robustness.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/run_cross_scenario_robustness.py)
- 推荐命令 1：
  - 直接按 measured preset 观测结果做跨场景聚合

```bash
.venv/bin/python dse/extras/run_cross_scenario_robustness.py \
  --scenario-root artifacts/dse/matrix_runs/ws2_firstlook_20260417 \
  --preset-name meas_cycle_strong meas_cycle_weak \
  --source pareto \
  --topk 2 \
  --accuracy-target 0.88 \
  --output-dir artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_observed
```

- 推荐命令 2：
  - 先利用每个 preset 内的 repeat summary，再做跨场景聚合

```bash
.venv/bin/python dse/extras/run_cross_scenario_robustness.py \
  --scenario-root artifacts/dse/matrix_runs/ws2_firstlook_20260417 \
  --preset-name meas_cycle_strong meas_cycle_weak \
  --use-robustness-summary \
  --topk 2 \
  --accuracy-target 0.88
```

- 当前已产出：
  - 观测值聚合：
    - [cross_scenario_observed/summary.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_observed/summary.csv)
  - repeat-summary 聚合：
    - [cross_scenario_robustness/summary.csv](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_robustness/summary.csv)
- 当前解释：
  - `cross_scenario_observed`
    - `pe_num=4x4` 排名第 1
    - 原因是跨 `strong/weak` 的 `worst_accuracy` 更高
  - `cross_scenario_robustness`
    - 两个 candidate 的 `mean/worst/yield` 完全一致
    - 说明当前 within-preset repeat 还没有拉开差异
- 验收：
  - 至少有一张可讲的对比图
- 注意：
  - 如果两者完全一致，也必须如实记录

### T3.4 判断 robust 证据是否足够

- 状态：`pending`
- 动作：
  - 判断是否已经足以支撑 `RobustMap-CIM`
- 验收：
  - 给出“继续 / 暂停 / 收缩范围”的明确结论

## WS4 会议子课题收敛

目标：

- 不再同时模糊保留两个方向，而是收敛出一个主题

### T4.1 比较两个候选方向

- 状态：`ready`
- 候选：
  - `RobustMap-CIM`
  - `StateCalib-MNSIM`
- 比较维度：
  - 当前证据是否足够
  - 还需要新增多少工作
  - 更像方法论文还是平台增强论文
- 参考：
  - [docs/framework/masters_thesis_to_dac_subtopics.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/masters_thesis_to_dac_subtopics.md)
  - [docs/framework/robustmap_cim_positioning.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/robustmap_cim_positioning.md)

### T4.2 固定一个主方向

- 状态：`pending`
- 验收：
  - 能用一句话讲清楚问题定义
  - 能列出 2 到 4 个 baseline
  - 能列出最关键的 2 到 3 张图

### T4.3 写出最小论文包

- 状态：`pending`
- 内容：
  - 标题候选
  - problem statement
  - contributions
  - baselines
  - experiment list
- 验收：
  - 不再是“想法”，而是“可投稿骨架”

## WS5 MNSIM 收束与轻量增强

目标：

- 先收束实验接口和输入输出，再决定是否做建模增强

### WS5A 实验接口与输入输出收束

原则：

- 这部分现在就可以做
- 目标是降低后续重跑、迁移和复评成本
- 不主动改变物理结论，只整理实验契约

### T5A.1 固定统一 experiment manifest

- 状态：`done (v1)`
- 目标：
  - 不再让关键输入分散在命令参数、`SimConfig.ini`、preset patch 和结果目录命名里
- 建议记录字段：
  - `base_config_path`
  - `weights_path`
  - `dataset_module`
  - `nn`
  - `preset_name`
  - `seed / noise_seed`
  - `max_acc_batches`
  - `enable_saf / variation / rratio`
  - `matrix_csv / batch info`
- 验收：
  - 同一个实验能仅靠 manifest 复述和复跑
- 已实现：
  - 新增公共模块：
    - [dse/contracts.py](/Users/bytedance/workspace/MNSIM-2.0/dse/contracts.py)
  - 当前会落盘：
    - 每个 `run_dse` trial 的 `experiment_manifest.json`
    - 每个 `run_matrix_csv` trial 的 `experiment_manifest.json`
    - 每个 `run_robustness` 输出目录的 `experiment_manifest.json`
    - 每个 measured matrix 根目录的 `experiment_manifest.json`

### T5A.2 收束 measured scenario 的输入口

- 状态：`done (v1)`
- 当前问题：
  - measured preset 现在主要通过 patch `Device_Resistance / Device_Variation / Device_SAF` 进入执行链
  - `retention` 只存在于摘要里，没有统一场景对象
- 目标：
  - 形成统一的 scenario 描述，而不是临时字符串 patch
- 验收：
  - 能清楚回答“这个实验到底用了哪个 measured 场景”
- 已实现：
  - measured preset 会先写成独立 scenario 文件，再传给下游：
    - `artifacts/dse/matrix_runs/<run>/scenarios/<preset>.json`
  - 示例：
    - [meas_cycle_strong.json](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws5a_measured_dryrun/scenarios/meas_cycle_strong.json)
  - `run_matrix_csv.py` 新增：
    - `--scenario-json`
  - `result.json` 的 `run_config` 现在包含：
    - `contract_version`
    - `scenario`

### T5A.3 统一结果 schema 与路径解析

- 状态：`done (v1)`
- 当前问题：
  - `result.json / history.csv / pareto.csv / summary.csv / meta.json` 的口径分散
  - 部分旧 `search_runs` 结果仍绑定远端绝对路径
- 目标：
  - 让 nominal / matrix / robustness 结果都更容易串联和本地复评
- 验收：
  - 旧结果至少能更稳定地当 baseline 被读取
- 已实现：
  - [dse/run_dse.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_dse.py) 的 `load_results_from_dir()` 现在会：
    - 读取 `contract_version / scenario`
    - 对 `weights_path / base_config_path` 做本地 fallback 解析
    - 在 `result.json` 缺字段时，回退读取 `experiment_manifest.json`
  - [dse/output.py](/Users/bytedance/workspace/MNSIM-2.0/dse/output.py) 的 `result.json` schema 已扩展
  - [app/server.py](/Users/bytedance/workspace/MNSIM-2.0/app/server.py) 会把新 contract 合并进 `run_config_json`

### T5A.4 固定显式 seed 与复现实验口径

- 状态：`done (v1)`
- 当前问题：
  - `run_robustness.py` 明确控制 `noise_seed`
  - `run_matrix_csv.py` / measured matrix 路径对 per-point 噪声种子的暴露还不够一致
- 目标：
  - 让 matrix 与 robustness 的统计口径更一致
- 验收：
  - 重复运行同一实验时，随机性来源是可解释的
- 已实现：
  - [dse/core.py](/Users/bytedance/workspace/MNSIM-2.0/dse/core.py) 的 `evaluate_config()` 新增 `noise_seed`
  - [dse/run_matrix_csv.py](/Users/bytedance/workspace/MNSIM-2.0/dse/run_matrix_csv.py) 新增：
    - `--noise-seed-base`
  - 当前约定：
    - per-point noise seed = `noise_seed_base + source_index - 1`
  - `run_robustness.py` 也会把 `noise_seed` 显式传给 `evaluate_config()`

### T5A.5 先做小范围接口收束，再继续扩实验

- 状态：`in_progress`
- 建议顺序：
  - 先 manifest / schema / seed
  - 再决定是否需要动更深的建模层
- 验收：
  - 之后新增实验不再继续扩散脚本分叉
- 当前进展：
  - `dse` 主链已接入 contract v1
  - `app` 前后端已能读取并展示：
    - `contract_version`
    - `scenario_name`
    - `scenario_kind`
    - `experiment_manifest`
  - smoke 验证 run：
    - [ws5a_measured_smoke_acc](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws5a_measured_smoke_acc)

### T5A.6 回填旧 run 到新 contract

- 状态：`done (key runs first batch)`
- 新工具：
  - [dse/extras/backfill_experiment_contracts.py](/Users/bytedance/workspace/MNSIM-2.0/dse/extras/backfill_experiment_contracts.py)
- 推荐命令：

```bash
.venv/bin/python dse/extras/backfill_experiment_contracts.py \
  --root \
    artifacts/dse/search_runs/exp01_formal_v3 \
    artifacts/dse/search_runs/exp02_guidance_v4 \
    artifacts/dse/search_runs/rram_formal_v3_gpu1 \
    artifacts/dse/search_runs/rram_guidance_v4_gpu0 \
    artifacts/dse/matrix_runs/ws2_firstlook_20260417 \
    artifacts/dse/matrix_runs/measured_run_20260412_141919 \
  --measured-presets-csv artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv \
  --patch-result-json
```

- 当前结果：
  - 已回填：
    - `23` 个关键 trial manifest
    - `23` 个 `result.json`
  - 已执行 `app` 刷新：
    - `23` 个已有 run metadata refreshed
  - 现在 `app` 能正确展示：
    - `ws2_firstlook_20260417/meas_cycle_strong`
    - `ws2_firstlook_20260417/meas_cycle_weak`
    的 `scenario_name / contract_version`

### WS5B 物理建模轻量增强

原则：

- 这部分不抢在 WS2 / WS3 前面拍板
- 只有主结论明显被粗模型卡住时，才进入实现

### T5B.1 判断是否真的需要升级

- 状态：`pending`
- 输入：
  - WS2、WS3 的结果
- 问题：
  - 当前结论是否已经被 `variation/SAF` 粗模型限制住
  - 当前 `ADC` 模型是否真的影响了主结论解释
- 验收：
  - 给出“需要 / 暂不需要”的判断

### T5B.2 设计第一优先级增强项

- 状态：`pending`
- 只允许从以下候选里选 1 到 2 个：
  - `device_states.csv`
  - `ADC CALIB`
  - 输入相关 `IR drop` proxy
  - `drift / retention` preset 字段
- 验收：
  - 每个增强都能对应一个明确物理缺口

### T5B.3 写实现前设计说明

- 状态：`pending`
- 内容：
  - 改哪些文件
  - 为什么改
  - 对速度的影响
  - 如何验证
- 验收：
  - 先有 design doc，再开始改代码

### T5B.4 实现后做最小验证

- 状态：`pending`
- 验收：
  - nominal 路径不能被破坏
  - 至少一个场景的解释能力变强
  - 速度开销在可接受范围内

## WS6 论文写作与组会资产

目标：

- 把实验结果转成论文结构和汇报资产

### T6.1 固定章节映射

- 状态：`ready`
- 输入：
  - [agent.md](/Users/bytedance/workspace/MNSIM-2.0/agent.md)
  - [docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/SCIENTIFIC_CODEX_FRAMEWORK.md)
- 输出：
  - 论文章节骨架

### T6.2 固定图表清单

- 状态：`pending`
- 建议至少包含：
  - nominal vs measured 对比图
  - nominal ranking vs robust ranking
  - 补偿变量消融
  - MNSIM 抽象边界图
- 验收：
  - 每张图都有明确来源和用途

### T6.3 形成讲稿底稿

- 状态：`pending`
- 目标：
  - 组会、开题、论文写作用同一套素材
- 验收：
  - 结果不再只存在于命令和目录里

---

## 9. 两周执行清单

这一节只放最近两周的动作，不放长期愿景。

## 第 1 周

- `done/ready`
  - 固定这份总表
  - 跑通 measured preset 提取
  - 跑完 measured matrix 首轮 strong/weak 两组结果
- `next`
  - 跑完 `meas_cycle_strong` 的 robustness 首轮重复评估
  - 抽取 strong/weak 的 measured matrix 对照摘要

## 第 2 周

- 决定是否补 `meas_cycle_weak` 的 robustness 首轮
- 形成第一版 nominal vs measured / robust 对照表
- 产出第一版：
  - nominal vs measured 差异
  - `mean/worst/yield`
  - 会议子课题倾向判断

---

## 10. 当前立即可执行的 6 件事

1. 运行 `run_testdata_analysis.sh`，生成最新 `measured_presets.csv`
2. 明确 `measured_presets.csv` 的真实输出目录
3. 从中选 1 到 2 个代表 preset
4. 用 `run_measured_matrix.py` 跑一个小批量 matrix 子集
5. 用 `run_robustness.py` 对其中一组结果做重复评估
6. 根据结果决定会议子课题先收敛到哪一条

对应最小命令链：

```bash
# WS1
bash artifacts/dse/scripts/run_testdata_analysis.sh

# WS2
.venv/bin/python dse/extras/run_measured_matrix.py \
  --measured-presets-csv artifacts/dse/testdata_runs/run_20260417_142758/measured_presets.csv \
  --preset-name meas_cycle_strong meas_cycle_weak \
  --matrix-csv artifacts/dse/matrices/rram_v2/matrix_all.csv \
  --matrix-name A \
  --max-points 4 \
  --base-config SimConfig.ini \
  --weights cifar10_vgg8_params.pth \
  --nn vgg8 \
  --device mps \
  --dataset-module MNSIM.Interface.cifar10 \
  --space-profile rram_v2 \
  --max-acc-batches 2 \
  --run-accuracy \
  --accuracy-target 0.88 \
  --enable-saf \
  --enable-variation \
  --seed 42 \
  --workers 1 \
  --output-root artifacts/dse/matrix_runs/ws2_firstlook_20260417

# WS3
.venv/bin/python dse/extras/run_robustness.py \
  --input-root artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong \
  --source pareto \
  --sort-by energy_nj \
  --topk 2 \
  --repeats 3 \
  --seed-base 1000 \
  --accuracy-target 0.88
```

---

## 11. 风险、停止条件与不做事项

## 11.1 主要风险

### 风险 A：范围膨胀

表现：

- 同时做主论文、子课题、框架升级、高保真对照

控制：

- 先 WS1-WS3，再决定 WS4 和 WS5

### 风险 B：MNSIM 升级变成无边界工程

表现：

- 一上来就追求“像 NeuroSim 一样全面”

控制：

- 先做 WS5A，再决定是否做 WS5B

### 风险 C：measured preset 退化成参数替换

表现：

- 只改 `variation / SAF`，没有统计解释

控制：

- 必须同时给来源、摘要和 ranking 变化

### 风险 D：强行制造 robust claim

表现：

- 只有单次结果，也写“鲁棒”

控制：

- 没有 `mean/worst/yield`，就不能用 robust 结论

## 11.2 停止条件

### 对 WS1

- 如果 `measured_presets.csv` 不能稳定生成，先停在数据筛选，不进入论文结论

### 对 WS2

- 如果 preset 连注入 `SimConfig` 都跑不通，先查兼容性，不直接解释成器件退化

### 对 WS3

- 如果 nominal ranking 和 robust ranking 完全一致，也必须如实报告，不强行制造迁移故事

### 对 WS5

- 如果 WS5A 尚未收束，就不要直接跳进 WS5B
- 如果升级后只是“更复杂”，但不能提高解释能力，就不要把它升级成主贡献

## 11.3 当前明确不做的事

- 不同时推进两条完整会议线
- 不把 `dse/` 误写成上游 `MNSIM` 原生模块
- 不把 `MNSIM` 的轻量升级写成完整替代 `NeuroSim/CrossSim`
- 不把单次结果包装成 robust claim
- 不在没有证据前默认“大阵列最优点迁移”一定存在

---

## 12. 验收标准速查表

| 工作流 | 最低验收标准 |
|---|---|
| WS1 | 生成可审计的 `measured_presets.csv` |
| WS2 | 至少 1 个 preset × 1 个矩阵点跑通 |
| WS3 | 至少拿到 `mean/worst/yield` 中两项，优先完整报告 |
| WS4 | 能用一句话讲清楚子课题问题定义 |
| WS5 | 升级后 nominal 路径仍可用，且解释能力变强 |
| WS6 | 有章节骨架和至少 3 到 4 张明确用途的图 |

---

## 13. 当前文件需要持续回填的内容

后续每次推进，优先回填以下信息：

- 任务状态
- 真实结果目录
- 失败记录
- 是否继续推进
- 是否影响会议子课题选择

如果这些内容没有回填，这份总表就会重新退化成“计划清单”，而不是“执行总表”。
