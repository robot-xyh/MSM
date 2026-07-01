# D3 集中式资源-目标分配算法与实施方案

## 1. 模块定位与边界

D3 是集中式资源-目标分配模块，输入来自 D2 的稳定 `GlobalTrack`/`global_track_id` 以及资源状态摘要，输出版本化候选 `AssignmentPlan`，供 D5 末端视觉配准知道“本资源当前应关注哪个全局目标”，也供 D4 在中心节点失效时作为降级协商基线。

本模块只研究离线科研仿真中的抽象候选分配。输出计划必须保持 `human_authorization_state="required"`，不得包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置或绕过授权流程。

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
- `human_authorization_state`：强制输出为 `required`，即候选计划仍需外部授权层处理。

过期版本不得覆盖新版本。`AssignmentPlanner.plan(..., expected_previous_version=...)` 会检查输入旧计划版本；内部还记录最新 `plan_id/version`，若调用方提交 stale plan，则抛出 `StalePlanError`。

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
J = sum_i sum_j x_ij * C_ij + sum_i u_i * U_i
```

`C_ij` 是资源 `j` 处理目标 `i` 的抽象代价，`u_i=1` 表示目标 `i` 被保留为未分配，`U_i` 是未分配惩罚。未分配惩罚随威胁权重上升：

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

## 8. 实施流程

当前代码路径如下：

1. 调用 `AssignmentPlanner.plan(tracks, resources, timestamp, previous_plan, expected_previous_version)`。
2. `CostModel.build_matrix()` 计算 `M x N` 代价矩阵、未分配成本和每条边的分项解释。
3. `HungarianAssignmentSolver.solve()` 拼接 dummy 未分配列，并调用 SciPy Hungarian；若 SciPy 不可用，则小规模 fallback 使用动态规划搜索。
4. `_assignments_from_solver()` 将 solver index 输出转为 `Assignment(target_id, resource_id, cost_breakdown)`。
5. `_apply_hysteresis()` 比较候选计划与旧计划，决定接受、保持或因旧计划不可行而换配。
6. `_remember_plan()` 记录最新 `plan_id/version`，供下一次 stale plan 检查。

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

## 9. 参数与调参建议

建议按以下顺序调参：

1. 先固定 `CostWeights` 全为 `1.0`，验证 Hungarian 基线能覆盖目标且没有重复分配。
2. 调整 `unassigned_base_cost` 和 `high_threat_threshold`，确保资源不足时高威胁目标不被过度未分配。
3. 扫描 `delta`：`0.1` 响应更快但更易换配，`0.2` 是当前推荐基线，`0.3` 更稳定但可能保持较差旧计划。
4. 扫描 `min_dwell`：建议从 1 到 3 个决策周期开始，避免每帧抖动。
5. 对目标密集、视场混叠场景，提高 `covariance`、`fov`、`conflict` 权重，减少把不确定目标直接推给末端资源的倾向。
6. 若短时间内大量目标交叉导致换配集中，可设置 `max_changes_per_window` 或 `reassignment_switch_penalty`。

所有权重都应记录到实验配置和 D6 日志，避免只报告命中率而无法解释分配行为。

## 10. 仿真验证与图表

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

### 10.1 成本与重分配曲线

![D3 分配成本与重分配曲线](../results/cost_reassignment.png)

该曲线展示迟滞策略降低重分配事件，但会使部分时刻保留旧计划，因此总成本略高。

### 10.2 权重敏感性曲线

![D3 权重敏感性曲线](../results/weight_sensitivity.png)

该曲线用于观察不同代价项权重对平均成本、高威胁未分配比例和重分配次数的影响。后续批量实验应由 D6 汇总多个随机种子下的均值、标准差和置信区间。

## 11. 评估指标

D3 本模块直接关注：

- `reassignment_count`：计划发生实质变更的次数。
- `changed_edges`：目标-资源边变化数量。
- `duplicate_assignment_count`：同一资源或目标被重复分配的异常计数，正常应为 0。
- `unassigned_high_threat_count` / `high_threat_unassigned_ratio`：高威胁目标未分配比例。
- `total_cost` / `average_cost`：采用计划的滚动成本。
- `candidate_total_cost` 与 `previous_total_cost_current`：迟滞决策解释变量。
- `runtime_ms`、`p95_runtime_ms`：规划实时性指标。
- `stale_plan_reject_count`：过期计划拒绝次数，建议由集成测试或 D6 汇总。

这些指标应通过 D6 统一记录，并与 D2 的 `id_switch_count`、D5 的 `terminal_association_accuracy`、D4 的 `failover_time` 联合分析。

## 12. 跨模块接口关系

### 12.1 与 D2 多目标跟踪

D2 提供稳定 `global_track_id` 和航迹质量。D3 不应自行合并、拆分或重命名目标 ID；如果 D2 报告 ID Switch 风险高，D3 应通过更高 `covariance` 或 `assignable=False` 降低错误分配概率。

### 12.2 与 D4 降级接管

中心节点正常时，D3 的 `AssignmentPlan` 是主计划。中心失效时，D4 应把最新有效版本作为降级协商基线；二级节点或完全分布式 CBBA 只能在版本更新和时效规则内接管，不能用旧版本覆盖新计划。中心恢复后，应对比计划版本、时间戳和 assignment 差异，不应立即强行夺权。

### 12.3 与 D5 末端视觉配准

D5 使用 `AssignmentPlan.assignments` 判断某个资源应在视场中锁定哪个 `global_track_id`。D5 可以回传 `TerminalAssociation`、`IdentityClaim`、模糊视场事件或友方重叠状态，D3 可将这些反馈转化为 `fov_difficulty`、`conflict_risk`、`operator_hold` 或 `feasibility_by_resource`。D5 不允许本地改写 D3 的 `global_track_id` 或自行换绑全局 assignment。

### 12.4 与 D6 系统评估

D6 消费 D3 的计划日志、成本分解、版本变化和决策状态。D3 应保证每次规划输出可复现、可追溯，并保留足够元数据支持批量实验对比。

## 13. 局限与后续工作

当前实现的主要局限：

- 代价特征是归一化抽象量，尚未直接接入 D1/D2 的完整协方差矩阵和时间同步信息。
- Hungarian 只表达一对一主分配，不支持容量、备份资源或多窗口全局优化。
- `conflict_risk` 是外部传入的边级摘要，未在 D3 内部计算真实轨迹冲突。
- `human_authorization_state` 当前强制为 `required`，模块不实现授权工作流。
- 仿真覆盖 8v8 滚动场景，仍需扩展到不同目标密度、通信降级和 D5 末端模糊反馈闭环。

后续建议：

- 与 D2/D5 建立统一反馈字段，把 ID Switch 风险、终端模糊和友方重叠映射到 D3 代价项。
- 为 D4 增加计划版本冲突和中心恢复合并的集成测试。
- 在保持接口不变的前提下实现 OR-Tools 最小费用流可选后端。
- 由 D6 批量运行多随机种子、多权重、多密度场景，输出统一中文实验报告和图表。
