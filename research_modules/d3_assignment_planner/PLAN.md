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

`PlannerConfig.human_authorization_state` 当前会直接写入 `AssignmentPlan.human_authorization_state`，并同步记录到 `metadata["configured_human_authorization_state"]` 和 `metadata["effective_human_authorization_state"]`。这允许 main runtime 在仿真中使用 `"recorded"` 等记录态授权，而不是让 D3 固定输出 `"required"`。

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

`apply_terminal_feedback_to_planner_inputs()` 已把 D5 feedback metadata 映射为下一轮 D3 DTO：duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False` 并形成禁配边；fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`；friend/hold metadata 写入 `ResourceState.operator_hold=True`。该 helper 始终 `allow_local_rebind=False`，只消费 main/D5 已聚合的 metadata，不自行做视觉身份判断。

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
- `apply_terminal_feedback_to_planner_inputs(...)`：把 D5 duplicate/friend/fov/feasibility metadata 写回下一轮 `TargetTrack[]/ResourceState[]`，让成本矩阵或禁配边实际生效。
- `prepare_secondary_takeover_plan(...)`：在 D4/main 已选定二级节点后，校验新 plan version 大于被 supersede 的中心 plan，并写入 `secondary_plan_v2`、owner/source node、superseded plan id/version、可选 epoch/lease 和 `allow_local_rebind=False`。
- `assignment_validity_summary_from_plan(...)`：导出 `AssignmentValiditySummary(plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`。
- `assignment_records_from_plan(...)`：导出 D6-compatible `AssignmentRecord(timestamp, plan_id, version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`，并携带多 seed current-plan 分组字段：`window_id`、`decision_state`、`changed`、`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`、`assignment_matrix_shape`、`plan_owner/active_plan_owner/owner_node_id`、source/target/link、`plan_schema`、`replan_reason/takeover_reason`、previous/superseded plan id/version、plan costs、`cost_margin` 和 `stale_after_s`。
- `summarize_assignment_mismatch_replay(...)`：从 D6 assignment records 或 summary dict 聚合 N/M replay 字段：`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`。
- `summarize_terminal_feedback_calibration(...)`：输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数，以及 cost/hysteresis 调参建议；该 helper 只给建议，不自动替换默认 `CostWeights`、`PlannerConfig.delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`。
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
- 当前主线剩余风险集中在真实多 seed/N 规模校准和 D5 feedback 权重阈值标定；D3 已把 current-plan owner/version/source、cost gap 和矩阵规模字段导出到 D6 assignment records，过早实现最小费用流会先增加建模复杂度，未必提升当前闭环能力。

计划策略：

- P2/非本轮以 optional dependency 接入 OR-Tools。
- 无 OR-Tools 环境仍保持 Hungarian/fallback 测试通过。
- 只有当容量、备份资源、多窗口或区域配额进入真实仿真输入时，才把 Min-Cost Flow 升为可运行后端。

## 4. 已接入闭环与待校准项

### 4.1 Secondary takeover owner/version 状态

当前 D3 已能识别并转发 `secondary_plan_v2` schema，并在 D7 binding 中携带二级计划的 `plan_id/version/source_node_id/target_node_id/link_type`。`prepare_secondary_takeover_plan()` 补齐了 D3 侧 DTO 规则：二级 plan version 必须大于被 supersede 的中心 plan；`source_node_id/owner_node_id/selected_secondary_node_id` 必须来自 D4/main 传入的 secondary node；metadata 记录 `supersedes_plan_id`、`supersedes_plan_version`、`active_plan_owner="secondary"`、可选 leader epoch/lease，且 `allow_local_rebind=False`。

main runtime 已接入 secondary owner/version/source 记录。D3 侧 remaining work 不再是 DTO 或版本补齐，而是随真实多 seed episode 校准这些记录是否在二级接管、中心恢复和 stale 拒绝场景中稳定出现。

D3 边界保持不变：

- D3 不选择 `selected_secondary_node_id`。
- D3 不维护二级 owner 的实际租约计时、leader 选举或中心恢复合并状态。
- 二级计划发布后，哪些 runtime 版本有效、中心恢复后如何拒绝旧二级计划或合并状态，仍属 main/D4 的 runtime policy，不列为 D3 DTO 缺口。

### 4.2 D4 request_center_replan 中心重规划闭环

D3 的 terminal feedback helper 可以返回 `main_action="replan"` 或 `main_action="secondary_arbitration"`，并在 metadata 中给出 `d4_request`、`d7_gate_action`、禁配边或 `operator_hold` 建议。但当前没有 D3 内部自动调用 D4：

- `request_center_replan` 是否触发，由 main/D4 根据 D3 summary、D5 状态、D2 不确定性和 C2Health 综合决定。
- D3 不直接发 D4 action，不执行 `degrade_to_secondary` 或 `degrade_to_distributed`。
- D3 只能提供版本、成本、stale、重复分配、高威胁未分配和 D5 feedback 证据。
- 当 D4/main 触发 `request_center_replan` 并再次调用 D3 时，D3 会生成新的版本化 `AssignmentPlan`。
- 当前 main runtime 已把该中心重规划接入 AirSim episode bus：触发重规划后，新计划 metadata/log 记录 `replan_reason`、`supersedes_plan_id`、`supersedes_plan_version` 和 `active_plan_owner="center"`。
- D3 侧验收重点变为保持版本递增、stale `previous_plan` 拒绝、`human_authorization_state` 配置透传和 D7 binding 当前版本约束不退化。

