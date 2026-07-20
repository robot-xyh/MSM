# D4 分布式协同与降级接管

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

**2026-07-20 scalable 3D 接线事实同步**：main-owned `IntegratedScalableModuleStack` 已消费 `d4-regional-failover-v1`，闭合单一二级 owner、两个二级节点的多区域 owner，以及中心与二级连续失效后的 distributed D3 plan。D7 在恢复质点导引前核对区域 owner/node、plan version、epoch、lease、commit mode 和 fault generation；过期 lease、缺 commit 或旧 source plan 均 fail closed。本轮只读定向复核 `research_modules/scalable_3d_simulation/tests/test_module_stack.py` 为 **8/8 passed**。这是三维质点接口/集成测试证据，不是 AirSim、真实 RF/mesh/socket、硬件或实飞证据，也不代表长时 200v200 多 seed 已验收。

**2026-07-20 可选区域资源建议层**：新增版本化 `RegionResourceSnapshot`、确定性规则基线、安全投影、共享区域图 actor-critic、行为克隆、原生 clipped PPO、manifest + `state_dict` + SHA256 bundle、整 `(scenario, seed)` 划分和 paired shadow evaluator。快照只含区域聚合需求、不确定性、可见/一致性、资源/备用、二级覆盖/就绪、通信和当前 authority fence，不含 actor truth ID 或具体目标身份。输出只允许区域配额增减、相邻区域资源转移、备用比例、侦察优先级与 hold/replan；不能生成 resource-target assignment。学习层默认 `disabled`，CLI 默认 `shadow`，任何超时、低置信、OOD、非有限输出、模型版本或 SHA 不匹配都回退规则建议；少于 20 个未见 seed 不得进入 assist。所有建议仍经 owner/version/epoch/lease、fault fence、ACK/commit、邻边和资源守恒投影，D4 确定性安全状态机继续拥有最终降级裁决。新增专项 **32/32 passed**，D4 全量 **335/335 passed**，均为确定性/研究管线测试，不是训练完成、模型优于规则或真实网络证据。

**2026-07-20 区域化合同状态**：新增 `d4-regional-failover-v1`，面向 scalable3d 场景按输入长度维护逐区域唯一 authority。中心未 `failed` 时保持中心 owner，仅根据 D1 协方差/时效、D2 ambiguity/IDSW/duplicate、D3 plan/version/epoch/lease/current/feasible 和 D5 consistent/inconsistent/binding/friend/duplicate 证据输出继续中心、请求机动高空侦察辅助、中心重规划或保持复核；中心 `failed` 后只选择对该区域具有完整持续 readiness、coverage 和有效 lease epoch 的 `mobile_high_recon`，没有有效二级节点时才进入受约束 bid fallback。任一层级的 `k>1` 任务都必须由全部 required member 对同一 plan/coalition version、epoch 和有效 lease 完成 ACK 才成为 `committed`；区域 authority/commit lease 取 authority、D3 task 和二级 lease 的最早到期值。缺 ACK、旧 epoch/version、过期 lease 或分区均闭锁。该阶段纯 Python 验收新增 23 项，覆盖 5/20/50/100/200 区域元数据、声明节点数上限、中心与二级连续失效、双区域 coverage、中心/二级/distributed 原子门、分区、D5 member hold、跨区域 capacity、单成员多能力、旧 generation 和 lease；当时 D4 全量 **303/303** 通过，现已由 335/335 回归覆盖。该模块合同本身没有 AirSim、真实网络或物理拦截样本；受约束成员选择是确定性基线，不等于完整 CCBBA、reserve 激活或在线联盟重构。

