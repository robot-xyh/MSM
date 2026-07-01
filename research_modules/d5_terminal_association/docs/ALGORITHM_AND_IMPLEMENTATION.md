# D5 终端视觉配准与身份认证算法原理与实施方案

## 1. 模块定位与边界

D5 位于 D3/D4 任务分配之后、D6 评估之前，负责回答一个窄问题：当前拦截资源相机视场中的哪个 `LocalVisualTrack` 可以被保守地认为对应中心分配的 `global_track_id`。D5 只输出 `TerminalAssociation` 和身份判断结果，不输出控制量、处置动作、毁伤判断或真实硬件接口，也不绕过中心授权和人工授权状态。

核心约束是：`global_track_id` 由中心态势和 D2 维护，D5 不创建、不重写、不换绑。即使本地相机看到更近、更清晰的目标，也不能把分配目标改成另一个全局航迹。

## 2. 问题定义

末端视场中常见的错误假设是“相机最近目标就是分配目标”。在多目标、多友方资源和未知飞行物共视场时，这个假设会导致错误配准：

- 分配目标、非分配目标、友方资源可能在图像中短时接近或交叉。
- 本地 MOT 的 `local_track_id` 只在当前相机内有意义，不能替代全局身份。
- 目标遮挡、漏检、逆光、小目标纹理不足会导致本地 ID switch。
- 二级侦察节点提供的图像 cue 若未经重投影，不能直接和拦截机相机像素比较。

D5 的目标不是最大化 `locked` 数量，而是把不确定情况显式降级为 `ambiguous`、`hold` 或 `reacquire`，为 D6 留下可统计的安全边界和失败样本。

## 3. 输入与输出

### 3.1 输入

| 输入 | 来源 | 关键字段 | 用途 |
|---|---|---|---|
| `Assignment` | D3 或 D4 | `assigned_global_track_id`, `assignment_version`, `authorization_state`, `resource_id` | 指定本机应核对的全局航迹 |
| `GlobalTrack[]` | D2 | 位置、速度、协方差、类别、版本、时间戳 | 预测并投影到图像平面 |
| `LocalVisualTrack[]` | 本地检测/MOT | `local_track_id`, `center_px`, `bbox`, `bearing_rate`, `quality`, `mot_history_length` | 本地候选观测 |
| `IdentityClaim[]` | 合作身份层 | Remote ID、MAVLink 签名、DDS Security、AprilTag 等模拟声明 | 友方/合作身份正向确认 |
| `CameraModel` | 离线回放/仿真 | 内参 `K`、外参 `R,t`、图像尺寸、像素噪声 | 几何投影与门控 |
| `ReconImageCue[]` | D4 二级侦察节点 | cue 图像帧、像素中心、置信度、作用资源范围 | 小范围辅助关联 |

### 3.2 输出

`TerminalAssociation` 包含：

- `assigned_global_track_id`：原样复制中心分配 ID。
- `local_track_id`：本地候选轨迹 ID，可能为空。
- `association_confidence` 与 `ambiguity_score`：关联置信度与歧义度。
- `friend_conflict_state`：友方重叠、未验证声明或无冲突。
- `decision_state`：`locked | ambiguous | hold | reacquire`。
- `candidate_costs`：候选代价排序，用于复盘。
- `recon_cue_used`：本次决策是否实际使用二级侦察 cue 降低代价。

## 4. 算法主流程

1. 校验 `Assignment.authorization_state`，未授权直接 `hold`。
2. 在 `GlobalTrack[]` 中查找 `assigned_global_track_id`，找不到则 `reacquire`。
3. 校验 `assignment_version` 与航迹版本，版本不一致则 `hold`。
4. 将分配航迹按当前图像时间做常速度预测。
5. 使用相机模型把预测位置和协方差投影到像素平面。
6. 对所有 `LocalVisualTrack` 计算像素马氏距离，超出门限的候选剔除。
7. 对门内候选计算综合代价：几何误差、角速率一致性、类别一致性、MOT 质量、友方冲突、二级侦察 cue。
8. 若门内候选与已验证友方重叠，输出 `hold`。
9. 若最佳候选代价低、与第二候选间隔足够、MOT 历史和质量满足阈值，则输出 `locked`；否则输出 `ambiguous`。
10. 全流程断言输入 `global_track_id` 未被改变。

