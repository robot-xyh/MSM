# D6 文档索引

2026-07-22 的 D1-D2 后验代次被动审计见 `MODULE_PRINCIPLES_CN.md` 和
`ALGORITHM_AND_IMPLEMENTATION.md`，接口验证见根目录 `../EXPERIMENT_REPORT.md` 2.21 节。
runtime v2 核对 D1 完整后验连续代次、D2 来源代次唯一递增、先发布后引用、最终 pending 排空、
consumed 等于 D1，以及消费数加合并数等于 D1；runtime v1 保持 unavailable。D1/D5 独立性能 JSON
只登记为描述性证据，不升级为全栈实时能力。专项 `58 passed`，D6 全量
`542 passed, 1 warning`。AirSim 接口未改变。

同日 main 已提供 clean commit `0d2da25` 的 nominal 200 对 200、10.0 s、三 seed runtime v2
episode。三次后验代次完整性、基础 formal provenance gate、pending 排空和在线真值隔离均通过，
失败原因空。输出见 `../outputs/scalable3d_posterior_v2_clean_0d2da25_20260722/`。该证据是三 seed
描述性 clean 校准；没有实验矩阵 metadata，也未达到 20 未见 seed。v6 报告日期已修正并重生成为
`2026-07-22`。

2026-07-22 nominal 200 对 200、10.0 s、seed `42000/42001/42002` 的 clean 长时集成校准见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和根目录 `../EXPERIMENT_REPORT.md`
2.20 节。reference 为 `8f86192`，candidate 为 `f80b5bd`。三 seed 的有限状态、在线真值隔离和跨提交
业务语义审计均通过；进程总墙钟均值下降 12.31%，峰值常驻内存下降 18.33%。candidate 写盘后处理
均值为 `40.639988 s`，但 reference 缺相同计时制品，不能做单阶段归因。该批仍是三 seed 描述性
clean-source calibration，不关闭 20 未见 seed、实时性、实验矩阵或物理拦截 P1。文档同步后 D6
全量回归为 `530 passed, 1 warning`；warning 为既有 Matplotlib `Axes3D` 环境问题。

2026-07-22 runtime plan outcome join 的严格等价性能优化见
`MODULE_PRINCIPLES_CN.md` 和 `ALGORITHM_AND_IMPLEMENTATION.md`，固定 3380 条 development A/B 结果见
`../EXPERIMENT_REPORT.md` 2.19 节。实现对全部在线记录继续执行真值键审计，只在审计后最小化留存，
并对 D2 identity 建立一次只读索引。baseline/candidate 报告、业务 JSON 和写盘摘要不变；独立入口
没有跳过真值检查的布尔参数。该结果不改变 AirSim 接线、admission 或物理证据层级。

