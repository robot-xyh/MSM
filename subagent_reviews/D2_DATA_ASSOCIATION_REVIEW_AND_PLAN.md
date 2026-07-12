# D2 多目标跟踪与数据关联综述及子方案

**定位**：维护稳定的 `global_track_id`，在目标交叉、密集编队、漏检、遮挡和虚警条件下抑制 ID Switch。
**边界**：本文只讨论科研仿真、离线回放、多目标跟踪、数据关联、状态机和指标记录，不包含真实飞控、火控、毁伤、自动处置或绕过人工授权的流程。
**当前代码口径**：已落地 GNN/Hungarian、二维常速度 Kalman fallback、Track 状态机、P1 D1-governed input/offline truth/10-seed runner，以及隔离 P2 frozen replay comparison。P2 v2 同场输出默认 GNN、模块内 JPDA/MHT research adapter 与 Stone Soup/FilterPy object adapter；后两者仍不是端到端 tracker，模块内 JPDA/MHT 也不是完整算法。P1 loader 可直接读取 D1 governed manifest/records，将 radar 球坐标投影到 N/E；声学/EO 因量测空间不同而显式跳过。

---

## 0. P0/P1 缺口快照

- **P0**：无 P0 blocker。GNN/Hungarian、显式 `id_switch_count`、`track_continuity`、risk summary、replay helper、按输入集合长度运行、航迹质量评分、运动一致性约束和 quality-aware gate baseline 已是当前主线并保持回归。
- **P1 合同层已闭合**：D1 governed adapter、online/offline truth 分离、association log/profile version、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed runner、availability-aware summary、M-of-N/false-track/NIS/NEES 接口及中心 canonical registry 基础已回归。
- **P1 闭合后研究**：专用真实 AirSim dense/crossing 性能标定、完整 adaptive gate 和 JPDA 同 seed/同预算对照仍可继续，但不再是 P1 合同 blocker。
- **历史基线**：2026-07-10 的 5v5/2v2 批次和 2026-07-11 早期的 seeds 7/17/27 当时不足以关闭 D2 P1，且 T001 双 primary 尚未通过。这些只作为实施前/过渡基线，不代表当前状态。
- **当前 ComputerVision 证据**：M=5、N=2 的 10 seeds 中，T001 双 primary 共识/计划授权为 8/10；D2 `id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。
- **commit 与物理边界**：二级/完全分布式 commit 正例通过，缺 ACK 时 fail-closed；这是下游沿用 D2 中心 `global_track_id` 的合同证据，不是 D2 owner failover/临时 ID 合并实现。SimpleFlight 15 s 只是诊断，30 个 active pair 无命中，物理拦截未闭合。
- **回归与 P2 边界**：D1 governed loader 属于 P1 输入合同；P2 只做隔离 benchmark。GNN/JPDA/MHT 在同一 truth-free replay 上复用 Tracker，随后由 offline evaluator 输出 IDSW/continuity；Stone Soup 1.9.1 与 FilterPy 1.4.5 只输出 object-adapter latency，身份指标以 `unavailable_reason` 标明不可用。默认依赖与在线 GNN 未改变。

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
- **3D NED 适配**：D2 可消费 D1 6D NED 输入并投影到水平面，但 D2 原生状态仍是二维 `[x,y,vx,vy]`，不是三维 tracker。
- **D6 集成**：D2 summary/logs 已含 IDSW、continuity、duplicate、risk/profile version、gate pass/reject、motion/quality 和 dense/crossing sensitivity 字段，并有 D2/D6 `id_switch_count` 合同测试。当前 P1 CV 批次已由 main/runtime/D6 生产与评分；后续专用 dense/crossing 分组标定属性能研究，不是 P1 合同缺口。

### 2.3 未实现

- **IMM/EKF/UKF**：代码中没有 FilterPy `IMMEstimator`、EKF、UKF、sigma points、CV/CA/CT 模型集或模型转移概率。当前是二维线性 Kalman fallback。
- **Stone Soup 完整追踪**：已创建 Detection/StateVector adapter，但未创建 Track、predictor/updater、JPDA/MHT tracker；不能报告外部框架 IDSW/continuity。
- **FilterPy 高阶/端到端追踪**：已创建 CV KalmanFilter object adapter，但没有跨帧关联 tracker、EKF、UKF 或 IMMEstimator。
- **自动算法升级**：当前由 CLI 或调用方显式选择 GNN/JPDA/MHT，`Tracker` 未按风险阈值自动切换。
- **真实 AirSim runtime 采集链路**：D2 已能消费离线 JSON/JSONL AirSim-like replay，但不连接 AirSim runtime，不采集真实 `simGetDetections`/ComputerVision 图像 metadata，也不负责 main/D6 episode JSONL 生产。
- **原生 3D tracker 和 OOSM 回溯**：当前 D2 不维护 6D 状态，不做异步量测回溯平滑。

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

当前顺序为：维护已闭合的 P1 D1-governed/replay/truth 合同和 10-seed runner；如有需要，再扩展真实 AirSim dense/crossing 性能标定与 adaptive gate/JPDA 同预算对照。P2 只保留隔离 adapter benchmark。

### P1 闭合维护与后续性能研究

1. 持续回归 D1 governed adapter、无 truth 在线输入/log、`d2-offline-truth-label/v1`、`rejected_pairs`、track lifecycle 与 threshold profile/version。如新增专用真实 dense/crossing replay，沿用同一合同。
2. 用多 seed 数据治理 gate/risk/IDSW 阈值，输出 IDSW、continuity、duplicate、软风险误触发率和硬风险漏报率，并保留非 2/5 数量合同验收。
3. 使用现有 M-of-N/false-track 接口做真实多 seed 网格标定，输出 init latency、漏建轨率和重复航迹率。
4. 将现有 NIS/NEES 卡方覆盖接入 D6，按传感器、距离和场景分组，严格区分 covariance 输入合法性与滤波统计一致性。
5. 在同 replay、seed 和计算预算下对比固定门限、quality-aware baseline、完整 adaptive gate 以及 GNN/JPDA；JPDA 只作为高歧义场景对照，不默认替代 GNN 主线。

### P2

- 决定是否升级原生 3D NED tracker；若升级，先定义三维状态、协方差、门控和 D1/D5 投影合同。
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