## 5. 数学模型

### 5.1 常速度时间预测

D5 使用轻量预测把 D2 输出航迹对齐到当前图像帧时间：

```text
dt = t_image - t_track
p(t_image) = p(t_track) + v * dt
Sigma_p(t_image) = Sigma_p(t_track) + Q(dt)
```

当前实现采用保守的简化过程噪声膨胀，随 `dt` 增大协方差上升。它不是完整跟踪器，只用于末端投影前的时间对齐。

### 5.2 相机投影

相机使用针孔模型：

```text
P_c = R * P_w + t
u = fx * X_c / Z_c + cx
v = fy * Y_c / Z_c + cy
```

若 `Z_c <= 0` 或像素落在有效图像范围之外，则该全局航迹在当前帧不可投影，决策进入 `reacquire`。

### 5.3 像素协方差传播

全局位置协方差通过投影雅可比传播到像素平面：

```text
J_cam = R
J_proj =
[[fx / Z_c, 0, -fx * X_c / Z_c^2],
 [0, fy / Z_c, -fy * Y_c / Z_c^2]]
J = J_proj * R
Sigma_px = J * Sigma_w * J^T + Sigma_measurement
```

`Sigma_px` 表示“预测像素位置的不确定性”。距离远、航迹协方差大或视角接近奇异时，像素门限自然变宽；这比固定像素半径更适合多源融合输出。

### 5.4 几何门控

对每个本地轨迹中心 `z = [u_l, v_l]^T`，计算：

```text
d2 = (z - p)^T * Sigma_px^-1 * (z - p)
```

默认 `gate_chi2 = 9.21`，对应二维卡方约 99% 门限。超过门限的候选不参与后续排序。

### 5.5 综合代价

门内候选的代价为：

```text
C = C_geo + C_rate + C_category + C_quality + C_friend + C_recon
```

其中：

- `C_geo = d2`：像素马氏距离。
- `C_rate`：本地 `bearing_rate` 与预测像素速度差异。
- `C_category`：类别不一致惩罚；未知类别保持中性。
- `C_quality`：低质量、短历史 MOT 惩罚。
- `C_friend`：已验证友方重叠给极大惩罚，并触发 `hold`。
- `C_recon`：二级侦察 cue 命中时的负代价奖励，但不能越过授权、版本和友方规则。

## 6. 本地 MOT 的使用边界

ByteTrack、BoT-SORT、Deep SORT 都可以作为 `LocalVisualTrack` 的来源，但 D5 不依赖它们的本地 ID 作为全局身份。

| MOT 方法 | 适用场景 | 主要风险 | D5 使用方式 |
|---|---|---|---|
| ByteTrack | 检测质量较稳定、短遮挡、需要简单强基线 | 小目标低分检测可能漂移 | 输出 `local_track_id`、中心点、bbox 和质量 |
| BoT-SORT | 相机运动明显、需要运动补偿 | 依赖检测器和运动补偿质量 | 作为更稳的本地轨迹输入 |
| Deep SORT | 外观纹理明显、目标尺寸较大 | 小型无人机纹理弱，外观特征不稳定 | 作为对照基线，不替代全局 ID |

D5 只把 MOT 历史长度和质量作为置信度线索。若 `mot_history_length` 过短或 `quality` 过低，即便几何距离较近，也倾向输出 `ambiguous`。

## 7. 决策逻辑

| 决策 | 触发条件 | 下游语义 |
|---|---|---|
| `locked` | 已授权、版本一致、唯一候选通过门控、代价低、候选间隔足够、无友方冲突、MOT 质量足够 | 仅表示离线配准可信 |
| `ambiguous` | 多候选接近、最佳代价过高、MOT 历史短、质量低、身份声明未验证或疑似伪造 | 需要继续观测或请求上级/二级节点辅助 |
| `hold` | 未授权、版本不一致、已验证友方重叠 | 保守暂停该帧的正向配准 |
| `reacquire` | 分配航迹不可见、不可投影、无候选过门限 | 需要重新捕获或等待后续观测 |

