# D2 数据关联模块计划

## 1. 范围与安全边界

D2 只负责离线科研仿真、日志回放和多目标数据关联评估。模块目标是维护稳定的 `global_track_id`，降低多目标交叉、密集编队、短时遮挡、漏检和虚警条件下的 ID Switch 风险。

本模块不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程或绕过人工授权的能力。`engageable` 只是代码中的研究状态，表示航迹质量足以供下游离线分配实验使用，不代表授权、处置或控制含义。

规模边界必须保持清晰：2v2、5v5、`crossing_dense_5v5` 都只是 baseline fixture 或回放场景名。D2 的关联器、Tracker、metrics 和 dry-run adapter 均按每帧传入的 `tracks`、`detections`、`active_tracks` 长度运行，不从场景名推断目标数量，不把 main runtime 的 `--drone-count N` 复制成内部常量。

### 1.1 2026-07-31 正式 R0 半程计划基线

clean producer `80e55eb` 的正式 R0 已完成 shard 0-9，共 `450/900` 个 episode；D6 v12
evaluator `b6289c5` 的严格离线重聚合得到 `414/450 available`、893 次 ID Switch、
169 个非零 episode。36 个失败关闭项由 27 个一轨多真值和 9 个谱系窗外观测组成。
在线 producer 保持 `0/450 available`，真值没有进入 D2 在线路径。

本轮证据同步不修改关联器、门限、身份承诺状态机或 `0.9 s` lineage window。后续 P1
按以下顺序推进：

1. 对 27 个一轨多真值 episode 做逐帧、逐来源谱系和候选分量因果回放，区分错误合轨、
   未承诺歧义处理和生命周期接续，不用离线真值生成在线关联动作。
2. 对 9 个窗外 episode 核对 measurement、arrival、state-valid、published、D2 consume
   五类时刻及 sidecar 匹配，先定位生产调度或证据合同断点，不直接扩大时间窗。
3. 候选先在固定失败子集和相邻通过子集做新 source A/B。通过后冻结新的 execution
   plan，再运行完整 9 场景、5 规模、20 unseen seeds；不得把旧 450-cell 与新代码混合。
4. 主线晋级要求在线 truth use、规范 ID 改写和旧谱系重放均为 0；身份歧义应通过
   uncommitted/coverage 口径表达，不能形成一轨多真值映射。严格不可用项不得补零，
   局部下界不得替代严格 ID Switch。
5. 候选除提高严格证据可用性外，还需对配对 seed 报告 ID Switch、identity/coverage
   continuity、track count、RMSE 和 D2 wall time，任何一项明显退化均不准入。

## 2. 当前代码状态概览

当前 D2 可运行路径依赖 NumPy、SciPy 和 pytest。兼容默认在线工程主线仍是 `GNNHungarianAssociator` + 马氏门控 + 二维常速度 Kalman fallback + `Tracker` 生命周期状态机；2026-07-20 新增的 `Scalable3DTracker` + `Sparse3DGNNHungarianAssociator` 是显式选择的六维稀疏路径，不替换旧 replay/AirSim 默认入口。JPDA 和 MHT 已有接口兼容、可执行的研究近似，但不是完整生产级 JPDA filter 或 MHT hypothesis manager。Stone Soup、FilterPy 已有 optional 版本/原因探测、对象 adapter 和 frozen replay smoke benchmark，但不进入默认运行路径或 requirements。

代码和测试已覆盖：

- `GNNHungarianAssociator` 使用 `scipy.optimize.linear_sum_assignment` 做一对一硬关联。
- GNN/Hungarian 主线在马氏门控和 Hungarian 求解前后保留原路径，并新增速度方向、短时历史和加速度异常组成的 motion consistency cost/diagnostics。
- `build_gated_cost_matrix()` 支持 quality-aware gate baseline，按 track quality、局部目标密度、位置协方差和上一帧 association risk 对每条 track 的 gate 做轻量调整。
- `DataAssociator` 抽象接口支持替换 GNN、JPDA、MHT。
- `Tracker` 使用 `[x, y, vx, vy]` 状态、4x4 covariance、Joseph update 和确定性状态机。
- `Scalable3DTracker` 使用 `[pN,pE,pD,vN,vE,vD]` 和 6x6 covariance；位置-only
  使用 3D NED Joseph update，独立六维量测使用 6D Joseph update，相关 D1 source
  posterior 使用固定权重 CI 和速度创新 NIS 门控；`GT3D-*` 仍只由中心 D2 分配，每条
  航迹历史和逐帧审计均有配置上限。
- 六维路径新增默认关闭的
  `AmbiguityHoldLeaseConfig`。`Scalable3DTracker.step()` 以可选关键字
  `ambiguity_components=()` 消费严格的
  `d1.structural-ambiguity-evidence.v1`；有效租约冻结已绑定 `GT3D-*` 的 update/hit/
  miss/birth/rebind，只允许常速度预测和协方差传播。首版仅到期释放，不包含
  component-level JPDA、MHT 或自动改绑。侧车量测/状态有效时刻允许早于当前 D2
  扫描时刻；`max_component_age_seconds` 对延迟做有界准入，未来和超龄分量
  fail-closed。租约首次时刻与后续新证据时刻均使用 D2 消费时钟。
- D1 不透明来源适配由
  `detections3d_from_d1_global_tracks(..., use_opaque_d1_source_tokens=True)`
  显式启用，默认关闭以保持 baseline 可归因。令牌和三段式 `source_key` 严格镜像 D1
  冻结规则；原始 D1 本地 ID 只参与 SHA-256，不进入 Detection 序列化或 D2
  canonical ID。
- 六维来源绑定已从匹配后冲突记录前移为关联候选边硬掩码。已绑定来源的原边若几何
  门控失败，则输入隔离、原航迹预测且禁止 shadow birth。
- `Sparse3DGNNHungarianAssociator` 用 KD-tree 生成保守空间候选，执行 3D 位置创新马氏门控，再按稀疏二部图连通分量运行 Hungarian；不分配全局 `N_t x N_z` 代价/距离矩阵。GNN 仅表示 Global Nearest Neighbor，未在 D2 引入图神经网络。
- `TrackLifecycleState` 当前枚举为 `tentative -> confirmed -> engageable -> lost -> dropped`，没有 `engaged` 状态。
- 每条 `GlobalTrack` 输出 `track_quality`、`association_risk` 和 `quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 与 `MetricsRecorder.summary()` 同步输出 track-level 质量/风险字段。
- `MetricsRecorder.summary()` 输出 `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`truth_metrics_available`、`continuity_available`、`duplicate_assignment_count`、RMSE、confusion matrix、runtime 和关联风险字段；无 offline truth label 时 continuity 数值只为报告兼容，不参与硬风险，旧 replay 缺 availability 字段时也按不可用处理。
- `AssociationRiskSummaryWindowGenerator` 可从代价矩阵、候选数、cost margin、ID switch delta、duplicate delta、可用 continuity 和 D5 disagreement 生成滑窗风险摘要。
- `RiskThresholds` 和 `classify_risk_summary()` 已把 D2 风险证据拆为 D4 对齐的软风险与硬风险。
- `detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、2D covariance 投影、`global_track_id` 和 metadata。
- `run_airsim_dry_run_association()` 支持 synthetic AirSim-style frame，不 import `airsim`，并在 bus message 中导出当前活动航迹和 `global_track_ids`。
- `load_airsim_replay_frames()` 可读取离线 JSON/JSONL replay 并保留 wrapper 中的 seed/episode/scenario/frame/offline truth label 校准元数据，`run_airsim_replay_association()` 输出 association logs、summary、风险分层和 replay metadata，`run_threshold_sensitivity()` 输出 gate/risk threshold 敏感性矩阵、`risk_profile_version`/`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary 和软/硬风险聚合字段，`summarize_multi_seed_risk_calibration()` 汇总多 seed IDSW/continuity/duplicate/soft-hard risk 分布并给出推荐阈值摘要。
- `AssociationLogEntry` 完整携带默认空 `rejected_pairs`，replay gate summary 可分别统计 `mahalanobis_gate` 和 `assignment_above_gate`，旧 JSON 缺字段按空列表处理。
- Detection/GlobalTrack covariance 输入治理已落地：非有限、明显非对称、明显非 PSD 输入显式拒绝；仅数值容差内对称化或特征值 floor。对象与 association metadata 同时记录最新 `covariance_consistency` 和 `last_regularization` 历史证据，避免预测/更新后沿用初始化诊断。
- 测试包含 3 目标 dry-run episode，证明输出数量来自输入集合长度；同时包含 2v2 replan baseline，证明中心/二级切换时可保持稳定 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count` 的系统规则已有合同测试：D2 `MetricsRecorder.id_switch_count` 与 D6 episode 统计口径一致。
- P1 replay governance 已实现：`run_airsim_replay_association()` 默认启用在线 truth isolation；在线 detection ID 按帧匿名化，actor/truth 元数据递归清除；`OfflineTruthEvaluation` 独立计算 identity/continuity、M-of-N 初始化、false-track 和 NEES，NIS 则由不依赖真值的在线 innovation 计算。每帧 association log 固化 `d2-association-log/v2`、risk profile/version、measurement/active-track count 和 NIS availability，不携带 truth label、truth target count 或 NEES。
- P1 offline truth 合同已冻结为 `d2-offline-truth-label/v1`：每条 JSONL 记录携带 episode、frame、timestamp、truth ID、二维 position 和可选匹配注释。在线帧递归移除 truth，离线标签仅在 association 完成后恢复为 evaluator-only 视图；缺标签时 IDSW/continuity/NEES 显式 unavailable。
- P1 deterministic calibration runner 已实现：通用 N-target dense crossing fixture 覆盖连续漏检/遮挡和虚警，默认 5-target 仅为基准；runner 强制至少 10 个唯一 seed，输出每 seed 与聚合 IDSW、continuity、NIS/NEES availability、gate/risk profile/version、runtime 和确定性签名。
- P2 optional benchmark v2 已收敛：同一 frozen replay digest 下固定运行默认 GNN/Hungarian，并可显式运行模块内 JPDA/MHT research adapter 和 Stone Soup/FilterPy object adapter。GNN/JPDA/MHT 共用 `Tracker` 生命周期，truth 只在运行结束后进入 offline evaluator；每行统一输出 IDSW、continuity、latency 和 `unavailable_reason`。外部 object adapter 的身份指标保持 unavailable，完整 JPDA/MHT 和端到端 FilterPy tracker 仍声明未实现。
- P1 governed input adapter 已支持 D1 `serialize_governed_replay`：识别 manifest v1/observation v1，按 `airsim_frame_index + measurement_timestamp` 聚合，用 radar `[range, azimuth, elevation]` 和传感器 NED 外参生成水平 N/E detection/covariance；声学 bearing 和 EO pixel 记录不做错误混合，跳过统计进入报告 metadata。旧 AirSim replay loader 兼容保留。它是 P1 truth-isolated 合同边界，不是 P2 第三方库 benchmark。
- M 对 N cross-node 注册基础已实现：6D NED `SourceTrackSummary`、source-local namespace、公共时刻 CV 传播、协方差感知 track-to-track gate、按 source 分组 Hungarian、canonical multi-source binding/history、payload/lineage/stale 防重，以及 exact/unknown/duplicate 三类相关性决策。
- `CrossNodeRegistryMetrics` 保持 truth-free，只统计 operational rebind、duplicate rejection 和 latency；`OfflineCrossNodeMetricsEvaluator` 通过独立 source-key truth mapping 计算 cross-node IDSW、canonical duplicate 和 association precision/recall。
- D2 回归覆盖 D1 governed manifest/records、匿名化、radar projection、模态跳过、offline position matching、旧 replay 兼容，以及 P2 五行输出、truth-free tracker 输入、缺依赖和未知 adapter 拒绝。
- 六维专项回归覆盖 5/20/50/100/200、D 轴门控、交叉、连续漏检、虚警、truth 拒绝、
  D2 ID 所有权、离线 IDSW/continuity、有界历史和速度状态稳定性；2026-07-20 完整
  D2 为 `139 passed, 1 warning`。

### 2.1 P0/P1 缺口快照

- **P0**：无开放 blocker。GNN/Hungarian、马氏门控、可插拔 `DataAssociator`、显式 online/offline `TrackerTruthPolicy`、truthless 指标 unavailable 语义、truth-free lifecycle event 导出、risk summary、D1/AirSim adapter、按输入集合长度运行、P0-B `track_quality`/`association_risk`、motion consistency cost 和 P0-C quality-aware gate baseline 均是当前主线并已有测试覆盖。六维来源绑定在 `_update_track` 前硬掩码，同源几何不相容输入不再先污染状态。seed1005 验收已升级为允许 replay=0 或有界 replay，见第 22 节。
- **P1 合同层已闭合**：D1 governed adapter、association log schema/profile、在线 truth isolation、独立 offline evaluator、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed calibration runner、availability-aware summary、M-of-N/false-track/NIS/NEES 接口及 cross-node canonical registry 基础均已实现并回归。
- **P1 ceiling-aware 完整冻结证据已生成，长期标定仍开放**：2026-07-15 使用 2026-07-13 冻结的六档真实 D1 governed replay 离线重算，screening 为 6x10 seeds、confirmation 为 6x20 seeds；未启动 AirSim。最佳候选 `gnn-g5.99-qa1-ld3_7-mw0.5x` 把平均 IDSW 从 `1.358333` 降至 `0.616667`（下降 `54.6012%`），identity continuity 从 `0.981046` 提高至 `0.983954`，消除 `15.3448%` 的剩余错误；false-track 0、P95 `15.470 ms`、truth leakage 0。总体五项联合 gate 全部通过并形成 promotion review recommendation，但默认 GNN/Hungarian 配置不变。分档只有 clutter/combined 完整通过，其余四档因 baseline IDSW=0 fail-closed；dropout truth alignment 为 partial。更长 OOSM/遮挡/杂波 replay、gate/risk、M-of-N 生命周期、NIS/NEES 和跨节点标定仍是 P1。
- **2026-07-14 truth/lifecycle P0 收口**：`Tracker` 默认 online fail-closed，offline evaluator 显式 opt-in truth；main owner 可传入布尔型 `online_truth_isolated/online_truth_hints_used/truth_metrics_available/continuity_available`，非布尔值、身份字段和 offline truth payload 仍拒绝。truthless IDSW/continuity/RMSE 为 `None` 并带逐指标 availability/reason，truth 可用时零 IDSW 仍为 available `0`；birth/lost/drop/rebirth 计数和 transitions 由 truth-free 状态事件产生。完整回归 `98 passed, 1 warning`。本批没有调整 gate/lost/drop，`T001 -> T005` 生命周期参数标定仍为 P1。
- **2026-07-12 历史代码状态**：`33e6fa0` 只增强 main/runtime 与 D4-D7 的 PNG delivery 链路；其后的 D2-owned P1 任务增加 long governed replay runner/schema，但默认在线路径仍为 GNN/Hungarian。当时指定模块回归为 `69 passed, 1 warning`，仅作为历史阶段记录；warning 是本机 Matplotlib `Axes3D` 多版本导入问题。
- **2026-07-14 历史回归状态**：Post-batch episode 审计后当时完整 D2 模块为 `99 passed, 1 warning`。当前权威结果见第 24 节。
- **2026-07-12 AirSim 证据边界**：PNG delivery 报告记录 2v2 candidate 10 seeds 为 20/20 pair、在线 truth 使用为 0；锁定后两帧 dropout 沿原 global/local track 与计划上下文预测，没有 truth ID 或本地 ID 重写。M5N2 8 s 短窗口为 0/9，且报告明确该批次不是同几何、同时间窗的长期对照。以上证明下游身份/truth-isolation 合同未退化，但报告没有 D2 专项 association log、隔离 offline IDSW/continuity 或真实 dense/crossing 长回放，不能新增 D2 算法完成项。
- **开放 P0/P1 与下一验收**：P0 无开放项。P1 synthetic 长 replay、独立 offline truth、至少 10 seeds 的 IDSW/continuity/false-track/RMSE/NIS/NEES availability 与 risk/gate/scenario version 已闭合；首轮严格 4 m/2 m 真实 dense crossing 标定也已完成，但候选未通过完整晋级门限。性能 backlog 是扩展 OOSM/遮挡/杂波和更长时间窗，标定 gate/risk/M-of-N/false-track/NIS/NEES，并复核 continuity 改善。跨节点部分还需 D1 数值 exact/CI posterior 回写、多 seed 高歧义 replay 和 owner/epoch failover 验证。
- **2026-07-15 admission 回归与证据**：专项覆盖理论上限、完美基线、continuity 退化、缺指标、baseline IDSW=0、false-track、latency、truth leakage 和“仅 IDSW 改善”拒绝；D2 全量结果 `113 passed, 1 warning`。冻结输入的 v2 完整联合报告、中文报告和真实数据图已生成，下一步是 main/D6 对 promotion review recommendation 做跨模块评审，而不是 runner 自动改默认路径。
- **2026-07-15 M5N2 20-case 实测同步**：SimpleFlight baseline/candidate 各 10 seed，
  20/20 actual-execution case 可用；D2 association main-bus 共 3805 个可用样本，
  mean/P95/max 为 `2.521/3.147/98.942 ms`。在线 truth identity/state use 均为 0，
  因此本批在线 IDSW/continuity 保持 unavailable，不能用 0 补齐。第二 primary
  `0/20` 进入 5 m 且最终均为 `collision_stop`，但未写盘碰撞对象，不能据此新增 D2
  根因或修改关联参数。该批关闭“同一 M5N2 运行时 D2 阶段时延无实测”的证据项，仍不
  关闭带离线真值的真实身份连续性、duplicate-source/teleport/clutter/dropout 扰动和
  owner/epoch failover 标定。`TERM` 前额外完成的 `png_ttc_2v2_seed001` 被排除，
  dropout case 为 0。
- **历史基线，2026-07-10**：当时的 5v5 60-case 和 2v2 10-seed 不是 D2 dense/crossing 真值回放，因而在当时不足以关闭 D2 P1。本段不代表当前状态。
- **历史过渡证据，2026-07-11 早期**：truth-isolated 短 episode 及 seeds 7/17/27 当时只证明 D2 -> D3/D6 通路与单 primary 合同收敛，T001 双 primary 尚未通过。本段不是当前结论。
- **2026-07-11 合同验收证据**：M=5、N=2 ComputerVision 的 T001 双 primary 共识/计划授权为 8/10；`id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。二级与完全分布式 commit 正例通过，缺 ACK 时 fail-closed；这验证下游使用 D2 中心 ID 的合同，不表示 D2 本地重绑 ID。
- **P2 边界保持原状态**：P2 仅是隔离 benchmark；模块内 JPDA/MHT 是显式研究近似，Stone Soup 1.9.1/FilterPy 1.4.5 仅对象 adapter smoke，默认在线 GNN 路径未替换。
- **2026-07-20 六维局部基线闭合**：D2-owned 六维 CV、3D 马氏门控、空间索引、稀疏分量 Hungarian、truth-free 在线合同和离线身份评分已实现；main-owned episode-bus 接入、真实多 seed 标定和极端高密度预算仍开放。
- **2026-07-23 歧义保持候选状态**：D1 v1 侧车、不可逆来源令牌、三段式
  `source_key`、观测预留、软/硬租约、prediction-only 不变式、epoch 回退拒绝和
  关联前 binding freeze 已在 D2 模块实现。延迟侧车按
  `D2消费时刻 - D1 state-valid时刻` 做有界年龄准入，开发默认上限为 `1.0 s`。
  完整回归为 `271 passed, 1 warning in 28.82s`。合同和模块不变式已实现，配置与
  adapter 均默认关闭。
