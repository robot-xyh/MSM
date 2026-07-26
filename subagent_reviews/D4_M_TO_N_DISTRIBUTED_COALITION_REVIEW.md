# D4 M 对 N 分布式联盟形成与降级接管调研

## 2026-07-26 区域学习与联盟证据边界

联盟 ACK 完整只能证明同一计划和联盟代次获得成员共识，不能证明 D4 学习候选产生了该计划。正式学习准入还必须把候选身份、区域建议、严格更新的 D3 计划、运行消费 ACK、成员 ACK 和采用后物理状态窗串成同一条内容寻址链。

现有 nominal 20-seed 候选采用为 0/20；`active_risk` 20-seed 虽有 188/188 隔离区域执行证据记录和 20/20 描述性物理比较，但所有 treatment 都是 `d4_development_candidate_not_admitted` 后的规则回退，D4 候选采用仍为 0/20。两类证据均不能用于 A2/C1/F1。D4 v2 writer 已固定为 development/shadow-only，后续 promotion 只能生成新 bundle，不能改写旧 manifest。

## 2026-07-25 异步确认实施状态

M 对 N 联盟确认已从“同一快照提供全部 ACK”改为“按网络到达跨快照累积”。提案和部分 ACK 保持 `collecting_acks`，完整必要成员集合到达后才原子 `committed`。普通快照不再隐式结束确认窗口；显式截止、租约到期、分区、联盟摘要冲突和成员不可执行仍失败关闭。

陈旧或无效 ACK 不进入成员位图，当前快照不授权执行。后续合法 ACK 可以在同一有效代次继续收集。通信因果门负责在业务 ACK 建立前拒绝旧 partition generation、晚到和无有效投递回执。2026-07-25 新增 5 项异步回归，三文件专项 97/97、D4 全量 569/569。验收阈值为完整 ACK 前零授权、三成员完整后一次提交、负例零授权。

模块状态机缺口已关闭。main-owned 2 目标、4 资源、1 个二级侦察节点的单随机种子三维场景也已复跑：随机种子 `1271` 下，单目标 3 成员先保持 0/3 ACK，随后 3/3 ACK 原子提交；两个主成员释放，备用成员待命。自主补位、到达窗口可达性、完整 CCBBA、真实 AirSim 多随机种子和正式规模矩阵仍是 P1/P2，不得由单随机种子质点结果替代。

**调研日期**：2026-07-11
**范围**：中心 C2、二级侦察节点和完全无中心三种运行层级下，面向 `k_j > 1` 协同任务的联盟形成、通信、一致性、成员退出和中心恢复。
**模块边界**：D4 研究“谁组成联盟、谁协调、何时重构以及如何保持版本一致”；D3 拥有中心化资源分配，D7 拥有到达时序和导引，D5/D2 提供身份与关联证据。本文不运行 AirSim；2026-07-11 已在调研结论上补充第一阶段 fail-closed 安全实现。

**2026-07-25 成员 ACK 通信证据边界**：`CoalitionMemberAck` 的内容门控继续保持，但成员自报 ACK 不再足以证明通信完成。D4 新增 `d4.coalition_member_ack.v1` delivered-receipt 合同，要求 envelope/payload 中的 member source、coordinator destination、authority、plan version、epoch、lease、partition generation、message ID 和 payload SHA-256 全部一致，并在决策时刻前实际到达。精确重复仅作幂等处理，冲突重放、旧代次、晚到和无回执均失败关闭。因果证据专项 56/56 通过；main 已完成通信队列接线、通信禁用负例和随机种子 `1271` 的异步三成员正例。加入异步联盟回归后 D4 全量为 569/569；AirSim 多随机种子和真实网络复跑仍待完成。

