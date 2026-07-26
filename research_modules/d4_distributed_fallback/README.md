# D4 分布式协同与降级接管

## 2026-07-26 A2 校准 development 候选

D4 已生成新版区域资源 `development/shadow` 候选
`region_resource_a2_development_calibrated_20260726_v1`。该候选合并正式 900
episode 与 clean supplemental 100 episode 的规范只读 60/20/20 视图；训练、验证和校准
分别使用 seed 0-99 中互不重叠的 60、20、20 个 seed。保留 seed 1000-1019 的使用数为
0，未参与训练、置信拟合、阈值选择或场景选择。

行为克隆使用动作平衡损失和补充课程重复采样，置信头只在 validation 正样本与合成分布外
样本上拟合；test 桶仅作独立校准，不调门限。校准 420 个样本中，候选
considered/gate-pass 为 **420/420**，置信度 min/mean/max 为
**0.707421/0.972089/1.000000**，推理时延 P95/max 为
**0.969215/1.294533 ms**。固定置信门仍为 **0.6**，固定时延门仍为 **50 ms**。
合成分布外样本 **420/420** 被硬门拒绝。

校准桶的后投影动作覆盖非零配额 40、跨区转移 20、hold 20 和 request-replan 40。
数据总目标动作清单为 15584 条，其中非零配额 200、transfer 100、hold 100、
request-replan 200。候选清单文件 SHA-256 为
`d3c96f0abf059d6726b4706f8380a59687d8635898253cfa04f0a8a61df036a2`，权重
SHA-256 为 `cf393eaa2e7777e63645ef244f8e9bf733123fdc768f2610a91954c5f6c4632f`。

该结果只证明新版候选具有动作多样性、固定门可通过且证据可绑定加载。候选仍固定
`lifecycle_stage=development`、`maximum_advisor_mode=shadow`，
`assist_enabled=false`、`authority_enabled=false`。正式保留 seed 降级试验、D3 严格后继
计划、运行消费 ACK、联盟成员 ACK、采用后物理窗、规则基线配对非退化和 D6 外部审计均未
执行，不能据此宣称系统收益、assist、生产 authority 或正式准入。

2026-07-26 D4 全量模块回归为 **577/577 passed**。本轮未运行 AirSim 或
reserved-seed 正式矩阵。

## 2026-07-26 A2 预准入证据装配盘点

本节记录新版校准候选形成前的盘点。当前候选状态和后续限制以上一节为准；旧冻结 bundle 和
历史 20-seed 结果继续保留为基线，不被新版产物改写。

结论是：D4 已有多段严格证据合同，但尚不具备与“D6 外部审计 -> D4 证据装配器 -> 新
bundle”等价的完整链路。该缺口当前为 P1，不是 P0。原因是
`d4-region-resource-model-bundle-v2`、loader 和 advisor 已共同把模型限制在
`development/shadow`；正式调用方不能用裸布尔、未绑定摘要、无 manifest 注入策略或
20 个未见 seed 自行进入 assist。测试代码中的合成布尔和测试摘要不进入生产加载或准入路径。

现有合同按证据能力分为四层：

1. **bundle 完整性**：writer/loader 校验 manifest、权重、训练清单、模型版本和
   SHA-256，并在写目录前拒绝 `qualified/assist`。
2. **候选实际采用**：`RegionResourceRuntimeAckParser` 可证明建议经过 main 消费、D3
   形成严格后继计划、D7 形成同代 binding，且 owner、plan、epoch、lease 和总线
   sequence/hash 一致。它不证明物理结果或模型准入。
3. **联盟和通信**：`CoalitionCommitState` 保存 required/acked members 和联盟代次；
   `CausalCommunicationEvidenceGate` 校验每个成员 ACK 的实际投递回执。当前这两类证据尚未
   与某个 A2 候选的 runtime ACK 和 D6 cell 审计装配为同一个内容身份。
4. **结果和配对**：区域 reward 适配器可绑定 ACK 后的非重叠、truth-free 观测窗口，但明确
   固定 `physical_execution_outcome_available=false`；隔离 paired 合同和
   `ShadowPairedEvaluator` 也不授予物理、因果、assist 或 authority。正式物理结果和配对
   非退化仍必须来自 main 运行制品及 D6 独立审计。

未来 D4 专用装配器的最小输入必须包含：候选 bundle 全树和模型摘要；场景、seed、comparison
key、advisory 及模型指纹；候选实际通过门控且未走规则回退；源计划和严格后继计划身份；
owner/layer、plan version、epoch、lease 和 fault/partition generation；联盟
ID/version、required/acked members、每个成员 ACK 的 delivered receipt 内容摘要；运行 ACK
与 D3/D7/main 的序列和载荷摘要；采用后物理结果 availability；同外生输入 R0 配对及逐项
non-degradation；D6 审计制品和带外校验摘要。任何一项缺失都保持 unavailable。D4 不复制
D6 的通用外部审计 schema；待 D6 输出冻结后，只实现 D4 语义校验和内容寻址装配，并在新目录
生成新版本 bundle，旧 v2 manifest 保持不变。

现有 development bundle、nominal 20-seed 和 `active_risk` 20-seed 证据仍不能拼接：
前者候选安全采用为 0/20，后者 188/188 区域记录执行的是规则回退且
`production_runtime_ack=false`。正式 assist、PPO 和 authority 继续关闭。

验证日期为 2026-07-26。本轮没有新增场景、seed 或性能样本；验收标准为不存在
development bundle 自晋级入口、历史证据不被宽松拼接、D4 全量回归零失败。结果为
**569/569 passed**。剩余限制是 D6 冻结外部审计和真实候选采用正样本尚未形成。

