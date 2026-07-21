# D3 Assignment Planner

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `src/d3_assignment_planner/fixtures.py`: versioned non-equal, dynamic-event, D5-feedback, and hard-window fixtures.
- `src/d3_assignment_planner/calibration.py`: reusable full/incremental P1 matrix runner and D6-friendly summaries.
- `src/d3_assignment_planner/cooperative_prescreen.py`: versioned M-to-N cooperative candidate grid, observed-result ranking, and current-plan metadata export.
- `src/d3_assignment_planner/learning.py`: optional shared candidate-edge PyTorch residual, behavior-cloning warm-up, shadow/assist inference, masks, and rule fallback.
- `tests/`: unit tests.
- `simulations/run_rolling_assignment.py`: 100 s, 2 Hz rolling simulation.
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`: Chinese algorithm principles and implementation guide.
- `docs/EXPERIMENT_REPORT.md`: experiment method and latest local results.
- `docs/AIRSIM_INTEGRATION_PLAN.md`: AirSim offline integration plan.
- `results/`: generated CSV, JSON, plots, and generated report after running simulation.

## Test

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
pytest
```

## Simulate

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

Optional fallback-only run:

```bash
python3 simulations/run_rolling_assignment.py --force-fallback
```

The default run uses 8 targets, 8 resources, 100 seconds, and 2 Hz. It compares no hysteresis with `delta=0.2` and `min_dwell=2.0`.

## M-to-N Demand Slots

`AssignmentPlan` now publishes `assignment_plan_v2`. A `TargetTrack` with no
`demand` keeps the original `k=1`, `independent`, Hungarian behavior. An
explicit `TargetDemand()` selects the high-threat research default `k=3`,
`hybrid`: two `primary` members in wave 0 and one `reserve` in wave 1.
`TargetDemand.primary_resource_count` controls that split and defaults to 2;
main's `--cooperative-primary-count` should be passed into this field. It must
satisfy `1 <= primary_resource_count <= required_resource_count`. The implicit
and explicit independent `k=1` demand uses `primary_resource_count=1`.

The `hungarian_demand_slots` path expands each target into role/wave/capability
slots, prioritizes higher-threat targets, and performs all-or-none admission.
An incomplete coalition publishes no executable `Assignment`; its
`CoalitionPlan` and `DemandSatisfactionSummary` retain candidate members plus
`demand_required`, `demand_assigned`, `demand_shortfall`, and completion state.
`simultaneous`, `sequential`, `hybrid`, and `independent` scheduling modes are
supported. Arrival windows, wave interval, minimum separation, and required
capability counts are explicit demand fields.

Use `assignments_by_target()` for multiplicity and `assignment_by_resource()`
for the resource index. The legacy `assignment_map()` remains valid for
one-to-one plans and raises `ValueError` for multi-resource targets. Stable
assignment signatures drive hysteresis, change counts, and switch penalties;
coalition member/role changes increment coalition version; executable window
changes increment plan version, while pure cost evaluation preserves it. D7 bindings
carry coalition identity, role, wave, mode, window, and minimum separation, and
only a current committed coalition can produce an active binding.
Changing `primary_resource_count` also changes the coalition demand signature,
increments coalition version, and is exported in binding fields/metadata.
`AssignmentPlan.execution_signature()` additionally covers executable bindings,
coalition state/members, role/wave/windows, owner, and activation/lease semantics.
For both `k=1` and `k>1`, a pure cost/evaluation refresh retains executable
`plan_id/version`, assignment `plan_version`, `created_at`, and coalition
`version/epoch`; it sets `evaluation_refresh_only=True` and updates only
diagnostic costs and `last_evaluated_at_s`. A resource/role/target/owner or
activation change advances executable identity. Secondary takeover is an
explicit new lineage. Plan and assignment metadata keep lineage creation time
in `identity_created_at_s` and the current evaluation tick separately.

OR-Tools is not a default dependency. The isolated P2 benchmark feeds one
unequal-N/M, hybrid primary+reserve, capacity-constrained demand-slot problem
to SciPy Hungarian (capacity-column expansion) and optional OR-Tools min-cost
flow (native resource capacities). Missing dependencies are returned as a
structured `unavailable_reason`; the default planner does not select either
benchmark adapter dynamically.

Run the isolated comparison with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p2_capacity_benchmark.py
```

The checked fixture has 4 resources, 3 targets, 5 demand slots, and capacities
`(2, 1, 1, 1)`. SciPy Hungarian returns objective `5.6`. In the current
environment OR-Tools is absent, so its result is `status="unavailable"` rather
than a failed benchmark run. This slot-level comparator checks capacity and
cost equivalence; it does not implement online coalition all-or-none admission.

## Incremental Planning

`AssignmentPlanner.plan_incremental(...)` accepts the current tracks/resources,
the exact published `previous_plan`, declared `changed_track_ids` and
`changed_resource_ids`, timestamp, and expected previous version. Every normal
plan stores deterministic track/resource/demand fingerprints. The incremental
entry compares those snapshots with the declared changes, builds the current
target-resource feasibility graph, and solves only the disconnected component
reachable from changed entities and their previous bindings. Unaffected
feasible assignments and coalition members retain their target/resource,
coalition identity/version, role, and wave; plan-version and evaluation metadata
are refreshed through the standard publication path.

The implementation is deliberately conservative. Missing snapshots, omitted
changed IDs, target/resource set changes, demand changes, expired plans,
time-dependent constraints, or a component that expands to the global problem
run the standard full planner and record `incremental_fallback_reason`. An
expected/current plan-version mismatch remains `StalePlanError` and exposes its
reason through `to_metadata()`; it is not silently replaced. Hysteresis is
applied after the local candidate is merged into the full plan, so relative
gain, dwell, change limits, high-threat release, M-to-N all-or-none admission,
and switch-penalty single charging keep their existing global semantics.

`summarize_incremental_planning_comparison(...)` compares incremental and full
plans by cost, assignment equivalence, latency, target-level change count, and
preserved assignment count. Latency is calibration evidence only; the planner
does not automatically choose a path from one timing sample.

`run_p1_assignment_calibration_matrix(...)` runs the same planner profile over
5v5, 3v5, 5v3, target arrival, resource failure, high-threat demand change,
D5 reserve feedback, and hard-window transitions. Each row reports full versus
incremental latency, churn, unassigned high-threat count, coalition shortfall,
hard-window rejects, equivalence, fallback reason, and role-aware primary
preservation. It is an offline calibration harness and never changes the
default Hungarian/demand-slot path from timing results.

Run the deterministic matrix as JSON with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py \
  --output research_modules/d3_assignment_planner/results/p1_assignment_summary.json
```

The `--output` path is optional. When supplied, parent directories are created
and the same formatted `summary.as_dict()` JSON is written to the file and
printed to stdout.

## Cross-Node Contract

`AssignmentPlan` and each `Assignment` expose cross-node metadata for integration dry runs: `source_node_id`, `target_node_id`, `link_type`, `plan_version`, `stale_after_s`, `terminal_feedback_state`, and `duplicate_terminal_lock_risk`. D3 also provides `evaluate_terminal_feedback(...)` to map D5 states into conservative recommendations:

`AssignmentPlanner` is stateful for one episode. Its first `plan(...)` call may use `previous_plan=None` and creates version 1. Stale checks use only the latest published identity. `plan(..., publish=False)` returns a candidate without advancing latest, and `publish_plan(candidate)` publishes a reviewed candidate. After a plan is published, later calls must pass that exact active identity as `previous_plan`; omitting it raises `StalePlanError` with `reason="previous_plan_required"`. Main must create a new planner instance for a new episode; D3 does not provide an implicit reset.

