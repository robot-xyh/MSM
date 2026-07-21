# D4 分布式协同与降级接管综述及子方案

**模块定位**：D4 负责中心 C2 异常、二级节点接管、主动降级仲裁和完全无中心协商的离线科研仿真方案。
**核心边界**：本文只讨论摘要交换、状态机、故障注入、降级协同和评估日志；不包含真实通信链路、飞控控制、火控参数、毁伤逻辑、自动处置或授权绕过。

**2026-07-21 正式行为克隆审计与准入更新**：D4 只读审计 2026-07-20 正式区域数据 900 episode/1798 frame，900/900 episode SHA256、source/schema identity、70/15/15 数值 seed 原子 split 和外部 1000-1019 隔离均通过。固定 seed `20260720` 的开发训练完成 66 epoch，最佳 epoch 54，内部测试 loss `0.071545`；准入复跑耗时 66.02 秒、推理 P95 `0.7774 ms`，权重 SHA256 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62` 与首次结果一致。D6 正式审计确认 14384 个区域动作中的 nonzero quota、transfer、hold、request_replan 均为 0，898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle admission 已固化全部动作计数、`action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`。结论严格限定为“管线可用但动作多样性不足，development/shadow-only”；低损失不代表策略能力，PPO/assist 不可用。权重只在 ignored `outputs/`，tracked 结果不含模型文件。当前区域建议/学习/消费与准入 51/51、数据/审计/训练发布 15/15，D4 全量 **369/369 passed**。

**2026-07-20 区域学习 episode 数据合同更新**：D4 新增 truth-free `d4-region-learning-dataset-v1` 及公开 source/frame、stage/finalize/load API。复核后训练 target 不再信任外部 `projected=true`，固定重验 projector、owner/plan/version/epoch/lease、备用、edge 和 quota；manifest 独立重验 canonical episode inventory、availability 与 split，truth/object/global-track key 变体失败关闭。该合同阶段数据测试 13/13、建议/消费 49/49、合计 62/62，D4 全量 **365/365 passed**。96-episode/192-frame 高基数样本只证明确定性合同，不是正式数据或模型收益证据；后续正式数据和开发 checkpoint 结论见上一段。正式降级控制路径未改变。

**2026-07-20 区域资源建议、消费合同与质点接线更新**：main-owned scalable 3D 已消费 D4 区域 verdict，闭合单一二级、多二级区域 owner、中心/二级连续失效后的 distributed D3 plan，并用 owner/node、plan version、epoch、lease、commit mode 与 fault generation fence 约束 D7；既有定向 8/8 passed，仅属质点接口证据。D4 新增 truth-free `RegionResourceSnapshot`、规则和确定性安全投影，以及共享变长图 actor-critic、BC、原生 clipped PPO、manifest/state_dict/SHA 和 paired shadow evaluator。动作只含区域 quota/邻区 transfer、备用、侦察和 hold/replan，不生成 resource-target assignment。`d4-region-resource-advisory-v1` 固化内容 ID、有效期、source plan、逐区域/transfer generation、reserve/committed 与 edge proof；`RegionResourceAdvisoryGate` 对下一周期 current snapshot/plan/epoch/lease/ACK/fault/守恒/邻接/容量和重复 ID fail closed。规则 fallback 与学习候选共享同一 projector；D4 仍不修改 D3 plan。原专项 32/32，新增 15 个消费 case 后该阶段专项 47/47、D4 全量 **350/350 passed**。该阶段只有纯 Python 合同证据；后续开发 checkpoint 不改变 D4 确定性状态机的最终裁决权，也不提供 AirSim 或真实网络收益证据。

**2026-07-20 区域化更新**：D4 新增 `d4-regional-failover-v1` 和 scalable3d mapping adapter，按动态 region/task/node 列表维护逐区域唯一 authority。中心未 `failed` 时主动 D1/D2/D3/D5 证据不转 owner；中心 `failed` 后只选择对 region 有显式 coverage、strict readiness 和有效 lease epoch 的 `mobile_high_recon`；二级不可用后才执行能力/跨区域 capacity 受约束 bid selection。中心、二级和 distributed 三层的 `k>1` 都必须 required ACK 全集、current plan/coalition version、epoch 和最早 lease 后原子 `committed`，commit metadata 分别标记 `d3_center_assignment`、`d3_assignment_secondary_coordination` 和 `bounded_constrained_bid_selection`，只有最后一种属于 distributed formation。缺 ACK、旧 generation、过期 lease 和任一层级分区均闭锁。新增 23 项测试覆盖 5/20/50/100/200 区域 metadata、声明节点数上限和安全边界，该阶段 D4 全量 **303/303 passed**，现已由 369/369 覆盖。区域合同单元用例本身无 AirSim/真实网络或物理证据；main 后续质点接线不改变该证据边界，受约束 selection 也不等于完整 CBBA/CCBBA、全局组合最优或自主重构。

**2026-07-15 P0 历史更新**：此前 278/278 只覆盖 coordinator、episode adapter、secondary coalition proposal、resource lease 和 D6 metadata，把它写成所有公开入口已闭锁属于过度声明。`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 后续要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格未过期；同一 active plan 维持路径也复核。当日 D4 全量 280/280 passed，先由 303/303、再由当前 369/369 回归取代。

