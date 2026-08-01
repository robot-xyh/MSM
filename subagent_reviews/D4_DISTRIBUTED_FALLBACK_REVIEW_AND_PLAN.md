# D4 分布式协同与降级接管综述及子方案

## 2026-08-01 A2 v8 main seed allocation binding 复核

D4 已新增只读 pre-generation gate，把 main 全局 registry 的固定身份、内容/文件 SHA-256
和 `d4-a2-v8-train` allocation，绑定到冻结的 v8 request 与 module seed registry。验证器
严格检查 allocation owner/version/usage/operations、`28100-28423` 精确库存、全局 seed
互斥、source binding、108×3 定向拓扑调度、空 validation/test 和全 false 权限。旧或错
registry、seed 缺失/重叠、schedule 漂移、非 TRAIN 分配或权限越界均失败关闭。

当前结论限于生成前置条件：readiness 为
`generation_prerequisites_ready_no_data_generated`，episode/sample 仍为 0，训练、模型和
运行准入仍为 false。2026-08-01 专项 12/12、D4 全量 947/947 通过；没有新 AirSim 或
物理接管证据。下一步由 main 发布完整 generation schedule 并生成全新 TRAIN 来源，D4
只负责内容审计；通过数据审计前不进入训练。

## 2026-08-01 v7 失败归因与 v8 请求评审

D4 接受本轮诊断为冻结 v7 失败结果的来源独立事后分层，不接受其作为 v7 调参依据或 v8
模型设计结论。固定评价树和候选树均通过内容摘要与前后树摘要检查；JSONL/CSV 128/128
一致。诊断没有执行 v7 actor，不读取正式 seed 或在线 truth/actor/object identity，不
改变候选、权重、阈值、0.60 门、注册或运行状态。

评审确认 validation/test 精确正动作分别为 0/9、0/9。train 的 10 个 actor 激活帧
均为规则负类；7 个没有形成转移变化，3 个形成错误边和虚假转移。投影拒绝、不变量失败、
错误方向和错误数量均为 0。45 个失败帧的阶段归因为 42 个正类未激活和 3 个负类错误边
通过投影，覆盖 45/45。

特征级原因保持 unavailable。原评价记录没有逐区域供需、完整邻接图、节点/边特征和逐边
通信状态，不能判断未激活由输入覆盖、表示能力、训练平衡或通信条件造成。区域编号仅用于
稳定键，不能当作物理正反向。冻结 v4 与外部键零重合仍只覆盖来源 A；来源 B 完整特征未
提供，评审不扩大全训练来源独立结论。

D6 的 128 帧低层独立重算已经完成。D4/D6 逐帧文件字节一致，说明评价可复现；v7 仍因
0/42 精确正动作和三次负类虚假转移失败关闭。此前文档中的 D6 待复核状态不再有效。

评审接受 v8 数据请求冻结。registry 使用全新 TRAIN seed `28100-28423`，324 个请求，
覆盖 8、9、12、16 区域拓扑、不同供需和通信、安全正向、安全反向与困难无转移负类。
三个重复分别冻结 1、2、3 个正类转移资源和同数量的困难负类候选资源。它不是数据集，
也没有生成 episode。旧训练、评价和正式 seed 均显式拒绝，validation/test 留空并后续
从另一全新来源分配。

下一步先由 main 按请求生成 TRAIN 来源，再由 D4 只读审计内容、在线真值隔离、类别和
拓扑覆盖。通过后才能另立 v8 候选。v8 冻结后再请求独立 validation/test；达到非零且
充分的正动作并保持零虚假转移和零安全回归前，不建立置信校准、不读取正式 holdout、
不开放 D3/D7、联盟、控制或物理权限。

本次不改变 AirSim、中心/二级/完全分布式接管和 M 对 N 联盟接口。assist、authority、
assignment、degradation、takeover、coalition、control、physical、D3、D7、production、
registration 和 runtime ACK 权限全部为 false。

新增专项 8/8、D4 全量 921/921 通过。全量仅有既有 Matplotlib `Axes3D` 环境警告。

## 2026-07-31 区域建议发布双层合同评审

D6 clean smoke 证明最终 D3-D4 计划和联盟可以闭合，同时暴露建议发布时序缺口：4 个
重规划 episode 在 v2 发布后仍输出 v1 建议。该 shadow 建议未改变正式决策，但正式
准入必须失败关闭，不能由 D6 后过滤改成有效。

D4 已提供独立 publication gate。`generation_publishable` 使用当前 D4 区域快照逐区域
比较计划标识、版本、authority epoch、lease 和 owner 绑定，并检查快照、回滚和合同
完整性。`planning_consumable` 独立复用 ACK、fault fence、正式裁决、守恒、备用和
transfer 安全门。当前代次但 fault-fenced 的 shadow advice 因而可以进入诊断总线，
同时保持不可采用；真正的 publication rejection 和旧代次仍失败关闭。

发布判定保留时间语义，历史有效 v1 与发布时已过时 v1 分开记录。同身份刷新不续租，
重规划后旧 snapshot 不得回滚为当前代次。两层结果均不改变正式 decision，也不授予
assignment、coalition、takeover 或 control 权限。

专项 10/10、相关回归 75/75、D4 全量 913/913、原 scalable 故障代次定向回归 1/1
通过；D4 全量仅有既有 Matplotlib `Axes3D` 环境警告。D4-owned 代码子项关闭，main
已完成最小总线接线；preplanning/online 时序拆分和 D6 clean 6-cell 复验仍是 formal
R0 前的跨模块 P0。main 必须在旧建议被拒后生成当前计划建议，只抑制旧记录不能满足
6/6 当前建议覆盖。

## 2026-07-31 D3 权威代次合同评审

