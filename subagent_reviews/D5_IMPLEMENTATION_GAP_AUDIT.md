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

已落地的能力包括：单相机 `cv2.projectPoints`/针孔投影 fallback、像素协方差传播、马氏几何门控、保守 `locked/ambiguous/hold/reacquire` 决策、`LocalVisualTrack`/`TerminalAssociation`/`IdentityClaim`/`ReconImageCue` 数据结构、二级 cue 作用域和重投影校验、跨视角摘要层、完全分布式 metadata-only 跨 peer 视觉假设生成、重复锁定风险、一致性摘要、AirSim `simGetDetections` 风格 bbox adapter、YOLO/ByteTrack 离线 schema adapter、YOLOv8 + ByteTrack/BoT-SORT frame adapter、确定性 IoU fallback tracker、AirSim 相机内外参转换、离线几何配准验证、可写盘 geometry/consistency/handoff metadata、P1 multi-seed calibration readiness 字段覆盖审计 helper、二级视觉覆盖 + detect 到 cross-view 转换漏斗诊断 helper、AirSim settings 驱动 detect-to-global-track registration helper，以及机动高空侦察云台 cue evidence。registration helper 消费 `GlobalTrack`、D2/D3 binding/`Assignment`、per-camera `CameraModel(K/R/t)`、timestamp、协方差和 `LocalVisualTrack`，用像素马氏距离 + Hungarian/JPDA-compatible candidates 输出既有 `global_track_id` 支持，记录 `DetectToGlobalTrackCandidate.outcome`、projection/reject reason、timestamp、measurement age、covariance summary 和稳定窗口结果，不使用 AirSim truth/actor ID。YOLO/MOT adapter 记录 confidence、class id、bbox scale、tracker backend 和请求的 CPU/GPU budget，tracker ID 仍只作为 `LocalVisualTrack.local_track_id`。机动云台 evidence 可区分 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`，并携带 GlobalTrack/radar cue 的 NED look-at、云台元数据、pointing error 和 gimbal track error。

未落地的是完整 runtime 工程栈：main/AirSim 连续图像流接入、GPU/CPU 实际部署与多 seed 阈值/预算标定、Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、OpenCV calibration/`solvePnP`、ROS 2 `tf2/message_filters`、真实二级侦察图像反投影再重投影链路，以及跨相机几何联合优化器。

2026-07-07 复核状态：`TerminalConsistencyTracker` 连续窗口已按 `resource_id + assigned_global_track_id` 维护，D3 对同一资源/目标滚动发布新的 `assignment_version` 不会清空连续视觉状态。该能力已由 `test_consistency_streak_survives_plan_version_updates_for_same_assignment_pair` 覆盖。D5 已补充 projected pixel、pixel error、Mahalanobis、gate pass、friend conflict、measurement age、duplicate-risk advisory、LOS/measurement-age handoff blockers 和离线 YOLO/ByteTrack truth 隔离测试。D5 的一致性输出仍是 advisory summary，只供 D4/D6/D7 作为证据消费，不触发降级、不生成 `AssignmentPlan`、不改写 `global_track_id`。

2026-07-08 AirSim 机动高空侦察节点复测状态分为历史 stress 与当前 calibration v2 两层：`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为旧批次证据，说明 `mobile_recon_gimbal` / `mobile_high_recon`、`radar_global_track_cue` 和云台指向 metadata 已被 D5 识别，目标看清能力相对固定俯视对照改善，但该批次的二级网络覆盖与降级注册没有闭合。最新结论来自 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`：单 seed、3 个机动高空二级节点、200 m、110 deg、1920x1080；`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，三个 case 的 stable cross-view registration 为 51/55/53，cross-view association 为 4/4/5，`degrade_to_secondary` / `degrade_to_distributed` 的 not-registered case 仍为 35/35，full-view mean≈0.048，coverage mean≈0.771。因此当前瓶颈不是 projection invalid，也不再是 cross-view 全为 0；主要缺口是二级网络全目标覆盖不足、`not_all_targets_visible` / `network_union_incomplete`、降级 case not-registered 仍高，以及真实多 seed 的阈值、外参和 MOT 标定。

