# D6 Evaluation Metrics

Offline evaluation module for detection, tracking, assignment, degradation, terminal registration, and safety metrics.

## Documentation

- Detailed Chinese algorithm and implementation notes: `docs/ALGORITHM_AND_IMPLEMENTATION.md`
- Document index: `docs/README.md`
- Chinese experiment report with generated figures: `EXPERIMENT_REPORT.md`
- Offline AirSim ingestion plan: `AIRSIM_INTEGRATION_PLAN.md`

The detailed notes now include the offline metric contract for D4 active degradation evaluation: passive vs active degradation counts, trigger-source metadata, coordinator selection fields, and before/after-window deltas for ID switches and assignment conflicts.

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
from d6_evaluation_metrics import TrackRecord, AssignmentRecord, EventRecord, TerminalRecord

collector = MetricsCollector()
collector.add_track(TrackRecord(timestamp=0.0, global_track_id="G0", truth_id="T0"))
metrics = collector.compute_episode(episode_id="example", duration=10.0)
```

The package is intentionally lightweight and uses only Python standard library, NumPy, matplotlib, and pytest for tests.
