# D6 系统级离线评估模块原理

## 跨视角图证据分层（2026-07-21）

D6 不把“数据可训练”解释为“模型可上线”。D5 clean 图证据依次分为数据支持、训练数据来源、模型内部
测试、保留 seed 和同 seed 配对影子五层。每一层只回答自身问题：边标签是否完整、训练视图是否固定、
模型是否在内部测试通过、未参与训练调参的 seed 是否通过、相同 seed 下模型与规则路径是否形成正式
配对。前层通过不能补齐后层。

数据层使用显式文件和调用方 SHA-256 建立来源链。规范划分必须为 60/20/20，共 100 个训练注册 seed；
`1000-1019` 只保留给后续独立验收。正边和负边均须存在，未标注边必须为 0，来源必须
`repository_dirty=false` 且无 manifest/artifact 改写。当前证据满足数据支持和训练来源，但尚无真实
模型报告、保留 seed 结果和 paired shadow，因此 G1、辅助模式和控制权限继续关闭，确定性几何规则
保持默认路径。

未来模型内部报告必须同时绑定权重、配置和训练来源 SHA，并包含聚合测试指标、45 个场景规模单元和
推理时延。该报告只可能打开“模型内部测试”一层。保留 seed、paired shadow、正式奖励、因果和反事实
结论仍需独立证据。

## 运行时计划确认与离线结果的证据边界（2026-07-21）

D6 将本链路分成三个互不替代的证据面。在线面包含 D3 分配计划、可选 D7 导引批次和 main
`runtime.assignment_plan_ack`，其中不得出现目标真值。身份面由 D2 离线评估提供，只接受 D1
source-observation lineage 形成的唯一 `global_track_id -> truth target` 映射。物理面包含独立真值状态
和 5 米接近事件，只在离线阶段使用。三个输入面各自带 SHA-256；任一文件、来源序号或载荷摘要不一致
时停止联接。

同一资源的连续决策按 ACK 时间切窗。前一窗口采用左闭右开区间，后一窗口从下一 ACK 时刻开始；最后
一窗闭合到 episode 终点。这样，每个离散真值样本和接近事件最多归入一次资源决策。窗口输出首末和
最小三维距离、距离闭合量、正确目标事件及同一资源对其他目标的事件。错误目标进入 5 米不计为当前
分配目标的正确结果。

有界配对进展诊断定义为

\[
q=\operatorname{clip}\left(
\frac{d_{start}-d_{min}}{\max(d_{start}-5\text{ m},\epsilon)},-1,1
\right).
\]

该值只描述单条已执行绑定在一个观测窗中的最佳距离进展。ACK 必须接受，D7 binding 必须实际进入
世界且不为 hold，D2 映射必须唯一，真值状态窗必须完整。任何一项缺失时 `q=null` 并记录原因。该诊断
不包含规则基线差值、反事实轨迹或因果归因，因此不能作为 D3 正式近端策略优化奖励。

当前准入继续分层：运行时 ACK 和 observed pair diagnostic 可以 available；formal reward、same-seed
paired shadow、held-out seed performance、counterfactual 和 causal attribution 均 unavailable。
PPO、在线 assist 和控制 authority 保持 false，规则回退保持强制。同一 plan identity 可发布显式
评估刷新；每次 ACK 仍按 sequence 和时间戳形成独立 occurrence。刷新前后的绑定、联盟、未分配目标和
authority 必须保持同一规范执行签名。真实 3v3 回归已验证 2 个 occurrence 和 6 个窗口；尚无正式多
seed 证据。

## 跨模块学习数据联合准入（2026-07-21）

联合准入解决两个不同问题。第一项是规范 seed 视图是否一致，即 D3、D4、D5 是否把同一个数值 seed
放入相同的训练、验证或测试集合。第二项是 producer 是否对全部样本、文件、数值和安全合同完成审计，
并由 D6 独立复核其身份。两项现均通过：`BC canonical view available=true`，D3/D4/D5 和跨模块
structural full-sample=`complete`。总体学习准入仍为 `partial`。结构完成不等于模型已训练，也不等于
数据已满足策略优化和在线控制条件。

D6 只读接收训练 seed 注册表、共享 seed 注册表、D3 正式 manifest、D4 正式 manifest 与独立
canonical view、D5 tracklet/active-vision 正式 manifest、canonical view、readiness，以及 D4/D5
补充课程 summary。D3、D4、D5 分别提供 producer 全样本审计和调用方带外文件 SHA-256。每个输入都
核对 schema、来源身份、文件与规范内容 SHA-256、expected/actual binding、binding checks、clean
source、完整计数和缺失状态。任一身份不一致、哈希篡改、dirty source、错误 seed assignment、保留
seed 泄漏、状态或权限误开都会失败关闭。

真实审计使用 2026-07-21 冻结的 900 episode、100 个训练 seed。规范
train/validation/test=`60/20/20`，保留 seed `1000-1019` 泄漏为 0。D4 formal canonical view 的
文件 SHA-256 为 `73a365d32b0439fbf805f40ea7941b8e992fe4c68687cbc5496704f230440b11`。该
文件是正式 900 episode 的 detached view；D4 的 100-episode 补充课程具有另一份 canonical view，
两者用途不同，不能互相替代。

证据分为四层。正式观测语料保存原始观测和规范 seed 身份；补充规则教师课程扩大规则动作覆盖；离线
评估标签描述可供 evaluator 使用的 truth 隔离标签；runtime ACK evidence 证明建议动作确实被运行时
接收或拒绝。D4 补充课程覆盖 hold 100、request-replan 200、nonzero quota 200、transfer 100。D5
补充课程覆盖 hold/observe-target/reacquire/search-sector=`200/600/200/200`、wide/zoom=`1000/200`、
interceptor/recon=`600/600`。这些动作覆盖不能替代正式语料或运行时执行证据。

D4 supplemental 的 canonical episode 切分为 60/20/20，frame 切分为 180/60/60。D5 tracklet 的
480 条候选边中有 362 条正标签、19 条负标签和 99 条未标注边。标签状态因此是 `partial`，而非完整
可用；381 条已标注边可用于离线评估准备，99 条未标注边必须保留在分母和完整性说明中。

D5 synthetic ACK 的 applied/rejected/missing 各 400，是对 ACK 分支的确定性故障注入。它没有实际
运行时动作归因，因此不能生成 reward、不能证明相机动作被执行，也不能提升在线准入。当前 reward、
outcome、counterfactual、causal、runtime ACK 和 paired shadow 均不可用。PPO、在线 assist 和控制
authority 保持关闭，规则回退强制启用。该审计没有模型收益结论。

D5 supplemental BC 全样本审计覆盖 100 episode、1200 sample，canonical episode=`60/20/20`、
sample=`720/240/240`；online/offline/descriptor 各 100 个，`302/302` 个登记制品完成 SHA-256 校验，
有限特征 `1200/1200`。online truth、保留 seed、dirty episode 和 D5 创建、改写或换绑
`global_track_id` 均为 0；四类离线标签保持 unavailable，没有以零补值。

D3 全样本审计覆盖 900 episode、1604 决策帧、3,658,815 条候选边、117,304 个规则选中动作和
43,905,780 个有限特征值。D4 全样本审计覆盖正式 900 episode/1798 sample/14384 action 和补充 100
episode/300 sample/1200 action。D3 `reward_components` 只作规则教师诊断；D4 `target.kind=rule` 不作
truth，`recommendation.projected=true` 不作 runtime ACK。

剩余工作是补齐真实动作采用与版本绑定、runtime ACK、可归因终局结果和奖励、因果/反事实证据，形成
同 seed paired shadow 非退化证据，并使用保留 seed `1000-1019` 做独立验收。2026-07-21 联合审计
专项 `37 passed`，D6 全量 `401 passed`；仅有既有 Matplotlib `Axes3D` 环境 warning。报告只能写到
正式 generation 根之外，防止离线
评估产物改变正式数据树。

## 历史共享种子划分治理（2026-07-21）

以下内容说明 detached canonical views 形成前的原始 manifest mismatch。当前准入状态以上一节为准，
生产者 manifest 没有被回写。

跨模块联合训练要求同一个数值 seed 在 D3、D4 和 D5 中承担相同角色。若 seed 7 在 D3 属于训练集，
在 D5 属于测试集，联合调参会把同一仿真随机条件同时用于训练和测试。模型指标因此失去独立测试含义。
D6 将这种问题作为数据治理失败处理，不把它解释为模型性能波动。

共享注册表是源训练 seed 清单之上的 detached 视图。D6 先验证源清单 SHA-256、训练/保留 seed 隔离和
100 个训练 seed 覆盖，再验证注册表内容哈希与 assignment 哈希。随后按冻结的数值 seed 排序公式独立
复算 60/20/20 分配。哈希正确但分配不能复现，或注册表正确但模块 manifest 没有精确遵守，均不能开放
联合训练。

D3 manifest 只有按 split 聚合的 seed、episode 和 frame 数。发生 seed mismatch 时，D6 无法从
manifest 判断具体多少 episode/frame 受影响，因此使用 `null+reason`。D4 和 D5 保留逐 episode 或逐图
记录，可以按 seed 直接累计 mismatch episode 与 sample。这里的 sample 对 D4 是区域帧，对 D5 图模型
是候选边，对 D5 主动视觉是相机策略样本。不同统计单位不相加。

正式审计确认 D3 与 canonical 完全一致。D4 有 51 个 mismatch seed；D5 图数据和主动视觉数据分别有
65 和 62 个 mismatch seed。联合训练 readiness 为 unavailable。该结论不否定各模块在本地 split 上的
行为克隆开发结果，也不证明任何模型达到准入门限。D6 只记录治理状态，不改写生产者 manifest。
工程验收要求注册表八项自校验通过，并且四个 required module 均 exact。本次注册表通过、模块联合门
未通过；2026-07-21 D6 全量回归为 `364 passed`。

## 离线学习标签的证据分层（2026-07-20）

D6 将学习标签分成四层。`outcome` 表示后续观测到的状态变化；`reward` 表示在动作确实进入运行时后，
按冻结公式计算的有界评分；`counterfactual` 表示同一初态执行替代动作的结果；`causal_label` 表示经过
动作归因和反事实比较后得到的因果判断。四层分别记录可用性、值、缺失原因和来源。上层缺失不能用
下层数值替代，也不能用零填充。

D4 的纯观测结果使用同一 episode 中相邻区域帧。对目标需求、高威胁积压、D1/D2 不确定度、D5
可见性与一致性、预备和已投入资源、通信时延、丢包、分配冲突和降级失败数计算前后差值。该差值只
说明系统状态发生变化。当前正式帧没有推荐被采用、实际动作摘要和终局结果的闭环证据，所以 D4
reward 保持 unavailable。规则 recommendation 可训练行为克隆模型，但现有 14384 个动作没有非零
quota、hold、重规划或跨区转移，多样性不足以支持策略准入。

D5 对有目标指向的动作计算角误差、可见概率、关联置信度、视场内状态和遮挡比例的变化；搜索动作
计算视场覆盖率、平均可见概率和平均关联置信度的变化。纯观测结果只要求同相机相邻样本落在 0.5 秒
窗口内。它不要求 ACK，也不带动作归因。

动作奖励使用以下硬门：样本必须有运行确认；确认必须与样本、相机、计划版本、联盟版本和通信版本
一致；已接受命令还必须在后续相机反馈中出现同一命令版本，且反馈时间不早于确认时间。满足硬门后，
目标指向奖励按角误差改善、可见性、关联置信度、进入视场和遮挡改善加权，权重依次为
`0.30/0.25/0.20/0.15/0.10`。搜索奖励按覆盖率、可见性和关联置信度加权，权重为
`0.50/0.30/0.20`。结果截断到 `[-1,1]`。明确的拒绝确认记为 `-1`，用于表示动作请求被运行时拒绝；
缺 ACK 时不生成奖励。相邻姿态变化不能证明命令已经应用。

单条事实轨迹只能支持观测结果。替代动作没有被执行，就无法从该轨迹识别反事实结果。当前正式数据
没有同初态配对重放、随机干预或其他可识别设计，因此 counterfactual 和 causal label 全部
unavailable。行为克隆学习的是规则示范分布，不能解释为因果最优策略。

