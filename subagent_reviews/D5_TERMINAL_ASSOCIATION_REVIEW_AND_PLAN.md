# D5 末端视觉配准与协同身份认证综述及子方案

**定位**: 分配完成后，资源节点末端视场内可能同时出现多个目标、友方资源和未知飞行物。本模块负责把局部视觉目标配准回中心分配的 `global_track_id`。  
**边界**: 本文只讨论视觉配准、协同身份认证和保守决策，不包含真实火控参数、毁伤逻辑、自动处置控制律或绕过人工授权的流程。

---

## 0. 阶段补充：二级侦察节点图像 cue

本阶段假设存在若干高空系留侦察无人机作为二级节点。中心节点正常时，二级节点持续把本覆盖小区内的侦察图像或图像平面 cue 发给若干拦截资源；中心节点失效时，D4 可将局部协调权降级到二级节点；二级节点失效后才进入完全无中心协商。

D5 使用这些 cue 的原则：

- 二级节点 cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心/框、置信度和 `scoped_resource_ids`。
- cue 只在指定小范围资源内生效，不能跨覆盖区使用。
- cue 只作为视觉关联代价的辅助证据，不能替代中心授权、版本匹配、友方身份认证和本地 MOT 质量门槛。
- 即使二级节点 cue 与本地相机目标一致，局部节点也只能输出 `TerminalAssociation`，不得自行改写 `global_track_id`。

### 0.1 与二级节点图像下发的坐标约束

二级高空侦察节点下发的图像或像素 cue 不能直接等同于拦截无人机本机相机坐标。若二级节点给出的是自身相机画面中的像素框，必须先通过仿真真值、D1/D2 全局航迹或几何重投影，转换到目标拦截无人机的相机平面，才能和本机 `LocalVisualTrack.center_px` 比较。

建议 `ReconImageCue` 的 `image_frame_id` 使用目标相机帧，例如 `UAV1/front_rgb`；原始二级节点相机帧放入 `metadata.source_image_frame_id`。`scoped_resource_ids` 必须限定 cue 可用资源，例如 `["UAV1", "UAV2"]`，避免未覆盖资源错误使用 cue。

### 0.2 本轮 5v5 AirSim ComputerVision D4/D5 专项适配

D5 已补充 dry-run 适配层，用于消费 `simGetDetections` 风格检测框 fixture，不导入 AirSim、不调用控制 API。专项几何假设为：5 个 `Interceptor_Cam_*` 主镜头，5 个目标，目标距主镜头约 50m，目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标；二级系留侦察镜头比目标高约 200m，分辨率更高并提供全局视野 cue。

D5 输出边界保持不变：

