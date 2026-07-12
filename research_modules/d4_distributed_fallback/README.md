# D4 分布式协同与降级接管

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `scripts/run_p1_failover_replay.py`：版本化 P1 二级/分布式接管扰动矩阵。
- `scripts/run_p2_coalition_replay.py`：隔离式 P2 联盟故障 replay；不接入在线 D4。
- `tests/`：状态机、CBBA、接管和仿真测试。
- `reports/EXPERIMENT_REPORT.md`：实验报告与曲线。
- `reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放集成计划。

## 快速运行

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --drone-count 5
```

运行隔离式 P2 联盟 replay：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p2_coalition_replay.py
```

只有显式提供本地参考树时才探测外部能力：`--mit-cbba-path PATH`、`--ca-cbba-path PATH`。探测不会 import 或执行外部代码，也不新增默认依赖。

运行 P1 接管扰动矩阵：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_failover_replay.py
```

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- `C2Health` 状态机：`normal -> degraded -> suspect -> failed`，heartbeat 使用滑动窗口和 `degraded/suspect` 防抖确认，中心恢复需双轨合并，不能只靠单次 heartbeat。
- 被动降级链路：中心 C2 失效 -> 固定系留或机动高空二级侦察节点/地面备份 -> 完全无中心 CBBA。
- 主动降级仲裁：中心未失效但 D1/D2/D3/D5 风险升高时，输出继续、请求中心重分配、请求二级辅助、降到二级节点或分布式的离线决策。
- 中心重规划请求生命周期：包顶层导出冻结 DTO `CenterReplanStatus` 和 `build_center_replan_risk_signature()`；`D4ArbitrationAdapter.evaluate(center_replan_status=...)` 只读消费 `pending|applied|acknowledged_no_change|expired`。`ActiveDegradationConfig.center_replan_cooldown_s` 默认 2.0 秒，以 `resolved_at`、pending 无 resolved 时以 `requested_at` 为起点；窗口内新增非硬风险继续 `continue_center`，在严格 `timestamp >= reference+cooldown` 边界才重新开放请求。若 pending 属于 current coalition，且中心 alive、D3 plan/coalition 双版本 current、D5 全部 current primary 已稳定 locked 并形成无冲突 consensus，D4 将旧请求收敛为 `continue_center`，输出 `center_replan_resolution_hint=acknowledged_no_change`。friend/duplicate/wrong-binding、plan/coalition version、center health、coalition conflict 或 commit 缺 ACK 均优先 fail closed，不会被 recovery 覆盖。该 `continue_center` 保留风险 evidence，不替代 D5/D7 独立门控。
- 二级节点建模：支持 `NodeRole.SECONDARY_RECON`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`、`FIXED_TETHERED_SECONDARY` 或 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；二级节点默认 `coordinator_only`，只做协调和侦察证据，不作为拦截执行资源。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、lease、coverage、cue/gimbal/link、network full-view、stable/not-registered 计数及其 `registration_evidence_source`/presence 标志，并区分节点类型与 `not_ready|visible_only|registration_usable|takeover_ready` 四级瞬时 readiness。adapter 进一步记录 `takeover_ready_consecutive_decisions`、ready since/duration、required decisions/duration、`takeover_ready_sustained` 和回落原因，供 D4 仲裁与 D6 逐决策审计。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size`、`risk_window_threshold` 和 `center_replan_cooldown_s`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。adapter 同时输出 hard/soft risk 拆分、center replan cooldown 状态和 `active_degradation_false_trigger_candidate`，供 D6 统计误触发。
- D2 在线指标可用性：`AssociationRiskSummary` 显式携带 `truth_metrics_available`、`continuity_available` 和连续 `duplicate_track_risk`。在线 truth 隔离时，IDSW/continuity 的数值占位不参与主动降级；`duplicate_track_risk >= 0.5` 只产生 soft `d2_duplicate_track_risk_high` 观察证据，不再合成 observed count。只有显式 `duplicate_track_count/duplicate_assignment_count`、对应 delta/delta sum 或明确 observed flag 才产生 hard `d2_duplicate_track_observed` 并立即阻断。
- D5 cross-view 风险：`TerminalAssociationSummary.cross_view_risk_score` 和 `duplicate_terminal_lock` 会阻止“误判为一致锁定”。
- M-to-N 原子联盟安全语义：`CoalitionSafetyEvidence` 以 duck typing/dict 消费 D3 `assignment_plan_v2` 的 `coalitions`、member、plan/coalition version、`required_resource_count` 和可选 commit。有效 secondary/distributed commit 必须满足完整 required-member ACK、双版本、epoch、成员、lease 和 digest 门控，随后才设置 `atomic_coalition_formed=true`；无有效 commit 时仍按中心可用性输出 `request_center_replan` 或 `coalition_fallback_unsupported`/`hold_or_revoke`。event 记录 `candidate_action`、`gated_action` 和 commit 审计；single-winner CBBA 不冒充 `k>1` 成员形成。合法联盟内多个已授权资源锁定同一 `global_track_id` 不算 duplicate；联盟外、超额、旧 plan 或旧 coalition version 均 fail closed。D4 不改写 `global_track_id`。
- D5 current-coalition recovery 最小接口：`cross_view_summary` 需提供 `global_track_id`、`plan_id/plan_version`、`coalition_id/coalition_version`、`primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`coalition_visual_consensus` 和 `coalition_conflict_state`；若 `coalition_commit_required=true`，还需 commit state、required/acked member IDs、valid 和 conflict reasons。字段缺失、scope 不 current 或 commit 不完整只会使 recovery 不成立。main 当前已传递该 D5 summary，D4 无需也不会修改 main adapter。
- D5 二级覆盖/转换漏斗诊断：adapter 可消费 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap` 和 `secondary_detect_to_cross_view_reject_reasons`；当二级检测可见但 cross-view/global binding/registration 未完成时，event metadata 写入 `secondary_detect_available_but_not_registered`、计数和诊断原因，但不会把该证据直接升级为 `secondary_plan_active`。
- 二级侦察校准解释口径：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不做像素投影或视觉注册。硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；瞬时 `takeover_ready` 还必须通过默认 3 个不同时间戳决策、至少 0.2 s 驻留且相邻证据间隔不超过 1.0 s 的 `SecondaryReadinessWindowConfig`，才允许进入 pending。相同时间戳的多资源/多目标决策不会重复累计。
- 完全无中心视觉证据接入：`DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()` 和 `merge_distributed_visual_evidence_into_tracks()` 可用 duck typing/dict 消费 D5 的 distributed terminal association / cross-peer hypothesis，不导入 D5 类型，也不创建或改写 `global_track_id`。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，除既有风险、review、coverage 和 capability 字段外，新增逐决策注册证据来源/presence、readiness streak/duration/sustained、`previous_state/transition`、pending since、activated at、activation delay 和 `secondary_takeover_fallback_reason`。
- 二级接管 plan metadata：`SecondaryTakeoverPlanMetadata` 明确 `not_applicable`、`pending_secondary_plan`、`secondary_plan_active` 三种状态。active 必须同时满足持续 readiness、source 与选中二级节点一致、plan version 严格更新或保持同一已激活 secondary plan、plan lease epoch 不低于节点要求且 lease 未过期；不满足时保留 pending/not executable 和明确 reject reason。D4 只输出合同和审计，不生成完整系统级 `AssignmentPlan`。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线；D5 视觉支持会提高对应资源出价，`hold`、友方冲突、过期/缺失/冲突 `global_track_id` 会阻止可执行出价，重复锁定风险进入 `assignment_audit` 且不允许多个 owner。
- CBBA gap benchmark：`build_cbba_cost_gap_benchmark()` 使用 D3/main 提供的中心 plan 与 cost matrix，计算 D4 CBBA 相对中心 Hungarian/Min Cost Flow 基线的 cost/completion/conflict/message 差距；D4 不在 no-center 路径运行虚拟中心 Hungarian。
- P2 隔离联盟 replay：`run_p2_coalition_fault_replay()` 复用原生 `CoalitionCommitCoordinator`，并将 `CBBANegotiator` 限定为协调者/补位候选选择，不把 single-winner 结果冒充 `k>1` 原子联盟。固定覆盖中心 -> 二级 -> 完全分布式、missing ACK、stale epoch、expired lease、partition、member loss/replacement，逐场景输出收敛轮数、完成率、冲突和最优差距或 `unavailable_reason`。MIT CBBA/CA-CBBA 只通过 `ExternalCoalitionReplayAdapter` 返回 path/source/capability/unavailable 审计，不替换在线 D4。
- D6 CBBA report metadata：`build_cbba_d6_metadata()` 将 `CBBAResult`、`coordination_mode`、`assignment_audit` 和可选 `CBBACostGapBenchmark` 归一化为多 seed 可聚合字段；`run_failover_simulation()` 顶层 metrics 透出 `d4_action`、`coordination_mode`、`selected_coordinator`、leader 和 coverage。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

