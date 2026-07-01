# D6 Evaluation Metrics Plan

## 1. Scope and Safety Boundary

D6 is an offline evaluation and report-generation module. It consumes recorded or simulated logs and produces reproducible metrics, tables, and plots. It does not participate in real-time task decisions, does not produce fire-control parameters, does not model damage effects, does not automate engagement or disposal actions, and does not bypass human authorization.

All implementation artifacts for this worker are confined to:

```text
research_modules/d6_evaluation_metrics/
```

## 2. Engineering and Scientific Questions

The engineering problem is to provide a single offline metrics layer that can compare end-to-end system performance across sensing, tracking, assignment, degradation, terminal registration, and safety-constraint behavior.

The scientific problem is to avoid reducing system quality to a single success or hit-rate statistic. The evaluation must answer:

- How often are true objects detected, missed, or falsely reported?
- How accurate and identity-stable are tracks over time?
- How often does assignment create duplicate coverage or leave high-priority objects unassigned?
- How quickly and reliably does the system recover into a degraded operating mode after failures?
- How accurate and stable is terminal association after an object enters a local field of view?
- How frequently do safety constraints, human holds, or human overrides interrupt autonomy?

## 3. Metric Families and Formulas

### 3.1 Detection Metrics

Let `TP` be true detections, `FP` false detections, `FN` missed truth opportunities, `T` elapsed episode time, and `N_truth` the number of truth opportunities.

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / T
missed_detection_rate = FN / (TP + FN)
```

If `T <= 0`, false alarm rate is reported as `0.0`.

### 3.2 MOT and CLEAR MOT Metrics

For frame `t`, let `m_t` be the number of matched truth-track pairs, `d_{t,i}` be localization distance for matched pair `i`, `g_t` be the number of truth objects, `fn_t` missed detections, `fp_t` false positives, and `idsw_t` identity switches.

CLEAR MOT precision:

```text
MOTP = (sum_t sum_i d_{t,i}) / (sum_t m_t)
```

CLEAR MOT accuracy:

```text
MOTA = 1 - (sum_t (fn_t + fp_t + idsw_t)) / (sum_t g_t)
```

This module implements directly required primitives rather than a full tracker benchmark suite:

```text
track_rmse = sqrt(mean(||estimated_position - truth_position||^2))
track_continuity = matched_truth_timestamps / truth_timestamps
id_switch_count = count changes in assigned global_track_id for each truth_id over time
```

These are compatible with CLEAR MOT style accounting and can be cross-checked later against `py-motmetrics`, TrackEval, or Stone Soup outputs.

### 3.3 OSPA Metrics

For truth set `X = {x_1, ..., x_m}` and estimate set `Y = {y_1, ..., y_n}`, cutoff `c`, order `p`, and `m <= n`:

```text
OSPA_p,c(X,Y) =
  (1 / n * ( min_pi sum_{i=1..m} min(c, d(x_i, y_{pi(i)}))^p
             + c^p * (n - m) ))^(1/p)
