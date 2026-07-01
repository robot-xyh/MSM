# AirSim Offline Integration Plan

Detailed Chinese algorithm and implementation notes are maintained in `docs/ALGORITHM_AND_IMPLEMENTATION.md`. This file focuses only on offline AirSim log ingestion.

## Boundary

The D6 AirSim integration is offline-only. It must ingest AirSim recordings, simulator metadata, and offline algorithm logs after a run has ended. It must not connect the evaluator to live AirSim control APIs for real-time tasking, must not emit control commands, and must not generate fire-control parameters, damage logic, automated disposal actions, or authorization bypasses.

## Goal

Convert AirSim-derived logs into D6 records:

```text
TrackRecord
AssignmentRecord
EventRecord
TerminalRecord
```

Then compute:

```text
EpisodeMetrics
```

and generate CSV tables, Markdown reports, and PNG plots using `ReportGenerator`.

## Offline Data Inputs

Expected AirSim-side artifacts:

- AirSim recording files with timestamped pose/state records.
- Optional camera frame metadata and frame paths.
- Ground-truth object tracks exported from the simulator scenario configuration or post-run labels.
- Offline detection and tracking outputs produced by separate algorithms.
- Offline assignment logs produced by a planner under test.
- Offline degradation and safety event logs.
- Offline terminal registration logs, if a terminal camera or local association algorithm is evaluated.

No live API calls are required for metric generation.

## Timestamp Alignment

All records should be transformed to a common monotonic episode clock:

```text
episode_time = source_timestamp - episode_start_timestamp
```

Recommended validation checks:

- Timestamps are non-negative.
- All streams cover the expected episode interval.
- Frame timestamps can be matched to truth timestamps within a declared tolerance.
- Time units are documented as seconds.

## Schema Mapping

### Tracking

Map offline tracker rows to `TrackRecord`:

| Source field | D6 field |
|---|---|
| tracker timestamp | `timestamp` |
| global track identifier | `global_track_id` |
| evaluator truth label, if available | `truth_id` |
| estimated position | `position` |
| truth position, if available | `truth_position` |
| covariance trace or uncertainty proxy | `covariance_trace` |
| track lifecycle state | `track_state` |
| source stream name | `association_source` |

If truth labels are not available, D6 can still count false-alarm-like records if the source marks them, but detection probability and missed detection rate require truth opportunity counts.

### Assignment

Map offline planner snapshots to `AssignmentRecord`:

| Source field | D6 field |
|---|---|
| planner timestamp | `timestamp` |
| plan identifier | `plan_id` |
| plan version | `version` |
| resource identifier | `resource_id` |
| assigned global track | `global_track_id` |
| offline cost terms | `cost_breakdown` |
| logged authorization state | `authorization_state` |
| active/inactive flag | `active` |
| evaluator truth label, if available | `truth_id` |

D6 counts duplicate assignment and unassigned high-priority evaluated targets. It does not recommend new assignments.

### Degradation and Safety Events

Map post-run event logs to `EventRecord`:

| Event | D6 `event_type` |
|---|---|
| central coordinator failure | `central_failure` |
| degraded mode stable | `degraded_stable` |
| consensus round count | `consensus_rounds` with `value` |
| degraded task completed | `degraded_task_completed` |
| degraded task failed | `degraded_task_failed` |
| safety constraint violation | `constraint_violation` |
| human override/rejection | `human_override` or `human_rejection` |

### Terminal Registration

Map local camera or terminal association logs to `TerminalRecord`:

| Source field | D6 field |
|---|---|
| local timestamp | `timestamp` |
| resource/camera identifier | `resource_id` |
| assigned global target | `assigned_global_track_id` |
| local visual or terminal track | `local_track_id` |
| field-of-view or lock state | `decision_state` |
| ambiguity score | `ambiguity_score` |
| friend-overlap state | `friend_conflict_state` |
| evaluator expected global target | `expected_global_track_id` |
| evaluator correctness label | `association_correct` |

Recommended terminal `decision_state` values:

- `fov_entry`
- `locked`
- `observed`

## Truth Summary Contract

`MetricsCollector.compute_episode(..., truth_summary=...)` accepts:

```python
truth_summary = {
    "truth_timestamps": {
        "T00": [0.0, 1.0, 2.0],
        "T01": [0.0, 1.0, 2.0],
    },
    "high_threat_ids": ["T00"],
    "high_threat_by_timestamp": {
        0.0: ["T00"],
        5.0: ["T00"],
    },
    "scenario": {
        "name": "airsim_replay_case_001",
        "time_unit": "seconds",
    },
}
```

The `high_threat_*` labels are evaluator-side priority labels for metrics only. They must not be used by D6 to generate real-time tasking.

## Proposed Adapter Workflow

1. Export AirSim recording artifacts after the simulation run.
2. Convert AirSim timestamps to episode time.
3. Convert tracker, planner, event, and terminal logs to D6 dataclasses.
4. Build `truth_summary` from simulator labels.
5. Run `MetricsCollector.compute_episode`.
6. Repeat for all seeds or scenario variants.
7. Run `ReportGenerator` to write tables and charts.
8. Archive command line, input file checksums, and package versions.

## Validation Tests Before Use

- One AirSim recording with known truth timestamps converts to the expected `truth_summary`.
- A known false record increments `false_alarm_rate`.
- A deliberate track ID change increments `id_switch_count`.
- A deliberate duplicate planner snapshot increments `duplicate_assignment_count`.
- A synthetic central failure and stable marker produce the expected `failover_time`.
- A terminal FOV entry and lock marker produce the expected `time_to_terminal_lock`.
- Constraint and human override events appear in the safety counts.

## Non-Goals

- No live AirSim vehicle control.
- No online replanning.
- No target engagement recommendation.
- No fire-control, weapon-effect, or damage modeling.
- No automatic disposal or response action.
- No bypass of human authorization or review.
