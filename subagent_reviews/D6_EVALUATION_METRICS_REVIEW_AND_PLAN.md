# D6 系统评估指标综述及子方案

## 2026-07-15 legacy provenance 与真实三档评审

评审确认 legacy fallback 是 case 注册驱动的持久化证据审计，不是目录名推断：仅路径输入且所有
summary/case/result provenance 缺失时，要求 20/20 sibling generated settings 显式、有限、正数且
一致。缺文件、缺键、冲突、NaN/Inf/字符串均 fail closed；mapping 与部分显式 provenance 不回退。

真实三档报告已生成：60 case、20 个跨档配对、truth identity/state 全 0；1.0 由 20 份 settings
闭合，0.2/0.1 为 case result provenance。冻结合同为 56 match/4 mismatch，四个受影响 candidate
case 明列原因且 aggregate unavailable；reserve 排除和 timing 分层不变。baseline 可用物理结果为
0.1 `4/30,4/20,0/10`、0.2 `9/30,9/20,0/10`、1.0 `6/30,6/20,0/10`。case wall timing 缺源字段。
因此不从 candidate 0.1/0.2 部分证据给出性能或准入结论。专项 `18 passed`、全量 `272 passed`。

## 2026-07-15 0.1 P1 NameError 紧急评审

评审确认根因修复不是放宽 case-aware 合同，而是消除模式 helper 的名称/定义顺序漂移：唯一 helper
在所有 dispatch 之前定义，三个调用点一致。新增 20-case 双层 merged evaluator 回归直接覆盖此次
失败入口。

真实 0.1 P1 v6 只读报告生成成功，两层各 4036 records、20 case，manifest match，runtime 输入 hash
不变。timing 专项 `28 passed`、D6 全量 `264 passed`。该证据关闭 D6 runtime NameError 回归，不代表
三档 comparator 已完成或形成性能结论，无新增 D6 P0。

## 2026-07-15 0.2 case-aware 与机会合同评审

评审确认 `d6-stage-timing-report-v2`/P1 v6 已关闭 merged suite loader 缺口。suite 模式仅接受
`case_id/family/profile/seed`，每 case 内保持严格单调，边界可重置；双层 manifest 必须一致，禁止
跨 case 连续化和 main/control 求和。默认 single episode 行为未改变。

`d6-m5n2-clock-speed-comparison-v2` 将每 case 机会冻结为 `3/2/1`。actual-execution unavailable 或
机会不符时，整项 unavailable，报告列 case/reasons；standby reserve 即使成功也不计 active-primary。
真实 0.2 20-case 审计为 18 match/2 mismatch：candidate seed006 为 D7 unavailable 且 reserve success
被排除，candidate seed009 的 D7 available 但机会仍为 `2/1/1`。两层 merged timing 各 6567 records/
20 case 的只读 P1 复测通过。该 0.2 阶段专项 `27/10 passed`、当时全量 `263 passed`。真实 0.1 P1
状态见顶部；该段记录 0.2 阶段状态，三档 comparator 随后已完成。

## 2026-07-15 ClockSpeed 三档能力评审

评审确认当时的 `d6-m5n2-clock-speed-comparison-v1` 已关闭 D6 离线比较入口缺口；当前 schema 已按
顶部合同审计升级为 v2。三档输入必须各包含
baseline/candidate seed 1-10，并按 `case_id/profile/seed` 完整配对；ClockSpeed 来自 suite/case
persisted provenance，不能由目录名决定。result row 全量一致的显式 `clock_speed` 可作为 case-level
provenance，并与注册 artifact 中的显式值交叉校验。

报告保留三层独立物理分母、第二 primary 五米/距离、最终锁/coalition consensus、collision stop、
case wall、main-bus/control-tick wall timing、归一化 simulated time/tick 和 truth identity/state
审计。缺证据为 unavailable；main bus 是 control tick 内层，禁止相加。任一 profile 的 10 case
不完整时不发布部分 aggregate。

2026-07-15 三档各 20 case 的确定性验收专项 `8 passed`、D6 全量 `254 passed`，仅有既有
Matplotlib `Axes3D` warning。该段是运行前结论；真实三档 comparator 随后已完成，availability-aware
结果见顶部。candidate 0.1/0.2 仍因合同 mismatch 不形成完整准入结论，无新增 D6 P0。

## 2026-07-15 M5N2 20-case 评审结论

