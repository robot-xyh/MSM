# D1 Sensor Fusion Module

Offline research module for radar, acoustic, EO, and optional synthetic lidar heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

## 当前权威增量（2026-07-16）

- 顶层 API 新增 `sensor_observation_from_local_image_track()`，把 main-owned
  `LocalImageTrackObservation` 保守适配为 D1 `SensorObservation | None`。只有 `measured`
  输出 `modality="eo"`、`frame_id="pixel"`；`lost` 始终返回 `None`，不会把旧像素再次送入融合。
- 适配器逐字段复制 measurement/arrival 双时间戳、2×2 pixel covariance、confidence 和
  quality flags；可见光/红外统一进入 EO 模态，同时以 `metadata.spectral_band` 保留波段。
  缺失、非有限、非对称、错误形状或非半正定 covariance 在 D1 边界 fail closed。
- metadata 保留 namespaced sensor/stream/epoch/local track、bbox/center 和 backend/batch 等
  在线审计字段；global/truth identity（含嵌套键）被拒绝。未显式传入 observation ID 时，ID
  由 sensor/stream/epoch/local track/measurement time 确定性生成；显式 source lineage 可对
  重复投递去重。
- 被接受的视觉观测把 `source_track_key` 去重累积到
  `GlobalTrack.metadata.source_track_ids`，但不会把本地来源键写成或重绑定
  `global_track_id`。
- 2026-07-16 无随机 seed 的构造合同回归为专项 `13 passed`、D1 全量 `111 passed`。本轮未
  启动 AirSim，未改变默认检测源、launch/reset/episode 顺序，也未生成新的 RMSE/NIS/NEES。

## 历史系统增量（2026-07-15）

- main 已完成真实 AirSim M5N2 baseline 10 case 与 candidate 10 case，共 20 case；本轮
  在线 `truth_identity` 与 `truth_state` 使用计数均为 0。
- 20 case 共记录 3,805 个 main-bus tick。D1 fusion 阶段 mean/P95/max 为
  `320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段；main-bus 整体为
  `349.34/487.40/1305.99 ms`。因此 100 ms 系统预算仍是开放 P1，不能把此前 D1-only
  batch replay 加速写成真实运行时已经达标。
- `measurement_timestamp`、`arrival_timestamp`、观测/航迹 covariance 和 NED 工作空间合同
  继续作为强制基线保持。本批是终端闭环与时序实验，未提供可用的 NIS、NEES 或 RMSE 标定
  结果，不能据此声称传感器噪声模型或估计一致性已经闭合。
- M5N2 达到 20/20 后批次终止；TERM 生效前额外完成的 1 个 `png_ttc_2v2_seed001` 被明确
  排除，dropout 完成数为 0。

权威证据为 `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md` 和
`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/`
下的两个汇总 JSON。后文保留历史实现与验证记录。

## Scope

This directory is limited to simulation and offline evaluation. It does not include real fire-control parameters, damage logic, hardware drivers, real vehicle control, automatic action, or bypass of human authorization.

## Runtime

The implementation uses NumPy/SciPy-compatible fallback code and does not require FilterPy or Stone Soup. Optional placeholders are available in `d1_sensor_fusion.compat`.

## Ownership

D1 owns this module and `subagent_reviews/D1_*`. Under the strict project workflow, main dispatches D1 tasks, D1 edits and tests only its owned paths, and main performs integration summary. D1 module changes must check whether README, PLAN, GAP, and review files need matching updates.

As of the 2026-07-09 P0-A hardening pass, D1 has closed the engineering P0-A items for FDIR-light, covariance floor/ceiling limits, and timestamp uncertainty metadata while preserving the existing `measurement_timestamp`, `arrival_timestamp`, covariance, and NED `GlobalTrack` contracts. D1 continues to provide `GlobalTrack[]`, `TrackUncertaintySummary[]`, latency/quality summaries, and sensor-health evidence only; it does not generate `AssignmentPlan` versions, decide active degradation, rewrite `global_track_id`, or modify D7 PN/PNG control behavior.

## Run Tests

From repository root:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```

## Run Full Simulation

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_simulation.py \
  --drone-count 3 \
  --duration 60 \
  --dt 0.1 \
  --seed 7 \
  --output research_modules/d1_sensor_fusion/reports
```

The command above is the historical 3-target baseline. In integrated runs, main owns the scenario size and passes N via `--drone-count`; D1 consumes the resulting N target truth/observation sources without a 2v2 or 5v5 cap.

The script writes:

- `reports/EXPERIMENT_REPORT.md`
- `reports/tracks_xy.png`
- `reports/rmse_latency_ablation.png`

## AirSim Dry-Run Fixture

The module includes a no-AirSim dependency dry-run adapter for integration tests:

```python
from d1_sensor_fusion import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)

fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
observations = observations_from_airsim_dry_run_fixture(fixture)
```

The adapter emits `SensorObservation[]` with `measurement_timestamp`, `arrival_timestamp`, `frame_id`, and `covariance` filled for synthetic radar, acoustic, EO, and optional lidar observations.

## Blocks JSONL Replay

Main/AirSim runtime `blocks_sensor_observations.jsonl` files can be read back and replayed without importing AirSim:

```python
from d1_sensor_fusion import FusionAdapter, read_blocks_sensor_observations_jsonl

