# D4 分布式协同与降级接管综述及子方案

## 2026-07-28 当前谱系影子运行评审

D4 已把候选可信加载、运行分布兼容和正式采用拆成三层证据。只读适配器固定候选身份并记录
每帧原始模型动作、确定性投影和逐特征 OOD；它不发布计划或授予权限。main 的 5v5/2 区域
和 200v200/8 区域共 5 帧全部 OOD，模型执行为 0。因此当前候选不能进入正式 20-seed。

候选原始字节已从被忽略的 `outputs/` 逐字节登记到受控 `model_registry`。clean clone
可以直接加载固定候选并复核权限全闭；该变化只关闭来源复现缺口，不关闭运行分布兼容和
正式采用缺口。

下一候选应复用运行数据与动作课程的复合视图。两个来源的 0-99 seed 必须统一原子分割，
1000-1019 完全排除。运行数据补足 8 区域运行特征，课程补足安全非零动作。2 区域边距离
仍未覆盖，继续规则回退。本轮不重训、不改 OOD 门；新权重只能在 D4 代码提交后的独立
clean checkout 生成。专项 **17/17**、D4 全量 **706/706** 通过。

## 2026-07-28 当前谱系候选复核

D4 已将当前谱系 A2 候选从历史 calibration-only 产物中分离。新构建器只读取 train 和
validation，test episode payload、旧 calibration 与 seed 1000-1019 均不进入训练、选模
或诊断。模型包保持 development/shadow，外层 manifest 新增当前源码、数据、split、配置、
权重和训练摘要的闭合绑定。

纯 Python 临时 clean Git fixture 已证明正式 CLI 能生成可加载候选。八项专项覆盖正向
构建以及 dirty、lineage mismatch、split overlap、permission escalation、artifact
tampering 和 nonfinite output。D4 全量为 **697/697 passed**。

main 提交后，D4 已从 clean commit `b0d498d9...` 生成并 review-only 复核当前谱系实物。
manifest 文件、权重、数据集、split 和 source identity 分别为 `7cc10ad7...de64`、
`fd1b9c4c...0047`、`7e17aba7...2d7f0`、`b413fa81...0c16` 和
`b81780ce...dfdf`。固定门限开发诊断得到 train 168/180、validation 54/60 个安全非零
实际模型动作；其余样本与基线相同，资源不可行和门控回退为 0。

当前谱系实物和开发态非零动作两个子项已关闭。后续先冻结该身份，再安排至少 20 个正式未见
seed。正式试验不得使用历史 calibration 或保留 seed 调参，也不得用 development rule
adapter 代表模型动作。严格后继计划、ACK、物理窗口、same-key R0 和 D6 非退化未闭合前，
全部学习与运行权限保持 false。

## 2026-07-27 A2 实际模型诊断评审

D4 已把“受控适配器可产生非零动作”和“实际模型可产生非零动作”拆为两条证据。新路径直接
加载 development 模型，只使用候选清单中的独立 calibration seed，并逐动作解释低置信、
权威错绑、动作掩码、资源不可行、基线同动作和策略输出退化。诊断不创建后继计划、ACK、
物理窗口或收益记录。

实际候选在 20 seed/420 sample 上固定门通过 420/420，得到 76 个安全非零实际模型动作和
344 个资源不可行无操作。原始可执行动作签名 88，说明模型没有整批塌缩。无操作主要发生在
资源已全部承诺的区域：Sigmoid 备用比例严格为正，整数化后请求至少 1 个备用资源，安全
投影只能压回基线。低置信、分布外、owner/lease/epoch、动作掩码和非有限输出均为 0。

候选 manifest SHA-256、模型 manifest/权重、数据集与逐 seed 分母已经绑定；两次重跑的
76/344 分类、样本身份摘要和分类摘要一致。动作分类使用固定功能性时延覆盖，因此本批不提供
时延性能证据。候选实现谱系已落后于当前代码，历史非零观察与当前谱系开发证据已分开，后者
为 false。正式 P1 仍要求当前谱系候选、
至少 20 个未见 seed、严格后继计划、实际 owner/coalition ACK、物理窗口、独立 R0 和 D6
非退化审计。所有权限继续为 false。专项 10/10，D4 全量 **689/689 passed**，未运行 AirSim。

## 2026-07-27 提交就绪评审

D4 当前未提交实现已完成模块级复核。成员确认和联盟状态采用严格布尔、整数和有限时间；
通信回执/期望采用字段全集解析并拒绝在线真值字段；安全采用结果不能由字符串可用性或
不一致 preparation 构造。中心、二级和完全分布式三层均验证了“证据可用但权限不随之开放”。

开发适配器仍是显式开发探针，正式 A2/R0 收益来源直接拒绝其策略身份。全量结果为
**679/679 passed**。建议 main 将当前 D4 代码、测试和同步文档作为独立提交。真实 episode
ACK/物理窗口、同键 R0、AirSim 多 seed 和 admitted 策略收益继续列为 P1。

