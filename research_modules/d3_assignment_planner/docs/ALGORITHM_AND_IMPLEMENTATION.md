# D3 集中式资源-目标分配算法与实施方案

## 1. 模块定位与边界

D3 是集中式资源-目标分配模块，输入来自 D2 的稳定 `GlobalTrack`/`global_track_id` 以及资源状态摘要，输出版本化候选 `AssignmentPlan`，供 D5 末端视觉配准知道“本资源当前应关注哪个全局目标”，也供 D4 在中心节点失效时作为降级协商基线。

本模块只研究离线科研仿真中的抽象候选分配。输出计划默认保持 `human_authorization_state="required"`，但可通过 `PlannerConfig.human_authorization_state` 显式设置为仿真记录态或外部授权层传入的状态；D3 不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置或绕过授权流程。

## 2. 输入与输出

### 2.1 输入对象

`TargetTrack` 表示一个可分配目标摘要，当前字段包括：

- `track_id`：来自 D2 的稳定全局航迹 ID。
- `threat_score`：归一化威胁权重，数值越高越应避免未分配。
- `covariance`：航迹不确定性摘要，通常可由 D1/D2 的协方差迹或门限归一化得到。
- `window_cost`：接近窗口或时间窗口代价，越小表示当前资源更适合在该窗口内处理该目标。
- `assignable`：是否允许进入候选分配。
- `fov_difficulty_by_resource`、`conflict_risk_by_resource`、`feasibility_by_resource`：按资源细化的视场难度、冲突风险和可行性约束。

`ResourceState` 表示一个资源摘要，当前字段包括：

- `resource_id`：资源 ID，需与 D5 的本地资源身份一致。
- `status`：`available/degraded/busy/unavailable` 等抽象状态。
- `health_score`、`busy_until`、`operator_hold`、`load_penalty`：资源健康、占用和人工保持状态。
- `fov_difficulty`、`conflict_risk`：默认视场难度和资源间冲突风险。
- `capability_class`、`metadata`：为后续容量、角色和区域约束预留。

### 2.2 输出对象

`AssignmentPlan` 是 D3 的唯一计划输出，关键字段为：

- `plan_id`、`version`、`window_id`：计划身份、单调递增版本和滚动窗口编号。
- `assignments`：`Assignment(target_id, resource_id, cost, cost_breakdown)` 列表。
- `unassigned_target_ids`：未被分配的目标。
- `total_cost`、`candidate_total_cost`、`previous_total_cost_current`：当前采用计划、候选计划和旧计划重评分成本。
- `decision_state`：如 `accepted`、`unchanged`、`held_by_hysteresis`、`accepted_previous_infeasible`。
- `human_authorization_state`：来自 `PlannerConfig.human_authorization_state`，默认 `required`；main runtime 可在仿真中使用 `recorded` 等状态，并由外部授权层解释。
- `source_node_id`、`target_node_id`、`link_type`、`plan_version`、`stale_after_s`：跨中心、二级节点和资源节点传递计划时的通信合同字段。
- `terminal_feedback_state`、`duplicate_terminal_lock_risk`：D5 末端反馈和重复锁定风险摘要，仅用于 hold/replan/arbitration 决策，不允许本地改写全局 ID。

过期版本不得覆盖新版本。`AssignmentPlanner` 实例绑定单个 episode：首次调用允许 `previous_plan=None`；一旦内部记录 active `plan_id/version`，后续调用必须显式传入该 active plan。缺失前序计划会抛出 `StalePlanError(reason="previous_plan_required")`，提交旧 plan id/version 或不匹配的 `expected_previous_version` 也会被拒绝。新 episode 应创建新的 planner 实例，不使用隐式 reset。

## 3. 数学模型

设目标集合为 `T={1,...,M}`，资源集合为 `R={1,...,N}`。分配变量为：

```text
x_ij in {0,1}
```

其中 `x_ij=1` 表示目标 `i` 分配给资源 `j`。当前主线采用一对一约束：

```text
sum_j x_ij <= 1      for each target i
sum_i x_ij <= 1      for each resource j
```

滚动规划的候选目标函数为：

