# 分布式协同与降级接管模块原理（模块编号 D4）

**状态日期**：2026-07-21
**适用范围**：离线科研仿真、合同验证、故障注入与评估日志。
**事实来源**：当前 D4 源码与测试、模块说明文件 `README.md`、模块计划文件 `PLAN.md`、D4 实现差距审计与综述，以及 2026-07-13 主级优先级 1 收敛验证报告 `MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`。
**状态声明**：本文只解释当前能力，不改变能力状态。凡标为“可选/离线”或“未实现”的内容，不属于默认在线主线。

**当前事实增量**：main-owned scalable 3D 质点模块栈已接入单一二级、多二级区域 owner 和中心/二级连续失效后的 distributed D3 plan；D7 依据 owner、plan version、epoch、lease、commit 与 fault generation fence 恢复导引。此前定向集成测试 8/8 passed，仅是质点接口证据。D4 同时具备默认 disabled/shadow 的区域资源学习建议层，以及 `d4-region-resource-advisory-v1` 后投影消费合同；它只建议区域配额和邻区转移，下一轮消费必须重验 current snapshot/authority，确定性 D4 安全状态机继续拥有健康检测、leader、epoch/lease、ACK/commit 和最终降级裁决。2026-07-21 新增独立动作覆盖补充课程，100 个 seed 的 300 帧中已形成 hold、request-replan、非零 quota 和 transfer 正类；该课程 reward/outcome 全部不可用，未改变正式 900 episode、PPO、assist 或在线裁决状态。

## 1. 模块定位与问题定义

### 1.1 模块定位

D4 是反无人机系统（Counter-Unmanned Aircraft System，C-UAS）多无人机流程中的分布式协同与降级接管模块。它位于上游态势、关联、分配和末端视觉证据与下游执行门控之间，负责回答“当前中心计划是否还能继续”“何时请求补充观测或中心重规划”“中心失效后由谁接管”“无中心时怎样保守维持任务连续性”。

本文中的指挥与控制（Command and Control，C2）表示中心协调权威及其健康状态；`C2Health` 是中心健康枚举。D1 至 D7 是仓库内的模块编号：D1 为传感器融合，D2 为数据关联，D3 为分配规划，D4 为本模块，D5 为末端关联，D6 为评估指标，D7 为比例导航与导引门控。

D4 的默认实现不是另一套常驻中心规划器。中心可用时，D3 仍拥有系统级分配计划；D4 只进行保守仲裁。只有中心被判定为 `failed`（失效）后，D4 才允许二级节点接管或进入完全分布式保底。

### 1.2 工程问题

当前实现针对以下工程问题：

1. **失效识别**：用心跳（heartbeat）、摘要校验值（digest）、世代号（epoch）和对等节点（peer）投票，区分短时抖动、可疑状态和中心失效。
2. **层级接管**：保持“中心 -> 二级协调节点 -> 完全分布式”的顺序，避免中心仍可用时直接争夺计划所有权（owner）。
3. **证据仲裁**：把 D1 协方差、D2 关联风险、D3 计划有效性和 D5 末端证据归一化为有限动作集合。
4. **接管可执行性**：把“二级节点看见目标”与“二级节点能持续接管”分开，要求覆盖、新鲜度、跨视角注册、租约（lease）、来源和计划版本同时满足。
5. **原子联盟安全**：多资源共同覆盖一个目标时，只有必要成员确认（Acknowledgement，ACK）齐全、版本一致且租约有效，才允许联盟进入可执行状态。
6. **无中心连续性**：使用一致性捆绑算法（Consensus-Based Bundle Algorithm，CBBA）风格的单获胜者协商作为一对一连续性保底，并显式报告收敛、冲突和通信开销。
7. **恢复防双主**：中心心跳恢复后先做双轨校验，不因单次恢复立即夺回所有权。
8. **建议消费防重放**：区域资源建议必须先形成内容寻址、限时、逐 generation 可审计的后投影合同；main 在下一轮规划边界重验后才能把它作为 D3 输入，同一 advisory 不得重复消费。

### 1.3 科学问题

D4 的研究问题不是“如何得到一次最优分配”，而是以下受不确定证据、通信退化和版本约束共同影响的序贯决策问题：

- 在观测误差、身份不确定和计划时效同时变化时，怎样降低误降级与漏降级；
- 在有限通信和节点失效下，怎样维持唯一可执行所有者并避免脑裂；
- 二级节点的覆盖质量、跨视角注册质量和证据持续时间怎样共同决定接管能力；
- 分布式保底相对中心化基线会付出多少代价、完成率和通信轮次损失；
- 多资源对多目标（Multiple Resources to Multiple Targets，M-to-N）问题中，怎样把单获胜者协商与多成员原子提交严格分开。

### 1.4 明确边界

D4 当前只处理粗粒度摘要、内存网络、状态机、仲裁结果、回放（replay）和审计元数据（metadata）。它不负责：

- 启动、重置或编排微软 AirSim 无人系统仿真器；这些属于主编排器（main）和运行时（runtime）；
- 图像像素投影、检测框几何、多视角视觉注册或局部视觉身份生成；这些属于 D5 和 main；
- 创建、改写或本地重绑定 `global_track_id`（中心拥有的全局航迹标识）；
- 生成完整系统级 `AssignmentPlan`（版本化分配计划）；D3/main 拥有其模式、所有者与版本事实；
- 真实无线频率（Radio Frequency，RF）链路、网络设备、套接字、视频传输、硬件驱动或飞行控制；
- 真实火控、毁伤、自动授权、自动处置或绕过人工审核。`hold_for_review`（保持并请求复核）始终是安全结果之一。

D4 按输入列表长度运行，不把 2 对 2、5 对 5 或任意 N 对 N 场景写死为算法规模。

## 2. 默认主线与分层架构

### 2.1 默认主线

当前默认主线为：

```text
D1 融合航迹与协方差
  -> D2 关联连续性和重复风险
  -> D3 中心版本化分配计划
  -> D4 保守仲裁
       中心可用：继续中心 / 请求二级观测辅助 / 请求中心重规划 / 保持复核
       中心失效：二级节点接管 / 完全分布式保底 / 保持复核
  -> D5 末端身份与视觉锁定继续独立门控
  -> D7 导引合同继续独立门控
  -> D6 只读评估与报告
```

主动降级 `active_degradation`（主动降级模式）处理“中心仍可用，但证据要求重新评估当前计划”；被动降级 `passive_failover`（被动接管模式）处理“中心已失效”。两者不能混写：

- 主动降级不会直接把所有权转给二级或分布式节点；
- `degrade_to_secondary`（降到二级节点）和 `degrade_to_distributed`（降到完全分布式）只属于中心失效后的接管路径；
- `request_secondary_assist`（请求二级观测辅助）不等于二级接管；
- `request_center_replan`（请求中心重规划）不等于 D4 自己生成新计划。

### 2.2 二级节点角色

二级节点可由地面备份、固定系留侦察节点、机动高空侦察节点或二级侦察节点表示。`coordinator_only`（仅协调标志）默认使其只提供区域协调与观测证据，不作为拦截执行资源参与 CBBA 出价。

中心可用时，二级节点最多提供区域图像线索、覆盖摘要和跨视角支持。中心失效后，只有二级节点通过瞬时能力门限和持续就绪性（readiness）窗口，才可成为接管候选。二级节点不可用、不可达、覆盖不足或证据不持续时，才进入完全分布式保底。

## 3. 输入、核心数据结构与输出

### 3.1 上游输入

| 来源 | 当前 D4 输入 | 关键字段及中文释义 |
|---|---|---|
| D1 | `TrackUncertaintySummary`（航迹不确定度摘要） | `track_id`（航迹标识）、`coverage_cell`（覆盖小区）、`position_sigma_m`（位置标准差，米）、`covariance_trace`（协方差迹）、`velocity_sigma_mps`（速度标准差，米每秒）、`measurement_age_s`（量测年龄，秒） |
| D2 | `AssociationRiskSummary`（关联风险摘要） | `ambiguity_score`（歧义评分）、`id_switch_count`（身份切换计数）、`duplicate_track_count`（显式重复航迹计数）、`duplicate_track_risk`（连续重复风险评分）、`track_continuity`（航迹连续率）、`truth_metrics_available`（真值指标是否可用）、`continuity_available`（连续率是否可用） |
| D3 | `AssignmentValiditySummary`（分配有效性摘要） | `global_track_id`（全局航迹标识）、`assigned_resource_id`（已分配资源标识）、`plan_version`（计划版本）、`is_current`（是否当前版本）、`plan_age_s`（最近评估活性年龄）、`cost_margin`（当前方案相对备选的代价裕度）、`resource_feasible`（资源是否可行） |
| D5 | `TerminalAssociationSummary`（末端关联摘要） | `decision_state`（锁定、歧义、保持或重捕获状态）、`terminal_evidence_applicable`（末端证据是否处于适用窗口）、`association_confidence`（关联置信度）、`ambiguity_score`（末端歧义）、`observed_global_track_id`（观测到的全局航迹标识）、连续非锁定/不一致计数、友方冲突、重复锁定、跨视角支持和二级覆盖诊断 |
| main/runtime | `C2Health`（中心健康）、`ResourceSummary[]`（资源摘要列表）、`CommunicationSummary[]`（通信摘要列表）、当前计划与联盟版本、二级计划回填状态 | 当前时间、心跳、链路新鲜度、计划所有者、计划/联盟版本、租约世代、租约到期时间、重规划请求状态、联盟提交状态 |

