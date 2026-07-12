# D4 分布式协同与降级接管计划

## 1. 范围与安全边界

D4 只负责 C-UAS 工作流中的离线科研仿真、降级仲裁、二级节点接管建模、完全无中心保底协商和评估日志。模块输入是粗粒度摘要，通信只使用内存网络或 main/runtime 提供的链路摘要；模块不拥有真实 AirSim episode 调度、真实通信链路、视频帧传输、飞控接口、硬件驱动、火控参数、毁伤模型、自动处置或授权绕过逻辑。

中心 C2 正常时，D3 仍是中心化分配的权威来源，`global_track_id` 仍由中心/上游航迹体系拥有。D4 在任何模式下都不得创建、改写或本地重绑定 `global_track_id`，只能复制上游 ID 做一致性检查、风险加权和审计。

## 2. 工程问题

中心节点正常时，系统依赖 D1/D2 的融合航迹、D3 的版本化 `AssignmentPlan`、D5 的末端视觉关联和 D6 的评估日志。当中心节点失效或局部分配证据不可信时，D4 需要回答以下问题：

- 如何区分中心真的失效的被动降级，与中心仍在线但计划风险升高的主动降级。
- 如何在中心失效后优先选择地面备份、固定系留或机动高空二级侦察节点，而不是直接进入完全无中心协商。
- 二级节点不可用时，如何使用轻量 CBBA 保底维持连续性，同时避免重复 owner、过期 ID、友方冲突和不收敛计划被发布。
- D1 不确定度、D2 关联风险、D3 plan/version/freshness 和 D5 terminal/cross-view 证据如何统一成 D4 仲裁动作。
- D5 distributed visual evidence 如何在完全无中心模式下影响 CBBA 出价，而不是构造虚拟中心或重新绑定 `global_track_id`。
- 中心恢复时如何通过双轨合并避免短暂 heartbeat 恢复导致双主。
- D4 输出如何进入 D6 event metadata 和后续 main runtime bus。

## 3. 当前总体状态

D4 所属的 P1 合同层已闭合。最新 2026-07-11 验证中，ComputerVision 总体验收为 8/10；二级协调者 `Secondary_Recon_1` 与完全分布式 `INT-02` peer 均以 required-member ACK 3/3 进入 `executing`，分别输出 `degrade_to_secondary` 和 `degrade_to_distributed`；缺 ACK 场景以 2/3 ACK 进入 `aborted`，三个 T001 成员均 `hold_for_review`，确认 fail-closed。当前不再把 secondary/distributed 正例写成 unsupported 或未闭合。

状态必须按层级解释：

| 层级 | 当前状态 | 不得外推为 |
|---|---|---|
| P1 合同层 | **已完成**：secondary ACK 3/3 `executing`、peer ACK 3/3 `executing`、缺 ACK 2/3 `aborted`/`hold_for_review` 已有真实 ComputerVision 正负例 | 自主成员形成、完整重构或物理拦截 |
| P1 物理/长期标定 | **仍开放**：SimpleFlight 15 s 的 30 个 active pair 均未物理命中；完整扰动矩阵、成员重构/恢复和多 seed 误降级标定未完成 | 不能用合同通过替代长时动力学、网络韧性或恢复验收 |
| D4 P2 isolated replay | **已实现原生故障 replay 和外部 capability adapter**：6/6 原生场景满足预期；MIT/CA-CBBA 默认输出 unavailable | 外部 MIT/CA-CBBA 已执行，或外部 unavailable 可用于性能比较 |

D4 的 P2 replay 只在显式 API/CLI 下隔离运行，不替换默认本地轻量 `CBBANegotiator`、原子 commit 或 ACK/lease/epoch 门控，也不添加默认依赖。当前原生 deterministic replay 覆盖旧 epoch、过期 lease、成员不可执行/补位和分区，但它是合同回归/研究近似，不等于完整 AirSim 多 seed 扰动矩阵与长期验收完成。P1 仍需 center-secondary/secondary-interceptor/peer 分区、digest conflict、缩编/整盟重构、恢复合并和误降级成对标定。

2026-07-11 P2 隔离 replay 结果：`center_secondary_distributed` 与 `member_loss_replacement` 均 7 轮收敛、完成率 1.0、冲突计数分别 2/1、相对隔离单槽最优基线的绝对差距均为 0.0；missing ACK、stale epoch、expired lease、partition 分别在 2/1/2/3 轮进入 `aborted|reconfiguring`，完成率 0，并给出 optimality-gap unavailable reason。原生 6 场景预期结果满足率 6/6，平均完成率 1/3，总冲突计数 5。MIT CBBA 与 CA-CBBA 未配置本地参考树，输出 path-not-configured capability/unavailable；探测到 MIT MATLAB 源码时仍因 runtime adapter 未集成而 unavailable，CA-CBBA 公共参考仅有 metadata 时报告无可执行源码。该结果不能解释为外部算法性能较差。

D4 模块内已经完成可测试的离线 P1 合同与 P0-B 降级层级硬化：`C2Health`、heartbeat smoothing、被动降级、固定系留/机动高空二级节点分类元数据、二级节点 lifecycle、二级能力评分与 `not_ready|visible_only|registration_usable|takeover_ready` readiness class、主动降级仲裁、主动降级硬/软风险分层、false-trigger metadata、secondary takeover plan lease/epoch strictness、主动降级 `necessary/unnecessary/inconclusive` review label、pre/post review window、plan activation delay、二级接管必要性/成功统计 metadata、D1/D2/D3/D5 adapter、D5 distributed visual evidence 归一化、完全无中心 CBBA 风险加权、CBBA cost gap benchmark helper、CBBA D6 report metadata、`assignment_audit`、D6-compatible event metadata、中心恢复基础合并和 N 规模输入均已存在。

