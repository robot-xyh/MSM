# D2 多目标跟踪与数据关联实现差距审计

**审计对象**：`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d2_data_association/` 代码与测试，并抽查 `research_modules/integration_contracts.py`、`research_modules/integrated_simulation/`、`research_modules/airsim_runtime/` 中的 D2 调用边界。

**审计边界**：仅评估 D2 离线科研仿真与数据关联模块，不涉及真实飞控、硬件、火控、毁伤或自动处置逻辑。

**结论摘要**：D2 已实现可运行的 GNN/Hungarian 主线、二维常速度 Kalman 航迹管理、简化 JPDA、有界 MHT 接口、IDSW/连续性指标、弱证据风险摘要和 AirSim dry-run 适配。本轮 P1 已补 `crossing_dense_5v5` 确定性场景、GNN/JPDA/MHT 同场对照、`AssociationRiskSummaryWindowGenerator` 滑窗风险生成器，以及 D1 `GlobalTrack` 到 D2 `Detection` 的模块内 adapter 基线。D2 运行链路按每帧输入的 `active_tracks` 和 `detections` 长度构造关联，不假设固定 2v2/5v5；5v5 仅是可重复 baseline fixture。未实现项仍集中在完整 EKF/UKF/IMM、Stone Soup/FilterPy 实际适配、生产级 JPDA/MHT 和原生 3D GlobalTrack 跟踪。

## 1. 总体判断

D2 当前实现符合“先用 GNN/Hungarian 做工程主线，密集交叉再升级 JPDA/MHT”的主流共识，也与 `MAIN_IMPLEMENTATION_GAP_AUDIT.md` 的 P0/P1 口径一致：P0 主线是轻量可运行的 Hungarian/ID 指标/dry-run，P1 已补 5v5 dense/crossing 对照、风险滑窗和 D1 adapter 基线。工程策略是正确的：运行路径只依赖 NumPy/SciPy，Stone Soup 与 FilterPy 暂作为外部验证和未来适配目标。D2 不复制 main runtime 的 `--drone-count` 为内部常量，而是消费调用方传入的观测/航迹集合。主要差距集中在更高阶运动模型、完整第三方框架适配、三维航迹原生支持和更贴近真实 AirSim ComputerVision 回放的压力测试。

## 2. 明确状态分区

### 2.1 已实现

- **GNN/Hungarian 主线**：`GNNHungarianAssociator` 调用 SciPy `linear_sum_assignment`，每帧由实际 `tracks` 与 `detections` 构造代价矩阵，输出匹配、未匹配、拒配原因、代价矩阵、歧义分数和候选计数。
- **马氏门控与二维 Kalman 航迹管理**：`build_gated_cost_matrix()`、`Tracker` 和 `[x,y,vx,vy]` 常速度预测/更新已可运行，生命周期覆盖 `tentative/confirmed/engageable/lost/dropped`。
- **核心指标**：`MetricsRecorder.summary()` 已输出 `id_switch_count`、`track_continuity`/`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime。
- **crossing/dense fixture**：`crossing_dense_5v5` 已作为确定性 baseline fixture 加入，可同场比较 GNN、JPDA、MHT；该 fixture 不改变关联器按输入集合长度运行的边界。
- **D1 adapter 基线**：`detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、`covariance`、`global_track_id` 和 metadata。
- **AirSim dry-run/replay 输入基线**：`detections_from_airsim_frame()` 与 `run_airsim_dry_run_association()` 支持 synthetic AirSim-style `detections/tracks/objects`，接受 `x/y`、`x_val/y_val`、2x2/3x3 covariance，且明确不 import 或调用 `airsim`。
- **弱证据风险摘要**：`AssociationRiskSummary` 和 `AssociationRiskSummaryWindowGenerator` 已把 cost margin、candidate overlap、ID switch delta、continuity、D5 disagreement、source node/link type 汇总为 D4/D6 可消费的风险证据。

### 2.2 部分实现

