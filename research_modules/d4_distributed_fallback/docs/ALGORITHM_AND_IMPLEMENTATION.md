# D4 算法原理与实施方案

## 1. 模块定位

D4 负责离线降级协同研究，包含两类模式：

- 被动降级 `passive_failover`：中心 C2 被摧毁、失效或经 quorum 判定不可用，系统从中心 C2 降到二级节点，再降到完全无中心 CBBA/拍卖。
- 主动降级 `active_degradation`：中心 C2 尚未失效，但 D1/D2/D3/D5 的风险证据显示当前中心或二级分配已不再可靠，需要由 D4 仲裁是否请求重分配、请求二级节点辅助，或临时降到区域/分布式协同。

它不替代 D3 的中心化最优分配，也不直接驱动 D5 的末端视觉锁定；它只在中心失效、信息不完整、通信受限或局部关联证据冲突的仿真条件下，维持最低限度的计划连续性，并把所有降级行为记录给 D6 评估。

本模块边界固定为离线科研仿真：只处理粗粒度 `TrackSummary`、`ResourceSummary`、CBBA 状态和审计日志；不实现真实无线链路、飞控接口、硬件驱动、火控参数、毁伤模型、自动处置或授权绕过。

## 2. 输入输出

### 2.1 输入

- `TrackSummary[]`：来自 D1/D2 的全局航迹摘要，字段包括 `track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`。
- `ResourceSummary[]`：来自资源状态管理或 D3 上一版计划的资源摘要，字段包括 `node_id`、`capability_class`、`availability_band`、`comm_band`、`operator_hold`、`takeover_priority`、`lease_epoch`、`node_role`、`coordinator_only`、`coverage_cell`、`heartbeat_timestamp_s`、`heartbeat_stale_after_s`、`cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`cross_view_support_count`、`epoch`。
- `C2` 健康输入：heartbeat 状态、assignment digest 是否一致、center epoch、peer fail votes。
- `SimulatedNetwork`：内存网络，提供延迟、丢包和消息计数。
- `TrackUncertaintySummary`：来自 D1 的定位不确定度摘要，包含 `position_sigma_m`、`covariance_trace`、`measurement_age_s` 和 `coverage_cell`。
- `AssociationRiskSummary`：来自 D2 的关联风险摘要，包含 `ambiguity_score`、`id_switch_count`、`duplicate_track_count`、`track_continuity`、`truth_metrics_available` 和 `continuity_available`。在线 truth 隔离时，后两个可用性标志阻止 IDSW/continuity 占位值进入硬风险；association ambiguity、duplicate track risk 和 track-quality-derived risk 仍可在线使用。
- `AssignmentValiditySummary`：来自 D3 的分配有效性摘要，包含 `global_track_id`、`assigned_resource_id`、`plan_version`、`is_current`、`plan_age_s` 和 `cost_margin`。
- `TerminalAssociationSummary`：由 D5 的 `TerminalAssociation` 归一化得到，包含末端 `resource_id`、`decision_state`、`association_confidence`、`ambiguity_score`、连续非锁定帧数、连续不一致帧数、友方冲突、重复末端锁定标记、cross-view 风险和当前 `coverage_cell`。
- `CommunicationSummary[]`：来自 main 通信层的离线链路摘要，字段包括 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind` 和 `stale_after_s`。

### 2.2 输出