2026-07-12 真实 AirSim 2v2 pilot `p1_5m_2v2_pilot_fix2_20260712/episode_006_full_flow` 暴露了 D4 terminal consistency 语义缺口：D5 的短时 `ambiguous/reacquire` 在 assigned/expected global track、resource 和 current plan 均一致且无 friend/duplicate/mismatch 时，旧实现仍立即输出 `terminal_consistent=false`，导致 D7 以 `d4_terminal_inconsistent` 清空 terminal delivery，而 D4 action 同时仍为 `continue_center`。D4/D7 合同复核进一步确认 `non_locked_frame_limit=3` 应表示可容忍 3 个连续 loss frame，与 D7 第 3 帧后进入 bounded coast 对齐，而不是只容忍 frame 1、2。修正后，`terminal_consistent` 表示 D4 是否仍信任中心 plan binding，不替代 D5/D7 的视觉锁定和 handoff gate；无硬冲突的 `ambiguous/reacquire` 在 `consecutive_non_locked_frames <= non_locked_frame_limit` 时保留现有中心计划一致性和动作防抖，第 4 帧才进入持续 reacquire/fail-closed 路径。friend conflict、duplicate terminal lock、resource/global-track mismatch、历史 mismatch counter、not-current/stale plan 不使用该 grace，仍立即阻断；track/mismatch 证据显式输出 hard `d5_terminal_id_mismatch`，stale/not-current 仍优先 `request_center_replan`。main 应逐 pair 消费同一 D4 record 的 `d4_action`、`terminal_consistent`、`risk_factors`/`hard_risk_factors`、`plan_id` 和 `plan_version`；D5 lock/readiness 仍由其独立字段门控，不能由 `terminal_consistent=true` 推导为 visual PNG ready。

### 实施现状与历史基线

历史基线（截至 2026-07-08）：main/runtime 完成 P1 基线接线；episode bus 已消费 D4 adapter 输出，`request_center_replan` 可触发 D3 新 plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过。main runtime 还新增了 P1 D4/D5 calibration sweep，可按二级高度、FOV、二级节点数量和 standoff 组合批量生成 stress episode，并在 sweep 结束后自动调用 D6 标准 AirSim calibration report bundle，输出 records/summary/report 口径。该记录只描述当时集成基线，不替代最新 P1 合同验收。D4 模块边界保持不变：D4 不生成系统级 `AssignmentPlan`，只提供 `pending_secondary_plan`/`secondary_plan_active` metadata、仲裁记录和 CBBA 保底结果供 main/D3/D7 消费。

历史基线（2026-07-08）：AirSim 机动高空侦察节点 stress 输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`，3 seeds 均 connected=True；每个 seed 含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，所有 episode 均为 13 frames 且 image_ok=13。场景使用 5 个目标、5 个拦截相机、2 个二级侦察相机、200 m 高差、80 度 FOV 和 1920x1080；D4 主动作符合预期：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`。二级侦察侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。

历史基线（2026-07-10）：`p1_gap_closure_calibration_20260710` 完成 10 seeds、50/200 m、3 个机动高空二级节点、FOV 110 度、1920x1080 的 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m 下 network joint full-view 均值 0.023、最大 0.154，coverage 均值 0.685；200 m 下 network joint full-view 恒为 0.000，coverage 均值 0.708。两种高度均有有效投影和稳定注册，cross-view association 均值为 4.6/4.0，stable registration 均值为 86.3/96.7。该批次记录的是当时 network full-view 持续性断点，不代表当前二级 commit 正例状态。

P0 状态：无 P0 blocker。P0-B 在 D4 模块内已闭合到单元测试层：heartbeat 短时丢包/延迟经滑动窗口和 dwell 后才进入 failed；过期或非单调二级 plan 被标记为 not executable；二级能力评分区分 `visible_only`、`registration_usable` 和 `takeover_ready`，并记录 score input 明细；无冲突 reacquire 不直接降级。历史 2026-07-10 的 10-seed 决策明细中，1300 条记录均通过 heartbeat/link/cue/gimbal、visible 和 registered 检查，score 无低于 0.70；1285 条因 network full-view < 0.80 保持 `registration_usable`，其中 600 条还低于 coverage 0.65。其余 15 条瞬时 `takeover_ready` 只出现在 50 m 的 seed 2/5，均为 `pending_secondary_plan`，没有 active/executable plan，最终仍回落 distributed。该组数字是门限历史基线，不是最新 commit 状态。

2026-07-11 D4 readiness/接管 P1 已在模块内补齐并修复边沿初始化：硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；`D4ArbitrationAdapter` 默认要求 3 个不同时间戳决策、至少 0.2 s 持续且相邻 evidence gap <= 1.0 s，才把瞬时 `takeover_ready` 解释为 sustained readiness。同一 frame 的多次调用不会增加 streak；`not_ready -> takeover_ready` 和能力回落后的再次 ready 都会设置新的 `ready_since_s`、从 count=1 重新计时。lifecycle/event 逐决策记录 stable/not-registered value、presence、evidence source、streak、duration、sustained 和 fallback reason。pending/active 合同新增 source match、required lease epoch、lease expiry、transition、pending since、activated at、activation delay 与回落原因；heartbeat/link/cue/gimbal/lease/能力回落均有 distributed 或 pending/not-executable 负例。D2 online truth 隔离后，D4 还显式读取 `truth_metrics_available`/`continuity_available`：不可用的 IDSW/continuity 占位不触发降级，在线 ambiguity 和 track-quality-derived association risk 仍生效。连续 `duplicate_track_risk` 仅作 soft 观察，不能合成 hard observed duplicate；显式 count/delta/observed flag 仍立即阻断。历史 AirSim 记录缺真实逐决策 stable/not-registered 输入；最新合同 episode 已完成 secondary/peer commit DTO 和 action 接线，后续缺口是物理执行、完整扰动与多 seed 长期证据。D4 不生成 `AssignmentPlan`。

2026-07-11 中心重规划请求 lifecycle 已在 D4 模块侧闭合：冻结 `CenterReplanStatus` 携带 request/target/coalition/risk/state/timestamp/resolved-plan 字段，adapter 用排序去重后的 risk tuple 比较当前风险。`ActiveDegradationConfig.center_replan_cooldown_s=2.0`，以 resolved/requested time 为起点；pending/applied/no-change 在窗口内即使新增非硬风险也继续 suppress，严格到 `timestamp >= reference+2.0` 才重新开放。`terminal_persistent_disagreement` 保留首次请求和 D6 hard-risk 分类，但不绕过 cooldown；expired、中心 failed 以及 friend/重复锁/assignment-version/IDSW/coalition conflict 仍即时绕过。`continue_center` 保留 `terminal_consistent=False` 和 D5 风险供 D7 独立门控；`k=1` fallback 行为不变。

2026-07-11 D4 本地 P1 原子联盟合同已实现：冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 直接扩展现有 `CoalitionSafetyEvidence`。协调器校验双版本、epoch、成员身份、ACK 有效期、lease 和 digest；完整 ACK 后才能进入 committed/executing，缺 ACK、旧 epoch、过期 lease、网络分区或 digest 冲突进入 aborted/reconfiguring。中心正常仍使用现有路径；中心失效后，只有 secondary `takeover_ready` 或完全无中心 committed 联盟才设置 `atomic_coalition_formed=true`，否则保持 fail closed。event/D6 metadata 已输出 commit 状态、成员、epoch、coordinator 和 lease；恢复只输出双轨审计，不立即夺权。当前 D4 模块测试 144 项通过。

