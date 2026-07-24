# AirSim Offline Integration Plan

## Boundary

This plan is for offline log ingestion and replay-based evaluation only. The D2 module will not publish vehicle commands, control hardware, change flight paths, perform automatic disposition, or bypass human authorization.

## 2026-07-15 M5N2 Runtime Evidence Sync

- Scope: SimpleFlight M5N2 baseline 10 seeds plus candidate 10 seeds, 20 completed cases.
  The multi-seed run was terminated after M5N2 completion. One excluded
  `png_ttc_2v2_seed001` finished before `TERM` took effect; no dropout case finished.
- Online truth identity/state use was zero. Online D2 IDSW and continuity therefore remain
  unavailable rather than numerical zero; evaluator-only truth must stay outside the online
  association path.
- The D2 association main-bus stage was available for all 3805 ticks. Mean/P95/max were
  `2.521/3.147/98.942 ms`. These timings are nested inside main-bus timing and must not be
  added to it again.
- The second primary failed to reach 5 m in all 20 cases and ended with `collision_stop`, but
  collision-object evidence was not persisted. This is not sufficient evidence to attribute the
  failure to D2 or to retune its gate/lifecycle parameters.
- The default GNN/Hungarian path and center-owned `global_track_id` contract remain unchanged.

## Goal

Convert AirSim-recorded sensor/truth logs into D2 `Detection` inputs and evaluator-only truth metadata so the default GNN/Hungarian path and optional JPDA/MHT research adapters can be evaluated on frozen replay without leaking truth online.

## 2026-07-23 Ambiguity-Hold Candidate Wiring

The real AirSim/runtime owner remains main. D2 now exposes two opt-in interfaces for a clean
baseline/candidate comparison:

- `detections3d_from_d1_global_tracks(..., use_opaque_d1_source_tokens=True,
  publisher_node_id=..., publisher_epoch=...)`;
- `Scalable3DTracker.step(..., ambiguity_components=...)` with
`AmbiguityHoldLeaseConfig(enabled=True)`.

Main must enable both interfaces only in the candidate arm. The baseline arm must retain the
default adapter call and disabled hold config. D1 sidecars must be transported as the public
`d1.structural-ambiguity-evidence.v1` mapping; D2 does not import D1 implementation classes.
The publisher epoch must rotate after a D1 publisher restart. If main omits it in the explicit
Detection adapter, D2 records the compatibility default `d1-default-epoch-v1`; that fallback
cannot detect a restart and is not a production epoch-governance result.

Main must not retime the sidecar to the compensated D1 GlobalTrack publication epoch.
`measurement_timestamp` and `state_valid_timestamp` remain the original D1 measurement
epoch. D2 accepts a sidecar only when its state-valid time is not in the future and
`d2_tracker_epoch - state_valid_timestamp` does not exceed
`AmbiguityHoldLeaseConfig.max_component_age_seconds`. The D2 development default is
`1.0 s`, covering the current main `0.5 s` D1 scan-lateness budget plus ordinary transport
margin; an AirSim candidate run should set it explicitly from the recorded end-to-end delay
distribution. Lease deadlines use the D2 consumption epoch. Events retain the original
measurement, arrival, state-valid and publication timestamps for audit.

AirSim actor/object identity remains offline truth. The online candidate may consume only
opaque D1 member tokens, opaque observation evidence keys, timestamps, NED state/covariance,
and candidate-edge evidence.

Main completed the first clean point-mass gate at commit `9cd2a79` with nominal 200v200,
seed 1100, duration 2.2 s and `recon_count=2`. The candidate consumed all 46 received D1
evidence records over seven D2 cycles and accepted 33 component events. It prevented
69 hits, 69 misses and four births. D2 tracks changed `203 -> 201`, D3 assignments
`200 -> 197`, available/unavailable mappings changed `1566/230 -> 1492/294`, and RTF
changed `0.2245 -> 0.2112`. Candidate identity metrics were unavailable because of
`source_observation_outside_lineage_window`; online truth use remained zero. The candidate
failed the pre-registered availability and operational non-regression gate, so seeds
1101/1102 were stopped and the default remains disabled.

