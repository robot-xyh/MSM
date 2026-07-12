# D2 多目标跟踪与数据关联实现差距审计

**审计对象**：`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d2_data_association/` 代码与测试，并抽查 `research_modules/integration_contracts.py`、`research_modules/integrated_simulation/`、`research_modules/airsim_runtime/` 中的 D2 调用边界。

**审计边界**：仅评估 D2 离线科研仿真与数据关联模块，不涉及真实飞控、硬件、火控、毁伤或自动处置逻辑。

**本轮 EVAL 同步来源**：`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`、`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`、`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`、`EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md`。

**结论摘要**：D2 P0 无运行级 blocker，P1 合同层已闭合；系统级物理拦截与更长真实 replay 的长期参数标定仍开放。当前 `67 passed` 覆盖默认 GNN/Hungarian、D1 governed replay、frozen offline truth、N-target/10-seed synthetic dense calibration 与 P2 optional 分支。P2 v2 已在同一 truth-free replay 下对照 GNN 与模块内 JPDA/MHT，并在运行后输出离线 IDSW/continuity；Stone Soup 1.9.1/FilterPy 1.4.5 仍只做对象 adapter smoke。完整外部 JPDA/MHT、EKF/UKF/IMM 和外部框架端到端身份指标仍未实现，默认在线 GNN/Hungarian 路径没有替换。

## 1. 总体判断

D2 当前实现符合“先用 GNN/Hungarian 做工程主线，密集交叉再用 JPDA/MHT/BP、SORT/ByteTrack-style fallback 做研究对照或增强”的主流共识。P1 replay governance 的 D1 governed input、online/offline truth 隔离、版本化 M-of-N、false-track、NIS/NEES 接口和 10-seed runner 已回归。后续 backlog 是真实 dense/crossing 性能标定、完整自适应门控、JPDA 同预算对照、高阶运动模型和原生 3D，不影响 P1 合同闭合结论。

### 1.1 本轮 P0/P1 复核结论

