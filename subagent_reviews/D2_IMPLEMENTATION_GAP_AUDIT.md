# D2 多目标跟踪与数据关联实现差距审计

**审计对象**：`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d2_data_association/` 代码与测试，并抽查 `research_modules/integration_contracts.py`、`research_modules/integrated_simulation/`、`research_modules/airsim_runtime/` 中的 D2 调用边界。

**审计边界**：仅评估 D2 离线科研仿真与数据关联模块，不涉及真实飞控、硬件、火控、毁伤或自动处置逻辑。

**结论摘要**：D2 已实现可运行的 GNN/Hungarian 主线、二维常速度 Kalman 航迹管理、简化 JPDA、有界 MHT 接口、IDSW/连续性指标、弱证据风险摘要和 AirSim dry-run 适配。本轮 P1 已补 `crossing_dense_5v5` 确定性场景、GNN/JPDA/MHT 同场对照、`AssociationRiskSummaryWindowGenerator` 滑窗风险生成器，以及 D1 `GlobalTrack` 到 D2 `Detection` 的模块内 adapter 基线。未实现项仍集中在完整 EKF/UKF/IMM、Stone Soup/FilterPy 实际适配、生产级 JPDA/MHT 和原生 3D GlobalTrack 跟踪。

## 1. 总体判断

D2 当前实现符合“先用 GNN/Hungarian 做工程主线，密集交叉再升级 JPDA/MHT”的主流共识，也与 `MAIN_IMPLEMENTATION_GAP_AUDIT.md` 的 P0/P1 口径一致：P0 主线是轻量可运行的 Hungarian/ID 指标/dry-run，P1 已补 5v5 dense/crossing 对照、风险滑窗和 D1 adapter 基线。工程策略是正确的：运行路径只依赖 NumPy/SciPy，Stone Soup 与 FilterPy 暂作为外部验证和未来适配目标。主要差距集中在更高阶运动模型、完整第三方框架适配、三维航迹原生支持和更贴近真实 AirSim ComputerVision 回放的压力测试。

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
| 跨视角弱证据风险字段 | 已实现最小数据合同。`AssociationRiskSummary` 支持 `source_node_id`、`link_type`、`d5_disagreement_count`、`duplicate_track_risk`、`association_ambiguity`、`covariance_overlap_rate` | `models.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 尚缺真实 D5/二级节点消息流和跨节点回放样本 | P1 已完成基线 |
| `AssociationRiskSummary` 自动派生 | 已实现 P1 基线。`AssociationRiskSummaryWindowGenerator` 可从 `AssociationResult.cost_matrix`、candidate count metadata、cost margin、ID switch delta、track continuity 和 D5 disagreement 生成滑窗风险摘要，并进入 `MetricsRecorder.summary()` | `metrics.py`；`tests/test_tracker_metrics.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 不适用；当前仍是轻量窗口规则，不是学习式风险模型 | 后续需用 5v5 AirSim replay 校准窗口长度、阈值和 D4 主动降级触发边界 | P1 已完成基线 |
| AirSim dry-run 适配 | 已实现。接收 synthetic AirSim-style dict/object，不 import `airsim`，支持 `detections/tracks/objects`、`x/y`、`x_val/y_val`、2x2/3x3 协方差 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py` | 不适用 | 尚未接真实 AirSim runtime；当前按要求只做 dry-run/replay | P0 已满足 |
| D1 `GlobalTrack` 到 D2 `Detection` | 已实现 P1 基线。D2 dry-run adapter 支持 `tracks` 字段和 3D covariance 投影到 2D；模块内提供 D1 `GlobalTrack` -> D2 `Detection` 转换入口，集成层仍保留 `CanonicalTrack`/`d2_detection_kwargs()` 合同测试 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py`；`integration_contracts.py`；`integration_tests/test_cross_module_contracts.py`；`integrated_simulation/adapters.py` | 不适用；当前转换仍保持 duck typing，避免 D2 强依赖 D1 包 | 后续需冻结 JSONL/replay schema、坐标轴投影规则和 timestamp 透传字段 | P1 已完成基线 |
| 原生 3D NED D2 跟踪 | 未实现。D2 状态固定 `[x,y,vx,vy]` | `models.py`；`tracker.py`；`dry_run_adapter.py` | Phase-1 D2 聚焦二维关联和 ID 保持 | 需要 3D 量测模型、D1/D5 投影接口、三维协方差门控 | P2 |
| 5v5 crossing/dense 专用测试 | 已实现 P1 基线。D2 自模块新增 deterministic `crossing_dense_5v5` fixture，并可同场比较 GNN、JPDA、MHT 的 IDSW、continuity 和 runtime | `simulation.py`；`tests/test_simulation.py`；`docs/benchmark_results.json` | 不适用；当前是二维质点观测压力测试，不是 AirSim 图像回放 | 后续应补真实 AirSim CV replay 输入和更多遮挡/漏检/虚警 sweep | P1 已完成基线 |
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