## 主动降级入口

`ActiveDegradationArbiter` 接收 D1 定位不确定度、D2 关联风险、D3 分配有效性、D5 末端视觉关联摘要、`C2Health` 和二级节点健康状态，输出 `ActiveDegradationDecision`。典型策略：

- D5 与分配目标一致且风险低：`continue_center`。
- D1/D2 风险升高但 D5 仍一致：优先 `request_secondary_assist`。
- D3 分配 `is_current=False` 或 `plan_age_s` stale 属于硬风险，D5 仍一致时优先 `request_center_replan`；`plan_age_s` 表示计划活性年龄，优先以 `plan.metadata.last_evaluated_at_s`（兼容 `last_evaluated_at/evaluated_at_s/evaluated_at`）为参考，缺失时才回退 `created_at`。稳定 plan ID 的身份年龄保留在证据 `metadata.identity_age_s`，不会把每帧已重新评估的稳定计划误判为 stale。`d3_assignment_cost_margin_low` 属于软证据，单独出现时只继续观察或请求二级 cue，不触发每帧重规划。
- D5 多帧 `ambiguous/hold/reacquire` 但没有 observed global track mismatch、资源错配、重复锁定或友方冲突时，不视为分配失效：有二级覆盖则 `request_secondary_assist`，否则 `continue_center` 并继续观察。
- D5 长期不一致且存在 observed global track mismatch、资源错配、重复锁定、cross-view 高风险或友方冲突等硬证据时，才进入中心重规划、`degrade_to_secondary` 或 `degrade_to_distributed`。
- D5 `friend_conflict=True`：强制 `hold_for_review`；`duplicate_terminal_lock=True` 不视为一致锁定。
- 若传入通信摘要，二级节点必须有未过期的 `secondary_relay`、`video_cue` 或 `c2_direct` 链路才可作为主动辅助/接管目标。
- 若二级节点 `heartbeat_timestamp_s` 超过 `heartbeat_stale_after_s`，即使视频链路摘要新鲜，也不会被选为二级接管目标。
- 机动高空侦察节点随拦截机出动但不拦截；它用 D1/D2 `GlobalTrack` 或雷达 cue 指向目标簇，正常时给局部拦截群提供图像/cross-view 证据，中心失效或主动降级硬条件满足时才可作为二级协调节点。仅有侦察图像、云台指向正常或 coverage ratio > 0 不会自动改变 action；二级可见但未注册时 readiness 为 `visible_only`，只支持 `request_secondary_assist`/诊断；稳定注册但网络全视场或 coverage 不足时为 `registration_usable`；只有 event `secondary_capability_class=takeover_ready` 才作为接管依据并允许后续 D7 visual PNG gate 消费 active secondary plan。
- 当中心和二级节点都不可用时，D4 使用 D5 分布式视觉证据作为 CBBA 的风险/代价输入：多资源视觉支持只增加对应资源的出价，不构造“虚拟中心”，也不重新绑定 `global_track_id`。
- `--drone-count`/main runtime 的 N 只决定输入摘要数量；D4 按实际 `TrackSummary[]`、`ResourceSummary[]` 和二级节点列表长度运行，不在仲裁里固定 2v2 或 5v5。
- 2v2/5v5 AirSim ComputerVision 专项 case 只作为测试 baseline：`case_001_no_degradation` 期望 `continue_center`；`case_002_degrade_to_secondary` 在 sustained readiness 前保持 distributed/observe，成立后才允许二级 pending/active；`case_003_degrade_to_distributed` 期望二级不可用、证据不持续或 lease 过期时分布式。

