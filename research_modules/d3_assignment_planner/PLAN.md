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

`AssignmentPlanner` 内部只记录已发布的最新 `plan_id/version`。首次调用允许 `previous_plan=None` 并生成 version 1；`plan(..., publish=False)` 生成的候选不推进 latest，审核或 owner/activation 盖章后由 `publish_plan(...)` 显式发布。已发布 active plan 后，后续调用必须显式传入该 active identity；缺失、旧版本、旧 id 或 `expected_previous_version` 不匹配均按既有 reason 拒绝。

计划 identity 由 `AssignmentPlan.execution_signature()` 和 lineage policy 共同约束。无论 `k=1` 还是 `k>1`，成员、角色、目标、owner、授权和执行状态均未变化时属于 evaluation refresh：保留 `plan_id/version/created_at`、assignment version、成员驻留时钟和 coalition `version/epoch`，仅设置 `evaluation_refresh_only=True` 并刷新成本诊断与 `last_evaluated_at_s`。真实 assignment/owner/activation/coalition 变化才推进执行版本；二级 owner takeover 等明确转换创建新 plan lineage。

M5N2 逐 pair 诊断合同已补齐但不改变上述 identity 规则。`AssignmentRecord` 和 D7 binding metadata 统一携带 plan owner/version、coalition id/version/epoch、member role、wave、activation、validity、`terminal_authorization_scope=per_primary`、授权资格、plan churn、rollback 和 stale reject。两个 primary 分别为 active/current/eligible；未显式激活的 reserve 始终为 standby、不可执行且不具终端授权资格。普通 current evaluation refresh 的 churn 为 0、rollback 为 false，且不重置 plan identity 或 coalition epoch。

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
- `held_by_transient_feedback_dwell`：版本匹配的短暂稳定性不足/reacquire 尚未达到 effective feedback window，旧 primary 可行时保持当前执行签名与 plan version。
- `accepted_transient_feedback_dwell_complete`：连续 transient feedback 达到 effective window，允许绕过普通 cost min dwell 发布候选。
- `accepted_hard_feedback_release`：硬反馈风险已确认但旧边尚未在成本矩阵中标为不可行，允许立即发布候选；若旧边已 hard reject，沿用 `accepted_previous_infeasible`。
- `replan_ack_no_change`：forced replan 已处理，但执行签名未变化，计划 identity 不推进。
- `replan_applied`：forced replan 改变执行签名，计划 identity 推进一次。

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

`apply_terminal_feedback_to_planner_inputs()` 已把 D5 feedback metadata 映射为下一轮 D3 DTO：duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False` 并形成禁配边；fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`；friend/hold metadata 写入 `ResourceState.operator_hold=True`。writeback 还保留 target/resource/source plan version、coalition reason/conflict、stable count 和 required window 的规范化 `terminal_feedback_events`，始终 `allow_local_rebind=False`。`plan()` 与 `plan_incremental()` 在普通 cost hysteresis 前统一执行版本化 transient feedback dwell：`PlannerConfig.transient_feedback_dwell_frames` 默认 2，effective window 取该值与上游 `required_stable_frames` 的最大值；`primary_lock_stability_incomplete`/短暂 `reacquire` 在窗口未满且旧 primary 仍可行时保持原成员，持续到阈值后释放。duplicate/friend conflict、wrong binding、失联、资源不可用、显式禁配或任何旧计划不可行立即绕过 dwell；不匹配 current plan version 的反馈只审计，不参与保护。该策略不降低 D5/D7 视觉门控，也不修改 PNG 核心。