- `CBBAResult`：降级分配结果、共识轮数、是否收敛、冲突数、完成率、消息数量和字节估计。
- `HealthTransition[]`：状态转移审计日志。
- `MergeResult`：中心恢复后的双轨合并结果，区分 `accepted/review/conflicts`。
- `final_views["coordination_mode"]`：写入 `state/leader_id/leader_role/coverage_cell`，并由 `build_cbba_d6_metadata()` 和 `run_failover_simulation()` 顶层 metrics 透传，便于 D6 区分二级节点接管与完全分布式 CBBA。
- `ActiveDegradationDecision`：主动/被动仲裁结果，字段包括 `mode`、`action`、`reason`、`target_node_id`、`coverage_cell`、`terminal_consistent`、`risk_factors` 和 `requires_human_review`；`to_metrics()` 输出 main/D6 所需 D4 指标字段。
- `SecondaryNodeLifecycleSummary`：二级节点生命周期摘要，字段包括 `heartbeat`、`lease_epoch`、`coverage_cell`、`video_cue_freshness_s`、`link_stale` 和 `secondary_available`。
- `D4DecisionRecord.to_event_record_kwargs()`：输出 D6 `EventRecord` 兼容事件，metadata 包含 `degradation_mode`、`selected_coordinator`、`coverage_cell`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp`、三值 `review_label`、secondary takeover plan lifecycle、`active_plan_owner`、二级 coverage/full-view、stable cross-view registration、not-registered 和 detect-to-registration 诊断，并保留 `d4_degradation_mode` 等 D4 原始字段。
- `CBBACostGapBenchmark`：离线 benchmark 输出，使用 D3/main 提供的中心 plan 和 cost matrix，对比 D4 CBBA 的 cost/completion/conflict/message 差距；D4 不运行中心化 Hungarian。
- `build_cbba_d6_metadata()`：将 `CBBAResult`、`coordination_mode`、`assignment_audit` 和可选 `CBBACostGapBenchmark` 转成 D6 多 seed 报告字段。

## 3. C2Health 状态机

状态定义：

- `normal`：中心 heartbeat、assignment digest 和 epoch 均可信。
- `degraded`：中心质量下降，或已由备份/二级节点维持连续性，但还不能恢复完全中心控制。
- `suspect`：heartbeat 过期、digest 冲突、epoch 倒退、节点投票不一致或恢复尚未通过合并校验。
- `failed`：heartbeat 超过硬超时，或 peer quorum 判定中心不可用。

典型触发条件：

| 转移 | 触发条件 | 设计意图 |
|---|---|---|
| `normal -> degraded` | heartbeat age 超过 `heartbeat_warning_s` | 提前进入谨慎模式，避免突然切主 |
| `normal/degraded -> suspect` | heartbeat stale、digest conflict、center epoch stale | 区分“网络抖动”和“态势不一致” |
| `suspect -> failed` | heartbeat age 超过 `heartbeat_failure_s` 或 peer votes 达到 quorum | 只有明确失效才启动降级规划 |
| `failed -> degraded` | 备份/二级节点/集群代表接管 | 降级接管不等于恢复中心权威 |
| `degraded/suspect -> normal` | 双轨合并无冲突且人工接受标志为真 | 防止短暂 heartbeat 恢复导致双主 |

不能只靠 heartbeat 恢复的原因：

1. heartbeat 只能证明中心节点“还在发送”，不能证明它拥有最新航迹和分配版本。
2. 中心恢复时可能落后于降级期间形成的 peer 计划，直接恢复会造成 stale assignment。
3. 多节点网络可能分区，部分节点看到中心恢复，部分节点仍在降级协商，单次 heartbeat 会形成双主。
4. D3/D5/D6 依赖 `plan_id/version/global_track_id` 连续性，恢复必须比较 digest、epoch 和所有权，再由人工接受标志闭环。

因此 `merge_recovery()` 采用双轨合并：中心计划和 fallback 计划并行比较，完全一致进入 `accepted`，单边出现进入 `review`，重复所有者或版本冲突进入 `conflicts`。只有 `conflicts` 和 `review` 均为空且 `human_accept=True` 才恢复 `normal`。

## 4. 层级降级链路

降级顺序固定为分层仲裁，而不是直接从中心跳到完全无中心：

```text
中心 C2 正常
  -> 风险低：continue_center
  -> 中心可用但 D3 plan/version/freshness 硬风险：request_center_replan
  -> 中心可用但 D1/D2/D5 需要补充视角：request_secondary_assist
  -> 中心 C2 失效或 D5 多帧硬冲突：地面备份、固定系留或机动高空二级侦察节点接管区域协调
  -> 二级节点不可用：集群代表 / 完全无中心 CBBA 或拍卖式协商
  -> 协商不收敛：保持、继续观测或安全回退的离线占位状态
