# D2 Data Association Research Module

D2 是 C-UAS 多目标数据关联研究模块，目标是在离线仿真和日志回放中维护稳定的 `global_track_id`，降低多目标交叉、密集编队、漏检、短时遮挡和虚警条件下的 ID Switch 风险。

安全边界：本模块只用于科研仿真、dry-run 和离线评估，不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置或绕过人工授权的流程。

规模边界：D2 消费每帧传入的 `tracks`、`detections` 和当前 `active_tracks` 集合，不从场景名推断目标数量，不写死 2v2 或 5v5。`crossing_dense_5v5` 等名称只是可重复 baseline fixture；main runtime 的 `--drone-count N` 只应体现为传入 D2 的输入集合长度。

### 2026-07-20 六维稀疏关联路径

- 新增显式选择的 `Scalable3DTracker`：航迹状态和协方差采用
  `[pN,pE,pD,vN,vE,vD]` / `6x6`。独立六维量测使用 Joseph 更新，只有位置时仍使用
  3D NED Joseph 更新；D1 source posterior 保留完整 6x6 covariance 并使用保守 CI，
  不再把相关 posterior 重复当作独立位置量测。旧二维 `Tracker`、replay、JPDA/MHT
  与默认 `GNNHungarianAssociator` 均未改变。
- `Sparse3DGNNHungarianAssociator` 先用 `scipy.spatial.cKDTree` 生成保守空间候选，
  再计算 3D 位置创新马氏距离，并对稀疏二部图的每个连通分量运行 Hungarian。这里及
  旧类名中的 GNN 都表示 Global Nearest Neighbor，不是图神经网络；D5 的跨视角图网络
  不在 D2 实现。
- 在线 `Detection3D` 合同没有 truth 字段，并递归拒绝 truth/actor/object/entity、上游
  `global_track_id` 等身份元数据。D1 六维对象适配器忽略上游 canonical 值，只有 D2
  `Scalable3DTracker` 分配 `GT3D-*`；adapter 以 D1 state-valid timestamp 作为关联
  epoch，并另存原始 measurement/arrival timestamp 供延迟审计。在线结果显式输出
  `id_switch_count=None`、continuity unavailable 和 `AssociationRiskSummary`；独立
  `Sparse3DOfflineEvaluator` 只在关联结束后读取 truth sidecar。
- D1 adapter 不再丢弃位置-速度交叉 covariance。相关 posterior 的当前 CI track weight
  固定为 `0.5`；速度创新 NIS 超过三自由度 99% 卡方门限时，通过 covariance inflation
  降低该速度 posterior 的影响。关联中的速度项也只在有限代价内作 tie-break，位置候选
  仍由三维马氏门控决定。这里没有按速度模长、4.7 m/s 或场景名硬裁剪。
- 2026-07-20 单元验收覆盖 5/20/50/100/200、D 轴门控、两目标三维交叉、连续漏检、
  15 个匿名虚警、truth 拒绝、有界历史和六维速度稳定性。完整 D2 回归为
  `139 passed, 1 warning`，
  验收阈值为零失败；warning 是环境 Matplotlib `Axes3D` 导入问题。
- 同日 200 目标确定性规则网格做 3 个独立 trial，每个 trial 预热 1 帧后测量 30 帧；
  90 个测量帧的候选边均为 `200`，潜在全对 `40,000`，分量矩阵元素 `200`，最大单
  分量元素 `1`，候选裁剪率 `99.5%`。聚合关联 mean/P95/max 为
  `6.683/7.056/22.471 ms`，含预测与更新的 tracker step 为
  `25.491/26.797/41.613 ms`。这是当前主机单进程合成样本，包含系统调度尾值，不是
  实时 SLA、真实 AirSim 或多 seed 统计；极端全重叠场景仍可能形成大连通分量。

### 2026-07-20 六维速度状态稳定性修复

- main 只读诊断的 50v50、seed 17、2.2 s、radar-only 输入中，D1 速度 P50/P90/max 为
  `6.28/12.16/21.03 m/s`，速度 covariance trace 为 `101.24/110.31/112.32`；旧 D2
  输出反而升至 `8.89/17.43/27.49 m/s`，trace 缩至 `62.95/69.37/70.86`。根因是
  adapter 丢弃 6x6 交叉 covariance，tracker 又只消费位置 marginal；CV 预测产生的
  position-velocity cross covariance 令位置 residual 持续注入速度，同时错误收缩 Pvv。
- D2-owned 匿名合成复现使用 seed 17、50 条、12 帧、0.2 s 周期（0.0--2.2 s）。输入
  速度 P50/P90/max 为 `5.415/7.960/12.274 m/s`；旧路径复现为
  `9.41/14.31/21.88 m/s`、Pvv trace `62.76`。修复后为
  `5.082/6.401/7.218 m/s`、Pvv trace `101.181`，最终位置 RMSE 从输入 posterior 的
  `52.634 m` 改善到 `48.364 m`，离线 IDSW 为 0、continuity 为 1.0。
- 200 条批量回归使用 seed 41、10 帧、0.2 s 周期。每个更新帧候选/潜在全对为
  `200/40,000`，活动航迹始终 200；输入/输出速度 P90 为 `8.097/5.980 m/s`，输出
  Pvv trace 中位数 `69.685`，输入 trace 为 `75`，离线 IDSW 为 0、continuity 为 1.0。
  seed 29 的 21 帧双目标交叉另注入一次速度离群值，交叉帧保持 4 条位置门内候选，
  NIS update gate 与有限速度代价均触发，IDSW 仍为 0、continuity 为 1.0。
- 验收比较使用输入/输出分位数、covariance trace、位置 RMSE 和隔离离线身份标签；在线
  DTO 不含 truth/actor/object identity，也没有速度硬上限。CI 权重 `0.5` 只是当前保守
  baseline，未证明最优；至少 20 个未见 seed、六维 NIS/离线 NEES coverage、不同
  covariance 相关结构和高机动/模型失配标定仍开放。main 的 50v50/200v200 场景也需
  owner 在修复后复跑，本文不把模块合成结果替代为端到端结论。

### 2026-07-15 M5N2 真实 AirSim 20-case 证据同步

- 本批为 SimpleFlight M5N2：baseline 10 seed、candidate 10 seed，共 20 case；M5N2 达到
  20/20 后终止多 seed 批次。`TERM` 生效前仅额外完成一个被排除的
  `png_ttc_2v2_seed001`，其结果不进入 M5N2 聚合；dropout case 完成数为 0。
- 20 case 共记录 3805 个可用 D2 association main-bus 样本，mean/P95/max 分别为
  `2.521/3.147/98.942 ms`。均值和 P95 明显低于整个 main bus，但 98.942 ms 的单次
  尾部值仍需在后续性能审计中保留，不能只报告均值。
- 在线 truth identity/state 使用均为 0。由于在线 D2 没有 truth assignment，本批在线
  `id_switch_count`、`track_continuity` 和其他依赖真值的身份指标必须保持
  `None + unavailable`，不得写成 0；如需身份结论，必须另用隔离 sidecar 在写盘后评分。
- 本批第二 primary 进入 5 m 为 0/20，且其最终停止原因均记录为 `collision_stop`；但
  artifact 没有持久化碰撞对象，当前证据不能把该失败归因于 D2 关联。默认
  GNN/Hungarian、中心拥有 `global_track_id`、D5/D7 禁止本地重绑的合同均保持不变。

