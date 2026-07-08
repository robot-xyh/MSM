# D3 中心化资源-目标分配综述及子方案

**定位**: 在由 main runtime `--drone-count` 决定的 N 对 N 或非等量资源/目标场景中，由中心节点生成滚动 `AssignmentPlan`，并通过迟滞逻辑避免频繁重分配；5v5 只作为示例和基准场景。
**边界**: 本文只讨论抽象资源-目标匹配、离线评估和人工授权前的候选计划，不包含真实火控参数、毁伤模型或自动处置流程。
**D3 复核状态 2026-07-08**: P0 无新增缺口；`PlannerConfig.human_authorization_state` 已生效；D5 duplicate/friend/fov/feasibility metadata 可通过 D3 helper 写回下一轮成本或禁配边，main runtime 已接入该 writeback；D4/main 触发 `request_center_replan` 后，main runtime 会再次调用 D3 生成新中心 plan version，并在 episode bus 记录 `replan_reason`、`supersedes_plan_id`、`supersedes_plan_version`、`active_plan_owner=center`；D4/main 选定二级节点后，D3 可生成 `secondary_plan_v2` owner/source/version DTO，main runtime 已接入 secondary owner/version/source 记录；D7 仍只接受当前有效 binding/version。剩余 P1 聚焦真实多 seed 校准和 D5 feedback 权重阈值长期标定，P2 保留 OR-Tools Min Cost Flow optional 后端。

---

## 0. 当前代码状态摘要

截至 2026-07-08，D3 代码已经实现：

- SciPy Hungarian / `linear_sum_assignment` 主线，带 dummy unassignment 列。
- 无 SciPy 时的小规模 `FallbackAssignmentSolver` 位掩码 DP fallback。
- `AssignmentPlan(plan_id, version, window_id, resource_count, target_count)` 和 `assignment_matrix_shape` 规模 metadata。
- `StalePlanError`，拒绝旧 `previous_plan`、旧 `plan_id` 或不匹配的 `expected_previous_version`。
- 迟滞重分配：`delta`、`min_dwell`、`max_changes_per_window`、`reassignment_switch_penalty`。
- D5 terminal feedback helper，始终 `allow_local_rebind=False`。
- D7 `AssignmentGuidanceBinding`，携带 `assigned_global_track_id`、`plan_version`、binding state、source/target/link 和 `allow_local_rebind=False`。
- `AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出。
- synthetic AirSim dry-run adapter，不 import AirSim，不控制 Blocks runtime。
- `PlannerConfig.human_authorization_state` 透传到 `AssignmentPlan.human_authorization_state`，并写入 `configured_human_authorization_state` / `effective_human_authorization_state` metadata。
- `apply_terminal_feedback_to_planner_inputs()` 将 D5 duplicate/friend/fov/feasibility metadata 写回下一轮 `TargetTrack[]/ResourceState[]`。
- `prepare_secondary_takeover_plan()` 在 D4/main 已选定二级节点后校验版本并写入 `secondary_plan_v2` owner/source/supersede metadata。

当前只是部分实现或未实现：

- `MinCostFlowAssignmentSolver` 只是 OR-Tools 预留接口，`solve()` 当前抛出 `NotImplementedError`。
- `secondary_plan_v2` 的 D3 DTO/binding 兼容、owner/source、版本 supersede metadata 已实现，main runtime 已接入 secondary owner/version/source 记录；二级节点选择、租约执行、中心恢复合并和 active owner runtime 仲裁仍属 D4/main policy，不列为 D3 DTO 缺口。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 仍由 main/D4 消费 D3 证据后触发，D3 不自动调用；其中中心 `request_center_replan` 的 owner/version/supersede runtime 记录已由 main 接线，D3 只需保持版本化计划和 stale 拒绝合同。
- 剩余 D3 P1 是真实多 seed/N 规模校准和 D5 feedback 权重阈值长期标定。
- D3 不负责末端视觉重绑，不改写 `global_track_id`。

---

## 1. 研究问题

初始分配不是一次性决策。目标会丢失、航迹质量会变化、资源状态会变化，末端配准也可能返回 `ambiguous` 或 `hold`。如果每一帧都重新求最优，系统会频繁抖动；如果完全不重分配，则会漏掉更合理的计划。

本子系统目标：

- 中心节点正常时默认使用 Hungarian。
- 复杂约束时升级为最小费用流或 CP-SAT/MILP。
- 分配代价包含航迹不确定性、抽象威胁权重、资源状态、视场确认难度和资源间冲突风险。
- 重分配必须带版本号、迟滞和最小保持时间。

---

## 2. 文献综述要点

2015-2026 年动态资源分配主线包括 Hungarian、最小费用流、MILP、滚动窗口优化和多智能体任务分配。Hungarian 适合一对一匹配，延迟低、实现成熟。最小费用流能表达容量、禁配边、任务需求量和多阶段约束。MILP/CP-SAT 表达能力更强，但求解时间和建模复杂度更高。

滚动窗口优化是动态场景常见方法：每个周期只提交近期计划，远期计划保持可调整。为了避免抖动，常用策略包括切换惩罚、最小保持时间、双阈值、版本锁和收益门限。例如只有新方案总代价相对旧方案改善超过阈值，才允许切换。

本文推荐：N 对 N 或非等量 M/N 一对一基线优先使用 SciPy Hungarian，5v5 仅作为默认示例/基准；当出现容量、禁配、备份资源或多轮窗口约束时，再把当前预留的 OR-Tools Min Cost Flow 后端实现为可运行求解器；更复杂逻辑再进入 CP-SAT/MILP 离线研究。

---

## 3. 开源代码选型

| 工具 | 适用场景 | 优点 | 限制 |
|------|----------|------|------|
| SciPy `linear_sum_assignment` | 一对一矩阵分配 | 简洁、快、稳定 | 难表达复杂约束 |
| OR-Tools Min Cost Flow | 容量、禁配、分组、时间窗 | 约束强，适合后续复杂约束 | 当前仅预留接口；需要 optional dependency、建图和整数代价缩放 |
| OR-Tools CP-SAT | 复杂逻辑约束 | 表达能力强 | 当前未实现，不适合高频滚动主线 |

当前已落地 Hungarian/fallback 主线和 `MinCostFlowAssignmentSolver` 保留边界。后续接入 OR-Tools 时，应保持 `AssignmentPlan`、D7 binding 和 D6 export 的外部合同不变。

---

## 4. 子系统架构

### 4.1 数据结构

```text
ResourceState
- resource_id
- status: available | busy | degraded | unavailable
- capability_class
- health_score
- busy_until
- operator_hold
- load_penalty
- fov_difficulty / conflict_risk
- metadata

