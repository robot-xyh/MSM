# Main 实现差距总审计

**审计来源**：D1-D7 子智能体分别对照 `subagent_reviews/*_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和各自 `research_modules/` 代码完成自查。
**审计目标**：列出共识算法与计划使用的开源代码哪些已经实现，哪些没有实现，为什么没有实现，以及缺少哪些条件。
**边界**：本文只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控或绕过授权的自动动作。

**P0/P1 状态入口**：本文是 main 层唯一的实现差距与 P0/P1 状态入口，集中维护 owner、当前状态、缺少条件和验收口径。2026-07-14 canonical actual-execution 证据链已完成真实 AirSim seed-1 复验：tuned 2v2 与 M5N2 均生成并通过校验的 `d7-actual-execution-metrics-v2`，不存在 unavailable artifact；`control_commands.csv`、`intercept_summary.json` 和 actual envelope 的物理成功数一致，控制计划 ID 与同一个 canonical D3 history 一致，身份和状态在线真值使用计数均为 0。2026-07-15 main/D6 进一步关闭“只有总耗时、无法定位预算违例阶段”的 P1 可观测性实现缺口；随后复核并关闭 D4 多入口二级接管证据不一致的系统级 P0 边界，以及 D2 continuity 固定 `+0.10` 在高基线下不可达的 P1 准入规则缺口。同日第二次只读审计发现 D4 两个公开 helper 仍把部分缺失证据 `None` 当成“非 False”放行；D4 owner 已改为 exact-true/fail-closed，补齐逐字段缺失负例并完成跨模块回归。D2/D6 随后已用原冻结 replay 生成 ceiling-aware v2 正式联合证据：总体 GNN 候选五项 gate 通过，但只有 `clutter`、`combined` 两个 difficulty 通过，dropout truth alignment 仍为 partial，JPDA 不准入，因此只形成 promotion review，默认 GNN/Hungarian 不变。最新相关回归为 D2 `113`、D4 `280`、D6 `272`、AirSim runtime `157`、integrated point-mass `7`；当前无开放运行级或证据级 P0 blocker。P1 继续包括 D3 长期 churn、M5N2 第二 primary/物理联盟、candidate `3/2/1` 机会合同、ClockSpeed 与顺序控制 RPC 解耦、D5 30/50 m 与 native MOT 准入、真实二级网络时序、D2 候选的跨 difficulty/完整系统评审，以及基于新分阶段证据达到 100 ms 实时预算。P2 仍只在隔离环境评估，不替换默认 NumPy/SciPy/PN/PNG/detect 路径。

**当前状态修订（2026-07-20）**：上段“无开放 P0”只对应此前 AirSim 审计。900-episode
正式生成在第 210 项发现 D5 同流多批次阻塞；以下专项记录为当前状态，优先级高于历史摘要。

## 2026-07-21 运行采用、离线结果与跨视角数据收敛

当前没有新增 P0。D3、D4、D5 的学习数据 producer 已完成全样本结构审计，main 的配对实验
矩阵固定使用 `sensor_random_schedule_version=entity_fixed_v1`，并持久化外生配置 SHA-256。
冻结 900 episode 保持只读，在线真值使用为 0。学习运行状态继续固定为
`PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true`。

D4 新增 `d4-region-resource-runtime-ack-evidence-v2`。它把区域建议采用分为
`new_execution_plan_applied` 和 `evaluation_refresh_applied`。真实 main 5v5、seed 41 的同计划
刷新链为 source D3 seq 10、current D3 seq 94、consumption seq 96、D7 seq 99、ACK seq 100。
计划编号和版本均保持 v1，资源绑定、联盟和 authority 执行签名不变，因此只准入评估刷新；
刷新标志、binding/coalition、执行签名或前序计划证据被篡改时失败关闭。D4 当前全量
`430 passed`。该证据不等于新执行计划、成员 ACK、物理结果或奖励。

D6 新增运行时确认到离线三维结果的严格联接。真实 main 3v3 episode 的 2 条 ACK 被识别为
1 条新计划身份和 1 条同身份评估刷新，按 ACK sequence/timestamp 形成 6 个非重叠资源-航迹
窗口。D2 离线身份映射、三维真值状态、五米接近事件和 11 项输入 SHA-256 均在消费前校验；
在线真值使用为 0。窗口输出起始、终止、最小距离和有界距离进展诊断，但该诊断不是 D3
正式近端策略优化奖励，也不构成反事实或因果证据。D6 全量 `423 passed`。main 已把 11 项
输入清单、JSON、中文报告和 provenance manifest 自动接入有运行时 ACK 的 episode，scalable
3D 全量 `90 passed`。

D5 对冻结正式图语料的 99 条未标注边完成逐条审计。原导出没有保存可核验 source-observation
lineage，99 条全部保持 unavailable，没有使用最近邻或轨迹连续性伪标签。独立困难样本课程已在
detached clean 提交 `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 上复生：4,500 帧、
66,726 个匿名局部航迹节点、245,032 条默认几何门候选边，正/负/未标注为
`57,292/187,740/0`。补充 manifest、dataset manifest 和 composite view SHA-256 分别为
`4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32`、
`4c49aebae8040f8a7dace329b5d1769739e2e40d811c3ad5eb733f302ebd8f6f` 和
`11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。数据支持与训练数据
来源门为 pass；尚未训练新模型、未生成 `.pt`，promotion 状态为
`awaiting_new_model_evidence`，G1 和 assist 继续关闭。

当前 P1 按以下顺序推进：先在 clean composite view 上训练新的 D5 图模型并完成内部独立测试；
再使用保留 seed `1000-1019` 做未见场景评估；随后建立规则与学习候选的同 seed paired shadow，
要求身份交换、错误合并、重复分配和安全违规不恶化；最后生成多 seed 的实际学习采用、运行确认
和物理结果证据。D3/D4 的有界诊断需另行冻结正式 reward 口径。上述门完成前不启动 PPO，
不开放在线辅助或控制权限。

## 2026-07-21 跨模块学习数据联合准入

D6 owner 已实现 `d6.cross-module-learning-data-admission.v1` 只读审计和命令行入口。审计显式
消费 training/shared seed registry、D3 正式 manifest、D4 正式 manifest 与独立 canonical view、
D5 tracklet/active-vision 正式 manifest/view/readiness、D4/D5 补充课程 summary，以及 D5 补充
主动视觉全样本审计和带外文件 SHA。正式观测语料、补充规则课程、逐样本审计、离线评分标签和
运行时 ACK 分层发布，来源混用、哈希篡改、dirty source、错误 seed、保留 seed 泄漏和 synthetic
ACK 冒充 runtime ACK 均失败关闭。

main 使用冻结的 900 episode 制品独立复跑。100 个训练 seed 的规范切分为 60/20/20，保留 seed
`1000-1019` 泄漏为 0，在线真值使用为 0。D4 补充课程的 hold/replan/nonzero quota/transfer 为
`100/200/200/100`；D5 补充课程为 100 episode/800 segment/1200 sample，四类 intent 为
`200/600/200/200`，wide/zoom 为 `1000/200`，拦截/侦察角色各 600。synthetic ACK
applied/rejected/missing 各 400 只算故障注入覆盖。D5 tracklet 的 480 条候选边中 381 条已标注、
99 条未标注，离线标签状态为 partial。

随后 D5 owner 对 clean 补充课程完成 100 episode/1200 sample 全样本审计：302/302 个受清单约束
文件、1200/1200 个 35 维有限特征、规范 episode/sample `60/20/20` 与 `720/240/240` 全部通过，
在线真值、保留 seed、dirty episode 和身份改写均为 0。审计文件/内容 SHA-256 为
`9a03653538e6dae054da8c127ad4a20aae2481af6c9bbef987edfddff0b423d3` 和
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。

D6 已重新消费该证据。当前结论为 BC canonical view available，D5 supplemental full-sample
complete，D3/D4 full-sample pending，跨模块总状态 partial。reward、outcome、counterfactual、
causal、真实 runtime ACK 和 paired shadow 仍 unavailable；PPO、在线 assist 和 authority 均关闭，
规则回退强制。联合报告 JSON/中文 Markdown SHA-256 为
`d3e3e858a14fb570cd0eb19da2661ce76686906530e313b5f79e6bf6af336de2` 和
`aaaeaefd99f38a03e4f80ffa96dabcb0eef0dd9724cb38fdb163c0bf603eff21`。专项 `21 passed`、D6
全量 `385 passed`；main 复算正式 43,973 个文件的树 SHA-256 仍为
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

开放 P1 转为：逐样本审计 D3/D4 canonical views；producer 持久化真实动作采用、版本绑定、
runtime ACK、终局 outcome 和可归因 reward；建立同 seed paired shadow；最后使用保留 seed
`1000-1019` 做独立模型验收。上述条件未闭合前不启动 PPO，也不允许学习策略进入在线控制权限。

## 2026-07-20 三维学习数据容量与吞吐复核

九类 200v200、每例 2 秒的 clean-tree 容量探针已完成。9/9 episode 状态有限，在线真值
使用为 0；D3、D4 和 D5 跨视角图正常最终化，D5 主动视觉因三 seed 不满足 20 个未见测试
seed 而保留 staging。九个 episode 的最终学习目录为 55.36 MB；全部 900 例均按本轮
200v200 平均值计算的存储保守上界为 5.54 GB。存储 P1 门已关闭，5 GB 运行中停止门保留。

同一 nominal seed 930-932 的第二轮 clean-tree 复测由提交
`45b36500dc3c6935b1f116614993e291041eb12d` 产生，完整生成达到 `467.8007→144.5513 s`，
staging `225.9243→12.4372 s`，批次 finalization `116.5624→7.2777 s`；episode run
`125.2205→124.7415 s`。D5 active-vision 三 seed 为
`4.0494/3.9898/3.9995 s`，由上一轮 `41.5623/43.2639/41.2271 s` 降低约一个数量级。
三场均为有限状态、`repository_dirty=false`、在线真值使用 0。D5 仍占 staging 96.8%，
但写入与最终化合计 19.7 秒，低于 episode 计算 124.7 秒，D5 writer 系统级 P1 阻塞关闭。
runner 已实现 episode 边界暂停、同计划/同提交恢复、连续 progress 与 staging index 复核。
2026-07-20 正式生成先完成两个 45-episode 分块，90/90 均为有限状态、干净提交且在线真值
使用为 0。连续运行随后完成到 209/900，在第 210 项
`communication_degraded 200v200 seed 64` 暴露 D5 同一相机流单次多批次边界异常并退出。
该目录没有最终化，不能作为正式训练集；D5 修复改变提交后必须从零重跑，禁止混合提交。

本次退出同时暴露旧 checkpoint 只在显式暂停时更新，导致 progress 为 209 而 checkpoint
停在 90。main 已升级 `scalable3d-learning-generation-checkpoint-v2`：每个完整 episode
同步写 progress 后原子推进 checkpoint；旧 checkpoint 滞后仅在 progress、staging、计划顺序和
安全字段全部通过时恢复，并记录恢复次数和行数。checkpoint 领先、staging 不完整、提交改变仍
失败关闭。开发定向测试 13/13 通过；正式 900 episode 复跑尚未完成，因此该项状态为“软件
修复完成、正式证据待重跑”。

D5 修复后的 main 开发回归已复跑原失败 cell `communication_degraded 200v200 seed 64`。
该单元状态有限、在线真值使用为 0，episode 运行 27.4 秒、写入 3.9 秒，并在三 seed 计划的
1/3 边界写出 checkpoint v2 后正常暂停。该运行来自脏工作树，仅关闭原异常路径的开发验证，
不能替代新干净提交上的 900-episode 正式重建。

当前代码级阻塞已关闭，正式证据阻塞为新提交上的 900 episode 重建。行为克隆、近端策略优化、
20 个未见 seed、paired shadow 和模型准入仍未执行。

## 2026-07-20 三维 D1/D2/D6 真值隔离评估闭环

main 已将 D1 最终一致性证据带到 episode 离线边界，并保存在线证据、离线真值状态、D2
规范映射和离线结果。D2 映射只读取 D1 源观测谱系；代码路径不使用最近距离、目标名称、
actor ID 或末端接近结果。在线总线文件、真值状态 NPZ 和 D2 身份评估文件均以真实
SHA256 写入来源证明，D6 消费前再次校验结果和 D2 四类原始来源。缺失或冲突映射会使
RMSE/NEES unavailable，NIS 仍按在线证据独立统计；`id_switch_count` 缺证据时保持 null，
不会转成零。

D6 owner 已完成公开 D1/D2 适配器、逐 seed CSV、传感器/距离分档 CSV、聚合 JSON 和
中文 Markdown，D6 全量 `334 passed`。main 的 5v5 单 episode、无模块栈负例和双 seed
3v3 聚合均通过，scalable 3D 全量 `72 passed`。D1 在线证据通过
`observation_id + measurement_timestamp` 与 D2 规范身份精确联接，不使用航迹区间前向
填充。该工作关闭了“真实 episode 制品没有接入
D6”的接口级 P1 缺口。开放项转为实验级 P1：在 clean tree 上按 5/20/50/100/200 和至少
20 个未见 seed 生成正式统计，冻结 NIS/NEES、航迹连续性、身份交换和分阶段耗时门限；
当前单 seed/双 seed 结果不得作为性能达标结论。

## 2026-07-20 D4 下一周期消费与 D5 主动视觉整 episode 导出

main 已闭合 `plan N -> D4 advisory N -> plan N+1` 的单进程受控桥接。D4 只有实际
`assist` 且包含后投影 `d4-region-resource-advisory-v1` 时才进入消费候选；main 使用建议
生成时冻结的区域快照和正式 D4 裁决调用一次性 gate。通过后转换为 D3-owned
`d3_regional_planning_hint_v1`，D3 再按当前 previous plan、资源区域、已提交成员、备用和
transfer candidate 校验。shadow、无准入、replay、严格到期、fault generation 变化和
regional authority 路径均 fail closed。定向 4/4 及 scalable 3D 全量 72/72 通过，在线
真值使用为 0。开放项是跨进程 consumed advisory ledger、正式 D4 checkpoint、20 个未见
seed paired shadow 和长时/真实通信验证。

D5 owner 提供的主动视觉整 episode 合同已由 main 接入统一学习导出。数据集 split 语义已
升级为 learning/episode dataset v2 和 bundle v3：完整 `(scenario_version, seed)` group 不可分，
同一数值 seed 跨场景和规模原子进入同一 train/validation/test split。main 的
`scalable3d-learning-export-v2` 逐决策保存 truth-free snapshot、规则示范、requested/effective
action、计划/联盟/通信版本和同帧相机反馈；在线文件与离线 reward/outcome/counterfactual
文件物理分离。缺失 reward 保持 unavailable/null，不伪造 ACK 或因果标签。

main 新增 `scalable3d-learning-generation-plan-v1` 流式生成入口。nominal 2v2/5v5、seed
1/2/3、6 个 2 秒开发 episode 全部有限且在线真值使用为 0；D3/D4/D5 图成功落盘，主动视觉
107 帧因测试 seed 只有 1 个按预期不最终化。正式模式已在启动前检查完整场景/规模、训练与
保留评估 seed 零重叠、干净工作树、忽略输出目录及 D5 至少 20 个未见测试 seed。开放 P1
是 D6 outcome/counterfactual 回填、训练与模型准入。后续 clean-tree 九场景和两轮三 seed
优化复测已经关闭存储、finalization 和 D5 writer 系统级子项；当前容量/吞吐状态以本文顶部
专项为准。剩余 P1 是首个正式 45-episode 分块恢复证据，以及 900 episode 的运行、标签回填
和训练。

main 已冻结 `scalable3d-balanced-curriculum-v1`：100 个生成 seed 均衡进入 45 个场景/规模
cell，每 cell 20 个、总计 900 episode；seed 1000-1019 只用于最终评估。正式预检现会拒绝
缺失交叉 cell、cell 分母不足、训练/评估 seed 交集和 D5 未见 seed 不足，并记录 schedule
SHA256。runner 的可恢复分块软件合同已完成，D5 writer 已由同 seed clean-tree 复测确认收敛；
首个正式代表分块验证前不得连续执行完整批次。

D6 已接入 `scalable3d-experiment-matrix-v1` 的独立离线审计，按 R0/G1/A1/A2/A3/C1/F1
验证运行时实际采用证据、固定 cell 分母、同 comparison key 配对差值和 bootstrap 置信区间。
D6 全量 334 项测试通过；当前只有 dirty producer smoke，尚无 clean 完整矩阵和算法准入结论。

## 2026-07-20 规模化学习运行时接线

D3、D4、D5 和 D6 owner 已分别完成规模化研究管线，并由 main 分四次提交。D3 提供整
`(scenario, seed)` 数据划分、行为克隆、原生近端策略优化、bundle 和 paired shadow
准入；D4 提供变长区域图、规则基线、学习建议和资源守恒/通信邻接/owner/epoch/lease/
故障围栏/联盟提交投影；D5 提供真值物理隔离的图数据、原生消息传递网络、验证集校准和
校验加载；D6 提供离线逐 episode、逐 seed、聚合、中文报告和阶段耗时曲线。

main 已新增显式学习运行时装配。默认 D3/D4/D5 学习路径全部关闭。D3 `assist` 必须通过
bundle 内至少 20 个未见 seed、成本非退化、安全非退化和零回退帧门限；D4 当前没有正式
准入制品，任何 `assist` 请求均保持 `shadow`，区域建议以独立总线消息发布且不能修改正式
D4 裁决；D5 只有显式 bundle 才使用图边概率，缺失、校验失败、非有限、低置信和超时均
回退几何规则。episode manifest 新增 D4 策略版本，场景 metadata 记录请求/实际模式、权重
SHA256 和回退原因，不记录不可复现的本地绝对路径。

2026-07-20 main 回归为 `39 passed`。额外命令行 smoke 使用 5v5、seed 41、1.2 秒和三个
缺失 bundle，结果为有限状态、在线真值使用 0、实时因子 8.133；D3 回退
`model_bundle_missing`，D4 `assist -> shadow` 且正式裁决摘要前后相同，D5 回退几何规则。
该 smoke 来自 dirty 开发工作树，只验证接线和失败关闭，不属于正式模型证据。

当前没有新增 P0。D4 到下一轮 D3 的单进程消费闭环和 D5 主动视觉整 episode staging 已
关闭到接口/确定性回归层。开放 P1 为：生成 clean-tree 真实整 seed D3/D4/D5 数据；由 D6
回填主动视觉 outcome/counterfactual；持久化跨进程 D4 consumed-ID ledger；完成通信分区/
乱序、5/20/50/100/200 规模和至少 20 个未见 seed 的规则、图网络、强化学习及组合对照。
合成 fixture、三 seed staging 和单 seed smoke 不得用于模型准入。

## 2026-07-16 D5 5+1 ComputerVision 多相机专项

main 新增隔离入口 `run_d5_multicamera_branch.py`，单次启动 Blocks 后用 reset 分隔
AirSim detect 基线与 YOLOv8+原生 ByteTrack 候选。场景包含 5 个
`1920x1080/60°` 主相机、1 个 `3840x2160/75°` 俯视侦察相机和 5 个
`Quadrotor1` actor；运行 12 s、49 帧、seed 7，并按 2 s 间隔保存本专项要求的画面。
五个主相机允许只看到目标子集，侦察相机提供较宽视野。本专项未运行 D1/D2，main
用 actor 运动学合成中心侧 GlobalTrack fixture，并用 truth 做离线交并比评分；D5
关联代价、Hungarian 选择和稳定窗口只使用既有 GlobalTrack ID、相机内外参、双时间戳、
协方差和 camera-local track，不读取局部 actor/object/truth identity。

首次分析把全部 camera batch 的投影时间错误覆盖为最后一帧，导致前半段系统性像素偏移。
main 已修正为按各批次 `measurement_timestamp` 投影，并增加 `--replay-existing`，使用
完全相同的原始 AirSim 帧重算，未重新检测或改变仿真输入。

| 后端 | 检测召回 | 配准准确率 | 严格准确率 | 稳定配准 | 主相机联合覆盖 | 侦察全覆盖 | local IDSW | P50/P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AirSim detect | `1.000` | `1.000` | `1.000` | `0.975` | `1.000` | `0.918` | `0` | N/A |
| YOLOv8 + ByteTrack | `0.622` | `0.996` | `0.966` | `0.955` | `1.000` | `0.878` | `25` | `10.42/12.37 ms` |

两条路径的在线 truth use 和 `global_track_id` rewrite 均为 0。结论是 detect 几何基线
通过本专项门限，证明“局部子集视场 + 侦察视场 + GlobalTrack 投影 + Hungarian/稳定
窗口”链路在该单 seed 场景可运行；YOLOv8+ByteTrack 虽满足延迟和配准门限，但召回、
本地身份连续性和侦察全覆盖未通过，继续保持 optional，不替换默认 detect。开放 P1
细化为：同几何至少 10 seeds、不同目标间距/遮挡、YOLO 类别和尺度标定、ByteTrack
IDSW 治理、侦察视野稳定性及真实相机同步/外参漂移。专项报告位于
`research_modules/airsim_runtime/outputs/d5_cv_5v5_multicamera_formal_20260716/`
`D5_CV_5V5_MULTICAMERA_BRANCH_REPORT_CN.md`。

回归结果：D5 `291 passed`，AirSim runtime `154 passed`；后者只有既有 Matplotlib
`Axes3D` 环境提示，不影响二维曲线或相机截图。两条路径各保存 7 个 2×3 间隔拼图，
共 14 个，覆盖 `0/2/4/6/8/10/12 s`。

## 2026-07-16 本地图像航迹可复用机制接入

`b.mp4` 人工框选实验继续作为 P2 离线诊断支线，不进入默认 AirSim、D1 融合或 D2
关联路径。本轮只抽取了与具体视频、亮度和跟踪器无关的机制：

| 层级 | 已实现内容 | 当前边界 |
| --- | --- | --- |
| main 合同 | `LocalImageTrackObservation` 统一携带 camera-local ID、local epoch、可见光/红外波段、measurement/arrival 双时间戳、像素中心/框、2×2 协方差、confidence 和显式 lost | metadata 禁止 global/truth identity；local ID 永远不是 `global_track_id` |
| D5 离线适配 | 人工视频记录可转换为上述合同；重复量测整批拒绝，lost 不携带旧像素 | 人工 ROI、CSRT、亮度候选、固定像素门限仍是离线案例调优，不晋级主线 |
| D1 融合边界 | `measured -> EO/pixel SensorObservation`，`lost -> None`；namespaced `source_track_key` 去重累积到 `GlobalTrack.metadata.source_track_ids` | 不改变全局 ID；真实相机模型、像素噪声和 producer 接线仍需标定 |
| main 到 D2 | `CanonicalTrack -> Detection` 只保留 NED 位置、位置协方差、版本和 `source_track_ids` | 像素中心、bbox 和像素协方差不进入 D2 |
| D2 审计 | 显式累计来源绑定冲突、来源不连续隔离和上游本地身份拒绝；进入 metrics、risk 和 replay 聚合 | 三项是审计量，不替代 `id_switch_count`，不自动改变 GNN/Hungarian、门限或风险分类 |

验证日期为 2026-07-16：D5 `288 passed`，D1 `111 passed`，D2
`123 passed, 1 warning`，跨模块合同 `7 passed`；warning 是既有 Matplotlib
`Axes3D` 环境提示。本批未启动 AirSim。D5 文档记录的 95 帧、5 local ID、475 条离线
记录转换结果为 `470 measured / 5 lost`，只证明合同转换，不证明通用多目标跟踪性能。

本轮关闭的是“局部图像航迹无法以双时间戳、协方差和命名空间来源进入 D1/D2”的接口
缺口。仍开放的 P1 是：真实可见光/红外/雷达 producer 接线、相机内外参和时间同步、
像素协方差标定、D5 拒绝计数到 main/D2 frame metadata 的运行时接线，以及至少 10 个
duplicate-source、teleport、dropout、clutter 和合法新目标 AirSim 受治理 case 的
false-suppression、recall、离线 IDSW/continuity 与置信区间。亮度差分、人工 ROI 身份、
固定 20 px gate、两点像素外推和 CSRT 权重不列为主线待办。

## 2026-07-15 M5N2 ClockSpeed 三档 60-Case 对比

main 使用同一 M5N2 baseline/candidate、seed 1-10 和 reset-separated Blocks
流程，补跑 `ClockSpeed=0.2` 与 `0.1`，并与既有 `1.0` 批次组成 60 个真实
AirSim case。D6 按 `case_id/profile/seed` 形成 20 组跨档配对；0.1/0.2 的
ClockSpeed 来自 case result，旧 1.0 来自 20/20 sibling generated settings，禁止按
目录名推断。三个 suite 的 identity/state online truth use 均为 0。

| ClockSpeed | Baseline active-primary | Baseline target | Baseline coalition | Control tick mean | 判定 |
|---:|---:|---:|---:|---:|---|
| `1.0` | `6/30` | `6/20` | `0/10` | `1070 ms` | 原实时倍率基线 |
| `0.2` | `9/30` | `9/20` | `0/10` | `2208 ms` | 本矩阵物理结果最好，但墙钟代价约翻倍 |
| `0.1` | `4/30` | `4/20` | `0/10` | `3453 ms` | 锁定和最近距离改善未转化为物理完成率 |

该结果不支持“ClockSpeed 越低，拦截效果越好”的假设。当前每个 active primary 的
`moveByVelocityZAsync(duration=0.1)` 顺序等待，导致 AirSim ClockSpeed 同时改变 RPC
墙钟占用和每个名义控制步覆盖的仿真时间；这不是严格固定步长闭环。P1 新增/保持两项：

1. 将控制派发改造成可审计的并行/固定仿真时钟调度后，按同一 20-case 矩阵复验；在此之前不以 `0.1` 作为默认运行倍率。
2. 修复 candidate 机会合同：0.1 seed007/009、0.2 seed006/009 共 4 个 case 的 observed active-primary/target/coalition 与冻结 `3/2/1` 不一致。相关 candidate aggregate 保持 unavailable，不以缩小分母发布性能结论。

本批关闭 multi-episode timing manifest、三档 provenance 和比较报告能力；未关闭 100 ms
实时预算、第二 primary/联盟完成率和 candidate 机会合同。D6 `272 passed`，AirSim runtime
`157 passed`。报告见 `subagent_reviews/MAIN_M5N2_CLOCK_SPEED_COMPARISON_REPORT_20260715.md`。

## 2026-07-15 M5N2 20-Case 实测完成与批次终止

按用户指定边界，main 在 baseline/candidate 各 10 seed、共 20 个 M5N2 case 落盘后终止当前批次。TERM 生效前批处理已额外完成 1 个 `png_ttc_2v2_seed001`；该单 case 不构成多 seed 证据并明确排除在本节统计之外，dropout 完成数为 0。20/20 M5N2 case 均有 physical 与 `d7-actual-execution-metrics-v2`，identity/state online truth use 均为 0；因此没有新增 P0 blocker。

| 指标 | Baseline | Soft prediction + trend coast candidate | P1 判定 |
|---|---:|---:|---|
| Active-primary physical | `6/30` | `6/30` | aggregate 持平，但逐 seed non-degradation 为 false，candidate 不晋级 |
| Target physical | `6/20` | `6/20` | 未形成稳定目标级改善 |
| Coalition completion | `0/10` | `0/10` | 第二 primary/联盟闭环继续开放 |
| 第二 primary 5 m | `0/10` | `0/10` | 最近距离均值 `12.74/12.57 m`，不是轻微阈值偏差 |
| 最终双 primary 视觉共识 | `1/10` | `1/10` | D5 证据持续性仍不足 |
| 预测/窗口过期 | `14/157` | `19/257` | candidate 增加预测但同时增加过期，未转化为物理收益 |

真实 pooled timing 为 3805 个 tick。main-bus 内层 mean/P95/max=`349.34/487.40/1305.99 ms`，100 ms 违例 `3649/3805`，主导阶段为 D1 fusion（均值约 `320.00 ms`）；control-tick 外层 mean/P95/max=`1069.45/1254.06/2072.51 ms`，100 ms 违例 `3805/3805`，主导阶段为 AirSim frame sample（均值约 `432.29 ms`）。外层包含 bus processing，两层禁止相加。

新增开放 P1：main 合并 timing 文件附加 case 标签并跨 case 重置 `frame_index`，D6 的严格单-episode loader 会拒绝该 suite 文件。逐 case 原始 timing 完整，本轮报告直接从 20 个原始 JSONL 分层汇总；后续需要版本化 multi-episode timing envelope/manifest，不能伪造连续 frame index。专项报告见 `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`。

D5 复核确认第二 primary 时序记录 `3725/3725` 可用，但 bbox stable/handoff-ready 只有
`161/3725`（4.32%）；主要失败类别为 bbox 稳定性 34.44%、检测/新鲜度 32.46% 和
视觉关联 20.51%。当前统一 `failure_category` 没有直接写入最终产物，只能从 producer
漏斗字段重建，继续列为 D5/D6 P1 接线项。第二 primary 成员按当前 D3/D5 membership
识别，禁止将 `INT-03` 写死为固定第二成员。

D6 七阶段证据显示第二 primary 前四阶段 `20/20`、control/mode `17/20`、5 m physical
`0/20`；D7 复核发现 20 个第二 primary 均以 `collision_stop` 结束。当前没有写出 collision
object、碰撞法向及碰撞时的成员/环境距离，无法区分成员间冲突、环境碰撞或 AirSim 状态异常。
该碰撞 provenance 与 canonical target success/cooperative target diagnosis 术语统一均列为
main/D6/D7 P1，未补齐前不得把第二 primary 失败单独归因于 D5。

模块 owner 同步复核还确认：D1 fusion `320.00/451.46/1234.88 ms` 是 main-bus 主导阶段，
NIS/NEES/RMSE 仍无本批可用分母；D2 association `2.521/3.147/98.942 ms`，truthless 在线
IDSW/continuity 保持 unavailable；D3 `3725/3725` 条 history 中每 case 始终单一
`plan_id/version=1`，实际 plan/member/owner churn 为 0；D4 `active_degradation=0`，本批只构成
中心继续执行负对照，不构成二级或分布式性能证据。对应 P1 已由 D1-D4 owned GAP/PLAN 更新。

## 2026-07-15 D4 公开 Secondary Helper Fail-Closed P0 关闭

| 范围 | 本次关闭内容 | 当前边界 |
|---|---|---|
| D4 public helpers | `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 对 active secondary plan 强制要求 sustained readiness、expected/actual source、plan/required lease epoch、expiry/current time 和 plan monotonicity 全部可用并通过；任一缺失均输出稳定 reject reason，只能 pending/phase 1 | 该规则只约束二级 owner/plan；distributed interceptor/peer 继续使用自身 ACK/lease/epoch/commit 合同 |
| D4 adapter | 不再用 required epoch 自动补造 plan epoch；同一已激活 secondary plan 的维持路径也逐 tick 重验完整证据 | 正常中心和未激活 pending 计划不会被误写为可执行二级计划 |
| 回归证据 | 新增两个公开 helper 的逐字段 `None` 负例、完整正例、same-active-plan 缺证据负例和 distributed bypass 回归 | 本批未启动 AirSim，不替代真实 RF/mesh、时钟漂移、队列、乱序和重传 P1 |