2026-07-11 center replan coalition convergence 已补齐：D4 读取 main 已传入的 D5 `CoalitionVisualSummary`，校验 current track/plan/coalition scope、完整 primary lock 集合、无 conflict，以及 commit-required 时 committed/executing 和 required ACK 完整。只有中心 alive 且当前决策无 friend/duplicate/wrong-binding/version/commit/health 硬冲突时，matching pending request 才可输出 `continue_center` 和 `resolution_hint=acknowledged_no_change`；同一 summary 对所有 current primary 给出一致 action。D4 不修改 main adapter；最小接口字段记录在 README。模块测试现为 144 项通过。

历史基线（2026-07-11、最终 P1 验证前）：`blocks_cv_m5_n2_liveness_batch_20260711` 的 seeds 7/17/27 均为 6 次重规划请求、6 次 `acknowledged_no_change`、0 次 applied、0 次 expired，需求满足率均为 1.0，错误重复锁均为 0，说明当时中心重规划请求 lifecycle 和合法多成员锁审计已稳定收敛。T002 的视觉共识帧为 4/5/4，D7 每个 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。该批次已被最新 10-seed/故障注入验收补充，只证明 ComputerVision 状态链，不代表 SimpleFlight 动力学控制、协同到达或物理拦截完成。

历史基线（2026-07-11 早期 smoke）：200 m/2 二级节点、50 m/2 二级节点和 200 m/5 二级节点三组 truth-isolated 场景中，预期二级接管正例因联合全覆盖率为 0.0 而保守回落到 distributed。当时结果未关闭 P1，但已被后续 ACK/commit 正负例验证取代为当前状态；它仍用于说明不得以平均覆盖替代同帧联合覆盖，也不得放宽 readiness 门限。

下一轮按以下顺序实施和验收：

1. 先保持 P0 回归，冻结现有 heartbeat、readiness、source/lease/version、重规划 lifecycle 和 `k>1` fail-closed 合同。
2. 保持已完成的 P1 联盟协商合同回归：`CoalitionMemberAck` 和 `CoalitionCommitState` 已覆盖 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted`，并携带 target/coalition/plan version、epoch、lease、required/acked members、能力证据时间和失败原因。
3. 保持已通过的二级 `executing` 3/3、peer `executing` 3/3 和缺 ACK `aborted` 2/3 正负例回归，不再重复列为待闭合能力。
4. 扩展旧 epoch、过期 lease、成员不可执行、center-secondary/secondary-interceptor/peer 分区、digest conflict、成员退出/重构和恢复的扰动矩阵；使用同 seed 正常/故障配对，由 D6 聚合误降级和恢复指标。
5. 将 SimpleFlight 15 s 保持为断点诊断，物理拦截验收由更长时长和更高控制频率的系统级试验单独关闭，不能用合同通过替代。
6. P2 只运行隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或恢复合并增强均不得替换本地轻量 CBBA 默认路径和 commit 安全合同。

任一步不满足都应保持 distributed/observe/hold，不降低 score、coverage、network full-view、持续窗口或版本安全门限。后续 D4 实现完成后运行：`PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`。

## 4. 被动降级与主动降级

### 4.1 被动降级

`passive_failover` 处理中心 C2 不可用：

- heartbeat 超过 hard timeout；
- heartbeat 滑动窗口内连续/累计 miss 达到 failed 阈值，且满足 `degraded/suspect` dwell；
- peer quorum 判定中心失败；
- assignment digest 或中心摘要长期不可用；
- center epoch 过期或倒退；
- 中心恢复后与 fallback 双轨日志无法合并。

被动降级顺序：

```text
center C2 normal
  -> C2 failed
  -> ground_backup / secondary_recon 接管区域协调
  -> secondary 不可用时进入 cluster representative / distributed CBBA
  -> CBBA 不收敛时 safe hold / continue observe / review
```

### 4.2 主动降级

`active_degradation` 处理中心未失效但局部证据不支持继续执行当前计划：

- D1：定位协方差、位置 sigma 或量测年龄过高；
- D2：ambiguity、`id_switch_count`、重复航迹或 continuity 风险升高；
- D3：plan stale、非 current、plan version 不匹配是硬风险；cost margin 过低是软证据，只说明当前方案容易抖动，不能单独触发中心重规划。
- D5：视觉候选与 assigned `global_track_id` 不一致、资源错配、重复末端锁定、cross-view 高风险或 friend conflict 是硬证据；无冲突的 `ambiguous/hold/reacquire` 多帧持续是软证据，优先继续观察或请求二级 cue。

主动降级的保守顺序：

1. D5 与 D3 分配一致且 D1/D2/D3 风险低：`continue_center`。
2. D3 版本/时效硬风险是主因且 D5 仍一致：`request_center_replan`。
3. D1/D2 风险升高但 D5 仍一致：`request_secondary_assist`。
4. 只有 cost margin 过低、D5 低置信度或无冲突 `ambiguous/reacquire` 时：`continue_center` 或 `request_secondary_assist`，继续观察，不重规划、不降级。
5. D5 单窗口不一致但未满足持续触发：若无硬风险则继续观察；若有二级覆盖且需要补充视角，则请求二级辅助。
6. D5 多帧不一致且存在 observed mismatch、资源错配、重复锁定或友方/身份冲突等硬证据时，才触发主动降级：有健康二级节点覆盖当前 `coverage_cell` 则 `degrade_to_secondary`。
7. 二级节点不可用、链路过期、heartbeat 过期或不覆盖区域，且硬不一致仍持续时才 `degrade_to_distributed`。
8. `friend_conflict=True` 或身份证据冲突：`hold_for_review`，不发布新计划。

## 5. `C2Health` 状态机

状态：

- `normal`：中心 heartbeat、digest 和 epoch 可信。
- `degraded`：中心质量下降，或 fallback/二级节点正在维持连续性。
- `suspect`：heartbeat stale、digest conflict、center epoch stale、peer 观察不一致或恢复待合并。
- `failed`：heartbeat hard timeout 或 peer quorum 判定中心不可用。

主要迁移：

```text
normal
  -> degraded : heartbeat jitter / warning threshold
  -> suspect  : heartbeat stale / digest conflict / center epoch stale

degraded
  -> suspect  : backup lease conflict / summary conflict / recovery pending merge
  -> failed   : peer quorum failed / heartbeat failure timeout
  -> normal   : dual-track merge accepted

suspect
  -> degraded : fallback leader or secondary node keeps continuity
  -> failed   : hard timeout or quorum
  -> normal   : center/fallback logs cleanly merge and human_accept=True