- `ambiguous` / `hold` -> `hold`
- `reacquire` -> `replan`
- `mismatch` or duplicate terminal lock risk -> `secondary_arbitration`

The feedback decision includes `main_action` and `planner_metadata` so main can apply a conservative integration action without local rebinding. The metadata explicitly carries the backward-compatible hold/feasibility/FOV fields plus additive `feedback_constraint_class`, scope, hard-reject flag, and classification reason. `apply_terminal_feedback_to_planner_inputs(...)` classifies ordinary `ambiguous`, `hold`, `reacquire`, geometry/FOV, and detection-instability evidence as `resource_target_edge_soft`: it raises only that edge's FOV cost, keeps D7 on hold, and leaves `ResourceState.operator_hold=False`. `friend_overlap_hold` remains resource-hard, verified-friend evidence is target-hard, and safety identity conflict, duplicate assignment/lock, or explicit feasibility rejection remains fail-closed. Existing metadata names, including nested `resource_update`, remain accepted; a legacy pair hold is downgraded to soft and audited rather than expanded to the whole resource.

The writeback also preserves normalized `terminal_feedback_events` with target,
resource, source plan version, coalition reason/conflict, stable-lock counts, and
the upstream required stable window. Before ordinary cost hysteresis, both
`plan()` and `plan_incremental()` apply a version-matched dwell to coalition
primary membership. `PlannerConfig.transient_feedback_dwell_frames` defaults to
2; the effective window is the maximum of this value and D5's
`required_stable_frames`, so D3 cannot weaken the visual gate. A short
`primary_lock_stability_incomplete` or `reacquire` holds a still-feasible
primary set until that window completes. Completing the frame window does not
bypass ordinary `delta`, `min_dwell`, change-limit, or coalition-member
hysteresis. Duplicate/friendly conflict, wrong
binding, loss, resource unavailability, explicit prohibited edges, or any other
old-plan infeasibility bypass the dwell immediately. Feedback for another plan
version is audit-only and cannot protect or release the current coalition.

Per-member reserve feedback has a separate role-aware rule that does not depend
on coalition reason, stable-window fields, or a role supplied by main. D3 joins
each version-matched target/resource event to the previous plan assignment. If
every previous primary reports `consistent/continue`, at least one previous
reserve reports a soft `hold/hold` or `reacquire/replan`, and all old primary
edges and capabilities remain feasible, the demand-slot matrix pins exactly
that previous primary set. The solver may constrain or replace reserve slots
without rotating a healthy primary into reserve. The resulting reserve change
is still a candidate and must pass ordinary member/global hysteresis. Any primary failure,
duplicate/friendly/wrong-binding conflict, unavailable primary edge, changed
demand, or stale feedback disables the pin and follows the existing hard-risk
or primary-failure policy.

`ResourceState` also carries P0-B resource detail fields: `energy_fraction`, `availability_score`, `current_load`, `history_failure_rate`, `intercept_feasibility_by_target`, and `intercept_feasibility_score_by_target`. `CostModel` consumes them through `resource_state` subcomponents and hard infeasible flags, so D6-facing cost breakdowns can distinguish energy, availability, load, historical failure, and intercept feasibility causes.

`TargetTrack` supports a lightweight hard time-window baseline through explicit fields or metadata: `hard_time_window`, `time_window_open_at_s`, `time_window_close_at_s`, `time_window_state`, and resource-specific `time_window_by_resource`. When a window is explicitly closed, expired, or not yet open, `CostModel` marks that edge infeasible, sets hard-window reject flags in the breakdown, and `AssignmentPlanner` exports the rejected edge with a readable `reject_reason`; the soft `window_cost` term remains available for ordering open edges.

`compose_threat_score_baseline(...)` provides the P0-C explainable baseline for `TargetTrack.threat_score`. It combines critical-zone proximity, TTC, speed, covariance, and target state into a normalized score with components/reasons metadata. This is a baseline helper only; full outcome-aware dynamic threat assessment remains a P1 model-calibration item.

`PlannerConfig.reassignment_switch_penalty` is applied before Hungarian/fallback solve. For a target assigned in `previous_plan`, every feasible edge to a different resource receives the penalty; the edge to the same resource does not. Targets without a previous assignment and all unassigned costs are unchanged. The solver input matrix, per-edge breakdown `total`, selected `Assignment.cost`, plan objective, and exported evidence therefore share one cost value, with no post-solve double charge.

D3 also exports:

- `assignment_validity_summary_from_plan(...)` -> `AssignmentValiditySummary(plan_id, version, plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`.
- `assignment_records_from_plan(...)` and `assignment_evidence_from_plan(...)` -> D6/main outputs containing current plan identity, `identity_created_at_s`, `last_evaluated_at_s`, N/M shape, costs/reject reasons, hysteresis state, secondary audit fields, plus `assignment_profile_schema`, cost/feedback profile id/version, the exact cost-weight snapshot, and planner thresholds. A record without an explicit export timestamp uses `last_evaluated_at_s`, not the stable identity creation time.
- `plan_history_record_from_plan(plan, sequence_index=..., timestamp=..., previous_plan=..., feedback_metadata=...)` -> one canonical `PlanningTickHistoryRecord` per planning tick. `feedback_metadata` is optional and accepts `TerminalFeedbackWriteback.metadata`; otherwise compatible feedback keys are read from `plan.metadata`. Call `to_dict()` before JSONL persistence. The schema is `d3_plan_history_record_v1`, and history order is the lexicographic `[sequence_index, timestamp]` key supplied by main.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_incremental_planning_comparison(...)` -> `IncrementalPlanningComparisonSummary` with incremental/full cost delta, equivalence, latency, change counts, and preserved targets/assignments.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows whose metadata includes identity creation and last evaluation timestamps. Binding freshness and `expires_at_s` use `last_evaluated_at_s`, with `created_at` as the fallback for legacy/manual plans. Main supplies the current `plan_id/version` when exporting a secondary binding; a historical plan, an unconfirmed secondary current identity, an inactive takeover, or an expired lease cannot produce an `active/current` D7 binding.
- `prepare_secondary_takeover_plan(...)` -> activates a D4/main-selected takeover candidate only after main supplies sustained `takeover_ready`, activation time, a live lease, and a positive monotonic leader epoch. A same-signature candidate may retain the current center identity; the helper advances identity exactly once for the owner/activation transition. Successful plans audit readiness, activation, supersede, owner, lease, epoch, and `allow_local_rebind=False` in plan, assignment, record, evidence, and binding metadata.
- `continue_active_secondary_plan(...)` -> converts the next ordinary rolling candidate into a same-owner secondary plan without a second takeover. It derives the concrete owner/source from the previous active plan, requires strict version/supersede continuity, sustained readiness, non-regressing epoch, and a live non-regressing lease; main must not hand-build these metadata fields.
- `build_p1_assignment_fixtures()` -> versioned deterministic 5v5, 3v5, 5v3, new-target, resource-failure, high-threat demand-change, D5-feedback, and hard-window inputs. Labels use `resources x targets`; explicit counts and changed IDs are present in fixture metadata.
- `run_p1_assignment_calibration_matrix()` -> paired full/incremental transition rows and aggregate latency/churn/high-threat/coalition-shortfall totals for main/D6.

The plan-history payload stores plan identity/state/counts and owner/source/
secondary epoch/lease once per tick, then deterministically orders assignments
by target, coalition, wave, role, and resource. Each assignment includes role,
activation/active state, coalition identity/version/epoch, validity, scalar cost,
and cost breakdown. The record also contains recoverable ordered coalition
members, hysteresis and membership-change evidence, feedback classifications
with soft/hard counts, costs, stale/rollback/replan audit reasons, and plan
lineage. It uses only JSON-native values; no `truth_id` argument exists and any
truth-named nested metadata key is excluded. `assignment_records_from_plan()`
remains backward compatible, including its offline-only optional truth label.

Main should persist one line per successful planning tick as follows:

```python
history_record = plan_history_record_from_plan(
    plan,
    sequence_index=tick_sequence_index,
    timestamp=planning_timestamp_s,
    previous_plan=previous_plan,
    feedback_metadata=None if writeback is None else writeback.metadata,
)
jsonl_writer.write(history_record.to_dict())
```

D3 defines and validates this record but does not own JSONL storage. The
existing 40-case aggregate predates main persistence of these records, so its
membership/version churn remains `unavailable`; the former pair-hold promotion
is a root-cause lead, not proven causality for those outcomes. A later actual-v2
run has separately proved main persistence and D6 consumption, as recorded
below.

`PlannerConfig.human_authorization_state` is the source of the plan authorization field. The planner records both `configured_human_authorization_state` and `effective_human_authorization_state` in plan metadata so main can run record-only simulation gates without hard-coding D3 to `"required"`.

For active degradation recovery, D3 does not emit D4 actions itself. Main calls `plan(..., forced_replan=True)` with the current published plan. If executable semantics are unchanged, D3 preserves identity and returns `decision_state="replan_ack_no_change"`; if they change, D3 advances identity once and returns `decision_state="replan_applied"`. Main/runtime integrates these states and any `replan_reason`/supersede metadata. A binding from an applied current plan remains `active/current`; the old published identity is stale.

Main/runtime has connected D5 feedback writeback, center replan owner/version/source recording, secondary owner/version/source recording, and the P1 D4/D5 calibration sweep. For secondary flow, main should request `publish=False`, apply `prepare_secondary_takeover_plan()` or `continue_active_secondary_plan()`, then call `publish_plan()` on the final owner-stamped plan. This prevents an intermediate center candidate from advancing published latest.

The 2026-07-11 P1 validation used 5 resources, 2 targets, and 10
ComputerVision seeds. T001 achieved two-primary visual consensus with current
plan authorization in 8/10 seeds; seeds 7 and 27 remain regressions. Together
with the incremental planner and role-aware primary-preservation tests, this
closes the D3 P1 contract layer rather than only the earlier demand-slot DTO.
Downstream secondary and distributed commit positive cases passed, and a
missing ACK aborted fail-closed with no D7 permission. The 2026-07-12 PNG
delivery change made no D3 code or behavior change. Its 2v2 candidate reached
20/20 physical pairs and therefore demonstrated a non-regressed one-to-one
chain under the current plan gate. The M5N2 8 s run reached 0/9 active pairs,
but is not comparable to the existing z=-30 m, 35 s high-clearance baseline;
the cooperative physical loop remains open pending a same-geometry,
same-window paired run. P2 remains an isolated optional benchmark and does not
replace the default Hungarian/demand-slot planner.

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. For `secondary_plan_v2`, D3 does not choose a concrete secondary node, renew leases, elect leaders, or perform recovery arbitration. D4/main supplies those decisions; D3 validates the activation snapshot and prevents expired, non-monotonic, or non-current plans from yielding an executable D7 binding. Normal operation uses Hungarian/demand-slot assignment. The optional same-input capacity comparator is implemented and is not an open online P1 dependency. CP-SAT/MILP coalition admission, backup-resource quotas, multi-window flow, and large-scale sweeps remain isolated P2 benchmarks. D4 secondary-node arbitration is preferred before CBBA-style fallback.

Current D3 regression baseline (2026-07-14): `157 passed, 1 skipped` with `python3 -m pytest -q research_modules/d3_assignment_planner/tests`. The five newest deterministic tests cover soft-feedback/round-trip stability, cumulative same-window change budget, cross-window recovery, hard resource failure, missing-target plus another membership hold, plan-level owner change, and history budget export. Earlier plan-history, held-scope/lifecycle, and feedback-governance cases remain covered. The skip is the installed-only OR-Tools benchmark in an environment without the optional dependency.

## Per-primary authorization and coalition membership hysteresis

Cooperative demand now carries the versioned contract
`terminal_authorization_scope="per_primary"` and
`arrival_coordination_required=False`. Each active primary may therefore be
authorized independently by downstream D4/D5/D7 gates; a reserve binding is
explicitly `hold` with `reserve_standby_not_activated` and cannot execute
without a newer plan changing its role.

Per-pair diagnostics use the same contract in both D6 records and D7 binding
metadata. They expose plan owner/version, coalition id/version/epoch, role,
wave, activation, assignment validity, authorization eligibility, plan churn,
rollback detection, and stale-reject count. Only feasible active primaries are
reported as active/eligible; reserve rows remain standby and inactive. A
compatible current-plan evaluation refresh reports zero churn and no rollback
while preserving plan identity and coalition epoch.

For `k>1`, executable members and roles have a separate membership clock.
They remain fixed for at least `PlannerConfig.min_dwell` and may be replaced
only when the previous member set is hard-infeasible, or when the candidate
coalition cost improves by more than `delta` after dwell. Plan metadata exports
the previous/current member sets, reason, target cost comparison, dwell result,
and hold basis. Ordinary compatible cost refreshes preserve both `plan_id` and
plan version; coalition `version/epoch` advances only when a resource or role
actually changes. The Hungarian/demand-slot solver is unchanged.

## P1 Cooperative Candidate Prescreen

`build_p1_cooperative_candidate_grid()` defines the stable 27-candidate grid
used by main's M5N2 paired sweep: terminal handoff range `20/30/40 m`, primary
arrival-window width `3/5/8 s`, and approach-sector separation
`20/40/60 deg`. Candidate IDs are deterministic and do not depend on resource
or target count. `demand_for_cooperative_candidate()` applies only the timing
and audit metadata to an existing `TargetDemand`; required resources, primary
count, hybrid/simultaneous/sequential mode, capability requirements, wave
interval, and minimum separation remain caller-owned.

`export_cooperative_candidate_plan_metadata()` emits candidate ID, current
plan/coalition versions, target/resource IDs, role, wave, arrival window,
minimum separation, and an explicit activation state. A primary is `active`;
a reserve/retry is `standby`. The export rejects a non-current plan, stale
assignment version, or stale/non-committed coalition. It is read-only and does
not activate a reserve or alter Hungarian/demand-slot planning.

`rank_cooperative_candidates()` accepts only complete physical observations
from main/D6. It refuses missing candidate observations instead of estimating
success. Ranking is deterministic: zero safety violations first, then maximum
coalition-completion rate, maximum pair-success rate, minimum arrival spread,
and finally candidate ID as the tie break. The default output is the top three
candidates. D3 therefore supplies experiment design and plan/reachability
metadata; it does not manufacture AirSim outcomes. Same-geometry 10-seed M5N2
execution and the `8/10` coalition-completion acceptance target remain open at
the main/runtime level.

## 2026-07-14 真实 AirSim 计划历史审计

对 `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001`
的 `episode_006_full_flow` 做了单 seed、349 个 planning tick 的只读复核。D3
初始计划包含 T001 的 2 个 active primary、1 个 standby reserve，以及 T002
的 1 个 active primary。后段 D2 连续产生 T003/T005/T007/T008 等新航迹，最终
current plan 为 T001 三成员、T002 一成员和 T008 一成员，因此执行产物出现 5 个
pair。T008 在 34.4 秒创建、34.5 秒 confirmed、34.6 秒 engageable；D3 不使用
truth，无法把它判定为物理目标或幻影航迹。

审计发现一个 D3-owned P1 合同缺陷：当候选因普通迟滞、联盟成员迟滞或 transient
feedback dwell 被 hold 时，当前输入中的新目标曾被写入 held plan 的
`unassigned_target_ids`，从而使 execution signature 改变并错误推进 plan/version。
修复后 held plan 完整保留上一 current plan 的 assignment、coalition、unassigned
和 incomplete 执行范围；当前候选只进入 `hysteresis_candidate_*`、
`hysteresis_pending_new_target_ids` 等审计字段。候选释放前不获得 current plan
身份。该规则不依赖 truth，不写死 M/N，也不放宽 stale、version 或 coalition 门控。

本次确定性验收标准是 hold 后 plan ID/version 与 execution signature 均不变，同时
仍记录实际输入 `target_count` 和 pending target。若上一已分配目标从当前输入消失，旧计划
直接判为 infeasible 并发布新版本，不允许迟滞继续持有不存在的执行目标。D3 全量结果为 `157 passed,
1 skipped`；唯一 skip 是 optional OR-Tools installed-only benchmark。真实 episode
没有在本任务中重跑。

两个跨模块问题保持开放：AirSim adapter 当前把除 lost/dropped 外的 D2 航迹都标为
assignable，应由 main/D2 准入链只向 D3 提交 engageable 或显式批准的航迹；D3 不以
本地 dwell 掩盖 D2 幻影。其次，D3 最终仍把 INT-01 reserve 输出为 standby/hold，
`intercept_summary.json` 中后续 active 来自 runtime pair 在 primary 变为 reserve
时未撤销旧 active 状态，不属于 D3 reserve activation。

## 2026-07-14 P1 计划抖动预算与统一成本口径

最新 truth-isolated M5N2 baseline seed 001 有 347 条 canonical planning records，
执行版本为 v1..v35。稳定双目标阶段仍约每秒往返换员。记录中的一个代表性 tick
把候选联盟成本写成 `0.8868`、previous 写成 `2.8520`；previous 当前边内含
`2.2` 的 soft-feedback FOV shaping，去除该候选搜索项后 previous 基础执行成本约为
`0.6520`，候选并未达到 20% 改善。该现象证明原 membership gain 比较混用了
search objective 与 execution comparison objective。

planner 现在使用 `d3_hysteresis_current_objective_v1` 同时重评 candidate 和
previous：包含当前 target-resource 基础成本、硬可行性和
`unassigned_cost * required_resource_count`；排除只用于搜索的 switch penalty、
soft-feedback FOV shaping、demand-slot priority 和 role pin。solver/evidence 仍保留
完整 search cost，metadata 同时记录 search/comparison 两套数值，避免再把口径差异
误判为 `delta=0.2` 收益。

`max_changes_per_window` 现在由 plan metadata 延续
`d3_cumulative_window_change_budget_v1`：同一 `window_id` 累加已接受的 assignment
change count，hold/evaluation refresh 不计费，新 window 清零。execution target
缺失、资源硬失效和 plan-level owner/activation/authorization 改变仍立即生成新版本，
预算不足时记录 bypass；成员 primary/reserve 候选本身仍受 coalition hysteresis，
不会借 activation 名义绕过。missing target 与另一联盟 hold 同时出现时，消失目标
不会进入新 assignment、coalition 或 membership audit。

本批只完成确定性实现验收，未重跑 AirSim。D3 全量为 `157 passed, 1 skipped`，零
失败达到接受阈值；剩余 P1 是 main/D2 lifecycle admission、runtime reserve
demotion、至少 10 个同几何 seeds 的 churn/高威胁未分配复验，以及 M5N2 物理
coalition completion 从当前最佳 `5/10` 达到 `8/10`。

## 2026-07-14 Actual-v2 真实 AirSim 证据链

本次只同步 main 已完成的真实 AirSim 证据，不修改 D3 代码、Hungarian/demand-slot、
迟滞、版本或 primary/reserve 语义。两个 seed-1 sequence 的 command CSV、
`d7-actual-execution-metrics-v2` 与 canonical D3 history 使用相同计划身份：

| Case | command/actual/history plan | History | D6 feedback churn |
|---|---|---:|---:|
| tuned 2v2 | `d3-plan-c3cc6d28c365/1` | 24 | 3 |
| M5N2 | `d3-plan-cfdd088a10e1/1` | 214 | 50 |

D6 对两条 history 的可用/不可用 case 为 `2/0`，validation reasons 为空；actual
execution required/available/unavailable case 为 `2/2/0`。因此 D3 计划从 history
到 command 再到 actual metrics 的运行级 P0 可追溯链已关闭。M5N2 的 plan version、
成员和 owner churn 均为 0，但 feedback churn 50 仍是单 seed P1 标定信号，不是
P1 稳定性通过。物理结果为 pair `2/3`、target `2/2`、coalition `0/1`；T001 第二
primary 最近约 11.02 m，未进入 5 m。目标级 `2/2` 不能写成联盟完成。第二 primary
物理闭环和同配置多 seed 复验继续保持 P1。

## 2026-07-15 M5N2 20-Case 计划历史复核

main 在 M5N2 baseline 与 `candidate_soft_prediction_trend_coast` 各完成 10 seeds 后
终止了后续多 seed suite。D3 对这 20 个 case 的
`main_episode_bus/d3_plan_history.json` 做了只读复核：共 `3725` 个 planning tick，
其中 baseline `1869`、candidate `1856`；20/20 个文件的 `record_count` 与实际数组长度
一致，全部记录均为 `d3_plan_history_record_v1`、`assignment_plan_v2`。

每个 tick 都报告动态规模 `resource_count=5`、`target_count=2`，并保持 T001 的
`2 primary + 1 standby reserve` 和 T002 的 `1 primary`，总计 4 个 assignment。
20 个 case 各自只出现一个 `plan_id/version=1`；逐 tick 计划身份、owner 和实际成员
roster 转换均为 0，stale reject 与 rollback 也均为 0。`3555` 条
`membership_change_records` 是候选换员评估，不是实际 churn：其中 `3524` 条由成员
迟滞保持，`31` 条虽通过成员收益/驻留条件，但又由全局迟滞保持，最终未改变 current
plan。由此，canonical history 的写盘和 D3 计划/成员/churn 可用性在本批已闭合，
不再是 `unavailable`。

跨 case 不能写死“第二 primary”的资源编号。19 个 case 的 T001 primary 为
`INT-02/INT-03`，1 个 candidate seed 的 primary 为 `INT-01/INT-02`；D3 文档只按
`target_id + member_role + current plan identity` 统计。系统物理结果为 pair
`12/60`、canonical target `12/40`、coalition `0/20`，第二 primary `0/20` 进入 5 m，
20 个第二 primary 的 `stop_reason` 均为 `collision_stop`。这些结果保留为跨模块 P1：
D3 history 未记录碰撞对象，不能把物理失败归因于分配器；candidate 的配对非退化
判据失败也不等于 D3 算法退化，因为两组的 D3 执行身份和成员均保持稳定。

术语必须分开：`canonical target success` 是 D6 对两个目标的标准目标级统计；
`cooperative target diagnosis` 专指 T001 两个 active primary 与 coalition 的诊断，
不能用前者替代联盟完成。TERM 生效前额外完成的 `png_ttc_2v2_seed001` 不纳入上述
M5N2 聚合；其余 tuned case 未执行，dropout case 数为 0，缺失结果保持
`unavailable`。

本次 D3 证据同步的验收门限是 20/20 history 可读、record count 无缺失、actual
plan/member/owner churn 可计算，且模块测试零失败；结果满足。物理验收门限仍为每个
active primary 进入 5 m，第二 primary 与 coalition 未满足。D3 全量测试为
`157 passed, 1 skipped`，唯一 skip 是 optional OR-Tools installed-only case。

## Scalable 3D Rule And Learning-Assist Path (2026-07-20)

`PlannerConfig.scalable_3d(...)` is an opt-in profile around the existing rule
planner. `TargetTrack` and `ResourceState` accept NED position/velocity,
position covariance, region identifiers, and resource speed/range fields. The
rule cost adds analytic constant-speed 3D intercept time/range, normalized NED
covariance, and region cost. Unreachable edges, exhausted assignment capacity,
declared friendly conflicts, and incompatible regions are hard-masked.

Candidate generation first applies the region/reachability gates and then
retains a deterministic per-target top-k. The effective k is never below the
target's `required_resource_count`, and still-feasible members of the current
published plan are retained so sparsification alone does not force churn. The
solver input remains a deterministic Hungarian/demand-slot matrix with pruned
edges set to the infeasible penalty. For sparse profiles, plan evidence stores
candidate-edge records and reject counts rather than a dense 40,000-edge audit
bundle.

The optional learning interface is `LearningCostAssistant`. It runs one shared
PyTorch MLP over a variable-length candidate-edge feature batch and supports
`shadow` and `assist` modes. Assist mode uses exactly:

```text
C_final = C_rule + alpha * tanh(delta_C)
```

The policy cannot emit assignments or a dense target-by-resource action vector;
Hungarian/demand-slot solving, all-or-none coalition admission, capacity, friend
conflict, and version checks remain deterministic. A stale version is rejected
by `AssignmentPlanner`; standalone residual inference masks a version mismatch.
Model timeout, low confidence, OOD features, invalid output, or model exception
returns the unchanged `C_rule`. `behavior_clone_warmup(...)` is a minimal native
PyTorch supervised warm-up interface, not PPO training or acceptance evidence.

Deterministic validation on 2026-07-20 added 13 tests: 3-target/5-resource,
5-target/3-resource, one 200v200 fixture, sparse high-threat M-to-N, 3D cost,
mask/fallback/version cases, and one 32-edge synthetic behavior-cloning batch.
The 200v200 sample assigned 200/200 with 800 candidate edges (2% density) and
800 shared-edge policy actions; one local invocation took 0.621 s. This is a
single functional timing sample, not a real-time benchmark. The full D3 suite
is `170 passed, 1 skipped`, with zero failures as the acceptance threshold and
only the optional OR-Tools installed-only test skipped.

Remaining learning gaps are real D2/D3 trajectory datasets, train/validation
splits, persisted checkpoints, calibrated OOD/confidence thresholds, bounded
preemptive inference, shadow multi-seed non-degradation, and any large-scale PPO
study. `gymnasium` and `stable_baselines3` are absent and are not required by
this implementation. The analytic reachability baseline does not replace D7
dynamics, obstacle/path planning, regional quota policy, or AirSim physical
validation.

## 2026-07-20 200×200 成本构造与区域计划合同

### 稀疏成本构造

此前的 top-k 只压缩了求解和证据输出，规则成本仍先对全部 `N×M` 资源目标对执行
Python 几何计算，并为随后被剪枝的边构造完整字典。同区域 200 resource × 200 target、
每目标 32 条候选边时，实际仍执行 40,000 次边成本和 80,000 次截获量计算。

`PlannerConfig.scalable_3d()` 现默认启用 `enable_vectorized_sparse_costs`。核心三维
位置、速度、协方差、资源状态、区域许可、截获时间和距离由 NumPy 批量计算；规则排序
仍按“成本、resource_id”确定性排序。最终只为 6,400 条候选边生成完整 breakdown，
剪枝边共享拒绝模板。带资源目标字典覆盖或复杂时间窗的输入继续走旧参考路径，保持既有
约束优先级和解释字段。学习残差、有界修正、规则回退和硬门控没有改变。

SciPy `linear_sum_assignment` 仍是默认确定性求解器。候选图不连通时，求解器按二部图
连通分量构造局部矩阵并分别运行 Hungarian；无候选目标直接按未分配成本处理。该分解
不改变全局最优值，因为分量之间没有共享资源边。

2026-07-20 同一进程、同一 200×200 输入、top-32、各重复 5 次的 D3 独立基准如下。
结果保存在 `results/scalable_3d_assignment_benchmark_20260720.json`。

| 路径 | 中位耗时 | 完整边 | 候选边 | Python 全边成本调用 | 分配数 |
|---|---:|---:|---:|---:|---:|
| 旧参考路径 | 1904.261 ms | 40,000 | 6,400 | 40,000 | 200 |
| 向量化稀疏路径 | 85.367 ms | 40,000 | 6,400 | 0 | 200 |

中位加速为 22.307 倍。20×23 逐边语义对照中，矩阵、候选掩码和拒绝原因一致，候选
breakdown 的浮点差在 `1e-11` 容差内。该数据是 D3 独立确定性基准，不代表 D1-D7
全栈实时性能，也不替代多 seed 或 AirSim 物理验收。

### 区域计划

新增 `RegionalAuthorityInput`、`RegionalAuthorityGrant` 和
`RegionalCoalitionCommitEvidence`。D3 不判断是否降级，只接受 D4 已裁决的区域
owner 和成员结果，生成一个普通、可版本校验的 `AssignmentPlan`。同一计划可携带
多个 secondary owner，也可携带 fully distributed peer owner；每条 assignment
记录 region、owner、epoch、lease 和 commit 状态。

发布前必须满足：D4 输入引用当前 `plan_id/version`；区域 epoch 不回退；lease 在
发布时间后有效；每个资源只属于一个目标；成员边仍在 D3 规则候选中；M-to-N 需求
完整。`k=1` 由 D4 已裁决的区域 ownership、epoch、lease、execution_allowed 和唯一
资源成员授权，不要求原子联盟提交；若 D4 同时提供 summary，只接受
`commit_required=False`、`single_member_authorized`、非 atomic、成员授权完整且租约
有效的证据。`k>1` 继续强制 committed、atomic committed、完整 ACK、成员一致且租约
有效。任一条件失败均抛出带 reason 的 `RegionalPlanAuthorityError`，不发布可执行
计划。计划执行变化继续严格递增版本，旧 previous plan 仍由 `StalePlanError` 拒绝。

本轮 D3 全量验收为 `193 passed, 1 skipped`，唯一 skip 是 optional OR-Tools。
区域合同已完成模块级测试，main 尚未把 D4 `RegionalFailoverDecision` 转换并接入
`plan_regional_authority()`；因此多 owner secondary 和 distributed 运行时闭环仍是
待集成，不得写成完整系统已通过。

## 2026-07-20 故障代际 Fence

`AssignmentPlanner.advance_authority_generation(...)` 用于中心或二级节点故障后、D4
重新裁决区域 owner 之前推进 D3 计划代际。调用方必须传入当前已发布计划、单调时间、
精确 `expected_previous_version` 和非空 `fence_reason`。接口复制原计划的 assignment
成员、coalition identity/version、目标身份、owner 和授权状态，只生成新的
`plan_id`、严格递增 `version`，并由 D3 正常发布登记。assignment 中仅同步新的计划
上下文版本；资源-目标绑定不变。

Fence metadata 使用 `d3_fault_authority_generation_fence_v1`，记录原因、来源计划、
fence generation、非重分配和非执行授权。`fault_authority_fence_requires_d4_gate=True`
表示该计划不能自行授权 D7；main/D7 仍必须执行 D4 的 hold/continue 结果。普通相同
执行签名的新身份继续被 `publish_plan()` 拒绝，只有来源、版本和安全标记完整的 fence
可推进。错误 expected version、旧来源、重复 fence 版本和篡改 coalition 均 fail
closed。

2026-07-20 新增 5 个专项测试。D3 全量共 199 项，结果为
`198 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。该结果关闭 D3-owned fence
接口缺口；main 尚需在 50v50 中心故障路径调用该接口，再把新 generation 交给 D4
区域裁决。

