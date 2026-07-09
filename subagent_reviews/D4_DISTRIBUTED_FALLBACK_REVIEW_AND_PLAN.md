# D4 分布式协同与降级接管综述及子方案

**模块定位**：D4 负责中心 C2 异常、二级节点接管、主动降级仲裁和完全无中心协商的离线科研仿真方案。
**核心边界**：本文只讨论摘要交换、状态机、故障注入、降级协同和评估日志；不包含真实通信链路、飞控控制、火控参数、毁伤逻辑、自动处置或授权绕过。

---

## 0. 2026-07-08 P1 状态更新

D4 模块内已补齐 P1 所需的本地输出口径：secondary takeover record metadata 可区分 `pending_secondary_plan` 与 `secondary_plan_active`，并携带当前/二级 plan id/version、source node、supersedes plan、reassignment complete、plan activation delay 和 pending duration 字段；主动降级 metadata 已能输出 `necessary/unnecessary/inconclusive` 三值 review label、pre/post review window、secondary diagnostic、takeover necessity/success，并透传 D5 二级视觉覆盖/转换漏斗 evidence，区分“二级 detect 可见”与“cross-view/global binding/registration 已完成”；`role/capability_class=mobile_high_recon/mobile_secondary_recon` 已作为机动高空二级侦察节点元数据进入候选、lifecycle 和 D6 事件，并与 `fixed_tethered_secondary/tethered_recon` 区分；完全无中心 CBBA 已用 D5 distributed visual evidence 做风险加权；`build_cbba_cost_gap_benchmark()` 可用 D3/main 提供的中心 plan 与 cost matrix 计算 CBBA vs 中心化 cost gap；`build_cbba_d6_metadata()` 和 `run_failover_simulation()` 顶层 metrics 可输出 secondary/distributed 分组、leader、coverage、CBBA 审计和 cost gap 扁平字段。

main/runtime P1 基线也已接入：episode bus 已消费 D4 adapter event，`request_center_replan` 可触发 D3 new plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已新增，可批量改变二级节点高度、FOV、节点数量和 standoff，并在 sweep 结束后自动生成 D6 标准 AirSim calibration records/summary/report bundle。

2026-07-08 AirSim 机动高空侦察节点 stress 结果已同步到当前状态：输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`，3 seeds 均 connected=True；每个 seed 含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，所有 episode 均为 13 frames 且 image_ok=13。场景使用 5 个目标、5 个拦截相机、2 个二级侦察相机、200 m 高差、80 度 FOV 和 1920x1080。D4 主动作符合预期：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`；二级侦察侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。

P0 状态：无 P0 blocker。边界保持不变：D4 只输出仲裁记录、metadata、CBBA 保底结果和离线 benchmark，不直接生成 D3 系统级 `AssignmentPlan`，不控制 D7，不引入 MIT/CA-CBBA 外部实现。机动高空侦察节点随拦截机出动、不拦截，正常时用 D1/D2 `GlobalTrack` 或 radar cue 指向目标簇并给局部拦截群提供图像/cross-view evidence；中心失效或主动降级硬条件满足时才可作为二级协调节点。剩余 P1 聚焦二级 coverage/heartbeat/link freshness、二级接管必要性标签填充、plan activation delay 分布、D5 peer evidence 合流、active degradation precision 和 D6 长期聚合；本轮二级网络同帧全覆盖仍不足，主要 coverage 断点是 `not_all_targets_visible` / `network_union_incomplete`，D5 detect 到 global track 注册不足的直接断点是 `geometry_gate_rejected`。MIT/CA-CBBA 与独立 auction baseline 仅作为 optional P2 对照。

D4 对二级侦察结果的 P1 校准解释已经固定：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不直接做相机几何注册。二级可见但未注册时，D4 记录 `secondary_detect_available_but_not_registered` 和 reject reasons，最多支持 `request_secondary_assist` 或接管必要性审计；二级网络未全覆盖时，D4 记录 `secondary_network_full_view_gap`，不把不完整视场当成接管成功；稳定 cross-view support 足够且二级链路新鲜时，才作为 `degrade_to_secondary` 必要性和成功的正证据。任何 `secondary_plan_active` 仍必须由 main/D3 回填新 plan id/version。