## 2026-07-27 A2 开发态候选评审

原开发批次 20/20 为无操作。main 随后用固定最小区域 hold+request helper 做内存探针，
15/20 形成 safe/auditable 链。其余五个 seed 的固定区域存在 committed binding，D3 按
`held_assignment_infeasible` 拒绝。这不是 D3 缺陷，不能通过降低 held-assignment 门解决。

D4 新适配器把 request-replan-only 作为首选。它按 snapshot 选择需要重规划且权威有效的
区域，不同时输出 hold。没有重规划请求时，才尝试最小 transfer；hold 只用于没有
committed resource 的区域。所有候选仍经过原投影器和正式 D4 decision。

本次复核修正了候选提前返回条件。原实现直接比较未投影 `reserve_ratio`，在 committed
resource 压缩可行备用量时会把“投影前看似变化、投影后回到基线”的候选误判为已有干预。
现在先使用共享确定性投影器构造可消费 advisory，再按安全采用链的干预证据判定。若
request-replan、transfer 或 hold 中任一级投影后仍为无操作，适配器继续尝试下一级。

main 复跑还暴露了 formal decision 的 committed member 只在第二次投影生效。适配器现在
显式接收 current formal decision，标准 advisor 只对声明该能力的策略传入。对于资源全部
受 committed + reserve 保护、规则没有任何动作的开发场景，另提供默认关闭的强制重规划
请求。它不 hold 已承诺任务，也不转移资源。

适配器只解决开发可测性。它包装原 learned candidate，但规则派生动作使用固定 development
策略名和 reason 标识，不能归因于模型。它没有 admitted manifest，advisor 请求 assist 时
仍保持 shadow；正式收益审计拒绝该策略身份。

seed 1000、1002、1007、1009、1013 的 committed-region 回归均通过，输出一个
request-replan、零 hold、零 transfer，并停在 `awaiting_d3_plan`。新增回归覆盖投影前
备用比例假变化、formal-only committed member 和显式强制 request。安全采用专项 68/68、
D4 全量 674/674 passed。

指定 seed 1 full episode 已用真实适配器和 development-only admitted transport 夹具运行
1 次。A2 stage 为 `physical_window_available`，可辨识、安全采用和物理窗口均为 true，
权限与收益为 false。该结果证明开发链可达。标准 advisor 仍保持 shadow；main 还需固化
formal-aware 调用并完成 20-seed 重跑，实际模型准入与收益仍未成立。

## 2026-07-27 A2 无操作归因评审

本次审计确认原安全采用口径缺少“建议实际改变了什么”的独立证据。候选被确定性投影和运行
桥消费，只能证明链路可达。同期 D3 发布更高版本计划，也不能自动说明该计划采用了候选动作。

D4 已新增投影干预证据。它比较区域资源配额、跨区域转移、整数备用资源、保持和请求重规划。
资源总量守恒不影响真实转移识别；侦察优先级因尚未进入 D3 可执行提示面，暂不计为干预。
无操作建议在绑定后继计划前失败关闭，普通重规划不能附着到该记录。D6 收益输入还必须具有
非空干预字段和干预内容摘要。

main/D6 已于 2026-07-27 完成 20-seed 开发批次的正确重算：投影/消费 20/20，可辨识干预
0/20，实际 A2 动作采用 0/20，收益审计 0/20。20 个拒绝原因均为
`identifiable_regional_intervention_missing`；批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。原 18/20 是普通
D3 计划升版造成的错误归因，已被本次结果取代。该批仍可保留为链路探针，不提供策略效果
结论。

安全采用专项 **52/52 passed**。原运行时集成夹具已改为分别验证无操作
`no_successor` 和真实干预 successor，专项 **6/6 passed**，D4 全量 **658/658 passed**。
计划代际、租约、联盟、硬约束和权限门均未放宽。本批制品和总报告口径修正已经完成；实际
A2 收益仍需非空干预、独立同键 R0 和正式未见 seed。

## 2026-07-27 A2 同键规则对照评审

D4 已补齐安全采用之后、D6 收益计算之前的只读配对合同。候选窗口必须引用当前
`RegionResourceSafeAdoptionEvidence` 的内容摘要，并与建议、策略、D3 后继计划、租约和
物理窗口逐项一致。规则 R0 窗口使用 `d4-region-resource-rule/v1`，不允许引用候选建议或
安全采用记录。

两臂共享 comparison key、场景版本、规模、seed、逻辑窗口和
`paired_exogenous_config_sha256`。execution arm、episode 事件日志 ID/hash、物理窗口
ID/hash 必须相互独立。该设计允许 main 在两个 reset-separated episode 或两个进程中运行
候选和规则，再从持久化 JSON 离线组装；不允许复制一份日志冒充 R0。

合同只输出 D6 是否可读取该配对输入。D4 不读取结果指标，不形成非退化结论，也不授予
assist、模型晋级、分配、接管或控制权限。批量合同额外拒绝重复 comparison key 和重复 R0
日志、窗口或执行臂。