Assignment
- resource_id
- target_id  # 等价引用 D2/中心维护的 global_track_id
- cost
- cost_breakdown
- feasibility_state
- source_node_id / target_node_id / link_type
- plan_version
- stale_after_s

AssignmentPlan
- plan_id
- version
- window_id
- resource_count
- target_count
- assignments
- total_cost
- created_at
- human_authorization_state
- decision_state
- source_node_id / target_node_id / link_type
- stale_after_s

TerminalFeedbackWriteback
- tracks/resources  # 下一轮 D3 输入
- prohibited_edges
- hold_resource_ids
- updated_target_ids / updated_resource_ids
- d7_gate_action
- d4_requests
- allow_local_rebind=False
```

### 4.2 类图

```text
AssignmentPlanner
  + plan(tracks, resources, timestamp, previous_plan=None, expected_previous_version=None)
  - _apply_hysteresis()
  - _validate_previous_plan()
  - _remember_plan()

CostModel
  + build_matrix(tracks, resources, timestamp)
  + edge_cost(track, resource, timestamp)

HungarianAssignmentSolver
  + solve(cost_matrix, unassigned_costs)

FallbackAssignmentSolver
  + solve(cost_matrix, unassigned_costs)

MinCostFlowAssignmentSolver
  + solve(...)  # 当前为 OR-Tools 预留接口，抛出 NotImplementedError
```

---

## 5. 代价函数

保持抽象、可解释、可记录：

```text
assignment_cost =
    approach_window_cost
  + track_uncertainty_penalty
  + target_priority_weight
  + resource_state_penalty
  + fov_confirmation_difficulty
  + inter_resource_conflict_risk
  + reassignment_switch_penalty
