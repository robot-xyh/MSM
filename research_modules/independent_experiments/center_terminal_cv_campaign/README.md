# Center-to-Terminal ComputerVision Campaign

This independent campaign validates three separable AirSim problems:

1. probability-cell search under either the legacy 80/80 cue fixture or the
   perfect-cue coarse-position offline protocol;
2. center dual-optical cue to terminal-camera track association;
3. anonymous cross-camera association between interceptor camera nodes.

The online path uses AirSim detection boxes only after the longest bounding-box
side reaches 10 pixels. Actor names and truth identities are offline scoring
labels and must not enter search or association decisions.

The three experiment packages are owned by separate task agents. Main owns the
shared contracts, settings generator, serial Blocks orchestration, and final
reporting.

Blocks 1.8.1 accepts the requested per-camera image dimensions but reports the
default 90-degree FOV immediately after startup. Main therefore applies 3.67
degrees to the center cameras and 19 degrees to terminal cameras through
`simSetCameraFov` after startup and every reset, then records an API audit.

## Post-search center handover error campaign on 2026-08-20

Main completed a center-to-terminal registration campaign that starts after
cooperative search has already found every target. Center source precision and
recall are fixed at 1.0 and resources are one-to-one with 20, 40, or 60 targets.
The camera is 1920x1080 with a 19-degree horizontal FOV, the target is 3 m and
50 m/s, and the observation range is about 700 m. The reported recall is
conditional on search success and is not an end-to-end system probability.

The offline matrix contains 480 scenario combinations and two association
backends, producing 960 per-seed rows over ten seeds. It crosses 5 m satellite
and 50 m visual-navigation radial P95 position error, normal and degraded
attitude/gimbal profiles, ideal and light detector conditions, and anonymous
versus geometry-validated coarse-ID handover. Light corruption uses 3% misses,
two false alarms per camera per second, and 0.25 px center noise.

For normal attitude, satellite navigation, and light detector corruption, the
anonymous geometry recall at 20/40/60 targets was 0.970/0.915/0.925. With a
validated coarse ID it was 0.975/0.953/0.965. Under 50 m visual navigation and
the degraded attitude profile, anonymous geometry recall fell to
0.860/0.710/0.615; the validated coarse-ID path reached
0.935/0.920/0.855. Across all combinations geometry averaged 0.950 precision
and 0.915 recall.

The previously frozen GNN averaged 0.438 precision and 0.025 recall because its
training distribution did not contain the new navigation, attitude, gimbal,
and detector errors; it is rejected for this campaign. The result does not
show that graph scoring is inherently unusable. It shows that the old model
cannot be transferred into this error regime without retraining and held-out
calibration, and that 60 targets are outside its trained scale.

One real ComputerVision `simGetDetections` representative also completed at
each requested scale with no saved PNGs. The first attempt exposed a Blocks
1.8.1 startup-reset crash; the runner now resets only between episodes. The
primary reproducible result remains the offline matrix under
`outputs/center_handover_sensor_error_20260820/`, graded B by the evidence
locator. The three one-seed AirSim roots are separate interface evidence and
currently grade C because complete runtime provenance was not frozen.

## Terminal registration diagnostic on 2026-08-19

The center-handover geometry now exposes the complete NED-to-body,
body-to-gimbal, and gimbal-to-camera rotation chain, separate body-to-gimbal
and gimbal-to-optical-center offsets, measurement-time pose interpolation, and
numerical covariance propagation for navigation, attitude, gimbal, and pixel
errors. Saved 20260816 AirSim observations contain a composite camera pose at
measurement time and are therefore replayed with zero installation offsets;
non-zero offsets and pose-error sequences are covered by unit tests, not by a
new AirSim run.

Cross-view offline scoring now reports relation precision plus target-equal
purity, completeness, exact clean-cluster rate, mixed-identity target count,
and opportunity targets that never formed a cross-view relation. A 36-point
diagnostic sweep varied only GNN probability threshold, GNN/geometry fusion
weight, and unmatched cost on the three report replays. The selected values
were 0.05, 0.25, and 0.85. They removed mixed identities, but reduced
target-equal completeness to 0.25 in 20/8 and 0.5666 in 40/50. The same values
improved 20/30 relation precision from 0.7402 to 0.9736. Because selection used
the report replays themselves, this is diagnostic test-set tuning and not an
independent validation. Sparse geometry remains the default.

Evidence and exact input hashes are under
`outputs/terminal_gnn_diagnostic_selection_20260819_v2/`. The terminal report
generator has a `--terminal-only` path so report updates do not rewrite the
perfect-cue search report.

## Perfect-cue offline search matrix on 2026-08-19

The search package now has a second, deliberately separate validation
protocol. It assumes one correct center cue per real target, with source
precision and recall both equal to 1.0, then injects seeded N/E/D position
errors with per-axis sigma values of 30, 60, and 100 metres. There are no
ghost, duplicate, or missed cues in this protocol.

The completed matrix contains 45 deterministic offline replays: three scales
(20 targets/8 resources, 20/30, and 40/50), three position-error levels, and
five cue-error seeds 20260816 through 20260820. The 20/8 mean consecutive
confirmation rates were 1.00, 0.97, and 0.91 for the 30, 60, and 100 metre
levels. The other two scales reached 1.00 in all three levels. Online truth
leakage was zero in all 45 runs.

