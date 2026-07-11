# D5 末端视觉配准与协同身份认证综述及子方案

**定位**: 分配完成后，资源节点末端视场内可能同时出现多个目标、友方资源和未知飞行物。本模块负责把局部视觉目标配准回中心分配的 `global_track_id`。  
**边界**: 本文只讨论视觉配准、协同身份认证和保守决策，不包含真实火控参数、毁伤逻辑、自动处置控制律或绕过人工授权的流程。

---

## 0. 阶段补充：二级侦察节点图像 cue

本阶段假设存在若干高空系留侦察无人机作为二级节点。中心节点正常时，二级节点持续把本覆盖小区内的侦察图像或图像平面 cue 发给若干拦截资源；中心节点失效时，D4 可将局部协调权降级到二级节点；二级节点失效后才进入完全无中心协商。

D5 使用这些 cue 的原则：

- 二级节点 cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心/框、置信度和 `scoped_resource_ids`。机动高空侦察云台 cue 还可携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。
- cue 只在指定小范围资源内生效，不能跨覆盖区使用。
- cue 只作为视觉关联代价的辅助证据，不能替代中心授权、版本匹配、友方身份认证和本地 MOT 质量门槛。
- 即使二级节点 cue 与本地相机目标一致，局部节点也只能输出 `TerminalAssociation`，不得自行改写 `global_track_id`。

### 0.1 与二级节点图像下发的坐标约束

二级高空侦察节点下发的图像或像素 cue 不能直接等同于拦截无人机本机相机坐标。若二级节点给出的是自身相机画面中的像素框，必须先通过仿真真值、D1/D2 全局航迹或几何重投影，转换到目标拦截无人机的相机平面，才能和本机 `LocalVisualTrack.center_px` 比较。

建议 `ReconImageCue` 的 `image_frame_id` 使用目标相机帧，例如 `UAV1/front_rgb`；原始二级节点相机帧放入 `metadata.source_image_frame_id`。`scoped_resource_ids` 必须限定 cue 可用资源，例如 `["UAV1", "UAV2"]`，避免未覆盖资源错误使用 cue。

### 0.2 本轮 AirSim ComputerVision N-v-N D4/D5 专项适配

D5 已补充 dry-run 适配层，用于消费 `simGetDetections` 风格检测框 fixture，不导入 AirSim、不调用控制 API。5v5 只是 stress baseline：5 个 `Interceptor_Cam_*` 主镜头、5 个目标，目标距主镜头约 50m，目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标；二级系留侦察镜头比目标高约 200m，分辨率更高并提供全局视野 cue。真实 N-v-N 数量由 main runtime 的 `--drone-count N` 统一控制，D5 只按 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表和 bus observation 长度运行。

在线配准只使用 bbox、时间戳、本地 MOT ID、显式 detector 类别/置信度和相机几何。在线 category 仅允许 `category/label/class_name` 或 detector `class_id + names` 映射；通用 `name`、`actor_name`、`object_name` 不得作为 category 或关联证据。AirSim detection 的 `object_id`、actor/object name、truth ID 只能作为离线评估标签，不能参与 `TerminalAssociator`、`TerminalObservationBus` 或跨视角一致性判断。本轮二级节点先使用 AirSim `simGetDetections` bbox/metadata，不启用 YOLO；若检测记录中的 `track_id`/`detection_id` 与 actor/truth 字段完全相同，或以 `: / | #` 分隔组件形式嵌入 actor/truth 值，D5 会回退为相机作用域本地检测 ID。

D5 输出边界保持不变：

- 可输出 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservationBus` 和 `CrossViewAssociation` 摘要。
- 不生成 `AssignmentPlan`。
- 不改写 `global_track_id`。
- 重复锁定只输出 `duplicate_terminal_lock_risk`，交由 D3/D4 仲裁。

三类 D5 证据 case：

- `no_degradation`：终端锁定与 D3 分配及离线评估真值一致。
- `degrade_to_secondary`：终端局部/二级证据与中心分配持续不一致或歧义，且二级 `ReconImageCue` 新鲜可用。
- `degrade_to_distributed`：同样不一致或歧义，但二级证据不可用、过期或失效，只能提供分散降级证据。

建议指标：`per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy`、`ambiguous_fov_event_count`。多 seed 报告前可调用 `summarize_multiseed_calibration_readiness()` 被动审计每个 seed 是否具备 local bbox/timestamp、geometry gate log、measurement age、AirSim detect source、YOLO/MOT backend、offline truth label、bbox/handoff advisory 和 duplicate/friend conflict evidence 字段。二级 detect 没有转成有效跨视角关联时调用 `summarize_secondary_visual_coverage_funnel()`，区分“看见目标”“网络联合覆盖”和“形成既有全局 ID 支持”三层指标；该 helper 还可区分 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`，并记录移动云台通过 GlobalTrack/radar cue look-at 补足的目标簇/子簇。

D5 现已补充 AirSim settings 驱动的 detect-to-global-track registration helper：`register_local_visual_tracks_to_global_tracks()` 输入 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，输出 `DetectToGlobalTrackCandidate.outcome`、注册后的 `TerminalObservation`、即时 `CrossViewAssociation` 和稳定 `stable_cross_view_associations`。匹配使用像素马氏距离 + Hungarian；缺 SciPy 时退回确定性唯一匹配并保留 gated candidates，便于 JPDA-compatible 下游使用。输出 reasons 包含 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。