**2026-07-15 P0 历史状态**：当日重新确认的二级接管 P0 已关闭。此前 278/278 回归覆盖 coordinator、episode adapter、secondary coalition proposal 和 D6 metadata，但把它表述为“所有公开 secondary owner 入口均已闭锁”属于过度声明：`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 仍会把缺失的 sustained readiness、expected/actual source 或 plan/required lease epoch 当成“不是 False”而放行。两个 helper 及 adapter 后续均要求这些字段显式存在，`secondary_readiness_sustained is True`、source 相等、plan epoch 不低于 required epoch，且 current time/expiry 存在并严格满足 `current_time < expiry`；同 id/version 的已激活 secondary plan 维持路径也执行同一复核。当日 D4 单元测试 280/280 通过；该历史数字先由区域合同阶段的 303/303、再由当前 335/335 回归取代。

**2026-07-15 M5N2 负对照同步**：真实 AirSim M5N2 baseline/candidate 各 10 seeds，共 20/20 case 完成。该批全程保持中心 owner，`active degradation=0`，因此只用于验证“中心继续执行时不误降级”和定位协同末端断点，不能宣称二级接管或完全分布式联盟性能闭合。聚合结果为 coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均以 `collision_stop` 结束；当前产物未记录碰撞对象，不能把该状态自动解释为成员冲突，也不能把它作为主动降级触发。D4 仍必须联合 D1 不确定度、D2 关联风险、D3 plan/version/可行性和 D5 当前绑定/身份/视觉一致性证据进行仲裁。D4 main-bus 阶段 mean/P95/max 约为 `5.59/6.70/94.10 ms`，不是本批约 1 s control tick 的主要耗时。终止前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合，dropout case 完成数为 0。真实 secondary/distributed 多 seed 仍为 P1。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `scripts/run_p1_failover_replay.py`：版本化 P1 二级/分布式接管扰动矩阵。
- `scripts/run_p1_communication_fault_replay.py`：六场景、多 seed 的 P1 通信故障矩阵。
- `scripts/run_p1_episode_fault_replay.py`：使用 AirSim 兼容 episode 时钟运行 P1 故障注入验收矩阵；不启动 AirSim，也不模拟真实 RF 网络。
- `d4_distributed_fallback/episode_communication.py`：供 main 按真实 AirSim episode 时钟逐 tick 调用的通信故障状态接口及七场景纯 Python replay。
- `d4_distributed_fallback/regional_failover.py`：scalable3d 兼容的区域场景元数据、逐区域 authority、主动证据、二级 readiness/coverage 和原子 fallback 合同。
- `d4_distributed_fallback/region_resource.py`：truth-free 区域资源快照、规则建议、确定性安全投影、reward、整 scenario/seed 划分和 paired shadow 指标。
- `d4_distributed_fallback/region_resource_learning.py`：可选共享区域图 actor-critic、BC、原生 clipped PPO、bundle/SHA/OOD 与 fail-closed advisor。
- `scripts/run_region_resource_advisor.py`：区域资源建议与 shadow paired evaluator CLI；默认 `shadow`，不改变正式 D4 verdict。
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

运行 10-seed 通信故障矩阵；成员数和二级节点数均由入口参数决定：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_communication_fault_replay.py \
  --member-count 3 --secondary-count 2 --seed-count 10
```

运行 episode-time 故障注入验收矩阵：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_episode_fault_replay.py \
  --member-count 3 --secondary-count 1
```

该入口覆盖正常中心、中心失效后二级接管、二级再次失效后 peer 接管、缺 ACK、旧 epoch、过期 lease 和分区。输出中的 `real_rf_network_validated=false` 与 `real_hardware_validated=false` 是固定边界：结果只验证 episode 时钟上的合同和故障注入，不代表真实无线链路、网络设备或硬件故障验证。

运行任意区域数的 shadow 建议 demo：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_region_resource_advisor.py \
  demo --region-count 8 --mode shadow
```

