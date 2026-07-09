# D2 多目标跟踪与数据关联综述及子方案

**定位**：维护稳定的 `global_track_id`，在目标交叉、密集编队、漏检、遮挡和虚警条件下抑制 ID Switch。
**边界**：本文只讨论科研仿真、离线回放、多目标跟踪、数据关联、状态机和指标记录，不包含真实飞控、火控、毁伤、自动处置或绕过人工授权的流程。
**当前代码口径**：已落地的是 GNN/Hungarian、可插拔 `DataAssociator`、二维常速度 Kalman fallback、Track 状态机、IDSW/continuity/duplicate 指标、风险摘要、D1 投影 adapter、AirSim dry-run adapter、离线 JSON/JSONL replay reader/report、seed/episode/scenario/frame/offline truth label 校准元数据透传、`RiskThresholds.profile_version`、threshold sensitivity helper 和 multi-seed calibration summary helper。JPDA/MHT 是可执行研究对照；IMM/EKF/UKF、Stone Soup、FilterPy 仍是未来对照或 adapter 计划。

---

## 0. P0/P1 缺口快照

- **P0**：无 P0 blocker。GNN/Hungarian、显式 `id_switch_count`、`track_continuity`、risk summary、replay helper 和按输入集合长度运行的规则已是当前主线。
- **P1**：D2-owned replay/report、risk split、threshold sensitivity、multi-seed summary、metadata/profile version、D1 adapter、5v5 dense/crossing fixture 和 IDSW/continuity 基线已完成；真实 AirSim 多 seed association threshold/risk calibration 的数据生产和批量执行仍是 P1 集成缺口，依赖 main/runtime/D6 提供真实 5v5 AirSim replay、离线 truth labels、episode 级阈值配置来源和稳定 JSONL schema。
- **main/D6 最新状态**：main runtime 已新增 P1 D4/D5 calibration sweep，D6 标准 AirSim calibration report bundle 已能自动生成。D2 不接管 sweep 或报告生成；D2 后续需要把真实 5v5 replay 的 association logs、offline truth labels 和 risk profile/version 对齐到该 bundle 的分组报告口径。

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