observations = read_blocks_sensor_observations_jsonl("blocks_sensor_observations.jsonl")
adapter = FusionAdapter()
tracks = adapter.ingest_many(observations)
summaries = adapter.track_uncertainty_summaries()
```

For the current Blocks N-actor integration, D1 expects upstream runtime logs to provide
simulation-derived observations from AirSim truth and `simGetDetections`/detector boxes. D1
receives the N target truth/observation sources provided by main and sizes `SensorObservation[]`
ingest and `GlobalTrack` output from those input arrays. Historical 2v2 and 5v5 logs are baselines,
not algorithm limits. These records must include `measurement_timestamp`, `arrival_timestamp`,
`measurement`, and `covariance`. D1 then publishes `GlobalTrack` objects with `position`,
`velocity`, and 6x6 `covariance`. This is a simulation contract only; it does not claim real radar,
acoustic, or lidar hardware is connected.

As of the 2026-07-08 P1 AirSim multi-seed calibration prep, D1 has regression coverage for
Blocks-style CSV replay preserving measurement/arrival timestamps, covariance, NED `GlobalTrack`
state, source support, coverage cell, latency/OOSM audit, and region quality summaries. JSONL replay
also preserves nested EO `camera_model` metadata for the projection model.

Main runtime now owns the P1 D4/D5 calibration sweep and automatically invokes the D6 standard
report bundle after the sweep. D1 does not launch that sweep or write AirSim runtime reports; it
keeps the replay/schema/latency/OOSM/region-quality fields stable so the main/D6 calibration reports
can consume them.
For that bundle, D1-owned evidence is limited to observation delay/quality fields such as raw and
post-fusion `LatencyAuditSummary`, `TrackUncertaintySummary`, `FusionQualityRegionSummary[]`,
`FusionQualityRegionWindowSummary[]`, `SensorHealthSummary[]`, covariance-limit reasons,
`covariance_scale_reason`, and `timestamp_uncertainty_s`. Main/D6 may report or aggregate these
fields; D1 does not turn them into active degradation actions.

As of the 2026-07-09 P1 input-support pass, the dry-run fixture includes
`schema_version="d1.airsim_dry_run_fixture.v1"` and rejects unsupported fixture schema versions.
Generated dry-run observations annotate `d1_fixture_schema_version`, and replay records annotate
`d1_replay_schema_version` so downstream audits can distinguish fixture/replay provenance.
The current P1 fixture path also accepts real Blocks/CV-style JSONL/CSV fields such as top-level
`bbox_xyxy`, `center_px`, `camera_metadata`, `detection_metadata`, `source_support`,
`coverage_cell`, `covariance_scale_reason`, and secondary/mobile recon cue metadata. These are
normalized into `SensorObservation.metadata` and carried into the latest `GlobalTrack.metadata`
lineage without requiring PNG frames or an AirSim Python dependency.

## Historical Baseline: 2026-07-10 AirSim 2v2 Contract Audit

The reset-separated 2v2 smoke output under
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710/` was replayed through
the D1 reader without changing main/runtime. Across six episodes, all 1,528 radar, acoustic, EO,
and synthetic-lidar records retained measurement/arrival timestamps and finite symmetric positive
semidefinite covariance; no record had `arrival_timestamp < measurement_timestamp`. The full-flow
main episode bus also retained both timestamps and covariance trace in every D1 observation summary
and retained timing/covariance fields in `TrackUncertaintySummary`. No D1 timestamp or covariance
contract regression was found.

The smoke also makes the remaining P1 boundary explicit. The current main Blocks writer omits
`schema_version`, so new output is accepted through `legacy.blocks_sensor_observations` rather than
the versioned v1 path. It also omits `coverage_cell`, so D1 can only emit the fallback `unassigned`
region, and the main tick currently serializes per-track uncertainty summaries but not region/window,
latency-audit, or sensor-health summaries. Finally, the fixed 0.2 s delayed multi-sensor stream makes
raw OOSM counts high; advisory sensor-health isolation thresholds require expected-latency calibration
before D4/D6 may consume them as fault evidence. The main bus also enables simulation-only truth-hint
association and retains two tracks, while default truth-free replay of the same file can create a
duplicate third track; replay configuration provenance and truth-free association parity therefore
remain P1. These are writer/schema/calibration items, not a reason to weaken the D1 dual-timestamp or
covariance contract or to treat truth labels as online identity evidence.

