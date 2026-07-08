# D5 Terminal Association

离线科研模块，用于把末端相机视场中的本地视觉轨迹保守关联到中心分配的 `global_track_id`。模块只输出 `TerminalAssociation` 决策，不修改、重写或重新分配任何全局轨迹 ID。

## 目录

- `src/d5_terminal_association/`: Python 实现。
- `tests/`: pytest 单元测试。
- `simulations/`: 多目标、友方、未知目标和遮挡的确定性仿真。
- `docs/`: 算法说明、实验报告和 AirSim 离线集成计划。

## 运行

```bash
pytest -q research_modules/d5_terminal_association/tests
python3 research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py --frames 120 --seed 7
```

当前实现仅依赖 Python 标准库、NumPy 和 OpenCV；测试使用 pytest。OpenCV 不可用时，投影函数会退回简化针孔模型。

## 核心接口

- `TerminalAssociator.project_tracks_to_image(global_tracks, camera)`
- `TerminalAssociator.build_cost_matrix(projections, local_tracks, identity_claims, recon_image_cues=(), resource_id=None)`
- `TerminalAssociator.decide(assignment, global_tracks, local_tracks, identity_claims, camera, current_time=None, recon_image_cues=())`
- `IdentityChecker.parse_claims(raw_messages, current_time)`
- `TerminalObservationBus.publish_terminal_association(...)`
- `TerminalObservationBus.cross_view_associations()`
- `TerminalCrossViewFusion.summarize_observations(...)`
- `TerminalCrossViewFusion.build_hypotheses(...)`
- `TerminalCrossViewFusion.associate(...)`
- `TerminalConsistencyTracker.update(...)`
- `summarize_terminal_consistency(...)`
- `annotate_visual_png_handoff(...)`
- `bbox_area_stability(...)`
- `local_visual_tracks_from_sim_detections(...)`
- `local_visual_tracks_from_offline_yolo_bytetrack(...)`
- `YoloMotAdapter.process_frame(...)`
- `publish_sim_detections_as_local_observations(...)`
- `compute_terminal_stress_metrics(...)`
- `summarize_degradation_case(...)`

推荐使用关键字参数传入时间和二级侦察 cue，避免误用位置参数：

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

详细算法原理、数学模型和实施流程见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。

## 当前状态总览

已实现：

