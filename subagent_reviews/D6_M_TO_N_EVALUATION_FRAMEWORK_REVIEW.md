# D6 M 对 N 协同拦截评估框架审查

## 2026-07-22 M 对 N 跨视角配对影子证据

D5 权威 v2 配对影子包含 `high_threat_m_to_n` 场景，并与其余 8 类场景共同覆盖 5、20、50、100、
200 五档规模。每个场景规模单元使用 seed `1000-1019`，总计 45 个单元和 900 帧。D6 按实际
seed、场景和规模重建目录，不从 `5v5` 或 `200v200` 名称推断资源或目标数量。

配对审计确认规则臂与模型臂在全部 74024 条已标注候选边上使用相同图、候选覆盖和标签，逐单元均无
质量退化。该证据只评价跨视角边和簇的配对结果，不替代 M 对 N 的联盟形成、成员到达、五米物理结果、
时延和故障接管指标。高威胁场景中的模型满分也受合成运动或尺度特征近确定性可分限制，不能作为大规模
外部泛化或控制采用依据。

本轮只将 paired-shadow 层标为 `complete`。G1、近端策略优化、辅助模式和控制权限保持关闭，规则回退
保持启用。M 对 N 后续验收仍需独立相机几何和运动扰动下的跨视角复验，并与联盟、运行确认和物理结果
使用不同分母报告。

## 2026-07-20 M 对 N 主动视觉证据审查

主动视觉指标按显式 target/resource/recon/camera 数量归一化，与 2v2、5v5 或 M 对 N 场景名称无关。
每台相机每次命令是评估机会，命令和 ACK 通过完整版本键连接；未 ACK 命令、意外 ACK 和拒绝均保留，
不能只统计 applied 子集。规则、shadow、assist 和物理结果使用不同分母。

M 对 N 下多个资源可能引用同一中心航迹。D6 允许多个合法 command 只读引用同一
`global_track_id`，但每条引用都必须存在于当时最近的 D2 中心航迹集合，并在 ACK 中保持不变。该规则
既不把多资源协同误报为重复身份，也不允许本地相机用另一个编号替代中心编号。缺 D2 快照时引用一致率
unavailable，不能填 0 或 1。

2026-07-20 确定性验证使用实际规模 T/R/Rc/Cam=`6/4/1/5`，并通过双 seed 报告确认聚合不依赖场景名。
主动视觉专项 8 项、scalable 合并专项 `25 passed`、D6 全量 `297 passed`。真实 20-unseen-seed 的 M 对 N
rule/assist 配对尚未执行，因此当前没有主动视觉提升率、物理因果效应或默认路径准入结论。

补充的 6v6 单 seed main-runtime smoke 有 133/133 command-ACK 闭合且全部 applied，证明任意 N 入口没有
按 2v2/5v5 名称分支。该 episode 为 dirty descriptive evidence，不替代 M 对 N 的 20-unseen-seed
配对验收。

## 2026-07-20 Scalable 3D 学习 advice 分层审查

Scalable 3D 的 M/N 规模继续由显式 target/resource/recon/camera 字段决定，不从场景名推断。D3/D4/D5
learning runtime provenance 与 D4 advice 指标按相同实际规模和 seed 分组；至少两个不同 seed 才产生
bootstrap CI，单 seed 不给出模型提升或准入推断。

M 对 N 学习证据按五层审查：bundle loaded、shadow recommendation、assist eligible、control adoption、
physical outcome。前一层不能回填后一层。D4 advice 不改变正式 region failover decision，assist 数和
shadow 输出数不能进入控制成功分母；control adoption 只来自通过完整建议引用与 summary 一致性审计的
main 消费合同及 D3 hint applied。五米 proximity 不作为 advice 的物理效果。

2026-07-20 deterministic fixtures 覆盖 disabled、missing bundle、assist-to-shadow、assist gate、守恒/
非守恒、旧/缺版本、digest 篡改、缺 advice 和 seeds 1/2 聚合；专项 `17 passed`、D6 全量 `289 passed`。
这些结果只验证动态规模无关的 consumer 与报告合同，不是模型验收或 M 对 N 物理性能证据。消费合同
与矩阵专项现为 scalable `40 passed`、D6 全量 `320 passed`；正式结论仍需 main 提供
`repository_dirty=false` 的多规模、多 seed 完整矩阵。

## 2026-07-15 legacy 1.0 provenance 与真实三档审查

旧 1.0 summary 无 ClockSpeed，但 20 个注册 case 的 sibling generated settings 均显式为 1.0。D6 仅
对路径输入且 suite/cases/rows 全无显式值的情形启用此 fallback，要求 20/20 文件和值闭合；目录名、
默认值、缺文件/缺键/冲突/非有限值均不准入。真实 0.2/0.1 仍使用 result row provenance。

三档各 20 case 已形成 20 个完整 M5N2 配对。合同审计 56 match/4 mismatch：0.1 candidate seed007
为 `1/1/0`、seed009 为 `2/1/1`；0.2 candidate seed006/009 为 `2/1/1`，seed006 另有 D7 actual
unavailable count conflicts。四 case 的相关聚合不可用，reserve 不计 active-primary；truth identity/
state 全 0，main/control 仍分层。专项 `18 passed`、D6 全量 `272 passed`。当前证据支持报告可用的
baseline 与 1.0 aggregate，但不支持用 0.1/0.2 candidate 部分值判定性能提升。

## 2026-07-15 ClockSpeed=0.1 P1 NameError 回归审查

timing mode helper 已前置并统一命名，20-case 双层 case-aware evaluator 回归直接覆盖真实 merged
suite 调用。真实 0.1 main/control 各 4036 records、20 case，P1 v6 只读生成成功，manifest match，
输入 hash 不变。专项 `28 passed`、全量 `264 passed`。该结论只关闭 D6 P1 接线异常；M 对 N 分层、
固定机会合同和 reserve 排除口径不变。该段记录紧急修复当时状态；三档 comparator 随后已完成。

## 2026-07-15 ClockSpeed=0.2 case-aware 与冻结合同审查

case-aware timing envelope 已实现：merged suite 只接受四个 case metadata，逐 case 单调、边界可
重置，case 不得重现；main bus/control tick manifest 对齐且不相加。真实 0.2 两层各 6567 records、
20 case 的 P1 v6 只读复测通过，输入 hash 未改变。

