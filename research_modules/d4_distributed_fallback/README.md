# D4 分布式协同与降级接管

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `tests/`：状态机、CBBA、接管和仿真测试。
- `reports/EXPERIMENT_REPORT.md`：实验报告与曲线。
- `reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放集成计划。

## 快速运行

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --drone-count 5
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
- 中心重规划请求生命周期：包顶层导出冻结 DTO `CenterReplanStatus` 和 `build_center_replan_risk_signature()`；`D4ArbitrationAdapter.evaluate(center_replan_status=...)` 只读消费 `pending|applied|acknowledged_no_change|expired`。`ActiveDegradationConfig.center_replan_cooldown_s` 默认 2.0 秒，以 `resolved_at`、pending 无 resolved 时以 `requested_at` 为起点；窗口内新增非硬风险继续 `continue_center`，在严格 `timestamp >= reference+cooldown` 边界才重新开放请求。持续 `terminal_persistent_disagreement` 可触发首次请求，但不是 cooldown bypass。expired、中心 failed、friend conflict、非法重复锁、assignment/version mismatch、ID switch 和 coalition conflict 均即时绕过。该 `continue_center` 保留 D5 不一致/risk evidence，不替代 D5 对 D7 的独立阻断。
- 二级节点建模：支持 `NodeRole.SECONDARY_RECON`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`、`FIXED_TETHERED_SECONDARY` 或 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；二级节点默认 `coordinator_only`，只做协调和侦察证据，不作为拦截执行资源。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、lease、coverage、cue/gimbal/link、network full-view、stable/not-registered 计数及其 `registration_evidence_source`/presence 标志，并区分节点类型与 `not_ready|visible_only|registration_usable|takeover_ready` 四级瞬时 readiness。adapter 进一步记录 `takeover_ready_consecutive_decisions`、ready since/duration、required decisions/duration、`takeover_ready_sustained` 和回落原因，供 D4 仲裁与 D6 逐决策审计。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size`、`risk_window_threshold` 和 `center_replan_cooldown_s`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。adapter 同时输出 hard/soft risk 拆分、center replan cooldown 状态和 `active_degradation_false_trigger_candidate`，供 D6 统计误触发。
- D2 在线指标可用性：`AssociationRiskSummary` 显式携带 `truth_metrics_available` 和 `continuity_available`。在线 truth 隔离时，IDSW/continuity 的数值占位不参与主动降级；可在线观测的 association ambiguity、duplicate track risk 和由 track quality 汇入的 association risk 仍按既有门限参与，`duplicate_track_risk >= 0.5` 的 D4 转换门限未放宽。
- D5 cross-view 风险：`TerminalAssociationSummary.cross_view_risk_score` 和 `duplicate_terminal_lock` 会阻止“误判为一致锁定”。
- M-to-N 第一阶段安全语义：`CoalitionSafetyEvidence` 以 duck typing/dict 消费 D3 `assignment_plan_v2` 的 `coalitions`、member、plan/coalition version 和 `required_resource_count`。中心可用且联盟完整、版本当前、成员合法时允许中心路径继续；若 arbiter 随后候选 `degrade_to_secondary|degrade_to_distributed`，但对应原子 coalition fallback 尚未形成，则中心可用时改为 `request_center_replan`，中心不可用时输出 `coalition_fallback_unsupported`/`hold_or_revoke`。event 同时记录 `candidate_action` 和 `gated_action`；coordinator 也不会启动 single-winner CBBA。合法联盟内多个已授权资源锁定同一 `global_track_id` 不算 duplicate；联盟外、超额、旧 plan 或旧 coalition version 均 fail closed。D4 不改写 `global_track_id`。
- D5 二级覆盖/转换漏斗诊断：adapter 可消费 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap` 和 `secondary_detect_to_cross_view_reject_reasons`；当二级检测可见但 cross-view/global binding/registration 未完成时，event metadata 写入 `secondary_detect_available_but_not_registered`、计数和诊断原因，但不会把该证据直接升级为 `secondary_plan_active`。
- 二级侦察校准解释口径：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不做像素投影或视觉注册。硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；瞬时 `takeover_ready` 还必须通过默认 3 个不同时间戳决策、至少 0.2 s 驻留且相邻证据间隔不超过 1.0 s 的 `SecondaryReadinessWindowConfig`，才允许进入 pending。相同时间戳的多资源/多目标决策不会重复累计。
- 完全无中心视觉证据接入：`DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()` 和 `merge_distributed_visual_evidence_into_tracks()` 可用 duck typing/dict 消费 D5 的 distributed terminal association / cross-peer hypothesis，不导入 D5 类型，也不创建或改写 `global_track_id`。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，除既有风险、review、coverage 和 capability 字段外，新增逐决策注册证据来源/presence、readiness streak/duration/sustained、`previous_state/transition`、pending since、activated at、activation delay 和 `secondary_takeover_fallback_reason`。
- 二级接管 plan metadata：`SecondaryTakeoverPlanMetadata` 明确 `not_applicable`、`pending_secondary_plan`、`secondary_plan_active` 三种状态。active 必须同时满足持续 readiness、source 与选中二级节点一致、plan version 严格更新或保持同一已激活 secondary plan、plan lease epoch 不低于节点要求且 lease 未过期；不满足时保留 pending/not executable 和明确 reject reason。D4 只输出合同和审计，不生成完整系统级 `AssignmentPlan`。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线；D5 视觉支持会提高对应资源出价，`hold`、友方冲突、过期/缺失/冲突 `global_track_id` 会阻止可执行出价，重复锁定风险进入 `assignment_audit` 且不允许多个 owner。
- CBBA gap benchmark：`build_cbba_cost_gap_benchmark()` 使用 D3/main 提供的中心 plan 与 cost matrix，计算 D4 CBBA 相对中心 Hungarian/Min Cost Flow 基线的 cost/completion/conflict/message 差距；D4 不在 no-center 路径运行虚拟中心 Hungarian。
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
- 已完成：主动降级继续保留 hard/soft risk、防抖和 release 条件；无冲突 `reacquire` 只请求二级 cue/继续观察，不直接接管或分布式降级；D6 metadata 可统计 false-trigger candidate。
- 已完成：D2 online truth 隔离语义已接入 D4；`truth_metrics_available=False`/`continuity_available=False` 时不再把 `id_switch_count` 或 `track_continuity=0` 占位解释为硬风险，在线 ambiguity/duplicate/quality 风险路径保持有效。

