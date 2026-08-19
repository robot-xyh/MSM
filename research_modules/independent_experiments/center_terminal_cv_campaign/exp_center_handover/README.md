# Center Dual-Optical to Terminal Handover

This independent experiment associates anonymous center source cues with
anonymous terminal-camera local tracks. It does not import or modify D1-D7 or
the dual-optical V4 implementation.

## Implemented path

1. Propagate each `SourceCueRecord` from `measurement_timestamp` to the image
   timestamp with a constant-velocity model and six-state covariance.
2. Apply the explicit NED -> body -> gimbal -> camera transform and pinhole
   projection. Propagate position covariance to a two-dimensional prediction
   ellipse with the projection Jacobian.
3. Reject candidates that fail source arrival/`valid_until`, ten-pixel
   recognition, Mahalanobis distance, or motion-continuity gates.
4. Solve one-to-one assignment with a source-specific dummy column. Confirm a
   binding only after it is selected in at least two of the latest three frames.
   The public AirSim runner samples five frames at 0.2 through 0.6 seconds by
   default, so one transient `detect` miss does not have to be the final sample.
5. Keep camera-local tracks for center-missed targets as
   `unregistered_candidate`. The experiment uses `source_track_id` and never
   creates or rewrites `global_track_id`.

The optional pure-PyTorch sparse graph scorer only reorders candidates that
already passed geometry. Hungarian assignment and temporal confirmation remain
mandatory. `torch_geometric` is not required. GNN mode requires an explicitly
provided saved model through `model_path` or `--model-path`; the experiment
entry point does not start a training campaign automatically.

The synthetic trainer covers both 20-target and 40-target fixtures and at
least three ordered frames. Existing motion-residual and motion-availability
edge features are populated from prior-frame observations instead of being
trained only on one-frame graphs. Training and inference are fixed to CPU.
AirSim seed `20260816` is held out and rejected from training and validation.

## Main integration API

`run_experiment.py` exports:

```python
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_experiment import run

result = run(
    fixture_dir=".../fixture_n20_seed20260816",
    output_dir=".../handover_output",
    mode="offline",                 # offline | airsim
    association_backend="geometry", # geometry | gnn
)
```

Saved AirSim output can be replayed without copying its JSON/JSONL artifacts:

```python
result = run(
    replay_manifest=".../center_terminal_gnn_replay.json",
    output_dir=".../center_handover_gnn_replay",
    mode="offline",
    association_backend="gnn",
    model_path=".../center_handover_sparse_gnn.pt",
)
```

The command-line interface exposes the same required fields:

```bash
python3 research_modules/independent_experiments/center_terminal_cv_campaign/exp_center_handover/run_experiment.py \
  --fixture-dir /path/to/fixture_n20_seed20260816 \
  --output-dir /path/to/handover_output \
  --mode offline \
  --association-backend geometry
```

For saved output, replace `--fixture-dir` with `--replay-manifest`. These two
inputs are mutually exclusive, and a replay manifest is accepted only in
`offline` mode.

`airsim` mode accepts an existing client through `run(..., airsim_client=...)`.
The adapter calls only `simGetCameraInfo` and `simGetDetections`; it does not
launch, reset, move, pause, or close Blocks. Main must position each terminal
camera so the intended local target is in view and reaches a longest bounding-
box side of at least 10 pixels. Shared settings place every `Terminal_CV_*` at
the origin. Main therefore sends any `simSetVehiclePose` position as an absolute
world-NED pose and must not add a settings-origin offset. Association uses the
absolute world-NED pose returned by `simGetCameraInfo`.

## Read-only replay contract

The loader accepts schema `center-terminal-gnn-replay-v1`. Paths are resolved
relative to the manifest. It reads and verifies SHA256 only for these center
handover inputs:

- `scenario`, `source_cues`, and `center_local_tracks`;
- `center_source_truth` and `center_local_truth` for post-association scoring;
- `crossview_calibrations` and `crossview_capture_plan` for the saved camera
  profile and capture-contract audit.

Other common-manifest keys, including `crossview_local_tracks` and
`crossview_truth`, are not opened by this experiment. Online source and local
records are rejected if they contain actor names, truth target IDs, or global
track IDs.

