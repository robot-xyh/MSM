# D2 Data Association Research Module

D2 是 C-UAS 多目标数据关联研究模块，目标是在离线仿真和日志回放中维护稳定的 `global_track_id`，降低多目标交叉、密集编队、漏检、短时遮挡和虚警条件下的 ID Switch 风险。

安全边界：本模块只用于科研仿真、dry-run 和离线评估，不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置或绕过人工授权的流程。

规模边界：D2 消费每帧传入的 `tracks`、`detections` 和当前 `active_tracks` 集合，不从场景名推断目标数量，不写死 2v2 或 5v5。`crossing_dense_5v5` 等名称只是可重复 baseline fixture；main runtime 的 `--drone-count N` 只应体现为传入 D2 的输入集合长度。

## 当前能力

已实现：

- GNN/Hungarian 默认关联器，底层使用 SciPy `linear_sum_assignment`。
- `DataAssociator` 可插拔接口，当前有 GNN、JPDA、MHT 三条接口兼容路径。
- 马氏门控、二维 `[x,y,vx,vy]` 常速度 Kalman fallback 和 4x4 covariance；Detection/GlobalTrack covariance 在输入和门控边界拒绝非有限、明显非对称或明显非 PSD 矩阵，仅对数值容差内缺陷做对称化/特征值 floor。`covariance_consistency` 表示最新检查，`covariance_regularized`/`regularization_ever_applied` 与 `last_regularization` 保留历史正则化证据。
- GNN/Hungarian 主线在保留马氏门控和 `linear_sum_assignment` 的基础上，加入速度方向、短时历史和加速度异常组成的轻量运动一致性代价，并输出 motion consistency diagnostics。
- quality-aware gate baseline：按 track quality、局部目标密度、位置协方差和上一帧 association risk 对每条 track 的 gate 做保守放宽或收紧；这不是完整自适应门控框架。
- `tentative/confirmed/engageable/lost/dropped` Track 状态机。
- 每条 `GlobalTrack` 输出 `track_quality`、`association_risk` 和 `quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 与 metrics summary 同步输出 track-level 质量和风险字典，供 D3/D5/D6 消费。
- `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime 指标；无 offline truth label 时保留兼容数值字段，同时用 `truth_metrics_available=false`、`continuity_available=false` 明确标记 identity/coverage continuity 不可用。旧 replay 缺 availability 字段时按不可用处理，不能从兼容值 `0.0` 推断 continuity collapse。
- `AssociationRiskSummaryWindowGenerator` 滑窗风险摘要，汇总代价 margin、候选重叠、IDSW delta、duplicate delta、可用 continuity、D5 disagreement、source node 和 link type；不可用 continuity 不参与 `duplicate_track_risk`、`continuity_collapse` 或 hard risk 计算。
- `RiskThresholds` / `classify_risk_summary()` 软/硬风险分层，按 D4 口径区分 ambiguity/cost margin/candidate overlap 与 IDSW/duplicate/continuity collapse。
- D1 6D NED `GlobalTrack` 到 D2 2D `Detection` 的投影 adapter，保留 `measurement_timestamp`、`arrival_timestamp`、covariance 和 metadata。
- AirSim-style dry-run/replay adapter，不 import 或调用 `airsim`，并在 bus message 中导出当前活动 `global_track_ids`。
- `load_airsim_replay_frames()`、`run_airsim_replay_association()`、`run_threshold_sensitivity()` 和 `summarize_multi_seed_risk_calibration()` 支持离线 JSON/JSONL replay 读取、association log/report 输出、seed/episode/scenario/frame/offline truth label 校准元数据透传、`RiskThresholds.profile_version` 与 `association_risk_threshold_version` 记录、gate pass/reject count、motion/quality risk summary、dense/crossing threshold sensitivity summary 和多 seed 推荐阈值摘要；无 truth label 的 N-v-N replay 会用输入观测数或显式 count 字段给出 `target_count` fallback。
- P1 replay 治理默认将 simulator truth 从在线 `Detection`、track 和 association log 中移除，并将源 detection/actor ID 改为按帧匿名 ID；嵌套 actor/truth metadata 同样递归清除。GNN/Hungarian 仅看到量测、协方差、时间戳、置信度和可用特征。`OfflineTruthEvaluation` 在关联完成后按同帧输入顺序独立对齐标签，计算 IDSW、continuity、confusion matrix 和 RMSE；报告同时保留 `online_metrics` 与 `offline_truth_evaluation`，避免把在线 unavailable 误写成零。
- `InitializationGovernanceProfile` 提供版本化 M-of-N 初始化口径，默认 `2-of-3`，也可由 replay 和 gate sensitivity 入口显式传入其他 profile；离线治理输出初始化/确认延迟、成功率、虚假航迹数与比例、漏检数、虚警数、逐帧 measurement count / truth-target count 以及 mismatch frame count。
- NIS 由关联前 innovation covariance 和马氏距离计算，不依赖 truth，因此无 truth replay 仍可输出；NEES 只在独立 offline truth state 可用时计算。两者输出样本数、均值、中位数、二维/四维 95% 卡方区间及区间覆盖率，不把缺失样本解释为零。
- `build_5v5_replay_fixture()` 构造动态 5 目标 crossing/dense/漏检/虚警组合 fixture；它只用于回归和标定，不把 5 写入关联器或 Tracker。
- `AssociationLogEntry.rejected_pairs` 默认空列表并完整序列化 `mahalanobis_gate`/`assignment_above_gate` 原因；replay gate summary 按原因统计，旧 JSON 缺该字段时按空列表兼容。
- 跨节点注册基础：`SourceTrackSummary` 使用 `(source_node_id, local_track_id, local_epoch)` 命名空间、独立 measurement/arrival timestamp、6D NED state/covariance、quality、lineage/correlation status 及 candidate/current canonical hint，在线合同不含 truth。
- `CrossNodeTrackAssociator` 将 source tracks 传播到公共时刻，按完整 6D 状态和差分协方差做 Mahalanobis gate，并按 source 节点分组使用 Hungarian；`CrossNodeTrackRegistry` 因而支持一个 canonical `global_track_id` 绑定多个观察节点的 source tracklets，同时保持同一 source 内一对一。
- registry 对 `exact_known_correlation` 输出 D1 数值相关融合请求，对 `unknown_correlation` 只输出 CI/保守融合请求，对显式 duplicate、重复 payload、重复 lineage 和 stale/replay source track 在关联前拒绝；D2 不复制数值 CI。
- cross-node 在线指标输出 source binding rebind ID switch、duplicate payload rejection 和 transport/queue/fusion latency；`OfflineCrossNodeMetricsEvaluator` 在独立 truth mapping 下计算 canonical duplicate 与 track-to-track association precision/recall，不向在线 registry 暴露 truth。

