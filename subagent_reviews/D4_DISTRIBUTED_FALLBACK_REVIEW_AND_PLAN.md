# D4 分布式协同与降级接管综述及子方案

**模块定位**：D4 负责中心 C2 异常、二级节点接管、主动降级仲裁和完全无中心协商的离线科研仿真方案。
**核心边界**：本文只讨论摘要交换、状态机、故障注入、降级协同和评估日志；不包含真实通信链路、飞控控制、火控参数、毁伤逻辑、自动处置或授权绕过。

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
  -> request_center_replan: D3 分配过期、版本不当前、代价裕度不足
  -> request_secondary_assist: D1/D2 风险升高但 D5 仍一致
  -> degrade_to_secondary : D5 多帧不一致且二级节点覆盖该区域
  -> degrade_to_distributed: 二级节点不可用或局部分区
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
- `cost_margin` 过低，说明当前分配和备选方案差距很小，容易抖动。
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

- D5 多帧 `ambiguous/hold/reacquire`。
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

4. 若 D3 版本/代价/时效风险上升，但 D5 仍一致：
     -> request_center_replan

5. 若 D1/D2 风险上升，但 D5 仍一致：
     -> request_secondary_assist

6. 若 D5 单帧不一致但未持续：
     -> request_secondary_assist 或 request_center_replan

7. 若 D5 多帧不一致、长期 reacquire/hold：
     -> 二级节点覆盖则 degrade_to_secondary
     -> 二级不可用则 degrade_to_distributed

8. 若 CBBA/拍卖不收敛：
     -> hold / continue_observe，只输出审计日志
```

### 5.2 二级节点接管条件

二级节点只有满足以下条件才可作为区域协调者：

- `node_role=secondary_recon` 或 `ground_backup`。
- `availability_band != none`。
- `operator_hold=False`。
- `coverage_cell` 覆盖当前目标/资源小区。
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

高空系留侦察无人机组成的二级节点不是执行资源，默认 `coordinator_only=True`。其职责是区域协调和观测增强。

### 6.1 未失效时

二级节点在中心正常或主动降级时提供：

- 区域侦察图像或图像索引。
- 检测摘要：目标框、置信度、时间戳、覆盖小区。
- 局部 `TrackSummary`：`track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`。
- 对 D5 的 scoped cue：只发送给覆盖范围内的小范围拦截资源。
- 对 D3/D4 的覆盖区健康摘要：可用性、通信质量、lease、operator hold。

这些输出只能作为辅助证据，不允许二级节点绕过 D3 的 `plan_version`、D5 的友方认证或人工授权状态。

### 6.2 中心失效后

二级节点接管区域协调：

- 维持局部计划版本。
- 汇总 D1/D2/D5 的摘要。
- 协助判断是否需要局部重分配。
- 对局部资源发布保底 `AssignmentPlan` 元数据。

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

### 7.3 AssignmentPlan 元数据

降级产生的计划必须显式标注来源：

```text
AssignmentPlan.metadata
- generated_by: D4
- degradation_mode
- coordination_mode: secondary_node | distributed_cbba | auction | hold
- leader_id
- leader_role
- coverage_cell
- source_plan_version
- fallback_epoch
- converged
- conflict_count
```

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
- `hold_for_review_count`
- `terminal_inconsistency_trigger_count`

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
| D5 多帧 `ambiguous/hold/reacquire` | 主动仲裁；二级覆盖则二级接管 |
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

---

## 12. 参考资料

- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- CBBA-Python: <https://github.com/zehuilu/CBBA-Python>
- CA-CBBA: <https://github.com/mit-acl/CACBBA>
- Dynamic UAV task allocation survey: <https://www.mdpi.com/2504-446X/9/1/75>