**2026-07-15 M5N2 证据更新**：baseline/candidate 各 10 seeds、共 20/20 case 已完成，但全部是中心继续执行负对照，`active degradation=0`。coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均为 `collision_stop`；因 collision object 缺失，不把失败标签自动升级为主动降级。D4 仍联合 D1/D2/D3/D5 证据仲裁。D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`。额外 `png_ttc_2v2_seed001` 排除，dropout=0。该批不能关闭 secondary/distributed 多 seed P1。

---

## 0. 2026-07-11 P1 状态更新

当前结论以 `p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md` 为准：D4 所属 P1 合同层已闭合，ComputerVision 总体验收为 8/10。二级协调者 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` 并输出 `degrade_to_secondary`；完全分布式 `INT-02` peer 以 ACK 3/3 进入 `executing` 并输出 `degrade_to_distributed`；缺 ACK 场景以 2/3 ACK 进入 `aborted`，T001 三成员均 `hold_for_review`。这组正负例证明 commit 与 fail-closed，不证明物理拦截。

2026-07-12 P1 增量：新增 `d4_p1_failover_disturbance_replay_v1` 版本化扰动矩阵和 CLI。九个确定性场景 9/9 满足预期：中心正常保持 `continue_center`；二级节点只有 required-member ACK 完整后才能 `executing`；missing ACK、旧 epoch、过期 lease 和 digest conflict 均 fail-closed；成员丢失和网络分区先进入 `reconfiguring`，随后必须使用更高 epoch/plan/coalition version 并全员重新 ACK；中心恢复只进入 dual-track review，不立即夺权。该阶段 D4 全量测试 155 项通过，并包含四成员规模无关回归。该结论只关闭模块合同 replay，不关闭真实 AirSim 多 seed 的分区时序、误降级、恢复时间和物理任务连续性。

2026-07-12 通信时序增量：新增 `d4_p1_communication_fault_replay_v1` 和 CLI，接口按调用方提供的 member/secondary 列表运行，不固定 2v2/5v5。10 seeds x 6 场景共 60/60 满足安全预期：normal 无误降级；0.5 s delay 全部完整提交并拒绝乱序旧 plan-version ACK；30% loss 下 3/10 全 ACK 执行、7/10 缺 ACK fail-closed；center failure 保持 secondary 优先，center+secondary failure 才进入 distributed；partition recovery 必须新 epoch/plan/coalition version 和全员 re-ACK，旧 owner 被拒绝。逐场景 summary 已记录 owner/version、ACK/lease/epoch、首个失败原因、退出/重构、消息统计、重复 owner 和 split-brain prevention。加入 posefix 专项后该阶段 D4 全量测试为 167 项通过；真实 AirSim 网络注入仍不由 D4 模块 replay 替代。

2026-07-12 episode 接线增量：新增 `d4_airsim_episode_communication_v1`，供 main 用 AirSim episode timestamp 逐 tick 驱动。输入包含中心/二级 heartbeat、消息 delay/drop、missing ACK、partition、center digest 与 recovery authorization；输出包含 heartbeat/message 事件、ACK/missing/reject、lease、epoch、owner、plan transition、commit、fail-closed 和 recovery 状态。normal、center failure、center+secondary failure、partition/missing ACK 四类纯 Python replay 已通过；分区恢复强制新 generation 全量 re-ACK，中心恢复要求双轨 digest 连续校验且不立即夺权。独立 primary 不要求同时到达，但 secondary/distributed 多成员执行仍须原子 ACK。该接口随后已由 2026-07-13 episode-clock 批量矩阵完成 main 侧多 seed 验收；真实网络仍不在该接口结论内。

2026-07-13 主动降级策略增量：中心可用时不再由持续视觉错绑直接转移到二级或 distributed。低风险保持中心，进入末端适用窗口后的暂时 ambiguous/reacquire 或感知软风险只请求二级观测辅助；stale/not-current/resource infeasible、重复锁定、资源错配和持续 global-track mismatch 请求中心重规划。追加 `terminal_evidence_applicable` 后，远距雷达/GlobalTrack 充分且尚未进入视觉窗口时，普通视觉软证据、streak，以及中心正常/current/feasible、binding 安全条件下仅由 D1/D2/D3 非 hard-active 因子组成的组合均不触发 secondary assist；风险仍写入审计。高 D1 不确定度/陈旧量测、observed IDSW/duplicate、低 continuity、friend conflict、duplicate lock、资源或明确 ID 错绑始终保留。只有中心 failed 才进入二级接管，中心与二级均不可用才 distributed。assist/takeover 和适用性均进入 event 审计，该阶段 D4 全量测试为 193 项通过，最新 episode-time 增量后的总数见下一段。

