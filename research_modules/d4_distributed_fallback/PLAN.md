# D4 分布式协同与降级接管计划

## 1. 范围与安全边界

D4 只负责 C-UAS 工作流中的离线科研仿真、降级仲裁、二级节点接管建模、完全无中心保底协商和评估日志。模块输入是粗粒度摘要，通信只使用内存网络或 main/runtime 提供的链路摘要；模块不拥有真实 AirSim episode 调度、真实通信链路、视频帧传输、飞控接口、硬件驱动、火控参数、毁伤模型、自动处置或授权绕过逻辑。

中心 C2 正常时，D3 仍是中心化分配的权威来源，`global_track_id` 仍由中心/上游航迹体系拥有。D4 在任何模式下都不得创建、改写或本地重绑定 `global_track_id`，只能复制上游 ID 做一致性检查、风险加权和审计。

## 2. 工程问题

中心节点正常时，系统依赖 D1/D2 的融合航迹、D3 的版本化 `AssignmentPlan`、D5 的末端视觉关联和 D6 的评估日志。当中心节点失效或局部分配证据不可信时，D4 需要回答以下问题：

- 如何区分中心真的失效的被动降级，与中心仍在线但计划风险升高的主动降级。
- 如何在中心失效后优先选择地面备份或高空/系留二级侦察节点，而不是直接进入完全无中心协商。
- 二级节点不可用时，如何使用轻量 CBBA 保底维持连续性，同时避免重复 owner、过期 ID、友方冲突和不收敛计划被发布。
- D1 不确定度、D2 关联风险、D3 plan/version/freshness 和 D5 terminal/cross-view 证据如何统一成 D4 仲裁动作。
- D5 distributed visual evidence 如何在完全无中心模式下影响 CBBA 出价，而不是构造虚拟中心或重新绑定 `global_track_id`。
- 中心恢复时如何通过双轨合并避免短暂 heartbeat 恢复导致双主。
- D4 输出如何进入 D6 event metadata 和后续 main runtime bus。

## 3. 当前总体状态

D4 模块内已经完成一个可测试的离线 P1 骨架：`C2Health`、被动降级、二级节点 lifecycle、主动降级仲裁、D1/D2/D3/D5 adapter、D5 distributed visual evidence 归一化、完全无中心 CBBA 风险加权、`assignment_audit`、D6-compatible event metadata、中心恢复基础合并和 N 规模输入均已存在。

仍需明确的是，这些实现主要停留在 D4 模块内和摘要级 dry-run/test 层。真实 main runtime bus 的 episode 接线、D3 在收到 `request_center_replan` 后自动生成新版计划、secondary takeover 后 plan id/version 回传 D7 的闭环，都还不是 D4 模块内已完成能力。

## 4. 被动降级与主动降级

### 4.1 被动降级

`passive_failover` 处理中心 C2 不可用：

- heartbeat 超过 hard timeout；
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
- D3：plan stale、非 current、plan version 不匹配或 cost margin 过低；
- D5：`ambiguous/hold/reacquire` 多帧持续、视觉候选与 assigned `global_track_id` 不一致、重复末端锁定、cross-view 高风险或 friend conflict。

主动降级的保守顺序：

1. D5 与 D3 分配一致且 D1/D2/D3 风险低：`continue_center`。
2. D3 版本/时效/代价风险是主因且 D5 仍一致：`request_center_replan`。
3. D1/D2 风险升高但 D5 仍一致：`request_secondary_assist`。
4. D5 单窗口不一致但未满足持续触发：请求中心重分配或二级辅助，不直接全分布式。
5. D5 多帧不一致且有健康二级节点覆盖当前 `coverage_cell`：`degrade_to_secondary`。
6. 二级节点不可用、链路过期、heartbeat 过期或不覆盖区域：`degrade_to_distributed`。
7. `friend_conflict=True` 或身份证据冲突：`hold_for_review`，不发布新计划。

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
- `update_health()` 覆盖 heartbeat warning/stale/failure 和 peer quorum。
- `merge_recovery()` 只比较 assignment owner/epoch 的基础版双轨合并；冲突或 review 未清空时保持 `degraded`。

