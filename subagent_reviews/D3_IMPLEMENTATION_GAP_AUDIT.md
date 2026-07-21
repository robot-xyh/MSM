# D3 实现差距审计

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-15
**审计依据**: 当前 `research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests，既有 2026-07-13 M5N2 40-case 报告，以及 `research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2_*/episode_006_full_flow/main_episode_bus/d3_plan_history.json` 的最新 20-case/3725-record 只读复核、main/D6/D7 物理结果汇总、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## 1. 总体结论

D3 当前已经完成中心化一对一与显式 M-to-N demand-slot 主线：SciPy Hungarian、DP fallback、schema v2、coalition all-or-none admission、滚动与保守增量规划、set/signature 迟滞、防 stale plan、版本化 `AssignmentPlan/CoalitionPlan`、可解释代价、D5 feedback writeback、secondary activation/continuation、D7 coalition binding、D6 export 和 synthetic AirSim dry-run adapter。历史第一次真实复验暴露了 soft reserve hold 顺带旋转 healthy primary；当前实现已从 previous plan 推导 member role，在健康 primary + soft reserve failure 时固定旧 primary slots。ComputerVision 10-seed 中 T001 双 primary 视觉共识与当前计划授权为 8/10，D3 P1 合同层已闭合。P2 已补齐同一非等量 N/M、hybrid role、资源容量输入的 SciPy/optional OR-Tools 隔离 runner；当前 OR-Tools 未安装时返回结构化 `unavailable_reason`。

2026-07-10 P1 switch-penalty 修复已完成：`reassignment_switch_penalty` 现在在 Hungarian/fallback solve 前加入已有 target 改配到不同 resource 的可行边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。后置 Assignment 加价路径已移除，solver matrix、edge breakdown、objective、plan cost 和 evidence 单次计费一致。当前新 plan binding 保持 `active/current`，旧 plan 继续由 latest `plan_id/version` gate 失效。

当前 D3 P0/P1 状态已从“接口缺口”转为“合同闭合、协同物理与参数校准待续”。2026-07-11 的 5-resource/2-target ComputerVision 10-seed 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。二级接管和完全分布式 commit 正例已通过，缺 ACK 时 coalition aborted 且 D7 许可为 0，证明 D3 current plan/binding 可被下游 fail-closed gate 正确消费。历史 `secondary_plan_active=0` 仅保留为 2026-07-10 实施前运行基线，不再代表当前合同状态。

2026-07-13 已完成 M5N2 hybrid `2 primary + 1 standby reserve` 的真实 SimpleFlight paired 验收：baseline 与三个候选各 10 seeds，共 40 个 episode；本阶段不要求 primary 同时到达。coalition completion 为 baseline `0/10`、最佳 `20 m / 3 s / 40 deg` `5/10`、其余候选 `2/10` 和 `1/10`，未达到 `8/10` 门限。版本/stale/role 合同保持，reserve 未授权执行、旧版本执行和 `global_track_id` 本地改写均未成为该轮安全问题。

当前 D3 没有未关闭的 P0 或 P1 **合同层**缺口。`previous_plan` 连续性、solve 前 switch penalty、D5/D7 禁止本地改绑、secondary activation/current-binding、增量接口、transient feedback dwell、role-aware primary 保持、plan/evidence schema 和 canonical planning-tick history schema/export 均作为回归合同保留。最新 M5N2 20-case 已由 main 写盘 `3725/3725` 条 canonical records，D3 对计划版本、owner、成员 roster 和迟滞审计的可用性不再是 `unavailable`；20 个 case 的实际 version/member/owner transition 均为 0。**P1 证据与参数标定仍开放**：第二 primary `0/20`、coalition `0/20`，并且还需完成真实 3v5、5v3 和动态事件标定。

2026-07-14 已关闭 P1 计划抖动的一个合同根因：普通 D5 `ambiguous/hold/reacquire` 以及几何、FOV、检测不稳定现在只形成当前 resource-target 边的 soft cost 和 D7 hold，不再把资源升级为 `operator_hold=True`。`friend_overlap_hold` 保持 resource-hard，verified friend 保持 target-hard；安全身份冲突、duplicate assignment/lock 和显式 feasibility reject 保持 hard reject，真实 unavailable 资源仍由成本模型整资源拒绝。分类 class/scope/reason/hard flag 写入审计 metadata，旧 `operator_hold_suggested/resource_update` pair metadata 继续可读并被审计降级。transient 帧窗口完成后仍进入 coalition/global `min_dwell` 迟滞，不再直接发布改配。

历史 40-case 仍保留为旧候选预筛证据；最新 20-case 已完成 main 逐 tick history 写盘。D3 现提供并实际写盘 `d3_plan_history_record_v1`、`PlanningTickHistoryRecord` 和 `plan_history_record_from_plan(...)`；`3725` 条记录完整输出 owner、迟滞、成本、成员与 stale/rollback 审计且排除 truth。实际 plan/member/owner churn 均为 0；`3555` 条 membership audit 是候选换员评估，其中 `3524` 条成员保持、`31` 条成员层通过后被全局迟滞保持，不能计为实际 churn。普通 pair hold 扩大为资源不可行仍只是旧 40-case 根因线索，不是已证明的物理失败因果。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞与 solve 前 switch penalty | P1 matrix integration done。支持 `delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 Hungarian/fallback 前进入可行改配边，matrix/breakdown/objective/evidence 单次计费一致，unassigned/release 语义不变。继续输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible`、`accepted_high_threat_release` 等决策状态和原因 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 transient feedback dwell | P1 done。writeback 保留 source plan version、stable counts/required window 和 conflict；full/incremental 在普通迟滞前保护仍可行的 primary set。effective window 取 D3 配置与上游 required 的最大值；窗口完成仅结束前置保护，soft candidate 仍进入 coalition/global `min_dwell` 迟滞，硬风险可立即释放。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| Reserve soft feedback 的 primary role 保护 | P1 done。D3 从 previous assignment 推导 member role；同版本 primary 全部 consistent 且仅 reserve 普通 hold/reacquire 时，在 demand-slot matrix 固定仍可行的旧 primary 集合，只重解 reserve candidate；实际替换仍需成员/全局迟滞放行。无需 main 新增 reason/required/member_role。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
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
| D5 feedback 分级写回 | P1 root-cause fix done（2026-07-14）。普通 ambiguous/hold/reacquire、几何/FOV/检测不稳定为 edge-soft，只写 FOV cost + D7 hold；friend overlap 为 resource-hard，verified friend 为 target-hard；身份冲突、duplicate 和显式 feasibility reject 为 edge-hard。兼容旧 metadata，并输出 class/scope/reason/hard flag；`allow_local_rebind=False` 不变。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/tests/test_p1_nm_feedback_governance.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| Secondary takeover activation/current binding | 已实现 D3 侧严格规则。`prepare_secondary_takeover_plan()` 要求 concrete secondary owner、持续 `takeover_ready`、精确 `previous_plan_id`、严格递增 version、正且单调 leader epoch、激活时未过期 lease；成功计划写入 active schema 和完整审计字段。secondary D7 binding 必须显式匹配 current plan，旧中心、非 current、未激活或 lease 过期计划均不是 `active/current`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段和 N/M replay 字段：`assigned_count/hysteresis_reject_count/stale_reject_count/reassign_count`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现并补齐多 seed current-plan 与逐 pair 字段。`assignment_records_from_plan()` 除基础 assignment/owner/cost/迟滞/stale 字段外，统一导出 coalition id/version/epoch/completeness、role/wave/activation/validity、per-primary 授权范围与资格、plan churn/rollback/stale reject。两个 primary 独立 active/current，reserve 记录为 standby 且 `active=false`，不会被统计为已激活执行 pair。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py`; `research_modules/d3_assignment_planner/tests/test_coalition_membership_hysteresis.py` |
| Canonical planning-tick history export | P1 D3 schema/export done（2026-07-14）。`plan_history_record_from_plan()` 生成 `d3_plan_history_record_v1`：计划级身份/规模/owner/epoch/lease/lineage/cost，ordered primary/reserve assignment 和可恢复 coalition members，迟滞/成员变化、soft/hard feedback count/classification、stale/rollback/replan reason；`to_dict()` 为 JSON-native，排除 truth 字段。旧 assignment export 兼容不变。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_plan_history_record.py` |
| D5 feedback calibration summary | 已实现。`summarize_terminal_feedback_calibration()` 输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数及 cost/hysteresis 建议；`summarize_assignment_mismatch_replay()` 输出 N/M replay summary。helper 只给建议，不自动替换默认权重或迟滞参数。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 已接入但需校准/部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback runtime 消费 | 已完成 D3 helper 与 main/runtime 接线。`evaluate_terminal_feedback()` 保持既有 action 兼容，writeback 新增 soft/hard scope 分类：普通 uncertainty 为 pair-soft，明确 friend/identity/duplicate/feasibility 风险 fail-closed；main/runtime 仍可使用原 metadata 字段。 | D3 只消费 D5/main 已聚合的 metadata，不自行判断视觉身份、不统计跨资源 duplicate lock，也不改写 `global_track_id`。 | 剩余是多 seed 校准：验证 edge-soft FOV、hard reject 和明确资源/目标 hard 在不同 N 规模、遮挡和 crossing 场景中稳定改善计划质量。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 validity/feedback 证据和严格 secondary activation/current-binding 合同；二级/分布式 commit 正例与缺 ACK fail-closed 已通过下游验证。 | D3 不选择二级节点、不续租、不执行 CBBA/拍卖或恢复仲裁。 | 后续中心恢复和长时 lease 校准属于 main/D4 policy，不是 D3 P1 合同缺口。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord`、`AssignmentEvidenceExport`、canonical `PlanningTickHistoryRecord`、validity summary、N/M replay summary 和 feedback calibration summary helper。最新 20-case 已写盘并可计算 plan/member/owner churn。 | D3 不写 D6 存储，也不拥有 episode log 总线；calibration helper 输出建议但不自动改默认参数。 | 写盘缺口对本批已关闭；下一步统一 canonical target 与 cooperative target 术语，并在真实动态 N/M 中继续标定权重和迟滞。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter、严格 secondary 合同、canonical history exporter 和 AirSim integration plan；最新 main runtime 完成 baseline/candidate 各 10 seeds 的 M5N2 20-case。默认 `2 primary + 1 standby reserve`，且不要求同时到达。 | history 20/20 可用且实际 plan/member/owner churn 为 0；但 pair/target/coalition=`12/60`/`12/40`/`0/20`，第二 primary `0/20`，20 个 stop reason 均为缺 collision object 的 `collision_stop`。 | main/runtime 补碰撞来源，D6 分离 canonical/cooperative 口径；D3 继续真实动态 N/M 标定，不因 candidate 非退化失败直接改算法。 |
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
4. **运行时总线持续校准**: D3 helper 已输出 metadata、summary、record、evidence、canonical history、binding、N/M replay summary 和 D5 feedback calibration summary。最新 20-case 已完成 main 写盘和 D3 只读复核；后续重点转为动态 N/M 多 seed、canonical/cooperative 术语统一和碰撞来源回灌。
5. **上游事件缺失**: duplicate terminal lock、D5 连续状态迁移、D2/D1 不确定性摘要和 D4 仲裁结果需要由其他模块或 main 聚合后再反馈给 D3。

