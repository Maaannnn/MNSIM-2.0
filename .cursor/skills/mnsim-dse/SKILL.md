---
name: mnsim-dse
description: Run and compare MNSIM DSE workflows with BO+GP, NSGA-II+Surrogate, and MOBO (ParEGO). Use when the user asks for design space exploration, Bayesian optimization, Pareto front search, script usage, parameter explanations, or result comparison in this repository.
---
# MNSIM DSE Workflows

## 唯一推荐入口

| 用途 | 命令 |
|------|------|
| 并行多算法 / 多 seed / 汇总对比 | `python dse/run_dse.py`（见 `--help`） |
| 一键三算法 + 出图（默认参数） | `bash dse/run_benchmark.sh` |
| 仅根据已有结果出对比图 | `python dse/run_dse.py --plot-only --output-root <run目录>` |

实现代码：`dse/algorithms/{bo_gp,nsga2,mobo}.py`，设计空间与仿真：`dse/core.py`，输出：`dse/output.py`。

## 常用示例

```bash
# 三算法 × 多 seed，并行 worker，并生成 comparison/ 与 plots
.venv/bin/python dse/run_dse.py \
  --algos bo_gp nsga2 mobo \
  --seeds 42 43 44 \
  --budget 24 --init-evals 6 \
  --nn vgg8 \
  --weights "$(pwd)/cifar10_vgg8_params.pth" \
  --base-config "$(pwd)/SimConfig.ini" \
  --output-root dse_runs/my_run \
  --workers 4 \
  --plots
```

精度评估（很慢）时在上述命令中加 `--run-accuracy`；BO 两阶段再加 `--two-stage --topk-accuracy 3` 等（见 reference.md）。

## 输出

默认不传 `--output-root` 时，每次运行会新建 **`<仓库根>/dse_runs/run_YYYYMMDD_HHMMSS/`**，避免覆盖旧结果与图。  
每个试验目录 `<algo>_seed<N>/`：英文 `history.csv`、`pareto.csv`、`result.json`，以及中文表头/键名的 `history_zh.csv`、`pareto_zh.csv`、`result_zh.json`。  
汇总：`comparison/` 下同样有英文与 `*_zh` 的 csv/json、`report.txt` / `report_zh.txt`。  
若加 `--plots`：`comparison/plots/` 中每个图有英文版与 `*_zh.png` 中文版。

## 注意

- `bo_gp` 为单目标 track；`nsga2`/`mobo` 为多目标 track，Hypervolume 仅对后者可比。
- 完整参数表：[`reference.md`](reference.md)
