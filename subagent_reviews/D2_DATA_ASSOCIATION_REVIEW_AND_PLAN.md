# D2 多目标跟踪与数据关联综述及子方案

**定位**：维护稳定的 `global_track_id`，在目标交叉、密集编队、漏检、遮挡和虚警条件下抑制 ID Switch。
**边界**：本文只讨论科研仿真、离线回放、多目标跟踪、数据关联、状态机和指标记录，不包含真实飞控、火控、毁伤、自动处置或绕过人工授权的流程。
**当前代码口径**：已落地 GNN/Hungarian、二维常速度 Kalman fallback、Track 状态机、P1 D1-governed input/offline truth/10/20-seed runner，以及隔离 P2 frozen replay comparison。2026-07-15 已用六档冻结真实 AirSim replay/truth 完成 ceiling-aware v2 的 6x10 screening 和 6x20 confirmation；总体最佳 GNN 候选五项联合 gate 通过并形成 promotion review recommendation，但默认路径未改变。2026-07-14 Post-batch M5N2 同 seed 的 `T008` 不复发状态不变。P2 v2 同场输出默认 GNN、模块内 JPDA/MHT research adapter 与 Stone Soup/FilterPy object adapter；后两者仍不是端到端 tracker，模块内 JPDA/MHT 也不是完整算法。

---

## 0. P0/P1 缺口快照

- **P0**：无开放 blocker。GNN/Hungarian、显式 `id_switch_count`、`track_continuity`、risk summary、replay helper、按输入集合长度运行、航迹质量评分、运动一致性约束和 quality-aware gate baseline 已是当前主线。seed1005 v3 验收已允许 replay=0 或有界 replay，见第 32 节。
- **P1 合同层已闭合**：D1 governed adapter、online/offline truth 分离、association log/profile version、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed runner、availability-aware summary、M-of-N/false-track/NIS/NEES 接口及中心 canonical registry 基础已回归。
- **P1 完整冻结 v2 证据已生成，长期标定仍开放**：最佳 GNN 候选 IDSW `1.358333 -> 0.616667`（下降 `54.6012%`），continuity `0.981046 -> 0.983954`，P95 `15.470 ms`；false-track/truth leakage 均为 0。总体联合 gate 全部通过，`promotion_recommended=true`；分档仅 clutter/combined 通过，另外四档 baseline IDSW=0 fail-closed。后续 P1 是跨模块评审、更长 OOSM/遮挡/杂波和生命周期标定，不再是缺少 v2 联合报告。
- **历史基线**：2026-07-10 的 5v5/2v2 批次和 2026-07-11 早期的 seeds 7/17/27 当时不足以关闭 D2 P1，且 T001 双 primary 尚未通过。这些只作为实施前/过渡基线，不代表当前状态。
- **当前 ComputerVision 证据**：M=5、N=2 的 10 seeds 中，T001 双 primary 共识/计划授权为 8/10；D2 `id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。
- **commit 与物理边界**：二级/完全分布式 commit 正例通过，缺 ACK 时 fail-closed；这是下游沿用 D2 中心 `global_track_id` 的合同证据，不是 D2 owner failover/临时 ID 合并实现。SimpleFlight 15 s 只是诊断，30 个 active pair 无命中，物理拦截未闭合。
- **回归与 P2 边界**：2026-07-15 最新 D2 完整回归为 `113 passed, 1 warning`；warning 不影响关联、指标或标定结论。D1 governed loader 属于 P1 输入合同；P2 只做隔离 benchmark。轻量 JPDA 在 strict 同输入对照中退化，GNN/JPDA/MHT research adapter 和 Stone Soup 1.9.1/FilterPy 1.4.5 object adapter 均不得进入默认主线。默认依赖与在线 GNN/Hungarian 未改变。
- **2026-07-15 M5N2 20-case 证据**：baseline/candidate 各 10 seed，共 20/20 case；
  D2 association main-bus 3805/3805 可用，mean/P95/max 为
  `2.521/3.147/98.942 ms`。在线 truth identity/state use 为 0，故本批在线
  IDSW/continuity 是 unavailable，不是 0。第二 primary `0/20` 进入 5 m 且最终均为
  `collision_stop`，但碰撞对象未持久化，不归因于 D2。默认 GNN/Hungarian 和中心
  `global_track_id` 所有权不变；终止前额外完成的一个 `png_ttc_2v2_seed001` 被排除，
  dropout case 为 0。
- **2026-07-22 当前集成证据**：main 在 clean reference `8f86192` 和 candidate
  `f80b5bd` 上完成 nominal 200v200、10.0 s、seeds 42000/42001/42002 对照。每 seed
  D2 association 调用 47 次，累计耗时均值 `8.317513 -> 7.671266 s`，终态航迹数
  `205/204/203` 逐 seed 相同；在线逐条语义和 topic counts 全部通过，truth use 为 0。
  短长对照仍把 D2 列为超线性，不宣称实时 promotion。当前完整 D2 回归为
  `219 passed, 1 warning in 49.75s`。

## 1. 研究问题

多目标场景中，系统风险不只来自位置误差，还来自“目标还在，但身份换了”。如果同一物理目标在交叉或遮挡恢复后被另一个 `global_track_id` 接续，后续 D3 分配、D4 降级仲裁、D5 终端视觉配准和 D6 episode 指标都会失真。

D2 子系统目标：

- 使用 GNN/Hungarian 作为默认工程基线。
- 通过 `DataAssociator` 接口保持 GNN、JPDA、MHT 可替换。
- 用 `Tracker` 管理 `tentative/confirmed/engageable/lost/dropped` 状态机。
- 强制记录 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity` 和 `duplicate_assignment_count`。
- 输出 association logs 和 `AssociationRiskSummary`，供 D3/D4/D5/D6 消费。
- 关联器和 Tracker 按每帧输入的 `tracks`/`detections` 集合长度运行；2v2、5v5 只作为 fixture 或验收场景，不写入算法假设。

D2/D6 的系统规则必须保留：`id_switch_count` 是强制显式指标，不能被 RMSE、覆盖率或命中数替代。当前测试已验证 D2 `MetricsRecorder.id_switch_count` 与 D6 episode IDSW 口径一致。

---

## 2. 当前实现状态

### 2.1 已实现