真实 M=5/N=2 复验进一步确认，main event 没有 coalition reason/required stable fields：两个旧 primary 分别为 `consistent/continue`，旧 reserve 为单帧 `hold/hold`。旧逻辑将 reserve 的 `operator_hold` 提升为 whole-coalition infeasibility，因此求解器在替换 reserve 时同时重排 primary。D3 现按 `previous_plan` 的 target/resource/member_role 关联版本匹配事件；当所有旧 primary 均 `consistent/continue`、至少一个旧 reserve 为普通 `hold/hold` 或 `reacquire/replan`、旧 primary 边及能力仍可行且无硬冲突时，在 demand-slot matrix 固定旧 primary 集合，只允许 reserve 正常约束/替换。该规则不依赖 main 新增 reason、required window 或 member_role 字段；primary 自身 failure、duplicate/friend/wrong-binding conflict、primary 不可用、需求变化或 stale feedback 均禁用固定并沿用既定释放策略。

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
- `prepare_secondary_takeover_plan(...)`：在 D4/main 已选定真实二级节点且持续满足 `takeover_ready` 后，要求 candidate 的 `previous_plan_id` 精确指向当前计划、version 严格递增、leader epoch 单调且 lease 在激活时有效；成功后写入 active `secondary_plan_v2`、owner/source、readiness、activation、supersede、epoch/lease 和 `allow_local_rebind=False`。
- `continue_active_secondary_plan(...)`：active owner 已是 secondary 时，把下一普通 rolling candidate 继续盖章为同一 owner；要求 version/supersede 连续、concrete owner/source、readiness sustained、epoch 不倒退以及 previous/new lease 均有效且不回退。这不是新 takeover，不要求 owner 改变。
- `build_p1_assignment_fixtures()`：输出带 schema/profile/version 和 changed-id 合同的 5v5、3v5、5v3、新目标、资源失效、高威胁需求变化、D5 reserve feedback 和 hard-window fixture；标签明确采用 `resources x targets`。
- `run_p1_assignment_calibration_matrix()`：用独立 full/incremental planner 执行同一事件转换，汇总 latency、churn、unassigned high-threat、coalition shortfall、hard-window reject、fallback reason、assignment/cost equivalence 和 role-aware primary 保持；CLI 支持可选 `--output` 持久化同一份 `summary.as_dict()` JSON，并始终保留 stdout；只生成校准证据，不根据单次计时改默认路径。
- `assignment_validity_summary_from_plan(...)`：导出 `AssignmentValiditySummary(plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`。
- `assignment_records_from_plan(...)` / `assignment_evidence_from_plan(...)`：除 current plan、N/M、成本、reject、迟滞和 secondary 字段外，输出 `assignment_profile_schema`、cost/feedback profile id/version、实际 `cost_weights` 和 `planner_thresholds`，供 main/D6 做同 profile 配对标定。
- `summarize_assignment_mismatch_replay(...)`：从 D6 assignment records 或 summary dict 聚合 N/M replay 字段：`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`。
- `summarize_terminal_feedback_calibration(...)`：输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数，以及 cost/hysteresis 调参建议；该 helper 只给建议，不自动替换默认 `CostWeights`、`PlannerConfig.delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`。
- `AirSimDryRunAssignmentAdapter`：接收 synthetic AirSim-style dict/object，不 import AirSim，不控制 Blocks runtime。

## 3. P2 Optional Benchmark：Min-Cost Flow / OR-Tools

当前容量约束对照是隔离 benchmark，不是默认 planner 后端：

- `p2_benchmark.py` 定义一份共享 `CapacityBenchmarkProblem`，同时送入 SciPy Hungarian 和 OR-Tools Min Cost Flow；fixture 为 4 resources / 3 targets / 5 demand slots，HIGH target 使用 `primary+primary+reserve`，资源容量为 `(2,1,1,1)`。
- Hungarian 通过按容量展开资源列求解，当前环境得到 objective `5.6`；Min Cost Flow 直接在 resource-to-sink arc 使用相同容量，不再局限于容量 1。
- `run_p2_capacity_benchmark()` 统一回映原始 resource/target/role，并输出目标值、耗时、assignment、容量和 `objective_delta/objectives_match`。当前环境未安装 OR-Tools，因此 flow outcome 为 `status="unavailable"` 且包含 `unavailable_reason`，不会抛出到 benchmark 调用者。
- `simulations/run_p2_capacity_benchmark.py` 输出结构化 JSON；low-level `MinCostFlowAssignmentSolver` 仍在直接调用且依赖缺失时抛 `OrToolsUnavailableError`。
- `ortools` 不进入默认 requirements，`AssignmentPlanner` 不自动选择该 benchmark。

仍不把 OR-Tools 作为默认路径的原因：

- `k_j=1` 和 demand-slot 高频 baseline 已由 SciPy Hungarian/fallback 覆盖。
- flow adapter 仅比较 demand-slot 容量和成本；role 随 slot 记录，但不表达 coalition 原子启用、committed prefix、波次同步或 reserve 激活逻辑。当前环境尚未产出 installed solver 结果。
- 更强约束应由 CP-SAT/MILP 小规模参考模型验证，不应把 flow benchmark 误称为完整 coalition solver。

