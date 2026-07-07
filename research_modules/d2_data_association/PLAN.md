# D2 数据关联模块计划

## 1. 范围与安全边界

D2 只负责离线科研仿真、日志回放和多目标数据关联评估。模块目标是维护稳定的 `global_track_id`，降低多目标交叉、密集编队、短时遮挡、漏检和虚警条件下的 ID Switch 风险。

本模块不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程或绕过人工授权的能力。`engageable` 只是代码中的研究状态，表示航迹质量足以供下游离线分配实验使用，不代表授权、处置或控制含义。

规模边界必须保持清晰：2v2、5v5、`crossing_dense_5v5` 都只是 baseline fixture 或回放场景名。D2 的关联器、Tracker、metrics 和 dry-run adapter 均按每帧传入的 `tracks`、`detections`、`active_tracks` 长度运行，不从场景名推断目标数量，不把 main runtime 的 `--drone-count N` 复制成内部常量。

## 2. 当前代码状态概览

当前 D2 可运行路径依赖 NumPy、SciPy 和 pytest。默认工程主线是 `GNNHungarianAssociator` + 马氏门控 + 二维常速度 Kalman fallback + `Tracker` 生命周期状态机。JPDA 和 MHT 已有接口兼容、可执行的研究对照实现，但不是完整生产级 JPDA filter 或 MHT hypothesis manager。Stone Soup、FilterPy 当前只保留 optional availability 检测和显式 placeholder，不进入默认运行路径。

代码和测试已覆盖：

- `GNNHungarianAssociator` 使用 `scipy.optimize.linear_sum_assignment` 做一对一硬关联。
- `DataAssociator` 抽象接口支持替换 GNN、JPDA、MHT。
- `Tracker` 使用 `[x, y, vx, vy]` 状态、4x4 covariance、Joseph update 和确定性状态机。
- `TrackLifecycleState` 当前枚举为 `tentative -> confirmed -> engageable -> lost -> dropped`，没有 `engaged` 状态。
- `MetricsRecorder.summary()` 输出 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix、runtime 和关联风险字段。
- `AssociationRiskSummaryWindowGenerator` 可从代价矩阵、候选数、cost margin、ID switch delta、continuity 和 D5 disagreement 生成滑窗风险摘要。
- `detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、2D covariance 投影、`global_track_id` 和 metadata。
- `run_airsim_dry_run_association()` 支持 synthetic AirSim-style frame，不 import `airsim`，并在 bus message 中导出当前活动航迹和 `global_track_ids`。
- 测试包含 3 目标 dry-run episode，证明输出数量来自输入集合长度；同时包含 2v2 replan baseline，证明中心/二级切换时可保持稳定 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count` 的系统规则已有合同测试：D2 `MetricsRecorder.id_switch_count` 与 D6 episode 统计口径一致。

## 3. 输入输出合同

### 3.1 D2 输入

当前可执行实现的核心输入是二维 `Detection`：

- `detection_id`：单帧观测 ID。
- `timestamp`：量测时间，适配 D1 时来自 `measurement_timestamp`。
- `position`：二维位置或三维 NED 的水平投影 `[north, east]` / `[x, y]`。
- `covariance`：2x2 量测协方差；D1 6x6 或 AirSim-style 3x3 covariance 会投影到二维。
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
- `AssociationResult.matched_pairs`：`(track_id, detection_id, cost, probability)`。
- `AssociationResult.unmatched_track_ids` / `unmatched_detection_ids`：漏配和新建轨迹依据。
- `AssociationResult.ambiguity_score`、`rejected_pairs`、`metadata`：解释门控拒绝、候选数量、求解器、JPDA/MHT 截断等信息。
- `MetricsRecorder.summary()`：D2/D6 必须保留的 `id_switch_count`，以及 continuity、duplicate、risk、runtime、confusion matrix。

`global_track_ids` 导出列表必须来自当前活动航迹集合，不按 2 或 5 个目标预分配、截断或补齐。

## 4. 已实现能力