## 2026-07-26 A2/C1/F1 学习准入复核

对照 main 提交 `d59352be83c24238fc8c41a9fe7a1c0db40a6d31` 的正式学习 scope 合同，D4 当前不能合法进入 A2、C1 或 F1。现有区域策略 bundle 为 `d4-region-bc-900-development-v1`，manifest、权重和训练清单 SHA-256 分别为 `dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9`、`3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62` 和 `ff3081c8e320d9c8e1b032fb6234cd24159f0feedb1c6a706633cea6c1030dc6`。其生命周期和模式上限仍是 `development/shadow`。

本轮收紧 `d4-region-resource-model-bundle-v2`：bundle writer 只能生成 `development/shadow`，调用方不能再靠布尔字段生成 `qualified/assist`；拒绝发生在目录和权重写入前。没有 D4 manifest 的注入策略也不能进入 assist。旧 bundle、manifest 和权重未修改。

已有两组证据都不能用于晋级。正式 nominal 20-seed 干预的源 manifest SHA-256 为 `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`，D4 干预文件 SHA-256 为 `aa6b22d252184d9bfc58c6e35cf6798551d26447a74ea7619c8a37a8969e2329`；候选安全采用为 0/20，运行 ACK 和物理结果不可用。`active_risk` 20-seed 隔离物理 sidecar 文件/内容 SHA-256 为 `dbbda16194f14a63b66e3fc9f2360103b8fe401a6db9b1f1e693dc8c169a7515`/`1aae70cd5612cce3f20ab4e2723533bd6ab1a0775d5e254cf425aeede85e3489`，虽然物理窗和描述性非退化为 20/20 可用，但 D4 候选均为 `candidate_considered=false`，执行的是确定性规则回退，且 `production_runtime_ack=false`。这两组制品不能拼接为模型准入。

2026-07-26 D4 全量回归为 **569 passed**。正式晋级仍需新的、内容寻址的 promotion 合同，以及在 clean、未见 seed、真实降级场景中绑定 D4 候选实际采用、新执行计划 ACK、联盟成员 ACK、采用后物理窗和配对非退化的 D6 独立审计。在此之前保持 fail-closed。

## 2026-07-25 异步 M-to-N 联盟确认

区域联盟确认现按真实通信到达顺序跨快照累积。提案建立后进入 `collecting_acks`；没有 ACK 或只有部分 ACK 时保持该状态，`execution_authorized=false`。同一 `plan_id/plan_version/epoch/coalition_version` 的后续快照复用现有成员位图，全部必要成员 ACK 到达后才原子进入 `committed`。普通评估不再把“当前缺 ACK”解释为“确认窗口已经结束”。

`RegionalFailoverSnapshot.finalize_coalition_collection` 是向后兼容的显式终结开关，默认关闭。只有调用方明确终结、租约到期、网络分区、联盟摘要冲突或成员明确不可执行时，当前代次才进入 `aborted` 或 `reconfiguring`。旧 epoch/version、过期、越权或内容不匹配 ACK 被拒绝，不进入 ACK 位图，当前快照继续失败关闭；后续合法 ACK 可在租约内完成同一代次，避免单个乱序旧包永久阻断合法联盟。

2026-07-25 新增 5 项异步生命周期回归。三文件专项为 **97 passed**，D4 全量为 **569 passed**。验收要求是：完整 ACK 前授权数为 0；三个必要成员分三次送达后一次性提交；显式终结、租约到期、分区、陈旧代次和无效 ACK 均不能产生执行权限。该组数字来自纯 Python 模块测试，不是 AirSim 或 scalable 3D 系统级证据。

main 随后完成单随机种子 scalable 3D 集成复跑。场景为 2 目标、4 资源、1 个二级侦察节点，高威胁目标要求 2 个主成员和 1 个备用成员，随机种子 `1271`。中心在 `1.5 s` 失效，二级计划版本 2 在 `2.00 s` 发布；`2.05 s` 为 0/3 ACK 和 `collecting_acks`，`2.10 s` 为 3/3 ACK 和原子 `committed`。提交前主成员保持，提交后两个主成员进入三维中段比例导引，备用成员继续待命；在线真值使用和 `global_track_id` 改写均为 0。main-owned 模块栈为 66 passed，scalable 3D 全量为 272 passed。该结果关闭单随机种子质点接线缺口，AirSim 多随机种子、真实网络、正式 5700 单元矩阵和 200 对 200 性能仍未验证。

## 2026-07-25 P0 区域通信因果证据门

D4 已完成运行级 P0 的模块合同部分。新增不可变 `CommunicationDeliveryReceipt`，记录回执号、消息号、源节点、目的节点、版本化 topic、总线序号、envelope schema、发送/到达时间、authority、plan version、epoch、lease expiry、partition generation 和 payload SHA-256。`CommunicationDeliveryReceipt.from_delivered_message()` 采用 duck typing，直接从 main 的 delivered message、envelope 和 truth-free payload 提取这些字段，不导入 main、AirSim 或 scalable3d。调用方不能覆盖消息类型、authority、plan、epoch、lease、partition generation 或 message ID；回执号按实际投递事实内容寻址生成。

版本化 topic 固定映射为 `d4.secondary_readiness.v1`、`d4.regional_plan_broadcast.v1` 和 `d4.coalition_member_ack.v1`。payload 必须同时携带 `schema/message_id/message_kind/authority_id/plan_version/epoch/lease_expires_at_s/partition_generation`，且 envelope source/timestamp、topic 映射和 payload 自声明必须相互一致。缺字段、truth 字段、错源、错时间或错消息类型在构造阶段失败关闭。