2026-07-13 episode-time 验收增量：`d4_p1_episode_fault_validation_matrix_v1` 将正常、中心失效后二级接管、二级再次失效后 peer 接管、missing ACK、stale epoch、expired lease 和 partition 分为 7 个独立规范场景。顺序降级场景先在 1.25 s 内形成二级 executable owner，再注入二级 heartbeat loss，并在 1.00 s 内完成 peer 原子 commit；验收上限分别为 1.5 s 和 2.5 s。normal 误降级为 0，四类安全异常均 fail closed，逐 tick owner、plan/coalition version、epoch 和 lease 审计完整。main/runtime 进一步按 AirSim episode clock 对 `normal`、`center_failure`、`center_secondary_failure`、`delay_0_5s`、`loss_30pct` 和 `partition_recovery` 六类场景各运行 10 seeds，共 60 case：60/60 safety outcome 通过，误降级、duplicate owner 和 split-brain prevention failure 均为 0。D4 全量回归为 198 项通过。该结果关闭 episode-clock 批量注入，不代表真实 RF、吞吐带宽、节点时钟漂移、操作系统/网络排队、乱序、重传或硬件链路已验证。

2026-07-12 posefix terminal consistency 专项：历史四组 smoke 中，中心 owner、current coalition 且 hard risk 为空时仍有 1087/1094/585/1064 条 `terminal_consistent=false`，对应 control CSV 的 `d4_terminal_inconsistent` 为 158/112/113/122 条。该现象不是正常安全拒绝，而是 D4 将 D5 readiness 再次解释为 plan binding，并共享单一 arbiter 迟滞状态造成的实现缺陷。修复后 binding 只由 resource/global-track/version/coalition、friend、duplicate、mismatch 等硬证据决定；D5 lock/confidence/ambiguity/reacquire 保持独立，持续失锁只请求 cue。adapter 按 pair 隔离状态，并输出 binding reject reasons、visual state 和 state key；active secondary lease 过期显式 hold。该专项阶段 D4 全量测试为 167 项通过，历史 AirSim 日志不回写，main 仍需重跑系统验收。

SimpleFlight 15 s 只用于诊断，30 个 active pair 物理命中为 0，系统物理拦截仍未闭合。D4 的 episode-clock 批量故障注入已经完成；后续 P1 转为真实吞吐带宽、节点时钟漂移、网络/操作系统排队抖动、乱序/重传、secondary-interceptor/peer 实际链路和长时间恢复统计，同时保留 heartbeat/link/cue/gimbal/source 与物理连续性审计。P2 只允许隔离式 benchmark，不替换轻量 CBBA 与 ACK/lease/epoch 合同。

2026-07-11 P2 隔离 replay 已补齐：原生 6/6 场景满足预期安全结果，中心 -> 二级 -> 完全分布式与成员丢失/补位均 7 轮完成、最优绝对差距 0；其余故障在 1-3 轮 fail closed。MIT/CA-CBBA 仅做可选 path/source capability probe，默认输出 unavailable，不 import/执行外部工程，不新增依赖，也不进入在线 D4。该 deterministic replay 和已通过的 episode-clock 批量矩阵都不能替代真实网络验证。

### 历史实施记录（不作为当前状态）

最新 M-to-N ComputerVision 收敛报告补充了中心重规划和协同视觉证据：seeds 7/17/27 均为 6 次 request、6 次 no-change ACK、0 applied、0 expired，需求满足率均为 1.0，错误重复锁均为 0；T002 共识帧为 4/5/4，D7 每 seed 获得 2 次终端合同许可，而 T001 双 primary 共识均为 0。结论是中心重规划 lifecycle 和合法多成员锁审计已收敛，但高威胁协同视觉与 fallback 联盟仍未闭合。该批次运行在 ComputerVision 模式，只验证状态合同，不验证动力学控制、协同到达或物理拦截。

M 对 N 联盟专项调研已完成，详见 [D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md](D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md)。审计覆盖 11 篇主要论文和 5 个公开仓库/归档，确认基础 CBBA 只提供 single-winner 基线，不能通过复制目标任务实现 `k_j=3` 的原子联盟。中心正常时应由 D3 生成联盟，D4 维护健康、lease、epoch 和重构；中心失效优先二级节点接管完整联盟摘要；完全无中心的 CCBBA/consensus grouping/coalition formation 仍属于 P1 合同研究和后续可插拔算法路线。成员退出必须按“满足最低需求则缩编、reserve 可达则补位、否则整盟重组”处理；同时/序贯/混合只由联盟合同表达，实际可达性由 D7 验证。