M5N2 机会不随实际缺项计划缩小，固定 pair/target/coalition=`3/2/1`。真实 0.2 中 candidate seed006
因 D7 actual unavailable 和 `2/1/1` 标为 contract mismatch；其 standby reserve success 不计
active-primary。candidate seed009 虽 D7 available，也因 `2/1/1` 标为 mismatch。审计总计 18 match/
2 mismatch，受影响指标 unavailable。该 0.2 阶段专项 `27/10 passed`、当时全量 `263 passed`。0.1
P1 状态见顶部，本节不预写三档性能结论。

## 2026-07-15 M5N2 ClockSpeed 三档对比审查

D6 新入口只接受 ClockSpeed=`1.0/0.2/0.1` 三个完整 M5N2 suite，每档 baseline/candidate 各 seed
1-10；suite 内和跨档都按 `case_id/profile/seed` 校验。family/resource_count/target_count 必须显式
为 M5N2，不从名字推断。ClockSpeed 必须来自 suite/case 持久化 provenance；目录名和根部裸字段
不能参与分组，多来源存在时必须一致。

M 对 N 口径继续保持 pair/target/coalition 独立分母。第二 primary、最终锁、coalition consensus
和 collision stop 从 required active-primary 终态读取；缺字段保持 unavailable。main bus/control
tick 分层报告，禁止相加；归一化 simulated time/tick 只用 control tick wall mean 乘 ClockSpeed。
truth identity/state 分开审计，不把缺失补成零。

2026-07-15 的验证样本是三档各 20 case、总计 60 case 的确定性 fixture，门限是完整配对、
provenance、availability、truth 正负例及 nested timing 语义全部通过；结果专项 `8 passed`、全量
`254 passed`。该段是运行前记录；真实三档 comparator 随后已完成，availability-aware 结果见顶部，
不会覆盖既有 ClockSpeed=1.0 单档证据或把 unavailable 的 candidate 指标写成结论。

## 2026-07-15 M5N2 20-case 正式复核