- `GlobalTrack` 投影到图像平面、像素协方差传播、马氏门控和保守候选排序；`TerminalAssociation.metadata` 和 `GeometricAssociationResult.to_log_records()` 已输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、friend conflict、measurement age 和 duplicate-risk advisory 字段，便于 main/D6 写 JSONL/CSV。
- `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservation`、`CrossViewAssociation`、`DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`、`CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation` 等 DTO。
- `locked/ambiguous/hold/reacquire` 保守状态机；D5 只核对当前 `assigned_global_track_id`，不会把本地最佳或最近目标改写成新的全局身份。
- 跨视角 distributed visual association P0：`TerminalObservationBus` 汇总多资源终端证据，`TerminalCrossViewFusion` 在完全无中心场景输出 metadata-only 多相机 peer evidence。
- AirSim `simGetDetections` 风格 bbox dry-run adapter、离线 YOLO/ByteTrack schema adapter，以及 `YoloMotAdapter` 图像帧入口。默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt`，可通过参数覆盖；真实 `ultralytics` ByteTrack/BoT-SORT 路径不可用时，adapter 使用确定性 IoU fallback tracker，并在 `YoloMotFrameResult.metadata["tracker_backend"]` 标明实际后端。在线路径只消费 bbox、时间戳、本地 MOT ID、类别/置信度、相机几何和协方差。
- D7 视觉 PNG 前置证据：`annotate_visual_png_handoff()` 只在 D5 `locked`、当前 `assigned_global_track_id` 一致、friend/duplicate 风险安全、bbox 稳定、LOS rate 可用、measurement age 新鲜且 D4/D3 gate 允许时输出 handoff/prelock 建议。

部分实现或仅为抽象/adapter：

- OpenCV 已用于投影和可选畸变参数消费；真实 `calibrateCamera`、`solvePnP`/PnP RANSAC、标定板/AprilTag 标定链未接入。
- YOLOv8/ByteTrack/BoT-SORT adapter 已能消费图像帧或 mock detector 输出并返回 `LocalVisualTrack`；无 `ultralytics`、权重缺失或原生 tracker 不可用时返回清晰 `unavailable` 状态或退回 IoU tracker。该 adapter 不采集 AirSim 图像流、不管理 GPU 部署，也不让 tracker ID 替代 `global_track_id`。
- ByteTrack、BoT-SORT 的真实质量依赖上游 `ultralytics` 和连续图像输入；Deep SORT/ReID 仍未接入。IoU fallback 只提供确定性本地 ID 连续性，不声明遮挡恢复或 IDSW/IDF1 工程质量。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag 只通过仿真字典归一化为 `IdentityClaim`；未接入真实报文、密钥、证书或 tag detector。
- ROS 2 `tf2/message_filters` 只是未来时间同步和坐标树方案；D5 当前不运行 ROS 2 节点。

未实现：

- AirSim/main runtime 的连续图像流接入、真实 detector/tracker 部署、多 seed 阈值标定、真实标定链、真实身份认证链路和跨相机三维联合优化。D5 已提供 YOLOv8 + ByteTrack/BoT-SORT 模块适配器；main 仍需把 AirSim RGB/PNG frame、camera/resource/frame_id/timestamp 和运行参数接入该 adapter。
- 在线 D5 不得使用 AirSim `object_id`、`actor_name` 或 actor truth ID。truth ID 只能作为离线评分标签进入 metadata/evaluator，用于 `terminal_lock_accuracy`、`locked_mismatch` 等指标。

剩余 P1/P2 聚焦真实工程链路，而不是 D5 侧 evidence 字段：P1 为 main runtime 图像流接入 `YoloMotAdapter` 和多 seed 阈值校准；P2 为 BoT-SORT/Deep SORT/ReID 评估、OpenDroneID Core/MAVLink signing/DDS Security/AprilTag 的真实 `IdentityClaim` adapter、OpenCV calibration/`solvePnP` 以及 ROS 2 `tf2/message_filters`。geometry log fields、D4 evidence、D7 visual PNG 前置证据、AirSim truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter 和 YOLOv8 frame adapter 已在 D5 侧补齐。

## 决策状态

- `locked`: 唯一候选通过几何门限和保守代价检查。
- `ambiguous`: 候选接近、身份声明不可靠或代价过高。
- `hold`: 已验证友方与候选重叠，或版本不一致。
- `reacquire`: 无候选通过门限，或投影不可用。

## 主动降级仲裁信号

D5 可通过 `TerminalConsistencyTracker` 把连续帧 `TerminalAssociation` 派生为 `TerminalConsistencySummary`，供 D4/D6 判断中心/二级节点分配与末端视觉证据是否一致。摘要包含 `decision_state`、`association_confidence`、`ambiguity_score`、`friend_conflict_state`、candidate cost margin、`recon_cue_used`、terminal lock age、连续 `locked/ambiguous/hold/reacquire` 帧数、丢锁/重捕获事件、`duplicate_terminal_lock_risk` 和 `cross_view_support_count`。

连续帧窗口按 `resource_id + assigned_global_track_id` 维护，而不是按每次 D3 `assignment_version` 重置。这样同一资源持续执行同一全局目标时，即使中心滚动发布新的 plan version，D5 也能保留末端视觉丢锁/重捕获的连续性；只有 assigned global track 变化才进入新的窗口。

该摘要只用于离线一致性评估和 D4 仲裁输入。D5 不触发降级、不重写 `global_track_id`、不生成新分配计划。

## 视觉 PNG 接管建议

D5 可在 `TerminalAssociation.metadata` 或 `TerminalConsistencySummary.metadata` 中输出视觉 PNG 提前接管建议，但不决定导引律、不调用控制、不修改 `global_track_id`。D7/main 仍需独立检查相机、LOS、机动裕度和自身 terminal gate。

默认配置把当前 AirSim Blocks 5v5 大目标 actor 的经验值写成可调区间，而不是固定 30m 门限：

- 远距候选区 `30-50m`：只允许准备/预锁定，`visual_png_prelock_recommended=True`，不直接建议视觉接管。
- 中距候选区 `15-30m`：若 bbox 面积连续稳定、D3/D4/D5 一致、无友方冲突和重复锁定，且 `time_to_go`、检测延迟和 D7 机动裕度可接受，可输出 `handoff_recommended=True`。
- 近距强制评估区 `5-15m`：若检测稳定则优先建议视觉 PNG；若 bbox 不稳定则建议保持或回退 radar PN，避免过早触发 `terminal_detection_timeout`。

bbox 稳定性默认要求同一 `local_track_id` 或同一 assigned track 窗口连续 `N=4` 帧可见，`bbox_area_ratio` 的变异系数 `CV <= 0.30`，可在 `VisualPngHandoffConfig` 中调整为 `N=3-5`、`CV=0.25-0.35`。输出字段包括 `handoff_recommended`、`visual_png_gate_pass`、`visual_png_handoff_blockers`、`handoff_reason`、`recommended_range_band`、`bbox_stability_score`、`bbox_area_cv`、`measurement_age_s`、`measurement_age_ok`、`los_rate_px_s`、`los_rate_ok`、`range_to_assigned_track_m` 和 `time_to_go_s`。

## 完全分布式跨视场视觉假设

当前程序已覆盖单机视场内多目标候选、友方 `hold`、二级侦察 cue 作用域和保守 `global_track_id` 不变式，并提供两层跨视场证据：

- `TerminalObservationBus`：被动收集多架拦截无人机、二级节点或 peer 链路发布的 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue` 摘要，按既有 `global_track_id` 汇总支持关系。
- `TerminalCrossViewFusion`：在完全分布式模式下消费 `DistributedVisualObservation`、`VisualTrackletSummary` 和 `PeerCameraState`，基于时间窗口、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和相机姿态协方差生成 `CrossPeerAssociationHypothesis` 与 `DistributedTerminalAssociation`。