M-to-N 安全实现已扩展到本地原子提交合同：D4 通过 `CoalitionSafetyEvidence` 消费 D3 schema v2 coalition/member/version/demand，并通过冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 管理 ACK/commit lifecycle。当前区域合同要求中心、secondary 和 distributed 三层 `k>1` 都通过 target、coalition/plan 双版本、epoch、成员、lease 和 digest 校验，全部 required ACK 后才原子 `committed`；中心与二级沿用 D3 给定成员，仅 distributed fallback 使用 `bounded_constrained_bid_selection`。无 commit、缺 ACK、过期、旧 epoch、分区或冲突仍输出 hold/reconfigure。合法联盟多个授权资源锁同一 `global_track_id` 不视为 duplicate；第四个成员、超额锁、旧 plan 或旧 coalition version 均拒绝。完整 CBBA/CCBBA 多轮共识、全局组合最优和在线联盟重构仍未实现。

上述两个合同已在 D4 模块内实现：`CoalitionMemberAck` 记录 member/target/coalition/plan version、epoch、能力状态、证据时间和有效期；`CoalitionCommitState` 使用 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted` 状态并记录 required/acked members、lease、时间戳和失败原因。下一步 P1 是由 main/D3/D5/D6/D7 在真实 episode 中生产和消费这些 DTO，验证二级 active plan、完全无中心三成员 commit、成员退出重构和同 seed 分区负例，而不是继续修改本地状态语义。

真实 AirSim `blocks_cv_m5_n2_cooperative_live_20260711` 暴露并验证了本轮修正点：中心 alive/owner=center，T001 coalition demand 3/3、complete、version current，但 D5 长期 reacquire 后原 arbiter 输出 `degrade_to_distributed`。由于现有 distributed 仍是 single-winner，该动作不具备原子联盟语义；修正后同类候选必须回到中心重规划，不能仅凭静态 `coalition_center_plan_valid` 放行。

中心重规划请求 lifecycle 的模块接口已补齐：`CenterReplanStatus` 是从包顶层导出的冻结 DTO，`risk_signature` 为排序去重 tuple，四态为 `pending|applied|acknowledged_no_change|expired`。adapter 对同 target/coalition scope 比较当前风险；默认 2.0 秒 cooldown 内，pending/applied/no-change 即使新增非硬风险也继续中心，严格边界到期才重新请求。`terminal_persistent_disagreement` 可触发首次 request，但 ACK 后不逐帧重发；既定 hard safety、expired 和 center failed 直接绕过。该动作不改写 D5 summary，因此 D5 仍可独立阻断 D7。测试覆盖 soft ambiguity `+0.5s` suppress、`+2.0s` reopen、friend/version `+0.5s` bypass、四态、center failed、非法重复锁、ID switch、coalition conflict、`k=1` 和 `k>1` fail-closed。

assignment freshness 已修正为活性语义：`build_assignment_validity_summary()` 优先读取 `plan.metadata.last_evaluated_at_s`，兼容 `last_evaluated_at/evaluated_at_s/evaluated_at`，缺失时才按 `created_at` 保持旧行为。`plan_age_s` 只表示最近评估活性年龄，稳定 plan ID 的 `identity_age_s` 连同参考字段和时间戳进入 assignment evidence metadata。超过 stale threshold 后仍生成原 `d3_assignment_not_current/d3_assignment_stale` 硬风险并绕过 replan cooldown；加入原子联盟合同、current-coalition pending 收敛和 P2 replay 后，当前 D4 测试为 144 项通过。

真实 `p1_cv_m5_n2_consensus_smoke_20260711` 的 `t=1.5` 暴露了 pair action 不一致：T001 D5 已给出 plan/coalition v2、INT-02/INT-03 primary consensus locked，但 D4 旧实现只读取单 pair lock，INT-02 仍 request replan，而 INT-03 因 pending 去重 continue。D4 已在 owned adapter 内消费完整 D5 summary，并以 current 双版本、primary 集合、conflict/commit/health 硬门控收敛 soft pending。main 已提供该 summary，本轮未跨模块改 runtime；真实 AirSim 需由 main 重跑确认，不在本 review 中预先宣称通过。

同一真实复验还定位出 D2 风险解释错误：`duplicate_track_risk` 是候选/协方差重叠的连续 score，旧 adapter 却用 `risk >= 0.5` 合成 observed count。D4 已删除该转换，独立保留 soft `d2_duplicate_track_risk_high`；显式 count、delta/delta sum 或 observed flag 仍生成 hard `d2_duplicate_track_observed`。因此风险 score 不再冒充已发生重复，真实重复事件的即时阻断保持不变。

D4 模块内已补齐 P1 所需的本地输出口径：secondary takeover record metadata 可区分 `pending_secondary_plan` 与 `secondary_plan_active`，并携带当前/二级 plan id/version、source node、supersedes plan、reassignment complete、plan activation delay 和 pending duration 字段；主动降级 metadata 已能输出 `necessary/unnecessary/inconclusive` 三值 review label、`active_degradation_necessity_label`、pre/post review window、secondary diagnostic、takeover necessity/success，并透传 D5 二级视觉覆盖/转换漏斗 evidence，区分 `not_ready`、`visible_only`、`registration_usable` 和 `takeover_ready`，避免把二级 detect 可见直接等同为可接管；`role/capability_class=mobile_high_recon/mobile_secondary_recon` 已作为机动高空二级侦察节点元数据进入候选、lifecycle 和 D6 事件，并与 `fixed_tethered_secondary/tethered_recon` 区分；完全无中心 CBBA 已用 D5 distributed visual evidence 做风险加权；`build_cbba_cost_gap_benchmark()` 可用 D3/main 提供的中心 plan 与 cost matrix 计算 CBBA vs 中心化 cost gap；`build_cbba_d6_metadata()` 和 `run_failover_simulation()` 顶层 metrics 可输出 secondary/distributed 分组、leader、coverage、CBBA 审计和 cost gap 扁平字段。

本轮 D4 P1 进一步闭合了“瞬时可见”到“可执行接管”之间的时序合同。现有 score >= 0.70、coverage >= 0.65、network full-view >= 0.80 门限保持不变；adapter 默认要求 `takeover_ready` 在 3 个不同时间戳决策中连续成立、持续至少 0.2 s 且 evidence gap 不超过 1.0 s，同一帧的重复评估不累计。2026-07-11 修复了 `not_ready -> takeover_ready` 边沿未设置 `ready_since_s` 的问题；首次 ready 和回落后的再次 ready 都从 count=1/新 timestamp 重启窗口。lifecycle/event 逐决策输出 stable/not-registered value、presence、evidence source、streak、duration、sustained 和 fallback reason。pending/active 还校验 source node、required lease epoch、lease expiry 和 plan version，并记录 transition、pending since、activated at、activation delay 与回落原因。D2 online truth 隔离语义也已闭合：`truth_metrics_available=False`/`continuity_available=False` 时，IDSW/continuity 占位不进入硬风险；在线 ambiguity、duplicate/quality risk 仍有效。

main/runtime P1 基线也已接入：episode bus 已消费 D4 adapter event，`request_center_replan` 可触发 D3 new plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已新增，可批量改变二级节点高度、FOV、节点数量和 standoff，并在 sweep 结束后自动生成 D6 标准 AirSim calibration records/summary/report bundle。该 owner/version 闭环是 main-owned 消费口径，D4 保持只输出仲裁/metadata，不生成系统级 `AssignmentPlan`。

2026-07-08 AirSim 机动高空侦察节点 stress 结果已同步到当前状态：输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`，3 seeds 均 connected=True；每个 seed 含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，所有 episode 均为 13 frames 且 image_ok=13。场景使用 5 个目标、5 个拦截相机、2 个二级侦察相机、200 m 高差、80 度 FOV 和 1920x1080。D4 主动作符合预期：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`；二级侦察侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。

`p1_gap_closure_calibration_20260710` 已完成 10 seeds、50/200 m、3 个机动高空二级节点、FOV 110 度、1920x1080 的 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m 的 network joint full-view 均值/范围为 0.023/0.000-0.154，coverage 均值 0.685；200 m 的 network joint full-view 恒为 0.000，coverage 均值 0.708。两种高度的 projection valid 都为 1.0，cross-view association 均值 4.6/4.0，stable registration 均值 86.3/96.7，not-registered 为 0，说明“检测到但未注册”已不是本轮主断点，网络同帧全覆盖的持续性才是主断点。

2026-07-11 又完成三组 online truth 隔离的真实 AirSim smoke。结果如下；表中的“网络平均覆盖”是跨帧/节点覆盖比例，不能替代同帧全目标联合覆盖。

| 证据目录 | 高差/二级节点 | 中心保持正例 | 预期二级接管正例 | 分布式负例 | 二级正例网络平均覆盖 | 二级正例同帧联合全覆盖 |
|---|---|---|---|---|---:|---:|
| `p1_runtime_truth_isolated_d4d5_smoke_20260711` | 200 m / 2 | `continue_center` | `degrade_to_distributed` | `degrade_to_distributed` | 0.72 | 0.00 |
| `p1_runtime_truth_isolated_d4d5_50m_20260711` | 50 m / 2 | `continue_center` | `degrade_to_distributed` | `degrade_to_distributed` | 0.64 | 0.00 |
| `p1_runtime_truth_isolated_d4d5_secondary5_20260711` | 200 m / 5 | `continue_center` | `degrade_to_distributed` | `degrade_to_distributed` | 0.80 | 0.00 |

这三组证据说明中心保持和分布式负例动作正确，在线 truth 隔离没有造成 D4 误触发；同时也证明“增加二级节点数量”只改善了平均 coverage，并未自动形成持续 `takeover_ready`。二级正例没有进入 pending/active 的结果符合当前安全合同，但它不是二级接管能力完成证明。

P0 状态：无 P0 blocker。历史 1300 条 secondary-case D4 决策中，1285 条因 network full-view < 0.80 保持 `registration_usable`；仅 15 条瞬时 `takeover_ready`，且没有 active/executable plan。新连续门控会把这些单帧/短时样本保持为 distributed，不降低既有门限。D4 已能审计显式 stable/not-registered 是否存在及其来源，但历史 AirSim input 仍为 `null`，因此 main/D5 还需完成真实逐帧接线。2026-07-11 三组 smoke 进一步确认安全回落正确，但二级接管正例仍未形成持续同帧全覆盖和 active plan，因此 P1 保持未关闭。剩余 P1 聚焦正向 sustained AirSim 样本、D3 active plan 回填、coverage-cell 聚合、网络分区与误降级成对标定、D5 peer evidence 和恢复双轨统计。

D4 对二级侦察结果的解释保持四级瞬时 readiness。`registration_usable` 只能作为辅助和诊断证据；`takeover_ready` 还必须通过连续窗口才能进入 pending，不等于接管完成。真正接管要求 main/D3 回填新的 plan id/version、正确 source、有效 lease epoch/expiry 并形成 `secondary_plan_active`/executable；D7 还要验证 current binding。D4 不做相机几何注册、不生成完整 `AssignmentPlan`，也不放宽安全门控。

---

## 1. 被动降级 vs 主动降级

D4 必须明确区分两类降级，因为触发源、优先级和恢复条件不同。

| 类型 | 触发条件 | 主要目标 | 默认策略 |
|---|---|---|---|
| 被动降级 `passive_failover` | 中心节点被摧毁、失联、heartbeat 超时、中心摘要长期不可用、peer quorum 判定中心失败 | 在中心不可用时维持保底任务连续性 | 中心 C2 -> 二级节点 -> 完全无中心 CBBA/拍卖 |
| 主动降级 `active_degradation` | 中心未失效，但 D1/D2/D3/D5 证据显示当前计划不可靠 | 防止“中心仍在线但局部计划已经失效” | 继续中心计划、请求中心重分配或请求二级观测辅助；不转移 plan owner |

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
  -> request_center_replan: D3 分配过期/版本不当前/资源不可行，或 D5 持续硬错绑/重复锁定
  -> continue/assist      : 仅代价裕度不足、低置信度或无冲突 reacquire 时继续观察
  -> request_secondary_assist: D1/D2 风险升高但 D5 仍一致
  -> hold_for_review      : friend_conflict 或身份冲突
```

