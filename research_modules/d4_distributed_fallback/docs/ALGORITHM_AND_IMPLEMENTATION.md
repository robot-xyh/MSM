# D4 算法原理与实施方案

## 1. 模块定位

D4 负责中心 C2 失效后的离线降级协同研究。它不替代 D3 的中心化最优分配，也不直接驱动 D5 的末端视觉锁定；它只在中心失效、信息不完整、通信受限的仿真条件下，维持最低限度的计划连续性，并把所有降级行为记录给 D6 评估。

本模块边界固定为离线科研仿真：只处理粗粒度 `TrackSummary`、`ResourceSummary`、CBBA 状态和审计日志；不实现真实无线链路、飞控接口、硬件驱动、火控参数、毁伤模型、自动处置或授权绕过。

## 2. 输入输出

### 2.1 输入

- `TrackSummary[]`：来自 D1/D2 的全局航迹摘要，字段包括 `track_id`、`coarse_cell`、`age_s`、`confidence_band`、`source_count`、`epoch`。
- `ResourceSummary[]`：来自资源状态管理或 D3 上一版计划的资源摘要，字段包括 `node_id`、`capability_class`、`availability_band`、`comm_band`、`operator_hold`、`takeover_priority`、`lease_epoch`、`node_role`、`coordinator_only`、`coverage_cell`、`epoch`。
- `C2` 健康输入：heartbeat 状态、assignment digest 是否一致、center epoch、peer fail votes。
- `SimulatedNetwork`：内存网络，提供延迟、丢包和消息计数。

### 2.2 输出

- `CBBAResult`：降级分配结果、共识轮数、是否收敛、冲突数、完成率、消息数量和字节估计。
- `HealthTransition[]`：状态转移审计日志。
- `MergeResult`：中心恢复后的双轨合并结果，区分 `accepted/review/conflicts`。
- `final_views["coordination_mode"]`：当前已写入 `state/leader_id/leader_role/coverage_cell`，建议后续在仿真 metrics 中继续透传，便于 D6 区分二级节点接管与完全分布式 CBBA。

## 3. C2Health 状态机

状态定义：

- `normal`：中心 heartbeat、assignment digest 和 epoch 均可信。
- `degraded`：中心质量下降，或已由备份/二级节点维持连续性，但还不能恢复完全中心控制。
- `suspect`：heartbeat 过期、digest 冲突、epoch 倒退、节点投票不一致或恢复尚未通过合并校验。
- `failed`：heartbeat 超过硬超时，或 peer quorum 判定中心不可用。

典型触发条件：

| 转移 | 触发条件 | 设计意图 |
|---|---|---|
| `normal -> degraded` | heartbeat age 超过 `heartbeat_warning_s` | 提前进入谨慎模式，避免突然切主 |
| `normal/degraded -> suspect` | heartbeat stale、digest conflict、center epoch stale | 区分“网络抖动”和“态势不一致” |
| `suspect -> failed` | heartbeat age 超过 `heartbeat_failure_s` 或 peer votes 达到 quorum | 只有明确失效才启动降级规划 |
| `failed -> degraded` | 备份/二级节点/集群代表接管 | 降级接管不等于恢复中心权威 |
| `degraded/suspect -> normal` | 双轨合并无冲突且人工接受标志为真 | 防止短暂 heartbeat 恢复导致双主 |

不能只靠 heartbeat 恢复的原因：

1. heartbeat 只能证明中心节点“还在发送”，不能证明它拥有最新航迹和分配版本。
2. 中心恢复时可能落后于降级期间形成的 peer 计划，直接恢复会造成 stale assignment。
3. 多节点网络可能分区，部分节点看到中心恢复，部分节点仍在降级协商，单次 heartbeat 会形成双主。
4. D3/D5/D6 依赖 `plan_id/version/global_track_id` 连续性，恢复必须比较 digest、epoch 和所有权，再由人工接受标志闭环。

因此 `merge_recovery()` 采用双轨合并：中心计划和 fallback 计划并行比较，完全一致进入 `accepted`，单边出现进入 `review`，重复所有者或版本冲突进入 `conflicts`。只有 `conflicts` 和 `review` 均为空且 `human_accept=True` 才恢复 `normal`。

## 4. 三级降级链路

降级顺序固定为：