`OBSERVATION_GOVERNANCE_CALIBRATION_CONTRACT_CN.md` 定义长 episode D1 扫描 OOSM、D2
claim ledger、evaluator-only sidecar、哈希链和 main required fields 的公共合同。
2026-07-22 clean/formal 快速治理结果见 `../EXPERIMENT_REPORT.md` 2.17 节。该批采用
`formal_only`，覆盖 20 episode/20 seed，绑定 clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b`，online truth use 为 0。正式证据只覆盖治理
合同，不包含精度、AirSim、实时性或物理拦截验收。
2026-07-22 的 development 快速治理基准与 200 对 200 全栈单 seed 冒烟见
`../EXPERIMENT_REPORT.md` 2.16 节；两类证据的隔离原则见 `MODULE_PRINCIPLES_CN.md`，读取和
availability 算法见 `ALGORITHM_AND_IMPLEMENTATION.md`。快速基准覆盖四档各 5 seed，全栈冒烟
仅覆盖 2.2 s 单 seed；两者均不能替代 clean formal 多 seed 精度与物理闭环验收。

2026-07-22 D2 重复航迹治理后的 `active_risk` 开发期复跑证据见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `../EXPERIMENT_REPORT.md` 2.14 节。
20 个 seed 的计划消费、导引血缘、物理窗、D4 adoption、配对差值、非退化和降级配对比较均为
20/20 可用；D4 区域采用合计 `188/188`，两臂各有 `1960` 条实际 world 命令，seed 1005 的 5 条
D2 航迹离线映射完整且 online truth use 为 0。该批为脏工作树 development rerun；两臂 5 m 成功均
为 0，production runtime ACK、counterfactual 和 causal 仍不可用，不替换下方此前 clean formal
19/20 历史证据。

2026-07-22 新增隔离双臂多周期物理评估合同。证据分层、真值隔离和结论边界见
`MODULE_PRINCIPLES_CN.md`；D3 计划消费、D7 world application、5 m 物理窗、差值和非退化算法见
`ALGORITHM_AND_IMPLEMENTATION.md`。同一合同现支持显式、可选且经 spec/manifest 双重 SHA-256 绑定的
D4 区域采用文件，区分 `not_declared`、名义 `not_applicable`、完整采用和部分区域不可用，并仅在全部
必要证据完整时输出描述性降级配对物理比较。已写入但未被 verdict 准入的 ACK 仍独立审计；其存在不
提升 adoption availability。接口验证见 `../EXPERIMENT_REPORT.md` 2.13 节；专项 `24 passed`、D6 全量
`507 passed`，main 20 seed producer 集成专项 `1 passed`。`active_risk` 20-seed 只读复跑已通过，但
D4 adoption/降级比较为 0/20 available，物理窗为 19/20。当前结果不能解释为正式降级收益、反事实或
因果结论。

2026-07-22 已将 D3/D4 保留 seed consumer 升级为 v1/v2 严格分派。历史 v1 保持兼容；新 v2 独立
复核 D3 safety-shell 40 arm、20/20 treatment application、同帧 assignment cost/safety/churn，以及
D4 arm-evidence-v2 的 confidence/OOD/latency/finite/failure 分门和 manifest 汇总。仅 offline
assignment comparison 可用；runtime ACK、physical outcome/effect、counterfactual 和 causal 仍为
null/unavailable。算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，边界见 `MODULE_PRINCIPLES_CN.md`，
结果见 `../EXPERIMENT_REPORT.md` 2.12 节。CLI profile 已绑定预期源 schema；测试内 v2 fixture 使
clean clone 仍覆盖成功与关键篡改路径。当前 canonical 使用独立 profile-bound v2 目录；固定时间戳
四文件可逐字节复生，sidecar/provenance 均记录 source schema。专项 `18 passed`、无权威输出路径
`16 passed`、D6 全量 `483 passed`。历史 v1 文件保留为旧 provenance，不把旧哈希写成当前可复生
哈希。已检查 `../AIRSIM_INTEGRATION_PLAN.md`；本次无 AirSim 接线变化，因此未修改。

2026-07-22 已完成 D5 paired-shadow 权威 v2 独立审计。D6 显式绑定 v2 report/lineage、held-out
corpus/evaluation、模型包、D5 实现源码和保留的 superseded 证据，复核 2718 项输入且审计前后哈希
一致。900 条 lineage、20 seed、45 cell、74024 条候选边、graph/candidate/label identity、逐 seed/cell
汇总和零安全违规均闭合。paired-shadow=`complete`，但三类运动/尺度特征近确定性可分，最强特征只在
35/45 cell 达到门限；外部泛化证据为 `synthetic_only_insufficient_for_external_generalization`。
G1/PPO/assist/authority 均为 false，规则回退保持 true。算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，
证据边界见 `MODULE_PRINCIPLES_CN.md`，实测结果见 `../EXPERIMENT_REPORT.md` 顶部。
专项测试 `8 passed`，D6 全量测试 `465 passed`；仅有既有 Matplotlib `Axes3D` 导入警告。

2026-07-21 已接入 D5 held-out report/corpus 的严格只读消费者。输入 v2 要求两项制品成对显式提供，
v1 只兼容无 held-out；D6 校验文件/内容 SHA、20 seed×45 cell×1 帧、model weights/config、冻结
validation 温度/阈值和身份/真值/权限零违规。指标通过只完成 held-out 层，paired shadow 仍独立阻断
G1/assist/authority。该段是权威 v2 生成前的接口状态，专项合成合同测试不代表正式结果；当前状态
以上一段独立审计为准。本次不修改 AirSim 接线。原理、实现和证据边界分别见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `../EXPERIMENT_REPORT.md` 2.9 节。

2026-07-21 已新增运行时计划确认到离线观测结果的严格联接。D6 显式校验 11 类输入及 SHA-256，复核
D3/D7 source sequence 与 payload SHA，只使用 D2 source-observation lineage 映射身份，并按同资源相邻
ACK 建立非重叠三维状态窗。有界配对进展仅作诊断，正式 reward、因果/反事实和三类学习权限保持
unavailable/false。合法同版本评估刷新按 ACK sequence/时间戳形成独立 occurrence；同版本执行签名
漂移失败关闭。专项 `22 passed`、D6 全量 `423 passed`；真实 main 3v3 回归形成 2 个 occurrence、6 个
绑定窗口。原理见 `MODULE_PRINCIPLES_CN.md`，实现见 `ALGORITHM_AND_IMPLEMENTATION.md`，接口证据见
`../EXPERIMENT_REPORT.md` 2.7 节。该改动不修改 AirSim 接线和冻结训练数据。

2026-07-21 已完成 D3、D4、D5 producer 全样本联合准入。D6 显式接收三份审计路径和带外文件 SHA-256，
独立复算 file/content SHA，核对 schema、完整计数、expected/actual binding、canonical 60/20/20、零
违规、availability 和 admission。三模块及跨模块 structural full-sample=`complete`，overall
admission=`partial`；PPO、assist、authority 均为 false，规则回退为 true。专项 `37 passed`，正式
输出及哈希见 `../EXPERIMENT_REPORT.md` 2.6 节。本次未修改 AirSim 接线。

2026-07-21 已接入 detached canonical numeric-seed split 只读审计。D6 独立校验共享 registry 的 schema、
policy、内容/assignment/source SHA-256、100 个训练 seed 和 `1000-1019` 保留 seed 隔离，并比较 D3、
D4、D5 图数据和 D5 主动视觉 manifest。正式结果为 D3 exact；D4、D5 graph、D5 active 分别有
51、65、62 个 mismatch seed，联合训练 unavailable。算法和空值口径见
`ALGORITHM_AND_IMPLEMENTATION.md`，治理原则见 `MODULE_PRINCIPLES_CN.md`，正式统计见
`../EXPERIMENT_REPORT.md`。2026-07-21 D6 全量 `364 passed`；本次不改变 AirSim 接线。

2026-07-20 已接入正式学习数据标签只读审计和 detached sidecar 合同。D4/D5 的 outcome、reward、
counterfactual、causal label 分层、运行确认硬门、保留 seed `1000-1019`、全量 SHA-256、原子发布和
确定性复用见 `MODULE_PRINCIPLES_CN.md` 与 `ALGORITHM_AND_IMPLEMENTATION.md`。正式 900 episode
审计确认 D4/D5 reward 均为 0 条可用，D5 runtime ACK 为 0；行为克隆只在模块内可准备，PPO 不可用。
D4/D5 split 有 423/900 个 episode 不一致，联合训练保持 unavailable。2026-07-21 标签专项
`17 passed`、D6 全量 `351 passed`；本轮未启动 AirSim，未修改 AirSim 计划或实验报告。

2026-07-20 已接入 scalable 3D 算法实验矩阵离线审计。D6 v5 从配置 metadata 读取
R0/G1/A1/A2/A3/C1/F1，核对 learning runtime 与实际采用证据，按固定 cell 分母和 variant 汇总，并在
完整 R0 配对上输出 delta/bootstrap CI。专项 `34 passed`、D6 全量 `314 passed`；clean/formal 与
dirty development 分开，正式矩阵尚未运行。
原理见 `MODULE_PRINCIPLES_CN.md`，实现见 `ALGORITHM_AND_IMPLEMENTATION.md`，接口验收见
`../EXPERIMENT_REPORT.md` 2.4 节。

2026-07-20 已同步 scalable 3D schema registry 窄修复。D6 offline v4 固定核对当前 world/bus/scenario/
online observation/offline truth 和 config schema；真实 online observation 名称为
`scalable3d-observation-v1`。原始值继续展示，旧、未知、篡改或缺失值不能进入 formal acceptance。
专项 `32 passed`、D6 全量 `304 passed`。原理见 `MODULE_PRINCIPLES_CN.md`，实现见
`ALGORITHM_AND_IMPLEMENTATION.md`，验证见 `../EXPERIMENT_REPORT.md` 2.3 节。

2026-07-20 已同步 scalable 3D 主动视觉离线 consumer v3。新增
`modules.d5.active_vision` 与 `runtime.camera_command_ack` 的规则/影子/辅助采用、issued/applied/
rejected、复合版本键关联、ACK latency、拒绝原因、D2 中心航迹只读引用和 truth-like 字段审计。缺
日志保持 null/unavailable；同 episode 的 assist applied 与五米接近不形成物理归因。主动视觉专项
8 项、合并 scalable 专项 `25 passed`、D6 全量 `297 passed`；上述 fixture 未启动 runtime/AirSim。
原理见 `MODULE_PRINCIPLES_CN.md`，字段与算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，测试证据见
`../EXPERIMENT_REPORT.md` 2.2 节。

同日另以当前 main runtime 运行 6v6/recon1/camera7、seed 37、2.2 s 临时 smoke。D6 读取 133 条规则
命令和 133 条 applied ACK，零拒绝、零中心航迹引用违规、零 truth 字段违规；summary 一致。该输入为
dirty 单 seed，只用于接线检查。

2026-07-20 已同步 scalable 3D 学习运行时离线 consumer v2。稳定入口仍是
`../scripts/run_scalable_3d_offline_evaluation.py`；新增 D3/D4/D5 bundle/fallback/fingerprint/version
availability 与 `modules.d4.region_resource_advice` 的 mode、assist、fallback、latency、quota 守恒、
projection、formal mutation 和 stale/missing version 审计。报告严格区分 bundle loaded、shadow
output、assist gate、control adoption 和 physical outcome；advice 不改变正式 D4 裁决，独立 main
消费合同和 D3 hint applied 才能证明控制采用。聚合按显式规模和不同 seed，单 seed 仅 descriptive；
正式 evidence 要求 `repository_dirty=false`。deterministic scalable 专项 `17 passed`、D6 全量
`289 passed`；未运行真实 scalable 3D/AirSim，也未形成模型验收。算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，原则见 `MODULE_PRINCIPLES_CN.md`，验证边界见
`../EXPERIMENT_REPORT.md` 顶部。

2026-07-15 已同步 legacy 1.0 provenance 兼容与真实三档报告。fallback 只在路径输入且 suite/cases/
rows 全无显式 ClockSpeed 时读取 20/20 sibling generated settings；不猜目录名、不默认 1.0，缺文件/
缺键/冲突/非法值 fail closed。真实 1.0/0.2/0.1 共 60 case、20 个跨档配对，合同 56 match/4
mismatch，truth identity/state 全 0；candidate 0.1/0.2 的受影响 aggregate unavailable。输出见
`../../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。ClockSpeed 专项 `18 passed`、D6
全量 `272 passed`，源组合 hash 前后不变。

