# D3 集中式 Assignment Planner 计划

## 1. 模块边界

D3 负责中心节点可用时的抽象资源-目标分配。输入是 D2/main 提供的 `TargetTrack[]`、`ResourceState[]` 和滚动时间戳；输出是版本化 `AssignmentPlan`、D7 可消费的 `AssignmentGuidanceBinding`、D4/D6 可消费的计划有效性摘要和 D6 assignment record。

D3 不负责：

- 末端视觉重绑。D5 可以报告 `ambiguous`、`hold`、`reacquire`、`mismatch`、`cross_view_conflict` 等状态，但 D3 不允许本地资源或末端视觉直接替换 `global_track_id`。
- 改写或重新命名 `global_track_id`。全局航迹 ID 由 D2/中心数据总线维护；D3 只在计划中引用它。
- D4 二级节点选择、CBBA/拍卖式分布式接管、中心恢复仲裁或主动/被动降级执行。
- AirSim Blocks 启停、episode 顺序、真实 runtime 日志采集、D6 存储、真实飞控/硬件/火控/毁伤或绕过人工授权的逻辑。

2v2、5v5 只是 baseline 场景名。运行规模由 main/runtime 的 `--drone-count N` 和输入数组长度决定，D3 不能写死 5v5，也不能假设目标数等于资源数。

## 2. 当前已实现状态

### 2.1 Hungarian / SciPy 主线

当前默认求解器是 `HungarianAssignmentSolver`：

- 优先调用 `scipy.optimize.linear_sum_assignment`。
- 在每个目标后拼接 dummy unassignment 列，支持资源少于目标、目标暂不分配或不可行边过滤。
- 当 SciPy 不可用或测试强制 `allow_scipy=False` 时，使用 `FallbackAssignmentSolver` 的位掩码 DP fallback。
- 代价矩阵尺寸来自 `len(tracks) x len(resources)`，并在计划 metadata 中记录 `assignment_matrix_shape`。

测试覆盖：

- SciPy/fallback 行为：`tests/test_solver.py`。
- 非 5v5 动态规模：`tests/test_planner.py` 中 3 targets / 2 resources，验证 `resource_count=2`、`target_count=3`、`assignment_matrix_shape=[3, 2]`。

### 2.2 版本化 AssignmentPlan

`AssignmentPlan` 当前包含：

- `plan_id`、`version`、`window_id`。
- `resource_count`、`target_count`。
- `assignments`、`unassigned_target_ids`。
- `total_cost`、`candidate_total_cost`、`previous_total_cost_current`。
- `decision_state`、`changed`、`last_changed_at`。
- `source_node_id`、`target_node_id`、`link_type`、`stale_after_s`。

`AssignmentPlanner` 内部记录最新 `plan_id/version`。调用方若传入旧 `previous_plan`，或 `expected_previous_version` 与计划版本不一致，会触发 `StalePlanError`。因此 stale plan 不允许覆盖当前计划。

### 2.3 滚动重分配与迟滞

每个 planning tick 的处理顺序是：

1. `CostModel.build_matrix()` 构建目标-资源代价矩阵和未分配代价。
2. Hungarian/fallback 求解候选计划。
3. 若存在 `previous_plan`，把旧 assignment 在当前矩阵上重评分。
4. 若候选计划与旧计划不同，只有满足收益、驻留时间和变更数量限制才接受。

接受新换配的核心条件：

```text
J_new < (1 - delta) * J_old_current
and dwell_time > min_dwell
and change_count <= max_changes_per_window
```

已实现的决策状态包括：

- `accepted`：首次计划或无迟滞情况下接受。
- `accepted_no_hysteresis`：关闭迟滞后接受候选。
- `unchanged`：候选 assignment 与旧 assignment 一致。
- `held_by_hysteresis`：旧计划仍可行，但收益或驻留时间不足。
- `held_by_change_limit`：收益和驻留时间满足，但单窗口变更边数超过限制。
- `accepted_gain_and_dwell`：收益、驻留时间和变更限制均满足。
- `accepted_previous_infeasible`：旧计划在当前矩阵中不可行，允许绕过迟滞接受候选。

### 2.4 代价函数与输入规模

当前 `CostModel.edge_cost()` 输出可解释 `cost_breakdown`：

- `window`
- `covariance`
- `threat`
- `resource_state`
- `fov`
- `conflict`
- `reassignment_switch_penalty`
- `infeasible`
- `total`

`TargetTrack` 支持 `fov_difficulty_by_resource`、`conflict_risk_by_resource`、`feasibility_by_resource`，可由 main 把 D5/D4/D2 的反馈映射进下一轮 D3 输入。`ResourceState` 支持 `status`、`health_score`、`busy_until`、`operator_hold`、`load_penalty`、`capability_class`。这些字段按输入数组长度运行，不依赖 2v2 或 5v5 常量。