## P1 状态

- 已完成：固定系留/机动高空二级节点分类元数据、二级节点 lifecycle summary、secondary takeover pending/active metadata、D5 二级覆盖/转换漏斗未配准诊断、heartbeat smoothing、lease strictness、secondary capability score/readiness class、主动降级 dwell/release/window 防抖配置、主动降级硬/软风险分层、false-trigger metadata、`necessary/unnecessary/inconclusive` review label 口径、pre/post review window、plan activation delay、secondary takeover necessity/success 统计 metadata、D6-compatible decision event metadata、D6-compatible CBBA report metadata、D5 distributed visual evidence -> 完全无中心 CBBA 风险加权、CBBA vs D3 中心化 cost gap benchmark helper、对应单元测试。
- 已完成的 main/runtime P1 基线：episode bus 已接入 D4 adapter event，`request_center_replan` 可触发 D3 new plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过；main runtime 已新增 P1 D4/D5 calibration sweep，用于按高度、FOV、二级节点数量和 standoff 组合批量生成 stress episode；sweep 结束后会自动调用 D6 标准 AirSim calibration report bundle，输出 records/summary/report 口径。该项为 main-owned 集成，修复后口径保持为 main/D3/D7 消费 owner/version，D4 仍只输出仲裁/metadata，不生成系统级 `AssignmentPlan`。
- 最新 AirSim/P1 多 seed 证据：`p1_gap_closure_calibration_20260710` 已完成 10 seeds、50/200 m、3 个机动高空二级节点、FOV 110 度、1920x1080 的 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m 的 network joint full-view 均值为 0.023、范围 0.000-0.154，coverage 均值 0.685；200 m 的 network joint full-view 恒为 0.000，coverage 均值 0.708。两种高度的投影有效率均为 1.0，cross-view association 分别均值 4.6/4.0，stable registration 分别均值 86.3/96.7，说明主要断点已经从“未注册”转为“注册存在但同帧网络全覆盖不稳定”。D4 不直接消费或计算 projection/geometry gate，只解释 D5/main 写入的 readiness evidence。
- 接管门限复核：`takeover_ready` 要求 visible、registered、coverage ratio >= 0.65、network full-view rate >= 0.80、capability score >= 0.70，并保持 heartbeat/link/cue/gimbal 新鲜。1300 条 `degrade_to_secondary` 决策中，新鲜度、visible 和 registered 均通过，score 无低于 0.70；1285 条因 network full-view 低于 0.80 保持 `registration_usable`，其中 600 条同时低于 coverage 0.65。仅 50 m 的 seed 2/5 出现 15 条瞬时 `takeover_ready`，均停留在 `pending_secondary_plan`，没有 active/executable secondary plan，后续又回落为 distributed。因此不能把瞬时全覆盖解释为二级接管成功，也不应放宽安全门控。
- 证据传递审计：D4 已逐决策输出 stable/not-registered 值、presence 和 `registration_evidence_source`，明确区分 D5 稳定计数、resource 计数和 cross-view compatibility 回退。历史 1300 条 AirSim 记录的两个显式计数仍为 `null`，因此 main/D5 仍需把真实逐帧摘要接入，D4 不把 compatibility 来源伪装成稳定注册计数。
- 2026-07-11 truth-isolated AirSim 三组 smoke 证据：`p1_runtime_truth_isolated_d4d5_smoke_20260711`（200 m、2 个二级节点）、`p1_runtime_truth_isolated_d4d5_50m_20260711`（50 m、2 个二级节点）和 `p1_runtime_truth_isolated_d4d5_secondary5_20260711`（200 m、5 个二级节点）均保持在线 truth ID 隔离。三组 `no_degradation` 正例均为 `continue_center`，三组二级不可用/分布式负例均为 `degrade_to_distributed`；预期二级接管正例也均保守输出 `degrade_to_distributed`，因为 `secondary_network_joint_full_view_frame_rate=0.0`，readiness 未达到持续 `takeover_ready`。5 个二级节点将网络平均覆盖提高到约 0.80，但没有形成同帧全目标联合覆盖，因此不能据此激活 secondary plan。
- 保持不变：轻量 CBBA 仍是完全无中心保底基线；未接入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。
- 已完成的 M-to-N 第一阶段：中心 D3 schema v2 联盟安全验证、合法多成员锁语义、旧 plan/coalition version 与越权/超额成员拒绝、中心可用时不支持 fallback 候选转中心重规划、中心失效 `hold_or_revoke`，以及 coordinator 禁止把 single-winner CBBA 作为原子联盟。二级/完全分布式原子联盟形成、ACK、补位和重构仍 deferred。
- D4 模块内已闭合的 P1：连续 readiness、逐决策注册证据审计、pending/active transition timing、source/lease epoch/lease expiry strictness、D2 online truth 指标可用性门控、中心重规划请求 lifecycle 去重/硬风险绕过、plan activity/identity age 分离，以及 heartbeat/link/cue/gimbal/能力回落到 distributed 的负例；当前模块测试为 121 项通过。
- 剩余跨模块 P1（未关闭）：main 必须复用同一个 adapter 实例并逐帧传入 D5 stable/not-registered、D3 新 plan source/version/lease；D3 生成有效新计划后回填 active，D7 同时检查 sustained readiness 与 current binding。2026-07-11 三组 smoke 只证明保守门控和负例动作正确，尚未提供持续同帧全覆盖、持续 `takeover_ready`、pending -> active 和 executable secondary plan 正例。仍需真实 AirSim 正向 sustained full-view、多 seed coverage-cell 聚合、网络分区/恢复、误降级成对标定、D5 peer evidence 和恢复双轨统计；不得降低现有门限制造接管成功样本。
- 后置 optional 对照：独立 single-round auction baseline、MIT/CA-CBBA/CBBA-Python adapter 和 Contract Net 均不是当前保底主线；完全无中心默认仍使用轻量 CBBA。
