# D4 M 对 N 分布式联盟形成与降级接管调研

**调研日期**：2026-07-11
**范围**：中心 C2、二级侦察节点和完全无中心三种运行层级下，面向 `k_j > 1` 协同任务的联盟形成、通信、一致性、成员退出和中心恢复。
**模块边界**：D4 研究“谁组成联盟、谁协调、何时重构以及如何保持版本一致”；D3 拥有中心化资源分配，D7 拥有到达时序和导引，D5/D2 提供身份与关联证据。本文不运行 AirSim；2026-07-11 已在调研结论上补充第一阶段 fail-closed 安全实现。

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

### 已实现且应保留

- 中心/二级/完全无中心降级顺序。
- heartbeat、coverage、lease、epoch、source、readiness 和中心恢复基础审计。
- 单 owner `TrackSummary` 的轻量 CBBA、通信轮次/字节/冲突统计。
- 成员级 D5 视觉风险对 bid 的保守加权。
- `CoalitionSafetyEvidence` 对 D3 schema v2 的中心联盟做 demand/member/plan version/coalition version 校验，并序列化给 main/D6/D7。
- 中心有效且联盟合法时允许中心路径继续；若 arbiter 候选 secondary/distributed 且原子 coalition fallback 未形成，则中心可用时 `request_center_replan`、中心不可用时 `coalition_fallback_unsupported`/`hold_or_revoke`；event 保留 candidate/gated action，`k_j>1` 不进入 single-winner CBBA。
- 合法联盟内授权多资源锁同一 `global_track_id` 不算 duplicate；联盟外/超额成员和旧 plan/coalition version fail closed。

### P1 缺口

- 第一阶段已读取 coalition id、target demand、member role 和双版本，但尚未实现 timing feasibility、ACK bitmap 和完整 coalition lifecycle。
- 完全无中心路径不能对 `k_j=3` 形成原子联盟，也没有缩编/补位/重组状态机。
- 二级接管 metadata 只证明 coordinator/plan 接管，尚未证明联盟成员计划完整接管。
- 中心恢复只比较 assignment owner，未比较 coalition digest、成员执行前缀、波次和 reserve 状态。
- D6 现有 completion/conflict 指标没有区分“目标被一个资源覆盖”和“目标需求被完整联盟满足”。

### P2/P3 保持项

- 外部 CCBBA/CBGA/auction/CNP adapter 和同预算 benchmark。
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