```text
J = sum_i sum_j x_ij * (C_ij + S_ij) + sum_i u_i * U_i
```

`C_ij` 是资源 `j` 处理目标 `i` 的抽象基础代价。若目标在 `previous_plan` 中已有资源且候选边切换到其他资源，`S_ij=reassignment_switch_penalty`；保持原资源、无历史 assignment、不可行边和未分配 dummy 边均不加该项。`S_ij` 在 Hungarian/fallback 求解前写入矩阵，使 solver objective、`Assignment.cost`、cost breakdown 和 evidence 保持单次计费一致。`u_i=1` 表示目标 `i` 被保留为未分配，`U_i` 是未分配惩罚。未分配惩罚随威胁权重上升：

```text
U_i = unassigned_base_cost * (0.5 + threat_score_i)
```

因此高威胁目标在资源不足时更不容易被放入未分配集合，但该设计仍只是离线评分，不代表自动处置。

## 4. Hungarian/LAP 主算法

### 4.1 原理

Hungarian 算法用于线性分配问题（LAP），在给定代价矩阵 `C` 时寻找总成本最小的一对一匹配。D3 使用它作为中心节点正常时的默认算法，因为：

- 适合 5v5、10v10 这类一对一滚动分配基线。
- 结果确定、可解释，便于审计每条边的 `cost_breakdown`。
- 复杂度通常记为 `O(k^3)`，`k` 为补齐后的矩阵规模；对当前离线仿真规模耗时很低。
- Python 可直接使用 `scipy.optimize.linear_sum_assignment`，并提供小规模动态规划 fallback。

### 4.2 可选未分配建模

真实滚动场景中，资源可能少于目标，或某些目标暂不可分配。因此 D3 在求解前给每个目标加入 dummy unassignment 列：

```text
prepared_matrix = [C_resource_edges | C_unassigned_dummy_edges]
```

若 Hungarian 选择真实资源列，则形成 `Assignment`；若选择 dummy 列，则该目标进入 `unassigned_target_ids`。这避免了强行把不可行目标分配给资源。

### 4.3 适用边界

Hungarian 适用于：

- 每个目标最多一个主资源、每个资源最多一个目标。
- 单个规划时刻的静态代价矩阵。
- 需要快速、透明、可复现的中心化基线。

它不直接表达：

- 一个资源同时服务多个目标的容量约束。
- 一个目标需要主资源和备份资源的需求约束。
- 编组配额、区域配额、路径时间层、先后顺序等复杂约束。
- 多窗口全局优化。

这些场景应升级到最小费用流或混合整数规划，但不应破坏 D3 当前的 `AssignmentPlan` 外部契约。

## 5. 最小费用流升级思路

当前 `MinCostFlowAssignmentSolver` 是预留接口，会明确抛出 `NotImplementedError`，避免在没有 OR-Tools 依赖时产生隐式行为。后续若需要多容量和备份资源，可按以下图模型实现：

```text
source
  -> resource nodes        capacity = resource_capacity_j, cost = resource_state_cost
  -> target-demand nodes   via resource-target arcs, cost = scaled C_ij
  -> sink                 demand = target_demand_i
```

可扩展约束包括：

- 资源容量：`capacity(resource_j -> target_i)` 限制单资源可承担数量。
- 目标需求：高优先目标可设置主分配和备份分配需求。
- 禁止边：不可行资源-目标对不建边或赋予高成本。
- 区域/编组配额：加入 group nodes 约束区域资源使用。
- 时间窗：复制多层时间节点，形成 time-expanded network。

实施时需要把浮点代价缩放为整数，并记录缩放比例，保证报告中的成本仍能回映到原始 `CostBreakdown`。D3 当前建议仅在 Hungarian 无法表达容量或备份约束时启用该路径。

## 6. 代价函数分解

D3 当前 `CostModel.edge_cost()` 将每条边分解为六个主要项：

```text
C_ij =
    w_window     * window_cost
  + w_covariance * covariance_penalty
  + w_threat     * (1 - threat_score)
  + w_resource   * resource_state_penalty
  + w_fov        * fov_difficulty
  + w_conflict   * conflict_risk
  + infeasible_penalty
```