评审范围严格限定为 baseline/candidate 各 10 seed 的 20 个真实 AirSim M5N2 case。M5N2 完成后、
`TERM` 生效前额外完成的 `png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned
2v2 和全部 dropout 未执行；缺失 case 保持 unavailable，不补零，也不构成完整 suite。canonical
actual evidence 为 `20/20` available，校验原因 0，在线 truth identity/state 均为 0。

正式物理结果是 pair `12/60`、target `12/40`、coalition `0/20`。第二 primary 七阶段
availability 全部完整，前四阶段通过 `20/20`、control/mode=`17/20`、physical=`0/20`；20 个
首失败原因全部可用。该结果说明 D6 口径已经能定位断点，但第二 primary 和联盟物理闭环未完成。
baseline/candidate 总成功数相同，逐 seed non-degradation=false，candidate 不应晋升默认路径。

术语审计统一为：canonical target physical success 是至少一个 participating pair 成功，本批为
`12/40`；cooperative target-stage diagnostic 是全部 required member 通过某一阶段。后者不能覆盖
正式 `target_intercept_success`。20 个第二 primary 最终均为 `collision_stop`，但 collision object
未写盘，D6 不推断成员冲突、环境碰撞或 AirSim 状态问题，原因对象保持 unavailable。

两层 timing 各 3805 条。main bus mean/P95=`349.34/487.40 ms`，control tick=
`1069.45/1254.06 ms`；二者嵌套，禁止相加。逐 case 原始文件可严格消费，但 partial acceptance
没有注册路径，suite 合并流又在 case 边界重置 frame/time，正式 timing 仍 unavailable。下一步由
main 修复 case-aware 接线；系统侧优先降低 D1 fusion、AirSim frame sample、bus processing 和
control RPC 延迟。另需区分 canonical “任一 pair 成功”的 target physical 与 cooperative “全部
成员阶段通过”的 target 诊断，后者不能覆盖正式 `target_intercept_success`。D6 不参与控制或阈值
放宽。

## 2026-07-15 第二 primary 与联盟完成口径评审

评审确认 `d6-cooperative-closure-v3` 已关闭 D6 被动报告缺口。第二 primary 具备从分配到物理结果
的七阶段漏斗；pair、target、coalition 保持独立机会数和 availability，coalition completion 不由
target success 推断。producer 未写首失败原因时，D6 只报告原因缺失，不构造 `unspecified`。

确定性专项 `11 passed`、当时 D6 全量 `246 passed`，`py_compile` 通过。其后 main 已生产本页顶部
的 20-case M5N2 证据；结果确认第二 primary 未完成五米拦截，coalition 未达门限。额外完成的
`png_ttc` seed001 不进入该聚合，其余 tuned 2v2 和全部 dropout 需作为后续独立批次。

## 2026-07-15 D2 ceiling-aware v2 正式证据评审

评审确认 D6 已关闭“尚无 D2 v2 正式证据”的 P1 报告缺口。aggregate 直接保留 producer 的
`promotion_recommended=true`、promotion candidate、selected/default path、14 条 overall/分档
assessment、五 gate reason 和 dropout truth alignment；legacy 缺字段保持 `None/unavailable`，
`producer_decision_recalculated_by_d6=false`。

总体 GNN 五 gate 通过且仅建议评审。分档只有 clutter/combined 通过；delayed_noisy、dropout、
nominal、tight_crossing 因 baseline IDSW=0 无可测 reduction evidence 而 fail-closed。dropout 在
10-seed screening 和 20-seed confirmation 全部为 partial truth alignment；JPDA 是 research-only
adapter 且不准入。默认在线 GNN/Hungarian 未改变。

本批没有安全复用异批 D1/D3/D4/D5/D7，六源均 unavailable，因此不是全系统通过证据。输出四件套
位于 `research_modules/d6_evaluation_metrics/outputs/p1_identity_ceiling_aware_v2_20260715/`；专项
`31 passed`、D6 全量 `243 passed`，未启动 AirSim。剩余 P1 是 promotion 评审、同批多源系统判决
和长期趋势，不再包括 D6 v2 parser/aggregate/中文报告能力。

## 2026-07-15 分阶段延迟评审结论

D6 已具备 main bus 与 SimpleFlight control tick 两层持久化计时的严格离线消费能力。非法合同、
数值、状态、顺序、和式或预算标志 fail closed；旧日志缺 timing 保持 unavailable。每层独立报告
分布、状态计数、预算违例和 dominant stage，禁止把 control tick 内的 `bus_processing` 与 main
bus 相加。该历史阶段 P1 acceptance 为 v5，当前 case-aware 接线为 v6。

2026-07-15 合法两层各 2 帧及负例矩阵专项 `20 passed`、D6 全量 `236 passed`，未启动 AirSim。
关闭的是计时可观测性代码 P1，不是系统性能 P1；其后 M5N2 20-case 已确认 `100 ms` 不达标，
case-aware 正式接线已关闭，瓶颈优化仍开放。

## 2026-07-14 actual target-state freshness/stale P1 评审结论

评审确认 D6 已关闭从最终 command 到 canonical actual evidence、source-hash validator、逐 case、
pooled aggregate 和正式 CSV/JSON/中文 Markdown 的完整 freshness/stale 指标链。六个字段均为必需；
所有缺失、非法数值、时间/age 冲突、非法 stale 或空 source 都 fail closed。显式零和真实正 stale
均保留 availability，不以零代替缺证据。

真实证据为 2026-07-14 tuned 2v2 seed-1 48 samples 与 M5N2 seed-1 608 samples；mean/p95/max
分别为 `0.0375/0.2/0.2 s` 和 `0.091118/0.2/0.2 s`，stale 均 0，来源均为
`d2_estimated_global_track`。validator 已用 source path+SHA256 重算并与 payload 对照，2/2 case
available。D6 全量 `216 passed`。该结论只关闭单 seed 正式指标链；multi-seed 趋势、跨提交回归
和 failure taxonomy 当时仍为 P1。顶部 20-case 已补齐 10389 条同配置 multi-seed 样本；当前剩余
跨提交回归、failure taxonomy 和独立批次复验，physical、五层、truth 与 availability 语义不变。

## 2026-07-14 actual v2 真实 AirSim 最终评审

评审读取统一 D6 acceptance report 与 main 实验报告，确认 tuned 2v2 seed-1、M5N2 seed-1 的
required/available/unavailable=`2/2/0`，actual execution P0 全可用门通过。两例
summary/CSV/actual 物理成功计数均为 `2/2/2`，旧
`d7_actual_execution_command_physical_count_conflict` 未复现并关闭。

M5N2 pair=`2/3`、target=`2/2`、coalition=available `0/1`；coalition 是完整证据下的失败，
不能由 target `2/2` 代替。`overall_acceptance_passed=false` 的范围是完整 P1 suite：当前仅
2 个 seed-1 case，未覆盖 baseline/candidate 配对、1-5 帧 dropout 和 multi-seed。性能结果
`123.3/384.6 ms`、budget violations 合计 `231` 仍为 P1；M5N2 第二 primary 物理闭环也保持
开放。D6 本批只同步文档状态，不改代码或控制边界。

## 2026-07-14 actual-execution/arrival 最终评审（真实重跑前历史）

评审确认 D6 formal gate 只接受通过校验的 canonical `d7-actual-execution-metrics-v2`。任一
required case 缺失或 explicit unavailable 时 `actual_execution_all_available=false`，suite 总验收
fail closed；legacy main row 与离线五米结果仅作 diagnostics，不能替代 actual envelope。

`arrival_coordination_required=false` 时，coalition completion 采用每个 required active primary
独立五米成功的口径，全部 required primary 成功才完成 target coalition。required-primary
denominator/member、physical result 或 coordination 字段缺失，以及 summary/pair 冲突，仍输出
`null/unavailable`，不补零或推断 arrival window。

2026-07-14 仅完成代码级回归：专项 `14 passed, 24 deselected`、D6 全量 `190 passed`。唯一
Matplotlib `Axes3D` warning 只限制 3D projection，不影响 JSON/CSV/Markdown、二维报告或本轮
结论；未运行 AirSim。D6-owned P0 已关闭，但 main-owned P0 仍开放：M5N2 baseline、M5N2
candidate、2v2 PNG-TTC、1-frame dropout 四个历史真实 seed-1 actual artifact 均为
`unavailable`，原因均为 `d7_actual_execution_command_physical_count_conflict`，需 main 真实重跑
并注册有效 v2 artifact。P1 继续为同配置 multi-seed provenance/freshness 趋势与 failure taxonomy，
不因本轮 fixture 回归关闭。

## 2026-07-14 owner provenance 最终评审结论

D6 actual envelope 不把 owner 当作每行无条件必填 provenance。plan ID/version 仍逐行必填；owner
只对 effective-authorized 的 secondary/distributed active/execution/reassignment 或显式 execute
action 行必填。中心授权与未授权 pre-transition/pending 行可为空，整集无 authoritative owner 时
`owner_node_ids` 为空且 availability 为 unavailable；需要 owner 的执行行缺值继续 fail closed。

2026-07-14 确定性离线验收（seed N/A）为 execution-evidence focused `20 passed`、D6 全量
`184 passed`，1 条既有 matplotlib warning；未运行 AirSim。评审结论关闭 D6 owner 语义 P0，
不改变 main 的真实 seed-1 注册和 multi-seed P1。

## 2026-07-14 actual plan identity 评审结论

本轮确认并关闭了 D6-owned P0：最终计划身份现在由 actual command CSV 证明。envelope v2 输出
去重的 `plan_ids/plan_versions/owner_node_ids` 和逐项 provenance；合法多版本保留，同一 plan 的
版本冲突、缺列、坏类型及 payload/source 不一致全部拒绝。merge v3 会移除 replay 的同名字段，
只采用 validator 返回的 actual metadata，不影响既有 safety、physical 和 mode 口径。

2026-07-14 离线 focused `24 passed`、全量 `180 passed`，`py_compile` 通过；该阶段没有真实
AirSim。评审结论覆盖 D6 consumer/validator/merge；真实 seed-1 注册和单 seed freshness/stale
正式链已由顶部证据关闭，同条件 multi-seed provenance、freshness 趋势/failure taxonomy 和
D2-D3 跨源 join 仍为 P1。

## 2026-07-14 actual execution 评审结论（真实重跑前实现评审）

D6 已完成执行证据来源隔离。`integrated_replay` 只说明离线重放状态；SimpleFlight actual
execution 必须由最终 command、physical summary 和 main bus performance 三源联合证明，并由
独立 `d7-actual-execution-metrics-v2` 固化路径与 SHA256。raw mode change 不等于获授权的执行
模式切换，规范计数使用 `mode_switched AND effective_control_authorized`；无性能样本不允许发布
零时延。

main 的稳定调用入口为 `write_d7_actual_execution_evidence()`。writer 成功后再调用既有
`register_terminal_closure_case_evidence(..., d7_execution_metrics_path=actual_path)`。任一来源
缺失或冲突时不注册，不得搜索相邻文件或回退 replay。

两组最新既有 M5N2 seed-1 离线复核证明原歧义真实存在：raw replay mode 17/13 与 actual
effective control 0 冲突，raw loop 0 又无性能样本；final main bus loop 为 386.519/398.333 ms。
新 builder 生成 actual mode 0、sample 142/141，符合控制和性能证据。D6 `168 passed`。本批关闭
D6 代码级 P0；main 此后已生成/注册顶部两条独立 artifact 并完成真实 AirSim seed-1 复验。
multi-seed、完整 P1 矩阵和性能仍开放；D6 不越界修改 runtime。

## 2026-07-14 多案例 D3/D7 证据评审（先前四案例）

D6 已把 terminal closure 的评估单位从“一个可选 D3/D7 summary”扩展为 main rows 中显式登记的
`(case_id, seed, path)`。D3 逐 case 运行 canonical validation，再输出逐 seed 和 suite count/churn；
D7 逐 case 验证结构与 seed，但 raw EpisodeMetrics 缺 terminal envelope 语义时不进入四层聚合。
该设计的工程理由是：同一 suite 可包含 M5N2、2v2 PNG-TTC 和 dropout，不应选择一个 D3 文件
代表全部 case，也不应因某个坏文件使其余 case 丢失。

现有 seed-1 suite 验证结果：D3 4/4 case、543 records；D7 原 main summary 0/4 path registered，
原因全部为 `d7_execution_metrics_path_not_registered_by_main`。临时显式登记现有文件后 D7 4/4
结构有效，control allowed 合计 51，与 main 四层值一致但未二次累计。D6 全量测试
`159 passed`。

后续计划由 main owner 执行 runtime helper 接线和正式 suite 重生成；D6 owner 只在 producer
合同变化时扩展 schema validator，不通过 glob 或目录命名规则补路径。正式 D7 4/4 registered
之前，multi-seed 的 D7 execution evidence 不准声明闭合。

## 2026-07-14 terminal suite P1 评审结论

D6-owned terminal suite schema、consumer 和报告链已关闭。`P1AcceptanceReportGenerator` v2
将 contract/control/switch/mode/physical 计数转为带 producer/scope/denominator/lifecycle 的
长表；只在 source+producer+scope+lifecycle 单一组内聚合。main planned-lock 与 D7 execution
同名指标并存时顶层 sum 为 null，各组单列，不比较或覆盖。

terminal suite 新增 D3 canonical file input，输出 latest plan/version、primary/reserve membership、
owner 和 feedback churn。性能指标要求正 sample count；无样本零不可用。candidate
non-degradation 与 effectiveness 分离，双零且零触发为 inconclusive，不推荐晋级。产物已覆盖
per-seed/aggregate JSON/CSV 和中文 Markdown。

2026-07-14 确定性离线验证专项 `8 passed`、canonical `24 passed`、全量 `154 passed`，1 条
既有 matplotlib warning；未运行 AirSim。下一步不在 D6：main `p1_terminal_closure` 需生产
规范 envelope、physical/performance/candidate 字段并传 D3/D7 文件，随后运行真实同条件
multi-seed batch。以下 physical provenance 等章节保留其独立状态。

## 2026-07-14 truth-state/physical provenance 评审结论

D6 已将 truth identity 与 truth state 正式拆成两个 availability-aware 计数。strict
`d2_estimated_global_track` 路径为 state-use available `0`，显式
`airsim_actor_truth_fixture` 为 `>0`；summary 零不能覆盖 pair/command 正证据。physical layer
现在要求 summary 与 active pair summaries 同时存在，command-only 和 summary-only 均 fail
closed。每个 active pair 必须显式 `physical_evidence_available=true`，且
`target_state_source` 与 summary online source 一致；offline scorer 只允许 D2 estimated
class，truth fixture 只允许显式 fixture class。command loader 保留 evidence 字段供审计，但
layered metrics 不再从 command rows 构造 physical pair。任一 gate 失败时 pair/target/
coalition 与 physical count/rate 全为 `None/unavailable`，旧无来源 status 只保留 raw audit。
每个 participating pair 还必须有显式 physical 布尔结果或规范 scorer 终态；coalition 缺
required member、arrival window、denominator 或 summary completion 时单独 unavailable，完整
显式失败保持 available `0`。各报告格式与 coalition metadata 使用同一 reason。

2026-07-14 使用 7 类确定性离线 provenance 场景达到全部 exact 门限，seed N/A；D6 全量
`150 passed`，1 条既有 matplotlib warning，未运行 AirSim；其中新增 7 项覆盖 result/member/
window/denominator/显式零。2026-07-11 至 07-13 历史
physical 数值若缺新 provenance，不作为迁移后 offline scorer evidence。本次只关闭 D6 P0
代码/测试；单 seed freshness/stale 正式分布已由本文顶部关闭，真实同条件 multi-seed AirSim
physical evidence 和跨提交 freshness 趋势仍为 P1。

## 2026-07-14 truth tracking 当前评审结论

truthless tracking 假零 P0 已关闭。`EpisodeMetrics`、collector、main-bus loader、merge 与
reporting 统一使用 null/unavailable；合法 truth identity history 中无切换则显式输出
available `id_switch_count=0`。JSON、CSV 和 Markdown 都携带同一 availability，旧载荷即使
含零也不能覆盖 unavailable。

2026-07-14 以 5 个确定性场景验收，seed N/A；空输入、匿名 track、不完整 sidecar、完整
truth 稳定/切换均达到预定门限，D6 全量 `137 passed`，1 条既有 matplotlib warning。本轮
没有 AirSim 物理实验。真实 multi-seed seed/config/schema/hash provenance，以及 D2 lifecycle
与 D3 churn 的 episode clock/global ID/plan version join 仍为 P1；P2 external benchmark
状态不变。

## 2026-07-14 第二批当前评审结论

D6 已接入 `d3_plan_history_v1/history[]` canonical ordered evidence。该分支严格校验 wrapper、
record、record_count、sequence/order key、timestamp、assignment/coalition/feedback/owner 和
truth 隔离；不对坏文件重排序，不从 plan version 推断 tick 顺序。无效历史的 churn、成员、
owner 与 feedback 指标全部 unavailable，稳定原因码进入 CSV、aggregate JSON 和 Markdown。

membership 现在比较相邻 assignment snapshot 的 target/resource/role/activation 状态；重复的
producer audit event 不增加计数。新增 primary/reserve membership 分项、soft/hard feedback，
并让 D3 canonical 行正式输出 owner change。计划、联盟 version 和 coalition epoch churn 由
同一 validated history 计算。

2026-07-14 专项 `24 passed`、D6 全量 `132 passed`，1 条 matplotlib `Axes3D` 环境 warning。
旧 snapshot/cooperative-role 回归继续通过。当前剩余 P1 为真实 multi-seed episode 趋势和
failure taxonomy；P2 external benchmark 不变。本轮无新 AirSim 物理结果，D6 仍为 file-only
被动消费者。以下第一批和更早章节为历史评审记录。

## 2026-07-14 第一批评审结论（历史）

已确认的 D3 churn availability 评估级 P0 已修复。统一报告现在只在 producer 显式写出
count，或至少两条记录具有顺序语义且该指标证据完整时，才计算
`plan_version_churn_count`、`coalition_version_churn_count`、
`coalition_epoch_churn_count` 和 `membership_change_count`。显式零和稳定有序历史输出
available `0`；最终快照、空 mapping、单条无序记录与不完整历史输出 unavailable。

2026-07-14 的 5 类 fixture 验收标准是前三类四项全 unavailable、后两类四项全 available
`0`；专项结果 `12 passed`，D6 全量 `120 passed`，另有 1 条 matplotlib `Axes3D` 环境
warning。正式 40-case cooperative-role 分支继续只报告角色，四项 churn 保持 unavailable，
因此现有 M5N2 角色/coalition 报告兼容。

当前剩余 P1 为真实有序 D3 plan history/provenance、长期 multi-seed 跨提交趋势和跨批次
failure reason taxonomy；P2 为真实 py-motmetrics benchmark 标定及 TrackEval/HOTA、Stone
Soup metrics、OSPA/GOSPA 等 optional/offline 对照。D6 仍只读写盘证据，不控制 AirSim，
不参与分配或导引。以下 2026-07-13 及更早章节是历史评审记录。

## 2026-07-13 历史最终统一报告状态

D6 已消费正式 AirSim/main 产物并形成七源统一离线报告，不再处于“等待 main 后续提供真实 AirSim evidence”的阶段。当前各源均为 available，展开行数为 D1 `1`、D2 `3660`、D3 `40`、D4 `60`、D5 per-primary `160`、native MOT `18`、D7 `164`。D7 的 164 条包含 160 条 pair/safety 记录和 4 条 profile 汇总，聚合时不重复计数。

正式结果为：M5N2 最佳 profile coalition `5/10`、全部 profile overall `8/40`；D7 四层分别为 contract `35`、control `7`、mode switch `9`、physical `62`。online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 0。D3 当前只有 case/final aggregate，没有逐时刻 plan history，因此 churn 明确保持 `unavailable`，不得从 version 总数或最终 snapshot 反推。

D6-owned schema adapter、availability、分组、四层分离和中文报告缺口已经闭合，当前回归为 `115 passed`。开放 P1 收敛为三项：长期 multi-seed 趋势、producer 逐时刻 schema（优先 D3 churn）和跨批次失败原因治理。P2 工具继续只作 optional/offline benchmark，不进入默认依赖、默认报告主线或在线控制路径。下文较早批次内容只保留演进记录；冲突时以本节为准。

## 2026-07-13 M5N2 正式写盘 schema 评审补充

统一系统证据报告器此前只识别通用 `summaries/rows/records`，会把 main 的
`cases/pair_rows/aggregates` 原始文件读成 0 个 D5 行，并把修正后的
`d6-cooperative-closure-v2` 指标标为 unavailable。本轮增加两个明确、只读的 schema
adapter，不改变 cooperative producer 或在线控制。

原始路径按显式 case/pair 展开：D3 只统计 active primary 与 reserve 角色，不从无序
plan version 推断 churn；D5 把 visible、由 `d5_decision_state=locked` 生成的
associated、common-lock participation 和 global ID rewrite 分开；D7 只对 active primary
统计四层 funnel，reserve 仅进入越权安全审计，并用 4 个 source aggregate 统计 coalition。
修正 aggregate 路径只恢复其真实保留的 funnel、共同锁定、profile 和安全计数，不构造
丢失的逐 pair 或 seed 数据。

两种路径均复现正式结果：40 case、4 profile、最佳 profile `5/10`、总体 coalition
`8/40`，D7 active-primary 四层为 `35/7/9/62`，reserve unauthorized、global ID rewrite、
online truth use 均为 0。profile 分组键仅为 `profile`，`case_id` 只保留逐行审计，避免再次
出现 40 个单 seed 组。D6 继续被动评估，不写回控制链路，也不导出 truth identity。

## 2026-07-13 P1 统一系统验收补充

本轮将既有专项报告收敛为一个被动统一入口。输入覆盖 D1 frozen dense-crossing、D2 difficulty profile、D3 M5N2 case/final aggregate、D4 episode/fault case、D5 per-primary/native MOT 和 D7 pair guidance/intercept；D6 只读取写盘 JSON/对象，不加载生产者算法，不参与 AirSim 调度。D3 未提供逐时刻 plan history，因此 churn 保持 unavailable。

报告采用三项硬约束：第一，合同允许、控制允许、模式切换和物理拦截是四个独立观测层，禁止逐级推断；第二，所有数值保留 availability，缺字段不补 0；第三，source schema、SHA256、producer/run、provenance 和在线 truth 审计随 CSV/JSON 保留。多 seed 指标使用固定 RNG 的 percentile bootstrap 95% CI，单 seed 只作描述性结果。D1 rejection、D2 admission、D4 fault/ACK、D5 lock/MOT 和 D7 first-failure 统一进入失败原因分布，但不把失败统计回写控制链路。

该能力关闭 D6 的 P1 聚合与报告代码缺口。正式 4 m/2 m replay、M5N2、D4 fault 和 native MOT 产物现已由统一入口消费；后续新批次缺失 evidence 时继续保持 unavailable。

## 2026-07-12 D1/D2 dense-crossing 标定评估补充

D6 新增独立、只读的 dense-crossing 报告路径。输入为 D1 governed manifest、evaluator-only truth summary 和 D2 10-seed/20-seed calibration 文件；输出按 seed 与算法配置保存，不参与在线关联、算法切换或控制授权。

评估口径固定如下：

1. screening 至少 10 seeds，只选择最佳 GNN 参数配置，不产生主线变更。
2. confirmation 至少 20 seeds，分别比较 GNN baseline、相同 config ID 的最佳 GNN candidate 和轻量 JPDA。
3. 历史 `d6-dense-crossing-evaluation/v1` 使用 IDSW 相对下降 30%、identity continuity 绝对增加 0.10、false track 增幅不超过 10%、p95 loop latency 预算和 truth isolation；其中 `+0.10` 已废弃为 D2 v2 判据。当前统一 system-evidence v2 直接消费 D2 ceiling-aware gate，不在 D6 内重算或覆盖 producer 判决。
4. FilterPy/Stone Soup object adapter smoke 没有端到端身份指标，固定排除；轻量 JPDA 标记为 research approximation，不等同于完整 JPDA filter。
5. IDSW、identity/coverage continuity、false track、RMSE、NIS/NEES、初始化延迟、p95 latency 和 truth leak 各自保留 availability。当前 D2 未提供 NIS/NEES mean 时，报告明确 unavailable。

本轮关闭的是 D6 报告和严格 recommendation 逻辑。正式 AirSim 10/20-seed evidence 已由统一入口消费；是否晋级继续只按冻结门限判定，不因报告接线完成而自动晋级算法。

## 2026-07-12 cooperative-closure-v2 实施复核

D6 已新增完全离线的协同闭环报告器。逐 case/seed/profile 明细完整保留，但 acceptance 按 `profile` 聚合唯一 `seed`；分别构造 resource-target pair、target 和稳定 coalition 三种单位。coalition 只包含至少两个 active primary 的目标，并按 `coalition_id` 跨滚动 version/epoch 合并；版本和 epoch 只作审计 provenance。该口径避免把 pair、target 和 coalition 结果互相回填，也避免把普通单 primary 目标或未激活 reserve 当成联盟失败。

D4 通信矩阵按其真实写盘合同读取：report 顶层的 `cases` 是评估行，`seeds` 只是批次索引；case 使用 `scenario_id` 作为故障分组、`passed` 作为 pass evidence，并原样保留 `fail_closed`。这组别名只在 D4 communication adapter 内生效，避免污染通用 cooperative row 的 `passed` 语义。

共同锁定采用 D5/main 的显式 `common_lock` 证据；没有共同时间窗时不根据单机 `associated` 推断。到达离散使用同一 coalition 内 primary 的 arrival error 极差。第二 primary 按 member order/role 排序，只有 physical outcome 可用时才进入失败分母。所有验收结果均标记 `advisory_only=true`，D6 不参与控制。

2026-07-13 真实 M5N2 summary 包含 40 个 case、4 个 profile、每 profile 10 个 seed。修复后的 profile 选择优先读取 source `best_candidate_profile`，缺失时才采用确定性 fallback；source 最佳 `d3-p1-h020.0-w03.0-s040.0` 得到 `5/10`，其余 profile 为 `0/10、2/10、1/10`，全 profile 完成 `8/40`，与 source aggregates 一致。门限检查因此是 available+failed，而不是 insufficient evidence；unavailable seed 单独计数，不折算为 0。

## 2026-07-12 P1 第二批统一报告补充

D6 已新增独立的 P1 summary 聚合入口，直接消费 main terminal closure 和 D1-D5/D7 的版本化离线产物，不要求 D6 导入生产者模块。统一报告固定输出逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG 概览图，并显式审计 source schema 与 evidence availability。

报告保持两组不可替代的层级：`contract_allowed/control_allowed/mode_switched/physical_intercept` 四层，以及 pair/target/coalition 三层。锁定、允许控制、模式切换和物理命中之间不做推断；M5N2 的任一 pair 命中也不会被回填成 coalition complete。D7 dropout、`png_ttc` 四类拒绝和 trend coast 晋级判据，D4 failover matrix，以及 D2 IDSW/continuity 已进入统一版式。

该实现关闭 D6 的离线消费与报告缺口，但不改变真实试验结论：没有对应 AirSim 文件时字段仍为 unavailable；合成 D1-D4 replay 只能证明 schema、回归和 fail-closed 逻辑可测，不能替代真实多 seed 物理验收。

复核 `p1_terminal_closure_smoke_v2_20260712` 后，D6 增加 main-summary 专项回退。独立 D7 summary 缺失时，版本化 `acceptance.dropout_matrix` 可直接形成完整性/合规性结论，`png_ttc` 和 candidate trend 只聚合逐行显式计数。该 smoke 的 dropout complete/compliant 均为 true，TTC 仅 not-expanding=1，trend 未触发且不建议晋级。执行四层仍等待 main 写出同名字段，不从 pair、switch 或专项结果推断。

**定位**：D6 建立覆盖探测、跟踪、分配、降级、末端配准、通信、D7 gate/intercept 和安全约束的离线评估体系，支持批量实验统计和报告图表。
**边界**：D6 只消费日志，不参与实时控制，不生成任务、分配、导引、火控、毁伤、自动处置或授权绕过流程。
**规模规则**：指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化，并按 `metric_scope/seed/scenario_group/scale` 分组，不从 `2v2/5v5` 场景名推断规模。
**ID 规则**：D2/D6 必须保留显式 `id_switch_count`。

## 2026-07-11 最终实测同步结论

D6 当前没有运行级 P0 blocker。`p1_p2_validation_20260711` 已给出合同层真实验收：CV 10 seeds 中 8/10 有 T001 双 primary 同帧共识与授权，全部 seed 的 IDSW 和错误重复锁为 0；secondary plan v2 executing 3/3、peer distributed executing 3/3、missing-ACK aborted 2/3 且 D7 allowed=0。D6 重放这些 JSONL 后得到相同结果，未发现 loader 错误。

contract/control/switch/physical 四层口径保持严格分离：CV 10 seeds 的 `control_allowed_count=0`、`physical_intercept_count=None`；SimpleFlight 10 seeds 的物理 evidence 可用，但 30 个 active pair 为 0 命中、24 detection timeout、6 timeout。每 seed 均保持 4 bindings、3 active + 1 standby。本批次只有 15 s、`control_dt=0.5 s`，因此合同层 P1 已闭合，物理拦截和导引律效果仍开放。P2 py-motmetrics IDF1/MOTA/MOTP adapter 已实现，HOTA unavailable。D6 当前回归基线为 `77 passed`。

## 2026-07-10 P1 评估补充

本轮在不参与控制的前提下增加了四条可执行评估链路：

| 链路 | D6 输入 | D6 输出 | 当前状态 |
|---|---|---|---|
| 二级接管生命周期 | readiness/plan state、owner/version/lease、fallback/stale 事件 | 状态驻留、activation latency、fallback/lease/stale count | 代码与单元测试完成，待真实 AirSim 多 seed 写盘 |
| YOLO/MOT | D5 frame event、backend、local track、latency/resource、嵌套 offline truth | recall、local-ID continuity、cross-view rate、latency/budget、truth-field violation | 代码与单元测试完成，D6 不加载 `best.pt` |
| 四导引律 | experiment-level law、稳定场景、相同 seed/规模、D7 execution metrics | same-seed CSV/JSON/中文 Markdown/差值曲线 | 代码与单元测试完成，PNG 核心算法不变 |
| 场景库 | stable scenario group/version、tags、difficulty、expected failure、seeds | scenario library JSON、seed matrix CSV、中文 Markdown | 代码与单元测试完成，CI 接线待 main |

availability 规则：状态、latency、recall、continuity 和资源指标缺真实证据时为 `null/unavailable`；显式记录且实际为零时才输出 0。`offline_truth` 永远只用于 D6 评估，不能回流 D4/D5/D7 在线状态。

### 2026-07-11 四导引律真实短 episode 结果

main 修复 experiment-level guidance law 回灌后，D6 已从
`p1_guidance_four_law_smoke_20260711` 生成同 seed CSV、JSON、中文 Markdown 和差值
曲线。结果表有 21 条指标配对行，但每行只配对 seed 7，不能把指标行数当成独立样本
数。四种导引律在 2 秒窗口内全部 timeout，成功率均为 0；PNG VM/TTC 的末端切换允许
率约 0.762/0.810，最小距离约 2.812/2.798 m。

因此当前结论仅是 D6 的回灌、配对、切换率、拒绝数和最小距离报告链路可用。单 seed、
短窗口无法支持最终命中率、置信区间或导引律优劣结论。P1 下一步由 main/D7 运行较长
窗口的真实多 seed 同条件批次，D6 继续离线报告成功/timeout/abort、距离、切换和门控
原因，不修改任何控制或导引逻辑。

main 写盘合同见 D6 README。尤其需要显式写 `readiness_state`、`plan_state`、plan owner/version/lease、`detection_backend`、`tracker_backend`、cross-view candidate/registered count、pipeline latency、CPU/GPU budget、嵌套 `offline_truth`、`experiment_guidance_law` 和稳定 `scenario_group/scenario_version/seed/actual scale`。

## 1. 研究问题

多目标 C-UAS workflow 不能只报告“成功率”。一个 episode 可能最终接近目标，但仍存在虚警高、漏检、航迹断裂、ID Switch、重复分配、高威胁未分配、中心失效后接管慢、D4 reassign pending、D5 末端误配准、D7 terminal switch reject、通信 stale update 或安全约束触发等问题。

D6 的目标是把 D1-D7 和 main runtime 的离线日志统一为可比较、可复现、可画图的系统级指标。D6 的评估结果服务报告和回归分析，不回写控制。

### 1.1 M 对 N 评估补充（2026-07-11）

完整公式、输入事件、聚合层级、12 组合实验矩阵、指标来源和开源候选见 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。框架区分合法 coalition multiplicity 与异常 duplicate，并覆盖 target demand/unmet slots、formation/reconfiguration、simultaneous/wave/hybrid、RMSE/NIS/NEES/geometry、canonical duplicate/cross-node IDSW/common-information rejection、planned/authorized/erroneous lock、same-resource continuity、center replan lifecycle、member loss/digest/stale、messages/bytes/rounds/latency 及 minimum separation/collision risk。

聚合固定为 `frame/member/wave/coalition-version/target-episode/episode/batch`，且 `unavailable/null`、真实 `0`、`not_applicable` 三者不可混用。实验采用 independent、simultaneous、sequential、hybrid primary/reserve 四路线，覆盖中心正常、二级接管、完全无中心和几何/同步/通信/成员失效扰动。现有场景无新增 P0；新增合同与聚合列 P1，现有 P2/P3 保持。

实现状态：D6 已新增 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal 合同并接入 JSONL、`EpisodeMetrics`、CSV、batch summary 和 Markdown。通用同帧多资源锁、授权协同锁、错误重复锁与跨帧同资源连续锁已拆分；探测三项由离线 truth pair gate；五类规范 `center_replan_*` 事件已接入请求/去重/解析/pending/convergence 指标。availability 逐指标记录 status/reason/numerator/denominator。剩余 P1 是上游真实日志与 12 组合多 seed 实验，不是 D6 聚合代码缺口。

## 2. 当前实现状态摘要

已实现：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 指标收集：`MetricsCollector`。
- JSONL：标准化 `truth_summary/track/assignment/target_demand/coalition/arrival/event/link/terminal` loader/writer。
- AirSim Blocks：`load_blocks_replay_jsonl()` 读取 `blocks_frames.jsonl` 与可选 `blocks_sensor_observations.jsonl`。
- main bus：`load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` 读取 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`。
- D4：`load_d4_active_degradation_decisions()` 读取 active-degradation CSV。
- D7：`load_d7_intercept_outputs()`、`load_d7_guidance_timeseries()` 读取 control/guidance/intercept CSV/JSON。
- 报告：episode CSV、summary CSV、Markdown、PNG 图表和批量统计；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表、D4/D5 detect-to-registration 漏斗和 terminal switch/contract reject reason 分布。
- 标准映射：`cuas-standard-map-v1` 已实现 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 最小映射，输出 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`；episode CSV 和 Markdown 报告保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`，并可通过 `ReportGenerator.write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`。
- AirSim calibration：`load_airsim_calibration_records()` 与 `AirSimCalibrationReportGenerator` 读取 D4/D5 stress metrics、AirSim summary 和 main bus metrics，按 `metric_scope/seed/scenario/comparison_role/secondary_height/FOV/secondary_count/detection_backend` 输出 CSV、JSON 和中文 Markdown；P1 二级侦察校准字段覆盖 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，并保留 `scenario_version`、`standard_mapping_version`、`evidence_path`、`trend_key`、`secondary_height_bucket` 和 actual scale 字段。
- main runtime 接入：2026-07-08 起，`--p1-calibration-sweep` 在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 不启动 AirSim、不调度 episode、不控制二级节点或终端关联。
- main/orchestrator 2026-07-07 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 只消费这些写盘结果，不参与控制。
- 2026-07-08 `p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可保留为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。
- 2026-07-08 registration calibration v2 历史基线为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，D6 bundle 已生成 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`；该批次不再表述为当前最新 P1 结论。

