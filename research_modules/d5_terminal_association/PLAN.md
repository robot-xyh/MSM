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
- `ReconImageCue[]`：来自 D4 二级高空系留侦察节点的局部图像 cue；机动侦察云台 cue 可额外携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source`、`capability_class` 和 `coverage_mode`。

完全分布式跨视场输入：

- `resource_id/camera_id/frame_id`：给每个本地视觉轨迹建立唯一观测命名空间，避免不同无人机都使用 `track_1` 时发生冲突。
- `PeerCameraState`：记录每个 peer 相机在量测时刻的姿态协方差和可选位姿元数据。
- `measurement_timestamp/arrival_timestamp`：区分图像形成时刻和数据到达时刻，便于跨视场时间对齐。
- `covariance` 或 `covariance_px`：描述本地像素检测的不确定性，不把框中心当作确定值。
- `DistributedVisualObservation`：把上述字段和本地 `local_track_id`、bearing、bbox、类别、置信度封装为跨 peer 视觉观测。
- `VisualTrackletSummary`：按 `resource/camera:local_track_id` 汇总观测窗口，保留 bbox 面积、scale rate、bearing rate 和可选 `assigned_global_track_id` 状态。

输出：

- `TerminalAssociation`：包含中心分配 ID、本地候选 ID、置信度、歧义度、友方冲突状态、决策状态、候选代价和 cue 使用标记。
- `CrossPeerAssociationHypothesis`：完全分布式模式下的跨 peer metadata-only 视觉假设，不创建全局 ID。
- `DistributedTerminalAssociation`：供 D4 完全分布式决策消费的保守摘要；missing/stale global ID、重复锁定、友方冲突或局部 ID 冲突时不得输出 `locked`。

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

### 5.1 当前代码与测试状态

本节按当前 `src/d5_terminal_association/` 和 `tests/` 状态记录能力边界，避免把计划项写成已接入工程栈。

已实现并有测试或代码支撑的能力：

- `GlobalTrack -> CameraModel -> image projection`：`GlobalTrack` 是 frozen dataclass，`geometry.py` 和 `airsim_geometry.py` 支持投影、协方差传播、马氏门控和 AirSim camera info 到 D5 `CameraModel` 的离线转换。OpenCV 可用时使用 `cv2.projectPoints`；不可用时退回针孔模型。`TerminalAssociator.decide()` 和 `GeometricAssociationResult.to_log_records()` 已提供 projected pixel、bbox center、pixel error/reprojection error、Mahalanobis、gate pass、friend conflict、measurement age、selected pair、camera pose source、calibration health、drift warning 和 duplicate-risk advisory 字段，供 main/D6 后续写盘。
- `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`：核心 DTO 已落地。`TerminalAssociator.decide()` 只核对 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`，不会选择另一个全局 ID 作为新分配。
- 保守 `decision_state`：未授权、版本不一致、已验证友方重叠时 `hold`；候选接近、质量不足或身份声明不可靠时 `ambiguous`；无有效投影或无门内候选时 `reacquire`；只有唯一、稳定、版本一致且无友方冲突时才 `locked`。
- P0-B 主动重捕获与时序一致性：`TerminalAssociator` 已保留 per `resource_id + assigned_global_track_id` 历史，正常 gate 失败时用 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 主动寻找同一 assigned track；同一 MOT ID 可快速恢复，MOT ID 变化必须先通过 bbox 历史和 stable window，candidate margin、stale/OOSM、friend conflict、assignment/version mismatch 仍保持保守 `ambiguous/hold`。
- AirSim truth ID 隔离：`local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `YoloMotAdapter.process_frame()` 明确忽略 `object_id`、`actor_name`、`truth_id`、`true_global_track_id`、`global_track_id` 等真值/全局字段；若 AirSim `track_id`/`detection_id` 与 actor/truth 字段相同，sim detection adapter 会将其视为 truth alias 并回退到相机作用域本地检测 ID。truth label 只可在 `TerminalObservation.metadata` 或离线 evaluator 中用于 `terminal_lock_accuracy`、`locked_mismatch` 等评分。
- 跨视角 distributed visual association DTO 与 fusion：`DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`、`CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation` 和 `TerminalCrossViewFusion` 已实现 P0 metadata-only 融合。融合基于 measurement/arrival timestamp、bearing 或像素中心、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost；SciPy 可用时用 Hungarian，缺失时退回纯 Python 唯一匹配。
- 完全无中心下多相机 peer evidence 输出：缺失或 stale `assigned_global_track_id` 时输出 `hypothesis_only/hold`，重复锁定、友方冲突或 local/global ID 冲突时输出 `hold/ambiguous` 风险证据；不会创建新 `global_track_id`。
- D7 视觉 PNG 前置证据：`annotate_visual_png_handoff()` 已在 `TerminalAssociation.metadata` 上附加 bbox 面积稳定性、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和机动裕度建议。该建议只给 D7/main 做 gate 输入，不决定导引律。
- D4/D6 一致性摘要：`TerminalConsistencyTracker` 已按 `resource_id + assigned_global_track_id` 维护连续窗口；`assignment_version` 只随摘要审计输出，不作为窗口 key。因此同一资源持续执行同一全局目标时，D3 plan version 滚动更新不会清空连续 `locked/ambiguous/hold/reacquire` 状态。该摘要只作为 advisory evidence，不触发降级、不生成分配计划、不改写 `global_track_id`。
- 二级视觉覆盖与 detect 漏斗诊断：`summarize_secondary_visual_coverage_funnel()` 接受普通 replay frame dict/dataclass、`TerminalObservation` 和 `CrossViewAssociation`，输出单二级相机 full-view 率、二级网络联合 full-view 率、每相机/网络每帧可见目标数、覆盖比例均值/最小值，以及 detect -> local/recon cue -> terminal association -> cross-view association -> multi-support 计数。offline target label 只用于“看见目标”覆盖统计，不进入在线绑定。
- Detect-to-global-track registration：`register_local_visual_tracks_to_global_tracks()` 接受 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、协方差和 `LocalVisualTrack[]`，输出 registration candidates、registered observations、即时 cross-view support 和稳定 `stable_cross_view_associations`。truth/actor ID 和 tracker ID 不参与在线绑定。
- P0-B calibration health：`TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate、registration observation 和 registration result summary 已输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。P0-B 只做健康监测和告警，不做在线标定或外参重估。
- P1 二级 detect 注册校准：candidate/observation metadata 已补齐 `pixel_error_px`、`reprojection_error`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`camera_pose_source`、`calibration_health`、`drift_warning`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 只从 batch metadata 标注 `airsim_camera_pose`、`runtime_guidance_pose` 或 `look_at_fallback`，D5 不调用 AirSim。
- P1 自适应像素协方差：`adaptive_pixel_covariance_px()` 按 `sigma_px = clamp(max(25, 0.5*sqrt(bbox_area_px), 0.008*image_diag_px), 25, 90)` 生成二级相机 bbox 观测协方差；有 bbox 面积时用于几何门控，无面积时保留 `batch.covariance_px` fallback。
- P1 多帧稳定注册：默认 `RegistrationStabilityConfig(window_frames=3, required_gate_passes=2)`。单帧 gate pass 只形成 candidate；近 3 帧内同一 `resource/camera/local_track/global_track` 至少 2 次通过才标记 `stable_cross_view_support=True`，否则 reason 记为 `stability_window_failed`。该逻辑只增加既有 `global_track_id` 的视觉支持，不创建、不改写、不换绑 ID。
- 机动高空侦察云台覆盖证据：`ReconImageCue`、`TerminalObservationBus.cross_view_associations()` 和 `summarize_secondary_visual_coverage_funnel()` 已支持 `fixed_downlook_secondary` 与 `mobile_recon_gimbal` 分层。移动侦察节点可记录雷达/GlobalTrack cue 到云台 look-at 的 NED 位置、pointing error 和像素 track error；coverage funnel 会标出固定俯视未 full-view、移动云台补足网络联合覆盖的帧和新增目标集合。

