# D4 实现差距审计：分布式协同与降级接管

**审计范围**：本文件只审计 D4 分布式协同与降级接管模块，对照 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、以及 `research_modules/d4_distributed_fallback/` 当前代码、README、PLAN、文档和测试。
**修改边界**：本次只更新 D4 GAP 审计结论；不修改 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`，也不修改 D1/D2/D3/D5/D6/D7 或 runtime 代码。
**安全边界**：结论仅用于离线科研仿真、接口补齐、AirSim ComputerVision dry-run/stress 规划和后续工程排期；不涉及真实通信链路、飞控、硬件、火控、毁伤、自动处置或授权绕过。

## 总体结论

D4 所属 P1 合同层已闭合。最新验证中 ComputerVision 总体验收为 8/10；二级协调者 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing`，完全分布式 `INT-02` peer 以 ACK 3/3 进入 `executing`，缺 ACK 场景以 2/3 ACK 进入 `aborted` 并令 T001 三成员 `hold_for_review`。因此 secondary/distributed commit 正例和缺 ACK fail-closed 都属于已通过，不再列为当前缺口。

状态分层如下，后续审计不得合并这些口径：

| 层级 | 状态 | 审计边界 |
|---|---|---|
| P1 合同层 | **已完成** | 已关闭 secondary/peer 3/3 ACK `executing` 正例和 missing ACK 2/3 `aborted` fail-closed；不等于自主成员形成或物理执行完成 |
| P1 物理/长期标定 | **仍开放** | SimpleFlight 15 s 的 30 个 active pair 物理命中为 0；旧 epoch、过期 lease、成员不可执行、网络分区、digest conflict、成员退出/重构/恢复和误降级成对标定仍缺完整 AirSim 扰动矩阵与多 seed 统计 |
| D4 P2 optional benchmark | **本轮未完成实际外部 benchmark** | `P1_P2_VALIDATION_SUMMARY_CN.md` 的 P2 结果仅列 D2/D5/D6/D7，没有 D4；D4 现有 cost-gap helper 仅为离线单场景接口/单元测试，不是 MIT/CA-CBBA adapter 验收 |

P2 后续只允许隔离式 benchmark，不替换本地轻量 CBBA、commit lifecycle 或 ACK/lease/epoch 门控。D4 的 ComputerVision 故障注入、summary adapter、内存网络和本地轻量 CBBA属于合同验证/adapter/研究近似；默认在线路径没有被外部算法替换。

D4 当前已具备 `C2Health`、被动降级、主动降级仲裁、固定系留/机动高空二级节点摘要、二级节点 lifecycle、secondary takeover plan lifecycle metadata、通信 freshness、D1/D2/D3/D5 evidence adapter、主动降级 review label、plan activation delay、D5 distributed visual evidence 风险加权、CBBA cost gap helper、D6-compatible metadata、轻量 CBBA、中心恢复合并和按输入列表长度运行的仿真入口。

### 历史实施记录（不作为当前状态）

历史状态（2026-07-11 原子 commit 实施前）：高威胁目标要求 `k_j=3` 时，single-winner `CBBANegotiator` 不能被解释为多机联盟分配。基础 CBBA 是成熟分布式基线，但 CCBBA、consensus-based grouping 和 distributed coalition formation 的公开代码成熟度不足。当时该项作为跨 D3/D4/D6/D7/main 的 P1 合同缺口；当前原子 commit 合同已关闭，成员形成、重构、恢复和时序可达性仍开放。证据见 `D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md`。

2026-07-11 原子联盟安全语义已落地：`CoalitionSafetyEvidence` 可序列化输出 D3 schema v2 的 plan/coalition version、需求、完整性、授权成员、锁成员和冲突原因，并可选消费 `CoalitionCommitState`。冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 已实现版本/epoch 单调、成员 ACK、lease、分区和 digest 门控；全部 required ACK 且 lease 有效后才允许 secondary/distributed `atomic_coalition_formed=true`。无有效 commit 保持 `coalition_fallback_unsupported`/`hold_or_revoke`。合法联盟内多个授权资源锁同一 `global_track_id` 不再计 duplicate；联盟外/超额成员及旧 plan/coalition version fail closed。最新真实 episode 已关闭 secondary/peer commit 正例与缺 ACK 负例；reserve 激活、成员补位/缩编、完整重构/恢复矩阵仍是后续 P1。

真实 AirSim 目录 `blocks_cv_m5_n2_cooperative_live_20260711` 证明需要对“最终动作”再次门控：中心 alive/owner=center，T001 demand required/assigned 为 3/3、coalition complete、version current，但 D5 长期 reacquire 后 D4 曾输出 `degrade_to_distributed`。该结果不能解释为可执行联盟 fallback，因为现有 distributed 仍是 single-winner；修正后同类候选在中心可用时请求 D3 重规划。

