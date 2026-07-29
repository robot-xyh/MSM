# D4 AirSim Episode 集成计划

## 2026-07-28 运行分布预检门

正式 AirSim 或三维质点多 seed 之前，main 必须先运行 D4 runtime-distribution preflight。
当前冻结候选在 5v5/2 区域 3/3 帧和 200v200/8 区域 2/2 帧均为 `feature_ood`，模型执行
0。正式 20-seed 暂停；运行时继续使用确定性规则策略。

来源审计和离线影子加载应指向受控
`model_registry/region_resource_a2_current_lineage_development_v1/`，不再依赖本机
`outputs/`。该路径只解决 clean clone 复现，AirSim 默认 runtime 仍不得启用该候选。

新候选应以 8 区域作为首个声明适用域，并把区域数、距离和转移时间范围写入 episode
配置摘要。2 区域几何在取得覆盖数据前继续预期 OOD。main 负责 seed registry 和 episode
选择，D4 不选择正式 seed。1000-1019 不得用于训练、验证、校准或预检调参。

## 2026-07-27 提交就绪复核

本轮未启动 AirSim。D4 已完成 ACK 和安全采用输入的严格类型加固，并用纯 Python fixture
覆盖中心、二级和完全分布式 owner。AirSim producer 后续必须发送原生布尔
`can_execute`、有限双时间戳和字段全集固定的版本化 payload；附加真值字段或字符串布尔值
按无效回执处理。

main 仍需在真实 episode 中路由并持久化 owner/coalition delivery receipt，形成 ACK 后物理
窗口，再运行二级与完全分布式多随机种子场景。D4 模块回归为 **679/679 passed**；该结果
不替代 AirSim、真实网络或收益验收。

## 2026-07-27 A2 无操作统计口径

AirSim 或三维质点 producer 不得从“建议已消费”或“同周期计划升版”直接生成 A2 实际采用。
每个候选 episode 应分别持久化以下四个计数：

1. 建议完成确定性投影和消费；
2. D4 重算得到可辨识区域资源干预；
3. 同一干预标识绑定严格后继计划、确认链和物理窗口；
4. 候选窗口具备独立同键 R0 收益审计资格。

无操作建议允许保留第 1 项，用作模型加载和运行桥探针。第 2 项为 false 时，第 3、4 项必须
为 false，后继计划、运行确认、所有者确认、联盟提交和物理窗口字段必须为空。main 应从
`intervention_id`、`intervention_fields` 和干预内容摘要建立因果绑定，不能使用时间相邻
关系替代。

当前 20-seed 开发制品应由 main/D6 重新汇总为链路 20/20、干预 0/20、实际采用 0/20、
收益审计 0/20。该重算不需要重跑 AirSim，但应生成新的统计制品，保留旧结果作为被修正的
开发记录。下一轮真实候选实验只有在出现非空资源转移、配额、备用资源、保持或重规划动作时，
才进入后继计划和物理窗口验证。

## 2026-07-27 A2/R0 独立 Episode 接线

D4 已提供离线配对 DTO，AirSim/runtime 的运行和 reset 仍由 main 负责。建议对每个
scenario/scale/seed 执行两个相互独立的 episode：

```text
冻结 config.metadata.paired_exogenous_config_sha256
  -> episode A2：候选安全采用、计划、ACK、物理窗口和事件日志
  -> reset
  -> episode R0：确定性规则、独立计划、ACK、物理窗口和事件日志
  -> 离线组装 D4 benefit-audit input
  -> D6 从两份事件日志计算结果
```

两次运行共享外生配置摘要、comparison key 和逻辑窗口，不共享 episode ID、execution arm、
事件日志 ID/hash 或物理窗口 ID/hash。main 已持久化 `learning_adoption_evidence.json`；
D4 可从其中的完整 A2 记录重算内容哈希并提取候选来源。事件日志摘要应包含 episode ID，
防止 reset 前后的日志被误认成同一执行臂。

本轮没有启动 AirSim。2026-07-27 的纯 Python 验证为安全采用专项 **50/50 passed**、D4
全量 **655/655 passed**，只证明离线接线合同可用。正式验收仍需至少 20 个未见 seed 的
独立 A2/R0 episode，并由 D6 计算非退化；D4 审计资格不能替代收益和权限结论。