## 2026-07-20 可复现 BC/PPO/Shadow 研究管线

本模块现提供完整但默认关闭的学习研究路径。`AssignmentPlanner` 默认仍不构造或加载
模型；规则 Hungarian/`hungarian_demand_slots`、候选 mask、联盟准入、迟滞、计划版本
和 stale 拒绝继续拥有最终决定权。模型只处理当前稀疏候选边，不输出 assignment、
target/resource index、联盟成员、owner、plan version 或 D7 控制量。

### 数据与模型合同

- `learning_data.py` 当前合同为 `d3_learning_dataset_v2`，split policy 为
  `d3_numeric_seed_atomic_split_v2`。采集帧显式标记 `unassigned`；finalize 取得完整唯一
  数值 seed catalog 后，按 seed 数量确定 train/validation/test，scenario version、规模和
  episode 不参与 seed 身份。同一数值 seed 的所有 scenario/scale/episode/frame 必须原子
  进入一个 split，三个数值 seed 集合两两不交。少于 3 个唯一 seed 或 test 少于声明的
  unseen 数时不写 manifest；正式默认声明 20，synthetic smoke 必须显式降为 1。
- v2 manifest 固化唯一 seed 数、逐 split seed/episode/frame 数、split 参数、split hash 和
  canonical `frames.jsonl` SHA256。loader 重算分配与统计并校验完整文件 SHA；v1 dataset、
  v1 scenario/seed split、冲突预分配和任何篡改均明确拒绝，不做静默迁移。