---

## 1. 被动降级 vs 主动降级

D4 必须明确区分两类降级，因为触发源、优先级和恢复条件不同。

| 类型 | 触发条件 | 主要目标 | 默认策略 |
|---|---|---|---|
| 被动降级 `passive_failover` | 中心节点被摧毁、失联、heartbeat 超时、中心摘要长期不可用、peer quorum 判定中心失败 | 在中心不可用时维持保底任务连续性 | 中心 C2 -> 二级节点 -> 完全无中心 CBBA/拍卖 |
| 主动降级 `active_degradation` | 中心未失效，但 D1/D2/D3/D5 证据显示当前计划不可靠 | 防止“中心仍在线但局部计划已经失效” | 继续中心计划、请求中心重分配、请求二级节点辅助、主动降到二级或局部分布式 |

被动降级是结构性故障处理；主动降级是一致性和不确定性仲裁。主动降级不代表中心失权，也不能允许本地节点自行改写 `global_track_id` 或绕过 D3/D5 的版本、身份和授权约束。

---

## 2. 状态机设计

### 2.1 C2Health 状态机

```text
normal
  -> degraded : heartbeat 抖动、中心摘要延迟升高、计划 digest 变旧
  -> suspect  : heartbeat 过期、中心 epoch 倒退、摘要冲突、peer 状态不一致

degraded
  -> normal   : heartbeat、digest、plan version 稳定且双轨校验通过
  -> suspect  : 备份 lease 冲突、二级节点摘要冲突、局部分区迹象
  -> failed   : heartbeat hard timeout 或 peer quorum 判定中心失败

suspect
  -> normal   : 中心与 peer 双轨日志一致，并通过人工/上层确认
  -> degraded : 有二级节点或备份 lease 可以维持保底连续性
  -> failed   : 中心失联超时、关键摘要长期不可用、quorum 失败票成立

failed
  -> degraded : 二级节点、地面备份或集群代表接管
  -> suspect  : 中心恢复但摘要/计划尚未合并
```

恢复不能只靠 heartbeat。heartbeat 只能证明中心又在发送消息，不能证明中心拥有最新航迹、最新分配版本和降级期间形成的局部计划。因此中心恢复必须走 `merge_recovery` 思路：中心日志和降级日志双轨比较，完全一致才恢复 `normal`；存在版本落后、重复所有者、计划冲突时保持 `degraded/suspect`。

### 2.2 降级模式状态机

```text
mode=none
  -> passive_failover     : C2Health == failed
  -> active_degradation   : C2 未 failed，但 D1/D2/D3/D5 风险触发

passive_failover
  -> secondary_node       : 覆盖区内二级侦察节点健康
  -> distributed_cbba     : 二级节点不可用或覆盖区失效
  -> hold/observe         : CBBA 不收敛或无可用资源

active_degradation
  -> continue_center      : D5 与分配一致，D1/D2/D3 风险低
  -> request_center_replan: D3 分配过期或版本不当前
  -> continue/assist      : 仅代价裕度不足、低置信度或无冲突 reacquire 时继续观察
  -> request_secondary_assist: D1/D2 风险升高但 D5 仍一致
  -> degrade_to_secondary : D5 多帧硬不一致且二级节点覆盖该区域
  -> degrade_to_distributed: D5 硬不一致持续且二级节点不可用或局部分区
  -> hold_for_review      : friend_conflict 或身份冲突
```

---

## 3. 被动降级判据

被动降级处理“中心节点不可用”的情况。

### 3.1 触发源

- 中心 heartbeat 超过 `heartbeat_failure_s`。
- 多节点 peer quorum 判定中心不可用。
- 中心 `epoch` 长时间停滞或倒退。
- 中心 `track_digest`、`assignment_digest` 长时间缺失。
- 中心恢复消息与降级期间形成的计划版本冲突。

### 3.2 决策顺序

```text
中心 C2 failed
  -> 查询覆盖 coverage_cell 的二级侦察节点
  -> 二级节点健康：secondary_node 接管区域协调
  -> 二级节点失效：cluster_representative 接管局部协商
  -> 仍不可用：完全无中心 CBBA/拍卖
  -> 不收敛：hold / continue_observe / review
```

