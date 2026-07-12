# D2 数据关联模块计划

## 1. 范围与安全边界

D2 只负责离线科研仿真、日志回放和多目标数据关联评估。模块目标是维护稳定的 `global_track_id`，降低多目标交叉、密集编队、短时遮挡、漏检和虚警条件下的 ID Switch 风险。

本模块不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程或绕过人工授权的能力。`engageable` 只是代码中的研究状态，表示航迹质量足以供下游离线分配实验使用，不代表授权、处置或控制含义。

规模边界必须保持清晰：2v2、5v5、`crossing_dense_5v5` 都只是 baseline fixture 或回放场景名。D2 的关联器、Tracker、metrics 和 dry-run adapter 均按每帧传入的 `tracks`、`detections`、`active_tracks` 长度运行，不从场景名推断目标数量，不把 main runtime 的 `--drone-count N` 复制成内部常量。

## 2. 当前代码状态概览

当前 D2 可运行路径依赖 NumPy、SciPy 和 pytest。默认在线工程主线仍是 `GNNHungarianAssociator` + 马氏门控 + 二维常速度 Kalman fallback + `Tracker` 生命周期状态机，本轮 P2 benchmark 没有替换该路径。JPDA 和 MHT 已有接口兼容、可执行的研究近似，但不是完整生产级 JPDA filter 或 MHT hypothesis manager。Stone Soup、FilterPy 已有 optional 版本/原因探测、对象 adapter 和 frozen replay smoke benchmark，但不进入默认运行路径或 requirements。

代码和测试已覆盖：

- `GNNHungarianAssociator` 使用 `scipy.optimize.linear_sum_assignment` 做一对一硬关联。
- GNN/Hungarian 主线在马氏门控和 Hungarian 求解前后保留原路径，并新增速度方向、短时历史和加速度异常组成的 motion consistency cost/diagnostics。
- `build_gated_cost_matrix()` 支持 quality-aware gate baseline，按 track quality、局部目标密度、位置协方差和上一帧 association risk 对每条 track 的 gate 做轻量调整。
- `DataAssociator` 抽象接口支持替换 GNN、JPDA、MHT。
- `Tracker` 使用 `[x, y, vx, vy]` 状态、4x4 covariance、Joseph update 和确定性状态机。
- `TrackLifecycleState` 当前枚举为 `tentative -> confirmed -> engageable -> lost -> dropped`，没有 `engaged` 状态。
- 每条 `GlobalTrack` 输出 `track_quality`、`association_risk` 和 `quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 与 `MetricsRecorder.summary()` 同步输出 track-level 质量/风险字段。
- `MetricsRecorder.summary()` 输出 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`truth_metrics_available`、`continuity_available`、`duplicate_assignment_count`、RMSE、confusion matrix、runtime 和关联风险字段；无 offline truth label 时 continuity 数值只为报告兼容，不参与硬风险，旧 replay 缺 availability 字段时也按不可用处理。
- `AssociationRiskSummaryWindowGenerator` 可从代价矩阵、候选数、cost margin、ID switch delta、duplicate delta、可用 continuity 和 D5 disagreement 生成滑窗风险摘要。
- `RiskThresholds` 和 `classify_risk_summary()` 已把 D2 风险证据拆为 D4 对齐的软风险与硬风险。
- `detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、2D covariance 投影、`global_track_id` 和 metadata。
- `run_airsim_dry_run_association()` 支持 synthetic AirSim-style frame，不 import `airsim`，并在 bus message 中导出当前活动航迹和 `global_track_ids`。
- `load_airsim_replay_frames()` 可读取离线 JSON/JSONL replay 并保留 wrapper 中的 seed/episode/scenario/frame/offline truth label 校准元数据，`run_airsim_replay_association()` 输出 association logs、summary、风险分层和 replay metadata，`run_threshold_sensitivity()` 输出 gate/risk threshold 敏感性矩阵、`risk_profile_version`/`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary 和软/硬风险聚合字段，`summarize_multi_seed_risk_calibration()` 汇总多 seed IDSW/continuity/duplicate/soft-hard risk 分布并给出推荐阈值摘要。
- `AssociationLogEntry` 完整携带默认空 `rejected_pairs`，replay gate summary 可分别统计 `mahalanobis_gate` 和 `assignment_above_gate`，旧 JSON 缺字段按空列表处理。
- Detection/GlobalTrack covariance 输入治理已落地：非有限、明显非对称、明显非 PSD 输入显式拒绝；仅数值容差内对称化或特征值 floor。对象与 association metadata 同时记录最新 `covariance_consistency` 和 `last_regularization` 历史证据，避免预测/更新后沿用初始化诊断。
- 测试包含 3 目标 dry-run episode，证明输出数量来自输入集合长度；同时包含 2v2 replan baseline，证明中心/二级切换时可保持稳定 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count` 的系统规则已有合同测试：D2 `MetricsRecorder.id_switch_count` 与 D6 episode 统计口径一致。
- P1 replay governance 已实现：`run_airsim_replay_association()` 默认启用在线 truth isolation；在线 detection ID 按帧匿名化，actor/truth 元数据递归清除；`OfflineTruthEvaluation` 独立计算 identity/continuity、M-of-N 初始化、false-track 和 NEES，NIS 则由不依赖真值的在线 innovation 计算。每帧 association log 固化 `d2-association-log/v2`、risk profile/version、measurement/active-track count 和 NIS availability，不携带 truth label、truth target count 或 NEES。
- P1 offline truth 合同已冻结为 `d2-offline-truth-label/v1`：每条 JSONL 记录携带 episode、frame、timestamp、truth ID、二维 position 和可选匹配注释。在线帧递归移除 truth，离线标签仅在 association 完成后恢复为 evaluator-only 视图；缺标签时 IDSW/continuity/NEES 显式 unavailable。
- P1 deterministic calibration runner 已实现：通用 N-target dense crossing fixture 覆盖连续漏检/遮挡和虚警，默认 5-target 仅为基准；runner 强制至少 10 个唯一 seed，输出每 seed 与聚合 IDSW、continuity、NIS/NEES availability、gate/risk profile/version、runtime 和确定性签名。
- P2 optional benchmark v2 已收敛：同一 frozen replay digest 下固定运行默认 GNN/Hungarian，并可显式运行模块内 JPDA/MHT research adapter 和 Stone Soup/FilterPy object adapter。GNN/JPDA/MHT 共用 `Tracker` 生命周期，truth 只在运行结束后进入 offline evaluator；每行统一输出 IDSW、continuity、latency 和 `unavailable_reason`。外部 object adapter 的身份指标保持 unavailable，完整 JPDA/MHT 和端到端 FilterPy tracker 仍声明未实现。
- P1 governed input adapter 已支持 D1 `serialize_governed_replay`：识别 manifest v1/observation v1，按 `airsim_frame_index + measurement_timestamp` 聚合，用 radar `[range, azimuth, elevation]` 和传感器 NED 外参生成水平 N/E detection/covariance；声学 bearing 和 EO pixel 记录不做错误混合，跳过统计进入报告 metadata。旧 AirSim replay loader 兼容保留。它是 P1 truth-isolated 合同边界，不是 P2 第三方库 benchmark。
- M 对 N cross-node 注册基础已实现：6D NED `SourceTrackSummary`、source-local namespace、公共时刻 CV 传播、协方差感知 track-to-track gate、按 source 分组 Hungarian、canonical multi-source binding/history、payload/lineage/stale 防重，以及 exact/unknown/duplicate 三类相关性决策。
- `CrossNodeRegistryMetrics` 保持 truth-free，只统计 operational rebind、duplicate rejection 和 latency；`OfflineCrossNodeMetricsEvaluator` 通过独立 source-key truth mapping 计算 cross-node IDSW、canonical duplicate 和 association precision/recall。
- D2 回归覆盖 D1 governed manifest/records、匿名化、radar projection、模态跳过、offline position matching、旧 replay 兼容，以及 P2 五行输出、truth-free tracker 输入、缺依赖和未知 adapter 拒绝。

