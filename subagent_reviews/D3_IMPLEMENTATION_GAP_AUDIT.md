# D3 实现差距审计

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-13
**审计依据**: 当前 `research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests，`research_modules/airsim_runtime/outputs/p1_m5n2_cooperative_10seed_20260713/`、`subagent_reviews/MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## 1. 总体结论

D3 当前已经完成中心化一对一与显式 M-to-N demand-slot 主线：SciPy Hungarian、DP fallback、schema v2、coalition all-or-none admission、滚动与保守增量规划、set/signature 迟滞、防 stale plan、版本化 `AssignmentPlan/CoalitionPlan`、可解释代价、D5 feedback writeback、secondary activation/continuation、D7 coalition binding、D6 export 和 synthetic AirSim dry-run adapter。历史第一次真实复验暴露了 soft reserve hold 顺带旋转 healthy primary；当前实现已从 previous plan 推导 member role，在健康 primary + soft reserve failure 时固定旧 primary slots。ComputerVision 10-seed 中 T001 双 primary 视觉共识与当前计划授权为 8/10，D3 P1 合同层已闭合。P2 已补齐同一非等量 N/M、hybrid role、资源容量输入的 SciPy/optional OR-Tools 隔离 runner；当前 OR-Tools 未安装时返回结构化 `unavailable_reason`。

2026-07-10 P1 switch-penalty 修复已完成：`reassignment_switch_penalty` 现在在 Hungarian/fallback solve 前加入已有 target 改配到不同 resource 的可行边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。后置 Assignment 加价路径已移除，solver matrix、edge breakdown、objective、plan cost 和 evidence 单次计费一致。当前新 plan binding 保持 `active/current`，旧 plan 继续由 latest `plan_id/version` gate 失效。

当前 D3 P0/P1 状态已从“接口缺口”转为“合同闭合、协同物理与参数校准待续”。2026-07-11 的 5-resource/2-target ComputerVision 10-seed 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。二级接管和完全分布式 commit 正例已通过，缺 ACK 时 coalition aborted 且 D7 许可为 0，证明 D3 current plan/binding 可被下游 fail-closed gate 正确消费。历史 `secondary_plan_active=0` 仅保留为 2026-07-10 实施前运行基线，不再代表当前合同状态。

2026-07-13 已完成 M5N2 hybrid `2 primary + 1 standby reserve` 的真实 SimpleFlight paired 验收：baseline 与三个候选各 10 seeds，共 40 个 episode；本阶段不要求 primary 同时到达。coalition completion 为 baseline `0/10`、最佳 `20 m / 3 s / 40 deg` `5/10`、其余候选 `2/10` 和 `1/10`，未达到 `8/10` 门限。版本/stale/role 合同保持，reserve 未授权执行、旧版本执行和 `global_track_id` 本地改写均未成为该轮安全问题。

当前 D3 没有未关闭的 P0 或 P1 **合同层**缺口。`previous_plan` 连续性、solve 前 switch penalty、D5/D7 禁止本地改绑、secondary activation/current-binding、增量接口、transient feedback dwell、role-aware primary 保持和 plan/evidence schema 均作为回归合同保留。**P1 证据与参数标定仍开放**：正式 40-case aggregate 缺少逐时刻 plan history，因此 membership/version churn 当前为 `unavailable`，不能推断为零；还需用逐时刻 D5 feedback 标定权重/迟滞，并完成真实 3v5、5v3 和动态事件标定。OR-Tools 等继续保持 P2 optional，不替换默认 Hungarian/demand-slot 在线路径。

