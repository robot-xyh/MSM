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

D4 模块内已经完成一个可测试的离线 P1 骨架，并补齐 P0-B 降级层级硬化：`C2Health`、heartbeat smoothing、被动降级、固定系留/机动高空二级节点分类元数据、二级节点 lifecycle、二级能力评分与 `not_ready|visible_only|registration_usable|takeover_ready` readiness class、主动降级仲裁、主动降级硬/软风险分层、false-trigger metadata、secondary takeover plan lease/epoch strictness、主动降级 `necessary/unnecessary/inconclusive` review label、pre/post review window、plan activation delay、二级接管必要性/成功统计 metadata、D1/D2/D3/D5 adapter、D5 distributed visual evidence 归一化、完全无中心 CBBA 风险加权、CBBA cost gap benchmark helper、CBBA D6 report metadata、`assignment_audit`、D6-compatible event metadata、中心恢复基础合并和 N 规模输入均已存在。

截至 2026-07-08，main/runtime 已完成 P1 基线接线：episode bus 已消费 D4 adapter 输出，`request_center_replan` 可触发 D3 新 plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过。main runtime 还新增了 P1 D4/D5 calibration sweep，可按二级高度、FOV、二级节点数量和 standoff 组合批量生成 stress episode，并在 sweep 结束后自动调用 D6 标准 AirSim calibration report bundle，输出 records/summary/report 口径。D4 模块边界保持不变：D4 不生成系统级 `AssignmentPlan`，只提供 `pending_secondary_plan`/`secondary_plan_active` metadata、仲裁记录和 CBBA 保底结果供 main/D3/D7 消费。

2026-07-08 AirSim 机动高空侦察节点 stress 结果已进入当前 P1 状态判断：输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`，3 seeds 均 connected=True；每个 seed 含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，所有 episode 均为 13 frames 且 image_ok=13。场景使用 5 个目标、5 个拦截相机、2 个二级侦察相机、200 m 高差、80 度 FOV 和 1920x1080；D4 主动作符合预期：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`。二级侦察侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。

后续 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*` 单 seed 校准已经把 D6 stable registration/not-registered 口径跑通：200 m、FOV 110、1920x1080、3 个机动高空二级侦察相机、7 frames 下，D6 上游几何统计为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`，三类 case 的 stable cross-view registration 分别为 51/55/53，cross-view association 为 4/4/5，degradation case 的 not-registered 均为 35，平均二级网络全覆盖率为 0.048，平均覆盖率为 0.771，主要断点仍是 `not_all_targets_visible` / `network_union_incomplete`。该结果说明 registration 字段已经能由 D5/D6/main 写盘并被 D4 解释，但只有 1 个 seed，不能替代多 seed 标定；D4 不直接消费或计算 projection/geometry gate。

P0 状态：无 P0 blocker。P0-B 在 D4 模块内已闭合到单元测试层：heartbeat 短时丢包/延迟经滑动窗口和 dwell 后才进入 failed；过期或非单调二级 plan 被标记为 not executable；二级能力评分区分 `visible_only`、`registration_usable` 和 `takeover_ready`，并记录 score input 明细；无冲突 reacquire 不直接降级。剩余 P1 主要是运行层校准和离线标注填充，而不是 D4 文档或接口缺口：mobile recon 批次中二级网络同帧全覆盖仍为 0.0，case mean 的联合覆盖约 0.65-0.69；registration v2 批次虽出现 stable registration 计数，但 full-view 仍低且 degradation case not-registered 仍高。后续需继续校准二级 coverage、mobile recon heartbeat/link/cue freshness、稳定跨视角注册、二级接管必要性、plan activation delay 分布、D5 peer evidence 合流、人工/离线 review label 和 D6 长期聚合。

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
- `AssociationRiskSummary`：D2 关联风险，含 `ambiguity_score`、`id_switch_count`、`duplicate_track_count`、`track_continuity`。
- `AssignmentValiditySummary`：D3 分配有效性，含 `global_track_id`、`assigned_resource_id`、`plan_version`、`is_current`、`plan_age_s`、`cost_margin`。
- `TerminalAssociationSummary`：D5 末端关联，含 `decision_state`、confidence、ambiguity、observed/assigned `global_track_id`、连续非锁定/不一致帧数、friend conflict、duplicate lock、cross-view 风险，以及 D5 二级覆盖/转换漏斗字段 `cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap`、`secondary_detect_to_cross_view_reject_reasons`、`secondary_detect_available_but_not_registered`。
- `CommunicationSummary`：链路摘要，含 source/target/relay、`link_type`、sent/received timestamp、`payload_kind`、`stale_after_s`、sequence id。
- `SecondaryNodeLifecycleSummary`：二级节点 heartbeat age/stale、lease epoch/expiry、coverage、requested coverage match、video/cue freshness、cue stale、gimbal pointing、coverage ratio、network full-view rate、stable registration count、not-registered count、cross-view support、固定/机动二级分类、link stale/fresh、`secondary_available`、`secondary_visible`、`secondary_registered`、`secondary_takeover_capable`、`secondary_capability_score`、`secondary_readiness_class` 和 `secondary_capability_inputs`。
- `D4DecisionRecord`：adapter 输出，可转为 D6 `EventRecord` kwargs，包含三值 review label、`active_degradation_necessity_label`、pre/post review window、`active_plan_owner`、secondary takeover metadata、plan activation delay、lease/executable/reject reason、hard/soft risk、false-trigger candidate、二级 diagnostic 节点字段、readiness `secondary_capability_class`、capability score inputs 和 D5 detect-to-registration 诊断。

