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

已落地的能力包括：单相机 `cv2.projectPoints`/针孔投影 fallback、像素协方差传播、马氏几何门控、保守 `locked/ambiguous/hold/reacquire` 决策、`LocalVisualTrack`/`TerminalAssociation`/`IdentityClaim`/`ReconImageCue` 数据结构、二级 cue 作用域和重投影校验、跨视角摘要层、完全分布式 metadata-only 跨 peer 视觉假设生成、重复锁定风险、一致性摘要、AirSim `simGetDetections` 风格 bbox adapter、YOLO/ByteTrack 离线 schema adapter、YOLOv8 + ByteTrack/BoT-SORT frame adapter、确定性 IoU fallback tracker、AirSim 相机内外参转换、离线几何配准验证和可写盘 geometry/consistency/handoff metadata。

未落地的是完整 runtime 工程栈：main/AirSim 连续图像流接入、GPU/CPU 部署与多 seed 阈值标定、Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、OpenCV calibration/`solvePnP`、ROS 2 `tf2/message_filters`、真实二级侦察图像反投影再重投影链路，以及跨相机几何联合优化器。

2026-07-07 复核状态：`TerminalConsistencyTracker` 连续窗口已按 `resource_id + assigned_global_track_id` 维护，D3 对同一资源/目标滚动发布新的 `assignment_version` 不会清空连续视觉状态。该能力已由 `test_consistency_streak_survives_plan_version_updates_for_same_assignment_pair` 覆盖。D5 已补充 projected pixel、pixel error、Mahalanobis、gate pass、friend conflict、measurement age、duplicate-risk advisory、LOS/measurement-age handoff blockers 和离线 YOLO/ByteTrack truth 隔离测试。D5 的一致性输出仍是 advisory summary，只供 D4/D6/D7 作为证据消费，不触发降级、不生成 `AssignmentPlan`、不改写 `global_track_id`。

## 跨模块合同结论

- 与 D4：D5 输出的是 terminal visual evidence，不是分配结果。`CrossViewAssociation`、`TerminalConsistencySummary`、`DistributedTerminalAssociation`、`duplicate_terminal_lock_risk`、`hypothesis_only/hold/ambiguous` 原因和 `recommended_d4_action` 可作为 D4 CBBA/主动降级的风险加权输入；D5 不生成 `AssignmentPlan`，不选择主备资源，不改写、不新建、不换绑 `global_track_id`。
- 与 D7：D7 视觉 PNG 切换必须依赖 D5 `locked`、当前 D3/D4 `assigned_global_track_id` 一致、bbox 连续稳定、无友方冲突、无重复锁定风险，并通过 D4/D3 gate。D5 的 `visual_png_prelock_recommended` 或 `handoff_recommended` 只是前置证据；D7 仍需独立检查 LOS、相机状态、导引律、机动裕度、检测延迟和 terminal gate。
- 与 AirSim/runtime：在线 D5 不能使用 AirSim `object_id`、`actor_name`、actor truth ID 或离线 truth map 做关联、过滤、换绑或锁定。truth ID 只允许在离线评估 metadata/evaluator 中计算 `terminal_lock_accuracy`、`locked_mismatch`、stress report 和测试断言。
- 与规模参数：2v2 与 5v5 只是 baseline 和 stress scenario 名称。D5 算法按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表、`TerminalObservation[]` 或 peer DTO 数组长度运行，不写死资源数或目标数。

## 已实现