D1 仍以北-东-地（North-East-Down，NED）坐标系作为融合工作坐标；D4 不做坐标变换，只消费协方差和粗粒度覆盖小区。D4 不使用在线仿真真值生成身份结论。

### 3.2 适配原则

`D4ArbitrationAdapter`（D4 仲裁适配器）使用对象属性或字典字段读取上游数据，不直接导入 D1、D2、D3、D5 的实现类型。适配器按以下顺序构造证据：

1. 解析资源和全局航迹标识；
2. 从协方差构造 D1 不确定度摘要；
3. 区分 D2 连续风险评分与显式已发生事件；
4. 从 D3 最近评估时间计算计划活性年龄；
5. 先构造 D3 联盟安全证据，再归一化 D5 末端证据；
6. 按 `(resource_id, global_track_id)`（资源标识与全局航迹标识对）选择独立仲裁器，避免一个资源/航迹对的迟滞状态污染其他对；
7. 构造二级节点生命周期和持续就绪窗口；
8. 运行仲裁、联盟安全门控、中心重规划生命周期和二级计划生命周期；
9. 输出 D6 可消费的决策记录。

### 3.3 被动降级与 CBBA 数据结构

- `TrackSummary`（航迹任务摘要）：包含 `track_id`（任务使用的上游航迹标识）、`coarse_cell`（粗粒度区域）、`age_s`（年龄）、`confidence_band`（置信等级）、`source_count`（来源数）、`epoch`（世代号）和 `visual_evidence`（分布式视觉证据）。它还可携带 `required_resource_count`（所需资源数）和联盟版本，但轻量 CBBA 只处理单获胜者分配。
- `ResourceSummary`（资源摘要）：包含节点角色、能力类别、可用性、通信等级、人工保持标志、接管优先级、租约、心跳、覆盖、线索新鲜度、云台指向和跨视角注册摘要。
- `BidState`（出价状态）：包含 `task_id`（任务标识）、`bidder`（出价节点）、`score`（出价评分）、`constraints_hash`（约束摘要哈希）、`epoch`（世代号）和 `round_id`（协商轮次）。
- `CBBAResult`（CBBA 结果）：包含唯一任务所有者、共识轮数、是否收敛、冲突计数、完成率、消息计数、估计字节数、最终视图和分配审计。

### 3.4 二级接管数据结构

`SecondaryNodeLifecycleSummary`（二级节点生命周期摘要）同时保存：

- 心跳年龄、心跳是否陈旧；
- 租约世代、租约到期时间和是否过期；
- 覆盖小区是否匹配、覆盖比例；
- 图像线索新鲜度、链路新鲜度和云台指向；
- 是否可见、是否完成稳定跨视角注册、综合能力评分；
- `secondary_readiness_class`（二级就绪等级）：`not_ready`（未就绪）、`visible_only`（仅可见）、`registration_usable`（注册可用但不足以接管）、`takeover_ready`（可接管）；
- 连续就绪决策数、就绪起始时间、持续时间、是否满足持续窗口和回落原因。

`SecondaryTakeoverPlanMetadata`（二级接管计划元数据）只描述状态，不创建系统计划。它有三态：

- `not_applicable`（不适用）；
- `pending_secondary_plan`（二级计划待生效）：D4 已选择来源节点，但当前所有者不变；
- `secondary_plan_active`（二级计划已激活）：main/D3 已回填正确来源、新计划标识与版本、有效租约，且持续就绪没有回落。

### 3.5 原子联盟数据结构

