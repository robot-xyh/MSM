# AirSim Integration Plan For D3 Assignment Planner

## Identity Commitment Field

Main should join D2's current commitment publication by `global_track_id` and
set `TargetTrack.identity_commitment_state` before calling D3. The dry-run
adapter accepts:

```text
record.identity_commitment_state
record.identity_commitment.identity_commitment_state
record.metadata.identity_commitment_state
```

When all three are missing, the adapter emits
`identity_commitment_missing`; unsupported values become
`identity_commitment_unknown`. Both states reject every assignment edge. An
AirSim/scalable episode must not infer commitment from `simGetDetections`
actor identity, offline labels, or a known target count.

Logs should retain the D2 source publication, D3 admitted/rejected counts and
reasons, and previous/new plan identity. Main owns the hold/replan decision and
must keep control held until it adopts the newer plan. If a bound target becomes
non-committed, all ordinary and coalition bindings for that target must be zero.
This contract passed 12 focused tests and the full `450 passed, 1 skipped`
suite on 2026-07-23.

The main scalable 3D runtime join has also been exercised on clean commit
`7e15dac9cdaf6743999dfe045a70676fd31a17d6`, with 200 resources, 200 targets,
2.2 s, and seed 1100. In both `hold_only` and `hold_plus_centroid`, plan v1
contained 193 assignments at `t=0.75`. Eleven previously assigned targets
entered ambiguity hold at `t=1.0`; D3 forced a hysteresis-bypassed replan to
v2/186, and none of those targets appeared in D3, D5 active vision, D5 terminal
binding, or D7 guidance after that time. Plan v3 retained 186 assignments at
`t=2.0`.

This was a point-mass scalable-runtime episode, not an AirSim Blocks episode.
It did not inject a stale plan. AirSim/module regression remains responsible
for active stale-input rejection. The main diagnostic binding-hold count of 13
must not be reported as the D3 rejected-target count; D3 rejected 11 targets in
the v2 decision. The equal two-arm result validates the safety gate and does
not establish D1/D2 algorithm improvement.

## Boundary

This plan is limited to offline AirSim playback or software-in-the-loop evaluation that produces human-review candidate assignment plans. It does not include real flight control, hardware drivers, real fire-control parameters, damage logic, autonomous disposition, or authorization bypasses.

## Integration Goal

Connect AirSim-derived simulated observations to the D3 planner interface:

```python
AssignmentPlanner.plan(
    tracks,
    resources,
    timestamp,
    previous_plan,
)
```

The output remains an abstract `AssignmentPlan`. Its default authorization state is `human_authorization_state="required"`, while AirSim validation may set `PlannerConfig.human_authorization_state` to a record-only state such as `"recorded"` for contract testing. D3 does not interpret that field as autonomous disposition authority.

One `AssignmentPlanner` instance is scoped to one AirSim episode. The first planning tick may omit `previous_plan`; every later tick must pass the exact active plan and should pass its version as `expected_previous_version`. A missing or stale predecessor is rejected with `StalePlanError`, and the runtime must retain the active plan rather than treating the rejected call as a new version-1 episode. Create a new planner instance after an episode reset.

## Proposed Data Flow

```text
AirSim log or live simulation tick
  -> observation adapter
  -> abstract TargetTrack list
  -> abstract ResourceState list
  -> AssignmentPlanner
  -> candidate AssignmentPlan
  -> logger / dashboard / human review queue
```

No planner output is sent directly to vehicle control, hardware control, or autonomous action.

## Adapter Responsibilities

Target adapter:

- Assign stable `track_id` values from the simulation track source.
- Normalize covariance quality into `TargetTrack.covariance` in `[0, 1]`.
- Normalize scenario priority into `TargetTrack.threat_score` in `[0, 1]`.
- Convert timing or geometry quality into abstract `window_cost` in `[0, 1]`.
- Compute pair-level `fov_difficulty_by_resource` in `[0, 1]` from simulated visibility or observation geometry.
- Compute pair-level `conflict_risk_by_resource` in `[0, 1]` from abstract resource contention or route overlap proxies.
- Mark `assignable=False` only for tracks that should not enter candidate assignment research.

Resource adapter:

- Assign stable `resource_id` values.
- Map simulated availability into `status`: `available`, `degraded`, `busy`, or `unavailable`.
- Normalize health or readiness proxy into `health_score` in `[0, 1]`.
- Set `operator_hold=True` when a human or scenario script excludes a resource from candidate assignment.
- Provide `busy_until` only as abstract scheduling state.

