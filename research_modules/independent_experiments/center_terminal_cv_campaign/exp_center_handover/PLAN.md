# Center Handover Experiment Plan

## Completed on 2026-08-16

- [x] Consume shared `SourceCueRecord` and `LocalVisualTrackRecord` contracts.
- [x] Propagate source state and covariance from measurement time to image time.
- [x] Implement NED/body/gimbal/camera projection and image covariance ellipses.
- [x] Gate by arrival time, record `valid_until`, ten-pixel recognition,
  Mahalanobis distance, and motion continuity.
- [x] Add Hungarian one-to-one assignment with explicit dummy unmatched choices.
- [x] Require two selections in a three-frame window before confirmation.
- [x] Preserve center-missed targets as anonymous unregistered candidates.
- [x] Add a pure-PyTorch sparse graph scorer, isolated training/validation seeds,
  model save/load, and geometry fail-closed behavior.
- [x] Add injectable AirSim detection/camera-info collection without Blocks
  lifecycle control.
- [x] Add offline replay/main `run(...)` API, fixed metrics/report paths,
  auditable JSONL records, two-dimensional figures, and a Chinese report.
- [x] Cover projection, covariance, 9.99/10-pixel boundary, dummy assignment,
  false-source rejection, missed-target isolation, two-of-three confirmation,
  truth leakage, and graph-gate invariants with tests.
- [x] Preserve `unregistered_candidate_count` as a backward-compatible
  camera-local-track count and add target-aware offline breakdown metrics.
- [x] Add the shared `center-terminal-gnn-replay-v1` read-only manifest adapter
  with relative paths and SHA256 verification for center-owned inputs only.
- [x] Reconstruct the actual center-camera set from saved anonymous local
  tracks, use cross-view calibration only as the common intrinsics template,
  and reject cross-frame pose changes. `resource_count` is not treated as the
  center-camera count.
- [x] Extend sparse-GNN synthetic training to 20/40 targets and three or more
  frames so motion-residual features are populated from prior observations.
- [x] Add an explicit CPU training CLI, disjoint/held-out seed enforcement, and
  a frozen model sidecar containing configuration, feature strategy, validation
  metrics, model SHA256, and metadata SHA256.
- [x] Fail closed on missing/old/tampered models, replay schema/hash mismatch,
  training/validation seed overlap, AirSim seed `20260816` use, and online
  actor/truth identity leakage.
- [x] Extend the public AirSim runner default observation schedule from three
  frames to five frames at 0.2--0.6 seconds without changing the rolling
  two-of-three confirmation rule or any recognition, geometry, motion, or
  identity gate.
- [x] Validate the five-frame schedule once in real AirSim with the saved
  `airsim_n20_formal_v3_20260816` output.
- [x] Train and freeze the optional center-handover GNN using only synthetic
  20-target and 40-target data with mutually exclusive training/validation
  seeds, while reserving AirSim seed `20260816` for held-out replay testing.
- [x] Compare geometry and frozen-GNN backends on identical saved `n20_m8`,
  `n20_m30`, and `n40_m50` observations with five timing repetitions per
  center-method case.

## Evidence

- Scenario: deterministic offline fixture, 20 targets, seed `20260816`, three
  frames at 0.2/0.3/0.4 seconds.
- Source condition: 16 correct cues and four incorrect cues, corresponding to
  80% precision and 80% recall.
- Result: 16 correct confirmed bindings, zero false bindings, four unregistered
  center-missed targets, and zero online truth leakage.
- Acceptance: geometry baseline met binding precision >=0.95, binding recall
  >=0.85, false-source rejection >=0.90, and zero missed-target wrong binding.
- AirSim scenario: one formal 20-target ComputerVision run, seed `20260816`,
  three frames, 20 terminal cameras, and `simGetDetections` metadata.
- AirSim result: all 16 correct source cues bound to their intended targets; all
  four false cues were rejected; false binding and truth leakage were zero.