2026-07-11 中心重规划请求 lifecycle 的 D4 模块缺口已闭合：公开冻结 DTO `CenterReplanStatus` 及稳定 risk-signature helper，adapter 只读消费四态请求。默认 cooldown 为 2.0 秒，以 `resolved_at` 或 pending 的 `requested_at` 为起点；窗口内新增 medium ambiguity 等非硬风险仍 suppress，严格边界到期后才重新请求。持续 `terminal_persistent_disagreement` 只负责首次请求和风险分类，不绕过 cooldown。expired、center failed 和 friend/非法重复锁/assignment-version/IDSW/coalition conflict 不受冷却。事件保留 request/status/current signature/是否恶化/是否抑制/绕过原因及 cooldown seconds/until/active。D4 的 `continue_center` 不清除 D5 不一致，D5/D7 gate 仍独立；`k>1` 原子联盟 fail closed 与 `k=1` 兼容均有回归。

2026-07-11 assignment freshness 误判缺口已闭合：稳定 plan identity 不再因 `created_at` 超过 4 秒自动 stale。adapter 优先使用 metadata 最近评估时间计算活性 `plan_age_s`，缺失字段保持原 `created_at` 回退；identity age、age reference 与 reference timestamp 保留在 assignment evidence metadata。阈值仍严格使用 `plan_age_s > stale threshold`，stale 后原 hard-risk 与 cooldown bypass 语义不变。

历史基线（2026-07-11 最终 P1 验证前）：M-to-N ComputerVision 三 seed 证据进一步确认中心重规划 lifecycle 已闭合；seeds 7/17/27 均为 replan request 6、no-change ACK 6、applied 0、expired 0，需求满足率 1.0，错误重复锁 0。T002 共识帧为 4/5/4，D7 每 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。当时二级 active plan 和完全无中心原子联盟仍列为 P1；该状态已被最新 3/3、3/3、2/3 故障注入验收取代。ComputerVision 流程成功不得表述为物理拦截完成。

仍需明确的是：D4 本体只输出仲裁结果，不直接控制 D3/D7。2026-07-08 main runtime bus 已经接入 `D4ArbitrationAdapter.evaluate()`，能在收到 `request_center_replan` 后触发下一轮 D3 plan version，把 D4 event 写入 D6 collector，并已把 secondary takeover owner/version 回灌到 D3/D7；controlled 2v2 secondary visual PNG 回归已通过。main runtime 已新增 P1 D4/D5 calibration sweep，可批量改变二级节点高度、FOV、数量和 standoff，且 sweep 结束后自动生成 D6 标准 AirSim calibration report bundle。D4 仍没有真实通信/视频链路，也没有引入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。`degrade_to_secondary` 是二级接管/重分配触发语义，系统级 plan 发布、owner/version 消费和 D7 gate 由 main/D3/D7 负责；修复后口径保持为 D4 只输出 pending/active metadata 与仲裁记录，不生成系统级 `AssignmentPlan`。完全无中心模式现在使用 D5 视觉证据调节轻量 CBBA 出价，不构造虚拟中心 Hungarian，不改写 `global_track_id`。

本轮 P0/P1 复核：无 P0 blocker。P0-B 已在 D4 模块内闭合到单元测试层；heartbeat smoothing、secondary readiness/lease/source、主动降级防抖、中心重规划 lifecycle、assignment freshness 和原子联盟 ACK/commit 合同均有回归。D4 现在区分“末端暂时看不清/重捕获”和“末端观测与分配冲突”，并要求 `k>1` fallback 具有有效 atomic commit。D4 record/D6 metadata 已增加 commit state、epoch、coordinator、required/acked/missing member、lease 和 `atomic_coalition_formed`；恢复双轨 digest 不一致只进入审计。新增 current-coalition recovery 后，旧 soft pending 只有在中心 alive、双版本 current、全部 primary consensus locked 且无硬冲突时才收敛为 no-change/continue。D2 continuous duplicate risk 与 observed duplicate count 已严格分离，避免候选/协方差重叠误报 hard duplicate。当前 D4 测试 144 项通过；D4 仍只输出仲裁和审计，main/D3 负责系统级计划和请求状态事实源，D5/D7 保持独立执行门控。

历史基线（2026-07-10，非当前状态）：`research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710/` 及其 50/200 m case 目录包含 10 seeds、3 个二级节点、FOV 110 度、1920x1080，共 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m/200 m 的 network joint full-view 均值为 0.023/0.000，coverage 均值为 0.685/0.708；projection valid 均为 1.0，cross-view association 均值为 4.6/4.0，stable registration 均值为 86.3/96.7，not-registered 均为 0。该批次表明当时注册链已显著改善但同帧全覆盖不稳定；它不否定后续 secondary 3/3 ACK `executing` 合同正例，也不能作为当前接管率。

