# D1 Sensor Fusion Module

Offline research module for radar, acoustic, EO, and optional synthetic lidar heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

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

## 2026-07-10 AirSim 2v2 Contract Audit

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

## 2026-07-11 Truth-Isolated 5v5 Runtime Evidence

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

As of 2026-07-11, the D1-owned writer/provenance contract, expected-latency/OOSM health fields,
fixed coverage-cell windows, covariance-growth windows, truth-free two-target replay, and durable
Blocks/CV-shaped JSONL/CSV fixtures are implemented. Remaining P1 work is main/shared adoption of
the governed writer, completion of the episode-bus D1 governance schema beyond the current short
smoke, multi-seed threshold calibration, broader camera/bbox fixtures, D6 long-run batch schema alignment,
IMM/model-set comparison, scene-adaptive covariance rules, and Track-to-Track fusion research.
Replay schema v1, legacy JSONL compatibility,
covariance-required CSV replay, raw and fusion latency audit, sensor-health summaries, timestamp
uncertainty, covariance floor/ceiling limiting, covariance scale reason passthrough, region quality
summaries, region window helpers, covariance-growth helpers, recon cue summaries, source de-dup,
nested EO camera metadata replay, real CV field normalization, dry-run fixture schema checks, and
Blocks JSONL replay are already implemented baselines.