示例：UAV1 看到目标 1/2/3，UAV2 看到目标 2/3/4 时，目标 2/3 会形成包含 `("UAV1", "UAV2")` 的多视角支持摘要；目标 1/4 保持单视角支持。局部 ID 按 `resource/camera:local_track_id` 命名空间处理，因此 `UAV1/front:track_1` 与 `UAV2/front:track_1` 不会被误认为同一本地轨迹。若多个资源同时持有同一 current `assigned_global_track_id`，或同一本地命名空间出现全局 ID 冲突，D5 只输出 `duplicate_terminal_lock_risk=True`、`hold/ambiguous/hypothesis_only` 等保守状态，供 D4 仲裁，不会改写分配。

`TerminalCrossViewFusion` 使用 Hungarian 匹配；若 SciPy 不可用，会退回纯 Python 最小代价唯一匹配。缺失或 stale `global_track_id` 时只输出 `hypothesis_only/hold`，不会输出 `locked`。未知类别不会被升级为敌方。

当前实现仍是 metadata-only P0 融合器，不做三维重投影、三角化、多相机 bundle adjustment、真实图像 ReID 或 D4 分配决策。

## 二级侦察节点输入

高空系留侦察无人机可作为二级节点向覆盖小区内的拦截资源发送 `ReconImageCue`。该 cue 只在 `scoped_resource_ids` 限定范围内降低关联代价，用于帮助末端相机把本地视觉轨迹配准到中心分配的 `global_track_id`。它不能替代授权、版本校验、友方正向认证或本地 MOT 质量门槛，也不能触发局部节点自行改写 `global_track_id`。

`ReconImageCue.center_px` 必须已经处在当前拦截资源相机平面。若 cue 来自二级侦察节点自己的相机，需要先重投影到本地相机帧，再与 `LocalVisualTrack.center_px` 比较。

cue 使用规则：

