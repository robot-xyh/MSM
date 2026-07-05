# D5 实现差距审计

**审计范围**：`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d5_terminal_association/README.md`、`PLAN.md`、`docs/ALGORITHM_AND_IMPLEMENTATION.md`、`src/d5_terminal_association/` 和 `tests/`。

**边界**：本文只审计 D5 末端视觉配准、协同身份声明、二级节点 cue、跨视角摘要和 AirSim ComputerVision 检测框适配现状。D5 不重新分配目标，不创建、不改写、不换绑 `global_track_id`；在线几何配准不得使用 AirSim `object_id`、`actor_name` 或 truth ID，truth 只能作为离线评估标签。

## 总体结论

D5 当前已经实现离线科研主线：

```text
GlobalTrack -> CameraModel -> OpenCV/projected image point
-> LocalVisualTrack -> TerminalAssociator -> TerminalAssociation
-> TerminalObservationBus / TerminalConsistencySummary
```

已落地的能力包括：单相机 `cv2.projectPoints`/针孔投影 fallback、像素协方差传播、马氏几何门控、保守 `locked/ambiguous/hold/reacquire` 决策、`LocalVisualTrack`/`TerminalAssociation`/`IdentityClaim`/`ReconImageCue` 数据结构、二级 cue 作用域和重投影校验、跨视角摘要层、重复锁定风险、一致性摘要、AirSim `simGetDetections` 风格 bbox adapter、YOLO 常见 `xyxy` bbox schema 兼容、AirSim 相机内外参转换和离线几何配准验证。

未落地的是完整真实图像/MOT/身份/标定工程栈：ByteTrack、BoT-SORT、Deep SORT、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、OpenCV calibration/`solvePnP`、ROS 2 `tf2/message_filters`、真实二级侦察图像反投影再重投影链路，以及跨相机几何联合优化器。

## 已实现

