# D5 末端视觉配准与身份认证实验报告

## 1. 实验边界

本报告验证保守的末端视觉关联模块。模块只在离线科研仿真中评估“中心分配目标”和“本地视觉轨迹”的对应关系，不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。局部节点严禁自行改写 `global_track_id`。

## 2. 实验目的

D5 解决的问题是：拦截资源末端视场内可能同时出现分配目标、其他目标、友方资源和未知飞行物，相机看到的最近目标不一定是中心分配目标。本轮重点验证：

- 全局航迹能否按当前图像帧时间做常速度预测后投影。
- 局部 MOT 结果能否通过像素马氏门限、角速度一致性和类别线索关联。
- 高空系留二级侦察节点发布的局部图像 cue 能否作为小范围资源的辅助证据。
- 友方正向认证能否触发 `hold`，避免把友方重叠误当作目标。
- 未授权计划、版本不匹配、短历史或低质量 MOT 是否会阻止 `locked`。

## 3. 几何模型

相机采用针孔模型：

```text
p = K [R | t] P_w
u = fx X_c / Z_c + cx
v = fy Y_c / Z_c + cy
```

位置协方差通过投影雅可比传播到像素平面：

```text
Sigma_px = J Sigma_w J^T + Sigma_measurement
```

本地检测与预测投影之间使用二维像素马氏距离门限，默认 `d2 <= 9.21`。

## 4. 决策状态

| 状态 | 含义 |
|---|---|
| `locked` | 唯一匹配、版本一致、已授权、MOT 质量足够、无友方冲突 |
| `ambiguous` | 候选接近、质量不足、身份未验证或代价过高 |
| `hold` | 未授权、版本不匹配、验证友方重叠 |
| `reacquire` | 分配航迹不可见或无本地轨迹通过门限 |

未知身份不等于敌方身份；`ambiguous` 和 `hold` 不得被下游解释为自动授权。

## 5. 二级侦察节点图像 cue

本阶段假设存在若干高空系留侦察无人机作为二级节点。中心节点正常时，二级节点持续向其覆盖小区内的若干拦截资源发送侦察图像或图像平面 cue。中心节点失效时，D4 可把局部协调权降级到二级节点；二级节点失效后才进入完全无中心协商。

D5 对二级节点图像 cue 的使用原则：

- cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心、置信度和 `scoped_resource_ids`。
- cue 的像素中心必须已经重投影到当前拦截资源的相机平面；二级侦察相机原始像素不能直接与本地 `LocalVisualTrack.center_px` 比较。
- cue 只对覆盖范围内的资源生效，不在范围内的资源不能使用该 cue 降低代价。
- cue 只能降低候选视觉轨迹的关联代价，不能绕过 `authorization_state`、`assignment_version`、友方验证或 MOT 质量门槛。
- 即便 cue 与本地检测一致，终端模块仍必须输出 `locked/ambiguous/hold/reacquire` 之一，且不得改写 `global_track_id`。
- 建议后续实验记录 `recon_cue_used_count`，并加入 cue 新鲜度、`image_frame_id`/目标相机帧一致性和空 `scoped_resource_ids` 语义的对照测试。

更完整的算法原理、数学模型和接口说明见 `ALGORITHM_AND_IMPLEMENTATION.md`。

## 6. 仿真场景

运行命令：

```bash
python3 research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py --frames 120 --seed 7
```

覆盖内容：

- 一个中心分配目标 `G_ASSIGNED`。
- 一个非分配干扰目标。
- 一个带模拟 OpenDroneID 友方标签的合作目标。
- 一个未知目标在部分帧靠近分配目标投影，制造歧义。
- 分配目标短时遮挡，触发 `reacquire`。
- 友方目标与分配投影重叠，触发 `hold`。

## 7. 图表与曲线

### 7.1 末端决策时间线

![D5 末端决策时间线与累计曲线](terminal_decision_timeline.png)

上图第一部分展示每一帧的终端决策状态，第二部分展示 `locked/ambiguous/hold/reacquire` 的累计数量。该图用于分析保守策略是否在遮挡、友方重叠和歧义区域主动降级，而不是盲目锁定。

## 8. 基线结果

| 指标 | 数值 |
|---|---:|
| 正确 locked 次数 | 84 |
| 错误 locked 次数 | 0 |
| ambiguous 次数 | 8 |
| hold 次数 | 19 |
| reacquire 次数 | 9 |
| locked precision | 1.0 |
| 全帧正确 locked 比例 | 0.7 |
| `global_track_id` 改写次数 | 0 |

## 9. 结论

D5 的目标不是最大化锁定次数，而是避免错误绑定和友方冲突。当前实现默认要求 assignment 版本匹配，并在未授权、版本不一致、短 MOT 历史或低质量检测时输出 `hold/ambiguous`。二级侦察节点 cue 可以提升局部关联的可解释性，但不能成为授权或身份确认的替代品。这使 D5 可以作为 D3/D4 分配计划与 D6 终端评估之间的保守安全门。
