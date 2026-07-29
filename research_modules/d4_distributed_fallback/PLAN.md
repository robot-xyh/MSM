# D4 分布式协同与降级接管计划

## 2026-07-28 当前谱系候选 P1

### 已完成

- 已审计既有训练、development candidate 和 bundle 流程。旧候选把 test split 用作独立
  calibration 门，保留为历史 development 证据，不作为当前谱系候选。
- 已新增 clean-lineage 构建/复核入口。整个工作区必须干净，固定实现文件必须已跟踪且与
  `HEAD` 内容一致。
- 已新增 train/validation 选择性 loader。模型训练只读取 train，早停和模型选择只读取
  validation；test payload、旧 calibration 和 seed 1000-1019 使用数固定为 0。
- 已将源码实现、数据集、split、配置、模型 manifest、权重和训练摘要闭合到同一严格
  manifest。权限字段、非有限输出、切分重叠和内容篡改均失败关闭。
- 已用五 seed 临时 clean Git fixture 完成真实 CLI 构建、磁盘加载和复核。结果只属于
  development/shadow 软件诊断，不是正式 A2 证据。
- 已在独立 clean checkout `b0d498d9e76e19e9045e127b6dae26ea164b3fa4` 用默认冻结配置
  构建当前谱系实物，并再次通过 `review-only`。候选 manifest、权重、数据集、split 和
  source identity 均已内容寻址。
- 已在不读取 test/calibration/reserved seed、不修改门限的条件下，对实际模型执行
  train/validation 开发诊断。结果分别为 168/180 和 54/60 安全非零动作；其余 12 和
  6 个样本与基线相同，资源不可行、非有限输出、身份错配和门控回退均为 0。

### 当前状态

当前谱系 development/shadow 实物已经生成，模型权重保留在 Git 忽略的 `outputs/`。源码
身份绑定 clean commit `b0d498d9...`；后续源码提交不会被解释为同一候选。训练和验证诊断
均属于已见开发分布，不能替代正式未见 seed。A2 admission、assist、authority、
assignment、takeover、coalition commit、control、actual adoption 和 benefit 仍全部为
false。

### 下一步

1. main 冻结候选 manifest 文件摘要 `7cc10ad7...de64`、权重
   `fd1b9c4c...0047` 和 clean commit，不再修改候选或门限。
2. 使用至少 20 个从未进入训练、验证或历史 calibration 的正式 seed。
3. treatment 必须由该冻结实际模型形成可辨识非零区域干预，不能使用规则派生 development
   adapter 冒充模型动作。
4. 继续闭合 D3 严格后继计划、runtime ACK、owner/coalition ACK、确认后物理窗口、独立
   same-key R0 和 D6 非退化审计。
5. 完成前保持 A2 admission、assist、authority、assignment、takeover、coalition commit
   和 control 全部为 false。

验证日期为 2026-07-28。构建和 review-only 均通过；新增专项 **8/8 passed**，D4 全量
**697/697 passed**。本轮没有运行 AirSim 或正式多随机种子实验。

## 2026-07-27 A2 实际模型诊断与后续校准计划

模块内 development-only 实际模型诊断路径已经完成。路径不修改模型和安全状态机，只从
候选清单读取互斥的 train/validation/calibration/reserved seed 目录，在 calibration 目录
上执行以下固定顺序：

1. 验证候选、模型权重、数据集和校准种子身份，拒绝 dirty 来源、保留 seed 和真值字段。
2. 执行实际 `LearnedRegionResourcePolicy` 推理，并固定使用 0.60 置信门和 0.05 分布外
   余量。动作分类使用固定 0 ms 功能性时延覆盖以消除主机调度抖动；50 ms 运行门配置不变，
   时延性能另行验证。
3. 逐区域比较原始与投影后配额、整数备用资源、`hold` 和 `request_replan`；逐转移检查边
   容量、链路掩码和源区域资源预算。
4. 将无操作归因为动作与基线相同、置信不足、动作掩码、owner/lease/epoch、资源不可行或
   批次策略输出退化。只有模型身份一致、固定门通过、advisory 可消费且干预字段非空时，
   才记录 `safe_nonzero_actual_model`。
5. 输出仅为开发诊断。不得装配正式 runtime adoption、收益或任何权限。

2026-07-27 的本地完整校准运行包含 20 seed/420 sample。结果为固定门通过 420、回退 0，
安全非零实际模型动作 76、资源可行域无操作 344；保留 seed 和在线真值使用均为 0。原始
可执行动作签名为 88 种，批次退化为 false。当前结论说明模型能产生非零区域动作，也说明
nominal/全承诺资源状态会系统性压掉备用比例建议。受控
`ConstrainedDevelopmentRegionResourceAdapter` 继续只作链路探针，不能替代本次模型证据。

该节记录 2026-07-27 历史候选的后续判断。第 1 项现已由本文件首节关闭，不再重跑历史
calibration：

1. 当前实现谱系候选已经重新生成并冻结；旧候选仍只用于历史开发诊断。
2. 如未来修改模型，在新的 train/validation 周期内处理全承诺资源下的零备用动作表达，
   可研究显式零动作头或
   feasibility-aware mask；不得用校准或 seed 1000-1019 调门限。
3. 当前冻结候选直接进入至少 20 个正式未见 seed 的影子评价，不再使用历史 calibration
   调参。
4. 在正式未见 seed 上生成严格后继计划、owner/coalition ACK、物理窗口和
   独立同键 R0，并交由 D6 做非退化审计。

本轮专项 **10/10 passed**，D4 全量 **689/689 passed**。候选清单 SHA-256、模型
manifest/权重摘要、逐 seed 分母和分类摘要均已绑定；两次重跑稳定得到 76/420 与 344/420。
assist、assignment、center replan、secondary takeover、coalition commit、failover 和
control 权限保持 false；未启动正式 900-cell、AirSim 或大写盘实验。

## 2026-07-27 提交前状态

模块内 A2 类型边界、通信映射严格解析、成员确认有限值检查和中心/二级/完全分布式三层
非授权回归已完成。开发适配器仍只能用于 development/test-only 探针，正式收益审计在来源
入口拒绝其策略身份。D4 全量 **679/679 passed**，关键文件 `py_compile` 与 scoped
`git diff --check` 通过。

仍开放的 P1 不在本次模块内收尾范围：main 真实 episode 的 owner/coalition ACK 路由与
物理窗口持久化、独立同键 R0 和 D6 非退化审计、二级/完全分布式 AirSim 多随机种子验证，
以及当前谱系 A2 策略在正式未见种子中的实际采用和收益验证。独立校准集已经证明旧
development 模型可产生非零动作，但未形成运行时采用。上述证据形成前，学习
assist、failover、assignment 和 control 权限继续关闭。

## 2026-07-27 A2 开发态干预计划状态

D4 模块内“候选始终为无操作，无法验证后继证据链”的开发可测性缺口已关闭。实现采用显式
启用、场景白名单和运行标签三重边界，不修改默认 development 模型、正式 advisor 准入或
main 控制路径。

处理顺序为：

1. 读取原学习候选并验证 learned source、模型摘要、snapshot/authority 身份、区域覆盖和
   未投影状态。
2. 用与规则策略共享的确定性投影器投影原候选，构造 advisory 并执行同 snapshot 消费检查；
   再按安全采用链相同的 D3 可消费字段判断是否存在真实干预。原始字段变化但投影后回到
   基线时仍视为无操作。
3. 原候选为无操作时，先选择单区域 request-replan-only；其次选择受总量上限约束的 transfer；
   最后只在 `committed_resources=0` 的区域选择 hold。
4. 每一级候选都重新执行投影、发布和消费判定；投影后无操作则继续下一优先级。保留原
   action 上的 owner、layer、plan、version、epoch 和 lease，正式链路继续带 formal
   decision 复核。
5. 开发策略不进入正式收益审计，不授予 assist、assignment、failover 或 control 权限。

formal decision 通过显式 `formal_decision_aware` 协议进入首次候选判定，正式 advisor 随后
仍执行第二次投影。`force_request_replan_on_projected_noop` 默认关闭，仅允许显式开发探针
开启。开启后若规则没有 request、transfer 和安全 hold，适配器可对一个 formal-eligible
区域发出 request-replan-only；它不能 hold 已承诺任务、转移受保护资源或修改权威身份。

main 开发探针的最小配置为：

```python
RegionResourceDevelopmentInterventionConfig(
    enabled=True,
    run_label="a2-nonzero-pairing-development",
    allowed_scenario_ids=(scenario_id,),
    maximum_total_transfer_resources=1,
)
```

