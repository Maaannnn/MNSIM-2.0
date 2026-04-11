# RRAM 设计指导空间（`rram_guidance_v4`）

## 为什么要有这版空间

你刚才的判断是对的：

- `rram_formal_v3` 更像“论文最终对比空间”
- 它适合做 `random / nsga2 / mobo` 的方法对比
- 但它固定掉了太多系统层参数，不足以回答“设计上到底该怎么选”

所以这里单独给一版：

- `rram_guidance_v4`

它的目标不是最小化搜索空间，而是保留足够多的**器件—接口—系统耦合**，让结果更像“设计指导”。

---

## 研究问题

这版空间主要回答：

1. 在 `P1/P2/P3` 三类器件退化下，`xbar_size` 应该怎么选
2. `ADC / DAC / sub_position` 的接口补偿收益，会不会随系统并行度而变化
3. `pe_num / tile_connection / inter_tile_bw` 这些系统层参数，到底是“稳定结论”还是“只在某个局部组合下成立”

---

## 设计变量

`rram_guidance_v4` 保留 8 个有效变量：

- `rram_preset`: `P1, P2, P3`
- `xbar_size`: `128x128, 256x256, 512x512`
- `adc_choice`: `4, 6, 7`
- `dac_num`: `32, 128`
- `sub_position`: `0, 1`
- `pe_num`: `2x2, 4x4`
- `tile_connection`: `2, 3`
- `inter_tile_bw`: `40, 80`

固定变量：

- `xbar_polarity = 2`
- `group_num = 1`

空间大小：

- `3 × 3 × 3 × 2 × 2 × 2 × 2 × 2 = 864`

这已经明显大于 `rram_formal_v3` 的 `36` 点，因此更适合做设计指导，但不适合穷举全扫。

---

## 推荐怎么用

### 用途 A：设计指导

用 `rram_guidance_v4` 跑：

- `random`
- `nsga2`
- `mobo`

目的：

- 看变量效应量
- 看 Pareto 前沿在更大空间下是否仍支持 `512x512 + 2x2 + bw80`
- 看 `ADC=6 + DAC=128` 是否在更大空间里仍然稳定

### 用途 B：论文最终结论

最后论文主图仍建议回到：

- `rram_formal_v3`

原因：

- 它更干净
- 更适合做方法对比
- 也更适合写“最终建议配置”

所以建议形成两层实验结构：

1. `rram_guidance_v4`：回答“为什么这么设计”
2. `rram_formal_v3`：回答“最终推荐哪几个点”

---

## 预算建议

因为 `864` 点明显更大，所以不建议一开始预算过大。

推荐：

- `random`: `budget 48~72`
- `nsga2`: `budget 48~72`
- `mobo`: `budget 36~60`

如果机器是当前这台 `M3 Pro + mps`：

- 建议 `workers=2` 或 `3`
- `max_acc_batches=4`

---

## 怎么执行

直接使用：

- `artifacts/dse/scripts/run_guidance_v4_search.sh`

默认会跑：

- `random nsga2 mobo`
- `seeds=42 43 44`
- `budget=48`

如果只是先试运行一轮，可以把预算改到 `24`。

