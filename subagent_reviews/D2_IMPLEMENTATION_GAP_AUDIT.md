# D2 多目标跟踪与数据关联实现差距审计

**审计对象**：`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d2_data_association/` 代码与测试，并抽查 `research_modules/integration_contracts.py`、`research_modules/integrated_simulation/`、`research_modules/airsim_runtime/` 中的 D2 调用边界。

**审计边界**：仅评估 D2 离线科研仿真与数据关联模块，不涉及真实飞控、硬件、火控、毁伤或自动处置逻辑。

**结论摘要**：D2 已实现可运行的 GNN/Hungarian 主线、二维常速度 Kalman 航迹管理、简化 JPDA、有界 MHT 接口、IDSW/连续性指标、弱证据风险摘要和 AirSim dry-run 适配。系统级已有 `nominal_5v5`、`crossing_5v5` 和 AirSim CV 5v5 actor 配置，但 D2 自模块仍未实现 GNN/JPDA/MHT 同场比较的 deterministic 5v5 crossing/dense fixture。未实现完整 EKF/UKF/IMM、Stone Soup/FilterPy 实际适配、完整生产级 JPDA/MHT 和原生 3D GlobalTrack 跟踪。

## 1. 总体判断

D2 当前实现符合“先用 GNN/Hungarian 做工程主线，密集交叉再升级 JPDA/MHT”的主流共识，也与 `MAIN_IMPLEMENTATION_GAP_AUDIT.md` 的 P0/P1 口径一致：P0 主线是轻量可运行的 Hungarian/ID 指标/dry-run，P1 缺口是 5v5 dense/crossing 对照、风险滑窗和主线集成合同收敛。工程策略是正确的：运行路径只依赖 NumPy/SciPy，Stone Soup 与 FilterPy 暂作为外部验证和未来适配目标。主要差距集中在更高阶运动模型、完整第三方框架适配、三维航迹原生支持、滑窗风险自动生成和更贴近 5v5 AirSim ComputerVision 的集成压力测试。