验证结果：D4 `280 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`，`git diff --check` 通过。旧 `278/278` 只覆盖 heartbeat/readiness 主入口，不能证明公开 helper 的所有缺失组合；本节记录发现、修复和新增覆盖后的权威结论。

## 2026-07-15 D2/D6 Ceiling-Aware 准入 P1 代码缺口关闭

| 范围 | 关闭内容 | 当前边界 |
|---|---|---|
| D2 owner | continuity 准入升级为 `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`：基线剩余空间 `H=max(0,1-Cb)`，所需提升 `min(0.10,0.10H)`；输出 headroom、实际/所需提升、误差消除比例、逐 gate reason 和 policy version | 旧 `+0.10` 仅保留 deprecated 审计字段；通过只形成 promotion review，不自动改变默认 GNN/Hungarian |
| D2 fail-safe | 指标缺失/越界、continuity 退化、IDSW baseline 为零、false-track 超限、P95 超预算及 baseline/candidate truth leakage 均拒绝；仅 IDSW 改善不可晋级 | `0.9810 -> 0.9840` 只证明 continuity 单项通过，不能从旧摘要追认完整联合门限 |
| D6 owner | `d6-p1-system-evidence` v2 同时消费 D2 v2 gates、legacy structured checks 和 bool checks；保留 policy/headroom/required/actual/error-reduction/all-pass 与失败原因 availability | 已用原冻结 replay 生成正式 v2 联合报告；历史 artifact 缺字段继续保持 `None/unavailable`，不补零 |