2026-07-08 AirSim D4/D5 视觉校准历史状态：

- `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为历史 stress 证据：旧批次覆盖 3 个 seed、5v5 D4/D5 stress、200 m 高差、80 deg FOV、1920x1080，证明 D5 已能识别 `mobile_recon_gimbal`、`radar_global_track_cue`、`mobile_high_recon` 和云台指向 metadata。该批次的 bbox 3326-3334 px^2 对固定俯视约 1144-1145 px^2 只能说明目标看清能力改善，不能作为当前闭环结论；其覆盖与降级注册仍未闭合。
- 最新 registration calibration v2 输出为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，单 seed、3 个机动高空二级节点、200 m、110 deg、1920x1080。
- v2 结果：`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，三个 case 的 stable cross-view registration 为 51/55/53，cross-view association 为 4/4/5，`degrade_to_secondary` / `degrade_to_distributed` 的 not-registered case 仍为 35/35，full-view mean≈0.048，coverage mean≈0.771。
- 该单 seed 结果只保留为历史基线；其中降级 case not-registered 35/35 已被 2026-07-10 的 60-case sweep 改写，不能继续作为当前状态。

2026-07-08 P1 calibration sweep 集成状态：

- main runtime 已新增 P1 D4/D5 calibration sweep，用于扫描二级高度、FOV、二级节点数量和 standoff 组合，并在每个组合内运行多 seed stress episode。
- main runtime 的 D4/D5 stress 链路已可把二级 detect-to-global-track registration 输出写入同一个 `TerminalObservationBus`，用于统计 `registered_to_global_track`、`geometry_gate_rejected`、`secondary_detect_available_but_not_registered`、cross-view support 和 coverage funnel。
- D6 标准报告 bundle 已由 main runtime 自动生成，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。
- 因此 D5 当前 P1 重点不再是“是否有 registration/helper/report 接口”，而是通过真实 AirSim 多 seed sweep 校准二级网络覆盖、注册门限、YOLO/MOT 阈值、外参误差和 D4/D7 消费口径。