- 可输出 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservationBus` 和 `CrossViewAssociation` 摘要。
- 不生成 `AssignmentPlan`。
- 不改写 `global_track_id`。
- 重复锁定只输出 `duplicate_terminal_lock_risk`，交由 D3/D4 仲裁。

三类 D5 证据 case：

- `no_degradation`：终端锁定与 D3 分配及离线评估真值一致。
- `degrade_to_secondary`：终端局部/二级证据与中心分配持续不一致或歧义，且二级 `ReconImageCue` 新鲜可用。
- `degrade_to_distributed`：同样不一致或歧义，但二级证据不可用、过期或失效，只能提供分散降级证据。

建议指标：`per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy`、`ambiguous_fov_event_count`。

---

## 1. 研究问题

末端视场中“最近目标”不一定是分配目标。局部相机可能同时看到：

- 中心分配的目标；
- 其他来袭目标；
- 友方资源节点；
- 空中侦察无人机；
- 未知或无关飞行物。

如果局部节点自行换绑 `global_track_id`，会造成重复分配、漏分配、ID Switch 或友方安全风险。因此末端节点只能输出 `TerminalAssociation`，不能直接改写中心分配。

### 1.1 多无人机重叠视场问题

阶段一 AirSim Blocks 或后续离线回放中，会出现多个拦截无人机同时观察同一空域但视场不完全重叠的情况。例如：

```text
UAV1 camera sees: target 1, target 2, target 3
UAV2 camera sees: target 2, target 3, target 4
```

这里 `UAV1` 和 `UAV2` 都可能生成 `local_track_id="L2"`，但它们只是各自相机/MOT 内部的本地编号，不能用字符串相等判断是否为同一目标。D5 必须把本地轨迹限定在 `(resource_id, camera_id, frame_id, local_track_id)` 命名空间下，再通过 D2 提供的 `GlobalTrack`、相机投影、时间戳、姿态和协方差门控，将本地观测配准到既有 `global_track_id`。

单视角目标不是错误：目标 1 只出现在 UAV1，目标 4 只出现在 UAV2，可能是视场边界、遮挡或距离造成的正常现象。D5 不能因为另一个视角未观察到目标就删除航迹或判定分配错误，只能降低跨视角一致性置信度，必要时输出 `hold/reacquire/ambiguous`。

---

## 2. 文献综述要点

局部 MOT 方面，ByteTrack 通过高低置信检测两阶段关联提升召回率，适合短时遮挡和小目标跟踪；BoT-SORT 加入相机运动补偿和 ReID，更适合运动相机；Deep SORT 使用深度外观特征，能降低 ID Switch，但无人机视角下目标小、模糊、逆光和外观相似会导致退化。

几何配准方面，OpenCV 标定、`solvePnP/projectPoints` 和 ROS 2 `tf2` 是默认工具链。核心不是全图识别，而是把 `GlobalTrack` 预测位置投影到相机平面，生成几何门限，再与 `LocalVisualTrack` 做关联。

身份认证方面，Remote ID/OpenDroneID、MAVLink signing、DDS Security 和任务内协同 ID 都只能正向确认友方或协同方。未知目标不能自动等同于敌方。AprilTag 等视觉标签可用于实验室合作目标，但不能作为复杂环境中的唯一身份依据。

---

## 3. 开源代码选型

| 工具 | 用途 | 适用性 |
|------|------|--------|
| ByteTrack | 局部MOT默认基线 | 小目标短时遮挡较稳，但不负责全局身份 |
| BoT-SORT | 运动相机MOT | 有相机运动补偿，适合资源节点视角 |
| Deep SORT | 外观辅助MOT | 纹理足时有效，低分辨率会退化 |
| OpenCV Calibration/solvePnP | 相机标定和投影 | 几何配准核心 |
| ROS 2 tf2 | 坐标变换 | 维护世界系、机体系、相机系 |
| OpenDroneID | Remote ID实现 | 仅作身份声明证据 |
| MAVLink signing / DDS Security | 消息来源认证 | 需与任务清单交叉验证 |
| AprilTag | 合作视觉标识 | 近距实验辅助 |

---

## 4. 处理链路

```text
AssignmentPlan.assigned_global_track_id
-> GlobalTrack按measurement_timestamp预测
-> tf2转换到camera_frame
-> OpenCV投影到图像平面
-> 生成几何门限
-> ByteTrack/BoT-SORT/Deep SORT生成LocalVisualTrack
-> Hungarian/JPDA匹配LocalVisualTrack与GlobalTrack
-> IdentityClaim做友方正向确认
-> 输出 locked | ambiguous | hold | reacquire
```

### 4.1 多视角跨视场处理链路

多视角情况下，D5 需要在“单机终端关联”之外增加一个被动跨视场汇总层。该层不分配目标，只把多个局部视觉证据配准到中心/二级节点已有的 `global_track_id`。

```text
UAV1 LocalVisualTrack[]
UAV2 LocalVisualTrack[]
...
-> TerminalObservationBus按(resource_id, camera_id, frame_id, local_track_id)汇聚
-> 对每个GlobalTrack按各相机measurement_timestamp预测
-> 用每个相机的CameraModel把同一GlobalTrack投影到对应图像平面
-> 每个相机内做像素马氏门控和候选代价排序
-> 跨视角合并同一global_track_id的支持证据
-> 输出CrossViewAssociation / TerminalConsistencySummary
```

核心原则：

- `local_track_id` 不跨资源共享语义，只是局部观测编号。
- `global_track_id` 只能来自 D2/D3/D4 的全局航迹和分配计划。
- 一个 `global_track_id` 可以被多个视角同时支持，也可以暂时只有单视角支持。
- 跨视角证据冲突时输出 `ambiguous/conflict/mismatch`，不得由 D5 本地改写 `global_track_id`。

### 4.2 示例：UAV1 sees {1,2,3}, UAV2 sees {2,3,4}

假设 D2 当前维护四条全局航迹：

```text
G1 -> target 1
G2 -> target 2
G3 -> target 3
G4 -> target 4
```

UAV1 的局部 MOT 输出：

```text
UAV1/front/L_a, UAV1/front/L_b, UAV1/front/L_c
```

UAV2 的局部 MOT 输出：

```text
UAV2/front/L_a, UAV2/front/L_b, UAV2/front/L_c
```

即使两个无人机都出现 `L_a/L_b/L_c`，这些 ID 也不能直接比较。正确流程是：

1. 对 `G1/G2/G3/G4` 分别投影到 UAV1 相机平面。
2. 对 `G1/G2/G3/G4` 分别投影到 UAV2 相机平面。
3. UAV1 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G1/G2/G3` 的候选代价。
4. UAV2 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G2/G3/G4` 的候选代价。
5. 对共享目标 `G2/G3`，合并 UAV1 和 UAV2 的支持证据：若两个视角都在门内、时间差可接受、姿态协方差可接受、候选 margin 足够，则提高 `G2/G3` 的跨视角一致性置信度。
6. 对单视角目标 `G1/G4`，保持单视角置信，不因另一架无人机未观察到而判错。若该资源被分配到对应目标，可继续由本资源做单机 `TerminalAssociation`；若投影不可见或候选缺失，则输出 `reacquire`。
7. 若 UAV1 和 UAV2 都对同一个 `global_track_id` 输出 `locked`，但 D3/D4 只允许一个主资源负责该目标，则 D5 只上报“重复锁定风险”，由 D3/D4 仲裁，D5 不自行取消或换绑任一资源。

避免重复锁定同一目标的建议：

- D5 输出 `TerminalAssociation` 时携带 `resource_id`、`assigned_global_track_id`、`local_track_id`、`decision_state` 和 `association_confidence`。
- 跨视场层输出 `CrossViewAssociation`，记录同一 `global_track_id` 被哪些资源支持。
- 若多个资源同时 `locked` 同一 `assigned_global_track_id`，且 AssignmentPlan 不允许多资源协同，则输出 `duplicate_terminal_lock_risk` 给 D4/D3。
- D3/D4 根据计划版本、资源状态、视场质量和任务优先级决定保留哪个资源为主，其他资源降为观察/备份；D5 不直接改分配计划。

---

## 5. 数据结构

```text
LocalVisualTrack
- local_track_id
- resource_id        # 建议扩展，避免跨无人机ID冲突
- camera_id          # 建议扩展，标识相机
- frame_id           # 建议扩展，标识图像帧/坐标系
- bbox
- center_px
- covariance_px      # 建议扩展，本地像素观测不确定性
- camera_pose        # 建议扩展，量测时刻相机姿态或CameraModel引用
- bearing_rate
- mot_history_length
- candidate_global_track_ids
- quality