```

### 4.1 二级侦察节点的角色

固定系留或机动高空侦察无人机在 D4 中建模为区域二级节点：

- `node_role=NodeRole.SECONDARY_RECON`：表示该节点具备区域观测和协调能力。
- `node_role=NodeRole.FIXED_TETHERED_SECONDARY/MOBILE_HIGH_RECON/MOBILE_SECONDARY_RECON` 或等价 `capability_class="tethered_recon" / "fixed_tethered_secondary" / "mobile_high_recon" / "mobile_secondary_recon"`：用于 leader 排序和审计。
- `coordinator_only=True`：表示该节点只做区域协调和观测摘要，不作为执行资源参与任务所有权分配。
- `coverage_cell`：表示节点覆盖的粗粒度小区或区域，后续应作为多区域接管过滤条件。
- `heartbeat_timestamp_s` / `heartbeat_stale_after_s`：表示最近心跳和过期门限；心跳过期时二级节点不作为辅助或接管候选。
- `lease_epoch`：表示二级节点租约版本；同等优先级下新租约优先。
- `cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio` 和 `cross_view_support_count`：表示来自 D5/D6/main 的二级侦察新鲜度、指向、覆盖和跨视角支持摘要；这些字段只影响候选和审计，不让 D4 自己做视觉注册。

当二级节点健康时，它可以作为区域协调者，向覆盖范围内的拦截资源提供：

- 航迹摘要：例如 `TrackSummary` 的高置信 source count、age 和 coverage cell。
- 局部资源摘要：附近资源的可用性、通信质量和 operator hold 状态。
- 面向 D5 的观测/图像 cue 语义：例如某个 `global_track_id` 在二级节点视场中的候选位置和置信度。

这些 cue 只作为 D5 末端视觉配准的辅助证据。它们不能授权本地处置，不能改变 `global_track_id`，不能绕过 D3 plan version，也不能替代 D5 的友方/未知身份保守判断。

### 4.2 Leader 选择

`FailoverCoordinator.elect_leader_resource()` 使用确定性排序：

```text
takeover_priority
-> node_role rank
-> lease_epoch
-> availability_band
-> comm_band
-> capability_class
-> node_id
```

设计意图：

- `takeover_priority`：让预设备份或区域节点优先于临时资源。
- `node_role`：优先级为 `ground_backup < secondary_recon < cluster_representative < interceptor`。
- `lease_epoch`：同类节点中选择更新租约，减少旧 leader 复活。
- `availability/comm/capability`：在前序条件相同的情况下选择状态更稳的节点。
- `node_id`：最后使用确定性 tie-break，保证并行节点选择一致。

当前实现中 `GROUND_BACKUP` 和 `SECONDARY_RECON` 都映射为 `coordination_mode="secondary_node"`。这表示“仍有区域/备份协调者”，不是完全无中心。若需要更细审计，后续可拆分为 `ground_backup_node` 与 `secondary_recon_node`。

### 4.3 被动降级与主动降级

D4 将降级触发源分成两类，避免把“中心真的失效”和“中心仍在但局部证据不可信”混为一类。

| 模式 | 触发源 | 典型证据 | 首选动作 |
|---|---|---|---|
| `passive_failover` | C2 被摧毁、失效、heartbeat 超时、peer quorum 判定失败 | `C2Health.FAILED`、中心 epoch 停滞、assignment digest 长时间不可用 | 二级节点接管；无二级节点时进入 CBBA |
| `active_degradation` | C2 未失效，但分辨率、定位、关联或分配证据不足 | D1 协方差增大、D2 ID switch 风险上升、D3 plan stale/not current、D5 本地候选与分配目标不一致；cost margin 低、低置信度、无冲突 `ambiguous/reacquire` 只作为软证据 | 仲裁后继续中心、请求中心重分配、请求二级辅助、主动降到二级节点或分布式 |

被动降级是“控制中心不可用”的结构性问题；主动降级是“中心计划仍存在但局部证据不支持继续执行”的一致性问题。主动降级不能直接绕过 D3/D5 的版本、授权和身份规则，它只是给出保守协调建议。

### 4.4 主动降级仲裁器

`ActiveDegradationArbiter` 是 D4 侧新增的离线规则仲裁器。它不订阅真实链路，也不发布控制命令；它只把 D1/D2/D3/D5 的摘要统一为一个 `ActiveDegradationDecision`，供仿真和 D6 评估。

伪接口：

```python
decision = ActiveDegradationArbiter().evaluate(
    track_uncertainty=TrackUncertaintySummary(...),
    association_risk=AssociationRiskSummary(...),
    assignment_validity=AssignmentValiditySummary(...),
    terminal_association=TerminalAssociationSummary(...),
    c2_health=C2Health.NORMAL,
    secondary_nodes=[ResourceSummary(...)]
)
```

输入语义：

- `TrackUncertaintySummary`：D1 的定位质量，重点看位置标准差、协方差迹和量测年龄。
- `AssociationRiskSummary`：D2 的身份连续性风险，重点看 ambiguity、ID switch、重复航迹和 track continuity。
- `AssignmentValiditySummary`：D3 的分配是否仍有效，重点看 plan version、是否 current、计划年龄和 cost margin。
- `TerminalAssociationSummary`：D5 的末端视觉配准结果，重点看是否 `locked`、是否来自 D3 指派的 `assigned_resource_id`、是否连续多帧非锁定、是否与 assigned `global_track_id` 一致，以及是否存在友方冲突。
- `C2Health`：判断是主动降级还是被动降级。若已为 `failed`，仲裁器直接走 `passive_failover`。
- `secondary_nodes`：二级节点健康和覆盖信息，使用 `ResourceSummary.node_role`、`availability_band`、`operator_hold`、`coverage_cell` 判断可用性。
- `communication_summaries`：可选通信摘要。若传入，二级节点必须存在未过期的 `c2_direct`、`secondary_relay` 或 `video_cue` 链路，才可被视为主动辅助/接管候选。
- 二级生命周期：`summarize_secondary_lifecycle()` 会输出每个二级节点的 heartbeat age、lease epoch、coverage cell、video cue freshness、link stale 和 `secondary_available`，adapter 会把该摘要放入结果供 D6 审计。

决策规则：

| 条件 | D4 决策 |
|---|---|
| D5 与中心/二级分配一致，且 D1/D2/D3 风险低 | `mode=none`，`action=continue_center` |
| D1/D2 风险上升，但 D5 仍一致，且二级节点覆盖该区域 | `active_degradation + request_secondary_assist`，请求二级节点提供区域观测/cue，不直接完全分布式 |
| D3 分配 stale 或非 current，但 D5 仍一致 | `active_degradation + request_center_replan`，优先中心滚动重分配 |
| 只有 `d3_assignment_cost_margin_low`、D5 低置信度或无冲突 `ambiguous/reacquire` | `continue_center` 或 `request_secondary_assist`，继续观察，不触发中心重规划或分布式降级 |
| D5 单窗口不一致但未连续恶化 | 若无硬风险则继续观察；若需要补充视角且二级节点可用，则请求二级辅助 |
| D5 连续多帧不一致且存在 observed global track mismatch、资源错配、重复锁定、cross-view 高风险或友方/身份冲突 | 触发主动仲裁；二级节点健康且覆盖该 `coverage_cell` 时输出阶段 1 `degrade_to_secondary` |
| 硬不一致持续且二级节点不可用、不可达或不覆盖当前区域 | `degrade_to_distributed`，进入 CBBA/拍卖式保底协商 |
| 友方冲突或身份证据冲突 | `hold_for_review`，只输出审计和人工复核需求 |
| `duplicate_terminal_lock=True` | 不视为 D5 一致，进入主动仲裁，优先请求二级辅助或中心复核 |
| `cross_view_risk_score` 高 | 不视为稳定一致，进入主动仲裁，优先二级节点辅助/接管 |

主动降级到二级节点采用两阶段语义，防止 D7 在重分配尚未完成的同一帧直接进入视觉 PNG：

1. 阶段 1：D4 输出 `degrade_to_secondary` 只表示已经选择二级节点并启动重分配；`build_d7_secondary_handoff()` 返回 `phase=1`、`reassignment_complete=false`、`visual_png_allowed=false`，且不输出 D7 动作。D7 不应在该帧进入视觉 PNG。
2. 阶段 2：二级节点的新 plan 已生效且 readiness 为 `takeover_ready` 后，`build_d7_secondary_handoff()` 返回 `phase=2`、`reassignment_complete=true`，并携带 `new_plan_id` 与 `new_plan_version`。若新 plan 下 D5 仍需二级 cue，则对 D7 输出 `request_secondary_assist`；若新 plan 下末端一致，则输出 `continue_center`。`visible_only`、`registration_usable` 或缺失 readiness 均不允许进入 visual PNG gate。

当前实现使用轻量规则阈值表达风险：

- D1：`position_sigma_m >= 20m` 记为中风险，`>= 50m` 记为高风险；`covariance_trace` 和量测年龄也会增加风险因子。
- D2：`ambiguity_score`、在线 duplicate/quality risk 始终按既有门限判断；只有 `truth_metrics_available=True` 时才使用 ID switch，只有 `continuity_available=True` 时才使用 track continuity。
- D3：`is_current=False` 和 `plan_age_s` 超限是硬分配风险；`cost_margin` 过低是软计划风险，单独出现时表示需要观察/迟滞，不直接请求中心重规划。
- D5：重复末端锁定、资源错配、observed `global_track_id` mismatch、cross-view 高风险和 friend conflict 是硬证据；`association_confidence` 低、`ambiguity_score` 高、无冲突连续非锁定帧属于软证据，默认继续中心或请求二级 cue。`friend_conflict` 优先级最高，直接 `hold_for_review`。
- 通信：传入通信摘要时，二级节点链路超过 `stale_after_s` 会被视为不可用；只有二级节点不可用时，主动持续不一致才降到 `distributed_cbba/auction`。
- 迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`risk_window_size` 和 `risk_window_threshold`。默认值保持轻量单步行为；复用同一个 arbiter 时，可要求多窗口风险满足阈值才从辅助升级到二级/分布式降级，并要求满足最短 dwell 和连续低风险 release 条件后才回到 `continue_center`。

这些阈值是离线仿真默认值，不代表真实传感器或真实系统参数。后续应由 D6 批量实验做敏感性分析。

### 4.5 二级侦察校准口径

D4 不直接做相机投影、bbox 几何门控、跨视角注册或 global track 绑定；这些由 D5/main 写盘并由 D6 聚合。D4 只消费 coverage、heartbeat/link/cue freshness、gimbal pointing、stable cross-view registration、not-registered 诊断、review label 和 plan activation metadata。

当前 AirSim/P1 证据分两层解释：

- `p1_d4d5_mobile_recon_20260708_055948*`：3 seeds 下 mobile high recon 的 radar cue、gimbal pointing 和 D4 三类动作正常，但二级网络同帧全覆盖仍为 0.0，联合覆盖约 0.65-0.69，degradation case 多数仍是 `secondary_detect_available_but_not_registered`。
- `p1_d4d5_registration_calibration_runtime_v2_20260708*`：单 seed、200 m、FOV 110、1920x1080、3 个机动高空二级节点下，D6 上游几何统计为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`；stable cross-view registration 为 51/55/53，cross-view association 为 4/4/5，degradation case not-registered 为 35/35，平均 full-view 为 0.048，平均 coverage 为 0.771。它证明 stable registration/not-registered 字段可由 D5/D6/main 产生并被 D4 消费；projection/geometry gate 只作为上游标定背景，D4 不直接消费或计算，且仍需多 seed 标定阈值、误注册风险和 review label。

