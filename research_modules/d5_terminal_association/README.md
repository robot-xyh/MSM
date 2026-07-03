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
- `local_visual_tracks_from_sim_detections(...)`
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

## 决策状态

- `locked`: 唯一候选通过几何门限和保守代价检查。
- `ambiguous`: 候选接近、身份声明不可靠或代价过高。
- `hold`: 已验证友方与候选重叠，或版本不一致。
- `reacquire`: 无候选通过门限，或投影不可用。

## 主动降级仲裁信号

D5 可把连续帧 `TerminalAssociation` 派生为 `TerminalConsistencySummary` 建议字段，供 D4 判断中心/二级节点分配与末端视觉证据是否一致。建议包含 `decision_state`、`association_confidence`、`ambiguity_score`、`friend_conflict_state`、candidate cost margin、`recon_cue_used`、terminal lock age，以及连续 `ambiguous/hold/reacquire` 帧数。

该摘要只用于离线一致性评估和 D4 仲裁输入。D5 不触发降级、不重写 `global_track_id`、不生成新分配计划。

## 跨视场配准设计

当前程序已覆盖单机视场内多目标候选、友方 `hold`、二级侦察 cue 作用域和保守 `global_track_id` 不变式，并新增最小 `TerminalObservationBus` 与 `CrossViewAssociation`。该总线用于收集多架拦截无人机、二级节点或 peer 链路发布的 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue` 摘要，按既有 `global_track_id` 被动汇总多视角支持关系。

示例：UAV1 看到目标 1/2/3，UAV2 看到目标 2/3/4 时，目标 2/3 会形成包含 `("UAV1", "UAV2")` 的多视角支持摘要；目标 1/4 保持单视角支持。若多个资源同时 `locked` 同一 `global_track_id`，D5 只输出 `duplicate_terminal_lock_risk=True`，供 D3/D4 仲裁，不会改写分配。

当前实现仍不是完整的多相机几何融合器。后续若要处理相机姿态协方差、跨相机时间对齐和三维重投影，应在 `TerminalObservationBus` 之上扩展 `TerminalCrossViewFusion`。

## 二级侦察节点输入

高空系留侦察无人机可作为二级节点向覆盖小区内的拦截资源发送 `ReconImageCue`。该 cue 只在 `scoped_resource_ids` 限定范围内降低关联代价，用于帮助末端相机把本地视觉轨迹配准到中心分配的 `global_track_id`。它不能替代授权、版本校验、友方正向认证或本地 MOT 质量门槛，也不能触发局部节点自行改写 `global_track_id`。

`ReconImageCue.center_px` 必须已经处在当前拦截资源相机平面。若 cue 来自二级侦察节点自己的相机，需要先重投影到本地相机帧，再与 `LocalVisualTrack.center_px` 比较。

在跨视角总线中，系留无人机视频 cue 只作为几何门控和复核证据随 `TerminalObservation` 记录。它可以增加 `recon_cue_used_count`，但不能创建新的 `global_track_id`、不能替代 D2 航迹，也不能让本地节点换绑分配目标。

## AirSim ComputerVision 5v5 专项适配

D5 提供不依赖 AirSim Python 包的 dry-run 适配器，用于消费 `simGetDetections` 风格的检测框 fixture。推荐 5v5 压测几何为：目标距拦截镜头约 50m，目标间距约 20m，拦截镜头间距约 20m；二级系留侦察镜头比目标高约 200m，分辨率更高并提供全局视野。

处理链路：

1. 每个 `Interceptor_Cam_*` 的检测框转换为 `LocalVisualTrack`。
2. 多镜头本地观测写入 `TerminalObservationBus`。
3. 单机 `TerminalAssociation` 和二级 `ReconImageCue` 作为被动证据发布。
4. `cross_view_associations()` 汇总重叠视场支持和重复锁定风险。
5. `summarize_degradation_case()` 输出 `no_degradation`、`degrade_to_secondary` 或 `degrade_to_distributed` 证据标签。

建议指标包括 `per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy` 和 `ambiguous_fov_event_count`。这些指标只供 D4/D6 仲裁和评估使用；D5 不生成 `AssignmentPlan`，不改写 `global_track_id`。

## 边界

本模块只用于科研仿真和离线评估；不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。