2026-07-10 真实 AirSim 60-case registration 状态：

- 证据目录为 `research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710`：5v5、10 seeds、50/200 m 二级高度、3 类 case，共 60 个 case。
- 60 个 case 均已形成有效 registration 记录；D6 的 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0。平均 `projection_valid_rate=1.0`、`stable_cross_view_registration_count=92.233`、`cross_view_association_count=4.417`。
- 该结果关闭“detect 无法注册到既有 `global_track_id`”这一接口缺口，但不等于二级节点已具备完整接管态势：网络同帧全目标覆盖率均值仅 `0.0231`，平均覆盖率 `0.7059`，稳定窗口失败仍是主要 reject reason。D5 不因注册成功而放宽唯一性、友方冲突、版本、时效或 D7 独立安全门控。

部分实现或仅作为 adapter/抽象的能力：

- 真实工程几何配准：当前消费已有 `CameraModel.K/R/t/dist_coeffs`，并能离线验证投影误差；没有完整标定采集、`calibrateCamera`、`solvePnP`/PnP RANSAC、bundle adjustment 或在线外参漂移估计链路。
- YOLOv8/ByteTrack/BoT-SORT：已提供 `YoloMotAdapter` 图像帧入口，默认权重为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许参数覆盖。`ultralytics` 可用时可请求 ByteTrack 或 BoT-SORT 原生 tracker；依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回确定性 IoU tracker，并在 `YoloMotFrameResult.metadata` 标明 stream key、实际 backend 和 per-stream 状态作用域。fallback tracker 与 native model/tracker 均按 `(resource_id, camera_id)` 隔离；输出仍只是带 camera namespace 的 `LocalVisualTrack`，tracker ID 不替代 `global_track_id`。
- Deep SORT/ReID：仍仅作为未来对照来源；当前没有 ReID embedding、长遮挡恢复或 IDSW/IDF1 统计实现。
- OpenCV：已用于投影与可选畸变参数消费；未实现标定工作流和真实图像角点/AprilTag 检测。
- ROS 2 `tf2/message_filters`：仅作为未来坐标/时间同步方案；D5 当前不启动 ROS graph，不订阅 topic，不消费 bag。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag：`IdentityChecker` 只解析仿真/fixture 风格身份字典并生成 `IdentityClaim`；未接入真实广播报文、密钥、证书、tag detector 或硬件链路。

未实现的真实工程能力及原因：

- 真实 AirSim/main 图像接线：D5 adapter 已能处理传入 frame 或 mock detector 输出，但 main runtime 仍需把连续 RGB/PNG frame、camera/resource/frame_id/timestamp 和参数覆盖接入 `YoloMotAdapter`，保持 stream key 稳定，并在 episode 边界调用 `reset_all_streams()`。
- 真实 MOT 标定：ByteTrack/BoT-SORT 原生质量依赖 `ultralytics` 和连续图像；IoU fallback 只保证 deterministic local ID 连续性，不声明遮挡恢复、ReID、IDSW/IDF1 工程质量。
- 真实标定链：缺少标定图像、标定板/AprilTag 角点、相机-机体系-世界系同步姿态、重投影误差验收阈值和 drift 告警流程。
- 真实身份认证链路：缺少 OpenDroneID/MAVLink/DDS 实际报文、密钥和白名单管理、时钟一致性、消息来源到平台身份的可信映射。
- 跨相机三维联合优化：缺少多相机同步 `CameraModel`、D2 航迹预测合同、三角化候选、重投影残差模型和 D4/D6 消费协议；当前只承诺 metadata-only peer evidence。

## 6. 二级侦察节点 cue 计划

本阶段假设存在若干高空系留侦察无人机作为二级区域节点。中心节点正常时，二级节点向覆盖小区内的拦截资源发送图像 cue；中心节点失效时，D4 可降级到二级节点协调；二级节点也失效时才进入完全无中心协商。

D5 将该输入表示为 `ReconImageCue`：