## 2026-07-27 A2 所有者确认接线

D4 已提供 main-independent 公共接口，main/AirSim runtime 仍需完成实际消息路由。每次
发布 `runtime.assignment_plan_ack` 后，main 应保留该 envelope，将其交给
`RegionResourceRuntimeAckParser`。解析结果中的 ACK payload SHA-256 和 ACK bus sequence
必须进入后续 owner ACK，不能只保留 D3 plan 的摘要和序号。

建议的 episode 接线如下：

```text
publish D3 successor plan
  -> publish D7 guidance bindings
  -> publish runtime.assignment_plan_ack
  -> parse RegionResourceRuntimeAckEvidence
  -> owner publishes d4.regional_plan_owner_ack.v1
  -> deterministic network delivers message
  -> RegionResourceOwnerAckDelivery.from_delivered_message
  -> validate_region_resource_owner_ack_delivery
  -> collect/validate nested CoalitionMemberAck（需要时）
  -> atomic commit
  -> start physical observation window
```

owner payload 必传 authority/owner layer、epoch、lease、partition generation、advisory
lineage、D3 successor plan ID/version/payload SHA/bus sequence、runtime assignment ACK
payload SHA/bus sequence 和 acknowledged timestamp。交付对象还必须提供 source、
destination、send/arrival timestamp、topic、transport sequence 和 envelope schema。
这些传输字段由 `CommunicationDeliveryReceipt.from_delivered_message()` 读取，main 不另行
计算 receipt ID。

联盟 payload 必须嵌套现有 `CoalitionMemberAck`，覆盖 resource、`global_track_id`、
coalition ID/version、plan ID/version、epoch、can-execute、evidence timestamp 和
valid-until。缺字段、旧代次、租约外确认、分区 generation 错误或未实际交付时保持 hold。

2026-07-27 的 D4 纯 Python 验证为四文件联合 **130/130 passed**、全量
**626/626 passed**。本轮没有启动 AirSim。main 尚未回调保存实际 assignment ACK envelope，
也未路由 owner ACK，因此 AirSim A2 仍是 P1 接线项。即使路由完成，缺采用后物理窗口或同键
R0 时仍输出 unavailable，不能写成 0 或收益通过。

## 2026-07-26 A2 安全采用运行时接线

D4 已完成真实候选采用的模块 DTO、校验器和失败关闭状态机，但没有修改 main-owned AirSim
运行时。本轮没有启动 AirSim，也没有形成新的候选采用或物理结果。

main 后续在每个 treatment episode 中按以下顺序接线：

1. 对每个权威域保存真实学习候选、区域 snapshot、正式 D4 裁决和采用 context。规则回退或
   低于 0.60 的候选不进入采用链。
2. D3 从当前正式 source plan 产生新 ID、严格更高版本的后继计划；main 保存建议
   ID/version/hash、计划 payload SHA-256 和总线 sequence。
3. 现有 production runtime ACK 必须确认该后继计划。二级或 peer owner 再通过
   `d4.regional_plan_owner_ack.v1` 返回 ACK，只有实际送达的消息可建立 receipt。
4. 多成员任务继续通过 `d4.coalition_member_ack.v1` 收集全部必要成员 ACK，并在同一
   plan/coalition/epoch/lease 下进入 executing。分区或缺成员时不积分 treatment 动作。
5. main 从确认完成后的状态积分区间生成物理窗口，绑定 runtime ACK 摘要、owner receipt 和
   coalition commit 摘要。D6 在带外形成同键规则基线和非退化结果。

正式 AirSim 验收至少要求 20 个未见 seed 的非 nominal 降级 treatment 实际采用。每个 seed
都要有完整 successor plan、runtime ACK、owner ACK、必要联盟 ACK、物理窗口和同键 R0。
模块 fixture 不计入该数量。现有 `isolated_degraded_adoption.py` 明确记录
`candidate_considered=false`、`execution_source=deterministic_rule_fallback`，因此仍为
规则负对照。