## 当前能力

已实现：

- GNN/Hungarian 默认关联器，底层使用 SciPy `linear_sum_assignment`。
- `DataAssociator` 可插拔接口，当前有 GNN、JPDA、MHT 三条接口兼容路径。
- 兼容基线保留马氏门控、二维 `[x,y,vx,vy]` 常速度 Kalman fallback 和 4x4 covariance；Detection/GlobalTrack covariance 在输入和门控边界拒绝非有限、明显非对称或明显非 PSD 矩阵，仅对数值容差内缺陷做对称化/特征值 floor。`covariance_consistency` 表示最新检查，`covariance_regularized`/`regularization_ever_applied` 与 `last_regularization` 保留历史正则化证据。
- 六维稀疏路径使用 `Detection3D`、`GlobalTrack3D`、完整 source 6x6 covariance、相关
  posterior CI、独立量测 Joseph update、速度创新 NIS 门控、3D 马氏门控、KD-tree
  候选图和分量级 Hungarian；航迹事件历史与逐帧审计均有配置上限，不保存无条件全密集代价/距离历史。
- GNN/Hungarian 主线在保留马氏门控和 `linear_sum_assignment` 的基础上，加入速度方向、短时历史和加速度异常组成的轻量运动一致性代价，并输出 motion consistency diagnostics。
- 在线 D1 track-to-track 输入增加非真值 `source_global_track_id` 连续性代价和来源谱系治理：已落入现有门限但未被一对一分配的上游影子航迹不立即 birth，仍绑定活动 D2 航迹但发生统计大跳的同源输入先隔离并记录原因；该保护不读取 actor/truth ID，不替代马氏门控或 GNN/Hungarian。
- quality-aware gate baseline：按 track quality、局部目标密度、位置协方差和上一帧 association risk 对每条 track 的 gate 做保守放宽或收紧；这不是完整自适应门控框架。
- `tentative/confirmed/engageable/lost/dropped` Track 状态机；summary 另导出不依赖 truth 的 `birth_count/lost_count/drop_count/rebirth_count` 和完整 lifecycle transitions。`rebirth` 仅指同一 `global_track_id` 从 `lost` 重获，不把 dropped 后新建航迹猜成同一真实目标。
- 每条 `GlobalTrack` 输出 `track_quality`、`association_risk` 和 `quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 与 metrics summary 同步输出 track-level 质量和风险字典，供 D3/D5/D6 消费。
- `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime 指标；无 truth assignment 时 IDSW、continuity 和 RMSE 字段仍存在，但值为 `None`，并分别输出一致的 `available=false` 与 `reason=truth_assignment_unavailable`。truth 可用且 IDSW 确实为零时输出可用的整数 `0`，不再用伪零表示 unavailable。
- `AssociationRiskSummaryWindowGenerator` 滑窗风险摘要，汇总代价 margin、候选重叠、IDSW delta、duplicate delta、可用 continuity、D5 disagreement、source node 和 link type；不可用 continuity 不参与 `duplicate_track_risk`、`continuity_collapse` 或 hard risk 计算。
- `RiskThresholds` / `classify_risk_summary()` 软/硬风险分层，按 D4 口径区分 ambiguity/cost margin/candidate overlap 与 IDSW/duplicate/continuity collapse。
- D1 6D NED `GlobalTrack` 到 D2 2D `Detection` 的旧投影 adapter，保留 `measurement_timestamp`、`arrival_timestamp`、covariance 和 metadata；新 `detections3d_from_d1_global_tracks()` 保留 NED 六维 source posterior 及完整 covariance，以 state-valid timestamp 对齐关联 epoch，把原始双时间戳留在 source metadata，并忽略上游 canonical ID。
- AirSim-style dry-run/replay adapter，不 import 或调用 `airsim`，并在 bus message 中导出当前活动 `global_track_ids`。
- `load_airsim_replay_frames()`、`run_airsim_replay_association()`、`run_threshold_sensitivity()` 和 `summarize_multi_seed_risk_calibration()` 支持离线 JSON/JSONL replay 读取、association log/report 输出、seed/episode/scenario/frame/offline truth label 校准元数据透传、`RiskThresholds.profile_version` 与 `association_risk_threshold_version` 记录、gate pass/reject count、motion/quality risk summary、dense/crossing threshold sensitivity summary 和多 seed 推荐阈值摘要；无 truth label 的 N-v-N replay 会用输入观测数或显式 count 字段给出 `target_count` fallback。
- `OfflineTruthLabel` 冻结 `d2-offline-truth-label/v1` JSONL 合同，每条记录包含 `episode_id/frame_index/timestamp/truth_id/position` 和可选离线匹配注释；读写器拒绝重复键和非法坐标。`strip_offline_truth_from_frames()` 生成不含 truth 的在线帧，`run_airsim_replay_association(..., offline_truth_labels=...)` 只在在线关联结束后构造 evaluator-only 评分视图。
- `build_dense_crossing_replay_fixture(target_count=N)` 按输入 N 生成 dense crossing、遮挡式连续漏检和虚警压力场景；`build_5v5_replay_fixture()` 只是兼容包装器。`run_dense_crossing_calibration()` 强制至少 10 个唯一 seed，输出每 seed IDSW、continuity、NIS/NEES availability、gate/risk profile/version、runtime、确定性签名和保留 unavailable 的聚合摘要。
- `load_airsim_replay_frames()` 同时接受旧 AirSim `frames` schema 和 D1 `d1.governed_replay_manifest.v1 + records`。D1 adapter 按 frame/timestamp 聚合 radar records，用球坐标雅可比投影到水平 N/E，并匿名化 observation ID/lineage；一维声学和 pixel EO 不混入 N/E，按原因显式跳过。
- P1 replay 治理默认将 simulator truth 从在线 `Detection`、track 和 association log 中移除，并将源 detection/actor ID 改为按帧匿名 ID；嵌套 actor/truth metadata 同样递归清除。GNN/Hungarian 仅看到量测、协方差、时间戳、置信度和可用特征。`OfflineTruthEvaluation` 在关联完成后按同帧输入顺序独立对齐标签，计算 IDSW、continuity、confusion matrix 和 RMSE；报告同时保留 `online_metrics` 与 `offline_truth_evaluation`，避免把在线 unavailable 误写成零。
- `InitializationGovernanceProfile` 提供版本化 M-of-N 初始化口径，默认 `2-of-3`，也可由 replay 和 gate sensitivity 入口显式传入其他 profile；离线治理输出初始化/确认延迟、成功率、虚假航迹数与比例、漏检数、虚警数、逐帧 measurement count / truth-target count 以及 mismatch frame count。
- NIS 由关联前 innovation covariance 和马氏距离计算，不依赖 truth，因此无 truth replay 仍可输出；NEES 只在独立 offline truth state 可用时计算。两者输出样本数、均值、中位数、二维/四维 95% 卡方区间及区间覆盖率，不把缺失样本解释为零。
- `build_5v5_replay_fixture()` 构造动态 5 目标 crossing/dense/漏检/虚警组合 fixture；它只用于回归和标定，不把 5 写入关联器或 Tracker。
- `AssociationLogEntry.rejected_pairs` 默认空列表并完整序列化 `mahalanobis_gate`/`assignment_above_gate` 原因；replay gate summary 按原因统计，旧 JSON 缺该字段时按空列表兼容。
- 跨节点注册基础：`SourceTrackSummary` 使用 `(source_node_id, local_track_id, local_epoch)` 命名空间、独立 measurement/arrival timestamp、6D NED state/covariance、quality、lineage/correlation status 及 candidate/current canonical hint，在线合同不含 truth。
- `CrossNodeTrackAssociator` 将 source tracks 传播到公共时刻，按完整 6D 状态和差分协方差做 Mahalanobis gate，并按 source 节点分组使用 Hungarian；`CrossNodeTrackRegistry` 因而支持一个 canonical `global_track_id` 绑定多个观察节点的 source tracklets，同时保持同一 source 内一对一。
- registry 对 `exact_known_correlation` 输出 D1 数值相关融合请求，对 `unknown_correlation` 只输出 CI/保守融合请求，对显式 duplicate、重复 payload、重复 lineage 和 stale/replay source track 在关联前拒绝；D2 不复制数值 CI。
- cross-node 在线指标输出 source binding rebind ID switch、duplicate payload rejection 和 transport/queue/fusion latency；`OfflineCrossNodeMetricsEvaluator` 在独立 truth mapping 下计算 canonical duplicate 与 track-to-track association precision/recall，不向在线 registry 暴露 truth。