This result is not an AirSim run. D2 has now frozen the module-owned repair as
`d2.identity-evidence-commitment.v2` and
`d2.scalable3d_identity_evidence.v2`. A track remains
`identity_uncommitted_after_hold` after soft/hard expiry until a fresh original observation is
actually accepted. D2 now retains each affected track's private ambiguity-evidence keys and
maximum component measurement-time watermark after the reservation leaves the claim ledger.
Recovery requires a different key, a source timestamp strictly after that watermark, a
first-accepted original claim with zero replay count, no active lease, and a truth-free
`target_candidate` disposition. An old candidate that re-enters after reservation release is
removed before state update, hit accounting, claim binding, or `detection_to_track` publication.
Uncommitted frames expose no source-observation binding, reduce identity coverage, and leave
ID-switch comparison anchored across the gap. The public payload exposes only blocker count,
watermark, and overflow status; blocker keys remain private. Capacity overflow stays fail-closed.
Ordinary lineage failures still fail closed. The D2 suite passed 281 tests in 29.46 seconds on
2026-07-23; this proves only the module contract and state transitions.

`known_false_alarm` and `unknown` in the online commitment path are truth-free upstream sensor
dispositions. They must not be populated from the offline AirSim truth sidecar. D2 recursively
rejects truth metadata online; AirSim actor identity remains available only to the offline
evaluator.

Main and D6 completed that persistence and audit path at clean commit `909669b`. The repeated
nominal 200v200, 2.2-second, `recon_count=2`, seed-1100 gate, using seed 1100 as the first
reserved unseen gate seed, produced 203 D2 tracks and 200 D3
assignments for baseline, versus 201 and 197 for the candidate. Baseline strict IDSW, track
continuity and coverage continuity were `9`, `0.865` and `0.870`; baseline commitment coverage
was `1.0`. Candidate all-record commitment coverage was `0.9591494124`, with 1714 committed
and 73 uncommitted records. The uncommitted records comprised 69 active-hold and four
after-hold records. Both uncommitted binding-violation counts and online truth use were zero.

The v2 persistence and fail-closed contract therefore passed. Algorithm admission did not.
Tracks `GT3D-000185`, `GT3D-000186` and `GT3D-000202` recovered on fresh radar observations
with measurement time `1.2 s`; evaluation occurred at `2.130815 s`. Their approximately
`0.930815 s` lineage age exceeded the fixed `0.9 s` window by `0.030815 s`, so candidate strict
IDSW and continuity remained unavailable. The window must not be increased to clear this
gate. The candidate remains disabled and seeds 1101/1102 remain stopped. Candidate AirSim
execution must wait for a same-seed repair that preserves zero binding violations and zero
online truth use while restoring strict metric availability and D2/D3 non-regression.

## Inputs

Expected offline files:

- AirSim recording CSV or JSON with timestamped object positions.
- Optional camera/radar-like detection logs generated by a separate perception pipeline.
- Optional per-detection feature vectors from an offline embedding, classifier, or handcrafted descriptor.
- Optional ground-truth object ids for evaluation only.
- D1 `serialize_governed_replay()` JSON bundle with `d1.governed_replay_manifest.v1` manifest and `d1.sensor_observation.v1` records.
- Separate `d2-offline-truth-label/v1` JSONL for evaluation; truth never enters online detections/tracks.

The legacy AirSim replay tracker consumes only:

- `timestamp`
- 2D or projected 3D position mapped to the D2 measurement plane
- 2x2 measurement covariance
- `detection_id`
- optional `feature`

## Coordinate Conversion

Recommended adapter stages:

1. Read AirSim NED/world coordinates from logs.
2. Select an evaluation plane, such as horizontal `(x, y)` or image-plane projection.
3. Convert units consistently and record transform metadata.
4. Estimate or configure measurement covariance per sensor source.
5. Emit one `Detection` per observation per timestamp.

For D1 governed bundles, D2 currently accepts only radar records that declare NED working semantics. `[range, azimuth, elevation]` and its covariance are projected to horizontal N/E with the spherical-coordinate Jacobian and sensor NED position. Bearing-only acoustic and pixel-plane EO records are counted in `skipped_reasons`; they are not mixed into the N/E association plane. Their information must first be fused by D1 into a common-state product.

No live AirSim API calls are needed for baseline replay. The current D2-owned reader and report path is:

```text
load_airsim_replay_frames(JSON/JSONL)
  -> detect legacy frames or D1 governed manifest/records
  -> D1 radar spherical-to-N/E conversion + online ID anonymization
  -> run_airsim_replay_association(...)
  -> ReplayAssociationReport / association_logs.jsonl
  -> run_threshold_sensitivity(...)
```

This remains an offline reader. AirSim launch, ComputerVision metadata capture, and episode JSONL production are main/runtime responsibilities.

## Replay Loop

```text
for frame in offline_log:
    online_detections = strip_simulator_truth(convert_frame_to_detections(frame))
    association = tracker.step(online_detections, frame.timestamp)
    offline_evaluator.observe(frame.offline_truth, association, tracker.snapshot)
summary = merge(online_metrics, offline_evaluator.summary)
```