2026-07-26 D4 模块专项 27/27、相邻证据链 100/100、全量 621/621 通过。该结果只证明 AirSim
接线所需的 D4 消费合同已存在，不证明 main 已接线或 AirSim treatment 有收益。

## 2026-07-26 学习准入试验边界

本轮没有启动 AirSim，也没有新增 AirSim 性能证据。D4 v2 bundle 已在模块侧固定为 development/shadow-only；AirSim 运行参数、飞控、actor 和既有确定性降级路径均未改变。

后续 AirSim 或三维质点正式试验必须把规则 control 与 D4 treatment 放在 reset 隔离、外生输入一致的 episode 中。只有非 nominal 降级场景、D4 候选实际采用、严格更新计划的运行 ACK、完整联盟成员 ACK、采用后物理状态窗和 D6 配对非退化同时可用时，才可交给新的 promotion 合同。仅能看到物理轨迹、两臂均规则回退或 outcome unavailable 时保持失败关闭。

main 提交 `d59352b` 已能在 execution plan 中绑定 bundle 树、设备和运行诊断，但现有 D4 bundle 会在 A2/C1/F1 预检阶段停在 `pending_runtime_shadow_gate`。在新 admitted bundle 和 episode 内实际采用证据形成前，不安排正式学习 scope AirSim 验收。

## 2026-07-25 异步 M-to-N 质点验证与 AirSim 计划

D4 已取消区域快照的隐式 ACK 终结。main 已在一个连续 scalable 3D episode 中按真实到达时刻投递计划广播和成员 ACK，没有在提案同 tick 合成全部 ACK，也没有在每个决策 tick 强制结束确认窗口。

已完成的最小复现使用 2 目标、4 资源和 1 个二级侦察节点，其中一个目标要求 2 个主成员和 1 个备用成员：

1. 随机种子为 `1271`，中心在 `1.5 s` 失效，单程通信时延 `0.04 s`，无抖动和丢包。
2. 二级计划版本 2 在 `2.00 s` 发布；`2.05 s` 为 0/3 ACK、`collecting_acks` 和 `execution_allowed=false`。
3. `2.10 s` 达到 3/3 ACK，联盟一次性 `committed`；两个主成员进入 `midcourse_pn_3d`，备用成员继续 `assignment_not_current`。
4. 在线真值使用和 `global_track_id` 改写均为 0；新计划版本仍需重新收集当前版本 ACK。

验收阈值为：完整 ACK 前控制许可 0；正例最终 3/3 ACK 且原子提交 1；`global_track_id` 改写 0；旧版本 ACK 不沿用。2026-07-25 D4 模块专项 **97 passed**、全量 **569 passed**；main-owned 模块栈 **66 passed**、scalable 3D 全量 **272 passed**。D4 的租约到期、显式截止、分区、旧 epoch/version 和无效成员 ACK 负例由模块测试覆盖。AirSim 后续需按同一合同运行多随机种子正负例，不能把本次质点单场景结果当作 AirSim 或真实网络验收。

## 2026-07-25 通信因果证据接线

D4 已提供不依赖 AirSim/main 包的 `CommunicationDeliveryReceipt.from_delivered_message()`
和 `CausalCommunicationEvidenceGate`。main 的 `DeliveredMessage` 已具备 source、
destination、send/arrival timestamp 和 envelope，并已接入原三类版本化消息；A2 安全采用
还需接入第四类所有者确认：

- `d4.secondary_readiness.v1`
- `d4.regional_plan_broadcast.v1`
- `d4.regional_plan_owner_ack.v1`（待 main 接线）
- `d4.coalition_member_ack.v1`

每个 payload 必须包含 `schema`、`message_id`、`message_kind`、`authority_id`、`plan_version`、`epoch`、`lease_expires_at_s` 和 `partition_generation`。严格工厂从 delivered message 和 envelope/payload 读取全部字段，核对 envelope source/timestamp 与 transport，按 topic 映射消息类型，并计算 payload SHA-256 和内容寻址 receipt ID。main 不应另传或覆盖 authority、plan、epoch、lease、partition generation、message kind 或 message ID。

接线顺序固定为：