The subsequent 10-seed 2v2 run under
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_multiseed_20260710/` confirms that the
D1 contract can be consumed repeatedly by reset-separated system episodes. The separate
`p0_truth_isolation_smoke_20260710` run confirms that online D5 local detection/MOT identifiers no
longer depend on AirSim actor/object names. This does not close D1 truth-free replay parity: synthetic
D1 observations may still carry `truth_id` as an offline label, and the main fusion configuration may
still enable simulation-only truth hints. The next D1 integration pass therefore keeps configuration
provenance, truth-free multi-seed replay, explicit writer schema/coverage fields, expected-latency
health calibration, and durable Blocks/CV fixtures open as P1.

## Historical Baseline: 2026-07-11 Truth-Isolated 5v5 Runtime Evidence

The three reset-separated 5v5 episodes under
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
provide the first main-bus evidence after online truth-hint isolation. The no-degradation,
secondary-degradation, and distributed-degradation cases each completed five frames with D1, D2,
and D3 health reported as `ok`; D1 published 15 module records per episode and D3 retained full
assignment coverage. This demonstrates that the online D1 -> D2 -> D3 path remains connected when
truth labels are unavailable to association.

D1 governance is now represented in `main_episode_bus_metrics.json`: all three episodes report
latency audit and region-quality metrics, including `d1_max_delay_s` about 0.2 s,
`d1_region_quality_coverage_rate=1.0`, and one `d1_latency_audit` plus one
`d1_region_quality_window` event per episode. The observed
`d1_oosm_observation_rate=0.9866666667` is the current asynchronous replay accounting result for
fixed-delay, sequentially ingested sensor batches. It is not evidence of a sensor fault and must not
directly trigger D4 degradation. Expected-latency budgets, batch/watermark semantics, and fault
injection controls still require calibration.

This is a seed-7, five-frame, 0.4 s smoke run. It closes neither the multi-seed P1 calibration item nor
long-duration latency/region threshold governance. Truth-isolated multi-seed replay, longer windows,
sensor-specific delay distributions, and negative fault cases remain required before D1 runtime
thresholds can be considered calibrated.

## Main Interfaces

- `SensorObservation`: canonical sensor input with `measurement_timestamp`, `arrival_timestamp`, optional cross-node communication metadata, covariance, and normalized `timestamp_uncertainty_s` / `timing_uncertainty_s` metadata.
- `FusionAdapter`: EKF fusion, fixed-lag replay, covariance limiting, and FDIR-light sensor-health accounting. Required methods are `predict_track()`, `update_at_measurement_time()`, `compensate_latency()`, `_bucket()`, `track_uncertainty_summaries()`, and `sensor_health_summaries()`.
- `GlobalTrack`: output state `[px, py, pz, vx, vy, vz]`, covariance, timestamp, source support, identity likelihood, quality level, covariance-limit reasons, latest timestamp uncertainty, latency audit, and sensor-health metadata.
- `TrackUncertaintySummary`: compact quality export with track IDs, covariance trace/a95, level, measurement age, source support, coverage cell, timing fields, timestamp uncertainty, and covariance-limit reasons.
- `SensorHealthSummary`: per-sensor FDIR-light export with `sensor_id`, `status`, `fault_reason`, `reject_count`, `isolation_hint`, `recovery_state`, and counters for duplicate, OOSM/stale, low-quality, anomalous covariance, and timestamp-uncertainty evidence.
- `FusionQualityRegionWindowSummary`: windowed coverage-cell trend export for covariance growth, freshness, source gaps, and latency/OOSM audit flags.
- `ReconCueSummary`: compact radar/GlobalTrack cue for second-stage recon camera pointing, generated by `summarize_recon_cue_from_tracks()`.
- `RadarCovarianceConfig`: optional distance-dependent radar covariance parameters. Defaults preserve the original noise model.
- `CooperativeBearingObservation` / `CooperativeObservationGroup`: D2-confirmed, same-canonical-ID bearing rays with observer lineage, platform pose/extrinsics covariance, dual timestamps, and a common estimate time.
- `localize_bearing_observation_group()`: NumPy-only weighted bearing-ray localization for 2..N observers with baseline, LOS angle, time-skew, information rank/condition, residual, and covariance-completeness gates.
- `CooperativeTrackEstimate` / `covariance_intersection()`: conservative same-ID state fusion with CV propagation, process/timing covariance growth, and message UUID/source-lineage deduplication.

## Cross-Node Metadata

`SensorObservation` accepts optional communication fields directly or through `metadata`: `source_node_id`, `target_node_id`, `relay_node_id`, `link_type`, `sent_timestamp`, `received_timestamp`, `payload_kind`, `stale_after_s`, and `source_support`. `FusionAdapter` preserves the latest observation communication metadata in `GlobalTrack.metadata` and publishes modality counts in `GlobalTrack.source_support`. It also suppresses repeated updates from the same source/sequence/payload lineage, including relay duplicates.

## Replay Schema And CSV

D1 replay schema v1 is `d1.sensor_observation.v1`. New `sensor_observations.jsonl` and Blocks replay records should include `schema_version` plus `observation_id`, `sensor_id`, `modality`, `measurement_timestamp`, `arrival_timestamp`, `frame_id`, `measurement`, and `covariance`. Existing `blocks_sensor_observations.jsonl` files without an explicit version are still accepted as legacy records when the required observation fields are present; the parser annotates them as `legacy.blocks_sensor_observations` in metadata.

Minimal CSV replay is available through `read_sensor_observations_csv()` and `replay_sensor_observations_csv()`. CSV cells for `measurement` and `covariance` should contain JSON arrays; `metadata`, `communication`, and `source_support` should contain JSON objects. CSV support is for replay/audit convenience and does not replace JSONL as the primary runtime log format.
CSV rows without an explicit `schema_version` are treated as `d1.sensor_observation.v1`, so
`covariance` is required for calibration replay instead of being silently accepted as a legacy
record.

New governed writers are available through `write_sensor_observations_jsonl()` and
`write_sensor_observations_csv()`. They always emit `schema_version="d1.sensor_observation.v1"`
and require `ReplayProvenance` with `scenario_id`, `scenario_version`, `config_id`, and
`config_digest`. The writer removes `truth_id`, actor name, and equivalent truth keys from online
metadata by default. An explicit `include_offline_truth=True` places those labels only under
`offline_truth`; they are never used by `FusionAdapter` association in the governed replay tests.

`summarize_sensor_observation_latency_audit()` can compute raw replay observation latency, OOSM,
stale, and duplicate-lineage counters from `SensorObservation[]` before a full `FusionAdapter`
run. The fusion-side `FusionAdapter.latency_audit_summary()` remains the authoritative post-fusion
audit when replay compensation is executed.

## Quality And Latency Audit Exports

`FusionAdapter.latency_audit_summary()` exports `observation_count`, `max_delay_s`, `mean_delay_s`, `replay_count`, `oosm_observation_count`, `stale_observation_count`, `stale_or_oosm_observation_count`, duplicate count, and maximum replay history size. OOSM means an arriving observation's `measurement_timestamp` is older than the fusion time already processed; stale means it is stale at processing time or its arrival delay exceeds `stale_after_s` when that budget is supplied.

`FusionAdapter.sensor_health_summaries()` exports per-sensor FDIR-light status derived from duplicate payload suppression, OOSM/stale latency evidence, low-confidence or occluded observations, anomalous covariance, and timestamp uncertainty. `SensorTimingExpectation` can configure an expected latency, tolerance, and whether fixed-delay OOSM is normal for a sensor. The health export then separates total OOSM from unexpected OOSM and reports mean/max latency plus budget exceedance count/rate. The summary is intentionally advisory: it gives D4/D6 explainable health evidence and isolation hints, but it does not isolate sensors outside D1 or issue control decisions.

Observation covariance is bounded before EKF use, and 6x6 track covariance is bounded after prediction/replay/update. Floor/ceiling reasons such as `observation_covariance_floor`, `track_covariance_floor`, `track_covariance_ceiling`, `long_extrapolation`, `low_quality_observation`, and `occluded_observation` are preserved in `GlobalTrack.metadata` and `TrackUncertaintySummary.to_dict()` without removing the covariance matrices themselves.

`FusionAdapter.region_quality_summaries()` derives lightweight `FusionQualityRegionSummary[]` records from `TrackUncertaintySummary[]`, grouped by `coverage_cell`. The region summary aggregates track count, a95, measurement age, handover readiness, source support, source gaps, and stale-track count for D4/D6 quality consumption while preserving the existing per-track `TrackUncertaintySummary` contract.

`annotate_covariance_growth_rates()` fills `TrackUncertaintySummary.covariance_growth_rate` from adjacent summary snapshots, and `summarize_region_quality_windows()` emits `FusionQualityRegionWindowSummary[]` over region snapshots plus optional `LatencyAuditSummary` snapshots. Supplying `window_size_s` creates deterministic `coverage_cell` time buckets and aligns timestamped latency audits to each bucket. This gives D4/D6 separate fields/flags for regional covariance growth, freshness degradation, source gaps, and latency/OOSM instead of forcing those causes into one quality number.

`summarize_recon_cue_from_tracks()` derives a lightweight `ReconCueSummary` from `GlobalTrack[]` or track-like dicts. It can summarize all tracks or a single `coverage_cell`, computes `cue_position_ned` as an inverse-covariance-trace weighted centroid, emits `cue_covariance`/`covariance_trace`, `active_target_ids`, timing fields, and diagnostics including `track_count`, `stale_count`, and `default_covariance_count`. Missing covariance uses a conservative default and is reported instead of changing the `GlobalTrack` contract.
Optional cue metadata can carry the secondary/mobile recon node, cue source, or mode through `ReconCueSummary.metadata`.

Video/image streams are represented only by derived observations such as bounding boxes, camera metadata, timestamps, and covariance. D1 does not require or store PNG frames.

As of the final 2026-07-11 validation, the D1 governed writer/provenance contract is adopted by the
main episode bus, online records strip truth/actor/object identity, and offline truth labels are written
separately for evaluation. This closes the D1 contribution to the P1 contract layer. Remaining D1 work
is validation and algorithm enhancement: longer real multi-seed maneuver/occlusion/node-loss replay,
sensor-specific latency and health-window calibration, broader camera/bbox fixtures, RMSE/NIS/NEES
consistency, cooperative runtime validation, and model-set/adaptive-covariance comparisons.
Replay schema v1, legacy JSONL compatibility,
covariance-required CSV replay, raw and fusion latency audit, sensor-health summaries, timestamp
uncertainty, covariance floor/ceiling limiting, covariance scale reason passthrough, region quality
summaries, region window helpers, covariance-growth helpers, recon cue summaries, source de-dup,
nested EO camera metadata replay, real CV field normalization, dry-run fixture schema checks, and
Blocks JSONL replay are already implemented baselines.

## Centralized Cooperative Localization P1 Foundation

The optional `cooperative.py` path implements the D1-owned centralized numerical foundation without
changing `FusionAdapter` defaults. A caller must provide observations that already share a
center-owned canonical `global_track_id`; the helper never associates targets, consumes truth IDs,
or creates/rebinds a track identity.

Bearing observations are transformed from calibrated sensor/body geometry into NED rays and
propagated to one estimate timestamp. The weighted least-squares solution includes bearing,
platform-pose, sensor-extrinsics, timing, and process uncertainty. It rejects fewer than two unique
rays, short baselines, near-collinear LOS geometry, excessive time skew, missing covariance under
the default policy, deficient/ill-conditioned information, negative depth, and excessive residual.
The summary retains all measurement/arrival timestamps and reports observer lineage, pairwise LOS
angles, information rank/condition, residuals, covariance inflation, and the accept/reject reason.

`covariance_intersection()` provides a dependency-light state-fusion baseline for unknown cross
correlation. It propagates 6-state NED estimates to a common time, suppresses repeated message UUID
or identical source lineage, preserves the supplied canonical ID, and produces a covariance no more
confident than the corresponding false-independent information sum. This is not a distributed
consensus path, a D2 association implementation, or a runtime integration claim. AirSim multi-seed
replay, D1/D2 two-stage association/fusion, maneuver and occlusion benchmarks, and distributed
end-to-end validation remain open.

## Current P0/P1/P2 Status (2026-07-12 Documentation Sync)

The current main-level status is recorded in
`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`. The D1 capability baseline remains
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`.
Commit `33e6fa0` and the 2026-07-12 PNG delivery validation changed D5/D6/D7 and main/runtime, not
D1 source or tests. D1 therefore has no behavior change in that delivery pass: its full regression
remains `62 passed`, its P0 contracts stay closed as regression baselines, and its open P1 replay,
cooperative-runtime, statistical-calibration, model-set, and adaptive-covariance work remains open.
The 2v2 `20/20`, post-lock dropout, and M5N2 `0/9` results are downstream control evidence, not D1
fusion-accuracy acceptance. P2/P3 planning is unchanged.