2026-07-27 安全采用专项 **50/50 passed**，D4 全量 **655/655 passed**。验证为纯 Python
合同 fixture，没有新增 AirSim episode、正式随机种子或收益数据。D4 模块软件缺口关闭；
main 的独立双臂 episode 生产和 D6 的至少 20 个未见 seed 收益审计仍是跨模块 P1。

## 2026-07-27 A2 确认收据后续引用评审

本次修复限定在通信事实的缓存语义。一个实际送达且已经验证的 owner 或 coalition ACK 可在
同一计划和权威绑定下支撑更晚的物理窗口评估。评估时刻不属于 ACK 的不可变身份，但每次
引用仍必须发生在消息到达后和租约到期前，并且不得回退到已处理时间之前。

绑定摘要继续包含 evidence kind、source/destination、authority、message ID、plan、
epoch、lease、partition generation 和 payload SHA-256。任一字段变化仍按跨证据复用拒绝；
同 receipt ID 内容变化按冲突重放拒绝。该修改没有减少 owner ACK、联盟全体 ACK、原子提交
或物理窗口要求，也没有授予 authority。

2026-07-27 的模块正例覆盖 `t=2.05 s` 先确认、`t=2.30 s` 再形成物理窗口；专项
**99/99 passed**，D4 全量 **637/637 passed**。现阶段结论只关闭 D4 收据后续引用的软件
缺口。main 的真实动态 episode、非 hold 控制、物理状态变化和 D6 same-key R0 仍需单独
验证。

## 2026-07-27 A2 严格确认桥评审

D4 已完成 main runtime 所需的公共 owner/coalition 确认合同。运行时 ACK parser 现保留
`runtime.assignment_plan_ack` payload SHA-256 和 envelope sequence；owner ACK 同时绑定
advisory、D3 successor plan、runtime assignment ACK、owner/layer、epoch、lease、
partition generation 和确认时间。实际交付通过
`RegionResourceOwnerAckDelivery.from_delivered_message()` 或
`RegionResourceCoalitionAckDelivery.from_delivered_message()` 解析并生成内容寻址回执，
main 不复制 D4 散列算法。

公共 validator 分别为 `validate_region_resource_owner_ack_delivery()` 和
`validate_region_resource_coalition_ack_delivery()`。联盟 payload 继续严格嵌套现有
`CoalitionMemberAck`，未扩展虚构业务字段。验证结果只表达通信和交叉绑定是否有效，固定
不能授予 authority。

安全采纳顺序固定为：确定性投影、D3 严格后继计划、main runtime assignment ACK、实际送达
owner ACK、必要成员 ACK 与原子提交、truth-free 物理窗口、D6 same-key R0。规则回退不计
learned adoption；缺物理窗口、R0 或任何 ACK 时保持 unavailable。

2026-07-27 四文件联合回归 **130/130 passed**，D4 全量 **626/626 passed**。测试覆盖
payload 严格往返解析、内容寻址回执、runtime ACK 摘要/序号绑定、嵌套联盟确认及篡改负例。
这是模块 fixture，不是 AirSim 或真实网络证据。剩余 P1 属于 main/D6：实际 ACK callback
与网络路由、delivery sidecar、采用后物理窗口、同键 R0 和正式多随机种子审计。当前正式
learned adoption 仍为 0，A2 收益不可用。

## 2026-07-26 A2 安全采用生产合同评审

本轮没有改写既有 A2 最终证据装配器。D4 在其上游增加两阶段安全采用合同，用于区分“候选
通过确定性投影”和“候选已由后继计划实际执行”。第一阶段只接收真实学习候选，冻结 0.60
置信门，并复用现有资源投影和正式权威检查。第二阶段要求 D3 严格后继计划、生产运行时确认、
二级或对等所有者的实际投递确认、必要联盟的全成员原子提交，以及租约内物理状态窗口。

合同新增 `d4.regional_plan_owner_ack.v1` 因果通信类型。所有者确认、联盟成员确认均必须由
`CommunicationDeliveryReceipt.from_delivered_message()` 产生内容寻址回执。后继计划的
载荷摘要和总线序号同时进入运行时确认、所有者确认和联盟成员确认；物理窗口再绑定建议版本、
运行时确认摘要、所有者回执和联盟提交摘要。相同计划号或消息号不能替代载荷一致性。

中心正常时，二级和对等 owner 被拒绝。中心失效时，具有有效二级节点的区域必须优先使用二级
owner；二级不可用才允许 peer。主动降级仍要求正式 D4 裁决和显式证据，证据不足时失败关闭。
网络分区、旧时期或版本、过期租约、容量和邻接违规、缺任一确认或物理窗均不能形成 available
记录。在线输入拒绝 truth、outcome 和 reward 字段，收益比较只交给 D6 带外完成。

2026-07-26 模块专项 27/27、通信与 A2 联合 100/100、D4 全量 621/621 通过。验证对象是模块
DTO、校验器和确定性 fixture。本轮没有运行 AirSim、正式 seed 1000-1019 或真实通信，正例
fixture 不计入 20 个实际采用。现有 main 记录仍明确未考虑候选并执行规则回退。