正式证据位于 `research_modules/d6_evaluation_metrics/outputs/p1_identity_ceiling_aware_v2_20260715/`。总体候选 IDSW `1.3583 -> 0.6167`，continuity `0.9810 -> 0.9840`，false-track `0 -> 0`，P95 `15.47 ms`，在线 truth leakage 为 `0`；仅 `clutter/combined` 分档通过，其他四档因 baseline IDSW 为零而 fail-closed，dropout truth alignment 为 partial，JPDA research adapter 未准入。`promotion_recommended=true` 只表示进入人工评审，`selected_online_path=baseline_gnn_hungarian` 且 `default_online_path_changed=false`。

验证结果：D2 `113 passed`，D6 `243 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`。本批未启动 AirSim。

## 2026-07-15 D4 多入口二级接管 P0 边界关闭

| 范围 | 关闭内容 | 当前边界 |
|---|---|---|
| D4 owner | 新增统一 `SecondaryReadinessEvidence`/assessment；所有二级入口共同要求显式 episode time、有效 epoch/lease、新鲜 heartbeat/cue/communication、gimbal、coverage、network full-view 和持续 readiness | distributed interceptor peer 不套用二级视觉条件；真实 RF、时钟漂移、排队、乱序和重传仍为 P1 |
| main episode bus | communication tick 只消费上一完整 D4 decision，不读取当前帧尚未完成的仲裁结果；heartbeat-only、缺失、陈旧、未持续或同一节点租约冲突均不生成二级执行证据 | 本批只完成代码和确定性回归，没有启动新 AirSim episode |
| D6 metadata | 缺 current time 时 lease 视为 invalid，atomic commit 为 false；不得从默认时间或 heartbeat 推断可执行接管 | 真实 multi-seed failover time 与网络负载分布仍待采集 |

验证结果：D4 `278 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`。专项正反测试同时证明 heartbeat-only 不可执行、完整 readiness 可接管、冲突 lease fail-closed。

## 2026-07-15 Runtime 分阶段延迟可观测性 P1 实现缺口关闭

| 范围 | 已关闭内容 | 当前边界 |
|---|---|---|
| main bus 内层 | `main-stage-timing-v1` 按 frame 保存 communication、D1、D2、D6 track recording、D3、coalition commit、D5、D4、D7 和 link/cross-view recording；输出 `main_episode_bus/stage_timings.jsonl` | 只测 main bus 内部，不包含 AirSim frame sample 和控制 RPC |
| SimpleFlight 外层 | `control-tick-stage-timing-v1` 保存 AirSim frame sample、bus processing、control evidence/pair sync、guidance/control RPC 和 control tick total；输出 `control_tick_timings.jsonl` | 外层包含 bus processing，禁止与 bus 内层总耗时相加 |
| availability/error | 使用单调 `perf_counter`；未执行阶段为 `not_applicable + null`，异常保留已完成/失败阶段耗时；记录 total、measured sum、unattributed、budget 和 error | 历史 artifact 没有新 JSONL 时保持 unavailable，不从旧 loop total 反推阶段 |
| D6 正式消费 | 严格校验 schema/scope、顺序、时间、非负有限值、状态/数值一致性、总和和 budget flag；独立汇总阶段 mean/P95/max、dominant stage 和预算违例，输出 CSV/JSON/中文 Markdown/PNG；P1 schema 升为 v5 | 关闭代码和报告能力，不证明 100 ms 已达标 |
| 兼容验收 | 真实 2v2/M5N2 seed-1 旧产物分别生成兼容报告，两层均正确显示 `stage_timing_artifact_missing` | 下一步必须重新运行同配置真实 AirSim multi-seed 才能得到实际 dominant stage |

兼容报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_stage_timing_legacy_compat_20260715/`。本批没有启动 AirSim，没有修改 D1-D7 算法，也没有修改 D7 PN/PNG/LOS/外推公式。旧证据中的 2v2/M5N2 `123.3/384.6 ms` 和 231 次违例仍是总量基线；性能达标继续为开放 P1。

## 2026-07-14 D6 Target-State Freshness/Stale P1 证据链关闭

| 范围 | 已关闭内容 | 当前边界 |
|---|---|---|
| canonical actual evidence | 从 source-hash 已验证的最终 `control_commands.csv` 逐行校验控制时间、量测时间、到达时间、量测年龄、stale 和状态来源；缺列、非有限值、负值、时间逆序、age 冲突、非法布尔或空来源全部 fail closed | 不从 main diagnostics 或默认值回填；历史缺字段 artifact 保持 unavailable |
| 两例真实源重建 | 2v2 为 48 samples，mean/P95/max=`0.0375/0.2/0.2 s`；M5N2 为 608 samples，mean/P95/max=`0.091118/0.2/0.2 s`；两例 stale 均为 0，来源均为 `d2_estimated_global_track` | 只关闭 seed-1 schema 和证据注册；同配置多 seed 分布、100 ms 性能预算和异常 stale 正例实测仍为 P1 |
| 正式报告 | case、pooled aggregate、CSV、JSON 和中文 Markdown 均输出 freshness/stale availability、样本数、年龄分布、stale 数量/比例和来源分布；五层正式证据为 contract/control/terminal-switch/mode/physical=`102/26/26/2/4` | 完整 P1 suite 仍因缺 paired/dropout/multi-seed 保持 fail，不能误写为整体通过 |

正式报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_actual_target_state_freshness_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`。D6 `216 passed`，D5 文档同步回归 `261 passed`，D7 文档同步回归 `188 passed`；本批未修改 D7 PN/PNG/LOS/外推公式。

## 2026-07-14 Actual-Execution 真实 AirSim P0 复验关闭

| 场景 | Canonical evidence | 物理结果 | 计划/安全证据 | 当前判定 |
|---|---|---|---|---|
| tuned 2v2 seed-1 | actual v2 `available`，无 unavailable artifact | pair/target `2/2`，最小距离约 `4.98/4.89 m` | command/actual/history plan ID 一致；identity/state online truth `0/0` | P0 通过；`png_ttc` 多 seed 仍为 P1 |
| M5N2 seed-1 | actual v2 `available`，无 unavailable artifact | active pair `2/3`，target `2/2`，coalition `0/1`；第二 primary 最近约 `11.02 m` | command/actual/history plan ID 一致；identity/state online truth `0/0` | P0 证据链通过；第二 primary 与联盟性能仍为 P1 |