## Offline Evaluation Modes

1. Log replay:
   - Read saved AirSim telemetry or perception logs.
   - Convert each timestamp into planner inputs.
   - Write `AssignmentPlan` outputs to JSONL/CSV for analysis.

2. Software-in-the-loop simulation:
   - Poll AirSim at a fixed rate such as 2 Hz.
   - Convert state to abstract planner inputs.
   - Display candidate plans and metrics.
   - Do not connect outputs to actuation.

3. Batch parameter sweep:
   - Replay the same AirSim scenario with different `delta`, `min_dwell`, and `CostWeights`.
   - Include `reassignment_switch_penalty` and verify that solver/evidence costs remain single-charged.
   - Compare reassignment count, total accepted-plan cost, unassigned high-priority ratio, and runtime.

## Message Schema Sketch

Input target record:

```json
{
  "track_id": "T01",
  "timestamp": 12.5,
  "threat_score": 0.82,
  "covariance": 0.34,
  "window_cost": 0.41,
  "assignable": true,
  "pair_terms": {
    "R01": {"fov": 0.22, "conflict": 0.10, "feasible": true}
  }
}
```

Input resource record:

```json
{
  "resource_id": "R01",
  "timestamp": 12.5,
  "status": "available",
  "health_score": 0.91,
  "busy_until": 0.0,
  "operator_hold": false
}
```

Output candidate plan record:

```json
{
  "plan_id": "d3-plan-example",
  "version": 42,
  "created_at": 12.5,
  "human_authorization_state": "recorded",
  "metadata": {
    "configured_human_authorization_state": "recorded",
    "effective_human_authorization_state": "recorded",
    "active_plan_owner": "center",
    "replan_reason": "request_center_replan",
    "supersedes_plan_id": "d3-plan-previous",
    "supersedes_plan_version": 41
  },
  "decision_state": "held_by_hysteresis",
  "assignments": [
    {"target_id": "T01", "resource_id": "R03", "cost": 1.73}
  ],
  "unassigned_target_ids": ["T04"],
  "total_cost": 14.2
}
```

## Validation Gates

- Unit tests must pass before AirSim adapter tests.
- Adapter tests should replay a short fixture and verify stable track/resource IDs, normalized ranges, and deterministic planner business output. Fresh planner instances intentionally create different UUID-based `plan_id` values; independent AirSim episodes must compare a validated, occurrence-normalized plan lineage rather than raw plan IDs.
- No output channel may be connected to vehicle control or hardware control.
- Every published candidate plan must preserve the configured `human_authorization_state`; the default remains `"required"`, while record-only AirSim gates may use `"recorded"`.
- Logs must include `decision_state`, version, total cost, and per-assignment cost breakdown.
- When main/D4 requests `request_center_replan`, the next D3 plan must increment version and main/runtime must log `replan_reason`, `supersedes_plan_id`, `supersedes_plan_version`, and `active_plan_owner="center"`.
- After every successful planning tick, main should call `plan_history_record_from_plan(plan, sequence_index=tick_sequence_index, timestamp=planning_timestamp_s, previous_plan=previous_plan, feedback_metadata=None if writeback is None else writeback.metadata).to_dict()` and persist one JSONL object. Ordering is lexicographic `[sequence_index, timestamp]`; plan version is not a tick-order substitute.

## Validation Status Through 2026-07-14