```text
bus publish versioned envelope
  -> DeterministicCommunicationNetwork.send
  -> deliver(current_episode_time)
  -> CommunicationDeliveryReceipt.from_delivered_message
  -> build current expectation
  -> validate secondary readiness / plan broadcast / owner ACK / member ACK
  -> existing readiness and coalition state machines
```

只有 `deliver()` 实际返回的消息可以建立 receipt。通信关闭、丢包或尚未到达时不得根据 heartbeat/readiness/ACK 布尔量补造回执。main 的 5v5 通信关闭固定验收现为 8/8 失败关闭、`execution_allowed=false`。全丢包、到达晚于决策、旧 plan/epoch、租约到期和 partition generation 不一致继续作为回归负例。

2026-07-25 因果证据专项 56/56、异步联盟三文件专项 97/97、D4 全量 569/569 通过，覆盖 5/20/50/100/200 成员。原通信禁用 P0 已关闭；异步 M-to-N 单随机种子 scalable 3D 系统正例也已通过。本轮没有运行新的 AirSim episode，AirSim 多随机种子、真实网络和正式规模验收仍待验证。

## 1. 范围与边界

本计划覆盖 AirSim episode 时间轴上的 D4 通信摘要输入、故障注入、顺序接管、原子 ACK、恢复审计和 D6 指标输出。D4 不直接启动 AirSim、不发布飞控命令、不处理视频帧，也不实现真实 socket、mesh、RF、硬件驱动、自动处置或授权绕过。

AirSim episode clock 只提供统一的仿真时间基准。已通过的 delay/loss/partition case 是时间轴上的可复现故障注入，不代表真实吞吐带宽、无线传播、节点时钟漂移、操作系统排队、乱序、重传或硬件链路已经验证。

## 2. 2026-07-22 当前状态

D4 已增加隔离 degraded rollout 采用合同，供 main 在未来 AirSim reset-separated control/treatment episode 或 scalable3d 克隆世界中生成逐周期证据。每个 receipt 必须绑定 `center_failed|center_and_secondary_failed|active_risk`、场景/初态/通信/故障 schedule SHA、D4 source snapshot/decision、源/新 D3 plan 和 candidate gate。它固定 `isolated_simulation_only=true`、`production_runtime_ack=false`，不能写入现有生产 `runtime.assignment_plan_ack` 口径。AirSim 接入时只有实际消费全部 D3 binding 并形成 D7/control lineage 后才能生成 receipt；D3 v1 隔离消费证据还必须通过 D4 独立桥接校验，截图、simGetDetections metadata、单帧建议或 projected flag 均不能代替。该合同专项 26/26、D4 全量 508/508；本轮未启动 AirSim，故没有新增 AirSim 结果。

main 适配器必须先按 region 将同帧当前 D3 plan 转为 formal D4 source view。`center_failed` 使用 secondary owner，`center_and_secondary_failed` 使用各区域 distributed owner，`active_risk` 保持 center owner；epoch 和 lease 均取 formal ownership。D3 `previous_plan` 不得直接替代这个 source。需要改变执行时，main/D3 从 formal source 发布新 ID 和严格更高版本的 applied plan；继续执行原计划时，applied 保持同一身份、binding、未分配清单和创建时间，并显式设置一个 refresh-only 标志。owner/epoch/lease 变化必须先生成新 formal decision。中心失效首轮 20-seed 的 20 pair、196 条区域记录全部以 `isolated_execution_plan_not_strictly_new` 拒绝，这是历史 producer 证据。2026-07-25 main-owned 选择器已跳过故障栅栏帧，并要求 D4 裁决完成且 D3 已采用相应区域计划；相关选择测试 11/11 通过。原 20-seed 物理制品尚未按新逻辑正式重生，D7 世界命令已应用仍不能替代计划代际门。