### 6.1 接近窗口代价

`window_cost` 由上游或仿真场景给出，用于表达当前资源相对该目标的滚动窗口优劣。它不表示真实拦截控制律，只是分配层排序特征。建议先归一化到 `[0,1]`，再进入 `CostWeights.window`。

### 6.2 航迹不确定性惩罚

`covariance` 来自 D1/D2 对目标位置、速度不确定性的摘要。协方差越大，错误分配和末端配准失败风险越高，因此代价增加。若 D2 输出完整协方差矩阵，可用位置协方差迹、最大特征值或门控椭圆面积归一化。

### 6.3 威胁权重

当前边代价使用 `(1 - threat_score)`，因此高威胁目标边代价更低，同时未分配惩罚 `U_i` 更高。这样在资源有限时，求解器自然倾向优先覆盖高威胁目标。

### 6.4 资源状态惩罚

`resource_state_penalty()` 综合 `status`、`health_score` 和 `load_penalty`。`operator_hold=True`、`status="unavailable"` 或忙碌未结束会直接判定不可行。`degraded/busy` 则表现为更高但仍可能可行的代价。

### 6.5 视场确认难度

`fov_difficulty` 用于表达资源对某目标的末端识别和持续观测难度。它为 D5 预留联动：如果 D5 或二级侦察节点报告某资源视场内目标重叠、遮挡或关联模糊，可通过该项提高对应边成本。

### 6.6 资源间冲突风险

`conflict_risk` 用于惩罚资源空间、视场或任务区域冲突风险。当前实现是边级抽象特征，不计算真实飞行路径冲突；后续如需显式多资源冲突约束，应升级到最小费用流或单独的约束优化层。

### 6.7 不可行惩罚

不可行边赋予 `infeasible_penalty`，且 `_assignments_from_solver()` 会过滤掉高惩罚边。这样求解器可以保持矩阵完整，同时发布计划不会包含不可行 assignment。

## 7. 滚动重分配与迟滞逻辑

每个决策周期，D3 先求解新的候选计划，再把旧计划在当前代价矩阵上重评分。若候选 assignment 与旧 assignment 不同，只有满足以下条件才接受换配：

```text
J_new < (1 - delta) * J_old
and dwell_time > min_dwell
and change_count <= max_changes_per_window
```

其中：

- `J_new` 是候选计划当前成本。
- `J_old` 是旧 assignment 在当前矩阵上的重评分成本。
- `delta` 是相对改善阈值，默认 `0.2`。
- `min_dwell` 是旧计划最短保持时间，默认 `2.0 s`。
- `max_changes_per_window` 可限制单窗口变更边数。

如果旧计划仍可行但候选提升不够，D3 输出新版本计划但保持旧 assignment，`decision_state="held_by_hysteresis"`。如果旧计划不可行，例如资源变为不可用、目标消失或边被标记不可行，则允许接受新计划并标记 `accepted_previous_infeasible`。

版本逻辑是降级场景的关键：D4 使用 D3 计划作为中心化基线时，必须拒绝更旧版本覆盖当前计划。D3 自身也通过 `StalePlanError` 防止 stale previous plan 继续滚动。

## 8. 面向 D4 主动降级的计划有效性判据

D4 的降级可分为两类：一类是中心节点宕机、心跳丢失或通信中断导致的被动降级；另一类是中心节点仍在线，但原 `AssignmentPlan` 在当前态势下已经不可靠，需要主动请求二级节点或分布式协同介入。D3 不直接决定 D4 的降级执行方式，但应提供可审计的计划有效性摘要，帮助 D4 判断是中心滚动重分配即可解决，还是需要进入主动降级仲裁。

### 8.1 D3 可提供的主动降级触发信号

D3 侧建议持续计算以下信号，并写入计划日志或单独的 `AssignmentValiditySummary`：