本轮 40-case aggregate 已可由 D6 展开，不再缺少 profile/case 级结果；但没有逐 planning tick 的 plan history，所以 D3 churn 相关指标仍不可用。P0/P1 下一验收不是新增合同字段，而是保存逐时刻 plan id/version、coalition membership/epoch、D5 feedback、迟滞原因和 outcome，再据此完成 D5 feedback 权重/迟滞与动态 N/M 标定。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞与 solve 前 switch penalty | P1 matrix integration done。支持 `delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 Hungarian/fallback 前进入可行改配边，matrix/breakdown/objective/evidence 单次计费一致，unassigned/release 语义不变。继续输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible`、`accepted_high_threat_release` 等决策状态和原因 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 transient feedback dwell | P1 done。writeback 保留 source plan version、stable counts/required window 和 conflict；full/incremental 在普通迟滞前保护仍可行的 primary set。effective window 取 D3 配置与上游 required 的最大值，持续反馈到阈值或硬风险立即释放。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| Reserve soft feedback 的 primary role 保护 | P1 done。D3 从 previous assignment 推导 member role；同版本 primary 全部 consistent 且仅 reserve 普通 hold/reacquire 时，在 demand-slot matrix 固定仍可行的旧 primary 集合，只重解 reserve。无需 main 新增 reason/required/member_role。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、旧边不可行或重复资源导致旧计划不可行时可接受新计划。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 `AssignmentPlan` 与前序连续性 | P0 done。`AssignmentPlan` 有 `plan_id/version/window_id/resource_count/target_count`；首次调用允许 `previous_plan=None`，active plan 后缺失前序计划以 `previous_plan_required` 拒绝并返回 latest id/version，旧计划和 expected-version 检查保持原语义。planner 实例只对应一个 episode。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 不写死 2v2/5v5 | 已实现。矩阵由输入列表长度构建，测试显式验证 3 targets / 2 resources 的 `assignment_matrix_shape=[3, 2]`、`resource_count=2`、`target_count=3`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 可解释代价分解 | 已实现。`CostModel.edge_cost()` 输出 `window/covariance/threat/resource_state/resource_energy/resource_availability/resource_current_load/resource_history_failure/fov/conflict/reassignment_switch_penalty/intercept_feasibility/infeasible/total`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py` |
| 轻量 hard time-window rejection baseline | 已实现。`TargetTrack` 支持全局或按资源的 `hard_time_window/time_window_open_at_s/time_window_close_at_s/time_window_state/time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` flags，planner 不分配该边并在 evidence 中导出 `reject_reason`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| P0-B 资源状态细化 | 已实现。`ResourceState` 补齐 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`，`CostModel` 消费这些字段并输出资源状态子项和不可行原因 flag；dry-run adapter 已映射 synthetic AirSim-style 字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| P0-B 可解释 threat score baseline | 已实现。`compose_threat_score_baseline()` 将关键区接近、TTC、速度、协方差、目标状态组合为可解释 `ThreatScoreBaseline`；adapter 在缺少显式 `threat_score` 时写入 baseline score 和 components/reasons metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| Current plan / cost evidence export | 已实现。planner metadata 记录 current plan id/version/owner/source、solver 实际使用的完整 cost matrix、target/resource ids、per-edge cost breakdown、rejected edges、hard reject reasons、stale rejection reason 和 secondary owner/source/version/supersede 字段；switch penalty 已在 solve 前进入 matrix/breakdown，`assignment_evidence_from_plan()` 导出同值 `AssignmentEvidenceExport` 供 D4/D6 replay。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D7 guidance binding | 已实现。`guidance_bindings_from_assignment_plan()` 导出 `AssignmentGuidanceBinding`，携带 `plan_id/version/resource_id/assigned_global_track_id/authorization_state/guidance_phase/source/target/link`，并暴露 D7 兼容别名；逐 pair metadata 还包含 coalition id/version/epoch、role/wave/activation/validity、per-primary 授权资格、plan churn/rollback/stale reject。新 current plan 即使发生改配仍输出 `active/current`，旧 plan 由 plan id/version gate 失效，reserve 始终 standby/hold。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py` |
| 授权状态配置透传 | 已实现。`PlannerConfig.human_authorization_state` 会写入 `AssignmentPlan.human_authorization_state`，并记录 `configured_human_authorization_state` 与 `effective_human_authorization_state`，main 可用 `"recorded"` 进行仿真记录态 gating。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback 写回下一轮输入 | 已实现。`apply_terminal_feedback_to_planner_inputs()` 将 duplicate/prohibited/feasibility metadata 写入 `TargetTrack.feasibility_by_resource=False`，将 fov/friend metadata 写入 `TargetTrack.fov_difficulty_by_resource`，将 friend/hold metadata 写入 `ResourceState.operator_hold=True`，并保持 `allow_local_rebind=False`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| Secondary takeover activation/current binding | 已实现 D3 侧严格规则。`prepare_secondary_takeover_plan()` 要求 concrete secondary owner、持续 `takeover_ready`、精确 `previous_plan_id`、严格递增 version、正且单调 leader epoch、激活时未过期 lease；成功计划写入 active schema 和完整审计字段。secondary D7 binding 必须显式匹配 current plan，旧中心、非 current、未激活或 lease 过期计划均不是 `active/current`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段和 N/M replay 字段：`assigned_count/hysteresis_reject_count/stale_reject_count/reassign_count`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现并补齐多 seed current-plan 与逐 pair 字段。`assignment_records_from_plan()` 除基础 assignment/owner/cost/迟滞/stale 字段外，统一导出 coalition id/version/epoch/completeness、role/wave/activation/validity、per-primary 授权范围与资格、plan churn/rollback/stale reject。两个 primary 独立 active/current，reserve 记录为 standby 且 `active=false`，不会被统计为已激活执行 pair。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py`; `research_modules/d3_assignment_planner/tests/test_coalition_membership_hysteresis.py` |
| D5 feedback calibration summary | 已实现。`summarize_terminal_feedback_calibration()` 输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数及 cost/hysteresis 建议；`summarize_assignment_mismatch_replay()` 输出 N/M replay summary。helper 只给建议，不自动替换默认权重或迟滞参数。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 已接入但需校准/部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback runtime 消费 | 已完成 D3 helper 与 main/runtime 接线。`evaluate_terminal_feedback()` 已把 `ambiguous/hold/friend_overlap_hold` 映射为 `hold`，`reacquire` 映射为 `replan`，`mismatch/multi_frame_inconsistent/cross_view_conflict` 和 `duplicate_terminal_lock_risk` 映射为 `secondary_arbitration`；`apply_terminal_feedback_to_planner_inputs()` 已能写回下一轮 D3 DTO，并由 main/runtime 在 episode bus 中调用和记录。 | D3 只消费 D5/main 已聚合的 metadata，不自行判断视觉身份、不统计跨资源 duplicate lock，也不改写 `global_track_id`。 | 剩余是多 seed 校准：验证写回后的禁配边、视场难度和 operator hold 是否在不同 N 规模、遮挡和 crossing 场景中稳定改善计划质量。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 validity/feedback 证据和严格 secondary activation/current-binding 合同；二级/分布式 commit 正例与缺 ACK fail-closed 已通过下游验证。 | D3 不选择二级节点、不续租、不执行 CBBA/拍卖或恢复仲裁。 | 后续中心恢复和长时 lease 校准属于 main/D4 policy，不是 D3 P1 合同缺口。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord`、`AssignmentEvidenceExport`、validity summary、N/M replay summary 和 feedback calibration summary helper，字段包括 plan id/version、owner/source/schema、replan/takeover reason、previous/supersede、secondary owner/version、resource/target/assigned 规模、hysteresis/stale/reassign 计数、matrix shape、current cost matrix、per-edge cost breakdown、reject reason、stale reason、迟滞决策状态与 held/released 原因、cost gap、authorization state 和 active/truth labels。main runtime 已在 P1 D4/D5 calibration sweep 后自动生成 D6 标准报告 bundle，D3 通过 plan/record/evidence helper 消费这些 episode 级数据。 | D3 不写 D6 存储，也不拥有 episode log 总线；calibration helper 输出建议但不自动改默认参数。 | D3 侧无 record/evidence export P1 缺口；剩余是用真实 D6 聚合结果、P1 sweep bundle 和 episode records 人工复核 D3 权重阈值、hard-window 输入和多 seed 稳定性。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter、严格 secondary 合同和 AirSim integration plan；main runtime 已完成 40 个真实 SimpleFlight M5N2 episode。默认 `2 primary + 1 standby reserve`，且不要求同时到达。 | 最佳 profile 仅 `5/10`，未达 `8/10`；正式 aggregate 缺逐时刻 plan history，membership/version churn 为 unavailable。 | main 写盘逐 tick plan/coalition/feedback/迟滞历史；D3/D6据此校准 D5 feedback、迟滞和动态 N/M，且不得把 unavailable 补成 0。 |
| EVAL P0-B 资源状态细化（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`ResourceState` 现有字段外已补 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`；`CostModel` 消费 energy、availability、load、history failure 和 intercept feasibility，并导出不可行原因 flag。 | 还缺真实 episode 中各字段的阈值标定和跨模块日志分布，不缺 D3 DTO/schema。若字段缺失、cost metadata 丢失或不可行原因不可解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 energy/availability/current_load/history_failure_rate 的默认阈值和 D6 聚合展示，同时保持现有 cost metadata 单元测试回归。 |
| EVAL P0-B 增强迟滞和 stale rejection（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。已有 `delta`、`min_dwell`、`max_changes_per_window`、旧边不可行绕过、stale plan 拒绝、high-threat release condition 和 D6 held/released 原因导出；P1 已进一步把 `reassignment_switch_penalty` 前移到 solver matrix 并消除双重计费。 | 多 seed 标定尚未完成，尤其是 release condition 与 churn/漏分配之间的参数平衡。若 min dwell、switch penalty、release condition 或 stale reason 无法解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，D6 报告同时展示重分配下降、高威胁未分配不升高、matrix/objective 一致和 stale rejection reason 可聚合。 |
| EVAL P0-B 可解释 threat baseline（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`compose_threat_score_baseline()` 将接近关键区、TTC、速度、协方差、目标状态合成为可解释 threat score；`TargetTrack.threat_score`、`unassigned_high_threat_count` 和 cost breakdown 继续消费该字段。 | 完整动态威胁评估尚未实现，不应把 baseline 伪装成 outcome-aware 模型。若 TTC、关键区接近、速度、协方差或目标状态无法进入 baseline 解释，再列 P0 backlog。 | 用 D6 多 seed outcome 标定完整模型，并保留 Hungarian/baseline 对照；P0 回归只要求 baseline 组件和 reasons 可解释、可导出。 |
| EVAL P1 完整动态威胁评估 | 未作为完整模型实现。当前仅消费/记录 threat baseline 所需字段。 | 完整威胁模型需要场景定义、保护区、TTC、速度、目标类别、协方差、资源状态和 D6 mission outcome 支撑，不能用单一 `threat_score` 字段伪装完成。 | 先保持 P0-B baseline 可解释，再用 D6 多 seed outcome 标定完整模型，并保留 Hungarian baseline 对照。 |
| EVAL P1 增量分配 | 接口和可复用校准矩阵已实现。`plan_incremental()` 校验输入快照与 declared changed IDs，只求解受影响的独立可行连通分量，随后在完整计划上应用迟滞；其余情况带原因回退全量。paired runner 覆盖 8 类转换并汇总 latency、churn、unassigned high-threat、coalition shortfall 和 reject/fallback。 | deterministic 3v5/5v3、目标新增、资源失效、需求变化、D5 reserve feedback、hard-window、all-or-none、switch penalty 和 full/incremental equivalence 已覆盖；真实 AirSim 多 seed 尚未标定。 | main/D6 用相同 schema/profile/version 的真实动态事件统计 incremental applied/fallback reason、延迟、cost equivalence、churn、高威胁未分配和 coalition shortfall；版本不一致继续 hard reject，不静默回退。 |
| EVAL P1 时间窗口硬约束 | 轻量 baseline 已实现。`TargetTrack.window_cost` 仍是软排序项；新增 hard close/open schema、不可行窗口拒绝、`reject_reason`、cost breakdown flags 和测试。 | 目前是轻量 baseline，不是完整多窗口/到达时间网络；未做真实多 seed 标定，也未接 OR-Tools 复杂约束。 | 用 AirSim/point-mass 多 seed/N 规模回放校准 hard window 输入、到达时间和 reject reason 分布；多窗口/容量/配额后续可进入 optional min-cost-flow 对照。 |
| P2 optional OR-Tools Min Cost Flow 对照 | 容量 benchmark contract done。共享 problem 同时进入 SciPy 容量列展开与 flow 原生容量 arc；覆盖非等量 N/M、hybrid primary+reserve、容量限制、objective/assignment 解码和结构化 unavailable。SciPy 当前 objective `5.6`。 | 当前环境未安装 OR-Tools，installed-only 求解 test skip，故尚无 flow objective 实证；slot-level flow 不表达 coalition 原子 admission。 | 在隔离环境运行 installed solver 并保存 objective delta/assignment；CP-SAT/MILP、备份配额、多窗口和分组配额继续作为 P2 optional，默认在线 planner 不变。 |

