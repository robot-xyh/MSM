# D4 分布式协同与降级接管计划

## 0. 2026-07-20 scalable3d 区域化合同（模块内已完成）

### 当前集成与区域资源建议增量

- main-owned scalable 3D 质点模块栈现已消费区域 D4 verdict：单一二级接管、两个二级节点的多区域 owner、中心与二级连续失效后的 distributed D3 plan 均已接线。D7 只在 owner/node、plan version、epoch、lease、commit mode 和 fault generation 全部 current 时恢复导引；本轮定向运行 `test_module_stack.py` 为 8/8 passed。该证据不属于 AirSim、真实网络或硬件验证。
- D4 新增可选全局区域资源建议层。`RegionResourceSnapshot` 只携带区域聚合需求/高威胁积压、D1/D2 不确定性、D5 可见/一致性、可用/备用资源、二级覆盖/就绪、通信容量/时延/丢包和当前 owner/version/lease；区域边携带 transferable capacity、距离/时间、带宽和 partition，不含 actor truth ID 或具体目标身份。
- 动作域只含区域配额增减、相邻区域转移、备用比例、侦察优先级和 hold/replan，不生成 resource-target assignment。确定性投影重新计算配额变化并硬性保证总资源守恒、只走可通信/可机动邻边、最低备用、当前 owner/epoch/lease、fault fence 和已提交联盟资源不被破坏。
- `d4-region-resource-advisory-v1` 将 projected recommendation 固化为 main 可在下一轮 D3 规划边界重验的只读合同。内容寻址 `advisory_id` 是一次性消费键；默认 TTL 1.0 episode-clock 秒并收缩到最早 authority lease。顶层携带 scenario/snapshot/authority、创建时间、source plan 集合、policy/model/projector identity；逐区域和 transfer 携带 source snapshot/plan/epoch/lease、owner、ACK/fault、资源前后/protected reserve/committed 以及 edge 端点/capacity。
- `validate_for_consumption()`/`RegionResourceAdvisoryGate` 对 current snapshot 再执行 fail-closed 校验。旧 snapshot/plan/epoch、严格到期 lease、非 projected、ACK 不完整、fault fence、总 quota 不守恒、未知/非邻接/不可用/超 capacity transfer 或 advisory 重放均为 `consumable=false`。该布尔值只表示可作为下一轮规划输入，不发布或修改 D3 plan，也不授权 D7。
- 研究管线包含规则基线、共享节点/边网络的变长区域图 actor-critic、行为克隆、原生 clipped PPO、包含 SHA256 的 manifest + `state_dict` bundle、完整 episode/数值 seed 原子划分和 paired shadow evaluator。reward 显式惩罚高威胁积压、跨区转移耗时、通信负载、备用不足、分配冲突、降级失败和计划抖动。
- 默认 API 为 `disabled`，CLI 为 `shadow`。超时、低置信、OOD、非有限、版本/SHA 不匹配均回退规则建议；规则 fallback 与学习候选必须通过同一 `DeterministicResourceProjector` 实例，学习模型只允许返回 raw proposal。少于 20 个未见 seed 不得进入 assist。正式 D4 健康检测、leader 选择、epoch/lease fencing、联盟 ACK/commit、D3 assignment 与 D7 gate 不受学习层替代。
- 新增 `d4-region-learning-dataset-v1`：source 固化 scenario/version/scale、seed、episode ID、Git commit/dirty 和 config SHA；frame 固化 snapshot、`rule|formal|unavailable` target、reward/unavailable 与可选 recommendation。训练 target 由固定 projector 重验 authority generation、lease、reserve、edge 和 quota 证明；manifest 重验 canonical episode inventory、availability 和可重放 split。stage 只发布完整 episode，同一数值 seed 的所有场景/规模/episode 必须同 split。BC/PPO loader 默认拒绝 dirty、缺 target/reward，`d4-region-resource-model-bundle-v2` 可嵌入数据 manifest。
- 新增 `d4-canonical-region-seed-split-view-v1`：D4 独立校验 main-owned shared registry 和源 training-seed-registry，不导入 main runtime；原 dataset 保持 70/15/15 且只读，显式 BC 视图采用 D3 兼容 60/20/20。视图绑定 dataset/split/registry/source SHA，漏 seed、多 seed、保留 seed、策略或哈希不一致全部失败关闭。
- 2026-07-21 当前验收：建议/消费/学习准入 `test_region_resource_advisor.py` 为 51/51，数据合同与正式训练回归为 15/15，共享切分专项为 12/12，动作覆盖课程专项为 6/6，D4 全量 387/387；此前 main-owned scalable 3D 定向集成为 8/8，阈值均为零失败。历史合同阶段数字保留在实验报告，不再作为当前计数。
- 2026-07-20 正式数据与开发训练：只读审计 900 episode/1798 frame，逐 episode SHA、dataset/source/schema、70/15/15 seed 原子 split 和 1000-1019 外部保留 seed 隔离均通过。2026-07-21 按固定 seed 复跑行为克隆，完成 66 epoch，最佳 epoch 54，内部测试 loss `0.071545`、CPU 推理 P95 `0.7774 ms`、权重 SHA256 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，与首次权重哈希一致。正式标签的 14384 个区域动作中 nonzero quota、transfer、hold、request_replan 均为 0；D6 审计还确认 898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle 机器准入固定 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false`、`development/shadow-only`。行为克隆管线可用，但低损失不能作为完整动作策略能力，PPO 和 assist 均不可用。权重保存在 ignored `outputs/`，tracked 结果不含模型文件。
- 2026-07-21 已完成独立动作覆盖补充课程 producer。课程按输入区域数和资源总数运行，每个共享训练 seed 生成 hold、request-replan、transfer 三帧，并在新输出目录中形成 dataset-v1 与只读 canonical view；正式 900 episode 目录不写入。本次 100 seed/300 frame 的动作计数为 hold 100、request-replan 200、非零 quota 200、transfer 100，三个 60/20/20 桶均有正类，硬约束和真值泄漏为 0。reward/outcome 统一 unavailable，PPO 与 assist 不开放。实际开发制品因并行 dirty worktree 不能直接训练；main 合并后须 clean 重生，再决定与正式数据的采样比例并运行外部 1000-1019 paired shadow。

- `regional_failover.py` 新增 `RegionalScenarioMetadata`、`RegionDefinition`、`RegionalTaskEvidence`、`MobileReconSecondary`、`RegionalFallbackMember`、`RegionOwnershipMetadata` 和 `RegionalFailoverCoordinator`，不导入 main-owned `scalable_3d_simulation`，通过 mapping/`to_dict()` 只读适配 `scalable3d-scenario-v1`。
- 每个区域最多一个 active authority。中心 health 未进入 `failed` 时始终保留中心 owner；D1/D2/D3/D5 风险只改变 `continue_center|request_secondary_assist|request_center_replan|hold_for_review`，不把主动降级变成所有权转移。
- 中心 `failed` 后，逐区域只从显式 coverage 且 strict readiness 完整的 `mobile_high_recon` 中选择二级协调者；排序为 takeover priority、coverage ratio、lease epoch、node id。二级节点保持 `coordinator_only`，不作为拦截成员。
- 没有有效二级节点时才执行受约束 bid fallback：按 region、availability、communication、operator hold、跨区域 capacity、capability demand 和 D5 support/hold/ambiguity 形成确定性候选成员集；一个成员可同时覆盖多项 capability。该实现是可审计保底 heuristic，不是完整 CBBA 消息共识、CCBBA、reserve 激活或动态联盟重构。
- authority 切换必须同时提升 `epoch` 和 `plan_version`；租约严格满足 `timestamp < expiry`，并收缩到 authority、D3 task 与二级 lease 的最早 expiry。中心、二级和 distributed 三层的 `k>1` 任务均复用 `CoalitionCommitCoordinator`，只有 required-member ACK 全集对同一 target/coalition/plan/version/epoch 有效时才原子 `committed`；缺 ACK、旧 ACK/authority generation、过期 lease 和任一层级分区全部 fail closed。
- 2026-07-20 区域合同阶段新增 23 项确定性单元测试：5/20/50/100/200 个 region/task/resource 元数据与中心 ownership，声明 resource/recon 数量上限，D1/D2 主动证据、D3/D5 硬门控、中心失效、二级失效、双区域 coverage、中心/二级/distributed 完整与缺失 ACK、旧 ACK epoch、全层网络分区、旧 authority epoch/plan version、最早 task/authority lease、旧 secondary lease epoch、D5 member hold、单成员多能力与跨区域 capacity。当时 D4 全量为 303/303，当前已由 **387/387 passed** 覆盖。
- 验证边界：23 项合同用例本身无随机 seed、AirSim episode、真实 RF/mesh/socket、带宽/时钟漂移或物理命中证据。main 后续已完成质点模块栈接线，但这不把合同单元测试升级为 AirSim/真实网络证据；根级系统文档仍由 main 同步。

### 0.1 2026-07-15 P0 公开二级接管入口统一（已完成）

- 抽取 `SecondaryReadinessEvidence`/`assess_secondary_readiness()`，统一 coordinator election、episode communication 和 secondary coalition proposal；旧式裸 `takeover_ready=true` 不再授权接管。
- 二级 owner 必须证明显式 current time、正 lease epoch、严格 `current_time < lease_expiry`、fresh heartbeat/cue/communication、gimbal=true、coverage >= 0.65、network full-view >= 0.80，以及至少 3 次/0.2 s 的 sustained readiness。缺失、陈旧、等于 expiry 或低于门限均阻断二级 proposal/execution。
- `FailoverCoordinator.plan_degraded()` 只对 secondary candidate 应用该门；interceptor/cluster-representative peer 的 distributed election 保持独立，不要求二级视觉 evidence。动态 N/M、plan/coalition version、epoch/lease、ACK、partition/recovery 和 upstream `global_track_id` 合同不变。
- 278/278 历史回归未覆盖 `build_d7_secondary_handoff()` 和 `build_secondary_takeover_plan_metadata()` 对 sustained/source/lease epoch 的 `None`，此前“所有公开入口已闭锁”的说法撤回。两个 helper 现要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格未过期；同一已激活 plan 的维持路径不豁免。
- 当日验收结果：D4 全量 280/280 passed，两个 helper 的逐字段 `None`、完整正例、same-plan 维持和 distributed bypass 均通过；`build_coalition_commit_d6_metadata()` 缺 current time 时仍 lease invalid/atomic false。该历史结果先由 303/303、再由当前 387/387 回归取代；P0 判定不变。

### 0.2 2026-07-15 M5N2 中心负对照（已完成，非降级验收）

- 已完成真实 AirSim M5N2 baseline/candidate 各 10 seeds，共 20/20 case；该批 `active degradation=0`，中心 owner 持续有效。
- 验收口径分层：中心负对照要求 `active degradation=0` 且 center owner 保持 current，本批满足；物理闭环要求第二 primary 进入 5 m 且 coalition 完成，本批未满足；secondary/distributed 因未执行而为 unavailable，不能补零或判定通过。
- 结果为 coalition completion `0/20`、第二 primary 进入 5 m `0/20`，且 20 个第二 primary 均为 `collision_stop`。碰撞对象未写盘，因此当前只记录现象，不推断成员冲突、环境碰撞或状态异常。
- 该批验证了中心负对照没有误触发主动降级，但没有执行 secondary takeover 或 distributed commit，不能用于关闭真实二级/完全分布式多 seed P1。
- 物理失败本身不触发主动降级。后续仲裁继续要求 D1 协方差/时效、D2 关联风险、D3 当前计划/版本/资源可行性和 D5 current `global_track_id` 绑定、身份冲突及跨视角一致性形成可审计证据。
- D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`；本批系统实时预算超限的主要瓶颈不在 D4 仲裁。
- `png_ttc_2v2_seed001` 是终止生效前额外完成的单 case，排除在 M5N2 聚合之外；dropout case 为 0，不补零、不作趋势结论。