部分实现 / 剩余 P1：

- P0：无 P0 blocker；P0-A 标准化评估映射最小版已实现并进入 D6 CSV/Markdown/metadata。
- D7 real execution 的正式/contract 双口径已完成主线；D6 已补 `metric_scope`、main bus metrics JSON loader、reject reason 分布输出和按 seed/scenario/实际规模分组的报告口径。剩余工作是多 seed、5v5/N-v-N 和非默认 episode 持续采用同一双口径。
- D6 已具备 D4/D5/D7/Blocks 离线消费能力，但真实 integrated episode 仍需要 main runtime 在同一 episode 目录写盘、对齐时间轴并调用多个 loader 合并。
- D4 主动降级已能统计次数、secondary takeover/reassignment、pending、窗口 delta、`active_degradation_precision` 和 `unnecessary_active_degradation_count`；必要性/精度只消费真实 episode 写出的 review label 或后验字段，缺 label 不进入 precision 分母。
- D6 已补二级视角/侦察云台指标，能从 main/D4/D5 写盘 metadata 汇总 fixed downlook secondary 与 mobile recon gimbal 的 coverage、cross-view、D5 registration miss、projection/gate/stable registration 和 cue/gimbal pointing error；2026-07-08 历史 registration calibration v2 为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3，指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。
- 2026-07-09 P1 AirSim calibration Markdown 已新增 50m vs 200m 二级覆盖对比、coverage funnel、baseline vs enhanced 表格和 D7 guidance reject reason 表；baseline/enhanced 只消费显式 comparison role，不从 `2v2/5v5` 场景名推断规模或实验组。
- 2026-07-10 已保留旧逐 seed 产物并新增 cross-seed aggregate、严格 baseline/enhanced seed 配对、missing seed、paired delta mean/std、Cohen's dz 和固定 RNG 的 2000 次 bootstrap 95% CI。真实 runtime 的 `scenario_version` 含 seed 参数，D6 统计键现仅移除该运行参数，原值继续留在 records；单 pair 标记 `descriptive_only`，不产生推断 CI/effect size。剩余 P1 聚焦至少两个真实配对 seed、N-v-N 数据和 review labels 验证；D6 继续只消费日志，不参与控制。