- **2026-07-23 main 单 seed 门槛已执行，候选拒绝**：固定提交 `9cd2a79`、
  nominal 200v200、seed 1100、2.2 s、`recon_count=2` 的候选实际消费 D1 evidence
  `46/46`，7 次 D2 消费共接受 33 个 component event，阻止 hit/miss/birth
  `69/69/4`。D2 航迹 `203 -> 201`、D3 分配 `200 -> 197`，映射
  `1566 available + 230 unavailable -> 1492 + 294`，RTF
  `0.2245 -> 0.2112`。候选离线身份评分因
  `source_observation_outside_lineage_window` 不可用，不能把缺失值解释为零或与
  baseline IDSW `9`、track/identity continuity `0.865`、coverage continuity
  `0.870` 比较。在线 truth use 为 0。
- **seed 1100 拒绝时的下一门槛**：默认 `enabled=False` 保持，停止 seeds
  1101/1102。当时确定先定义歧义保活帧的可评分谱系合同：
  `identity_uncommitted/ambiguity_hold` 必须与普通
  `lineage_missing` 分开统计，候选观测在身份未承诺期间不得硬分给
  `global_track_id`。评估器应保留这类区间及分母/availability 审计，但不得把它计成
  正确身份或 IDSW。合同冻结后再用实测 evidence age 联合校准当前 `0.9 s` lineage
  window 与 soft/hard lease，并定位航迹数、映射可用性和 D3 分配退化。仅放宽
  `0.9 s` window 禁止作为准入修复。完成后先复跑同一 seed 1100；只有指标口径有效、
  业务可用性不退化且预注册联合门槛通过，才进入未见 seed 和长时实验。
- **2026-07-23 D2-owned 合同增量已完成**：新增
  `d2.identity-evidence-commitment.v2` 和
  `d2.scalable3d_identity_evidence.v2`。六维 tracker 跨 soft/hard lease expiry
  保存 `identity_uncommitted_after_hold`。每条受影响航迹持久化歧义 observation key
  阻断集合和最大 component measurement timestamp；claim reservation 释放不删除该
  历史。恢复还要求新 key、source 时刻严格晚于水位线、本扫描首次 accepted original
  claim、零 replay、零活动 lease、truth-free `target_candidate` disposition，以及
  `当前 D2 tracker frame timestamp - 原始 source measurement timestamp` 不超过版本化
  发布新鲜度预算。
  未提交候选在状态更新前撤回，不进入 hit、claim binding 或 `detection_to_track`。
- **容量与公开边界**：`IdentityCommitmentRecoveryConfig` 默认限制每航迹 2048 个阻断
  key、全局 250000 个。未溢出状态可在合法恢复后清理；溢出保持 fail-closed，只在永久
  drop 后清理。配置 schema 为 `d2.identity-commitment-recovery-config.v2`，默认启用
  `0.9 s` 发布新鲜度门控；显式关闭仅用于旧水位线/replay 行为兼容。公开 DTO 只携带
  blocker count、水位线和 overflow，不携带 key。`known_false_alarm/unknown` 必须由不
  读取离线 truth sidecar 的上游传感器处置产生。
- **本轮验收边界**：D2 完整模块回归为 `291 passed, 1 warning in 29.05s`，专项另覆盖
  37 目标动态规模、旧候选 key 在 reservation 释放后重入、同水位线新 key、严格更晚
  新 key、晚于水位线但发布超龄继续未提交、后续合格证据恢复、Detection 与 tracker
  frame 不一致拒绝、兼容关闭、未来来源时刻拒绝、容量溢出和 v2 审计重算。该结果完成
  D2-owned typed payload、状态迁移和 evaluator 语义。
- **2026-07-23 evaluator v2 审计已完成**：
  `d2.scalable3d_identity_evaluation.v2` 嵌入受 evidence bundle SHA-256 约束的
  `identity_evidence_records`，并由每条 `IdentityEvidenceCommitment` 重算 all-record
  与 created/matched observed-record 两套承诺分母、reason counts、恢复阻断器数量、
  水位线年龄和 overflow。loader 对聚合篡改、负水位线年龄和未提交候选/来源绑定失败
  关闭。v1 继续输出 legacy unavailable/`None`。
- **发布新鲜度修复后的 clean seed 1100 已执行**：main 与 D6 在配置谱系绑定后的
  clean 提交 `ff881316243ff5a2991a4659ab78637ed625d123` 复跑 nominal 200v200、2.2 s、
  `recon_count=2`。baseline 为 D2 航迹 203、D3 分配 200、strict IDSW 9、track
  continuity `0.865`、coverage continuity `0.870`、承诺覆盖率 `1.0`。candidate 为
  D2 航迹 201、D3 分配 197、strict IDSW 3、track continuity `0.8266667`、coverage
  continuity `0.8283333`、all-record commitment coverage `0.9574706212`。
- **配置谱系已闭合**：baseline/candidate 的 9 条 D2 发布均使用承诺 schema/policy
  `d2.identity-evidence-commitment.v2` /
  `d2-structural-ambiguity-commitment-v2`。集成配置
  `main-scalable3d-identity-recovery-publication-freshness-v1` 的规范化 SHA-256 为
  `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`；
  manifest v2 已验证逐发布一致性并绑定原始 D2 JSONL。该集成版本与 D2 单模块默认
  `d2-identity-recovery-publication-freshness-v2` 名称不同，但 schema、`0.9 s` 预算和
  fail-closed 行为一致，文档不得混写两类配置来源。
- **合同修复通过，算法候选仍拒绝**：candidate 1787 条记录中 committed 1711、
  active hold 69、after hold 7。三条恢复被发布新鲜度门控阻断，严格身份指标恢复可用；
  未提交 source/candidate binding violation 均为 0，online truth use 为 0，
  duplicate assignment 为 0。IDSW 改善不能抵消 D2/D3 数量及两项 continuity 退化。
  固定 `0.9 s` 不扩大，候选保持默认关闭；seeds 1101/1102、10 s 和 20-seed 矩阵停止。

## 3. 输入输出合同

### 3.1 D2 输入

兼容基线的核心输入仍是二维 `Detection`：

- `detection_id`：单帧观测 ID。
- `timestamp`：量测时间，适配 D1 时来自 `measurement_timestamp`。
- `position`：二维位置或三维 NED 的水平投影 `[north, east]` / `[x, y]`。
- `covariance`：2x2 量测协方差；D1 6x6 或 AirSim-style 3x3 covariance 会投影到二维。D2 对投影后实际参与门控的 covariance 执行有限性、对称性和 PSD 校验，容差内修复必须留诊断。
- `truth_id`：仅用于离线评估和 D6 指标，不应作为在线身份决策依据。
- `feature`：可选外观、类别、声纹或其他 embedding，当前用简单欧氏差异参与代价。
- `metadata`：保留来源、frame、timestamp、truth_position、`global_track_id` 等调试和回放信息。

六维路径输入为不含 truth 字段的 `Detection3D`：3D NED 位置、3x3 位置协方差、双时间戳、置信度，以及可选速度/速度协方差和 namespaced source key。元数据递归拒绝 truth/actor/object/entity、上游 canonical ID；D1 fused-track adapter 使用 state-valid timestamp 作为关联 epoch，并保留原始 source measurement/arrival timestamp。原始 radar 球坐标和 visual pixel 必须先由 D1 投影或融合。

结构歧义候选另接受 `AmbiguityComponent3D` 或其公开 mapping。D1 侧车必须携带
`publisher_node_id/publisher_epoch`、分量 generation、双时间戳、NED member
state/covariance、不可逆 observation evidence key、完整 candidate edges 和
prediction-only 治理字段。D2 不 import D1 私有类，不接受原始 observation ID，
不把 D1 `global_track_id` 作为 canonical ID。发布者缺 epoch 的兼容仅存在于显式
Detection adapter：使用 `d1-default-epoch-v1` 并记录 defaulted；公开侧车缺 epoch
直接拒绝。D1 的 `measurement_timestamp == state_valid_timestamp` 保持原值；D2
允许该时刻早于当前 tracker epoch，但不允许来自未来或超过
`max_component_age_seconds`。默认 `1.0 s` 仅是当前 main 时序预算下的开发值，
正式配置需覆盖已标定的 D1 scan lateness 与传输延迟。原 arrival/published 时刻不参与
租约重定时，只进入审计；soft/hard deadline 从 D2 首次消费和新鲜证据消费时刻起算。

结构歧义候选启用时，D2 每帧另输出
`d2.identity-evidence-commitment.v2`。字段固定包含 `global_track_id`、
`association_state`、`identity_commitment_state/reason`、状态时刻、量测/到达双时间戳、
commitment/component/evidence generation、publisher node/epoch、active lease key、
soft/hard deadline、expiry、recovery blocker count、measurement watermark 和 overflow。
阻断 key 是 D2 私有状态，不进入 payload。`identity_uncommitted_ambiguity_hold` 与
`identity_uncommitted_after_hold` 均不得携带 source observation evidence key。main
生成 `d2.scalable3d_identity_evidence.v2` 时也必须把该帧
`source_observations` 置空；只有 `committed` 的 observed frame 才可携带实际接受的原始
观测谱系。普通 v1 producer 可继续使用原 schema，但不能伪装成 v2。

D2 Tracker 假设每次输入是共同量测时刻且调用顺序单调；直接遇到乱序 scan 仍 fail
closed。模块已提供前置 `Scalable3DOOSMScanAdapter` 对有界迟到的完整 scan 做排序；原始
异步量测回溯、已更新状态重放和平滑仍属于 D1/main 集成或后续研究责任。

### 3.2 D2 输出

D2 输出包括兼容 `GlobalTrack`、六维 `GlobalTrack3D`、`AssociationResult`、`AssociationLogEntry` 和 metrics summary：

- `GlobalTrack.global_track_id`：D2 维护的稳定身份键。
- `GlobalTrack.state`：当前实现固定为 `[x, y, vx, vy]`。
- `GlobalTrack.covariance`：4x4 状态协方差。
- `GlobalTrack3D.state/covariance`：固定 `[pN,pE,pD,vN,vE,vD]` 与 6x6；只由 D2 tracker 创建 `global_track_id`。
- `GlobalTrack.lifecycle_state`：`tentative/confirmed/engageable/lost/dropped`。
- `GlobalTrack.track_quality` / `association_risk` / `quality_metadata`：D2-owned track-level 质量、关联风险和解释字段。
- `AssociationResult.matched_pairs`：`(track_id, detection_id, cost, probability)`。
- `AssociationResult.unmatched_track_ids` / `unmatched_detection_ids`：漏配和新建轨迹依据。
- `AssociationResult.ambiguity_score`、`rejected_pairs`、`metadata`：解释门控拒绝、候选数量、covariance consistency、motion consistency、quality-aware gate、track quality/risk、求解器、JPDA/MHT 截断等信息；`AssociationLogEntry` 必须保留同一 `rejected_pairs`。
- `MetricsRecorder.summary()`：D2/D6 必须保留的 `id_switch_count`，以及 continuity 数值与可用性标志、duplicate、risk、runtime、confusion matrix。

`global_track_ids` 导出列表必须来自当前活动航迹集合，不按 2 或 5 个目标预分配、截断或补齐。真实 replay 默认使用在线/离线双层合同：在线层将源 detection ID 匿名化且不含 truth，离线层按同帧输入顺序对齐匿名 detection、标签和 truth state，并在关联结束后计算评估指标。

## 4. 已实现能力

### 4.1 GNN/Hungarian 主线

`GNNHungarianAssociator` 是默认工程路径。它先调用 `build_gated_cost_matrix()` 计算 `N x M` 代价矩阵，其中 `N=len(active_tracks)`，`M=len(detections)`；门外候选使用大代价并记录 `RejectedPair(reason="mahalanobis_gate")`。随后通过 SciPy Hungarian 求解一对一最小代价匹配，匹配后仍会拒绝超门限 pair。

已输出的解释信息包括：

- `cost_matrix` 和 `distance_matrix`。
- `motion_consistency_cost_matrix`、`motion_consistency_by_pair` 和 `motion_consistency_by_track`。
- `gate_thresholds_by_track`、`target_density_by_track`、`pre_association_track_quality_by_track` 和 `previous_association_risk_by_track`。
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
- `track_continuity`：当前是 `identity_continuity` 的别名，表示身份连续性；仅当 `continuity_available=true` 时可解释和参与风险阈值。
- `identity_continuity`：真值存在期间由同一身份稳定覆盖的比例。
- `coverage_continuity`：真值存在期间是否被任意航迹覆盖。
- `duplicate_assignment_count`：同帧重复 detection/track 或同一 truth 被多个 track 覆盖。
- `rmse`：位置误差，仅作为几何精度指标，不能替代身份指标。
- `confusion_matrix`：truth-to-track 分布。
- `runtime_seconds_by_associator`：算法耗时。

风险摘要已经有代码基线：`AssociationRiskSummaryWindowGenerator` 从候选重叠、cost margin、ID switch delta、duplicate assignment delta、continuity risk、D5 disagreement 和 metadata 生成 `AssociationRiskSummary`，并进入 `AssociationLogEntry` 与 summary 字段。`classify_risk_summary()` 使用 `RiskThresholds` 将软风险（ambiguity/cost margin/candidate overlap/D5 disagreement）和硬风险（IDSW、duplicate、continuity collapse）分层输出，供 D4/D6 回放标定使用。

### 4.5 N 规模输入与 dry-run bus 输出

D2 已有非 2/5 数量测试：3 目标 synthetic AirSim-style dry-run episode 产生 3 个活动航迹和 3 个 `global_track_ids`。这证明 `global_track_id` 输出数量由输入帧和 Tracker 状态决定，而不是由场景名决定。

2v2 active-degradation/replan 测试是身份合同 baseline：中心到二级节点切换时，如果同一 replay episode 使用同一个 Tracker 状态，D2 应通过关联和 Kalman update 保持同一 physical target 的 `global_track_id`，并保持 `id_switch_count == 0`。

### 4.6 AirSim-style replay 与阈值敏感性 helper

D2 侧 P1 已补离线 replay 读写和阈值敏感性 helper：

