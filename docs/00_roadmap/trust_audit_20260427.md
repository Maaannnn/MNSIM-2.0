# Trust Audit 报告 — 2026-04-27

## 目的

在基于 `artifacts/dse/` 历史数据写论文前做的可信度审计。结论：**历史数据
不可用**，任何 storyline 必须基于干净重跑。本文档存档教训，避免再踩。

## 关键事实清单

| 项 | 事实 | 出处 |
|---|---|---|
| `MNSIM/` 是上游 fork | 可信，是别人发表过的代码 | 用户确认 |
| `pim_sim/`、`dse/` 是用户新写的增强层 | 中等可信，未全审 | 用户确认 |
| `artifacts/dse/search_runs/archive/exp00_preliminary/` 是早期试跑 | 全部 NaN，run_accuracy=False | data audit |
| `dse/core.py:SPACE_PROFILES` 当前定义 | formal_v3/guidance_v4 都不含 P0 | 代码 |
| 但历史 `random_*` runs 在 formal_v3/guidance_v4 路径下选过 P0 30 次 | 说明 SPACE 跑实验后被改过 | data audit |
| `evaluate_config` 没 try/except | NaN 不来自 wrapper silent failure | 代码审计 |
| 算法层 (`nsga2.py`, `mobo.py` etc) 调用 evaluate_config 也未 swallow exception | 同上 | 代码审计 |

## 三次错误的 storyline

| Storyline | 我的 claim | 真相 |
|---|---|---|
| 1. Multi-task BO over 15 wafers | 跨 wafer transfer learning 加速搜索 | 健康 wafer LRS_CV 都挤在 1.4-4.2%，没有足够多样性 |
| 2. CVaR / robust DSE | 多 preset 鲁棒搜索 | 同上，preset 间差异不显著 |
| 3. Failure mode taxonomy + F1=1.0 classifier | 17.3% silent crash, deterministic 可预测 | 196 个 NaN 全来自 archive runs (run_accuracy=False)，不是 crash |

附加错误：
- "MOBO 永远不选 P0 (p<10⁻⁴)" — 因为 P0 不在 MOBO 跑的 SPACE 里
- "(xbar=256/512) × (ADC=8) 100% crash" — ADC=8 只出现在 archive 里，且那 batch 跑时 run_accuracy=False
- 那个 "F1=1.0 crash classifier" 实际学的是 "is_archive ?"

## 数据可信度最终判定

| 数据来源 | 状态 | 用途 |
|---|---|---|
| `artifacts/dse/search_runs/archive/` | **完全弃用** | 不读 |
| `artifacts/dse/search_runs/{formal,guidance}_v4_*/` | **横评不可用** | 之前的 SPACE ≠ 现在的 SPACE |
| `artifacts/dse/datasets/*` | **不可用** | 派生于上面 |
| `artifacts/dse/matrices/rram_v2/*` | 仅作 SPACE 设计参考 | 不作为 ground truth |
| `pim_sim/device/calibrated_presets.py` 里 wafer 数据 | **可信** | 直接来自 wafer 实测 |
| `MNSIM/` | **可信** | 上游 fork |

## 教训（karpathy 视角）

1. **K-1 (假设外显)**：默认"实验已跑过 = 实验正确"是错的。下次必须先问数据来源。
2. **K-2 (简单优先)**：不要一上来就用 active learning / multi-task BO 这些花哨方法。先用 random sample + 看一眼数据。
3. **K-4 (可验证目标)**：跑统计检验前必须确认对比组是 apples-to-apples。p<10⁻⁴ 漂亮但毫无意义。

## 重跑前必须满足的不变量

未来任何 DSE 实验数据要可发表，必须满足：

1. **SPACE 冻结**：runtime 写入 manifest，且 `evaluate_config` 拒跑不合 SPACE 的配置。
2. **run_accuracy 必须为 True**（除非论文 claim 不依赖 accuracy）。
3. **每个 trial 写入 commit hash + SPACE hash + seed**，可追溯到具体代码版本。
4. **算法横评必须用同一个 SPACE 同一个 budget 同一个 seed 列表**。
5. **archive/preliminary/exp00 类目录默认排除**，需明确审视后才能纳入。

## 下一步

A 路线（清重跑）已被确认。详见 `00_roadmap/clean_rerun_plan_20260427.md`（待写）。