## 1. 范围与安全边界

D4 只负责 C-UAS 工作流中的离线科研仿真、降级仲裁、二级节点接管建模、完全无中心保底协商和评估日志。模块输入是粗粒度摘要，通信只使用内存网络或 main/runtime 提供的链路摘要；模块不拥有真实 AirSim episode 调度、真实通信链路、视频帧传输、飞控接口、硬件驱动、火控参数、毁伤模型、自动处置或授权绕过逻辑。

中心 C2 正常时，D3 仍是中心化分配的权威来源，`global_track_id` 仍由中心/上游航迹体系拥有。D4 在任何模式下都不得创建、改写或本地重绑定 `global_track_id`，只能复制上游 ID 做一致性检查、风险加权和审计。

## 2. 工程问题

中心节点正常时，系统依赖 D1/D2 的融合航迹、D3 的版本化 `AssignmentPlan`、D5 的末端视觉关联和 D6 的评估日志。当中心节点失效或局部分配证据不可信时，D4 需要回答以下问题：

- 如何区分中心真的失效的被动降级，与中心仍在线但计划风险升高的主动降级。
- 如何在中心失效后优先选择地面备份、固定系留或机动高空二级侦察节点，而不是直接进入完全无中心协商。
- 二级节点不可用时，如何使用轻量 CBBA 保底维持连续性，同时避免重复 owner、过期 ID、友方冲突和不收敛计划被发布。
- D1 不确定度、D2 关联风险、D3 plan/version/freshness 和 D5 terminal/cross-view 证据如何统一成 D4 仲裁动作。
- D5 distributed visual evidence 如何在完全无中心模式下影响 CBBA 出价，而不是构造虚拟中心或重新绑定 `global_track_id`。
- 中心恢复时如何通过双轨合并避免短暂 heartbeat 恢复导致双主。
- D4 输出如何进入 D6 event metadata 和后续 main runtime bus。
- 如何把 scalable3d 的动态 resource/recon/region/target 数量映射为逐区域唯一 authority，并在区域之间隔离 coverage、generation、lease 和 coalition commit。
- 如何在不触碰具体 resource-target assignment 和正式降级裁决的前提下，学习全局区域配额/邻区转移建议，并让任何模型失败都安全回退确定性规则。

## 3. 当前总体状态

D4 所属的 P1 合同层已闭合。最新 2026-07-11 验证中，ComputerVision 总体验收为 8/10；二级协调者 `Secondary_Recon_1` 与完全分布式 `INT-02` peer 均以 required-member ACK 3/3 进入 `executing`，分别输出 `degrade_to_secondary` 和 `degrade_to_distributed`；缺 ACK 场景以 2/3 ACK 进入 `aborted`，三个 T001 成员均 `hold_for_review`，确认 fail-closed。当前不再把 secondary/distributed 正例写成 unsupported 或未闭合。

状态必须按层级解释：

| 层级 | 当前状态 | 不得外推为 |
|---|---|---|
| P0 secondary evidence/lease fail-closed | **2026-07-15 已关闭**：280/280 回归覆盖 coordinator/episode/coalition/D6 及两个公开 plan helper；readiness/source/epoch/time 任一缺失均阻断，历史 278/278 过度声明已纠正 | 新 AirSim 网络证据或 P1 自主联盟重构 |
| scalable3d 区域 authority 与质点接线 | **已实现并接线到 main 质点模块栈**：模块合同覆盖 5/20/50/100/200 metadata；main 集成已覆盖单二级、多二级 owner 和连续失效后的 distributed D3 plan，D7 按 owner/epoch/lease/commit/fault fence 执行 | AirSim、真实网络、长时 200v200 多 seed、完整 CCBBA 或物理任务闭环 |
| 区域资源学习建议与消费合同 | **行为克隆开发模型已训练，仍为 shadow-only**：规则、确定性投影、版本化限时 advisory、一次性消费门、共享变长图 actor-critic、BC/PPO 接口、bundle/SHA、OOD/timeout 回退和 paired evaluator 均可运行；正式 900 episode 审计和 BC 已完成 | 14384 个标签动作没有 quota/transfer/hold/replan 正样本，D6 reward/causal/counterfactual 可用数均为 0，内部 test 仅 15 seed，外部 20 seed 未评估；bundle 明确禁止策略能力声明，不得 PPO/assist，也不具有裁决/assignment 权限 |
| D3/D4/D5 共享 seed 切分的 D4 消费端 | **已实现 development/data-governance 能力**：严格消费 source-external registry，正式 900 episode 已只读映射为 60/20/20 seed；BC 可显式选用 canonical view，默认 70/15/15 不变 | 不代表 D3/D5 消费端已闭合，不代表联合模型已训练，也不改变 PPO/assist 准入 |
| P1 合同层 | **已完成**：secondary ACK 3/3 `executing`、peer ACK 3/3 `executing`、缺 ACK 2/3 `aborted`/`hold_for_review` 已有真实 ComputerVision 正负例 | 自主成员形成、完整重构或物理拦截 |
| P1 通信 replay | **D4 模块内已完成**：九场景合同 replay 加六场景、10-seed 内存通信矩阵，覆盖 0.5 s delay、30% loss、中心/二级连续失效、分区恢复、乱序旧版本和 split-brain 防护 | 真实 AirSim 网络时序或物理任务连续性 |
| P1 episode 时钟接口 | **D4 模块侧已完成并通过批量验收**：除 7 类规范合同 replay 外，2026-07-13 已完成六类、10-seed、60-case AirSim episode clock 故障注入；逐 case 保留 owner/version、ACK、epoch、lease 和恢复记录 | 该结果不是实际 RF、mesh、socket、带宽、时钟漂移或硬件网络验证 |
| P1 物理/长期标定 | **仍开放**：episode clock 故障注入已完成安全结果验收，但真实带宽限制、节点时钟漂移、乱序/抖动网络时序、secondary-interceptor/peer 链路和物理任务连续性仍未闭合 | 不能用 episode-time 注入替代真实网络或长时动力学验收 |
| D4 P2 isolated replay | **已实现原生故障 replay 和外部 capability adapter**：6/6 原生场景满足预期；MIT/CA-CBBA 默认输出 unavailable | 外部 MIT/CA-CBBA 已执行，或外部 unavailable 可用于性能比较 |

D4 的 P2 replay 只在显式 API/CLI 下隔离运行，不替换默认本地轻量 `CBBANegotiator`、原子 commit 或 ACK/lease/epoch 门控，也不添加默认依赖。当前原生 deterministic replay 覆盖旧 epoch、过期 lease、成员不可执行和调用方手工给定替换成员后的重新提交；它没有自主 reserve 发现、激活或补位状态机。2026-07-13 episode clock 矩阵关闭了六类、10-seed 的批量安全结果验收。上述结果仍属于合同回归/研究近似，P1 继续保留真实带宽、时钟漂移、网络排队/抖动/乱序/重传、实际 secondary-interceptor/peer 链路、缩编/整盟重构和长期恢复合并。

2026-07-12 新增独立于 P2 外部算法对照的 `d4_p1_failover_disturbance_replay_v1`。版本化 JSON 固定输出九个场景和逐阶段 epoch、plan/coalition version、required/acked/missing members、lease 与 execution gate。正常中心、二级完整接管、缺 ACK、手工预编排成员替换、分区恢复、旧 epoch、过期 lease、digest conflict 和中心恢复双轨审计为 9/9 通过；执行许可只在 `executing + full ACK + valid lease` 成立，替换和恢复必须新 generation 全量 re-ACK。该 replay 不选择 reserve，也不实现在线补位/缩编/重组；中心恢复只输出 dual-track review。

2026-07-12 在该冻结合同之上新增 `d4_p1_communication_fault_replay_v1`。`CommunicationReplayConfig` 由调用方传入任意数量的联盟成员和二级节点；批量 helper 默认可运行 10 seeds，逐 seed 输出六类通信场景、消息统计、层级/owner/version、ACK/lease/epoch、首个失败原因、退出/重构和 split-brain 诊断。当前 3 members、2 secondaries 的 60 个 case 全部满足安全预期：0.5 s delay 10/10 可执行，30% loss 中 7/10 因缺 ACK 保守阻断、3/10 完整 ACK 后执行，中心/二级层级和分区恢复均正确，重复 owner 为 0。该结果关闭 D4 内存通信 replay 缺口；2026-07-13 又完成同六类的 AirSim episode clock 批量安全验收。D6 长期趋势以及真实带宽、漂移和网络时序仍由 main/工程链路验证保持开放。

