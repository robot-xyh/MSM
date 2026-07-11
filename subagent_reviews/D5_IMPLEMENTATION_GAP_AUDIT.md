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

2026-07-08 AirSim 机动高空侦察节点复测只保留为历史基线：`p1_d4d5_mobile_recon_20260708_055948*` 证明 D5 能识别机动云台/cue metadata，`p1_d4d5_registration_calibration_runtime_v2_20260708*` 的单 seed 结果证明投影和 cross-view 不再全为 0；其中降级 case not-registered 35/35 已被后续 60-case sweep 改写，不能作为当前缺口。

2026-07-10 60-case registration 结论：`research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710` 覆盖 5v5、10 seeds、50/200 m、三类 case，共 60 个 case。D6 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0；平均 `projection_valid_rate=1.0`、stable registration `92.233`、cross-view association `4.417`。基础 detect-to-global registration 缺口已闭合。剩余瓶颈是网络同帧全目标覆盖率均值 `0.0231`、平均覆盖率 `0.7059` 和稳定窗口失败。D5 侧逐决策证据与 episode 聚合的接口分离已由 `SecondaryFrameAssociationEvidence` 闭合；main/D4 是否在真实 decision tick 使用它仍是跨模块 P1。registration 成功不能替代唯一性、友方冲突、时效、版本或 D7 安全门控。

2026-07-10 本轮 D5 P1 补齐：`build_secondary_frame_association_evidence()` 仅消费单个同步 frame 的 camera/network coverage 与 registration candidate，输出 D4 `TerminalAssociationSummary` 同名字段，并保留 frame、measurement/arrival timestamp、detector/tracker backend、calibration health、ignored historical candidate count。混合 frame/timestamp fixture 会拒绝，在线 metadata 不传播 AirSim actor/truth 字段。`YoloMotAdapter` 已补实际 tracker selection、native/fallback/unavailable 状态、wall latency、预算比较、observed device、camera-local continuity 和离线 detector recall/precision/FN/FP；离线 bbox 不影响在线跟踪。单测覆盖 5v5 多相机、交叉、短时遮挡和跨 frame 防回填，D5 全量为 `101 passed`。本机 `best.pt` 与 Ultralytics 8.4.71 可加载推理；黑帧无目标时 ByteTrack/BoT-SORT 无 ID 并明确回退，该烟测只验证部署入口，不代表真实目标质量。

2026-07-11 M-to-N 联盟视觉完成汇总已闭合：新增 `CoalitionVisualSummary`、纯函数 `summarize_coalition_visual_completion()` 和 bus 便捷接口。hybrid 默认要求全部 active primary 当前锁定并各自连续至少 2 帧，standby reserve 的本资源/本相机几何匹配只输出 `reserve_ready_resource_ids`，不授权视觉 PNG，也不补足缺失 primary。接口继续阻断 plan/coalition version conflict、联盟外 lock、over-demand、单资源多 local lock 和跨 resource/camera bbox 借用，且只回显 D3/D2 已有 `assigned_global_track_id`。真实 AirSim 连续有效检测与联盟完成证据仍未闭合，不能用 DTO 单测替代 runtime 验收。

2026-07-11 AirSim full-flow 历史污染缺口已在 D5 闭合：`cross_view_associations()` 新增可选 `as_of_timestamp/max_age_s/plan_id/plan_version`。scope 模式只消费 freshness window 内当前 plan/version 的 observation，并按 resource 选择最新 timestamp，避免旧帧 local lock、旧 plan 多资源 lock 累积为当前 duplicate；同帧当前 plan 的未授权多资源 lock 仍保持 duplicate，合法 coalition 仍输出 `planned_cooperative_lock`。无参数调用保持旧离线行为。四类专项回归及全量 `127 passed`；main/runtime 接线不属于 D5 ownership，本任务未修改。

2026-07-08 P1 calibration sweep 集成复核：main runtime 已新增 P1 D4/D5 calibration sweep，可扫描二级高度、FOV、二级节点数量和 standoff，并在每个组合内运行多 seed D4/D5 stress。D4/D5 stress 链路已可把 D5 detect-to-global-track registration 产生的 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary coverage funnel 和 mobile gimbal metadata 写入统一 observation/report 流；D6 标准报告 bundle 已由 main runtime 自动生成，包含 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。因此 D5 当前没有“缺 registration helper 或缺标准报告输入合同”的 P1 接口缺口，剩余 P1 是真实 AirSim 多 seed 的阈值、外参、覆盖几何和二级/分布式降级 case 验收。

