# 科研框架：面向 MNSIM-2.0 的研究主线

本文档基于 [开题报告v3-11.14.docx](/Users/bytedance/workspace/MNSIM-2.0/开题报告v3-11.14.docx) 与当前仓库实际资产整理，目标不是复述开题报告，而是将其转化为适合 `MNSIM-2.0` 当前阶段的可执行科研框架。

## 1. 框架定位

本仓库中的 Codex 科研框架应服务于一个更具体、更可落地的目标：

- 以 `MNSIM-2.0` 为统一评估底座
- 以 `RRAM-CIM` 多目标设计空间探索为研究对象
- 以 `measured-in-the-loop` 为创新主线
- 以“问题定义 -> 论文搜索 -> 实验执行 -> 结果归纳 -> 论文写作”五段式流程组织仓库

这意味着当前阶段的重点不是构建一个大而全的软件平台，而是先把以下三件事做扎实：

1. 把问题形式化清楚
2. 把论文搜索做宽、做深、做成体系
3. 把实验流程打通并可复现
4. 把实验结果稳定映射为论文章节与结论

## 2. 研究总目标

结合开题报告，本课题可以在当前仓库中收敛为如下总目标：

构建一个基于 `MNSIM-2.0` 的 RRAM-CIM 自动化设计探索框架，在满足精度约束的前提下，对时延、能耗、面积进行多目标优化，并进一步引入真实测试数据驱动的器件预设，研究器件非理想对最优设计迁移与鲁棒优化的影响。

## 3. 建议的科研主线

相比开题报告中较大的“系统平台”叙事，当前仓库更适合采用一条更强、更聚焦的论文主线：

### 主线 A：形式化问题定义

回答的问题是：

- 设计变量到底有哪些
- 优化目标与约束如何表达
- formal space 与 guidance space 各自承担什么角色

对应仓库层：

- `docs/framework/RRAM_DSE_Problem_Formulation_And_Method.md`
- `agent.md`

### 主线 B：自动化搜索与设计指导

回答的问题是：

- 在给定评估预算下，不同算法谁更高效
- 在受限空间内，真实 Pareto 前沿长什么样
- 在扩展空间内，能否提炼稳定的设计指导规律

对应仓库层：

- `dse/run_dse.py`
- `dse/run_matrix_csv.py`
- `artifacts/dse/scripts/`

### 主线 C：Measured-in-the-loop 鲁棒优化

这是最值得保留和加强的创新线。

回答的问题是：

- 当器件预设由真实测试数据而非默认标称值给出时，最优设计是否迁移
- 单一标称最优点在多器件场景下是否失效
- ADC、DAC、差分位置等补偿策略能否缓解器件退化

对应仓库层：

- `test_data/`
- `artifacts/dse/scripts/run_testdata_analysis.sh`
- `dse/extras/run_measured_matrix.py`

### 主线 D：论文化表达与科研交接

回答的问题是：

- 如何让实验结构直接映射到论文结构
- 如何让 Codex 多次接手时不丢研究上下文
- 如何让 prompt 和 handoff 复用，而不是每次重新解释项目

对应仓库层：

- `AGENTS.md`
- `codex/`
- `prompts/`

### 主线 E：扩展型论文搜索与对标

这一主线需要明确加入 Codex 责任范围，而不能只靠人工临时补文献。

回答的问题是：

- 当前工作应与哪些 venue 的论文体系对话
- 哪些方法可能来自传统 CIM 仿真器圈外部
- 哪些 baseline、优化方法、建模思路来自 EDA 或 ML 顶会
- related work 是否只覆盖了熟悉的小圈子，而忽略了可迁移方法

建议的基础 venue 视野：

- `IEEE TVLSI`
- `DAC`
- `ICCAD`
- `DATE`
- `IEDM`
- `ISSCC`
- `NeurIPS`
- `ICML`
- `AAAI`

对应仓库层：

- `prompts/literature/`
- `docs/`
- `references/` 或后续文献笔记目录

## 4. 推荐的论文章节映射

基于开题报告与现有实验设计，建议固定如下论文骨架：

### Section 1 Introduction

- 内存墙与边缘智能背景
- IMC / CIM 的必要性
- 现有工具链断层：`SPICE` 太慢，`MNSIM/NeuroSim` 偏评估器、缺少自动探索
- 本文主张：基于 `MNSIM` 的自动化 DSE，并引入 measured presets 做鲁棒优化

### Section 2 Background and Related Work

- RRAM-CIM 基本架构与主要非理想
- 现有仿真器与评估器
- 自动化 DSE / NAS / 多目标优化相关工作
- 来自 `DAC` / `ICCAD` / `TVLSI` 的 EDA 视角
- 来自 `NeurIPS` / `ICML` 的优化与代理建模视角
- 当前缺口：松耦合、可扩展、真实器件场景驱动的优化框架不足

### Section 3 Problem Formulation