本轮进一步新增 `d4_airsim_episode_communication_v1` tick 合同和 `d4_p1_episode_fault_validation_matrix_v1` 验收输出。`AirSimEpisodeCommunicationAdapter` 不启动 AirSim，而是接受 main 的严格递增 episode timestamp 与通信证据，并返回逐 tick 的 heartbeat、message delay/drop、ACK、lease、epoch、owner、plan/coalition version、plan transition 和 recovery 状态。中心失效后优先二级，二级已执行后再次失效才选择 distributed coordinator；任一 fallback generation 在完整 required-member ACK 前都没有可执行 owner。7 个规范场景全部通过：normal false degradation=0；中心 heartbeat loss 注入到二级 executable 为 1.25 s，满足 <=1.5 s；二级 heartbeat loss 注入到 peer atomic executing 为 1.00 s，满足 <=2.5 s；missing ACK、stale epoch、expired lease 和 partition 均 fail closed。分区恢复继续要求新 generation 全量 re-ACK，中心恢复需双轨 digest 连续验证和显式授权。独立 primary 仅取消到达同步，原子成员授权不变。验收输出固定声明 `validation_scope=episode_time_fault_injection`、`real_rf_network_validated=false` 和 `real_hardware_validated=false`，不得把该结果解释为真实无线网络或硬件故障试验。

2026-07-13，main/runtime 又按 AirSim episode clock 对 `normal`、`center_failure`、`center_secondary_failure`、`delay_0_5s`、`loss_30pct` 和 `partition_recovery` 六类场景各运行 10 seeds，共 60 case。60/60 safety outcome 通过，`false_degradation_count=0`、`duplicate_owner_count=0`、`split_brain_prevention_failure_count=0`；30% loss 下 7 个缺 ACK case 保守阻断，只有 3 个完整 ACK case 执行。该批结果验证的是 episode 时间轴上的故障注入、顺序接管和安全门控，不包含真实 RF 功率、实际吞吐带宽、节点时钟漂移、操作系统/socket 排队、无线重传或硬件链路。

2026-07-11 P2 隔离 replay 结果：`center_secondary_distributed` 与 `member_loss_replacement` 均 7 轮收敛、完成率 1.0、冲突计数分别 2/1、相对隔离单槽最优基线的绝对差距均为 0.0；missing ACK、stale epoch、expired lease、partition 分别在 2/1/2/3 轮进入 `aborted|reconfiguring`，完成率 0，并给出 optimality-gap unavailable reason。原生 6 场景预期结果满足率 6/6，平均完成率 1/3，总冲突计数 5。MIT CBBA 与 CA-CBBA 未配置本地参考树，输出 path-not-configured capability/unavailable；探测到 MIT MATLAB 源码时仍因 runtime adapter 未集成而 unavailable，CA-CBBA 公共参考仅有 metadata 时报告无可执行源码。该结果不能解释为外部算法性能较差。

D4 模块内已经完成可测试的离线 P1 合同与 P0-B 降级层级硬化：`C2Health`、heartbeat smoothing、被动降级、固定系留/机动高空二级节点分类元数据、二级节点 lifecycle、二级能力评分与 `not_ready|visible_only|registration_usable|takeover_ready` readiness class、主动降级仲裁、主动降级硬/软风险分层、false-trigger metadata、secondary takeover plan lease/epoch strictness、主动降级 `necessary/unnecessary/inconclusive` review label、pre/post review window、plan activation delay、二级接管必要性/成功统计 metadata、D1/D2/D3/D5 adapter、D5 distributed visual evidence 归一化、完全无中心 CBBA 风险加权、CBBA cost gap benchmark helper、CBBA D6 report metadata、`assignment_audit`、D6-compatible event metadata、中心恢复基础合并和 N 规模输入均已存在。

2026-07-12 posefix smoke 进一步暴露 D4 terminal consistency 合同缺陷：四组历史 AirSim 输出中，`terminal_consistent=false` 且 hard risk 为空、中心 owner 与 coalition 均有效的记录分别为 1087/1094/585/1064 条，并在 control CSV 中造成 158/112/113/122 条 `d4_terminal_inconsistent` 拒绝。样本包括 D5 已 `locked` 但置信度低于 D4 自有阈值，以及无 ID/resource/version 冲突的持续 reacquire。修正后 `terminal_consistent` 只表示 D4 是否仍信任当前 plan binding；D5 confidence/ambiguity/lock/reacquire 只作为视觉准备度和 soft risk，超过 `non_locked_frame_limit` 可请求二级 cue，但不再单独破坏 binding。friend、duplicate、resource/global-track mismatch、历史 mismatch counter、not-current/stale plan、旧 plan/coalition version、缺 ACK 与过期 lease 仍立即 fail closed。adapter 的迟滞状态按 `(resource_id, global_track_id)` 隔离，避免某一 pair 的降级状态污染其他 pair。main 仍需逐 pair 同时消费 D4 action/binding 与 D5 lock gate，`terminal_consistent=true` 不能推导为 visual PNG ready。

2026-07-13 真实 2v2 又暴露“远距尚未进入视觉适用窗口却逐帧请求二级辅助”的语义缺口。D4 现增加 `terminal_evidence_applicable` 合同并默认 `true` 兼容已有输入；adapter 按 terminal association、D5 evidence、cross-view summary 顺序读取该字段及四个兼容别名，并写入决策记录。值为 false 且中心正常时，confidence、ambiguity、cross-view 软风险、streak 及仅由 `d2_association_ambiguity_medium + d2_duplicate_track_risk_high + d3_assignment_cost_margin_low` 等 D1/D2/D3 非 hard-active 因子组成的中段风险只保留审计，继续中心。高 D1 不确定度/陈旧量测、observed IDSW/duplicate、not-current/stale/resource infeasible、friend、duplicate terminal lock 和明确 binding mismatch 仍保持原强门控。值为 true 时继续执行既有末端 cue/replan 策略。

当前中心健康与 D5 持续 mismatch 的处置顺序固定为：中心健康且只是持续视觉软不一致时，先输出 `request_secondary_assist` 获取二级 cue，并保持现有中心 owner、plan id/version；当不一致形成明确硬失配或当前计划已不可继续时，输出 `request_center_replan`，仍不由 D4 直接转移 owner。只有 C2 健康状态进入 `failed` 才允许二级节点接管；二级节点随后失效或不可用才允许进入 distributed。secondary/distributed 任一 generation 均要求当前 epoch、有效 lease 和完整 required-member ACK，否则 fail closed。

2026-07-12 状态同步以 `PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md` 和 main GAP 为实测依据：D4 模块回归为 148 项通过；2v2 candidate 为 20/20 pair、锁定后两帧 dropout 为 2/2 物理成功，说明 D3/D4/D5/D7 门控主链未因本轮修正退化，但自然运行未触发 soft prediction/trend coast，因此不能把成功率归因于 D4 grace。M5N2 短窗口仍为 0/9，且受第二 primary 中段闭合、D5 hold/reacquire 和联盟视觉一致性共同约束；该结果不关闭 D4 的物理协同、完整扰动、成员重构/恢复或误降级标定缺口。

本轮除 terminal plan-binding 一致性语义、`d5_terminal_id_mismatch` 硬风险分类及对应审计外，P0 heartbeat smoothing、secondary readiness/source/lease/epoch、center-replan lifecycle、D2 truth 隔离和 P1 原子联盟 commit/ACK 行为均**无行为变化、保持原状态**。随后新增的 P1 replay 只编排现有合同并形成版本化扰动汇总，不修改 commit 算法：确定性扰动矩阵已完成，P1 物理/长期标定继续保持部分实现和开放状态。

### 实施现状与历史基线

历史基线（截至 2026-07-08）：main/runtime 完成 P1 基线接线；episode bus 已消费 D4 adapter 输出，`request_center_replan` 可触发 D3 新 plan version，secondary takeover owner/version 已回灌给 D3/D7，controlled 2v2 secondary visual PNG 回归已通过。main runtime 还新增了 P1 D4/D5 calibration sweep，可按二级高度、FOV、二级节点数量和 standoff 组合批量生成 stress episode，并在 sweep 结束后自动调用 D6 标准 AirSim calibration report bundle，输出 records/summary/report 口径。该记录只描述当时集成基线，不替代最新 P1 合同验收。D4 模块边界保持不变：D4 不生成系统级 `AssignmentPlan`，只提供 `pending_secondary_plan`/`secondary_plan_active` metadata、仲裁记录和 CBBA 保底结果供 main/D3/D7 消费。

历史基线（2026-07-08）：AirSim 机动高空侦察节点 stress 输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`，3 seeds 均 connected=True；每个 seed 含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，所有 episode 均为 13 frames 且 image_ok=13。场景使用 5 个目标、5 个拦截相机、2 个二级侦察相机、200 m 高差、80 度 FOV 和 1920x1080；D4 主动作符合预期：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`。二级侦察侧 `gimbal_pointing_ok_rate=1.0`，cue source 为 `radar_global_track_cue`，capability class 为 `mobile_high_recon`。

历史基线（2026-07-10）：`p1_gap_closure_calibration_20260710` 完成 10 seeds、50/200 m、3 个机动高空二级节点、FOV 110 度、1920x1080 的 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m 下 network joint full-view 均值 0.023、最大 0.154，coverage 均值 0.685；200 m 下 network joint full-view 恒为 0.000，coverage 均值 0.708。两种高度均有有效投影和稳定注册，cross-view association 均值为 4.6/4.0，stable registration 均值为 86.3/96.7。该批次记录的是当时 network full-view 持续性断点，不代表当前二级 commit 正例状态。