- The real 5v5 calibration completed 60 connected cases: seeds 1-10, secondary heights 50/200 m, and `no_degradation`, `degrade_to_secondary`, and `degrade_to_distributed` cases.
- The historical runtime path has not activated a secondary plan. All 20 requested secondary cases fell back conservatively to distributed operation; 15 of 1300 D4 decisions reached momentary `takeover_ready`, all stopped at `pending_secondary_plan`, and `secondary_plan_active=0`.
- D3 provides the strict activation contract. The current secondary and distributed commit positive cases passed, and missing ACK aborted fail-closed. Stale-center, lease/epoch, and recovery cases remain long-term main/D4 regression and calibration concerns, not open D3 P1 contract work.
- The deterministic 3v5, 5v3, target-arrival, resource-failure, demand-change, and incremental/full suite closes the D3 N/M interface contract. Real non-equal multi-seed replay remains parameter-tuning evidence rather than missing implementation.
- The current 2026-07-11 ComputerVision M-to-N validation used 5 resources, 2 targets, and 10 seeds. T001 achieved two-primary visual consensus with current-plan authorization in 8/10 seeds; seeds 7 and 27 remain regressions. Combined with incremental planning and role-aware primary preservation, the D3 P1 contract layer is closed.
- Real M5N2 SimpleFlight validation has now run. It used `2 primary + 1 standby reserve`, did not require simultaneous primary arrival, and completed 40 episodes: 10 baseline seeds plus 10 seeds for each of three candidates.
- Coalition completion was `0/10` for baseline, `5/10` for the best `20 m / 3 s / 40 deg` profile, and `2/10` and `1/10` for the other two profiles. The best profile did not meet the `8/10` acceptance gate, so cooperative physical closure remains open even though real AirSim execution is no longer pending.
- Plan version, stale-plan rejection, member-role contracts, and reserve standby safety remained in force. The reserve was not authorized as an active primary.
- D3 now classifies ordinary ambiguous/hold/reacquire and geometry/FOV/detection instability as pair-soft feedback. These events raise only the current edge cost and hold D7; they do not set resource-wide `operator_hold`. Friend overlap, verified friend, safety identity conflict, duplicate assignment/lock, explicit feasibility rejection, and genuinely unavailable resources remain fail-closed at their declared scope.
- The 2026-07-14 deterministic acceptance now totals `157 passed, 1 skipped`. The five newest tests add soft-feedback/round-trip stability, cumulative same-window budget, cross-window recovery, hard resource failure, missing plus membership hold, owner fail-closed, and history budget export. Earlier canonical-history and held-scope/lifecycle cases remain covered. The skip remains the optional OR-Tools installed-only case.
- D3 now publishes `d3_plan_history_record_v1` through `PlanningTickHistoryRecord` and `plan_history_record_from_plan(...)`. The whitelist payload contains one tick's plan/count/owner/lineage/cost state, ordered assignments and recoverable coalitions, hysteresis/membership records, feedback classifications/counts, and stale/rollback/replan audit reasons; online truth fields are excluded.
- P2 results remain isolated optional benchmarks and do not select or replace the default Hungarian/demand-slot path.

## Open P1 Calibration Work

- D3 canonical per-planning-tick schema/export is complete. Main still must call it and persist JSONL for each tick; no main/runtime file is changed by this D3 task.
- D6 can expand all 40 M5N2 cases, but the formal aggregate predates main persistence of canonical records. Membership/version churn is therefore still `unavailable` and must not be inferred or filled with zero; D6 consumption is outside this task.
- The former pair-hold-to-resource-hold promotion is a root-cause lead for churn, not proven causality for the 40-case outcomes. Causal attribution requires paired per-tick plan, feedback, classification, and hysteresis records.
- Calibrate D5 feedback weights and `delta`, `min_dwell`, and `reassignment_switch_penalty` from paired per-tick evidence.
- Run dynamic N/M multi-seed cases, including 3v5, 5v3, target arrival, resource loss, and demand changes.
- Do not add a simultaneous-arrival requirement to this P1 acceptance path.

## Future OR-Tools Path

The optional same-input comparator behind `MinCostFlowAssignmentSolver` is implemented and remains outside the default planner and requirements. Environments without OR-Tools report explicit unavailability and keep the core suite green. CP-SAT/MILP coalition references, resource capacities, group quotas, backup resources, multi-window networks, and predictive rolling remain isolated P2/P3 work; they must not replace the Hungarian/demand-slot default path without separate evidence.

## 2026-07-14 Seed 001 Integration Findings

The persisted M5N2 baseline seed 001 contains 349 D3 planning ticks and 45
published versions. Eight held ticks advanced identity because current-input
unassigned scope leaked into the held plan. D3 now preserves the previous
execution scope and exposes the candidate scope as audit-only metadata. The
acceptance criterion for the next main-owned replay is zero version advances
for `held_by_hysteresis`, `held_by_coalition_membership_hysteresis`, or
`held_by_transient_feedback_dwell` unless owner/lease/activation semantics are
explicitly changed by a coordinated takeover.

The integration owner must also address two non-D3 boundaries before claiming
closure:

1. `target_tracks_from_online_d2(...)` currently marks every state except
   lost/dropped assignable. It must carry lifecycle admission explicitly and
   submit only engageable or separately authorized tracks to D3. No truth ID or
   known target-count filter is allowed.
2. The intercept runtime must demote an already-active pair when its current D3
   binding changes from primary to reserve. D3 emits reserve as standby/hold;
   execution code must not retain an earlier primary active bit.

