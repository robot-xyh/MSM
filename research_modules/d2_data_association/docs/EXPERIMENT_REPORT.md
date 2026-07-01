# D2 多目标跟踪与数据关联实验报告

## 1. 实验边界

本报告仅覆盖离线合成数据上的多目标跟踪、航迹生命周期和数据关联算法评估。模块不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

## 2. 实验目的

D2 的核心任务是维护稳定的 `global_track_id`。本轮实验比较 GNN/Hungarian、JPDA 和 MHT 接口在交叉、编队、遮挡、漏检和虚警条件下的表现，重点关注：

- `id_switch_count`：同一真值目标被不同全局航迹接续的次数。
- `coverage_continuity`：目标存在时是否被任意航迹覆盖。
- `identity_continuity`：目标存在时是否由同一身份连续覆盖。
- `duplicate_assignment_count`：同一帧重复分配或一对多异常。

## 3. 算法配置

详细算法原理、数学模型、参数调节和跨模块接口见 [ALGORITHM_AND_IMPLEMENTATION.md](ALGORITHM_AND_IMPLEMENTATION.md)。本报告只记录当前离线仿真结果和图表解读。

| 算法 | 作用 | 当前定位 |
|---|---|---|
| GNN/Hungarian | 马氏门限 + 一对一硬关联 | 默认工程基线 |
| JPDA | 多假设边缘概率关联 | 交叉/遮挡时的进阶候选 |
| MHT | 有界假设树接口 | 后续完整 MHT 的占位基线 |

## 4. 场景配置

| 场景 | 说明 |
|---|---|
| `crossing` | 两目标中心交叉 |
| `formation` | 五目标近距编队 |
| `occlusion` | 三目标短时遮挡 |
| `missed` | 四目标随机漏检 |
| `false_alarms` | 四目标叠加虚警杂波 |

运行命令：

```bash
python3 research_modules/d2_data_association/scripts/run_simulation.py --steps 36 --seed 7
```

## 5. 图表与曲线

### 5.1 ID Switch 与 RMSE 对比

![D2 数据关联 IDSW 与 RMSE 对比曲线](association_idsw_rmse.png)

上半部分为不同场景下的 ID Switch 柱状图，下半部分为 RMSE 曲线。该图用于判断是否需要从 GNN/Hungarian 升级到 JPDA/MHT：如果遮挡或虚警场景中 IDSW 明显升高，应优先检查门限、协方差和局部特征，再评估软关联算法。

## 6. 结果解读

- `crossing` 与 `formation` 场景主要验证门控和一对一约束是否稳定。
- `occlusion` 是主要失败模式，遮挡后重新出现的目标容易产生身份断裂。
- JPDA 在高歧义场景可能减少 ID Switch，但代价是运行时间更高。
- 当前 MHT 为有界研究接口，不应直接宣称优于 JPDA。

## 7. 结论

D2 的默认路线仍建议为 `GNN/Hungarian + EKF/UKF`。当候选门内观测数量升高、目标轨迹交叉或 `identity_continuity` 快速下降时，再启用 JPDA/MHT 对照。D2 输出的 `global_track_id` 是后续 D3 分配和 D5 终端锁定的核心键，不能由下游模块改写。
