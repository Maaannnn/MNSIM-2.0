# DSE Artifacts

统一后的 DSE 产物目录如下：

```text
artifacts/dse/
  datasets/      # 可持续累积的数据集
  search_runs/   # run_dse.py 的搜索/对比实验
  matrices/      # 固定论文矩阵 CSV
  matrix_runs/   # run_matrix_csv.py 的逐点实验
  docs/          # 论文实验设计说明
  scripts/       # 一键运行脚本
```

当前保留的主要内容：

- `datasets/cifar10_vgg8_cifar10_vgg8_params_SimConfig_acc_saf1_var1_rr0_qfix0_acct0_88`
  - 当前与你的 RRAM 论文主线最相关的数据集

- `matrices/rram_v2`
  - 第二版论文矩阵 `A/B/C/D`

- `search_runs/my_exp`
  - 早期算法对比实验，暂时保留

- `docs/rram_formal_v3.md`
  - 正式论文版搜索空间设计说明

- `docs/rram_guidance_v4.md`
  - 面向设计指导的增强搜索空间说明

- `docs/server_run_guide.md`
  - 服务器上传、环境配置、运行、监控与结果回传说明

- `scripts/run_formal_v3_search.sh`
  - 正式论文版 `random / nsga2 / mobo` 运行脚本

- `scripts/run_guidance_v4_search.sh`
  - 面向设计指导的增强搜索空间运行脚本

- `scripts/run_dual_a100_jobs.sh`
  - 双 A100 一键并行提交脚本：GPU0 跑 guidance_v4，GPU1 跑 formal_v3

建议：

- 新采样数据优先放 `datasets/`
- 新搜索实验优先放 `search_runs/`
- 新论文矩阵优先放 `matrices/`
- 用矩阵逐点执行得到的实验优先放 `matrix_runs/`