```

每项都必须写入 `cost_breakdown`，便于解释为何分配或拒配。

---

## 6. 迟滞逻辑伪代码

```python
class AssignmentPlanner:
    def plan(self, tracks, resources, timestamp, previous_plan=None, expected_previous_version=None):
        validate_previous_plan(previous_plan, expected_previous_version)
        matrix = CostModel.build_matrix(tracks, resources, timestamp)
        candidate = HungarianAssignmentSolver.solve(matrix, unassigned_costs)
        candidate = build_assignment_plan(candidate, resource_count=len(resources), target_count=len(tracks))
        candidate.human_authorization_state = self.config.human_authorization_state
        if previous_plan is None:
            remember_latest_plan(candidate)
            return candidate
        candidate = apply_hysteresis(candidate, previous_plan, matrix, timestamp)
        remember_latest_plan(candidate)
        return candidate

class HysteresisManager:
    def apply(self, candidate, previous):
        old_cost = rescore_previous_assignment_on_current_matrix(previous)
        if previous_infeasible:
            return accept(candidate, "accepted_previous_infeasible")
        if not enough_gain_or_dwell_or_change_budget(candidate, old_cost):
            return keep_previous_assignments_with_new_version("held_by_hysteresis")
        return accept(candidate, "accepted_gain_and_dwell")
