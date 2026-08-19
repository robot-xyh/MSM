# Implementation Plan

## Completed on 2026-08-16

- [x] Freeze shared ComputerVision settings, exact 80/80 source-cue fixtures,
  the 10-pixel recognition rule, and anonymous online records.
- [x] Implement search, center handover, and interceptor cross-view experiments
  in disjoint packages with main-callable interfaces.
- [x] Apply and audit 3.67-degree center and 19-degree terminal FOV profiles
  after startup and every reset.
- [x] Run one real five-target smoke sequence and a series of twenty-target
  repair runs in one-Blocks, reset-separated episodes, seed 20260816.
- [x] Keep Actor names and target identities in offline scoring outputs only.
- [x] Keep deterministic geometry and Hungarian assignment as the default.
- [x] Increase search-cell dwell to three frames while retaining the
  consecutive two-frame recognition confirmation gate.
- [x] Extend center-handover observation to five frames while retaining the
  rolling two-of-three confirmation rule and all geometry gates.
- [x] Add mature-cluster bridge redundancy and short-track multi-camera
  consensus without enabling the optional GNN backend.
- [x] Rerun the real twenty-target campaign after the fixes and generate a
  five-/twenty-target comparison report from the saved metrics.
- [x] Run real 20-target/30-resource and 40-target/50-resource scale cases in
  one Blocks process with reset-separated episodes and all requested cameras
  active in search and cross-view capture.
- [x] Replace quadratic candidate-to-match report lookup with a set lookup and
  bound scale figures to 200 relations and 20 evenly sampled cameras.
- [x] Generate one metrics-backed 20/8, 20/30, and 40/50 comparison report with
  search-capacity calculations, handover projection, cross-view ray geometry,
  and eight reproducible principle/result figures.
- [x] Add relative-path, SHA256-verified replay manifests for the three saved
  AirSim campaigns and keep seed 20260816 test-only.
- [x] Train and freeze optional center-handover and cross-view graph scorers on
  synthetic 20/40-target data with disjoint training and validation seeds.
- [x] Add pre-candidate `full/sector_fov` camera-pair policies and an audit-only
  output mode that avoids rewriting complete scale candidate graphs.
- [x] Complete the 18-row geometry/GNN offline benchmark. The 40/50 sparse
  geometry path reached 0.9960 precision, 0.9305 recall, and zero identity
  mixing; sparse GNN had identical quality and 5.4% higher wall time.

## Remaining validation

- [ ] Repeat real AirSim validation with at least ten independent seeds. The
  current runs reuse seed 20260816 and are integration/repair evidence, not
  calibration statistics.
- [ ] Quantify search confirmation and cross-view recall sensitivity to
  `simGetDetections` dropouts, short-track length, FOV edges, and resource ratio.
- [ ] Run the planned 20-target search resource counts of 20/25/30/40 without
  relaxing the 10-pixel, geometry, or temporal confirmation gates.
- [ ] Inject navigation, camera-pose, timestamp, and detector errors into saved
  replays before making any equipment-level performance claim.
- [ ] Calibrate deterministic ghost-source exclusion over independent seeds.
  The optional GNN removed the one saved 40-target ghost binding, but one replay
  is insufficient evidence for a default-path change.
- [ ] Repeat geometry/GNN comparisons over independent real AirSim seeds. GNN
  remains optional because it improved the 20/30 sparse replay but added no
  quality in 40/50 sparse replay and increased wall time by 5.4%.
- [ ] Profile and reduce geometry candidate-construction cost. Even after
  pruning 1,225 camera pairs to 403, the 40/50 sparse geometry replay required
  770.99 seconds on the current CPU/reporting path.
