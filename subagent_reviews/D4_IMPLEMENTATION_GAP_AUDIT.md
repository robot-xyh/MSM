# D4 实现差距审计：分布式协同与降级接管

**审计范围**：本文件只审计 D4 分布式协同与降级接管模块，对照 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、以及 `research_modules/d4_distributed_fallback/` 当前代码、README、PLAN、文档和测试。
**修改边界**：本次只更新 D4 GAP 审计结论；不修改 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`，也不修改 D1/D2/D3/D5/D6/D7 或 runtime 代码。
**安全边界**：结论仅用于离线科研仿真、接口补齐、AirSim ComputerVision dry-run/stress 规划和后续工程排期；不涉及真实通信链路、飞控、硬件、火控、毁伤、自动处置或授权绕过。

## 总体结论

D4 当前已经形成可测试的降级骨架，且与主 GAP 的 P1 状态基本一致：模块内已具备 `C2Health`、被动降级、主动降级仲裁、固定系留/机动高空二级节点摘要、二级节点 lifecycle、secondary takeover plan lifecycle metadata、通信 freshness、D1/D2/D3/D5 evidence adapter、主动降级 `necessary/unnecessary/inconclusive` review label、pre/post review window、plan activation delay、二级接管必要性/成功统计 metadata、D5 distributed visual evidence 到 CBBA 的风险加权、CBBA vs 中心化 cost gap benchmark helper、CBBA D6 report metadata、D6-compatible event metadata、轻量 CBBA、中心恢复合并和按输入列表长度运行的仿真入口。

仍需明确的是：D4 本体只输出仲裁结果，不直接控制 D3/D7。2026-07-08 main runtime bus 已经接入 `D4ArbitrationAdapter.evaluate()`，能在收到 `request_center_replan` 后触发下一轮 D3 plan version，把 D4 event 写入 D6 collector，并已把 secondary takeover owner/version 回灌到 D3/D7；controlled 2v2 secondary visual PNG 回归已通过。main runtime 已新增 P1 D4/D5 calibration sweep，可批量改变二级节点高度、FOV、数量和 standoff，且 sweep 结束后自动生成 D6 标准 AirSim calibration report bundle。D4 仍没有真实通信/视频链路，也没有引入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。`degrade_to_secondary` 是二级接管/重分配触发语义，系统级 plan 发布、owner/version 消费和 D7 gate 由 main/D3/D7 负责；D4 只输出 pending/active metadata。完全无中心模式现在使用 D5 视觉证据调节轻量 CBBA 出价，不构造虚拟中心 Hungarian，不改写 `global_track_id`。

本轮 P0/P1 复核：无 P0 blocker。P0-B 已在 D4 模块内闭合到单元测试层；2026-07-09 已补齐 heartbeat sliding window/miss threshold/dwell，单次 heartbeat 延迟不会直接 failed；secondary takeover plan 新增 lease expiry、epoch monotonic、executable/reject reason 和恢复双轨审计字段，过期或非单调替换二级 plan 不可执行，当前 plan owner 已是 secondary 且 current/secondary plan id/version 相同时可保持 `secondary_plan_active`；secondary capability score 区分 visible、registered、takeover_capable，并消费 coverage、heartbeat/link/cue freshness、gimbal、stable registration/not-registered/reject reason；主动降级继续保留硬/软风险分层、dwell/release/window 防抖和 false-trigger metadata，避免 `d3_assignment_cost_margin_low`、D5 低置信度、D5 持续无冲突 `ambiguous/reacquire` 等软证据造成名义场景每帧中心重规划或分布式降级。D4 现在区分“末端暂时看不清/重捕获”和“末端观测与分配冲突”：前者继续中心或请求二级 cue，后者才进入中心重规划、二级接管或分布式保底。2026-07-08 已补齐机动高空侦察节点元数据：`role/capability_class=mobile_high_recon/mobile_secondary_recon` 会进入二级候选和 lifecycle/D6 evidence，并与 `fixed_tethered_secondary/tethered_recon` 区分；但侦察图像、cue freshness、云台指向或 coverage ratio 本身不触发接管。D4 record 中 secondary takeover `pending_secondary_plan`/`secondary_plan_active` metadata、三值 review label、pre/post window、plan activation delay、二级接管必要性/成功统计字段、D5 distributed evidence 到 CBBA 风险加权、CBBA cost gap helper、CBBA D6 report metadata 和 D6 event metadata 均已补齐。

最新 main 测试上下文来自 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 和后续 P1 D4/D5 calibration sweep：AirSim 链路、云台 cue 和 D4 三类动作已经跑通。D4 主动作符合预期：`continue_center`、`degrade_to_secondary`、`degrade_to_distributed` 分别对应三类 case。机动二级侦察链路侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。3-seed mobile recon 批次仍显示二级网络同帧全覆盖为 0.0，联合覆盖约 0.65-0.69，主要断点是 `not_all_targets_visible` / `network_union_incomplete`；`p1_d4d5_registration_calibration_runtime_v2_20260708*` 的单 seed D6 bundle 在 200 m、FOV 110、1920x1080、3 个机动高空二级节点下已输出 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case not-registered 35/35、平均 full-view 0.048 和平均 coverage 0.771。剩余 P1 应聚焦二级 coverage/heartbeat/link freshness、稳定注册多 seed 标定、not-registered 下降趋势、二级接管必要性标签填充、plan activation delay 分布、D5 peer evidence 合流和 D6 长期聚合。D4 只消费 D5/D6/main 的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不直接做视觉注册，也不直接消费/计算 projection 或 geometry gate；MIT/CA-CBBA、独立 auction baseline 和 contract-net 均后置为 optional P2 对照，不作为当前 P1 主线或完全无中心默认路径。

本轮 D4 P1 校准口径补充：D4 把二级侦察结果解释为三类互斥或可叠加状态，而不是把“检测可见”直接当成“可接管”。第一类是二级可见但未注册：`secondary_detect_available_but_not_registered=True`、`cross_view_association_count=0` 或 reject reasons 指向 global binding/registration 断点；D4 只记录诊断或请求辅助。第二类是二级网络未全覆盖：`secondary_network_joint_full_view_frame_rate < 1.0`、`secondary_network_full_view_gap > 0`、`network_union_incomplete` 或 `not_all_targets_visible`；D4 把它作为 coverage gap 和接管必要性审计输入。第三类是稳定 cross-view support 足够：D5/D6/main 已给出稳定注册计数，且二级 heartbeat/link/cue freshness 可用；registration v2 已验证该字段能落入 D6 报告，但仍需多 seed 验证稳定性和误注册风险。该类才作为 `degrade_to_secondary` 必要性和接管成功的正向证据，但系统级 plan owner/version 仍由 main/D3 回填。

## EVAL P0/P1 同步

本节仅同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中已经确认的 D4 P0/P1 条目，不改变下面“已实现/部分实现/未实现”表中已经完成的状态，也不调整 P2/P3 对照项。

### P0-B 降级层级硬化

D4 的 P0-B 硬化继续按四级层级解释，不把单个传感器或终端软证据直接提升成完全分布式降级：

1. **中心正常**：`continue_center` 是默认路径；heartbeat 短时抖动先进入 `suspect/degraded` 观察，不直接判定中心失效。
2. **主动重规划**：中心仍可用但 D1/D2/D3/D5 证据显示硬风险时，D4 只输出 `request_center_replan`，由 main/D3 发布新版本计划；主动降级防抖继续依赖 dwell/release、硬/软风险分层和三值 review label。
3. **二级节点接管**：中心失效或需要二级接管时，D4 输出 `degrade_to_secondary` 和 pending/active metadata；可接管性必须同时审计 coverage、freshness、stable cross-view registration、not-registered 断点、lease/epoch 和 source node。
4. **完全分布式降级**：只有中心不可用且二级节点不可用、不可达或覆盖不足时才进入 `degrade_to_distributed`；当前默认仍是本地轻量 CBBA 保底，不构造虚拟中心，不改写 `global_track_id`。

| EVAL P0-B 条目 | D4 当前状态 | 同步后的缺口/验收口径 |
|---|---|---|
| Heartbeat 平滑 | 已完成。`FailoverCoordinator` 新增 heartbeat sliding window、miss threshold、`degraded/suspect/failed` dwell；有 heartbeat 样本流时，短时丢包/延迟先进入 degraded/suspect，不直接 failed | `tests/test_health.py::test_heartbeat_window_suppresses_single_delayed_sample_before_failed`；真实 AirSim false failover rate 仍属于 P1 多 seed 校准 |
| Lease 严格管理 | 已完成 D4 合同层。`SecondaryTakeoverPlanMetadata` 输出 lease epoch/expiry、epoch monotonic、executable、reject reason 和 `recovery_dual_track_audit`；过期或非单调替换二级 plan 保持 pending/not executable；当前 secondary-owned 同 id/version plan 可保持 active，D7 helper 不放行未就绪计划 | `tests/test_arbitration_adapter.py::test_adapter_rejects_expired_secondary_plan_as_not_executable`；`::test_adapter_rejects_non_monotonic_secondary_plan_version`；`::test_adapter_accepts_current_active_secondary_plan_with_same_id_and_version`；系统级执行仍由 main/D3/D7 消费这些字段 |
| 二级能力评估 | 已完成 D4 合同层。`SecondaryNodeLifecycleSummary` 输出 `secondary_visible`、`secondary_registered`、`secondary_takeover_capable`、`secondary_capability_score/reasons`，接管选择要求 takeover capable；visible-but-not-registered 只可辅助/诊断，不可接管 | `tests/test_active_degradation.py::test_visible_but_not_registered_secondary_is_not_takeover_capable`；`tests/test_arbitration_adapter.py::test_adapter_reports_secondary_detect_visible_without_cross_view_registration` |
| 主动降级防抖 | 已完成 D4 合同层。保留 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、release 条件和硬/软风险分层；无冲突 reacquire 不直接降级；adapter 输出 hard/soft risk 和 `active_degradation_false_trigger_candidate` | `tests/test_active_degradation.py::test_no_conflict_reacquire_requests_secondary_cue_without_takeover`；`tests/test_arbitration_adapter.py::test_adapter_marks_unnecessary_active_degradation_as_false_trigger_candidate`；真实 false trigger rate 仍需 P1 多 seed 标定 |

### P1 边界

以下 D4 条目按 EVAL 保留为 P1 后续项。它们用于增强网络退化、选举对照和通信统计可信度，但不提升为当前 P0，也不替换现有四级降级主线。

| EVAL P1 条目 | 当前边界 | 验收口径 |
|---|---|---|
| 网络分区检测 | 当前 D4 有通信 freshness、peer quorum、digest conflict 和内存网络统计，但脑裂/分区状态仍不足；P1 只做检测和审计，不允许分区侧绕过 main/D3/D7 合同 | 网络分区注入下输出 `partition_state`、conflict count、peer view/digest 差异和恢复后的 merge audit |
| Raft/Leader 选举对照 | 当前默认是二级接管排序和轻量 CBBA，尚无成熟 Raft/leader election 对照；P1 只能作为可复现实验对照，不替代 `degrade_to_secondary`/CBBA 默认路径 | 选举日志可回放，leader change、term/epoch、timeout、conflict 与二级接管结果可被 D6 统计，且不产生执行绕过 |
| DDS QoS/通信策略 | 当前通信是仿真 summary/内存网络合同，真实 DDS/ROS2 QoS 不属于 D4 直接拥有路径；P1 先建模丢包、优先级、stale link 和消息 freshness | D6 可统计 packet loss、delay、priority、stale link、freshness age 和对 failover/CBBA 收敛的影响 |

## 完全无中心模式边界

完全无中心只在中心不可用且二级节点不可用、不可达或不覆盖当前区域时作为保底路径。当前实现使用本地轻量 `CBBANegotiator`，把 D5 distributed visual evidence 作为 CBBA 风险/代价修正项：视觉支持资源获得正向加权，`hold`、friend conflict、stale/missing/conflicting `global_track_id` 阻止可执行 bid，duplicate terminal lock 写入 `assignment_audit` 并惩罚相关资源。

D4 不构造“虚拟中心”，不在 no-center 路径临时调用 Hungarian/Min Cost Flow 伪装中心化最优，也不创建、改写或本地重绑定 `global_track_id`。D3 的中心化 cost matrix 只能作为后续离线 gap benchmark 输入，不能替代 D4 的完全无中心 CBBA 保底。

## 已实现

| 能力 | 当前实现状态 | 关键证据 |
|---|---|---|
| `C2Health` 枚举和状态迁移 | 已实现 `normal/degraded/suspect/failed`，覆盖 heartbeat warning/stale/failure、heartbeat sliding window、miss threshold、dwell、peer quorum、digest conflict、center epoch stale；恢复 heartbeat/digest 后先进入 `suspect`，不能直接回 normal | `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`；`coordinator.py`；`tests/test_health.py` |
| 被动降级入口 | 已实现中心 failed 后才运行 `plan_degraded()`；可选二级/备份/代表节点 leader；无 leader 或 CBBA 不收敛时不发布有效 assignments | `coordinator.py`；`tests/test_coordinator.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| 二级系留/高空节点模型 | 已实现 `NodeRole.SECONDARY_RECON`、`GROUND_BACKUP`、`FIXED_TETHERED_SECONDARY`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`，并支持等价 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；`coordinator_only`、`coverage_cell`、coverage ratio、`takeover_priority`、`lease_epoch`、heartbeat/cue freshness、gimbal 字段和 leader 排序均已覆盖 | `models.py`；`coordinator.py`；`active_degradation.py`；`README.md`；`PLAN.md` |
| 主动降级仲裁 | 已实现规则版 `ActiveDegradationArbiter`，可输出 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary`、`degrade_to_distributed`、`hold_for_review` | `active_degradation.py`；`tests/test_active_degradation.py` |
| D1/D2/D3/D5 evidence adapter | D4 侧已实现 `D4ArbitrationAdapter`，用 duck typing/dict 读取 D1 covariance/age、D2 ambiguity/IDSW/continuity、D3 plan/version/freshness/cost margin、D5 terminal/cross-view/friend-conflict 摘要 | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 友方/重复锁定保守处理 | 已实现 `friend_conflict` 强制 `hold_for_review`；`duplicate_terminal_lock` 和 cross-view 高风险不视为一致锁定 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| D5 二级覆盖/转换漏斗诊断 | 已实现 D5 secondary detect coverage/conversion evidence 透传，新增 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio` 和 `cross_view_support_count`；当二级覆盖可用但 cross-view association 为 0，或 D5 在 global binding/registration 断点拒绝时，D4 event metadata 写入 `secondary_detect_available_but_not_registered`、reject reasons 和 diagnostic；该诊断不直接激活 `secondary_plan_active`。D4 文档口径已明确区分二级可见未注册、二级网络未全覆盖和稳定 cross-view support 足够三类状态 | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 分布式视觉证据接入 CBBA | 已实现 `DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()`、`merge_distributed_visual_evidence_into_tracks()`；轻量 CBBA 会优先视觉支持资源，阻止 `hold`、友方冲突、过期/缺失/冲突 `global_track_id` 的可执行 bid；测试覆盖完全无中心 CBBA 使用 D5 evidence 风险加权 | `models.py`；`adapter.py`；`cbba.py`；`tests/test_arbitration_adapter.py`；`tests/test_cbba.py` |
| 完全无中心 CBBA 风险加权 | 已实现 visual support 正向加权、`hypothesis_only` 弱加权、ambiguous/duplicate/local conflict 风险惩罚、single-winner 防重复 owner；没有虚拟中心 Hungarian fallback | `cbba.py`；`tests/test_cbba.py` |
| `assignment_audit` | 已实现每个带视觉证据任务的 owner、support/hold/ambiguous/duplicate resource、confidence/ambiguity、hypothesis、stale/missing/global/local conflict、risk reasons 审计 | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| 二级节点 lifecycle 和链路 freshness | 已实现 `SecondaryNodeLifecycleSummary`、`CommunicationSummary`、video/cue freshness、gimbal pointing、coverage ratio、requested coverage match、lease expiry、fixed/mobile secondary classification、link stale/fresh、cue stale、heartbeat stale、visible/registered/takeover_capable 和 capability score；传入通信摘要时二级节点必须有新鲜链路才可被选为辅助/接管节点，接管还必须 takeover capable | `models.py`；`active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py` |
| 主动降级防抖/迟滞 | 已实现 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、`release_consecutive_consistent_frames`；2026-07-07 增加硬/软风险分层，`d3_assignment_not_current/stale` 为硬风险，`d3_assignment_cost_margin_low` 为软风险，软 margin + 早期 D5 low confidence 只观察不触发中心重规划；持续 D5 `ambiguous/reacquire` 在没有 observed global track mismatch、资源错配、重复锁定或友方冲突时不降级，只继续中心或请求二级 cue；2026-07-09 新增 hard/soft risk 和 false-trigger D6 metadata；测试覆盖窗口化升级、释放条件和软风险不过敏 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| D7 二级接管门控辅助 | 已实现 `build_d7_secondary_handoff()`，`degrade_to_secondary` 阶段 1 不放行 visual PNG，阶段 2 必须有新 plan id/version | `active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| secondary takeover plan metadata | 已实现 `SecondaryTakeoverPlanMetadata` 和 adapter event metadata，能区分 `pending_secondary_plan` 与 `secondary_plan_active`，携带 active owner、source node、当前/二级 plan id/version、lease epoch/expiry、epoch monotonic、executable/reject reason、恢复双轨审计、supersedes plan 和 reassignment complete 字段；过期二级 plan 不可执行；当前 secondary-owned 同 id/version plan 可保持 active；D4 不生成系统级 `AssignmentPlan` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 event metadata | 已实现 `D4DecisionRecord.to_event_record_kwargs()`，metadata 含 `d4_action`、`degradation_mode`、`selected_coordinator`、`coverage_cell`、trigger/decision timestamp、三值 review label、pre/post review window、secondary lifecycle、secondary diagnostic、secondary takeover plan lifecycle、lease/executable/reject reason、hard/soft risk、false-trigger candidate、plan activation delay、takeover necessity/success、D5 secondary coverage/conversion evidence 和未配准诊断等字段 | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 CBBA report metadata | 已实现 `build_cbba_d6_metadata()`，metadata 含 `coordination_mode`、`selected_coordinator`、leader、coverage、CBBA completion/conflict/round/message、`assignment_audit` 和 cost gap 扁平字段；`run_failover_simulation()` 顶层 metrics 已透出 secondary/distributed 分组字段 | `cbba.py`；`simulation.py`；`tests/test_cbba.py`；`tests/test_simulation.py` |
| 简化分布式 CBBA | 已实现本地 `CBBANegotiator`、winner/bid 扩散、确定性 tie-break、bundle release/rebuild、packet loss/delay 内存网络、收敛/冲突/消息统计 | `cbba.py`；`network.py`；`tests/test_cbba.py`；`tests/test_coordinator.py` |
| CBBA vs 中心化 cost gap helper | 已实现 `CBBACostGapBenchmark` 和 `build_cbba_cost_gap_benchmark()`，用 D3/main 提供的中心 plan 与 cost matrix 计算 CBBA cost/completion/conflict/message gap；不接入外部 CBBA，也不在 no-center 路径运行 Hungarian | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| main/runtime secondary owner/version 消费 | main 已接入 D4 event、`request_center_replan -> D3 new version`、secondary takeover owner/version 和 D7 owner gate；controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已能生成多组合 stress episode，D6 标准 AirSim calibration report bundle 已自动生成。该项是 main-owned 集成证据，D4 仍只输出仲裁/metadata | `research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_main_episode_bus_marks_secondary_takeover_plan_for_d7`；`::test_controlled_2v2_active_degradation_secondary_plan_visual_png` |
| 中心恢复合并基础版 | 已实现 `merge_recovery()`，比较 center/fallback assignments；冲突或 review 未清空时保持 degraded，只有 clean merge 且 `human_accept=True` 才 normal | `coordinator.py`；`tests/test_coordinator.py` |
| N 规模输入 | 仿真和 CBBA 按 `ResourceSummary[]`、`TrackSummary[]`、`node_ids` 长度运行；`--drone-count` 只是输入规模，2v2/5v5 仅作为 baseline 名称 | `simulation.py`；`scripts/run_failover_simulation.py`；`tests/test_simulation.py` |