### 4.1 GNN/Hungarian 主线

`GNNHungarianAssociator` 是默认工程路径。它先调用 `build_gated_cost_matrix()` 计算 `N x M` 代价矩阵，其中 `N=len(active_tracks)`，`M=len(detections)`；门外候选使用大代价并记录 `RejectedPair(reason="mahalanobis_gate")`。随后通过 SciPy Hungarian 求解一对一最小代价匹配，匹配后仍会拒绝超门限 pair。

已输出的解释信息包括：

- `cost_matrix` 和 `distance_matrix`。
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
- `track_continuity`：当前是 `identity_continuity` 的别名，表示身份连续性。
- `identity_continuity`：真值存在期间由同一身份稳定覆盖的比例。
- `coverage_continuity`：真值存在期间是否被任意航迹覆盖。
- `duplicate_assignment_count`：同帧重复 detection/track 或同一 truth 被多个 track 覆盖。
- `rmse`：位置误差，仅作为几何精度指标，不能替代身份指标。
- `confusion_matrix`：truth-to-track 分布。
- `runtime_seconds_by_associator`：算法耗时。

风险摘要已经有代码基线：`AssociationRiskSummaryWindowGenerator` 从候选重叠、cost margin、ID switch delta、continuity risk、D5 disagreement 和 metadata 生成 `AssociationRiskSummary`，并进入 `AssociationLogEntry` 与 summary 字段。

### 4.5 N 规模输入与 dry-run bus 输出

D2 已有非 2/5 数量测试：3 目标 synthetic AirSim-style dry-run episode 产生 3 个活动航迹和 3 个 `global_track_ids`。这证明 `global_track_id` 输出数量由输入帧和 Tracker 状态决定，而不是由场景名决定。

2v2 active-degradation/replan 测试是身份合同 baseline：中心到二级节点切换时，如果同一 replay episode 使用同一个 Tracker 状态，D2 应通过关联和 Kalman update 保持同一 physical target 的 `global_track_id`，并保持 `id_switch_count == 0`。

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

IMM、EKF、UKF 目前是研究计划项，不是已落地代码。D2 的 `Tracker` 只有二维线性常速度 Kalman fallback。`compat.py` 中 FilterPy 的用途说明为 future IMM/EKF/UKF prototype adapters，但 `to_filterpy_state()` 是显式 placeholder。

如果后续证明机动预测误差是 ID Switch 主因，应先定义三维 NED 或二维机动模型、量测模型、协方差合同和评估场景，再决定是否接入 FilterPy 或自研 IMM/EKF/UKF。

## 6. 未实现与未使用库

### 6.1 Stone Soup 未实际使用

当前未创建 Stone Soup `Detection`、`State`、`Track`、JPDA 或 MHT 对象，也没有 Stone Soup benchmark。`compat.py` 只检查 `stonesoup` 是否可 import；如果调用 `to_stonesoup_detection()`，要么提示未安装，要么抛出 `NotImplementedError`。

暂未接入原因：

- 默认回归需要保持 NumPy/SciPy/pytest 轻依赖。
- 不希望把 Stone Soup 对象暴露到跨模块总线。
- D2 先固化 `DataAssociator`、`AssociationResult`、metrics 和 D1/D6 合同，再做外部框架对照。
- 尚缺多 seed AirSim CV replay、密集交叉和遮挡 sweep 来证明完整 JPDA/MHT 的收益。

缺少条件：

- 独立 research env 或 optional extras。
- Stone Soup adapter 映射和测试标记。
- 固定 replay 数据集、truth labels、容差和对照报告。

### 6.2 FilterPy 未实际使用

当前未创建 FilterPy KalmanFilter、ExtendedKalmanFilter、UnscentedKalmanFilter 或 IMMEstimator。`optional_dependency_status()` 只报告 `filterpy` 可用性，`to_filterpy_state()` 是 placeholder。

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
- 真实 AirSim ComputerVision replay 压测：现有 adapter 是 synthetic/replay-style，不 import AirSim SDK，也不直接消费真实 runtime JSONL。
- OOSM 回溯和平滑：当前假设输入帧已按时间整理。
- py-motmetrics/CLEAR MOT：仅可作为未来离线评估参考，当前未作为依赖或测试路径。

