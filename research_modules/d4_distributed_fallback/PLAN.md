# D4 Distributed Fallback Plan

## Scope And Safety Boundary

This module is limited to research simulation, offline evaluation, and minimum continuity after a center C2 outage or a simulated active-degradation arbitration event. It exchanges coarse summaries through an in-memory simulated network only. It does not model real fire-control parameters, damage effects, live radio frequencies, hardware drivers, automatic disposition, or bypass of human authorization.

## Engineering And Scientific Problem

Centralized C2 normally owns the freshest fused tracks and assignment plan. After the center becomes unavailable, peer nodes may only have stale plans, local summaries, and intermittent peer communication. In addition, the center may remain alive while high uncertainty, stale assignment validity, or terminal visual disagreement makes the current plan locally unsafe to trust. The engineering question is how to preserve minimum continuity without creating duplicate assignments or conflicting local plans, while separating passive failover from active degradation.

Scientific questions:

- How quickly can a small peer group detect C2 failure and enter a safe degraded coordination mode?
- How many consensus rounds are needed for coarse task/resource summaries under packet loss and delay?
- What conflict rate remains when only summaries are exchanged?
- What communication overhead is introduced by bundle and winner-state diffusion?
- How should peer decisions be merged back when the center returns without immediate authority thrash?
- When the center is alive, how should D4 arbitrate among D1 localization uncertainty, D2 association risk, D3 assignment validity, and D5 terminal association disagreement?
- When should the system request center replanning or secondary-node assistance instead of immediately entering fully distributed CBBA?

## Passive Failover And Active Degradation

`passive_failover` is triggered by center unavailability:

- heartbeat failure timeout;
- peer quorum confirming outage;
- stale center epoch or unavailable assignment digest long enough to enter `failed`;
- secondary node failure after center outage, which then falls back to distributed CBBA.

`active_degradation` is triggered while the center is not failed:

- D1 reports increasing localization covariance or stale measurements;
- D2 reports high association ambiguity, ID switch, duplicate tracks, or low continuity;
- D3 reports stale/non-current assignment, low cost margin, or plan-version risk;
- D5 reports repeated `ambiguous`, `hold`, `reacquire`, persistent mismatch between terminal visual candidates and the assigned `global_track_id`, duplicate terminal locks, cross-view risk, or friend-conflict states.

The active path is conservative:

1. If D5 remains consistent and D1/D2/D3 risk is low, continue the center plan.
2. If D1/D2/D3 risk rises but D5 remains consistent, prefer center rolling replanning or secondary-node assistance.
3. If D5 disagreement persists across multiple frames, select a healthy secondary node covering the `coverage_cell`.
4. If no secondary node is available or the local region is partitioned, fall back to distributed CBBA/auction-style negotiation.
5. Friend/identity conflict only produces a hold/review decision in this offline module.
6. When communication summaries are available, secondary-node assistance requires a fresh data/video link record; stale secondary links are treated as unavailable.

## C2Health State Machine

States:

- `normal`: heartbeat and digest checks are current.
- `degraded`: heartbeat or digest quality is reduced, but continuity can still follow the center or a valid backup lease.
- `suspect`: heartbeat is stale, digests conflict, or peer observations disagree.
- `failed`: quorum or timeout indicates center unavailability.

Transitions:

```text
normal
  -> degraded : heartbeat jitter or digest age exceeds warning threshold
  -> suspect  : heartbeat is stale, digest conflict appears, or center messages are out of order

degraded
  -> normal  : heartbeat and assignment digest recover for the required stable window
  -> suspect : backup lease conflict, summary conflict, or degraded timer expires
  -> failed  : explicit fail quorum or hard timeout

suspect
  -> normal  : dual-track center and peer checks match for the stable window
  -> failed  : stale heartbeat exceeds failure timeout or peer quorum confirms outage
  -> degraded: valid backup lease exists but center recovery is not fully verified

failed
  -> degraded: peer quorum elects a fallback leader or backup lease remains valid
  -> normal  : center recovery passes dual-track merge and human-gated acceptance flag
```

Each transition records state, timestamp, reason, and epoch. The implementation treats `normal` as the only full-center mode. `degraded`, `suspect`, and `failed` only permit continuity-oriented planning.

## Summary Interfaces

`TrackSummary`:

- `track_id`: stable synthetic identifier used only in simulation.
- `coarse_cell`: coarse grid label, not precise coordinates.
- `age_s`: summary age in seconds.
- `confidence_band`: `low`, `medium`, or `high`.
- `source_count`: number of independent contributing sources.
- `epoch`: monotonic planning epoch.

`ResourceSummary`:

- `node_id`: simulated peer identifier.
- `capability_class`: coarse capability such as `observe`, `relay`, or `hold`.
- `availability_band`: `none`, `low`, `medium`, or `high`.
- `comm_band`: `poor`, `limited`, or `good`.
- `operator_hold`: when true, the resource cannot receive new fallback assignments.
- `node_role`: `ground_backup`, `secondary_recon`, `cluster_representative`, or `interceptor`.
- `coordinator_only`: when true, the node coordinates or observes but does not own executable fallback tasks.
- `coverage_cell`: coarse region covered by a secondary node.
- `heartbeat_timestamp_s`: latest secondary-node heartbeat time when available.
- `heartbeat_stale_after_s`: heartbeat age threshold used to mark a secondary node unavailable.
- `epoch`: monotonic planning epoch.

