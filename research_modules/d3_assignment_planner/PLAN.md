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
- 当前 plan metadata 同时记录 D4/D6 可回放的 current cost matrix、target/resource ids、per-edge cost breakdown、hard rejected edges 和 reject reasons；`assignment_evidence_from_plan(...)` 可导出结构化 evidence bundle。

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

`AssignmentPlanner` 内部记录最新 `plan_id/version`。首次调用允许 `previous_plan=None` 并生成 version 1；一旦 planner 记住 active plan，后续调用必须显式传入该 active plan。缺失时抛出 `StalePlanError(reason="previous_plan_required")`，并携带 `latest_plan_id/latest_version`；旧 `previous_plan`、旧 plan id 或不匹配的 `expected_previous_version` 继续按原 reason 拒绝。因此 active version 不会因省略 `previous_plan` 回退到 1。planner 实例对应单个 episode，新 episode 必须由 main 创建新实例，不提供隐式 reset。

`PlannerConfig.human_authorization_state` 当前会直接写入 `AssignmentPlan.human_authorization_state`，并同步记录到 `metadata["configured_human_authorization_state"]` 和 `metadata["effective_human_authorization_state"]`。这允许 main runtime 在仿真中使用 `"recorded"` 等记录态授权，而不是让 D3 固定输出 `"required"`。

### 2.3 滚动重分配与迟滞

每个 planning tick 的处理顺序是：

1. `CostModel.build_matrix()` 构建目标-资源基础代价矩阵和未分配代价。
2. 若存在 `previous_plan`，对已有 target 改配到不同 resource 的可行候选边加入 `reassignment_switch_penalty`；同 resource 边和 unassigned cost 不变。
3. Hungarian/fallback 使用加过 switch penalty 的矩阵求解候选计划。
4. 把旧 assignment 在同一矩阵上重评分；由于旧 resource 边不加 penalty，`J_old_current` 不含虚假切换费。
5. 若候选计划与旧计划不同，只有满足收益、驻留时间和变更数量限制才接受。

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
- `accepted_high_threat_release`：候选计划减少高威胁未分配目标时，允许带原因记录地释放迟滞。

迟滞结果会写入 plan metadata 和 D6 `AssignmentRecord`：`hysteresis_state`、`hysteresis_reason`、`hysteresis_reasons`、`hysteresis_release_reason`、`hysteresis_dwell_time_s`、`hysteresis_min_dwell_s`、`hysteresis_delta`、收益/驻留/变更限制布尔值、candidate change count，以及高威胁 release 前后的未分配计数。这样 D6 可以解释一次 hold 或 release 是由收益不足、min dwell、change limit、旧边不可行还是高威胁保护触发。

### 2.4 代价函数与输入规模

当前 `CostModel.edge_cost()` 输出可解释 `cost_breakdown`：

- `window`
- `covariance`
- `threat`
- `resource_state`
- `resource_energy`
- `resource_availability`
- `resource_current_load`
- `resource_history_failure`
- `fov`
- `conflict`
- `reassignment_switch_penalty`
- `intercept_feasibility`
- `infeasible`
- `total`

`TargetTrack` 支持 `fov_difficulty_by_resource`、`conflict_risk_by_resource`、`feasibility_by_resource`，可由 main 把 D5/D4/D2 的反馈映射进下一轮 D3 输入。`ResourceState` 支持 `status`、`health_score`、`busy_until`、`operator_hold`、`load_penalty`、`capability_class`，并补齐 P0-B 字段：`energy_fraction`、`availability_score`、`current_load`、`history_failure_rate`、`intercept_feasibility_by_target`、`intercept_feasibility_score_by_target`。`CostModel` 将能量、可用性、当前负载、历史失败率纳入 `resource_state`，并把能量耗尽、availability 为零、pair infeasible 和 intercept infeasible 标成硬不可行原因 flag。这些字段按输入数组长度运行，不依赖 2v2 或 5v5 常量。

P1 switch-penalty 矩阵接入已完成：penalty 在 solve 前写入 `CostMatrixResult.matrix` 和对应 edge breakdown，`breakdown["total"]` 与 matrix cell 相等。solver objective、候选 `Assignment.cost`、`candidate_total_cost/total_cost` 和 `AssignmentEvidenceExport` 共用该矩阵，不再在 solve 后追加 penalty，因此不会双重计费。不可行边、同 resource 边、无历史 assignment 的 target 和 `unassigned_costs` 保持原语义。