### 2.1 P0/P1 缺口快照

- **P0**：无 P0 blocker。GNN/Hungarian、马氏门控、可插拔 `DataAssociator`、`id_switch_count`、`track_continuity`、risk summary、D1 adapter、AirSim dry-run adapter、按输入集合长度运行、P0-B `track_quality`/`association_risk`、motion consistency cost 和 P0-C quality-aware gate baseline 均是当前主线并已有测试覆盖。
- **P1 合同层已闭合**：D1 governed adapter、association log schema/profile、在线 truth isolation、独立 offline evaluator、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed calibration runner、availability-aware summary、M-of-N/false-track/NIS/NEES 接口及 cross-node canonical registry 基础均已实现并回归。
- **P1 长期标定仍开放**：专用更长真实 AirSim dense/crossing replay，以及 gate/risk、M-of-N 生命周期、false-track、NIS/NEES 的多 seed 参数标定仍需继续。这些开放项不回退 D2 P1 合同层和 synthetic dense calibration runner 的完成状态。D2 不直连 AirSim SDK，也不以物理拦截成功率替代身份连续性验收。
- **2026-07-12 代码状态**：`33e6fa0` 只增强 main/runtime 与 D4-D7 的 PNG delivery 链路；其后的 D2-owned P1 任务增加 long governed replay runner/schema，但默认在线路径仍为 GNN/Hungarian。当前指定模块回归为 `69 passed, 1 warning`，warning 是本机 Matplotlib `Axes3D` 多版本导入问题。
- **2026-07-12 AirSim 证据边界**：PNG delivery 报告记录 2v2 candidate 10 seeds 为 20/20 pair、在线 truth 使用为 0；锁定后两帧 dropout 沿原 global/local track 与计划上下文预测，没有 truth ID 或本地 ID 重写。M5N2 8 s 短窗口为 0/9，且报告明确该批次不是同几何、同时间窗的长期对照。以上证明下游身份/truth-isolation 合同未退化，但报告没有 D2 专项 association log、隔离 offline IDSW/continuity 或真实 dense/crossing 长回放，不能新增 D2 算法完成项。
- **开放 P0/P1 与下一验收**：P0 无开放项。P1 synthetic 长 replay、独立 offline truth、至少 10 seeds 的 IDSW/continuity/false-track/RMSE/NIS/NEES availability 与 risk/gate/scenario version 已闭合；性能 backlog 是冻结真实 dense/crossing/OOSM replay并做阈值参数标定。跨节点部分还需 D1 数值 exact/CI posterior 回写、多 seed 高歧义 replay 和 owner/epoch failover 验证。
- **历史基线，2026-07-10**：当时的 5v5 60-case 和 2v2 10-seed 不是 D2 dense/crossing 真值回放，因而在当时不足以关闭 D2 P1。本段不代表当前状态。
- **历史过渡证据，2026-07-11 早期**：truth-isolated 短 episode 及 seeds 7/17/27 当时只证明 D2 -> D3/D6 通路与单 primary 合同收敛，T001 双 primary 尚未通过。本段不是当前结论。
- **2026-07-11 合同验收证据**：M=5、N=2 ComputerVision 的 T001 双 primary 共识/计划授权为 8/10；`id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。二级与完全分布式 commit 正例通过，缺 ACK 时 fail-closed；这验证下游使用 D2 中心 ID 的合同，不表示 D2 本地重绑 ID。
- **P2 边界保持原状态**：P2 仅是隔离 benchmark；模块内 JPDA/MHT 是显式研究近似，Stone Soup 1.9.1/FilterPy 1.4.5 仅对象 adapter smoke，默认在线 GNN 路径未替换。

## 3. 输入输出合同

### 3.1 D2 输入

当前可执行实现的核心输入是二维 `Detection`：

- `detection_id`：单帧观测 ID。
- `timestamp`：量测时间，适配 D1 时来自 `measurement_timestamp`。
- `position`：二维位置或三维 NED 的水平投影 `[north, east]` / `[x, y]`。
- `covariance`：2x2 量测协方差；D1 6x6 或 AirSim-style 3x3 covariance 会投影到二维。D2 对投影后实际参与门控的 covariance 执行有限性、对称性和 PSD 校验，容差内修复必须留诊断。
- `truth_id`：仅用于离线评估和 D6 指标，不应作为在线身份决策依据。
- `feature`：可选外观、类别、声纹或其他 embedding，当前用简单欧氏差异参与代价。
- `metadata`：保留来源、frame、timestamp、truth_position、`global_track_id` 等调试和回放信息。

D2 假设输入已经被调用方整理到可处理的帧序列。OOSM、异步传感器回溯和三维传感器原始融合主要属于 D1/main 集成责任；D2 当前只保留投影和 metadata 透传能力。

### 3.2 D2 输出

D2 输出包括 `GlobalTrack`、`AssociationResult`、`AssociationLogEntry` 和 metrics summary：

- `GlobalTrack.global_track_id`：D2 维护的稳定身份键。
- `GlobalTrack.state`：当前实现固定为 `[x, y, vx, vy]`。
- `GlobalTrack.covariance`：4x4 状态协方差。
- `GlobalTrack.lifecycle_state`：`tentative/confirmed/engageable/lost/dropped`。
- `GlobalTrack.track_quality` / `association_risk` / `quality_metadata`：D2-owned track-level 质量、关联风险和解释字段。
- `AssociationResult.matched_pairs`：`(track_id, detection_id, cost, probability)`。
- `AssociationResult.unmatched_track_ids` / `unmatched_detection_ids`：漏配和新建轨迹依据。
- `AssociationResult.ambiguity_score`、`rejected_pairs`、`metadata`：解释门控拒绝、候选数量、covariance consistency、motion consistency、quality-aware gate、track quality/risk、求解器、JPDA/MHT 截断等信息；`AssociationLogEntry` 必须保留同一 `rejected_pairs`。
- `MetricsRecorder.summary()`：D2/D6 必须保留的 `id_switch_count`，以及 continuity 数值与可用性标志、duplicate、risk、runtime、confusion matrix。

`global_track_ids` 导出列表必须来自当前活动航迹集合，不按 2 或 5 个目标预分配、截断或补齐。真实 replay 默认使用在线/离线双层合同：在线层将源 detection ID 匿名化且不含 truth，离线层按同帧输入顺序对齐匿名 detection、标签和 truth state，并在关联结束后计算评估指标。

## 4. 已实现能力

### 4.1 GNN/Hungarian 主线

`GNNHungarianAssociator` 是默认工程路径。它先调用 `build_gated_cost_matrix()` 计算 `N x M` 代价矩阵，其中 `N=len(active_tracks)`，`M=len(detections)`；门外候选使用大代价并记录 `RejectedPair(reason="mahalanobis_gate")`。随后通过 SciPy Hungarian 求解一对一最小代价匹配，匹配后仍会拒绝超门限 pair。

已输出的解释信息包括：

- `cost_matrix` 和 `distance_matrix`。
- `motion_consistency_cost_matrix`、`motion_consistency_by_pair` 和 `motion_consistency_by_track`。
- `gate_thresholds_by_track`、`target_density_by_track`、`pre_association_track_quality_by_track` 和 `previous_association_risk_by_track`。
- `candidate_counts_by_track`。
- `candidate_counts_by_detection`。
- `ambiguity_score`。
- `rejected_pairs`。
- `solver="scipy.optimize.linear_sum_assignment"`。

### 4.2 可插拔关联器接口

`DataAssociator.associate(tracks, detections, timestamp)` 是插件边界。`Tracker` 不关心底层使用 GNN、JPDA 还是 MHT，只消费统一的 `AssociationResult`。这使得关联器可替换，但 metrics、状态机、风险摘要和 dry-run adapter 仍可复用。

### 4.3 Track 状态机

`Tracker` 当前状态机为：

```text
tentative -> confirmed -> engageable
       miss threshold -> lost -> dropped
       hit after lost -> confirmed 或 engageable