计划策略：

- P2 capacity benchmark contract done：同一非等量 N/M、hybrid role 和容量输入可由 SciPy 求解，并可选调用 OR-Tools；缺依赖状态可机读。
- installed OR-Tools 的 objective/assignment 实证仍待隔离环境补跑；无 OR-Tools 环境保持默认全量回归通过。
- CP-SAT/MILP coalition 参考尚未实现；原子 admission、备份资源配额、多窗口、区域配额和预测性滚动仍属于 P2/P3 复杂约束。
- 默认在线路径仍是 SciPy Hungarian/fallback 与显式 demand 的 demand-slot 主线，未被 optional adapter 替换。

## 4. 已接入闭环与待校准项

### 4.1 Secondary takeover owner/version 状态

当前 D3 已闭合模块内 secondary activation 与 same-owner rolling 合同。首次接管使用 `prepare_secondary_takeover_plan()`；后续每次普通 `AssignmentPlanner.plan(previous_plan=active_secondary)` 的 candidate 必须经过 `continue_active_secondary_plan()`，否则 candidate 中的 center 默认 metadata 不代表可执行 owner。continuation helper 从 previous plan 派生 concrete owner/source，校验严格 version/supersede、持续 readiness、epoch 不倒退和 lease 有效/续期。D7 仍只接受显式 current identity，旧版本为 stale。

历史基线（2026-07-10）：main runtime 已接入 secondary owner/version/source 记录，但当时 20 个 `degrade_to_secondary` case 均保守转为 `degrade_to_distributed`，`secondary_plan_active=0`。2026-07-11 P1 验证已进一步通过二级接管和完全分布式的 commit 正例；缺 ACK 时 coalition 中止、D7 许可为 0，fail-closed 通过。该结果证明 D3 版本化 current plan/binding 可被下游 commit gate 正确消费，不把二级节点选择、ACK 协议或恢复仲裁归入 D3。

D3 边界保持不变：

- D3 不选择 `selected_secondary_node_id`。
- D3 校验激活快照中的 lease/epoch 并在 binding 导出时拒绝过期 lease，但不维护 lease 续期、leader 选举或中心恢复合并状态。
- 二级计划发布后，哪些 runtime 版本有效、中心恢复后如何拒绝旧二级计划或合并状态，仍属 main/D4 的 runtime policy，不列为 D3 DTO 缺口。

已验证并保持回归的跨模块合同序列为：