## 6. 摘要接口

### 6.1 被动降级和 CBBA 摘要

- `TrackSummary`：`track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`、`visual_evidence`。
- `ResourceSummary`：`node_id`、`capability_class`、`availability_band`、`comm_band`、`operator_hold`、`takeover_priority`、`lease_epoch`、`node_role`、`coordinator_only`、`coverage_cell`、`heartbeat_timestamp_s`、`heartbeat_stale_after_s`、`epoch`。
- `BidState`：`task_id`、`bidder`、`score`、`constraints_hash`、`epoch`、`round_id`。
- `CBBAResult`：assignments、rounds、converged、conflict/completion/message/byte 指标、`final_views`、`assignment_audit`。

### 6.2 主动降级摘要

- `TrackUncertaintySummary`：D1 定位质量，含 `position_sigma_m`、`covariance_trace`、`velocity_sigma_mps`、`measurement_age_s` 和 `coverage_cell`。
- `AssociationRiskSummary`：D2 关联风险，含 `ambiguity_score`、`id_switch_count`、`duplicate_track_count`、`track_continuity`。
- `AssignmentValiditySummary`：D3 分配有效性，含 `global_track_id`、`assigned_resource_id`、`plan_version`、`is_current`、`plan_age_s`、`cost_margin`。
- `TerminalAssociationSummary`：D5 末端关联，含 `decision_state`、confidence、ambiguity、observed/assigned `global_track_id`、连续非锁定/不一致帧数、friend conflict、duplicate lock、cross-view 风险。
- `CommunicationSummary`：链路摘要，含 source/target/relay、`link_type`、sent/received timestamp、`payload_kind`、`stale_after_s`、sequence id。
- `SecondaryNodeLifecycleSummary`：二级节点 heartbeat age、lease、coverage、video cue freshness、link stale、`secondary_available`。
- `D4DecisionRecord`：adapter 输出，可转为 D6 `EventRecord` kwargs。

### 6.3 D5 分布式视觉证据摘要

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

## 8. 二级节点 lifecycle 与接管

二级节点在代码中通过 `NodeRole.GROUND_BACKUP` 和 `NodeRole.SECONDARY_RECON` 建模。可用性判断包括：

- `availability_band != none`；
- `operator_hold=False`；
- `coverage_cell` 为空或覆盖当前区域；
- heartbeat 未超过 `heartbeat_stale_after_s`；
- 若传入 `CommunicationSummary[]`，必须存在新鲜的 `c2_direct`、`secondary_relay` 或 `video_cue` 等可用链路。

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

主动降级中，`ActiveDegradationArbiter._select_secondary_node()` 会按覆盖区、heartbeat 和链路 freshness 过滤候选，再按 `takeover_priority -> lease_epoch -> node_id` 排序。

## 9. D6 事件与指标

`D4DecisionRecord.to_event_record_kwargs()` 当前可输出 D6 兼容字段：

- `event_type`：`d4_arbitration_decision`、`active_degradation_decision` 或 `passive_failover_start`；
- `severity`：正常继续中心为 `info`，降级/hold 为 `warning`；
- metadata：`d4_action`、`degradation_mode`、`d4_degradation_mode`、`selected_coordinator`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp`、`review_label`、resource/track/plan/version、`coverage_cell`、`terminal_consistent`、`risk_factors`、`secondary_available`、`communication_fresh`、`secondary_lifecycle`、`requires_human_review`。

`ActiveDegradationDecision.to_metrics()` 可输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate` 和 `distributed_conflict_count`。

## 10. N 规模输入

D4 不写死 2v2 或 5v5。当前行为：