- **P0 复核**：无运行级 P0 blocker。GNN/Hungarian、马氏门控、`DataAssociator`、`Track` 状态机、`id_switch_count`、`track_continuity`、`duplicate_assignment_count`、D1 adapter、AirSim dry-run adapter 和按输入集合长度运行的要求已在文档/GAP 中准确覆盖。EVAL 已确认的 D2 P0 项已闭合并作为回归保持：每条 track 的 `track_quality`/`association_risk` 航迹质量评分、参与 GNN/Hungarian 代价的运动一致性约束，以及 dense/crossing 下可随 track quality/density 轻量调整的 quality-aware gate baseline。当前 D2 无未完成 P0 backlog；验收口径是持续输出上述字段、保持 D3/D5/D6 可消费性、不替换默认关联器、不改写 D1/D3/D5 合同字段。
- **P1 合同复核**：D1 governed adapter、offline truth evaluator、逐帧 schema/profile、匿名在线 detection ID、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed runner、M-of-N/false-track 和 NIS/NEES availability 已闭合。在线 Detection/Track/log 不含 actor 身份或 truth；无 truth replay 仍可计算 NIS。
- **历史基线**：2026-07-10 的 5v5/2v2 批次和 2026-07-11 早期的 seeds 7/17/27 当时不足以关闭 D2 P1，且 T001 双 primary 为 0。本条仅保留实施前/过渡证据边界，不代表当前状态。
- **当前 10-seed 证据**：M=5、N=2 ComputerVision 的 T001 双 primary 共识/计划授权为 8/10；D2 `id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。
- **commit/fail-closed 边界**：二级和完全分布式 commit 正例通过，缺 ACK 时 `aborted`/`hold_for_review` 且导引许可为 0。这只证明下游能沿用 D2 中心 `global_track_id` 完成 commit/fail-closed，不表示 D2 owner failover 或分布式临时 ID 合并已实现。
- **物理边界**：SimpleFlight 15 s 仅诊断，30 个 active pair 无命中；物理拦截和长期真实 replay 标定未闭合，不影响 D2 身份/truth-isolation 合同及 synthetic dense calibration runner 的 P1 闭合结论。
- **在线/离线指标边界**：没有 offline truth label 时，truth-based `id_switch_count`、`track_continuity`/`identity_continuity` 和 NEES 必须标记 unavailable；在线可继续计算 NIS、ambiguity、candidate overlap、cost margin、duplicate 和 track-quality risk。IDSW/continuity 结论必须由隔离的 offline evaluator 评分。
- **P1 闭合与后续研究边界**：D2 已形成覆盖 dense crossing、连续漏检/遮挡和虚警的动态 N、10-seed replay，并冻结独立 truth JSONL；同 seed 复现、truth 隔离和 availability 已有测试。专用真实 AirSim dense/crossing 与更深 gate/risk/NIS/NEES 标定是后续性能研究，不是 P1 合同缺口。
- **M 对 N P1 状态**：D2 已实现跨节点 local-track namespace、公共时刻传播、track-to-track Mahalanobis/Hungarian、公共信息谱系防重、canonical multi-source binding/history 和 exact/unknown/duplicate 决策基础。多个节点观测同一目标不会增加目标基数，也不会被误记为合法协同资源的 duplicate assignment。数值 CI/相关融合仍由 D1 owner 实现；高歧义多帧关联、owner failover 和融合一致性标定尚未闭合。专项证据见 `D2_M_TO_N_TRACK_FUSION_REVIEW.md`。
- **D4 P1 仲裁语义复核**：2026-07-07 main runtime bus / D4 P1 修复后，D4 已区分 D2 软风险和硬风险。`association_ambiguity`、cost margin risk、candidate overlap 和短时 D5 disagreement 是观察/二级 cue 证据；`id_switch_count` 增量、`duplicate_assignment_count`/`duplicate_track_risk` 和可用的 `track_continuity` 低于阈值才是 D4 主动仲裁的硬风险证据。2026-07-10 D2 P1 修复后，无 offline truth label 时 `truth_metrics_available=false`、`continuity_available=false`，兼容数值 `0.0` 不再触发 `duplicate_track_risk`、`continuity_collapse` 或 hard risk；旧 replay 未携带 availability 字段时同样保守按不可用处理。
- **P2 边界复核**：P2 v2 在同一 frozen replay digest 下比较默认 GNN、模块内 JPDA/MHT research adapter 和 Stone Soup/FilterPy object adapter，统一输出 IDSW、continuity、latency 与 `unavailable_reason`。GNN/JPDA/MHT 的身份指标来自运行后的隔离 evaluator；外部对象 adapter 的身份指标明确 unavailable。模块内轻量 JPDA/MHT 仍是研究近似；完整外部 JPDA/MHT/UKF/IMM、optional 端到端 tracking 和原生 3D 仍未实现。benchmark 没有替换默认在线路径或 requirements。

## 2. 明确状态分区

### 2.1 已实现

- **GNN/Hungarian 主线**：`GNNHungarianAssociator` 调用 SciPy `linear_sum_assignment`，每帧由实际 `tracks` 与 `detections` 构造代价矩阵，输出匹配、未匹配、拒配原因、代价矩阵、歧义分数和候选计数。
- **可插拔关联器接口**：`DataAssociator` 已作为统一插件边界，`Tracker` 消费 `AssociationResult`，因此 GNN、JPDA、MHT 可共享状态机、metrics 和风险摘要。
- **马氏门控与二维 Kalman 航迹管理**：`build_gated_cost_matrix()`、`Tracker` 和 `[x,y,vx,vy]` 常速度预测/更新已可运行，生命周期覆盖 `tentative/confirmed/engageable/lost/dropped`。
- **P0-B track quality / association risk**：`GlobalTrack.to_dict()`、`AssociationResult.metadata`、association logs、risk summary metadata 和 `MetricsRecorder.summary()` 已输出 `track_quality_by_track`、`association_risk_by_track`、mean/min/max 质量风险摘要和每条 track 的 `quality_metadata`。
- **P0-B 运动一致性约束**：`GNNHungarianAssociator` 在保留马氏门控和 `linear_sum_assignment` 的基础上，把速度方向、短时历史和加速度异常形成的 `motion_consistency_cost_matrix` 加入代价，并输出 per-pair/per-track diagnostics。
- **P0-B quality-aware gate baseline**：`build_gated_cost_matrix()` 已按 track quality、局部目标密度、位置协方差和上一帧 association risk 生成 `gate_thresholds_by_track`，在低质量/高协方差时保守放宽、在高密度/高歧义时收紧；完整自适应门控仍保留为 P1。
- **核心指标**：`MetricsRecorder.summary()` 已输出 `id_switch_count`、`track_continuity`/`identity_continuity`、`coverage_continuity`、`truth_metrics_available`、`continuity_available`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime；无 truth 时 continuity 数值只保留报告兼容性。
- **拒配日志闭环**：`AssociationLogEntry.rejected_pairs` 默认空列表，`to_dict()` 和 `MetricsRecorder` 日志构造完整保留 `mahalanobis_gate`/`assignment_above_gate`；replay gate summary 分原因计数，旧 JSON 缺字段按空处理。
- **covariance 输入与统计治理**：Detection/GlobalTrack 及门控边界拒绝非有限、明显非对称、明显非 PSD covariance；replay governance 已输出 NIS 和 offline-only NEES 的 95% 卡方覆盖。剩余项是用真实多 seed 数据按距离、传感器和场景校准，而非接口缺失。
- **crossing/dense fixture**：`crossing_dense_5v5` 已作为确定性 baseline fixture 加入，可同场比较 GNN、JPDA、MHT；该 fixture 不改变关联器按输入集合长度运行的边界。
- **D1 adapter 基线**：`detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、`covariance`、`global_track_id` 和 metadata。
- **AirSim dry-run/replay 输入基线**：`detections_from_airsim_frame()` 与 `run_airsim_dry_run_association()` 支持 synthetic AirSim-style `detections/tracks/objects`，接受 `x/y`、`x_val/y_val`、2x2/3x3 covariance，且明确不 import 或调用 `airsim`。
- **AirSim-style replay/report helper**：`load_airsim_replay_frames()`、`run_airsim_replay_association()`、`write_replay_association_report()` 和 `write_association_logs_jsonl()` 已能读取离线 JSON/JSONL replay，保留 main/D6-style row 中的 seed/scenario/frame/offline truth label，并输出 association logs、summary、当前 `global_track_ids`、`replay_metadata`、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary 和风险摘要。
- **阈值敏感性与多 seed helper**：`run_threshold_sensitivity()` 可按 gate threshold 与 risk threshold profile 输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`/`association_risk_threshold_version`、seed/episode/scenario/frame metadata、gate/motion/quality diagnostics 和 soft/hard risk summary；`summarize_multi_seed_risk_calibration()` 可按 gate/risk profile/version 汇总 IDSW、continuity、duplicate、soft/hard risk 分布、dense/crossing sensitivity summary 并给出推荐阈值摘要。
- **冻结 truth 与 calibration runner**：`OfflineTruthLabel` JSONL 合同固定 episode/frame/timestamp/truth ID/position/可选注释；读写器校验 schema、重复键和数值。通用 N-target fixture 和至少 10-seed runner 分离在线帧/离线评分，输出每 seed 和聚合 IDSW、continuity、NIS/NEES availability、gate/risk version、runtime 与确定性签名，unavailable 不转换为零。
- **弱证据风险摘要**：`AssociationRiskSummary`、`AssociationRiskSummaryWindowGenerator`、`RiskThresholds` 和 `classify_risk_summary()` 已把 cost margin、candidate overlap、ID switch delta、duplicate delta、continuity、D5 disagreement、source node/link type 汇总为 D4/D6 可消费的风险证据。
- **M 对 N canonical registry 基础**：`SourceTrackSummary` 固化 source/local/epoch namespace、measurement/arrival timestamp、6D NED state/covariance、quality、lineage/correlation status 和 canonical hints；`CrossNodeTrackAssociator`/`CrossNodeTrackRegistry` 完成公共时刻传播、covariance-aware gate、按 source Hungarian、one canonical-to-many source binding/history 与 duplicate/stale governance。source hints 不具备 canonical 身份权威。
- **M 对 N 指标与 truth 隔离**：在线 `CrossNodeRegistryMetrics` 输出 operational cross-node rebind、duplicate payload rejection 和 transport/queue/fusion latency，且不接受 truth；独立 `OfflineCrossNodeMetricsEvaluator` 通过 source-key truth mapping 计算 cross-node IDSW、`canonical_duplicate_count` 和 association precision/recall。

### 2.2 部分实现

- **JPDA**：`JPDAAssociator` 已能枚举小规模联合假设、计算边缘概率并输出接口兼容结果；但它不是完整 JPDA 滤波器，没有概率混合状态更新、完整协方差融合或生产级参数标定。
- **MHT**：`MHTAssociator` 已有 bounded branch、短历史和 pruning 参数，能作为 MHT-compatible research placeholder；但不是完整 MHT，没有 N-scan pruning、分簇、长期假设树管理和中心算力策略。
- **EKF 表述**：D2 当前只有二维线性 Kalman fallback。主审计中“EKF/滤波主线 P0 可用”在 D2 侧应理解为轻量 Kalman 航迹预测可用，不代表 D2 已实现非线性 EKF。
- **3D NED 支持**：D2 可消费 D1 6D NED 输入并投影到水平 N-E 平面，但 D2 原生状态仍固定为 `[x,y,vx,vy]`，不是 `[px,py,pz,vx,vy,vz]` 三维跟踪器。
- **D6/集成输出**：D2 summary 与 association logs 已具备 IDSW、continuity、duplicate、risk/profile version、gate pass/reject、motion/quality 和 dense/crossing sensitivity 字段，且有 D2/D6 `id_switch_count` 口径测试。当前 P1 CV 批次已由 main/runtime/D6 生产和评分。
- **D6 bundle 对齐**：D6 标准 AirSim calibration bundle 已由 main runtime 自动调用；D2 只保证 report/log/profile 字段可被分组读取，不在模块内重复生成 D6 report。

### 2.3 未实现

- **UKF 与 IMM-EKF/UKF**：代码中无 sigma-point UKF、IMMEstimator、CV/CA/CT 模型集或模型转移概率。
- **完整非线性 EKF**：代码中无雷达球坐标、相机投影或三维非线性量测雅可比。
- **完整外部框架 tracker**：`compat.py` 已返回 Stone Soup Detection 与 FilterPy KalmanFilter，`p2_benchmark.py` 已建立可运行 smoke comparison；但没有 Stone Soup Track/JPDA/MHT 或 FilterPy 端到端关联器。
- **JPDA/MHT 自动升级触发**：当前由调用方或仿真 CLI 显式选择 associator，未在 `Tracker` 内按风险阈值自动切换。
- **原生 3D NED D2 跟踪**：`Detection` 固定二维 position/covariance，`GlobalTrack` 固定四维状态和 4x4 covariance。
- **AirSim runtime 职责边界**：D2 消费 main/runtime 导出的 governed JSON/JSONL replay 与隔离 truth，不连接 AirSim SDK，不采集 `simGetDetections`/CV 图像 metadata，也不编排 episode。
- **后续研究增强**：JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控、N/M 初始化参数网格和 NEES/NIS 深度标定仍未完成；这些不是 P1 合同 blocker。

### 2.4 未实现原因

- **轻依赖优先**：当前默认测试要求只依赖 NumPy/SciPy/pytest，避免 Stone Soup、FilterPy、AirSim SDK、ROS 或 GPU 依赖进入基础回归。
- **接口先于高阶算法**：D2 先固化 `DataAssociator`、`AssociationResult`、ID 指标、风险摘要和 D1/D6 合同，避免在总线未稳定时引入重型框架对象。
- **场景证据不足**：UKF/IMM、完整 JPDA/MHT 和原生 3D 跟踪需要强机动、遮挡、密集交叉、真实 replay 等场景证明收益，否则会增加参数和复杂度但不一定降低 IDSW。
- **职责边界**：真实 AirSim 启停、episode JSONL、CV detector metadata 和跨模块 runtime bus 由 main/runtime 负责；D2 只维护模块内 adapter 和离线关联能力。

### 2.5 缺少条件

- **数据条件**：若继续后续性能研究，需要专用多 seed 真实 AirSim dense/crossing replay、隔离 truth position、漏检/虚警/遮挡 sweep，以及 false track、init latency 和软/硬风险误报漏报统计。
- **模型条件**：JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控策略、N/M 初始化标定和 NEES/NIS 统计一致性判定；三维 NED 状态合同、三维 covariance 门控、雷达/相机非线性量测模型、CV/CA/CT 机动模型和 IMM 转移概率。
- **依赖条件**：隔离 venv 已具备 Stone Soup 1.9.1/FilterPy 1.4.5 并完成 adapter smoke；完整算法仍需 framework tracker 配置、版本化参数、测试标记和同预算验收门限。
- **系统条件**：main/runtime/D6 已完成当前 P1 CV 批次及离线评分。后续自动算法切换仍需阈值配置来源、迟滞和专用 replay 证据。

### 2.6 下一步优先级

- **P0 维护**：保持 GNN/Hungarian、门控、指标、D1 adapter、dry-run adapter、5v5 fixture、航迹质量评分、运动一致性约束和 quality-aware gate baseline 测试稳定；严禁把 2v2/5v5 写成算法常量。
- **P0 工程化硬化**：已新增每条 track 的 `track_quality`/`association_risk`，已把速度方向、加速度异常和短时历史一致性作为 GNN/Hungarian 代价项与 score 输出，并已实现 quality-aware gate baseline；继续维护这些字段的 D3/D5/D6 可消费性。当前无 D2 运行级 P0 blocker。
- **P1 闭合维护**：持续回归 replay/report、D1 governed adapter、冻结 truth JSONL、动态 N fixture、至少 10-seed runner、availability、threshold/risk split、covariance 治理和 IDSW/continuity 评分边界。完整 adaptive gate、JPDA 对照和真实 dense/NIS/NEES 标定作为后续性能研究。
- **P2**：决定 D2 是否升级原生 3D 状态；若升级，先实现 3D NED state/covariance/gating，再考虑 EKF/UKF/IMM。
- **P2 benchmark 已收敛**：dependency version/reason probe、对象 adapter、frozen replay digest、GNN/JPDA/MHT 同 Tracker 对照、五行 JSON、统一 `unavailable_reason`、truth-free 在线输入和隔离 venv smoke 已覆盖；默认 requirements/在线路径不变。
- **D1 governed schema 支持**：这是已闭合的 P1 输入合同。D2 loader 识别 `d1.governed_replay_manifest.v1`/`d1.sensor_observation.v1`，匿名 observation identity，按 frame/time 聚合 radar 球坐标并传播 covariance 到水平 N/E；声学 bearing 与 EO pixel 按原因跳过。
- **P2/P3 剩余**：完整 Stone Soup JPDA/MHT、FilterPy EKF/UKF/IMM、端到端身份指标与真实 replay 对照。
- **P3**：在多 seed replay 证明收益后，再做 JPDA/MHT 自动升级策略和切换迟滞。

实施顺序为：维护已闭合的 P1 replay/truth/D1-governed 合同和 synthetic runner；如需要，再扩展真实 dense/crossing 性能标定。P2 继续隔离运行，adapter 不得写入默认总线对象或默认依赖。

### 2.7 `global_track_id` 下游消费合同

- **D3**：D3 以 D2 输出的 `global_track_id`、状态、协方差和 `lifecycle_state` 构造资源-目标分配代价。D2 应提供当前活动航迹集合；D3 应优先消费 `confirmed/engageable`，对 `tentative`、长期 `lost` 或高风险航迹提高代价或延迟分配。D2 不生成 `AssignmentPlan`，也不修改 D3 的 plan version。
- **D4**：D4 消费 D2 `AssociationRiskSummary`、`id_switch_count` delta、continuity、duplicate risk、D5 disagreement、`source_node_id` 和 `link_type` 作为主动降级证据。D2 只发布关联风险，不决定 `continue_center`、`request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。
- **D4 软/硬风险分层**：D2 的 ambiguity、low margin 和候选重叠是软风险，支持观察、提高 D3 迟滞、请求二级 cue 或离线 JPDA/MHT 对照；ID switch、duplicate 和 continuity 崩塌是硬风险，可作为 D4 主动重规划/降级仲裁证据。D2 不直接输出降级动作。
- **D5**：D5 使用 `global_track_id` 做终端视觉投影和候选配准，可回传 `TerminalAssociation`、`IdentityClaim`、候选 ID 与不一致事件作为弱证据。D5 不得改写、重绑或本地覆盖 D2 的规范 `global_track_id`。
- **D6**：D6 消费 association logs、TrackTransition、summary 和 confusion matrix。D2/D6 必须显式保留 `id_switch_count`：同一 truth 的代表 `global_track_id` 变化就是 ID Switch，不能用 RMSE、覆盖率或命中数替代。