D4 已完成保留 seed 1000-1019 的配对干预消费合同和冻结候选隔离加载器；scalable 3D nominal 5v5 的正式 v2 40-arm execution receipts 位于 `reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`，绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`。D6 已生成 profile-bound v2 outcome-availability sidecar，目录为 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，状态 `pass_offline_assignment_comparison_only`，文件/内容 SHA256 为 `f3852251...1c3b`/`c02a345c...5d2d`。D6 独立重算确认 20/20 source clean/finite、truth=0、candidate considered 20/20；保持 `minimum_confidence=0.6` 后 confidence 0/20，OOD/latency/finite/failure 各 20/20，aggregate 0/20，safe adoption 0/20，规则回退 20/20。执行时延 `treatment_candidate_latency_ms` 的 nearest-rank P95 为 `2.241315 ms`，门控汇总的线性插值 P95 为 `2.264415 ms`。本轮未修改 main/AirSim runtime，也未启动 AirSim。未来 AirSim 配对仍由 main 为每个 seed 生成规则 control 与候选 treatment 两个 reset 隔离 episode，并冻结相同 settings/scenario config、actor/资源初始状态、通信 schedule、故障 schedule 和区域快照 lineage SHA。D4 treatment 只读加载 `region_resource_bc_900_20260720/bundle`，核对 manifest、权重和训练清单 SHA，生成 raw candidate 后进入原确定性投影；加载、推理、阈值或投影失败均记录并回退规则。arm evidence v2 不改变 bundle、authority、projection 或 next-cycle 安全门，`isolated_treatment_safe_adopted` 也不能改变线上 authority。availability sidecar 已存在不表示 physical outcome 有值；runtime ACK、AirSim 干预后物理结果、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍未执行或不可用。专项 33/33、该历史阶段 D4 全量 482/482；2026-07-25 当前全量为 569/569。`formal_twenty_seed_performance_completed=false`，nominal 5v5 只证明门控和规则回退。

最新 M5N2 baseline/candidate 各 10 seeds 已完成，共 20/20 case。该批中心 owner 始终有效且 `active degradation=0`，是中心继续执行负对照：coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均为 `collision_stop`。由于 collision object 未写盘，runtime 后续必须补充碰撞对象/来源字段，D4 不能把该终态自动转换成主动降级事件。D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`。`png_ttc_2v2_seed001` 排除在 M5N2 聚合之外，dropout case 完成数为 0。

该证据没有运行二级或完全分布式接管，故真实 secondary/distributed 多 seed 仍为 P1。后续 AirSim 集成必须构造与中心负对照配对的故障 case，并让 D4 从 D1/D2/D3/D5 摘要得出动作，不得由 `collision_stop` 标签直接注入动作。

区域建议运行时确认验证器保持 v2。AirSim 或质点 runtime 启用区域建议时，main 必须保存
`modules.d4.region_resource_consumption`、当前 `modules.d3.assignment_plan`、同周期
`modules.d7.guidance_commands` 和 `runtime.assignment_plan_ack`。无操作建议只保存消费和
`no_successor` 拒绝事实，不发布 applied ACK，也不刷新 authority/lease。存在可辨识干预时，
D3 必须发布新 plan ID、严格更高版本、正确 `previous_plan_id` 和完整 owner/epoch/lease，
随后才可进入 `new_execution_plan_applied`。当前质点集成专项 **6/6 passed**，D4 全量
**658/658 passed**。该结果不是 AirSim 证据；冻结历史 episode 仍不能回填，验证器也不改变
AirSim 控制、D3 计划或 D7 gate。

同日新增区域结果/奖励证据 v1。AirSim 集成时，main/D6 需要按每个 ACK occurrence 生成 `[ack_time,next_ack_or_lease)` 区域窗口，保存源/结果区域快照、执行绑定首尾哈希、联盟绑定首尾哈希、region owner/epoch/lease/fault generation 以及区域指标来源制品 SHA256。窗口必须使用在线区域聚合数据，目标真值和 AirSim actor ID 只能留在 D6 离线评分侧。D4 适配器不从碰撞、五米事件、D7 command 或 D6 目标距离诊断反推区域 reward。新执行计划和评估刷新的样本分别统计，窗口相交、跨 lease、binding/coalition 改变和分项缺测必须进入 unavailable/failure reason。该合同的纯 Python 专项为 19/19，D4 全量 449/449；尚未运行 AirSim producer，因此不能宣称已有真实 AirSim 区域 reward、paired shadow 或 on-policy 样本。