2026-07-15 已同步 0.1 P1 NameError 紧急回归：timing mode helper 前置并统一命名；新增 20-case 双层
case-aware evaluator 测试。真实 0.1 两层各 4036 records/20 case 的 P1 v6 只读报告生成成功，输入
hash 不变。timing 专项 `28 passed`、D6 全量 `264 passed`。该段记录紧急修复当时状态；真实三档
comparator 随后已完成，见顶部同步项。

2026-07-15 已同步 case-aware merged suite timing 与真实 ClockSpeed=0.2 证据。P1 v6 显式区分
`single_episode/case_aware_suite`，后者只接受四个 case metadata、逐 case 单调并允许边界重置；两层
各 6567 records/20 case 的只读复测通过，禁止跨 case 伪连续和 main/control 相加。ClockSpeed
comparator v2 冻结 M5N2 每 case `3/2/1`，真实 0.2 审计为 18 match/2 mismatch（candidate seed006/
seed009）；reserve 成功不计 active-primary。该 0.2 阶段专项 `27/10 passed`、当时全量
`263 passed`。真实 0.1 P1 状态见顶部，不预写三档结论。

2026-07-15 已同步 M5N2 ClockSpeed=`1.0/0.2/0.1` 三档离线比较接口。每档强制
baseline/candidate 各 seed 1-10，并按 `case_id/profile/seed` 跨档配对；ClockSpeed 来自 suite/case
persisted provenance，不从目录名推断。报告覆盖三层物理结果、第二 primary、最终锁/共识、
collision stop、独立 wall timing、归一化 simulated time/tick 和 truth identity/state availability。
确定性 fixture 为三档各 20 case、总计 60 case，专项 `8 passed`、D6 全量 `254 passed`。
运行前接口记录已由本页顶部更新：真实 0.2/0.1 均已完成 P1 复核；算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，
接线见 `../AIRSIM_INTEGRATION_PLAN.md`，测试证据见 `../EXPERIMENT_REPORT.md` 1.7 节。

