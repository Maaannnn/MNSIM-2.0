# MNSIM-2.0 芯片结构建模详细技术文档

> 基于源码逐行分析，涵盖从器件到架构的完整五层硬件层次，包含所有参数定义、物理建模公式与软件实现细节。

---

## 目录

1. [整体层次结构](#1-整体层次结构)
2. [第一层：器件层 Device](#2-第一层器件层-device)
3. [第三层：接口层 ADC / DAC](#3-第三层接口层-adc--dac)
4. [第四层：Crossbar 阵列层](#4-第二层crossbar-阵列层)
5. [第五层：处理单元层 ProcessElement (PE)](#5-第四层处理单元层-processelement-pe)
6. [数字辅助模块](#6-数字辅助模块)
7. [第六层：Tile 层](#7-第五层tile-层)
8. [第七层：芯片架构层](#8-第六层芯片架构层)
9. [SimConfig.ini 完整参数说明](#9-simconfigini-完整参数说明)
10. [已知代码缺陷与注意事项](#10-已知代码缺陷与注意事项)

---

## 1. 整体层次结构

MNSIM-2.0 的硬件建模采用自下而上的六层继承/组合体系：

```
┌─────────────────────────────────────────────┐
│              芯片架构层（Architecture）        │
│  Tile_Num × Tile，TCG映射，NoC互联            │
├─────────────────────────────────────────────┤
│              Tile 层（tile）                  │
│  PE_Num[0] × PE_Num[1] 个 PE，               │
│  Buffer，Pooling，JointModule                 │
├─────────────────────────────────────────────┤
│         处理单元层（ProcessElement）           │
│  group_num 组，每组含若干 Crossbar             │
│  + ADC + DAC + 数字控制逻辑                   │
├─────────────────────────────────────────────┤
│    接口层（ADC / DAC）  ←→  Crossbar 阵列层    │
│  模拟/数字转换接口          存储计算阵列         │
├─────────────────────────────────────────────┤
│              器件层（Device）                  │
│  NVM 多级阻态 / SRAM 单比特存储单元             │
└─────────────────────────────────────────────┘
```

**Python 类继承关系：**

```python
device
  └── crossbar(device)
        └── ProcessElement(crossbar, DAC, ADC)
              └── tile(ProcessElement)
```

**注：** 代码中没有单独的 `chip` 类，芯片级别通过 `SimConfig.ini` 的 `Tile_Num` 参数和 `TCG`（Tile Connection Graph）来表达。

---

## 2. 第一层：器件层 Device

**文件：** `MNSIM/Hardware_Model/Device.py`  
**类：** `class device`

器件层是整个建模体系的物理基础，对应单个存储单元（Cell）的电学特性。

### 2.1 配置参数（来自 `[Device level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Device_Tech` | `device_tech` | 130 | nm | 工艺节点 |
| `Device_Type` | `device_type` | `NVM` | — | 器件类型：`NVM` 或 `SRAM` |
| `Device_Area` | `device_area` | 1.44 | μm² | 单个存储单元面积 |
| `Read_Level` | `device_read_voltage_level` | 2 | — | 读电压档位数量 |
| `Read_Voltage` | `device_read_voltage` | `[0, 0.15]` | V | 各档读电压列表（长度 = Read_Level） |
| `Write_Level` | `device_write_voltage_level` | 2 | — | 写电压档位数量 |
| `Write_Voltage` | `device_write_voltage` | `[0, 3]` | V | 各档写电压列表 |
| `Read_Latency` | `device_read_latency` | 3.16 | ns | 单次读操作延迟 |
| `Write_Latency` | `device_write_latency` | 10 | ns | 单次写操作延迟 |

#### NVM 专属参数

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Device_Level` | `device_level` | 2 | — | 阻态档位数（MLC 精度位数 = log₂(Device_Level)） |
| `Device_Resistance` | `device_resistance` | `[1e6, 1e4]` | Ω | 各阻态对应电阻值（从 HRS 到 LRS） |
| `Device_Variation` | `decice_variation` | 1 | % | 器件变异幅度，即 ΔR/R 的百分比（**注意属性名拼写错误**） |
| `Device_SAF` | — | `[0.1, 0.1]` | % | Stuck-At-HRS 和 Stuck-At-LRS 的故障比例 |

#### SRAM 专属参数

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Read_Energy` | `device_read_energy` | 1.12e-15 | J | 每 bit 读能量 |
| `Write_Energy` | `device_write_energy` | 1.6e-15 | J | 每 bit 写能量 |

SRAM 分支中等效阻值硬编码为 `device_resistance = [1.6e6, 1.6e6]`（HRS = LRS，代表无 IV 特性差异），`device_variation = 0`。

### 2.2 物理建模：读功耗计算

**方法：** `calculate_device_read_power(self, R=None, V=None)`

NVM 采用欧姆热耗散模型 \(P = V^2 / R\)：

**等效电阻（默认，调和加权）：**
$$R_{eff} = \frac{R_{HRS} \cdot R_{LRS}}{0.67 \cdot R_{LRS} + 0.33 \cdot R_{HRS}}$$

> 物理含义：器件在读操作时，多数时间（67%）处于低阻（LRS=数据1），少数时间（33%）处于高阻（HRS=数据0）的加权平均等效阻

**等效读电压（默认，RMS 加权）：**
$$V_{eff} = \sqrt{0.9 \cdot V_{read,0}^2 + 0.1 \cdot V_{read,N-1}^2}$$

**读功耗：**
$$P_{device,read} = \frac{V_{eff}^2}{R_{eff}}$$

### 2.3 物理建模：写功耗计算

**方法：** `calculate_device_write_power(self, R=None, V=None)`

**等效电阻（默认，几何平均）：**
$$R_{write} = \sqrt{R_{HRS} \cdot R_{LRS}}$$

**等效写电压（默认，算术平均）：**
$$V_{write} = \frac{V_{write,0} + V_{write,N-1}}{2}$$

**写功耗：**
$$P_{device,write} = \frac{V_{write}^2}{R_{write}}$$

### 2.4 SRAM 的功耗计算方式

SRAM 不用 \(V^2/R\) 模型，而用每 bit 能量直接除以延迟：

$$P_{SRAM,read} = \frac{E_{read,per\_bit}}{t_{read\_latency}}$$

---

## 3. 第三层：接口层 ADC / DAC

> 接口层在层次上介于 Crossbar 与 PE 之间，负责模拟域与数字域的转换。

### 3.1 DAC（数模转换器）

**文件：** `MNSIM/Hardware_Model/DAC.py`  
**类：** `class DAC`

DAC 将数字激活值转换为施加在 Crossbar 字线（WL）上的模拟电压。

#### 配置参数（来自 `[Interface level]`）

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `DAC_Choice` | 1 | 选择预定义设计（1–7）或 -1（用户自定义） |
| `DAC_Area` | 0 | 0 = 使用内置表格；否则用户指定（μm²） |
| `DAC_Precision` | 0 | 0 = 内置表格；否则用户指定（bit） |
| `DAC_Power` | 0 | 0 = 内置表格；否则用户指定（W） |
| `DAC_Sample_Rate` | 0 | 0 = 内置表格；否则用户指定（GSamples/s） |

**数字 PIM 特殊处理（`PIM_type == 1`）：** 强制 `DAC_choice = 1`（1-bit DAC）。

#### 七种预定义 DAC 设计查找表（ISAAC 论文来源）

| Choice | Precision (bit) | Area (μm²) | Power (W) | Sample Rate (GSamples/s) |
|---|---|---|---|---|
| 1 | 1 | 0.166 | 3.9×10⁻⁶ | 1 |
| 2 | 2 | 0.332 | 7.8×10⁻⁶ | 1 |
| 3 | 3 | 0.664 | 1.56×10⁻⁵ | 1 |
| 4 | 4 | 1.328 | 3.12×10⁻⁵ | 1 |
| 5 | 6 | 5.312 | 1.248×10⁻⁴ | 1 |
| 6 | 8 | 21.248 | **0.4992**（疑似缺 ×10⁻³） | 1 |
| 7 | 1 | 0.166 | 3.9×10⁻⁶ | 1 |

#### 延迟与能量公式

$$t_{DAC} = \frac{1}{f_{sample}} \times (N_{bit} + 2)$$

$$E_{DAC} = t_{DAC} \times P_{DAC}$$

### 3.2 ADC（模数转换器）

**文件：** `MNSIM/Hardware_Model/ADC.py`  
**类：** `class ADC`

ADC 将 Crossbar 位线（BL）的模拟电流/电压求和结果量化为数字值。

#### 配置参数（来自 `[Interface level]`）

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `ADC_Choice` | 6 | 选择预定义设计（1–9）或 -1（用户自定义） |
| `ADC_Area` | 0 | 0 = 内置表格；否则用户指定（μm²） |
| `ADC_Precision` | 0 | 0 = 内置表格；否则用户指定（bit） |
| `ADC_Power` | 0 | 0 = 内置表格；否则用户指定（W） |
| `ADC_Sample_Rate` | 0 | 0 = 内置表格；否则用户指定（Samples/s） |
| `ADC_Interval_Thres` | -1 | -1 = 自动生成；否则手动指定量化区间电压列表（V） |
| `Logic_Op` | -1 | 附加逻辑运算：-1无，0=AND，1=OR，2=XOR |

**数字 PIM 特殊处理（`PIM_type == 1` 且 `ADC_choice != -1`）：** 强制 `ADC_choice = 8`（Sense Amplifier，1-bit 比较器）。

#### 九种预定义 ADC 设计查找表

| Choice | Precision (bit) | Area (μm²) | Power (W) | Sample Rate (GSamples/s) | 类型说明 |
|---|---|---|---|---|---|
| 1 | 10 | 1600 | 6.92×10⁻³ | 1.5 | 高精度 |
| 2 | 8 | 1200 | 2×10⁻³ | 1.28 | 通用 |
| 3 | 8 | 1650 | 4×10⁻³ | 1.1 | 通用 |
| 4 | 6 | 580 | 1.26×10⁻³ | 1 | 低功耗 |
| 5 | 8 | 1650 | 4×10⁻³ | 1.1 | 通用 |
| 6 | 6 | 1650 | 1.26×10⁻³ | 1 | 通用（**默认**） |
| 7 | 4 | 500 | 0.7×10⁻³ | 1 | 低精度 |
| 8 | 1 | 1 | 0.1086×15×10⁻⁶ | 1 | Sense Amplifier（数字 PIM） |
| 9 | 8 | 15899 | 8×0.0073×10⁻³ | 6 | 高速 |

**附加逻辑面积：**
- `Logic_Op = 0/1`：面积 += 17.28 × 0.18 μm²
- `Logic_Op = 2`：面积 += 19.2 × 0.18 μm²

#### 延迟公式（三种情况）

```python
if ADC_precision == 1:
    ADC_latency = 1 / ADC_sample_rate                          # SA：单周期
elif ADC_choice == 9:
    ADC_latency = 1 / ADC_sample_rate * (2 ** ADC_precision)   # 高速 ADC 特例
else:
    ADC_latency = 1 / ADC_sample_rate * (ADC_precision + 2)    # 标准逐次逼近型
```

#### ADC 量化区间生成（`config_ADC_interval`）

当 `ADC_interval[0] == -1` 时自动生成，共 `2^N - 1` 个区间边界：

设激活字线数为 `WL_num`，每级步长 `step = ceil(WL_num / 2^N)`：

$$V_{max} = WL\_num \times \frac{V_{in,max}}{R_{LRS}} \times R_{load}$$

第 i 个区间边界：
$$\text{interval}[i] = 0.5 \times \left[ \frac{(k-1) V_{in,max}}{R_{LRS}} R_s + \frac{(WL-k+1) V_{in,max}}{R_{LRS}} R_s + \frac{k \cdot V_{in,max}}{R_{LRS}} R_s + \frac{(WL-k) V_{in,0}}{R_{HRS}} R_s \right]$$

其中 k = (i+1) × step，Rs = Load_Resistance。

---

## 4. 第二层：Crossbar 阵列层

**文件：** `MNSIM/Hardware_Model/Crossbar.py`  
**类：** `class crossbar(device)`

Crossbar 是存内计算的核心运算单元，用电阻阵列实现向量矩阵乘法（VMM）。

### 4.1 配置参数（来自 `[Crossbar level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 单位 | 物理含义 |
|---|---|---|---|---|
| `Xbar_Size` | `xbar_size = [xbar_row, xbar_column]` | `[256, 256]` | — | 阵列行数 × 列数 |
| `Subarray_Size` | `subarray_size` | 256 | rows | 子阵列行数（列数与 Crossbar 相同） |
| `Cell_Type` | `cell_type` | `1T1R` | — | 存储单元类型：`1T1R`（有选通管）或 `0T1R`（无选通管） |
| `Transistor_Tech` | `transistor_tech` | 130 | nm | 外围晶体管工艺节点 |
| `Wire_Resistance` | `wire_resistance` | -1 | Ω | 字/位线单位电阻，-1 = 使用默认值 2.82 Ω |
| `Wire_Capacity` | `wire_capacity` | -1 | fF | 字/位线单位电容，-1 = 使用默认值 1 fF |
| `Load_Resistance` | `xbar_load_resistance` | -1 | Ω | 位线负载电阻，-1 = √(R_HRS × R_LRS) |
| `Area_Calculation` | `area_calculation_method` | 0 | — | 0 = 用 Device_Area 计算；1 = 用工艺几何公式计算 |

**衍生参数：**
- `subarray_num = xbar_row / subarray_size`（子阵列数量）
- `xbar_simulation_level`：继承自 `[Algorithm Configuration]` 的 `Simulation_Level`

### 4.2 仿真级别分支

`xbar_simulation_level` 控制计算精度与模式：

**Level 0（Behavior 级，默认）：**
- 不依赖具体权重矩阵内容
- 仅记录已占用行列数（`xbar_num_write_row`，`xbar_num_read_column` 等）
- 电导矩阵/电压向量使用默认估算值（几何/RMS 平均）

**Level 1（Estimation 级）：**
- 使用实际权重数据（`xbar_write_matrix`、`xbar_read_matrix`）
- 电导矩阵：`conductance[i,j] = 1 / R[weight_level[i,j]]`
- 读电压向量：按输入激活值选择对应电平 `V_read[input_level]`
- 支持更精细的功耗估计（矩阵级 `G·V²` 求和）

### 4.3 面积计算（`calculate_xbar_area`）

**方法 0（使用 Device_Area，适合 NVM）：**

```
PIM_type != 0（数字 PIM）：
  xbar_area = xbar_row × xbar_column × device_area
            + xbar_row × (7.3×2.7 + 9.5×3.8) × (transistor_tech/65)²

PIM_type == 0（模拟 PIM）：
  xbar_area = xbar_row × xbar_column × device_area + 1150 × xbar_row
```

**方法 1（使用工艺几何，适合 SRAM 或精确评估）：**

```
SRAM：
  xbar_area = xbar_row × xbar_column × 5

0T1R（无选通管）：
  xbar_area = 4 × xbar_row × xbar_column × device_tech² × 1e-6

1T1R（有选通管，WL_ratio=3）：
  xbar_area = 3 × (WL_ratio + 1) × xbar_row × xbar_column × device_tech² × 1e-6
```

### 4.4 线路寄生参数（物理特性建模）

**线电阻默认值（`calculate_wire_resistance`）：**
```
若 wire_resistance < 0：wire_resistance = 2.82 Ω  （引自文献）
```

**线电容默认值（`calculate_wire_capacity`）：**
```
若 wire_capacity < 0：wire_capacity = 1 fF         （引自文献）
```

### 4.5 读延迟（`calculate_xbar_read_latency`）

读延迟由器件固有延迟与线路 RC 延迟两部分组成：

**线路延迟经验公式（对 1T1R 与 0T1R 相同）：**

$$size_{KB} = \frac{N_{row} \times N_{col}}{1024 \times 8}$$

$$t_{wire} = 0.001 \times \left( 2 \times 10^{-4} \times size^2 + 5 \times 10^{-6} \times size + 4 \times 10^{-14} \right) \quad \text{(ns)}$$

**总读延迟：**
$$t_{xbar,read} = t_{device,read} + t_{wire}$$

### 4.6 写延迟（`calculate_xbar_write_latency`）

假设同一行并行写入：
$$t_{xbar,write} = t_{device,write} \times N_{write\_rows}$$

### 4.7 读功耗（`calculate_xbar_read_power`）

**Level 0（行为级）：**

```
P_xbar_read = N_read_rows × N_read_cols × P_device_read

若 cell_type == "0T1R"（无选通管存在泄漏）：
  P_xbar_read += 0.25 × N_read_rows × (N_col - N_read_cols) × P_device_read(R_HRS)
  （未激活列按 1/4 功耗模拟泄漏电流）
```

**Level 1（估计级）：**

$$P_{xbar,read} = \sum_j \left( G_j \cdot \sum_i V_i^2 \right) = \mathbf{G}^T \cdot \mathbf{V}^2$$

其中 \(G_j = 1/R_j\)（每列电导），\(V_i\) 为第 i 个输入激活电压。

0T1R 额外泄漏：
$$P_{leak} = 0.25 \times \sum_{j \notin active} \frac{1}{R_{LRS}} \cdot V_i^2$$

### 4.8 写功耗（`calculate_xbar_write_power`）

**Level 0：**
$$P_{xbar,write} = N_{write\_cols} \times P_{device,write}$$

**Level 1：**
$$P_{xbar,write} = \frac{\mathbf{G}_{write}^T \cdot \mathbf{V}_{write}^2}{N_{write\_rows}}$$

### 4.9 能量计算

$$E_{xbar,read} = \begin{cases} P_{xbar,read} \times t_{xbar,read} & \text{NVM} \\ N_{read\_rows} \times N_{read\_cols} \times E_{device,read} \times 10^6 & \text{SRAM} \end{cases}$$

$$E_{xbar,write} = \begin{cases} P_{xbar,write} \times t_{device,write} & \text{NVM（不含写线功耗）} \\ N_{write\_rows} \times N_{write\_cols} \times E_{device,write} \times 10^6 & \text{SRAM} \end{cases}$$

---

## 5. 第四层：处理单元层 ProcessElement (PE)

**文件：** `MNSIM/Hardware_Model/PE.py`  
**类：** `class ProcessElement(crossbar, DAC, ADC)`

PE 是完整的计算单元，包含若干 Crossbar 阵列组、DAC/ADC 接口、以及数字控制逻辑。

### 5.1 配置参数（来自 `[Process element level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 含义 |
|---|---|---|---|
| `PIM_Type` | `PIM_type_pe` | 0 | 0 = 模拟 PIM；1 = 数字 PIM（强制 1-bit 接口） |
| `Xbar_Polarity` | `Xbar_Polarity` | 2 | 1 = 单阵列存正负权重；2 = 正阵列 + 负阵列分开 |
| `Sub_Position` | `Sub_Position` | 0 | Polarity=2 时：0 = 模拟域相减（ADC前）；1 = 数字域相减（ADC后） |
| `Group_Num` | `group_num` | 1 | 每个 PE 内的 Crossbar 组数（用于通道并行） |
| `DAC_Num` | `PE_group_DAC_num`（初始值） | 128 | 每组每 subarray 的 DAC 数量；0 = 自动推算 |
| `ADC_Num` | `PE_group_ADC_num`（初始值） | 128 | 每组每 subarray 的 ADC 数量；0 = 自动推算 |
| `PE_inBuf_Size` | — | 0→默认 16 KB | PE 输入缓冲大小 |
| `Tile_outBuf_Size` | — | 0→默认 | Tile 输出缓冲大小（从 PE 级读取，逻辑上属于 Tile） |
| `DFU_Buf_Size` | — | 0→默认 | Data Forwarding Unit 缓冲大小 |

**衍生结构参数：**

```python
# Polarity = 1：单阵列
PE_multiplex_xbar_num = [1, 1]

# Polarity = 2：正负双阵列
PE_multiplex_xbar_num = [1, 2]

# PE 总 Crossbar 数量
PE_xbar_num = group_num × multiplex[0] × multiplex[1]

# PE 总 ADC / DAC 数量
PE_ADC_num = group_num × PE_group_ADC_num
PE_DAC_num = group_num × PE_group_DAC_num
```

### 5.2 ADC/DAC 数量自动推算

当 `ADC_Num = 0` 时，根据面积比例自动计算可以放下多少个 ADC（**物理约束**）：

**ADC 数量自动推算（`calculate_ADC_num`）：**

$$PE\_group\_ADC\_num = \min\left( \lceil (Sub\_Position+1) \times \frac{\sqrt{A_{xbar}} \times N_{pol,neg}}{\sqrt{A_{ADC}}} \rceil, \; N_{col} \right) \times N_{subarray}$$

其中 \(A_{xbar}\) 是单个 Crossbar 面积，\(A_{ADC}\) 是单个 ADC 面积，物理意义是：**在 Crossbar 底边长度内能排下的 ADC 数量**。

**输出 MUX 比（多列共享一个 ADC 时的分时复用度）：**
$$output\_mux = \left\lceil \frac{N_{col}}{PE\_group\_ADC\_num / N_{subarray}} \times (Sub\_Position + 1) \right\rceil$$

**DAC 数量自动推算（`calculate_DAC_num`）：**

$$PE\_group\_DAC\_num = \min\left( \lceil \frac{\sqrt{A_{xbar}} / N_{subarray} \times N_{pol,pos}}{\sqrt{A_{DAC}}} \rceil, \; subarray\_size \right) \times N_{subarray}$$

**输入 DEMUX 比（多行共享一个 DAC 时的分时复用度）：**
$$input\_demux = \left\lceil \frac{subarray\_size \times N_{pol,pos}}{PE\_group\_DAC\_num / N_{subarray}} \right\rceil$$

### 5.3 MUX / DEMUX 面积与功耗

晶体管面积基准：
$$A_{transistor} = 10 \times transistor\_tech^2 \times 10^{-6} \quad \text{(μm²)}$$

面积/功耗字典（按 demux/mux 比值档位）：

| 比值档位 | 面积（×Aₜ） | 功耗（×Pₜ）（Pₜ = 10×1.2/1e9 W） |
|---|---|---|
| 2 | 8 | 8 |
| 4 | 24 | 24 |
| 8 | 72 | 72 |
| 16 | 216 | 216 |
| 32 | 648 | 648 |
| 64 | 1944 | 1944 |

### 5.4 PE 内加法树结构（`calculate_inter_PE_connection`）

对 `group_num` 组进行二叉树合并，计算所需加法器总数：

```python
temp = group_num
PE_adder_num = 0
while temp / 2 >= 1:
    PE_adder_num += int(temp / 2) * subarray_num
    temp = int(temp / 2) + temp % 2
```

即：对 group 数量进行二叉树折叠，每层加法器数量 = floor(group/2) × subarray_num。

### 5.5 PE 总面积组成

$$A_{PE} = A_{xbar,total} + A_{ADC,total} + A_{DAC,total} + A_{digital} + A_{input\_buf}$$

其中：
$$A_{xbar,total} = PE\_xbar\_num \times A_{xbar}$$
$$A_{ADC,total} = PE\_ADC\_num \times A_{ADC}$$
$$A_{DAC,total} = PE\_DAC\_num \times A_{DAC}$$
$$A_{digital} = A_{adder} + A_{shiftreg} + A_{demux} + A_{mux} + A_{iReg} + A_{oReg}$$
$$A_{adder} = PE\_group\_ADC\_num \times PE\_adder\_num \times A_{single\_adder}$$
$$A_{shiftreg} = PE\_ADC\_num \times A_{single\_shiftreg}$$

### 5.6 PE 读功耗组成（`calculate_PE_read_power_fast`）

各子模块功耗的比例关系：

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

**数字 PIM 时（`PIM_type == 1`）：** ADC/MUX/Adder/ShiftReg/oReg 均再乘以 `subarray_num`，因为每个 subarray 有独立的 SA（Sense Amplifier）。

### 5.7 PE 能效计算（`calculate_PE_energy_efficiency`）

这是 MNSIM 的核心性能指标计算方法：

**时间步数（分时复用次数）：**
$$multiple\_time = \left\lceil \frac{8}{DAC\_precision} \right\rceil$$

> 若 DAC 精度为 1-bit，则需要 8 个时间步才能完成 8-bit 输入激活的计算

**Decoder 延迟（DEMUX 控制，基于 1-to-8 decoder 级联）：**
$$t_{decoder} = m \times 0.27933 \text{ ns}$$
其中 m 通过 `Row_per_DAC` 除以 8 的循环次数决定。

**MUX 延迟（输出 MUX，基于 8-to-1 MUX 级联）：**
$$t_{mux} = m \times 32.744 \times 10^{-3} \text{ ns}$$

**各子模块延迟汇总：**
$$t_{xbar} = multiple\_time \times t_{xbar,read}$$
$$t_{DAC} = multiple\_time \times t_{DAC,latency}$$
$$t_{ADC} = multiple\_time \times t_{ADC,latency}$$
$$t_{iReg} = t_{digital\_period} + multiple\_time \times t_{digital\_period}$$
$$t_{shiftreg} = multiple\_time \times t_{digital\_period}$$
$$t_{demux} = multiple\_time \times t_{decoder}$$
$$t_{adder} = \lceil \log_2(group\_num) \rceil \times t_{digital\_period}$$
$$t_{mux} = multiple\_time \times t_{mux,latency}$$
$$t_{oReg} = t_{digital\_period}$$

**总 PE 延迟：**
$$t_{PE,total} = t_{xbar} + t_{DAC} + t_{ADC} + t_{iReg} + t_{shiftreg} + t_{demux} + t_{adder} + t_{mux} + t_{oReg}$$

**等效算力（GOPS）：**
$$GOPS = \frac{2 \times PE\_group\_DAC\_num \times PE\_group\_ADC\_num}{t_{PE,total}}$$

**能效（GOPS/W）：**
$$Efficiency = \frac{2 \times PE\_group\_DAC\_num \times PE\_group\_ADC\_num}{E_{PE,total}}$$

---

## 6. 数字辅助模块

这些模块是 PE 和 Tile 中数字逻辑部分的组成子单元，均通过 `[Digital module]` 配置。

### 6.1 Adder（加法器）

**文件：** `MNSIM/Hardware_Model/Adder.py`  
**类：** `class adder`

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Adder_Tech` | 45 nm | 工艺节点（支持 28/45/55/65/130 nm） |
| `Adder_Area` | 0 → 自动 | μm²；0 = 自动查表 |
| `Adder_Power` | 0 → 自动 | W；0 = 自动查表 |
| `Digital_Frequency` | 500 MHz | 数字电路工作频率 |
| `adder_bitwidth` | 8 bit | 加法器位宽（可由上层传入） |

**延迟：**
$$t_{adder} = \frac{1}{f_{digital}} \quad \text{（单个加法器一个时钟周期）}$$

**面积查找表（基于 14 晶体管全加器，×bitwidth）：**

| 工艺节点 | 单位面积（每 bit） |
|---|---|
| ≤ 28 nm | 10×14×28²/1e6 μm² |
| ≤ 45 nm | 10×14×45²/1e6 μm² |
| ≤ 55 nm | 10×14×55²/1e6 μm² |
| ≤ 65 nm | 1.42 μm²（实测值） |
| > 65 nm | 10×14×130²/1e6 μm² |

**功耗查找表：**

| 工艺节点 | 单位功耗（每 bit） |
|---|---|
| 65 nm | 3×10⁻⁷ W |
| 其余 | 2.5×10⁻⁹ W |

### 6.2 ShiftReg（移位寄存器）

**文件：** `MNSIM/Hardware_Model/ShiftReg.py`  
**配置：** `ShiftReg_Tech`（65 nm），`ShiftReg_Area`，`ShiftReg_Power`

用于在 PE 内部对多 bit ADC 输出进行移位累加（bit-serial MAC 的数字累加部分）。延迟同为一个数字时钟周期。

### 6.3 Reg（寄存器）

**文件：** `MNSIM/Hardware_Model/Reg.py`  
**配置：** `Reg_Tech`（45 nm），`Reg_Area`，`Reg_Power`

- **iReg**：PE 输入寄存器，存放当前时间步的激活值，位数 = DAC_precision
- **oReg**：PE 输出寄存器，存放 ADC 量化结果，位数 = ADC_precision

### 6.4 JointModule（合并模块）

**文件：** `MNSIM/Hardware_Model/JointModule.py`  
**类：** `class JointModule`

JointModule 用于 Tile 层面将多个 PE 的输出合并（加法/连接），等效于 Tile 内的跨 PE 加法树节点。

| 参数 | 默认值 | 说明 |
|---|---|---|
| `JointModule_Tech` | 45 nm | 工艺节点 |
| `JointModule_Area` | 0 → 自动 | μm² |
| `JointModule_Power` | 0 → 自动 | W |
| `jointmodule_bit` | 8 bit | 操作位宽（由上层传入） |

**延迟：**
$$t_{joint} = \frac{1}{f_{digital}}$$

**面积/功耗查找表（按位宽，带工艺缩放 `(tech/65)²`）：**

| 位宽 | 面积（μm²，@65nm） | 功耗（W，@65nm） |
|---|---|---|
| ≤ 4 bit | 182.88 | 1.39×10⁻⁴ |
| ≤ 8 bit | 353.76 | 2.64×10⁻⁴ |
| ≤ 12 bit | 385.44 | 3.67×10⁻⁴ |
| ≤ 16 bit | 512.16 | 4.97×10⁻⁴ |

**工艺缩放：** `area/power × (tech/65)²`

### 6.5 Buffer（SRAM 缓存）

**文件：** `MNSIM/Hardware_Model/Buffer.py`  
**类：** `class buffer`

Buffer 有三个层级（`buf_level`）：
- `1`：PE 输入缓冲（`PE_inBuf_Size`）
- `2`：Tile 输出缓冲（`Tile_outBuf_Size`）
- `3`：DFU 数据转发缓冲（`DFU_Buf_Size`）

**配置参数（来自 `[Architecture level]`）：**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Buffer_Choice` | 1 | 1 = SRAM；2 = DRAM；3 = RRAM |
| `Buffer_Technology` | 90 nm | 工艺节点（支持 <65/65–89/≥90 nm 三档） |
| `Buffer_Bitwidth` | 64 bit | 总线位宽（支持 64/128/256/512 bit 四档） |
| `Buffer_ReadPower` | 0 → 自动 | mW |
| `Buffer_WritePower` | 0 → 自动 | mW |

**索引机制：** 根据工艺（3档）× 容量（9档：2/4/8/16/32/64/128/256/512+ KB）× 位宽（4档）= 108 个预定义配置，通过 `self.index` 查找面积/功耗/延迟数组。

**读写延迟：**
$$t_{buf,read} = \left\lceil \frac{data \times 8}{buf\_bitwidth} \right\rceil \times buf\_cycle \quad \text{(ns)}$$

其中 `buf_cycle` 固定为 20 ns（代码中硬编码，注释掉了查表逻辑）。

**读写功耗：**
$$P_{buf,read} = P_{dynamic,read} + P_{leakage}$$
$$P_{dynamic,read} = \frac{E_{read\_per\_access}}{buf\_cycle} \times 10^3 \quad \text{(mW)}$$

**读写能量：**
$$E_{buf,read} = (E_{per\_access} + buf\_cycle \times P_{leakage} / 10^3) \times \left\lceil \frac{data \times 8}{bitwidth} \right\rceil \quad \text{(nJ)}$$

### 6.6 Pooling（池化单元）

**文件：** `MNSIM/Hardware_Model/Pooling.py`  
**类：** `class Pooling`

**配置参数（来自 `[Tile level]`）：**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `Pooling_shape` | `3,3` | 池化核尺寸（行,列），默认 3×3 |
| `Pooling_unit_num` | 64 | 每个 Tile 中并行池化单元数量 |
| `Pooling_Tech` | 65 nm | 池化单元工艺节点 |
| `Pooling_area` | 0 → 自动 | μm² |

**面积参考值（65 nm 工艺，3×3 核，64 个单元）：** 91917.16 μm²

工艺缩放：乘以 `(tech/65)²`，数量缩放：乘以 `unit_num/64`

**功耗参考值（@65nm, 3×3, 64 units）：** 3.082×10⁻³ W

**延迟：**
$$t_{pooling} = 100 \times \left\lceil \frac{inchannel}{Pooling\_unit\_num} \right\rceil \times \left\lceil \frac{insize}{Pooling\_size} \right\rceil \quad \text{(ns)}$$

---

## 7. 第五层：Tile 层

**文件：** `MNSIM/Hardware_Model/Tile.py`  
**类：** `class tile(ProcessElement)`

Tile 是加速器的基本调度单元，包含一个 PE 二维网格及相关输入/输出基础设施。

### 7.1 配置参数（来自 `[Tile level]`）

| 参数名（ini key） | 属性名（Python） | 默认值 | 含义 |
|---|---|---|---|
| `PE_Num` | `tile_PE_num` | `0,0` → `[4,4]` | Tile 内 PE 阵列尺寸（行×列）；0,0 = 默认 4×4 |
| `Pooling_shape` | — | `3,3` | 池化核尺寸 |
| `Pooling_unit_num` | — | 64 | 并行池化单元数 |
| `Pooling_Tech` | — | 65 nm | 池化工艺节点 |
| `Pooling_area` | — | 0 → 自动 | 池化面积（μm²） |
| `Tile_Adder_Num` | — | 0 → 自动 | Tile 级加法器数；0 = 自动计算 |
| `Tile_ShiftReg_Num` | — | 0 → 自动 | Tile 级移位寄存器数 |
| `Inter_Tile_Bandwidth` | — | 20 Gbps | Tile 间通信带宽 |
| `Intra_Tile_Bandwidth` | — | 1024 Gbps | Tile 内 PE 间通信带宽 |
| `Tile_outBuf_Size` | — | 0 → 默认 | Tile 输出缓冲大小（KB） |
| `DFU_Buf_Size` | — | 0 → 默认 | 数据转发单元缓冲大小（KB） |

**衍生参数：**
```python
tile_PE_total_num = tile_PE_num[0] × tile_PE_num[1]
```

Tile 内包含：
- `tile_PE_list`：二维列表，每个元素为一个 `ProcessElement` 实例
- `tile_jointmodule_list`：用于 PE 间合并的 JointModule 列表
- `tile_buffer`：输出 Buffer（buf_level=2）
- `DFU_buffer`：数据转发 Buffer（buf_level=3）
- `tile_pooling`：Pooling 单元实例

### 7.2 Tile 内 PE 间加法树（`calculate_intra_PE_connection`）

对 `tile_PE_total_num` 个 PE 的输出做二叉树合并：

```python
index = tile_PE_total_num
temp_num = 0
while index / 2 >= 1:
    temp_num += int(index / 2) + index % 2
    index = int(index / 2)

tile_adder_num = tile_shiftreg_num = tile_jointmodule_num = temp_num × PE_ADC_num
```

> 注意：这里把 Tile 级的加法/移位寄存器/JointModule 数量都设为相同值，反映了流水线式的 PE 输出合并树。

### 7.3 Tile 总面积组成

$$A_{Tile} = A_{xbar,all} + A_{ADC,all} + A_{DAC,all} + A_{digital,all} + A_{buffer} + A_{pooling}$$

各项为所有 PE 的对应面积之和：
$$A_{xbar,all} = \sum_{i,j} A_{xbar,PE[i][j]}$$

Tile 级额外数字面积：
$$A_{digital,Tile} = \sum_{PE} A_{demux,PE} + A_{mux,PE} + A_{adder,PE} + A_{shiftreg,PE} + A_{iReg,PE} + A_{oReg,PE} + A_{jointmodule} \times tile\_jointmodule\_num$$

Tile 级缓冲面积：
$$A_{buffer,Tile} = A_{outBuf} + A_{DFU\_buf}$$

### 7.4 Tile 读延迟（片内传输，`Tile_latency.py`）

Tile 内 PE 间的数据合并传输延迟：

$$t_{transfer,intra} = \frac{(L \times (N_{ADC\_prec} + t_{merge}) - \frac{t_{merge}(t_{merge}+1)}{2}) \times N_{read\_col}}{BW_{intra}}$$

其中：
- `L = total_level`：加法树层数（log₂(PE数)）
- `t_merge`：每层合并所需时钟数
- `N_ADC_prec`：ADC 精度（bit）
- `N_read_col`：需要传输的列数
- `BW_intra = Intra_Tile_Bandwidth`（Gbps）

### 7.5 Tile 读功耗组成（`calculate_tile_read_power_fast`）

| 子模块 | 功耗来源 |
|---|---|
| 全部 PE | `N_PE × P_PE_read × (max_group / group_num_total)` |
| JointModule | `(max_PE - 1) × ⌈max_col / output_mux⌉ × P_jointmodule` |
| Output Buffer（读） | `buf_rpower × 1e-3` |
| Output Buffer（写） | `buf_wpower × 1e-3` |
| Pooling | `Pooling_power`（仅 pooling 层） |

**汇总：**
$$P_{Tile,read} = P_{xbar,all} + P_{ADC,all} + P_{DAC,all} + P_{digital,all} + P_{buffer,Tile}$$

---

## 8. 第六层：芯片架构层

**主要文件：** `MNSIM/Mapping_Model/Tile_connection_graph.py`，`main.py`

此层无独立 Python 类，由 `SimConfig.ini` 的 `[Architecture level]` 参数和 TCG 映射引擎共同定义。

### 8.1 配置参数（来自 `[Architecture level]`）

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
| `Tile_Num` | `64,64` → `[64,64]` | 芯片上 Tile 阵列规模（行,列）；0,0=默认 8×8 |

### 8.2 算法配置（来自 `[Algorithm Configuration]`）

| 参数名（ini key） | 默认值 | 含义 |
|---|---|---|
| `Weight_Polarity` | 1 | 权重极性处理方式 |
| `Simulation_Level` | 0 | 0=行为级；1=估计级（影响 Crossbar 功耗计算精度） |
| `NoC_enable` | 0 | 0=不调用 BookSim；1=调用 BookSim 进行 NoC 仿真 |

### 8.3 TCG 映射流程

**步骤：**
1. 对每个神经网络层计算所需 PE 数（`PEnum`）
2. 计算所需 Tile 数：`tilenum = ceil(PEnum / tile_PE_total_num)`
3. 用 `startid` 累加分配每层的 Tile 区间 `[startid, startid + tilenum)`
4. `mapping_matrix_gen()` 按拓扑策略生成 Tile 坐标到层 ID 的映射矩阵
5. `mapping_net()` 生成 `mapping_result[i][j] = layer_id`

**四种铺排拓扑：**

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

### 8.4 传输距离计算（`calculate_transfer_distance`）

计算 **层内**（同一层 Tile 之间）和 **层间**（相邻层 Tile 之间）的曼哈顿距离：

$$d_{inLayer}[l] = \text{Manhattan}(\text{last Tile of layer l}, \text{first Tile of layer l})$$
$$d_{transLayer}[l] = \text{Manhattan}(\text{last Tile of layer l}, \text{first Tile of layer l+1})$$

这些距离用于 `Model_latency` 中的片间传输时间计算：

$$t_{transfer} = d_{transLayer}[l] \times \frac{N_{output\_channel} \times N_{output\_bits}}{BW_{inter\_tile}}$$

---

## 9. SimConfig.ini 完整参数说明

以下汇总 `SimConfig.ini` 中所有 key，配合代码中的实际使用位置说明。

### `[Device level]`

```ini
Device_Tech = 130         # nm，工艺节点
Device_Type = NVM         # NVM | SRAM
Device_Area = 1.44        # μm²，单元面积（参考文献 RRAM）
Read_Level = 2            # 读电压档位数
Read_Voltage = 0,0.15     # V，各档读电压（逗号分隔，长度=Read_Level）
Write_Level = 2           # 写电压档位数
Write_Voltage = 0,3       # V，各档写电压
Read_Latency = 3.16       # ns，单次读延迟（NTHU ISSCC19）
Write_Latency = 10        # ns，单次写延迟
Device_Level = 2          # 阻态数（SRAM固定=2）
Device_Resistance = 1e6, 1e4  # Ω，HRS→LRS各档阻值
Device_Variation = 1      # %，NVM变异幅度 ΔR/R
Device_SAF = 0.1,0.1      # %，Stuck-At-HRS/LRS故障率
Read_Energy = 1.12e-15    # J/bit，SRAM读能量
Write_Energy = 1.6e-15    # J/bit，SRAM写能量
```

### `[Crossbar level]`

```ini
Xbar_Size = 256,256       # (行,列) 阵列尺寸
Subarray_Size = 256       # 子阵列行数（列数与Xbar相同）
Cell_Type = 1T1R          # 1T1R | 0T1R，仅NVM有效
Transistor_Tech = 130     # nm，外围晶体管工艺
Wire_Resistance = -1      # Ω | -1=默认2.82Ω
Wire_Capacity = -1        # fF | -1=默认1fF
Load_Resistance = -1      # Ω | -1=自动计算√(R_HRS×R_LRS)
Area_Calculation = 0      # 0=用Device_Area；1=用工艺几何公式
```

### `[Interface level]`

```ini
DAC_Choice = 1            # -1=用户自定义；1~7=内置ISAAC设计
DAC_Area = 0              # μm² | 0=使用Choice对应默认值
DAC_Precision = 0         # bit | 0=默认
DAC_Power = 0             # W | 0=默认
DAC_Sample_Rate = 0       # GSamples/s | 0=默认
ADC_Choice = 6            # -1=用户自定义；1~9=内置设计（8=SA）
ADC_Area = 0              # μm² | 0=默认
ADC_Precision = 0         # bit | 0=默认
ADC_Power = 0             # W | 0=默认
ADC_Sample_Rate = 0       # Samples/s | 0=默认
ADC_Interval_Thres = -1   # -1=自动生成量化区间；否则为电压阈值列表(V)
Logic_Op = -1             # -1=无附加逻辑；0=AND；1=OR；2=XOR（数字PIM）
```

### `[Process element level]`

```ini
PIM_Type = 0              # 0=模拟PIM；1=数字PIM（1-bit ADC/DAC）
Xbar_Polarity = 2         # 1=单阵列正负共存；2=正/负分离双阵列
Sub_Position = 0          # Polarity=2时：0=模拟域相减；1=数字域相减
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
Adder_Area = 0            # μm²，0=查表（×bitwidth）
Adder_Power = 0           # W，0=查表（×bitwidth）
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
JointModule_Area = 0      # μm²，0=查表（按位宽×工艺缩放）
JointModule_Power = 0     # W，0=查表
```

### `[Tile level]`

```ini
PE_Num = 2,2              # (行,列)，每Tile中PE数组；0,0=默认4×4
Pooling_shape = 3,3       # (行,列) 池化核大小
Pooling_unit_num = 64     # Tile内并行池化单元数
Pooling_Tech = 65         # nm
Pooling_area = 0          # μm²，0=自动
Tile_Adder_Num = 0        # 0=自动计算；x=手动指定
Tile_Adder_Level = 0      # 加法树最大层数；0=自动
Tile_ShiftReg_Num = 0     # 0=自动
Tile_ShiftReg_Level = 0
Inter_Tile_Bandwidth = 20     # Gbps，Tile间通信带宽
Intra_Tile_Bandwidth = 1024   # Gbps，Tile内PE间通信带宽
Tile_outBuf_Size = 0      # KB（与PE level里同名键重叠，以Tile level读取为准）
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
Buffer_Bitwidth = 64      # bit，全局缓冲总线位宽
LUT_Capacity = 1          # Mb
LUT_Area = 0              # mm²
LUT_Power = 0             # mW
LUT_Bandwidth = 0         # Mb/s
Tile_Connection = 2       # 0=正常；1=蛇形；2=回字形；3=zigzag
Tile_Num = 64,64          # 芯片上Tile网格；0,0=默认8×8
```

### `[Algorithm Configuration]`

```ini
Weight_Polarity = 1       # 权重极性处理方式（1或2）
Simulation_Level = 0      # 0=行为级（快）；1=估计级（需具体权重，慢但准）
NoC_enable = 0            # 0=不调用BookSim；1=调用BookSim做NoC仿真
```

---

## 10. 已知代码缺陷与注意事项

在阅读与使用源码时，以下几处存在潜在 bug 或设计不一致，需要特别注意：

| 位置 | 问题描述 | 影响 |
|---|---|---|
| `Device.py`：`calculate_device_write_power` | 使用 `self.type`，但属性名为 `self.device_type` | NVM 写功耗调用时会 `AttributeError` |
| `Device.py`：NVM 分支 | 变异属性名为 `decice_variation`（拼写错误），SRAM 分支为 `device_variation` | 跨分支引用时会出错 |
| `PE.py`：`calculate_DAC_num` | 使用裸变量 `subarray_num`，应为 `self.subarray_num` | 可能 `NameError` |
| `PE.py`：`calculate_PE_read_power` 第627行 | 使用 `PE_iReg.shiftreg_power`，`reg` 类无此属性 | 应为 `PE_shiftreg.shiftreg_power` |
| `DAC.py`：Choice 6 | 功耗值为 `0.4992`，其他选项均有 `×1e-3`，疑似缺少 `e-3` 量纲 | 8-bit DAC 功耗高估约 1000 倍 |
| `Crossbar.py`：SRAM 分支输出 | `xbar_output()` 打印 `xbar_load_resistance`，但 SRAM 分支 `__init__` 未定义该属性 | 仅 output 函数出错，不影响计算 |
| `Tile.py`：第395–475行 | `calculate_tile_write_power` 等方法被包裹在三引号字符串中，**不可执行** | 写功耗/能量无法通过 Tile 直接计算 |

---

*文档生成时间：2026-04-07*  
*基于 MNSIM-2.0 源码（commit 对应 main.py git status: modified）逐行分析*