The P1 contract layer is closed: the main episode bus writes the D1 governed replay manifest and
truth-stripped online records while keeping truth in a separate offline-label path. In the 10-seed
ComputerVision batch, the downstream T001 two-primary contract met its 8/10 acceptance threshold;
the secondary and distributed 3/3-ACK commit cases passed, and the 2/3-ACK case aborted fail-closed.
These downstream results show that D1 state, covariance, timing, and lineage can feed the governed
contract chain; they do not add control or coalition responsibilities to D1.

- **P0 closed/regression baseline:** dual timestamps, NED, covariance, FDIR-light, covariance bounds,
  timestamp uncertainty, source-lineage de-duplication, and N-target input remain mandatory. The
  current D1 regression baseline is `62 passed`.
- **P1 contract layer closed:** governed replay/schema/provenance is used by main, online truth is
  isolated from offline scoring labels, and D1 timing/covariance/lineage records are present in the
  accepted CV and degradation/fail-closed episode chain.
- **Open D1 validation/enhancement:** real multi-seed maneuver/occlusion/node-loss/cooperative replay,
  sensor-specific latency and health-window calibration, camera/bbox fixture expansion,
  RMSE/NIS/NEES consistency, and model-set/adaptive-covariance comparison remain open. These are not
  reasons to reopen the P1 contract-layer result.
