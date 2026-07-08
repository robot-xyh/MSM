# D1 Sensor Fusion Module

Offline research module for radar, acoustic, EO, and optional synthetic lidar heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

## Scope

This directory is limited to simulation and offline evaluation. It does not include real fire-control parameters, damage logic, hardware drivers, real vehicle control, automatic action, or bypass of human authorization.

## Runtime

The implementation uses NumPy/SciPy-compatible fallback code and does not require FilterPy or Stone Soup. Optional placeholders are available in `d1_sensor_fusion.compat`.

## Ownership

D1 owns this module and `subagent_reviews/D1_*`. Under the strict project workflow, main dispatches D1 tasks, D1 edits and tests only its owned paths, and main performs integration summary. D1 module changes must check whether README, PLAN, GAP, and review files need matching updates.

As of the 2026-07-07 runtime/D3/D4/D5 P1 review, D1 has no new P0 blocker. D1 continues to provide `GlobalTrack[]` and `TrackUncertaintySummary[]` evidence only; it does not generate `AssignmentPlan` versions, decide active degradation, rewrite `global_track_id`, or modify D7 PN/PNG control behavior.

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

## Main Interfaces

- `SensorObservation`: canonical sensor input with `measurement_timestamp`, `arrival_timestamp`, optional cross-node communication metadata, and covariance.
- `FusionAdapter`: EKF fusion and fixed-lag replay. Required methods are `predict_track()`, `update_at_measurement_time()`, `compensate_latency()`, `_bucket()`, and `track_uncertainty_summaries()`.
- `GlobalTrack`: output state `[px, py, pz, vx, vy, vz]`, covariance, timestamp, source support, identity likelihood, and quality level.
- `TrackUncertaintySummary`: compact quality export with track IDs, covariance trace/a95, level, measurement age, source support, coverage cell, and timing fields.
- `RadarCovarianceConfig`: optional distance-dependent radar covariance parameters. Defaults preserve the original noise model.

## Cross-Node Metadata

`SensorObservation` accepts optional communication fields directly or through `metadata`: `source_node_id`, `target_node_id`, `relay_node_id`, `link_type`, `sent_timestamp`, `received_timestamp`, `payload_kind`, `stale_after_s`, and `source_support`. `FusionAdapter` preserves the latest observation communication metadata in `GlobalTrack.metadata` and publishes modality counts in `GlobalTrack.source_support`. It also suppresses repeated updates from the same source/sequence/payload lineage, including relay duplicates.

## Replay Schema And CSV

D1 replay schema v1 is `d1.sensor_observation.v1`. New `sensor_observations.jsonl` and Blocks replay records should include `schema_version` plus `observation_id`, `sensor_id`, `modality`, `measurement_timestamp`, `arrival_timestamp`, `frame_id`, `measurement`, and `covariance`. Existing `blocks_sensor_observations.jsonl` files without an explicit version are still accepted as legacy records when the required observation fields are present; the parser annotates them as `legacy.blocks_sensor_observations` in metadata.

Minimal CSV replay is available through `read_sensor_observations_csv()` and `replay_sensor_observations_csv()`. CSV cells for `measurement` and `covariance` should contain JSON arrays; `metadata`, `communication`, and `source_support` should contain JSON objects. CSV support is for replay/audit convenience and does not replace JSONL as the primary runtime log format.

## Quality And Latency Audit Exports

`FusionAdapter.latency_audit_summary()` exports `observation_count`, `max_delay_s`, `mean_delay_s`, `replay_count`, `oosm_observation_count`, `stale_observation_count`, `stale_or_oosm_observation_count`, duplicate count, and maximum replay history size. OOSM means an arriving observation's `measurement_timestamp` is older than the fusion time already processed; stale means it is stale at processing time or its arrival delay exceeds `stale_after_s` when that budget is supplied.

`FusionAdapter.region_quality_summaries()` derives lightweight `FusionQualityRegionSummary[]` records from `TrackUncertaintySummary[]`, grouped by `coverage_cell`. The region summary aggregates track count, a95, measurement age, handover readiness, source support, source gaps, and stale-track count for D4/D6 quality consumption while preserving the existing per-track `TrackUncertaintySummary` contract.

Video/image streams are represented only by derived observations such as bounding boxes, camera metadata, timestamps, and covariance. D1 does not require or store PNG frames.

Current remaining P1 work is limited to more real Blocks/CV fixture regressions, D6 long-run batch schema alignment, region time windows, covariance-growth windows, and real-sample regression. Replay schema v1, legacy JSONL compatibility, CSV replay, latency audit, region quality summaries, source de-dup, and Blocks JSONL replay are already implemented baselines.