2026-07-10 2v2 smoke 复核：`outputs/p1_gap_closure_2v2_smoke_20260710` 中 2/2 资源对完成 `collision_intercept`，pair summary 的 D5 状态均为 `locked`；D7/main 因 `bbox_near_image_edge` 拒绝视觉接管 9 次、覆盖 2 个资源对，仅 2 个控制记录允许 terminal switch。安全上该结果正确，因为 D5 lock 没有绕过 D7 独立 camera/LOS/maneuver gate；工程上仍需 P1 标定边缘裕量、连续边缘帧、相机指向和 handoff 抖动。

P0 状态：无 blocker，端到端 AirSim runtime truth 隔离 P0 已闭合。D5 已闭合主动重捕获、时序/稳定窗口、calibration health、active reacquire 友方声明复检和 detection category/truth 隔离。main hotfix 为 builtin detect 增加按 camera 分区的匿名 bbox tracker，ID 不含 actor 名、仅由 bbox IoU/中心距离维持连续性并在 episode setup reset；actor 名只留在 offline truth metadata。episode bus 在线 D5 路径不读取 `object_id`，truth map 只用于决策后的离线评分；intercept 注入及 D4/D5 fallback 的 actor-name local ID 也已清理。验收证据为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`：三类 case 均 connected、各 5 帧，local/detection ID actor 泄漏为 0，匿名 ID history 达 5，所有 actor 名记录均为 `offline_truth_only=True`，每类 cross-view association 均为 4。D5 安全合同保持为不分配、不授权、不改写 `global_track_id`，且不对任意既有 tracker ID 做猜测式重写。

| EVAL P0-B 项 | 当前状态 | 已闭合实现 | 验收口径 |
|---|---|---|---|
| 主动重捕获 | 已闭合，保持回归。 | `TerminalAssociator` 保留 per `resource_id + assigned_global_track_id` 历史；正常 gate 失败时用 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 主动寻找同一 assigned track。同一 MOT ID 可快速恢复；MOT ID 更换需先通过 bbox 历史和 stable window。 | `test_active_reacquire_recovers_assigned_track_from_search_window` 和 `test_reacquire_with_new_mot_id_requires_stable_bbox_history` 覆盖；恢复仍只输出当前 `assigned_global_track_id`，不创建、不改写、不换绑 `global_track_id`。 |
| Active reacquire 友方声明复检 | 已闭合，保持回归。 | active reacquire candidate 复用 `IdentityChecker.friend_conflict_state()`；verified/stale/unverified/spoof-suspected 重叠均强制 `hold`，输出顶层与 candidate/search-window `friend_conflict_state` 和 reason。 | `test_active_reacquire_friend_claims_force_auditable_hold` 覆盖同一/新 MOT ID 和四类 auth state；任何冲突不得 `locked`，不得改写 `global_track_id`。 |
| Detection category/truth 隔离 | 已闭合，保持回归。 | AirSim、offline YOLO 和 frame YOLO record 只从显式 detector 类别字段得到在线类别；D5 adapter 过滤 actor/truth alias。main builtin detect 使用匿名 camera-local bbox tracker，intercept/fallback local ID 不嵌 actor 名。 | D5 回归、targeted runtime test 和 `outputs/p0_truth_isolation_smoke_20260710` 真实三 case 验收均通过；持续要求 offline truth 不进入 D5 cost/binding。 |
| 时序一致性和稳定窗口 | 已闭合，保持回归。 | 重捕获后加强 `candidate_cost_margin`、stable window、bbox area ratio、MOT history、measurement stale/OOSM 和 friend/version/authorization 阻断；`TerminalConsistencyTracker` 的 stable 判定使用明确 margin、稳定帧和 lock age/inf margin。 | `pytest -q research_modules/d5_terminal_association/tests` 覆盖；stale、assignment mismatch、friend conflict、duplicate risk 仍不得升级为 `locked`。 |
| 相机校准健康监测 | 已闭合，保持回归。 | `TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate/observation/result summary 输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。 | `test_decision_metadata_records_geometry_gate_and_measurement_age_fields` 与 `test_registration_logs_pose_source_bbox_area_and_offline_truth_without_using_truth_for_binding` 覆盖；P0-B 只监测/告警，不做在线标定。 |

P1 状态：以下是 EVAL 确认的 D5 P1 能力增强项。它们不覆盖上表 P0-B 的最小硬化范围，也不得改变 D5 不分配、不换绑 `global_track_id` 和 truth ID 仅离线评分的边界。