同一历史基线中的 1300 条 secondary-case D4 决策提供了门限级证据：heartbeat/link/cue/gimbal、visible 和 registered 全部通过，capability score 无低于 0.70；1285 条的 network full-view < 0.80，因而 readiness 为 `registration_usable`，其中 600 条同时 coverage < 0.65。仅 50 m seed 2/5 的三个 frame 产生 15 条 `takeover_ready` 记录，但均为 `pending_secondary_plan`，0 条 `secondary_plan_active`、0 条 executable，随后回落 distributed。该历史数据用于冻结门限解释，不代表最新 commit 正例仍未闭合。D4 保持这些硬门限，并新增默认 3 个不同时间戳决策、至少 0.2 s、evidence gap <= 1.0 s 的持续 readiness gate；单帧和同时间戳重复判定均不能接管。

逐决策证据的 D4 输出缺口已闭合：lifecycle/event 现在同时记录 stable/not-registered value、presence、`registration_evidence_source`、streak、since/duration、sustained 和 fallback reason，明确标识 D5/resource 显式计数与 cross-view compatibility 回退。历史 1300 条 D4 input 的两个显式计数仍为 `null`，所以剩余的是 main/D5 真实接线缺口，不是 D4 字段缺口。

D4 模块内 pending/active 合同也已补齐：只有 sustained readiness 才能进入 pending；active 还要求 source 与选中二级节点一致、plan version 单调或保持同一已激活 secondary plan、plan lease epoch 不低于节点要求且 lease 未过期。原子联盟、center-replan recovery 和 D2 duplicate score/count 分离测试覆盖正常中心、secondary/distributed commit、缺 ACK、旧 epoch、过期 lease、重复/非成员 ACK、能力撤销、分区、digest 冲突、soft pending recovery、continuous risk=0.8/count=0、explicit count=1、stale visual coalition version 和 center failure；当前 D4 测试为 144 项通过。真实 AirSim 的 secondary/peer commit DTO 与 action 正负例已经接线；剩余 P1 是物理执行、coverage-cell 长期聚合、成员退出/补位/缩编/整盟重构、完整网络分区/恢复矩阵和误降级成对标定。

历史 smoke（2026-07-11、最终故障注入验证前）：`p1_runtime_truth_isolated_d4d5_smoke_20260711`（200 m、2 secondary）、`p1_runtime_truth_isolated_d4d5_50m_20260711`（50 m、2 secondary）和 `p1_runtime_truth_isolated_d4d5_secondary5_20260711`（200 m、5 secondary）中，中心保持正例均为 `continue_center`，二级不可用负例均为 `degrade_to_distributed`。三组预期二级接管正例当时同样为 `degrade_to_distributed`，其共同证据是 `secondary_network_joint_full_view_frame_rate=0.0`、readiness 非持续 `takeover_ready`。5-secondary 配置虽把 `secondary_network_mean_coverage_ratio` 提升到约 0.80，仍未形成同帧全目标联合覆盖。该历史结果说明安全回落正确并冻结 readiness 门限；二级 3/3 ACK `executing` 正例现已由后续验证关闭，但平均覆盖、累计检测或单帧可见性仍不能解释为 active secondary plan，也不得用于降低门限。

本轮 D4 P1 校准口径补充：D4 把二级侦察结果解释为四级 readiness，而不是把“检测可见”直接当成“可接管”。`not_ready` 表示 coverage、heartbeat、link、cue、lease 或 gimbal 不足；`visible_only` 表示二级可见但未注册，常见证据是 `secondary_detect_available_but_not_registered=True`、`cross_view_association_count=0`、`not_registered_count>0` 且无稳定注册，或 reject reasons 指向 global binding/registration 断点；`registration_usable` 表示已有 stable registration/cross-view support，但 `secondary_network_joint_full_view_frame_rate`、coverage 或综合 score 仍不足以接管；`takeover_ready` 才作为 `degrade_to_secondary` 接管依据。D4 event 顶层输出 readiness `secondary_capability_class`，lifecycle 保留节点类型字段并新增 `secondary_readiness_class` 与 `secondary_capability_inputs`；D7 handoff 必须看到 `secondary_capability_class=takeover_ready`。系统级 plan owner/version 仍由 main/D3 回填。

## EVAL P0/P1 同步

本节仅同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中已经确认的 D4 P0/P1 条目，不改变下面“已实现/部分实现/未实现”表中已经完成的状态，也不调整 P2/P3 对照项。当前没有新增运行级 P0 blocker；已实现的 P0 项按“保持回归”处理，若后续出现未完成 P0，只能列为 P0 backlog 并绑定明确验收口径。

### P0-B 降级层级硬化