```text
pending_secondary_plan
-> takeover_ready (持续满足)
-> prepare_secondary_takeover_plan(exact supersede, version/epoch monotonic, live lease)
-> secondary_plan_active(owner=concrete secondary node)
-> planner.plan(previous_plan=current secondary)
-> continue_active_secondary_plan(same owner, renewed lease, non-regressing epoch)
-> old center plan rejected as stale
-> D7 consumes only the explicitly current, lease-valid secondary binding
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

D3 有 synthetic dry-run adapter，不直接导入 AirSim。真实 AirSim Blocks 的 tick-to-plan-to-gate 闭环由 main/runtime 接线，当前已覆盖 D3 plan/binding/summary/record/evidence、D5 feedback writeback、中心重规划和 secondary owner/version 记录。2026-07-11 的 5-resource/2-target ComputerVision 10-seed 验证中，T001 双 primary 视觉共识与当前计划授权达到 8/10，seeds 7/27 保留回归；结合保守增量规划和 role-aware primary 保持实现，D3 的 P1 合同层已闭合。二级/分布式 commit 正例和缺 ACK fail-closed 也已通过下游验证。

2026-07-13 已按同一验收口径完成 M5N2 hybrid `2 primary + 1 standby reserve` 的真实 SimpleFlight paired 运行：baseline 与三个候选各 10 seeds，共 40 个 episode；本阶段不要求两个 primary 同时到达。baseline coalition completion 为 `0/10`，`20 m / 3 s / 40 deg` 为 `5/10`，其余两个候选分别为 `2/10` 和 `1/10`，最佳结果未达到 `8/10` 验收门限。该结果证明候选排序与逐 pair 合同能够进入真实 runtime，但不能宣称协同物理闭环已完成。计划版本/stale 拒绝、primary/reserve 角色和 reserve standby 安全合同保持，未发现 reserve 越权执行。

- D3 已提供 8 类 deterministic fixture 和统一 paired runner：覆盖 5v5、3v5、5v3、目标新增、资源失效、高威胁 `2 primary + 1 reserve` 需求变化、D5 reserve hold 与 hard-window；本地 8/8 转换的 full/incremental assignment/cost 等价。下一步将逐时刻 plan history 接入真实 AirSim episode，而不是只保存最终 aggregate。
- D6 已能展开 40 个 M5N2 case 和逐 pair 结果；正式 aggregate 缺少逐时刻 `AssignmentPlan/AssignmentRecord` 历史，因此 membership/version churn 当前必须报告为 `unavailable`，不得推断或补零。
- D3 已验证 duplicate/friend/fov/feasibility 对矩阵、reject、assignment 和迟滞的直接影响；下一步使用逐时刻 D5 feedback、计划版本和 outcome 做权重/迟滞配对扫描，并补真实 3v5、5v3、目标新增、资源失效和需求变化标定。
- 二级/分布式 commit 正例和缺 ACK fail-closed 已覆盖下游 current binding 消费；后续仅继续校准长时 lease、epoch 负例和中心恢复，不重开 D3 P1 合同。
- 校准完整动态威胁模型、增量/全量选择结果和 hard time-window 到达时间/多窗口输入；所有 fallback/reject reason 必须可由 D6 聚合。
- P2 同输入容量 benchmark 合同已完成；installed OR-Tools 求解实证、备份资源配额、分组配额和 CP-SAT/MILP 只进入隔离 benchmark。任何结果都不替换默认在线路径。

## 5. 跨模块接口影响

### 5.1 D4 主动/被动降级

被动降级由 D4/C2Health 判断，D3 只提供最新中心计划作为接管基线。主动降级中，D3 应提供：

- `stale_plan_version`：旧版本不得继续驱动 D5/D7。
- `cost_margin`：中心重分配是否有明显收益。
- `duplicate_assignment_count`：非零时优先 hold 或仲裁。
- `unassigned_high_threat_count`：持续非零时需要中心重分配或 D4 仲裁。
- D5 feedback 映射后的 `main_action` 和 `d4_request`。

推荐顺序是：中心仍可用且 Hungarian 能改善时先 `request_center_replan`；中心计划连续 stale、D5 多帧不一致或 D2/D1 不确定性升高时进入 `degrade_to_secondary`/二级仲裁；二级不可用后再由 D4 进入分布式 fallback。

`request_center_replan` 完成后，main/runtime 已把新中心计划登记为 active owner/version，并记录它 supersede 的旧计划版本；D3 只保证新计划版本化和旧计划拒绝。二级 takeover 完成后，D3 通过 `prepare_secondary_takeover_plan()` 强制登记 concrete secondary owner、精确 supersede、持续 readiness、激活时刻和必填 epoch/lease；main/runtime 仍负责 secondary node 选择、lease 续期、当前 owner 仲裁和中心恢复策略，并在导出 D7 binding 时传入当前 plan id/version。

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

- D5 feedback 治理 fixture done：duplicate/friend/fov/feasibility 已验证能改变矩阵、禁配边、assignment 和迟滞，并输出 profile/version/weights；剩余是真实 D6 records 权重扫描。
- P1 合同层 done：真实 AirSim ComputerVision 的 5-resource/2-target 10 seeds 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。demand-slot、计划 identity/no-change ACK、增量规划和 role-aware primary 保持已闭合。
- 下游合同证据 done：二级接管和完全分布式 commit 正例通过，缺 ACK 时 aborted 且 D7 许可为 0。该证据不把 D4 联盟协议归入 D3，也不等于物理拦截。
- 增量接口 done：`plan_incremental(...)` 用输入指纹验证 changed IDs，在可行二部图的独立连通分量上局部求解，保留未受影响且仍可行的 assignment/coalition member；漏报变更、目标/资源集合变化、需求变化、计划过期、时间相关约束或全局分量均带原因回退标准全量 `plan()`。expected/current version 不一致继续抛带 metadata 的 `StalePlanError`。
- N/M deterministic evidence done：8 类矩阵已覆盖 5v5、3v5、5v3、新目标、资源失效、高威胁需求变化、D5 feedback 和 hard-window；统一 summary 输出增量/全量 latency、churn、unassigned high-threat、coalition shortfall、reject/fallback 和 role-aware primary，8/8 转换 assignment/cost 等价。真实 AirSim 3v5/5v3 和动态事件仍需多 seed 校准。
- P1 物理/长期标定 open：2026-07-13 已完成 40 个真实 SimpleFlight M5N2 episode，最佳 `20 m / 3 s / 40 deg` profile coalition completion 为 `5/10`，其余候选为 `2/10`、`1/10`，baseline 为 `0/10`，未达到 `8/10`。下一步不重复候选接口，而是补逐时刻 plan history、D5 feedback 权重/迟滞和真实动态 N/M 标定。
- 完整动态威胁评估：在现有可解释 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，保留 baseline 对照。
- 时间窗口硬约束校准：覆盖到达时间、多窗口、closed/not-yet-open edge 和 reject reason 聚合，不重复实现已有单窗口拒绝 baseline。
- 二级 active plan runtime 验证：D3 takeover、same-owner continuation 和 current-binding 合同已完成；main/D4 需在 episode bus 调用两个 helper并验证 lease 续期、中心恢复与多 seed。
- 合同保持回归：维持 active-plan `previous_plan` 必填、solve 前 switch penalty、D5/D7 禁止本地 rebind、secondary current/lease/owner gate 和 D6 profile schema；schema v2/M-to-N 回归由 `test_m_to_n_demand_slots.py` 覆盖。

### P2

- OR-Tools Min-Cost Flow：同输入容量 runner、SciPy objective 和结构化 unavailable 已完成；当前环境 installed-only test skip，因此尚不能称为完成了已安装 flow 求解器实证。
- CP-SAT/MILP 小规模参考模型：尚未实现；仅规划为 optional benchmark，用于表达 coalition 原子启用、能力、同步和波次约束，不进入默认 requirements 或在线 planner。
- OR-Tools Min-Cost Flow 扩展研究：共享输入已覆盖单层资源容量；备份资源、分组配额或多窗口只在离线对照中评估，并保持 Hungarian/demand-slot 为默认轻量路径。
- 大规模参数扫描：扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数和 assignment quality 的长期对照表。

### 后续实施顺序

1. 保持 P0 和已完成 P1 接口回归，不重复实现 demand-slot、execution signature、forced replan ACK 或 optional Min-Cost Flow 接口。
2. done：事件驱动 `plan_incremental(...)`、输入快照、连通子图、安全全量回退和增量/全量 summary 已实现并完成 deterministic 测试。
3. next：用真实 3v5、5v3、目标新增、资源失效和高威胁需求变化多 seed 数据校准增量/全量延迟、迟滞、fallback 分布和未分配率；不得用单次延迟自动选择路径。
4. next：用 D6 records 配对标定 D5 feedback、完整动态威胁和 hard-window 输入，同时由 main/D4 验证 secondary active-plan 正负例。
5. P2 容量约束同输入 benchmark 合同已完成；后续补 installed OR-Tools 实证、CP-SAT/MILP coalition 参考、复杂 flow 和大规模参数扫描。任何 optional 结果不得替换默认 Hungarian/demand-slot 主线。

## 8. 验收命令

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
git diff --check -- research_modules/d3_assignment_planner subagent_reviews/D3_*
```