- 设计变量定义
- PPA 与精度指标
- 精度约束下的多目标优化表达
- formal space 与 guidance space 定义
- measured preset 与 robust search 的扩展形式化

### Section 4 Baseline Search and Ground Truth

- formal space 穷举真值
- random / NSGA-II / MOBO 的预算内对比
- Pareto 质量、HV、收敛速度、可行率

### Section 5 Design Guidelines in Wider Space

- guidance space 搜索结果
- 关键变量趋势
- 与人工经验是否一致
- 哪些规律在多 seed 下稳定

### Section 6 Measured-in-the-loop Robust Optimisation

- measured preset 提取流程
- measured matrix 实验
- representative preset 下的 robust search
- compensation factors 分析

### Section 7 Cross-Network Generalisation

- LeNet / VGG / ResNet 对照
- 设计规律是否跨网络保持

### Section 8 Discussion and Limitations

- 当前模型边界
- measured presets 与真实 deployment 之间的距离
- 搜索预算限制
- 对未来器件模型和联合软硬件搜索的扩展方向

## 5. Codex 在该框架中的职责

基于开题报告，Codex 不应承担一个“全栈软件平台开发器”的角色，而应承担四类更适配当前阶段的职责：

### 5.1 实验编排器

- 识别该跑哪个脚本
- 固定预算、种子、配置与输出目录
- 保障实验可复现

### 5.2 结果整理器

- 从 run 目录中提取关键指标
- 组织 Pareto、HV、可行率、鲁棒性结论
- 生成论文友好的 markdown 摘要

### 5.3 写作辅助器

- 将实验结果映射到论文章节
- 区分“已验证发现”和“待验证假设”
- 控制措辞，避免夸大

### 5.4 研究记忆层

- 保存 handoff
- 维护 prompt 模板
- 固化下一次会话需要先读的文件和下一步动作

### 5.5 文献搜索器

- 扩展检索视野，而不是只搜本领域熟面孔
- 在硬件、EDA、优化、ML 几类 venue 之间建立桥接
- 为 related work、baseline 选择、方法借鉴提供结构化输入
- 标记“已覆盖的文献簇”和“尚未覆盖的文献簇”

## 6. 对开题报告的收敛性改写建议

开题报告中的部分内容适合作为远期愿景，但不建议直接成为当前仓库的主叙事。

### 建议保留的部分

- 从手工试错走向模型驱动设计
- 将设计问题形式化为多目标约束优化
- 用自动化搜索替代经验枚举
- 引入真实器件测试数据提升外部可信度

### 建议降级为远期愿景的部分

- 完整前后端微服务平台
- Celery / PostgreSQL / TimescaleDB / Redis / MinIO 体系
- 大规模 Docker 化部署与 SLO 目标
- “精度提升 50% / 时间缩短 70% / 支持 90% 参数配置”这类当前尚无实证支撑的量化承诺

原因很简单：这些内容更像产品工程目标，而你当前最强的科研优势其实在于：

- 已有 `MNSIM` 评估底座
- 已有 `DSE` 统一入口
- 已有 `test_data` 真实测量数据
- 已有 measured preset 流水线雏形

真正值得写成论文贡献的，是“问题形式化 + 自动化搜索 + measured-in-the-loop robustness”，而不是“大而全系统平台”。

但要支撑这三点，文献检索不能窄。否则容易出现两个问题：

- 方法上重复已有工作却误以为自己新
- 只与小范围工具论文对比，导致 related work 和 positioning 不够强

## 7. 仓库结构建议

在当前仓库中，科研框架建议固定为以下职责分层：

- `README.md`
  - 外部入口，说明仓库研究定位与 Codex 工作区入口
- `AGENTS.md`
  - Codex 的行为边界、证据纪律、文件纪律
- `agent.md`
  - 论文级实验主线、RQ、实验清单
- `docs/`
  - 问题定义、方法设计、分析报告、科研框架
- `codex/`
  - handoff、工作流、后续可加入阶段总结
- `prompts/`
  - setup、文献搜索、实验设计、结果分析、写作模板
- `artifacts/dse/`
  - 实验输出事实层

## 8. 当前阶段最值得优先补齐的内容

为了让这个科研框架真正可用，建议按以下顺序推进：

1. 完成 `formal_v3` ground truth 与算法对比，建立论文第一批硬证据
2. 建立一轮扩展文献搜索，覆盖 `TVLSI / DAC / ICCAD / NeurIPS / ICML`
3. 完成 measured presets 提取与 1 到 3 个 preset 的矩阵验证
4. 形成一个 measured robust search 的聚合分析脚本或报告模板
5. 把 `Section 2/3/4/6` 的论文草稿骨架写出来
6. 再考虑是否需要更重的系统化界面与服务层

## 9. 一句话版本

这套科研 Codex 框架的核心，不是“帮你做一个复杂平台”，而是“把开题报告中的研究命题，压缩成一条围绕 `MNSIM + DSE + measured presets + broad literature search + paper writing` 的可持续科研流水线”。