```

If `m > n`, swap `X` and `Y`. OSPA decomposes total error into localization and cardinality penalties and is reported in the research report as a recommended extension point. The first implementation focuses on the requested scalar metrics and keeps OSPA as an explicit formula and future adapter target.

### 3.4 Assignment Metrics

For each assignment plan timestamp:

```text
duplicate_assignment_count = count targets assigned more than one distinct resource
unassigned_high_threat_count = count high-threat truth/track items without an active assignment
```

The module records counts only. It does not recommend or generate reassignment actions.

### 3.5 Degradation Metrics

Let `t_failure` be a central-failure event time and `t_stable` the next degraded-stable event time:

```text
failover_time = t_stable - t_failure
consensus_rounds = sum or mean of reported offline consensus round counts
degraded_completion_rate = completed_degraded_tasks / total_degraded_tasks
```

### 3.6 Terminal Registration Metrics

```text
terminal_association_accuracy = correct_terminal_associations / terminal_association_attempts
terminal_id_switch_count = changes in local_track_id for the same assigned_global_track_id
ambiguous_fov_event_count = count terminal ambiguity events
friend_overlap_hold_count = count friend-overlap hold events
time_to_terminal_lock = first terminal_lock time - first fov_entry time
```

### 3.7 Safety Metrics

```text
constraint_violation_count = count safety constraint violation events
human_override_count = count human override or human rejection events
```

Safety counts are treated as first-class outputs, not filtered away by success labels.

## 4. Experimental Factors and Response Variables

Experimental factors:

- Sensor detection probability and false-alarm intensity.
- Measurement noise level.
- Target count and target density.
- Occlusion/dropout probability.
- Track association ambiguity and ID-switch pressure.
- Assignment resource count and high-threat object ratio.
- Central failure time and degraded-mode stability delay.
- Communication consensus-round distribution.
- Terminal field-of-view ambiguity probability.
- Friend-overlap hold probability.
- Human override probability.

Response variables:

- Detection: `detection_probability`, `false_alarm_rate`, `missed_detection_rate`.
- Tracking: `track_rmse`, `track_continuity`, `id_switch_count`.
- Assignment: `duplicate_assignment_count`, `unassigned_high_threat_count`.
- Degradation: `failover_time`, `consensus_rounds`, `degraded_completion_rate`.
- Terminal: `terminal_association_accuracy`, `terminal_id_switch_count`, `ambiguous_fov_event_count`, `friend_overlap_hold_count`, `time_to_terminal_lock`.
- Safety: `constraint_violation_count`, `human_override_count`.

## 5. Statistical Methods

Batch experiments use 100 fixed random seeds by default.

For each metric, report:

- Per-episode value.
- Mean.
- Sample standard deviation.
- Standard error.
- Two-sided normal-approximation 95% confidence interval.
- Median.
- 5th and 95th percentiles.

Where assumptions are weak or distributions are strongly skewed, the report must flag the metric as requiring bootstrap or non-parametric review in a follow-up study.

## 6. Reproducibility Requirements

- Every synthetic episode records `episode_id`, `seed`, scenario parameters, and module version.
- Batch scripts accept explicit seed count and output directory.
- Outputs are deterministic for a fixed Python version, package set, and seed list.
- Raw simulated logs, per-episode CSV, summary CSV, Markdown report, and plots are written under the selected output directory.
- Report text states that logs are synthetic/offline and are not operational command outputs.
- Tests use deterministic fixtures and do not require network access.

## 7. Module Interfaces

### Data Classes

```text
TrackRecord
AssignmentRecord
EventRecord
TerminalRecord
EpisodeMetrics
```

### Core Classes

```text
MetricsCollector
  add_track(record)
  add_assignment(record)
  add_event(record)
  add_terminal(record)
  compute_episode(episode_id, seed, duration, truth_summary)

ReportGenerator
  write_episode_csv(episodes, path)
  write_summary_csv(episodes, path)
  write_markdown_report(episodes, path)
  write_plots(episodes, output_dir)
```

### Script Entry Point

```text
python3 scripts/run_batch_example.py --seeds 100 --output-dir outputs/example_batch
```

The script generates synthetic offline logs and a report. It does not connect to live simulators or vehicles.

## 8. Deliverables

- `PLAN.md`: this engineering and scientific plan.
- Python package implementing data models, metric collection, aggregation, and report generation.
- Unit tests covering required metrics and edge cases.
- Batch 100-random-seed synthetic example script.
- Generated example log/report workflow that outputs tables and charts.
- `EXPERIMENT_REPORT.md`: report template and example interpretation guidance.
- `AIRSIM_INTEGRATION_PLAN.md`: offline AirSim log ingestion plan that preserves the non-real-time boundary.

## 9. Acceptance Criteria

- All required metric names are present in `EpisodeMetrics`.
- Unit tests pass with `python3 -m pytest`.
- Batch example can run for 100 seeds and writes CSV, Markdown, and PNG charts.
- No files outside `research_modules/d6_evaluation_metrics/` are modified by D6.
- Documentation clearly states the offline-only boundary and safety exclusions.