- **GNN/Hungarian**：`GNNHungarianAssociator` 通过 `scipy.optimize.linear_sum_assignment` 求解一对一匹配，代价来自马氏距离和可选 feature cost。
- **马氏门控**：`build_gated_cost_matrix()` 生成 `N x M` cost/distance matrix，记录 `candidate_counts_by_track`、`candidate_counts_by_detection` 和 `RejectedPair`。
- **可插拔关联器**：`DataAssociator.associate()` 是统一接口，`Tracker` 只消费 `AssociationResult`。
- **二维 Kalman fallback**：`Tracker` 使用 `[x,y,vx,vy]` 和 4x4 covariance 做常速度预测、Joseph update、建轨和漏检处理。
- **Track 状态机**：代码中只有 `tentative -> confirmed -> engageable -> lost -> dropped`，并支持 lost 后重新命中回到 `confirmed` 或 `engageable`。
- **核心指标**：`MetricsRecorder.summary()` 输出 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix、runtime。
- **风险摘要**：`AssociationRiskSummaryWindowGenerator` 已从候选重叠、cost margin、IDSW delta、duplicate delta、continuity risk、D5 disagreement 和 metadata 生成滑窗风险。
- **软/硬风险分层**：`RiskThresholds` 与 `classify_risk_summary()` 已按 D4 口径把 ambiguity/cost margin/candidate overlap/D5 disagreement 归为软风险，把 IDSW、duplicate 和 continuity collapse 归为硬风险。
- **N 规模输入**：关联器按 `len(active_tracks)` 和 `len(detections)` 构造矩阵；dry-run 测试包含 3 目标 episode，输出 3 个活动 `global_track_id`。
- **D1 adapter**：`detections_from_d1_global_tracks()` 把 D1 6D NED `GlobalTrack` 投影为 D2 2D `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、covariance 投影和 metadata。
- **AirSim dry-run adapter**：支持 synthetic AirSim-style dict/object，不 import `airsim`，可从 `detections/tracks/objects`、`x/y`、`x_val/y_val` 和 2x2/3x3 covariance 生成 D2 输入。
- **AirSim-style replay/calibration helper**：`load_airsim_replay_frames()`、`run_airsim_replay_association()`、`write_replay_association_report()`、`write_association_logs_jsonl()`、`run_threshold_sensitivity()` 和 `summarize_multi_seed_risk_calibration()` 已覆盖离线 5 目标 JSONL replay、association logs、metrics、seed/episode/scenario/frame/offline truth label metadata、阈值 profile version、N-v-N `target_count` fallback、风险阈值敏感性输出和多 seed 推荐阈值摘要。

### 2.2 部分实现

- **JPDA**：`JPDAAssociator` 已能枚举小规模联合假设、计算边缘概率并输出接口兼容 `AssociationResult`。它是可执行研究对照，不是完整 JPDA filter；当前没有概率混合状态更新、完整协方差融合、track coalescence 抑制或大规模分簇策略。
- **MHT**：`MHTAssociator` 已维护有界 branch、短历史、漏检/虚警惩罚和 pruning 参数。它是 MHT-compatible research placeholder，不是完整 MHT；当前没有 N-scan pruning、长期假设树管理、分簇或中心算力策略。
- **3D NED 适配**：D2 可消费 D1 6D NED 输入并投影到水平面，但 D2 原生状态仍是二维 `[x,y,vx,vy]`，不是三维 tracker。
- **D6 集成**：D2 summary 和 logs 已含 D6 所需指标，且有 D2/D6 `id_switch_count` 合同测试；main runtime 已自动生成 D6 AirSim calibration report bundle。episode 级真实 5v5 association JSONL schema、offline truth labels、gate/risk profile/version 字段和最终分组校准口径仍由 main/D6 固化。

### 2.3 未实现

- **IMM/EKF/UKF**：代码中没有 FilterPy `IMMEstimator`、EKF、UKF、sigma points、CV/CA/CT 模型集或模型转移概率。当前是二维线性 Kalman fallback。
- **Stone Soup 实际适配**：未创建 Stone Soup Detection/Track/JPDA/MHT 对象；`compat.py` 只有 availability check 和 placeholder。
- **FilterPy 实际适配**：未创建 FilterPy filter 或 IMM 对象；`to_filterpy_state()` 是 placeholder。
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
| Stone Soup | 完整 GNN/JPDA/MHT、轨迹管理示例 | 未实际使用，仅 availability/placeholder | 需要独立 research env、adapter 映射、固定 replay benchmark；不应把 Stone Soup 对象暴露到系统总线 |
| FilterPy | EKF、UKF、IMMEstimator | 未实际使用，仅 availability/placeholder | 需要明确机动模型、非线性量测、状态维度和测试门限 |
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
- **硬风险**：`id_switch_count` 或滑窗 delta 增长、`duplicate_assignment_count`/`duplicate_track_risk` 增长、`track_continuity` 低于阈值。它们说明规范 `global_track_id` 已经发生切换、重复解释或连续性崩塌，可作为 D4 主动仲裁的硬证据。
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

2026-07-08 起，main runtime 的 P1 D4/D5 calibration sweep 会自动生成 D6 标准 AirSim calibration report bundle。D2 对该 bundle 的职责是提供可分组、可回放的 association logs 与 summary 字段，包括 `seed`、`episode_id`、`scenario_name`、`frame_index`、`target_count`/`drone_count`、gate threshold、`risk_profile`、`risk_profile_version`、`id_switch_count`、continuity、duplicate 和 soft/hard risk summary。D2 不直接生成 bundle，也不使用在线 truth ID 绑定 `global_track_id`。

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

`run_threshold_sensitivity()` 会按 gate threshold 与 risk threshold profile 输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`、seed/episode/scenario/frame metadata 和软/硬风险摘要，用于离线标定 D4 仲裁阈值。`summarize_multi_seed_risk_calibration()` 会按 gate/risk profile/version 汇总多 seed 的 IDSW、continuity、duplicate、soft/hard risk count/rate/score 分布和推荐阈值摘要。

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