因此 D4 把二级侦察结果记录为四级 readiness：`not_ready`、`visible_only`、`registration_usable`、`takeover_ready`。`visible_only` 只说明二级看见目标但没有可用 cross-view/global binding；`registration_usable` 说明稳定注册存在但 coverage、network full-view 或综合 score 还不足以接管；只有 `takeover_ready` 与新鲜二级链路、D3/main 回填的 plan owner/version 同时满足时，才能作为二级接管必要性和成功的正证据。仅有检测可见、gimbal OK 或 coverage ratio > 0 不会自动激活 `secondary_plan_active`。

## 5. CBBA、拍卖和合同网协议

### 5.1 CBBA 原理

CBBA（Consensus-Based Bundle Algorithm）把任务分配拆成两个过程：

1. Bundle building：每个节点根据本地收益把任务加入自己的 bundle。
2. Consensus：节点交换各任务的 winner 和 bid，发现自己失去某个任务后释放该任务及其后的 bundle，再重新竞标。

在本模块中，任务是连续性任务 `TrackSummary`，资源是可执行的 `ResourceSummary`。二级节点如果 `coordinator_only=True`，会被排除在执行资源之外。

本模块的打分函数是合成研究基线：

\[
s_{ij}=2.0C_j+1.4A_i+0.5M_i+1.2Q_{ij}+1.0S_j-0.8R_j
\]

其中：

- \(C_j\)：航迹置信等级。
- \(A_i\)：资源可用性等级。
- \(M_i\)：通信质量等级。
- \(Q_{ij}\)：能力匹配分。
- \(S_j\)：source count 奖励。
- \(R_j\)：航迹年龄惩罚。