正式 snapshot 使用 `recommend --snapshot PATH [--bundle-dir PATH]`；paired 评估使用 `shadow-evaluate --baseline PATH --candidate PATH`。即使显式请求 `--mode assist`，少于 20 个未见 seed、规则回退或任一模型门失败时仍降为 shadow。

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- 区域化 scalable3d 合同：`RegionalScenarioMetadata.from_scalable_scenario()` 只读消费 `scalable3d-scenario-v1` 的 target/resource/recon/region count，并拒绝 schema 或声明数量溢出；`RegionalFailoverCoordinator` 按实际 region/task/node 列表运行并输出 truth-free `d4-regional-failover-v1` bus payload。逐区域 owner 变更必须同时提升 `epoch` 和 `plan_version`，租约严格使用 `timestamp < expiry` 且收缩到最早 D3 task/secondary expiry，同 generation 不允许换 owner，分区时所有层级闭锁。
- 全局区域资源建议：`RegionResourceSnapshot` 和 `RegionResourceEdge` 按变长区域图运行；`RuleRegionResourcePolicy` 与 `DeterministicResourceProjector` 保证总资源守恒、只走可通信/可机动邻边、最低备用、当前 authority fence 和已提交联盟资源。`SharedRegionGraphActorCritic`、BC/PPO 与模型 bundle 只属可选研究路径，默认不参与正式 D4 裁决。
- `C2Health` 状态机：`normal -> degraded -> suspect -> failed`，heartbeat 使用滑动窗口和 `degraded/suspect` 防抖确认，中心恢复需双轨合并，不能只靠单次 heartbeat。
- 被动降级链路：中心 C2 失效 -> 固定系留或机动高空二级侦察节点/地面备份 -> 完全无中心 CBBA。
- 主动降级仲裁：中心未失效时只输出继续中心、请求中心重分配、请求二级观测辅助或安全保持；`degrade_to_secondary/degrade_to_distributed` 只属于中心失效后的被动接管链路。
- 中心重规划请求生命周期：包顶层导出冻结 DTO `CenterReplanStatus` 和 `build_center_replan_risk_signature()`；`D4ArbitrationAdapter.evaluate(center_replan_status=...)` 只读消费 `pending|applied|acknowledged_no_change|expired`。`ActiveDegradationConfig.center_replan_cooldown_s` 默认 2.0 秒，以 `resolved_at`、pending 无 resolved 时以 `requested_at` 为起点；窗口内新增非硬风险继续 `continue_center`，在严格 `timestamp >= reference+cooldown` 边界才重新开放请求。若 pending 属于 current coalition，且中心 alive、D3 plan/coalition 双版本 current、D5 全部 current primary 已稳定 locked 并形成无冲突 consensus，D4 将旧请求收敛为 `continue_center`，输出 `center_replan_resolution_hint=acknowledged_no_change`。friend/duplicate/wrong-binding、plan/coalition version、center health、coalition conflict 或 commit 缺 ACK 均优先 fail closed，不会被 recovery 覆盖。该 `continue_center` 保留风险 evidence，不替代 D5/D7 独立门控。
- 二级节点建模：支持 `NodeRole.SECONDARY_RECON`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`、`FIXED_TETHERED_SECONDARY` 或 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；二级节点默认 `coordinator_only`，只做协调和侦察证据，不作为拦截执行资源。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、lease、coverage、cue/gimbal/link、network full-view、stable/not-registered 计数及其 `registration_evidence_source`/presence 标志，并区分节点类型与 `not_ready|visible_only|registration_usable|takeover_ready` 四级瞬时 readiness。heartbeat/current time、cue、gimbal、communication summary 或 network full-view 缺失均不能达到 `takeover_ready`。adapter 进一步记录 `takeover_ready_consecutive_decisions`、ready since/duration、required decisions/duration、`takeover_ready_sustained` 和回落原因，供 D4 仲裁与 D6 逐决策审计。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size`、`risk_window_threshold` 和 `center_replan_cooldown_s`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。adapter 同时输出 hard/soft risk 拆分、center replan cooldown 状态和 `active_degradation_false_trigger_candidate`，供 D6 统计误触发。
- D2 在线指标可用性：`AssociationRiskSummary` 显式携带 `truth_metrics_available`、`continuity_available` 和连续 `duplicate_track_risk`。在线 truth 隔离时，IDSW/continuity 的数值占位不参与主动降级；`duplicate_track_risk >= 0.5` 只产生 soft `d2_duplicate_track_risk_high` 观察证据，不再合成 observed count。只有显式 `duplicate_track_count/duplicate_assignment_count`、对应 delta/delta sum 或明确 observed flag 才产生 hard `d2_duplicate_track_observed` 并立即阻断。
- D5 末端证据适用性：`TerminalAssociationSummary.terminal_evidence_applicable` 显式表示当前是否已进入末端视觉适用窗口，默认 `true` 保持旧调用兼容。窗口外不消费低 confidence、高 ambiguity、cross-view 软风险或连续非锁定/无明确观测的 mismatch streak；friend conflict、duplicate lock、resource/assigned-track mismatch 和明确 observed-track mismatch 仍保持硬门控。adapter 兼容 `evidence_applicable`、`visual_evidence_applicable`、`within_terminal_visual_window` 和 `terminal_visual_window_active` 别名，并将最终值写入 D6 event metadata。
- M-to-N 原子联盟安全语义：`CoalitionSafetyEvidence` 以 duck typing/dict 消费 D3 `assignment_plan_v2` 的 `coalitions`、member、plan/coalition version、`required_resource_count` 和可选 commit。有效 secondary/distributed commit 必须满足完整 required-member ACK、双版本、epoch、成员、lease 和 digest 门控，随后才设置 `atomic_coalition_formed=true`；无有效 commit 时仍按中心可用性输出 `request_center_replan` 或 `coalition_fallback_unsupported`/`hold_or_revoke`。event 记录 `candidate_action`、`gated_action` 和 commit 审计；single-winner CBBA 不冒充 `k>1` 成员形成。合法联盟内多个已授权资源锁定同一 `global_track_id` 不算 duplicate；联盟外、超额、旧 plan 或旧 coalition version 均 fail closed。D4 不改写 `global_track_id`。
- D5 current-coalition recovery 最小接口：`cross_view_summary` 需提供 `global_track_id`、`plan_id/plan_version`、`coalition_id/coalition_version`、`primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`coalition_visual_consensus` 和 `coalition_conflict_state`；若 `coalition_commit_required=true`，还需 commit state、required/acked member IDs、valid 和 conflict reasons。字段缺失、scope 不 current 或 commit 不完整只会使 recovery 不成立。main 当前已传递该 D5 summary，D4 无需也不会修改 main adapter。
- D5 二级覆盖/转换漏斗诊断：adapter 可消费 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap` 和 `secondary_detect_to_cross_view_reject_reasons`；当二级检测可见但 cross-view/global binding/registration 未完成时，event metadata 写入 `secondary_detect_available_but_not_registered`、计数和诊断原因，但不会把该证据直接升级为 `secondary_plan_active`。
- 二级侦察校准解释口径：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不做像素投影或视觉注册。硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；瞬时 `takeover_ready` 还必须通过默认 3 个不同时间戳决策、至少 0.2 s 驻留且相邻证据间隔不超过 1.0 s 的 `SecondaryReadinessWindowConfig`，才允许进入 pending。相同时间戳的多资源/多目标决策不会重复累计。
- 完全无中心视觉证据接入：`DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()` 和 `merge_distributed_visual_evidence_into_tracks()` 可用 duck typing/dict 消费 D5 的 distributed terminal association / cross-peer hypothesis，不导入 D5 类型，也不创建或改写 `global_track_id`。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，除既有风险、review、coverage 和 capability 字段外，新增逐决策注册证据来源/presence、readiness streak/duration/sustained、`previous_state/transition`、pending since、activated at、activation delay 和 `secondary_takeover_fallback_reason`。
- 二级接管 plan metadata：`SecondaryTakeoverPlanMetadata` 明确 `not_applicable`、`pending_secondary_plan`、`secondary_plan_active` 三种状态。active 必须同时满足持续 readiness exact-true、expected/actual source 均存在且与选中二级节点一致、plan version 严格更新或保持同一已激活 secondary plan、plan/required lease epoch 均存在且前者不低于后者，并能证明 `current_time < lease_expiry`。任一字段缺失、`current_time == lease_expiry`、过期、旧 epoch 或 source mismatch 均保持 pending/not executable；已激活 secondary owner 也重新校验。D4 只输出合同和审计，不生成完整系统级 `AssignmentPlan`。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线；D5 视觉支持会提高对应资源出价，`hold`、友方冲突、过期/缺失/冲突 `global_track_id` 会阻止可执行出价，重复锁定风险进入 `assignment_audit` 且不允许多个 owner。
- CBBA gap benchmark：`build_cbba_cost_gap_benchmark()` 使用 D3/main 提供的中心 plan 与 cost matrix，计算 D4 CBBA 相对中心 Hungarian/Min Cost Flow 基线的 cost/completion/conflict/message 差距；D4 不在 no-center 路径运行虚拟中心 Hungarian。
- P2 隔离联盟 replay：`run_p2_coalition_fault_replay()` 复用原生 `CoalitionCommitCoordinator`，并将 `CBBANegotiator` 限定为协调者/补位候选选择，不把 single-winner 结果冒充 `k>1` 原子联盟。固定覆盖中心 -> 二级 -> 完全分布式、missing ACK、stale epoch、expired lease、partition、member loss/replacement，逐场景输出收敛轮数、完成率、冲突和最优差距或 `unavailable_reason`。MIT CBBA/CA-CBBA 只通过 `ExternalCoalitionReplayAdapter` 返回 path/source/capability/unavailable 审计，不替换在线 D4。
- P1 通信故障 replay：`run_p1_communication_fault_matrix()` 接收任意长度的 member/secondary 列表和 seed 集合，固定输出 `normal`、0.5 s delay、30% loss、center failure、center+secondary failure、partition+recovery 六类逐 seed 记录。记录包含层级轨迹、owner/plan/coalition version、ACK/lease/epoch、首个失败原因、消息统计、节点退出/重构、重复 owner 和 split-brain prevention；乱序旧 version ACK 被拒绝但不阻塞后续有效全量 ACK，分区恢复必须提升 generation 并全员重新 ACK。
- AirSim episode 通信接口：`AirSimEpisodeCommunicationAdapter.tick()` 读取 main 提供的单调仿真时间、中心/二级 heartbeat、消息延迟、ACK 丢弃、partition、digest 和恢复授权，逐 tick 输出 heartbeat/message/ACK、lease、epoch、owner、plan/coalition version、plan transition、commit 和恢复状态。接管收集 ACK 期间无可执行 owner；只有全部 required member ACK、lease 有效且 commit=`executing` 才发布单一 fallback owner。取消 primary 同时到达要求不会取消多成员原子授权。中心恢复必须连续通过双轨 digest 校验并取得显式授权，不因 heartbeat 恢复立即夺权。规范 episode-time 矩阵 7/7 通过：normal 误降级为 0，中心故障到二级可执行 1.25 s，二级故障到 peer 原子执行 1.00 s；missing ACK、stale epoch、expired lease 和 partition 均 fail closed。上述数字是 0.25 s tick 的逻辑故障注入结果，不是 RF/真实网络时延。
- D6 CBBA report metadata：`build_cbba_d6_metadata()` 将 `CBBAResult`、`coordination_mode`、`assignment_audit` 和可选 `CBBACostGapBenchmark` 归一化为多 seed 可聚合字段；`run_failover_simulation()` 顶层 metrics 透出 `d4_action`、`coordination_mode`、`selected_coordinator`、leader 和 coverage。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