Run at least 10 same-geometry seeds after integration changes. Persist canonical
history and report plan churn, held-version advances, lifecycle-at-admission,
reserve unauthorized activation, high-threat unassigned count, and stale-plan
rejects. This D3 task ran deterministic module tests only; it did not relaunch
Blocks or replace the recorded episode.

## 2026-07-14 Latest 347-Record Churn Closure

The latest truth-isolated M5N2 baseline seed 001 contains 347 canonical D3
records and executable versions v1 through v35. It still showed approximately
one round-trip membership change per second. A representative record compared
candidate coalition cost `0.8868` with previous cost `2.8520`; the previous
side contained `2.2` of soft-feedback FOV search shaping. On the common base
execution objective the previous side is about `0.6520`, so the candidate does
not satisfy the configured 20 percent gain.

D3 now exports a common comparison-cost schema and a cumulative window-budget
schema. Main must preserve an intentional `window_id` across ticks that belong
to one budget window; a new `window_id` explicitly restores the budget. History
records include comparison/search costs, changes used, candidate changes,
remaining budget, and any hard bypass reason. Missing execution targets,
genuinely unavailable resources, and coordinated plan-level owner/activation
changes still publish a new identity immediately so old bindings become stale.

This D3 task ran deterministic tests only: `157 passed, 1 skipped`, with zero
failures required. Blocks was not relaunched. Main/D6 acceptance remains at
least 10 same-geometry seeds, zero unexplained periodic churn, no increase in
high-threat unassigned targets, zero online truth use, and no unauthorized
reserve execution. Physical coalition completion must still reach `8/10`; the
current best remains `5/10`.

## 2026-07-14 Actual-v2 Evidence Wiring

No D3 algorithm changed in this evidence-only run. Tuned 2v2 seed 1 uses
`d3-plan-c3cc6d28c365/1` across command, actual metrics, and 24 history
records. M5N2 seed 1 uses `d3-plan-cfdd088a10e1/1` across all three and has
214 history records. D6 reports two available history cases, zero unavailable
cases, and no validation reasons, closing the runtime identity chain at P0.

M5N2 feedback churn is 50 while plan-version, membership, and owner churn are
zero. Pair/target/coalition results are `2/3`, `2/2`, and `0/1`; the second
primary reached about 11.02 m. Target success is not coalition completion.
Second-primary 5 m closure and same-configuration multi-seed evidence remain P1.

## 2026-07-15 M5N2 20-Case Integration Status

Main runtime has now persisted canonical D3 history for the completed M5N2
batch: 10 baseline seeds and 10 `candidate_soft_prediction_trend_coast` seeds.
All 20 `d3_plan_history.json` files are readable and contain 3725/3725 valid
records. The previous integration item "main persists per-tick history" is
therefore closed for this batch.

The records show one current plan identity per case, zero plan-version,
coalition-roster, and owner transitions, and zero stale/rollback events. T001
keeps two active primaries and one standby reserve; T002 keeps one active
primary. Candidate membership evaluations are available and auditable, but
none changed the current roster. Runtime and D6 must calculate churn from
consecutive execution identities, not from the number of membership audit
objects.

Remaining integration work is outcome lineage rather than D3 plan persistence:

- record the collision object/category for every `collision_stop` so a terminal
  failure is not attributed to D3 without evidence;
- report `canonical target success` separately from T001 cooperative target,
  second-primary, and coalition diagnostics;
- identify the second primary from the current plan binding, never from a fixed
  vehicle name;
- retain missing tuned/dropout cases as unavailable. The extra
  `png_ttc_2v2_seed001` case is excluded from the M5N2 20-case aggregate.

The physical aggregate remains pair 12/60, canonical target 12/40, coalition
0/20, and second-primary 0/20. The candidate's paired non-degradation failure
does not demonstrate D3 planner degradation because D3 plan/member stability is
the same in both profiles.

## 2026-07-20 Scalable-3D Adapter Status

D3 now has an opt-in NED 3D rule profile, sparse candidate graph, and optional
shared-edge learning residual. This task did not modify or run the AirSim
adapter/runtime, so these capabilities remain **module-tested, AirSim-unwired**.
No 200v200 or learning outcome in this document should be inferred from the
local deterministic tests.