D4 接受当前 main-D3 发布合同补全。每个首次权威计划现在显式携带中心和区域的
epoch/lease 四项绑定；同身份 no-op 评价重评保留原值、不续租，也不形成新的权威
计划或 adoption ACK。该变化提高了 D6 可审计性，不改变 D4 执行许可判据。

D4 owner 已将过时的“no-op 不含 authority 字段”断言改为逐值比较来源权威消息。
集成文件 6/6、模块全量 903/903 通过。计划版本、epoch、冻结 lease、内容摘要、分区
和必要成员 ACK 仍全部失败关闭。

发布实现子项已关闭。v4 的 `0/100 available` 属于旧制品，新的 v5 批量还未运行。
main 和 D6 需证明字段可用率为 100%，并逐 episode 核对 D3 发布值与 D4 ownership；
完成前，跨模块 P1 仍按“实现完成、批量验证待办”管理。D4 没有新增 P0/P1。

## 2026-07-30 高威胁开发批次 v4 评审

D4 接受 main 的任务证据生命周期修复。当前 D3 计划仍有效时，D2 临时缺轨只触发
计划期航迹 fallback，任务和联盟不再从 D4 快照静默消失。fallback 使用最后可信的
D2 状态、协方差和时间，不使用离线真值；D7 仍要求当前 D2 身份承诺，缺轨目标保持
控制闭锁。

v4 共 100 个高威胁 episode，覆盖 5、20、50、100、200 规模各 20 个种子。有限状态、
在线真值隔离、D3-D4 当前计划对齐和联盟执行闭合均为 100/100。28 个 episode 使用
过 fallback，三个 v3 原失败样本均闭合；权威计划摘要冲突为零。

D4 核心协议未改。旧摘要、旧计划、旧 epoch、过期 lease、错误成员和错误分区证据仍
失败关闭。同身份 evaluation refresh 不再成为第二份权威载荷，执行语义变化必须提升
版本。此前 main-owned P1 的开发态诊断关闭，D4-owned P0/P1 保持关闭。

D6 已完成 v4 独立审计：计划 ID/版本对齐 100/100，644 个当前多成员联盟目标全部
闭合，195838 条通信处置在 100/100 episode 中均为 available/verified。D3 区域
epoch 与 lease 对照字段均为 0/100 available，保留为跨模块开放 P1。

本评审不签署 formal R0。v4 只有 100 个 2 秒 dirty development episode，尚未覆盖
完整 900 项矩阵和长期缺轨/撤销/lease 到期组合。main 需从 clean source 重跑，并
补齐 epoch/lease 对照字段后更新正式结论。D4 no-op 集成专项 6/6、全量 903/903；
测试同步了新权威发布合同，D4 算法未改。

## 2026-07-30 高威胁开发批次评审

以下内容保留 v3 历史诊断，开放项已由上述 v4 开发批次关闭。

100 个 `high_threat_m_to_n` 开发 episode 中，当前计划联盟闭合为 97/100。三个失败
都不是 D4 完整 ACK 提交失败。D3 当前计划保留 `GT3D-000011`，但该航迹从 D2 当前
输出消失后，main 的 D4 快照静默删除对应 task；终态 closure 因缺少整个 commit 将
三个成员全部列为缺失。

seed 1010 和 1013 在删除前已经 committed，且通信拒绝为零。seed 1017 同一
`plan_id/version/epoch` 出现两份载荷摘要，D4 拒绝旧摘要 ACK 符合内容寻址合同。
D4-owned P0 保持关闭；main 快照任务覆盖为开放 P1，D3/main 计划身份不可变性为开放
P0 合同。修复责任不在 D4 owned paths，不能通过放宽摘要校验处理。

## 2026-07-30 第三轮最终评审

D4 owner 对 main 最新 P0 补丁的只读复核通过。plan delivery、ACK、当前计划对齐、
执行闭合和 terminal drain 已形成统一失败关闭链路；旧 plan ID、旧 epoch、错 lease、
fresh coordinator 和真实 digest conflict 均不能获得当前 permission。

二次失效显式桥接回归通过。桥接仅使用 `previous_plan_id` 指向的上一版本，且原始
delivery lease 必须覆盖当前冻结 lease。第三轮 targeted 为 11/11，未发现新的 P0 或
独立 P1。后续由 main 从 clean source 重跑正式 R0，再由 D6 独立审计；旧制品不拼接。

## 2026-07-30 正式 R0 联盟确认评审

D4 owner 对 main 最新 P0 补丁的结论仍为未通过。v2 对齐已经比较 plan ID、version、
authority epoch 和冻结 lease，permission 在三条 authority layer 前统一失败关闭，
排空完成也同时要求当前代次对齐和缺 ACK 为零。旧版本、旧 epoch、排空错代专项和
owner 错 lease 注入均得到预期 hold。

剩余阻断属于 main ACK 证据缓存。缓存键缺少 plan ID，重新装配时未核对 payload 的
plan ID，并把旧 ACK 改写为当前 task 的 plan ID。仅改变 plan ID 的负向注入中，旧
3 个 ACK 被暴露为新计划 ACK；fresh coordinator 可据此 committed。需要把 plan ID
加入缓存键和装配校验。

有状态 coordinator 虽因历史 digest 冲突保持失败关闭，但当前 region 没有 commit；
缺 ACK 统计只遍历已有 commit，返回 0。ownership 与当前代次对齐后，terminal drain
完成谓词仍为 true。缺 ACK 统计必须从当前 D3 多成员 assignment 出发，并要求同代
region/commit 存在、region 可执行、commit 已授权。还需增加 plan-id-only、错 lease、
真实旧 ACK/digest conflict 排空负向回归。上述 P0 关闭前不接受新的正式 R0 全量重跑。