D6 联合报告位于 `research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`；新增 freshness/stale 重建报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_actual_target_state_freshness_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`。其中 `actual_execution_all_available=true`；总 P1 suite 仍为 fail 是因为本批只运行两项 P0 smoke，没有 baseline/candidate 配对、1-5 帧 dropout 全矩阵和多 seed，不能误写为完整 P1 验收通过。2v2 loop latency 约 `123.3 ms`、M5N2 约 `384.6 ms`，性能预算违例合计 `231`，继续列 P1。actual v2 已正式独立提供 contract/control/terminal-switch/mode/physical 五层证据，并从最终 CSV 重算 freshness/stale；不从 `control_allowed` 或默认值回填。

## 2026-07-14 D6 Actual-Execution 计划来源 P0 关闭

| 范围 | 关闭内容 | 验证与剩余边界 |
|---|---|---|
| D6 canonical evidence | actual envelope v2 严格保存 `plan_ids`、正整数 `plan_versions`、`owner_node_ids` 及 availability/source/semantics；缺列、空计划、坏版本、同一 plan 混合版本及二级/分布式有效控制缺 owner 均 fail-closed | D6 `184 passed`；安全计数、physical provenance 和实际视觉切换语义未放宽 |
| D6 merge | merge v3 清除 replay 中同名计划来源，只接受通过 source hash 和结构校验的 actual envelope metadata | 中心重规划与二级接管两个原失败场景均已通过 |
| main integration | actual artifact 仍由 main 在三份最终执行源写盘后生成和注册；最终 metrics 保留实际计划来源及两个在线真值安全计数 | AirSim runtime `142 passed`；P1 terminal/integrated/dry-run `17 passed`；`git diff --check` 通过 |

该代码级结论已由上节真实 2v2/M5N2 seed-1 复验补强。更早历史 output 不追溯升级；后续多 seed 必须生成新的 v2 artifact。

## 2026-07-14 第二批 P1 代码闭合与 main 接线

| 范围 | 已闭合代码项 | 仍开放 P1 证据 |
|---|---|---|
| D3/main | 当前 tick 成本口径、窗口累计变更预算、canonical history 写盘 | 同几何至少 10 seeds 下 churn、未分配高威胁率、reserve demotion 与 D2 生命周期准入 |
| D5/main | 稳定 camera/stream/backend/local-track 历史，committed primary 与 duplicate risk 接线 | M5N2 第二 primary 获取/锁定，30/50 m recall，YOLO/ByteTrack/BoT-SORT 至少 10 seeds 准入 |
| D7/main | raw gate、latch、effective contract/control、termination snapshot 和 dropout scope；终止行不再复用历史 latch | truth-isolated 2v2/M5N2/dropout 同 seed 物理复跑、range/closing speed/机动/3D 标定 |
| D6/main | terminal metric envelope、物理分母、性能样本、D3 history 和 suite/case 报告入口 | 跨 case/multi-seed 长期聚合、约 1.3 s loop latency 与预算违例根因、显著性和趋势治理 |

本批没有运行真实 AirSim，历史 postfix seed-1 的 M5N2 `0/3 pair`、`0/2 target`、`0/1 coalition` 和 2v2 最近距离约 `7 m` 仍只是修复前诊断证据，不能用于宣称第二批 P1 性能闭合。

## 2026-07-14 D1 Covariance 与 D4 二级证据完整性 P0 关闭

| 范围 | 关闭内容 | 验证与剩余边界 |
|---|---|---|
| D1 covariance contract | online fusion、online replay、governed bundle 和 AirSim freeze 统一校验 measurement/covariance 维度、有限性、对称性和半正定性；缺失/非法矩阵不再静默修复 | D1 `92 passed`。显式 offline legacy migration 保留，但必须写原始缺失原因、model/default/参数和 offline-only provenance；真实传感器标定与多 seed NIS/NEES 仍为 P1 |
| D4 secondary evidence | 缺 current time、heartbeat、cue freshness、gimbal、communication summary 或 network full-view 均不可达到 `takeover_ready`；lease 继续严格要求 `current_time < expiry` | D4 `224 passed`。完整正例和中心/二级/distributed 顺序保持；真实网络、时钟漂移、排队/乱序/丢包和自主联盟重构仍为 P1 |
| main integration | 质点集成场景显式生成二级视频/数据链 `CommunicationSummary`，不通过恢复 fail-open 兼容旧 fixture | integrated point-mass/contracts `10 passed`；AirSim runtime `134 passed` |

本批没有启动真实 AirSim。历史缺字段 replay 只能作为 legacy/unavailable 证据，不能用于证明二级节点可执行接管。

## 2026-07-14 D5 Native MOT History P1 子缺口关闭

D5 owner 已修复真实 Ultralytics `Results.boxes.id` 路径：原生 ByteTrack/BoT-SORT 的
`mot_history_length` 不再每帧固定为 1，而是按
`(resource_id, camera_id, tracker_backend, native_tracker_id)` 累计连续实测命中。同一 ID
连续帧从 1 增长到 2 及以上；ID 变化、任一空帧、backend 切换、原生模型重建、stream reset
和 episode reset 都从 1 重新开始。短时消失的 ID 状态可在 `max_track_age_frames` 内保留供
tracker 审计，但 coast 不计入连续实测历史，长期复用 ID 不能直接满足锁定门限。

该修复没有降低 `min_mot_history`，没有放宽 friend/duplicate/version/timestamp/calibration
gate，也没有创建或换绑 `global_track_id`。Results-like 专项为 `41 passed`，D5 全量
`241 passed`，AirSim runtime YOLO/MOT focused `10 passed`，runtime 全量 `130 passed`。
本项只关闭代码级 P1；真实 AirSim/真实图像的远距召回、IDSW/continuity、P95 延迟、失败回退
和 M5N2 第二 primary 稳定锁定仍开放。

## 2026-07-14 D4 Lease 与 D6 Physical Completeness P0 关闭

本批由 D4 owner 将 secondary resource 候选、secondary plan 发布/维持、active secondary owner
和 D7 handoff 统一到同一严格租约判据：expiry 与当前 episode time 必须同时存在，且严格满足
`current_time < lease_expiry`。缺 expiry、缺 current time、`current_time == lease_expiry`、过期、
旧 epoch 和 source mismatch 均不可执行；active secondary owner 的 lease 失效时进入
`hold_review`，不保留过期执行权。D4 全量 `211 passed`。

D6 owner 在既有 physical provenance gate 上继续补齐结果和联盟完整性：每个 active pair
必须存在显式 `physical_success` 或规范 scorer 终态；required-primary 持久化成员不足、缺到达
窗口、缺 denominator，或 summary 声明 opportunity 但缺 completion 时，coalition 指标保持
unavailable；证据完整的显式失败仍保持 available `0`。CSV、JSON 和 Markdown 使用同一
availability/reason。D6 全量 `150 passed`，仅有既有 Matplotlib 3D 后端环境 warning。

main 只修正合法跨模块 fixture：integrated simulation 与 AirSim runtime 的 secondary 资源和
plan 现在显式携带 heartbeat、lease epoch/expiry 和 episode time，没有放宽 D4。验证结果为
AirSim runtime `130 passed`、integrated point-mass `7 passed`、D7 `178 passed`。本批未运行
新的真实 AirSim episode；真实同 seed AirSim 重跑仍是 P1 证据任务。

## 2026-07-14 D6 Physical Provenance P0 关闭

只读复核曾发现 D6 在 summary 宣称物理证据可用、但缺逐 pair summary 时，仍可能从
`control_commands.csv` 回退生成物理 pair；同时没有逐 active pair 校验
`target_state_source` 与 episode 的 `online_control_state_source`。该缺口会把证据缺失或
来源冲突的结果误标为物理成功，因而按评估级 P0 处理。

本批由 D6 owner 完成修复：物理指标必须同时具备 intercept summary、持久化 pair summary、
每个参与 pair 的 `physical_evidence_available=true`、可判定 physical result 和一致的状态来源。
command-only、summary-only、缺证据、缺结果或来源冲突全部 fail closed；required-primary 成员、
到达窗口、denominator 和 completion opportunity 也必须完整。合法 offline scorer、显式 truth
fixture 和证据完整的显式失败正例保持。运行结束后的 generic `active=false` 不再被误解为
assignment inactive，standby reserve 仍排除。验证结果为 D6 `150 passed`、AirSim runtime
`130 passed`、integrated point-mass `7 passed`，`py_compile` 与 `git diff --check` 通过。该修复
关闭代码级 P0，不替代真实同条件 multi-seed AirSim P1 复验。

## 2026-07-14 在线真值隔离 P0 复核

| 范围 | 当前状态 | 判定与下一验收 |
|---|---|---|
| D1 AirSim 观测入口 | 已移除 actor/object/truth 身份；EO 使用真实 detection bbox；雷达/声学/LiDAR 作为传感器仿真可由场景真值生成带噪量测，但生成后的在线 DTO 不携带目标身份 | 已关闭；改名不改变在线 observation，D1 `83 passed` |
| D1 arrival queue | 量测只在 `arrival_timestamp <= episode clock` 时进入融合；尚在传输中的量测可写 governed replay，但不得提前更新状态 | 已关闭；未来量测不提前消费，main runtime `124 passed` |
| D2/D6 truthless 语义 | D2 在线策略拒绝 truth/actor/object 字段；无完整 truth 配对时 RMSE、continuity、IDSW 保持 `None/unavailable`，不再伪造 0 | 已关闭；D2 `98 passed`，D6 `137 passed` |
| 离线 integrated replay | 离线 runner 显式使用 `TrackerTruthPolicy.OFFLINE`，与真实 main episode bus 的 `ONLINE` 策略分离 | 已关闭；integrated `7 passed` |
| SimpleFlight 在线控制状态 | 默认、主动中心重规划和主动二级接管统一消费 D2 `target_estimate`；合同覆盖只修改 plan/version/owner/D4/D5 状态，目标状态与 actor alias 不可注入；无估计/陈旧估计 fail-closed | **P0 closed**。actor truth 扰动不改变命令，在线 state use 为 0，actor truth 只进入运行后离线 NED 三维 5 m scorer；AirSim runtime `130 passed` |

关闭后的边界仍需保持：`truth_identity_online_use_count=0` 与
`truth_state_online_use_count=0` 必须分别成立；历史缺少 state provenance 的物理结果仍只作
迁移前 smoke/离线证据。同 seed 真实 AirSim 复跑属于 P1 性能与证据验收，不回退为 P0
代码断链。

## 2026-07-14 第二批 P1 修复：D3 有序历史与 D6 churn

| 范围 | 本批实现 | 验证与剩余边界 |
|---|---|---|
| D3 canonical history | 新增 `d3_plan_history_record_v1`，每个 planning tick 保存顺序索引、时间、plan/version/window、owner/epoch/lease、primary/reserve active 状态、联盟成员、迟滞、反馈分类和成本；递归排除 truth 字段 | D3 `149 passed, 1 skipped`；D3 owner 已同步 README/PLAN/GAP/算法和实验文档 |
| main episode bus | 每次实际规划调用只生成一条 history；非规划 frame 不重复；独立写出 `main_episode_bus/d3_plan_history.json`，tick 仅在本帧发生规划时携带记录 | focused end-to-end 测试已覆盖 3 planning ticks、稀疏 planning frame 和 truth 隔离 |
| D6 canonical consumer | 严格校验 wrapper/record schema、record count、sequence 唯一单调、ordering key 和 timestamp；按相邻 assignment 集合计算 membership churn，不累加重复审计事件 | D6 `132 passed`；乱序、重复索引、单记录均为 `unavailable` |
| D6 新指标 | `primary_membership_change_count`、`reserve_membership_change_count`、`owner_change_count`、`soft_feedback_count`、`hard_feedback_count` 和四项 churn 正式可用 | AirSim runtime `122 passed`，integrated point-mass `7 passed` |

本批完成的是证据链和离线算法验收，不是新的物理性能证据。修复前 M5N2 `5/10` 仍为当前真实基线；下一步必须在相同 20 m/3 s/40° 几何、相同 seeds 1-10 下复跑，比较 plan/member churn、第二 primary 锁定和 coalition completion。

## 2026-07-14 第一批 P0/P1 修复

本批继续采用“main 下发、D3/D5/D6 owner 自改自测、main 只处理运行时桥接和集成回归”的流程。

| 范围 | 本批修复 | 验证与当前边界 |
|---|---|---|
| D6 评估级 P0 | 最终快照、空输入和单条无序记录不再推断 plan/coalition/epoch/membership churn 为 `0`；只有显式计数或至少两条有序历史才可计算 | D6 `120 passed`；P0 已关闭。真实逐 tick D3 history 仍为 P1 |
| D5 反馈语义 | 普通 ambiguity/hold/reacquire 保持视觉不确定性；verified friend、spoof、duplicate 和 assignment conflict 保持硬冲突 | D5 `235 passed`；没有放宽 D7 当前 pair 的视觉切换门控 |
| D3 写回与迟滞 | 普通视觉不确定性改为 resource-target edge-soft，不再把整架资源设为 `operator_hold`；硬身份/重复/显式可行性冲突继续 fail-closed；soft feedback 不再绕过 `min_dwell` | D3 `144 passed, 1 skipped`；40-case 高 churn 仍只是根因线索，需要同输入复跑证明效果 |
| main episode bus | 输出显式 `feedback_constraint_class`；stale/unverified identity 保持 soft，verified/spoof/duplicate 保持 hard；standby reserve 的 D6 `AssignmentRecord.active=False` | AirSim runtime `121 passed`，integrated point-mass `7 passed` |

本批没有修改 D7 PN/PNG 公式，也没有启动新的 AirSim 物理 episode。M5N2 `5/10` 是修复前基线，必须用同几何、同 seeds 复跑后才能判断计划抖动和第二 primary 锁定是否改善。

## 2026-07-13 P1 收敛实测与统一验收

详细结果见 `subagent_reviews/MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`，统一 D6 证据位于 `research_modules/airsim_runtime/outputs/p1_convergence_20260713/d6_system_evidence/`。

| 范围 | 真实 AirSim/离线验收结果 | 当前判定 |
|---|---|---|
| D1/D2 dense crossing | 4 m 与 2 m 横向间距各 20 seeds，共 40 episode、10200 条 evaluator-only truth；在线 truth 泄漏 0。最佳 GNN 候选 IDSW `1.3583 -> 0.6167`，下降 54.6%，continuity `0.9810 -> 0.9840`，P95 24 ms | 未达到冻结的 continuity `+0.10` 晋级条件；默认 GNN/Hungarian 不变，轻量 JPDA 不晋级 |
| D4 episode-time fault matrix | normal、center failure、center+secondary failure、0.5 s delay、30% loss、partition recovery，共 60/60 safety outcome 通过；false degradation、duplicate owner 均为 0 | episode-time 接管/原子 fail-closed 合同闭合；不等同真实 RF/网络验证 |
| M5N2 cooperative closure | 10 seeds、baseline + 3 个候选，共 40 episode；最佳 20 m/3 s/40 deg profile 为 `5/10`，其他为 `2/10`、`1/10`，baseline `0/10`；总体 `8/40` | 未达到 `8/10`。主要断点为 `d5_not_locked` 与 terminal detection acquisition timeout；继续列 P1 |
| D5 原生 MOT | 18 个 1920x1080 筛选工况全部 connected；20 m native active/continuity=1、IDSW=0，ByteTrack P95 约 7.4 ms、BoT-SORT 约 16.2 ms；30/50 m 无检测 | 20 m precision/recall 仅约 0.26-0.33，0 个候选准入，未启动 confirmation；默认 detect 不变 |
| 安全合同 | reserve unauthorized=0、global track rewrite=0、online truth use=0 | P0 安全门控保持 |
| D6 | 修正 profile 分组并展开 40 case、160 条 D5 和 164 条 D7 证据；合同/控制/模式/物理严格分层 | 统一 P1 证据入口闭合；缺失的 D3 时序 churn 保持 unavailable |

本轮还修正了 main-owned integrated point-mass 回归的旧断言：中心健康时，持续 D5 ID 不一致的正确动作是先请求二级辅助、再请求中心重规划，不直接转移计划 owner。该修正未改变 D4 模块策略。

统一回归结果：D1 79、D2 93、D3 139（optional OR-Tools 1 skipped）、D4 198、D5 232、D6 115、D7 178、AirSim runtime 124、integrated/dry-run 11，全部通过。matplotlib `Axes3D` 为本机依赖 warning，不影响本轮二维图表。

### D1-D7 PLAN/GAP 同步状态

2026-07-13 已由 D1-D7 owner 分别复核并更新各自 `research_modules/Dx_*/PLAN.md` 与 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`。本次同步只更新状态、证据和后续验收口径，没有修改模块算法代码。当前权威开放 P1 为：

| Owner | 当前开放 P1 |
|---|---|
| D1 | 真实漏检/虚警/遮挡/异步采样 fixture，区域时间窗和协方差长期治理 |
| D2 | 更长 OOSM/遮挡/杂波 replay、gate/risk 与 NIS/NEES 分档；当前候选不晋级 |
| D3 | 逐时刻 plan/coalition history、D5 feedback 权重/迟滞和动态 N/M 标定 |
| D4 | 真实带宽、时钟漂移、排队/抖动/乱序/重传与长期恢复统计 |
| D5 | 第二 primary 稳定获取、bbox 口径/尺度/时间对齐、30/50 m 召回和候选 confirmation |
| D6 | 长期 multi-seed 趋势、producer 逐时刻 schema 和跨批次失败原因治理 |
| D7 | 第二 primary 视觉 gate/acquisition、closing speed/range、三维几何和机动标定 |

P2 内容保持原计划，不因本次文档同步提前进入默认依赖或在线路径。

## 2026-07-13 远距雷达直接分配增量

详细实现与实测见 `subagent_reviews/MAIN_RADAR_DIRECT_ASSIGNMENT_AIRSIM_VALIDATION_REPORT_20260713.md`。main 已将正常 CV 场景的相机指向改为持续消费当前 D3 binding 和 D2 预测位置；`--cv-reassignment-time` 只作为显式压力注入。D4 新增末端视觉证据适用范围：约 50 m 雷达中段、中心正常、计划 current/feasible 且只有 D1/D2/D3 软风险时继续中心计划，不请求二级视觉辅助；高不确定度/陈旧量测、已观测 IDSW/duplicate、计划硬失效和 D5 身份冲突保持原强门控。

真实 2v2 复测为 14/14 `continue_center`、14/14 `radar_midcourse`、plan owner/version 全程 `center/v1`、owner mismatch=0。5v5 YOLOv8+ByteTrack 三 seed 为 105/105 `continue_center`、active degradation=0、在线 truth 违规=0，视觉平均处理耗时约 12.99 ms。P1 尚未关闭的是视觉效果准入：18 个相机-seed 流均因 episode 仅 8 个 warmup-inclusive 帧或召回不足未获 native MOT admission，第三主相机无稳定检测，200 m 二级相机离线召回约 0.08-0.09；后续需更长 episode 和视角/尺度/阈值校准，但不再作为远距中心分配的前置条件。

## 2026-07-12 P1 Cooperative/Identity 收敛增量

详细实施与实测报告见 `subagent_reviews/MAIN_P1_COOPERATIVE_AND_IDENTITY_CALIBRATION_REPORT_20260712.md`。

| 范围 | 已关闭缺口 | 当前开放 P1 |
|---|---|---|
| D1 | 真实 AirSim replay 冻结、governed schema、独立 truth sidecar、双时间戳/协方差/NED/lineage | 增加漏检、虚警、遮挡和不等采样率 fixture |
| D2 | 54 组固定矩阵、10/20-seed screening/confirmation、轻量 JPDA 同输入对照；真实 AirSim 证据分类修正 | 当前 crossing fixture 区分度不足，不能据 `IDSW=0` 关闭身份治理 |
| D3/D7 | 27 组 cooperative 候选、质点预筛、滚动兼容版本保持视觉滤波历史；PN/PNG 公式未改 | top-3 至少 10 seeds；第二 primary 可达性和同步窗口仍未闭合 |
| D4 | binding 与视觉 readiness 解耦；arbiter 按 pair 隔离；六类通信 replay 60/60 | 真实通信时序和二级/peer 联盟继续多 seed |
| D5/main | 有 local track 的 596/596 条记录携带有效 typed camera geometry；无 truth 回填 | 同步双 primary 锁定、候选 margin 和失锁恢复仍需标定 |
| D6/main | cooperative/dense crossing 中文报告、曲线和 D3-D7 evidence manifest | 长期趋势、难度分层和 10-seed cooperative 汇总 |

本轮四个 35 s M5N2 case 全部 connected。D4 错误 `d4_terminal_inconsistent` 已降为 0；D6 active-primary 漏斗为 assigned/visible/associated `12/12`、contract `2/12`、control `0/12`、physical `1/12`，coalition completion `0/4`。12 s 稀疏 binding 专项中 `d4_owner_missing=0`。因此当前无新增 P0，但 M5N2 协同物理闭环仍是最高优先级 P1。