## 4. 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|---|
| 完整 runtime secondary takeover 仲裁策略 | D3 已实现 activation/current-binding 严格校验和审计导出，且下游 commit 正例与缺 ACK fail-closed 已通过。 | D3 不是 D4 二级节点选择器，不维护 heartbeat/lease 续期，也不拥有中心恢复仲裁。 | D4/main policy 继续校准租约续期、中心恢复合并和 stale secondary runtime 拒绝。 | 外部 policy，非 D3 DTO/P1 缺口。 |
| CP-SAT / MILP | 未实现，仅作为更复杂的隔离研究方向。 | 高频滚动主线不需要 MILP；求解时间、建模复杂度和约束定义都未定。 | 需要明确组合约束、求解时间预算、失败降级策略和对比场景。 | P2 optional benchmark。 |
| D3 内部 CBBA/拍卖 | 未实现，且不建议在 D3 实现。 | D3 是中心化分配模块；中心失效或通信受限后的 CBBA/拍卖属于 D4 分布式 fallback 边界。 | D4 需要以 D3 最新中心计划作为基线实现/对比 CBBA、拍卖或合同网。 | 不列入 D3 优先级。 |
| 直接 AirSim/Blocks import 和控制 | 未实现，且不应放入 D3。 | D3 边界是抽象规划；AirSim launch/reset/episode/log collection 属于 main/runtime。 | main/runtime adapter 提供抽象输入和日志输出。 | 不列入 D3 内部实现。 |