本批只有 M5N2 baseline/candidate 各 10 seed，共 20 case。actual execution
required/available/unavailable=`20/20/0`，truth identity/state 在线使用为 0。M5N2 完成后、`TERM`
生效前额外完成的 `png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned 2v2 和
全部 dropout 未执行；缺失 case 不计入机会数、不把 unavailable 写成 0，也不宣称完整 suite 通过。

正式三层物理结果为 pair=`12/60`、target=`12/40`、coalition=`0/20`。baseline 和 candidate
各为 `6/30`、`6/20`、`0/10`；逐 seed non-degradation=false。第二 primary 漏斗通过数依次为
`20,20,20,20,17,17,0`，对应阶段分母全部为 20。首失败原因 availability=`20/20`，以预测窗
过期 10、视觉获取未稳定 6 为主；最近距离均未进入 5 m。因此 coalition 零是 available failure，
不是缺证据。

术语统一为 canonical target physical success（至少一个 participating pair 成功，本批 `12/40`）
和 cooperative target-stage diagnostic（全部 required member 通过某阶段）。后者不等于正式
`target_intercept_success`。此外，第二 primary `20/20` 最终为 `collision_stop`，但 collision
object 未落盘，不能归因为成员冲突、环境碰撞或 AirSim 状态问题；对象原因保持 unavailable。

main-bus/control-tick 各有 3805 条逐 case 合法 timing，mean/P95/max 分别为
`349.34/487.40/1305.99 ms` 和 `1069.45/1254.06/2072.51 ms`。两层嵌套，禁止相加。当前正式
partial acceptance 没有注册 timing path，合并 JSONL 又保留局部 frame/time 重置，故 suite 层
保持 unavailable。case-aware timing 接线已由顶部关闭；剩余 P1 是性能优化、第二 primary/coalition 物理闭环
和 candidate 稳健性；D6 consumer 本身无新增 P0。

## 2026-07-15 第二 primary 漏斗与独立分母审查

`d6-cooperative-closure-v3` 将第二 primary 从单一最终失败计数扩展为七阶段漏斗，同时继续把
pair、target、coalition 作为三个独立统计单位。每层分别发布 unit、有效机会、不可用机会、成功、
失败和 rate；coalition completion 只由该层显式物理结果计算。任何层缺证据均保持 unavailable，
不能由相邻层补值。

首失败原因是 producer 字段的被动聚合。失败单元缺原因时记录 reason unavailable/partial 及缺失
数量，不使用 `unspecified`。2026-07-15 确定性专项 `11 passed`、当时 D6 全量 `246 passed`。
代码级 P1 报告缺口关闭；其后 20-case 真实结果已由本页顶部回填，性能仍未达标。

## 2026-07-15 M 对 N 分阶段延迟评估接线

D6 现按真实 timing 帧数分别统计 main bus 与 control tick，不从 M/N 或场景名推断规模。两层为
嵌套测量域，禁止相加；旧或未注册 timing 为 unavailable。2026-07-15 动态规模无关 fixture
专项 `20 passed`、当时全量 `236 passed`。其后 20-case M5N2 已定位主导阶段并确认 `100 ms` 未
达标；正式 suite 的 case-aware timing 接线已关闭，优化后复验继续开放。

## 2026-07-14 M 对 N actual target-state freshness/stale 关闭结论

M 对 N actual evidence 现按每条最终 command 的 control/measurement/arrival/age/stale/source
评估目标状态新鲜度，不从 M/N 场景名或 physical pair 推断。canonical case 输出 samples、
mean/p95/max age、stale count/rate 和 source distribution；validator 在 SHA256 通过后从 CSV 重算。
任一缺列、非法数值、时间/age 冲突、非法 stale 或空 source 使整个 case unavailable。

2026-07-14 真实 M5N2 seed-1 为 608 samples、mean/p95/max=`0.091118/0.2/0.2 s`、stale 0、
`d2_estimated_global_track:608`；对照 2v2 为 48 samples、`0.0375/0.2/0.2 s`、stale 0。两 case
均通过 source-hash 复算，D6 全量 `216 passed`。该指标不生成 physical pair、不改写 coalition、
末端五层或 truth 结论。单 seed 链关闭；顶部 20-case 已补齐 10389 条同配置 multi-seed freshness
样本。跨提交趋势、failure taxonomy 和独立批次复验仍开放。

## 2026-07-14 M5N2 actual v2 真实证据结论

真实 AirSim M5N2 seed-1 与 tuned 2v2 seed-1 的 canonical actual artifact 均通过 D6 校验，
suite required/available/unavailable=`2/2/0`。两例 summary/CSV/actual 物理成功计数均为
`2/2/2`，旧 `d7_actual_execution_command_physical_count_conflict` 未复现，actual P0 证据门关闭。

M5N2 分层结果为 pair=`2/3`、target=`2/2`、coalition=available `0/1`。required-primary
成员和分母均存在，因此 coalition 零是显式失败而非 unavailable；第二 primary 最近约
`11.02 m`，不能用 target 层成功回填。`overall_acceptance_passed=false` 只表示两个 seed-1 case
不构成 baseline/candidate、1-5 帧 dropout 和 multi-seed 的完整 P1 矩阵。

M 对 N 性能 P1 也未关闭：2v2/M5N2 loop latency=`123.3/384.6 ms`，budget violations
`19/212`、合计 `231`。本节是 2026-07-14 单 seed 结论；顶部 20-case 已补齐同配置 multi-seed，
但第二 required primary 物理闭环和时延预算仍未关闭。本次不增加同步到达算法，也不修改 D6 代码。

## 2026-07-14 M 对 N actual gate 与独立到达最终语义（真实重跑前历史）

M 对 N formal suite 对每个 required case 只接受通过校验的 canonical
`d7-actual-execution-metrics-v2`；缺失或 explicit unavailable 时 suite 总验收 fail closed。legacy
main row 与离线五米结果仅 diagnostics，不得替代 actual envelope。

`arrival_coordination_required=false` 不是“coalition 不评估”，而是按每个 required active primary
独立五米成功评分；全部 required primary 成功才完成该 target coalition。required-primary
denominator/member、physical result 或 coordination 字段缺失，以及 summary/pair 冲突时仍为
`null/unavailable`。这只关闭既有独立到达分支口径，不增加同步到达窗口性能算法。

2026-07-14 代码级专项 `14 passed, 24 deselected`、D6 全量 `190 passed`；唯一 Matplotlib
`Axes3D` warning 仅限制 3D projection，不影响本轮 JSON/CSV/Markdown、二维报告或结论。没有
运行 AirSim。M5N2 baseline/candidate 及同 suite 的 2v2 PNG-TTC、1-frame dropout 四个历史真实
seed-1 actual artifact 仍为 `unavailable`，原因均为
`d7_actual_execution_command_physical_count_conflict`，main 必须真实重跑并注册有效 v2 artifact。

## 2026-07-14 M 对 N owner provenance 最终语义

M 对 N actual command 的 plan ID/version 仍逐行必填，但 owner provenance 可以 unavailable。中心
effective-authorized 行和未授权 pre-transition/pending 行不因空 owner 失败；只有
effective-authorized 且属于 secondary/distributed active/execution/reassignment，或显式 execute
secondary/distributed action 的行缺 owner 时 fail closed。这样保留真实接管 owner 证明，同时不
为中心路径补造 `d4_target_node_id`。

2026-07-14 确定性离线验收（seed N/A）为 execution-evidence focused `20 passed`、D6 全量
`184 passed`，1 条既有 matplotlib warning；未运行 AirSim，不形成新的 M5N2 物理结论。

## 2026-07-14 M 对 N actual plan provenance 补充

M 对 N episode 可包含多个不同 plan/version/owner，D6 v2 actual envelope 会按 command rows 去重
保留；它不把“多个版本”本身判为错误。错误条件是同一 `plan_id` 绑定多个 version、字段缺失/
非法，或 envelope 与 hashed CSV 不一致。merge v3 不从 replay 恢复这些字段，因此最终 coalition
评估的计划身份具有 actual provenance。

该能力于 2026-07-14 通过 focused `24 passed` 和 D6 全量 `180 passed`；该代码阶段没有运行
真实 AirSim。M5N2 seed-1 注册已由顶部证据关闭，同条件 multi-seed provenance/趋势仍为 P1。

## 2026-07-14 M5N2 terminal suite 先前四案例证据状态

新的 case evidence 聚合已覆盖当前 M5N2 baseline/candidate 与同 suite 的 2v2 专项，不从场景名
推断规模。M5N2 两个 case 的 D3 canonical history 分别为 244/241 records，均保持 2-primary +
1-reserve membership 证据；suite 连同两个 2v2 case 共 543 records。D7 原 summary 未登记执行
文件路径，因此 M5N2 D7 evidence 仍 unavailable，不能用相邻目录中实际存在的文件替代正式
wiring。

D6 侧 P1 consumer 已关闭并通过全量 `159 passed`。M 对 N 下一步验收仍要求 main 对每个 case
显式注册 D7 path，之后按 case/seed 检查 primary/coalition execution；缺失路径、schema mismatch
和 seed mismatch 必须保持 fail-closed。新增同步到达窗口性能指标仍不进入本轮范围；
`arrival_coordination_required=false` 的独立五米完成语义以本文最新章节为准。P2/P3 计划不变。

## 0.6 2026-07-14 terminal suite 多层语义闭合

M 对 N terminal suite 现在要求每个 contract/control/switch/mode/physical count 携带
producer、metric scope、正 denominator 和 lifecycle。main planned cooperative lock 与 D7
terminal execution 即使同名也分组；多个语义组时不产生跨组总和。pair、target、coalition
继续使用各自 physical denominator，并携带统一 physical producer/scope/lifecycle。

D3 canonical file input 在 terminal suite 中输出 plan/version、primary/reserve 成员、owner 和
feedback churn；缺历史 unavailable。性能 0 需要正 sample count。candidate 多 seed 非退化还
必须有机制触发和效果证据；baseline/candidate 双零且 trigger=0 时只能 inconclusive。

2026-07-14 file-only 回归全量 `154 passed`，未运行 AirSim。D6-owned P1 口径已关闭；main
`p1_terminal_closure` 仍需接入 envelope、D3 history、D7 execution、performance sample 与
candidate effect，真实 multi-seed M 对 N 结论仍开放。

## 0.5 2026-07-14 truth-state 与 M 对 N physical provenance

M 对 N 的 pair/target/coalition physical 分母现共享同一严格 gate：summary 与 active pair
summaries 必须同时存在，command-only/summary-only 不进入分母；合法 offline scorer 或显式
truth-state fixture source、summary online source、逐 pair `physical_evidence_available=true` 与
逐 pair `target_state_source` 必须一致。command CSV evidence 只审计，不生成 physical pair。
每个 active pair 还必须写出显式 physical result 或规范 scorer 终态；仅 evidence=true 不进入
可用分母。required-primary 数量超过实际 persisted members、arrival coordination required 时缺
arrival window、缺 coalition
denominator 或 summary opportunity 缺 completion 时 coalition 为 null/unavailable；完整显式零
保持 available `0`，standby reserve 仍不进入分母。
`truth_state_online_use_count` 与既有 identity count 分离，strict 路径为 available `0`，fixture
为 `>0`。无来源历史 pair status 不进入 M 对 N physical 分母。

2026-07-14 使用既有 provenance 矩阵并新增 7 项 result/coalition completeness 场景验收，
seed N/A，D6 全量 `150 passed`，1 条
既有 matplotlib warning，未运行 AirSim。该结果只关闭 D6 physical provenance P0 代码/测试。
迁移前 M5N2 physical 数值只保留历史口径；单 seed freshness/stale 正式链已关闭，新 schema 的
真实同条件 multi-seed M5N2 重跑与 freshness 趋势仍为 P1。

## 0.4 2026-07-14 truth tracking availability 对齐

M 对 N 报告中的 RMSE、continuity 和 D2/D6 显式 IDSW 现在遵守同一证据规则：没有
truth-to-track pair 是 null/unavailable，完整 identity history 中的零切换才是 available `0`。
collector、JSON/CSV/Markdown、main-bus load 和 replay/execution merge 不再把默认或遗留零
升级为观测证据。

2026-07-14 采用 5 个确定性场景、seed N/A 验收，完整 stable/switch 的 IDSW 分别为
available `0/1`，truthless 场景不进入统计；D6 全量 `137 passed`，1 条既有 matplotlib
warning，未运行 AirSim。该 P0 已关闭。真实 seed/provenance 和 D2 lifecycle-D3 churn join
仍为 P1；M 对 N 外部 benchmark P2 状态不变。

## 0.3 2026-07-14 canonical D3 history 回填

M 对 N membership churn 已从“等待真实有序 producer schema”推进为 D6 可消费 canonical
history：每 tick assignment 以 `(target_id, resource_id)` 为成员键，以 role、activation
state、active 为状态。相邻状态变化形成总体 membership count；变化涉及 primary/reserve 时
进入对应分项。`membership_change_records` 仅供审计，重复出现不重复计数。

同一 validated history 还提供 plan version、coalition version/epoch、active owner/node、
soft/hard feedback。wrapper/record schema、record count、sequence/order key、timestamp 或结构
校验失败时全部 history-derived 指标 unavailable，并输出原因。旧 cooperative-role 只有角色
快照时仍不能产生 churn。

2026-07-14 专项 `24 passed`、D6 全量 `132 passed`，1 条 matplotlib `Axes3D` 环境 warning；
无新物理 AirSim 实验。剩余 P1 为真实 multi-seed episode 趋势和 failure taxonomy，P2 optional
外部指标不变。CLI 使用 `--d3-plan-history`，Python API 仍传
`P1SystemEvidenceInputs.d3_assignment_churn`。以下 0.2 及更早小节为历史记录。

## 0.2 2026-07-14 D3 churn availability 修正

M 对 N 的 coalition/member role 最终快照可以证明当时成员结构，但不能证明跨计划周期的
churn 为零。D6 现要求 producer 显式提供 count，或至少两条顺序明确且 version/epoch/
membership change 字段完整的历史记录，才计算 plan、coalition version、coalition epoch 和
membership churn。稳定有序历史和显式零为 available `0`；最终快照、空 mapping、单条无序
记录及不完整历史为 unavailable。

2026-07-14 使用 5 类 fixture 验收，前三类四项全 unavailable、后两类四项全 available
`0`；正式 40-case cooperative-role fixture 的角色计数保持兼容且 churn 全 unavailable。
专项 `12 passed`，D6 全量 `120 passed`，1 条 matplotlib `Axes3D` 环境 warning。该评估级
P0 已闭合；真实有序 D3 history/provenance 仍是 P1 evidence，外部 MOT/OSPA/HOTA 等仍是
P2 optional。D6 只消费日志的边界不变。以下 2026-07-12 及 2026-07-11 内容为历史记录。

## 0.1 2026-07-12 统一验收回填

`P1AcceptanceReportGenerator` 已将 M5N2 main summary 纳入统一离线报告，按同一 profile/seed 分别保留 active pair、unique target 和 coalition completion 的机会数、成功数和成功率。四层执行证据与三层物理结果继续分离；缺 required-primary 或 arrival-window evidence 时 coalition 不由 pair/target 反推。当前代码入口已闭合，真实同条件 M5N2 baseline/candidate 多 seed 数据仍是开放 P1。

2026-07-12 复核时进一步限定 `physical_levels` 只读取 `family=m5n2_paired`；2v2 dropout 和 `png_ttc` 行不进入 M5N2 pair/target/coalition 分母。main 后续新增的四层指标继续按同名字段读取。

**日期**：2026-07-11

**范围**：基于 D1-D5、D7 六份 `M_TO_N` 专项报告，定义 D6 离线评估口径；不修改控制、分配、关联、导引或 AirSim 运行逻辑。

**状态**：D6 日志合同、离线聚合、兼容 duplicate 判定和报告接线已实现；当前无运行级 P0 blocker。CV 10-seed 已达到 8/10 T001 双 primary 合同验收，secondary/distributed executing 3/3 与 missing-ACK aborted 2/3 正负例均闭合；SimpleFlight 物理命中仍开放。py-motmetrics IDF1/MOTA/MOTP 已作为 P2 optional adapter 实现，HOTA unavailable。D6 只消费落盘事件，truth 只用于离线评分。

## 0. 2026-07-11 实现回填

- 新增 `TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`，并扩展 `AssignmentRecord/TerminalRecord` 的 D3 对齐字段。
- `EpisodeMetrics`、JSONL loader/writer、episode CSV、batch summary 和 Markdown 已接入本报告第 4 节指标；每项在 `m_to_n_metric_availability` 保存 status、reason、numerator 和 denominator。
- `duplicate_terminal_lock_count` 保留通用同帧多资源锁计数；`authorized_cooperative_lock_count`、`erroneous_duplicate_lock_count` 与 `same_resource_lock_continuity_count` 分开报告，错误锁只含 `k=1`、版本冲突或超需求。
- 探测 POD/miss/FAR 同时要求 truth opportunity 与离线 match/miss 配对裁决；仅有 truth 列表且全部 track truthless 时为 `None/unavailable`，truthless center track 不自动计 false alarm。
- 五类 `center_replan_*` 事件已接入 request/deduplicated/no-change/applied/expired、pending dwell 和 convergence time，并保留 request/target/coalition/risk/resolved-plan 审计字段。
- 测试覆盖 3 个合法 cooperative lock、第四个非法、版本冲突、same-resource continuity、replan complete/expired/unavailable、shortfall、hybrid reserve 等待、simultaneous/sequential、缺证据三态、legacy 和 JSONL/report round-trip。
- 中心正常 CV 10 seeds 中 8/10 形成 T001 双 primary 同帧锁与授权；全部 seed 为 IDSW=0、错误重复锁=0、control=0、physical unavailable。2 个未双锁 seed 保留为鲁棒性尾部样本。
- 二级正例为 `secondary_plan_v2` active、secondary executing ACK 3/3；完全分布式正例为 peer executing ACK 3/3；missing-ACK 为 aborted ACK 2/3、D7 allowed=0。
- SimpleFlight 10 seeds 每组均为 4 bindings、3 active + 1 standby，但 30 个 active pair 为 0 命中、24 detection timeout、6 timeout。15 s、`control_dt=0.5 s` 只构成诊断证据，不能宣称物理协同拦截已完成。

## 1. 结论

1. M 对 N 评估必须把“一个目标需要多个资源”与“同一目标被错误复制”分开。合法联盟多分配、多观测和多锁定不能沿用一对一 `duplicate_assignment_count` 或 `duplicate_terminal_lock_count` 的充分判据。
2. 评估单位从单 pair 扩展为 `episode -> target -> coalition/wave -> member/link/frame`。所有比例同时输出 numerator、denominator、aggregation level、evidence availability；缺证据为 `unavailable/null`，证据存在且计数为零才是 `0`。
3. 现有 D6 的实际规模、显式 `id_switch_count`、RMSE/continuity、版本/迟滞、D4 lifecycle、D5 terminal/multi-view、通信、D7 intercept/safety、多 seed 配对与报告能力均可复用。新增项是 P1 合同和离线聚合，不要求立即引入外部库。
4. 实验采用四路线：`independent`、`simultaneous`、`sequential`、`hybrid_primary_reserve`；每条路线覆盖中心正常、二级接管、完全无中心三个层级，并在几何、同步、通信和成员失效四类扰动下比较。
5. 当前场景没有新增 P0。若未来正式启用 `required_resource_count > 1`，在报告成功前必须至少具备 target demand、coalition/version/member role、planned cooperative lock 和 arrival/wave 证据；缺这些证据时 M 对 N 指标应 unavailable，不能按一对一指标猜测。

## 2. 统一输入事件与键

所有事件至少包含：

```text
episode_id, timestamp, event_type, source_node_id,
global_track_id, plan_id, plan_version,
coalition_id, coalition_version, coalition_epoch,
resource_id, member_role, wave_id,
measurement_timestamp, arrival_timestamp,
evidence_available, metadata
```

规范键和责任边界：

- `global_track_id` 由中心或当前合法 owner 维护；D6 不创建、合并或重绑定。
- local track 键必须为 `(source_node_id, local_track_id, local_epoch)`，不能仅比较 local ID 数值。
- 联盟快照键为 `(episode_id, global_track_id, coalition_id, coalition_version, coalition_epoch)`。
- 计划快照键为 `(episode_id, plan_id, plan_version)`；旧版本 reject 单独计数。
- 波次键为 `(coalition_id, coalition_version, wave_id)`；成员角色至少为 `primary | reserve | observer | retry`。
- 消息唯一键为 `message_uuid` 或 `(source_node_id, sequence_id, source_epoch)`，并保留 `parent_fusion_ids/source_lineage`。

建议上游落盘事件如下：

| 事件族 | 最小事件/字段 | D6 用途 |
| --- | --- | --- |
| 目标需求 | `target_demand_declared/updated`：`required_count`、能力需求、有效窗口 | demand 分母与 unmet slots |
| 联盟生命周期 | `coalition_proposed/forming/committed/reconfigured/released/failed`、成员集合、ACK bitmap、digest | formation/reconfiguration、digest conflict |
| 分配与版本 | `member_assigned/revoked`、role、plan/version、stale reject | 合法多分配、成员变化、stale rejection |
| 到达与波次 | `arrival_window_assigned`、`member_arrived`、`wave_started/completed/cancelled` | dispersion、common-window、interval/order |
| 主备切换 | `reserve_held/activated/released`、触发原因、新版本 | hybrid primary/reserve |
| 定位 | 估计/真值、`P`、创新 `nu`、`S`、observer lineage、几何质量、reject reason | RMSE/NIS/NEES/一致性/几何拒绝 |
| 跨节点航迹 | local-to-global binding、canonical registry snapshot、fusion lineage、duplicate reject | canonical duplication、cross-node IDSW、公共信息去重 |
| 末端锁定 | local track、resource、decision、coalition/plan/version、slot、authorization | planned cooperative lock 与错误 duplicate lock |
| 失效与冲突 | `member_lost/replaced`、`coalition_digest_conflict`、lease/epoch/version reject | 成员失效和一致性 |
| 通信与安全 | sent/received bytes、round、latency、member pose/range、risk/violation | 消息预算、时延、最小间距、碰撞风险 |

## 3. 聚合层级与 unavailable/zero

### 3.1 聚合层级

| 层级 | 主键 | 适合指标 |
| --- | --- | --- |
| frame/update | timestamp + target/member/link | NIS、NEES、几何拒绝、瞬时 separation/risk、消息 latency |
| member | coalition + resource | 到达误差、锁定、失联、角色切换 |
| wave | coalition + wave | 波次间隔、顺序、完成率 |
| coalition-version | coalition + version/epoch | formation/reconfiguration、digest、消息/字节/轮次 |
| target-episode | episode + global target | demand satisfaction、unmet slots、canonical duplication |
| episode | episode_id | 成功、安全、总开销、三中心层级对比 |
| batch | scenario/version/route/center/fault/seed/actual scale | 均值、分位数、paired effect、bootstrap CI |

batch 分组必须保留实际 `drone_count/resource_count/target_count/camera_count`，不得从 `2v2/5v5` 名称推断。宏平均先对 target/coalition 等权，微平均按机会数加权；两者都报告，不能只给一个总体比例。

### 3.2 unavailable 与零

- `unavailable/null`：需求事件、时间戳、真值、协方差、消息字节或成员位置等必要证据缺失；该样本不进入分母。
- `0`：证据链完整且事件计数确实为零，例如 0 个 unmet slot、0 次 stale reject、0 次碰撞风险越阈。
- `not_applicable`：策略本身不含该概念，例如 `independent` 路线没有 reserve activation rate；不得写成 0。
- 每项输出 `value/numerator/denominator/availability_reason/evidence_path`。分母为 0 时比例 unavailable，而不是 0 或 1。

## 4. 指标定义

### 4.1 目标需求、联盟形成与重构

对目标 `j` 在评估快照 `s` 的需求 `k_js` 和有效已分配成员数 `a_js`：

```text
satisfied_slots_js = min(a_js, k_js)
unmet_slots_js = max(k_js - a_js, 0)
target_demand_satisfaction_rate_micro
  = sum_js satisfied_slots_js / sum_js k_js