2026-07-09 P1 二级 detect 校准补充：registration candidate 和 observation metadata 已携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、measurement/arrival/local-track timestamp、`measurement_age_s`、`covariance_px`、`projection_covariance_px`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`projection_reason`、`camera_pose_source`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 支持 `airsim_camera_pose`、`runtime_guidance_pose`、`look_at_fallback`，D5 只消费 main/runtime 提供的 `CameraModel` 和 metadata，不直接调用 AirSim。`adaptive_pixel_covariance_px()` 按 bbox 面积和图像对角线生成二级相机自适应像素协方差；无 bbox 面积时保留安全 fallback。默认稳定窗口为 3 帧内同一 `resource/camera/local_track/global_track` 至少 2 次 gate pass，单帧通过只记为 candidate，稳定后才标记 `stable_cross_view_support=True`。

2026-07-11 AirSim 集成复核发现 cross-view bus 的全历史汇总会把旧帧/旧 plan lock 当成当前 duplicate。D5 已为 `cross_view_associations()` 增加 `as_of_timestamp`、`max_age_s`、`plan_id`、`plan_version` 快照参数：作用域模式先做 freshness 与 plan identity 过滤，再按 resource 保留最新 timestamp 的同帧观测；duplicate 与 coalition 判定只在该快照上执行。无参数调用保持旧离线兼容，scope metadata 可审计筛选数量。main 在线应传当前 frame timestamp、约 `1.5 * dt` freshness 和当前 plan identity；D5 不修改 D3 prohibited edge 或 runtime 调度。

### 0.3 registration calibration 演进结论

`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为历史 stress 证据：该旧批次说明 D5 已能识别 `mobile_recon_gimbal`、`radar_global_track_cue`、`mobile_high_recon` 和云台指向 metadata，目标看清能力相对固定俯视对照改善，但二级网络覆盖与降级注册未闭合。

`research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*` 的单 seed 结果保留为历史基线：`projection_valid_rate=1.0`，三个 case 的 cross-view association 为 4/4/5，但降级 case not-registered 为 35/35。

当前结论来自 `research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710`：5v5、10 seeds、50/200 m、三类 case，共 60 个 case。D6 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0；平均 `projection_valid_rate=1.0`、stable registration `92.233`、cross-view association `4.417`。基础 detect-to-global registration 已闭合，但网络同帧全目标覆盖率均值仅 `0.0231`、平均覆盖率 `0.7059`，稳定窗口失败仍需校准。局部注册成功不表示二级接管态势完整。

D5 当前无 P0 blocker。2026-07-10 已闭合 active reacquire 友方声明、通用 detection name category 污染、sim-detection actor alias 和端到端 AirSim actor-name local ID 隔离。真实验收证据为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`：三类 case 均 connected、各 5 帧，local/detection ID 不含 actor 名，匿名 ID history 达 5，actor 名仅在 `offline_truth_only=True` metadata，每类 cross-view association 均为 4。当前 D5 剩余 P1 聚焦二级网络覆盖、降级 case registration、真实多 seed 阈值/外参/MOT、视觉接管边缘裕量和 `solvePnP` 增强。D5 仍不分配、不授权、不创建/改写/换绑 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

2026-07-11 YOLO/MOT 冒烟修复：offline detector evaluation 的 bbox-only 输入不再经过会拆散裸四元组的通用递归路径，现支持单框、多框和 dict/object detection，畸形输入明确报错。此修复只恢复离线 detector 指标采集，不改变在线 tracker、局部 ID 或全局绑定逻辑，也不把 truth identity 带入 metadata。

### 0.4 P1 D4/D5 calibration sweep 与 D6 bundle 状态

main runtime 已新增 P1 D4/D5 calibration sweep，可按二级高度、FOV、二级节点数量和 standoff 组合运行多 seed stress episode。D4/D5 stress 链路已把 D5 的 detect-to-global-track registration output、`detect_registration_outcome`、`detect_registration_reject_reasons`、timestamp/measurement-age/covariance/projection-covariance evidence、`TerminalObservation`、`CrossViewAssociation`、secondary coverage funnel、mobile gimbal metadata 和 registration rejection reason 放入统一 observation/report 流。

D6 标准报告 bundle 已由 main 自动生成，包含 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D5 的职责是保证 evidence DTO、registration helper、truth ID 在线隔离和 `global_track_id` 不变式；AirSim 启停、sweep 调度、日志落盘和 D6 报告仍由 main/D6 负责。

因此本阶段 D5 的剩余 P1 不再是“缺 helper、缺报告输入合同或基础 registration 不工作”，而是二级网络完整覆盖、真实 YOLOv8 + ByteTrack/BoT-SORT 多 seed、外参漂移/时间同步、D4 逐决策 evidence、遮挡/交叉和友方身份真实 replay。所有任务保持现有保守门控。

### 0.5 2026-07-10 2v2 active-secondary visual-PNG 复核

证据目录为 `research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710`。本轮 2 个资源对均完成 `collision_intercept`，pair summary 的 D5 结果均为 `locked`；D7/main 独立 terminal gate 同时记录 `bbox_near_image_edge` 9 次、覆盖 2 个资源对，控制日志中仅 2 条记录满足 `terminal_switch_allowed=True`。因此本轮证明了 D5 lock 与 D7 camera/LOS/maneuver gate 是串联而非互相替代：边缘框不会因为 D5 已锁定而自动放行视觉 PNG。

该结果保留 P1 动作：跨 seed 记录 bbox 到四条边界的归一化最小裕量、连续边缘帧、相机指向误差和 handoff 重复请求，必要时由 D5 handoff metadata 提前暴露 edge advisory，但不得取消 D7 独立门控。P0 集成 hotfix 已通过上述真实 AirSim 三 case 验收并转为保持回归；D5 不对任意既有 `LocalVisualTrack.local_track_id` 做猜测式重写。