**2026-07-22 配对干预与联盟边界同步**：保留 seed 1000-1019 的规则 control/候选 treatment 继续复用 `coalition_ack_complete`、owner/plan/version/epoch/lease 和 fault fence；当前权威 `formal_7891296` 绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`。D6 独立重算确认 20/20 source clean/finite、truth=0、candidate considered 20/20。20 个候选 confidence min/mean/max 为 **0.508892953/0.563426384/0.569492280**，在未下调的 `minimum_confidence=0.6` 下通过 **0/20**；OOD、latency、finite、failure gate 各 **20/20**，aggregate **0/20**，safe adoption **0/20**，规则回退 **20/20**。执行时延 nearest-rank P95 为 **2.241315 ms**，门控汇总线性插值 P95 为 **2.264415 ms**。D6 profile-bound v2 sidecar 位于 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，状态 `pass_offline_assignment_comparison_only`，文件/内容 SHA256 为 `f3852251...1c3b`/`c02a345c...5d2d`。availability sidecar 已存在不代表联盟成员 ACK 或物理结果存在；runtime ACK、成员级 post-intervention outcome、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍不可用。专项现为 **33/33**、D4 全量 **482/482 passed**。隔离加载器继续只读校验冻结 bundle，raw candidate 仍须通过原确定性投影和 next-cycle gate；`formal_twenty_seed_performance_completed=false`，该 nominal 5v5 只证明门控/回退，不形成或改写联盟，不开放 PPO、assist 或 authority。

**2026-07-21 区域 reward 与联盟边界同步**：新增结果窗口合同要求窗口内 coalition binding 首尾哈希一致，否则区域 reward 失败关闭。这个校验用于防止把联盟重构前后的结果合成一条样本；它不验证 required member ACK，也不把稳定 coalition hash 解释为联盟已执行。新执行计划的区域 reward 仍是非因果时间窗口观测，同代评估刷新没有动作 reward。新增专项 19/19、D4 全量 449/449；真实联盟 paired shadow、成员级物理结果和 on-policy evidence 仍未完成。

**2026-07-21 运行时确认边界同步**：`d4-region-resource-runtime-ack-evidence-v2` 区分新执行计划采纳和同代评估刷新采纳。后者要求前序与当前资源-目标 binding、coalition ID/version 和 member role 完全一致，因此只能证明区域建议在既有联盟上被评估采用，不能证明联盟形成、成员 ACK 或执行状态变化。真实 main 5v5 刷新集成与篡改专项 5/5，运行时专项合计 33/33，该阶段 D4 全量 430/430；当前为 482/482。该证据不是 `CoalitionMemberAck`，不能证明物理执行或策略收益；冻结 900 episode 仍没有对应 runtime 字段，PPO、assist 和 authority 保持关闭。

**2026-07-20 区域建议边界同步**：新增全局区域资源建议层不改变联盟形成职责。`RegionResourceSnapshot` 只保留需求/积压和资源/通信/authority 的区域聚合，不含 actor truth ID、目标 ID、成员列表或 resource-target assignment；建议只调整区域 quota、邻边 transfer、备用、侦察和 hold/replan。formal committed member、owner/epoch/lease、fault fence 和 ACK 由确定性投影保护，学习策略不能形成/解散联盟或替代 D3 assignment。`d4-region-resource-advisory-v1` 仅把后投影区域建议固化为内容寻址、限时、逐 generation 可审计的下一轮规划输入；消费门重验 current snapshot/plan/epoch/lease/ACK/fault、守恒、邻接/容量和 replay，不输出 formal coalition 的 member/target identity。规则与学习共享同一 projector。原共享图/BC/PPO/bundle/shadow 管线 32/32，新增消费合同后该阶段专项 47/47、D4 全量 350/350；新增 15 项为无随机 seed 的 Python 合同测试，不是联盟形成、正式多 seed、AirSim 或真实网络证据。少于 20 个实际未见 seed 不得 assist。

**2026-07-20 episode 数据合同边界同步**：`d4-region-learning-dataset-v1` 只保存 truth-free 区域快照、区域级 target/reward availability 和可选 recommendation，不保存联盟 target truth、evaluator truth 或成员级 assignment。训练 target 复核 projector/authority/edge，manifest 复核 inventory/split；该阶段数据合同 13/13、D4 全量 365/365，共享切分阶段为 381/381，课程阶段为 387/387，全样本准入阶段为 397/397，运行时确认阶段为 430/430，候选门诊断阶段为 482/482，当前全量为 569/569。上述数据治理和证据合同都不改变联盟形成、`CoalitionMemberAck`、CBBA 或恢复逻辑，也不是联盟算法或性能证据。

**2026-07-20 main 质点接线事实**：单一二级、多二级区域 owner 和中心/二级连续失效后的 distributed D3 plan 已进入 main-owned scalable 3D 质点模块栈，D7 按 owner/epoch/lease/commit/fault fence 执行；定向测试 8/8。该事实不是 AirSim、真实网络、完整 CCBBA 或自主重构证据。

**2026-07-20 区域合同同步**：`regional_failover.py` 已把中心 -> 机动高空二级 -> distributed 顺序扩展为逐区域 authority，并仅为无有效二级节点的区域加入能力/跨区域 capacity 受约束 bid selection。该 selection 从动态 member/task 集合形成候选，允许单成员覆盖多项 capability，D5 support/hold/ambiguity 参与排序或排除；中心、二级和 distributed 的 `k_j>1` 候选都必须全部 required ACK、current plan/coalition version、epoch 和最早 lease 后原子 `committed`。commit metadata 依次标记 `d3_center_assignment`、`d3_assignment_secondary_coordination`、`bounded_constrained_bid_selection`。23 项区域测试使当时 D4 全量达到 303/303，后续数据合同阶段为 365/365、运行时确认阶段为 430/430、候选门诊断阶段为 482/482，2026-07-25 当前为 569/569。该增量不实现 CBBA 多轮消息共识、全局组合最优、CCBBA coupled timing、reserve 激活或在线成员重构；main 已有单随机种子质点因果接线，仍无 AirSim 多随机种子、真实网络或物理证据。

**2026-07-15 历史合同同步**：secondary coordinator proposal 与两个公开 secondary plan helper 均已 fail-closed；helper active/maintained 路径要求 readiness exact-true、expected/actual source、plan/required lease epoch 和严格未过期时间证据。此前 278/278 不含 helper 的逐字段 `None`，不能证明全部公开入口；当日 280/280 已补齐，候选门诊断阶段全量为 482/482，2026-07-25 当前为 569/569。distributed peer commit 继续只受 member/双版本/epoch/lease/digest/partition 合同约束，不套用二级视觉门。

## 1. 问题定义与关键结论

设资源集合为 `R={r_i}`，目标集合为 `T={t_j}`，目标 `t_j` 的最低协同需求为 `k_j`，联盟为 `C_j subseteq R`。一个可执行联盟至少满足：

```text
|C_j| >= k_j
capability(C_j) >= required_capability_j
arrival(C_j) satisfies the assigned time-window policy
all members agree on coalition_id / target_id / plan_version / epoch
```

高威胁目标取 `k_j=3` 时，问题已不再是普通 CBBA 的“一任务一个 winner”。把同一目标简单复制成三条独立任务会产生三个严重问题：无法保证三条任务属于同一联盟、无法原子地判断能力和到达窗口是否满足、成员退出时无法避免部分旧任务继续执行。因此需要 **coalition/coupled-task allocation**，而不是把现有 single-winner CBBA 重复运行三次。

调研结论：

1. **成熟默认**：中心正常时，由 D3 的中心化容量/需求分配生成联盟；D4 只维护健康、lease、epoch、成员状态和降级仲裁。这仍是当前最稳妥路线。
2. **二级节点接管**：二级节点有区域态势和可靠链路时，可承担区域 coalition coordinator，但必须接收完整联盟摘要并发布新版本，不能沿用只含单 owner 的 fallback assignment。
3. **完全无中心**：基础 CBBA 是成熟研究基线，但不原生支持 `k_j>1` 的原子联盟。CCBBA、consensus-based grouping、分布式 coalition formation 是可选研究路线，公开实现成熟度不足，尚无可直接替换 MSM D4 的工程级库。
4. **同时或分批不是 D4 单独决定**：D4 负责把 `simultaneous | sequential | mixed` 和时间窗写入联盟合同；D7 判断运动学可达性并执行导引，D3计算全局资源代价。
5. **成员退出必须分级处置**：剩余成员仍满足最低数量和能力时可缩编；有满足窗口的预留成员时补位；否则整个联盟进入新 epoch 重组。不能只删除失效成员并让旧计划继续有效。

## 2. 三类时序策略在 D4 中的含义

| 策略 | 联盟合同 | D4 的职责 | 主要适用条件 | 主要风险 |
|---|---|---|---|---|
| 同时到达 | 所有主成员满足共同窗口 `[tau-delta, tau+delta]` | 保持完整成员集合和共同 `arrival_window_id`；任何关键成员退出均重新验证整个联盟 | 任务确实依赖协同到达、通信和时钟质量高、成员机动裕度足 | 最慢成员拖累联盟；成员退出导致整体失效；碰撞/相互干扰风险高 |
| 分批到达 | 成员属于有序 `wave_id`，每波有独立窗口 | 维护波次顺序、每波最低需求和补位规则；已执行波次不可被旧 plan 回滚 | 资源有限、需要先探测/确认后补位、同时到达不可达 | 前波结果延迟导致后波计划过时；跨波重复 owner |
| 混合 | 首批 `k_primary` 同时，后续为 reserve/confirm/retry 波次 | 同时维护 primary coalition 和 reserve pool；依据 D5/D2 反馈激活后续波次 | 高威胁目标、关联/定位仍有不确定性、需要容错 | 合同和恢复合并更复杂；预留资源降低其他目标覆盖 |

没有文献支持“所有高威胁目标默认必须三机严格同时到达”这一普适结论。D4 推荐把混合作为后续研究默认：主联盟满足最低协同需求，至少一个资源可配置为 reserve；只有任务模型明确要求共同时间窗时才使用严格同时模式。

## 3. 中心、二级节点与完全无中心的任务分层

### 3.1 中心正常

- D3 形成 `coalition_id -> target_id -> member/resource roles -> timing policy` 的版本化计划。
- D4 监控中心健康和联盟执行证据，不运行另一套分布式分配与中心争权。
- D4 只在成员失联、计划 stale、D5 目标不一致或协同窗口不可达时请求中心重规划。

### 3.2 中心失效、二级节点可用

- 二级节点应缓存最近的 target demand、联盟成员、能力、时间窗、D2/D5 绑定和 plan digest。
- 接管必须生成新的 `plan_version/epoch/lease`，并声明 superseded center plan。
- 若只失去一个成员，二级节点优先在同一区域 reserve pool 中补位；不能补位且剩余成员低于最低需求时，撤销旧 coalition lease 后重组。
- 二级节点只能协调其 coverage cell 内的联盟；跨区域目标必须请求其他二级节点协作或降到完全无中心。

### 3.3 中心和二级节点均不可用

完全无中心模式需要把普通 `winner_by_task` 扩展为对以下状态达成一致：

```text
coalition_id
target_global_track_id        # 只复制上游 ID，不重写
required_count / min_count
required_capabilities
member_ids and member_roles
timing_policy / arrival_window / wave_id
coalition_epoch / lease_expiry
member_ack bitmap
formation_state: proposed | forming | committed | executing | reconfiguring | released
```

只有在成员数量、能力、时间窗和 ACK 同时满足后才可 `committed`。网络分区时，同一 target/epoch 只能保留可证明持有有效 lease 的 coalition；无法消解时进入 hold/observe，不发布两个并行联盟。

## 4. 成员退出、缩编、补位与重组

成员退出可由 heartbeat stale、链路分区、资源故障、D5 friend/identity conflict、D7 不可达或 operator hold 触发。

| 条件 | 默认动作 | 版本语义 |
|---|---|---|
| 剩余成员数和能力仍满足 `min_count/min_capability`，且时间窗仍可达 | 缩编继续 | 新 coalition version；旧成员 lease 作废 |
| 有 reserve，reserve 可在剩余窗口内加入且不会破坏其他高威胁任务最低覆盖 | 补位 | 同 coalition id、新 version/epoch；全成员重新 ACK |
| 低于最低数量、丢失关键能力或同步窗口不可达 | 释放并重组 | 原 coalition 状态置 `released/failed`；新 coalition id 或新 epoch |
| 已有波次开始执行 | 不回滚已完成波次；只重排未执行波次 | 记录 immutable execution prefix 和新 suffix version |
| 网络分区后出现两个成员视图 | 比较 lease epoch、plan version、target binding 和 quorum；无法唯一裁决则 hold | 禁止按本地观测自行合并或改写 `global_track_id` |

CBBA-PR 的“部分释放 bundle 后缀”可作为动态补位的研究参考，但它解决的是在线新任务和部分重规划，不等价于原子联盟重构。联盟成员变更仍需全体确认共同 coalition digest。

## 5. 文献证据

下表以 2015-2026 年为主，并保留 CBBA、CCBBA、合同网等奠基文献。`时序` 表示论文任务模型是否显式支持同时/序贯；“未规定”不能被解读为支持同时到达。

| 年份 | 文献与原始来源 | 问题/方法 | 中心性 | 时序 | 验证与代码证据 | 对 MSM 的意义 |
|---:|---|---|---|---|---|---|
| 2009 | Choi, Brunet, How, *Consensus-Based Decentralized Auctions for Robust Task Allocation*, [DOI](https://doi.org/10.1109/TRO.2009.2022423) | CBAA/CBBA，winner/bid 共识，证明冲突消解和性能界 | 分布式 | 序贯 bundle；非联盟同时到达 | 数值仿真；MIT 提供 MATLAB 基线包 | 完全无中心 single-winner 默认研究基线，不原生支持 `k_j>1` |
| 2011 | Whitten et al., *Decentralized Task Allocation with Coupled Constraints in Complex Missions*, [DOI](https://doi.org/10.1109/ACC.2011.5990917) | CCBBA，引入 assignment relationship 和 temporal constraint，比较 pessimistic/optimistic bidding | 分布式 | 支持任务间时序/耦合，但不是现成三机拦截协议 | 仿真；无作者官方可运行仓库被确认 | `k_j>1` 联盟和波次约束的重要算法依据 |
| 2014 | Hunt et al., *A Consensus-Based Grouping Algorithm for Multi-agent Cooperative Task Allocation with Complex Requirements*, [DOI](https://doi.org/10.1007/s12559-014-9265-0) | 多智能体共同完成单任务，考虑异构能力、依赖和动态需求 | 分布式 | 未规定严格同时到达 | 仿真；未确认官方代码 | 比普通 CBBA 更直接对应 coalition formation，但工程代码不足 |
| 2017 | Guerrero, Oliver, Valero, *Multi-Robot Coalitions Formation with Deadlines*, [DOI/全文](https://doi.org/10.1371/journal.pone.0170659) | 联盟任务、deadline、物理干扰、ILP 最优条件和启发式比较 | 以全局优化/拍卖比较为主 | deadline；考虑多机器人同时占位干扰 | 仿真/复杂度分析；无配套仓库 | 说明同时协同必须计入空间干扰，且问题一般具有组合复杂度 |
| 2018/2019 | Buckman, Choi, How, *Partial Replanning for Decentralized Dynamic Task Allocation*, [arXiv](https://arxiv.org/abs/1806.04836), [DOI](https://doi.org/10.2514/6.2019-0915) | CBBA-PR，释放 bundle 后部以响应在线任务，降低重规划通信 | 分布式 | 序贯任务 | 多 UAV 仿真；无官方代码被确认 | 成员退出后的局部重规划参考，不足以替代 coalition commit |
| 2019 | Yan et al., *Real-time Task Allocation for a Heterogeneous Multi-UAV Simultaneous Attack*, [DOI/全文](https://doi.org/10.1360/N112018-00338) | CNP 联盟形成结合协同路径规划，显式考虑目标资源需求和同时到达 | 合同网分配+协同规划 | 同时到达 | 仿真，与 PTCFA 比较；无公开代码被确认 | 说明“联盟分配”和“同时到达路径”必须联合验证；不是可直接复用实现 |
| 2020 | Ye et al., *Decentralized Task Allocation for Heterogeneous Multi-UAV System with Task Coupling Constraints*, [DOI](https://doi.org/10.1007/s11227-020-03264-4) | 异构多 UAV、任务耦合约束的分布式分配 | 分布式 | 耦合时序，具体由任务模型决定 | 论文仿真；无公开官方仓库被确认 | CCBBA 类升级路线，适合表达能力互补和任务依赖 |
| 2020 | Zitouni et al., *A Distributed Approach ... Using CBBA and Ant Colony System*, [DOI](https://doi.org/10.1109/ACCESS.2020.2971585) | ACS 构造 bundle、共识消冲突，优化 makespan/距离/消息数 | 分布式 | 序贯任务 | Java/JADE 仿真；论文未给出可核验公共仓库 | 可作同预算通信/质量对照，不是联盟原子提交实现 |
| 2021 | Mazdin, Rinner, *Distributed and Communication-Aware Coalition Formation and Task Assignment in Multi-Robot Systems*, [DOI](https://doi.org/10.1109/ACCESS.2021.3061149) | 分布式联盟形成，比较 event/time/hybrid communication，研究故障下一致性 | 分布式，并与中心化比较 | 未限定；任务需求驱动 | ns-3 仿真，多网络条件；未确认公开代码 | 最直接支持 D4 的 coalition+通信+故障研究；事件触发通信可降低开销但仍需一致性验证 |
| 2021 | Raja, Habibi, How, *Communication-Aware CBBA*, [DOI](https://doi.org/10.1109/ACCESS.2021.3138857) | 深度强化学习调度 CBBA 消息，缓解带宽、碰撞和 hidden-node 问题 | 分布式 | 沿用 CBBA 任务模型 | 多场景仿真；`mit-acl/CACBBA` 只有 README，未公开源代码 | 只能作为通信调度研究证据，不能作为现成依赖 |
| 1980 | Smith, *The Contract Net Protocol*, [DOI](https://doi.org/10.1109/TC.1980.1675516) | announce-bid-award 的经典分布式任务协商 | manager/contractor 分布式 | 可表达动态任务，但时序由合同定义 | 原理和案例；无现代可直接接入实现 | 二级节点有临时 manager 时易解释；manager 失效必须另有共识/重招标机制 |

补充综述依据：2023 年 MRTA 优化综述 [DOI](https://doi.org/10.1016/j.robot.2023.104492) 和 2025 年动态多 UAV 分配综述 [DOI](https://doi.org/10.3390/drones9010075) 可用于算法分类，但不替代上述原始算法论文。

## 6. 开源代码真实性与成熟度审计

审计时间为 2026-07-11。GitHub `updated_at` 可能因访问、issue 或元数据变化更新，维护状态以下表的 `pushed_at`、仓库内容、许可证和测试资产为准。

| 项目 | 真实性/许可证/维护 | 实际能力 | `k_j>1` 适配结论 |
|---|---|---|---|
| [MIT ACL CBBA MATLAB archive](https://acl.mit.edu/files/CBBA_MATLAB_ACLMIT_July13_2010.zip) | MIT ACL 官方项目页提供；2010 MATLAB 源码；压缩包未见 LICENSE，授权范围需另行确认 | 基础 CBBA bundle、communicate、scoring 和示例 | 可信基线但只解决普通 CBBA；无 coalition commit、成员 ACK、lease、退出重构 |
| [zehuilu/CBBA-Python](https://github.com/zehuilu/CBBA-Python) | 个人实现，MIT License；最后代码推送 2021-04-22；有 `test/` 示例但不是持续集成的工程测试套件 | Python/Numpy，异构 agent/task、任务 time window、路径和 bundle 示例 | 适合算法对照和 adapter 原型；一任务一个 winner，不能直接表达三机共同满足一个目标 |
| [seo2730/CCBBA-J_based](https://github.com/seo2730/CCBBA-J_based) | 个人 MATLAB 研究代码，MIT License；最后提交 2020-09-23；仓库很小，无 CI/系统测试证据 | README 称 CCBBA；提交记录含 temporal constraint、mutex 和 transit problem | 可验证 coupled constraint 思路，但不是通用 coalition 库，不应直接进入主线 |
| [mit-acl/CACBBA](https://github.com/mit-acl/CACBBA) | MIT ACL 组织仓库；截至审计日只有一行 README，无 LICENSE、无源码，`size=0` | 声明为 CA-CBBA 官方实现，但没有可运行内容 | **不可作为开源实现**；只能引用论文，不列为可接入依赖 |
| [Dymsia/CNP_CBBA-](https://github.com/Dymsia/CNP_CBBA-) | 个人 MATLAB/R 课程/演示型仓库；无许可证；最后代码推送 2019-09-10 | CNP、CBBA、时间窗和优先约束的报告/演示 | 可辅助理解协议，因无许可证、无维护和无联盟合同，不能复用到 MSM |

已核验并纠正两条历史说法：`github.com/mit-acl/cbba-python` 返回 404，CBBA-Python 不是 MIT 官方仓库；曾提及的 `CBBA-CPP` 地址也返回 404。后续文档不得继续将它们写成可用官方实现。

## 7. 方案分级

### 7.1 成熟默认方案

- 中心正常：D3 中心化需求/容量分配，D4 维护版本化 coalition lifecycle。
- 中心失效、二级可用：二级节点基于缓存态势做区域联盟接管，严格执行 source/lease/epoch/coverage 门控。
- 完全无中心的最低保底：现有轻量 CBBA 可继续承担 `k_j=1` 或“选择联盟协调者/候选成员”的第一阶段，但不能宣称已完成 `k_j>1` 联盟分配。

### 7.2 可插拔升级

- CCBBA/consensus-based grouping：表达 assignment relationship、能力互补和时序耦合。
- CBBA-PR：在成员退出或新目标出现时减少全量重规划，但必须叠加 coalition commit。
- event-triggered coalition updates：网络状态变化时降低消息量，需与固定周期 heartbeat 并存。

### 7.3 研究型方案

- CA-CBBA 的学习式消息调度。
- 联盟形成与同时到达路径/导引联合优化。
- 在网络分区下保持 coalition atomicity 的分布式事务/共识机制。

### 7.4 无成熟开源实现

当前没有发现同时满足以下条件的 Python 工程库：明确许可证、持续维护、支持目标需求 `k_j`、异构能力、同时/波次时间窗、成员退出重构、分区恢复、可测通信开销，并能直接接入 MSM 的 summary bus。该缺口应保持为 P1 研究/合同定义和后续 P2 算法实现，不能用基础 CBBA 仓库冒充已解决。

## 8. 对当前 D4 的差距判断

### 2026-07-11 当前验收状态

D4 所属 P1 合同层已闭合。2026-07-11 ComputerVision 总体验收为 8/10；二级协调者 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing`，完全分布式 `INT-02` peer 以 ACK 3/3 进入 `executing`，确认窗口显式截止后的缺 ACK 场景以 2/3 ACK 进入 `aborted` 并令 T001 三成员 `hold_for_review`。2026-07-25 后，截止前普通快照保持 `collecting_acks`。这些结果关闭了 secondary/distributed commit 正例与缺 ACK fail-closed，不关闭自主成员形成、联盟重构或物理拦截。

