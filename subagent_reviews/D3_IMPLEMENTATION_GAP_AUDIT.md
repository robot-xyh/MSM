# D3 实现差距审计

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-11
**审计依据**: `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`、`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`、`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`、`EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md`、`research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## 1. 总体结论

D3 当前已经完成中心化一对一资源-目标分配主线：SciPy Hungarian / `linear_sum_assignment`、无 SciPy 时的小规模 DP fallback、滚动重分配、迟滞、防 stale plan、版本化 `AssignmentPlan`、`resource_count/target_count` 和 `assignment_matrix_shape` 规模字段、可解释代价分解、D5 terminal feedback helper、D5 feedback metadata 写回下一轮输入、D4/main 选定 secondary node 后的严格 `secondary_plan_v2` activation/current-binding 与 same-owner rolling continuation 合同、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6-compatible `AssignmentRecord` 导出，以及 synthetic AirSim dry-run adapter。2026-07-10 复核撤销了旧“无 P0 blocker”结论：planner 已有 active plan 时，`previous_plan=None` 曾可错误生成 version 1。该 P0 现已修复并标记 done，缺失前序计划会以 `previous_plan_required` 拒绝并携带 latest plan id/version。P1 switch penalty、secondary activation 和 rolling continuation 合同均已关闭，当前 D3 全量回归为 `84 passed`。

2026-07-10 P1 switch-penalty 修复已完成：`reassignment_switch_penalty` 现在在 Hungarian/fallback solve 前加入已有 target 改配到不同 resource 的可行边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。后置 Assignment 加价路径已移除，solver matrix、edge breakdown、objective、plan cost 和 evidence 单次计费一致。当前新 plan binding 保持 `active/current`，旧 plan 继续由 latest `plan_id/version` gate 失效。

当前 D3 P0/P1 补齐状态已从“接口缺口”转为“真实 episode 校准”。2026-07-10 已跑完 5v5、10 seeds、50/200 m、三类降级场景共 60 个真实 AirSim episode，全部连接；但它们仍是等量 M/N，不能关闭非等量 N/M 与增量更新缺口。2026-07-11 新增三个真实 AirSim 5v5 短 episode：在线 D2 航迹全部 `truth_id=None`，D3 assignment coverage 均为 `1.0`，版本化计划与 D5/D7 binding 正常。这关闭的是“等量 5v5 单 seed 短时链路是否依赖 truth ID”的证据缺口，不代表真实多 seed、长时或非等量 N/M 已校准。历史 20 个请求二级接管的 case 全部保守转为分布式，1300 条 D4 决策仅 15 条瞬时 `takeover_ready`，均停在 `pending_secondary_plan`，`secondary_plan_active=0`。D3 已补齐持续 readiness、精确 supersede、严格 version/epoch、live lease、concrete owner 和 current binding 的模块合同；剩余 secondary P1 是 main/D4 runtime 接线与真实正负例验证，不再是 D3 DTO 缺口。

当前 D3 没有未关闭的 P0。`previous_plan` 连续性、solve 前 switch penalty、D5/D7 禁止本地改绑、secondary activation/current-binding 和 plan/evidence schema 作为回归合同保留。剩余 P1 是 D5 feedback 权重/迟滞阈值标定、非等量 N/M 和增量更新、完整动态威胁评估、hard time-window 多场景校准、secondary runtime 正负例，以及 OR-Tools Min Cost Flow 同输入对照。OR-Tools 仍是 P1 对照项，不替换 Hungarian。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞与 solve 前 switch penalty | P1 matrix integration done。支持 `delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 Hungarian/fallback 前进入可行改配边，matrix/breakdown/objective/evidence 单次计费一致，unassigned/release 语义不变。继续输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible`、`accepted_high_threat_release` 等决策状态和原因 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、旧边不可行或重复资源导致旧计划不可行时可接受新计划。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 `AssignmentPlan` 与前序连续性 | P0 done。`AssignmentPlan` 有 `plan_id/version/window_id/resource_count/target_count`；首次调用允许 `previous_plan=None`，active plan 后缺失前序计划以 `previous_plan_required` 拒绝并返回 latest id/version，旧计划和 expected-version 检查保持原语义。planner 实例只对应一个 episode。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 不写死 2v2/5v5 | 已实现。矩阵由输入列表长度构建，测试显式验证 3 targets / 2 resources 的 `assignment_matrix_shape=[3, 2]`、`resource_count=2`、`target_count=3`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 可解释代价分解 | 已实现。`CostModel.edge_cost()` 输出 `window/covariance/threat/resource_state/resource_energy/resource_availability/resource_current_load/resource_history_failure/fov/conflict/reassignment_switch_penalty/intercept_feasibility/infeasible/total`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py` |
| 轻量 hard time-window rejection baseline | 已实现。`TargetTrack` 支持全局或按资源的 `hard_time_window/time_window_open_at_s/time_window_close_at_s/time_window_state/time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` flags，planner 不分配该边并在 evidence 中导出 `reject_reason`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| P0-B 资源状态细化 | 已实现。`ResourceState` 补齐 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`，`CostModel` 消费这些字段并输出资源状态子项和不可行原因 flag；dry-run adapter 已映射 synthetic AirSim-style 字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| P0-B 可解释 threat score baseline | 已实现。`compose_threat_score_baseline()` 将关键区接近、TTC、速度、协方差、目标状态组合为可解释 `ThreatScoreBaseline`；adapter 在缺少显式 `threat_score` 时写入 baseline score 和 components/reasons metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| Current plan / cost evidence export | 已实现。planner metadata 记录 current plan id/version/owner/source、solver 实际使用的完整 cost matrix、target/resource ids、per-edge cost breakdown、rejected edges、hard reject reasons、stale rejection reason 和 secondary owner/source/version/supersede 字段；switch penalty 已在 solve 前进入 matrix/breakdown，`assignment_evidence_from_plan()` 导出同值 `AssignmentEvidenceExport` 供 D4/D6 replay。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D7 guidance binding | 已实现。`guidance_bindings_from_assignment_plan()` 导出 `AssignmentGuidanceBinding`，携带 `plan_id/version/resource_id/assigned_global_track_id/authorization_state/guidance_phase/source/target/link`，并暴露 D7 兼容别名；新 current plan 即使发生改配仍输出 `active/current`，旧 plan 由 plan id/version gate 失效，stale/revoked/hold/reassigned 状态和 current/secondary owner/version metadata 有测试。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 授权状态配置透传 | 已实现。`PlannerConfig.human_authorization_state` 会写入 `AssignmentPlan.human_authorization_state`，并记录 `configured_human_authorization_state` 与 `effective_human_authorization_state`，main 可用 `"recorded"` 进行仿真记录态 gating。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback 写回下一轮输入 | 已实现。`apply_terminal_feedback_to_planner_inputs()` 将 duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False`，将 fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`，将 friend/hold metadata 写入 `ResourceState.operator_hold=True`，并保持 `allow_local_rebind=False`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| Secondary takeover activation/current binding | 已实现 D3 侧严格规则。`prepare_secondary_takeover_plan()` 要求 concrete secondary owner、持续 `takeover_ready`、精确 `previous_plan_id`、严格递增 version、正且单调 leader epoch、激活时未过期 lease；成功计划写入 active schema 和完整审计字段。secondary D7 binding 必须显式匹配 current plan，旧中心、非 current、未激活或 lease 过期计划均不是 `active/current`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段和 N/M replay 字段：`assigned_count/hysteresis_reject_count/stale_reject_count/reassign_count`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现并补齐多 seed current-plan 字段。`assignment_records_from_plan()` 导出 D6-compatible `AssignmentRecord(timestamp, plan id/version, resource_id, global_track_id, cost_breakdown, authorization_state, active, truth_id)`，并携带 `window_id`、`decision_state`、`changed`、`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`、`assignment_matrix_shape`、plan owner/source/link/schema、`replan_reason/takeover_reason`、previous/superseded plan id/version、secondary owner/version/epoch/lease、plan costs、`cost_margin`、`stale_after_s`、stale rejection metadata 和迟滞 held/released 解释字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback calibration summary | 已实现。`summarize_terminal_feedback_calibration()` 输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数及 cost/hysteresis 建议；`summarize_assignment_mismatch_replay()` 输出 N/M replay summary。helper 只给建议，不自动替换默认权重或迟滞参数。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 已接入但需校准/部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback runtime 消费 | 已完成 D3 helper 与 main/runtime 接线。`evaluate_terminal_feedback()` 已把 `ambiguous/hold/friend_overlap_hold` 映射为 `hold`，`reacquire` 映射为 `replan`，`mismatch/multi_frame_inconsistent/cross_view_conflict` 和 `duplicate_terminal_lock_risk` 映射为 `secondary_arbitration`；`apply_terminal_feedback_to_planner_inputs()` 已能写回下一轮 D3 DTO，并由 main/runtime 在 episode bus 中调用和记录。 | D3 只消费 D5/main 已聚合的 metadata，不自行判断视觉身份、不统计跨资源 duplicate lock，也不改写 `global_track_id`。 | 剩余是多 seed 校准：验证写回后的禁配边、视场难度和 operator hold 是否在不同 N 规模、遮挡和 crossing 场景中稳定改善计划质量。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 validity/feedback 证据和严格 secondary activation/current-binding 合同，能审计 readiness、activation、owner、supersede、version/epoch 和 lease。 | 既有 10-seed/60-case 仍未形成 active secondary plan；D3 不选择二级节点、不续租、不执行 CBBA/拍卖或恢复仲裁。 | main/D4 接入必填 activation 参数并构造持续 readiness 正例、lease/epoch/current identity 负例及中心恢复专项。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord`、`AssignmentEvidenceExport`、validity summary、N/M replay summary 和 feedback calibration summary helper，字段包括 plan id/version、owner/source/schema、replan/takeover reason、previous/supersede、secondary owner/version、resource/target/assigned 规模、hysteresis/stale/reassign 计数、matrix shape、current cost matrix、per-edge cost breakdown、reject reason、stale reason、迟滞决策状态与 held/released 原因、cost gap、authorization state 和 active/truth labels。main runtime 已在 P1 D4/D5 calibration sweep 后自动生成 D6 标准报告 bundle，D3 通过 plan/record/evidence helper 消费这些 episode 级数据。 | D3 不写 D6 存储，也不拥有 episode log 总线；calibration helper 输出建议但不自动改默认参数。 | D3 侧无 record/evidence export P1 缺口；剩余是用真实 D6 聚合结果、P1 sweep bundle 和 episode records 人工复核 D3 权重阈值、hard-window 输入和多 seed 稳定性。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter、严格 secondary 合同和 AirSim integration plan；main runtime 已接入 D5 feedback writeback、center replan 与 secondary owner/version/source 记录。 | D3 不直接导入 AirSim；当前 main 调用仍需补 sustained readiness、activation、leader epoch 和 current binding 参数，既有 sweep 未形成 active secondary plan。 | main 完成接口适配后补 3v5、5v3、目标新增、资源失效、crossing/dense 和 secondary activation 专项。 |
| EVAL P0-B 资源状态细化（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`ResourceState` 现有字段外已补 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`；`CostModel` 消费 energy、availability、load、history failure 和 intercept feasibility，并导出不可行原因 flag。 | 还缺真实 episode 中各字段的阈值标定和跨模块日志分布，不缺 D3 DTO/schema。若字段缺失、cost metadata 丢失或不可行原因不可解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 energy/availability/current_load/history_failure_rate 的默认阈值和 D6 聚合展示，同时保持现有 cost metadata 单元测试回归。 |
| EVAL P0-B 增强迟滞和 stale rejection（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。已有 `delta`、`min_dwell`、`max_changes_per_window`、旧边不可行绕过、stale plan 拒绝、high-threat release condition 和 D6 held/released 原因导出；P1 已进一步把 `reassignment_switch_penalty` 前移到 solver matrix 并消除双重计费。 | 多 seed 标定尚未完成，尤其是 release condition 与 churn/漏分配之间的参数平衡。若 min dwell、switch penalty、release condition 或 stale reason 无法解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，D6 报告同时展示重分配下降、高威胁未分配不升高、matrix/objective 一致和 stale rejection reason 可聚合。 |
| EVAL P0-B 可解释 threat baseline（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`compose_threat_score_baseline()` 将接近关键区、TTC、速度、协方差、目标状态合成为可解释 threat score；`TargetTrack.threat_score`、`unassigned_high_threat_count` 和 cost breakdown 继续消费该字段。 | 完整动态威胁评估尚未实现，不应把 baseline 伪装成 outcome-aware 模型。若 TTC、关键区接近、速度、协方差或目标状态无法进入 baseline 解释，再列 P0 backlog。 | 用 D6 多 seed outcome 标定完整模型，并保留 Hungarian/baseline 对照；P0 回归只要求 baseline 组件和 reasons 可解释、可导出。 |
| EVAL P1 完整动态威胁评估 | 未作为完整模型实现。当前仅消费/记录 threat baseline 所需字段。 | 完整威胁模型需要场景定义、保护区、TTC、速度、目标类别、协方差、资源状态和 D6 mission outcome 支撑，不能用单一 `threat_score` 字段伪装完成。 | 先保持 P0-B baseline 可解释，再用 D6 多 seed outcome 标定完整模型，并保留 Hungarian baseline 对照。 |
| EVAL P1 增量分配 | 未实现局部增量策略。当前 `AssignmentPlanner.plan()` 是滚动全量重算，已可处理目标/资源数量变化。 | 新目标突增、资源失效或局部反馈时还没有只重算受影响子图的 plan update 路径和 latency 对照。 | 定义新目标、资源失效、D5 feedback 写回后的增量更新 API；验收重点是 plan update latency 下降且版本/stale 拒绝不退化。 |
| EVAL P1 时间窗口硬约束 | 轻量 baseline 已实现。`TargetTrack.window_cost` 仍是软排序项；新增 hard close/open schema、不可行窗口拒绝、`reject_reason`、cost breakdown flags 和测试。 | 目前是轻量 baseline，不是完整多窗口/到达时间网络；未做真实多 seed 标定，也未接 OR-Tools 复杂约束。 | 用 AirSim/point-mass 多 seed/N 规模回放校准 hard window 输入、到达时间和 reject reason 分布；多窗口/容量/配额后续可进入 optional min-cost-flow 对照。 |
| EVAL P1 OR-Tools Min Cost Flow 对照接口 | 部分实现为边界保留。`MinCostFlowAssignmentSolver` 类和测试存在，`solve()` 显式抛出 `NotImplementedError`，说明 OR-Tools 未安装且当前应使用 Hungarian。 | 三个 patch 均确认 OR-Tools 工程成熟，但 P0/P1/P2 确认文档将其收敛为 P1 对照、复杂约束升级；当前只有 API 边界和失败语义，没有 OR-Tools optional dependency、整数代价缩放、基础网络建图或求解结果解码。 | P1 只要求能在同输入下输出 Hungarian vs min-cost-flow 对照计划；容量、备份资源、多窗口和分组配额属于后续复杂约束，不替代当前 Hungarian 默认主线。 |

## 4. 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|---|
| 完整 runtime secondary takeover 仲裁策略 | D3 已实现 activation/current-binding 严格校验和审计导出；main runtime 已接入基础 secondary owner/version/source 记录，但尚未传齐 sustained readiness、activation、epoch、lease 和 current identity。 | D3 不是 D4 二级节点选择器，不维护 heartbeat/lease 续期，也不拥有中心恢复仲裁。 | D4/main policy 需完成调用适配并验证租约续期、中心恢复合并和 stale secondary runtime 拒绝。 | 外部 policy，非 D3 DTO 缺口。 |
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
| 非等量 N/M 与事件驱动校准矩阵 | 等量 5v5 的 10-seed/60-case 已完成；仍缺 3v5、5v3、目标新增、资源失效、D5 模糊、D2 不确定和 crossing/dense 场景。 |
| D5 feedback 权重阈值长期标定数据 | D3 已能生成 advisory calibration summary；仍需要真实 D6 records 反复校准 `fov_difficulty_by_resource`、禁配边、operator hold、hold/replan/secondary_arbitration 阈值，避免过度重规划或过度 hold。 |
| D5/main duplicate lock 和多帧不一致聚合分布 | D3 不自行判断多资源终端锁定冲突；需要上游持续提供聚合事件，供 D3 权重阈值校准。 |
| P0-B 多 seed 标定证据 | baseline schema/helper 已完成；仍需要覆盖非等量 M/N、资源不足、高威胁目标、D5 模糊和 crossing/dense 场景，用于校准增强迟滞参数、资源状态阈值和 threat score baseline 权重。 |
| P1 增量/hard-window 校准/OR-Tools 输入 schema | 需要定义局部更新事件、hard time-window 多窗口/到达时间校准、整数代价缩放和 optional OR-Tools 依赖边界，保持无 OR-Tools 环境测试仍通过。 |

## 7. 当前 D3 P0/P1 缺口与下一步优先级

1. **P0 done**: 已撤销旧“无运行级 P0 blocker”结论。active plan 后 `previous_plan=None` 导致 version 回退到 1 的缺口已修复；现在固定以 `previous_plan_required` 拒绝并携带 latest plan id/version，首次调用和新 planner 实例仍从 version 1 开始。Hungarian、fallback DP、迟滞、其他 stale/expected-version 检查、D7 binding、D6 export、current evidence export、P0-B 资源状态细化、P0-B 增强迟滞/stale rejection、P0-B threat baseline 和轻量 hard time-window baseline 继续保持回归。
2. **P1 switch-penalty matrix integration done**: penalty 已在 solve 前加入可行改配边，零 penalty/中等 penalty/较大 penalty 构造测试覆盖换配、单次计费和保持原资源；边界测试同时确认不可行边、无历史 assignment 的新目标和 unassigned cost 不受 penalty 污染，release 与 current binding 语义保持不变。
3. **P1 no-truth 5v5 smoke done / 多 seed 待校准**: 三个真实 AirSim 短 episode 在 D2 `truth_id=None` 下 assignment coverage=`1.0`，计划版本与 D5/D7 binding 正常；该结论限于单 seed、短时、等量 5v5，不能外推到长期稳定性。
4. **P1 D5 feedback 权重标定**: 用真实 D6 records 对 `fov_difficulty_by_resource`、禁配边、operator hold、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty` 做配对扫描；验收抖动下降且高威胁未分配不恶化。
5. **P1 非等量 N/M 与增量分配**: 补真实 3v5、5v3、目标新增和资源失效场景；局部更新相对全量重算应降低 update latency，同时版本/stale 拒绝不退化。
6. **P1 完整动态威胁评估**: 在 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，并保留 baseline 对照。
7. **P1 时间窗口硬约束校准**: 已有单窗口 closed-edge baseline 不重复实现；补到达时间、多窗口、not-yet-open/expired 分布和 reject reason 聚合。
8. **P1 D3 secondary activation 合同 done / runtime 待验证**: 模块内已验收 concrete owner、持续 readiness、严格 version/epoch、live lease、旧中心 stale、非 current/过期 binding 阻断和审计导出；剩余由 main/D4 完成调用适配、持续 readiness 正例与中心恢复多 seed 验证。
9. **P1 OR-Tools Min Cost Flow 对照接口**: 按既定优先级接入 optional、同输入的一对一对照，保持 Hungarian 默认；复杂容量/备份/配额不进入本 P1。
10. **P1 合同保持回归**: active-plan `previous_plan` 必填、switch penalty solve 前单次计费、D5/D7 禁止本地换绑、secondary current/lease/rolling gate 和 D6 schema 必须继续通过。当前 D3 回归基线为 `84 passed`。
11. **P2 大规模参数扫描**: 扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数、资源状态阈值、threat baseline 权重和 assignment quality 的长期对照表。