failed
  -> degraded : fallback leader elected or secondary takeover starts
  -> suspect  : center heartbeat/digest recovered but merge not accepted
  -> normal   : only after clean merge and explicit acceptance
```

当前代码证据：

- `FailoverCoordinator.observe_center()` 在 heartbeat/digest 恢复后进入 `suspect`，不直接回 `normal`。
- `update_health()` 覆盖 heartbeat warning/stale/failure、peer quorum、heartbeat sliding window、miss threshold 和 `degraded/suspect` dwell；有 heartbeat 样本流时，单次延迟不会直接 `failed`。
- `merge_recovery()` 只比较 assignment owner/epoch 的基础版双轨合并；冲突或 review 未清空时保持 `degraded`。

## 6. 摘要接口

### 6.1 被动降级和 CBBA 摘要

- `TrackSummary`：`track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`、`visual_evidence`。
- `ResourceSummary`：`node_id`、`capability_class`、`availability_band`、`comm_band`、`operator_hold`、`takeover_priority`、`lease_epoch`、`lease_expires_at_s`、`node_role`、`coordinator_only`、`coverage_cell`、`heartbeat_timestamp_s`、`heartbeat_stale_after_s`、`cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_full_view_rate`、`cross_view_support_count`、`stable_cross_view_registration_count`、`not_registered_count`、`epoch`。
- `BidState`：`task_id`、`bidder`、`score`、`constraints_hash`、`epoch`、`round_id`。
- `CBBAResult`：assignments、rounds、converged、conflict/completion/message/byte 指标、`final_views`、`assignment_audit`、可选 `cost_gap_benchmark`；`build_cbba_d6_metadata()` 可将这些字段归一化为 D6 多 seed 报告 metadata。

### 6.2 主动降级摘要

- `TrackUncertaintySummary`：D1 定位质量，含 `position_sigma_m`、`covariance_trace`、`velocity_sigma_mps`、`measurement_age_s` 和 `coverage_cell`。
- `AssociationRiskSummary`：D2 关联风险，含 `ambiguity_score`、`id_switch_count`、`duplicate_track_count`、`track_continuity`、`truth_metrics_available` 和 `continuity_available`。后两个字段决定 truth-based IDSW/continuity 是否可用于在线仲裁；不影响在线 ambiguity、duplicate 和质量风险。
- `AssignmentValiditySummary`：D3 分配有效性，含 `global_track_id`、`assigned_resource_id`、`plan_version`、`is_current`、`plan_age_s`、`cost_margin` 和证据 metadata。`plan_age_s` 是最近评估活性年龄，优先读取 `plan.metadata.last_evaluated_at_s` 及兼容同义字段，缺失时回退 `created_at`；计划身份年龄单独记录为 `metadata.identity_age_s`。
- `TerminalAssociationSummary`：D5 末端关联，含 `decision_state`、confidence、ambiguity、observed/assigned `global_track_id`、连续非锁定/不一致帧数、friend conflict、duplicate lock、cross-view 风险，以及 D5 二级覆盖/转换漏斗字段 `cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap`、`secondary_detect_to_cross_view_reject_reasons`、`secondary_detect_available_but_not_registered`。
- `CommunicationSummary`：链路摘要，含 source/target/relay、`link_type`、sent/received timestamp、`payload_kind`、`stale_after_s`、sequence id。
- `SecondaryNodeLifecycleSummary`：除 heartbeat、lease、coverage、cue/gimbal/link、registration 与四级 readiness 外，新增 `registration_evidence_source`、stable/not-registered presence、takeover-ready consecutive decisions/since/duration/required values、`takeover_ready_sustained` 和 fallback reason。
- `D4DecisionRecord`：adapter 输出，可转为 D6 `EventRecord` kwargs；除既有 review、risk、coverage 和 plan 字段外，新增逐决策 readiness/evidence 审计、`secondary_takeover_previous_state/transition/fallback_reason`、pending since、activated at、activation delay、required lease epoch 和 source-match 结果。

### 6.3 二级接管 plan lifecycle metadata

D4 不生成完整系统级 `AssignmentPlan`，但在 `degrade_to_secondary` 触发时通过 `SecondaryTakeoverPlanMetadata` 给 main/D3/D7 提供可消费状态：

- `not_applicable`：非二级接管动作；当前 active plan owner 仍是 center、distributed_cbba 或 hold_review。
- `pending_secondary_plan`：只有 sustained `takeover_ready` 才能进入。D4 已选择二级节点并触发重分配，但新 plan 尚未生效；当前 owner 保持不变，并记录 source、supersedes、pending since/duration 和 reject reason。
- `secondary_plan_active`：main/D3 已回填新的 plan id/version、正确 source、满足节点要求的 lease epoch 和未过期 lease，且 sustained readiness 未回落；`active_plan_owner=secondary_node`、`secondary_reassignment_complete=True`。D7 还必须检查 current binding；瞬时 readiness 不允许放行。

metadata 字段包括 `secondary_takeover_state`、`active_plan_owner`、`secondary_plan_source_node_id`、`secondary_plan_id/version`、`secondary_plan_lease_epoch`、`secondary_plan_lease_expires_at_s`、`secondary_plan_lease_valid`、`secondary_plan_epoch_monotonic`、`secondary_plan_executable`、`secondary_plan_reject_reason`、`recovery_dual_track_audit`、`secondary_supersedes_plan_id/version` 和 `secondary_reassignment_complete`。过期或非单调替换二级 plan 保持 `pending_secondary_plan`/not executable，不能被解释为可执行接管计划；若当前 plan owner 已是 secondary 且 current/secondary plan id/version 相同，则该 equality 表示同一二级计划已经激活。

D5 二级 detect 覆盖可见、`gimbal_pointing_ok=True` 或 `secondary_coverage_ratio > 0` 只说明二级节点具备侦察证据；只有 main/D3 回填新的二级 plan id/version 且显式 `secondary_plan_active=True` 时，D4 才把接管 metadata 置为 `secondary_plan_active`。若 cross-view association 为 0，或 D5 在 global binding/registration 漏斗处拒绝，D4 仅记录 `secondary_detect_available_but_not_registered` 诊断，保持 `request_secondary_assist`/pending 或按既有硬冲突规则降级。

### 6.4 二级侦察校准解释口径

D4 不直接做视觉注册、相机投影、bbox 几何门控或多视角 ID 绑定；这些由 D5/main 产生，再由 D6 聚合。D4 只消费下列摘要并写入仲裁事件：coverage、heartbeat/link/cue freshness、gimbal pointing、stable cross-view registration、not-registered 诊断、三值 review label 和 plan activation metadata。

为避免把“看见目标”等同于“可接管分配”，D4 把二级侦察状态记录为四级 readiness class。lifecycle 保留节点类型字段，event metadata 顶层 `secondary_capability_class` 表示 readiness：

- `not_ready`：coverage、heartbeat、link、cue、lease 或 gimbal 条件不足，不能作为辅助或接管依据。
- `visible_only`：二级可见但未注册，常见证据为 `secondary_detect_available_but_not_registered=True`、`cross_view_association_count=0`、`not_registered_count>0` 且无稳定注册，或 reject reasons 包含 global binding/registration 断点。D4 只记录诊断或请求二级辅助，不把该证据升级成 `secondary_plan_active`。
- `registration_usable`：已有 `stable_cross_view_registration_count`、`cross_view_support_count` 或 `cross_view_association_count`，但 `secondary_network_joint_full_view_frame_rate`/`secondary_network_full_view_gap`、coverage 或综合 score 还不到接管阈值。D4 把它作为接管必要性审计和阈值标定输入，不直接放行 D7 visual PNG gate。
- `takeover_ready`：coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、稳定注册和综合 score 均满足 D4 gate。只有该状态才可作为 `degrade_to_secondary` 接管依据；D7 handoff 必须看到 `secondary_capability_class=takeover_ready`，系统级 plan owner/version 仍必须由 main/D3 回填。

### 6.5 D5 分布式视觉证据摘要

`DistributedVisualEvidenceSummary` 用于完全无中心 CBBA 的风险加权，字段包括：

- `visual_support_resource_ids`、`hold_resource_ids`、`ambiguous_resource_ids`、`duplicate_lock_resource_ids`；
- upstream `assigned_global_track_id`；
- terminal confidence/ambiguity、hypothesis/support count；
- `hypothesis_only`、`stale_global_track_id`、`missing_global_track_id`、`duplicate_terminal_lock_risk`；
- `friend_conflict`、`global_track_id_conflict`、`local_id_conflict` 和 `risk_reasons`。

D4 的 adapter 使用 duck typing/dict 归一化 D5 distributed terminal association 或 cross-peer hypothesis，不导入 D5 类型，也不生成新 ID。

## 7. CBBA 保底模型

当前完全无中心模式使用本地轻量 `CBBANegotiator`。它不是 MIT CBBA/CA-CBBA 的外部实现，也不是独立 single-round auction 或 contract-net。

任务为 `TrackSummary`，资源为可执行 `ResourceSummary`；`coordinator_only=True` 的二级节点只参与协调审计，不作为执行资源出价。

合成打分基线：

```text
score = 2.0 * confidence
      + 1.4 * availability
      + 0.5 * comm
      + 1.2 * capability_match
      + 1.0 * source_bonus
      - 0.8 * age_penalty
      + D5_visual_adjustment