正式 900 episode 审计得到 D4 outcome `898/1798`、D5 outcome
`1,063,214/1,153,242`。D4 和 D5 reward 均为 0 条可用。D5 的 1,153,242 条样本没有 runtime ACK，
有效模式全部为 disabled；这是 PPO 不可用的直接原因。训练 seed 为 100 个，保留评估 seed
`1000-1019` 共 20 个，两者没有交集。D4 与 D5 各自保持 seed 原子 split，但两套 split registry 在
47 个 seed 上不同，造成 423 个 episode 跨模块 split 不一致。该数据只能用于单模块训练；联合训练需要
共享 split registry，不能从其中一个模块静默覆盖另一个模块。

审计证据日期固定为 2026-07-20。2026-07-21 的代码验收为标签专项 `17 passed`、D6 全量
`351 passed`；验证没有启动 AirSim，也不构成模型性能结论。

## 算法实验矩阵证据边界（2026-07-20）

算法变体是实验配置，不是目录标签。D6 只读取 episode 内持久化的 matrix schema、variant、comparison
key、场景族、显式规模和 seed。字段缺失时保留原有 D1-D7 指标，但矩阵身份为 unavailable。显式
comparison key 可直接使用；缺 key 时只能由配置内的场景族、对称规模和 seed 形成审计键，不能使用
路径名称。当前 v1 的对称 scale 要求 target_count 与 resource_count 相等；不对称输入保持 key
unavailable，等待 producer 给出明确 scale 合同。

变体执行分为“运行时解析”和“实际采用”两层。运行时解析要求 config 与 summary diagnostics 一致，
所需组件 bundle loaded、requested/effective mode 均为 assist、fallback 为空，未声明组件保持 disabled。
实际采用继续使用模块证据：D3 读取学习代价实际 applied，D5 图模型读取 loaded model scoring，主动
视觉读取 assist adopted。D4 advice 单独不证明采用；main 消费合同必须通过完整引用和 summary 一致性
审计，并明确 `d3_hint_applied=true`。R0 还要确认四个组件没有 assist 或实际采用泄漏。

每个比较键固定要求 R0/G1/A1/A2/A3/C1 六个 cell；中心失效、二级失效和高威胁 M-to-N 再要求 F1。
缺 cell、重复 cell 和执行无效 cell 分别统计。按变体的描述统计保留每项 availability。paired delta
只使用同键唯一 R0 与唯一有效变体，方向为变体减 R0；至少两个独立键才 bootstrap。clean/formal 与
dirty development 使用独立子集，配对存在也不自动形成因果结论。

## 当前 schema 与历史可读性（2026-07-20）

schema 字段非空只能证明 producer 写入了一个名称，不能证明该名称与当前 evaluator 合同一致。D6 使用
本地版本化 registry 精确核对 world、episode bus、scenario、online observation 和 offline truth，
同时核对 scenario config 自身 schema。registry 不从 main runtime 导入，避免离线 evaluator 因运行
模块安装状态改变判断。

当前 online observation 合同是 `scalable3d-observation-v1`。旧 fixture 中的
`scalable3d-online-observation-v1` 不属于当前 producer 合同。D6 仍保留每个原始 schema 字段，并为其
补充 expected current、match、status 和 reason。这样历史数据可以继续解释，但旧、未知、篡改或缺失
schema 不会被误列为正式 clean evidence。

整体 `current_schema_contract_match` 是 formal acceptance 必需项。全部字段存在时，不匹配产生可用的
false 和明确失败原因；字段缺失时整体结果为 unavailable。验证包括一个全匹配正例、五项 manifest
不匹配和一个缺字段负例；专项 `32 passed`、D6 全量 `304 passed`。

## 主动视觉的命令、执行和归因分层（2026-07-20）

D5 主动视觉输出属于观察管理，不等于相机已经执行。D6 将每次运行拆成五层：确定性规则命令、影子
模型建议、经安全外壳采用的辅助动作、main runtime 的 applied/rejected ACK、离线物理结果。前一层
不能替代后一层。shadow 模式下模型建议只用于比较，实际命令仍由规则策略给出；assist 模式只有在
D5 选择模型动作且 main 返回 applied ACK 后，才能称为已执行辅助动作。

命令与 ACK 的身份由 camera ID、resource ID、issued timestamp、plan version、coalition version、
communication version、intent 和 mode 共同确定。只比较 camera ID 会把旧计划 ACK 接到新命令；只
比较时间会混淆同帧多个相机。D6 保留未 ACK、意外 ACK、延迟和拒绝原因，不从 applied 子集缩小分母。
日志缺失时指标 unavailable，summary 的零不能替代逐条命令证据。

主动视觉只能引用中心维护的 `global_track_id`。D6 在命令时刻向前查找最近的 D2 中心航迹集合，核对
每个目标引用；ACK 必须返回同一编号。多个相机引用同一航迹在协同观察中是合法行为，未知编号或 ACK
改写才是违规。D6 只审计，不创建、不合并、不重绑定编号。主动视觉 command/ACK 同时参加递归在线
truth-like 字段检查，仿真真值仍只允许进入离线标签和评估产物。

因果归因需要配对实验。一次 assist applied 后出现五米接近，只能说明事件先后发生，不能排除初始
几何、随机机动、其他模块或规则安全外壳的作用。正式归因必须使用同 seed、同场景、同配置的规则控制
组和 assist 处理组，并保存模型版本和实际采用证据。在此之前 attribution 保持 null/unavailable。

2026-07-20 验证为 8 项主动视觉 deterministic tests，显式规模 T/R/Rc/Cam=`6/4/1/5`，报告测试含
2 个不同 seed；与既有 scalable 测试合计 `25 passed`，D6 全量 `297 passed`。这些结果证明 consumer
合同和缺值规则可运行，不证明主动视觉性能。

同日的 main-runtime 临时 smoke 使用 6v6、1 个 recon、7 台 camera、seed 37、2.2 s，D6 读取到 133
条规则命令和 133 条 applied ACK，拒绝、中心航迹引用违规和在线 truth 字段均为 0。该单 seed 输入的
worktree 为 dirty，因此只能补充端到端文件合同证据，不能进入正式统计。

## Scalable 3D 学习证据分层与缺值原则（2026-07-20）

D6 对 main-owned scalable 3D episode 只做持久化文件消费。learning runtime metadata 与 D4 advice
来自写盘 config/summary/online JSONL；D6 不导入 runtime、不回写总线、不参与控制，也不读取在线真值。
`online_truth_use_count` 与递归 truth-like 字段审计仍必须为零，正式 evidence 还必须满足
`repository_dirty=false`、配置 hash 和 D4 policy version 可用。

学习能力必须分成五个不可互相替代的证据层：

1. **bundle 能加载**：只证明 producer 成功加载了有 fingerprint/version 的 bundle。
2. **shadow 有输出**：只证明生成了结构合法、版本新鲜且经过安全投影的 recommendation。
3. **assist 获准**：只证明 unseen-seed/fallback 等 advisor gate 允许 assist。
4. **控制实际采用**：必须由独立、版本化 producer evidence 说明哪个 plan/command 采用了 advice。
5. **物理结果**：是独立离线结果层，不能仅凭时间相邻归因于 advice。

当前 `d4-region-resource-advisory-runtime-v1` 保持正式 D4 decision digest unchanged，也没有 control
adoption 字段。因此 `assist_eligible=true` 不能解释为控制生效。独立证据来自 main 发布的
`d4-region-resource-consumption-v1`；缺消费、旧 schema、未知或篡改建议引用及 summary 冲突时，D6
将 control adoption 保持 null/unavailable。五米 proximity 同样不自动成为 advice 效果或任务成功。

availability 先于数值。bundle 未加载时 model fingerprint/version 为 unavailable，规则 runtime
version 不冒充模型证据；字段缺失不能补零。D3/D5 fallback 只有 producer 显式写出 null/none 或原因
时才能形成可用零/正计数。D4 advice 的旧 schema、非法类型、过期 scenario/plan/version/epoch/lease、
非守恒 quota、projection 非法或 digest flag 篡改均 fail closed，且不能用合法 advice 子集缩分母。

规模分组仍来自显式 scenario/version 与 target/resource/recon/camera 数量，`2v2/5v5` 只允许作标签。
统计按 seed 组织；bootstrap 以不同 seed 的 episode 均值为单位。单 seed 只做 descriptive，不用 episode
内帧数伪造模型推断样本。

2026-07-20 的验证是 17 个 deterministic scalable fixtures，不是真实模型或物理实验。覆盖 disabled、
missing bundle、assist-to-shadow、assist gate、守恒/非守恒、projection、formal mutation/unchanged、
digest 篡改、旧/缺版本、缺 advice、既有规模/缺值和双 seed 聚合；后续消费合同与矩阵专项扩展到
scalable `40 passed`、D6 全量 `320 passed`。正式 clean、多规模、多 seed 矩阵、global-track truth
映射和真实物理效果仍是 main/producer P1。

## Legacy provenance 必须由完整持久化证据闭合（2026-07-15）

目录名缺省值不是 provenance。旧 suite 若 summary/cases/rows 都未持久化 ClockSpeed，只有在调用者
提供真实路径时，D6 才可按已注册的 20 个 case_id 读取固定 sibling generated settings；20/20 文件
和显式有限正数必须存在且一致。少一份、缺一个键、出现冲突或非有限值均应拒绝整档，而不是猜测
1.0。inline mapping 不允许触发环境相关搜索，部分显式值也不得与 fallback 混合。

真实三档运行中，1.0 由上述 20 份 settings 闭合，0.2/0.1 由 result row 闭合。机会合同是独立于
provenance 的第二道门：60 case 中 4 case 机会不符，相关 aggregate 保持 unavailable；这优先于
对剩余 case 计算看似更好的成功率。truth 审计、reserve 排除、main/control 分层和缺值不补零原则
均未改变。

## Timing mode 名称必须先定义后分派（2026-07-15）

case-aware 能力不仅要求数据合同正确，也要求 loader、summarizer、evaluator 共享同一个模块级模式
规范化函数。当前唯一名称 `_normalize_stage_timing_input_mode` 在三个入口之前定义，避免私有名称漂移
导致运行期 NameError。真实形态回归固定使用 20 case、双层、逐 case frame/time 重置，不再只用单层
或少量 case 间接覆盖。

真实 0.1 P1 只读复测确认两层各 4036 records/20 case、manifest 一致、输入 hash 不变。该事实证明
case-aware P1 接线可运行，不自动证明三档性能比较结论。当前 timing 专项 `28 passed`、D6 全量
`264 passed`。

## Case-aware timing 与冻结机会原则（2026-07-15）

分阶段 timing 有两种不可混用的证据形态。`single_episode` 保持原字段白名单和全流 frame/timestamp
严格递增；`case_aware_suite` 额外且只允许 `case_id/family/profile/seed`，按连续 case envelope
分别校验单调性，case 边界可以重置。suite 汇总只池化同一 scope 的耗时分布，不定义跨 case 时间轴；
main bus/control tick 的 case manifest 必须一致且两层仍禁止相加。

M5N2 frozen contract 不从实际缺项计划反推分母：每 case active-primary pair/target/coalition 固定为
`3/2/1`。actual-execution unavailable、row opportunity 或 intercept active 结构不符，均使受影响 case
指标 unavailable，而不是将缺项记成不存在的机会。standby reserve 不属于 required active primary，
即使 physical success=true 也只能进入排除审计。真实 0.2 已验证 20 case 中 18 match、2 mismatch；
seed006 为 D7 unavailable，seed009 为 D7 available 但机会不符。真实 0.1 P1 状态见顶部；该段仍只
描述 0.2 合同审计。

## ClockSpeed 对比的证据与归一化原则（2026-07-15）

三档对比首先是严格配对问题，不是目录分组问题。D6 要求 ClockSpeed=`1.0/0.2/0.1` 每档都有
baseline/candidate 各 seed 1-10，并按 `case_id/profile/seed` 形成 20 个跨档配对。ClockSpeed 只能
来自 suite/case 持久化 provenance；20 个 result row 的全量一致显式字段属于 case-level
provenance，目录名和 summary 根部裸字段不属于。旧 suite 的 20/20 sibling generated settings 是
路径输入下的封闭兼容证据，不是目录名推断。多处显式值存在时必须一致。