## 6. 缺少条件

| 缺少条件 | 影响 |
|---|---|
| 真实非等量 N/M 与事件驱动多 seed | 2026-07-15 最新 M5N2 baseline/candidate 共 20 case 已有 3725 条逐时刻计划历史；仍缺真实 3v5、5v3、目标新增、资源失效、D5 模糊、D2 不确定和 crossing/dense 动态数据。 |
| D5 feedback 权重阈值长期标定数据 | D3 已能生成 advisory calibration summary；仍需要真实 D6 records 反复校准 `fov_difficulty_by_resource`、禁配边、operator hold、hold/replan/secondary_arbitration 阈值，避免过度重规划或过度 hold。 |
| D5/main duplicate lock 和多帧不一致聚合分布 | D3 不自行判断多资源终端锁定冲突；需要上游持续提供聚合事件，供 D3 权重阈值校准。 |
| P0-B 多 seed 标定证据 | baseline schema/helper 已完成；仍需要覆盖非等量 M/N、资源不足、高威胁目标、D5 模糊和 crossing/dense 场景，用于校准增强迟滞参数、资源状态阈值和 threat score baseline 权重。 |
| P1 增量/hard-window 长期校准 | 增量 API/schema 已完成；仍需真实动态事件和 hard time-window 多窗口/到达时间多 seed 校准。 |
| P2 optional 求解器证据 | 同输入容量 runner 与 SciPy 结果已完成；仍缺 installed Min-Cost Flow objective/assignment 对照，CP-SAT/MILP coalition 参考与复杂 flow 尚未实现。 |