## 5. 未实现原因汇总

1. **模块边界**: D3 只发布中心化候选计划、有效性证据和跨模块 DTO，不执行 D4 降级、D5 视觉改绑、D6 存储或 AirSim runtime 控制。
2. **当前算法需求**: 默认无显式 demand 时保持 `k_j=1` Hungarian；显式 M-to-N 使用 demand-slot all-or-none 主线。更复杂的最小费用流、CP-SAT/MILP 只在隔离 benchmark 中评估。
3. **依赖策略**: OR-Tools 不进入默认依赖；容量 benchmark 在缺失时输出 `status=unavailable` 和 `unavailable_reason`，installed solver 实证仍待补，也不进入默认 planner。
4. **运行时总线持续校准**: D3 helper 已输出 metadata、summary、record、evidence、binding、N/M replay summary 和 D5 feedback calibration summary；main 已把 D5 feedback writeback、中心重规划 owner/version/source、secondary owner/version/source、P1 D4/D5 calibration sweep 和 D6 标准报告 bundle 接入 AirSim episode state machine。D3 record/evidence 现已补齐 owner/version/source、replan/takeover reason、previous/supersede、secondary owner/version、迟滞决策、N/M replay 计数、current cost matrix、per-edge cost breakdown、hard reject reason、stale reason 和 cost gap 字段，后续重点是多 seed 数据回灌和人工复核。
5. **上游事件缺失**: duplicate terminal lock、D5 连续状态迁移、D2/D1 不确定性摘要和 D4 仲裁结果需要由其他模块或 main 聚合后再反馈给 D3。

