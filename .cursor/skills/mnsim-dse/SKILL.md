---
name: mnsim-dse
description: Run and compare MNSIM DSE workflows with BO+GP, NSGA-II+Surrogate, and MOBO (ParEGO). Use when the user asks for design space exploration, Bayesian optimization, Pareto front search, script usage, parameter explanations, or result comparison in this repository.
---
# MNSIM DSE Workflows

## 适用场景

- 用户提到 DSE、设计空间搜索、参数寻优
- 用户提到 BO/GP、NSGA-II、MOBO、Pareto front
- 用户想知道脚本命令、参数含义、结果文件怎么看
- 用户想对比三种算法结果

## 脚本入口

- `dse_bo_gp.py`：单目标 BO+GP（支持两阶段精度复评）
- `dse_nsga2_surrogate.py`：NSGA-II + Surrogate（随机森林代理）
- `dse_mobo_parego.py`：MOBO（ParEGO）
- `compare_dse_results.py`：三方案结果汇总对比
- `run_fair_moo_benchmark.sh`：公平对比一键脚本（并行运行三方法 + 多seed汇总）
- `dse_multi_utils.py`：公共设计空间与评估函数（不要直接作为入口运行）

## 标准执行流程

1. 先确认环境与权重路径有效（建议使用项目 `.venv`）
2. 先跑小规模 smoke（2~5 次评估）验证命令和输出目录
3. 再跑正式实验（建议三算法预算接近，便于公平比较）
4. 最后运行对比脚本汇总结果

## 推荐命令模板

### 0) 一键公平对比（推荐）

```bash
bash run_fair_moo_benchmark.sh \
  --nn vgg8 \
  --weights "/Users/bytedance/workspace/MNSIM-2.0/cifar10_vgg8_params.pth" \
  --repeats 3 \
  --budget 24
```

若要统一精度口径（非常慢）：

```bash
bash run_fair_moo_benchmark.sh \
  --nn vgg8 \
  --weights "/Users/bytedance/workspace/MNSIM-2.0/cifar10_vgg8_params.pth" \
  --repeats 2 \
  --budget 12 \
  --run-accuracy \
  --bo-topk-accuracy 3 \
  --accuracy-target 0.90 \
  --accuracy-penalty 120
```

### 1) BO+GP（两阶段，推荐）

```bash
"/Users/bytedance/workspace/MNSIM-2.0/.venv/bin/python" dse_bo_gp.py \
  --iterations 12 \
  --init-random 4 \
  --nn vgg8 \
  --weights "/Users/bytedance/workspace/MNSIM-2.0/cifar10_vgg8_params.pth" \
  --run-accuracy \
  --two-stage \
  --topk-accuracy 3 \
  --accuracy-target 0.90 \
  --accuracy-penalty 120 \
  --output-dir dse_bo_results_vgg8_acc_2stage
```

### 2) NSGA-II + Surrogate

```bash
"/Users/bytedance/workspace/MNSIM-2.0/.venv/bin/python" dse_nsga2_surrogate.py \
  --generations 10 \
  --population 20 \
  --init-evals 20 \
  --evals-per-gen 4 \
  --nn vgg8 \
  --weights "/Users/bytedance/workspace/MNSIM-2.0/cifar10_vgg8_params.pth" \
  --output-dir dse_nsga2_results
```

### 3) MOBO（ParEGO）

```bash
"/Users/bytedance/workspace/MNSIM-2.0/.venv/bin/python" dse_mobo_parego.py \
  --iterations 20 \
  --init-random 6 \
  --nn vgg8 \
  --weights "/Users/bytedance/workspace/MNSIM-2.0/cifar10_vgg8_params.pth" \
  --output-dir dse_mobo_results
```

### 4) 结果对比

```bash
"/Users/bytedance/workspace/MNSIM-2.0/.venv/bin/python" compare_dse_results.py \
  --bo-dir dse_bo_results_vgg8_acc_2stage \
  --nsga2-dir dse_nsga2_results \
  --mobo-dir dse_mobo_results \
  --output-dir dse_compare_results_vgg8
```

## 输出文件约定

- BO：`bo_history.csv`、`best_result.json`、（两阶段）`stage2_rerank.csv`
- NSGA-II：`nsga2_history.csv`、`pareto_front.csv`、`summary.json`
- MOBO：`mobo_history.csv`、`pareto_front.csv`、`summary.json`
- Compare：`compare_summary.csv`、`compare_summary.json`
- Fair Benchmark：`dse_fair_benchmark/run_*/seed_*/...` + `global_summary.csv/json`

## 常见问题处理

- 运行很慢：优先关闭 `--run-accuracy` 或使用 BO 两阶段
- 看起来“卡住”：CPU 下 accuracy 评估很慢，先看是否在跑首个候选
- 配置不合法：`Xbar_Size` 必须满足 `xbar_row % Subarray_Size == 0`
- 路径错误：优先用绝对路径传 `--weights` 和输出目录
- 公平性要求：比较算法时保持 `budget`、`seed`、`非理想性开关` 一致

## 参数细节

完整参数表与逐项解释见：[`reference.md`](reference.md)