### 3.3 二次被动降级

二级节点并不是新的永久中心。它只是在中心失效后的区域协调者。若二级节点再次失效，D4 必须触发二次被动降级：

```text
secondary_node active
  -> secondary heartbeat stale
  -> secondary availability none/operator_hold
  -> coverage_cell 不再覆盖当前任务
  -> degrade_to_distributed
```

---

## 4. 主动降级触发源

主动降级处理“中心仍在线，但当前分配和局部观测不再可信”的情况。D4 只做仲裁，不直接改变 D1/D2/D3/D5 的原始结论。

### 4.1 D1 定位不确定度

D1 应向 D4 提供 `TrackUncertaintySummary`：

- `track_id / global_track_id`
- `coverage_cell`
- `position_sigma_m`
- `covariance_trace`
- `velocity_sigma_mps`
- `measurement_age_s`
- 可选：传感器来源数量、遮挡状态、时间戳延迟

主动降级风险：

- 协方差快速增大，中心定位分辨率不足。
- `measurement_age_s` 超过中心分配可接受窗口。
- 高动态目标导致预测误差扩大。
- 当前 `coverage_cell` 与二级节点覆盖区不一致。

### 4.2 D2 关联风险

D2 应向 D4 提供 `AssociationRiskSummary`：

- `track_id`
- `ambiguity_score`
- `id_switch_count`
- `duplicate_track_count`
- `track_continuity`

主动降级风险：

- 多目标交叉后 `id_switch_count` 增加。
- `ambiguity_score` 高，GNN/Hungarian 硬关联不稳定。
- 重复航迹出现，可能导致 D3 重复分配。
- `track_continuity` 下降，中心计划绑定的目标身份可信度不足。

### 4.3 D3 分配有效性

D3 应向 D4 提供 `AssignmentValiditySummary`：

- `global_track_id`
- `assigned_resource_id`
- `plan_id`
- `plan_version`
- `is_current`
- `plan_age_s`
- `cost_margin`
- 可选：当前分配代价、备选分配代价、replan dwell time

主动降级风险：

- `is_current=False`。
- `plan_age_s` 超过滚动重分配窗口。
- `cost_margin` 过低，说明当前分配和备选方案差距很小，容易抖动；这是软证据，单独出现时不触发 `request_center_replan`。
- D3 计划版本落后于 D5 末端观测时间。

### 4.4 D5 末端视觉关联

D5 应向 D4 提供 `TerminalAssociationSummary`：

- `resource_id`
- `assigned_global_track_id`
- `observed_global_track_id`
- `decision_state`: `locked | ambiguous | hold | reacquire`
- `association_confidence`
- `ambiguity_score`
- `consecutive_non_locked_frames`
- `consecutive_mismatch_frames`
- `friend_conflict`
- `coverage_cell`

主动降级风险：

- D5 多帧 `ambiguous/hold/reacquire` 但没有观测 ID mismatch、资源错配、重复锁定或友方冲突时，只作为软证据。
- 本地视觉候选与 D3 分配目标长期不一致。
- `resource_id` 与 D3 指派资源不一致。
- `friend_conflict=True`，必须进入 `hold_for_review`，不能降级为自动协商。

---

## 5. 仲裁逻辑与决策顺序

D4 仲裁器的核心原则：能继续中心计划就继续；能请求中心滚动重分配就不直接分布式；能由二级节点区域协调就不直接完全无中心。

### 5.1 总体决策顺序

```text
1. 若 friend_conflict 或身份冲突：
     -> hold_for_review

2. 若 C2Health == failed：
     -> passive_failover
     -> 二级节点可用则 secondary_node
     -> 否则 distributed_cbba/auction

3. 若 D5 与 D3 分配一致，且 D1/D2/D3 风险低：
     -> continue_center

4. 若 D3 版本/时效硬风险上升，但 D5 仍一致：
     -> request_center_replan

5. 若只有 D3 cost margin 低、D5 低置信度或无冲突 reacquire：
     -> continue_center 或 request_secondary_assist，继续观察

6. 若 D1/D2 风险上升，但 D5 仍一致：
     -> request_secondary_assist

7. 若 D5 单帧不一致但未持续：
     -> 无硬风险则 continue_center；需要补充视角时 request_secondary_assist

8. 若 D5 多帧硬不一致、长期目标 mismatch、资源错配、重复锁定或友方冲突：
     -> 二级节点覆盖则 degrade_to_secondary
     -> 二级不可用则 degrade_to_distributed

9. 若 CBBA/拍卖不收敛：
     -> hold / continue_observe，只输出审计日志
```