`CausalCommunicationEvidenceGate` 分别验证二级 readiness、区域计划广播和联盟成员 ACK。缺回执、冲突重放、错源/目的/类型、旧 plan/epoch、过期或错 scope lease、到达晚于决策、分区代次和 payload digest 不一致均输出稳定 reason code。完全相同的 receipt 和 expectation 可幂等重放；同 receipt ID 的内容变化或跨证据复用被拒绝。验证结果固定 `authority_granted=false`，不修改既有 owner、epoch、lease、plan 或 coalition 状态机。

main 已把 readiness、计划广播和 ACK 接入 `DeterministicCommunicationNetwork`，只用实际 delivered message 建立回执。原 5v5 通信关闭复现现为 D4 可执行区域 0、失败关闭区域 8，全部 D7 命令保持 `hold/d4_hold_for_review`，原 P0 已关闭。异步联盟修复后的 2 目标/4 资源单随机种子系统正例也已按上一节通过；该证据仍不能替代 AirSim 多随机种子、真实网络或正式规模验收。

## 2026-07-22 跨独立运行内容身份边界

D3 使用不透明计划号区分独立执行谱系。同 seed、同输入的两个独立 planner 可以产生不同的原始 `plan_id`。D4 的 `authority_digest` 包含区域 `plan_id`，`formal_decision_digest` 包含正式裁决中的计划号，`advisory_id` 又对完整建议合同做内容寻址，因此三类值会随 D3 原始计划号确定性变化。它们仍是单次运行内的正式身份和完整性字段，不能从原始日志、消费 ledger 或运行时回执中删除或改写。

跨提交业务等价比较只允许生成独立的规范比较视图。比较器必须先验证原始运行：D3 谱系连续；同时间正式裁决可重算出 advice 的 before/after digest 且二者相等；`RegionResourceAdvisoryContract.from_dict()` 能从原始合同重算相同 `advisory_id`；顶层、recommendation、每个 region 和 transfer 的 authority digest 一致，并可由完整 authority payload 重算。随后只把已经通过 D3 谱系审计的原始计划号映射为规范计划 token，重算规范 authority digest、正式裁决 digest 和 `d4-rr-advisory-<SHA256>`。事件序号只用于配对，不得替代 `advisory_id`，也不得把任意摘要改成“同一摘要类别”。

以下字段不得归一化：区域、任务、全局航迹、资源、节点和联盟身份；owner/layer/role；plan version、epoch、lease、ACK、active/fault fence；正式 action/reason/decision；recommendation 的策略、模型、置信度、区域动作、转移和安全证明。任一源事件缺失、原始哈希不闭合、未知计划引用、谱系不连续或上述字段不同，比较均失败关闭。

本次只读复核覆盖 clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002、三组 10 秒 200v200 episode。两侧各 30 条正式裁决和 30 条建议中，原始 advisory 内容地址、正式裁决摘要、authority 摘要和摘要副本一致性均为 30/30；按上述规则重算后，30/30 对正式裁决和建议逐字段相同。当前制品可由 `source_version + protected_committed_resources` 回算原始 authority 摘要；未来若该回算不成立，必须持久化完整 `RegionResourceSnapshot` authority payload 后才能比较。

## 2026-07-22 隔离物理续跑计划代际复核

main 的中心失效 20-seed 物理续跑共形成 20 个 pair、196 条区域记录，D7 世界命令已经应用，但 D4 区域采用全部以 `isolated_execution_plan_not_strictly_new` 拒绝。该结果不是 owner、epoch、lease 或物理消费失败。适配器把同帧 `d3_planning_frame.plan` 作为 formal source，同时把从 `previous_plan` 重新求解得到的同版本 arm plan 作为 applied plan。两者计划标识不同而版本相同，不满足严格后继，也不属于同身份刷新。

main 必须按以下规则构造证据：

- `center_failed`：source 是与同帧 formal secondary decision 完全一致的区域计划；owner 为选中的二级节点，epoch 和 lease 取 formal ownership。applied 必须由该 source 继续生成，使用新 plan ID、严格更高版本，并保持同一 formal owner/epoch/lease。
- `center_and_secondary_failed`：source 是与 formal distributed decision 一致的区域计划；每个区域使用该 decision 的分布式 owner、epoch 和 lease。applied 同样必须是该 source 的严格后继。
- `active_risk`：source 是 formal center authority 的当前计划。若中心重规划改变执行签名，applied 必须严格更新；若实际执行未改变，只能以相同 plan ID/version、相同 binding/未分配清单和相同 owner/epoch/lease 形成显式 evaluation refresh。
- `d3_planning_frame.previous_plan` 只表示 D3 规划祖先。被动降级时它仍属于上一个 authority，不能直接冒充 D4 source，除非另有同代 formal D4 decision 明确绑定它。

D4 没有放宽 strictly-new、owner、epoch、lease 或 production-runtime-ack 门。模块测试新增同版本异 ID、故障前 owner 和三类刷新回归，隔离专项 **26/26 passed**，该阶段 D4 全量 **508/508 passed**。2026-07-25 main-owned 选择逻辑已改为跳过仅含故障栅栏的帧，并只选择已完成 D4 裁决且由 D3 采用对应区域计划的帧；相关保留种子选择测试 11/11 通过。原 20-seed 物理证据尚未按新逻辑正式重生，本次历史全拒绝仍不能计为降级采用成功。

## 2026-07-21 PDT / 2026-07-22 UTC 隔离多周期采用合同