- `write_learning_dataset()` 用临时 SQLite 只保存排序键和 payload 偏移，以磁盘 JSONL
  sidecar 保存单次 canonical 编码结果，再按稳定键流式输出；
  `iter_learning_frame_records()` 可逐行消费 staged JSONL。每帧仍只保存匿名 ordinal
  target/resource 摘要、`E x 12` 候选边特征、mask、规则成本/选边、版本、反馈/迟滞和
  reward 分量，不保存原始 ID、truth actor 或上游 metadata。
- `learning_bundle.py` 保留 `d3_learning_model_bundle_v2` 兼容加载，并对正式开发模型使用
  `d3_learning_model_bundle_v3`。v3 在 feature/policy、split hash、归一化、guardrail、
  dataset/split schema 之外增加 provenance 与 admission。v1 bundle 稳定回退为
  `model_bundle_schema_unsupported`；缺失、损坏、SHA、特征或合同不匹配均返回逐元素相同
  的 `C_rule`，权重只用 `torch.load(..., weights_only=True)`。
- shadow 可加载未晋级 bundle。assist 必须显式调用 `load_model_bundle(...,
  mode="assist")`，且 promotion manifest 同时满足 recommended、至少 20 个未见 test
  seed、安全/成本非退化和零 fallback；仅写一个 true 布尔值不能绕过门控。