P0 状态：无 P0 blocker。P0-B 在 D4 模块内已闭合到单元测试层：heartbeat 短时丢包/延迟经滑动窗口和 dwell 后才进入 failed；过期或非单调二级 plan 被标记为 not executable；二级能力评分区分 `visible_only`、`registration_usable` 和 `takeover_ready`，并记录 score input 明细；无硬冲突的持续 reacquire 保留 center plan binding，但不能授予 D5/D7 terminal lock 或 PNG 控制权限。历史 2026-07-10 的 10-seed 决策明细中，1300 条记录均通过 heartbeat/link/cue/gimbal、visible 和 registered 检查，score 无低于 0.70；1285 条因 network full-view < 0.80 保持 `registration_usable`，其中 600 条还低于 coverage 0.65。其余 15 条瞬时 `takeover_ready` 只出现在 50 m 的 seed 2/5，均为 `pending_secondary_plan`，没有 active/executable plan，最终仍回落 distributed。该组数字是门限历史基线，不是最新 commit 状态。

2026-07-11 D4 readiness/接管 P1 已在模块内补齐并修复边沿初始化：硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；`D4ArbitrationAdapter` 默认要求 3 个不同时间戳决策、至少 0.2 s 持续且相邻 evidence gap <= 1.0 s，才把瞬时 `takeover_ready` 解释为 sustained readiness。同一 frame 的多次调用不会增加 streak；`not_ready -> takeover_ready` 和能力回落后的再次 ready 都会设置新的 `ready_since_s`、从 count=1 重新计时。lifecycle/event 逐决策记录 stable/not-registered value、presence、evidence source、streak、duration、sustained 和 fallback reason。pending/active 合同新增 source match、required lease epoch、lease expiry、transition、pending since、activated at、activation delay 与回落原因；heartbeat/link/cue/gimbal/lease/能力回落均有 distributed 或 pending/not-executable 负例。D2 online truth 隔离后，D4 还显式读取 `truth_metrics_available`/`continuity_available`：不可用的 IDSW/continuity 占位不触发降级，在线 ambiguity 和 track-quality-derived association risk 仍生效。连续 `duplicate_track_risk` 仅作 soft 观察，不能合成 hard observed duplicate；显式 count/delta/observed flag 仍立即阻断。历史 AirSim 记录缺真实逐决策 stable/not-registered 输入；最新合同 episode 已完成 secondary/peer commit DTO 和 action 接线，后续缺口是物理执行、完整扰动与多 seed 长期证据。D4 不生成 `AssignmentPlan`。

2026-07-11 中心重规划请求 lifecycle 已在 D4 模块侧闭合：冻结 `CenterReplanStatus` 携带 request/target/coalition/risk/state/timestamp/resolved-plan 字段，adapter 用排序去重后的 risk tuple 比较当前风险。`ActiveDegradationConfig.center_replan_cooldown_s=2.0`，以 resolved/requested time 为起点；pending/applied/no-change 在窗口内即使新增非硬风险也继续 suppress，严格到 `timestamp >= reference+2.0` 才重新开放。`terminal_persistent_disagreement` 保留首次请求和 D6 hard-risk 分类，但不绕过 cooldown；expired、中心 failed 以及 friend/重复锁/assignment-version/IDSW/coalition conflict 仍即时绕过。2026-07-12 后，`continue_center` 对无硬冲突的 `ambiguous/hold/reacquire` 始终保留 `terminal_consistent=True` 以表达 current center binding 仍可信；持续失锁只触发视觉 cue/观察路径。真实 mismatch、stale/not-current plan、版本/ACK/lease 冲突仍保留 `terminal_consistent=False` 和风险供 D7 独立门控。center-replan lifecycle 与 `k=1` fallback 本身无行为变化。

2026-07-11 D4 本地 P1 原子联盟合同已实现：冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 直接扩展现有 `CoalitionSafetyEvidence`。协调器校验双版本、epoch、成员身份、ACK 有效期、lease 和 digest；完整 ACK 后才能进入 committed/executing，缺 ACK、旧 epoch、过期 lease、网络分区或 digest 冲突进入 aborted/reconfiguring。中心正常仍使用现有路径；中心失效后，只有 secondary `takeover_ready` 或完全无中心 committed 联盟才设置 `atomic_coalition_formed=true`，否则保持 fail closed。event/D6 metadata 已输出 commit 状态、成员、epoch、coordinator 和 lease；恢复只输出双轨审计，不立即夺权。该合同在 2026-07-12 无行为变化；当前 D4 模块测试 148 项通过。

2026-07-11 center replan coalition convergence 已补齐：D4 读取 main 已传入的 D5 `CoalitionVisualSummary`，校验 current track/plan/coalition scope、完整 primary lock 集合、无 conflict，以及 commit-required 时 committed/executing 和 required ACK 完整。只有中心 alive 且当前决策无 friend/duplicate/wrong-binding/version/commit/health 硬冲突时，matching pending request 才可输出 `continue_center` 和 `resolution_hint=acknowledged_no_change`；同一 summary 对所有 current primary 给出一致 action。D4 不修改 main adapter；最小接口字段记录在 README。该能力本轮无行为变化；当前模块测试为 148 项通过。

历史基线（2026-07-11、最终 P1 验证前）：`blocks_cv_m5_n2_liveness_batch_20260711` 的 seeds 7/17/27 均为 6 次重规划请求、6 次 `acknowledged_no_change`、0 次 applied、0 次 expired，需求满足率均为 1.0，错误重复锁均为 0，说明当时中心重规划请求 lifecycle 和合法多成员锁审计已稳定收敛。T002 的视觉共识帧为 4/5/4，D7 每个 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。该批次已被最新 10-seed/故障注入验收补充，只证明 ComputerVision 状态链，不代表 SimpleFlight 动力学控制、协同到达或物理拦截完成。

历史基线（2026-07-11 早期 smoke）：200 m/2 二级节点、50 m/2 二级节点和 200 m/5 二级节点三组 truth-isolated 场景中，预期二级接管正例因联合全覆盖率为 0.0 而保守回落到 distributed。当时结果未关闭 P1，但已被后续 ACK/commit 正负例验证取代为当前状态；它仍用于说明不得以平均覆盖替代同帧联合覆盖，也不得放宽 readiness 门限。

下一轮按以下顺序实施和验收：