### 0.6 2026-07-10 逐帧 D4 evidence 与 YOLO/MOT adapter 补齐

D5 新增 `SecondaryFrameAssociationEvidence` 和 `build_secondary_frame_association_evidence()`。输入必须是同一同步 `frame_id` 的二级 camera coverage、network coverage 和 registration result；输出直接提供 D4 现有 `TerminalAssociationSummary` 可消费的当前帧字段：单相机/网络 full-view、网络 coverage、stable cross-view registration、not-registered、cross-view conversion gap、cue freshness、gimbal pointing 和 reject diagnostic。metadata 保留 measurement/arrival timestamp、detector/tracker backend、registration backend 与 calibration health。registration result 即使包含历史候选，也只选择当前 frame/timestamp；混合 camera frame 或超出同步容差直接拒绝，所以 episode 末汇总不能冒充在线接管证据。D5 仍不决定降级动作。

`YoloMotAdapter` 的主线明确为：优先调用 Ultralytics `bytetrack.yaml` 或 `botsort.yaml`；依赖/权重缺失返回 `unavailable`；原生 tracker 失败但 detector 仍可用时启用 per-stream deterministic IoU fallback。每帧记录 requested/selected backend、native/fallback 状态、detector+tracker wall latency、CPU/GPU 声明预算比较、observed device、per-local-track history 和 camera-local continuity。可选 offline truth bbox 只在在线输出形成之后计算 recall/precision/FN/FP/IoU，不输出 identity，不影响检测筛选、tracker ID 或全局绑定。

新增测试覆盖 5v5 多相机命名空间、目标交叉、单帧遮挡后恢复、native BoT-SORT 优先、离线召回隔离和跨 frame 防回填；D5 全量结果为 `101 passed`。本机 `best.pt`、Ultralytics 8.4.71 和 Torch CUDA 环境可用；CPU 黑帧烟测中首个模型加载约 3.87 s、第二个独立 adapter 热路径约 118 ms，黑帧无检测导致原生 tracker 无 ID 并按设计回退。该结果只验证真实权重和库入口，不代表无人机目标召回率或多 seed MOT 质量。

### 0.7 2026-07-11 AirSim 检测/MOT 实测边界

真实证据需要分为几何注册基线和 YOLO/MOT 质量两部分：

- 三组既有 D4/D5 回归均得到 `cross_view_association_count=4`，稳定注册约 19-61，证明已有 bbox/几何路径可形成跨视角支持；二级同帧全目标覆盖仍不足，不能据此声明二级节点态势完整。
- `research_modules/airsim_runtime/outputs/p1_yolov8_bytetrack_smoke_fixed_20260711` 完成 6 个 reset-separated episode、每个 2 帧。AirSim RGB 解码、YOLOv8/ByteTrack 调用、per-stream 状态、在线 truth 隔离、offline bbox-only 评分和 D5 runtime event 均正常执行，接口层已闭合。
- 当前相机/actor 几何下 `accepted_detection_count=0`，AirSim offline truth boxes 多数为 0；因此 detector recall/precision 大多不可计算或为 0。原生 ByteTrack 没有 detector track ID，按设计回退 `iou_fallback`，没有形成可评价的 native MOT identity continuity。
- 本轮处理延时多数约 38-49 ms，首轮约 197 ms。该数字只用于当前短序列部署预算基线，2 帧不足以评价稳态 p95、GPU 并发、遮挡恢复或 IDSW/IDF1。

结论：YOLO/MOT 的输入输出、truth 隔离和失败回退合同已闭合；目标检测有效性、offline truth bbox 可用性、native ByteTrack/BoT-SORT 连续性和真实多 seed 预算尚未闭合。下一轮必须先取得非零 accepted detection 和有效 offline truth bbox，再进行阈值、class map、目标尺度、FOV/相机指向、MOT continuity 和多 seed 标定。任何检测/MOT 改善都不能让 tracker ID 生成、改写或换绑 `global_track_id`。

---

## 1. 研究问题

### 0.4 真实 AirSim M=5、N=2 检测/几何复核

`blocks_cv_m5_n2_cooperative_live_20260711` 已证明 7 路相机出图和 D3 schema v2 联盟字段可进入 full flow，但没有证明 D5 可锁定：full-flow 为 32 次 `reacquire`、4 次 `ambiguous`、0 次 `locked`。主要断点发生在 D5 前的 `simGetDetections`，绝大多数 camera-frame 返回空列表。

唯一 `Secondary_Recon_1` bbox 的同相机离线复算结果为：`T002` projected pixel 与 bbox center 相差约 0.09 px，D5 几何选择正确；由于只有单帧、MOT history=1，保守输出 `ambiguous`。现有 18-78 px 汇总混入了 main runtime 的跨相机 fallback，不应解释为 D5 外参公式失效或据此放宽 `gate_chi2`。main 应先修正 per-resource camera scope，再用 `Quadrotor1*`/actor exact filter 和 pose-update warm-up 重跑。

边界保持不变：D5 不读取 online truth ID，不根据该唯一 bbox 改绑 `global_track_id`，也不把二级相机 detection 当作任意主资源的本地 MOT。真实 AirSim 联盟锁仍待每成员连续有效 bbox 后验收。

### 1.0 M 对 N 高威胁目标的计划内多机锁定

2026-07-11 专项调研已形成 `D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`，并已完成 D3 schema v2 联盟锁合同。`Assignment`、`GlobalTrackBinding`、`TerminalAssociation` 和 `CrossViewAssociation` 保留联盟/计划版本、成员角色、波次、需求数、协同模式、arrival window 与 activation state。`k_j>1` 时，同一已授权激活联盟内且不超过 demand 的多个 lock 输出 `planned_cooperative_lock`，不设置 `duplicate_terminal_lock_risk`；第四个超额 lock、联盟/版本不一致、scope 不符和 local/global 多重绑定仍冲突。