D4 接受 D6 的 900/900 制品完整性结论，并将 28 个严格业务失败保持为安全失败关闭，
不接受把 `collecting_member_acks` 提升为成功。只读复核覆盖全部 28 个失败和同场景
72 个通过样本。

16 个失败由 main 在同一分配周期先运行旧计划 D4、后发布 D3 新计划造成。其余 12 个
计划身份一致；11 个在最后 D4 决策后收到有效 ACK，但中心正常路径没有重评；1 个受
确认重发和 2 秒终止窗口限制。成员集合、epoch 和 lease 没有形成 D4 本地根因，状态机
在再次消费完整有效 ACK 后能够原子提交。

当前 D4 全量回归 903/903。代码未改，正式 R0 未重跑。main 应把计划身份一致性列为
跨模块 P0，把 ACK 事件重评、可靠重发、终止排空和逐消息审计列为 P1。修复后 D6 还需
拒绝最后 D4 决策与最后 D3 计划身份不一致的样本。任何修复均不得降低 required ACK、
版本、epoch、lease、成员身份或原子提交门。

由于修复会改变 D4 最终决策与 D7 门控输入，必须基于新 clean source 完整重跑 900 项，
不得只修补 28 项或与旧结果拼接。详细证据见
`research_modules/d4_distributed_fallback/reports/`
`FORMAL_R0_COALITION_ACK_DIAGNOSTIC_20260730.md`。

## 2026-07-30 v7 来源独立评价评审

D4 接受本轮产物为冻结 v7 的来源独立只读评价，不接受其作为泛化通过、置信校准前置或
生产准入。评价输入固定为 source commit `4a83a373...3aec`、seed 5216-5279、
M16N24、8 区域、64 episode 和 128 帧。train/validation/test 为 90/20/18，规则
正类为 24/9/9。数据集和划分摘要为 `f6c52bdd...ce67` 和
`4179c0a7...215`。

评价器硬绑定候选、source、labeled root、dataset、evidence、derivation、export
summary 和 frozen v4 source。候选、原始来源、标签导出、dataset 和冻结 v4 五棵树
评价前后一致。外部 train/validation/test 的 fit、checkpoint、threshold 和 confidence
calibration 使用数均为 0；候选或输入修改、注册、准入、正式 holdout 和旧评价 payload
读取数均为 0。

行为结果没有建立来源独立正类。train 的 raw activation/transfer change 为 10/3，
exact 正动作 0/24，负类 exact R0 63/66，3 次变化均为虚假转移。validation 和 test
的 activation/change 均为 0/0，exact 正动作均为 0/9，负类 exact R0 分别为 11/11
和 9/9。test actor-derived 正类分母为 0，结果保持 unavailable。

安全结果保持稳定。三个划分的投影拒绝、不变量失败和完整 R0 raw action tuple 偏差均
为 0。该结果说明 R0 节点继承和确定性安全外壳有效，但不能抵消转移残差在独立正类上
完全未激活的事实。评审处置为失败关闭。

冻结 v4 TRAIN+VALIDATION 与外部数据的唯一在线可观测键为 251/92，精确交集为 0。
候选训练来源 B 的完整特征载荷没有提供给本评价器，因此全训练来源可观测键重合状态
仍为 unavailable；评审不把 seed 隔离写成完整特征独立证明。

v7 继续 unregistered、development/shadow only、admission closed 和 rule fallback
required。没有置信校准器；assist、authority、assignment、degradation、takeover、
coalition、control、physical、D3、D7 和生产确认权限全部为 false。D4 评价专项
21/21、全量 903/903 和语法检查通过。D6 后续已完成低层独立重算，结果与 D4 一致；
不允许用本批数据反向修改 v7 或建立校准器。

本次没有改变 AirSim 和 M 对 N 联盟接口。`AIRSIM_INTEGRATION_PLAN.md` 与
`D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md` 已检查，无需修改。

## 2026-07-30 v7 规则节点与转移残差候选评审

D4 接受 v7 为新的未注册开发候选，不接受其作为 v4-v6 的覆盖版本或生产晋级。v6 在
M16N24 外部输入上出现 raw transfer 0 和节点动作偏离 R0。v7 因此取消学习节点动作：
同帧 R0 负责区域储备、侦察、hold、重规划和 authority 绑定，actor 只输出帧级残差
激活、一个有向边和资源数。学习输出仍需通过既有投影和干预不变量。

训练来源固定为冻结 v4 TRAIN 350 帧和 M16N24 TRAIN 89 帧；checkpoint 只使用对应
VALIDATION 75/20 帧。M16N24 TEST 17 帧没有进入 fit、checkpoint 或 threshold。
seed 4016-4079 已作为 v7 development source，后续不能再声称为未见评价。正式
holdout 1000-1019、旧评价 3008-3039 和预留独立评价 5216-5279 在候选构建阶段均未
读取；5216-5279 后续只用于页首来源独立评价。

首版转移残差网络仍在 M16N24 VALIDATION 上激活 20/20 帧，负类 exact R0 为 0/11。
最终结构将帧激活与边方向解耦，并将新域负类门写入 checkpoint。最佳 epoch 137 的
M16N24 VALIDATION 结果为：raw residual activation 6、exact 正动作 2/9、正确有向
残差 2/9、负类 exact R0 9/11、投影拒绝 0、不变量失败 0、R0 节点字段偏差 0。旧域
VALIDATION 为 13/15、13/15、58/60、0、0、0。

fail-closed 复核进一步要求 raw activation 和相对 R0 的实际 transfer change 均非零，
且投影拒绝为 0。节点保持检查改为直接比较完整 `RegionResourceAction` tuple，包含
`resource_quota_delta` 和 reasons。当前 M16N24 VALIDATION transfer change 为 6，
新增门继续通过。