| EVAL P1 项 | 当前状态保留 | P1 后续边界 |
|---|---|---|
| YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定 | `YoloMotAdapter`、ByteTrack/BoT-SORT 请求路径、deterministic IoU fallback 和 multi-seed readiness helper 已存在；6 episode x 2 帧 AirSim 冒烟已接通 online truth 隔离、offline bbox 评分和延迟事件。当前 `accepted_detection_count=0`，native ByteTrack 回退 `iou_fallback`，故仅接口闭合。 | 先校正 AirSim offline truth bbox、目标像素尺度、FOV/相机指向、class map 和 confidence；再以非零 accepted detection、native tracker ID、跨帧 continuity、IDSW/IDF1、遮挡恢复和 CPU/GPU 多 seed 分布作为质量闭合条件。tracker/local ID 仍只作为本地证据，不替代 `global_track_id`。 |
| 多相机 detector/tracker 状态隔离 | 已闭合，保持回归。`YoloMotAdapter` 按 `(resource_id, camera_id)` 持久化 fallback tracker 和 native model/tracker，并提供 `reset_stream()` / `reset_all_streams()`。metadata 记录 stream key、实际 backend 和状态作用域。 | main 必须保持 stream key 稳定并在 episode 边界 reset；native 每 stream 独立模型会增加内存/显存和首帧加载时延，但不得为节省资源而静默共享 `persist=True` tracker state。 |
| IBVS/间歇可见性重捕获对照 | P0-B 已有投影/search-window 主动重捕获、stable window 和 handoff blocker metadata；D5 当前不实现视觉伺服控制器。 | 用 replay 或对照实验统计 lost/reacquire 时间下降，并保持误锁为 0；D5 只输出 `TerminalAssociation`/`IdentityClaim` 证据，不授权、不重新分配、不驱动 D7 绕过 gate。 |
| 多模态友方识别 replay adapter | `IdentityClaim` 抽象和 simulated Remote ID/OpenDroneID 风格字段已可表达 verified/stale/spoof/unverified，verified friend overlap 会触发 `hold`。 | 至少接入一个 replay adapter，将 Remote ID/MAVLink/DDS/AprilTag 等来源归一化为 `IdentityClaim`；未知或 stale 不升级目标，不绕过几何门控和 assignment 一致性。 |
| 完整相机在线标定/畸变校正 | `CameraModel` 已消费 K/R/t/dist，`projectPoints` 可使用畸变参数；`solvePnP`/calibration 仍未落地。 | 基于 replay/标定样本建立 2D-3D 对应、PnP/RANSAC、外参漂移估计和重投影误差验收；将 distortion 接入 projection/registration/误差报告并量化重投影误差下降，不替代上游 `GlobalTrack` 或 D3/D4 gate。 |
| 视觉接管图像边缘裕量 | 2v2 smoke 已记录 `bbox_near_image_edge` 9 次且覆盖 2 个资源对；D7 独立 gate 保守拒绝，未形成安全绕过。 | 跨 seed 统计 bbox 到边界的归一化最小裕量、连续边缘帧、相机指向误差和 D5 handoff 到 D7 reject 的转移；可增强 D5 advisory metadata，但不得降低 D7 camera/LOS/maneuver gate。 |
| 外参漂移与时间同步鲁棒性 | 已携带 K/R/t/dist、measurement/arrival timestamp、measurement age 和 calibration-health 字段；尚无系统扰动标定。 | 注入姿态/位置外参漂移及时间延迟/抖动，统计重投影误差、门控拒绝、误锁和恢复时间；在线逻辑不得读取 truth 位姿补偿。 |
| D4 逐决策 evidence 合同 | D5 已输出 CrossView/Consistency/registration evidence；当前 60-case 报告主要证明 episode 聚合可用。 | 每个 D4 决策 tick 携带 stable/not-registered count、timestamp/age、camera/resource scope、threshold version 和 conflict reasons；D5 只提供证据，不触发降级。 |
| 遮挡/交叉和 MOT ID 变化 | 已有 active reacquire 与 stable window 单元能力；缺真实多相机连续图像压力标定。 | 覆盖同视角交叉、跨视角部分重叠、短时全遮挡和 local ID 变化；候选不唯一时保持 `ambiguous/hold/reacquire`，不得本地换绑全局 ID。 |

## 跨模块合同结论