## 7. 当前 D3 P0/P1 缺口与下一步优先级

1. **P0 done / 当前无开放 blocker**: 历史上曾发现 active plan 后 `previous_plan=None` 导致 version 回退到 1 的 P0 blocker；该缺口现已修复，因此当前恢复并确认无开放 P0 blocker。现在固定以 `previous_plan_required` 拒绝并携带 latest plan id/version，首次调用和新 planner 实例仍从 version 1 开始。Hungarian、fallback DP、迟滞、其他 stale/expected-version 检查、D7 binding、D6 export、current evidence export、P0-B 资源状态细化、P0-B 增强迟滞/stale rejection、P0-B threat baseline 和轻量 hard time-window baseline 继续保持回归。
2. **P1 switch-penalty matrix integration done**: penalty 已在 solve 前加入可行改配边，零 penalty/中等 penalty/较大 penalty 构造测试覆盖换配、单次计费和保持原资源；边界测试同时确认不可行边、无历史 assignment 的新目标和 unassigned cost 不受 penalty 污染，release 与 current binding 语义保持不变。
3. **P1 合同层 done / 协同物理闭环 open**: 2026-07-13 的 40 个真实 SimpleFlight M5N2 episode 中，baseline 为 `0/10`，最佳 `20 m / 3 s / 40 deg` 为 `5/10`，其余为 `2/10`、`1/10`，未达 `8/10`。`2 primary + 1 standby reserve`、无同时到达要求、版本/stale/role 和 reserve 安全合同保持；D3 history schema/export 已完成，下一验收是 main 写盘、D6 churn 与参数闭环。
4. **P1 D5 feedback 权重标定**: 用真实逐 tick D6 records 对 edge-soft FOV、hard reject、明确 resource/target hard、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty` 做配对扫描；验收抖动下降且高威胁未分配不恶化。40-case 现状只能提供根因线索，不能证明分类修复与 outcome 的因果。
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

D5 只做末端视觉配准和一致性证据。D3 给 D5 的 assignment 是“资源当前应关注的 `global_track_id`”，不是允许 D5 改绑的授权。D5 反馈被 D3 helper 转为 `hold/replan/secondary_arbitration` 建议，并通过 `apply_terminal_feedback_to_planner_inputs()` 分级写回 edge-soft FOV、hard reject 或明确 resource/target hard；普通 pair hold 不设置 `operator_hold`。main/runtime 已负责调用和记录。D3 文档和 DTO 均明确 `allow_local_rebind=False`，后续重点是用真实多 seed 结果长期标定 D5 feedback 权重阈值。

### 8.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 只消费当前版本 binding。对 secondary plan，main 必须把当前 `plan_id/version` 传给 D3 binding helper；不匹配、缺失 current confirmation、takeover 未激活或 lease 过期时 binding 为 stale/hold。D7 仍必须同时检查 D4 action 和 D5 lock，且不得本地换绑 `global_track_id`。

### 8.4 N 规模输入

D3 的 `target_count/resource_count` 来自输入数组长度。main 的 `--drone-count N` 只决定资源状态记录数量；目标数可以大于、小于或等于资源数。2v2 和 5v5 只作为 baseline 名称，非等量 M/N 也应通过同一 `AssignmentPlanner.plan()` 路径。

## 9. 关键依据路径

- `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`: SciPy Hungarian、dummy unassignment、DP fallback。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`: 滚动 plan、迟滞、版本推进、stale previous plan 拒绝、规模 metadata。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`: 代价矩阵和 cost breakdown。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`: `AssignmentPlan`、D5 feedback decision/writeback、secondary takeover DTO、D7 binding、`AssignmentValiditySummary`、D6 `AssignmentRecord`、`PlanningTickHistoryRecord` 与 canonical exporter。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`: optional OR-Tools Min Cost Flow benchmark 与 unavailable gate。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/p2_benchmark.py`: 共享非等量 N/M、hybrid role、容量约束输入和结构化双 solver outcome。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`: synthetic AirSim dry-run adapter。
- `research_modules/d3_assignment_planner/tests/test_planner.py`: 非 5v5 规模、迟滞、stale plan、cross-node fields。
- `research_modules/d3_assignment_planner/tests/test_solver.py`: Hungarian/fallback 行为。
- `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`: D5 feedback 映射、写回下一轮输入和不允许 local rebind。
- `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`: D7 binding stale/revoked/hold/reassigned/secondary takeover schema/owner/source/version。
- `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`: validity summary 和 D6 assignment record export。
- `research_modules/d3_assignment_planner/tests/test_plan_history_record.py`: canonical ordering、primary/reserve、owner/epoch/lease、feedback/hysteresis/cost、JSON 与 truth 排除。
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
| membership/version churn | D3 schema/export done；跨模块消费 open / unavailable | D3 已提供 canonical history；main 未写入 40-case aggregate、D6 未计算，不得将缺测推断或补零 |

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

本轮 D3 回归基线为 `157 passed, 1 skipped`（2026-07-14）；新增 5 个计划抖动/预算确定性测试函数，既有 canonical history 和 held-scope/lifecycle case 继续通过，唯一 skip 为 optional OR-Tools installed-only test。当前 D3-owned history/hold identity 和周期性换员实现 P1 已关闭；跨模块真实多 seed、生命周期准入和 reserve demotion 仍为 P1；OR-Tools/CP-SAT/MILP 保持 P2 optional。

## 13. Seed 001 计划范围泄漏 P1 复核（2026-07-14）

| 项目 | 级别/状态 | 证据与结论 |
|---|---|---|
| hold 时新目标进入 current unassigned scope | P1 done | 三类 hold 分支改为保留上一 execution scope；普通/M-to-N 新目标回归均保持 plan ID/version/signature |
| hold 候选范围审计 | P1 done | 新增 candidate/unassigned/incomplete、pending/missing target 和 audit-only policy 字段 |
| 上一执行目标从输入消失仍被 hold | P1 done | missing previous execution target 使 previous plan infeasible，绕过 same-assignment/dwell 并输出明确目标列表 |
| T008 等后段新生航迹准入 | P1 open，main/D2 owner | T008 34.4 s birth、34.5 s confirmed 并被提交、34.6 s engageable；D3 无 truth，不能本地删除 |
| 稳定双目标阶段周期性换配 | D3-owned P1 implementation done；main+D6 real replay open | 最新 347-record/v1..v35 seed 证明 soft-feedback/search cost 与 previous execution cost 混口径；现已统一比较口径并实现同 window 累计 change budget，确定性往返不再推进版本；至少 10 seeds 真实复验仍开放 |
| reserve 后续 active | P0/P1 integration open，main runtime owner | D3 v45 中 INT-01 仍是 standby reserve；runtime 未随角色变化撤销旧 active pair |
| 真实多 seed 复验 | P1 open，main+D6 owner | 历史审计为 349 tick/v45，最新 postfix 审计为 347 records/v35，均只有 seed 1；需至少 10 个同几何 seeds |

D3-owned hold identity 缺口已关闭，未新增 P0。全量 `157 passed, 1 skipped`，唯一
skip 为 optional OR-Tools。D3 不采用固定 M/N、truth 过滤、降低高威胁门限或放宽
stale/coalition gate 来掩盖 D2 幻影；正确 fail-closed 位置是 main/D2 lifecycle
admission 进入 `TargetTrack.assignable` 之前。

## 14. 同窗口累计预算与统一迟滞成本 P1（2026-07-14）

| 项目 | 状态 | 证据与验收 |
|---|---|---|
| `max_changes_per_window` 语义 | P1 done | `d3_cumulative_window_change_budget_v1` 从 previous plan metadata 延续同 `window_id` 已接受 change count；hold/refresh 不消耗，新 window 清零 |
| candidate/previous 成本口径 | P1 done | `d3_hysteresis_current_objective_v1` 双侧包含 base edge、hard feasibility、当前 demand/unassigned；双侧排除 switch、soft-feedback FOV、slot priority/role pin search shaping |
| 往返换员稳定性 | P1 deterministic done | 小幅往返噪声和 soft feedback candidate 不再虚假通过 `delta=0.2`；同 window 第二次普通 change 在累计 2/1 时 hold |
| 硬条件优先 | P0/P1 safety regression done | missing execution target、资源 unavailable 和 plan-level owner/activation/authorization 变化立即产生新 identity；预算耗尽的资源硬失效记录 bypass |
| missing + membership hold | P1 done | previous-only target 不作为 membership change 审计；另一联盟即使要求 hold，消失目标也不进入 assignment/coalition/audit |
| 动态规模与身份 | 保持 | 实现按输入 target/resource/demand 运行，无 2v2/5v5 常量，不消费 truth，不改写 `global_track_id` |

验证日期为 2026-07-14。动因样本是最新 truth-isolated M5N2 seed 1 的 347 条
planning records 和 v1..v35；代表性旧记录为 candidate coalition `0.8868` 对
previous `2.8520`，其中 previous 含 `2.2` soft-feedback FOV，统一 base 后 previous
约 `0.6520`，候选不满足 20% 改善。本批新增 5 个确定性测试函数，D3 全量
`157 passed, 1 skipped`，接受阈值为零失败；skip 为 optional OR-Tools 未安装。
未重跑 Blocks，因此真实 10-seed churn、高威胁未分配和物理完成率仍开放，不能把
确定性关闭写成系统物理 P1 已关闭。

## 15. Actual-v2 P0 证据链与开放 P1（2026-07-14）

| 项目 | 真实证据 | 状态 |
|---|---|---|
| 2v2 plan identity | command/actual/history=`d3-plan-c3cc6d28c365/1`；24 条 history | P0 done |
| M5N2 plan identity | command/actual/history=`d3-plan-cfdd088a10e1/1`；214 条 history | P0 done |
| D6 history validation | available/unavailable=`2/0`；reasons=`{}` | P0 done |
| M5N2 feedback | churn=50；plan/membership/owner churn=0 | P1 open |
| M5N2 physical | pair/target/coalition=`2/3`/`2/2`/`0/1`；第二 primary 约 11.02 m | P1 open |
| 统计充分性 | 两个场景均仅 seed 1 | P1 open |

本批只关闭计划身份从 history 到 command 和 actual metrics 的可追溯性。目标级
`2/2` 不能用于关闭 required-primary 联盟完成；第二 primary 与多 seed 保持 P1。

## 16. 最新 M5N2 20-Case GAP 状态（2026-07-15）

| GAP/证据 | 最新状态 | 结论 |
|---|---|---|
| canonical history 写盘 | P1 evidence done for this batch | 20/20 case、3725/3725 record 可用；baseline 1869、candidate 1856 |
| 动态 N/M 与任务结构 | P1 evidence done for M5N2 | 3725 条均为 5 resources/2 targets；T001 2 primary+1 reserve，T002 1 primary |
| plan/version churn | available，0 transition | 每 case 单一 `plan_id/version=1`；首次发布不计重分配 |
| member roster churn | available，0 transition | 3555 条 membership audit 均未改变 current roster |
| owner/stale/rollback | available，均为 0 | owner 始终 center；无 stale reject 或 rollback |
| 第二 primary/coalition 物理闭环 | P1 open | 第二 primary 0/20，coalition 0/20；canonical target 12/40 不能替代联盟结果 |
| collision lineage | P1 open，main/runtime owner | 20 个第二 primary 均 `collision_stop`，但没有 collision object/category |
| candidate 晋级 | 未通过，不归类为 D3 退化 | baseline/candidate 的 D3 current plan 与成员均稳定；candidate 系统级 paired non-degradation=false |
| 真实动态 N/M | P1 open | 仍缺 3v5、5v3、目标新增、资源失效和需求切换的 AirSim 多 seed |
| 术语统一 | P1 cross-module open | 区分 `canonical target success` 与 `cooperative target diagnosis` |

本轮不新增 D3 P0。D3 计划历史写盘/churn availability 缺口已对最新 M5N2 批次关闭，
但物理联盟闭环不能因此关闭。跨 case 成员组合存在差异，第二 primary 必须按 current
plan 的 target/role 识别，不能固定资源编号。`png_ttc_2v2_seed001` 排除在本批聚合
之外；其余 tuned case 未执行，dropout=0，缺失项保持 `unavailable`。

验收命令 `python3 -m pytest -q research_modules/d3_assignment_planner/tests` 返回
`157 passed, 1 skipped`，零失败达到门限；owned-path `git diff --check` 通过。

## 17. Scalable-3D / Learning-Assist GAP（2026-07-20）

| GAP/能力 | 当前状态 | 证据与边界 |
|---|---|---|
| 三维 rule cost | P1 interface done | NED position/velocity/covariance、解析 reachability、region cost/hard gate 单测通过 |
| 稀疏候选 | P1 deterministic done | per-target top-k、不低于 demand、保留 previous feasible edge；200v200=800 edges |
| 非等量 N/M | deterministic support done | 3v5、5v3 同路径通过；真实多 seed 仍 open |
| M-to-N 稀疏槽 | regression done | 2-target/5-resource、high-threat k=3 完整联盟；all-or-none 不变 |
| action mask | P0/P1 safety done | 不可达、capacity=0、friendly conflict、version mismatch 均不可学习绕过 |
| residual formula | P1 interface done | 严格 `C_final=C_rule+alpha*tanh(delta_C)`，最终 Hungarian 不变 |
| fail-safe fallback | P0/P1 deterministic done | timeout、low confidence、OOD、invalid/error 返回逐元素相同 `C_rule` |
| shared PyTorch edge policy | minimal tested | 32-edge synthetic BC loss 下降；无固定 40,000-action head |
| 真实 BC 数据/checkpoint | P1 open | 尚无 D2/D3 trajectory labels、split、版本化 artifact 和 replay evaluation |
| shadow non-degradation | P1 open | 尚无未见 seed、收益/安全配对统计和 confidence/OOD threshold calibration |
| PPO | P2 unavailable | gymnasium/SB3 不在环境；未实现、未训练、未验收 |
| 200v200 系统性能 | P1 open | 单样本 200/200、0.621 s；无重复分布/阶段归因/闭环实时结论 |

本轮关闭的是 D3-owned 规则/接口/确定性安全 GAP，不关闭真实训练或系统 outcome GAP。
新增 13 个测试后全量为 `170 passed, 1 skipped`，零失败达到门限；skip 仍是 optional
OR-Tools。`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：本批未接 AirSim adapter、runtime
或 actor/control 合同，因此不改其已验证/未验证状态。`docs/EXPERIMENT_REPORT.md` 只
记录本地确定性样本，并明确不是 AirSim/PPO 证据。