- **GNN/Hungarian**：`GNNHungarianAssociator` 通过 `scipy.optimize.linear_sum_assignment` 求解一对一匹配，代价来自马氏距离、可选 feature cost 和 motion consistency cost。
- **马氏门控**：`build_gated_cost_matrix()` 生成 `N x M` cost/distance matrix，记录 `candidate_counts_by_track`、`candidate_counts_by_detection`、per-track quality-aware gate threshold 和 `RejectedPair`。
- **可插拔关联器**：`DataAssociator.associate()` 是统一接口，`Tracker` 只消费 `AssociationResult`。
- **二维 Kalman fallback**：`Tracker` 使用 `[x,y,vx,vy]` 和 4x4 covariance 做常速度预测、Joseph update、建轨和漏检处理。
- **Track 状态机**：代码中只有 `tentative -> confirmed -> engageable -> lost -> dropped`，并支持 lost 后重新命中回到 `confirmed` 或 `engageable`。
- **核心指标**：`MetricsRecorder.summary()` 输出 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`truth_metrics_available`、`continuity_available`、`duplicate_assignment_count`、RMSE、confusion matrix、runtime；无 truth 时 continuity 兼容值不参与 hard risk，旧 replay 缺 availability 字段时保守按不可用处理。
- **风险摘要**：`AssociationRiskSummaryWindowGenerator` 已从候选重叠、cost margin、IDSW delta、duplicate delta、continuity risk、D5 disagreement 和 metadata 生成滑窗风险。
- **软/硬风险分层**：`RiskThresholds` 与 `classify_risk_summary()` 已按 D4 口径把 ambiguity/cost margin/candidate overlap/D5 disagreement 归为软风险，把 IDSW、duplicate 和 continuity collapse 归为硬风险。
- **N 规模输入**：关联器按 `len(active_tracks)` 和 `len(detections)` 构造矩阵；dry-run 测试包含 3 目标 episode，输出 3 个活动 `global_track_id`。
- **D1 adapter**：`detections_from_d1_global_tracks()` 把 D1 6D NED `GlobalTrack` 投影为 D2 2D `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、covariance 投影和 metadata。
- **AirSim dry-run adapter**：支持 synthetic AirSim-style dict/object，不 import `airsim`，可从 `detections/tracks/objects`、`x/y`、`x_val/y_val` 和 2x2/3x3 covariance 生成 D2 输入。
- **AirSim-style replay/calibration helper**：`load_airsim_replay_frames()`、`run_airsim_replay_association()`、`write_replay_association_report()`、`write_association_logs_jsonl()`、`run_threshold_sensitivity()` 和 `summarize_multi_seed_risk_calibration()` 已覆盖离线 5 目标 JSONL replay、association logs、metrics、seed/episode/scenario/frame/offline truth label metadata、阈值 profile version、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、N-v-N `target_count` fallback、风险阈值敏感性输出和多 seed 推荐阈值摘要。
- **冻结 truth 与批量校准**：`OfflineTruthLabel`/JSONL reader-writer 固化 episode/frame/timestamp/truth ID/position；`strip_offline_truth_from_frames()` 保证在线输入无 truth，离线匹配注释仅供 evaluator 恢复评分。`build_dense_crossing_replay_fixture(target_count=N)` 和 `run_dense_crossing_calibration()` 已覆盖连续漏检/遮挡、虚警、动态 N、至少 10 seed、同 seed 确定性签名和 availability-aware 聚合。
- **拒配原因闭环**：`AssociationLogEntry.rejected_pairs` 默认空列表并完整序列化 `mahalanobis_gate`/`assignment_above_gate`，replay gate summary 分原因统计，旧 JSON 缺字段按空处理。
- **covariance 输入治理**：Detection/GlobalTrack 和门控边界拒绝非有限、明显非对称、明显非 PSD covariance，仅对容差内缺陷正则化；`covariance_consistency` 始终表示最新检查，`regularization_ever_applied`/`last_regularization` 保留历史修复证据。
- **replay governance**：默认在线检测、航迹和 association log 不含 simulator truth，源 detection/actor ID 按帧匿名化；online innovation 独立输出 NIS，offline evaluator 输出 IDSW/continuity、2-of-3 初始化、false-track 和 NEES。缺 truth 时 NEES 与 truth 指标保持 unavailable，但 NIS 仍可用。
- **truth-isolated main runtime 合同**：真实短 episode 已验证在线 `truth_id=None` 时 D2 航迹仍可进入 D3，且 `d2_governance_summary` 可被 D6 消费。在线风险摘要不需要 truth；truth-based `id_switch_count`、identity/coverage continuity 和 NEES 仍只能在离线评估层产生。

### 2.2 部分实现

- **JPDA**：`JPDAAssociator` 已能枚举小规模联合假设、计算边缘概率并输出接口兼容 `AssociationResult`。它是可执行研究对照，不是完整 JPDA filter；当前没有概率混合状态更新、完整协方差融合、track coalescence 抑制或大规模分簇策略。
- **MHT**：`MHTAssociator` 已维护有界 branch、短历史、漏检/虚警惩罚和 pruning 参数。它是 MHT-compatible research placeholder，不是完整 MHT；当前没有 N-scan pruning、长期假设树管理、分簇或中心算力策略。
- **3D NED 双路径**：旧 D1 adapter/`Tracker` 继续投影到二维；2026-07-20 新增独立 `Detection3D`/`GlobalTrack3D`/`Scalable3DTracker`，固定六维 NED、3D 马氏门控和稀疏 GNN/Hungarian。main scalable bus 已接入并完成三 seed nominal clean 非退化复核；困难场景、实时预算和离线身份标定仍开放。
- **D6 集成**：D2 summary/logs 已含 IDSW、continuity、duplicate、risk/profile version、gate pass/reject、motion/quality 和 dense/crossing sensitivity 字段，并有 D2/D6 `id_switch_count` 合同测试。当前 P1 CV 批次已由 main/runtime/D6 生产与评分；后续专用 dense/crossing 分组标定属性能研究，不是 P1 合同缺口。

### 2.3 未实现

- **IMM/EKF/UKF**：代码中没有 FilterPy `IMMEstimator`、EKF、UKF、sigma points、CV/CA/CT 模型集或模型转移概率。当前是二维线性 Kalman fallback。
- **Stone Soup 完整追踪**：已创建 Detection/StateVector adapter，但未创建 Track、predictor/updater、JPDA/MHT tracker；不能报告外部框架 IDSW/continuity。
- **FilterPy 高阶/端到端追踪**：已创建 CV KalmanFilter object adapter，但没有跨帧关联 tracker、EKF、UKF 或 IMMEstimator。
- **自动算法升级**：当前由 CLI 或调用方显式选择 GNN/JPDA/MHT，`Tracker` 未按风险阈值自动切换。
- **真实 AirSim runtime 采集链路**：D2 已能消费离线 JSON/JSONL AirSim-like replay，但不连接 AirSim runtime，不采集真实 `simGetDetections`/ComputerVision 图像 metadata，也不负责 main/D6 episode JSONL 生产。
- **OOSM 与六维高阶跟踪**：六维线性 CV 已实现；异步量测回溯平滑、六维 JPDA/MHT、EKF/UKF/IMM 和极端高密度预算未实现。

---

## 3. 方法综述

2015-2026 年多目标跟踪主线仍是“运动预测 + 门控 + 数据关联 + 航迹管理”。D2 当前落地的是这条主线的轻量可测版本。

**GNN/Hungarian** 是硬关联方法。它把每个观测分配给最多一个航迹，优点是计算轻、延迟低、解释性强，适合默认运行和低歧义回放。缺点是在目标距离很近、交叉或并行运动时，一次错误匹配会造成 ID Switch。

**JPDA** 是软关联方法。它对多个候选观测计算联合概率，再对每条航迹做边缘概率。D2 当前实现能做小规模联合假设对照，但没有完整概率状态融合。它适合分析交叉和遮挡恢复中的不确定性，不宜被文档写成生产级 JPDA。

**MHT** 是延迟决策方法。它保留多帧假设树，通过剪枝选择全局更合理的解释。D2 当前有 bounded branch 对照实现，但不包含完整 MHT 所需的 N-scan、分簇和长期树管理。MHT 更适合中心节点或离线评估，不建议部署到资源受限节点。

**IMM/EKF/UKF** 不是数据关联算法，而是运动预测增强。它们可能降低机动目标预测误差，从而减少门控重叠和 ID Switch，但当前 D2 代码未实现。后续只有在强机动场景证明常速度模型是主要瓶颈时，才应引入。

---

## 4. 开源工具选型与实际使用

| 工具 | 预期可复用内容 | 当前 D2 状态 | 原因和条件 |
|---|---|---|---|
| SciPy | `linear_sum_assignment` | 已实际使用 | 默认 GNN/Hungarian 求解器，轻依赖、可测试 |
| NumPy | 状态、协方差、矩阵运算 | 已实际使用 | 默认运行路径基础依赖 |
| Stone Soup | 完整 GNN/JPDA/MHT、轨迹管理示例 | Detection adapter + frozen replay conversion smoke 已实现并用 1.9.1 验证；完整 tracker 未实现 | 需要 predictor/updater、Track lifecycle、JPDA/MHT 状态更新和同预算指标；外部对象不得进入总线 |
| FilterPy | Kalman、EKF、UKF、IMMEstimator | CV KalmanFilter 初始化/predict/update adapter 已实现并用 1.4.5 验证；非端到端 tracker | 需要关联生命周期、EKF/UKF/IMM 模型和真实强机动 replay 才能产生 IDSW/continuity |
| py-motmetrics/CLEAR MOT | 离线 MOTA/IDF1 等指标参考 | 未使用 | 当前 D2/D6 先固化 `id_switch_count`、continuity、duplicate 和 confusion matrix |

实际工程原则：

- 默认测试不能依赖 Stone Soup、FilterPy、AirSim SDK、ROS 或 GPU。
- 外部库只能作为 optional benchmark 或 adapter，不进入 D2 默认 bus contract。
- 所有关联器必须输出统一 `AssociationResult`，以便 D3/D4/D5/D6 不感知底层算法对象。

---

## 5. 子系统架构

```text
abstract DataAssociator
  + associate(tracks, detections, timestamp) -> AssociationResult

GNNHungarianAssociator --|> DataAssociator
JPDAAssociator         --|> DataAssociator
MHTAssociator          --|> DataAssociator

Tracker
  + predict_all(timestamp)
  + associator.associate(...)
  + Kalman update matched tracks
  + mark missed tracks
  + create tentative tracks
  + record metrics

TrackLifecycleState
  tentative -> confirmed -> engageable -> lost -> dropped

MetricsRecorder
  id_switch_count
  track_continuity / identity_continuity / coverage_continuity
  duplicate_assignment_count
  association_logs
  risk summaries
```

`AssociationResult` 当前关键字段：

```text
timestamp
matched_pairs: [(track_id, detection_id, cost, probability)]
unmatched_track_ids
unmatched_detection_ids
ambiguity_score
associator_type
rejected_pairs
cost_matrix
distance_matrix
metadata
source_node_id / link_type
risk_summary
```

---

## 6. 核心伪代码

```python
class DataAssociator:
    def associate(self, tracks, detections, timestamp):
        raise NotImplementedError

class GNNHungarianAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        cost = build_gated_cost_matrix(tracks, detections)
        rows, cols = linear_sum_assignment(cost.cost_matrix)
        return AssociationResult(...)

class JPDAAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        hypotheses = enumerate_valid_joint_hypotheses(tracks, detections)
        marginals = marginalize_probabilities(hypotheses)
        return select_non_conflicting_marginal_matches(marginals)

class MHTAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        branches = expand_bounded_branches(tracks, detections)
        return best_branch_current_frame(branches)
```

指标记录：

```python
def update_identity(truth_id, track_id):
    old = last_truth_to_track.get(truth_id)
    if old is not None and old != track_id:
        id_switch_count += 1
    last_truth_to_track[truth_id] = track_id
```

注意：`truth_id` 只用于离线评估；在线 ComputerVision 路径不得用 AirSim truth ID 做 D5/D2 实时身份绑定。

---

## 7. D2 输出给 D3/D4/D5/D6 的合同

### 7.1 D3 分配规划

D3 使用 D2 的 `global_track_id`、状态、协方差、生命周期和风险字段构造分配代价。推荐 D3 优先消费 `confirmed` 和 `engageable` 航迹；对 `tentative`、长期 `lost`、高 `association_ambiguity` 或高 `duplicate_track_risk` 的航迹提高代价或延迟重分配。

D2 不生成 `AssignmentPlan`，不维护 plan version，也不接受 D3 将 `global_track_id` 重命名。每个 assignment plan 的版本化和 stale rejection 仍由 D3 负责。

### 7.2 D4 主动降级

D2 只向 D4 提供关联风险证据，不决定降级模式。可用证据包括：

- `id_switch_count` 和滑窗 delta。
- `track_continuity` / `identity_continuity` 下降。
- `duplicate_assignment_count` 和 `duplicate_track_risk`。
- `association_ambiguity`、cost margin risk、candidate overlap。
- `covariance_overlap_rate`。
- `d5_disagreement_count`。
- `source_node_id` 和 `link_type`。

D4 应综合 D1 定位质量、D3 分配抖动、D5 终端反馈和 D2 风险摘要，再决定 `continue_center`、`request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。D2 不直接切换二级节点或分布式模式。

2026-07-07 的 D4 P1 修复后，D2 对 D4 的风险证据需要按软/硬两层解释：