真实 CV dense crossing 20 seeds 中默认 GNN 的 IDSW=0、identity/coverage continuity=1.0、false track=0、RMSE 约 0.164 m、P95 约 3.7 ms；轻量 JPDA 指标无改善且 P95 约 4.7 ms，`promotion_recommended=false`，默认 GNN/Hungarian 不变。

### 2026-07-12 独立主资源、原生 MOT 与运行时失效接线

本轮不再研究同时到达。高威胁目标继续采用 `2 primary + 1 reserve`，但两个 active primary 使用 `terminal_authorization_scope=per_primary`、`arrival_coordination_required=false`，分别通过 D3/D4/D5/相机质量/机动余量门控，并分别按 NED 三维 5 m 判断物理成功；reserve 仍为 standby，未激活不得切换视觉 PNG。PN、`png_vm`、`png_ttc` 公式均未修改。

| 范围 | 本轮关闭的实现缺口 | 仍开放的 P1 |
|---|---|---|
| D3/main/D5/D7 | 同名授权字段已贯通 demand、plan、D5 Assignment、D7 binding 和 SimpleFlight topology；纯成本/诊断刷新不再推进 plan id/version/coalition epoch | 需真实 M5N2 多 seed 复跑，确认每个 primary 的 contract/control/mode/physical 四层结果 |
| D4/main | AirSim frame 时钟驱动 center/secondary/peer heartbeat、ACK、lease、epoch、owner；无可执行 owner、分区、reconfiguring 时 fail-closed 阻断视觉 PNG | 需真实 center failure、center+secondary failure、missing ACK 多 seed episode |
| D5/main | ByteTrack 与 BoT-SORT 原生准入监测接入真实帧；truth RPC 严格在 online result 之后，IoU fallback 不可准入 | 需实际运行 18-case screening 和每后端 10-seed 双相机 confirmation |
| D2/main | 六 difficulty profile 不再只换标签；dropout 删除量测、clutter 注入匿名虚警、delayed/noisy 增加延迟并放大协方差；2 m tight geometry 必须真实捕获 | 需采集 4 m nominal 与 2 m tight 各 10/20 seeds 并完成阈值治理 |
| D6 | 新增统一 P1 evidence CSV/JSON/中文 Markdown/PNG，分离 contract/control/mode/physical，汇总 D2-D5/D7 availability | 需用真实 AirSim 产物填充全部 source，当前代码回归不能替代实测结论 |

本轮代码级回归已覆盖 main runtime、跨模块合同和 D1-D7 模块测试；原生 MOT 与新的多 seed AirSim 矩阵尚未实际启动，因此不得把“接口闭合”表述为算法已晋级。默认在线检测/关联主线继续保持 AirSim detect 与 GNN/Hungarian，ByteTrack/BoT-SORT 只有达到准入阈值后才进入主线评审。

后续真实预检已完成 20/30/50 m 距离矩阵和 20 m、102 帧单相机确认。20 m 下 ByteTrack/BoT-SORT 均达到 native active=1、continuity=1、IDSW=0、fallback=0，P95 分别约 8.29/18.23 ms；30/50 m 均无检测。20 m 使用 AirSim detect 框做 IoU=0.5 post-online 评分时 precision/recall 仅约 0.29-0.32，因此两者均未通过准入。P1 开放项已从“原生 MOT 未运行”细化为：30/50 m 小目标检测召回、YOLO/AirSim bbox 口径与 IoU 多阈值标定、之后再运行完整 confidence 和多 seed 矩阵。

## 2026-07-12 P1 Terminal Closure 10-Seed 结果

main 使用 `p1-terminal-closure-v1` 运行 80 个 reset-separated episode，全部 connected，默认不保存 PNG。执行索引为 `research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/p1_terminal_closure_summary.json`，D6 中文报告和曲线位于同目录 `d6_unified_acceptance_full/`。

| 范围 | 实测结果 | 当前 GAP 判定 |
| --- | --- | --- |
| M5N2 baseline | active-primary `7/30`，target `7/20`，coalition `0/10` | 物理协同未闭合 |
| M5N2 candidate | active-primary `4/30`，target `4/20`，coalition `0/10` | 相对 baseline 退化，soft/trend 不得晋级默认 |
| 1-5 帧 dropout | 物理 100/100；1 帧预测 9/10，2 帧 10/10；3-5 帧各 10/10 命中 0.25 s 硬过期 | 矩阵完整但为 49/50；seed 2 单帧注入/锁定时序仍需复核 |
| 2v2 `png_ttc` | 10 seeds、pair/target `20/20`，115 个 control-allowed sample；not-expanding 13、TTC out-of-range 22 | 真实多 seed 主链闭合；area-jump/clipping 受控拒绝覆盖仍开放 |
| Truth/ID 安全 | 80 episode online truth use=0；D5 deterministic 10/10，global ID rewrite=0 | P0/P1 安全合同保持 |
| D2 long replay | 10 seeds，IDSW 均值 138.1，continuity 0.694，false track 均值 5.4，RMSE 0.307 m | 校准链路闭合，但默认 GNN 风险阈值未通过 |
| D3 matrix | 8/8 full/incremental 等价；仅 1/8 使用局部增量，7/8 安全回退 | 正确性闭合，增量收益仍需真实事件校准 |
| D4 matrix | 9/9 通过，误降级 0，五个负例 fail-closed | 确定性扰动矩阵闭合；真实通信时序仍开放 |
| D6 | D1-D5/main 证据 available；四层和 pair/target/coalition 分离 | 统一离线验收入口闭合 |

当前最急 P1 已从“缺少 paired 数据”转为：M5N2 第二 primary/联盟物理闭合、D2 dense crossing ID 连续性治理、真实二级通信时序、真实相机同步/YOLO-MOT 标定，以及 `png_ttc` 剩余两类受控拒绝覆盖。

## 2026-07-12 PNG delivery 增强与实测状态