- `producer_node_id`：cue 来源二级节点。
- `image_frame_id`：cue 所属图像帧。
- `global_track_id`：可选的全局航迹提示。
- `center_px` 与 `bbox`：图像平面提示。
- `confidence`：cue 置信度。
- `scoped_resource_ids`：允许使用该 cue 的资源集合。
- `cue_position_ned` / `look_at_ned`：雷达或 GlobalTrack cue 与云台 look-at 的 NED 位置。
- `gimbal_pointing_metadata`：云台 yaw/pitch、目标簇/子簇、时间同步或控制状态等报告字段。
- `cue_pointing_error_m` / `cue_pointing_error_rad` / `gimbal_track_error_px`：cue 指向和图像跟踪误差。
- `cue_source`：例如 `radar_global_track_cue`。
- `capability_class` / `coverage_mode`：例如 `mobile_high_recon` 与 `mobile_recon_gimbal`；固定俯视二级相机使用 `fixed_downlook_secondary`。

关键约束：

- 若 cue 来自二级侦察节点自己的相机，必须先重投影到当前拦截资源相机平面。
- 未重投影的二级相机像素不能直接与 `LocalVisualTrack.center_px` 比较。
- cue 只能降低候选代价，不能绕过授权、版本校验、友方确认和 MOT 质量门槛。
- 空 `scoped_resource_ids` 当前可视为广播 cue；若实验要求严格小范围分发，应改为显式广播标记或视为空无效。
- 当前实现已加入 cue 新鲜度、目标相机帧校验、重投影标记校验和 `recon_cue_used` 决策标记；`recon_cue_used_count` 仍需进入 D6/main 统一日志。

机动侦察节点的图像服务末端跨视角配准的目标链路是：

```text
GlobalTrack/radar cue
-> mobile high-recon gimbal look-at(cue_position_ned, look_at_ned)
-> detector/MOT produces LocalVisualTrack[] on recon/interceptor cameras
-> per-camera geometry gate and Hungarian/JPDA-style candidate selection
-> TerminalAssociation for the existing assigned_global_track_id
-> TerminalObservationBus/CrossViewAssociation evidence
```

固定俯视二级相机覆盖不足时，D5 只在 evidence 中报告 `fixed_downlook_secondary` 的覆盖缺口和 `mobile_recon_gimbal` 对目标簇/子簇的补充覆盖；它仍不生成分配计划、不控制云台、不改写 `global_track_id`。

## 7. 多无人机重叠视场配准计划

典型场景：无人机 1 的相机看到目标 1/2/3，无人机 2 的相机看到目标 2/3/4。两个相机的 `local_track_id` 只在本机本相机内有效，例如 `UAV1:cam0:L2` 与 `UAV2:cam0:L2` 可能指向不同目标，也可能分别是同一个 `global_track_id` 的两个观测。D5 的跨视场目标是把这些本地观测配准到 D2 已存在的 `global_track_id`，而不是在本地创造新的全局 ID。

建议流程：

1. 当前 `TerminalObservationBus` 收集每架无人机的 `TerminalObservation` 摘要；完全分布式 metadata-only 路径使用 `DistributedVisualObservation` 和 `VisualTrackletSummary` 携带资源、相机、帧、时间戳、协方差和本地 MOT 命名空间信息。
2. 对 D2 的每个 `GlobalTrack` 按各自相机的 `measurement_timestamp` 做时间预测。
3. 将同一个 `GlobalTrack` 分别投影到 UAV1、UAV2 等相机平面，得到每个视场内的像素预测和协方差。
4. 在每个相机内先做像素马氏门控，形成局部候选代价。
5. 对重叠视场中的共享目标 2/3，比较多相机候选是否同时支持同一 `global_track_id`。
6. 对时间差过大、相机姿态不可信、协方差过大或候选代价接近的情况输出 `ambiguous/unknown`，不强行跨视场绑定。
7. 二级侦察 cue 先重投影到每个目标相机平面，再按 `scoped_resource_ids` 对相应资源降低候选代价。

当前已实现接口：