- **JPDA**：`JPDAAssociator` 已能枚举小规模联合假设、计算边缘概率并输出接口兼容结果；但它不是完整 JPDA 滤波器，没有概率混合状态更新、完整协方差融合或生产级参数标定。
- **MHT**：`MHTAssociator` 已有 bounded branch、短历史和 pruning 参数，能作为 MHT-compatible research placeholder；但不是完整 MHT，没有 N-scan pruning、分簇、长期假设树管理和中心算力策略。
- **EKF 表述**：D2 当前只有二维线性 Kalman fallback。主审计中“EKF/滤波主线 P0 可用”在 D2 侧应理解为轻量 Kalman 航迹预测可用，不代表 D2 已实现非线性 EKF。
- **3D NED 支持**：D2 可消费 D1 6D NED 输入并投影到水平 N-E 平面，但 D2 原生状态仍固定为 `[x,y,vx,vy]`，不是 `[px,py,pz,vx,vy,vz]` 三维跟踪器。
- **D6/集成输出**：D2 summary 与 association logs 已具备 IDSW、continuity、duplicate、risk 字段，且有 D2/D6 IDSW 口径测试；但 episode 级 JSONL schema 和真实 main runtime 写入仍由 main/D6 固化。

### 2.3 未实现

- **UKF 与 IMM-EKF/UKF**：代码中无 sigma-point UKF、IMMEstimator、CV/CA/CT 模型集或模型转移概率。
- **完整非线性 EKF**：代码中无雷达球坐标、相机投影或三维非线性量测雅可比。
- **Stone Soup/FilterPy 实际适配**：`compat.py` 只做 optional availability 检测和显式 placeholder，未返回 Stone Soup/FilterPy 对象，也未建立可运行 benchmark。
- **JPDA/MHT 自动升级触发**：当前由调用方或仿真 CLI 显式选择 associator，未在 `Tracker` 内按风险阈值自动切换。
- **原生 3D NED D2 跟踪**：`Detection` 固定二维 position/covariance，`GlobalTrack` 固定四维状态和 4x4 covariance。
- **真实 AirSim ComputerVision replay 压测**：现有路径是 synthetic/dry-run/replay-style 数据适配，不接真实 AirSim runtime、不消费真实 `simGetDetections` episode JSONL、不验证 5v5 CV 图像/metadata 回放。

### 2.4 未实现原因

- **轻依赖优先**：当前默认测试要求只依赖 NumPy/SciPy/pytest，避免 Stone Soup、FilterPy、AirSim SDK、ROS 或 GPU 依赖进入基础回归。
- **接口先于高阶算法**：D2 先固化 `DataAssociator`、`AssociationResult`、ID 指标、风险摘要和 D1/D6 合同，避免在总线未稳定时引入重型框架对象。
- **场景证据不足**：UKF/IMM、完整 JPDA/MHT 和原生 3D 跟踪需要强机动、遮挡、密集交叉、真实 replay 等场景证明收益，否则会增加参数和复杂度但不一定降低 IDSW。
- **职责边界**：真实 AirSim 启停、episode JSONL、CV detector metadata 和跨模块 runtime bus 由 main/runtime 负责；D2 只维护模块内 adapter 和离线关联能力。

### 2.5 缺少条件

- **数据条件**：多 seed 5v5 AirSim CV replay、真实或稳定 synthetic `simGetDetections` schema、带 `truth_id` 的离线评估标签、漏检/虚警/遮挡 sweep。
- **模型条件**：三维 NED 状态合同、三维 covariance 门控、雷达/相机非线性量测模型、CV/CA/CT 机动模型和 IMM 转移概率。
- **依赖条件**：隔离 research env 的 Stone Soup/FilterPy optional extras、adapter 映射、测试标记和容差门限。
- **系统条件**：main/D6 固化 episode JSONL 字段，D4 认可风险阈值和自动切换迟滞，D5/D1 真实反馈进入 replay 而不是仅靠 fixture。

### 2.6 下一步优先级

- **P0 维护**：保持 GNN/Hungarian、门控、指标、D1 adapter、dry-run adapter 和 5v5 fixture 测试稳定；严禁把 2v2/5v5 写成算法常量。
- **P1**：让 main/D6 用真实 5v5 AirSim CV replay 写入 D2 association logs 和 risk summary，校准 `AssociationRiskSummaryWindowGenerator` 阈值。
- **P2**：决定 D2 是否升级原生 3D 状态；若升级，先实现 3D NED state/covariance/gating，再考虑 EKF/UKF/IMM。
- **P2/P3**：建立 Stone Soup/FilterPy optional benchmark，先用于离线对照 JPDA/MHT/EKF/UKF/IMM，不进入默认运行路径。
- **P3**：在多 seed replay 证明收益后，再做 JPDA/MHT 自动升级策略和切换迟滞。

