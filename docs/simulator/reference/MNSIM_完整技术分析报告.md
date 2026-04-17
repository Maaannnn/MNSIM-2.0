# 参考分析：MNSIM-2.0 完整技术分析报告

这篇文档保留为技术细节参考，不作为当前组会或执行路线的主入口。

> **综合版** | 结合论文（IEEE TCAD 2023）、源码逐行分析与可优化方向全景
>
> 论文全称：*MNSIM 2.0: A Behavior-Level Modeling Tool for Processing-In-Memory Architectures*  
> DOI: 10.1109/TCAD.2023.3251696  
> 代码仓库：GitHub thu-nics/MNSIM-2.0

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [系统全局设计哲学](#2-系统全局设计哲学)
3. [整体架构总览](#3-整体架构总览)
4. [层次化硬件建模（完整六层）](#4-层次化硬件建模完整六层)
   - 4.1 [全局系统层（Layer 0）](#41-全局系统层layer-0)
   - 4.2 [PIM Bank / 架构层（Layer 1）](#42-pim-bank--架构层layer-1)
   - 4.3 [器件层 Device（Layer 2）](#43-器件层-devicelayer-2)
   - 4.4 [接口层 ADC / DAC（Layer 3）](#44-接口层-adc--daclayer-3)
   - 4.5 [Crossbar 阵列层（Layer 4）](#45-crossbar-阵列层layer-4)
   - 4.6 [处理单元层 PE（Layer 5）](#46-处理单元层-pelayer-5)
   - 4.7 [数字辅助模块](#47-数字辅助模块)
   - 4.8 [Tile 层（Layer 6）](#48-tile-层layer-6)
5. [层间通信机制](#5-层间通信机制)
6. [映射与调度模块](#6-映射与调度模块)
7. [算法层：精度仿真与训练量化流](#7-算法层精度仿真与训练量化流)
8. [闭环反馈机制与代码实现](#8-闭环反馈机制与代码实现)
9. [代码结构详解](#9-代码结构详解)
10. [PPA 建模方法](#10-ppa-建模方法)
11. [SimConfig.ini 完整参数说明](#11-simconfigini-完整参数说明)
12. [已知代码缺陷与注意事项](#12-已知代码缺陷与注意事项)
13. [与 NeuroSim 的学术比较](#13-与-neurosim-的学术比较)
14. [验证方法与精度](#14-验证方法与精度)
15. [可优化方向全景分析（研究机会）](#15-可优化方向全景分析研究机会)
16. [总结：MNSIM 2.0 的设计权衡地图](#16-总结mnsim-20-的设计权衡地图)

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

PIM 架构的设计面临三大挑战：

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

硬件性能结果反馈给算法优化，算法优化结果再送回硬件评估。这是一个**真实的设计迭代闭环**，而非单向流水线：

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
│  │   System → Bank → Tile → PE → Crossbar → Device         │  │
│  │                                                          │  │
│  │   ├── Latency Model    ├── Area Model                   │  │
│  │   ├── Power Model      └── Energy Model                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  配置输入: SimConfig.ini        输出: PPA + Accuracy            │
└─────────────────────────────────────────────────────────────────┘
```

**Python 类继承关系（硬件模型层）：**

```python
device
  └── crossbar(device)
        └── ProcessElement(crossbar, DAC, ADC)
              └── tile(ProcessElement)
```

> **注**：代码中没有单独的 `chip` 类，芯片级别通过 `SimConfig.ini` 的 `Tile_Num` 参数和 `TCG` 来表达。代码中也没有独立的 `bank` 类，与 Bank 最接近的实体是 `Architecture level` 下的 `Tile_Num` 网格。

---

## 4. 层次化硬件建模（完整六层）

### 4.1 全局系统层（Layer 0）

**对应代码**：`main.py`，`SimConfig.ini`

全局系统由三部分构成：CPU + DRAM + PIM 芯片。

- **CPU**：负责 NN 映射结果生成、权重部署到 PIM 存储器、PIM 控制器初始化
- **DRAM**：片外大容量存储，存放待部署的权重和输入图像
- **PIM 芯片**：被 CPU 唤醒后，从 DRAM 读取输入，由内部控制器管理整个 NN 计算

关键设计决策：PIM 内部的计算完全独立于 CPU，CPU 只负责启动和收结果。这个"批量计算"模式使得**权重只需要加载一次**，对能效极为有利。

---

### 4.2 PIM Bank / 架构层（Layer 1）

**对应代码**：`MNSIM/Mapping_Model/Tile_connection_graph.py`，`SimConfig.ini` 的 `[Architecture level]`

芯片架构层是整个 PIM 芯片最顶层的调度结构，无独立 Python 类，由 `SimConfig.ini` 的 `[Architecture level]` 参数和 TCG（Tile Connection Graph）映射引擎共同定义。

#### 配置参数

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `Buffer_Choice` | 1 | 全局缓冲类型：0=自定义，1=SRAM，2=DRAM，3=RRAM |
| `Buffer_Technology` | 90 nm | 全局缓冲工艺节点 |
| `Buffer_ReadPower` | 0 → 自动 | mW |
| `Buffer_WritePower` | 0 → 自动 | mW |
| `Buffer_Bitwidth` | 64 bit | 总线位宽 |
| `LUT_Capacity` | 1 Mb | 查找表容量 |
| `LUT_Area` | 0 → 自动 | mm² |
| `LUT_Power` | 0 → 自动 | mW |
| `LUT_Bandwidth` | 0 → 自动 | Mb/s |
| `Tile_Connection` | 2 | Tile 铺排拓扑：0=正常，1=蛇形，2=回字形，3=zigzag |
| `Tile_Num` | `64,64` | 芯片上 Tile 阵列规模（行,列）；0,0=默认 8×8 |

#### 算法配置

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `Weight_Polarity` | 1 | 权重极性处理方式（1或2） |
| `Simulation_Level` | 0 | 0=行为级（快）；1=估计级（需具体权重，慢但准） |
| `NoC_enable` | 0 | 0=不调用 BookSim；1=调用 BookSim 进行 NoC 仿真 |

#### TCG 映射流程

1. 对每个神经网络层计算所需 PE 数（`PEnum`）
2. 计算所需 Tile 数：`tilenum = ceil(PEnum / tile_PE_total_num)`
3. 用 `startid` 累加分配每层的 Tile 区间 `[startid, startid + tilenum)`
4. `mapping_matrix_gen()` 按拓扑策略生成 Tile 坐标到层 ID 的映射矩阵
5. `mapping_net()` 生成 `mapping_result[i][j] = layer_id`

#### 四种 Tile 铺排拓扑

```
Normal（0）:              Snake（1）:
 0  1  2  3               0  1  2  3
 4  5  6  7               7  6  5  4
 8  9  10 11              8  9  10 11

Hui（回字形，2）:          Zigzag（3）:
 0  1  2  3               0  3  4  7
11 12 13  4               1  2  5  6
10 15 14  5               ...
 9  8  7  6
```

**回字形（Hui）的物理含义**：相邻层的 Tile 在空间上紧邻，减少层间传输的 Manhattan 距离，适合层间通信密集的 CNN。

#### Tile 间传输距离计算

$$d_{inLayer}[l] = \text{Manhattan}(\text{最后一个 Tile of layer l}, \text{第一个 Tile of layer l})$$

$$d_{transLayer}[l] = \text{Manhattan}(\text{最后一个 Tile of layer l}, \text{第一个 Tile of layer l+1})$$

层间传输时间：

$$t_{transfer} = d_{transLayer}[l] \times \frac{N_{output\_channel} \times N_{output\_bits}}{BW_{inter\_tile}}$$

---

### 4.3 器件层 Device（Layer 2）

**文件**：`MNSIM/Hardware_Model/Device.py`  
**类**：`class device`

器件层是整个建模体系的物理基础，对应单个存储单元（Cell）的电学特性。

#### 通用参数（来自 `[Device level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Device_Tech` | `device_tech` | 130 | nm | 工艺节点 |
| `Device_Type` | `device_type` | `NVM` | — | 器件类型：`NVM` 或 `SRAM` |
| `Device_Area` | `device_area` | 1.44 | μm² | 单个存储单元面积（参考：RRAM 1.44 μm²@ISSCC） |
| `Read_Level` | `device_read_voltage_level` | 2 | — | 读电压档位数量 |
| `Read_Voltage` | `device_read_voltage` | `[0, 0.15]` | V | 各档读电压列表（长度 = Read_Level） |
| `Write_Level` | `device_write_voltage_level` | 2 | — | 写电压档位数量 |
| `Write_Voltage` | `device_write_voltage` | `[0, 3]` | V | 各档写电压列表 |
| `Read_Latency` | `device_read_latency` | 3.16 | ns | 单次读操作延迟（来源：NTHU ISSCC19） |
| `Write_Latency` | `device_write_latency` | 10 | ns | 单次写操作延迟 |

#### NVM 专属参数

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Device_Level` | `device_level` | 2 | — | 阻态档位数，SLC=2，MLC=4，TLC=8；weight_bit = log₂(Device_Level) |
| `Device_Resistance` | `device_resistance` | `[1e6, 1e4]` | Ω | 各阻态对应电阻值，从 HRS→LRS 排列 |
| `Device_Variation` | `decice_variation`（**拼写错误**） | 1 | % | 器件变异幅度，即 ΔR/R 的百分比 |
| `Device_SAF` | — | `[0.1, 0.1]` | % | Stuck-At-HRS 和 Stuck-At-LRS 的故障比例 |

#### SRAM 专属参数

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Read_Energy` | `device_read_energy` | 1.12e-15 | J | 每 bit 读能量 |
| `Write_Energy` | `device_write_energy` | 1.6e-15 | J | 每 bit 写能量 |

SRAM 分支等效阻值硬编码为 `device_resistance = [1.6e6, 1.6e6]`（HRS = LRS），`device_variation = 0`。

#### 支持的器件类型（设计空间）

| 器件 | 类型 | 存储机制 | 适用场景 |
|------|------|---------|---------|
| RRAM（HfOx/TaOx等）| 模拟PIM | 导电细丝阻变 | 最主流，非线性强 |
| PCM | 模拟PIM | 晶/非晶相变 | 多值存储精度好 |
| MRAM | 模拟/数字 | 磁隧道结 | 耐久性好 |
| Flash（NOR/NAND）| 模拟PIM | 浮栅电荷存储 | 成熟工艺 |
| SRAM | 数字PIM | 锁存器（6T） | 速度最快，面积最大 |

#### 物理建模：NVM 读功耗

**方法**：`calculate_device_read_power(self, R=None, V=None)`，采用欧姆热耗散模型 \(P = V^2 / R\)：

**等效电阻（调和加权，默认）：**

$$R_{eff} = \frac{R_{HRS} \cdot R_{LRS}}{0.67 \cdot R_{LRS} + 0.33 \cdot R_{HRS}}$$

> 物理含义：67% 时间处于 LRS（数据1），33% 时间处于 HRS（数据0）的加权调和平均阻

**等效读电压（RMS 加权，默认）：**

$$V_{eff} = \sqrt{0.9 \cdot V_{read,0}^2 + 0.1 \cdot V_{read,N-1}^2}$$

**读功耗：**

$$P_{device,read} = \frac{V_{eff}^2}{R_{eff}}$$

#### 物理建模：NVM 写功耗

**方法**：`calculate_device_write_power(self, R=None, V=None)`：

$$R_{write} = \sqrt{R_{HRS} \cdot R_{LRS}} \quad \text{（几何平均）}$$

$$V_{write} = \frac{V_{write,0} + V_{write,N-1}}{2} \quad \text{（算术平均）}$$

$$P_{device,write} = \frac{V_{write}^2}{R_{write}}$$

#### 物理建模：SRAM 功耗

不用 \(V^2/R\) 模型，使用每 bit 能量除以延迟：

$$P_{SRAM,read} = \frac{E_{read,per\_bit}}{t_{read\_latency}}$$

#### 电导 → 权重的映射关系

```
W_quant ∈ {0, 1, ..., 2^Pw - 1}（Pw 位量化权重）
    │
    ▼ 线性映射
G_target = G_min + W_quant × (G_max - G_min) / (2^Pw - 1)
    │
    ▼ 加入高斯噪声（device variation）
G_actual ~ N(G_target, σ²_device)   其中 σ = G_target × variation / 100
```

---

### 4.4 接口层 ADC / DAC（Layer 3）

接口层介于 Crossbar 与 PE 之间，负责模拟域与数字域的相互转换。

#### 4.4.1 DAC（数模转换器）

**文件**：`MNSIM/Hardware_Model/DAC.py`  
**类**：`class DAC`

DAC 将数字激活值转换为施加在 Crossbar 字线（WL）上的模拟电压。

**配置参数（来自 `[Interface level]`）：**

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `DAC_Choice` | 1 | 选择预定义设计（1–7）或 -1（用户自定义） |
| `DAC_Area` | 0 | 0 = 使用内置表格；否则用户指定（μm²） |
| `DAC_Precision` | 0 | 0 = 内置表格；否则用户指定（bit） |
| `DAC_Power` | 0 | 0 = 内置表格；否则用户指定（W） |
| `DAC_Sample_Rate` | 0 | 0 = 内置表格；否则用户指定（GSamples/s） |

**数字 PIM 特殊处理（`PIM_type == 1`）**：强制 `DAC_choice = 1`（1-bit DAC，对应一位驱动电平）。

**七种预定义 DAC 设计查找表（来源：ISAAC 论文）：**

| Choice | Precision (bit) | Area (μm²) | Power (W) | Sample Rate (GSamples/s) |
|---|---|---|---|---|
| 1（默认） | 1 | 0.166 | 3.9×10⁻⁶ | 1 |
| 2 | 2 | 0.332 | 7.8×10⁻⁶ | 1 |
| 3 | 3 | 0.664 | 1.56×10⁻⁵ | 1 |
| 4 | 4 | 1.328 | 3.12×10⁻⁵ | 1 |
| 5 | 6 | 5.312 | 1.248×10⁻⁴ | 1 |
| 6 | 8 | 21.248 | **0.4992**（⚠️ 疑似缺 ×10⁻³） | 1 |
| 7 | 1 | 0.166 | 3.9×10⁻⁶ | 1 |

**延迟与能量公式：**

$$t_{DAC} = \frac{1}{f_{sample}} \times (N_{bit} + 2)$$

$$E_{DAC} = t_{DAC} \times P_{DAC}$$

#### 4.4.2 ADC（模数转换器）

**文件**：`MNSIM/Hardware_Model/ADC.py`  
**类**：`class ADC`

ADC 将 Crossbar 位线（BL）的模拟电流/电压求和结果量化为数字值。

**配置参数（来自 `[Interface level]`）：**

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `ADC_Choice` | 6 | 选择预定义设计（1–9）或 -1（用户自定义） |
| `ADC_Area` | 0 | 0 = 内置表格；否则用户指定（μm²） |
| `ADC_Precision` | 0 | 0 = 内置表格；否则用户指定（bit） |
| `ADC_Power` | 0 | 0 = 内置表格；否则用户指定（W） |
| `ADC_Sample_Rate` | 0 | 0 = 内置表格；否则用户指定（Samples/s） |
| `ADC_Interval_Thres` | -1 | -1 = 自动生成；否则手动指定量化区间电压列表（V） |
| `Logic_Op` | -1 | 附加逻辑运算：-1无，0=AND，1=OR，2=XOR（数字 PIM 扩展） |

**数字 PIM 特殊处理**（`PIM_type == 1` 且 `ADC_choice != -1`）：强制 `ADC_choice = 8`（Sense Amplifier，1-bit 比较器）。

**附加逻辑面积（`Logic_Op` 非 -1 时）：**
- `Logic_Op = 0/1`：面积 += 17.28 × 0.18 μm²
- `Logic_Op = 2`：面积 += 19.2 × 0.18 μm²

**九种预定义 ADC 设计查找表：**

| Choice | Precision (bit) | Area (μm²) | Power (W) | Sample Rate (GSamples/s) | 类型 |
|---|---|---|---|---|---|
| 1 | 10 | 1600 | 6.92×10⁻³ | 1.5 | 高精度 SAR |
| 2 | 8 | 1200 | 2×10⁻³ | 1.28 | 通用 |
| 3 | 8 | 1650 | 4×10⁻³ | 1.1 | 通用 |
| 4 | 6 | 580 | 1.26×10⁻³ | 1 | 低功耗 |
| 5 | 8 | 1650 | 4×10⁻³ | 1.1 | 通用 |
| 6（**默认**） | 6 | 1650 | 1.26×10⁻³ | 1 | 通用 |
| 7 | 4 | 500 | 0.7×10⁻³ | 1 | 低精度 |
| 8 | 1 | 1 | 0.1086×15×10⁻⁶ | 1 | Sense Amplifier（数字 PIM） |
| 9 | 8 | 15899 | 8×0.0073×10⁻³ | 6 | 高速 |

**延迟公式（三种情况）：**

```python
if ADC_precision == 1:                          # Sense Amplifier：单周期
    ADC_latency = 1 / ADC_sample_rate
elif ADC_choice == 9:                           # 高速 ADC 特例
    ADC_latency = 1 / ADC_sample_rate * (2 ** ADC_precision)
else:                                           # 标准逐次逼近型（SAR）
    ADC_latency = 1 / ADC_sample_rate * (ADC_precision + 2)
```

**ADC 量化区间自动生成（`config_ADC_interval`）：**

当 `ADC_interval[0] == -1` 时，根据激活字线数 `WL_num`、读电压和器件电阻自动生成 `2^N - 1` 个区间边界。每级步长 `step = ceil(WL_num / 2^N)`，最大电压：

$$V_{max} = WL\_num \times \frac{V_{in,max}}{R_{LRS}} \times R_{load}$$

第 i 个区间边界（k = (i+1) × step）：

$$\text{interval}[i] = 0.5 \times \left[ \frac{(k-1)V_{in,max}}{R_{LRS}}R_s + \frac{(WL-k+1)V_{in,max}}{R_{LRS}}R_s + \frac{kV_{in,max}}{R_{LRS}}R_s + \frac{(WL-k)V_{in,0}}{R_{HRS}}R_s \right]$$

物理含义：按等间距激活字线数划分，使量化误差均匀分布。

---


### 4.5 Crossbar 阵列层（Layer 4）

**文件**：`MNSIM/Hardware_Model/Crossbar.py`  
**类**：`class crossbar(device)`

Crossbar 是存内计算的核心运算单元，用电阻阵列实现向量矩阵乘法（VMM）。

#### 4.5.1 配置参数（来自 `[Crossbar level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Xbar_Size` | `xbar_size = [xbar_row, xbar_column]` | `[256, 256]` | — | 阵列行数 × 列数 |
| `Subarray_Size` | `subarray_size` | 256 | rows | 子阵列行数（列数与 Crossbar 相同，`subarray_num = xbar_row / subarray_size`） |
| `Cell_Type` | `cell_type` | `1T1R` | — | `1T1R`（有选通管）或 `0T1R`（无选通管，有泄漏电流） |
| `Transistor_Tech` | `transistor_tech` | 130 | nm | 外围晶体管工艺节点 |
| `Wire_Resistance` | `wire_resistance` | -1 | Ω | 字/位线单位电阻，-1 = 默认 2.82 Ω（文献引用） |
| `Wire_Capacity` | `wire_capacity` | -1 | fF | 字/位线单位电容，-1 = 默认 1 fF（文献引用） |
| `Load_Resistance` | `xbar_load_resistance` | -1 | Ω | 位线负载电阻，-1 = √(R_HRS × R_LRS)（几何平均） |
| `Area_Calculation` | `area_calculation_method` | 0 | — | 0 = 用 Device_Area 计算；1 = 用工艺几何公式计算 |

#### 4.5.2 模拟 PIM 的计算语义

```
输入向量 x[N] ──DAC量化──> 电压向量 V[N]（施加到WL）
权重矩阵 W[M×N] ──编程──> 电导矩阵 G[M×N]

BL电流：I[M] = G[M×N] · V[N]    ← 欧姆定律，并行MVM

I[M] ──ADC量化──> 数字输出 O[M]
```

**关键假设（也是最大简化）**：G 是常数，I 与 V 线性相关。真实 RRAM 的 IV 曲线是非线性的。

#### 4.5.3 数字 PIM 的计算语义

```
O_j = Σ_{b=0}^{B-1} 2^b × Σ_{i=1}^{N} (A_{bj} AND W_{ji})

其中：
  B   = 输入位宽
  A_bj = 输入第 b 位
  W_ji = 权重值（1-bit，存在每个 memory cell）
  AND  = 每个 cell 附带的逻辑门
```

位串行计算需要 B 个时钟周期完成一个完整的 MVM，但可以全行并行。

#### 4.5.4 仿真级别分支（`xbar_simulation_level`）

**Level 0（Behavior 级，默认，对应 `Simulation_Level = 0`）：**
- 不依赖具体权重矩阵内容
- 仅记录已占用行列数（`xbar_num_write_row`，`xbar_num_read_column` 等）
- 功耗用默认估算值（几何/RMS 平均电导和电压）

**Level 1（Estimation 级，对应 `Simulation_Level = 1`）：**
- 使用实际权重数据（`xbar_write_matrix`、`xbar_read_matrix`）
- 电导矩阵：`conductance[i,j] = 1 / R[weight_level[i,j]]`
- 支持矩阵级 `G·V²` 求和的精细功耗估计

#### 4.5.5 面积计算（`calculate_xbar_area`）

**方法 0（使用 Device_Area，适合 NVM）：**

```
模拟 PIM（PIM_type == 0）：
  xbar_area = xbar_row × xbar_column × device_area + 1150 × xbar_row
              （1150 μm/row 为外围电路经验值）

数字 PIM（PIM_type != 0）：
  xbar_area = xbar_row × xbar_column × device_area
            + xbar_row × (7.3×2.7 + 9.5×3.8) × (transistor_tech/65)²
```

**方法 1（使用工艺几何，适合 SRAM 或精确评估）：**

```
SRAM：
  xbar_area = xbar_row × xbar_column × 5  （5F² per cell，F = transistor_tech）

0T1R（无选通管）：
  xbar_area = 4 × xbar_row × xbar_column × device_tech² × 1e-6

1T1R（有选通管，WL_ratio=3）：
  xbar_area = 3 × (WL_ratio + 1) × xbar_row × xbar_column × device_tech² × 1e-6
            = 12 × xbar_row × xbar_column × device_tech² × 1e-6
```

#### 4.5.6 读延迟（`calculate_xbar_read_latency`）

读延迟由器件固有延迟与阵列 RC 延迟两部分组成：

**线路延迟经验公式（对 1T1R 与 0T1R 相同）：**

$$size_{KB} = \frac{N_{row} \times N_{col}}{1024 \times 8}$$

$$t_{wire} = 0.001 \times \left( 2 \times 10^{-4} \times size^2 + 5 \times 10^{-6} \times size + 4 \times 10^{-14} \right) \quad \text{(ns)}$$

**总读延迟：**

$$t_{xbar,read} = t_{device,read} + t_{wire}$$

#### 4.5.7 写延迟（`calculate_xbar_write_latency`）

假设同一行并行写入：

$$t_{xbar,write} = t_{device,write} \times N_{write\_rows}$$

#### 4.5.8 读功耗（`calculate_xbar_read_power`）

**Level 0（行为级）：**

$$P_{xbar,read} = N_{read\_rows} \times N_{read\_cols} \times P_{device,read}$$

若 `cell_type == "0T1R"`（无选通管，存在寄生泄漏路径）：

$$P_{xbar,read} += 0.25 \times N_{read\_rows} \times (N_{col} - N_{read\_cols}) \times P_{device,read}(R_{HRS})$$

> 1/4 系数来自等效电路估算：未激活列通过相邻行形成的 sneak path

**Level 1（估计级）：**

$$P_{xbar,read} = \mathbf{G}^T \cdot \mathbf{V}^2 = \sum_j \left( G_j \cdot \sum_i V_i^2 \right)$$

0T1R 额外泄漏（激活行对非激活列的贡献）：

$$P_{leak} = 0.25 \times \sum_{j \notin active} \frac{1}{R_{LRS}} \cdot V_{active,i}^2$$

#### 4.5.9 写功耗与能量

**Level 0：** $P_{xbar,write} = N_{write\_cols} \times P_{device,write}$

**Level 1：** $P_{xbar,write} = \mathbf{G}_{write}^T \cdot \mathbf{V}_{write}^2 / N_{write\_rows}$

**读能量：**

$$E_{xbar,read} = \begin{cases} P_{xbar,read} \times t_{xbar,read} & \text{NVM} \\ N_{read\_rows} \times N_{read\_cols} \times E_{device,read} \times 10^6 & \text{SRAM} \end{cases}$$

**写能量：**

$$E_{xbar,write} = \begin{cases} P_{xbar,write} \times t_{device,write} & \text{NVM（不含写线功耗）} \\ N_{write\_rows} \times N_{write\_cols} \times E_{device,write} \times 10^6 & \text{SRAM} \end{cases}$$

#### 4.5.10 IR Drop 建模（简化解析模型）

```
简化解析模型：
  V_drop(i) ≈ I_cumulative(i) × R_wire_per_unit × i

  L_BL = ArrayRow × cell_pitch
  R_wire = ρ × L / A（电阻率 × 长度 / 截面积）
```

**已知局限**：IR drop 基于平均电流，未考虑具体激活模式（activation pattern）对电流分布的影响——不同输入会导致不同的 IR drop 分布。这是精度误差的主要来源之一。

---


### 4.6 处理单元层 PE（Layer 5）

**文件**：`MNSIM/Hardware_Model/PE.py`  
**类**：`class ProcessElement(crossbar, DAC, ADC)`

PE 是完整的计算执行单元，包含若干 Crossbar 阵列组、DAC/ADC 接口及数字控制逻辑。

#### 4.6.1 配置参数（来自 `[Process element level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 含义 |
|---|---|---|---|
| `PIM_Type` | `PIM_type_pe` | 0 | 0 = 模拟 PIM；1 = 数字 PIM（强制 1-bit 接口） |
| `Xbar_Polarity` | `Xbar_Polarity` | 2 | 1 = 单阵列存正负权重（折叠）；2 = 正阵列+负阵列分开（对偶） |
| `Sub_Position` | `Sub_Position` | 0 | Polarity=2 时：0 = 模拟域相减（ADC前）；1 = 数字域相减（ADC后） |
| `Group_Num` | `group_num` | 1 | 每个 PE 内的 Crossbar 组数（通道并行度） |
| `DAC_Num` | `PE_group_DAC_num`（初始值） | 128 | 每组每 subarray 的 DAC 数；0 = 根据面积自动推算 |
| `ADC_Num` | `PE_group_ADC_num`（初始值） | 128 | 每组每 subarray 的 ADC 数；0 = 根据面积自动推算 |
| `PE_inBuf_Size` | — | 0→默认 16 KB | PE 输入缓冲大小（KB） |
| `Tile_outBuf_Size` | — | 0→默认 | Tile 输出缓冲大小（逻辑上属于 Tile，从 PE 级读取） |
| `DFU_Buf_Size` | — | 0→默认 | Data Forwarding Unit 缓冲大小（KB） |

**衍生结构参数：**

```python
# Polarity = 1：单阵列（一个阵列存储正负两种符号权重）
PE_multiplex_xbar_num = [1, 1]

# Polarity = 2：正负双阵列（正权重和负权重各用一个阵列）
PE_multiplex_xbar_num = [1, 2]

PE_xbar_num = group_num × multiplex[0] × multiplex[1]  # PE 内总 Crossbar 数
PE_ADC_num = group_num × PE_group_ADC_num               # PE 内总 ADC 数
PE_DAC_num = group_num × PE_group_DAC_num               # PE 内总 DAC 数
```

#### 4.6.2 ADC/DAC 数量自动推算（物理面积约束）

当 `ADC_Num = 0` 时，按面积比例估算可在 Crossbar 边长内排下多少个 ADC：

**ADC 数量（`calculate_ADC_num`）：**

$$PE\_group\_ADC\_num = \min\left( \left\lceil (Sub\_Position+1) \times \frac{\sqrt{A_{xbar}} \times N_{pol,neg}}{\sqrt{A_{ADC}}} \right\rceil, N_{col} \right) \times N_{subarray}$$

**输出 MUX 比（分时复用度）：**

$$output\_mux = \left\lceil \frac{N_{col}}{PE\_group\_ADC\_num / N_{subarray}} \times (Sub\_Position + 1) \right\rceil$$

**DAC 数量（`calculate_DAC_num`）：**

$$PE\_group\_DAC\_num = \min\left( \left\lceil \frac{\sqrt{A_{xbar}} / N_{subarray} \times N_{pol,pos}}{\sqrt{A_{DAC}}} \right\rceil, subarray\_size \right) \times N_{subarray}$$

**输入 DEMUX 比（分时复用度）：**

$$input\_demux = \left\lceil \frac{subarray\_size \times N_{pol,pos}}{PE\_group\_DAC\_num / N_{subarray}} \right\rceil$$

#### 4.6.3 MUX/DEMUX 面积与功耗

晶体管面积基准：

$$A_{transistor} = 10 \times transistor\_tech^2 \times 10^{-6} \quad \text{(μm²)}$$

功耗基准：$P_{transistor} = 10 \times 1.2 / 10^9 \text{ W}$

| 复用比值档位 | 面积（×Aₜ） | 功耗（×Pₜ） |
|---|---|---|
| 2 | 8 | 8 |
| 4 | 24 | 24 |
| 8 | 72 | 72 |
| 16 | 216 | 216 |
| 32 | 648 | 648 |
| 64 | 1944 | 1944 |

#### 4.6.4 PE 内加法树（`calculate_inter_PE_connection`）

对 `group_num` 组进行二叉树合并，计算所需加法器总数：

```python
temp = group_num
PE_adder_num = 0
while temp / 2 >= 1:
    PE_adder_num += int(temp / 2) * subarray_num
    temp = int(temp / 2) + temp % 2
```

每层加法器数量 = ⌊group/2⌋ × subarray_num，对应二叉树折叠合并结构。

#### 4.6.5 PE 总面积组成

$$A_{PE} = A_{xbar,total} + A_{ADC,total} + A_{DAC,total} + A_{digital} + A_{input\_buf}$$

$$A_{xbar,total} = PE\_xbar\_num \times A_{xbar}$$
$$A_{ADC,total} = PE\_ADC\_num \times A_{ADC}$$
$$A_{DAC,total} = PE\_DAC\_num \times A_{DAC}$$
$$A_{digital} = A_{adder} + A_{shiftreg} + A_{demux} + A_{mux} + A_{iReg} + A_{oReg}$$
$$A_{adder} = PE\_group\_ADC\_num \times PE\_adder\_num \times A_{single\_adder}$$

#### 4.6.6 PE 读功耗组成（`calculate_PE_read_power_fast`）

| 子模块 | 功耗计算公式 |
|---|---|
| Crossbar | `P_xbar × N_pol_neg × group / input_demux / output_mux` |
| DAC | `group × ⌈row / input_demux⌉ × P_DAC` |
| Input DEMUX | `group × ⌈row / input_demux⌉ × P_demux` |
| Input Reg (iReg) | `group × ⌈row / input_demux⌉ × P_iReg` |
| ADC | `group × ⌈col / output_mux⌉ × P_ADC` |
| Output MUX | `group × ⌈col / output_mux⌉ × P_mux` |
| Adder | `(group - 1) × ⌈col / output_mux⌉ × P_adder` |
| ShiftReg | `group × ⌈col / output_mux⌉ × P_shiftreg` |
| Output Reg (oReg) | `group × ⌈col / output_mux⌉ × P_oReg` |

**数字 PIM 时（`PIM_type == 1`）**：ADC/MUX/Adder/ShiftReg/oReg 均再乘以 `subarray_num`（每个 subarray 有独立 SA）。

#### 4.6.7 PE 能效计算（`calculate_PE_energy_efficiency`）

**时间步数（DAC 分时复用次数）：**

$$multiple\_time = \left\lceil \frac{8}{DAC\_precision} \right\rceil$$

> 若 DAC 精度为 1-bit，则需 8 个时间步才能完成 8-bit 输入激活的完整计算

**Decoder 延迟（1-to-8 decoder 级联，基准 0.27933 ns/级）：**

$$t_{decoder} = m \times 0.27933 \text{ ns}$$

其中 m 通过 `Row_per_DAC` 反复除以 8 的循环次数决定。

**MUX 延迟（8-to-1 MUX 级联，基准 32.744×10⁻³ ns/级）：**

$$t_{mux} = m \times 32.744 \times 10^{-3} \text{ ns}$$

**各子模块延迟：**

$$t_{xbar} = multiple\_time \times t_{xbar,read}$$
$$t_{DAC} = multiple\_time \times t_{DAC,latency}$$
$$t_{ADC} = multiple\_time \times t_{ADC,latency}$$
$$t_{iReg} = t_{digital\_period} + multiple\_time \times t_{digital\_period}$$
$$t_{shiftreg} = multiple\_time \times t_{digital\_period}$$
$$t_{demux} = multiple\_time \times t_{decoder}$$
$$t_{adder} = \lceil \log_2(group\_num) \rceil \times t_{digital\_period}$$
$$t_{mux\_out} = multiple\_time \times t_{mux,latency}$$
$$t_{oReg} = t_{digital\_period}$$

**总 PE 延迟：** $t_{PE,total} = \sum_{all\;modules} t_{module}$

**等效算力与能效：**

$$GOPS = \frac{2 \times PE\_group\_DAC\_num \times PE\_group\_ADC\_num}{t_{PE,total}}$$

$$Efficiency_{GOPS/W} = \frac{2 \times PE\_group\_DAC\_num \times PE\_group\_ADC\_num}{E_{PE,total}}$$

---

### 4.7 数字辅助模块

这些模块是 PE 和 Tile 中数字逻辑部分的子单元，均通过 `[Digital module]` 配置，所有延迟基准均为 `1 / Digital_Frequency`。

#### 4.7.1 Adder（加法器）

**文件**：`MNSIM/Hardware_Model/Adder.py`

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Adder_Tech` | 45 nm | 工艺节点（支持 28/45/55/65/130 nm） |
| `Adder_Area` | 0 → 自动 | μm²；0 = 自动查表 |
| `Adder_Power` | 0 → 自动 | W；0 = 自动查表 |
| `Digital_Frequency` | 500 MHz | 数字电路工作频率 |
| `adder_bitwidth` | 8 bit | 加法器位宽（可由上层传入） |

**面积查找表（基于 14 晶体管全加器，×bitwidth）：**

| 工艺节点 | 单位面积（每 bit） |
|---|---|
| ≤ 28 nm | 10×14×28²/1e6 μm² |
| ≤ 45 nm | 10×14×45²/1e6 μm² |
| ≤ 55 nm | 10×14×55²/1e6 μm² |
| ≤ 65 nm | 1.42 μm²（实测值，非几何公式） |
| > 65 nm | 10×14×130²/1e6 μm² |

**功耗查找表（×bitwidth）：**

| 工艺节点 | 单位功耗（每 bit） |
|---|---|
| 65 nm | 3×10⁻⁷ W |
| 其余 | 2.5×10⁻⁹ W |

#### 4.7.2 ShiftReg（移位寄存器）

**文件**：`MNSIM/Hardware_Model/ShiftReg.py`  
**配置**：`ShiftReg_Tech`（默认 65 nm），`ShiftReg_Area`，`ShiftReg_Power`

用于在 PE 内部对多 bit ADC 输出进行移位累加（bit-serial MAC 的数字累加部分），将每个时间步的 ADC 输出左移适当位数后累加。

#### 4.7.3 Reg（寄存器）

**文件**：`MNSIM/Hardware_Model/Reg.py`  
**配置**：`Reg_Tech`（默认 45 nm），`Reg_Area`，`Reg_Power`

- **iReg（输入寄存器）**：缓存当前时间步送入 DAC 的激活值片段，位数 = DAC_precision
- **oReg（输出寄存器）**：缓存 ADC 量化结果，位数 = ADC_precision

#### 4.7.4 JointModule（跨 PE 合并模块）

**文件**：`MNSIM/Hardware_Model/JointModule.py`

JointModule 用于 Tile 层面将多个 PE 的输出加法合并，等效于 Tile 内的跨 PE 二叉加法树节点。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `JointModule_Tech` | 45 nm | 工艺节点 |
| `JointModule_Area` | 0 → 自动 | μm² |
| `JointModule_Power` | 0 → 自动 | W |
| `jointmodule_bit` | 8 bit | 操作位宽（由上层传入） |

**面积/功耗查找表（按位宽，带工艺缩放 `(tech/65)²`）：**

| 位宽 | 面积（μm²，@65nm） | 功耗（W，@65nm） |
|---|---|---|
| ≤ 4 bit | 182.88 | 1.39×10⁻⁴ |
| ≤ 8 bit | 353.76 | 2.64×10⁻⁴ |
| ≤ 12 bit | 385.44 | 3.67×10⁻⁴ |
| ≤ 16 bit | 512.16 | 4.97×10⁻⁴ |

工艺缩放系数：`(tech/65)²`。

#### 4.7.5 Buffer（SRAM 片上缓存）

**文件**：`MNSIM/Hardware_Model/Buffer.py`

Buffer 分三个层级（`buf_level`）：
- `1`：PE 输入缓冲（`PE_inBuf_Size`）
- `2`：Tile 输出缓冲（`Tile_outBuf_Size`）
- `3`：DFU 数据转发缓冲（`DFU_Buf_Size`）

**配置参数（来自 `[Architecture level]`）：**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Buffer_Choice` | 1 | 1 = SRAM；2 = DRAM；3 = RRAM |
| `Buffer_Technology` | 90 nm | 工艺节点（支持 <65 / 65–89 / ≥90 nm 三档） |
| `Buffer_Bitwidth` | 64 bit | 总线位宽（支持 64/128/256/512 bit 四档） |
| `Buffer_ReadPower` | 0 → 自动 | mW |
| `Buffer_WritePower` | 0 → 自动 | mW |

**索引机制**：根据工艺（3档）× 容量（9档：2/4/8/16/32/64/128/256/512+ KB）× 位宽（4档）= 108 个预定义配置，通过 `self.index` 查找面积/动态功耗/静态泄漏/延迟数组。

**读写延迟：**

$$t_{buf,read} = \left\lceil \frac{data \times 8}{buf\_bitwidth} \right\rceil \times buf\_cycle \quad \text{(ns)}$$

其中 `buf_cycle` 在代码中**硬编码为 20 ns**（注释掉了动态查表逻辑）。

**读写功耗（动态 + 静态泄漏）：**

$$P_{buf,read} = P_{dynamic,read} + P_{leakage}$$

$$P_{dynamic,read} = \frac{E_{read\_per\_access}}{buf\_cycle} \times 10^3 \quad \text{(mW)}$$

**读写能量（含泄漏）：**

$$E_{buf,read} = \left( E_{per\_access} + buf\_cycle \times \frac{P_{leakage}}{10^3} \right) \times \left\lceil \frac{data \times 8}{bitwidth} \right\rceil \quad \text{(nJ)}$$

#### 4.7.6 Pooling（池化单元）

**文件**：`MNSIM/Hardware_Model/Pooling.py`

**配置参数（来自 `[Tile level]`）：**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Pooling_shape` | `3,3` | 池化核尺寸（行,列），默认 3×3 |
| `Pooling_unit_num` | 64 | 每个 Tile 中并行池化单元数量 |
| `Pooling_Tech` | 65 nm | 池化单元工艺节点 |
| `Pooling_area` | 0 → 自动 | μm² |

**面积参考值（@65nm, 3×3核, 64单元）**：91917.16 μm²，工艺缩放乘以 `(tech/65)²`，数量缩放乘以 `unit_num/64`

**功耗参考值（@65nm, 3×3, 64 units）**：3.082×10⁻³ W

**延迟（分批并行处理）：**

$$t_{pooling} = 100 \times \left\lceil \frac{inchannel}{Pooling\_unit\_num} \right\rceil \times \left\lceil \frac{insize}{Pooling\_size} \right\rceil \quad \text{(ns)}$$

---

### 4.8 Tile 层（Layer 6）

**文件**：`MNSIM/Hardware_Model/Tile.py`  
**类**：`class tile(ProcessElement)`

Tile 是加速器的基本调度单元，包含一个 PE 二维网格及相关输入/输出基础设施。

#### 4.8.1 配置参数（来自 `[Tile level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 含义 |
|---|---|---|---|
| `PE_Num` | `tile_PE_num` | `0,0` → `[4,4]` | Tile 内 PE 阵列尺寸（行×列）；0,0 = 默认 4×4 |
| `Tile_Adder_Num` | — | 0 → 自动 | Tile 级加法器数；0 = 自动计算 |
| `Tile_Adder_Level` | — | 0 → 自动 | 加法树最大层数 |
| `Tile_ShiftReg_Num` | — | 0 → 自动 | Tile 级移位寄存器数 |
| `Tile_ShiftReg_Level` | — | 0 → 自动 | 移位寄存器最大层数 |
| `Inter_Tile_Bandwidth` | — | 20 Gbps | Tile 间通信带宽（层间数据传输） |
| `Intra_Tile_Bandwidth` | — | 1024 Gbps | Tile 内 PE 间通信带宽 |
| `Tile_outBuf_Size` | — | 0 → 默认 | Tile 输出缓冲大小（KB） |
| `DFU_Buf_Size` | — | 0 → 默认 | 数据转发单元缓冲大小（KB） |

Tile 内包含：
- `tile_PE_list`：二维 PE 实例列表（tile_PE_num[0] × tile_PE_num[1]）
- `tile_jointmodule_list`：PE 间合并 JointModule 列表
- `tile_buffer`：输出 Buffer（buf_level=2）
- `DFU_buffer`：数据转发 Buffer（buf_level=3）
- `tile_pooling`：Pooling 单元实例

**数据流设计**：Tile 内部的 IFmap（输入特征图）可以广播给所有需要它的 PE，体现了 Weight Stationary 数据流——权重固定在阵列中，输入数据在 PE 间流动。

#### 4.8.2 Tile 内 PE 间加法树（`calculate_intra_PE_connection`）

对 `tile_PE_total_num` 个 PE 的输出做二叉树合并：

```python
index = tile_PE_total_num
temp_num = 0
while index / 2 >= 1:
    temp_num += int(index / 2) + index % 2
    index = int(index / 2)

# 三者相等，反映流水线式的 PE 输出合并树
tile_adder_num = tile_shiftreg_num = tile_jointmodule_num = temp_num × PE_ADC_num
```

#### 4.8.3 Tile 总面积组成

$$A_{Tile} = A_{xbar,all} + A_{ADC,all} + A_{DAC,all} + A_{digital,all} + A_{buffer} + A_{pooling}$$

$$A_{digital,Tile} = \sum_{PE} (A_{demux} + A_{mux} + A_{adder} + A_{shiftreg} + A_{iReg} + A_{oReg}) + tile\_jointmodule\_num \times A_{jointmodule}$$

$$A_{buffer,Tile} = A_{outBuf} + A_{DFU\_buf}$$

#### 4.8.4 Tile 内传输延迟（`Tile_latency.py`）

Tile 内 PE 间数据合并传输延迟（基于带宽和加法树层数）：

$$t_{transfer,intra} = \frac{\left( L \times (N_{ADC\_prec} + t_{merge}) - \frac{t_{merge}(t_{merge}+1)}{2} \right) \times N_{read\_col}}{BW_{intra}}$$

其中：
- `L = total_level`：加法树层数（≈ log₂(PE 数)）
- `t_merge`：每层合并所需时钟数
- `N_ADC_prec`：ADC 精度（bit）
- `BW_intra = Intra_Tile_Bandwidth`（Gbps）

#### 4.8.5 Tile 读功耗组成

| 子模块 | 功耗来源 |
|---|---|
| 全部 PE | `N_PE × P_PE_read × (max_group / group_num_total)` |
| JointModule | `(max_PE - 1) × ⌈max_col / output_mux⌉ × P_jointmodule` |
| Output Buffer（读） | `buf_rpower × 1e-3` |
| Output Buffer（写） | `buf_wpower × 1e-3` |
| Pooling | `Pooling_power`（仅 pooling 层） |

$$P_{Tile,read} = P_{xbar,all} + P_{ADC,all} + P_{DAC,all} + P_{digital,all} + P_{buffer,Tile}$$

---

## 5. 层间通信机制

MNSIM 2.0 的通信建模采用**静态解析模型**（而非事件驱动仿真），这是行为级工具的典型选择。

### 5.1 通信的四条路径

```
路径 1：DRAM → PIM 芯片    （权重加载，计算前一次性完成）
路径 2：层间 Tile 传输      （IFmap 分发，跨 Tile 部分和聚合）
路径 3：Tile 内 PE 间传输   （PE 输出向 Tile 级合并树传递）
路径 4：PE 内 Crossbar 间   （group 间局部加法树合并）
```

### 5.2 Tile 间通信延迟建模

TCG 计算 Manhattan 距离，结合 Inter_Tile_Bandwidth 得到传输时间：

$$t_{transfer,layer\_l} = d_{transLayer}[l] \times \frac{N_{output\_channel} \times N_{output\_bits}}{BW_{inter\_tile}}$$

**局限**：曼哈顿距离是几何近似，没有考虑实际 NoC 拥塞（congestion）和仲裁延迟。ResNet 的残差连接等有等待关系的结构会导致延迟低估。

### 5.3 NoC（可选，BookSim）

`SimConfig.ini` 中 `NoC_enable = 1` 时：
- 调用 `MNSIM/NoC/interconnect_estimation.py`
- 使用 **BookSim 可执行文件 + mesh 配置 + 注入率文件** 估算平均包延迟
- 默认**关闭**；与主流程耦合较弱（依赖外部预生成的流量文件）
- **片间（chip-to-chip）互联未建模**

### 5.4 通信 vs. 计算的关键权衡

```
计算并行度 ↑  →  Tile 数量 ↑  →  NoC 流量 ↑  →  通信开销 ↑
             →  PE 数量 ↑   →  局部通信 ↑  →  功耗 ↑

这个 trade-off 是 MNSIM 设计空间探索的核心目标函数之一
```

---

## 6. 映射与调度模块

映射与调度是连接 NN 算法和 PIM 硬件的桥梁，直接决定 PPA 和精度的实际表现。

### 6.1 卷积层的权重映射

**权重展开：**

```
CONV 层权重 W[Cout × Cin × K × K]
    │ reshape
    ▼
W'[Cout × (Cin×K×K)]    ← 2D 矩阵，D = Cin×K×K
```

**资源分配逻辑：**

```
需要的 Array 列数 = ceil(D / ArrayRow)          （沿输入维度切分）
需要的 Array 行数 = ceil(Cout / ArrayCol)        （沿输出维度切分）
需要的 PE 数     = ceil(D / ArrayRow) × ceil(Cout / ArrayCol)
需要的 Tile 数   = ceil(PE 总数 / tile_PE_total_num)
```

### 6.2 调度策略

| 策略 | 说明 | 优势 |
|------|------|------|
| Weight-Stationary (WS) | 权重固定在阵列，输入和输出流动 | 权重访问能耗最低 |
| Layer-by-Layer | 逐层执行，层间流水 | 实现简单，内存占用可控 |
| Pipeline | 层间流水线，提高吞吐 | 延迟隐藏，提升利用率 |

`main.py` 默认走 `calculate_model_latency(mode=1)`（流水线模式）。

### 6.3 PE 利用率

当权重矩阵尺寸不能整除阵列尺寸时，会出现 PE 空洞（idle columns/rows），降低利用率。MNSIM 2.0 会通过 `xbar_utilization` 统计并报告这一指标：

$$utilization = \frac{N_{occupied\_row} \times N_{occupied\_col}}{xbar\_row \times xbar\_column}$$

### 6.4 behavior_mapping（可选）

除 TCG 主流程外，代码中还存在 `MNSIM/Mapping_Model/behavior_mapping.py`，实现按 kernel/通道/bit 切分的行为级 PE/Tile 数量估算（`config_behavior_mapping`）。`main.py` 默认走 TCG，两者并行存在。

---

## 7. 算法层：精度仿真与训练量化流

### 7.1 完整精度仿真流程

```
权重矩阵 W（PyTorch 格式）
│
├─→ 按 ArrayRow × ArrayCol 分块（weight splitting）
│
▼ 各子块权重
│
├─→ [Device Variation]  G_actual ~ N(G_target, σ²)
├─→ [Stuck-at Fault]    部分 cell 随机固定在 Ron 或 Roff
├─→ [ADC 量化]          n-bit 均匀量化截断
│
▼ 含噪声的等效权重
│
├─→ 与输入激活进行 MVM（分时复用 multiple_time 步）
├─→ 加法器树合并部分和
├─→ 激活函数
│
▼ 下一层输入（误差向后传播）
│
▼ 最终 Top-1 精度
```

### 7.2 非理想性注入机制（`Weight_update.py`，`Crossbar_accuracy.py`）

#### 7.2.1 器件变异（Device Variation）

**Weight 级（`Weight_update.py`，训练后注入）：**

```python
for each weight index j:
    temp_resistance = Normal(0, device_resistance[j] * variation / 100)
    conductance[j] = 1 / (device_resistance[j] + temp_resistance) * unit_conductance
```

#### 7.2.2 Stuck-at Fault（SAF）

按 `Device_SAF` 比例随机将权重固定：
- Stuck-At-LRS（SAL）：权重固定为 `max_value`（对应低阻态）
- Stuck-At-HRS（SAH）：权重固定为 `0`（对应高阻态）

**Crossbar 精度级（`Crossbar_accuracy.py`，更细粒度）：**

对非 SAF 单元，加入电阻随机扰动（来自 `device_variation`），再叠加行列线 IR 压降修正：

```
temp_resistance = uniform(R × (1 ± 0.01 × device_variation))
V_effective = V_applied - sum_of_wire_resistance_drops
```

#### 7.2.3 ADC 量化非理想性

**`set_weights_forward`（`quantize.py`）** 实现两种量化模式：

- **SCALE 模式**（`adc_action='SCALE'`）：按动态 scale 与 point_shift 做舍入，每次前向自适应范围，对应硬件实时校准
- **FIX 模式**（`adc_action='FIX'`）：用固定 `fix_scale_range` 与 `xbar_size` 做舍入，对应实际部署的固定量化范围

**ADC 有效位宽扩展（`extend_ADC_bitwidth`）**：

由于每个时钟周期只激活部分行（受 `DAC_num` 和阵列行数限制），多个部分积的累加会导致输出动态范围扩大，ADC 有效位宽需要增加以避免截断：

$$ADC\_eff\_bits = ADC\_bits + \lceil \log_2(input\_demux) \rceil$$

#### 7.2.4 各非理想因素的影响特征

| 非理想性 | 影响类型 | 对精度影响 | MNSIM 建模方式 |
|---------|---------|-----------|--------------|
| Device Variation | 随机噪声 | 每次推断随机波动 | 高斯分布 N(0, σ²) |
| Stuck-at Fault | 系统性偏差 | 固定精度损失 | 随机选取比例固定 cell |
| ADC 量化 | 截断误差 | 位数越低损失越大 | 均匀量化 |
| IR Drop | 空间相关偏差 | 大阵列边缘精度差 | 简化解析式（激活无关） |

### 7.3 PIM 导向训练与量化

#### 7.3.1 权重拆分感知训练

```
训练时的关键操作：
  根据 ArrayRow × ArrayCol 大小对权重矩阵分块
  在每个子块上独立进行量化（而非全局量化）
  引入 ADC 量化误差到训练 loss
  → 训练出的权重天然适应 PIM 分块执行模式
```

#### 7.3.2 能量正则化训练（Energy-Aware Regularization）

```python
loss_total = loss_cross_entropy + λ × loss_energy
loss_energy = Σ_layer Σ_weight |W_ij|
```

物理含义：大电导值（对应大权重）需要更多编程脉冲，能耗更高，正则化鼓励稀疏小权重。

#### 7.3.3 混合精度量化

不同层对精度的敏感度不同，MNSIM 2.0 支持逐层分配不同量化位宽：

```
敏感层（如第一层、最后一层）→ 高位宽（8-bit）
不敏感层（中间层）→ 低位宽（2-4 bit）
评估依据：基于 Hessian 矩阵或激活范围分析
```

#### 7.3.4 非均匀激活量化

针对输出激活值分布不均匀（长尾分布），使用非均匀量化：

```
均匀量化：等间距划分 → 尾部精度差
非均匀量化：基于数据分布自适应划分 → 集中精度在高密度区域
```

---

## 8. 闭环反馈机制与代码实现

### 8.1 反馈循环的本质

MNSIM 2.0 的反馈是一个**设计迭代闭环**（非运行时动态）：

```
Step 1：设定初始硬件配置（SimConfig.ini）
Step 2：运行硬件性能建模 → 得到 array_size, adc_bits 等约束
Step 3：这些约束传入训练/量化流 → 优化 NN 模型
Step 4：优化后的 NN 模型重新进行精度仿真
Step 5：更新硬件配置（如发现 ADC 分辨率不够）→ 回到 Step 2
```

### 8.2 代码中的双模块共享配置

两个独立模块共享同一套 `SimConfig.ini`：

```python
SimConfig_path = "SimConfig.ini"   # 统一配置源

# 模块1：NN 训练/精度仿真
__TestInterface = TrainTestInterface(
    network_module=args.NN,
    SimConfig_path=SimConfig_path,    # ← 读取 hw 约束（ADC精度、阵列大小等）
    weights_file=args.weights
)

# 模块2：硬件性能建模（同一个配置文件）
__latency = Model_latency(NetStruct=structure_file, SimConfig_path=SimConfig_path, ...)
__area    = Model_area(NetStruct=...,    SimConfig_path=SimConfig_path, ...)
__power   = Model_inference_power(NetStruct=..., SimConfig_path=SimConfig_path, ...)
__energy  = Model_energy(NetStruct=...,  SimConfig_path=SimConfig_path, ...)
```

---

## 9. 代码结构详解

### 9.1 目录结构

```
MNSIM-2.0/
│
├── main.py                          # 主入口，串联所有模块
├── SimConfig.ini                    # 硬件配置文件（用户主要修改此处）
│
└── MNSIM/
    ├── Interface/                   # NN 模型接口层
    │   ├── TrainTestInterface.py    # 训练/测试/精度评估入口
    │   ├── network.py               # 计算图：get_net(), get_structure()
    │   ├── quantize.py              # 量化前向推断（QuantizeLayer, set_weights_forward）
    │   └── Network_DEFINE/          # NN 结构定义（vgg8 等）
    │
    ├── Accuracy_Model/              # 精度仿真核心
    │   ├── Crossbar_accuracy.py     # Crossbar 级物理精度小模型
    │   └── Weight_update.py         # 非理想性注入（variation, SAF）
    │
    ├── Mapping_Model/               # 映射与调度
    │   ├── Tile_connection_graph.py # TCG：NN 层 → Tile 映射，距离计算
    │   └── behavior_mapping.py      # 行为级资源估算（可选）
    │
    ├── Hardware_Model/              # 硬件层次模型
    │   ├── Device.py                # 器件层
    │   ├── Crossbar.py              # Crossbar 阵列层
    │   ├── ADC.py                   # ADC 接口
    │   ├── DAC.py                   # DAC 接口
    │   ├── PE.py                    # Processing Element
    │   ├── Tile.py                  # Tile
    │   ├── Adder.py                 # 加法器
    │   ├── ShiftReg.py              # 移位寄存器
    │   ├── Reg.py                   # 寄存器
    │   ├── JointModule.py           # 跨 PE 合并模块
    │   ├── Buffer.py                # SRAM 缓存（三层级）
    │   ├── Pooling.py               # 池化硬件
    │   └── Multiplier.py            # 乘法器（扩展项，未完全启用）
    │
    ├── Latency_Model/               # 延迟建模
    │   ├── Model_latency.py         # 整体延迟汇总（含流水线）
    │   ├── Tile_latency.py          # Tile 级延迟
    │   ├── PE_latency.py            # PE 级延迟
    │   └── Pooling_latency.py       # 池化层延迟
    │
    ├── Area_Model/                  # 面积建模
    │   └── Model_area.py
    │
    ├── Power_Model/                 # 推理功耗建模
    │   └── Model_inference_power.py
    │
    ├── Energy_Model/                # 能量建模（功率×延迟）
    │   └── Model_energy.py
    │
    └── NoC/                         # 可选 NoC 仿真（BookSim）
        └── interconnect_estimation.py
```

### 9.2 核心入口 main.py

```python
def main():
    # 1. 解析命令行参数（NN模型、权重、配置路径、是否开启非理想性等）
    args = parser.parse_args()
    
    # 2. 初始化 NN 接口（加载网络结构和权重）
    __TestInterface = TrainTestInterface(
        network_module=args.NN,
        SimConfig_path=args.hardware_description,
        weights_file=args.weights
    )
    
    # 3. 获取网络结构文件（用于硬件建模）
    structure_file = __TestInterface.get_structure()
    
    # 4. 构建 Tile Connection Graph（映射）
    TCG_mapping = TCG(NetStruct=structure_file,
                      SimConfig_path=args.hardware_description)
    
    # 5. 硬件性能建模（Latency → Area → Power → Energy）
    __latency = Model_latency(structure_file, SimConfig_path, TCG_mapping)
    __area    = Model_area(structure_file, SimConfig_path, TCG_mapping)
    __power   = Model_inference_power(structure_file, SimConfig_path, TCG_mapping)
    __energy  = Model_energy(structure_file, SimConfig_path, TCG_mapping, __latency, __power)
    
    # 6. 精度仿真
    # 原始精度（无 PIM 非理想性）
    __TestInterface.origin_evaluate(method='FIX_TRAIN', adc_action='SCALE')
    
    # PIM 实际精度（含非理想性）
    weight_2 = __TestInterface.get_weights()
    __TestInterface.set_net_bits_evaluate(
        weight_2, adc_action='SCALE',
        is_Variation=args.enable_variation,
        is_SAF=args.enable_SAF,
        is_Rratio=args.enable_R_ratio
    )
```

### 9.3 关键模块调用链

**精度仿真：**

```
TrainTestInterface.set_net_bits_evaluate()
    └── Weight_update.weight_variation_add()   ← 注入 variation
        └── Weight_update.SAF_analysis()        ← 注入 SAF
            └── quantize.set_weights_forward()  ← 量化前向推断
                └── 最终精度计算
```

**硬件延迟：**

```
Model_latency.calculate_model_latency()
    └── Tile_latency.tile_latency_analysis()
        ├── PE_latency.pe_latency_analysis()
        │   └── crossbar.calculate_xbar_read_latency()  ← 查公式/表格
        ├── buffer.calculate_buf_read_latency()          ← 查 SRAM 表
        └── noc_latency = distance × data / bandwidth   ← 曼哈顿距离
```

---

## 10. PPA 建模方法

### 10.1 延迟模型

**整体延迟（含流水线）：**

$$T_{total} = \sum_{layer} \max(T_{compute}[layer], T_{comm}[layer])$$

**PE 级计算延迟：**

$$T_{xbar} = DAC\_latency \times multiple\_time + ADC\_latency \times multiple\_time + Adder\_tree\_latency$$

**层间通信延迟：**

$$T_{comm}[layer] = \frac{data\_volume}{BW_{inter\_tile}} \times d_{transLayer}[l]$$

流水线建模：当前层计算与下一层数据传输重叠，用 `max()` 取计算和通信的瓶颈。

### 10.2 面积模型

$$A_{total} = N_{tile} \times \left( N_{PE} \times (N_{Xbar} \times A_{xbar} + A_{PE\_logic}) + A_{buffer,tile} + A_{pooling} \right) + A_{NoC}$$

$$A_{xbar} = A_{cell} \times N_{row} \times N_{col} + A_{DAC} \times N_{row} + A_{ADC} \times N_{col} + A_{WL\_driver} + A_{decoder}$$

### 10.3 功耗与能量模型

**推理功耗：**

$$P_{dynamic} = P_{xbar,compute} + P_{buffer,access} + P_{noc}$$

$$P_{xbar} = P_{DAC} + P_{ADC} + P_{wire} + P_{cell,read}$$

**静态功耗：**

$$P_{static} = N_{cell} \times P_{leakage/cell} + \sum N_{buffer} \times P_{leakage,buffer}$$

**总能量：**

$$E_{total} = (P_{dynamic} + P_{static}) \times T_{total}$$

或更精确地，逐层累加：

$$E_{total} = \sum_{layer} (P_{arch\_xbar}[i] \times T_{xbar}[i] + P_{ADC}[i] \times T_{ADC}[i] + \ldots)$$

---

## 11. SimConfig.ini 完整参数说明

### `[Device level]`

```ini
Device_Tech = 130         # nm，工艺节点
Device_Type = NVM         # NVM | SRAM
Device_Area = 1.44        # μm²，单元面积（参考: RRAM 1.44μm²@ISSCC）
Read_Level = 2            # 读电压档位数
Read_Voltage = 0,0.15     # V，各档读电压（逗号分隔，长度=Read_Level）
Write_Level = 2           # 写电压档位数
Write_Voltage = 0,3       # V，各档写电压
Read_Latency = 3.16       # ns，单次读延迟（NTHU ISSCC19）
Write_Latency = 10        # ns，单次写延迟
Device_Level = 2          # 阻态数（SRAM固定=2；NVM: 2=SLC, 4=MLC, 8=TLC）
Device_Resistance = 1e6, 1e4  # Ω，各档阻值，从HRS→LRS
Device_Variation = 1      # %，ΔR/R 变异幅度（仅 NVM）
Device_SAF = 0.1,0.1      # %，[SAH比例, SAL比例]（仅 NVM）
Read_Energy = 1.12e-15    # J/bit，SRAM读能量
Write_Energy = 1.6e-15    # J/bit，SRAM写能量
```

### `[Crossbar level]`

```ini
Xbar_Size = 256,256       # (行,列) 阵列尺寸
Subarray_Size = 256       # 子阵列行数（列数与Xbar相同，subarray_num = row/size）
Cell_Type = 1T1R          # 1T1R（有选通管）| 0T1R（无选通管，有泄漏路径）
Transistor_Tech = 130     # nm，外围晶体管工艺
Wire_Resistance = -1      # Ω | -1=默认 2.82Ω（文献引用）
Wire_Capacity = -1        # fF | -1=默认 1fF（文献引用）
Load_Resistance = -1      # Ω | -1=自动计算 √(R_HRS × R_LRS)
Area_Calculation = 0      # 0=用Device_Area计算；1=用工艺几何公式计算
```

### `[Interface level]`

```ini
DAC_Choice = 1            # -1=用户自定义；1~7=内置 ISAAC 设计
DAC_Area = 0              # μm² | 0=使用 Choice 对应默认值
DAC_Precision = 0         # bit | 0=默认
DAC_Power = 0             # W | 0=默认
DAC_Sample_Rate = 0       # GSamples/s | 0=默认
ADC_Choice = 6            # -1=用户自定义；1~9=内置设计（8=SA，数字PIM用）
ADC_Area = 0              # μm² | 0=默认
ADC_Precision = 0         # bit | 0=默认
ADC_Power = 0             # W | 0=默认
ADC_Sample_Rate = 0       # Samples/s | 0=默认
ADC_Interval_Thres = -1   # -1=自动生成量化区间；否则为电压阈值列表(V)
Logic_Op = -1             # -1=无附加逻辑；0=AND；1=OR；2=XOR（数字PIM扩展）
```

### `[Process element level]`

```ini
PIM_Type = 0              # 0=模拟PIM；1=数字PIM（1-bit ADC/DAC）
Xbar_Polarity = 2         # 1=单阵列正负共存；2=正/负分离双阵列
Sub_Position = 0          # Polarity=2时：0=模拟域相减（ADC前）；1=数字域相减（ADC后）
Group_Num = 1             # 每PE内的Crossbar组数（通道并行度）
DAC_Num = 128             # 每subarray每组的DAC数；0=自动根据面积推算
ADC_Num = 128             # 每subarray每组的ADC数；0=自动根据面积推算
PE_inBuf_Size = 0         # KB，PE输入缓冲；0=默认16KB
PE_inBuf_Area = 0         # μm²，0=自动计算
Tile_outBuf_Size = 0      # KB，Tile输出缓冲；0=默认
Tile_outBuf_Area = 0      # μm²
DFU_Buf_Size = 0          # KB，数据转发缓冲
DFU_Buf_Area = 0          # μm²
```

### `[Digital module]`

```ini
Digital_Frequency = 500   # MHz，所有数字逻辑的统一工作频率
Adder_Tech = 45           # nm，加法器工艺
Adder_Area = 0            # μm²，0=查表（按 tech，×bitwidth）
Adder_Power = 0           # W，0=查表
Multiplier_Tech = 45      # nm（扩展项，未完全启用）
Multiplier_Area = 0
Multiplier_Power = 0
ShiftReg_Tech = 65        # nm
ShiftReg_Area = 0         # μm²
ShiftReg_Power = 0        # W
Reg_Tech = 45             # nm
Reg_Area = 0              # μm²
Reg_Power = 0             # W
JointModule_Tech = 45     # nm
JointModule_Area = 0      # μm²，0=查表（按位宽×工艺缩放(tech/65)²）
JointModule_Power = 0     # W，0=查表
```

### `[Tile level]`

```ini
PE_Num = 2,2              # (行,列)，每Tile中PE数组；0,0=默认4×4
Pooling_shape = 3,3       # (行,列) 池化核大小；0,0=默认3×3
Pooling_unit_num = 64     # Tile内并行池化单元数；0=默认64
Pooling_Tech = 65         # nm；0=默认65nm
Pooling_area = 0          # μm²；0=自动
Tile_Adder_Num = 0        # 0=自动计算；x=手动指定
Tile_Adder_Level = 0      # 加法树最大层数；0=自动
Tile_ShiftReg_Num = 0     # 0=自动
Tile_ShiftReg_Level = 0
Inter_Tile_Bandwidth = 20     # Gbps，Tile间通信带宽
Intra_Tile_Bandwidth = 1024   # Gbps，Tile内PE间通信带宽
Tile_outBuf_Size = 0      # KB（与PE level同名键，以此处为准）
Tile_outBuf_Area = 0
DFU_Buf_Size = 0
DFU_Buf_Area = 0
```

### `[Architecture level]`

```ini
Buffer_Choice = 1         # 1=SRAM；2=DRAM；3=RRAM
Buffer_Technology = 90    # nm，全局缓冲工艺
Buffer_ReadPower = 0      # mW，0=自动
Buffer_WritePower = 0     # mW
Buffer_Bitwidth = 64      # bit，全局缓冲总线位宽；0=默认256bit
LUT_Capacity = 1          # Mb，查找表容量
LUT_Area = 0              # mm²
LUT_Power = 0             # mW
LUT_Bandwidth = 0         # Mb/s
Tile_Connection = 2       # 0=正常；1=蛇形；2=回字形；3=zigzag
Tile_Num = 64,64          # 芯片上Tile网格；0,0=默认8×8
```

### `[Algorithm Configuration]`

```ini
Weight_Polarity = 1       # 权重极性处理方式（1或2）
Simulation_Level = 0      # 0=行为级（快）；1=估计级（需具体权重，慢但准确）
NoC_enable = 0            # 0=不调用BookSim；1=调用BookSim做NoC仿真
```

---

## 12. 已知代码缺陷与注意事项

在阅读与使用源码时，以下几处存在潜在 bug 或设计不一致，需要特别注意：

| 位置 | 问题描述 | 影响 |
|---|---|---|
| `Device.py`：`calculate_device_write_power` | 使用 `self.type`，但属性名应为 `self.device_type` | NVM 写功耗调用时 `AttributeError` |
| `Device.py`：NVM 分支属性名 | 变异属性名为 `decice_variation`（拼写错误），SRAM 分支为 `device_variation` | 跨分支引用会出错 |
| `PE.py`：`calculate_DAC_num` | 使用裸变量 `subarray_num`，应为 `self.subarray_num` | 可能 `NameError`（取决于作用域） |
| `PE.py`：`calculate_PE_read_power` 第627行 | 使用 `PE_iReg.shiftreg_power`，`reg` 类无此属性 | 应为 `PE_shiftreg.shiftreg_power` |
| `DAC.py`：Choice 6 | 功耗值为 `0.4992`，其他选项均含 `×1e-3`，疑似缺少量纲 | 8-bit DAC 功耗高估约 **1000 倍** |
| `Crossbar.py`：SRAM 分支输出函数 | `xbar_output()` 打印 `xbar_load_resistance`，SRAM `__init__` 中未定义该属性 | 仅 output 函数出错，不影响计算路径 |
| `Tile.py`：第395–475行 | `calculate_tile_write_power` 等方法被包裹在三引号字符串中，**不可执行** | Tile 级写功耗/能量无法直接计算 |
| `is_Rratio` 逻辑 | `Weight_update` 中 `is_Rratio` 启用但 `is_Variation=False` 时，`temp_resistance` 恒为 0 | R 比例独立建模实际未实现，效果与不开变异相同 |

---

## 13. 与 NeuroSim 的学术比较

| 维度 | MNSIM 2.0 | NeuroSim / DNN+NeuroSim |
|------|-----------|------------------------|
| **开发机构** | 清华大学 NICS Lab | 亚利桑那州立大学（Shimeng Yu 课题组）|
| **建模粒度** | 行为级（Behavior-Level）| 电路宏模型级（Circuit-Level Macro）|
| **覆盖范围** | 模拟 + 数字 PIM（统一框架）| 主要面向模拟CIM，后续扩展数字 |
| **验证精度** | 3.8–5.5%（流片宏单元） | <1%（经PDK校准后）|
| **软件集成** | 集成完整训练+量化流 | 与 PyTorch 集成，侧重推断评估 |
| **调度灵活性** | 通用调度接口，支持 TCG | 相对固定数据流 |
| **主要优势** | 系统级 DSE、软硬件协同、统一模型 | 电路精度高、广泛工业用户（Intel/Samsung）|
| **主要局限** | 通信理想化、Transformer 支持弱 | 建模开销大、扩展性有限 |

**核心哲学差异**：NeuroSim 更适合**电路级精度验证和单器件特性分析**；MNSIM 2.0 更适合**跨类型 PIM 架构的系统级 DSE 和算法-硬件协同优化**。

---

## 14. 验证方法与精度

MNSIM 2.0 使用**两个实际流片的 PIM 宏单元**进行验证：

| 验证对象 | 工艺 | 阵列类型 | 建模误差 |
|---------|------|---------|---------|
| PIM Macro 1 | 定制工艺 | 模拟 RRAM crossbar | ~3.8% |
| PIM Macro 2 | 定制工艺 | 数字 SRAM-CIM | ~5.5% |

**误差来源分析：**

| 误差来源 | 估计贡献 | 对应代码简化 |
|---------|---------|------------|
| 解析模型对非线性效应的线性化近似 | ~2% | `I = G × V`（欧姆定律，忽略 RRAM 非线性） |
| IR drop 建模的激活模式无关假设 | ~1.5% | 基于平均电流的解析式 |
| ADC/DAC 实际非线性被忽略 | ~1% | 均匀量化，无 DNL/INL |
| 温度效应未建模 | <0.5% | 室温恒定假设 |

---

## 15. 可优化方向全景分析（研究机会）

### 15.1 物理器件层优化

#### 🔴 高优先级：非线性 IV 模型

**现状**：MNSIM 使用线性欧姆定律 `I = G × V`，隐含 G 为常数的假设。

**真实情况**：RRAM 的 IV 特性呈现明显非线性，典型物理模型：

```
双曲正弦模型：  I = I₀ × sinh(V / V₀)
Simmons 隧穿：  I = A × V × exp(−B/V)
Power Law：     I = G₀ × V^α  (α ≠ 1)
```

**影响**：高压输入时实际电流被低估（功耗低估）；MVM 结果出现非线性偏差（精度高估）；精度方差被低估。

#### 🔴 高优先级：动态电导变化模型

**现状**：σ（variation）是固定常数，与写次数、温度、保留时间无关。

**真实情况**：

```
σ(G) = f(n_write, T, t_retention, G_state)
  - 写次数越多 (n_write ↑) → σ ↑（疲劳效应）
  - 温度越高 (T ↑) → σ ↑（热激活，Arrhenius 模型）
  - 保留时间越长 (t ↑) → G 漂移（非高斯分布）
  - LRS/HRS 的 σ 不同（非对称）
```

**改进方案**：引入状态方程 `dG/dt = f(V, G, T)`，用 Arrhenius 模型描述温度依赖性。

#### 🟡 中优先级：自热效应（Self-Heating）

**现状**：温度完全不建模，假设室温恒定。

**真实情况**：大规模计算时，功耗密度导致局部温升可达 30-50°C，温升改变电导、加速 retention 漂移、影响 ADC 精度。

**改进方案**：集成热阻网络（Thermal Resistance Network）模型。

#### 🟡 中优先级：Stuck-at Fault 的时变模型

**现状**：SAF 比例是固定参数。

**真实情况**：SAF 比例随写次数增加而增大，遵循 Weibull 分布：

$$P_{SAF}(n) = 1 - \exp\left(-\left(\frac{n}{n_{char}}\right)^\beta\right)$$

#### 🟡 中优先级：读扰动（Read Disturb）累积

**现状**：完全不建模。

**真实情况**：频繁读操作会累积地改变 RRAM 状态，导致推断精度随推断次数缓慢下降（边缘长期部署场景不可忽视）。

---

### 15.2 电路外围层优化

#### 🔴 高优先级：ADC 非理想性建模

**现状**：均匀量化，无失调、无增益误差、无 DNL/INL。

**真实 SAR ADC 的非理想性：**

```
DNL（微分非线性）：每个量化步长不等宽
INL（积分非线性）：累积误差导致系统性偏差
Offset Error：ADC 输入范围偏移
Gain Error：量化斜率偏差
Thermal Noise：随机噪声底限
```

**影响**：ADC 非理想性导致**系统性偏差**而非随机噪声，精度损失分布特征完全不同。

#### 🔴 高优先级：IR Drop 的激活模式依赖

**现状**：IR drop 用平均电流的简化解析式，与具体输入无关。

**真实情况**：
- 不同输入导致不同的 BL 电流分布
- IR drop 是输入 pattern 的强相关函数
- 对某些输入 pattern 误差极大（worst-case），对另一些几乎无误差（best-case）
- 这导致精度具有**输入依赖性**，MNSIM 完全忽略了这个效应

**改进方案**：引入基于有限元或等效电路的 2D IR drop 计算模型。

#### 🟡 中优先级：BL/WL 寄生电容对延迟的影响

**现状**：延迟模型中 BL 充放电基于理想电容值。

**真实情况**：随阵列规模增大，BL 寄生电容非线性增大（布线密度效应），导致大阵列的实际延迟远高于线性外推值。

---

### 15.3 架构与调度层优化

#### 🔴 高优先级：数据依赖的通信延迟建模

**现状**：假设完全异步通信，数据计算完立即可用。

**真实情况**：
- ResNet 的残差连接需要等待两条并行路径都完成才能做加法
- Transformer 的 attention 计算 QKV 三者有数据依赖
- MNSIM 对这类有等待关系的结构**严重低估延迟**（ResNet 误差可达 53%）

#### 🔴 高优先级：稀疏性利用

**现状**：不支持稀疏计算，零权重仍然消耗计算资源。

**真实情况**：经过剪枝的 NN 有 50%-90% 的权重为零，稀疏 PIM 可通过门控（gating）跳过零值计算，MNSIM 对稀疏模型能耗预测严重偏高。

#### 🟡 中优先级：可重构数据流建模

**现状**：PE 功能固定（只能做 pooling 或 MVMUL，不能组合）。

**真实情况**：现代 PIM 芯片支持可重构数据流，PE 的计算序列是可编程的，固定数据通路限制了 MNSIM 对新型芯片架构的建模能力。

#### 🟡 中优先级：Transformer/LLM 支持

**现状**：主要支持 CNN，对 Transformer 的支持很弱。

**真实情况**：
- Attention 的 Q×K^T 是动态矩阵乘（权重非静止），PIM 优势完全不同于 CNN
- KV Cache 的存储访问模式特殊
- 大模型层数多、权重大，需要多 Tile/Bank 协作，通信开销建模完全不同

---

### 15.4 算法与训练层优化

#### 🟡 中优先级：先进量化方法集成

**现状**：主要支持均匀量化（PTQ/QAT 基础版本）。

**可集成的先进方法：**
- **GPTQ**：基于 Hessian 的权重量化，大模型低精度推断
- **AWQ**：激活感知量化，保护关键通道
- **SmoothQuant**：权重/激活联合平滑，改善量化难度
- **ADAROUND**：自适应舍入，减少量化误差累积

#### 🟡 中优先级：更真实的 Noise-Aware Training

**现状**：noise injection 只注入简单高斯噪声。

**改进方向**：
- 将非线性 IV 的误差分布注入训练（与物理层改进联动）
- 使用真实器件测量的噪声分布（非高斯）
- 对抗式噪声训练（worst-case noise，提升鲁棒性）

---

### 15.5 系统 DSE 层优化

#### 🔴 高优先级：代理模型（Surrogate Model）加速 DSE

**现状**：MNSIM 每次仿真都需要完整执行所有模块，没有缓存或学习机制。

**改进方案（贝叶斯优化 + 高斯过程代理模型）：**

```python
class SurrogateAcceleratedDSE:
    def __init__(self, simulator):
        self.sim = simulator
        self.gp = GaussianProcessRegressor()
        self.X_obs, self.Y_obs = [], []
    
    def suggest_next_design(self):
        return maximize_EI(self.gp, self.X_obs)  # 最大化 Expected Improvement
    
    def run_iteration(self, x):
        y = self.sim.evaluate(x)  # 真实仿真（昂贵，每次需要完整执行）
        self.X_obs.append(x); self.Y_obs.append(y)
        self.gp.fit(self.X_obs, self.Y_obs)
        return y
```

**预期收益**：从穷举 10 万次仿真 → 贝叶斯优化 200-500 次仿真找到接近最优解（100-500× 加速）。

#### 🔴 高优先级：多目标 Pareto 前沿探索

**现状**：MNSIM 只能给出单一配置的 PPA+精度，没有多目标优化能力。

**改进方案**：集成 NSGA-II/NSGA-III，输出 PPA 与精度的 Pareto 前沿，让设计者从 Pareto 集合中选择最优折中点。

#### 🟡 中优先级：迁移学习辅助的跨场景 DSE

**场景**：换一个工艺节点或换一个 NN 模型时，之前积累的仿真数据能否复用？

**方案**：Meta-Learning / Transfer Bayesian Optimization，将旧任务的 GP 先验迁移到新任务，大幅减少冷启动仿真次数。

#### 🟡 中优先级：物理信息约束的设计空间剪枝

```python
def is_feasible(config):
    # 约束1：IR drop < 10% Vdd
    if estimated_ir_drop(config.array_row, config.input_current) > 0.1 * Vdd:
        return False
    # 约束2：ADC 精度足以区分最小电导差
    if config.adc_bits < required_adc_bits(config.weight_bits, config.variation):
        return False
    return True
```

### 优化方向优先级总结

| 优先级 | 方向 | 预期影响 | 工程难度 |
|--------|------|---------|---------|
| 🔴 最高 | 非线性 IV 模型 | 精度预测误差降低 2-3% | 中 |
| 🔴 最高 | 动态电导变化 | 长期精度预测更真实 | 中高 |
| 🔴 最高 | ADC 非理想性 | 系统性偏差建模 | 中 |
| 🔴 最高 | IR Drop 激活依赖 | 大阵列精度预测改善 | 高 |
| 🔴 最高 | Surrogate Model DSE | 探索效率提升 100-500× | 中 |
| 🔴 最高 | 多目标 Pareto 优化 | 设计决策质量提升 | 中 |
| 🟡 中 | 自热效应 | 功耗建模完整性 | 高 |
| 🟡 中 | 稀疏性支持 | 剪枝模型能耗预测准确 | 中 |
| 🟡 中 | Transformer 支持 | 覆盖 LLM 场景 | 高 |
| 🟡 中 | 先进量化方法 | 精度上限提升 | 中 |

---

## 16. 总结：MNSIM 2.0 的设计权衡地图

MNSIM 2.0 在每一个关键设计节点上都做出了 **"仿真速度 vs. 物理保真度"** 的权衡选择：

| 设计决策 | MNSIM 的选择 | 代价 | 研究机会 |
|---------|------------|------|---------|
| 建模粒度 | 行为级 | 3.8-5.5% 误差 | 在关键路径引入更精确模型 |
| IV 模型 | 线性欧姆定律 | 忽略非线性（尤其 RRAM） | 替换为 sinh/lookup 模型 |
| 器件变化 | 固定高斯噪声 | 忽略写疲劳、温度、保留退化 | 引入状态方程 |
| IR Drop | 平均电流解析式 | 忽略激活模式依赖 | 2D 有限元/等效电路 |
| ADC/DAC | 查表+均匀量化 | 忽略 DNL/INL/Offset | 引入电路级非线性模型 |
| 通信模型 | 静态解析+曼哈顿距离 | 无动态调度冲突/数据依赖 | 事件驱动或数据依赖建模 |
| DSE 能力 | 无，手动配置 | 无法自动探索设计空间 | Surrogate Model + 多目标优化 |
| 验证方式 | 2 个流片宏单元 | 覆盖范围有限 | 更多工艺/器件/NN类型验证 |

**最终结论**：MNSIM 2.0 是一个**工程上成熟、学术上有贡献**的 PIM 仿真工具，其核心价值在于**统一建模框架 + 软硬件协同闭环 + 系统级 DSE 支持**。但其物理建模的保真度存在系统性的简化假设，这些假设在**大阵列、非理想器件、现代 NN 架构（Transformer）、以及设计空间自动探索**等场景下会导致显著误差或功能缺失。

---

*报告生成时间：2026年4月7日*  
*基于：IEEE TCAD 2023 论文（DOI: 10.1109/TCAD.2023.3251696）+ GitHub thu-nics/MNSIM-2.0 源码逐行分析*  
*综合来源：MNSIM_2.0_深度分析报告.md + MNSIM_Architecture_Analysis.md*