### 2.5 D7 guidance binding

D3 已实现 `guidance_bindings_from_assignment_plan()`：

- 输出 `AssignmentGuidanceBinding`。
- 保留 `plan_id`、`plan_version`、`resource_id`、`assigned_global_track_id`、`target_id`、`authorization_state`、`guidance_phase`。
- 提供 D7 兼容别名：`assignment_id`、`id`、`version`、`track_version`、`owner`、`assigned_resource_id`、`global_track_id`、`human_authorization_state`、`source`、`target`、`link`。
- 支持 `active`、`stale`、`revoked`、`reassigned`、`hold` 状态。
- 在 metadata 中固定 `allow_local_rebind=False`。

D7 PN/PNG gating 的含义是：D7 只能消费当前版本且未被 D4/D5 gate 阻断的 binding；D7 不分配目标、不授权、不改写 `global_track_id`。当 D4 输出 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`，或 D5 未达到 terminal `locked`，D7 应保持/阻断视觉 PNG，而不是自行切换目标。

### 2.6 D4/D5/D6 辅助导出

D3 已实现以下 helper：

- `evaluate_terminal_feedback(...)`：把 D5 反馈映射为 `hold`、`replan` 或 `secondary_arbitration`，始终 `allow_local_rebind=False`。
- `assignment_validity_summary_from_plan(...)`：导出 `AssignmentValiditySummary(plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count)`。
- `assignment_records_from_plan(...)`：导出 D6-compatible `AssignmentRecord(timestamp, plan_id, version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`。
- `AirSimDryRunAssignmentAdapter`：接收 synthetic AirSim-style dict/object，不 import AirSim，不控制 Blocks runtime。

## 3. 部分实现：Min-Cost Flow / OR-Tools

当前 `MinCostFlowAssignmentSolver` 是预留接口，不是可运行求解器：

- 文件存在于 `src/d3_assignment_planner/min_cost_flow.py`。
- `solve()` 会显式抛出 `NotImplementedError`。
- `tests/test_min_cost_flow.py` 验证错误信息，避免调用方误以为 OR-Tools 后端已经接入。

尚未接入 OR-Tools 的原因：

- 当前主线是一对一 optional assignment，Hungarian 已能表达中心化 baseline 和非等量 M/N 场景。
- OR-Tools 依赖未纳入 D3 默认测试环境，贸然加入会影响轻量回归。
- 复杂约束 schema 尚未固定，包括资源容量、目标需求、备份资源、分组配额、禁配边、时间展开网络和整数代价缩放。
- D4 主动/被动降级和 D5 末端反馈闭环尚未完全接入 main runtime，过早实现最小费用流会先增加建模复杂度，未必提升当前闭环能力。

计划策略：

- P1/P2 以 optional dependency 接入 OR-Tools。
- 无 OR-Tools 环境仍保持 Hungarian/fallback 测试通过。
- 只有当容量、备份资源、多窗口或区域配额进入真实仿真输入时，才把 Min-Cost Flow 升为可运行后端。

## 4. 尚未实现的闭环

### 4.1 二级节点完整 plan owner/version 闭环

当前 D3 已能识别并转发 `secondary_plan_v2` schema，并在 D7 binding 中携带二级计划的 `plan_id/version/source_node_id/target_node_id/link_type`。但完整闭环尚未实现：

- D3 不选择 `selected_secondary_node_id`。
- D3 不维护二级 owner 的租约、leader epoch、接管原因或中心恢复合并状态。
- 二级计划发布后，谁是 plan owner、哪些版本有效、中心计划如何被二级计划 supersede、中心恢复后如何拒绝旧二级计划，这些仍属 main/D4 的后续集成。

### 4.2 D4 request_center_replan 自动调用

D3 的 terminal feedback helper 可以返回 `main_action="replan"` 或 `main_action="secondary_arbitration"`，并在 metadata 中给出 `d4_request`、`d7_gate_action`、禁配边或 `operator_hold` 建议。但当前没有 D3 内部自动调用 D4：

- `request_center_replan` 是否触发，由 main/D4 根据 D3 summary、D5 状态、D2 不确定性和 C2Health 综合决定。
- D3 不直接发 D4 action，不执行 `degrade_to_secondary` 或 `degrade_to_distributed`。
- D3 只能提供版本、成本、stale、重复分配、高威胁未分配和 D5 feedback 证据。

### 4.3 真实 AirSim runtime 闭环

D3 有 synthetic dry-run adapter，但真实 AirSim Blocks 的 tick-to-plan-to-gate 闭环仍由 main/runtime 接线：

- main 把 `--drone-count N`、D1/D2 航迹、资源状态、D5 末端反馈转为 D3 输入。
- D3 输出计划、binding、summary、record。
- main/D4/D5/D7/D6 消费这些 DTO 并写统一 episode log。

## 5. 跨模块接口影响

### 5.1 D4 主动/被动降级

被动降级由 D4/C2Health 判断，D3 只提供最新中心计划作为接管基线。主动降级中，D3 应提供：

- `stale_plan_version`：旧版本不得继续驱动 D5/D7。
- `cost_margin`：中心重分配是否有明显收益。
- `duplicate_assignment_count`：非零时优先 hold 或仲裁。
- `unassigned_high_threat_count`：持续非零时需要中心重分配或 D4 仲裁。
- D5 feedback 映射后的 `main_action` 和 `d4_request`。

推荐顺序是：中心仍可用且 Hungarian 能改善时先 `request_center_replan`；中心计划连续 stale、D5 多帧不一致或 D2/D1 不确定性升高时进入 `degrade_to_secondary`/二级仲裁；二级不可用后再由 D4 进入分布式 fallback。

### 5.2 D5 terminal association

D5 是末端视觉配准模块，不是分配模块。D3 文档和 DTO 必须保持以下约束：

- D5 不重新分配目标。
- D5 不创建、不改写、不换绑 `global_track_id`。
- D3 对 D5 的输入只发布“资源当前应关注哪个全局目标”的版本化 assignment。
- D5 反馈只能被 main 映射为下一轮 D3 的 `operator_hold`、`feasibility_by_resource`、`fov_difficulty_by_resource` 或 D4/D7 gate，不允许本地视觉直接改写 assignment。

### 5.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 应满足：

- D3 plan/binding version 当前有效。
- D4 action 允许继续中心计划；若 D4 要求 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`，D7 阻断视觉 PNG。
- D5 terminal association 为 `locked` 且与 `assigned_global_track_id` 一致。
- binding 未 stale、未 revoked、未 hold。

D3 提供 binding 和 gate 证据，但不产生导引律、不执行控制、不授权目标处置。

## 6. N 规模输入策略

D3 所有核心路径按输入列表长度运行：

- `target_count = len(tracks)`。
- `resource_count = len(resources)`。
- `assignment_matrix_shape = [target_count, resource_count]`。
- 当 `target_count > resource_count` 时，dummy unassignment 支持部分目标未分配。
- 当资源不可用、忙碌或 operator hold 时，该资源对应边被判为不可行或高成本。

P1 集成时，main 应保证：

- `--drone-count N` 只决定资源/actor 数量，不进入 D3 算法常量。
- 目标数可大于、小于或等于资源数。
- 2v2、5v5、8v8、非等量 M/N 都使用同一接口。

## 7. 下一步优先级

### P1

- main/runtime 接线：把 AirSim/point-mass episode 中的 tracks/resources/D5 feedback 转为 D3 输入，并记录 D3 plan/binding/summary/record。
- D4 主动降级消费：由 D4/main 根据 `AssignmentValiditySummary`、C2Health、D5 多帧一致性和 D2 不确定性决定 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。
- D5 feedback 闭环：main 消费 `evaluate_terminal_feedback()` metadata，写回下一轮 `ResourceState.operator_hold`、`TargetTrack.feasibility_by_resource`、`TargetTrack.fov_difficulty_by_resource` 和 D7 gate。
- D7 gating 集成测试：验证 stale/revoked/hold/reassigned binding、D4 action 和 D5 lock 状态共同阻断或允许 PN/PNG。
- D6 指标记录：持续统计 `resource_count`、`target_count`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、`reassignment_count`、`secondary_arbitration_count`。

### P2

- 完整 secondary plan owner/version 闭环：由 D4/main 定义二级 owner、epoch、租约、版本 supersede、中心恢复合并和 stale secondary plan 拒绝。
- OR-Tools Min-Cost Flow 可选后端：实现容量、备份资源、禁配边、分组配额或多窗口约束，并保持 Hungarian 为默认轻量路径。
- 多规模参数扫描：覆盖 2v2、5v5、8v8、非等量 M/N、目标交叉和视场混叠场景，扫描 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`。
- D3-D4-D5-D7 联合回归：验证 D5 不一致不会触发本地 rebind，D4 降级 action 会阻断 D7 terminal PNG，D3 stale plan 不能覆盖新版本。

## 8. 验收命令

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
git diff --check -- research_modules/d3_assignment_planner subagent_reviews/D3_*
```