## 9. M 对 N 联盟分配研究计划补充（2026-07-11）

文献与开源审计见 `subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md`。schema v2 与 demand-slot baseline 已于 2026-07-11 实现；本节同步实现状态，不改变既有 P2/P3 范围。

### 9.1 问题定义修正

既有“非等量 N/M”仍是一对一 optional assignment，只说明目标数和资源数可以不相等。新增 M 对 N 能力指目标 `j` 有资源需求 `k_j`；高威胁基准为 `k_j=3`。后续方案必须区分：

- `k_j=1`: 继续使用当前 Hungarian 默认主线。
- `k_j>1`: 形成版本化 coalition，并显式记录 required/assigned/shortfall，禁止把部分联盟记为任务完成。
- 合法 coalition multiplicity 不得计入 `duplicate_assignment_count`；异常超额、同一资源跨联盟冲突仍需记录。

### 9.2 P1 实现状态与后续顺序

1. done：`TargetDemand`、`CoalitionPlan`、成员 role/wave/window、demand summary 和 `AssignmentPlan schema v2` 合同已冻结并实现；`primary_resource_count` 接收 main `--cooperative-primary-count`，校验范围为 `1..k_j`。
2. done：`hungarian_demand_slots` 展开 target slots，按 threat penalty 优先 admission；不足或能力不匹配时整目标剔除并重解，不发布部分 executable assignment。
3. done：迟滞、change count、switch penalty 和 reassign export 使用稳定 set/signature；成员/角色变化才递增 coalition version/epoch，可执行窗口变化递增 plan version，纯成本/诊断重评不递增执行版本。
4. done：D7 multi-binding 与 coalition-aware duplicate 语义已实现；只有 committed/current coalition 可 active，合法 `<=k_j` multiplicity 不计异常。
5. P2 benchmark contract done / installed evidence pending：4-resource/3-target、5-slot hybrid primary+reserve 容量输入已在 SciPy 得到 objective `5.6`；OR-Tools 缺失时输出结构化 `unavailable_reason`，不进入默认 requirements 或默认 planner。当前环境未执行 installed flow 求解。
6. evidence updated：2026-07-13 已完成 baseline 与三个 profile 各 10 seeds、合计 40 个真实 SimpleFlight M5N2 episode；默认保持 `2 primary + 1 standby reserve` 且无同时到达要求。最佳 `20 m / 3 s / 40 deg` 为 `5/10`，其余为 `2/10`、`1/10`，baseline 为 `0/10`，未达 `8/10`。版本/stale/role 合同和 reserve 安全保持。
7. calibration pending：先补逐时刻 plan history，使 D6 可计算 membership/version churn；随后按真实 D5 feedback 校准代价权重与迟滞，并完成 3v5、5v3、目标新增、资源失效和需求变化等动态 N/M 多 seed 标定。本阶段不新增同时到达要求。
8. P2 optional：用 OR-Tools CP-SAT/Pyomo/PuLP 建小规模全局参考模型，对比 demand-slot admission 的最优差距；复杂同步动力学、committed prefix 和 reserve feedback policy 不进入默认在线主线。