D4 的 P0-B 硬化继续按四级层级解释，不把单个传感器或终端软证据直接提升成完全分布式降级，也不绕过 D3/D5/D7 gate：

1. **中心正常**：`continue_center` 是默认路径；heartbeat 短时抖动先进入 `suspect/degraded` 观察，不直接判定中心失效。
2. **主动重规划**：中心仍可用但 D1/D2/D3/D5 证据显示硬风险时，D4 只输出 `request_center_replan`，由 main/D3 发布新版本计划；主动降级防抖继续依赖 dwell/release、硬/软风险分层和三值 review label。
3. **二级节点接管**：中心失效或需要二级接管时，D4 输出 `degrade_to_secondary` 和 pending/active metadata；可接管性必须同时审计 coverage、freshness、stable cross-view registration、not-registered 断点、lease/epoch 和 source node。
4. **完全分布式降级**：只有中心不可用且二级节点不可用、不可达或覆盖不足时才进入 `degrade_to_distributed`；当前默认仍是本地轻量 CBBA 保底，不构造虚拟中心，不改写 `global_track_id`。

| EVAL P0-B 条目 | D4 当前状态 | 同步后的缺口/验收口径 |
|---|---|---|
| Heartbeat 平滑 | 已完成，保持回归。`FailoverCoordinator` 新增 heartbeat sliding window、miss threshold、`degraded/suspect/failed` dwell；有 heartbeat 样本流时，短时丢包/延迟先进入 degraded/suspect，不直接 failed | `tests/test_health.py::test_heartbeat_window_suppresses_single_delayed_sample_before_failed`；真实 AirSim false failover rate 仍属于 P1 多 seed 校准 |
| Lease/epoch 严格合同 | 已完成 D4 合同层，保持回归。除 expiry/version 外，现校验 plan source、required lease epoch、sustained readiness，并记录 transition/timing/fallback；过期/stale lease、错误 source、能力回落均不可执行 | `tests/test_arbitration_adapter.py::test_active_secondary_plan_rejects_stale_lease_epoch_and_wrong_source`；`::test_active_plan_rolls_back_on_expired_lease_and_capability_regression`；系统级计划仍由 main/D3/D7 负责 |
| 二级能力评估 | 已完成 D4 合同层，保持回归。瞬时四级 readiness 后增加默认 3 decisions/0.2 s 连续窗口；相同 timestamp 不累计；not-ready 边沿和回落后重新初始化 since/count。lifecycle/event 输出逐决策 registration source/presence、streak/duration/sustained/fallback；D7 helper 可显式拒绝未 sustained 的 `takeover_ready` | `tests/test_arbitration_adapter.py::test_default_readiness_window_blocks_single_frame_takeover_and_audits_evidence`；`::test_readiness_window_restarts_after_not_ready_edge_and_after_regression`；`::test_sustained_readiness_enters_pending_then_active_with_transition_timing` |
| 主动降级防抖 | 已完成 D4 合同层，保持回归。保留 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、release 条件和硬/软风险分层；无冲突 reacquire 不直接降级；adapter 输出 hard/soft risk 和 `active_degradation_false_trigger_candidate` | `tests/test_active_degradation.py::test_no_conflict_reacquire_requests_secondary_cue_without_takeover`；`tests/test_arbitration_adapter.py::test_adapter_marks_unnecessary_active_degradation_as_false_trigger_candidate`；真实 false trigger rate 仍需 P1 多 seed 标定 |

### P1 边界

