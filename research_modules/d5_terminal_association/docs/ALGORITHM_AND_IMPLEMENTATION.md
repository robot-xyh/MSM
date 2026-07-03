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

面向 D4 主动降级仲裁，D5 还应在离线日志或接口层派生 `TerminalConsistencySummary`。它不是新的处置命令，而是把若干帧 `TerminalAssociation` 压缩为“中心/二级分配是否仍与末端视觉证据一致”的状态摘要。

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

### 9.3 已实现约束

当前代码支持 cue 降低代价，并在 `AssociationConfig` 与 `build_cost_matrix()/decide()` 中实现以下约束：

- 新鲜度：`max_recon_cue_age_s` 默认 1 秒；超过阈值或来自未来的 cue 不参与代价。
- 帧一致性：调用方传入 `frame_id` 时，cue 必须位于该目标相机帧，或通过 `metadata["target_frame_id"]` 指向该目标帧。
- 重投影：若 `metadata["source_image_frame_id"]` 与目标帧不同，或 cue 通过 `target_frame_id` 指向目标帧，则必须设置 `metadata["reprojected_to_local_camera"] == True`。
- 资源范围：`scoped_resource_ids` 非空表示仅对指定资源生效；空值按 `allow_broadcast_recon_cue` 配置决定是否视为广播 cue。
- 置信度：`confidence` 只调节负代价大小，不改变门控和授权流程。
- 指标：D6 应记录 `recon_cue_used_count`、cue 命中后 `locked` 比例、cue 相关误配次数和 stale cue 被拒次数。

## 10. 多无人机重叠视场下的终端视觉跨视场配准

### 10.1 问题场景

考虑两个拦截资源的相机具有部分重叠视场：

- 无人机 1 看到目标 1/2/3，生成本地轨迹 `UAV1:cam0:L1/L2/L3`。
- 无人机 2 看到目标 2/3/4，生成本地轨迹 `UAV2:cam0:L1/L2/L3`。

这里的 `local_track_id` 只在本资源、本相机、本帧或短时间窗口内有效。`UAV1:cam0:L2` 和 `UAV2:cam0:L2` 名称相同并不表示同一目标；名称不同也不表示不同目标。跨视场配准必须以 D2 维护的 `global_track_id` 为唯一全局身份锚点，通过相机几何、时间戳、姿态和协方差门控，把多个本地观测被动关联到已有全局航迹。

D5 的原则不变：跨视场模块只能输出关联证据和一致性摘要，不能创建、改写或换绑 `global_track_id`。

### 10.2 当前程序覆盖与缺口

当前 D5 程序已经覆盖：

- 单机视场内多个本地候选的几何门控和代价排序。
- “相机最近目标不等于分配目标”的单机测试。
- 友方身份正向确认导致的 `hold`。
- 二级侦察 `ReconImageCue` 的资源 scope 约束。
- 最小 `TerminalObservationBus` 跨节点摘要汇总。
- `CrossViewAssociation` 对多视角支持和重复终端锁定风险的被动表达。
- `global_track_id` 不被 D5 修改的不变式。

尚未完整实现：

- 完整多无人机、多相机几何融合。
- 跨相机时间戳对齐、相机姿态校验和观测协方差融合。
- `TerminalCrossViewFusion` 级别的跨视场候选融合和协方差级别复核。

因此，当前代码具备“摘要层跨视角汇总”能力，但不表示已经具备完整跨无人机多相机几何融合能力。

### 10.3 推荐数据结构扩展

当前实现新增了摘要层结构：

```python
@dataclass(frozen=True)
class TerminalObservation:
    resource_id: str
    source_node_id: str
    link_type: str
    timestamp: float
    local_track: LocalVisualTrack | None
    terminal_association: TerminalAssociation | None
    identity_claims: tuple[IdentityClaim, ...]
    recon_image_cues: tuple[ReconImageCue, ...]
    camera_id: str | None
    frame_id: str | None
    arrival_timestamp: float | None

@dataclass(frozen=True)
class CrossViewAssociation:
    global_track_id: str
    supporting_resource_ids: tuple[str, ...]
    local_track_ids: tuple[str, ...]
    ambiguity_score: float
    duplicate_terminal_lock_risk: bool
    source_node_id: str
    link_type: str
```

