# AirSim 离线集成计划

## 范围

本计划只描述 AirSim 数据采集、离线回放和评估接入。不调用实机飞控、硬件驱动、武器/毁伤模型、自动处置接口，也不绕过人工授权。D5 模块只输出 `TerminalAssociation`，不改写中心维护的 `global_track_id`。

## 2026-07-13 最新实测基线

- M5N2 paired AirSim 已形成 `120` 条 active-primary 证据、`120` 条 visible 证据和 `74` 条 D5 关联/锁定证据；最佳 coalition completion 为 `5/10`。当前 P1 是第二 primary 的持续检测、稳定 bbox 和连续 measured lock，主要失败原因为 `d5_not_locked` 与 `terminal_detection_acquisition_timeout`。
- 原生 MOT 已完成 `18`-case 正式 screening：`1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m native active rate/continuity 均为 `1.0`、IDSW 为 `0`、P95 约 `7.4/16.2 ms`；precision/recall 仅约 `0.26-0.33`，30/50 m 无检测。
- screening 准入候选为 `0`，two-camera confirmation 为 `0`。默认在线检测保持 AirSim `simGetDetections`，不得把 20 m tracker 连续性写成原生 MOT 已晋级。
- 2026-07-13 最新 D5 全量回归为 `232 passed`。开放 P1 为第二 primary 稳定锁定、bbox 口径/尺度/时间对齐、远距召回，以及候选通过 screening 后的多 seed confirmation。

## 数据来源

从 AirSim 场景离线采集：

- RGB 相机帧和时间戳。
- 相机内参 `K`、外参 `R, t`，或可转换为 `P_c = R P_w + t` 的位姿。
- 仿真对象世界坐标、速度、类别和中心系统生成的 `global_track_id`。
- 合作/友方对象的模拟 OpenDroneID 或任务标签消息。
- 可选：分割图、深度图、标注框，用于生成或校验本地检测输入。

## 坐标与投影

AirSim 采集层负责把仿真世界位姿转换为 D5 的 `CameraModel`：

```text
P_c = R_cw P_w + t_cw
p = K [R_cw | t_cw] P_w
```

如果使用 ROS 2/tf2，只在离线回放时提供坐标变换；D5 不订阅或发布控制指令。

## 本地视觉输入

两种离线输入模式：

- 标注模式：由 AirSim 真值投影和噪声模型生成 `LocalVisualTrack`，用于算法单元评估。
- 检测模式：将 AirSim RGB 帧送入本地检测器或 MOT，例如 ByteTrack、BoT-SORT、Deep SORT，再归一化为 `LocalVisualTrack`。

MOT 的 `local_track_id` 只作为本地观测 ID，不得替代或重写 `global_track_id`。

### 当前实际实现状态

当前 D5 已实现的是 AirSim ComputerVision bbox dry-run adapter、相机几何离线验证辅助、detect-to-global-track registration helper 和可选 YOLO/MOT frame adapter：

- 已接入：`simGetDetections` 风格 `box2D/bbox_xyxy/xyxy` schema 转 `LocalVisualTrack`，`TerminalObservationBus` 汇总多相机观测，`TerminalCrossViewFusion` 输出 metadata-only peer evidence。
- 已接入：`register_local_visual_tracks_to_global_tracks()` 按 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]` 做像素马氏门控 + Hungarian/确定性唯一匹配，输出 registration candidate、`TerminalObservation`、即时 `CrossViewAssociation` 和稳定 `stable_cross_view_associations`。candidate/observation metadata 携带 `pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`camera_pose_source`、`bbox_area_px`、`offline_truth_global_id` 和 3 帧 2 次通过的稳定窗口字段；truth/actor ID 只作为离线 metadata。
- 已接入：`YoloMotAdapter.process_frame()` 可消费图像帧或 mock detector 输出；默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt`，可请求 ultralytics ByteTrack/BoT-SORT 原生 tracker，依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回确定性 IoU tracker，并在 metadata 中标明实际 detector/tracker backend。main/AirSim 连续 RGB episode 接线已用于 18-case 正式 screening。
- 部分接入：OpenCV 用于 `projectPoints` 投影和可选畸变参数消费；OpenDroneID/MAVLink/DDS/AprilTag 仅可通过仿真字典转为 `IdentityClaim`。
- 未闭合：bbox 定义/尺度/时间对齐、30/50 m 远距召回、候选多 seed confirmation、GPU/CPU 长期预算、Deep SORT/ReID、OpenCV calibration/`solvePnP` 真实标定链、ROS 2 `tf2/message_filters`、真实 OpenDroneID/MAVLink/DDS/AprilTag 身份认证链路。