## 6. 缺少条件

| 缺少条件 | 影响 |
|---|---|
| 真实非等量 N/M 与事件驱动多 seed | 2026-07-13 已完成 M5N2 baseline/三候选共 40 个真实 SimpleFlight episode；仍缺逐时刻计划历史，以及真实 3v5、5v3、目标新增、资源失效、D5 模糊、D2 不确定和 crossing/dense 动态数据。 |
| D5 feedback 权重阈值长期标定数据 | D3 已能生成 advisory calibration summary；仍需要真实 D6 records 反复校准 `fov_difficulty_by_resource`、禁配边、operator hold、hold/replan/secondary_arbitration 阈值，避免过度重规划或过度 hold。 |
| D5/main duplicate lock 和多帧不一致聚合分布 | D3 不自行判断多资源终端锁定冲突；需要上游持续提供聚合事件，供 D3 权重阈值校准。 |
| P0-B 多 seed 标定证据 | baseline schema/helper 已完成；仍需要覆盖非等量 M/N、资源不足、高威胁目标、D5 模糊和 crossing/dense 场景，用于校准增强迟滞参数、资源状态阈值和 threat score baseline 权重。 |
| P1 增量/hard-window 长期校准 | 增量 API/schema 已完成；仍需真实动态事件和 hard time-window 多窗口/到达时间多 seed 校准。 |
| P2 optional 求解器证据 | 同输入容量 runner 与 SciPy 结果已完成；仍缺 installed Min-Cost Flow objective/assignment 对照，CP-SAT/MILP coalition 参考与复杂 flow 尚未实现。 |