## 主动降级入口

`ActiveDegradationArbiter` 接收 D1 定位不确定度、D2 关联风险、D3 分配有效性、D5 末端视觉关联摘要、`C2Health` 和二级节点健康状态，输出 `ActiveDegradationDecision`。典型策略：

- D5 与分配目标一致且风险低：`continue_center`。
- D1/D2 风险升高但 D5 仍一致：优先 `request_secondary_assist`。
- D3 分配 `is_current=False` 或 `plan_age_s` stale 属于硬风险，D5 仍一致时优先 `request_center_replan`；`plan_age_s` 表示计划活性年龄，优先以 `plan.metadata.last_evaluated_at_s`（兼容 `last_evaluated_at/evaluated_at_s/evaluated_at`）为参考，缺失时才回退 `created_at`。稳定 plan ID 的身份年龄保留在证据 `metadata.identity_age_s`，不会把每帧已重新评估的稳定计划误判为 stale。`d3_assignment_cost_margin_low` 属于软证据，单独出现时只继续观察或请求二级 cue，不触发每帧重规划。
- 未进入末端视觉适用窗口时，D5 普通 `ambiguous/hold/reacquire`、低 confidence、高 ambiguity、cross-view 软风险和 non-locked streak 不参与主动辅助/重规划判定；D1/D2/D3 风险低且中心 binding 有效时直接 `continue_center`。
- 已进入末端视觉适用窗口后，D5 多帧 `ambiguous/hold/reacquire` 但没有 observed global track mismatch、资源错配、重复锁定或友方冲突时，不视为分配失效：有二级覆盖则 `request_secondary_assist`，否则 `continue_center` 并继续观察。
- D5 持续 observed global-track mismatch、资源错配、重复锁定，或 D3 plan stale/not-current、显式 `resource_feasible=False` 时，中心可用路径只输出 `request_center_replan`；friend conflict 仍 `hold_for_review`。单窗口 observed mismatch 继续受 `mismatch_frame_limit/risk_window` 防抖。
- D5 `friend_conflict=True`：强制 `hold_for_review`；`duplicate_terminal_lock=True` 不视为一致锁定。
- 二级辅助/接管必须显式提供通信摘要，并证明存在未过期的 `secondary_relay`、`video_cue` 或 `c2_direct` 链路；缺通信证据不是“跳过检查”，而是 fail-closed。
- 若二级节点 `heartbeat_timestamp_s` 超过 `heartbeat_stale_after_s`，即使视频链路摘要新鲜，也不会被选为二级接管目标。
- 机动高空侦察节点随拦截机出动但不拦截；它用 D1/D2 `GlobalTrack` 或雷达 cue 指向目标簇，中心可用时只给局部拦截群提供图像/cross-view 辅助，保持中心 plan owner/version。只有中心失效后，持续 `takeover_ready` 才允许它成为二级协调节点。仅有侦察图像、云台指向正常或 coverage ratio > 0 不会自动改变 action；event 用 `secondary_assist_requested` 与 `secondary_takeover_candidate` 分别审计辅助和接管。
- 当中心和二级节点都不可用时，D4 使用 D5 分布式视觉证据作为 CBBA 的风险/代价输入：多资源视觉支持只增加对应资源的出价，不构造“虚拟中心”，也不重新绑定 `global_track_id`。
- `--drone-count`/main runtime 的 N 只决定输入摘要数量；D4 按实际 `TrackSummary[]`、`ResourceSummary[]` 和二级节点列表长度运行，不在仲裁里固定 2v2 或 5v5。
- 2v2/5v5 AirSim ComputerVision 专项 case 只作为测试 baseline：中心可用且硬绑定失效时应 `request_center_replan`；中心 failed 且二级持续 ready 时才允许 secondary pending/active；中心和二级均不可用、证据不持续或 lease 过期时才进入 distributed。

