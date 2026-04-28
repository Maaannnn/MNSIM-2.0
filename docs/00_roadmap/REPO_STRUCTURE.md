# 仓库组织：目录结构说明

- `MNSIM/` — MNSIM 2.0 核心代码（准确率/面积/能耗/延迟等模型）。
- `dse/` — 设计空间探索脚本与实现（NSGA-II、MOBO、BO 等）。
- `artifacts/dse/` — 实验产物与报告（datasets、search_runs、matrices、reports 等）。
- `test_data/` — 英文路径的测试数据目录（与原始 `测试数据/` 同步镜像，方便脚本/服务器环境）。
- `weights/` — 预训练权重（`.pth`）。根目录保留到该目录的符号链接，旧命令不变；脚本也会自动在此目录查找。
- `configs/` — 配置文件（如 `SimConfig.ini`）。根目录保留到该文件的符号链接，旧命令不变；脚本也会自动在此目录查找。
- `app/` — 轻量可视化/服务。
  - `server.py`：Flask 入口与路由绑定
  - `backend/`：分析、报告、同步等后端模块
  - `static/index.html`：页面骨架
  - `static/css/app.css`：样式
  - `static/js/app.js`：前端状态与交互逻辑
  - `dse_records.db`：本地 SQLite 数据库
- `docs/` — 说明文档与研究记录总目录。
  - `status/`：执行状态、路线图、仓库组织
  - `framework/`：论文框架、问题定义、选题定位与 claim
  - `simulator/`：`MNSIM` / `NeuroSim` / `CrossSim` / fidelity gap 分析
  - `notes/`：PDF / DOCX 阅读笔记与阶段性研究启发
  - `references/`：外部参考材料（官方手册、调研报告、开题文档等 PDF/DOCX）
- `SimConfig.ini` — 默认硬件配置（软链接 → `configs/SimConfig.ini`）。
- `*.pth` — 预训练权重（默认从仓库根目录读取，已忽略版本控制）。
- `.venv/` — 本地虚拟环境（已忽略版本控制）。

清理脚本：`tools/clean.sh` 可清除 `.DS_Store`、`__pycache__`、`.pytest_cache` 等临时文件。

注意：
- 已迁移权重与配置至新目录，并在根目录保留符号链接保证兼容；脚本也内置了查找顺序：
  - 权重查找：给定路径→`weights/<name>`→仓库根目录。
  - 配置查找：给定路径→`configs/<name>`→仓库根目录。
- 由于部分脚本与文档默认读取 `test_data/`，仓库保留原中文目录 `测试数据/`，并新增 `test_data/` 作为镜像，二者内容保持一致。

补充：使用中英文测试数据目录同步脚本：
- 同步到英文路径：`bash tools/sync_test_data.sh`
- 同步回中文路径：`bash tools/sync_test_data.sh -r`