Future main-owned integration must map D2 track NED state/covariance and current
resource NED state/speed/range/region into the new fields, pass only online
identity-safe data, and persist candidate count, fallback reason, confidence,
latency, rule/final cost, plan identity, and solver result. Shadow mode must be
run before assist mode and compared over unseen seeds; hard reject, stale,
duplicate, and authorization violations must remain zero. D3 still emits the
final Hungarian/demand-slot plan, and D7/AirSim remains responsible for physical
dynamics and intercept outcomes.

The 2026-07-20 module evidence is 13 new deterministic tests and a full result
of `170 passed, 1 skipped`; the 200v200 sample used 800 candidate actions and
one invocation took 0.621 s. These are not AirSim, real-time, PPO, or multi-seed
acceptance results.

## 2026-07-20 Real-Episode Learning Frame Recorder Contract

D3 now exposes `planner.latest_planning_evidence` and
`build_latest_learning_frame_record(...)`. Main should call the helper once,
immediately after each successful planning tick, with the stable scenario
version, seed, episode, and monotonic frame index. It must not call
`_build_search_matrix()` or reconstruct costs in `IntegratedScalableModuleStack`.
The evidence already contains the exact rule/effective matrices, current
timestamp, previous version, and anonymous plan/input snapshots used by D3.

The evidence object is local-only and must not be published on an AirSim, D4,
or D7 bus. IDs are ordinalized and upstream metadata plus truth/actor/object
aliases are absent. `available=false` is a real frame outcome: main should log
its reason and must not substitute the prior frame. Expected examples include
stale calls, rejected regional authority, an authority-generation fence with no
new cost input, and snapshot-consistency failure.

This D3 task did not edit the runtime stack, launch Blocks, or write real
episode data. Module validation added 11 focused tests and collected 226 total:
`225 passed, 1 skipped`, with zero failures required and the optional OR-Tools
case skipped. Main-owned acceptance remains: export complete sequential frames
for every requested seed, verify no missing/duplicated frame index, validate
anonymous schema and split hash, aggregate unavailable reasons, and compare
rule/shadow pairs before any assist trial.

### Numeric-seed v2 dataset finalization

The recorder now emits `split=unassigned`; neither an AirSim scenario name nor
a scale may assign a split independently. Main must finish staging the complete
numeric-seed catalog, then call the v2 writer once. The writer assigns every
reuse of one numeric seed across all scenarios, scales, episodes, and frames to
one split and fails when fewer than three unique seeds or fewer than the
declared unseen test seeds are available. Main's globally reserved evaluation
seed set must remain disjoint from any train/validation generation set.

For scalable 200v200 export, main should pass
`iter_learning_frame_records(staging_path)` directly to
`write_learning_dataset(...)`. The current scalable main finalize does this and
no longer uses `read_text().splitlines()` plus a complete record tuple. D3 uses
a disk payload sidecar and a SQLite key/offset index, then streams canonical
output with split and frame SHA auditing. The remaining formal acceptance is
the clean-tree 900-episode capacity gate and worst-case dense/fault scenarios,
not another in-memory D3 call-site conversion.

No AirSim adapter, Blocks setting, actor, camera, control algorithm, Hungarian
solver, reward formula, or action space changed in this v2 contract task. No
AirSim episode or model-performance experiment was run; module evidence is
software-contract validation only.

## 2026-07-20 Regional Resource Hint Integration Contract

No AirSim runtime, adapter, settings, actor, camera, or control file changed in
this D3 task. The new `regional_planning_hint` entry is module-tested only.
Main must construct the D3-owned neutral DTO after D4 emits one projected
`RegionResourceRecommendation`; it must not pass a D4 control object or any
truth/actor/object/target/resource identity field.

The required episode order is D3 plan generation N, D4 regional advice derived
from generation N, then D3 plan generation N+1 with the exact generation-N
`previous_plan`. `created_at_s`, `expires_at_s`, every regional lease, and the
D3 planning timestamp must use the same monotonic episode clock. AirSim reset
must clear cached advice. A stale source, expired lease, region roster change,
non-conserving quota, or unsafe transfer capacity must produce a rejected hint
with a non-empty fallback reason while the ordinary D3 plan still completes.

Main/D6 integration acceptance must cover dynamic N/M and both one-to-one and
M-to-N demand over formal unseen seeds. Persist advisory/source identity,
available/considered/applied/rejected, rejection reason, allowed/actual transfer
count, total cross-region assignments, demand shortfall, churn, plan version,
solver latency, and D4/D7 gate state. Required safety thresholds are zero stale
hint application, zero allowance overflow, zero protected member transfer, zero
hard-edge resurrection, and zero unauthorized D7 execution. Performance and
physical interception non-degradation require a separate multi-seed AirSim
report; the current 14 fixtures and `239 passed, 1 skipped` module result do not
satisfy that requirement.