- `plan_age_s`：当前计划从 `created_at` 到评估时刻的年龄。超过规划周期上限时，优先触发中心重分配；若连续无法生成新计划，再请求 D4 仲裁。
- `plan_version_stale`：调用方持有的 `plan_id/version` 与 D3 最新版本不一致。stale plan 不应被 D4、D5 或二级节点继续当作主计划使用。
- `assignment_cost_growth`：旧 assignment 在当前代价矩阵上的成本增长量，可定义为 `J_old_current - J_old_at_accept`。
- `new_vs_old_cost_ratio`：候选计划与旧计划重评分成本的比值，可定义为 `J_new / max(J_old_current, eps)`。该值明显小于 1 表示中心重分配有收益；该值接近或大于 1 且风险持续升高，说明单纯重分配可能不能解决。
- `resource_state_change_count`：资源状态突变数量，例如 `available -> degraded/unavailable`、`operator_hold=True`、`busy_until` 延长等。
- `window_failure_count`：接近窗口或任务窗口失效的目标数量，例如 `window_cost` 越过不可接受阈值、目标不再 `assignable` 或原边进入 `feasibility_by_resource=False`。
- `hysteresis_hold_count`：迟滞反复保持旧计划的次数。若连续 `held_by_hysteresis` 且 `candidate_total_cost` 持续低于旧计划，说明中心仍可通过解除迟滞或调整权重解决；若保持期间 D5 多帧不一致，则应请求 D4 仲裁。
- `high_threat_unassigned_count`：高威胁目标未分配数量。若中心仍有可用资源且仅因权重导致未分配，优先中心重分配；若资源区域或观测链路不足，转 D4。
- `d2_uncertainty_level`：来自 D2 的关联不确定性、ID Switch 风险或协方差升高摘要。
- `d5_consistency_state`：来自 D5 的末端一致性状态，如 `consistent`、`ambiguous`、`friend_overlap_hold`、`multi_frame_inconsistent`。

这些信号都是离线仿真和候选计划有效性指标，不表示真实处置命令。

### 8.2 `AssignmentValiditySummary` 已实现结构

当前 D3 已实现 `AssignmentValiditySummary`，用于把 main/D4/D6 需要的 P1 运行时摘要从 `AssignmentPlan` 中稳定导出，并同步覆盖 N/M replay 所需的规模和变更计数字段：

```python
AssignmentValiditySummary(
    plan_id: str,
    version: int,
    plan_age_s: float,
    assignment_latency_s: float,
    cost_margin: float,
    stale_plan_version: bool,
    duplicate_assignment_count: int,
    unassigned_high_threat_count: int,
    resource_count: int,
    target_count: int,
    assigned_count: int,
    hysteresis_reject_count: int,
    stale_reject_count: int,
    reassign_count: int,
)
```

导出 helper 为：

```python
summary = assignment_validity_summary_from_plan(
    plan,
    evaluated_at=t_now,
    latest_version=latest_version,
    latest_plan_id=latest_plan_id,
    assignment_latency_s=latency_s,
    tracks=tracks,
    high_threat_threshold=0.7,
)
```

字段含义：

- `plan_age_s`：`evaluated_at - plan.created_at`。
- `assignment_latency_s`：由调用方传入，或通过 `input_timestamp_s`/计划 metadata 派生；缺省为 `0.0`。
- `cost_margin`：优先使用 `previous_total_cost_current - candidate_total_cost`，正值表示候选计划相对旧计划重评分更便宜。
- `stale_plan_version`：调用方提供的最新 `plan_id/version` 与该计划不一致时为真。
- `duplicate_assignment_count`：同一目标被多个资源分配或同一资源被多个目标分配的异常计数。
- `unassigned_high_threat_count`：未分配集合中高威胁目标数量，可由 `tracks` 和 `high_threat_threshold` 或显式 high-threat ID 集合计算。
- `resource_count`、`target_count`、`assigned_count`：按当前输入和输出计划记录真实规模，不假设目标数等于资源数。
- `hysteresis_reject_count`、`stale_reject_count`、`reassign_count`：供 D6 聚合迟滞保持、stale 拒绝和重分配趋势，也供 `summarize_assignment_mismatch_replay(...)` 聚合非等量 N/M replay。