P0-C threat baseline 由 `compose_threat_score_baseline(...)` 提供：输入关键区接近、TTC、速度、协方差和目标状态，输出 normalized `ThreatScoreBaseline(threat_score, components, weights, reasons, metadata)`。`AirSimDryRunAssignmentAdapter` 在输入没有显式 `threat_score` 时会使用该 helper 生成 baseline，并把 components/reasons 写入 track metadata。完整动态威胁评估、资源状态耦合和 outcome-aware 标定仍是 P1。

`apply_terminal_feedback_to_planner_inputs()` 已把 D5 feedback metadata 映射为下一轮 D3 DTO：duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False` 并形成禁配边；fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`；friend/hold metadata 写入 `ResourceState.operator_hold=True`。该 helper 始终 `allow_local_rebind=False`，只消费 main/D5 已聚合的 metadata，不自行做视觉身份判断。

轻量 hard time-window baseline 已接入 Hungarian 主线，不引入 OR-Tools。`TargetTrack` 可用显式字段或 metadata 描述 `hard_time_window`、`time_window_open_at_s`、`time_window_close_at_s`、`time_window_state` 和按资源的 `time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把对应边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` breakdown flag，planner 不会分配该边，并在 evidence metadata 中记录可解释 `reject_reason`。`window_cost` 仍作为 open edge 的软排序项。

### 2.5 D7 guidance binding

D3 已实现 `guidance_bindings_from_assignment_plan()`：

- 输出 `AssignmentGuidanceBinding`。
- 保留 `plan_id`、`plan_version`、`resource_id`、`assigned_global_track_id`、`target_id`、`authorization_state`、`guidance_phase`。
- 提供 D7 兼容别名：`assignment_id`、`id`、`version`、`track_version`、`owner`、`assigned_resource_id`、`global_track_id`、`human_authorization_state`、`source`、`target`、`link`。
- 支持 `active`、`stale`、`revoked`、`reassigned`、`hold` 状态。
- 在 metadata 中固定 `allow_local_rebind=False`。
- 新 plan 的 binding 即使发生资源-目标改配仍为 `active/current`；旧 plan 由当前 `plan_id/version` gate 判 stale/revoked，不把新 binding 标为 `superseded`。