错误 duplicate 仍包括计划外资源加入、单资源多本地轨迹锁定、单一本地轨迹支持多个全局目标、stale plan、友方冲突和跨视角几何不一致。同步观测可用于带权三角化；序贯观测必须按量测时间运动补偿并膨胀协方差。像素位置和 bbox 尺度历史只作关联辅助，不能独立提供三维尺度或创建新全局身份。

未激活 `reserve/retry` 即使已形成视觉可锁候选，也只输出 `hold`、`execution_gate_reason` 和 D7 visual PNG blocker；active primary wave-0 与 k=1 回归保持正常。每个 resource-camera 仍独立执行 GlobalTrack 投影与 local MOT，D5 不形成联盟、不重新分配、不裁减超额资源。带权三角化、PDOP/可观测度和融合协方差仍是后续协同定位研究范围；论文与代码成熟度分级以专项报告为准。

末端视场中“最近目标”不一定是分配目标。局部相机可能同时看到：

- 中心分配的目标；
- 其他来袭目标；
- 友方资源节点；
- 空中侦察无人机；
- 未知或无关飞行物。

如果局部节点自行换绑 `global_track_id`，会造成重复分配、漏分配、ID Switch 或友方安全风险。因此末端节点只能输出 `TerminalAssociation`，不能直接改写中心分配。

### 1.1 多无人机重叠视场问题

阶段一 AirSim Blocks 或后续离线回放中，会出现多个拦截无人机同时观察同一空域但视场不完全重叠的情况。例如：

```text
UAV1 camera sees: target 1, target 2, target 3
UAV2 camera sees: target 2, target 3, target 4
```

这里 `UAV1` 和 `UAV2` 都可能生成 `local_track_id="L2"`，但它们只是各自相机/MOT 内部的本地编号，不能用字符串相等判断是否为同一目标。D5 必须把本地轨迹限定在 `(resource_id, camera_id, frame_id, local_track_id)` 命名空间下，再通过 D2 提供的 `GlobalTrack`、相机投影、时间戳、姿态和协方差门控，将本地观测配准到既有 `global_track_id`。

单视角目标不是错误：目标 1 只出现在 UAV1，目标 4 只出现在 UAV2，可能是视场边界、遮挡或距离造成的正常现象。D5 不能因为另一个视角未观察到目标就删除航迹或判定分配错误，只能降低跨视角一致性置信度，必要时输出 `hold/reacquire/ambiguous`。

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

### 3.1 当前实际接入状态

当前仓库内 D5 只接入了轻量、可离线复现的几何和证据层，不应把上表开源项理解为已经完整工程化：

| 项目 | 当前状态 |
|------|----------|
| OpenCV `projectPoints` | 已用于单相机投影；OpenCV 不可用时退回针孔模型。当前不做真实 calibration、`solvePnP`、PnP RANSAC 或 bundle adjustment。 |
| AirSim `simGetDetections` | 已有 dry-run bbox adapter，兼容 `box2D`、`bbox_xyxy`、`xyxy` 等 fixture/schema。在线转换忽略 `object_id`、`actor_name`、actor truth ID，并过滤与这些 truth/actor 字段同值的 `track_id/detection_id`。本轮二级节点优先使用该输入口径。 |
| YOLOv8 / ByteTrack | 已有离线 schema adapter 和 `YoloMotAdapter` frame adapter。fallback/native tracker state 按 `(resource_id, camera_id)` 隔离，提供 `reset_stream()` / `reset_all_streams()`；native `persist=True` 使用每 stream 独立 model/tracker，缺依赖/原生 tracker 时退回 per-stream IoU tracker。metadata 记录 stream key、backend/scope、confidence、class id、bbox area/scale 和 CPU/GPU budget；在线转换忽略 truth/global 字段，tracker ID 只作为 `LocalVisualTrack.local_track_id`。 |
| Multi-seed calibration readiness | 已有 `summarize_multiseed_calibration_readiness()`，对 D5 输出的 `TerminalObservation` 与 `CrossViewAssociation` 做字段覆盖审计，标出每个 seed 缺少的 required/recommended 报告字段。truth label 只从离线 metadata 计数，不进入在线关联。 |
| Secondary coverage/funnel diagnostics | 已有 `summarize_secondary_visual_coverage_funnel()`，对普通 replay frame、`TerminalObservation` 和 `CrossViewAssociation` 输出二级覆盖率、联合覆盖率、detect 到 multi-support 漏斗和断点原因。offline target label 只用于覆盖统计，不参与在线绑定。 |
| Mobile high-recon gimbal cue evidence | 已有 `ReconImageCue` 字段和 coverage/cross-view summary metadata，可记录 `cue_position_ned`、`look_at_ned`、云台指向元数据、cue pointing error、gimbal track error、`radar_global_track_cue`、`mobile_high_recon` 和 `mobile_recon_gimbal`；测试覆盖固定俯视不足时机动云台改善二级网络联合覆盖。 |
| BoT-SORT / Deep SORT | `YoloMotAdapter` 可请求 ultralytics BoT-SORT；Deep SORT/ReID 仍作为未来对照。BoT-SORT/Deep SORT 的小目标质量、遮挡恢复、IDSW/IDF1 和算力预算仍需真实图像链路后评估。 |
| ROS 2 `tf2/message_filters` | 只是未来坐标变换和时间同步方案；D5 当前不启动 ROS graph，不订阅 topic。 |
| OpenDroneID / MAVLink signing / DDS Security | 仅通过 `IdentityClaim` 抽象表达仿真身份声明；未接真实报文、密钥、证书或白名单。 |
| AprilTag | 仅作为未来实验室合作目标标识方案；当前没有图像 detector 或 tag ID 到平台身份的可信映射。 |
| Distributed visual association | 已实现 P0 metadata-only DTO 与 `TerminalCrossViewFusion`，输出 peer evidence；未实现三维重投影、三角化或跨相机联合优化。 |