```

winner/bid 扩散使用确定性 tie-break：更高 score、更新 epoch、较小 bidder id、较小 constraints hash。节点失去 bundle 中的任务后会释放该任务及后续任务，再重建 bundle。

### 7.1 D5 visual evidence 风险加权

D5 分布式视觉证据在 CBBA 中只作为风险/代价项：

- 支持同一个 upstream `global_track_id` 的 peer evidence 会提高对应资源出价。
- `hypothesis_only` 只给弱正向加权。
- `hold`、friend conflict、stale/missing/conflicting `global_track_id` 会阻止该任务产生可执行 bid。
- local/global ID conflict 会扣分或阻止执行，取决于风险类型。
- duplicate terminal lock 会进入 `assignment_audit` 并强惩罚相关资源；CBBA 的 single-winner 规则仍保证一个任务只有一个 owner。
- D4 不构造虚拟中心 Hungarian，不把多 peer 视觉支持转化为中心化 cost matrix，不改写 `global_track_id`。

### 7.2 收敛与失败边界

在连通 peer 图、静态 epoch、确定性 tie-break、有限 bundle length 和足够轮数下，winner view 预期收敛。丢包和延迟会增加 takeover wall-clock time；若 `converged=False`，`plan_degraded()` 不应把空 assignments 当成有效计划发布，只保留审计。

通信复杂度为：

```text
O(|E| * |T|)
```

全连接 N 节点约为 `O(N^2 * |T|)`；稀疏链路减少单轮消息量，但增加传播轮数。

### 7.3 CBBA vs 中心化 cost gap benchmark

`build_cbba_cost_gap_benchmark()` 只做离线对照，不在完全无中心路径运行中心化 Hungarian。输入必须来自 D3/main：

- `center_assignments`：D3 当前中心化计划或 Hungarian/Min Cost Flow 结果的 task -> owner 映射；
- `cost_by_task_resource`：同一场景下 D3 保存的 task/resource cost matrix；
- `CBBAResult`：D4 轻量 CBBA 的 assignments、completion、conflict、rounds 和 message 指标。

输出 `CBBACostGapBenchmark`，字段包括 `cbba_total_cost`、`center_total_cost`、`absolute_cost_gap`、`relative_cost_gap`、assignment/completion 差距、CBBA conflict/round/message 指标、缺失 task 和缺失 cost pair 审计。若任一已分配 task/resource cost 缺失，总 cost/gap 保持 `None`，避免伪造可比结果。

## 8. 二级节点 lifecycle 与接管

二级节点在代码中通过 `NodeRole.GROUND_BACKUP`、`NodeRole.SECONDARY_RECON`、`NodeRole.FIXED_TETHERED_SECONDARY`、`NodeRole.MOBILE_HIGH_RECON`、`NodeRole.MOBILE_SECONDARY_RECON`，或等价 `capability_class=fixed_tethered_secondary/tethered_recon/mobile_high_recon/mobile_secondary_recon` 建模。可用性判断包括：

- `availability_band != none`；
- `operator_hold=False`；
- `coverage_cell` 为空、覆盖当前区域，或机动二级节点提供正的 `secondary_coverage_ratio`；
- heartbeat 未超过 `heartbeat_stale_after_s`；
- 若给出 `cue_freshness_s`，必须未超过节点 freshness 窗口；
- 若给出 `gimbal_pointing_ok=False`，不得作为二级候选；
- 若传入 `CommunicationSummary[]`，必须存在新鲜的 `c2_direct`、`secondary_relay` 或 `video_cue` 等可用链路。

机动高空侦察节点随拦截机出动、不拦截，正常时用 D1/D2 `GlobalTrack` 或 radar cue 指向目标簇，并给局部拦截群提供图像、coverage 和 cross-view evidence。中心失效、或主动降级硬条件满足且二级候选可用时，它可作为二级协调节点；但仅有侦察图像、cue freshness、云台指向或 coverage ratio 不能绕过 D3 plan version、D5 身份/友方约束或 D4 既有 action 门控。

被动降级中，`FailoverCoordinator.elect_leader_resource()` 的排序为：

```text
takeover_priority
-> node_role rank
-> newer lease_epoch
-> availability
-> comm
-> capability
-> node_id
```

主动降级中，`ActiveDegradationArbiter._select_secondary_node()` 会按覆盖区/coverage ratio、network full-view rate、heartbeat、lease expiry、cue freshness、gimbal pointing、链路 freshness、stable registration count 和 not-registered count 过滤候选。辅助 cue 可使用 visible/fresh 二级节点；`degrade_to_secondary` 必须满足 `secondary_readiness_class=takeover_ready` 和 `secondary_takeover_capable=True`。排序口径为 `takeover_priority -> secondary_capability_score -> capability class -> lease_epoch -> node_id`。

## 9. D6 事件与指标

`D4DecisionRecord.to_event_record_kwargs()` 当前可输出 D6 兼容字段：

- `event_type`：`d4_arbitration_decision`、`active_degradation_decision` 或 `passive_failover_start`；
- `severity`：正常继续中心为 `info`，降级/hold 为 `warning`；
- metadata：`d4_action`、`degradation_mode`、`d4_degradation_mode`、`selected_coordinator`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp`、`review_label`、`active_degradation_review_label`、`active_degradation_necessity_label`、`review_label_detail`、`review_label_source`、pre/post review window、resource/track/plan/version、`active_plan_owner`、`secondary_takeover_state`、`secondary_plan_source_node_id`、`secondary_plan_id/version`、lease/executable/reject reason、`recovery_dual_track_audit`、`secondary_supersedes_plan_id/version`、`secondary_reassignment_complete`、`secondary_plan_activation_delay_s`、`secondary_plan_pending_duration_s`、`secondary_takeover_candidate`、`secondary_takeover_success`、`secondary_takeover_necessity_label`、`coverage_cell`、`terminal_consistent`、`risk_factors`、hard/soft risk、false-trigger candidate、`secondary_available`、`communication_fresh`、`secondary_lifecycle`、二级 diagnostic 节点 heartbeat/link/cue/gimbal/coverage/capability 字段、readiness `secondary_capability_class`、`secondary_capability_inputs`、`cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_coverage_available`、`secondary_network_full_view_gap`、`cross_view_support_count`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap`、`secondary_detect_to_registration_gap`、`secondary_detect_to_cross_view_reject_reasons`、`secondary_detect_available_but_not_registered`、`secondary_detect_to_cross_view_diagnostic`、`requires_human_review`。

`ActiveDegradationDecision.to_metrics()` 可输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate` 和 `distributed_conflict_count`。