以下 D4 条目按 EVAL 保留为 P1 后续项。它们用于增强网络退化、选举对照、分布式通信效率和通信统计可信度，但不提升为当前 P0，也不替换现有四级降级主线。etcd/Raft/SwarmRaft/DDS 是对照或后续工程化方向，不是当前 P0 强依赖；任何 P1 对照只能丰富 D4 record/D6 统计，不能绕过 D3 plan version、D5 身份/终端 gate 或 D7 handoff gate。D4 主链路 action 合同仍保持 `continue_center`、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`。

| EVAL P1 条目 | 当前边界 | 验收口径 |
|---|---|---|
| Raft/SwarmRaft leader election 对照 | 当前默认是二级接管排序和轻量 CBBA，尚无成熟 Raft/SwarmRaft leader election 对照；P1 只能作为可复现实验对照，不替代 `degrade_to_secondary`/CBBA 默认路径，也不要求当前集成 etcd | 选举日志可回放，leader change、term/epoch、timeout、conflict 与二级接管结果可被 D6 统计，且不产生执行绕过 |
| Event-Driven CBBA 通信优化 | 当前本地轻量 CBBA 已有 round/message/conflict 统计和内存网络 packet loss/delay，但仍按现有协商节奏运行；P1 只评估事件触发消息减少，不替换 no-center 默认保底语义 | 同一任务/资源输入下输出 baseline vs event-driven 的 message count、consensus rounds、conflict rate、completion rate 和 cost gap，且不改写 `global_track_id` 或 D3 plan owner |
| 网络分区检测与恢复韧性指标 | 当前 D4 有通信 freshness、peer quorum、digest conflict、内存网络统计和 assignment-only merge，但脑裂/分区状态、恢复审计和韧性分数仍不足；P1 只做检测、恢复审计和 D6 指标，不允许分区侧绕过 main/D3/D7 合同 | 网络分区注入下输出 `partition_state`、conflict count、peer view/digest 差异、恢复后的 merge audit 和 `resilience_score`/等价韧性指标 |
| 误降级/漏降级标定 | 已有 false-trigger metadata、三值 review label、pre/post review window 和 D6 active-degradation precision 字段；现有 60-case 正常 freshness 基线不足以形成成对故障真值 | main/D6 用同 seed 正常/故障成对场景输出 false-degradation rate、missed-degradation rate、动作混淆矩阵、dwell/release 抖动和 review label coverage；不得通过降低二级 readiness 门限改善表面接管率 |
| DDS QoS 通信策略仿真 | 当前通信是仿真 summary/内存网络合同，真实 DDS/ROS2 QoS 不属于 D4 直接拥有路径；P1 先建模丢包、优先级、stale link、message durability/reliability 和消息 freshness，不把 DDS/RTI/ROS2 生产化列为 P0 | D6 可统计 packet loss、delay、priority delivery、stale link、freshness age、QoS profile 和对 failover/CBBA 收敛的影响 |

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
| D2 online truth 隔离语义 | 已实现 `truth_metrics_available`/`continuity_available` 透传与门控；不可用的 IDSW/continuity 数值占位不产生硬风险。连续 `duplicate_track_risk >= 0.5` 输出 soft `d2_duplicate_track_risk_high`，不合成 count；只有显式 duplicate count、delta/delta sum 或 observed flag 输出 hard `d2_duplicate_track_observed` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 友方/重复锁定保守处理 | 已实现 `friend_conflict` 强制 `hold_for_review`；`duplicate_terminal_lock` 和 cross-view 高风险不视为一致锁定 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| D5 二级覆盖/转换漏斗诊断 | 已实现 D5 secondary detect coverage/conversion evidence 透传，新增 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_joint_full_view_frame_rate`、`cross_view_support_count`、`stable_cross_view_registration_count` 和 `not_registered_count`；当二级覆盖可用但 cross-view association 为 0，或 D5 在 global binding/registration 断点拒绝时，D4 event metadata 写入 `secondary_detect_available_but_not_registered`、reject reasons、计数和 diagnostic；该诊断不直接激活 `secondary_plan_active`。D4 文档口径已明确区分 `visible_only`、`registration_usable` 和 `takeover_ready` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 分布式视觉证据接入 CBBA | 已实现 `DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()`、`merge_distributed_visual_evidence_into_tracks()`；轻量 CBBA 会优先视觉支持资源，阻止 `hold`、友方冲突、过期/缺失/冲突 `global_track_id` 的可执行 bid；测试覆盖完全无中心 CBBA 使用 D5 evidence 风险加权 | `models.py`；`adapter.py`；`cbba.py`；`tests/test_arbitration_adapter.py`；`tests/test_cbba.py` |
| 完全无中心 CBBA 风险加权 | 已实现 visual support 正向加权、`hypothesis_only` 弱加权、ambiguous/duplicate/local conflict 风险惩罚、single-winner 防重复 owner；没有虚拟中心 Hungarian fallback | `cbba.py`；`tests/test_cbba.py` |
| `assignment_audit` | 已实现每个带视觉证据任务的 owner、support/hold/ambiguous/duplicate resource、confidence/ambiguity、hypothesis、stale/missing/global/local conflict、risk reasons 审计 | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| 二级节点 lifecycle 和链路 freshness | 已实现 heartbeat/lease/coverage/cue/gimbal/link、四级瞬时 readiness，并新增逐决策 stable/not-registered source/presence、连续 readiness streak/since/duration/sustained/fallback。默认要求 3 个不同 timestamp 决策和 0.2 s 驻留，单帧不接管 | `models.py`；`active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| 主动降级防抖/迟滞 | 已实现 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、`release_consecutive_consistent_frames`；2026-07-07 增加硬/软风险分层，`d3_assignment_not_current/stale` 为硬风险，`d3_assignment_cost_margin_low` 为软风险，软 margin + 早期 D5 low confidence 只观察不触发中心重规划；持续 D5 `ambiguous/reacquire` 在没有 observed global track mismatch、资源错配、重复锁定或友方冲突时不降级，只继续中心或请求二级 cue；2026-07-09 新增 hard/soft risk 和 false-trigger D6 metadata；测试覆盖窗口化升级、释放条件和软风险不过敏 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| D7 二级接管门控辅助 | 已实现 `build_d7_secondary_handoff()`；阶段 2 除新 plan id/version 和 `takeover_ready` 外，可显式要求 `secondary_readiness_sustained=True`，瞬时 readiness、过期 lease 和非当前 plan 均不放行 | `active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py::test_d7_handoff_rejects_visible_only_secondary_capability` |
| secondary takeover plan metadata | 已实现 pending/active、source match、required lease epoch、expiry、version monotonic、sustained readiness、executable/reject、previous/current transition、pending/active timing 和 fallback reason；D4 不生成系统级 `AssignmentPlan` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 event metadata | 已实现既有 D4/D6 metadata，并新增逐决策 registration source/presence、readiness streak/duration/sustained、transition、pending since、activated at、activation delay、required lease epoch、source match 和 fallback reason | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 CBBA report metadata | 已实现 `build_cbba_d6_metadata()`，metadata 含 `coordination_mode`、`selected_coordinator`、leader、coverage、CBBA completion/conflict/round/message、`assignment_audit` 和 cost gap 扁平字段；`run_failover_simulation()` 顶层 metrics 已透出 secondary/distributed 分组字段 | `cbba.py`；`simulation.py`；`tests/test_cbba.py`；`tests/test_simulation.py` |
| 简化分布式 CBBA | 已实现本地 `CBBANegotiator`、winner/bid 扩散、确定性 tie-break、bundle release/rebuild、packet loss/delay 内存网络、收敛/冲突/消息统计 | `cbba.py`；`network.py`；`tests/test_cbba.py`；`tests/test_coordinator.py` |
| CBBA vs 中心化 cost gap helper | 已实现 `CBBACostGapBenchmark` 和 `build_cbba_cost_gap_benchmark()`，用 D3/main 提供的中心 plan 与 cost matrix 计算 CBBA cost/completion/conflict/message gap；不接入外部 CBBA，也不在 no-center 路径运行 Hungarian | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| P2 隔离 coalition fault replay | 已实现 6 场景原生 replay、逐场景 round/completion/conflict/gap-or-unavailable 输出、MIT/CA-CBBA path/source capability probe 和 CLI；明确 `isolated_from_online_d4=true`、`replaces_online_d4=false`、`adds_default_dependency=false` | `p2_coalition_replay.py`；`scripts/run_p2_coalition_replay.py`；`tests/test_p2_coalition_replay.py` |
| main/runtime secondary owner/version 消费 | main 已接入 D4 event、`request_center_replan -> D3 new version`、secondary takeover owner/version 和 D7 owner gate；controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已能生成多组合 stress episode，D6 标准 AirSim calibration report bundle 已自动生成。该项是 main-owned 集成证据，D4 仍只输出仲裁/metadata | `research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_main_episode_bus_marks_secondary_takeover_plan_for_d7`；`::test_controlled_2v2_active_degradation_secondary_plan_visual_png` |
| 中心恢复合并基础版 | 已实现 `merge_recovery()`，比较 center/fallback assignments；冲突或 review 未清空时保持 degraded，只有 clean merge 且 `human_accept=True` 才 normal | `coordinator.py`；`tests/test_coordinator.py` |
| N 规模输入 | 仿真和 CBBA 按 `ResourceSummary[]`、`TrackSummary[]`、`node_ids` 长度运行；`--drone-count` 只是输入规模，2v2/5v5 仅作为 baseline 名称 | `simulation.py`；`scripts/run_failover_simulation.py`；`tests/test_simulation.py` |

## 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| 完整 `C2Health` 审计 | 有 heartbeat、digest、epoch、peer vote 和 transition log | 未持久比较完整 center track digest、assignment digest、terminal lock log、communication log | main 需要生成并持久化中心/peer 双轨日志，D6 需要消费状态迁移和 merge outcome |
| 被动降级二级接管 | 中心 failed 后可选固定系留/机动高空二级/备份节点；二级不可用时落到 cluster representative/CBBA；`coordination_mode`、leader capability 和 secondary capability 写入 `CBBAResult.final_views`，并由 `build_cbba_d6_metadata()`/`run_failover_simulation()` 透传到报告字段 | 二级节点没有真实区域 TrackSummary 缓存、局部 plan 发布器或持续 heartbeat 维护 | main/AirSim episode 需要维护 `Secondary_Recon_*`/mobile recon heartbeat、coverage ratio、lease、gimbal、视频/检测 cue 和链路事件 |
| main runtime bus 真实 episode 接线 | 已完成 D4/D5 sweep、二级与 peer commit 正例及缺 ACK fail-closed；D4 record 包含 review、readiness、commit 和 secondary diagnostic | 完整通信/heartbeat/cue、epoch/lease、成员故障、分区/digest conflict 和恢复扰动矩阵仍开放 | main 增加同 seed 成对扰动并沿用当前 schema |
| D3 `request_center_replan` 自动调用 | main 已监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新版本 `AssignmentPlan`，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；D4 已避免软 cost margin、低终端置信度和无冲突持续 reacquire 每帧触发 replan | 真实多 seed 中的触发阈值、dwell/release 和 review label 还未标定 | main/D3 需要保持 version/supersedes/stale rejection，并用多 seed 统计验证 |
| secondary takeover plan version 闭环 | D4 sustained readiness、pending/active/source/lease/timing/fallback 合同已完成；最新二级正例由 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` | 合同正例已通过；完整扰动、回落与恢复统计仍开放 | 保持正例回归，扩展 lease/分区/成员故障矩阵；不降低门限 |
| D1/D2/D3/D5 evidence adapter | D4 已逐决策记录 stable/not-registered source/presence，并保留 compatibility 来源 | 历史 AirSim input 两个显式计数仍为 null；D5 peer evidence 合流仍需校准 | main/D5 将真实逐帧 stable/not-registered 摘要送入 adapter，D6 汇总 source 分布 |
| D6 metadata | D4 已能产出 D6 `EventRecord` kwargs，含 active degradation precision 所需三值 label、`active_degradation_necessity_label`、review window、readiness class、stable/not-registered count 和 false-trigger candidate；main/runtime P1 基线已写入 D6 collector，P1 sweep 已自动生成 D6 AirSim calibration records/summary/report bundle | episode-level 长期聚合、主动/被动降级次数、二级接管率、分布式冲突率和人工/离线 review label 分布仍需多 seed 报告固化 | main/D6 保留 batch seed 维度并统一聚合字段 |
| 中心恢复合并 | assignment-only merge 已实现 | 未比较 track version、plan digest、terminal lock、communication link、D5/D7 gate 状态 | 需要完整双轨 episode log 和恢复前后版本序列 |
| CBBA vs 中心化最优差距 | D4 已有单场景 helper、benchmark 字段和 `build_cbba_d6_metadata()`，可比较 D4 CBBA 与 D3/main 提供的中心 plan/cost matrix 并输出多 seed 报告字段 | 真实 episode 还未持续保存 D3 cost matrix/current plan，D6 还未做多 seed 聚合 | main/D3 需要保存中心化 cost matrix/current plan，D6 需要聚合 cost gap |
| D5 distributed visual evidence 运行时接线 | D4 模块内可消费 D5 distributed association/hypothesis 的对象或 dict，并在 CBBA scoring 中使用 | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重还未标定 | main 需要在 episode 状态机中持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线并形成 D6 统计 |
| AirSim D4/D5 stress | 历史 sweep 与最新 commit 正负例均可审计；二级和 peer 3/3 `executing`、缺 ACK 2/3 `aborted` 已通过 | 完整扰动矩阵、成员退出/重构、误降级和恢复的多 seed 统计仍开放 | main 使用统一 D4 schema 增加同 seed 成对扰动 |
| M 对 N 联盟降级 | 已读取 D3 schema v2 demand/coalition/member/双版本，并实现 member ACK、commit lifecycle、lease/epoch、digest、分区、恢复双轨审计和 `atomic_coalition_formed`；真实 secondary/peer commit 正例及缺 ACK fail-closed 已通过 | 自主成员形成、reserve 激活、缩编/补位/整盟重组、D7 时序可达性和完整扰动矩阵尚未闭合 | P1 保持 commit 回归并完成扰动/重构矩阵；P2 只隔离比较 CCBBA/grouping，不绕过合同 |