该分数只用于离线协商排序，不是实际效果或处置能力估计。

### 5.2 收敛假设

CBBA 收敛依赖以下条件：

- peer 图在仿真窗口内连通。
- 任务和资源摘要在一个 `epoch` 内相对静态。
- 每个节点使用相同 tie-break 规则。
- 消息最终能在足够轮数内到达。
- bundle 长度有限。

若丢包过高或轮数不足，`CBBAResult.converged=False`，当前实现不会发布有效 assignment，而是保留审计信息。这是保守安全边界。

### 5.3 通信开销

每轮每条边交换 winner/bid 状态，量级近似为：

\[
O(|E|\cdot|\mathcal{T}|)
\]

其中 \(E\) 为 peer 边数，\(\mathcal{T}\) 为任务数。全连接网络为 \(O(N^2|\mathcal{T}|)\)，稀疏网络减少单轮消息量，但增加网络直径和共识轮数。

### 5.4 与拍卖和合同网的关系

- 单轮拍卖：实现简单、通信少，但在冲突和重分配场景中容易出现局部最优或重复所有者。
- 合同网协议：适合 manager/contractor 结构，若二级节点健康，可由二级节点扮演区域 manager；但 manager 失效后仍需 peer 共识。
- CBBA：比单轮拍卖更重，但能通过 winner state 传播减少冲突，适合 D4 作为完全无中心降级基线。

与 D3 的中心化 Hungarian 或最小费用流相比，CBBA 不保证全局最优。它的目标是中心失效时的保底一致性，而不是替代中心化最优计划。

### 5.5 CBBA cost gap benchmark

`build_cbba_cost_gap_benchmark()` 用于同场景离线对照：

```python
benchmark = build_cbba_cost_gap_benchmark(
    cbba_result,
    center_assignments={"track-1": "int-1"},
    cost_by_task_resource={"track-1": {"int-1": 1.0, "int-2": 1.4}},
)
```

其中 `center_assignments` 和 `cost_by_task_resource` 必须来自 D3/main 的中心化计划和 cost matrix。D4 只计算 `cbba_total_cost`、`center_total_cost`、`absolute_cost_gap`、`relative_cost_gap`、completion gap、conflict/round/message 指标和缺失 cost pair 审计，不接入 MIT/CA-CBBA，也不在完全无中心路径构造虚拟中心。

## 6. 实施流程

### 6.1 正常运行

1. D3 发布中心化 AssignmentPlan，D4 只记录 digest、epoch 和资源摘要。
2. D4 定期接收 heartbeat 和 assignment digest。
3. 固定系留或机动高空二级侦察节点在健康时作为区域观察源，维护覆盖区、cue freshness、gimbal 和 cross-view support 摘要。

### 6.2 中心失效

1. `update_health()` 根据 heartbeat age 和 peer votes 转入 `failed`。
2. `plan_degraded()` 调用 `elect_leader_resource()`。
3. 若 leader 是 `ground_backup` 或 `secondary_recon`，进入 `coordination_mode="secondary_node"`。
4. 若无可用二级/备份节点，则由集群代表或普通资源进入 `coordination_mode="distributed_cbba"`。
5. `coordinator_only` 节点被排除出执行资源，只参与协调审计。
6. `CBBANegotiator.run()` 生成保底 assignment 或非收敛审计结果。

### 6.3 中心恢复

1. heartbeat 恢复后先进入 `suspect`，不直接回 `normal`。
2. `merge_recovery()` 对中心计划和 fallback 计划做双轨合并。
3. 无冲突、无 review 且 `human_accept=True` 才恢复 `normal`。
4. 否则保持 `degraded`，等待上层重新确认。

### 6.4 主动降级流程

1. 中心 C2 仍处于 `normal/degraded/suspect`，但 D4 收到 D1/D2/D3/D5 的风险摘要。
2. `ActiveDegradationArbiter.evaluate()` 先判断 D5 末端结果是否与 D3 分配的 `global_track_id` 一致。
3. 若 D5 一致且风险低，继续当前中心计划。
4. 若 D5 一致但 D3 stale/not current 等硬分配风险上升，优先请求中心滚动重分配；若只是 cost margin 低，则继续观察。
5. 若 D5 一致但 D1/D2 风险上升，优先请求二级节点补充观测，不直接进入完全分布式。
6. 若 `friend_conflict=True`，直接 `hold_for_review`。
7. 若 `duplicate_terminal_lock=True`，不视为一致锁定，进入主动仲裁。
8. 若 D5 连续多帧 `ambiguous/hold/reacquire` 但没有 observed mismatch、资源错配、重复锁定或友方冲突，则只继续中心或请求二级 cue。
9. 若本地视觉候选与分配目标长期不一致，或出现资源错配、重复锁定、cross-view 高风险等硬证据，进入主动降级仲裁。
10. 仲裁时优先选择覆盖当前 `coverage_cell` 且链路新鲜的健康二级节点；无可用二级节点时才进入完全无中心 CBBA/拍卖。
11. 所有主动降级结果均输出 `ActiveDegradationDecision`，交给 D6 记录，不允许本地节点自行改写 `global_track_id`。

## 7. 关键接口

### 7.1 `FailoverCoordinator`