---

## 4. 处理链路

目标工程链路如下，其中 `tf2`、ByteTrack/BoT-SORT/Deep SORT 是预期上游能力，不是当前 D5 代码内已运行组件：

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

当前已实现的 P0 路径是：

```text
Assignment.assigned_global_track_id
-> D2 GlobalTrack + CameraModel
-> projectTracksToImage / cv2.projectPoints fallback
-> LocalVisualTrack[]  # 来自 fixture、AirSim bbox adapter 或外部 detector/tracker schema
-> TerminalAssociator.decide()
-> TerminalAssociation
-> TerminalObservationBus / TerminalCrossViewFusion / TerminalConsistencySummary
```

在线 D5 禁止使用 AirSim `object_id`、`actor_name` 或 actor truth ID。truth ID 只允许作为离线评分标签，计算 `terminal_lock_accuracy`、`locked_mismatch` 或测试断言。

### 4.1 多视角跨视场处理链路

多视角情况下，D5 需要在“单机终端关联”之外增加一个被动跨视场汇总层。该层不分配目标，只把多个局部视觉证据配准到中心/二级节点已有的 `global_track_id`。

```text
UAV1 LocalVisualTrack[]
UAV2 LocalVisualTrack[]
...
-> TerminalObservationBus按(resource_id, camera_id, frame_id, local_track_id)汇聚
-> 对每个GlobalTrack按各相机measurement_timestamp预测
-> 用每个相机的CameraModel把同一GlobalTrack投影到对应图像平面
-> 每个相机内做像素马氏门控和候选代价排序
-> 跨视角合并同一global_track_id的支持证据
-> 输出CrossViewAssociation / TerminalConsistencySummary
```

完全无中心时，当前 P0 metadata-only 链路为：

```text
DistributedVisualObservation[]
+ VisualTrackletSummary[]
+ PeerCameraState[]
-> TerminalCrossViewFusion.build_hypotheses()
-> CrossPeerAssociationHypothesis
-> DistributedTerminalAssociation
-> D4/D6 distributed evidence
```

该链路基于时间窗口、bearing/center_px、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差匹配 peer 视觉 tracklet。缺失或 stale `assigned_global_track_id` 输出 `hypothesis_only/hold`；重复锁定、友方冲突、local/global ID 冲突输出 `hold/ambiguous`。D5 不创建全局 ID，不分配资源。

核心原则：

- `local_track_id` 不跨资源共享语义，只是局部观测编号。
- `global_track_id` 只能来自 D2/D3/D4 的全局航迹和分配计划。
- 一个 `global_track_id` 可以被多个视角同时支持，也可以暂时只有单视角支持。
- 跨视角证据冲突时输出 `ambiguous/conflict/mismatch`，不得由 D5 本地改写 `global_track_id`。

### 4.2 示例：UAV1 sees {1,2,3}, UAV2 sees {2,3,4}

假设 D2 当前维护四条全局航迹：

```text
G1 -> target 1
G2 -> target 2
G3 -> target 3
G4 -> target 4
```

UAV1 的局部 MOT 输出：

```text
UAV1/front/L_a, UAV1/front/L_b, UAV1/front/L_c
```

UAV2 的局部 MOT 输出：

```text
UAV2/front/L_a, UAV2/front/L_b, UAV2/front/L_c
```

即使两个无人机都出现 `L_a/L_b/L_c`，这些 ID 也不能直接比较。正确流程是：

1. 对 `G1/G2/G3/G4` 分别投影到 UAV1 相机平面。
2. 对 `G1/G2/G3/G4` 分别投影到 UAV2 相机平面。
3. UAV1 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G1/G2/G3` 的候选代价。
4. UAV2 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G2/G3/G4` 的候选代价。
5. 对共享目标 `G2/G3`，合并 UAV1 和 UAV2 的支持证据：若两个视角都在门内、时间差可接受、姿态协方差可接受、候选 margin 足够，则提高 `G2/G3` 的跨视角一致性置信度。
6. 对单视角目标 `G1/G4`，保持单视角置信，不因另一架无人机未观察到而判错。若该资源被分配到对应目标，可继续由本资源做单机 `TerminalAssociation`；若投影不可见或候选缺失，则输出 `reacquire`。
7. 若 UAV1 和 UAV2 都对同一个 `global_track_id` 输出 `locked`，但 D3/D4 只允许一个主资源负责该目标，则 D5 只上报“重复锁定风险”，由 D3/D4 仲裁，D5 不自行取消或换绑任一资源。

避免重复锁定同一目标的建议：

- D5 输出 `TerminalAssociation` 时携带 `resource_id`、`assigned_global_track_id`、`local_track_id`、`decision_state` 和 `association_confidence`。
- 跨视场层输出 `CrossViewAssociation`，记录同一 `global_track_id` 被哪些资源支持。
- 若多个资源同时 `locked` 同一 `assigned_global_track_id`，且 AssignmentPlan 不允许多资源协同，则输出 `duplicate_terminal_lock_risk` 给 D4/D3。
- D3/D4 根据计划版本、资源状态、视场质量和任务优先级决定保留哪个资源为主，其他资源降为观察/备份；D5 不直接改分配计划。

---

## 5. 数据结构