1. 先保持 P0 回归，冻结现有 heartbeat、readiness、source/lease/version、重规划 lifecycle 和 `k>1` fail-closed 合同。
2. 保持已完成的 P1 联盟协商合同回归：`CoalitionMemberAck` 和 `CoalitionCommitState` 已覆盖 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted`，并携带 target/coalition/plan version、epoch、lease、required/acked members、能力证据时间和失败原因。
3. 保持已通过的二级 `executing` 3/3、peer `executing` 3/3 和缺 ACK `aborted` 2/3 正负例回归，不再重复列为待闭合能力。
4. 对 1-5 帧及更长 `ambiguous/reacquire` 做同 plan/同 ID 的成对 dropout 验收：所有无硬冲突帧保持 binding，但不能单独授权 terminal PNG；超过 `non_locked_frame_limit` 后可请求二级 cue。friend/duplicate/resource/global-track/mismatch/stale-plan 在任意帧都必须立即 fail closed，并保持错误绑定为 0。
5. 扩展旧 epoch、过期 lease、成员不可执行、center-secondary/secondary-interceptor/peer 分区、digest conflict、成员退出/重构和恢复的扰动矩阵；使用同 seed 正常/故障配对，由 D6 聚合误降级和恢复指标。
6. 同一高净空几何和运行窗口的 M5N2 baseline/candidate 中心负对照已完成各 10 seeds；下一步复用相同 seeds 注入中心失效、中心与二级连续失效及 D1/D2/D3/D5 主动风险，分别报告 target、active-primary、coalition completion、D4 reject/action、误降级和恢复分布。中心负对照不能替代 fallback 验收。
7. 将 SimpleFlight 15 s 保持为断点诊断，物理拦截验收由更长时长和更高控制频率的系统级试验单独关闭，不能用合同通过替代。

P2（保持原规划）：

6. P2 只运行隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或恢复合并增强均不得替换本地轻量 CBBA 默认路径和 commit 安全合同。

任一步不满足都应保持 distributed/observe/hold，不降低 score、coverage、network full-view、持续窗口或版本安全门限。后续 D4 实现完成后运行：`PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`。

## 4. 被动降级与主动降级

### 4.1 被动降级

`passive_failover` 处理中心 C2 不可用：

- heartbeat 超过 hard timeout；
- heartbeat 滑动窗口内连续/累计 miss 达到 failed 阈值，且满足 `degraded/suspect` dwell；
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
- D3：plan stale、非 current、plan version 不匹配或显式资源不可行是硬风险；cost margin 过低是软证据，只说明当前方案容易抖动，不能单独触发中心重规划。
- D5：先由 `terminal_evidence_applicable` 判断普通视觉 readiness 证据是否处于适用窗口。窗口外忽略低 confidence、高 ambiguity、cross-view 软风险及 non-locked streak；friend conflict、重复末端锁定、资源错配、assigned/明确 observed `global_track_id` mismatch 仍是硬证据。窗口内无冲突的 `ambiguous/hold/reacquire` 多帧持续是软证据，优先继续观察或请求二级 cue。

主动降级的保守顺序：

1. 末端证据尚不适用、中心正常、D5 无明确硬冲突且 D1/D2/D3 只有非 hard-active 风险，或 D5 已适用并与 D3 分配一致：`continue_center`；软风险仍写入 record/D6。
2. D3 版本/时效硬风险是主因且 D5 仍一致：`request_center_replan`。
3. D1/D2 风险升高但 D5 仍一致：`request_secondary_assist`。
4. 只有 cost margin 过低、D5 低置信度或无冲突 `ambiguous/reacquire` 时：`continue_center` 或 `request_secondary_assist`，继续观察，不重规划、不降级。
5. D5 单窗口不一致但未满足持续触发：若无硬风险则继续观察；若有二级覆盖且需要补充视角，则请求二级辅助。
6. D5 持续 observed mismatch、资源错配、重复锁定，或 D3 stale/not-current/resource infeasible 时：中心仍可用则 `request_center_replan`，二级 readiness 不改变 owner/version。
7. 只有 `C2Health == failed` 才进入被动接管：二级持续 ready 则 `degrade_to_secondary`，二级不可用、链路/lease 过期或覆盖不足才 `degrade_to_distributed`。
8. `friend_conflict=True` 或身份证据冲突：`hold_for_review`，不发布新计划。

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
- `update_health()` 覆盖 heartbeat warning/stale/failure、peer quorum、heartbeat sliding window、miss threshold 和 `degraded/suspect` dwell；有 heartbeat 样本流时，单次延迟不会直接 `failed`。
- `merge_recovery()` 只比较 assignment owner/epoch 的基础版双轨合并；冲突或 review 未清空时保持 `degraded`。

## 6. 摘要接口

### 6.1 被动降级和 CBBA 摘要

- `TrackSummary`：`track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`、`visual_evidence`。
- `ResourceSummary`：`node_id`、`capability_class`、`availability_band`、`comm_band`、`operator_hold`、`takeover_priority`、`lease_epoch`、`lease_expires_at_s`、`node_role`、`coordinator_only`、`coverage_cell`、`heartbeat_timestamp_s`、`heartbeat_stale_after_s`、`cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_full_view_rate`、`cross_view_support_count`、`stable_cross_view_registration_count`、`not_registered_count`、`epoch`。
- `BidState`：`task_id`、`bidder`、`score`、`constraints_hash`、`epoch`、`round_id`。
- `CBBAResult`：assignments、rounds、converged、conflict/completion/message/byte 指标、`final_views`、`assignment_audit`、可选 `cost_gap_benchmark`；`build_cbba_d6_metadata()` 可将这些字段归一化为 D6 多 seed 报告 metadata。

### 6.2 主动降级摘要

- `TrackUncertaintySummary`：D1 定位质量，含 `position_sigma_m`、`covariance_trace`、`velocity_sigma_mps`、`measurement_age_s` 和 `coverage_cell`。
- `AssociationRiskSummary`：D2 关联风险，含 `ambiguity_score`、`id_switch_count`、`duplicate_track_count`、`track_continuity`、`truth_metrics_available` 和 `continuity_available`。后两个字段决定 truth-based IDSW/continuity 是否可用于在线仲裁；不影响在线 ambiguity、duplicate 和质量风险。
- `AssignmentValiditySummary`：D3 分配有效性，含 `global_track_id`、`assigned_resource_id`、`plan_version`、`is_current`、`plan_age_s`、`cost_margin` 和证据 metadata。`plan_age_s` 是最近评估活性年龄，优先读取 `plan.metadata.last_evaluated_at_s` 及兼容同义字段，缺失时回退 `created_at`；计划身份年龄单独记录为 `metadata.identity_age_s`。
- `TerminalAssociationSummary`：D5 末端关联，含 `terminal_evidence_applicable`、`decision_state`、confidence、ambiguity、observed/assigned `global_track_id`、连续非锁定/不一致帧数、friend conflict、duplicate lock、cross-view 风险，以及 D5 二级覆盖/转换漏斗字段 `cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap`、`secondary_detect_to_cross_view_reject_reasons`、`secondary_detect_available_but_not_registered`。
- `CommunicationSummary`：链路摘要，含 source/target/relay、`link_type`、sent/received timestamp、`payload_kind`、`stale_after_s`、sequence id。
- `SecondaryNodeLifecycleSummary`：除 heartbeat、lease、coverage、cue/gimbal/link、registration 与四级 readiness 外，新增 `registration_evidence_source`、stable/not-registered presence、takeover-ready consecutive decisions/since/duration/required values、`takeover_ready_sustained` 和 fallback reason。
- `D4DecisionRecord`：adapter 输出，可转为 D6 `EventRecord` kwargs；除既有 review、risk、coverage 和 plan 字段外，新增逐决策 readiness/evidence 审计、`secondary_takeover_previous_state/transition/fallback_reason`、pending since、activated at、activation delay、required lease epoch 和 source-match 结果。

### 6.3 二级接管 plan lifecycle metadata

D4 不生成完整系统级 `AssignmentPlan`，但在 `degrade_to_secondary` 触发时通过 `SecondaryTakeoverPlanMetadata` 给 main/D3/D7 提供可消费状态：

- `not_applicable`：非二级接管动作；当前 active plan owner 仍是 center、distributed_cbba 或 hold_review。
- `pending_secondary_plan`：只有 sustained `takeover_ready` 才能进入。D4 已选择二级节点并触发重分配，但新 plan 尚未生效；当前 owner 保持不变，并记录 source、supersedes、pending since/duration 和 reject reason。
- `secondary_plan_active`：main/D3 已回填新的 plan id/version、正确 source、满足节点要求的 lease epoch，且 expiry/current time 均存在并严格满足 `current_time < expiry`，同时 sustained readiness 未回落；`active_plan_owner=secondary_node`、`secondary_reassignment_complete=True`。D7 还必须检查 current binding；瞬时 readiness 不允许放行。

metadata 字段包括 `secondary_takeover_state`、`active_plan_owner`、`secondary_plan_source_node_id`、`secondary_plan_id/version`、`secondary_plan_lease_epoch`、`secondary_plan_lease_expires_at_s`、`secondary_plan_lease_valid`、`secondary_plan_epoch_monotonic`、`secondary_plan_executable`、`secondary_plan_reject_reason`、`recovery_dual_track_audit`、`secondary_supersedes_plan_id/version` 和 `secondary_reassignment_complete`。缺 expiry/current time、`current_time >= expiry`、旧 epoch、source mismatch 或非单调替换均不可执行。若当前 plan owner 已是 secondary 且 current/secondary plan id/version 相同，该 equality 只豁免版本递增，不豁免 lease/source/readiness；失效时 owner 转为 `hold_review`。

D5 二级 detect 覆盖可见、`gimbal_pointing_ok=True` 或 `secondary_coverage_ratio > 0` 只说明二级节点具备侦察证据；只有 main/D3 回填新的二级 plan id/version 且显式 `secondary_plan_active=True` 时，D4 才把接管 metadata 置为 `secondary_plan_active`。若 cross-view association 为 0，或 D5 在 global binding/registration 漏斗处拒绝，D4 仅记录 `secondary_detect_available_but_not_registered` 诊断，保持 `request_secondary_assist`/pending 或按既有硬冲突规则降级。

### 6.4 二级侦察校准解释口径

D4 不直接做视觉注册、相机投影、bbox 几何门控或多视角 ID 绑定；这些由 D5/main 产生，再由 D6 聚合。D4 只消费下列摘要并写入仲裁事件：coverage、heartbeat/link/cue freshness、gimbal pointing、stable cross-view registration、not-registered 诊断、三值 review label 和 plan activation metadata。

为避免把“看见目标”等同于“可接管分配”，D4 把二级侦察状态记录为四级 readiness class。lifecycle 保留节点类型字段，event metadata 顶层 `secondary_capability_class` 表示 readiness：

- `not_ready`：coverage、heartbeat、link、cue、lease 或 gimbal 条件不足，不能作为辅助或接管依据。
- `visible_only`：二级可见但未注册，常见证据为 `secondary_detect_available_but_not_registered=True`、`cross_view_association_count=0`、`not_registered_count>0` 且无稳定注册，或 reject reasons 包含 global binding/registration 断点。D4 只记录诊断或请求二级辅助，不把该证据升级成 `secondary_plan_active`。
- `registration_usable`：已有 `stable_cross_view_registration_count`、`cross_view_support_count` 或 `cross_view_association_count`，但 `secondary_network_joint_full_view_frame_rate`/`secondary_network_full_view_gap`、coverage 或综合 score 还不到接管阈值。D4 把它作为接管必要性审计和阈值标定输入，不直接放行 D7 visual PNG gate。
- `takeover_ready`：coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、稳定注册和综合 score 均满足 D4 gate。只有该状态才可作为 `degrade_to_secondary` 接管依据；D7 handoff 必须看到 `secondary_capability_class=takeover_ready`，系统级 plan owner/version 仍必须由 main/D3 回填。

### 6.5 D5 分布式视觉证据摘要

`DistributedVisualEvidenceSummary` 用于完全无中心 CBBA 的风险加权，字段包括：

- `visual_support_resource_ids`、`hold_resource_ids`、`ambiguous_resource_ids`、`duplicate_lock_resource_ids`；
- upstream `assigned_global_track_id`；
- terminal confidence/ambiguity、hypothesis/support count；
- `hypothesis_only`、`stale_global_track_id`、`missing_global_track_id`、`duplicate_terminal_lock_risk`；
- `friend_conflict`、`global_track_id_conflict`、`local_id_conflict` 和 `risk_reasons`。

D4 的 adapter 使用 duck typing/dict 归一化 D5 distributed terminal association 或 cross-peer hypothesis，不导入 D5 类型，也不生成新 ID。

### 6.6 区域资源建议合同

- `RegionResourceSnapshot`/`RegionResourceNode`/`RegionResourceEdge` 是 `d4-region-resource-snapshot-v1` 的 truth-free 变长图合同；区域节点不列举 task、target、actor 或 `global_track_id`。
- `RegionResourceRecommendation` 只返回逐区域 `resource_quota_delta`、`reserve_ratio`、`reconnaissance_priority`、`hold/request_replan` 和邻边 `RegionTransferSuggestion`，不承载成员或目标分配。
- `DeterministicResourceProjector` 将模型/规则原始输出重新投影到当前 formal D4 verdict；总 quota delta 必须为零，断边、partition、旧 owner/plan/epoch、过期 lease、缺 ACK、fault fence 和 formal commit 都阻断资源移动。
- `RegionResourceAdvisoryContract` 是后投影的 `d4-region-resource-advisory-v1`。其 `advisory_id` 对完整合同内容做 SHA256，`valid_until_s=min(created_at_s+advisory_ttl_s, min(region lease))`，并显式携带 source plan versions、逐区域 authority generation、protected reserve/committed 和逐 transfer endpoint generation/edge capacity proof。
- `RegionResourceAdvisoryGate.consume()` 使用 current `RegionResourceSnapshot` 和可选 current formal verdict 重验合同，并在首次 `consumable=true` 后记录 ID。后续同 ID、旧 snapshot/plan/epoch、严格到期 lease、ACK/fault 变化、formal commit 变化、资源或 edge 变化一律拒绝。内存 gate 只提供进程内幂等；main 若跨进程消费必须持久化 advisory ID ledger。
- `RegionResourceAdvisorConfig.mode` 默认 `disabled`；`shadow` 只记录建议，`assist` 仍只是建议可见性级别。少于 20 个未见 seed 或模型回退时 effective mode 保持 `shadow`。
- paired evaluator 至少输出 backlog、transfer time、plan churn、communication load、fail-closed、安全违规和 candidate latency P50/P95；安全违规、fail-closed/backlog 回归或样本不足均不得推荐 assist。

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

### 7.3 CBBA vs 中心化 cost gap benchmark

`build_cbba_cost_gap_benchmark()` 只做离线对照，不在完全无中心路径运行中心化 Hungarian。输入必须来自 D3/main：

- `center_assignments`：D3 当前中心化计划或 Hungarian/Min Cost Flow 结果的 task -> owner 映射；
- `cost_by_task_resource`：同一场景下 D3 保存的 task/resource cost matrix；
- `CBBAResult`：D4 轻量 CBBA 的 assignments、completion、conflict、rounds 和 message 指标。

输出 `CBBACostGapBenchmark`，字段包括 `cbba_total_cost`、`center_total_cost`、`absolute_cost_gap`、`relative_cost_gap`、assignment/completion 差距、CBBA conflict/round/message 指标、缺失 task 和缺失 cost pair 审计。若任一已分配 task/resource cost 缺失，总 cost/gap 保持 `None`，避免伪造可比结果。

## 8. 二级节点 lifecycle 与接管

二级节点在代码中通过 `NodeRole.GROUND_BACKUP`、`NodeRole.SECONDARY_RECON`、`NodeRole.FIXED_TETHERED_SECONDARY`、`NodeRole.MOBILE_HIGH_RECON`、`NodeRole.MOBILE_SECONDARY_RECON`，或等价 `capability_class=fixed_tethered_secondary/tethered_recon/mobile_high_recon/mobile_secondary_recon` 建模。可用性判断包括：

- `availability_band != none`；
- `operator_hold=False`；
- `coverage_cell` 必须匹配当前任务区域，且显式 `secondary_coverage_ratio >= 0.65`；
- heartbeat 未超过 `heartbeat_stale_after_s`；
- `cue_freshness_s` 必须显式存在且未超过 freshness 窗口；
- `gimbal_pointing_ok` 必须显式为 true；unknown/false 均拒绝；
- `CommunicationSummary[]` 必须显式存在且包含新鲜的 `c2_direct`、`secondary_relay` 或 `video_cue` 链路；
- network full-view、readiness timestamp/streak/duration 和 lease epoch/expiry 必须显式满足统一门限。

机动高空侦察节点随拦截机出动、不拦截，正常时用 D1/D2 `GlobalTrack` 或 radar cue 指向目标簇，并给局部拦截群提供图像、coverage 和 cross-view evidence。中心可用时它只提供观测辅助；中心 failed 且二级候选持续 ready 时才可作为二级协调节点。仅有侦察图像、cue freshness、云台指向或 coverage ratio 不能绕过 D3 plan version、D5 身份/友方约束或 D4 既有 action 门控。

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

`ActiveDegradationArbiter._select_secondary_node()` 会按覆盖区/coverage ratio、network full-view rate、heartbeat、lease expiry、cue freshness、gimbal pointing、链路 freshness、stable registration count 和 not-registered count 过滤候选。中心可用时该候选只用于辅助 cue；中心 failed 后，`degrade_to_secondary` 还必须满足 `secondary_readiness_class=takeover_ready` 和 `secondary_takeover_capable=True`。排序口径为 `takeover_priority -> secondary_capability_score -> capability class -> lease_epoch -> node_id`。

## 9. D6 事件与指标

`D4DecisionRecord.to_event_record_kwargs()` 当前可输出 D6 兼容字段：

- `event_type`：`d4_arbitration_decision`、`active_degradation_decision` 或 `passive_failover_start`；
- `severity`：正常继续中心为 `info`，降级/hold 为 `warning`；
- metadata：`d4_action`、`degradation_mode`、`d4_degradation_mode`、`selected_coordinator`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp`、`review_label`、`active_degradation_review_label`、`active_degradation_necessity_label`、`review_label_detail`、`review_label_source`、pre/post review window、resource/track/plan/version、`active_plan_owner`、`secondary_takeover_state`、`secondary_plan_source_node_id`、`secondary_plan_id/version`、lease/executable/reject reason、`recovery_dual_track_audit`、`secondary_supersedes_plan_id/version`、`secondary_reassignment_complete`、`secondary_plan_activation_delay_s`、`secondary_plan_pending_duration_s`、`secondary_takeover_candidate`、`secondary_takeover_success`、`secondary_takeover_necessity_label`、`coverage_cell`、`terminal_consistent`、`terminal_evidence_applicable`、`risk_factors`、hard/soft risk、false-trigger candidate、`secondary_available`、`communication_fresh`、`secondary_lifecycle`、二级 diagnostic 节点 heartbeat/link/cue/gimbal/coverage/capability 字段、readiness `secondary_capability_class`、`secondary_capability_inputs`、`cue_freshness_s`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_coverage_available`、`secondary_network_full_view_gap`、`cross_view_support_count`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap`、`secondary_detect_to_registration_gap`、`secondary_detect_to_cross_view_reject_reasons`、`secondary_detect_available_but_not_registered`、`secondary_detect_to_cross_view_diagnostic`、`requires_human_review`。

