# `dse/run_dse.py` 参数参考

统一入口：所有算法通过 `--algos` 选择；每个 `(algo, seed)` 一个子目录 `<algo>_seed<seed>/`。

## 通用

| 参数 | 含义 |
|------|------|
| `--algos` | `bo_gp` \| `nsga2` \| `mobo`（可多选） |
| `--seeds` | 随机种子列表 |
| `--budget` | 每试验总 MNSIM 评估次数（含 init） |
| `--init-evals` | 随机初始化次数 |
| `--nn` | 网络名（默认 `vgg8`） |
| `--weights` | 权重 `.pth` |
| `--base-config` | `SimConfig.ini` |
| `--device` | 默认 `cpu` |
| `--dataset-module` | 默认 `MNSIM.Interface.cifar10` |
| `--workers` | 并行进程数；`0` 表示自动 |
| `--output-root` | 输出根目录；**默认 `AUTO`**：每次新建 `<仓库>/dse_runs/run_时间戳/`（不覆盖旧实验）。`--compare-only` / `--plot-only` 须写已有目录 |
| `--compare-only` | 不跑仿真，从已有子目录重算 HV 并写 `comparison/` |
| `--plots` | 仿真或 `--compare-only` 后写 PNG（需 `matplotlib`） |
| `--plot-only` | 只根据已有结果出图，不跑仿真 |

## 精度与非理想性

| 参数 | 含义 |
|------|------|
| `--run-accuracy` | 打开精度仿真（慢） |
| `--enable-saf` | 默认开启 |
| `--enable-variation` / `--enable-rratio` / `--fixed-qrange` | 见 `--help` |

## BO+GP（`bo_gp`）

| 参数 | 含义 |
|------|------|
| `--w-latency` / `--w-energy` / `--w-area` | 对数标量化权重 |
| `--two-stage` | 需 `--run-accuracy`；先硬件 BO 再 Top-K 复评精度 |
| `--topk-accuracy` | 两阶段复评数量 |
| `--accuracy-target` / `--accuracy-penalty` | 精度约束惩罚 |

## NSGA-II（`nsga2`）

| 参数 | 含义 |
|------|------|
| `--population` | 种群规模 |
| `--evals-per-gen` | 每代真实评估次数 |

## 设计空间（`dse/core.py` 中 `SPACE`）

维度与取值以代码为准，典型包括：`Xbar_Size`、`ADC_choice`、`DAC_choice`、`PE_Num`、`Tile_Connection`、`Inter_Tile_Bandwidth`、`Intra_Tile_Bandwidth` 等。约束：`xbar_row % Subarray_Size == 0`。

## 快速试跑建议

- 小预算：`--budget 8 --init-evals 3 --seeds 42`，先不加 `--run-accuracy`。
- 多目标对比：保持 `budget`、`seed`、`run-accuracy` 等开关在算法间一致。