main 应把现有 learned policy 包装为
`ConstrainedDevelopmentRegionResourceAdapter`，并仅用于 development/test harness。
合法非零候选完成 `prepare()` 后，缺 D3 后继计划时的预期状态为
`awaiting_d3_plan`，原因为 `d3_successor_plan_missing`。均衡且没有合法动作的场景仍为
`safe_adoption_rejected / identifiable_regional_intervention_missing`。旧
owner/epoch/lease 或投影修改仍为
`candidate_rejected / deterministic_projection_rejected_or_modified`。

main 先前 hold+request helper 的 20-seed 内存结果为 15/20。D4 已对问题 seed
1000、1002、1007、1009、1013 增加 request-only 回归，模块内均通过；main 下一步应使用新
适配器重跑相同 20 seed，逐 seed 保存候选动作类型、投影字段、D3 successor reason 和最终
stage。未完成该重跑前，不把模块测试推导为 20/20 runtime adoption。

2026-07-27 新增两个两区域单样本回归：区域 A 为 3 个可用资源、2 个已承诺资源、1 个基线
备用资源，原候选给出 `reserve_ratio=0.6`。投影后备用资源仍为 1，原候选被判为无操作，
适配器继续输出 request-replan-only，并形成非空 D3 可消费干预；formal-only committed
member 同样参与首次投影。验证为安全采用专项 **68/68 passed**、D4 全量
**674/674 passed**。

同一日期已用 development-only admitted transport 夹具运行 1 次指定 full episode：
5 target/5 resource/1 recon/2 region、3.0 s、seed 1、radar detection probability 0.45。
显式开启 `force_request_replan_on_projected_noop` 后，1/1 A2 记录到达
`physical_window_available`，可辨识干预、安全采用和物理窗口均可用，权限和收益均不可用。
当前 P1 是 main 将该 formal-aware 调用固定到自身开发探针、完成 20-seed 重跑和独立 R0。
实际旧 development 模型已在独立 calibration split 产生 76 个安全非零动作，但当前实现
谱系、正式未见 seed 和运行时采用尚未闭合；标准 advisor 的适配器仍为 shadow，该开发探针
不关闭模型准入或收益 P1。

## 2026-07-27 A2 无操作归因计划状态

D4 模块内的无操作归因缺口已关闭。执行顺序调整为：

1. 候选继续经过确定性投影和消费检查，保留链路探针用途。
2. D4 从 advisory 重建投影前后区域载荷，比较资源配额、跨区转移、整数备用资源、
   `hold` 和 `request_replan`。
3. 没有上述变化时，记录 `identifiable_intervention_available=false`，并在绑定 D3
   后继计划前失败关闭。
4. 只有存在可辨识干预时，才继续验证严格后继计划、运行确认、所有者确认、必要联盟提交和
   物理窗口。
5. D6 收益输入必须同时携带干预标识、内容摘要和非空干预字段。

`total_quota_delta` 不作为单独判据，因为真实跨区转移在资源守恒条件下总增量同样为零。侦察
优先级目前未进入 D3 可执行提示合同；只有后续跨模块合同明确消费并形成可观测执行变化后，
才可纳入干预集合。

main/D6 已于 2026-07-27 按新口径完成 20-seed 开发批次重算：链路探针 20/20，可辨识
干预、实际采用和收益审计均为 0/20。20 个拒绝原因均为
`identifiable_regional_intervention_missing`，批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。原 18/20 采用结论
已被该结果取代。main 不得再以普通 D3 计划升版推导 A2 采用。D6 分别统计
`projection_consumed`、`identifiable_intervention`、`successor_execution_adopted` 和
`benefit_audit_eligible`。

安全采用专项为 **52/52 passed**，运行时集成专项为 **6/6 passed**，D4 全量为
**658/658 passed**。过时的 refresh 正例已拆为无操作和真实 successor 两条路径，不再要求
main/D3 为无操作建议生成 `evaluation_refresh_applied`。本批开发制品和总报告口径修正
已经完成；后续 P1 是生成具有非空干预、独立同键 R0 和正式未见 seed 的真实收益证据。

## 2026-07-27 A2 同键 R0 合同状态

D4 模块内的 same-key R0 输入合同已完成。新合同不把 R0 或收益字段写入在线安全采用前缀，
而是在 episode 结束后建立只读配对记录。共同上下文冻结 comparison key、场景/版本、规模、
seed、逻辑窗口、窗口时长和 `paired_exogenous_config_sha256`。候选臂与规则臂各自保存
execution arm、episode 事件日志、物理窗口、计划版本和有效期；R0 固定使用确定性规则
`d4-region-resource-rule/v1`。

模块内处理顺序为：

1. 从进程内 `RegionResourceSafeAdoptionEvidence`，或从
   `learning_adoption_evidence.json` 的完整 A2 记录，严格提取候选来源视图并复核内容哈希。
2. 将候选窗口绑定到安全采用记录、建议 ID/版本、策略身份、严格后继计划、租约和物理窗口
   SHA-256。
3. 从独立 R0 episode 构造规则窗口引用。两臂必须具有相同外生配置和逻辑窗口，但
   execution arm、event log ID/hash、physical window ID/hash 必须不同。
4. 检查窗口时长、完整性、物理执行、计划有效期、权威租约和硬约束。批量装配再检查每个
   comparison key 只有一个 R0，且 R0 日志、窗口和执行臂不重复。
5. 仅在全部条件满足时输出 `d6_benefit_audit_eligible=true`。D4 不读取结果指标，也不计算
   收益。

2026-07-27 安全采用专项 **50/50 passed**，D4 全量 **655/655 passed**。新增合同文件已进入
A2 实现谱系清单，后续正式外层 evidence 必须使用包含该文件的新 D6 implementation
evidence，旧实现摘要不能跨版本沿用。

剩余工作属于 main/D6 跨模块 P1。main 需用同一
`paired_exogenous_config_sha256` 运行独立 A2 与 R0 episode，持久化各自 episode identity
和事件日志摘要，并组装 D4 输入；D6 再从两份独立日志计算指标、非退化和最终收益。至少
20 个未见 seed 通过前，`a2_benefit_available`、assist、模型晋级、分配权、故障接管权和
控制权均保持 false。本轮没有修改 AirSim 场景、D3 计划器、D5、D6 或 D7。

## 2026-07-27 A2 确认收据复用计划状态

D4 模块内缺口已关闭。因果证据门把“不可变 ACK 绑定”和“本次安全采用评估时刻”分开管理。
同一 owner/coalition ACK 只有在 receipt、evidence kind、source/destination、message、
payload、plan/epoch/lease 和 partition generation 全部不变时，才能在更晚评估中再次引用。
每次引用都重新检查消息已到达、评估时间不回退且租约仍有效。

验证覆盖以下路径：

1. owner ACK 在早期评估通过，物理窗口尚未形成，状态保持
   `awaiting_physical_window`；
2. 同一计划和权威绑定在更晚时刻形成物理窗口，原 ACK 幂等复用并通过；
3. 修改 expected ACK 绑定、目的节点、消息标识、计划、时期、租约、分区或载荷摘要均拒绝；
4. 评估时刻回退、租约到期和同 receipt ID 内容冲突均拒绝。

2026-07-27 通信与安全采用专项 **99/99 passed**，D4 全量 **637/637 passed**。下一步由
main 在真实动态 A2 episode 中复跑“首次 owner ACK -> 后续非 hold 控制 -> 物理状态变化”
链路，并由 D6 继续保持收益 unavailable，直到形成 same-key R0。D4 不修改 PN/PNG、D3
计划或 AirSim 场景。

## 2026-07-27 A2 严格证据桥接计划

D4 公共合同已完成以下模块内工作：解析并保存 main 运行时计划确认的 payload SHA-256 和
总线序号；构造、严格解析和验证 `d4.regional_plan_owner_ack.v1`；从实际 delivered
message 自动构造内容寻址回执；严格解析带嵌套 `CoalitionMemberAck` 的联盟确认；通过公共
validator 复核 owner/plan/advisory/runtime-ACK/epoch/lease/partition/timestamp 绑定。main
不需要也不应复制 D4 私有规范 JSON 或 receipt ID 算法。

main 后续按以下顺序接线：

1. 仅对通过确定性投影且 `source=learned` 的候选保留
   `RegionResourceAppliedRecommendation`；规则回退记录在负对照，不进入采用分母。
2. D3 发布引用同一 advisory 的严格更高版本计划。main 保存计划 payload SHA-256 和
   envelope sequence。
3. main 发布 `runtime.assignment_plan_ack`，把实际 ACK envelope 交给
   `RegionResourceRuntimeAckParser`。解析结果必须有
   `assignment_plan_ack_payload_sha256` 和 `ack_bus_sequence`。
