# MNSIM 2.0 深度技术分析报告
> 面向组会汇报 | 结合论文（IEEE TCAD 2023）与代码（GitHub: thu-nics/MNSIM-2.0）
>
> 论文全称：*MNSIM 2.0: A Behavior-Level Modeling Tool for Processing-In-Memory Architectures*
> DOI: 10.1109/TCAD.2023.3251696

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [系统全局设计哲学](#2-系统全局设计哲学)
3. [整体架构总览](#3-整体架构总览)
4. [层次化硬件建模：每层的设计与实现](#4-层次化硬件建模每层的设计与实现)
   - 4.1 [Layer 0 - 全局系统层](#41-layer-0---全局系统层)
   - 4.2 [Layer 1 - PIM Bank 层](#42-layer-1---pim-bank-层)
   - 4.3 [Layer 2 - Tile 层](#43-layer-2---tile-层)
   - 4.4 [Layer 3 - Processing Element (PE) 层](#44-layer-3---processing-element-pe-层)
   - 4.5 [Layer 4 - Memory Array 层（核心统一模型）](#45-layer-4---memory-array-层核心统一模型)
   - 4.6 [Layer 5 - Device Model 层](#46-layer-5---device-model-层)
5. [层间通信机制](#5-层间通信机制)
6. [映射与调度模块](#6-映射与调度模块)
7. [算法层：精度仿真与训练量化流](#7-算法层精度仿真与训练量化流)
   - 7.1 [非理想性注入机制](#71-非理想性注入机制)
   - 7.2 [PIM 导向训练与量化](#72-pim-导向训练与量化)
8. [闭环反馈机制与代码实现](#8-闭环反馈机制与代码实现)
9. [代码结构详解](#9-代码结构详解)
   - 9.1 [目录结构](#91-目录结构)
   - 9.2 [核心入口 main.py](#92-核心入口-mainpy)
   - 9.3 [SimConfig.ini 配置系统](#93-simconfigini-配置系统)
   - 9.4 [关键模块代码路径](#94-关键模块代码路径)
10. [PPA 建模方法](#10-ppa-建模方法)
    - 10.1 [延迟模型](#101-延迟模型)
    - 10.2 [面积模型](#102-面积模型)
    - 10.3 [功耗与能量模型](#103-功耗与能量模型)
11. [与 NeuroSim 的学术比较](#11-与-neurosim-的学术比较)
12. [验证方法与精度](#12-验证方法与精度)
13. [**可优化方向全景分析（研究机会）**](#13-可优化方向全景分析研究机会)
    - 13.1 [物理器件层优化](#131-物理器件层优化)
    - 13.2 [电路外围层优化](#132-电路外围层优化)
    - 13.3 [架构与调度层优化](#133-架构与调度层优化)
    - 13.4 [算法与训练层优化](#134-算法与训练层优化)
    - 13.5 [系统 DSE 层优化（CustomSimLab 方向）](#135-系统-dse-层优化customsimlab-方向)
14. [总结：MNSIM 2.0 的设计权衡地图](#14-总结mnsim-20-的设计权衡地图)

---

## 1. 背景与动机

### 1.1 "存储墙"问题

在 AI 加速器设计领域，传统冯·诺依曼架构面临根本性瓶颈：**计算单元（CPU/GPU）与存储器（DRAM）之间的数据搬运消耗了超过 80% 的系统总能量**，这被称为"存储墙"（Memory Wall）问题。

以卷积神经网络（CNN）为例：
- VGG-16 推断一张图片需要 ~15 GB 数据搬移
- 这些数据搬移能耗远超实际 MAC（乘累加）计算本身
- 传统加速器（如 NVDLA、TPU）通过更大片上 SRAM 缓解，但根本未解决

### 1.2 PIM 架构的解决思路

存内计算（Processing-In-Memory, PIM）的核心思想：**在存储阵列内部直接完成计算，权重永远不需要搬移**。

```
传统架构：
  Weight (Memory) ──大量数据搬移──> Compute Unit
                      ↑ 瓶颈所在

PIM 架构：
  Weight 存储在阵列中
  Input 施加到阵列
  Output 直接从阵列读出（电流/数字结果）
  ──> 权重数据搬移为零
```

PIM 主要分两类：

| 类型 | 工作原理 | 代表器件 |
|------|---------|---------|
| **模拟 PIM** | 利用欧姆定律 I=GV，在模拟域完成矩阵向量乘（MVM） | RRAM, PCM, MRAM |
| **数字 PIM** | 存储单元附加逻辑门，位串行乘法 | SRAM-CIM, DRAM-CIM |

### 1.3 为什么需要 MNSIM 这样的工具

PIM 架构的设计面临三大挑战，使得传统仿真工具不够用：

1. **SPICE 太慢**：8KB memristor 阵列仿真一个输入向量需要 >10 分钟；完整 NN 需要数月
2. **设计空间巨大**：器件×阵列规模×量化精度×调度策略 ≈ 10万+ 组合
3. **算法-硬件耦合紧密**：器件非理想性直接影响 NN 精度，不能分开评估

MNSIM 2.0 的定位：**在可接受的精度误差（3.8%–5.5%）下，将仿真速度提升 7000 倍以上，支持跨层次协同评估**。

---

## 2. 系统全局设计哲学

MNSIM 2.0 的设计建立在三个核心哲学原则上：

### 原则一：行为级建模（Behavior-Level）而非电路级

通过抽象电路功能行为，用**解析模型 + 离线参考数据库**替代在线 SPICE 仿真。代价是引入 ~5% 的建模误差，换取的是三个数量级以上的速度提升。

### 原则二：闭环协同（Closed-Loop Co-design）

硬件性能结果反馈给算法优化，算法优化结果再送回硬件评估。这是一个**真实的设计迭代闭环**，而非单向流水线。

```
NN 模型 ──[训练/量化流]──> 优化后 NN 模型
            ↑                    │
     架构参数反馈          [映射/调度模块]
            │                    │
     [PPA 建模]◄──────────[架构性能建模]
     [精度仿真]◄──────────[非理想性注入]
```

### 原则三：统一抽象（Unified Abstraction）

用**同一套参数化模型**描述模拟 PIM 和数字 PIM，使得两类架构可以在同一框架下公平比较。这是 MNSIM 2.0 相对前代工具最重要的学术贡献之一。

---

## 3. 整体架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         MNSIM 2.0                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Algorithm Layer（算法层）                    │  │
│  │                                                          │  │
│  │   NN Model ──> Quantization ──> Noise Injection ──> ACC │  │
│  │   (PyTorch)    (Mixed-Prec)    (Variation/SAF/ADC)      │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ 权重矩阵 + 精度要求                │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │              Mapping & Scheduling Layer（映射调度层）      │  │
│  │                                                          │  │
│  │   CNN → TCG（Tile Connection Graph）→ 数据流调度          │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ 映射结果 + 调度方案               │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │              Hardware Model Layer（硬件模型层）            │  │
│  │                                                          │  │
│  │   System → Bank → Tile → PE → MemArray → Device         │  │
│  │                                                          │  │
│  │   ├── Latency Model    ├── Area Model                   │  │
│  │   ├── Power Model      └── Energy Model                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  配置输入: SimConfig.ini        输出: PPA + Accuracy            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 层次化硬件建模：每层的设计与实现

### 4.1 Layer 0 - 全局系统层

**对应代码**：`main.py`，`SimConfig.ini`

全局系统由三部分构成：CPU + DRAM + PIM。

- **CPU**：负责 NN 映射结果生成、权重部署到 PIM 存储器、PIM 控制器初始化
- **DRAM**：片外大容量存储，存放待部署的权重和输入图像
- **PIM**：被 CPU 唤醒后，从 DRAM 读取输入，由内部控制器管理整个 NN 计算

关键设计决策：PIM 内部的计算完全独立于 CPU，CPU 只负责启动和收结果。这个"批量计算"模式使得权重只需要加载一次，对能效极为有利。

### 4.2 Layer 1 - PIM Bank 层

**对应代码**：`MNSIM/Hardware_Model/` 中的 Bank 相关类

Bank 是最顶层的 PIM 计算单元，多个 Bank 之间通过 NoC（片上网络）互连。

**关键参数（SimConfig.ini 中）**：
```ini
[Architecture]
BankNum = 1           # Bank 数量
```

Bank 层的主要功能：
- 接收来自 DRAM 的输入特征图数据
- 协调内部多个 Tile 的计算
- 通过 NoC 聚合多 Tile 的部分和结果

**NoC 延迟建模**：MNSIM 2.0 使用曼哈顿距离（Manhattan Distance）估计 Tile 间通信延迟，这是行为级建模的典型简化。

### 4.3 Layer 2 - Tile 层

**对应代码**：`MNSIM/Hardware_Model/Tile.py`（及关联的 Latency/Area/Power 子模块）

Tile 是调度的基本单位，也是数据流路由的核心节点。

**Tile 的组成**：
```
Tile
├── 多个 PE（数量由 PENumPerTile 配置）
├── 输入缓冲区（Input Buffer）
├── 输出缓冲区（Output Buffer）
├── 数据转发单元（Data Forwarding Unit）
└── Tile 级控制器
```

**关键参数**：
```ini
[Architecture]
TileNumPerBank = 16    # 每 Bank 的 Tile 数
PENumPerTile   = 12    # 每 Tile 的 PE 数
```

**数据流设计**：Tile 内部的 IFmap（输入特征图）可以广播给所有需要它的 PE，这是 Weight Stationary 数据流的体现——权重固定在阵列中，输入数据在 PE 间流动。

**Tile 连接图（TCG）**：这是 MNSIM 2.0 的核心映射结构。TCG 描述了 NN 各层到 Tile 的分配关系，以及 Tile 之间的数据依赖关系。

```python
# 对应代码：MNSIM/Mapping_Model/Tile_connection_graph.py
from MNSIM.Mapping_Model.Tile_connection_graph import TCG
TCG_mapping = TCG(NetStruct=structure_file, SimConfig_path=SimConfig_path)
```

### 4.4 Layer 3 - Processing Element (PE) 层

**对应代码**：`MNSIM/Hardware_Model/` PE 相关类

PE 是计算的基本执行单元，每个 PE 包含若干 Memory Array 实例。

**PE 的组成**：
```
PE
├── N 个 Memory Array（crossbar 或 SRAM array）
├── 局部累加逻辑（Partial Sum Accumulation）
├── 输入/输出寄存器
└── 局部控制逻辑
```

**关键参数**：
```ini
[Architecture]
ArrayNumPerPE  = 8     # 每 PE 的 Array 数
```

**PE 的功能职责**：
- 执行权重矩阵的一个子块的 MVM 计算
- 累加来自多个 Array 的部分和
- 向 Tile 上报计算结果

**PE 利用率（PE Utilization Rate）**：这是评估映射效率的关键指标。当权重矩阵尺寸不能整除阵列尺寸时，会出现 PE 空洞（idle columns/rows），降低利用率。MNSIM 2.0 会统计并报告这一指标。

### 4.5 Layer 4 - Memory Array 层（核心统一模型）

**对应代码**：`MNSIM/Hardware_Model/crossbar.py`（及 techfile.txt）

这是 MNSIM 2.0 **最重要的学术创新**——首次提出统一的 PIM 存储阵列模型，能够同时描述模拟 PIM 和数字 PIM。

#### 4.5.1 统一模型的核心结构

```
Memory Array（统一模型）
│
├── 子阵列 1（Subarray）
│   ├── WL Driver（字线驱动器）
│   ├── 存储单元矩阵（Cell Matrix）
│   ├── DAC × n（模拟PIM用，数字PIM省略）
│   ├── ADC × m（模拟PIM高精度，数字PIM用SA）
│   └── Logic Gates（数字PIM用AND门等）
│
├── 子阵列 2
│   └── ...
│
└── Adder Tree（加法器树，合并子阵列部分和）
```

#### 4.5.2 关键参数（决定模拟/数字PIM的分界）

```ini
[Crossbar]
ArrayRow      = 128    # 阵列行数
ArrayCol      = 128    # 阵列列数
SubarrayNum   = 1      # 关键！1=模拟PIM crossbar模式；=ArrayRow 则为数字PIM模式
WeightPrecision = 4    # 权重位宽 Pw
InputPrecision  = 8    # 输入位宽 Pa
DACResolution   = 4    # DAC 分辨率（模拟PIM）
ADCResolution   = 8    # ADC 分辨率（模拟PIM）
```

**`SubarrayNum` 的物理含义**：

- **SubarrayNum = 1（模拟PIM）**：整个阵列作为一个 crossbar，所有行的电流在 BL 上自然叠加，一次完成 N 行的 MVM
- **SubarrayNum = ArrayRow（数字PIM）**：每行是独立的子阵列，每行读出 1-bit 权重，附带 AND 门执行位运算，再通过加法器树聚合

#### 4.5.3 模拟 PIM 的计算语义

```
输入向量 x[N] ──DAC量化──> 电压向量 V[N]（施加到WL）
权重矩阵 W[M×N] ──编程──> 电导矩阵 G[M×N]

BL电流：I[M] = G[M×N] · V[N]    ← 欧姆定律，并行MVM

I[M] ──ADC量化──> 数字输出 O[M]
```

**这里的关键假设（也是最大简化）**：G 是常数，I 与 V 线性相关。真实 RRAM 的 IV 曲线是非线性的！

#### 4.5.4 数字 PIM 的计算语义

```
O_j = Σ_{b=0}^{B-1} 2^b × Σ_{i=1}^{N} (A_{bj} AND W_{ji})

其中：
  B   = 输入位宽
  A_bj = 输入第 b 位
  W_ji = 权重值（1-bit，存在每个memory cell）
  AND  = 每个cell附带的逻辑门
```

位串行计算需要 B 个时钟周期完成一个完整的 MVM，但可以全行并行。

#### 4.5.5 互连线的 IR Drop 建模

```
简化解析模型：
  V_drop(i) ≈ I_cumulative(i) × R_wire_per_unit × i

  L_BL = ArrayRow × cell_pitch
  R_wire = ρ × L / A（电阻率 × 长度 / 截面积）
```

**已知局限**：MNSIM 的 IR drop 是基于平均电流的解析估计，未考虑具体激活模式（activation pattern）对电流分布的影响——不同输入会导致不同的电流分布，从而产生不同的 IR drop 分布。这是精度误差的主要来源之一。

### 4.6 Layer 5 - Device Model 层

**对应代码**：`techfile.txt`，`SimConfig.ini` 中的 Device 配置节

器件层是整个系统的物理基础。MNSIM 2.0 通过**参数化统计模型**抽象器件特性，而非进行器件级 SPICE 仿真。

#### 4.6.1 支持的器件类型

| 器件 | 类型 | 存储机制 | 适用场景 |
|------|------|---------|---------|
| RRAM（HfOx/TaOx等）| 模拟PIM | 导电细丝阻变 | 最主流，非线性强 |
| PCM | 模拟PIM | 晶/非晶相变 | 多值存储精度好 |
| MRAM | 模拟/数字 | 磁隧道结 | 耐久性好 |
| Flash（NOR/NAND）| 模拟PIM | 浮栅电荷存储 | 成熟工艺 |
| SRAM | 数字PIM | 锁存器（6T） | 速度最快，面积最大 |

#### 4.6.2 器件参数接口（SimConfig.ini 相关配置）

```ini
[Device]
DeviceRonMean   = 1e4       # 低阻态均值（Ω）
DeviceRonStd    = 1e3       # 低阻态标准差（器件间变化）
DeviceRoffMean  = 1e7       # 高阻态均值
DeviceRoffStd   = 1e6       # 高阻态标准差
CellBit         = 2         # 每 cell 存储位数（SLC=1, MLC=2, TLC=3）
SAFRatio        = 0.01      # Stuck-at Fault 比例
```

#### 4.6.3 电导 → 权重的映射关系

```
W_quant ∈ {0, 1, ..., 2^Pw - 1}（Pw 位量化权重）
    │
    ▼ 线性映射
G_target = G_min + W_quant × (G_max - G_min) / (2^Pw - 1)
    │
    ▼ 加入高斯噪声（device variation）
G_actual ~ N(G_target, σ²_device)
```

**MNSIM 的简化**：σ_device 是一个**固定常数**，与写次数、温度、保留时间无关。真实器件中这些因素会显著改变 σ。

#### 4.6.4 离线参考数据库（Reference Data Library）

MNSIM 2.0 的 PPA 建模核心机制：提前用 SPICE 仿真各个电路模块，拟合成解析表达式，存入 `techfile.txt`。在线运行时通过查表获取延迟、面积、功耗数据。

```
techfile.txt 包含内容示例：
  ADC（n-bit SAR）：
    area(n)    = A_coeff × 2^n × tech_factor
    power(n,f) = P_coeff × 2^n × f × Vdd²
    latency(n) = n × t_compare

  加法器树（depth = log₂(col)）：
    latency    = depth × gate_delay
    energy     = switching_activity × C_load × Vdd²
```

---

## 5. 层间通信机制

MNSIM 2.0 的通信建模采用**静态解析模型**（而非事件驱动仿真），这是行为级工具的典型选择。

### 5.1 通信的四条路径

```
路径 1：DRAM → Bank    （权重加载，计算前一次性完成）
路径 2：Bank → Tile    （IFmap 分发）
路径 3：Tile → Tile    （跨 Tile 部分和聚合）
路径 4：PE → Tile      （PE 内部结果上报）
```

### 5.2 NoC 延迟建模

对于 Tile 间通信，MNSIM 2.0 的 NoC 模型如下：

```
NoC 通信分两部分：
  Part 1：每个 Tile → 汇聚 Tile（同层内聚合）
          延迟 ∝ Manhattan_distance × hop_latency

  Part 2：汇聚 Tile → 下一层 Tile（层间传播）
          延迟 ∝ Manhattan_distance × hop_latency

总 NoC 延迟 = max(Part1, Part2)（流水线执行）
```

**局限**：曼哈顿距离是几何近似，没有考虑实际 NoC 拥塞（congestion）和仲裁延迟。

### 5.3 缓冲区建模

```ini
[Buffer]
InputBufferSize  = 16384   # 字节
OutputBufferSize = 16384   # 字节
```

缓冲区访问延迟通过查表获得（CACTI 类方法）。MNSIM 2.0 会根据缓冲区大小和访问模式估计总的缓冲区访问延迟和功耗。

### 5.4 通信 vs 计算的关键权衡

```
计算并行度 ↑  →  Tile 数量 ↑  →  NoC 流量 ↑  →  通信开销 ↑
             →  PE 数量 ↑   →  局部通信 ↑  →  功耗 ↑

这个 trade-off 是 MNSIM 设计空间探索的核心目标函数之一
```

---

## 6. 映射与调度模块

映射与调度是连接 NN 算法和 PIM 硬件的桥梁，直接决定 PPA 和精度的实际表现。

### 6.1 卷积层的映射策略

**权重展开**：
```
CONV 层权重 W[Cout × Cin × K × K]
    │ reshape
    ▼
W'[Cout × (Cin×K×K)]    ← 2D 矩阵

设 D = Cin×K×K（输入维度）
```

**分配逻辑**：
```
需要的 Array 列数 = ceil(D / ArrayRow)          （行切，沿输入维度）
需要的 Array 行数 = ceil(Cout / ArrayCol)        （列切，沿输出维度）
需要的 PE 数     = ceil(D / ArrayRow) × ceil(Cout / ArrayCol)
需要的 Tile 数   = ceil(PE 总数 / PENumPerTile)
```

### 6.2 Tile Connection Graph（TCG）

TCG 是 MNSIM 2.0 映射模块的核心数据结构：

```python
# MNSIM/Mapping_Model/Tile_connection_graph.py
class TCG:
    def __init__(self, NetStruct, SimConfig_path):
        # 解析 NN 结构
        self.net_structure = NetStruct
        # 读取硬件配置
        self.hw_config = SimConfig(SimConfig_path)
        # 构建 Tile 分配图
        self.tile_graph = self._build_graph()
    
    def _build_graph(self):
        # 对每一层 NN 计算所需 Tile 数量
        # 建立 Tile 间的数据依赖边
        # 分配 Tile ID 并记录映射关系
        pass
```

TCG 的输出是一个**有向图**：
- 节点 = 某层某个 Tile
- 有向边 = 数据流方向（部分和传递方向）
- 边权重 = 通信数据量

### 6.3 调度策略

MNSIM 2.0 支持通用调度描述接口，目前实现的主要策略：

| 策略 | 说明 | 优势 |
|------|------|------|
| Weight-Stationary (WS) | 权重固定在阵列，输入和输出流动 | 权重访问能耗最低 |
| Layer-by-Layer | 逐层执行，层间流水 | 实现简单，内存占用可控 |
| Pipeline | 层间流水线，提高吞吐 | 延迟隐藏，提升利用率 |

---

## 7. 算法层：精度仿真与训练量化流

### 7.1 非理想性注入机制

精度仿真通过在前向推断中注入多种非理想性因素来模拟真实 PIM 的精度损失：

#### 7.1.1 完整精度仿真流程

```
权重矩阵 W
│
├─→ 按 ArrayRow × ArrayCol 分块（weight splitting）
│
▼
各子块权重
│
├─→ [Device Variation] G_actual ~ N(G_target, σ²)
├─→ [Stuck-at Fault (SAF)] 部分 cell 固定在 Ron 或 Roff
├─→ [R-ratio 变化] 高低阻态比值退化
├─→ [ADC 量化] n-bit 均匀量化截断
│
▼
含噪声的等效权重
│
├─→ 与输入激活进行 MVM
├─→ 加法器树合并部分和
├─→ 激活函数
│
▼
下一层输入（误差向后传播）
│
▼
最终 Top-1 精度
```

#### 7.1.2 代码中的非理想性开关

```python
# main.py 中的命令行参数控制
parser.add_argument("-SAF",  "--enable_SAF",       default=True)   # Stuck-at Fault
parser.add_argument("-Var",  "--enable_variation",  default=False)  # 器件变化
parser.add_argument("-Rrat", "--enable_R_ratio",    default=False)  # 阻态比值

# 精度评估调用
__TestInterface.set_net_bits_evaluate(
    weight_2,
    adc_action='SCALE',
    is_Variation=args.enable_variation,
    is_SAF=args.enable_SAF,
    is_Rratio=args.enable_R_ratio
)
```

#### 7.1.3 各非理想因素的影响特征

| 非理想性 | 影响类型 | 对精度影响 | MNSIM 建模方式 |
|---------|---------|-----------|--------------|
| Device Variation | 随机噪声 | 每次推断随机波动 | 高斯分布 N(0, σ²) |
| Stuck-at Fault | 系统性偏差 | 固定精度损失 | 随机选取 SAFRatio 比例的 cell |
| ADC 量化 | 截断误差 | 位数越低损失越大 | 均匀量化 |
| IR Drop | 空间相关偏差 | 大阵列边缘精度差 | 简化解析式 |

### 7.2 PIM 导向训练与量化

MNSIM 2.0 集成了一套完整的 PIM-aware 训练流程，使 NN 模型能更好地适应 PIM 硬件的约束：

#### 7.2.1 权重拆分感知训练

```
训练时的关键操作：
  根据 ArrayRow × ArrayCol 大小对权重矩阵分块
  在每个子块上独立进行量化（而非全局量化）
  引入 ADC 量化误差到训练 loss
  → 训练出的权重天然适应 PIM 分块执行模式
```

#### 7.2.2 能量正则化训练（Energy-Aware Regularization）

```python
# 将硬件能量估计引入训练损失函数
loss_total = loss_cross_entropy + λ × loss_energy

loss_energy = Σ_layer Σ_weight |W_ij|    ← 权重绝对值越大，存储能耗越高
```

物理含义：大电导值（对应大权重）需要更多编程脉冲，能耗更高，正则化鼓励稀疏小权重。

#### 7.2.3 混合精度量化

不同层对精度的敏感度不同，MNSIM 2.0 支持逐层分配不同的量化位宽：

```
敏感层（如第一层、最后一层）→ 高位宽（8-bit）
不敏感层（中间层）→ 低位宽（2-4 bit）

评估依据：基于 Hessian 矩阵或激活范围分析
```

#### 7.2.4 非均匀激活量化

针对输出激活值分布不均匀的问题（长尾分布），使用非均匀量化：

```
均匀量化：等间距划分 → 尾部精度差
非均匀量化：基于数据分布自适应划分
  → 集中精度在高密度区域
  → 降低对 ADC 分辨率的要求
```

---

## 8. 闭环反馈机制与代码实现

### 8.1 反馈循环的本质

MNSIM 2.0 的反馈不是运行时动态反馈，而是一个**设计迭代闭环**：

```
迭代流程：
  Step 1：设定初始硬件配置（SimConfig.ini）
  Step 2：运行硬件性能建模 → 得到 array_size, adc_bits 等约束
  Step 3：这些约束传入训练/量化流 → 优化 NN 模型
  Step 4：优化后的 NN 模型重新进行精度仿真
  Step 5：更新硬件配置（如发现 ADC 分辨率不够）→ 回到 Step 2
```

### 8.2 代码中的双模块共享配置

反馈的实现机制是：**两个独立模块共享同一套 SimConfig.ini 配置文件**。

```python
# main.py 核心结构
SimConfig_path = "SimConfig.ini"   # 统一配置源

# 模块1：NN 训练/精度仿真
__TestInterface = TrainTestInterface(
    network_module=args.NN,
    SimConfig_path=SimConfig_path,    ← 读取 hw 约束
    weights_file=args.weights
)

# 模块2：硬件性能建模
__latency = Model_latency(
    NetStruct=structure_file,
    SimConfig_path=SimConfig_path,    ← 同一个配置
    TCG_mapping=TCG_mapping
)
__area   = Model_area(NetStruct=..., SimConfig_path=SimConfig_path, ...)
__power  = Model_inference_power(NetStruct=..., SimConfig_path=SimConfig_path, ...)
__energy = Model_energy(NetStruct=..., SimConfig_path=SimConfig_path, ...)
```

**反馈的代码路径**：当用户发现精度不达标时，修改 `SimConfig.ini`（例如增大 ADC 位宽），重新运行即完成一次设计迭代。

### 8.3 精度仿真中的误差传播

误差在层间传播的机制：

```python
# 伪代码：层间误差传播
def forward_with_nonideality(model, input, config):
    x = input
    for layer in model.layers:
        # 1. 获取该层量化权重
        W_quant = quantize(layer.weight, bits=config.weight_bits)
        
        # 2. 注入器件变化
        W_noisy = W_quant + gaussian_noise(sigma=config.variation)
        
        # 3. 注入 Stuck-at Fault
        W_noisy = apply_SAF(W_noisy, ratio=config.saf_ratio)
        
        # 4. 执行（含噪声的）MVM
        output = W_noisy @ x
        
        # 5. ADC 量化输出
        x = quantize(output, bits=config.adc_bits)
    
    return x    # 最终精度由此 x 与真实标签比较得出
```

---

## 9. 代码结构详解

### 9.1 目录结构

```
MNSIM-2.0/
│
├── main.py                          # 主入口，串联所有模块
├── SimConfig.ini                    # 硬件配置文件（用户主要修改此处）
├── techfile.txt                     # 器件/电路参考数据库（离线SPICE结果）
├── MNSIM_manual.pdf                 # 用户手册
│
└── MNSIM/
    ├── Interface/                   # NN 模型接口层
    │   ├── TrainTestInterface.py    # 训练/测试/精度评估入口
    │   ├── cifar10.py               # 数据集接口
    │   └── Network_DEFINE/          # NN 结构定义（vgg8等）
    │
    ├── Accuracy_Model/              # 精度仿真核心
    │   ├── Accuracy_evaluation.py   # 精度评估主逻辑
    │   └── Weight_update.py         # 非理想性注入（variation, SAF）
    │
    ├── Mapping_Model/               # 映射与调度
    │   ├── Tile_connection_graph.py # TCG：NN层→Tile映射
    │   └── Behavior_mapping.py      # 具体行为级映射实现
    │
    ├── Hardware_Model/              # 硬件层次模型
    │   ├── crossbar.py              # Memory Array（统一模型核心）
    │   ├── PE.py                    # Processing Element
    │   ├── Tile.py                  # Tile
    │   └── SimConfig.py             # 配置文件解析器
    │
    ├── Latency_Model/               # 延迟建模
    │   ├── Model_latency.py         # 整体延迟汇总
    │   ├── Tile_latency.py          # Tile 级延迟
    │   └── PE_latency.py            # PE 级延迟
    │
    ├── Area_Model/                  # 面积建模
    │   ├── Model_Area.py
    │   └── Tile_Area.py
    │
    ├── Power_Model/                 # 功耗建模
    │   ├── Model_inference_power.py
    │   └── Tile_inference_power.py
    │
    └── Energy_Model/                # 能量建模
        └── Model_energy.py
```

### 9.2 核心入口 main.py

```python
# main.py 完整执行流程（简化）

def main():
    # 1. 解析命令行参数
    args = parser.parse_args()
    
    # 2. 初始化 NN 接口（加载网络结构和权重）
    __TestInterface = TrainTestInterface(
        network_module=args.NN,
        dataset_module='MNSIM.Interface.cifar10',
        SimConfig_path=args.hardware_description,
        weights_file=args.weights,
        device=args.device
    )
    
    # 3. 获取网络结构文件（用于硬件建模）
    structure_file = __TestInterface.get_structure()
    
    # 4. 构建 Tile Connection Graph（映射）
    TCG_mapping = TCG(NetStruct=structure_file, 
                      SimConfig_path=args.hardware_description)
    
    # 5. 硬件性能建模（可选）
    if not args.disable_hardware_modeling:
        __latency = Model_latency(structure_file, SimConfig_path, TCG_mapping)
        __latency.model_latency_output(...)
        
        __area = Model_area(structure_file, SimConfig_path, TCG_mapping)
        __area.model_area_output(...)
        
        __power = Model_inference_power(structure_file, SimConfig_path, TCG_mapping)
        __power.model_power_output(...)
        
        __energy = Model_energy(structure_file, SimConfig_path, TCG_mapping, 
                                __latency, __power)
        __energy.model_energy_output(...)
    
    # 6. 精度仿真（可选）
    if not args.disable_accuracy_simulation:
        # 原始精度（无PIM非理想性）
        print("Original accuracy:", 
              __TestInterface.origin_evaluate(method='FIX_TRAIN', 
                                              adc_action='SCALE'))
        
        # PIM 实际精度（含非理想性）
        weight_2 = __TestInterface.get_weights()
        print("PIM-based accuracy:", 
              __TestInterface.set_net_bits_evaluate(
                  weight_2, adc_action='SCALE',
                  is_Variation=args.enable_variation,
                  is_SAF=args.enable_SAF,
                  is_Rratio=args.enable_R_ratio
              ))
```

### 9.3 SimConfig.ini 配置系统

这是用户与 MNSIM 2.0 交互的主要界面：

```ini
[Crossbar]
ArrayRow       = 128      # 阵列行数
ArrayCol       = 128      # 阵列列数
SubarrayNum    = 1        # 子阵列数（1=模拟PIM）
Weight_Precision = 4      # 权重位宽
ADC_Precision  = 8        # ADC 位宽
DAC_Precision  = 4        # DAC 位宽

[Device]
Device_Name    = RRAM
Device_Level   = 2        # 器件电平数（= 2^CellBit）
SAF_ratio      = 0.01     # Stuck-at Fault 比例
Device_Variation = 0.1    # 电导变化标准差

[Architecture]
BankNum        = 1
TileNumPerBank = 16
PENumPerTile   = 12
ArrayNumPerPE  = 8

[Buffer]
InputBufferSize  = 16384
OutputBufferSize = 16384

[NoC]
Noc_Bandwidth  = 16       # bytes/cycle
```

### 9.4 关键模块代码路径

**精度仿真的核心调用链**：

```
TrainTestInterface.set_net_bits_evaluate()
    └── Weight_update.weight_variation_add()   ← 注入 variation
        └── Weight_update.SAF_analysis()        ← 注入 SAF
            └── Accuracy_evaluation.evaluate()  ← 前向推断+精度计算
```

**硬件延迟的核心调用链**：

```
Model_latency.model_latency_output()
    └── Tile_latency.tile_latency()
        ├── PE_latency.pe_latency()
        │   └── crossbar.xbar_latency()         ← 查 techfile.txt
        ├── buffer_latency()                    ← CACTI 类解析模型
        └── noc_latency()                       ← 曼哈顿距离估计
```

---

## 10. PPA 建模方法

### 10.1 延迟模型

整体延迟计算：

```
T_total = Σ_layer max(T_compute[layer], T_comm[layer])

其中：
T_compute[layer] = T_xbar × ceil(D/ArrayRow) × ceil(Cout/ArrayCol)
                   ÷ PENumPerTile × TileNumPerBank    （流水线并行）

T_xbar =  DAC_latency × InputPrecision    （逐位输入）
        + ADC_latency                      （一次读出）
        + Adder_tree_latency               （合并部分和）

T_comm[layer] = data_volume / NoC_bandwidth × hop_count
```

流水线建模：MNSIM 2.0 支持层间流水线（inter-layer pipeline），即当前层计算与下一层数据传输重叠，用 `max()` 取计算和通信的瓶颈。

### 10.2 面积模型

```
A_total = N_tile × (N_PE × (N_Array × A_xbar + A_PE_logic)
                  + A_buffer + A_tile_ctrl)
        + A_noc + A_global_ctrl

A_xbar = A_cell × ArrayRow × ArrayCol    （cell 面积）
       + A_DAC × ArrayRow                 （DAC 面积）
       + A_ADC × ArrayCol                 （ADC 面积）
       + A_WL_driver + A_decoder          （外围电路）
```

### 10.3 功耗与能量模型

```
P_dynamic = P_xbar_compute + P_buffer_access + P_noc

P_xbar = P_DAC + P_ADC + P_wire_charging + P_cell_read
P_DAC  ∝ 2^DAC_bits × f × Vdd²
P_ADC  ∝ 2^ADC_bits × f × Vdd²    （SAR ADC 功耗模型）

P_static = N_cell × P_leakage_per_cell    （非易失器件较小）

E_total = P_dynamic × T_total + P_static × T_total
```

---

## 11. 与 NeuroSim 的学术比较

| 维度 | MNSIM 2.0 | NeuroSim / DNN+NeuroSim |
|------|-----------|------------------------|
| **开发机构** | 清华大学 NICS Lab | 亚利桑那州立大学（Shimeng Yu 课题组）|
| **建模粒度** | 行为级（Behavior-Level）| 电路宏模型级（Circuit-Level Macro）|
| **覆盖范围** | 模拟 + 数字 PIM（统一框架）| 主要面向模拟CIM，后续扩展数字 |
| **验证精度** | 3.8–5.5%（实际流片宏单元）| <1%（经PDK校准后）|
| **软件集成** | 集成完整训练+量化流 | 与 PyTorch 集成，侧重推断评估 |
| **调度灵活性** | 通用调度接口 | 相对固定数据流 |
| **主要优势** | 系统级 DSE、软硬件协同、统一模型 | 电路精度高、广泛工业用户（Intel/Samsung）|
| **主要局限** | 通信理想化、Transformer 支持弱 | 建模开销大、扩展性有限 |

**核心哲学差异**：NeuroSim 更适合**电路级精度验证和单器件特性分析**；MNSIM 2.0 更适合**跨类型 PIM 架构的系统级 DSE 和算法-硬件协同优化**。

---

## 12. 验证方法与精度

MNSIM 2.0 使用**两个实际流片的 PIM 宏单元**进行验证：

| 验证对象 | 工艺 | 阵列类型 | 建模误差 |
|---------|------|---------|---------|
| PIM Macro 1 | 定制工艺 | 模拟 RRAM crossbar | ~3.8% |
| PIM Macro 2 | 定制工艺 | 数字 SRAM-CIM | ~5.5% |

**误差来源分析**：
1. 解析模型对非线性效应的线性化近似（~2%）
2. IR drop 建模的激活模式无关假设（~1.5%）
3. ADC/DAC 实际非线性被忽略（~1%）
4. 温度效应未建模（<0.5%）

---

## 13. 可优化方向全景分析（研究机会）

> 本章节是本报告的核心研究价值所在，总结了基于 MNSIM 2.0 可以开展的所有改进方向，按层次组织，适合直接用于论文 Motivation / Related Work 章节。

---

### 13.1 物理器件层优化

#### 🔴 高优先级：非线性 IV 模型

**现状**：MNSIM 使用线性欧姆定律 `I = G × V`，隐含 G 为常数的假设。

**真实情况**：RRAM 的 IV 特性在工作电压范围内呈现明显非线性，典型物理模型包括：

```
双曲正弦模型：  I = I₀ × sinh(V / V₀)
Simmons 隧穿：  I = A × V × exp(−B/V)
Power Law：     I = G₀ × V^α  (α ≠ 1)
```

**影响**：
- 高压输入时，实际电流显著高于线性估计 → 功耗被低估
- MVM 结果出现非线性偏差 → 精度被高估
- 不同输入 pattern 的误差不一致 → 精度方差被低估

**改进方案**：

```python
# 替换核心 MVM 计算函数
class NonlinearMemArray:
    def compute(self, G_matrix, V_WL, model='sinh'):
        if model == 'sinh':
            return G_matrix * np.sinh(V_WL / self.V0)
        elif model == 'lookup':
            return self.IV_table.query(G_matrix, V_WL)
        elif model == 'power_law':
            return G_matrix * (V_WL ** self.alpha)
```

#### 🔴 高优先级：动态电导变化模型

**现状**：σ（variation）是固定常数，与任何物理量无关。

**真实情况**：

```
σ(G) = f(n_write, T, t_retention, G_state)

具体依赖：
  - 写次数越多 (n_write ↑) → σ ↑（疲劳效应）
  - 温度越高 (T ↑) → σ ↑（热激活）
  - 保留时间越长 (t ↑) → G 漂移（非高斯）
  - LRS/HRS 的 σ 不同（非对称）
```

**改进方案**：引入状态方程 `dG/dt = f(V, G, T)`，用 Arrhenius 模型描述温度依赖性。

#### 🟡 中优先级：自热效应（Self-Heating）

**现状**：温度完全不建模，假设室温恒定。

**真实情况**：
- 大规模计算时，功耗密度导致局部温升可达 30-50°C
- 温升改变 RRAM 电导、加速 retention 漂移、影响 ADC 精度
- 不同位置的 cell 温度不同（空间不均匀）

**改进方案**：集成热阻网络（Thermal Resistance Network）模型。

#### 🟡 中优先级：Stuck-at Fault 的时变模型

**现状**：SAF 比例是固定参数，不随使用时间变化。

**真实情况**：SAF 比例随写次数增加而增大，遵循 Weibull 分布：

```
P_SAF(n) = 1 - exp(-(n / n_char)^β)
```

#### 🟡 中优先级：读扰动（Read Disturb）累积

**现状**：完全不建模。

**真实情况**：频繁读操作会累积地改变 RRAM 状态，导致推断精度随推断次数缓慢下降。这在边缘推断长期部署场景中不可忽视。

---

### 13.2 电路外围层优化

#### 🔴 高优先级：ADC 非理想性建模

**现状**：均匀量化，无失调、无增益误差、无 DNL/INL。

**真实情况**：真实 SAR ADC 有以下非理想性：

```
DNL（微分非线性）：每个量化步长不等宽
INL（积分非线性）：累积误差导致系统性偏差
Offset Error：ADC 输入范围偏移
Gain Error：量化斜率偏差
Thermal Noise：随机噪声底限
```

**影响**：ADC 非理想性导致**系统性偏差**而非随机噪声，精度损失的分布特征完全不同。

#### 🔴 高优先级：IR Drop 的激活模式依赖

**现状**：IR drop 用平均电流的简化解析式，与具体输入无关。

**真实情况**：
- 不同输入导致不同的 BL 电流分布
- IR drop 是输入 pattern 的强相关函数
- 对某些输入 pattern 误差极大（worst-case），对另一些几乎无误差（best-case）
- 这导致精度具有**输入依赖性**，是 MNSIM 完全忽略的效应

**改进方案**：引入基于有限元或等效电路的 2D IR drop 计算模型。

#### 🟡 中优先级：BL/WL 寄生电容对延迟的影响

**现状**：延迟模型中 BL 充放电基于理想电容值。

**真实情况**：随阵列规模增大，BL 寄生电容非线性增大（布线密度效应），导致大阵列的实际延迟远高于线性外推值。

---

### 13.3 架构与调度层优化

#### 🔴 高优先级：数据依赖的通信延迟建模

**现状**：假设完全异步通信，数据计算完立即可用。

**真实情况**：
- ResNet 的残差连接需要等待两条并行路径都完成才能做加法
- Transformer 的 attention 计算 QKV 三者有数据依赖
- MNSIM 对这类有等待关系的结构**严重低估延迟**（ResNet 误差可达 53%）

#### 🔴 高优先级：稀疏性利用

**现状**：不支持稀疏计算，零权重仍然消耗计算资源。

**真实情况**：
- 经过剪枝的 NN 有 50%-90% 的权重为零
- 稀疏 PIM 可通过门控（gating）跳过零值计算
- MNSIM 对稀疏模型的能耗预测严重偏高

#### 🟡 中优先级：可重构数据流建模

**现状**：PE 功能固定（只能做 pooling 或 MVMUL，不能组合）。

**真实情况**：现代 PIM 芯片（如 PRIME、ISSAC 后继者）支持可重构数据流，PE 的计算序列是可编程的。固定数据通路限制了 MNSIM 对新型芯片架构的建模能力。

#### 🟡 中优先级：Transformer/LLM 支持

**现状**：主要支持 CNN，对 Transformer 的支持很弱。

**真实情况**：
- Attention 的 Q×K^T 是动态矩阵乘（不是权重静止的），PIM 的优势不同于 CNN
- KV Cache 的存储访问模式特殊
- 大模型的层数多、权重大，需要多 Bank 协作，通信开销建模完全不同

---

### 13.4 算法与训练层优化

#### 🟡 中优先级：先进量化方法集成

**现状**：主要支持均匀量化（PTQ/QAT 的基础版本）。

**可集成的先进方法**：
- **GPTQ**：基于 Hessian 的权重量化，大模型低精度推断
- **AWQ**：激活感知量化，保护关键通道
- **SmoothQuant**：权重/激活联合平滑，改善量化难度
- **ADAROUND**：自适应舍入，减少量化误差累积

#### 🟡 中优先级：更真实的 Noise-Aware Training

**现状**：noise injection 只注入简单高斯噪声。

**改进方向**：
- 将非线性 IV 的误差分布注入训练（与物理层改进联动）
- 使用真实器件测量的噪声分布（非高斯）
- 对抗式噪声训练（worst-case noise）

---

### 13.5 系统 DSE 层优化（CustomSimLab 方向）

这是从 MNSIM 出发，构建全新系统框架的核心机会。

#### 🔴 高优先级：代理模型（Surrogate Model）加速

**现状**：MNSIM 每次仿真都需要完整执行所有模块，没有缓存或学习机制。

**改进方案**：

```python
# 贝叶斯优化 + 高斯过程代理模型
from sklearn.gaussian_process import GaussianProcessRegressor

class SurrogateAcceleratedDSE:
    def __init__(self, simulator):
        self.sim = simulator          # custom-sim
        self.gp = GaussianProcessRegressor()
        self.X_obs = []               # 已仿真的设计点
        self.Y_obs = []               # 对应 PPA+精度结果
    
    def suggest_next_design(self):
        # 最大化 Expected Improvement
        return maximize_EI(self.gp, self.X_obs)
    
    def run_iteration(self, x):
        y = self.sim.evaluate(x)     # 真实仿真（昂贵）
        self.X_obs.append(x)
        self.Y_obs.append(y)
        self.gp.fit(self.X_obs, self.Y_obs)
        return y
```

**预期收益**：从穷举 10 万次仿真 → 贝叶斯优化 200-500 次仿真找到接近最优解。

#### 🔴 高优先级：多目标 Pareto 前沿探索

**现状**：MNSIM 只能给出单一配置的 PPA+精度，没有多目标优化能力。

**改进方案**：集成 NSGA-II/NSGA-III，输出 PPA 与精度的 Pareto 前沿，让设计者从 Pareto 集合中选择最优折中点。

#### 🟡 中优先级：迁移学习辅助的跨场景 DSE

**场景**：换一个工艺节点或换一个 NN 模型时，之前积累的仿真数据能否复用？

**方案**：Meta-Learning / Transfer BO，将旧任务的 GP 先验迁移到新任务，大幅减少冷启动仿真次数。

#### 🟡 中优先级：物理信息约束的设计空间剪枝

**思想**：用物理规律（如"增大 ArrayRow 必然导致 IR drop 增大"）提前剪枝不可行的设计点，减少无效仿真。

```python
# 物理约束剪枝示例
def is_feasible(config):
    # 约束1：IR drop < 10% Vdd
    if estimated_ir_drop(config.array_row, config.input_current) > 0.1 * Vdd:
        return False
    # 约束2：ADC 精度足以区分最小电导差
    if config.adc_bits < required_adc_bits(config.weight_bits, config.variation):
        return False
    return True
```

---

### 优化方向优先级总结

| 优先级 | 方向 | 预期影响 | 工程难度 |
|--------|------|---------|---------|
| 🔴 最高 | 非线性 IV 模型 | 精度预测误差降低 2-3% | 中 |
| 🔴 最高 | 动态电导变化 | 长期精度预测更真实 | 中高 |
| 🔴 最高 | ADC 非理想性 | 系统性偏差建模 | 中 |
| 🔴 最高 | IR Drop 激活依赖 | 大阵列精度预测改善 | 高 |
| 🔴 最高 | Surrogate Model DSE | 探索效率提升 100-500x | 中 |
| 🔴 最高 | 多目标 Pareto 优化 | 设计决策质量提升 | 中 |
| 🟡 中 | 自热效应 | 功耗建模完整性 | 高 |
| 🟡 中 | 稀疏性支持 | 剪枝模型能耗预测准确 | 中 |
| 🟡 中 | Transformer 支持 | 覆盖 LLM 场景 | 高 |
| 🟡 中 | 先进量化方法 | 精度上限提升 | 中 |

---

## 14. 总结：MNSIM 2.0 的设计权衡地图

MNSIM 2.0 在每一个关键设计节点上都做出了**"仿真速度 vs. 物理保真度"**的权衡选择：

| 设计决策 | MNSIM 的选择 | 代价 | 你的机会 |
|---------|------------|------|---------|
| 建模粒度 | 行为级 | 3.8-5.5% 误差 | 在关键路径引入更精确模型 |
| IV 模型 | 线性欧姆定律 | 忽略非线性 | 替换为 sinh/lookup 模型 |
| 器件变化 | 固定高斯噪声 | 忽略动态变化 | 引入状态方程 |
| IR Drop | 平均电流解析式 | 忽略激活模式 | 2D 有限元/等效电路 |
| 通信模型 | 静态解析 + 理想异步 | 无动态调度冲突 | 事件驱动或数据依赖建模 |
| DSE 能力 | 无，手动配置 | 无法自动探索 | CustomSimLab 的核心价值 |
| 验证方式 | 2 个流片宏单元 | 覆盖范围有限 | 更多工艺/器件验证 |

**最终结论**：MNSIM 2.0 是一个**工程上成熟、学术上有贡献**的 PIM 仿真工具，但其物理建模的保真度存在系统性的简化假设，这些假设在**大阵列、非理想器件、现代 NN 架构（Transformer）、以及设计空间自动探索**等场景下会导致显著误差或功能缺失。这正是 CustomSimLab 系统的研究价值所在。

---

*报告生成时间：2026年4月*
*基于：IEEE TCAD 2023 论文 + GitHub thu-nics/MNSIM-2.0 代码*
*作者：基于课题组研究需求整理*