## 8. 跨模块接口影响

### 8.1 D4 主动/被动降级

被动降级由 D4 的 C2Health、通信和进程状态触发，D3 只提供最新中心 `AssignmentPlan` 作为接管基线。主动降级时，D3 的影响是提供证据而不是执行动作：`AssignmentValiditySummary`、`d4_request`、stale/version 状态、成本 margin、重复分配和高威胁未分配计数。若中心仍可用且 Hungarian 能明显改善，D4/main 应优先 `request_center_replan`；该请求完成后 main/runtime 已记录新的中心 plan owner、`plan_id/version`、`replan_reason`、superseded 旧计划和 stale 拒绝结果。若 D5 多帧不一致、D2/D1 不确定性高或计划持续 stale，再进入二级仲裁；secondary owner/version/source runtime 记录已接入，真实 secondary owner 选择、租约和中心恢复合并策略仍由 D4/main 负责，D3 侧只提供 DTO/helper 和多 seed 记录校准。

### 8.2 D5 terminal association

D5 只做末端视觉配准和一致性证据。D3 给 D5 的 assignment 是“资源当前应关注的 `global_track_id`”，不是允许 D5 改绑的授权。D5 反馈被 D3 helper 转为 `hold/replan/secondary_arbitration` 建议，并可通过 `apply_terminal_feedback_to_planner_inputs()` 写回下一轮 `operator_hold`、禁配边或视场难度；main/runtime 已负责调用和记录。D3 文档和 DTO 均明确 `allow_local_rebind=False`，后续重点是用真实多 seed 结果长期标定 D5 feedback 权重阈值。

### 8.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 只消费当前版本 binding。对 secondary plan，main 必须把当前 `plan_id/version` 传给 D3 binding helper；不匹配、缺失 current confirmation、takeover 未激活或 lease 过期时 binding 为 stale/hold。D7 仍必须同时检查 D4 action 和 D5 lock，且不得本地换绑 `global_track_id`。

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
