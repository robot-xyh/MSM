# Center-to-Terminal ComputerVision Campaign

This independent campaign validates three separable AirSim problems:

1. probability-cell search from center cues with 80% precision and 80% recall;
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