因此，若 main/runtime 提供真实 frame、detector 或 tracker 输出，D5 只消费归一化后的 bbox、类别、置信度、时间戳和本地 track ID；D5 不管理 AirSim 图像采集、GPU 部署或 episode 调度，也不把 tracker ID 提升为全局身份。

### ComputerVision N-v-N 多镜头压力输入

本轮 D4/D5 专项测试采用 AirSim ComputerVision Vehicle 场景的离线检测合同，不要求 D5 导入 AirSim 或调用仿真 API。数量由 main runtime 的 `--drone-count N` 统一控制；D5 按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表和 bus observation 长度运行。5v5 只是 stress baseline，推荐几何假设：

- 5 个 `Interceptor_Cam_*` 主镜头。
- 5 个目标，目标距拦截镜头约 50m。
- 目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标。
- 一个或多个可机动高空侦察节点，可保持约 200m 高差，携带高分辨率、高性能光电云台，并按 GlobalTrack/radar cue 指向目标簇。

每个主镜头的 `simGetDetections` 结果应被转换为：

```text
DetectionInfo / fixture bbox
-> LocalVisualTrack(local_track_id, center_px, bbox, category, quality, timestamp)
-> TerminalObservationBus.publish_local_track(...)
```

在线转换不得使用 AirSim detection 的 `object_id`、`actor_name` 或 truth ID 来生成、过滤或改写 `LocalVisualTrack`/`TerminalAssociation`。这些真值字段只能作为离线评估标签写入单独 metadata 或 evaluation map。

若已经完成单机配准，则继续发布：

```text
TerminalAssociation
-> TerminalObservationBus.publish_terminal_association(...)
-> CrossViewAssociation summary
```