- `CoalitionMemberAck`（联盟成员确认）：绑定资源、全局航迹、联盟标识/版本、计划标识/版本、世代号、成员可执行性、证据时间和有效期。
- `CoalitionCommitState`（联盟提交状态）：记录协调者、必要成员、已确认成员、租约和 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted`（提议、收集确认、已提交、执行中、重构中/已中止）生命周期。
- `CoalitionSafetyEvidence`（联盟安全证据）：记录中心是否可用、联盟是否完整、授权/锁定成员、双版本、冲突原因、原子联盟是否形成、候选动作与门控后动作。

### 3.6 下游输出

| 输出 | 消费方 | 语义 |
|---|---|---|
| `ActiveDegradationDecision`（主动/被动仲裁决策） | main、D6 | 动作、模式、原因、目标二级节点、风险因子、当前绑定是否可信、是否需人工复核 |
| `D4DecisionRecord`（D4 决策记录） | main、D6 | 完整输入摘要、硬/软风险、二级生命周期、接管状态迁移、重规划冷却、联盟门控和审计字段 |
| `SecondaryTakeoverPlanMetadata` | main、D3、D7 | 二级计划待生效/已激活、来源、版本、租约和可执行性；不是系统计划 |
| `D7SecondaryHandoff`（D7 二级交接门控） | D7 | 两阶段交接；阶段 1 不允许视觉比例导航制导（Proportional Navigation Guidance，PNG），阶段 2 仍需新计划和 D5/D7 独立条件 |
| `CBBAResult` | main、D6 | 一对一无中心保底结果与收敛、冲突、完成率、消息开销 |
| `MergeResult`（恢复合并结果） | main、D6 | 中心与降级计划的接受、复核、冲突和是否恢复正常 |
| `EpisodeCommunicationTick`（单次试验时钟步通信状态） | main、D6 | 每时钟步的健康、层级、所有者、版本、ACK、租约、提交、闭锁和恢复状态 |
| `RegionResourceSnapshot`（区域资源快照） | 规则/可选学习建议层 | 版本化、truth-free 变长区域图；含聚合需求、不确定性、可见/一致性、资源/备用、二级和通信、当前 authority fence |
| `RegionResourceRecommendation`（区域资源建议） | main、D6、shadow evaluator | 只含区域配额增减、邻区转移、备用比例、侦察优先级和 hold/replan；不是 D3 assignment，也不授权 D7 |
| `RegionResourceAdvisoryContract`（后投影建议合同） | main 下一轮规划边界 | 内容寻址 ID、创建时间/有效期、scenario/snapshot/authority、source plan、policy/model/projector identity，以及逐区域/transfer generation、资源和 edge 安全证明；不含目标级分配 |
| `RegionResourceConsumptionView`（消费判定视图） | main | 在 current snapshot/formal verdict 上输出 `consumable` 与稳定拒绝原因；`true` 只表示可作为 D3 下一轮输入，不表示已生成计划或获执行授权 |
| `RegionLearningEpisodeSource/Frame`（区域学习 episode 数据） | main writer、离线训练 | source 固化 scenario/version/scale、seed、episode/Git/config identity；frame 固化 truth-free snapshot、显式 target/reward availability 和可选 recommendation |

### 3.7 区域资源快照与动作边界

区域节点必须包含目标需求和高威胁积压的聚合值、D1/D2 不确定性、D5 可见性/一致性、可用资源与备用、二级覆盖/就绪、通信容量/时延/丢包，以及当前 owner layer/node、plan version、epoch 和 lease。区域边包含可转移资源、距离、转移时间、带宽、通信/机动可用性与 partition。合同递归拒绝 actor/target/truth identity 和 `global_track_id` 字段。

建议动作不能列出资源成员或目标标识。`resource_quota_delta` 由投影后的邻边 transfer 重新计算，所有区域之和必须为零；模型不能通过直接写 quota delta 绕开资源守恒。`reserve_ratio`、`reconnaissance_priority`、`hold` 和 `request_replan` 只表达建议，不改变 formal D4 verdict。

规则 fallback 与学习候选在 `RegionResourceAdvisor` 内共享同一 `DeterministicResourceProjector` 实例；学习模型只能返回 `projected=false` 的 raw proposal。投影器随后生成 `d4-region-resource-advisory-v1`：`advisory_id` 是合同内容的 SHA256 幂等键；默认有效期为创建后 1.0 episode-clock 秒，并取所有区域 authority lease 的最早截止。每个区域记录 source snapshot/version/authority、owner/layer、plan id/version、epoch/lease、ACK/fault、资源前后量、protected reserve/committed；每个 transfer 还记录两端 generation、edge 端点、capacity、transfer time、bandwidth 和通信/机动/partition 状态。

消费门严格使用 `evaluated_at < valid_until`。旧 snapshot/plan/epoch、lease 到期、非 projected、ACK 不完整、fault fence、formal verdict 变化、资源不守恒、reserve/committed 保护失败、未知/非邻接/不可用/超 capacity transfer，或已在 gate 中成功消费过的 `advisory_id`，均输出 `consumable=false`。当前 gate 的 replay ledger 是进程内集合；跨进程运行时由 main 持久化。D4 不借此创建或修改 D3 `AssignmentPlan`。

### 3.8 区域学习 episode 数据治理

`d4-region-learning-dataset-v1` 以完整 episode 为最小持久化和 split 单元。source 必须记录 scenario/version/scale、数值 seed、episode ID、Git commit/dirty 与 config SHA256；每帧 target 只能是区域级 `rule|formal` 投影建议或带原因的 unavailable，reward 同样必须显式 available/unavailable，可选 recommendation 只作记录。任何 target/actor/global-track/evaluator/offline truth key 都被拒绝，不能进入在线特征。

stage 产物使用 canonical JSONL header/frame/footer 和 frame SHA；finalizer 再固化逐 episode SHA、dataset SHA、feature/target/reward semantics、全部 source identity 和 availability。同一数值 seed 下的不同场景、规模和多个 episode 原子进入同一 train/validation/test split，三份 seed 两两零交集；唯一 seed 少于 3 或实际 unseen 少于声明下限时不生成 dataset。BC loader 缺 target 即失败，PPO loader 缺 target 或 reward 即失败，二者默认拒绝 dirty source，不以 0 填补。`model-bundle-v2` 可嵌入并验证 dataset/split manifest；这些数据治理能力不改变 D4 authority、lease、epoch、CBBA、联盟或降级状态机。

### 3.9 正式行为克隆与准入边界

2026-07-20 正式数据包含 900 episode 和 1798 frame。训练、验证、内部测试分别使用 70、15、15 个数值 seed，外部保留 seed 1000-1019 不在数据集中。审计重新计算 900 个 episode SHA256，并核对 dataset/source/schema、Git/config identity 和 split hash。固定 seed `20260720` 的行为克隆在 CPU 单线程完成 66 epoch，最佳 epoch 为 54；内部测试损失为 `0.071545`。2026-07-21 准入复跑的端到端建议与投影推理 P95 为 `0.7774 ms`，本地权重 SHA256 仍为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。

数据中的 14384 个区域动作没有非零配额、跨区域转移、保持或重规划正样本。保留比例和侦察优先级存在变化，模型可复现这两个连续字段；配额和转移的零误差只反映零动作基线。D6 审计还发现 898/1798 帧只有无归因相邻状态转移，reward、causal label 和 counterfactual label 可用数均为 0。模型置信度头没有校准标签。由此，训练管线可用，但动作多样性不足；低损失不构成完整动作策略能力证据，PPO 不可启动。

模型 manifest 固定 `lifecycle_stage=development`、`maximum_advisor_mode=shadow`、`action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`，并保存五项动作计数。`RegionResourceAdvisor` 会读取模式上限；即使请求 `assist` 并传入 20 个 unseen seed，也只能保持 shadow。权重位于 Git 忽略目录，当前无 Git LFS；普通 Git 只记录训练配置、数据/模型准备度、指标、训练命令、权重 SHA256 和本地相对定位。

### 3.10 共享 seed 切分视图

联合训练不能分别沿用 D3、D4、D5 的模块内 split，否则同一数值 seed 可能在一个模块用于训练、在另一个模块用于测试。D4 新增只读 canonical view，消费 main 发布的 `scalable3d-shared-seed-split-registry-v1`，但不导入 main runtime。消费者独立复现 D3 兼容哈希排序，并校验 registry schema/policy、content/assignment SHA、源 training-seed-registry SHA、100 个 dataset seed 的完整覆盖、无额外 seed 和 1000-1019 保留集隔离。

canonical view 是冻结内存覆盖层。它保存每个 episode 的原 split 和共享 split，并绑定原 dataset SHA、原 split SHA、manifest 文件 SHA、共享 registry 文件/内容 SHA、assignment SHA 和源 registry SHA。源 manifest 与 episode 文件不修改。BC loader 只有显式传入 view 时采用共享 60/20/20；默认仍使用原 70/15/15。

正式 900 episode 的共享视图包含 60/20/20 seed、540/180/180 episode 和 1079/359/360 frame。源数据目录树在审计前后哈希相同。该能力解决数据治理问题，不证明模型收益，不解除动作多样性、reward、PPO 或 assist 门槛。

### 3.11 区域动作覆盖补充课程

`d4-region-action-coverage-curriculum-v1` 是独立的规则 teacher 数据源。它不从正式 episode 抽取标签，也不修改正式 900 episode。生成器读取共享训练 seed 注册表，对每个数值 seed 依次构造三种区域聚合状态：降级失败触发保持、分配冲突触发中心重规划请求、相邻区域余量和需求缺口触发资源转移。动作由现有 `RuleRegionResourcePolicy` 生成，再由 `DeterministicResourceProjector` 投影；课程自身不能直接写入可信 quota。

本次配置为 4 个区域、17 份聚合资源、100 个 seed、每 seed 3 帧。结果含 hold 100、request-replan 200、非零 quota action 200、transfer 100。canonical 训练、验证、测试桶为 60/20/20 seed，每个桶都有四类动作。硬约束违规、在线真值字段和保留 seed 泄漏均为 0。

课程没有动作执行后的真实结果。300 帧 reward 和 outcome 全部显式 unavailable，因此只能用于行为克隆 teacher 覆盖和离线 shadow。当前实际制品来自 dirty worktree，默认行为克隆加载器会拒绝；clean fixture 已验证 canonical 训练桶 180 帧可加载，PPO loader 因 reward unavailable 失败关闭。该结果关闭 producer 和标签覆盖接口缺口，不关闭策略有效性、因果归因、外部保留 seed 性能或在线准入。

## 4. 数学模型与核心公式

### 4.1 集合、状态与决策

设资源集合为

\[
\mathcal{R}=\{r_i\}_{i=1}^{M},
\]

目标任务集合为

\[
\mathcal{T}=\{t_j\}_{j=1}^{N}.
\]

这里，\(M\) 是输入资源数，\(N\) 是输入任务数；二者由 main 的场景输入决定，不固定为 2 或 5。对一对一保底任务，D4 寻找映射 \(a:t_j\mapsto r_i\)。对需要 \(k_j>1\) 个资源的任务，必须使用联盟 \(\mathcal{C}_j\subseteq\mathcal{R}\) 和原子提交门控，不能把一条任务复制 \(k_j\) 次来冒充联盟。

D4 决策函数可抽象为

\[
d_t=\pi(z_t,h_t,m_t),
\]

其中 \(z_t\) 是 D1/D2/D3/D5 的当前证据，\(h_t\) 是中心与二级节点健康，\(m_t\) 是迟滞、重规划请求、计划与联盟提交的内部记忆；\(d_t\) 只取六种实现动作之一。

### 4.2 中心健康判定

令最近一次有效中心心跳时间为 \(t_{hb}\)，当前时间为 \(t\)，心跳年龄为

\[
\Delta t_{hb}=t-t_{hb}.
\]

`FailoverCoordinator`（降级协调器）的默认阈值是：预警 1 秒、陈旧 2 秒、失效 4 秒。心跳窗口长度为 5，退化、可疑和失效的默认缺失计数阈值分别为 1、2、3。窗口缺失数为

\[
m_t=\sum_{q\in W_t}\mathbf{1}[q=\text{缺失}],
\]

其中 \(W_t\) 是最近五个心跳样本，\(\mathbf{1}[\cdot]\) 是条件成立时取 1 的示性函数。实际迁移还受状态驻留时间和 peer 多数阈值约束。若参与判定的节点数为 \(n\)，默认多数阈值为

\[
q=\left\lfloor\frac{n}{2}\right\rfloor+1.
\]

只要 peer 失效票数达到 \(q\)，中心可直接进入 `failed`。反向恢复不对称：恢复心跳和 digest 只使状态进入 `suspect`（可疑），必须通过双轨合并与显式接受才能回到 `normal`（正常）。

### 4.3 协方差到 D1 风险

适配器从上游协方差矩阵 \(P\) 取位置子矩阵 \(P_p\) 和速度子矩阵 \(P_v\)。位置标准差定义为

\[
\sigma_p=\sqrt{\max(\lambda_{\max}(P_p),0)},
\]

其中 \(\lambda_{\max}(P_p)\) 是位置协方差最大特征值；速度标准差定义为

\[
\sigma_v=\sqrt{\max(\operatorname{tr}(P_v),0)}.
\]

当前规则中，\(\sigma_p\ge 20\) 米产生中等位置不确定风险，\(\sigma_p\ge 50\) 米产生高风险；\(\operatorname{tr}(P)\ge 2500\) 产生高协方差风险；量测年龄大于 4 秒产生陈旧量测风险。这些是离线规则阈值，不是传感器物理认证参数。

### 4.4 D2、D3 与 D5 风险门限

D2 当前门限为：

- 关联歧义 \(a_2\ge0.35\) 为中等风险，\(a_2\ge0.70\) 为高风险；
- `duplicate_track_risk`（重复航迹连续风险）\(\ge0.50\) 只产生软观察证据；
- 只有显式重复计数、增量或已观测标志才产生硬重复事件；
- 只有 `truth_metrics_available=true`（真值指标可用）时，`id_switch_count>0`（身份切换计数大于零）才成为硬风险；身份切换（Identity Switch，IDSW）不会由不可用真值的占位数值推断；
- 只有 `continuity_available=true`（连续率可用）时，连续率 \(<0.60\) 才成为硬风险。

D3 当前门限为：

- `is_current=false`（不是当前计划）、计划活性年龄大于 4 秒或资源不可行是硬风险；
- `cost_margin<0.10`（代价裕度过低）是软证据，不能单独触发逐帧重规划；
- 计划年龄优先以最近评估时间计算，计划创建时间只在缺少最近评估时间时回退使用，因此稳定计划标识不会仅因存在时间较长而被误判陈旧。

D5 中，友方冲突、重复末端锁定、资源与分配不一致、已分配/已观测全局航迹不一致属于硬绑定或身份证据。低置信度（小于 0.65）、高末端歧义（大于等于 0.55）和高跨视角风险（大于等于 0.65）只在末端证据适用窗口内作为软风险。

### 4.5 末端绑定与末端视觉准备度分离

令当前 D3 绑定为 \((r_a,g_a,v_a)\)，分别表示资源、全局航迹和计划版本；D5 末端摘要提供 \((r_o,g_o)\)。D4 的 `terminal_consistent`（当前计划绑定是否可信）要求没有以下硬拒绝原因：

\[
r_o\ne r_a,
\quad g_o\ne g_a,
\quad \text{友方冲突},
\quad \text{重复锁定},
\quad \text{计划陈旧、非当前或不可行}.
\]

低置信度、歧义、`reacquire`（重捕获）或连续未锁定本身不证明中心绑定错误。它们只描述视觉准备度，并由 D5/D7 独立决定是否允许后续导引。这个分离修复了历史上 D4 重复解释 D5 就绪性、导致无硬冲突时 `terminal_consistent=false` 的问题。

`terminal_evidence_applicable=false`（末端证据尚不适用）时，远距阶段的普通低置信度、歧义、跨视角软风险和未锁定连续计数不参与辅助/重规划动作；明确观测航迹错配、资源错配、重复锁定和友方冲突仍立即有效。

### 4.6 二级节点能力评分

对候选二级节点，D4 构造以下归一化分量：

- \(c\)：覆盖比例；
- \(n\)：网络同帧全覆盖率；若缺失，则回退为 \(c\)；
- \(r\in\{0,1\}\)：是否有稳定注册；
- \(h,l,u\in\{0,1\}\)：心跳、链路、线索是否新鲜；
- \(f=(h+l+u)/3\)：综合新鲜度；
- \(g\in\{0,1\}\)：云台指向是否可用。

当前综合能力评分为

\[
S_{sec}=\operatorname{clip}_{[0,1]}(
0.25c+0.15n+0.25r+0.15f+0.10g+0.05u+0.03l+0.02h
).
\]

式中各变量都是摘要证据，不是图像几何计算。四级分类为：

1. **未就绪**：节点不可用、覆盖为零、心跳/租约/线索/链路/云台条件失败；
2. **仅可见**：可见但没有稳定跨视角注册；
3. **注册可用**：已有注册，但 \(c<0.65\)、可用的 \(n<0.80\) 或 \(S_{sec}<0.70\)；
4. **可接管**：可见且已注册，并满足覆盖、网络全覆盖和综合评分门限。

若网络全覆盖率没有提供，代码不以缺失值直接判失败；它用覆盖分数参与评分并把网络门限视为可用。真实接线应尽量提供该字段，以减少乐观缺省。

### 4.7 持续就绪与二级节点选择

瞬时 `takeover_ready` 不足以接管。对节点 \(s\)、航迹 \(g\) 和覆盖小区 \(c\) 的组合，持续就绪条件为

\[
R_{s,g,c}(t)=
\mathbf{1}[K\ge3]
\cdot\mathbf{1}[t-t_0\ge0.2]
\cdot\mathbf{1}[\Delta t_{evidence}\le1.0],
\]

其中 \(K\) 是不同时间戳上的连续可接管判定数，\(t_0\) 是本次连续就绪起点，\(\Delta t_{evidence}\) 是相邻证据间隔。相同时间戳的多资源/多目标重复调用不增加 \(K\)；时间倒退、间隔超过 1 秒或能力回落会从 1 重新计数。

通过所有硬过滤后，候选按以下字典序排序：

\[
(\text{更小接管优先级},
\text{更高能力评分},
\text{节点类别秩},
\text{更新租约世代},
\text{节点标识}).
\]

机动高空侦察、机动二级侦察、固定系留二级、普通二级侦察、地面备份依次参与类别秩比较。持续条件不满足时，候选二级接管会保守回落为分布式路径或待生效/不可执行状态，而不是放宽门限。

### 4.8 CBBA 出价与视觉修正

当前轻量 CBBA 对资源 \(i\) 和任务 \(j\) 的基础评分为

\[
B_{ij}=2.0C_j+1.4A_i+0.5L_i+1.2M_{ij}+1.0Q_j-0.8D_j+V_{ij}-0.15|b_i|.
\]

变量物理意义如下：

- \(C_j\in\{1,2,3\}\)：任务低、中、高置信等级；
- \(A_i\in\{0,1,2,3\}\)：资源无、低、中、高可用等级；
- \(L_i\in\{0.5,1.0,1.5\}\)：通信差、受限、良好等级；
- \(M_{ij}\)：能力匹配分，`observe`（观测）为 1.0，`relay`（中继）按来源数为 0.85 或 0.65，`hold`（保持）为 0.2，其他为 0.5；
- \(Q_j=0.15\min(\text{来源数},3)\)：多来源奖励；
- \(D_j=\min(\max(\text{航迹年龄},0),30)/30\)：航迹年龄惩罚；
- \(V_{ij}\)：D5 分布式视觉证据修正；
- \(|b_i|\)：资源当前任务束（bundle）长度。

视觉修正遵循“支持可加分、身份冲突可阻断”：

- 当前资源有直接视觉支持时，完整证据最多加 2.75；仅假设证据最多加 0.75；
- 其他资源被支持而当前资源不在支持集合时减 1.25；
- 当前资源歧义减 1.25，并按末端歧义再减最多 1.0；
- 重复锁定风险对相关资源减 2.5，对其他资源减 0.75；局部身份冲突再减 1.0；
- 友方冲突、陈旧/缺失/冲突全局航迹标识或当前资源处于保持集合时，直接不产生可执行出价。

获胜比较首先看更新世代，再看更高评分；评分在 \(10^{-9}\) 容差内相同时，使用更小节点标识和更小约束摘要确定性消歧。只有所有节点对每个任务的获胜者和评分视图一致时才算收敛；未收敛时 `assignments`（分配结果）为空，不发布为有效保底计划。

若通信图边集合为 \(\mathcal{E}\)，任务数为 \(|\mathcal{T}|\)，每轮获胜者/出价（winner/bid）传播的量级为

\[
O(|\mathcal{E}|\,|\mathcal{T}|).
\]

全连接 \(M\) 节点网络约为 \(O(M^2|\mathcal{T}|)\)。稀疏网络降低单轮消息量，但通常增加传播轮数。当前 `SimulatedNetwork`（内存仿真网络）只使用均匀延迟和独立丢包近似，不代表真实网络队列与协议。

### 4.9 原子联盟提交条件

对需要 \(k_j>1\) 个资源的目标，设必要成员集合为 \(R_j\)，已确认集合为 \(A_j\)。一个降级保底（fallback）联盟可进入 `committed`（已提交）或 `executing`（执行中）的必要条件可写为

\[
G_j=
\mathbf{1}[A_j=R_j]
\mathbf{1}[t<t_{lease}]
\mathbf{1}[v_p=v_p^*]
\mathbf{1}[v_c=v_c^*]
\mathbf{1}[e=e^*]
\mathbf{1}[d=d^*]
\mathbf{1}[\text{成员可执行}],
\]

其中 \(t_{lease}\) 是联盟租约到期时间，\(v_p\) 和 \(v_c\) 是计划与联盟版本，\(e\) 是世代号，\(d\) 是联盟摘要。只有 \(G_j=1\) 才设置 `atomic_coalition_formed=true`（原子联盟已形成）。缺 ACK、旧版本、旧世代、过期租约、非必要成员确认、成员不可执行、网络分区或 digest 冲突都保持失效时闭锁（fail closed）。

合法联盟内多个授权资源锁定同一 `global_track_id` 不算重复所有者；联盟外、超额或旧版本资源锁定会被拒绝。轻量单获胜者 CBBA 不承担 \(k_j>1\) 的成员形成。

### 4.10 离线代价差距

若 D3/main 提供同一场景的中心计划和代价矩阵，D4 可计算

\[
\Delta C=C_{CBBA}-C_{center},
\qquad
\delta C=\frac{\Delta C}{|C_{center}|},
\]

其中 \(C_{CBBA}\) 是 D4 保底分配总代价，\(C_{center}\) 是中心化计划总代价。若任一已分配任务/资源对缺少代价，总代价和差距保持不可用，不补造数值。该辅助函数（helper）只做离线比较，不在无中心路径运行匈牙利算法（Hungarian algorithm）或最小费用流（Minimum Cost Flow）。

### 4.11 区域所有权与世代

scalable3d 区域集合记为 \(\mathcal{R}\)。每个区域只能有一个 active owner：

\[
\forall r\in\mathcal{R},\quad \sum_o \mathbf{1}[owner(r)=o\land active(r)]\le 1.
\]

中心未失效时 owner 保持中心，D1/D2/D3/D5 主动证据只能请求辅助、重规划或保持复核；中心计划中的 \(k>1\) 任务也必须完整 ACK 后才把 owner 标为 active。中心失效后，机动高空二级节点必须对区域具有显式 coverage，并满足完整 strict readiness 与 `secondary_lease_epoch >= authority_epoch`。只有无有效二级节点时才进入受约束 distributed candidate formation。owner/layer 切换要求 `epoch` 与 `plan_version` 同时严格递增；同 generation 换 owner、过期租约或任一层级分区都闭锁。区域 authority/commit lease 取 authority、D3 task 和二级 lease 的最早 expiry。区域候选形成按 capability、跨区域 capacity、communication 和 D5 member evidence 做确定性选择，一个成员可覆盖多项 capability，但 \(k>1\) 的可执行性仍由第 4.9 节完整 ACK 决定。

### 4.12 区域资源安全投影与学习奖励

设区域配额变化为 \(\Delta q_r\)，接受的有向邻边转移为 \(x_{uv}\)。确定性投影强制：

\[
\sum_{r\in\mathcal R}\Delta q_r=0,\qquad
\Delta q_r=\sum_u x_{ur}-\sum_v x_{rv}.
\]

仅当边可通信、可机动且未 partition 时允许 \(x_{uv}>0\)，并满足 edge capacity。源区域转出后必须保留已提交联盟资源和最低备用；owner/plan/epoch/lease 与 formal verdict 不一致、fault fence、缺 ACK 或过期 lease 时该区域 transfer 为零并进入 hold。学习奖励是以下代价的负加权和：高威胁积压、跨区转移耗时、通信负载、备用不足、分配冲突、降级失败和计划抖动。奖励不能减弱任何安全投影条件。

## 5. 算法步骤

### 5.1 每次仲裁的默认步骤

1. **解析绑定**：确定资源标识、全局航迹标识、覆盖小区和当前计划版本。
2. **归一化 D1-D5 证据**：计算协方差风险、关联风险、计划活性与末端证据适用性。
3. **构造联盟安全证据**：校验需求数、成员、计划/联盟双版本、视觉共识和可选原子提交。
4. **更新二级生命周期**：检查心跳、租约、覆盖、线索、链路、云台和跨视角注册，计算能力评分与四级就绪性。
5. **更新持续窗口**：按节点、航迹和覆盖小区累计不同时间戳的连续就绪证据。
6. **运行基础仲裁**：先处理友方冲突，再处理中心失效，然后处理中心计划硬失效、远距软证据、末端持续不一致和一般风险。
7. **应用迟滞**：在风险窗口未满足或释放条件未满足时保持原动作。
8. **应用联盟安全门控**：多成员降级保底没有合法原子提交时，中心可用则请求重规划，中心不可用则保持复核。
9. **应用中心重规划生命周期**：抑制冷却期内重复的非硬请求；硬安全风险不受抑制。
10. **应用二级计划门控**：校验来源、持续就绪、版本单调、租约世代和租约到期时间。
11. **输出审计记录**：把候选动作、最终动作、硬/软风险、状态迁移和拒绝原因交给 main/D6。

### 5.2 中心可用时的动作优先级

1. 友方冲突：`hold_for_review`。
2. D3 计划非当前、陈旧、资源不可行，或明确资源/身份硬错配：`request_center_replan`。
3. 末端证据尚不适用，且只有软风险：`continue_center`，但保留风险审计。
4. 末端窗口内持续 `ambiguous/hold/reacquire`，但没有身份或绑定硬冲突：有健康二级节点则 `request_secondary_assist`，否则继续中心观察。
5. D1/D2 风险升高而当前绑定仍可信：优先请求二级辅助；若没有辅助节点且风险属于硬主动仲裁因素，则请求中心重规划。
6. 风险低且绑定可信：`continue_center`。

### 5.3 中心失效时的被动接管

1. 只有 `C2Health.FAILED`（中心失效）才启动被动接管。
2. 过滤处于人工保持、无可用性、覆盖不匹配、心跳/租约/线索/链路陈旧或云台不可用的二级节点。
3. 对剩余候选计算瞬时评分和持续就绪；满足后输出 `degrade_to_secondary`。
4. 二级节点不满足持续条件时输出 `degrade_to_distributed`，进入轻量 CBBA 或原子联盟提交路径。
5. 一对一 CBBA 未收敛时不发布分配；多成员联盟无完整提交时保持复核或撤销。

### 5.4 单次试验时钟通信状态机

`AirSimEpisodeCommunicationAdapter`（AirSim 单次试验通信适配器）不启动 AirSim，只消费 main 提供的严格递增单次试验（episode）时间戳。默认验证配置为：中心预警 0.5 秒、中心失效 1.0 秒、二级心跳陈旧 0.75 秒、ACK 截止 0.75 秒、ACK 有效期 1.0 秒、联盟租约 10 秒、恢复需连续 2 个 digest 匹配时钟步。

每个时钟步（tick）的处理顺序为：

1. 记录中心与二级心跳；
2. 分类中心健康，选择期望层级；
3. 递送到期 ACK，并拒绝旧世代、旧计划版本或过期 ACK；
4. 若需要接管，提升 epoch、计划版本和联盟版本，清空可执行所有者并开始收集 ACK；
5. 全部必要成员确认后从 `committed` 进入 `executing`，才发布单一可执行所有者；
6. 截止时间到达仍缺 ACK 时中止；分区时清空降级保底所有者；
7. 中心恢复时连续校验双轨 digest，且必须收到显式恢复授权，之后再以新世代恢复中心。

该适配器的 `owner_id`（所有者标识）是层级/计划发布提示，main 仍负责生成系统级计划。

### 5.5 scalable3d 区域仲裁步骤

1. 从 `scalable3d-scenario-v1` mapping 读取 target/resource/recon/region count，不导入 main 模块。
2. 校验 schema、scenario 声明数量、region definition、active task、secondary coverage 和 fallback member region scope。
3. 按区域聚合 D1 covariance/age、D2 ambiguity/IDSW/duplicate、D3 plan/version/epoch/lease/current/feasible 和 D5 consistency/binding/friend/duplicate。
4. 中心未 `failed` 时保留中心 owner；中心 `failed` 时选 valid `mobile_high_recon`；没有有效二级节点时才形成 distributed candidate。
5. 校验 authority generation 与最早 lease；对中心、二级和 distributed 三层的 \(k>1\) 候选逐成员记录 ACK，并在完整 ACK 后一次性进入 `committed`；分区时三层均闭锁。
6. 输出 `d4-regional-failover-v1` truth-free payload，包含逐区域 ownership、selected layer、action、risk、readiness、assignment、commit 和 reject reason。

## 6. 状态机、门控与身份安全规则

### 6.1 `C2Health` 状态机

| 状态 | 中文含义 | 当前主要进入条件 |
|---|---|---|
| `normal` | 正常 | 心跳、digest、epoch 可信，且不存在未完成恢复合并 |
| `degraded` | 退化 | 心跳预警、缺失窗口初步触发，或降级节点正在维持连续性 |
| `suspect` | 可疑 | 心跳陈旧、digest 冲突、中心 epoch 过旧、恢复待合并 |
| `failed` | 失效 | 硬超时或 peer 多数判定失效 |

恢复路径必须经过双轨校验；`stable_recovery_s`（稳定恢复时间）字段存在于协调器配置，但当前基础 `merge_recovery()` 没有实现完整多轮稳定窗口。

### 6.2 降级动作状态机

```text
continue_center
  -> request_secondary_assist       中心仍拥有计划，仅请求补充观测
  -> request_center_replan          中心仍拥有计划，由 main/D3 生成新版本
  -> hold_for_review                身份/友方/联盟安全证据冲突