`degrade_to_secondary/degrade_to_distributed` 只由 `C2Health == failed` 的被动链路产生。二级节点可见、覆盖充分或 readiness 高均不能在中心可用时触发接管。

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
- `truth_metrics_available`
- `continuity_available`

主动降级风险：

- 离线 truth 指标可用时，多目标交叉后 `id_switch_count` 增加。
- `ambiguity_score` 高，GNN/Hungarian 硬关联不稳定。
- 重复航迹出现，可能导致 D3 重复分配。
- continuity 指标可用时，`track_continuity` 下降说明中心计划绑定的目标身份可信度不足；在线不可用的数值占位不得触发降级。

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
- `terminal_evidence_applicable`（默认 `true`；兼容 `evidence_applicable`、`visual_evidence_applicable`、`within_terminal_visual_window`、`terminal_visual_window_active`）
- `decision_state`: `locked | ambiguous | hold | reacquire`
- `association_confidence`
- `ambiguity_score`
- `consecutive_non_locked_frames`
- `consecutive_mismatch_frames`
- `friend_conflict`
- `coverage_cell`

主动降级风险：

- `terminal_evidence_applicable=false` 且中心正常时，多帧 `ambiguous/hold/reacquire`、低置信度、高歧义、cross-view 软风险、无明确观测 ID 的 streak，以及仅含 D1/D2/D3 非 hard-active 因子的组合不参与辅助/重规划；这些风险保留审计并继续中心。
- `terminal_evidence_applicable=true` 时，D5 多帧 `ambiguous/hold/reacquire` 但没有观测 ID mismatch、资源错配、重复锁定或友方冲突，只作为软证据。
- 本地视觉候选与 D3 分配目标长期不一致。
- `resource_id` 与 D3 指派资源不一致。
- `friend_conflict=True`，必须进入 `hold_for_review`，不能降级为自动协商。
- 明确的 observed/assigned `global_track_id` mismatch、重复锁定和资源错配在窗口外也不得忽略。

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
     -> 中心可用时 request_center_replan
     -> friend conflict 则 hold_for_review