- `load_airsim_replay_frames(path)` 读取 JSON/JSONL，支持顶层 frame、`frames` 数组以及混合 episode JSONL 中的 `frame`/`d2_frame`/`airsim_frame` payload，并把 wrapper/top-level 中的 `seed`、`episode_id`、`scenario_name`、`drone_count` 等校准字段保留为 `replay_metadata`。
- `run_airsim_replay_association(frames, gate_thresholds=...)` 复用现有 Tracker，输出 `ReplayAssociationReport`，其中包含 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、association logs、当前 `global_track_ids`、`replay_metadata` 和软/硬风险摘要。
- `ReplayAssociationReport.risk_summary` 和 `threshold_sensitivity` rows 稳定输出 `association_risk_threshold_version`、gate pass/reject count、motion consistency risk summary、track quality/association risk summary；`threshold_sensitivity_summary` 汇总 dense/crossing 场景标签、IDSW、continuity、duplicate 和 soft/hard risk frame rate 分布，便于 D6 bundle 做真实 5v5 replay 分组。
- `write_replay_association_report()` 与 `write_association_logs_jsonl()` 固化 D2-owned report/log 输出格式，便于 main/D6 后续消费。
- `run_threshold_sensitivity()` 对 gate threshold 与 risk threshold profile 做离线 sweep，逐项输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`、`association_risk_threshold_version`、seed/episode/scenario/frame 元数据、gate/motion/quality diagnostics、soft/hard risk frame count、max risk score 和 risk summary。
- `summarize_multi_seed_risk_calibration()` 汇总多个 seed/episode 的 threshold sensitivity rows，按 gate/risk profile/version 输出 IDSW、continuity、duplicate、soft/hard risk count/rate/score 分布、dense/crossing sensitivity summary、风险原因集合和推荐阈值摘要。
- `OfflineTruthLabel`、`write/load_offline_truth_labels_jsonl()` 与 `evaluation_frames_with_offline_truth()` 固化独立 truth 文件，并让 `run_airsim_replay_association(..., offline_truth_labels=...)` 在在线关联完成后复用原 evaluator。
- `run_dense_crossing_calibration()` 复用上述 replay/evaluator/risk summary，强制至少 10 个唯一 seed，并通过 `summarize_dense_crossing_calibration()` 显式统计 available/unavailable seed。
- `load_airsim_replay_frames()` 在旧 frame schema 前识别 D1 governed bundle；转换后的 online frame 不携带 observation ID、lineage 或 truth，离线 `offline_only` labels 仅在 evaluator 副本中用位置 Hungarian 建立评分映射。
- `tests/test_replay.py` 与 `tests/test_calibration.py` 覆盖 5 目标 AirSim-like replay、动态 N、truth JSONL round-trip/隔离、阈值版本、无 truth availability、同 seed 复现和 10-seed 聚合。

该 helper 不连接 AirSim runtime，也不从场景名推断目标数量；真实 ComputerVision 图像/metadata 采集、episode JSONL 生产和跨模块 schema 发布仍由 main/runtime/D6 负责。

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

IMM、EKF、UKF 目前是研究计划项，不是已落地代码。D2 的 `Tracker` 只有二维线性常速度 Kalman fallback。`to_filterpy_state()` 和 `filterpy_filter_from_detection()` 只映射二维 CV `KalmanFilter` 并用于对象更新 smoke，不实现 IMM、EKF、UKF 或端到端关联。

如果后续证明机动预测误差是 ID Switch 主因，应先定义三维 NED 或二维机动模型、量测模型、协方差合同和评估场景，再决定是否接入 FilterPy 或自研 IMM/EKF/UKF。

## 6. 隔离式外部库状态

### 6.1 Stone Soup Detection adapter

`to_stonesoup_detection()` 已把在线安全的 D2 `Detection` 映射为 Stone Soup `Detection/StateVector`。`run_optional_framework_benchmark()` 可在 frozen replay 上测量转换 latency；隔离环境 Stone Soup 1.9.1 已实测执行成功。当前没有 Stone Soup `Track`、predictor/updater、JPDA 或 MHT tracker，因此 adapter 行不得输出 IDSW/continuity 数值。

暂未接入原因：

- 默认回归需要保持 NumPy/SciPy/pytest 轻依赖。
- 不希望把 Stone Soup 对象暴露到跨模块总线。
- D2 先固化 `DataAssociator`、`AssociationResult`、metrics 和 D1/D6 合同，再做外部框架对照。
- 尚缺真实多 seed AirSim CV replay、密集交叉和遮挡 sweep 来证明完整 JPDA/MHT 的收益。

缺少条件：

- Stone Soup predictor/updater、Track 生命周期和完整关联器映射。
- 完整 JPDA/MHT 的状态混合、假设管理、剪枝和同预算验收。
- 真实 replay 数据集、truth labels、容差和对照报告。

### 6.2 FilterPy CV object adapter

当前已创建 FilterPy `KalmanFilter` CV 对象 adapter，可从 D2 `GlobalTrack` 或 `Detection` 初始化，并在 benchmark 中执行 predict/update；隔离环境 FilterPy 1.4.5 已实测成功。它没有替换 D2 Tracker，也不维护跨帧关联身份，所以 IDSW/continuity 保持 unavailable。`ExtendedKalmanFilter`、`UnscentedKalmanFilter` 和 `IMMEstimator` 仍未实现。

暂未接入原因：

- 当前二维常速度 Kalman fallback 足以支撑 phase-1 数据关联、状态机和指标验证。
- EKF/UKF/IMM 需要更明确的机动目标模型、非线性量测模型和三维/二维状态选择。
- 引入 FilterPy 会增加依赖和参数面，若没有证明 IDSW 改善，容易增加维护成本。

缺少条件：

- CV/CA/CT 或其他机动模型集。
- 模型转移概率和协方差初始化策略。
- 雷达球坐标、相机投影或三维 NED 量测雅可比/无迹变换定义。
- 与 GNN/JPDA/MHT 共同评估的机动场景。

### 6.3 其他未实现或待集成项

- 原生 3D NED 的 D2-owned 稀疏基线已实现；尚未完成 main-owned scalable episode bus 自动编排、版本化跨模块输出、真实多 seed 标定和最坏情况大连通分量预算。
- JPDA/MHT 自动升级：当前由仿真 CLI 或调用方显式选择 associator，`Tracker` 内没有按风险阈值自动切换。
- 真实 AirSim runtime 采集链路：D2 已能消费离线 JSON/JSONL AirSim-like replay 并输出 association report/log，但不接 AirSim SDK、不采集 ComputerVision 图像/metadata，也不负责 main/D6 episode JSONL 生产。
- OOSM 回溯和平滑：前置 adapter 已能排序有界迟到的完整 scan，但不回溯或平滑已更新
  状态。
- py-motmetrics/CLEAR MOT：仅可作为未来离线评估参考，当前未作为依赖或测试路径。

## 7. D2 输出如何供 D3/D4/D5/D6 使用

### 7.1 D3

D3 用 `global_track_id`、状态、协方差和 lifecycle state 构造资源-目标分配输入。D2 应向 D3 暴露当前活动航迹集合；D3 应优先消费 `confirmed` 和 `engageable`，对 `tentative`、长期 `lost`、高风险或高歧义航迹提高代价、延迟分配或等待重评估。

D2 不生成 D3 `AssignmentPlan`，也不修改分配版本。D3 的 versioned plan 和 stale version rejection 仍由 D3 负责。

### 7.2 D4

D4 不直接使用 D2 结果切换系统模式，而是把 D2 的 `AssociationRiskSummary`、`id_switch_count`、continuity、duplicate risk、D5 disagreement 和 source/link metadata 作为主动降级证据。D2 只发布风险证据，例如 `association_ambiguity`、`duplicate_track_risk`、`covariance_overlap_rate`；是否请求中心重规划、二级节点接管或分布式协同由 D4 综合 D1/D3/D5 信号仲裁。

2026-07-07 的 main runtime bus / D4 P1 修复后，D2 风险证据在 D4 中应按以下分层解释：

- **软风险证据**：`association_ambiguity`、cost margin risk、candidate overlap、短时 D5 disagreement。它们表示当前硬关联不确定，默认只支持继续观察、提高 D3 迟滞、请求二级节点 cue 或进入离线 JPDA/MHT 对照，不应单帧触发 `request_center_replan`。
- **硬风险证据**：`id_switch_count` 或窗口 delta 大于 0、`duplicate_assignment_count`/`duplicate_track_risk` 增长、`track_continuity` 低于阈值。这些说明规范 `global_track_id` 连续性已经受损或重复解释已经发生，可作为 D4 主动仲裁的硬证据。
- **D2 边界**：D2 不知道 D3 plan 是否过期，也不判断 D5 末端锁定是否授权。D2 只把上述证据写入 summary/log；D4 再结合 D1、D3、D5 和通信/二级节点状态选择 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary` 或 `degrade_to_distributed`。

### 7.3 D5

D5 使用 `global_track_id` 将中心航迹投影到终端相机或局部目标候选上。D5 可以回传 `TerminalAssociation`、`IdentityClaim`、候选 ID、末端不一致和锁定/保持状态作为弱证据。D5 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。如果 D5 与中心预测长期冲突，D2 只应降低身份置信或提高风险摘要，不能直接用终端真值重命名全局航迹。

### 7.4 D6

D6 消费 D2 association logs、state transitions、summary 和 confusion matrix 做系统级评估。D2 和 D6 必须显式保留 `id_switch_count` 规则：D2 内部 IDSW 与 D6 episode IDSW 口径需要一致，不能只用 RMSE 或覆盖率替代身份连续性。当前已有 D2/D6 合同测试验证同一 truth 的代表 `global_track_id` 变化会被两侧计为 ID Switch。

main runtime 的 P1 D4/D5 calibration sweep 已接入 D6 标准报告 bundle，因此 D2 后续输出应优先对齐该报告入口：每个真实 5v5 replay 需要携带 `seed`、`episode_id`、`scenario_name`、`frame_index`、`drone_count`/`target_count`、gate threshold、`risk_profile`、`risk_profile_version`、association logs、D2 summary 和 offline truth labels。D2 不生成 D6 bundle，也不连接 AirSim SDK；D2 只保证其 report/log 字段可被 D6 分组统计。

## 8. 剩余风险

### 8.1 多目标交叉

GNN 是硬关联，交叉帧的最优/次优代价 margin 可能很小。一旦硬判决选错，后续 Kalman update 会把错误观测吸收到航迹状态中，导致 ID Switch。JPDA/MHT 能提供对照，但当前 JPDA 没有完整概率状态混合，MHT 没有完整多帧确认策略，因此不能宣称已彻底解决交叉身份交换。

### 8.2 密集编队

密集编队中多条航迹共享门内候选，协方差椭圆重叠，`candidate_counts_by_track` 和 `candidate_counts_by_detection` 会升高。当前特征代价只是简单向量差异，若来源特征不稳定或不具备区分力，GNN 仍可能在平行近距目标间交换 ID。

### 8.3 ID Switch 评估风险

`id_switch_count` 依赖离线 `truth_id`。真实/在线路径没有 truth label 时，只能通过 D2 风险摘要、D5 disagreement、confusion-like replay label 和 D6 离线评估分析身份风险。文档和报告不得把线上无 truth 的风险摘要等同于真实 IDSW ground truth。

### 8.4 N 规模性能风险

虽然 D2 不写死 2v2/5v5，算法复杂度仍随输入规模增长。旧二维 GNN 分配全矩阵，Hungarian 求解约为 `O(max(N,M)^3)`；新六维路径通常按 KD-tree 候选图分量求解，但极端全重叠目标仍可能形成单个稠密分量。JPDA 联合假设枚举和 MHT 分支扩展仍可能组合爆炸，更大 N 的高歧义路径需要预算、截断和标定。

## 9. 下一步

当前顺序为：维护已闭合的 P1 replay/truth/D1-governed 合同和 synthetic runner，复用 2026-07-13 strict 4 m/2 m 各 20-seed 真实基线扩展 OOSM、遮挡、杂波和生命周期参数标定。P2 保持隔离 benchmark，不得反向改写默认 GNN/Hungarian 路径、默认依赖或跨模块总线合同。

### P1 闭合维护与后续标定

1. **维护冻结合同**：main/runtime 输出不含 truth 的 governed detection/timestamp/covariance，并单独输出 `d2-offline-truth-label/v1`；D2 持续回归匿名化、availability 和 evaluator-only 评分。
2. **继续真实 dense/crossing 标定**：首轮 strict 4 m/2 m 各 20 seeds 已完成；后续专项数据集继续固化 gate threshold、`risk_profile_version`、`association_risk_threshold_version` 和 IDSW 判定版本，由 D6 汇总 IDSW、continuity、duplicate 及软/硬风险误报漏报。候选必须同时满足全部冻结门限，不能只凭 IDSW 改善晋级。
3. **标定 N/M 初始化**：对 confirmation hits、miss tolerance 和 birth/deletion 参数做网格实验，输出初始化延迟、false track rate、漏建轨率和重复航迹率，并按目标密度与漏检率分层。
4. **补齐 NIS/NEES 统计一致性**：NIS 使用量测创新与创新协方差，NEES 仅在离线 truth state 可用时计算；输出置信区间内比例和按传感器/距离/场景分组的偏离原因，不把 covariance 输入合法性等同于统计一致性。
5. **开展 adaptive gate / JPDA 受控对照**：在同一 replay、seed 和计算预算下比较固定/quality-aware/完整 adaptive gate，以及 GNN/Hungarian/当前 JPDA 对照；验收同时报告 IDSW、continuity、false track、漏关联、延迟和假设截断，GNN 仍为默认主线。

P1 闭合证据区分两层：在线层只使用 innovation、候选重叠、cost margin、duplicate 和质量风险等可观测量；离线层使用隔离 truth labels 计算 IDSW、identity/coverage continuity、NEES 和 hard-risk 漏报率。2026-07-11 CV 10-seed 的 IDSW=0 是离线评分结论，不应与无 truth 的在线 `d2_hard_risk_frame_rate=0.0` 混淆；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW 评分。2026-07-13 strict 4 m/2 m 评分使用独立 evaluator truth，在线 truth leakage 为 0。

### P2

- 将已实现的六维稀疏 D2 路径接入 main-owned `scalable_3d_simulation` bus，冻结输出 schema、模型版本、延迟预算和 D1/D3/D5 消费合同；接入前旧默认路径不变。
- **已完成 benchmark 合同**：v2 固定 frozen replay digest，默认 GNN baseline 与可选 JPDA/MHT research adapter 走同一 Tracker/offline evaluator；Stone Soup/FilterPy object adapter 按依赖可用性执行。五类结果统一输出 IDSW、continuity、latency 和 `unavailable_reason`，并回归在线输入无 truth。
- **未完成的 P2 增强**：Stone Soup 完整 JPDA/MHT、FilterPy EKF/UKF/IMM、optional 端到端 tracker 及其 IDSW/continuity 对照；模块内轻量 JPDA/MHT 仍只是研究近似，不能当作这些完整算法已实现。
- 设计 JPDA/MHT 自动升级策略，但必须包含切换迟滞、D4/D6 阈值认可和回放证据，避免算法抖动。
- P2 只在隔离 research environment 和冻结 replay 上执行；当前 Stone Soup/FilterPy 只是 adapter smoke，模块内 JPDA/MHT 只是研究近似。optional import/API/metric 失败时必须填写 `unavailable_reason`，不能静默回退或写成完整 tracker benchmark。

### P3

- 在多 seed replay 证明收益后，再考虑生产级 MHT 分簇、N-scan pruning 或外部框架适配。
- 若 D5 多视角反馈稳定可用，再把末端关联作为低权重身份证据接入 D2 风险模型；仍不得让 D5 改写 `global_track_id`。

## 10. 验收命令

从仓库根目录运行：

