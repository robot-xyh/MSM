# D4 实现差距审计：分布式协同与降级接管

**审计范围**：本文件只审计 D4 分布式协同与降级接管模块，对照 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、以及 `research_modules/d4_distributed_fallback/` 当前代码、README、PLAN、文档和测试。
**修改边界**：本次只更新 D4 GAP 审计结论；不修改 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`，也不修改 D1/D2/D3/D5/D6/D7 或 runtime 代码。
**安全边界**：结论仅用于离线科研仿真、接口补齐、AirSim ComputerVision dry-run/stress 规划和后续工程排期；不涉及真实通信链路、飞控、硬件、火控、毁伤、自动处置或授权绕过。

## 总体结论

D4 当前已经形成可测试的离线降级骨架，且与主 GAP 的 P1 状态基本一致：模块内已具备 `C2Health`、被动降级、主动降级仲裁、二级节点摘要、二级节点 lifecycle、通信 freshness、D1/D2/D3/D5 evidence adapter、D5 distributed visual evidence 到 CBBA 的风险加权、D6-compatible event metadata、轻量 CBBA、中心恢复合并和按输入列表长度运行的仿真入口。

仍需明确的是：这些能力主要是**摘要级、离线、模块内基线**。D4 还没有接入真实 main runtime bus，没有在真实 AirSim episode 中持续维护中心/二级/拦截机链路日志，也没有引入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。`request_center_replan` 只是 D4 输出动作，不等于 D3 已被自动调用；`degrade_to_secondary` 是二级接管/重分配触发语义，不等于完整二级局部计划发布已经闭环。完全无中心模式现在使用 D5 视觉证据调节轻量 CBBA 出价，不构造虚拟中心 Hungarian，不改写 `global_track_id`。

## 完全无中心模式边界

完全无中心只在中心不可用且二级节点不可用、不可达或不覆盖当前区域时作为保底路径。当前实现使用本地轻量 `CBBANegotiator`，把 D5 distributed visual evidence 作为 CBBA 风险/代价修正项：视觉支持资源获得正向加权，`hold`、friend conflict、stale/missing/conflicting `global_track_id` 阻止可执行 bid，duplicate terminal lock 写入 `assignment_audit` 并惩罚相关资源。

D4 不构造“虚拟中心”，不在 no-center 路径临时调用 Hungarian/Min Cost Flow 伪装中心化最优，也不创建、改写或本地重绑定 `global_track_id`。D3 的中心化 cost matrix 只能作为后续离线 gap benchmark 输入，不能替代 D4 的完全无中心 CBBA 保底。

## 已实现

| 能力 | 当前实现状态 | 关键证据 |
|---|---|---|
| `C2Health` 枚举和状态迁移 | 已实现 `normal/degraded/suspect/failed`，覆盖 heartbeat warning/stale/failure、peer quorum、digest conflict、center epoch stale；恢复 heartbeat/digest 后先进入 `suspect`，不能直接回 normal | `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`；`coordinator.py`；`tests/test_health.py` |
| 被动降级入口 | 已实现中心 failed 后才运行 `plan_degraded()`；可选二级/备份/代表节点 leader；无 leader 或 CBBA 不收敛时不发布有效 assignments | `coordinator.py`；`tests/test_coordinator.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| 二级系留/高空节点模型 | 已实现 `NodeRole.SECONDARY_RECON`、`GROUND_BACKUP`、`coordinator_only`、`coverage_cell`、`takeover_priority`、`lease_epoch`、heartbeat 字段和 leader 排序 | `models.py`；`coordinator.py`；`README.md`；`PLAN.md` |
| 主动降级仲裁 | 已实现规则版 `ActiveDegradationArbiter`，可输出 `continue_center`、`request_center_replan`、`request_secondary_assist`、`degrade_to_secondary`、`degrade_to_distributed`、`hold_for_review` | `active_degradation.py`；`tests/test_active_degradation.py` |
| D1/D2/D3/D5 evidence adapter | D4 侧已实现 `D4ArbitrationAdapter`，用 duck typing/dict 读取 D1 covariance/age、D2 ambiguity/IDSW/continuity、D3 plan/version/freshness/cost margin、D5 terminal/cross-view/friend-conflict 摘要 | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 友方/重复锁定保守处理 | 已实现 `friend_conflict` 强制 `hold_for_review`；`duplicate_terminal_lock` 和 cross-view 高风险不视为一致锁定 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| D5 分布式视觉证据接入 CBBA | 已实现 `DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()`、`merge_distributed_visual_evidence_into_tracks()`；轻量 CBBA 会优先视觉支持资源，阻止 `hold`、友方冲突、过期/缺失/冲突 `global_track_id` 的可执行 bid | `models.py`；`adapter.py`；`cbba.py`；`tests/test_arbitration_adapter.py`；`tests/test_cbba.py` |
| 完全无中心 CBBA 风险加权 | 已实现 visual support 正向加权、`hypothesis_only` 弱加权、ambiguous/duplicate/local conflict 风险惩罚、single-winner 防重复 owner；没有虚拟中心 Hungarian fallback | `cbba.py`；`tests/test_cbba.py` |
| `assignment_audit` | 已实现每个带视觉证据任务的 owner、support/hold/ambiguous/duplicate resource、confidence/ambiguity、hypothesis、stale/missing/global/local conflict、risk reasons 审计 | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| 二级节点 lifecycle 和链路 freshness | 已实现 `SecondaryNodeLifecycleSummary`、`CommunicationSummary`、video cue freshness、link stale、heartbeat stale 判断；传入通信摘要时二级节点必须有新鲜链路才可被选为辅助/接管节点 | `models.py`；`active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py` |
| 主动降级防抖/迟滞 | 已实现 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、`release_consecutive_consistent_frames`；测试覆盖窗口化升级和释放条件 | `active_degradation.py`；`tests/test_active_degradation.py` |
| D7 二级接管门控辅助 | 已实现 `build_d7_secondary_handoff()`，`degrade_to_secondary` 阶段 1 不放行 visual PNG，阶段 2 必须有新 plan id/version | `active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| D6 event metadata | 已实现 `D4DecisionRecord.to_event_record_kwargs()`，metadata 含 `d4_action`、`degradation_mode`、`selected_coordinator`、`coverage_cell`、trigger/decision timestamp、review label、secondary lifecycle 等字段 | `adapter.py`；`tests/test_arbitration_adapter.py` |
| 简化分布式 CBBA | 已实现本地 `CBBANegotiator`、winner/bid 扩散、确定性 tie-break、bundle release/rebuild、packet loss/delay 内存网络、收敛/冲突/消息统计 | `cbba.py`；`network.py`；`tests/test_cbba.py`；`tests/test_coordinator.py` |
| 中心恢复合并基础版 | 已实现 `merge_recovery()`，比较 center/fallback assignments；冲突或 review 未清空时保持 degraded，只有 clean merge 且 `human_accept=True` 才 normal | `coordinator.py`；`tests/test_coordinator.py` |
| N 规模输入 | 仿真和 CBBA 按 `ResourceSummary[]`、`TrackSummary[]`、`node_ids` 长度运行；`--drone-count` 只是输入规模，2v2/5v5 仅作为 baseline 名称 | `simulation.py`；`scripts/run_failover_simulation.py`；`tests/test_simulation.py` |

## 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| 完整 `C2Health` 审计 | 有 heartbeat、digest、epoch、peer vote 和 transition log | 未持久比较完整 center track digest、assignment digest、terminal lock log、communication log | main 需要生成并持久化中心/peer 双轨日志，D6 需要消费状态迁移和 merge outcome |
| 被动降级二级接管 | 中心 failed 后可选二级/备份节点；二级不可用时落到 cluster representative/CBBA；`coordination_mode` 写入 `CBBAResult.final_views` | 二级节点没有真实区域 TrackSummary 缓存、局部 plan 发布器或持续 heartbeat 维护；`run_failover_simulation()` 顶层 metrics 尚未透传 `coordination_mode` | main/AirSim episode 需要维护 `Secondary_Recon_*` heartbeat、coverage、lease、视频/检测 cue 和链路事件 |
| main runtime bus 真实 episode 接线 | D4 adapter 可消费对象/dict 摘要，并返回 `D4DecisionRecord` 与 D6 event kwargs | main/AirSim runtime 还未证明每个真实 episode 都统一调用 D4 adapter、持续写入 D4 event、持续维护二级节点链路和 D5 peer evidence | main 需要把真实 D1/D2/D3/D5 episode 数据、LinkRecord-like 通信记录、batch seed 和 event sink 统一送入 `D4ArbitrationAdapter.evaluate()` |
| D3 `request_center_replan` 自动调用 | D4 可在 D3 stale/non-current/cost margin 低且 D5 仍一致时输出 `request_center_replan` | D4 不会直接调用 D3 planner，也不会写入 main bus 或生成新版 `AssignmentPlan` | main 需要监听 D4 action 并触发 D3 生成新版本 `AssignmentPlan`，同时把新 plan id/version 回传给后续门控 |
| secondary takeover plan version 闭环 | `degrade_to_secondary`、lifecycle、D7 两阶段 handoff 已有 | 二级新 plan 生成、plan owner、D3 版本化封装、D7 实际控制状态机接线不在 D4 内闭环 | main/D3/D7 需要接收 D4 决策并发布新版本计划，再把新 plan id/version 返给 D7 gate 和恢复合并日志 |
| D1/D2/D3/D5 evidence adapter | D4 侧 adapter 可消费对象/dict 摘要，不依赖其他模块内部类型 | integrated_simulation/AirSim runtime 是否统一调用 adapter 仍属 main 侧工作；当前仍可能存在手工 summary 构造路径 | main 需要把真实 D1/D2/D3/D5 episode 数据统一送入 `D4ArbitrationAdapter.evaluate()` |
| D6 metadata | D4 已能产出 D6 `EventRecord` kwargs | episode-level 聚合、主动/被动降级次数、二级接管率、分布式冲突率由 D6/main 负责 | main 要把 `record.to_event_record_kwargs()` 写入 D6 collector，并保留 batch seed 维度 |
| 中心恢复合并 | assignment-only merge 已实现 | 未比较 track version、plan digest、terminal lock、communication link、D5/D7 gate 状态 | 需要完整双轨 episode log 和恢复前后版本序列 |
| CBBA vs 中心化最优差距 | CBBA 有 completion/conflict/rounds/messages | 未和 D3 Hungarian/OR-Tools/centralized cost matrix 做同场景 gap 评估 | main/D3 需要保存中心化 cost matrix/current plan，D6 需要计算 cost gap |
| D5 distributed visual evidence 运行时接线 | D4 模块内可消费 D5 distributed association/hypothesis 的对象或 dict，并在 CBBA scoring 中使用 | main runtime bus 还未把真实 D5 多 peer 输出持续 merge 到 D4 `TrackSummary.visual_evidence` | main 需要在 episode 状态机中调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线 |
| AirSim D4/D5 stress | D4 合同测试覆盖 case_001/002/003；main 层脚本可生成 stress 分析 | D4 不直接运行 AirSim，不保证真实 episode 中已持续写入 D4 event | main 需要统一 stress 脚本和 runtime 的 D4 输入口径 |

## 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CBBA-Python / CA-CBBA 适配 | 未接入外部实现；只有本地轻量 CBBA | 外部项目的数据模型、依赖、许可证、异步通信语义和本项目 summary bus 不一致；当前 P1 优先轻量可复现 | 许可证/版本评估、adapter、同场景 benchmark、收敛/通信开销报告 | P2 |
| 独立 auction baseline | 未单独实现 | 当前 `CBBANegotiator` 已覆盖 winner/bid 思想，并已接入 D5 visual evidence，但不是 single-round auction | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P1 |
| Contract Net 协议 | 未实现 manager/contractor announce-bid-award 状态机 | 不是 D4 最小闭环必需；二级节点 healthy 时也仍需和 D3 plan version 对齐 | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现真实 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是离线摘要和内存网络，不拥有 runtime 通信层 | main/runtime 生成 `LinkRecord`/video metadata；D5/D1 消费图像/检测 cue | P2/P3 |
| 二级节点真实图像/检测 cue adapter | D4 只消费/记录 cue freshness，不处理图像或 bbox 几何 | 像素配准、相机标定和 local visual track 属于 D5/main | AirSim detection schema、camera calibration、二级节点视角日志、D5 cue schema | P1 |
| OpenDroneID/MAVLink signing/DDS Security/AprilTag | D4 不实现 | 这些是身份/协议证据源，D4 只消费 D5 汇总后的 `friend_conflict`、auth/duplicate/cross-view 风险 | D5/main 提供身份摘要，不让 D4 直接判定身份 | P2/P3 |
| D4 直接写 shared bus | 未实现 | D4 遵守模块边界，只返回 record/kwargs，不发布全局事件 | main 统一调用 adapter 并写 D6 collector | P1 main |
| D4 直接生成新 `AssignmentPlan` | 未实现完整系统级封装 | 中心化计划属于 D3/main；D4 降级 CBBA 只是保底 continuity assignment | D3 plan schema、版本策略、secondary takeover 后的 plan owner 规则 | P1 main/D3 |
| 大规模 SCRIMMAGE 或替代仿真 | 未实现 | 当前目标仍是 AirSim CV 和本地 point-mass/内存仿真 | 完成 5v5 stress 后再评估场景导出、ID 映射和通信退化模型 | P3 |

## 未实现原因汇总

1. **模块边界**：D4 只负责降级仲裁、摘要模型、保底协商和事件记录。main 才拥有 runtime bus、AirSim episode、D6 collector 和跨模块状态机。
2. **轻量可复现优先**：当前默认测试不能依赖 AirSim 服务、ROS、真实通信、GPU 或外部 CBBA 工程；因此保留本地 NumPy/内存网络实现。
3. **真实 episode 数据不足**：主动降级阈值、dwell/release、secondary freshness 和 false degradation rate 需要多 seed 5v5 CV stress 才能校准。
4. **外部开源适配成本**：MIT/CA-CBBA、auction、contract-net 要求额外协议状态、消息模型、许可证审查和同场景 benchmark，直接替换主线会增加不确定性。
5. **安全/身份边界**：D4 不应直接处理身份认证、图像语义、飞控动作或授权状态，只能消费 D5/main 的保守摘要。

## 缺少条件

- main 在同一 episode 中持续提供 D1 `TrackUncertaintySummary`、D2 `AssociationRiskSummary`、D3 `AssignmentValiditySummary`、D5 `TerminalAssociationSummary` 或等价对象/dict。
- main/runtime 统一调用 `D4ArbitrationAdapter.evaluate()`，不再分散手工构造 D4 summary。
- D6 collector 接收 `D4DecisionRecord.to_event_record_kwargs()`，并按 active/passive、secondary/distributed、coverage_cell、batch seed 聚合指标。
- AirSim 5v5 stress 维护二级节点 heartbeat、lease、coverage、video cue freshness、link stale 和 secondary takeover lifecycle。
- D3 在收到 `request_center_replan` 或二级 takeover 后能发布新版本 `AssignmentPlan`，并把 plan id/version 回传给 D7 gate。
- 中心恢复需要完整双轨日志：track digest、assignment digest、terminal lock、communication link、plan version、降级期间 fallback assignments。
- 做 MIT/CA-CBBA/auction/contract-net 前，需要同一任务集 benchmark、许可证/依赖审查、adapter 和 D6 cost/communication gap 报告。

## P1/P2 下一步

1. **P1 main 接线**：main/integrated runtime 调用 `D4ArbitrationAdapter.evaluate()`，把 D1/D2/D3/D5 摘要和 LinkRecord-like 通信记录送入 D4，并写入 D6 `EventRecord`。
2. **P1 AirSim stress 统一口径**：将 D4/D5 stress 脚本和真实 episode 的 D4 输入口径统一到 adapter，保证 case_001/002/003 的 D4 decision 字段与 D6 聚合一致，并在完全无中心 case 中把 D5 distributed visual evidence merge 到 D4 `TrackSummary.visual_evidence`。
3. **P1 二级接管闭环**：在 main/D3 中定义 secondary takeover 后的新 plan owner、plan id/version、D7 two-stage handoff 和恢复合并规则。
4. **P1 CBBA gap benchmark**：保存 D3 中心化 cost matrix/current plan，计算 lightweight CBBA 与中心化 Hungarian/Min Cost Flow 的 cost/completion/conflict gap。
5. **P1/P2 独立 auction baseline**：先实现最小 single-round auction baseline，用同一 summary/task/resource 输入与 CBBA 对照。
6. **P2 MIT/CA-CBBA adapter**：完成许可证和依赖审查后，以 optional benchmark 接入，不替换默认轻量 CBBA。
7. **P2 恢复合并增强**：把 `merge_recovery()` 从 assignment-only 扩展到 track digest、terminal lock、communication link 和 plan version 的组合校验。

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
