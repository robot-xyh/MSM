# D5 末端视觉配准与协同身份认证综述及子方案

**定位**: 分配完成后，资源节点末端视场内可能同时出现多个目标、友方资源和未知飞行物。本模块负责把局部视觉目标配准回中心分配的 `global_track_id`。  
**边界**: 本文只讨论视觉配准、协同身份认证和保守决策，不包含真实火控参数、毁伤逻辑、自动处置控制律或绕过人工授权的流程。

---

## 0. 阶段补充：二级侦察节点图像 cue

本阶段假设存在若干高空系留侦察无人机作为二级节点。中心节点正常时，二级节点持续把本覆盖小区内的侦察图像或图像平面 cue 发给若干拦截资源；中心节点失效时，D4 可将局部协调权降级到二级节点；二级节点失效后才进入完全无中心协商。

D5 使用这些 cue 的原则：

- 二级节点 cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心/框、置信度和 `scoped_resource_ids`。
- cue 只在指定小范围资源内生效，不能跨覆盖区使用。
- cue 只作为视觉关联代价的辅助证据，不能替代中心授权、版本匹配、友方身份认证和本地 MOT 质量门槛。
- 即使二级节点 cue 与本地相机目标一致，局部节点也只能输出 `TerminalAssociation`，不得自行改写 `global_track_id`。

---

## 1. 研究问题

末端视场中“最近目标”不一定是分配目标。局部相机可能同时看到：

- 中心分配的目标；
- 其他来袭目标；
- 友方资源节点；
- 空中侦察无人机；
- 未知或无关飞行物。

如果局部节点自行换绑 `global_track_id`，会造成重复分配、漏分配、ID Switch 或友方安全风险。因此末端节点只能输出 `TerminalAssociation`，不能直接改写中心分配。

---

## 2. 文献综述要点

局部 MOT 方面，ByteTrack 通过高低置信检测两阶段关联提升召回率，适合短时遮挡和小目标跟踪；BoT-SORT 加入相机运动补偿和 ReID，更适合运动相机；Deep SORT 使用深度外观特征，能降低 ID Switch，但无人机视角下目标小、模糊、逆光和外观相似会导致退化。

几何配准方面，OpenCV 标定、`solvePnP/projectPoints` 和 ROS 2 `tf2` 是默认工具链。核心不是全图识别，而是把 `GlobalTrack` 预测位置投影到相机平面，生成几何门限，再与 `LocalVisualTrack` 做关联。

身份认证方面，Remote ID/OpenDroneID、MAVLink signing、DDS Security 和任务内协同 ID 都只能正向确认友方或协同方。未知目标不能自动等同于敌方。AprilTag 等视觉标签可用于实验室合作目标，但不能作为复杂环境中的唯一身份依据。

---

## 3. 开源代码选型

| 工具 | 用途 | 适用性 |
|------|------|--------|
| ByteTrack | 局部MOT默认基线 | 小目标短时遮挡较稳，但不负责全局身份 |
| BoT-SORT | 运动相机MOT | 有相机运动补偿，适合资源节点视角 |
| Deep SORT | 外观辅助MOT | 纹理足时有效，低分辨率会退化 |
| OpenCV Calibration/solvePnP | 相机标定和投影 | 几何配准核心 |
| ROS 2 tf2 | 坐标变换 | 维护世界系、机体系、相机系 |
| OpenDroneID | Remote ID实现 | 仅作身份声明证据 |
| MAVLink signing / DDS Security | 消息来源认证 | 需与任务清单交叉验证 |
| AprilTag | 合作视觉标识 | 近距实验辅助 |

---

## 4. 处理链路

```text
AssignmentPlan.assigned_global_track_id
-> GlobalTrack按measurement_timestamp预测
-> tf2转换到camera_frame
-> OpenCV投影到图像平面
-> 生成几何门限
-> ByteTrack/BoT-SORT/Deep SORT生成LocalVisualTrack
-> Hungarian/JPDA匹配LocalVisualTrack与GlobalTrack
-> IdentityClaim做友方正向确认
-> 输出 locked | ambiguous | hold | reacquire
```

---

## 5. 数据结构

```text
LocalVisualTrack
- local_track_id
- bbox
- center_px
- bearing_rate
- mot_history_length
- candidate_global_track_ids
- quality

TerminalAssociation
- assigned_global_track_id
- local_track_id
- association_confidence
- ambiguity_score
- friend_conflict_state
- decision_state: locked | ambiguous | hold | reacquire
- assignment_version

IdentityClaim
- platform_id
- claim_type: cooperative_id | remote_id | visual_tag
- auth_state: verified | stale | unverified | spoof_suspected
- associated_track_id
- timestamp
```

---

## 6. 匹配代价

```text
terminal_association_cost =
    image_projection_error
  + los_rate_consistency_error
  + timestamp_latency_penalty
  + track_covariance_penalty
  + mot_history_penalty
  + class_mismatch_penalty
  + friend_identity_conflict_penalty
```

只有候选唯一、代价差距明显、无友方冲突且版本匹配时，才能进入 `locked`。

---

## 7. 决策伪代码

```python
def terminal_association(global_track, assignment, local_tracks, claims):
    if assignment.assigned_global_track_id != global_track.global_track_id:
        return TerminalAssociation(decision_state="hold")

    gate = project_global_track_to_image(global_track)
    candidates = []

    for local in local_tracks:
        if not inside_projection_gate(local, gate):
            continue
        cost = projection_cost(local, gate)
        cost += los_rate_cost(local, global_track)
        cost += identity_conflict_cost(local, claims)
        candidates.append((cost, local))

    best, margin = select_unique_candidate(candidates)
    friend_state = evaluate_positive_friend_claim(best, claims)

    if friend_state == "friend_conflict":
        return TerminalAssociation(decision_state="hold")
    if best is None:
        return TerminalAssociation(decision_state="reacquire")
    if margin < MIN_MARGIN:
        return TerminalAssociation(decision_state="ambiguous")

    return TerminalAssociation(decision_state="locked")
```

---

## 8. 失败案例测试

| 场景 | 期望状态 |
|------|----------|
| 最近目标不是分配目标 | 锁定投影门内匹配目标，不抢绑最近目标 |
| 短时遮挡 | `hold -> reacquire` |
| Remote ID匹配但签名失败 | `ambiguous/hold` |
| AprilTag可见但投影残差异常 | 拒绝身份提升 |
| 外参偏移 | 投影门失败并记录校准告警 |
| 时间戳延迟 | 预测补偿后再匹配 |
| 两候选代价接近 | `ambiguous`，不上报锁定 |

---

## 9. 交付物

1. 末端MOT、几何投影、友方认证综述。
2. ByteTrack、BoT-SORT、Deep SORT、OpenCV、tf2、OpenDroneID适用性评估。
3. `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 数据结构。
4. 匹配代价和保守决策逻辑。
5. 模拟相机投影与歧义场景测试用例。

---

## 10. 参考资料

- ByteTrack: <https://github.com/FoundationVision/ByteTrack>
- BoT-SORT: <https://github.com/NirAharon/BoT-SORT>
- Deep SORT: <https://github.com/nwojke/deep_sort>
- OpenCV camera calibration: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>
- OpenCV `solvePnP`: <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>
- OpenDroneID Core C: <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing: <https://mavlink.io/en/guide/message_signing.html>
- ROS 2 DDS Security: <https://design.ros2.org/articles/ros2_dds_security.html>
- AprilTag: <https://github.com/AprilRobotics/apriltag>