## 3. 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| GNN/Hungarian 默认关联主线 | 已实现。`GNNHungarianAssociator` 使用 SciPy `linear_sum_assignment`，支持马氏门控、代价矩阵、拒配原因、候选数元数据，并按实际 `len(tracks)`/`len(detections)` 运行 | `research_modules/d2_data_association/d2_data_association/associators.py`；`tests/test_gating_and_associators.py` | 不适用 | 继续保留 5v5 高密交叉基准作为 fixture，不把规模写成运行假设 | P0 已满足，持续维护 |
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
| AirSim dry-run 适配 | 已实现。接收 synthetic AirSim-style dict/object，不 import `airsim`，支持 `detections/tracks/objects`、`x/y`、`x_val/y_val`、2x2/3x3 协方差，并在 bus message 中按活动航迹集合导出全部 `global_track_id` | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py` | 不适用 | 尚未接真实 AirSim runtime；当前按要求只做 dry-run/replay | P0 已满足 |
| D1 `GlobalTrack` 到 D2 `Detection` | 已实现 P1 基线。D2 dry-run adapter 支持 `tracks` 字段和 3D covariance 投影到 2D；模块内提供 D1 `GlobalTrack` -> D2 `Detection` 转换入口，集成层仍保留 `CanonicalTrack`/`d2_detection_kwargs()` 合同测试 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py`；`integration_contracts.py`；`integration_tests/test_cross_module_contracts.py`；`integrated_simulation/adapters.py` | 不适用；当前转换仍保持 duck typing，避免 D2 强依赖 D1 包 | 后续需冻结 JSONL/replay schema、坐标轴投影规则和 timestamp 透传字段 | P1 已完成基线 |
| 原生 3D NED D2 跟踪 | 未实现。D2 状态固定 `[x,y,vx,vy]` | `models.py`；`tracker.py`；`dry_run_adapter.py` | Phase-1 D2 聚焦二维关联和 ID 保持 | 需要 3D 量测模型、D1/D5 投影接口、三维协方差门控 | P2 |
| 5v5 crossing/dense 专用测试 | 已实现 P1 基线。D2 自模块新增 deterministic `crossing_dense_5v5` fixture，并可同场比较 GNN、JPDA、MHT 的 IDSW、continuity 和 runtime；该场景是 baseline fixture，不是关联器固定数量假设 | `simulation.py`；`tests/test_simulation.py`；`docs/benchmark_results.json` | 不适用；当前是二维质点观测压力测试，不是 AirSim 图像回放 | 后续应补真实 AirSim CV replay 输入和更多遮挡/漏检/虚警 sweep | P1 已完成基线 |
| JPDA/MHT 自动升级触发 | 未实现。文档定义触发条件，代码需调用方手动选择 associator | `simulation.py` 的 `make_associator()`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 自动切换会影响可比性和测试稳定，先保留显式对照 | 需要 D4/D6 认可风险阈值、切换迟滞和实验矩阵 | P2 |
| Stone Soup 对照测试 | 未实现 | `compat.py`；`tests/test_simulation.py` 只检查 optional dependency status | 外部依赖不保证存在；当前 CI/本地测试保持轻量 | 需要可选 extras、隔离测试标记和固定对照数据 | P2 |
| FilterPy 对照测试 | 未实现 | `compat.py`；`tests/test_simulation.py` | 同上；当前并未实现 FilterPy 状态映射 | 需要 FilterPy dependency、EKF/UKF/IMM adapter | P2/P3 |
| D6 指标输出接口 | 部分实现。`MetricsRecorder.summary()` 输出 IDSW、continuity、duplicate、RMSE、runtime、risk 字段；`integrated_simulation` 已把 D2 tracks/summary 写入系统级记录；D2 本身未直接生成 D6 `EpisodeMetrics` | `metrics.py`；`tests/test_tracker_metrics.py`；`integrated_simulation/runner.py`；`integrated_simulation/adapters.py` | D6 统一日志格式独立维护，D2 避免直接耦合 D6 类 | 需要 main/D6 继续固化日志 schema、区分 D2 内部 IDSW 与 D6 episode IDSW 口径 | P1 |