C2Health == failed
  -> degrade_to_secondary           仅在持续就绪和计划门控通过后
  -> degrade_to_distributed         二级不可用或不满足接管条件
  -> hold_for_review                原子联盟或身份安全门控失败
```

### 6.3 迟滞与防抖

主动仲裁有两类时间记忆：

- 风险窗口：最近 \(w\) 个样本中至少 \(k\) 个风险样本成立才认为窗口触发；默认 \(w=k=1\)，保持轻量单步行为；
- 释放迟滞：只有绑定可信、风险为空、连续一致帧数达到配置值且最短驻留时间满足，才释放上一降级动作；默认连续 1 帧、驻留 0 秒。

适配器按资源/航迹对隔离上述状态。二级持续就绪另按节点/航迹/覆盖小区隔离，避免同一帧多次调用虚增连续计数。

### 6.4 中心重规划请求生命周期

`CenterReplanStatus`（中心重规划状态）有 `pending`（等待处理）、`applied`（已应用）、`acknowledged_no_change`（确认无需变更）、`expired`（已过期）四态。风险签名是排序去重后的不可变风险元组。

默认冷却时间为 2 秒，以解决时间为起点；等待中的请求没有解决时间时，以请求时间为起点。严格在

\[
t\ge t_{reference}+2.0
\]

时重新开放非硬风险请求。友方冲突、重复锁定、资源/身份错配、显式身份切换或重复事件、计划/联盟版本错误、资源不可行、联盟冲突与提交不完整等硬风险直接绕过冷却。

若等待中的请求与当前目标/联盟范围一致，中心仍可用，双版本当前，所有主成员稳定锁定并形成无冲突视觉共识，且必要提交完整，D4 可输出 `continue_center` 并给出 `acknowledged_no_change` 解决提示。它不清除 D5/D7 自己的门控。

### 6.5 二级计划生命周期

二级计划可执行条件为：

\[
E_{sec}=
\mathbf{1}[\text{已激活}]
\mathbf{1}[\text{来源匹配}]
\mathbf{1}[\text{持续就绪}]
\mathbf{1}[e_{lease}\ge e_{required}]
\mathbf{1}[t<t_{lease}]
\mathbf{1}[v_{new}>v_{current}\ \text{或同一已激活计划}].
\]

其中来源必须等于选中的二级节点；新计划版本必须严格更新，只有当前所有者已经是同一个二级计划时才允许标识和版本相等。任何条件失败都会保留待生效、标记不可执行，或在当前二级计划已失效时进入 `hold_for_review`。

### 6.6 身份与协方差安全

- D4 只复制上游 `global_track_id`，不创建、不改写、不按本地视觉重绑定；
- D1 协方差始终作为风险证据保留，不能用低维点估计替代；
- D2 的连续风险评分不能冒充显式身份切换或重复事件；
- D5 友方冲突优先于接管和重规划，直接保持复核；
- 合法联盟内的授权多资源锁不算重复，联盟外锁定仍闭锁；
- D4 的 `terminal_consistent=true` 只表示当前计划绑定未被硬证据推翻，不表示 D5 已锁定，也不授权 D7；
- 旧计划、旧联盟版本、旧 epoch、过期 lease、缺 ACK 或 digest 冲突都不能通过“可见性高”或“评分高”绕过。

## 7. 与其他模块及 main/runtime 的接口

### 7.1 D1 传感器融合

D1 提供带协方差和量测时间的全局航迹。D4 从协方差计算位置/速度不确定度，从量测时间计算年龄；不重新滤波、不做坐标转换、不修改航迹。

### 7.2 D2 数据关联

D2 提供歧义、显式 IDSW、重复航迹事件、连续风险和航迹连续率。在线真值隔离时，D4 读取可用性标志，防止缺失真值的零值或占位值变成错误硬风险。`id_switch_count`（身份切换计数）仍保持显式，不被 D4 隐藏或重建。

### 7.3 D3 分配规划

D3 是中心计划权威。D4：

- 读取计划标识、版本、最近评估时间、资源可行性、代价裕度、联盟成员和需求；
- 对非当前、陈旧、不可行或联盟冲突计划请求中心重规划；
- 输出二级计划来源、待生效/已激活、租约和 supersedes（替代关系）元数据；
- 不创建系统级 `AssignmentPlan`，不绕过 D3 的旧版本拒绝。

### 7.4 D5 末端关联

D5 提供末端状态、友方冲突、重复锁定、观测全局航迹、跨视角共识和二级覆盖/注册漏斗。D4 只判断这些证据是否支持保持绑定、请求辅助、重规划或闭锁；不做像素几何，也不把二级检测可见直接解释为接管就绪。

完全无中心时，`merge_distributed_visual_evidence_into_tracks()`（把分布式视觉证据合入航迹摘要）可把 D5 多 peer 证据写入匹配的 `TrackSummary.visual_evidence`（航迹摘要视觉证据），但仍按上游全局航迹标识匹配。

### 7.5 D6 评估指标

D6 只读消费 D4 的事件和结果，不控制系统。主要字段包括：动作、模式、原因、硬/软风险、误触发候选、接管延迟、待生效持续时间、就绪等级、覆盖缺口、共识轮数、完成率、冲突、消息数、唯一所有者和脑裂防护结果。

### 7.6 D7 导引门控

D7 继续独立检查计划、所有者、末端锁定和导引合同。二级接管的第一阶段 `visual_png_allowed=false`（不允许视觉 PNG）；第二阶段仍需二级计划已激活、来源与版本正确、租约有效、能力为 `takeover_ready` 且持续就绪。D4 不实现 D7 的导引公式，也不替代其运动学可达性判断。

### 7.7 main/runtime

main/runtime 负责 AirSim 启停与 episode 顺序、故障注入时间轴、D3 新计划发布、所有者/版本回灌、D6 日志收集和最终报告。D4 的 episode 适配器只返回可审计状态；main 必须把它转换成系统级计划和运行时动作。scalable 3D 质点模块栈现已完成该转换：单一二级、多二级区域 owner 和连续失效后的 distributed D3 plan 都经过 D4 verdict，D7 再检查 owner/epoch/lease/commit/fault fence。该接线事实不代表 AirSim 或真实网络已验证。

## 8. 已实现主线、可选算法与未实现能力

仓库以优先级 0、优先级 1、优先级 2（Priority 0/1/2，P0/P1/P2）表示优先级层级；本文只用这些标签描述项目状态，不把优先级计划当作已实现能力。

### 8.1 当前已实现并属于默认主线

| 能力 | 当前事实 |
|---|---|
| 中心健康与被动接管 | 四态健康、滑动窗口、缺失阈值、peer 多数、digest/epoch 检查、中心 -> 二级 -> 分布式顺序 |
| scalable3d 区域 authority | 动态 scenario/region/task/node metadata、声明数量上限、逐区域唯一 owner、机动高空二级 coverage/readiness、epoch+plan version+最早 lease 和全层原子门控 |
| 主动降级仲裁 | 中心可用时只继续中心、请求辅助、请求重规划或保持复核；末端适用性、硬/软风险和按绑定隔离迟滞已实现 |
| 二级接管门控 | 四级瞬时就绪、综合评分、默认 3 次/0.2 秒持续窗口、来源/版本/租约严格校验和待生效/已激活状态 |
| 原子联盟安全合同 | 双版本、epoch、成员 ACK、租约、digest、分区和 fail-closed；已有二级与 peer 正例及缺 ACK 负例 |
| 一对一无中心保底 | 本地轻量 CBBA、D5 视觉风险修正、唯一任务所有者、确定性消歧、收敛/冲突/消息审计 |
| episode 时钟接口 | 严格递增时间戳、顺序接管、ACK 延迟/丢弃、分区、租约、中心双轨恢复状态 |
| D6 输出 | 仲裁事件、二级生命周期、接管迁移、联盟提交、CBBA 与通信指标 |

### 8.2 已实现但仅属可选或离线

| 能力 | 状态边界 |
|---|---|
| P1 九场景确定性扰动回放 | 已实现，用于合同回归；不等于真实网络或物理连续性 |
| P1 六类多随机种子通信回放 | 已实现内存通信矩阵；不等于真实带宽、排队、重传或硬件 |
| P2 原生联盟故障回放 | 已实现且与在线 D4 隔离；CBBA 只选协调者/补位候选，不冒充多成员形成 |
| CBBA 与中心化代价差距 | 辅助函数已实现；只有 D3/main 提供同场景代价矩阵时才有结果 |
| 外部能力探测 | 只探测本地参考路径和源码能力，不导入、不执行、不增加默认依赖 |
| 区域资源规则建议与投影 | 已实现 truth-free 变长区域图、守恒/邻边/备用/authority/commit/fault 安全投影；只输出建议 |
| 共享区域图学习研究管线 | 正式 900 episode 已完成行为克隆开发训练；bundle/state/SHA、OOD/timeout/低置信/非有限回退和确定性投影可运行。标签动作多样性不足，模型强制 development/shadow-only，PPO/assist 不可用 |
| 区域学习 episode dataset | 正式 dataset-v1 已完成 900 episode/1798 frame 审计和 70/15/15 seed 原子 split；外部 1000-1019 保持隔离。reward/causal/counterfactual 仍 unavailable |
| 跨模块共享 seed 切分消费端 | D4 已实现独立严格校验和只读 60/20/20 canonical view；原 dataset 零修改。仅属 development/data-governance，不是模型性能证据 |
| 区域动作覆盖补充课程 | 独立 producer 已覆盖 hold、request-replan、非零 quota 和 transfer；所有 target 经确定性投影，reward/outcome unavailable。仅用于 clean 来源下的行为克隆和离线 shadow，不是正式策略证据 |
| paired shadow evaluator | 已报告 backlog、transfer、churn、communication、fail-closed、安全违规和 P50/P95 latency；少于 20 个未见 seed 不推荐 assist |

### 8.3 未实现或明确不作为 D4 主线

| 能力 | 当前严格结论 |
|---|---|
| 麻省理工学院（Massachusetts Institute of Technology，MIT）CBBA 外部执行 | 未集成。矩阵实验室（Matrix Laboratory，MATLAB）数值计算与仿真平台参考代码即使被探测到，也没有运行时适配器 |
| 通信感知一致性捆绑算法（Communication-Aware Consensus-Based Bundle Algorithm，CA-CBBA）外部执行 | 未实现；已审计公共参考没有可执行源码，不存在性能结论 |
| 耦合约束一致性捆绑算法（Coupled-Constraint Consensus-Based Bundle Algorithm，CCBBA） | 只作为研究方向，未进入默认或在线路径 |
| 独立单轮拍卖 | 未实现；当前 CBBA 含获胜者/出价思想，但不是独立拍卖状态机 |
| 合同网协议（Contract Net Protocol，CNP） | 未实现管理者/承包者（manager/contractor）公告、投标、授标和失败重招标状态机 |
| 自主多成员形成与完整重构 | 区域能力与跨区域容量约束的确定性 bid selection 已实现；仅 distributed fallback 使用该算法。完整 CBBA/CCBBA 共识、全局组合最优、时序约束、预留激活、缩编、补位和整盟重组未实现 |
| 完整中心恢复审计 | 当前 `merge_recovery()` 只比较分配所有者与 epoch；完整航迹、计划、末端锁定、通信和 D5/D7 门控 digest 尚未合并 |
| 真实通信和视频链路 | 未实现真实 RF、网状网络（mesh）、带宽、时钟漂移、操作系统队列、乱序、重传和硬件故障认证 |
| 虚拟中心优化 | 明确不在无中心路径运行中心匈牙利算法或最小费用流；只允许离线对照 |
| D4 直接生成系统计划 | 明确不做；D3/main 拥有 `AssignmentPlan` |
| 已验收可推荐模型 | 已有开发 checkpoint，但无动作正样本、D6 可验证回报和外部 20-seed paired 结果；不得声称 learned policy 优于规则，最高只允许 shadow |

## 9. 2026-07-20 验证状态

### 9.1 当前结果

最新真实 AirSim M5N2 批次完成 baseline/candidate 各 10 seeds，共 20/20 case。该批中心 owner 始终有效且 `active degradation=0`，属于中心继续执行的负对照，不是 secondary/distributed 故障注入。物理结果为 coalition completion `0/20`、第二 primary 进入 5 m `0/20`；20 个第二 primary 均报告 `collision_stop`，但未持久化碰撞对象，因而不能从该字段推断冲突类型。

这组结果只支持两个判断：一是没有因物理失败自动误触发 D4 主动降级；二是 M-to-N 第二 primary 和联盟物理闭环仍未完成。D4 不使用单个 `collision_stop` 或“未进入 5 m”直接改变 owner，而继续依据 D1/D2/D3/D5 的不确定性、关联、计划有效性和末端一致性证据仲裁。D4 main-bus 阶段 mean/P95/max 约为 `5.59/6.70/94.10 ms`，当前 control tick 总体超时不能归因于 D4 算法计算。额外 `png_ttc_2v2_seed001` 排除在聚合之外，dropout case 为 0。

根据 2026-07-13 主验证报告与 D4 审计：

- 2026-07-21 D4 全量模块回归为 **387/387 项通过**，验收阈值为零失败。区域动作覆盖课程专项 6/6，覆盖动作分布、真值隔离、确定性、安全投影、canonical split、保留 seed、reward unavailable、行为克隆加载和 PPO 失败关闭。正式 900 episode 数据、补充课程、canonical view 和 development checkpoint 按独立证据口径记录，不包含新的 AirSim 或真实网络样本。历史阶段计数保持不变。
- `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 当前统一要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格 `current_time < expiry`。逐字段 `None`、完整正例和同 id/version 维持路径均有回归；未运行新 AirSim episode。
- 完全分布式 interceptor/peer 选择不套用二级视觉 readiness 门；动态 N/M、版本/epoch/lease、ACK 和 `global_track_id` 所有权规则未改变。
- 二级 resource 和 plan lease 只有在 expiry/current time 均存在且严格 `current_time < expiry` 时有效；等于边界按过期处理。缺字段分别输出可审计原因并 fail-closed，不能发布或维持 executable secondary plan。
- 七个规范单次试验时间轴（episode time）场景为 **7/7 通过**：正常中心、中心失效、中心后二级再次失效、缺 ACK、旧 epoch、过期 lease、分区。
- 在 0.25 秒逻辑时钟步下，中心故障到二级可执行所有者为 **1.25 秒**，二级故障到对等节点原子执行为 **1.00 秒**；对应验收上限为 1.5 秒和 2.5 秒。
- 主编排器/运行时又按 AirSim 单次试验时钟（episode clock）运行六类场景、每类 10 个随机种子（seed），共 **60 个试验用例（case）**：安全结果 **60/60**，误降级 0，重复所有者 0，脑裂防护失败 0。
- 30% 消息丢失下，7/10 因缺 ACK 保守闭锁，只有 3/10 在 ACK 完整后执行。这证明“缺确认不执行”，不是通信性能优良的证明。
- 更早的 D4 P1 合同层正负例中，二级协调者和完全分布式对等节点都以 3/3 ACK 进入 `executing`，缺 ACK 场景以 2/3 进入 `aborted`（已中止）并保持复核。
- 区域化合同验证为 23 个确定性单元 test case，无随机 seed；它关闭 D4 模块内 metadata/authority/安全门控。main 后续质点接线的定向 `test_module_stack.py` 为 8/8 passed，覆盖单二级、多二级 owner、distributed D3 plan 和 D7 fencing；二者均不构成 AirSim、真实网络、硬件或长时 200v200 多 seed 证据。
- 区域资源学习已形成正式数据审计和离线开发 checkpoint。内部测试只有 15 个 seed，14384 个动作标签没有 quota/transfer/hold/replan 正样本；D6 审计中 898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle 固化动作多样性不足和策略能力声明禁止，外部 20-seed paired 结果与真实网络收益仍缺失，因此 assist 资格不可用。
- 独立补充课程已提供四类规则 teacher 正样本，但实际制品为 dirty source，且没有 outcome/reward。它不能覆盖正式数据的状态分布，也不能把现有 development bundle 重新分类为可推荐策略。