2026-07-08 P1 calibration sweep 集成复核：main runtime 已新增 P1 D4/D5 calibration sweep，可扫描二级高度、FOV、二级节点数量和 standoff，并在每个组合内运行多 seed D4/D5 stress。D4/D5 stress 链路已可把 D5 detect-to-global-track registration 产生的 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary coverage funnel 和 mobile gimbal metadata 写入统一 observation/report 流；D6 标准报告 bundle 已由 main runtime 自动生成，包含 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。因此 D5 当前没有“缺 registration helper 或缺标准报告输入合同”的 P1 接口缺口，剩余 P1 是真实 AirSim 多 seed 的阈值、外参、覆盖几何和二级/分布式降级 case 验收。

P0 状态：无当前运行级 P0 blocker。按 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`，D5 同步为“无阻塞 + 工程化 P0-B 硬化项”的口径：D5 安全合同仍保持为不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID；truth ID 只能作为离线评分标签。2026-07-09 已闭合 P0-B 主动重捕获、时序一致性和稳定窗口、calibration health 最小硬化范围，当前作为保持回归项；若后续测试或日志字段回退，则按 P0 backlog 重新打开并以表中验收口径补齐。P0-B 不引入 ReID、不做完整在线标定，也不让局部 tracker ID、友方身份或二级 cue 绕过 assignment 一致性。

| EVAL P0-B 项 | 当前状态 | 已闭合实现 | 验收口径 |
|---|---|---|---|
| 主动重捕获 | 已闭合，保持回归。 | `TerminalAssociator` 保留 per `resource_id + assigned_global_track_id` 历史；正常 gate 失败时用 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 主动寻找同一 assigned track。同一 MOT ID 可快速恢复；MOT ID 更换需先通过 bbox 历史和 stable window。 | `test_active_reacquire_recovers_assigned_track_from_search_window` 和 `test_reacquire_with_new_mot_id_requires_stable_bbox_history` 覆盖；恢复仍只输出当前 `assigned_global_track_id`，不创建、不改写、不换绑 `global_track_id`。 |
| 时序一致性和稳定窗口 | 已闭合，保持回归。 | 重捕获后加强 `candidate_cost_margin`、stable window、bbox area ratio、MOT history、measurement stale/OOSM 和 friend/version/authorization 阻断；`TerminalConsistencyTracker` 的 stable 判定使用明确 margin、稳定帧和 lock age/inf margin。 | `pytest -q research_modules/d5_terminal_association/tests` 覆盖；stale、assignment mismatch、friend conflict、duplicate risk 仍不得升级为 `locked`。 |
| 相机校准健康监测 | 已闭合，保持回归。 | `TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate/observation/result summary 输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。 | `test_decision_metadata_records_geometry_gate_and_measurement_age_fields` 与 `test_registration_logs_pose_source_bbox_area_and_offline_truth_without_using_truth_for_binding` 覆盖；P0-B 只监测/告警，不做在线标定。 |

P1 状态：以下是 EVAL 确认的 D5 P1 能力增强项。它们不覆盖上表 P0-B 的最小硬化范围，也不得改变 D5 不分配、不换绑 `global_track_id` 和 truth ID 仅离线评分的边界。

| EVAL P1 项 | 当前状态保留 | P1 后续边界 |
|---|---|---|
| YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定 | `YoloMotAdapter`、ByteTrack/BoT-SORT 请求路径、deterministic IoU fallback 和 multi-seed readiness helper 已存在，online adapter 已隔离 truth/global 字段，并记录 confidence、class id、bbox area/scale、tracker backend 和请求的 CPU/GPU budget。 | 用 AirSim 连续图像或 detector bbox stream 形成目标尺度、FOV、置信度阈值、tracker backend、CPU/GPU budget 实测和失败回退报告；tracker/local ID 仍只作为本地证据，不替代 `global_track_id`。 |
| IBVS/间歇可见性重捕获对照 | P0-B 已有投影/search-window 主动重捕获、stable window 和 handoff blocker metadata；D5 当前不实现视觉伺服控制器。 | 用 replay 或对照实验统计 lost/reacquire 时间下降，并保持误锁为 0；D5 只输出 `TerminalAssociation`/`IdentityClaim` 证据，不授权、不重新分配、不驱动 D7 绕过 gate。 |
| 多模态友方识别 replay adapter | `IdentityClaim` 抽象和 simulated Remote ID/OpenDroneID 风格字段已可表达 verified/stale/spoof/unverified，verified friend overlap 会触发 `hold`。 | 至少接入一个 replay adapter，将 Remote ID/MAVLink/DDS/AprilTag 等来源归一化为 `IdentityClaim`；未知或 stale 不升级目标，不绕过几何门控和 assignment 一致性。 |
| 完整相机在线标定/畸变校正 | `CameraModel` 已消费 K/R/t/dist，`projectPoints` 可使用畸变参数；`solvePnP`/calibration 仍未落地。 | 基于 replay/标定样本建立 2D-3D 对应、PnP/RANSAC、外参漂移估计和重投影误差验收；将 distortion 接入 projection/registration/误差报告并量化重投影误差下降，不替代上游 `GlobalTrack` 或 D3/D4 gate。 |