## 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CA-CBBA 外部执行 | 已有隔离 capability adapter 和逐场景 unavailable 结果，但没有 import/执行外部算法 | MIT 参考为 MATLAB 且 runtime adapter 未集成；CA-CBBA 公共参考无可执行源码；外部项目也不提供 MSM coalition commit | 获得许可证明确的可执行源码和隔离 runtime 后，按现有 schema 增加 execution adapter；不得替换默认路径 | P2 execution unavailable |
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
3. **针对性 episode 数据仍不足**：常规 freshness 下的 10-seed 5v5 CV stress 已完成，但尚缺持续 network full-view、heartbeat/link/cue 故障、coverage-cell 切换和 active secondary plan 样本，不能据此标定全部阈值或接管延迟。
4. **外部开源适配成本**：MIT/CA-CBBA capability 探测已实现并以 unavailable 收尾；真实 execution 仍要求额外 runtime、协议状态、消息模型和许可证审查，不能直接替换主线。
5. **安全/身份边界**：D4 不应直接处理身份认证、图像语义、飞控动作或授权状态，只能消费 D5/main 的保守摘要。

## 缺少条件

- main 在同一 episode 中持续提供 D1 `TrackUncertaintySummary`、D2 `AssociationRiskSummary`、D3 `AssignmentValiditySummary`、D5 `TerminalAssociationSummary` 或等价对象/dict；P1 基线已接入，D2 truth/continuity unavailable 已有 D4 回归，仍需多 seed 缺测路径和其他字段分布校准。
- main/runtime 统一调用 `D4ArbitrationAdapter.evaluate()`，不再分散手工构造 D4 summary；2026-07-08 已在 main episode bus 中形成基线接线。
- D6 collector 接收 `D4DecisionRecord.to_event_record_kwargs()` 和 `build_cbba_d6_metadata()` 输出，并按 active/passive、secondary/distributed、coverage_cell、batch seed、review label 和 review window 聚合指标；长期报告口径仍需多 seed 固化。
- AirSim stress 已完成 2026-07-10 的 10-seed 常规 freshness 基线；下一批应专门构造持续 network full-view、heartbeat/lease/video-cue/link stale、coverage-cell 切换和 active secondary plan 样本，校准接管驻留时间、回落原因和 plan activation delay。D4 只消费这些摘要，不修正视觉几何注册。
- D3 在收到 `request_center_replan` 后已能由 main 触发新版本 `AssignmentPlan` 并把 plan id/version 写入后续 gate；main/D3/D7 已完成 secondary owner/version P1 基线和 controlled 2v2 secondary visual PNG 回归，D4 已输出 activation delay/pending duration 字段，仍需真实多 seed 校准 delay 分布、freshness 和恢复合并窗口。
- 中心恢复需要完整双轨日志：track digest、assignment digest、terminal lock、communication link、plan version、降级期间 fallback assignments。
- MIT/CA-CBBA capability adapter 已完成；若未来做外部 execution，仍需许可证/依赖审查、隔离 runtime 和 D6 cost/communication gap 报告。做独立 auction baseline 前，先完成同一任务集的 CBBA vs 中心化多 seed gap 聚合。