| 能力项 | 当前状态与证据 | 说明 |
|---|---|---|
| `LocalVisualTrack` | 已实现。`models.py` 定义本地轨迹；`airsim_cv_adapter.py::local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `yolo_mot_adapter.py::YoloMotAdapter.process_frame()` 可从 AirSim bbox、离线 schema 或图像帧 detector/tracker 输出生成中心点、bbox、质量、类别和 `mot_history_length`。 | 只标准化本地检测/MOT 输出，不携带 truth/global ID；tracker ID 只能是本地 ID。 |
| `TerminalAssociation` | 已实现。`associator.py::TerminalAssociator.decide()` 只评估 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`、候选代价、友方冲突、cue 使用标记和 per-pair geometry log metadata。 | 不是重分配器，不会选择另一个全局 ID 作为新分配。 |
| OpenCV `projectPoints` / 几何门控 | 已实现单相机版。`geometry.py::_project_pixel()` 优先调用 `cv2.projectPoints`，不可用时退回针孔公式；`project_track()` 传播协方差，`mahalanobis_d2()` 做像素马氏距离。 | 只消费已有 `CameraModel.K/R/t/dist_coeffs`，不估计标定参数。 |
| AirSim 相机几何 adapter | 已实现模块内验证辅助。`airsim_geometry.py` 提供 FOV 到 K、AirSim quaternion 到 OpenCV camera rotation、`camera_model_from_airsim_camera_info()`、`associate_tracks_to_detections_geometrically()` 和 `GeometricAssociationResult.to_log_records()`。 | 用于 D5 几何验证；不调用 AirSim API，也不依赖 object truth；main/D6 仍需接入实际日志 sink。 |
| AirSim `simGetDetections` bbox adapter | 已实现 dry-run 适配。`airsim_cv_adapter.py` 接受 `box2D`、`bbox_xyxy`、`xyxy` 等 schema，发布到 `TerminalObservationBus`。 | 不导入 AirSim；真实采集由 main/runtime 负责。 |
| YOLOv8 + ByteTrack/BoT-SORT adapter | 已实现模块 adapter。`YoloMotAdapter` 默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许覆盖；可请求 ultralytics ByteTrack/BoT-SORT，缺依赖/权重/原生 tracker 时返回 `unavailable` 或使用确定性 IoU fallback。测试覆盖 mock YOLO 输出、连续帧 local track ID 稳定、truth/global 字段隔离和无 ultralytics 状态。 | D5 不采集 AirSim 图像流、不管理 GPU/CPU 部署、不把 tracker ID 替代 `global_track_id`；真实 runtime 接线归 main。 |
| AirSim truth ID 隔离 | 已实现并测试。`airsim_cv_adapter.py` 明确忽略 `object_id/actor_name/truth_id/global_track_id`；`test_detection_parser_ignores_airsim_truth_identity_fields_online()` 和离线 YOLO/ByteTrack adapter 测试覆盖；`airsim_geometry.py::evaluate_associations_offline()` 才读取 truth label。 | 在线关联只用 bbox、时间、相机几何、本地 ID、类别和置信度。 |
| `global_track_id` 不变式 | 已实现。`GlobalTrack` frozen；`TerminalAssociator` 记录输入 ID 并 `_assert_global_ids_unchanged()`；`TerminalObservationBus` 只按已有 `assigned_global_track_id` 分组。 | D5 只输出 evidence，不能成为分配权威。 |
| `IdentityClaim` 抽象 | 已实现模拟层。`identity.py::IdentityChecker.parse_claims()` 可把 Remote ID/OpenDroneID 风格 dict 和通用签名字段转为 `IdentityClaim`；verified friend overlap 触发 `hold`。 | 只做正向友方确认；未知不升级。 |
| 二级节点 cue | 已实现摘要/代价基线。`ReconImageCue` 有 producer、frame、global ID、center/bbox、confidence、scope、metadata；`associator.py` 校验 scope、age、frame 和 `reprojected_to_local_camera` 后给代价 bonus。 | cue 不能绕过授权、版本、友方冲突和 MOT 质量门槛。 |
| 跨视角重复锁定 | 已实现摘要层。`observation_bus.py::cross_view_associations()` 按既有全局 ID 汇总多资源支持，命名空间化 local ID，并输出 `duplicate_terminal_lock_risk`。 | 只上报给 D3/D4 仲裁，不解除锁定，不改计划。 |
| 完全分布式跨 peer 视觉假设 | 已实现 P0 metadata-only。`terminal_cross_view_fusion.py::TerminalCrossViewFusion` 消费 `DistributedVisualObservation`、`VisualTrackletSummary` 和 `PeerCameraState`，基于时间、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差 gating/cost，输出 `CrossPeerAssociationHypothesis` 与 `DistributedTerminalAssociation`。 | 使用 Hungarian；SciPy 不可用时退回纯 Python 最小代价唯一匹配。missing/stale `global_track_id`、重复锁定、友方冲突或 local/global ID 冲突不会输出 `locked`。 |
| 一致性摘要 | 已实现。`consistency.py::TerminalConsistencyTracker` 输出 `TerminalConsistencySummary`，包含 lock age、连续 ambiguous/hold/reacquire、丢锁/重捕获、重复锁定风险、cross-view support 和 `recommended_d4_action`。2026-07-07 已将连续窗口 key 固化为 `resource_id + assigned_global_track_id`，避免同一 assignment pair 的滚动 plan version 更新清空 D4 需要的连续视觉状态。 | 是 D4/D6 advisory summary，不替代 D4 仲裁；D5 仍不因连续丢锁触发降级。 |
| 二级计划 2v2 语义 | 已实现测试覆盖。`test_airsim_cv_2v2_secondary_plan.py` 覆盖二级 plan 输入后只锁定 `assigned_global_track_id`、locked mismatch 只进入问题统计、不改写 ID、友方冲突阻断。 | 2v2 是测试语义，不是算法规模上限。 |
| N-v-N stress 指标 | 已实现 D5 helper。`compute_terminal_stress_metrics()` 与 `summarize_degradation_case()` 输出 per-camera count、multi-target FOV、cross-view overlap、duplicate risk、lock accuracy、ambiguous count 和三类 degradation evidence。 | 5v5 只是默认 stress baseline；`AirSimCVScenarioSpec` 支持传入不同数量。 |
| 视觉 PNG handoff 建议 | 已实现 advisory metadata。`visual_handoff.py::annotate_visual_png_handoff()` 在已有 `TerminalAssociation` 上附加 bbox 稳定、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和 maneuver margin 等建议。 | D5 不决定导引律；D7/main 仍需独立 gate；stale measurement age 和 missing LOS 会阻断建议。 |