当前 `LocalVisualTrack` 保持单相机本地检测/MOT 输出的轻量结构，跨资源命名空间由 `TerminalObservationBus` 或 distributed DTO 提供；不要把 `local_track_id` 字符串直接跨无人机比较。

```text
LocalVisualTrack
- local_track_id
- bbox
- center_px
- bearing_rate
- mot_history_length
- timestamp
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

已实现跨视场摘要结构：

```text
TerminalObservation
- resource_id
- source_node_id
- link_type
- timestamp
- arrival_timestamp
- camera_id
- frame_id
- local_track
- terminal_association
- identity_claims
- recon_image_cues

CrossViewAssociation
- global_track_id
- supporting_resource_ids
- local_track_ids  # resource/camera:local_track_id
- ambiguity_score
- duplicate_terminal_lock_risk
- support_count
- duplicate_lock_resource_ids
- duplicate_local_track_ids

TerminalConsistencySummary
- resource_id
- assigned_global_track_id
- decision_state
- association_confidence
- ambiguity_score
- friend_conflict_state
- candidate_cost_margin
- recon_cue_used
- mismatch_with_assignment
- recommended_d4_action: observe | request_secondary_cue | report_conflict | arbitrate
```

已实现完全分布式 P0 metadata-only 结构：

```text
DistributedVisualObservation
- resource_id / camera_id / frame_id / local_track_id
- measurement_timestamp / arrival_timestamp
- center_px or bearing
- covariance_px or covariance
- bbox / bearing_rate / category / confidence
- assigned_global_track_id / assigned_global_track_stale
- friend_conflict_state

VisualTrackletSummary
- resource/camera/local_track namespace
- bbox_area / scale_rate / observation_count
- assigned_global_track_ids / stale_assigned_global_track_ids

PeerCameraState
- resource_id / camera_id / frame_id
- pose_covariance
- optional position_ned / orientation_quat_xyzw

CrossPeerAssociationHypothesis
- participant_tracklet_keys
- supporting_resource_ids
- support_state
- duplicate_terminal_lock_risk
- global_track_id_conflict / local_id_conflict

DistributedTerminalAssociation
- decision_state: locked | ambiguous | hold | hypothesis_only
- assigned_global_track_id
- supporting_resource_ids
- local_track_ids
- recommended_d4_action

CalibrationSeedReadiness / MultiSeedCalibrationReadiness
- seed_id / ready / missing_required_fields / missing_recommended_fields
- source_counts / detector_backend_counts / tracker_backend_counts
- geometry_log_count / measurement_age_count / local_bbox_count
- truth_label_count / handoff_advisory_count / bbox_stability_count
- duplicate_terminal_lock_risk_count / friend_conflict_count

SecondaryVisualCoverageFunnelSummary
- secondary_single_camera_full_view_frame_rate
- secondary_network_joint_full_view_frame_rate
- secondary_camera_frame_visible_target_counts
- secondary_network_frame_joint_visible_target_counts
- secondary_single_camera_coverage_ratio_mean / min
- secondary_network_joint_coverage_ratio_mean / min
- funnel_counts.detect_count / local_or_recon_cue_count
- funnel_counts.terminal_association_count / cross_view_association_count / multi_support_count
- rejection_reason_counts
- metadata.coverage_mode_counts / capability_class_counts / cue_source_counts
- metadata.mobile_recon_gimbal_improved_joint_coverage_frame_count
- metadata.mobile_recon_gimbal_added_target_ids_by_frame
- metadata.cue_pointing_error_m_by_camera_frame / cue_pointing_error_rad_by_camera_frame
- metadata.gimbal_track_error_px_by_camera_frame

ReconImageCue mobile gimbal fields
- cue_position_ned / look_at_ned
- gimbal_pointing_metadata
- cue_pointing_error_m / cue_pointing_error_rad
- gimbal_track_error_px
- cue_source / capability_class / coverage_mode
```

后续真实多相机三维几何融合仍可新增 `CrossViewObservation/CrossViewTrackEvidence`，携带完整 `CameraModel`、三维候选、重投影残差和协方差摘要；该扩展仍不能改变 D5 不改写 `global_track_id` 的边界。二级覆盖诊断中，`visible_target_ids`/覆盖比例只是离线可见性，`secondary_network_joint_full_view_frame_rate` 是网络并集覆盖，`cross_view_association_count`/`multi_support_count` 才是已形成全局 ID 支持。`mobile_recon_gimbal_improved_joint_coverage_frame_count` 只说明机动云台 evidence 补足固定俯视覆盖，不是 D5 获得云台控制或分配权限。

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

跨视角时，单视角代价先独立计算，再做全局航迹级证据合并：

```text
cross_view_cost(global_track_id) =
    sum(valid_view_costs)
  + timestamp_skew_penalty
  + camera_pose_uncertainty_penalty
  + missing_view_penalty_if_expected_visible
  + duplicate_lock_risk_penalty
```

注意 `missing_view_penalty_if_expected_visible` 只能在几何上确认目标应在该相机视场内时使用。若目标本来就在视场外，不能因为缺失观测惩罚该 `global_track_id`。

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

### 7.1 跨视场汇总伪代码

```python
def cross_view_association(global_tracks, observations_by_resource, cameras, assignment_plan):
    cross_view_results = []

    for global_track in global_tracks:
        supports = []
        conflicts = []

        for resource_id, local_tracks in observations_by_resource.items():
            camera = cameras[resource_id]
            predicted = predict_to_measurement_time(global_track, camera.timestamp)
            projection = project_global_track_to_camera(predicted, camera)

            if not projection.valid:
                continue

            candidates = gate_local_tracks(local_tracks, projection)
            best = select_best_candidate(candidates)

            if best.is_friend_conflict:
                conflicts.append((resource_id, best.local_track_id))
            elif best.is_valid:
                supports.append((resource_id, best.local_track_id, best.cost))

        if conflicts:
            state = "conflict"
        elif len(supports) >= 2:
            state = "consistent"
        elif len(supports) == 1:
            state = "single_view_supported"
        else:
            state = "unknown"

        cross_view_results.append(
            CrossViewAssociation(
                global_track_id=global_track.global_track_id,
                supporting_observations=supports,
                consistency_state=state,
            )
        )

    duplicate_risks = detect_duplicate_terminal_locks(cross_view_results, assignment_plan)
    return cross_view_results, duplicate_risks