main 后续需按权威域路由真实候选，保存 D3 计划载荷和总线序号，投递所有者与联盟确认，并从
实际状态积分生成物理窗口。D3 需提供严格后继计划引用；D6 需提供同键规则基线、配对非退化和
最终 A2 收益审计。在这些接线和正式证据形成前，候选继续保持 development/shadow，
assist、PPO、默认模型和运行 authority 不开放。

## 2026-07-26 A2 evidence assembler 评审

D4 已完成模块专用 `d4-region-resource-a2-evidence-bundle-v1` 装配器、严格 loader 和
CLI。它把不可变 development bundle、当前实现摘要、D6 外审、20 个未见 seed 正式 scope、
实际安全采用、D3 严格后继计划、runtime ACK、干预后物理窗口、唯一 same-key R0、paired
non-degradation、硬约束和联盟完整性绑定为同一内容身份。任何缺项、摘要或候选指纹不一致、
旧 epoch/lease、权限误开、额外清单项或输出覆盖均失败关闭。

权限边界没有扩大。新外层包最多表达 `a2_assist_eligible`；default、PPO、model promotion、
failover、assignment 和 control authority 均为 false，规则回退保留。旧
`d4-region-resource-model-bundle-v2` 继续是 development/shadow，不能被原地改写。

2026-07-26 合成完整 fixture 专项 17/17、相关合同 124/124、D4 全量 594/594 通过。当前
实际 development bundle 与 D6 fail-closed audit 的组合稳定返回
`d6_external_audit_fail_closed`，源三项制品哈希保持不变且未创建输出包。当前仍缺实现
evidence、正式 20-seed scope、实际采用、严格后继计划及 ACK、物理窗口、唯一 R0、配对
非退化和硬约束/联盟完整性实物。软件装配缺口关闭，真实准入证据 P1 保持开放。

## 2026-07-26 A2 development 候选评审

D4 已完成新版区域资源 development 候选的训练、置信拟合、独立校准和证据绑定。正式
900 episode 保留原数据不变，clean supplemental 100 episode 提供 quota、transfer、hold
和 request-replan 正类；两者通过同一规范 60/20/20 seed 视图只读组合。seed
1000-1019 完全隔离。

校准桶共 420 个样本，420 个候选被考虑并通过固定 0.6 置信、50 ms 时延、分布外、有限值和
确定性安全投影门。校准动作覆盖非零配额 40、transfer 20、hold 20、request-replan 40；
合成 OOD 420/420 被拒绝。候选 manifest、权重、数据、切分和实现谱系均可由隔离 loader
复核。旧 frozen bundle 的拒绝和加载合同保持兼容。

本轮不改变 D4 降级仲裁、联盟状态机或正式权限。候选清单明确
development/shadow-only，未运行 1000-1019，未形成实际采用、新计划 ACK、成员 ACK、物理
结果或配对非退化。下一步由 main 组织未见 seed 的隔离降级对照并由 D6 外部审计；D4 在证据
完整前继续拒绝 assist、authority 和 production 声明。

2026-07-26 D4 全量模块回归为 **577/577 passed**。本轮证据限于模块训练、校准和隔离
fixture，不是 AirSim、真实网络或物理效果证据。

## 2026-07-26 A2 证据链盘点

本节是新版校准候选形成前的历史盘点。当前候选能力和限制以上一节为准；正式证据链缺口仍按
本节执行。

D4 当时没有完整的“D6 外部审计 -> D4 evidence assembler -> 新 bundle”链路；该软件链现已
按页首实现。已有组件能分别
验证开发 bundle、区域建议、严格后继计划、运行消费、联盟成员业务 ACK、消息实际投递和结果
观测窗口，但没有一个准入对象把这些事实绑定到同一候选、同一 seed、同一 comparison key 和
同一 authority generation。该状态不会形成运行级旁路，因为 v2 bundle 和所有正式 advisor
调用仍被限制在 development/shadow。

后续分工已经收敛。D6 负责冻结通用外部审计制品，验证 clean source、bundle 树、逐 cell
实际采用、物理结果 availability 和 R0 配对非退化；main 负责产生真实运行、通信和物理制品。
D4 只负责模块语义装配：重验 advisory/model、严格新计划、owner/version/epoch/lease、
coalition required/acked members、逐成员 delivered receipt 以及 D6 pair 身份。D4 不复制
D6 schema，也不接受外部审计中的单个通过布尔作为晋级凭据。全部字段内容寻址闭合后，才另建
新 schema bundle；旧 v2 manifest 不修改。

现有 nominal 20-seed 和 `active_risk` 20-seed 仍不能合并。前者没有候选采用和物理结果，后者
执行的是规则回退且没有生产 runtime ACK。软件合同、development bundle、不可拼接 evidence
和正式 assist/authority 必须继续分开陈述。