2026-07-15 已同步真实 AirSim M5N2 20-case 复核。baseline/candidate 各 10 seed；actual execution
为 `20/20` available，正式物理 pair/target/coalition=`12/60`、`12/40`、`0/20`，在线 truth
identity/state 均为 0。第二 primary 七阶段分母全部 available，但 5 m physical=`0/20`。两层
timing 各 3805 samples，main-bus/control-tick mean=`349.34/1069.45 ms`，禁止相加。partial
acceptance 的正式 timing 接线仍 unavailable。M5N2 完成后、`TERM` 生效前额外完成的 `png_ttc`
seed001 明确排除在 20-case 聚合与验收之外；其余 tuned 2v2 和全部 dropout 未执行，缺失 case 不补零。
`12/40` 固定表示“至少一个 participating pair 成功”的 canonical target physical success；全部
required member 通过阶段只称 cooperative target-stage diagnostic。第二 primary `20/20` 最终为
`collision_stop`，但 collision object 未写盘，原因对象保持 unavailable。
详细结果见 `../EXPERIMENT_REPORT.md`，接线缺口见 `../AIRSIM_INTEGRATION_PLAN.md`，算法和证据边界
见 `ALGORITHM_AND_IMPLEMENTATION.md` 与 `MODULE_PRINCIPLES_CN.md`。