```

`single_view_supported` 不是错误状态。它表示当前只有一个视角提供有效证据，需要结合 D2 航迹质量、相机视场覆盖和 D4/D3 分配计划判断是否足够。

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
| UAV1/UAV2 本地ID同名 | 不按 `local_track_id` 字符串合并，必须使用 `(resource_id,camera_id,local_track_id)` |
| 目标2/3被两个视角看到 | 合并为对同一 `global_track_id` 的多视角支持证据 |
| 目标1/4仅单视角可见 | 保持单视角置信，不判为错误 |
| 两资源同时锁定同一目标 | 上报 `duplicate_terminal_lock_risk` 给 D4/D3 仲裁 |
| 二级cue未重投影 | 不得用于本机 `LocalVisualTrack.center_px` 代价计算 |
| AssignmentPlan与末端视觉不一致 | 输出 `mismatch/ambiguous`，触发D4仲裁，不本地换绑 |

---

## 9. 与 D4 主动降级的仲裁接口

D5 是 D4 主动降级的重要观测源，但不是降级决策者。D4 需要判断中心/二级节点分配与末端视觉证据是否一致，并可把 D5 的 distributed evidence 作为 CBBA/分布式仲裁风险加权输入：

| D5 输出 | D4 含义 | 建议动作 |
|---------|---------|----------|
| `locked` 且 `assigned_global_track_id`/版本一致 | 分配与末端视觉一致 | 继续当前计划 |
| 多帧 `ambiguous` | 末端证据不足或候选接近 | 请求二级侦察 cue 或延长观测 |
| `hold` + `verified_friend_overlap` | 友方/合作目标重叠 | 上报冲突，不自动换绑 |
| 多帧 `reacquire` | 视场内无法确认分配目标 | D4 结合 D1/D2/D3 风险主动仲裁 |
| `mismatch_with_assignment=True` | 本地最佳视觉证据长期不支持当前 AssignmentPlan | D4 仲裁中心/二级节点分配 |
| `duplicate_terminal_lock_risk=True` | 多资源可能重复锁定同一目标 | D4/D3 调整主备资源或计划版本 |
| `DistributedTerminalAssociation.decision_state="hypothesis_only"` | peer 视觉证据存在但缺少 current global ID 或单视角不足 | 观察或请求 D2/D3/D4 更新，不让 D5 本地建 ID |
| `DistributedTerminalAssociation.decision_state="hold/ambiguous"` | stale ID、重复锁定、友方冲突、global/local ID 冲突或跨 peer 置信不足 | D4 进行风险加权和仲裁，D5 不解除冲突 |

主动降级触发建议使用连续帧统计，避免单帧检测噪声导致抖动：

- `consecutive_ambiguous_frames >= 5`：请求二级节点 cue 或继续观测。
- `consecutive_reacquire_frames >= 5` 且 D1/D2 航迹质量下降：建议 D4 仲裁。
- `friend_conflict_state="verified_friend_overlap"` 连续出现：上报冲突并保持 `hold`。
- 同一 `global_track_id` 被多个资源 `locked` 且计划不允许多资源协同：上报重复锁定风险。

2026-07-07 代码状态：`TerminalConsistencyTracker` 的连续窗口按 `resource_id + assigned_global_track_id` 维护，`assignment_version` 只作为摘要审计字段输出，不作为窗口 key。因此 D3 对同一资源/目标滚动发布新的 plan version 时，不会清空 D5 的连续 `ambiguous/hold/reacquire/locked` 计数；只有 `assigned_global_track_id` 实际变化才进入新的窗口。

无论 D4 是否决定降级到二级节点或分布式协商，D5 都只能输出视觉配准、身份确认和 advisory summary，不得直接生成新 `AssignmentPlan`，不得选择主备资源，不得触发降级动作，不得改写 `global_track_id`。

---

## 10. 与 D7 视觉比例导引/LOS 的接口

D7 负责末端视觉比例导引或 LOS 角速率导引时，必须以 D5 的保守锁定结果为前置条件。接口原则：

1. 只有 `TerminalAssociation.decision_state == "locked"`，且 `assigned_global_track_id` 与 D3/D4 当前 AssignmentPlan 一致时，D7 才能考虑该视觉目标作为 `visual PN / LOS` 输入。
2. 视觉 PNG 切换还必须满足 bbox 连续稳定、无友方冲突、无重复终端锁定风险、LOS rate 可用、measurement age 新鲜、检测延迟与机动裕度可接受，并通过 D4/D3 gate。
3. D7 输入应包含 `assigned_global_track_id`、`resource_id`、`local_track_id`、图像中心、LOS 角速率、时间戳、置信度和 D5 handoff/prelock metadata。
4. 若 D5 输出 `ambiguous/hold/reacquire/hypothesis_only/mismatch`，或 `annotate_visual_png_handoff()` 给出 `assignment_mismatch`、`duplicate_terminal_lock_risk`、`bbox_area_unstable`、`measurement_age_stale`、`los_rate_unavailable` 等阻断原因，D7 只能进入保持、继续观测或等待上级计划更新的状态，不能自行选择另一个本地目标。
5. D7 严禁根据本地相机“更近”或“更清晰”的目标直接改绑 `global_track_id`。
6. 若二级侦察 cue 参与锁定，D7 应记录 `recon_cue_used=True`，用于 D6 评估 cue 依赖和误锁风险。

推荐 D5 -> D7 消息：

```text
VisualLockForGuidance
- resource_id
- assigned_global_track_id
- assignment_version
- local_track_id
- decision_state == locked
- center_px
- bearing_rate
- association_confidence
- measurement_timestamp
- measurement_age_s
- visual_png_handoff_blockers
- camera_id / frame_id
- recon_cue_used
```

该消息不是处置授权，也不是新的分配计划，只是 D7 视觉导引模块的离线仿真输入合同。

---

## 11. AirSim Blocks 当前实现约束

AirSim Blocks 阶段一适配应保持离线/仿真边界：

- 视觉输入优先来自 `simGetDetections` 或离线检测器/tracker 输出的检测框，再归一化为 `LocalVisualTrack`；D5 已提供 `YoloMotAdapter.process_frame()`，按 `(resource_id, camera_id)` 隔离 fallback/native 状态，依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回 per-stream IoU tracker。main 必须保持 stream key 稳定，单相机重启调用 `reset_stream()`，episode 边界调用 `reset_all_streams()`；真实 AirSim 连续图像流、GPU/CPU 部署参数和多 seed 阈值标定仍由 main/runtime 接线。
- 相机输入必须包含相机内参、相机位姿、图像时间戳和图像尺寸，转换为 D5 `CameraModel`。
- AirSim 默认不要求保存 PNG。若主程序选择保存图像，只能作为离线复盘和可视化，不应成为 D5 逻辑依赖。
- `actor/object_name` 可以作为仿真真值辅助评估 `association_correct`，用于 D6 指标计算和测试断言。
- 正式 D5 关联逻辑不能依赖 `actor/object_name`、`truth_id` 或 `global_track_id` 输入字段作弊。运行时配准必须基于 `GlobalTrack` 投影、局部检测框、时间戳、相机姿态、协方差门控、身份声明和 cue。
- Blocks 中同一目标在不同相机下可能产生不同检测框和本地 ID，必须通过 `global_track_id` 投影门控和跨视角证据合并处理。
- 不调用 AirSim 控制 API，不输出控制量、拦截点、毁伤判断或自动处置动作。

建议阶段一 dry-run 输入：

```text
AirSim detection bbox
-> LocalVisualTrack(resource_id, camera_id, frame_id, center_px, bbox, timestamp)