TerminalAssociation
- assigned_global_track_id
- local_track_id
- association_confidence
- ambiguity_score
- friend_conflict_state
- decision_state: locked | ambiguous | hold | reacquire
- assignment_version

IdentityClaim
- platform_id
- claim_type: cooperative_id | remote_id | visual_tag
- auth_state: verified | stale | unverified | spoof_suspected
- associated_track_id
- timestamp
```

建议新增跨视场结构：

```text
CrossViewObservation
- observation_id
- resource_id
- camera_id
- frame_id
- local_track_id
- measurement_timestamp
- arrival_timestamp
- center_px
- bbox
- covariance_px
- camera_pose / camera_model
- mot_history_length
- quality

CrossViewAssociation
- global_track_id
- supporting_observations: [(resource_id, camera_id, local_track_id)]
- per_view_costs
- fused_confidence
- consistency_state: consistent | ambiguous | conflict | unknown
- duplicate_terminal_lock_risk

TerminalConsistencySummary
- resource_id
- assigned_global_track_id
- decision_state
- association_confidence
- ambiguity_score
- friend_conflict_state
- candidate_cost_margin
- recon_cue_used
- mismatch_with_assignment
- recommended_d4_action: observe | request_secondary_cue | report_conflict | arbitrate
```

---

## 6. 匹配代价

```text
terminal_association_cost =
    image_projection_error
  + los_rate_consistency_error
  + timestamp_latency_penalty
  + track_covariance_penalty
  + mot_history_penalty
  + class_mismatch_penalty
  + friend_identity_conflict_penalty