### 5.2 二级节点接管条件

二级节点只有满足以下条件才可作为区域协调者：

- `node_role=secondary_recon`、`ground_backup`、`fixed_tethered_secondary`、`mobile_high_recon`、`mobile_secondary_recon`，或等价 `capability_class=tethered_recon/fixed_tethered_secondary/mobile_high_recon/mobile_secondary_recon`。
- `availability_band != none`。
- `operator_hold=False`。
- `coverage_cell` 覆盖当前目标/资源小区。
- 对机动二级节点，正的 `secondary_coverage_ratio` 可作为动态目标簇覆盖证据。
- `cue_freshness_s` 新鲜且 `gimbal_pointing_ok` 未显式为 false。
- `lease_epoch` 不落后于当前降级 epoch。
- 若同区域多个二级节点可用，按 `takeover_priority -> lease_epoch -> comm_band -> node_id` 排序。

### 5.3 局部代表节点协商

当二级节点不可用但局部仍有通信时，选择 `cluster_representative` 作为协商入口。该节点不获得中心级权威，只负责发起 CBBA/拍卖式保底协商。

### 5.4 完全无中心 CBBA/拍卖

进入完全无中心协商的条件：

- 中心 failed 且二级节点 failed。
- 主动降级时 D5 多帧不一致，且二级节点不可用或不覆盖。
- 网络分区导致只能局部保底。

CBBA/拍卖结果必须带 epoch、版本和冲突统计。若不收敛，不得发布有效 `AssignmentPlan`，只能发布 `EventRecord`。

---

## 6. 二级节点职责

固定系留或机动高空侦察无人机组成的二级节点不是执行资源，默认 `coordinator_only=True`。其职责是区域协调和观测增强；机动高空侦察节点随拦截机出动但不拦截，用 D1/D2 `GlobalTrack` 或 radar cue 指向目标簇，正常时向局部拦截群提供图像、coverage 和 cross-view evidence。

### 6.1 未失效时

二级节点在中心正常或主动降级时提供：

- 区域侦察图像或图像索引。
- 检测摘要：目标框、置信度、时间戳、覆盖小区。
- 局部 `TrackSummary`：`track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`。
- 对 D5 的 scoped cue：只发送给覆盖范围内的小范围拦截资源。
- 对 D3/D4 的覆盖区健康摘要：可用性、通信质量、lease、operator hold。

这些输出只能作为辅助证据，不允许二级节点绕过 D3 的 `plan_version`、D5 的友方认证或人工授权状态。仅有侦察图像、cue freshness、云台指向正常或 coverage ratio > 0 不会自动触发 `degrade_to_secondary`。

2026-07-08 mobile recon stress 已证明 `mobile_high_recon` 可作为二级候选能力进入 D4 且云台/cue 正常，但二级网络同帧全覆盖仍为 0.0。后续 P1 必须把二级 coverage、heartbeat/link freshness、接管必要性和 plan activation delay 作为统一校准项，而不是只看单帧侦察可见性。

### 6.2 中心失效后

二级节点接管区域协调：

- 维持局部计划版本。
- 汇总 D1/D2/D5 的摘要。
- 协助判断是否需要局部重分配。
- 通过 main/D3 发布保底 plan metadata；D4 只记录 source node、pending/active 状态和 plan id/version，不直接生成系统级 `AssignmentPlan`。

### 6.3 二级节点失效后

触发二次被动降级：

- 将 `secondary_node_takeover` 结束事件写入日志。
- 选择局部代表节点。
- 若代表节点不可用，则进入完全无中心 CBBA/拍卖。
- 若 CBBA 不收敛，只输出 `hold/continue_observe` 事件。

---

## 7. 输出接口与日志