新增 `region_resource_isolated_rollout.py`，为 main 后续克隆世界多周期 rollout 提供 `d4-region-resource-isolated-adoption-evidence-v1`。合同只接受 `center_failed`、`center_and_secondary_failed` 和 `active_risk` 三类来源；snapshot、formal D4 decision、源 D3 plan、候选门、场景配置、初始状态、通信 schedule 和故障 schedule 均以 SHA256 进入 lineage。场景名含 nominal、来源哈希不一致、网络分区或 formal decision 未形成可执行二级/分布式 authority 时，降级策略证据保持不可用。

候选证据显式区分 `candidate_considered`、`gate_pass`、`new_execution_plan_applied`、`evaluation_refresh_applied` 和 `rule_fallback`。候选置信门保持 `0.6`，时延门保持 `50 ms`。只有新 plan ID、严格更高 plan version、当前 owner/epoch/lease、完整 binding hash 和 main 隔离世界消费回执全部一致时，才输出 `isolated_candidate_adoption_available=true`。同 plan ID/version 只允许 binding、未分配集合、owner、epoch、lease 和创建时间不变的 evaluation refresh；它不计为候选采用。候选低置信、缺 ACK、旧 epoch、到期 lease、ACK/plan binding 篡改、缺联盟确认或分区均失败关闭，低置信候选只能回到确定性规则计划。

隔离回执固定 `isolated_simulation_only=true`、`production_runtime_ack=false`。证据同时固定 physical outcome、paired non-degradation、counterfactual、causal、degradation-effectiveness claim、PPO、assist 和 authority 为 false，规则回退为 true。D4 还提供 D3 `d3.isolated-plan-consumption-evidence.v1` 到本合同的严格桥接：不导入 D3，只校验字段集合、来源 lineage、计划、binding 数量、时间窗、内容哈希和隔离权限，再生成非生产 D4 回执。2026-07-22 本地验证覆盖三类正例、三类刷新、同版本异 ID 拒绝、故障前 authority 来源拒绝、规则回退、D3 回执桥接和篡改/过期负例，专项 **26/26 passed**，D4 全量 **508/508 passed**。当前只完成 D4 消费合同；main 的首轮中心失效物理续跑尚未形成有效区域采用，D6 也不能据此给出成对非退化结论。既有 nominal 5v5 结果不得关闭该缺口。

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

**2026-07-21 保留 seed 配对候选门诊断**：`RegionResourcePairedArmEvidence` 已升级为 `d4-region-resource-paired-arm-evidence-v2`。新证据除 aggregate `candidate_thresholds_passed` 外，还持久化 candidate confidence、冻结的 `minimum_confidence`、OOD 状态、candidate latency 与 latency limit、finite 状态，以及 confidence/OOD/latency/finite/external-failure 五项 gate 结果。executor 对已考虑候选至少输出 `candidate_low_confidence`、`candidate_ood_rejected`、`candidate_inference_timeout`、`candidate_output_nonfinite` 中对应的明确拒绝码；旧 `candidate_threshold_or_finite_gate_rejected` 仅作为兼容汇总码保留，不能单独解释拒绝。v1 reader 先按旧字段集合和旧 manifest content ID 验证，再迁移为 v2 且令新增诊断显式 unavailable；历史 v1 artifact 保持只读，新 v2 正式证据使用独立目录，不覆盖旧运行。