```

状态转移由命中数、连续命中、漏检数、协方差迹和身份置信度驱动。所有转移写入 `TrackTransition`，并附带原因字段，例如 `confirmation_hits_reached`、`quality_threshold_reached`、`lost_miss_threshold_reached`、`drop_miss_threshold_reached`。

### 4.4 指标和风险摘要

D2 已实现并测试以下核心指标：

- `id_switch_count`：同一 truth 的代表 `global_track_id` 发生变化时计数。
- `track_continuity`：当前是 `identity_continuity` 的别名，表示身份连续性；仅当 `continuity_available=true` 时可解释和参与风险阈值。
- `identity_continuity`：真值存在期间由同一身份稳定覆盖的比例。
- `coverage_continuity`：真值存在期间是否被任意航迹覆盖。
- `duplicate_assignment_count`：同帧重复 detection/track 或同一 truth 被多个 track 覆盖。
- `rmse`：位置误差，仅作为几何精度指标，不能替代身份指标。
- `confusion_matrix`：truth-to-track 分布。
- `runtime_seconds_by_associator`：算法耗时。

风险摘要已经有代码基线：`AssociationRiskSummaryWindowGenerator` 从候选重叠、cost margin、ID switch delta、duplicate assignment delta、continuity risk、D5 disagreement 和 metadata 生成 `AssociationRiskSummary`，并进入 `AssociationLogEntry` 与 summary 字段。`classify_risk_summary()` 使用 `RiskThresholds` 将软风险（ambiguity/cost margin/candidate overlap/D5 disagreement）和硬风险（IDSW、duplicate、continuity collapse）分层输出，供 D4/D6 回放标定使用。

### 4.5 N 规模输入与 dry-run bus 输出

D2 已有非 2/5 数量测试：3 目标 synthetic AirSim-style dry-run episode 产生 3 个活动航迹和 3 个 `global_track_ids`。这证明 `global_track_id` 输出数量由输入帧和 Tracker 状态决定，而不是由场景名决定。

2v2 active-degradation/replan 测试是身份合同 baseline：中心到二级节点切换时，如果同一 replay episode 使用同一个 Tracker 状态，D2 应通过关联和 Kalman update 保持同一 physical target 的 `global_track_id`，并保持 `id_switch_count == 0`。

### 4.6 AirSim-style replay 与阈值敏感性 helper

D2 侧 P1 已补离线 replay 读写和阈值敏感性 helper：

- `load_airsim_replay_frames(path)` 读取 JSON/JSONL，支持顶层 frame、`frames` 数组以及混合 episode JSONL 中的 `frame`/`d2_frame`/`airsim_frame` payload，并把 wrapper/top-level 中的 `seed`、`episode_id`、`scenario_name`、`drone_count` 等校准字段保留为 `replay_metadata`。
- `run_airsim_replay_association(frames, gate_thresholds=...)` 复用现有 Tracker，输出 `ReplayAssociationReport`，其中包含 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、association logs、当前 `global_track_ids`、`replay_metadata` 和软/硬风险摘要。
- `ReplayAssociationReport.risk_summary` 和 `threshold_sensitivity` rows 稳定输出 `association_risk_threshold_version`、gate pass/reject count、motion consistency risk summary、track quality/association risk summary；`threshold_sensitivity_summary` 汇总 dense/crossing 场景标签、IDSW、continuity、duplicate 和 soft/hard risk frame rate 分布，便于 D6 bundle 做真实 5v5 replay 分组。
- `write_replay_association_report()` 与 `write_association_logs_jsonl()` 固化 D2-owned report/log 输出格式，便于 main/D6 后续消费。
- `run_threshold_sensitivity()` 对 gate threshold 与 risk threshold profile 做离线 sweep，逐项输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`、`association_risk_threshold_version`、seed/episode/scenario/frame 元数据、gate/motion/quality diagnostics、soft/hard risk frame count、max risk score 和 risk summary。
- `summarize_multi_seed_risk_calibration()` 汇总多个 seed/episode 的 threshold sensitivity rows，按 gate/risk profile/version 输出 IDSW、continuity、duplicate、soft/hard risk count/rate/score 分布、dense/crossing sensitivity summary、风险原因集合和推荐阈值摘要。
- `OfflineTruthLabel`、`write/load_offline_truth_labels_jsonl()` 与 `evaluation_frames_with_offline_truth()` 固化独立 truth 文件，并让 `run_airsim_replay_association(..., offline_truth_labels=...)` 在在线关联完成后复用原 evaluator。
- `run_dense_crossing_calibration()` 复用上述 replay/evaluator/risk summary，强制至少 10 个唯一 seed，并通过 `summarize_dense_crossing_calibration()` 显式统计 available/unavailable seed。
- `load_airsim_replay_frames()` 在旧 frame schema 前识别 D1 governed bundle；转换后的 online frame 不携带 observation ID、lineage 或 truth，离线 `offline_only` labels 仅在 evaluator 副本中用位置 Hungarian 建立评分映射。
- `tests/test_replay.py` 与 `tests/test_calibration.py` 覆盖 5 目标 AirSim-like replay、动态 N、truth JSONL round-trip/隔离、阈值版本、无 truth availability、同 seed 复现和 10-seed 聚合。