## 7. 当前 D3 P0/P1 缺口与下一步优先级

1. **P0 done / 当前无开放 blocker**: 历史上曾发现 active plan 后 `previous_plan=None` 导致 version 回退到 1 的 P0 blocker；该缺口现已修复，因此当前恢复并确认无开放 P0 blocker。现在固定以 `previous_plan_required` 拒绝并携带 latest plan id/version，首次调用和新 planner 实例仍从 version 1 开始。Hungarian、fallback DP、迟滞、其他 stale/expected-version 检查、D7 binding、D6 export、current evidence export、P0-B 资源状态细化、P0-B 增强迟滞/stale rejection、P0-B threat baseline 和轻量 hard time-window baseline 继续保持回归。
2. **P1 switch-penalty matrix integration done**: penalty 已在 solve 前加入可行改配边，零 penalty/中等 penalty/较大 penalty 构造测试覆盖换配、单次计费和保持原资源；边界测试同时确认不可行边、无历史 assignment 的新目标和 unassigned cost 不受 penalty 污染，release 与 current binding 语义保持不变。
3. **P1 合同层 done / 协同物理闭环 open**: 2026-07-13 的 40 个真实 SimpleFlight M5N2 episode 中，baseline 为 `0/10`，最佳 `20 m / 3 s / 40 deg` 为 `5/10`，其余为 `2/10`、`1/10`，未达 `8/10`。`2 primary + 1 standby reserve`、无同时到达要求、版本/stale/role 和 reserve 安全合同保持；下一验收是逐时刻 plan history 与参数闭环。
4. **P1 D5 feedback 权重标定**: 用真实 D6 records 对 `fov_difficulty_by_resource`、禁配边、operator hold、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty` 做配对扫描；验收抖动下降且高威胁未分配不恶化。
5. **P1 非等量 N/M 与增量校准支撑 done / 真实校准待办**: versioned 8-scenario matrix 覆盖 3v5、5v3、目标新增、资源失效、高威胁需求变化、D5 reserve feedback 和 hard-window；paired runner 的 8/8 转换 assignment/cost 等价，并报告 latency、churn、unassigned high-threat、coalition shortfall、hard reject、fallback 和 primary 保持。下一步补真实多 seed，不预设局部路径必然更快。
6. **P1 完整动态威胁评估**: 在 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，并保留 baseline 对照。
7. **P1 时间窗口硬约束校准**: 已有单窗口 closed-edge baseline 不重复实现；补到达时间、多窗口、not-yet-open/expired 分布和 reject reason 聚合。
8. **P1 D3 secondary activation 合同 done**: 模块内 concrete owner、持续 readiness、严格 version/epoch、live lease、旧中心 stale、非 current/过期 binding 阻断和审计导出已验收；下游 commit 正例和缺 ACK fail-closed 已验证，中心恢复长期校准仍属 main/D4。
9. **P2 capacity benchmark contract done / installed evidence pending**: 同一 4-resource/3-target、5-slot hybrid 和容量输入已接 SciPy/optional flow；SciPy objective `5.6`，缺 OR-Tools 时结构化报告原因。当前环境仍未运行 installed flow；Hungarian/demand-slot 默认在线路径不变。
10. **P1 合同保持回归**: published active-plan `previous_plan` 必填；k=1/k>1 纯 evaluation refresh 均保持 `plan_id/version`，真实可执行语义变化才推进版本；forced ack/applied、未发布 candidate 不推进 latest、switch penalty solve 前单次计费、D5/D7 禁止本地换绑、transient dwell、reserve standby、secondary current/lease/rolling gate、schema v2/M-to-N、增量 snapshot/fallback 和 D6 schema 必须继续通过。当前回归基线见本文件末尾。
11. **P2 optional benchmark remaining**: 补 installed Min-Cost Flow objective/assignment 结果，并实现 CP-SAT/MILP coalition 参考、复杂 flow 和 10x10/20x20 参数扫描；只使用离线同输入数据形成最优差距、延迟和参数长期对照表，不进入默认 planner。

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
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`: optional OR-Tools Min Cost Flow benchmark 与 unavailable gate。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/p2_benchmark.py`: 共享非等量 N/M、hybrid role、容量约束输入和结构化双 solver outcome。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`: synthetic AirSim dry-run adapter。
- `research_modules/d3_assignment_planner/tests/test_planner.py`: 非 5v5 规模、迟滞、stale plan、cross-node fields。
- `research_modules/d3_assignment_planner/tests/test_solver.py`: Hungarian/fallback 行为。
- `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`: D5 feedback 映射、写回下一轮输入和不允许 local rebind。
- `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`: D7 binding stale/revoked/hold/reassigned/secondary takeover schema/owner/source/version。
- `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`: validity summary 和 D6 assignment record export。
- `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py`: schema v2、3v1/2v1/5v2、能力、角色/波次、版本/迟滞、multiplicity、binding。
- `research_modules/d3_assignment_planner/tests/test_min_cost_flow.py`: OR-Tools optional installed/skip/unavailable 合同。
- `research_modules/d3_assignment_planner/tests/test_p2_capacity_benchmark.py`: 同输入容量、objective、role、unavailable reason 和在线 planner 隔离合同。