- **软风险**：`association_ambiguity`、cost margin risk、candidate overlap、短时 D5 disagreement。它们说明当前 GNN 硬关联不确定，D4 可以继续观察、请求二级节点 cue、提高 D3 重分配迟滞或要求 JPDA/MHT 离线对照，但不应由单帧软风险直接触发 `request_center_replan`。
- **硬风险**：`id_switch_count` 或滑窗 delta 增长、`duplicate_assignment_count`/`duplicate_track_risk` 增长、可用的 `track_continuity` 低于阈值。`continuity_available=false` 时兼容数值 `0.0` 不得触发 continuity collapse 或 hard risk。
- **D2 边界**：D2 只保证上述字段被明确记录和可回放；D4 负责结合 D1/D3/D5 和二级节点/通信状态决定 `request_center_replan`、`request_secondary_assist`、`degrade_to_secondary` 或 `degrade_to_distributed`。

### 7.3 D5 末端关联

D5 使用 `global_track_id` 做中心航迹到终端相机候选的映射。D5 可以回传：

- `TerminalAssociation.association_confidence`。
- `candidate_global_track_ids`。
- `decision_state`。
- 末端不一致事件。
- `IdentityClaim` 的 verified/stale/unverified/spoof_suspected 状态。

D5 反馈只能作为弱证据进入 D2 风险摘要或身份置信调整，不允许直接改写、重绑或本地覆盖 D2 的规范 `global_track_id`。

### 7.4 D6 指标评估

D6 消费 D2 `AssociationLogEntry`、`TrackTransition`、summary 和 confusion matrix。D2 与 D6 必须显式保留 `id_switch_count`：同一 truth 的代表 `global_track_id` 变化就是 ID Switch。当前测试已验证 D2/D6 对该规则的一致计数。

2026-07-08 起，main runtime 的 P1 D4/D5 calibration sweep 会自动生成 D6 标准 AirSim calibration report bundle。D2 对该 bundle 的职责是提供可分组、可回放的 association logs 与 summary 字段，包括 `seed`、`episode_id`、`scenario_name`、`frame_index`、gate threshold、`risk_profile`、`risk_profile_version`、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、`id_switch_count`、continuity、duplicate 和 soft/hard risk summary。`drone_count`/`target_count` 可保留在离线 report/episode metadata；在线 association log 只保留 measurement/active-track count，不写 truth target count。D2 不直接生成 bundle，也不使用在线 truth ID 绑定 `global_track_id`。

---

## 8. 主动降级风险摘要

当前 D2 已实现轻量 `AssociationRiskSummary` 和 D4 对齐的 `RiskThresholds`/`classify_risk_summary()`，字段和分层包括：

- `timestamp`
- `source_node_id`
- `link_type`
- `d5_disagreement_count`
- `duplicate_track_risk`
- `association_ambiguity`
- `covariance_overlap_rate`
- `metadata`

窗口生成器当前使用：

- `AssociationResult.ambiguity_score`。
- `AssociationResult.cost_matrix` 的最小/次小 cost margin。
- `candidate_counts_by_track` 和 `candidate_counts_by_detection`。
- `id_switch_delta`。
- `track_continuity`。
- metadata 中的 D5 disagreement、source node、link type。

`run_threshold_sensitivity()` 会按 gate threshold 与 risk threshold profile 输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`/`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、seed/episode/scenario/frame metadata 和软/硬风险摘要，用于离线标定 D4 仲裁阈值。`summarize_multi_seed_risk_calibration()` 会按 gate/risk profile/version 汇总多 seed 的 IDSW、continuity、duplicate、soft/hard risk count/rate/score 分布、dense/crossing sensitivity summary 和推荐阈值摘要。

后续可在不改变 D2 身份权威边界的情况下增加：

- `affected_global_track_ids`。
- `risk_level`。
- `jpda_recommended` / `mht_recommended`。
- `recommend_active_reevaluation`。
- `state_regression_count`。

这些字段应由当前活动航迹集合和 association logs 派生，不应按固定 2 或 5 个目标生成。

---

## 9. 剩余风险

### 9.1 多目标交叉

GNN 在交叉窗口内只能做单帧硬判决。如果两条航迹的最优和次优候选代价差距很小，GNN 可能任意打破平局，造成后续 ID Switch。JPDA/MHT/BP 对照能暴露歧义和 track coalescence 风险，但当前实现还不足以承诺消除该风险。

### 9.2 密集编队

密集编队会提升协方差重叠和共享候选比例。当前 feature cost 是简单向量距离，若特征来源不稳定，仍可能出现目标间身份交换或重复航迹解释。

### 9.3 ID Switch 观测限制

`id_switch_count` 依赖离线 `truth_id`。真实在线路径没有 truth label 时，D2 只能输出风险摘要和弱证据，不能宣称在线已知道真实 IDSW。D6 应在离线 replay 或带 truth label 的仿真中计算最终 IDSW。

### 9.4 规模和复杂度

D2 不写死 2v2/5v5，但复杂度仍随 N 增长。GNN/Hungarian 约为 `O(max(N,M)^3)`；JPDA 假设枚举会组合爆炸；MHT 分支扩展随时间和候选数增长。更大规模需要分簇、预算、截断和离线 benchmark 支撑。

---

## 10. 测试方案

| 测试 | 当前覆盖 | 指标 |
|---|---|---|
| 马氏门控 | 已覆盖 near/far gate | rejected reason、candidate count |
| GNN/Hungarian | 已覆盖一对一匹配 | 无重复 detection/track |
| JPDA | 已覆盖 marginal output | hypothesis count、marginal shape |
| MHT | 已覆盖接口兼容 | branch count、history bound |
| Track 状态机 | 已覆盖 engageable/lost/dropped | lifecycle transition |
| D2 metrics | 已覆盖 IDSW/continuity/duplicate/confusion | summary 字段 |
| D2/D6 IDSW 口径 | 已覆盖 | `id_switch_count` 一致 |
| AirSim dry-run | 已覆盖 synthetic frames | bus message、association logs |
| N 规模输入 | 已覆盖 3 target episode | `global_track_ids` 长度来自输入 |
| dense 5v5 fixture | 已覆盖 deterministic compare | GNN/JPDA/MHT IDSW、continuity、runtime |
| AirSim-like 5 目标 JSONL replay | 已覆盖 reader/report/log 输出 | `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、seed/episode/scenario metadata、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、soft/hard risk summary |
| threshold sensitivity 与 multi-seed summary | 已覆盖变量目标数、多 profile sweep、阈值版本和多 seed 汇总 | gate threshold、risk profile/version、`association_risk_threshold_version`、gate/motion/quality diagnostics、dense/crossing summary、IDSW、continuity、duplicate、soft/hard risk 分布、推荐阈值摘要 |
| main/D6-style row metadata 与 offline truth label | 已覆盖 JSONL wrapper/payload 读取、在线匿名 detection ID 和 offline truth label 评估 | actor/truth identity 不进入在线日志，`global_track_id` 仍由 D2 Tracker 生成 |
| N-v-N replay 无 truth label target count | 已覆盖 report 输入观测数 fallback | 离线 report 可记录估计 `target_count`；在线日志只记录 measurement/active-track count，IDSW/continuity 真值评估仍需离线 labels |
| 无 truth continuity 风险 | 已覆盖多帧 replay | availability=false、无虚假 duplicate/continuity hard risk |
| 拒配日志与回放 | 已覆盖门外 pair 和旧日志 | 两类 reject reason、JSONL 序列化、gate summary 一致 |
| covariance 输入治理 | 已覆盖 NaN/非对称/负特征值、容差内修复和正常输入 | 显式拒绝、regularization diagnostics、正常 GNN 不退化 |
| offline truth JSONL | 已覆盖 round-trip、schema/字段和在线递归隔离 | episode/frame/timestamp/truth ID/position、在线 Detection/Track/log 无 truth |
| N-target dense/crossing | 已覆盖 7-target 动态规模、漏检和虚警 | 数量来自输入 N，feature 维度和 truth 基数同步 |
| 至少 10-seed calibration | 已覆盖 10 seeds 连续运行两次 | 确定性签名、每 seed/聚合 IDSW、continuity、NIS/NEES availability、profile/version、runtime |
| long governed replay | 已覆盖 3-target/4-target、40-frame 最小长回放和至少 10 seeds | dense crossing、遮挡、漏检/虚警、arrival inversion、false-track、RMSE、NIS/NEES availability、truth leakage=0、动态 N/M |
| unavailable 聚合 | 已覆盖缺 truth/NEES seed | `available=false`、均值为 `None`，不转换为零 |
| P2 dependency unavailable | 已覆盖默认环境缺 FilterPy/Stone Soup | `dependency_available=false`、明确 reason、`executed=false` |
| P2 adapter available smoke | 已覆盖模拟 available，并在隔离 venv 实测 | conversion/update latency；IDSW/continuity 仍 unavailable；JPDA/MHT claims=false |
| frozen replay comparison | 已覆盖同输入两次执行 | input digest 和 baseline IDSW/continuity 一致 |
| D1 governed replay input | 已覆盖 manifest/records 最小 fixture 和真实 AirSim 文件 | radar spherical -> N/E、匿名在线 ID、声学/EO skip diagnostics、旧 frame schema 兼容 |

默认验收命令：

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

---

## 11. 后续研究与 P2 边界

当前顺序为：维护已闭合的 P1 D1-governed/replay/truth 合同和 10/20-seed runner，以 2026-07-13 strict 4 m/2 m 真实基线扩展更长 OOSM、遮挡、漏检、杂波和生命周期标定。P2 只保留隔离 adapter benchmark，不因本轮 JPDA 对照而升级主线。

### P1 闭合维护与后续性能研究

1. 持续回归 D1 governed adapter、无 truth 在线输入/log、`d2-offline-truth-label/v1`、`rejected_pairs`、track lifecycle 与 threshold profile/version。新增真实 OOSM/遮挡/杂波 replay 时沿用 strict 4 m/2 m 的同一合同。
2. 用多 seed 数据治理 gate/risk/IDSW 阈值，输出 IDSW、continuity、duplicate、软风险误触发率和硬风险漏报率，并保留非 2/5 数量合同验收。
3. 使用现有 M-of-N/false-track 接口做真实多 seed 网格标定，输出 init latency、漏建轨率和重复航迹率。
4. 将现有 NIS/NEES 卡方覆盖接入 D6，按传感器、距离和场景分组，严格区分 covariance 输入合法性与滤波统计一致性。
5. 在同 replay、seed 和计算预算下对比固定门限、quality-aware baseline、完整 adaptive gate 以及 GNN/JPDA；JPDA 只作为高歧义场景对照，不默认替代 GNN 主线。

### P2

- 将已实现的六维 NED 稀疏 tracker 接入 main-owned scalable bus，冻结 D1/D3/D5/D6 schema、模型版本和多 seed 性能预算。
- optional probe、Stone Soup Detection adapter、FilterPy CV filter adapter 和 comparison JSON 已完成。
- 完整 Stone Soup JPDA/MHT、FilterPy EKF/UKF/IMM 与 optional 端到端 IDSW/continuity 对照仍未实现。
- 设计 JPDA/MHT 自动升级阈值和迟滞，但必须先通过 D4/D6 回放证据证明收益。
- optional benchmark 必须在隔离 research environment 中运行；Stone Soup/FilterPy 当前只是 adapter smoke。缺依赖时显式输出 unavailable，不得静默回退后宣称第三方 tracker 结果有效。

---

## 12. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup JPDA tutorial: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html>
- Stone Soup MHT example: <https://stonesoup.readthedocs.io/en/latest/auto_examples/dataassociation/mht_example.html>
- FilterPy: <https://filterpy.readthedocs.io/>
- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- SORT paper: <https://arxiv.org/abs/1602.00763>
- Deep SORT paper: <https://arxiv.org/abs/1703.07402>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>

## 13. M 对 N 协同拦截中的 D2 扩展边界

专项文献和开源审计见 `D2_M_TO_N_TRACK_FUSION_REVIEW.md`。该调研确认：当三个拦截节点共同观测同一个高威胁目标时，D2 面对的是“一个全局目标、多个来源航迹”，不是三个目标。D3 的 `k_j=3` 是资源需求，不能反向复制 D2 `global_track_id`。

已闭合的中心注册基础按两个阶段处理：

```text
跨节点 local-track 对应
  -> 公共信息/未知互相关治理
  -> CI 或已知交叉协方差融合
  -> canonical global_track_id 多源 binding