## 7. D2 输出如何供 D3/D4/D5/D6 使用

### 7.1 D3

D3 用 `global_track_id`、状态、协方差和 lifecycle state 构造资源-目标分配输入。D2 应向 D3 暴露当前活动航迹集合；D3 应优先消费 `confirmed` 和 `engageable`，对 `tentative`、长期 `lost`、高风险或高歧义航迹提高代价、延迟分配或等待重评估。

D2 不生成 D3 `AssignmentPlan`，也不修改分配版本。D3 的 versioned plan 和 stale version rejection 仍由 D3 负责。

### 7.2 D4

D4 不直接使用 D2 结果切换系统模式，而是把 D2 的 `AssociationRiskSummary`、`id_switch_count`、continuity、duplicate risk、D5 disagreement 和 source/link metadata 作为主动降级证据。D2 只发布风险证据，例如 `association_ambiguity`、`duplicate_track_risk`、`covariance_overlap_rate`；是否请求中心重规划、二级节点接管或分布式协同由 D4 综合 D1/D3/D5 信号仲裁。

### 7.3 D5

D5 使用 `global_track_id` 将中心航迹投影到终端相机或局部目标候选上。D5 可以回传 `TerminalAssociation`、`IdentityClaim`、候选 ID、末端不一致和锁定/保持状态作为弱证据。D5 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。如果 D5 与中心预测长期冲突，D2 只应降低身份置信或提高风险摘要，不能直接用终端真值重命名全局航迹。

### 7.4 D6

D6 消费 D2 association logs、state transitions、summary 和 confusion matrix 做系统级评估。D2 和 D6 必须显式保留 `id_switch_count` 规则：D2 内部 IDSW 与 D6 episode IDSW 口径需要一致，不能只用 RMSE 或覆盖率替代身份连续性。当前已有 D2/D6 合同测试验证同一 truth 的代表 `global_track_id` 变化会被两侧计为 ID Switch。

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

### P1

- 用真实或稳定导出的 5v5 AirSim ComputerVision replay JSONL 校准 `AssociationRiskSummaryWindowGenerator` 的窗口长度、cost margin、candidate overlap、D5 disagreement 和 IDSW delta 阈值。
- 固化 D2 association log schema，确保 D3/D4/D5/D6 可稳定消费 `global_track_id`、risk summary、source node、link type 和 D2/D6 `id_switch_count` 口径。
- 增加多 seed dense/crossing、短遮挡、漏检、虚警 sweep，明确哪些场景 GNN 足够，哪些场景才需要 JPDA/MHT 对照。
- 保留并扩展非 2/5 数量的合同测试，防止未来把目标数写死到算法或文档。

### P2

- 决定 D2 是否升级原生 3D NED tracker；若升级，先定义 `[px, py, pz, vx, vy, vz]`、6x6 covariance、三维门控和 D1/D5 投影合同。
- 建立 Stone Soup optional benchmark，只用于离线对照完整 JPDA/MHT，不进入默认运行路径。
- 建立 FilterPy optional benchmark，只用于 EKF/UKF/IMM 原型和强机动场景对照。
- 设计 JPDA/MHT 自动升级策略，但必须包含切换迟滞、D4/D6 阈值认可和回放证据，避免算法抖动。

### P3

- 在多 seed replay 证明收益后，再考虑生产级 MHT 分簇、N-scan pruning 或外部框架适配。
- 若 D5 多视角反馈稳定可用，再把末端关联作为低权重身份证据接入 D2 风险模型；仍不得让 D5 改写 `global_track_id`。

## 10. 验收命令

从仓库根目录运行：

```bash
git diff --check -- research_modules/d2_data_association subagent_reviews/D2_*
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```
