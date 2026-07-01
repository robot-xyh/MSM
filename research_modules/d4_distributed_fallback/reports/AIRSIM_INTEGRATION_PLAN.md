# AirSim Offline Integration Plan

## Boundary

This plan is limited to offline AirSim log replay and synthetic evaluation. It does not add real vehicle control, live communications, hardware drivers, fire-control parameters, damage logic, automatic disposition, or authorization bypass.

## Integration Goal

Use AirSim as a source of recorded or replayed environment observations, then convert those observations into the same coarse `TrackSummary` and `ResourceSummary` objects used by the D4 simulator. The D4 package remains independent from AirSim APIs so unit tests and fallback experiments can run without AirSim installed.

## Proposed Adapter Layout

Future files, still inside this module:

- `adapters/airsim_log_adapter.py`: load exported AirSim replay JSON/CSV and produce coarse summaries.
- `adapters/summary_writer.py`: write summaries and fallback metrics to JSONL for later analysis.
- `scripts/run_airsim_log_replay.py`: offline replay CLI that feeds summaries into `run_failover_simulation`-style orchestration.
- `tests/test_airsim_log_adapter.py`: fixture-based parser tests using synthetic log snippets.

## Data Flow

```text
AirSim replay/export files
  -> offline adapter
  -> coarse cell quantization
  -> TrackSummary / ResourceSummary
  -> SimulatedNetwork + FailoverCoordinator
  -> CBBA fallback result
  -> JSON metrics and merge-review artifacts
```

## Adapter Inputs

The adapter should read exported files only:

- Simulation timestamp.
- Synthetic object or track identifier.
- Coarse position or cell source fields.
- Confidence proxy from simulator annotations when available.
- Simulated node identifier and availability metadata.

Precise coordinates should be quantized immediately into `coarse_cell`, and the D4 core should not retain high-resolution vehicle states.

## Adapter Outputs

`TrackSummary` mapping:

- `track_id`: synthetic replay object id.
- `coarse_cell`: quantized grid cell such as `x03_y07`.
- `age_s`: replay time minus observation time.
- `confidence_band`: derived from synthetic confidence thresholds.
- `source_count`: count of independent replay observations.
- `epoch`: replay episode epoch.

`ResourceSummary` mapping:

- `node_id`: simulated node id.
- `capability_class`: `observe`, `relay`, `secondary_c2`, `tethered_recon`, or `hold`.
- `availability_band`: offline availability category.
- `comm_band`: simulated communication quality category.
- `operator_hold`: manual test flag.
- `node_role`: `ground_backup`, `secondary_recon`, `cluster_representative`, or `interceptor`.
- `coordinator_only`: true for tethered secondary reconnaissance nodes that coordinate but should not own executable tasks.
- `coverage_cell`: coarse cell or region covered by the secondary node.
- `epoch`: replay episode epoch.

## Secondary Node Replay

For this phase, AirSim fixtures may include several high-altitude tethered
reconnaissance UAVs. The adapter should map them to
`node_role=secondary_recon`, `capability_class=tethered_recon`, and
`coordinator_only=True`.

Replay degradation order:

```text
center C2 available
  -> center outage: secondary reconnaissance node coordinates its coverage cell
  -> secondary node outage: cluster representative / fully distributed CBBA
```

Secondary nodes can publish scoped observation summaries for nearby interceptor
resources. These summaries remain offline records and do not create live
communication or control interfaces.

## Replay Procedure

1. Export or record AirSim scenario logs outside the D4 package.
2. Run the offline adapter against the exported log files.
3. Quantize observations into coarse cells.
4. Inject a center outage event at a configured replay timestamp.
5. Feed summaries into `FailoverCoordinator` and `CBBANegotiator`.
6. Save metrics JSON and transition logs.
7. Review merge artifacts before any claimed recovery to `normal`.

## Test Strategy

- Parser tests with tiny synthetic AirSim-like JSON/CSV fixtures.
- Quantization tests that verify precise fields are discarded after cell assignment.
- Replay smoke test with 3 to 5 simulated nodes.
- Merge recovery test where the center replay log intentionally lags the fallback log.

## Non-Goals

- No AirSim vehicle command publication.
- No online socket bridge.
- No real radio or hardware interface.
- No automatic handoff to a live operator station.
- No tactical or fire-control decision model.

## Initial Acceptance Criteria

- The D4 package still passes `pytest -q` without AirSim installed.
- A replay fixture can generate `TrackSummary` and `ResourceSummary` objects.
- Running a replay produces the same required metrics as the built-in simulation: takeover time, consensus rounds, assignment completion rate, conflict count, and communication overhead.