### 2026-07-11 main runtime 证据

- main 在线链路已强制令 D2 输入和航迹的 `truth_id=None`；D1 -> D2 -> D3 仍按 D2 状态、协方差、质量和中心维护的 `global_track_id` 运行，不再依赖 simulator truth/actor identity 构造 D3 目标。
- `d2_governance_summary` 已进入 main episode bus 并由 D6 消费。真实 5v5 短 episode 的 main-bus 结果记录 `d2_hard_risk_frame_rate=0.0`，说明该短运行内没有由在线可观测证据触发 D2 hard-risk frame。
- 上述 `0.0` 不是在线 IDSW 或 continuity 的真值结论。在线没有 truth label 时，truth-based `id_switch_count`、`track_continuity`/`identity_continuity` 必须标记 unavailable；它们只能在 episode 结束后由隔离的 offline truth labels 评分。
- 该证据只证明 truth-isolated runtime 合同与治理事件通路已接通。真实 5v5 dense/crossing、遮挡、漏检和虚警条件下的多 seed IDSW/continuity、gate/risk、M-of-N 与 NIS/NEES 标定仍未闭合。

部分实现：

- `JPDAAssociator` 可执行小规模联合假设枚举和 marginal probability 对照，但不是完整 JPDA filter。
- `MHTAssociator` 可执行有界 branch 和短历史对照，但不是完整 MHT。
- D2 可投影 D1 3D/NED 输入，但原生 tracker 仍是二维状态。
- cross-node registry 已完成低歧义 GNN/Hungarian 注册基础，但尚无多帧 JPDA/MHT 歧义保持、owner/epoch failover 或数值融合回写。

未实现：

- Stone Soup 实际 adapter 或 benchmark。
- FilterPy EKF/UKF/IMM 实际 adapter。
- 原生 3D NED tracker。
- JPDA/MHT 自动升级触发。
- 真实 AirSim runtime 录制链路、ComputerVision 图像/metadata 采集和 main/D6 episode JSONL 固化；D2 当前只消费已导出的离线 replay。
- D1-owned 数值 CI、已知交叉协方差融合、fusion NEES/ANEES 和通信字节统计；D2 当前只发布相关性决策与融合请求。

## 目录