当前权威输入为 `research_modules/scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`，源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS` 文件 SHA256 为 `821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`，manifest SHA256 为 `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。D6 已在 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/` 生成 profile-bound v2 outcome-availability sidecar，状态为 `pass_offline_assignment_comparison_only`；sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。D6 独立重算确认 20/20 source clean 且 finite、在线 truth 使用数为 0，20/20 treatment candidate 被评估；confidence gate 在保持不变的 `minimum_confidence=0.6` 下通过 0/20，OOD、latency、finite、failure gate 各通过 20/20，aggregate gate 通过 0/20，safe adoption 0/20，规则回退 20/20。候选 confidence min/mean/max=`0.508892953/0.563426384/0.569492280`。`treatment_candidate_latency_ms` 的执行时延 P95 采用 nearest-rank，为 `2.241315 ms`；`candidate_gate_summary.candidate_latency_ms` 的门控汇总 P95 采用线性插值，为 `2.264415 ms`，两者不得混称。sidecar 已存在只表示同帧离线分配比较可用；runtime ACK、干预后物理结果、paired effect/non-degradation、counterfactual、causal 及故障场景降级策略效果仍为 unavailable。bundle manifest 继续声明 `confidence_head_uncalibrated`，`formal_twenty_seed_performance_completed=false`，`PPO/assist/authority=false`、`rule_fallback=true`；该 nominal 5v5 只证明门控分解和失败回退，不能证明候选或降级策略有效。配对专项 **33/33 passed**，D4 全量 **482/482 passed**。

**2026-07-21 区域结果与奖励证据合同**：新增 `region_resource_reward_evidence.py`，冻结 `d4-region-resource-observational-reward-v1`。适配器只接受已通过 ACK v2 的区域建议，并把 advisory/模型指纹、源计划与当前计划、owner/epoch/lease/fault generation、ACK sequence/time、源/结果区域快照、执行与联盟绑定以及来源制品 SHA256 固定到一个左闭右开的非重叠窗口。高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动均保留 raw value、单位、归一化分母、来源 SHA、availability 和 reason；缺测分项保持 `unavailable`，不补零。冻结观测成本为 `sum(weight*min(raw/denominator,1))/sum(weight)`，新执行计划的时间窗口观测奖励取其负值；`evaluation_refresh_applied` 只输出观测成本，不获得动作归因奖励。窗口重叠、缺 ACK、旧 generation、租约覆盖不足、执行/联盟绑定变化、哈希篡改、真值字段或缺字段均失败关闭。该阶段新增专项 **19/19 passed**，运行时 ACK 与奖励专项合计 **52/52 passed**，D4 全量 **449/449 passed**。该合同没有回填正式 900 episode，也没有产生 paired、counterfactual、causal 或 on-policy 证据；`CoalitionMemberAck`、物理执行、PPO、assist 和 authority 继续不可用，规则回退保持必选。

**2026-07-21 区域建议运行时确认接口**：`region_resource_runtime_ack.py` 已升级为只读 `d4-region-resource-runtime-ack-evidence-v2`，在不导入 main、D3、D7 或 scalable3d 的条件下消费 D4 advisory/result、main consumption、运行时 ACK，以及 D3/D7 源 envelope。输出用 `adoption_kind` 区分两种证据：执行签名变化时，只有 plan ID 和版本严格推进、owner/epoch/lease 完整、D3/D7 序列/哈希与全部 binding 一致，才产生 `new_execution_plan_applied`；执行签名不变时，允许同 plan ID/version 的 `evaluation_refresh_applied`，但必须显式满足 `evaluation_refresh_only|plan_refresh_only`、`execution_signature_changed=false`，并用 advisory source-plan envelope 证明资源、全局航迹、coalition、coalition version、member role、区域 owner 字段和未分配集合均未改变。5v5 seed 41、1.2 s 的真实 main 质点集成正例已通过；篡改 refresh flags、同版本 binding 和无版本提升的 execution change 均失败关闭。专项 **33/33 passed**；加入该专项时 D4 全量为 **430/430**，加入奖励合同时为 **449/449 passed**。评估刷新中缺省的 D3 epoch/lease 不被解释为新执行权限；验证器只依赖仍有效的 D4 source authority，并保持 `CoalitionMemberAck`、物理 outcome、真实 paired reward、PPO、assist 和 authority 为不可用/false。冻结 900 episode 没有新 runtime 字段，仍不能补造 applied ACK。

**2026-07-21 区域调度全样本准入审计**：新增只读、失败关闭的 `region_resource_full_sample_audit.py`。正式数据路径为 `research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region`，共 900 episode、1798 frame/sample、14384 个区域动作；规范只读切分为 train/validation/test = 540/180/180 episode、1079/359/360 sample、8632/2872/2880 action。补充课程路径为 `outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset`，共 100 episode、300 frame/sample、1200 action；规范切分为 60/20/20 episode、180/60/60 sample、720/240/240 action。900/900 和 100/100 episode 文件哈希均通过，全部样本数值有限并通过动作/transfer 合同、配额守恒、owner/plan/epoch/lease/version、保留 seed、dirty 状态和在线真值隔离检查，违规数为 0。`target.kind=rule` 只表示规则教师标签；`recommendation.projected=true` 只表示离线确定性投影通过，二者都不是运行时 applied ACK。显式投影前动作掩码、被拒旧计划/旧租约样本、真实 `CoalitionMemberAck`、outcome、可归因 reward 和同 seed paired shadow 均为 `unavailable/pending`。D6 外部路径与带外 SHA256 复核尚未完成；PPO、assist、authority 继续关闭，确定性规则、lease/epoch 和安全投影仍是唯一可执行路径。审计专项 10/10，该阶段 D4 全量 **397/397 passed**；后续候选门诊断阶段为 **482/482 passed**，当前全量见本文顶部的 **569/569 passed**。

**2026-07-20 scalable 3D 接线事实同步**：main-owned `IntegratedScalableModuleStack` 已消费 `d4-regional-failover-v1`，闭合单一二级 owner、两个二级节点的多区域 owner，以及中心与二级连续失效后的 distributed D3 plan。D7 在恢复质点导引前核对区域 owner/node、plan version、epoch、lease、commit mode 和 fault generation；过期 lease、缺 commit 或旧 source plan 均 fail closed。本轮只读定向复核 `research_modules/scalable_3d_simulation/tests/test_module_stack.py` 为 **8/8 passed**。这是三维质点接口/集成测试证据，不是 AirSim、真实 RF/mesh/socket、硬件或实飞证据，也不代表长时 200v200 多 seed 已验收。

**2026-07-20 可选区域资源建议层**：新增版本化 `RegionResourceSnapshot`、确定性规则基线、安全投影、共享区域图 actor-critic、行为克隆、原生 clipped PPO、manifest + `state_dict` + SHA256 bundle、完整 episode/数值 seed 原子划分和 paired shadow evaluator。快照只含区域聚合需求、不确定性、可见/一致性、资源/备用、二级覆盖/就绪、通信和当前 authority fence，不含 actor truth ID 或具体目标身份。输出只允许区域配额增减、相邻区域资源转移、备用比例、侦察优先级与 hold/replan；不能生成 resource-target assignment。学习层默认 `disabled`，CLI 默认 `shadow`，任何超时、低置信、OOD、非有限输出、模型版本或 SHA 不匹配都回退规则建议；少于 20 个未见 seed 不得进入 assist。所有建议仍经 owner/version/epoch/lease、fault fence、ACK/commit、邻边和资源守恒投影，D4 确定性安全状态机继续拥有最终降级裁决。原建议/学习管线专项 **32/32 passed**；增加下一周期消费、正式 bundle 准入和动作多样性失败关闭回归后该文件当前 **51/51 passed**。这些测试证明合同和研究管线可运行，不证明模型优于规则、AirSim 收益或真实网络性能。

**2026-07-20 区域学习 episode 数据合同**：新增 D4-owned `d4-region-learning-dataset-v1`。`RegionLearningEpisodeSource` 固化 scenario/version/scale、数值 seed、episode ID、Git commit/dirty 和 config SHA256；每帧必须提供 truth-free `RegionResourceSnapshot`、`rule|formal` target 或显式 unavailable、显式 reward/unavailable，并可附 recommendation。训练 target 会按固定 projector 版本重验 owner/plan/version/epoch/lease、备用、邻边、容量、分区和 quota 证明，不信任外部 `projected=true`；actor/object/global-track/evaluator/offline-truth key 变体均拒绝。manifest 还会把 episode 顺序、availability 和可重放 split 对照 episode inventory。数据与正式训练准入测试为 **15/15 passed**，共享切分专项为 **12/12 passed**；候选门诊断阶段 D4 全量为 **482/482 passed**，当前全量见本文顶部。96-episode/192-frame 高基数用例仍只是合成确定性合同回归，正式数据和开发模型结论单列如下。

**2026-07-20 正式数据审计与行为克隆开发模型**：D4 只读审计 `learning_generation_v1_multibatchfix` 的 900 episode/1798 frame 数据，900 个 episode SHA256、dataset SHA、source identity、schema 和数值 seed 原子划分均通过。训练/验证/内部测试为 70/15/15 个 seed、1258/270/270 帧；外部保留 seed 1000-1019 未进入数据。2026-07-21 使用固定 seed `20260720` 复跑后，共享区域图行为克隆在 CPU 单线程运行 66 epoch，最佳 epoch 54，内部测试损失 `0.071545`、推理 P95 `0.7774 ms`，权重 SHA256 仍为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。该结果只能证明训练和安全投影管线可运行：14384 个区域动作中非零 quota、transfer、hold、request_replan 均为 0；D6 还确认 898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle admission 直接记录 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false` 和全部动作计数。当前结论是“管线可用但动作多样性不足，shadow-only”；低损失不能作为调度策略能力证据，PPO 与 assist 均失败关闭。权重只保存在 ignored `outputs/`，普通 Git 只保留配置、指标、审计、SHA256 和本地定位说明。

