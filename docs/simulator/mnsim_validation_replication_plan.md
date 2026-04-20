# MNSIM 原论文验证的复现计划（T8.1 前置产物）

> **目的**：把 MNSIM TCAD 2023 §VII.B 的 "3.8% SRAM / 5.5% RRAM" 复现出来，作为 pim_sim ablation（T8.2 系列）的 anchor baseline。
>
> **状态**：2026-04-20 初版。**参数抄取自 ISSCC 两篇 PDF 原文**，尚未跑仿真验证。

---

## 1. 两篇参考文献的权威出处

| 标签 | 完整引用 | 本仓库 PDF | MNSIM 引用编号 |
|---|---|---|---|
| **RRAM-chip**（主验证） | Q. Liu et al., "33.2 A Fully Integrated Analog ReRAM Based 78.4TOPS/W Compute-In-Memory Chip with Fully Parallel MAC Computing," *ISSCC 2020*, pp. 500–502. DOI: `10.1109/ISSCC19947.2020.9062953` | `33.2_A_Fully_Integrated_Analog_ReRAM_Based_78.4TOPS_W_Compute-In-Memory_Chip_with_Fully_Parallel_MAC_Computing.pdf` | `[27]` |
| **SRAM-chip**（null control） | B. Yan et al., "A 1.041-Mb/mm² 27.38-TOPS/W Signed-INT8 Dynamic-Logic-Based ADC-less SRAM Compute-In-Memory Macro in 28nm with Reconfigurable Bitwise Operation for AI and Embedded Applications," *ISSCC 2022*, vol. 65, pp. 188–190. DOI: `10.1109/ISSCC42614.2022.9731545` | `A_1.041-Mb_mm2_27.38-TOPS_W_..._for_AI_and_Embedded_Applications.pdf` | `[10]` |

---

## 2. 参数抄取：RRAM-chip（ISSCC 2020 Paper 33.2）

### 2.1 从 PDF 直接抄出的事实

| 类别 | PDF 字段 | 值 | 来源段落 |
|---|---|---|---|
| 工艺 | Technology | **130 nm CMOS** | 正文结尾："The CMOS circuits are fabricated in a 130nm process." |
| 架构 | NN model | **784-100-10 MLP**（两层全连接） | 正文："this work implements a fully-integrated 784-100-10 MLP model" |
| 阵列 1 | First layer | **784 × 100 SW-2T2R** | 正文 + MNSIM 2.0 §VII.B："784×100 RRAM array designed for the first layer" |
| 阵列 2 | Second layer | **100 × 10 1T1R** | 正文：两 FC arrays + 阵列类型 |
| 设备容量 | Total ReRAM | **158.8 Kb** | 正文 |
| 设备状态 | on-chip | **3-level (quasi-2bit) / 7-level (quasi-3bit)** | 正文 |
| 设备状态 | off-chip | **256 states** (continuous tuning) | 正文 |
| ADC 类型 | Interface | **LPAR-ADC**（integrator + SC-DAC + comparator） | Fig 33.2.4 + 正文 |
| ADC 精度 | 1st stage | **2 bit**（典型） | Fig 33.2.5 + 正文 |
| ADC 精度 | 2nd stage | **8 bit** | 正文 |
| 供电 | VDD | **4.2 V** | Fig 33.2.5 |
| 供电 | VREAD | **0.2 V** | Fig 33.2.5 + 正文 §33.2.3 |
| 能效 | Peak TOPS/W | **78.4** | 正文 + title |
| 精度 | MNIST simulated | 94.4% | 正文 |
| 精度 | MNIST silicon (3bit W) | 93.4% | 正文 |
| 延迟 | MAC-OUT access time | **51.1 ns** | Fig 33.2.5 |
| 延迟 | Per-image inference | **77 μs** (MNIST) | 正文 + Fig 33.2.5 |

### 2.2 映射到 MNSIM `SimConfig.ini` key