本轮由 main 下发、D5/D6/D7 分别实现并自测，main 只负责 AirSim runtime 接线、真实运行和汇总。详细报告为 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`，D6 结构化对照包位于 `research_modules/airsim_runtime/outputs/png_delivery_enhancement_eval_20260712/`。

| 范围 | 当前状态 | GAP 判定 |
| --- | --- | --- |
| D7 图像 KF 生命周期 | 已按 resource/global/local track 与 plan owner/version 隔离；切换即重置，漏检不伪造身份切换 | P1 实现闭合，保持跨 ID/version/friend/duplicate 回归 |
| D7 `png_ttc` | 已加入 delivery 等价面积 EMA、窗口斜率、跳变/裁剪/TTC 范围拒绝；`png_vm` 不变 | P1 实现闭合，真实 `png_ttc` 多 seed 标定仍开放 |
| soft prediction / trend coast | 默认关闭；candidate profile 显式开启，预测上限 0.25 s，trend 仅水平且不超过 0.75 m/s | P1 optional 能力闭合，不晋级默认 profile |
| D5 证据合同 | 已输出双时间戳、local-track transition、MOT history、bbox clip、相机内外参和姿态有效性；truth ID 在线使用禁止 | P1 合同闭合，真实标定误差/姿态同步长期校准开放 |
| D7 6D LOS KF | 仅离线 replay，兼容 direct `camera_to_ned_rotation` 或分解旋转；字段缺失明确 unavailable | P2 optional，不替换在线 EMA/滑窗 |
| D6 指标 | 已增加滤波状态、TTC 拒绝、soft/coast、命令跳变及 contract/control/mode/physical 分层报告 | P1 指标闭合 |
| 真实 2v2 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，在线 truth=0；旧基线为 19/20 | 达到本轮非退化验收，但自然场景未触发 soft/trend，不能据此宣称增强算法贡献 |
| 锁定后 dropout | 2 帧均为 `image_kf_predict`，2/2 物理成功，未发生跨身份 coast | 有界预测真实链路闭合 |
| M5N2 | 8 s 短窗口 3 seeds 为 0 成功，最近距离 22-32 m；出现 soft prediction 4、innovation reject 2、truth=0 | 与既有 z=-30 m/35 s 高净空基线不等价；P1 仍是第二 primary 中段闭合和联盟视觉一致性，不归因于 PNG 滤波 |

统一回归：D4 148、D5 161、D6 84、D7 137、AirSim runtime 98、质点集成 7、dry-run 4、跨模块合同 3，全部通过。当前没有新增 P0；仍需用同一高净空 M5N2 几何和相同运行窗口做 paired baseline/candidate，才能决定 soft prediction 或 trend coast 是否进入默认 AirSim profile。

## 2026-07-11 P1 收敛实施后历史检查点

完整中文报告和结构化证据位于 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。本节保留 2026-07-11 当日状态；当前权威状态以前文 2026-07-12 小节和第 7 节为准。

| 范围 | 实施与验证结果 | 当前判定 |
| --- | --- | --- |
| D1/D2 replay 与 truth 隔离 | D1 输出带 schema、双时间戳、协方差、lineage 的 governed replay；D2 只从独立 offline truth label 评分 | P1 合同闭合，继续补充更长真实 replay 校准 |
| D3 动态规划 | 增量规划、短时 feedback dwell、primary 角色保持和 N/M 非等量合同已实现 | P1 合同闭合，真实阈值仍需多 seed 调参 |
| D4 联盟接管 | 二级节点和完全分布式三成员联盟均达到 `executing`、ACK 3/3；缺 ACK 为 2/3、状态 `aborted` | P1 原子 commit/ACK/epoch/lease 正负例闭合 |
| D5/D7 协同末端合同 | CV 10 seeds 中 8/10 达到 T001 双 primary 视觉共识并授权；10/10 IDSW=0、错误重复锁=0、global ID 改写=0 | 达到本轮 8/10 合同验收；两个失败 seed 保留为鲁棒性回归 |
| D6 结果语义 | 已分离 `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`，ComputerVision 的物理命中为 unavailable 而非 0 | P1 指标口径闭合 |
| SimpleFlight 物理拦截 | runtime 默认成功半径已由 0.75 m 改为 NED 三维 5.0 m；pair/target/coalition 分层统计已接入；首次无锁使用 acquisition grace，已锁定后按 `image_kf_predict -> blind_push -> expired/reacquired` 处理 | 2026-07-11 时 P1 代码与接口闭合、实测待重跑；已被 2026-07-12 的 2v2 20/20 与 M5N2 paired 开放项更新 |
| D5 在线视觉链 | 默认继续使用 `simGetDetections` bbox；controlled intercept 已取消 `object_id == target_id` 选框和模拟锁定，改为消费 episode bus 的匿名 local track 与几何 `TerminalAssociation` | P1 truth 隔离和接线闭合；YOLO 数据集标定后置 |
| P2 可选对照 | D1 FilterPy/Stone Soup、D2 GNN/JPDA/MHT、D3 OR-Tools capacity、D4 coalition replay、D5 OpenCV PnP、D6 py-motmetrics、D7 3D/APN/FRPN 均按 available/unavailable 口径隔离运行 | 仅 benchmark；不进入默认 requirements 和在线控制路径 |

本轮统一回归结果：D1 62、D2 67、D3 123（1 skipped）、D4 144、D5 155、D6 82、D7 117、AirSim runtime 90，均通过。唯一 D3 skip 为未安装 optional OR-Tools；PNG delivery 核心公式未修改。

### P1/P2 模块边界复核

| Owner | P1 当前状态 | P2 当前状态 | 默认路径是否替换 |
| --- | --- | --- | --- |
| D1 | governed replay、truth policy 和融合合同完成；真实长 replay、CI/阈值长期标定开放 | 冻结 replay benchmark 已实现；当前环境 FilterPy/Stone Soup unavailable，显式给出原因 | 否，仍为 NumPy EKF/fixed-lag |
| D2 | D1 adapter、offline truth、N-target synthetic dense calibration 完成；真实长 replay 开放 | GNN/JPDA/MHT 同 replay 对照完成；FilterPy/Stone Soup 对象 adapter 不提供身份指标 | 否，仍为 GNN/Hungarian |
| D3 | M-to-N demand-slot、增量规划、role-aware primary 和 commit/current-binding 合同完成；动态非等量长期标定开放 | capacity benchmark 已实现；当前 OR-Tools unavailable 并显式报告原因 | 否，仍为 SciPy Hungarian/demand-slot |
| D4 | secondary/peer commit、故障矩阵和 member loss/replacement replay 完成 | 原生 6 场景 replay 完成；MIT/CA-CBBA 未配置或未集成时显式 unavailable | 否，仍为本地轻量 CBBA/原子 commit |
| D5 | detect-first 匿名 local track、几何锁定、预测/丢失不锁定和 runtime record 完成；真实多 seed 标定开放 | OpenCV calibration/PnP 离线 benchmark 完成；YOLO/ByteTrack 数据集标定 deferred | 否，在线默认仍为 AirSim detect 与保守门控 |
| D6 | pair/target/coalition、四层结果语义和 detect/coast 诊断完成 | py-motmetrics 可选；HOTA/TrackEval 依赖不足时保持 unavailable | 否，仍为本地 D6 指标主线 |
| D7 | commit-aware gate、N/M topology、有界 KF/coast 外推和 SimpleFlight consumer 接线完成；真实长时标定开放 | 3D PN、True PN、APN、FRPN 仅离线 benchmark；FRPN 是研究近似 | 否，仍为既有位置 PN/视觉 PNG |

## 2026-07-11 P1 收敛实施前基线

真实 AirSim ComputerVision 证据目录为 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_*_20260711/`，中文汇总为 `M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。该目录属于生成输出，不作为在线真值源。

| 核查项 | seeds 7/17/27 结果 | 当前判定 |
| --- | --- | --- |
| 中心重规划 lifecycle | 每 seed 6 request、6 no-change ACK、0 applied、0 expired，收敛 0.5 s | P1 状态闭环已完成，保持回归 |
| M-to-N 需求槽 | satisfaction=1.0、unmet=0、错误重复锁=0 | 中心化 demand-slot 与合法多锁已完成 |
| T002 单 primary | 共识帧 4/5/4，每 seed 2 次 D7 终端合同许可 | D3-D5-D7 k=1 链路已闭合 |
| T001 hybrid 2+1 | 双 primary 共识帧均为 0 | P1 未闭合；不得宣称协同末端完成 |
| 二级/无中心 k>1 | 当前 `coalition_fallback_unsupported` 并 fail-closed | P1 待实现 ACK/commit/epoch/lease 原子联盟 |
| 物理拦截 | ComputerVision 不执行 SimpleFlight 控制 | P1 待 90 s、10-seed SimpleFlight 验证 |

实施前统一回归基线：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，均通过。D1-D7 owner 已先行同步各自 PLAN/GAP/review；后续能力变化后必须由同一 owner 再次回写实际状态。

## 2026-07-11 M 对 N 协同拦截调研增量

D1-D7 已分别完成高威胁目标 \(k_j=3\) 的文献、开源实现和模块边界审计，main 汇总见 `subagent_reviews/MAIN_M_TO_N_COOPERATIVE_INTERCEPTION_SYNTHESIS.md`。

以下表格保留 2026-07-11 实施前的调研基线，用于解释任务来源；其状态已被后文“中心化 M 对 N 实施闭环”取代：

| Owner | 实施前 P1 新缺口 | 实施前边界（历史） |
| --- | --- | --- |
| D1/D2 | 多平台共同估计时刻、几何质量、跨节点 track registration、公共信息谱系和 CI | 当前有双时间戳、协方差、GNN/Hungarian 和中心 ID 基础，无协同 Track-to-Track 全链路 |
| D3 | target demand、b-matching/flow、联盟原子激活、角色、同步/波次和版本 | 实施前 Hungarian 仍是一对一 |
| D4 | coalition commit/ACK/lease、缩编/补位/重组、分区和恢复 digest | 当前 CBBA 是单 winner，不支持原子 \(k_j>1\) |
| D5 | planned cooperative lock、over support、多视角几何质量和联盟时序 | 当前多资源同目标可能仍被旧 duplicate 语义误判 |
| D6 | 需求满足、联盟形成、到达离散、波次、协同定位一致性和安全统计 | 需在现有 EpisodeMetrics 上新增 M 对 N 口径 |
| D7 | cooperative 与 independent pair 边界、到达窗口、终端扇区、最小间距和成员退出 | 当前仅有任意 N 个独立 PN/PNG pair |

建议默认研究比较 hybrid 2+1、simultaneous 3、sequential 1+1+1 和 independent PN。只有完成上述合同后才能启用 \(k_j>1\)；否则 D3/D4/D5/D7 断链会成为该新增场景的 P0 blocker。

### 2026-07-11 中心化 M 对 N 实施闭环

上述新增场景的中心化 P0 合同已经闭合，原调研表中的“当前仍是一对一/尚未实现”不再代表当前代码状态：

| Owner | 已完成 | 仍保留的 P1 |
| --- | --- | --- |
| D1 | 2..N bearing-ray 定位、共同估计时刻传播、协方差膨胀、CI 和 lineage 去重 | 真实 AirSim 多视角观测接线与几何阈值标定 |
| D2 | `SourceTrackSummary`、公共时刻马氏/Hungarian 注册、canonical registry、跨节点 ID 指标 | 真实 5v5 replay 与 D1 CI 请求闭环标定 |
| D3 | schema v2、`TargetDemand`、demand-slot Hungarian、all-or-none admission、hybrid 2+1、联盟/计划版本与迟滞 | CP-SAT/MILP 复杂约束参考；OR-Tools 仅为可选 benchmark |
| D4 | 中心有效时验证联盟；中心失效且 `k_j>1` 时 fail-closed，禁止单赢家 CBBA 冒充联盟 | 二级/完全分布式 coalition commit、ACK、lease、补位和重构 |
| D5 | 联盟只读合同、合法三成员锁、超额/版本冲突、reserve standby 门控 | 真实多视角三角定位与跨视角 AirSim 多 seed 标定 |
| D6 | demand/coalition/arrival 记录、需求满足、波次、合法锁、通信和安全指标 | 真实 episode 的 arrival/成员损失/替换证据积累 |
| D7 | 成员级 role/wave/window/version gate；reserve 未激活阻断；PNG 核心公式未改 | 同步到达可达性、终端扇区、最小距离和多 seed 飞行校准 |
| main | `--resource-count M --target-count N`、协同需求 CLI、D3→D5/D4/D7/D6 总线、5v2 3+1 闭环 | 真实 Blocks 5v2 多 seed 与 SimpleFlight 3v1/5v2 长时飞行 |

回归证据：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，全部通过。质点 `cooperative_3v1`/`cooperative_5v2` 的需求满足率为 1.0、shortfall 为 0；main episode bus 的 5-resource/2-target 测试形成 3+1 assignment pair，D5/D7 均保留 4 个独立上下文。中心和二级失效时三机联盟输出 `coalition_fallback_unsupported` 并 hold，不发布伪分布式联盟。

## 2026-07-11 P1 实施与真实 AirSim 结果

详细报告见 `subagent_reviews/MAIN_P1_AIRSIM_RUNTIME_VALIDATION_REPORT_20260711.md`。

| Owner | 实施结果 | 当前证据与结论 |
|---|---|---|
| main/runtime | D2→D3/D5 无 truth 转换、仿真 actor alias 边界隔离、D1-D4 governance/lifecycle、guidance experiment law 回灌 | 5v5/2v2 真机进程运行完成；在线 `truth_id=None` 不再造成 D3 空计划 |
| D4 | truth/continuity unavailable 不触发虚假硬风险，在线风险门限保持 | 中心保持和 distributed 负例通过；secondary 正例仍因 full-view readiness 不足而未闭合 |
| D5 | bbox-only offline truth parser 支持真实 AirSim 输入，truth 不进入在线 tracker | 84 个相机样本接口通过；当前模型 accepted detection=0，效果仍为 P1 |
| D6/main | 四导引律 experiment law 可配对，生成 JSON/CSV/中文报告/曲线 | 21 条指标配对行，只有 seed 7；四律 2 秒均 timeout，不作为命中率结论 |
| D7 | Pure Pursuit、Radar PN、PNG-VM、PNG-TTC 真实 SimpleFlight selector/gate 接入 | PNG VM/TTC switch allowed 约 0.762/0.810；需长时多 seed |

## 2026-07-10 P0/P1 实施与实测结果

本轮继续严格执行 “main 下发、D-agent 自改自测、main 只改 runtime/集成/总文档并运行 AirSim”。

| Owner | 实施结果 | 实测/验收 |
|---|---|---|
| main/runtime | stale D3 plan 被拒后保留当前 plan；YOLO/MOT adapter 跨 episode 重置 stream；AirSim builtin detect 改为匿名 camera-local bbox tracker，局部 ID 不含 actor 名 | `p0_truth_isolation_smoke_20260710` 三 case connected，匿名 ID 连续 5 帧，actor-name online 泄漏为 0 |
| D1 | 复核真实 2v2 双时间戳、协方差 finite/symmetric/PSD 和 NED 合同，无源码回归 | 1528 条观测可回放；32 tests passed |
| D2 | truth-unavailable continuity、rejected-pair replay、covariance validation/diagnostic | 39 tests passed |
| D3 | active plan 后 previous-plan 必填；switch penalty 进入 Hungarian 矩阵；stale plan 保留 | 63 tests passed |
| D4 | 保持 takeover-ready 安全门限，并对 60-case 结果完成状态机诊断 | 84 tests passed；15/1300 决策瞬时 takeover-ready，active plan 为 0 |
| D5 | friend-aware reacquire、actor-name category 隔离、MOT per-stream state/reset | 96 tests passed；匿名 ID smoke 各 case cross-view association=4 |
| D6 | cross-seed/scenario-group 聚合、paired baseline/enhanced、deterministic bootstrap、review labels；拦截 outcome/距离/时间/视觉切换/gate 指标进入 cross-seed | 48 tests passed；D6 报告只把有 intercept evidence 的 full-flow 列入 outcome，execution=18/20，read-only 不再误报 0/20 |
| D7 | 不改 PNG 控制律，复核真实 10-seed guidance/gate 输出 | 45 tests passed；18/20 拦截成功 |

AirSim 证据：

- `outputs/p1_gap_closure_calibration_20260710`：10 seeds、50/200 m、3 个二级节点、110 deg、1920x1080、三 case，共 60 episode。
- `outputs/p1_gap_closure_2v2_multiseed_20260710`：10 seeds、20 pairs，18 collision intercept、2 terminal detection timeout；pair 等权平均最小距离 2.113 m，D6 每 episode 最小值均值 1.812 m。
- D4/D5 的主要未闭合项不是投影或注册，而是 sustained network full-view、逐决策 stable evidence 和 secondary plan activation。
- D7 的主要未闭合项是视觉 gate 通过率和 PN/Pure Pursuit/PNG-TTC/PNG-VM 同 seed 对照，不是 PNG 核心公式重写。

## 2026-07-09 P0 实施结果

本轮严格按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。main 只修改 AirSim runtime/总线桥接和 main GAP 文档；D1-D7 各自只改 owned paths。

| Owner | P0 实施结果 | 验证 |
|---|---|---|
| main/runtime | episode bus 输出 episode clock、scenario config、D1-D7 module health、runtime errors、mission outcome/root cause/performance metadata；D4/D5 stress bridge 正确把二级注册 evidence 输入 D4，并避免把 `registered_to_global_track` 当作拒绝原因；P1 calibration suite/threshold metadata、高度对比和 secondary owner 保持已实现 | `pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py` -> 59 passed |
| D1 | sensor health、covariance floor/ceiling reason、timestamp uncertainty、replay summary、latency audit 和区域质量摘要已实现 | 32 passed |
| D2 | motion consistency cost、quality-aware gate baseline、`track_quality/association_risk/quality_metadata` 已实现 | 31 passed |
| D3 | 资源状态细化、high-threat release、结构化 stale rejection、explainable threat baseline 和 assignment evidence export 已实现 | 56 passed |
| D4 | heartbeat smoothing、lease/epoch strictness、secondary capability score、active degradation debounce 和 `secondary_capability_class` 已实现；active secondary plan 同 id/version 回归已修复 | 84 passed |
| D5 | active reacquire、temporal consistency、candidate margin、calibration health metadata 和 detect registration outcome 已实现 | 79 passed |
| D6 | mission outcome、failure reason、top failure causes、eval priority/status/evidence path、performance metrics 和 P1 calibration 标准报告 bundle 已实现 | 38 passed |
| D7 | terminal latch、dwell/release/reacquire grace、filtered LOS rate/outlier reject evidence、3D PN benchmark/log 和 P1 switch/gate calibration fields 已实现 | 45 passed |

`git diff --check` 通过。D2、D6、runtime 的 matplotlib Axes3D warning 为本机环境 warning，不构成 P0/P1。

## 2026-07-09 P1 实施结果

本轮 P1 实施仍按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。D1-D7 各自更新 owned paths 和 GAP/PLAN/README/review；main 只修改 AirSim runtime、测试和 main-level GAP/status。

| Owner | P1 实施结果 | 验证 |
|---|---|---|
| main/runtime | `--p1-calibration-sweep` 输出 suite/version/threshold、二级高度/FOV/数量/站距、expected state fields 和 50/200 m 高度对比；自动生成 D6 `d6_airsim_calibration` bundle；修复 secondary takeover plan 在连续 replan 后 `owner_node_id` 回退为 `d3_central` 的问题 | runtime 59 passed；`p1_gap_fix_smoke_20260709` 生成 6 行 smoke summary |
| D1 | dry-run/replay 增加 schema/version/metadata 检查、latency/OOSM audit 和区域质量摘要 | 32 passed |
| D2 | replay 输出 association risk threshold version、gate pass/reject、risk summary 和 threshold sensitivity | 31 passed |
| D3 | 增加 assignment evidence export、cost breakdown/rejected edges/stale reason/secondary fields 和硬时间窗闭合边拒绝 | 56 passed |
| D4 | 增加二级 readiness/capability class，D7 handoff 需 `takeover_ready` 才放行 active secondary visual PNG | 84 passed |
| D5 | detect-to-global candidate 增加 outcome、reject reason、timestamp/age、projection/covariance 和 YOLO/MOT metadata；`projection_invalid` 独立成因 | 79 passed |
| D6 | AirSim calibration report 保留 scenario/standard mapping/evidence/trend/height bucket/actual scale；Markdown 增加 50/200m、coverage funnel、stable registration、D7 reject 等口径 | 38 passed |
| D7 | runtime/comparison/replay/calibration 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block reason、D5/D3 consistency、secondary capability、threshold advisory version 和 visual PNG switch count；未改 PNG 核心控制律 | 45 passed |

## 1. 总体结论

当前项目已经形成一条可运行的轻量科研主线：

```text
D1 NumPy EKF/FusionAdapter
-> D2 GNN/Hungarian 关联与 ID 指标
-> D3 SciPy Hungarian 分配与迟滞
-> D4 C2Health + 主动/被动降级 + 轻量 CBBA
-> D5 几何投影门控 + 保守 TerminalAssociation
-> D7 PN / SimpleFlight 视觉 PNG gate
-> D6 离线 EpisodeMetrics / JSONL / Blocks replay 评估
```

已经落地的主要是**自研轻量实现和少量成熟 Python 科学计算库**：NumPy、SciPy、OpenCV `projectPoints`、AirSim `simGetDetections` metadata、D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter、SimpleFlight 控制、D7 delivery 包中的 YOLO+ByteTrack 可选链路。

**2026-07-08 子智能体复核状态**：D1-D7 已分别重审并更新各自 PLAN/GAP 文件，所有子 GAP 均明确拆分为“已实现、部分实现、未实现、未实现原因、缺少条件、下一步优先级”。本轮确认：D1 的 replay schema v1、legacy JSONL、最小 CSV reader/replay、latency/OOSM audit 和区域质量摘要已实现；D2 的 replay helper、5v5 dense/crossing fixture、风险阈值敏感性和显式 ID 指标已实现；D3 的 D5 feedback writeback、secondary takeover DTO/helper、D7 binding、owner/version/source metadata 和 D6 export 已实现；D4 的主动降级硬/软风险分层、二级节点 lifecycle、secondary takeover metadata、D5 evidence 到 CBBA 和 cost gap helper 已实现；D5 的几何日志、handoff advisory、一致性窗口、truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter、可运行 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 已实现；D6 的 execution/contract 双口径、实际规模分组、主动降级精度和 D7 replay 指标已实现；D7 的 runtime bus、comparison/replay helper、N-pair 状态、D4 gate blocking、owner/version gate 和 terminal contract gate 已实现。

尚未落地的主要是**完整外部工程栈、生产级适配或高阶主线替换**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、Deep SORT/ReID、SCRIMMAGE、TrackEval/HOTA、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。BoT-SORT 和 py-motmetrics 已有 optional adapter/可用性路径，但真实多 seed、依赖和指标口径未完成时不算生产落地。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main runtime bus 接口基线已接入**：AirSim runtime 已在同一 episode 中持续写入 D1-D7 summary/record 和 D6 JSONL；2026-07-08 已把执行拦截结果回灌到正式 main bus metrics，接入 D5 feedback、二级接管 owner/version 和 D7 runtime bus，并保留 raw contract metrics；2026-07-09 P1 calibration sweep 已自动回灌 D6 标准 CSV/JSON/Markdown 报告 bundle，且 summary 保留 suite/threshold version 与高度对比；secondary takeover 连续 replan 时 owner 不再回退为中心节点；下一步仍需真实 Blocks 多 seed 校准。
3. **二级侦察看清不等于可接管**：2026-07-08 5v5 registration calibration v2 中，二级云台指向成功率为 1.0，`projection_valid_rate=1.0`，几何门通过率约 0.474，稳定跨视角注册约 51/55/53，cross-view association 为 4/4/5；但 `secondary_network_joint_full_view_frame_rate` 均值仍约 0.048，联合覆盖约 0.771，主要断点是 `not_all_targets_visible` / `network_union_incomplete`。它说明二级节点已能提供有效注册证据，但不能绕过 D3/D4/D5 的分配、仲裁和视觉 PNG gate。
4. **真实图像/通信/身份源仍需标定**：D5 已能运行 YOLOv8 + MOT 并由 main runtime 显式接线；Remote ID、MAVLink signing、AprilTag 仍需要真实报文、密钥和时间同步，YOLO/MOT 仍需要 AirSim 多 seed 阈值标定。
5. **高阶算法需要基准场景支撑**：IMM、JPDA/MHT 完整版、FRPN、MPC、OSPA/HOTA 等应在 5v5 crossing、遮挡、主动降级和 AirSim replay 稳定后再做对照。

## 2. 横向开源/共识方案落地状态

| 共识/开源项 | 预期用途 | 当前状态 | 涉及模块 | 未实现/未完全实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|---|
| EKF | 融合和航迹滤波主线 | **已实现轻量版**。D1 自研 NumPy EKF，D2 自研二维线性 Kalman | D1, D2 | 未使用 FilterPy/Stone Soup 后端 | 外部库对照接口、三维/非线性量测合同 | P0 已可用，P2 对照 |
| UKF | 强非线性量测升级 | 未实现 | D1, D2 | 当前 EKF/CV 已满足 phase-1；不想提前引依赖 | UKF 后端、sigma-point 参数、强非线性场景 | P2 |
| IMM-EKF/UKF | 高机动目标模型切换 | 未实现 | D1, D2 | 当前场景以 CV/二维基础关联为主 | CV/CA/CT 模型、转移概率、机动基准 | P2 |
| Stone Soup | 多目标跟踪、JPDA/MHT、轨迹融合、指标对照 | **占位/文档级**，未作为运行依赖 | D1, D2, D6 | 默认环境轻依赖；Stone Soup 对象不宜直接污染系统总线 | 安装版本、adapter、对照数据和指标门限 | P2 |
| FilterPy | EKF/UKF/IMM 原型 | **占位/可用性检查**，未调用 | D1, D2 | 已有自研 NumPy fallback | 依赖策略、状态/量测模型、测试容差 | P2/P3 |
| ROS 2 `tf2` | 坐标树、外参、frame 变换 | 未实现 | D1, D5, D7 | 当前是 Python 离线/AirSim runtime，不启动 ROS 图 | ROS 2 runtime、frame tree、带戳消息 | P3 |
| ROS 2 `message_filters` | 多传感器时间同步 | 未实现 | D1, D5 | 当前用 `measurement_timestamp/arrival_timestamp` 和离线 replay | topic schema、同步策略、bag/replay | P3 |
| SciPy `linear_sum_assignment` | Hungarian 关联/分配 | **已实现** | D2, D3 | 不适用 | 仅需保持 SciPy 依赖 | P0 |
| OR-Tools Min Cost Flow | 多容量/复杂约束分配 | 接口预留，未实现 | D3 | 当前 5v5 一对一 Hungarian 足够 | OR-Tools 依赖、容量/需求/禁配边结构 | P1/P2 |
| GNN/Hungarian | 多目标硬关联主线 | **已实现** | D2 | 不适用 | 需增加 5v5 dense/crossing 压测 | P0 |
| JPDA | 密集交叉软关联 | **轻量对照版**，非完整生产级 | D2 | 仅枚举小规模假设，不做完整概率混合更新 | Stone Soup 对照、密集交叉基准、参数标定 | P1 |
| MHT | 多扫描假设跟踪 | **有界 placeholder** | D2 | 完整 MHT 延迟/内存高，不适合资源节点 | N-scan pruning、分簇、中心算力假设 | P2 |
| PN 比例导引 | 单目标/中段默认导引 | **已实现** | D7 | 当前是二维经典 PN 和 SimpleFlight gate | 三维状态、D5/D3 门控、真实飞控约束 | P0 |
| Pure Pursuit | 对照 baseline | **已实现轻量 baseline**。D7 提供 `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law=\"pure_pursuit\"` | D7 | 未直接引入 PythonRobotics，有意保持轻依赖 | 多 seed PN/Pure Pursuit 对照报告、AirSim controlled 选择开关 | P1 已完成基线 |
| 改进 PN / FRPN | 高机动增强导引 | **已有隔离式研究近似 benchmark，未进入主线** | D7 | 当前先稳定经典 PN/PNG；现有 FRPN 不是生产级完整实现 | 目标加速度估计、严格公式、机动场景和同输入对照 | P2 benchmark |
| 视觉 PN / PNG | 末端视觉导引 | **部分实现** | D7 | 已有 bbox gate、LOS-rate、TTC/VM，仍非严格纯视觉闭环 | D5 locked、距离/闭合速度估计、相机标定 | P0/P1 |
| AirSim `simGetDetections` | CV 检测框输入 | **已使用** | D5, D7, main runtime | D5 不直接调 AirSim，只消费 fixture/replay；D7/main 调用 runtime | 稳定 detection schema、camera/object ID 映射 | P0 |
| OpenCV `projectPoints` | 图像投影和门控 | **已实现单相机主线**。D5 优先调用 `cv2.projectPoints`，无 OpenCV 时有针孔 fallback，并传播像素协方差 | D5 | 未实现 calibration/solvePnP/跨相机联合优化 | 准确 K/R/t/dist、标定样本、PnP 2D-3D 对应 | P0 已可用，P2 标定增强 |
| OpenCV calibration / `solvePnP` | 相机标定、外参估计 | 未实现 | D5 | 当前假设 AirSim/runtime 提供相机参数 | 2D-3D 匹配点、标定图、PnP RANSAC | P2 |
| YOLOv8 + ByteTrack/BoT-SORT | 局部检测/MOT 默认候选 | **P1 已接入显式运行路径**。D5 `YoloMotAdapter` 可加载 `best.pt`，优先 ByteTrack/BoT-SORT，失败时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5，并转换为现有 detection contract | D5, main runtime, D7 | 默认仍不保存 PNG；MOT ID 只作为 `LocalVisualTrack.local_track_id`，不得替代 `global_track_id` | AirSim 多 seed 阈值、class id、GPU/CPU 预算、MOT IDSW 标签 | P1 接线已完成，P1/P2 标定 |
| BoT-SORT | 运动相机 MOT | **已接入 D5 可选 tracker backend**，失败时可回退 IoU；未完成真实 ReID/相机运动补偿验收 | D5 | 当前缺真实图像多 seed 和稳定 ReID/运动补偿证据 | 图像序列、依赖、ReID 模型、IDSW truth | P1/P2 标定 |
| Deep SORT | 外观辅助 MOT | 未实现 | D5 | 当前小目标外观未建模 | embedding 模型、图像帧、IDSW 真值 | P2 |
| OpenDroneID / Remote ID | 友方身份正向声明 | **模拟实现** | D5 | 只解析 `protocol=OpenDroneID` 风格 dict，未接 Core C | 报文解码器、白名单、签名/位置一致性 | P1 |
| MAVLink signing | 消息来源认证 | 未在 D5 实现；D7 delivery 有 MAVLink 控制路径 | D5, D7 | 当前没有真实 MAVLink telemetry/signing key 管理 | MAVLink source、签名库、密钥策略 | P2 |
| DDS Security | ROS 2 中间件认证 | 未实现 | D5, main | 当前无 ROS 2/DDS runtime | enclave、证书、权限文件、节点映射 | P3 |
| AprilTag | 合作视觉标签 | 未实现 | D5 | 当前无图像帧和 tag detector | 图像流、tag ID 映射、误检评估 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA | 分布式降级对照 | 未接入；自研轻量 CBBA | D4 | 外部项目接口/许可证/依赖和 summary bus 不匹配；本轮 P1 明确暂不构造外部开源算法 | adapter、同场景 benchmark、许可证审查 | P2 |
| 拍卖算法 | 分布式保底 baseline | 未单独实现 | D4 | 当前 CBBA 机制覆盖拍卖式思想，但无独立 baseline | bid/award/rollback 协议和测试 | P1 |
| 合同网协议 | 分布式任务协商对照 | 未实现 | D4 | 非 5v5 最小闭环必需 | announce-bid-award 状态机 | P2 |
| SCRIMMAGE | 大规模多智能体仿真 | 未实现 | D6/main | 当前优先 AirSim CV 5v5 和质点仿真 | SCRIMMAGE 输出样例、ID 映射、时钟对齐 | P3 |
| TrackEval / py-motmetrics | HOTA/IDF1/MOTA/MOTP | **py-motmetrics optional adapter 已实现**；依赖缺失时 unavailable。TrackEval/HOTA 未接入 | D6 | 当前先保持本地可解释指标，外部结果不得回流控制 | 稳定 MOT 导出、帧级 truth 匹配、TrackEval 依赖版本 | P2 |
| Stone Soup metrics / OSPA/GOSPA/SIAP | 标准跟踪指标对照 | 未实现 | D6 | 需要 D1/D2 Stone Soup Track adapter | cutoff/order、匹配门限、坐标合同 | P2 |
| PX4 SITL / MAVLink body-rate | 更真实飞控闭环 | delivery 包有实验路径，main 未接入 | D7 | 当前主线选 SimpleFlight，避免飞控复杂度 | PX4 SITL、Offboard 状态机、推力/坐标标定 | P2 |

