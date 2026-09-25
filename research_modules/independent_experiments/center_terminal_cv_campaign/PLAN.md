# Implementation Plan

## Completed on 2026-08-20

- [x] Add a post-search center-to-terminal error protocol with source
  precision/recall 1.0, one interceptor per target, and 20/40/60 target scale.
- [x] Propagate center-track, navigation, body-attitude, gimbal, drift, and
  pixel uncertainty into the image-plane association covariance.
- [x] Complete the ten-seed, 960-row offline matrix over navigation, attitude,
  detector, handover-information, and backend conditions without excluding low
  results.
- [x] Freeze the protocol, source snapshot, model and hashes, row-level and
  aggregate metrics, figures, representative traces, and reproduction command
  under `outputs/center_handover_sensor_error_20260820/`.
- [x] Complete one real `simGetDetections` AirSim representative at 20, 40, and
  60 targets; do not save PNG frames. Correct the first-episode reset lifecycle
  after the initial Blocks startup crash.
- [x] Keep geometry as the active baseline. Reject the old frozen GNN for this
  error distribution after its full-matrix recall averaged 0.025.
- [x] Run 41 center-handover tests and audit the primary offline evidence as a
  deterministic replay package (grade B).

## Completed on 2026-08-19

- [x] Add a search-only offline replay protocol with exactly one correct cue
  per target and seeded N/E/D position errors at 30, 60, and 100 metre sigma.
- [x] Split assigned tasks from executed observations. Enforce an 18-second
  budget, 97 m/s platform speed, 200 deg/s gimbal rate, and 0.3-second dwell
  before recording true-frustum coverage.
- [x] Tile each 3-sigma cue region using the 1920x1080, 19-degree camera
  footprint with 20% overlap; retain the 10-pixel and two-frame gates.
- [x] Complete 45 offline runs over 20/8, 20/30, and 40/50 scales, three error
  levels, and seeds 20260816-20260820. All online truth-leakage checks passed.
- [x] Save per-run configuration, anonymous online records, separate truth,
  input SHA256, aggregate CSV/JSON, figures, and a reproduction manifest under
  `outputs/offline_search_100pct_cues_20260819/`.
- [x] Generate the revised Chinese search report and Word document from the
  completed matrix without regenerating the terminal-registration report.
- [x] Add the explicit `R_C^G R_G^B R_B^N` chain, two-stage camera installation
  offsets, measurement-time pose interpolation, and joint image/ray
  covariance propagation with numerical tests.
- [x] Add target-equal cross-view purity, completeness, exact clean-cluster,
  mixed-target, and unfinished-opportunity metrics without exposing truth to
  online association.
- [x] Run a 36-point GPU diagnostic sweep that varies only GNN probability
  threshold, fusion weight, and unmatched cost on the three saved sector/FOV
  AirSim replays; freeze inputs, hashes, candidates, selection reason, and cold
  timing under `outputs/terminal_gnn_diagnostic_selection_20260819_v2/`.
- [x] Generate the terminal-only Markdown/Word report while preserving the
  cooperative-search Markdown and Word hashes.

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

- [ ] Replace linear trajectory extrapolation after 0.8 seconds with longer
  saved AirSim motion before treating the 45-run matrix as dynamic-flight
  evidence.
- [ ] Validate the forward staging line, 97 m/s platform limit, 200 deg/s
  gimbal limit, settling time, collision avoidance, and communication delay in
  an AirSim run with physical motion rather than an offline upper-limit model.
- [ ] Validate detector, navigation, timestamp, and camera-pose errors taken
  from AirSim/runtime or hardware streams. The center-handover matrix now has
  controlled offline injection, while the perfect-cue search matrix still has
  none.
- [ ] Record decomposed body, gimbal, and camera mount poses in a new AirSim
  capture so non-zero installation offsets and measurement-time pose
  interpolation are validated beyond unit tests.
- [ ] Calibrate GNN probabilities on independent training/validation replays.
  The 2026-08-19 diagnostic selection improved 20/30 but lost substantial
  completeness in 20/8 and 40/50, so it must not replace sparse geometry.
- [ ] Reduce repeated views in dense target groups without eliminating useful
  second-angle confirmation.
- [ ] Keep search confirmation separate from center-cue identity binding. The
  offline matrix records cue closures triggered by nearby targets at larger
  position errors; terminal registration must resolve those identities.

- [ ] Repeat real AirSim validation with at least ten independent seeds. The
  current runs reuse seed 20260816 and are integration/repair evidence, not
  calibration statistics.
- [ ] Quantify search confirmation and cross-view recall sensitivity to
  `simGetDetections` dropouts, short-track length, FOV edges, and resource ratio.
- [ ] Run the planned 20-target search resource counts of 20/25/30/40 without
  relaxing the 10-pixel, geometry, or temporal confirmation gates.
- [ ] Extend controlled error replay beyond center handover to search and
  interceptor-to-interceptor association before making an equipment-level
  performance claim.
- [ ] Calibrate deterministic ghost-source exclusion over independent seeds.
  The optional GNN removed the one saved 40-target ghost binding, but one replay
  is insufficient evidence for a default-path change.
- [ ] Retrain center-handover GNN on the new error distribution and 60-target
  scale, then compare geometry/GNN over independent AirSim seeds. Cross-view
  GNN remains a separate optional path.
- [ ] Profile and reduce geometry candidate-construction cost. Even after
  pruning 1,225 camera pairs to 403, the 40/50 sparse geometry replay required
  770.99 seconds on the current CPU/reporting path.
