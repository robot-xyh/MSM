# D3 中心化资源-目标分配综述及子方案

**定位**: 在 5 对 5 及更多目标场景中，由中心节点生成滚动 `AssignmentPlan`，并通过迟滞逻辑避免频繁重分配。  
**边界**: 本文只讨论抽象资源-目标匹配、离线评估和人工授权前的候选计划，不包含真实火控参数、毁伤模型或自动处置流程。

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

本文推荐：5 对 5 首先使用 SciPy Hungarian；当出现容量、禁配、备份资源或多轮窗口约束时，用 OR-Tools Min Cost Flow；更复杂逻辑再进入 CP-SAT/MILP 离线研究。

---

## 3. 开源代码选型

| 工具 | 适用场景 | 优点 | 限制 |
|------|----------|------|------|
| SciPy `linear_sum_assignment` | 一对一矩阵分配 | 简洁、快、稳定 | 难表达复杂约束 |
| OR-Tools Min Cost Flow | 容量、禁配、分组、时间窗 | 约束强 | 需要建图和整数代价缩放 |
| OR-Tools CP-SAT | 复杂逻辑约束 | 表达能力强 | 不适合高频滚动主线 |

推荐先写统一 `AssignmentSolver` 接口，底层可切换 Hungarian 或 Min Cost Flow。

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
- last_assignment
- operator_hold

Assignment
- resource_id
- global_track_id
- cost
- cost_breakdown
- feasibility_state

AssignmentPlan
- plan_id
- version
- window_id
- assignments
- total_cost
- created_at
- human_authorization_state
```

### 4.2 类图

```text
AssignmentPlanner
  + build_cost_matrix()
  + solve()
  + apply_hysteresis()
  + publish_plan()

AssignmentSolver
  + solve(cost_model, constraints)

HungarianSolver --|> AssignmentSolver
MinCostFlowSolver --|> AssignmentSolver

HysteresisManager
  + min_hold_time
  + min_switch_gain
  + max_changes_per_window
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
    def plan(self, tracks, resources, previous_plan):
        feasible_tracks = filter_engageable_tracks(tracks)
        feasible_resources = filter_available_resources(resources)

        cost = self.build_cost_matrix(feasible_tracks, feasible_resources)
        candidate = self.solver.solve(cost)

        candidate = self.hysteresis.apply(candidate, previous_plan)
        candidate.version = previous_plan.version + 1
        candidate.human_authorization_state = "required"
        return candidate

class HysteresisManager:
    def apply(self, candidate, previous):
        gain = previous.total_cost - candidate.total_cost
        if gain < self.min_switch_gain:
            return previous.keep_with_new_window()

        if count_changes(candidate, previous) > self.max_changes_per_window:
            candidate = limit_changes(candidate, previous)

        return keep_assignments_within_min_hold(candidate, previous)
```

---

## 7. 重分配触发条件

| 触发 | 说明 |
|------|------|
| 新目标确认 | `tentative -> confirmed/engageable` |
| 航迹质量变化 | 协方差发散或重新稳定 |
| 资源状态变化 | 资源失效、忙碌、通信降级 |
| 末端配准失败 | D5返回 `ambiguous/hold/reacquire` |
| 中心降级 | D4进入 `suspect/failed` |
| 计划收益足够 | 新方案改善超过迟滞阈值 |

---

## 8. 离线验证

生成 5x5、10x10、20x20 场景，固定随机种子，比较：

```text
Hungarian without hysteresis
Hungarian with hysteresis
MinCostFlow with constraints
MinCostFlow with hysteresis
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
```

---

## 9. 交付物

1. 动态分配策略综述。
2. SciPy 与 OR-Tools 选型对比。
3. `AssignmentPlanner`、`AssignmentPlan`、`ResourceState` 数据结构。
4. 迟滞重分配算法设计。
5. 离线批量验证脚本方案和报告模板。

---

## 10. 参考资料

- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/mincostflow>
- OR-Tools assignment as min-cost flow: <https://developers.google.com/optimization/flow/assignment_min_cost_flow>
- Dynamic WTA rolling horizon example: <https://www.mdpi.com/2079-9292/9/9/1511>
- TAPF dynamic assignment discussion: <https://arxiv.org/html/2307.00663v1>
