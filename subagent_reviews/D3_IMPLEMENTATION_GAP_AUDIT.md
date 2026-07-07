# D3 实现差距审计

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-06
**审计依据**: `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## 1. 总体结论

D3 当前已经完成中心化一对一资源-目标分配主线：SciPy Hungarian / `linear_sum_assignment`、无 SciPy 时的小规模 DP fallback、滚动重分配、迟滞、防 stale plan、版本化 `AssignmentPlan`、`resource_count/target_count` 和 `assignment_matrix_shape` 规模字段、可解释代价分解、D5 terminal feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6-compatible `AssignmentRecord` 导出，以及 synthetic AirSim dry-run adapter。

当前未完成或仅部分完成的内容集中在运行时闭环和复杂约束：OR-Tools Min Cost Flow 只有保留接口，尚未接入 OR-Tools 依赖和可运行建图；D5 feedback 只输出保守 metadata，不在 D3 内自动改写下一轮成本；`secondary_plan_v2` 只有 schema/binding 兼容，没有完整二级 owner/version 闭环；D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 仍需 main/D4 消费 D3 证据后触发；D3 不直接接 AirSim/Blocks runtime；重复 terminal lock 聚合、D6 episode 日志写入由 main/D4/D5/D6 消费 D3 输出完成。D3 算法按输入数组长度运行，现有测试覆盖非 5v5 的 3 target / 2 resource 场景，5v5 只作为基准规模。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞 | 已实现。支持 `delta`、`min_dwell`、`max_changes_per_window`，输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible` 等决策状态。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、旧边不可行或重复资源导致旧计划不可行时可接受新计划。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 `AssignmentPlan` | 已实现。`AssignmentPlan` 有 `plan_id/version/window_id/resource_count/target_count`；planner 内部记录最新 plan/version，并对 stale `previous_plan` 抛出 `StalePlanError`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 不写死 2v2/5v5 | 已实现。矩阵由输入列表长度构建，测试显式验证 3 targets / 2 resources 的 `assignment_matrix_shape=[3, 2]`、`resource_count=2`、`target_count=3`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 可解释代价分解 | 已实现。`CostModel.edge_cost()` 输出 `window/covariance/threat/resource_state/fov/conflict/reassignment_switch_penalty/infeasible/total`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py` |
| D7 guidance binding | 已实现。`guidance_bindings_from_assignment_plan()` 导出 `AssignmentGuidanceBinding`，携带 `plan_id/version/resource_id/assigned_global_track_id/authorization_state/guidance_phase/source/target/link`，并暴露 D7 兼容别名；stale/revoked/hold/reassigned 状态有测试。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现。`assignment_records_from_plan()` 导出 D6-compatible `AssignmentRecord(timestamp, plan_id, version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback | `evaluate_terminal_feedback()` 已把 `ambiguous/hold/friend_overlap_hold` 映射为 `hold`，`reacquire` 映射为 `replan`，`mismatch/multi_frame_inconsistent/cross_view_conflict` 和 `duplicate_terminal_lock_risk` 映射为 `secondary_arbitration`；始终 `allow_local_rebind=False`，并输出 `main_action/planner_metadata`。 | D3 只产生保守建议，不在本模块内自动改写下一轮 `TargetTrack.fov_difficulty_by_resource`、`feasibility_by_resource` 或 `ResourceState.operator_hold`。这是模块边界要求，避免 D5 本地视觉直接改绑 `global_track_id`。 | main 需要消费 `planner_metadata`，把建议写入下一轮 D3 输入、D7 gate 或 D4 仲裁请求；D5/main 需要提供连续反馈和 duplicate lock 聚合事件。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 `AssignmentValiditySummary` 和 terminal feedback 中的 `d4_request="secondary_arbitration"`。 | D3 不执行二级节点选择、CBBA、拍卖或分布式接管；这些属于 D4/main。 | D4/main 需要消费 D3 summary，决定 `central_replan/secondary_arbitration/distributed_arbitration/hold_for_observation`，并写入 D6 指标。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord` 和 validity summary 导出 helper。 | D3 不写 D6 存储，也不拥有 episode log 总线。 | main/orchestrator 需要把 D3 records/summary 写入统一 episode log，D6 再批量消费。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter 和 AirSim integration plan。 | D3 不直接导入 AirSim 或控制 Blocks runtime，当前没有真实 AirSim tick 到 D3 输入再到 D4/D5/D7/D6 的完整接线。 | main/AirSim adapter 需要把 runtime actor/camera/track/resource 状态转换为 D3 synthetic records，并把 plan/binding 写回系统状态机。 |
| OR-Tools Min Cost Flow | 部分实现为边界保留。`MinCostFlowAssignmentSolver` 类和测试存在，`solve()` 显式抛出 `NotImplementedError`，说明 OR-Tools 未安装且当前应使用 Hungarian。 | 只有 API 边界和失败语义，没有 OR-Tools 依赖、整数代价缩放、容量/需求/禁配边/time-expanded network 建图或求解结果解码。 | 需要先确定容量、备份资源、多窗口或分组配额是否进入 P1/P2 场景；再以 optional dependency 接入 OR-Tools，保持无 OR-Tools 环境测试通过。 |

## 4. 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|---|
| 二级节点完整 secondary plan owner/version 闭环 | 未实现。D3 测试覆盖 `secondary_plan_v2` schema 被 binding 携带，但没有完整 owner、epoch、租约、版本 supersede、中心恢复合并或 stale secondary plan 拒绝逻辑。 | D3 不是 D4 二级节点选择器，也不拥有中心恢复仲裁。当前只能把外部已发布的 secondary plan 作为版本化 DTO 转给 D7/D6。 | D4/main 需要定义 `selected_secondary_node_id`、plan owner、有效期、接管原因、中心/二级版本冲突规则和恢复合并规则。 | P2。 |
| D4 `request_center_replan` 自动调用 | 未实现。D3 helper 可返回 `main_action="replan"`、`d4_request="secondary_arbitration"` 或 gate metadata，但不会直接调用 D4 action。 | D4 action 需要同时看 C2Health、D1/D2 不确定性、D5 多帧一致性、资源覆盖和 runtime 状态；D3 只拥有 assignment 证据。 | main/D4 需要消费 `AssignmentValiditySummary` 和 D5 feedback metadata，自动选择 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`，并把结果写入 D6。 | P1。 |
| CP-SAT / MILP | 未实现，仅在方案文档中作为更复杂离线研究方向。 | 高频滚动主线不需要 MILP；求解时间、建模复杂度和约束定义都未定。 | 需要明确组合约束、求解时间预算、失败降级策略和对比场景。 | P3/低。 |
| D3 内部 CBBA/拍卖 | 未实现，且不建议在 D3 实现。 | D3 是中心化分配模块；中心失效或通信受限后的 CBBA/拍卖属于 D4 分布式 fallback 边界。 | D4 需要以 D3 最新中心计划作为基线实现/对比 CBBA、拍卖或合同网。 | 不列入 D3 优先级。 |
| 直接 AirSim/Blocks import 和控制 | 未实现，且不应放入 D3。 | D3 边界是抽象规划；AirSim launch/reset/episode/log collection 属于 main/runtime。 | main/runtime adapter 提供抽象输入和日志输出。 | 不列入 D3 内部实现。 |

## 5. 未实现原因汇总

1. **模块边界**: D3 只发布中心化候选计划、有效性证据和跨模块 DTO，不执行 D4 降级、D5 视觉改绑、D6 存储或 AirSim runtime 控制。
2. **当前算法需求**: 现阶段资源-目标是一对一匹配，Hungarian 已足够表达；最小费用流、CP-SAT/MILP 要等容量、备份资源、多窗口或分组约束进入场景后才有必要。
3. **依赖策略**: 默认测试保持轻依赖，OR-Tools 未安装；现有 min-cost-flow 文件保留接口边界并用清晰异常避免伪实现。
4. **运行时总线未统一**: D3 helper 已输出 metadata、summary、record 和 binding，但需要 main 把这些字段接入同一 AirSim episode state machine 和 D6 日志。
5. **上游事件缺失**: duplicate terminal lock、D5 连续状态迁移、D2/D1 不确定性摘要和 D4 仲裁结果需要由其他模块或 main 聚合后再反馈给 D3。

## 6. 缺少条件

| 缺少条件 | 影响 |
|---|---|
| main/AirSim adapter 将 `--drone-count N` runtime 状态转成 D3 `TargetTrack[]/ResourceState[]` | D3 只能做 offline/synthetic dry-run，无法形成真实 Blocks episode 闭环。 |
| main 消费 D5 feedback metadata 并写回下一轮 D3 输入 | `hold/replan/secondary_arbitration` 仍停留在建议层，不能自动影响后续成本矩阵。 |
| D5/main 提供 duplicate lock 和多帧不一致聚合事件 | D3 不能自行判断多资源终端锁定冲突。 |
| D4 消费 `AssignmentValiditySummary` 并输出主动降级动作 | D3 只能导出证据，不能完成二级仲裁或分布式降级。 |
| D4/main 定义 secondary plan owner/version 闭环 | `secondary_plan_v2` 只能作为 binding schema 被转发，无法完成二级节点接管后的计划所有权和版本仲裁。 |
| main/D4 自动触发 `request_center_replan` | D3 的 `replan` 建议不能自动转换为中心重规划 action 或降级 action。 |
| main/D6 写入并消费 `AssignmentRecord` 和 validity summary | D6 assignment/failover 指标无法从真实 episode 中稳定聚合。 |
| OR-Tools 依赖与复杂约束 schema | Min Cost Flow 后端无法实现为可运行求解器。 |

## 7. 下一步优先级

1. **P0 保持回归**: 继续跑 D3 单元测试，保证 Hungarian、fallback DP、迟滞、stale plan 拒绝、D7 binding、D6 export 不退化。
2. **P1 main 接线**: 由 main/runtime 把 AirSim `--drone-count N` 状态转为 D3 tracks/resources，并把 `AssignmentPlan`、`AssignmentGuidanceBinding`、`AssignmentValiditySummary`、`AssignmentRecord` 写入 D4/D5/D7/D6 流；`N` 只影响输入数量，不进入算法常量。
3. **P1 D5 feedback 闭环**: main 消费 `evaluate_terminal_feedback()` 的 metadata，将 `operator_hold`、`feasibility_by_resource`、`fov_difficulty_by_resource`、`prohibited_edges` 映射到下一轮 D3 输入和 D7 gate；D3/D5 均不得本地改写 `global_track_id`。
4. **P1 D4/D6 有效性消费**: D4 使用 `AssignmentValiditySummary` 判断 `request_center_replan`、二级仲裁或分布式降级；D6 记录 `stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、`resource_count`、`target_count` 等指标。
5. **P1 D7 PN/PNG gating 集成**: D7 只有在 D3 version 当前、binding 未 stale/revoked/hold、D4 action 允许且 D5 terminal association 为 `locked` 时进入视觉 PNG；否则保持 PN/hold/reacquire，不得自行换绑目标。
6. **P2 secondary plan owner/version 闭环**: 由 D4/main 定义二级节点 owner、epoch、租约、版本 supersede、中心恢复合并和 stale secondary plan 拒绝；D3 继续只转发版本化 evidence/binding。
7. **P1/P2 OR-Tools 后端**: 只有在需要容量、备份资源、时间窗或分组配额时实现 `MinCostFlowAssignmentSolver`；保持 optional dependency，环境无 OR-Tools 时测试仍通过。
8. **P2 压测与参数扫描**: 在 2v2、5v5、8v8、非等量 M/N 和 crossing/dense 场景中扫描 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，把结果交给 D6 汇总。

## 8. 跨模块接口影响

### 8.1 D4 主动/被动降级

被动降级由 D4 的 C2Health、通信和进程状态触发，D3 只提供最新中心 `AssignmentPlan` 作为接管基线。主动降级时，D3 的影响是提供证据而不是执行动作：`AssignmentValiditySummary`、`d4_request`、stale/version 状态、成本 margin、重复分配和高威胁未分配计数。若中心仍可用且 Hungarian 能明显改善，D4/main 应优先 `request_center_replan`；若 D5 多帧不一致、D2/D1 不确定性高或计划持续 stale，再进入二级仲裁；二级不可用后才进入分布式 fallback。

### 8.2 D5 terminal association

D5 只做末端视觉配准和一致性证据。D3 给 D5 的 assignment 是“资源当前应关注的 `global_track_id`”，不是允许 D5 改绑的授权。D5 反馈被 D3 helper 转为 `hold/replan/secondary_arbitration` 建议；真正写回 `operator_hold`、禁配边或视场难度的是 main 下一轮输入映射。D3 文档和 DTO 均明确 `allow_local_rebind=False`。

### 8.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 只消费当前版本 binding。D3 binding 为 D7 提供 `plan_id/version/resource_id/assigned_global_track_id/guidance_phase/binding_state`，但不提供导引律或处置授权。D7 必须同时检查 D3 version、D4 action 和 D5 lock 状态；遇到 stale/revoked/hold/reassigned、D4 `request_center_replan/degrade_*` 或 D5 未锁定时阻断视觉 PNG。

### 8.4 N 规模输入

D3 的 `target_count/resource_count` 来自输入数组长度。main 的 `--drone-count N` 只决定资源状态记录数量；目标数可以大于、小于或等于资源数。2v2 和 5v5 只作为 baseline 名称，非等量 M/N 也应通过同一 `AssignmentPlanner.plan()` 路径。

## 9. 关键依据路径

- `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`: SciPy Hungarian、dummy unassignment、DP fallback。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`: 滚动 plan、迟滞、版本推进、stale previous plan 拒绝、规模 metadata。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`: 代价矩阵和 cost breakdown。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`: `AssignmentPlan`、D5 feedback decision、D7 binding、`AssignmentValiditySummary`、D6 `AssignmentRecord`。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`: OR-Tools Min Cost Flow 保留接口。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`: synthetic AirSim dry-run adapter。
- `research_modules/d3_assignment_planner/tests/test_planner.py`: 非 5v5 规模、迟滞、stale plan、cross-node fields。
- `research_modules/d3_assignment_planner/tests/test_solver.py`: Hungarian/fallback 行为。
- `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`: D5 feedback 映射和不允许 local rebind。
- `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`: D7 binding stale/revoked/hold/reassigned/secondary plan schema。
- `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`: validity summary 和 D6 assignment record export。
- `research_modules/d3_assignment_planner/tests/test_min_cost_flow.py`: OR-Tools 未实现接口的显式异常。