评审接受该结果关闭“节点动作与 transfer 脱节”和“新域验证全激活”两个开发缺口。
不接受来源独立泛化结论。M16N24 TRAIN 正动作仅命中 1/24，VALIDATION 2/9 又参与
checkpoint 选择，证据等级仍是开发验收。原定的冻结 v7 和 5216-5279 只读评价已由
页首评审收口，结果为失败关闭；D6 低层独立复核已完成且不改变处置。D4 不再根据开发或
评价数据修改本候选。

v7 没有置信校准器，固定 0.60 门未应用。候选保持 unregistered、
development/shadow only、admission closed 和 rule fallback required。assist、
assignment、degradation、takeover、coalition、control、physical、D3 和 D7 权限
全部为 false。专项 19/19、D4 全量 882/882 通过。AirSim 和 M 对 N 联盟接口未变化。

最终两次构建逐文件一致。模型内容、训练审计内容、候选 manifest 内容和候选树内容
SHA-256 分别为 `bec99032...0082d`、`1d60fbd1...6385e`、
`fe9b18f6...4f45f` 和 `b143a6bc...a2fa`。

## 2026-07-30 v6 来源独立外部评价评审

D4 接受本次结果为 v6 的来源独立、只读开发评价，不接受其作为模型准入或正式
holdout。候选 manifest、训练审计、模型参数和状态文件内容固定为
`f40064e7...66a83f`、`ebc1334d...4bee9a`、`c09d1719...ba9e6` 和
`e92ea3aa...b6ea8`。评价前后候选树摘要均为 `8c9d0179...1665e7`。

外部数据来自 clean commit `ed9e086e...2801e`，由 clean exporter commit
`9bdbe31d...d88a` 导出。数据包含 M16N24、8 区域、seed 4016-4079、64 个 episode
和 126 帧。train/validation/test 为 89/20/17 帧，规则正类为 24/9/9。三个划分均未
用于 v6 训练、checkpoint 选择或阈值拟合。

冻结 v4 TRAIN+VALIDATION 的 251 个唯一在线可观测键与外部 94 个唯一键精确交集为 0。
外部输入不是 v6 训练数据的重命名或重新切分。在线键只绑定图张量，不绑定 seed、
episode、目标标签或真值。

评价结果显示 v6 在三个 split 上均未输出原始转移。正确有向边和投影后 exact 正动作
均为 0；负类 exact R0 为 61/65、9/11、7/8。不变量失败为 6/6/3，主要由无转移条件下
节点二值动作偏离 R0 引起。错误方向、错误数量、虚假转移和投影拒绝均为 0，这些零值
不能抵消未激活任何转移边的事实。

actor-derived 正类要求投影后存在相对 R0 的可执行差异、通过不变量且无投影拒绝。
当前三划分分母均为 0，对应比率记为 unavailable。v6 没有置信校准器，未校准
`confidence_head` 未用于固定 0.60 门。

评审决定保持 v6 unregistered、development/shadow only、admission closed 和
rule fallback required。全部 assist、assignment、degradation、takeover、
coalition、control、physical、D3 和 D7 权限继续为 false。候选和输入突变均为 0，
旧评价 seed 3008-3039 和正式 holdout seed 1000-1019 均未读取。后续若继续研究，应
另立训练候选；本次外部结果不得用于修改当前 v6。

## 2026-07-29 v6 转移动作学习候选评审

D4 接受 v6 为新的未注册开发候选，不接受其作为 v4/v5 的覆盖或晋级版本。v4、v5、
来源独立评价 seed 3008-3039 和正式 holdout seed 1000-1019 保持冻结。v6 只用
TRAIN 350 帧拟合，VALIDATION 75 帧只选 checkpoint；其他 payload 读取和拟合为 0。

TRAIN 根因审计显示正/零边为 72/3848，v4 截断加权后零边有效质量仍为正边 1.670 倍。
v4 的单个连续边输出同时承担激活、方向和数量，缺少有向边排序和资源数监督。v6 采用
独立激活头、TRAIN 派生正边权重、帧内方向排序和正边资源数损失，同时保持共享输出合同
和确定性投影。

固定结果的 TRAIN/VALIDATION exact 正动作和正确有向边为 58/60、13/15，投影拒绝为
0/0。负类基线动作保持为 255/290、55/60，低于 v4 的 276/290、58/60。负类表示与
R0 无可执行差异，不等于所有帧都没有转移。评审据此认定 v6 已解决训练表示冲突，但
没有证明模型效果提升或来源独立泛化。

两次构建逐文件一致。v6 专项 12/12、D4 全量 855/855 通过。候选继续
unregistered、development/shadow only、admission closed、rule fallback required；
固定 0.60 门不变，全部生产、D3 和 D7 权限为 false。

后续需另立训练版本增加安全正转移、困难负类和有向边拓扑覆盖，优先恢复负类基线动作
保持。actor 冻结后才能新建置信校准器，并由 D6 使用全新来源独立数据盲审。
当前不运行正式 holdout、runtime preflight、D3 successor、D7 权限或物理/AirSim
试验。

## 2026-07-29 v5 来源独立外部评价评审

D4 接受本次评价为来源独立、只读 development 审计，不接受其作为正式验证。输入固定为
M16N20、8 区域、32 个来源 episode、63 帧和 seed 3008-3039。训练 seed 0-99、正式
holdout 1000-1019、设计 pilot 3000-3007 与评价 seed 完全隔离。来源配置、数据、
split、标签推导、v4/v5 候选和评价配置均已内容寻址。

评价器没有使用在线 D4 recommendation 作为教师标签。外部标签由同一快照的确定性 R0
和既有安全投影产生。63 帧中 train/validation 各有 1 个规则安全转移动作。规则正动作
与候选正类不是同一概念。候选正类要求冻结 actor 的可执行签名与规则安全正动作完全一致，
并再次通过干预不变量。