### BC、PPO 与 paired shadow

`SharedEdgeActorCriticPolicy` 共享同一 edge encoder，支持任意当前候选数 `E`。每边
actor 输出 bounded residual；value 使用 masked mean-pooled frame context；hold/replan
是按 `advice_allowed` 低频开放的建议。BC 按 frame mini-batch 跨多个 episode 学习规则
选边、规则 residual teacher 和 hold/replan，并输出 train/validation loss 与完整 seed
指标。原生 PyTorch PPO 使用 clipped objective、GAE、value loss、entropy 和 gradient
clip；每次动作经确定性 mask 与 Hungarian demand-slot solver 后，才按规则成本、高威胁
覆盖、未满足槽、churn、过期和安全拒绝重算离线 reward。

`shadow_evaluation.py` 在相同 scenario/seed/frame 上复制同一规则矩阵，分别求解 rule
和 bounded proposal，报告 assignment cost、高威胁 unmet、churn、duplicate/hard
violation、推理 P50/P95 和 fallback reason。unseen 与 whole-seed 指标按全局数值 seed
跨 scenario 聚合，输入必须先通过完整三分合同；shadow 从不改写规则矩阵，也不发布计划。

四个 CLI 子命令为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli generate-data --output /tmp/d3_data
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-bc --dataset /tmp/d3_data --bundle /tmp/d3_bc_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-ppo --dataset /tmp/d3_data --input-bundle /tmp/d3_bc_bundle --bundle /tmp/d3_ppo_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli shadow-eval --dataset /tmp/d3_data --bundle /tmp/d3_ppo_bundle --output /tmp/d3_shadow.json
```

### 当前证据边界

此前 30-seed synthetic smoke 的 `23/1/6` split、loss 和 shadow 时延来自 v1
scenario/seed policy，只保留为历史开发记录；v2 loader 与 bundle loader 均拒绝把该产物
解释为当前合同。该段记录的是正式训练前的软件合同阶段；最新正式 loss、成本和时延见
本文末尾的“正式数据行为克隆开发模型”。

软件合同回归覆盖同一数值 seed 在 2v2/5v5 风格 scenario、多个规模和 episode 中复用、
输入逆序确定性、三 split 零交集、唯一 seed/unseen 数不足、split/frame/hash 篡改、v1
dataset/bundle 拒绝、训练和 shadow 的全局 seed 计数。D3 全量收集 244 项，结果为
`243 passed, 1 skipped`；唯一 skip 是 optional OR-Tools installed-only case。

200v200 dense fixture 单帧含 40,000 candidate edge，canonical JSON 约 5,854,691 bytes；
NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。当前 scalable main finalize 已把
`iter_learning_frame_records(staging_path)` 直接传给 writer，不再在调用侧执行
`read_text().splitlines()` 和完整 tuple 构造。正式 900-episode 数据容量、故障/密集场景
最坏值和长期磁盘预算仍需由 main 在 clean tree 上验收。

本批没有提交正式权重，没有真实 D2/D3 轨迹训练，没有至少 20 个未见真实/高保真 seed，
也没有 CPU/GPU deadline 分布、AirSim 物理收益或可抢占 timeout 证据。当前结论仅为
管线实现和合成 smoke；规则 Hungarian 继续是唯一默认路径。

本次结果是软件数据合同证据，不是模型性能、AirSim 物理收益或 assist promotion 证据。

## 2026-07-20 单帧只读规划证据

`AssignmentPlanner.latest_planning_evidence` 现返回
`PlanningFrameEvidence`（schema `d3_planning_frame_evidence_v1`）。planner 只保留最近
一次规划尝试：每次 `plan()`、`plan_incremental()` 或
`plan_regional_authority()` 开始时先替换旧帧，成功后保存与该次输入一致的 rule
`CostMatrixResult`、实际送入 solver 的 effective `CostMatrixResult`、计划
`plan_id/version`、规划时间、前序版本，以及构造 `LearningFrameRecord` 所需的
tracks/resources/plan 安全副本。新 episode 仍按既有合同创建新 planner；新实例初始
状态为 `available=False, reason="no_planning_frame"`。

证据明确区分四种 learning 状态：`rule_only`、`shadow_proposal`、
`assist_effective` 和 `rule_fallback`。shadow 的 proposal 是独立只读矩阵，effective
矩阵仍逐元素等于 rule；assist 只把有界 residual 后矩阵标为 effective；timeout、低
置信、OOD、bundle/version 等 fallback 必须保持 effective 与 rule 逐元素相同并给出
`fallback_reason`。solver 名称单独记录，因此 SciPy Hungarian 与 `fallback_dp` 也可
审计，默认 `learning_assistant=None` 和 Hungarian 行为未改变。

该接口只存在于 planner 本地对象，不写入 `AssignmentPlan.metadata`，不定义线上 DTO，
也不上 D4/D7 总线。快照把输入 ID 重映射为 `target_0000/resource_0000`，剥离上游
metadata、node/actor/object/truth alias；NumPy 数据来自独立不可写 buffer，嵌套 mapping
也只读。held、unchanged、forced-replan ack 和有效 regional authority 均保存当前输入
帧；stale/区域拒绝、无矩阵 authority fence、证据不一致或无匹配成本帧的外部 publish
只返回 `available=False` 和明确 reason，不回退到上一帧。

main 可直接调用：

```python
record = build_latest_learning_frame_record(
    planner,
    scenario_version=scenario_version,
    seed=seed,
    episode=episode,
    frame_index=frame_index,
)
```

helper 使用证据中的 timestamp 和 rule matrix，继续输出匿名 ordinal token；调用方不再
调用私有 `_build_search_matrix()`，也不重复构造可能与真实规划不一致的成本矩阵。
2026-07-20 新增 11 个专项测试，覆盖首帧、held/unchanged/forced replan、shadow、
assist、learning/solver fallback、regional 成功与拒绝、失败清旧帧、外部修改隔离及
1x3、3x2、7x4 roster。D3 全量共收集 226 项，结果为
`225 passed, 1 skipped`，零失败达到门限；skip 仍是未安装 optional OR-Tools 的
installed-only case。main 尚未用真实 AirSim episode 导出整 seed 数据，因此这里只
关闭 D3-owned recorder 接口缺口，不构成真实数据、shadow non-degradation 或 assist
晋级证据。

## 2026-07-20 上一轮区域资源提示约束下一轮候选图

普通入口现支持可选关键字 `regional_planning_hint`。D3 自有且冻结的
`RegionalPlanningHint`、`RegionalPlanningConstraint` 和
`RegionalTransferAllowance` 使用 schema `d3_regional_planning_hint_v1`；调用方也可
传入中性 mapping，由严格 `from_mapping()` 解析。该解析不导入 D4 类型，拒绝未知字段
以及 truth/actor/object/target/resource 身份字段。提示携带 advisory identity/version、
created/expiry、精确 source plan、逐区域 owner/epoch/lease、projected、quota delta、
reserve ratio、hold/request-replan 和邻区 transfer allowance。

提示只在显式提供时进入普通规划。D3 要求 source `plan_id/version` 与
`previous_plan` 完全一致，当前 timestamp 同时落在提示与全部区域 lease 内，当前 target/
resource 区域集合可解释，projected quota 总和守恒且与 transfer 净额一致。每个源区按
当前资源数、上一计划全部 assignment/coalition 成员和 post-quota reserve floor 计算
可转移容量；不满足时不把 transfer 当成 0，而是写入明确 fallback reason 后重新执行
原规则路径。

合法提示在规则矩阵和 switch penalty 之后、learning residual 之前约束候选 mask。同区
边保持原规则门控；跨区只开放给该 route 固定大小且互斥的未承诺资源池，因此普通
Hungarian 的资源唯一性直接形成 transfer count 上限。M-to-N role/wave slot 继续复制同一
mask，D5 hard edge、能力/可达性、学习有界代价、迟滞和版本发布均不被绕过。最终
`AssignmentPlan.metadata` 记录 available/considered/applied/rejected、advisory/source
identity、fallback reason、逐 route allowed/actual count 和实际跨区资源总数，供 D6
审计。无提示时规则矩阵、learning 调用和 Hungarian 路径不变。

2026-07-20 新增 14 个确定性 pytest case，覆盖严格解析、无提示等价、1-to-1 实际跨区
选边、8 类非法/过时回退、commit/reserve 保护、M-to-N 两资源 transfer 上限，以及 D5
hard edge 与 learning assist 共存。seed 不适用于该模块 fixture；接受门限为全量零失败。
D3 共收集 240 项，结果为 `239 passed, 1 skipped`，skip 是既有 optional OR-Tools
installed-only case。本批没有运行 AirSim、正式多 seed 性能或物理拦截；main 仍需把
D4 `RegionResourceRecommendation` 显式映射为 D3 DTO，并在 reset-separated episode
中验证时间基准、owner/epoch/lease 和 D6 指标。

## 2026-07-20 Learning 安全复核补正

本轮对可选 BC/PPO/shadow/assist 路径做 fail-closed 复核，不改变默认 Hungarian、
`hungarian_demand_slots`、联盟准入、计划版本或 D7 授权链：

- BC 训练入口只接受 `train`/`validation`，PPO 只接受 `train`；任一训练 API 收到
  `test` frame 都拒绝。CLI 对完整 dataset 的读取只用于内容、哈希和三分合同校验，
  test frame 不进入训练 batch、normalization 或训练期 whole-seed metric；test 仅由显式
  `shadow-eval --split test` 入口消费。
- `LearningFrameRecord.from_dict()` 对 v2 使用完整字段 allow-list；普通扩展必须升级
  schema。解析前递归拒绝 truth/actor/identity、实体 ID、UUID 和 vehicle-name 类字段，
  同时保留已知匿名 ordinal、数值/布尔字段及语义性 hard-reject reason 的兼容策略。
- `candidate_mask` 是候选提示，不是授权。候选索引、assistant 返回 mask 和 solver 消费
  mask 都始终与 `reject_reasons is None` 求交，shape 不一致失败关闭，不能重开 D5、
  可达性、容量或友方冲突 hard edge。
- bundle v2 同时绑定 split hash、canonical `frames.jsonl` SHA256 和
  `state_dict.pt` SHA256。assist 不允许关闭 promotion gate；promotion evidence 必须是
  `d3_shadow_promotion_evidence_v1`、正式 `test` split、`evidence_eligible=true`、
  `paired_rule_residual_shadow`、`rule_cost_matrix_v1`，且三项摘要与 bundle 完全一致。
  布尔和计数字段采用严格类型校验，错配或伪装均回退 `C_rule`。
- residual proposal 仍按 `C_final=C_rule+alpha*tanh(delta_C)` 产生候选方案，但 rule 与
  proposal assignment 的非退化指标都按同一个最终 `C_rule + unassigned_costs` 基准
  重新评分，禁止比较不同矩阵各自的 solver objective。学习输出始终只是受约束提案，
  不能直接授权 assignment、coalition 或 D7 执行。

2026-07-20 全量收集 252 项，结果为 `251 passed, 1 skipped`，接受门限为零失败；唯一
skip 是未安装 optional OR-Tools 的 installed-only benchmark。新增负例覆盖 test-seed
训练拒绝、训练指标隔离、递归 identity/未知字段拒绝、hard-reject mask 求交、frame SHA/
promotion 证据错配、validation/非 eligible/bypass 拒绝和共同规则代价重评分。本轮未训练
或提交正式权重，未运行 AirSim，也没有至少 20 个未见真实/高保真 test seed、正式
promotion、模型收益或物理闭环结论。

## 2026-07-20 200×200 学习帧导出性能复核

本轮只优化 D3 学习帧构造、canonical JSONL 读写和数据集 finalization，不改变
Hungarian、学习残差、硬拒绝掩码、`plan_version`、truth isolation、dataset schema 或
任何输出字段。候选特征构造按目标缓存一次 `effective_demand`；学习帧的硬拒绝计数复用
同一 action-mask 扫描结果。JSONL identity 检查改为迭代遍历容器，避免对密集数值数组
中的每个标量递归调用。

finalization 仍先验证每个 `LearningFrameRecord` 的当前数组、掩码、匿名实体和身份字段，
随后只做一次 canonical 编码。临时 SQLite 保存排序键、payload offset 和 size；payload
写入临时 JSONL。最终排序阶段只读取对应字节并替换唯一受控的 `split=unassigned`
占位符，不再执行第二轮 `json.loads -> from_dict -> replace -> to_dict -> json.dumps`。
正序、逆序输入和旧重编码语义输出逐字节相同，frame SHA256 与 manifest 规则不变。

同机开发微基准使用 200 targets、200 resources、top-32、每帧 6,400 candidate edges、
6 帧。墙钟只作归因证据，不作为单元测试门限。

| 阶段 | 修改前 | 修改后 | 变化 |
|---|---:|---:|---:|
| 单帧 frame build 中位数 | 48.19 ms | 22.99 ms | 2.10× |
| 单帧 JSON decode + validate 中位数 | 95.92 ms | 56.09 ms | 1.71× |
| 6 帧 dataset finalize 中位数 | 910.20 ms | 243.65 ms | 3.74× |
| 匹配 cProfile/Tracemalloc 峰值 | 14,575,699 B | 12,725,690 B | -12.69% |

当前 top-32 帧约 2.20 MB；九场景 D3 正式帧证据总计约 27.86 MB，数据内容和存储量按
要求未压缩或删减。模块局部测得的六帧构造、首次编码、逐行读取和 finalization 合计约
0.87 s，不能把 main 记录的 D3/D4/D5 总耗时全部归因于 D3。

main 随后在干净工作树上复跑 nominal 200v200、seed 930/931/932、每个 episode 2 s。
优化后产物由 commit `4052d9411363c39d52100c0e3a4f60ee88443cab` 生成，清单记录
`repository_dirty=false`。总生成耗时由 467.8007 s 降至 262.2866 s，artifact staging
由 225.9243 s 降至 126.4682 s，总 finalization 由 116.5624 s 降至 7.7377 s；episode
run 为 125.2205 s 与 127.9871 s，基本未变。这里的总 finalization 同时包含 D3、D4、D5，
不能作为 D3 单模块耗时。

分项记录给出的 D3 stage 分别为 0.0917 s、0.1129 s、0.0999 s。D3 数据集共 6 帧，
train/validation/test 各 2 帧，正常最终化，在线真值使用为 0。该证据关闭 D3-owned
重复编码和最终化热点及其跨模块归因问题，但不是正式 900-episode 生成、模型训练、
至少 20 个未见 seed 评估或 AirSim 结果。

可复现命令：

```bash
python3 research_modules/d3_assignment_planner/simulations/run_learning_export_profile.py \
  --count 200 --max-candidate-edges 32 --frame-count 6 --repeat 5
