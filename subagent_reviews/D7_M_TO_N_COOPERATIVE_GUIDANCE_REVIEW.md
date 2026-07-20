# D7 M 对 N 多无人机协同导引与到达时序综述

## 2026-07-20 三维 N-pair 执行边界补充

新增 `ScalableGuidanceController3D.command_batch()` 可在一次调用中处理任意长度的
已分配 pair，并输出按 main resource index 排列的完整 NED 加速度数组；确定性测试
已覆盖 7 pair 和 200 pair，命令均 finite 且不越配置上限。多个资源可以合法地消费
同一个 center-owned `global_track_id`，但各自的航迹滤波、LOS KF、TTC、dropout
coast 和模式状态按 `(resource_id, global_track_id)` 隔离，D7 不由此形成或修改联盟。

2-resource/1-target 质点 fixture 使用 NED 三维 5 米判据：任一资源首达即满足本测试
的 target intercept，首达时另一资源仍在 5 米外。这与当前 per-primary/无需同时到达
合同一致，也再次说明“N 个独立三维 PN pair 并行”不是 cooperative impact-time
guidance。本轮没有 coalition clock、time-to-go consensus、同步/序贯到达控制、终端
扇区协调或成员防碰撞；这些能力仍保持未实现。

2026-07-20 验证为 14 个新增确定性场景、D7 全量 `204 passed`，无 AirSim 运行。
scalable point-mass 3D 路径已从 isolated benchmark 晋级为 D7-owned executable
baseline，但 M-to-N 协同结论不变：D3 决定成员和版本，D4 决定许可，D5 提供每个
资源的视觉锁，D7 只执行各 pair 的有界命令。后续若研究同时到达，必须另建明确的
coalition-level 时钟、通信、可行性和安全约束，不能复用本轮“任一首达 5 米”结果
宣称协同控制完成。

## 2026-07-15 M5N2 baseline/candidate 各 10 seeds 复核

本轮只复核 20 个已完成的真实 AirSim SimpleFlight M5N2 case。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；该单 seed 不纳入本次 M5N2 统计，也不用于分析或晋级，其余 tuned case 和全部 dropout 均未执行。高威胁目标的联盟仍为 2 个 active primary + 1 个 standby reserve，验收仍是每个 active primary 在同 case 分别进入 NED 三维 5 米，不要求同时到达。

baseline 和 candidate 的 active-primary 成功都是 `6/30`，target 都是 `6/20`，coalition 都是 `0/10`；合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`。第二 primary 按各 case 的 active membership 动态识别，不固定资源编号；七阶段证据为 `assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。最近距离仍为 `8.873-14.740 m` 和 `8.843-14.309 m`。其中 baseline 的首失败为 physical 8/terminal control 2，candidate 为 physical 9/terminal control 1。这一证据将主要问题从“合同没接上”进一步收敛到“视觉可控状态不持续或物理航路/停控未闭合”。

20 个第二 primary 最终均为 `collision_stop`，但 collision object 为空，故当前不能区分是友方协同冲突、环境碰撞、机体状态还是其他 AirSim 原因，也不能归因于导引公式。这是下一轮最直接的 P1 证据缺口，不能用放宽 D5/D7 安全门代替。candidate 逐 seed non-degradation=false，paired 结果为 2 改善、2 退化、6 持平，trend coast 触发=0、soft-specific duration=0，故继续 default-off。D7 阶段 mean/P95 为 `4.84/5.78 ms`，不是主要时序瓶颈。online truth identity/state 均为 0，位置 PN、VM/TTC PNG、LOS 和外推公式未修改。

## 2026-07-15 第二 primary 诊断补充

联盟摘要不再只给第二 primary 的一个最终字符串，而是保留 `assigned -> active -> radar -> D5 visible/associated/locked -> contract -> control -> mode -> physical` 全漏斗、每级首达时刻、规范首失败和 measured-lock 时序。该能力适用于任意 primary 数量；“第二 primary”仅是联盟内按资源/assignment 稳定排序后的 ordinal 2 诊断视图，不写死 M5N2，也不要求同时到达。

本地确定性回归中，第二 primary 在 contract 已达、control 未达时被正确定位为 `terminal_control`；reserve、owner/version 和 D3/D4/D5 门控语义保持不变。2026-07-15 D7 全量 `190 passed`；真实 AirSim 多 seed、第二 primary 5 米完成率和成员安全间距仍为 P1。

## 2026-07-14 actual-execution 证据补充