target_demand_satisfaction_rate_macro
  = mean_js I[a_js >= k_js]
```

`a_js` 只计 active、授权、current plan/version、未过 lease 且能力/角色满足的成员。`over_support=max(a_js-k_js,0)` 单列，不抵消其他目标 unmet slots。没有 `target_demand_declared` 时以上指标 unavailable。

```text
coalition_formation_time
  = t(first committed with demand/capability/ACK satisfied)
    - t(demand declared or formation requested)

coalition_reconfiguration_time
  = t(first new committed version after trigger)
    - t(member loss/digest conflict/stale-plan trigger)
```

超时但证据完整的样本按预先声明 censor/timeout 规则报告，不把 timeout 当作 0。另报 formation success、reconfiguration success、shrink/replacement/reform count 和 target-uncovered duration。

### 4.2 同时到达、波次与混合主备

对同一 simultaneous primary group 的实际到达时刻集合 `A_j={t_ij}`：

```text
simultaneous_arrival_dispersion_s = max(A_j) - min(A_j)
arrival_time_std_s = sample_std(A_j)
common_window_success
  = I[all required primary members arrived in assigned common window
      and dispersion <= allowed_dispersion]
```

成员缺失时 `common_window_success=0` 仅限需求、窗口和 episode 完成状态均有证据；未落盘到达事件则 unavailable。

对有序波次：

```text
wave_interval_w = t_start(w+1) - t_complete(w)
wave_interval_error_w = wave_interval_w - assigned_gap_w
wave_order_violation
  = I[t_start(w+1) < t_release_or_complete(w)]