```

只有候选唯一、代价差距明显、无友方冲突且版本匹配时，才能进入 `locked`。

跨视角时，单视角代价先独立计算，再做全局航迹级证据合并：

```text
cross_view_cost(global_track_id) =
    sum(valid_view_costs)
  + timestamp_skew_penalty
  + camera_pose_uncertainty_penalty
  + missing_view_penalty_if_expected_visible
  + duplicate_lock_risk_penalty
```

注意 `missing_view_penalty_if_expected_visible` 只能在几何上确认目标应在该相机视场内时使用。若目标本来就在视场外，不能因为缺失观测惩罚该 `global_track_id`。

---

## 7. 决策伪代码

```python
def terminal_association(global_track, assignment, local_tracks, claims):
    if assignment.assigned_global_track_id != global_track.global_track_id:
        return TerminalAssociation(decision_state="hold")

    gate = project_global_track_to_image(global_track)
    candidates = []

    for local in local_tracks:
        if not inside_projection_gate(local, gate):
            continue
        cost = projection_cost(local, gate)
        cost += los_rate_cost(local, global_track)
        cost += identity_conflict_cost(local, claims)
        candidates.append((cost, local))

    best, margin = select_unique_candidate(candidates)
    friend_state = evaluate_positive_friend_claim(best, claims)

    if friend_state == "friend_conflict":
        return TerminalAssociation(decision_state="hold")
    if best is None:
        return TerminalAssociation(decision_state="reacquire")
    if margin < MIN_MARGIN:
        return TerminalAssociation(decision_state="ambiguous")

    return TerminalAssociation(decision_state="locked")
```

### 7.1 跨视场汇总伪代码

```python
def cross_view_association(global_tracks, observations_by_resource, cameras, assignment_plan):
    cross_view_results = []

    for global_track in global_tracks:
        supports = []
        conflicts = []

        for resource_id, local_tracks in observations_by_resource.items():
            camera = cameras[resource_id]
            predicted = predict_to_measurement_time(global_track, camera.timestamp)
            projection = project_global_track_to_camera(predicted, camera)

            if not projection.valid:
                continue

            candidates = gate_local_tracks(local_tracks, projection)
            best = select_best_candidate(candidates)

            if best.is_friend_conflict:
                conflicts.append((resource_id, best.local_track_id))
            elif best.is_valid:
                supports.append((resource_id, best.local_track_id, best.cost))

        if conflicts:
            state = "conflict"
        elif len(supports) >= 2:
            state = "consistent"
        elif len(supports) == 1:
            state = "single_view_supported"
        else:
            state = "unknown"

        cross_view_results.append(
            CrossViewAssociation(
                global_track_id=global_track.global_track_id,
                supporting_observations=supports,
                consistency_state=state,
            )
        )

    duplicate_risks = detect_duplicate_terminal_locks(cross_view_results, assignment_plan)
    return cross_view_results, duplicate_risks