Center camera IDs come from `center_local_tracks`, not from `resource_count` or
the cross-view camera list. This matters for the 20-target/8-resource saved run:
center handover contains 20 target-facing `Terminal_CV` cameras while the
cross-view calibration file contains eight active search cameras. The latter
provides only the common 1920x1080/19-degree intrinsics template. Each center
camera origin and attitude is reconstructed from its anonymous local-track
records and must remain consistent across saved frames.

## GNN training and frozen model

Run the explicit CPU trainer with disjoint synthetic seeds:

```bash
python3 research_modules/independent_experiments/center_terminal_cv_campaign/exp_center_handover/train_gnn.py \
  --output-model /path/to/center_handover_sparse_gnn.pt \
  --train-seeds 20260001,20260002,20260003 \
  --validation-seeds 20260101,20260102 \
  --target-counts 20,40 \
  --frame-timestamps 0.2,0.3,0.4
```

Freezing writes the `.pt` file and a `.pt.manifest.json` sidecar. The sidecar
records model dimensions, feature strategy, full training configuration,
training and validation seeds, validation metrics, metadata SHA256, and model
SHA256. Loading fails closed for a missing sidecar, old schema, changed model,
changed metadata, seed overlap, held-out seed use, or feature mismatch. Saved
AirSim replay is not accepted as training data; `test_only=true` or campaign
seed `20260816` is explicitly rejected by the training entry point.

## Inputs and outputs

The fixture reads the shared campaign contracts without changing `common/`.
If `camera_models.json` and `online/local_tracks.jsonl` are absent, offline mode
derives them from fixture truth solely to build a replay. Truth stays under the
`truth/` output directory and is used only for scoring.

Every run writes:

- `metrics.json` and `REPORT_CN.md` at the requested output root;
- online source cues, local tracks, candidate gates, selections, confirmations,
  dummy decisions, and rejection reasons under `online/`;
- offline labels under `truth/` when available;
- two-dimensional prediction-ellipse and matching-cost figures under
  `figures/`.

`unregistered_candidate_count` is retained for compatibility. Its unit is the
number of unmatched camera-local tracks in the final frame, not the number of
distinct targets. New metrics expose the same count as
`unregistered_local_track_candidate_count`, record its semantics explicitly,
separate candidates above and below the ten-pixel gate, and use offline labels
to split redundant views of registered targets from observations of center-
missed targets. Online association still receives no truth identity.

Matplotlib uses the `Agg` backend and no `Axes3D` feature. This avoids the local
`mpl_toolkits` version conflict.

## Validation

### Offline fixture

On 2026-08-16, the deterministic 20-target seed `20260816` geometry replay
produced 16 correct confirmed bindings, rejected all four incorrect source
cues, and kept four center-missed targets unregistered. Binding precision and
recall over the 16 eligible correct source cues were both 1.0. Online truth-ID
leakage was zero. This is fixture evidence, not a real AirSim or equipment
performance result.

### AirSim formal run

The real output
`../outputs/airsim_n20_formal_20260816/center_handover/` was audited on
2026-08-16 without rerunning Blocks. It contains three frames from 20
ComputerVision terminal cameras using `simGetDetections`. All 16 correct source
cues were confirmed against the correct truth target; all four false cues (two
duplicate sources and two ghost sources) remained `source_unmatched`. False
binding and online truth leakage were both zero.

The final frame contains 52 camera-local tracks for 20 physical targets. Sixteen
tracks were selected for confirmed bindings and 36 were left unmatched. Of the
36 unmatched tracks, 23 are redundant camera views of 13 already registered
targets, and 13 are observations of the four targets omitted by the center cue
fixture. Thirty-five meet the ten-pixel gate; one is a 7.10-pixel redundant view
of already registered `TGT-010`. Therefore the historical value
`unregistered_candidate_count=36` does not mean that 36 targets failed to
register. This is one controlled AirSim seed, not equipment performance or a
multi-seed statistical result.

The saved v2 output
`../outputs/airsim_n20_formal_v2_20260816/center_handover/` was compared with
the first formal output without starting Blocks. Its only unconfirmed correct
cue was `SRC-009`, whose offline target label is `TGT-012`, on
`Terminal_CV_05`. Frames at 0.2 and 0.3 seconds selected the same local track
`LCL-Terminal_CV_05-0003`; the second frame confirmed it. The 0.4-second frame
contained no detection of that target, so no candidate for the established
local track existed and the source ended as unmatched. The runner now collects
two additional frames by default while retaining the same ten-pixel,
Mahalanobis, motion, identity, and rolling two-of-three confirmation gates.
The saved outputs contain no 0.5/0.6-second observations, so recovery to 16/16
could not be established from the v2 evidence alone.