| MNSIM key | 填值 | 依据 / 备注 |
|---|---|---|
| `[Process Information] Process_Node` | `130` | 论文 |
| `[Crossbar level] Xbar_Size` | `784, 100` | 第一层（主验证对象）。MNSIM §VII.B 专门比这一层 |
| `[Crossbar level] Cell_Type` | `RRAM` | 论文 |
| `[Crossbar level] Cell_Type` | `1T1R`（**MNSIM 只支持 `0T1R` / `1T1R` 两档**，见 `configs/SimConfig.ini:52` 注释 + `Crossbar.py:154` 的 `cell_type[0] == '0'` 唯一分支）。SW-2T2R 在代码层面无专门 branch | ✅ **已确认**：2T2R 作 1T1R 近似；若要模拟差分对 2×device，把 `Xbar_Size` 的列数翻倍到 `784, 200` 作为 workaround |
| `[Device level] Device_Resistance` | 暂用 `2e7,6e4`（HRS≈20MΩ, LRS≈60kΩ），从 Fig. 33.2.S1 右下角 `five 10ns` 分布图粗读 | **暂定**：后续若拿到更清晰原图或原验证配置，再替换 |
| `[Device level] Device_Variation` | baseline 先用 `1.0`（与当前 `configs/SimConfig_issc2020_33p2.ini` 一致），后续 `pim_sim` 组再用 `typical_robust`/wafer preset | **已定 baseline，pim_sim 组待扩展** |
| `[Device level] Device_Level` | `3`（on-chip quasi-2bit） | 论文 |
| `[Interface level] ADC_Choice` | `9`（`MNSIM/Hardware_Model/ADC.py` 内置 `Qi Liu` preset） | 用作 T8.1 的 PE-level baseline 近似；仍需核对这是否就是 MNSIM 原文 Table IV 的精确设置 |
| `[Interface level] ADC_Precision` | 对 `ADC_Choice = 9` 而言，**effective precision = 8**（由 `ADC.py` preset 隐式给出；ini 字段本身可保持 `0`） | 论文 2nd-stage |
| `[Algorithm Configuration] NN` | T8.1 的 macro PPA baseline **不必先走 `main.py`**；优先用 `ProcessElement` PE-level harness | 若后续要复现 77us per-image latency / MNIST accuracy，再补 `mlp_784_100_10` |
| `[Algorithm Configuration] Quantization_Scale` | 3 bit signed weights, 1 bit inputs | 论文 |

### 2.3 MNSIM TCAD 2023 Table IV（RRAM chip 验证目标）

来源：飞书知识问答 `https://ask.feishu.cn`（2026-04-20 用户提供）。MNSIM 论文 §VII.B 逐项对比如下 — 这是 T8.1 的 **硬复现目标**：

| metric | silicon（ISSCC 20-33.2） | MNSIM 2.0 原文报 | 相对误差（原文） |
|---|---|---|---|
| **Area (mm²)** | 3.77 | 3.50 | **−7.2%** |
| **Latency (ns)** (per MAC-OUT) | 51.10 | 53.38 | **+4.5%** |
| **Energy efficiency (TOPS/W)** | 78.40 | 74.44 | **−5.1%** |

**MNSIM 2.0 Table III 的配置**（供复现对照）：
- `(#array, #row, #col) = (1, 784, 100)` → 只跑第一层
- `(#act_row, #act_col) = (784, 100)` → 全并行（匹配论文 "Fully Parallel MAC"）
- `(Res, Op) = (8, MVM)` → **8-bit resolution**，对应论文 off-chip 256-state 精度，不是 on-chip 3-level

### 2.4 三项误差的平均

- RRAM 三项 |err| 平均：(7.2 + 4.5 + 5.1)/3 = **5.6% ≈ MNSIM §VII.B 报的 5.5%** ✓
- 这三项 = T8.2 ablation 的 **Y 向量**（5 configs × 3 metrics）

### 2.5 其它 silicon 数值（非 Table IV，作参考）