## 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| 完整 `C2Health` 审计 | 有 heartbeat、digest、epoch、peer vote 和 transition log | 未持久比较完整 center track digest、assignment digest、terminal lock log、communication log | main 需要生成并持久化中心/peer 双轨日志，D6 需要消费状态迁移和 merge outcome |
| 被动降级二级接管 | 中心 failed 后可选固定系留/机动高空二级/备份节点；二级不可用时落到 cluster representative/CBBA；`coordination_mode`、leader capability 和 secondary capability 写入 `CBBAResult.final_views`，并由 `build_cbba_d6_metadata()`/`run_failover_simulation()` 透传到报告字段 | 二级节点没有真实区域 TrackSummary 缓存、局部 plan 发布器或持续 heartbeat 维护 | main/AirSim episode 需要维护 `Secondary_Recon_*`/mobile recon heartbeat、coverage ratio、lease、gimbal、视频/检测 cue 和链路事件 |
| main runtime bus 真实 episode 接线 | D4 adapter 可消费对象/dict 摘要，并返回 `D4DecisionRecord` 与 D6 event kwargs；main episode bus 已持续调用 D4 adapter、写入 D4 event，并保留 D1/D2/D3/D5 摘要；P1 D4/D5 calibration sweep 已接入，D6 标准 report bundle 已自动生成；2026-07-08 mobile recon stress 的 3 seeds 均 connected=True，9 个 episode 均为 13/13 image frames，三类 D4 action 与预期一致；registration calibration v2 单 seed 已输出 stable registration、not-registered、coverage/full-view 和上游 projection/geometry gate 统计；D4 record 已输出三值 review label、pre/post window 和 secondary diagnostic 字段 | 仍需真实 Blocks 多 seed 校准二级 coverage/heartbeat/link freshness、人工/离线 review label 填充、二级接管必要性和 D5 peer evidence 分布 | main 需要继续用同一 adapter schema 形成 D6 多 seed 统计 |
| D3 `request_center_replan` 自动调用 | main 已监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新版本 `AssignmentPlan`，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；D4 已避免软 cost margin、低终端置信度和无冲突持续 reacquire 每帧触发 replan | 真实多 seed 中的触发阈值、dwell/release 和 review label 还未标定 | main/D3 需要保持 version/supersedes/stale rejection，并用多 seed 统计验证 |
| secondary takeover plan version 闭环 | `degrade_to_secondary`、lifecycle、D7 两阶段 handoff、D4 record pending/active metadata 已有；固定系留/机动高空二级均可作为 source node，`mobile_high_recon` 已作为二级候选能力进入 D4；D4 record 已输出 plan activation delay/pending duration 与 takeover necessity/success 字段；main/D3/D7 已完成 secondary owner/version P1 基线，并通过 controlled 2v2 secondary visual PNG 回归 | 本轮 mobile recon gimbal/cue 正常，但二级网络同帧全覆盖仍为 0.0，case mean 联合覆盖约 0.65-0.69；registration v2 单 seed 已有 stable registration 51/55/53，但 degradation case not-registered 仍为 35/35；真实 Blocks 多 seed 中的 mobile recon heartbeat、coverage ratio、gimbal、link freshness、稳定注册、接管必要性标签和恢复合并窗口还未标定 | main/D3/D7 需要继续把二级新 plan id/version、source node 和恢复后双轨校验写入同一 episode log |
| D1/D2/D3/D5 evidence adapter | D4 侧 adapter 可消费对象/dict 摘要，不依赖其他模块内部类型；main/runtime P1 基线已把 episode 摘要送入 adapter | 真实多 seed 的 D1/D2/D3/D5 字段分布、缺测路径和 D5 peer evidence 合流仍需校准 | main 需要继续保持真实 episode 数据统一送入 `D4ArbitrationAdapter.evaluate()` |
| D6 metadata | D4 已能产出 D6 `EventRecord` kwargs，含 active degradation precision 所需三值 label 和 review window；main/runtime P1 基线已写入 D6 collector，P1 sweep 已自动生成 D6 AirSim calibration records/summary/report bundle | episode-level 长期聚合、主动/被动降级次数、二级接管率、分布式冲突率和人工/离线 review label 分布仍需多 seed 报告固化 | main/D6 保留 batch seed 维度并统一聚合字段 |
| 中心恢复合并 | assignment-only merge 已实现 | 未比较 track version、plan digest、terminal lock、communication link、D5/D7 gate 状态 | 需要完整双轨 episode log 和恢复前后版本序列 |
| CBBA vs 中心化最优差距 | D4 已有单场景 helper、benchmark 字段和 `build_cbba_d6_metadata()`，可比较 D4 CBBA 与 D3/main 提供的中心 plan/cost matrix 并输出多 seed 报告字段 | 真实 episode 还未持续保存 D3 cost matrix/current plan，D6 还未做多 seed 聚合 | main/D3 需要保存中心化 cost matrix/current plan，D6 需要聚合 cost gap |
| D5 distributed visual evidence 运行时接线 | D4 模块内可消费 D5 distributed association/hypothesis 的对象或 dict，并在 CBBA scoring 中使用 | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重还未标定 | main 需要在 episode 状态机中持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线并形成 D6 统计 |
| AirSim D4/D5 stress | D4 合同测试覆盖 case_001/002/003；main 层脚本和 runtime 已有基线 stress/controlled regression 接线；D4 事件字段已能承载 coverage、freshness、stable cross-view registration、not-registered 和 review label | D4 不直接运行 AirSim；真实 Blocks 多 seed 的阈值、freshness、false degradation rate、active degradation precision 和二级接管必要性标签尚未校准 | main 需要用统一 D4 输入口径跑多 seed 并输出 D6 报告 |