4. 所有者使用 `build_region_resource_owner_plan_ack()` 形成确认 payload；main 只从实际
   delivered message 调用 `RegionResourceOwnerAckDelivery.from_delivered_message()`，
   再调用公共 owner validator。
5. 多成员任务逐条调用
   `RegionResourceCoalitionAckDelivery.from_delivered_message()` 和公共 coalition
   validator。全部必要成员通过后，现有 `CoalitionCommitCoordinator` 才可进入 committed
   和 executing。
6. main 在确认完成之后记录 truth-free 物理执行窗口。D6 按完全相同 comparison key 生成
   R0 并执行收益审计。

采纳阶段不得乱序：

```text
deterministic projection
  -> strict D3 successor plan
  -> runtime assignment ACK
  -> delivered owner ACK
  -> delivered member ACKs + atomic coalition commit（需要时）
  -> physical execution window
  -> same-key R0 / D6 benefit audit
```

2026-07-27 模块验收为四文件联合 **130/130 passed**、D4 全量 **626/626 passed**。本轮
没有新增 AirSim 场景或随机种子。D4 模块 API 缺口已关闭；跨模块 P1 仍开放，包括 main
回调和消息路由、真实 owner/coalition delivery sidecar、采用后物理窗口、同键 R0 和 D6
独立收益审计。任一项缺失时必须保持 unavailable，不能填 0。正式 A2、assist、PPO 和运行
authority 继续关闭。

## 2026-07-26 A2 安全采用生产与接线状态

D4 模块内生产和验证合同已完成。`RegionResourceSafeAdoptionAssembler.prepare()` 把真实学习
候选送入现有确定性资源投影，并在正式 D4 裁决、权威层级、所有者、计划、时期号、租约、
邻接、容量、保留资源和网络分区门内形成待采用建议。`assemble()` 再验证 D3 严格后继计划、
运行时确认、所有者实际投递确认、必要联盟提交和物理窗口。规则候选、规则回退、低于 0.60
置信门的候选和含在线真值/结果/奖励字段的输入均失败关闭。

模块验收日期为 2026-07-26。专项 **27/27**、相邻证据链 **100/100**、D4 全量
**621/621 passed**，修改入口通过语法检查。测试覆盖有效二级采用、有效对等节点联盟采用、
缺计划、缺运行时或所有者确认、缺联盟提交、缺物理窗口、旧时期或版本、过期租约、非法区域
转移、容量超限、网络分区、中心正常时误降级、二级优先级、在线真值隔离和确定性重放。测试
fixture 只验证合同，不计入正式实际采用。

后续接线按以下顺序执行：

1. main 从真实候选推理输出构造 snapshot、candidate、formal decision 和
   `RegionResourceSafeAdoptionContext`；多权威域建议按所有者、时期和租约拆分。
2. D3 发布严格更高版本计划，并提供源建议标识/版本/载荷摘要、计划载荷摘要和总线序号；
   main 只能在计划已实际接受且区域提示已应用后建立后继计划引用。
3. main 路由现有生产 `RegionResourceRuntimeAckEvidence`，并把二级或对等所有者通过
   `d4.regional_plan_owner_ack.v1` 实际送达的确认转换为内容寻址回执。无投递不得补造确认。
4. 需要多成员联盟时，D4 接收执行态 `CoalitionCommitState` 和每个必要成员通过
   `d4.coalition_member_ack.v1` 送达的确认。旧代次、缺成员或分区继续阻断。
5. main 从计划确认后的真实状态积分生成物理窗口。D6 在带外添加同键规则基线、配对结果和
   收益审计，再交给既有 20-seed A2 装配器。

当前 P1 仍是运行时证据生产与系统验证。现有隔离 degraded 制品没有真实学习候选采用，
main 的 `candidate_considered=false` 和 `deterministic_rule_fallback` 记录不能转为正例。
在 20 个实际采用、确认、物理窗口、同键规则基线和联盟完整性全部形成前，assist、PPO、
默认模型、分配权、故障接管权和控制权继续关闭。

## 2026-07-26 A2 证据装配实施状态

模块专用 evidence assembler 和 strict loader 已完成，先前“缺少证据装配软件合同”的 P1
代码项关闭。新合同使用 `d4-region-resource-a2-evidence-bundle-v1` 外层包裹不可变
development bundle，并按候选指纹、实现谱系、D6 审计、正式 scope、逐 seed runtime chain
和联盟执行事实进行内容寻址。输出只表达 `a2_assist_eligible`；默认模型、PPO、模型晋级、
故障接管、分配和控制权限继续关闭。

软件合同验收日期为 2026-07-26。合成完整 fixture 专项 **17/17 passed**，相关证据合同
**124/124 passed**，D4 全量 **594/594 passed**，新增入口均通过 `py_compile`。正例采用
合成的 20-seed 完整制品，仅证明装配器和严格加载器在完整输入下可以工作。

当前实物准入仍失败关闭。实际 development bundle 配合 D6 当前外审时稳定返回
`d6_external_audit_fail_closed`，输出目录未创建，源 manifest、权重和训练清单未改写。后续
按以下顺序补齐真实证据：

1. main 和 D6 冻结 seed 1000-1019 的正式 scope、精确校验清单和当前实现 evidence。
2. 非 nominal 降级 treatment 实际采用候选并通过 0.6 置信门、确定性投影和全部 authority
   fence；规则回退不计入采用。
3. D3 发布严格更高版本后继计划，main 保存生产语义 runtime ACK、owner/epoch/lease/fault
   generation 及完整联盟成员 ACK。
4. D6 从 ACK 后物理窗口形成唯一 same-key R0 和 paired non-degradation，并确认零硬约束
   违规、零在线真值使用和零 `global_track_id` 改写。
5. D4 只读装配这些实物。任一缺项或摘要不闭合时继续使用规则路径，不生成 A2 外层包。

当前开放项属于证据生产与正式验证，不再是 D4 assembler 软件缺口。AirSim 接口、故障状态机
和区域 advisory 运行接口未改变。

## 2026-07-26 A2 development 候选收敛与后续验证

模块内候选训练与校准已完成。新版候选绑定正式 900 episode、clean supplemental
100 episode、规范 60/20/20 seed 视图、实现文件和独立校准证据；固定
`minimum_confidence=0.6`、`latency_limit_ms=50`、分布外边界和确定性安全投影均未放宽。
校准正门为 420/420，四类必要动作均有预测正样本，分布外拒绝为 420/420。候选只允许
isolated/shadow，production writer/loader 仍不能自声明 qualified、assist 或 authority。

下一阶段按以下顺序执行：

1. main 冻结 `1000-1019` 的未见 seed 场景、通信和故障时序。这 20 个 seed 不得回流到
   训练、阈值、温度、置信拟合或场景筛选。
2. 在 `center_failed`、`center_and_secondary_failed` 和 `active_risk` 隔离场景生成规则
   control 与候选 treatment。nominal 只作负对照，不进入降级采用正样本分母。
3. treatment 必须先通过 0.6、50 ms、分布外、有限值、外部故障和原确定性安全投影，再由
   D3 形成严格更高版本的计划；旧 epoch/lease、ACK 不完整、网络分区或投影失败继续规则
   回退。
4. main 保存候选清单、D4 advisory、source/applied plan、owner/epoch/lease、联盟成员
   ACK、D3/D7 绑定和隔离消费回执。D6 独立计算采用后物理 availability 与同输入规则基线
   非退化。
5. reserved-seed 证据完整前，不实现或授予正式 assist。即使隔离采用通过，也只形成 A2
   外部证据候选，不直接获得 authority。

当前模块内 P1“动作正类不足、置信头未训练、候选缺少证据绑定加载路径”已关闭。A2 的外部
P1 仍开放：20 个保留 seed 尚未运行，新执行计划 ACK、联盟投递回执、物理结果和配对因果
证据尚未形成。

本轮模块验收为 **577/577 passed**；新增和修改入口通过 `py_compile`。AirSim 接口未改变。

## 2026-07-26 A2 预准入证据装配计划

本节是新版候选训练前的历史计划。模块内候选训练与校准现已按上一节完成；本节关于正式
promotion 所需外部证据的约束继续有效。

本轮只读盘点确认没有新的 D4 P0 软件旁路。现有 v2 bundle writer/loader、advisor、
runtime ACK、区域 reward、联盟状态机和通信因果回执都保持原安全边界；不训练、不运行正式
多 seed，不放宽 `minimum_confidence=0.6`、`50 ms`、assist 或 authority。

本节所列 D4 P1 代码任务已由页首的软件合同完成；以下内容保留为原设计约束和真实证据生产
顺序。装配器不重定义 D6 的通用审计 schema，不从 `evidence_admission_allowed` 裸布尔
直接晋级，也不修改旧 v2 manifest。实施顺序为：