D4 当前具备两层 AirSim episode 接口、一个已接入 main 质点模块栈的 scalable3d 区域接口，以及一个默认 disabled/shadow 的区域资源建议接口：

- `d4_airsim_episode_communication_v1`：main 按严格递增的 episode timestamp 逐 tick 输入 heartbeat、消息 delay/drop、ACK、partition、digest、恢复授权，以及按 secondary node keyed 的 `SecondaryReadinessEvidence`。readiness DTO 必须显式携带 current time、lease epoch/expiry、heartbeat/cue/communication 时间、gimbal、coverage/full-view 和 sustained window；heartbeat 单独存在不得 propose secondary owner。
- `d4_p1_episode_fault_validation_matrix_v1`：覆盖 normal、center failure、center+secondary failure、missing ACK、stale epoch、expired lease 和 partition 的规范合同验收。
- `d4-regional-failover-v1`：D4-owned truth-free payload，包含动态 scenario/node/region/task metadata、逐区域 ownership、D1/D2/D3/D5 risk、机动高空二级 coverage/readiness、最早 lease、跨区域 capacity fallback assignment 和全层 coalition commit。main-owned scalable 3D 质点模块栈已消费该接口并发布 secondary/distributed D3 plan；AirSim 区域 episode 仍未验证。
- `d4-region-resource-snapshot-v1` / `d4-region-resource-recommendation-v1` / `d4-region-resource-advisory-v1`：只传区域聚合图与配额/邻区转移/备用/侦察/hold-replan 建议，不传 actor/truth/object identity 或具体 assignment。advisory 在确定性投影后增加内容 ID、严格有效期、逐区域/transfer source generation、资源与 edge proof；main 下一轮消费时还必须对 current snapshot/formal verdict 重验，并拒绝 replay。它不能替代 D4 仲裁、D3 plan 或 D7 gate。
- `d4-region-resource-outcome-window-v1` / `d4-region-resource-reward-evidence-v1`：只读接收 ACK 锚定的非重叠区域结果窗口，保存八项原始成本及 availability/reason。当前只完成 schema、公式和失败关闭消费端；AirSim/main producer、D6 汇总和训练准入未完成。
- `d4-region-resource-paired-intervention-spec-v1` / arm evidence v2 / manifest v1：冻结 20 个保留 seed 的两 arm 输入、`region_resource_bc_900_20260720` 三文件摘要、阈值和安全版本；隔离 loader/evaluator 已可生成 raw candidate，记录 confidence/OOD/latency/finite 分解门，并执行确定性投影/规则回退。v1 arm JSON 可受校验迁移但不回填冻结 artifact。AirSim/main 后续只负责按规范调度与记录，D6 负责结果 sidecar。D4 不把隔离采用标志解释为线上 ACK。

main/runtime 已按 AirSim episode clock 对以下六类场景各运行 10 seeds，共 60 case：

1. `normal`
2. `center_failure`
3. `center_secondary_failure`
4. `delay_0_5s`
5. `loss_30pct`
6. `partition_recovery`

验收结果：

| 指标 | 结果 |
|---|---:|
| safety outcome | 60/60 |
| false degradation | 0 |
| duplicate owner | 0 |
| split-brain prevention failure | 0 |
| D4 模块回归 | 508/508 passed（2026-07-22；含隔离 degraded rollout 专项 26/26） |
| 区域资源建议/消费合同专项 | 49/49 passed |
| 区域学习 episode 数据合同 | 13/13 passed |
| scalable 3D 质点接口定向测试 | 8/8 passed |

30% loss 场景中，7 个缺 ACK case 保守阻断，只有 3 个完整 ACK case 执行。该结果关闭 episode-clock 多 seed 安全矩阵缺口，不关闭真实网络 P1。