已实现项的安全边界：

- `locked` 只表示“当前分配 ID 的视觉候选被保守支持”，不是处置授权。
- `hypothesis_only` 只表示“peer metadata 之间可能支持同一视觉目标”，没有 current `assigned_global_track_id` 时不能升级为 `locked`。
- 重复锁定、友方冲突、stale ID、global/local ID 冲突都只输出风险和仲裁建议，不在 D5 内解除冲突。

## 部分实现

| 能力项 | 已有部分 | 未完成部分 | 未完成原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|
| OpenCV calibration / 畸变使用 | `CameraModel` 可携带 `dist_coeffs`，`projectPoints` 会消费。 | 没有 `calibrateCamera`、标定图像流程或重投影误差报告。 | 当前 AirSim/runtime 可直接给相机参数，D5 阶段优先验证关联逻辑。 | 标定图像、棋盘/AprilTag 角点、畸变模型选择、误差验收阈值。 | P2 |
| OpenCV `solvePnP` | 文档已列为推荐链路。 | 代码未调用 `cv2.solvePnP` 或 PnP RANSAC。 | 当前 D5 假设上游提供 `CameraModel.R/t`，没有足够 2D-3D 匹配点。 | 稳定 2D-3D 对应、PnP RANSAC 策略、外参漂移判据、离线标定样本。 | P2 |
| OpenDroneID / Remote ID | `IdentityChecker` 可解析 `protocol=OpenDroneID` 风格字典并给出 verified/stale/spoof_suspected。 | 未接 OpenDroneID Core C，未解析真实广播报文。 | 缺少真实 Remote ID 数据源、签名/来源校验和平台白名单。 | OpenDroneID decoder、密钥/白名单、位置一致性检查、时间同步。 | P1/P2 |
| MAVLink signing | `IdentityChecker` 可消费 `signed/signature_valid` 风格模拟字段。 | 未验证真实 MAVLink signing，也没有 key 管理。 | 当前没有 MAVLink telemetry source。 | MAVLink 消息流、签名校验库、系统 ID/组件 ID 策略、密钥和时钟策略。 | P2 |
| 跨视角高阶几何优化 | `TerminalObservationBus`、`CrossViewAssociation` 和 `TerminalCrossViewFusion` 已覆盖摘要层与 metadata-only P0 假设生成，包含 measurement/arrival timestamp、协方差、frame/resource/local ID 命名空间和姿态协方差 cost。 | 没有三维重投影、三角化、bundle adjustment、D2 航迹联合预测或跨相机几何优化。 | P0 只需要 metadata-only 分布式假设供 D4 消费；真实 3D 几何需要更完整的相机/D2 合同。 | 每相机 `CameraModel`、D2 `GlobalTrack[]`、时间同步、三维候选生成、几何残差模型。 | P2 |
| 二级侦察图像 cue | 已有 `ReconImageCue`、scope/age/frame/reprojection 校验和代价 bonus。 | 没有从二级相机图像检测结果反投影到 3D 再重投影到拦截机相机。 | 缺少二级相机真实 detection、pose、深度/三维目标估计。 | 二级相机标定和 pose、目标三维估计、cue 新鲜度策略、目标相机 frame 映射。 | P2 |
| MOT 输入质量 | 使用 `local_track_id`、`mot_history_length`、`quality` 做锁定门槛。 | 不维护帧间 tracker 状态，不计算 ID switch。 | 当前 D5 只定义 LocalVisualTrack 消费合同。 | 图像帧或 detector stream、帧率、tracker cache、真值 IDSW 评估。 | P1 |