旧候选 TRAIN/VALIDATION 共 425 帧、251 个唯一可观测键；外部数据 63 帧、41 个唯一键。
精确键交集为 0。冻结 actor 在外部数据上产生 16 个相对 R0 的可执行差异，但没有匹配
两个安全正动作。actor-derived 正类为 0，positive denominator unavailable。

v5 得分全部为 0，固定 0.60 门通过 0/63，负类误接收 0/63，规则回退 63/63。评审接受
“当前外部负类拒绝有效”这一有限结论，不接受“独立正类召回合格”“泛化通过”或“候选
可准入”的表述。

D4 实际读取 train/validation/test payload 为 43/10/10，fit、threshold fit、
selection 和 split 修改为 0。main 先前只读检查同一 test 10 条的过程事实单列。正式
holdout 和 pilot 读取为 0。候选树评价前后不变。

当前评审决定保持 v5 unregistered、admission closed、rule fallback required。生产、
D3、D7、接管、联盟和控制权限均为 false。不运行正式 holdout、runtime preflight、
D3 successor 或 D7 权限测试。D6 已独立重算本批制品，样本 43/10/10、规则安全
正动作 1/1/0、actor-derived 正类 0/0/0、63 个得分均为 0、固定门通过 0、负类误接收
0、回退 63/63、旧/新唯一键 251/41 且重合 0、正式 holdout 读取 0，均与 D4 一致。
D4 不根据 test 或 D6 结果修改当前候选、split 或 0.60 门。正类分母仍不可用；若未来
另立候选，需先形成足量来源独立 actor-derived 正类。评价器同时补齐冻结输入树的输出
路径保护，来源、标签和 v4/v5 候选的任意子目录均不得作为输出。新增评价专项 8/8、
与原 v5 专项合计 18/18、D4 全量 843/843 通过。

## 2026-07-29 v4 独立审计与 v5 校准评审

D6 已完成冻结 v4 候选的独立只读审计。候选文件、来源实现、模型、数据、切分和 v3
registry 完整性通过。TEST 只解析 manifest 元数据，候选 payload、builder read、D6
payload read、fit 和 weight fit 均为 0。该审计关闭了完整性和开发指标独立重算缺口。

模型门没有通过。固定 0.60 门下，TRAIN/VALIDATION 正类召回为
0.206897/0.307692，负类特异度均为 1.0，最小越门正裕量只有 0.000504935。v4 保留为
development/shadow 对照，未注册、admission closed、rule fallback required。正式
holdout、runtime preflight 和收益仍未完成。

D4 评审接受一个独立 v5 最小校准实验。v5 不改 actor，不覆盖或重签 v4，也不触碰 v3。
它从冻结 v4 actor 的 pooled latent 生成实际 24 维在线可见特征，用 TRAIN 均值和标准差
归一，再使用固定 11 近邻逆距离得分。冻结 v4 `hidden_dim` 与 v5
`feature_dimension` 均为 24；这是冻结候选配置，不修改通用模型默认维度。输入不含
节点身份、目标身份、seed、未来结果或 reward。

训练数据用途固定为 TRAIN 350 条拟合、VALIDATION 75 条审计。validation 不拟合权重、
门限、超参数或模型，也不参与候选选择；TEST 与正式 holdout payload 不读取。开发门在
实现前固定为两个 split 正类召回不低于 0.80、负类特异度等于 1.0、最小越门正裕量不低于
0.02，固定置信门保持 0.60。

本次 D4 构建的 TRAIN/VALIDATION 正类召回均为 1.0，负类特异度均为 1.0，最小越门
正裕量为 0.400000/0.209319。开发门通过。近邻模型在 TRAIN 上 Brier 为 0，说明它精确
记住了训练 latent；该结果不能作为未见数据泛化证据。

进一步复算显示，VALIDATION 75 条中 42 条 raw graph key 和 latent 与 TRAIN 完全重合。
非重合记录有 20 条最近距离小于 `1e-3`、10 条位于 `[1e-3,0.1)`、3 条不低于 0.1。
最近 TRAIN 标签 75/75 一致，13 个正类中 12 个完全重合。validation 没有参与拟合，
但其来源和输入几何不独立。

D6 已完成 v5 独立只读审计。候选四个 artifact、调用方固定哈希、v4 基线、v3 registry
树、数据用途和原开发门均可复现。TRAIN 全库存评分 self-match 为 350/350；raw
observable key 留组与 latent exact key 留组的 recall/specificity/Brier 均为
`0.965517/0.958904/0.037610440`。validation exact overlap 为 42/75，去除 exact
overlap 后仅剩 1 个正类，因此独立泛化指标 unavailable。

v5 manifest 内容 SHA-256 为 `83192d4f...2c52`。默认加载以
`v5_candidate_unregistered` 拒绝，离线 development loader 才可读取。全部生产权限以及
D3/D7 权限为 false。评审将 v5 重分类为“记忆化开发对照，等待来源独立扰动集”，并固定
independence/generalization evidence 为 false。该结果不关闭低召回 P1；候选保持
unregistered、admission closed、rule fallback required，不跑正式 holdout、不接入
运行权限。定向测试 10/10 通过。

## 2026-07-29 v4 落盘候选不可变评审

D4 已从文件系统重新调用现有 reviewer 和离线 development loader。clean commit
`fd857457...7f848`、manifest 内容 `4f3e9735...7e116`、模型
`33a28060...b9fe5` 和数据 `b31fc43f...7fb8c` 绑定一致。179 个 artifact 的路径和
SHA-256 与 manifest 完全相同，四个实现文件与 Git commit blob 逐项一致。