An assignment is not counted as an observation. A resource must reach the
camera pose under the 97 m/s platform-speed assumption, satisfy the 200 deg/s
gimbal-rate assumption, and complete three 0.1-second frames inside the
18-second budget. Observation scoring then applies the real pinhole frustum,
the 10-pixel gate, and two consecutive frames. The camera is 1920 by 1080
pixels with a 19-degree horizontal FOV and a derived 10.75-degree vertical FOV.

The input is saved AirSim actor motion, not five new AirSim flights. Existing
motion logs end at 0.8 seconds and are extrapolated for the remaining 17.2
seconds using their saved velocities. Resources start from a forward staging
line at N=2100 m; 97 m/s and 200 deg/s are simulation assumptions, not measured
equipment performance. No random detector miss, false alarm, navigation error,
collision constraint, or communication delay is injected. A visual search
confirmation closes a cue task but does not prove source-to-local identity;
that binding remains a terminal-registration responsibility.

Machine-readable evidence is under
`outputs/offline_search_100pct_cues_20260819/`. It contains 45 run directories,
`matrix.csv`, `matrix_summary.json`, input hashes, anonymous online records,
separate truth labels, figures, and a reproduction manifest. The Chinese
leadership report is `deliverables/leadership_report/协同搜索试验报告_CN.md`.

## Validation state

On 2026-08-16 main ran one real five-target smoke campaign and a sequence of
twenty-target repair runs in AirSim ComputerVision mode, seed 20260816. Each
campaign used one Blocks process with reset-separated search, center-handover,
and cross-view episodes. Target actors moved at 50 m/s and camera detections
used the 10-pixel longest-side gate. No AirSim scene screenshots were saved.

The five-target smoke found all five targets, bound all four correct center
cues without a wrong binding, and scored five correct cross-view relations
without an identity switch. In the final twenty-target run, all 20 targets were
detected and reached the recognition gate, while 19/20 passed consecutive-frame
confirmation. Three of the four targets omitted by the center fixture were
recovered. Center handover bound all 16 correct cues, rejected all four false
cues, and produced no wrong binding. Cross-view association scored 30 correct
relations, zero wrong relations, two missed relations, and no mixed identity
cluster, for 1.0 precision and 0.9375 recall. Online truth leakage was zero in
all three experiments, and every camera FOV audit passed.

The initial, v2, and v3 twenty-target runs used the same seed but include
incremental algorithm and observation-window fixes. They demonstrate defect
closure and run-to-run `simGetDetections` variation; they are not independent
seed statistics. Evidence is below `outputs/airsim_n5_smoke_v3_20260816/` and
`outputs/airsim_n20_formal_v3_20260816/`. The combined Chinese report is
`outputs/AIRSIM_5_20_TARGET_VALIDATION_REPORT_CN.md`. Output directories remain
generated artifacts and are ignored by Git.

## Scale stress on 2026-08-16

Main subsequently reused one 52-vehicle Blocks process for a 20-target,
30-interceptor case and a 40-target, 50-interceptor case. Every declared
interceptor participated in search and in the cross-view capture plan. Search
confirmed all targets in both cases and recovered all center-missed targets.

The scale run did not validate global all-camera association. The 30-camera
case produced 85,847 candidate edges, 302 wrong relations, and five mixed
identity clusters. The 50-camera case produced 1,104,646 candidate edges,
2,537 wrong relations, and 18 mixed identity clusters. Center handover also
produced one ghost-source binding in the 40-target case. These results require
sector/FOV overlap gating before local Hungarian association; they do not
support enabling the optional GNN on the full candidate graph.

The comparison report is
`outputs/AIRSIM_M30N20_M50N40_SCALE_REPORT_CN.md`. The 40/50 numerical
artifacts completed, while the legacy full-relation figure was interrupted
because plotting thousands of relation artists added no metric evidence.
Reporting now uses constant-time relation lookup and bounded camera/relation
sampling for future scale runs.

The full 20-target/8-resource, 20-target/30-resource, and
40-target/50-resource comparison is
`outputs/AIRSIM_20_8_20_30_40_50_FULL_REPORT_CN.md`. It reads the three saved
metric sets directly and includes eight reproducible principle and result
figures below `outputs/three_scale_report_figures/`.

## Offline GNN replay benchmark on 2026-08-16

Main froze two optional pure-PyTorch graph scorers using synthetic 20-target
and 40-target data with disjoint training and validation seeds. The three saved
AirSim campaigns above remained held-out test data. Relative-path replay
manifests verify every referenced input by SHA256, and online association loads
anonymous observations before offline truth labels.

The benchmark compared geometry and GNN backends for center handover, full
camera-pair cross-view association, and sector/FOV-sparse cross-view
association. It produced 18 result rows. The 20-target/30-camera sparse GNN
improved precision from 0.7402 to 0.8008, recall from 0.8967 to 0.9078, and
reduced mixed-identity clusters from four to two. In the 40-target/50-camera
case, camera-pair sparsification was the dominant change: it reduced camera
pairs from 1,225 to 403 and candidate edges from 1,104,646 to 375,236. Sparse
geometry reached 0.9960 precision, 0.9305 recall, and zero mixed identities.
The sparse GNN produced exactly the same quality and took 812.96 seconds versus
770.99 seconds for geometry.

The GNN therefore remains an offline optional comparator. Sector/FOV-sparse
geometry stays the default cross-view path. Center GNN removed the one
geometry-only ghost-source binding in the 40-target replay, but this single-seed
result is not enough to change the default. The full report is
`outputs/gnn_offline_benchmark_20260816/GNN_OFFLINE_BENCHMARK_REPORT_CN.md`;
`benchmark_summary.json` contains all metrics, timing samples, acceptance
checks, and truth-isolation counts.