availability 先于数值聚合。任一 profile 的 10 个 case 中有一个指标 unavailable，该 profile/
ClockSpeed 的对应 aggregate 也保持 unavailable，同时报告 available/unavailable case 数；不得用
剩余 9 个 case 的均值冒充完整 10-seed 结果。truth identity/state 分开审计，缺失不是零，显式正值
也不会被其他 case 的零覆盖。

wall timing 保留两个嵌套 scope：main episode bus 内层与 SimpleFlight control tick 外层。D6 分别
报告两层 mean/P95，不产生 cross-layer total。ClockSpeed 归一化 simulated time/tick 定义为
`control_tick_wall_mean_ms / 1000 * ClockSpeed`，只改变单位解释，不把 main bus 再加到 control
tick。case wall elapsed 是另一个独立指标，缺失时保持 unavailable。

第二 primary 按同一 target 内 required active primary 的稳定 `resource_id` 顺序选择第 2 个；五米
结果读取显式 offline physical scorer，最终锁/coalition consensus 读取 episode 终态，collision
stop 只读取显式 stop reason。三者语义独立。运行前 60-case fixture 当时达到专项 `8 passed`、全量
`254 passed`；0.2 阶段 case-aware/合同回归为专项 `27/10 passed`、当时全量 `263 passed`。真实
0.1 P1 与三档 comparator 随后均已完成，最终 availability-aware 结果见顶部。

## 真实 M5N2 多 case 证据判读原则（2026-07-15）

2026-07-15 的正式复核样本是 baseline/candidate 各 10 seed 的 20 个 M5N2 case。M5N2 完成后、
`TERM` 生效前额外完成了 `png_ttc` seed001，但它明确排除在 M5N2 20-case 聚合与验收之外。其余
tuned 2v2 和全部 dropout 未执行；缺失 case 保持 unavailable，不能在本批中解释为失败、零值或
完整 suite。20 个 canonical actual artifact 全部可用，在线 truth identity/state 均为 0；因此
本批可以评价 M5N2 actual 和物理结果，但不能用聚合外 seed001 评价未完成的专项批次。

物理结果必须按统计单位解释：pair `12/60` 表示 60 个 active-primary 资源目标对中的 12 个进入
5 m；target `12/40` 表示 40 个目标机会中的 12 个至少有一个 pair 成功；coalition `0/20` 表示
20 个高威胁联盟机会没有一个满足全部 required primary。三者回答不同问题，不能互相替代。

术语上，target `12/40` 固定称为“规范目标物理成功（canonical target physical success）”，其
语义是至少一个 participating pair 成功；七阶段中“全部 required member 通过某阶段”固定称为
“协同目标阶段诊断（cooperative target-stage diagnostic）”。协同诊断不能改写规范目标物理成功。

第二 primary 的 `assigned/visible/associated/contract=20/20` 只证明这些阶段在 episode 内曾有
有效正证据；`control/mode=17/20`、physical=`0/20` 说明证据在后段收缩。associated 不能解释为
锁定持续到命中。20 个首失败原因都可用，故失败分布是可审计观测，不是缺字段补出的类别。

执行终态和首失败原因是不同证据层。本批第二 primary `20/20` 最终为 `collision_stop`，但没有
collision object，因此只能把对象原因标为 unavailable；不得从终态猜测成员互撞、环境碰撞、
AirSim 状态异常或五米成功。只有 producer 写出对象、时间戳和来源后，D6 才能继续分类。

时序同样按嵌套域解释。main bus 是 control tick 的内部组成，不能把 `349.34 ms` 与
`1069.45 ms` 相加。逐 case 原始流可用并可按 scope 池化；正式 suite 合并流若在 case 边界重置
frame/time，则在单流语义下必须 fail closed。此时应同时报告“逐 case 证据可用”和“suite 接线
unavailable”，不能用池化数值伪装接线已闭合。

## 第二 primary 与独立分母原则（2026-07-15）

D6 将 active-primary pair、target 和 coalition 视为三个不同统计单位。pair 成功只能说明该资源-
目标对完成；target 成功不能证明全部 required primary 完成；coalition completion 必须使用联盟层
自身的显式机会数和成员物理结果。因此三个分母独立，任一层缺证据均为 unavailable，不允许跨层
回填。

第二 primary 以同一成员为单位保留七阶段漏斗。首失败原因必须来自 producer 明确写盘字段；原因
缺失只改变原因 availability，不反推原因类别。该原则经确定性专项 `11 passed`、D6 全量
`246 passed` 验证；其后真实 M5N2 20-case 已按本页顶部完成输入和判读。

## 分阶段延迟证据原则（2026-07-15）

D6 将延迟作为只读证据。`not_applicable` 表示阶段未执行，`error` 表示执行失败但仍有测量值，
二者都不能补成零。每条记录必须满足时间顺序、状态和值、阶段和、总耗时、未归因耗时及预算标志
一致；非法证据 fail closed。

main bus 是 control tick 的内部组成，D6 只在各自测量域内计算分布和主导阶段，禁止跨层相加。
旧日志缺 timing 为 unavailable。该原则最初经 20 个专项和 236 个全量测试验证；随后真实 M5N2
20-case 已确认 `100 ms` 预算未达标。正式 case-aware 接线已关闭，性能优化和跨提交复验仍开放。

## Freshness 必须由最终命令源证明（2026-07-14）

目标状态新鲜度属于 actual execution evidence，不能由 replay、summary 默认值或场景配置推断。
D6 只有在最终 command 的 control/measurement/arrival/age/stale/source 六项逐行完整、一致且 source
hash 通过时才发布统计。缺证据是 unavailable；显式 `False` 是 available stale 0；显式 `True`
是 available 正 stale。三者不得互换。

正式 case 输出样本数、mean/p95/max age、stale count/rate 和 source distribution，并携带
availability/source/semantics。suite 聚合只池化已经过哈希源复算的 age 样本。2026-07-14 真实
2v2/M5N2 为 48/608 samples、stale 均 0，关闭单 seed 正式指标链；随后 M5N2 20-case 已补齐
10389 条同配置 multi-seed 样本，stale=0。跨提交趋势和 failure taxonomy 仍开放。该原则不允许
freshness 改写 physical、五层、truth identity/state 或控制状态。

## 真实证据门与完整 suite 判定必须分离（2026-07-14）

actual execution availability 与完整 P1 suite acceptance 是两层判定。2026-07-14 tuned 2v2
seed-1、M5N2 seed-1 的 canonical required/available/unavailable=`2/2/0`，满足 actual P0 全可用
门；旧 physical-count conflict 未复现并关闭。`overall_acceptance_passed=false` 仅表示两个 case
缺 baseline/candidate 配对、1-5 帧 dropout 全矩阵和 multi-seed，不能被解释为 actual artifact
不可用。

可用性也不能与成功混淆。M5N2 coalition 为 available `0/1`：required member、denominator 和
physical result 均存在，但第二 required primary 未完成五米拦截，所以是可审计的显式失败。
pair `2/3`、target `2/2` 和 coalition `0/1` 必须保留各自分母。性能同理：2v2/M5N2 loop latency
为 `123.3/384.6 ms`，预算违例合计 `231`，有证据但未达门限，仍是 P1。

## Actual-execution 验收与独立到达原则（2026-07-14 真实重跑前复核）

actual execution 是 fail-closed 证据层。每个 required case 只有通过校验的 canonical
`d7-actual-execution-metrics-v2` 才能标为 available；缺失或 explicit unavailable 会令
`actual_execution_all_available=false` 并使 suite 总验收失败。legacy main row 与离线五米物理
结果属于 diagnostics，只能说明离线评分，不能替代、补齐或晋升为 actual envelope。

当 producer 明确 `arrival_coordination_required=false` 时，联盟完成语义为
`independent_required_primary_physical_success`：对每个 required active primary 独立执行五米物理
成功判定，只有全部 required primary 成功才完成该 target coalition，不再要求共同 arrival
window。required-primary denominator/member、physical result 或该开关缺失，以及 summary/pair
冲突时必须保持 `null/unavailable`。

该原则目前只有代码级证据。M5N2 baseline、M5N2 candidate、2v2 PNG-TTC、1-frame dropout 四个
历史真实 seed-1 actual artifact 仍为 `unavailable`，原因均为
`d7_actual_execution_command_physical_count_conflict`；main 需要真实重跑并注册有效 v2 artifact。
2026-07-14 专项 `14 passed, 24 deselected`、D6 全量 `190 passed`。唯一 Matplotlib `Axes3D`
warning 只限制 3D projection，不影响本轮 JSON/CSV/Markdown、二维报告和口径结论；本轮未运行
AirSim。

## 计划身份必须来自实际命令证据（2026-07-14）

最终评估中的计划身份属于 actual execution provenance，不属于 replay 推断结果。D6 只从已关闭的
`control_commands.csv` 提取逐行必填的非空 `plan_id`、正整数 `plan_version`，以及条件必填的
`d4_target_node_id`，形成去重排序的 plan、version 和 owner 集合。只有 effective control 已授权，
且行语义为 secondary/distributed active、execution、reassignment 或显式 execute action 时，
owner 才是 fail-closed 条件。中心授权和未授权 pre-transition/pending 行可无 owner；若整集没有
authoritative owner，owner provenance 为 `unavailable`，不能补造中心 owner。多次重规划产生多个
不同版本是合法历史；同一 plan ID 同时声明多个版本则是来源冲突，整份 envelope 不可用。

每个集合必须携带显式 availability、`control_commands` 来源和冻结 semantics；plan/version 为
available，合法空 owner 集合为 unavailable。validator 在校验
source hash 时重读 CSV；merge 先丢弃 replay 的同名字段，只接受 validator 返回值。该原则不
改变控制授权模式切换、物理命中或 truth safety 的既有定义。2026-07-14 的确定性离线验收为
execution-evidence focused `20 passed`、全量 `184 passed`；该阶段没有运行真实 AirSim。真实
seed-1 provenance 已关闭；本文首节 20-case 又补齐同条件 multi-seed provenance。当前剩余项是
case-aware timing、跨提交趋势和性能复验。

## 执行证据分层原则（2026-07-14）

D6 将“集成重放结果”和“实际飞行控制结果”视为两个不可替代的证据层。重放可以说明算法在离线
记录上给出了什么判断，但不能证明控制权限生效、模式真实切换、物理拦截发生或实时预算得到满足。
因此实际执行层采用三源交叉验证：command CSV 证明逐命令合同和控制授权，intercept summary
证明物理 scorer 结果，final main bus clock 证明循环样本和处理时延。

实际模式切换定义为：

```text
actual_mode_switch(row)
  = mode_switched(row) AND effective_control_authorized(row)
```

从而 `mode_switched_count <= control_allowed_count`。模式字段变化但控制未授权只作为 raw audit，
不能进入执行层。性能均值必须具有正 `frame_count/ticks` 且两者一致；无样本的数值零属于缺证据，
不是零时延。每份来源以 SHA256 固定，suite 消费时重新校验，防止 producer 写盘后变更。

## 2026-07-14 多案例证据的保守聚合原则

terminal closure suite 的证据单位是 `(case_id, seed, evidence_path)`，不是“输出目录附近可能
存在的某个文件”。D6 逐项执行以下判定：路径必须由 main 显式登记；文件必须可读且 JSON root
为 object；D3 必须满足 canonical history schema 和有序记录合同；D7 必须满足执行指标结构并与
case seed 一致。任一步失败只输出 unavailable 和原因，不构造零值。

D3 的 case summary 可在各 case 内计算 latest plan、membership、owner 和 churn；suite 只对
record count 和有明确可加语义的 churn count 求和，不选择一个“代表 latest plan”。D7 raw
`EpisodeMetrics` 可以证明执行文件存在且结构有效，但没有 producer、metric scope、denominator、
lifecycle 的 terminal envelope 时，不能再次计入 contract/control/mode/physical 四层。这样既
避免缺证据假零，也避免 main row 与 D7 raw 文件重复计数。