### 2026-07-15 Ceiling-aware 身份连续性准入

- P1 报告 schema 已升级为 `d2-p1-identity-calibration/v2`，准入策略版本为
  `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`。基线连续性为
  `C_b` 时，剩余误差空间 `H=max(0, 1-C_b)`；候选实际提升
  `Delta=C_c-C_b`；v2 所需提升为 `Delta_req=min(0.10, 0.10*H)`。当 `H>0`
  时同时输出 `Delta/H`，即候选消除基线剩余身份错误的比例；当 `H=0` 时只接受合法、
  不退化的 `C_c=1`。
- 每个候选输出 baseline headroom、实际/所需提升、headroom/error reduction fraction、
  policy version，以及 IDSW、continuity、false-track、P95 latency、truth leakage 五项
  gate 的 `passed/reason/actual/required`。缺指标、非有限值、越界连续性、零 IDSW
  基线、continuity 退化、false-track 超限、延时超预算或任一在线 truth leakage 均
  fail-closed；不能只凭 IDSW 改善晋级。
- v1 的固定 `+0.10` 仍在报告中以 `legacy/deprecated` 字段保留，仅供历史审计，明确
  `used_for_admission=false`，不改变旧字段曾表示“绝对提升”的语义。任何通过结果仍
  只是 promotion review 建议，`default_online_path_changed=false`，默认在线
  GNN/Hungarian 不变。
- 2026-07-15 已使用冻结的六档真实 AirSim replay/truth manifest 离线重算完整 v2
  报告，本批没有重新启动 AirSim。candidate `gnn-g5.99-qa1-ld3_7-mw0.5x` 的总体
  IDSW `1.358333 -> 0.616667`，continuity `0.981046 -> 0.983954`；headroom
  `0.018954`、所需提升 `0.001895`、实际提升 `0.002908`、error reduction
  `15.3448%`。false-track 0、P95 `15.470 ms`、baseline/candidate truth leakage 0，
  五项联合 gate 全部通过，因此 `promotion_recommended=true`。该字段只表示评审建议；
  `selected_online_path=baseline_gnn_hungarian` 且
  `default_online_path_changed=false`。
- 分档只有 `clutter` 和 `combined` 通过完整联合 gate；其余四档 baseline IDSW=0，
  按 `baseline_zero_no_measurable_reduction_evidence` fail-closed。dropout 的 offline
  truth alignment 为 partial，未做最近邻补齐，也没有在线 truth 泄漏。
- 2026-07-15 模块回归：`113 passed, 1 warning`；warning 仍是本机 Matplotlib
  `Axes3D` 多版本导入问题，不影响准入判据。

### 2026-07-14 Online Truth Policy 与 Truthless 指标收口

- `TrackerTruthPolicy` 显式区分 `online` 与 `offline`，默认 `online`。在线 `step()` 在状态预测和关联前 fail-closed：拒绝 `Detection.truth_id`、任何显式 `truth_ids_present`，以及 Detection/frame metadata 中递归出现的 truth、actor 或 object identity。`online_truth_isolated`、`online_truth_hints_used`、`truth_metrics_available`、`continuity_available` 仅作为布尔治理状态允许通过；非布尔值仍拒绝。拒绝发生时不建轨、不计帧。
- replay 的在线路径显式使用 `online` tracker；synthetic simulation 和允许 truth 的 evaluator/dry-run 路径显式使用 `offline`。offline evaluator 继续允许 truth，并保持“真实零 IDSW = available `0`”。
- 验证日期为 2026-07-14：8 类拒绝用例、main owner 四布尔状态正例、3 帧和 5 帧 truthless replay、7 帧 birth/lost/rebirth/drop 状态序列及完整 D2 回归均通过；验收阈值为零失败、在线拒绝发生于状态变更前、truthless 三个身份/误差字段均为 `None`。完整结果为 `98 passed, 1 warning`，warning 是环境中的 Matplotlib `Axes3D` 多版本导入问题。
- 本批没有修改 `confirmation_hits`、`lost_miss_threshold`、`drop_miss_threshold` 或 gate。真实 replay 中 `T001 -> T005` 航迹序列对应的 birth/lost/drop/rebirth 参数标定仍为 P1。

### 2026-07-12 状态同步

- commit `33e6fa0` 本身没有修改 D2；其后的 D2-owned P1 任务新增长 governed replay 校准入口、OOSM exposure 审计和动态 N/M 回归。该阶段 D2 回归当时为 `69 passed, 1 warning`，warning 是本机 Matplotlib `Axes3D` 多版本导入问题。
- main GAP 与 PNG delivery AirSim 报告给出的 D2 相关新证据仅是合同保持：2v2 candidate 10 seeds 为 20/20 pair、在线 truth 使用为 0；锁定后两帧 dropout 仍沿原 global/local track 与计划上下文预测，没有 truth ID 或本地 ID 重写。
- M5N2 8 s 短窗口为 0/9，且不是同几何、同时间窗的长期对照；该 AirSim 报告没有 D2 专项 offline IDSW/continuity 或真实 dense/crossing 长回放。当前已闭合 D2 synthetic 长 replay runner/schema，但真实 replay、gate/risk、M-of-N/false-track、NIS/NEES 和跨节点 failover 标定仍开放。

### 2026-07-11 main runtime 合同验收证据（历史）