1. D6 先固定可校验的外部审计制品、逐 cell 采用状态、物理指标 availability、R0 配对、
   non-degradation 和 `SHA256SUMS`；D4 只读消费。
2. main 提供同一 clean execution plan 下的 A2 非 nominal 降级 episode，实际采用 D4 候选，
   并保存 D3/D7/main 运行 ACK、严格后继计划和通信投递制品。
3. D4 装配器按候选 bundle/advisory/model、scenario/seed/comparison key、source/applied
   plan、owner/version/epoch/lease/fault generation、coalition required/acked members、
   delivered receipts、物理窗和 D6 pair 逐项连接。跨候选、跨 seed、跨 authority、跨
   comparison key 或缺 availability 一律失败关闭。
4. 只有装配结果完整且 D6 审计明确通过，才允许新 writer 在新目录生成独立的新 schema
   bundle。旧 development bundle、训练 manifest 和权重保持只读；新 loader 必须重算所有
   引用制品摘要。
5. main 最后分别验证 scope 预检、episode 内实际采用和默认规则回退。正式 assist 只能影响
   受现有确定性投影和 authority fence 约束的区域建议，不能直接获得运行 authority。

上述实物尚未形成，因此当前不能执行真实装配。合成 fixture 只用于验证代码路径，不替代
`new_execution_plan_applied` 的真实 D4 候选 ACK、同一联盟的逐成员因果回执、采用后物理
结果或同 comparison key 的 R0 配对非退化。

## 2026-07-26 A2/C1/F1 准入计划

当前结论为 **D4 不可生成新的 admitted bundle，A2/C1/F1 不可启动**。现有 v2 bundle 只允许 `development/shadow`；writer 已拒绝自声明 `qualified/assist`，无 manifest 的注入策略也保持 shadow。旧 bundle 三项 SHA-256 固定为 manifest `dad2adbe...c05c9`、权重 `3da0360b...d5f62`、训练清单 `ff3081c8...30dc6`，不得修改这些文件自我晋级。

下一验收按以下顺序执行：

1. D6 先冻结通用外部审计输出；D4 随后定义模块专用 evidence assembler 和新 bundle
   schema。新 bundle 必须另目录生成，并绑定旧候选身份、clean source commit、完整制品树和
   带外 SHA-256；v2 manifest 不增加兼容白名单，也不复制 D6 审计字段定义。
2. 在 `center_failure`、`secondary_failure` 或 `active_risk` 等真实降级场景运行保留未见 seed 配对试验。nominal、同帧离线比较、规则回退和 unavailable outcome 不进入准入分母。
3. treatment 必须实际采用 D4 候选并产生严格更新的执行计划。D4 证据需逐 seed 绑定 `new_execution_plan_applied`、有效 owner/plan/epoch/lease、完整联盟成员 ACK、无分区和零安全违规。
4. D6 从采用后的独立物理状态窗计算候选与规则基线，输出物理结果 availability 和配对非退化。两臂相同、候选采用为 0 或只有描述性规则回退时不得通过。
5. main 在新 bundle 形成后再修改学习预检，把 D4 的证据绑定准入和 episode 内实际 assist 采用同时写入诊断。提交 `d59352b` 当前预检仍显示 `pending_runtime_shadow_gate`，正式学习 episode 数为 0。

本轮验收日期为 2026-07-26，无新增仿真 seed。代码验收要求“自声明 assist 不创建目录”和“无 admitted manifest 的注入策略不进入 assist”；D4 全量结果为 **569/569 passed**。

## 2026-07-25 异步 M-to-N 联盟确认计划

**D4 模块修复和 main 单随机种子集成复跑已完成；AirSim 多随机种子与正式矩阵待执行。**

已完成：

1. 普通区域快照取消隐式 `finalize=True`，提案和部分 ACK 在租约内保持 `collecting_acks`。
2. ACK 位图按同一 plan、epoch 和 coalition generation 跨快照保留；全部必要成员到达后原子提交。
3. 增加默认关闭的 `finalize_coalition_collection`，供明确截止条件触发 `missing_required_acks`。
4. 保留租约、分区、摘要冲突、成员不可执行、陈旧版本和无效 ACK 的失败关闭门。陈旧或无效 ACK 不计入成员位图，也不授权执行。
5. 2026-07-25 新增 5 项生命周期回归，三文件专项 **97 passed**，D4 全量 **569 passed**。验收阈值为完整 ACK 前执行授权 0、完整 ACK 后原子提交 1、所有负例执行授权 0。

main 集成复跑结果：

1. 2026-07-25 已运行 2 目标、4 资源、1 个二级侦察节点的 scalable 3D 场景，随机种子 `1271`；高威胁目标使用 2 个主成员和 1 个备用成员。
2. 中心在 `1.5 s` 失效，单程通信时延为 `0.04 s`，无抖动和丢包。二级计划版本 2 在 `2.00 s` 发布；`2.05 s` 为 0/3 ACK 和 `collecting_acks`，`2.10 s` 为 3/3 ACK 和原子 `committed`。
3. 提交前两个主成员保持 `d4_hold_for_review`，备用成员保持 `assignment_not_current`；提交后两个主成员进入 `midcourse_pn_3d`，备用成员不越权执行。在线真值使用和 `global_track_id` 改写均为 0。
4. main-owned 模块栈回归为 66 passed，scalable 3D 全量为 272 passed；这组结果是单随机种子质点集成证据，不是 AirSim、多随机种子、真实网络或 200 对 200 性能证据。

main 后续需在 AirSim 和正式实验矩阵中复现通信延时、丢包、分区、租约到期和新版本重新确认，并由 D6 聚合逐随机种子结果。

## 2026-07-25 P0 区域通信因果证据门

**D4 合同和 main 因果通信接线均已完成；作为强制回归保留。**

D4 已交付：

1. 不可变通信投递回执和 truth-free payload 摘要，完整携带 transport、authority、plan、epoch、lease 和 partition generation。
2. 固定的版本化 topic 到消息类型映射；严格 delivered-message 工厂从 envelope/payload 提取字段，不接受调用方覆盖。
3. 二级 readiness、区域计划广播、区域计划所有者确认和联盟成员 ACK 四个独立验证入口。
4. 稳定失败原因、exact replay 幂等、conflicting replay/跨用途复用拒绝，以及 `authority_granted=false` 权限边界。
5. 5/20/50/100/200 参数化测试和 main 的 5v5 通信关闭语义负例。因果证据专项 56/56 通过；加入异步联盟测试后 D4 当前全量为 569/569。

main 已完成并应持续回归：

1. 为 readiness、区域计划广播、区域计划所有者确认和成员 ACK 发布版本化 envelope；
   payload 补齐 `schema/message_id/message_kind/authority_id/plan_version/epoch/lease_expires_at_s/partition_generation`。
2. 把上述消息全部送入 `DeterministicCommunicationNetwork`，只对 `deliver(timestamp)` 实际返回的消息调用 `CommunicationDeliveryReceipt.from_delivered_message()`。
3. 用当前 owner、plan、epoch、lease、partition generation、决策时刻和 payload digest 构造 expectation，再调用对应 gate。
4. gate 未通过时，不得把 heartbeat/readiness/communication 布尔量或调用方 ACK 写成可执行证据。
5. 增加通信关闭、全丢包、延迟到达和区域分区集成负例；5v5 通信关闭复现必须从原 8/8 可执行变为 8/8 `receipt_missing` 且 `execution_allowed=false`。

通信关闭负例现为 0 个 D4 可执行区域、8 个失败关闭区域，原 P0 已关闭。异步 M-to-N 正例属于上节独立的系统级复跑任务。

## 2026-07-22 跨提交谱系比较计划

- **D4 结论**：独立 planner 的原始 `plan_id` 可以不同。D4 `authority_digest`、`formal_decision_digest` 和 `advisory_id` 因包含或间接包含该计划号而确定性变化，不构成业务差异；原始值在单次运行内仍必须完整保留并通过内容校验。
- **main 比较顺序**：先验证同 seed/场景/配置/时间轴、D3 计划谱系、D4 formal-advice 配对、原始 before/after digest、原始 authority payload digest 和原始 advisory 内容地址；再在只读副本中规范 D3 计划号，并按 D4 原算法重算三类派生身份。禁止按事件号覆盖 `advisory_id`，禁止只保留摘要相等类。
- **强比较字段**：owner/layer/role、region/task/global-track/resource/node/coalition identity、plan version、epoch、lease、ACK、fault fence、正式动作和 recommendation 全部保持原业务语义并逐字段相等。只有经 D3 审计的 plan identity 及其确定性派生摘要可进入规范视图。
- **当前证据**：clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002，各 30 条 D4 正式裁决和建议均通过单运行完整性；30/30 对规范重算结果相同。该结果是跨提交描述性等价证据，不是降级性能、学习收益或真实网络证据。
- **后续集成**：main 的通用比较器应优先读取完整 `RegionResourceSnapshot` authority payload。若制品只含 advisory，只有用 `source_version + protected_committed_resources` 回算并精确匹配原始 authority digest 时才可继续；否则标记不可比较并失败关闭。