2026-07-15 已同步 `d6-cooperative-closure-v3`：第二 primary 七阶段漏斗、pair/target/coalition 独立
物理分母、coalition completion 和首失败原因 availability 已写入模块原理、算法、AirSim 计划与
实验报告。确定性专项 `11 passed`、D6 全量 `246 passed`；该代码批次未启动 AirSim，后续 M5N2
20-case 结果以本页首段和实验报告 1.6 节为准。

2026-07-15 已同步两层分阶段延迟能力：模块原理说明嵌套域与 availability，算法文档说明严格
校验、P95、预算和 dominant stage；模块根目录 AirSim 计划与实验报告记录接入和测试证据。代码
可观测性已闭合；M5N2 20-case 已确认预算不达标，正式 case-aware 接线已关闭，优化复验仍为 P1。

2026-07-14 actual target-state freshness/stale 正式指标链已关闭：canonical v2 强制消费最终
command 的六个 freshness 字段，formal validator 从 SHA256 已验证 CSV 复算，case/pooled
aggregate/CSV/JSON/中文 Markdown 均已接入。最新真实 2v2/M5N2 为 48/608 samples，stale 均 0，
source 均为 `d2_estimated_global_track`；pooled 656 samples。D6 全量 `216 passed`。详细算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产约束见 `../AIRSIM_INTEGRATION_PLAN.md`，真实数值见
`../EXPERIMENT_REPORT.md`。随后 20-case 已补齐 10389 条同配置 freshness 样本；跨提交趋势和
failure taxonomy 仍为 P1。