`build_cbba_d6_metadata()` 可从 `CBBAResult` 输出被动/完全无中心侧多 seed 字段：`d4_action`、`coordination_mode`、`selected_coordinator`、leader/coverage、`failover_time`、consensus/conflict/completion/message 指标、`assignment_audit` 和可选 `cost_gap_benchmark` 扁平字段。`run_failover_simulation()` 顶层 metrics 已透出 `coordination_mode`、leader 和 coverage，避免二级接管与完全分布式 CBBA 在报告中混淆。

## 10. N 规模输入

D4 不写死 2v2 或 5v5。当前行为：

- `run_failover_simulation()` 按 `resources`/`tasks` 实际列表长度运行；若未传列表，则按 `node_count`/`task_count` 构造摘要。
- CLI `--drone-count N` 只决定默认资源/任务数量，`--nodes` 是 legacy alias。
- CBBA 使用 `node_ids`、`TrackSummary[]` 和 `ResourceSummary[]` 长度运行。
- 2v2/5v5 只作为 AirSim baseline 或测试命名，不是算法限制。

### 10.1 M 对 N 联盟任务边界

2026-07-11 文献和开源实现审计确认：目标需求 `k_j > 1` 时，问题不再是当前 single-winner CBBA 的普通 N 规模扩展。当前 `TrackSummary -> one owner` 合同只能表示一对一保底分配；将高威胁目标复制成三条任务无法原子保证成员集合、异构能力、共同/波次到达窗口和成员退出后的重构一致性。

D4 已完成 fail-closed 与本地 commit 合同：`CoalitionSafetyEvidence` 读取 D3 schema v2 的 coalition/member/version/demand，中心可用且完整合法时允许中心路径继续；中心失效后可选消费 `CoalitionCommitState`。`CoalitionCommitCoordinator` 只有在 target、双版本、epoch、成员身份、全部 ACK、lease 和 digest 均有效时才形成 atomic fallback；否则输出 hold/reconfigure。`FailoverCoordinator` 仍不对 `k_j>1` 运行 single-winner CBBA，避免把成员选择与原子提交混为一谈。合法联盟内多个授权成员锁同一 `global_track_id` 不算 duplicate；越权/超额成员和旧版本均拒绝。reserve 激活、补位/缩编、基于能力的成员形成算法和真实 episode DTO 路由保持 deferred。D4 不替代 D7 到达可达性判定，也不改写 `global_track_id`。