`TerminalObservationBus` 使用 D3/D4/D5 已产生的 `TerminalAssociation.assigned_global_track_id` 分组，不新建全局 ID。`local_track_ids` 被命名空间化为 `resource_id/camera_id:local_track_id`，避免不同无人机都使用 `L1`、`track_1` 时发生冲突。

完整跨视场几何融合时，仍建议扩展或包装为 `CrossViewObservation`，至少包含：

```python
@dataclass(frozen=True)
class CrossViewObservation:
    observation_id: str
    resource_id: str
    camera_id: str
    frame_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    center_px: np.ndarray
    bbox: tuple[float, float, float, float] | None
    covariance_px: np.ndarray
    bearing_rate: np.ndarray
    category: str
    quality: float
    mot_history_length: int
    camera_model: CameraModel
    camera_pose_covariance: np.ndarray | None
    candidate_global_track_ids: tuple[str, ...] = ()
```

也可以直接给 `LocalVisualTrack` 增加以下字段：

- `resource_id`：无人机或拦截资源 ID。
- `camera_id`：相机 ID，例如 `front_rgb`。
- `frame_id`：图像帧坐标系 ID。
- `camera_pose` 或 `camera_model`：量测时刻的相机姿态和内参。
- `covariance` 或 `covariance_px`：本地像素观测不确定性。
- `measurement_timestamp` 与 `arrival_timestamp`：支持异步到达和延迟统计。

后续完整几何融合可增加更细粒度的输出结构，避免与当前摘要层 `CrossViewAssociation` 混淆：

```python
@dataclass(frozen=True)
class CrossViewGeometricAssociation:
    global_track_id: str
    observations: tuple[str, ...]  # CrossViewObservation.observation_id
    per_view_costs: dict[str, float]
    fused_confidence: float
    consistency_state: str  # consistent | ambiguous | conflict | unknown
    reason: str

@dataclass(frozen=True)
class CrossViewTrackEvidence:
    global_track_id: str
    associations: tuple[CrossViewGeometricAssociation, ...]
    fused_confidence: float
    covariance_summary: dict[str, float]
    conflict_state: str
    evidence_source_count: int
```

跨视场融合器可以命名为 `TerminalCrossViewFusion`。当前已实现的 `TerminalObservationBus` 属于更轻量的摘要汇聚层，只负责收集终端摘要、按既有全局 ID 分组并输出风险信号，不拥有分配权。

### 10.4 跨视场关联流程

对于 UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的场景，建议流程如下：

1. 对每个相机观测建立唯一观测键：

```text
obs_key = resource_id + "/" + camera_id + "/" + frame_id + "/" + local_track_id
```

2. 对 D2 输出的每个 `GlobalTrack`，分别按 UAV1 和 UAV2 的 `measurement_timestamp` 做时间预测。
3. 用各自的 `CameraModel` 将同一个 `GlobalTrack` 投影到每个相机平面。
4. 在每个相机内使用像素马氏距离做门控，得到局部候选：

```text
d2_i,j,k = (z_i,k - project_j(camera_i))^T S_i,j^-1 (z_i,k - project_j(camera_i))
```

其中 `i` 是相机/资源，`j` 是 `global_track_id`，`k` 是本地观测。

5. 为每个候选计算综合代价：

```text
C_i,j,k =
  w_geo * d2_i,j,k
  + w_time * |measurement_timestamp_i - track_timestamp_j|
  + w_pose * pose_uncertainty_i
  + w_cov * trace(covariance_px_i,k)
  + w_rate * bearing_rate_error_i,j,k
  + w_category * category_mismatch
  + w_quality * mot_quality_penalty
  + w_friend * friend_conflict_penalty
  + w_recon * recon_cue_bonus
```

6. 对同一 `global_track_id` 汇聚多个视场证据。例如：

```text
G_T2 <- UAV1:cam0:L2 + UAV2:cam0:L1
G_T3 <- UAV1:cam0:L3 + UAV2:cam0:L2
```