该 summary 只描述计划有效性、成本变化、版本时效和跨模块一致性，不包含真实硬件、火控或自动处置含义。更细的 D2 不确定性、D5 多帧一致性、D4 主动降级执行状态仍由 main/D4 在运行时闭环里聚合。

### 8.3 中心重分配与 D4 主动降级的边界

D3 建议按三层判断：

1. `keep_plan`：计划版本新、`plan_age_s` 在允许范围内、旧 assignment 当前仍可行、D5 多帧一致、D2 不确定性低或中等。此时即使 D1/D2 风险小幅升高，也可通过迟滞保持计划，避免抖动。
2. `central_replan`：中心节点在线，资源和目标仍在中心视野/通信范围内，`J_new` 明显低于 `J_old_current`，或资源状态突变但 Hungarian 能生成可行新计划。此时应由 D3 发布新版本 `AssignmentPlan`，而不是立刻请求 D4 主动降级。
3. `request_d4_arbitration`：中心仍在线，但 D3 发现计划失效不是单次重分配能解决，例如高动态延迟导致计划持续过期、D2 ID/协方差风险高且 D5 多帧不一致、多个资源状态突变使中心计划频繁 stale、或高威胁目标持续未分配。此时 D3 只发出仲裁请求，由 D4 决定降级到二级节点还是完全分布式。

### 8.4 典型组合策略

| D1/D2 风险 | D5 末端一致性 | D3 成本/版本状态 | D3 建议动作 |
|---|---|---|---|
| 协方差升高但 ID 连续 | D5 一致 | 成本轻微升高，计划未 stale | `keep_plan` 或 `central_replan` |
| 关联不确定性升高 | D5 一致 | `J_new` 明显优于旧计划 | `central_replan`，输出新版本 |
| ID Switch 风险高 | D5 多帧不一致 | 旧计划成本恶化或窗口失效 | `request_d4_secondary_node`，请求二级节点利用局部侦察和区域通信仲裁 |
| 资源状态突变较多 | D5 局部一致 | 旧计划不可行，中心可重算 | `central_replan`，标记 `accepted_previous_infeasible` |
| 计划版本频繁 stale | D5 不一致或资源反馈延迟 | 重分配反复被迟滞/版本冲突阻断 | `request_d4_secondary_node` 或 `request_d4_distributed` |
| 高威胁目标持续未分配 | D5 无法确认 | 中心候选计划也不可行 | `hold_for_observation` 并请求 D4 仲裁，不由 D3 本地升级处置 |

核心原则是：D1/D2 风险上升但 D5 仍稳定时，优先保持或中心重分配；D5 连续多帧不一致、友方重叠保持、或 D3 计划代价恶化超过阈值时，D3 应请求 D4 主动降级仲裁。

### 8.5 末端反馈 helper 合同

D3 提供 `evaluate_terminal_feedback(...)` 作为集成层最小 helper，用于把 D5 末端反馈转为保守分配建议：

| D5 反馈或风险 | D3 建议 | 约束 |
|---|---|---|
| `ambiguous` / `hold` / `friend_overlap_hold` | `hold` | 保持原 `assigned_global_track_id`，等待更多证据 |
| `reacquire` | `replan` | 中心重新计算 `AssignmentPlan`，不允许本地换绑 |
| `mismatch` / `multi_frame_inconsistent` / `cross_view_conflict` | `secondary_arbitration` | 请求 D4 二级节点仲裁 |
| `duplicate_terminal_lock_risk=True` | `secondary_arbitration` | 抑制重复锁定，进入二级节点/中心协调 |

该 helper 的输出 `allow_local_rebind` 始终为 `False`，并显式带有 `main_action` 与 `planner_metadata`。`planner_metadata` 当前包含：

- `operator_hold_suggested`：`hold` 时建议 main 将对应资源输入映射为 `ResourceState.operator_hold=True`。
- `prohibit_assignment_suggested`、`prohibited_edges`：`secondary_arbitration` 或重复末端锁定时建议 main 对当前边做禁配/二级仲裁处理。
- `feasibility_suggestion`、`feasibility_by_resource`：用于把禁配或可行性复核写回下一轮 `TargetTrack.feasibility_by_resource`。
- `fov_difficulty_suggestion`、`fov_difficulty_by_resource`：用于把末端视场困难写回下一轮 `TargetTrack.fov_difficulty_by_resource`。
- `d7_gate_action`、`d4_request`：供 main 驱动 D7 gate 或 D4 仲裁请求。