该 helper 不连接 AirSim runtime，也不从场景名推断目标数量；真实 ComputerVision 图像/metadata 采集、episode JSONL 生产和跨模块 schema 发布仍由 main/runtime/D6 负责。

## 5. 部分实现能力

### 5.1 JPDA

`JPDAAssociator` 是可执行研究对照，不只是空接口。它会：

- 对每条 track 选取门内候选。
- 枚举小规模一对一联合假设。
- 根据马氏代价、`detection_probability` 和 `clutter_density` 计算假设似然。
- 归一化得到 marginal probability。
- 用 `min_marginal_probability` 输出非冲突匹配。
- 在 metadata 中写入 `joint_hypothesis_count`、`truncated` 和 `marginal_probabilities`。

但它不是完整 JPDA filter。当前没有概率混合状态更新、完整协方差融合、track coalescence 抑制、参数标定流程或生产级大规模分簇策略。目标/观测数增大时依赖 `max_joint_hypotheses` 截断。

### 5.2 MHT

`MHTAssociator` 也是可执行研究对照。它维护有界 `_branches`，每帧扩展合法分配，加入漏检和虚警惩罚，保留 `max_hypotheses`，并用 `max_history` 限制历史长度。

但它不是完整 MHT。当前没有 N-scan pruning、track-oriented/tree-oriented 完整假设管理、分簇、长期分支合并、中心算力预算或多帧回溯确认策略。它的定位是接口兼容和离线对照基线。