The helper `run_airsim_replay_association()` wraps this loop and returns `id_switch_count`, `track_continuity`, `duplicate_assignment_count`, per-frame association logs, active `global_track_ids`, and a D4-aligned soft/hard risk summary.

Online logs use schema `d2-association-log/v2`. They contain risk profile/version, track/anonymized-detection order, measurement/active-track counts, gate diagnostics and NIS, but no actor name, truth label, truth target count or NEES. `offline_truth_evaluation` separately contains truth target count, confusion matrix, initialization latency, false-track statistics and NEES. This separation is mandatory for ComputerVision replay because AirSim object names are evaluation truth, not deployable identity evidence.

Truth samples first require a unique replay frame within the frozen `1e-9 s` timestamp tolerance. Samples without an exact frame remain `partial/unmatched`; nearest-neighbor timestamp filling and fabricated labels are forbidden. Only after this exact-time alignment may an external truth JSONL with `match_annotation.offline_only=true` match projected detections to truth positions with Hungarian assignment and a default 25 m spatial gate. This occurs after the online association run and is never written back to the frozen replay or online logs.

## 2026-07-13 Strict Calibration Baseline

Main/runtime captured and froze real D1 governed replay for both strict geometries:

- nominal 4 m: 20 unique seeds;
- tight 2 m: 20 unique seeds.

On 2026-07-15 D2 consumed the frozen six-difficulty real AirSim replay/truth manifests without launching AirSim. The complete v2 rerun used 6x10 screening and 6x20 confirmation seeds. Candidate `gnn-g5.99-qa1-ld3_7-mw0.5x` reduced mean IDSW from `1.358333` to `0.616667` (`54.6012%`) and changed identity continuity from `0.981046` to `0.983954`; its headroom reduction was `15.3448%`. False-track remained zero, P95 loop latency was `15.470 ms`, and baseline/candidate online truth leakage was zero. All five overall gates passed and the runner emitted a promotion review recommendation. Only clutter and combined passed every per-difficulty gate; four strata failed closed because baseline IDSW was zero. The lightweight JPDA comparison degraded. The online default remains baseline GNN/Hungarian and `default_online_path_changed=false`.

Online truth leakage was zero. Exact timestamp matching uses the `1e-9 s` tolerance described above, with unmatched samples retained for audit rather than imputed. The latest complete D2 regression on 2026-07-14 is `99 passed, 1 warning`; the local Matplotlib `Axes3D` warning does not affect association, metrics, or calibration results.

## Target Count and Replan Identity Contract

D2 does not infer target count from a scenario name and does not require a
fixed 2v2 or 5v5 shape. For every replay frame, the associators build their
cost matrices from the actual `len(active_tracks)` by `len(detections)` input
sets, and the `Tracker` creates, updates, loses, or drops tracks from those
sets. Main runtime scenarios may choose the target/drone count through their
own `--drone-count` parameter; D2 consumes only the detections/tracks it is
given for that frame.

`DryRunAssociationResult.to_bus_message()` exports all current
`global_track_id` values through `active_tracks` and `global_track_ids`. The
export list is derived from the tracker state and is not truncated or padded to
a fixed count before D3/D5/D6 handoff.

The AirSim Blocks 2v2 active-degradation path is a baseline fixture for this
identity contract. In that path, D2 owns the `global_track_id` namespace across
central-plan and secondary-node replan phases. A replan frame may change
`source_node_id`, `link_type`, detection ids, or assignment authority, but it
must be applied to the same `Tracker` instance/state when it represents the
same replay episode. D2 then updates the existing `GlobalTrack` by association
and Kalman prediction/update rather than minting a new global id.

The acceptance condition for a no-ID-switch replan is:

- each physical target keeps the same `global_track_id` before and after the
  central-plan to secondary-node transition;
- `MetricsRecorder.summary()["id_switch_count"] == 0`;
- `DryRunAssociationResult.to_bus_message()` exposes the same
  `id_switch_count` for D4/D6 handoff checks.

This is covered by
`tests/test_dry_run_adapter.py::test_airsim_2v2_replan_keeps_global_track_ids_and_records_no_id_switch`.

## Evaluation Outputs

- Per-frame association logs.
- `ReplayAssociationReport` JSON via `write_replay_association_report()`.
- Association log JSONL via `write_association_logs_jsonl()`.
- Track lifecycle transitions.
- `id_switch_count`
- `track_continuity`
- `duplicate_assignment_count`
- D4-aligned soft risk summary: association ambiguity, candidate overlap, cost margin, D5 disagreement.
- D4-aligned hard risk summary: IDSW delta, duplicate assignment/track risk, continuity collapse.
- Threshold sensitivity rows from `run_threshold_sensitivity()`.
- RMSE when truth positions are available.
- Truth-to-track confusion matrix.
- Versioned M-of-N initialization success and latency.
- False-alarm detections, missed detections, false-track count/rate and N/M mismatch frames.
- NIS and offline-only NEES with 95% chi-square coverage.