- Metric audit: the final frame had 52 camera-local tracks. The 36 unmatched
  tracks comprised 23 redundant views of 13 registered targets and 13 views of
  the four center-missed targets. This is a local-track count, not 36 missed
  targets.
- Saved-output comparison: the v2 run ended at 15/16 because `SRC-009` /
  `TGT-012` on `Terminal_CV_05` selected
  `LCL-Terminal_CV_05-0003` at 0.2 seconds, confirmed the same pair at 0.3
  seconds, and had no target detection at 0.4 seconds. This was an observation
  shortage at the final sample, not a relaxed or failed geometry match.
- Five-frame AirSim rerun: seed `20260816` processed five frames, correctly
  bound all 16 correct source cues, produced zero false bindings, and rejected
  all four false source cues. The final frame contained 48 recognized local
  tracks; 16 were bound and 32 were unmatched.
- Unmatched-track audit: the 32 unmatched local tracks comprised 20 redundant
  observations of 12 already registered targets and 12 observations of the four
  center-missed targets. The count is per camera-local track, not per physical
  target. Correct-source unbound observations and unknown labels were both zero.
- Evidence limit: v3 is one rerun of the same seed. Variation between the first,
  v2, and v3 runs remains evidence of runtime detection fluctuation, not a
  multi-seed performance distribution.
- Scale evidence: one real 20-target/30-resource run produced 14/16 correct
  bindings and zero wrong binding. One real 40-target/50-resource run produced
  31 correct bindings and one ghost-source binding. Both used seed 20260816;
  they are scale stress evidence, not calibration statistics.
- Implementation validation: 30 center-handover tests passed on 2026-08-16.
  The replay test uses 20 center cameras and eight search resources. Synthetic
  GNN tests train on both 20-target and 40-target, three-frame fixtures and
  verify nonzero multi-frame motion features. Unit tests create models only
  under temporary paths; the campaign model is frozen separately by the main
  offline benchmark.
- Saved-replay adapter smoke: a temporary manifest referenced the existing
  `airsim_n20_formal_v3_20260816` output without copying it. The loader resolved
  20 center cameras, eight search resources, five frames, 243 anonymous local
  observations, and 20 source cues. A one-epoch temporary model completed the
  GNN runner path with zero online truth leakage; its association result is not
  performance evidence.
- Frozen-model training: the optional experimental GNN used only synthetic
  20-target and 40-target data with disjoint training and validation seeds.
  AirSim seed `20260816` was excluded from training and validation. Synthetic
  validation edge precision was `0.999306` and edge recall was `1.0`.
- Held-out replay comparison: `n20_m8` produced 16 correct / 0 wrong bindings
  with geometry and 16 / 0 with GNN; `n20_m30` produced 14 / 0 with both;
  `n40_m50` produced 31 / 1 with geometry and 31 / 0 with GNN.
- Isolation and timing: online truth leakage was zero for both methods in all
  three scenarios. Every center-method case used five timing repetitions.
- Evidence limit: all three comparisons replay the same AirSim seed
  `20260816`. They are not multi-seed statistics, and the frozen GNN remains an
  optional experimental path rather than a production capability.

## Remaining main-owned validation

- [ ] Run ten held-out 20-target AirSim seeds with `simGetDetections` boxes.
- [ ] Repeat the identical-frame geometry/GNN comparison over independent
  AirSim seeds before drawing statistical conclusions.
- [ ] Add navigation, gimbal, timestamp, and detector error sensitivity only
  after the ideal handover baseline remains stable.
- [ ] Add an explicit ghost-source exclusion stage using source existence,
  source-to-source conflict, and independent camera support before confirming
  a dense-scene binding.

The geometry path now has multiple runs of one real AirSim seed, including one
five-frame result. Multi-seed calibration and error sensitivity remain
main-owned because they require Blocks launch, actor movement, episode reset,
camera placement, and campaign-level log collection.