## P1/P2 下一步

0. **P1 M 对 N 联盟合同回归**：二级 ACK 3/3 `executing`、peer ACK 3/3 `executing` 和缺 ACK 2/3 `aborted` 已通过；后续保持这些场景并增加成员退出 `reconfiguring`、恢复和误降级统计。不得把 single-winner CBBA 宣称为自主 `k_j=3` 成员形成算法。
1. **P1 AirSim D4/D5 定向校准**：D4 逐决策审计和连续 readiness 已完成；main/D5 需输入真实 stable/not-registered，构造持续 network full-view 与 coverage-cell 切换 case，统计各状态驻留、source 分布、false degradation 和接管必要性。
2. **P1 secondary plan 回归与扰动**：合同正例已通过；继续注入 heartbeat/link/cue/gimbal/lease/source/成员故障，统计 executing 后的回落、恢复和 activation delay，不降低门限。
3. **P1 完整扰动矩阵与误降级成对标定**：注入旧 epoch、过期 lease、成员不可执行、center-secondary、secondary-interceptor、peer split/recovery 和 digest conflict，记录 partition/digest/duplicate-owner/merge 指标；同 seed 配置正常对照和故障真值，由 D6 统计 false/missed degradation、动作混淆和恢复时间。
4. **P1 CBBA gap benchmark 聚合**：D4 已有单场景 helper；main/D3 仍需保存中心化 cost matrix/current plan，D6 仍需聚合 lightweight CBBA 与中心化 Hungarian/Min Cost Flow 的 cost/completion/conflict gap。
5. **P2 隔离 optional auction baseline（未开始）**：只能在隔离环境用同一 summary/task/resource 输入与 CBBA 对照，不进入默认路径。
6. **P2 隔离 MIT/CA-CBBA adapter（capability 已完成，execution unavailable）**：原生 6 场景 replay 与外部逐场景 unavailable 行已落地；默认未配置参考路径。即使检测到 MIT MATLAB 源码也不执行，CA-CBBA 公共参考无可执行源码。未来 execution 仍不可替换默认轻量 CBBA，也不可绕过联盟 ACK/lease/epoch 合同。
7. **P2 恢复合并增强**：把 `merge_recovery()` 从 assignment-only 扩展到 track digest、terminal lock、communication link、coalition digest 和 plan version 的组合校验。

实施顺序更新为：保持 P1 commit 正负例回归 -> 完整扰动/成员重构矩阵 -> D6 多 seed 聚合 -> P2 隔离 benchmark。后续实现验收命令为 `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`。

## 关键依据路径

- `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/active_degradation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/adapter.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/coordinator.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/cbba.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/network.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/simulation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/p2_coalition_replay.py`
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