最新真实 AirSim seed-1 证据不改变“多个独立 pair 不等于协同导引”的结论。canonical actual 五层按 contract/control/terminal-switch/mode/physical 独立统计：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`；五层均为 `available`，且 `terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计。M5N2 active pair 为 `2/3`、第二 primary 最近约 `11.02 m`，target `2/2` 只表示目标覆盖，coalition completion 是独立的 `0/1`。两个 actual-execution case 均 available 且 identity/state online truth 为 0，P0 证据链关闭。当前 P1 是第二 primary、multi-seed/dropout/candidate、延迟及 pair funnel/closing-speed/三维机动标定；3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。

## 1. 调研结论摘要

本报告面向一个高威胁目标由多架拦截无人机协同处置的 `M resources -> N targets` 场景。以目标 `j` 的资源需求 `k_j=3` 为例，未来 D3 即使为同一个 `global_track_id` 形成三成员联盟，也不自动构成协同导引。只有三架资源共享或协调到达时间、剩余时间、通信拓扑、终端进入方向或安全间隔，并据此改变各自导引命令，才能称为协同导引。

主要结论如下：

1. **经典 PN 仍是单机末段默认基线**。多架无人机各自运行 PN，只能称为“多个独立 PN pair 并行”，不能称为 cooperative PN。
2. **同步到达的主流研究路线是 impact-time control/consensus + 末段 PN**。有限时间、固定时间和预设时间一致性均有较多同行评审研究，但多数只验证了质点或导弹动力学仿真，少数有实验平台验证，尚不是可直接部署到多旋翼 C-UAS 的成熟软件栈。
3. **同步到达不是所有高威胁目标的默认答案**。三机同时到达同一空间点会增加互撞、视场遮挡、通信同步和机动饱和风险，必须同时设计终端扇区、期望进入角和最小间隔。
4. **序贯波次主要是调度问题**。D3/D4 先给出每架资源的期望到达时刻或时间窗，D7 再执行独立 ITCG/PN。检索中没有发现与同步一致性同等成熟的“序贯协同导引”统一开源实现。
5. **建议的工程研究默认是混合主备**：首批资源在可行时间窗内协调到达，后续资源保持时间/空间间隔并根据首批结果继续、等待或退出。它兼顾高威胁覆盖和互撞风险，但仍属于需要仿真验证的系统方案，不是已经形成唯一共识的控制律。
6. **没有发现成熟、许可证明确、带测试、可直接复用的多旋翼 cooperative impact-time guidance 库**。许可证明确的候选只实现单拦截器 impact-time control；真正展示同步齐射或 cooperative PIP 的仓库均存在许可证或验证完整度问题。
7. **MSM 已实现中心化 coalition 合同门控，但没有实现协同到达控制律**。D7 现可消费 coalition/version、role、wave、arrival window 和 activation/version，并按 assignment pair 独立 gate；它仍没有 coalition clock、time-to-go consensus、成员间防碰撞约束或协同导引通信状态。
8. **arrival window 是视觉接管许可窗，不是 assignment 自动撤销时刻**。真实 posefix replay 显示窗口关闭样本仍需要 radar PN 保持中段控制并等待新版本；D7 已按此解释状态，但同步到达和窗口滚动仍由 D3/main 负责。
9. **当前阶段可显式采用 per-primary terminal authorization**。当 D3 合同声明 `terminal_authorization_scope=per_primary` 且 `arrival_coordination_required=false`，D7 允许每个 active primary 独立满足 D5/视觉/机动门控后切换 PNG，不再等待共同锁定或同步到达；这是一种阶段性工程合同，不等价于 cooperative impact-time guidance，reserve 和分布式提交安全门控保持不变。
10. **typed topology 已下发上述 policy**。构建器支持统一或按目标配置，并把 scope/arrival policy 写入 target summary 与每个 binding；因此 main 不应再通过临时 metadata 改写合同。默认调用仍保持旧 coalition/arrival gate。
11. **pair/coalition 聚合采用版本化末端语义**。`d7_terminal_semantics_v2` 分离 raw gate、effective contract、latched mode、effective control、mode transition 和 termination snapshot；bounded coast 必须标记 scope，终止行不参与 live coalition control/mode 分母。旧字段仅为 effective 口径 alias，不能再把 raw D5 non-lock 与合规 coast 或 episode 终止混成同一计数。
12. **M5N2 no-switch 必须按 pair 首失败解释**。`d7_pair_guidance_funnel_v2` 先区分是否进入配置交接距离，再区分 D5 declared/measured lock、raw gate、camera/LOS/closing-speed/maneuver 和 latch/effective control。seed-1 现有输出中，两个 active pair 在约 `35-39 m` 停止，未进入约 `30 m` 交接区；一个 pair 进入约 `26 m` 后仍 `d5_not_locked`。主 CSV 缺 raw reject/measured-lock 字段时必须报 evidence missing，不能把默认 false 解释成具体视觉门限失败。
13. **配置视觉律、候选视觉律与实际执行律必须分开**。`d7_guidance_law_semantics_v1` 规定 main 选择 `png_vm/png_ttc` 只代表配置了 radar-to-vision 策略；本帧候选 PNG 经过 camera/LOS/maneuver gate 后，只有 effective control 与 visual latch 都成立才可成为 executed law。gate 失败时实际执行仍是 `radar_pn`。联盟统计必须使用同一 live state instance 的 `executed_visual_mode_switch`，不能从 candidate、handover 状态或 legacy active-sample 字段推断切换。