## 跨模块合同结论

- 与 D4：D5 输出的是 terminal visual evidence，不是分配结果。`CrossViewAssociation`、`TerminalConsistencySummary`、`DistributedTerminalAssociation`、`duplicate_terminal_lock_risk`、`hypothesis_only/hold/ambiguous` 原因和 `recommended_d4_action` 可作为 D4 CBBA/主动降级的风险加权输入；D5 不生成 `AssignmentPlan`，不选择主备资源，不改写、不新建、不换绑 `global_track_id`。
- 与 D7：D7 视觉 PNG 切换必须依赖 D5 `locked`、当前 D3/D4 `assigned_global_track_id` 一致、bbox 连续稳定、无友方冲突、无重复锁定风险，并通过 D4/D3 gate。D5 的 `visual_png_prelock_recommended` 或 `handoff_recommended` 只是前置证据；D7 仍需独立检查 LOS、相机状态、导引律、机动裕度、检测延迟和 terminal gate。
- 与 AirSim/runtime：在线 D5 不能使用 AirSim `object_id`、`actor_name`、actor truth ID 或离线 truth map 做关联、过滤、换绑或锁定。本轮二级节点输入先按 `simGetDetections` bbox/metadata 归一化，不启用 YOLO；若 AirSim `track_id`/`detection_id` 与 actor/truth 字段相同，D5 视为仿真真值别名而不是在线本地身份。truth ID 只允许在离线评估 metadata/evaluator 中计算 `terminal_lock_accuracy`、`locked_mismatch`、stress report 和测试断言。
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
| AirSim truth ID 隔离 | 已实现并测试。`airsim_cv_adapter.py` 明确忽略 `object_id/actor_name/truth_id/global_track_id`，并在 AirSim `track_id/detection_id` 重复 actor/truth 值时回退为相机作用域 detection ID；`test_detection_parser_ignores_airsim_truth_identity_fields_online()`、二级节点 sim detection 测试和离线 YOLO/ByteTrack adapter 测试覆盖；`airsim_geometry.py::evaluate_associations_offline()` 才读取 truth label。 | 在线关联只用 bbox、时间、相机几何、本地 ID、类别和置信度；本轮二级节点不启用 YOLO。 |
| `global_track_id` 不变式 | 已实现。`GlobalTrack` frozen；`TerminalAssociator` 记录输入 ID 并 `_assert_global_ids_unchanged()`；`TerminalObservationBus` 只按已有 `assigned_global_track_id` 分组。 | D5 只输出 evidence，不能成为分配权威。 |
| `IdentityClaim` 抽象 | 已实现模拟层。`identity.py::IdentityChecker.parse_claims()` 可把 Remote ID/OpenDroneID 风格 dict 和通用签名字段转为 `IdentityClaim`；verified friend overlap 触发 `hold`。 | 只做正向友方确认；未知不升级。 |
| 二级节点 cue | 已实现摘要/代价基线。`ReconImageCue` 有 producer、frame、global ID、center/bbox、confidence、scope、metadata；`associator.py` 校验 scope、age、frame 和 `reprojected_to_local_camera` 后给代价 bonus。 | cue 不能绕过授权、版本、友方冲突和 MOT 质量门槛。 |
| 跨视角重复锁定 | 已实现摘要层。`observation_bus.py::cross_view_associations()` 按既有全局 ID 汇总多资源支持，命名空间化 local ID，并输出 `duplicate_terminal_lock_risk`。 | 只上报给 D3/D4 仲裁，不解除锁定，不改计划。 |
| 完全分布式跨 peer 视觉假设 | 已实现 P0 metadata-only。`terminal_cross_view_fusion.py::TerminalCrossViewFusion` 消费 `DistributedVisualObservation`、`VisualTrackletSummary` 和 `PeerCameraState`，基于时间、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差 gating/cost，输出 `CrossPeerAssociationHypothesis` 与 `DistributedTerminalAssociation`。 | 使用 Hungarian；SciPy 不可用时退回纯 Python 最小代价唯一匹配。missing/stale `global_track_id`、重复锁定、友方冲突或 local/global ID 冲突不会输出 `locked`。 |
| 一致性摘要 | 已实现。`consistency.py::TerminalConsistencyTracker` 输出 `TerminalConsistencySummary`，包含 lock age、连续 ambiguous/hold/reacquire、丢锁/重捕获、重复锁定风险、cross-view support 和 `recommended_d4_action`。2026-07-07 已将连续窗口 key 固化为 `resource_id + assigned_global_track_id`，避免同一 assignment pair 的滚动 plan version 更新清空 D4 需要的连续视觉状态。 | 是 D4/D6 advisory summary，不替代 D4 仲裁；D5 仍不因连续丢锁触发降级。 |
| 二级计划 2v2 语义 | 已实现测试覆盖。`test_airsim_cv_2v2_secondary_plan.py` 覆盖二级 plan 输入后只锁定 `assigned_global_track_id`、locked mismatch 只进入问题统计、不改写 ID、友方冲突阻断。 | 2v2 是测试语义，不是算法规模上限。 |
| N-v-N stress 指标 | 已实现 D5 helper。`compute_terminal_stress_metrics()` 与 `summarize_degradation_case()` 输出 per-camera count、multi-target FOV、cross-view overlap、duplicate risk、lock accuracy、ambiguous count 和三类 degradation evidence。 | 5v5 只是默认 stress baseline；`AirSimCVScenarioSpec` 支持传入不同数量。 |
| Multi-seed calibration readiness | 已实现 D5 helper。`summarize_multiseed_calibration_readiness()` 对每个 seed 的 `TerminalObservation`/`CrossViewAssociation` 做字段覆盖审计，输出 required/recommended missing fields、AirSim/YOLO source/backend counts、offline truth label count、measurement age、bbox stability、handoff advisory、duplicate/friend conflict evidence 计数。 | 只做被动审计；truth label 只从离线 metadata 计数，不参与在线关联或换绑。 |
| 二级覆盖/漏斗诊断 | 已实现 D5 helper。`summarize_secondary_visual_coverage_funnel()` 对 replay frame、`TerminalObservation` 和 `CrossViewAssociation` 输出单二级相机 full-view 率、二级网络联合 full-view 率、每帧可见目标数、覆盖比例均值/最小值，以及 detect/local-or-recon/terminal/cross-view/multi-support 漏斗计数和断点原因。 | offline target label 只用于“看见目标”覆盖统计；形成全局支持仍必须依赖已有 `TerminalAssociation.assigned_global_track_id` 和 `CrossViewAssociation`。 |
| Detect-to-global-track registration | 已实现 D5 helper。`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 binding/`Assignment`、per-camera `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 选择注册对，并保留 gated candidates 供 JPDA-compatible 下游使用。输出 `DetectToGlobalTrackCandidate`、`TerminalObservation`、即时 `CrossViewAssociation`、稳定 `stable_cross_view_associations` 和 reason counts。P1 已补齐 `camera_pose_source`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`bbox_area_px`、离线 `offline_truth_global_id`、bbox 自适应像素协方差和 3 帧 2 次通过的稳定注册窗口。 | 只增加对既有 `global_track_id` 的支持证据；不新建、不重绑、不授权，不让 YOLO/MOT tracker ID 或 AirSim truth/actor ID 替代全局 ID。main P1 sweep 已可消费该证据，后续重点是 AirSim 真实 camera pose 接线、多 seed 阈值、二级覆盖策略和 `stability_window_failed` 验收。 |
| 机动高空侦察云台 cue evidence | 已实现 D5 DTO/summary 字段。`ReconImageCue`、`CrossViewAssociation.metadata` 和 `SecondaryVisualCoverageFunnelSummary.metadata` 可携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。测试覆盖固定俯视不足时移动云台补足二级网络联合覆盖。 | 只证明证据字段和 coverage/cross-view 汇总；真实云台控制、传感器指向闭环和多 seed D6 趋势分析仍在 D5 外。 |
| 视觉 PNG handoff 建议 | 已实现 advisory metadata。`visual_handoff.py::annotate_visual_png_handoff()` 在已有 `TerminalAssociation` 上附加 bbox 稳定、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和 maneuver margin 等建议。 | D5 不决定导引律；D7/main 仍需独立 gate；stale measurement age 和 missing LOS 会阻断建议。 |
| P1 calibration sweep / D6 bundle 输入合同 | 已实现接口层状态。main runtime 已可在 P1 sweep 中消费 D5 registration observation、secondary funnel 和 mobile gimbal metadata，并自动调用 D6 输出标准 CSV/JSON/Markdown bundle。 | D5 不运行 AirSim、不调度 sweep、不生成系统报告；后续验收重点是实际多 seed 数据是否提升注册率、覆盖率和降级 case 质量。 |