```text
中心 C2 正常
  -> 中心 C2 失效：地面备份或高空系留二级侦察节点接管区域协调
  -> 二级节点不可用：集群代表 / 完全无中心 CBBA 或拍卖式协商
  -> 协商不收敛：保持、继续观测或安全回退的离线占位状态
```

### 4.1 二级侦察节点的角色

高空系留侦察无人机在 D4 中建模为区域二级节点：

- `node_role=NodeRole.SECONDARY_RECON`：表示该节点具备区域观测和协调能力。
- `capability_class="tethered_recon"` 或 `"secondary_c2"`：用于 leader 排序和审计。
- `coordinator_only=True`：表示该节点只做区域协调和观测摘要，不作为执行资源参与任务所有权分配。
- `coverage_cell`：表示节点覆盖的粗粒度小区或区域，后续应作为多区域接管过滤条件。

当二级节点健康时，它可以作为区域协调者，向覆盖范围内的拦截资源提供：

- 航迹摘要：例如 `TrackSummary` 的高置信 source count、age 和 coverage cell。
- 局部资源摘要：附近资源的可用性、通信质量和 operator hold 状态。
- 面向 D5 的观测/图像 cue 语义：例如某个 `global_track_id` 在二级节点视场中的候选位置和置信度。

这些 cue 只作为 D5 末端视觉配准的辅助证据。它们不能授权本地处置，不能改变 `global_track_id`，不能绕过 D3 plan version，也不能替代 D5 的友方/未知身份保守判断。

### 4.2 Leader 选择

`FailoverCoordinator.elect_leader_resource()` 使用确定性排序：

```text
takeover_priority
-> node_role rank
-> lease_epoch
-> availability_band
-> comm_band
-> capability_class
-> node_id
```

设计意图：

- `takeover_priority`：让预设备份或区域节点优先于临时资源。
- `node_role`：优先级为 `ground_backup < secondary_recon < cluster_representative < interceptor`。
- `lease_epoch`：同类节点中选择更新租约，减少旧 leader 复活。
- `availability/comm/capability`：在前序条件相同的情况下选择状态更稳的节点。
- `node_id`：最后使用确定性 tie-break，保证并行节点选择一致。

当前实现中 `GROUND_BACKUP` 和 `SECONDARY_RECON` 都映射为 `coordination_mode="secondary_node"`。这表示“仍有区域/备份协调者”，不是完全无中心。若需要更细审计，后续可拆分为 `ground_backup_node` 与 `secondary_recon_node`。

## 5. CBBA、拍卖和合同网协议

### 5.1 CBBA 原理

CBBA（Consensus-Based Bundle Algorithm）把任务分配拆成两个过程：

1. Bundle building：每个节点根据本地收益把任务加入自己的 bundle。
2. Consensus：节点交换各任务的 winner 和 bid，发现自己失去某个任务后释放该任务及其后的 bundle，再重新竞标。

在本模块中，任务是连续性任务 `TrackSummary`，资源是可执行的 `ResourceSummary`。二级节点如果 `coordinator_only=True`，会被排除在执行资源之外。

本模块的打分函数是合成研究基线：

\[
s_{ij}=2.0C_j+1.4A_i+0.5M_i+1.2Q_{ij}+1.0S_j-0.8R_j
\]

其中：

- \(C_j\)：航迹置信等级。
- \(A_i\)：资源可用性等级。
- \(M_i\)：通信质量等级。
- \(Q_{ij}\)：能力匹配分。
- \(S_j\)：source count 奖励。
- \(R_j\)：航迹年龄惩罚。

该分数只用于离线协商排序，不是实际效果或处置能力估计。

### 5.2 收敛假设

CBBA 收敛依赖以下条件：

- peer 图在仿真窗口内连通。
- 任务和资源摘要在一个 `epoch` 内相对静态。
- 每个节点使用相同 tie-break 规则。
- 消息最终能在足够轮数内到达。
- bundle 长度有限。

若丢包过高或轮数不足，`CBBAResult.converged=False`，当前实现不会发布有效 assignment，而是保留审计信息。这是保守安全边界。

### 5.3 通信开销

每轮每条边交换 winner/bid 状态，量级近似为：

\[
O(|E|\cdot|\mathcal{T}|)
\]

其中 \(E\) 为 peer 边数，\(\mathcal{T}\) 为任务数。全连接网络为 \(O(N^2|\mathcal{T}|)\)，稀疏网络减少单轮消息量，但增加网络直径和共识轮数。