### 9.3 跨模块输入与输出边界

- D1/D2 提供航迹状态、协方差和可达时间相关的不确定度，不由 D3 实施协同定位。
- D5 提供多视角一致性和观测几何证据，不允许改写 `global_track_id`。
- D7 提供成员 ETA/可达性并执行具体同步或波次导引；D3 只发布角色和目标时间窗。
- D4 在中心失效时负责 coalition 协商和成员退出后的重构；D3 提供最新中心 coalition plan 作为基线。
- D6 区分合法多资源 coalition 和 duplicate assignment，并评估 demand satisfaction、arrival dispersion、wave interval 和 coalition churn。

### 9.4 P0/P1 状态

- **P0**: 当前无新增 blocker。现有 `k_j=1` Hungarian、plan version、stale rejection、迟滞和 `global_track_id` 约束保持回归。
- **P1 done**: `target_demand=k_j`、可配置 `primary_resource_count`、全有或全无 admission、成员角色、simultaneous/sequential/hybrid 波次、coalition version、coalition-aware duplicate、D7 multi-binding 和 demand summary 已实现并单测。
- **P1 evidence done**: 5-resource/2-target ComputerVision 10-seed 运行中 T001 双 primary 视觉共识与当前计划授权达到 8/10；二级/分布式 commit 正例及缺 ACK fail-closed 通过。D3 P1 合同层闭合。
- **P1 interface done**: `plan_incremental`、changed-set 完整性检查、独立连通分量求解、全量回退原因、M-to-N all-or-none、全局迟滞、版本化 transient feedback dwell、reserve-soft-feedback primary role protection 和增量/全量 comparison summary 已实现。
- **P2 capacity benchmark contract done**: 共享 4-resource/3-target、5-slot hybrid 输入已由 SciPy 求解；optional flow 缺依赖时输出 `unavailable_reason`，installed 实证待补。
- **Regression**: `139 passed, 1 skipped`；唯一 skip 为当前环境缺少 optional OR-Tools 的 installed-only 求解测试。