## 3. 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| GNN/Hungarian 默认关联主线 | 已实现。`GNNHungarianAssociator` 使用 SciPy `linear_sum_assignment`，支持马氏门控、运动一致性代价、quality-aware gate diagnostics、代价矩阵、拒配原因、候选数元数据，并按实际 `len(tracks)`/`len(detections)` 运行 | `research_modules/d2_data_association/d2_data_association/associators.py`；`research_modules/d2_data_association/d2_data_association/gating.py`；`tests/test_gating_and_associators.py` | 不适用 | 继续保留 5v5 高密交叉基准作为 fixture，不把规模写成运行假设；完整自适应门控仍需多 seed 标定 | P0 已满足，持续维护 |
| 可插拔 `DataAssociator` 接口 | 已实现。GNN、JPDA、MHT 均返回统一 `AssociationResult`，可复用 `Tracker`、metrics、risk summary 和 dry-run 输出 | `associators.py`；`tracker.py`；`tests/test_gating_and_associators.py` | 不适用 | 后续外部库 adapter 必须继续返回 `AssociationResult`，不得把外部对象泄漏到系统总线 | P0 已满足 |
| 马氏距离门控 | 已实现。`mahalanobis_squared()`、`build_gated_cost_matrix()` 输出候选数和拒配对 | `research_modules/d2_data_association/d2_data_association/gating.py`；`tests/test_gating_and_associators.py` | 不适用 | 可增加协方差交叠率自动计算 | P0 已满足 |
| 二维常速度 Kalman 航迹管理 | 已实现。`Tracker` 使用 `[x,y,vx,vy]`、线性预测和 Joseph 更新，含 tentative/confirmed/engageable/lost/dropped 状态机 | `research_modules/d2_data_association/d2_data_association/tracker.py`；`tests/test_tracker_metrics.py` | 不适用 | 若接 D1 3D NED，需要三维状态或投影适配策略固定 | P0 已满足 |
| EKF | D2 未实现完整非线性 EKF。当前是二维线性 Kalman fallback；主审计中“EKF/滤波主线 P0 可用”对 D2 的含义是轻量 Kalman 跟踪可用，不是 D2 EKF 已实现 | `tracker.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md`；`MAIN_IMPLEMENTATION_GAP_AUDIT.md` | Phase-1 使用二维质点/线性观测，暂不需要雅可比和非线性量测 | 需要三维 NED、雷达球坐标/相机投影量测、非线性观测模型 | P2 |
| UKF | 未实现 | `compat.py` 仅实现线性 CV FilterPy object adapter；没有 sigma points | 当前运行路径避免引入高阶模型；未定义 UKF 三维状态/量测接口 | 需要机动/非线性场景和模型合同 | P2 |
| IMM-EKF/UKF | 未实现 | `D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md` 仅列为目标；代码中无 IMMEstimator | 当前机动压力测试不足，D2 重点先解决关联接口与指标 | 需要 CV/CA/CT 模型集、模型转移概率、机动目标场景和评估门限 | P2 |
| JPDA | 部分实现。`JPDAAssociator` 可枚举小规模联合假设、计算边缘概率并输出接口兼容结果；不是完整 JPDA 滤波器 | `associators.py`；`tests/test_gating_and_associators.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 为保持轻量可运行，只实现小规模离线对照；没有概率混合状态更新和完整航迹协方差融合 | 需要真实 5v5 replay、多 seed risk calibration、Stone Soup/完整 JPDA 对照和参数标定 | P1 已有可执行对照；完整 JPDA benchmark 为 P2 |
| MHT | 部分实现。`MHTAssociator` 保留有界分支和短历史，是 MHT-compatible research placeholder；非完整 MHT | `associators.py`；`tests/test_gating_and_associators.py` | 完整 MHT 复杂度高，当前只做中心/离线对照接口 | 需要 N-scan pruning、分簇、假设管理策略、中心节点算力假设和多 seed replay 证据 | P2 optional benchmark |
| Stone Soup | 部分实现。Detection/StateVector adapter、版本探测、frozen replay conversion smoke 已实现；1.9.1 实测成功 | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | 刻意不把 Stone Soup 对象暴露到总线；尚未配置 Track/predictor/updater | 完整 JPDA/MHT、状态更新、假设管理和同预算 IDSW/continuity | P2 adapter 已完成；tracker 未完成 |
| FilterPy | 部分实现。CV KalmanFilter 可由 D2 track/detection 初始化并执行 predict/update；1.4.5 实测成功 | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | adapter 不替换默认 Tracker，也不维护跨帧身份 | EKF/UKF/IMM、端到端关联生命周期和同输入身份指标 | P2 CV adapter 已完成；高阶/端到端未完成 |
| `id_switch_count` | 已实现。`MetricsRecorder` 根据 truth-to-track 代表 ID 变化计数，且测试验证 D2 与 D6 episode 计数口径一致 | `metrics.py`；`tests/test_tracker_metrics.py`；`simulation.py` | 不适用 | 集成场景必须提供离线 `truth_id`，否则只能输出风险摘要，不能评估真实 IDSW | P0 已满足，D2/D6 强制保留 |
| `track_continuity` / `identity_continuity` | 已实现。`track_continuity` 是 `identity_continuity` 别名，同时有 `coverage_continuity`；`truth_metrics_available`/`continuity_available` 区分无 truth 的 unavailable 与真实数值 0 | `metrics.py`；`tests/test_tracker_metrics.py`；`tests/test_replay.py` | 不适用 | D6 消费时必须先检查 availability，不能把兼容 `0.0` 当作连续性崩塌 | P0 指标已满足；P1 unavailable 语义已闭合 |
| `duplicate_assignment_count` | 已实现。统计同帧重复 detection/track 和同 truth 多 track | `metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 后续可扩展为滑窗 duplicate-track risk 自动评分 | P0 已满足 |
| 跨视角弱证据风险字段 | 已实现最小数据合同。`AssociationRiskSummary` 支持 `source_node_id`、`link_type`、`d5_disagreement_count`、`duplicate_track_risk`、`association_ambiguity`、`covariance_overlap_rate` | `models.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 尚缺真实 D5/二级节点消息流和跨节点回放样本 | P1 已完成基线 |
| `AssociationRiskSummary` 自动派生 | 已实现 P1 基线。`AssociationRiskSummaryWindowGenerator` 可从 `AssociationResult.cost_matrix`、candidate count metadata、cost margin、ID switch delta、duplicate delta、track continuity 和 D5 disagreement 生成滑窗风险摘要，并进入 `MetricsRecorder.summary()` | `metrics.py`；`tests/test_tracker_metrics.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 不适用；当前仍是轻量窗口规则，不是学习式风险模型 | 后续需用真实 5v5 AirSim replay 校准窗口长度、阈值和 D4 主动降级触发边界 | P1 已完成基线 |
| D4 软/硬风险消费合同 | 已实现代码和文档。D2 ambiguity/cost margin/candidate overlap 作为软风险；IDSW、duplicate 和可用 continuity 低于阈值作为硬风险。`continuity_available=false` 时 classifier 显式忽略 continuity，D2 不直接发起 `request_center_replan` | `metrics.py`；`tests/test_replay.py`；`README.md`；`PLAN.md`；`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md` | D4 的主动降级动作由 D4/main runtime bus 负责，D2 只能维护证据字段 | 需要真实 5v5 AirSim replay 校准软风险误触发率和硬风险漏报率 | P1 unavailable 语义已闭合，阈值校准保留 |
| AirSim dry-run 适配 | 已实现。接收 synthetic AirSim-style dict/object，不 import `airsim`，支持 `detections/tracks/objects`、`x/y`、`x_val/y_val`、2x2/3x3 协方差，并在 bus message 中按活动航迹集合导出全部 `global_track_id` | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py` | 不适用 | 尚未接真实 AirSim runtime；当前按要求只做 dry-run/replay | P0 已满足 |
| AirSim-like replay、冻结 truth JSONL 与 multi-seed summary | 已实现 D2 P1 合同。`d2-offline-truth-label/v1` 固定 episode/frame/timestamp/truth ID/position 和可选匹配注释；在线帧与 track/log 不携带 truth。通用 N-target fixture 和至少 10-seed runner 输出每 seed/聚合 IDSW、continuity、NIS/NEES availability、gate/risk version、runtime 和确定性签名 | `offline_truth.py`；`calibration.py`；`replay.py`；`tests/test_calibration.py`；`tests/test_replay.py` | D2 不连接 AirSim SDK | 可选扩展专用真实 dense/crossing 性能标定 | P1 合同/runner 已闭合 |
| D1 governed frozen replay loader | 已实现。manifest/records 转为 timestamp-grouped radar N/E detections，使用球坐标 Jacobian 传播 covariance；源 observation ID/lineage 不进入在线帧，声学/EO 有 skip diagnostics，旧 AirSim frames 保持兼容 | `d1_governed_adapter.py`；`replay.py`；`tests/test_p2_benchmark.py` | D2 当前关联平面是水平 N/E，不能直接混合 bearing-only 或 pixel measurements | 非 radar 模态需先由 D1 融合成 GlobalTrack，不能在 D2 loader 中伪转换 | P1 governed input 合同已闭合 |
| D1 `GlobalTrack` 到 D2 `Detection` | 已实现 P1 基线。D2 dry-run adapter 支持 `tracks` 字段和 3D covariance 投影到 2D；模块内提供 D1 `GlobalTrack` -> D2 `Detection` 转换入口，集成层仍保留 `CanonicalTrack`/`d2_detection_kwargs()` 合同测试 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py`；`integration_contracts.py`；`integration_tests/test_cross_module_contracts.py`；`integrated_simulation/adapters.py` | 不适用；当前转换仍保持 duck typing，避免 D2 强依赖 D1 包 | 后续需冻结真实 replay schema、坐标轴投影规则、timestamp 透传字段和阈值版本记录 | P1 已完成基线 |
| 原生 3D NED D2 跟踪 | 未实现。D2 状态固定 `[x,y,vx,vy]` | `models.py`；`tracker.py`；`dry_run_adapter.py` | Phase-1 D2 聚焦二维关联和 ID 保持 | 需要 3D 量测模型、D1/D5 投影接口、三维协方差门控 | P2 |
| 5v5 crossing/dense 专用测试 | 已实现 P1 基线。D2 自模块新增 deterministic `crossing_dense_5v5` fixture，并可同场比较 GNN、JPDA、MHT 的 IDSW、continuity 和 runtime；该场景是 baseline fixture，不是关联器固定数量假设 | `simulation.py`；`tests/test_simulation.py`；`docs/benchmark_results.json` | 不适用；当前是二维质点观测压力测试，不是 AirSim 图像回放 | 后续应补真实 AirSim CV replay 输入和更多遮挡/漏检/虚警 sweep | P1 已完成基线 |
| JPDA/MHT 自动升级触发 | 未实现。文档定义触发条件，代码需调用方手动选择 associator | `simulation.py` 的 `make_associator()`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 自动切换会影响可比性和测试稳定，先保留显式对照 | 需要 D4/D6 认可风险阈值、切换迟滞和实验矩阵 | P2 |
| Stone Soup 对照测试 | adapter smoke 已实现。缺依赖明确 unavailable；available 分支转换 frozen replay Detection 并记录 latency，IDSW/continuity unavailable | `p2_benchmark.py`；`tests/test_p2_benchmark.py` | 未实现完整 tracker，禁止宣称 JPDA/MHT 成功 | 需要 Stone Soup tracker pipeline 才能产生身份指标 | P2 基础完成 |
| FilterPy 对照测试 | CV object smoke 已实现。缺依赖明确 unavailable；available 分支执行 predict/update 并记录 latency，IDSW/continuity unavailable | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | 无跨帧关联和生命周期 | 需要端到端 tracker 才能比较身份指标 | P2 基础完成 |
| D6 指标输出接口 | 已实现 D2-owned 输出。`MetricsRecorder.summary()` 输出 IDSW、continuity、duplicate、RMSE、runtime、risk、track quality 和 association risk 字段；`integrated_simulation` 已把 D2 tracks/summary 写入系统级记录；main runtime/D6 负责 episode 汇总 | `metrics.py`；`tests/test_tracker_metrics.py`；`integrated_simulation/runner.py`；`integrated_simulation/adapters.py` | D6 统一日志格式独立维护，D2 避免直接耦合 D6 类 | 可选扩展专用 dense/crossing 分组标定 | P1 D2/D6 指标合同已闭合 |
| `track_quality` / `association_risk` 航迹质量评分 | 已实现 EVAL P0-B。每条 `GlobalTrack` 输出 `track_quality`、`association_risk`、`quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 和 `MetricsRecorder.summary()` 输出 track-level 质量/风险字典与 mean/min/max 摘要 | `models.py`；`tracker.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用；当前是可解释规则评分，不是学习式质量模型 | 后续 D3/D5/D6 只消费该字段，不改写 D1/D3/D5 合同字段；多 seed replay 可继续标定阈值 | P0 已闭合，保持回归 |
| 运动一致性约束 | 已实现 EVAL P0-B。GNN/Hungarian 代价在马氏距离和可选 feature cost 外加入速度方向、短时历史和加速度异常形成的 motion consistency cost，并输出 pair/track diagnostics | `associators.py`；`gating.py`；`tracker.py`；`tests/test_gating_and_associators.py` | 不适用；仍保留原马氏门控和 Hungarian 求解器 | 后续用 dense/crossing replay 持续验证 motion weight 是否需要按场景校准 | P0 已闭合，保持回归 |
| quality-aware gate baseline | 已实现 EVAL P0-B。`build_gated_cost_matrix()` 按 track quality、局部目标密度、位置协方差和上一帧 association risk 生成 per-track gate threshold，低质量/高协方差保守放宽，高密度/高歧义收紧；不是完整 adaptive gating framework | `gating.py`；`associators.py`；`metrics.py`；`tests/test_gating_and_associators.py`；`tests/test_replay.py` | 轻量、可解释 baseline，不替换默认关联器 | 完整自适应门控作为后续研究 | P0 已闭合，保持回归 |
| 完整自适应门控策略 | 未实现。当前只有 quality-aware gate baseline | `gating.py`；`replay.py`；`metrics.py` | 阈值敏感性 helper 已完成，但不是在线自适应策略 | 需要专用 replay、隔离 truth、版本治理和多 seed calibration | 后续研究增强 |
| JPDA/MHT/BP 选型对照 | 模块内轻量研究近似已进入 frozen replay benchmark。`JPDAAssociator` 小规模枚举、`MHTAssociator` 有界分支均复用 Tracker/offline evaluator，并与 GNN 同输入输出 IDSW、continuity 和 latency；BP 未实现 | `associators.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py`；`simulation.py` | 当前 JPDA/MHT 未做概率混合状态更新、生产级假设管理、同预算标定或 coalescence 指标；BP 不进入当前依赖 | 需要真实 dense/crossing 多 seed 与同预算验收，且保留 GNN/Hungarian 默认主线 | P2 轻量对照已闭合；完整算法未实现 |
| SORT/ByteTrack-style fallback | 未实现 EVAL P1。当前 GNN/Hungarian 已具备 SORT-like 的运动预测 + Hungarian 核心，但没有独立 SORT fallback 模式，也没有 ByteTrack-style 低置信检测二阶段关联或视觉 MOT handoff adapter | `associators.py`；`tracker.py`；`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`；`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md` | 当前 P0 主线已足够运行；SORT/ByteTrack 应作为轻量 fallback 或视觉 MOT 场景对照，不能替代稳定 `global_track_id` 合同 | 需要定义 fallback 触发条件、输入置信度字段、IDSW/continuity 对照、异常回退路径和 D5 视觉 MOT replay 样本 | P1 对照/增强，不是 P0 |
| N/M 初始化优化 | D2-owned 接口已实现。`InitializationGovernanceProfile` 默认 2-of-3，并可由 replay/sensitivity 入口注入其他版本；输出 init/confirmation latency、success rate、false-track count/rate、miss/false-alarm 和逐帧 measurement/truth count | `replay_governance.py`；`replay.py`；`tests/test_replay_governance.py` | 在线 Tracker 状态机保持不变，truth 只用于离线标定 | 需要 main/D6 在真实多 seed replay 中标定 M/N 和生命周期参数 | P1 接口闭合；真实标定保留 |
| 协方差一致性检查 | 输入治理和统计接口已实现：NIS 用在线 innovation，NEES 仅用独立 offline truth state，输出二维/四维 95% 卡方区间及覆盖率 | `gating.py`；`replay_governance.py`；`tests/test_replay_governance.py` | online path 不接触 truth，缺 truth 时 NEES 为 unavailable | 需要真实 replay 和 D6 做分传感器/距离/场景多 seed 标定 | P1 接口闭合；真实标定保留 |
| M 对 N 跨平台 track-to-track association 与保守融合决策 | D2 注册基础已实现。`SourceTrackSummary`、公共时刻 CV 传播、完整 6D covariance-aware Mahalanobis gate、按 source Hungarian、lineage/payload/stale 防重和 exact/unknown/duplicate 决策均有测试；unknown 只输出 CI request，不在 D2 复制数值 CI | `cross_node_models.py`；`cross_node_registry.py`；`tests/test_cross_node_registry.py` | 数值 CI/已知相关融合属于 D1；D2 当前只完成关联、身份和融合策略请求 | 需要 D1 消费 fusion directives 并返回融合 posterior；需要高歧义多帧 replay 和 NEES/ANEES | P1 D2 基础闭合；跨模块数值融合/标定保留 |
| canonical global identity 多源注册 | 已实现中心 registry 基础。维护 `global_track_id -> [(source_node_id, local_track_id, epoch)]`、binding history、连续 ID 分配和 authoritative rebind；source candidate/current ID 只作非权威 hint | `cross_node_models.py`；`cross_node_registry.py`；`cross_node_metrics.py`；`tests/test_cross_node_registry.py` | 中心单 owner 已闭合；二级 owner 切换和完全分布式临时 ID 合并不在本轮基础范围 | 需要 D4 owner/epoch failover 合同和跨 owner replay | P1 中心注册闭合；failover 保留 |