当前 seed-1 四案例证据表明 D3 4/4 可用、543 records；D7 的实际文件虽已写盘，但原 main row
路径为 null，因此正式结论仍是 0/4 registered。只有 main 通过公开 registration helper 明确
登记后，D6 才接受这些文件。

**状态日期：2026-07-14**

本文说明 D6 当前已经实现并经过仓库证据验证的原理、接口和边界。文中“已实现”仅表示
D6 能够被动读取相应写盘证据并形成指标或报告，不表示上游算法已经达到准入门限，也不
表示 D6 获得任何在线控制权限。

## 2026-07-14 terminal suite 原则补充

- 同名不等于同口径：terminal 指标必须带 producer、metric scope、正 denominator 和
  lifecycle；source/producer/scope/lifecycle 不同就分组，不做跨组 sum、compare 或 overwrite。
- 四层不互推：contract、control、mode、physical 独立；switch gate 不替代 mode outcome，
  planned lock 不替代 D7 execution。
- 零必须有样本：性能 violation=0 或 physical success=0 只有在正分母和完整 evidence 下可用；
  `0/0` 永远是 unavailable。
- 非退化不是有效性：baseline/candidate 都为零且 candidate 未触发，只能是 inconclusive，不得
  promotion。
- 历史必须是真的历史：D3 缺 canonical history、单 snapshot 或坏顺序时，plan/member/owner/
  feedback churn 全部 unavailable。
- seed-level CSV/JSON 与 aggregate CSV/JSON/中文 Markdown 使用同一 availability 和语义组。

上述 D6 consumer/report 于 2026-07-14 通过全量 `154 passed`；没有运行 AirSim。main
`p1_terminal_closure` producer envelope 与真实 multi-seed 证据仍需接线。

## 0.3 2026-07-14 真值状态与物理来源原则

真值身份和真值状态必须分开审计。`truth_identity_online_use_count` 继续表示在线身份泄漏；
`truth_state_online_use_count` 表示在线位置/速度状态使用。严格 D2 estimated-state 路径只有在
summary、command 或 source 提供实际证据时才能报告 available `0`；显式 actor-truth fixture
必须报告正数，不能被 summary 假零覆盖。

离线 physical success 必须同时有 intercept summary、active pair summaries、合法
scorer/fixture source、显式 availability、匹配的 online state source 和逐 pair evidence。
offline scorer 只允许 D2 estimated class，truth fixture 只允许显式 truth fixture class；每个
active pair 必须显式 `physical_evidence_available=true`，并让 `target_state_source` 与 summary
source 完全一致，还必须写出显式 physical 布尔结果或规范 scorer 终态。command-only、
summary-only 或任一 pair 缺结果/证据/来源不一致时，pair/target/coalition 和 physical
count/rate 全部 unavailable，不能用 0 表示。coalition 缺 denominator、required member、arrival
window 或 summary completion 时同样 unavailable；只有证据完整的显式失败才是 available `0`。
command CSV evidence 只用于审计。无 provenance 的旧 status 不得晋升，但可保留为
历史 raw audit。

2026-07-14 以 7 类确定性离线 provenance 场景验证上述门限，seed N/A，D6 全量
`150 passed`，1 条既有 matplotlib warning，未运行 AirSim。该验证只关闭 D6 P0 代码/测试；
迁移前 physical 数值不与新 scorer 批次直接比较，真实 multi-seed AirSim physical evidence 和
target-state freshness 趋势仍为 P1。

## 0.2 2026-07-14 truth tracking 可用性原则

truth-dependent tracking 指标必须先证明 evaluator-side 配对证据存在。RMSE 的证据单位是
同时具有 `global_track_id/truth_id/position/truth_position` 的记录；continuity 还要求非空
truth timestamp sidecar 覆盖全部已配对 track timestamp；IDSW 的证据单位是显式
`truth_id -> global_track_id` 时间历史。缺证据返回 `None/unavailable`，不能用 dataclass 默认
值、merge 或 reporting 补零。合法历史计算结果为零时，特别是 `id_switch_count=0`，必须保留
为 available。

JSON、CSV 和 Markdown 共享 `metric_availability`；显式 unavailable 优先于遗留数值。验证日期
2026-07-14，5 个确定性场景、seed N/A，D6 全量 `137 passed`，仅有既有 matplotlib
`Axes3D` warning，未运行 AirSim。该证据关闭评估语义 P0，不关闭真实 multi-seed
seed/provenance 完整性，也不关闭 D2 lifecycle-D3 churn 的跨源 join；二者仍为 P1。

## 0.1 2026-07-14 第二批 canonical plan history 原则

D3 canonical history 是 main 落盘的只读 episode 证据，wrapper schema 为
`d3_plan_history_v1`，record schema 为 `d3_plan_history_record_v1`。D6 不导入 producer，
不排序修复坏文件，也不从 plan version 猜测 tick 顺序。

有效 history 必须同时满足：记录数不少于 2；record_count 与数组长度一致；sequence index
为非负整数、唯一且严格递增；ordering key 精确等于 `[sequence_index,timestamp]`、唯一且
严格递增；timestamp 有限且不倒退；每条 record 的 schema/version 和 assignment、coalition、
hysteresis、feedback、owner 结构完整；不得携带 truth 字段。任一条件失败时所有历史派生指标
为 unavailable，并保留稳定原因码。

成员变化以相邻 tick 的 target/resource 键比较 role、activation state 和 active 状态。总体
变化对每个成员键每个 transition 最多计一次；primary/reserve 分项按变化前后涉及的角色审计，
不要求两项之和等于总体。`membership_change_records` 只作 producer 审计，不进入 D6 计数。
owner 使用 `(active_plan_owner, owner_node_id)`；soft/hard feedback 使用 record 内显式计数；
coalition version/epoch 比较相邻 coalition ID 映射。

新增输出为 `d3_history_record_count`、history validation status/reasons、总体/primary/reserve
membership change、owner change 和 soft/hard feedback，并保留原三项 version/epoch churn。
旧 snapshot/cooperative-role 不受影响，证据不足继续 unavailable。2026-07-14 专项
`24 passed`、D6 全量 `132 passed`，1 条 matplotlib `Axes3D` 环境 warning；本轮无新 AirSim
物理实验。以下第一批修复和 2026-07-13 更早内容均为历史证据。

## 0. 2026-07-14 第一批 D3 churn 证据原则修正（历史）

D3 churn 是跨时间记录的变化量，不是最终状态属性。D6 只有在 producer 显式提供对应 count，
或至少两条历史记录具有顺序语义并完整提供该指标字段时，才把计划版本、联盟版本、联盟
时期和成员变化 churn 标为 available。显式 `0` 与稳定有序历史的计算结果 `0` 都是有效零；
最终快照、空 mapping、单条无序记录和字段不完整的历史均为 `unavailable`。

通用 `rows/records` 需要统一且唯一的 sequence/index/timestamp 才具有顺序语义；
`plans/history` 序列按历史顺序消费。联盟 version/epoch 必须在各历史记录中完整出现，成员
变化必须逐记录显式写出 change records 或 count。正式 cooperative-role `pair_rows` 没有
时序证据时仍只提供角色统计，不产生 churn。

2026-07-14 以最终快照、空输入、单条无序、两条稳定有序和显式零 5 类 fixture 验收：前三
类四项 churn 全部 unavailable，后两类全部 available `0`；正式 40-case cooperative-role
fixture 的四项 churn 继续 unavailable。专项测试 `12 passed`，D6 全量 `120 passed`，另有
1 条本机 matplotlib `Axes3D` 环境 warning。该评估级 P0 已闭合；真实 D3 有序 history 与
provenance 仍是上游 P1 evidence 缺口。本文后续 2026-07-13 及更早数据均为历史证据。

## 1. 模块定位、问题与边界

### 1.1 模块定位

D6 是系统证据面上的离线评估与报告模块。它接收 D1-D7 和主运行时已经写盘的单次实验
（episode）记录，把不同模块的事件、状态快照、真值裁决和执行结果转换为可追溯的单次
实验指标、批量统计和中文报告。

当前标准输出包括逗号分隔值文件（Comma-Separated Values，CSV）、JavaScript 对象表示
法文件（JavaScript Object Notation，JSON）、逐行 JavaScript 对象表示法文件（JSON
Lines，JSONL）、Markdown 轻量标记文档和便携式网络图形（Portable Network Graphics，
PNG）图表。这里的 PNG 指图像格式；第 3.9 节中的“视觉 PNG”是另一种含义。

D6 的核心价值不是再给系统增加一个总分，而是保留失效结构：探测、跟踪、身份、分配、
联盟、降级、末端配准、通信、导引门控、物理结果、安全和性能预算分别报告。这样可以防止
总体成功率掩盖身份切换、证据缺失、错误重复分配或安全约束触发。

### 1.2 工程问题

D6 回答以下工程问题：

1. 不同模块写出的时间、身份、版本和规模字段能否对齐到同一实验时钟和证据路径。
2. 同一指标的分子、分母、可用状态和来源是否明确，显式零是否被错误地当成缺失值。
3. 执行后结果与执行前合同诊断是否分开，回放估计是否会覆盖真实执行证据。
4. 5 个资源对 2 个目标的 `M5N2` 场景、2 对 2 场景和其他规模能否按实际资源、目标、
   飞行器和相机数量归一化，而不是从场景名猜测规模。
5. 多随机种子（seed）结果能否严格按场景版本、配置档、几何和实际规模成对比较。
6. 所有报告结论能否追溯到源文件、数据模式、生产者、运行标识和散列摘要。

### 1.3 科学问题

D6 支持但不替代上游研究，主要回答以下科学问题：

1. 探测覆盖、定位误差、身份连续性和分配完整性分别对系统结果造成多大影响。
2. 一个目标需要多个资源时，合法协同多分配与异常重复分配如何区分。
3. 中心、二级节点和分布式降级条件下，确认应答、租约、版本、延迟和成员失效如何影响
   联盟提交及安全闭锁。
4. 末端视觉锁定、门控允许、控制允许、模式切换和物理结果之间的漏斗损失发生在哪一层。
5. 多资源协同时，需求满足、到达窗口、成员间距和物理完成能否同时满足，而不是只看任意
   一个资源对的成功。
6. 指标变化是否超过随机种子波动，并且是否满足预先冻结的晋级门限。

### 1.4 明确边界

D6 只消费文件或内存中的离线对象，不参与实时链路：

- 不发布航迹，不创建或重绑定 `global_track_id`（中心维护的全局航迹标识）。
- 不生成分配计划，不拒绝过时计划，不触发重规划，也不改变 D3 迟滞阈值。
- 不发起中心、二级或分布式降级，不提交联盟，不续签租约。
- 不执行视觉关联、相机控制、云台控制、导引或车辆控制。
- 不生成真实火控参数、毁伤逻辑、自动授权、自动处置或绕过人工审核的流程。
- 离线真值、高威胁标签和后验复核标签只用于评分，禁止回流在线系统。
- D6 报告中的门限结论为咨询性证据，不构成控制授权。

## 2. 上游输入、数据结构与下游输出

### 2.1 上游输入