## P0-B 状态

- 已完成：heartbeat smoothing 使用滑动窗口、miss threshold 和 `degraded/suspect/failed` dwell，短时丢包/延迟不会直接进入 `failed`。
- 已完成：secondary resource、takeover plan、active owner 和 D7 handoff 统一按严格 `current_time < lease_expiry` 校验。公开 helper 对 readiness、expected/actual source、plan/required lease epoch、expiry/current time 的 `None` 分别输出稳定 reject reason；当前 secondary-owned 同 id/version 计划只有在全套证据仍有效时才可维持 active。D7 handoff 还必须看到 `secondary_capability_class=takeover_ready`；distributed action 直接走自身 ACK/lease/epoch/commit 合同，不进入该视觉门。
- 已完成：二级能力评分区分 `not_ready`、`visible_only`、`registration_usable` 和 `takeover_ready`，并消费 coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、stable registration count、not-registered count 和 reject reason；只有 `takeover_ready` 会成为接管依据。
- 已完成：adapter 在瞬时门限之后增加连续 readiness 窗口；单帧或同时间戳重复的 `takeover_ready` 不会进入 pending，heartbeat/link/cue/gimbal/lease 或能力回落会清零 streak 并阻断接管。`not_ready -> takeover_ready` 边沿会重新初始化 `ready_since_s` 和 count=1，能力回落后再次 ready 也从新窗口计时。
- 已完成：主动降级继续保留 hard/soft risk、防抖和 release 条件；`terminal_consistent` 只表示 current plan 的 resource/global-track/version/coalition binding 是否仍可信。`terminal_evidence_applicable=false` 且中心正常时，低置信度、歧义、cross-view 软风险、连续非锁定/无明确观测的 mismatch streak，以及 D1/D2/D3 的非 hard-active 风险组合只保留审计，不触发二级视觉辅助；进入适用窗口后才按既有策略请求 cue。高位置/协方差不确定度、陈旧量测、observed IDSW/duplicate track、低 continuity、not-current/stale/resource infeasible、friend/duplicate terminal lock 和明确 binding mismatch 仍执行原强门控。该字段不能单独授权 terminal PNG。
- 已完成：`AssignmentValiditySummary.resource_feasible` 默认向后兼容为 true；adapter 可从 assignment/plan 字段或 metadata 读取显式可行性。不可行资源、stale/not-current plan、重复末端锁、资源/计划绑定错配和持续 global-track mismatch 在中心可用时统一请求中心重规划，不因二级 readiness 高而转移 owner。
- 2026-07-12 posefix smoke 审计：四组历史输出中分别有 1087/1094/585/1064 条 `terminal_consistent=false` 同时满足中心 owner、coalition safe 和 hard risk 为空，导致 control CSV 出现 158/112/113/122 条 `d4_terminal_inconsistent` 拒绝。根因是 D4 重复解释 D5 readiness，并由单一有状态 arbiter 跨 resource/track 共享迟滞。adapter 现按 `(resource_id, global_track_id)` 隔离状态，event 新增 `terminal_binding_reject_reasons`、`terminal_visual_state` 和 `arbitration_state_key`；旧 plan/coalition version、缺 ACK、过期 lease 继续 fail closed。历史日志不回写，需 main 重跑 AirSim 生成修复后系统证据。
- 已完成：D2 online truth 隔离语义已接入 D4；`truth_metrics_available=False`/`continuity_available=False` 时不再把 `id_switch_count` 或 `track_continuity=0` 占位解释为硬风险，在线 ambiguity/duplicate/quality 风险路径保持有效。