已实现项的安全边界：

- `locked` 只表示“当前分配 ID 的视觉候选被保守支持”，不是处置授权。
- `hypothesis_only` 只表示“peer metadata 之间可能支持同一视觉目标”，没有 current `assigned_global_track_id` 时不能升级为 `locked`。
- 重复锁定、友方冲突、stale ID、global/local ID 冲突都只输出风险和仲裁建议，不在 D5 内解除冲突。

## 部分实现

| 能力项 | 已有部分 | 未完成部分 | 未完成原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|
| OpenCV calibration / 畸变使用 | `CameraModel` 可携带 `dist_coeffs`，`projectPoints` 会消费。 | 没有 `calibrateCamera`、标定图像流程或重投影误差报告。 | 当前 AirSim/runtime 可直接给相机参数，但 2026-07-08 复测显示覆盖/注册瓶颈需要更强外参和重投影误差审计。 | 标定图像、棋盘/AprilTag 角点、畸变模型选择、误差验收阈值。 | P1/P2 |
| OpenCV `solvePnP` | 文档已列为推荐链路。 | 代码未调用 `cv2.solvePnP` 或 PnP RANSAC。 | 当前 D5 假设上游提供 `CameraModel.R/t`，但 multi-camera cross-view registration 需要可审计的 2D-3D 外参校核。 | 稳定 2D-3D 对应、PnP RANSAC 策略、外参漂移判据、离线标定样本。 | P1/P2 |
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
| 机动高空侦察云台真实 pointing telemetry | 验证 `cue_position_ned`、`look_at_ned`、pointing error 和 gimbal track error 的真实性 | main/AirSim runtime 或真实云台控制日志 |
| D3/D4/main runtime 消费 D5 advisory evidence | 重复锁定仲裁、主动降级闭环 | D3/D4/main；D5 侧 evidence 字段已可输出 |
| D6/main 统一记录 terminal record/event | terminal lock accuracy、locked mismatch、cue 依赖、handoff 建议评估 | D6/main；D5 侧 geometry/consistency/handoff metadata 已可输出 |