- 与 D4：D5 输出的是 terminal visual evidence，不是分配结果。`CrossViewAssociation`、`TerminalConsistencySummary`、`DistributedTerminalAssociation`、`duplicate_terminal_lock_risk`、`hypothesis_only/hold/ambiguous` 原因和 `recommended_d4_action` 可作为 D4 CBBA/主动降级的风险加权输入；D5 不生成 `AssignmentPlan`，不选择主备资源，不改写、不新建、不换绑 `global_track_id`。
- 与 D7：D7 视觉 PNG 切换必须依赖 D5 `locked`、当前 D3/D4 `assigned_global_track_id` 一致、bbox 连续稳定、无友方冲突、无重复锁定风险，并通过 D4/D3 gate。D5 的 `visual_png_prelock_recommended` 或 `handoff_recommended` 只是前置证据；D7 仍需独立检查 LOS、相机状态、导引律、机动裕度、检测延迟和 terminal gate。
- 与 AirSim/runtime：在线 D5 不能使用 AirSim `object_id`、`actor_name`、actor truth ID 或离线 truth map 做关联、过滤、换绑或锁定。D5 adapter 过滤 actor/truth alias；main builtin detect 输出匿名 camera-local ID，episode bus 在线路径不读取 `object_id`，intercept/fallback 不生成 actor-name local ID。真实三 case 已完成验收，truth ID 只允许在离线 metadata/evaluator 中计算 `terminal_lock_accuracy`、`locked_mismatch`、stress report 和测试断言。
- 与规模参数：2v2 与 5v5 只是 baseline 和 stress scenario 名称。D5 算法按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表、`TerminalObservation[]` 或 peer DTO 数组长度运行，不写死资源数或目标数。

## 已实现

