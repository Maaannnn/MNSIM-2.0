# dse/extras/

非主线实验脚本，不属于核心 DSE 流水线。

| 文件 | 状态 | 说明 |
|------|------|------|
| `build_surrogate_dataset.py` | ⚠️ 已失效 | 使用了旧 `SPACE` 全局字典；当前 core.py 改为 profile-based，`SPACE={}` 空字典，直接运行会报错 |
| `train_surrogate.py` | ⚠️ 已失效 | 同上，依赖旧 `SPACE` API |
| `surrogate_query.py` | 存档 | 查询 sklearn joblib 模型，配套上面两个脚本，不参与主线流程 |
| `export_rram_v2_matrices.py` | 存档 | 生成 `artifacts/dse/matrices/rram_v2/matrix_A/B/C/D.csv`，矩阵已生成完毕 |
| `run_robustness.py` | 存档 | 鲁棒性测试工具，不属于论文核心实验 |
| `extract_measured_presets.py` | 新增工具 | 从 `test_data/` 提取真实测试统计，导出 measured preset 建议与 retention stress 标签 |
| `run_measured_matrix.py` | 新增工具 | 读取 `measured_presets.csv`，为每个 preset 生成 patched SimConfig，并自动调用 `run_matrix_csv.py` 跑矩阵实验 |