2026-07-15 的 280/280 回归关闭了公开 secondary plan helper 的 readiness/source/epoch/time 缺失门控，更早 278/278 不再作为全部入口证据。区域合同阶段为 303/303，建议管线阶段 335/335，next-cycle 消费合同阶段 350/350，课程阶段为 387/387，全样本准入阶段为 397/397，运行时确认阶段为 430/430；加入区域 reward、冻结 bundle 隔离加载、候选门诊断、degraded rollout 合同和 D3 隔离消费证据桥接后，该历史阶段 D4 全量为 501/501。2026-07-25 当前全量为 569/569。main 质点模块栈已从早期 8/8 定向接线扩展到 66 passed，并完成单随机种子异步三成员正例；该结果仍不提供 AirSim、真实网络或硬件证据。正式 development checkpoint 强制 shadow-only；冻结数据中的真实 ACK/outcome/reward 仍 unavailable，PPO、assist 和 authority 继续关闭。

## 3. 状态与所有权规则

中心健康时，D4 不因 D5 视觉不一致直接转移 plan owner：

```text
center healthy
  -> 普通或持续视觉软不一致: request_secondary_assist
  -> 明确硬失配/计划不可继续: request_center_replan
  -> owner 仍为 center，由 main/D3 发布新版本计划

center failed
  -> secondary readiness/plan/ACK/epoch/lease 全部有效: secondary takeover

center failed + secondary failed/unavailable
  -> distributed negotiation
  -> required-member ACK、current epoch、valid lease 缺一即 fail closed
```

`request_secondary_assist` 只请求二级观测 cue，不是接管候选的自动批准。`request_center_replan` 只请求 D3/main 生成新版本计划，D4 不直接生成系统级 `AssignmentPlan`，也不改写 `global_track_id`。

## 4. 数据流

```text
AirSim/main episode clock and link evidence
  -> AirSimEpisodeCommunicationAdapter
  -> C2Health + active/passive degradation arbitration
  -> secondary or distributed coalition commit gate
  -> owner/version + ACK/epoch/lease + transition records
  -> main runtime bus
  -> D6 metrics and Chinese report
```

离线 AirSim export 仍可映射为 `TrackSummary`、`ResourceSummary` 和链路摘要，但高分辨率坐标、相机几何和 bbox 注册属于 D1/D5/main，不进入 D4 核心。

## 5. Episode 输入

main 每个 tick 至少提供：

- episode id、严格递增且不可缺失的 timestamp 和 seed；
- center/secondary heartbeat 与 C2 health evidence；
- message delay/drop、partition 和 link freshness；
- current plan id/version、coalition id/version 和 owner；
- required/acked/missing members、epoch、不可缺失的 lease expiry；
- D1/D2/D3/D5 风险摘要和 D5 terminal evidence applicability；
- center/fallback digest 与 recovery authorization。

所有输入按实际资源和任务列表长度运行，不写死 2v2 或 5v5。

scalable3d 质点接线现已由 main 按在线时钟提供 scenario/region definition、D1/D2/D3/D5 evidence、逐区域 secondary readiness 和 member ACK，并消费 D4 ownership 生成 D3 secondary/distributed plan。D4 仍不从真值位置推导 region 或 ID，也不生成 D3 系统计划；后续缺口是长时 200v200、多 seed、D6 区域趋势和 AirSim 区域 episode，而不是接口“未接线”。

## 6. Episode 输出

D4 每个 tick 输出：

- `continue_center | request_secondary_assist | request_center_replan` 等中心健康动作；
- center failed 后的 secondary/distributed 状态；
- owner、plan/coalition version、epoch、lease validity；
- required/acked/missing members 和 commit/fail-closed reason；
- false degradation、duplicate owner、split-brain prevention 和 recovery audit 字段；
- D6 可消费的 transition/event metadata。

## 7. 已完成验收流程

1. main 创建或 reset episode，并固定 seed。
2. 按 episode timestamp 注入 normal、delay、loss、中心失效、中心与二级连续失效或 partition/recovery 证据。
3. D4 adapter 逐 tick 更新健康、owner、version、epoch、lease 和 ACK 状态。
4. 缺 ACK、旧 epoch、过期 lease 或分区 generation 不完整时阻断执行。
5. 恢复后使用新 generation 全量 re-ACK；中心恢复只进入双轨审计，不立即夺权。
6. main 汇总 10 seeds，D6 统计 safety outcome、误降级、重复 owner 和脑裂防护。

当前六类 60-case 流程已完成，不再把“main 仍需注入同一 episode-clock 证据”列为缺口。

## 8. P1 剩余工作