## 下一步优先级

### P1 已补齐（D5 侧）

| 能力 | 当前证据 | 边界 |
|---|---|---|
| Geometry log fields | `TerminalAssociation.metadata`、`CandidateBreakdown.to_log_dict()` 和 `GeometricAssociationResult.to_log_records()` 输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair 与 duplicate-risk advisory。 | D5 只产出字段；main/D6 若要落盘 JSONL/CSV 需在其 owned paths 接入。 |
| `TerminalConsistencySummary` 连续窗口 | `TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口；`assignment_version` 仅进入摘要审计。 | advisory summary，不触发降级，不生成分配计划。 |
| AirSim truth ID 在线隔离 | AirSim/YOLO/ByteTrack adapter 忽略 `object_id`、`actor_name`、`truth_id`、`true_global_track_id`、`global_track_id` 等真值/全局字段；sim detection adapter 还会过滤与 actor/truth 字段同值的 `track_id/detection_id`。truth 只进入离线 evaluator/metadata。 | 在线关联只消费 bbox、时间、相机几何、本地 ID、类别和置信度；二级节点本轮使用 `simGetDetections` bbox/metadata，不默认 YOLO。 |
| YOLOv8 frame adapter | `YoloMotAdapter.process_frame()` 将图像帧或 mock detector 输出转为命名空间化 `LocalVisualTrack`；原生 ByteTrack/BoT-SORT 不可用时 `IouFallbackTracker` 保持 deterministic local ID 连续性，并在 metadata 中标明 `tracker_backend`。 | 真实 AirSim frame stream 接入、部署参数和多 seed 标定仍由 main/runtime 完成。 |
| Multi-seed readiness helper | `summarize_multiseed_calibration_readiness()` 已输出每个 seed 是否具备 local bbox/timestamp、geometry gate log、measurement age、AirSim detect source、YOLO/MOT backend、offline truth、bbox/handoff advisory 和 duplicate/friend conflict evidence 字段。 | D5 只审计字段覆盖；main/D6 仍负责实际跨 seed 落盘、聚合图表和阈值调参。 |
| Secondary coverage/funnel helper | `summarize_secondary_visual_coverage_funnel()` 已输出 `secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、每相机/网络每帧可见目标数、覆盖比例均值/最小值、detect 到 multi-support 漏斗计数，以及 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点。 | D5 只做诊断汇总；main/D4/D6 仍负责从 AirSim replay frames 调用、落盘和仲裁。 |
| Detect-to-global-track registration helper | `register_local_visual_tracks_to_global_tracks()` 已输出 `DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`、`detect_registration_reject_reasons`、registration candidates、registered observations、即时 cross-view support、稳定 `stable_cross_view_associations` 和 `registered_to_global_track` 成功状态；timestamp、measurement age、covariance/projection covariance、缺绑定、stale binding/cue、`projection_invalid`、geometry gate、稳定窗口失败和 offline-only truth 均有记录。 | D5 helper 已完成，main P1 sweep/D6 bundle 已有消费口径；后续是 AirSim camera pose metadata、多 seed gate、外参和降级 case 校准。 |
| Mobile recon gimbal cue evidence | `ReconImageCue` 与 coverage/cross-view summaries 已携带 `mobile_high_recon`、`mobile_recon_gimbal`、radar/GlobalTrack cue source、NED look-at、云台 metadata 和 pointing/track error；测试证明固定俯视不足时移动云台可改善二级网络联合覆盖证据。 | D5 不运行云台控制，也不使用 actor/truth ID 绑定；main/D6 已能接收报告字段，后续需真实 telemetry 多 seed 趋势分析。 |
| P1 calibration sweep / D6 bundle 输入合同 | main runtime 可运行 P1 D4/D5 calibration sweep，D6 自动生成 records/summary/report bundle。 | D5 不负责 AirSim 启停和报告生成；只维护 evidence DTO、helper、truth 隔离和 `global_track_id` 不变式。 |
| D4 evidence | `CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 已可作为 D4/D6 evidence。 | D5 不仲裁、不授权、不创建或换绑 `global_track_id`。 |
| D7 visual PNG 前置证据 | `annotate_visual_png_handoff()` 输出 handoff/prelock、gate pass、blockers、measurement age、LOS rate、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend/duplicate risk、unstable bbox、stale measurement age、missing LOS 会阻断。 | D5 不决定导引律，D7/main 仍需独立 terminal gate。 |

### P0-B 已闭合

| 优先级 | 任务 | 验收结果 |
|---|---|---|
| P0-B | 主动重捕获。 | 已实现 GlobalTrack 预测投影 + bbox/MOT 历史 + search window 的 assigned-track reacquire；测试覆盖遮挡后同一 MOT ID 快速恢复、MOT ID 更换需稳定窗口，且不改写 `global_track_id`。保持回归；若恢复逻辑退化为最近目标或 truth/local tracker ID 绑定，则作为 P0 backlog 重开。 |
| P0-B | 时序一致性和稳定窗口。 | 已加强 candidate margin、stable window、bbox/MOT history、stale/OOSM 和保守 hold/ambiguous 阻断；`TerminalConsistencyTracker` stable 判定不再把任意正 margin 视为稳定。保持回归；若 stable window、margin 或 stale/OOSM 阻断缺失，则作为 P0 backlog 重开。 |
| P0-B | 相机校准健康监测。 | 已输出 projection valid、reprojection error、camera pose source/trust、calibration health、drift warning、registration health counts 和误差摘要，供 D6/main 直接消费。保持回归；若缺失 reprojection error、pose source、calibration health 或 drift warning，则作为 P0 backlog 重开。 |

### 剩余 P1/P2

| 优先级 | 任务 | 验收建议 |
|---|---|---|
| P1 | YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定。 | 用 AirSim 连续 RGB/PNG 或外部 detector bbox stream 调用 `YoloMotAdapter.process_frame()`，跨 seed 标定目标尺度、FOV、confidence、class id 分布、bbox scale、tracker backend、CPU/GPU budget 实测、`gate_chi2`、candidate margin、bbox stability、handoff range、measurement age、LOS availability、ambiguity 和 quality 阈值，并报告 `locked_mismatch`、false handoff、ambiguous/reacquire 抖动和 `terminal_id_switch_count`。 |
| P1 | IBVS/间歇可见性重捕获对照。 | 基于 replay/对照实验评估 IBVS 或间歇可见性切换策略能否降低 lost/reacquire 时间；验收必须保持误锁为 0，且 D5 只产出 `TerminalAssociation`/`IdentityClaim` 证据，不重新分配、不授权、不本地换绑 `global_track_id`。 |
| P1 | 多模态友方识别 replay adapter。 | 将至少一个 Remote ID/MAVLink/DDS/AprilTag replay 来源归一化为 `IdentityClaim`，输出 verified/stale/unverified/spoof 状态；未知或 stale 不升级目标，verified friend 仍只触发保守阻断。 |
| P1 | 完整相机在线标定/畸变校正。 | 在 replay/标定样本中接入 2D-3D 对应、`solvePnP`/PnP RANSAC、外参漂移估计和重投影误差验收；将 `CameraModel.dist_coeffs` 从可消费字段推进为完整 projection/registration/误差报告链路，量化畸变校正前后的重投影误差下降。 |
| P1 | 二级节点几何/覆盖策略。 | 基于 `p1_d4d5_registration_calibration_runtime_v2_20260708*` 继续调整高空侦察节点站位、视场/分辨率、look-at 扫描/子簇策略和 full-view 判据；当前 `projection_valid_rate=1.0` 且 cross-view association 已非 0，验收重点是提高 full-view mean≈0.048 和 coverage mean≈0.771，降低 `not_all_targets_visible` / `network_union_incomplete`，并减少降级 case not-registered 35/35。 |
| P1 | Multi-camera cross-view registration 多 seed 标定。 | D5 helper、main P1 sweep 和 D6 bundle 输入合同已完成；后续用真实 sweep 数据校准 `GlobalTrack`、D2/D3 binding、per-camera `K/R/t`、timestamp/covariance、二级 `LocalVisualTrack` 和 gate/margin，落盘并分析 `registered_to_global_track` / `projection_invalid` / `geometry_gate_rejected` / `stability_window_failed` 等 reasons，验收 `degrade_to_secondary` / `degrade_to_distributed` 不再停留在 offline visible-only。 |
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
- `research_modules/d5_terminal_association/src/d5_terminal_association/cross_view_registration.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/consistency.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_terminal_association.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_5v5_evidence.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_2v2_secondary_plan.py`
- `research_modules/d5_terminal_association/tests/test_geometric_registration_validation.py`
- `research_modules/d5_terminal_association/tests/test_terminal_observation_bus.py`
- `research_modules/d5_terminal_association/tests/test_distributed_cross_view_fusion.py`
- `research_modules/d5_terminal_association/tests/test_cross_view_registration.py`
- `research_modules/d5_terminal_association/tests/test_terminal_consistency.py`
- `research_modules/d5_terminal_association/tests/test_visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_yolo_mot_adapter.py`