## 18. 200×200 性能与区域计划合同 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| top-32 仍遍历全部 Python pair | D3-owned closed | 40,000 次全边调用降为 0；只物化 6,400 个候选 breakdown |
| 200×200 D3 成本/求解耗时 | deterministic benchmark done | 同进程 5 次中位 1904.261 ms -> 85.367 ms，22.307×；不是全栈实时验收 |
| 向量化规则语义 | D3-owned closed | 20×23 矩阵、mask、reject reason 一致，breakdown 容差 `1e-11` |
| 稀疏 Hungarian | D3-owned closed | SciPy 默认；候选二部图按连通分量求解，无候选目标走未分配代价 |
| 复杂 pair-specific 约束 | regression protected | 自动回退旧路径；尚未向量化，不影响既有语义 |
| D4 裁决的多个 secondary owner | D3 interface done | 单计划、多区域 owner、epoch/lease/source 校验通过；main/D4 尚待映射 |
| secondary/distributed k=1 | D3 contract aligned | 区域授权可不建原子联盟；显式 summary 只接受 single_member_authorized、非 atomic、完整成员和当前 lease |
| fully distributed k>1 coalition | D3 interface done | commit_required、committed、atomic、完整 ACK、成员/epoch/lease 一致才发布；运行时闭环仍 open |
| stale/old epoch/expired lease/missing ACK | D3 fail-closed done | 专项测试均拒绝；尚需 main 故障注入复验 |
| 区域计划 D6 指标 | cross-module P1 open | 尚缺 owner transition、commit latency、reject reason 和 lease violation 汇总 |
| AirSim/多 seed | P1 open | 本批未运行，不以模块 benchmark 替代系统证据 |