```bash
git diff --check -- research_modules/d2_data_association subagent_reviews/D2_*
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

## 11. M 对 N 协同拦截下的跨平台航迹融合研究计划

专项调研见 `subagent_reviews/D2_M_TO_N_TRACK_FUSION_REVIEW.md`。结论是：多个拦截节点观测同一高威胁目标时，多个 local tracks 只能登记为同一 canonical `global_track_id` 的多源证据，不能解释为多个目标，也不能让 `k_j=3` 的资源需求复制三条全局航迹。

该能力不改变当前 detection-to-track GNN/Hungarian P0 主线。已闭合的中心注册基础如下：

1. **已实现**：带 source/local/epoch namespace、两个 timestamp、6D NED state/covariance、quality、lineage、correlation status 和 canonical hints 的 `SourceTrackSummary`；source hint 不具备身份权威。
2. **已实现**：公共融合时刻传播、covariance-aware track-to-track Mahalanobis gate、按 source 节点分组的 Hungarian，以及 `global_track_id -> source tracklets` binding/history；测试覆盖 1/2/3/N source、异步、交叉、重复、local ID 冲突和 canonical continuity。
3. **已实现决策边界**：known cross-covariance 输出 exact correlated fusion request，unknown correlation 只输出 CI request，duplicate payload/lineage 直接拒绝。数值 CI/相关融合继续由 D1 owner 实现。
4. **已实现指标基础**：online cross-node rebind IDSW、duplicate payload rejection、fusion latency，以及隔离 offline truth 下的 canonical duplicate 和 association precision/recall。
5. **后续研究**：高歧义跨节点 JPDA/MHT、多 seed 同时/序贯/混合 replay、D2 owner/epoch failover、通信字节和 D1/D6 数值融合一致性 NEES/ANEES。D4 二级/分布式 commit 正例通过不等于 D2 owner failover 已实现。
6. **保持隔离**：Stone Soup 只作为 track-to-track association/CI benchmark，不把第三方对象写入跨模块总线。

当前已落地 `canonical_duplicate_count`、`cross_node_id_switch_count`、track-to-track association precision/recall、重复消息拒绝数和融合延迟。fusion NEES/ANEES 与通信字节仍待 D1/D6/replay 集成；所有 cross-node 指标都不能与合法的多资源协同或 D3 `duplicate_assignment_count` 混为一谈。

## 12. 2026-07-12 P1 长 Replay 实施状态

本轮已增加 `d2-governed-long-replay/v1` 校准路径，默认生成至少 40 帧、
推荐 120 帧的动态 N 目标 governed replay。场景包含重复密集交叉、交叉窗口
遮挡、周期漏检、近场虚警和人为延迟到达；runner 要求至少 10 个唯一 seed。

实施原则如下：

1. 默认关联器保持 GNN/Hungarian，JPDA/MHT 继续只在 optional benchmark 中运行。
2. D1/main 负责原始量测 OOSM 和跨模块时钟治理；D2 Tracker 按 measurement time 有序
   关联，必要时由 D2 前置 whole-scan adapter 对有界 arrival inversion 排序。该 adapter
   不能误写成 `dt=0` fallback、状态回溯或固定滞后平滑。
3. 在线帧递归剥离 truth，离线 `d2-offline-truth-label/v1` 只在关联完成后评分。
4. 每 seed 固化 scenario/gate/risk/profile version，并输出 IDSW、identity/coverage
   continuity、false-track、RMSE、NIS/NEES availability、runtime 和 truth leakage。
5. `global_track_id_owner=d2_center` 是报告合同；source detection/local identity
   不能成为规范 ID，N/M 变化也不能触发固定长度补齐或截断。

该 synthetic long replay 入口关闭的是 D2-owned 可重复校准工具缺口，不等于真实
AirSim 长 replay 已完成参数冻结。真实 replay 仍需 main 提供 governed frames 和
隔离 truth，D6 按相同 schema 做长期趋势和阈值验收。

## 13. P1 身份连续性固定矩阵

当前 `d2-p1-identity-calibration/v2` 把分散参数实验固化为两阶段流程：

1. 10 个唯一 seed 上运行 54 个 GNN/Hungarian 配置：3 个马氏门限、quality-aware
   off/on、3 组 lost/drop 生命周期和 3 个 motion weight 倍数。
2. 按 IDSW、identity continuity、false-track、p95 loop latency 的固定顺序选择
   最佳 GNN；默认 baseline 始终是 `9.21/on/2-5/1.0x`。
3. 轻量 JPDA 只复用最佳 GNN 的 frozen replay/truth digest、gate 和生命周期，作为
   research adapter 对照，不进入默认在线路径。
4. 20 个唯一 seed 上只确认 baseline、最佳 GNN 和 JPDA。缺输入时确认和准入均为
   unavailable，不生成 synthetic 替代结果。
5. 联合准入要求 IDSW 下降至少 30%；identity continuity 使用
   `H=max(0,1-C_b)`、`Delta_req=min(0.10,0.10H)` 的 ceiling-aware 判据且禁止退化；
   false-track 增幅不超过 10%；p95 不超过冻结预算；baseline/candidate truth
   leakage 均为 0。任一指标缺失均 fail-closed。通过只表示可提交主线升级评审；
   runner 自身始终保持默认 GNN/Hungarian 不变。

输出逐 seed 和聚合 IDSW、identity/coverage continuity、false-track、RMSE、
NIS/NEES availability、初始化延迟、p95 loop latency、truth leakage 及输入 digest。
当前 D2-owned 接口和回归已闭合。2026-07-13 已由 main 采集 nominal 4 m 与 tight
2 m 各 20 seeds 的真实 D1 replay 并执行确认；结果只能作为该冻结场景的参数证据，
不能外推为所有 AirSim 场景或把单元测试 fixture 写成真实标定结果。

### 13.1 D1 Offline Truth Sidecar 对接

P1 manifest loader 已支持 D1 freeze 的 `offline_truth.json`。适配顺序固定为：先把
D1 governed observation bundle 转成不含 truth 的在线 D2 frames，再单独读取
`d1.airsim_offline_truth.v1`，校验 evaluator-only、NED、时间和身份/位置完整性，最后
按 timestamp 映射 frame 并创建 D2 `OfflineTruthLabel`。同一 timestamp 多 frame 时
仅允许用 `source_payload_index == frame_index` 消歧，否则 fail closed。

D2 只使用 N/E 位置做二维离线匹配；D1 Down 坐标保留为 annotation，不能进入在线
Detection、GlobalTrack 或 association log。`.jsonl` 仍只接受原生 D2 truth label；
未知 suffix/schema 不做猜测。端到端回归覆盖 D1 governed radar replay、D1 JSON
sidecar、offline evaluator 指标可用和在线 truth leakage 为 0。

### 13.2 AirSim 证据来源治理

`airsim_evidence` 按来源合同分类：保留 legacy `airsim`，并接受 main 冻结流程生成的
`real_airsim_*` 受治理标识。分类结果在 GNN screening、GNN confirmation 与 JPDA
同输入对照中统一复用；普通 synthetic 标签即使包含 `airsim` 子串也保持 false。
该修复不改变 54 组矩阵、默认 GNN/Hungarian、固定阈值、准入策略或 online truth
隔离边界。

### 13.3 六档高难度身份连续性校准

D2 已支持 main 冻结的 `nominal/tight_crossing/dropout/clutter/delayed_noisy/combined`
六档 replay。D2 不生成 AirSim 场景，也不读取在线 truth；场景注入参数作为受治理
`difficulty_metadata` 随 case 进入 manifest。混合套件按 `(difficulty, seed)` 唯一，
允许六档使用相同 seed，并按档检查 10-seed screening 数量；`combined` 可单独提供
20-seed confirmation。

54 组 GNN 矩阵和轻量 JPDA 均输出总体与分档聚合。分档摘要包含 IDSW、continuity、
false-track、RMSE、latency 和 admission；若所有算法仍为零 IDSW 和满 continuity，
结果标为 `scenario_still_non_discriminative`，不提出 promotion。下一步由 main 生成
六档真实 AirSim replay 并冻结实际注入参数，D2 只运行同输入校准和结果治理。

### 13.4 Governed replay 离线压力变换

D2 现提供 deterministic、truth-free transformer，直接处理 D1 governed observation
records，不读取 evaluator truth sidecar。dropout 删除中段雷达观测，clutter 注入匿名
雷达虚警，delayed/noisy 只改变雷达到达时间和协方差，combined 顺序组合三类压力；
其他模态原样保留。所有新增/改变记录都保留双时间戳、协方差、source lineage，并以
`injected_evaluator_scenario` 记录 profile、seed 和实际参数。

`tight_crossing` 不做几何变换，只验证 main 的约 2 m 捕获声明；nominal 和三个单压力
profile 验证约 4 m，combined 验证约 2 m。若 D1 manifest 已声明 spacing，二者必须
一致。main 后续只需调用 transformer、写入 result payload，并把 profile metadata/
digest 放入已有 P1 manifest；D2 仍不负责 AirSim 场景生成。

### 13.5 Spacing provenance 收口

D1 loader 已透传 `target_spacing_m` 与离线压力 profile。真实 AirSim 校准 case 必须
提供可追溯 spacing：nominal/单压力约 4 m，tight/combined 约 2 m；缺失、跨来源数值
冲突或档位冲突均 fail closed。suite 仍按 `(difficulty, seed)` 治理，随机注入的实际
参数允许逐 seed 变化，同档只冻结 profile/schema/version 等不变量。该修复只加强输入
证据治理，不改变 54 组矩阵、promotion 门限、JPDA research-only 或默认 GNN。

### 13.6 稀疏 Governed Replay Truth 对齐

D1 sidecar 可保留全部 AirSim truth 帧，而 D2 governed replay 仅包含存在匿名观测的
时刻。D2 因此采用严格稀疏对齐：只接受冻结 `1e-9 s` 时间容差内可唯一映射的 frame；
缺 frame 的合法 truth 样本计入 unmatched 并从 evaluator label 集合排除，不使用最近邻。
case、screening/confirmation 和分档结果均报告 alignment availability 与 unmatched 数。
无 label 时 truth 指标保持 unavailable；非法或歧义输入继续 fail closed。

## 14. 2026-07-13 Strict 4 m/2 m 真实标定结论

### 14.1 冻结证据

- nominal 4 m 与 tight 2 m 均使用真实 D1 governed replay，各 `20` 个唯一 seed。
- 最佳 GNN 候选的平均 IDSW 为 `1.3583 -> 0.6167`，下降 `54.6%`。
- identity continuity 为 `0.9810 -> 0.9840`，只提高 `0.0030`。
- P95 loop latency 为 `24 ms`。
- online truth leakage 为 `0`；truth 只在关联结束后进入离线 evaluator。
- truth 对齐只接受 `1e-9 s` 内的 exact match。没有严格对应 frame 的样本保留为
  `partial/unmatched` 审计项，不使用最近邻补齐，也不伪造 truth label。

### 14.2 选型决定

v1 冻结规则曾要求 continuity 绝对提高 `0.10`，因此历史结论把该候选判为不通过。
2026-07-15 的完整 v2 报告现已证明总体候选五项联合 gate 全部通过，并给出
`promotion_recommended=true`；其中 `H=0.018954`、`Delta_req=0.001895`、实际
`Delta=0.002908`，消除约 `15.3448%` 的剩余错误。该结论只是评审建议，分档仍有四档
因 baseline IDSW=0 fail-closed。轻量 JPDA 在同输入对照中发生退化，不能作为主线候选。
默认在线关联器和参数继续保持 GNN/Hungarian；JPDA、
MHT、Stone Soup/FilterPy 仅保留为 P2 optional/offline benchmark，不进入默认依赖、
在线切换策略或跨模块合同。

### 14.3 后续任务边界

- **P1 开放**：增加更长时窗、OOSM、遮挡、漏检和杂波组合的真实 replay；按分档
  标定 gate/risk、M-of-N、false-track、NIS/NEES，并验证 continuity 是否有稳定改善。
- **P1 跨节点开放**：继续验证高歧义 canonical registration、owner/epoch failover，
  并由 D1/D6 完成 exact/CI posterior 与 NEES/ANEES 闭环。
- **P2 optional**：完整 JPDA/MHT、Stone Soup 端到端 tracker、FilterPy EKF/UKF/IMM
  和六维路径的高机动/非线性升级只做隔离对照；没有同预算、同 replay 的明确收益不得
  替换规则 GNN/Hungarian。

### 14.4 权威回归状态

2026-07-13 当时 D2 模块完整回归为 `93 passed`。文档前部保留的 `69 passed,
1 warning` 是 2026-07-12 历史阶段结果，不代表当前测试规模。本机 Matplotlib
`Axes3D` warning 不影响 D2 关联主线、身份指标、truth isolation 或本轮标定结论。

## 15. D1 来源航迹谱系治理与真实复跑计划

### 15.1 已完成实现

1. `GlobalTrack` 保存可多对一归并的 `source_track_ids`，仅表示 D1 上游航迹谱系。
2. 默认 GNN/Hungarian 在既有马氏门限和运动代价后增加来源连续性代价；同源候选
   优先于同门内的新来源，但新来源在唯一可行时仍可更新既有规范航迹。
3. 在线 Tracker 对门内影子观测抑制即时 birth；对仍绑定活动规范航迹、但超出
   来源门限的同源 teleport 输入隔离并输出 `source_lineage_governance` 诊断。
4. 不读取 truth/actor ID，不写死目标数，不改变 JPDA/MHT research-only 定位，
   不改变 D2 对 `global_track_id` 的中心所有权。

### 15.2 验证和后续责任

- 2026-07-14 已审计 1 个真实 Blocks seed、351 帧，并以 4 帧匿名来源谱系 fixture
  验证修复；验收为 2 条目标只保留 2 个规范 ID、1 次影子抑制、1 次大跳隔离，结果
  通过。完整 D2 回归为 `99 passed`。
- main 已按同配置完成 seed 1 baseline/candidate 复跑；D2 只产生 `T001/T002`，
  `birth=2` 且 `lost/drop/rebirth=0`，未复现 `T008`。2026-07-15 又完成
  baseline/candidate 各 10 seed 的普通 M5N2 运行并获得 D2 时延，但该批没有冻结 D2
  offline identity 评分或显式来源扰动。下一步转为针对性比较 birth/drop、最大活动
  航迹数、计划版本、pair churn 和离线身份指标，而不是单纯增加普通 seed 数量。
- D1 owner 负责消除 `global_track_002/003` 跨模态重复与 D1 状态 teleport；main/D3
  负责只把满足下游质量合同的航迹送入分配。D2 不跨模块修改这两处。
- 若真实复跑仍发生合法近距新目标被 shadow suppression 延迟初始化，应按冻结回放
  标定来源连续性权重与抑制窗口，不得使用目标真值调参。

### 15.3 Post-batch 单 seed 结论与下一验收

- 证据日期：2026-07-14；场景：真实 Blocks M5N2；样本：baseline/candidate 各 1 seed，
  分别 142/141 帧。
- 在线验收通过：最大活动规范航迹数 2，唯一 ID 仅 `T001/T002`，两组均
  `birth=2, lost=0, drop=0, rebirth=0`，未出现 `T008`，来源绑定保持一一稳定。
- 在线 IDSW/continuity 继续 unavailable；独立 sidecar evaluator 对 governed replay
  得到两组 IDSW 0、continuity 1.0、false track 0、truth leakage 0。main 实际 track
  records 的离线裁决 continuity 为 0.985915/0.985816，缺口只来自启动前 2 帧。
- 本批没有触发 shadow suppression 或 teleport quarantine，因此只关闭同 seed 的
  `T008` 复发问题。2026-07-15 的后续 20-case 已满足普通 M5N2 的 seed 数和 D2 时延
  采样，但同样没有这些显式扰动，也没有该批 offline IDSW/continuity 评分。
- 下一批验收不再以“至少 10 个普通 seed”为目标，而是冻结至少 10 个带
  duplicate source、source teleport、dropout、clutter 和合法新目标的受治理 case；
  要求每 seed 最大活动规范航迹数不超过离线真实目标数加已裁决新目标数，非裁决膨胀
  为 0，在线 truth leakage 为 0，离线 IDSW/continuity 均 available。候选仍须通过
  既有多指标 admission，不能因任一单 seed 零 IDSW 自动晋级。

### 15.4 2026-07-15 Ceiling-aware v2 冻结证据状态

- 6x10 screening 和 6x20 confirmation 已离线完成，耗时 `2501.32 s`，未启动 AirSim。
- 总体候选 `gnn-g5.99-qa1-ld3_7-mw0.5x` 的五项联合 gate 均通过，形成
  `promotion_recommended=true`；默认路径仍为 baseline GNN/Hungarian。
- 分档 clutter/combined 通过，其余四档 baseline IDSW=0 fail-closed；dropout truth
  alignment partial。后续计划是跨模块评审该混合证据及继续长 replay/lifecycle 标定，
  不是由 D2 runner 自动切换参数。

## 16. 2026-07-16 来源身份治理指标收口

### 16.1 已实现合同

1. 保持现有 GNN/Hungarian、马氏门控和 source-lineage governance，不建立独立的
   pixel/local tracker，也不复制 D5 `bright_hungarian`。
2. 每帧从 D2 自身产生的 `source_binding_conflicts` 与 `quarantined_sources` 累计
   `source_binding_conflict_count` 和 `source_lineage_quarantine_count`。
3. `upstream_local_identity_rejection_count` 只从验证后的 frame metadata 累计：
   缺失为 0，值必须是非布尔的非负整数；非法值在 tracker 状态变化前拒绝。
4. 三项计数进入 metrics、association risk、replay report、threshold sensitivity、
   多 seed group、dense/long calibration per-seed/aggregate 和 P1 identity calibration
   聚合；`id_switch_count` 的 availability 与显式字段保持不变。
5. 三项计数只审计来源身份风险，不创建观测/航迹、不重命名或重绑中心
   `global_track_id`，也不直接改变现有 soft/hard risk 阈值结果。

### 16.2 验证、完成状态与剩余计划

- 验证日期 2026-07-16；专项场景为连续 namespaced source、同一 source 集合跨两个
  canonical track 的 binding conflict、绑定来源 Mahalanobis discontinuity、零检测
  upstream rejection、5 类非法 metadata 和 legacy missing metadata。
- 两个 3-frame synthetic replay seed 的精确结果为 conflict `1/1`、quarantine
  `1/1`、upstream rejection `2/4`，聚合均值 `1/1/3`；旧流程三项均为 0。
- 验收门限是专项精确计数、非法 metadata 零 tracker/metrics 副作用以及全量测试零失败；
  结果 `123 passed, 1 warning`，warning 为环境 Matplotlib `Axes3D`，不影响合同。
- 本项关闭“来源治理只有明细、没有显式累计指标”和“上游本地身份塌缩拒绝无法进入
  D2 replay 审计”的 D2-owned 缺口。真实 AirSim 至少 10 个显式扰动 case、
  false-suppression/recall 与独立 offline IDSW/continuity 仍为 P1；main/D1 仍负责提供
  namespaced `source_track_ids` 和可信 frame-level rejection count。

## 17. 2026-07-20 六维稀疏 200 目标路径

### 17.1 已实现

1. `Detection3D` 在线 DTO 不含 truth 字段，保留 NED 位置、3x3 covariance、
   measurement/arrival timestamp、置信度及可选速度；D1 source posterior 额外保留
   完整 6x6 covariance 和 position-velocity cross block。DTO 递归拒绝 evaluator、
   actor、object、entity 和上游 canonical identity。
2. `GlobalTrack3D` 与 `Scalable3DTracker` 固定状态顺序
   `[pN,pE,pD,vN,vE,vD]`，执行三维 CV 预测；相关 source posterior 走 6D covariance
   intersection，独立六维量测走 Joseph update，位置-only 输入保留 3D Joseph update。
   新 `GT3D-*` 只由 D2 tracker 分配，D1 对象的 `global_track_id` 在 adapter 中被忽略。
3. `Sparse3DGNNHungarianAssociator` 使用 KD-tree 保守查询半径、三维位置创新马氏门控、
   有限速度一致性代价及二部候选图连通分量 Hungarian。速度创新 NIS 超门时通过
   covariance inflation 降权，不拒绝位置门内 pair。GNN 的含义固定为 Global Nearest
   Neighbor；`graph_neural_network_used=false`。
4. `AssociationResult` 不保存全密集 cost/distance matrix，显式输出候选边、潜在全对、
   空间裁剪、分量矩阵元素、阶段耗时和风险摘要。track history 与 frame log 均为有界。
5. 在线 summary 保留 `id_switch_count`、continuity 字段但值为 `None + unavailable`；
   `Sparse3DOfflineEvaluator` 仅在在线关联完成后消费独立 truth label，计算可用的
   IDSW、identity/coverage continuity、duplicate 和 false-alarm assignment。

### 17.2 验证证据

- 日期：2026-07-20；原六维专项 13 个，加 3 个速度稳定性专项，覆盖规模
  5/20/50/100/200、三维 D 轴门控、crossing、两帧连续漏检、15 个虚警、truth
  fail-closed、upstream ID 非权威、有界历史、完整 covariance、速度离群值和多帧噪声。
- 验收阈值：全部规模匹配数等于输入目标数；无固定 2/5 shape；在线 truth 字段使用为
  0；交叉/漏检/虚警离线 IDSW 为 0；全量测试零失败。结果：`139 passed, 1 warning`；
  warning 仅为环境 Matplotlib `Axes3D`。
- 200 目标性能采样：确定性三维规则网格，单进程，3 个独立 trial，每个 trial 预热
  1 帧后测量 30 帧。90 个测量帧的候选边均为 `200/40,000`，component matrix pair
  `200`，peak component pair `1`，裁剪率 `99.5%`。聚合关联 mean/P50/P95/max 为
  `6.683/6.306/7.056/22.471 ms`；tracker step 为
  `25.491/25.016/26.797/41.613 ms`。

### 17.3 剩余缺口

- 本次性能数据只有一个确定性布局和 3 x 30 个连续帧，不是多 seed 置信区间、实时 SLA、
  真实 AirSim 或 200v200 全链路证据。
- main-owned `scalable_3d_simulation` 已提供 D1/D2/D3 六维 point-mass 只读运行诊断；
  修复后 50v50/200v200 复跑、版本化跨模块输出和多 seed 端到端验收仍由 main 负责。
- 极端全重叠或过度膨胀协方差可形成大连通分量，仍需候选预算/分区策略与召回率联合
  标定；六维 JPDA/MHT、OOSM 回溯/平滑、EKF/UKF/IMM 和 learned association 均未实现。

### 17.4 速度状态稳定性收口与下一验收

- **触发证据**：main 只读 50v50、seed 17、2.2 s、radar-only 中，D1 速度
  P50/P90/max `6.28/12.16/21.03 m/s`、Pvv trace
  `101.24/110.31/112.32`；旧 D2 变为 `8.89/17.43/27.49 m/s`、trace
  `62.95/69.37/70.86`。D2 定位为完整 covariance 丢失及相关 posterior 被重复按独立
  位置量测消费，不是 D3 reachability 或场景速度上限问题。
- **已实现**：D1 adapter 传递完整 6x6 covariance；相关 source posterior 使用
  `correlated_state_ci_track_weight=0.5` 的 CI；速度创新 NIS 超过三自由度 99% 门限时
  按 `NIS/gate` 膨胀速度 covariance；关联速度代价在同一门限处封顶。位置 3D 马氏
  gate、稀疏候选、中心 ID 和 truth isolation 均不变，没有按速度模长硬限速。
- **50 条验收**：seed 17、12 帧、0.2 s 周期。匿名输入速度 P50/P90/max
  `5.415/7.960/12.274 m/s`；旧 D2 复现 `9.41/14.31/21.88 m/s`、trace `62.76`；
  修复后 `5.082/6.401/7.218 m/s`、trace `101.181`。最终位置 RMSE
  `52.634 -> 48.364 m`，离线 IDSW 0、continuity 1.0。
- **200 条验收**：seed 41、10 帧、0.2 s 周期；更新帧 candidate/dense pair
  `200/40,000`，活动航迹 200，输入/输出速度 P90 `8.097/5.980 m/s`，输入/输出 Pvv
  trace 中位数 `75/69.685`，离线 IDSW 0、continuity 1.0。seed 29 的 21 帧双目标
  crossing 加一次速度离群值后同样 IDSW 0、continuity 1.0。
- **未关闭**：固定 CI weight `0.5` 只是一致性 baseline，不能写为最优。下一验收至少
  20 个未见 seed，联合扫描 CI 权重、不同 position-velocity correlation、量测频率、
  加速度/转弯和漏检；在线报告六维 velocity NIS coverage，独立 offline evaluator
  报告六维 NEES coverage。main 修复后 50v50/200v200 和 D3 reachability 复跑也必须
  单独报告，不能由本模块合成结果代替。

## 18. 2026-07-20 evaluator-only global-track truth 合同

### 18.1 D2-owned 已实现

1. 冻结 `d2.scalable3d_identity_evidence.v1`：每条 frame/global-track evidence 明示
   lifecycle、association state、source observation lineage、measurement timestamp、
   replay generation 和所引用的 D1/D2 record sequence，不含 truth。
2. 冻结 observation truth、逐帧 mapping、identity metrics 和 evaluation artifact 的
   `v1` schema；writer/loader 使用确定性 JSON/JSONL，输出并验证 `sha256:` digest。
3. 文件 evaluator 绑定 D1 online records、D2 online records、association evidence 和
   独立 truth sidecar。除 schema/hash/sequence/truth-isolation 外，还逐项验证 D1 lineage
   与 D2 frame/canonical ID/六维 state/6x6 covariance/lifecycle/association，并要求
   evidence 覆盖完整 D2 track-frame 集合；任一失败即 fail closed，语义证据不完整时
   生成 `ambiguous/unavailable`，而不是猜测或抛出伪零。
4. 支持一对多/多对一、同帧和跨帧 lineage 冲突、显式 replay generation、缺标签、
   truth label 冲突、frame/measurement 时间窗、birth/lost/drop/rebirth 生命周期。
5. 只对完整验证 mapping 计算 `id_switch_count`、track/identity/coverage continuity、
   `duplicate_truth_to_track_count` 和 confusion matrix；first-assignment、稳定帧和 duplicate
   口径与 `MetricsRecorder` 专项对照一致。

### 18.2 验证与后续接线

- 新增 23 个合同测试；完整结果 `162 passed, 1 warning in 30.63s`，验收为零失败、
  unavailable 不得填 0、规模按输入长度。本轮没有 AirSim 或正式 seed 性能运行。
- main 需为每条 evidence 提供 `episode_id/frame_index/frame_timestamp/global_track_id/`
  `lifecycle_state/association_state/source_observations[]/d1_record_sequences/`
  `d2_record_sequence`；每个 source observation 必须有
  `observation_id/measurement_timestamp/source_lineage/replay_generation`，且 lineage 最后
  一项为 observation ID。只发布本帧实际关联证据；累计历史重复使用必须递增 replay
  generation。
- main episode manifest 需保存 evidence bundle SHA-256；bundle 自身绑定 D1、D2、truth
  三个源文件 SHA-256。D6 后续只加载 public evaluation artifact：legacy evidence
  使用 `d2.scalable3d_identity_evaluation.v1`，identity commitment evidence 使用
  `d2.scalable3d_identity_evaluation.v2`；两者都不得解析 tracker 私有 metadata。
- main 当前 `_identity_evidence_records()` 会跳过无 lineage 的 D2 track/frame，与完整性
  校验不一致；需保留这些记录并以 unavailable/unassigned 语义发布，不能通过删行得到
  假可用 IDSW。
- 本项关闭“D2 没有可审计 global-track-to-truth 离线映射及 availability identity metrics
  合同”的模块缺口。main producer 接线、D6 汇总字段、真实多 seed IDSW/continuity 与
  阈值性能结论仍开放，不能因合成合同测试通过而升级。

## 19. 2026-07-22 陈旧 D1 后验和短时重生治理

### 19.1 问题和判据

active-risk 5v5 seed 1005 在 0.439 s 由 5 条航迹扩张为 6 条。新增航迹后续每帧接收
状态时刻不同、但 `latest_observation_id` 始终相同的 D1 预测后验，因此旧确认门把同一
观测重复计成多次命中。`GT3D-000004/000006` 空间相距超过 1 km，宽空间合并既不能
解释来源，也会增加近邻真实目标误合并风险。

本轮冻结以下 truth-free 规则：

1. D2 只把 opaque observation ID 与传感器 namespace 用作新鲜度证据，不解析 ID
   内容，不读取 actor、object 或 target truth。
2. 同一 observation key 只允许第一次进入关联；后续 state-valid posterior 继续作为
   D1 预测输出审计，但不再形成 D2 hit。
3. 同 key 的源量测时间变化超过 `1e-6 s` 时按 identity/timestamp conflict 隔离。
4. tentative 第一次漏配保持 tentative，连续第二次仍无新证据时 dropped。该规则保留
   seed 1005 中旧 `GT3D-000004` 的短时重获，同时清除错误 `GT3D-000006`。
5. 合并要求共享 observation/source 证据，并同时通过三维位置和三维速度 99% 卡方门。
   双方同帧都有新证据时禁止合并。survivor 先看生命周期成熟度，再选更早创建、命中
   更多、ID 字典序更小的中心航迹；不重命名 survivor。

### 19.2 已完成实现和证据

- `Scalable3DTracker.step()` 在预测和 GNN/Hungarian 前完成 fresh/replay 分区。
- 每帧 metadata 输出输入/新鲜/不可判定/隔离数量、replay generation、claimed track、
  时间冲突、合并事件、survivor policy 和 suppressed birth；summary 累计隔离、冲突、
  tentative 删除与合并计数，并继续显式输出 `id_switch_count` availability。
- 5 个模块专项验证陈旧重放无法确认、旧 ID 重获、近邻独立目标不合并、共享来源的
  协方差门边界和新 OOSM posterior 单次接纳。
- 真实 point-mass active-risk 5v5 seed 1005、2.2 s、10 个 D2 发布帧的航迹数为
  `5,6,6,5,5,5,5,5,5,5`；隔离 9 次，tentative stale drop 1 次，最终 5 条 confirmed，
  `GT3D-000004` 保留，`GT3D-000006` 删除，online truth use 0。
- 验证日期 2026-07-22；完整命令结果 `168 passed, 1 warning in 26.15s`。验收阈值为
  seed 等价输入不形成重复 confirmed、近邻独立目标不误合并、在线真值使用为 0、
  `id_switch_count` 字段不消失和完整回归零失败，全部通过。

### 19.3 集成状态

1. **clean 集成复跑已闭合**：main 以提交 `0fa7c00` 运行 active-risk seeds
   1000--1019。manifest 为 `repository_dirty=false`，20/20 物理窗和配对比较可用，D4
   adoption 188/188，两臂各 1960 条命令，100 条离线唯一映射。1 s 有效窗内两臂均无
   5 m 拦截；counterfactual、causal、production runtime ACK 仍 unavailable。
2. **总线持久化已闭合**：`d2-observation-evidence-governance-v1` 已覆盖原 v1
   fresh/replay、timestamp conflict、coalescence、suppressed births 和 tentative stale
   drop。main 下一步需要向同一版本治理记录追加 v2 ledger/OOSM 公开 summary，不应读取
   Tracker 私有字典。
3. **证据边界保持**：clean 结果证明运行来源可复现和现有合同非退化，不证明拦截收益、
   AirSim 阈值或 200v200 完整验收。

## 20. 长 episode claim 与整帧 OOSM P1 收口

### 20.1 已实现

1. `ObservationClaimLedgerConfig` 冻结 config/schema version、retention、max-count、
   max-lateness。admission watermark 独立拒绝过旧量测；safe eviction watermark 同时满足
   retention 和 max-lateness。
2. claim 字典、per-track observation 反向索引和最小堆均受 max-count 约束。安全淘汰后
   旧 source measurement time 仍由 admission watermark 阻断；无时间戳 claim 不冒险
   淘汰，容量满时新证据按 overflow fail closed。
3. 逐帧和累计 reason 分开统计 too-old、key timestamp conflict、replay、within-scan
   duplicate 和 overflow。summary 显式给出 current/peak/evicted、undated、两个水位线、
   eviction index、tombstone=0 和 anti-replay mode。
4. `Scalable3DOOSMScanAdapter` 对整帧执行有界缓冲、量测时间排序和水位线释放。Tracker
   自身仍拒绝倒序 `step()`；adapter 超窗、早于已释放状态、arrival regression 和 buffer
   overflow 均 fail closed，不实现 rewind 或 fixed-lag smoothing。
5. 离线 benchmark 在 online `step()` 后连接 truth sidecar，统计合法新目标 false
   suppression、近邻独立目标 recall、错误 coalescence、confirmation latency 和 IDSW。

### 20.2 模块验收

- 2026-07-22 新增 15 个测试，完整 D2 为 `183 passed, 1 warning in 29.08s`。
- 5 目标 x 500 帧、40 目标 x 200 帧长期循环均满足 peak/current 不超过 `6N`、overflow 0、
  安全 evicted 大于 0；算法不从场景名或 2v2/5v5 推断 N。
- 3/12 目标离线 benchmark 各运行 16 帧、间距 0.75 m，合法检测 43/187，false
  suppression 0、recall 1.0、错误 coalescence 0、确认延迟均值/P95 0.25/0.25 s、IDSW 0。
- 四个整帧 OOSM 测试覆盖有界 inversion 排序、超 max-lateness、buffer overflow 和已释放
  状态边界；所有 Tracker state timestamp 单调。

### 20.3 下一验收

1. main 按公开 config/summary 接入 scalable episode bus，分别冻结 D1 状态有效时间、底层
   source measurement time、scan arrival time 和 adapter max-lateness，不将三者合并。
2. 在真实 AirSim replay 上标定 observation ID 唯一性、时钟误差、迟到分布、buffer 上限、
   距离/遮挡/杂波门限和 false suppression；本轮确定性 fixture 不能替代该证据。
3. 对 20/50/100/200 目标和至少 20 个未见 seed 运行长期场景，报告 claim 峰值、overflow、
   OOSM 拒绝、recall、false merge、confirmation latency、IDSW/continuity 和循环延迟。
4. `tentative_drop_miss_threshold=2`、两个 99% coalescence gate、默认 30 s/100000/5 s
   ledger 参数仍是 baseline，不作为 AirSim 或 200v200 冻结值。

## 21. 重复全量后验 replay coast

### 21.1 已实现

1. 新增版本化 `ReplayCoastConfig`，默认 grace 为 0.5 s。资格只来自
   `repeated_latest_observation_id`、已绑定现存航迹和 `state_time-last_update_time <= grace`。
2. replay detection 仍被 quarantine。coast 只跳过本帧 miss，不做量测更新、不增加 hit、
   不建 birth，也不刷新 `last_update_time`，因此不能靠持续重放无限保活。
3. 同 key 时间冲突、too-old、ledger overflow、未绑定或已 dropped 航迹、超过 grace 均
   fail closed，继续原 miss/lost/drop 路径。同一航迹本帧出现非 replay 冲突时不 coast。
4. result、risk metadata、frame log 和 summary 已公开 coast count、reason、配置、事件和
   实际 missed track；默认 GNN/Hungarian、中心 ID owner 与在线 truth 隔离不变。

### 21.2 验收与后续

- 5 个新增专项覆盖跨帧重复后验、超时后 miss、时间冲突、版本校验和 12 目标 200 帧
  长循环。12 目标 fixture 的 1920 次 bounded replay 均不增加 hit、birth 或 miss；这是
  当前 D2-owned coast 机制的独立证据。
- main 已在 scalable bus 显式传入 coast 配置并持久化公开字段。尾部扫描现在先由 D1
  完成融合，只把最终后验送 D2 一次，因此某个集成 episode 的 replay 合法为 0，不能把
  `replay>0` 作为所有 main 场景的固定验收条件。
- 真实 AirSim 仍需按 D1 发布率、雷达更新周期和时钟偏差标定 grace。grace 必须有上界，
  不得通过放大该值替代传感器失联判定。

## 22. scalable 尾部合并后验收

### 22.1 已完成

1. 复现 active-risk seed 1005 的 1.1 s 当前路径。main 产生 1 个常规 D2 帧和 1 个
   episode-finalize D2 帧，二者均为 5 条航迹；累计 birth 5、claim 10、
   quarantine/coast 0、tentative stale drop 0、coalescence 0，最终 5 条 confirmed。
   finalize 只调用 D2 一次并合并 5 条尾部释放，不用于控制。
2. 复现保留 seeds 1000--1019。seed 1011/1019 的干预时刻 1.0 s 只有 4 条在线航迹，
   根因是首个雷达扫描各漏检一个目标，后续完整新鲜扫描在干预帧之后到达；两例终态均为
   5 条 confirmed，未出现 D2 误抑制、错误删除或真值使用。
3. seed1005 复现报告升级为 v3，接受 replay=0 或有界 replay，并同时检查五条规范中心
   航迹、owner、birth、coast/quarantine 一致性、stale drop、错误合并和在线 truth。当前
   2.2 s 路径得到 6 个五航迹帧、birth 5、replay 0、在线 truth 0；完整 D2 为
   `189 passed, 1 warning`，关联算法未修改。

### 22.2 main 后续验收

1. seed 1005 不固定发布帧数量；至少检查发布非空、每帧规范 ID 唯一、最终 confirmed、
   birth=5、quarantine 与 coast 审计一致、在线真值使用为 0。`replay=0` 和 bounded
   replay 都是合法分支，取决于上游是否在调用 D2 前合并重复后验。
2. 干预源以实际 D2 航迹数为在线库存。要求 target identity bridge 与该库存一一对应，
   `intervention_global_tracks <= target_count`，并把差额记为当前不可观测或未建轨，不得用
   truth 填充。
3. 真实 AirSim 和长期多 seed 仍需评估漏检后的建轨延迟、干预帧可用率和航迹连续性；该
   P1 标定不通过放宽 replay grace 或硬编码目标数解决。

## 23. 多规模治理证据

1. main 的 200v200、seed 42000、2.2 s 质点制品把尾部 31 次 D2 调用合并为 1 次，记录
   `coalesced_release_count=30`。最新持久化制品的常规/尾部 D2 时延分别为 6.135/2.033 s，
   claim current/peak 为 `1583/1583`、容量 60000、overflow/too-old 0、online truth 0。
   合并前制品的 `1976/1976` 只作历史对照，不与新制品混报。
2. 快速治理初跑的 development 数值已由提交
   `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上的 formal/clean 批次复核。
   20/50/100/200 各 5 个唯一 seed，共 20/20 formal episode；manifest 均为
   `repository_dirty=false` 并绑定该提交。输入清单中 60 个关键制品哈希全部匹配。