| metric | silicon 值 | MNSIM 可算？ | 备注 |
|---|---|---|---|
| Per-image latency (MNIST, 2-layer) | 77 μs | ✅ `Latency_Model` | 非 Table IV 指标，作 sanity check |
| MNIST accuracy (3bit W) | 93.4% silicon / 94.4% sim | ✅（接 PIM-oriented quantization 流） | |
| Power breakdown | ⚠️ Fig 33.2.5 图，无 numerical table | `Power_Model` 逐模块 | 非 Table IV 指标 |

### 2.4 尚未确定的关键参数（阻塞 T8.1）

- [ ] Device_Resistance：已先用 Fig. 33.2.S1 的 `five 10ns` 分布图粗读成 `2e7,6e4`；后续若要更严谨，可再做数字化或找原验证配置
- [ ] Device_Variation：未报。暂用 wafer 校准的 `asym preset` 作为 pim_sim 预设，MNSIM baseline 沿用默认 1%
- [x] ~~Xbar 2T2R 结构在 MNSIM 的 `Hardware_Model/Crossbar.py` 是否支持~~ → **已验证**：MNSIM 只有 `0T1R` / `1T1R` 两档（`Crossbar.py:154`），2T2R 用 `1T1R` 近似，列数可选翻倍
- [ ] 若后续要跑 end-to-end accuracy：补 `mlp_mnist` 网络定义与 MNIST 接口；**这不再阻塞 T8.1 的 macro PPA baseline**

---

## 3. 参数抄取：SRAM-chip（ISSCC 2022 Paper 11.7，null control）

### 3.1 直接抄出的事实

| 类别 | 值 | 来源 |
|---|---|---|
| 工艺 | **28 nm** | 正文 |
| 阵列 | **32-kb**，32 compartments × 16 WLs × 64 BLs | 正文 + MNSIM §VII.B |
| 单元 | 6T SRAM + 4T RLPU + DCC | 正文 + Fig 11.7.3 |
| ADC | **无**（DCC 取代） | 正文 |
| 精度 | INT8 signed | 正文 |
| VDD | **0.8 V** | 正文 |
| 时钟 | 3 ns 周期 = 333 MHz | 正文 |
| 能效 | **27.38 TOPS/W avg** (19.21–35.55 range) | 正文 |
| 权重密度 | 1.041 Mb/mm² | title + 正文 |
| DCC 占比 | **0.5% of macro power** | 正文 |
| 测试网络 | ResNet-34 (CIFAR-100), MobileNet (CIFAR-10) | 正文 |

### 3.1b MNSIM TCAD 2023 Table IV（SRAM chip 验证目标）

来源：飞书知识问答（同 §2.3）。这是 null control 的硬复现目标：

| metric | silicon（ISSCC 22-11.7） | MNSIM 2.0 原文报 | 相对误差（原文） |
|---|---|---|---|
| **Area (mm²)** | 0.030 | 0.034 | **+13.3%** |
| **Performance (GOPS)** | 16.00 | 16.22 | **+1.4%** |
| **Energy efficiency (TOPS/W)** | 27.38 | 28.23 | **+3.1%** |

**MNSIM 2.0 Table III 配置**：
- `(#array, #row, #col) = (32, 16, 64)` → 32 compartments
- `(#act_row, #act_col) = (1, 64)` → 每周期只激活 1 行 × 64 列
- `(Res, Op) = (1, AND)` → **1-bit bitwise AND**（不是 MVM）

**三项 |err| 平均：(13.3 + 1.4 + 3.1)/3 = 5.93%**，非 §VII.B 报的 3.8%。MNSIM 原论文的 3.8% 可能是别的子集（去掉 Area，(1.4+3.1)/2 = 2.25%，也不符）。**留待 §5 复现后实测确认**。

### 3.2 为什么做 null control 而不是 positive evidence