因此，协同到达属于后置研究，不是当前 P0 或 P1 运行断链。impact-time consensus、同步到达和到达离散优化不进入当前 P1 验收；当前只保持 per-primary 独立完成、联盟版本/角色/激活合同和安全门控。D7-owned pair 诊断与导引律执行语义已由 `188 passed` 关闭，main/D6 canonical 五层也已正式闭合；开放项仅为第二 primary、multi-seed/dropout/candidate、延迟及 pair-funnel/closing-speed/三维机动标定。现有 D3/D4/D5/D7 执行链必须保持可用，且不得通过修改 `png_guidance_delivery` 公式或放宽 D3/D4/D5 gate 来伪造协同能力。

## 2. 问题定义与判定边界

### 2.1 M 对 N 与目标资源需求

设资源集合为 `R={r_1,...,r_M}`，目标集合为 `T={t_1,...,t_N}`，目标 `t_j` 的资源需求为 `k_j >= 1`。D3 需要形成联盟：

```text
C_j = {r_i | resource r_i is assigned to target t_j}
|C_j| >= k_j
```

D7 只消费已经生效且版本一致的联盟成员关系，不决定 `k_j`，也不增删联盟成员。一个可执行的协同导引任务至少还需要：

```text
coalition_id
assigned_global_track_id
member_resource_ids
coordination_mode: independent | simultaneous | sequential | hybrid
desired_arrival_time_s or arrival_window_s
wave_index / member_role
terminal_approach_sector or desired_terminal_bearing
minimum_member_separation_m
plan_id / plan_version / owner_node_id
```

这些是后续跨模块合同调研项，本轮不设计或实现代码。

### 2.2 什么才是协同导引

以下情况不构成协同导引：

- 三架无人机碰巧被分到同一目标，但各自只按自身 LOS 独立运行 PN。
- 三架无人机使用相同导航比，但没有共享到达时间或邻居状态。
- D5 同时看到三架友方和一个目标，仅凭视觉画面判定“协同”。
- main 同时启动三个独立 pair，而 D7 内部没有 coalition-level state。

以下情况可以构成协同导引：

- 各成员交换或由 leader/中心发布 time-to-go，形成 impact-time consensus。
- 各成员接受同一可行到达时间或不同波次到达时间，并使用 ITCG/bias PN 调整路径长度。
- 各成员协调终端进入角、LOS 扇区和最小间距，避免同点同向冲突。
- 在通信受限时，依据版本化的共同计划和可验证的本地时钟继续执行，并在过期或不一致时保守退出协同模式。

### 2.3 有限时间、固定时间与预设时间

| 概念 | 收敛时间特性 | 对 MSM 的意义 |
|---|---|---|
| finite-time | 有限时间收敛，但上界通常依赖初始条件 | 可用于给定场景的快速一致，但换几何后需重新验证 |
| fixed-time | 收敛时间上界不依赖初始条件 | 对多初始几何更稳健，但增益和饱和仍需校准 |
| prescribed-time | 设计者指定理论收敛时间 | 最贴合版本化任务时间窗，但指定时间必须满足可达性和控制约束 |
| practical prescribed-time | 在指定时间进入有界误差邻域 | 更接近有噪声、时延和饱和的工程实现 |

无论采用哪一种，一致性收敛都不等于安全到达。终端碰撞规避、成员失联处理和 D5 身份一致性仍需单独门控。

## 3. 同时、序贯与混合策略

### 3.1 同时到达

典型方法是让各成员的估计剩余时间 `t_go,i` 收敛到共同值或共同指定值：

```text
e_i = t_go,i - t_go,consensus
u_i = PN_term + impact_time_bias(e_i, neighbor_errors)
```

适用条件：

- 目标高速机动或逃逸窗口短，首轮失败后几乎没有补救时间。
- 三架资源均能在共同到达时间的可达集合内完成任务。
- 时钟同步、成员通信或 leader/中心广播可靠。
- 已分配不同终端扇区/进入角，并能保证成员间最小距离。
- D1/D2 对目标机动和协方差的估计足以支持稳定 `t_go`。

主要风险：