| 能力项 | 当前状态与证据 | 说明 |
|---|---|---|
| `LocalVisualTrack` | 已实现。`models.py` 定义本地轨迹；`airsim_cv_adapter.py::local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `yolo_mot_adapter.py::YoloMotAdapter.process_frame()` 可从 AirSim bbox、离线 schema 或图像帧 detector/tracker 输出生成中心点、bbox、质量、类别和 `mot_history_length`。 | 只标准化本地检测/MOT 输出，不携带 truth/global ID；tracker ID 只能是本地 ID。 |
| `TerminalAssociation` | 已实现。`associator.py::TerminalAssociator.decide()` 只评估 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`、候选代价、友方冲突、cue 使用标记和 per-pair geometry log metadata。 | 不是重分配器，不会选择另一个全局 ID 作为新分配。 |
| OpenCV `projectPoints` / 几何门控 | 已实现单相机版。`geometry.py::_project_pixel()` 优先调用 `cv2.projectPoints`，不可用时退回针孔公式；`project_track()` 传播协方差，`mahalanobis_d2()` 做像素马氏距离。 | 只消费已有 `CameraModel.K/R/t/dist_coeffs`，不估计标定参数。 |
| AirSim 相机几何 adapter | 已实现模块内验证辅助。`airsim_geometry.py` 提供 FOV 到 K、AirSim quaternion 到 OpenCV camera rotation、`camera_model_from_airsim_camera_info()`、`associate_tracks_to_detections_geometrically()` 和 `GeometricAssociationResult.to_log_records()`。 | 用于 D5 几何验证；不调用 AirSim API，也不依赖 object truth；main/D6 仍需接入实际日志 sink。 |
| AirSim `simGetDetections` bbox adapter | 已实现 dry-run 适配。`airsim_cv_adapter.py` 接受 `box2D`、`bbox_xyxy`、`xyxy` 等 schema，发布到 `TerminalObservationBus`。 | 不导入 AirSim；真实采集由 main/runtime 负责。 |
| YOLOv8 + ByteTrack/BoT-SORT adapter | 已实现模块 adapter。`YoloMotAdapter` 默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许覆盖；可请求 ultralytics ByteTrack/BoT-SORT，缺依赖/权重/原生 tracker 时返回 `unavailable` 或使用确定性 IoU fallback。测试覆盖 mock 输出、truth/global 隔离、交错 stream、episode reset、native 隔离和 native-to-fallback。 | D5 不采集 AirSim 图像流、不管理 GPU/CPU 部署、不把 tracker ID 替代 `global_track_id`；真实 runtime 接线和 episode reset 调用归 main。 |
| AirSim truth ID 隔离 | 已实现并完成真实 AirSim 验收。D5 adapter 过滤 truth alias；main 匿名 camera-local bbox tracker 和 episode bus 在线/离线分流已接通。 | `outputs/p0_truth_isolation_smoke_20260710` 三类 case 的 ID、history、offline truth flag 和 cross-view evidence 均满足关闭条件；保持回归。 |
| `global_track_id` 不变式 | 已实现。`GlobalTrack` frozen；`TerminalAssociator` 记录输入 ID 并 `_assert_global_ids_unchanged()`；`TerminalObservationBus` 只按已有 `assigned_global_track_id` 分组。 | D5 只输出 evidence，不能成为分配权威。 |
| `IdentityClaim` 抽象 | 已实现模拟层。`identity.py::IdentityChecker.parse_claims()` 可把 Remote ID/OpenDroneID 风格 dict 和通用签名字段转为 `IdentityClaim`；verified friend overlap 触发 `hold`。 | 只做正向友方确认；未知不升级。 |
| 二级节点 cue | 已实现摘要/代价基线。`ReconImageCue` 有 producer、frame、global ID、center/bbox、confidence、scope、metadata；`associator.py` 校验 scope、age、frame 和 `reprojected_to_local_camera` 后给代价 bonus。 | cue 不能绕过授权、版本、友方冲突和 MOT 质量门槛。 |
| 跨视角重复锁定 | 已实现摘要层。`observation_bus.py::cross_view_associations()` 按既有全局 ID 汇总多资源支持，命名空间化 local ID，并输出 `duplicate_terminal_lock_risk`；在线可用 timestamp freshness、plan identity 和 per-resource latest-frame scope，避免历史污染。 | 无参数保留全历史离线兼容；main 在线必须传当前 frame timestamp、freshness 和当前 plan ID/version。D5 只上报给 D3/D4 仲裁，不解除锁定，不改计划。 |
| M-to-N 联盟视觉完成汇总 | 已实现。`coalition_visual.py::summarize_coalition_visual_completion()` 和 `TerminalObservationBus.coalition_visual_summary()` 读取 D3 coalition bindings 与当前/历史 association，输出 primary 完成、reserve readiness、consensus、稳定帧、计划内协同 lock 和冲突字段。 | reserve readiness 不授权视觉 PNG；二级 cue/其他相机 bbox 不替代本机 lock；真实 AirSim 连续检测仍是 P1 验收缺口。 |
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
| MOT 输入质量 | 已按 `(resource_id, camera_id)` 隔离并持久化 Ultralytics native tracker 或 IoU fallback，输出 `mot_history_length`、camera-local continuity、backend、latency 和 reset API。 | 尚未在真实 AirSim 多 seed 中计算 IDF1/IDSW、遮挡恢复和资源预算分布。 | D5 模块 tracker 状态已实现，真实图像质量与 D6 指标尚缺。 | 连续 AirSim 图像、离线 truth evaluator、GPU/CPU 环境和多 seed 结果。 | P1 |

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

2026-07-11 回归补充：D5 已修复 `offline_truth_detections=tuple[tuple[x1,y1,x2,y2], ...]` 被通用归一化递归拆成标量的问题。离线 evaluator 现稳健支持单 bbox、多 bbox、dict/object detection，并对畸形输入给出明确错误；解析结果仍仅用于 recall/precision/FN/FP/IoU，不能进入在线 MOT 或 `global_track_id` binding。真实 AirSim 多 seed 质量标定仍为 P1，不因该接口修复而宣称闭合。

2026-07-11 真实证据补充：三组既有 D4/D5 回归均形成 `cross_view_association_count=4`，稳定注册约 19-61，但二级同帧全目标覆盖仍不足。`p1_yolov8_bytetrack_smoke_fixed_20260711` 完成 6 episode、每个 2 帧，验证 AirSim RGB -> YOLOv8 -> tracker adapter -> D5 event、在线 truth 隔离和 offline bbox-only 评分合同均可运行；这关闭的是接口 P1。质量 P1 未关闭：当前几何下 `accepted_detection_count=0`，AirSim offline truth boxes 多数为 0，原生 ByteTrack 因无 track ID 回退 `iou_fallback`，延时多数约 38-49 ms、首轮约 197 ms。没有非零检测就不能声明 detector recall、native MOT continuity、IDSW/IDF1 或 cross-view registration 已由 YOLO 路径验证。

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

### 真实 AirSim M=5、N=2 检测/几何专项（2026-07-11）

