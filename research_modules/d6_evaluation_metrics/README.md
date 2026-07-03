# D6 Evaluation Metrics

Offline evaluation module for detection, tracking, assignment, degradation, terminal registration, communication-link, D7 guidance-gate, and safety metrics.

## Documentation

- Detailed Chinese algorithm and implementation notes: `docs/ALGORITHM_AND_IMPLEMENTATION.md`
- Document index: `docs/README.md`
- Chinese experiment report with generated figures: `EXPERIMENT_REPORT.md`
- Offline AirSim ingestion plan: `AIRSIM_INTEGRATION_PLAN.md`

The detailed notes now include the offline metric contract for D4 active degradation evaluation: passive vs active degradation counts, trigger-source metadata, coordinator selection fields, and before/after-window deltas for ID switches and assignment conflicts.

D6 also accepts optional `LinkRecord` entries or equivalent `EventRecord.metadata`
for cross-node communication evaluation. Supported derived metrics include
`cross_node_latency_ms`, `message_drop_rate`, `out_of_order_count`,
`stale_track_update_count`, `video_metadata_delivery_rate`,
`bbox_delivery_rate`, and `consensus_latency_s`.

For D5/D7 integration, D6 consumes metadata-only video evidence and D7 gate
events. PNG frames are not required for metric computation when logs preserve
bounding boxes, camera intrinsics/extrinsics, timestamps, assigned global track
IDs, object labels, and gate outcomes. D7 events may report `guidance_law`,
`terminal_switch_reject_reason`, `camera_quality_gate_pass`,
`los_quality_gate_pass`, `maneuver_margin_gate_pass`, and
`terminal_switch_allowed`. Supported D7 guidance metrics include
`camera_quality_gate_pass_rate`, `los_quality_gate_pass_rate`,
`maneuver_margin_gate_pass_rate`, `terminal_switch_allowed_rate`,
`terminal_switch_reject_count`, and intercept outcome counts.

## AirSim Blocks Replay Inputs

D6 can directly ingest the main runtime's metadata-only Blocks replay files:

- `blocks_frames.jsonl` for truth objects, camera metadata, image status,
  detection boxes, local visual IDs, object labels, and timestamps.
- `blocks_sensor_observations.jsonl` for D1 replay observations and optional
  communication metadata such as source/target node, timestamps, sequence ID,
  payload kind, delivery state, and stale threshold.

Use `load_blocks_replay_jsonl()` for offline evaluation. It reads files from
disk only; it does not import AirSim, connect to a simulator, or call vehicle
control APIs.

```python
from d6_evaluation_metrics import load_blocks_replay_jsonl

collector, truth_summary = load_blocks_replay_jsonl(
    "research_modules/airsim_runtime/outputs/cv5v5_verify_001/blocks_frames.jsonl",
    "research_modules/airsim_runtime/outputs/cv5v5_verify_001/blocks_sensor_observations.jsonl",
)
metrics = collector.compute_episode("cv5v5_verify_001", truth_summary=truth_summary)
```

## Boundary

This module only evaluates recorded or synthetic logs. It does not participate in real-time decisions, does not emit control commands, does not provide fire-control parameters, does not model damage, does not automate disposal actions, and does not bypass human authorization.

## Run Tests

From the repository root:

```bash
python3 -m pytest research_modules/d6_evaluation_metrics/tests
```

## Run 100-Seed Example

From the repository root:

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

Default outputs:

```text
research_modules/d6_evaluation_metrics/outputs/example_batch/
  episode_metrics.csv
  summary_metrics.csv
  batch_report.md
  logs/*.jsonl
  plots/*.png
```

## Core API

```python
from d6_evaluation_metrics import MetricsCollector, ReportGenerator
from d6_evaluation_metrics import LinkRecord
from d6_evaluation_metrics import TrackRecord, AssignmentRecord, EventRecord, TerminalRecord

collector = MetricsCollector()
collector.add_track(TrackRecord(timestamp=0.0, global_track_id="G0", truth_id="T0"))
collector.add_link(
    LinkRecord(
        timestamp=0.1,
        source_node_id="interceptor_01",
        target_node_id="center",
        payload_kind="track",
        sent_timestamp=0.0,
        received_timestamp=0.1,
    )
)
metrics = collector.compute_episode(episode_id="example", duration=10.0)
```

The package is intentionally lightweight and uses only Python standard library, NumPy, matplotlib, and pytest for tests.