```

结果文件为 `results/scalable_3d_learning_export_profile_20260720.json` 和配对比较 JSON。
D3 全量回归收集 255 项，结果 `254 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。
剩余 CPU 热点是标准库 JSON 对 NumPy 数组执行 `tolist()` 和 canonical `json.dumps()`。
继续减少该部分需要引入新编码依赖或改变持久化格式，因此不在本次无 schema 变化任务中
处理。

## 2026-07-20 正式数据行为克隆开发模型

正式 D3 数据位于三维规模化仿真学习数据目录，只读审计通过。清单包含 900 episode、
1604 帧和 100 个数值 seed，train/validation/internal-test 为 962/320/322 帧，对应
60/20/20 个 seed。canonical frame SHA256 为
`6761d35d6b48639a5eb4f3306f7b3f12ca72352a1028296a0c39a4b90fdb59a2`，split hash 为
`679a9051e8637fad38d935eb685f09dd8abc8d43043a28264dab64b077ac70a2`。外部保留 seed
1000-1019 与当前数据交集为空，也未在本轮评估中消费。

训练使用固定 seed `20260720`、12 epoch、隐藏层 64、Adam 学习率 0.001、8 帧小批次和
正类权重上限 16。正类加权只处理规则已选边约 3.2% 的类别不平衡；学习输出仍是
`C_final=C_rule+alpha*tanh(delta_C)`，`alpha=0.25`。不可达边、硬拒绝、需求槽、容量、
版本、迟滞和 Hungarian 求解不进入学习动作空间。训练损失由 1.083713 降至 0.468781，
验证损失为 0.469243。内部 test 的边排序一致性为 0.8031，计划完全一致率为 0.6770，
平均规则成本差为 +0.022345，相对差约 +0.0091%；需求满足率与 rule-only 同为 0.975689，
重复分配和硬门控违规均为 0，平均重分配 churn 均为 70.1149。