- 2v2 回灌专项已复核：`p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的正式 execution main-bus 指标为实际规模 `2/2/2/2`、成功拦截 2、视觉 PNG 切换 3，contract 指标单独保留。Blocks summary 的 legacy integrated snapshot 仍是过时 `3/3/2/0`；D6 loader 不消费该快照，并通过 fixture 测试固定 execution/contract 优先级与 evidence path。上游 summary 对齐由 main 负责。

- 2v2 10-seed 拦截报告专项已完成：AirSim calibration record/CSV/summary/cross-seed 新增 success、collision/range/abort、min range、time-to-intercept、visual PNG switch、terminal switch allowed/takeover 和 gate reject。availability gate 要求 intercept summary/control command/显式 pair-status/D7 execution event 证据，episode_001..005 read-only 默认零因此为 unavailable 且不进入 Outcome 表。对 `seed001..010` summaries 的离线验收仍得到 full-flow execution `18/20=0.9`、collision/range/abort=`18/0/2`；contract 保持独立并由 scope 明示。D6 仍不参与控制。

- D6 owner 2026-07-11 当前回归基线为 `77 passed`。除既有能力外，coalition epoch/lease/member ACK/commit failure 指标、secondary/distributed commit、terminal contract/control/mode/physical 分层指标和 py-motmetrics adapter 已闭合；CV 8/10 与 commit/fail-closed 已提供合同层 evidence，后续 schema 回归必须继续区分 CV physical unavailable 与 SimpleFlight physical=0 available。

未实现：

- Stone Soup metrics、TrackEval、OSPA/GOSPA 和 HOTA 标准输出。py-motmetrics 的 IDF1/MOTA/MOTP 已实现为隔离式 P2 adapter。
- AirSim 原生 recording parser 和 live AirSim replay/API。
- SCRIMMAGE metrics bridge。

## 3. 指标体系

| 类别 | 已实现指标 | 含义 |
|---|---|---|
| 探测 | `detection_probability` | 真值机会中被检测到的比例 |
| 探测 | `false_alarm_rate` | 单位时间虚警数 |
| 探测 | `missed_detection_rate` | 漏检比例 |
| 跟踪 | `track_rmse` | 航迹位置与真值的均方根误差 |
| 跟踪 | `track_continuity` | 真值 timestamp 被匹配覆盖的比例 |
| 跟踪 | `id_switch_count` | 同一 `truth_id` 对应 `global_track_id` 变化次数 |
| 分配 | `duplicate_assignment_count` | 同一 plan snapshot 中多个资源分配到同一目标 |
| 分配 | `unassigned_high_threat_count` | 评估侧高威胁目标未被有效 active assignment 覆盖 |
| 降级 | `failover_time` | 中心失效到降级稳定的平均耗时 |
| 降级 | `consensus_rounds` | 离线记录的协商轮数均值 |
| 降级 | `degraded_completion_rate` | 降级任务完成比例 |
| 降级 | `active_degradation_count` | D4 主动降级决策次数 |
| 降级 | `active_degradation_precision` | 有 review/后验标签的主动降级中必要标签比例 |
| 降级 | `active_degradation_label_count` | precision 的可分类 review-label 分母；为 0 时 precision unavailable/null |
| 降级 | `unnecessary_active_degradation_count` | 有 review/后验标签且判为不必要的主动降级次数 |
| 降级 | `passive_failover_count` | 被动 failover 次数 |
| 降级 | `secondary_node_takeover_count` | 二级节点接管/协助次数 |
| 降级 | `secondary_reassignment_count` | 二级节点重分配次数 |
| 降级 | `d4_reassign_pending_count` | D4 重分配未完成导致的 pending/reject |
| 降级 | `distributed_fallback_count` | 分布式 fallback 次数 |
| 降级 | `failover_active_window_delta_s` | active window 与 failover/takeover 之间的平均 delta |
| 末端 | `terminal_association_accuracy` | D5 末端局部绑定正确率 |
| 末端 | `terminal_id_switch_count` | 同一 `assigned_global_track_id` 下 local visual ID 变化次数 |
| 末端 | `ambiguous_fov_event_count` | 末端视场歧义事件数 |
| 末端 | `friend_overlap_hold_count` | 友方 overlap 导致 hold 的事件数 |
| 末端 | `time_to_terminal_lock` | FOV entry 到 terminal lock 的平均时间 |
| 末端 | `terminal_lock_count` | 唯一 terminal lock 事件/记录数 |
| 末端 | `multi_view_consensus_rate` | 多视角一致成功比例 |
| 末端 | `cross_view_conflict_count` | 跨视角绑定冲突数 |
| 末端 | `duplicate_terminal_lock_count` | 同一目标被多个资源重复锁定次数 |
| 二级视角 | `secondary_network_joint_full_view_frame_rate` | 二级网络联合 full-view frame 比例 |
| 二级视角 | `secondary_network_mean_coverage_ratio` | 二级网络按实际 target count 归一化的平均覆盖比例 |
| 二级视角 | `secondary_visible_target_union_ratio` | 二级网络可见目标并集比例 |
| 二级视角 | `secondary_single_camera_full_view_frame_rate` | 单相机 camera-frame full-view 比例 |
| 二级视角 | `secondary_detect_count` | 二级检测机会计数 |
| 二级视角 | `projection_valid_rate` | GlobalTrack 投影到二级相机图像平面后有效的比例 |
| 二级视角 | `geometry_gate_pass_rate` | D5 几何门控通过比例 |
| 二级视角 | `registered_candidate_count` | 单帧/候选级注册候选计数 |
| 二级视角 | `stable_cross_view_registration_count` | 多帧稳定跨视角注册计数 |
| 二级视角 | `not_registered_count` | 二级检测未注册到既有 global track 的计数 |
| 二级视角 | `cross_view_association_count` | D5/main 写盘的跨视角配准成功计数 |
| 二级视角 | `secondary_detect_available_but_not_registered_count` | 二级检测可用但 D5 未注册计数 |
| 二级视角 | `cue_pointing_error_*` | cue 指向误差 count/mean/rmse/max |
| 二级视角 | `gimbal_pointing_error_*` | 云台指向误差 count/mean/rmse/max |
| 通信 | `cross_node_latency_ms` | 跨节点平均 latency |
| 通信 | `message_drop_rate` | 消息丢弃比例 |
| 通信 | `out_of_order_count` | 显式乱序事件和序列号倒退 |
| 通信 | `stale_track_update_count` | 超过 stale threshold 的 track payload |
| 通信 | `video_metadata_delivery_rate` | video metadata delivery 比例 |
| 通信 | `bbox_delivery_rate` | bbox delivery 比例 |
| 通信 | `consensus_latency_s` | consensus/bid 或 start-to-stable latency |
| D7 gate | `camera_quality_gate_pass_rate` | 相机质量 gate 通过率 |
| D7 gate | `los_quality_gate_pass_rate` | LOS 质量 gate 通过率 |
| D7 gate | `maneuver_margin_gate_pass_rate` | 机动余量 gate 通过率 |
| D7 gate | `terminal_switch_allowed_rate` | D7 允许末端切换的 command 比例 |
| D7 gate | `visual_png_switch_count` | 切换到视觉 PNG/PNG guidance 相关模式的次数 |
| D7 gate | `terminal_takeover_rate` | unique pair 中进入末端接管的比例 |
| D7 gate | `terminal_switch_reject_count` | 末端切换拒绝次数 |
| D7 intercept | `mode_switch_count` | guidance mode switch 次数 |
| D7 intercept | `terminal_contract_reject_count` | terminal contract reject 次数 |
| D7 intercept | `intercept_success_count` | 离线成功状态计数 |
| D7 intercept | `collision_intercept_count` | collision threshold 命中计数 |
| D7 intercept | `range_intercept_count` | range threshold 命中计数 |
| D7 intercept | `time_to_intercept_s` | 达到拦截状态的平均时间 |
| D7 intercept | `min_range_m` | episode/pair 最小距离 |
| D7 intercept | `gate_reject_count` | gate/reject 事件总数 |
| 安全 | `constraint_violation_count` | 安全约束违反次数 |
| 安全 | `human_override_count` | 人工覆盖或拒绝次数 |

## 4. 日志模型

### 4.1 Tracking / Detection

```text
TrackRecord
- timestamp
- global_track_id
- truth_id
- position
- truth_position
- covariance_trace
- track_state
- association_source
```

要求：

- `global_track_id` 由中心/上游维护，D6 不重写。
- `truth_id` 是离线评估标签，不可进入在线 D5/D7 控制判断。
- D1 输出应保留测量时间、到达时间和协方差；D6 通过记录或 link metadata 消费这些信息。

### 4.2 Assignment

```text
AssignmentRecord
- timestamp
- plan_id
- version
- resource_id
- global_track_id
- cost_breakdown
- authorization_state
- active
- truth_id
```

D6 只统计 active 且有效授权状态的分配。stale plan reject 由 D3/main 在线链路负责，D6 可在日志中统计结果但不执行拒绝。

### 4.3 Event

```text
EventRecord
- timestamp
- event_type
- actor_id
- severity
- note
- value
- metadata
```

典型事件：

```text
central_failure
degraded_stable
consensus_rounds
degraded_task_completed
degraded_task_failed
active_degradation_decision
passive_failover
secondary_node_takeover
secondary_reassignment
d4_reassign_pending
distributed_fallback
terminal_lock
terminal_fov_entry
terminal_ambiguous_fov
friend_overlap_hold
multi_view_consensus_result
cross_view_conflict
duplicate_terminal_lock
d7_control_command
d7_guidance_record
d7_intercept_pair_summary
constraint_violation
human_override
```

### 4.4 Link

```text
LinkRecord
- timestamp
- source_node_id
- target_node_id
- relay_node_id
- link_type
- message_type
- sequence_id
- sent_timestamp
- received_timestamp
- measurement_timestamp
- arrival_timestamp
- payload_kind
- delivered
- stale_after_s
- metadata
```

`measurement_timestamp` 和 `arrival_timestamp` 必须保留，用于 stale 和 latency 统计。

### 4.5 Terminal

```text
TerminalRecord
- timestamp
- resource_id
- assigned_global_track_id
- local_track_id
- decision_state
- ambiguity_score
- friend_conflict_state
- assignment_version
- expected_global_track_id
- association_correct
```

D5 不得本地改写 `global_track_id`。D6 只统计末端绑定与中心/评估标签的一致性。

## 5. AirSim / D4 / D5 / D7 接入方案

### 5.1 Blocks replay

已实现 `load_blocks_replay_jsonl()`：

- `blocks_frames.jsonl` 提供 truth objects、resources、cameras、visual detections、image metadata。
- `blocks_sensor_observations.jsonl` 提供 D1 replay observation 和 communication metadata。
- D6 从中构建 truth summary、实际规模字段、visual track、terminal records、video metadata links、bbox links、multi-view consensus/conflict。
- PNG 不必保存；`metadata.images[].path` 只进入 `png_saved` 元数据。

### 5.2 Main bus metrics

已实现 `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()`：

- 读取正式 execution `main_episode_bus_metrics.json` 和 raw contract `main_episode_bus_contract_metrics.json`。
- 把已写盘 `metrics` payload 还原为 `EpisodeMetrics`，保留 `metric_scope`、seed、`scenario_group`、实际规模字段和 metadata。
- 可消费 `terminal_switch_reject_reasons`、`terminal_contract_reject_reasons`、`guidance_law_counts`、D7 intercept/guidance 指标等由 main/D7 合并出的字段。
- 只读文件，不运行 AirSim，不触发 D7 执行，不合并或覆盖控制链路结果。

### 5.3 D4

已实现：

- D4 active-degradation CSV loader。
- 主/被动降级、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因分布。
- `review_label`、`active_degradation_necessary`、`post_window_outcome`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段离线消费。

长期 producer schema 治理：

- 持续写出真实 episode 的 D4 决策日志。
- 在每个 episode 稳定提供 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`。
- 固定 pre/post 窗口，支持真实数据中的必要性、改善 delta、decision latency、ID switch delta 和 assignment conflict delta。