3. 四档 claim peak/capacity 为 2390/4800、6020/12000、12070/24000、24170/48000；
   safe evicted 为 285/735/1485/2985，overflow/too-old 全为 0。评估侧近邻召回率
   为 1.0，误抑制/错误合并为 0，确认延迟均值/P95 为 0.25/0.25 s，在线真值使用 0。
4. 该批次关闭 clean 来源的四规模治理复跑。仍需用更多未见 seed、代表性漏检/
   遮挡/杂波/OOSM 分布和独立身份标签验证 IDSW/continuity。该批次不是
   AirSim、实时 SLA 或完整 200v200 感知到物理拦截验收。

## 24. 200 规模关联热路径收敛

### 24.1 已完成

- 冻结 clean 基线 `nominal/200v200` seeds 42000--42004，并以同配置、同离线真值
  sidecar 运行候选；每个 episode 含 8 个常规 D2 周期和 1 个 finalize 周期。
- 通过 `cProfile` 定位到真实热点是递归 metadata 身份审计和 adapter 重复扫描，不是
  稀疏 Hungarian。实施有界键分类缓存、原生前后缀判断和一次冗余预扫描删除。
- 新增版本化比较器，分别哈希完整 D2 发布、关联、规范 ID/生命周期、claim/审计和
  逐周期记录，并校验场景配置及离线 truth sidecar 的 SHA-256。
