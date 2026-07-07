# AirSim 离线集成计划

## 范围

本计划只描述 AirSim 数据采集、离线回放和评估接入。不调用实机飞控、硬件驱动、武器/毁伤模型、自动处置接口，也不绕过人工授权。D5 模块只输出 `TerminalAssociation`，不改写中心维护的 `global_track_id`。

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

当前 D5 已实现的是 AirSim ComputerVision bbox dry-run adapter 和相机几何离线验证辅助：

- 已接入：`simGetDetections` 风格 `box2D/bbox_xyxy/xyxy` schema 转 `LocalVisualTrack`，`TerminalObservationBus` 汇总多相机观测，`TerminalCrossViewFusion` 输出 metadata-only peer evidence。
- 部分接入：OpenCV 用于 `projectPoints` 投影和可选畸变参数消费；YOLO 仅兼容输出 schema；OpenDroneID/MAVLink/DDS/AprilTag 仅可通过仿真字典转为 `IdentityClaim`。
- 未接入：真实 YOLO 推理、ByteTrack/BoT-SORT/Deep SORT tracker、OpenCV calibration/`solvePnP` 标定链、ROS 2 `tf2/message_filters`、真实 OpenDroneID/MAVLink/DDS/AprilTag 身份认证链路。

因此，若 main/runtime 提供真实 detector 或 tracker 输出，D5 只消费归一化后的 bbox、类别、置信度、时间戳和本地 track ID；D5 不负责运行 detector/tracker，也不把 tracker ID 提升为全局身份。

### ComputerVision N-v-N 多镜头压力输入

本轮 D4/D5 专项测试采用 AirSim ComputerVision Vehicle 场景的离线检测合同，不要求 D5 导入 AirSim 或调用仿真 API。数量由 main runtime 的 `--drone-count N` 统一控制；D5 按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表和 bus observation 长度运行。5v5 只是 stress baseline，推荐几何假设：

- 5 个 `Interceptor_Cam_*` 主镜头。
- 5 个目标，目标距拦截镜头约 50m。
- 目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标。
- 一个或多个高空系留二级侦察镜头，比目标高约 200m，分辨率更高，覆盖全局视野。

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

AirSim 场景中可加入高空系留侦察无人机作为二级节点。二级节点正常时，将其覆盖小区内的离线图像 cue 转换为 `ReconImageCue`：

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
3. 对二级系留侦察镜头发布已重投影的 `ReconImageCue`；过期或不可用 cue 必须显式标记。
4. 调用 `TerminalObservationBus.cross_view_associations()` 汇总重叠视场支持。
5. 调用 `compute_terminal_stress_metrics()` 和 `summarize_degradation_case()` 生成 D5 证据。

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

## 防护约束

- D5 不调用 AirSim 控制 API。
- D5 不输出控制量、拦截点、打击参数或毁伤判断。
- D5 不改变中心全局轨迹表。
- 友方重叠默认 `hold`。
- 未知身份默认保持未知，不自动推断为对抗目标。
- 所有自动输出仅供离线评估和人工审查。

## 里程碑

1. 用 AirSim 真值投影生成 `LocalVisualTrack`，复现当前合成仿真指标。
2. 加入图像噪声、遮挡和漏检，评估 `ambiguous/reacquire` 行为。
3. 接入离线 MOT 输出，比较 ByteTrack、BoT-SORT、Deep SORT 与 D5 关联层。
4. 加入模拟身份声明异常，包括 stale、unverified、spoof_suspected。
5. 固化离线评估报告模板和结果 JSON 导出。