这些结果验证的是单次试验时间轴上的顺序接管、版本/租约/ACK 门控和唯一所有者，不代表真实 RF、真实吞吐带宽、节点时钟漂移、网络设备或硬件故障已经验证。

### 9.2 已解决问题

1. **末端一致性误判**：`terminal_consistent` 已只表达计划绑定安全，不再把低置信度、歧义或重捕获重复解释为绑定错误；迟滞按资源/航迹对隔离。
2. **远距视觉误触发**：新增 `terminal_evidence_applicable`，未进入末端窗口时普通视觉软证据不再逐帧请求二级辅助。
3. **D2 风险语义混淆**：连续重复风险评分与显式重复事件分离；真值不可用时，IDSW/连续率占位值不触发硬风险。
4. **计划年龄误判**：优先使用最近评估时间，稳定计划标识不因创建较早而自动陈旧。
5. **重规划请求抖动**：四态请求生命周期和 2 秒冷却已实现；硬安全风险保持即时绕过。
6. **二级可见性过度外推**：已建立四级就绪性、综合评分和持续就绪窗口，单帧可见或单帧 `takeover_ready` 不接管。
7. **二级计划执行边界**：来源、版本单调、租约世代、租约到期和持续就绪已纳入待生效/已激活门控。
8. **多成员降级保底原子性**：完整 ACK、双版本、epoch、lease 和 digest 合同已实现；缺 ACK、旧世代、过期租约和分区保持闭锁。
9. **单次试验多随机种子安全矩阵**：六类、10 个随机种子、60 个试验用例的误降级、重复所有者和脑裂安全结果已闭合。
10. **区域 authority 合同**：动态 region/task/node metadata、声明数量上限、中心保持、二级 coverage 接管、跨区域 capacity candidate、双 generation、最早 lease 和全层原子 ACK/partition 门控已完成模块测试。
11. **区域资源建议安全边界**：资源守恒、邻边/分区、最低备用、formal owner/epoch/lease/fault/commit fence、模型回退和 shadow 不变性已完成模块测试；正式降级裁决仍归确定性 D4 状态机。
12. **下一周期 advisory 消费合同**：版本化内容 ID、严格有效期、逐区域/transfer 来源版本、安全证明、旧 generation/重放/ACK/fault/守恒/edge fail-closed 已完成模块测试；main/D3 实际消费尚未接线。
13. **区域学习 episode 数据合同**：truth-free source/frame、完整 episode、数值 seed 原子 split、多层 SHA、availability 和严格 BC/PPO loader 已完成模块测试；main 正式 episode writer 尚未接线。
14. **D4 共享切分消费端**：source-external registry 的 schema/policy/hash/source binding、100-seed 完整覆盖、保留集隔离和只读 BC 视图已完成；D3/D5 消费端和联合训练不由 D4 单独关闭。
15. **区域动作覆盖 producer**：独立课程在三个 canonical 桶中覆盖 hold、request-replan、quota 和 transfer，并保持投影、真值和保留 seed 门控；课程未生成 reward，不开放 PPO 或 assist。