**2026-07-21 跨模块共享 seed 切分**：新增 `canonical_seed_split.py`，独立消费 main 发布的 `scalable3d-shared-seed-split-registry-v1`，不导入 main runtime。加载器严格核对 schema/policy、D3 兼容排序、assignment/content SHA256、源 training-seed-registry SHA、100 个数据 seed 的完整覆盖、无额外或保留 seed，并绑定原 dataset SHA、原 split SHA 和共享 registry 文件/内容 SHA。D4 原 70/15/15 manifest 与 episode 文件保持只读；显式 canonical 内存视图将同一批数据映射为 60/20/20 seed、540/180/180 episode 和 1079/359/360 frame。BC loader 只有收到 `canonical_split_view` 时采用该视图，默认行为不变。正式只读审计前后源数据目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。该能力只解决 D3/D4/D5 未来联合训练的数据切分治理，不提供新模型性能证据；PPO、assist 和正式裁决状态均未改变。

**2026-07-21 区域动作覆盖补充课程**：新增独立 `region_resource_curriculum.py` 和 CLI。每个共享训练 seed 构造保持、请求重规划和跨区转移三帧，复用 `RegionResourceSnapshot`、`RuleRegionResourcePolicy`、`DeterministicResourceProjector`、dataset-v1 和 canonical registry，不修改正式 900 episode。commit `9445ed6` 的 clean 课程为 100 seed/100 episode/300 frame、4 区域/17 聚合资源，含 hold 100、request-replan 200、非零 quota action 200、transfer 100；60/20/20 三个 canonical 桶均覆盖四类动作，硬约束违规、在线真值字段和保留 seed 泄漏均为 0。clean dirty episode 数为 0，行为克隆只读 view 可用；300/300 reward/outcome 仍显式 unavailable，PPO、assist、authority 均关闭。首次 dirty 产物只保留为开发历史。该课程只关闭“规则 teacher 动作覆盖 producer 与 clean BC 数据准入”缺口，不证明策略收益或正式 900 数据已有动作多样性。

**2026-07-20 下一轮规划 advisory contract**：`d4-region-resource-advisory-v1` 是 `RegionResourceRecommendation` 经 `DeterministicResourceProjector` 后的只读消费视图。内容寻址 `advisory_id` 同时充当幂等键；合同给出 episode-clock 创建时间、默认 1.0 s 可配置 TTL、最早 authority lease 截止时间、scenario/snapshot/authority、source plan 集合、policy/model/projector identity，并为每个区域和 transfer 固化 snapshot version、owner/layer、plan id/version、epoch、lease、ACK/fault 状态、资源前后量、protected reserve/committed、edge 端点与 capacity。`RegionResourceAdvisoryGate` 在下一轮严格重验 current snapshot/plan/epoch/lease、ACK、fault fence、守恒、transfer 邻接/容量和已消费 ID；任一不满足均输出 `consumable=false`。它只给 main 提供下一轮 D3 规划输入，不修改 D3 plan，不授权 D7，也不包含 truth/actor/object identity、成员或目标级分配。