### 5.3 IMM/EKF/UKF

IMM、EKF、UKF 目前是研究计划项，不是已落地代码。D2 的 `Tracker` 只有二维线性常速度 Kalman fallback。`to_filterpy_state()` 和 `filterpy_filter_from_detection()` 只映射二维 CV `KalmanFilter` 并用于对象更新 smoke，不实现 IMM、EKF、UKF 或端到端关联。

如果后续证明机动预测误差是 ID Switch 主因，应先定义三维 NED 或二维机动模型、量测模型、协方差合同和评估场景，再决定是否接入 FilterPy 或自研 IMM/EKF/UKF。

## 6. 隔离式外部库状态

### 6.1 Stone Soup Detection adapter

`to_stonesoup_detection()` 已把在线安全的 D2 `Detection` 映射为 Stone Soup `Detection/StateVector`。`run_optional_framework_benchmark()` 可在 frozen replay 上测量转换 latency；隔离环境 Stone Soup 1.9.1 已实测执行成功。当前没有 Stone Soup `Track`、predictor/updater、JPDA 或 MHT tracker，因此 adapter 行不得输出 IDSW/continuity 数值。

暂未接入原因：

- 默认回归需要保持 NumPy/SciPy/pytest 轻依赖。
- 不希望把 Stone Soup 对象暴露到跨模块总线。
- D2 先固化 `DataAssociator`、`AssociationResult`、metrics 和 D1/D6 合同，再做外部框架对照。
- 尚缺真实多 seed AirSim CV replay、密集交叉和遮挡 sweep 来证明完整 JPDA/MHT 的收益。

缺少条件：

- Stone Soup predictor/updater、Track 生命周期和完整关联器映射。
- 完整 JPDA/MHT 的状态混合、假设管理、剪枝和同预算验收。
- 真实 replay 数据集、truth labels、容差和对照报告。

