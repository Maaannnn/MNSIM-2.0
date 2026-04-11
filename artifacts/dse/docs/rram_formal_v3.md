# RRAM 正式论文实验空间（`rram_formal_v3`）

## 1. 适用场景

当前 `A/B/C/D` 矩阵已经回答了三件事：

- 器件迁移：`P3` 在无补偿时会失效
- 接口补偿：`P1/P2` 可通过 `ADC/DAC/sub_position` 获得明显 `PPA` 收益
- 系统瓶颈：`512x512 + 2x2 + tile_connection=2 + inter_tile_bw=80` 更稳

因此，下一步不应继续扩矩阵，而应切换到一个**正式论文版收束空间**，让 `random / nsga2 / mobo` 在同一空间里做对比。

---

## 2. 研究问题

这套正式实验聚焦三个问题：

1. 在已经固定系统层主结构后，**器件退化与接口参数**如何共同决定 `PPA + ACC`
2. `ADC=6 + DAC=128` 这一条 `PPA` 主线，与 `ADC=4 + DAC=32` 这一条基线主线，谁更适合作为论文默认配置
3. 在 `P1/P2/P3` 三类器件场景下，搜索算法能否快速找到稳定的 Pareto 候选

---

## 3. 设计变量

正式空间只保留 4 个变量：

- `rram_preset`：`P1, P2, P3`
- `adc_choice`：`4, 6, 7`
- `dac_num`：`32, 128`
- `sub_position`：`0, 1`

总空间大小：

- `3 × 3 × 2 × 2 = 36` 点

这意味着：

- 空间已经足够小，适合做**正式算法对比**
- 也足够可控，便于最后做**穷举校验 / Pareto 复核**

---

## 4. 固定参数

下面这些参数不再搜索，直接固定为矩阵实验已经支持的主结构：

- `xbar_size = 512x512`
- `xbar_polarity = 2`
- `group_num = 1`
- `pe_num = 2x2`
- `tile_connection = 2`
- `inter_tile_bw = 80`

这样做的原因是：

- `C` 已经说明 `4x4` 不值得继续保留
- `tile_connection=2` 比 `3` 更稳
- `inter_tile_bw=80` 的时延更优

---

## 5. 输出指标

正式论文实验继续使用这 4 个输出：

- `latency_ns`
- `energy_nj`
- `area_um2`
- `accuracy`

对应论文中就是：

- `PPA = latency + energy + area`
- `ACC = accuracy`

---

## 6. 推荐实验顺序

### 实验 A：方法对比

同一空间跑：

- `random`
- `nsga2`
- `mobo`

比较：

- `HV`
- Pareto size
- best latency / energy / area / accuracy
- wall time

### 实验 B：论文主结论

从正式空间里给出两条主线：

- `PPA 主线`：通常会偏向 `ADC=6 + DAC=128`
- `基线/面积主线`：通常会偏向 `ADC=4 + DAC=32`

### 实验 C：边界说明

重点解释：

- `P3` 是否还能进入可行域
- `P4` 为什么不纳入正式搜索空间

---

## 7. 如何执行

推荐直接使用：

- `artifacts/dse/scripts/run_formal_v3_search.sh`

它会默认：

- 使用 `vgg8`
- 使用 `cifar10_vgg8_params.pth`
- 使用 `SimConfig.ini`
- 打开 `run_accuracy`
- 打开 `SAF` 与 `Variation`
- 使用 `rram_formal_v3`

如果你要手工运行，见脚本内命令。