7. 若两个视场都支持同一全局航迹且时间差、姿态误差和代价 margin 满足阈值，则后续完整几何融合器可输出 `CrossViewGeometricAssociation.consistency_state="consistent"`。
8. 若 UAV1 和 UAV2 对目标 2/3 的候选交换、代价接近或姿态协方差过大，则输出 `ambiguous`，不强制跨视场绑定。
9. 若某个本地观测与已验证友方身份重叠，则对应全局候选进入 `conflict/hold`，不得被其他视场的弱证据覆盖。
10. 若观测无法投影到任何已有 `global_track_id`，D5 只输出 unmatched/unknown 证据，由 D1/D2 决定是否新建或删除航迹。

### 10.5 时间戳、相机姿态与协方差

跨视场配准比单机配准更依赖时空基准：

- 使用 `measurement_timestamp` 做几何投影时间，不能用晚到的 `arrival_timestamp` 直接投影。
- `arrival_timestamp - measurement_timestamp` 应进入日志，用于分析通信延迟和 cue 过期。
- 每个相机姿态必须对应量测时刻；若姿态来自插值，应记录插值误差或姿态协方差。
- 相机姿态不确定性应扩大像素门控，而不是把投影点当作精确值。
- 高速相对运动时，不同无人机相机之间超过阈值的时间差应导致 `ambiguous/unknown`。

### 10.6 二级侦察 cue 在跨视场中的使用

`ReconImageCue` 在跨视场中仍是辅助证据，不是全局身份来源。推荐规则：

- 二级节点原始像素 cue 必须分别重投影到 UAV1、UAV2 等目标相机平面。
- `image_frame_id` 应标识重投影后的目标相机帧，例如 `UAV1/front_rgb`；原始二级相机帧放入 `metadata.source_image_frame_id`。
- `scoped_resource_ids=("UAV1", "UAV2")` 表示该 cue 只允许这两个资源使用。
- 对 UAV1 生效的 cue 不应自动对 UAV2 生效，除非已重投影到 UAV2 的相机平面并在 scope 内。
- cue 只能降低 `C_recon`，不能绕过几何门控、版本校验、友方 `hold` 或 D3/D4 分配。

### 10.7 接口建议

当前已实现最小摘要总线：

```python
bus = TerminalObservationBus()

bus.publish_terminal_association(
    resource_id="UAV1",
    source_node_id="UAV1",
    link_type="interceptor_peer",
    timestamp=current_time,
    terminal_association=decision_uav1,
    local_track=local_track_uav1,
    camera_id="front_rgb",
    frame_id="UAV1/front_rgb",
)

cross_view = bus.cross_view_associations()
```

在 UAV1 看到 1/2/3、UAV2 看到 2/3/4 的测试中，`cross_view_associations()` 会产生：

- `G2/G3`：`supporting_resource_ids=("UAV1", "UAV2")`，表示多视角支持。
- `G1/G4`：仅保留单视角支持。
- 对同一个 `global_track_id` 出现多个资源 `locked` 时，设置 `duplicate_terminal_lock_risk=True`。该字段只上报给 D3/D4/D6，不修改既有分配。

后续完整几何融合建议新增第二层：

```python
class TerminalCrossViewFusion:
    def associate(
        self,
        global_tracks: list[GlobalTrack],
        observations: list[CrossViewObservation],
        recon_image_cues: list[ReconImageCue],
        current_time: float,
    ) -> list[CrossViewGeometricAssociation]: ...
```

主程序仍可对每个资源调用现有 `TerminalAssociator.decide()` 生成单机 `TerminalAssociation`；跨视场层再基于多个 `TerminalAssociation` 和 `CrossViewAssociation` 派生全局一致性摘要。这样可以保持现有单机逻辑稳定，同时逐步扩展多相机能力。

## 11. 关键接口

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

跨视角摘要可在每个资源完成 `decide()` 后写入总线：

```python
bus.publish_terminal_association(
    resource_id=assignment.resource_id,
    source_node_id=assignment.resource_id,
    link_type="interceptor_peer",
    timestamp=current_time,
    terminal_association=decision,
    local_track=matched_local_track,
    recon_image_cues=reprojected_recon_cues,
    camera_id="front_rgb",
    frame_id=f"{assignment.resource_id}/front_rgb",
)

cross_view_summary = bus.cross_view_associations()
```