### 7.1 DegradationDecision

建议总线使用统一输出：

```text
DegradationDecision
- episode_id
- timestamp
- mode: none | passive_failover | active_degradation
- action:
    continue_center
    request_center_replan
    request_secondary_assist
    degrade_to_secondary
    degrade_to_distributed
    hold_for_review
- arbitration_reason
- risk_factors[]
- target_node_id
- leader_role
- coverage_cell
- terminal_consistent
- requires_human_review
- source_epoch
- active_plan_owner
- secondary_takeover_state: not_applicable | pending_secondary_plan | secondary_plan_active
- secondary_plan_source_node_id
- secondary_plan_id
- secondary_plan_version
- secondary_reassignment_complete
- plan_version
```

### 7.2 EventRecord

```text
EventRecord
- event_type:
    c2_health_transition
    passive_failover_started
    secondary_node_takeover
    secondary_node_failed
    distributed_cbba_started
    distributed_cbba_converged
    distributed_cbba_timeout
    active_degradation_arbitrated
    center_recovery_merge
- timestamp
- track_id
- resource_id
- coverage_cell
- arbitration_reason
- details
```

### 7.3 D4 secondary takeover metadata

D4 record 必须显式标注二级接管来源和生效状态，供 main/D3/D7 生成或消费系统级计划：

```text
D4DecisionRecord.metadata
- active_plan_owner: center | secondary_node | distributed_cbba | hold_review
- secondary_takeover_state: not_applicable | pending_secondary_plan | secondary_plan_active
- secondary_plan_source_node_id
- current_plan_id
- current_plan_version
- secondary_plan_id
- secondary_plan_version
- secondary_supersedes_plan_id
- secondary_supersedes_plan_version
- secondary_reassignment_complete
- secondary_plan_activation_delay_s
- secondary_plan_pending_duration_s
- secondary_takeover_candidate
- secondary_takeover_success
- secondary_takeover_necessity_label
- review_label: necessary | unnecessary | inconclusive
- active_degradation_review_window
- secondary_diagnostic_heartbeat_age_s
- secondary_diagnostic_link_fresh
- secondary_diagnostic_cue_freshness_s
- secondary_diagnostic_gimbal_pointing_ok
- secondary_diagnostic_coverage_ratio
- secondary_network_full_view_gap
- secondary_detect_to_registration_gap
```

规则：`degrade_to_secondary` 的第一帧只表示二级接管待生效，`active_plan_owner` 仍是当前计划 owner；只有 main/D3 回填新的二级 plan id/version 且标记 active 后，D4 metadata 才进入 `secondary_plan_active`。D4 不直接发布完整 `AssignmentPlan`。

### 7.4 指标

D6 应消费以下 D4 指标：

- `failover_time`
- `active_degradation_count`
- `secondary_node_takeover_count`
- `distributed_cbba_count`
- `arbitration_reason_histogram`
- `degraded_completion_rate`
- `consensus_rounds`
- `conflict_count`
- `cbba_total_cost / center_total_cost / absolute_cost_gap / relative_cost_gap`
- `coordination_mode / selected_coordinator / leader_role / coverage_cell`
- `hold_for_review_count`
- `terminal_inconsistency_trigger_count`
- `active_degradation_precision` using `review_label in {necessary, unnecessary, inconclusive}`
- `secondary_takeover_necessity_label`
- `secondary_plan_activation_delay_s / secondary_plan_pending_duration_s`
- `secondary_network_coverage_available / secondary_network_full_view_gap`
- `secondary_single_camera_full_view_frame_rate / secondary_network_joint_full_view_frame_rate`
- `secondary_network_mean_coverage_ratio / cross_view_association_count`
- `secondary_detect_to_registration_gap`

---

## 8. 摘要消息合同

```text
TrackSummary
- track_id
- coarse_cell
- age_s
- confidence_band
- source_count
- epoch

ResourceSummary
- node_id
- capability_class
- availability_band
- comm_band
- operator_hold
- takeover_priority
- lease_epoch
- node_role
- coordinator_only
- coverage_cell
- cue_freshness_s
- gimbal_pointing_ok
- secondary_coverage_ratio
- cross_view_support_count
- epoch

BidState
- task_id
- bidder
- score
- constraints_hash
- epoch
- round_id
```

