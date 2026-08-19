"""Bridge the main-owned shared snapshot to the frozen lightweight routes."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping

import numpy as np

from dual_optical_100target_gnn.graph import GeometryGate, build_online_graph
from dual_optical_100target_gnn.schema import (
    AnonymousTrack,
    CorruptionSummary,
    OnlineEpisode,
    TrackSample,
)
from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
    LEGACY_SCHEMA_VERSION,
    RevolutionSnapshot as SharedRevolutionSnapshot,
    SCHEMA_VERSION,
)

from .online import OnlineAssociationPublication, OnlineLightweightAdapter
from .online import RevolutionSnapshot as CandidateGraphSnapshot


def _summary_value(values: Mapping[str, int | float | str], name: str) -> int:
    aliases = {
        "dropped_sample_count": "dropped_detection_count",
        "retained_sample_count": "retained_real_detection_count",
    }
    value = values.get(name, values.get(aliases.get(name, ""), 0))
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as exc:
            raise ValueError(f"invalid corruption summary value: {name}") from exc
    return int(value)


def _canonical_payload_fingerprint(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        values,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def shared_snapshot_fingerprint(snapshot: SharedRevolutionSnapshot) -> str:
    """Fingerprint V2 canonically and preserve the original V1 field set."""

    parsed_fingerprint = getattr(
        snapshot, "_lightweight_source_input_fingerprint", None
    )
    if parsed_fingerprint is not None:
        return str(parsed_fingerprint)
    payload = snapshot.online_payload()
    if snapshot.tracker_fingerprint != "legacy-unfrozen-tracker":
        return _canonical_payload_fingerprint(payload)
    payload["schema_version"] = LEGACY_SCHEMA_VERSION
    payload.pop("tracker_fingerprint", None)
    for camera_tracks in payload["tracks"].values():
        for track in camera_tracks:
            for name in (
                "track_state",
                "recent_sweep_hits",
                "missed_sweep_count",
                "ambiguity_count",
            ):
                track.pop(name, None)
            for sample in track["samples"]:
                for name in (
                    "measurement_covariance_deg2",
                    "state_vector",
                    "state_covariance",
                    "innovation_mahalanobis2",
                ):
                    sample.pop(name, None)
    return _canonical_payload_fingerprint(payload)


def _reject_online_truth_fields(values: Any) -> None:
    forbidden = {"truth_id", "actor_name", "true_world_position", "identity"}
    if isinstance(values, Mapping):
        hits = forbidden & {str(key).lower() for key in values}
        if hits:
            raise ValueError(f"shared online snapshot contains forbidden fields: {sorted(hits)}")
        for value in values.values():
            _reject_online_truth_fields(value)
    elif isinstance(values, (list, tuple)):
        for value in values:
            _reject_online_truth_fields(value)


def shared_snapshot_from_dict(values: Mapping[str, Any]) -> SharedRevolutionSnapshot:
    """Parse the canonical payload written by the main-owned snapshot contract."""

    payload = dict(values)
    stored_fingerprint = payload.pop("input_fingerprint", None)
    _reject_online_truth_fields(payload)
    common = {
        "schema_version",
        "protocol_fingerprint",
        "seed",
        "split",
        "corruption_level",
        "revolution_index",
        "cutoff_timestamp",
        "camera_ids",
        "camera_positions_ned",
        "focal_length_px",
        "tracks",
        "corruption_summary",
        "source_hashes",
    }
    shared_candidate_fields = {
        "geometry_candidate_pairs",
        "candidate_graph_fingerprint",
        "candidate_graph_summary",
    }
    optional_fields = {
        "target_count",
        "association_round_period_s",
        "association_round_count",
    }
    schema_version = str(payload.get("schema_version", ""))
    required = common | ({"tracker_fingerprint"} if schema_version == SCHEMA_VERSION else set())
    if schema_version not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise ValueError("unsupported main-owned shared snapshot schema")
    target_count = payload.get("target_count")
    if target_count is not None and (
        isinstance(target_count, bool)
        or not isinstance(target_count, int)
        or target_count <= 0
    ):
        raise ValueError("shared snapshot target_count must be a positive integer")
    present_candidate_fields = set(payload) & shared_candidate_fields
    if present_candidate_fields and present_candidate_fields != shared_candidate_fields:
        raise ValueError("shared candidate graph fields must be supplied together")
    payload_fields = set(payload)
    if not required <= payload_fields or payload_fields - (
        required | shared_candidate_fields | optional_fields
    ):
        raise ValueError("shared snapshot fields do not match the main contract")
    fingerprint_payload = dict(payload)
    expected_fingerprint = _canonical_payload_fingerprint(fingerprint_payload)
    if stored_fingerprint not in {None, expected_fingerprint}:
        raise ValueError("stored shared snapshot fingerprint mismatch")
    # A route may accept the main contract's generic source marker, but it must
    # never let that marker alter association features or expose actor truth.
    sanitized_tracks = {}
    for camera_id, camera_tracks in payload["tracks"].items():
        sanitized_tracks[camera_id] = [
            {**dict(track), "source_kind": "anonymous"}
            for track in camera_tracks
        ]
    payload["tracks"] = sanitized_tracks
    snapshot = SharedRevolutionSnapshot.from_online_payload(payload)
    # The main contract is a frozen dataclass without slots.  Retain the exact
    # source payload fingerprint so pre-target_count snapshots remain auditable
    # after parsing without changing their public fields.
    object.__setattr__(
        snapshot,
        "_lightweight_source_input_fingerprint",
        expected_fingerprint,
    )
    return snapshot


def _shared_candidate_pairs(
    snapshot: SharedRevolutionSnapshot,
) -> tuple[tuple[str, str], ...] | None:
    """Return the main allowlist, or ``None`` only for legacy snapshots.

    A current snapshot may intentionally publish an empty allowlist.  Its graph
    fingerprint or summary distinguishes that case from an older snapshot that
    did not carry the shared-candidate contract at all.
    """

    pairs = tuple(
        (str(track_a_id), str(track_b_id))
        for track_a_id, track_b_id in getattr(
            snapshot, "geometry_candidate_pairs", ()
        )
    )
    fingerprint = str(getattr(snapshot, "candidate_graph_fingerprint", ""))
    summary = dict(getattr(snapshot, "candidate_graph_summary", {}))
    if pairs or fingerprint or summary:
        return pairs
    return None


def read_shared_snapshot(path: str | Path) -> SharedRevolutionSnapshot:
    return shared_snapshot_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _build_candidate_snapshot(
    snapshot: SharedRevolutionSnapshot,
    geometry_gate: Mapping[str, Any],
) -> tuple[CandidateGraphSnapshot, dict[str, int | float | str]]:
    tracks: dict[str, tuple[AnonymousTrack, ...]] = {}
    maximum_timestamp = 0.0
    snapshot_v2 = snapshot.tracker_fingerprint != "legacy-unfrozen-tracker"
    if snapshot_v2 and not snapshot.tracker_fingerprint:
        raise ValueError("Snapshot V2 must identify the frozen shared tracker")
    degrees_to_mrad = math.pi / 180.0 * 1000.0
    for camera_id in snapshot.camera_ids:
        converted = []
        for track in snapshot.tracks[camera_id]:
            samples = tuple(
                TrackSample(
                    sweep_index=int(sample.sweep_index),
                    timestamp=float(sample.timestamp),
                    direction_ned=tuple(float(value) for value in sample.direction_ned),
                    detection_count=int(sample.detection_count),
                    bbox_area_px2=float(sample.bbox_area_px2),
                    confidence=float(sample.confidence),
                    direction_covariance_mrad2=(
                        tuple(
                            float(value) * degrees_to_mrad * degrees_to_mrad
                            for value in sample.measurement_covariance_deg2
                        )
                        if snapshot_v2
                        else None
                    ),
                )
                for sample in track.samples
            )
            if samples:
                maximum_timestamp = max(
                    maximum_timestamp, max(item.timestamp for item in samples)
                )
            converted.append(
                AnonymousTrack(
                    track_id=track.track_id,
                    camera_id=track.camera_id,
                    samples=samples,
                    source_kind="anonymous",
                    angular_velocity_deg_s=(
                        tuple(float(value) for value in track.samples[-1].state_vector[2:4])
                        if snapshot_v2 and track.samples
                        else None
                    ),
                    state_covariance=(
                        tuple(
                            float(value)
                            for value in (
                                np.diag((degrees_to_mrad, degrees_to_mrad, 1.0, 1.0))
                                @ np.asarray(
                                    track.samples[-1].state_covariance, dtype=float
                                ).reshape(4, 4)
                                @ np.diag((degrees_to_mrad, degrees_to_mrad, 1.0, 1.0))
                            ).reshape(-1)
                        )
                        if snapshot_v2 and track.samples
                        else None
                    ),
                    recent_revolution_hits=(
                        tuple(bool(value) for value in track.recent_sweep_hits)
                        if snapshot_v2
                        else ()
                    ),
                    track_state=track.track_state if snapshot_v2 else "legacy_v1",
                    snapshot_contract_version="v2" if snapshot_v2 else "v1",
                )
            )
        tracks[camera_id] = tuple(converted)

    shared_candidate_pairs = _shared_candidate_pairs(snapshot)
    episode = OnlineEpisode(
        seed=snapshot.seed,
        schema_version=(
            "dual-optical-shared-revolution-snapshot-v2"
            if snapshot_v2
            else "dual-optical-shared-revolution-snapshot-v1"
        ),
        configured_target_count=snapshot.target_count,
        camera_ids=snapshot.camera_ids,
        camera_positions_ned={
            camera_id: tuple(
                float(value) for value in snapshot.camera_positions_ned[camera_id]
            )
            for camera_id in snapshot.camera_ids
        },
        focal_length_px=float(snapshot.focal_length_px),
        tracks=tracks,
        source_hashes=dict(snapshot.source_hashes),
        snapshot_contract_version="v2" if snapshot_v2 else "v1",
        geometry_candidate_pairs=shared_candidate_pairs,
        candidate_graph_fingerprint=(
            snapshot.candidate_graph_fingerprint or None
        ),
    )
    summary = CorruptionSummary(
        level=snapshot.corruption_level,
        corruption_seed=_summary_value(snapshot.corruption_summary, "corruption_seed"),
        dropped_sample_count=_summary_value(
            snapshot.corruption_summary, "dropped_sample_count"
        ),
        retained_sample_count=_summary_value(
            snapshot.corruption_summary, "retained_sample_count"
        ),
        transient_false_track_count=_summary_value(
            snapshot.corruption_summary, "transient_false_track_count"
        ),
        persistent_false_track_count=_summary_value(
            snapshot.corruption_summary, "persistent_false_track_count"
        ),
    )
    graph, diagnostics = build_online_graph(
        episode,
        summary,
        gate=GeometryGate(**dict(geometry_gate)),
    )
    return (
        CandidateGraphSnapshot.from_graph(
            graph,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            observation_max_timestamp=maximum_timestamp,
            snapshot_mode="cumulative",
        ),
        {
            **diagnostics,
            "snapshot_v2_available": int(snapshot_v2),
            "frozen_shared_tracker_available": int(snapshot_v2),
            "shared_candidate_allowlist_used": int(
                shared_candidate_pairs is not None
            ),
            "shared_candidate_allowlist_count": (
                len(shared_candidate_pairs)
                if shared_candidate_pairs is not None
                else -1
            ),
            "configured_target_count": (
                int(snapshot.target_count)
                if snapshot.target_count is not None
                else -1
            ),
            "confirmed_or_coasting_track_count": sum(
                track.track_state in {"confirmed", "coasting"}
                for camera_tracks in snapshot.tracks.values()
                for track in camera_tracks
            ),
        },
    )


class SharedSnapshotLightweightAdapter:
    """Stateful public entry point used by the main online benchmark."""

    def __init__(
        self,
        online_adapter: OnlineLightweightAdapter,
        *,
        selected_route_id: str,
    ) -> None:
        route_ids = {item.route_id for item in online_adapter.routes}
        if selected_route_id not in route_ids:
            raise ValueError("selected lightweight route is not loaded")
        self.online_adapter = online_adapter
        self.selected_route_id = selected_route_id
        self.last_route_publications: tuple[OnlineAssociationPublication, ...] = ()
        self.last_graph_diagnostics: Mapping[str, int | float | str] = {}

    def reset(self, seed: int | None = None, corruption_level: str | None = None) -> None:
        self.online_adapter.reset(seed, corruption_level)
        self.last_route_publications = ()
        self.last_graph_diagnostics = {}

    def process(
        self, snapshot: SharedRevolutionSnapshot
    ) -> AssociationPublication:
        """Build one candidate graph, run four routes, and publish the selected route."""

        started_ns = time.perf_counter_ns()
        candidate_started_ns = time.perf_counter_ns()
        candidate_snapshot, diagnostics = _build_candidate_snapshot(
            snapshot, self.online_adapter.geometry_gate
        )
        candidate_finished_ns = time.perf_counter_ns()
        candidate_generation_ms = (
            candidate_finished_ns - candidate_started_ns
        ) / 1.0e6
        route_publications = self.online_adapter.process(
            candidate_snapshot,
            upstream_elapsed_ms=candidate_generation_ms,
        )
        selected = next(
            item
            for item in route_publications
            if item.route_id == self.selected_route_id
        )
        rejection_reasons = dict(selected.rejection_reasons)
        rejection_reasons.update(
            {
                f"graph_{key}": int(value)
                for key, value in diagnostics.items()
                if isinstance(value, (bool, int, np.integer))
            }
        )
        finished_ns = time.perf_counter_ns()
        end_to_end_ms = max(
            (finished_ns - started_ns) / 1.0e6,
            selected.scoring_ms + selected.hungarian_ms,
        )
        deadline_exceeded = (
            end_to_end_ms > selected.latency_budget_ms
            or selected.availability == "timeout"
        )
        if deadline_exceeded:
            rejection_reasons["deadline_exceeded"] = 1
        publication = AssociationPublication(
            route_name="lightweight",
            route_version=(
                f"online-v2:{selected.route_id}:{selected.model_id}"
            ),
            model_fingerprint=selected.model_version,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            input_fingerprint=shared_snapshot_fingerprint(snapshot),
            availability="timeout" if deadline_exceeded else selected.availability,
            matches=tuple(
                AssociationMatch(
                    track_a_id=item.track_a_id,
                    track_b_id=item.track_b_id,
                    score=item.probability,
                    decision_state=item.confirmation_state,
                )
                for item in (() if deadline_exceeded else selected.matches)
            ),
            rejection_reasons=rejection_reasons,
            candidate_graph_fingerprint=str(
                getattr(snapshot, "candidate_graph_fingerprint", "")
            ),
            stage_latencies_ms={
                "candidate_generation": candidate_generation_ms,
                "model_scoring": selected.scoring_ms,
                "hungarian_assignment": selected.hungarian_ms,
                "confirmation_and_publication": selected.confirmation_ms,
            },
            scoring_ms=selected.scoring_ms,
            hungarian_ms=selected.hungarian_ms,
            end_to_end_ms=end_to_end_ms,
            deadline_ms=selected.latency_budget_ms,
        )
        self.last_route_publications = route_publications
        self.last_graph_diagnostics = diagnostics
        return publication