- 这颗芯片 **ADC-less**，pim_sim 的 Walden ADC 模型不适用
- SRAM-CIM 不是 RRAM，pim_sim 的 AsymmetricGaussianModel（HRS/LRS）语义不存在
- IR-drop 在数字 SRAM-CIM 的 6T + DCC 结构里不是主导误差源
- **结论**：SRAM 芯片上跑 pim_sim = 应该**不改变** MNSIM 的 3.8% 误差。如果 pim_sim 让 SRAM 误差**下降**，说明我们在假拟合；如果**上升**，说明 pim_sim 实现有 bug。这是论文里的负控制，必须跑但不用于 positive claim。

### 3.3 MNSIM SimConfig 映射（简化，因为不做 ablation）

| key | 值 |
|---|---|
| `Process_Node` | `28` |
| `Cell_Type` | `SRAM` |
| `Xbar_Size` | `16, 64`（单 compartment）× 32 compartments |
| `ADC_Choice` | N/A（digital，走 SA 路径） |
| `NN` | ResNet-34 (CIFAR-100) 或 MobileNet (CIFAR-10) — **MNSIM 现有 resnet18 最近，需要确认是否有 resnet34 变体** |

---

## 4. 审稿人会追问的参数不确定性

| 风险 | 缓解 |
|---|---|
| Device_Resistance / Variation 未直接披露 | **敏感度分析**：在 R_on/R_off 合理范围（论文组其他 paper 的数据）扫一组，展示误差对这些参数不敏感 |
| MNSIM 没有 SW-2T2R 直接支持 | 用 1T1R 作近似，说明"2T2R 主要影响 IR-drop 和 signed weight 实现，不影响 peak TOPS/W 量级" |
| MLP NetStruct 要新写 | 0.5 天工作量，一次性；`MNSIM/NetStruct/` 下加 `mlp_mnist.py` |
| ~~论文 Table IV 我们看不到~~ | ✅ 已解决（2026-04-20），见 §2.3 + §3.1b |

---

## 5. T8.1 的最小闭环检查单

**通过 T8.1 的条件**（缺一不可）：

**RRAM chip（ISSCC 20-33.2）复现目标 — 对齐 MNSIM 2.0 原文 Table IV**：

| metric | MNSIM 2.0 原文 | 我们的可接受区间（±3%） |
|---|---|---|
| Area (mm²) | 3.50 | [3.40, 3.60] |
| Latency (ns) | 53.38 | [51.78, 54.98] |
| Energy efficiency (TOPS/W) | 74.44 | [72.21, 76.67] |

**SRAM chip（ISSCC 22-11.7，null control）复现目标**：

| metric | MNSIM 2.0 原文 | 我们的可接受区间（±3%） |
|---|---|---|
| Area (mm²) | 0.034 | [0.033, 0.035] |
| Performance (GOPS) | 16.22 | [15.73, 16.71] |
| Energy efficiency (TOPS/W) | 28.23 | [27.38, 29.08] |

**过关清单**：

1. `configs/SimConfig_issc2020_33p2.ini` 已填，所有 `⚠️` 标的参数至少有一个合理默认值
2. `configs/SimConfig_issc2022_11p7.ini` 同上（null control）
3. `validate/literature_anchor_baseline.py --chip rram_isscc2020_33p2` 跑通，并写出 `validate/output/literature_anchor/baseline_mnsim_vs_issc.csv`
4. RRAM 三项 metric 落在上表区间，或至少给出与目标值的明确偏差说明和下一步调参方向
5. 若后续扩展到 end-to-end accuracy，再补 `mlp_mnist` / MNIST 路径
6. 若失败：先确认是 SimConfig 参数问题，再改 Hardware_Model 代码（记 commit，别覆盖）

**失败则切换**：改跑 SRAM-chip baseline（null control 路径），确认是 RRAM 特定问题而非 MNSIM 复现问题。

---

## 6. 后续任务锚点（交给 T8.2 系列）

本文档完成后，**T8.1 的输入就齐了**。T8.2a/b/c/d 只需要：