## 10. M 对 N 联盟分配 P0/P1 补充（2026-07-11）

证据综述：`subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md`。本节只新增 P0/P1 状态，不改写既有 P2/P3 项。

### 10.1 现状判定

- `AssignmentPlan schema v2`、`TargetDemand`、`CoalitionPlan/member/summary` 已实现。无显式 demand 时仍为 `k=1 independent primary=1`；显式 `TargetDemand()` 启用默认 `k=3 hybrid primary=2`。`primary_resource_count` 可接收 main `--cooperative-primary-count`，不再硬编码 `min(2,k)`。
- `hungarian_demand_slots` 已实现 role/wave/capability slot 展开、威胁优先和全有或全无 admission。不完整 coalition 记录 tentative members/shortfall，但不发布 executable assignment。
- assignment signature/set 驱动迟滞；`k>1` 成员/角色有独立 dwell 与 coalition epoch。兼容成本/诊断刷新保留 plan ID/version 且不推进 coalition epoch；成员/角色变化才推进 coalition epoch。只有真实新执行版本发布后旧 binding 才 stale。
- D7 binding 已携带 coalition/role/wave/mode/window/min separation；只有 committed/current coalition 可 active。
- duplicate 统计允许同 coalition 且 `<=k_j` 的合法 multiplicity，只计资源跨目标冲突、超额、stale/revoked/unauthorized。
- OR-Tools Min-Cost Flow 已接 optional 容量 benchmark；共享 input 的 SciPy 路径已运行，当前 OR-Tools 缺失状态可机读，且未加入默认依赖。它不是 coalition CP-SAT 参考模型。

### 10.2 P0/P1 状态表

| 缺口 | 当前状态 | 优先级 | 缺少条件/验收口径 |
|---|---|---|---|
| 既有一对一安全合同 | 已实现并保持回归 | P0 done | `k_j=1` 时 Hungarian、版本、stale、迟滞、禁止本地 rebind 不退化 |
| `target_demand=k_j` 与 demand satisfaction | 已实现 | P1 done | required/assigned/shortfall/complete 已进入 plan；部分联盟不发布 executable assignment |
| Coalition 原子 admission、能力和成员角色 | 已实现 baseline | P1 done | id/version/state、primary/reserve/retry、能力槽与 all-or-none admission 已覆盖 |
| 同时、分批、混合时序策略 | 已实现合同/baseline | P1 done | hybrid primary 数为显式 `primary_resource_count`，进入 role/wave/signature/version/binding；真实 ETA 同步与 reserve feedback 激活仍由后续跨模块验证 |
| Coalition-aware 重分配与迟滞 | 已实现成员级 gain+dwell | P1 done | 当前成员至少保持 2 s；仅硬不可行或成本改善超过 20%且 dwell 满足时替换；输出前后成员、原因和保持依据 |
| 合法多资源与 duplicate 区分 | 已实现 | P1 done | 合法 `<=k_j`、超额、资源冲突和 stale/unauthorized 均有测试 |
| OR-Tools flow baseline | 同输入容量 benchmark 合同完成，installed solver 未在本轮运行 | P2 contract done / evidence pending | 默认 requirements/path 不变；隔离环境补 objective/assignment 结果 |
| CP-SAT/MILP 小规模参考 | 未实现 | P2 optional | 表达 `sum_i x_ij=k_j z_j`、能力、同步和波次，并设置求解超时/不可行报告；不得替换默认主线 |