从冻结 TRAIN/VALIDATION payload 重算 Actor 类别平衡、confidence 类别平衡、可辨识性和
门限指标，结果与训练摘要完全一致。实际非零/零 edge target 为 `72/3848`。候选只复制
TRAIN/VALIDATION episode；TEST payload 未复制、未读取、未拟合。

fixture 继续标为 training-domain smoke，置信裕量约 0.002367，不形成独立泛化或正式
验证证据。全部权限为 false。默认 loader 以 `v4_candidate_unregistered` 拒绝，离线
loader 的注册绑定状态为 false。评审结论是“落盘候选完整性通过，可以保留为后续独立
评估输入；登记、准入、preflight、holdout、运行采用和收益均未通过”。后续 D6 独立
审计与 v5 开发校准结论见本文件首节。

## 2026-07-29 v4 observable-group 置信校准评审（构建前）

该阶段只评审 v4 训练机制，不形成正式候选。外部组合数据的 train 有 60 个安全可执行
差异正例和 290 个 no-op 负例；后续落盘重算确认 3920 条有向边目标中 72 条非零。D4
在 v4 私有路径使用
train-only 有界权重：正 frame 权重 4.833333，非零 edge 权重封顶为 32，负 frame 和
零 edge 权重为 1。通用行为克隆语义未修改。

新 observable-group 数据 SHA 为 `b31fc43f...7fb8c`，272 个模型输入键没有混标或
target conflict。actor 最佳 epoch 107，train 正/负命中为 58/60、276/290，
validation 为 13/15、58/60。两个 split 各有 2 条投影后干预不变量拒绝，记录已保留。

confidence 只从 train 计算权重。正/负标签为 58/292；正类权重 5.034483，16 条动作
不一致负例权重上限 8，14 条可执行错误负例权重为 20.857143、上限 32。置信头结构不变。
损失使用固定 0.60 门及 0.20 对数几率平方间隔，全批学习率为 0.003。

checkpoint 必须在 train 和 validation 同时满足正类与可执行通过数大于 0、负类与动作
不一致通过数为 0。完整复跑有 8 个 epoch 合格，最长连续 7 个。最佳 epoch 66 的
positive/negative/inconsistent/executable 计数为 train `12/0/0/12`、validation
`4/0/0/4`。validation 只做 checkpoint 与验收，test payload 不读取或拟合。

旧 development fixture 的 D2 不确定度对数、视觉可见率和一致率超出新训练域。固定
0.05 OOD 余量正确拒绝该输入。只夹紧越界特征后，置信度为 0.481511 且投影无转移，
不具备安全差异验收能力。

评审接受专用的 4 区域域内代表夹具。夹具按 TRAIN 模型可见张量域中心排序，并固定为
版本化常量；选择过程不读 target、reward、validation、test、seed 或来源身份。构建时
校验模型可见图指纹，随后保持 0.05 OOD、0.60 confidence、确定性投影和同键 R0。只读
复跑的夹具置信度为 0.602367，投影形成 1 条安全转移，且相对 R0 和 source 均有非零
可执行差异。端点从投影结果读取，不依赖区域身份名称。

该模型可见图指纹与 TRAIN 输入键完全相同。评审将其限定为 training-domain smoke，
`independent_generalization_evidence_available=false`，
`formal_validation_claim_allowed=false`。相对固定门的裕量约 0.002367，不能用于
准入、泛化或独立验证结论。manifest 对三个治理字段和裕量计算执行失败关闭校验。

该阶段证据仅为内存训练和只读数据验证。后续 clean build、候选制品和不可变 review 已
完成，状态见本文件首节。D6 审计、D3 successor、物理结果和收益仍未完成。v4 未登记，
全部生产权限为 false；v3 身份和 registry 保持不变。专项 42/42、D4 全量 825/825
通过。

## 2026-07-29 规划权限解耦评审

区域资源不足时，正式 D4 裁决会关闭当前执行。此前区域资源投影器把这项闭锁同时解释为
禁止重规划建议，导致跨区资源候选无法送入 D3 下一周期。评审决定保留当前执行闭锁，
增加独立 planning-only capability。该 capability 只说明中心可以接收聚合建议并重新
规划，不表示现有分配可执行。

接收区对 D3 暴露 `hold=false/request_replan=true`。若继续使用 `hold=true`，D3 会以
`regional_hint_transfer_touches_hold_region` 拒绝任何触及该区的 transfer。执行安全
由独立的 assignment、coalition、takeover、control authority 字段保持全 false，并由
正式裁决、版本、租约和 capability 摘要共同复核。实际故障代际围栏、网络分区和身份类
硬冲突不会进入该例外。

例外范围固定为中心当前 owner/layer 和两个 D3 资源短缺原因。接收区只能接收，不能转出；
源区继续保护 committed resource、10% 备用比例和至少 1 个备用资源。v1 正常路径保持
原序列化和内容标识，v2 才携带规划证明。专项 14/14 和 D4 全量 794/794 已通过。

下一项评审由 main/D3 完成：在 locality-enforced 区域探针中验证 v2 advisory 能形成严格
successor，同时 assignment/control authority 仍为 false。普通场景不要求生成未分配
D4 task，本合同也不依赖该行为。v4 继续保持未登记。

## 2026-07-29 v4 框架评审

main 未接受首版 v4 原型。评审确认三项问题：原型把备用下限从 0.10/1 放宽到 0/0，
把规则转移压力门限从 0.05 提高到 10.0，并由 builder 生成 36 个 dirty episode 后标作
运行数据。原型 artifact 已删除，未登记任何 SHA，也未修改 v3。

