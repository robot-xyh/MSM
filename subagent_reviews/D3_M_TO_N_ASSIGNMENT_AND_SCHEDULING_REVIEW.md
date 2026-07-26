# D3 M 对 N 多资源联盟分配与时序调度调研

## 学习残差权限边界（2026-07-26）

M-to-N 需求槽可以在 shadow 中使用冻结学习残差做离线比较，但当前 production D3 不允许
学习残差进入 assist。复核证明原 v3 清单可由调用方填写正向布尔和占位 SHA 自我晋级；
writer 与 loader 现已同时失败关闭，完整手工清单返回
`bundle_assist_evidence_assembler_unavailable`。该修改不改变需求槽 Hungarian、
联盟 all-or-none、主备角色、迟滞和版本逻辑。

D6 已有跨模块数据审计和同帧 reserved-seed 审计，新 formal-scope auditor 也具备实际采用、
物理结果和同键 R0 非退化检查能力。当前没有实际 A1 审计输出，旧 sidecar 的 runtime ACK、
物理结果和 paired non-degradation 均不可用。D3 不另造通用审计 schema；后续只在 D6
实物覆盖 20 个未见 seed 后实现模块专用装配器并生成新 bundle。

## 滚动需求变化（2026-07-25）

正式 R0 证明 M-to-N 需求变化还必须治理旧联盟库存。clean commit `32b3b40` 的
200v200、seed 1000、2.0 秒场景中，一个无成员的 `k=1` incomplete coalition 在下一
规划周期升为完整 `k=3` 候选。其他目标的成员驻留触发全局迟滞，旧空 coalition 被一并
保留，最终形成运行异常。

当前 D3 在迟滞前比较旧/新需求合同。需求数量、主资源数量、协同模式、能力或时间模板
变化后，旧 coalition 不再具备保留资格，规划器采用当前求解器生成的新库存。该释放不允许
部分联盟执行，也不绕过容量、资源唯一性、计划版本、stale、主备角色和需求一致性门控。
同需求 coalition 的普通成员变化继续按收益和驻留期处理。

2026-07-25 同配置开发复验完成，`GT3D-000021` 在 `t=1.0` 重建为完整 `k=3`
coalition；最终 197 个 assignment 使用 197 个唯一资源，过分配和需求摘要失配为 0。
模块全量为 `464 passed, 1 skipped`。该结果尚未在新 clean commit 下形成 formal R0
制品，正式分片重跑仍由 main 负责。

## 身份承诺前置条件（2026-07-23）

M-to-N 需求不覆盖身份不确定性。目标只有在 D2 状态为 `committed` 时才展开可执行
primary/reserve 槽位。两类 uncommitted、缺失和未知状态对该目标全部资源边作硬拒绝，
需求摘要保持零满足和完整 shortfall，不生成可执行成员。

main 触发 hold/replan 后，若目标已在上一联盟中而当前为非 committed，D3 撤销整个目标的
成员绑定并严格升版。不能只撤销一个 primary，也不能让 reserve 继续执行。该合同已有
集中测试；它未改变 2 primary + 1 reserve 研究模板，也未加入同时到达要求。

2026-07-23 的 clean seed 1100、200v200、2.2 秒运行进一步验证了普通已绑定目标的系统级
撤回链路。两臂均在 `t=1.0` 将同一组 11 个原 v1 目标从 v2 完全删除，计划由 v1/193
严格升为 v2/186，且 D5/D7 对这些目标的后续执行为 0。本场景没有为这 11 个目标设置
M-to-N 联盟需求，因此它证明普通绑定和下游链路的运行时安全门已经接通，不能替代
2 primary + 1 reserve 的多 seed 联盟撤回专项。

本 episode 也没有主动注入 stale plan。旧版本拒绝仍由模块与 AirSim regression 覆盖。
两臂一致不代表 D1/D2 算法性能改善。AirSim 多 seed 联盟性能仍需单独验证。

**模块**: D3 集中式资源-目标分配

**调研日期**: 2026-07-11

**调研范围**: 以 2015-2026 年论文为主，并纳入少量 MRTA、CBBA 和同步车辆路径问题的奠基文献。

**边界**: 本文只讨论科研仿真中的抽象任务需求、联盟分配和到达时序，不涉及真实处置载荷、毁伤模型或绕过人工授权的自动决策。

## 1. 结论摘要

本调研开始时 D3 只支持**非等量规模下的一对一 optional assignment**：目标数和资源数可以不相等，但每个目标最多一个主资源。当时不能表达“高威胁目标需要 3 架无人机”的 `k_j=3` 联盟需求。这里的 M 对 N 不是简单的矩阵非方阵，而是任务基数、能力和时序都发生变化：

\[
\sum_i x_{ij}=k_j z_j,\qquad \sum_j x_{ij}\leq 1
\]

其中 `x_ij` 表示资源 `i` 是否加入目标 `j` 的联盟，`k_j` 是目标需求，`z_j` 表示该目标是否形成完整可执行联盟。若允许部分满足，应使用显式缺口变量并施加高惩罚，不能把“分到 1/3 架”误记为完成。

调研后的分级结论如下：

- **成熟默认方案**: 对只有基数需求、边成本可加、无强协同效应的中心化问题，优先使用 capacitated bipartite b-matching 或最小费用流。OR-Tools 和 NetworkX 提供成熟求解基础，但需要 MSM 自己构造 `k_j`、禁配边和未满足惩罚合同。
- **可插拔升级**: 有能力互补、任务启用、主备关系、同步窗口、波次和碰撞约束时，使用 CP-SAT/MILP；Pyomo/PuLP 是建模层，OR-Tools CP-SAT 是可选求解后端。它们适合离线或较低频滚动规划，不应未经预算测试替换 Hungarian 高频基线。
- **研究型方案**: one-to-many matching、联盟形成启发式、通信感知分布式联盟和时空逻辑联合规划有明确论文依据，但没有一个成熟开源库能直接满足 MSM 的版本化计划、D4 接管、D5 视觉反馈和 D7 到达时序全部合同。
- **当前实施口径**: 保持**混合 2+1** 的资源角色，但本阶段两个 primary 独立授权、独立统计 5 m 结果，不要求同时到达；第三架仍为 standby reserve。同步到达只保留为后续研究对照。
- **调研时项目状态**: Hungarian、版本、迟滞和 D7 单资源 binding 已实现；`target_demand=k_j`、联盟原子激活、波次、同步到达窗口、联盟版本变更和合法多资源锁定语义均未实现。本段保留调研起点，实施更新见下节。

### 1.1 2026-07-11 实施更新

本轮已实现 `AssignmentPlan schema v2`、显式 `TargetDemand`、`CoalitionPlan/member/summary`、`hungarian_demand_slots`、能力槽、威胁优先与全有或全无 admission、四种 coordination mode、coalition version/stable signature、coalition-aware duplicate 和 D7 multi-binding。缺省仍是 `k=1 independent primary=1`；只有显式 `TargetDemand()` 才启用高威胁默认 `k=3 hybrid primary=2`。hybrid primary 数由 `primary_resource_count` 显式配置，可接收 main `--cooperative-primary-count`。资源或能力不足时只记录 incomplete/shortfall，不发布 executable assignment。