`ActiveDegradationDecision.to_metrics()` 可输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate` 和 `distributed_conflict_count`。

`build_cbba_d6_metadata()` 可从 `CBBAResult` 输出被动/完全无中心侧多 seed 字段：`d4_action`、`coordination_mode`、`selected_coordinator`、leader/coverage、`failover_time`、consensus/conflict/completion/message 指标、`assignment_audit` 和可选 `cost_gap_benchmark` 扁平字段。`run_failover_simulation()` 顶层 metrics 已透出 `coordination_mode`、leader 和 coverage，避免二级接管与完全分布式 CBBA 在报告中混淆。

## 10. N 规模输入

D4 不写死 2v2 或 5v5。当前行为：

- `run_failover_simulation()` 按 `resources`/`tasks` 实际列表长度运行；若未传列表，则按 `node_count`/`task_count` 构造摘要。
- CLI `--drone-count N` 只决定默认资源/任务数量，`--nodes` 是 legacy alias。
- CBBA 使用 `node_ids`、`TrackSummary[]` 和 `ResourceSummary[]` 长度运行。
- 2v2/5v5 只作为 AirSim baseline 或测试命名，不是算法限制。

### 10.1 M 对 N 联盟任务边界

2026-07-11 文献和开源实现审计确认：目标需求 `k_j > 1` 时，问题不再是当前 single-winner CBBA 的普通 N 规模扩展。当前 `TrackSummary -> one owner` 合同只能表示一对一保底分配；将高威胁目标复制成三条任务无法原子保证成员集合、异构能力、共同/波次到达窗口和成员退出后的重构一致性。

D4 已完成 fail-closed 与本地 commit 合同：`CoalitionSafetyEvidence` 读取 D3 schema v2 的 coalition/member/version/demand；区域合同中的中心、二级和完全分布式三层 `k_j>1` 任务都必须通过 `CoalitionCommitCoordinator`，只有 target、双版本、epoch、成员身份、全部 ACK、lease 和 digest 均有效时才原子 `committed`，否则输出 hold/reconfigure。中心和二级路径沿用 D3 给定成员，commit metadata 分别标记 `d3_center_assignment` 与 `d3_assignment_secondary_coordination`；仅完全分布式路径使用 `bounded_constrained_bid_selection` 形成候选。`FailoverCoordinator` 仍不把 single-winner CBBA 冒充多成员原子联盟。合法联盟内多个授权成员锁同一 `global_track_id` 不算 duplicate；越权/超额成员和旧版本均拒绝。当前已实现区域能力与跨区域容量约束的确定性成员候选；完整 CBBA/CCBBA 多轮共识、全局组合最优、耦合时序、reserve 激活、补位/缩编、在线整盟重构和 main-owned episode DTO 路由仍保持 deferred。D4 不替代 D7 到达可达性判定，也不改写 `global_track_id`。

真实证据 `airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 暴露了原门控缺口：中心 owner 仍为 `center`，T001 coalition `k=3`、complete、plan/coalition version current，但 D5 长期 `reacquire` 后 arbiter 候选进入 `degrade_to_distributed`。静态 `coalition_center_plan_valid` 不等于 single-winner distributed path 已支持原子联盟；本轮修正将该候选改为中心重规划。

### 10.2 区域化 200v200 合同

`RegionalScenarioMetadata.from_scalable_scenario()` 消费 scalable3d 场景中的 `target_count`、`resource_count`、`recon_count`、`region_count`、scenario name/version 和 schema version；区域 ID 可由 main 显式传入，缺省只按输入 `region_count` 生成稳定编号。`RegionalFailoverSnapshot` 要求 region definition 与 scenario region 集合一致，active task 数不得超过 scenario target count，节点、区域和任务均按输入列表长度处理。

每个 `RegionalTaskEvidence` 保留上游 `global_track_id`，并同时携带 D1 covariance/age、D2 ambiguity/IDSW/duplicate、D3 plan id/version/epoch/lease/current/feasible、D5 consistency/binding/friend/duplicate 和可选 member support/hold/ambiguity。D4 不创建或重绑定 `global_track_id`。输出 `d4-regional-failover-v1` 包含 scenario/node/resource/recon/region/task counts、逐区域 action、selected layer、唯一 ownership、readiness、candidate assignment、coalition commit 和 reject reason，可直接作为 main-owned `VersionedEnvelope.payload` 的 truth-free 数据。