### AirSim five-frame rerun

The real five-frame output
`../outputs/airsim_n20_formal_v3_20260816/center_handover/` closed that specific
check on 2026-08-16. All 16 correct source cues were bound to the correct local
tracks, no incorrect binding was produced, and all four false source cues were
rejected. Binding precision and recall over the 16 correct source cues were both
1.0. The run processed five frames and retained the same rolling two-of-three
confirmation rule and gate thresholds.

The final frame contained 48 recognized camera-local tracks. Sixteen were used
by confirmed bindings and 32 remained unmatched. Offline labels split those 32
tracks into 20 redundant camera observations of 12 already registered targets
and 12 observations of the four targets for which the center supplied no correct
source cue. No unmatched observation came from a correct but unbound source,
and no truth label was missing. Thus `unregistered_candidate_count=32` is a
camera-local-track count, not 32 unregistered physical targets.

This is one rerun of seed `20260816`. The first, v2, and v3 runs demonstrate
run-to-run `simGetDetections` variation under the same nominal scenario; they do
not provide independent-seed statistics or equipment-level performance bounds.

Run the package tests from the repository root:

```bash
pytest -q research_modules/independent_experiments/center_terminal_cv_campaign/exp_center_handover/tests
```

On 2026-08-16, this directory's 30 tests passed. They include a small saved-
replay fixture with 20 actual center cameras and eight search resources,
manifest and model hash checks, online truth-leak checks, cross-frame camera
pose checks, disjoint-seed checks, and executed 20/40-target multi-frame synthetic
training. These tests do not constitute a geometry-versus-GNN AirSim result.

A separate read-only smoke check referenced the existing
`airsim_n20_formal_v3_20260816` files through a temporary unified manifest. It
loaded 20 center cameras, eight declared search resources, five frames, 243
anonymous local-track observations, and 20 source cues. An end-to-end GNN
runner smoke check completed with zero online truth leakage using a one-epoch
temporary model. No association-performance conclusion is drawn from that
temporary model.

### Scale stress rerun

On 2026-08-16 the real 20-target/30-resource case confirmed 14 of 16 correct
source bindings with zero wrong binding. Binding precision was 1.0 and recall
over correct sources was 0.875. The real 40-target/50-resource case confirmed
31 correct bindings and one wrong binding among 32 confirmations, for 0.96875
precision and recall over the 32 correct sources.

The wrong 40-target relation bound ghost source `SRC-037` to local track
`LCL-Terminal_CV_07-0004`, whose offline label is `TGT-037`. Online records did
not use that label. This is evidence that a spatially plausible ghost cue can
survive the current geometry, motion, Hungarian, and temporal gates in a dense
scene. Multi-camera source exclusion and existence-probability governance
remain required; extending the frame window alone is insufficient.

### Frozen-model offline replay benchmark

Main completed the read-only benchmark stored under
`../outputs/gnn_offline_benchmark_20260816/`. The experimental frozen GNN was
trained and validated only on synthetic 20-target and 40-target data. Training
and validation used mutually exclusive seed sets, and AirSim seed `20260816`
was excluded from both sets and used only as held-out replay data. Synthetic
validation produced edge precision `0.999306` and edge recall `1.0`.

Geometry and GNN were then evaluated on identical saved observations:

| Saved scenario | Geometry result | GNN result |
| --- | ---: | ---: |
| `n20_m8` | 16 correct / 0 wrong | 16 correct / 0 wrong |
| `n20_m30` | 14 correct / 0 wrong | 14 correct / 0 wrong |
| `n40_m50` | 31 correct / 1 wrong | 31 correct / 0 wrong |

Online truth leakage was zero for both methods in all three scenarios. Each
center-method case was timed five times. The 40-target replay shows that the
GNN candidate reordering removed the one geometry-only ghost-source binding
without relaxing the existing geometry gates, Hungarian assignment, or
two-of-three temporal confirmation contract.

All three scenarios are offline replays of the same AirSim seed `20260816`.
They are not independent-seed statistics and do not establish equipment or
production performance. The frozen GNN remains an optional experimental path;
geometry remains the fail-closed gate and the default deterministic baseline.