### 5.4 与拍卖和合同网的关系

- 单轮拍卖：实现简单、通信少，但在冲突和重分配场景中容易出现局部最优或重复所有者。
- 合同网协议：适合 manager/contractor 结构，若二级节点健康，可由二级节点扮演区域 manager；但 manager 失效后仍需 peer 共识。
- CBBA：比单轮拍卖更重，但能通过 winner state 传播减少冲突，适合 D4 作为完全无中心降级基线。

与 D3 的中心化 Hungarian 或最小费用流相比，CBBA 不保证全局最优。它的目标是中心失效时的保底一致性，而不是替代中心化最优计划。

## 6. 实施流程

### 6.1 正常运行

1. D3 发布中心化 AssignmentPlan，D4 只记录 digest、epoch 和资源摘要。
2. D4 定期接收 heartbeat 和 assignment digest。
3. 高空系留二级侦察节点在健康时作为区域观察源，维护覆盖区摘要。

### 6.2 中心失效

1. `update_health()` 根据 heartbeat age 和 peer votes 转入 `failed`。
2. `plan_degraded()` 调用 `elect_leader_resource()`。
3. 若 leader 是 `ground_backup` 或 `secondary_recon`，进入 `coordination_mode="secondary_node"`。
4. 若无可用二级/备份节点，则由集群代表或普通资源进入 `coordination_mode="distributed_cbba"`。
5. `coordinator_only` 节点被排除出执行资源，只参与协调审计。
6. `CBBANegotiator.run()` 生成保底 assignment 或非收敛审计结果。

### 6.3 中心恢复

1. heartbeat 恢复后先进入 `suspect`，不直接回 `normal`。
2. `merge_recovery()` 对中心计划和 fallback 计划做双轨合并。
3. 无冲突、无 review 且 `human_accept=True` 才恢复 `normal`。
4. 否则保持 `degraded`，等待上层重新确认。

## 7. 关键接口

### 7.1 `FailoverCoordinator`

- `observe_center(now_s, heartbeat_ok, digest_ok, center_epoch)`：处理中心状态观测。
- `update_health(now_s, peer_fail_votes, quorum_size)`：根据超时和 quorum 更新状态。
- `elect_leader_resource(resources)`：选择备份/二级/代表节点。
- `plan_degraded(tasks, resources, network, now_s, ...)`：执行降级计划。
- `merge_recovery(center_assignments, fallback_assignments, human_accept, now_s)`：中心恢复双轨合并。

### 7.2 `CBBANegotiator`

- `run(tasks, resources, network, start_time_s)`：运行多轮 bundle building 和 winner consensus。

### 7.3 数据结构

- `TrackSummary`：只保留粗粒度任务摘要，不携带高精度状态。
- `ResourceSummary`：描述资源/节点角色、可用性、通信质量、租约和覆盖区域。
- `CBBAResult`：用于 D6 的降级指标来源。

## 8. 参数与调参建议

| 参数 | 默认/位置 | 建议 |
|---|---|---|
| `heartbeat_warning_s` | `FailoverCoordinator` | 应小于 stale 阈值，用于提前进入 degraded |
| `heartbeat_stale_s` | `FailoverCoordinator` | 控制 suspect 灵敏度，过小会频繁误报 |
| `heartbeat_failure_s` | `FailoverCoordinator` | 控制 failed 判定，必须大于正常抖动上界 |
| `stable_recovery_s` | `FailoverCoordinator` | 后续可用于恢复稳定窗口 |
| `takeover_priority` | `ResourceSummary` | 预设备份/二级节点应小于普通资源 |
| `lease_epoch` | `ResourceSummary` | 新租约优先，防止旧 leader 复活 |
| `bundle_limit` | `plan_degraded()` | 1 适合一资源一任务基线；多任务资源可增大 |
| `max_rounds` | `CBBANegotiator` | 丢包或稀疏网络下需增大 |
| `round_period_s` | `CBBANegotiator` | 影响 takeover duration 和消息传播 |
| `packet_loss/min_delay/max_delay` | `SimulatedNetwork` | 用于通信退化敏感性实验 |

二级节点调参建议：