GNN 在交叉窗口内只能做单帧硬判决。如果两条航迹的最优和次优候选代价差距很小，GNN 可能任意打破平局，造成后续 ID Switch。JPDA/MHT 对照能暴露歧义，但当前实现还不足以承诺消除该风险。

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
| AirSim-like 5 目标 JSONL replay | 已覆盖 reader/report/log 输出 | `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、seed/episode/scenario metadata、soft/hard risk summary |
| threshold sensitivity 与 multi-seed summary | 已覆盖变量目标数、多 profile sweep、阈值版本和多 seed 汇总 | gate threshold、risk profile/version、IDSW、continuity、duplicate、soft/hard risk 分布、推荐阈值摘要 |
| main/D6-style row metadata 与 offline truth label | 已覆盖 JSONL wrapper/payload 读取、frame metadata 透传和 offline truth label 评估 | truth label 只用于离线 metrics，`global_track_id` 仍由 D2 Tracker 生成 |
| N-v-N replay 无 truth label target count | 已覆盖输入观测数 fallback | 无在线 truth 时仍可记录 `target_count`，但 IDSW/continuity 真值评估仍需离线 labels |

默认验收命令：

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

---

## 11. P1/P2 下一步

### P1

- D2-owned 已完成：`replay.py`、AirSim-like JSON/JSONL replay reader、5 目标 association report/log 输出、软/硬风险分层、threshold sensitivity helper、multi-seed calibration summary helper、seed/episode/scenario/frame/offline truth label replay metadata、`RiskThresholds.profile_version`、N-v-N `target_count` fallback、D1 adapter、`crossing_dense_5v5` fixture，以及显式 `id_switch_count`/continuity/duplicate 指标。
- 剩余 P1 集成：main/runtime/D6 用真实或稳定导出的 5v5 AirSim ComputerVision replay 生产 D2 输入，并固化 D2->D3/D4/D5/D6 的 episode JSONL/log schema，确保 `global_track_id`、`id_switch_count` 和风险字段稳定。
- 剩余 P1 评估标签：main/runtime/D6 为真实 replay 固化离线 `truth_id`/truth position labels；在线 D2/D5 路径不得用 AirSim truth ID 做身份绑定。
- 剩余 P1 阈值与标定执行：main/D6 需要发布真实 episode 的 gate/risk threshold profile/version 配置来源，并用多 seed 真实 5v5 dense/crossing、短遮挡、漏检、虚警 replay 调用 D2 helper 校准软风险误触发率和硬风险漏报率。
- 与最新 runtime 对齐：P1 D4/D5 calibration sweep 和 D6 report bundle 已由 main/D6 提供，D2 后续工作应集中在真实 5v5 AirSim replay 的 association risk profile/version、offline truth labels、ID switch 阈值治理和 D6 分组报告校准。
- 保留非 2/5 数量合同测试，防止算法和文档回退到固定规模假设。
- 明确 JPDA/MHT 只在高歧义回放中作为对照或建议，不默认替代 GNN 主线。

### P2

- 决定是否升级原生 3D NED tracker；若升级，先定义三维状态、协方差、门控和 D1/D5 投影合同。
- 建立 Stone Soup optional benchmark，用于完整 JPDA/MHT 离线对照；当前轻量 JPDA/MHT 已是可执行研究对照，不再作为 P1 未完成项。
- 建立 FilterPy optional benchmark，用于 EKF/UKF/IMM 预测器原型。
- 设计 JPDA/MHT 自动升级阈值和迟滞，但必须先通过 D4/D6 回放证据证明收益。

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