## 4. 关键缺口说明

### 4.1 已满足的 P0 主线

- GNN/Hungarian 作为默认关联器已可运行，且使用成熟 SciPy 求解器。
- 马氏门控、候选计数、歧义分数、拒配原因已输出。
- Tracker 具备基本航迹生命周期管理和 ID 评估闭环。
- 关联器、Tracker 和 metrics 均按输入集合长度运行；2v2/5v5 只作为可重复测试场景。
- `id_switch_count`、`track_continuity`、`duplicate_assignment_count` 已进入 summary，且 D2/D6 对 `id_switch_count` 的计数规则已有合同测试。
- AirSim dry-run/replay-style 适配满足“无 AirSim SDK import、无真实 simulator call”的约束。
- D2-owned JSON/JSONL replay reader/report、association logs JSONL、threshold profile version、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、replay metadata、main/D6 row metadata、offline truth label、N-v-N target_count fallback、threshold sensitivity helper 和 multi-seed summary helper 已补齐，并通过 5 目标 AirSim-like replay、main/D6-style row、无 truth label N-v-N 与多 seed summary 测试覆盖。
- 集成层已能把 D1/D2/D3/D4/D5/D6 串入 `nominal_5v5` replay，D2 P0 主线已进入系统级离线闭环。

### 4.2 P1 已闭合接口与后续研究项

