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
- `AssociationLogEntry.rejected_pairs` 默认空列表并完整序列化 `mahalanobis_gate`/`assignment_above_gate` 原因；replay gate summary 按原因统计，旧 JSON 缺该字段时按空列表兼容。

部分实现：

- `JPDAAssociator` 可执行小规模联合假设枚举和 marginal probability 对照，但不是完整 JPDA filter。
- `MHTAssociator` 可执行有界 branch 和短历史对照，但不是完整 MHT。
- D2 可投影 D1 3D/NED 输入，但原生 tracker 仍是二维状态。

未实现：

- Stone Soup 实际 adapter 或 benchmark。
- FilterPy EKF/UKF/IMM 实际 adapter。
- 原生 3D NED tracker。
- JPDA/MHT 自动升级触发。
- 真实 AirSim runtime 录制链路、ComputerVision 图像/metadata 采集和 main/D6 episode JSONL 固化；D2 当前只消费已导出的离线 replay。

## 目录

- `d2_data_association/models.py`：`Detection`、`GlobalTrack`、`AssociationResult`、风险摘要和生命周期数据结构。
- `d2_data_association/gating.py`：马氏距离、门控代价矩阵和歧义分数。
- `d2_data_association/associators.py`：`DataAssociator`、`GNNHungarianAssociator`、`JPDAAssociator`、`MHTAssociator`。
- `d2_data_association/tracker.py`：常速度 Kalman fallback、状态机、建轨、漏检和删除。
- `d2_data_association/metrics.py`：IDSW、continuity、duplicate、RMSE、confusion matrix、风险摘要和软/硬风险分层。
- `d2_data_association/dry_run_adapter.py`：D1/AirSim-style dry-run 输入适配和 bus message 输出。
- `d2_data_association/replay.py`：离线 JSON/JSONL replay 读取、association report/log 输出和阈值敏感性 helper。
- `d2_data_association/simulation.py`：crossing、dense 5v5、formation、occlusion、missed、false alarm 场景。
- `scripts/run_simulation.py`：CLI benchmark runner。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法和实现说明。
- `docs/EXPERIMENT_REPORT.md`：离线仿真结果和解释。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。

## 跨模块合同

- D2 输出的 `global_track_id` 是 D3 分配、D4 主动降级证据、D5 末端配准和 D6 指标评估的共同键。
- D2 track-level `track_quality` 和 `association_risk` 是下游可消费的质量/风险证据；下游可以提高代价、延迟分配或标记复核，但不得用这些字段改写 `global_track_id`。
- D5 和 D7 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count`；它不能被 RMSE、覆盖率或命中率替代。
- D2 输出的 `global_track_ids` 来自当前活动航迹集合，不截断或补齐到固定 2 或 5。
- D4 当前把 D2 风险分为软/硬两类：`association_ambiguity`、低 cost margin、candidate overlap 属于观察/二级 cue 证据；`id_switch_count` 增量、`duplicate_assignment_count`/`duplicate_track_risk` 和可用的 `track_continuity` 低于阈值属于硬风险证据。`continuity_available=false` 时不得把兼容数值 `0.0` 当作 continuity collapse。D2 只发布证据，不直接触发 `request_center_replan` 或降级。
- 多 seed 风险校准的 replay/report 应保留 `seed`、`episode_id`、`scenario_name`/`scenario`、`frame_index`、`drone_count`/`target_count`、gate threshold、`risk_profile`、`risk_profile_version`、`association_risk_threshold_version`、association logs、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、`id_switch_count`、`track_continuity`、`duplicate_assignment_count` 和 soft/hard risk summary；D2 仅把 `truth_id`/offline truth label 用于离线 metrics，不用它重命名或绑定 `global_track_id`。
- 真实 AirSim 5v5 replay 输入、ComputerVision metadata 采集、离线 truth labels 固化、episode JSONL schema 发布、ID switch 阈值治理和批量运行仍由 main/runtime/D6 生产/标定；D2 不连接 AirSim SDK。
- main runtime 已具备 P1 D4/D5 calibration sweep，D6 已具备标准 AirSim calibration report bundle 自动生成。D2 的对齐目标是让自身 replay/report/log 字段能进入该 bundle 做分组统计；D2 不重复实现 sweep 编排、AirSim reset 或 D6 报告生成。

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