- main 在线链路已强制令 D2 输入和航迹的 `truth_id=None`；D1 -> D2 -> D3 仍按 D2 状态、协方差、质量和中心维护的 `global_track_id` 运行，不再依赖 simulator truth/actor identity 构造 D3 目标。
- `d2_governance_summary` 已进入 main episode bus 并由 D6 消费。D1 governed replay adapter 保留 timestamp/covariance 并匿名化来源身份；D2 在线关联不读取 simulator truth，truth 只通过 `d2-offline-truth-label/v1` 在 episode 后评分。
- P1 合同层已闭合。M=5、N=2 的 ComputerVision 10-seed 批次中，T001 双 primary 视觉共识与当前计划授权为 8/10；D2 相关指标为 `id_switch_count=0` (10/10)、错误 duplicate 为 0 (10/10)、`global_track_id` 改写/重绑为 0 (10/10)。
- 二级接管和完全分布式的 coalition commit 正例均进入 `executing`，缺 ACK 时为 `aborted`/`hold_for_review` 且导引许可为 0。这是下游消费 D2 中心管理 `global_track_id` 的 commit/fail-closed 合同证据，不是 D2 重绑 ID 或实现分布式临时 ID 合并的证据。
- SimpleFlight 15 s 仅用于诊断。30 个 active pair 的物理命中为 0，因此不能宣称物理拦截闭合；该结果也不改写 D2 已通过的身份与 truth-isolation 合同结论。
- D2-owned N-target dense/crossing fixture、至少 10-seed runner、offline truth 和 availability-aware 汇总已闭合。专用真实 AirSim dense/crossing 的参数标定是后续性能研究，不再作为 P1 合同 blocker。
- P2 benchmark 在同一 frozen replay digest 下固定输出 GNN/Hungarian、FilterPy、Stone Soup、模块内 JPDA 和模块内 MHT 五行。GNN/JPDA/MHT 复用同一 `Tracker` 生命周期并在在线运行结束后由隔离 truth evaluator 计算 IDSW/continuity；Stone Soup 1.9.1 和 FilterPy 1.4.5 仍仅是对象 adapter smoke，不是端到端 tracker，也不进入默认依赖/在线路径。

部分实现：

- `JPDAAssociator` 可执行小规模联合假设枚举和 marginal probability 对照，但不是完整 JPDA filter。
- `MHTAssociator` 可执行有界 branch 和短历史对照，但不是完整 MHT。
- 旧 `Tracker` 继续投影 D1 3D/NED 输入；独立 `Scalable3DTracker` 已实现原生六维状态，
  main-owned scalable point-mass 总线已有只读运行证据，但修复后端到端复跑、版本化输出
  验收与多 seed 标定尚未完成。
- cross-node registry 已完成低歧义 GNN/Hungarian 注册基础，但尚无多帧 JPDA/MHT 歧义保持、owner/epoch failover 或数值融合回写。
- Stone Soup `Detection` adapter 与 FilterPy CV `KalmanFilter` adapter 已可选执行并记录对象转换/更新 latency；它们是 adapter smoke，不是端到端 tracker，IDSW/continuity 必须标记 unavailable。

未实现：

- Stone Soup 完整 JPDA/MHT tracker benchmark。
- FilterPy EKF/UKF/IMM 或端到端数据关联 tracker。
- `scalable_3d_simulation` 六维路径修复后的版本化输出 schema 和端到端多 seed 验收；
  episode-bus 基础编排已有 main 只读运行证据，不再列为完全未接入。
- JPDA/MHT 自动升级触发。
- D2 不直连 AirSim SDK，不负责 ComputerVision 图像/metadata 采集或 episode 编排；它只消费 main/runtime 导出的 governed replay 与隔离 offline truth。
- 跨节点多 source 的 D1-owned 数值 CI、已知交叉协方差融合、fusion NEES/ANEES 和
  通信字节统计；D2 当前只发布跨节点相关性决策与融合请求。D2 内部针对同一 source
  posterior 时序相关性的固定权重 CI 不等同于该跨节点数值融合能力。

## 目录

- `d2_data_association/models.py`：`Detection`、`GlobalTrack`、`AssociationResult`、风险摘要和生命周期数据结构。
- `d2_data_association/gating.py`：马氏距离、门控代价矩阵和歧义分数。
- `d2_data_association/associators.py`：`DataAssociator`、`GNNHungarianAssociator`、`JPDAAssociator`、`MHTAssociator`。
- `d2_data_association/tracker.py`：常速度 Kalman fallback、状态机、建轨、漏检和删除。
- `d2_data_association/metrics.py`：IDSW、continuity、duplicate、RMSE、confusion matrix、风险摘要和软/硬风险分层。
- `d2_data_association/cross_node_models.py`：source-track、canonical binding/history、相关性和融合请求合同。
- `d2_data_association/cross_node_registry.py`：公共时刻传播、track-to-track Hungarian 和中心 canonical registry。
- `d2_data_association/cross_node_metrics.py`：truth-free registry 指标和隔离的 offline cross-node evaluator。
- `d2_data_association/scalable_3d_models.py`：truth-free `Detection3D`、六维 `GlobalTrack3D` 和松耦合 D1/scalable 量测适配器。
- `d2_data_association/sparse_3d.py`：KD-tree 稀疏 GNN/Hungarian、六维 CV Tracker、风险摘要和有界审计。
- `d2_data_association/scalable_3d_offline.py`：关联完成后才可调用的 3D truth sidecar IDSW/continuity evaluator。
- `d2_data_association/dry_run_adapter.py`：D1/AirSim-style dry-run 输入适配和 bus message 输出。
- `d2_data_association/d1_governed_adapter.py`：D1 frozen manifest/records 到在线安全 D2 radar/N-E frames 的转换和跳过诊断。
- `d2_data_association/replay.py`：离线 JSON/JSONL replay 读取、association report/log 输出和阈值敏感性 helper。
- `d2_data_association/replay_governance.py`：在线 truth 隔离、offline label evaluator、M-of-N 初始化、false-track、NIS/NEES 和 5v5 压力 fixture。
- `d2_data_association/offline_truth.py`：版本化 offline truth JSONL 合同、truth stripping 和 evaluator-only 评分视图。
- `d2_data_association/calibration.py`：N-target dense/crossing 至少 10-seed runner、每 seed 结果和 availability-aware 聚合。
- `d2_data_association/compat.py`：optional dependency 版本/原因探测、Stone Soup Detection 和 FilterPy CV filter 对象 adapter。
- `d2_data_association/p2_benchmark.py`：同一 frozen replay 下默认 GNN/Hungarian、模块内 JPDA/MHT 研究 adapter 与外部对象 adapter 的隔离比较合同。
- `d2_data_association/simulation.py`：crossing、dense 5v5、formation、occlusion、missed、false alarm 场景。
- `scripts/run_simulation.py`：CLI benchmark runner。
- `scripts/run_dense_crossing_calibration.py`：P1 多 seed 校准 CLI，单独输出 truth JSONL 和聚合 JSON。
- `scripts/run_p2_optional_benchmark.py`：读取 frozen replay/truth 文件并输出 P2 adapter comparison JSON。
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
- 2026-07-11 P1 CV 批次、episode 证据和隔离 truth 由 main/runtime/D6 生产/评分；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW/continuity。D2 不连接 AirSim SDK。若继续做专用真实 dense/crossing 标定，应沿用已冻结 schema/profile，但它是后续性能研究而非 P1 合同缺口。
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

P1 N-target、至少 10-seed 校准：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_dense_crossing_calibration.py \
  --target-count 5 \
  --steps 12 \
  --output /tmp/msm-d2-calibration