### 6.2 FilterPy CV object adapter

当前已创建 FilterPy `KalmanFilter` CV 对象 adapter，可从 D2 `GlobalTrack` 或 `Detection` 初始化，并在 benchmark 中执行 predict/update；隔离环境 FilterPy 1.4.5 已实测成功。它没有替换 D2 Tracker，也不维护跨帧关联身份，所以 IDSW/continuity 保持 unavailable。`ExtendedKalmanFilter`、`UnscentedKalmanFilter` 和 `IMMEstimator` 仍未实现。

暂未接入原因：

- 当前二维常速度 Kalman fallback 足以支撑 phase-1 数据关联、状态机和指标验证。
- EKF/UKF/IMM 需要更明确的机动目标模型、非线性量测模型和三维/二维状态选择。
- 引入 FilterPy 会增加依赖和参数面，若没有证明 IDSW 改善，容易增加维护成本。

缺少条件：

- CV/CA/CT 或其他机动模型集。
- 模型转移概率和协方差初始化策略。
- 雷达球坐标、相机投影或三维 NED 量测雅可比/无迹变换定义。
- 与 GNN/JPDA/MHT 共同评估的机动场景。

### 6.3 其他未实现项

- 原生 3D NED tracker：当前 `Detection` 固定二维，`GlobalTrack` 固定四维状态。
- JPDA/MHT 自动升级：当前由仿真 CLI 或调用方显式选择 associator，`Tracker` 内没有按风险阈值自动切换。
- 真实 AirSim runtime 采集链路：D2 已能消费离线 JSON/JSONL AirSim-like replay 并输出 association report/log，但不接 AirSim SDK、不采集 ComputerVision 图像/metadata，也不负责 main/D6 episode JSONL 生产。
- OOSM 回溯和平滑：当前假设输入帧已按时间整理。
- py-motmetrics/CLEAR MOT：仅可作为未来离线评估参考，当前未作为依赖或测试路径。

## 7. D2 输出如何供 D3/D4/D5/D6 使用

### 7.1 D3

D3 用 `global_track_id`、状态、协方差和 lifecycle state 构造资源-目标分配输入。D2 应向 D3 暴露当前活动航迹集合；D3 应优先消费 `confirmed` 和 `engageable`，对 `tentative`、长期 `lost`、高风险或高歧义航迹提高代价、延迟分配或等待重评估。

D2 不生成 D3 `AssignmentPlan`，也不修改分配版本。D3 的 versioned plan 和 stale version rejection 仍由 D3 负责。

### 7.2 D4

D4 不直接使用 D2 结果切换系统模式，而是把 D2 的 `AssociationRiskSummary`、`id_switch_count`、continuity、duplicate risk、D5 disagreement 和 source/link metadata 作为主动降级证据。D2 只发布风险证据，例如 `association_ambiguity`、`duplicate_track_risk`、`covariance_overlap_rate`；是否请求中心重规划、二级节点接管或分布式协同由 D4 综合 D1/D3/D5 信号仲裁。

2026-07-07 的 main runtime bus / D4 P1 修复后，D2 风险证据在 D4 中应按以下分层解释：