SimpleFlight 15 s 仅用于诊断，30 个 active pair 物理命中为 0。2026-07-12 P1 版本化 replay 覆盖旧 epoch、过期 lease、成员不可执行和手工给定替换成员后的重新提交、网络分区/恢复、digest conflict 和中心恢复双轨审计，九场景 9/9 通过；它不实现自主补位。真实 AirSim 的 secondary-interceptor/peer split、误降级、恢复时间和物理连续性矩阵仍开放。

P2 隔离合同 replay 已实现并保持上述边界：member loss/replacement 场景由 replay 手工给定替换成员，再验证版本和 ACK，不代表在线成员选择或自动补位；其余场景逐项输出 round/completion/conflict/gap-or-unavailable。MIT CBBA/CA-CBBA 仅返回 capability/unavailable；没有外部性能结果。

### 2026-07-15 M5N2 中心负对照

最新真实 AirSim M5N2 完成 baseline/candidate 各 10 seeds，共 20/20 case。该批 `active degradation=0`，没有执行二级接管或完全分布式联盟，因此 coalition `0/20` 和第二 primary 5 m `0/20` 只能说明中心计划下的物理协同闭环未完成，不能作为 fallback 算法性能结论。20 个第二 primary 均为 `collision_stop`，但未记录碰撞对象；D4 不根据该单一终态自动降级，仍依赖 D1/D2/D3/D5 证据仲裁。D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`。额外 `png_ttc_2v2_seed001` 排除，dropout case 为 0。

因此真实 secondary/distributed 多 seed 仍为 P1：需在同几何和 seeds 下显式注入中心失效、二级再次失效和可审计主动风险，验证原子 commit、owner/version、误降级、恢复以及物理连续性。

### 历史基线（2026-07-11 最终 P1 验证前）

`blocks_cv_m5_n2_liveness_batch_20260711` ComputerVision 证据中，seeds 7/17/27 均为 6 次中心重规划请求、6 次 no-change ACK、0 applied、0 expired，需求满足率均为 1.0，错误重复锁均为 0；T002 共识帧为 4/5/4，D7 每 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。该批次当时确认 P0 无新增 blocker。随后 D4 完成 `CoalitionMemberAck`、`CoalitionCommitState`、轻量 commit coordinator 和 `CoalitionSafetyEvidence` 原子 fallback 扩展；当时 T001 协同视觉、二级 active plan 和完全无中心 `k>1` 的真实 episode 接线仍列为 P1。该段是最终 3/3、3/3、2/3 验收前的历史基线，不得覆盖上一节当前状态；ComputerVision 证据也不是物理拦截证明。

该历史阶段的后续顺序曾是 P0/本地 ACK-commit 回归、二级 active-plan/commit 正负例、完全无中心三成员真实 episode commit 与网络分区负例、成员退出重构、D6 多 seed 聚合。当前 secondary/peer commit 正例和 missing ACK 负例已由上一节关闭；仍开放的是完整分区/成员重构/恢复矩阵与多 seed 聚合。MIT/CA-CBBA 已有 P2 capability/unavailable 输出，但外部 execution benchmark 尚不可用；auction/contract-net 也未执行，且均不得替换本地轻量 CBBA 默认路径。

### 已实现且应保留

- 中心/二级/完全无中心降级顺序。
- heartbeat、coverage、lease、epoch、source、readiness 和中心恢复基础审计。
- 单 owner `TrackSummary` 的轻量 CBBA、通信轮次/字节/冲突统计。
- 成员级 D5 视觉风险对 bid 的保守加权。
- `CoalitionSafetyEvidence` 对 D3 schema v2 的中心联盟做 demand/member/plan version/coalition version 校验，并序列化给 main/D6/D7。
- 中心、secondary、distributed 三层 `k_j>1` 都只有在 required ACK 完整且 generation/lease 有效后才原子 `committed`；中心和二级审计 D3 给定成员，仅 distributed fallback 形成受约束候选。无有效 commit 时中心可用则 `request_center_replan`、中心不可用则 `coalition_fallback_unsupported`/`hold_or_revoke`；event 保留 candidate/gated action，`k_j>1` 原子联盟不交给 single-winner CBBA。
- 合法联盟内授权多资源锁同一 `global_track_id` 不算 duplicate；联盟外/超额成员和旧 plan/coalition version fail closed。
- center replan lifecycle 已消费 D5 current-coalition summary：只有 track/plan/coalition scope current、全部 primary 稳定 locked、visual consensus 无冲突且 required commit 完整时，旧 soft pending 才输出 no-change/continue；同一 summary 对所有 current primary 产生一致 D4 action。
- main 当前已传递所需 summary。D4 的最小字段是双版本 scope、primary required/locked/complete、consensus/conflict，以及 commit-required 时 state、required/acked IDs、valid/conflict reasons；缺字段不推断 recovery。
- D2 continuous `duplicate_track_risk` 只作为 soft 候选/协方差重叠证据；只有显式 duplicate count/delta/observed flag 才是 hard observed duplicate。该区分防止合法 current coalition consensus 被非事件型 score 错误阻断，同时保留真实重复事件 fail closed。
- scalable3d 区域合同已能按 region、member availability/communication/跨区域 capacity、required capability 和 D5 member evidence 形成 bounded deterministic candidate，并对三层候选执行完整 atomic commit；owner/layer 变更要求 epoch 与 plan version 同时提升，lease 取各上游范围的最早 expiry。

### P1 缺口

- 已读取 coalition id、target demand、member role 和双版本，并实现 required-member ACK bitmap、commit lifecycle、lease/epoch、digest、分区和恢复审计；真实 episode 的二级/peer commit 正例与缺 ACK 负例已通过。模块级分区恢复及手工 member-replacement replay 已版本化，但自主补位未实现；D7 timing feasibility 和真实 AirSim 多 seed 扰动仍开放。
- 完全无中心路径除可对上游给定 `k_j=3` 集合做本地原子 commit 外，现有区域合同还能形成能力/跨区域 capacity 受约束 candidate；但该 region-id 顺序贪心没有全局组合最优，也没有 CBBA 网络图共识、CCBBA 时序耦合、D7 arrival feasibility、reserve 激活、缩编/补位/整盟重组状态机，不能称为完整自主成员形成。中心和二级不运行该 candidate formation，但使用相同的完整 ACK 原子门。
- 二级接管已证明协调者与 required-member 3/3 ACK 可进入 `executing`；该合同证据不等于成员运动学可达或物理拦截完成。
- 中心正常路径的 D5 visual consensus recovery 已校验 current coalition scope 和 primary 集合；中心失效后的恢复仍只比较 assignment owner，尚未比较完整 coalition digest、成员执行前缀、波次和 reserve 状态。
- D6 现有 completion/conflict 指标没有区分“目标被一个资源覆盖”和“目标需求被完整联盟满足”。

### P2/P3 保持项

- 外部 CCBBA/CBGA execution adapter 和同预算 benchmark；当前仅完成 MIT/CA-CBBA capability/unavailable adapter。
- CA-CBBA 学习式通信调度、真实 DDS/mesh 和硬件链路。
- 与真实末端处置、飞控和导引的联合在线优化。

## 9. 后续跨模块接口建议（仅作为调研结论）

D4 后续至少需要从 D3 接收 `target_required_count`、capability demand、timing policy、coalition/member role 和 reserve policy；从 D7 接收每个成员的 time-to-go/arrival-window feasibility；从 D2/D5 接收 target binding 和 identity consistency；向 D6 输出：

- `coalition_formation_time`
- `target_demand_satisfaction_rate`
- `coalition_member_loss_count`
- `coalition_replacement_time`
- `coalition_shrink/reform_count`
- `coalition_digest_conflict_count`
- `simultaneous_arrival_window_feasible`
- `wave_order_violation_count`
- `messages/bytes/consensus_rounds per coalition change`

这些接口不应由 D4 单方面落地；需由 main 协调 D3、D6、D7 共同确定跨模块合同。

## 10. 检索限制

- 本轮可访问 DOI、出版社原始页、arXiv、OpenAlex、MIT ACL 官方页和 GitHub API。
- Google Scholar 仅作为发现渠道，本文没有引用其搜索摘要。
- 当前环境没有 Web of Science 订阅或导出文件，因此没有声称完成 WOS 引文网络/分区核验；后续如需 WOS 证据，应由用户提供导出记录或机构访问。
- “未发现公开代码”表示在本轮检索和论文原始页面中未核验到，不等价于作者绝对没有私有实现。