## P0-B 状态

- 已完成：heartbeat smoothing 使用滑动窗口、miss threshold 和 `degraded/suspect/failed` dwell，短时丢包/延迟不会直接进入 `failed`。
- 已完成：secondary takeover plan 严格校验 lease expiry、plan epoch monotonic 和 executable 状态；过期或非单调替换二级 plan 被拒绝为 pending/not executable，当前 secondary-owned 同 id/version 计划可保持 `secondary_plan_active`，D7 handoff helper 必须看到 `secondary_capability_class=takeover_ready` 才放行。
- 已完成：二级能力评分区分 `not_ready`、`visible_only`、`registration_usable` 和 `takeover_ready`，并消费 coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、stable registration count、not-registered count 和 reject reason；只有 `takeover_ready` 会成为接管依据。
- 已完成：adapter 在瞬时门限之后增加连续 readiness 窗口；单帧或同时间戳重复的 `takeover_ready` 不会进入 pending，heartbeat/link/cue/gimbal/lease 或能力回落会清零 streak 并阻断接管。`not_ready -> takeover_ready` 边沿会重新初始化 `ready_since_s` 和 count=1，能力回落后再次 ready 也从新窗口计时。
- 已完成：主动降级继续保留 hard/soft risk、防抖和 release 条件；`terminal_consistent` 只表示 current center plan binding 是否仍可信。默认无硬冲突 `reacquire` frame 1..3 保留 binding、frame 4 才进入持续路径；friend/duplicate/resource/global-track/mismatch/stale-plan 不使用 grace。该字段不替代 D5/D7 lock/handoff；D6 metadata 可统计 false-trigger candidate。
- 已完成：D2 online truth 隔离语义已接入 D4；`truth_metrics_available=False`/`continuity_available=False` 时不再把 `id_switch_count` 或 `track_continuity=0` 占位解释为硬风险，在线 ambiguity/duplicate/quality 风险路径保持有效。