- `d2_data_association/models.py`：`Detection`、`GlobalTrack`、`AssociationResult`、风险摘要和生命周期数据结构。
- `d2_data_association/gating.py`：马氏距离、门控代价矩阵和歧义分数。
- `d2_data_association/associators.py`：`DataAssociator`、`GNNHungarianAssociator`、`JPDAAssociator`、`MHTAssociator`。
- `d2_data_association/tracker.py`：常速度 Kalman fallback、状态机、建轨、漏检和删除。
- `d2_data_association/metrics.py`：IDSW、continuity、duplicate、RMSE、confusion matrix、风险摘要和软/硬风险分层。
- `d2_data_association/cross_node_models.py`：source-track、canonical binding/history、相关性和融合请求合同。
- `d2_data_association/cross_node_registry.py`：公共时刻传播、track-to-track Hungarian 和中心 canonical registry。
- `d2_data_association/cross_node_metrics.py`：truth-free registry 指标和隔离的 offline cross-node evaluator。
- `d2_data_association/dry_run_adapter.py`：D1/AirSim-style dry-run 输入适配和 bus message 输出。
- `d2_data_association/replay.py`：离线 JSON/JSONL replay 读取、association report/log 输出和阈值敏感性 helper。
- `d2_data_association/replay_governance.py`：在线 truth 隔离、offline label evaluator、M-of-N 初始化、false-track、NIS/NEES 和 5v5 压力 fixture。
- `d2_data_association/simulation.py`：crossing、dense 5v5、formation、occlusion、missed、false alarm 场景。
- `scripts/run_simulation.py`：CLI benchmark runner。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法和实现说明。
- `docs/EXPERIMENT_REPORT.md`：离线仿真结果和解释。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。

## 跨模块合同

- D2 输出的 `global_track_id` 是 D3 分配、D4 主动降级证据、D5 末端配准和 D6 指标评估的共同键。
- source 的 local ID、candidate/current canonical hint 不具备身份权威；只有 `CrossNodeTrackRegistry` 能创建或更新 canonical binding。多个合法观察者绑定同一 canonical ID 不增加目标基数，也不计为 D3 duplicate assignment。
- `REQUEST_COVARIANCE_INTERSECTION` 和 `REQUEST_EXACT_CORRELATED_FUSION` 是 D2 关联/相关性决策，不是已融合状态；数值融合及一致性统计由 D1/D6 owner 接续。
- D2 track-level `track_quality` 和 `association_risk` 是下游可消费的质量/风险证据；下游可以提高代价、延迟分配或标记复核，但不得用这些字段改写 `global_track_id`。
- D5 和 D7 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count`；它不能被 RMSE、覆盖率或命中率替代。
- D2 输出的 `global_track_ids` 来自当前活动航迹集合，不截断或补齐到固定 2 或 5。
- D4 当前把 D2 风险分为软/硬两类：`association_ambiguity`、低 cost margin、candidate overlap 属于观察/二级 cue 证据；`id_switch_count` 增量、`duplicate_assignment_count`/`duplicate_track_risk` 和可用的 `track_continuity` 低于阈值属于硬风险证据。`continuity_available=false` 时不得把兼容数值 `0.0` 当作 continuity collapse。D2 只发布证据，不直接触发 `request_center_replan` 或降级。
- 多 seed 风险校准的 replay/report 应保留 `seed`、`episode_id`、`scenario_name`/`scenario`、`frame_index`、`drone_count`/`target_count`、gate threshold、`risk_profile`、`risk_profile_version`、`association_risk_threshold_version`、association logs、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、M-of-N profile、false-track、NIS/NEES、`id_switch_count`、`track_continuity`、`duplicate_assignment_count` 和 soft/hard risk summary。在线 association log 只记录 schema/profile、measurement/active-track count 和 innovation 诊断，不携带 truth label、truth target count 或 NEES；标签、真值目标数和 NEES 只存在于 `offline_truth_evaluation`。
- 真实 AirSim 5v5 replay 输入、ComputerVision metadata 采集、离线 truth labels 固化、episode JSONL schema 发布、ID switch 阈值治理和批量运行仍由 main/runtime/D6 生产/标定；D2 不连接 AirSim SDK。
- main runtime 已具备 P1 D4/D5 calibration sweep，D6 已具备标准 AirSim calibration report bundle 自动生成。D2 的对齐目标是让自身 replay/report/log 字段能进入该 bundle 做分组统计；D2 不重复实现 sweep 编排、AirSim reset 或 D6 报告生成。
- 在线 D6 治理摘要可以记录 soft/hard risk frame rate，但不得在缺少 offline truth labels 时把它解释成 IDSW=0 或 continuity 正常；truth-based 指标必须保留 unavailable 状态，待离线评分后再进入多 seed 结论。

## 运行测试

从仓库根目录：

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

从模块目录：

```bash
pytest -q
```

## 运行仿真

```bash
python3 scripts/run_simulation.py --steps 24 --seed 7
```

可选输出：

```bash
python3 scripts/run_simulation.py \
  --steps 36 \
  --seed 7 \
  --json-out artifacts/d2_results.json \
  --markdown-out artifacts/d2_results.md
```

## 可选集成

`filterpy` 和 `stonesoup` 不是运行时依赖。`d2_data_association/compat.py` 只报告 optional dependency availability，并在调用未实现 adapter 时给出显式错误。后续如需使用 Stone Soup 或 FilterPy，应放在独立 research env 或 optional benchmark 中，不进入默认测试路径。