`cross_view_summary` 只用于 D3/D4/D6 的一致性、重复锁定风险和多视角支持分析，不生成新的 `AssignmentPlan`。

AirSim ComputerVision dry-run 检测输入可先转为本地观测：

```python
tracks = publish_sim_detections_as_local_observations(
    bus=bus,
    detections=sim_get_detections_like_records,
    resource_id="Interceptor_Cam_1",
    camera_id="front_rgb",
    frame_id="Interceptor_Cam_1/front_rgb",
    timestamp=measurement_timestamp,
    arrival_timestamp=arrival_timestamp,
)

metrics = compute_terminal_stress_metrics(
    observations=bus.observations(),
    cross_view_associations=bus.cross_view_associations(),
)

evidence = summarize_degradation_case(
    observations=bus.observations(),
    cross_view_associations=bus.cross_view_associations(),
    current_time=current_time,
)
```

`evidence.case_name` 只能作为 D4 仲裁输入，不是分配计划。

## 12. 参数与调参建议

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

## 13. 仿真验证与指标

现有仿真位于 `simulations/run_terminal_association_sim.py`，覆盖多目标、友方重叠、未知目标接近和遮挡。图表和结果写入 `docs/EXPERIMENT_REPORT.md`。

AirSim ComputerVision 5v5 专项测试采用纯离线数据合同：5 个 `Interceptor_Cam_*` 主镜头、5 个目标，目标距镜头约 50m，目标间距和镜头间距约 20m，使每个主镜头视场内出现多个目标。二级系留侦察镜头比目标高约 200m，输出高分辨率全局视野 cue；进入 D5 前必须重投影到目标拦截机相机平面。

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
- `candidate_cost_margin`
- `terminal_lock_age_s`
- `consecutive_ambiguous_frames`
- `consecutive_hold_frames`
- `consecutive_reacquire_frames`
- `terminal_consistency_state`
- `cross_view_association_accuracy`
- `cross_view_id_switch_count`
- `cross_view_ambiguous_count`
- `cross_view_duplicate_local_id_count`
- `per_camera_detection_count`
- `multi_target_fov_rate`
- `cross_view_overlap_count`
- `duplicate_terminal_lock_risk`
- `terminal_lock_accuracy`
- `ambiguous_fov_event_count`

5v5 专项三类 D5 证据：

- `no_degradation`：终端锁定与 D3 分配及离线评估真值一致。
- `degrade_to_secondary`：中心分配与终端局部/二级证据持续不一致或歧义，且二级 `ReconImageCue` 新鲜可用。
- `degrade_to_distributed`：同样不一致或歧义，但二级证据不可用、过期或失效，只能给 D4 提供分散降级证据。

其中 `global_track_id_rewrite_count` 期望恒为 0；`wrong_locked_count` 比 `locked` 数量更重要。

## 14. 与其他模块的接口关系

| 模块 | 与 D5 的关系 |
|---|---|
| D2 多目标跟踪与数据关联 | 提供稳定 `GlobalTrack` 和 `global_track_id`，D5 不修改 |
| D3 集中式分配 | 提供 `AssignmentPlan` 和 `Assignment`，D5 只核对本机分配目标 |
| D4 分布式协同与降级接管 | 中心失效时提供降级分配；二级节点可提供 `ReconImageCue` |
| D6 评估体系 | 消费 `TerminalAssociation`、候选代价、身份冲突和 cue 使用日志 |

D5 可以把 `TerminalAssociation` 回传给 D2/D3/D4 作为置信度和歧义事件，但不能直接触发重新分配或局部换绑。

## 15. 面向 D4 主动降级的一致性与冲突信号

D4 主动降级策略需要判断“中心或二级节点给出的分配是否仍被末端视觉证据支持”。D5 不做降级决策，只提供可解释、带时间连续性的末端一致性信号。D4 可将这些信号与 D1/D2 航迹质量、D3 分配版本、通信健康状态和二级节点覆盖状态结合，决定是否请求二级 cue、继续观测、切换二级节点仲裁或进入分布式协商。