- `observe_center(now_s, heartbeat_ok, digest_ok, center_epoch)`：处理中心状态观测。
- `update_health(now_s, peer_fail_votes, quorum_size)`：根据超时和 quorum 更新状态。
- `elect_leader_resource(resources)`：选择备份/二级/代表节点。
- `plan_degraded(tasks, resources, network, now_s, ...)`：执行降级计划。
- `merge_recovery(center_assignments, fallback_assignments, human_accept, now_s)`：中心恢复双轨合并。

### 7.2 `CBBANegotiator`

- `run(tasks, resources, network, start_time_s)`：运行多轮 bundle building 和 winner consensus。

### 7.3 `ActiveDegradationArbiter`

- `evaluate(track_uncertainty, association_risk, assignment_validity, terminal_association, c2_health, secondary_nodes)`：输出主动/被动仲裁决策。
- 可选参数：`communication_summaries` 和 `current_time_s`。传入后，二级节点必须有未过期链路摘要才可用于 `request_secondary_assist` 或 `degrade_to_secondary`。

输出动作包括：

- `continue_center`：继续中心计划。
- `request_center_replan`：请求 D3 滚动重分配。
- `request_secondary_assist`：请求覆盖区二级节点补充观测摘要或图像 cue。
- `degrade_to_secondary`：主动或被动降到二级节点区域协调；在主动降级场景中这是阶段 1 接管触发，表示二级重分配未完成，不是 D7 视觉 PNG 放行。
- `degrade_to_distributed`：无可用二级节点时进入完全无中心 CBBA/拍卖。
- `hold_for_review`：友方冲突或身份冲突时只保持审计和人工复核。

`D7SecondaryHandoff`/`build_d7_secondary_handoff()` 用于把 `degrade_to_secondary` 转换为 D7 可消费的两阶段门控结果。阶段 1 不携带 `new_plan_id/new_plan_version` 且 `visual_png_allowed=false`；阶段 2 必须携带 `new_plan_id/new_plan_version` 和 `secondary_capability_class=takeover_ready`，并把 D7 动作限制为 `request_secondary_assist` 或 `continue_center`。

`SecondaryTakeoverPlanMetadata`/`build_secondary_takeover_plan_metadata()` 是 D4 record 的 plan lifecycle 合同。它区分：

- `pending_secondary_plan`：D4 已选择二级节点并触发重分配，但当前 active plan owner 仍是 center 或上游当前 owner；metadata 记录 source node、当前 plan id/version 和 supersedes 字段。
- `secondary_plan_active`：main/D3 已回填二级 plan id/version 并标记 active；metadata 记录 `active_plan_owner=secondary_node` 和 `secondary_reassignment_complete=true`。
- `not_applicable`：非二级接管动作，D4 只保留当前 active owner。

D4 不在这个 metadata 中创建系统级 `AssignmentPlan`，只给 main/D3/D7 提供可消费状态。

`ActiveDegradationDecision.to_metrics()` 输出：

- `d4_action`
- `degradation_mode`
- `target_node_id`
- `risk_factors`
- `terminal_consistent`
- `failover_time`
- `secondary_selected_rate`
- `distributed_conflict_count`

### 7.4 数据结构

- `TrackSummary`：只保留粗粒度任务摘要，不携带高精度状态。
- `ResourceSummary`：描述资源/节点角色、可用性、通信质量、租约和覆盖区域。
- `CBBAResult`：用于 D6 的降级指标来源。
- `TrackUncertaintySummary`：D1 定位不确定度摘要。
- `AssociationRiskSummary`：D2 多目标关联风险摘要。
- `AssignmentValiditySummary`：D3 分配有效性摘要。
- `TerminalAssociationSummary`：D5 末端视觉配准摘要。
- `CommunicationSummary`：D4 通信新鲜度摘要，表达源节点、目标节点、可选中继节点、链路类型、发送/接收时间、载荷类型和过期时间。
- `SecondaryNodeLifecycleSummary`：二级节点生命周期摘要，表达 heartbeat、lease、coverage、video cue freshness、link stale 和最终可用性。
- `ActiveDegradationDecision`：D4 仲裁结果。
- `D4DecisionRecord`：D4 adapter 事件记录，可直接转换为 D6 `EventRecord` kwargs，含 secondary takeover plan lifecycle metadata。
- `SecondaryTakeoverPlanMetadata`：D4 二级接管 metadata，表达 pending/active plan 状态、source node、当前/二级 plan id/version 和 supersedes 关系。
- `CBBACostGapBenchmark`：D4 CBBA 与 D3 中心化 cost baseline 的离线对照字段。

## 8. 参数与调参建议