| 来源 | D6 当前消费的证据 | D6 不做的事 |
| --- | --- | --- |
| D1 传感器融合 | 双时间戳、北-东-地坐标系（North-East-Down，NED）位置、协方差摘要、来源谱系、观测接受或拒绝、时延与区域质量 | 不融合观测，不把世界大地测量系统 1984（World Geodetic System 1984，WGS 84）作为融合工作坐标，不修正航迹 |
| D2 数据关联 | 真值离线配对后的身份连续性、身份切换、错误航迹、关联风险、协方差一致性摘要和循环时延 | 不运行关联器，不改写全局身份 |
| D3 分配规划 | 版本化计划、资源-目标绑定、需求数、联盟角色、版本/时期、迟滞拒绝和过时拒绝事件 | 不决定分配，不从最终快照伪造计划变化时序 |
| D4 分布式降级 | 中心/二级/分布式状态、确认应答、租约、故障注入、接管、提交、闭锁、复核标签和窗口统计 | 不仲裁所有者（owner），不主动降级，不解除闭锁 |
| D5 末端关联 | 每主资源可见性、局部航迹、锁定/歧义/友方重叠保持、跨视角注册、原生跟踪结果和离线正确性标签 | 不用真值做在线关联，不本地重绑定全局身份 |
| D7 导引 | 合同检查、控制许可、模式切换、物理结果、拒绝原因、最近距离、末端滤波和短时丢失诊断 | 不选择导引律，不改变门控参数，不下发控制 |
| 主运行时 | 正式执行指标、原始合同指标、场景版本、随机种子、实际规模、证据路径和运行摘要 | 不启动仿真器，不调度实验，不写回运行状态 |
| 仿真与离线裁决 | 微软 AirSim 无人系统仿真器（用于生成无人机、相机和目标仿真日志）的 Blocks 示例场景（AirSim 自带基础环境）记录、移动场景对象（actor）目标元数据、离线真值及人工/规则复核 | 不直接连接实时仿真应用程序编程接口（Application Programming Interface，API），不把 actor 真值身份提供给在线 D5/D7 |

主运行时负责 AirSim Blocks 启停、复位分隔的实验顺序和日志落盘。当前物理飞行实验使用
AirSim SimpleFlight 多旋翼飞行控制后端；目标是移动 actor，而不是额外的 SimpleFlight
飞行器。D6 只在实验结束后读取这些结果。

### 2.2 核心数据结构

1. `TrackRecord`（航迹/探测离线记录）

   - `timestamp`（记录时间戳）；
   - `global_track_id`（中心全局航迹标识）；
   - `truth_id`（仅供离线评分的真值身份）；
   - `position`（估计位置）与 `truth_position`（离线真值位置）；
   - `covariance_trace`（协方差矩阵迹摘要）；
   - `track_state`（航迹状态）与 `association_source`（关联证据来源）。

2. `AssignmentRecord`（版本化分配快照）

   - `plan_id`（计划标识）与 `version`（计划版本）；
   - `resource_id`（资源标识）与 `global_track_id`（目标全局航迹标识）；
   - `authorization_state`（授权记录状态）与 `active`（是否有效）；
   - `coalition_id`（联盟稳定标识）、`coalition_version`（联盟版本）、
     `member_role`（成员角色）和 `required_resource_count`（目标需求资源数）；
   - 到达窗口、波次和成员最小间距等协同评估字段。

3. `TargetDemandRecord`（目标需求快照）

   保存目标需要的资源数、已分配数、缺口、协同模式、联盟和窗口证据，是多资源需求率的
   正式分母来源。

4. `CoalitionRecord`（联盟生命周期快照）

   保存联盟成员、角色、计划版本、联盟 `epoch`（联盟时期编号）、协调者、必要成员、已确认
   成员、提交状态、租约、提交时间、消息数、字节数和共识轮次。该结构用于离线重建状态
   驻留与完成情况，不驱动状态转移。

5. `ArrivalRecord`（成员到达或波次证据）

   保存资源、目标、联盟版本、成员角色、到达时间、到达窗口、波次起止时间和成员间距。

6. `EventRecord`（通用事件）

   通过 `event_type`（事件类型）、`actor_id`（参与者标识）、数值和 `metadata`（结构化附加
   元数据）表达降级、门控、失败、安全、性能和离线裁决事件。

7. `LinkRecord`（通信链路记录）

   同时保留 `sent_timestamp`（发送时间）、`received_timestamp`（接收时间）、
   `measurement_timestamp`（测量产生时间）和 `arrival_timestamp`（消息到达时间），并保存
   序列号、负载类型、是否送达和过时阈值。

8. `TerminalRecord`（末端配准记录）

   保存资源、被分配的全局航迹、局部航迹、决策状态、歧义分数、友方冲突、分配版本、
   评估期望身份和离线关联正确性。局部身份不能替代全局身份。

9. `EpisodeMetrics`（单次实验标量指标）

   保存任务结果、证据范围、实际规模、全部指标、`metric_availability`（逐指标可用性）、
   `m_to_n_metric_availability`（多资源对多目标指标可用性）和审计元数据。数值字段的默认
   值不是证据；加载器和合并器必须结合可用性判断其是否有效。

### 2.3 当前公共接口

- `MetricsCollector`（通用指标收集器）通过 `add_*`/`extend_*` 接收上述记录，并由
  `compute_episode()`（计算单次实验指标）生成 `EpisodeMetrics`。
- `load_episode_log_jsonl()`（读取 D6 标准日志）与 `dump_episode_log_jsonl()`（写出标准
  日志）支持真值摘要和全部记录类型往返。
- `load_blocks_replay_jsonl()`（读取 Blocks 回放日志）从帧记录和传感器记录构建规模、真值
  摘要、探测、末端和通信证据。
- `load_main_episode_bus_metrics()`（读取单个主总线指标文件）和
  `load_main_episode_bus_metric_files()`（读取执行/合同双文件）还原正式指标。
- `load_d4_active_degradation_decisions()`（读取 D4 主动降级决策）以及
  `load_d7_intercept_outputs()`（读取 D7 控制与物理摘要）只执行文件适配。
- `P1SystemEvidenceReportGenerator`（一级收敛系统证据报告器）是 2026-07-13 七源统一报告
  入口；一级收敛优先级（Priority 1，P1）表示项目当前收敛任务，不表示在线权限等级。
- `CooperativeClosureReportGenerator`（协同闭环报告器）、
  `DenseCrossingEvaluationReportGenerator`（密集交叉标定报告器）和
  `NativeMotAirSimReportGenerator`（原生多目标跟踪报告器）分别处理专项证据。
- `merge_replay_with_execution_metrics()`（合并回放与执行指标）为主运行时提供纯函数；D6
  不负责调用后的写盘位置或实验调度。
- `ReportGenerator`（通用报告器）输出单次实验 CSV、汇总 CSV、中文 Markdown、标准映射和
  指标族图表。

### 2.4 下游输出及使用方式

D6 输出只供回归、实验比较、人工评审和报告使用。正式主线包含：

- 单次实验指标与证据可用性；
- 按 `metric_scope`（指标口径）、随机种子、`scenario_group`（稳定场景组）和实际规模分组
  的批量统计；
- 失败原因分布、源文件清单和可复现性摘要；
- 执行结果与合同诊断的并列视图；
- 中文结论与 PNG 图表。

任何下游决策必须由人工或所属控制模块依据其自身合同完成，不能把 D6 的验收布尔值直接
接到在线执行链路。

## 3. 数学模型、指标与算法步骤

### 3.1 记号与证据集合

设一个单次实验中有 $M$ 个资源、$N$ 个目标，实际数量分别来自
`resource_count`（资源数）和 `target_count`（目标数），而不是场景名。对目标 $j$ 的
离线真值机会集合记为

\[
\Omega_j=\{(j,t_k)\},
\]

其中 $t_k$ 是真值采样时间。离线裁决为“匹配”的集合记为 $D$。真正例（True
Positive，TP）、假正例（False Positive，FP）和假负例（False Negative，FN）只在离线
真值机会与配对裁决同时存在时定义。

身份标识（Identifier，ID）在本文分为中心全局 ID、节点局部 ID 和仅供离线评估的真值
ID。三者必须保留命名空间，不能因数值相同而互换。

### 3.2 探测指标

\[
P_D=\frac{TP}{TP+FN},\qquad
P_M=\frac{FN}{TP+FN},\qquad
R_{FA}=\frac{FP}{T_e}.
\]

- $P_D$ 是探测概率；
- $P_M$ 是漏检率；
- $R_{FA}$ 是每秒虚警率；
- $T_e$ 是单次实验持续时间。

实现中，$(truth\_id,timestamp)$ 落入真值机会集合的航迹或显式离线匹配事件形成 TP；
机会集合中没有匹配的项形成 FN；带离线真值标签但落在机会集合外的检测形成 FP。没有
`truth_id`（离线真值身份）的中心航迹不会自动计为虚警，因为它可能只是缺少裁决标签。

只有真值机会而没有任何匹配/漏检裁决时，三项指标均为 `unavailable`（证据不可用），
不能输出零。实验持续时间为零时，虚警率分母无效，也必须不可用。

### 3.3 跟踪、身份与协方差一致性

对 $K$ 个具有估计位置与真值位置的样本，位置均方根误差（Root Mean Square Error，
RMSE）为

\[
RMSE=\sqrt{\frac{1}{K}\sum_{k=1}^{K}
\lVert \hat{\boldsymbol p}_k-\boldsymbol p_k\rVert_2^2}.
\]


其中 \(\hat{\boldsymbol p}_k\) 是估计位置，\(\boldsymbol p_k\) 是离线真值位置。

航迹覆盖连续率为

\[
C_{track}=\frac{|D\cap\Omega|}{|\Omega|}.
\]

身份切换（Identity Switch，IDSW）按同一真值目标的时间有序全局航迹序列计数：

\[
N_{IDSW}=\sum_j\sum_{k>1}
\mathbf 1[g_j(t_k)\ne g_j(t_{k-1})].
\]

其中 $g_j(t_k)$ 是目标 $j$ 在时刻 $t_k$ 对应的全局航迹 ID。D2 与 D6 的硬规则是
`id_switch_count`（身份切换显式计数）必须独立输出，不能被总体准确率隐藏。

协方差一致性使用归一化创新平方（Normalized Innovation Squared，NIS）与归一化估计误差
平方（Normalized Estimation Error Squared，NEES）：

\[
NIS_k=\boldsymbol\nu_k^T\boldsymbol S_k^{-1}\boldsymbol\nu_k,
\qquad
NEES_k=(\hat{\boldsymbol x}_k-\boldsymbol x_k)^T
\boldsymbol P_k^{-1}(\hat{\boldsymbol x}_k-\boldsymbol x_k).
\]

- \(\boldsymbol\nu_k\) 是创新，\(\boldsymbol S_k\) 是创新协方差；
- \(\hat{\boldsymbol x}_k\) 与 \(\boldsymbol x_k\) 分别是估计状态和离线真值状态；
- \(\boldsymbol P_k\) 是状态估计协方差。

当前通用 `TrackRecord` 只直接保存 `covariance_trace`（协方差迹摘要）；D6 不用迹重建完整
协方差矩阵，也不从 RMSE 推导 NIS/NEES。`d2_nis_mean`（D2 的 NIS 均值）、
`d2_nees_mean`（D2 的 NEES 均值）及置信区间内比例只消费上游明确写出的治理摘要。只有
“可用”标记而没有均值时，均值仍为不可用。

### 3.4 分配、目标需求与合法多重性

有效分配首先经过离线证据门控：记录必须 `active=True`（当前有效），且
`authorization_state`（授权状态）属于已记录、已授权、已批准、人工批准或操作员批准。
快照键为 $(timestamp,plan\_id,version)$，因此不同计划版本不能混在同一分母中。

对目标 $j$ 在快照 $s$ 的需求资源数 $k_{js}$ 和有效已分配资源数 $a_{js}$：

\[
s_{js}=\min(a_{js},k_{js}),\qquad
u_{js}=\max(k_{js}-a_{js},0),\qquad
o_{js}=\max(a_{js}-k_{js},0).
\]

- $s_{js}$ 是满足的资源槽位；
- $u_{js}$ 是未满足槽位；
- $o_{js}$ 是超额支持，不能抵消其他目标的缺口。

微平均和宏平均需求满足率分别为

\[
R_{micro}=\frac{\sum_{j,s}s_{js}}{\sum_{j,s}k_{js}},
\qquad
R_{macro}=\frac{1}{Q}\sum_{j,s}\mathbf 1[a_{js}\ge k_{js}],
\]

其中 $Q$ 是有完整需求证据的目标快照数。微平均按槽位加权，宏平均让每个目标快照等权。

一对一旧日志没有需求事件时，只能显式采用 $k=1$ 的兼容规则。具有
`required_resource_count>1`（需求资源数大于一）的当前联盟中，多资源绑定是合法协同，
不能直接计为异常重复。最终 `duplicate_assignment_count`（非法重复分配数）采用需求和
当前联盟授权感知的结果；超过需求、版本冲突、过时或计划外绑定才属于错误。

