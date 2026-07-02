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

当前程序已覆盖单机视场内多目标候选、友方 `hold`、二级侦察 cue 作用域和保守 `global_track_id` 不变式；尚未完整实现多无人机、多相机的跨视场融合。

后续集成建议把 `local_track_id` 明确限定在 `(resource_id, camera_id, frame_id)` 命名空间内，并新增 `CrossViewObservation`、`CrossViewAssociation`、`TerminalCrossViewFusion` 或 `TerminalObservationBus`。跨视场逻辑只把多个本地观测配准到 D2 已存在的 `global_track_id`，不得由 D5 创建、改写或换绑全局 ID。

## 二级侦察节点输入

高空系留侦察无人机可作为二级节点向覆盖小区内的拦截资源发送 `ReconImageCue`。该 cue 只在 `scoped_resource_ids` 限定范围内降低关联代价，用于帮助末端相机把本地视觉轨迹配准到中心分配的 `global_track_id`。它不能替代授权、版本校验、友方正向认证或本地 MOT 质量门槛，也不能触发局部节点自行改写 `global_track_id`。

`ReconImageCue.center_px` 必须已经处在当前拦截资源相机平面。若 cue 来自二级侦察节点自己的相机，需要先重投影到本地相机帧，再与 `LocalVisualTrack.center_px` 比较。

## 边界

本模块只用于科研仿真和离线评估；不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。