## 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CBBA-Python / CA-CBBA 适配 | 未接入外部实现；只有本地轻量 CBBA | 外部项目的数据模型、依赖、许可证、异步通信语义和本项目 summary bus 不一致；当前 P1 优先轻量可复现 | 许可证/版本评估、adapter、同场景 benchmark、收敛/通信开销报告 | P2 |
| 独立 auction baseline | 未单独实现，后置为可选对照基线 | 当前 `CBBANegotiator` 已覆盖 winner/bid 思想，并已接入 D5 visual evidence，但不是 single-round auction；当前 P1 主线先做 runtime adapter 接线和 CBBA gap benchmark | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P2 后置 |
| Contract Net 协议 | 未实现 manager/contractor announce-bid-award 状态机 | 不是 D4 最小闭环必需；二级节点 healthy 时也仍需和 D3 plan version 对齐 | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现真实 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是离线摘要和内存网络，不拥有 runtime 通信层 | main/runtime 生成 `LinkRecord`/video metadata；D5/D1 消费图像/检测 cue | P2/P3 |
| 二级节点真实图像/检测 cue adapter | D4 只消费/记录 cue freshness，不处理图像或 bbox 几何 | 像素配准、相机标定和 local visual track 属于 D5/main；D4 剩余工作是 heartbeat/link freshness 的多 seed 标定 | AirSim detection schema、camera calibration、二级节点视角日志、D5 cue schema | P1 校准 / P2 适配 |
| OpenDroneID/MAVLink signing/DDS Security/AprilTag | D4 不实现 | 这些是身份/协议证据源，D4 只消费 D5 汇总后的 `friend_conflict`、auth/duplicate/cross-view 风险 | D5/main 提供身份摘要，不让 D4 直接判定身份 | P2/P3 |
| D4 直接写 shared bus | 不实现为 D4 责任；main 已统一调用 adapter 并写 D6 collector | D4 遵守模块边界，只返回 record/kwargs，不发布全局事件 | 需要 main 继续保持 episode bus 接线和多 seed 回归 | P1 main 基线已完成，后续校准 |
| D4 直接生成新 `AssignmentPlan` | 不作为 D4 能力实现；D4 只输出仲裁/metadata/CBBA 保底结果 | 中心化计划属于 D3/main；D4 降级 CBBA 只是保底 continuity assignment；main 已完成 secondary owner/version 消费基线 | D4 继续保持 `SecondaryTakeoverPlanMetadata` 输出，不生成系统级计划 | 非 D4 主线 |
| 大规模 SCRIMMAGE 或替代仿真 | 未实现 | 当前目标仍是 AirSim CV 和本地 point-mass/内存仿真 | 完成 5v5 stress 后再评估场景导出、ID 映射和通信退化模型 | P3 |