## 2026-07-22 计划代际适配复核

- **已确认**：`RegionResourceIsolatedAdoptionVerifier` 的严格后继和评估刷新分支语义正确，无需调整安全门。隔离专项 26/26、D4 全量 508/508 通过。
- **main 代码路径已修正，正式证据待重生**：三类场景的 source 必须是与同帧 formal D4 regional ownership 对齐的当前计划，不是任意 `previous_plan`。applied 要么是 source 的新 ID、严格更高版本后继，要么是同 ID/version 且执行签名、binding、未分配清单、owner、epoch、lease 和创建时间均不变的显式刷新。2026-07-25 main-owned 选择器已跳过故障栅栏帧并要求已采用区域计划，保留种子选择测试 11/11 通过；原 20-seed 物理制品尚未正式重生。
- **被动降级**：中心失效使用 secondary formal owner；中心和二级失效使用逐区域 distributed formal owner。两者的 applied plan 保持 formal epoch/lease，若 authority generation 改变则必须重新生成 snapshot、formal decision 和 lineage。
- **主动风险**：中心仍是 owner。执行变化走严格新计划；仅重新评估且世界继续执行原计划时走 evaluation refresh。刷新不能计为候选采用或动作回报。
- **验收未完成**：中心失效 20-seed 的 20 pair、196 区域记录仍全部被拒绝。main 修正 producer 并由 D6 重新汇总前，不关闭物理采用 P1。

## 0.0A 2026-07-21 PDT / 2026-07-22 UTC 隔离 degraded rollout 合同（D4 已完成，main/D6 producer 待完成）

- D4 已新增独立于生产 runtime ACK 的 `d4-region-resource-isolated-plan-consumption-ack-v1` 和 `d4-region-resource-isolated-adoption-evidence-v1`。main 后续为 control/treatment 克隆世界逐周期生成 receipt；D4 只读核验，不导入 main、D3、D6 或 D7 runtime，也不改变正式 authority。
- lineage 只允许 `center_failed`、`center_and_secondary_failed`、`active_risk`。每个 region/cycle/arm 绑定 scenario/version、seed、配置、初始状态、通信/故障 schedule、D4 snapshot/decision、源 D3 plan 和 candidate gate SHA256。nominal 场景不能伪装成降级证据，既有 nominal 5v5 只保留门控/回退基线意义。
- 候选门保持 `minimum_confidence=0.6`、latency limit `50 ms`，并要求 OOD、finite、external-failure 和 deterministic safety projection 全部通过。候选失败或保守 override 时只能记录 `rule_fallback=true`；不得把 projected recommendation、离线 receipt 或同代 refresh 写成候选采用。
- 新执行计划采用必须同时满足：新 plan ID、严格更高 version、`execution_signature_changed=true`、非 refresh-only、创建/评估时间不早于来源帧、formal owner/node/epoch/lease 完整一致、ACK 时间严格早于 lease、全部 assignment binding 已由隔离世界消费。same-generation 只允许唯一 refresh flag，且 binding、未分配集合、owner、epoch、lease、plan creation 全部不变。
- 缺 receipt、receipt replay、旧 epoch、旧 plan generation、过期/不一致 lease、owner 或 binding 篡改、缺 CoalitionMemberAck、formal fail-closed、网络分区和低置信候选均保持安全边界。输出固定 `production_runtime_ack=false`、`isolated_simulation_only=true`，physical/paired/counterfactual/causal/effectiveness/PPO/assist/authority 全为 false，规则回退保持 true。
- D4 提供 D3 `d3.isolated-plan-consumption-evidence.v1` 的独立严格桥接，校验来源 lineage、计划身份、binding 数量、时间窗、内容哈希和全部非生产权限后，才生成 D4 隔离回执；该桥接不表示 main 已消费计划，也不授予生产 ACK。
- D4 模块验收为隔离专项 **26/26**、全量 **508/508 passed**。样本为确定性单元合同 fixture，不是 AirSim、真实网络或已完成采用的多 seed 物理结果。

### main/D6 后续顺序

1. main 用相同初始世界和外生传感器、通信、故障 schedule 克隆 control/treatment arm；每个 arm 独立消费自身 D3 plan，并在实际状态积分和 D7 command consumption 后生成隔离 receipt。receipt 不得命名为 production runtime ACK。
2. 单独运行 `center_failed`、`center_and_secondary_failed`、`active_risk` 多周期场景；优先构造接近决策边界且可能改变 plan binding 的样本。nominal 5v5 不进入降级效果验收。
3. D6 仅在 lineage、receipt、逐周期状态窗口和 arm 完整性齐备后计算 availability-aware physical outcome 与 paired non-degradation。因果/反事实结论继续单独审计。
4. 正式多 seed evidence 生成后，D4 再按新制品的日期、seed 数、阈值、结果和限制同步 README/PLAN/GAP；当前不得开放 PPO、assist 或 production authority。

## 0.0 2026-07-22 保留 seed 配对干预边界（D6 可用性 sidecar 已形成，物理结果待完成）