2026-07-14 最新真实证据状态：tuned 2v2 seed-1 与 M5N2 seed-1 的 canonical
`d7-actual-execution-metrics-v2` 均可用，required/available/unavailable=`2/2/0`；旧
physical-count conflict 未复现并关闭。M5N2 pair/target/coalition=`2/3`、`2/2`、available
`0/1`，显式 coalition 失败不能由 target 成功替代。统一报告 overall=false 是因为 2 个 seed-1
case 不构成 baseline/candidate、1-5 帧 dropout 和 multi-seed 的完整 P1 矩阵。2v2/M5N2 loop
latency=`123.3/384.6 ms`，budget violations=`19/212`、合计 `231`，保持 P1。此次只同步文档，
未改 D6 代码。

2026-07-14 actual SimpleFlight execution evidence 已形成 v2 builder/writer、计划身份 provenance
和 fail-closed validator；plan/version 逐行必填，owner 只对 effective-authorized 的
secondary/distributed active/execution/reassignment 或显式 execute action 行必填。中心授权或
未授权 pending 可无 owner；整集没有 authoritative owner 时 provenance 为 `unavailable`。merge
v3 只发布 validated actual metadata，不从 replay 推断。接口见
模块 `README.md`，证据分层原理见 `MODULE_PRINCIPLES_CN.md`，字段来源和实现见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产顺序见根目录 `AIRSIM_INTEGRATION_PLAN.md`，最新
两组 M5N2 审计见根目录 `EXPERIMENT_REPORT.md`。此前 owner-provenance 专项为
execution-evidence focused `20 passed`、当时 D6 全量 `184 passed`；该代码级阶段没有运行真实
AirSim，随后完成的两条真实 seed-1 证据以本页首段为准。
代码级 P0 与本批 actual seed-1 写盘注册门均已关闭；完整 P1 矩阵和性能门仍开放。

本目录保存 D6 的详细设计和实现状态文档。D6 的长期边界是离线评估：只消费日志，不参与 D1-D7 控制链路。

2026-07-15 D2 准入 schema 兼容与正式证据均已同步：统一 system-evidence v2 支持 D2 v2 gates、
legacy structured/bool checks，并结构化保留 source promotion/path、逐 difficulty、truth alignment
和 JPDA research-only 状态。正式 D2-only bundle 位于
`../outputs/p1_identity_ceiling_aware_v2_20260715/`；其他六源 unavailable、全系统判决未评估。
实验文档记录专项 `31 passed`、D6 全量 `243 passed`；本批未启动 AirSim。