- **Physical boundary:** the 15 s SimpleFlight batch is diagnostic only. Its 0/30 active-pair physical
  intercept result does not close physical interception and is not a D1 fusion-accuracy acceptance.
- **P2 isolated only:** the frozen governed-replay harness now reports RMSE/NIS/NEES/time for the
  current path. FilterPy and Stone Soup are unavailable in the validated environment and emit an
  explicit `unavailable_reason`; they do not replace the NumPy EKF/fixed-lag default path.

The next D1 sequence is real multi-seed replay and statistical calibration, followed by optional
association-to-fusion and model-set comparisons. The acceptance command is:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```

## Governed Replay Manifest And Serializer

`serialize_governed_replay()` is the frozen online entry point for main. It returns a JSON-safe
`{"manifest": ..., "records": [...]}` bundle and validates the full batch before returning. The
manifest uses `d1.governed_replay_manifest.v1` and records the observation schema, NED fusion working
frame, scenario/config IDs, versions and digests, seed, timestamp ranges, coverage cells, and an
opaque source-lineage entry for every observation.

The strict path requires finite ordered dual timestamps, covariance matching the measurement shape,
`coverage_cell`, and JSON-safe lineage. Online records recursively remove truth, actor, and object
identifiers. `serialize_offline_governed_replay()` is the explicit offline-only path that places such
labels under `offline_truth`; it never restores them into online metadata. Existing unversioned
Blocks JSONL remains readable through the legacy compatibility reader, but it does not satisfy the
strict governed manifest contract.

This closes the D1-owned P1 manifest/serializer implementation. The main episode bus now adopts the
API with scenario/config provenance and seed data; D1 still does not own AirSim launch, episode order,
or runtime report generation.

## Isolated P2 Filter Benchmark

`p2_benchmark.py` consumes the frozen
`tests/fixtures/p2_governed_filter_benchmark_v1.json` bundle. It validates the governed manifest,
NED working frame, dual timestamps, observation covariance, source lineage, and truth-stripped online
records before running the existing `FusionAdapter`. The separate `offline_truth` sidecar is used only
after filtering to compute position RMSE and six-state NEES; track NIS is read from the current path.

Run the benchmark with:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_p2_isolated_benchmark.py
```

The 2026-07-11 validation produced RMSE `0.2335 m`, mean NIS `0.0426`, mean NEES `0.0651`, and
`6.9-10.1 ms` wall time across two runs of six observations on the validation host. The low NIS/NEES values indicate a
conservative covariance on this small synthetic fixture; they are evidence that the metric path runs,
not a real-sensor consistency acceptance. Neither optional dependency is installed. FilterPy and
Stone Soup therefore report `status=unavailable`, null metrics, and a non-empty `unavailable_reason`.
No optional package was added to default requirements and no online D1 code path was changed.

## Governed Long-Replay Challenge (2026-07-12)

D1 now exposes a deterministic, main-callable synthetic long-replay fixture without changing the
default NumPy EKF path:

```python
from d1_sensor_fusion import build_long_replay_scenario, summarize_long_replay

scenario = build_long_replay_scenario()
summary = summarize_long_replay(scenario).to_dict()
```

The official CLI writes the same `LongReplaySummary.to_dict()` payload as JSON:

```bash
python3 research_modules/d1_sensor_fusion/scripts/run_long_replay.py \
  --seed 17 --duration 60 --target-count 5 \
  --output research_modules/d1_sensor_fusion/reports/long_replay_summary.json
```

