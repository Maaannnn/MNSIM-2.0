# DSE Artifacts

## 目录结构

```
artifacts/dse/
├── datasets/                         # [只读] 持续累积的评估数据集
├── matrices/rram_v2/                 # 论文固定矩阵 CSV
│   ├── matrix_A.csv                  # 器件迁移矩阵（P0-P3 × xbar × adc）
│   ├── matrix_B.csv                  # 接口补偿矩阵（adc/dac/sub_position）
│   ├── matrix_C.csv                  # 系统瓶颈矩阵（pe_num × tile × bw）
│   ├── matrix_D.csv                  # 扩展实验矩阵
│   ├── matrix_all.csv                # A+B+C+D 合并（72 行）
│   └── matrix_E.csv                  # formal_v3 全空间穷举（36 点 Ground Truth）
├── matrix_runs/                      # run_matrix_csv.py 产物
│   ├── exp_formal_v3_exhaustive/     # [待运行] 36 点穷举评估结果
│   └── archive/                      # 历史测试运行（batch_demo 等）
├── search_runs/                      # run_dse.py 算法对比实验产物
│   ├── exp01_formal_v3/              # [待运行] formal_v3 算法对比（random/nsga2/mobo）
│   ├── exp02_guidance_v4/            # [待运行] guidance_v4 设计指导（random/nsga2/mobo）
│   └── archive/exp00_preliminary/    # 早期 BO+GP/NSGA2/MOBO 探索性实验
├── docs/
│   ├── rram_formal_v3.md             # 正式论文搜索空间设计说明
│   ├── rram_guidance_v4.md           # 设计指导增强空间说明
│   └── server_run_guide.md           # 服务器运行指南
└── scripts/
    ├── run_formal_v3_exhaustive.sh   # 实验 0：36 点穷举（Ground Truth）
    ├── run_formal_v3_search.sh       # 实验 1：formal_v3 算法对比
    ├── run_guidance_v4_search.sh     # 实验 2：guidance_v4 设计指导
    ├── run_dual_a100_jobs.sh         # 双 GPU 并行：实验 1 + 实验 2 同时跑
    └── finalize_search_run.sh        # 任务结束后重建 comparison + HTML 分析
```

---

## 实验进度

| # | 实验 | 空间 | 脚本 | 状态 |
|---|------|------|------|------|
| 0 | formal_v3 穷举（Ground Truth） | 36 点 | `run_formal_v3_exhaustive.sh` | ⏳ 待运行 |
| 1 | formal_v3 算法对比 | 36 点 | `run_formal_v3_search.sh` | ⏳ 待运行 |
| 2 | guidance_v4 设计指导 | 864 点 | `run_guidance_v4_search.sh` | ⏳ 待运行 |
| — | 早期 BO/NSGA2/MOBO 探索 | 旧空间 | — | ✅ 已归档 |

---

## 下一步实验目标

> 详细论文实验目标见下方「实验目标」章节

### 推荐运行顺序

**步骤 1：先跑穷举（获得 Ground Truth）**

```bash
bash artifacts/dse/scripts/run_formal_v3_exhaustive.sh
```

- 对 `rram_formal_v3` 全部 36 点逐一评估
- 得到真实 Pareto Front，用于后续校验算法结果
- 约耗时：36 点 × 单点评估时间

**步骤 2：跑正式算法对比**

```bash
bash artifacts/dse/scripts/run_formal_v3_search.sh
```

- 在 36 点空间内比较 `random / nsga2 / mobo`
- 3 种算法 × 3 个 seed = 9 次 trial，budget=18，worker=3
- 产物：`search_runs/exp01_formal_v3/`

**步骤 3：跑设计指导实验（可与步骤 2 并行）**

```bash
bash artifacts/dse/scripts/run_guidance_v4_search.sh
```

- 在 864 点更大空间内验证 `512x512+2x2+bw80` 是否仍然稳定
- 产物：`search_runs/exp02_guidance_v4/`

**步骤 4（服务器双 GPU）：一键并行跑步骤 2+3**

```bash
bash artifacts/dse/scripts/run_dual_a100_jobs.sh
```

**步骤 5：实验结束后生成分析报告**

```bash
bash artifacts/dse/scripts/finalize_search_run.sh artifacts/dse/search_runs/exp01_formal_v3
bash artifacts/dse/scripts/finalize_search_run.sh artifacts/dse/search_runs/exp02_guidance_v4
```

---

## 实验目标（论文视角）

### 已完成（矩阵实验 A/B/C/D）

矩阵实验已经回答了三件事：

- **器件迁移（A）**：P3 在无补偿时会失效，P1/P2 可以接受
- **接口补偿（B）**：`ADC=6+DAC=128` 相比 `ADC=4+DAC=32` 有明显 PPA 收益
- **系统瓶颈（C）**：`512×512 + 2×2 + tile_connection=2 + inter_tile_bw=80` 最稳

### 待完成

**目标 1：验证搜索空间是否可解（实验 0）**

- 用穷举获得 36 点完整 Pareto Front
- 确认 P3 能否在接口补偿后进入可行域（acc ≥ 0.88）
- 确认 `ADC=6+DAC=128` vs `ADC=4+DAC=32` 的全局对比结论

**目标 2：算法效率对比（实验 1，论文核心实验）**

- 回答：在 36 点空间内，`nsga2 / mobo` 相比 `random` 有多大优势？
- 指标：Hypervolume、Pareto size、best latency/energy/area、wall time
- 用 3 seed 结果做均值 ± 标准差

**目标 3：设计指导（实验 2，论文辅助实验）**

- 回答：在 864 点更大空间下，原矩阵实验结论是否仍然成立？
- 具体：`xbar_size=512` 是否仍然主导？`ADC=6+DAC=128` 的效果是否随 pe_num 变化？
- 为论文"设计建议"章节提供系统级依据

### 论文结构映射

```
Section 3: Problem Formulation     ← 设计变量定义（已完成）
Section 4: Matrix Analysis         ← 矩阵实验 A/B/C/D（已完成）
Section 5: Algorithm Comparison    ← 实验 1（formal_v3，待运行）
Section 6: Design Guidelines       ← 实验 0 + 实验 2（待运行）
```

---

## 常用参数覆盖

所有脚本均支持环境变量覆盖，例如：

```bash
# 服务器 CUDA 运行
DEVICE=cuda PYTHON_BIN=python bash artifacts/dse/scripts/run_formal_v3_search.sh

# 修改 budget 快速测试
BUDGET=6 WORKERS=2 bash artifacts/dse/scripts/run_formal_v3_search.sh

# 只跑单个算法
ALGOS=nsga2 bash artifacts/dse/scripts/run_formal_v3_search.sh
```

---

## 数据存放规范

| 类型 | 存放位置 |
|------|----------|
| 新采样数据（累积） | `datasets/` |
| 新搜索实验结果 | `search_runs/expNN_name/` |
| 新矩阵定义 | `matrices/rram_v2/matrix_X.csv` |
| 矩阵逐点评估结果 | `matrix_runs/exp_name/` |