## 未实现原因汇总

1. **模块边界**：D4 只负责降级仲裁、摘要模型、保底协商和事件记录。main 才拥有 runtime bus、AirSim episode、D6 collector 和跨模块状态机。
2. **轻量可复现优先**：当前默认测试不能依赖 AirSim 服务、ROS、真实通信、GPU 或外部 CBBA 工程；因此保留本地 NumPy/内存网络实现。
3. **真实 episode 数据不足**：主动降级阈值、dwell/release、secondary freshness 和 false degradation rate 需要多 seed 5v5 CV stress 才能校准。
4. **外部开源适配成本**：MIT/CA-CBBA、auction、contract-net 要求额外协议状态、消息模型、许可证审查和同场景 benchmark，直接替换主线会增加不确定性。
5. **安全/身份边界**：D4 不应直接处理身份认证、图像语义、飞控动作或授权状态，只能消费 D5/main 的保守摘要。

## 缺少条件

- main 在同一 episode 中持续提供 D1 `TrackUncertaintySummary`、D2 `AssociationRiskSummary`、D3 `AssignmentValiditySummary`、D5 `TerminalAssociationSummary` 或等价对象/dict；P1 基线已接入，仍需多 seed 缺测路径和字段分布校准。
- main/runtime 统一调用 `D4ArbitrationAdapter.evaluate()`，不再分散手工构造 D4 summary；2026-07-08 已在 main episode bus 中形成基线接线。
- D6 collector 接收 `D4DecisionRecord.to_event_record_kwargs()` 和 `build_cbba_d6_metadata()` 输出，并按 active/passive、secondary/distributed、coverage_cell、batch seed、review label 和 review window 聚合指标；长期报告口径仍需多 seed 固化。
- AirSim stress 继续维护并校准二级节点 coverage、heartbeat、lease、video/cue freshness、link stale、稳定 cross-view registration、not-registered 趋势、二级接管必要性和 secondary takeover lifecycle；2026-07-08 mobile recon stress 已确认 gimbal/cue/capability 正常，但二级网络同帧全覆盖仍不足，主要 coverage 断点是 `not_all_targets_visible` / `network_union_incomplete`。registration v2 单 seed 已确认 stable registration 字段可落盘，但多 seed 稳定性、误注册风险和 review label 仍未闭合。D4 只消费这些摘要，不修正视觉几何注册。
- D3 在收到 `request_center_replan` 后已能由 main 触发新版本 `AssignmentPlan` 并把 plan id/version 写入后续 gate；main/D3/D7 已完成 secondary owner/version P1 基线和 controlled 2v2 secondary visual PNG 回归，D4 已输出 activation delay/pending duration 字段，仍需真实多 seed 校准 delay 分布、freshness 和恢复合并窗口。
- 中心恢复需要完整双轨日志：track digest、assignment digest、terminal lock、communication link、plan version、降级期间 fallback assignments。
- 做 MIT/CA-CBBA/contract-net 前，需要许可证/依赖审查、adapter 和 D6 cost/communication gap 报告；做独立 auction baseline 前，先完成同一任务集的 CBBA vs 中心化多 seed gap 聚合。

