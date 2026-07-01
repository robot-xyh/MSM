# D5 终端视觉配准与身份认证计划

## 1. 范围与安全边界

D5 只面向科研仿真、离线回放和保守的终端视觉配准评估。模块不实现真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程，也不绕过人工或中心授权。

局部终端节点必须遵守一个硬约束：不得改写、重建或重新分配 `global_track_id`。D5 只能基于中心分配的 `assigned_global_track_id`，报告本地视觉轨迹是否与该全局航迹匹配。

## 2. 核心工程问题与科学问题

工程问题：末端相机视场内可能同时出现分配目标、非分配目标、友方资源和未知飞行物。相机最近目标不一定是中心分配目标，本地 MOT 的 `local_track_id` 也不能替代全局身份。D5 需要在这些干扰下输出可解释、可审计的 `locked/ambiguous/hold/reacquire` 决策。

科学问题：如何融合中心航迹预测、像素协方差传播、几何门控、局部 MOT 稳定性、合作身份声明和二级侦察 cue，在不引入虚假确定性的前提下降低终端 ID switch 和错误绑定。

## 3. 输入输出

输入：

- `Assignment`：来自 D3/D4，包含 `assigned_global_track_id`、版本、授权状态和资源 ID。
- `GlobalTrack[]`：来自 D2，包含位置、速度、协方差、类别、时间戳和 `global_track_id`。
- `LocalVisualTrack[]`：来自本地检测/MOT，包含像素中心、bbox、角速率、质量和本地轨迹历史。
- `IdentityClaim[]`：来自仿真的 Remote ID、MAVLink 签名、DDS Security 或 AprilTag 等合作身份声明。
- `CameraModel`：相机内参、外参、图像尺寸和测量协方差。
- `ReconImageCue[]`：来自 D4 二级高空系留侦察节点的局部图像 cue。

输出：

- `TerminalAssociation`：包含中心分配 ID、本地候选 ID、置信度、歧义度、友方冲突状态、决策状态、候选代价和 cue 使用标记。

## 4. 简化数学模型

### 4.1 时间预测

用常速度模型把中心航迹预测到图像帧时间：

```text
dt = t_image - t_track
p(t_image) = p(t_track) + v * dt
Sigma_p(t_image) = Sigma_p(t_track) + Q(dt)
```

该预测只用于终端投影对齐，不替代 D2 的航迹滤波器。

### 4.2 相机投影

使用针孔模型：

```text
P_c = R * P_w + t
u = fx * X_c / Z_c + cx
v = fy * Y_c / Z_c + cy
```

`Z_c <= 0` 或投影落出图像范围时，当前帧不可配准，输出 `reacquire`。

### 4.3 像素协方差传播

将世界坐标协方差传播到像素平面：

```text
J = d(project(P_w)) / d(P_w)
Sigma_px = J * Sigma_w * J^T + Sigma_measurement
```

用二维马氏距离进行几何门控：

```text
d2 = (z - p)^T * Sigma_px^-1 * (z - p)
```

默认门限采用 `gate_chi2 = 9.21`。

### 4.4 综合代价

候选代价：

```text
C = C_geo + C_rate + C_category + C_quality + C_friend + C_recon
```

其中 `C_recon` 只作为二级侦察 cue 的辅助负代价，不能越过授权、版本和友方冲突规则。

## 5. 算法选型理由

默认采用“中心航迹投影 + 像素马氏门控 + 本地 MOT 候选排序”的路线，原因是：

- 可解释：每个候选都有投影误差、角速率、类别、质量和身份冲突分项。
- 保守：没有候选过门限时不会强行匹配。
- 可集成：D2/D3/D4 已提供全局航迹、分配版本和降级计划。
- 可评估：D6 可以直接统计错误 `locked`、歧义事件、友方 `hold` 和 cue 使用次数。

ByteTrack、BoT-SORT、Deep SORT 只作为本地 MOT 输入来源。它们输出的 `local_track_id` 不能替代 `global_track_id`。

## 6. 二级侦察节点 cue 计划

本阶段假设存在若干高空系留侦察无人机作为二级区域节点。中心节点正常时，二级节点向覆盖小区内的拦截资源发送图像 cue；中心节点失效时，D4 可降级到二级节点协调；二级节点也失效时才进入完全无中心协商。

D5 将该输入表示为 `ReconImageCue`：

- `producer_node_id`：cue 来源二级节点。
- `image_frame_id`：cue 所属图像帧。
- `global_track_id`：可选的全局航迹提示。
- `center_px` 与 `bbox`：图像平面提示。
- `confidence`：cue 置信度。
- `scoped_resource_ids`：允许使用该 cue 的资源集合。

关键约束：