**2026-07-20 区域化合同状态**：新增 `d4-regional-failover-v1`，面向 scalable3d 场景按输入长度维护逐区域唯一 authority。中心未 `failed` 时保持中心 owner，仅根据 D1 协方差/时效、D2 ambiguity/IDSW/duplicate、D3 plan/version/epoch/lease/current/feasible 和 D5 consistent/inconsistent/binding/friend/duplicate 证据输出继续中心、请求机动高空侦察辅助、中心重规划或保持复核；中心 `failed` 后只选择对该区域具有完整持续 readiness、coverage 和有效 lease epoch 的 `mobile_high_recon`，没有有效二级节点时才进入受约束 bid fallback。任一层级的 `k>1` 任务都必须由全部 required member 对同一 plan/coalition version、epoch 和有效 lease 完成 ACK 才成为 `committed`；区域 authority/commit lease 取 authority、D3 task 和二级 lease 的最早到期值。缺 ACK、旧 epoch/version、过期 lease 或分区均闭锁。该阶段纯 Python 验收新增 23 项，覆盖 5/20/50/100/200 区域元数据、声明节点数上限、中心与二级连续失效、双区域 coverage、中心/二级/distributed 原子门、分区、D5 member hold、跨区域 capacity、单成员多能力、旧 generation 和 lease；当时 D4 全量 **303/303** 通过，后续运行时确认阶段为 430/430、候选门诊断阶段为 482/482，当前全量见本文顶部。该模块合同本身没有 AirSim、真实网络或物理拦截样本；受约束成员选择是确定性基线，不等于完整 CCBBA、reserve 激活或在线联盟重构。