正常态仍采用 Hungarian；复杂约束升级 OR-Tools Min Cost Flow；中心计划不可信但二级节点可用时，优先二级节点仲裁，再进入 CBBA/拍卖式保底。本轮未实现 OR-Tools Min Cost Flow 或 CP-SAT。

### 8.6 建议阈值与仿真记录

具体阈值应在离线实验中扫描，而不是固定为真实系统参数。初始仿真可记录：

- `max_plan_age_s = 2 到 3 个规划周期`。
- `cost_growth_ratio_threshold = 1.25`，即旧计划当前成本较接受时增长 25% 以上时进入重分配检查。
- `new_vs_old_replan_ratio = 0.85`，即候选计划较旧计划有 15% 以上改善时优先中心重分配。
- `d4_arbitration_hold_limit = 3`，即连续多次迟滞保持且跨模块一致性恶化时请求 D4。
- `d5_inconsistent_frame_limit = 3`，即 D5 多帧不一致不再由 D3 单独解释为普通成本波动。

D6 应将这些阈值、触发次数和最终 `recommended_action` 进入批量统计，以比较“中心重分配优先”和“主动降级优先”两类策略的稳定性。

## 9. 实施流程

当前代码路径如下：

1. 调用 `AssignmentPlanner.plan(tracks, resources, timestamp, previous_plan, expected_previous_version)`，先校验 active plan 连续性。
2. `CostModel.build_matrix()` 计算 `M x N` 基础代价矩阵、未分配成本和每条边的分项解释。
3. `_apply_switch_penalty_to_matrix()` 在可行改配边上加入 switch penalty，不修改原资源边、不可行边、新目标边和 dummy 未分配成本。
4. `HungarianAssignmentSolver.solve()` 拼接 dummy 未分配列，并调用 SciPy Hungarian；若 SciPy 不可用，则小规模 fallback 使用动态规划搜索。
5. `_assignments_from_solver()` 将 solver index 输出转为 `Assignment(target_id, resource_id, cost_breakdown)`。
6. `_apply_hysteresis()` 在同一计费矩阵上比较候选计划与旧计划，决定接受、保持或因旧计划不可行而换配。
7. `_remember_plan()` 记录最新 `plan_id/version`，供下一次缺失/stale plan 检查。

核心接口：

```python
plan = planner.plan(
    tracks=tracks,
    resources=resources,
    timestamp=t,
    previous_plan=previous_plan,
    expected_previous_version=previous_plan.version if previous_plan else None,
)
```

## 10. 参数与调参建议

建议按以下顺序调参：

1. 先固定 `CostWeights` 全为 `1.0`，验证 Hungarian 基线能覆盖目标且没有重复分配。
2. 调整 `unassigned_base_cost` 和 `high_threat_threshold`，确保资源不足时高威胁目标不被过度未分配。
3. 扫描 `delta`：`0.1` 响应更快但更易换配，`0.2` 是当前推荐基线，`0.3` 更稳定但可能保持较差旧计划。
4. 扫描 `min_dwell`：建议从 1 到 3 个决策周期开始，避免每帧抖动。
5. 对目标密集、视场混叠场景，提高 `covariance`、`fov`、`conflict` 权重，减少把不确定目标直接推给末端资源的倾向。
6. 若短时间内大量目标交叉导致换配集中，可设置 `max_changes_per_window` 或 `reassignment_switch_penalty`。

所有权重都应记录到实验配置和 D6 日志，避免只报告命中率而无法解释分配行为。

主动降级相关阈值建议单独扫描，不与基础 Hungarian 权重混在一次实验中调整。优先固定 `CostWeights`，再分别扫描 `max_plan_age_s`、`cost_growth_ratio_threshold`、`new_vs_old_replan_ratio`、`d4_arbitration_hold_limit` 和 `d5_inconsistent_frame_limit`，观察重分配次数、D4 仲裁请求次数、计划 stale 次数和 D5 终端一致性变化。