## 2. 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| GNN/Hungarian 默认关联主线 | 已实现。`GNNHungarianAssociator` 使用 SciPy `linear_sum_assignment`，支持马氏门控、代价矩阵、拒配原因、候选数元数据 | `research_modules/d2_data_association/d2_data_association/associators.py`；`tests/test_gating_and_associators.py` | 不适用 | 后续只需增加 5v5 高密交叉基准 | P0 已满足，持续维护 |
| 马氏距离门控 | 已实现。`mahalanobis_squared()`、`build_gated_cost_matrix()` 输出候选数和拒配对 | `research_modules/d2_data_association/d2_data_association/gating.py`；`tests/test_gating_and_associators.py` | 不适用 | 可增加协方差交叠率自动计算 | P0 已满足 |
| 二维常速度 Kalman 航迹管理 | 已实现。`Tracker` 使用 `[x,y,vx,vy]`、线性预测和 Joseph 更新，含 tentative/confirmed/engageable/lost/dropped 状态机 | `research_modules/d2_data_association/d2_data_association/tracker.py`；`tests/test_tracker_metrics.py` | 不适用 | 若接 D1 3D NED，需要三维状态或投影适配策略固定 | P0 已满足 |
| EKF | D2 未实现完整非线性 EKF。当前是二维线性 Kalman fallback；主审计中“EKF/滤波主线 P0 可用”对 D2 的含义是轻量 Kalman 跟踪可用，不是 D2 EKF 已实现 | `tracker.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md`；`MAIN_IMPLEMENTATION_GAP_AUDIT.md` | Phase-1 使用二维质点/线性观测，暂不需要雅可比和非线性量测 | 需要三维 NED、雷达球坐标/相机投影量测、非线性观测模型 | P2 |
| UKF | 未实现 | `compat.py` 仅报告 FilterPy 可用性；`to_filterpy_state()` 是占位 | 当前运行路径避免引入 FilterPy；未定义 UKF sigma 点模型和三维状态接口 | 需要机动/非线性仿真场景和 FilterPy 或自研 UKF 依赖决策 | P2/P3 |
| IMM-EKF/UKF | 未实现 | `D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md` 仅列为目标；代码中无 IMMEstimator | 当前机动压力测试不足，D2 重点先解决关联接口与指标 | 需要 CV/CA/CT 模型集、模型转移概率、机动目标场景和评估门限 | P2 |
| JPDA | 部分实现。`JPDAAssociator` 可枚举小规模联合假设、计算边缘概率并输出接口兼容结果；不是完整 JPDA 滤波器 | `associators.py`；`tests/test_gating_and_associators.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 为保持轻量可运行，只实现小规模离线对照；没有概率混合状态更新和完整航迹协方差融合 | 需要 Stone Soup 对照、密集交叉基准、JPDA 参数标定 | P1 |
| MHT | 部分实现。`MHTAssociator` 保留有界分支和短历史，是 MHT-compatible research placeholder；非完整 MHT | `associators.py`；`tests/test_gating_and_associators.py` | 完整 MHT 复杂度高，当前只做中心/离线对照接口 | 需要 N-scan pruning、分簇、假设管理策略和中心节点算力假设 | P2 |
| Stone Soup | 未实际集成。仅有可用性检测和占位转换函数 | `research_modules/d2_data_association/d2_data_association/compat.py` | 避免把 Stone Soup 对象暴露到系统总线；当前环境保持轻依赖 | 需要独立 research env 安装 Stone Soup、定义 adapter 映射和对照报告 | P2 |
| FilterPy | 未实际集成。仅可用性检测和 `to_filterpy_state()` 占位 | `compat.py` | 当前 Tracker 已有线性 Kalman fallback；FilterPy 作为未来 EKF/UKF/IMM 原型 | 需要确定是否引入依赖、状态/量测模型、测试场景 | P2/P3 |
| `id_switch_count` | 已实现。`MetricsRecorder` 根据 truth-to-track 代表 ID 变化计数 | `metrics.py`；`tests/test_tracker_metrics.py`；`simulation.py` | 不适用 | 集成场景必须提供 `truth_id`，否则无法评估真实 IDSW | P0 已满足 |
| `track_continuity` / `identity_continuity` | 已实现。`track_continuity` 是 `identity_continuity` 别名，同时有 `coverage_continuity` | `metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 需要 D6 统一消费并区分覆盖连续性与身份连续性 | P0 已满足 |
| `duplicate_assignment_count` | 已实现。统计同帧重复 detection/track 和同 truth 多 track | `metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 后续可扩展为滑窗 duplicate-track risk 自动评分 | P0 已满足 |
| 跨视角弱证据风险字段 | 已实现最小数据合同。`AssociationRiskSummary` 支持 `source_node_id`、`link_type`、`d5_disagreement_count`、`duplicate_track_risk`、`association_ambiguity`、`covariance_overlap_rate` | `models.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 尚缺 D5/二级节点真实消息 adapter 和滑窗风险生成器 | P1 |
| `AssociationRiskSummary` 自动派生 | 部分实现。可从 `AssociationResult.risk_summary` 或 `metadata` 进入 D2 summary；集成层可把 D2 的 `id_switch_count`、`track_continuity` 等转换为 D4 的主动降级 `AssociationRiskSummary`，但 D2 还未自动从 cost matrix/滑窗计算全部风险 | `metrics.py`；`integrated_simulation/adapters.py`；`d4_distributed_fallback/active_degradation.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前先固定数据合同，避免过早绑定 D4/D5 消息格式 | 需要 D4 主动降级阈值、滑窗长度、cost margin 和协方差交叠算法 | P1 |
| AirSim dry-run 适配 | 已实现。接收 synthetic AirSim-style dict/object，不 import `airsim`，支持 `detections/tracks/objects`、`x/y`、`x_val/y_val`、2x2/3x3 协方差 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py` | 不适用 | 尚未接真实 AirSim runtime；当前按要求只做 dry-run/replay | P0 已满足 |
| D1 `GlobalTrack` 到 D2 `Detection` | 部分实现。D2 dry-run adapter 支持 `tracks` 字段和 3D covariance 投影到 2D；集成层已有 `CanonicalTrack`/`d2_detection_kwargs()` 和 `d1_tracks_to_d2_detections()`，并有合同测试；D2 模块内仍没有强类型 D1 adapter API | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py`；`integration_contracts.py`；`integration_tests/test_cross_module_contracts.py`；`integrated_simulation/adapters.py` | D1->D2 合同目前由 integration/main 层维护，D2 先保持松耦合 | 需要决定 adapter 归属、冻结字段名/坐标系/时间戳规范，并把 replay 主线持续纳入回归 | P1 |
| 原生 3D NED D2 跟踪 | 未实现。D2 状态固定 `[x,y,vx,vy]` | `models.py`；`tracker.py`；`dry_run_adapter.py` | Phase-1 D2 聚焦二维关联和 ID 保持 | 需要 3D 量测模型、D1/D5 投影接口、三维协方差门控 | P2 |
| 5v5 crossing/dense 专用测试 | 部分实现。D2 自模块已有 formation 5 目标、crossing 2 目标、occlusion、missed、false_alarms；系统级已有 `crossing_5v5` 场景和 AirSim CV 5v5 crossing actor specs；但 D2 benchmark/test 仍没有 deterministic 5v5 crossing/dense fixture 来同场比较 GNN、JPDA、MHT 的 IDSW/continuity/runtime | `simulation.py`；`tests/test_simulation.py`；`integrated_simulation/scenario.py`；`airsim_runtime/models.py`；`docs/benchmark_results.json` | 早期 D2 基线场景覆盖通用风险，系统级 5v5 不等于 D2 关联器对照实验；`run_batch.py` 默认也未包含 `crossing_5v5` | 需要 D2-owned deterministic 5v5 crossing/dense fixture，或把系统级 `crossing_5v5` 接成可重复的 D2 GNN/JPDA/MHT 对照入口 | P1 |
| JPDA/MHT 自动升级触发 | 未实现。文档定义触发条件，代码需调用方手动选择 associator | `simulation.py` 的 `make_associator()`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 自动切换会影响可比性和测试稳定，先保留显式对照 | 需要 D4/D6 认可风险阈值、切换迟滞和实验矩阵 | P2 |
| Stone Soup 对照测试 | 未实现 | `compat.py`；`tests/test_simulation.py` 只检查 optional dependency status | 外部依赖不保证存在；当前 CI/本地测试保持轻量 | 需要可选 extras、隔离测试标记和固定对照数据 | P2 |
| FilterPy 对照测试 | 未实现 | `compat.py`；`tests/test_simulation.py` | 同上；当前并未实现 FilterPy 状态映射 | 需要 FilterPy dependency、EKF/UKF/IMM adapter | P2/P3 |
| D6 指标输出接口 | 部分实现。`MetricsRecorder.summary()` 输出 IDSW、continuity、duplicate、RMSE、runtime、risk 字段；`integrated_simulation` 已把 D2 tracks/summary 写入系统级记录；D2 本身未直接生成 D6 `EpisodeMetrics` | `metrics.py`；`tests/test_tracker_metrics.py`；`integrated_simulation/runner.py`；`integrated_simulation/adapters.py` | D6 统一日志格式独立维护，D2 避免直接耦合 D6 类 | 需要 main/D6 继续固化日志 schema、区分 D2 内部 IDSW 与 D6 episode IDSW 口径 | P1 |

## 3. 关键缺口说明

### 3.1 已满足的 P0 主线

- GNN/Hungarian 作为默认关联器已可运行，且使用成熟 SciPy 求解器。
- 马氏门控、候选计数、歧义分数、拒配原因已输出。
- Tracker 具备基本航迹生命周期管理和 ID 评估闭环。
- `id_switch_count`、`track_continuity`、`duplicate_assignment_count` 已进入 summary。
- AirSim dry-run 适配满足“无 AirSim SDK import、无真实 simulator call”的约束。
- 集成层已能把 D1/D2/D3/D4/D5/D6 串入 `nominal_5v5` replay，D2 P0 主线已进入系统级离线闭环。

### 3.2 当前最重要的 P1 差距

- 缺少 D2-owned 的 5v5 crossing/dense 确定性压力测试。系统级 `crossing_5v5` 和 AirSim CV 5v5 actor 配置已存在，但还没有 GNN/JPDA/MHT 同场对照和固定验收阈值。
- `AssociationRiskSummary` 已有数据合同，但尚未从 cost margin、candidate overlap、协方差交叠和 D5 disagreement 自动生成完整滑窗风险。
- D1 `GlobalTrack` 到 D2 `Detection` 的合同已有集成层 helper 和测试，但 adapter 归属、主线 schema、replay 回归和 D2 模块内强类型 API 仍未最终固化。
- D6/集成层已消费部分 D2 summary 和 track records，但仍需统一 D2 内部 IDSW 与 D6 episode IDSW 的统计口径，并把 association logs/risk summary 纳入稳定 schema。

### 3.3 暂不实现的合理项

- 完整 Stone Soup/FilterPy 适配暂不应进入核心运行路径。主流方案建议它们作为研究对照和原型工具，而不是直接污染统一数据总线。
- 完整 MHT 不适合资源节点，当前有界 MHT placeholder 满足离线接口验证；生产级 MHT 需要中心算力、剪枝策略和更完整的场景基准。
- EKF/UKF/IMM 需要更复杂的三维/机动量测模型。当前二维线性 Kalman 对 phase-1 数据关联验证足够。

## 4. 下一步建议

1. **P1：新增 5v5 crossing/dense fixture**  
   使用 deterministic truth trajectories，输出 GNN/JPDA/MHT 的 IDSW、continuity、runtime 对比，作为 AirSim ComputerVision 前置验收。

2. **P1：实现 D2 风险滑窗生成器**  
   从 `AssociationResult.cost_matrix`、`candidate_counts_by_track`、`candidate_counts_by_detection`、`MetricsRecorder` 差分和 `TrackTransition` 自动计算 `AssociationRiskSummary`。

3. **P1：固定 D1->D2 adapter contract**  
   明确 D1 `GlobalTrack` 的字段名、坐标系、协方差投影规则、`measurement_timestamp/arrival_timestamp` 传递方式。

4. **P2：引入三维状态或三维到二维的统一策略**  
   如果 D5 终端投影、D7 中段 PN 都需要三维状态，D2 需要升级为 3D `[px,py,pz,vx,vy,vz]` 或明确只输出二维关联 ID、三维状态由 D1 提供。

5. **P2/P3：外部库对照环境**  
   单独建立 Stone Soup/FilterPy optional benchmark，不纳入默认测试路径。用于验证 JPDA/MHT、EKF/UKF/IMM 在高密交叉和强机动场景下是否优于当前轻量实现。

## 5. 审计结论

D2 已经具备端到端集成的最小可用能力：输入检测、维护全局航迹 ID、执行 GNN/Hungarian、记录 IDSW/连续性、输出风险摘要和 dry-run bus message。它还具备 JPDA/MHT 的轻量可插拔对照。主要未完成项不是基础功能，而是高保真对照、三维机动模型、自动风险滑窗和 5v5 AirSim 专用压力测试。建议优先补 P1 项，暂缓将 Stone Soup/FilterPy 或完整 MHT 引入默认运行路径。