**2026-07-15 P0 历史状态**：当日重新确认的二级接管 P0 已关闭。此前 278/278 回归覆盖 coordinator、episode adapter、secondary coalition proposal 和 D6 metadata，但把它表述为“所有公开 secondary owner 入口均已闭锁”属于过度声明：`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 仍会把缺失的 sustained readiness、expected/actual source 或 plan/required lease epoch 当成“不是 False”而放行。两个 helper 及 adapter 后续均要求这些字段显式存在，`secondary_readiness_sustained is True`、source 相等、plan epoch 不低于 required epoch，且 current time/expiry 存在并严格满足 `current_time < expiry`；同 id/version 的已激活 secondary plan 维持路径也执行同一复核。当日 D4 单元测试 280/280 通过；候选门诊断阶段全量为 482/482，当前全量见本文顶部。

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
- `d4_distributed_fallback/region_resource.py`：truth-free 区域资源快照、规则建议、确定性安全投影、下一周期 advisory contract/一次性消费门、reward、数值 seed 原子划分和 paired shadow 指标。
- `d4_distributed_fallback/region_resource_dataset.py`：版本化 episode source/frame、原子 stage/finalize/load、数值 seed split、manifest/哈希与 availability 校验。
- `d4_distributed_fallback/canonical_seed_split.py`：共享 seed registry 的独立严格校验，以及不改源数据的 canonical 内存切分视图。
- `d4_distributed_fallback/region_resource_learning.py`：可选共享区域图 actor-critic、BC、原生 clipped PPO、bundle/SHA/OOD 与 fail-closed advisor。
- `d4_distributed_fallback/region_resource_training.py`：正式 dataset 只读审计、固定 seed 行为克隆、逐字段/安全/延时评估和 shadow-only 准入报告。
- `d4_distributed_fallback/region_resource_full_sample_audit.py`：正式数据和补充课程的全清单、全 episode、全 frame/sample 只读准入审计；输出显式 availability 和 fail-closed 状态。
- `d4_distributed_fallback/region_resource_runtime_ack.py`：独立解析和核对 advisory、main consumption、D3 plan ACK、D3/D7 source envelope 的只读运行时 applied-ACK 证据；不授予执行权。
- `d4_distributed_fallback/region_resource_reward_evidence.py`：把已确认采用的区域建议与非重叠、哈希绑定、真值隔离的区域结果窗口连接，输出分项观测成本和严格受限的时间窗口奖励证据；不接入 PPO 或执行权。
- `d4_distributed_fallback/region_resource_paired_intervention.py`：冻结保留 seed 的 control/treatment 同输入合同、`region_resource_bc_900_20260720` 只读候选加载与三文件 SHA 复核、隔离 arm 安全采用证据和完整 manifest；复用规则策略、确定性投影、运行确认/奖励 schema 与 paired evaluator，但不生成线上 ACK 或结果标签。
- `scripts/run_region_resource_advisor.py`：区域资源建议与 shadow paired evaluator CLI；默认 `shadow`，不改变正式 D4 verdict。
- `scripts/run_region_resource_paired_intervention.py`：严格校验并规范化 round-trip 配对 specification/manifest；不运行 episode、PPO 或性能评估。
- `scripts/train_region_resource_bc.py`：数据审计与行为克隆命令入口。
- `reports/region_resource_bc_900_20260720/`：不含权重的正式审计、训练配置、指标、模型准备度和本地 bundle 定位。
- `reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.{json,md}`：供 D6 通过显式路径和带外 SHA256 复核的全样本证据。
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

正式 snapshot 使用 `recommend --snapshot PATH [--bundle-dir PATH]`；advisor 结果同时给出 projected recommendation 与 `advisory_contract`。main 若要将其作为下一轮 D3 规划输入，必须用同配置 `DeterministicResourceProjector.validate_for_consumption()` 或 `RegionResourceAdvisoryGate.consume()` 在 current snapshot 上重验。paired 评估使用 `shadow-evaluate --baseline PATH --candidate PATH`。即使显式请求 `--mode assist`，少于 20 个未见 seed、规则回退或任一模型门失败时仍降为 shadow。

正式行为克隆训练命令记录在 `reports/region_resource_bc_900_20260720/TRAINING_COMMAND.md`。本地 bundle 位于 Git 忽略目录，加载前必须核对模型版本和权重 SHA256。当前包的最高模式固定为 `shadow`，不能由 `--mode assist` 或调用方传入的 seed 数解除。

main 的 region-learning writer 不应再自行拼接 D4 私有 JSON。每个 episode 结束时构造公开 `RegionLearningEpisodeSource` 与 `RegionLearningFrame[]`，逐帧把缺 target/reward 写成带原因的 unavailable，再调用 `stage_region_learning_episode()`；批次完成后调用 `finalize_region_learning_dataset(..., minimum_unseen_seeds=声明值)`。训练端先调用 `load_region_learning_dataset()` 验证全部哈希，再分别使用 `load_region_behavior_cloning_samples()` 或 `load_region_ppo_training_episodes()`；PPO 返回的是完整 episode 预处理记录，不伪造 old log probability、value、advantage 或 return。

跨模块联合训练必须由调用方显式加载共享视图，再传给 BC loader：

```python
view = load_canonical_region_learning_split_view(
    dataset,
    shared_registry_path=shared_registry,
    training_seed_registry_path=training_seed_registry,
)
samples = load_region_behavior_cloning_samples(
    dataset,
    split="train",
    canonical_split_view=view,
)
```

不传 `canonical_split_view` 时继续使用 D4 manifest 内的 70/15/15 切分。共享视图不会写 sidecar 到源数据目录，也不能解除 reward、动作多样性、PPO 或 assist 门槛。

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- 区域化 scalable3d 合同：`RegionalScenarioMetadata.from_scalable_scenario()` 只读消费 `scalable3d-scenario-v1` 的 target/resource/recon/region count，并拒绝 schema 或声明数量溢出；`RegionalFailoverCoordinator` 按实际 region/task/node 列表运行并输出 truth-free `d4-regional-failover-v1` bus payload。逐区域 owner 变更必须同时提升 `epoch` 和 `plan_version`，租约严格使用 `timestamp < expiry` 且收缩到最早 D3 task/secondary expiry，同 generation 不允许换 owner，分区时所有层级闭锁。
- 全局区域资源建议：`RegionResourceSnapshot` 和 `RegionResourceEdge` 按变长区域图运行；规则 fallback 与学习候选共用同一 `DeterministicResourceProjector` 实例，保证总资源守恒、只走可通信/可机动邻边、最低备用、当前 authority fence 和已提交联盟资源。`RegionResourceAdvisoryContract`/`RegionResourceAdvisoryGate` 进一步提供版本化、限时、幂等且 fail-closed 的下一周期消费接口。`SharedRegionGraphActorCritic`、BC/PPO 与模型 bundle 只属可选研究路径，默认不参与正式 D4 裁决。
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
- 2026-07-21 全样本准入阶段为 397/397 项通过，新增专项 10/10；加入运行时确认、区域奖励合同、冻结 bundle 隔离加载和候选门诊断回归后，该历史阶段 D4 全量为 482/482。2026-07-25 当前全量为 569/569。正式和补充数据的模块内准入状态为 complete，但 D6 外部带外 SHA256 复核、真实运行时 ACK/outcome、可归因 reward、20-seed 同 seed paired outcome、真实链路、误降级率、恢复时间和物理任务连续性仍开放。机器可读准入固定禁止把规则教师标签、后投影 recommendation、隔离采用或低损失写成运行策略能力、applied ACK 或 assist 资格。
- 二级接管正例：协调者 `Secondary_Recon_1`，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_secondary`。
- 完全分布式正例：协调者为 `INT-02` peer，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_distributed`。
- 缺 ACK 负例：确认窗口显式截止时 ACK 仍为 2/3，最终 `aborted`；T001 三个成员保持 `hold_for_review`，D7 许可为 0。普通快照在截止前保持 `collecting_acks`。该结果确认 fail-closed；有有效 commit 的二级/分布式路径已获正例验证。
- SimpleFlight 15 s 结果仅用于断点诊断：30 个 active pair 物理命中为 0，不能据此宣称 D4 fallback 或系统物理拦截闭环完成。
- 仍开放：将已冻结的 P1 扰动合同映射到真实 AirSim 同 seed 成对试验，完成 heartbeat/link/cue/gimbal/source、secondary-interceptor/peer split、误降级、恢复时间及物理连续性多 seed 统计。模块 replay 不等于系统矩阵验收完成。
- P2 只允许隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或其他 adapter 不替换当前轻量 CBBA 和 ACK/lease/epoch 合同。
- P2 原生确定性 replay 已收敛：6/6 场景符合预期安全结果；中心 -> 二级 -> 分布式和手工预编排的 member-loss/replacement 场景均以 7 轮、完成率 1.0、冲突 2/1、最优绝对差距 0.0 收敛。该结果只验证调用方给定替换成员后的版本/ACK 合同，不是自主补位能力。missing ACK、stale epoch、expired lease、partition 分别以 2/1/2/3 轮 fail closed，完成率均为 0，并输出对应 optimality-gap unavailable reason。
- 默认环境未配置 MIT CBBA 或 CA-CBBA 参考路径，因此各 6 个外部对照行分别输出 `mit_cbba_reference_path_not_configured`、`ca_cbba_reference_path_not_configured`。MIT MATLAB 源码树即使被检测到也报告 runtime adapter 未集成；已审计的 CA-CBBA 公共仓库没有可执行源码。上述 unavailable 是 capability 结论，不是外部算法性能结论。

历史基线：2026-07-10 calibration sweep 和 2026-07-11 早期 truth-isolated smoke 曾因 network full-view/readiness 不持续而未形成二级 active plan。该结论只描述实施前场景，不再作为当前能力状态；门限与 fail-closed 规则仍保留。