部分实现项的口径：

- “接入 OpenCV”当前只代表投影/畸变参数消费，不代表已经具备真实标定链。
- “兼容 YOLO”当前代表已有 bbox schema adapter 和 `YoloMotAdapter` frame adapter；不代表 main runtime 已把 AirSim 连续图像流、部署参数和多 seed 标定闭环接好。
- “支持 OpenDroneID/MAVLink/DDS/AprilTag”当前只代表 `IdentityClaim` 抽象可表达这些来源，不代表真实协议或 detector 已接入。
- “支持 distributed visual association”当前只代表 metadata-only peer evidence，不代表完成三维几何配准、三角化或跨相机 bundle adjustment。

## 未实现

| 未实现项 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|
| main runtime 图像流接入 | D5 已提供 `YoloMotAdapter`，但 AirSim/main 尚需把连续 RGB/PNG frame、camera/resource/frame_id/timestamp 和参数覆盖传入该 adapter。 | RGB/PNG frame 或稳定 detector bbox stream、runtime 参数、日志 sink、episode/seed 配置。 | P1：main 接线，不替换 D5 几何主线。 |
| BoT-SORT 工程质量评估 | D5 可请求 ultralytics BoT-SORT 或退回 IoU tracker，但小目标运动相机质量未评估。 | 连续图像、相机运动估计、BoT-SORT 依赖、ReID 模型、算力预算、IDF1/IDSW 真值。 | P2：真实图像链路后再评估。 |
| Deep SORT | 小型无人机外观纹理弱，当前没有 embedding 提取或外观真值。 | 图像帧、检测器、embedding 模型、IDSW/IDF1 评估数据。 | P2：作为对照，不作为默认主线。 |
| DDS Security | D5 不运行 ROS 2/DDS middleware。 | ROS 2 runtime、enclave、证书、权限文件、节点身份到 `IdentityClaim` 的映射。 | P2：仅在 ROS 2/DDS runtime 或回放链路确定后实施。 |
| AprilTag | 当前不处理图像帧，也没有 tag detector。 | RGB/灰度图、AprilTag detector、tag ID 到友方平台映射、误检/漏检评估。 | P2。 |
| ROS 2 `tf2/message_filters` | 仓库当前是 Python 离线/AirSim runtime，不启动 ROS 图。 | 带戳 topic schema、frame tree、ApproximateTime/ExactTime 同步策略、bag/replay。 | P2：仅在项目进入 ROS 2 runtime 或 bag replay 后实施。 |
| 真实图像保存/处理 | D5 默认 metadata-only，不保存 PNG；图像链路不应成为当前逻辑依赖。 | 若接入 MOT/AprilTag，需要图像帧、存储策略、离线复盘格式。 | P2。 |
| 跨相机三维联合优化器 | 当前 `TerminalCrossViewFusion` 是 metadata-only P0，不做三维相机几何联合优化。 | 多相机 `CameraModel`、D2 航迹预测、同步时间戳、三维候选、重投影残差、冲突状态机。 | P2。 |
| YOLOv8 runtime 部署标定 | D5 adapter 已能加载默认 `best.pt` 或覆盖路径并运行/适配 detector 输出；缺少 main episode 中的部署参数、算力预算和多 seed 标定。 | 图像流、class map、置信度阈值、CPU/GPU 预算、评估样本和 seed 结果。 | P1：main runtime 接线和多 seed 标定。 |