本轮验证日期为 2026-07-26，没有新增场景或 seed。D4 全量 **569/569 passed**；验收只覆盖
软件旁路审计和既有合同回归，不证明新候选有效、物理非退化或正式准入。

## 2026-07-26 学习 scope 复核

main `d59352b` 已为 A2、C1、F1 建立 bundle 树、设备、诊断、版本和逐单元发布前后复核。D4 当前没有合法 admitted bundle。现有模型为 development/shadow，正式 nominal 配对候选采用 0/20；另一个 `active_risk` 物理制品执行的是规则回退，不是 D4 学习候选。运行 ACK、物理值和非退化值只有与同一个实际采用候选绑定时才可组合。

D4 本轮删除了模块内自声明准入旁路。v2 writer 不能输出 qualified/assist，manifest-less 注入策略也不能 assist。后续应由 D6 产生独立、带外 SHA-256 固定的 promotion evidence，新 bundle 另目录生成；旧 manifest 不修改。2026-07-26 D4 全量为 569/569 passed。

正式验收应选择非 nominal 降级场景和未见 seed，要求 treatment 真实改变下一版计划并获得运行和联盟成员 ACK，再从采用后的物理状态窗计算配对非退化。候选 0 次采用、两臂相同规则路径、同帧离线比较或 unavailable outcome 都不能进入准入分母。

## 2026-07-25 异步联盟确认补充

真实通信把联盟提案、计划广播和成员 ACK 分散到多个 tick。D4 区域编排此前在提案快照结束时立即终结确认窗口，首帧缺 ACK 会永久中止该代次。修复后，同一版本化联盟的成员位图跨快照保留，提案和部分 ACK 均处于 `collecting_acks`；全部必要 ACK 到达后才原子提交。

显式截止通过默认关闭的快照字段触发。租约到期、网络分区、联盟摘要冲突和成员不可执行仍直接中止或重构。陈旧、过期、越权和不匹配 ACK 只做拒绝和审计，不进入位图，当前时刻不授予权限；后续正确 ACK 仍可在有效租约内完成确认。

2026-07-25 新增 5 项异步生命周期用例，三文件专项 97/97、D4 全量 569/569。完整 ACK 前执行授权 0、三成员分时到达后原子提交、负例授权 0。

main 已完成 2 目标、4 资源、1 个二级侦察节点的单随机种子三维通信复跑。随机种子 `1271` 下，高威胁目标采用 2 个主成员和 1 个备用成员；二级计划版本 2 发布后先出现 0/3 ACK 的 `collecting_acks` 帧，随后 3/3 ACK 原子提交。提交前主成员保持，提交后两个主成员进入三维中段比例导引，备用成员继续待命。在线真值使用和 `global_track_id` 改写均为 0。该结果不是 AirSim、多随机种子、真实网络或物理拦截证据。

## 2026-07-25 通信因果证据补充

现有二级 readiness 和联盟 ACK 合同检查内容是否完整，但此前没有证明消息实际经过通信链路。main 的 5v5 通信关闭复现显示，heartbeat、communication 和 sustained readiness 可全部被适配层直接填成 true，导致 8/8 区域在中心失效后仍进入可执行二级层。

D4 已增加独立通信证据门。每条 readiness、区域计划广播、区域计划所有者确认和联盟 ACK
都必须引用 delivered receipt。回执由版本化 envelope 和 truth-free payload 严格生成，
保存 source/destination、双时间戳、authority、plan、epoch、lease、partition generation
与 payload SHA-256。调用方不能另传这些字段覆盖 envelope/payload。无回执返回
`receipt_missing`；旧代次、晚到、摘要不一致和冲突重放均失败关闭。验证器只输出证据结果，
不授予 owner 或推进 coalition。

因果证据专项 56/56 通过，规模覆盖 5/20/50/100/200。main 已把 D4 控制消息接到实际通信队列，通信关闭负例现为 0 个可执行区域、8 个失败关闭区域，原 P0 已关闭。异步三成员单随机种子正例已按上节通过；AirSim 多随机种子与正式矩阵仍按 P1 复跑。

**2026-07-22 跨独立运行身份审查**：D4 已复核 clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002、三组 10 秒 200v200 运行。两侧各 30 条 `regional_failover` 和 30 条 `region_resource_advice` 均通过原始正式裁决摘要、authority 摘要、advisory 内容地址及摘要副本一致性检查。独立 D3 planner 的原始 `plan_id` 不同会确定性改变 `formal_decision_digest`、`authority_digest` 和 `advisory_id`；先验证单运行完整性，再规范 D3 谱系并按原算法重算后，30/30 对 D4 正式裁决和建议逐字段相同。`advisory_id` 可在只读比较视图中重算，不能按事件序号替换，也不能修改原日志或消费 ledger。owner/layer/role、plan version、epoch、lease、ACK/fence、region/task/global-track/resource/node/coalition identity、正式 decision 和 recommendation 仍要求严格相等。当前批次可从合同回算 authority 原始输入；通用跨提交审计仍需 main 持久化完整 authority payload，缺失或回算不闭合时失败关闭。