## Future Compatibility

- Stone Soup can be used later to cross-check full JPDA/MHT behavior in a separate research environment.
- FilterPy can be used later for IMM/EKF/UKF experiments if maneuvering prediction becomes the main IDSW driver.
- These dependencies must remain optional so the NumPy/SciPy fallback tests keep passing on the current host.

## Next AirSim Calibration Stage

The 2 m capture is complete and is no longer an open action. P1 AirSim work now extends the frozen 4 m/2 m contract with:

- longer replay windows and repeated crossings;
- explicit OOSM/arrival-order stress while preserving both timestamps;
- controlled occlusion, missed detections, and clutter combinations;
- M-of-N initialization, lost/drop lifecycle, false-track, gate/risk, and NIS/NEES calibration;
- per-seed and aggregate continuity checks under the same truth-isolation rules.

JPDA/MHT, Stone Soup end-to-end tracking, and FilterPy EKF/UKF/IMM remain optional P2/offline benchmarks. A D2-owned native 3D sparse rule path now exists, but it is not connected to this legacy AirSim replay adapter and has no real AirSim acceptance evidence. Main must provide a truth-free Cartesian NED D1 product and versioned bus integration before that path can be used in an AirSim-derived representative subscenario; it must not consume raw radar spherical measurements, pixels, actor IDs, or object names.

## Acceptance Checks

- AirSim replay works without network or simulator connection.
- D1 governed manifest/records replay produces timestamp-grouped radar/N-E frames, skip diagnostics, and no source observation identity leakage.
- Legacy AirSim `frames` JSON/JSONL remains supported.
- 5-target AirSim-like JSONL replay produces association logs, metrics, soft/hard risk summary, and threshold sensitivity rows.
- No command/control topics or APIs are imported by the D2 adapter.
- Missing optional fields produce explicit warnings or default covariance/feature behavior.
- Metrics from AirSim replay can be compared against synthetic simulation metrics with the same recorder.
- Strict nominal 4 m and tight 2 m evidence remains traceable to 20 unique seeds each.
- Truth alignment is exact within `1e-9 s`; unmatched samples remain auditable and never use nearest-neighbor timestamp fabrication.
- Candidate promotion requires all versioned IDSW, ceiling-aware continuity, false-track, latency, and truth-isolation gates. The complete frozen v2 report now passes all overall gates and recommends review, but the runner does not change the online default. Per-difficulty zero-baseline IDSW failures and dropout partial truth alignment remain explicit review inputs.

## 2026-07-14 Truth Boundary Acceptance

- Online replay uses an explicit `TrackerTruthPolicy.ONLINE`; any `Detection.truth_id`, explicit `truth_ids_present`, or nested truth/actor/object identity fails before prediction or association.
- Main-owner boolean status fields `online_truth_isolated`, `online_truth_hints_used`, `truth_metrics_available`, and `continuity_available` are accepted. Non-boolean values under those keys, offline truth payloads, and identity fields remain rejected.
- Offline evaluation explicitly opts into `TrackerTruthPolicy.OFFLINE` and continues to report an available integer `0` when truth proves there were no ID switches.
- Truthless IDSW, continuity, and RMSE remain present as `None` with consistent availability/reason fields. Truth-free birth/lost/drop/rebirth counts and transitions remain available for AirSim lifecycle summaries.
- Validation covered eight rejection cases, the main-owner four-boolean positive case, 3-frame and 5-frame truthless replays, and a 7-frame lifecycle sequence on 2026-07-14. Full D2 regression passed `98` tests with one environment-only Matplotlib warning; acceptance required zero failures and no state mutation on rejected online input.
- No lost/drop/gate threshold changed. Calibration of the real `T001 -> T005` lifecycle pattern remains P1.

## 2026-07-14 Source-Lineage Inflation Guard

The audited real Blocks input contained two targets but D1 emitted a third
track at frame 313 and later teleported an existing D1 track. D2 now treats
`source_global_track_id` as anonymous upstream lineage: it adds a continuity
cost inside the existing Mahalanobis gate, suppresses an unmatched gated
shadow birth, and quarantines a bound source that jumps outside the lineage
gate. AirSim actor/object identity is not consumed.

The module-level acceptance fixture contains four frames, two moving sources,
one overlapping duplicate source, and one source teleport. It passed with two
canonical D2 IDs, one suppressed shadow, and one quarantined discontinuity;
the full D2 suite passed 99 tests on 2026-07-14.