9. 只有中心 failed 才进入 fallback：
     -> 二级节点持续 ready 则 degrade_to_secondary
     -> 二级不可用则 degrade_to_distributed

10. 若 CBBA/拍卖不收敛：
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

历史基线（2026-07-10）：10-seed sweep 证明 `mobile_high_recon` 的云台、cue、注册和 freshness 基线可用，但当时 20 个 secondary case 的最终动作仍全部 distributed。该记录用于说明不能只看单帧可见性或累计 stable registration，也不得降低 D4 门限；它不再表示当前二级 commit 正例状态。

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
- secondary_plan_pending_since_s
- secondary_plan_activated_at_s
- secondary_takeover_previous_state
- secondary_takeover_transition
- secondary_takeover_fallback_reason
- required_secondary_plan_lease_epoch
- secondary_plan_source_matches_target
- secondary_takeover_candidate
- secondary_takeover_success
- secondary_takeover_necessity_label
- active_degradation_necessity_label
- review_label: necessary | unnecessary | inconclusive
- active_degradation_review_window
- secondary_diagnostic_heartbeat_age_s
- secondary_diagnostic_link_fresh
- secondary_diagnostic_cue_freshness_s
- secondary_diagnostic_gimbal_pointing_ok
- secondary_diagnostic_coverage_ratio
- secondary_capability_class: not_ready | visible_only | registration_usable | takeover_ready
- secondary_capability_inputs
- secondary_diagnostic_capability_class
- stable_cross_view_registration_count
- not_registered_count
- secondary_diagnostic_registration_evidence_source
- secondary_diagnostic_stable_registration_evidence_present
- secondary_diagnostic_not_registered_evidence_present
- secondary_takeover_ready_consecutive_decisions
- secondary_takeover_ready_since_s
- secondary_takeover_ready_duration_s
- secondary_takeover_ready_sustained
- secondary_takeover_readiness_fallback_reason
- secondary_network_full_view_gap
- secondary_detect_to_registration_gap
```

规则：单帧 `takeover_ready` 不产生 pending；只有连续窗口成立才输出 `degrade_to_secondary/pending_secondary_plan`，此时 owner 仍保持当前计划。main/D3 回填正确 source、更新 version、有效 lease epoch/expiry 并标记 active 后，D4 才进入 `secondary_plan_active`。任何 readiness、heartbeat/link/cue/gimbal 或 lease 回落都必须记录 transition/fallback reason，并阻断 executable。D4 不发布完整 `AssignmentPlan`。

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
- `active_degradation_necessity_label`
- `secondary_plan_activation_delay_s / secondary_plan_pending_duration_s`
- `secondary_capability_class / secondary_capability_inputs`
- `secondary_network_coverage_available / secondary_network_full_view_gap`
- `secondary_single_camera_full_view_frame_rate / secondary_network_joint_full_view_frame_rate`
- `secondary_network_mean_coverage_ratio / cross_view_association_count`
- `stable_cross_view_registration_count / not_registered_count`
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

RegionalFailoverSnapshot
- scalable scenario name/version + dynamic node/region/task counts
- region definitions and partitioned region ids
- D1 covariance/age, D2 ambiguity/IDSW/duplicate
- D3 plan id/version/epoch/lease/current/feasible
- D5 consistency/binding/friend/duplicate and member evidence
- mobile_high_recon readiness by region
- fallback members and coalition ACKs

RegionOwnershipMetadata
- region_id + one owner_id/layer/role
- plan_id/plan_version + epoch + lease expiry
- active flag + scoped task ids
```

