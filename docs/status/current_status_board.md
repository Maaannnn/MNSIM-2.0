# 研究状态：当前状态看板

适合组会快速汇报的 1 页版本

---

## 1. 当前主线

- 毕业论文主线：`MNSIM + DSE + measured preset + robust evaluation`
- 会议子课题候选：
  - `RobustMap-CIM`
  - `StateCalib-MNSIM`
- 当前判断：
  - 先做 measured 与 robust 证据
  - 再决定子课题最终收敛方向
  - `MNSIM` 第三支线拆成两层：
    - 先做 `WS5A` 接口收束
    - 再决定是否做 `WS5B` 建模增强

---

## 2. 当前平台判断

- 主平台：`MNSIM`
- 角色：快速 `accuracy + PPA` 联合评估底座
- 不替代：
  - `NeuroSim`
  - `CrossSim`
- 当前策略：
  - 用 `MNSIM` 跑主线探索
  - 必要时再用高保真工具做局部趋势验证

---

## 3. 当前最重要的 3 个工作流

| 工作流 | 目标 | 当前状态 | 说明 |
|---|---|---|---|
| WS1 | measured preset 提取 | `done` | 已成功生成 `measured_presets.csv` |
| WS2 | measured matrix 首跑 | `done (first-look)` | `strong/weak` 两个 preset 的首批矩阵实验已完成 |
| WS3 | robust ranking 首版 | `done (first-look)` | `strong/weak` 的 within-preset repeat 已完成 |

---

## 4. 已有关键证据

- 文档层：
  - [group_meeting_navigation.md](/Users/bytedance/workspace/MNSIM-2.0/docs/status/group_meeting_navigation.md)
  - [current_research_todo.md](/Users/bytedance/workspace/MNSIM-2.0/docs/status/current_research_todo.md)
  - [MNSIM_group_meeting_report.md](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/MNSIM_group_meeting_report.md)
  - [mnsim_fidelity_gap_review.md](/Users/bytedance/workspace/MNSIM-2.0/docs/simulator/mnsim_fidelity_gap_review.md)
  - [robustmap_cim_positioning.md](/Users/bytedance/workspace/MNSIM-2.0/docs/framework/robustmap_cim_positioning.md)
- 实验层：
  - 已有 nominal `search_runs` 可复用
  - measured preset 提取链路已跑通
  - measured matrix 首批结果正在生成

---

## 5. 最新执行结果

## WS1 measured preset 提取

- 输出目录：
  - `artifacts/dse/testdata_runs/run_20260417_142758/`
- 核心文件：
  - `measured_presets.csv`
  - `summary.json`
  - `retention_phase_summary.csv`
- 当前得到的 3 个主 preset：
  - `meas_cycle_strong`
  - `meas_cycle_typical`
  - `meas_cycle_weak`

## WS2 measured matrix 首跑

- 当前实验目录：
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/`
- 当前选择：
  - preset：`meas_cycle_strong`、`meas_cycle_weak`
  - matrix：`A`
  - points：前 4 个
  - `max_acc_batches=2`
- 结果摘要：
  - `meas_cycle_strong`
    - `pareto_size=2`
    - `best_accuracy=0.9473`
  - `meas_cycle_weak`
    - `pareto_size=2`
    - `best_accuracy=0.9453`

## WS3 robust ranking 首轮

- 当前已完成：
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_strong/robustness/`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/meas_cycle_weak/robustness/`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_observed/`
  - `artifacts/dse/matrix_runs/ws2_firstlook_20260417/cross_scenario_robustness/`
- strong 首轮摘要：
  - candidate 1 (`pe_num=2x2`)
    - `mean_accuracy=0.9375`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
  - candidate 2 (`pe_num=4x4`)
    - `mean_accuracy=0.9375`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
- weak 首轮摘要：
  - candidate 1 (`pe_num=2x2`)
    - `mean_accuracy=0.9375`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
  - candidate 2 (`pe_num=4x4`)
    - `mean_accuracy=0.9375`
    - `worst_accuracy=0.9316`
    - `yield=1.0`
- cross-scenario 观察值聚合：
  - `4x4` 当前排第 1
  - 原因：跨 `strong/weak` 的 `worst_accuracy` 更高
- cross-scenario repeat-summary 聚合：
  - 两个 candidate 暂时打平
  - 说明 within-preset repeat 还不足以单独支撑 ranking 分化

---

## 6. 当前发现

- 现有 `dse` 主线已经足够支持 nominal DSE 和 measured 接入
- 当前最大断点不是平台不存在，而是 measured 与 robust 证据还没完全闭环
- `run_robustness.py` 可以直接复评 measured matrix 结果
  - 但 `--input-root` 需要指向每个 preset 的输出根目录
- `run_robustness.py` 在本仓库里原先有 `sys.path` 小 bug，已修正
- 当前的 robustness 结果是“固定 preset 内多 seed 重复评估”
  - 它已经能提供统计量
  - 但还不能单独替代“跨 measured preset 聚合”的 robust ranking
- 现在已经有两种 cross-scenario 口径：
  - `observed`
  - `repeat-summary`
  - 后续写论文时必须明确区分
- `MNSIM` 第三支线不应一上来就重做建模层
  - 更稳的顺序是先收束输入输出，再决定是否补 `LUT / ADC CALIB / retention / IR-drop`
- `WS5A` 已经进入落地阶段
  - `dse/contracts.py` 已上线
  - `run_dse / run_matrix_csv / run_measured_matrix / run_robustness / app` 已接入 contract v1
- 现有 `search_runs` 应该复用
  - 适合作为 nominal baseline
  - 不需要全部重跑

---

## 7. 当前短板

最关键的不是“没有工具”，而是这 3 个缺口：

1. measured 证据还少
2. robust ranking 已有跨 preset first-look，但候选集还太小
3. `MNSIM` 的输入输出契约已经有 contract v1，但旧 run 仍在逐步 backfill
4. 是否真的需要升级 `MNSIM` 建模层，还要等更大规模 WS2 / WS3 结果来判断

---

## 8. 接下来两步

### 下一步 1

整理 strong/weak 两边的 first-look 结果，抽取：

- nominal vs measured 差异
- 哪些点在 `strong/weak` 下变化明显
- `mean / worst / yield` 是否已经能支撑 robust 说法
- 哪些证据必须进入跨 preset 聚合

### 下一步 2

把 `WS5A` 明确成小范围接口收束任务：

- 统一 manifest
- 统一 scenario 输入口
- 统一结果 schema / seed 口径

当前已完成的 `WS5A` 验证：

- nominal dry-run：
  - [ws5a_dryrun](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws5a_dryrun)
- measured dry-run：
  - [ws5a_measured_dryrun](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws5a_measured_dryrun)
- measured smoke 实跑：
  - [ws5a_measured_smoke_acc](/Users/bytedance/workspace/MNSIM-2.0/artifacts/dse/matrix_runs/ws5a_measured_smoke_acc)

当前已完成的 legacy 回填：

- 关键旧 run 已回填 manifest / scenario / contract_version
- `app` 同步后，`ws2_firstlook_20260417` 的 strong/weak 已能显示 measured scenario 名称

---

## 9. 当前最重要的一句话

现在的重点不是再扩框架，而是先把：

`measured preset -> measured matrix -> robust ranking`

这条证据链跑通，并据此决定会议子课题最终收敛到哪一条。