1. 在相同 M5N2 几何和 seeds 下增加中心失效、中心与二级连续失效两组 paired case，验证 secondary/distributed owner、版本、epoch、lease、完整 ACK 和物理连续性。
2. 增加可审计主动风险 case：D1 协方差/陈旧、D2 关联冲突、D3 stale/infeasible、D5 current binding/身份/跨视角不一致；单纯物理未命中或 `collision_stop` 不得直接触发降级。
3. 在控制日志中持久化 collision object/source lineage，用于区分成员碰撞、环境碰撞和 AirSim 状态异常；该字段只供诊断和 D6 评分，不绕过 D4 仲裁。
4. 保持已完成的 scalable3d versioned envelope 接线回归，扩展 5/20/50/100/200 长时多 seed episode，记录逐区域 owner、generation、lease、commit、fault fence、stage timing、churn 和分区恢复；该工作属于 main-owned 集成，不由 D4 修改。
5. 区域资源学习建议先在 shadow 中运行至少 20 个未见 seed，paired 报告 backlog、transfer、churn、communication、fail-closed、安全违规和 P50/P95 latency。当前 nominal 5v5 保留 seed 的 20/20 confidence 低于 0.6，只能用于规划独立 confidence 校准/重训，不能据此下调门。未满足门槛前不进入 assist；即使满足也不绕过正式 D4/D3/D7 gate。
6. main 如在 AirSim planning loop 消费区域资源建议，只接受 `d4-region-resource-advisory-v1`，在每个 D3 planning boundary 使用 current snapshot/formal verdict 重验，并跨进程持久化 consumed advisory ID。不得直接消费 raw/non-projected recommendation；D4 不修改 main/D3-owned 实现。
7. main 的逐 episode region-learning writer 改为调用 D4 公开 API：episode 开始固化 `RegionLearningEpisodeSource`（scenario/version/scale、seed、episode ID、Git commit/dirty、config SHA），逐帧构造带显式 target/reward availability 的 `RegionLearningFrame`，episode 完成后 stage，批次完成后 finalize。旧 JSONL 只有 frame_index/timestamp/snapshot/recommendation，不满足正式训练合同；main 不应解析 D4 私有 artifact。
8. 动作覆盖课程保持离线独立。main 不把课程 frame 注入 AirSim episode bus，也不把规则 teacher 当作实际 D4 运行结果。clean worktree 重生已经完成；后续训练配置仍须单独记录正式 episode 与课程样本比例，缺真实 outcome 时不得启动 PPO。

以下项目仍为 P1，不能由当前 episode-clock 结果替代：

- 在可配置吞吐带宽和队列容量下验证消息拥塞与优先级；
- 注入 center、secondary 和 peer 节点时钟漂移与时间同步误差；
- 建模操作系统/socket 排队、网络抖动、乱序、重传和突发丢包；
- 验证 secondary-interceptor 和 peer-to-peer 实际链路分区；
- 在长时间运行中统计 false/missed degradation、恢复时间和 owner 抖动；
- 有条件时使用网络仿真器或硬件链路验证 RF/mesh 行为。

这些实验必须继续保持中心健康时不转 owner，以及 secondary/distributed 的 ACK、epoch、lease fail-closed 规则。

## 9. 非目标

- 不发布 AirSim vehicle control 命令。
- 不在 D4 内实现在线 socket bridge、视频传输或无线协议栈。
- 不把 episode clock delay/loss 结果表述为真实 RF 验证。
- 不由 D4 生成新的中心化系统级 `AssignmentPlan`。
- 不绕过 D3 版本、D5 身份/视觉门控或 D7 控制许可。

## 10. 验收命令

```bash
python3 -m py_compile \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/communication_causal_evidence.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_learning.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_curriculum.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_curriculum_cli.py
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

本轮新增 D4 独立动作覆盖课程、canonical 绑定、审计、测试和文档，不启动 AirSim，也不修改 main/runtime、scalable_3d_simulation、D3、D5、D6 或 D7。既有 main-owned 质点集成 8/8 仅作为此前接口事实保留，本轮未把 D4 单元测试外推为新的 AirSim 或多 seed 证据。
