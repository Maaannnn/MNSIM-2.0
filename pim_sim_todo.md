# pim_sim — Enhancement Layer TODO & Progress

> **Purpose**: Drop-in accuracy/PPA enhancement layer for MNSIM.
> Fills three specific gaps in MNSIM's default models without forking the simulator.
>
> **Integration point**: `dse/core.py:evaluate_config` — pass `pim_sim_model=<DeviceModel>` to activate.

---

## Status Overview

| Module | Status | Notes |
|---|---|---|
| `pim_sim/device/model.py` | ✅ Done | SymmetricGaussianModel, AsymmetricGaussianModel, EmpiricalDeviceModel |
| `pim_sim/device/calibrate.py` | ✅ Done | calibrate_from_wafer_csv（含 IQR 鲁棒过滤），calibrate_from_measured_presets_csv |
| `pim_sim/device/calibrated_presets.py` | ✅ Done | 硬编码15个wafer校准结果 + 4个命名场景 |
| `pim_sim/array/ir_drop.py` | ✅ Done | IRDropModel — 一阶行位置 IR-drop 修正 |
| `pim_sim/array/adc_model.py` | ✅ Done | WaldenADCModel — 连续 ENOB Walden FOM 参数化 ADC（FOM已重新拟合） |
| `pim_sim/accuracy/weight_inject.py` | ✅ Done | pim_sim_weight_inject — drop-in for weight_update() |
| `pim_sim/ppa/estimator.py` | ✅ Done | adc_ppa_delta, parametric_adc_sweep（单位 bug 已修） |
| `dse/core.py` modification | ✅ Done | evaluate_config 新增 pim_sim_model + ir_drop_model 参数 |
| `validate/calibrate_from_testdata.py` | ✅ Done | 校准验证，IQR 过滤，图输出 |
| `validate/compare_accuracy_models.py` | ✅ Done | MNSIM vs pim_sim 精度对比，单次 init 复用 |
| `validate/sweep_xbar_sensitivity.py` | ✅ Done | IR-drop 对阵列尺寸的敏感度分析 |
| `validate/compare_adc_models.py` | ✅ Done | MNSIM 9点查表 vs Walden FOM 参数化对比 |

### 已修 Bug 清单

| # | 文件 | 问题 | 修正 |
|---|---|---|---|
| 1 | `adc_model.py` | 默认 FOM 常数错 3 个数量级（1e-12→20e-15），6-bit 功率算出 64 mW | 从 MNSIM choice-4 反推重新拟合 |
| 2 | `compare_adc_models.py` | 能量列 `ns×W×1e12` 差 1e6 倍 | 改为 `×1e6` |
| 3 | `ppa/estimator.py` | `mnsim_energy`/`pim_energy` 均多乘 `1e9`，两分支不一致 | 去掉，加注释说明 ns×W=nJ |
| 4 | `calibrate.py` | SAF 故障点拉偏 std，xy7 的 LRS CV 算出 353% | 加 IQR 鲁棒过滤（factor=10） |
| 5 | `compare_accuracy_models.py` | 每 trial 重新 init，36 runs≈90 min；输出行缓冲看不到进度 | 只 init 一次；加 `-u` 标志 |
| 6 | `compare_accuracy_models.py` | 模型名 `asym_10` 的数字是几何均值参数，不是 CV%，误导 | 改为 `asym_hrs32_lrs3` 格式 |
| 7 | `ppa/estimator.py` | key 名 `per_conversion` 歧义（实为所有 ADC 总能量） | 改为 `per_cycle` |

---

## Gap 1: 非对称器件变异

### 问题
MNSIM `Weight_update.py` line 41：
```python
temp_resistance = np.random.normal(loc=0, scale=device_resistance[j] * variation / 100)
```
同一 `variation%` 施加到所有电阻状态（HRS、LRS 及 MLC 中间态）。

### 实测校准结果（15 wafers，IQR 鲁棒，2026-04-18）

| 状态 | CV 范围 | 均值 | 物理原因 |
|---|---|---|---|
| HRS | 27.7–39.3% | **31.5%** | 导电细丝溶解，随机过程 |
| LRS | 1.4–8.2% | **3.1%** | 细丝形成，过程受控 |
| 比值 | — | **10×** | 远高于文献 1.8–2.5× |

- wafer_xy7 / xy24 含 SAF 故障点（stuck-at-HRS），IQR 过滤后恢复正常
- `meas_cycle_typical` preset **不可用**（HRS_CV=74%，LRS_CV=423%，属异常簇）
- 推荐使用 `calibrated_presets.py` 中的 `typical_robust`（HRS=31.5%，LRS=3.1%）

### 精度实验结果（VGG8/CIFAR-10，max_batches=1，2-trial，2026-04-18）

| 模型 | 等效噪声 | 均值精度 | 相对 baseline 损失 |
|---|---|---|---|
| baseline（无噪声） | — | **0.9492** | — |
| MNSIM symmetric | Device_Variation=1%（SimConfig） | 0.9414 | -0.78% |
| pim_sim sym 10% | HRS=LRS=10% | 0.9375 | -1.17% |
| **pim_sim asym（真实校准）** | **HRS=31.6%，LRS=3.2%** | **0.9258** | **-2.34%** |
| pim_sim asym 超限 | HRS=63.2%，LRS=6.3% | 0.1036 | -84.6%（崩溃） |

**结论**：在真实器件参数下，pim_sim 预测的精度损失是 MNSIM 的 **3×**。MNSIM 因对称假设 + SimConfig 默认 1% 参数，系统性低估精度损失。