- 45/45 周期全部语义哈希一致，在线 truth use 为 0。GNN/Hungarian、三维门控、中心
  ID、claim ledger、生命周期和显式 IDSW/continuity unavailable 语义未改变。

### 24.2 性能结果

- 常规关联平均累计墙钟 `7.5552 -> 2.2033 s`，加速 `3.429x`。
- finalize 平均累计墙钟 `2.2747 -> 0.5646 s`，加速 `4.029x`。
- 单 episode D2 合计均值 `9.8299 -> 2.7679 s`，五 seed 总墙钟
  `49.1497 -> 13.8397 s`，总体加速 `3.551x`。

### 24.3 后续边界

本轮性能任务到此收敛，不继续调整算法。候选仍需由 main 在 clean-tree、固定运行环境下
复跑后才能晋级。后续性能证据应覆盖极端大连通分量、遮挡/杂波/OOSM 和真实 AirSim，
并同时报告循环时延分布与身份指标 availability。不得用本轮墙钟替代实时 SLA，也不得
为追求速度放宽身份审计、门控或 claim 约束。

## 25. 长时重复诊断审计收口

### 25.1 已完成

- 用 2.2 秒和 10 秒同配置 profile 区分元数据审计、GNN/Hungarian、claim summary 与
  duplicate coalescence，确认超线性增长来自 D1 批内重复诊断树的逐轨递归审计。
- 在 D1 到 D2 边界增加批审计和合同投影。共享诊断内容相同时复用已通过审计；任一变体
  仍完整递归检查，投影后只保留 D2 实际消费字段。
- 保留 `Detection3D` 构造和 tracker step 二次审计，新增单轨 truth 注入拒绝、合同投影、
  可复现 200 航迹/48 周期性能和语义哈希测试。
- 完成五 seed、45 周期和单 seed、48 周期隔离对照。完整发布、关联、身份/生命周期、
  claim/审计哈希均一致，在线 truth use 为 0。

### 25.2 当前状态

最终审查加固代码的可复现 200 航迹、48 周期基准为
`16.858297 -> 6.472896 s`，加速 `2.604444x`。未知或自定义 Mapping 始终完整审计，
恶意恒真 `__eq__` 回归 fail closed。既有 10 秒 D2 合计 `37.0072 -> 5.6582 s` 和五
seed 计时属于审查加固前候选；语义哈希仍有效，最终性能由 main 复跑。本项 D2-owned
长时重复审计缺口关闭。后续仍按原计划在真实 AirSim、遮挡/杂波/OOSM 和极端大连通
分量上校准；本轮不调整关联频率、门限、生命周期或 claim 策略。

## 26. 关联内核严格等价热路径收口

### 26.1 已完成

1. 从 clean 基线 `8f86192` 的 10 秒、200v200、seed 42000 冻结在线日志重建 48 个 D2
   周期；runner 只读 online observations，不读 truth sidecar。
2. 固定 dense pair、空间候选、三维马氏求解、合法边、连通分量、匹配、fresh/replay 等
   操作数，并对完整公开结果、航迹状态、协方差诊断、claim、历史和生命周期逐周期哈希。
3. 批量执行 covariance 特征值和 KD-tree 半径查询；复用匹配边 velocity NIS、consistent
   D1 full covariance 治理诊断，并跳过 1x1 Hungarian。regularized covariance 保留完整
   校验回退，不减少输入、频率或合法候选。
4. D1 covariance 复用改为内部预置状态，`Detection3D(...)` 普通构造签名不含预验证参数。
   伪造 consistency 且 6x6 整体非 PSD 的负例仍被 full governance 拒绝。

### 26.2 验收

- 48/48 周期语义 SHA-256 均为
  `dd3f65f01fd5e0941fe5c37def42650edd7107213f7ae97c528c64688a8721ab`，固定操作数逐项
  相等，online truth use 为 0。
- 7 次计时、1 次 warmup 的合计中位数为 `4.859477 -> 4.018963 s`，加速
  `1.209137x`；tracker 中位数为 `2.747088 -> 2.118685 s`，7/7 对应样本更快。
- `govern_covariance` 调用从 66,090 降至 47,434，`eigvalsh` 从 84,789 降至 47,529，
  匹配更新路径重复 `_quadratic_form` 从 9012 降为 0。
- 安全专项 `18 passed`；完整 D2 为 `219 passed, 1 warning in 41.91s`。

### 26.3 剩余 P1

1. 真实 AirSim observation ID、源时钟偏差、雷达周期及迟到分布标定。
2. 代表性遮挡、杂波、漏检和 OOSM 多 seed 回放，以及离线 IDSW/continuity 置信区间。
3. 极端全重叠大连通分量的候选预算、召回和最坏耗时。
4. 固定硬件逐周期 P50/P95/P99 与实时预算，以及完整 200v200 D1-D7 闭环复跑。

## 27. 三 seed clean 集成晋级复核

### 27.1 已完成

1. main 以 `8f86192` 为 reference、`f80b5bd` 为 candidate，在独立 clean worktree 中运行
   nominal 200v200、10.0 s、seeds 42000/42001/42002。三个 episode 均保持有限状态，
   online truth use 为 0。
2. 每个 seed 的 D2 association 调用数均为 47。累计 association 耗时三 seed 均值为
   `8.317513 -> 7.671266 s`，下降约 `7.77%`；终态 D2 航迹数按 seed 为
   `205/204/203`，两侧逐 seed 相同。
3. main 新增跨提交逐条语义审计，三 seed 的 D2 在线记录和 topic counts 均通过。独立
   D3 planner 产生的 opaque `plan_id` 只按 plan occurrence/version 规范化；原始 ACK
   载荷 SHA 在规范化前验证，owner/version/coalition/`global_track_id`/command 业务字段
   不被忽略。
4. D2 候选边界保持：批量 KD-tree/eigenvalue、同周期 velocity innovation 复用、可信
   consistent covariance governance 复用和已完整门控的 1x1 component bypass。不能证明
   可信或发生 regularization 的 covariance 仍走完整回退，不减少合法候选或调用频率。
5. 当前工作区完整 D2 回归为 `219 passed, 1 warning in 49.75s`，零测试失败；warning
   为环境 Matplotlib `Axes3D` 导入提示，不影响关联、身份治理或本轮文档证据。

### 27.2 GAP 状态

nominal 200v200 三 seed 的 clean 跨构建 D2 语义等价复跑已经完成，替代第二十六节中
“尚缺完整集成复跑”的旧待办口径。该证据只关闭集成非退化和最终加固代码 clean 复跑，
不关闭实时性 P1：短长对照仍将 D2 association 判为超线性。下一轮继续验证真实 AirSim
observation ID/源时钟、遮挡/杂波/漏检/OOSM、多场景 offline IDSW/continuity、极端大
连通分量，以及固定硬件逐周期 P50/P95/P99。完整任务效果和物理拦截由 main/D6 另行验收。

## 28. 部分可评估身份合同

### 28.1 已完成

1. 在 evaluation v1 中增加可选
   `d2.scalable3d_partial_identity_diagnostics.v1`，不修改严格 metrics schema、字段、
   availability、reason 或数值。
2. 分开记录全部 mapping、`created/matched` 受评分 mapping、可评估 mapping、歧义、
   unavailable、truth 不在本帧以及缺 identity evidence 数量。
3. 固化 mapping、完整帧和相邻真值转移三个分母。零分母时 coverage 为 unavailable；
   不能以 0 代替。
4. 只对谱系 truth sidecar 能证明的连续唯一锚点统计 IDSW lower bound。一个真值帧必须
   恰好对应一个唯一可评估 `global_track_id` 才能成为锚点；多航迹重复映射单独计入
   exclusion reason，不能按持久化顺序选代表来形成部分下界。未建立完整 truth
   assignment 转移全集，不输出 upper bound。
5. public loader 校验诊断计数、coverage、原因和逐帧 mapping 一致性，篡改后 fail
   closed；在线 DTO/log 未增加 truth 或诊断字段。

### 28.2 当前证据

2026-07-22 对 clean source commit `0d2da25` 的 nominal 200v200、10.0 s、seed 1000
做单 seed 只读复算。48 帧、9644 条 mapping 的原状态计数为 `8906/13/725`；9038 条
进入身份评分，606 条只保留状态审计。受评分映射中 8906 条可评估，coverage 为
`0.985395`，119 条缺 truth label。严格 IDSW 仍因多真值歧义为 unavailable。385 个
唯一锚点区间得到 lower bound 7；另有 1 个真值帧因多条可评估航迹被排除，该帧原本也
不是完整可评估帧，所以 385/7 未变化。该值只是下界，不是完整 IDSW。相关身份测试共
32 项；完整 D2 为 `228 passed, 1 warning in 29.26s`，验收阈值为零失败且 strict
metrics 不退化。

### 28.3 后续

1. main 用新 producer 重算正式多 seed 制品，并冻结每 seed source hash、coverage 和
   blocker 分布；本轮单 seed 结果不得扩写成 20-seed 结论。
2. D6 接入 mapping/frame/transition coverage、ambiguous/missing、lower-bound
   availability/reason；严格 IDSW 与部分诊断必须分栏。
3. 继续补真实 AirSim observation ID/时钟、遮挡/杂波/漏检/OOSM 数据。只有所有 strict
   blocker 消失后，完整 IDSW/continuity 才可恢复 available。

## 29. clean `4ac3bb2` seed 1000 性能 P1 归因与局部收敛

### 29.1 已完成

1. 对 nominal 200v200、seed 1000、10.0 s 的冻结
   `online_observations.jsonl` 建立 `d2-scalable3d-association-hotpath-benchmark-v2`。
   runner 将每条 D2 记录与最新前置 D1 记录配对，允许 MAIN/D5/D7 交错；共恢复 48 个
   D2 周期，不读取 truth sidecar。输入 SHA-256 为
   `c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。
2. 增加 top cumulative/own-time profile、adapter/tracker 逐周期计时、前后各 8 个
   regular 周期窗口、CPU affinity 和线程环境记录。计时策略显式为
   `diagnostic_only_no_wall_clock_pass_fail`，测试只固定业务语义和操作数。
3. 对明确热点实施三项等价优化：每个 `predict_all()` 周期按唯一 `dt` 复用 CV
   transition/process matrix；可信 D1 adapter 对同一已治理 6x6 covariance 及其原生
   marginal 跳过两次冗余 `allclose`；claim ledger 用增量维护的 undated/key 数量并且
   每帧只生成一次 summary。普通 `Detection3D`、regularized covariance、门控、候选、
   claim 淘汰和身份审计路径不变。

### 29.2 验收

- 旧/新对照使用同一冻结输入，48/48 周期公开结果和 tracker 状态严格相等，重复运行
  语义 SHA-256 均为
  `b2334c619b9d2f7c467387ad27b62614d028af83f0b7842b867cab1c4aa9824b`。
- input/fresh/replay/candidate/matched 操作数为
  `9626/9038/588/8862/8823`，两侧逐项相等；逐条在线输出、中心
  `global_track_id`、显式 `id_switch_count` availability、门控、版本、claim ledger
  声明和 truth isolation 均未变化，`online_truth_used=false`。
- CPU 0、BLAS/OMP 单线程、1 次 warmup、7 次计时的 D2 core 总中位数为
  `2.928830 -> 2.204672 s`，描述性加速 `1.328465x`。机器报告
  `docs/d2_clean_4ac3bb2_seed1000_hotpath_20260723.json` 的 SHA-256 为
  `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。
- 完整 D2 回归为 `234 passed, 1 warning in 34.83s`，验收阈值为零失败；warning 是
  既有 Matplotlib `Axes3D` 环境提示。

### 29.3 GAP 状态与下一验收

本轮关闭“缺少可复现 profiler”和上述三个已证明等价的常数成本热点，不关闭长窗口性能
P1。候选早/晚 regular 窗口比为 `1.123036x`，基线为 `1.119661x`；原完整阶段 47 次
regular association 的 P50/P95/max `121.972/137.335/145.966 ms` 以及 10.0 s 相对
2.2 s 的 `1.579x` 仍是 main-owned 全阶段证据，本轮未重跑或改写。

下一验收限于固定硬件的完整阶段逐周期 P50/P95/P99、多 seed 长短窗口，以及 main-owned
lineage/publication 成本分离；同时保留真实 AirSim 时钟、遮挡/杂波/漏检/OOSM、极端
大连通分量和 offline IDSW/continuity。不得用降采样、减少候选、放宽门限、降低关联
频率或在线 truth 换取性能。

## 30. 20-seed 严格身份阻断诊断与上游交接

### 30.1 已实施

1. 新增独立离线诊断合同，按原因、`global_track_id` 和连续帧区间汇总阻断。每个区间
   固化起止帧/时刻、候选真值、观测号、量测时刻和来源谱系哈希，可回到冻结 producer
   制品复核。
2. 新增 D1 `d2_lineage_mapping` 完整性审计。只有每条 estimate-available D1 观测都具有
   唯一量测时刻、唯一离线标签和唯一 D2 航迹声明时，才输出
   `d1.consistency.d2_lineage_mapping_record.v1` 记录。任一缺口使全部 mapping records
   保持空，避免部分 sidecar 被当成完整映射。
3. CLI 对每个 episode 重新执行 source SHA、在线真值隔离、D1/D2 记录语义和 producer
   evaluation 重放，并与持久化 evaluation 逐项比较。在线 Tracker、门控、关联、生命周期
   和 `global_track_id` 均不读取该诊断。

### 30.2 20-seed 结果

clean `5263e2b` nominal 200v200、10 秒、seed 1000--1019 的 20/20 来源和重放检查通过。
严格 IDSW 仍为 `0/20` 可用。阻断分为：

- 118 个真实多真值航迹帧，107 个连续时间段。不同真值均由独立 observation ID、
  measurement timestamp 和 sidecar 标签支撑，不能通过 evaluator 分母调整消除。
- 2464 个受评分映射缺显式 truth/non-target 标签。D1 estimate 侧共有 2474 条此类观测；
  现有 sidecar 没有“已知虚警”处置，D2 不从观测名称推断。