### 3.5 联盟、波次和主备指标

联盟形成时间和重构时间为

\[
T_{form}=t_{first\ committed}-t_{demand/request},
\]

\[
T_{reconfig}=t_{first\ new\ committed\ version}-t_{trigger}.
\]

前者从需求声明或形成请求开始，到首个满足需求、角色和确认条件的提交状态；后者从成员
失效、摘要冲突或过时版本触发，到新版本首次提交。缺少成对时间戳时不可用，超时不能写成
零。

对明确标记为同时到达的必要主成员集合 $A_j=\{t_{ij}\}$：

\[
\Delta t_j=\max A_j-\min A_j.
\]


`simultaneous_arrival_dispersion_s`（同时到达离散时间）是有效联盟样本的 \(\Delta t_j\)
均值；`common_window_success_rate`（公共窗口成功率）要求所有必要主成员具有到达证据并落在
其分配窗口内。对于序贯波次：

\[
I_w=t_{start,w+1}-t_{complete,w},
\]

且后一波在前一波释放或完成前启动时记一次顺序违反。对混合主备路线，未激活的
`reserve`（备用成员）不能计入需求满足；只有写盘的激活事件、激活时间和当前版本可以形成
备用激活率与延迟。

独立、同时、序贯和主备混合四类路线的**指标合同已经实现**。完整的“四路线乘三个中心
层级乘四类扰动”实验矩阵仍是研究设计，不表示 D3-D7 已实现所有在线控制路线。

### 3.6 D4 降级与联盟提交状态

D6 观察而不驱动以下状态链：中心正常、中心失效、二级候选、二级执行、分布式候选、
分布式执行，以及提交状态 `proposed`（已提议）、`committed`（已提交）、
`executing`（执行中）、`reconfiguring`（重构中）和 `aborted`（已中止）。

同一目标、联盟、计划和时期组成一个同代状态实例（generation）。同代的
`committed -> executing`（已提交转执行中）只计一次有效提交。必要成员确认不全、租约
过期、计划版本过时或联盟时期过时时，上游应闭锁；D6 只统计上游是否按合同闭锁。

失效切换时间为

\[
T_{failover}=t_{degraded\ stable}-t_{central\ failure}.
\]

降级任务完成率为

\[
R_{degraded}=\frac{N_{completed}}
{N_{completed}+N_{failed}+N_{cancelled}}.
\]

主动降级精度为

\[
P_{active}=\frac{N_{reviewed\ necessary}}{N_{reviewed}}.
\]

只有带复核标签、后验结果或冻结前后窗口风险证据的主动降级样本进入该分母。无复核标签的
主动降级只增加总次数，不能默认判为必要或不必要。

### 3.7 D5 末端关联、锁定与身份安全

末端关联准确率为

\[
A_{terminal}=\frac{N_{correct\ adjudicated}}
{N_{adjudicated\ association\ attempts}}.
\]

其中正确性来自离线裁决，不参与在线决策。末端局部身份切换按同一
`assigned_global_track_id`（被分配的全局航迹）对应的 `local_track_id`（节点局部航迹）
变化计数。首锁延迟为首次进入视场到首次锁定的时间差。

D6 观察 D5 的 `observed`（已观测）、`associated`（已关联）、`locked`（已锁定）、
`ambiguous`（歧义）和 `hold`（保持）等决策状态，并分别统计歧义视场、友方重叠保持、
跨视角一致、跨视角冲突和重复锁。它不把普通关联当成共同锁定；共同锁定必须有明确同窗
证据。

对同帧锁集合 $L_{obs}$ 和当前计划授权集合 $L_{auth}$：

\[
N_{planned}=|L_{obs}\cap L_{auth}|.
\]


授权协同锁要求资源属于当前联盟、版本一致、角色已激活且锁数不超过需求。错误重复锁只计
一对一溢出、版本冲突和超需求；同一资源跨帧持续锁定只进入
`same_resource_lock_continuity_count`（同资源锁连续次数），不能当作重复资源。

末端滤波的 `measured`（测量更新）、`predicted`（预测）、`innovation_rejected`（创新拒绝）、
`reset`（复位）和 `expired`（到期）状态，以及短时软预测和短时保持预测（coast）持续时间，
也只由 D6 被动统计。D6 不设置创新门限、保持时长或重新获取策略。

### 3.8 通信、时间和过时证据

完整发送/接收时间对的端到端延迟为

\[
L_{e2e}=1000\times(received\_timestamp-sent\_timestamp)\ \text{ms}.
\]

测量年龄为

\[
A_{measurement}=arrival\_timestamp-measurement\_timestamp.
\]

消息丢弃率为丢弃消息数除以尝试消息数；乱序数由显式乱序事件和同一消息流中序列号倒退
共同形成。轨迹负载的链路时延或测量年龄超过 `stale_after_s`（过时阈值秒数）时，增加
过时更新计数。

联盟通信同时报告消息发送/送达/丢弃数、已知负载字节、共识轮次和延迟。消息大小缺失时，
字节指标不可用，不能从消息条数估算。确认应答（Acknowledgement，ACK）完成率为已确认
必要成员数除以必要成员数；分母为零时不可用。

### 3.9 D7 四层漏斗、视觉 PNG 与物理结果

视觉比例导航制导（Proportional Navigation Guidance，PNG；此处不是 PNG 图像格式）是
D7 的末端导引模式之一。D6 只统计 `visual_png_switch_count`（切换到视觉 PNG 的次数），
不要求保存相机截图。

D7 证据严格分为四层：

1. `contract_allowed`（合同允许）：D3/D4/D5/D7 合同条件通过；
2. `control_allowed`（控制允许）：当前资源被允许实际执行控制；
3. `mode_switched`（模式已切换）：导引模式发生实际切换；
4. `physical_intercept`（物理结果可用且成功）：有明确物理判据证据。

四层各有独立机会数、成功数和可用性。后层成功不能反推前层计数，前层允许也不能推导后层
成功。只有计算机视觉（Computer Vision，CV）状态记录而没有物理执行时，物理结果必须
不可用；执行证据完整但未成功时才是显式零。

物理结果另按三种单位分层：

\[
R_{pair}=\frac{N_{successful\ active\ pairs}}{N_{active\ assigned\ pairs}},
\]

\[
R_{target}=\frac{N_{targets\ with\ any\ successful\ pair}}
{N_{participating\ targets}},
\]

\[
R_{coalition}=\frac{N_{targets\ with\ all\ required\ primaries\ complete}}
{N_{coalition\ opportunities}}.
\]

资源对分母只含已激活且当前有效的分配；未激活备用成员不进入分母。目标成功只要求该目标
至少一个参与资源对成功。联盟完成要求至少两个必要主成员均具有显式物理结果，并满足各自
到达窗口；这不等于“同一时刻到达”，除非场景明确采用同时到达路线。三个比例禁止互相
回填。

当前物理验收判据审计保存 `intercept_radius_m`（拦截半径米）、
`intercept_distance_frame`（距离坐标系）、`intercept_distance_dimension`（距离维度）和
判据版本。2026-07-13 主线使用 NED 三维欧氏距离不大于 5 米；
`collision_intercept`（碰撞阈值成功）和 `range_intercept`（距离阈值成功）都属于物理
成功状态。

碰撞时间（Time To Collision，TTC）分支的面积跳变、边界框裁剪、目标未扩张和 TTC
越界拒绝分别计数。边界框（Bounding Box，bbox）证据来自元数据；D6 不据此生成控制命令。

### 3.10 安全、性能与任务结果

安全指标至少保留 `constraint_violation_count`（约束违反次数）和
`human_override_count`（人工覆盖或拒绝次数）。多资源安全还包括

\[
d_{min}=\min_{t,i\ne j}\lVert\boldsymbol p_i(t)-\boldsymbol p_j(t)\rVert_2,
\]

以及风险阈值内的累计暴露时间。同步成功、目标成功或联盟完成都不能覆盖安全失败。

性能指标消费模块时长、循环时延、记录时延、中央处理器（Central Processing Unit，CPU）
预算利用率、图形处理器（Graphics Processing Unit，GPU）预算利用率和预算违反次数。

任务结果 `mission_outcome`（任务结果）可为成功、部分成功、失败或中止。根因仅从写盘记录
和已计算指标被动派生，按跟踪、分配、末端门控、导引、覆盖、运行异常、通信、安全和性能
等类别报告。它用于解释，不用于在线处置。

### 3.11 计算流程

当前主线算法按以下顺序执行：

1. **加载**：从标准 JSONL、Blocks 日志、模块专项文件或主总线指标文件读取证据。
2. **模式适配**：识别版本化源数据模式；保留路径、生产者、运行标识和原始来源。
3. **时间与身份规范化**：保留测量/到达双时间戳、全局/局部/真值身份命名空间以及计划和
   联盟版本。
4. **确定实际规模**：优先读取真值摘要或场景元数据，缺失时才从记录集合保守推断。
5. **逐指标计算**：分别计算探测、跟踪、分配、多资源协同、降级、末端、通信、导引、
   物理、安全和性能指标。
6. **可用性裁决**：每项输出值、状态、原因、分子和分母；不跨指标补值。
7. **层级聚合**：按帧、成员、波次、联盟版本、目标-实验、实验和批次分层汇总。
8. **执行证据选择**：终端、跨视角、在线真值审计和物理执行字段优先采用主总线明确写出的
   执行值；回放值保留在来源审计中。
9. **统计与报告**：生成逐实验表、汇总表、失败原因、中文报告和二维图表。

### 3.12 选型理由

1. **文件离线边界**：评估与控制解耦，既便于复现，也能阻断离线真值和后验标签回流在线
   链路。
2. **类型化记录加版本化适配器**：不同模块可保留自身生产合同，D6 在边界处显式适配数据
   模式；旧日志缺字段时降级为不可用，而不是静默制造默认值。
3. **可解释指标族而非单一总分**：显式身份切换、错误重复、门控拒绝和安全事件可直接定位
   失效来源，避免被成功率或综合准确率平均掉。
4. **资源对、目标、联盟独立分母**：三种单位回答不同问题，分开统计能防止“一个资源对
   成功”被误写成“全部必要成员完成”。
5. **本地轻依赖主线**：仓库默认测试无需外部大型评估器，便于快速回归；标准多目标跟踪和
   集合距离工具保留为隔离式离线对照，不改变在线算法。
6. **实际规模与严格配对**：按真实资源、目标和相机数分组，并冻结场景版本、几何和随机
   种子，避免场景名称或不等价批次造成伪改善。
7. **逐指标可用性**：不同生产者的证据成熟度不一致，三态语义比统一补零更符合科学统计，
   也能明确暴露上游数据缺口。
8. **固定自助重采样**：在多随机种子证据足够时减少对正态分布的依赖；固定重采样次数和
   随机种子保证报告可复现。

## 4. 统计、可用性和证据治理

### 4.1 三态语义

- `available`（证据可用）：必要字段与分母完整。值可以是零。
- `unavailable`（证据不可用）：必要事件、时间戳、真值、协方差、分母或来源缺失。该样本
  不进入对应比例分母。
- `not_applicable`（策略不适用）：该场景或路线没有此概念，例如无备用角色的路线没有
  备用激活率。

显式零表示“已经观察且事件没有发生”；不可用表示“不能判断”。分母为零时比例不可用，
不能写成零或一。

### 4.2 聚合层级与实际规模

批量分组保留 `drone_count`（飞行器数）、`resource_count`（可分配资源数）、
`target_count`（目标数）和 `camera_count`（相机数）。`2v2`、`5v5` 与 `M5N2` 只是场景
标签，不能推断算法上限、相机数或统计分母。

资源对、目标和联盟使用独立分母；帧级检测数不能直接当作目标数；逐案例（case）行数也不能当作
独立随机种子数。2026-07-13 的协同闭环验收按配置档分组，并在每个配置档内按唯一随机
种子计数，`case_id`（案例标识）只保留审计。

### 4.3 描述统计与区间

通用批量报告提供样本数、均值、样本标准差、中位数、第 5/95 百分位数和基于标准误的
正态近似区间。第 95 百分位数（95th Percentile，P95）常用于循环时延。