真实证据 `airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 暴露了原门控缺口：中心 owner 仍为 `center`，T001 coalition `k=3`、complete、plan/coalition version current，但 D5 长期 `reacquire` 后 arbiter 候选进入 `degrade_to_distributed`。静态 `coalition_center_plan_valid` 不等于 single-winner distributed path 已支持原子联盟；本轮修正将该候选改为中心重规划。

## 11. 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `C2Health` | `normal/degraded/suspect/failed`、heartbeat warning/stale/failure、sliding window/miss threshold/dwell、peer quorum、digest conflict、center epoch stale、恢复待合并 | `coordinator.py`、`models.py`、`tests/test_health.py` |
| 被动降级 | 中心 failed 后才执行 `plan_degraded()`；可选 ground backup/fixed tethered secondary/mobile high recon/representative；不收敛不发布有效 assignments | `coordinator.py`、`tests/test_coordinator.py` |
| 二级节点 lifecycle | heartbeat age/stale、lease epoch/expiry、coverage、requested coverage match、video/cue freshness、cue stale、gimbal pointing、coverage ratio、network full-view rate、stable registration/not-registered count、固定/机动二级分类、link stale/fresh、`secondary_available`、visible/registered/takeover_capable、`secondary_readiness_class`、capability score 和 score inputs | `active_degradation.py`、`models.py`、`tests/test_active_degradation.py` |
| 主动降级仲裁 | 输出 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary`、`degrade_to_distributed`、`hold_for_review`；2026-07-07 已区分硬风险和软证据，避免 cost margin 低、低终端置信度或无冲突 `ambiguous/reacquire` 导致每帧重规划/降级；当前无冲突 `reacquire` 只请求二级 cue/继续观察，不直接接管 | `active_degradation.py`、`tests/test_active_degradation.py` |
| D1/D2/D3/D5 adapter | duck typing/dict 读取 covariance/age、ambiguity/IDSW/continuity、plan/version/freshness/cost、terminal/cross-view/friend conflict，并归一化 dict/object 形式二级节点的 `role/capability_class/cue_freshness/gimbal/coverage` | `adapter.py`、`tests/test_arbitration_adapter.py` |
| M-to-N 原子联盟安全门控 | schema v2 coalition/member/双版本校验；member ACK、commit lifecycle、lease/epoch、digest 和 fail-closed 已实现。最新验证中二级与 peer 均 ACK 3/3 `executing`，缺 ACK 为 2/3 `aborted`；无有效 commit 时仍 replan/hold。合法授权多锁不算 duplicate；single-winner CBBA 不承担 `k>1` 成员形成 | `coalition_safety.py`、`adapter.py`、`coordinator.py`、`tests/test_coalition_safety.py`、`tests/test_coalition_commit.py` |
| D5 distributed visual evidence normalization | `build_distributed_visual_evidence_summary()`、`attach_distributed_visual_evidence()`、`merge_distributed_visual_evidence_into_tracks()` | `adapter.py`、`tests/test_arbitration_adapter.py` |
| 完全无中心 CBBA 风险加权 | D5 visual support 调整出价；hold/friend/stale/missing/conflicting ID 阻止 bid；duplicate lock 风险审计 | `cbba.py`、`tests/test_cbba.py` |
| `assignment_audit` | 输出 owner、visual support、hold/ambiguous/duplicate IDs、confidence/ambiguity、hypothesis、ID 风险和 reason | `cbba.py`、`tests/test_cbba.py` |
| D6 event metadata | `D4DecisionRecord.to_event_record_kwargs()` 输出 D6-compatible kwargs 和 metadata，含三值 review label、`active_degradation_necessity_label`、pre/post window、secondary diagnostic、network coverage gap、readiness class、capability score inputs、stable/not-registered count、lease/executable/reject reason、hard/soft risk、false-trigger candidate、plan activation delay 和 takeover necessity/success 字段 | `adapter.py`、`tests/test_arbitration_adapter.py` |
| D6 CBBA report metadata | `build_cbba_d6_metadata()` 输出 coordination mode、leader、coverage、CBBA 收敛/通信/审计指标和 cost gap 扁平字段；`run_failover_simulation()` 顶层 metrics 透出 secondary/distributed 分组字段 | `cbba.py`、`simulation.py`、`tests/test_cbba.py`、`tests/test_simulation.py` |
| D7 二级接管门控辅助 | `build_d7_secondary_handoff()` 阶段 1 不放行 visual PNG，阶段 2 必须带新 plan id/version，且二级 plan lease 未过期、epoch 单调；只有显式 `secondary_capability_class=takeover_ready` 放行，`visible_only`、`registration_usable` 或缺失 readiness 均阻止 visual PNG | `active_degradation.py`、`tests/test_airsim_phase1_dry_run_contracts.py` |
| secondary takeover plan metadata | `SecondaryTakeoverPlanMetadata` 输出 pending/active 状态、当前/二级 plan id/version、source node、lease epoch/expiry、epoch monotonic、executable/reject reason、恢复双轨审计、supersedes plan 和 reassignment complete 字段；过期二级 plan 不可执行；当前 secondary-owned 同 id/version plan 可保持 active，不被误判为非单调替换；D4 不生成系统级 `AssignmentPlan` | `active_degradation.py`、`adapter.py`、`tests/test_arbitration_adapter.py` |
| CBBA vs 中心化 cost gap helper | `build_cbba_cost_gap_benchmark()` 对比 D4 CBBA result 与 D3/main 提供的中心 plan/cost matrix，输出 cost/completion/conflict/message gap 字段 | `models.py`、`cbba.py`、`tests/test_cbba.py` |
| main/runtime P1 消费基线 | main 已接入 D4 adapter event、`request_center_replan -> D3 new version`、secondary takeover owner/version 和 D7 owner gate；controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已能批量改变二级节点高度/FOV/数量/standoff，并自动生成 D6 AirSim calibration report bundle。此项为 main-owned 集成证据，修复后口径为 main/D3/D7 消费 owner/version，D4 只消费/输出仲裁与 metadata，不生成系统级 `AssignmentPlan` | `research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_main_episode_bus_marks_secondary_takeover_plan_for_d7`、`::test_controlled_2v2_active_degradation_secondary_plan_visual_png` |
| N 规模输入 | 仿真、CBBA 和测试按输入列表长度运行 | `simulation.py`、`scripts/run_failover_simulation.py`、`tests/test_simulation.py`、`tests/test_cbba.py` |

