# 参数参考（mnsim-dse）

## 1) `dse_bo_gp.py`

### 核心参数

- `--base-config`：基础 `SimConfig.ini` 路径（默认仓库根目录）
- `--weights`：模型权重文件路径
- `--nn`：网络名（默认 `vgg8`）
- `--iterations`：总评估轮数（BO预算）
- `--init-random`：随机初始化轮数
- `--seed`：随机种子
- `--device`：运行设备（默认 `cpu`）

### 精度相关

- `--run-accuracy`：启用精度评估（最耗时）
- `--enable-saf`：启用 SAF 注入（默认 True）
- `--enable-variation`：启用器件变异
- `--enable-rratio`：启用 R-ratio 影响开关
- `--fixed-qrange`：固定量化范围（否则动态 SCALE）
- `--accuracy-target`：目标精度阈值（需配合 `--run-accuracy`）
- `--accuracy-penalty`：低于目标精度时的惩罚系数

### 两阶段 BO

- `--two-stage`：先硬件 BO，再 Top-K 做 accuracy
- `--topk-accuracy`：阶段2复评候选个数

### 单目标权重

- `--w-latency`：`log(1+latency)` 权重
- `--w-energy`：`log(1+energy)` 权重
- `--w-area`：`log(1+area)` 权重

### 输出

- `--output-dir`：结果目录（`bo_history.csv`、`best_result.json` 等）

---

## 2) `dse_nsga2_surrogate.py`

### 搜索预算

- `--generations`：进化代数
- `--population`：种群大小
- `--init-evals`：初始真实评估数
- `--evals-per-gen`：每代真实评估数（其余依赖 surrogate 预测）

### 其他

- `--base-config`、`--weights`、`--nn`、`--seed`、`--device`
- `--run-accuracy`、`--enable-saf`、`--enable-variation`、`--enable-rratio`、`--fixed-qrange`
- `--output-dir`

### 输出

- `nsga2_history.csv`：全部真实评估记录
- `pareto_front.csv`：非支配解前沿
- `summary.json`：评估总数与前沿大小

---

## 3) `dse_mobo_parego.py`

### 搜索预算

- `--iterations`：总迭代数
- `--init-random`：随机初始样本数

### 其他

- `--base-config`、`--weights`、`--nn`、`--seed`、`--device`
- `--run-accuracy`、`--enable-saf`、`--enable-variation`、`--enable-rratio`、`--fixed-qrange`
- `--output-dir`

### 输出

- `mobo_history.csv`：全部评估记录
- `pareto_front.csv`：非支配前沿
- `summary.json`：方法标识（MOBO-ParEGO）与统计

---

## 4) `compare_dse_results.py`

### 输入目录

- `--bo-dir`：BO 结果目录
- `--nsga2-dir`：NSGA-II 结果目录
- `--mobo-dir`：MOBO 结果目录

### 输出

- `--output-dir`
- 产物：`compare_summary.csv`、`compare_summary.json`

---

## 5) `run_fair_moo_benchmark.sh`（推荐入口）

用于公平对比三方法（并发运行 + 多随机种子重复 + 全局汇总）。

### 核心参数

- `--nn`：网络名（默认 `vgg8`）
- `--weights`：权重文件绝对路径
- `--base-config`：基础配置路径
- `--repeats`：重复次数（不同 seed）
- `--seed-start`：起始 seed
- `--budget`：公平预算（BO/MOBO迭代数；NSGA会据此计算代数）
- `--bo-init` / `--mobo-init` / `--nsga-init`：三方法初始真实评估数
- `--nsga-evals-per-gen`：NSGA 每代真实评估数
- `--out-root`：总输出目录

### 精度公平参数（可选）

- `--run-accuracy`：三方法都启用 accuracy（非常慢）
- `--bo-topk-accuracy`：BO 两阶段复评 Top-K（默认 3）
- `--bo-no-two-stage`：关闭 BO 两阶段（不推荐）
- `--accuracy-target`：精度阈值（用于 BO 惩罚）
- `--accuracy-penalty`：精度惩罚系数（用于 BO）

### 非理想性开关（统一口径）

- `--disable-saf`
- `--enable-variation`
- `--enable-rratio`
- `--fixed-qrange`

### 输出

- 每个 seed：`seed_xx/bo`、`seed_xx/nsga2`、`seed_xx/mobo`、`seed_xx/compare`
- 总汇总：`global_summary.csv`、`global_summary.json`

---

## 6) 当前设计空间（来自 `dse_multi_utils.py`）

- `xbar_size`: `(256,256)` / `(512,512)`
- `adc_choice`: `4, 6, 7, 8`
- `dac_choice`: `1, 2, 3, 4`
- `pe_num`: `(2,2)` / `(4,4)` / `(8,8)`
- `tile_connection`: `0, 1, 2, 3`
- `inter_tile_bw`: `10, 20, 40, 80`
- `intra_tile_bw`: `512, 1024, 2048`

> 注意：`xbar_row` 必须能被 `Subarray_Size` 整除（Crossbar 约束）

---

## 7) 建议实验配置

### 快速开发（分钟级）

- BO：`iterations=6, init-random=2, run-accuracy=False`
- NSGA-II：`generations=3, population=8, evals-per-gen=2`
- MOBO：`iterations=8, init-random=3`

### 正式实验（小时级）

- BO 两阶段：`iterations=20, init-random=6, two-stage, topk-accuracy=3`
- NSGA-II：`generations=15, population=30, evals-per-gen=6`
- MOBO：`iterations=30, init-random=8`