```

当前实现还会拒绝 stale `previous_plan`，并把每轮 `resource_count`、`target_count` 和 `assignment_matrix_shape` 写入计划。

---

## 7. 重分配触发条件

| 触发 | 说明 |
|------|------|
| 新目标确认 | `tentative -> confirmed/engageable` |
| 航迹质量变化 | 协方差发散或重新稳定 |
| 资源状态变化 | 资源失效、忙碌、通信降级 |
| 末端配准失败 | D5返回 `ambiguous/hold/reacquire` |
| 被动中心降级 | D4进入 `suspect/failed` |
| 主动降级风险 | 中心仍在线，但计划年龄、延迟、成本或末端一致性已不满足有效性要求 |
| 计划收益足够 | 新方案改善超过迟滞阈值 |

---

## 8. 主动降级与末端反馈下的分配约束

D4 现在区分被动降级和主动降级。被动降级来自中心节点心跳、通信或进程失效；主动降级发生在中心节点仍工作，但 D3 发现当前 `AssignmentPlan` 在态势上已经不可靠，例如定位误差增大、关联不确定性升高、计划版本过期、assignment 成本快速恶化，或 D5 末端视觉连续反馈不一致。

D3 在该场景下的职责不是直接选择二级节点或完全分布式方案，也不是自动调用 D4 action，而是输出可审计的计划有效性证据，并约束下游不得本地改绑：

```text
D5 末端反馈 -> D3 计划有效性评估 -> keep / hold / replan / secondary_arbitration
```

### 8.1 D5 不一致时的处理原则

当 D5 发现末端视觉关联与中心或二级节点分配不一致时，D3 应按保守顺序处理：

1. `hold`: 若只是单帧模糊、短时遮挡、局部 MOT 未稳定，D3 保持原 `assigned_global_track_id`，把对应资源置为暂缓确认，不允许本地无人机自行改绑 `global_track_id`。
2. `replan`: 若 D5 连续反馈目标不可见、视场代价显著升高，但 D2 航迹仍稳定，D3 重新计算中心 `AssignmentPlan`，提高该资源-目标边的 `fov_confirmation_difficulty` 或设置临时禁配边。
3. `secondary_arbitration`: 若 D5 多帧不一致，且 D2 关联不确定性或 D1 定位协方差同时升高，D3 请求 D4 进入主动降级仲裁，优先交给覆盖该区域的二级侦察节点复核。
4. `distributed_arbitration`: 若中心和二级节点都无法形成一致计划，D3 只输出失效证据，由 D4 降级到完全分布式协同；D3 不直接发布分布式任务结果。

核心约束：D5 可以报告 `ambiguous`、`hold`、`reacquire`、`friend_overlap_hold` 和候选视觉证据，但不能把本地视觉最近目标直接替换为新的 `global_track_id`。D3 只能接受来自 D2/D4 统一数据总线的全局 ID 和版本化计划。

### 8.2 D3 给 D4 的主动降级触发量

D3 应向 D4 发布或记录以下 `AssignmentValiditySummary` 字段，用于主动降级仲裁：

| 触发量 | 含义 | 建议用途 |
|---|---|---|
| `plan_age` | 当前计划从 `created_at` 到评估时刻的年龄 | 超过 2-3 个规划周期时触发中心重分配检查 |
| `assignment_latency` | 从 D2 航迹时间戳到 D3 计划发布时间的端到端延迟 | 延迟持续升高时降低计划置信度 |
| `cost_margin` | 当前候选计划与旧计划的成本差或比值 | 判断是否值得中心重分配 |
| `reassignment_hysteresis` | 迟滞保持次数、最小保持时间和收益门限状态 | 区分正常防抖与持续无法切换 |
| `stale_plan_version` | 调用方或下游使用的版本是否落后于 D3 最新版本 | stale 计划必须被拒绝，不得覆盖新计划 |
| `duplicate_assignment_count` | 同一目标或同一资源被重复分配的异常计数 | 非零时请求 D4 仲裁或进入 hold |
| `unassigned_high_threat_count` | 高优先级目标未分配数量 | 持续非零时触发重分配或主动降级 |

建议 D4 解释这些字段时采用分层判断：

```text
valid -> central_replan -> secondary_arbitration -> distributed_arbitration -> hold_for_observation
```

如果 `cost_margin` 显示中心 Hungarian 可以显著改善，且 `stale_plan_version=False`，应由 main/D4 优先触发 `request_center_replan`。当前 main runtime 已在触发后再次调用 D3，并记录新的 `active_plan_owner=center`、`plan_id/version`、`replan_reason`、superseded previous plan 和 stale/rejected plan 归因。如果 `assignment_latency`、`stale_plan_version`、`duplicate_assignment_count` 或 D5 多帧不一致同时出现，应请求 D4 主动降级仲裁。D3 当前只给出 summary、metadata、feedback writeback 和 secondary takeover DTO，不直接执行 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。

### 8.3 D3 与 D7 比例导引的接口

D7 比例导引只应消费 D3/D4 确认过的版本化分配，不应自行选择目标。D3 当前输出给 D7 的接口是 `AssignmentGuidanceBinding`：

```text
AssignmentGuidanceBinding
- assigned_global_track_id
- resource_id
- plan_id
- plan_version
- guidance_phase: midcourse | terminal_visual
- assignment_validity_state
- human_authorization_state
```

中段 PN 使用 `assigned_global_track_id` 对应的 D2/D1 航迹预测作为导引目标；进入末端视觉 PNG 后，D7 必须继承同一个 `global_track_id`。如果 D5 在末端发现视觉目标与该 `global_track_id` 不一致，D7 不得切换目标，而应进入 `hold/reacquire`，并把不一致事件回传 D5/D3/D4。

因此 D3 到 D7 的约束是：

- `plan_version` 必须与当前数据总线版本一致。
- `assigned_global_track_id` 在中段和末端保持一致。
- `guidance_phase` 只描述仿真阶段，不代表真实控制或处置命令。
- `human_authorization_state` 来自 `PlannerConfig`，默认 `required`，也可由外部授权/仿真记录层显式设置；D3 不提供绕过授权字段。
- D4 action 为 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed` 时，D7 应阻断视觉 PNG。
- D5 terminal association 未达到 `locked` 或 binding 为 `stale/revoked/hold/reassigned` 时，D7 不得进入目标重绑。

---

## 9. N 配置滚动重分配执行顺序与迟滞原则

### 9.1 2v2 场景

2v2 适合做最小闭环测试，重点验证 ID 稳定、版本号、迟滞和 D5 末端反馈；它和 5v5 一样都不是算法常量：

1. D2 输出两个稳定 `global_track_id`，D3 构建 2x2 成本矩阵。
2. D3 使用 Hungarian 生成初始 `AssignmentPlan(version=1)`。
3. 若 D5 两个资源均返回一致锁定，D3 保持计划，除非新计划收益超过 `delta` 且满足 `min_dwell`。
4. 若一个资源末端模糊，D3 对该边提高 `fov_confirmation_difficulty`，先进入 `hold` 或中心重分配。
5. 若两个目标交叉导致 D5 与 D2 同时不稳定，D3 不允许本地换绑，输出主动降级证据给 D4。