- D2-owned `crossing_dense_5v5` 确定性压力测试已经加入，用于 GNN/JPDA/MHT 同场对照。
- `AssociationRiskSummaryWindowGenerator` 已能从 cost margin、candidate overlap、ID switch delta、duplicate delta、continuity 和 D5 disagreement 自动生成滑窗风险。
- `RiskThresholds`/`classify_risk_summary()` 已把 D2 风险证据分为软风险和硬风险。
- `run_airsim_replay_association()`、`run_threshold_sensitivity()` 与 `summarize_multi_seed_risk_calibration()` 已能输出 5 目标 AirSim-like replay 的 association logs、metrics、risk summary、replay metadata、risk profile version、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing 阈值敏感性行和多 seed 推荐阈值摘要。
- D1 `GlobalTrack` 到 D2 `Detection` 的模块内 adapter 基线已经可用，仍保持松耦合字段读取；当前是 NED 6D 到 D2 2D 水平面的投影，不是 D2 原生 3D tracker。
- 当前 P1 CV 批次已沿隔离 truth 边界完成评分；如扩展专用真实 dense/crossing 数据集，main/runtime/D6 应继续沿用 `d2-offline-truth-label/v1` 与已冻结 profile。
- EVAL 同步后的航迹质量评分、运动一致性约束和 quality-aware gate baseline 已作为 P0 工程化硬化闭合并保持回归；这些项增强 GNN/Hungarian 主线，不替换默认关联器，也不得改写 D1/D3/D5 合同字段。
- JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控、N/M 参数优化和 NEES/NIS 深度标定保留为后续研究增强，不再写成 P1 合同未闭合。
- M 对 N D2-owned 注册基础已闭合：1/2/3/N source、异步公共时刻、交叉、duplicate payload/lineage、source local ID 冲突、canonical continuity、exact/unknown/duplicate 决策和 online truth isolation 均有专项回归。剩余是 D1 数值融合、D6 NEES/ANEES、多 seed 高歧义 replay 和 owner failover。