## 11. 仿真验证与图表

当前离线仿真位于 `simulations/run_rolling_assignment.py`。默认配置为：

- 8 个目标、8 个资源。
- 100 秒仿真时长。
- 2 Hz 决策频率。
- 对比无迟滞与 `delta=0.2, min_dwell=2.0`。

运行命令：

```bash
cd research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

实验报告见 `docs/EXPERIMENT_REPORT.md`，自动生成报告见 `results/EXPERIMENT_REPORT_GENERATED.md`。

### 11.1 成本与重分配曲线

![D3 分配成本与重分配曲线](../results/cost_reassignment.png)

该曲线展示迟滞策略降低重分配事件，但会使部分时刻保留旧计划，因此总成本略高。

### 11.2 权重敏感性曲线

![D3 权重敏感性曲线](../results/weight_sensitivity.png)

该曲线用于观察不同代价项权重对平均成本、高威胁未分配比例和重分配次数的影响。后续批量实验应由 D6 汇总多个随机种子下的均值、标准差和置信区间。

## 12. 评估指标

D3 本模块直接关注：

- `reassignment_count`：计划发生实质变更的次数。
- `changed_edges`：目标-资源边变化数量。
- `duplicate_assignment_count`：同一资源或目标被重复分配的异常计数，正常应为 0。
- `unassigned_high_threat_count` / `high_threat_unassigned_ratio`：高威胁目标未分配比例。
- `total_cost` / `average_cost`：采用计划的滚动成本。
- `candidate_total_cost` 与 `previous_total_cost_current`：迟滞决策解释变量。
- `runtime_ms`、`p95_runtime_ms`：规划实时性指标。
- `stale_plan_reject_count`：过期计划拒绝次数，建议由集成测试或 D6 汇总。
- `assignment_validity_state_count`：`valid/replan_recommended/d4_arbitration_requested/invalid_hold` 的计数。
- `d4_arbitration_request_count`：D3 请求 D4 主动降级仲裁的次数。
- `plan_age_violation_count`：计划年龄超过阈值的次数。
- `cost_growth_violation_count`：旧计划当前成本增长超过阈值的次数。
- `hysteresis_repeated_hold_count`：迟滞连续保持且跨模块一致性恶化的次数。

这些指标应通过 D6 统一记录，并与 D2 的 `id_switch_count`、D5 的 `terminal_association_accuracy`、D4 的 `failover_time` 联合分析。

## 13. 跨模块接口关系

### 13.1 与 D2 多目标跟踪

D2 提供稳定 `global_track_id` 和航迹质量。D3 不应自行合并、拆分或重命名目标 ID；如果 D2 报告 ID Switch 风险高，D3 应通过更高 `covariance` 或 `assignable=False` 降低错误分配概率。

### 13.2 与 D4 降级接管

中心节点正常时，D3 的 `AssignmentPlan` 是主计划。中心失效时，D4 应把最新有效版本作为降级协商基线；二级节点或完全分布式 CBBA 只能在版本更新和时效规则内接管，不能用旧版本覆盖新计划。中心恢复后，应对比计划版本、时间戳和 assignment 差异，不应立即强行夺权。

D4 主动降级场景下，D3 应额外提供 `AssignmentValiditySummary` 或等价日志字段。D4 可以按 `recommended_action` 处理：`central_replan` 由 D3 继续发布新版本；`request_d4_secondary_node` 交给二级侦察/区域节点仲裁；`request_d4_distributed` 才进入完全分布式协同。D3 不应越权选择具体降级节点，只提供计划有效性、版本、成本和跨模块一致性证据。

当前 main runtime 已接入中心重规划闭环：`request_center_replan` 完成后会登记新的 `active_plan_owner=center`、`plan_id/version`、`replan_reason`、`supersedes_plan_id`、`supersedes_plan_version` 和 stale/rejected plan 归因。D3 侧只负责继续发布版本化 plan/binding evidence，并保持 stale 版本拒绝。二级 takeover 的 D3 DTO 也已能通过 `prepare_secondary_takeover_plan(...)` 标记 `secondary_plan_v2`、owner/source node、superseded center plan id/version、可选 epoch/lease 和 `allow_local_rebind=False`；main runtime 已记录 secondary owner/version/source。仍待 D4/main 真实多 seed 校准的是二级租约/heartbeat、中心恢复合并、active owner 仲裁和 stale secondary plan runtime 拒绝策略。

若 D4/main 发布二级计划，应在 `AssignmentPlan.metadata["plan_schema"]` 中标记 `secondary_plan_v2`，并提供外部确定的 `source_node_id`/`target_node_id`/`link_type`。D3 的 `AssignmentGuidanceBinding` 会原样携带该 schema、`plan_id` 和 `plan_version`，并保持 `allow_local_rebind=False`；D3 不推断或选择具体二级节点。

### 13.3 与 D5 末端视觉配准

D5 使用 `AssignmentPlan.assignments` 判断某个资源应在视场中锁定哪个 `global_track_id`。D5 可以回传 `TerminalAssociation`、`IdentityClaim`、模糊视场事件或友方重叠状态，D3 可将这些反馈转化为 `fov_difficulty`、`conflict_risk`、`operator_hold` 或 `feasibility_by_resource`。D5 不允许本地改写 D3 的 `global_track_id` 或自行换绑全局 assignment。

对主动降级判断，D5 的一致性比单帧视觉结果更重要。若 D5 仅单帧模糊但后续恢复一致，D3 可保持或重分配；若 D5 连续多帧不一致、出现友方重叠保持或本地 MOT 与全局计划长期冲突，D3 应将 `d5_consistency_state` 写入有效性摘要并建议 D4 仲裁。

### 13.4 与 D6 系统评估

D6 消费 D3 的计划日志、成本分解、版本变化和决策状态。D3 应保证每次规划输出可复现、可追溯，并保留足够元数据支持批量实验对比。

D6 还应统计 `AssignmentValiditySummary` 的状态分布，区分中心滚动重分配、D4 主动降级仲裁和被动失效降级，避免把所有降级都归因于中心节点宕机。

## 14. 局限与后续工作

当前实现的主要局限：

- 代价特征是归一化抽象量，尚未直接接入 D1/D2 的完整协方差矩阵和时间同步信息。
- Hungarian 只表达一对一主分配，不支持容量、备份资源或多窗口全局优化。
- `conflict_risk` 是外部传入的边级摘要，未在 D3 内部计算真实轨迹冲突。
- `human_authorization_state` 当前由 `PlannerConfig` 配置，默认 `required`；模块不实现授权工作流，也不把记录态仿真字段解释为处置授权。
- 离线脚本覆盖 8v8 滚动场景；真实 AirSim/P1 仍需在 2v2、5v5、8v8、非等量 M/N、crossing/dense 场景中做多 seed 校准。
- `AssignmentValiditySummary`、D6-compatible `AssignmentRecord`、N/M replay summary 和 D5 feedback calibration summary 已实现。后续局限在于真实 episode records 是否持续、稳定地写入并能支撑参数标定，而不是 D3 模块缺少数据结构。

后续建议：

- 基于真实 D6 records 和 P1 calibration sweep bundle 复核 D2 ID Switch 风险、D5 duplicate/friend/fov/geometry feedback、禁配边、`operator_hold` 和 D3 迟滞参数的长期权重阈值。
- 配合 D4/main 校准计划版本冲突、二级 owner/lease、中心恢复合并和 stale secondary plan 拒绝策略；D3 不在本模块内实现 runtime 仲裁。
- 在 main 运行时持续调用 D3 侧有效性评估器，输出 `AssignmentValiditySummary`、`AssignmentRecord` 和 D5 feedback calibration/replay summary，并由 D6 统计触发原因。
- P2/非本轮在保持接口不变的前提下实现 OR-Tools 最小费用流可选后端。
- 由 D6 批量运行多随机种子、多权重、多密度场景，输出统一中文实验报告和图表。