Offline YOLO/ByteTrack row
-> LocalVisualTrack(local_track_id namespaced by camera/source tracker id)

YOLO/MOT frame
-> YoloMotAdapter.process_frame(...)
-> LocalVisualTrack(local_track_id namespaced by camera/source tracker id)

AirSim camera metadata
-> CameraModel(K, R_cw, t_cw, image_size, measurement_cov)

D2 GlobalTrack
-> project into each camera frame

optional actor/object_name
-> evaluator-only truth label, never used in association decision
```

---

### 11.1 当前 P1 补齐状态与剩余聚焦

D5 侧 P1 已补齐项包括：geometry log fields、detect-to-global outcome/reject reason、registration covariance/timestamp、`TerminalConsistencySummary` 连续窗口、D4 frame-scoped evidence DTO、D7 visual PNG handoff/prelock blockers、AirSim truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter、YOLOv8 + ByteTrack/BoT-SORT frame adapter、per-stream native/fallback MOT、实际 selection/latency/device/continuity、offline detector recall、multi-seed readiness、二级覆盖/漏斗、detect-to-global registration 和 mobile high-recon gimbal cue。native 每 stream 独立 model/tracker 会增加内存/显存与首帧加载开销，但避免静默共享 `persist=True` tracker。上述输出都是 evidence 或 adapter，不赋予 D5 分配、授权、降级、云台控制或导引控制权。

P0 状态：无 blocker。active reacquire 友方声明复检、detection category/truth 隔离、sim-detection actor alias 过滤和端到端 AirSim actor-name local ID 隔离均已闭合；证据路径为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`。D5 不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

60-case 已关闭基础 registration 和 detect-available-but-not-registered 缺口，D5 逐帧 evidence 接口也已关闭；剩余 P1 聚焦 main/D4 同 tick 消费、二级网络完整覆盖、真实 YOLOv8 + ByteTrack/BoT-SORT 多 seed、外参漂移/时间同步、真实遮挡/交叉、友方身份 replay 和 2v2 视觉接管边缘裕量。剩余 P2 保留 Deep SORT/ReID、ROS 2 `tf2/message_filters` 和硬件级三维联合标定。任何增强均不得放宽唯一性、友方冲突、版本、时效或 D7 独立 camera/LOS/maneuver gate；在线 D5 仍不得使用 truth ID 或 tracker ID 生成、改写、换绑 `global_track_id`。

---

## 12. 交付物

1. 末端MOT、几何投影、友方认证综述。
2. ByteTrack、BoT-SORT、Deep SORT、OpenCV、tf2、OpenDroneID适用性评估。
3. `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 数据结构。
4. 匹配代价和保守决策逻辑。
5. 模拟相机投影与歧义场景测试用例。
6. 多视角 `CrossViewObservation/CrossViewAssociation` 接口建议。
7. D4 主动降级仲裁信号和 D7 视觉导引输入合同。
8. AirSim Blocks 检测框/相机元数据离线适配约束。

---

## 13. 参考资料

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