### 15.1 D5 可提供的基础信号

| 信号 | 来源 | 含义 | 给 D4/D3 的用途 |
|---|---|---|---|
| `decision_state` | `TerminalAssociation` | 当前帧为 `locked/ambiguous/hold/reacquire` | 主状态输入 |
| `association_confidence` | `TerminalAssociation` | 当前最佳候选的几何和质量置信度 | 判断锁定质量是否稳定 |
| `ambiguity_score` | `TerminalAssociation` | 候选区分度不足程度 | 判断是否需要二级 cue 或继续观测 |
| `friend_conflict_state` | `TerminalAssociation` | 是否存在已验证友方或可疑身份重叠 | 防止错误换绑和冲突升级 |
| `candidate_cost_margin` | `candidate_costs` 派生 | 最佳候选与次优候选代价差 | 判断最佳候选是否足够唯一 |
| `recon_cue_used` | `TerminalAssociation` | 是否使用二级侦察 cue 降低代价 | 区分“自相机稳定锁定”和“依赖二级 cue” |
| `terminal_lock_age_s` | 时序状态派生 | 连续 `locked` 且目标版本一致的持续时间 | 判断锁定是否稳定 |
| `consecutive_ambiguous_frames` | 时序状态派生 | 连续歧义帧数 | 触发请求二级 cue 或继续观测 |
| `consecutive_hold_frames` | 时序状态派生 | 连续保守暂停帧数 | 触发友方冲突或版本冲突上报 |
| `consecutive_reacquire_frames` | 时序状态派生 | 连续重捕获失败帧数 | 触发 D4 主动仲裁候选 |
| `local_best_conflicts_with_assignment` | 被动全局候选比较派生 | 本地长期最佳视觉候选不支持当前分配 | 触发主动仲裁，但不得本地换绑 |

`candidate_cost_margin` 建议按候选代价排序计算：

```text
if len(candidate_costs) >= 2:
    candidate_cost_margin = cost_2nd_best - cost_best
else:
    candidate_cost_margin = +inf
```

margin 越小，表示候选越难区分。若仅有一个候选但其总代价高，也不应把 `+inf` margin 误解为可靠锁定，仍需结合 `association_confidence` 和 `decision_state`。

### 15.2 TerminalConsistencySummary 字段建议

D5 已在接口层增加如下摘要结构。该结构由连续帧 `TerminalAssociation` 派生，不要求也不允许 D5 直接修改 D3/D4 分配。

```python
@dataclass(frozen=True)
class TerminalConsistencySummary:
    resource_id: str
    assigned_global_track_id: str
    assignment_version: int
    timestamp: float
    decision_state: str
    consistency_state: str  # consistent | inconsistent | unknown | conflict
    association_confidence: float
    ambiguity_score: float
    friend_conflict_state: str
    candidate_cost_margin: float
    recon_cue_used: bool
    terminal_lock_age_s: float
    consecutive_locked_frames: int
    consecutive_ambiguous_frames: int
    consecutive_hold_frames: int
    consecutive_reacquire_frames: int
    local_track_id: str | None
    previous_decision_state: str | None
    lock_lifecycle_state: str
    lost_lock_event: bool
    lock_reacquired_event: bool
    event_summary: str
    competing_global_track_id: str | None
    local_best_conflicts_with_assignment: bool
    duplicate_terminal_lock_risk: bool
    duplicate_lock_resource_ids: tuple[str, ...]
    duplicate_local_track_ids: tuple[str, ...]
    cross_view_support_count: int
    cross_view_supporting_resource_ids: tuple[str, ...]
    cross_view_decision_states: tuple[str, ...]
    recommended_d4_action: str  # observe | request_secondary_cue | report_conflict | arbitrate
    reason: str
```

字段解释：