- `scoped_resource_ids` 非空时，仅指定资源可使用；为空时按配置允许广播。
- `current_time` 存在时，超过 `AssociationConfig.max_recon_cue_age_s` 或来自未来的 cue 不参与代价。
- `frame_id` 存在时，`image_frame_id` 必须等于目标相机帧；若通过 `metadata["target_frame_id"]` 指向目标相机帧，则必须同时有 `metadata["reprojected_to_local_camera"] == True`。
- 若 `metadata["source_image_frame_id"]` 与目标帧不同，也必须显式标记已重投影。

在跨视角总线中，系留无人机视频 cue 只作为几何门控和复核证据随 `TerminalObservation` 记录。它可以增加 `recon_cue_used_count`，但不能创建新的 `global_track_id`、不能替代 D2 航迹，也不能让本地节点换绑分配目标。

## AirSim ComputerVision N-v-N 专项适配

D5 提供不依赖 AirSim Python 包的 dry-run 适配器，用于消费 `simGetDetections` 风格的检测框 fixture。5v5 只是历史 stress baseline：目标距拦截镜头约 50m，目标间距约 20m，拦截镜头间距约 20m；二级系留侦察镜头比目标高约 200m，分辨率更高并提供全局视野。真实 N-v-N 仿真数量由 main runtime 的 `--drone-count N` 决定，D5 只按传入的 `LocalVisualTrack[]`、`GlobalTrack[]` 和 camera/resource 列表长度运行，不在模块内固定 2/5 个相机或目标。

当前主线使用捷联固定相机和 AirSim detect bbox，不默认运行 YOLO。为了减少机架遮挡，建议 main/D7/AirSim settings 将拦截机相机沿机体系前向前移约 `0.5m`；D5 只消费更新后的 `CameraModel` 外参，不直接修改相机安装或 AirSim settings。

在线几何配准只使用 bbox、时间戳、相机几何、本地 MOT ID、类别/置信度等观测字段。AirSim detection 的 `object_id`、`actor_name` 或 truth ID 只能作为离线评估标签进入 `metadata`/评估 helper，不能进入 `TerminalAssociator`、`TerminalObservationBus` 或跨视角一致性决策。

处理链路：

1. 每个当前 runtime camera/resource 的检测框转换为 `LocalVisualTrack`。
2. 多镜头本地观测写入 `TerminalObservationBus`。
3. 单机 `TerminalAssociation` 和二级 `ReconImageCue` 作为被动证据发布。
4. `cross_view_associations()` 或 `TerminalCrossViewFusion.associate()` 汇总重叠视场支持、metadata-only 分布式假设和重复锁定风险。
5. `summarize_degradation_case()` 输出 `no_degradation`、`degrade_to_secondary` 或 `degrade_to_distributed` 证据标签。

建议指标包括 `per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy` 和 `ambiguous_fov_event_count`。这些指标只供 D4/D6 仲裁和评估使用；D5 不生成 `AssignmentPlan`，不改写 `global_track_id`。

## AirSim Blocks 2v2 二级计划语义

在主动降级后，D4/D3 的二级节点重分配结果仍必须以 `Assignment.assigned_global_track_id` 输入 D5。D5 只核对该 ID 对应的中心/二级计划航迹是否被本机 `simGetDetections` 检测框支持：

- `locked` 只表示当前 `assigned_global_track_id` 的投影与唯一稳定候选一致、已授权、版本一致、MOT 质量足够且无友方冲突。
- 若离线真值或评估元数据表明检测目标不是 `assigned_global_track_id`，D5 只能把该帧统计为 `locked_mismatch` 或阻断视觉 PNG handoff，不能把结果改写成另一个 `global_track_id`。
- bbox 连续稳定性由 `annotate_visual_png_handoff()` 检查；稳定性不足时即使单帧几何可 `locked`，也不得输出视觉 PNG handoff 建议。
- 已验证友方与门内候选重叠时必须 `hold`；未验证或疑似伪造身份声明降级为 `ambiguous`。

## 边界

本模块只用于科研仿真和离线评估；不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。