## 4. 关键缺口说明

### 4.1 已满足的 P0 主线

- GNN/Hungarian 作为默认关联器已可运行，且使用成熟 SciPy 求解器。
- 马氏门控、候选计数、歧义分数、拒配原因已输出。
- Tracker 具备基本航迹生命周期管理和 ID 评估闭环。
- 关联器、Tracker 和 metrics 均按输入集合长度运行；2v2/5v5 只作为可重复测试场景。
- `id_switch_count`、`track_continuity`、`duplicate_assignment_count` 已进入 summary。
- AirSim dry-run/replay-style 适配满足“无 AirSim SDK import、无真实 simulator call”的约束。
- 集成层已能把 D1/D2/D3/D4/D5/D6 串入 `nominal_5v5` replay，D2 P0 主线已进入系统级离线闭环。

### 4.2 本轮已补齐的 P1 接口

- D2-owned `crossing_dense_5v5` 确定性压力测试已经加入，用于 GNN/JPDA/MHT 同场对照。
- `AssociationRiskSummaryWindowGenerator` 已能从 cost margin、candidate overlap、ID switch delta、continuity 和 D5 disagreement 自动生成滑窗风险。
- D1 `GlobalTrack` 到 D2 `Detection` 的模块内 adapter 基线已经可用，仍保持松耦合字段读取；当前是 NED 6D 到 D2 2D 水平面的投影，不是 D2 原生 3D tracker。
- D6/集成层仍需统一 D2 内部 IDSW 与 episode IDSW 的统计口径，并把 association logs/risk summary 纳入稳定 JSONL schema。

### 4.3 暂不实现的合理项

- 完整 Stone Soup/FilterPy 适配暂不应进入核心运行路径。主流方案建议它们作为研究对照和原型工具，而不是直接污染统一数据总线。
- 完整 MHT 不适合资源节点，当前有界 MHT placeholder 满足离线接口验证；生产级 MHT 需要中心算力、剪枝策略和更完整的场景基准。
- EKF/UKF/IMM 需要更复杂的三维/机动量测模型。当前二维线性 Kalman 对 phase-1 数据关联验证足够。

## 5. 下一步建议

1. **P1 已完成：5v5 crossing/dense fixture 与风险滑窗生成器**
   当前可用 `crossing_dense_5v5` 对比 GNN/JPDA/MHT，并用 `AssociationRiskSummaryWindowGenerator` 输出滑窗风险摘要。

2. **P1 已完成基线：D1->D2 adapter contract**
   D2 已能消费 D1-like `GlobalTrack`，下一步不是重写 adapter，而是冻结 replay schema、坐标系和 timestamp 字段。

3. **P2：引入三维状态或三维到二维的统一策略**
   如果 D5 终端投影、D7 中段 PN 都需要三维状态，D2 需要升级为 3D `[px,py,pz,vx,vy,vz]` 或明确只输出二维关联 ID、三维状态由 D1 提供。

4. **P2/P3：外部库对照环境**
   单独建立 Stone Soup/FilterPy optional benchmark，不纳入默认测试路径。用于验证 JPDA/MHT、EKF/UKF/IMM 在高密交叉和强机动场景下是否优于当前轻量实现。

## 6. 审计结论

D2 已经具备端到端集成的最小可用能力：输入检测、维护全局航迹 ID、执行 GNN/Hungarian、记录 IDSW/连续性、输出风险摘要和 dry-run bus message。它还具备 JPDA/MHT 的轻量可插拔对照、5v5 dense/crossing 压测、D1 NED 投影 adapter 和滑窗风险摘要。当前 D2 责任范围内没有固定 2v2/5v5 数量依赖；`global_track_id` 输出随活动航迹集合变化，可供 D3/D5 按集合消费。主要未完成项不是基础功能，而是高保真第三方对照、三维机动模型、原生 3D NED 跟踪和真实 AirSim CV replay 压力测试。建议暂缓将 Stone Soup/FilterPy 或完整 MHT 引入默认运行路径。