```

输出目录包含 `calibration_summary.json` 和按 episode 分开的 `offline_truth/*.jsonl`；这些 truth 文件只供离线评分使用。

P1 长 governed replay 校准：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_long_replay_calibration.py \
  --target-count 5 \
  --steps 120 \
  --sample-period-s 0.2 \
  --output /tmp/msm-d2-long-replay
```

该入口固定使用默认 `GNNHungarianAssociator`，场景版本为
`d2-governed-long-replay/v1`，覆盖重复 dense crossing、交叉窗口遮挡、
周期漏检、近场虚警和延迟到达。输入帧由 D1/main 治理后按
`measurement_timestamp` 排序；D2 保留 `arrival_timestamp` 并报告 arrival
inversion/late measurement 暴露，但不宣称实现原始量测 OOSM 回溯。每 seed
输出 IDSW、identity/coverage continuity、false-track、RMSE、NIS/NEES
availability、版本化 gate/risk profile、中心 ID owner 和 online truth leakage。
量测数可以小于或大于目标数，目标数和代价矩阵均来自当前输入，不依赖场景名。

P1 dense/crossing 固定矩阵标定：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_p1_identity_calibration.py \
  --screening-manifest /path/to/screening-10seed-manifest.json \
  --confirmation-manifest /path/to/confirmation-20seed-manifest.json \
  --output /tmp/d2-p1-identity-calibration.json
```

manifest schema 为 `d2-p1-identity-calibration-input/v1`，每个 seed 显式给出
`replay_path` 和 evaluator-only `truth_path`，并冻结
`frozen_p95_loop_latency_budget_s`。runner 对全部 54 组 GNN 配置使用同一个
replay/truth digest，覆盖 gate `5.99/9.21/13.82`、quality-aware off/on、
lost/drop `1/3, 2/5, 3/7` 和 motion weight `0.5/1/2` 倍。轻量 JPDA 只在最佳
GNN 的输入、gate 和 lifecycle 上做离线同预算对照。缺少 10 或 20 个唯一 seed 时
对应阶段显式 `unavailable`，不会用 synthetic fixture 补齐或冒充 AirSim 结论。
准入报告使用 `d2-p1-identity-calibration/v2` 和版本化 ceiling-aware 联合门限，
只给出评审建议，不会替换默认 GNN/Hungarian。

`truth_path` 按 suffix 和 schema 显式选择：`.jsonl` 读取
`d2-offline-truth-label/v1`；`.json` 只接受 D1 freeze 生成的
`d1.airsim_offline_truth.v1`。D1 JSON adapter 校验 `evaluator_only=true`、NED
frame、有限 timestamp、非空 `truth_id` 和有限三维 `position_ned`，再按量测时间
映射到 governed replay frame，并投影为 D2 水平 N/E label。Down 分量只进入离线审计
annotation。无法唯一匹配 replay frame、位置不可用或 schema 不支持时直接拒绝，绝不
把 sidecar 内容写入在线 frame。

证据分类兼容 legacy `airsim` 和受治理的 `real_airsim_*` 来源标识，因此 main 生成的
`real_airsim_blocks_d1_governed_replay` 会在 screening、confirmation 和 JPDA 对照中
正确标为 `airsim_evidence=true`。包含 `airsim` 字样但不以 `real_airsim_` 开头的
synthetic 来源不会被误分类。该字段只描述证据来源，不参与参数排序或算法准入。

P1 高难度 replay 使用六个固定 `scenario_difficulty`：`nominal`、
`tight_crossing`、`dropout`、`clutter`、`delayed_noisy`、`combined`。manifest 可在
顶层设置统一难度，也可在 case 中覆盖；可选 `difficulty_metadata` 记录 main 实际注入
参数。D2 只校验和消费元数据，不在模块内生成 AirSim 数据。混合 manifest 的 case
唯一键为 `(scenario_difficulty, seed)`，每个出现的难度档都必须满足 screening 10 个
seed；confirmation 通常只提供 `combined` 的 20 个 seed。

每个 GNN/JPDA 结果新增 `aggregate_by_difficulty`，报告的 `difficulty_results` 直接给出
每档 baseline、最佳 GNN、JPDA 的 IDSW、identity continuity、false-track、RMSE 和
p95 latency，以及分档 admission。若所有受评算法在某档均为 `IDSW=0` 且
`identity_continuity=1.0`，该档显式标记
`scenario_still_non_discriminative=true`，禁止把理想但无区分度的 fixture 解释为候选
算法优于默认 GNN/Hungarian。在线 truth 隔离和 v2 版本化联合准入保持不变。

真实 governed replay 的观测压力使用纯离线 API：

```python
from d2_data_association import transform_d1_governed_replay

result = transform_d1_governed_replay(
    d1_governed_bundle,
    scenario_difficulty="combined",
    seed=7,
    declared_target_spacing_m=2.0,
)
# main 写 result.payload，并把 result.profile_metadata 放入校准 manifest。
```

transformer 不接收 truth sidecar：`dropout` 在量测时间中段删除 0.6-1.2 s 雷达记录，
`clutter` 每帧注入 1-3 条匿名雷达虚警，`delayed_noisy` 增加 0.2-0.5 s 到达延迟并将
协方差放大 3 倍，`combined` 组合三者。保留的记录维持 measurement timestamp、
arrival timestamp、covariance 和原 source lineage；延迟/噪声 profile 在保留原值
来源的同时生成受治理新值和追加 lineage。虚警仅使用 opaque ID，并带
`injected_evaluator_scenario`。

几何不能由该 API 伪造：`nominal/dropout/clutter/delayed_noisy` 只接受 main 声明的
约 4 m 捕获，`tight_crossing/combined` 只接受约 2 m 捕获。若 D1 provenance 已携带
`target_spacing_m`，声明必须一致；没有该字段时，报告明确标记为
`capture_declaration_only_no_truth_geometry`。输出包含 profile metadata、输入/输出
digest、实际注入参数、计数和 online truth leak 审计。

进入真实 AirSim P1 标定 manifest 时规则更严格：D1 adapter 会把
`target_spacing_m` 和 `d2_offline_stress_profile` 透传到每个 D2 frame；
`airsim`/`real_airsim_*` case 缺少 spacing、4 m/2 m 档位不符、frame 与 profile
数值冲突或 difficulty 冲突时直接拒绝。六档治理仍以 `(difficulty, seed)` 为唯一键，
允许不同 seed 保留不同的实际 dropout/delay/clutter 参数，仅 profile/schema/version
等不变量要求同档一致。分档摘要同时报告 NIS/NEES available seed count。

D1 offline truth 允许比 governed replay 更稠密。adapter 只在量测时间戳位于冻结
`1e-9 s` 容差且 frame 可唯一确定时生成 evaluator label；没有匿名传感器观测而缺失的
replay frame 记为 unmatched，不做最近邻补配。输出 `complete/partial/unavailable`、
matched/unmatched sample count、原因和不含身份的样本索引/时间审计。非法 sidecar、
重复样本或同时间多 frame 无法消歧仍 fail closed；truth 不进入在线 frame。

## 可选集成

`filterpy` 和 `stonesoup` 不是运行时依赖。默认环境缺依赖时，对应行输出 `dependency_available=false`、`executed=false` 和明确的 `unavailable_reason`；不会静默回退。隔离环境已验证 FilterPy 1.4.5 与 Stone Soup 1.9.1 的对象 adapter，但完整外部框架 JPDA/MHT、EKF/UKF/IMM 和 optional 端到端 IDSW/continuity 仍未实现。模块内 `JPDAAssociator`/`MHTAssociator` 不需要外部依赖，只作为显式 research adapter 运行，不能解释为完整算法已经实现。

```bash
PYTHONPATH=research_modules/d2_data_association \
/home/linux/.cache/msm-p2-venv/bin/python \
  research_modules/d2_data_association/scripts/run_p2_optional_benchmark.py \
  --replay /path/to/frozen_replay.jsonl \
  --offline-truth /path/to/offline_truth_labels.jsonl \
  --output /tmp/d2-p2-benchmark.json
```

输出 schema 为 `d2-optional-framework-benchmark/v2`。每行统一包含 `id_switch_count`、`track_continuity`、`latency_seconds` 和 `unavailable_reason`：GNN/JPDA/MHT 行在离线标签有效时提供身份指标；FilterPy/Stone Soup 对象行的身份指标保持 unavailable，并用 `adapter_only_no_end_to_end_association` 说明原因。所有行继续声明完整 JPDA/MHT 的真实实现状态。输入若为 D1 governed replay，报告 `input_metadata.d1_governed_adapter` 会给出接受的 radar 数量、跳过模态及投影方法。

## 2026-07-14 AirSim `T008` 来源谱系膨胀 P1 修复

- 修复前审计对象为真实 Blocks episode
  `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001`，
  seed 1、351 帧、在线目标数 2。D1 在 31.3 秒由 2 条航迹增至 3 条：新增
  `global_track_003` 只有单次雷达支持，却与原 `global_track_002` 同时落入 D2
  `T002` 门限；之后 `global_track_002` 又从约 `[77,-19] m` 跳至
  `[13.5,-24.9] m`。D2 未使用上游航迹谱系，因而累计 birth 8、drop 4，并在
  34.4 秒生成 `T008`；D3 随后把它纳入新计划，放大为 plan/pair churn。
- D2 修复由 `GlobalTrack.source_track_ids`、GNN 来源连续性代价、门内影子 birth
  抑制和已绑定来源的马氏大跳隔离组成。来源 ID 只是 D1 航迹谱系，不是目标真值；
  新来源在几何允许时可并入既有 D2 航迹，D2 规范 `global_track_id` 不被重写。
- 修复后验证为 4 帧匿名在线回归：2 条目标轨迹、1 条近邻重复来源和 1 次同源
  teleport；验收阈值为活动 D2 航迹始终恰为 2、影子 birth 抑制 1 次、大跳隔离
  1 次、truth 输入 0。专项与完整回归通过，最新结果为 `99 passed, 1 warning`；
  warning 仍是本机 Matplotlib `Axes3D` 环境问题。
- 修复后的同 seed 真实复跑已经完成，详见下一节。2026-07-15 后续 M5N2 已完成
  baseline/candidate 各 10 seed，但未注入显式 teleport/影子扰动，也未形成该批 D2
  offline identity 评分，因此仍不能把 seed 数量达标外推为 P1 参数冻结结论。

## 2026-07-14 Post-batch M5N2 同 seed 复验

审计对象为以下两组真实 Blocks、M5N2、seed 1 episode，均不保存在线真值：

- `p1_terminal_closure_postbatch_seed1_20260714_m5n2_baseline_seed001`；
- `p1_terminal_closure_postbatch_seed1_20260714_m5n2_candidate_soft_prediction_trend_coast_seed001`。

baseline 共 142 帧，candidate 共 141 帧。两组 D1 均在前 2 帧后稳定输出
`global_track_001/global_track_002`；D2 分别在后续 140/139 帧只维护
`T001/T002`，最大活动规范航迹数为 2，未再出现 `T008`。两组 truth-free 生命周期
均为 `birth=2, lost=0, drop=0, rebirth=0`，状态只发生
`tentative -> confirmed -> engageable` 各两次。来源绑定最终均为
`global_track_001 -> T001`、`global_track_002 -> T002`。

在线摘要按设计保持 `id_switch_count=None`、`track_continuity=None` 和
`truth_assignment_unavailable`；这不是零 IDSW 的在线声明。独立 sidecar 只在写盘后
进入 evaluator：对 D1 governed replay 运行现有 `run_airsim_replay_association()`，
两组均得到 IDSW 0、identity/coverage continuity 1.0、false track 0、online truth
isolation violation 0。对 main 实际发布的 track records 做独立位置匈牙利裁决时，
baseline/candidate 分别得到 IDSW 0、continuity 0.985915/0.985816；差异仅来自 D1/D2
启动前 2 帧尚无规范航迹，混淆关系始终为 `TGT-001 -> T001`、
`TGT-002 -> T002`。

本次平稳 episode 中 `suppressed_births=0`、quarantine 0、source conflict 0，说明
来源治理没有误触发，但没有真实激发 teleport 抑制。teleport/影子能力仍由匿名专项
回归证明。当前判断是：`T008` 同 seed 复发缺口已关闭；2026-07-15 的 20-case 已满足
普通 M5N2 运行数量并补齐 D2 阶段时延，但没有覆盖重复来源、teleport、漏检、杂波、
合法新目标 birth 延迟或独立离线身份评分，相关 P1 仍开放。默认 GNN/Hungarian、中心
`global_track_id` 所有权和在线 truth 隔离均不变。

## 2026-07-16 来源身份治理显式指标

- `MetricsRecorder.summary()`、逐帧 `AssociationRiskSummary`、replay risk summary、
  threshold sensitivity 逐 seed 行及多 seed/校准聚合现在显式保留
  `source_binding_conflict_count`、`source_lineage_quarantine_count` 和
  `upstream_local_identity_rejection_count`；`id_switch_count` 仍是独立且显式的
  truth-based 指标，未被三项在线治理诊断替代。
- 前两项分别只累计每帧 `AssociationResult.metadata.source_binding_conflicts` 和
  `quarantined_sources` 的条目数。第三项只接受经 `Tracker.step(frame_metadata=...)`
  验证的同名非负整数；字段缺失为 0，布尔、浮点、字符串、`None` 和负数均在预测、
  关联或建轨前 fail closed。该上游计数只记录 D1/main 已拒绝的本地身份塌缩候选，
  不合成 Detection、不创建 Track，也不把 local/source ID 升级为 `global_track_id`。
- 2026-07-16 专项验证包含连续同源、同源跨两个规范航迹冲突、绑定来源马氏不连续隔离、
  零观测上游审计、5 类非法 metadata 和旧帧无 metadata 兼容。两条 3-frame replay
  seed 7/8 各得到 conflict=1、quarantine=1，上游拒绝分别为 2/4；多 seed 均值为
  1/1/3。验收阈值为精确计数、非法输入零状态副作用和完整回归零失败，结果为
  `123 passed, 1 warning`；warning 仍是本机 Matplotlib `Axes3D` 环境问题。
- 本批没有启动 AirSim、没有读取像素或 actor/truth ID、没有复制 D5
  `bright_hungarian`，也没有改变默认 GNN/Hungarian、马氏门限、来源连续性权重、
  lifecycle 门限或风险阈值。三项计数当前是审计证据，不自动新增 soft/hard risk 原因；
  至少 10 个真实 duplicate-source/teleport/合法新目标受治理 case 的统计标定仍开放。

## 2026-07-20 scalable 3D 离线身份映射合同

D2 新增 `scalable_3d_identity.py`，只用于在线关联结束后的 evaluator。公开版本为：

- evidence bundle：`d2.scalable3d_identity_evidence.v1`；
- observation truth adapter：`d2.scalable3d_observation_truth.v1`，并严格适配现有
  `scalable3d-offline-truth-v1` 的 `observation_id -> truth_entity_id` sidecar；
- frame mapping：`d2.scalable3d_global_track_truth_mapping.v1`；
- metrics：`d2.scalable3d_identity_metrics.v1`；
- evaluation artifact：`d2.scalable3d_identity_evaluation.v1`。

公开入口包括 `ObservationLineageRef`、`GlobalTrackLineageEvidence`、
`create_scalable_3d_identity_evidence_bundle()`、
`evaluate_scalable_3d_identity[_files]()` 以及 evidence/truth/evaluation 的确定性
writer/loader。文件入口要求 evidence bundle 的外部 SHA-256，同时校验其绑定的 D1
records、D2 records、truth sidecar 三个 SHA-256、在线 schema、truth-isolation audit
和 record sequence。sequence 不是仅做存在性检查：每条 mapping 还必须逐项绑定被哈希
D2 record 中同一 frame 的 D2-owned canonical ID、六维 `state_ned`、`6x6 covariance`、
lifecycle/association/source lineage，并回查对应 D1 observation lineage；任一不一致直接
拒绝。逐帧输出 mapping status、候选 truth、证据/replay/重复计数、冲突原因和 source
hashes。

身份只沿 `source_lineage` 最终的 `observation_id` 连接独立 truth label。一个 truth 对应
多条有效 global track 会计入 `duplicate_truth_to_track_count`；一条 track 的证据指向
多个 truth、同 lineage 被多 track 声明、标签冲突、缺标签、未标记重放、时间窗冲突或
lifecycle 冲突时为 `ambiguous/unavailable`，不会按名称、actor ID、终态邻近或最近距离
选 truth。IDSW、identity/coverage continuity 和 duplicate 采用 `MetricsRecorder` 的
逐帧 first-assignment 口径；只要身份完整性不足，值就是 `None + availability=false`，
不以 0 填补。

2026-07-20 新增 23 个专项，覆盖稳定身份、真实 ID switch、一对多/多对一、缺失/重复/
冲突 lineage、显式 replay generation、标签冲突与篡改、时间窗、dropped 后复用、无
truth、37 目标动态规模、schema/hash/在线 truth 隔离、六维 source binding、D2 ID owner、
在线 IDSW null/unavailable 和 public artifact availability round-trip。完整 D2 回归为
`162 passed, 1 warning in 30.63s`；warning 仍为环境 Matplotlib
`Axes3D`。本轮未修改在线 association、`global_track_id` owner、门限、JPDA/MHT、控制
路径或默认 GNN/Hungarian。当前只关闭 D2-owned 离线合同；main 持久化 evidence 与 D6
接线、AirSim/point-mass 正式多 seed 身份性能仍开放。当前 main producer 会跳过无
source lineage 的 D2 track/frame；在其按完整 D2 frame 集合持久化 available/unavailable
evidence 前，不能把现有接线写成端到端 identity metrics 已可用。

## 2026-07-22 陈旧后验重放治理

active-risk 5v5、seed 1005 暴露出一条独立于空间近邻的重复航迹路径。D1 的一条预测型
后验在没有新传感器观测时仍按当前状态时刻发布，但 `latest_observation_id` 长时间保持
为 `radar-s000002-d0003`。旧 D2 只看每帧重新生成的 detection ID，把同一底层观测
重复计为新命中，最终令 `GT3D-000004` 和 `GT3D-000006` 同时 confirmed。两条航迹
相距约 1.5--1.6 km，不能用宽距离门强行合并。

`Scalable3DTracker` 现已在 GNN/Hungarian 前增加在线观测新鲜度治理：

- 以 `latest_sensor_id + latest_observation_id` 形成不解析内容的 opaque evidence key；
- 同一 key 跨帧再次出现时从关联输入中隔离，不参与状态更新、命中计数或确认；
- 同一 key 携带冲突的源量测时间时 fail closed，并输出时间冲突审计；
- tentative 航迹连续两帧没有新证据后删除，第一次漏配只重置连续命中，保留短时重获；
- 航迹合并只允许共享 observation/source 证据、六维位置和速度统计门均通过、且双方
  没有在同帧同时获得新证据。survivor 依次按生命周期成熟度、创建时间、命中数和
  `global_track_id` 选择；状态使用协方差交叉融合，不累加重复命中。

真实复现命令：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/reproduce_active_risk_seed_1005.py
```

2026-07-22 的 2.2 s 单 seed 结果为：10 个 D2 发布帧，航迹数
`5,6,6,5,5,5,5,5,5,5`；隔离陈旧后验 9 次、tentative 陈旧删除 1 次、统计合并 0 次，
最终保留 `GT3D-000001` 至 `GT3D-000005`，`GT3D-000006` 被删除，在线真值使用为 0。
5 个合成专项覆盖重复确认、seed 1005 等价短时重生、近邻独立目标、协方差合并边界和
异步新证据；真实 seed 专项 1 个。完整 D2 回归为 `168 passed, 1 warning in 26.15s`，
warning 仍为本机 Matplotlib `Axes3D` 环境问题。

main 于 2026-07-22 先完成 development 复跑，随后以提交 `0fa7c00` 生成 clean-tree
active-risk seeds 1000--1019 结果。clean manifest 记录 `repository_dirty=false`、源提交
统一、20/20 物理窗与配对比较可用、D4 adoption 188/188、两臂各 1960 条命令、100 条
离线唯一身份映射。seed 1005 保持 GT1-GT5 五条唯一映射，在线 truth use 0。两臂在
1 s 计划有效窗内均为 0 次 5 m 拦截；counterfactual、causal 和 production runtime ACK
仍 unavailable，因此该 clean 结果只关闭可复现集成运行，不证明降级收益或拦截效果。

## 2026-07-22 长 episode 声明治理

`Scalable3DTracker` 新增 `ObservationClaimLedgerConfig`。默认配置版本为
`d2-observation-claim-policy-v2`，包含 retention、max-count 和 max-lateness。新观测先按
`current_state_time - max_lateness` 检查是否过旧；claim 只有在
`current_state_time - max(retention, max_lateness)` 之后才可淘汰。淘汰索引使用最小堆，
旧量测即使 key 已从字典移除，也会被 admission watermark 拒绝，不能重新形成 hit 或
birth。无源量测时间的 claim 不淘汰；达到 max-count 后新证据 fail closed，内存不再增长。

逐帧 metadata 和 summary 现区分 `observation_measurement_too_old`、
`observation_identity_timestamp_conflict`、`repeated_latest_observation_id`、
`duplicate_observation_within_scan` 和 `observation_claim_ledger_overflow`。公开 ledger
summary 包含配置/schema 版本、current/peak/evicted、overflow/too-old/replay、两个水位线、
undated、eviction index、track observation reverse-index、`tombstone_count=0` 和
anti-replay mode。

乱序整帧由可选 `Scalable3DOOSMScanAdapter` 在 Tracker 前处理。它按到达顺序接收完整
common-epoch scan，在 max-lateness 水位线后按量测时间释放；超窗、早于已释放状态或缓冲
溢出的 scan 整帧拒绝。`flush()` 只用于 episode 结束后的有序排空，不做状态回溯、固定
滞后平滑或重放。

本轮新增 15 个模块测试。5 目标 x 500 帧和 40 目标 x 200 帧长期循环均满足 claim
peak 不超过配置上限、overflow=0 且发生安全淘汰。离线 benchmark 的 3/12 目标、16 帧、
0.75 m 间距分别有 43/187 条合法检测，误抑制 0、近邻召回 1.0、错误 coalescence 0、
确认延迟均值/P95 0.25/0.25 s、离线 IDSW 0；truth 只在 `step()` 后进入 evaluator。
完整 D2 回归为 `183 passed, 1 warning in 29.08s`。真实 AirSim 的 observation ID 稳定性、
时钟误差、距离/遮挡/杂波门限，以及 20/50/100/200 多规模多 seed 性能证据仍开放。
在线 `id_switch_count` 继续显式为 `None/unavailable`。

### main-owned 接入建议

main 构造 Tracker 时应显式传入并写入 manifest：

```python
tracker = Scalable3DTracker(
    observation_claim_config=ObservationClaimLedgerConfig(
        config_version="d2-observation-claim-policy-v2",
        retention_seconds=30.0,
        max_count=100_000,
        max_lateness_seconds=5.0,
    ),
    replay_coast_config=ReplayCoastConfig(
        config_version="d2-replay-coast-policy-v1",
        grace_seconds=0.5,
    ),
)
```

若 main 已保证 scan 的 state-valid `measurement_timestamp` 单调，可直接调用
`tracker.step()`。若 transport 按 arrival 顺序交付且完整 scan 可能乱序，应使用
`Scalable3DOOSMScanAdapter`。每个 `submit_scan()` 传入一个完整共同量测时刻的 scan；空
scan 必须显式传 measurement/arrival time。一次 submit 可能释放 0 到多条 result，main
应按 result 自带时间逐条发布。`flush()` 只在确认该 episode 不再有输入时调用，reset 后
重新构造 adapter/tracker，不能把 flush 当作周期性回溯更新。

在线持久化建议包括 result 的 `observation_rejection_reason_counts`、累计 reason、
`observation_claim_ledger`、eviction count/events，以及 adapter summary 的
submitted/admitted/released/rejected、current/peak scan 与 detection buffer、measurement inversion、拒绝
原因、水位线和 last released time。离线 D6 可消费 governance benchmark 的 false
suppression、nearby recall、erroneous coalescence、confirmation latency 和 offline
identity metrics；这些 truth 指标不得写回在线总线。

## 2026-07-22 重复后验短时 coast

D1 全量发布后验时，无新量测的航迹仍可能携带上一条 `latest_observation_id`。D2 继续把
这类 detection 按 `repeated_latest_observation_id` 隔离，不进入候选图、状态量测更新、
hit 或 birth。若该 claim 已绑定现存中心航迹，且当前状态时刻距航迹
`last_update_time` 不超过版本化 `ReplayCoastConfig.grace_seconds`，该航迹本帧只做常
速度预测，不增加 miss。`last_update_time` 和宽限起点不因 replay 刷新，超过宽限后立即
恢复原 miss/lost/drop 逻辑。时间冲突、过旧量测、账本溢出和未绑定 claim 均不 coast。

逐帧结果公开 `replay_coast_count/events/track_ids/reason_counts/config` 和
`missed_track_ids`；Tracker summary 公开累计 coast count、reason 和配置。coast 不增加
常驻 ledger，额外持久状态只有定长整数计数。12 目标、200 帧、雷达每 0.5 s 更新的全量
后验循环中，1920 次相邻 replay coast，所有航迹 misses 为 0，claim 仍受 max-count
约束。合并前 main 接线中的 active-risk seed 1005 曾从旧基线的 `5,6,6,5` 改为前四帧
持续 5 条航迹，9 次 replay 均未形成额外 birth 或 tentative stale drop；当前尾部合并后
该 seed 的集成 replay 为 0，见下一节。两种路径在线 truth 使用均为 0。
完整 D2 回归为 `188 passed, 1 warning in 31.03s`；warning 为既有 Matplotlib
`Axes3D` 环境提示。

## 2026-07-22 scalable 尾部合并后证据复核

main 当前在 episode 结束时仍按量测时刻逐条融合并发布 D1 尾部扫描，但只把最终融合后验
送入 D2 一次；该次更新只用于状态和审计收口，不生成相机或运动控制命令。active-risk
5v5、seed 1005、1.1 s 当前运行产生 2 个 D2 发布帧，均为 GT1-GT5 五条规范航迹。累计
birth 5、claim 10、replay quarantine/coast 0、tentative stale drop 0、coalescence 0；
D2 finalize 调用 1 次，`coalesced_release_count=5`，在线真值使用为 0。旧文档中的
`claim=26、replay=9` 属于尾部逐次调用 D2 的上一版 main 接线，不再代表当前集成行为。

D2 的 bounded replay/coast 能力没有删除。12 目标、200 帧模块 fixture 仍以 1920 次
重复后验验证宽限、超时和冲突边界。seed1005 复现报告现为
`d2.active-risk-seed1005-reproduction.v3`，接受 replay=0 或有界 replay；两种分支均要求
全部发布为 GT1-GT5、owner 为 `D2_center`、birth 5、coast 与 quarantine 一致、无 stale
drop/错误合并且在线真值使用为 0。当前 2.2 s 复跑得到 6 个五航迹帧、replay 0，
`acceptance_passed=true`。完整 D2 回归为 `189 passed, 1 warning`，未修改 D2 算法。

200v200、seed 42000、2.2 s 的最新持久化 development 制品将尾部 31 次 D2 调用合并为
1 次并记录 `coalesced_release_count=30`。常规 D2 关联 8 次共 6.135 s，尾部关联 1 次为
2.033 s；claim current/peak 为 `1583/1583`，容量 60000，overflow/too-old 0，在线真值
使用 0。`1976/1976` 来自合并前的上一份 development 制品，不能与合并后的调用次数和
时延拼接成同一结果。以上均来自脏工作树质点运行，不是 AirSim、实时性或完整 200v200
验收。

快速治理标定另运行 20/50/100/200 四个规模、每档 5 个 seed，共 20 个 development
episode，`formal_episode_count=0`。200 规模 claim current/peak 为 `24170/24170`、容量
48000、安全淘汰 2985、overflow/too-old 0；四档离线 near-neighbor recall 均为 1.0，
false suppression 和 erroneous coalescence 均为 0，在线真值使用为 0。这是专用治理
benchmark，不包含完整运动、分配、降级、视觉和制导闭环。

保留 seed 1011 和 1019 在 1.0 s 干预帧只有 4 条在线航迹，后续新鲜观测到达后终态恢复
5 条 confirmed。scalable 验收仍应以实际 D2 库存连接 D3，并单独报告相对场景目标数的
可见性缺口；不得用离线 truth 补轨或硬编码目标数。
