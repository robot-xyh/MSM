# D3 实现差距审计

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-09
**审计依据**: `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`、`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`、`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`、`EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md`、`research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## 1. 总体结论

D3 当前已经完成中心化一对一资源-目标分配主线：SciPy Hungarian / `linear_sum_assignment`、无 SciPy 时的小规模 DP fallback、滚动重分配、迟滞、防 stale plan、版本化 `AssignmentPlan`、`resource_count/target_count` 和 `assignment_matrix_shape` 规模字段、可解释代价分解、D5 terminal feedback helper、D5 feedback metadata 写回下一轮输入、D4/main 选定 secondary node 后的 `secondary_plan_v2` owner/source/version DTO、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6-compatible `AssignmentRecord` 导出，以及 synthetic AirSim dry-run adapter。2026-07-08 P1 准备小修已把 current-plan owner/version/source、replan/takeover reason、previous/supersede、迟滞决策、矩阵规模、cost gap 和 N/M mismatch replay 字段补入 `AssignmentRecord`，并新增 D5 terminal feedback calibration summary helper。2026-07-09 已补齐 EVAL P0-B baseline：资源状态细化、增强迟滞和 stale rejection release metadata、可解释 threat score baseline helper。当前 P1 小修已补齐 current cost matrix / per-edge cost breakdown evidence export、stale rejection reason 回归、secondary owner/version 校准字段，以及轻量 hard time-window closed-edge rejection baseline。

当前 D3 P0/P1 补齐状态已从“接口缺口”转为“真实 episode 校准”：D5 feedback writeback helper、feedback calibration summary helper、N/M mismatch replay summary、secondary takeover plan DTO/helper、D7 `AssignmentGuidanceBinding`、plan owner/version/source metadata、fallback DP、`AssignmentValiditySummary`、D6-compatible `AssignmentRecord` 导出、`AssignmentEvidenceExport`、P0-B 资源状态细化、P0-B 增强迟滞、P0-B threat baseline 和轻量 hard time-window baseline 均已完成并应保持回归。main runtime 已接入 D5 feedback writeback、center replan owner/version/source、secondary owner/version/source 记录、P1 D4/D5 calibration sweep 和 sweep 后自动生成的 D6 标准报告 bundle。D3-relevant P1 保留为真实多 seed/N 规模日志回灌、D5 feedback 权重阈值人工复核标定、完整动态威胁评估、增量分配、hard time-window 多场景校准和 OR-Tools Min Cost Flow 对照接口。D3 算法按输入数组长度运行，现有测试覆盖非 5v5 的 3 target / 2 resource 场景，5v5 只作为基准规模。

当前 D3 P0/P1 缺口清单：P0 为“无运行级 P0 blocker，P0-B baseline 已闭合并保持回归”；若后续发现资源状态、迟滞/stale rejection、hard time-window rejection 或 threat baseline 在多 seed/N 规模回放中退化，再按 P0 backlog 处理，验收口径以 cost metadata、min dwell/switch penalty/release condition/stale reason、hard reject reason、TTC/关键区接近/速度/协方差/目标状态进入 threat baseline 为准。P1 为真实多 seed AirSim/point-mass 校准、D5 feedback 权重/迟滞阈值人工复核标定、完整动态威胁评估、增量分配、hard time-window 多场景校准、OR-Tools Min Cost Flow 对照接口，以及持续合同回归。OR-Tools 在确认文档中采用 P1 对照/复杂约束升级口径，不是当前 P0 替换 Hungarian 主线；容量/备份资源/分组配额等更复杂约束仍不进入当前 P1 默认主线。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞 | 已实现。支持 `delta`、`min_dwell`、`max_changes_per_window`、`reassignment_switch_penalty`，输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible`、`accepted_high_threat_release` 等决策状态，并导出 held/released 原因 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、旧边不可行或重复资源导致旧计划不可行时可接受新计划。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 `AssignmentPlan` | 已实现。`AssignmentPlan` 有 `plan_id/version/window_id/resource_count/target_count`；planner 内部记录最新 plan/version，并对 stale `previous_plan` 抛出 `StalePlanError`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 不写死 2v2/5v5 | 已实现。矩阵由输入列表长度构建，测试显式验证 3 targets / 2 resources 的 `assignment_matrix_shape=[3, 2]`、`resource_count=2`、`target_count=3`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 可解释代价分解 | 已实现。`CostModel.edge_cost()` 输出 `window/covariance/threat/resource_state/resource_energy/resource_availability/resource_current_load/resource_history_failure/fov/conflict/reassignment_switch_penalty/intercept_feasibility/infeasible/total`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py` |
| 轻量 hard time-window rejection baseline | 已实现。`TargetTrack` 支持全局或按资源的 `hard_time_window/time_window_open_at_s/time_window_close_at_s/time_window_state/time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` flags，planner 不分配该边并在 evidence 中导出 `reject_reason`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| P0-B 资源状态细化 | 已实现。`ResourceState` 补齐 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`，`CostModel` 消费这些字段并输出资源状态子项和不可行原因 flag；dry-run adapter 已映射 synthetic AirSim-style 字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| P0-B 可解释 threat score baseline | 已实现。`compose_threat_score_baseline()` 将关键区接近、TTC、速度、协方差、目标状态组合为可解释 `ThreatScoreBaseline`；adapter 在缺少显式 `threat_score` 时写入 baseline score 和 components/reasons metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| Current plan / cost evidence export | 已实现。planner metadata 记录 current plan id/version/owner/source、完整 cost matrix、target/resource ids、per-edge cost breakdown、rejected edges、hard reject reasons、stale rejection reason 和 secondary owner/source/version/supersede 字段；`assignment_evidence_from_plan()` 导出 `AssignmentEvidenceExport` 供 D4/D6 replay。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D7 guidance binding | 已实现。`guidance_bindings_from_assignment_plan()` 导出 `AssignmentGuidanceBinding`，携带 `plan_id/version/resource_id/assigned_global_track_id/authorization_state/guidance_phase/source/target/link`，并暴露 D7 兼容别名；stale/revoked/hold/reassigned 状态和 current/secondary owner/version metadata 有测试。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py` |
| 授权状态配置透传 | 已实现。`PlannerConfig.human_authorization_state` 会写入 `AssignmentPlan.human_authorization_state`，并记录 `configured_human_authorization_state` 与 `effective_human_authorization_state`，main 可用 `"recorded"` 进行仿真记录态 gating。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback 写回下一轮输入 | 已实现。`apply_terminal_feedback_to_planner_inputs()` 将 duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False`，将 fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`，将 friend/hold metadata 写入 `ResourceState.operator_hold=True`，并保持 `allow_local_rebind=False`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| Secondary takeover DTO | 已实现 D3 侧规则。`prepare_secondary_takeover_plan()` 要求 secondary plan version 大于被 supersede 的中心 plan，写入 `secondary_plan_v2`、owner/source node、superseded plan id/version、secondary plan version、可选 epoch/lease 和 `allow_local_rebind=False`；D7 binding 和 D6 record 携带 secondary owner/version 校准字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段和 N/M replay 字段：`assigned_count/hysteresis_reject_count/stale_reject_count/reassign_count`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现并补齐多 seed current-plan 字段。`assignment_records_from_plan()` 导出 D6-compatible `AssignmentRecord(timestamp, plan id/version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`，并携带 `window_id`、`decision_state`、`changed`、`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`、`assignment_matrix_shape`、plan owner/source/link/schema、`replan_reason/takeover_reason`、previous/superseded plan id/version、secondary owner/version/epoch/lease、plan costs、`cost_margin`、`stale_after_s`、stale rejection metadata 和迟滞 held/released 解释字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback calibration summary | 已实现。`summarize_terminal_feedback_calibration()` 输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数及 cost/hysteresis 建议；`summarize_assignment_mismatch_replay()` 输出 N/M replay summary。helper 只给建议，不自动替换默认权重或迟滞参数。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 已接入但需校准/部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback runtime 消费 | 已完成 D3 helper 与 main/runtime 接线。`evaluate_terminal_feedback()` 已把 `ambiguous/hold/friend_overlap_hold` 映射为 `hold`，`reacquire` 映射为 `replan`，`mismatch/multi_frame_inconsistent/cross_view_conflict` 和 `duplicate_terminal_lock_risk` 映射为 `secondary_arbitration`；`apply_terminal_feedback_to_planner_inputs()` 已能写回下一轮 D3 DTO，并由 main/runtime 在 episode bus 中调用和记录。 | D3 只消费 D5/main 已聚合的 metadata，不自行判断视觉身份、不统计跨资源 duplicate lock，也不改写 `global_track_id`。 | 剩余是多 seed 校准：验证写回后的禁配边、视场难度和 operator hold 是否在不同 N 规模、遮挡和 crossing 场景中稳定改善计划质量。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 `AssignmentValiditySummary`、terminal feedback 中的 `d4_request="secondary_arbitration"`、`prepare_secondary_takeover_plan()`，并配合 main runtime 的 center/secondary owner/version/source 记录。 | D3 不执行二级节点选择、CBBA、拍卖或分布式接管；也不自行发 D4 action，不维护 runtime 租约或中心恢复合并。 | 剩余是跨 seed 验证 owner/version/source、supersede 和 stale 拒绝记录在中心重规划、二级接管、中心恢复场景中稳定可聚合。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord`、`AssignmentEvidenceExport`、validity summary、N/M replay summary 和 feedback calibration summary helper，字段包括 plan id/version、owner/source/schema、replan/takeover reason、previous/supersede、secondary owner/version、resource/target/assigned 规模、hysteresis/stale/reassign 计数、matrix shape、current cost matrix、per-edge cost breakdown、reject reason、stale reason、迟滞决策状态与 held/released 原因、cost gap、authorization state 和 active/truth labels。main runtime 已在 P1 D4/D5 calibration sweep 后自动生成 D6 标准报告 bundle，D3 通过 plan/record/evidence helper 消费这些 episode 级数据。 | D3 不写 D6 存储，也不拥有 episode log 总线；calibration helper 输出建议但不自动改默认参数。 | D3 侧无 record/evidence export P1 缺口；剩余是用真实 D6 聚合结果、P1 sweep bundle 和 episode records 人工复核 D3 权重阈值、hard-window 输入和多 seed 稳定性。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter 和 AirSim integration plan；main runtime 已接入 D5 feedback writeback、center replan owner/version/source、secondary owner/version/source 记录和 P1 D4/D5 calibration sweep。 | D3 不直接导入 AirSim 或控制 Blocks runtime。 | 剩余是多 seed/N 规模校准，不是 D3 DTO 字段缺失。 |
| EVAL P0-B 资源状态细化（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`ResourceState` 现有字段外已补 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`；`CostModel` 消费 energy、availability、load、history failure 和 intercept feasibility，并导出不可行原因 flag。 | 还缺真实 episode 中各字段的阈值标定和跨模块日志分布，不缺 D3 DTO/schema。若字段缺失、cost metadata 丢失或不可行原因不可解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 energy/availability/current_load/history_failure_rate 的默认阈值和 D6 聚合展示，同时保持现有 cost metadata 单元测试回归。 |
| EVAL P0-B 增强迟滞和 stale rejection（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。已有 `delta`、`min_dwell`、`max_changes_per_window`、`reassignment_switch_penalty`、旧边不可行绕过、stale plan 拒绝；新增 high-threat release condition 和 D6 held/released 原因导出。 | 多 seed 标定尚未完成，尤其是 release condition 与 churn/漏分配之间的参数平衡。若 min dwell、switch penalty、release condition 或 stale reason 无法解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，D6 报告同时展示重分配下降、高威胁未分配不升高和 stale rejection reason 可聚合。 |
| EVAL P0-B 可解释 threat baseline（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`compose_threat_score_baseline()` 将接近关键区、TTC、速度、协方差、目标状态合成为可解释 threat score；`TargetTrack.threat_score`、`unassigned_high_threat_count` 和 cost breakdown 继续消费该字段。 | 完整动态威胁评估尚未实现，不应把 baseline 伪装成 outcome-aware 模型。若 TTC、关键区接近、速度、协方差或目标状态无法进入 baseline 解释，再列 P0 backlog。 | 用 D6 多 seed outcome 标定完整模型，并保留 Hungarian/baseline 对照；P0 回归只要求 baseline 组件和 reasons 可解释、可导出。 |
| EVAL P1 完整动态威胁评估 | 未作为完整模型实现。当前仅消费/记录 threat baseline 所需字段。 | 完整威胁模型需要场景定义、保护区、TTC、速度、目标类别、协方差、资源状态和 D6 mission outcome 支撑，不能用单一 `threat_score` 字段伪装完成。 | 先保持 P0-B baseline 可解释，再用 D6 多 seed outcome 标定完整模型，并保留 Hungarian baseline 对照。 |
| EVAL P1 增量分配 | 未实现局部增量策略。当前 `AssignmentPlanner.plan()` 是滚动全量重算，已可处理目标/资源数量变化。 | 新目标突增、资源失效或局部反馈时还没有只重算受影响子图的 plan update 路径和 latency 对照。 | 定义新目标、资源失效、D5 feedback 写回后的增量更新 API；验收重点是 plan update latency 下降且版本/stale 拒绝不退化。 |
| EVAL P1 时间窗口硬约束 | 轻量 baseline 已实现。`TargetTrack.window_cost` 仍是软排序项；新增 hard close/open schema、不可行窗口拒绝、`reject_reason`、cost breakdown flags 和测试。 | 目前是轻量 baseline，不是完整多窗口/到达时间网络；未做真实多 seed 标定，也未接 OR-Tools 复杂约束。 | 用 AirSim/point-mass 多 seed/N 规模回放校准 hard window 输入、到达时间和 reject reason 分布；多窗口/容量/配额后续可进入 optional min-cost-flow 对照。 |
| EVAL P1 OR-Tools Min Cost Flow 对照接口 | 部分实现为边界保留。`MinCostFlowAssignmentSolver` 类和测试存在，`solve()` 显式抛出 `NotImplementedError`，说明 OR-Tools 未安装且当前应使用 Hungarian。 | 三个 patch 均确认 OR-Tools 工程成熟，但 P0/P1/P2 确认文档将其收敛为 P1 对照、复杂约束升级；当前只有 API 边界和失败语义，没有 OR-Tools optional dependency、整数代价缩放、基础网络建图或求解结果解码。 | P1 只要求能在同输入下输出 Hungarian vs min-cost-flow 对照计划；容量、备份资源、多窗口和分组配额属于后续复杂约束，不替代当前 Hungarian 默认主线。 |

## 4. 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|---|
| 完整 runtime secondary takeover 仲裁策略 | D3 侧 owner/source/version DTO 已实现，main runtime 也已接入 secondary owner/version/source 记录；D3 只校验和盖章 D4/main 传入的 secondary owner，secondary node 选择、租约心跳/过期、中心恢复合并和 active owner 仲裁不在 D3 内。 | D3 不是 D4 二级节点选择器，也不拥有中心恢复仲裁。 | D4/main policy 需要继续定义和验证租约、中心恢复合并和 stale secondary plan 拒绝策略；D3 只做多 seed 记录校准。 | 外部 policy，非 D3 DTO 缺口。 |
| CP-SAT / MILP | 未实现，仅在方案文档中作为更复杂离线研究方向。 | 高频滚动主线不需要 MILP；求解时间、建模复杂度和约束定义都未定。 | 需要明确组合约束、求解时间预算、失败降级策略和对比场景。 | P3/低。 |
| D3 内部 CBBA/拍卖 | 未实现，且不建议在 D3 实现。 | D3 是中心化分配模块；中心失效或通信受限后的 CBBA/拍卖属于 D4 分布式 fallback 边界。 | D4 需要以 D3 最新中心计划作为基线实现/对比 CBBA、拍卖或合同网。 | 不列入 D3 优先级。 |
| 直接 AirSim/Blocks import 和控制 | 未实现，且不应放入 D3。 | D3 边界是抽象规划；AirSim launch/reset/episode/log collection 属于 main/runtime。 | main/runtime adapter 提供抽象输入和日志输出。 | 不列入 D3 内部实现。 |

## 5. 未实现原因汇总

1. **模块边界**: D3 只发布中心化候选计划、有效性证据和跨模块 DTO，不执行 D4 降级、D5 视觉改绑、D6 存储或 AirSim runtime 控制。
2. **当前算法需求**: 现阶段资源-目标是一对一匹配，Hungarian 已足够表达；最小费用流、CP-SAT/MILP 要等容量、备份资源、多窗口或分组约束进入场景后才有必要。
3. **依赖策略**: 默认测试保持轻依赖，OR-Tools 未安装；现有 min-cost-flow 文件保留接口边界并用清晰异常避免伪实现。
4. **运行时总线持续校准**: D3 helper 已输出 metadata、summary、record、evidence、binding、N/M replay summary 和 D5 feedback calibration summary；main 已把 D5 feedback writeback、中心重规划 owner/version/source、secondary owner/version/source、P1 D4/D5 calibration sweep 和 D6 标准报告 bundle 接入 AirSim episode state machine。D3 record/evidence 现已补齐 owner/version/source、replan/takeover reason、previous/supersede、secondary owner/version、迟滞决策、N/M replay 计数、current cost matrix、per-edge cost breakdown、hard reject reason、stale reason 和 cost gap 字段，后续重点是多 seed 数据回灌和人工复核。
5. **上游事件缺失**: duplicate terminal lock、D5 连续状态迁移、D2/D1 不确定性摘要和 D4 仲裁结果需要由其他模块或 main 聚合后再反馈给 D3。

## 6. 缺少条件

| 缺少条件 | 影响 |
|---|---|
| 真实多 seed AirSim/point-mass 校准矩阵 | main runtime 已具备 P1 D4/D5 calibration sweep 和 D6 标准报告 bundle；仍需要在更多 N 规模、非等量 M/N、D5 模糊、D2 不确定和 crossing/dense 场景中验证统计稳定性。 |
| D5 feedback 权重阈值长期标定数据 | D3 已能生成 advisory calibration summary；仍需要真实 D6 records 反复校准 `fov_difficulty_by_resource`、禁配边、operator hold、hold/replan/secondary_arbitration 阈值，避免过度重规划或过度 hold。 |
| D5/main duplicate lock 和多帧不一致聚合分布 | D3 不自行判断多资源终端锁定冲突；需要上游持续提供聚合事件，供 D3 权重阈值校准。 |
| P0-B 多 seed 标定证据 | baseline schema/helper 已完成；仍需要覆盖非等量 M/N、资源不足、高威胁目标、D5 模糊和 crossing/dense 场景，用于校准增强迟滞参数、资源状态阈值和 threat score baseline 权重。 |
| P1 增量/hard-window 校准/OR-Tools 输入 schema | 需要定义局部更新事件、hard time-window 多窗口/到达时间校准、整数代价缩放和 optional OR-Tools 依赖边界，保持无 OR-Tools 环境测试仍通过。 |

## 7. 当前 D3 P0/P1 缺口与下一步优先级

1. **P0 运行状态**: 无运行级 P0 blocker。Hungarian、fallback DP、版本化 `AssignmentPlan`、迟滞、stale plan 拒绝、D7 binding、D6 export、current evidence export、P0-B 资源状态细化、P0-B 增强迟滞/stale rejection、P0-B threat baseline 和轻量 hard time-window baseline 均已实现；继续用 D3 单元测试防退化。
2. **P1 真实多 seed 校准**: main/runtime 接线已覆盖 D3 plan/binding/summary/record/evidence、D5 feedback writeback、center replan owner/version/source、secondary owner/version/source、P1 D4/D5 calibration sweep 和自动 D6 标准报告 bundle；后续在 2v2、5v5、8v8、非等量 M/N、crossing/dense 场景中验证统计稳定性。
3. **P1 D5 feedback 权重阈值长期标定**: D3 已提供 advisory helper；继续用真实 D6 records 扫描 `fov_difficulty_by_resource`、`feasibility_by_resource`、duplicate/friend/hold/reacquire 状态、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，人工复核并收敛 hold/replan/secondary_arbitration 触发阈值。
4. **P1 完整动态威胁评估**: 在 P0-B baseline 稳定后，扩展到 TTC、保护区、速度、目标类别、协方差、资源状态和 mission outcome 的可解释评分，并用 D6 outcome 做对照标定。
5. **P1 增量分配**: 当前滚动全量重算保持可用；后续为新目标、资源失效和 D5 feedback 写回增加局部增量策略，验收指标是 plan update latency 下降且版本/stale 拒绝不退化。
6. **P1 时间窗口硬约束**: 轻量 hard window open/close schema、拒绝原因和 closed-edge 禁配 baseline 已完成；后续校准多 seed/N 规模、到达时间、多窗口和与 optional min-cost-flow 复杂约束的对照。
7. **P1 OR-Tools Min Cost Flow 对照接口**: 当前只有 reserved solver 和显式 `NotImplementedError`；后续以 optional dependency 接入最小可运行 min-cost-flow 对照计划，保持 Hungarian 为默认主线，容量/备份资源/分组配额不进入当前 P1 默认范围。
8. **P1 合同保持回归**: D7 只有在 D3 version 当前、binding 未 stale/revoked/hold、D4 action 允许且 D5 terminal association 为 `locked` 时进入视觉 PNG；D5/D7 不得自行换绑目标；D3 stale previous plan 继续被拒绝。
9. **P2 大规模参数扫描**: 扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数、资源状态阈值、threat baseline 权重和 assignment quality 的长期对照表。

## 8. 跨模块接口影响

### 8.1 D4 主动/被动降级

被动降级由 D4 的 C2Health、通信和进程状态触发，D3 只提供最新中心 `AssignmentPlan` 作为接管基线。主动降级时，D3 的影响是提供证据而不是执行动作：`AssignmentValiditySummary`、`d4_request`、stale/version 状态、成本 margin、重复分配和高威胁未分配计数。若中心仍可用且 Hungarian 能明显改善，D4/main 应优先 `request_center_replan`；该请求完成后 main/runtime 已记录新的中心 plan owner、`plan_id/version`、`replan_reason`、superseded 旧计划和 stale 拒绝结果。若 D5 多帧不一致、D2/D1 不确定性高或计划持续 stale，再进入二级仲裁；secondary owner/version/source runtime 记录已接入，真实 secondary owner 选择、租约和中心恢复合并策略仍由 D4/main 负责，D3 侧只提供 DTO/helper 和多 seed 记录校准。

### 8.2 D5 terminal association

D5 只做末端视觉配准和一致性证据。D3 给 D5 的 assignment 是“资源当前应关注的 `global_track_id`”，不是允许 D5 改绑的授权。D5 反馈被 D3 helper 转为 `hold/replan/secondary_arbitration` 建议，并可通过 `apply_terminal_feedback_to_planner_inputs()` 写回下一轮 `operator_hold`、禁配边或视场难度；main/runtime 已负责调用和记录。D3 文档和 DTO 均明确 `allow_local_rebind=False`，后续重点是用真实多 seed 结果长期标定 D5 feedback 权重阈值。

### 8.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 只消费当前版本 binding。D3 binding 为 D7 提供 `plan_id/version/resource_id/assigned_global_track_id/guidance_phase/binding_state`，但不提供导引律或处置授权。D7 必须同时检查 D3 version、D4 action 和 D5 lock 状态；遇到 stale/revoked/hold/reassigned、D4 `request_center_replan/degrade_*` 或 D5 未锁定时阻断视觉 PNG。

### 8.4 N 规模输入

D3 的 `target_count/resource_count` 来自输入数组长度。main 的 `--drone-count N` 只决定资源状态记录数量；目标数可以大于、小于或等于资源数。2v2 和 5v5 只作为 baseline 名称，非等量 M/N 也应通过同一 `AssignmentPlanner.plan()` 路径。

## 9. 关键依据路径

- `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`: SciPy Hungarian、dummy unassignment、DP fallback。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`: 滚动 plan、迟滞、版本推进、stale previous plan 拒绝、规模 metadata。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`: 代价矩阵和 cost breakdown。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`: `AssignmentPlan`、D5 feedback decision/writeback、secondary takeover DTO、D7 binding、`AssignmentValiditySummary`、D6 `AssignmentRecord`。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`: OR-Tools Min Cost Flow 保留接口。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`: synthetic AirSim dry-run adapter。
- `research_modules/d3_assignment_planner/tests/test_planner.py`: 非 5v5 规模、迟滞、stale plan、cross-node fields。
- `research_modules/d3_assignment_planner/tests/test_solver.py`: Hungarian/fallback 行为。
- `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`: D5 feedback 映射、写回下一轮输入和不允许 local rebind。
- `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`: D7 binding stale/revoked/hold/reassigned/secondary takeover schema/owner/source/version。
- `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`: validity summary 和 D6 assignment record export。
- `research_modules/d3_assignment_planner/tests/test_min_cost_flow.py`: OR-Tools 未实现接口的显式异常。