**2026-07-22 计划代际适配复核**：main 的中心失效 20-seed 物理续跑形成 20 pair、196 region，D7 世界命令已应用，但 D4 以 `isolated_execution_plan_not_strictly_new` 拒绝 196/196。formal decision 绑定同帧故障后 current plan，物理 arm 却从故障前 `previous_plan` 重新求解，得到同版本异 ID applied plan。D4 合同不需要放宽：被动降级 source 必须分别匹配 secondary 或 distributed formal owner；主动风险 source 保持 center owner。applied 改变执行时必须严格升版，未改变时只能做同身份、同 binding 的 refresh。authority 变化需先重建 formal decision/lineage。新增三类刷新、同版本异 ID 和故障前 owner 负例后，隔离专项 26/26、D4 全量 508/508。main producer 和 D6 复跑仍是开放 P1，本轮结果不能解释为降级采用或策略收益。

**2026-07-21 PDT / 2026-07-22 UTC 隔离多周期合同更新**：D4 已新增 degraded-scenario lineage、candidate gate、isolated plan-consumption ACK 和 adoption evidence。只接受 `center_failed`、`center_and_secondary_failed`、`active_risk` 三类经 formal D4 decision 证明的来源；nominal 场景直接拒绝。候选门保持 confidence `0.6` 和 latency `50 ms`，并保留 OOD、finite、failure、deterministic projection。成功结果明确分为 `new_execution_plan_applied` 与 `evaluation_refresh_applied`，同时记录 `candidate_considered/gate_pass/rule_fallback`；只有严格更新且 owner/epoch/lease/binding/receipt 全部 current 的候选新计划才算隔离采用。同代刷新、规则 fallback、缺 ACK、旧 epoch、过期 lease、binding 篡改、分区和缺联盟 ACK 均不能形成候选采用。D4 另以无 D3 import 的严格 parser 接收 `d3.isolated-plan-consumption-evidence.v1`，核对来源 lineage、计划、binding、时间窗、内容哈希和隔离权限后生成非生产 D4 回执。新增专项 19/19、相关联合回归 103/103、D4 全量 501/501 passed。该合同固定 `isolated_simulation_only=true`、`production_runtime_ack=false`，不提供物理、成对非退化、因果、反事实或生产 authority；main/D6 的真实多周期 producer 和评估仍待完成，既有 nominal 5v5 不构成降级策略效果证据。

**模块定位**：D4 负责中心 C2 异常、二级节点接管、主动降级仲裁和完全无中心协商的离线科研仿真方案。
**核心边界**：本文只讨论摘要交换、状态机、故障注入、降级协同和评估日志；不包含真实通信链路、飞控控制、火控参数、毁伤逻辑、自动处置或授权绕过。