### 4.3 真实 AirSim runtime 接线与校准

D3 有 synthetic dry-run adapter，不直接导入 AirSim。真实 AirSim Blocks 的 tick-to-plan-to-gate 闭环由 main/runtime 接线，当前已覆盖 D3 plan/binding/summary/record、D5 feedback writeback、中心重规划 owner/version 和 secondary owner/version 记录。main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动生成 D6 标准报告 bundle；D3 后续重点是消费这些 episode 级 assignment records、feedback records 和 D6 summary 做参数校准，而不是再补接口字段：

- 在 2v2、5v5、8v8、非等量 M/N 和 crossing/dense 场景中跑真实多 seed。
- 检查 D5 feedback writeback 后的 `operator_hold`、`feasibility_by_resource`、`fov_difficulty_by_resource` 是否产生稳定、可解释的重规划结果。
- 检查 center/secondary plan owner、version、source、supersede metadata、cost gap、迟滞决策状态和 D6 assignment records 是否在 episode log 中可稳定聚合。
- 用 D6 指标和 P1 sweep 的 `d6_airsim_calibration` bundle 回看 D3 参数，特别是 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty` 与 D5 feedback 权重阈值；D3 侧已经提供轻量 calibration summary helper，剩余工作是用真实多 seed 数据填充和复核建议。

## 5. 跨模块接口影响

### 5.1 D4 主动/被动降级

被动降级由 D4/C2Health 判断，D3 只提供最新中心计划作为接管基线。主动降级中，D3 应提供：

- `stale_plan_version`：旧版本不得继续驱动 D5/D7。
- `cost_margin`：中心重分配是否有明显收益。
- `duplicate_assignment_count`：非零时优先 hold 或仲裁。
- `unassigned_high_threat_count`：持续非零时需要中心重分配或 D4 仲裁。
- D5 feedback 映射后的 `main_action` 和 `d4_request`。

推荐顺序是：中心仍可用且 Hungarian 能改善时先 `request_center_replan`；中心计划连续 stale、D5 多帧不一致或 D2/D1 不确定性升高时进入 `degrade_to_secondary`/二级仲裁；二级不可用后再由 D4 进入分布式 fallback。

`request_center_replan` 完成后，main/runtime 已把新中心计划登记为 active owner/version，并记录它 supersede 的旧计划版本；D3 只保证新计划版本化和旧计划拒绝。二级 takeover 完成后，D3 可通过 `prepare_secondary_takeover_plan()` 登记 secondary owner/source、superseded center version 和可选 epoch/lease metadata；main/runtime 已接入 secondary owner/version/source 记录，D4/main 仍负责 secondary node 选择、租约执行、当前 owner 仲裁和中心恢复时的 stale secondary plan 拒绝策略。

### 5.2 D5 terminal association

D5 是末端视觉配准模块，不是分配模块。D3 文档和 DTO 必须保持以下约束：

- D5 不重新分配目标。
- D5 不创建、不改写、不换绑 `global_track_id`。
- D3 对 D5 的输入只发布“资源当前应关注哪个全局目标”的版本化 assignment。
- D5 反馈只能通过 main/D3 DTO 映射为下一轮 D3 的 `operator_hold`、`feasibility_by_resource`、`fov_difficulty_by_resource` 或 D4/D7 gate，不允许本地视觉直接改写 assignment。D3 侧 `apply_terminal_feedback_to_planner_inputs()` 已提供该映射，main/runtime 已在 episode bus 中调用和记录；后续 D3 工作是长期标定 `fov_difficulty`、禁配边、hold/replan/secondary_arbitration 阈值和迟滞参数的相互影响。

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

## 7. 当前 P0/P1 缺口与下一步优先级

### P0

- 无 P0 blocker。Hungarian/DP fallback、版本化 `AssignmentPlan`、迟滞与 stale 拒绝、D5 feedback helper/writeback、secondary takeover owner/version DTO、D7 binding 和 D6 export 当前均已实现；后续 P0 工作只要求保持回归测试不退化。

### P1

- 真实多 seed 校准：main runtime 已提供 P1 D4/D5 calibration sweep 和自动 D6 标准报告 bundle；下一步在 AirSim/point-mass 2v2、5v5、8v8、非等量 M/N、crossing/dense 场景中验证 D3 plan/binding/summary/record、D5 feedback writeback、center replan owner/version/source 和 secondary owner/version/source 记录稳定可聚合。
- D5 feedback 权重阈值长期标定：D3 已提供 advisory calibration helper；下一步基于真实 D6 records 扫描 `fov_difficulty_by_resource`、`feasibility_by_resource`、duplicate/friend/hold/reacquire 状态、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，人工复核并收敛 hold/replan/secondary_arbitration 触发阈值。
- 合同保持回归：D7 只接受当前有效 binding/version；D5 不本地 rebind 或改写 `global_track_id`；`AssignmentPlan` 继续版本化并拒绝 stale previous plan；D6 assignment record export 字段保持兼容。

### P2

- OR-Tools Min-Cost Flow 可选后端：实现容量、备份资源、禁配边、分组配额或多窗口约束，并保持 Hungarian 为默认轻量路径。
- 大规模参数扫描：扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数和 assignment quality 的长期对照表。

## 8. 验收命令

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
git diff --check -- research_modules/d3_assignment_planner subagent_reviews/D3_*
```