- 新增版本化 `d4-region-resource-paired-intervention-spec-v1`。保留 seed 固定为 1000-1019，每个 seed 必须同时具有 `control_rule` 和 `treatment_candidate` 两个隔离 arm。两个 arm 重复绑定相同 scenario/version、配置 SHA、初始状态 SHA、通信 schedule SHA、故障 schedule SHA 和区域快照 lineage SHA；候选 bundle manifest、模型权重、策略版本、置信/超时/OOD 阈值及安全外壳版本也被内容寻址固定。
- 隔离候选加载器只接受 `region_resource_bc_900_20260720/bundle`。冻结身份为 development 模型 `d4-region-bc-900-development-v1`，manifest/权重/训练清单 SHA256 分别为 `dad2adbe...c05c9`、`3da0360b...d5f62` 和 `ff3081c8...30dc6`。加载时要求训练清单存在，并校验数据集 `b06d741b...d36158`、切分 `18a2c600...d7f0`、`maximum_advisor_mode=shadow` 及全部不可准入字段；每次推理前后重新计算三文件指纹，文件变化立即失败关闭。
- control 只执行现有 `RuleRegionResourcePolicy`。treatment 只在离线仿真 arm 内允许候选建议进入现有 `DeterministicResourceProjector`；候选必须经过 owner/plan/version/epoch/lease、fault fence、coalition ACK、邻接、带宽/机动、边容量、备用、已提交资源和总量守恒检查，再由现有 next-cycle consumption gate 复核。旧 generation、过期 lease、缺 ACK、联盟不完整、未知边、bundle/阈值/哈希错误均阻断候选并保持规则回退。
- arm evidence 升级为 v2；对已考虑候选保存 confidence/`minimum_confidence`、OOD、latency/limit、finite 和 confidence/OOD/latency/finite/external-failure 五项 gate。低置信、分布外、超时和非有限输出分别写入 `candidate_low_confidence`、`candidate_ood_rejected`、`candidate_inference_timeout` 和 `candidate_output_nonfinite`；旧 generic reason 仅兼容保留。没有成功生成 raw candidate 时 `candidate_considered=false` 且各候选 gate 为未评估，不伪造低置信或非有限结论。规则 fallback 仍使用原确定性 projector，正式 `RegionResourceAdvisor`、区域 failover decision 和生产准入状态不变。
- `isolated_treatment_safe_adopted` 只表示候选在隔离 treatment arm 中具备下一周期输入资格。它显式不能转换为 `runtime_advisory_applied_ack`，也不改变正式 D4 authority、D3 plan 或 D7 gate。`PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true` 被 specification、arm evidence 和 manifest 三层共同固定。
- manifest 要求 40 个 arm 记录完整，逐 seed 核对两个 arm 的 observed input 和实际 snapshot payload SHA。缺 arm、输入/通信/故障 schedule 不同、跨 arm 快照不同、内容哈希篡改、truth/actor/object/target key 和非有限值全部失败关闭。v1 reader 先验证旧字段集合和旧 manifest content ID，再迁移为诊断 unavailable 的 v2；不回填或改写冻结 v1 JSON。CLI 只做 JSON 严格验证和 canonical migration/round-trip。
- D4 复用 `ShadowPairedEvaluator(minimum_unseen_seeds=20)` 作为 D6 指标计算入口。源 producer manifest 中的 `d6_outcome_sidecar_attached=false` 保留为生成时历史事实；D6 后续已独立生成 profile-bound v2 outcome-availability sidecar，状态为 `pass_offline_assignment_comparison_only`。它只开放同帧离线分配比较，runtime ACK、observed physical outcome、paired effect/non-degradation、counterfactual、causal、formal 20-seed performance 和性能声明仍为 unavailable/false。
- 2026-07-21 模块验收：配对专项 **33/33**，D4 全量 **482/482 passed**。新增回归逐项覆盖 confidence/OOD/latency/finite 单门、四门组合、原始 `0.6/50 ms` 边界、v1 40-arm manifest 迁移，以及 rule fallback、pair input、bundle identity 和 next-cycle safety 不退化。
- 当前权威正式输入 `reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296` 绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS`/manifest SHA256 分别为 `821f1503...72bc` 和 `d6ef23b2...883c`。D6 独立重算确认 20/20 source clean 且 finite、truth 使用数 0，candidate considered 20/20；confidence min/mean/max 为 `0.508892953/0.563426384/0.569492280`，在未下调的 `minimum_confidence=0.6` 下通过 0/20，OOD、latency、finite、failure gate 各通过 20/20，aggregate 0/20，safe adopted 0/20，规则回退 20/20。执行时延 `treatment_candidate_latency_ms` 的 nearest-rank P95 为 `2.241315 ms`；门控汇总 `candidate_gate_summary.candidate_latency_ms` 的线性插值 P95 为 `2.264415 ms`。D6 sidecar 位于 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，文件/内容 SHA256 分别为 `f3852251...1c3b`/`c02a345c...5d2d`。`formal_twenty_seed_performance_completed=false`；nominal 5v5 只证明门控和回退，不证明 candidate validity、paired physical performance 或降级策略效果。

### 后续执行顺序

1. 保持当前 v2 正式 20-seed artifact、历史 v1 artifact、冻结 900-episode 数据、bundle、权重和 manifest 只读；后续重跑必须写入新目录并保留独立 lineage，不能覆盖任一正式记录。
2. 在与训练 seed、保留 seed 1000-1019 均隔离的 calibration split 上定义 confidence 标签，报告 reliability diagram、ECE、Brier 和分桶样本数。优先校准或重训 confidence head；不使用本次保留 seed 选择或下调 `minimum_confidence`。
3. 校准/重训候选仍须在同一 `minimum_confidence=0.6`、OOD、`50 ms`、finite、bundle、authority、projection 和 next-cycle 门下复验；未通过则继续规则回退。
4. 保留已完成的 D6 profile-bound v2 sidecar 绑定和同帧离线分配比较；下一步为相同 arm 补充可认证 runtime ACK、干预后物理状态窗口和 paired effect/non-degradation。counterfactual/causal 另行审计，不能由 D4 的安全采用或规则回退标记推导。
5. 只有完成独立校准、运行时与物理结果证据、同输入审计及单独准入评审后，才决定是否保留 shadow candidate；当前 availability sidecar 本身不能开放 PPO、assist 或 authority。

## 0.1 2026-07-21 区域 reward 口径冻结（模块内合同已完成）

- 新增 `d4-region-resource-outcome-window-v1`、`d4-region-resource-outcome-provenance-v1` 和 `d4-region-resource-reward-evidence-v1`。输入必须先有 `d4-region-resource-runtime-ack-evidence-v2` 正例，再绑定 advisory/model fingerprint、源计划与 applied plan、owner/epoch/lease/fault generation、ACK sequence/time、源与结果 `RegionResourceSnapshot` 的规范 SHA256，以及执行/联盟绑定的窗口首尾 SHA256。
- 固定八项原始成本：高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动。每项必须显式给出 `available|unavailable`；可用项携带 raw value、单位、归一化分母、归一化成本及来源制品 SHA，不可用项携带 reason 且数值为空。合同禁止从相邻快照、command-only 或缺失记录补零。
- v1 归一化为 `c_i=min(raw_i/denominator_i,1)`，观测成本为 `sum(w_i*c_i)/sum(w_i)`，时间窗口奖励为其负值。只有 `new_execution_plan_applied` 且八项全部可用时才输出非因果的时间窗口归因奖励；`evaluation_refresh_applied` 可输出观测成本，但执行签名未变化，因此奖励保持不可用。
- 适配器按 episode/region 记录已接受窗口。重复窗口、窗口重叠、ACK 缺失、旧 epoch/fault generation、窗口到达租约边界、区域清单变化、owner/plan/binding/coalition 改变、来源哈希错误、在线 truth key 和 schema/字段缺失均失败关闭。成功输出仍固定 `CoalitionMemberAck=false`、physical outcome=false、causal=false、paired shadow=false、on-policy=false、PPO/assist/authority=false、rule fallback=true。
- 2026-07-21 验收为新增专项 19/19、ACK 与 reward 专项 52/52、D4 全量 449/449；新增/修改 Python 已通过 `py_compile`。这只关闭 reward 定义和模块内消费合同的下一步，不关闭 main/D6 区域结果 producer、正式 episode 回填、保留 seed 1000-1019、同 seed paired shadow、因果评估或 on-policy 采样。

### 后续执行顺序

1. main/D6 按该 schema 从真实 scalable3d episode 生成 truth-free 区域时序、窗口边界和带外制品 SHA；D4 只读消费，不从 D6 的目标级 truth diagnostic 推导区域 reward。
2. 对新执行计划和同代评估刷新分别运行多 seed，验证不重叠窗口、租约覆盖、绑定稳定和分项 availability。正式 900 episode 保持冻结，不做追溯伪标签。
3. 在外部保留 seed 上完成规则与候选的同 seed paired shadow，并单独评估 counterfactual/causal 口径。完成前不得把时间窗口观测奖励写入 PPO loader，不启动 PPO，不评审 assist 或 authority。

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
- 2026-07-21 新增 `d4-region-resource-full-sample-admission-audit-v1`。它只读扫描正式 900 episode/1798 frame/sample/14384 action 和 clean supplemental 100 episode/300 frame/sample/1200 action，核对 manifest 与逐 episode SHA256、来源/schema、规范 60/20/20 只读切分、数值有限性、动作覆盖、配额和 transfer 合同、owner/plan/epoch/lease/version、保留 seed、dirty 状态与在线真值隔离。正式规范切分为 540/180/180 episode、1079/359/360 sample、8632/2872/2880 action；补充课程为 60/20/20 episode、180/60/60 sample、720/240/240 action。两类全样本均为 complete，违规数为 0。
- 证据解释固定为：`target.kind=rule` 是规则教师标签；`recommendation.projected=true` 是后投影建议通过确定性合同，不是 runtime applied ACK。补充课程只能证明结构、有限值、动作覆盖和安全约束。显式投影前 action mask、被拒旧 generation 样本、真实 `CoalitionMemberAck`、outcome、可归因 reward、同 seed paired shadow 和 D6 外部带外 SHA256 准入仍为 unavailable/pending。全样本通过不改变 `ppo_allowed=false`、`assist_allowed=false`、`online_authority_allowed=false`。
- 2026-07-21 升级为 `d4-region-resource-runtime-ack-evidence-v2`。`RegionResourceRuntimeAckParser` 用 `adoption_kind` 区分 `new_execution_plan_applied` 与显式同代 `evaluation_refresh_applied`。前者继续要求新 plan ID/version、完整 owner/epoch/lease、source sequence/hash 和全部 binding；后者只校验已存在执行身份的同代评估事实，不计为 A2 动作采用。2026-07-27 起，无操作区域建议必须由 D3 返回 `no_successor`，不得进入 refresh ACK；只有可辨识干预及其严格 successor 才进入 A2 采用链。成功证据仍要求 `consumable=true`、D3 hint applied 和 main accepted，并对 `(advisory_id, advisory_version)` 防重放。
- 2026-07-21 的 5v5 同代刷新为历史 parser 夹具。2026-07-27 已替换为无操作
  `no_successor`、真实干预 successor 和四项篡改负例，当前集成专项 6/6、D4 全量
  658/658。历史阶段数字保留在实验报告，但不再代表当前 A2 采用语义。
- 已形成一条可辨识干预的质点 runtime 正例，但冻结 900 episode 仍没有该证据。后续
  main/D6 应持久化 v2 evidence 并按 `adoption_kind` 分开统计。评估刷新只属于传输层同代
  事实，不能充当 A2 动作采用、新执行计划、`CoalitionMemberAck`、outcome、reward、
  paired shadow、PPO、assist 或 authority 证据。
- 2026-07-20 正式数据与开发训练：只读审计 900 episode/1798 frame，逐 episode SHA、dataset/source/schema、70/15/15 seed 原子 split 和 1000-1019 外部保留 seed 隔离均通过。2026-07-21 按固定 seed 复跑行为克隆，完成 66 epoch，最佳 epoch 54，内部测试 loss `0.071545`、CPU 推理 P95 `0.7774 ms`、权重 SHA256 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，与首次权重哈希一致。正式标签的 14384 个区域动作中 nonzero quota、transfer、hold、request_replan 均为 0；D6 审计还确认 898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle 机器准入固定 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false`、`development/shadow-only`。行为克隆管线可用，但低损失不能作为完整动作策略能力，PPO 和 assist 均不可用。权重保存在 ignored `outputs/`，tracked 结果不含模型文件。
- 2026-07-21 已完成独立动作覆盖补充课程 producer，并由 main 在 detached clean worktree commit `9445ed6` 上重生证据。课程按输入区域数和资源总数运行，每个共享训练 seed 生成 hold、request-replan、transfer 三帧，并在新输出目录中形成 dataset-v1 与只读 canonical view；正式 900 episode 目录不写入。clean 课程为 100 seed/300 frame，动作计数为 hold 100、request-replan 200、非零 quota 200、transfer 100，三个 60/20/20 桶均有正类，硬约束、真值泄漏、保留 seed 泄漏和 dirty episode 均为 0。行为克隆只读 view 已可用；reward/outcome 统一 unavailable，PPO 与 assist 不开放。首次 dirty 产物只保留为开发历史；下一步冻结与正式数据的采样比例并运行外部 1000-1019 paired shadow。