D4 已按 main 合同完成框架修订。v4 复用 0.10/1/1.5 秒安全投影和
2.0/0.5/0.05 同键规则。受控 8 区域 fixture 现有 21 个资源和 19 条绑定，源区留有
2 个未承诺资源；转移 1 个后仍保护 1 个备用。专项测试证明该动作可安全表达且区别于
真正 R0，但该动作来自 fixture，不是训练模型输出。

builder 现在只接受外部内容寻址数据集和独立来源证据，只加载 train/validation payload，
并强制两个 split 同时具备合法跨区正例与 no-op 负例。dirty、全正、缺来源 SHA、
test/holdout 参与、动作多样性不足和投影裁剪均失败关闭。未登记 v4 的五项注册摘要为
`None`，默认 runtime loader 直接拒绝。2026-07-29 专项 11/11、D4 全量 780/780 通过，
v3 文件树摘要仍为 `07c770b0...a93a`。

该框架阶段评审结论是“v4 builder/framework 可保留，当时尚无 v4 候选”。后续
observable-group 数据已完成训练、clean build 和 D4 不可变制品审查；当前状态以本文件
首节为准。D6 对 v4/v5 的独立只读审计已完成；开放 P1 包括来源独立扰动集、正式
holdout、preflight、main 准入决策、D3 successor、独立双臂非退化和正收益。AirSim
与既有物理实验结果未受本轮变化影响。

## 2026-07-29 D6 v2b 最终评审

D6 已完成 readiness v3 的 10-seed 隔离双臂审计和 seed 2007 完整 episode 复核。场景
固定为 20 目标、20 资源、2 个侦察节点、8 个区域和 3.2 秒，seeds 为 2003-2012。
原始推理、运行门、安全投影和隔离采用均为 10/10，说明 D4 候选与统一三维运行链兼容。
该证据不是 AirSim 或实飞结果。

D3 后继、development ACK 和 producer 物理摘要只覆盖 1/10；其余 9/10 为
`regional_hint_no_executable_successor`。候选可辨识动作是 0/10。seed 2007 的
advisory、后继、ACK 和 D7 指令可以重放，19 条 D7 控制绑定中 18 条可关联物理窗口。
candidate 与规则臂的 D3 可执行 successor 字段以及 source/successor 的资源—目标和联盟
绑定相同，因此不能把该后继解释为学习动作。`GT3D-000004` 的身份映射缺口由 D2/main
另行审计，D4 不补造 truth。

有界非退化只对已声明的拦截数和最小距离 available/true。两臂没有拦截，逐 seed 最小
距离相同，正收益为 unavailable/false。评审结论是“运行兼容通过、模型收益与晋级未通过”。
全部生产权限继续为 false，候选保留在 development shadow，普通 assist 不开放，规则
回退保持。当前没有新增 D4 P0；P1 集中在可辨识区域动作、完整物理映射、扰动场景覆盖和
正收益证据。

## 2026-07-29 readiness v3 隔离配对评审

D4 已新增独立 `development-v3` control/treatment 合同，固定 seeds 2003-2012。旧配对
schema 继续绑定正式保留 seeds 1000-1019，未把 development pairing 标成 formal
holdout。v3 loader 验证 candidate manifest 文件和内容身份、全部登记制品、bundle、
model state、策略/模型版本、8-region scope 及内嵌运行一致性门。

main-facing 接口返回两臂实际 selected recommendation、advisory contract、完整 paired
evidence 和四阶段状态：raw inference、runtime gate、projection、next-cycle isolated
adoption。固定阈值为 `TTL=1.5`、置信度 0.60、OOD 余量 0.05、预备比例 0.10、预备资源
1、推理超时 50 毫秒。任一身份、scope、置信度、OOD、超时、非有限、动作一致性、投影或
消费检查失败，treatment 选择确定性规则。

该接口与普通 assist 桥分离，不设置 `assist_eligible`。production runtime ACK、assist、
assignment、degradation、takeover、coalition commit 和 control 权限固定为 false。
当前关闭的是“v3 候选不能进入隔离双臂运行合同”的 P1 接口缺口。统一三维两臂 episode、
D3 successor、隔离消费证据、物理窗口和 D6 非退化/收益仍待 main 集成。2026-07-29
定向回归 52/52、D4 全量 769/769 passed；仅有既有 Matplotlib `Axes3D` 环境警告。

## 2026-07-29 readiness v3 名义多 seed 运行评审

main 从 clean commit `83b8869...0226` 加载固定 v3 registry。20v20/8-region seed 2001
和 200v200/8-region seed 2002 各 3 帧，均为 3/3 分布内、3/3 原始推理、3/3 门应用、
3/3 动作一致、3/3 候选许可，规则回退和所有安全异常为 0。两组满足 0.80 分布内比例和
至少 1 次模型评价的开发验收门。

名义预检使用 seeds 2003-2012，每 case 2.2 秒。20v20/recon2 与 200v200/recon8 各有
10 cases、30 frames；分布内、原始推理、门应用、动作一致和门后许可均为 30/30，回退、
真值、安全异常和 blocker 均为 0。两档 JSON 哈希分别为 `5f97c818...53db9` 和
`77a3ef45...d6cf4`。seeds 与训练 0-99、正式保留 1000-1019 无交集。

5v5/2-region seed 2000 的预期拒绝仍是独立适用域结论。名义 10-seed 兼容性已经闭合，
但尚无扰动多 seed、同键规则非退化、可辨识干预、D3 后继、ACK、物理窗口、时延、收益或
正式 holdout 结论，全部权限继续关闭。

## 2026-07-29 readiness v3 评审

main 已对不可变 readiness v2 执行真实 development preflight。5v5/2-region 总线通过，
3/3 帧因 Advisor 的 1.5 秒建议有效期与 v2 bundle 的 1.0 秒合同不一致而规则回退。该结果
说明运行时一致性门按配置失败关闭，也说明离线 validation 接受不能代替运行投影合同核对。
在线真值使用数为 0，formal decision 未改变投影。