- 若 cue 来自二级侦察节点自己的相机，必须先重投影到当前拦截资源相机平面。
- 未重投影的二级相机像素不能直接与 `LocalVisualTrack.center_px` 比较。
- cue 只能降低候选代价，不能绕过授权、版本校验、友方确认和 MOT 质量门槛。
- 空 `scoped_resource_ids` 当前可视为广播 cue；若实验要求严格小范围分发，应改为显式广播标记或视为空无效。
- 后续应加入 cue 新鲜度、目标相机帧校验和 `recon_cue_used_count` 指标。

## 7. 实施流程

1. 读取 D3/D4 分配，确认授权状态和版本。
2. 从 D2 航迹表中查找中心分配的 `global_track_id`。
3. 按图像帧时间预测该航迹。
4. 调用 `project_tracks_to_image()` 得到像素预测和协方差。
5. 将本地检测/MOT 输出标准化为 `LocalVisualTrack[]`。
6. 将合作身份消息标准化为 `IdentityClaim[]`。
7. 将已重投影的二级节点图像提示标准化为 `ReconImageCue[]`。
8. 调用 `build_cost_matrix()` 构造候选代价。
9. 调用 `decide()` 输出 `TerminalAssociation`。
10. 记录候选代价、身份冲突、决策状态和 cue 使用情况，交给 D6 离线评估。

## 8. 代码模块划分

```text
research_modules/d5_terminal_association/
├── PLAN.md
├── README.md
├── docs/
│   ├── ALGORITHM_AND_IMPLEMENTATION.md
│   ├── EXPERIMENT_REPORT.md
│   ├── AIRSIM_INTEGRATION_PLAN.md
│   └── terminal_decision_timeline.png
├── simulations/
│   └── run_terminal_association_sim.py
├── src/d5_terminal_association/
│   ├── associator.py
│   ├── geometry.py
│   ├── identity.py
│   └── models.py
└── tests/
    └── test_terminal_association.py
```

主要职责：

- `models.py`：定义 `GlobalTrack`、`LocalVisualTrack`、`Assignment`、`IdentityClaim`、`ReconImageCue` 和 `TerminalAssociation`。
- `geometry.py`：实现投影、协方差传播和马氏距离。
- `identity.py`：解析仿真身份声明并判断友方冲突。
- `associator.py`：实现投影、代价矩阵和保守决策。
- `simulations/`：生成离线合成场景和实验结果。
- `docs/`：保存算法说明、实验报告、图表和 AirSim 离线计划。

## 9. 关键接口

推荐全部使用关键字参数调用，尤其是 `current_time` 和 `recon_image_cues`：

```python
decision = associator.decide(
    assignment=assignment,
    global_tracks=global_tracks,
    local_tracks=local_tracks,
    identity_claims=identity_claims,
    camera=camera,
    current_time=current_time,
    recon_image_cues=reprojected_recon_cues,
)
```

核心接口：

- `TerminalAssociator.project_tracks_to_image(global_tracks, camera, timestamp=None)`
- `TerminalAssociator.build_cost_matrix(projections, local_tracks, identity_claims=(), recon_image_cues=(), resource_id=None)`
- `TerminalAssociator.decide(assignment, global_tracks, local_tracks, identity_claims=(), camera=None, current_time=None, recon_image_cues=())`
- `IdentityChecker.parse_claims(raw_messages, current_time)`

## 10. 仿真场景设计

初始仿真使用简单图像平面和质点投影，不涉及真实飞控或硬件：

- 一个中心分配目标。
- 一个非分配干扰目标。
- 一个带合作身份声明的友方目标。
- 一个未知目标靠近分配目标投影，制造歧义。
- 分配目标短时遮挡，触发 `reacquire`。
- 友方目标与投影重叠，触发 `hold`。

后续补充：

- 已重投影的二级侦察 cue。
- stale cue。
- 跨资源 cue。
- 空 `scoped_resource_ids` 语义对照。

## 11. 指标

D5 至少记录：

- `terminal_association_accuracy`
- `locked_precision`
- `wrong_locked_count`
- `ambiguous_count`
- `hold_count`
- `friend_overlap_hold_count`
- `reacquire_count`
- `time_to_terminal_lock`
- `terminal_id_switch_count`
- `global_track_id_rewrite_count`
- `recon_cue_used_count`

其中 `global_track_id_rewrite_count` 应始终为 0。

## 12. 预期交付物

- 根目录 `PLAN.md` 和 `README.md`。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法原理与实施方案。
- `docs/EXPERIMENT_REPORT.md`：中文实验报告和图表引用。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放与接口计划。
- Python 源码、单元测试和离线仿真脚本。

## 13. 局限与后续工作

- 目前 `ReconImageCue` 的新鲜度和相机帧一致性主要由调用方保证。
- 当前仿真尚未批量生成二级 cue 场景。
- 当前身份声明为离线仿真抽象，不连接真实通信或安全中间件。
- 本地 MOT 质量对小目标场景影响大，需要 AirSim 离线回放进一步评估。
- D5 输出只用于评估和上游复盘，不应被解释为自动处置命令。