- 部分 mapping/frame/adjacent-transition coverage 为
  `178531/181110`、`103/959`、`1149/187800`；19 个 episode 的下界合计
  `199/15215` anchor intervals。strict 未回填，upper bound 未生成。
- D1 唯一候选为 `188951/191425`；完整可消费 sidecar 为 `0/20`。

### 30.3 下一步责任

1. D1 使用本次多真值区间校准雷达/视觉跨模态门控，必要时分裂航迹，避免不同目标的
   观测进入同一融合后验。
2. main/传感器 producer 为观测全集写显式 `target`、`known_false_alarm` 或
   `unknown` 处置和完整性摘要。D2 继续禁止从名称、位置或距离补标签。
3. D1 若要在已知虚警存在时报告 RMSE/NEES，应另设带 coverage 的部分误差合同；该合同
   不能改变 D2 strict IDSW availability。
4. D2 后续在新 producer 制品上重跑同一 CLI。验收要求 strict 指标只有在唯一、完整、
   全时序映射成立时才可用，同时保留来源哈希和在线真值使用为 0。

## 31. observation truth v2 标签处置

### 31.1 已实施

1. 将规范 sidecar 升级为 `d2.scalable3d_observation_truth.v2`，处置集合固定为
   `target`、`known_false_alarm`、`unknown`。v1 D2 和 producer target-only 输入继续
   兼容读取，write/hash 使用规范化 v2。
2. `target` 强制唯一 `truth_target_id`；另外两类禁止携带目标 ID。冲突、重复、时间戳
   不一致和 unknown 均保持 fail-closed。没有从 observation 名称或几何信息推断处置。
3. 目标与已知虚警混合谱系保留唯一目标候选并进入 disposition audit。纯已知虚警航迹帧
   作为非身份 `excluded` 记录，不进入 strict 或 partial lower-bound 分母。
4. D1 mapping 只发布 target 记录。已知虚警进入 exclusion 计数；unknown 或其他不完整
   证据使全部 mapping records 为空。blocker diagnostics 和 D1 audit 版本升级为 v2。

### 31.2 验证与后续

2026-07-23 新增 11 项处置合同测试，完整 D2 为
`249 passed, 1 warning in 32.08s`。冻结 `5263e2b` nominal 200v200、seed 1000 的旧 v1
producer evaluation 重放一致，证明 target-only 输入兼容。

D2-owned schema、load/write/hash、评估和诊断实现已闭合。main/传感器 producer 仍需为
观测全集实际写出 v2，尤其是 `_append_false_alarms` 产生的视觉虚警；随后重跑
seed 1000--1019。D1 的真实多目标混轨不因虚警处置被跳过，strict IDSW 只有在混轨、
unknown、冲突、缺标签和时间问题全部消失后才可用。

## 32. 身份承诺 v2 clean seed 1100 复核

### 32.1 已完成

1. main 在 clean 提交 `909669b` 上完成 nominal 200v200、2.2 s、
   `recon_count=2`、seed 1100（首个预留的未见 gate seed）的 baseline/candidate A/B；
   运行制品位于
   `/tmp/MSM-identity-commitment-ab-909669b/{baseline,candidate}`。
2. baseline 为 D2 航迹 203、D3 分配 200、strict IDSW 9、track continuity
   `0.865`、coverage continuity `0.870`，all-record commitment coverage 为 `1.0`。
3. candidate 为 D2 航迹 201、D3 分配 197。1787 条 evidence 中 1714 条 committed、
   73 条 uncommitted，all-record commitment coverage 为 `0.9591494124`；未提交记录
   分为 69 条 active hold 和 4 条 after hold。
4. candidate 的未提交 source binding violation 与 candidate binding violation 均为
   0，online truth use 为 0。该结果确认 v2 原子持久化、公开审计和 fail-closed 约束按
   合同执行。

### 32.2 未通过项

`GT3D-000185`、`GT3D-000186`、`GT3D-000202` 已由新原始雷达观测恢复 committed。
三条观测的 `measurement_timestamp=1.2 s`，评分帧为 `2.130815 s`，对应谱系年龄
约 `0.930815 s`，比固定 `0.9 s` lineage window 多约 `0.030815 s`。candidate 的
strict IDSW、track/identity continuity 和 coverage continuity 因
`source_observation_outside_lineage_window` 保持 unavailable。D2 航迹和 D3 分配也
分别比 baseline 少 2 条和 3 条，未满足业务可用性非退化门槛。

### 32.3 后续计划

1. 结构歧义候选保持 `enabled=False`，停止 seeds 1101/1102；本轮不进入 AirSim 或扩展
   seed 晋级试验。
2. 固定 `0.9 s` lineage window 不扩大。后续先分析评分帧与恢复量测之间约
   `0.030815 s` 的调度、发布和评分边界，修复必须保持谱系唯一性和时间合同。
3. 下一候选仍需在同 seed 同时满足 strict identity metrics available、online truth
   use 为 0、未提交绑定违规为 0、D2/D3 可用性不退化，才允许启动后续未见 seed。
4. 文档与评审必须持续区分两项结论：身份承诺 v2 合同已实现并通过 fail-closed 验证；
   结构歧义算法候选尚未通过准入。

## 33. 恢复承诺发布新鲜度门控

### 33.1 已实施

1. `IdentityCommitmentRecoveryConfig` 升级为
   `d2.identity-commitment-recovery-config.v2`。默认配置版本为
   `d2-identity-recovery-publication-freshness-v2`，发布新鲜度门控默认开启，冻结预算
   为 `0.9 s`。
2. hold 后恢复承诺必须同时满足原有 key、水位线、claim、replay、活动租约和
   truth-free disposition 条件，以及
   `tracker_frame_timestamp - source_measurement_timestamp <= 0.9 s`。超龄证据在
   量测更新前撤回，航迹保持未提交并等待更新的原始证据。
3. `Scalable3DTracker.step()` 的统一状态时刻显式传入恢复门控。当前在线合同继续要求
   Detection 的状态有效时刻与 tracker frame 相等；原始传感器量测时刻单独保存在
   `source_measurement_timestamp`。二者不相等的 Detection 扫描被拒绝，OOSM 输入仍须
   走显式适配器。
4. 配置允许显式关闭发布新鲜度门控以复现旧水位线/replay 行为。默认保持开启；兼容关闭
   不能作为结构歧义候选准入配置。

### 33.2 验证与下一门槛

2026-07-23 使用确定性 D2 六维质点夹具验证，无随机 seed、未启动 AirSim。专项文件
`test_ambiguity_hold_lease.py` 为 `32 passed`；完整 D2 为
`291 passed, 1 warning in 29.05s`，验收阈值为零失败。warning 是既有 Matplotlib
`Axes3D` 环境提示。

模块测试证明发布超龄恢复保持未提交、后续合格原始证据可恢复、same/older/replay 继续
阻断、无 hold 路径不受恢复预算影响、配置版本和非法值校验有效。

main 已在配置谱系绑定后的 clean 提交
`ff881316243ff5a2991a4659ab78637ed625d123` 完成权威 seed 1100 A/B，制品位于
`/tmp/MSM-identity-freshness-final-ff88131/{baseline,candidate}`。发布新鲜度门控把三条
超龄恢复保持为 `identity_uncommitted_after_hold`，strict 指标由旧候选的 unavailable
恢复为可用；candidate IDSW 为 3，baseline 为 9。该候选仍未通过联合门槛：D2 航迹
`203 -> 201`、D3 分配 `200 -> 197`、track continuity
`0.865 -> 0.8266667`、coverage continuity `0.870 -> 0.8283333`。因此下一步不是扩展
seed，而是形成新的结构歧义算法候选并先关闭数量、连续性和覆盖退化。当前继续停止
seeds 1101/1102、10 s 和 20-seed 运行。

## 34. 结构歧义租约因果审计

### 34.1 已完成

1. 使用既有 clean baseline/candidate 逐帧联接 D2 航迹、身份承诺和 D3 计划。候选
   累计创建 203 条航迹，`GT3D-000133/000164` 退出后终态为 201；其后继碎片对应
   candidate 的 3 次 strict IDSW。
2. 确认终态 9 条未提交航迹由 4 条释放后无新证据、3 条发布超龄和 2 条活动租约组成。
   三条超龄证据年龄为 `0.9308153039 s`，超过冻结 `0.9 s`，拒绝必须保留。
3. detached clean seed 1100 已扫描 `(1,2)`、`(1,3)`、`(1,4)`、`(2,3)`、`(2,4)`。
   五组终态 D2 航迹均为 197；D3 分配为 `195/195/197/195/197`。没有参数点满足
   baseline-relative 联合非退化。
4. 旧冻结 seed-1100 制品的 D3 第 2/3 版计划分别包含 11/8 条未提交航迹。该结果说明
   历史 D3 分配数 197 不是 committed 可分配航迹数。固定提交 `7e15dac9` 的同输入
   clean 复验已经证明 D3-owned 准入会排除全部未提交航迹，见第 35 节。

### 34.2 后续边界

1. 默认 `(2,5)`、默认关闭状态和 `0.9 s` 发布新鲜度预算保持不变。
2. 不再扩展重放、seed 或长时矩阵。`(1,4)` 只作为下一候选的诊断对照，不进入默认。
3. 下一算法候选需由新任务单独实施。方向是身份未提交但运动学保守更新：不产生身份
   binding、hit、建轨、改绑或 ID 变化；协方差不得在歧义子空间收缩；replay、来源绑定、
   publisher epoch、水位线和 0.9 秒门控保持不变。
4. main/D3 拒绝未提交航迹、旧绑定撤回、严格版本递增和下游 D5/D7 阻断已经由第 35 节
   的同输入复验证明；该项转为强制回归，不再列为开放合同缺口。
5. 完整证据和合同见
   `subagent_reviews/D2_STRUCTURAL_AMBIGUITY_HOLD_LEASE_CAUSAL_AUDIT_CN.md`。

此前因果专项为 `42 passed in 0.61s`。2026-07-23 本次复核又运行完整 D2 回归，结果为
`291 passed, 1 warning in 31.00s`；warning 为既有 Matplotlib `Axes3D` 环境提示。
未启动额外 seed、长时重放或 AirSim。

## 35. clean seed 1100 承诺准入 A/B

### 35.1 冻结输入