## 3. 各子模块核心结论

| 模块 | 已实现主线 | 关键未实现项 | 直接阻塞条件 | 详细文件 |
|---|---|---|---|---|
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；measurement/arrival timestamp；NED 六维状态；协方差；雷达/声学/EO/合成 LiDAR；延迟补偿；AirSim dry-run；Blocks JSONL reader/replay；replay schema v1/legacy JSONL；最小 CSV reader/replay；`TrackUncertaintySummary`；`LatencyAuditSummary`；`FusionQualityRegionSummary`；source de-dup；N-target 输入 | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2/message_filters、D1 包内真实 AirSim CV 直连、Track-to-Track fusion、更多真实 Blocks/CV fixture | 真实相机/传感器外参、稳定 detection schema、外部依赖、跨节点相关性策略、D6 长期批量 schema | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter、`crossing_dense_5v5`、风险滑窗、D1 adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、真实 AirSim CV replay 压测 | 5v5 replay 样本、风险阈值、三维跟踪策略 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6 assignment record export、AirSim dry-run、main episode bus plan/version 输出 | OR-Tools Min Cost Flow、D5 feedback 自动写回真实代价 | D5/D6 重复锁定聚合校准、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、`SecondaryNodeLifecycleSummary`、CommunicationSummary、主动降级防抖、轻量 CBBA、中心恢复合并、D4 arbitration adapter、D6-compatible event metadata、main episode bus D4 event 写入 | MIT/CA-CBBA 适配、独立拍卖/合同网、真实视频 cue adapter | 二级 heartbeat/coverage/link freshness 的真实 Blocks 多 seed 校准 | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | `GlobalTrack -> CameraModel -> projected image point -> LocalVisualTrack -> TerminalAssociation`；OpenCV `projectPoints`/fallback；马氏门控；保守 `locked/ambiguous/hold/reacquire`；AirSim bbox adapter；YOLOv8 + MOT runtime adapter；truth ID 在线隔离；二级 cue；跨视角摘要；`TerminalConsistencySummary`；视觉 PNG handoff advisory；main episode bus terminal record；禁止改写 ID | Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration、ROS2 tf2、跨相机几何联合优化 | 协议报文/密钥、相机标定样本、二级节点真实 pose/detection、真实 AirSim 多 seed YOLO/MOT 阈值标定 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、D4 active/passive degradation、D7 intercept/guidance time-series、PNG delivery 对照和 py-motmetrics optional adapter | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA、长期主动降级 review label | 标准帧级匹配表、真实 D4 metadata、D7 同条件多 seed records/summaries | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、雷达中段 PN、Pure Pursuit baseline、视觉 PNG、TTC/VM、D3/D4/D5 gate、生命周期 KF、`png_ttc` 面积治理、N-pair filter、6D LOS/3D/APN/FRPN optional benchmark | 严格生产级 3D/FRPN、完整视觉闭环、PX4/MAVLink 主线、MPC/NMPC、ViSP/ROS2 | 同条件 M5N2、1-5 帧 dropout、真实 `png_ttc`、trend coast 晋级和平台动力学约束 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### 4.1 已完成的 P0/P1 接口基线

1. **D1 融合合同已成型**
   `SensorObservation`、`measurement_timestamp/arrival_timestamp`、协方差、NED 六维状态、fixed-lag 延迟补偿、雷达距离相关协方差、source lineage 去重、`TrackUncertaintySummary` 和 Blocks JSONL reader/replay 已实现。

2. **D2 关联与身份指标已成型**
   GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT 对照、`id_switch_count`、continuity、duplicate assignment、D1 adapter、AirSim dry-run adapter、`crossing_dense_5v5` 和风险滑窗已实现。

3. **D3 分配到 D7 的版本化合同已成型**
   SciPy Hungarian、fallback DP、迟滞、stale plan 拒绝、版本化 `AssignmentPlan`、D5 feedback helper、`AssignmentGuidanceBinding`、`AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出已实现。

4. **D4 主动/被动降级仲裁已成型**
   `C2Health`、被动降级、主动降级、二级节点 lifecycle、communication freshness、D1/D2/D3/D5 evidence adapter、D6 event metadata、轻量 CBBA、D7 two-stage secondary handoff 和中心恢复合并基础版已实现。2026-07-07 已增加硬/软风险分层：`d3_assignment_not_current/stale` 仍触发中心重规划，`d3_assignment_cost_margin_low` 与早期 D5 低置信度只进入观察；无 observed mismatch、资源错配、重复锁定或友方冲突的持续 D5 `ambiguous/reacquire` 不再造成名义场景每帧 `request_center_replan` 或分布式降级。

5. **D5 末端视觉配准安全合同已成型**
   OpenCV `projectPoints`/fallback、像素协方差传播、马氏门控、`LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、AirSim/YOLO bbox schema adapter、AirSim truth ID 在线隔离、二级 cue、跨视角重复锁定风险、`TerminalConsistencySummary` 和视觉 PNG handoff advisory 已实现。

6. **D6 离线评估主线已成型**
   `EpisodeMetrics` 显式保留实际 `drone_count/resource_count/target_count/camera_count`，并可消费 track/assignment/event/link/terminal、Blocks replay、D4 active/passive degradation、D7 intercept replay、D7 guidance time-series、批量 CSV/Markdown/PNG 报告。

7. **D7 PN/PNG 导引合同已成型**
   经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar-to-vision 质点闭环、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、handoff/hold/reacquire/revoke 状态和 N-pair 独立 filter 单测已实现。

### 4.2 当前最关键的未闭合项