本轮没有新增 D3 P0。D3 全量共收集 194 项，`193 passed, 1 skipped`，零失败满足门限；
唯一 skip 为 optional OR-Tools。main 需要复跑施工中间态曾失败的 5v5、200v200、中心
失效和二级失效 module-stack 回归，并把 D4 区域裁决接入
`plan_regional_authority()`。在该接线完成前，多 owner 和 fully distributed 仍标为
接口已实现、系统未集成。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已复核。本轮未改变 AirSim adapter、actor、控制、
话题或 settings，因此不改该文件。实验文档已新增本地性能和合同证据，并明确未运行
AirSim、多 seed 或全栈实时验收。

本次 D4-D3 复审关闭了 distributed k=1 被误判为缺少原子提交的合同缺口。修复只按
需求数区分 single-member authority 与 atomic coalition commit；k>1 的 committed、
atomic committed、全 ACK、成员/协调者/epoch/lease 一致性门限保持不变。main 仍需
把 D4 `CoalitionCommitSummary.commit_required` 原样映射并运行 module-stack 回归。

## 19. 故障代际 Fence GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与边界 |
|---|---|---|
| 分配未变时 forced replan 不升版 | 语义保持 | 普通重规划仍正确返回原 identity，不用于故障隔离 |
| D4 owner change generation fence | D3-owned closed | `advance_authority_generation()` 严格 +1 并正常 publish |
| assignment/coalition 不变 | deterministic done | k=3 成员、角色、coalition id/version 和执行签名一致 |
| stale/rollback/重复版本 | fail-closed done | expected mismatch、旧 source 和 duplicate fence 均拒绝 |
| fence 伪造执行变化 | fail-closed done | coalition 篡改及 owner/授权变化不允许进入 fence 路径 |
| D4/D7 安全边界 | interface done | metadata 标记非授权并要求 D4 gate；D7 不得仅凭 fence continue |
| 50v50 中心故障接线 | cross-module blocker open | main 尚未在 D4 裁决前调用接口和复跑场景 |

