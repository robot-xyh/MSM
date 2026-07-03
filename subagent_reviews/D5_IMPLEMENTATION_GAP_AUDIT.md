# D5 实现差距审计

**审计范围**：`subagent_reviews/D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_COMMUNICATION_AND_DIFFICULTY_REVIEW.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d5_terminal_association/`、`research_modules/airsim_runtime/d4d5_stress.py`。  
**边界**：本文只审计 D5 末端视觉配准、身份声明、跨视角摘要和 AirSim ComputerVision stress 接口现状，不提出真实控制、处置或硬件接入方案。

## 总体结论

D5 当前已经实现了“离线科研版”的核心安全边界和轻量数据合同：`GlobalTrack -> CameraModel -> image projection -> LocalVisualTrack -> TerminalAssociation`、友方声明模拟、`ReconImageCue` 辅助代价、`TerminalObservationBus` 跨视角摘要、`TerminalConsistencyTracker/TerminalConsistencySummary` 末端一致性摘要、5v5 ComputerVision 检测框 dry-run helper，以及禁止改写 `global_track_id` 的测试。

尚未实现的是完整工业/学术工具链接入：真实 ByteTrack/BoT-SORT/Deep SORT、ROS 2 tf2、OpenDroneID/MAVLink/DDS/AprilTag 协议栈、OpenCV calibration/solvePnP 标定链路，以及跨相机几何联合优化器。当前 P0/P1 已补齐 AirSim stress 中真实调用 `TerminalAssociator` 的端到端路径：`research_modules/airsim_runtime/d4d5_stress.py` 从 replay frame 构造 `GlobalTrack[]`、`Assignment`、`CameraModel`、`LocalVisualTrack[]` 和 `ReconImageCue[]`，再调用 `TerminalAssociator.decide()` 生成 `TerminalAssociation`，最后交给 `TerminalObservationBus`、`TerminalConsistencyTracker` 和 D4 仲裁。