Active-degradation summaries:

- `TrackUncertaintySummary`: D1 localization uncertainty, covariance trace, measurement age, and coverage cell.
- `AssociationRiskSummary`: D2 ambiguity, ID switch count, duplicate track count, and continuity.
- `AssignmentValiditySummary`: D3 assigned track/resource, plan version, freshness, and cost margin.
- `TerminalAssociationSummary`: D5 terminal decision state, confidence, ambiguity, mismatch duration, duplicate terminal lock, cross-view risk, and friend-conflict flag.
- `ActiveDegradationDecision`: D4 output with mode, action, reason, target node, coverage cell, risk factors, and terminal consistency.
- `SecondaryNodeLifecycleSummary`: D4 secondary-node lifecycle output with `heartbeat`, `lease_epoch`, `coverage_cell`, `video_cue_freshness_s`, `link_stale`, and final `secondary_available`.
- `D4DecisionRecord`: adapter output that can be converted to D6 `EventRecord` kwargs. Metadata includes `degradation_mode`, `selected_coordinator`, `coverage_cell`, `trigger_reason`, `trigger_timestamp`, `decision_timestamp`, and `review_label`.

Decision metrics:

- `d4_action`
- `degradation_mode`
- `target_node_id`
- `risk_factors`
- `terminal_consistent`
- `failover_time`
- `secondary_selected_rate`
- `distributed_conflict_count`

Active-degradation debounce and hysteresis configuration:

- `mismatch_frame_limit`: consecutive terminal mismatch frames required before persistent disagreement can escalate.
- `risk_window_size` and `risk_window_threshold`: rolling risk window used to debounce persistent terminal disagreement.
- `min_dwell_s`: minimum time to remain in a degraded decision before release.
- `release_consecutive_consistent_frames`: consecutive low-risk, terminal-consistent frames required before returning to `continue_center`.

Enhanced communication summary:

- `CommunicationSummary.source_node_id`: message producer.
- `CommunicationSummary.target_node_id`: intended consumer.
- `CommunicationSummary.relay_node_id`: optional relay, usually a secondary node.
- `CommunicationSummary.link_type`: `c2_direct`, `secondary_relay`, `interceptor_peer`, or `video_cue`.
- `CommunicationSummary.sent_timestamp` / `received_timestamp`: used to compute latency.
- `CommunicationSummary.payload_kind`: `track`, `bbox`, `video_metadata`, `assignment`, `terminal_association`, `bid`, `resource_summary`, or `health`.
- `CommunicationSummary.stale_after_s`: freshness deadline used by active-degradation arbitration.

`BidState`:

- `task_id`: synthetic continuity task identifier.
- `bidder`: node identifier.
- `score`: normalized utility score, not a real-world effect estimate.
- `constraints_hash`: digest of coarse local constraints.
- `epoch`: planning epoch.
- `round_id`: CBBA consensus round.

All summaries are coarse, versioned by epoch, and safe for offline simulation logs.

## CBBA Formulation

Let agents be \(i \in \mathcal{A}\), continuity tasks \(j \in \mathcal{T}\), and each agent's bundle \(b_i = [j_1, ..., j_k]\) with \(k \le L\). Each agent computes a local score:

\[
s_{ij} = w_c C_j + w_a A_i + w_q Q_{ij} - w_r R_{ij}
\]

where \(C_j\) is track confidence rank, \(A_i\) is resource availability rank, \(Q_{ij}\) is coarse capability match, and \(R_{ij}\) is an offline risk/constraint penalty. These are synthetic ranks only.

Marginal gain for inserting task \(j\) into bundle \(b_i\):

\[
\Delta_{ij}(b_i) = S_i(b_i \oplus j) - S_i(b_i)
\]

The local bid is:

\[
y_{ij} = \max(0, \Delta_{ij})
\]

Winner and bid vectors:

\[
z_{ij} = \arg\max_{a \in \mathcal{A}} (y_{aj}, -\text{tie\_rank}(a))
\]

\[
y^*_{ij} = \max_{a \in \mathcal{A}} y_{aj}
\]

Conflict resolution uses deterministic tie-breaking by higher score, then lower node id, then lower constraints hash. When a node loses a winner entry for a task in its bundle, it releases that task and all later bundle entries, then rebuilds bids from remaining feasible tasks.

Convergence expectation for this simulator: with a connected peer graph, deterministic tie-breaking, bounded bundle length \(L\), static task summaries, and reliable eventual message delivery, winner vectors converge in \(O(D \cdot |\mathcal{T}|)\) consensus propagation rounds, where \(D\) is network diameter. Packet loss and delay increase wall-clock takeover time but not the deterministic fixed point if enough rounds are allowed.

Communication overhead per consensus round is:

\[
O(|E| \cdot |\mathcal{T}|)
\]

for peer edges \(E\), because each message carries compact winner/bid state per known task. With \(N\) nodes, a full mesh has \(O(N^2 |\mathcal{T}|)\) per round; sparse relay graphs reduce bytes but may increase diameter and rounds.

## Center Recovery Dual-Track Merge

When center updates resume, fallback plans are not discarded immediately.

Dual-track merge stages:

1. Keep center track/assignment log and fallback peer log side by side.
2. Compare epochs, summary digests, and assignment ownership.
3. Mark exact matches as `accepted`.
4. Mark center-only or peer-only assignments as `review`.
5. Mark duplicate owners or stale summaries as `conflict`.
6. Return to `normal` only when the merged log has no unresolved conflicts and the caller supplies a human-gated acceptance flag.

This prevents immediate dual-master behavior after a short center recovery.

## Takeover Priority

1. Valid ground backup lease.
2. High-altitude tethered reconnaissance UAV acting as a secondary regional node.
3. Resource-cluster representative elected by deterministic peer priority.
4. CBBA fallback negotiation for continuity-only assignments.
5. If no quorum or convergence, choose `hold`, `continue_observe`, or `return_safe` placeholders for offline evaluation.

## Secondary Reconnaissance Node Assumption

This phase assumes several high-altitude tethered reconnaissance UAVs can act
as secondary regional nodes. They are modeled as `ResourceSummary` records with
`node_role=secondary_recon`, optional `coverage_cell`, and usually
`coordinator_only=True`.

Degraded hierarchy:

```text
center C2 available
  -> center C2 failed: secondary reconnaissance node coordinates its local area
  -> secondary node unavailable: cluster representative / fully distributed CBBA
  -> no convergence: hold / continue-observe placeholder for offline evaluation
```

Secondary nodes do not own center-level authority. They keep continuity,
forward local summaries, and provide scoped coordination until the center
recovers and dual-track merge is accepted.

## Simulation Scenarios

Primary scenario:

- Simulated node/resource count follows the supplied `ResourceSummary[]` length
  or the CLI `--drone-count` value; 2v2 and 5v5 are retained only as baseline
  tests.
- Center heartbeat is normal until `t = 30s`.
- Center then fails.
- Simulated peer network applies 0.1 to 0.5 second delivery delay.
- Packet loss is configurable.
- Nodes exchange summaries and CBBA winner states through in-memory queues.

Fault variants:

- Heartbeat stale transition from `normal` to `suspect` to `failed`.
- Packet loss during CBBA rounds.
- Summary replay with stale epoch.
- Duplicate tentative assignment conflict.
- Center recovers with incomplete log and requires degraded review.

Metrics:

- Takeover time.
- Consensus rounds.
- Assignment completion rate.
- Conflict count.
- Communication overhead in message count and estimated bytes.

## Code Interfaces

Python package:

- `models.py`: enums and dataclasses for health state, summaries, bids, assignments, metrics, and messages.
- `network.py`: in-memory simulated network with delay and packet loss.
- `cbba.py`: simplified CBBA negotiator.
- `coordinator.py`: `FailoverCoordinator` with health detection, leader election, degraded planning, and merge recovery.
- `active_degradation.py`: `ActiveDegradationArbiter` with passive/active degradation decision rules.
- `simulation.py`: scenario runner and metric aggregation.

CLI:

- `scripts/run_failover_simulation.py`: runs the default 5-node center-failure scenario and prints metrics JSON.

Tests:

- Health-state transitions.
- CBBA convergence and duplicate-owner conflict resolution.
- Failover coordinator takeover and center recovery merge.
- Active degradation arbitration for consistent, risky, terminal-disagreement, secondary-node, and distributed fallback cases.
- Simulated packet loss/delay metrics smoke test.

## Deliverables

- `PLAN.md`: this plan.
- Python implementation under `d4_distributed_fallback/`.
- Unit tests under `tests/`.
- Simulation script under `scripts/`.
- Experiment report under `reports/EXPERIMENT_REPORT.md`.
- AirSim integration plan under `reports/AIRSIM_INTEGRATION_PLAN.md`, limited to offline adapter interfaces and synthetic logs.

## P1 Gap Status

Completed in D4 module:

- Secondary node lifecycle fields and summaries: heartbeat, lease epoch, coverage cell, video cue freshness, stale link state, and final `secondary_available`.
- Active-degradation debounce and hysteresis configuration: dwell, release condition, consecutive mismatch frame threshold, and rolling risk window threshold.
- D6-compatible decision event output from `D4ArbitrationAdapter`.
- Tests for lifecycle availability, dwell/release behavior, windowed mismatch debounce, and D6 metadata fields.

Intentionally unchanged:

- The local lightweight CBBA remains the only distributed fallback baseline.
- MIT CBBA, CA-CBBA, standalone auction, and contract-net integrations were not added.

Remaining outside this D4 module:

- Main/integrated runtime must call `D4ArbitrationAdapter` during real episodes and write the returned event kwargs into the D6 collector.