D5 只生成 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue` 和 `TerminalObservationBus/cross_view summaries`。不得生成 `AssignmentPlan`，不得改写 `global_track_id`。

## 身份声明输入

将合作对象元数据转换为模拟身份消息：

```json
{
  "protocol": "OpenDroneID",
  "platform_id": "FRIEND_SIM_1",
  "local_track_id": "L_friend",
  "timestamp": 12.0,
  "is_friend": true,
  "signature_valid": true
}
```

`IdentityChecker` 只把已验证且新鲜的声明作为正向友方确认。过期、未签名、签名失败或几何不一致的声明不会升级为 `locked`。

## 二级侦察节点图像 cue

AirSim 场景中可加入可机动高空侦察无人机作为二级节点。节点携带高性能光电云台，按 GlobalTrack/radar cue 指向目标簇；二级节点正常时，将其覆盖小区内的离线图像 cue 转换为 `ReconImageCue`：

```json
{
  "cue_id": "sec_cue_001",
  "producer_node_id": "secondary_recon_1",
  "image_frame_id": "secondary_recon_1/camera",
  "timestamp": 12.0,
  "global_track_id": "G_ASSIGNED",
  "center_px": [320.0, 240.0],
  "confidence": 0.8,
  "scoped_resource_ids": ["R1", "R2"]
}
```

`ReconImageCue` 只在 `scoped_resource_ids` 指定的小范围资源中降低视觉关联代价。它不能替代中心授权、版本匹配、友方认证和本地 MOT 质量门槛，也不能让局部节点改写 `global_track_id`。

坐标语义要求：

- 若 `center_px` 来自二级侦察节点相机，回放预处理层必须先根据目标三维位置、二级相机位姿和当前拦截资源相机位姿，将 cue 重投影到当前拦截资源相机平面。
- `image_frame_id` 应标识 cue 当前所属的目标相机帧；建议在 `metadata` 中保留 `source_image_frame_id`。
- 未重投影的二级相机像素不得直接与 `LocalVisualTrack.center_px` 比较。
- 后续离线实验应记录 `recon_cue_used_count`，并对 stale cue、跨资源 cue、空 `scoped_resource_ids` 语义进行回放测试。

## 评估循环

每帧离线回放：

1. 读取中心分配 `Assignment.assigned_global_track_id`。
2. 读取或预测中心全局轨迹 `GlobalTrack`。
3. 构造当前 `CameraModel`。
4. 从标注或 MOT 结果构造 `LocalVisualTrack`。
5. 从模拟 OpenDroneID/友方标签构造 `IdentityClaim`。
6. 可选读取二级侦察节点 `ReconImageCue`。
7. 调用 `TerminalAssociator.decide(...)`。
8. 记录 `locked/ambiguous/hold/reacquire`、候选成本、cue 使用情况、正确性和 ID 不变式。

ComputerVision N-v-N 专项回放中，额外执行：

1. 对 runtime 当前提供的所有 camera/resource 分别调用检测转换 helper，统计每个镜头检测数量。
2. 对每个资源发布本地观测和终端关联结果。
3. 对二级可机动高空侦察节点的光电云台发布已重投影的 `ReconImageCue`；云台按 GlobalTrack/radar cue 指向目标簇，过期或不可用 cue 必须显式标记。
4. 调用 `register_local_visual_tracks_to_global_tracks()` 把本地 detect 注册为既有 `global_track_id` 的候选/稳定跨视角支持；单帧 gate pass 只作为 candidate，默认 3 帧内 2 次通过才进入稳定支持。
5. 调用 `TerminalObservationBus.cross_view_associations()` 或 registration result 中的 `cross_view_associations` / `stable_cross_view_associations` 汇总重叠视场支持。
6. 调用 `compute_terminal_stress_metrics()`、`summarize_degradation_case()`、`summarize_multiseed_calibration_readiness()` 和 `summarize_secondary_visual_coverage_funnel()` 生成 D5 证据、字段覆盖审计和二级 detect 漏斗。

三类证据输出语义：

- `no_degradation`：终端 `locked` 与 D3 分配及评估真值一致，无持续歧义或冲突。
- `degrade_to_secondary`：终端局部证据与中心分配持续不一致或歧义，且二级侦察 cue 新鲜可用。
- `degrade_to_distributed`：终端局部证据与中心分配持续不一致或歧义，但二级 cue 不可用、过期或被标记失效，只能给 D4 提供分散降级证据。

## 指标

- 终端关联正确率。
- locked precision。
- 错误 locked 数。
- `ambiguous` 次数。
- `hold` 次数，尤其是友方重叠触发次数。
- `reacquire` 次数和遮挡恢复耗时。
- 输入 `global_track_id` 变更次数，期望恒为 0。
- `per_camera_detection_count`。
- `multi_target_fov_rate`。
- `cross_view_overlap_count`。
- `duplicate_terminal_lock_risk`。
- `terminal_lock_accuracy`。
- `ambiguous_fov_event_count`。
- `registered_to_global_track` / `geometry_gate_rejected` / `stability_window_failed` / `network_union_incomplete` reason counts。
- `camera_pose_source`、`bbox_area_px`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass` 和 `projection_valid` 字段覆盖率。
- `secondary_single_camera_full_view_frame_rate` 与 `secondary_network_joint_full_view_frame_rate`。
- `detector_backend` / `tracker_backend` 分布，以及 YOLO/MOT 多 seed 阈值标定结果。
- `native_active_frame_rate`、fallback frame、local continuity、terminal local IDSW、P95 latency、offline precision/recall、admission candidate 和 confirmation case 数。

## 防护约束

- D5 不调用 AirSim 控制 API。
- D5 不输出控制量、拦截点、打击参数或毁伤判断。
- D5 不改变中心全局轨迹表。
- 友方重叠默认 `hold`。
- 未知身份默认保持未知，不自动推断为对抗目标。
- 所有自动输出仅供离线评估和人工审查。

## 里程碑

1. 已完成 AirSim `simGetDetections` bbox dry-run、geometry log、truth ID 在线隔离、YOLO/MOT frame adapter、连续 RGB episode 接线、detect-to-global-track registration、multi-seed readiness helper 和 secondary coverage funnel。
2. 已完成 P1 D4/D5 calibration sweep、M5N2 120/120/74 漏斗、原生 MOT 18-case screening 与 D6 bundle 的 D5 evidence 输入口径；0 个 MOT 候选进入 confirmation，默认 detect 不变。
3. 剩余 P1：提升第二 primary 稳定锁定；校正 bbox 口径/尺度/时间对齐；恢复 30/50 m 召回；候选通过 screening 后运行至少 10 seeds confirmation。二级覆盖、真实 camera pose/registration 门限和 D4/D7 逐决策消费继续按既有安全口径校准。
4. 剩余 P1/P2：建立 AirSim/replay 标定样本、`solvePnP`/PnP RANSAC、重投影误差阈值和外参 drift 告警。
5. 剩余 P2：评估 BoT-SORT/Deep SORT/ReID 质量，接入真实身份来源为 `IdentityClaim` adapter，并在需要时接入 ROS 2 `tf2/message_filters`。