按工程链路归纳的未实现项：

- 真实多目标检测器：D5 已有 YOLOv8 frame adapter；main 仍缺连续 RGB/PNG frame 输入接线、class map、阈值策略、硬件加速和误检/漏检评估。
- 真实 MOT：D5 已有 ByteTrack/BoT-SORT 请求路径和 IoU fallback；仍缺长遮挡恢复、ReID embedding、frame-to-frame IDSW 统计和 MOT 真值。
- 真实标定链：没有标定图像、棋盘/AprilTag 角点、相机-机体系-世界系同步姿态、`calibrateCamera`/`solvePnP` 验证、重投影误差报告和外参漂移告警。
- 真实身份认证链路：没有 OpenDroneID/MAVLink/DDS 实际报文、密钥/证书/白名单管理、时间同步、消息来源到平台身份的可信映射，也没有 AprilTag detector。

## 未实现原因归纳

1. **当前主线是轻量可复现离线科研链路**：D5 默认测试只依赖 Python、NumPy、OpenCV 和 pytest，不强制 AirSim、ROS 2、GPU、MAVLink 或真实 Remote ID 硬件。
2. **D5 的职责是消费抽象证据而不是运行所有外部栈**：MOT、Remote ID、MAVLink、DDS、AprilTag 都应先归一化为 `LocalVisualTrack` 或 `IdentityClaim` 后进入 D5。
3. **真实图像/协议/密钥/标定数据缺失**：未实现项多数需要连续图像帧、协议报文、密钥、标定板/特征点、相机姿态和多源时间同步。
4. **安全边界优先于锁定率**：当前实现宁愿输出 `ambiguous/hold/reacquire`，也不允许用最近目标、truth ID 或局部 MOT ID 换绑 `global_track_id`。
5. **跨模块条件未完全闭合**：真实 episode 中仍需要 main/D2/D3/D4 提供稳定 `GlobalTrack`、当前 `Assignment`、相机外参、时间戳、二级 cue 和 D4/D6 消费路径。

## 缺少条件清单

| 条件 | 影响能力 | 归属/来源 |
|---|---|---|
| 连续 RGB/PNG 或 detector bbox stream | main 接 `YoloMotAdapter`、ByteTrack、BoT-SORT、Deep SORT、AprilTag | main/AirSim runtime 或外部 detector |
| 准确相机 K/R/t/dist、时间戳和 frame_id | `projectPoints` 准确性、solvePnP/calibration、跨相机融合 | main/runtime 或标定流程 |
| 2D-3D 匹配点和重投影误差样本 | `solvePnP`、标定质量评估 | 标定/仿真 fixture |
| Remote ID/MAVLink/DDS 真实报文和密钥 | OpenDroneID、MAVLink signing、DDS Security | 通信/身份层 |
| 二级侦察节点真实检测与 pose | cue 反投影/重投影、degrade_to_secondary 真实性 | D4/main/runtime |
| D3/D4/main runtime 消费 D5 advisory evidence | 重复锁定仲裁、主动降级闭环 | D3/D4/main；D5 侧 evidence 字段已可输出 |
| D6/main 统一记录 terminal record/event | terminal lock accuracy、locked mismatch、cue 依赖、handoff 建议评估 | D6/main；D5 侧 geometry/consistency/handoff metadata 已可输出 |

## 下一步优先级

### P1 已补齐（D5 侧）