状态顺序固定为：中心非 `failed` 时保持中心；中心 `failed` 后选择覆盖当前 region 且 strict readiness/lease epoch 有效的机动高空二级节点；只有不存在有效二级节点时才形成 distributed candidate。owner/layer 变更要求 `epoch` 与 `plan_version` 同时递增，同 generation 的 owner 变化视为冲突。分区会撤销已提交区域 coalition 的执行资格并进入 `reconfiguring`；恢复必须由调用方提供新 generation。

当前 distributed candidate formation 只实现确定性、能力和跨区域容量受约束的 bid selection。它能从动态 member/task 集合形成一个候选集合并叠加原子 commit，但不含 CBBA 多轮消息传播、网络图收敛证明、全局组合最优、耦合时序优化、reserve 激活或 member-loss 在线重构，因此不能宣称区域化 CBBA/CCBBA 算法差距已关闭。中心与二级不使用该 formation algorithm，而是分别审计 D3 中心成员和 D3 二级协调成员；三层 `k>1` 的 ACK 原子门一致。

## 11. 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `C2Health` | `normal/degraded/suspect/failed`、heartbeat warning/stale/failure、sliding window/miss threshold/dwell、peer quorum、digest conflict、center epoch stale、恢复待合并 | `coordinator.py`、`models.py`、`tests/test_health.py` |
| scalable3d 区域 authority | 动态 scenario/resource/recon/region/task 元数据，逐区域中心/机动高空二级/distributed 顺序，唯一 ownership，epoch+plan version+lease，D1/D2/D3/D5 evidence，truth-free bus payload | `regional_failover.py`、`tests/test_regional_failover.py` |
| 区域资源规则、安全投影与消费合同 | 版本化聚合区域图、规则基线、资源守恒、邻边通信/机动约束、最低备用、owner/version/epoch/lease/fault/ACK/commit fence、内容寻址 ID、有效期、来源版本和一次性 next-cycle consumption gate | `region_resource.py`、`tests/test_region_resource_advisor.py` |
| 可选共享图学习研究管线 | 共享 node/edge 网络、变长图 actor-critic、BC、原生 clipped PPO、bundle v2/SHA256、OOD/timeout/低置信/非有限回退、数值 seed 口径 shadow paired evaluator；默认 disabled/shadow | `region_resource_learning.py`、`region_resource_cli.py`、`scripts/run_region_resource_advisor.py`、`tests/test_region_resource_advisor.py` |
| 区域学习 episode 数据合同 | `dataset-v1` source/frame、truth-key 拒绝、完整 episode stage、数值 seed 原子 split、manifest/availability/多层 SHA、严格 BC/PPO loader 和 bundle v2 provenance | `region_resource_dataset.py`、`region_resource_learning.py`、`tests/test_region_resource_dataset.py` |
| 被动降级 | 中心 failed 后才执行 `plan_degraded()`；可选 ground backup/fixed tethered secondary/mobile high recon/representative；不收敛不发布有效 assignments | `coordinator.py`、`tests/test_coordinator.py` |
| 二级节点 lifecycle | heartbeat age/stale、lease epoch/expiry、coverage、requested coverage match、video/cue freshness、cue stale、gimbal pointing、coverage ratio、network full-view rate、stable registration/not-registered count、固定/机动二级分类、link stale/fresh、`secondary_available`、visible/registered/takeover_capable、`secondary_readiness_class`、capability score 和 score inputs | `active_degradation.py`、`models.py`、`tests/test_active_degradation.py` |
| 主动降级仲裁 | 中心可用时输出 `continue_center`、`request_center_replan`、`request_secondary_assist` 或 `hold_for_review`；`degrade_to_secondary/degrade_to_distributed` 仅由中心 failed 的被动链路输出。`terminal_evidence_applicable=false` 且中心正常时，窗口外视觉软证据及 D1/D2/D3 非 hard-active 风险不拉起视觉辅助；hard-active 和安全/绑定冲突仍保持原动作 | `active_degradation.py`、`adapter.py`、`tests/test_active_degradation.py`、`tests/test_arbitration_adapter.py` |
| D1/D2/D3/D5 adapter | duck typing/dict 读取 covariance/age、ambiguity/IDSW/continuity、plan/version/freshness/cost、terminal/cross-view/friend conflict，并归一化 dict/object 形式二级节点的 `role/capability_class/cue_freshness/gimbal/coverage` | `adapter.py`、`tests/test_arbitration_adapter.py` |
| M-to-N 原子联盟安全门控 | schema v2 coalition/member/双版本校验；member ACK、commit lifecycle、lease/epoch、digest 和 fail-closed 已实现。最新验证中二级与 peer 均 ACK 3/3 `executing`，缺 ACK 为 2/3 `aborted`；无有效 commit 时仍 replan/hold。合法授权多锁不算 duplicate；single-winner CBBA 不承担 `k>1` 成员形成 | `coalition_safety.py`、`adapter.py`、`coordinator.py`、`tests/test_coalition_safety.py`、`tests/test_coalition_commit.py` |
| D5 distributed visual evidence normalization | `build_distributed_visual_evidence_summary()`、`attach_distributed_visual_evidence()`、`merge_distributed_visual_evidence_into_tracks()` | `adapter.py`、`tests/test_arbitration_adapter.py` |
| 完全无中心 CBBA 风险加权 | D5 visual support 调整出价；hold/friend/stale/missing/conflicting ID 阻止 bid；duplicate lock 风险审计 | `cbba.py`、`tests/test_cbba.py` |
| `assignment_audit` | 输出 owner、visual support、hold/ambiguous/duplicate IDs、confidence/ambiguity、hypothesis、ID 风险和 reason | `cbba.py`、`tests/test_cbba.py` |
| D6 event metadata | `D4DecisionRecord.to_event_record_kwargs()` 输出 D6-compatible kwargs 和 metadata，含三值 review label、`active_degradation_necessity_label`、pre/post window、secondary diagnostic、network coverage gap、readiness class、capability score inputs、stable/not-registered count、lease/executable/reject reason、hard/soft risk、false-trigger candidate、plan activation delay 和 takeover necessity/success 字段 | `adapter.py`、`tests/test_arbitration_adapter.py` |
| D6 CBBA report metadata | `build_cbba_d6_metadata()` 输出 coordination mode、leader、coverage、CBBA 收敛/通信/审计指标和 cost gap 扁平字段；`run_failover_simulation()` 顶层 metrics 透出 secondary/distributed 分组字段 | `cbba.py`、`simulation.py`、`tests/test_cbba.py`、`tests/test_simulation.py` |
| D7 二级接管门控辅助 | `build_d7_secondary_handoff()` 阶段 1 不放行 visual PNG；阶段 2 必须带 plan id/version、readiness exact-true、存在且匹配的 expected/actual source、存在且满足的 plan/required lease epoch，并证明 `current_time < expiry`。逐字段 `None`、等于边界、过期、旧 epoch、source mismatch 或非 `takeover_ready` 均阻止放行；maintained secondary owner 也重新校验 | `active_degradation.py`、`tests/test_airsim_phase1_dry_run_contracts.py` |
| secondary takeover plan metadata | `SecondaryTakeoverPlanMetadata` 输出 pending/active、source、lease epoch/expiry、executable/reject 和恢复审计；发布与维持统一严格 `<`。当前 secondary-owned 同 id/version 只豁免版本递增，lease 缺失/到期仍回落 hold；D4 不生成系统级 `AssignmentPlan` | `active_degradation.py`、`adapter.py`、`tests/test_arbitration_adapter.py` |
| CBBA vs 中心化 cost gap helper | `build_cbba_cost_gap_benchmark()` 对比 D4 CBBA result 与 D3/main 提供的中心 plan/cost matrix，输出 cost/completion/conflict/message gap 字段 | `models.py`、`cbba.py`、`tests/test_cbba.py` |
| main/runtime P1 消费基线 | main 已接入 D4 adapter event、`request_center_replan -> D3 new version`、secondary takeover owner/version 和 D7 owner gate；controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已能批量改变二级节点高度/FOV/数量/standoff，并自动生成 D6 AirSim calibration report bundle。此项为 main-owned 集成证据，修复后口径为 main/D3/D7 消费 owner/version，D4 只消费/输出仲裁与 metadata，不生成系统级 `AssignmentPlan` | `research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_main_episode_bus_marks_secondary_takeover_plan_for_d7`、`::test_controlled_2v2_active_degradation_secondary_plan_visual_png` |
| N 规模输入 | 仿真、CBBA 和测试按输入列表长度运行 | `simulation.py`、`scripts/run_failover_simulation.py`、`tests/test_simulation.py`、`tests/test_cbba.py` |