摘要必须粗粒度、带版本、带 epoch。区域 owner/layer 改变要求 epoch 与 plan version 同时前进；同 generation 换 owner、过期 lease 或分区均 fail closed。D4 不应接收未经 D1/D2/D3/D5 校验的完整高精度态势，也不应让局部节点直接覆盖 `global_track_id`。

---

## 9. CBBA、拍卖和合同网综述

2015-2026 年无人机集群任务分配中，CBBA、拍卖算法和合同网协议是常见分布式路线。

CBBA 通过 winner/bid 向量扩散和一致性消解，在连通图、确定仲裁和边际收益条件满足时可有限轮收敛。优点是适合多智能体任务协商，缺点是通信量随任务数、束长和网络直径上升。

拍卖算法实现简单、收敛快，适合保底协商；但如果缺少稳定拍卖人或一致仲裁，可能发生反复竞价。合同网协议适合动态插入任务，通信过程清晰，但结果通常偏贪心。

工程共识是：中心正常时不主动全分布式；二级节点可用时不直接全分布式；完全无中心只作为中心和二级节点均不可用后的保底能力。

对于 `k_j>1`，上述基础结论需要增加限制：普通 CBBA 的一个 task 只有一个 winner，不等于 coalition formation。CCBBA 可表达 assignment/temporal coupling，consensus-based grouping 和 distributed coalition formation 可表达多个异构成员共同完成任务，但目前未发现同时具备明确许可证、维护、联盟时序、成员退出重构和可直接接入 MSM summary bus 的成熟 Python 库。因此当前 D4 轻量 CBBA 只能继续作为 single-winner/候选成员研究基线，不能宣称已经支持三机协同拦截。