| 参数 | 默认/位置 | 建议 |
|---|---|---|
| `heartbeat_warning_s` | `FailoverCoordinator` | 应小于 stale 阈值，用于提前进入 degraded |
| `heartbeat_stale_s` | `FailoverCoordinator` | 控制 suspect 灵敏度，过小会频繁误报 |
| `heartbeat_failure_s` | `FailoverCoordinator` | 控制 failed 判定，必须大于正常抖动上界 |
| `stable_recovery_s` | `FailoverCoordinator` | 后续可用于恢复稳定窗口 |
| `takeover_priority` | `ResourceSummary` | 预设备份/二级节点应小于普通资源 |
| `lease_epoch` | `ResourceSummary` | 新租约优先，防止旧 leader 复活 |
| `bundle_limit` | `plan_degraded()` | 1 适合一资源一任务基线；多任务资源可增大 |
| `max_rounds` | `CBBANegotiator` | 丢包或稀疏网络下需增大 |
| `round_period_s` | `CBBANegotiator` | 影响 takeover duration 和消息传播 |
| `packet_loss/min_delay/max_delay` | `SimulatedNetwork` | 用于通信退化敏感性实验 |
| `position_sigma_medium_m/high_m` | `ActiveDegradationConfig` | D1 定位风险门限，需按仿真传感器精度标定 |
| `association_ambiguity_medium/high` | `ActiveDegradationConfig` | D2 关联不确定度门限 |
| `max_plan_age_s/min_cost_margin` | `ActiveDegradationConfig` | `max_plan_age_s` 是 D3 stale 硬门限；`min_cost_margin` 是软计划裕度门限，单独出现时只观察/迟滞 |
| `terminal_confidence_min` | `ActiveDegradationConfig` | D5 locked 最低置信度 |
| `cross_view_risk_high` | `ActiveDegradationConfig` | D5 多视角冲突/支持不足风险门限 |
| `non_locked_frame_limit` | `ActiveDegradationConfig` | 连续 `ambiguous/hold/reacquire` 触发主动仲裁的帧数 |
| `mismatch_frame_limit` | `ActiveDegradationConfig` | 末端候选与分配目标长期不一致的触发帧数 |
| `risk_window_size/risk_window_threshold` | `ActiveDegradationConfig` | 主动降级窗口化风险阈值，用于防止单窗口噪声直接升级 |
| `min_dwell_s` | `ActiveDegradationConfig` | 主动/被动降级决策的最短保持时间 |
| `release_consecutive_consistent_frames` | `ActiveDegradationConfig` | 释放降级并回到中心计划前所需的连续低风险一致帧数 |
| `heartbeat_timestamp_s/heartbeat_stale_after_s` | `ResourceSummary` | 二级节点生命周期心跳和过期门限 |
| `stale_after_s` | `CommunicationSummary` | 二级链路过期时间；过期后不再作为可用二级辅助 |

二级节点调参建议：

- 区域二级节点使用 `node_role=SECONDARY_RECON`、`capability_class="tethered_recon"`、`coordinator_only=True`。
- 若同一区域有多个二级节点，使用 `takeover_priority` 和 `lease_epoch` 明确主备。
- 后续多区域仿真应按 `coverage_cell` 过滤二级节点接管范围，避免一个二级节点接管无覆盖区域。

## 9. 仿真验证

默认脚本：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py \
  --nodes 5 --tasks 4 --packet-loss 0.10 --seed 7