## 2026-07-20 Learning Evidence Safety Review

This review changed no AirSim adapter, Blocks setting, actor/detection path,
episode order, camera, or flight-control code, and no AirSim episode was run.
The D3-only contract now requires BC/PPO training to exclude test frames and
permits test seeds only through an explicit independent shadow/evaluation
entry. A full dataset load during a training command validates canonical file
content, split integrity, and hashes only; it must not feed test features or
labels into normalization, updates, or training metrics.

Any future main-owned recorder must preserve the strict v2 anonymous frame
allow-list and recursively reject truth/actor/identity fields. Any promotion
artifact must bind the dataset split hash, canonical frame-content SHA256, and
model-state SHA256 and must come from eligible paired `test` evidence. Rule and
residual assignments must both be rescored on `rule_cost_matrix_v1`; the model
output remains a proposal and cannot authorize an AssignmentPlan or D7 action.

The module acceptance result is 252 collected, `251 passed, 1 skipped`, with
zero failures; the skip is the optional OR-Tools installed-only benchmark.
There is still no formal model weight, no eligible >=20 unseen real/high-
fidelity test-seed shadow report, no assist promotion decision, and no AirSim
model-benefit or 200v200 full-stack validation.

## 2026-07-20 Learning Export Performance Note

This D3-only task changed no AirSim adapter, Blocks setting, actor, camera,
control command, runtime episode order, or online assignment contract. It did
not launch AirSim. The module micro-profile used synthetic 200-by-200 planner
evidence with 6,400 candidate edges per frame and measured only frame export.
Six-frame dataset finalization decreased from a 0.910 s median to 0.244 s while
canonical bytes and schema stayed identical.

The module profile alone did not explain the 74-76 s combined D3/D4/D5 staging
interval. Main subsequently completed a clean-tree scalable point-mass rerun
for nominal 200v200 seeds 930/931/932. The post-optimization D3 stage fields
were 0.0917/0.1129/0.0999 s, with 6 finalized frames and zero online truth use.
The combined finalization changed from 116.5624 s to 7.7377 s, but that field
includes D3, D4, and D5 and is not a D3-only result.

This rerun changed no AirSim setting, actor, camera, adapter, control command,
or episode sequence, and it must not be cited as AirSim evidence. Formal
900-episode generation, model training, and at least 20 unseen-seed evaluation
remain open. D3 tests collected 255 cases and returned `254 passed, 1 skipped`;
the skip is the optional OR-Tools dependency.

## 2026-07-21 Formal Assignment Audit Boundary

The formal point-mass assignment corpus now has a read-only full-sample audit. It
verified 900 scenario episodes, 1604 decision frames, 3658815 candidate edges,
117304 selected actions, zero dirty episodes, and zero online-truth use. The
canonical numeric-seed identity is 60/20/20; actual scenario episodes are
540/180/180 and frames are 962/320/322. This is point-mass dataset evidence, not
an AirSim episode or a physical interception result.

The learning-frame schema does not carry the current plan owner, current plan
version, runtime stale rejection, applied acknowledgement, or attributed outcome.
AirSim/main integration must persist these as separate versioned runtime records.
It must not infer them from `frame_index`, `previous_plan_version`,
`feedback_result`, `hysteresis_result`, or the rule-teacher `reward_components`.
The two result strings are categorical diagnostics; the reward fields are not
runtime causal rewards.

Before any AirSim shadow or assist review, main must bind the audit JSON and its
file SHA, then record the same-seed rule and learning proposals, current
owner/version, applied ACK, outcome, fallback, timeout, stale rejection, demand
shortfall, churn, and D7 gate state. Until D6 verifies those records, rule cost
plus demand-slot Hungarian remains the only default path and assist/authority
stay disabled. This audit changed no AirSim adapter, settings, actor, camera,
episode order, or control command.

## 运行计划 ACK 接入边界（2026-07-21）

D3 已实现 `scalable3d-assignment-plan-runtime-ack-v1` 的独立只读消费者。main 在保存
episode 日志时，应同时保留 ACK envelope、其引用的 D3 计划 envelope 和可选 D7 命令
envelope；只保存 ACK payload 无法验证来源 bus sequence 和 payload SHA-256。D6 离线
回放前先调用 D3 验证器，再按 plan id/version、source sequence 和时间窗连接控制与结果
sidecar。