2026-07-20 区域合同仅在 distributed fallback 增加能力/跨区域 capacity 受约束 bid selection，可从动态区域 member 集合生成候选、允许单成员覆盖多项 capability，并叠加全层原子 commit。中心和二级分别沿用 D3 中心成员与 D3 二级协调成员，不运行该 selection；三层 `k>1` 都执行完整 ACK 原子门。distributed selection 按 region id 确定性贪心，不提供全局组合最优；也没有 CBBA 多轮消息传播/收敛状态或 CCBBA 的任务耦合与时间窗优化，因此只缩小“候选集合形成”工程缺口，不关闭上述完整算法差距。

---

## 10. 故障注入测试建议

| 场景 | 期望 |
|---|---|
| 中心 heartbeat 丢失 | `normal -> suspect -> failed`，触发被动降级 |
| 中心 failed + 二级节点健康 | `degrade_to_secondary`，`secondary_node_takeover_count + 1` |
| 中心 failed + 二级节点 unavailable | `degrade_to_distributed`，启动 CBBA/拍卖 |
| 二级 commit 全员 ACK | ACK 3/3，最终 `executing`；已通过 |
| peer commit 全员 ACK | ACK 3/3，最终 `executing`；已通过 |
| peer commit 缺 ACK | ACK 2/3，最终 `aborted` 并 `hold_for_review`；已通过 |
| 二级节点接管后失效 | 二次被动降级到局部代表/CBBA |
| D1 协方差增大但 D5 一致 | 请求二级辅助，不直接分布式 |
| D2 ID switch 上升但 D5 一致 | 请求二级辅助或中心重分配 |
| D3 plan stale 但 D5 一致 | `request_center_replan` |
| D5 多帧无冲突 `ambiguous/hold/reacquire` | 继续中心或请求二级 cue，不直接重规划/降级 |
| D5 多帧硬不一致或资源错配/重复锁定 | 中心可用时 `request_center_replan`，不转移 owner |
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
7. mobile recon 的 `gimbal_pointing_ok`、`radar_global_track_cue` 和 `mobile_high_recon` capability 只能证明候选节点可用；二级网络同帧全覆盖不足或 not-registered 仍高时，D4 应继续记录 coverage/registration 断点并等待上游校准。
8. `degrade_to_secondary` 前必须通过 D4 sustained readiness；进入 pending 后继续校验 source/version/lease，并区分 active 与回落。main 必须复用 adapter 实例，D3 只生成计划，D7/D6 分别消费 current binding 和 transition/timing/fallback metadata。
9. 后续 D4/D5 AirSim 校准应优先使用 main runtime 的 P1 calibration sweep 和 D6 标准 bundle 输出；D4 只消费 sweep 产生的摘要与 report 字段，不直接启动 AirSim 或写 main runtime。
10. 旧 epoch、过期 lease、center/secondary failure、30% loss、0.5 s delay 和 partition recovery 已在规范 replay 与六类、10-seed、60-case episode-clock 矩阵中保持回归；下一阶段只补真实带宽、时钟漂移、排队/抖动/乱序/重传、secondary-interceptor/peer 实际链路以及成员退出/重构。D6 继续输出 false/missed degradation、动作混淆、duplicate owner、split-brain prevention failure、恢复时间和 merge outcome。

---

## 12. 参考资料

- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- CBBA-Python: <https://github.com/zehuilu/CBBA-Python>
- CA-CBBA: <https://github.com/mit-acl/CACBBA>
- Dynamic UAV task allocation survey: <https://www.mdpi.com/2504-446X/9/1/75>
- D4 M 对 N 联盟形成专项审计：<D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md>