```

当前默认仿真由 `default_resources()` 生成普通节点，没有构造 `NodeRole.SECONDARY_RECON`。因此默认结果代表“二级节点不可用或未建模时的 CBBA 降级基线”。二级节点优先接管由 `tests/test_coordinator.py` 中的单元测试覆盖：

- `test_center_failure_degrades_to_secondary_recon_node_before_distributed_cbba`
- `test_secondary_unavailable_falls_back_to_distributed_cbba`

主动降级仲裁由 `tests/test_active_degradation.py` 覆盖：

- 低风险且 D5 一致时继续中心计划。
- D1/D2 风险上升但 D5 一致时请求二级辅助，不直接完全分布式。
- D3 分配无效但 D5 一致时请求中心滚动重分配。
- D5 持续不一致且二级节点覆盖时主动降到二级节点。
- 二级节点不可用或不覆盖当前区域时主动降到分布式 CBBA/拍卖。
- `C2Health.FAILED` 时走 `passive_failover`。

显式二级节点仿真场景已由 `run_failover_simulation()` summary-list 输入和单元测试覆盖，构造方式为：

1. 在资源集中加入 `sec-1`，设置 `node_role=SECONDARY_RECON`、`coordinator_only=True`、`coverage_cell="cell-north"`。
2. 让 `task.coarse_cell` 落在该覆盖区。
3. 对比 `secondary_node` 与 `distributed_cbba` 的接管时间、消息量、冲突数。
4. `coordination_mode/leader_role/coverage_cell` 已透传到 metrics JSON，供 D6 绘制分组统计。

## 10. 指标

D4 应向 D6 输出或支持计算：

- `failover_time`：从中心故障到降级计划形成的时间。
- `consensus_rounds`：CBBA 共识轮数。
- `degraded_completion_rate`：降级模式下任务分配完成率。
- `conflict_count`：过渡过程中 winner view 冲突次数。
- `messages_sent/messages_delivered/messages_dropped`：通信开销和丢包影响。
- `estimated_bytes`：粗略消息字节估计。
- `coordination_mode`：`secondary_node` 或 `distributed_cbba`。
- `leader_role`：`ground_backup/secondary_recon/cluster_representative/interceptor`。
- `coverage_cell`：二级节点覆盖区域。
- `degradation_mode`：D6 事件 metadata 使用 `none/passive/active`；D4 原始枚举另存为 `d4_degradation_mode`。
- `selected_coordinator`：`center/secondary_node/distributed_cbba/hold_review`。
- `trigger_reason` / `trigger_timestamp` / `decision_timestamp`：D6 主动降级评估所需触发和决策时间。
- `review_label`：离线复核标签，取值为 `necessary/unnecessary/inconclusive`；缺少真实标签时 D6 不应从事件名自证必要性。
- `degradation_action`：继续、请求重分配、请求二级辅助、降到二级、降到分布式或 hold。
- `active_degradation_reason`：主动仲裁触发原因。
- `risk_factors`：D1/D2/D3/D5 风险因子列表。
- `terminal_consistent`：D5 末端关联是否与分配目标一致。
- `secondary_available/link_stale/video_cue_freshness_s`：二级节点生命周期和链路 freshness 审计字段。
- `secondary_takeover_state/active_plan_owner/secondary_plan_source_node_id/secondary_plan_id/secondary_plan_version`：二级接管 pending/active 状态和 plan metadata。
- `secondary_network_coverage_available/secondary_network_full_view_gap/secondary_network_mean_coverage_ratio`：二级网络覆盖与全覆盖缺口。
- `cross_view_association_count/stable_cross_view_registration_count/not_registered_count`：D5/D6/main 输出的跨视角支持和未注册统计，供 D4 做接管必要性解释。
- `secondary_detect_available_but_not_registered/secondary_detect_to_registration_gap`：二级可见但未完成 global binding/registration 的诊断。
- `cbba_total_cost/center_total_cost/absolute_cost_gap/relative_cost_gap/completion_rate_gap`：CBBA 与 D3 中心化基线的离线 cost gap benchmark 字段。

当前 `coordination_mode` 已存在于 `CBBAResult.final_views`，并由 `build_cbba_d6_metadata()` 与 `run_failover_simulation()` 透传到顶层 metrics，避免实验报告把二级节点接管和完全分布式 CBBA 混在一起统计。CBBA cost gap benchmark 仍需要 main/D3 保存同场景 cost matrix/current plan，D4 helper 只负责单场景计算与字段归一化。

## 11. 与 D3/D5/D6 的接口关系

### D3 集中式分配

D3 是中心存在时的主分配模块。D4 不应覆盖 D3 的正常计划，只缓存 digest、version、epoch 和资源摘要。中心失效时，D4 使用上一版可验证计划作为降级基准；中心恢复后，D4 必须通过 `merge_recovery()` 与 D3 新计划对齐。主动降级中，如果 `AssignmentValiditySummary` 显示计划过期或非 current，D4 的首选动作是 `request_center_replan`，不是直接完全分布式；如果只是 `cost_margin` 过低，D4 将其视为软证据，继续中心或请求二级 cue，等待 D3/main 的正常滚动迟滞处理。

### D5 终端视觉配准

二级侦察节点健康时，可把区域图像 cue 或观测摘要传给小范围拦截资源，帮助 D5 做末端候选匹配。D4 只负责描述 cue 的来源、作用域和版本，不负责像素几何配准。D5 必须继续执行授权、plan version、友方身份和 `global_track_id` 不改写规则。主动降级中，D5 的长期目标不一致、资源错配、重复锁定或友方冲突是触发仲裁的强证据；无冲突的多帧 `ambiguous/hold/reacquire` 是软证据，优先请求二级 cue 或继续观察，避免过度切换。D4 只消费 D5/D6/main 的 stable registration、not-registered 和 coverage/freshness 汇总，不把二级 detect 可见直接解释为可接管。

### D6 评估

D6 消费 D4 的 transition log、CBBAResult 和 merge result，计算 failover、consensus、conflict、completion、通信开销和恢复合并指标。建议 D6 将 `coordination_mode` 作为分组变量，分别统计二级节点接管和完全分布式 CBBA。

## 12. 局限与后续工作

当前局限：

- 默认仿真未构造 `secondary_recon`，二级节点路径主要由单元测试覆盖。
- 主动仲裁已按 `coverage_cell` 过滤二级节点；被动 coordinator 的全局 leader 选择仍未按每个任务覆盖区拆分。
- 默认仿真的默认资源集仍不构造 `secondary_recon`；显式 summary-list 场景已能在 metrics 顶层透传 `coordination_mode/leader_role/coverage_cell`。
- CBBA 打分函数是合成基线，没有与 D3 的真实中心化代价函数完全对齐。
- 网络模型是内存队列，只用于延迟/丢包统计，不代表真实链路。
- 主动降级仲裁器目前是规则基线，已包含 dwell/release/window 防抖配置，但未用 5v5/N-v-N 批量 episode 标定阈值。
- 2026-07-08 mobile recon 与 registration calibration 已跑通 coverage、stable registration 和 not-registered 字段，但 full-view 仍低、degradation case not-registered 仍高，且 registration v2 只有单 seed。
- D5 `TerminalAssociation` 当前在 D4 内归一化为 `TerminalAssociationSummary`，跨模块字段合同还需要主智能体统一。

后续工作：

1. 增加二级节点默认或可选仿真场景。
2. 增加多 `coverage_cell`、多二级节点租约冲突的 episode 级仿真。
3. 在 main/D6 多 seed 报告中持续聚合 `coordination_mode/leader_role/coverage_cell`。
4. 保留轻量 CBBA 为当前默认基线；如后续需要，另行评估 MIT CBBA/CA-CBBA/auction/contract-net 的许可证、依赖和同场景 benchmark。
5. 把 D3 的 plan version、authorization state 和 D5 的 cue 审计字段纳入降级日志。
6. 增加中心恢复后的多轮稳定窗口，而不是只依赖一次合并调用。
7. 将主动降级决策接入系统级日志，交给 D6 统计 `active_degradation_count`、`false_degradation_rate`、`active_degradation_precision`、stable registration、not-registered 和 `terminal_disagreement_duration`。