## 2026-07-14 Post-batch Same-seed Evidence

Main completed the real M5N2 seed-1 baseline and candidate reruns. The 142/141
frame episodes each had two D1 source tracks after the first two startup
frames, and D2 retained only `T001/T002` for all 140/139 active frames. Both
ended with birth/lost/drop/rebirth `2/0/0/0`; no `T008` record existed.

Online IDSW and continuity correctly remained unavailable because actor/truth
identity was absent. Evaluator-only replay with the external sidecar produced
IDSW 0, continuity 1.0, false-track count 0, and zero truth-isolation
violations. Post-hoc adjudication of the emitted track records produced IDSW 0
and continuity 0.985915/0.985816 because the two startup frames had no emitted
track.

No shadow or teleport event occurred in either smooth episode: suppression,
quarantine, and source-conflict counts were all zero. Therefore the same-seed
inflation recurrence is closed. A later 20-case M5N2 run satisfied the ordinary
multi-seed count and timing collection, but did not inject duplicate-source,
teleport, dropout, clutter, or legitimate-new-target events and did not produce
batch-specific offline identity metrics. The remaining P1 acceptance is now a
targeted governed suite, not another ordinary minimum-seed run; it must report
lifecycle, offline identity availability, plan/pair churn, and false-suppression
results.

## 2026-07-16 Source-Governance Metric Contract

The AirSim-style replay adapter now forwards the frame-level
`upstream_local_identity_rejection_count` audit field into `Tracker.step()`.
The value must be a non-boolean, non-negative integer; a missing field means
zero, while invalid type or range fails before tracker state changes. It is an
upstream rejection count only: D2 does not turn it into a detection or track
and does not promote any local/source ID to `global_track_id`.

`source_binding_conflict_count`, `source_lineage_quarantine_count`, and
`upstream_local_identity_rejection_count` are present in metrics, replay risk,
threshold-sensitivity per-seed rows, and multi-seed/calibration aggregates.
They remain diagnostics and do not alter GNN/Hungarian, Mahalanobis/source
lineage gates, lifecycle thresholds, or the current soft/hard risk profile.

Validation on 2026-07-16 used two three-frame synthetic replay seeds: each
produced one binding conflict and one quarantine, while upstream rejection
counts were 2 and 4; the aggregate means were 1, 1, and 3. The full D2 suite
passed 123 tests with one environment-only Matplotlib warning. No AirSim
Blocks episode was launched for this change, so real duplicate-source,
teleport, clutter, and legitimate-new-target acceptance remains the existing
P1 targeted-suite requirement.

## 2026-07-20 Scalable 3D Offline Identity Artifact

The AirSim impact was reviewed without changing the runtime adapter or launching
Blocks. D2 now owns a versioned evaluator-only artifact that can be used after
main persists truth-free D1/D2 records and the independent observation truth
sidecar. Main must provide frame/global-track lineage evidence with source
observation IDs, measurement timestamps, replay generations, lifecycle states,
and referenced D1/D2 bus sequences. It must also record the evidence-bundle
SHA-256 in the episode manifest.

`evaluate_scalable_3d_identity_files()` verifies the bundle and its bound D1,
D2, and truth files before joining `observation_id` to evaluator truth. Record
sequences must bind exact D1 lineage and the same D2-owned six-state track,
6x6 covariance, frame, lifecycle, association state, and source observations;
all persisted D2 track frames must be represented. Track kinematics are audited
for provenance but never used to select truth. It does not use AirSim actor
names/IDs, final proximity, or nearest distance. Ambiguous or incomplete lineage
leaves IDSW, continuity, and duplicate identity metrics unavailable rather than
zero.

The D2 contract passed 23 focused tests and the full
`162 passed, 1 warning in 30.63s` module suite on 2026-07-20. This is interface
evidence only. Main currently skips D2 track frames without lineage and must
retain them as unavailable/unassigned evidence before the producer wiring meets
this contract. Real AirSim-derived artifacts and formal multi-seed identity
performance remain open; the default GNN/Hungarian, gates, and control path are
unchanged.

## 2026-07-22 陈旧观测重放治理接入要求

active-risk seed 1005 质点回放确认：D1 可在连续状态发布中重复携带同一底层
`latest_observation_id`。D2 现以 `latest_sensor_id + latest_observation_id` 作为不透明
在线证据键，在关联前隔离已消费证据。该键只用于新鲜度治理，不能解析目标序号，也不能
包含 AirSim actor/object identity。

真实 AirSim runtime 进入 D2 前应保留下列字段：