D4 新增独立 v3 身份和构建入口。v3 将最小备用比例 0.1、最小备用资源 1、有效期 1.5 秒、
规则权重 2.0/0.5/0.05，以及 OOD/confidence/cap/tolerance
0.05/0.60/0.59/0.10 写入配置和门内容哈希。构建视图、validation 和 Advisor 使用相同
projector/rule 语义。1.0 秒 Advisor、混用 v2 identity、篡改 TTL 或哈希均拒绝。

main 已从 clean commit `4ba2c8a...4114` 构建 v3，D4 独立 review 后将 8 个文件逐字节
登记到新目录。manifest 内容、模型、源码身份、复合数据、split 和登记树为
`7978aec0...ada2`、`ace5df6d...7f52d`、`e260ff2f...4ef`、
`5d174dd3...ee03`、`69ae1b0e...d817` 和 `07c770b0...a93a`。validation 门后
293/344 通过，动作不一致通过 0；在线 truth 使用为 0。

v3/v2 registry 联合专项 13/13、D4 全量 754/754 passed，v2 registry 字节保持不变。
后续单 seed 8-region runtime preflight 已通过，2-region 负例按适用域拒绝；正式评价和
全部运行权限仍为 false。后续名义 10-seed 兼容性也已闭合，扰动与 paired 非退化是
下一阶段。

## 2026-07-28 readiness v2 登记评审

main 已在 detached clean worktree commit `891b542...fea9e` 完成 readiness v2 构建。
D4 独立 review 三来源、全局 seed split、bundle 运行门和权限后，将候选八个文件逐字节
登记到独立 v2 registry。源目录与登记目录的相对路径和逐文件 SHA-256 全部一致，旧候选
未覆盖。三来源按数字 seed 0-99 全局原子切分，正式种子 1000-1019、test payload 和校准
seed 使用数均为 0。

main 指出的验证标签泄漏和运行上下文分裂已经修复。新路径定义为运行时确定性一致性门：
validation 标签只用于统计；Advisor 将自己的 projector、rule policy 和
`formal_decision` 交给同一 helper，门内投影结果直接作为最终候选。bundle 哈希同时绑定
规则/投影配置、OOD 0.05、confidence 0.60、cap 0.59 和 tolerance 0.10。任一上下文
不匹配均在推理前规则回退。

新增门诊断只记录无真值运行事实：原始推理、门应用、动作一致性、原始/有效置信度、门后
候选许可和门拒绝规则回退。main 可将其用于 runtime preflight 分母，不得将其解释为
assist、分配、接管、联盟或控制许可。旧 bundle 不声明该门，既有行为和序列化保持兼容。

validation 共 344 个样本。原始置信度 344/344 越过 0.60，其中动作不一致 51；运行门后
293/344 越过门限，动作不一致通过 0，通过动作一致率 1.0，Brier
0.056837453793788656，规则参考/记录标签 mismatch 为 0，接受结果 true。固定候选内容、
模型、源码身份、复合数据和 split 为 `48148034...3852f`、`ace5df6d...7f52d`、
`331b4f29...92ce0`、`996dbd66...493e` 和 `69ae1b0e...d817`。

registry 专项 3/3、v1/v2/运行门联合专项 37/37、D4 全量 743/743 passed。main runtime
preflight 后续已执行但未通过，失败原因为 v2 TTL 1.0 与实际 TTL 1.5 的上下文不匹配；
正式评价继续关闭，全部权限为 false。

## 2026-07-28 八区域候选评审

D4 已完成 8-region 复合候选的构建、内容寻址登记和专项测试。运行源与动作课程分别绑定
`b06d741b...6158` 和 `7e17aba7...e72`；0-99 按 70/15/15 全局原子切分，
1000-1019 使用数为 0。课程动作在八区域运行几何上由规则策略和安全投影重新标注，没有
直接混用四区域张量，也没有在线真值或未来结果。

候选专用置信度头已获得监督，但 validation 中 51 个动作不一致样本仍越过固定 0.60。
清单因此记录 `confidence_calibration_accepted=false`，shadow failure gate 强制失败。
八区域代表帧无 feature OOD、confidence 0.909641，但 aggregate gate 与实际执行均为
false。该结果支持“训练和审计链可复现”，不支持“候选可运行”。

候选由 clean commit `923f3f6e91af0f85aed446c66420c834d2de63fb` 构建。manifest
文件/内容、模型、源码身份、bundle manifest、复合数据和 split SHA-256 为
`ad5846b1...f5e5`、`52866167...e2f`、`43157f4e...b0ee`、
`f9c52715...53ed`、`824aecf1...b8f`、`ee6bd202...cfd4` 和
`69ae1b0e...d817`。2026-07-28 最终 registry 专项 14/14、D4 全量 720/720 通过。

main development preflight 已完成。5v5/2 区域 3 帧分布内 0/3、raw execution 0；
200v200/8 区域 3 帧分布内 1/3、raw execution 1、candidate-permitted execution 0。
八区域剩余 OOD 只来自 `secondary_readiness`，训练范围 [1.0, 1.0] 未覆盖运行范围
[0.0, 1.0]，24 个节点值中 16 个低于训练下界。两组有限值正常，在线真值使用数为 0。

双源重切分将 raw execution 从 0 提高到 1，但运行分布仍未闭合。需补采真实 8-region、
`secondary_readiness=0` 帧，并修复验证集中 51/315 个动作不一致样本跨过 0.60 的校准
误接收。当前状态为已构建、main preflight 未通过。正式 20-seed/900-cell 禁止，
assist/assignment/takeover/coalition/control 和物理权限全为 false；不得降低 0.60 或
使用 test/reserved seed。

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