### 5.4 D5

已实现：

- D6 指标和数据模型可消费 D5 terminal/multi-view 日志。
- Blocks replay 可提供无 PNG 的 bbox/camera metadata 基线。
- 二级视角指标可消费 `secondary_node_type=fixed_downlook_secondary/mobile_recon_gimbal`、coverage/full-view、cross-view association、detect-available/not-registered 和 cue/gimbal pointing error metadata。

长期 producer schema 治理：

- 写出 terminal association、identity claim、terminal-center disagreement、cross-view conflict、duplicate lock、friend overlap hold、validation label。
- 保留 bbox、相机内外参、timestamp、`resource_id/camera_id`、`local_track_id`、`assigned_global_track_id`。
- 为移动侦察云台节点稳定记录几何、FOV、分辨率、cue source、目标覆盖集合/计数、cross-view association 结果、D5 registration 状态和指向误差。
- 2026-07-08 mobile recon stress 已写出 `mobile_recon_gimbal`、`mobile_high_recon`、coverage、bbox、funnel breakpoint 和 gimbal OK 指标，是 D6 消费该类字段的历史证据；同日 registration calibration v2 进一步写出 height 200 m、FOV 110 deg、secondary_count 3、projection/gate/stable registration/not-registered/D7 reject 指标，并由 D6 bundle 汇总。两者均保留为历史基线。