## 11. 独立 Primary 合同与成员级迟滞（2026-07-12）

- 高威胁默认保持 `2 primary + 1 reserve`。合同显式输出 `terminal_authorization_scope=per_primary`、`arrival_coordination_required=false`；本阶段不要求 primary 同时到达。
- reserve 分配用于容量保留，但 D7 binding 为 `hold/reserve_standby_not_activated`，只有后续新版本改变角色后才能执行。
- `k>1` 成员迟滞按目标维护 `membership_changed_at_s`。当前成员可执行时，未满 2 s 或候选成本改善不超过 20%均保持原成员；资源失效、硬边不可行或 gain+dwell 同时通过才替换。
- 每轮输出 `membership_change_reason`、前后成员集合、成员成本、dwell/gain 判据和 `membership_hold_basis`。普通 evaluation refresh 保持 plan ID/version 与 coalition epoch，只更新非执行诊断。
- 默认 Hungarian/demand-slot solver、威胁 admission 和 all-or-none demand satisfaction 不变。
- **Physical loop evidenced / coalition still open**: 2026-07-13 已完成 40 个真实 SimpleFlight M5N2 episode；最佳 profile 为 `5/10`，未达 `8/10`。下一验收是逐时刻 plan 写盘、membership/version churn 可用性、D5 feedback/dwell 和真实动态 N/M 多 seed 校准，而不是增加同时到达约束。
- **P2 isolated benchmark only**: CP-SAT/MILP 全局参考、复杂 flow、复杂同步动力学和大规模参数扫描不得进入默认 requirements，也不替换 Hungarian/demand-slot 主线。

## 10. P1 M5N2 协同候选预筛（2026-07-12）

### 10.1 D3 已实现

- 新增通用 `CooperativePrescreenCandidate` 和固定 3x3x3 参数网格：末端交接距离 `20/30/40 m`、primary 到达窗口宽度 `3/5/8 s`、接近扇区间隔 `20/40/60 deg`。`candidate_id` 稳定，不包含固定 M/N 数量。
- `demand_for_cooperative_candidate()` 在调用方提供的 `TargetDemand` 上设置 primary 窗口宽度和候选审计字段，保留 required/primary 数、coordination mode、能力、wave interval 和 minimum separation。因此高威胁 `2 primary + 1 reserve` 保持现有合同，其他动态 k 值也走同一接口。
- `export_cooperative_candidate_plan_metadata()` 只导出当前 plan 的 candidate、arrival window、sector separation、member role/wave、plan/coalition version 和 minimum separation。primary 标为 active，reserve/retry 标为 standby；旧 plan、assignment version 或 coalition version 被拒绝。
- `rank_cooperative_candidates()` 只对 main/D6 提供的完整实测数据排序，固定优先级为：零安全违规、coalition completion 最大、pair success 最大、arrival spread 最小、candidate ID 稳定破同分。默认输出前三名，不预测或补齐缺失物理结果。
- Hungarian、demand-slot all-or-none admission、迟滞、版本推进、D5 feedback 和 D7 binding 主线均未修改。

### 10.2 Main/D6 执行结果与后续

1. 真实 AirSim 已完成 baseline 与前三候选各 10 seeds，共 40 个 SimpleFlight episode；两个 primary 独立按 5 m 结果计分，不要求同时到达。
2. coalition completion 分别为：baseline `0/10`、`20 m / 3 s / 40 deg` `5/10`、其余候选 `2/10` 和 `1/10`。最佳 profile 未达到 `8/10`，默认 Hungarian/demand-slot 与当前安全门控不变。
3. 计划版本/stale/role 合同保持；reserve 始终为 standby，未出现 reserve 越权执行。D6 可以展开全部 40 case，但正式 aggregate 没有逐时刻 plan history，membership/version churn 必须标记为 `unavailable`，不能补零。
4. 下一轮由 main 写盘每个 planning tick 的 plan id/version、coalition membership/epoch、D5 feedback、迟滞 decision/reason 和 assignment outcome；D3 用这些证据标定 feedback 权重、`delta/min_dwell/reassignment_switch_penalty` 与动态 N/M 事件。
5. OR-Tools Min-Cost Flow、CP-SAT/MILP 和复杂容量约束保持 P2 optional，只做隔离 benchmark，不进入默认在线路径。