1. 新脚本 `validate/literature_anchor_ablation.py`
   - 循环 5 configs × 2 chips（RRAM + SRAM null control）
   - 每个 config 调一次 `evaluate_config`，传对应 `pim_sim_model` / `ir_drop_model` 参数
   - **2026-04-20 现状**：RRAM 路径已先落一个 ADC-only 版本；结果表明对 Liu 33.2 这颗芯片，generic Walden ADC 会把误差拉大，不应直接拿来做 positive claim
   - **2026-04-20 现状补充**：已新增 `pim_sim` chip profile registry。对 Liu 33.2，`pim_sim_chip_profile` 目前是 **public-data-safe no-op**，因为 `MNSIM` baseline 已经走 `ADC_Choice=9` 的 Qi Liu 专用实现，并已用 paper-backed `Device_Resistance`。这给出了正式的 `pim_sim + MNSIM + baseline` 结果，但当前数值与 baseline 相同
2. 产物 CSV：`validate/output/literature_anchor/ablation_<chip>_<date>.csv`
3. 汇总脚本画 bar chart：每个 metric 的 5 configs 误差柱状图
4. 计算 Δ_device / Δ_irdrop / Δ_adc / interaction 并写入 `docs/paper/section_4_outline.md`

---

## Changelog

- **2026-04-20 初版**（claude）：从 ISSCC 2020 §33.2 + ISSCC 2022 §11.7 两篇 PDF 抄取全部可抄参数。标注 6 个 `⚠️ 需要确认` 项为 T8.1 阻塞点。
- **2026-04-20 v1.1**（claude）：阻塞点 #3（2T2R 支持）经 `Crossbar.py:154` 代码确认，MNSIM 只支持 `0T1R`/`1T1R`；`Cell_Type = 1T1R` 为官方近似。阻塞点 #5（MNSIM Table IV）用户提供飞书截图数据，§2.3 + §3.1b 已填具体 metric；§5 过关区间改为 MNSIM 原文值 ±3%。剩余阻塞：Device_Resistance / Device_Variation / LPAR-ADC mapping / MLP NetStruct。
- **2026-04-20 v1.2**（codex）：补 `validate/literature_anchor_ablation.py` 和 `validate/output/literature_anchor/ablation_rram_isscc2020_33p2.csv`。同时修正 `pim_sim` ADC delta 在 `ADC_Choice=9` 下的基线读取错误：必须走 MNSIM 实际 `ADC.py` 行为，不能用 generic lookup/Walden 近似。当前结果显示：对 Liu 33.2，ADC-only Walden 修正会把 area / latency / energy-efficiency 三项对 silicon 的误差全部拉大，因此这条路径暂不支持 “pim_sim improves PPA fidelity” 的正结论。
- **2026-04-20 v1.3**（codex）：新增 `pim_sim/ppa/chip_profiles.py`，把 Liu 33.2 注册为 chip-specific profile，并在 `literature_anchor_ablation.py` 里产出正式 `pim_sim_chip_profile` 结果。当前该 profile 是显式 no-op，原因是 baseline 已经包含 Qi Liu 专用 ADC + paper-backed device 阻值；因此 `pim_sim + MNSIM + baseline` 与 baseline 数值一致。这不是 bug，而是当前公开数据下最保守可辩护的结果。
- **2026-04-20 v1.4**（codex）：把 Liu 33.2 chip profile 升级为**非零** public-data-backed correction。新增两项 overlay：1) 按 Fig. 33.2.2 给 `PE_area` 补一个缺失的 `4KB output buffer` 边界面积；2) 按 Fig. 33.2.1 / Fig. 33.2.5 的 SW-2T2R measured `1.9×` power reduction，只对 current-dependent 的 `ADC + xbar` 能量施加 `1/1.9` 缩放。结果：`pim_sim_chip_profile` 从 baseline 的 `3.391 mm² / 53.79 ns / 74.65 TOPS/W` 变成 `3.460 mm² / 53.79 ns / 79.11 TOPS/W`。相对 silicon 的绝对误差变化：area `10.04% -> 8.22%`、latency `5.27% -> 5.27%`、energy-efficiency `4.78% -> 0.91%`。