- `TerminalObservation`：单条跨节点末端摘要，可携带 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue`。
- `TerminalObservationBus`：被动收集多资源/多链路摘要，按既有 `global_track_id` 生成跨视角汇总。
- `CrossViewAssociation`：表达一个 `global_track_id` 的 `supporting_resource_ids`、命名空间化 `local_track_ids`、`ambiguity_score`、`duplicate_terminal_lock_risk`、来源节点和链路类型。
- `DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`：完全分布式 metadata-only 跨 peer 输入 DTO。
- `TerminalCrossViewFusion`：基于时间窗口、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost，并使用 Hungarian 或纯 Python fallback 做唯一匹配。
- `CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation`：向 D4 输出支持假设、`hypothesis_only/hold/ambiguous/locked` 状态、重复终端锁定风险和命名空间化 local track IDs。

该最小实现覆盖 UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的摘要层逻辑：目标 2/3 得到多视角支持，目标 1/4 保持单视角支持；重复锁定只上报风险，不改分配。

当前 `TerminalCrossViewFusion` 是 P0 metadata-only 融合器，不做三维重投影、三角化、bundle adjustment、真实图像 ReID 或 D4 分配决策。后续完整几何融合可新增 `CrossViewTrackEvidence`，把相机几何重投影和 D2 航迹预测纳入同一摘要，但仍不改变 D5 不改写 `global_track_id` 的边界。

## 8. 实施流程

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
11. 当前可由 `TerminalObservationBus` 汇总多个资源的 `TerminalAssociation` 摘要，向 D3/D4/D6 上报 `CrossViewAssociation` 支持关系和重复锁定风险。
12. 完全分布式模式可由 `TerminalCrossViewFusion` 对多个资源的 `DistributedVisualObservation` 或 `VisualTrackletSummary` 做 metadata-only 跨 peer 融合，并只向 D4/D6 上报 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。

## 9. 代码模块划分

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
│   ├── airsim_geometry.py
│   ├── associator.py
│   ├── consistency.py
│   ├── geometry.py
│   ├── identity.py
│   ├── observation_bus.py
│   ├── terminal_cross_view_fusion.py
│   ├── visual_handoff.py
│   └── models.py
└── tests/
    ├── test_airsim_cv_2v2_secondary_plan.py
    ├── test_airsim_cv_5v5_evidence.py
    ├── test_distributed_cross_view_fusion.py
    ├── test_geometric_registration_validation.py
    ├── test_terminal_association.py
    ├── test_airsim_dry_run_interface.py
    ├── test_terminal_consistency.py
    ├── test_terminal_observation_bus.py
    └── test_visual_handoff.py
```

主要职责：

- `models.py`：定义 `GlobalTrack`、`LocalVisualTrack`、`Assignment`、`IdentityClaim`、`ReconImageCue` 和 `TerminalAssociation`。
- `airsim_cv_adapter.py`：转换 `simGetDetections` 风格检测框，生成 N-v-N ComputerVision 压测指标、三类降级证据摘要和 multi-seed calibration readiness 字段覆盖审计；5v5 只是 stress baseline。
- `yolo_mot_adapter.py`：运行或适配 YOLOv8 图像帧检测，优先请求 ByteTrack/BoT-SORT，缺依赖时退回确定性 IoU tracker，输出 `LocalVisualTrack` 和 backend metadata。
- `airsim_geometry.py`：提供 AirSim 相机内外参到 D5 投影模型的离线转换和几何匹配验证辅助，不读取 AirSim truth 做在线关联。
- `observation_bus.py`：定义最小跨节点 `TerminalObservationBus` 汇总逻辑，输出 `CrossViewAssociation` 风险与支撑摘要。
- `terminal_cross_view_fusion.py`：定义完全分布式 metadata-only 跨 peer 假设生成，输出 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。
- `consistency.py`：把连续帧 `TerminalAssociation`、跨视角摘要和冲突状态压缩为 `TerminalConsistencySummary`。
- `visual_handoff.py`：给 D7/main 输出视觉 PNG handoff advisory metadata，检查 locked、bbox 稳定、分配一致和重复锁定风险。
- `geometry.py`：实现投影、协方差传播和马氏距离。
- `identity.py`：解析仿真身份声明并判断友方冲突。
- `associator.py`：实现投影、代价矩阵和保守决策。
- `simulations/`：生成离线合成场景和实验结果。
- `docs/`：保存算法说明、实验报告、图表和 AirSim 离线计划。

## 10. 关键接口

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
- `TerminalObservationBus.publish_terminal_association(...)`
- `TerminalObservationBus.publish_local_track(...)`
- `TerminalObservationBus.cross_view_associations()`
- `TerminalCrossViewFusion.summarize_observations(...)`
- `TerminalCrossViewFusion.build_hypotheses(...)`
- `TerminalCrossViewFusion.associate(...)`
- `local_visual_tracks_from_sim_detections(...)`
- `YoloMotAdapter.process_frame(frame, resource_id=..., camera_id=..., frame_id=..., timestamp=...)`
- `YoloMotAdapter.reset_stream(resource_id, camera_id)`
- `YoloMotAdapter.reset_all_streams()`
- `publish_sim_detections_as_local_observations(...)`
- `compute_terminal_stress_metrics(...)`
- `summarize_degradation_case(...)`
- `summarize_multiseed_calibration_readiness(...)`
- `summarize_secondary_visual_coverage_funnel(...)`

最小跨视角摘要接口：