本轮复核只读取
`/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。两臂固定
提交为 `7e15dac9cdaf6743999dfe045a70676fd31a17d6`，工作树均为 clean；场景为
nominal 200v200、`recon_count=2`、时长 `2.2 s`、seed 1100。场景配置 SHA-256 为
`20ef5248c8b45ff5aced9080c8d47e65a43aaba54f18ce824dc50fac7a52b840`。
`hold_only` 关闭 D1 identity-neutral centroid correction，`hold_plus_centroid`
开启该候选；其他已核对的 D2/D3 配置一致。

### 35.2 已关闭合同

1. 两臂 9 条 D2 在线发布逐字节相同，SHA-256 为
   `da7089facfea118ea90e7c7f6464ff8745c079971656b58b954e9fcd0edf8d2f`。
2. 第 2 版 D3 计划在 `t=1.0 s` 显式拒绝 11 条未承诺航迹，`forced_replan=true`、
   `hysteresis_bypassed=true`、`all_primary_reserve_slots_blocked=true`。11 条旧绑定
   全部从新计划撤出，计划版本 `1 -> 2`，新计划只含 186 条 committed assignment。
3. 第 3 版计划版本严格增加到 3，继续拒绝当时的 11 条未承诺航迹。每版
   `identity_commitment_rejected_target_ids` 与 assignment 的交集均为空。
4. 与各自计划版本联接后，D5 active-vision 和 D7 guidance 对被拒绝目标的命令数均为
   0；online truth use、duplicate assignment、未承诺 source/candidate binding
   violation 均为 0。

以上结果关闭显式承诺状态从 D2 到 D3/D5/D7 的安全准入合同。该关闭项不属于 D2
关联算法性能晋级。

### 35.3 P1 保持开放

- 两臂 D2 终态均为 201，strict IDSW、track continuity、coverage continuity 为
  `3/0.8266666667/0.8283333333`；available/unavailable/uncommitted mapping 为
  `1491/218/76`，all-record commitment coverage 为 `0.9574706212`。这些值与此前
  hold candidate 相同，没有修复 D2 连续性和可用映射退化。
- 质心臂 46 个候选全部被 fail-closed gate 拒绝，实际处理为 0，不能判断收益或风险，
  也不能作为结构歧义 hold 的替代算法。
- 下一 D2 候选仍需在不恢复身份承诺、不硬绑定 observation、不虚假收缩协方差的前提下，
  提供可验证的歧义期运动学支持，并先在 seed 1100 同时满足航迹数、可用映射和两项
  continuity 非退化。
- seeds 1101/1102、10 s 和 20-seed 扩展继续停止；真实 AirSim 身份准入复验仍未执行。

本轮完整 D2 回归为 `291 passed, 1 warning in 29.29s`。warning 是本机 Matplotlib
`Axes3D` 环境提示，不改变验收判定。

## 36. 结构歧义有界概率/多假设 C0 计划

### 36.1 当前状态

2026-07-23 完成 C0 文档规划，详细设计见
`docs/STRUCTURAL_AMBIGUITY_BOUNDED_HYPOTHESIS_PLAN_CN.md`。本节只登记未来实施顺序，
不改变第 35 节的运行结论：

- 当前没有新增 Python、开关、配置类、公开 schema、测试或运行证据；
- 默认 GNN/Hungarian、现有 prediction-only hold、默认关闭状态和固定
  `0.9 s` 发布新鲜度预算不变；
- `global_track_id` 仍为中心 D2 权威，D3 继续只消费 committed；
- seeds 1101/1102、10 s 和 20-seed 扩展继续停止。

### 36.2 输入与首阶段边界

C1 计划只消费严格的 D1 `d1.structural-ambiguity-evidence.v1`：

1. 保留 `measurement_timestamp` 和 `arrival_timestamp`，measurement time 作为固定
   窗口重放主序，arrival/published time 用于延迟和 tie-break 审计。
2. 只使用 D1 `candidate_edges` 中含 `maximum_matching_allowed` 的 allowed edge；
   D2 不补边。
3. opaque member token、三段式 `source_key` 和 observation evidence key 只承担来源
   lineage/幂等；不能成为 canonical ID。
4. NIS 只形成版本化相对身份权重；generation、evidence/component digest 和 publisher
   epoch 承担回放幂等。
5. `cross_covariance_available=false` 是强制门。C1 只管理关联/身份假设，不做概率
   状态混合、分支状态更新、历史回填或相关 covariance 融合。
6. 在线 truth/actor/target/D6 mapping 使用必须为 0。

若 member 没有既有 canonical binding，保持 `uncommitted + deferred_birth`；hypothesis
manager 不建轨。任何获胜路径若要求创建、改写、交换或局部重绑 `global_track_id`，
均失败关闭。

### 36.3 算法选择

首版推荐 component-local identity-only bounded MHT：

- bounded MHT 保存最多五代的少量联合匹配路径，适合连续 generation 延迟承诺；
- 从同一联合假设池导出 JPDA 风格 `beta_ij`、归一化熵和第一/第二路径似然比；
- JPDA 边缘概率作为诊断和承诺门，不执行 JPDA state/covariance mixing；
- 当前 `JPDAAssociator`/`MHTAssociator` 不能直接视为该能力，仍是二维轻量研究对照。

200 规模按 allowed-edge 稀疏连通分量运行，不建立全局 200x200 假设树，不跨分量相乘
权重。确定 1x1 分量留在既有路径。未来 C1 预注册预算为：

- 单窗 member/observation/edge `8/8/64`；
- 完整枚举最多 256 个最大基数匹配，否则每代 k-best 32；
- 剪枝前 child 总数 2048，每窗口保留 64 个假设；
- 窗口最多 5 generation 且 measurement-time 跨度最多 `1.0 s`；
- active window 最多 256，全局保留假设最多 4096。

超限不得靠静默截断后形成高置信度；回退 hold 并保持 uncommitted。k-best 没有遗漏
质量上界时只能 shadow，禁止 commit。

### 36.4 权重、排序与幂等

每条 allowed edge 的首版计划分数为
\(-\operatorname{NIS}/(2T_{\mathrm{NIS}})\)，与显式 coast/deferred-birth prior 和
parent path 权重在 log domain 累加。使用 logsumexp 归一化；任一输入、部分和、归一化、
熵或似然比出现 NaN/Inf，整窗 fail closed。

窗口按 measurement/arrival/published time、publisher node/epoch、sensor/scan、
component/generation/evidence ID 的完整键重放。成员、观测、边和假设分别使用规范排序；
剪枝键固定为 `(-log_weight, hypothesis_id)`，并列由内容摘要决胜。

幂等键为
`(publisher_node_id,publisher_epoch,component_id,component_generation)`：

- 同 key/同 digest 是无副作用 no-op；
- 同 key/异 digest、generation 回退或跳号均不能承诺；
- 窗内 OOSM 只从身份 checkpoint 重算权重，不重放物理状态；
- 超过 5 代或 `1.0 s` 的 OOSM/网络迟到不重开窗口；
- 同一 member/canonical track/observation 出现在冲突窗口时，涉及窗口全部失败关闭。

### 36.5 commitment 与 D3

未收敛窗口继续输出现有 uncommitted 语义。未来承诺必须同时满足：

1. 最新支持 evidence 的 measurement age 不超过 `0.9 s`；
2. 第一/第二路径 likelihood ratio 至少 20；
3. 含 omitted-mass `other` 桶的归一化熵不超过 `0.20`；
4. 拟承诺匹配每条边缘概率至少 `0.95`；
5. 同一 canonical assignment 连续至少 3 个严格递增 generation 获胜；
6. 至少 3 个不同 evidence/scan 和 observation key，measurement time 严格推进，
   publisher epoch 和既有 canonical reference 一致；
7. 没有溢出、缺代、同代冲突、跨窗冲突、非有限权重或无界截断质量。

commitment 只结束未来身份 hold，不回填歧义帧状态。D3 继续只消费 committed；overflow、
missing evidence、网络超窗和 fail-closed 航迹均不得进入新计划。已有计划撤回、严格
增版和 D5/D7 阻断沿第 35 节已闭合合同维护。

### 36.6 C0-C3 与预注册验收

- **C0，当前完成**：只冻结设计、预算、停止条件和文档；无代码/测试/运行。
- **C1**：内部默认关闭的纯身份假设原型；只跑手算/确定性 fixture，验证 full/k-best、
  log-domain、排序、剪枝、OOSM、generation、容量、truth 隔离和 ID 不变式。
- **C2**：冻结输入 offline shadow；业务输出仍由 GNN+hold 产生。先验证 200 规模
  P95/RSS 和长时有界性，再由独立任务决定是否复核 seed 1100。
- **C3**：只允许已通过联合门的 commitment 结束后续 hold；仍不做相关状态融合。
  同输入全部非退化后，才能另行预注册全新未见 seed。

候选指标必须同时包含 strict IDSW availability、strict IDSW、track/coverage
continuity、D2 committed/available mapping、D3 committed target/assignment、
birth delay、generated/retained hypothesis 数、P95、峰值 RSS、online truth use 和
ID create/rewrite/rebind/token-as-ID/uncommitted binding violation。预注册性能门为
hypothesis stage P95 `<=20 ms`、D2 core P95 `<=1.25x` baseline、RSS 增量
`<=128 MiB` 且 `<=1.20x` baseline。IDSW 改善不能抵消 continuity、可用性、birth
delay、资源或绑定合同退化。

seeds 1101/1102 在 C0-C2 均不恢复；C3 也必须重新登记 seed 清单并单独授权，本计划不
自动把 1101/1102 作为下一批。

## 37. 已知虚警排除计数口径收口

### 37.1 已完成

2026-07-24 将 `known_false_alarm_only_mapping_count` 的 producer 口径改为最终
持久化映射口径：

```text
count(status == excluded and reason == known_false_alarm_only)
```

不再用来源 disposition 中“有 known false alarm、无 target、无 unknown”的组数替代
最终排除数。来源处置仍用于 `target_with_known_false_alarm_mapping_count` 和
`unknown_disposition_mapping_count`；这两个字段描述每个持久化 mapping group 的证据
组成，不表示 mapping 的最终状态。

新增非 observed 仅虚警回归。该组同时带有
`lineage_on_unassigned_track` 和 `track_not_assigned_in_frame`，最终为 unavailable，
不得进入排除计数。既有缺标签、unknown、处置冲突、时间错误和谱系超窗仍保持
fail closed。

### 37.2 真实制品复核

只读重放 nominal 200v200、10 秒、seed 1102 reference 制品。48 帧、9505 条 identity
evidence 和 11437 条 truth labels 中，旧审计报告 14，最终 persisted exclusions 为
11；另 3 个仅虚警组因谱系超窗为 unavailable。新 producer 报告 11。除该字段外，新旧
evaluation payload 严格相同；相邻计数 `133/0` 不变。

验收门是审计值与最终 persisted `excluded/known_false_alarm_only` 映射逐条相等，且
其余身份结果不变。专项 `12 passed`，完整 D2
`292 passed, 1 warning in 28.81s`。该 D2-owned 评估合同缺口已关闭。

### 37.3 不变的后续计划

本修复不构成关联算法、AirSim 或实时性能晋级。结构歧义运动学支持、C1-C3 有界身份
假设、真实 AirSim、多 seed 严格身份和固定硬件时延仍按前述 P1 计划执行。

## 38. D1 发布审计 v2 消费合同

### 38.1 已完成

2026-07-24 完成 D2-owned v2 消费逻辑：

- 只接受 D1 公开的精确 `ImmutablePublicationAuditMap` 根、精确递归 validator 和固定
  `d1.publication_audit_tree.v2`；
- 每个新对象先验证不可变结构，再执行 D2 forbidden-key 内容审计；
- 成功后在当前批内保留强引用，以 `id` 定位并用 `is` 确认同一对象后复用；
- 等值但不同身份的 v2 根分别处理；畸形精确构造和 v2 子类失败关闭；
- marker、自定义 equality 和可变 backing 不进入 v2 路径；
- 精确内建容器的既有等值代表复用不变；
- 新增 `detections3d_from_d1_global_tracks_with_audit()` typed API，并与
  `D1GlobalTrackDetectionBatch` 一同通过包 API 和 `__all__` 导出；旧入口返回兼容。

200 航迹、三个共享 v2 根的确定性测试中，合同验证和完整内容审计各 3 次，同身份复用
597 次。完整 D2 回归为 `305 passed, 1 warning in 29.40s`。该阶段没有启动 AirSim，
没有改 GNN/Hungarian、状态机、身份承诺或 `global_track_id` 规则。

### 38.2 main/D6 正式验收结果

2026-07-24 已在 clean source commit
`be399e138762f5e660f553c8caa812d52ab38c61` 上完成预注册矩阵。场景为 200 目标、
200 资源和 2 侦察节点；short 10 pair、long 3 pair，共 13 pair/26 arm。所有 arm
均重新运行，`reused=0`、`failed=0`。13/13 pair 的业务语义、有限状态、在线真值
隔离、实现身份和 D2 发布元数据审计通过。

候选臂累计得到：

1. 精确 v2 合同验证 702 次；
2. v2 完整内容审计 702 次；
3. 同对象身份复用 139920 次；
4. 合同拒绝 0 次、内建等价复用 0 次。

参考臂累计 139920 次内建等价复用，所有 v2 计数为 0。D2 association 墙钟 short
由 `0.657417 s` 降至 `0.548699 s`，下降 `16.1939%`；long 由 `5.869413 s`
降至 `3.774282 s`，下降 `35.6213%`。两档结果均满足候选相对参考均值增幅
`<=5%` 的门限。D1 fusion 和核心墙钟改善也通过各自门限，D6 最终输出
`d1_optimization_admitted=true`。main promotion commit `f5b350b` 已默认选择
`immutable_shared_v2`，并保留 `per_track_copy_v1` 作为显式 reference。

### 38.3 保留的 P1

本次只完成发布元数据审计路径的墙钟和业务语义准入。以下工作不因候选晋级而关闭：

1. 最低实时因子仅 `0.1730801`，系统实时 P1 继续开放；
2. 当前 `latest/totals` 只能证明固定批次累计关系，尚缺逐批审计日志；
3. 本矩阵不验收 IDSW、track/identity/coverage continuity、RMSE、NEES 或 NIS；
4. 本矩阵是三维质点正式证据，不是 AirSim、固定硬件或实飞精度验收；
5. `global_track_id` 仍由中心 D2 所有，发布元数据优化不得改变身份合同。

## 39. 正式 R0 generation 守恒阻断

### 39.1 已完成复核

- [x] 读取 source commit `2c7b425` 的正式 R0 900-episode D6 聚合和五个失败
  episode 原始制品。
- [x] 核对 D1 posterior generation、D2 source generation 序列、pre-tick merge、
  pending、finalize skip、D2 publication 和 tracker timestamp。
- [x] 确认 finalize skip 分布为 `{0: 895, 1: 5}`，扩展计数式在 900/900 上成立。
- [x] 逐轨比较五例最后实际消费后验与最终后验，确认全部航迹的状态和协方差变化。
- [x] 确认五例均在 main 调用 D2 前被简化签名跳过，D2 Tracker 没有收到最终
  generation。
- [x] 确认 D2 replay-coast 已具备重复来源证据的无 hit、无 birth、无 freshness
  refresh 治理。

### 39.2 D2 决定

- [x] 不修改 D2 在线关联器、claim ledger、IDSW 统计或生命周期。
- [x] 不把未调用记为消费，不增加虚假 merge，不丢弃 late batch。
- [x] 发布
  `docs/D2_FORMAL_R0_GENERATION_CONSERVATION_AUDIT_CN.md`。
- [x] main runtime bus 修复已实际消费最终 pending 后验，消费失败时不再清空 pending；
  修复已形成 clean source commit `98d01bf`。
- [x] 五个原失败 seed 的开发态定向回归已通过 generation integrity 和 D2
  replay-coast 不变量。
- [x] D2 replay-coast 复核提交为 `dc5821f`，D6 skip 准入修复提交为 `8e955f3`；
  二者均包含在 `98d01bf` 的提交历史中。
- [x] 正式 source 已冻结为 `1e5ed8ddcf27f375e922a447decfbd875d21bfdf`，execution
  plan SHA-256 为
  `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
- [x] shards 0、5、9 已完成，共 135/900；其中三个原失败 cell 已由 D6 v10 正式闭合。
- [ ] 解决存储容量阻塞。当前可用空间只比 20 GiB 运行下限多约 65 MB，已停止启动
  新单元。
- [ ] 存储解阻后按同一 source、plan 和分片合同继续其余 765 个单元；不得与旧
  `2c7b425` 的 895 个通过项拼接。

### 39.3 验收

修复后的每个 episode 必须同时满足：

1. pending 只在 D2 成功消费或强内容摘要证明合法 no-op 后清空；
2. 实际 D2 consumption count 等于 D2 publication count；
3. 最终 D2 source generation 等于 D1 final generation；
4. 合法 late/OOSM 后验没有丢失；
5. 重复来源证据没有增加 hit、创建新轨或刷新原始证据时钟；
6. `global_track_id` 未改写，`id_switch_count` 没有回填或伪造。

扩展式 `consumption + pre_tick_merge + finalize_skip = d1_generation` 只保留为诊断。
在当前 skip 缺少强内容等价证据时，不得把它用作 clean-formal 准入条件。

### 39.4 Hotfix 复核状态

五个定向 cell 的 D1/D2 final generation 分别为
`13/13、9/9、13/13、14/14、27/27`，skip 全为 0，pending 全部排空，在线真值使用为
0。四个 5v5 cell 的 replay quarantine/coast 均为 5/5；20v20 seed 1009 为 20/19，
剩余一条只触发既有 miss/lifecycle 路径。

D2 owner 快照确认五例累计 hits、last update time、track key 和 canonical ID 集合
不变，created map 为空、duplicate coalescence 为 0。当前输出全部
`repository_dirty=true`，D6 formal admission 为 0/5。P0 的代码修复已通过开发态复核，
修复已形成 clean source commit `98d01bf`。后续正式 source
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf` 已运行 135/900；3/5 原失败项正式闭合，
完整 R0 仍等待存储解阻后继续。

### 39.5 当前验证

- D2 replay-coast 专项：`5 passed in 0.95s`；
- D2 全量：`305 passed, 1 warning in 29.45s`；
- main hotfix 五 seed 定向测试：`5 passed, 66 deselected in 3.51s`；
- D2 全部 Python 文件 `py_compile` 和 scoped `git diff --check`：通过；
- 全量 `pyflakes`：仅保留 `calibration.py:6` 自提交 `d0cd548f` 起存在的未使用
  `dataclasses.field` 导入，不属于本次 finalize 修复。

### 39.6 正式重跑增量

2026-07-25 的正式增量固定为：

1. source commit：
   `1e5ed8ddcf27f375e922a447decfbd875d21bfdf`；
2. execution plan SHA-256：
   `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`；
3. 完成 shards：0、5、9，每片 45 个单元，合计 135/900；
4. 原失败正式闭合：5v5 seed 1000、5v5 seed 1005、20v20 seed 1009；
5. 上述三项 D6 v10 均为 clean-formal、formal eligible、generation verified，
   skip=0、pending empty、failure reason empty；
6. 5v5 seeds 1008/1018 尚未正式重跑，完整 R0 不关闭；
7. 可用空间只比 20 GiB 下限多约 65 MB，运行已停止，等待存储解阻。

## 40. seed 2007 物理窗口身份映射审计

### 40.1 已完成复核

2026-07-29 对 readiness-v3 seed 2007 treatment full-chain 做只读审计。后继计划
`d3-plan-3529e5a66440:v2` 在 `[1.0, 2.0)` 秒执行 19 条非 hold D7 绑定，只有
`INT-0004/GT3D-000004` 返回 `identity_mapping_unavailable`。

D2 evaluation v2 的该航迹共有 13 个持久化 frame。12 个 available frame 全部唯一映射
到 `TGT-0004`；唯一 unavailable frame 位于 `1.035192721089 s`，association state 为
unmatched、lifecycle 为 confirmed、原因为 `track_not_assigned_in_frame`。前后 available
锚点分别为 `0.833472220197 s` 和 `1.236148794089 s`，均指向 `TGT-0004`。没有 ambiguous、
uncommitted、竞争真值声明或在线 truth 使用。

### 40.2 D2 决定

D2 不修改在线 tracker、逐帧 truth mapping 或 identity commitment。unmatched coast
没有本帧接受观测，`source_observations` 必须为空；复制历史谱系会制造重复证据。逐帧
mapping 继续以 `track_not_assigned_in_frame` 失败关闭。

该断点不是 D2 producer 丢字段。evaluation v2 已携带前后 mapping、逐帧 evidence record、
identity commitment 和 `lineage_time_window_s=0.9`。直接根因是 D6 runtime outcome join
尚未区分“身份歧义/未提交”与“已提交航迹的一帧无量测 coast”，并把后者扩大为整个执行
窗口 unavailable。

### 40.3 后续消费合同

main 应把修复任务交给 D6。D6 可增加 evaluator-only 的
`bounded_committed_coast_bridge_v1`，但必须同时满足：

1. gap 前后存在同一 `global_track_id` 的 available mapping；
2. 两个锚点只指向同一 `truth_target_id`；
3. gap 内 mapping 只允许 confirmed/unmatched 且 reason 精确为
   `track_not_assigned_in_frame`；
4. gap 内 identity commitment 持续 committed，无 active ambiguity lease、recovery
   blocker、uncommitted 或 ambiguous 状态；
5. 同期没有其他 global track 声明该 truth；
6. 锚点间隔不超过 evaluation 中冻结的 lineage window；
7. 输出标记 `online_exposure_allowed=false`，只用于离线物理结果联接。

缺任一条件时保持 unavailable。D6 修复后由 main 对同一落盘输入重放，不得修改源
episode、在线 D2 JSONL、truth sidecar 或规范 `global_track_id`。本项为 D6-owned P1，
D2 无新增 P0/P1 代码任务。2026-07-29 的 D2 evaluation loader、全量
`305 passed, 1 warning`、全部 Python `py_compile` 和 scoped `git diff --check` 均通过。

## 41. 正式 R0 严格身份阻断因果诊断

### 41.1 已完成

2026-07-31 已完成离线诊断最小闭环。现有 CLI 保留旧 `--episode-root`，并增加
`--execution-root`，从正式 `shards/*/cells/*/episode` 布局按 execution plan 和 shard
状态发现已完成单元。发现过程校验 source commit、execution-plan logical/file hash、
shard plan、checkpoint、progress、cell result、episode identity、D6 identity 摘要和
离线身份 source hashes。任何缺失、布局错误、哈希不一致或严格 verdict 不一致均失败
关闭。

诊断 v3 与 causal pack API 已导出。输出按 episode 和 mapping event 分层，避免把
27/9 episode 写成 38/518 event。multi-truth 分类包含历史真值簇、最新观测真值、最新
引入标记、radar/camera 来源转换和承诺 reason；lineage-window 分类包含每条来源年龄、
最老/最新年龄、active commitment source 年龄及 historical-only/active-stale 状态。
archive 只提供元数据绑定和 main 单 shard 临时恢复约束，不自动解包。

### 41.2 验证边界

小型 fixture 覆盖当前正式目录布局、36 个筛选结果及 27/9 原因计数、517
historical-only 与 1 active-stale、multi-truth newest-introduction、radar-to-camera
转换和 identity source hash 篡改。main 已独立核对正式 450 episode 的 36-case 统计，
本轮 D2 不重新运行正式 episode，不修改正式制品，也不把 unavailable 改写为 0。

### 41.3 后续 P1

离线因果诊断工具缺口关闭。后续 P1 只保留两项：一是 main 在存储和调度条件满足时用
同一 source/plan 生成正式 36-case pack；二是基于几何、协方差、运动连续性和来源一致性
设计 truth-free 在线候选，经新 producer/execution plan 和多 seed 正式批次验证。在线
候选不得读取诊断中的 truth cluster，不得放宽固定 `0.9 s` 身份承诺新鲜度预算，也不得
改写 `global_track_id`。2026-07-31 专项回归为 `8 passed in 0.60s`，全量为
`309 passed, 1 warning in 29.68s`；CLI help、变更 Python 文件 `py_compile` 和 scoped
`git diff --check` 均通过。