### 实现
`AsymmetricGaussianModel(state_cv_pct=[hrs_cv, lrs_cv])` + IQR 鲁棒校准

---

## Gap 2: IR-Drop 对精度的影响

### 问题
MNSIM `evaluate_config` 精度路径完全没有 IR-drop。
`Crossbar_accuracy.py`（DSE 中未被调用）有残缺模型，但用均匀分布（与 `weight_update` 不一致），且只做线性行偏移而非基于物理的修正。

### 物理模型
N 行阵列中第 i 行有效电压：
```
V_eff(i) ≈ V_in × (1 - α × i/N)
α = N × R_wire_segment / R_device_avg
```

| 阵列尺寸 | α（R_wire=0.5Ω，R_dev=5kΩ） | 底行压降 | 均值精度损失上界 |
|---|---|---|---|
| 64×64 | 0.0064 | 0.63% | 0.32% |
| 128×128 | 0.0128 | 1.27% | 0.64% |
| 256×256 | 0.0256 | 2.55% | 1.28% |
| 512×512 | 0.0512 | 5.11% | 2.56% |

IR-drop 效应随阵列规模**二次增长**，MNSIM 对大阵列的精度高估更严重。

### 实现
`IRDropModel.apply_to_weight_matrix()` 对每行导纳施加位置相关的缩放因子

### 验证（已运行）
```
validate/output/ir_drop_sensitivity.csv
validate/output/ir_drop_profiles.png
validate/output/ir_drop_heatmap.png
```

---

## Gap 3: 参数化 ADC 模型

### 问题
MNSIM 有 9 个硬编码 ADC preset，ADC bits 是离散变量，无法插值，无法做连续灵敏度分析。

### 实现
`WaldenADCModel(enob=6.0)` — 连续 ENOB，从 MNSIM choice-4 拟合 FOM 常数：
- `FOM_W = 20 fJ/conv`（拟合 choice-4：6b，1.26mW，1GSa/s）
- `FOM_A = 8 µm²` per 2^ENOB/GSa/s

6-bit 对比：Walden=1.28 mW vs MNSIM=1.26 mW，误差 1.6%。

### 验证（已运行）
```
validate/output/adc_comparison.csv
validate/output/adc_ppa_curves.png
```

---

## 待完成工作

### HIGH PRIORITY

- [ ] **在真实 DSE 中替换噪声模型**：修改 `dse/run_matrix.py` 接受 `--pim-sim-preset strong/weak` 参数，用 `calibrated_presets.py` 替换 MNSIM 对称噪声，重跑 ws2 矩阵实验，对比 Pareto 前沿形状变化

- [ ] **精度饱和问题**：当前 VGG8/CIFAR-10 在 strong/weak preset 下精度相同（0.9424）→ 网络对噪声过于鲁棒。选项：
  - 用 4-bit 量化网络（对器件噪声更敏感）
  - 缩小 xbar 到 32×32（IR-drop 效应更显著）
  - 换更难任务（ImageNet top-5）

- [ ] **meas_cycle_typical 诊断**：确认异常原因（双峰分布 vs 测量 artifact），决定是否完全排除或用 typical_robust 替代

### MEDIUM PRIORITY

- [ ] **ADC bits 加入 DSE 搜索空间**：在 `dse/core.py:SPACE` 中加 `adc_bits` 连续轴，用 `WaldenADCModel` 计算 PPA，解锁 ADC bits 作为优化变量

- [ ] **IR-drop 精度实验**：跑 128×128 vs 256×256 vs 512×512 的精度对比，量化 MNSIM 高估幅度随阵列规模的变化曲线（论文图的核心数据）

- [ ] **更多 trials 减小方差**：当前 2 trials，max_batches=1（500 样本），方差约 ±1%。建议 5 trials + max_batches=3 出最终论文数据

- [ ] **EmpiricalDeviceModel 序列化**：加 `save_to_npz/load_from_npz`，避免每次重新读 CSV

### LOW PRIORITY

- [ ] **单元测试** `tests/test_device_models.py`：对称模型精确复刻 MNSIM；AsymmetricGaussian σ/mean = CV%；IR-drop 顶行=1.0，底行=1-α(N-1)/N；Walden 功率 ∝ 2^ENOB

- [ ] **NeuroSim 对比列**：论文中加 NeuroSim 同等设计的 PPA 参考列

---

## Paper Claim 检查清单

| Claim | 证据 | 状态 |
|---|---|---|
| MNSIM 对称模型低估 HRS 噪声、高估 LRS 噪声 | wafer 校准：HRS=31.5% vs LRS=3.1%，比值 10× | ✅ 有数据 |
| 非对称模型预测精度损失是 MNSIM 的 3× | accuracy 实验：0.9258 vs 0.9414 | ✅ 有数据 |
| IR-drop 效应随阵列规模二次增长 | sweep_xbar_sensitivity：64→512 行，α 从 0.006 到 0.051 | ✅ 有数据 |
| Walden FOM 使 ADC bits 成为连续优化变量 | compare_adc_models：6-bit 误差 1.6% | ✅ 有数据 |
| pim_sim 改变 DSE Pareto 前沿形状 | 需跑 DSE 实验 | ⬜ 待做 |
| 大阵列（>256×256）精度被 MNSIM 系统高估 | 需跑 IR-drop 精度实验 | ⬜ 待做 |

---

*Last updated: 2026-04-18*