- 共同时间不可达时，成员为延迟或赶时产生过大航迹弯曲、加速度饱和或 FOV 丢失。
- 多成员同时进入相同小区域，互撞和相机遮挡风险显著增加。
- 一个成员的错误 time-to-go 或通信异常可能污染一致性结果。
- 同步命中研究常采用导弹质点模型，不能直接推定 SimpleFlight 多旋翼可复现同等性能。

### 3.2 序贯波次

序贯策略为不同成员给出偏移后的到达时刻：

```text
t_arrival,i = t_base + wave_index_i * delta_t
```

D7 只负责跟踪每个成员的到达时间/窗口；波次和 `delta_t` 应由 D3 根据威胁、资源机动能力、D5 观测和安全约束确定。

适用条件：

- 需要根据首批结果决定后续资源是否继续。
- 目标身份或末端视觉关联仍存在不确定性。
- 同时进入会造成互撞、遮挡、下洗或通信拥塞。
- 资源初始距离和机动能力差异过大，没有共同可行到达时间。
- 通信受限但能够在任务开始前下发稳定的版本化时间窗。

主要代价：

- 后续成员可能面对目标机动后的新几何，原时间窗失效。
- 总任务完成时间更长，目标可能在波次间逃逸。
- 首批任务反馈必须通过 D4/D5/D3 进入新版本计划，D7 不能自行决定第二波是否继续。

检索结论：序贯方法通常由任务调度、time-window assignment 与单机 ITCG/PN 拼接而成，尚未找到成熟统一的开源“序贯 cooperative guidance”实现。

### 3.3 混合主备

对 `k_j=3` 的高威胁目标，推荐作为下一阶段研究基线，而不是当前默认控制律：

- 两架 primary 在有安全角度分离的条件下进入共同到达窗口。
- 第三架 reserve/observer 保持空间和时间间隔，继续提供观测或等待新版本授权。
- 若 primary 关联一致且任务完成，reserve 保持/退出；若 D5 报告失败或 D4/D3 发布新计划，reserve 才进入下一波。

适用条件：

- 高威胁需要资源冗余，但三机同点同时到达风险不可接受。
- D5 能在首批执行后及时返回锁定、模糊、友方冲突或重捕获状态。
- D4/D3 能在计划版本和 lease 内完成继续/取消仲裁。

混合策略的核心不是简单的“2+1”，而是显式成员角色、时间窗、终端扇区和版本化继续条件。若任务定义要求三架都必须实际进入拦截窗口，则可以采用 `2 simultaneous + 1 delayed`，但不能把 reserve 永久等待计入需求满足。

### 3.4 决策建议

| 条件 | 优先策略 | 理由 |
|---|---|---|
| 逃逸窗口短、三机共同时间可达、通信和分离角可靠 | 同时到达 | 压缩目标规避时间 |
| 身份/航迹不确定、首批结果有信息价值 | 序贯 | 允许依据反馈保守决策 |
| 高威胁且需冗余，但终端空间拥挤 | 混合主备 | 兼顾覆盖和安全 |
| 通信中断但已有可信版本化时间窗 | 序贯或预先计划混合 | 避免依赖在线 consensus |
| 共同时间不可达、成员机动差异大 | 序贯 | 防止为赶时导致饱和/FOV 丢失 |
| 无终端分离扇区或防碰撞证据 | 禁止三机同时进入 | 到达同步不能替代安全约束 |

## 4. 论文证据

本次以 2015-2026 年为主，保留必要的 impact-time control 基础概念。下表列出 12 篇已通过 DOI/出版社元数据或开放全文页面核验的主要论文。论文代码列为“未发现”时，仅表示本轮未找到作者公开、许可证明确的实现，不能据此断言作者从未发布任何材料。