发现时该问题阻断 50v50 中心故障区域裁决，属于运行级 P0 集成阻塞。D3-owned 接口和
发布门控已关闭，系统级状态仍为 main/D4 接线待验。新增 5 个测试后全量共 199 项，
`198 passed, 1 skipped`，零失败达到门限。AirSim 集成文档已检查：本轮没有修改
AirSim adapter、settings、actor 或控制合同，因此无需更新；scalable 3D runtime 由
main 另行接线，D3 不跨模块修改。

## 20. BC/PPO/Shadow 研究管线 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 可复现学习数据 schema | legacy v1 superseded by section 23 | 原 scenario+seed split 存在跨场景同数值 seed 泄漏；v1 不再接受 |
| truth/edge leakage | deterministic fail-closed | allow-list entity schema，不保存原 ID/metadata；同 seed 跨 split 和重复 frame 均拒绝 |
| model bundle | D3-owned implemented/tested | manifest+state_dict+SHA256；feature/schema/policy/split/normalization/guardrail/training/promotion 完整，weights-only strict load |
| bundle fallback | P0/P1 safety done | missing、SHA、feature/policy mismatch 和 version constraint 返回逐元素相同规则矩阵 |
| multi-episode BC | pipeline implemented/synthetic tested | frame mini-batch 学习 rule edge/residual/advice，输出 train/validation loss 与 whole-seed metrics |
| native PyTorch PPO | P2 research pipeline implemented | clipped actor-critic、GAE、pooled value、bounded sparse residual、low-frequency advice；counterfactual reward 仍经 deterministic solver |
| fixed 200x200 action head | closed | shared edge network 对 3v5、5v3、200 candidate edges 输出同形 residual，无 roster-size 参数 |
| paired shadow evaluator | pipeline implemented/synthetic tested | 同 seed rule/proposal 成本、high-threat unmet、churn、duplicate/hard violation、P50/P95、fallback 可报告；规则矩阵不变 |
| assist promotion gate | fail-closed implemented | manifest 必须 >=20 unseen test seed、零 fallback、安全和成本非退化；19 seed 即使手写 recommended 也拒绝 |
| 真实训练/准入 | P1 open/unavailable | 无真实 D2/D3 trajectory、正式权重、>=20 未见真实/高保真 seed、AirSim outcome 或 deadline calibration |

以下 30-seed、60-frame synthetic smoke 属于 legacy v1：split 为 23/1/6 seed 和 46/2/12 frame。BC train
loss `1.1001 -> 0.5014`、validation `0.3768`；46-transition PPO 更新指标有限；test
shadow P50/P95=`0.281/0.350 ms`，fallback/duplicate/hard violation 均为 0。但
assignment-cost non-degradation=false，test 只有 6 seed，且 source synthetic，所以
promotion 为 `false/unavailable`。该结果把旧“数据/checkpoint/PPO 管线未实现”改为
“管线已实现、真实数据和准入仍开放”，不关闭 outcome GAP。