### 9.3 剩余局限

- 真实 secondary takeover 和完全分布式 commit 尚未在与上述 M5N2 相同的多 seed 几何中执行，继续是 P1。
- `d4-region-resource-advisory-v1` 目前只有 D4 单元/接口证据；main 尚未在真实 planning loop 持久化 consumed ID 或将合同接入下一轮 D3，不能据此声称在线规划收益。
- `d4-region-learning-dataset-v1` 已形成 900 episode 正式训练集和 development checkpoint；但动作正样本、可归因转移、D6 reward/causal/counterfactual、外部 20-seed paired 结果仍缺失，不能据此声称已有可推荐策略。
- 20 个 `collision_stop` 缺少 collision object/source lineage，无法区分成员间碰撞、环境碰撞或 AirSim 状态异常；在证据补齐前不得把它设为主动降级硬触发。

1. **真实网络未验证**：带宽、拥塞、时钟漂移、操作系统/网络排队、抖动、乱序、重传、实际二级节点到执行资源链路和对等节点图分裂仍开放。
2. **恢复合并不完整**：当前基础合并没有覆盖完整航迹摘要校验值、计划摘要校验值、末端锁定、通信链路、联盟执行前缀和 D5/D7 门控。
3. **完整自主联盟形成未实现**：区域合同已有仅用于 distributed fallback 的能力与跨区域容量约束 candidate；中心和二级使用 D3 给定成员，三层 `k>1` 都执行完整 ACK 原子提交。当前仍没有 CBBA 网络图多轮共识、全局组合最优性、CCBBA 时序耦合或 D7 arrival feasibility；member-loss/replacement replay 仍由测试手工给定替换成员，只验证新 generation 全量 ACK，也不解决预留激活、缩编、补位和整盟重构。
4. **CBBA 是合成基线**：评分函数未与 D3 的真实中心代价完全对齐；真实单次试验尚未持续保存同场景中心代价矩阵并由 D6 做多随机种子差距聚合。
5. **D5 分布式视觉合流仍需标定**：模块内辅助函数已实现，但真实无中心多随机种子下的合流频率、风险权重和覆盖小区切换仍未闭合。
6. **物理闭环不能由 D4 合同结果替代**：2026-07-15 中心负对照的五资源对二目标（Five Resources to Two Targets，M5N2）20-case 聚合中，联盟完成率为 0/20、第二主资源进入 5 米为 0/20。较早的 5/10 结果属于不同批次历史证据，不覆盖本次同口径聚合。当前物理缺口不能归因于或由 D4 的 60/60 安全门控结果关闭。
7. **外部算法无性能结论**：MIT CBBA 与 CA-CBBA 当前只有能力不可用记录；未执行就不能比较优劣。
8. **学习建议仍无推广证据**：正式 BC 开发模型已生成，但 14384 个动作标签没有 quota/transfer/hold/replan 正样本，898/1798 帧状态转移无归因，reward/causal/counterfactual 可用数均为 0；外部 20-seed 和 AirSim/真实网络 paired evaluator 尚未完成。bundle admission 明确 `action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`，模型继续 development/shadow-only，低损失不能用于宣称调度策略能力。