内部 test 模型推理 P50/P95/P99 为 0.506/2.554/2.809 ms。按 5/20/50/100/200 名义规模，
推理 P95 分别为 0.247/0.433/0.860/1.434/2.793 ms。当前 OOD 规则按“单帧任一候选边任一
特征超过 6 个标准差”判定，内部 test 有 163/322 帧回退规则路径。该现象和轻微成本退化
说明模型不能晋级 assist，后续需在外部保留 seed 上重新标定 OOD、confidence 和 deadline。

新 bundle schema 为 `d3_learning_model_bundle_v3`，增加训练日期、数据 manifest SHA、
训练源码 SHA、Git 基线提交、工作树状态和显式 admission。提交 `39b097e...` 是正式数据
生成与训练基线；训练时存在 D3 模块改动，精确源码由 training-source SHA256 绑定。当前
状态固定为 `development/shadow-only`；即使
有人写入 recommended promotion，loader 仍返回 `bundle_shadow_only`。权重 SHA256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。权重和 bundle 位于
ignored `outputs/formal_bc_development_20260720/bundle`，不进入普通 Git 提交；tracked
`results/formal_bc_development_20260720` 只保留审计、配置、命令、指标报告和定位说明。
当前环境没有 Git LFS，长期权重需由 main 转存到 Git LFS 可用环境或独立制品存储。

复现入口为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 \
  research_modules/d3_assignment_planner/simulations/run_formal_bc_development.py \
  --dataset research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d3_assignment \
  --output research_modules/d3_assignment_planner/results/formal_bc_development_20260720 \
  --bundle-output research_modules/d3_assignment_planner/outputs/formal_bc_development_20260720/bundle \
  --repository-git-commit 39b097e72487567ac915c2297eaa27eed49ef76b
```

本轮没有启动 PPO，没有更改 AssignmentPlan 版本、`global_track_id` 或 D7 binding。内部
test 是开发集内的独立切分，不是最终 20 个保留 seed 准入。main 下一步必须使用同一冻结
权重运行 seed 1000-1019，并由 D6 独立汇总安全非退化、成本、需求满足、抖动、回退和时延。
新增正式审计、v3 bundle、加权 BC 与开发评估测试后，D3 全量收集 258 项，结果为
`257 passed, 1 skipped`；唯一 skip 仍是 optional OR-Tools installed-only case。