接口已由 D3 自动化测试用 main 三维质点集成栈的 3v3、seed 7、1.2 秒场景验证：公开
consumer 校验最后一条 ACK，最终 3 条 binding 全部进入 D7，在线真值使用为 0。consumer
源码不导入 main，测试侧导入 main 集成栈用于覆盖顶层与 namespaced D3 类型组合。该次
没有启动 Blocks，也没有 AirSim actor、相机或 SimpleFlight 控制，因此不能写成 AirSim
证据。后续 AirSim runtime 若采用同一 ACK schema，仍需导出完整来源 envelope，并保持
truth ID 只进入 D6 离线评分。

冻结 900-episode 数据没有该 ACK，不能原地回填。新的 AirSim 或三维质点 episode 可以
生成 ACK sidecar，但 physical outcome 和 reward 必须由 D6 独立生成；运行 ACK 自报
这两项会被 D3 拒绝。当前 PPO、assist 和在线 authority 均不启用。

## AirSim 结果归因接入（2026-07-21）

新的 D3 适配器已经在三维质点 main runtime 上验证，尚未形成 AirSim 实测证据。AirSim
episode 若要进入同一合同，main 需要继续保存 D3 plan envelope、D7 guidance envelope、
`runtime.assignment_plan_ack`、D2 离线身份映射、真值状态、五米事件、场景配置和
episode manifest。D6 先独立完成 v1 联接并写出完整结果及摘要，D3 再按资源和
`global_track_id` 消费指定窗口。

AirSim 在线链路不得把 actor 名称、检测真实编号或仿真真值写入 D3 plan、D7 command 或
ACK。真值只存在于 D6 离线来源中；D3 输出会删除 truth target 和原始事件身份，只保留
布尔事件、距离进展可用性和来源 SHA-256。若 D6 报告在线真值使用不为 0，D3 直接拒绝。

后续 AirSim 验收至少包括：

1. 同一资源连续计划刷新产生不重叠窗口，plan version 和 occurrence 单调；
2. command-only、hold、缺 D7 消费、过期 owner/lease 和旧版本不能形成 applied 证据；
3. 规则与候选策略使用相同场景、seed、初始状态和传感器随机数分别运行，由 D6 输出配对
   sidecar；
4. 五米事件和相邻距离改善只作 observed diagnostic，正式 reward 在 paired、
   counterfactual 和 causal 字段完整前保持 unavailable。

当前验收日期为 2026-07-21，样本为 1 个三维质点 3v3 seed，不是 Blocks、SimpleFlight
或 ComputerVision 试验。AirSim seed 数、结果值和正式奖励均待验证。

## 隔离计划消费与 AirSim 边界（2026-07-22）

新增 `d3.isolated-plan-consumption-evidence.v1` 面向 main 的 control/treatment 克隆质点
世界，不是 AirSim runtime ACK。AirSim 后续若复用同一离线实验方法，每个 reset 后的 arm
仍需独立保存 source snapshot、plan payload SHA 和消费账本；该记录只能说明隔离 episode
接收了计划，不能替代 `runtime.assignment_plan_ack`、D7 控制命令或 SimpleFlight 执行
记录。

本次只运行 D3 单元与回归测试，没有启动 Blocks、ComputerVision 或 SimpleFlight，也未
修改 AirSim adapter、settings、actor、相机、episode 顺序和控制命令。故本节不增加
AirSim 性能证据。生产 ACK 和物理结果仍按前两节的完整来源 envelope 与 D6 sidecar 规则
处理。

2026-07-21 补充：离线 arm 现于 receipt 生成前按当前匿名 track roster 规范化目标库存。
AirSim 若复用 control/treatment reset 流程，无 binding 的当前目标会显式进入未分配和不
完整清单，生命周期已移除目标不会残留。该变更未修改 AirSim runtime、相机、actor、飞控
或生产 ACK；本轮证据仍是质点 reserved-seed 接口验证，不是 AirSim 实验结果。

## 在线故障库存的 AirSim 接入要求（2026-07-22）

在线 D3 计划现可在故障代际中表达“旧绑定继续有效、当前又出现新目标”。AirSim runtime
接入时，main 必须在同一 assignment 周期向 D3 提供当前 D2 tracks，并保留形成该计划的
planning frame。中心故障后，先由 D3 推进带完整库存的新代际，再由 D4 选择二级或分布式
owner。若 planning frame 不可用，不允许从 actor 真值或检测真实编号补写目标。