## P1 状态

- P1 联盟合同结论仍以 `p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md` 为准：D4 所属合同层已闭合。2026-07-12 PNG delivery 验证中 D4 148 项通过，2v2 candidate 为 20/20 且锁定后两帧 dropout 为 2/2，证明本轮 terminal consistency 修正未使主线退化；M5N2 短窗口仍为 0/9。上述结果不关闭 D4 物理协同、完整扰动、成员重构/恢复或误降级标定缺口。
- `d4_p1_failover_disturbance_replay_v1` 已形成版本化九场景矩阵：正常中心无误降级、二级完整 ACK 接管、缺 ACK、成员丢失/补位、分区/恢复、旧 epoch、过期 lease、digest conflict 和中心恢复双轨审计均通过。补位与恢复必须提升 epoch/plan/coalition version 并由新联盟全员重新 ACK；中心恢复不立即夺权。D4 不生成 `AssignmentPlan`，不降低 D3/D5/D7 gate。
- 当前 D4 全量测试为 155 项通过，并包含四成员规模无关回归。模块 replay 只关闭确定性合同与状态轨迹缺口；真实 AirSim 多 seed 的链路时序、secondary-interceptor/peer split、误降级率、恢复时间和物理任务连续性仍开放。
- 二级接管正例：协调者 `Secondary_Recon_1`，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_secondary`。
- 完全分布式正例：协调者为 `INT-02` peer，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_distributed`。
- 缺 ACK 负例：ACK 2/3，最终 `aborted`；T001 三个成员保持 `hold_for_review`，D7 许可为 0。该结果确认 fail-closed；有有效 commit 的二级/分布式路径已获正例验证。
- SimpleFlight 15 s 结果仅用于断点诊断：30 个 active pair 物理命中为 0，不能据此宣称 D4 fallback 或系统物理拦截闭环完成。
- 仍开放：将已冻结的 P1 扰动合同映射到真实 AirSim 同 seed 成对试验，完成 heartbeat/link/cue/gimbal/source、secondary-interceptor/peer split、误降级、恢复时间及物理连续性多 seed 统计。模块 replay 不等于系统矩阵验收完成。
- P2 只允许隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或其他 adapter 不替换当前轻量 CBBA 和 ACK/lease/epoch 合同。
- P2 原生确定性 replay 已收敛：6/6 场景符合预期安全结果；中心 -> 二级 -> 分布式和成员丢失/补位均以 7 轮、完成率 1.0、冲突 2/1、最优绝对差距 0.0 收敛。missing ACK、stale epoch、expired lease、partition 分别以 2/1/2/3 轮 fail closed，完成率均为 0，并输出对应 optimality-gap unavailable reason。原生 6 场景平均完成率为 1/3、总冲突计数为 5。
- 默认环境未配置 MIT CBBA 或 CA-CBBA 参考路径，因此各 6 个外部对照行分别输出 `mit_cbba_reference_path_not_configured`、`ca_cbba_reference_path_not_configured`。MIT MATLAB 源码树即使被检测到也报告 runtime adapter 未集成；已审计的 CA-CBBA 公共仓库没有可执行源码。上述 unavailable 是 capability 结论，不是外部算法性能结论。

历史基线：2026-07-10 calibration sweep 和 2026-07-11 早期 truth-isolated smoke 曾因 network full-view/readiness 不持续而未形成二级 active plan。该结论只描述实施前场景，不再作为当前能力状态；门限与 fail-closed 规则仍保留。