- **软风险证据**：`association_ambiguity`、cost margin risk、candidate overlap、短时 D5 disagreement。它们表示当前硬关联不确定，默认只支持继续观察、提高 D3 迟滞、请求二级节点 cue 或进入离线 JPDA/MHT 对照，不应单帧触发 `request_center_replan`。
- **硬风险证据**：`id_switch_count` 或窗口 delta 大于 0、`duplicate_assignment_count`/`duplicate_track_risk` 增长、`track_continuity` 低于阈值。这些说明规范 `global_track_id` 连续性已经受损或重复解释已经发生，可作为 D4 主动仲裁的硬证据。
- **D2 边界**：D2 不知道 D3 plan 是否过期，也不判断 D5 末端锁定是否授权。D2 只把上述证据写入 summary/log；D4 再结合 D1、D3、D5 和通信/二级节点状态选择 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary` 或 `degrade_to_distributed`。

### 7.3 D5

D5 使用 `global_track_id` 将中心航迹投影到终端相机或局部目标候选上。D5 可以回传 `TerminalAssociation`、`IdentityClaim`、候选 ID、末端不一致和锁定/保持状态作为弱证据。D5 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。如果 D5 与中心预测长期冲突，D2 只应降低身份置信或提高风险摘要，不能直接用终端真值重命名全局航迹。

### 7.4 D6

D6 消费 D2 association logs、state transitions、summary 和 confusion matrix 做系统级评估。D2 和 D6 必须显式保留 `id_switch_count` 规则：D2 内部 IDSW 与 D6 episode IDSW 口径需要一致，不能只用 RMSE 或覆盖率替代身份连续性。当前已有 D2/D6 合同测试验证同一 truth 的代表 `global_track_id` 变化会被两侧计为 ID Switch。

main runtime 的 P1 D4/D5 calibration sweep 已接入 D6 标准报告 bundle，因此 D2 后续输出应优先对齐该报告入口：每个真实 5v5 replay 需要携带 `seed`、`episode_id`、`scenario_name`、`frame_index`、`drone_count`/`target_count`、gate threshold、`risk_profile`、`risk_profile_version`、association logs、D2 summary 和 offline truth labels。D2 不生成 D6 bundle，也不连接 AirSim SDK；D2 只保证其 report/log 字段可被 D6 分组统计。

## 8. 剩余风险

### 8.1 多目标交叉

GNN 是硬关联，交叉帧的最优/次优代价 margin 可能很小。一旦硬判决选错，后续 Kalman update 会把错误观测吸收到航迹状态中，导致 ID Switch。JPDA/MHT 能提供对照，但当前 JPDA 没有完整概率状态混合，MHT 没有完整多帧确认策略，因此不能宣称已彻底解决交叉身份交换。

### 8.2 密集编队

密集编队中多条航迹共享门内候选，协方差椭圆重叠，`candidate_counts_by_track` 和 `candidate_counts_by_detection` 会升高。当前特征代价只是简单向量差异，若来源特征不稳定或不具备区分力，GNN 仍可能在平行近距目标间交换 ID。

### 8.3 ID Switch 评估风险

`id_switch_count` 依赖离线 `truth_id`。真实/在线路径没有 truth label 时，只能通过 D2 风险摘要、D5 disagreement、confusion-like replay label 和 D6 离线评估分析身份风险。文档和报告不得把线上无 truth 的风险摘要等同于真实 IDSW ground truth。

### 8.4 N 规模性能风险

虽然 D2 不写死 2v2/5v5，算法复杂度仍随输入规模增长。GNN 的 Hungarian 求解约为 `O(max(N,M)^3)`；JPDA 联合假设枚举会组合爆炸；MHT 分支扩展随时间和候选数增长。更大 N 需要调用方设置预算、截断、分簇或只在离线对照中启用高阶算法。

## 9. 下一步

当前顺序为：维护已闭合的 P1 replay/truth/D1-governed 合同和 synthetic 10-seed runner；如有需要，再由 main/runtime/D6 沿冻结合同扩展真实 dense/crossing 性能标定。P2 保持隔离 benchmark，不得反向改写默认 GNN/Hungarian 路径、默认依赖或跨模块总线合同。

### P1 闭合维护与后续标定

1. **维护冻结合同**：main/runtime 输出不含 truth 的 governed detection/timestamp/covariance，并单独输出 `d2-offline-truth-label/v1`；D2 持续回归匿名化、availability 和 evaluator-only 评分。
2. **可选真实 dense/crossing 标定**：若扩展专项数据集，每个 episode 应固化 gate threshold、`risk_profile_version`、`association_risk_threshold_version` 和 IDSW 判定版本；D6 汇总 IDSW、continuity、duplicate 及软/硬风险误报漏报。这是 P1 闭合后性能研究。
3. **标定 N/M 初始化**：对 confirmation hits、miss tolerance 和 birth/deletion 参数做网格实验，输出初始化延迟、false track rate、漏建轨率和重复航迹率，并按目标密度与漏检率分层。
4. **补齐 NIS/NEES 统计一致性**：NIS 使用量测创新与创新协方差，NEES 仅在离线 truth state 可用时计算；输出置信区间内比例和按传感器/距离/场景分组的偏离原因，不把 covariance 输入合法性等同于统计一致性。
5. **开展 adaptive gate / JPDA 受控对照**：在同一 replay、seed 和计算预算下比较固定/quality-aware/完整 adaptive gate，以及 GNN/Hungarian/当前 JPDA 对照；验收同时报告 IDSW、continuity、false track、漏关联、延迟和假设截断，GNN 仍为默认主线。

P1 闭合证据区分两层：在线层只使用 innovation、候选重叠、cost margin、duplicate 和质量风险等可观测量；离线层使用隔离 truth labels 计算 IDSW、identity/coverage continuity、NEES 和 hard-risk 漏报率。2026-07-11 CV 10-seed 的 IDSW=0 是离线评分结论，不应与无 truth 的在线 `d2_hard_risk_frame_rate=0.0` 混淆；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW 评分。

### P2

- 决定 D2 是否升级原生 3D NED tracker；若升级，先定义 `[px, py, pz, vx, vy, vz]`、6x6 covariance、三维门控和 D1/D5 投影合同。
- **已完成 benchmark 合同**：v2 固定 frozen replay digest，默认 GNN baseline 与可选 JPDA/MHT research adapter 走同一 Tracker/offline evaluator；Stone Soup/FilterPy object adapter 按依赖可用性执行。五类结果统一输出 IDSW、continuity、latency 和 `unavailable_reason`，并回归在线输入无 truth。
- **未完成的 P2 增强**：Stone Soup 完整 JPDA/MHT、FilterPy EKF/UKF/IMM、optional 端到端 tracker 及其 IDSW/continuity 对照；模块内轻量 JPDA/MHT 仍只是研究近似，不能当作这些完整算法已实现。
- 设计 JPDA/MHT 自动升级策略，但必须包含切换迟滞、D4/D6 阈值认可和回放证据，避免算法抖动。
- P2 只在隔离 research environment 和冻结 replay 上执行；当前 Stone Soup/FilterPy 只是 adapter smoke，模块内 JPDA/MHT 只是研究近似。optional import/API/metric 失败时必须填写 `unavailable_reason`，不能静默回退或写成完整 tracker benchmark。

### P3

- 在多 seed replay 证明收益后，再考虑生产级 MHT 分簇、N-scan pruning 或外部框架适配。
- 若 D5 多视角反馈稳定可用，再把末端关联作为低权重身份证据接入 D2 风险模型；仍不得让 D5 改写 `global_track_id`。

## 10. 验收命令

从仓库根目录运行：

```bash
git diff --check -- research_modules/d2_data_association subagent_reviews/D2_*
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