本轮只读验证使用三维质点 `center_failure`、5v5、3.2 秒、seed 1011/1019。两个场景均形成
二级 v3 计划和故障后可用规划证据。没有启动 Blocks、ComputerVision 或 SimpleFlight，
没有验证 AirSim 总线时序、reset、通信丢包、actor 生命周期或控制执行。AirSim 后续验收应
至少覆盖目标在故障前后增删、规划帧丢失、旧版本重放和二级再次失效，并保存严格计划摘要
及生产 runtime ACK 作为不同记录。

## 故障 authority 重放的 AirSim 边界（2026-07-22）

离线 executor 已能重放 center-to-secondary 的两阶段计划身份，但本次验收使用三维质点
reserved-seed 场景。没有启动 Blocks、ComputerVision 或 SimpleFlight。AirSim 复用时，
main 仍需保存转换前的 previous plan、转换后的 planning frame、D4 二级裁决时间、lease、
epoch 和来源 envelope；只保存最终 secondary plan 无法证明求解阶段使用了正确 owner。

AirSim 验收必须继续保留生产 `runtime_plan_ack`。本次新增的
`offline_authority_identity_replayed` 只说明隔离重放执行了同一 D3 helper，不能替代总线
采用、D7 命令或物理结果。后续还应覆盖二级再次失效和 distributed authority；当前实现
遇到不支持的 authority owner 会失败关闭。

## 区域待分配库存的 AirSim 接入（2026-07-22）

main 构造 D4 区域授权输入时，只应为上一计划中已有可执行绑定的目标生成 grant。上一计划
已明确为零绑定且未满足的目标可以不生成 grant，但必须原样进入当前 D3 航迹输入。D3 会
验证其前序库存并在新区域计划中继续标记未分配。main 不得根据 AirSim actor 标识、检测
真实编号或当前可见性临时补写区域 owner。

本轮只在三维质点 `secondary_failure`、5 目标、4 个授权绑定、seed 1011/1019 中验证该
接线，未启动 AirSim。后续 Blocks 验收应保存前序计划、D4 grant、D3 区域计划和生产
runtime ACK 四类独立记录，并检查待分配目标没有 assignment、coalition、commit 或 owner。
目标重新获得 D4 grant 后，必须通过新的计划版本进入执行集合。

## 隔离执行计划升版的 AirSim 边界（2026-07-22）

本次新增的是 D3 计划合同，不修改 AirSim settings、actor、检测、飞控或 episode 调度。
已检查 AirSim 接入文档，现有接口无需调整。后续 main 在 AirSim 或三维质点克隆世界使用
离线候选前，应把同一 planning frame 的 `previous_plan` 作为
`offline_solve_source_plan`、`plan` 作为 `formal_authority_plan`，连同完整 planning frame、
arm、receipt 和候选调用 `build_isolated_execution_plan(...)`。返回的同一计划对象交给
D7、D4 和 D6 适配层，禁止各适配层再次独立改写 plan id/version。

运行记录应保存 planning frame 输入摘要与转换摘要、求解源摘要、正式权威摘要、候选摘要、
转换证据摘要、执行计划摘要和隔离消费证据。隔离消费时刻不得早于新计划的严格递增创建
时刻。这些记录必须继续标明非生产。只有实际命令应用和状态窗口另有可验证日志时，D6 才
能报告物理结果。本轮未启动 AirSim，也没有新增 AirSim seed、轨迹或拦截指标。

## 区域权威离线重放的 AirSim 边界（2026-07-22）

AirSim 或三维质点 main 无需新增 D3 调用接口。main 继续把完整 `PlanningFrameEvidence`
交给现有离线干预执行器；D3 内部根据 `planning_path=regional_authority` 恢复记录授权并
调用线上区域规划函数。main 不应复制 owner、epoch、lease、commit，也不应自行放宽处理臂
的成员集合。

episode 记录应保留区域权威转换摘要、前序和记录计划摘要、arm action-mask 摘要及最终计划
摘要。待分配目标应在库存日志中出现，但在区域 binding 和控制命令日志中为零。若 AirSim
后续验证发现 D4 或 D7 使用了该目标，D6 应将其报告为授权边界违规，而不是补写 D3 binding。

2026-07-22 的验收来自三维质点 `secondary_failure` 20 seed，不是 AirSim。当前没有新增
相机、飞行控制、网络时延或物理拦截指标；AirSim reset、episode 调度和结果采集仍由 main
负责。