### 4.3 多目标交叉、密集编队与 ID Switch 剩余风险

- **多目标交叉**：GNN/Hungarian 是单帧硬判决。交叉窗口内最优/次优代价 margin 过小时，硬关联可能任意打破平局，并在后续 Kalman update 中吸收错误观测。JPDA/MHT 可用于对照和风险暴露，但当前 JPDA 没有概率混合状态更新，MHT 没有完整 N-scan 和长期假设管理，不能宣称已消除交叉 ID Switch。
- **密集编队**：多条航迹共享门内候选时，`candidate_counts_by_track`、`candidate_counts_by_detection` 和协方差重叠会升高。当前 feature cost 是简单向量差异；若外观、类别或声纹特征不稳定，仍可能发生 ID 交换或重复航迹解释。
- **ID Switch 可观测性**：`id_switch_count` 依赖离线 `truth_id`。真实在线路径没有 truth label 时，D2 只能发布风险摘要和弱证据，不能把在线风险摘要当成真实 IDSW ground truth。D6 应在带 truth 的仿真或 replay 中计算最终 IDSW。
- **规模风险**：D2 不写死 2v2/5v5，但 GNN 仍有 Hungarian 复杂度，JPDA/MHT 仍会随候选数增长。更大 N 需要分簇、预算、截断或只做离线对照。