| 能力项 | 当前状态与证据 | 说明 |
|---|---|---|
| `LocalVisualTrack` | 已实现。`models.py` 定义本地轨迹；`airsim_cv_adapter.py::local_visual_tracks_from_sim_detections()` 可从 AirSim/YOLO 风格 bbox 生成中心点、bbox、质量、类别和 `mot_history_length`。 | 只标准化检测/MOT 输出，不运行真实 tracker。 |
| `TerminalAssociation` | 已实现。`associator.py::TerminalAssociator.decide()` 只评估 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`、候选代价、友方冲突和 cue 使用标记。 | 不是重分配器，不会选择另一个全局 ID 作为新分配。 |
| OpenCV `projectPoints` / 几何门控 | 已实现单相机版。`geometry.py::_project_pixel()` 优先调用 `cv2.projectPoints`，不可用时退回针孔公式；`project_track()` 传播协方差，`mahalanobis_d2()` 做像素马氏距离。 | 只消费已有 `CameraModel.K/R/t/dist_coeffs`，不估计标定参数。 |
| AirSim 相机几何 adapter | 已实现模块内验证辅助。`airsim_geometry.py` 提供 FOV 到 K、AirSim quaternion 到 OpenCV camera rotation、`camera_model_from_airsim_camera_info()` 和 `associate_tracks_to_detections_geometrically()`。 | 用于 D5 几何验证；不调用 AirSim API，也不依赖 object truth。 |
| AirSim `simGetDetections` bbox adapter | 已实现 dry-run 适配。`airsim_cv_adapter.py` 接受 `box2D`、`bbox_xyxy`、`xyxy` 等 schema，发布到 `TerminalObservationBus`。 | 不导入 AirSim；真实采集由 main/runtime 负责。 |
| YOLO detect adapter 兼容 | 已实现 bbox schema 兼容。测试 `test_detection_parser_accepts_runtime_bbox_xyxy_and_yolo_xyxy_schema()` 覆盖 `xyxy`/`track_id`。 | 不是 YOLO 推理链路，也不加载 detector。 |
| AirSim truth ID 隔离 | 已实现并测试。`airsim_cv_adapter.py` 明确忽略 `object_id/actor_name`；`test_detection_parser_ignores_airsim_truth_identity_fields_online()` 覆盖；`airsim_geometry.py::evaluate_associations_offline()` 才读取 truth label。 | 在线关联只用 bbox、时间、相机几何、本地 ID、类别和置信度。 |
| `global_track_id` 不变式 | 已实现。`GlobalTrack` frozen；`TerminalAssociator` 记录输入 ID 并 `_assert_global_ids_unchanged()`；`TerminalObservationBus` 只按已有 `assigned_global_track_id` 分组。 | D5 只输出 evidence，不能成为分配权威。 |
| `IdentityClaim` 抽象 | 已实现模拟层。`identity.py::IdentityChecker.parse_claims()` 可把 Remote ID/OpenDroneID 风格 dict 和通用签名字段转为 `IdentityClaim`；verified friend overlap 触发 `hold`。 | 只做正向友方确认；未知不升级。 |
| 二级节点 cue | 已实现摘要/代价基线。`ReconImageCue` 有 producer、frame、global ID、center/bbox、confidence、scope、metadata；`associator.py` 校验 scope、age、frame 和 `reprojected_to_local_camera` 后给代价 bonus。 | cue 不能绕过授权、版本、友方冲突和 MOT 质量门槛。 |
| 跨视角重复锁定 | 已实现摘要层。`observation_bus.py::cross_view_associations()` 按既有全局 ID 汇总多资源支持，命名空间化 local ID，并输出 `duplicate_terminal_lock_risk`。 | 只上报给 D3/D4 仲裁，不解除锁定，不改计划。 |
| 一致性摘要 | 已实现。`consistency.py::TerminalConsistencyTracker` 输出 `TerminalConsistencySummary`，包含 lock age、连续 ambiguous/hold/reacquire、丢锁/重捕获、重复锁定风险、cross-view support 和 `recommended_d4_action`。 | 是 D4/D6 advisory summary，不替代 D4 仲裁。 |
| 二级计划 2v2 语义 | 已实现测试覆盖。`test_airsim_cv_2v2_secondary_plan.py` 覆盖二级 plan 输入后只锁定 `assigned_global_track_id`、locked mismatch 只进入问题统计、不改写 ID、友方冲突阻断。 | 2v2 是测试语义，不是算法规模上限。 |
| N-v-N stress 指标 | 已实现 D5 helper。`compute_terminal_stress_metrics()` 与 `summarize_degradation_case()` 输出 per-camera count、multi-target FOV、cross-view overlap、duplicate risk、lock accuracy、ambiguous count 和三类 degradation evidence。 | 5v5 只是默认 stress baseline；`AirSimCVScenarioSpec` 支持传入不同数量。 |
| 视觉 PNG handoff 建议 | 已实现 advisory metadata。`visual_handoff.py::annotate_visual_png_handoff()` 在已有 `TerminalAssociation` 上附加 bbox 稳定、距离区间、TGO、延迟和 maneuver margin 等建议。 | D5 不决定导引律；D7/main 仍需独立 gate。 |

## 部分实现

| 能力项 | 已有部分 | 未完成部分 | 未完成原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|
| OpenCV calibration / 畸变使用 | `CameraModel` 可携带 `dist_coeffs`，`projectPoints` 会消费。 | 没有 `calibrateCamera`、标定图像流程或重投影误差报告。 | 当前 AirSim/runtime 可直接给相机参数，D5 阶段优先验证关联逻辑。 | 标定图像、棋盘/AprilTag 角点、畸变模型选择、误差验收阈值。 | P2 |
| OpenCV `solvePnP` | 文档已列为推荐链路。 | 代码未调用 `cv2.solvePnP` 或 PnP RANSAC。 | 当前 D5 假设上游提供 `CameraModel.R/t`，没有足够 2D-3D 匹配点。 | 稳定 2D-3D 对应、PnP RANSAC 策略、外参漂移判据、离线标定样本。 | P2 |
| OpenDroneID / Remote ID | `IdentityChecker` 可解析 `protocol=OpenDroneID` 风格字典并给出 verified/stale/spoof_suspected。 | 未接 OpenDroneID Core C，未解析真实广播报文。 | 缺少真实 Remote ID 数据源、签名/来源校验和平台白名单。 | OpenDroneID decoder、密钥/白名单、位置一致性检查、时间同步。 | P1/P2 |
| MAVLink signing | `IdentityChecker` 可消费 `signed/signature_valid` 风格模拟字段。 | 未验证真实 MAVLink signing，也没有 key 管理。 | 当前没有 MAVLink telemetry source。 | MAVLink 消息流、签名校验库、系统 ID/组件 ID 策略、密钥和时钟策略。 | P2 |
| 跨视角目标关联 | `TerminalObservationBus` 和 `CrossViewAssociation` 已做摘要层分组、support count、duplicate lock 风险。 | 没有多相机几何联合优化、时间对齐、姿态协方差或 per-view cost 融合。 | 当前只需要向 D3/D4/D6 提供安全摘要，尚无完整跨相机观测合同。 | `CrossViewObservation`、每相机 `CameraModel`、measurement/arrival timestamp、D2 `GlobalTrack[]`、跨相机代价函数。 | P2 |
| 二级侦察图像 cue | 已有 `ReconImageCue`、scope/age/frame/reprojection 校验和代价 bonus。 | 没有从二级相机图像检测结果反投影到 3D 再重投影到拦截机相机。 | 缺少二级相机真实 detection、pose、深度/三维目标估计。 | 二级相机标定和 pose、目标三维估计、cue 新鲜度策略、目标相机 frame 映射。 | P2 |
| MOT 输入质量 | 使用 `local_track_id`、`mot_history_length`、`quality` 做锁定门槛。 | 不维护帧间 tracker 状态，不计算 ID switch。 | 当前 D5 只定义 LocalVisualTrack 消费合同。 | 图像帧或 detector stream、帧率、tracker cache、真值 IDSW 评估。 | P1 |

## 未实现

| 未实现项 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|
| ByteTrack | 当前只消费 bbox/MOT 抽象输出，未引入真实图像帧、detector 和第三方 tracker 依赖。 | RGB/PNG frame 或稳定 detector bbox stream、ByteTrack 依赖、类别/置信度 schema、MOT 真值。 | P1：先做可选 adapter，不替换 D5 主线。 |
| BoT-SORT | 需要相机运动补偿、ReID 和检测器链路，超出当前 metadata-only dry-run。 | 连续图像、相机运动估计、BoT-SORT 依赖、ReID 模型、算力预算。 | P2：ByteTrack baseline 后再评估。 |
| Deep SORT | 小型无人机外观纹理弱，当前没有 embedding 提取或外观真值。 | 图像帧、检测器、embedding 模型、IDSW/IDF1 评估数据。 | P2：作为对照，不作为默认主线。 |
| DDS Security | D5 不运行 ROS 2/DDS middleware。 | ROS 2 runtime、enclave、证书、权限文件、节点身份到 `IdentityClaim` 的映射。 | P3。 |
| AprilTag | 当前不处理图像帧，也没有 tag detector。 | RGB/灰度图、AprilTag detector、tag ID 到友方平台映射、误检/漏检评估。 | P2。 |
| ROS 2 `tf2/message_filters` | 仓库当前是 Python 离线/AirSim runtime，不启动 ROS 图。 | 带戳 topic schema、frame tree、ApproximateTime/ExactTime 同步策略、bag/replay。 | P3。 |
| 真实图像保存/处理 | D5 默认 metadata-only，不保存 PNG；图像链路不应成为当前逻辑依赖。 | 若接入 MOT/AprilTag，需要图像帧、存储策略、离线复盘格式。 | P2。 |
| 跨相机几何联合优化器 `TerminalCrossViewFusion` | 目前只有摘要层，不具备跨相机姿态/时间/协方差联合建模。 | `CrossViewObservation`、多相机 `CameraModel`、同步时间戳、融合代价、冲突状态机。 | P2。 |
| 真实 YOLO 推理链路 | 仅兼容 YOLO 常见 `xyxy` 输出 schema；没有加载权重或运行 detector。 | 图像流、权重、class map、置信度阈值、CPU/GPU 预算、评估样本。 | P1/P2，取决于 main 是否要求图像 detector。 |

## 未实现原因归纳

1. **当前主线是轻量可复现离线科研链路**：D5 默认测试只依赖 Python、NumPy、OpenCV 和 pytest，不强制 AirSim、ROS 2、GPU、MAVLink 或真实 Remote ID 硬件。
2. **D5 的职责是消费抽象证据而不是运行所有外部栈**：MOT、Remote ID、MAVLink、DDS、AprilTag 都应先归一化为 `LocalVisualTrack` 或 `IdentityClaim` 后进入 D5。
3. **真实图像/协议/密钥/标定数据缺失**：未实现项多数需要连续图像帧、协议报文、密钥、标定板/特征点、相机姿态和多源时间同步。
4. **安全边界优先于锁定率**：当前实现宁愿输出 `ambiguous/hold/reacquire`，也不允许用最近目标、truth ID 或局部 MOT ID 换绑 `global_track_id`。
5. **跨模块条件未完全闭合**：真实 episode 中仍需要 main/D2/D3/D4 提供稳定 `GlobalTrack`、当前 `Assignment`、相机外参、时间戳、二级 cue 和 D4/D6 消费路径。

## 缺少条件清单

| 条件 | 影响能力 | 归属/来源 |
|---|---|---|
| 连续 RGB/PNG 或 detector bbox stream | ByteTrack、BoT-SORT、Deep SORT、AprilTag、真实 YOLO | main/AirSim runtime 或外部 detector |
| 准确相机 K/R/t/dist、时间戳和 frame_id | `projectPoints` 准确性、solvePnP/calibration、跨相机融合 | main/runtime 或标定流程 |
| 2D-3D 匹配点和重投影误差样本 | `solvePnP`、标定质量评估 | 标定/仿真 fixture |
| Remote ID/MAVLink/DDS 真实报文和密钥 | OpenDroneID、MAVLink signing、DDS Security | 通信/身份层 |
| 二级侦察节点真实检测与 pose | cue 反投影/重投影、degrade_to_secondary 真实性 | D4/main/runtime |
| D3/D4 消费 `duplicate_terminal_lock_risk` 和 `TerminalConsistencySummary` | 重复锁定仲裁、主动降级闭环 | D3/D4/main |
| D6 统一记录 terminal record/event | terminal lock accuracy、locked mismatch、cue 依赖、handoff 建议评估 | D6/main |

## 下一步优先级

| 优先级 | 任务 | 验收建议 |
|---|---|---|
| P0 | 保持现有安全合同回归：D5 不改写 `global_track_id`、不使用 AirSim truth 在线关联、friend overlap `hold`、二级 cue 需 frame/scope/age/reprojection 校验。 | `pytest -q research_modules/d5_terminal_association/tests`。 |
| P1 | 将 `airsim_geometry.py` 的相机转换、几何匹配结果和 `TerminalConsistencySummary` 纳入 main runtime/D6 日志字段。 | AirSim CV replay 中记录 projected pixel、pixel error、mahalanobis、gate_pass、locked mismatch 和 duplicate lock。 |
| P1 | 增加可选 ByteTrack adapter，只把 tracker 输出转为 `LocalVisualTrack`，不让 tracker ID 替代 `global_track_id`。 | 单测覆盖短遮挡、低置信检测和 local ID switch，D5 仍只锁定 assigned ID。 |
| P1 | 明确 YOLO detector adapter 边界：D5 接收 `xyxy/class/confidence/track_id/timestamp`，不在 D5 内运行控制或分配。 | schema fixture 和 truth 隔离测试。 |
| P2 | 实现 solvePnP/calibration 离线验证工具。 | 标定样本、PnP RANSAC、重投影误差阈值和外参漂移告警。 |
| P2 | 设计 `CrossViewObservation`/`TerminalCrossViewFusion`，把摘要层升级为跨相机几何融合。 | UAV1 `{G1,G2,G3}`、UAV2 `{G2,G3,G4}` 场景中输出 per-view cost、timestamp skew、pose covariance 和 conflict state。 |
| P2 | 接入真实 OpenDroneID/MAVLink signing/AprilTag 之一作为 `IdentityClaim` adapter。 | 真实或回放报文/图像 fixture，验证 stale/spoof/unverified/verified 状态不会把未知目标升级。 |
| P3 | ROS 2 `tf2/message_filters` 和 DDS Security。 | 仅在项目转为 ROS 2 runtime 后实施。 |

## 关键代码依据

- `research_modules/d5_terminal_association/src/d5_terminal_association/models.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/associator.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_cv_adapter.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/identity.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/observation_bus.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/consistency.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_terminal_association.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_5v5_evidence.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_2v2_secondary_plan.py`
- `research_modules/d5_terminal_association/tests/test_geometric_registration_validation.py`
- `research_modules/d5_terminal_association/tests/test_terminal_observation_bus.py`
- `research_modules/d5_terminal_association/tests/test_terminal_consistency.py`
- `research_modules/d5_terminal_association/tests/test_visual_handoff.py`