- D1 后验的状态有效时刻；
- `arrival_timestamp`；
- 底层观测的 `measurement_timestamp`；
- `latest_observation_id`；
- 稳定且带命名空间的 sensor/source node 标识；
- replay generation（若上游显式提供）。

D1 predict-only 发布不得伪造新的 observation ID。相同证据键对应不同底层量测时间时，
D2 按 timestamp conflict 隔离，不进行状态更新。D2 对每帧输出 replay quarantine、claim、
tentative stale drop 和受约束 coalescence 审计。main 已在开发期总线上将这些字段以
`d2-observation-evidence-governance-v1` 原样持久化，包括 fresh/replay、timestamp
conflict、coalescence、suppressed births 和 tentative stale drop 的累计值。

2026-07-22 的早期专项采用 point-mass seed 1005，不启动 Blocks。当时 10 帧活动航迹数为
`5,6,6,5,5,5,5,5,5,5`，quarantine 9 次、tentative stale drop 1 次、在线 truth 使用
0 次；该结果只保留为 main 尾部合并前的历史证据。当前 main 逐扫描融合 D1 尾部输入，
只把最终后验送 D2 一次，seed1005 集成 replay=0 合法；v3 复现验收同时接受 replay=0 与
bounded replay。随后完成的脏工作树
development 20-seed active-risk 运行中，D6 七类 availability 均为 20/20，D4 adoption
188/188，seed 1005 离线恢复 GT1-GT5 五条唯一映射且在线 truth 使用仍为 0。这关闭了
开发期 main/D6 接线验证，不是 AirSim 验收结论。随后提交 `0fa7c00` 的 clean-tree 复跑
记录 `repository_dirty=false`、20 个 pair、D4 adoption 188/188、两臂各 1960 条命令和
100 条离线唯一映射。该 clean 运行已完成；两臂 1 s 窗口内均无 5 m 拦截，不能解释为
拦截收益或 AirSim 结论。

## 长 episode 与 OOSM 接入

main-owned scalable runtime 推荐显式构造：

```python
tracker = Scalable3DTracker(
    observation_claim_config=ObservationClaimLedgerConfig(
        config_version="d2-observation-claim-policy-v2",
        retention_seconds=30.0,
        max_count=100_000,
        max_lateness_seconds=5.0,
    ),
    replay_coast_config=ReplayCoastConfig(
        config_version="d2-replay-coast-policy-v1",
        grace_seconds=0.5,
    ),
)
```

以上数值是模块默认 baseline，不是 AirSim 冻结值。main 应根据实测速率、episode 时长、
迟到分位数和内存预算生成配置，并把 config/schema version 写入 manifest。D1 传入 D2 的
state-valid `measurement_timestamp`、底层 `source_measurement_timestamp` 和 scan
`arrival_timestamp` 必须分开保留。

若 main 已在上游保证完整 scan 的 state-valid epoch 单调，可以直接调用 `tracker.step()`。
若网络按 arrival 顺序交付且整个 scan 可能乱序，应构造
`Scalable3DOOSMScanAdapter(tracker=tracker, config=OOSMScanAdapterConfig(...))`：

1. `submit_scan()` 每次只接收一个共同 measurement epoch 的完整 scan，按 arrival 顺序
   调用；空 scan 显式传入 measurement/arrival timestamp。
2. submit 可能返回 0 到多条 released result。main 必须按每条 result 的 timestamp 发布，
   不得用 submit 调用时刻覆盖量测时刻。
3. `flush()` 只在确认 episode 输入结束时调用。它把迟到窗内剩余 scan 按量测时间排空，
   不用于周期更新，不允许跨 reset 复用 adapter/tracker。
4. 超窗、早于已释放 state、arrival 回退或 buffer overflow 的 rejected event 进入 D6 日志，
   不调用 Tracker，也不伪称固定滞后回溯。

main 应持久化 Tracker result/summary 的 reason counts、ledger current/peak/evicted、overflow、
too-old、两个水位线、undated、配置版本和 eviction 统计；adapter summary 的
submitted/admitted/released/rejected、current/peak scan/detection buffer、measurement inversion、逐原因
计数和 last released time也需进入 episode 汇总。离线 benchmark 的 false suppression、
nearby recall、erroneous coalescence、confirmation latency 和 IDSW 只供 D6 评分，不进入
在线 D2 消息。