### 6.3 二级接管 plan lifecycle metadata

D4 不生成完整系统级 `AssignmentPlan`，但在 `degrade_to_secondary` 触发时通过 `SecondaryTakeoverPlanMetadata` 给 main/D3/D7 提供可消费状态：

- `not_applicable`：非二级接管动作；当前 active plan owner 仍是 center、distributed_cbba 或 hold_review。
- `pending_secondary_plan`：D4 已选择二级节点并触发重分配，但新的二级 plan 尚未生效；`active_plan_owner` 仍为当前 plan owner，`pending_plan_owner=secondary_node`，并记录 `secondary_plan_source_node_id`、当前 plan id/version 和 supersedes 字段。
- `secondary_plan_active`：main/D3 已回填新的二级 plan id/version 且标记 active；`active_plan_owner=secondary_node`，`secondary_reassignment_complete=True`。D7 只能在该状态、event 顶层 `secondary_capability_class=takeover_ready` 且两阶段 handoff 允许时继续后续视觉 PNG gate。

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

## 11. 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `C2Health` | `normal/degraded/suspect/failed`、heartbeat warning/stale/failure、sliding window/miss threshold/dwell、peer quorum、digest conflict、center epoch stale、恢复待合并 | `coordinator.py`、`models.py`、`tests/test_health.py` |
| 被动降级 | 中心 failed 后才执行 `plan_degraded()`；可选 ground backup/fixed tethered secondary/mobile high recon/representative；不收敛不发布有效 assignments | `coordinator.py`、`tests/test_coordinator.py` |
| 二级节点 lifecycle | heartbeat age/stale、lease epoch/expiry、coverage、requested coverage match、video/cue freshness、cue stale、gimbal pointing、coverage ratio、network full-view rate、stable registration/not-registered count、固定/机动二级分类、link stale/fresh、`secondary_available`、visible/registered/takeover_capable、`secondary_readiness_class`、capability score 和 score inputs | `active_degradation.py`、`models.py`、`tests/test_active_degradation.py` |
| 主动降级仲裁 | 输出 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary`、`degrade_to_distributed`、`hold_for_review`；2026-07-07 已区分硬风险和软证据，避免 cost margin 低、低终端置信度或无冲突 `ambiguous/reacquire` 导致每帧重规划/降级；当前无冲突 `reacquire` 只请求二级 cue/继续观察，不直接接管 | `active_degradation.py`、`tests/test_active_degradation.py` |
| D1/D2/D3/D5 adapter | duck typing/dict 读取 covariance/age、ambiguity/IDSW/continuity、plan/version/freshness/cost、terminal/cross-view/friend conflict，并归一化 dict/object 形式二级节点的 `role/capability_class/cue_freshness/gimbal/coverage` | `adapter.py`、`tests/test_arbitration_adapter.py` |
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
| main runtime bus 真实 episode 接线 | D4 adapter 可消费对象/dict 摘要并返回 D6 event kwargs；main/runtime P1 基线已持续调用 adapter、写 D4/D6 event，并保留 D1/D2/D3/D5 摘要；P1 D4/D5 calibration sweep 已接入，D6 标准 report bundle 已自动生成；2026-07-08 AirSim mobile recon stress 的 3 seeds 均 connected=True，9 个 episode 均为 13/13 image frames，D4 三类动作与预期一致；registration calibration v2 单 seed 已输出 stable registration、not-registered、coverage/full-view 和上游 projection/geometry gate 统计；D4 record 已输出三值 review label、review window、readiness class 和 capability score inputs | 真实 Blocks 多 seed 下的阈值、人工/离线 necessary/unnecessary 标签填充、secondary coverage/heartbeat/link freshness、二级接管必要性和 D5 peer evidence 合流仍未标定 | main 需要用相同 adapter schema 继续跑 D4/D5 stress 多 seed，并用 D6 bundle 固化可比较聚合 |
| D3 `request_center_replan` 自动调用 | D4 能输出 `request_center_replan` 并说明风险因素；main 已监听该 action 并触发 D3 新 plan version | 真实多 seed 下仍需确认硬 stale/not-current 和真实 terminal mismatch 的触发频率，避免软风险回归成每帧 replan | main/D3 保持 owner/version/supersedes 字段和 stale rejection，并用多 seed 报告校准 |
| secondary takeover plan owner/version 闭环 | D4 能选择固定系留或机动高空二级节点，D7 handoff helper 能表达两阶段 gate，D4 record metadata 能区分 `pending_secondary_plan` 与 `secondary_plan_active`，并输出 plan activation delay/pending duration、readiness class 与 takeover necessity/success 字段；`mobile_high_recon` 已作为二级候选能力进入 D4；main/D3/D7 已完成 owner/version P1 基线和 controlled 2v2 secondary visual PNG 回归 | 本轮 mobile recon gimbal/cue 正常，但二级网络同帧全覆盖仍为 0.0，case mean 联合覆盖约 0.65-0.69；registration v2 单 seed 出现 stable registration 51/55/53，但 full-view 均值仍低且 degradation case not-registered 仍为 35；真实 Blocks 多 seed 中 mobile recon heartbeat、coverage ratio、gimbal、link freshness、接管必要性标签和恢复合并窗口仍未标定 | main/D3/D7 保持 secondary plan id/version 回填，并用 D4/D5 stress 多 seed 校准 freshness、coverage、stable registration 和 gate 迁移 |
| 完整 C2 双轨审计 | 已记录 health transition 和 assignment-only merge | 尚未比较完整 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态 | main/runtime 需要持久化中心和 fallback 双轨 episode log，D6 消费 merge outcome |
| D4/D5 stress 统一口径 | D4 合同测试已有 case_001/002/003，adapter 可接收 D5 terminal/cross-peer evidence；main/runtime 已有基线 stress 与 controlled regression 接线；D4 事件已能区分 `visible_only`、`registration_usable` 和 `takeover_ready`；D6 calibration bundle 已输出 `stable_cross_view_registration_count`、`not_registered_count`、`secondary_detect_available_but_not_registered_count` 和 funnel reject reasons | 仍需真实 Blocks 多 seed 统计 false degradation、reacquire、secondary freshness、D5 peer evidence、stable registration 稳定性、not-registered 下降趋势和 active degradation precision 的分布 | main/runtime 使用同一 adapter record/event schema 跑多 seed，并固定 D6 汇总字段 |
| D5 distributed visual evidence 运行时合流 | D4 模块内可把 D5 多 peer evidence merge 到 `TrackSummary.visual_evidence` | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重仍需标定 | main 在 no-center case 持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线 |
| CBBA 与中心化最优 gap | D4 已有 `CBBACostGapBenchmark`、`build_cbba_cost_gap_benchmark()` 和 `build_cbba_d6_metadata()`，可对 D3/main 提供的中心 plan/cost matrix 计算 cost/completion/conflict/message gap 并输出 D6 多 seed 报告字段 | 真实 episode 还未持续保存同场景 D3 cost matrix/current plan，也未由 D6 汇总多 seed gap | main/D3 保存中心化 cost matrix/current plan，D6 聚合 benchmark 输出 |

## 13. 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CBBA-Python / CA-CBBA | 未接入外部实现；当前只有本地轻量 CBBA | 外部实现的数据模型、依赖、许可证、异步通信语义和 D4 summary bus 不一致；默认测试不能依赖外部工程 | 许可证/版本审查、adapter、可重复 benchmark、D6 收敛/通信开销报告 | P2 |
| 独立 auction baseline | 未单独实现 single-round auction，后置为可选对照基线 | 当前 `CBBANegotiator` 有 winner/bid 共识和 D5 visual evidence 加权，但不是独立拍卖状态机；P1 主线先保证 adapter 接线和 CBBA gap benchmark | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P2 后置 |
| Contract Net | 未实现 manager/contractor announce-bid-award 状态机 | 二级节点健康时仍需和 D3 plan version 对齐；manager 失效后还要 fallback 到 peer consensus | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是摘要和内存网络，真实链路属于 main/runtime/D5/D1 | runtime 生成 LinkRecord/video metadata；D5/D1 处理图像、检测、标定和 cue schema | P2/P3 |
| 虚拟中心 Hungarian | 明确不实现为 no-center fallback | 完全无中心模式不能伪造中心权威或改写 `global_track_id`；中心化最优属于 D3/main | 若要对照，只能做离线 benchmark，不得替代 D4 CBBA 保底 | 不做主线 |
| D4 直接生成系统级 `AssignmentPlan` | 不作为 D4 能力实现；D4 只输出仲裁/metadata/CBBA 保底结果 | D3/main 拥有 plan schema、plan owner、版本策略和 stale rejection；main P1 已接入 secondary owner/version 消费基线 | D4 继续保持不生成系统级计划，必要字段通过 `SecondaryTakeoverPlanMetadata` 输出 | 非 D4 主线 |

## 14. P1/P2 下一步

P1：

1. 使用 main runtime 的 P1 D4/D5 calibration sweep 和 D6 标准 report bundle 跑真实 Blocks/AirSim stress 多 seed，校准 `ActiveDegradationArbiter` 阈值、dwell/release、review label 填充、false degradation rate、terminal mismatch/reacquire 分布、二级覆盖/注册/接管必要性、readiness class 分布和 D6 聚合字段；2026-07-08 mobile recon stress 已验证三类 D4 action 正常，registration v2 单 seed 已验证 stable registration/not-registered 字段可写盘，但不能替代多 seed 标定。
2. 校准 secondary coverage、heartbeat、lease、video/cue freshness、gimbal pointing、mobile recon coverage ratio、link stale、stable cross-view registration、not-registered 下降趋势、plan activation delay 分布和恢复合并窗口，确保二级接管只在新鲜链路与覆盖/注册条件满足时从 pending 进入 active；当前断点是 `not_all_targets_visible` / `network_union_incomplete`，二级网络同帧全覆盖仍低。D4 只消费这些断点摘要并解释接管必要性，不负责修正 D5 几何注册。
3. 在完全无中心 case 中持续把 D5 distributed visual evidence 合流到 `TrackSummary.visual_evidence`，并用多 seed 报告确认 CBBA completion/conflict/cost gap/round/message 指标。
4. main/D3 继续保存同场景中心化 cost matrix/current plan，D6 聚合 D4 `CBBACostGapBenchmark` 多 seed 指标；轻量 CBBA 仍为默认保底。

P2：

1. 评估 MIT CBBA/CA-CBBA/CBBA-Python 的许可证、依赖、消息语义和同场景 benchmark，把它们作为 optional benchmark 而不是默认替换。
2. 在多 seed CBBA gap benchmark 稳定后，可选实现独立 single-round auction baseline，用同一 `TrackSummary[]`/`ResourceSummary[]`/D5 evidence 输入与 CBBA 对照。
3. 设计 Contract Net 的 manager/contractor 状态机、超时、拒绝/重招标和 manager 失效回退规则。
4. 扩展 `merge_recovery()`，加入 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态和多轮稳定窗口。
5. 若 P1 多 seed 校准暴露恢复抖动，再扩展 `merge_recovery()` 的多轮稳定窗口和状态审计。

## 15. 验收命令

```bash
git diff --check -- research_modules/d4_distributed_fallback subagent_reviews/D4_*
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
