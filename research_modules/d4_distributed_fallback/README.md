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
- 二级节点建模：支持 `NodeRole.SECONDARY_RECON`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`、`FIXED_TETHERED_SECONDARY` 或 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；二级节点默认 `coordinator_only`，只做协调和侦察证据，不作为拦截执行资源。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、`heartbeat_stale`、`lease_epoch`、`lease_expires_at_s`、`lease_expired`、`coverage_cell`、`coverage_matches_requested_cell`、`video_cue_freshness_s`、`cue_freshness_s`、`cue_stale`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_full_view_rate`、`cross_view_support_count`、`stable_cross_view_registration_count`、`not_registered_count`、lifecycle 内的节点类型 `secondary_capability_class=mobile_high_recon|mobile_secondary_recon|fixed_tethered_secondary|tethered_recon`、readiness `secondary_readiness_class=not_ready|visible_only|registration_usable|takeover_ready`、`secondary_capability_inputs`、`link_stale`、`link_fresh`、`secondary_available`、`secondary_visible`、`secondary_registered`、`secondary_takeover_capable` 和 `secondary_capability_score`，供 D4 仲裁与 D6 日志审计；adapter event 顶层会把 readiness 同步为 `secondary_capability_class`。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size` 和 `risk_window_threshold`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。adapter 同时输出 hard/soft risk 拆分和 `active_degradation_false_trigger_candidate`，供 D6 统计误触发。
- D5 cross-view 风险：`TerminalAssociationSummary.cross_view_risk_score` 和 `duplicate_terminal_lock` 会阻止“误判为一致锁定”。
- D5 二级覆盖/转换漏斗诊断：adapter 可消费 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap` 和 `secondary_detect_to_cross_view_reject_reasons`；当二级检测可见但 cross-view/global binding/registration 未完成时，event metadata 写入 `secondary_detect_available_but_not_registered`、计数和诊断原因，但不会把该证据直接升级为 `secondary_plan_active`。
- 二级侦察校准解释口径：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不做像素投影或视觉注册。D4 在报告中区分四级 readiness：`not_ready` 表示链路/heartbeat/cue/gimbal/coverage 不足；`visible_only` 表示二级可见但未注册；`registration_usable` 表示已有稳定注册但 coverage 或 network full-view 还不足以接管；只有 event 顶层 `secondary_capability_class=takeover_ready` 才可作为二级接管依据并进入 D7 handoff。
- 完全无中心视觉证据接入：`DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()` 和 `merge_distributed_visual_evidence_into_tracks()` 可用 duck typing/dict 消费 D5 的 distributed terminal association / cross-peer hypothesis，不导入 D5 类型，也不创建或改写 `global_track_id`。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，metadata 含 `degradation_mode`、`selected_coordinator`、`coverage_cell`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp`、三值 `review_label=necessary/unnecessary/inconclusive`、`active_degradation_necessity_label`、pre/post review window、secondary takeover plan lifecycle、lease/executable/reject reason、plan activation delay、hard/soft risk、false-trigger candidate、`active_plan_owner`、二级 diagnostic 节点 heartbeat/link/cue/gimbal/coverage/capability score、readiness `secondary_capability_class`、`secondary_capability_inputs`、network coverage gap、stable/not-registered 计数、D5 二级覆盖/未配准诊断和 `secondary_detect_to_registration_gap`，并保留 `d4_degradation_mode` 兼容 D4 原始枚举。
- 二级接管 plan metadata：`SecondaryTakeoverPlanMetadata` 明确 `not_applicable`、`pending_secondary_plan`、`secondary_plan_active` 三种状态，记录当前 plan id/version、二级 plan id/version、source node、supersedes plan、lease epoch、lease expiry、epoch monotonic、executable/reject reason、恢复双轨审计和 reassignment 是否完成；过期或非单调二级 plan 只保留审计，不标记为可执行；若当前 plan owner 已是 secondary 且 current/secondary plan id/version 相同，则解释为已激活二级计划，不要求 version 再大于自身；D4 不生成完整系统级 `AssignmentPlan`。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线；D5 视觉支持会提高对应资源出价，`hold`、友方冲突、过期/缺失/冲突 `global_track_id` 会阻止可执行出价，重复锁定风险进入 `assignment_audit` 且不允许多个 owner。
- CBBA gap benchmark：`build_cbba_cost_gap_benchmark()` 使用 D3/main 提供的中心 plan 与 cost matrix，计算 D4 CBBA 相对中心 Hungarian/Min Cost Flow 基线的 cost/completion/conflict/message 差距；D4 不在 no-center 路径运行虚拟中心 Hungarian。
- D6 CBBA report metadata：`build_cbba_d6_metadata()` 将 `CBBAResult`、`coordination_mode`、`assignment_audit` 和可选 `CBBACostGapBenchmark` 归一化为多 seed 可聚合字段；`run_failover_simulation()` 顶层 metrics 透出 `d4_action`、`coordination_mode`、`selected_coordinator`、leader 和 coverage。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

## 主动降级入口

`ActiveDegradationArbiter` 接收 D1 定位不确定度、D2 关联风险、D3 分配有效性、D5 末端视觉关联摘要、`C2Health` 和二级节点健康状态，输出 `ActiveDegradationDecision`。典型策略：

- D5 与分配目标一致且风险低：`continue_center`。
- D1/D2 风险升高但 D5 仍一致：优先 `request_secondary_assist`。
- D3 分配 `is_current=False` 或 `plan_age_s` stale 属于硬风险，D5 仍一致时优先 `request_center_replan`；`d3_assignment_cost_margin_low` 属于软证据，单独出现时只继续观察或请求二级 cue，不触发每帧重规划。
- D5 多帧 `ambiguous/hold/reacquire` 但没有 observed global track mismatch、资源错配、重复锁定或友方冲突时，不视为分配失效：有二级覆盖则 `request_secondary_assist`，否则 `continue_center` 并继续观察。
- D5 长期不一致且存在 observed global track mismatch、资源错配、重复锁定、cross-view 高风险或友方冲突等硬证据时，才进入中心重规划、`degrade_to_secondary` 或 `degrade_to_distributed`。
- D5 `friend_conflict=True`：强制 `hold_for_review`；`duplicate_terminal_lock=True` 不视为一致锁定。
- 若传入通信摘要，二级节点必须有未过期的 `secondary_relay`、`video_cue` 或 `c2_direct` 链路才可作为主动辅助/接管目标。
- 若二级节点 `heartbeat_timestamp_s` 超过 `heartbeat_stale_after_s`，即使视频链路摘要新鲜，也不会被选为二级接管目标。
- 机动高空侦察节点随拦截机出动但不拦截；它用 D1/D2 `GlobalTrack` 或雷达 cue 指向目标簇，正常时给局部拦截群提供图像/cross-view 证据，中心失效或主动降级硬条件满足时才可作为二级协调节点。仅有侦察图像、云台指向正常或 coverage ratio > 0 不会自动改变 action；二级可见但未注册时 readiness 为 `visible_only`，只支持 `request_secondary_assist`/诊断；稳定注册但网络全视场或 coverage 不足时为 `registration_usable`；只有 event `secondary_capability_class=takeover_ready` 才作为接管依据并允许后续 D7 visual PNG gate 消费 active secondary plan。
- 当中心和二级节点都不可用时，D4 使用 D5 分布式视觉证据作为 CBBA 的风险/代价输入：多资源视觉支持只增加对应资源的出价，不构造“虚拟中心”，也不重新绑定 `global_track_id`。
- `--drone-count`/main runtime 的 N 只决定输入摘要数量；D4 按实际 `TrackSummary[]`、`ResourceSummary[]` 和二级节点列表长度运行，不在仲裁里固定 2v2 或 5v5。
- 2v2/5v5 AirSim ComputerVision 专项 case 只作为测试 baseline：`case_001_no_degradation` 期望 `continue_center`；`case_002_degrade_to_secondary` 期望二级节点优先；`case_003_degrade_to_distributed` 期望二级不可用/过期后才分布式。

## P0-B 状态

- 已完成：heartbeat smoothing 使用滑动窗口、miss threshold 和 `degraded/suspect/failed` dwell，短时丢包/延迟不会直接进入 `failed`。
- 已完成：secondary takeover plan 严格校验 lease expiry、plan epoch monotonic 和 executable 状态；过期或非单调替换二级 plan 被拒绝为 pending/not executable，当前 secondary-owned 同 id/version 计划可保持 `secondary_plan_active`，D7 handoff helper 必须看到 `secondary_capability_class=takeover_ready` 才放行。
- 已完成：二级能力评分区分 `not_ready`、`visible_only`、`registration_usable` 和 `takeover_ready`，并消费 coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、stable registration count、not-registered count 和 reject reason；只有 `takeover_ready` 会成为接管依据。
- 已完成：主动降级继续保留 hard/soft risk、防抖和 release 条件；无冲突 `reacquire` 只请求二级 cue/继续观察，不直接接管或分布式降级；D6 metadata 可统计 false-trigger candidate。

## P1 状态

- 已完成：固定系留/机动高空二级节点分类元数据、二级节点 lifecycle summary、secondary takeover pending/active metadata、D5 二级覆盖/转换漏斗未配准诊断、heartbeat smoothing、lease strictness、secondary capability score/readiness class、主动降级 dwell/release/window 防抖配置、主动降级硬/软风险分层、false-trigger metadata、`necessary/unnecessary/inconclusive` review label 口径、pre/post review window、plan activation delay、secondary takeover necessity/success 统计 metadata、D6-compatible decision event metadata、D6-compatible CBBA report metadata、D5 distributed visual evidence -> 完全无中心 CBBA 风险加权、CBBA vs D3 中心化 cost gap benchmark helper、对应单元测试。
- 已完成的 main/runtime P1 基线：episode bus 已接入 D4 adapter event，`request_center_replan` 可触发 D3 new plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过；main runtime 已新增 P1 D4/D5 calibration sweep，用于按高度、FOV、二级节点数量和 standoff 组合批量生成 stress episode；sweep 结束后会自动调用 D6 标准 AirSim calibration report bundle，输出 records/summary/report 口径。该项为 main-owned 集成，修复后口径保持为 main/D3/D7 消费 owner/version，D4 仍只输出仲裁/metadata，不生成系统级 `AssignmentPlan`。
- 最新 AirSim/P1 校准证据：`p1_d4d5_mobile_recon_20260708_055948*` 的 3 seeds 已验证 mobile high recon 三类 D4 action、radar cue 和 gimbal pointing 正常，但二级网络同帧全覆盖仍为 0.0，联合覆盖约 0.65-0.69，降级 case 仍是二级可见但未注册；`p1_d4d5_registration_calibration_runtime_v2_20260708*` 的 D6 bundle 在单 seed、200 m、FOV 110、1920x1080、3 个机动高空二级节点下给出 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case not-registered 35/35、平均 full-view 0.048 和平均 coverage 0.771。该结果说明 D4 字段能消费稳定注册和未注册诊断，但 D4 不直接消费/计算 projection 或 geometry gate，且该批次还不是多 seed 闭合标定。
- 保持不变：轻量 CBBA 仍是完全无中心保底基线；未接入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。
- 剩余 P1：使用 main runtime P1 sweep 和 D6 bundle 持续校准真实 AirSim/Blocks D4/D5 stress 多 seed 结果，重点是机动高空侦察节点 coverage/freshness/plan activation、heartbeat/link/cue freshness、gimbal pointing、coverage ratio、stable registration 稳定性、not-registered 下降趋势、D5 peer evidence 合流、人工/离线 review label 填充、二级接管必要性、active degradation precision 和 D6 长期聚合。当前 D4 侧字段已经足够表达 `visible_only`、`registration_usable` 和 `takeover_ready` readiness；二级覆盖、注册和接管必要性仍是真实多 seed 标定项，剩余工作不是 D4 视觉注册实现。
- 后置 optional 对照：独立 single-round auction baseline、MIT/CA-CBBA/CBBA-Python adapter 和 Contract Net 均不是当前保底主线；完全无中心默认仍使用轻量 CBBA。
