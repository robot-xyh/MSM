#!/usr/bin/env python3
"""Run the isolated center dual-optical to terminal handover experiment."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
import sys
import time
from typing import Any, Callable, Literal, Sequence


PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from center_terminal_cv_campaign.common.io import write_jsonl  # noqa: E402
from center_terminal_cv_campaign.exp_center_handover.airsim_adapter import (  # noqa: E402
    AirSimDetectionAdapter,
    AirSimOfflineDetectionLabel,
)
from center_terminal_cv_campaign.exp_center_handover.association import (  # noqa: E402
    CenterHandoverAssociator,
    FrameAssociationResult,
)
from center_terminal_cv_campaign.exp_center_handover.fixture import (  # noqa: E402
    HandoverFixture,
    LocalTrackTruthLabel,
    load_handover_fixture,
)
from center_terminal_cv_campaign.exp_center_handover.gnn import (  # noqa: E402
    SparseGNNScorer,
    load_model,
)
from center_terminal_cv_campaign.exp_center_handover.reporting import (  # noqa: E402
    OutputPaths,
    write_experiment_outputs,
)
from center_terminal_cv_campaign.exp_center_handover.replay import (  # noqa: E402
    load_replay_fixture,
)


RunMode = Literal["offline", "airsim"]
AssociationBackend = Literal["geometry", "gnn"]
FrameAdvance = Callable[[int, float], None]


@dataclass(frozen=True)
class ExperimentRunResult:
    fixture_dir: Path
    replay_manifest: Path | None
    output_dir: Path
    mode: RunMode
    association_backend: AssociationBackend
    metrics: dict[str, Any]
    paths: OutputPaths
    frame_results: tuple[FrameAssociationResult, ...]


def run(
    *,
    fixture_dir: Path | str | None = None,
    replay_manifest: Path | str | None = None,
    output_dir: Path | str,
    mode: RunMode = "offline",
    association_backend: AssociationBackend = "geometry",
    airsim_client: Any | None = None,
    model_path: Path | str | None = None,
    frame_timestamps: Sequence[float] = (0.2, 0.3, 0.4, 0.5, 0.6),
    frame_delay_s: float = 0.1,
    frame_advance: FrameAdvance | None = None,
) -> ExperimentRunResult:
    """Public main-agent entry point.

    The function never launches or resets Blocks. In ``airsim`` mode main may
    inject an existing client and a callback that advances its actor scene.
    """

    if (fixture_dir is None) == (replay_manifest is None):
        raise ValueError("provide exactly one of fixture_dir or replay_manifest")
    if fixture_dir is not None:
        fixture_path = Path(fixture_dir)
    else:
        assert replay_manifest is not None
        fixture_path = Path(replay_manifest)
    replay_path = Path(replay_manifest).resolve() if replay_manifest is not None else None
    output_path = Path(output_dir)
    if mode not in {"offline", "airsim"}:
        raise ValueError("mode must be offline or airsim")
    if association_backend not in {"geometry", "gnn"}:
        raise ValueError("association_backend must be geometry or gnn")
    if len(frame_timestamps) < 3:
        raise ValueError("at least three frames are required for 2-of-3 confirmation")
    if frame_delay_s < 0.0:
        raise ValueError("frame_delay_s cannot be negative")
    if replay_path is not None and mode != "offline":
        raise ValueError("saved replay manifests are valid only in offline mode")

    if replay_path is None:
        fixture = load_handover_fixture(fixture_path)
    else:
        fixture, _ = load_replay_fixture(replay_path)
    raw_air_sim_labels: tuple[AirSimOfflineDetectionLabel, ...] = ()
    if mode == "offline":
        frames = fixture.frames
    else:
        client = airsim_client or _connect_existing_airsim()
        adapter = AirSimDetectionAdapter(fixture.camera_models)
        collected_frames: list[tuple[Any, ...]] = []
        label_rows: list[AirSimOfflineDetectionLabel] = []
        for frame_index, timestamp in enumerate(frame_timestamps):
            if frame_index:
                if frame_advance is not None:
                    frame_advance(frame_index, float(timestamp))
                elif frame_delay_s:
                    time.sleep(frame_delay_s)
            batch = adapter.collect_frame(
                client,
                measurement_timestamp=float(timestamp),
                arrival_timestamp=float(timestamp) + 0.02,
            )
            collected_frames.append(batch.local_tracks)
            label_rows.extend(batch.offline_labels)
        frames = tuple(collected_frames)
        raw_air_sim_labels = tuple(label_rows)
        fixture = replace(
            fixture,
            frames=frames,
            local_truth=_derive_air_sim_local_truth(raw_air_sim_labels, fixture),
        )

    scorer = None
    model_metadata: dict[str, Any] | None = None
    if association_backend == "gnn":
        if model_path is None:
            raise ValueError("gnn backend requires an explicit model_path")
        resolved_model_path = Path(model_path)
        if not resolved_model_path.is_file():
            raise FileNotFoundError(f"GNN model does not exist: {resolved_model_path}")
        model, model_metadata = load_model(resolved_model_path)
        scorer = SparseGNNScorer(model)

    associator = CenterHandoverAssociator(fixture.camera_models, candidate_scorer=scorer)
    frame_results = tuple(
        associator.process_frame(fixture.source_cues, tuple(frame)) for frame in frames
    )
    metrics, paths = write_experiment_outputs(
        output_dir=output_path,
        fixture=fixture,
        frames=frames,
        results=frame_results,
        mode=mode,
        backend=association_backend,
        model_metadata=model_metadata,
    )
    if raw_air_sim_labels:
        write_jsonl(output_path / "truth" / "airsim_detection_labels.jsonl", raw_air_sim_labels)
    return ExperimentRunResult(
        fixture_dir=fixture_path,
        replay_manifest=replay_path,
        output_dir=output_path,
        mode=mode,
        association_backend=association_backend,
        metrics=metrics,
        paths=paths,
        frame_results=frame_results,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--fixture-dir", type=Path)
    input_group.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline", "airsim"), default="offline")
    parser.add_argument(
        "--association-backend", choices=("geometry", "gnn"), default="geometry"
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--frame-delay-s", type=float, default=0.1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(
        fixture_dir=args.fixture_dir,
        replay_manifest=args.replay_manifest,
        output_dir=args.output_dir,
        mode=args.mode,
        association_backend=args.association_backend,
        model_path=args.model_path,
        frame_delay_s=args.frame_delay_s,
    )
    print(f"metrics={result.paths.metrics.resolve()}")
    print(f"report={result.paths.report.resolve()}")
    return 0


def _connect_existing_airsim() -> Any:
    import airsim

    client = airsim.VehicleClient()
    client.confirmConnection()
    return client


def _derive_air_sim_local_truth(
    rows: Sequence[AirSimOfflineDetectionLabel], fixture: HandoverFixture
) -> tuple[LocalTrackTruthLabel, ...]:
    actor_to_truth = {
        target.actor_name: target.truth_target_id for target in fixture.target_truth
    }
    labels: dict[tuple[str, str], LocalTrackTruthLabel] = {}
    for row in rows:
        truth_id = _match_actor_name(row.raw_detection_name, actor_to_truth)
        if truth_id is None:
            continue
        key = (row.camera_id, row.local_track_id)
        labels[key] = LocalTrackTruthLabel(
            camera_id=row.camera_id,
            local_track_id=row.local_track_id,
            truth_target_id=truth_id,
        )
    return tuple(labels[key] for key in sorted(labels))


def _match_actor_name(raw_name: str, actor_to_truth: dict[str, str]) -> str | None:
    matches = [name for name in actor_to_truth if raw_name == name or raw_name.startswith(f"{name}_")]
    if not matches:
        return None
    return actor_to_truth[max(matches, key=len)]


if __name__ == "__main__":
    raise SystemExit(main())