### 4.4 暂不实现的合理项

- Stone Soup/FilterPy object adapter 已隔离实现，但不得进入核心运行路径；完整 tracker 仍只能作为未来研究对照。
- 完整 MHT 不适合资源节点，当前有界 MHT placeholder 满足离线接口验证；生产级 MHT 需要中心算力、剪枝策略和更完整的场景基准。
- EKF/UKF/IMM 需要更复杂的三维/机动量测模型。当前二维线性 Kalman 对 phase-1 数据关联验证足够。

## 5. 下一步建议

1. **维护 P1 governed replay/truth 合同**：继续回归 D1 adapter、在线匿名化、`d2-offline-truth-label/v1`、profile version 和 evaluator-only 评分。若新增专用真实 dense/crossing 数据，沿用同一合同。

2. **N/M 初始化与 false-track 标定**：使用已实现的版本化 M-of-N/false-track 输出，对建轨确认、漏检容忍和删除参数做真实多 seed 网格实验，并覆盖非 2/5 数量输入。

3. **NIS/NEES 真实标定**：复用现有 NIS/NEES 和卡方覆盖接口，补按传感器、距离和场景的多 seed 分组偏差及 D6 趋势。

4. **完整 adaptive gate / JPDA 对照**：固定 replay、seed、输入和预算，对比固定门限、quality-aware baseline、完整 adaptive gate 及 GNN/JPDA，报告 IDSW、continuity、false track、漏关联、延迟和 JPDA 截断率；默认主线仍保持 GNN/Hungarian。