```

同时报告早启、迟启、wave completion、cancel、immutable-prefix rollback 和 stale-wave execution。序贯路线没有公共到达窗口时为 not_applicable。

混合主备至少报告：

```text
primary_demand_satisfaction_rate
reserve_hold_integrity_rate
reserve_activation_rate
reserve_activation_latency
unnecessary_reserve_activation_count
reserve_release_latency
```

reserve 永久等待不能计入 demand satisfied；只有计划明确把 observer/reserve 计入任务需求且满足对应时间槽时才可计入。

### 4.3 协同定位精度与一致性

位置维度为 `d_p`，状态维度为 `d_x`：

```text
position_RMSE = sqrt((1/N) * sum_n ||p_hat_n - p_truth_n||^2)
NEES_n = (x_hat_n - x_truth_n)^T P_n^-1 (x_hat_n - x_truth_n)
NIS_n  = nu_n^T S_n^-1 nu_n
```

报告 RMSE 的单机、最佳双机、全部合法成员对照；NEES/NIS 报均值、分位数、超出 `chi-square(alpha, dof)` 上下界比例和 `consistency_pass_rate`。缺 truth 时 NEES unavailable，但 NIS 可在创新与 `S` 完整时计算；缺 `P/S` 时不能用 RMSE 代替一致性。

几何评估输出 observer count、LOS 最小/最大交会角、baseline/range、联合信息矩阵 rank/condition number、重投影残差、PDOP 或等价 covariance quality。定义：

```text
geometry_rejection_rate
  = rejected_updates_due_to_geometry / geometry_evaluated_updates