## P1 状态

- P1 联盟合同结论仍以 `p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md` 为准：D4 所属合同层已闭合。2026-07-12 PNG delivery 的 M5N2 `0/9` 是历史短窗口结果；2026-07-15 已完成中心继续执行的 baseline/candidate 各 10 seeds，最新同口径负对照为 coalition `0/20`、第二 primary 5 m `0/20`、`active degradation=0`。该更新不关闭 D4 物理协同、真实 fallback 扰动、成员重构/恢复或误降级标定缺口。
- `d4_p1_failover_disturbance_replay_v1` 已形成版本化九场景矩阵：正常中心无误降级、二级完整 ACK 接管、缺 ACK、手工预编排的成员丢失/替换、分区/恢复、旧 epoch、过期 lease、digest conflict 和中心恢复双轨审计均通过。replay 中替换后的联盟必须提升 epoch/plan/coalition version 并全员重新 ACK；这不代表在线 D4 已实现自主 reserve 发现、激活、缩编、补位或整盟重组。中心恢复不立即夺权，D4 不生成 `AssignmentPlan`，不降低 D3/D5/D7 gate。
- `d4_p1_communication_fault_replay_v1` 已完成 10 seeds x 6 场景的 60/60 安全结果：正常中心误降级为 0；0.5 s 延迟 10/10 完整提交；30% 丢包下 3/10 完整 ACK 后执行、7/10 缺 ACK 后 fail-closed；中心失效 10/10 降到二级，中心和二级连续失效 10/10 降到 distributed；分区恢复 10/10 使用新 epoch/version 全量 re-ACK，并拒绝旧 owner。重复 owner 和 split-brain prevention failure 均为 0。
- 2026-07-20 当前 D4 全量测试为 335/335 项通过；其中 23 项区域 authority 合同测试覆盖五档 region/task/resource 元数据及原子/fencing 边界，新增 32 项区域资源建议测试覆盖 3/5/8/32 变长图、守恒、断边/分区、中心/多二级/distributed owner、旧 epoch/过期 lease/缺 ACK/fault fence、BC、PPO、bundle SHA、OOD/timeout/低置信/非有限回退和 shadow 不改正式 verdict。2026-07-15 的 280/280、区域合同阶段 303/303 和更早 278/278 保留为历史证据。未运行新 AirSim episode；真实链路、学习模型 20 个未见 seed 验收、误降级率、恢复时间和物理任务连续性仍开放。
- 二级接管正例：协调者 `Secondary_Recon_1`，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_secondary`。
- 完全分布式正例：协调者为 `INT-02` peer，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_distributed`。
- 缺 ACK 负例：ACK 2/3，最终 `aborted`；T001 三个成员保持 `hold_for_review`，D7 许可为 0。该结果确认 fail-closed；有有效 commit 的二级/分布式路径已获正例验证。
- SimpleFlight 15 s 结果仅用于断点诊断：30 个 active pair 物理命中为 0，不能据此宣称 D4 fallback 或系统物理拦截闭环完成。
- 仍开放：将已冻结的 P1 扰动合同映射到真实 AirSim 同 seed 成对试验，完成 heartbeat/link/cue/gimbal/source、secondary-interceptor/peer split、误降级、恢复时间及物理连续性多 seed 统计。模块 replay 不等于系统矩阵验收完成。
- P2 只允许隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或其他 adapter 不替换当前轻量 CBBA 和 ACK/lease/epoch 合同。
- P2 原生确定性 replay 已收敛：6/6 场景符合预期安全结果；中心 -> 二级 -> 分布式和手工预编排的 member-loss/replacement 场景均以 7 轮、完成率 1.0、冲突 2/1、最优绝对差距 0.0 收敛。该结果只验证调用方给定替换成员后的版本/ACK 合同，不是自主补位能力。missing ACK、stale epoch、expired lease、partition 分别以 2/1/2/3 轮 fail closed，完成率均为 0，并输出对应 optimality-gap unavailable reason。
- 默认环境未配置 MIT CBBA 或 CA-CBBA 参考路径，因此各 6 个外部对照行分别输出 `mit_cbba_reference_path_not_configured`、`ca_cbba_reference_path_not_configured`。MIT MATLAB 源码树即使被检测到也报告 runtime adapter 未集成；已审计的 CA-CBBA 公共仓库没有可执行源码。上述 unavailable 是 capability 结论，不是外部算法性能结论。

历史基线：2026-07-10 calibration sweep 和 2026-07-11 早期 truth-isolated smoke 曾因 network full-view/readiness 不持续而未形成二级 active plan。该结论只描述实施前场景，不再作为当前能力状态；门限与 fail-closed 规则仍保留。