| 年份 | 论文与原始来源 | 组织方式 | 到达策略 | 验证 | 代码/适配判断 |
|---|---|---|---|---|---|
| 2016 | Zhou, Yang, *Distributed Guidance Law Design for Cooperative Simultaneous Attacks with Multiple Missiles*, JGCD, [DOI](https://doi.org/10.2514/1.G001609) | 分布式 | 同时 | 数值仿真 | 未发现许可证明确代码；可作分布式同步基线 |
| 2019 | Lyu et al., *Multiple missiles cooperative guidance with simultaneous attack requirement under directed topologies*, AST, [DOI](https://doi.org/10.1016/j.ast.2019.03.037) | 有向图分布式 | 同时 | 数值仿真 | 未发现代码；适合研究不对称通信拓扑 |
| 2019/2020 | Zhang, Tang, Guo, *Two-stage cooperative guidance strategy using a prescribed-time optimal consensus method*, AST, [DOI](https://doi.org/10.1016/j.ast.2019.105641) | 分布式两阶段 | 同时 | 数值仿真 | 未发现代码；“一致性阶段 + PN 阶段”与 D7 分层最接近 |
| 2019 | Jha et al., *Cooperative Guidance and Collision Avoidance for Multiple Pursuers*, JGCD, [DOI](https://doi.org/10.2514/1.G004139) | 协同最优控制 | 协同拦截并避碰 | 仿真和实验验证 | 未发现代码；说明同步外必须显式处理 pursuer-pursuer collision |
| 2020/2021 | Zhang et al., *Finite-Time Cooperative Guidance Strategy for Impact Angle and Time Control*, IEEE TAES, [DOI](https://doi.org/10.1109/TAES.2020.3037958) | leaderless/leader-follower | 同时、角度约束 | 数值仿真 | 未发现代码；适合比较中心 leader 与无 leader 模式 |
| 2021 | Chen et al., *Three-dimensional fixed-time robust cooperative guidance law for simultaneous attack with impact angle constraint*, AST, [DOI](https://doi.org/10.1016/j.ast.2021.106523) | 分布式/固定时间 | 同时、3D、角度约束 | 数值仿真 | 未发现代码；用于 D7 未来 3D benchmark，不可直接替换 2D 主线 |
| 2021 | Li et al., *Distributed observer-based cooperative guidance with appointed impact time and collision avoidance*, JFI, [DOI](https://doi.org/10.1016/j.jfranklin.2021.06.030) | 分布式 observer | 指定同时到达并避碰 | 数值仿真 | 未发现代码；同时覆盖到达时间和成员碰撞约束 |
| 2022 | Ma et al., *Prescribed-time cooperative guidance with time delay*, Aeronautical Journal, [DOI](https://doi.org/10.1017/aer.2022.87) | 延时一致性、两阶段 | 同时 | 3D 比较仿真 | 未发现代码；第一阶段处理延时，第二阶段转 PN，适合通信时延研究 |
| 2023 | Yu et al., *Impact Time Consensus Cooperative Guidance Against the Maneuvering Target: Theory and Experiment*, IEEE TAES, [DOI](https://doi.org/10.1109/TAES.2023.3243154) | 邻居通信、max-consensus | 自动协商共同时间 | 数值仿真和等效实验平台 | 未发现作者代码；实验等级高于纯仿真论文，但仍非多旋翼开源栈 |
| 2023 | Tang, Zuo, *Cooperative Circular Guidance of Multiple Missiles: A Practical Prescribed-Time Consensus Approach*, JGCD, [DOI](https://doi.org/10.2514/1.G007431) | 有向/无向分布式 | 同时 | 2D/3D 数值仿真 | 未发现代码；强调 practical prescribed-time 和加速度降低 |
| 2024 | Ma, Guo, *Prescribed-Time Cooperative Guidance Law for Multi-UAV with Intermittent Communication*, Drones, [DOI/开放全文](https://doi.org/10.3390/drones8120748) | 有向内部通信、间歇 pinning | 同时、两阶段 | 数值仿真 | 论文 CC BY 4.0，未发现配套代码；与 MSM 通信退化假设最接近 |
| 2025 | Zhu et al., *Impact-Angle-Constrained Cooperative Guidance: An Event-Triggered Finite-Time Strategy*, IEEE TAES, [DOI](https://doi.org/10.1109/TAES.2025.3556115) | 事件触发分布式 | 同时、角度约束 | 数值仿真 | 未发现代码；事件触发可降通信频率，但仍需工程时钟和丢包验证 |

### 4.1 论文证据强弱

- **较强证据**：Yu et al. 2023 同时给出理论、数值仿真和等效实验平台；Jha et al. 2019 把成员碰撞规避纳入协同控制并报告实验验证。
- **中等证据**：其余主要为有收敛证明的同行评审论文和 2D/3D 数值仿真，能支持算法可行性，不能直接支持 AirSim/SimpleFlight 或真实多旋翼工程成熟度。
- **开放性较好**：Ma, Guo 2024 为 CC BY 4.0 开放论文，但开放论文不等于开放实现。
- **序贯证据不足**：没有检索到同等成熟、统一处理波次调度、成员反馈和末段导引的同行评审开源方案，应由 D3 调度研究与 D7 ITCG/PN 研究组合验证。

## 5. 开源代码审计

### 5.1 候选仓库

| 仓库 | 内容 | 许可证 | 活跃/测试状态 | 可复用性与 MSM 适配难点 |
|---|---|---|---|---|
| [wongquinn/Nonsingular-Sliding-Mode-Guidance-for-Impact-Time-Control](https://github.com/wongquinn/Nonsingular-Sliding-Mode-Guidance-for-Impact-Time-Control) | Cho et al. 2016 nonsingular sliding-mode ITCG 的 MATLAB 单脚本复现 | MIT | 2025 建仓；未见自动测试 | 唯一许可证明确候选；只解决单拦截器 impact time，不含 consensus、联盟、通信或避碰，只能作公式对照 |
| [dkm-08/impact-time-guidance-interceptor](https://github.com/dkm-08/impact-time-guidance-interceptor) | MATLAB/Simulink；通过各拦截器可行时间区间交集选择共同 `t_f`，演示 salvo 同步 | 未声明 | 2025-01 最后代码提交；6 个顶层文件/压缩包；未见测试 | 思路直观，但无许可证不可并入代码；缺机动目标、自动驾驶仪延迟和 HIL |
| [Dev-Rajyaguru/missile-guidance](https://github.com/Dev-Rajyaguru/missile-guidance) | MATLAB 3DOF ITCG/PN 对照和四枚齐射动画 | 未声明 | 2026-06 有更新；未见自动测试 | 可作人工复现实验参考；无许可证、无 D3/D4/D5 合同、无多旋翼模型 |
| [AidenGeunGeun/Coop_guidance](https://github.com/AidenGeunGeun/Coop_guidance) | Python 2D/3DoF sandbox，PN/APN/PIP cooperative，带 pytest | 未声明 | 2025-12 有更新；仓库含 tests | 工程结构最好，但 PIP cooperation 不等于 impact-time consensus；无许可证，不可复制；模型和安全边界与 SimpleFlight 不同 |
| [aofenghanyue/EntryGuidance](https://github.com/aofenghanyue/EntryGuidance) | Python 多飞行器协同高超声速再入制导 | 未声明 | 2022-07 最后提交；未见正式测试 | 领域、动力学和任务不同；只可借鉴多实体仿真组织，不宜作为 D7 协同拦截算法来源 |

### 5.2 开源结论

- **成熟开源实现：未发现。** 没有候选同时满足 cooperative impact-time consensus、终端避碰、多旋翼动力学、清晰许可证、自动测试和活跃维护。
- **许可证明确的研究对照：1 个。** `wongquinn/...` 可用于核对单机 ITCG 数学结果，但不能代表协同导引。
- **研究型参考：4 个。** 其余仓库可用于理解 common-time selection、salvo 动画、PIP 或多实体仿真，但因许可证或任务模型问题，不应复制进入 MSM。
- **当前建议：只记录证据，不引入依赖。** 后续若实现，应依据论文重新独立实现最小研究核，并保留论文引用和数值回归，而不是拷贝无许可证源码。

## 6. 碰撞避免、LOS 分离与终端同步

### 6.1 同步时间不等于同步空间安全

三架资源如果都以同一个目标点和同一个到达时刻作为唯一目标，可能在终端形成资源-资源碰撞。最低限度需要同时约束：

```text
|t_arrival,i - t_arrival,j| <= simultaneous_window_s
distance(resource_i, resource_j) >= minimum_member_separation_m
terminal_sector_i != terminal_sector_j
```

同步策略应把终端进入角/方位扇区作为 D3/D7 联合约束；D7 还需记录命令饱和和安全 gate。单纯调整导航比或共享 `t_go` 不足以保证安全。

### 6.2 LOS 角分离

可研究的保守方法包括：

- D3 为联盟成员分配不同 terminal approach sector。
- D7 使用 impact-angle-constrained guidance 将各成员 LOS 收敛到不同终端方向。
- 当预测成员间距低于安全阈值时，安全层优先于 time consensus，输出 hold/abort 或重新规划请求。
- D5 对多视角共同锁定同一 `global_track_id` 应标记为“计划内 coalition lock”，不能沿用一对一场景的 duplicate assignment 判据。

这些都尚未在 D7 实现。尤其不能通过修改 `png_guidance_delivery` 的 VM/TTC 公式代替联盟避碰层。

### 6.3 终端切换同步

每个成员仍需独立满足现有条件：D5 `locked`、D3 plan/version/owner 一致、D4 action 允许、视觉质量和机动裕度 gate 通过。协同模式不能要求“任何一个成员 locked 就让全联盟进入视觉 PNG”。建议的研究语义是：

- `all-ready simultaneous`：所有 primary 在超时前 ready，才发布共同切换 epoch。
- `partial-ready hybrid`：未 ready 成员转 reserve/下一波，ready 成员按新版本执行。
- `stale/mismatch`：任何成员不得使用过期 coalition epoch 或改绑目标。

D4 正在 `request_center_replan/degrade_to_secondary/degrade_to_distributed` 时，现有 D7 视觉 PNG 阻断规则保持不变。

## 7. 与协同定位的关系

多架拦截无人机可以协同定位同一目标，但它属于 D1/D2/D5 主责，D7 只是状态消费者。可用信息包括多平台 bearing、bbox 中心和面积变化、已知相机内外参、平台 NED 位姿、时间戳和各观测协方差。必要条件为：

- `measurement_timestamp` 与 `arrival_timestamp` 分离，能够补偿异步观测。
- 各平台位姿和相机外参已标定到共同 NED frame。
- 多视线有足够基线和交角，避免近共线几何退化。
- D2/D5 能确认多平台观测对应同一中心拥有的 `global_track_id`。
- 融合考虑公共先验和交叉相关，不能把相关观测当独立信息重复计数。

协同定位可以降低 time-to-go 和预测拦截点的不确定性，但不能替代 D3 联盟分配、D4 计划所有权、D5 身份确认或 D7 碰撞规避。

## 8. 对 MSM/D7 的分级结论

### 8.1 成熟默认

- 单成员中段 Radar PN 和末端视觉 PNG 继续作为 D7 默认基线。
- 所有成员继续使用中心拥有的 `global_track_id`、版本化 D3 binding 和现有 D4/D5 gate。
- 多资源同目标时，每个 pair 必须保持独立 filter/state；这是必要基础，但不是协同导引本身。

### 8.2 可插拔升级

- 两阶段 cooperative guidance：先协调 time-to-go，再回到成员级 PN。
- leader-follower 或中心广播共同 arrival window，适用于中心/二级节点健康时。
- 预先计划的不同 arrival window，适用于序贯和通信退化场景。

### 8.3 研究方案

- 分布式 finite/fixed/prescribed-time consensus。
- event-triggered/intermittent-communication cooperative guidance。
- impact-angle/LOS-sector-constrained simultaneous arrival。
- 联盟级碰撞避免、成员失效后重新协商 arrival window。
- `2 primary + 1 reserve` 或 `2 simultaneous + 1 delayed` 混合策略。

### 8.4 无成熟开源实现

- 没有发现可直接进入 MSM 默认主线的 cooperative PN/ITCG Python 库。
- 没有发现同时支持多旋翼动力学、协同到达、D3/D4/D5 版本合同和安全避碰的实现。
- 序贯/混合策略没有统一开源控制律，需要 D3 调度与 D7 导引分别研究。

### 8.5 本项目当前状态

已实现：

- 任意 N 个 assignment pair 的独立 PN/PNG runtime state。
- 每 pair 独立视觉 filter、terminal latch 和 D3/D4/D5 gate。
- PN/Pure Pursuit/PNG VM/PNG TTC 单 pair 对照和 SimpleFlight 消费接口。
- 中心化 coalition binding/runtime 字段，以及 primary/reserve/retry、wave、arrival window、activation 和 plan/track/coalition version gate。
- D4/main 已接入 fallback 原子 commit；D7 对 `committed|executing`、lease、epoch、版本和 required ACK 做 commit-aware gate。缺 ACK、`reconfiguring|aborted`、过期 lease、旧 epoch/version、replan/degrade/pending 均 fail closed，no-change ACK 转为 `continue_center` 后仍执行 D5 gate。
- 默认 coalition scope 下的 D5 coalition visual completion，以及所有 scope 共用的 D3/D5 plan/track/coalition version fail-closed 门控；显式 per-primary scope 仅取消共同视觉完成/到达要求。T001 primary 独立切换、T002 k=1、standby reserve 和新版本 activation 均有回归。
- main 已将 D5 coalition visual summary 接入 D7：当前 M=5/N=2 ComputerVision 10-seed 达到 8/10 双 primary 合同验收。历史基线 seeds 7/17/27 的 T002 4/5/4 帧、T001 双 primary 0 共识记录只作早期接线证据，不能替代当前结果，也不证明物理协同拦截。
- D7 已实现 fallback 原子提交的被动消费 gate，D4/main 已完成 commit-aware 消息接线；二级接管、完全分布式和缺 ACK 故障注入分别验证 committed/executing 与 fail-closed。D7 仍不形成联盟、不选成员。
- N/M binding topology helper 已接入 main AirSim 流程；当前 M=5/N=2 形成 T001 两个 active primary、一个 standby reserve，T002 一个 active primary，第五个资源未分配。
- D7 已新增被动协同导引诊断/候选预筛接口：可按任意 primary 数输出 pair 六阶段漏斗、第二 primary 失败阶段、arrival-window error、closest approach、member separation 和 coalition arrival spread，并携带 D3 handoff range/arrival-window width/sector separation candidate metadata。该能力用于定位和筛选 main 后续 sweep，不是 impact-time consensus 或协同控制律。
- D7 已在本地 `188 passed` 回归中关闭末端状态/指标语义、导引律执行语义及 pair 首失败诊断接口；main/D6 canonical actual 五层也已独立 `available`。future multi-seed/dropout/candidate 继续保持同一 state instance，pair 漏斗的 range、measured lock、camera/LOS/closing/maneuver 覆盖作为 P1 标定，不改变 coalition gate 或 PN/PNG 控制律。

未实现：

- 一个 `global_track_id` 对应多个成员时的共享 consensus/clock state；现有 filter/latch 仍按 resource-target pair 独立。
- arrival window 已作为 gate 消费，但共同 time-to-go consensus 和 impact-time control 未实现。
- leader/neighbor cooperative guidance message。
- 成员间预测距离、终端扇区、impact-angle 和碰撞规避 gate；当前只被动记录 main 提供的实际 member separation/safety evidence。
- 物理协同拦截证据仍不足：2026-07-14 actual-v2 M5N2 seed-1 的 active pair 为 `2/3`，但第二 primary 最近约 `11.02 m`、coalition `0/1`，且视觉控制/mode switch 为 0。它关闭 canonical P0 证据链，不关闭多 seed 物理 coalition P1；早期 15 秒 0/30 active-pair 诊断仅保留为历史断点。
- 成员掉队、失联或 D5 未锁定后的联盟重构由 D4/main 产生新 commit/version；D7 已能阻断 `reconfiguring/aborted`，但不自行重构联盟。

## 9. P0/P1 建议

### P0

本次调研没有发现新的 D7 P0 运行断链。现有一对一和 N-pair 独立执行链应保持回归：D7 不分配、不授权、不改写 `global_track_id`，D4 降级/重规划期间继续阻断视觉 PNG。

### P1（当前项）

当前 P1 明确收敛为：M5N2 第二 primary 末端检测/锁定与 5 米闭环；PN/Pure Pursuit/PNG-VM/PNG-TTC 同几何 multi-seed；真实 dropout/candidate 配对；控制延迟；pair funnel、closing speed、三维几何与平台机动标定。未激活 reserve 必须继续 standby，不能用 target `2/2` 或 CV 合同验收替代 coalition 物理评分。

以下均为后置研究，不列当前 P1：cooperative guidance 与 independent multi-pair 的新边界实现；同一目标多成员的同步 ITCG、序贯/混合 point-mass 对照；终端扇区、impact angle、同步到达离散、通信一致性与协同避碰；3D PN、True PN、APN、FRPN 在线化。现阶段只保持已接线的 coalition/arrival-window/wave/role/commit 合同，D7 只消费，不决定联盟。

### P2 optional benchmark

3D PN、True PN、APN、FRPN 的隔离式离线质点对照已实现，replay 只作为可选输入接口；不修改位置 PN 与 `png_guidance_delivery` VM/TTC 核心公式，也不进入默认 SimpleFlight runtime。当前 FRPN 是明确标记的鲁棒增益调度研究近似，不代表成熟 cooperative FRPN；该单拦截器 P2 benchmark 也不实现 coalition impact-time consensus。

## 10. 检索与访问说明

- 检索日期：2026-07-11。
- 使用来源：DOI/Crossref、OpenAlex、Semantic Scholar 元数据、arXiv API、GitHub API/仓库原始 README 与 LICENSE。
- Google Scholar：仅作为计划中的发现入口，本环境未使用其搜索摘要作为证据；最终引用均回到 DOI/出版社或仓库原始页。
- Web of Science：当前环境没有机构订阅或导出文件，未声称完成 WOS 被引网络审计。OpenAlex/Semantic Scholar 的引用计数只用于辅助筛选，未作为算法正确性依据。
- arXiv：该专题在 arXiv 的直接覆盖和查询精度有限；本报告以已发表同行评审论文为主，没有用不相关搜索结果补数量。
- 开源状态可能变化；无许可证按当前仓库状态判定为不可直接复用。

## 11. 最终建议

针对“高威胁目标需要三架无人机”的下一阶段，不应直接把 D7 的三个独立 PNG 控制器同时打开。推荐先把任务语义分成：

```text
simultaneous: 共同 arrival window + 不同 terminal sectors + collision gate
sequential:   不同 arrival windows + 首批结果驱动新 plan version
hybrid:       primary group + delayed reserve/observer + explicit continuation rule
```

第一研究基线建议采用混合模式，并同时保留独立 PN 和全同步 ITCG 作为对照。只有在共同到达时间可达、通信/时钟可靠、终端扇区明确且成员间距可证明满足时，才允许三机同步进入终端。否则应使用序贯或混合方式。当前交付只把中心化版本/角色/波次/时间窗/激活语义固化为视觉 PNG 前置 gate，不代表 cooperative guidance 已成为本项目成熟默认方案。