## P1/P2 下一步

1. **P1 AirSim D4/D5 stress 多 seed 校准**：main/integrated runtime 已调用 `D4ArbitrationAdapter.evaluate()` 并写入 D6 event；P1 D4/D5 calibration sweep 已接入，D6 标准 AirSim calibration report bundle 已自动生成；2026-07-08 mobile recon stress 已验证三类 D4 action 正常，registration v2 单 seed 已验证 stable registration/not-registered 字段，下一步是继续用真实 Blocks 多 seed 校准主动降级阈值、dwell/release、review label 填充、false degradation rate、active degradation precision、二级接管必要性和 D5 peer evidence 合流。
2. **P1 secondary coverage/heartbeat/link freshness 校准**：基于真实 episode 标定 heartbeat stale、coverage/coverage ratio、lease、video/cue freshness、gimbal pointing、secondary relay freshness、stable cross-view registration、not-registered 下降趋势、plan activation delay 分布和恢复合并窗口；当前断点是 `not_all_targets_visible` / `network_union_incomplete`，D4 剩余任务是解释这些断点对接管必要性的影响，而不是执行视觉注册。
3. **P1 CBBA gap benchmark 聚合**：D4 已有单场景 helper；main/D3 仍需保存中心化 cost matrix/current plan，D6 仍需聚合 lightweight CBBA 与中心化 Hungarian/Min Cost Flow 的 cost/completion/conflict gap。
4. **P2 optional auction baseline**：在多 seed CBBA gap benchmark 稳定后，可选实现最小 single-round auction baseline，用同一 summary/task/resource 输入与 CBBA 对照。
5. **P2 optional MIT/CA-CBBA adapter**：完成许可证和依赖审查后，以 optional benchmark 接入，不替换默认轻量 CBBA。
6. **P2 恢复合并增强**：把 `merge_recovery()` 从 assignment-only 扩展到 track digest、terminal lock、communication link 和 plan version 的组合校验。

## 关键依据路径

- `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/active_degradation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/adapter.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/coordinator.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/cbba.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/network.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/simulation.py`
- `research_modules/d4_distributed_fallback/README.md`
- `research_modules/d4_distributed_fallback/PLAN.md`
- `research_modules/d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md`
- `research_modules/d4_distributed_fallback/tests/test_health.py`
- `research_modules/d4_distributed_fallback/tests/test_coordinator.py`
- `research_modules/d4_distributed_fallback/tests/test_active_degradation.py`
- `research_modules/d4_distributed_fallback/tests/test_arbitration_adapter.py`
- `research_modules/d4_distributed_fallback/tests/test_cbba.py`
- `research_modules/d4_distributed_fallback/tests/test_airsim_phase1_dry_run_contracts.py`
- `research_modules/d4_distributed_fallback/tests/test_simulation.py`