下一阶段 identity 语义也已实现：execution signature 覆盖 coalition member/role/wave/window 以及 owner/activation；同签名刷新保持 plan identity，成员或 coalition 执行字段变化只递增一次。未发布候选不推进 stale latest，forced replan 可区分 `replan_ack_no_change` 与 `replan_applied`。

OR-Tools Min-Cost Flow 已接入 optional 容量 benchmark：同一 4-resource/3-target、5-slot hybrid primary+reserve 输入由 SciPy 容量列展开和 flow 原生容量共享，缺 OR-Tools 时结构化输出 unavailable reason；它不进入默认依赖或 planner 主线。当前增量规划、role-aware primary 保持和跨模块 P1 合同验证已完成：ComputerVision 10 seeds 中 T001 双 primary 视觉共识与当前计划授权为 8/10，二级/分布式 commit 正例及缺 ACK fail-closed 通过。15 s SimpleFlight 仍无物理命中，物理闭环开放；installed flow 实证、CP-SAT/MILP 和复杂 flow 仅保留为 P2 隔离 benchmark。

2026-07-12 进一步补齐 D3 可复用校准支撑：versioned 8-scenario matrix 覆盖 3v5、5v3、目标新增、资源失效、高威胁需求切换为 `2 primary + 1 reserve`、D5 reserve hold 和 hard-window。paired full/incremental runner 的 8/8 转换 assignment/cost 等价；D5 场景保持两个健康 primary，只生成 reserve 替换 candidate，并统一导出 latency、churn、unassigned high-threat 和 coalition shortfall。2026-07-14 分级修复后，soft reserve candidate 仍需 `min_dwell`/成员迟滞放行，不再借资源 `operator_hold` 绕过迟滞。该结果关闭 deterministic 支撑缺口，不替代真实 AirSim 多 seed 或协同物理验收。

本轮复核进一步统一逐 pair 输出：D6 record 与 D7 binding 均携带 plan owner/version、coalition id/version/epoch、member role、wave、activation、validity、per-primary 授权资格、churn/rollback/stale reject。两个 primary 独立授权，不要求同时到达；reserve 仅占用计划容量并保持 standby/hold。该补充是诊断合同，不修改 Hungarian、迟滞、成员选择或 PNG 控制。

2026-07-14 D3 又补齐单 planning-tick canonical history schema/export：`plan_history_record_from_plan(...)` 生成 `d3_plan_history_record_v1`，按 main 提供的 `[sequence_index, timestamp]` 排序，集中记录 owner/epoch/lease、ordered primary/reserve assignments、可恢复 coalition members、迟滞/成员变化、soft/hard feedback、成本和 stale/rollback/replan reason，`to_dict()` 严格 JSON 且排除 truth 字段。它不改变 Hungarian、all-or-none、reserve standby 或 `global_track_id` 合同。历史 40-case 没有逐 tick history；2026-07-15 最新 20-case 已由 main 写盘并可计算实际 churn，因此两批证据必须分开。pair hold 扩大仍只是旧批次根因线索，不是已证明物理因果。

## 2. 问题模型与算法边界

### 2.1 基数、能力和任务启用

仅要求三架同类资源参与时，可使用：

\[
\sum_i x_{ij}=k_j z_j
\]

如果不同资源具备不同能力 `a_ic`，而目标要求能力向量 `r_jc`，则需要：

\[
\sum_i a_{ic}x_{ij}\geq r_{jc}z_j,\quad \forall c
\]

`z_j` 很重要。普通 min-cost flow 可以强制所有需求都满足，也可以允许流量不足，但很难直接表达“要么完整组成 3 机联盟，要么不激活并记录缺口”的固定启用成本；这类逻辑更适合 CP-SAT/MILP。若所有高威胁目标均必须满足且资源总量充足，则最小费用流可以通过 target-to-sink 的需求/容量变换表达精确 `k_j`。

### 2.2 三种时序策略

| 策略 | 数学表达 | 适用条件 | 主要风险 |
|---|---|---|---|
| 同时到达 | 联盟公共时刻 `T_j`，`|t_ij-T_j|<=epsilon_j`，或 `max(t_ij)-min(t_ij)<=Delta_j` | 需要同步观测、几何包围、同时占位；时间同步和轨迹预测可靠 | 规划更难；成员延迟拖累整个联盟；近距冲突和相机遮挡风险高 |
| 分批到达 | 波次变量 `y_ijw`，每波需求 `k_jw`，`T_j,w+1 >= T_jw + gap_jw` | 每次尝试结果可观测；资源紧张；希望保留补位能力 | 首波失败后可能错过窗口；反馈延迟会使后续波次过时 |
| 混合主备 | 主联盟满足同步窗口，后备资源有 release/commit 条件 | 高威胁但不确定是否需要全部资源；需要兼顾同步和容错 | 必须定义后备何时转 active，避免同一资源被其他目标占用 |

任务“同时分配”不等于“同时到达”。D3 决定联盟成员、角色和目标时间窗，D7 才负责具体 cooperative guidance 或 impact-time control。没有 D7 可达时间反馈时，D3 只能生成名义窗口，不能宣称同步到达已实现。

### 2.3 算法适用边界

| 算法 | 能表达 `k_j` | 能力/协同效应 | 同步/波次 | 滚动重分配 | D3 结论 |
|---|---:|---:|---:|---:|---|
| 复制目标槽位 + Hungarian | 是，但仅固定基数 | 弱；难保证联盟原子激活 | 否 | 可沿用现有迟滞 | 只适合快速 baseline；资源不足时容易产生部分联盟语义 |
| 二部图 b-matching | 是 | 适合可加边成本和度约束 | 否 | 可重解 | 基数需求的成熟数学基线 |
| Min-Cost Flow | 是 | 支持容量、禁配、需求和可加成本 | 可用时间展开扩展 | 适合中等规模滚动 | D3 首选升级路线，但 optional target 和联盟启用需额外建模 |
| Generalized Assignment | 通常是一任务给一资源 | 支持资源容量 | 弱 | 可重解 | 标准 GAP 不是多资源共同完成单任务，不能直接等同联盟分配 |
| CP-SAT/MILP | 是 | 强，支持角色、能力、启用和逻辑约束 | 强 | 可做滚动窗口和冻结前缀 | 复杂约束参考模型；必须约束求解时间 |
| Coalition Formation | 是 | 强，可建模组合效用和互补能力 | 取决于具体方法 | 动态场景需重组机制 | NP-hard，算法和开源实现尚未形成统一工程默认 |
| Time-Expanded Network | 是 | 通过节点/弧表达占用和转移 | 强，天然表达时隙与波次 | 适合有限滚动窗口 | 状态规模随时间离散粒度快速增长 |

## 3. 主要论文证据

以下 12 篇为本轮主证据。论文页面和 DOI 为最终引用来源；OpenAlex 用于元数据核验。Google Scholar 只作为发现渠道，本轮没有把搜索摘要当作证据。当前环境没有 WOS 订阅或用户导出数据，因此未声称完成 WOS 引文网络核验。