- `consistency_state="consistent"`：分配 ID 与版本一致，且当前帧或一段时间内有稳定 `locked` 证据。
- `consistency_state="inconsistent"`：本地被动比较显示长期最佳视觉候选不支持当前 `assigned_global_track_id`，或版本/候选关系持续冲突。
- `consistency_state="unknown"`：信息不足，例如连续 `ambiguous` 或 `reacquire`，无法确认分配是否错误。
- `consistency_state="conflict"`：已验证友方重叠、授权/版本冲突、身份冲突或重复锁定风险；此时不应自动换绑。
- `competing_global_track_id` 只允许来自 D2 已存在的全局航迹被动比较结果，用于上报仲裁；D5 不能把它写回为新的分配 ID。
- `lost_lock_event` 和 `lock_reacquired_event` 只表达状态迁移事件，用于 D4/D6 统计丢锁和重捕获耗时。
- `cross_view_support_count` 与 `duplicate_terminal_lock_risk` 来自 `TerminalObservationBus.cross_view_associations()`，用于把单资源状态与多视角支持/重复锁定风险统一到同一摘要。
- `recommended_d4_action` 只是仲裁建议，不是执行动作。D4 仍需结合系统级风险和健康状态决定。

### 15.3 一致性判定规则

推荐的 D5 侧判定逻辑：

| 场景 | D5 一致性状态 | 给 D4 的建议 |
|---|---|---|
| `locked`，`assigned_global_track_id` 存在，`assignment_version` 一致，置信度高，margin 足够 | `consistent` | `observe`，不触发主动降级 |
| `locked` 但依赖 `recon_cue_used=True`，且自相机置信度中等 | `consistent` 或 `unknown` | 继续观测并记录 cue 依赖，必要时请求二级节点持续 cue |
| 多帧 `ambiguous`，无友方重叠 | `unknown` | `request_secondary_cue` 或继续观测 |
| 已验证友方重叠导致 `hold` | `conflict` | `report_conflict`，不自动换绑，不把未知/友方解释为分配目标 |
| 版本不一致或授权状态不满足导致 `hold` | `conflict` | 上报 D3/D4 版本冲突，等待仲裁 |
| 多帧 `reacquire`，且 D1/D2 航迹不确定性、D3 分配风险或通信健康风险较高 | `unknown` | `arbitrate`，建议 D4 主动仲裁 |
| 被动全局候选比较显示本地最佳视觉候选长期不是 `assigned_global_track_id` | `inconsistent` | `arbitrate`，触发主动仲裁；D5 不本地改写 ID |
| 单帧低置信 `ambiguous/reacquire` | `unknown` | 不立即降级，继续观测 |

主动降级触发应使用“连续帧 + 风险门限”，避免单帧图像噪声导致频繁切换。建议初始阈值：

- `consecutive_ambiguous_frames >= 5`：请求二级侦察节点 cue 或继续观测。
- `consecutive_reacquire_frames >= 5` 且 D1/D2/D3 任一风险高：建议 D4 主动仲裁。
- `consecutive_hold_frames >= 2` 且 `friend_conflict_state="verified_friend_overlap"`：上报友方冲突，禁止本地换绑。
- `local_best_conflicts_with_assignment` 持续 `>= 3` 个评估周期：建议 D4 仲裁中心/二级节点分配。
- `terminal_lock_age_s >= 1.0` 且 `candidate_cost_margin >= min_lock_margin`：认为末端一致性较稳定。

这些阈值只用于离线仿真初值，应通过 D6 批量实验评估误报率、漏报率和仲裁频率。

### 15.4 本地最佳候选不等于分配目标的处理

为支持“本地最优视觉候选长期不是 assigned_global_track_id”的检测，D5 可在不改变当前 `decide()` 保守语义的前提下，增加一个被动一致性观测流程：

1. 对 D2 提供的若干 `GlobalTrack` 同时执行 `project_tracks_to_image()`。
2. 对本地 `LocalVisualTrack[]` 构造全局候选代价矩阵。
3. 比较当前 `Assignment.assigned_global_track_id` 的最佳候选与其他全局航迹的最佳候选。
4. 若其他全局航迹长期拥有更低代价、更高置信度且版本新鲜，则设置 `local_best_conflicts_with_assignment=True`，并填充 `competing_global_track_id`。
5. 该结果只上报 D4/D3 仲裁，禁止 D5 本地改写 `assigned_global_track_id`。