### 10.3 开源证据结论

OR-Tools、NetworkX、Pyomo 和 PuLP 是成熟优化工具，但都不会自动提供 MSM coalition 业务合同。`dynamic_task_allocation`、HeteroMRTA、Hierarchical-LTL-STAP、CapAM-MRTA 等仓库可作算法/场景对照；其中多个明确是 SR-ST/ST-MR 或缺少清晰许可证，不能声称已经存在可直接集成的成熟 `k_j=3` C-UAS 方案。2019 ICRA OTMaM 有直接论文证据，但本轮未找到作者官方、许可证明确的实现。

## 11. P1 协同候选预筛缺口更新（2026-07-12）

| 项目 | 当前状态 | 结论 |
|---|---|---|
| 20/30/40 m、3/5/8 s、20/40/60 deg 候选 DTO | 已实现 | 27 个稳定 candidate ID；不写死 M/N，不修改 Hungarian 主线 |
| 动态 demand 映射 | 已实现 | 保留 required/primary count、coordination mode、能力、wave interval 和 minimum separation |
| main/D6 元数据导出 | 已实现 | 输出 candidate、窗口、扇区、成员 role/wave/activation、plan/coalition version；reserve 保持 standby |
| stale/version 拒绝 | 已实现并单测 | 非 current plan、assignment version 冲突、coalition version/state 冲突均 fail closed |
| 候选结果排序 | 已实现 | 仅消费完整实测 observation；按安全、coalition completion、pair success、arrival spread、candidate ID 排序并返回前三 |
| M5N2 真实物理预筛数据 | 已执行，P1 evidence partial | baseline 与前三候选各 10 seeds，共 40 个真实 SimpleFlight episode；结果为 `0/10`、`5/10`、`2/10`、`1/10`，最佳未达 `8/10` |
| per-primary 真实物理验收 | 已具备 case/pair 结果，P1 performance open | 两个 active primary 独立验收，不要求同时到达；reserve 保持 standby 且无越权执行 |
| membership/version churn | P1 open / unavailable | D6 可展开 40 case，但正式 aggregate 缺逐时刻 plan history；不得将缺测推断或补零 |

本轮关闭的是 D3-owned 的候选设计、排序合同和 current-plan 元数据出口，不是 AirSim 物理闭环。P0 合同无变化：k=1 回归、版本连续、stale rejection、迟滞、reserve standby 和禁止本地改写 `global_track_id` 必须继续通过。

## 12. 独立 Primary 与成员版本语义更新（2026-07-12）

| 项目 | 状态 | 验收结果 |
|---|---|---|
| per-primary 终端授权 | P1 done | demand/coalition/assignment/plan/binding 均携带版本化字段；不要求同时到达 |
| reserve 越权阻断 | P0/P1 done | reserve binding 固定为 hold，原因 `reserve_standby_not_activated` |
| coalition 成员级迟滞 | P1 done | 独立 2 s membership clock；硬不可行立即释放，其他替换要求 `>20%` gain 与 dwell 同时通过 |
| evaluation 与 executable identity 拆分 | P1 done | 纯成本重评保留 plan_id/version 和 coalition epoch；真实 assignment/owner/activation/coalition 变化才推进；secondary takeover 显式新建 lineage |
| 审计字段 | P1 done | 输出 `membership_change_reason`、previous/current members、成本、dwell/gain 和 hold basis |
| 默认 solver | 未改变 | 继续使用 Hungarian/demand-slot；未引入新依赖 |

本轮 D3 回归基线为 `139 passed, 1 skipped`。当前 D3-owned P0/P1 合同缺口已关闭；2026-07-13 已完成 40 个 M5N2 实验，但最佳 coalition completion 仅 `5/10`。逐时刻 plan 写盘、membership/version churn、D5 feedback 权重/迟滞和动态 N/M 标定仍为 P1；OR-Tools/CP-SAT/MILP 保持 P2 optional。