`unknown` 是身份状态，不是对抗结论。未知对象不能被 D5 自动升级为任何处置含义。

## 8. 友方与合作身份正向确认

D5 支持的身份来源在仿真中可以映射为 `IdentityClaim`：

- Remote ID / OpenDroneID：广播身份和位置声明。
- MAVLink 签名：任务通信层的签名验证。
- DDS Security：中间件层身份与加密通信状态。
- AprilTag 或其他视觉标签：近距离合作目标的视觉正向标记。

这些机制只能正向确认“友方/合作身份”。其限制必须写入实验和评估：

- 未收到身份声明不等于非友方。
- 签名失败、过期或几何不一致不能证明对抗，只能降低可信度。
- 已验证友方与候选重叠时，D5 必须 `hold`。
- 合作身份不能覆盖 D3/D4 的分配版本，也不能替代 `global_track_id`。

## 9. 二级高空系留侦察节点 ReconImageCue

### 9.1 作用

在本阶段设定中，高空系留侦察无人机可作为 D4 的二级区域节点。中心正常时，它们把覆盖小区内的图像 cue 发送给附近拦截资源；中心失效后，D4 可降级到二级节点协调；二级节点也失效时才进入完全无中心协商。

D5 将二级节点输入建模为 `ReconImageCue`，用于辅助本地视觉候选排序。cue 不是授权、不是身份认证、不是全局分配。

### 9.2 坐标语义硬约束

`ReconImageCue.center_px` 必须与当前被评估的 `LocalVisualTrack.center_px` 处在同一图像坐标系，才能直接比较。也就是说：

- 如果 cue 来自二级侦察节点自己的相机画面，必须先经过跨相机几何变换或三维重投影，转换到当前拦截资源相机平面。
- `image_frame_id` 应表示 cue 所属图像帧；推荐在预处理后写成目标相机帧，例如 `interceptor_R1/front_camera`，并在 `metadata` 中保留原始二级节点帧。
- 未重投影的二级相机像素不能直接和拦截机本地像素相减，否则会产生错误代价。

### 9.3 推荐约束

当前代码支持 cue 降低代价，后续实验建议增加以下约束：

- 新鲜度：加入 `max_recon_cue_age_s`，超过阈值的 cue 不参与代价。
- 帧一致性：加入 `target_camera_frame_id` 或 `is_reprojected_to_local_camera=true` 标记。
- 资源范围：`scoped_resource_ids` 非空表示仅对指定资源生效；空值当前语义可视为广播 cue。若实验阶段要求严格小范围分发，建议把空 scope 视为无效或显式写为 `broadcast_allowed=true`。
- 置信度：`confidence` 只调节负代价大小，不改变门控和授权流程。
- 指标：D6 应记录 `recon_cue_used_count`、cue 命中后 `locked` 比例、cue 相关误配次数和 stale cue 被拒次数。

## 10. 关键接口