| 年份 | 论文与来源 | 问题/方法 | 中心性与时序 | 验证方式 | 对 D3 的意义 |
|---:|---|---|---|---|---|
| 2019 | Dutta, Asaithambi, *One-to-many bipartite matching based coalition formation for MRTA*, ICRA, [DOI](https://doi.org/10.1109/ICRA.2019.8793855) | 将多个机器人匹配到单任务的 NP-hard 联盟问题建成 OTMaM，使用 mutually-best pair 启发式 | 中心化；未提供同步到达模型 | 仿真；论文报告 100 robots/10 tasks 小于 1 ms | 直接证明经典一对一 matching 不够；提供 one-to-many 快速研究基线 |
| 2017 | Guerrero et al., *Multi-Robot Coalitions Formation with Deadlines*, PLOS ONE, [DOI](https://doi.org/10.1371/journal.pone.0170659) | 联盟、deadline、物理干扰；给出可由整数线性规划求最优的条件 | 中心化 ILP 与启发式；deadline/干扰 | 最优 ILP 与拍卖/新启发式比较；中位性能超过最优值的 80% | 同时到达不能忽略成员间物理干扰；MILP 可作为小规模参考真值 |
| 2021 | Maždin, Rinner, *Distributed and Communication-Aware Coalition Formation and Task Assignment*, IEEE Access, [DOI](https://doi.org/10.1109/ACCESS.2021.3061149) | 分布式联盟与任务分配，比较事件、周期和混合通信 | 分布式；关注通信故障和一致性 | ns-3 仿真，与中心化方法和不同网络条件比较 | 为 D4 接管后的联盟一致性提供边界；D3 中心模型不能直接替代该协议 |
| 2022 | Aziz et al., *Task Allocation Using a Team of Robots*, Current Robotics Reports, [DOI](https://doi.org/10.1007/s43154-022-00087-4) | 机器人团队/联盟任务分配综述，统一状态、约束、目标和动态信息 | 同时覆盖中心与分布式 | 综述 | 支持把 `k_j`、可行性、目标函数和动态信息分开建模 |
| 2025 | Arjun et al., *Optimizing Coalition Formation Strategies for Scalable MRTA*, Robotics, [DOI](https://doi.org/10.3390/robotics14070093) | 动态任务和 coalition formation 方法综述，强调 NP-hard 与可扩展性 | 中心/分布式方法综述 | 比较分析和仿真 | 说明联盟形成尚无单一默认算法，不能把某个启发式称为工程共识 |
| 2018 | Schillinger et al., *Simultaneous Task Allocation and Planning for Temporal Logic Goals*, IJRR, [DOI](https://doi.org/10.1177/0278364918774135) | 在资源约束下同时进行任务分配和执行规划，使用时序逻辑/自动机分解 | 中心化联合规划；表达顺序约束 | 办公环境多机器人实验与 case study | 证明复杂时序下分配与路径成本不能完全分离；但其任务模型不等同拦截联盟 |
| 2016 | Nunes et al., *A taxonomy for task allocation problems with temporal and ordering constraints*, RAS, [DOI](https://doi.org/10.1016/j.robot.2016.10.008) | 时间窗、顺序和任务依赖分类 | 综述 | 分类与文献分析 | 为同步、波次、precedence 和 committed prefix 的合同命名提供依据 |
| 2018 | Gombolay et al., *Fast Scheduling of Robot Teams Performing Tasks With Temporospatial Constraints*, IEEE TRO, [DOI](https://doi.org/10.1109/TRO.2018.2795034) | Tercio：快速满足型 sequencer + MILP，处理紧耦合时空约束和扰动 | 中心化调度 | 近优调度仿真和多机器人硬件 testbed | 支持用 MILP 作为复杂约束参考，并在滚动时保留快速近似路径 |
| 2022 | Bai et al., *Group-Based Distributed Auction Algorithms for MRTA*, IEEE TASE, [DOI](https://doi.org/10.1109/TASE.2022.3175040) | 动态任务、容量和时间窗；先构造可行任务组再分布式拍卖 | 分布式；时间窗 | 仿真，与 Gurobi ILP、贪心和启发式比较 | 说明“先生成可行组/联盟，再分配组”可降低组合复杂度；问题方向与多资源单目标相反，需谨慎迁移 |
| 2015 | Zhao et al., *A Heuristic Distributed Task Allocation Method for Multivehicle Multitask Problems*, IEEE TCYB, [DOI](https://doi.org/10.1109/TCYB.2015.2418052) | 局部任务加入、共识和移除的分布式启发式 | 分布式 | 搜救数值仿真，与 CBBA 比较 | 可作为 D4 分布式滚动任务基线，不直接提供 `k_j` 联盟原子性 |
| 2009 | Choi et al., *Consensus-Based Decentralized Auctions for Robust Task Allocation*, IEEE TRO, [DOI](https://doi.org/10.1109/TRO.2009.2022423) | CBAA/CBBA，局部通信下冲突消解并给出收敛和最坏性能界 | 分布式；任务 bundle | 数值实验 | 奠基基线；经典 CBBA 的 multi-assignment 不等于一个任务必须由多机器人共同完成 |
| 2012 | Drexl, *Synchronization in Vehicle Routing*, Transportation Science, [DOI](https://doi.org/10.1287/trsc.1110.0400) | 空间、时间和载荷同步约束的 VRP 分类 | 中心优化综述；同步 | 综述 | 为同时到达、共同地点和负载/角色同步提供成熟运筹建模语言 |

补充综述证据：Chakraa et al. 2023 对 MRTA 优化方法进行了系统回顾，[DOI](https://doi.org/10.1016/j.robot.2023.104492)。该综述支持“matching/flow 是结构简单问题的基线，复杂约束进入整数规划和启发式”的分层，但不提供可直接接入 MSM 的实现。

### 3.1 论文对应代码可得性

| 论文组 | 本轮核验到的代码 | 许可证/维护判断 |
|---|---|---|
| OTMaM 2019 | 对标题、作者和算法名进行了 GitHub 检索，未找到作者官方对应仓库 | 不得标记为成熟开源实现；若复现应依据论文重新实现并单独测试 |
| Guerrero 2017、Maždin 2021、Gombolay 2018、Bai 2022、Zhao 2015 | 论文提供算法和实验依据，本轮未核验到可直接复用的作者官方仓库 | 只作为数学模型/实验设计证据，不把第三方零散实现当生产依赖 |
| Schillinger 2018 | [Hierarchical-LTL-STAP](https://github.com/XushengLuo92/Hierarchical-LTL-STAP) 是后续相关研究代码，README 明确场景受该论文启发，并非原论文的 drop-in 实现 | 仓库未发现明确许可证；只能作为研究对照 |
| Choi 2009 CBBA | 存在多个公共衍生实现，但中心化 D3 不选定其生产上游 | 分布式实现和许可证审计由 D4 负责；经典 CBBA 也不自动满足 `k_j` 联盟原子性 |
| Nunes 2016、Aziz 2022、Arjun 2025、Drexl 2012、Chakraa 2023 | 综述/分类论文，不以参考实现为主要贡献 | 用于术语、问题分类和算法成熟度，不宣称存在对应代码 |

## 4. 开源代码审计

### 4.1 成熟优化工具

| 项目 | 用途与许可证 | 维护/测试状态 | `k_j` 与时序适用性 | MSM 适配难点 |
|---|---|---|---|---|
| [google/or-tools](https://github.com/google/or-tools) | `SimpleMinCostFlow`、CP-SAT；Apache-2.0 | 大型官方项目，2026-07-10 仍有提交，包含多语言测试和官方示例 | flow 可表达容量/供需；CP-SAT 可表达联盟启用、能力、同步、波次 | flow 成本需整数化；下界/optional coalition 要做网络变换或转 CP-SAT；需保持现有 plan/version/evidence 合同 |
| [networkx/networkx](https://github.com/networkx/networkx) | `min_cost_flow` / network simplex；BSD-3-Clause | 2026-07-10 仍活跃，成熟测试体系 | 适合 Python 原型和带 node demand/edge capacity 的小中规模 flow | 性能和数值边界不宜直接作为高频大规模生产后端；同样不原生解决联盟原子启用 |
| [Pyomo/pyomo](https://github.com/Pyomo/pyomo) | Python 代数建模；BSD-3-Clause | 2026-07-10 仍活跃，成熟测试；需外部求解器 | 最适合写 `x_ij/z_j/y_ijw`、能力、同步和滚动窗口参考 MILP | 求解器安装、许可证和时间预算另行管理；不是独立求解器 |
| [coin-or/pulp](https://github.com/coin-or/pulp) | LP/MILP Python 建模；MIT | 2026-06-19 仍有提交，文档和测试存在 | 小规模参考模型、CBC 基线 | 表达方便但性能取决于后端；需单独处理超时、不可行和 incumbent |

### 4.2 MRTA/联盟研究仓库

| 项目 | 许可证/活动 | 实际覆盖 | 结论 |
|---|---|---|---|
| [nubot-nudt/dynamic_task_allocation](https://github.com/nubot-nudt/dynamic_task_allocation) | BSD-2-Clause；最后核心推送 2024-07；ROS Kinetic/Melodic、Gazebo | auction、vacancy chain、DQN；探索/处置任务和分布式通信仿真 | 可参考动态分配事件和 ROS 仿真，但依赖老旧且没有 MSM `k_j`、同步到达、版本/迟滞合同 |
| [marmotlab/HeteroMRTA](https://github.com/marmotlab/HeteroMRTA) | Apache-2.0；代码发布 2025-01 | RAL 2024 的异构 MRTA+调度强化学习；README 明确为 ST-MR | 可做研究对照，但不是 multi-robot-per-task 联盟实现，不能直接解决 `k_j=3` |
| [labimage/Multi-robot-Task-Allocation](https://github.com/labimage/Multi-robot-Task-Allocation) | 未发现明确许可证；最后推送 2019-07 | 异构两类团队、复杂 schedule，含 MILP/GA/heuristic 和 Gantt 展示 | 有时序建模参考价值；许可证和维护状态不满足直接复用要求 |
| [XushengLuo92/Hierarchical-LTL-STAP](https://github.com/XushengLuo92/Hierarchical-LTL-STAP) | 未发现仓库级明确许可证；2025-05 仍有代码 | 6 机器人层次时序逻辑、联合 task allocation/planning | 适合复杂时序研究对照；依赖 LTL2BA，任务语义和计算路径远重于 D3 高频分配 |
| [adamslab-ub/CapAM-MRTA](https://github.com/adamslab-ub/CapAM-MRTA) | MIT；最后推送 2023-07 | README 明确 SR-ST MRTA，基于 attention/RL | 可做一对一学习基线，不支持一目标多资源联盟 |
| [biorobotics/MRTA](https://github.com/biorobotics/MRTA) | 未发现明确许可证；最后推送 2021-11 | WAFR 2022 多智能体任务分配研究代码 | 维护和许可证不足，且无证据表明覆盖 `k_j` 联盟与同步波次，不建议直接集成 |

对 2019 ICRA OTMaM 论文进行了论文标题和关键词 GitHub 检索，本轮未找到作者官方、许可证明确且可复现的对应仓库。因此 OTMaM 应标记为“论文算法可重现研究方案”，不能标成成熟开源实现。

## 5. D3 推荐研究架构

### 5.1 第一层：基数需求 baseline

保留当前 Hungarian 作为 `k_j=1` 默认。对 `k_j>1` 增加同输入对照研究时，首选 flow/b-matching 表达：

```text
source -> resource_i            capacity=1
resource_i -> target_j          capacity=1, cost=C_ij
target_j -> sink                lower=upper=k_j  # 通过 node supply/demand 变换实现
```

必须同时报告 `demand_required`、`demand_assigned`、`demand_shortfall` 和 `coalition_complete`。资源不足时不能用三个独立 assignment 记录掩盖未完成联盟。

### 5.2 第二层：联盟原子性和能力约束

采用 CP-SAT/MILP 参考模型：

- `z_j=1` 才允许完整激活目标联盟。
- `sum_i x_ij=k_j z_j`，并满足能力需求。
- 对高威胁目标未激活或 demand shortfall 施加可解释惩罚。
- 主资源、协同资源和 reserve 使用显式 role，而不是通过数组顺序推断。
- 联盟成员变更必须生成新 plan version，旧成员 binding 进入 stale/revoked。

### 5.3 第三层：到达时序和滚动规划

将每个目标的策略声明为 `simultaneous`、`sequential` 或 `hybrid`：

- simultaneous：公共终端窗口和最大到达离散度。
- sequential：波次索引、每波 quota、最小/最大间隔和反馈等待条件。
- hybrid：主联盟 committed，reserve 在 release deadline 前保留能力。
- 滚动重规划冻结即将执行的 committed prefix，只调整未承诺波次；联盟变化同时受现有 `delta/min_dwell/switch penalty` 和任务完整性约束。

time-expanded network 只用于窗口离散后规模可控的对照。若时间粒度过细，应改用 CP-SAT interval/整数时间变量，避免图规模爆炸。

### 5.4 默认策略选择规则

高威胁 `k_j=3` 的初始研究默认采用 `hybrid 2+1`：

1. 两架 primary 在容差窗口内到达，形成几何分离并避免同航线冲突。
2. 第三架 reserve 保持任务绑定但不立即进入同一终端点。
3. D5/D2/D1 证据确认首波完成或目标状态改变后，D3 释放、换配或激活 reserve。
4. 只有任务模型明确要求三点同步几何，且 D7 提供可达时间、通信/时钟满足门限时，才升级为 `simultaneous 3`。
5. 若每次尝试相互独立且结果可及时观测，则使用 `sequential 1+1+1` 或 `2+1`，避免一次占用全部资源。

这只是后续仿真的默认假设，不是行业已经达成共识的唯一方案。

## 6. 协同定位与跨模块边界

多个无人机可以协同定位同一目标，但 D3 不执行定位。D3 只负责分配“哪些资源在什么时段提供观测/拦截角色”，并消费 D1/D2 输出的不确定度和 D5 多视角证据。

协同定位成立至少需要：

- 每个平台位姿和相机/传感器外参已知，并使用同一 NED 工作坐标系。
- 保留 measurement/arrival timestamp，并把时钟偏差和通信延迟进入协方差。
- 多站观测具有非退化几何基线；近共线 bearing-only 观测不能产生虚假高精度。
- 处理公共先验导致的相关性，避免重复融合；该问题由 D1/D2 选择集中融合、track-to-track fusion 或 covariance intersection。
- D5 只能把多个视角证据关联到中心维护的同一 `global_track_id`，不能创建本地新绑定。

D3 后续只需要在代价中消费 `cooperative_localization_gain`、预期几何质量和通信成本，并把“协同观测角色”与“终端拦截角色”分开。详细算法属于 D1、D2 和 D5 调研范围。

## 7. 对现有合同的影响与 GAP 结论

当前合同中以下部分可以保留：

- `AssignmentPlan.plan_id/version/window_id`、stale 拒绝和迟滞。
- 动态 `resource_count/target_count`，不写死 2v2/5v5。
- 可解释 cost breakdown、D5 feedback writeback 和 D7 current binding gate。
- `global_track_id` 继续由中心/D2 维护。

本轮已定义并实现的合同包括：

- 目标侧：`required_resource_count=k_j`、能力需求、任务策略、同步容差、波次和优先级。
- 联盟侧：`coalition_id/version/state`、成员与角色、demand satisfaction、共同窗口、reserve/commit/release 状态。
- 计划侧：不能再假设一个 target 只有一个 assignment；合法 `k_j>1` 不计入 `duplicate_assignment_count`。
- D7 binding：同一 `global_track_id` 可有多个合法 resource binding，但每个都必须携带同一 current coalition/plan identity 和独立 role/wave。
- D6/D3 export：D3 已区分合法 coalition multiplicity 与异常重复分配并记录 demand satisfaction；到达离散度、波次完成和联盟重组次数继续作为 D6 长期参数校准指标，不是未实现的 D3 P1 合同。

该能力现为 **P1 contract done**。现有 Hungarian 不退化，仍是无显式 demand 的 `k_j=1` 默认基线；`hungarian_demand_slots` 是显式 demand 主线。`plan_incremental` 已能对独立连通分量保持 coalition all-or-none，并在需求/容量/版本或全局约束变化时保守回退。历史第一次真实复验暴露 soft reserve hold 会顺带旋转 healthy primary；D3 现从 previous plan 推导 member role，在同版本 healthy primaries + soft reserve failure 时固定旧 primary slots，只重解 reserve candidate，并继续执行成员/全局迟滞。普通 pair hold 也不再扩大为 resource-hard。deterministic 8-scenario paired runner 已关闭非等量/动态事件的本地复用与汇总缺口。当前 ComputerVision 10 seeds 中 T001 双 primary 视觉共识与当前计划授权为 8/10，且二级/分布式 commit 正例和缺 ACK fail-closed 通过；真实多 seed 参数与协同物理闭环仍开放，CP-SAT/MILP 和复杂 flow 只作为 P2 隔离 benchmark。

## 8. 参考链接

### 论文

- <https://doi.org/10.1109/ICRA.2019.8793855>
- <https://doi.org/10.1371/journal.pone.0170659>
- <https://doi.org/10.1109/ACCESS.2021.3061149>
- <https://doi.org/10.1007/s43154-022-00087-4>
- <https://doi.org/10.3390/robotics14070093>
- <https://doi.org/10.1177/0278364918774135>
- <https://doi.org/10.1016/j.robot.2016.10.008>
- <https://doi.org/10.1109/TRO.2018.2795034>
- <https://doi.org/10.1109/TASE.2022.3175040>
- <https://doi.org/10.1109/TCYB.2015.2418052>
- <https://doi.org/10.1109/TRO.2009.2022423>
- <https://doi.org/10.1287/trsc.1110.0400>
- <https://doi.org/10.1016/j.robot.2023.104492>

### 官方代码与文档

- OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/mincostflow>
- OR-Tools repository: <https://github.com/google/or-tools>
- NetworkX Min Cost Flow: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.flow.min_cost_flow.html>
- Pyomo: <https://github.com/Pyomo/pyomo>
- PuLP: <https://github.com/coin-or/pulp>
- Dynamic Task Allocation: <https://github.com/nubot-nudt/dynamic_task_allocation>
- HeteroMRTA: <https://github.com/marmotlab/HeteroMRTA>
- Hierarchical-LTL-STAP: <https://github.com/XushengLuo92/Hierarchical-LTL-STAP>

## 15. M-to-N Hold Scope 补充结论（2026-07-14）

真实 M5N2 seed 001 暴露的版本问题不在 demand-slot 求解本身，而在 hold 输出范围：
候选新目标被写入上一 current plan 的 unassigned scope，导致联盟成员虽被 hold，计划
身份仍推进。D3 已使 coalition membership hold 保留上一完整 execution signature，
并把新目标放入 pending candidate 审计。`2 primary + 1 reserve` 的原子需求和
reserve standby 合同未改变。

本次日志还说明，M-to-N 不能假定目标集合固定。D2 晚到航迹会动态改变 M，D3 必须
先接收明确 lifecycle admission，再进行 demand-slot 求解；不能按物理场景已知目标数
截断，也不能用 AirSim truth 判断 T008。当前 D3 侧回归通过，但 main/D2 仍需把
tentative/confirmed 与 engageable 的准入语义明确传入，main runtime 仍需在成员从
primary 变为 reserve 时撤销旧 active pair。

## 16. M-to-N 同窗口成员抖动治理补充（2026-07-14）

最新 M5N2 seed 1 的 347 条记录和 v1..v35 表明，需求槽本身能够形成完整
`2 primary + 1 reserve`，但 search-only feedback/slot 成本若与 previous base cost
混比，会让完整联盟在成员集合之间周期性旋转。D3 现将两种 objective 分离：

- demand-slot Hungarian 继续使用 switch penalty、soft feedback、slot priority 和
  role pin 找候选；
- coalition membership 与全局 `delta` 同时使用
  `d3_hysteresis_current_objective_v1`，按当前 base edge、hard feasibility 和
  demand/unassigned 统一重评 candidate/previous；
- `d3_cumulative_window_change_budget_v1` 在同 `window_id` 累计已接受成员变更，
  hold/refresh 不消耗，新 window 恢复；
- missing execution target 的 lifecycle release 优先于另一联盟的 membership hold，
  previous-only target 不进入新 coalition 或 membership audit。

该修复不改变 `k_j`、primary 数、reserve standby、coalition all-or-none、动态 M/N、
版本或 `global_track_id` 所有权。2026-07-14 D3 全量为 `157 passed, 1 skipped`；
新增确定性测试零失败，未重跑 AirSim。真实多 seed 物理结果和 main/runtime role
demotion 仍是跨模块 P1，CP-SAT/MILP/复杂 flow 仍为 P2 optional。

## 17. 最新 M5N2 20-Case 对 M-to-N 合同的验证（2026-07-15）

最新批次固定为 5 resources/2 targets，但仍由输入 `TargetDemand` 生成槽位：T001 为
2 primary + 1 reserve，T002 为 1 primary。20 个 case、3725 个 planning tick 全部
保持该结构，并且每个 case 的 plan/version、owner 和成员 roster 都没有发生实际转换。
这证明当前 demand-slot + 两层迟滞能在该静态几何批次稳定维持联盟，但不证明动态
3v5/5v3 或资源失效场景已经闭合。

`3555` 条 membership records 是对候选换员的审计：`3524` 条记录成员保持，`31` 条
成员收益/驻留条件通过后又被全局迟滞保持。M-to-N 报告必须把“candidate membership
evaluation count”和“actual coalition roster churn”分开，后者本批为 0。

20 个 case 中有 1 个 candidate seed 使用 `INT-01/INT-02` 作为 T001 primary，其他
19 个使用 `INT-02/INT-03`。因此联盟语义必须依赖 plan identity、target、role 和 wave，
不得把第二 primary 固定成某一资源。

物理 aggregate 为 pair 12/60、canonical target 12/40、coalition 0/20，第二 primary
0/20，说明稳定联盟计划仍未转化为 required-primary 物理完成。`canonical target
success` 是目标级统计，`cooperative target diagnosis` 才是 T001 两 primary/coalition
诊断，二者不得混用。20 个第二 primary 的 `collision_stop` 缺碰撞对象，candidate
paired non-degradation 失败也不构成 D3 demand-slot 退化证据。

额外完成的 `png_ttc_2v2_seed001` 排除在 M5N2 20-case 之外；全部 dropout case 未
执行。未执行结果保持 `unavailable`，不补零。

## 18. Scalable-3D 稀疏候选对 M-to-N 的影响（2026-07-20）

稀疏化在目标需求槽展开之前执行，但每目标候选数使用
`max(configured_top_k, required_resource_count)`，因此配置 top-2 时显式 k=3 高威胁
目标仍至少保留 3 条可行边。上一 current coalition 中仍可行的成员也额外保留，避免
top-k 排名轻微变化直接制造联盟 hard infeasible。

新增的 2-target/5-resource 确定性 case 保持 high-threat `2 primary + 1 reserve`，
最终仍由 `hungarian_demand_slots` 完成 all-or-none admission；学习策略只对原始
target-resource 候选边共享输出 residual，展开后的 role/wave/capability mask、容量和
联盟原子性不交给模型。版本变化和 stale rejection 沿用 `AssignmentPlan` 合同。

该单测关闭“top-k 小于 k_j 导致实现性 shortfall”的 D3-owned 缺口，但不证明密集
200v200 M-to-N、能力异构、动态资源失效或 AirSim 协同物理完成。全量结果为
`170 passed, 1 skipped`；真实 M5N2 第二 primary/coalition、多 seed 和 PPO 均保持
开放或未实现状态。

## 19. 区域降级下的 M-to-N 提交合同（2026-07-20）

中心、二级或完全分布式层级变化不能降低 M-to-N 的全有或全无要求。D4 先裁决区域
owner 和成员，D3 再检查成员数量是否等于 `required_resource_count`、资源是否重复、
每条边是否仍可行及能力是否满足。`k=1` 使用 D4 已裁决的区域 owner、epoch、lease、
执行许可和唯一成员，不建立多成员原子联盟；该规则同时适用于 secondary 和完全分布式
层级。任何 `k>1` 目标均必须附带 committed、atomic committed 和完整 ACK 联盟证据。

联盟证据必须与区域 owner、epoch、成员集合和 lease 一致，并包含全部必要成员 ACK。
缺 ACK、未 committed、过期 lease、旧 epoch、协调者不一致或成员不一致均 fail closed。
通过后仍生成普通 `CoalitionPlan` 和版本化 `AssignmentPlan`，角色、波次、备用成员和
既有迟滞语义不变。D3 不自行选择二级节点，也不在分布式状态下本地重写目标身份。

模块测试已覆盖 secondary/distributed 单成员授权、D4 显式
`single_member_authorized`、单成员无授权/过期 lease、owner/epoch/member 不一致、
错误 atomic/commit-required 标记、grant 禁止执行和重复资源，distributed 三成员
committed，以及缺 ACK、旧 epoch 和 stale source 拒绝。该结果证明 D3 发布合同可执行，
不证明 D4 已完成区域裁决映射，
也不证明网络分区下的运行时原子提交。main/D4 接线和 D6 按提交模式统计
latency/abort/reconfigure 仍为 P1。

## 20. M-to-N 联盟的故障代际 Fence（2026-07-20）

故障 fence 不重建 M-to-N 联盟。测试中的 k=3 计划在 fence 前后保持相同成员、角色、
coalition id/version、到达模式和授权状态，仅 D3 plan id/version 递增。这样 D4 可用
新 generation 重新裁决 owner，同时不会把故障隔离误计为联盟换员或绕过成员迟滞。

Fence metadata 明确标记 non-reassignment 和 requires-D4-gate。D7 仍按 D4
hold/continue、当前 owner 和后续区域计划执行；fence 本身不使任何 primary 或 reserve
获得新授权。该能力已通过模块测试，50v50 中心故障下的区域 owner 重裁决仍待 main
集成验证。

## 21. 学习研究管线对 M-to-N 的边界（2026-07-20）

新数据、BC、PPO 和 shadow 管线没有把 M-to-N 联盟原子性转移给模型。dataset 的
candidate edge 仍是原始 target-resource 边，目标需求数和 primary 数只是特征与 reward
上下文；role/wave/capability slot 展开、资源唯一性、all-or-none admission、coalition
version 和 stale 拒绝继续由 deterministic demand-slot planner 处理。

PPO rollout 将 bounded residual 写入候选成本副本后，必须调用同一个
`HungarianDemandSlotSolver`。hold 建议只能引用前一规则选边，并重新验证 candidate mask、
资源唯一和 demand 上限；不满足时计 safety rejection 并使用 solver 结果。策略不能
输出 coalition member list、primary/reserve role 或 assignment index。

legacy v1 synthetic smoke 只交替覆盖 independent-demand 3v5/5v3；已有 high-threat k=3
稀疏/all-or-none 单测继续作为 M-to-N 安全回归。尚未使用真实动态 demand、能力异构、
primary/reserve feedback 或资源失效序列训练，也没有 20 个未见 M-to-N test seed。
因此 pipeline implemented 不等于 M-to-N 学习策略或协同物理收益已验收；默认
Hungarian demand-slot 和既有 `8/10` 物理门限均不改变。

包括该 legacy 安全边界在内，当时新增学习管线专项测试 16 项；D3 全量为
`214 passed, 1 skipped`（215 项收集、6.95 s），唯一 skip 是 optional OR-Tools。

## 22. 单帧证据对 M-to-N 学习记录的约束（2026-07-20）

最近帧证据保留原始 target-resource rule/effective 矩阵，而不是把展开后的 demand slot
伪装成固定动作矩阵。匿名 track snapshot 仍携带
`required_resource_count/primary_resource_count`，最终 plan snapshot 保留实际选边；现有
`LearningFrameRecord` 因而可继续计算 demand shortfall、高威胁覆盖、前序选边和 churn。
role/wave/capability 展开、all-or-none admission 与 coalition 发布仍由在线 deterministic
planner 完成，不交给 recorder 或模型。

held、unchanged 和 forced-replan ack 的 frame 使用本 tick 成本矩阵和前序版本，可区分
“candidate 变化但联盟 roster 被迟滞保持”与“无变化”。regional authority frame 通过
`selection_source` 标识，不把 D4 owner 决策冒充中心 Hungarian。invalid authority、
stale 或无法将 plan assignment 映射到当前 roster 时直接 unavailable，不会用上一帧
补数。

专项测试包含非等量 1x3、3x2、7x4，证明证据 shape 随输入规模变化，没有 2v2/5v5
或固定 M-to-N 动作头。D3 全量 226 项为 `225 passed, 1 skipped`。该结果只完成
D3 recorder 合同；真实动态 demand、primary/reserve feedback、资源故障连续 seed、
main 写盘和 M-to-N shadow 非退化仍未验证。

## 23. 区域 transfer allowance 与 M-to-N 需求槽（2026-07-20）

区域提示约束原始 target-resource candidate mask，不创建独立的固定规模 transfer solver。
同一目标展开为多个 role/wave/capability slot 后，每个 slot 复制该 mask；所有 slot 仍共享
一组资源列并交给 `HungarianDemandSlotSolver`，因此一个资源不能被多个成员或目标重复
使用。每条 source-region -> target-region allowance 先绑定固定大小、互斥且未承诺的
资源池，故 M-to-N 实际跨区成员数不会超过许可。

上一计划的 primary、reserve、retry 及 coalition 成员均视为 protected，不进入新跨区
池；aggregate reserve ratio 另按 post-quota 计算 floor。提示不会重开 D5 hard edge、
能力不匹配或三维不可达边，也不改变 complete coalition 的 all-or-none admission、成员
角色、epoch、迟滞和 plan version。提示无效时整个 M-to-N 求解回到原 candidate graph，
不是在受损图上把 transfer count 置零。

专项 fixture 以一个 `required_resource_count=2` 的 simultaneous 目标验证两个 A 区空闲
资源经 allowance 成为 B 区候选并组成完整 coalition，actual/allowed 均为 2；另有 D5
hard edge + learning assist case 验证被禁资源不进入联盟。14 个新增 case 后 D3 全量为
`239 passed, 1 skipped`（240 项）；seed 不适用，未运行真实动态 demand、多 seed AirSim
或协同物理完成，因此只关闭 D3 候选图和 cardinality 合同缺口。

## 24. 数值 Seed v2 对 M-to-N 学习证据的约束（2026-07-20）

M-to-N roster、role/wave、demand-slot 和 coalition 仍由确定性 planner 处理，本批未改
算法。学习数据的 split identity 改为全局数值 seed：同一 seed 在 independent 2v2/5v5、
非等量规模和 M-to-N scenario 中复用时必须进入同一 split，不能把不同规模当成新的未见
seed。whole-seed 与 shadow unseen 计数也按该身份跨 scenario 聚合。

测试覆盖双 scenario/scale、多 episode、逆序输入、三 split 零交集和篡改拒绝；D3 全量
为 `243 passed, 1 skipped`（244 项）。这只关闭 M-to-N 学习数据隔离合同，不提供新的
动态 demand、联盟协同、模型收益或 AirSim 物理证据。

## 25. Learning 安全补正对 M-to-N 的影响（2026-07-20）

本轮不改变 demand-slot、role/wave、resource uniqueness、all-or-none admission、
coalition version 或 stale gate。BC/PPO 训练现在不能消费 test seed；test 只进入独立
shadow/evaluation。frame parser 的递归 identity 拒绝覆盖嵌套 M-to-N 匿名实体，普通
扩展需要 schema bump，不允许借 role/member/actor 字段恢复真实 roster 身份。

M-to-N slot 复制前的 target-resource candidate mask 必须与 hard reject reasons 求交，
因此 residual 不能重开 capability、D5、容量、冲突或可达性边。rule coalition 与 residual
proposal coalition 分别求解后，都用原始 `C_rule + unassigned_costs` 按最终选边和 unmet
slot 重评分；`rule_cost_matrix_v1` 是 promotion 的唯一成本非退化口径。bundle/evidence
还必须绑定 split、完整 frame 内容和 model-state 三摘要，并通过 eligible 正式 test gate。

最新 D3 全量 252 项为 `251 passed, 1 skipped`，零失败通过，skip 是 optional OR-Tools。
这只关闭 M-to-N 学习外环的软件安全缺口；仍无动态 demand 真实训练、20 个未见真实/高
保真 M-to-N test seed、正式权重/promotion、AirSim 协同收益或 `8/10` 物理门限新证据。

## 26. M-to-N 运行绑定确认（2026-07-21）

新 runtime ACK 消费器按资源验证 binding，因此允许多个资源合法指向同一
`global_track_id`，同时禁止同一资源重复出现或被重绑。每条 M-to-N binding 必须与预期
`AssignmentPlan` 的 coalition id/version 和 member role 精确一致。primary、reserve
或 retry 不能由 D7 ACK 临时改写；缺失、额外、重复成员和旧计划版本均失败关闭。

专项正例使用两个资源指向同一中心航迹，分别携带 primary 和 reserve 角色，并验证一个
中段命令和一个 hold 命令。24 项专项测试通过，其中包含两种合法 D3 包导入组合和任意
鸭子类型拒绝。自动化 3v3、seed 7、1.2 秒真实 main 集成测试另验证 3 条普通 binding
的来源哈希和控制统计，但不是高威胁 M-to-N 物理协同试验。consumer 源码不导入 main；
main 集成栈只在 D3 测试中导入。冻结 900-episode 数据仍无运行 ACK；多成员 outcome、
联盟协同完成和 reward 继续 unavailable，PPO/assist 不开放。

## 27. M-to-N 运行窗口归因（2026-07-21）

新的 D3 归因合同按成员 binding 建窗，因此同一 `global_track_id` 可以合法对应多个
primary/reserve 资源，同时每个资源仍只能有一个当前窗口。每个成员分别绑定 plan/
coalition version、角色、owner、D7 消费和 ACK occurrence。资源窗口重叠、旧联盟版本、
角色不一致或同 identity 执行签名变化均拒绝。

成员进入五米或距离改善只形成该 binding 的 observed diagnostic。合同不会把一个成员的
结果外推为 coalition completion，也不会把多个同 episode 五米事件相加为协同 reward。
正式 M-to-N 奖励仍需计划级需求满足、全部 required primary 状态、规则/候选同 seed 配对
和反事实归因。当前六项原始 reward 分量与 coalition reward 均 unavailable，不补零；
PPO、assist 和 authority 保持关闭。

该行为包含在 16 项新专项和 D3 全量 `319 passed, 1 skipped` 中。真实 3v3 集成样本验证
普通 binding 链路，不是高威胁多成员物理协同试验，不能关闭原有 M-to-N 多 seed P1。

## 28. 区域授权与零绑定需求库存（2026-07-22）

区域降级计划现区分“D4 已授权的执行目标”和“当前计划必须保留的需求库存”。grant 未覆盖
的目标只有在上一计划已经证明零 assignment、未分配、不完整且需求摘要为零满足时才能
继续进入新计划。该目标只保留 required、assigned 0 和 shortfall，不生成区域 owner、
coalition、commit 或执行许可。

该规则不放宽 M-to-N 全有或全无约束。只要目标已有一个可执行成员，D4 就必须覆盖该目标，
并按需求数量提供完整成员与必要的原子提交证据；不能把部分联盟伪装成零绑定库存。新增但
未证明的目标、漏掉旧执行目标、previous-only 可执行绑定、旧 epoch、过期 lease 和缺少
成员 ACK 均失败关闭。

模块回归覆盖 5 目标、4 个授权绑定和 1 个 `0/1` 待分配目标。三维质点
`secondary_failure`、4.2 秒、seed 1011/1019 的 main 集成测试文件为 `10 passed`，D3 全量
为 `390 passed, 1 skipped`。当前仍缺更大规模、多 seed、通信退化和 AirSim 区域联盟
验证；生产 runtime ACK、D7 控制采用和物理结果不由该库存合同推导。

## 29. 多周期行为克隆影子评估中的 M-to-N 需求变化（2026-07-25）

本轮把 M-to-N 需求变化纳入规则组与行为克隆残差组的连续成对评估。每个组接收同一匿名
目标、资源、时间戳和外生事件，各自沿自己的上一计划推进。场景将同一高威胁目标的
`required_resource_count` 按 `1 -> 3 -> 1` 改变，最终分配仍由既有需求槽 Hungarian、
成员唯一性和全有或全无准入决定。处理组没有成员增删权限，也不能重开硬安全候选边。

固定保留种子影子运行使用 1000-1019，与训练种子 0-99 无交集。M-to-N 场景共 100 个周期，
其中需求提升对应的 40 个周期被特征分布保护判定为分布外，处理矩阵逐元素恢复规则矩阵。
该场景没有重复资源、硬约束或计划谱系违规，也没有旧版本采用和在线真值使用。结果说明
现有冻结行为克隆模型尚未覆盖三成员动态需求，不能通过放宽分布外门限直接参与 M-to-N
分配。

该项只补齐 M-to-N 多周期需求变化、回退原因和矩阵一致性证据。PPO、线上 assist、
authority 和运行时计划发布继续关闭；默认 Hungarian 与需求槽 Hungarian 不变。真实成员
确认、联盟执行、后续物理结果和协同收益仍缺失，因此 M-to-N 运行闭环 P1 保持开放。

## 30. M-to-N 干预候选帧资格（2026-07-26）

学习处理帧只有在 M-to-N 联盟完整时才能进入后续共同检查点。D3 现从当前匿名航迹重新读取
`required_resource_count` 和 primary 数量，并逐目标核对需求摘要、联盟成员、角色、波次、
可执行 assignment、未分配清单及不完整清单。完整联盟必须 committed 且执行全部所需成员；
不完整联盟必须执行零成员。任何部分联盟均返回
`rule_m_to_n_all_or_none_incomplete` 或
`treatment_m_to_n_all_or_none_incomplete`。

专项正例包含一个双 primary 目标和一个普通目标。规则与处理计划均有 3 个完整需求槽，学习
实际改变 6 条 hard-safe 边并形成 3 个资源绑定差异。负例删除一个处理组可执行成员后资格
失败。该资格只支持 main 选择物理续跑前的候选帧，不确认成员 ACK、D4 联盟提交、D7 控制
采用或协同物理完成。

D3 全量为 `484 passed, 1 skipped`（485 项）。默认 `hungarian_demand_slots`、成员角色、
迟滞、计划版本和全有或全无准入未改变。真实多成员共同检查点、D4/D7 求交和 clean 多 seed
物理比较仍属于跨模块 P1。

## 31. M-to-N 单帧隔离重放（2026-07-26）

单帧重放生产者继续使用现有 `hungarian_demand_slots`，没有为学习处理组增加成员选择或
部分联盟权限。正向夹具中一个目标要求两个 primary，另一个目标要求一个资源。规则组和
处理组均形成三个完整需求槽、零未分配和零不完整联盟；学习残差只改变 hard-safe 成本，
最终三个资源绑定发生变化。

源帧的需求、成员角色、目标顺序、前序版本或 M-to-N 全有或全无证据不完整时，重放或后续
资格判断失败关闭。bundle 身份错误、非 shadow-only、OOD 或超时时恢复规则成本，不能为了
获得绑定变化放宽安全门。该专项包含在新增 `17 passed` 和 D3 全量
`501 passed, 1 skipped` 中。

本项只关闭 D3 生成同输入规则/处理帧的接口缺口。main/D6 仍需从外层 manifest 校验 20 个
保留 seed，并与 D4 联盟提交、D7 共同检查点和后续物理窗口连接。成员 ACK、协同 outcome
和 reward 仍不可用。

## 32. M-to-N 20-seed 批量检查点合同（2026-07-26）

外层 batch runner 已能对固定 seed `1000-1019` 逐帧执行 M-to-N 单帧重放，并选择每个
seed 的首个完整且绑定发生变化的候选。夹具使用一个双 primary 目标和一个普通目标，两组
计划都必须完成三个需求槽；任何部分联盟仍由原资格合同拒绝。batch 没有增加成员、改变
角色或绕过需求槽 Hungarian。

可辨识夹具 20/20 seed 有首个合格帧，零残差夹具 20/20 seed 明确不可用。该批次使用重复
匿名单元夹具验证 manifest、顺序和失败关闭，不是 20 个独立物理场景。

main 后续在 clean source commit `0ed7ca2730f5354be1e6021f9882f1ae26bc42df`
保存了 20 seed、每 seed 5 帧、共 100 个真实形态匿名帧。输入 manifest SHA-256 为
`e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`，输入
`SHA256SUMS` 全部通过。首次重放暴露新增目标联盟匿名标识与隔离规划器本地命名不一致。
D3 只恢复记录帧已哈希绑定的新联盟 token，并继续校验前序联盟连续性、成员引用、需求摘要
和完整控制执行签名。

正式 clean evaluator 使用代码提交
`bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c`。输出 `SHA256SUMS` 全部通过，内容
SHA-256 为 `c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`，
输入与输出外部归档 SHA-256 为
`127ad91d864b136ab10cde7111bf6241a7a765ad4467aa449ef29cbb5557ef5e`。修复后 100 帧
全部可重放，但逐 seed 资源目标绑定变化为 0；80 帧应用学习代价，20 帧分布外回退，
20/20 seed 均为 `no_eligible_frame`，硬违规和 `global_track_id` 改写均为 0。

真实多成员 ACK、D4 联盟提交、D7 控制采用、协同 outcome 和 reward 仍未形成。当前 bundle
没有产生可辨识 M-to-N 检查点，不能形成 D7 checkpoint 或 A1 准入，跨模块物理闭环 P1
保持开放。`publish=false`，默认路径和生产权限保持关闭。不能通过降低全有或全无、联盟
连续性或 eligibility 门限获得候选。

该合同和新增真实形态正负例包含在单帧专项 `23 passed`、相关合同组合 `79 passed` 和 D3
全量 `521 passed, 1 skipped`（522 项）中；它没有关闭真实 M-to-N 物理协同证据缺口。