| 能力 | 当前证据 | 边界 |
|---|---|---|
| Geometry log fields | `TerminalAssociation.metadata`、`CandidateBreakdown.to_log_dict()` 和 `GeometricAssociationResult.to_log_records()` 输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair 与 duplicate-risk advisory。 | D5 只产出字段；main/D6 若要落盘 JSONL/CSV 需在其 owned paths 接入。 |
| `TerminalConsistencySummary` 连续窗口 | `TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口；`assignment_version` 仅进入摘要审计。 | advisory summary，不触发降级，不生成分配计划。 |
| AirSim truth ID 在线隔离 | AirSim/YOLO/ByteTrack adapter 忽略 `object_id`、`actor_name`、`truth_id`、`true_global_track_id`、`global_track_id` 等真值/全局字段；truth 只进入离线 evaluator/metadata。 | 在线关联只消费 bbox、时间、相机几何、本地 ID、类别和置信度。 |
| YOLOv8 frame adapter | `YoloMotAdapter.process_frame()` 将图像帧或 mock detector 输出转为命名空间化 `LocalVisualTrack`；原生 ByteTrack/BoT-SORT 不可用时 `IouFallbackTracker` 保持 deterministic local ID 连续性，并在 metadata 中标明 `tracker_backend`。 | 真实 AirSim frame stream 接入、部署参数和多 seed 标定仍由 main/runtime 完成。 |
| D4 evidence | `CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 已可作为 D4/D6 evidence。 | D5 不仲裁、不授权、不创建或换绑 `global_track_id`。 |
| D7 visual PNG 前置证据 | `annotate_visual_png_handoff()` 输出 handoff/prelock、gate pass、blockers、measurement age、LOS rate、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend/duplicate risk、unstable bbox、stale measurement age、missing LOS 会阻断。 | D5 不决定导引律，D7/main 仍需独立 terminal gate。 |

### 剩余 P1/P2

| 优先级 | 任务 | 验收建议 |
|---|---|---|
| P0 | 保持现有安全合同回归：D5 不改写 `global_track_id`、不使用 AirSim truth 在线关联、friend overlap `hold`、二级 cue 需 frame/scope/age/reprojection 校验，完全分布式 metadata-only 跨 peer 假设在 missing/stale global ID 或 duplicate risk 时不得 `locked`。 | `pytest -q research_modules/d5_terminal_association/tests`。 |
| P1 | main runtime 图像流接入。 | 用 AirSim 连续 RGB/PNG 或外部 detector bbox stream 调用 `YoloMotAdapter.process_frame()`，传入 resource/camera/frame_id/timestamp 和权重/后端参数；输出仍只归一化为 `LocalVisualTrack`，在线逻辑不得读 truth/global 字段，tracker ID 不替代 `global_track_id`。 |
| P1 | 多 seed 阈值校准。 | 跨 seed/episode 报告 `gate_chi2`、candidate margin、bbox stability、handoff range、measurement age、LOS availability、ambiguity 和 quality 阈值对 `locked_mismatch`、false handoff、ambiguous/reacquire 抖动和 `terminal_id_switch_count` 的影响。 |
| P2 | 实现 solvePnP/calibration 离线验证工具。 | 标定样本、2D-3D 对应、PnP RANSAC、重投影误差阈值和外参漂移告警。 |
| P2 | 评估 BoT-SORT/Deep SORT/ReID 是否适合小型无人机 AirSim/真实图像。 | 有连续图像、算力预算、IDF1/IDSW 评估；若小目标纹理不足，保持几何门控 + ByteTrack/schema adapter 为默认基线。 |
| P2 | 接入真实身份来源为 `IdentityClaim` adapter：OpenDroneID Core、MAVLink signing、DDS Security 或 AprilTag。 | 真实或回放报文/图像 fixture，验证 stale/spoof/unverified/verified 状态不会把未知目标升级，也不会绕过几何门控和 assignment 一致性。 |
| P2 | ROS 2 `tf2/message_filters` 坐标/时间同步链路。 | 仅在项目进入 ROS 2 runtime 或 bag replay 后实施；验收 frame tree、带戳 transform、相机/航迹同步和 D5 `CameraModel` 转换一致性。 |

## 关键代码依据

- `research_modules/d5_terminal_association/src/d5_terminal_association/models.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/associator.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_cv_adapter.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/yolo_mot_adapter.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/identity.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/observation_bus.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/terminal_cross_view_fusion.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/consistency.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_terminal_association.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_5v5_evidence.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_2v2_secondary_plan.py`
- `research_modules/d5_terminal_association/tests/test_geometric_registration_validation.py`
- `research_modules/d5_terminal_association/tests/test_terminal_observation_bus.py`
- `research_modules/d5_terminal_association/tests/test_distributed_cross_view_fusion.py`
- `research_modules/d5_terminal_association/tests/test_terminal_consistency.py`
- `research_modules/d5_terminal_association/tests/test_visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_yolo_mot_adapter.py`