## 12. 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| main runtime bus 真实 episode 接线 | D4 adapter、D6 event、二级与 peer commit 正例、缺 ACK fail-closed 和 calibration sweep 已接线；二级/peer ACK 3/3 `executing`，缺 ACK 2/3 `aborted` | 完整 heartbeat/link/cue、旧 epoch/lease、成员不可执行、分区/digest conflict、成员退出/重构和误降级扰动矩阵仍开放 | main 继续使用同一 schema，增加成对扰动和多 seed 聚合 |
| D3 `request_center_replan` 自动调用 | D4 能输出 `request_center_replan` 并说明风险因素；main 已监听该 action 并触发 D3 新 plan version | 真实多 seed 下仍需确认硬 stale/not-current 和真实 terminal mismatch 的触发频率，避免软风险回归成每帧 replan | main/D3 保持 owner/version/supersedes 字段和 stale rejection，并用多 seed 报告校准 |
| secondary takeover plan owner/version 闭环 | D4 已实现 sustained gate、逐决策 evidence、pending/active transition、source/lease epoch/expiry strictness；最新二级正例由 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` | 正例已闭合合同层；仍需在完整扰动矩阵中统计回落、恢复和误降级 | 保持正例回归，并扩展 lease/分区/成员故障成对样本；不放宽门限 |
| 完整 C2 双轨审计 | 已记录 health transition 和 assignment-only merge | 尚未比较完整 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态 | main/runtime 需要持久化中心和 fallback 双轨 episode log，D6 消费 merge outcome |
| D4/D5 stress 统一口径 | 历史 60-case freshness 基线、最新二级/peer commit 正例和缺 ACK 负例均可审计 | 仍缺完整扰动矩阵、coverage-cell 切换、成员退出/重构和多 seed 恢复统计 | main/runtime 使用同一 schema 增加成对扰动 case，统计 readiness 驻留、回落和恢复 |
| D5 distributed visual evidence 运行时合流 | D4 模块内可把 D5 多 peer evidence merge 到 `TrackSummary.visual_evidence` | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重仍需标定 | main 在 no-center case 持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线 |
| CBBA 与中心化最优 gap | D4 已有 `CBBACostGapBenchmark`、`build_cbba_cost_gap_benchmark()` 和 `build_cbba_d6_metadata()`，可对 D3/main 提供的中心 plan/cost matrix 计算 cost/completion/conflict/message gap 并输出 D6 多 seed 报告字段 | 真实 episode 还未持续保存同场景 D3 cost matrix/current plan，也未由 D6 汇总多 seed gap | main/D3 保存中心化 cost matrix/current plan，D6 聚合 benchmark 输出 |

## 13. 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CA-CBBA optional replay | 已实现隔离 path/source capability adapter 和逐场景 unavailable 结果；未 import/执行外部实现 | MIT 参考为 MATLAB 且未集成 runtime；CA-CBBA 公共参考没有可执行源码；默认测试不能依赖外部工程 | 若未来获得合法可执行源码与 runtime，另加离线 execution adapter 和同预算结果校验；不得进入默认路径 | P2 capability 已完成 / execution unavailable |
| 独立 auction baseline | 未单独实现 single-round auction，后置为可选对照基线 | 当前 `CBBANegotiator` 有 winner/bid 共识和 D5 visual evidence 加权，但不是独立拍卖状态机；P1 主线先保证 adapter 接线和 CBBA gap benchmark | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P2 后置 |
| Contract Net | 未实现 manager/contractor announce-bid-award 状态机 | 二级节点健康时仍需和 D3 plan version 对齐；manager 失效后还要 fallback 到 peer consensus | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是摘要和内存网络，真实链路属于 main/runtime/D5/D1 | runtime 生成 LinkRecord/video metadata；D5/D1 处理图像、检测、标定和 cue schema | P2/P3 |
| 虚拟中心 Hungarian | 明确不实现为 no-center fallback | 完全无中心模式不能伪造中心权威或改写 `global_track_id`；中心化最优属于 D3/main | 若要对照，只能做离线 benchmark，不得替代 D4 CBBA 保底 | 不做主线 |
| D4 直接生成系统级 `AssignmentPlan` | 不作为 D4 能力实现；D4 只输出仲裁/metadata/CBBA 保底结果 | D3/main 拥有 plan schema、plan owner、版本策略和 stale rejection；main P1 已接入 secondary owner/version 消费基线 | D4 继续保持不生成系统级计划，必要字段通过 `SecondaryTakeoverPlanMetadata` 输出 | 非 D4 主线 |
| 自主成员形成与联盟重构算法 | 二级/peer 原子 commit 与缺 ACK fail-closed 的真实正负例已通过；尚未实现自主 `k_j>1` 成员形成、reserve/补位/缩编/整盟重构或 CCBBA/grouping | 当前 single-winner CBBA 不能替代成员形成与时序可达性 | P1 保持 commit 合同并完成扰动/重构矩阵；可选形成算法只做 P2 隔离对照 | P1 扰动 / P2 隔离 benchmark |

## 14. P1/P2 下一步

P1：

0. **M 对 N 联盟合同保持回归**：P1 合同层已闭合；固定回归二级 ACK 3/3 `executing`、peer ACK 3/3 `executing` 和缺 ACK 2/3 `aborted`。继续研究 `simultaneous|sequential|mixed`、reserve、成员退出缩编/补位/整盟重组，但不得把这些开放项误写成 commit 正例未闭合。
1. D4 模块内的逐决策 stable/not-registered source/presence、连续 readiness 窗口、pending/active transition、source/lease strictness 和 heartbeat/link/cue/gimbal/能力回落负例已完成；后续保持这些合同回归，不再作为代码缺口。
2. 保持已通过的 secondary/peer executing 与缺 ACK aborted 场景，继续统计 activation delay、回落原因和恢复窗口，不降低门限。
3. 增加 heartbeat、lease、video/cue freshness、link stale 和 gimbal 异常 seed，验证这些门限在 network coverage 改善后仍能独立阻断接管；同时记录 plan activation delay 和恢复双轨窗口。D4 只消费这些摘要，不负责修正 D5 几何注册。
4. 增加网络分区专项：分别注入 center-secondary 断链、secondary-interceptor 断链、peer 图分裂和恢复重连，记录 `partition_state`、peer/digest 冲突、局部重复 owner、CBBA 收敛/冲突、恢复 merge audit 和恢复时间；分区侧不得绕过 plan version、lease 或 D5 友方/身份门控。
5. 使用同 seed 的正常/故障成对场景标定误降级：正常场景应保持 `continue_center`，硬失效/持续硬不一致场景才应进入预期降级动作；由 D6 统计 false-degradation rate、missed-degradation rate、active-degradation precision、动作混淆矩阵和 dwell/release 抖动。阈值调整必须基于成对证据。
6. 在完全无中心 case 中持续把 D5 distributed visual evidence 合流到 `TrackSummary.visual_evidence`，并用多 seed 报告确认 CBBA completion/conflict/cost gap/round/message 指标。
7. main/D3 继续保存同场景中心化 cost matrix/current plan，D6 聚合 D4 `CBBACostGapBenchmark` 多 seed 指标；轻量 CBBA 仍为默认保底。

P2：

1. **已完成 capability 收尾**：MIT CBBA/CA-CBBA 可选路径探测、标准 unavailable 行和原生 6 场景 replay 已实现；默认不执行外部工程。未来只有在许可证、源码和 runtime 均可用时才增加 execution adapter，并保持同一结果 schema。
2. 在多 seed CBBA gap benchmark 稳定后，可选实现独立 single-round auction baseline，用同一 `TrackSummary[]`/`ResourceSummary[]`/D5 evidence 输入与 CBBA 对照。
3. 设计 Contract Net 的 manager/contractor 状态机、超时、拒绝/重招标和 manager 失效回退规则。
4. 扩展 `merge_recovery()`，加入 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态和多轮稳定窗口。
5. 若 P1 多 seed 校准暴露恢复抖动，再扩展 `merge_recovery()` 的多轮稳定窗口和状态审计。

## 15. 验收命令

```bash
git diff --check -- research_modules/d4_distributed_fallback subagent_reviews/D4_*
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