```

`single_view_supported` 不是错误状态。它表示当前只有一个视角提供有效证据，需要结合 D2 航迹质量、相机视场覆盖和 D4/D3 分配计划判断是否足够。

---

## 8. 失败案例测试

| 场景 | 期望状态 |
|------|----------|
| 最近目标不是分配目标 | 锁定投影门内匹配目标，不抢绑最近目标 |
| 短时遮挡 | `hold -> reacquire` |
| Remote ID匹配但签名失败 | `ambiguous/hold` |
| AprilTag可见但投影残差异常 | 拒绝身份提升 |
| 外参偏移 | 投影门失败并记录校准告警 |
| 时间戳延迟 | 预测补偿后再匹配 |
| 两候选代价接近 | `ambiguous`，不上报锁定 |
| UAV1/UAV2 本地ID同名 | 不按 `local_track_id` 字符串合并，必须使用 `(resource_id,camera_id,local_track_id)` |
| 目标2/3被两个视角看到 | 合并为对同一 `global_track_id` 的多视角支持证据 |
| 目标1/4仅单视角可见 | 保持单视角置信，不判为错误 |
| 两资源同时锁定同一目标 | 上报 `duplicate_terminal_lock_risk` 给 D4/D3 仲裁 |
| 二级cue未重投影 | 不得用于本机 `LocalVisualTrack.center_px` 代价计算 |
| AssignmentPlan与末端视觉不一致 | 输出 `mismatch/ambiguous`，触发D4仲裁，不本地换绑 |

---

## 9. 与 D4 主动降级的仲裁接口

D5 是 D4 主动降级的重要观测源，但不是降级决策者。D4 需要判断中心/二级节点分配与末端视觉证据是否一致：

| D5 输出 | D4 含义 | 建议动作 |
|---------|---------|----------|
| `locked` 且 `assigned_global_track_id`/版本一致 | 分配与末端视觉一致 | 继续当前计划 |
| 多帧 `ambiguous` | 末端证据不足或候选接近 | 请求二级侦察 cue 或延长观测 |
| `hold` + `verified_friend_overlap` | 友方/合作目标重叠 | 上报冲突，不自动换绑 |
| 多帧 `reacquire` | 视场内无法确认分配目标 | D4 结合 D1/D2/D3 风险主动仲裁 |
| `mismatch_with_assignment=True` | 本地最佳视觉证据长期不支持当前 AssignmentPlan | D4 仲裁中心/二级节点分配 |
| `duplicate_terminal_lock_risk=True` | 多资源可能重复锁定同一目标 | D4/D3 调整主备资源或计划版本 |

主动降级触发建议使用连续帧统计，避免单帧检测噪声导致抖动：

- `consecutive_ambiguous_frames >= 5`：请求二级节点 cue 或继续观测。
- `consecutive_reacquire_frames >= 5` 且 D1/D2 航迹质量下降：建议 D4 仲裁。
- `friend_conflict_state="verified_friend_overlap"` 连续出现：上报冲突并保持 `hold`。
- 同一 `global_track_id` 被多个资源 `locked` 且计划不允许多资源协同：上报重复锁定风险。

无论 D4 是否决定降级到二级节点或分布式协商，D5 都只能输出视觉配准和身份确认证据，不得直接生成新 AssignmentPlan。

---

## 10. 与 D7 视觉比例导引/LOS 的接口

D7 负责末端视觉比例导引或 LOS 角速率导引时，必须以 D5 的保守锁定结果为前置条件。接口原则：

1. 只有 `TerminalAssociation.decision_state == "locked"`，且 `assigned_global_track_id` 与 D3/D4 当前 AssignmentPlan 一致时，D7 才能使用该视觉目标作为 `visual PN / LOS` 输入。
2. D7 输入应包含 `assigned_global_track_id`、`resource_id`、`local_track_id`、图像中心、LOS 角速率、时间戳和置信度。
3. 若 D5 输出 `ambiguous/hold/reacquire/mismatch`，D7 只能进入保持、继续观测或等待上级计划更新的状态，不能自行选择另一个本地目标。
4. D7 严禁根据本地相机“更近”或“更清晰”的目标直接改绑 `global_track_id`。
5. 若二级侦察 cue 参与锁定，D7 应记录 `recon_cue_used=True`，用于 D6 评估 cue 依赖和误锁风险。

推荐 D5 -> D7 消息：

```text
VisualLockForGuidance
- resource_id
- assigned_global_track_id
- assignment_version
- local_track_id
- decision_state == locked
- center_px
- bearing_rate
- association_confidence
- measurement_timestamp
- camera_id / frame_id
- recon_cue_used
```

该消息不是处置授权，也不是新的分配计划，只是 D7 视觉导引模块的离线仿真输入合同。

---

## 11. AirSim Blocks 当前实现约束

AirSim Blocks 阶段一适配应保持离线/仿真边界：

- 视觉输入优先来自 `simGetDetections` 或离线检测器输出的检测框，再归一化为 `LocalVisualTrack`。
- 相机输入必须包含相机内参、相机位姿、图像时间戳和图像尺寸，转换为 D5 `CameraModel`。
- AirSim 默认不要求保存 PNG。若主程序选择保存图像，只能作为离线复盘和可视化，不应成为 D5 逻辑依赖。
- `actor/object_name` 可以作为仿真真值辅助评估 `association_correct`，用于 D6 指标计算和测试断言。
- 正式 D5 关联逻辑不能依赖 `actor/object_name` 作弊。运行时配准必须基于 `GlobalTrack` 投影、局部检测框、时间戳、相机姿态、协方差门控、身份声明和 cue。
- Blocks 中同一目标在不同相机下可能产生不同检测框和本地 ID，必须通过 `global_track_id` 投影门控和跨视角证据合并处理。
- 不调用 AirSim 控制 API，不输出控制量、拦截点、毁伤判断或自动处置动作。

建议阶段一 dry-run 输入：

```text
AirSim detection bbox
-> LocalVisualTrack(resource_id, camera_id, frame_id, center_px, bbox, timestamp)