### 3.2 本轮已补齐的 P1 接口

- D2-owned `crossing_dense_5v5` 确定性压力测试已经加入，用于 GNN/JPDA/MHT 同场对照。
- `AssociationRiskSummaryWindowGenerator` 已能从 cost margin、candidate overlap、ID switch delta、continuity 和 D5 disagreement 自动生成滑窗风险。
- D1 `GlobalTrack` 到 D2 `Detection` 的模块内 adapter 基线已经可用，仍保持松耦合字段读取。
- D6/集成层仍需统一 D2 内部 IDSW 与 episode IDSW 的统计口径，并把 association logs/risk summary 纳入稳定 JSONL schema。

### 3.3 暂不实现的合理项

- 完整 Stone Soup/FilterPy 适配暂不应进入核心运行路径。主流方案建议它们作为研究对照和原型工具，而不是直接污染统一数据总线。
- 完整 MHT 不适合资源节点，当前有界 MHT placeholder 满足离线接口验证；生产级 MHT 需要中心算力、剪枝策略和更完整的场景基准。
- EKF/UKF/IMM 需要更复杂的三维/机动量测模型。当前二维线性 Kalman 对 phase-1 数据关联验证足够。

## 4. 下一步建议

1. **P1 已完成：5v5 crossing/dense fixture 与风险滑窗生成器**
   当前可用 `crossing_dense_5v5` 对比 GNN/JPDA/MHT，并用 `AssociationRiskSummaryWindowGenerator` 输出滑窗风险摘要。

2. **P1 已完成基线：D1->D2 adapter contract**
   D2 已能消费 D1-like `GlobalTrack`，下一步不是重写 adapter，而是冻结 replay schema、坐标系和 timestamp 字段。

3. **P2：引入三维状态或三维到二维的统一策略**
   如果 D5 终端投影、D7 中段 PN 都需要三维状态，D2 需要升级为 3D `[px,py,pz,vx,vy,vz]` 或明确只输出二维关联 ID、三维状态由 D1 提供。

4. **P2/P3：外部库对照环境**
   单独建立 Stone Soup/FilterPy optional benchmark，不纳入默认测试路径。用于验证 JPDA/MHT、EKF/UKF/IMM 在高密交叉和强机动场景下是否优于当前轻量实现。

## 5. 审计结论

D2 已经具备端到端集成的最小可用能力：输入检测、维护全局航迹 ID、执行 GNN/Hungarian、记录 IDSW/连续性、输出风险摘要和 dry-run bus message。它还具备 JPDA/MHT 的轻量可插拔对照、5v5 dense/crossing 压测和滑窗风险摘要。主要未完成项不是基础功能，而是高保真第三方对照、三维机动模型和真实 AirSim CV replay 压力测试。建议暂缓将 Stone Soup/FilterPy 或完整 MHT 引入默认运行路径。