```python
associator = TerminalAssociator()

projections = associator.project_tracks_to_image(
    global_tracks=global_tracks,
    camera=camera,
    timestamp=current_time,
)

cost_result = associator.build_cost_matrix(
    projections=projections,
    local_tracks=local_tracks,
    identity_claims=identity_claims,
    recon_image_cues=reprojected_recon_cues,
    resource_id=assignment.resource_id,
)

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

推荐使用关键字参数传入 `current_time` 和 `recon_image_cues`，避免把 cue 误传为相机或时间位置参数。

## 11. 参数与调参建议

| 参数 | 默认含义 | 调参建议 |
|---|---|---|
| `gate_chi2` | 像素马氏门限 | 初期保持 9.21；漏关联多时先检查协方差，再考虑放宽 |
| `min_lock_margin` | 最优与次优代价差 | 目标密集时提高，减少错误 `locked` |
| `max_lock_cost` | `locked` 最大总代价 | 低质量图像下适当降低，迫使更多 `ambiguous` |
| `rate_sigma_px_s` | 像素角速率归一化尺度 | 相机抖动大时增大，避免过度惩罚 |
| `min_mot_history` | 最短 MOT 历史 | 遮挡频繁时可降低，但必须观察误锁率 |
| `min_lock_quality` | 本地轨迹质量门槛 | 检测器质量不稳定时提高更保守 |
| `recon_cue_bonus` | cue 命中奖励 | 不应大到压倒几何门控和友方规则 |
| `recon_cue_center_threshold_px` | cue 与本地中心距离阈值 | 依据重投影误差和相机分辨率设置 |

调参顺序建议：先固定几何门控和友方规则，再调 MOT 质量阈值，最后调 cue 权重。不要用 cue 奖励弥补坐标帧错误。

## 12. 仿真验证与指标

现有仿真位于 `simulations/run_terminal_association_sim.py`，覆盖多目标、友方重叠、未知目标接近和遮挡。图表和结果写入 `docs/EXPERIMENT_REPORT.md`。

建议 D5 独立统计：

- `terminal_association_accuracy`
- `locked_precision`
- `wrong_locked_count`
- `ambiguous_count`
- `hold_count`
- `friend_overlap_hold_count`
- `reacquire_count`
- `time_to_terminal_lock`
- `global_track_id_rewrite_count`
- `terminal_id_switch_count`
- `recon_cue_used_count`

其中 `global_track_id_rewrite_count` 期望恒为 0；`wrong_locked_count` 比 `locked` 数量更重要。

## 13. 与其他模块的接口关系

| 模块 | 与 D5 的关系 |
|---|---|
| D2 多目标跟踪与数据关联 | 提供稳定 `GlobalTrack` 和 `global_track_id`，D5 不修改 |
| D3 集中式分配 | 提供 `AssignmentPlan` 和 `Assignment`，D5 只核对本机分配目标 |
| D4 分布式协同与降级接管 | 中心失效时提供降级分配；二级节点可提供 `ReconImageCue` |
| D6 评估体系 | 消费 `TerminalAssociation`、候选代价、身份冲突和 cue 使用日志 |

D5 可以把 `TerminalAssociation` 回传给 D2/D3/D4 作为置信度和歧义事件，但不能直接触发重新分配或局部换绑。

## 14. 实施结构

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

结构规则：

- 根目录保留 `PLAN.md` 和 `README.md`。
- 算法说明、实验报告和 AirSim 离线计划放入 `docs/`。
- Python 源码只放入 `src/d5_terminal_association/`。
- 单元测试只放入 `tests/`。
- 离线仿真脚本只放入 `simulations/`。

## 15. 局限与后续工作

当前实现的主要局限：

- `ReconImageCue` 还没有内置新鲜度和目标相机帧强校验，需由调用方预处理保证。
- 仿真脚本尚未批量生成二级 cue 场景，`recon_cue_used_count` 需要接入 D6 或本模块实验统计。
- 当前时间预测为简化常速度模型，不替代 D2 跟踪器。
- 当前身份声明是仿真模型，不接入真实 Remote ID、MAVLink 或 DDS 安全栈。
- 小目标图像检测质量对 MOT 输入影响很大，需要通过 AirSim 离线回放进一步评估。

后续优先级：

1. 在离线仿真中加入已重投影 `ReconImageCue`、过期 cue 和跨资源 cue 的对照场景。
2. 增加 cue 新鲜度、frame 语义和空 scope 策略的显式配置。
3. 把 `recon_cue_used_count`、stale cue 拒绝次数和 cue 相关误配计入 D6。
4. 用 AirSim 标注框和离线 MOT 输出比较 ByteTrack、BoT-SORT、Deep SORT 的输入质量。
5. 建立失败样本库，重点保存友方重叠、目标交叉、遮挡恢复和跨相机 cue 错配案例。