## 11. M 对 N 协同拦截下的跨平台航迹融合研究计划

专项调研见 `subagent_reviews/D2_M_TO_N_TRACK_FUSION_REVIEW.md`。结论是：多个拦截节点观测同一高威胁目标时，多个 local tracks 只能登记为同一 canonical `global_track_id` 的多源证据，不能解释为多个目标，也不能让 `k_j=3` 的资源需求复制三条全局航迹。

该能力不改变当前 detection-to-track GNN/Hungarian P0 主线。已闭合的中心注册基础如下：

1. **已实现**：带 source/local/epoch namespace、两个 timestamp、6D NED state/covariance、quality、lineage、correlation status 和 canonical hints 的 `SourceTrackSummary`；source hint 不具备身份权威。
2. **已实现**：公共融合时刻传播、covariance-aware track-to-track Mahalanobis gate、按 source 节点分组的 Hungarian，以及 `global_track_id -> source tracklets` binding/history；测试覆盖 1/2/3/N source、异步、交叉、重复、local ID 冲突和 canonical continuity。
3. **已实现决策边界**：known cross-covariance 输出 exact correlated fusion request，unknown correlation 只输出 CI request，duplicate payload/lineage 直接拒绝。数值 CI/相关融合继续由 D1 owner 实现。
4. **已实现指标基础**：online cross-node rebind IDSW、duplicate payload rejection、fusion latency，以及隔离 offline truth 下的 canonical duplicate 和 association precision/recall。
5. **后续研究**：高歧义跨节点 JPDA/MHT、多 seed 同时/序贯/混合 replay、D2 owner/epoch failover、通信字节和 D1/D6 数值融合一致性 NEES/ANEES。D4 二级/分布式 commit 正例通过不等于 D2 owner failover 已实现。
6. **保持隔离**：Stone Soup 只作为 track-to-track association/CI benchmark，不把第三方对象写入跨模块总线。

当前已落地 `canonical_duplicate_count`、`cross_node_id_switch_count`、track-to-track association precision/recall、重复消息拒绝数和融合延迟。fusion NEES/ANEES 与通信字节仍待 D1/D6/replay 集成；所有 cross-node 指标都不能与合法的多资源协同或 D3 `duplicate_assignment_count` 混为一谈。

## 12. 2026-07-12 P1 长 Replay 实施状态

本轮已增加 `d2-governed-long-replay/v1` 校准路径，默认生成至少 40 帧、
推荐 120 帧的动态 N 目标 governed replay。场景包含重复密集交叉、交叉窗口
遮挡、周期漏检、近场虚警和人为延迟到达；runner 要求至少 10 个唯一 seed。

实施原则如下：

1. 默认关联器保持 GNN/Hungarian，JPDA/MHT 继续只在 optional benchmark 中运行。
2. D1/main 负责原始 OOSM 治理；D2 按 measurement time 有序输入关联，只审计
   arrival inversion、late measurement 数量和时延分布，避免把 `dt=0` fallback
   误写成 OOSM 回溯实现。
3. 在线帧递归剥离 truth，离线 `d2-offline-truth-label/v1` 只在关联完成后评分。
4. 每 seed 固化 scenario/gate/risk/profile version，并输出 IDSW、identity/coverage
   continuity、false-track、RMSE、NIS/NEES availability、runtime 和 truth leakage。
5. `global_track_id_owner=d2_center` 是报告合同；source detection/local identity
   不能成为规范 ID，N/M 变化也不能触发固定长度补齐或截断。

该 synthetic long replay 入口关闭的是 D2-owned 可重复校准工具缺口，不等于真实
AirSim 长 replay 已完成参数冻结。真实 replay 仍需 main 提供 governed frames 和
隔离 truth，D6 按相同 schema 做长期趋势和阈值验收。