新增 16 个专项测试后 D3 全量共收集 215 项，最终为 `214 passed, 1 skipped`
（6.95 s），零失败达到门限；唯一 skip 是 optional OR-Tools installed-only case。
`research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：没有修改
adapter、actor、settings、控制、D7 或 runtime 接口，因此无需变更。实验文档只记录
synthetic smoke，并明确不是 AirSim、正式 PPO 收益或 promotion 证据。

## 21. 真实 Episode 学习帧证据 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| main 无法取得真实规划矩阵 | D3-owned closed | 公开 `latest_planning_evidence` 同时保存 rule/effective `CostMatrixResult` 和计划上下文 |
| main 重建私有矩阵可能漂移 | D3-owned closed | `build_latest_learning_frame_record()` 直接消费 planner 最近成功帧；synthetic generator 已移除私有调用 |
| shadow/assist/fallback 混淆 | deterministic closed | `rule_only/shadow_proposal/assist_effective/rule_fallback` 分离；fallback 要求 effective 与 rule 完全一致 |
| held/unchanged/forced replan | deterministic closed | 当前 timestamp/previous version 与当前输入矩阵可记录，不复用旧矩阵 |
| regional authority | D3 interface done | 有效 authority 记录 `selection_source=regional_authority`；拒绝路径清空旧 payload 并给 reason |
| 失败后返回陈旧帧 | fail-closed done | stale、invalid regional、fence、unmatched publish 和一致性失败均 `available=False`、payload 为空 |
| 外部反向修改 planner | deterministic closed | ID 匿名化，array 为 immutable buffer，mapping 只读；修改生成 record 不影响 retained evidence |
| 在线总线/仿真身份泄漏 | D3-owned closed | 证据不进 plan metadata/DTO；track/resource/assignment 仅 ordinal token，无 truth/actor/object/upstream metadata |
| 真实整 seed 导出 | cross-module P1 open | main 尚未在 IntegratedScalableModuleStack 调 helper，也未形成 AirSim sequential dataset |
| 真实 shadow/assist 准入 | P1 open/unavailable | 仍缺 >=20 未见真实/高保真 seed、paired non-degradation、deadline/OOD/confidence 标定 |

本轮把“D3 已有 frame builder 但无法取得真实调用使用的矩阵”从接口 GAP 改为
implemented/tested；它不关闭真实数据与系统 outcome GAP。新增 11 个专项测试覆盖首帧、
held/unchanged/forced replan、shadow、assist、learning/solver fallback、regional 正负例、
失败清旧帧、外部修改隔离和 1x3/3x2/7x4。2026-07-20 D3 全量收集 226 项，结果
`225 passed, 1 skipped`，零失败达到门限；唯一 skip 是 optional OR-Tools。

`README.md`、`PLAN.md`、三份 D3 review/GAP 和模块内四份主题文档已同步。AirSim 文档
只新增 recorder 接线计划，明确本轮未修改 adapter、settings、actor/control 或运行真实
episode。根级 main/system 文档不在 D3 owned paths，由 main 在集成 helper 后同步实际
seed/frame/result。

## 22. 区域资源提示到候选图 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| D4 recommendation 无 D3 公共入口 | D3-owned closed | `regional_planning_hint` 可接 DTO 或严格中性 mapping；不导入 D4 |
| 提示来源与时效 | deterministic fail-closed | source plan 精确匹配，created/expiry 和逐区域 lease 同时有效 |
| quota/transfer 资源守恒 | deterministic fail-closed | projected、总 delta=0、逐区域 transfer 净额一致；非法提示有 reason 并回退 |
| committed/coalition/reserve 保护 | deterministic closed | previous assignments/coalition members 全保护，reserve 按 post-quota 向上取整 |
| 跨区许可只写 metadata | closed | 合法 route 真实修改 candidate mask，1-to-1/M-to-N 均由 Hungarian 选中 |
| transfer cardinality | deterministic closed | route 固定互斥资源池 + 全局资源唯一性，actual 不超过 allowance |
| D5/learning/迟滞兼容 | regression covered | hard edge 不重开，learning 只见受约束 mask，既有反馈/版本路径保留 |
| D6 审计字段 | D3 interface done | available/considered/applied/rejected、identity/reason、allowed/actual 和跨区总数 |
| main/D4 映射 | cross-module P1 open | 尚未把 `RegionResourceRecommendation` 映射为 DTO，也未处理 reset 后 advisory 生命周期 |
| AirSim/多 seed/性能 | P1 open | 无新 episode、正式多 seed、时延分位数或物理结果 |

本轮把“D4 区域聚合建议只能停留在 metadata/离线报告”改为“D3 候选约束合同已实现，
系统接线待完成”。新增 14 个 fixture case；2026-07-20 全量收集 240 项，结果为
`239 passed, 1 skipped`，接受门限为零失败，skip 是 optional OR-Tools。该证据不关闭
main-owned 时序接线、D6 多 seed 非退化、AirSim 或物理拦截 GAP。

## 23. 跨场景数值 Seed 隔离与流式写出 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 同 seed 跨 scenario/scale 泄漏 | D3-owned closed | split identity 改为纯数值 seed；2v2/5v5 风格双 scenario、多 episode/多 frame 复用测试通过 |
| episode/frame 原子性 | deterministic closed | 完整 catalog finalize；同 seed 任一 frame 改 split 即拒绝，重复 frame 由唯一键拒绝 |
| 三 split 数量与零交集 | fail-closed closed | 按唯一数值 seed 数量分配；少于 3、任一 split 空、声明 unseen 不足均拒绝 |
| dataset/split schema | v2 implemented/tested | `d3_learning_dataset_v2` + `d3_numeric_seed_atomic_split_v2`；manifest 固化 split 参数、逐 split seed/episode/frame 数、split hash、frame SHA |
| bundle/shadow schema | v2 implemented/tested | bundle v2 绑定 dataset/split v2；shadow report v2 按数值 seed 聚合；v1 稳定拒绝 |
| hash/loader 篡改 | deterministic fail-closed | 逆序输入同 canonical frames/manifest/hash；frame SHA、split 映射、统计和 policy 均重算 |
| training/shadow unseen 计数 | closed | BC/PPO/shadow 先验完整三分；whole-seed/unseen 不再把同一 seed 的多个 scenario 重复计数 |
| D3 writer 全量内存 | D3-owned closed | iterator + 临时 SQLite + 批次提交 + 增量 SHA；输入不再 `tuple(sorted(...))` |
| main batch finalize 全量内存 | integrated/closed | scalable main 已把 `iter_learning_frame_records(...)` 直接传给 writer，不再完整读取/构造 tuple |
| 正式模型与性能 | P1 open/unavailable | 本批未训练、未跑 AirSim、无模型 loss/成本/时延/物理收益结论 |

200v200 dense fixture 有 40,000 candidate edge；单帧 canonical JSON 为 5,854,691 bytes，
NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。40 帧时，main 现有文本加上述对象的
保守下界超过约 440 MB，尚未计 `read_text`/`splitlines` 重复和 JSON 临时对象。因此
D3 API 的有界写出已实现，但正式 200v200 全链路内存 GAP 只有 main 调用 iterator 后才能
关闭。

2026-07-20 D3 全量收集 244 项，结果为 `243 passed, 1 skipped`，接受门限零失败达到；
唯一 skip 是 optional OR-Tools installed-only benchmark。`README.md`、`PLAN.md`、D3
review/GAP、模块内 `MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`、
`AIRSIM_INTEGRATION_PLAN.md`、`EXPERIMENT_REPORT.md` 和 docs index 已同步。AirSim 文档
明确本批未改 adapter/settings/actor/control、未运行 episode；实验文档只记录软件合同。
根级 `docs/**`、main/scalable 调用点不在 D3 owned paths，由 main 汇总同步。

## 24. Learning 训练与 Promotion Fail-Closed GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| BC/PPO 消费 test seed | D3-owned closed | BC 只接收 train/validation、PPO 只接收 train；任一训练 API 遇 test 报错，BC whole-seed metric 无 test |
| frame truth/identity 泄漏 | deterministic closed | v2 完整字段 allow-list；任意层级 truth/actor/identity/entity-ID/UUID/vehicle-name 键拒绝，匿名字段强类型校验 |
| candidate hint 重开 hard reject | safety closed | 候选索引、assistant 返回与 solver mask 均和 reject-reason allow mask 求交；shape 错误失败关闭 |
| bundle 与数据内容脱钩 | integrity closed | bundle/promotion evidence 同时绑定 split SHA、canonical frame SHA、state-dict SHA；错配拒绝 |
| promotion 口径可绕过 | safety closed | assist 强制 eligible 正式 test paired evidence、严格类型、>=20 unseen seed、零 fallback、安全/成本非退化；bypass/validation/non-eligible 拒绝 |
| shadow objective 不可比 | metric closed | rule/proposal 方案统一按 `rule_cost_matrix_v1 + unassigned_costs` 重评分，不比较不同矩阵 objective |
| 正式权重/promotion | P1 open/unavailable | 无真实 D2/D3 训练、>=20 未见真实/高保真 test seed、正式权重或 assist promotion 结论 |
| AirSim/200v200 模型收益 | P1 open/unavailable | 本轮未运行 AirSim 或全栈模型性能实验；同步 timeout 仍不可抢占 |

负例覆盖 test-seed 输入、指标隔离、递归字段、mask 不一致、frame/evidence hash、证据
split/eligibility/bypass/type 和共同成本基准。2026-07-20 D3 全量收集 252 项，结果为
`251 passed, 1 skipped`，零失败达到门限；唯一 skip 是 optional OR-Tools installed-only
benchmark。上述关闭项是 D3 software contract，不把模型提案升级为计划或执行授权。

## 25. 200×200 学习帧导出 CPU/内存 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 候选边重复 demand 构造 | D3-owned closed | 6,400 edge 从逐边构造改为 200 target 缓存；frame build 48.19 -> 22.99 ms |
| reject reason 重复扫描 | D3-owned closed | frame 复用 action-mask reason count；硬拒绝内容不变 |
| JSONL identity 递归标量调用 | D3-owned closed | 改显式容器栈；递归字段拒绝正负例保持，decode/validate 95.92 -> 56.09 ms |
| SQLite 保存完整 payload | D3-owned closed | SQLite 只存 key/offset/size；payload 使用临时 JSONL sidecar |
| finalization 二次 decode/rebuild/encode | D3-owned closed | 受控 split 占位符流式替换；6-frame median 910.20 -> 243.65 ms |
| 构造后可变状态逃逸校验 | fail-closed closed | writer 重新校验 mask/shape/finite/anonymous schema；真值键和 mask 篡改均拒绝 |
| schema/content/hash 漂移 | deterministic closed | expected legacy semantic bytes 与优化输出完全相同；正逆序、frame SHA、manifest 回归通过 |
| D3 finalization 峰值 | improved, not zero-copy | 匹配 cProfile/Tracemalloc 14,575,699 -> 12,725,690 B，下降 12.69% |
| 74-76 s 总 staging 归因 | cross-module P1 open | D3 六帧完整导出阶段约 0.87 s；main 必须用 D3/D4/D5 分项 wall fields 定位其余耗时 |
| JSON `tolist/dumps` | residual P2 optimization | 已为主要热点；无新依赖和无格式变化条件下保留，后续只能 optional adapter 对照 |
| 正式数据/模型准入 | P1 open/unavailable | 仍缺正式连续数据、训练、>=20 未见 seed、shadow 非退化和 assist promotion |

本轮没有新增 P0。top-32 单帧约 2.20 MB、九场景 D3 帧约 27.86 MB，因 schema/content
保持要求没有减少。微基准属于同机开发归因证据，不是硬实时、AirSim 或 200v200 全栈
验收。D3 全量收集 255 项，结果 `254 passed, 1 skipped`，唯一 skip 为 optional
OR-Tools，零失败达到门限。

`README.md`、`PLAN.md`、`MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md`、`EXPERIMENT_REPORT.md` 和 D3 review 已同步。
`AIRSIM_INTEGRATION_PLAN.md` 仅纠正 main 已采用 iterator 并记录未运行 AirSim；没有改变
settings、actor、camera、control 或 episode 合同。M-to-N 算法和成员合同未变化，因此
`D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md` 检查后无需修改。