该流程是“被动一致性检查”，不是局部分配器。它尤其适合中心节点可能延迟、二级节点 cue 覆盖不完整或多目标交叉后分配关系可疑的离线分析场景。

### 15.5 D4 主动降级接口建议

D5 建议向 D4 发布或记录如下事件流：

```text
/terminal/consistency_summary
```

每条消息包含：

- 当前 `TerminalConsistencySummary`。
- 最近窗口统计，例如 `window_size_frames`、`locked_ratio`、`ambiguous_ratio`、`hold_ratio`、`reacquire_ratio`。
- 最近一次 `ReconImageCue` 使用情况和 cue 来源节点。
- 最近一次友方冲突状态。

D4 使用建议：

- `consistent`：不因 D5 触发主动降级。
- `unknown + ambiguous`：优先请求二级侦察 cue 或延长观测窗口。
- `conflict + verified_friend_overlap`：进入冲突上报和保守等待，不自动换绑。
- `unknown + reacquire` 且系统风险高：主动仲裁，可考虑二级节点接管或重新分配。
- `inconsistent`：主动仲裁中心/二级分配关系，但仍由 D4/D3 生成新计划版本。

## 16. 实施结构

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
│   ├── airsim_cv_adapter.py
│   ├── associator.py
│   ├── geometry.py
│   ├── identity.py
│   ├── observation_bus.py
│   └── models.py
└── tests/
    ├── test_airsim_cv_5v5_evidence.py
    ├── test_terminal_association.py
    ├── test_airsim_dry_run_interface.py
    └── test_terminal_observation_bus.py
```

结构规则：

- 根目录保留 `PLAN.md` 和 `README.md`。
- 算法说明、实验报告和 AirSim 离线计划放入 `docs/`。
- Python 源码只放入 `src/d5_terminal_association/`。
- 单元测试只放入 `tests/`。
- 离线仿真脚本只放入 `simulations/`。

其中 `observation_bus.py` 是本次新增的最小跨视角摘要层，只输出 `CrossViewAssociation` 支持关系和风险信号，不参与分配或控制。
`airsim_cv_adapter.py` 是 5v5 ComputerVision dry-run 适配层，只把检测框转换为 `LocalVisualTrack`/`TerminalObservation`，并计算 D5 证据指标；它不导入 AirSim、不调用仿真器、不生成 `AssignmentPlan`。

## 17. 局限与后续工作

当前实现的主要局限：

- 仿真脚本尚未批量生成二级 cue 场景，`recon_cue_used_count` 需要接入 D6 或本模块实验统计。
- 本地最佳候选与全局分配的被动一致性比较尚未形成独立测试场景。
- 已实现最小 `TerminalObservationBus`、`CrossViewAssociation` 与 `TerminalConsistencySummary`，但跨无人机多相机几何融合尚未完整实现；`CrossViewObservation`、`CrossViewTrackEvidence` 和 `TerminalCrossViewFusion` 仍是接口建议。
- 当前时间预测为简化常速度模型，不替代 D2 跟踪器。
- 当前身份声明是仿真模型，不接入真实 Remote ID、MAVLink 或 DDS 安全栈。
- 小目标图像检测质量对 MOT 输入影响很大，需要通过 AirSim 离线回放进一步评估。

后续优先级：

1. 把 `recon_cue_used_count`、stale cue 拒绝次数和 cue 相关误配计入 D6。
2. 增加本地最佳候选长期偏离中心分配的被动一致性测试。
3. 扩展 `TerminalObservationBus` 的窗口、过期剔除和统计接口，并实现 `TerminalCrossViewFusion` 的离线原型，覆盖 UAV1 看到 1/2/3、UAV2 看到 2/3/4 的重叠视场几何融合场景。
4. 给 `LocalVisualTrack` 或其包装结构增加 `resource_id/camera_id/frame_id/camera_pose/covariance`。
8. 用 AirSim 标注框和离线 MOT 输出比较 ByteTrack、BoT-SORT、Deep SORT 的输入质量。
9. 建立失败样本库，重点保存友方重叠、目标交叉、遮挡恢复、多相机时间错位和跨相机 cue 错配案例。