真实 AirSim 仍需验证相机/雷达适配后的 observation ID 唯一性、时钟误差、迟到分布、
缓冲上限、遮挡/杂波和距离分档门限。2026-07-22 在 clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b`
上完成的 20/50/100/200 各 5 seed formal 质点治理复跑，只关闭 claim 容量、安全淘汰、
哈希来源和 evaluator-only 真值隔离的 clean 复跑。本批没有启动 AirSim，不改变本文的
AirSim 适配、时钟和场景标定计划，也不构成完整 200v200 验收。

main 还需持久化 `replay_coast_count/events/track_ids/reason_counts/config` 和
`missed_track_ids`。grace 应覆盖 D1 相邻全量发布到下一次雷达更新之间的正常间隔，并给
时钟抖动留出已测裕量；不得按 episode 时长设置。超过 grace 后 D2 自动恢复 miss，main
不应在外层重置 `last_update_time`。整帧乱序仍先由 OOSM adapter 排序，coast 不承担乱序
回溯职责。

## 离线部分身份诊断接线

AirSim 在线 episode 不增加任何 truth 字段。main 继续在 episode 结束后，把匿名 D1/D2
records、identity evidence 和独立 truth sidecar 交给 D2 evaluator。legacy evidence
生成 `d2.scalable3d_identity_evaluation.v1`；identity commitment evidence 生成 v2。
两种制品都可附带 `partial_identity_diagnostics`，供 D6 读取以下字段：

- mapping 总数、受评分数、可评估数、ambiguous、unavailable 和 missing 数；
- mapping、完整帧和相邻转移 coverage 及各自 availability/reason；
- 因一真值帧对应多条可评估航迹而排除的锚点数及 reason counts；
- lower-bound anchor transition 数、IDSW lower bound 及 availability/reason；
- 不可评估映射 reason counts。

D6 必须将 strict `id_switch_count` 与 `id_switch_lower_bound` 分开存储和展示。严格指标
unavailable 时不得用下界填充；下界为 0 也不得改写成完整 IDSW=0。当前没有 upper
bound。D6 也不得从重复映射的持久化顺序推导部分下界。main 需把新 evaluation 文件
SHA-256 写回 manifest，再由 D6 校验。

2026-07-22 的 seed 1000 只读复算用于接口检查，没有启动 AirSim，也没有生成新批次。
真实 AirSim 后续应按场景、seed、遮挡、杂波、漏检和 OOSM 分组统计 coverage 与
blocker；在 D6 完成接线前，新字段只属于 D2 producer 证据。

## Observation Truth v2 接线

main 在 episode 结束后为每条在线 observation 写一条独立离线记录。目标记录携带
`disposition="target"` 和唯一 `truth_target_id`；由场景 producer 明确生成的虚警写
`disposition="known_false_alarm"`，不写目标 ID；无法确认的观测写
`disposition="unknown"`。三类记录都使用
`d2.scalable3d_observation_truth.v2`、原 observation ID 和原
`measurement_timestamp`。

AirSim actor/detection ID 只能在离线 producer 内用于形成 target 标签，不能进入在线
D1/D2 DTO。虚警处置必须由生成虚警的 producer 分支显式写出，禁止按 observation 名称
中的 `fa`、目标距离或在线关联结果补写。main 应使用
`write_scalable_3d_observation_truth_labels()` 生成规范 JSONL，把返回的 SHA-256 写入
identity evidence manifest；也可调用 `Scalable3DObservationTruthLabel.target()`、
`known_false_alarm()` 和 `unknown()` 构造记录。

D6 展示时分开 strict、partial 和 disposition audit。纯虚警映射不进入身份分母；
unknown 仍使 strict unavailable。main 更新 producer 后应先重跑 seed 1000，检查旧
缺标签样例转为 `known_false_alarm_only`，再运行 1000--1019；真实多 target 混轨计数
不得因虚警合同上线而被删除。

## Identity commitment evaluation v2 接线

main 在持久化 `d2.scalable3d_identity_evidence.v2` 后，应使用同一 evidence bundle
生成 `d2.scalable3d_identity_evaluation.v2`，并把 evaluation SHA-256 写入 episode
manifest。D6 只读取 evaluation 的 `audit` 和公开
`identity_evidence_records`，不得读取 tracker 私有 blocked-key 集合。

D6 已在配置谱系绑定后的 clean 提交
`ff881316243ff5a2991a4659ab78637ed625d123` 汇总 all-record
与 created/matched observed-record coverage、恢复拒绝原因、blocker count、水位线年龄、
overflow 和两个未提交 binding violation 字段。seed 1100 candidate 的两个 violation
均为 0，三条超龄恢复由发布新鲜度门控保持为未提交。strict IDSW、track continuity 和
coverage continuity 恢复为可用值 `3/0.8266667/0.8283333`，baseline 为
`9/0.865/0.870`。

该次运行是三维质点 clean A/B，不是 AirSim。candidate 的 D2 航迹和 D3 分配仍由
`203/200` 降至 `201/197`，两项 continuity 也退化，因此算法候选保持禁用。真实 AirSim
episode 与扩展 seeds 1101/1102 未执行。

## Recovery publication freshness gate 接线

D2 已把恢复配置升级为 `d2.identity-commitment-recovery-config.v2`，默认发布年龄预算
为 `0.9 s`。main 传入 D2 的 Detection batch 必须继续以延迟补偿后的统一状态有效时刻
作为 `Detection3D.measurement_timestamp`，并令它与本次 tracker frame timestamp
相等。原始雷达、视觉或声学量测时刻保存在 `source_measurement_timestamp`，不能被
状态传播后的时刻覆盖。

AirSim adapter 若收到状态有效时刻早于当前 D2 frame 的输入，不得直接送入
`Scalable3DTracker.step()`；应先由现有 OOSM/状态传播边界处理并保留原双时间戳。
恢复门控计算 tracker frame 与原始 source measurement 的年龄。超龄时航迹保持
uncommitted，D6 应从既有恢复原因计数中展示阻断，不把它写成 IDSW 0。

AirSim episode 还必须逐条持久化实际恢复配置，并用规范化 SHA-256 绑定 offline identity
manifest 与原始 D2 JSONL。当前三维质点权威证据使用
`main-scalable3d-identity-recovery-publication-freshness-v1`，配置哈希为
`sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`。
AirSim 不得默认沿用该哈希；若节点配置、预算或版本不同，应生成新的快照和哈希，并在同一
episode 内执行一致性校验。

2026-07-23 已完成 D2 确定性模块测试：专项 `32 passed`，完整模块
`291 passed, 1 warning in 29.05s`；并完成上述三维质点 clean seed 1100 A/B。没有启动
AirSim，也没有生成新的 AirSim replay。由于首个 gate seed 已出现 D2/D3 数量和
continuity 退化，本候选不进入真实 AirSim 多 seed；固定 `0.9 s` 不扩大，seeds
1101/1102、10 s 和 20-seed 矩阵停止。

## 承诺准入复核后的 AirSim 边界

固定提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 已在三维质点 200v200、seed 1100
的同输入两臂中验证 D2 显式承诺状态可被 D3、D5 active vision 和 D7 guidance
失败关闭消费。第 2 版计划从上一版撤出 11 条未承诺旧绑定，版本 `1 -> 2`，并把
assignment 数调整为 186；第 3 版继续拒绝 11 条未承诺目标。被拒绝 ID 进入 D3
assignment、D5 active-vision command 和 D7 guidance command 的计数均为 0。

该复核没有启动 AirSim，也没有改变 D2 的 AirSim 输入、话题、时间戳、坐标系或
`global_track_id` 合同，因此本文件不新增 adapter API。AirSim 后续只需保持以下验收：

1. D2 每次发布完整、显式的 `identity_commitment_by_track`，不由下游从临时 hold 列表
   推断；
2. main/D3 对缺失、未知和未承诺状态全部失败关闭，并严格增加计划版本；
3. D5/D7 只消费当前已接纳计划中的 committed 目标；
4. D6 同时记录 D2 continuity/mapping 退化和下游 unauthorized continuation，不能用后者
   为 0 代替前者通过；
5. AirSim 证据必须重新记录实际时钟、漏检、遮挡、杂波、配置快照和制品哈希，不能沿用
   本次质点运行的场景或运行时指纹。

`hold_plus_centroid` 本轮 46 个候选全部被拒绝，实际处理为 0。该零 treatment 不构成
AirSim 候选准入依据，也不改变 seeds 1101/1102 继续停止的决定。

本轮只运行 D2 模块回归，结果为 `291 passed, 1 warning in 29.29s`；未启动 AirSim。

## 已知虚警排除计数接线

AirSim 或质点 episode 写出 observation truth v2 后，D2 evaluation 的
`known_false_alarm_only_mapping_count` 必须由最终 frame mappings 重算，只接受
`status="excluded"` 且 `reason="known_false_alarm_only"`。仅虚警来源若同时发生
未观测状态、谱系超窗、重复或其他完整性错误，mapping 保持 unavailable，不能报告为
已排除。

D6 的严格校验不放宽。消费者从 evaluation 的 frame mappings 独立重算排除数，并与
audit 比较。2026-07-24 使用 nominal 200v200、10 秒、seed 1102 的质点制品完成只读
验证：旧 disposition 组数为 14，最终排除映射为 11；新 producer 输出 11，其他身份
载荷不变。该次没有启动 AirSim，没有改变 AirSim adapter、双时间戳、坐标系、观测
schema 或在线身份路径。真实 AirSim 的 v2 虚警 producer 和多 seed 校准仍需后续运行。