```python
bus.publish_terminal_association(
    resource_id="UAV1",
    source_node_id="UAV1",
    link_type="interceptor_peer",
    timestamp=current_time,
    terminal_association=decision,
    local_track=local_track,
    camera_id="front_rgb",
    frame_id="UAV1/front_rgb",
)

cross_view = bus.cross_view_associations()
```

完全分布式 metadata-only 跨视场接口：

```python
distributed = terminal_cross_view_fusion.associate(
    observations=distributed_visual_observations,
    tracklet_summaries=peer_tracklet_summaries,
    camera_states=peer_camera_states,
    current_assigned_global_track_ids=current_ids,
    stale_assigned_global_track_ids=stale_ids,
)
```

该接口只输出 `DistributedTerminalAssociation`，每条摘要携带 `CrossPeerAssociationHypothesis`；不产生新分配计划，不创建或换绑 `global_track_id`。

## 11. 仿真场景设计

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
- UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的重叠视场 metadata-only 配准。
- N-v-N ComputerVision 压测：数量由 main runtime 的 `--drone-count N` 统一控制；5v5 baseline 使用目标距主镜头约 50m、目标间距 20m、镜头间距 20m，每个主镜头视场内至少两个目标。
- 二级系留侦察镜头比目标高约 200m，输出已重投影到拦截机相机平面的 `ReconImageCue`。
- 相同 `local_track_id` 在不同无人机中重复出现的命名空间冲突测试。
- 相机姿态误差、时间戳错位和高协方差观测导致的跨视场 `ambiguous`。
- `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 D5 证据 case。

## 12. 指标

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
- `secondary_single_camera_full_view_frame_rate`
- `secondary_network_joint_full_view_frame_rate`
- `secondary_camera_frame_visible_target_counts`
- `secondary_network_frame_joint_visible_target_counts`
- `secondary_single_camera_coverage_ratio_mean`
- `secondary_single_camera_coverage_ratio_min`
- `secondary_network_joint_coverage_ratio_mean`
- `secondary_network_joint_coverage_ratio_min`
- `detect_count`
- `local_or_recon_cue_count`
- `terminal_association_count`
- `cross_view_association_count`
- `multi_support_count`
- `rejection_reason_counts`
- `coverage_mode_counts`
- `mobile_recon_gimbal_improved_joint_coverage_frame_count`
- `mobile_recon_gimbal_added_target_ids_by_frame`
- `cue_pointing_error_m_by_camera_frame`
- `cue_pointing_error_rad_by_camera_frame`
- `gimbal_track_error_px_by_camera_frame`

其中 `global_track_id_rewrite_count` 应始终为 0。二级覆盖指标分三层解释：`visible_target_ids`/覆盖比例只表示二级相机“看见目标”；`secondary_network_joint_full_view_frame_rate` 表示同一帧多二级相机并集覆盖全部 active targets；`cross_view_association_count` 和 `multi_support_count` 才表示检测/本地 cue 已经转成既有 `global_track_id` 支持。`mobile_recon_gimbal_improved_joint_coverage_frame_count` 只说明机动云台 evidence 补足固定俯视覆盖，不代表 D5 获得分配或控制权限。

## 13. 预期交付物

- 根目录 `PLAN.md` 和 `README.md`。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法原理与实施方案。
- `docs/EXPERIMENT_REPORT.md`：中文实验报告和图表引用。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放与接口计划。
- Python 源码、单元测试和离线仿真脚本。

## 14. 局限与后续工作

- `ReconImageCue` 的 scope、age、frame 和重投影标记已有代码校验，但真实二级侦察图像反投影/重投影链路尚未接入；当前 cue 仍主要来自 fixture 或预处理结果。
- 已实现 `TerminalObservationBus`、`CrossViewAssociation`、`TerminalCrossViewFusion` 和 N-v-N ComputerVision dry-run evidence helper。
- 尚未完整实现跨无人机多相机三维几何融合；`CrossViewTrackEvidence` 仍是后续接口建议。
- 当前身份声明为离线仿真抽象，不连接真实 OpenDroneID、MAVLink signing、DDS Security 或 AprilTag detector。
- 本地 MOT 质量对小目标场景影响大；当前 D5 已提供 YOLOv8 frame adapter、ByteTrack/BoT-SORT 原生 tracker 请求、IoU fallback 和 per-stream MOT 状态隔离，但真实 AirSim 图像流接线、GPU/CPU部署和多 seed 标定仍未闭合。native 模式为避免 `persist=True` tracker 串流而按 stream 创建独立 model/tracker，资源占用随活跃 stream 数增长。
- D5 输出只用于 D4/D6/D7 的证据、评估和上游复盘，不应被解释为自动处置命令。

P1 补齐状态：

- 已完成 D5 侧 AirSim CV replay 可写盘字段：projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair、`duplicate_terminal_lock_risk` advisory、`recon_cue_used_count` 和 visual PNG advisory metadata。main/D6 若需要实际 JSONL/CSV sink，应在 runtime/D6 owned path 接入这些 D5 输出字段。
- 已完成 D5 侧 multi-seed calibration readiness helper：`summarize_multiseed_calibration_readiness()` 对 `TerminalObservation` 和 `CrossViewAssociation` 做被动字段覆盖审计，输出每个 seed 的 `missing_required_fields`、`missing_recommended_fields`、source/backend counts、truth-label count、handoff/bbox-stability count 和 duplicate/friend conflict count。truth label 只作为离线 metadata 计数，不参与在线关联。
- 已完成 D5 侧二级覆盖/漏斗诊断 helper：`summarize_secondary_visual_coverage_funnel()` 输出 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点计数，帮助 main/D4/D6 区分“二级相机看见了目标”“二级网络并集覆盖了目标”和“D5 已形成全局 ID 支持”。
- 已完成 D5 侧 AirSim settings 驱动 detect-to-global-track registration helper：`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 匹配输出 `DetectToGlobalTrackCandidate.outcome`、`TerminalObservation` 和 `CrossViewAssociation`；SciPy 不可用时退回确定性唯一匹配，同时保留 gated candidates 供 JPDA-compatible 下游使用。输出 records 携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、projection reason、timestamp、measurement age、covariance/projection covariance summary 和 reasons，覆盖 `no_global_binding`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`network_union_incomplete`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。二级 detect 只能增加既有 `global_track_id` 支持，不能创建、重绑或使用 AirSim truth/actor ID。
- 已完成 main runtime P1 calibration sweep 和 D6 bundle 对 D5 evidence 的接线口径：D5 不启动 AirSim、不生成报告，但其 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary funnel 和 mobile gimbal metadata 已是 sweep/D6 统计的输入合同。
- 已完成 D5 侧机动侦察云台 cue evidence：`ReconImageCue` 与 coverage/cross-view summary 可携带 NED cue/look-at、云台 metadata、pointing/track error、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。历史 mobile recon stress 只保留为旧批次基线；2026-07-10 的 60-case sweep 已达到 `not_registered_count=0` 和平均 cross-view association `4.417`，当前主瓶颈转为同帧全目标覆盖、稳定支持和 D4 逐决策消费。
- 已完成 `TerminalConsistencySummary` 连续窗口修正：`TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口，`assignment_version` 只做摘要审计字段。同一资源持续执行同一全局目标时，滚动 plan version 不会清空连续 `locked/ambiguous/hold/reacquire` 状态。
- 已完成 D4 evidence 输出：`CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 均为 D4/D6 advisory evidence；D5 不触发降级、不生成 `AssignmentPlan`、不选择主备资源。
- 已完成 D7 visual PNG 前置证据：`annotate_visual_png_handoff()` 输出 handoff/prelock 建议、gate pass、blockers、measurement age、LOS availability、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend conflict、duplicate risk、unstable bbox、stale measurement age 或 missing LOS 都会阻断建议。
- 已完成 AirSim truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter 和 YOLOv8 frame adapter：AirSim `object_id`、`actor_name`、`truth_id`、`true_global_track_id` 或 `global_track_id` 输入字段不会进入在线关联；在线 category 只接受 `category/label/class_name` 或 detector `class_id + names` 映射，通用 `name/actor_name/object_name` 不影响 category、cost、binding 或 online metadata。本轮二级节点也先按 `simGetDetections` bbox/metadata 转 `LocalVisualTrack`，不启用 YOLO，且不会把 actor/truth alias 当作本地在线身份。truth 只允许进入离线 evaluator/metadata 统计。YOLO/ByteTrack row 或 frame adapter 输出只转为命名空间化 `LocalVisualTrack`，metadata 记录 confidence、class id、bbox scale、tracker backend 与 CPU/GPU budget，tracker ID 不替代 `global_track_id`。
- 2026-07-10 已闭合 active reacquire 友方声明复检 P0：候选在任何 `locked` 输出前复用 `IdentityChecker`，verified/stale/unverified/spoof-suspected 友方声明重叠均输出 `hold`，顶层与 search-window/candidate metadata 保留冲突状态和 reason；同一/新 MOT ID 回归均保持 `global_track_id` 不变。
- 2026-07-10 已闭合多相机 MOT 状态隔离 P1：fallback tracker 与 Ultralytics native model/tracker 按 `(resource_id, camera_id)` 持久化，提供单 stream 和全 episode reset API；交错相机、reset、native 成功及 native-to-fallback 回归均不串 ID/history。
- 2026-07-10 2v2 smoke 复核：2/2 资源对完成拦截，pair summary 的 D5 状态均为 `locked`，但 D7/main 因 `bbox_near_image_edge` 拒绝视觉接管 9 次、覆盖 2 个资源对，仅 2 个控制记录允许切换。该现象不要求放宽 D5/D7 门控；P1 需补充边缘裕量、连续边缘帧、相机指向误差和 handoff 抖动的多 seed 标定。
- 同一 smoke 的终端记录曾包含 `Interceptor*:0:MSM_TargetActor_*` 本地 ID。D5 sim-detection adapter 已过滤 actor/truth alias；main hotfix 已把 builtin detect 改为仅基于 bbox 的匿名 camera-local tracker，清理 intercept 注入和 D4/D5 fallback 的 actor-name local ID，并把 actor 名限制为 offline truth metadata。真实 AirSim 证据 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710` 中三类 case 均 connected、各 5 帧，local/detection ID 无 actor 名，匿名 ID history 达 5，offline truth 标记正确且 cross-view association 均为 4。端到端 truth 隔离 P0 已闭合；D5 不越权修改 runtime，也不对任意既有本地 tracker ID 做字符串重写。

P0 状态：无 P0 blocker。active reacquire 友方声明复检、detection category/truth 隔离和端到端 AirSim actor-name local ID 隔离均已闭合。安全合同仍需持续回归：D5 不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

剩余 P1：

- 二级节点几何/覆盖策略：60-case 当前网络同帧全目标覆盖率均值为 `0.0231`、平均覆盖率为 `0.7059`，`not_all_targets_visible` / `network_union_incomplete` 仍主导；继续调整高空侦察节点站位、look-at 扫描/子簇策略和 full-view 判据，目标是提升完整态势覆盖，而不是再证明投影或基础 registration 有效。
- 真实 YOLOv8 + ByteTrack/BoT-SORT 多 seed：消费连续 RGB frame，分别标定目标尺度、FOV、confidence、bbox scale、tracker backend、CPU/GPU 时延和失败回退；用 IDSW/IDF1、遮挡恢复时间、`locked_mismatch`、false handoff 与 `terminal_id_switch_count` 判断 ByteTrack/BoT-SORT 的适用边界。
- 外参漂移与时间同步：对 per-camera `K/R/t/dist_coeffs` 注入可控姿态/位置漂移，对 measurement/arrival timestamp 注入时延和抖动，统计重投影误差、马氏门控拒绝率、错误锁定率和恢复时间；必要时再引入离线 `solvePnP`/PnP RANSAC，不在 D5 内伪造同步后的真值位姿。
- D4 逐决策 evidence：在 D5 合同中明确每次 D4 决策所需的 stable/not-registered count、evidence timestamp/age、camera/resource scope、threshold version 和冲突原因；main/D4 负责把这些字段接入同一决策 tick，不得用 episode 聚合值替代实时证据，也不得让 D5 直接触发降级。
- 遮挡/交叉专项：构造同相机交叉、跨相机部分重叠、短时全遮挡和 local MOT ID 变化场景，验证恢复只能绑定当前 D3/D4 分配的既有 `global_track_id`；候选不唯一、友方重叠或稳定窗口不足时保持 `ambiguous/hold/reacquire`。
- 友方身份真实 replay：至少接入一个 Remote ID/OpenDroneID、MAVLink signing、DDS Security 或 AprilTag replay adapter，统一为 `IdentityClaim`，验证 verified/stale/unverified/spoof-suspected 的保守决策和时间有效性；未知不等于敌方，任何身份线索不得绕过几何和 assignment gate。
- 视觉接管边缘裕量校准：基于真实控制日志统计 bbox 到四条图像边界的归一化最小距离、连续 `bbox_near_image_edge` 帧、相机指向误差和 D5 handoff 到 D7 terminal gate 的拒绝原因；目标是减少重复 handoff 请求而不降低 D7 独立 camera/LOS/maneuver 安全门控。
- 标定/`solvePnP`/外参增强：为 AirSim/replay 建立离线标定验证、PnP RANSAC、重投影误差阈值、外参 drift 告警和多相机 frame/timestamp 对齐检查；真实硬件级标定链仍可继续归入 P2。

剩余 P2：

- 在真实图像链路后评估 BoT-SORT、Deep SORT 和 ReID 是否适合小型无人机图像；用 IDF1/IDSW、遮挡恢复和算力预算决定是否只保留 ByteTrack + 几何门控基线。
- 在 P1 replay adapter 之后接入真实在线身份源、密钥/证书和白名单运维；未知、过期、伪造或校验失败只能降低可信度，不能升级为敌方或锁定目标。
- ROS 2 `tf2/message_filters` 只在项目进入 ROS 2 runtime 或 bag replay 后实施，目标是维护带戳 frame tree 和相机/航迹时间同步，不改变 D5 不改写 `global_track_id` 的边界。