证据 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 表明 5 主相机和 2 二级相机均有有效 Scene 图像，但 AirSim built-in detection 基本断流：9 帧 episode 的前 8 帧所有相机 count=0，末帧仅部分 episode 的 `Secondary_Recon_1` count=1。full-flow D5 为 32 `reacquire` + 4 `ambiguous` + 0 `locked`，因此本轮不能作为 M-to-N cooperative lock 成功证据。

D5 模块内解析/几何复核通过：记录 bbox 使用正确 `Secondary_Recon_1:0` 外参时对 `T002` 的重投影误差约 0.09 px，并正确关联到既有 `T002`；`mot_history_length=1` 触发 `mot_history_too_short`，没有放宽门控。18-78 px 日志来自 main runtime 的跨相机 fallback：资源自有相机没有 detection 时返回全部 local tracks，使一个二级 bbox 被多个主资源及主相机模型重复消费。该问题不在 D5 owned path，本次未跨模块修改。

main 验收前置条件：

- filter 同时覆盖 spawn actor exact name 和 asset mesh `Quadrotor1*`，并记录每相机实际 filter/radius；
- spawn/filter 与每次 actor/camera pose 更新后增加至少一个丢弃的 Scene/detection warm-up tick；
- `_local_tracks_for_resource` 无本相机检测时必须返回空，不得回退全部相机；二级 bbox 只能结合二级相机外参进入 recon/cross-view registration；
- 先达到每个预期可见相机连续至少 2 帧 detection、同相机重投影误差可审计，再评估 D5 lock 与联盟锁语义。

本轮 local ID 为 `Secondary_Recon_1:0:det:0001`，保持 camera-local namespace；actor/object truth 只出现在 offline-only metadata 和评分，未进入 online 绑定。联盟字段完整保留，但因 0 lock，合法 cooperative lock 分支尚未由真实 AirSim 命中。

### M 对 N 协同锁定 P1 已闭合（2026-07-11）

专项证据见 `D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`，覆盖 11 篇主要论文和 8 个开源候选。D5 已完成启用 `k_j>1` 前的联盟锁语义：

- 只读消费 D3 schema v2 的 `coalition_id/version`、`member_role`、`wave_id`、`required_resource_count`、`coordination_mode`、`plan_id/version`、arrival window 和 activation state；
- 把合法联盟成员对同一 `global_track_id` 的多机锁定解释为 `planned_cooperative_lock`，而不是仅凭资源数大于 1 判定 duplicate；
- 继续将联盟/计划版本不一致、缺失合同、resource scope 不符、超额资源、单资源多本地轨迹和 local-to-global 多重绑定标为 duplicate/conflict；
- 未激活 `reserve/retry` 在视觉匹配可锁时输出 `hold`、原始 visual-match evidence 和 D7 PNG blocker；active primary wave-0 与 k=1 保持回归；
- 每个 resource-camera 的 GlobalTrack 投影和 local MOT 仍独立运行，D5 不分配、裁减联盟或改写 `global_track_id`。

仍未闭合的是同步/序贯支持分层、带权 bearing 三角化、相机位姿/时间误差传播、PDOP/可观测度和融合协方差；这些是协同定位 P1/P2，不影响当前联盟锁语义通过。OpenCV 几何和 ByteTrack 本地 MOT 属于成熟默认候选；BoT-SORT 为可插拔升级；ReST、LMGP、多视图 GLMB及 Omni-swarm 相对位姿栈仅作为研究参考。

### P1 已补齐（D5 侧）