- 区域二级节点使用 `node_role=SECONDARY_RECON`、`capability_class="tethered_recon"`、`coordinator_only=True`。
- 若同一区域有多个二级节点，使用 `takeover_priority` 和 `lease_epoch` 明确主备。
- 后续多区域仿真应按 `coverage_cell` 过滤二级节点接管范围，避免一个二级节点接管无覆盖区域。

## 9. 仿真验证

默认脚本：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py \
  --nodes 5 --tasks 4 --packet-loss 0.10 --seed 7
```

当前默认仿真由 `default_resources()` 生成普通节点，没有构造 `NodeRole.SECONDARY_RECON`。因此默认结果代表“二级节点不可用或未建模时的 CBBA 降级基线”。二级节点优先接管由 `tests/test_coordinator.py` 中的单元测试覆盖：

- `test_center_failure_degrades_to_secondary_recon_node_before_distributed_cbba`
- `test_secondary_unavailable_falls_back_to_distributed_cbba`

后续建议新增一个显式二级节点仿真场景：

1. 在资源集中加入 `sec-1`，设置 `node_role=SECONDARY_RECON`、`coordinator_only=True`、`coverage_cell="cell-north"`。
2. 让 `task.coarse_cell` 落在该覆盖区。
3. 对比 `secondary_node` 与 `distributed_cbba` 的接管时间、消息量、冲突数。
4. 将 `coordination_mode/leader_role/coverage_cell` 透传到 metrics JSON，供 D6 绘制分组统计。

## 10. 指标

D4 应向 D6 输出或支持计算：

- `failover_time`：从中心故障到降级计划形成的时间。
- `consensus_rounds`：CBBA 共识轮数。
- `degraded_completion_rate`：降级模式下任务分配完成率。
- `conflict_count`：过渡过程中 winner view 冲突次数。
- `messages_sent/messages_delivered/messages_dropped`：通信开销和丢包影响。
- `estimated_bytes`：粗略消息字节估计。
- `coordination_mode`：`secondary_node` 或 `distributed_cbba`。
- `leader_role`：`ground_backup/secondary_recon/cluster_representative/interceptor`。
- `coverage_cell`：二级节点覆盖区域。

当前 `coordination_mode` 已存在于 `CBBAResult.final_views`，但 `run_failover_simulation()` 尚未透传到顶层 metrics。建议后续补齐，避免实验报告把二级节点接管和完全分布式 CBBA 混在一起统计。

## 11. 与 D3/D5/D6 的接口关系

### D3 集中式分配

D3 是中心存在时的主分配模块。D4 不应覆盖 D3 的正常计划，只缓存 digest、version、epoch 和资源摘要。中心失效时，D4 使用上一版可验证计划作为降级基准；中心恢复后，D4 必须通过 `merge_recovery()` 与 D3 新计划对齐。

### D5 终端视觉配准

二级侦察节点健康时，可把区域图像 cue 或观测摘要传给小范围拦截资源，帮助 D5 做末端候选匹配。D4 只负责描述 cue 的来源、作用域和版本，不负责像素几何配准。D5 必须继续执行授权、plan version、友方身份和 `global_track_id` 不改写规则。

### D6 评估

D6 消费 D4 的 transition log、CBBAResult 和 merge result，计算 failover、consensus、conflict、completion、通信开销和恢复合并指标。建议 D6 将 `coordination_mode` 作为分组变量，分别统计二级节点接管和完全分布式 CBBA。

## 12. 局限与后续工作

当前局限：

- 默认仿真未构造 `secondary_recon`，二级节点路径主要由单元测试覆盖。
- `coverage_cell` 已记录但未参与 leader 过滤，无法直接评估多区域接管。
- `coordination_mode/leader_role/coverage_cell` 尚未在默认 metrics 顶层透传。
- CBBA 打分函数是合成基线，没有与 D3 的真实中心化代价函数完全对齐。
- 网络模型是内存队列，只用于延迟/丢包统计，不代表真实链路。

后续工作：

1. 增加二级节点默认或可选仿真场景。
2. 按 `coverage_cell` 限制二级节点接管范围，并增加多区域测试。
3. 将 `coordination_mode/leader_role/coverage_cell` 透传到 D6 metrics。
4. 增加合同网和单轮拍卖 baseline，与 CBBA 对比收敛轮数和冲突率。
5. 把 D3 的 plan version、authorization state 和 D5 的 cue 审计字段纳入降级日志。
6. 增加中心恢复后的多轮稳定窗口，而不是只依赖一次合并调用。