**2026-07-22 保留 seed 正式 v2 证据更新**：当前权威 `reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296` 绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS` 与 manifest SHA256 分别为 `821f1503...72bc`、`d6ef23b2...883c`。D6 独立重算确认 20/20 source clean 且 finite、truth 使用数 0、20/20 candidate considered；confidence min/mean/max 为 **0.508892953/0.563426384/0.569492280**，在未下调的 `minimum_confidence=0.6` 下通过 **0/20**，OOD、latency、finite、failure gate 各通过 **20/20**，aggregate **0/20**，safe adoption **0/20**，规则回退 **20/20**。执行时延 `treatment_candidate_latency_ms` 的 nearest-rank P95 为 **2.241315 ms**；门控汇总 `candidate_gate_summary.candidate_latency_ms` 的线性插值 P95 为 **2.264415 ms**。D6 profile-bound v2 sidecar 位于 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，状态为 `pass_offline_assignment_comparison_only`；sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。sidecar 已存在只表示同帧离线分配比较可用；runtime ACK、干预后物理结果、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍 unavailable。专项 **33/33**、D4 全量 **482/482 passed**；`minimum_confidence=0.6`、pair input、冻结 bundle identity、确定性投影和 next-cycle safety gate 均未放宽，`PPO/assist/authority=false`、`rule_fallback=true`。该 nominal 5v5 只证明门控分解与规则回退，不证明候选或降级策略有效。

**2026-07-21 区域结果与 reward 合同更新**：D4 新增只读 `d4-region-resource-reward-evidence-v1`。它以 ACK v2 为窗口起点，绑定 advisory/模型、源与当前计划、owner/epoch/lease/fault generation、ACK 序号/时间、源与结果快照、执行/联盟首尾哈希和来源制品 SHA。八项成本均保存 raw value、单位、归一化分母、availability/reason，缺测不补零。新执行计划在全部分项可用时只得到非因果时间窗口观测 reward；同代评估刷新只能记录观测成本。新增专项 19/19，D4 全量 449/449。该合同没有生成正式 episode、paired、causal 或 on-policy 证据，不能代替成员 ACK、物理执行或正式策略准入；PPO、assist、authority 仍关闭。

**2026-07-21 区域建议运行时确认更新，2026-07-27 语义复核**：D4 的 main-independent parser 使用 `d4-region-resource-runtime-ack-evidence-v2`。新执行计划要求 plan ID/version 严格推进、正确前序计划和完整 owner/epoch/lease；显式同代 refresh 仍可作为传输校验证据，但不计为 A2 动作采用。当前集成测试已拆成无操作 `no_successor` 和真实 `hold/request_replan` successor 两条链。四项 successor 篡改均失败关闭，专项 **6/6 passed**，D4 全量 **658/658 passed**。无操作建议不修改 formal D4 authority、D3 plan 或 D7 gate。冻结 900 episode 没有 v2 字段；`CoalitionMemberAck`、真实 outcome、paired shadow、PPO、assist 和 authority 仍 unavailable/false。

**2026-07-21 区域调度全样本准入更新**：D4 已新增只读、失败关闭的全样本审计。正式区域数据共 900 episode、1798 frame/sample、14384 action，规范 60/20/20 视图为 540/180/180 episode、1079/359/360 sample、8632/2872/2880 action；clean supplemental 课程共 100 episode、300 frame/sample、1200 action，规范切分为 60/20/20 episode、180/60/60 sample、720/240/240 action。900/900 与 100/100 episode SHA256 通过，1798/1798 与 300/300 样本数值有限且通过 action/transfer 配额守恒、邻接容量、owner/plan/version/epoch/lease、安全投影、保留 seed、dirty 和真值隔离检查，违规数为 0。`target.kind=rule` 只作规则教师标签，不是 truth；projected recommendation 只作后投影建议，不是 runtime applied ACK。真实 `CoalitionMemberAck`、outcome、可归因 reward、被拒旧 generation 样本和 paired shadow 均 unavailable/pending，D6 外部带外 SHA256 复核尚未完成。审计专项 10/10，D4 全量 **397/397 passed**；PPO、assist、authority 仍关闭。

**2026-07-21 区域动作覆盖课程更新**：D4 已实现独立、truth-free、确定性的区域课程 producer。它按共享 registry 的 100 个训练 seed 生成 100 episode/300 frame，动作分布为 hold 100、request-replan 200、nonzero quota 200、transfer 100；60/20/20 三个 canonical 桶均覆盖四类动作，硬约束违规、在线真值字段和保留 seed 泄漏均为 0。main 已在 detached clean worktree commit `9445ed6` 上重生当前证据，dirty episode 数为 0，dataset SHA256 为 `7e17aba...9e72`，canonical view SHA256 为 `9aa28765...cc8de`，行为克隆只读 view 可用。首次 dirty 产物只保留为开发历史。reward/outcome 300/300 unavailable，PPO、assist 和 authority 不开放。该增量关闭动作覆盖 producer、审计接口和 clean BC 数据准入缺口，不关闭正式状态分布、策略收益、D6 因果回报或外部保留 seed 评估。课程专项 6/6，该阶段 D4 全量 **387/387 passed**。

**2026-07-21 共享 seed 切分更新**：D4 已增加 source-external shared registry 的独立消费者。它严格核对 `scalable3d-shared-seed-split-registry-v1` 的 schema/policy、D3 兼容排序、content/assignment SHA、源 training-seed-registry SHA，以及 100 个 dataset seed 的完整覆盖和 1000-1019 保留集隔离。原 900-episode dataset 和 70/15/15 split 不改写；显式只读视图映射为 60/20/20 seed、540/180/180 episode、1079/359/360 frame。BC loader 默认仍使用模块内 split，只有调用方传入 canonical view 才切换。正式审计前后源数据目录树哈希一致。共享切分阶段为 381/381；候选门诊断阶段 D4 全量为 **482/482 passed**，当前全量见本文顶部。该更新只关闭 D4 的跨模块数据切分消费缺口，不提供策略收益、PPO 或 assist 证据。

**2026-07-21 正式行为克隆审计与准入更新**：D4 只读审计 2026-07-20 正式区域数据 900 episode/1798 frame，900/900 episode SHA256、source/schema identity、70/15/15 数值 seed 原子 split 和外部 1000-1019 隔离均通过。固定 seed `20260720` 的开发训练完成 66 epoch，最佳 epoch 54，内部测试 loss `0.071545`；准入复跑耗时 66.02 秒、推理 P95 `0.7774 ms`，权重 SHA256 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62` 与首次结果一致。D6 正式审计确认正式数据 14384 个区域动作中的 nonzero quota、transfer、hold、request_replan 均为 0，898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。独立补充课程和 reward schema 不改写该结论，也不提供正式回报。bundle admission 继续固定 `action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`。结论严格限定为 development/shadow-only；低损失不代表策略能力，PPO/assist 不可用。该历史阶段 D4 全量 **482/482 passed**，当前全量见本文顶部。