- `run_failover_simulation()` 按 `resources`/`tasks` 实际列表长度运行；若未传列表，则按 `node_count`/`task_count` 构造摘要。
- CLI `--drone-count N` 只决定默认资源/任务数量，`--nodes` 是 legacy alias。
- CBBA 使用 `node_ids`、`TrackSummary[]` 和 `ResourceSummary[]` 长度运行。
- 2v2/5v5 只作为 AirSim baseline 或测试命名，不是算法限制。

## 11. 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `C2Health` | `normal/degraded/suspect/failed`、heartbeat warning/stale/failure、peer quorum、digest conflict、center epoch stale、恢复待合并 | `coordinator.py`、`models.py`、`tests/test_health.py` |
| 被动降级 | 中心 failed 后才执行 `plan_degraded()`；可选 ground backup/secondary/representative；不收敛不发布有效 assignments | `coordinator.py`、`tests/test_coordinator.py` |
| 二级节点 lifecycle | heartbeat、lease、coverage、video cue freshness、link stale、`secondary_available` | `active_degradation.py`、`models.py`、`tests/test_active_degradation.py` |
| 主动降级仲裁 | 输出 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary`、`degrade_to_distributed`、`hold_for_review` | `active_degradation.py`、`tests/test_active_degradation.py` |
| D1/D2/D3/D5 adapter | duck typing/dict 读取 covariance/age、ambiguity/IDSW/continuity、plan/version/freshness/cost、terminal/cross-view/friend conflict | `adapter.py`、`tests/test_arbitration_adapter.py` |
| D5 distributed visual evidence normalization | `build_distributed_visual_evidence_summary()`、`attach_distributed_visual_evidence()`、`merge_distributed_visual_evidence_into_tracks()` | `adapter.py`、`tests/test_arbitration_adapter.py` |
| 完全无中心 CBBA 风险加权 | D5 visual support 调整出价；hold/friend/stale/missing/conflicting ID 阻止 bid；duplicate lock 风险审计 | `cbba.py`、`tests/test_cbba.py` |
| `assignment_audit` | 输出 owner、visual support、hold/ambiguous/duplicate IDs、confidence/ambiguity、hypothesis、ID 风险和 reason | `cbba.py`、`tests/test_cbba.py` |
| D6 event metadata | `D4DecisionRecord.to_event_record_kwargs()` 输出 D6-compatible kwargs 和 metadata | `adapter.py`、`tests/test_arbitration_adapter.py` |
| D7 二级接管门控辅助 | `build_d7_secondary_handoff()` 阶段 1 不放行 visual PNG，阶段 2 必须带新 plan id/version | `active_degradation.py`、`tests/test_airsim_phase1_dry_run_contracts.py` |
| N 规模输入 | 仿真、CBBA 和测试按输入列表长度运行 | `simulation.py`、`scripts/run_failover_simulation.py`、`tests/test_simulation.py`、`tests/test_cbba.py` |

## 12. 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| main runtime bus 真实 episode 接线 | D4 adapter 可消费对象/dict 摘要并返回 D6 event kwargs | main/AirSim runtime 尚未保证每个真实 episode 都统一调用 D4 adapter 和写 D6 collector | main 需要在 episode 状态机中提供 D1/D2/D3/D5 摘要、LinkRecord-like 通信记录、batch seed 和 event sink |
| D3 `request_center_replan` 自动调用 | D4 能输出 `request_center_replan` 并说明风险因素 | D4 不调用 D3 planner，也不生成新版 `AssignmentPlan` | main 监听 D4 action，D3 发布新 plan id/version，并拒绝 stale plan |
| secondary takeover plan version 闭环 | D4 能选择二级节点，D7 handoff helper 能表达两阶段 gate | 二级节点新 plan 生成、plan owner、plan id/version 回传和 D7 控制状态机不是 D4 内闭环 | main/D3/D7 需要定义 secondary plan schema、版本策略、恢复合并和 D7 gate 接线 |
| 完整 C2 双轨审计 | 已记录 health transition 和 assignment-only merge | 尚未比较完整 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态 | main/runtime 需要持久化中心和 fallback 双轨 episode log，D6 消费 merge outcome |
| D5 distributed visual evidence 运行时合流 | D4 模块内可把 D5 多 peer evidence merge 到 `TrackSummary.visual_evidence` | 真实 episode 中 D5 多 peer 输出是否持续进入 D4 仍属 main 接线 | main 在 no-center case 调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线 |
| CBBA 与中心化最优 gap | D4 输出 completion/conflict/rounds/messages/assignment audit | 尚未与 D3 Hungarian/Min Cost Flow/OR-Tools 同场景 cost matrix 做 gap benchmark | D3/main 保存中心化 cost matrix/current plan，D6 计算 cost/completion/conflict gap |

## 13. 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CBBA-Python / CA-CBBA | 未接入外部实现；当前只有本地轻量 CBBA | 外部实现的数据模型、依赖、许可证、异步通信语义和 D4 summary bus 不一致；默认测试不能依赖外部工程 | 许可证/版本审查、adapter、可重复 benchmark、D6 收敛/通信开销报告 | P2 |
| 独立 auction baseline | 未单独实现 single-round auction | 当前 `CBBANegotiator` 有 winner/bid 共识和 D5 visual evidence 加权，但不是独立拍卖状态机 | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P1/P2 |
| Contract Net | 未实现 manager/contractor announce-bid-award 状态机 | 二级节点健康时仍需和 D3 plan version 对齐；manager 失效后还要 fallback 到 peer consensus | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是摘要和内存网络，真实链路属于 main/runtime/D5/D1 | runtime 生成 LinkRecord/video metadata；D5/D1 处理图像、检测、标定和 cue schema | P2/P3 |
| 虚拟中心 Hungarian | 明确不实现为 no-center fallback | 完全无中心模式不能伪造中心权威或改写 `global_track_id`；中心化最优属于 D3/main | 若要对照，只能做离线 benchmark，不得替代 D4 CBBA 保底 | 不做主线 |
| D4 直接生成系统级 `AssignmentPlan` | 未实现完整系统级封装 | D3/main 拥有 plan schema、plan owner、版本策略和 stale rejection | D3 plan contract、secondary owner 规则、D7 gate 回传、D6 日志闭环 | P1 main/D3 |

## 14. P1/P2 下一步

P1：

1. main/integrated runtime 在真实 episode 中统一调用 `D4ArbitrationAdapter.evaluate()`，把 D1/D2/D3/D5 摘要、通信记录和 D5 distributed visual evidence 接入 D4。
2. main 将 `D4DecisionRecord.to_event_record_kwargs()` 写入 D6 collector，并按 active/passive、secondary/distributed、coverage、seed 聚合。
3. main/D3 监听 `request_center_replan`，生成新版 `AssignmentPlan`，并把 plan id/version 返还给 D4/D7 gate。
4. main/D3/D7 定义 secondary takeover 后的新 plan owner、plan id/version、D7 two-stage handoff 和恢复合并规则。
5. D4/D6 增加 CBBA vs D3 中心化 cost matrix 的 gap benchmark，保留轻量 CBBA 为默认保底。

P2：

1. 评估 MIT CBBA/CA-CBBA/CBBA-Python 的许可证、依赖、消息语义和同场景 benchmark，把它们作为 optional benchmark 而不是默认替换。
2. 实现独立 single-round auction baseline，用同一 `TrackSummary[]`/`ResourceSummary[]`/D5 evidence 输入与 CBBA 对照。
3. 设计 Contract Net 的 manager/contractor 状态机、超时、拒绝/重招标和 manager 失效回退规则。
4. 扩展 `merge_recovery()`，加入 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态和多轮稳定窗口。
5. 在 AirSim stress 中标定主动降级阈值、dwell/release、false degradation rate 和 secondary freshness。

## 15. 验收命令

```bash
git diff --check -- research_modules/d4_distributed_fallback subagent_reviews/D4_*
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