### 5.5 D7

已实现：

- D7 control/guidance/intercept 文件 loader。
- gate pass rate、switch allowed/reject、visual PNG switch、takeover rate、mode switch、contract reject、intercept counts。
- `metadata` 中保留 guidance law、reject reason、D4/D5 state、plan/version。

main/orchestrator 已完成：

- 真实执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`。
- 执行前合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 gate/reject，而不覆盖执行后拦截结果。

长期 producer schema 治理：

- 每个 integrated AirSim episode 稳定写出 D7 文件。
- 在多 seed、5v5/N-v-N 和非默认 episode 中保持正式 metrics 与 raw contract metrics 的双口径，并让 D6 报告继续按 `metric_scope/seed/scenario_group/scale` 分组。

## 6. 开源工具与外部 benchmark

| 工具/接口 | 当前实际状态 | 原因和条件 |
|---|---|---|
| Stone Soup metrics | 未使用 | 需要 Stone Soup 版本锁定、D1/D2 到 `Track/Detection/GroundTruthPath` 的 adapter、坐标/门限合同和 CI fixture |
| TrackEval | 未使用 | 需要 MOTChallenge 格式或等价 frame-level export、IoU/距离门限和依赖容差 |
| py-motmetrics | 已隔离使用 `motmetrics 1.4.0` | `msm-offline-mot-v1` 提供 accumulator 输入；输出 IDF1/MOTA/MOTP，HOTA unavailable |
| OSPA/GOSPA | 未输出字段 | 需要 truth/estimate set 序列、cutoff/order、birth/death/遮挡规则 |
| HOTA | unavailable；py-motmetrics 1.4.0 不支持 | 需要支持 HOTA 的 evaluator、完整帧级检测/关联/身份评估表和遮挡规则 |
| AirSim 原生 recording parser | 未实现 | Blocks JSONL 已满足当前主线；原生 recording 需要样例、schema、坐标和时钟映射 |
| Live AirSim replay/API | 未实现且非 D6 目标 | D6 只读文件；live replay 应由 main runtime 执行并导出日志 |
| SCRIMMAGE metrics | 未实现 | 当前无 SCRIMMAGE 输出样例、message schema、ID 映射和 episode clock 合同 |

这些外部项是 P2/P3 的可选 benchmark 或扩展，不替代当前本地离线指标。

## 7. 批量统计与报告

当前报告生成：

```text
episode_metrics.csv
summary_metrics.csv
standard_metric_mapping.csv
batch_report.md
plots/detection_metrics.png
plots/tracking_metrics.png
plots/assignment_metrics.png
plots/degradation_metrics.png
plots/terminal_metrics.png
plots/secondary_sensing_metrics.png
plots/communication_metrics.png
plots/guidance_metrics.png
plots/safety_metrics.png
plots/selected_metric_distributions.png
```

`episode_metrics.csv` 保留每个 episode 的 metadata JSON、`scenario_version`、`standard_mapping_version` 和 `standard_metric_family_summary`。`standard_metric_mapping.csv` 保留固定版本 `cuas-standard-map-v1` 的本地指标到标准 C-UAS family 映射。`batch_report.md` 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表，并在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表，以及 terminal switch/contract reject reason 分布，便于对比 execution/contract 双口径下的拒绝原因。

AirSim calibration bundle 额外输出：

```text
airsim_calibration_records.csv
airsim_calibration_summary.csv
airsim_calibration_summary.json
airsim_calibration_report.md
```

该 bundle 保留原逐 seed 分组与文件，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。配对键包含稳定 `scenario_group`、移除运行 seed 参数后的 `scenario_version`、实际 N/M/camera count、几何、backend 和 seed；case_name 只审计。单 pair 只描述，不输出推断 CI。active-degradation 显式标注优先读取 d4d5 stress metrics，再 fallback main metrics。

统计量：

```text
count
mean
sample_std
stderr
normal-approximation 95% CI
median
p05
p95
```

偏态或长尾指标在正式结论前应补 bootstrap 或非参数 CI；当前实现满足工程回归和批量对比。

## 8. 示例实验报告模板

```text
实验名称：
episode / batch seed：
metric_scope：execution / contract / not_recorded
scenario_group：
实际规模：
- drone_count:
- resource_count:
- target_count:
- camera_count:

数据来源：
- synthetic / Blocks JSONL / D4 CSV / D5 terminal JSONL / D7 CSV+JSON
- 是否保存 PNG:

探测：
- detection_probability:
- false_alarm_rate:
- missed_detection_rate:

跟踪：
- track_rmse:
- track_continuity:
- id_switch_count:

分配：
- duplicate_assignment_count:
- unassigned_high_threat_count:

降级：
- active_degradation_count:
- active_degradation_precision:
- unnecessary_active_degradation_count:
- passive_failover_count:
- secondary_node_takeover_count:
- secondary_reassignment_count:
- d4_reassign_pending_count:
- distributed_fallback_count:
- failover_time:
- consensus_rounds:
- degraded_completion_rate:

末端：
- terminal_association_accuracy:
- terminal_id_switch_count:
- ambiguous_fov_event_count:
- friend_overlap_hold_count:
- terminal_lock_count:
- time_to_terminal_lock:
- multi_view_consensus_rate:
- cross_view_conflict_count:
- duplicate_terminal_lock_count:

二级视角/侦察：
- secondary_network_joint_full_view_frame_rate:
- secondary_network_mean_coverage_ratio:
- secondary_visible_target_union_ratio:
- secondary_single_camera_full_view_frame_rate:
- secondary_detect_count:
- projection_valid_rate:
- geometry_gate_pass_rate:
- registered_candidate_count:
- stable_cross_view_registration_count:
- not_registered_count:
- cross_view_association_count:
- secondary_detect_available_but_not_registered_count:
- cue_pointing_error_mean_deg:
- gimbal_pointing_error_mean_deg:

通信：
- cross_node_latency_ms:
- message_drop_rate:
- out_of_order_count:
- stale_track_update_count:
- video_metadata_delivery_rate:
- bbox_delivery_rate:
- consensus_latency_s:

D7 gate/intercept：
- terminal_switch_allowed_rate:
- visual_png_switch_count:
- terminal_takeover_rate:
- terminal_switch_reject_count:
- mode_switch_count:
- terminal_contract_reject_count:
- intercept_success_count:
- collision_intercept_count:
- range_intercept_count:
- time_to_intercept_s:
- min_range_m:
- gate_reject_count:

安全：
- constraint_violation_count:
- human_override_count:

结论：
- 主要失效模式：
- 长尾风险：
- 需 main/D4/D5/D7 补充的日志：
- 是否需要人工复核：
```

## 9. P1 最终开放项

1. **长期 multi-seed 趋势**：按冻结 scenario/version/profile/actual scale 持续形成跨提交趋势、门限稳定性、paired effect size 和 bootstrap CI；单批次结果不外推为长期结论。
2. **producer 逐时刻 schema**：统一 episode clock、version/epoch、provenance 和 availability，优先补 D3 有序 plan history/churn；缺逐时刻记录时 churn 必须保持 unavailable。
3. **跨批次失败原因治理**：冻结 reason taxonomy 和 schema version，明确 unknown、unavailable、not_applicable 与显式零，避免不同 producer 对同一失败重复计数或名称漂移。

现有 execution/contract 四层、M5N2 profile、native MOT、D4 fault 和 dense-crossing 结果只需继续回归，不再列为首次接入缺口。

## 10. P2 可选离线对照

以下工具不进入默认依赖、默认七源报告主线或在线控制路径，只在 evidence schema 和样本条件满足时单独运行：

1. `msm-offline-mot-v1` 最小 frame-level truth/detection/track schema 已完成；下一步只补真实 replay fixture 与门限版本。
2. py-motmetrics adapter 已完成；使用真实冻结 replay 校准距离门限。TrackEval/HOTA 仍为可选 benchmark，HOTA 不得由现有指标推断或伪造。
3. 接入 Stone Soup 与 OSPA/GOSPA 作为论文级对照。
4. 为长尾指标增加 bootstrap/非参数 CI。
5. 有真实 SCRIMMAGE schema 和样例后再把 SCRIMMAGE bridge 作为 P3 可选项评估。
6. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。

## 11. 验收命令

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

## 12. 参考资料

- Stone Soup metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.tracktotruthmetrics.html>
- Stone Soup OSPA metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.ospametric.html>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim APIs: <https://microsoft.github.io/AirSim/apis/>
- AirSim recording: <https://microsoft.github.io/AirSim/modify_recording_data/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>

## 13. 2026-07-12 P1 汇总接口评审结论

本轮 D6 以新增 `P1SystemEvidenceReportGenerator` 的方式扩展现有报告体系，未修改旧 `P1AcceptanceReportGenerator` 的字段和验收口径。该接口只读取 producer 已写盘 JSON-like summary，不导入 D2-D5/D7 在线模块，也不控制 AirSim。

评审结论：

1. D5 native MOT admission 已能按 backend、camera、resource 输出 native/fallback、precision/recall、continuity、local IDSW、P95 latency 和拒绝原因。
2. D2 六难度结果按 difficulty profile 和 candidate 保留，IDSW 仍为必须项，non-discriminative 场景不会被隐藏。
3. D3 接口可把普通 plan refresh 与 coalition membership/version/epoch churn 分开统计，per-primary 与 arrival coordination 配置进入证据行；本批正式 aggregate 没有逐时刻 history，因此 churn 仍为 unavailable。
4. D4 按真实 tick 序列统计通信和接管状态，中心失效后的无 owner fail-closed 阶段不会被过滤。
5. D7 的合同允许、控制允许、模式切换和物理拦截为四个独立 availability-aware 指标，不允许相互反推。
6. 汇总输出不包含 raw truth ID；precision/recall/IDSW 只作为离线评估结果消费，显式在线 truth 使用单独报错。

当前 D6-owned 代码缺口已闭合，正式 AirSim 多 seed 产物已经写盘并由 main 调用 D6 统一入口生成报告。剩余 P1 仅为长期趋势、逐时刻 producer schema 和跨批次失败原因治理；D6 不应把接口可用误写成算法通过 admission，也不把缺失时序证据补成 churn。

## 14. Native MOT 专项评审（2026-07-12）

早期专项报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_native_mot_20260712/`；最终七源统一报告已消费正式 native MOT execution index 的 18 条记录。旧专项的 discovery/range/confirmation 分层只作历史过程记录，不替代最终 source manifest 行数。

评审结论：20 m confirmation 的两种原生 MOT 都保持连续、无 IDSW、无 fallback；ByteTrack P95 约 8.292 ms，低于 BoT-SORT 的 18.232 ms。两者离线 precision/recall 分别约 0.324 和 0.293，均未通过准入。30/50 m 短检查无接受检测。当前只能确认 20 m 原生跟踪运行稳定，不能确认检测准确性达标，也不能确认 30/50 m 可用。

D6 报告接口状态为完成；算法准入状态仍为拒绝。下一步先核对离线 truth 框、IoU/几何门限和时间对齐，再由 main/D5 复跑多 seed confirmation。D6 不参与在线检测、跟踪或阈值放宽。

## 15. Main Bus 执行指标合并评审（2026-07-13）

D6 新增 `d6.execution-metrics-merge.v1`。该接口解决历史 integrated replay 与实际 main bus 执行指标分裂的问题，不修改现有 `EpisodeMetrics` 和 loader，也不参与在线控制。

评审结论：

1. replay 继续保留离线评估结果，main bus 只对终端、cross-view、在线 truth、合同/控制/切换和物理执行字段拥有规范优先级，避免扩大覆盖范围到 D1-D3 离线指标。
2. 所有覆盖均可审计：输出同时保存两侧值、availability、source path 和 selected source，历史 replay 值不会丢失。
3. 缺失 execution 时 `execution_metrics_merged=false`，缺失指标为 unavailable，不因 `EpisodeMetrics` 默认字段而制造执行证据。
4. 持久化 11 帧与包含 warmup 的 12 帧按两个字段记录，D6 不假设两者固定相差一帧。
5. main 仍负责调用和写盘；本轮 D6 只提供纯函数、包导出、单元测试和文档合同。