- `regional_failover.py` 新增 `RegionalScenarioMetadata`、`RegionDefinition`、`RegionalTaskEvidence`、`MobileReconSecondary`、`RegionalFallbackMember`、`RegionOwnershipMetadata` 和 `RegionalFailoverCoordinator`，不导入 main-owned `scalable_3d_simulation`，通过 mapping/`to_dict()` 只读适配 `scalable3d-scenario-v1`。
- 每个区域最多一个 active authority。中心 health 未进入 `failed` 时始终保留中心 owner；D1/D2/D3/D5 风险只改变 `continue_center|request_secondary_assist|request_center_replan|hold_for_review`，不把主动降级变成所有权转移。
- 中心 `failed` 后，逐区域只从显式 coverage 且 strict readiness 完整的 `mobile_high_recon` 中选择二级协调者；排序为 takeover priority、coverage ratio、lease epoch、node id。二级节点保持 `coordinator_only`，不作为拦截成员。
- 没有有效二级节点时才执行受约束 bid fallback：按 region、availability、communication、operator hold、跨区域 capacity、capability demand 和 D5 support/hold/ambiguity 形成确定性候选成员集；一个成员可同时覆盖多项 capability。该实现是可审计保底 heuristic，不是完整 CBBA 消息共识、CCBBA、reserve 激活或动态联盟重构。
- authority 切换必须同时提升 `epoch` 和 `plan_version`；租约严格满足 `timestamp < expiry`，并收缩到 authority、D3 task 与二级 lease 的最早 expiry。中心、二级和 distributed 三层的 `k>1` 任务均复用 `CoalitionCommitCoordinator`，只有 required-member ACK 全集对同一 target/coalition/plan/version/epoch 有效时才原子 `committed`；缺 ACK、旧 ACK/authority generation、过期 lease 和任一层级分区全部 fail closed。
- 2026-07-20 区域合同阶段新增 23 项确定性单元测试：5/20/50/100/200 个 region/task/resource 元数据与中心 ownership，声明 resource/recon 数量上限，D1/D2 主动证据、D3/D5 硬门控、中心失效、二级失效、双区域 coverage、中心/二级/distributed 完整与缺失 ACK、旧 ACK epoch、全层网络分区、旧 authority epoch/plan version、最早 task/authority lease、旧 secondary lease epoch、D5 member hold、单成员多能力与跨区域 capacity。当时 D4 全量为 303/303，当前已由 **482/482 passed** 覆盖。
- 验证边界：23 项合同用例本身无随机 seed、AirSim episode、真实 RF/mesh/socket、带宽/时钟漂移或物理命中证据。main 后续已完成质点模块栈接线，但这不把合同单元测试升级为 AirSim/真实网络证据；根级系统文档仍由 main 同步。

### 0.1 2026-07-15 P0 公开二级接管入口统一（已完成）

- 抽取 `SecondaryReadinessEvidence`/`assess_secondary_readiness()`，统一 coordinator election、episode communication 和 secondary coalition proposal；旧式裸 `takeover_ready=true` 不再授权接管。
- 二级 owner 必须证明显式 current time、正 lease epoch、严格 `current_time < lease_expiry`、fresh heartbeat/cue/communication、gimbal=true、coverage >= 0.65、network full-view >= 0.80，以及至少 3 次/0.2 s 的 sustained readiness。缺失、陈旧、等于 expiry 或低于门限均阻断二级 proposal/execution。
- `FailoverCoordinator.plan_degraded()` 只对 secondary candidate 应用该门；interceptor/cluster-representative peer 的 distributed election 保持独立，不要求二级视觉 evidence。动态 N/M、plan/coalition version、epoch/lease、ACK、partition/recovery 和 upstream `global_track_id` 合同不变。
- 278/278 历史回归未覆盖 `build_d7_secondary_handoff()` 和 `build_secondary_takeover_plan_metadata()` 对 sustained/source/lease epoch 的 `None`，此前“所有公开入口已闭锁”的说法撤回。两个 helper 现要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格未过期；同一已激活 plan 的维持路径不豁免。
- 当日验收结果：D4 全量 280/280 passed，两个 helper 的逐字段 `None`、完整正例、same-plan 维持和 distributed bypass 均通过；`build_coalition_commit_d6_metadata()` 缺 current time 时仍 lease invalid/atomic false。候选门诊断阶段全量为 482/482，2026-07-25 当前全量为 569/569；P0 判定不变。

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

D4 所属的 P1 合同层已闭合。2026-07-11 ComputerVision 验证中，总体验收为 8/10；二级协调者 `Secondary_Recon_1` 与完全分布式 `INT-02` peer 均以 required-member ACK 3/3 进入 `executing`，分别输出 `degrade_to_secondary` 和 `degrade_to_distributed`；缺 ACK 场景在确认窗口显式截止时以 2/3 ACK 进入 `aborted`，三个 T001 成员均 `hold_for_review`，确认 fail-closed。2026-07-25 后，未到显式截止的普通快照保持 `collecting_acks`。当前不再把 secondary/distributed 正例写成 unsupported 或未闭合。

状态必须按层级解释：

| 层级 | 当前状态 | 不得外推为 |
|---|---|---|
| P0 secondary evidence/lease fail-closed | **2026-07-15 已关闭**：280/280 回归覆盖 coordinator/episode/coalition/D6 及两个公开 plan helper；readiness/source/epoch/time 任一缺失均阻断，历史 278/278 过度声明已纠正 | 新 AirSim 网络证据或 P1 自主联盟重构 |
| scalable3d 区域 authority 与质点接线 | **已实现并接线到 main 质点模块栈**：模块合同覆盖 5/20/50/100/200 metadata；main 集成已覆盖单二级、多二级 owner 和连续失效后的 distributed D3 plan，D7 按 owner/epoch/lease/commit/fault fence 执行 | AirSim、真实网络、长时 200v200 多 seed、完整 CCBBA 或物理任务闭环 |
| 区域资源学习建议与消费合同 | **行为克隆开发模型已训练，仍为 shadow-only**：规则、确定性投影、版本化限时 advisory、一次性消费门、共享变长图 actor-critic、BC/PPO 接口、bundle/SHA、OOD/timeout 回退和 paired evaluator 均可运行；正式 900 episode 审计和 BC 已完成 | 14384 个标签动作没有 quota/transfer/hold/replan 正样本，D6 reward/causal/counterfactual 可用数均为 0，内部 test 仅 15 seed，外部 20 seed 未评估；bundle 明确禁止策略能力声明，不得 PPO/assist，也不具有裁决/assignment 权限 |
| D3/D4/D5 共享 seed 切分的 D4 消费端 | **已实现 development/data-governance 能力**：严格消费 source-external registry，正式 900 episode 已只读映射为 60/20/20 seed；BC 可显式选用 canonical view，默认 70/15/15 不变 | 不代表 D3/D5 消费端已闭合，不代表联合模型已训练，也不改变 PPO/assist 准入 |
| P1 合同层 | **已完成**：secondary ACK 3/3 `executing`、peer ACK 3/3 `executing`、显式截止后缺 ACK 2/3 `aborted`/`hold_for_review` 已有真实 ComputerVision 正负例 | 自主成员形成、完整重构或物理拦截 |
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