`--output` is a JSON file path; its parent directory is created when needed. The CLI defaults to
seed 7, 60 seconds, three targets, and `reports/long_replay_summary.json`.

The default fixture runs for 60 seconds with three crossing targets and generates range-dependent
radar observations, coarse acoustic bearings, EO pixel observations, a dense-crossing clutter
window, full/partial EO occlusion, delayed radar OOSM, and relay duplicates. Main can override the
target count, seed, duration, rates, and event intervals through `LongReplayConfig`; no 2v2/5v5
constant is used.

The fixture freezes scenario, config, replay-schema, summary-schema, and threshold-profile versions.
Every online observation keeps measurement/arrival timestamps, covariance, NED working-frame
metadata, coverage cell, and opaque source lineage. Observation IDs and lineage contain no stable
target slot. Truth labels and six-state trajectories are returned only through the explicit
`d1.long_replay_offline_truth.v1` sidecar and never enter online observations or `GlobalTrack`.

`summarize_long_replay()` reuses `FusionAdapter`, raw/fusion latency audits, sensor health, and fixed
region windows. It reports modality/event counts, final track/source summaries, truth-leak count,
and metric availability. RMSE/NEES remain explicitly unavailable until offline D2 canonical-ID
mapping exists. A default smoke run produced 843 observations, 21 injected radar OOSM events, six
deduplicated relay copies, 29 region windows, and zero online truth leaks in about 8.8 seconds on the
validation host. This closes the D1-owned synthetic long-replay construction/summary gap, not the
real Blocks/CV multi-seed calibration gap. The CLI has a subprocess regression that verifies
argument propagation, output-directory creation, summary schema, and zero online truth leakage.

## Real AirSim persisted-input freeze

`airsim_replay_freeze.py` reads main-persisted JSON/JSONL observations or frames with embedded
`sensor_observations`/`observations`/`records`. It does not import the AirSim SDK and processes the
input array length without a 2v2/5v5 constant.

The output is `manifest.json`, `sensor_observations.jsonl`, `offline_truth.json`, and `summary.json`.
Online records reuse `d1.sensor_observation.v1` and preserve measurement/arrival timestamps,
covariance, canonical observation frames, NED fusion working frame, coverage cell, lineage, sensor
health, event labels, and scene/profile/source-schema identity. Missing processing/publish timestamps
or sensor health are explicitly `unavailable`; they are not inferred from arrival time.

Legacy Blocks IDs may encode actor/object/truth identity. The freezer replaces online observation IDs
with opaque sequence IDs and recursively removes identity keys and strings containing known identity
tokens. Truth ID and NED position are written only to the evaluator-only
`d1.airsim_offline_truth.v1` sidecar. Crossing, occlusion, missed detection, false alarm, OOSM, and
node-exit labels are diagnostic evidence; a frame without a real measurement never creates a sensor
observation.

```bash
python3 research_modules/d1_sensor_fusion/scripts/freeze_airsim_replay.py \
  INPUT.jsonl OUTPUT_DIR \
  --scenario-id dense-crossing --scenario-version 2 \
  --config-id blocks-settings-v4 --config-version 4 --seed 17 \
  --target-spacing-m 4.0 \
  --profile-id p1-dense-v1
```

This closes the D1-owned persisted-input freeze and truth-sidecar separation gap. Main still owns real
AirSim capture; D2/D6 still own offline identity scoring and multi-seed RMSE/NIS/NEES and threshold
calibration. D1 full regression after the sidecar follow-up is `74 passed`.

### Offline truth sidecar deduplication

The evaluator sidecar has one deterministic sample per `(truth_id, timestamp)`. If a frame truth
sample has a position and observation metadata has only the same identity, the available position
replaces the unavailable sample regardless of input order. Two available positions within `1e-6 m`
are treated as the same sample; inconsistent available positions reject the freeze instead of
silently selecting one. Samples at different timestamps remain separate. An identity with no source
position remains `position_availability="unavailable"`; no position is interpolated or fabricated.

Both the sidecar and summary publish position-availability counts so D2/D6 can distinguish valid
position labels from identity-only labels before strict offline scoring.

### Capture provenance gate

AirSim freezing now requires an explicit capture-side declaration containing scenario/config version,
seed, `target_spacing_m`, and `evidence_path`. The captured spacing is authoritative and is never
inferred from truth positions. A conflicting CLI/API declaration or inconsistent declaration across
payloads fails closed. Manifest and summary expose per-field availability; online records remain
truth-free, while the evaluator sidecar is bound by the capture-provenance digest. Regression coverage
includes 4 m and 2 m profiles across 20 seeds each. Current D1 regression: `79 passed`.

## Online scene-observation anonymization (2026-07-14)

AirSim or another simulator may use scene truth to generate a noisy `SensorObservation`; that does
not authorize the online fusion path to receive the actor/object identity used to generate it. Main
or runtime must apply the public boundary before sending scene-derived observations to online D1/D2
algorithms:

```python
from d1_sensor_fusion import (
    anonymize_online_observations,
    assert_online_observations_identity_free,
)

online = anonymize_online_observations(
    scene_observations,
    identity_tokens=scene_actor_names,
    stream_id="online",
)
assert_online_observations_identity_free(
    online,
    identity_tokens=scene_actor_names,
)
```