```

成熟默认路线是公共时刻预测、track-to-track 马氏门控、低歧义 GNN/Hungarian、未知互相关 CI 请求和中心规范身份注册。JPDA/MHT 用于跨节点对应歧义，GCI/AA/labeled-RFS 用于离线研究对照；它们不能替代来源谱系和重复消息治理。

当前模块已实现 `SourceTrackSummary`、公共时刻传播、6D covariance-aware cost/gate、按 source Hungarian、lineage/payload/stale 防重、多源 canonical binding/history、exact/unknown/duplicate 决策，以及 online/offline 隔离指标。unknown correlation 只生成 CI request，D2 不计算数值 CI；尚缺 D1 融合 posterior 回写、高歧义多帧 JPDA/MHT、owner failover、fusion NEES/ANEES 和通信成本标定。现有 detection-to-track GNN/Hungarian P0 主线未改动。Stone Soup 仍只作为隔离 benchmark。

## 14. P1 长 Governed Replay 校准评审

新增长 replay 路径把原有 12-frame fixture 扩展为版本化、多 seed、动态 N/M 的
持续压力入口。轨迹采用周期机动以重复形成交叉窗口，遮挡和漏检造成 measurement
count 低于目标数，近场虚警造成 measurement count 高于目标数；因此可以同时检查
ID continuity、false-track birth/deletion 和门限风险，而不是只验证固定方阵。

时间治理采用两层语义：`measurement_timestamp` 决定 D2 Tracker 的处理顺序，
`arrival_timestamp` 用于统计传输延迟和 arrival-order inversion。选定帧增加延迟后
会晚于下一量测到达，但进入 D2 前仍由 governed replay 按量测时间排序。报告中的
`handling_policy=measurement_time_ordered_after_governance` 明确说明这一点；D2 不将
常速度 Tracker 的非负 `dt` 处理冒充 OOSM rewind/replay。

在线路径继续递归剥离 actor/truth 字段并匿名化 detection ID，规范 ID 只由中心
Tracker 生成。离线 evaluator 在运行结束后计算 IDSW、identity/coverage continuity、
false-track、RMSE 和 NEES；NIS 来自在线 innovation。缺 truth 时必须保持 unavailable，
不能写成零。默认 GNN/Hungarian 未变，完整 JPDA/MHT 仍只属于 P2 optional 对照。

该入口已用于 main/D6 导入真实 governed replay。2026-07-12 阶段只关闭了 D2-owned
runner/schema/test 缺口；2026-07-13 strict 4 m/2 m 各 20-seed 数据冻结和首轮参数
评审已经完成。更长 OOSM/遮挡/杂波、生命周期参数、跨节点 owner failover 和 D1
数值融合仍是开放项。

默认 5 目标、120 帧、10 seeds 的 CLI smoke 结果为：平均 IDSW `139.6`、identity
continuity `0.691`、coverage continuity `0.924`、false-track `5.3`、RMSE
`0.306 m`，NIS/NEES 均为 10/10 seeds available，arrival inversion 共 70 次，
online truth leakage 为 0；每 seed 平均运行约 `0.586 s`。当前 profile 的 governance
判定为不通过，说明长机动/重复交叉条件下 CV+GNN 身份连续性仍需真实数据标定，
不能因为 runner 已实现而宣称关联问题已解决。

## 15. P1 Dense/Crossing 固定标定矩阵评审

新增 runner 将 GNN 工程参数治理固定为 54 个组合，并明确区分 screening、
confirmation 和 promotion review：10-seed 阶段只负责在同一 frozen input digest 上
排序；20-seed 阶段只复跑 baseline、最佳 GNN 和最佳输入上的轻量 JPDA。所有指标均
来自已有 truth-isolated online tracker 加 evaluator-only truth，在线 leakage 必须为
0。

排序不能解释成自动调参或运行时切换。20-seed 准入同时要求 IDSW、identity
continuity、false-track、p95 latency 和 truth isolation 五项门限，任何 unavailable
均不通过。即使候选通过，输出也只是 `promotion_recommended`，默认在线关联器继续为
GNN/Hungarian，需 main/D6 复核真实 AirSim 证据后另行决定。

单元测试覆盖完整 54 组合、同 digest、10/20 seed 接口、逐项指标和缺真实输入时
unavailable。2026-07-13 已输入 strict nominal 4 m 与 tight 2 m 各 20 seeds 的真实
AirSim/D1 replay 和冻结预算：最佳 GNN 候选 IDSW `1.3583 -> 0.6167`（下降
`54.6%`），continuity `0.9810 -> 0.9840`，P95 `24 ms`。continuity 增益只有
`0.002908`。v1 固定 `+0.10` 曾据此拒绝；完整 v2 重算得到 headroom `0.018954`、
所需提升 `0.001895`、error reduction `15.3448%`，并同时证明 IDSW、false-track、
P95 和 truth isolation gate 通过，因此形成总体 promotion review recommendation。
轻量 JPDA 在同输入下退化，默认 GNN/Hungarian 不变，也不宣称轻量 JPDA 已达到完整
JPDA 工程能力。

### 15.1 D1 Freeze Truth Sidecar 评审

D1 freeze 的在线产物和离线真值采用不同 schema：governed records 不含身份，
`offline_truth.json` 才包含 evaluator-only samples。D2 现在保持该隔离边界，先转换
在线 records，再由独立 adapter 把 D1 三维 NED sample 映射成 D2 二维离线 label。

frame mapping 以 measurement timestamp 为主，不把 `source_payload_index` 无条件当作
D2 frame index；只有同时间候选不唯一时才允许用二者相等消歧。任一 sample 的 NED、
时间、identity、position 或 replay frame 映射不合法都会拒绝整个 sidecar，避免静默
错标造成虚假的 IDSW/continuity 结论。适配结果只在 offline evaluator 中出现，不改变
默认 GNN/Hungarian、中心 `global_track_id` 或在线日志合同。

### 15.2 真实 AirSim 来源分类复核

main 的冻结流程使用 `real_airsim_blocks_d1_governed_replay` 标识来源，原实现却仅以
`source == "airsim"` 判定，造成真实输出的 `airsim_evidence` 假阴性。D2 已统一
screening、confirmation 和 JPDA 对照的分类规则：legacy `airsim` 与
`real_airsim_*` 为真实 AirSim，synthetic 来源不能靠字符串包含关系通过。该元数据修复
不改变任何关联结果和准入结论。2026-07-13 strict 输出已使用修复后的分类规则生成；
更早历史 JSON 不回写。

## 16. 六档身份连续性难度治理评审

本轮把 `nominal`、紧密交叉、漏检、杂波、延迟噪声和组合压力六档作为显式证据维度，
而不是从 replay 名称猜测场景。实际注入参数由 main 记录，D2 只验证同档一致性、
truth sidecar 隔离和输入 digest。相同 seed 可在不同档复用，但同档重复 seed 被拒绝。

报告同时保留总体排序和按档指标，避免 nominal 的理想结果稀释 combined 的身份风险。
每档都能查看 baseline/最佳 GNN/轻量 JPDA 的 IDSW、continuity、false-track、RMSE、
latency 和准入结果。若全部算法仍取得零 IDSW 与满 continuity，系统明确记录该 fixture
没有算法区分度；此时即使绝对指标很好，也不能据此升级 JPDA 或冻结新 GNN 参数。

代码回归已覆盖六档复用 seed、分档聚合、combined 20-seed confirmation、无区分度
判断、未知档位与不一致元数据 fail closed。真实六档 AirSim 采集和难度有效性结论仍属
main/D6 后续工作。

## 17. Truth-free 观测压力 transformer 评审

仅把同一易 replay 改成六个标签不能形成有效算法试验。新增 transformer 因此工作在
D1 governed record 层：保留真实捕获几何，仅对 D2 可见的雷达观测施加连续漏检、匿名
杂波、异步到达和协方差膨胀。它不接受 sidecar，输出也由递归字段审计确认 online
truth leak 为 0。

设计上将“场景几何”和“观测压力”分离。2026-07-13 已由 main 完成并声明 2 m tight
crossing 与 4 m nominal 各 20-seed 捕获，D2 没有移动观测去伪造交叉。实际 spacing
写入 D1 provenance 后由 transformer 交叉校验。该边界继续适用于后续场景：transformer
能证明压力注入真实发生且可复现，但不能单独证明目标真实间距，最终证据仍由 main
capture metadata 与 D6 报告共同给出。

专项测试覆盖统计差异、匿名虚警、双时间戳/协方差/lineage、同 seed 可复现、输入不被
修改、truth key fail closed 和现有 D2 adapter 兼容。默认 GNN/Hungarian、54 组矩阵及
JPDA 准入逻辑没有改变。

## 18. Spacing provenance 与逐 seed 治理复核

真实 AirSim P1 case 现在不能只依赖 manifest 的难度名称。D1 governed adapter 会把
捕获时的 `target_spacing_m` 和 D2 stress profile 传入 frame metadata；loader 与 runner
都验证 nominal/单压力约 4 m、tight/combined 约 2 m。spacing 缺失、来源值冲突或
profile difficulty 冲突均 fail closed，避免把 4 m replay 错报成 2 m tight crossing。

治理键保持 `(difficulty, seed)`。实际 dropout 时长、延迟和杂波数可按 seed 变化；
profile/schema/version 等同档不变量仍须一致。分档输出补充 NIS/NEES availability，
promotion 仍固定使用 IDSW、continuity、false-track、P95 和 truth leakage 五项门限，
通过也只生成评审建议，不自动替换默认 GNN/Hungarian。

## 19. 真实稀疏 Replay Truth 对齐复核

D1 truth sidecar 是完整 AirSim truth 时间线，governed replay 则可能因某时刻没有匿名
传感器观测而缺 frame。原 adapter 把这种合法稀疏性当作结构错误，导致 40-episode
pipeline 在 `t=4.6` 中止。修复后仅精确对齐冻结 `1e-9 s` 容差内的 replay frame，
缺 frame 样本计入 identity-free unmatched 审计，不做最近邻或伪造 label。

alignment summary 随 FrozenReplayCase 进入 screening、confirmation、逐 seed 和分档
聚合，明确报告 complete/partial/unavailable、matched/unmatched 数和原因。无匹配标签
时 truth-based 指标 unavailable；非法位置/时间、重复样本、同时间多 frame 无法消歧
仍 fail closed。spacing/provenance 和默认 GNN/JPDA promotion 合同未改变。

## 20. 2026-07-13 Strict 真实 AirSim 权威状态

- nominal 4 m 与 tight 2 m 各完成 `20` 个真实 D1 governed replay seeds；2 m 捕获不再
  是待办项。
- 最佳 GNN 候选 IDSW `1.3583 -> 0.6167`，下降 `54.6%`；continuity
  `0.9810 -> 0.9840`；P95 loop latency `24 ms`。
- v1 admission 要求 continuity 绝对提高 `0.10`，该规则在高基线时不可达；v2 已改为
  消除至少 10% 基线剩余错误。2026-07-15 完整冻结重算中总体联合 gate 已通过并形成
  promotion review recommendation；轻量 JPDA 退化，默认 GNN/Hungarian 不变。
- truth timestamp 只在 `1e-9 s` 内 exact matching。无严格对应 frame 的样本保留为
  `partial/unmatched`，不做最近邻补齐，不伪造 label；online truth leakage 为 0。
- 2026-07-13 当时 D2 完整回归为 `93 passed`；当前完整回归为 2026-07-14 的
  `99 passed, 1 warning`。本机 Matplotlib `Axes3D` warning 不影响 D2 功能。
- 下一轮 P1 使用更长时窗和 OOSM/遮挡/漏检/杂波组合，标定 gate/risk、M-of-N、
  false-track、NIS/NEES 和 track lifecycle。完整 JPDA/MHT、Stone Soup/FilterPy
  端到端 tracker 继续保持 P2 optional/offline 边界；六维规则基线已实现，但跨模块接入和
  多 seed 标定仍保持 P2 边界。

## 21. 2026-07-14 Truth Policy 与 Lifecycle 评审

本轮 P0 修复不改变 GNN/Hungarian、Kalman、gate 或 lost/drop 数值。`Tracker` 新增显式 `online/offline` truth policy：online 是默认 fail-closed 路径，在状态变更前递归拒绝 Detection、frame 参数和 metadata 中的 truth/actor/object identity；offline 仅供 synthetic/evaluator truth 评分。main owner 的 `online_truth_isolated/online_truth_hints_used/truth_metrics_available/continuity_available` 仅在值为布尔型时作为状态通过，不能承载身份字符串。

truthless summary 不再以 `0` 冒充 IDSW、continuity 或 RMSE，三个字段保留但值为 `None`，并带一致的 availability/reason。离线 truth 确实证明零 IDSW 时仍输出 available `0`。birth/lost/drop/rebirth 与 transitions 现可从不含 truth 的 tracker 状态事件直接审计，其中 rebirth 仅表示 lost 航迹重获。

2026-07-14 专项场景包含 8 类拒绝输入、main owner 四布尔状态正例、3/5 帧 truthless replay 和 7 帧 lifecycle 序列；完整 D2 测试为 `98 passed, 1 warning`，验收阈值为零失败和零在线状态副作用。`T001 -> T005` 的真实 lifecycle 参数调优、M-of-N/false-track 分档冻结仍是 P1，不由本批接口收口替代。

## 22. `T008` 真实 episode 复核与处理决定

2026-07-14 对 1 个真实 M5N2 baseline seed、351 帧进行只读复核。离线真值仅用于
事后确认问题性质：`T002` 与 `T003` 在 31.3--31.7 秒均位于第二个真实目标附近，
证明 D1 `global_track_002/003` 是重复解释；在线修复没有读取该结论。31.8 秒
`global_track_002` 对应位置跳到约 `[13.5,-24.9] m`，后续又多次跳变，D2 因缺少
上游 source-track 约束产生 `T004...T008`，并由下游形成计划版本 33--45 的额外变更。

D2 决定不扩大马氏门限、不降低确认条件、不换 JPDA/MHT，也不使用 AirSim actor ID。
本次采用上游航迹谱系连续性、门内影子 birth 抑制和同源 teleport 隔离。四帧匿名
回归证明两个真实运动链只保留两个规范 ID，且新 D1 source ID 可在几何可行时归并到
既有 D2 ID。完整回归 `99 passed`。

该决定是模块级 P1 修复，不替代 D1 重复航迹修复，也不替代 main 的真实 AirSim
复跑。修复后同 seed 结果已经获得，详见下一节；2026-07-15 的普通 M5N2 已完成
20 case 并补齐 D2 时延，但显式 teleport/影子扰动、offline identity 和计划 churn 的
统计稳定性仍列为 main 集成验收项。

## 23. Post-batch baseline/candidate 复核决定

2026-07-14 复核真实 Blocks M5N2 seed 1 的 post-batch baseline 142 帧和 candidate
141 帧。D1 前 2 帧未形成航迹，之后始终只有 `global_track_001/002`；D2 同期始终
只有 `T001/T002`，最大活动规范航迹数 2。两组最终生命周期均为 birth 2、lost 0、
drop 0、rebirth 0，未出现 `T003...T008`。来源绑定稳定为
`global_track_001 -> T001`、`global_track_002 -> T002`。

在线 IDSW/continuity 仍不可用，这是在线 truth 隔离的正确行为。使用独立 sidecar 的
D2 governed replay 评分得到两组 IDSW 0、continuity 1.0、false track 0、truth
leakage 0；对 main 已发布 track records 的事后裁决得到 IDSW 0，continuity 为
0.985915/0.985816，差额是启动前 2 帧无规范航迹，而不是身份交换。

本批没有出现 source conflict，`suppressed_births` 和 quarantine 都为 0，因此只能
确认来源治理没有误杀正常数据，不能用这两个平稳 episode 宣称 teleport 抑制已在
真实扰动下标定。D2 评审决定：同 seed `T008` 复发项关闭。后续普通 M5N2 已完成
20 case，但未加入重复来源、teleport、dropout、clutter、合法新目标 birth 或该批离线
身份评分；下一验收改为至少 10 个显式受治理扰动 case，不再把普通 seed 数量作为缺口。
默认 GNN/Hungarian 和全部 P0 合同不变。

## 24. 2026-07-15 Ceiling-aware v2 完整冻结证据评审

- **输入**：六档真实 AirSim frozen replay/truth；screening 6x10 seeds，confirmation
  6x20 seeds；本批未启动 AirSim。
- **治理**：schema `d2-p1-identity-calibration/v2`，policy
  `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`；阶段内 digest 唯一，
  全部在线 truth leakage 为 0。
- **总体候选**：`gnn-g5.99-qa1-ld3_7-mw0.5x`，IDSW 下降 `54.6012%`，continuity
  error reduction `15.3448%`，false-track 0，P95 `15.470 ms`。五项联合 gate 均
  通过，`promotion_recommended=true`。
- **分档**：clutter/combined 完整通过；nominal/tight/dropout/delayed 的 baseline
  IDSW=0，按不可测改善比例 fail-closed。dropout truth alignment 为 partial，不做
  最近邻补齐。
- **算法评审**：候选只获得提交评审资格；`default_online_path_changed=false`。JPDA
  research adapter 的 IDSW/continuity 明显退化，不进入主线候选。
- **耗时与产物**：runner wall time `2501.32 s`；完整 JSON、中文报告和真实数据图位于
  `research_modules/d2_data_association/outputs/p1_identity_ceiling_aware_v2_20260715/`。

## 25. 2026-07-16 来源身份治理指标评审

本轮复用现有 GNN/Hungarian、Mahalanobis gate、source continuity cost、shadow-birth
suppression 和 bound-source quarantine，没有引入第二套局部视觉关联器。D2 对
namespaced `source_track_ids` 的使用仍限于弱来源谱系：它可以约束既有规范航迹的连续性，
但不能把 D1/D5 local ID 直接变成 `global_track_id`。

新增三项显式审计指标：

- `source_binding_conflict_count`：逐帧累计
  `AssociationResult.metadata.source_binding_conflicts`；
- `source_lineage_quarantine_count`：逐帧累计 `quarantined_sources`；
- `upstream_local_identity_rejection_count`：只累计经验证的 frame metadata 非负整数，
  缺失为 0，类型错误或负数 fail closed。

三项已进入 `MetricsRecorder.summary()`、逐帧 risk summary、episode replay risk、threshold
sensitivity 行、多 seed group、dense/long calibration per-seed/aggregate 和 P1 identity
calibration 聚合。它们当前是审计字段，不新增 D4 soft/hard 原因，也不改变
`id_switch_count`、truth availability 或默认 admission/ranking。

2026-07-16 验证覆盖连续同源无冲突、同一来源集合跨两个 canonical track 冲突、绑定来源
马氏不连续隔离、零检测上游塌缩拒绝只审计、5 类非法 metadata 和 legacy 零值。两条
3-frame synthetic replay seed 7/8 输出 conflict=`1/1`、quarantine=`1/1`、upstream
rejection=`2/4`，多 seed 均值=`1/1/3`。完整 D2 结果为
`123 passed, 1 warning`，验收阈值零失败；warning 为环境 `Axes3D`。

评审结论：D2-owned 显式指标接口缺口关闭；默认 GNN/Hungarian、gate、source weight、
lifecycle 和 risk thresholds 不变。本轮没有 AirSim 实跑或真实统计证据。真实至少 10 个
受治理扰动 case、false suppression/recall 和 offline identity 置信区间继续列为 P1，
main/D1 负责生产可信 namespaced lineage 与 upstream audit metadata。

## 26. 2026-07-20 六维稀疏路径评审

### 26.1 设计决定

- 保持既有二维 `GNNHungarianAssociator`、`Tracker`、replay 和 JPDA/MHT 行为不变；六维
  路径使用独立 DTO/Tracker，避免为新规模需求破坏历史基线。
- `Sparse3DGNNHungarianAssociator` 中 GNN 明确为 Global Nearest Neighbor。候选图是
  确定性稀疏优化结构，不是 Graph Neural Network；D5 的学习式跨视角关联不在 D2 冒名
  实现。
- 状态固定 `[pN,pE,pD,vN,vE,vD]`，gate 固定三维位置 innovation。相关 D1 source
  posterior 保留完整 6x6 covariance 并走 CI；独立六维/位置-only 输入分别走 Joseph
  update。速度只作有限交叉 tie-break，不改变 gate 自由度。
- KD-tree 使用协方差最大特征值构造保守查询半径；精确门控后按候选图连通分量运行
  Hungarian。不同分量无可行边，因此合并后保持全局最近邻语义。
- `GT3D-*` 只由 D2 创建。上游 D1 `global_track_id` 值被 adapter 忽略；online DTO
  递归拒绝 truth/actor/object/entity/canonical identity。
- D1 fused-track adapter 以 state-valid timestamp 作为关联 epoch，并把原始 sensor
  measurement/arrival timestamp 保存在 source metadata，避免状态时刻与量测时刻错配。

### 26.2 结果

- 原六维专项 13 个和新增速度稳定性专项 3 个覆盖 5/20/50/100/200、Down 轴门控、
  交叉、两帧漏检、15 个虚警、truth fail-closed、D2 ID ownership、有界 history/log、
  完整 covariance 和速度离群值；完整 D2 为 `139 passed, 1 warning`。
- 200 目标执行 3 个 trial、共 90 个测量帧：候选/全对始终为 `200/40,000`，component
  pair `200`，peak component `1`，裁剪 `99.5%`；聚合关联/tracker-step P95 为
  `7.056/26.797 ms`，max 为 `22.471/41.613 ms`。
- 在线 `id_switch_count`/continuity 仍为 `None + unavailable`，risk summary 可用；独立
  offline evaluator 对 crossing/漏检/虚警得到 IDSW 0，且 truth 不回写关联路径。

### 26.3 评审结论

D2-owned 原生六维规则关联 GAP 关闭，状态从“未实现”改为“局部基线已实现、集成与
标定开放”。当前证据不构成修复后 200v200 全链路、实时 SLA、AirSim 或多 seed 结论。
main point-mass bus 已有只读诊断，但修复后复跑、20 未见 seed、CI 权重/NIS-NEES、
极端大分量预算、六维 JPDA/MHT/OOSM 与高阶滤波继续开放；默认二维路径不变。

## 27. 2026-07-20 六维速度状态稳定性评审

### 27.1 根因与设计决定

main 只读 50v50、seed 17、2.2 s、radar-only 诊断显示，D1 速度 P50/P90/max
`6.28/12.16/21.03 m/s`、Pvv trace `101.24/110.31/112.32`，旧 D2 却变为
`8.89/17.43/27.49 m/s`、trace `62.95/69.37/70.86`。评审确认旧路径不是每帧直接
复制速度：只在 birth 复制一次，之后反复把 D1 六维 posterior 当作独立三维位置量测。
adapter 丢弃 Ppv，D2 预测又生成自身 Ppv，导致位置 residual 持续注入速度并错误收缩
Pvv。

本轮设计决定如下：

- `Detection3D.state_estimate_covariance` 明确表示相关 source posterior 并保留完整 6x6
  covariance；marginal 不匹配 fail closed。
- 相关 posterior 使用 covariance intersection，当前 track weight 固定 `0.5`；独立
  六维量测和位置-only 量测分别使用 6D/3D Joseph update。
- velocity NIS 超三自由度 99% 门限时通过相似变换膨胀速度 covariance，完整 cross
  block 随之缩放；关联速度 cost 在门限处封顶，位置 3D Mahalanobis gate 不变。
- 不读取 truth/actor/object ID，不按 4.7 m/s、速度模长或场景名裁剪，也不复制或重绑
  上游 `global_track_id`。

### 27.2 验收结果

| 场景 | 速度结果 | covariance / 稀疏结果 | 身份与位置 |
| --- | --- | --- | --- |
| seed 17，50 条，12 帧，0.2 s | 输入 `5.415/7.960/12.274`，输出 `5.082/6.401/7.218 m/s` | 旧/新 Pvv trace `62.76/101.181` | RMSE `52.634 -> 48.364 m`，IDSW 0，continuity 1.0 |
| seed 29，2 条 crossing，21 帧 | 注入一次速度离群值，NIS/cost gate 均触发 | 交叉帧候选 4 | 活动 2，IDSW 0，continuity 1.0 |
| seed 41，200 条，10 帧，0.2 s | 输入/输出 P90 `8.097/5.980 m/s` | 每更新帧 `200/40,000`，Pvv trace `75/69.685` | 活动 200，IDSW 0，continuity 1.0 |

原六维专项加本轮 3 个专项均通过，D2 全量结果为 `139 passed, 1 warning`；warning 是
环境 Matplotlib `Axes3D`，不影响数值结果。在线 tracker 输入无 truth；IDSW/continuity
由关联完成后的隔离 offline evaluator 评分。

### 27.3 评审结论与限制

D2-owned“速度均值放大且 covariance 伪收缩”缺口以协方差一致的 source-posterior
baseline 关闭。固定 CI track weight `0.5` 只获得当前确定性样本的通过状态，没有参数
最优性或 promotion 结论。后续至少需要 20 个未见 seed 的 CI weight sweep、按距离/
频率/covariance 分组的 velocity NIS coverage、隔离 offline 六维 NEES coverage、持续
加速度/协调转弯/漏检/OOSM，以及 main 修复后 50v50/200v200、D3 reachable count 和
端到端时延复跑。本轮也不改变跨节点多 source 数值 CI 仍由 D1 owner 执行的职责边界。

## 28. 2026-07-20 Scalable 3D evaluator identity 合同评审

评审决定把“在线 truth-free association”和“离线 identity join”保持为两条物理分离的
数据路径。在线 D2 继续发布 `None + unavailable` identity 状态；离线 evidence 只记录
D2 canonical ID、frame/lifecycle/association state、source observation lineage、replay
generation 和 D1/D2 record sequence。truth sidecar 不得出现 global track map。

D2 冻结 evidence、observation truth、frame mapping、metrics、evaluation 五个 `v1`
schema，并提供 deterministic writer/loader 和 file evaluator。bundle 绑定三个源文件
hash，episode manifest 再绑定 bundle hash；schema/hash/sequence/online truth isolation
之外，sequence 还逐项绑定 D1 lineage 与 D2-owned ID、六维 state/6x6 covariance、frame、
lifecycle/association，并检查完整 D2 track-frame 集合。任一失败不产出 artifact；语义
不完整则逐 mapping 输出 ambiguous/unavailable 和原因，且 IDSW/continuity/duplicate
为 `None`。

算法评审确认：多 source observation 全指向同一 truth 才可形成 track mapping；一 track
多 truth 不做强制 Hungarian，一 truth 多 track 保留并计 duplicate。显式 replay 需
递增 generation；未标记重复和跨 track lineage 重绑阻断指标。IDSW、稳定帧、coverage
和 duplicate 已由专项直接与 `MetricsRecorder` 数值对照。

23 个专项和完整 `162 passed, 1 warning in 30.63s` 通过。本轮没有修改 tracker、
associator、gate、owner、JPDA/MHT 或控制代码，没有 AirSim/多 seed 性能证据。评审结论
是 D2-owned contract GAP 关闭；main evidence producer 当前跳过无 lineage track/frame，
与完整性合同不一致，D6 正式消费和 episode 统计继续开放。

## 29. 2026-07-22 陈旧观测重放与重复航迹治理评审

### 29.1 机制判定

active-risk seed 1005 的 GT4/GT6 离线谱系都对应同一目标，但在线修复不得读取该 truth。
在线证据显示，GT4 持续接收新的雷达 observation，GT6 的
`latest_observation_id=radar-s000002-d0003` 从 `t=0.439 s` 后重复出现。外层 detection
ID 和状态有效时刻每帧变化，底层量测谱系没有变化。旧 tracker 把这些包装帧计为独立
hit，形成 5 个真实目标、6 条 confirmed GlobalTrack。GT4/GT6 相距 1.5--1.6 km，宽化
几何合并门会增加近邻不同目标误合并风险，因而不采用。

### 29.2 设计决定

- observation freshness 在关联前判定。证据键由 sensor namespace 和不透明 observation
  ID 组成，不解释 ID 中的序号或目标含义。
- 重复证据不进入 KD-tree、Hungarian、状态更新和 confirmation hit；量测时间冲突直接
  quarantine。迟到但具有新 observation ID 的 posterior 仍可进入当前有序 state epoch。
- tentative 首 miss 保留，连续第二次无新证据删除，避免单次异步漏配立刻销毁，同时阻止
  陈旧证据维持的新生航迹成为 confirmed。
- 航迹合并仅作为强谱系和统计一致性同时成立时的后备治理。同帧双新证据禁止合并；
  survivor 保留原中心 ID，不累计重复 hits。

### 29.3 验收与后续

seed 1005 的 10 帧活动航迹数为 `5,6,6,5,5,5,5,5,5,5`，quarantine 9 次、tentative
stale drop 1 次、coalescence 0 次、在线 truth 使用 0 次。最终保留 GT1-GT5，GT4
重获，GT6 删除。5 个合成治理专项和 1 个真实集成专项通过；完整 D2 为
`168 passed, 1 warning in 26.15s`。近邻不同目标专项验证没有误合并，异步时间专项验证
新 observation 可接收、同 identity 的量测时间冲突被拒绝。

本次首先关闭 D2-owned 单 seed 缺口。main 随后完成 development 集成复跑，并持久化
`d2-observation-evidence-governance-v1`。D6 的 plan consumption、guidance lineage、
physical window、D4 adoption、paired physical effect、paired non-degradation 和
degraded comparison 均为 20/20 available；D4 adoption 188/188，两臂各 1960 条命令。
seed 1005 离线身份只得到 GT1-GT5 五条唯一映射，在线 truth 使用 0。提交 `0fa7c00`
随后生成 clean-tree 20-seed 结果：`repository_dirty=false`、20 个 pair、D4 adoption
188/188、两臂各 1960 条命令、100 条离线唯一映射。两臂 1 s 窗口均无 5 m 拦截；
counterfactual、causal、production runtime ACK unavailable。clean 复跑已完成，但不
支持因果收益、AirSim 或 200v200 结论。

## 30. 长 episode observation evidence governance 评审

### 30.1 设计决定

- 将过旧观测接纳水位线与 claim 安全淘汰水位线分开。前者由 max-lateness 决定，后者由
  `max(retention, max-lateness)` 决定。这样较长 retention 不会放宽量测迟到边界。
- 不采用无限 tombstone。带可信源量测时间的 claim 只在安全水位线后淘汰；同一旧证据
  重放时由 admission watermark 拒绝。无源时间 claim 保留到容量上限，满载后新证据
  fail closed。
- claim 字典、航迹反向 key 和淘汰最小堆受同一 max-count 上界约束。拒绝原因分开报告，
  不把 too-old、timestamp conflict、replay 和 overflow 合并成单一计数。
- Tracker 继续只接受单调 common-epoch scan。新的 OOSM adapter 只在 Tracker 前缓存和
  排序完整 scan；不做已更新状态的回溯、重放或固定滞后平滑。
- 近邻召回和误抑制只由独立离线 truth sidecar 评分。在线 metadata、候选图、合并门和
  `global_track_id` owner 不读取 truth。

### 30.2 结果

15 个新增专项覆盖两个水位线、淘汰后旧证据、overflow、无时间戳容量、5/40 动态 N
长期循环、整帧 inversion/超窗/overflow/已释放边界，以及 3/12 目标离线基准。完整 D2
为 `183 passed, 1 warning in 29.08s`。

5 x 500 和 40 x 200 帧循环均满足 peak/current <= `6N`、overflow 0、evicted >0。
3/12 目标各 16 帧、0.75 m 间距的合法检测为 43/187，false suppression 0、recall 1.0、
错误 coalescence 0、确认延迟 0.25 s、IDSW 0。该结果只证明确定性 fixture 下不因新账本
规则损害这些样本，不能外推真实传感器分布。

### 30.3 接入和开放项

main 应显式构造 `ObservationClaimLedgerConfig`，将 config/schema version 写入 manifest。
已排序 scan 可直接调用 Tracker；arrival-order 输入存在整帧 inversion 时使用
`Scalable3DOOSMScanAdapter`。每次 submit 可释放 0 到多帧，flush 只在 episode 终止时
排空，reset 后重新构造。main 持久化公开 ledger/OOSM summary，不读取私有 claim。

真实 AirSim observation ID、时钟误差、迟到长尾、buffer/ledger 默认值和距离/遮挡/杂波
仍需标定。20/50/100/200 各 5 seed 的 formal/clean 治理复跑已在后续批次完成；
更多未见 seed、代表性难度、IDSW/continuity 和完整闭环时延证据仍开放。默认
GNN/Hungarian、中心 ID ownership、离线一对一 truth 映射和 explicit IDSW availability 不变。

## 31. 重复全量后验短时 coast 评审

### 31.1 决策

D1 未获新量测时继续发布预测后验，旧 observation ID 必须被 D2 quarantine。直接把该帧
计 miss 会让正常高频发布与较低雷达更新率之间出现错误 lost。当前只对已绑定活动航迹、
原因严格为 `repeated_latest_observation_id` 且距最后新鲜更新不超过版本化 grace 的情况
跳过 miss。航迹仍执行到当前单调时刻的运动预测，不做量测校正。

宽限不由 replay 刷新。冲突、过旧、溢出、未绑定、已 dropped 和超时均不 coast；同一
航迹在一帧出现其他拒绝原因时也阻断 coast。该边界避免把时间冲突或账本压力伪装成正常
传感器间隔。

### 31.2 证据和接入

5 个新增专项覆盖版本、跨帧 replay、超时、冲突和长循环。12 目标 200 帧 fixture 的
1920 次 replay 均未增加 hit/birth/miss，claim 内存仍有界。seed 1005 始终保持 5 条航迹，
不再先生成第 6 条再删除。完整 D2 为 `188 passed, 1 warning in 31.03s`。main 后续显式
传入 `ReplayCoastConfig`，并记录逐帧 coast 和实际 miss；AirSim grace 参数仍需按传感器
节拍标定。

## 32. scalable 尾部合并评审

### 32.1 当前行为

main 已把 episode 结束时的 D1 扫描排空改为“逐条融合、最终后验单次送 D2”。active-risk
seed 1005 的 1.1 s 当前路径只有 1 个常规 D2 帧和 1 个 finalize D2 帧，均保持 GT1-GT5。
累计 claim 10、replay quarantine/coast 0、birth 5、stale drop 0、coalescence 0；finalize
调用 1 次并合并 5 条尾部释放。该次 finalize 不生成相机或运动控制命令。

因此上一轮记录的 7 个 D2 帧、26 个 claim 和 9 次 replay 只属于旧 main 接线，不能继续
作为当前集成口径。D2 的 bounded coast 功能仍由 12 目标、200 帧、1920 次 replay 的模块
fixture 覆盖。上游先合并重复后验时，集成 replay 为 0 是合法结果。

### 32.2 测试一致性

seed1005 复现报告已升级为 v3。验收接受 replay=0 或正数 bounded replay，并强制全部
发布帧为 GT1-GT5、owner 为 `D2_center`、birth 5、coast 与 quarantine 一致、无 stale
drop/错误合并和 online truth 0。当前 2.2 s 路径得到 6 个五航迹帧、replay 0，
`acceptance_passed=true`；专项 2 个测试通过，完整 D2 为 `189 passed, 1 warning`。
本次没有修改关联、claim、coast 或身份所有权算法。

### 32.3 干预库存

保留 seed 1011/1019 的干预帧仍只有 4 条航迹。两例首扫各缺一个观测，第 5 条新鲜证据在
干预时刻之后到达，终态恢复为 5 条 confirmed。干预源的 target inventory 以冻结时刻
实际 D2 发布为准；`planning_target_identity_bridge` 与该库存一一对应，离线 truth mapping
只用于后验评分。main 应把 target_count 差额作为可用性指标，不得用 truth 补轨。

## 33. 多规模治理证据评审

### 33.1 200v200 单 seed

最新持久化 development 制品为 200 个目标、200 个资源、seed 42000、2.2 s。尾部 31 次
D2 调用合并为 1 次，`coalesced_release_count=30`；常规 D2 关联 8 次共 6.135 s，尾部
关联 1 次为 2.033 s。claim current/peak/capacity 为 1583/1583/60000，overflow、too-old、
coalescence 和 online truth use 均为 0。

1976/1976 是上一份合并前 development 制品的 claim 值。两份制品的调用拓扑不同，不能
混合成一条验收记录。当前结果来自脏工作树和单 seed，不是 AirSim、实时服务等级或完整
200v200 结论。

### 33.2 快速治理 formal/clean 批次

初次 development 批次的 `formal_episode_count=0` 保留为历史口径。提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上的复跑覆盖 20/50/100/200 各
5 个唯一 seed，共 20/20 formal/clean episode。输入清单绑定的 60 个 manifest/
online-audit/sidecar SHA-256 全部重算一致，20 个 sidecar 均为 evaluator-only 且
没有进入在线路径。

四档 claim peak/capacity 为 2390/4800、6020/12000、12070/24000、24170/48000；
safe evicted 为 285/735/1485/2985，overflow/too-old 全为 0。近邻召回率为 1.0，
false suppression 和 erroneous coalescence 为 0，确认延迟均值/P95 为 0.25/0.25 s，
online truth use 为 0。该 runner 只校验质点治理和离线 sidecar，不包含完整 D1-D7 闭环。

### 33.3 后续决策

seed1005 测试验收口径已同步，clean 治理复跑也已关闭。后续 P1 聚焦更多未见
seed、真实或代表性漏检/遮挡/杂波/OOSM 分布、离线 IDSW/continuity、真实 AirSim 和
完整闭环时延。D2 默认 GNN/Hungarian、中心 `global_track_id` ownership 和 fail-closed
边界保持不变。

## 34. 200v200 关联热路径评审

### 34.1 评审决定

五 seed profile 显示，当前 200v200 nominal 输入的主要开销不是 Hungarian，而是在线
metadata 身份键归一化、禁用键判断及 D1 adapter 的重复递归扫描。本轮只允许优化这些
等价审计操作。三维候选图、马氏门控、代价、GNN/Hungarian、航迹更新、claim ledger 和
生命周期均不得改变。

实施结果为有界字符串分类缓存、原生元组前后缀判断和删除 adapter 的冗余预扫描。
`Detection3D.__post_init__` 继续执行完整审计，Tracker step 继续阻断构造后 metadata
篡改。缓存最多 1024 项，不持有 detection、track、claim 或 episode 对象。

### 34.2 对照结果

clean 基线和候选均使用 `nominal/200v200` seeds 42000--42004，每 seed 8 个常规周期和
1 个 finalize 周期。常规关联平均累计墙钟 `7.5552 -> 2.2033 s`，finalize
`2.2747 -> 0.5646 s`，单 episode D2 合计 `9.8299 -> 2.7679 s`。五 seed 总墙钟
`49.1497 -> 13.8397 s`，总体加速 `3.551x`。

比较器对完整发布、关联、规范 ID/生命周期、claim/审计及每周期记录分别计算哈希。
45/45 周期全部一致，场景配置和离线 truth sidecar 也逐 seed 一致；两侧在线 truth use
均为 0。完整 D2 回归为 `211 passed, 1 warning`，warning 是既有 Matplotlib `Axes3D`
环境提示。

### 34.3 状态结论

D2 第二阶段热路径优化在开发态候选上通过。没有调整默认算法，也没有降低身份安全。
候选未提交、未完成固定环境 clean-tree promotion，因此不宣称实时 SLA、真实 AirSim
或完整 200v200 闭环通过。后续若继续性能晋级，只做同输入 clean 复跑和更困难输入验证，
不在本任务内继续扩展实现。

## 35. 200v200 长时重复诊断审计评审

### 35.1 根因与决策

第二阶段字符串缓存后，10 秒输入仍出现显著增长。新 profile 显示 D1 将随传感器数增长的
`sensor_health`、`association_audit` 和 `latency_audit` 复制到每条航迹，D2 对相同树
逐轨、跨适配边界重复递归。10 秒递归访问为 62,249,840 次，GNN/Hungarian 累计仅
`0.990 s`，因此本轮继续限定在元数据审计边界，不调整关联算法和频率。

实现采用批内代表审计和 D1 到 D2 合同投影。全部原始 metadata 仍受身份检查；只有完全
由可信内置容器和标量组成、无循环且内容相等的共享诊断复用结果。未知或自定义 Mapping
始终完整审计。恶意恒真 `__eq__` 且第二项含 `truth_id` 的专项继续 fail closed。通过后
不再把 D1-owned 大型诊断树复制到 `Detection3D`，对象构造和 tracker step 两道检查保持。

### 35.2 验证

最终审查加固代码的自包含 200 航迹、48 周期基准为
`16.858297 -> 6.472896 s`，加速 `2.604444x`，48/48 周期语义一致，机器可读文件
SHA-256 为 `8a8f9781955e22e91f87aecdeb1cb9f049fda43e1bbd0340ae62da6d5583afa5`。

五 seed 短时对照 `13.3842 -> 4.9606 s` 和 10 秒 seed 42000 的关联
`35.8121 -> 5.5057 s`、finalize `1.1951 -> 0.1525 s` 均来自审查加固前候选。这些
计时不代表最终加固性能；45/45 和 48/48 周期四个语义域哈希及在线 truth use 为 0 的
证据仍有效，最终计时由 main 同输入复跑。

审查加固后专项为 `25 passed`；`214 passed, 1 warning in 48.48s` 是加固前全量结果，
最终全量由 main 复跑。本轮关闭 D2-owned 长时重复诊断审计 P1 缺口，不构成 AirSim、
实时 SLA、极端候选图或完整 200v200 闭环验收。下一步保持原有真实时钟、遮挡/杂波/
OOSM 和最坏连通分量标定计划，不再扩展本轮实现。

## 36. 关联内核等价优化与可信构造复核

### 36.1 决策

冻结操作数表明 48 周期的 dense pair 为 1,820,766，但 KD-tree 后只有 9215 次位置马氏
求解、9017 条合法边、9012 个匹配，峰值 component matrix size 为 2。因此保留现有稀疏
候选和全部门控，仅合并 covariance 特征值/KD-tree 调用，复用同周期匹配 velocity NIS
与 consistent covariance governance，跳过 1x1 Hungarian。输入、频率、合法候选、门限、
truth isolation、中心 ID 和 IDSW 语义不得变化。

主控复核发现初版把 `_prevalidated_state_estimate_covariance` 暴露为 dataclass 构造参数，
可伪造 consistency 绕过整体 6x6 PSD 检查。最终实现将该 field 设为 `init=False` 且无构造
默认赋值，只允许 D1 adapter 在同一调用内预置刚治理的同一 ndarray；regularized 输入走
普通构造和完整回退。负例证明边缘正定、交叉项导致整体非 PSD 的矩阵即使带伪造诊断仍
被拒绝，旧关键字由普通构造直接拒绝。公开 DTO/序列化不变。

### 36.2 证据

输入 SHA-256 为 `3d2b4ae9f8036ae036d877a9f0e48fc7b7b1d9555bc9662b909cc9df2206924e`，
truth sidecar 未读。固定操作数逐项相等，48/48 周期语义 SHA-256 均为
`dd3f65f01fd5e0941fe5c37def42650edd7107213f7ae97c528c64688a8721ab`。7 次计时合计中位数
`4.859477 -> 4.018963 s`，`1.209137x`，7/7 对应样本更快；tracker 为
`2.747088 -> 2.118685 s`。完整 D2 为 `219 passed, 1 warning in 41.91s`。

### 36.3 状态

D2-owned nominal 冻结回放关联内核重复计算缺口关闭。真实 AirSim observation ID/时钟、
代表性遮挡/杂波/OOSM、极端大连通分量、固定硬件周期分位数、多 seed offline
IDSW/continuity 和完整 200v200 闭环继续保留为 P1；本结果不构成实时 promotion。

## 37. 三 seed clean 集成晋级评审

### 37.1 评审输入

main 比较 `8f86192` 与 `f80b5bd` 的独立 clean 输出。三组均为 nominal 200v200、
10.0 s，seeds 42000/42001/42002；有限状态和在线 truth use 为 0。每组 D2 association
均调用 47 次，终态航迹数分别为 205、204、203，两侧逐 seed 一致。

### 37.2 结果

D2 association 累计耗时三 seed 均值 `8.317513 -> 7.671266 s`，约下降 `7.77%`。
跨提交逐条语义审计和 topic counts 三组均通过。D3 随机 `plan_id` 只按 occurrence/version
规范化，且先核对 ACK 原始载荷 SHA；owner、version、coalition、`global_track_id`、
command 等业务字段保持精确比较。D2 发布自身未忽略字段。文档同步后的完整回归为
`219 passed, 1 warning in 49.75s`，零测试失败。

### 37.3 决定

接受 `f80b5bd` 上 D2 批量 KD-tree/eigenvalue、velocity innovation/covariance governance
复用和已门控 1x1 component bypass 的三 seed clean 集成非退化证据。nominal 集成复跑
待办关闭，实时和复杂度待办不关闭：短长对照仍将 D2 association 判为超线性。真实
AirSim 时钟、遮挡/杂波/OOSM、极端大分量、固定硬件周期分位数和离线 IDSW/continuity
继续保留为 P1。

## 38. 2026-07-22 部分身份诊断评审

评审接受在 evaluation v1 中增加可选
`d2.scalable3d_partial_identity_diagnostics.v1`，前提是 strict metrics 完全不变。
新块只使用 evaluator-only lineage truth sidecar，禁止最近距离、actor/object/target
名称和终端邻近。在线 D2 发布、风险摘要和中心 ID registry 不消费该块。

分母已经冻结：mapping coverage 只评分 `created/matched`；完整帧 coverage 要求本帧
truth presence 非空且全部受评分映射可评估；转移 coverage 统计相邻 truth-presence
帧的唯一锚点。只有同一真值帧恰好对应一个唯一可评估 `global_track_id` 时才建立下界
锚点；多航迹帧被排除并记录原因，不使用 strict metrics 的持久化代表顺序。IDSW lower
bound 可比较跨不完整帧的连续唯一锚点，锚点区间不重叠。零锚点转移时不输出 0；由于
侧车不完整，upper bound 固定 unavailable。

单 seed 只读复算使用 clean source commit `0d2da25`、nominal 200v200、10.0 s、
seed 1000。原 `8906 available / 13 ambiguous / 725 unavailable` 不变；受评分 9038、
非评分状态审计 606、可评估 8906、coverage `98.5395%`、missing 119。严格 IDSW 仍
unavailable；1 个重复映射真值帧被排除，385 个唯一锚点区间仍得到部分下界 7。该重复
帧原本也不完整，因此修正未改变 385/7。该下界不是完整 IDSW，不能参与 promotion 或
continuity 计算。

相关身份测试共 32 项，覆盖全可用、缺失、歧义、交叉、duplicate truth mapping、不完整
帧重复映射、零转移、truth-free online DTO、tamper rejection 和旧 v1 兼容；完整 D2 为
`228 passed, 1 warning in 29.26s`。重复映射顺序互换专项保留 strict `IDSW=1` 和
duplicate=2，同时使部分下界 unavailable。main/D6 尚未重算 20-seed，因此评审状态是
“D2 producer 合同完成，跨模块聚合待接线”，不写成多 seed 性能完成。