2v2 默认迟滞建议：`delta=0.2`，`min_dwell=2` 个规划周期，单窗口最多允许 1 条 assignment 变化。这样可以清楚观察每一次换配的原因。

### 9.2 N 对 N 场景

运行时 N 由 main `--drone-count` 统一设置，5v5 是基准示例。重点是避免频繁抖动、重复分配和高优先级目标长期未分配：

1. D2 输出 N 个或更多 `GlobalTrack`，D3 过滤 `confirmed/engageable` 航迹。
2. D3 将资源状态、D5 视场难度、D1/D2 协方差和冲突风险合成成本矩阵。
3. 中心节点正常时，每个规划周期先计算候选 Hungarian 计划，但不立即替换旧计划。
4. 若旧计划仍可行，只有满足 `J_new < (1-delta) * J_old`、`dwell_time > min_dwell`、`change_count <= max_changes_per_window` 才接受换配。
5. 若旧计划不可行，例如资源失效、目标 dropped、禁配边出现，则允许绕过收益门限，标记 `accepted_previous_infeasible`。
6. 若 D5 多视角关联与中心/二级计划连续不一致，D3 请求 D4 `secondary_arbitration`，而不是在本地资源之间直接重写 `global_track_id`。
7. 若二级节点也无法提供一致计划，D4 才进入完全分布式协同；D3 只保留最新中心计划作为回滚和审计基线。二级 takeover 的 D3 DTO 规则已要求新 plan version 大于被 supersede 的中心 plan，并写入 owner/source/supersede/epoch/lease metadata；节点选择、租约执行、中心恢复合并和 stale secondary plan runtime 拒绝规则由 D4/main 定义。

N 对 N 基准迟滞建议可从 5v5 参数开始扫描：`delta=0.2`，`min_dwell=2.0s`，`max_changes_per_window=2`，连续 3 次 `held_by_hysteresis` 且 D5 不一致时请求 D4 主动降级仲裁。后续 P1 校准应跨真实多 seed 统计 `resource_count`、`target_count`、`reassignment_count`、`duplicate_assignment_count`、`unassigned_high_threat_count`、`stale_plan_version_count`、`secondary_arbitration_count`、center/secondary owner/version/source 变更，并用 D6 assignment records 反向标定 D5 feedback 权重阈值。

---

## 10. 离线验证

当前已实现的离线验证主要覆盖 Hungarian/fallback、迟滞、stale 拒绝、D7 binding、D5 feedback helper/writeback、secondary takeover DTO、D6 export 和 synthetic dry-run adapter。后续可生成 2v2、5v5、8v8、10x10、20x20 和非等量 M/N 场景，固定随机种子，比较：

```text
Hungarian without hysteresis
Hungarian with hysteresis
MinCostFlow with constraints      # P2/非本轮后端实现后再加入
MinCostFlow with hysteresis       # P2/非本轮后端实现后再加入
```

指标：

```text
total_assignment_cost
reassignment_count
average_assignment_hold_time
duplicate_assignment_count
unassigned_high_threat_count
version_conflict_count
single_window_runtime_ms
secondary_arbitration_count
stale_plan_version_count
```

---

## 11. 交付物

1. 动态分配策略综述。
2. SciPy 与 OR-Tools 选型对比。
3. `AssignmentPlanner`、`AssignmentPlan`、`ResourceState` 数据结构。
4. 迟滞重分配算法设计。
5. 离线批量验证脚本方案和报告模板。
6. 面向 D4 主动降级的 `AssignmentValiditySummary` 字段建议。
7. 面向 D7 PN 的 `AssignmentGuidanceBinding` 接口建议。

---

## 12. 参考资料

- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/mincostflow>
- OR-Tools assignment as min-cost flow: <https://developers.google.com/optimization/flow/assignment_min_cost_flow>
- Dynamic WTA rolling horizon example: <https://www.mdpi.com/2079-9292/9/9/1511>
- TAPF dynamic assignment discussion: <https://arxiv.org/html/2307.00663v1>