## 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| AirSim `simGetDetections` 输入接入 | **部分实现**。D5 有 `simGetDetections` 风格 fixture 转换器；`d4d5_stress.py` 消费 replay 后的 `AirSimDetectionBox`，不是直接调用 AirSim API。`bbox_xyxy` 已与 YOLO 常见 `xyxy` schema 一并兼容。 | `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_cv_adapter.py`; `research_modules/airsim_runtime/d4d5_stress.py`; `research_modules/d5_terminal_association/tests/test_airsim_cv_5v5_evidence.py` | D5 被设计为离线模块，不直接依赖 AirSim 包；真实采集由 main/runtime 负责。 | 需要 main 继续保持 `simGetDetections` 到 `AirSimDetectionBox` 的稳定字段映射，尤其 camera_id、object_id、timestamp。 | P0 已完成接口兼容，真实 API 调用仍属 runtime 职责 |
| `LocalVisualTrack` 生成 | **已实现基础版**。可由 detection bbox 生成中心点、bbox、类别、质量、时间戳；stress 路径会把回放 bbox 重心重投影到 D5 `CameraModel` 的几何预测附近，用于验证 D5 门控链路。 | `airsim_cv_adapter.py`; `d4d5_stress.py`; `tests/test_airsim_cv_5v5_evidence.py` | 未包含真实 MOT 历史维护，只读取或默认 `mot_history_length`；stress 中为避免第一帧冷启动影响，按稳定观测处理。 | 需要帧间 tracker 缓存、检测器置信度定义、相机帧时间戳。 | P0 已完成 replay 接入；真实 MOT 为 P1 |
| ByteTrack | **未实现**。仅在文档中作为本地 MOT 推荐。 | `D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 当前阶段只做 bbox fixture/dry-run，未引入图像帧、检测器输出和第三方依赖。 | 需要 PNG/RGB frame 或 detector bbox stream、ByteTrack 依赖、帧率、类别与置信度 schema、评估真值。 | P1 |
| BoT-SORT | **未实现**。仅作为运动相机 MOT 候选方案。 | `D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 需要相机运动补偿和 ReID/检测器链路，超出当前 dry-run。 | 需要图像序列、相机运动估计、BoT-SORT 依赖、ReID/检测模型选择。 | P2 |
| Deep SORT | **未实现**。仅作为外观辅助 MOT 对照。 | `D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 小目标外观特征在当前场景未建模；无图像特征提取链路。 | 需要图像帧、检测器、embedding 模型、目标外观真值或 IDSW 评估。 | P2 |
| OpenCV `projectPoints` | **部分实现**。`cv2.projectPoints` 可用时用于世界点投影；不可用时退回针孔公式。 | `research_modules/d5_terminal_association/src/d5_terminal_association/geometry.py` | 只实现投影，不负责标定参数求解。 | 需要上游提供准确 `CameraModel.K/R/t/dist_coeffs`。 | P0 |
| OpenCV `solvePnP` | **未实现**。文档建议，但代码未调用。 | `geometry.py`; `docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前 D5 假设相机外参已由 AirSim/runtime 或上游给出。 | 需要 2D-3D 匹配点、标定板/特征点、PnP RANSAC 策略和外参误差评估。 | P2 |
| OpenCV Calibration | **未实现**。代码只消费内参/畸变，不做相机标定。 | `models.py` 的 `CameraModel`; `geometry.py` | AirSim CV 阶段可直接读取/配置相机参数，暂不需要离线标定流程。 | 需要标定图像、棋盘/AprilTag 角点、重投影误差报告、畸变模型选择。 | P2 |
| ROS 2 tf2 / message_filters | **未实现**。文档选型，D5 代码不依赖 ROS 2。 | `MAIN_COMMUNICATION_AND_DIFFICULTY_REVIEW.md`; `docs/AIRSIM_INTEGRATION_PLAN.md` | 当前 repo 以 Python 离线仿真为主，未启动 ROS 2 节点或 tf tree。 | 需要 ROS 2 runtime、带戳消息定义、frame tree、ApproximateTime 同步策略。 | P2 |
| `GlobalTrack` 到图像平面几何门控 | **已实现单相机版**。预测、投影、协方差传播、马氏门控和候选代价已在 `TerminalAssociator`。 | `associator.py`; `geometry.py`; `tests/test_terminal_association.py` | 完整跨相机联合优化未实现。 | 需要每相机准确 `CameraModel`、D2 航迹协方差、跨相机时间同步。 | P0 |
| `TerminalAssociator.decide()` 保守决策 | **已实现单资源版**。支持 `locked/ambiguous/hold/reacquire`、版本检查、友方 hold、cue bonus。 | `associator.py`; `tests/test_terminal_association.py`; `tests/test_airsim_dry_run_interface.py` | 只评估中心分配的一个 `assigned_global_track_id`，不是全局多目标重分配器。 | 若要扩展被动 competing track 比较，需要全局候选代价矩阵和 D4 summary 派生器。 | P0 |
| `ReconImageCue` | **已实现 P1 摘要基线**。数据结构、scope、age、frame/reproject 字段、代价 bonus 和 used count 已有；stress 中已生成面向当前拦截机相机平面的 reprojected cue。 | `models.py`; `associator.py`; `d4d5_stress.py`; `tests/test_terminal_association.py`; `tests/test_airsim_cv_5v5_evidence.py` | 当前 cue 仍由 replay 真值/几何构造，不是从二级相机图像检测结果反投影再重投影。 | 需要二级相机 pose、二级图像检测、目标三维估计、目标相机 pose、cue age policy、frame_id 校验。 | P1 已完成摘要基线；真实二级图像链路为 P2 |
| OpenDroneID / Remote ID | **模拟实现**。`IdentityChecker` 可解析 `protocol=OpenDroneID` 风格字典并判断 verified/stale/spoof_suspected。 | `identity.py`; `tests/test_terminal_association.py`; `simulations/run_terminal_association_sim.py` | 未接入 OpenDroneID Core C 或真实广播报文。 | 需要 Remote ID 解码器、签名/来源验证、平台白名单、位置一致性校验。 | P1 |
| MAVLink signing | **未实现真实协议**。可通过 `IdentityChecker` 的通用 raw message 字段模拟 signed/signature_valid。 | `identity.py`; D5 review 文档 | 当前没有 MAVLink 消息流或 signing key 管理。 | 需要 MAVLink telemetry source、签名校验库、密钥/系统 ID 策略、时间同步。 | P2 |
| DDS Security | **未实现**。仅在文档中作为 ROS 2 身份/链路认证方案。 | `MAIN_COMMUNICATION_AND_DIFFICULTY_REVIEW.md`; D5 review 文档 | 当前 D5 不运行 ROS 2/DDS middleware。 | 需要 ROS 2 安全 enclave、证书、权限文件、节点身份映射到 `IdentityClaim`。 | P3 |
| AprilTag | **未实现**。仅文档建议作为实验室合作视觉标签。 | D5 review 文档; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 当前没有图像帧解码或 tag detector。 | 需要 RGB/灰度图、AprilTag detector、tag ID 到友方平台映射、误检评估。 | P2 |
| 友方/未知处理原则 | **部分实现**。verified friend overlap 触发 `hold`；unknown 不被升级；stale/unverified/spoof 进入 ambiguous/penalty。 | `identity.py`; `associator.py`; `tests/test_terminal_association.py` | 真实身份来源未接入，只是仿真声明。 | 需要真实身份栈或 main 提供可信 `IdentityClaim` schema。 | P0 |
| 跨视角目标关联 | **已实现摘要层 P1 基线**。`TerminalObservationBus` 按已有 `assigned_global_track_id` 汇总多资源支持、local ID 命名空间、重复锁定风险和 cross-view support count；`TerminalConsistencyTracker` 可消费该摘要生成一致性状态。 | `observation_bus.py`; `models.py`; `consistency.py`; `tests/test_terminal_observation_bus.py`; `tests/test_terminal_consistency.py` | 没有跨相机几何投影融合、时间对齐、姿态协方差、per-view cost。 | 需要 `CrossViewObservation`、每相机 `CameraModel`、D2 `GlobalTrack` 列表、measurement/arrival timestamp 和融合策略。 | P1 已完成摘要基线；几何联合优化 P2 |
| 多个无人机看到不同目标集合 | **已实现摘要处理**。UAV1 看到 G1/G2/G3、UAV2 看到 G2/G3/G4 的 bus grouping 已测试；stress 中每个拦截机视角都会独立调用 `TerminalAssociator.decide()`，再由 bus 汇总同一 global ID 的多视角支持，且不会让任一局部节点改写全局分配。 | `tests/test_terminal_observation_bus.py`; `tests/test_terminal_consistency.py`; `d4d5_stress.py`; `README.md` | 仍不是跨相机联合优化；每视角先独立关联，再做摘要级 cross-view grouping。 | 需要 `CrossViewObservation`、每相机 `CameraModel`、measurement/arrival timestamp 和跨相机联合代价。 | P1 已完成摘要基线；跨相机几何融合 P2 |
| 重复锁定风险 | **已实现摘要信号并进入一致性摘要**。多个资源 `locked` 同一 `global_track_id` 时输出 `duplicate_terminal_lock_risk=True`，并由 `TerminalConsistencySummary` 记录 duplicate resource/local track IDs。 | `observation_bus.py`; `consistency.py`; `tests/test_terminal_observation_bus.py`; `tests/test_terminal_consistency.py`; `tests/test_airsim_cv_5v5_evidence.py` | D5 不负责解除重复锁定，符合边界。 | 需要 D3/D4 消费该风险并生成新 plan/version 或仲裁动作。 | P1 已完成摘要基线 |
| D5 禁止改写 `global_track_id` | **已实现并有测试**。`GlobalTrack` frozen，`TerminalAssociator` 断言输入 ID 不变，bus 只复制 assigned ID。 | `models.py`; `associator.py`; `tests/test_terminal_association.py`; `tests/test_airsim_dry_run_interface.py` | 无需实现改写能力；这是硬边界。 | 仍需在 main/integration 中保持 D5 输出只作为 evidence，不作为 assignment authority。 | P0 |
| D5 是否生成 `AssignmentPlan` | **未生成，符合要求**。D5 只输出 association/evidence/metrics；`AssignmentPlan` 只在文档字符串中作为禁止项出现。 | `airsim_cv_adapter.py`; `README.md`; `D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md` | D5 不是分配模块。 | 需要 D3/D4 明确消费 D5 evidence 后再改 plan。 | P0 |
| D4/D5 stress 是否真实调用 `TerminalAssociator` | **已实现 P0**。`d4d5_stress.py` 导入并实例化 `TerminalAssociator`，每帧每个拦截资源调用 `decide()`；测试用 spy 校验调用次数。 | `research_modules/airsim_runtime/d4d5_stress.py`; `research_modules/airsim_runtime/tests/test_blocks_runtime.py` | 仍使用 replay 真值构造 `GlobalTrack` 和 look-at `CameraModel`，不是完整 D2/D3/真实 tf 链路。 | 需要 main integrated episode 提供真实 D2 `GlobalTrack`、D3 assignment、相机外参和时间同步。 | P0 已完成，集成真实上游为 P1 |
| AirSim replay 中真实 `TerminalObservationBus` 使用 | **已实现**。`d4d5_stress.py` 使用 bus 汇总观察和 cross-view associations；bus 输入已改为 `TerminalAssociator.decide()` 输出。 | `d4d5_stress.py`; `tests/test_blocks_runtime.py` | bus 仍是摘要层，不做分配和跨相机联合优化。 | 需要 D3/D4 消费 cross-view risk 和 `TerminalConsistencySummary`。 | P0 |
| 5v5 stress 指标 | **部分实现**。D5 helper 有 D5-only metrics；`d4d5_stress.py` 自己计算 per-camera、multi-target、overlap、accuracy、ambiguous。 | `airsim_cv_adapter.py`; `d4d5_stress.py`; `tests/test_airsim_cv_5v5_evidence.py` | D5 helper 和 runtime stress 指标实现重复，尚未统一。 | 需要 main/runtime 复用 D5 helper 或明确二者职责：D5 pure helper vs runtime aggregate metrics。 | P1 |
| `TerminalConsistencySummary` | **已实现 P1 基线**。D5 新增 `TerminalConsistencySummary`、`TerminalConsistencyConfig` 和 `TerminalConsistencyTracker`，可记录 decision state、confidence、ambiguity、friend conflict、candidate margin、recon cue、lock age、连续 `locked/ambiguous/hold/reacquire` 帧数、丢锁/重捕获事件、重复锁定风险和 cross-view support。 | `models.py`; `consistency.py`; `tests/test_terminal_consistency.py`; `README.md`; `docs/ALGORITHM_AND_IMPLEMENTATION.md` | 不适用；当前仍是摘要层，不替代 D4 自有仲裁模型 | 后续需 main 将该 summary 映射到 D4 `TerminalAssociationSummary` 和 D6 `TerminalRecord/EventRecord` | P1 已完成模块基线 |
| 真实图像保存/处理 | **未实现，当前不要求默认保存 PNG**。D5 使用 bbox metadata 和 fixture。 | `MAIN_COMMUNICATION_AND_DIFFICULTY_REVIEW.md`; `docs/AIRSIM_INTEGRATION_PLAN.md` | CV 5v5 阶段默认 metadata-only，避免图像链路复杂度。 | 若接入 MOT/AprilTag，需要图像帧或 detector 输出流。 | P2 |