**M 对 N 后续：数值融合与高歧义治理**：D2 已闭合“公共时刻预测 -> track-to-track association -> 相关性/公共信息判定 -> canonical binding -> fusion request”基础。后续由 D1 接续 exact/CI 数值融合，并用多 seed crossing/dense replay 验证跨节点 JPDA/MHT、D2 owner failover 和融合一致性。D4 commit 正例通过不等于这些 D2 能力已实现。

**M 对 N 评估状态**：已实现 `canonical_duplicate_count`、cross-node IDSW、track-to-track association precision/recall、重复消息拒绝数和 fusion latency；online registry 不读取 simulator truth。fusion NEES/ANEES 和通信字节仍需 D1/D6 离线评分与 replay schema。

5. **P2：引入三维状态或三维到二维的统一策略**
   如果 D5 终端投影、D7 中段 PN 都需要三维状态，D2 需要升级为 3D `[px,py,pz,vx,vy,vz]` 或明确只输出二维关联 ID、三维状态由 D1 提供。

6. **P2/P3：外部库增强**
   对象 adapter/frozen replay smoke 已完成。后续只有在真实 replay 和计算预算冻结后才实现 Stone Soup JPDA/MHT 或 FilterPy EKF/UKF/IMM 端到端对照；否则保持 unavailable，不以 adapter latency 代替 IDSW/continuity。

## 6. 审计结论

D2 已具备 P1 合同闭合所需的模块能力：D1 governed input 进入 truth-isolated GNN/Hungarian，源 identity 被匿名化，中心 `global_track_id` 稳定；在线 innovation 提供 NIS，隔离 evaluator 计算 IDSW、M-of-N、false-track 和 NEES；CV 10-seed 中 D2 IDSW、错误 duplicate 和 ID 改写均为 0。完整自适应门控、高阶关联/运动对照、原生 3D、D2 owner failover 和专用真实 dense/crossing 标定是后续研究；P2 保持隔离 adapter benchmark。