## 10. 选型理由

### 10.1 为什么默认采用分层而非全时分布式

中心可用时，D3 拥有更完整的全局状态、版本和代价信息。全时运行分布式分配会引入所有权竞争、消息开销和版本分叉。因此 D4 把完全分布式限定为中心和二级都不可用后的连续性保底。

### 10.2 为什么二级节点需要覆盖与持续门控

二级节点可能“看见一部分目标”但不能在同一时间窗覆盖完整目标集合，也可能只有检测而没有稳定全局绑定。将可见性直接等同于接管会增加错误所有权和后续计划失效。四级就绪性与持续窗口使接管依据从单帧证据变成可审计的时空证据。

### 10.3 为什么使用轻量 CBBA

轻量 CBBA 无外部运行时依赖，能在任意输入规模上复现实验，显式输出轮数、冲突、消息和收敛状态，并保持每任务唯一所有者。它适合作为一对一无中心连续性基线，但不被外推为多成员联盟形成算法。

### 10.4 为什么原子提交独立于成员选择

“谁应该加入联盟”和“这组成员是否对同一版本达成可执行共识”是两个问题。单获胜者 CBBA 可用于选择协调者或候选，但只有 ACK/epoch/lease/digest 门控才能阻止部分成员执行、旧联盟复活和分区双主。因此当前实现把成员选择能力的开放项与已实现的原子提交安全合同分开。