## 关键风险与建议

1. **P0 缺口已关闭：`d4d5_stress.py` 已调用 `TerminalAssociator`**。当前 stress 报告不仅验证 D4 仲裁链路和 D5 evidence 格式，也能证明 D5 几何投影、马氏门控、`ReconImageCue` bonus 和 `locked/reacquire` 决策在 AirSim replay 中真实执行。下一步重点是把 replay 真值构造的 `GlobalTrack/CameraModel` 替换为 main 集成链路中的 D2/D3/tf 输入。

2. **跨视角当前是摘要关联，不是几何融合**。`TerminalObservationBus` 和 `TerminalConsistencyTracker` 能回答“哪些资源报告同一个全局 ID、是否重复锁定、是否丢锁/重捕获”，不能回答“不同相机中的 bbox 是否几何上一致支持同一目标”。要完成 UAV1 `{1,2,3}`、UAV2 `{2,3,4}` 的真实跨视角配准，需要 `CrossViewObservation`、每相机 `CameraModel`、每观测时间戳和跨相机投影代价。

3. **MOT 与身份认证仍是模拟层**。ByteTrack/BoT-SORT/Deep SORT、OpenDroneID、MAVLink signing、DDS Security、AprilTag 都还没有真实库接入。当前 D5 只消费它们可能产生的抽象输出：`LocalVisualTrack` 或 `IdentityClaim`。

4. **OpenCV 已用于投影，但不是完整标定工具链**。`cv2.projectPoints` 对齐了标准投影接口；`solvePnP` 和 calibration 尚未实现，因为当前 AirSim/runtime 假设能直接提供相机内外参。

5. **`global_track_id` 边界实现较稳**。模型冻结、单测和 bus 设计都表明 D5 不应、也不会成为分配权威。后续集成重点是防止 main/D4 把 D5 的 `observed_global_track_id` 或 truth metadata 误用为 D5 自行换绑结果。