2026-07-13 的统一系统证据报告对至少两个显式随机种子的逐种子均值使用固定 2000 次百分位
自助重采样，并使用固定随机数生成器（Random Number Generator，RNG）种子形成 95% 置信
区间。少于两个种子时只给描述性结果，不输出推断区间。当前已经实现该专用自助法；面向
全部长尾指标的通用非参数统计框架仍未实现。

### 4.4 来源和可复现性

统一报告保存源数据模式、文件路径、安全散列算法 256 位（Secure Hash Algorithm
256-bit，SHA-256）摘要、生产者、运行标识和证据来源链（provenance）。报告不导出原始
真值身份，只保留离线聚合结果和在线真值违规计数。

`persisted_frame_count`（实际写盘帧数）与 `warmup_inclusive_frame_count`（含预热帧数）
是两条独立证据，D6 不假设固定相差一帧，也不从其中一个推导另一个。

## 5. 状态机、门控、迟滞、协方差与身份规则

### 5.1 状态机责任

D6 的状态机是**观测模型**，不是执行模型。它根据有序事件计算驻留时间、转移次数、完成率
和失败原因，但所有状态转移均由所属模块或主运行时完成。

| 状态族 | D6 观察内容 | 安全规则 |
| --- | --- | --- |
| D3 计划 | 计划标识、版本、反馈、迟滞拒绝、过时拒绝 | 无真实有序历史时，变化次数不可用 |
| D4 降级 | 中心、二级、分布式所有者，提交/执行/重构/中止，ACK、租约和时期 | ACK 不全、租约或版本失效时应闭锁；D6 只核验结果 |
| D5 末端 | 观测、关联、锁定、歧义、保持、滤波测量/预测/拒绝/复位/到期 | 局部身份不得改写全局身份；普通关联不得冒充共同锁定 |
| D7 执行 | 合同、控制、模式、物理四层，以及短时预测/保持/重新获取 | 四层不互推；无物理证据时物理层不可用 |

### 5.2 门控规则

1. **证据门控**：字段缺失即不可用，不用邻近指标代替。
2. **版本门控**：计划、联盟、时期、租约和角色必须来自同一当前代；D6 不把过时记录并入
   当前授权分母。
3. **角色门控**：只有 active primary（已激活主成员）进入预期物理完成分母；standby
   reserve（待命备用成员）只进入安全与越权审计，除非有显式激活证据。
4. **真值门控**：真值只允许在在线结果落盘后用于离线裁决；在线字段出现 actor 名称、分割
   标识或真值身份会增加违规计数。
5. **物理门控**：CV 状态实验不能被记为物理成功；物理成功必须有明确状态或物理摘要。
6. **晋级门控**：算法是否晋级由预冻结多指标门限决定，不能由单项改善或报告接线完成代替。

### 5.3 迟滞规则

D3 拥有分配迟滞和版本拒绝逻辑。D6 只消费 `d3_hysteresis_reject_rate`（D3 迟滞拒绝率）、
`d3_stale_reject_rate`（D3 过时拒绝率）和反馈接受率。若上游仅提供最终快照，D6 不从版本
总数推导计划变化，也不把成员变化与普通计划刷新混为一谈。

D5/D7 的锁定连续性、软预测和短时保持持续时间是对已发生行为的测量，不是 D6 实现的控制
迟滞。D6 不修改锁定阈值、短时保持上限或模式切换门限。

### 5.4 协方差规则

- D1 输入应保留观测和航迹协方差；D6 的基础航迹记录保存协方差迹。
- 几何退化时，上游增大协方差或拒绝更新都可能是正确安全行为，必须结合 RMSE、NIS、
  NEES、几何拒绝率和下游准备状态解释。
- 没有完整协方差或创新协方差时，不能用 RMSE 伪造一致性指标。
- 缺离线真值时 NEES 不可用；若创新和创新协方差完整，NIS 仍可用。

### 5.5 身份安全规则

- `global_track_id` 是中心或当前合法所有者维护的规范身份；D6、D5 和 D7 不得改写。
- 局部航迹键应包含源节点和局部时期，不能只比较局部数字 ID。
- `id_switch_count` 与 `cross_node_id_switch_count`（跨节点规范身份切换数）均显式输出。
- 合法多资源协同锁与错误重复锁分开；同一资源跨帧持续锁不算多资源重复。
- `truth_identity_online_use_count`（在线使用真值身份次数）、全局身份改写和备用成员越权执行
  是独立安全审计项，不能被成功率抵消。

## 6. 与其他模块和主运行时的接口关系

### 6.1 当前系统默认主线

截至 2026-07-13，系统默认在线主线保持：D1 轻量扩展卡尔曼滤波器（Extended Kalman
Filter，EKF）；D2 全局最近邻（Global Nearest Neighbor，GNN）与匈牙利分配；D3 使用
SciPy 科学计算库（用于数值优化和分配求解）的版本化分配与迟滞；D4 采用中心、二级、
分布式三级保守仲裁；D5 使用 AirSim detect 元数据检测接口进行几何配准；D7 使用位置比例
导航（Proportional Navigation，PN）和视觉 PNG。

这些是 D1-D7 与主运行时的默认能力，不是 D6 的算法选择。D6 的默认主线是本地数据模型、
文件适配器、`MetricsCollector`、专项/统一报告器和可用性治理。

### 6.2 模块接口合同

- **D1 -> D6**：输出 NED 位置、双时间戳、协方差、来源谱系和接受/拒绝统计。D6 形成
  探测、RMSE、覆盖、时延和区域质量指标。
- **D2 -> D6**：输出逐随机种子的 IDSW、连续性、错误航迹、关联风险、NIS/NEES 摘要和
  性能。D6 强制保留身份切换，不改变关联配置。
- **D3 -> D6**：输出版本化计划、目标需求、联盟角色、成员和到达协调。D6 检查合法多重性
  和需求满足；缺有序历史时计划/联盟变化不可用。
- **D4 -> D6**：输出逐时刻故障、所有者、ACK、租约、时期、提交和闭锁。D6 形成故障矩阵、
  切换时间、提交率和安全结果。
- **D5 -> D6**：输出每主资源可见、关联、锁定、共同锁定、跨视角、局部身份和原生跟踪
  证据。D6 的离线真值评分不返回 D5。
- **D7 -> D6**：输出四层漏斗、资源对物理摘要、拒绝原因、最近距离和末端诊断。D6 不由
  模式切换推导物理结果。
- **主运行时 -> D6**：主运行时拥有 AirSim 启停、复位、实验顺序、统一时钟和文件写盘，
  并调用 D6 纯函数或报告器。D6 不扫描实时总线，也不接管调度。

### 6.3 执行与合同双口径

正式 `main_episode_bus_metrics.json`（执行后主总线指标）优先表达实际执行结果；
`main_episode_bus_contract_metrics.json`（执行前合同诊断指标）保留门控和拒绝原因。D6 用
`metric_scope=execution`（执行口径）与 `metric_scope=contract`（合同口径）分组，不把两者
合并成一个“更好看”的数值。

集成回放继续保留离线探测、跟踪和分配指标；终端、跨视角、在线真值审计、合同/控制/
切换和物理字段在主总线有明确执行值时以主总线为规范来源。两侧原值、可用性、路径和最终
选择均保留在 provenance 中。

## 7. 默认主线、可选离线算法与未实现能力

### 7.1 已实现的 D6 默认主线

- 通用记录模型、JSONL 往返、主总线和 Blocks 文件适配。
- 探测、跟踪、显式身份切换、分配、多资源需求、联盟、降级、末端、通信、四层漏斗、
  三层物理、安全、性能和根因指标。
- 按实际规模与证据范围分组的 CSV、JSON、中文 Markdown 和 PNG 图表。
- 七源 `P1SystemEvidenceReportGenerator` 统一报告。
- 密集交叉、协同闭环、AirSim 标定、末端交付（delivery）和原生多目标跟踪专项报告。
- 执行/合同双口径与回放/执行来源合并。
- 固定随机种子的专用自助置信区间和源文件 SHA-256 审计。

### 7.2 已实现但仅限可选/离线对照

1. Python 编程语言的 py-motmetrics 多目标跟踪评估库（用于离线标准指标对照）的隔离
   适配器已经实现冻结数据模式，可输出精确率与召回率调和评分（F-one Score，F1）中的
   身份调和评分（Identity F1 Score，IDF1）、多目标跟踪准确率
   （Multiple Object Tracking Accuracy，MOTA）和多目标跟踪精度（Multiple Object
   Tracking Precision，MOTP）。当前真实后端证据仍只完成最小两帧接线验证，不能替代
   D6 本地主线或 D2/D5 在线路径。
2. 联合概率数据关联（Joint Probabilistic Data Association，JPDA）轻量对照可进入 D6
   报告，但它是研究近似，2026-07-13 实测退化，未替换 GNN/匈牙利默认关联。
3. ByteTrack 多目标跟踪实现和增强型在线实时多目标跟踪器（Bag of Tricks for Simple
   Online and Realtime Tracking，BoT-SORT）已由 D5/主运行时真实运行并由 D6 离线评分，
   但 18 个筛选案例均未通过检测准确性准入，默认仍使用 AirSim detect。
4. 四导引律同随机种子报告器已经实现，但早期单随机种子、短窗口结果只证明接口可用，
   不能作为导引律排序证据。
5. 场景库和随机种子矩阵接口已经实现；它们不等于长期跨提交趋势数据已经建立。

### 7.3 严格未实现或仍开放

- TrackEval 多目标跟踪评估库尚未接入；高阶跟踪准确度（Higher Order Tracking Accuracy，
  HOTA）不可用，不能从现有指标推断。
- Stone Soup 多目标跟踪研究库尚未接入对象转换器或指标生成器。
- 最优子模式分配距离（Optimal Subpattern Assignment，OSPA）和广义最优子模式分配距离
  （Generalized Optimal Subpattern Assignment，GOSPA）尚未进入 `EpisodeMetrics`。
- 多假设跟踪（Multiple Hypothesis Tracking，MHT）没有成为当前 D6 或系统默认实现。
- AirSim 原生录制（recording）通用解析器未实现；实时 AirSim API 接入不是 D6 目标。
- SCRIMMAGE 多智能体仿真平台（用于可选的大规模通信与协同实验）桥接未实现，仅保留为更低
  优先级候选。
- 面向全部长尾指标的统一非参数统计框架未实现；当前只有指定报告器中的自助区间。
- 长期真实多随机种子跨提交趋势、D3 逐时刻计划/联盟变化数据模式、跨批次失败原因词表治理
  仍是 P1 开放项。

上述可选库和研究路线不进入默认依赖、默认七源报告主线或在线控制路径。

## 8. 2026-07-13 验证结果

### 8.1 七源统一报告

正式统一报告已经消费七类写盘证据：D1 1 条汇总、D2 3660 条难度配置记录、D3 40 条协同
案例、D4 60 条通信故障案例、D5 160 条每主资源记录、D5 原生多目标跟踪 18 条，以及 D7
164 条资源对/配置档记录。D7 的 164 条由 160 条资源对/安全记录和 4 条配置档汇总组成，
聚合时不重复计数。

D7 四层显式计数为：合同允许 35、控制允许 7、模式切换 9、资源对物理成功 62。四层数据
均按本层证据读取，没有跨层回填。在线真值使用、`global_track_id` 改写和备用成员越权执行
均为 0，且证据状态为可用。

### 8.2 D1/D2 严格密集交叉

- 目标数 5；相邻目标三维间距分别严格为 4 米和 2 米。
- 每组 20 个随机种子，共 40 个真实 AirSim CV 实验；每个实验 51 帧，不保存截图。
- 评估侧真值样本 10200 条，在线真值泄漏为 0。
- 基线平均 IDSW 为 1.3583，最佳 GNN 候选为 0.6167，下降 54.6%。
- 航迹连续率从 0.9810 提升到 0.9840，绝对提升仅 0.0030。
- 候选 P95 循环时延为 24 毫秒，满足实时筛选预算。

