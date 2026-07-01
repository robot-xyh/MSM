# D2 Data Association Plan

## Scope and Safety Boundary

This module is limited to research simulation and offline evaluation of multi-target tracking identity continuity. It does not implement real fire-control parameters, damage effects, hardware drivers, live flight-control loops, automatic disposal, or bypass of human authorization.

## Engineering and Scientific Problem

Dense multi-target tracking can preserve geometric accuracy while losing identity consistency. The D2 problem is to reduce ID switches when 2-6 targets cross, fly in close formation, undergo short occlusions, produce missed detections, or appear with false alarms.

Engineering goals:

- Provide a common `DataAssociator` interface for GNN/Hungarian, JPDA, and MHT-compatible implementations.
- Use NumPy/SciPy only for the runnable fallback path.
- Keep FilterPy and Stone Soup as future compatibility/integration targets, not runtime requirements.
- Manage track lifecycle with a deterministic state machine.
- Force metric logging for `id_switch_count`, `track_continuity`, and `duplicate_assignment_count`.

Scientific goals:

- Compare hard assignment, soft association, and delayed-hypothesis association under controlled synthetic scenarios.
- Expose ambiguity and gate rejection logs so failure modes can be explained.
- Produce offline metrics: IDSW, RMSE, runtime, continuity, duplicate assignments, and confusion matrix.

## Mahalanobis Gating `d^2`

For each track `i` and detection `j`, the predicted measurement is:

```text
z_hat_i = H x_i
S_i = H P_i H^T + R_j
r_ij = z_j - z_hat_i
d_ij^2 = r_ij^T S_i^-1 r_ij
```

A pair is valid only if `d_ij^2 <= gate_threshold`. The default gate threshold is `9.21`, approximately a 99% chi-square gate for a 2D position measurement. Invalid pairs are represented by a large finite cost and recorded with rejection reason `mahalanobis_gate`.

## GNN/Hungarian Cost Matrix

GNN is the default engineering baseline. It builds a rectangular cost matrix:

```text
C_ij = d_ij^2 + appearance_penalty + continuity_penalty
```

The runnable fallback uses motion-only position measurements and a small continuity preference. SciPy `linear_sum_assignment` solves the minimum-cost assignment. Matched pairs above the gate are rejected after assignment, and unassigned detections can spawn tentative tracks.

Complexity:

- Cost construction: `O(NM)` for `N` tracks and `M` detections.
- Hungarian solve: `O(max(N, M)^3)`.
- Recommended for nominal 2-6 target simulations and low ambiguity frames.

## JPDA Probability Model

JPDA is used when association ambiguity increases. The simplified runnable version enumerates valid one-to-one joint hypotheses for small target counts and computes hypothesis likelihood:

```text
L(H) = product over matched pairs exp(-0.5 d_ij^2)
       * Pd^(number_of_matches)
       * (1 - Pd)^(number_of_missed_tracks)
       * clutter_density^(number_of_unmatched_detections)
```

Hypothesis probabilities are normalized:

```text
P(H_k | Z) = L(H_k) / sum_l L(H_l)
```

Marginal association probabilities are:

```text
beta_ij = sum over H containing pair (i, j) P(H | Z)
```

The simplified updater emits the highest marginal non-conflicting associations above `min_marginal_probability`, plus per-track probability logs. It is not a full production JPDA filter, but it is executable and suitable for offline comparison.

Complexity:

- Worst-case joint hypothesis enumeration grows combinatorially with target/detection count.
- This module caps enumeration for small research runs and reports truncation/ambiguity metadata.
- Upgrade trigger: multiple valid detections per track, mean candidate count above `1.5`, or high GNN ambiguity score.

## MHT Interface

MHT keeps delayed association hypotheses across frames. The runnable fallback maintains a bounded list of global branches:

```text
branch = (score, assignments, misses, history)
```

For each frame it expands GNN-like valid assignments, retains `max_hypotheses`, prunes by `max_history`, and returns the current best branch. This is a research placeholder and an interface-compatible path for future Stone Soup MHT integration.

Complexity:

- Without pruning, branching is exponential over time.
- With pruning, complexity is bounded by `O(K * B)` per frame, where `K` is retained hypotheses and `B` is generated branch count.
- Upgrade trigger: sustained occlusion, repeated GNN/JPDA ambiguity, or conflicting identity evidence across multiple frames.

## Track State Machine

Tracks move through:

```text
tentative -> confirmed -> engageable -> lost -> dropped
```

State meaning:

- `tentative`: new track with insufficient hits.
- `confirmed`: enough observations for stable display/fusion.
- `engageable`: high-quality research track eligible for downstream offline assignment experiments. This is not an authorization or fire-control state.
- `lost`: temporarily unmatched but retained by prediction.
- `dropped`: aged out and removed from active tracking.

Transitions are driven by hit streak, total hits, misses, covariance trace, and identity confidence. Every transition is logged with timestamp and reason.

## Simulation Scenarios

The simulation suite covers:

- 2-target crossing with noisy detections.
- 4-6 target close formation with small spacing.
- Short occlusion window with missing detections.
- Random missed detections.
- False alarms/clutter.

Each scenario runs GNN, JPDA, and MHT and records:

- `id_switch_count`
- `track_continuity`
- `duplicate_assignment_count`
- RMSE
- runtime
- truth-to-track confusion matrix

## Interfaces

Primary data classes:

- `Detection`: measurement, covariance, optional `truth_id`, timestamp, and detection id.
- `GlobalTrack`: global track id, state vector, covariance, lifecycle state, counters, history, and optional current truth label for evaluation.
- `AssociationResult`: matched pairs, unmatched tracks, unmatched detections, costs, ambiguity score, rejected-pair reasons, and algorithm metadata.
- `AssociationLogEntry`: per-frame logging for offline analysis.

Primary classes:

- `DataAssociator`: abstract base class.
- `GNNHungarianAssociator`: default hard-assignment baseline.
- `JPDAAssociator`: simplified executable soft-association version.
- `MHTAssociator`: bounded hypothesis placeholder with MHT-compatible interface.
- `Tracker`: prediction, update, track creation, pruning, and metric logging.
- `MetricsRecorder`: identity switches, continuity, duplicate assignments, RMSE, confusion matrix, and runtime aggregation.

## Deliverables

- `PLAN.md`: this plan and safety boundary.
- Python package with data classes, associators, tracker, metrics, and simulation utilities.
- Unit tests runnable with pytest without FilterPy, Stone Soup, OR-Tools, or hardware dependencies.
- Simulation CLI comparing GNN, JPDA, and MHT on crossing, formation, occlusion, miss, and false-alarm cases.
- Experiment report template/output documenting observed IDSW/RMSE/runtime tradeoffs.
- AirSim integration plan for offline log ingestion only.