1. **main runtime bus 已完成接口闭合，仍需真实多 seed 校准**
   `research_modules/airsim_runtime/episode_bus.py` 已由 main 串接 D1 track、D2 risk、D3 plan/version、D4 action、D5 terminal decision、D7 pair state 和 D6 collector，并在每个 Blocks episode 输出 `main_episode_bus.jsonl`、ticks、metrics 和 summary。执行拦截时，main 还会把 `control_commands.csv` 和 `intercept_summary.json` 的成功数、碰撞拦截数、guidance law 和 terminal reject 回灌到正式 metrics，同时保留 contract-only metrics。2026-07-08 已补齐 D5 terminal feedback 到 D3、D4 二级接管 owner/version 到 D3/D7，以及 D7 N-pair runtime summary。2026-07-09 已补齐 P1 calibration sweep suite/threshold metadata、高度对比、D6 标准报告 bundle，并修复 secondary takeover 连续 replan 后 owner 回退问题。未闭合的是在真实 Blocks 长时/多 seed 条件下校准阈值、状态迁移和降级必要性标签。

2. **N-pair 真实控制状态机已有 main 接线，仍需真实多 seed 校准**
   D7 已支持每个 assignment pair 独立 filter，main runtime bus 已按每个有效 pair 注入 `AssignmentGuidanceBinding`、D4 permission/action、D5 `TerminalAssociation`、资源状态、目标估计并写 D6 guidance log。下一步重点不是再补接口，而是在真实 Blocks 多 seed 下校准终端切换、重捕获和拒绝原因分布。

3. **D4/D5/D7 的状态迁移需要真实 episode 校准**
   `locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 terminal contract reject 需要在多 seed AirSim replay 中统一记录与评估。本轮已修正软 cost margin 造成的 replan 抖动，并把“无冲突持续重捕获”与“真实 terminal mismatch”分离，但阈值仍需 5v5/multi-seed 统计确认。

4. **机动高空侦察二级节点仍需覆盖/配准校准**
   5v5 registration calibration v2 已验证二级节点 `mobile_recon_gimbal`、`radar_global_track_cue`、200 m 高差、110 deg FOV 和 1920x1080 观测链路能稳定出图、保持有效投影，并把二级 detect 转成稳定 cross-view registration。当前未闭合的不是姿态/投影，而是二级网络同帧全目标覆盖：`secondary_network_joint_full_view_frame_rate` 均值约 0.048，主要断点为 `not_all_targets_visible` / `network_union_incomplete`。下一步应优先校准二级站位/扫描策略、coverage cell、cue freshness、外参/时间戳和 D6 coverage funnel 指标。

5. **YOLO/MOT 已有显式运行路径，真实协议/标定链路仍待推进**
   D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 和 main `--detection-backend yolo` 接线已完成；Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration 和 ROS2 tf2/message_filters 仍需真实图像/报文、密钥、相机外参、时间同步和依赖隔离。

6. **高阶算法仍需作为 optional benchmark 接入**
   UKF/IMM、完整 JPDA/MHT、Stone Soup、FilterPy、OR-Tools Min Cost Flow、MIT/CA-CBBA、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、FRPN、MPC、PX4/MAVLink 都不应直接替换当前轻量主线，应先在同场景对照报告中验证收益。

### 4.3 直接下一步缺口

1. main 继续用 `MainAirSimEpisodeBus` 做 Blocks episode 的统一 DTO/record 总线，并保持 `main_episode_bus.jsonl` 可由 D6 `load_episode_log_jsonl()` 反读。
2. main 在真实 Blocks 多 seed 中校准 D3 `AssignmentPlan`、D3 `AssignmentGuidanceBinding`、D4 action、D5 terminal decision 和 D7 guidance records 的状态迁移阈值。
3. main/AirSim runtime 继续固化 Blocks JSONL/replay schema，保留实际目标数、资源数、相机数、bbox、相机内外参、truth offline label、plan/version、D4/D5/D7 状态字段，并避免在线 D5 使用 truth ID。
4. main/D4/D5/D6 继续跑机动高空侦察节点 5v5 stress，分别统计单相机全局视野率、二级网络联合覆盖率、detect-to-registration 转换率、`secondary_detect_available_but_not_registered` 和 cross-view association。
5. D5 已实现 YOLOv8 + MOT runtime adapter，main 已接入显式 YOLO 检测后端。下一步用真实 AirSim 多 seed 校准 `best.pt`、置信度、tracker backend、目标尺度和 FOV 条件；adapter 只输出 `LocalVisualTrack`，不允许 tracker ID 替代 `global_track_id`。
6. D6 已实现主动降级必要性最小指标口径，main P1 sweep 已自动生成 D6 标准报告 bundle。下一步要求 main/D4 在真实 multi-seed episode 中持续写出 review/window 字段，形成可比较的 active degradation precision 和 unnecessary active degradation count。
7. D6/main 按 patch v2.0 新增 P0-A 口径补齐标准化评估映射最小版：先把当前工程指标映射到 COURAGEOUS、MDPI C-UAS、OCEF 的指标族，并在报告中保留 `standard_metric_family`、`scenario_version`、`evidence_path`、`implementation_status`；完整标准流程、场景库和显著性对比留作 P1。

## 5. 建议实施顺序

1. **保持 P0 合同回归**
   继续用 D3-D7 与 AirSim runtime 测试覆盖 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalAssociation`、D7 terminal gate 和 D6 intercept adapter。

2. **用 main runtime bus 做真实 episode 校准**
   main 已把 D3 plan/version、D4 action、D5 terminal decision、资源状态和 D7 控制 pair 合并到同一个 AirSim episode state machine，并写入 D6 已支持的分组/降级/guidance 字段；下一步用真实 Blocks 多 seed 校准阈值和报告口径。

3. **跑多 seed 校准**
   使用单次 Blocks 启动 reset 循环跑 CV 5v5、D4/D5 stress 和 2v2 intercept，校准 D4 防抖、D5 一致性、D7 terminal handoff 和 D6 分组指标。

4. **随后做开源对照，不替换主线**
   Stone Soup、FilterPy、TrackEval、ByteTrack、MIT/CA-CBBA、OR-Tools 都建议以 optional benchmark/adapter 方式接入，先生成同场景对照报告，再决定是否进入默认运行路径。

## 6. 子智能体交付文件

- `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md`

## 7. P0/P1 集中状态与验收

本节合并原独立 P0/P1 状态文档的权威信息。前文保留实现历史和开源落地审计，本节只维护当前优先级、保持项和验收入口。

### 7.1 当前判断

- 当前无开放运行级 P0 blocker；SimpleFlight 默认、主动中心重规划和主动二级接管已经统一使用 D2 估计状态。
- D1/D2/D6 身份隔离、指标 availability、到达时间队列、truth-state provenance 和逐 pair physical provenance gate 已修复；actor truth 仅允许进入离线评分边界。
- 现有 \(k_j=1\) 主线继续可用；M 对 N 的 demand-slot、合法多机锁定、二级/完全分布式原子联盟和成员级 D7 门控合同已实现。
- 历史 ComputerVision 合同验收为 8/10；当前已完成 5 m 成功判据、detect-first truth 隔离、1-5 帧硬窗口、D6 分层指标、2v2 `png_ttc` 20/20 和同条件 M5N2 paired。M5N2 candidate 退化且联盟 0/10，下一步是物理协同和阈值根因修复，不再扩展成功语义。
- P2 隔离 benchmark 已覆盖 D1-D7 的当前可运行范围；不可用外部依赖均显式记录 `unavailable_reason`，不得宣称为主线算法替换。

### 7.2 P0 保持矩阵

| Owner | P0 状态 | 必须保持的合同 | 验收 |
| --- | --- | --- | --- |
| D1 | 无新增 blocker | 双时间戳、NED、协方差、OOSM、source de-dup、局部图像航迹 fail-closed 适配和 GlobalTrack | D1 `111 passed` |
| D2 | 无新增 blocker | GNN/Hungarian、稳定 global_track_id、id_switch_count、continuity 和来源身份治理显式计数 | D2 `123 passed, 1 warning` |
| D3 | 无新增 blocker | 版本化 AssignmentPlan、迟滞、stale rejection、D7 binding | D3 模块测试 |
| D4 | 无新增 blocker | C2Health、主动/被动降级、二级 lifecycle；active secondary helper/owner 必须对 sustained readiness、expected/actual source、plan/required epoch、expiry/current time 和 plan monotonicity exact-true；冲突或缺失证据 fail-closed | D4 `280 passed` |
| D5 | 无新增 blocker | 不改写 global_track_id、truth 隔离、friend/duplicate 保守门控；原生 MOT 连续实测历史按 stream/backend/ID 隔离并在空帧/reset 后重计；离线人工记录转换重复坍缩 fail-closed；补充课程全样本审计不得开放在线权限 | D5 `486 passed` |
| D6 | 无新增 blocker | 只消费日志；实际规模、id_switch_count、unavailable/zero 分离；逐 pair physical evidence/result/source、联盟完整性和跨模块学习准入严格门控；D5 全样本证据需带外 SHA，报告不得写入正式 generation 根 | D6 `385 passed` |
| D7 | 核心公式无 blocker；控制输入 P0 由 main/runtime 持有 | 不分配目标；D3/D4/D5 gate 失败时阻断视觉 PNG；不修改 PN/PNG 核心公式 | D7 模块测试 + truth-isolated control contract |
| main/runtime | 无新增 blocker | episode bus 可回放；在线 truth identity/state 均为 0；SimpleFlight 只消费 D2 estimate；二级 communication 只消费上一完整 D4 readiness；actor truth 仅离线 5 m scorer；默认不保存 PNG | actor truth 扰动命令不变量 + heartbeat-only/strict-readiness 正反合同 + AirSim runtime `147 passed` |

### 7.3 当前 P1 清单

| Owner | 当前缺口 | 已有基础 | 缺少条件/下一验收 |
| --- | --- | --- | --- |
| main/D6 | 分阶段实时性能达标 | seed-1 actual truth-isolated 复验与 freshness 已关闭；两层 stage timing JSONL、严格 D6 consumer 和中文报告已实现 | 按相同配置运行真实 2v2/M5N2 至少 10 seeds，分别统计 control tick 与 bus 内层阶段 mean/P95/max、dominant stage 和预算违例；优化后复验 100 ms，不跨层相加 |
| D2/D6/main | v2 关联候选评审与跨 difficulty 证据 | 正式 v2 联合报告已生成；总体五项 gate 通过，IDSW 下降 54.6%，P95 15.47 ms，truth leakage=0；默认在线主线未改变 | 仅 `clutter/combined` 通过，四个零 baseline-IDSW difficulty fail-closed，dropout truth alignment 为 partial；需补同 case/seed 完整多源 system bundle 后再决定是否晋级，JPDA 保持不准入 |
| D3/D5/D7/main | M5N2 协同物理闭环 | 同条件 10-seed paired 和四层日志已完成；baseline 7/30 pair，candidate 4/30，联盟均 0/10 | 分离第二 primary 中段重捕、D5 共识、D7 gate 和成员安全根因；candidate 保持关闭 |
| D5/D7/main | 单帧 dropout 尾部 | 2-5 帧逐 seed 全通过，物理结果 100/100，truth/ID/version 无违规 | 复核 seed 2 在 0.8 s 注入时没有进入 image-KF 的锁定时序；不得用聚合计数掩盖 |
| D7/main/D6 | `png_ttc` 受控覆盖 | tuned 2v2 10 seeds 为 20/20，not-expanding/TTC-out-of-range 已实测 | 补 area-jump 与 bbox-clipping 受控注入，不把未自然出现解释为算法缺失 |
| D5/main | YOLOv8/native MOT 校准 | adapter、Results 连续历史和离线 benchmark 已有；当前在线明确继续使用 AirSim detect | 等数据集补充后再校准类别、尺度、置信度、远距召回、IDSW/continuity、GPU/CPU P95 延时和失败回退；代码级历史累计已关闭，不阻塞 detect-first P1 |
| D1/D2/D5/main | 通用图像来源谱系真实运行标定 | 局部观测合同、D5 离线适配、D1 EO 入口、D1 `source_track_ids`、main NED-only D2 handoff 和 D2 三项来源治理计数已实现 | 接入真实可见光/红外 producer 与 D5 拒绝计数，冻结内外参/时间同步/像素协方差；至少 10 个来源扰动 AirSim case 评估 false-suppression、recall 和离线 IDSW/continuity |
| D1/D2/D3/main | 长 replay 治理阈值 | 版本化 replay/CLI 已具备；D2 10 seeds 的 IDSW=138.1、continuity=0.694 | 默认 GNN 未通过阈值；继续调 gate/lifecycle/model，不用 truth 或本地重绑掩盖问题 |
| D4/main | 联盟重构、二级接管和恢复实测 | 9/9 确定性矩阵通过，含 member replacement、partition recovery 和双轨合并；严格二级 readiness 已统一到所有入口 | 映射到真实 AirSim 通信延迟/丢包/乱序/时钟漂移多 seed，并量化 failover time；不得以 heartbeat-only 作为正例 |
| D5/D6 | M 对 N 视觉鲁棒性 | 确定性 10/10，外参漂移/时间偏差保守拒绝，ID rewrite=0 | 在真实多视角 AirSim/相机同步和持续 detect 下复验，不以确定性 fixture 代替实测 |
| D3/D4/D5/D6/main | 学习数据全样本与运行证据 | canonical seed 60/20/20 和全样本审计已完成；D5 20-seed paired shadow 已完成但有合成可分性限制；D3/D4 5v5 写盘预演完成，真值使用为 0，候选分别为 20/20 OOD 回退和 20/20 threshold 回退 | 在干净 worktree 重跑 D3/D4 正式制品；D6 生成 availability/outcome sidecar；候选未实际采用时 outcome/counterfactual/causal 保持 unavailable；随后诊断训练分布和门限，再决定是否扩展多规模；PPO/assist/authority 保持关闭 |
| D6/main | 场景库与长期趋势 | cross-seed、paired effect、bootstrap、联盟 lifecycle 和证据路径已具备 | 固化 scenario version，生成长期 CI、失败漏斗和 active-degradation review 趋势 |
| D7 | 成员安全与独立到达 | role/wave/window、active/standby、commit-aware gate 和 N/M topology 已有 | 当前不要求同时到达；先验证独立 primary 的 terminal sector、minimum separation 和 member loss，协同到达时间后置 |

### 7.4 M 对 N 场景升级条件

required resource count \(k_j>1\) 的合同层升级条件已经满足，后续启用物理协同拦截前仍须满足以下运行级条件：

1. 保持 D3/D4 coalition id、成员、角色、版本、epoch、lease 和原子 ACK/commit 回归不退化。
2. 保持 D5/D6 planned cooperative lock、over-support、错误 duplicate 和 truth 隔离语义不退化。
3. 在真实 SimpleFlight 中验证 D7 simultaneous/sequential/hybrid 到达窗口、成员间距和退出策略，而不修改既有 PNG 核心公式。
4. 用更长真实 replay 验证 D1/D2 canonical registration、lineage 去重和 CI，不让 offline truth 回流在线总线。

### 7.5 统一验收命令

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
python3 -m pytest -q research_modules/d3_assignment_planner/tests
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
pytest -q research_modules/d5_terminal_association/tests
pytest -q research_modules/d6_evaluation_metrics/tests
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
git diff --check
```