| 能力 | 当前证据 | 边界 |
|---|---|---|
| Geometry log fields | `TerminalAssociation.metadata`、`CandidateBreakdown.to_log_dict()` 和 `GeometricAssociationResult.to_log_records()` 输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair 与 duplicate-risk advisory。 | D5 只产出字段；main/D6 若要落盘 JSONL/CSV 需在其 owned paths 接入。 |
| `TerminalConsistencySummary` 连续窗口 | `TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口；`assignment_version` 仅进入摘要审计。 | advisory summary，不触发降级，不生成分配计划。 |
| AirSim truth ID 在线隔离 | D5 adapter 忽略 truth/global 字段并过滤 actor/truth alias；main builtin detect 使用匿名 camera-local bbox tracker，intercept/fallback local ID 已清理，truth 只进入离线 evaluator/metadata。 | 已由 `outputs/p0_truth_isolation_smoke_20260710` 真实 AirSim 三 case 验收闭合，转为保持回归。 |
| YOLOv8 frame adapter | `YoloMotAdapter.process_frame()` 默认优先 Ultralytics ByteTrack/BoT-SORT，将图像帧或 mock detector 输出转为命名空间化 `LocalVisualTrack`；fallback/native MOT 状态按 `(resource_id, camera_id)` 隔离，缺依赖明确 unavailable，detector 可用时可退回 deterministic IoU。metadata 标明 selection/backend/scope、wall latency、预算比较、observed device、MOT history、camera-local continuity，并提供 offline-only recall/precision/FN/FP 和 reset API。 | 真实 AirSim frame stream 接入、部署参数和多 seed IDF1/IDSW 标定仍由 main/runtime/D6 完成；tracker ID 只属于 camera-local namespace。 |
| Multi-seed readiness helper | `summarize_multiseed_calibration_readiness()` 已输出每个 seed 是否具备 local bbox/timestamp、geometry gate log、measurement age、AirSim detect source、YOLO/MOT backend、offline truth、bbox/handoff advisory 和 duplicate/friend conflict evidence 字段。 | D5 只审计字段覆盖；main/D6 仍负责实际跨 seed 落盘、聚合图表和阈值调参。 |
| Secondary coverage/funnel helper | `summarize_secondary_visual_coverage_funnel()` 已输出 `secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、每相机/网络每帧可见目标数、覆盖比例均值/最小值、detect 到 multi-support 漏斗计数，以及 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点。 | D5 只做诊断汇总；main/D4/D6 仍负责从 AirSim replay frames 调用、落盘和仲裁。 |
| D4 frame-scoped evidence | `SecondaryFrameAssociationEvidence` 输出与 D4 `TerminalAssociationSummary` 同名的 coverage/full-view、stable/not-registered、cue/gimbal 和 reject 字段，并保留 frame/timestamp/backend/calibration provenance。builder 只选择当前 frame candidate，拒绝混合 frame/timestamp；127 项 D5 测试已覆盖历史 candidate 隔离、cross-view 当前快照、5v5 多相机 fixture、M-to-N 联盟锁语义和真实 M=5/N=2 几何证据回放。 | D5 只产生证据；main/D4 仍需在真实同一 decision tick 消费、做 freshness/threshold version 检查，禁止 episode 末回填。 |
| Detect-to-global-track registration helper | `register_local_visual_tracks_to_global_tracks()` 已输出 `DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`、`detect_registration_reject_reasons`、registration candidates、registered observations、即时 cross-view support、稳定 `stable_cross_view_associations` 和 `registered_to_global_track` 成功状态；timestamp、measurement age、covariance/projection covariance、缺绑定、stale binding/cue、`projection_invalid`、geometry gate、稳定窗口失败和 offline-only truth 均有记录。 | D5 helper 已完成，main P1 sweep/D6 bundle 已有消费口径；后续是 AirSim camera pose metadata、多 seed gate、外参和降级 case 校准。 |
| Mobile recon gimbal cue evidence | `ReconImageCue` 与 coverage/cross-view summaries 已携带 `mobile_high_recon`、`mobile_recon_gimbal`、radar/GlobalTrack cue source、NED look-at、云台 metadata 和 pointing/track error；测试证明固定俯视不足时移动云台可改善二级网络联合覆盖证据。 | D5 不运行云台控制，也不使用 actor/truth ID 绑定；main/D6 已能接收报告字段，后续需真实 telemetry 多 seed 趋势分析。 |
| P1 calibration sweep / D6 bundle 输入合同 | main runtime 可运行 P1 D4/D5 calibration sweep，D6 自动生成 records/summary/report bundle。 | D5 不负责 AirSim 启停和报告生成；只维护 evidence DTO、helper、truth 隔离和 `global_track_id` 不变式。 |
| D4 evidence | `CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 已可作为 D4/D6 evidence。 | D5 不仲裁、不授权、不创建或换绑 `global_track_id`。 |
| D7 visual PNG 前置证据 | `annotate_visual_png_handoff()` 输出 handoff/prelock、gate pass、blockers、measurement age、LOS rate、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend/duplicate risk、unstable bbox、stale measurement age、missing LOS 会阻断。 | D5 不决定导引律，D7/main 仍需独立 terminal gate。 |

### P0-B 已闭合

| 优先级 | 任务 | 验收结果 |
|---|---|---|
| P0-B | 主动重捕获。 | 已实现 GlobalTrack 预测投影 + bbox/MOT 历史 + search window 的 assigned-track reacquire；测试覆盖遮挡后同一 MOT ID 快速恢复、MOT ID 更换需稳定窗口，且不改写 `global_track_id`。保持回归；若恢复逻辑退化为最近目标或 truth/local tracker ID 绑定，则作为 P0 backlog 重开。 |
| P0 | Active reacquire 友方声明复检。 | 已闭合并覆盖同一/新 MOT ID × verified/stale/unverified/spoof-suspected；冲突输出 `hold`、非空 `friend_conflict_state` 和可审计 reason，不改写 `global_track_id`。 |
| P0 | Detection category/truth 隔离。 | 已闭合并覆盖 generic/actor/object name 不影响 category/cost/binding，detector class-id names 映射仍有效，既有 truth isolation 保持。 |
| P0-B | 时序一致性和稳定窗口。 | 已加强 candidate margin、stable window、bbox/MOT history、stale/OOSM 和保守 hold/ambiguous 阻断；`TerminalConsistencyTracker` stable 判定不再把任意正 margin 视为稳定。保持回归；若 stable window、margin 或 stale/OOSM 阻断缺失，则作为 P0 backlog 重开。 |
| P0-B | 相机校准健康监测。 | 已输出 projection valid、reprojection error、camera pose source/trust、calibration health、drift warning、registration health counts 和误差摘要，供 D6/main 直接消费。保持回归；若缺失 reprojection error、pose source、calibration health 或 drift warning，则作为 P0 backlog 重开。 |

### 剩余 P1/P2

| 优先级 | 任务 | 验收建议 |
|---|---|---|
| P1 | YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定。 | 用 AirSim 连续 RGB/PNG 或外部 detector bbox stream 调用 `YoloMotAdapter.process_frame()`，跨 seed 标定目标尺度、FOV、confidence、class id 分布、bbox scale、tracker backend、CPU/GPU budget 实测、`gate_chi2`、candidate margin、bbox stability、handoff range、measurement age、LOS availability、ambiguity 和 quality 阈值，并报告 `locked_mismatch`、false handoff、ambiguous/reacquire 抖动和 `terminal_id_switch_count`。 |
| P1 | IBVS/间歇可见性重捕获对照。 | 基于 replay/对照实验评估 IBVS 或间歇可见性切换策略能否降低 lost/reacquire 时间；验收必须保持误锁为 0，且 D5 只产出 `TerminalAssociation`/`IdentityClaim` 证据，不重新分配、不授权、不本地换绑 `global_track_id`。 |
| P1 | 多模态友方识别 replay adapter。 | 将至少一个 Remote ID/MAVLink/DDS/AprilTag replay 来源归一化为 `IdentityClaim`，输出 verified/stale/unverified/spoof 状态；未知或 stale 不升级目标，verified friend 仍只触发保守阻断。 |
| P1 | 完整相机在线标定/畸变校正。 | 在 replay/标定样本中接入 2D-3D 对应、`solvePnP`/PnP RANSAC、外参漂移估计和重投影误差验收；将 `CameraModel.dist_coeffs` 从可消费字段推进为完整 projection/registration/误差报告链路，量化畸变校正前后的重投影误差下降。 |
| P1 | 二级节点几何/覆盖策略。 | 60-case 已关闭基础 not-registered 缺口，但网络同帧全目标覆盖率均值仍为 `0.0231`。继续调整站位、look-at 扫描/子簇策略和 full-view 判据，降低 `not_all_targets_visible` / `network_union_incomplete`；不得把局部 registration 误报为完整接管态势。 |
| P1 | Multi-camera cross-view registration 多 seed 标定。 | 60-case 的 `not_registered_count=0`、平均 cross-view association `4.417` 已作为当前基线；下一步转向外参漂移、时间同步、遮挡/交叉、稳定窗口和错误绑定压力测试，不再重复证明基础 registration 可运行。 |
| P1 | D4 逐决策 evidence 接线验收。 | D5 单帧 DTO/字段映射已完成；main/D4 需在同一 decision tick 传递并消费该对象，补 threshold version、stale rejection 和状态迁移日志。验收不得使用 stale/episode 聚合值，D5 不直接决定降级动作。 |
| P1 | 视觉接管图像边缘裕量与相机指向标定。 | 以 2v2 smoke 的 `bbox_near_image_edge=9`、2 个受影响资源对为基线，跨 seed 统计归一化 edge margin、连续边缘帧、camera pointing error、handoff request/reject 次数及 terminal switch 率；不得通过放宽 D7 独立安全 gate 提高切换率。 |
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