```

拒绝原因至少拆分 `rank_deficient | near_parallel_los | short_baseline | condition_number | reprojection | pose_covariance | time_skew`。退化几何下增大 covariance 或拒绝是正确行为，不应单独视为失败；应结合 RMSE/NEES 和下游 readiness 解释。

### 4.4 规范身份、公共信息与末端锁定

```text
canonical_duplicate_count
  = sum_truth_or_adjudicated_target max(number_of_active_canonical_ids - 1, 0)

cross_node_id_switch_count
  = count of canonical global_track_id changes for one physical target
    after namespace-aware local-to-global registration

common_information_duplicate_rejection_rate
  = rejected_duplicate_payloads / known_duplicate_payload_opportunities
```

canonical duplication 需要离线 truth 或人工裁决；没有裁决证据时 unavailable。cross-node IDSW 与现有 D2/D6 `id_switch_count` 都必须显式保留，并按 source node、center level 和 target 报告。公共信息机会由 message UUID、source lineage、source epoch 或 parent fusion ID 建立；没有 lineage 时不能宣称 rejection rate 为 1。

末端锁定集合记为 `L_obs`，计划授权集合记为 `L_auth`：

```text
planned_cooperative_lock_count = |L_obs intersect L_auth|
authorized_cooperative_lock_count
  = authorized resource locks in same-frame multi-resource snapshots within k
erroneous_duplicate_lock_count
  = legacy k=1 overflow
    + current coalition/assignment version conflict
    + locks beyond required_resource_count
same_resource_lock_continuity_count
  = sum_target,resource max(number_of_distinct_lock_timestamps - 1, 0)
```

另报 `planned_cooperative_lock_success_rate`、`over_support_count`、stale/mismatched plan lock、geometry-inconsistent lock 和 friend-overlap conflict。通用 `duplicate_terminal_lock_count` 只表示同一 timestamp+target 有多个 resource 的锁观测，不表达授权正确性，也不得覆盖 `erroneous_duplicate_lock_count`。

replan 生命周期只消费以下规范事件：`center_replan_request_created`、`center_replan_request_deduplicated`、`center_replan_ack_no_change`、`center_replan_applied`、`center_replan_expired`。请求、去重、no-change、applied、expired 分别计数；`replan_pending_dwell_s` 汇总 resolved/expired 的 `pending_dwell_s`，缺该字段时用 `resolved_at-requested_at`；`replan_convergence_time_s` 仅对 no-change/applied 成功闭合请求取均值。无事件证据时全部为 unavailable。

### 4.5 成员失效、摘要冲突、通信和安全

```text
coalition_member_loss_count
replacement_time = t(replacement committed) - t(member loss detected)
coalition_digest_conflict_count
stale_rejection_count
stale_rejection_rate = rejected_stale_messages / detected_stale_messages
```

按 shrink、replacement、full reform、hold/abort 分支统计结果，并记录失效后需求不满足持续时间。digest conflict 必须比较 member set、role、target binding、plan version、epoch、lease 和 immutable wave prefix，而不只比较 owner。

每次 coalition change 及每 episode 报告：

```text
messages_sent/delivered/dropped
payload_bytes_sent/delivered
consensus_rounds
end_to_end_latency_ms = received_timestamp - sent_timestamp
measurement_age_ms = arrival_timestamp - measurement_timestamp
```

同时给出 per-member、per-coalition-change、per-satisfied-target-slot 归一化开销。消息大小未知时 bytes unavailable，不能由消息数估算。

安全指标：

```text
minimum_member_separation_m = min_t,i!=j ||p_i(t)-p_j(t)||
collision_risk_exposure_s
  = integral I[predicted_or_actual_separation < safety_threshold] dt