历史 D6 dense-crossing v1 曾要求连续率绝对提高 0.10；该门限在基线 0.9810 时不可达，
现仅保留为 legacy 对照。D2 v2 改用上限感知的剩余误差消除判据：基线 headroom 为
0.0190，所需提升为 0.0019，实际提升为 0.0030，因此连续率单项 gate 通过。D6 只保留
D2 显式策略、gate 和可用性，不自行据此切换算法；历史 artifact 缺少完整 v2 false-track
和逐 gate 证据时，整体 promotion review 仍保持未确认，默认 GNN/匈牙利关联器不变。

### 8.3 D4 实验时钟故障矩阵

正常、中心失效、中心加二级失效、0.5 秒延迟、30% 丢包和网络分区恢复各运行 10 个随机
种子，共 60 个案例。结果为安全结果 60/60，错误降级 0、重复所有者 0、脑裂防护失败 0；
30% 丢包场景中 7/10 按合同闭锁。

这些结果证明实验时钟上的时期、租约、ACK 和闭锁逻辑可以被 D6 正确核验，不代表已完成
真实射频链路、硬件时钟漂移或带宽认证。

### 8.4 M5N2 协同物理闭环

资源数 5、目标数 2，高威胁目标使用 2 个已激活主成员和 1 个待命备用成员。基线与三个
D3 候选配置各运行 10 个随机种子，共 40 个 SimpleFlight 实验。各主成员独立通过门控；
当前判据不要求同时到达，物理成功使用 NED 三维最近距离不大于 5 米。

| 配置档 | 联盟完成 |
| --- | ---: |
| 基线 | 0/10 |
| 20 米 / 3 秒 / 40 度 | 5/10 |
| 20 米 / 5 秒 / 40 度 | 2/10 |
| 20 米 / 8 秒 / 40 度 | 1/10 |

最佳配置档为 `d3-p1-h020.0-w03.0-s040.0`（20 米、3 秒、40 度配置），只达到 5/10，
未达到 8/10 验收门限。四个配置档总体完成 8/40。主要失败原因是 D5 未锁定和末端检测
获取超时，少量案例为 bbox 面积过小。安全侧三个零项保持不变。

### 8.5 D5 原生多目标跟踪准入

多目标跟踪（Multi-Object Tracking，MOT）筛选使用 1920x1080 相机、90 度视场
（Field of View，FOV）、20/30/50 米距离、三组置信度和两个跟踪后端，共 18 个真实
AirSim 案例，每例 101 帧。

20 米时，ByteTrack 和 BoT-SORT 的原生激活率与连续率均为 1.0，IDSW 为 0，P95 时延约
为 7.4/16.2 毫秒；但按交并比（Intersection over Union，IoU）0.5 的离线边界框口径，
精确率/召回率仅约 0.30-0.32 和 0.26-0.33。30/50 米没有有效接受检测。18 个候选均未
准入，确认阶段案例数为 0，默认检测仍为 AirSim detect。

### 8.6 D6 回归与报告状态

截至主线报告，D6 全量回归为 `115 passed`。本机 Python Matplotlib 绘图库（用于报告
制图）的 `Axes3D` 三维坐标轴导入警告不影响本轮二维 PNG 报告。此次文档任务不改变代码
能力状态，因此不以重新运行全量测试作为文档验收要求；仓库既有测试命令仍为：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

### 8.7 已解决问题

1. 七源统一报告已能直接读取主运行时原始 `cases/pair_rows/aggregates`（案例/资源对/聚合）
   数据模式和修正后的协同闭环聚合模式。
2. 协同闭环不再按 `case_id::profile`（案例标识拼接配置档）错误拆成 40 个单随机种子组，
   而是按配置档和唯一随机种子统计。
3. 稳定联盟标识跨滚动版本合并；普通单主成员目标不再进入联盟分母。
4. 执行、合同、回放和执行后证据来源已分开，可审计地选择规范值。
5. 缺失值、显式零和不适用三态已经固定；D3 缺有序历史时变化指标保持不可用。
6. 原生 MOT 是否真实运行、D4 故障是否使用实验时钟、密集交叉几何是否严格为 4/2 米等
   证据缺口已经关闭。

### 8.8 剩余局限

1. M5N2 最佳联盟完成只有 5/10，第二主成员的视觉获取与稳定锁定仍是最高优先级性能问题。
2. D2 候选虽显著降低 IDSW，但连续率增益不足，不能替换默认关联器。
3. D5 两个原生 MOT 后端均未通过检测准确性准入，30/50 米没有有效检测。
4. D4 验证仍是 AirSim 实验时钟故障注入，不等价于真实通信网络认证。
5. D3 缺逐时刻计划历史，成员、计划版本和联盟时期变化指标仍不可用。
6. 长期多随机种子跨提交趋势、门限稳定性和跨批次失败原因词表尚未形成持续证据。
7. 外部多目标跟踪和集合距离评估器仍是可选或未实现能力，不能写成默认主线。

## 9. 中文术语表

| 中文术语 | 英文/缩写或代码名 | 本文含义 |
| --- | --- | --- |
| 单次实验 | episode | 一次具有统一时钟、场景、随机种子和证据目录的运行 |
| 实际规模 | `drone_count/resource_count/target_count/camera_count` | 飞行器、资源、目标和相机的真实数量 |
| 北-东-地坐标系 | North-East-Down，NED | D1 融合和当前物理距离判据的工作坐标系 |
| 全局航迹标识 | `global_track_id` | 由中心或当前合法所有者维护的规范目标身份 |
| 测量时间 | `measurement_timestamp` | 观测对应物理量产生的时间 |
| 到达时间 | `arrival_timestamp` | 消息到达接收端的时间 |
| 均方根误差 | Root Mean Square Error，RMSE | 估计位置与离线真值位置的平方误差均值开方 |
| 身份切换 | Identity Switch，IDSW | 同一真值目标对应的规范航迹身份发生变化 |
| 归一化创新平方 | Normalized Innovation Squared，NIS | 创新相对创新协方差的一致性统计量 |
| 归一化估计误差平方 | Normalized Estimation Error Squared，NEES | 状态误差相对状态协方差的一致性统计量 |
| 目标需求微平均 | `target_demand_satisfaction_rate_micro` | 按需求槽位加权的满足率 |
| 目标需求宏平均 | `target_demand_satisfaction_rate_macro` | 对目标快照等权的完整满足率 |
| 联盟时期 | `coalition_epoch`/`epoch` | 区分联盟所有权和提交代际的单调时期编号 |
| 确认应答 | Acknowledgement，ACK | 必要成员对联盟提交或消息的确认 |
| 迟滞拒绝率 | `d3_hysteresis_reject_rate` | D3 因迟滞规则拒绝分配变更的比例 |
| 证据可用 | `available` | 必要字段和分母完整，显式零有效 |
| 证据不可用 | `unavailable` | 缺必要证据，不能进入分母 |
| 策略不适用 | `not_applicable` | 场景或路线没有该概念 |
| 执行口径 | `metric_scope=execution` | 执行后正式结果 |
| 合同口径 | `metric_scope=contract` | 执行前合同与门控诊断 |
| 视觉比例导航制导 | Proportional Navigation Guidance，PNG | D7 末端视觉导引模式，不是图像文件 |
| 便携式网络图形 | Portable Network Graphics，PNG | D6 报告图像格式，不是导引模式 |
| 碰撞时间 | Time To Collision，TTC | 基于目标图像扩张估计的剩余接近时间 |
| 边界框 | Bounding Box，bbox | 图像中目标矩形范围 |
| 资源对成功 | `pair_physical_success_count` | 一个已激活资源-目标绑定的物理成功数 |
| 目标成功 | target intercept success | 目标至少有一个参与资源对物理成功 |
| 联盟完成 | coalition completion | 目标的全部必要主成员均按各自证据条件完成 |
| 在线真值隔离 | `truth_identity_online_use_count` | 真值只在结果写盘后供离线评分，不进入在线控制 |
| 来源链 | provenance | 指标从源文件、生产者到最终选择值的审计关系 |
| 一级收敛优先级 | Priority 1，P1 | 当前项目收敛任务等级，不是控制授权等级 |

## 10. D2 准入证据的被动评估原则（2026-07-15）

D6 对 D2 准入的职责是“忠实记录”，不是“再次裁决”。v2 gates 优先于两种 legacy checks；
失败必须同时保留 gate 名和可用的具体原因。连续率 baseline、headroom、实际提升、所需提升
和误差消除比例是互相独立的证据字段，任何缺失都保持 unavailable，不能利用公式回填。

`all_thresholds_passed=True` 仅表示 D2 建议进入 promotion review；它不等于控制许可、主线
切换或在线部署。D6 aggregate 直接保留 producer 的 promotion、selected/default path、逐
difficulty assessment、逐 gate reason 和 truth-alignment summary，并固定声明
`producer_decision_recalculated_by_d6=false`。legacy 缺 source-level decision 时对应字段必须为
`None/unavailable`，不能从 IDSW 或 continuity 反推。

2026-07-15 正式冻结 replay 的总体五 gate 通过，但分档仅 clutter/combined 通过；其余四档因
baseline IDSW=0 无可测 reduction evidence 而 fail-closed。dropout screening/confirmation 分别
为 10/20 个 partial case；JPDA research adapter 不准入，默认在线 GNN/Hungarian 未改变。
该 D2-only bundle 的其他六源 unavailable，所以全系统判决是 `not_evaluated`。回归为专项
`31 passed`、全量 `243 passed`，本批未运行 AirSim。

## 11. 三维规模化一致性与身份证据（2026-07-20）

### 11.1 输入边界

D1 与 D2 负责形成规范评估制品，D6 负责验证、归一化和汇总。D6 不访问在线融合器或关联
器内部状态。D1 输入必须是公开 `OfflineConsistencyResult`，D2 输入必须是公开
`Scalable3DIdentityEvaluation`。文件输入还必须由 main 提供外部 SHA-256；只有路径而没有
期望摘要时拒绝读取，D2 路径还必须提供四类完整 expected source hash。

D1 制品同时保留测量时间、到达时间、传感器、距离分档、误差、一致性统计和来源摘要。
D6 校验内部内容摘要，再按 scenario、sensor、range 对公开 aggregation records 分组。D2
制品已经由 evaluator-only observation lineage 形成真值映射。D6 只消费发布后的指标、混淆
矩阵和覆盖计数，不重新匹配全局航迹与真值。

D1 当前规范来源名是 `input_digests.d2_lineage_mapping` 和 aggregation row 的
`d2_lineage_mapping_digest`。旧 `canonical_mapping` 仅用于历史输入兼容；D6 对外 DTO、
逐 seed CSV、aggregate JSON 和中文报告始终归一化为 `d2_lineage_mapping`。新旧字段并存且
摘要不同时 fail-closed，不允许按字段优先级掩盖冲突。

### 11.2 可用性原则

RMSE、NEES 和 NIS 分别有独立 availability 和 sample count。某组只有 NIS 而没有离线真值
时，NIS 可以有效，RMSE/NEES 保持不可用。D2 必须同时满足来源摘要及记录序列验证、在线
真值隔离验证和“未使用身份启发式”三项审计，身份指标才可进入统计。

`id_switch_count=0` 只在 D2 明确给出可用身份评估且 `evaluated_frame_count>0`、存在 truth-frame
证据时成立。制品缺失、lineage 冲突、零帧/无 truth-frame 或真值
隔离未验证时，D6 输出 `id_switch_count=None`、`availability=unavailable` 和具体原因。该
规则防止把“没有评估”解释成“没有身份切换”；对应 truth counts/confusion 也不进入聚合。

### 11.3 规模与统计

episode context 直接记录实际目标、资源、侦察节点和相机数量。5、20、50、100、200 是
验收规模，不是数组长度限制。批量统计按 scenario/version/actual scale 分组，同一 seed 的
重复 episode 先求 seed 内均值，再跨不同 seed 统计。至少两个独立 seed 才输出 95% 自助法
置信区间；单 seed 只给描述统计。

2026-07-20 的验证覆盖五档规模和 14 项专项用例，D6 全量为 `334 passed`。本轮仅证明公共
合同、哈希校验、availability 和报告输出可用，没有运行 AirSim 或正式多 seed，因此不能
据此判断 D1 精度、D2 身份连续率或 200 对 200 性能达标。