先前 case-wiring 状态（2026-07-14）：terminal suite `d6-p1-unified-acceptance-v2`、
`d6-terminal-metric-envelope-v1` 和逐 case evidence aggregation 已实现并通过 D6 全量
`159 passed`。现有 seed-1 suite 的 D3 为 4/4 case、543 records；D7 原 main row 路径仍全部
未注册并明确 fail-closed。公开 registration helper、逐 case/seed JSON/CSV/Markdown 和缺文件/
schema mismatch 回归已同步到下列文档；main runtime 的 D7 路径登记与正式 suite 重生成仍开放。

| 文档 | 位置 | 说明 |
|---|---|---|
| 模块 README | `../README.md` | 当前能力、规模归一化、AirSim/D4/D5/D7 离线入口、测试命令和 API 示例 |
| 模块计划 | `../PLAN.md` | 已实现、部分实现、未实现、main runtime 接线缺口、P1/P2 下一步 |
| AirSim 离线集成计划 | `../AIRSIM_INTEGRATION_PLAN.md` | Blocks JSONL、D4/D5/D7 AirSim 产物回灌、PNG 策略和未实现 replay 项 |
| 算法原理与当前实现 | `ALGORITHM_AND_IMPLEMENTATION.md` | 指标公式、数据模型、`EpisodeMetrics` 字段、D4/D5/D7 gate、开源 benchmark 缺口 |
| 示例实验报告 | `../EXPERIMENT_REPORT.md` | 批量示例报告和图表引用；不是代码或在线控制输出 |

核心规则：

- `id_switch_count` 是 D2/D6 强制显式指标。
- truth-to-track pair 缺失时 `track_rmse/track_continuity/id_switch_count` 为
  `None/unavailable`；完整 identity history 的零切换是 available `0`。JSON/CSV/Markdown、
  loader、merge 和 batch reporting 必须保留该区别。
- 2026-07-14 五场景 truth tracking 回归已关闭假零 P0，D6 全量 `137 passed`；真实
  seed/provenance 完整性和 D2 lifecycle-D3 churn join 仍为 P1。
- 指标按实际 `drone_count/resource_count/target_count/camera_count` 分组和归一化，不从 `2v2/5v5` 场景名推断。
- D7 guidance records 通过 `guidance_records.csv` / `guidance_summaries.json` loader 转为 `EventRecord` metadata；D6 只做离线 gate/intercept 统计，不提供在线导引控制通道。
- 2026-07-07 起，main/orchestrator 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 仍只消费这些写盘产物。
- 2026-07-08 起，main runtime P1 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 AirSim calibration records/summary/Markdown；报告字段覆盖 coverage、projection/gate、stable registration、`not_registered_count`、active degradation review label 和 D7 guidance reject reason。
- PNG 截图不是默认指标输入；bbox、相机参数、timestamp、ID 和 gate metadata 才是指标主线。
- py-motmetrics 已作为隔离式 P2 benchmark 输出 IDF1/MOTA/MOTP，HOTA unavailable；Stone Soup、OSPA/GOSPA、TrackEval、AirSim 原生 recording replay 和 SCRIMMAGE bridge 仍是未实现的可选项，live AirSim replay/API 仍是禁止在线控制项。

2026-07-20 新增 `../d6_evaluation_metrics/truth_isolated_offline.py`。该文件是三维规模化
D1/D2 公共离线制品入口，提供 DTO/哈希文件适配、episode/batch 记录和逐 seed CSV、聚合
JSON、中文 Markdown 输出。算法边界见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 17 节，原则
与证据边界见 `MODULE_PRINCIPLES_CN.md` 第 11 节，AirSim/main 写盘要求见
`../AIRSIM_INTEGRATION_PLAN.md` 第 11 节。文件模式强制校验制品 SHA-256 和 D2 四类来源
摘要，零帧/无 truth-frame 不得产生 available IDSW=0。D1 规范字段为
`d2_lineage_mapping`，旧 `canonical_mapping` 仅输入兼容且冲突 fail-closed。专项
`14 passed`、D6 全量 `334 passed`；本轮只验证合同和报告，不代表正式多 seed 性能达标。