collision_risk_event_count
collision_or_constraint_violation_count
```

区分预测风险、实际阈值越界和碰撞；只有离散采样时同时报告 sample period，防止漏掉采样间最小距离。到达同步成功不能覆盖 separation 或 collision failure。

## 5. 四路线 x 三中心层级实验矩阵

每个单元都运行相同 scenario version、实际规模、初始几何和 paired seeds。四类扰动至少各设 baseline 与 stress：几何为良好/近共线或短基线；同步为低 skew/时钟偏差与 arrival jitter；通信为正常/延迟丢包乱序分区；成员失效为无失效/primary 或 coordinator 在形成中与执行中退出。

| 路线 | 中心层级 | 几何变量 | 同步变量 | 通信变量 | 成员失效变量 | 主比较指标 |
| --- | --- | --- | --- | --- | --- | --- |
| independent | 中心正常 | 单/双/三观察者、退化 LOS | 各 pair 独立 | 中心链路延迟/丢包 | 单成员退出 | RMSE、需求满足、IDSW、min separation |
| independent | 二级接管 | 二级 coverage/基线 | 接管时钟偏差 | center-secondary 断链 | owner/成员退出 | takeover、stale reject、需求缺口 |
| independent | 完全无中心 | peer 几何差异 | peer clock skew | mesh 分区/乱序 | peer 退出 | CBBA rounds/bytes、canonical duplicate |
| simultaneous | 中心正常 | 终端扇区/交会角 | common-window jitter | time-to-go 广播延迟 | primary 退出 | dispersion、window success、separation/risk |
| simultaneous | 二级接管 | 区域视角退化 | coordinator clock offset | 接管丢包 | coordinator/primary 退出 | reconfiguration、window miss、digest conflict |
| simultaneous | 完全无中心 | 分布式几何质量 | consensus skew | 间歇通信/分区 | leaderless member loss | rounds/latency、window success、collision risk |
| sequential | 中心正常 | 每波几何变化 | wave gap jitter | feedback latency | 前波成员退出 | interval/order、stale wave、完成率 |
| sequential | 二级接管 | coverage cell 切换 | wave clock offset | feedback drop | reserve/owner 退出 | prefix 保持、重排时间、unmet slots |
| sequential | 完全无中心 | peer 可见性变化 | local wave clocks | mesh partition | wave member loss | order violation、digest、messages/bytes |
| hybrid primary/reserve | 中心正常 | primary 几何+reserve 视角 | primary window/reserve delay | activation feedback latency | primary 退出 | primary satisfaction、activation latency、safety |
| hybrid primary/reserve | 二级接管 | 二级 cue/primary 基线 | takeover 与 reserve slot 偏差 | lease/activation 丢包 | coordinator/primary 退出 | hold integrity、replacement、stale reject |
| hybrid primary/reserve | 完全无中心 | observer/primary 几何 | distributed release epoch | 分区/重复消息 | primary/reserve 退出 | digest conflict、duplicate reject、需求恢复 |

每个组合至少输出 target/coalition 级原始行和 episode/batch 汇总；不能只输出总成功率。严格 simultaneous、sequential、hybrid 是研究路线，不表示当前 D3/D4/D5/D7 已实现相应控制能力。

## 6. 原始指标与算法证据

以下来源均用于定义评估或实验设计，不表示 MSM 已实现论文算法：

| 家族 | 原始/基础来源 | D6 使用方式 |
| --- | --- | --- |
| CLEAR MOT | Bernardin, Stiefelhagen, *Evaluating Multiple Object Tracking Performance: The CLEAR MOT Metrics*, [DOI](https://doi.org/10.1155/2008/246309) | MOTA/MOTP、miss、false positive、ID switch 的标准对照；D6 继续显式输出 IDSW |
| HOTA | Luiten et al., *HOTA: A Higher Order Metric for Evaluating Multi-object Tracking*, [DOI](https://doi.org/10.1007/s11263-020-01375-2), [arXiv](https://arxiv.org/abs/2009.07736) | 检测、关联和定位平衡的帧级外部对照 |
| OSPA | Schuhmacher, Vo, Vo, *A Consistent Metric for Performance Evaluation of Multi-Object Filters*, [DOI](https://doi.org/10.1109/TSP.2008.920469) | 集合定位与基数误差，需固定 order/cutoff |
| GOSPA | Rahmathullah, García-Fernández, Svensson, *Generalized Optimal Sub-Pattern Assignment Metric*, 2017 International Conference on Information Fusion, [DOI](https://doi.org/10.23919/ICIF.2017.8009645), [arXiv](https://arxiv.org/abs/1601.05585) | 分解 localization、missed、false target 代价 |
| NEES/NIS consistency | Lyu et al., 多机器人异步协同定位与 CI，[DOI](https://doi.org/10.3390/app9050903)；D1 专项的 Qian et al.，[DOI](https://doi.org/10.1109/TIM.2024.3382741) | 用卡方区间审计 covariance consistency；NIS 不需 truth，NEES 需离线 truth |
| 航迹融合 ANEES | `jonassagild/Track-to-Track-Fusion`（MIT，D2 专项已核验）及 CI 基础 Julier/Uhlmann，[DOI](https://doi.org/10.1109/ACC.1997.609105) | 对照独立假设、已知相关和 CI 的一致性 |
| MRTA one-to-many | Dutta, Asaithambi, [DOI](https://doi.org/10.1109/ICRA.2019.8793855) | demand satisfaction、联盟完整性和求解时延设计 |
| CBBA | Choi, Brunet, How, [DOI](https://doi.org/10.1109/TRO.2009.2022423) | 完全无中心 rounds/messages/conflict 基线；不把 single-winner 当原子联盟 |
| Coalition/deadline | Guerrero et al., [DOI](https://doi.org/10.1371/journal.pone.0170659) | formation、deadline、成员物理干扰和重构评估 |
| 通信感知 coalition | Maždin, Rinner, [DOI](https://doi.org/10.1109/ACCESS.2021.3061149) | event/time/hybrid 通信的 bytes/messages/一致性与故障矩阵 |
| Cooperative impact time | Zhou, Yang, [DOI](https://doi.org/10.2514/1.G001609)；Yu et al., [DOI](https://doi.org/10.1109/TAES.2023.3243154) | simultaneous arrival dispersion、consensus latency 和 common-window success |
| Collision safety | Jha et al., [DOI](https://doi.org/10.2514/1.G004139)；Li et al., [DOI](https://doi.org/10.1016/j.jfranklin.2021.06.030) | minimum separation、risk exposure、同步与安全联合判定 |

## 7. 开源评估候选

| 项目 | 许可证/状态 | 适用性 | 限制与结论 |
| --- | --- | --- | --- |
| [Stone Soup](https://github.com/dstl/Stone-Soup) | MIT；D1/D2 专项核验为活跃维护，2026-06-24 发布 `v1.9.1` | Track/Detection/GroundTruth、OSPA/SIAP、track-to-track/CI 研究对照 | 需 MSM adapter、版本锁定、时间/坐标/lineage 合同；适合作为 P2 隔离 benchmark，不替换本地主线 |
| [TrackEval](https://github.com/JonathonLuiten/TrackEval) | MIT；公开 evaluator | CLEAR、HOTA、Identity 等标准 MOT 对照 | 需要 frame-level export、IoU/距离门限和遮挡规则；适合 D2/D5 P2 benchmark，不覆盖联盟/通信/安全 |
| [py-motmetrics](https://github.com/cheind/py-motmetrics) | MIT；公开 Python MOT accumulator | CLEAR MOT、ID 指标和逐帧匹配核对 | 需稳定 accumulator 输入；可作为轻量备选，但不提供 HOTA、联盟或 covariance consistency 全链路 |

当前已选择 py-motmetrics 作为隔离式 P2 对照，输出 IDF1/MOTA/MOTP，HOTA unavailable。TrackEval 与 Stone Soup/OSPA 仍是后续可选互补 benchmark；这些外部工具都不得进入在线总线或成为 D6 默认测试硬依赖。

## 8. D6 可复用能力、P1 与 P2/P3

### 8.1 已有可复用能力

- `EpisodeMetrics` 与 track/assignment/target-demand/coalition/arrival/event/link/terminal 记录模型。
- 实际规模归一化、`metric_scope/seed/scenario_group/scale` 分组和 unavailable/zero 基础语义。
- `track_rmse`、continuity、显式 `id_switch_count`，以及 D4 failover/consensus、D5 multi-view/terminal、通信 latency/drop/stale、D7 min range/intercept/safety 指标。
- main execution/contract 双口径、evidence path、场景库、多 seed 严格配对、effect size/bootstrap CI 和 CSV/Markdown/PNG 报告。
- D6 offline-only 与 truth isolation 边界。

### 8.2 P1 实现状态

1. 已实现 M 对 N DTO、assignment/terminal 扩展和 JSONL loader/writer。
2. 已实现 target/coalition/wave/member 聚合器和 unavailable/not-applicable/zero 三态。
3. 已实现合法 coalition multiplicity 判定，以及 canonical duplicate、cross-node IDSW、common-information duplicate rejection、planned/authorized/erroneous lock、same-resource continuity 和 center replan lifecycle。
4. 已接入 episode CSV、batch summary、Markdown 和 actual-scale 分组。
5. 已完成 CV 10-seed T001 合同验收、二级/无中心 commit 正例和 missing-ACK 负例；SimpleFlight 当前只有 0/30 命中诊断，物理执行与完整四路线 x 三中心层级 x 四类扰动矩阵仍待完成。

当前场景无新增 P0。D6 本地合同与聚合已完成；缺日志时只标 unavailable，不阻断现有 `k_j=1` 回归。

### 8.3 保留 P2/P3

- P2 状态：`msm-offline-mot-v1` 与 py-motmetrics IDF1/MOTA/MOTP adapter 已实现；TrackEval、Stone Soup、OSPA/GOSPA、HOTA、bootstrap/非参数 CI 和必要时的 AirSim recording parser 仍待实现。
- P3 保持：仅在已有真实 schema/样例且 AirSim 无法回答实验问题时评估 SCRIMMAGE bridge。
- 禁止项保持：D6 不接 live AirSim 控制，不把评估 truth 或后验标签回写在线链路。

## 9. 验收口径

- 每项指标能追溯到输入事件、公式、聚合层级、分母和 evidence path。
- 合法 `k_j>1` assignment/lock 不产生异常 duplicate；计划外、stale、local-to-multiple-global 冲突仍被计数。
- 几何退化时 covariance 增大或更新被拒绝；RMSE 与 NEES/NIS 共同解释。
- simultaneous 同时满足 common window 和 minimum separation 才算完整成功；sequential 保持 wave order；hybrid 不把未激活 reserve 冒充需求满足。
- 三个中心层级均报告 demand、formation/reconfiguration、digest/stale、messages/bytes/rounds/latency。
- 缺失证据保持 unavailable，真实零保持 0；not-applicable 不进入分母。
- 当前任务已实现并运行 D6 离线单元测试；未运行 AirSim，也未修改上游控制或日志生产代码。

## 10. 三维规模化身份证据接口影响（2026-07-20）

新增 D1/D2 真值隔离 adapter 不改变本文件的 M 对 N 指标定义、联盟分母、同时/分批到达
路线或安全判据。它补充了 M 对 N 场景所需的上游定位一致性和身份连续性证据：D1 可按
sensor/range 提供 RMSE、NEES、NIS，D2 可提供显式 IDSW、continuity、duplicate、confusion
和 coverage。

接口支持任意正整数 actual target/resource count，已用 5/20/50/100/200 结构 fixture
回归。高威胁多成员联盟仍必须由 D3/D4/D5/D7 的 coalition/member 记录评估，不能由 D2
duplicate 指标反推。D1 来源摘要现规范为 `d2_lineage_mapping`，旧名称只输入兼容，不改变
M 对 N 分母或指标定义。2026-07-20 D6 全量 `334 passed`；本轮未运行 M 对 N AirSim 或正式
多 seed 物理闭环，M 对 N 性能状态保持原结论。