`anonymize_online_observations()` returns new objects. It recursively removes truth/actor/object/
segmentation identity keys, removes inferred or caller-supplied identity tokens from nested values
and `classification_hint`, and replaces `observation_id` plus source lineage with frame-local opaque
IDs. It preserves measurement, covariance, both timestamps, sensor fields, communication timing,
and sensor/camera geometry. `assert_online_observations_identity_free()` fails closed on any remaining
identity key or supplied/inferred identity token.

The existing dry-run and offline evaluator paths are unchanged. In particular, evaluator-only truth
sidecars remain available from the original scene observations; callers must not build an offline
sidecar from the anonymous online copies. Validation on 2026-07-14 used two two-observation EO batches
whose geometry and all non-identity fields were identical while target, actor, and truth names were
changed. Acceptance required exact equality of every anonymized `SensorObservation` field, unchanged
numeric/camera geometry, zero identity leakage, validator rejection of injected leaks, and unchanged
offline sidecar labels. All conditions passed; full D1 regression is `83 passed`.

This closes the D1-owned P0 API gap. System closure still requires main/runtime to call this boundary
at every scene-state online ingress. Values whose identity is not represented by an identity metadata
key must be supplied through `identity_tokens`; omission is a caller contract violation and the main
integration must maintain the complete scene identity-token set.

## Association governance and fixed-lag checkpoint correction (2026-07-14)

An audit of the persisted AirSim M5N2 seed-001 episode found that D1 could update one track more than
once from one physical observer scan, create a duplicate radar birth after a strict-gate miss, and
discard intermediate filter posteriors while pruning the fixed-lag window. The last behavior made a
later replay restart from the original anchor and could move an existing state discontinuously.

`FusionAdapter` now limits each `(modality, observer, scan)` to one update per track, permits only a
unique recent mature-track radar reacquisition under a separate chi-square gate, suppresses ambiguous
radar births, and audits inconsistent bearing-only Cartesian corrections. Fixed-lag pruning now places
the posterior checkpoint immediately after the latest accepted observation not newer than the lag
boundary. This preserves the original process-noise intervals; observations older than the checkpoint
remain available in a history archive for legal measurement-time OOSM replay. Modality is part of the
scan key, so a delayed acoustic observation is not rejected merely because radar used the same scan
number.

Validation on 2026-07-14: focused association/OOSM tests passed `5/5`, the complete D1 suite passed
`87/87`, and main reported the complete AirSim runtime suite passed `134/134`. These are code and
interface regressions. The corrected D1 implementation has not yet rerun the same real AirSim seed;
elimination of the historical third birth and 31.8 s state jump remains a P1 episode acceptance item.

## Covariance contract hardening (2026-07-14)

Every observation entering `FusionAdapter`, online anonymization validation, versioned replay writing/
reading, or AirSim persisted-input freezing must now carry a modality-sized covariance: radar `4x4`,
legacy acoustic `1x1`, scalable `acoustic_3d` `2x2`, EO `2x2`, and lidar `3x3`. The matrix must be finite, symmetric, and positive
semidefinite. Invalid or missing input raises `ValueError` before a filter update; D1 no longer repairs
it with a default model, reshapes flat arrays, symmetrizes it, or resets it silently. Existing quality
scaling and covariance floor/ceiling handling still apply after a legal input passes this gate.

Unversioned historical records that omitted covariance are accepted only through
`migrate_offline_legacy_sensor_observation()`. That explicit evaluator-only API records the migration
mode, original missing reason, model/default identifier, parameter source, generation inputs, and
resulting dimensions under `covariance_imputation_provenance`. Migrated observations are rejected by
online fusion, online governed serialization, and AirSim freeze. Ordinary legacy readers fail closed.

Validation on 2026-07-14 covered missing, non-finite, non-symmetric, non-PSD, and wrong-sized radar
covariance; explicit radar legacy migration; governed replay; legal OOSM/fixed-lag observations; and
the existing seven-record AirSim freeze fixture. The full D1 suite passed `92/92`. No real AirSim
episode was run. Sensor-model defaults used for offline migration remain research defaults, not
real-sensor calibration evidence.

## 同帧批量 fixed-lag 处理（2026-07-14）

`FusionAdapter.process_batch(observations)` 是正式的同帧/同到达批次入口。它保留调用方给定
的到达顺序，并对每条观测分别执行 covariance 合同、`measurement_timestamp`/
`arrival_timestamp` 审计、NED/pixel 帧校验、source lineage 去重、observer scan 约束和关联；
优化仅缓存同一航迹历史版本在同一测量时刻的状态，并把每条更新后的全历史发布重放合并为
每个受影响航迹一次。它不会丢弃观测、伪造同步时间、缩短 fixed-lag 证据或改写来源信息。

main 的推荐调用为：

```python
batch_result = fusion_adapter.process_batch(frame_observations)
global_tracks = list(batch_result.tracks)
batch_audit = batch_result.summary.to_dict()
```

`tracks` 是处理完整个输入序列后、统一发布于本批最终融合时刻的确定性快照，不是每条观测的
中间快照。`summary` 显式给出输入/接受/未接受/重复观测数、创建/更新数量、受影响航迹、历史
重放数、origin 重放数、状态缓存命中/未命中、终结重放数和被合并的更新重放数。空批次返回
当前航迹快照；`ingest_many()` 保持先按 arrival 排序的兼容语义并改用该批处理实现。