**2026-07-20 区域学习 episode 数据合同更新**：D4 新增 truth-free `d4-region-learning-dataset-v1` 及公开 source/frame、stage/finalize/load API。复核后训练 target 不再信任外部 `projected=true`，固定重验 projector、owner/plan/version/epoch/lease、备用、edge 和 quota；manifest 独立重验 canonical episode inventory、availability 与 split，truth/object/global-track key 变体失败关闭。该合同阶段数据测试 13/13、建议/消费 49/49、合计 62/62，D4 全量 **365/365 passed**。96-episode/192-frame 高基数样本只证明确定性合同，不是正式数据或模型收益证据；后续正式数据和开发 checkpoint 结论见上一段。正式降级控制路径未改变。

**2026-07-20 区域资源建议、消费合同与质点接线更新**：main-owned scalable 3D 已消费 D4 区域 verdict，闭合单一二级、多二级区域 owner、中心/二级连续失效后的 distributed D3 plan，并用 owner/node、plan version、epoch、lease、commit mode 与 fault generation fence 约束 D7；既有定向 8/8 passed，仅属质点接口证据。D4 新增 truth-free `RegionResourceSnapshot`、规则和确定性安全投影，以及共享变长图 actor-critic、BC、原生 clipped PPO、manifest/state_dict/SHA 和 paired shadow evaluator。动作只含区域 quota/邻区 transfer、备用、侦察和 hold/replan，不生成 resource-target assignment。`d4-region-resource-advisory-v1` 固化内容 ID、有效期、source plan、逐区域/transfer generation、reserve/committed 与 edge proof；`RegionResourceAdvisoryGate` 对下一周期 current snapshot/plan/epoch/lease/ACK/fault/守恒/邻接/容量和重复 ID fail closed。规则 fallback 与学习候选共享同一 projector；D4 仍不修改 D3 plan。原专项 32/32，新增 15 个消费 case 后该阶段专项 47/47、D4 全量 **350/350 passed**。该阶段只有纯 Python 合同证据；后续开发 checkpoint 不改变 D4 确定性状态机的最终裁决权，也不提供 AirSim 或真实网络收益证据。

**2026-07-20 区域化更新**：D4 新增 `d4-regional-failover-v1` 和 scalable3d mapping adapter，按动态 region/task/node 列表维护逐区域唯一 authority。中心未 `failed` 时主动 D1/D2/D3/D5 证据不转 owner；中心 `failed` 后只选择对 region 有显式 coverage、strict readiness 和有效 lease epoch 的 `mobile_high_recon`；二级不可用后才执行能力/跨区域 capacity 受约束 bid selection。中心、二级和 distributed 三层的 `k>1` 都必须 required ACK 全集、current plan/coalition version、epoch 和最早 lease 后原子 `committed`，commit metadata 分别标记 `d3_center_assignment`、`d3_assignment_secondary_coordination` 和 `bounded_constrained_bid_selection`，只有最后一种属于 distributed formation。缺 ACK、旧 generation、过期 lease 和任一层级分区均闭锁。新增 23 项测试覆盖 5/20/50/100/200 区域 metadata、声明节点数上限和安全边界，该阶段 D4 全量 **303/303 passed**，现已由 449/449 覆盖。区域合同单元用例本身无 AirSim/真实网络或物理证据；main 后续质点接线不改变该证据边界，受约束 selection 也不等于完整 CBBA/CCBBA、全局组合最优或自主重构。

**2026-07-15 P0 历史更新**：此前 278/278 只覆盖 coordinator、episode adapter、secondary coalition proposal、resource lease 和 D6 metadata，把它写成所有公开入口已闭锁属于过度声明。`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 后续要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格未过期；同一 active plan 维持路径也复核。当日 D4 全量 280/280 passed，后续由 303/303、430/430 和当前 482/482 回归覆盖。

**2026-07-15 M5N2 证据更新**：baseline/candidate 各 10 seeds、共 20/20 case 已完成，但全部是中心继续执行负对照，`active degradation=0`。coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均为 `collision_stop`；因 collision object 缺失，不把失败标签自动升级为主动降级。D4 仍联合 D1/D2/D3/D5 证据仲裁。D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`。额外 `png_ttc_2v2_seed001` 排除，dropout=0。该批不能关闭 secondary/distributed 多 seed P1。

---

## 0. 2026-07-11 P1 状态更新

2026-07-11 的 `p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md` 记录 D4 P1 合同层 ComputerVision 总体验收为 8/10。二级协调者 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` 并输出 `degrade_to_secondary`；完全分布式 `INT-02` peer 以 ACK 3/3 进入 `executing` 并输出 `degrade_to_distributed`；确认窗口显式截止后的缺 ACK 场景以 2/3 ACK 进入 `aborted`，T001 三成员均 `hold_for_review`。2026-07-25 后，截止前普通快照保持 `collecting_acks`。这组正负例证明 commit 与 fail-closed，不证明物理拦截。

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
| peer commit 缺 ACK | 确认窗口显式截止时 ACK 2/3，最终 `aborted` 并 `hold_for_review`；已通过 |
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