### 10.5 为什么中心恢复需要双轨校验

心跳恢复只能证明中心重新发声，不能证明其航迹、分配和联盟状态最新。双轨校验和显式接受避免旧中心计划覆盖降级期间的新世代状态。

## 11. 证据与复核入口

当前模块使用 Python 编程语言的 pytest 测试框架。下列命令通过 Python 模块搜索路径环境变量 `PYTHONPATH` 指定 D4 包目录：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

本次新增区域化代码、测试和文档，并已重跑全量测试。主要源码证据：

- `models.py`：共享数据结构、中心健康、资源/航迹/通信/结果模型；
- `active_degradation.py`：风险规则、二级评分、动作仲裁、二级计划与 D7 交接门控；
- `adapter.py`：D1-D5/main 数据归一化、持续就绪性、中心重规划和联盟门控；
- `coordinator.py`：中心健康、协调负责人（leader）选择、被动保底和基础恢复合并；
- `cbba.py`：轻量 CBBA、视觉风险修正和离线代价差距；
- `coalition_safety.py`：多成员 ACK、原子提交与联盟安全证据；
- `regional_failover.py`：scalable3d 区域元数据、逐区域 authority、机动高空二级覆盖和受约束原子 fallback；
- `region_resource.py`：区域资源快照、规则基线、确定性安全投影、reward、数值 seed 原子划分与 paired evaluator；
- `region_resource_dataset.py`：episode source/frame、stage/finalize/load、数值 seed split、manifest/availability/hash；
- `canonical_seed_split.py`：共享 seed registry 严格校验、原 dataset/split/source 多级绑定和只读 canonical view；
- `region_resource_curriculum.py`：独立动作覆盖课程、三类确定性状态构造、canonical 绑定和安全/真值/reward 审计；
- `region_resource_learning.py`：共享区域图 actor-critic、严格 BC/PPO loader、bundle-v2/SHA/OOD 和 fail-closed advisor；
- `region_resource_cli.py`、`scripts/run_region_resource_advisor.py`：默认 shadow 的建议/paired evaluation CLI；
- `episode_communication.py`：单次试验时钟通信接口与七场景验收；
- `communication_fault_replay.py`、`p1_failover_replay.py`：P1 内存通信与确定性扰动回放；
- `p2_coalition_replay.py`：隔离式 P2 原生回放和外部能力探测。

## 12. 中文术语表

| 术语 | 中文解释 | 在 D4 中的严格含义 |
|---|---|---|
| C-UAS | 反无人机系统 | 本仓库的多模块研究流程，不表示实机自动处置系统 |
| C2 | 指挥与控制 | 中心协调权威及其健康状态 |
| CBBA | 一致性捆绑算法 | 当前为本地轻量、单获胜者、一对一无中心保底 |
| ACK | 确认 | 必要联盟成员对同一目标、计划、联盟版本和 epoch 的有效确认 |
| IDSW | 身份切换 | 只有上游明确指标可用时才作为在线硬风险 |
| NED | 北-东-地坐标系 | D1 融合工作坐标；D4 不做坐标变换 |
| RF | 无线频率 | 当前未做真实链路或硬件验证 |
| PNG | 视觉比例导航制导 | D7 的导引门控语义，不是 D4 输出的自动授权 |
| M-to-N | 多资源对多目标 | 资源数和目标数由输入决定；\(k_j>1\) 时需要联盟语义 |
| heartbeat | 心跳 | 节点存活和新鲜度证据，不足以单独证明计划权威最新 |
| digest | 摘要校验值 | 用于比较计划、联盟或恢复双轨状态的一致性 |
| epoch | 世代号 | 分区恢复、接管或成员重构时用于拒绝旧状态的单调代际标识 |
| lease | 租约 | 限定协调者、计划或联盟状态有效期的时间合同 |
| owner | 所有者 | 当前被 main/D3 认可的计划协调来源或降级保底协调者 |
| fail closed | 失效时闭锁 | 证据缺失、冲突、过期或不完整时不允许执行 |
| readiness | 就绪性 | 二级节点从未就绪、仅可见、注册可用到可接管的分级状态 |
| active degradation | 主动降级 | 中心仍可用时的保守仲裁，不转移计划所有权 |
| passive failover | 被动接管 | 中心明确失效后的二级或分布式接管 |
| terminal consistency | 末端绑定一致性 | 当前资源/全局航迹/版本/联盟绑定未被硬证据推翻，不等于视觉已锁定 |
| atomic coalition | 原子联盟 | 全部必要成员对同一版本完成有效 ACK，且租约和摘要一致 |
| replay | 回放 | 确定性或多随机种子的离线合同验证，不等于真实网络认证 |
| main/runtime | 主编排器/运行时 | 拥有 AirSim 单次试验、系统计划发布、日志收集和跨模块接线 |
| metadata | 元数据 | 随决策输出的版本、原因、状态迁移和评估审计字段 |
| hold for review | 保持并请求复核 | 身份、友方、联盟或版本安全条件不满足时的保守动作 |
