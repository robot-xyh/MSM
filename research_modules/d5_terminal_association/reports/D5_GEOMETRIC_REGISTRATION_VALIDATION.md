# D5_GEOMETRIC_REGISTRATION_VALIDATION

## 专项目标

本专项把 D5 末端视觉配准从 AirSim `simGetDetections` 自带 `object_id` / `actor_name` 强监督路径，推进到真实工程口径的几何配准路径：

- 在线关联只使用 `GlobalTrack` 三维状态、相机内外参、detection `bbox_xyxy` 计算出的 bbox center。
- AirSim detection 的 `object_id`、`actor_name`、truth ID 不进入在线关联函数，只允许在离线评估阶段作为真值标签。
- adapter 默认保留原始 bbox center，不再用 track projection pixel 覆盖 detection center。

## 当前已实现

1. AirSim 相机内参提取
   - 从 settings 的 `Width`、`Height`、`FOV_Degrees` 计算 OpenCV pinhole `K`。
   - 当前按水平 FOV 处理：`fx = fy = width / (2 * tan(FOV/2))`，`cx = width/2`，`cy = height/2`。
   - `640x480 + 120deg` 对应 `fx=fy≈184.75, cx=320, cy=240`，不再接受 `cx=640, cy=360` 这类旧内参。

2. AirSim 相机外参提取
   - runtime 优先读取 `simGetCameraInfo(camera_name, vehicle_name).pose`。
   - position 加上 vehicle settings 初始 `X/Y/Z`，形成全局 NED camera position。
   - orientation 作为 camera/body-to-world quaternion，转换为 world/NED 到 OpenCV camera frame 的 `rotation_world_to_camera`。
   - 如果 orientation 缺失，则从 vehicle + camera settings 的 `Pitch/Roll/Yaw` 合成；真实验证路径不再默认单位阵。

3. D5 几何关联
   - 新增几何验证接口：`GlobalTrack -> CameraModel -> project_tracks_to_image -> bbox center -> Mahalanobis gate -> Hungarian/scipy assignment fallback`。
   - 输出 per-pair 诊断字段：
     - `projected_px`
     - `bbox_center_px`
     - `pixel_error`
     - `mahalanobis_d2`
     - `gate_pass`
     - `assignment_selected`
   - 离线评估接口单独接收 `local_track_id -> truth/global_track_id` mapping，输出：
     - `association_accuracy`
     - `id_mismatch_count`
     - `evaluated_count`
     - `ambiguous_count`

4. adapter 真实路径保护
   - `local_visual_tracks_from_blocks_frame(..., use_projected_detection_centers=False)` 默认禁用 projection center override。
   - 即使传入 `terminal_tracks/terminal_camera` 做诊断，也不会覆盖 detection bbox center。
   - 旧的 projection override 只能显式打开，用于遗留合成测试，不作为真实几何验收路径。

5. legacy adapter 与真实几何 adapter 的边界
   - `local_visual_tracks_from_blocks_frame()` 是 legacy/offline 兼容入口。它仍会使用 AirSim `detection.object_id -> D2 truth_id -> global_track_id` 过滤 detection，并返回 `local_truth_map`，因此不能作为真实工程在线几何关联入口。
   - `geometric_local_visual_tracks_from_blocks_frame()` 是真实几何入口。它只使用 detection 的 `detection_id/local_track_id/camera_id/bbox_xyxy/confidence/classification_hint/timestamp`，从 bbox 计算 center，不读取、不过滤、不依赖 `object_id`、`actor_name` 或 truth ID。
   - `offline_truth_map_from_blocks_frame()` 是 evaluation-only 入口。它单独使用 AirSim truth ID 生成 `local_track_id -> global_track_id` 标签，只允许送入离线 `evaluate_associations_offline()`，不能进入 online association 输入。

## 当前不能保证的事项

- 尚未在真实 AirSim ComputerVision 进程中完成端到端 2v2 实测；当前完成的是 mock/unit/interface 验证。
- OpenCV camera frame 与 AirSim camera/body frame 的固定轴变换已按 forward/right/down 到 right/down/forward 处理，但仍需要真实图像点回归验证。
- `FOV_Degrees` 当前按水平 FOV 解释；如果具体 AirSim 版本或 ImageType 行为不同，需要用单目标实测校准。
- detection bbox center 与三维目标中心投影不一定重合，近距离、截断、遮挡和非点目标会带来系统误差。
- 多目标非常接近时，几何门控可能给出自然歧义，应通过 `ambiguous_count` 显式报告，而不是强行锁定。

## AirSim ComputerVision 2v2 实测步骤

1. 使用 2v2 或可缩小的 ComputerVision settings，明确 `CameraDefaults.CaptureSettings` 或 `Vehicles.*.Cameras.*.CaptureSettings`：
   - `ImageType=0`
   - `Width=640`
   - `Height=480`
   - `FOV_Degrees=120`

2. 启动 AirSim Blocks ComputerVision 场景，确认 runtime frame 中：
   - camera `fx/fy/cx/cy` 与 settings 一致。
   - `rotation_world_to_camera` 非单位阵，且随 camera yaw/pitch 改变。
   - detection `center_px` 来自 bbox，不等于 projection pixel 的强制替换值。

3. 单目标校准：
   - 固定一个目标在相机前方。
   - 输出 `projected_px` 与 `bbox_center_px`。
   - 检查 pixel error 是否在可解释范围内。

4. 2v2 几何配准：
   - 构建两个 `GlobalTrack`。
   - 使用 `geometric_local_visual_tracks_from_blocks_frame()` 从两个 AirSim detections 生成 `LocalVisualTrack`。
   - 调用 D5 几何关联接口。
   - 离线使用 `offline_truth_map_from_blocks_frame()` 生成评估标签，再统计 accuracy/mismatch。

5. 扩展到 5v5：
   - 保留相同接口。
   - 重点观察 `ambiguous_count`、`gate_reject_count`、`p95 pixel_error` 和 `id_mismatch_count`。

## 主要风险

- NED/world/camera 轴向约定错误。
- AirSim quaternion 方向被误解为 world-to-camera 而不是 camera-to-world。
- vehicle 初始 `X/Y/Z` 与 camera pose 的相对/全局口径重复相加或漏加。
- `FOV_Degrees` 水平/垂直口径不一致。
- bbox 边缘截断、目标太近、目标形状中心与三维中心不一致。
- timestamp 不同步导致 track prediction 和 image frame 错位。
- covariance 设置不合理，导致 gate 过严或过松。