摘要必须粗粒度、带版本、带 epoch。D4 不应接收未经 D1/D2/D3/D5 校验的完整高精度态势，也不应让局部节点直接覆盖 `global_track_id`。

---

## 9. CBBA、拍卖和合同网综述

2015-2026 年无人机集群任务分配中，CBBA、拍卖算法和合同网协议是常见分布式路线。

CBBA 通过 winner/bid 向量扩散和一致性消解，在连通图、确定仲裁和边际收益条件满足时可有限轮收敛。优点是适合多智能体任务协商，缺点是通信量随任务数、束长和网络直径上升。

拍卖算法实现简单、收敛快，适合保底协商；但如果缺少稳定拍卖人或一致仲裁，可能发生反复竞价。合同网协议适合动态插入任务，通信过程清晰，但结果通常偏贪心。

工程共识是：中心正常时不主动全分布式；二级节点可用时不直接全分布式；完全无中心只作为中心和二级节点均不可用后的保底能力。

---

## 10. 故障注入测试建议

| 场景 | 期望 |
|---|---|
| 中心 heartbeat 丢失 | `normal -> suspect -> failed`，触发被动降级 |
| 中心 failed + 二级节点健康 | `degrade_to_secondary`，`secondary_node_takeover_count + 1` |
| 中心 failed + 二级节点 unavailable | `degrade_to_distributed`，启动 CBBA/拍卖 |
| 二级节点接管后失效 | 二次被动降级到局部代表/CBBA |
| D1 协方差增大但 D5 一致 | 请求二级辅助，不直接分布式 |
| D2 ID switch 上升但 D5 一致 | 请求二级辅助或中心重分配 |
| D3 plan stale 但 D5 一致 | `request_center_replan` |
| D5 多帧无冲突 `ambiguous/hold/reacquire` | 继续中心或请求二级 cue，不直接重规划/降级 |
| D5 多帧硬不一致或资源/身份冲突 | 主动仲裁；二级覆盖则二级接管，否则完全无中心保底 |
| D5 `friend_conflict=True` | `hold_for_review`，不发布新计划 |
| CBBA 超时 | 不发布有效 assignment，只写事件 |
| 中心恢复但日志落后 | 双轨校验失败，保持 degraded/suspect |

---

## 11. 交付物与集成建议

1. 保持 `C2Health` 与 `DegradationMode` 分离：前者描述中心健康，后者描述降级策略。
2. D4 主循环应先处理 `friend_conflict`，再处理被动降级，最后处理主动降级。
3. 主动降级应有 dwell time / hysteresis，避免 D5 单帧抖动导致频繁切换。
4. 二级节点的图像 cue 和检测摘要必须 scoped 到覆盖区内资源。
5. `coordination_mode`、`leader_role`、`coverage_cell` 必须进入 `AssignmentPlan.metadata` 和 D6 日志。
6. 完全无中心结果必须携带 `converged/conflict_count/consensus_rounds`，未收敛时不得被 main 当成可执行计划。
7. mobile recon 的 `gimbal_pointing_ok`、`radar_global_track_cue` 和 `mobile_high_recon` capability 只能证明候选节点可用；二级网络同帧全覆盖不足时，D4 应继续记录 coverage 断点并等待上游校准。
8. `degrade_to_secondary` 后必须继续区分 `pending_secondary_plan` 与 `secondary_plan_active`；D4 已输出 plan activation delay/pending duration 和 takeover necessity/success metadata，main/D6 需用真实 episode 标注校准接管必要性和 D7 gate 迁移。
9. 后续 D4/D5 AirSim 校准应优先使用 main runtime 的 P1 calibration sweep 和 D6 标准 bundle 输出；D4 只消费 sweep 产生的摘要与 report 字段，不直接启动 AirSim 或写 main runtime。

---

## 12. 参考资料

- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- CBBA-Python: <https://github.com/zehuilu/CBBA-Python>
- CA-CBBA: <https://github.com/mit-acl/CACBBA>
- Dynamic UAV task allocation survey: <https://www.mdpi.com/2504-446X/9/1/75>