2026-07-14 验证包含 6 个无随机 seed 的构造测试：逐条/批量数值等价、乱序 OOSM、relay
重复 source、radar/lidar/acoustic 跨模态、fixed-lag 检查点边界和确定性重放性能。5 航迹、
15 条同帧观测中，历史重放由 95 次降至 24 次，减少 74.7%，状态与 covariance 在
`1e-9` 绝对容差内等价。对已有 M5N2 seed-001 baseline 的前 40 帧、786 条持久化观测做
D1-only 重放，逐条为 18.05 s/1267 次重放，批处理为 5.70 s/351 次重放，约 3.17 倍加速，
状态与 covariance 最大绝对差均为 0。D1 全量 `98 passed`。

这些证据关闭 D1-owned 的批量 API 与最少重放实现缺口，但 main/runtime 尚未改用该接口，
完整 245/248 帧控制循环、多 seed 增益和 100 ms 预算仍是系统 P1 验收项。

## 可扩展三维扫描融合入口（2026-07-20）

`Scalable3DFusionAdapter` 是面向 `scalable_3d_simulation` 在线总线的 D1-owned 入口。它以
鸭子类型消费 `OnlineSensorBatch` 或同合同 `SensorMeasurement` 扫描，不导入 main-owned
模块；递归拒绝 truth/actor/object/entity/target ID 和 offline truth sidecar。雷达输入
`[range, azimuth, elevation]` 在 canonical 合同中保留一个补零径向速度和对应方差，但同时
标记 `radial_velocity_observed=False`；滤波量测模型只消费前三维，补零值不进入 EKF 更新。
位置 covariance 通过解析 Jacobian 传播，速度以零均值、各轴方差 `25 m2/s2` 的独立高斯
先验起始，位置-速度交叉块为零。原始 `3x3` 球坐标 covariance、
`measurement_timestamp`、`arrival_timestamp`、sensor position 和匿名 observation lineage
均被保留。

新 `process_scan_batch()` 与旧 `process_batch()` 语义不同。旧入口继续保证逐条处理等价，供
2v2、5v5、M5N2 回归使用；新入口先针对扫描前航迹和整扫描点迹构造三维马氏代价矩阵，再用
一对一匈牙利匹配更新，每个未匹配雷达点迹都可独立 birth。这样不会再因同 observer scan 的
固定门限把多个可分点迹误当成对同一航迹的重复更新。数量完全由输入扫描长度决定。

main 新增的二维 `acoustic_bearing=[azimuth,elevation]` 映射为 `acoustic_3d` NED 弱约束；
它只能更新既有雷达航迹，不能单独 birth。输入 `soundprint_is_identity` 必须为 `False`，随后
转换为 `soundprint_category_only=True`；类别概率只进入 track metadata/类别提示，不进入几何
关联、航迹 ID 或 truth hint。`Scalable3DFusionAdapter` 禁止启用
`use_truth_hints_for_association`。

2026-07-20 使用 `scalable3d-world-v1`/`scalable3d-observation-v1`、seed 7，在
5/20/50/100/200 五档各运行两次无漏检雷达扫描，共 10 个 batch、750 条匿名雷达量测。首扫
birth 和次扫 update 均为 `5/5、20/20、50/50、100/100、200/200`；200 规模不再收缩为约
34 条，track ID 集保持不变。另有 2 目标、6 条量测的迟到扫描回归，2 条 OOSM 均在量测时刻
重放且航迹数保持 2；二维声学专项证明无雷达先验时 `0` birth、有先验时只更新 5 条航迹。
新增专项 `9 passed`，D1 全量 `120 passed`。一次本机非门限化探针中 200 点首扫约 0.108 s、
次扫约 0.392 s；该单次耗时不是实时性能验收。

当前 D1-owned 实现和合同回归已完成，但 main orchestrator 尚未接入此 adapter，D2 的原生
六维关联、漏检/虚警下的航迹确认与删除、多 seed dense crossing 的 recall/ID continuity、
长期 NIS/NEES 和实时预算仍需跨模块验收。本轮不涉及 AirSim runtime。

### 无多普勒速度稳定性修复（2026-07-20）

`Scalable3DFusionAdapter` 对位置-only radar 使用 3 自由度 NIS 门控，默认阈值为
`chi2_3(0.999)=16.26623619623813`。门外观测保留在合法 observation history 中供确定性 OOSM
重放，但不修改该时刻的预测状态；航迹 metadata 记录本次 replay 的创新数、实际滤波更新数、
拒绝数和匿名 observation ID。速度先验方差和门限均为显式可配置参数，不读取场景目标速度，
也不对状态做速度裁剪。

自动化验证使用 2026-07-20、radar-only、seed 17。200 条航迹连续 10 个 scan，共 2,000 条
匿名 radar measurement，数量和 ID 集始终保持 200，所有速度有限、covariance 保持 `6x6`；
末帧速度模长 median/P90/max 为 `3.87/6.43/8.54 m/s`，速度 covariance trace 为
`57.97/60.69/61.19`。50 条开发探针的修复前后速度分别为
`6.28/12.16/21.03 -> 3.99/6.12/9.69 m/s`，修复后 covariance trace 仍为
`58.22/60.43/60.90`，没有通过隐藏方差宣称精确速度。顺序/乱序 2 航迹、3 scan 回归在共同
发布时刻的 state/covariance 差不超过 `1e-9`，并保留原始双时间戳。专项 `13 passed`，D1
全量 `124 passed`。

当前限制是零均值先验会在短时间窗内收缩速度均值；其方差仍需至少 20 个未见 seed 的
NIS/NEES 与速度误差覆盖率标定。D2 会再次滤波 D1 六维状态，D2 速度均值和 D3 可达性/分配
数量必须由 main 用当前代码正式复测。本轮没有启动或修改 AirSim runtime。