AirSim camera metadata
-> CameraModel(K, R_cw, t_cw, image_size, measurement_cov)

D2 GlobalTrack
-> project into each camera frame

optional actor/object_name
-> evaluator-only truth label, never used in association decision
```

---

## 12. 交付物

1. 末端MOT、几何投影、友方认证综述。
2. ByteTrack、BoT-SORT、Deep SORT、OpenCV、tf2、OpenDroneID适用性评估。
3. `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 数据结构。
4. 匹配代价和保守决策逻辑。
5. 模拟相机投影与歧义场景测试用例。
6. 多视角 `CrossViewObservation/CrossViewAssociation` 接口建议。
7. D4 主动降级仲裁信号和 D7 视觉导引输入合同。
8. AirSim Blocks 检测框/相机元数据离线适配约束。

---

## 13. 参考资料

- ByteTrack: <https://github.com/FoundationVision/ByteTrack>
- BoT-SORT: <https://github.com/NirAharon/BoT-SORT>
- Deep SORT: <https://github.com/nwojke/deep_sort>
- OpenCV camera calibration: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>
- OpenCV `solvePnP`: <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>
- OpenDroneID Core C: <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing: <https://mavlink.io/en/guide/message_signing.html>
- ROS 2 DDS Security: <https://design.ros2.org/articles/ros2_dds_security.html>
- AprilTag: <https://github.com/AprilRobotics/apriltag>