D7 PN/PNG gating 的含义是：D7 只能消费当前版本且未被 D4/D5 gate 阻断的 binding；D7 不分配目标、不授权、不改写 `global_track_id`。当 D4 输出 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`，或 D5 未达到 terminal `locked`，D7 应保持/阻断视觉 PNG，而不是自行切换目标。

### 2.6 D4/D5/D6 辅助导出

D3 已实现以下 helper：

- `evaluate_terminal_feedback(...)`：把 D5 反馈映射为 `hold`、`replan` 或 `secondary_arbitration`，始终 `allow_local_rebind=False`。
- `apply_terminal_feedback_to_planner_inputs(...)`：把 D5 duplicate/friend/fov/feasibility metadata 写回下一轮 `TargetTrack[]/ResourceState[]`，让成本矩阵或禁配边实际生效。
- `compose_threat_score_baseline(...)`：从关键区接近、TTC、速度、协方差和目标状态组合可解释 threat baseline；不替代 P1 完整动态威胁评估。
- `prepare_secondary_takeover_plan(...)`：在 D4/main 已选定二级节点后，校验新 plan version 大于被 supersede 的中心 plan，并写入 `secondary_plan_v2`、owner/source node、superseded plan id/version、可选 epoch/lease 和 `allow_local_rebind=False`。
- `assignment_validity_summary_from_plan(...)`：导出 `AssignmentValiditySummary(plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`。
- `assignment_records_from_plan(...)`：导出 D6-compatible `AssignmentRecord(timestamp, plan_id, version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`，并携带多 seed current-plan 分组字段：`window_id`、`decision_state`、`changed`、`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`、`assignment_matrix_shape`、`plan_owner/active_plan_owner/owner_node_id`、source/target/link、`plan_schema`、`replan_reason/takeover_reason`、previous/superseded plan id/version、secondary owner/version/epoch/lease、plan costs、`cost_margin`、`stale_after_s`、stale rejection metadata 和迟滞解释字段。
- `assignment_evidence_from_plan(...)`：导出 `AssignmentEvidenceExport`，包含 current plan id/version/owner/source、规模字段、完整 current cost matrix、per-edge cost breakdown、hard rejected edges/reasons、stale rejection reason 和 secondary owner/source/version/supersede 字段。
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

- P1 按既定优先级实现最小可运行的 optional OR-Tools 对照：仅在同一组一对一输入上输出 Hungarian 与 min-cost-flow 计划、成本和求解耗时，不替换默认 Hungarian 主线。
- 无 OR-Tools 环境仍保持 Hungarian/fallback 测试通过。
- 容量、备份资源、多窗口、区域配额和预测性滚动仍属于 P2/P3 复杂约束，不在当前 P1 对照中展开。

## 4. 已接入闭环与待校准项

### 4.1 Secondary takeover owner/version 状态

当前 D3 已能识别并转发 `secondary_plan_v2` schema，并在 D7 binding 中携带二级计划的 `plan_id/version/source_node_id/target_node_id/link_type`。`prepare_secondary_takeover_plan()` 补齐了 D3 侧 DTO 规则：二级 plan version 必须大于被 supersede 的中心 plan；`source_node_id/owner_node_id/selected_secondary_node_id` 必须来自 D4/main 传入的 secondary node；metadata 记录 `supersedes_plan_id`、`supersedes_plan_version`、`active_plan_owner="secondary"`、可选 leader epoch/lease，且 `allow_local_rebind=False`。

main runtime 已接入 secondary owner/version/source 记录。2026-07-10 的 5v5、10-seed、50/200 m、三类降级场景共 60 个真实 AirSim episode 全部连接；但 20 个 `degrade_to_secondary` case 最终均保守转为 `degrade_to_distributed`。1300 条 D4 决策只有 15 条瞬时达到 `takeover_ready`，均停留在 `pending_secondary_plan`，`secondary_plan_active=0`。因此 D3 侧 remaining work 不再是 DTO 或版本字段补齐，而是与 main/D4 共同验收 active-plan activation 合同：持续 readiness 后必须生成并激活严格递增的 secondary plan，旧中心 plan 必须 stale，恢复中心不得覆盖更新的 owner/version。这里保持 D3 侧口径：D3 只校验和盖章 D4/main 传入的 secondary owner，不在模块内选择真实 active owner。

D3 边界保持不变：

- D3 不选择 `selected_secondary_node_id`。
- D3 不维护二级 owner 的实际租约计时、leader 选举或中心恢复合并状态。
- 二级计划发布后，哪些 runtime 版本有效、中心恢复后如何拒绝旧二级计划或合并状态，仍属 main/D4 的 runtime policy，不列为 D3 DTO 缺口。

下一阶段的跨模块验收序列固定为：

```text
takeover_ready (持续满足)
-> prepare_secondary_takeover_plan(version > center version)
-> pending_secondary_plan
-> secondary_plan_active(owner=secondary)
-> old center plan rejected as stale
-> D7 consumes only the current secondary binding
```

### 4.2 D4 request_center_replan 中心重规划闭环

D3 的 terminal feedback helper 可以返回 `main_action="replan"` 或 `main_action="secondary_arbitration"`，并在 metadata 中给出 `d4_request`、`d7_gate_action`、禁配边或 `operator_hold` 建议。但当前没有 D3 内部自动调用 D4：

- `request_center_replan` 是否触发，由 main/D4 根据 D3 summary、D5 状态、D2 不确定性和 C2Health 综合决定。
- D3 不直接发 D4 action，不执行 `degrade_to_secondary` 或 `degrade_to_distributed`。
- D3 只能提供版本、成本、stale、重复分配、高威胁未分配和 D5 feedback 证据。
- 当 D4/main 触发 `request_center_replan` 并再次调用 D3 时，D3 会生成新的版本化 `AssignmentPlan`。
- 当前 main runtime 已把该中心重规划接入 AirSim episode bus：触发重规划后，新计划 metadata/log 记录 `replan_reason`、`supersedes_plan_id`、`supersedes_plan_version` 和 `active_plan_owner="center"`。
- D3 侧验收重点变为保持版本递增、stale `previous_plan` 拒绝、`human_authorization_state` 配置透传和 D7 binding 当前版本约束不退化。

### 4.3 真实 AirSim runtime 接线与校准

D3 有 synthetic dry-run adapter，不直接导入 AirSim。真实 AirSim Blocks 的 tick-to-plan-to-gate 闭环由 main/runtime 接线，当前已覆盖 D3 plan/binding/summary/record/evidence、D5 feedback writeback、中心重规划 owner/version 和 secondary owner/version 记录。2026-07-10 已完成等量 5v5 的 10-seed、50/200 m 校准和 2v2 SimpleFlight 10-seed 执行基线；这证明现有记录链可运行，但不能替代非等量 N/M、D5 feedback 权重和 secondary active-plan 合同校准。D3 后续重点是消费 episode 级 assignment records、feedback records、current-plan evidence 和 D6 summary 做参数校准，而不是重复补已存在的接口字段：

- 在 3v5、5v3、目标新增、资源失效和 crossing/dense 场景中补真实或可回放的非等量 N/M 多 seed 数据，验证 `assigned_count`、高威胁未分配、迟滞、stale rejection 和更新延迟。
- 对 D5 feedback writeback 做受控权重扫描，验证 `operator_hold`、`feasibility_by_resource`、`fov_difficulty_by_resource` 对重规划收益、抖动和高威胁漏分配的影响。
- 构造持续 `takeover_ready` 专项，闭合 `pending_secondary_plan -> secondary_plan_active`，并验证 owner/version/source、supersede、旧中心 stale rejection 和 D7 current binding。
- 校准完整动态威胁模型、增量更新和 hard time-window 到达时间/多窗口输入；所有 reject reason 必须可由 D6 聚合。
- 最后按既定 P1 优先级增加 Hungarian 与 optional OR-Tools min-cost-flow 同输入对照；容量、备份资源和分组配额不进入本阶段。

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

- 旧“无 P0 blocker”结论已撤销。P0 `previous_plan` 连续性缺口已于 2026-07-10 修复并标记 done：首次调用仍允许 `None`；active plan 存在后省略 `previous_plan` 会以 `previous_plan_required` 拒绝并返回 latest plan id/version，版本不会回退到 1；新 episode 使用新 planner 实例。
- 其余 Hungarian/DP fallback、版本化 `AssignmentPlan`、迟滞与 stale 拒绝、D5 feedback helper/writeback、secondary takeover owner/version DTO、D7 binding、D6 export、`AssignmentEvidenceExport` 和轻量 hard time-window closed-edge rejection baseline 当前均已实现并保持回归。
- P0-B 已补齐：`ResourceState` 标准化 energy、availability、intercept feasibility、current load、history failure 字段，`CostModel` 消费这些字段并导出可解释资源状态/不可行原因。
- P0-B 增强迟滞已补齐：保留 switch penalty、min dwell、change limit、旧边不可行 bypass 和 stale 拒绝；新增高威胁 release condition 与 D6 可解释 metadata/export。
- P0-C 已补齐：`compose_threat_score_baseline(...)` 提供关键区接近、TTC、速度、协方差和目标状态的可解释 baseline helper；完整动态威胁评估不并入 P0。

### P1

- D5 feedback 权重标定：基于真实 D6 records 对 `fov_difficulty_by_resource`、禁配边、operator hold 和迟滞参数做配对扫描，验收重分配抖动下降且高威胁未分配不恶化。
- 非等量 N/M 与增量分配：补 3v5、5v3、目标新增和资源失效场景，对比全量重算与局部更新的延迟，同时保持版本递增和 stale 拒绝。
- 完整动态威胁评估：在现有可解释 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，保留 baseline 对照。
- 时间窗口硬约束校准：覆盖到达时间、多窗口、closed/not-yet-open edge 和 reject reason 聚合，不重复实现已有单窗口拒绝 baseline。
- 二级 active plan activation 合同：构造持续 readiness 场景，闭合 `pending_secondary_plan -> secondary_plan_active`，验证唯一 active owner、严格递增 version、旧中心 stale 和 D7 current binding。
- OR-Tools Min-Cost Flow 对照：按既定 P1 优先级实现 optional、同输入的一对一对照，默认仍为 Hungarian；复杂容量/备份/配额保持 P2/P3。
- 合同保持回归：维持 active-plan `previous_plan` 必填、solve 前 switch penalty、D5/D7 禁止本地 rebind 和 D6 record/evidence schema。当前 D3 全量测试基线为 `63 passed`。

### P2

- OR-Tools Min-Cost Flow 可选后端：实现容量、备份资源、禁配边、分组配额或多窗口约束，并保持 Hungarian 为默认轻量路径。
- 大规模参数扫描：扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数和 assignment quality 的长期对照表。

## 8. 验收命令

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
git diff --check -- research_modules/d3_assignment_planner subagent_reviews/D3_*
```