2026-07-11 D4 本地 P1 原子联盟合同已实现：冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 直接扩展现有 `CoalitionSafetyEvidence`。协调器校验双版本、epoch、成员身份、ACK 有效期、lease 和 digest；完整 ACK 后才能进入 committed/executing。2026-07-25 异步修复后，普通快照缺 ACK 保持 `collecting_acks` 和零授权；显式终结、租约到期、网络分区或 digest 冲突才进入 aborted/reconfiguring。中心正常仍使用现有路径；中心失效后，只有 secondary `takeover_ready` 或完全无中心 committed 联盟才设置 `atomic_coalition_formed=true`，否则保持 fail closed。event/D6 metadata 已输出 commit 状态、成员、epoch、coordinator 和 lease；恢复只输出双轨审计，不立即夺权。该合同在 2026-07-12 无行为变化；当时 D4 模块测试 148 项通过，候选门诊断阶段为 482/482，2026-07-25 当前全量为 569/569。

2026-07-11 center replan coalition convergence 已补齐：D4 读取 main 已传入的 D5 `CoalitionVisualSummary`，校验 current track/plan/coalition scope、完整 primary lock 集合、无 conflict，以及 commit-required 时 committed/executing 和 required ACK 完整。只有中心 alive 且当前决策无 friend/duplicate/wrong-binding/version/commit/health 硬冲突时，matching pending request 才可输出 `continue_center` 和 `resolution_hint=acknowledged_no_change`；同一 summary 对所有 current primary 给出一致 action。D4 不修改 main adapter；最小接口字段记录在 README。该能力本轮无行为变化；当时模块测试为 148 项通过，候选门诊断阶段为 482/482，2026-07-25 当前全量为 569/569。

历史基线（2026-07-11、最终 P1 验证前）：`blocks_cv_m5_n2_liveness_batch_20260711` 的 seeds 7/17/27 均为 6 次重规划请求、6 次 `acknowledged_no_change`、0 次 applied、0 次 expired，需求满足率均为 1.0，错误重复锁均为 0，说明当时中心重规划请求 lifecycle 和合法多成员锁审计已稳定收敛。T002 的视觉共识帧为 4/5/4，D7 每个 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。该批次已被最新 10-seed/故障注入验收补充，只证明 ComputerVision 状态链，不代表 SimpleFlight 动力学控制、协同到达或物理拦截完成。

历史基线（2026-07-11 早期 smoke）：200 m/2 二级节点、50 m/2 二级节点和 200 m/5 二级节点三组 truth-isolated 场景中，预期二级接管正例因联合全覆盖率为 0.0 而保守回落到 distributed。当时结果未关闭 P1，但已被后续 ACK/commit 正负例验证取代为当前状态；它仍用于说明不得以平均覆盖替代同帧联合覆盖，也不得放宽 readiness 门限。

下一轮按以下顺序实施和验收：

1. 先保持 P0 回归，冻结现有 heartbeat、readiness、source/lease/version、重规划 lifecycle 和 `k>1` fail-closed 合同。
2. 保持已完成的 P1 联盟协商合同回归：`CoalitionMemberAck` 和 `CoalitionCommitState` 已覆盖 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted`，并携带 target/coalition/plan version、epoch、lease、required/acked members、能力证据时间和失败原因。
3. 保持已通过的二级 `executing` 3/3、peer `executing` 3/3 和显式截止后缺 ACK `aborted` 2/3 正负例回归，不再重复列为待闭合能力。
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
| M-to-N 原子联盟安全门控 | schema v2 coalition/member/双版本校验；member ACK、commit lifecycle、lease/epoch、digest 和 fail-closed 已实现。验证中二级与 peer 均 ACK 3/3 `executing`，显式截止后缺 ACK 为 2/3 `aborted`；截止前无有效 commit 时保持 `collecting_acks` 和 replan/hold。合法授权多锁不算 duplicate；single-winner CBBA 不承担 `k>1` 成员形成 | `coalition_safety.py`、`adapter.py`、`coordinator.py`、`tests/test_coalition_safety.py`、`tests/test_coalition_commit.py` |
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
| 区域资源建议消费与学习效果 | 后投影 advisory、一次性门、规则、dataset-v1、bundle provenance 和 fail-closed 回退已实现；正式 900 episode 已按 70/15/15 seed 审计并完成固定 seed BC 开发模型；clean 补充课程已提供四类动作正样本和可用的 canonical BC 只读 view | 正式 14384 个区域动作仍没有 quota/transfer/hold/replan 正样本；补充课程没有 outcome/reward；外部 20 seed、paired 收益和 main/D3 advisory 消费仍未完成 | 冻结正式数据与课程的采样比例，D6 冻结 reward/causal 合同；随后重训并在 1000-1019 上做 paired shadow。当前 bundle 固化 `action_diversity_sufficient=false` 与 `strategy_capability_claim_allowed=false`，不得用 clean 数据准入或低损失申请 PPO/assist |

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

0. **M 对 N 联盟合同保持回归**：P1 合同层已闭合；固定回归二级 ACK 3/3 `executing`、peer ACK 3/3 `executing` 和显式截止后缺 ACK 2/3 `aborted`。继续研究 `simultaneous|sequential|mixed`、reserve、成员退出缩编/补位/整盟重组，但不得把这些开放项误写成 commit 正例未闭合。
1. D4 模块内的逐决策 stable/not-registered source/presence、连续 readiness 窗口、pending/active transition、source/lease strictness 和 heartbeat/link/cue/gimbal/能力回落负例已完成；后续保持这些合同回归，不再作为代码缺口。
2. 保持已通过的 secondary/peer executing 与显式截止后缺 ACK aborted 场景，继续统计 activation delay、回落原因和恢复窗口，不降低门限。
3. episode clock 六类、10-seed、60-case 安全矩阵已完成；下一步把 heartbeat、lease、video/cue freshness 和 gimbal 摘要接到可配置带宽、时钟漂移、排队抖动、乱序和重传模型，继续记录 plan activation delay 与恢复双轨窗口。D4 只消费链路摘要，不负责修正 D5 几何注册。
4. 分区注入已证明 10/10 恢复时新 generation 全量 re-ACK，且重复 owner/split-brain prevention failure 为 0；下一步针对真实 secondary-interceptor 断链、peer 图分裂和不同节点时钟偏差，补齐 peer/digest 差异、恢复 merge audit 和长时恢复分布。分区侧不得绕过 plan version、lease 或 D5 友方/身份门控。
5. 当前 episode-time 正常场景的 false degradation 为 0；下一步用同 seed 的带宽受限、时钟漂移和真实网络时序成对场景统计 false/missed degradation、动作混淆矩阵和 dwell/release 抖动。阈值调整必须基于成对证据。
6. 在完全无中心 case 中持续把 D5 distributed visual evidence 合流到 `TrackSummary.visual_evidence`，并用多 seed 报告确认 CBBA completion/conflict/cost gap/round/message 指标。
7. main/D3 继续保存同场景中心化 cost matrix/current plan，D6 聚合 D4 `CBBACostGapBenchmark` 多 seed 指标；轻量 CBBA 仍为默认保底。
8. 复用已完成的 M5N2 20-case 几何/seeds 运行 secondary/distributed paired 故障场景，并补充 collision object/source lineage；不得以 `collision_stop` 或未进入 5 m 直接触发主动降级。
9. scalable3d episode bus 的单二级、多二级和 distributed D3 plan 接线已完成；下一步保持 owner/epoch/lease/commit/fault fence 回归，并补长时 200v200、多 seed stage timing、分区恢复、transition/churn 和 D6 汇总。D4 不越权修改 main-owned 文件。
10. main 后续如消费区域资源建议，只接 `d4-region-resource-advisory-v1`，每个 D3 planning boundary 用 current snapshot/formal verdict 重验并持久化 consumed advisory ID；不得直接消费 raw/non-projected recommendation。该工作属于 main/D3-owned 集成，本轮 D4 不越界修改。
11. 正式 writer 与 dataset-v1 已形成 900 episode 数据，clean 补充课程已提供规则教师动作覆盖；两类数据的 D4 全样本只读审计已经完成。D6 下一步必须按 tracked JSON 的显式路径和外部计算的 JSON SHA256 独立复核，不得把 `target.kind=rule` 当 truth 泄漏，也不得把 recommendation/projected 当 runtime applied ACK。此后仍需版本化真实 ACK/outcome/reward/causal/counterfactual availability 和同 seed paired shadow；缺失时继续 unavailable。满足前 bundle 保持 development/shadow-only，PPO/assist/authority 不开放，也不改变正式 D4/D3/D7 裁决。
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
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_full_sample_audit.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_learning.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_cli.py
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