## 12. 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| main runtime bus episode-time 接线 | D4 tick adapter、7 场景规范矩阵和 2026-07-13 六类、10-seed、60-case AirSim episode clock 批量验收均已完成；60/60 safety outcome，误降级、重复 owner 和 split-brain prevention failure 均为 0 | 真实吞吐带宽、时钟漂移、网络排队/抖动/乱序/重传、secondary-interceptor/peer 实际链路和硬件 RF 尚未验证 | 保持当前 schema 与安全门控；工程网络验证需独立链路仿真器、网络仿真或硬件条件 |
| D3 `request_center_replan` 自动调用 | D4 能输出 `request_center_replan` 并说明风险因素；main 已监听该 action 并触发 D3 新 plan version | 真实多 seed 下仍需确认硬 stale/not-current 和真实 terminal mismatch 的触发频率，避免软风险回归成每帧 replan | main/D3 保持 owner/version/supersedes 字段和 stale rejection，并用多 seed 报告校准 |
| secondary takeover plan owner/version 闭环 | D4 已实现 sustained gate、逐决策 evidence、pending/active transition、source/lease epoch/expiry strictness；最新二级正例由 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` | 正例已闭合合同层；仍需在完整扰动矩阵中统计回落、恢复和误降级 | 保持正例回归，并扩展 lease/分区/成员故障成对样本；不放宽门限 |
| 完整 C2 双轨审计 | 已记录 health transition 和 assignment-only merge | 尚未比较完整 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态 | main/runtime 需要持久化中心和 fallback 双轨 episode log，D6 消费 merge outcome |
| D4/D5 stress 统一口径 | 历史 60-case freshness 基线、最新二级/peer commit 正例和缺 ACK 负例均可审计 | 仍缺完整扰动矩阵、coverage-cell 切换、成员退出/重构和多 seed 恢复统计 | main/runtime 使用同一 schema 增加成对扰动 case，统计 readiness 驻留、回落和恢复 |
| D5 distributed visual evidence 运行时合流 | D4 模块内可把 D5 多 peer evidence merge 到 `TrackSummary.visual_evidence` | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重仍需标定 | main 在 no-center case 持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线 |
| CBBA 与中心化最优 gap | D4 已有 `CBBACostGapBenchmark`、`build_cbba_cost_gap_benchmark()` 和 `build_cbba_d6_metadata()`，可对 D3/main 提供的中心 plan/cost matrix 计算 cost/completion/conflict/message gap 并输出 D6 多 seed 报告字段 | 真实 episode 还未持续保存同场景 D3 cost matrix/current plan，也未由 D6 汇总多 seed gap | main/D3 保存中心化 cost matrix/current plan，D6 聚合 benchmark 输出 |
| scalable3d 区域运行时接线 | main-owned 质点模块栈已发布区域 evidence、消费 ownership payload，并闭合单二级、多二级和 distributed D3 plan；D7 按 owner/epoch/lease/commit/fault fence 门控 | 仅有接口/质点集成测试；未完成 AirSim、真实网络、长时 200v200 多 seed 与 D6 区域趋势报告 | 保持 8/8 定向集成回归，补 20 个未见 seed、stage timing、transition/churn、分区恢复和安全违规统计 |
| 区域资源建议消费与学习效果 | 后投影 advisory、一次性门、规则、dataset-v1、bundle provenance 和 fail-closed 回退已实现；正式 900 episode 已按 70/15/15 seed 审计并完成固定 seed BC 开发模型，tracked 指标与 SHA 已落盘 | 当前 14384 个区域动作没有 quota/transfer/hold/replan 正样本；898/1798 帧状态转移无归因；reward/causal/counterfactual 可用数均为 0；外部 20 seed、paired 收益和 main/D3 advisory 消费仍未完成 | producer 先生成带动作归因和安全结果的正负样本，D6 冻结 reward/causal 合同；随后重训并在 1000-1019 上做 paired shadow。当前 bundle 固化 `action_diversity_sufficient=false` 与 `strategy_capability_claim_allowed=false`，不得用低损失申请 PPO/assist |

## 13. 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CA-CBBA optional replay | 已实现隔离 path/source capability adapter 和逐场景 unavailable 结果；未 import/执行外部实现 | MIT 参考为 MATLAB 且未集成 runtime；CA-CBBA 公共参考没有可执行源码；默认测试不能依赖外部工程 | 若未来获得合法可执行源码与 runtime，另加离线 execution adapter 和同预算结果校验；不得进入默认路径 | P2 capability 已完成 / execution unavailable |
| 独立 auction baseline | 未单独实现 single-round auction，后置为可选对照基线 | 当前 `CBBANegotiator` 有 winner/bid 共识和 D5 visual evidence 加权，但不是独立拍卖状态机；P1 主线先保证 adapter 接线和 CBBA gap benchmark | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P2 后置 |
| Contract Net | 未实现 manager/contractor announce-bid-award 状态机 | 二级节点健康时仍需和 D3 plan version 对齐；manager 失效后还要 fallback 到 peer consensus | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是摘要和内存网络，真实链路属于 main/runtime/D5/D1 | runtime 生成 LinkRecord/video metadata；D5/D1 处理图像、检测、标定和 cue schema | P2/P3 |
| 虚拟中心 Hungarian | 明确不实现为 no-center fallback | 完全无中心模式不能伪造中心权威或改写 `global_track_id`；中心化最优属于 D3/main | 若要对照，只能做离线 benchmark，不得替代 D4 CBBA 保底 | 不做主线 |
| D4 直接生成系统级 `AssignmentPlan` | 不作为 D4 能力实现；D4 只输出仲裁/metadata/CBBA 保底结果 | D3/main 拥有 plan schema、plan owner、版本策略和 stale rejection；main P1 已接入 secondary owner/version 消费基线 | D4 继续保持不生成系统级计划，必要字段通过 `SecondaryTakeoverPlanMetadata` 输出 | 非 D4 主线 |
| 完整自主成员形成与联盟重构算法 | 区域合同仅在 distributed fallback 使用 bounded constrained bid selection，可按 region、跨区域 capacity、capability 和 D5 member evidence 形成确定性候选；中心/二级/distributed 三层原子 commit 与缺 ACK fail-closed 正负例已通过 | 尚无 CBBA/CCBBA 多轮区域共识、全局组合最优、时序可达性、reserve 激活、补位/缩编/整盟重构；member-loss/replacement replay 仍由测试手工给定 | 保持当前 commit 合同，后续增加网络图、耦合任务、reserve 和成员变化的新 generation 状态机 | P1 保持开放 |

## 14. P1/P2 下一步

P1：

0. **M 对 N 联盟合同保持回归**：P1 合同层已闭合；固定回归二级 ACK 3/3 `executing`、peer ACK 3/3 `executing` 和缺 ACK 2/3 `aborted`。继续研究 `simultaneous|sequential|mixed`、reserve、成员退出缩编/补位/整盟重组，但不得把这些开放项误写成 commit 正例未闭合。
1. D4 模块内的逐决策 stable/not-registered source/presence、连续 readiness 窗口、pending/active transition、source/lease strictness 和 heartbeat/link/cue/gimbal/能力回落负例已完成；后续保持这些合同回归，不再作为代码缺口。
2. 保持已通过的 secondary/peer executing 与缺 ACK aborted 场景，继续统计 activation delay、回落原因和恢复窗口，不降低门限。
3. episode clock 六类、10-seed、60-case 安全矩阵已完成；下一步把 heartbeat、lease、video/cue freshness 和 gimbal 摘要接到可配置带宽、时钟漂移、排队抖动、乱序和重传模型，继续记录 plan activation delay 与恢复双轨窗口。D4 只消费链路摘要，不负责修正 D5 几何注册。
4. 分区注入已证明 10/10 恢复时新 generation 全量 re-ACK，且重复 owner/split-brain prevention failure 为 0；下一步针对真实 secondary-interceptor 断链、peer 图分裂和不同节点时钟偏差，补齐 peer/digest 差异、恢复 merge audit 和长时恢复分布。分区侧不得绕过 plan version、lease 或 D5 友方/身份门控。
5. 当前 episode-time 正常场景的 false degradation 为 0；下一步用同 seed 的带宽受限、时钟漂移和真实网络时序成对场景统计 false/missed degradation、动作混淆矩阵和 dwell/release 抖动。阈值调整必须基于成对证据。
6. 在完全无中心 case 中持续把 D5 distributed visual evidence 合流到 `TrackSummary.visual_evidence`，并用多 seed 报告确认 CBBA completion/conflict/cost gap/round/message 指标。
7. main/D3 继续保存同场景中心化 cost matrix/current plan，D6 聚合 D4 `CBBACostGapBenchmark` 多 seed 指标；轻量 CBBA 仍为默认保底。
8. 复用已完成的 M5N2 20-case 几何/seeds 运行 secondary/distributed paired 故障场景，并补充 collision object/source lineage；不得以 `collision_stop` 或未进入 5 m 直接触发主动降级。
9. scalable3d episode bus 的单二级、多二级和 distributed D3 plan 接线已完成；下一步保持 owner/epoch/lease/commit/fault fence 回归，并补长时 200v200、多 seed stage timing、分区恢复、transition/churn 和 D6 汇总。D4 不越权修改 main-owned 文件。
10. main 后续如消费区域资源建议，只接 `d4-region-resource-advisory-v1`，每个 D3 planning boundary 用 current snapshot/formal verdict 重验并持久化 consumed advisory ID；不得直接消费 raw/non-projected recommendation。该工作属于 main/D3-owned 集成，本轮 D4 不越界修改。
11. 正式 writer 与 dataset-v1 已形成 900 episode 数据，行为克隆开发训练已完成。下一轮不直接启动 PPO：producer 需为 quota/transfer/hold/replan 生成可归因正样本，D6 需提供版本化 outcome/reward/causal/counterfactual availability、公式和审计制品 SHA256；缺失时继续 unavailable。重训后使用外部 seed 1000-1019 做 paired shadow，要求零安全违规且 backlog/fail-closed 不回归。满足前 bundle 保持 development/shadow-only，低损失不作为策略能力证据，也不改变正式 D4/D3/D7 裁决。
12. D4 共享切分消费端已经闭合。未来 D3/D4/D5 联合训练只能使用与同一 source training-seed-registry SHA 绑定的 canonical registry；不得回写原 manifest，也不得把共享切分视图作为模型晋级证据。其余模块消费端和联合训练编排由各 owner/main 分别验收。

P2：

1. **已完成 capability 收尾**：MIT CBBA/CA-CBBA 可选路径探测、标准 unavailable 行和原生 6 场景 replay 已实现；默认不执行外部工程。未来只有在许可证、源码和 runtime 均可用时才增加 execution adapter，并保持同一结果 schema。
2. 在多 seed CBBA gap benchmark 稳定后，可选实现独立 single-round auction baseline，用同一 `TrackSummary[]`/`ResourceSummary[]`/D5 evidence 输入与 CBBA 对照。
3. 设计 Contract Net 的 manager/contractor 状态机、超时、拒绝/重招标和 manager 失效回退规则。
4. 扩展 `merge_recovery()`，加入 track digest、plan digest、terminal lock、communication link、D5/D7 gate 状态和多轮稳定窗口。
5. 若 P1 多 seed 校准暴露恢复抖动，再扩展 `merge_recovery()` 的多轮稳定窗口和状态审计。

## 15. 验收命令

```bash
python3 -m py_compile \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_dataset.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/canonical_seed_split.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_learning.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_cli.py
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
