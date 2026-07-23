"""Fail-closed offline identity mapping for the scalable 3D association path.

The contracts in this module are evaluator-only.  They bind persisted,
truth-free D1/D2 records to a separate observation-to-truth sidecar, then use
source observation lineage to map D2-owned global track IDs to truth IDs.  No
position, target name, actor ID, or terminal proximity is used as identity
evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any


SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION = (
    "d2.scalable3d_identity_evidence.v1"
)
SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION = (
    "d2.scalable3d_observation_truth.v1"
)
SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION = "scalable3d-offline-truth-v1"
SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION = (
    "d2.scalable3d_identity_evaluation.v1"
)
SCALABLE_3D_GLOBAL_TRACK_TRUTH_MAPPING_SCHEMA_VERSION = (
    "d2.scalable3d_global_track_truth_mapping.v1"
)
SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION = (
    "d2.scalable3d_identity_metrics.v1"
)
SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION = (
    "d2.scalable3d_partial_identity_diagnostics.v1"
)
SCALABLE_3D_IDENTITY_POLICY_VERSION = "d2.scalable3d_identity_policy.v1"
SCALABLE_3D_IDENTITY_HASH_ALGORITHM = "sha256"

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTIVE_LIFECYCLE_STATES = frozenset(
    {"tentative", "confirmed", "engageable"}
)
_LIFECYCLE_STATES = _ACTIVE_LIFECYCLE_STATES | {"lost", "dropped"}
_OBSERVED_ASSOCIATION_STATES = frozenset({"created", "matched"})
_ASSOCIATION_STATES = _OBSERVED_ASSOCIATION_STATES | {
    "unmatched",
    "lost",
    "dropped",
}
_IDENTITY_METRIC_NAMES = (
    "id_switch_count",
    "track_continuity",
    "identity_continuity",
    "coverage_continuity",
    "duplicate_truth_to_track_count",
)
_MISSING_IDENTITY_EVIDENCE_REASONS = frozenset(
    {
        "source_lineage_missing",
        "truth_label_missing",
        "truth_mapping_evidence_unavailable",
    }
)
_LOWER_BOUND_ANCHOR_EXCLUSION_REASONS = frozenset(
    {"multiple_evaluable_global_tracks_for_truth_frame"}
)
_PARTIAL_IDENTITY_DIAGNOSTIC_DEFINITIONS = {
    "mapping_denominator": (
        "scored_mapping_count counts created or matched global-track/frame "
        "mappings; lost, dropped, and unmatched audit rows are not scored"
    ),
    "evaluable_mapping": (
        "a scored mapping with status available, exactly one truth target, "
        "and that truth target present in the frame sidecar window"
    ),
    "frame_denominator": (
        "evaluated_frame_count counts every persisted D2 frame represented "
        "by the evidence bundle or verified source records"
    ),
    "evaluable_frame": (
        "a frame with non-empty truth presence where every scored mapping is "
        "evaluable; a frame may be evaluable with zero assigned tracks"
    ),
    "transition_denominator": (
        "transition_opportunity_count is the sum over truth targets of "
        "max(number of truth-present frames minus one, zero)"
    ),
    "evaluable_transition": (
        "an adjacent pair of truth-present frames whose endpoints are both "
        "evaluable and each have exactly one unique evaluable global track "
        "for that truth target"
    ),
    "lower_bound_anchor": (
        "a truth-target/frame pair in an evaluable frame with exactly one "
        "unique evaluable global track; pairs with multiple evaluable global "
        "tracks are excluded rather than ordered into a representative"
    ),
    "lower_bound_anchor_exclusion": (
        "lower_bound_anchor_excluded_truth_frame_count counts truth-target/"
        "frame pairs with more than one unique evaluable global track; such "
        "pairs never become lower-bound anchors even when the frame is "
        "otherwise incomplete"
    ),
    "id_switch_lower_bound": (
        "changes of the unique global_track_id between consecutive "
        "lower-bound anchors for each truth target; anchor intervals are "
        "disjoint and duplicate mappings never select a representative, so "
        "the count is a conservative episode lower bound"
    ),
    "missing_identity_evidence_mapping": (
        "a scored mapping carrying source_lineage_missing, "
        "truth_label_missing, or truth_mapping_evidence_unavailable"
    ),
    "id_switch_upper_bound": (
        "not emitted because missing or ambiguous sidecar evidence does not "
        "establish a complete truth-assignment transition universe"
    ),
}
_REQUIRED_EVALUATION_SOURCE_HASHES = {
    "online_d1_records",
    "online_d2_records",
    "observation_truth_labels",
    "identity_evidence_bundle",
}
_ONLINE_RECORD_CONTRACTS = {
    "d1": (
        "D1",
        "modules.d1.fused_tracks",
        "d1-scalable3d-fusion-v1",
    ),
    "d2": (
        "D2",
        "modules.d2.associated_tracks",
        "d2-scalable3d-association-v1",
    ),
}


@dataclass(frozen=True, slots=True)
class ObservationLineageRef:
    """One truth-free source observation in a D1-to-D2 association lineage."""

    observation_id: str
    measurement_timestamp: float
    source_lineage: tuple[str, ...] = ()
    replay_generation: int = 0

    def __post_init__(self) -> None:
        observation_id = _identifier(self.observation_id, "observation_id")
        timestamp = _timestamp(
            self.measurement_timestamp,
            "source observation measurement_timestamp",
        )
        lineage = tuple(
            _identifier(item, "source_lineage item") for item in self.source_lineage
        )
        if not lineage:
            lineage = (observation_id,)
        if lineage[-1] != observation_id:
            raise ValueError(
                "source_lineage must terminate at its observation_id"
            )
        replay_generation = int(self.replay_generation)
        if replay_generation < 0:
            raise ValueError("replay_generation must be non-negative")
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(self, "measurement_timestamp", timestamp)
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(self, "replay_generation", replay_generation)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ObservationLineageRef":
        _reject_unknown_keys(
            payload,
            {
                "observation_id",
                "measurement_timestamp",
                "source_lineage",
                "replay_generation",
            },
            "observation lineage",
        )
        return cls(
            observation_id=payload["observation_id"],
            measurement_timestamp=payload["measurement_timestamp"],
            source_lineage=tuple(payload.get("source_lineage", ())),
            replay_generation=payload.get("replay_generation", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "measurement_timestamp": self.measurement_timestamp,
            "source_lineage": list(self.source_lineage),
            "replay_generation": self.replay_generation,
        }


@dataclass(frozen=True, slots=True)
class GlobalTrackLineageEvidence:
    """Truth-free lineage evidence for one D2 global track at one frame."""

    episode_id: str
    frame_index: int
    frame_timestamp: float
    global_track_id: str
    lifecycle_state: str
    association_state: str
    source_observations: tuple[ObservationLineageRef, ...] = ()
    d1_record_sequences: tuple[int, ...] = ()
    d2_record_sequence: int | None = None
    schema_version: str = SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported identity evidence schema: {self.schema_version!r}"
            )
        episode_id = _identifier(self.episode_id, "episode_id")
        frame_index = int(self.frame_index)
        if frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        frame_timestamp = _timestamp(self.frame_timestamp, "frame_timestamp")
        global_track_id = _identifier(self.global_track_id, "global_track_id")
        lifecycle_state = str(self.lifecycle_state).strip().lower()
        if lifecycle_state not in _LIFECYCLE_STATES:
            raise ValueError(
                f"unsupported lifecycle_state: {self.lifecycle_state!r}"
            )
        association_state = str(self.association_state).strip().lower()
        if association_state not in _ASSOCIATION_STATES:
            raise ValueError(
                f"unsupported association_state: {self.association_state!r}"
            )
        observations = tuple(
            item
            if isinstance(item, ObservationLineageRef)
            else ObservationLineageRef.from_mapping(_as_mapping(item, "source observation"))
            for item in self.source_observations
        )
        d1_sequences = tuple(int(item) for item in self.d1_record_sequences)
        if any(item < 0 for item in d1_sequences):
            raise ValueError("d1_record_sequences must be non-negative")
        if len(set(d1_sequences)) != len(d1_sequences):
            raise ValueError("d1_record_sequences must not contain duplicates")
        d2_sequence = (
            None
            if self.d2_record_sequence is None
            else int(self.d2_record_sequence)
        )
        if d2_sequence is not None and d2_sequence < 0:
            raise ValueError("d2_record_sequence must be non-negative")
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "frame_index", frame_index)
        object.__setattr__(self, "frame_timestamp", frame_timestamp)
        object.__setattr__(self, "global_track_id", global_track_id)
        object.__setattr__(self, "lifecycle_state", lifecycle_state)
        object.__setattr__(self, "association_state", association_state)
        object.__setattr__(self, "source_observations", observations)
        object.__setattr__(self, "d1_record_sequences", d1_sequences)
        object.__setattr__(self, "d2_record_sequence", d2_sequence)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GlobalTrackLineageEvidence":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "episode_id",
                "frame_index",
                "frame_timestamp",
                "global_track_id",
                "lifecycle_state",
                "association_state",
                "source_observations",
                "d1_record_sequences",
                "d2_record_sequence",
            },
            "global-track lineage evidence",
        )
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            episode_id=payload["episode_id"],
            frame_index=payload["frame_index"],
            frame_timestamp=payload["frame_timestamp"],
            global_track_id=payload["global_track_id"],
            lifecycle_state=payload["lifecycle_state"],
            association_state=payload["association_state"],
            source_observations=tuple(payload.get("source_observations", ())),
            d1_record_sequences=tuple(payload.get("d1_record_sequences", ())),
            d2_record_sequence=payload.get("d2_record_sequence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "frame_index": self.frame_index,
            "frame_timestamp": self.frame_timestamp,
            "global_track_id": self.global_track_id,
            "lifecycle_state": self.lifecycle_state,
            "association_state": self.association_state,
            "source_observations": [
                item.to_dict() for item in self.source_observations
            ],
            "d1_record_sequences": list(self.d1_record_sequences),
            "d2_record_sequence": self.d2_record_sequence,
        }


@dataclass(frozen=True, slots=True)
class Scalable3DIdentityEvidenceBundle:
    """Versioned evidence bundle cryptographically bound to persisted inputs."""

    episode_id: str
    records: tuple[GlobalTrackLineageEvidence, ...]
    source_hashes: Mapping[str, str]
    schema_version: str = SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION
    policy_version: str = SCALABLE_3D_IDENTITY_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported identity evidence schema: {self.schema_version!r}"
            )
        if self.policy_version != SCALABLE_3D_IDENTITY_POLICY_VERSION:
            raise ValueError(
                f"unsupported identity policy: {self.policy_version!r}"
            )
        episode_id = _identifier(self.episode_id, "episode_id")
        records = tuple(
            item
            if isinstance(item, GlobalTrackLineageEvidence)
            else GlobalTrackLineageEvidence.from_mapping(
                _as_mapping(item, "identity evidence record")
            )
            for item in self.records
        )
        if any(item.episode_id != episode_id for item in records):
            raise ValueError("all evidence records must use the bundle episode_id")
        source_hashes = _validated_source_hashes(
            self.source_hashes,
            required={
                "online_d1_records",
                "online_d2_records",
                "observation_truth_labels",
            },
        )
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "source_hashes", source_hashes)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "Scalable3DIdentityEvidenceBundle":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "policy_version",
                "hash_algorithm",
                "episode_id",
                "source_hashes",
                "records",
            },
            "identity evidence bundle",
        )
        if payload.get("hash_algorithm") != SCALABLE_3D_IDENTITY_HASH_ALGORITHM:
            raise ValueError("identity evidence bundle requires sha256 hashes")
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            policy_version=str(payload.get("policy_version", "")),
            episode_id=payload["episode_id"],
            source_hashes=_as_mapping(payload.get("source_hashes"), "source_hashes"),
            records=tuple(payload.get("records", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "hash_algorithm": SCALABLE_3D_IDENTITY_HASH_ALGORITHM,
            "episode_id": self.episode_id,
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "records": [item.to_dict() for item in self.records],
        }


@dataclass(frozen=True, slots=True)
class Scalable3DObservationTruthLabel:
    """Evaluator-only observation-to-truth label, never an online DTO."""

    observation_id: str
    truth_target_id: str
    measurement_timestamp: float
    schema_version: str = SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION
    source_schema_version: str = SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported normalized truth schema: {self.schema_version!r}"
            )
        if self.source_schema_version not in {
            SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION,
            SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION,
        }:
            raise ValueError(
                f"unsupported observation truth schema: {self.source_schema_version!r}"
            )
        object.__setattr__(
            self,
            "observation_id",
            _identifier(self.observation_id, "observation_id"),
        )
        object.__setattr__(
            self,
            "truth_target_id",
            _identifier(self.truth_target_id, "truth_target_id"),
        )
        object.__setattr__(
            self,
            "measurement_timestamp",
            _timestamp(self.measurement_timestamp, "truth measurement_timestamp"),
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "Scalable3DObservationTruthLabel":
        version = str(payload.get("schema_version", ""))
        if version == SCALABLE_3D_EXTERNAL_TRUTH_SCHEMA_VERSION:
            _reject_unknown_keys(
                payload,
                {
                    "schema_version",
                    "observation_id",
                    "measurement_timestamp",
                    "truth_entity_id",
                    "truth_target_id",
                },
                "external observation truth label",
            )
            truth_keys = [
                key
                for key in ("truth_target_id", "truth_entity_id")
                if key in payload
            ]
            if len(truth_keys) != 1:
                raise ValueError(
                    "external truth label requires exactly one truth identity field"
                )
            truth_target_id = payload[truth_keys[0]]
        elif version == SCALABLE_3D_OBSERVATION_TRUTH_SCHEMA_VERSION:
            _reject_unknown_keys(
                payload,
                {
                    "schema_version",
                    "observation_id",
                    "measurement_timestamp",
                    "truth_target_id",
                },
                "D2 observation truth label",
            )
            truth_target_id = payload["truth_target_id"]
        else:
            raise ValueError(f"unsupported observation truth schema: {version!r}")
        return cls(
            observation_id=payload["observation_id"],
            truth_target_id=truth_target_id,
            measurement_timestamp=payload["measurement_timestamp"],
            source_schema_version=version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "measurement_timestamp": self.measurement_timestamp,
            "truth_target_id": self.truth_target_id,
        }


@dataclass(frozen=True, slots=True)
class GlobalTrackTruthMapping:
    """One frame-level evaluator decision for a D2 global track."""

    global_track_id: str
    lifecycle_state: str
    association_state: str
    status: str
    truth_target_id: str | None
    reason: str | None
    unavailable_reasons: tuple[str, ...]
    candidate_truth_target_ids: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    source_lineage_hashes: tuple[str, ...]
    evidence_count: int
    unique_lineage_count: int
    labeled_evidence_count: int
    replayed_lineage_count: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GlobalTrackTruthMapping":
        return cls(
            global_track_id=str(payload["global_track_id"]),
            lifecycle_state=str(payload["lifecycle_state"]),
            association_state=str(payload["association_state"]),
            status=str(payload["status"]),
            truth_target_id=(
                None
                if payload.get("truth_target_id") is None
                else str(payload["truth_target_id"])
            ),
            reason=(None if payload.get("reason") is None else str(payload["reason"])),
            unavailable_reasons=tuple(payload.get("unavailable_reasons", ())),
            candidate_truth_target_ids=tuple(
                payload.get("candidate_truth_target_ids", ())
            ),
            source_observation_ids=tuple(payload.get("source_observation_ids", ())),
            source_lineage_hashes=tuple(payload.get("source_lineage_hashes", ())),
            evidence_count=int(payload.get("evidence_count", 0)),
            unique_lineage_count=int(payload.get("unique_lineage_count", 0)),
            labeled_evidence_count=int(payload.get("labeled_evidence_count", 0)),
            replayed_lineage_count=int(payload.get("replayed_lineage_count", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "lifecycle_state": self.lifecycle_state,
            "association_state": self.association_state,
            "status": self.status,
            "truth_target_id": self.truth_target_id,
            "reason": self.reason,
            "unavailable_reasons": list(self.unavailable_reasons),
            "candidate_truth_target_ids": list(self.candidate_truth_target_ids),
            "source_observation_ids": list(self.source_observation_ids),
            "source_lineage_hashes": list(self.source_lineage_hashes),
            "evidence_count": self.evidence_count,
            "unique_lineage_count": self.unique_lineage_count,
            "labeled_evidence_count": self.labeled_evidence_count,
            "replayed_lineage_count": self.replayed_lineage_count,
        }


@dataclass(frozen=True, slots=True)
class FrameGlobalTrackTruthMapping:
    """All evaluator decisions and audit counts for one D2 frame."""

    frame_index: int
    frame_timestamp: float
    truth_target_ids_present: tuple[str, ...]
    mappings: tuple[GlobalTrackTruthMapping, ...]
    evidence_count: int
    unique_lineage_count: int
    replayed_lineage_count: int
    duplicate_lineage_count: int
    available_mapping_count: int
    ambiguous_mapping_count: int
    unavailable_mapping_count: int
    reason_counts: Mapping[str, int]
    schema_version: str = SCALABLE_3D_GLOBAL_TRACK_TRUTH_MAPPING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != SCALABLE_3D_GLOBAL_TRACK_TRUTH_MAPPING_SCHEMA_VERSION
        ):
            raise ValueError(
                f"unsupported global-track truth mapping schema: {self.schema_version!r}"
            )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "FrameGlobalTrackTruthMapping":
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            frame_index=int(payload["frame_index"]),
            frame_timestamp=float(payload["frame_timestamp"]),
            truth_target_ids_present=tuple(
                payload.get("truth_target_ids_present", ())
            ),
            mappings=tuple(
                GlobalTrackTruthMapping.from_mapping(
                    _as_mapping(item, "frame mapping")
                )
                for item in payload.get("mappings", ())
            ),
            evidence_count=int(payload.get("evidence_count", 0)),
            unique_lineage_count=int(payload.get("unique_lineage_count", 0)),
            replayed_lineage_count=int(payload.get("replayed_lineage_count", 0)),
            duplicate_lineage_count=int(payload.get("duplicate_lineage_count", 0)),
            available_mapping_count=int(payload.get("available_mapping_count", 0)),
            ambiguous_mapping_count=int(payload.get("ambiguous_mapping_count", 0)),
            unavailable_mapping_count=int(payload.get("unavailable_mapping_count", 0)),
            reason_counts={
                str(key): int(value)
                for key, value in _as_mapping(
                    payload.get("reason_counts", {}),
                    "frame reason_counts",
                ).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "frame_index": self.frame_index,
            "frame_timestamp": self.frame_timestamp,
            "truth_target_ids_present": list(self.truth_target_ids_present),
            "mappings": [item.to_dict() for item in self.mappings],
            "evidence_count": self.evidence_count,
            "unique_lineage_count": self.unique_lineage_count,
            "replayed_lineage_count": self.replayed_lineage_count,
            "duplicate_lineage_count": self.duplicate_lineage_count,
            "available_mapping_count": self.available_mapping_count,
            "ambiguous_mapping_count": self.ambiguous_mapping_count,
            "unavailable_mapping_count": self.unavailable_mapping_count,
            "reason_counts": dict(sorted(self.reason_counts.items())),
        }


@dataclass(frozen=True, slots=True)
class Scalable3DIdentityMetrics:
    """MetricsRecorder-compatible identity metrics with explicit availability."""

    available: bool
    reason: str | None
    id_switch_count: int | None
    track_continuity: float | None
    identity_continuity: float | None
    coverage_continuity: float | None
    duplicate_truth_to_track_count: int | None
    confusion_matrix: Mapping[str, Mapping[str, int]] | None
    evaluated_frame_count: int
    truth_frame_count: Mapping[str, int]
    truth_assigned_frame_count: Mapping[str, int]
    truth_identity_stable_frame_count: Mapping[str, int]
    schema_version: str = SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported identity metrics schema: {self.schema_version!r}"
            )
        available = _strict_bool(self.available, "truth_metrics_available")
        evaluated_frame_count = _nonnegative_int(
            self.evaluated_frame_count,
            "evaluated_frame_count",
        )
        truth_frame_count = _count_mapping(
            self.truth_frame_count,
            "truth_frame_count",
        )
        truth_assigned_frame_count = _count_mapping(
            self.truth_assigned_frame_count,
            "truth_assigned_frame_count",
        )
        stable_frame_count = _count_mapping(
            self.truth_identity_stable_frame_count,
            "truth_identity_stable_frame_count",
        )
        unknown_assigned = set(truth_assigned_frame_count) - set(truth_frame_count)
        unknown_stable = set(stable_frame_count) - set(truth_frame_count)
        if unknown_assigned or unknown_stable:
            raise ValueError("identity metric counts reference unknown truth targets")
        for truth_id, frame_count in truth_frame_count.items():
            assigned = truth_assigned_frame_count.get(truth_id, 0)
            stable = stable_frame_count.get(truth_id, 0)
            if assigned > frame_count or stable > assigned:
                raise ValueError(
                    "identity metric counts must satisfy stable <= assigned <= present"
                )

        if available:
            if self.reason is not None:
                raise ValueError("available identity metrics must not carry a reason")
            id_switch_count = _nonnegative_int(
                self.id_switch_count,
                "id_switch_count",
            )
            duplicate_count = _nonnegative_int(
                self.duplicate_truth_to_track_count,
                "duplicate_truth_to_track_count",
            )
            track_continuity = _unit_interval(
                self.track_continuity,
                "track_continuity",
            )
            identity_continuity = _unit_interval(
                self.identity_continuity,
                "identity_continuity",
            )
            coverage_continuity = _unit_interval(
                self.coverage_continuity,
                "coverage_continuity",
            )
            if abs(track_continuity - identity_continuity) > 1.0e-12:
                raise ValueError(
                    "track_continuity must equal identity_continuity in policy v1"
                )
            if not truth_frame_count:
                raise ValueError(
                    "available identity metrics require truth-frame evidence"
                )
            if self.confusion_matrix is None:
                raise ValueError(
                    "available identity metrics require a confusion matrix"
                )
            confusion = _count_matrix(self.confusion_matrix, "confusion_matrix")
        else:
            reason = _required_reason(self.reason, "truth_metrics_reason")
            if any(
                value is not None
                for value in (
                    self.id_switch_count,
                    self.track_continuity,
                    self.identity_continuity,
                    self.coverage_continuity,
                    self.duplicate_truth_to_track_count,
                    self.confusion_matrix,
                )
            ):
                raise ValueError(
                    "unavailable identity metrics must not carry metric values"
                )
            id_switch_count = None
            duplicate_count = None
            track_continuity = None
            identity_continuity = None
            coverage_continuity = None
            confusion = None
            object.__setattr__(self, "reason", reason)

        object.__setattr__(self, "available", available)
        object.__setattr__(self, "id_switch_count", id_switch_count)
        object.__setattr__(
            self,
            "duplicate_truth_to_track_count",
            duplicate_count,
        )
        object.__setattr__(self, "track_continuity", track_continuity)
        object.__setattr__(self, "identity_continuity", identity_continuity)
        object.__setattr__(self, "coverage_continuity", coverage_continuity)
        object.__setattr__(self, "confusion_matrix", confusion)
        object.__setattr__(self, "evaluated_frame_count", evaluated_frame_count)
        object.__setattr__(self, "truth_frame_count", truth_frame_count)
        object.__setattr__(
            self,
            "truth_assigned_frame_count",
            truth_assigned_frame_count,
        )
        object.__setattr__(
            self,
            "truth_identity_stable_frame_count",
            stable_frame_count,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Scalable3DIdentityMetrics":
        allowed = {
            "schema_version",
            "evaluated_frame_count",
            "truth_metrics_available",
            "truth_metrics_reason",
            "continuity_available",
            "continuity_reason",
            "confusion_matrix",
            "truth_frame_count",
            "truth_assigned_frame_count",
            "truth_identity_stable_frame_count",
            "duplicate_assignment_count",
            "duplicate_assignment_count_available",
            "duplicate_assignment_count_reason",
        }
        for name in _IDENTITY_METRIC_NAMES:
            allowed.update({name, f"{name}_available", f"{name}_reason"})
        _reject_unknown_keys(payload, allowed, "identity metrics")
        required = allowed - {"confusion_matrix"}
        missing = required - set(payload)
        if missing:
            raise ValueError(
                f"identity metrics are missing required fields: {sorted(missing)}"
            )

        available = _strict_bool(
            payload["truth_metrics_available"],
            "truth_metrics_available",
        )
        reason = _optional_reason(payload.get("truth_metrics_reason"))
        if _strict_bool(
            payload["continuity_available"],
            "continuity_available",
        ) != available:
            raise ValueError("continuity availability contradicts truth metrics")
        if _optional_reason(payload.get("continuity_reason")) != reason:
            raise ValueError("continuity reason contradicts truth metrics")
        for name in _IDENTITY_METRIC_NAMES:
            if _strict_bool(payload[f"{name}_available"], f"{name}_available") != available:
                raise ValueError(f"{name} availability contradicts truth metrics")
            if _optional_reason(payload.get(f"{name}_reason")) != reason:
                raise ValueError(f"{name} reason contradicts truth metrics")

        duplicate_value = payload.get("duplicate_truth_to_track_count")
        if payload.get("duplicate_assignment_count") != duplicate_value:
            raise ValueError(
                "duplicate_assignment_count must alias "
                "duplicate_truth_to_track_count"
            )
        if _strict_bool(
            payload["duplicate_assignment_count_available"],
            "duplicate_assignment_count_available",
        ) != available:
            raise ValueError("duplicate assignment availability is inconsistent")
        if _optional_reason(payload.get("duplicate_assignment_count_reason")) != reason:
            raise ValueError("duplicate assignment reason is inconsistent")

        confusion = payload.get("confusion_matrix")
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            available=available,
            reason=reason,
            id_switch_count=_optional_int(payload.get("id_switch_count")),
            track_continuity=_optional_float(payload.get("track_continuity")),
            identity_continuity=_optional_float(
                payload.get("identity_continuity")
            ),
            coverage_continuity=_optional_float(
                payload.get("coverage_continuity")
            ),
            duplicate_truth_to_track_count=_optional_int(
                payload.get("duplicate_truth_to_track_count")
            ),
            confusion_matrix=(
                None
                if confusion is None
                else _count_matrix(confusion, "confusion_matrix")
            ),
            evaluated_frame_count=int(payload.get("evaluated_frame_count", 0)),
            truth_frame_count=_count_mapping(
                payload.get("truth_frame_count", {}),
                "truth_frame_count",
            ),
            truth_assigned_frame_count=_count_mapping(
                payload.get("truth_assigned_frame_count", {}),
                "truth_assigned_frame_count",
            ),
            truth_identity_stable_frame_count=_count_mapping(
                payload.get("truth_identity_stable_frame_count", {}),
                "truth_identity_stable_frame_count",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        reason = None if self.available else self.reason
        duplicate = (
            self.duplicate_truth_to_track_count if self.available else None
        )
        return {
            "schema_version": self.schema_version,
            "evaluated_frame_count": self.evaluated_frame_count,
            "id_switch_count": self.id_switch_count if self.available else None,
            "id_switch_count_available": self.available,
            "id_switch_count_reason": reason,
            "track_continuity": self.track_continuity if self.available else None,
            "track_continuity_available": self.available,
            "track_continuity_reason": reason,
            "identity_continuity": (
                self.identity_continuity if self.available else None
            ),
            "identity_continuity_available": self.available,
            "identity_continuity_reason": reason,
            "coverage_continuity": (
                self.coverage_continuity if self.available else None
            ),
            "coverage_continuity_available": self.available,
            "coverage_continuity_reason": reason,
            "duplicate_truth_to_track_count": duplicate,
            "duplicate_truth_to_track_count_available": self.available,
            "duplicate_truth_to_track_count_reason": reason,
            "duplicate_assignment_count": duplicate,
            "duplicate_assignment_count_available": self.available,
            "duplicate_assignment_count_reason": reason,
            "truth_metrics_available": self.available,
            "truth_metrics_reason": reason,
            "continuity_available": self.available,
            "continuity_reason": reason,
            "confusion_matrix": (
                None
                if not self.available or self.confusion_matrix is None
                else {
                    truth_id: dict(sorted(track_counts.items()))
                    for truth_id, track_counts in sorted(
                        self.confusion_matrix.items()
                    )
                }
            ),
            "truth_frame_count": dict(sorted(self.truth_frame_count.items())),
            "truth_assigned_frame_count": dict(
                sorted(self.truth_assigned_frame_count.items())
            ),
            "truth_identity_stable_frame_count": dict(
                sorted(self.truth_identity_stable_frame_count.items())
            ),
        }


@dataclass(frozen=True, slots=True)
class Scalable3DPartialIdentityDiagnostics:
    """Auditable partial identity evidence without relaxing strict metrics."""

    total_mapping_count: int
    available_mapping_count: int
    ambiguous_mapping_count: int
    unavailable_mapping_count: int
    scored_mapping_count: int
    non_scored_mapping_count: int
    evaluable_mapping_count: int
    ambiguous_scored_mapping_count: int
    unavailable_scored_mapping_count: int
    mapped_truth_not_present_mapping_count: int
    missing_identity_evidence_mapping_count: int
    evaluable_mapping_coverage: float | None
    evaluable_mapping_coverage_reason: str | None
    evaluated_frame_count: int
    evaluable_frame_count: int
    evaluable_frame_coverage: float | None
    evaluable_frame_coverage_reason: str | None
    transition_opportunity_count: int
    evaluable_transition_count: int
    evaluable_transition_coverage: float | None
    evaluable_transition_coverage_reason: str | None
    lower_bound_anchor_excluded_truth_frame_count: int
    lower_bound_anchor_exclusion_reason_counts: Mapping[str, int]
    lower_bound_anchor_transition_count: int
    id_switch_lower_bound: int | None
    id_switch_lower_bound_reason: str | None
    excluded_scored_mapping_reason_counts: Mapping[str, int]
    schema_version: str = (
        SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported scalable 3D partial identity diagnostics schema"
            )
        count_names = (
            "total_mapping_count",
            "available_mapping_count",
            "ambiguous_mapping_count",
            "unavailable_mapping_count",
            "scored_mapping_count",
            "non_scored_mapping_count",
            "evaluable_mapping_count",
            "ambiguous_scored_mapping_count",
            "unavailable_scored_mapping_count",
            "mapped_truth_not_present_mapping_count",
            "missing_identity_evidence_mapping_count",
            "evaluated_frame_count",
            "evaluable_frame_count",
            "transition_opportunity_count",
            "evaluable_transition_count",
            "lower_bound_anchor_excluded_truth_frame_count",
            "lower_bound_anchor_transition_count",
        )
        counts = {
            name: _nonnegative_int(getattr(self, name), name)
            for name in count_names
        }
        if (
            counts["available_mapping_count"]
            + counts["ambiguous_mapping_count"]
            + counts["unavailable_mapping_count"]
            != counts["total_mapping_count"]
        ):
            raise ValueError(
                "partial identity mapping status counts must sum to total"
            )
        if counts["scored_mapping_count"] > counts["total_mapping_count"]:
            raise ValueError("scored mapping count exceeds total mapping count")
        if (
            counts["scored_mapping_count"]
            + counts["non_scored_mapping_count"]
            != counts["total_mapping_count"]
        ):
            raise ValueError(
                "scored and non-scored mapping counts must sum to total"
            )
        if (
            counts["evaluable_mapping_count"]
            + counts["ambiguous_scored_mapping_count"]
            + counts["unavailable_scored_mapping_count"]
            + counts["mapped_truth_not_present_mapping_count"]
            != counts["scored_mapping_count"]
        ):
            raise ValueError(
                "partial identity scored mapping categories are incomplete"
            )
        if counts["missing_identity_evidence_mapping_count"] > (
            counts["ambiguous_scored_mapping_count"]
            + counts["unavailable_scored_mapping_count"]
        ):
            raise ValueError(
                "missing identity evidence count exceeds unresolved scored mappings"
            )
        if counts["evaluable_frame_count"] > counts["evaluated_frame_count"]:
            raise ValueError("evaluable frame count exceeds evaluated frame count")
        if (
            counts["evaluable_transition_count"]
            > counts["transition_opportunity_count"]
        ):
            raise ValueError(
                "evaluable transition count exceeds transition opportunities"
            )
        if (
            counts["lower_bound_anchor_transition_count"]
            > counts["transition_opportunity_count"]
        ):
            raise ValueError(
                "lower-bound anchor transitions exceed transition opportunities"
            )
        anchor_exclusion_reason_counts = _count_mapping(
            self.lower_bound_anchor_exclusion_reason_counts,
            "lower_bound_anchor_exclusion_reason_counts",
        )
        unsupported_anchor_exclusion_reasons = (
            set(anchor_exclusion_reason_counts)
            - _LOWER_BOUND_ANCHOR_EXCLUSION_REASONS
        )
        if unsupported_anchor_exclusion_reasons:
            raise ValueError(
                "unsupported lower-bound anchor exclusion reasons: "
                f"{sorted(unsupported_anchor_exclusion_reasons)}"
            )
        if sum(anchor_exclusion_reason_counts.values()) != counts[
            "lower_bound_anchor_excluded_truth_frame_count"
        ]:
            raise ValueError(
                "lower-bound anchor exclusion reason counts must sum to "
                "the excluded truth-frame count"
            )

        mapping_coverage, mapping_reason = _validated_partial_coverage(
            self.evaluable_mapping_coverage,
            self.evaluable_mapping_coverage_reason,
            numerator=counts["evaluable_mapping_count"],
            denominator=counts["scored_mapping_count"],
            unavailable_reason="no_scored_identity_mappings",
            name="evaluable_mapping_coverage",
        )
        frame_coverage, frame_reason = _validated_partial_coverage(
            self.evaluable_frame_coverage,
            self.evaluable_frame_coverage_reason,
            numerator=counts["evaluable_frame_count"],
            denominator=counts["evaluated_frame_count"],
            unavailable_reason="no_evaluated_identity_frames",
            name="evaluable_frame_coverage",
        )
        transition_coverage, transition_reason = _validated_partial_coverage(
            self.evaluable_transition_coverage,
            self.evaluable_transition_coverage_reason,
            numerator=counts["evaluable_transition_count"],
            denominator=counts["transition_opportunity_count"],
            unavailable_reason="no_truth_presence_transition_opportunities",
            name="evaluable_transition_coverage",
        )

        lower_bound_reason = _optional_reason(self.id_switch_lower_bound_reason)
        if counts["lower_bound_anchor_transition_count"] == 0:
            if self.id_switch_lower_bound is not None:
                raise ValueError(
                    "ID-switch lower bound requires an evaluable anchor transition"
                )
            if lower_bound_reason != "no_evaluable_identity_transitions":
                raise ValueError(
                    "unavailable ID-switch lower bound has an invalid reason"
                )
            lower_bound = None
        else:
            lower_bound = _nonnegative_int(
                self.id_switch_lower_bound,
                "id_switch_lower_bound",
            )
            if lower_bound > counts["lower_bound_anchor_transition_count"]:
                raise ValueError(
                    "ID-switch lower bound exceeds evaluated anchor transitions"
                )
            if lower_bound_reason is not None:
                raise ValueError(
                    "available ID-switch lower bound must not carry a reason"
                )

        for name, value in counts.items():
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "evaluable_mapping_coverage",
            mapping_coverage,
        )
        object.__setattr__(
            self,
            "evaluable_mapping_coverage_reason",
            mapping_reason,
        )
        object.__setattr__(self, "evaluable_frame_coverage", frame_coverage)
        object.__setattr__(
            self,
            "evaluable_frame_coverage_reason",
            frame_reason,
        )
        object.__setattr__(
            self,
            "evaluable_transition_coverage",
            transition_coverage,
        )
        object.__setattr__(
            self,
            "evaluable_transition_coverage_reason",
            transition_reason,
        )
        object.__setattr__(self, "id_switch_lower_bound", lower_bound)
        object.__setattr__(
            self,
            "id_switch_lower_bound_reason",
            lower_bound_reason,
        )
        object.__setattr__(
            self,
            "lower_bound_anchor_exclusion_reason_counts",
            anchor_exclusion_reason_counts,
        )
        object.__setattr__(
            self,
            "excluded_scored_mapping_reason_counts",
            _count_mapping(
                self.excluded_scored_mapping_reason_counts,
                "excluded_scored_mapping_reason_counts",
            ),
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "Scalable3DPartialIdentityDiagnostics":
        allowed = {
            "schema_version",
            "scope",
            "denominator_definitions",
            "total_mapping_count",
            "available_mapping_count",
            "ambiguous_mapping_count",
            "unavailable_mapping_count",
            "scored_mapping_count",
            "non_scored_mapping_count",
            "evaluable_mapping_count",
            "ambiguous_scored_mapping_count",
            "unavailable_scored_mapping_count",
            "mapped_truth_not_present_mapping_count",
            "missing_identity_evidence_mapping_count",
            "evaluable_mapping_coverage",
            "evaluable_mapping_coverage_available",
            "evaluable_mapping_coverage_reason",
            "evaluated_frame_count",
            "evaluable_frame_count",
            "evaluable_frame_coverage",
            "evaluable_frame_coverage_available",
            "evaluable_frame_coverage_reason",
            "transition_opportunity_count",
            "evaluable_transition_count",
            "evaluable_transition_coverage",
            "evaluable_transition_coverage_available",
            "evaluable_transition_coverage_reason",
            "lower_bound_anchor_excluded_truth_frame_count",
            "lower_bound_anchor_exclusion_reason_counts",
            "lower_bound_anchor_transition_count",
            "id_switch_lower_bound",
            "id_switch_lower_bound_available",
            "id_switch_lower_bound_reason",
            "id_switch_upper_bound",
            "id_switch_upper_bound_available",
            "id_switch_upper_bound_reason",
            "excluded_scored_mapping_reason_counts",
        }
        _reject_unknown_keys(payload, allowed, "partial identity diagnostics")
        missing = allowed - set(payload)
        if missing:
            raise ValueError(
                "partial identity diagnostics are missing required fields: "
                f"{sorted(missing)}"
            )
        if payload.get("scope") != "offline_lineage_truth_sidecar_only":
            raise ValueError("partial identity diagnostics use an invalid scope")
        definitions = {
            str(key): str(value)
            for key, value in _as_mapping(
                payload.get("denominator_definitions"),
                "partial identity denominator definitions",
            ).items()
        }
        if definitions != _PARTIAL_IDENTITY_DIAGNOSTIC_DEFINITIONS:
            raise ValueError(
                "partial identity denominator definitions do not match policy"
            )
        for coverage_name in (
            "evaluable_mapping_coverage",
            "evaluable_frame_coverage",
            "evaluable_transition_coverage",
        ):
            available = _strict_bool(
                payload[f"{coverage_name}_available"],
                f"{coverage_name}_available",
            )
            if available != (payload.get(coverage_name) is not None):
                raise ValueError(
                    f"{coverage_name} availability contradicts its value"
                )
        lower_available = _strict_bool(
            payload["id_switch_lower_bound_available"],
            "id_switch_lower_bound_available",
        )
        if lower_available != (payload.get("id_switch_lower_bound") is not None):
            raise ValueError(
                "ID-switch lower-bound availability contradicts its value"
            )
        if (
            payload.get("id_switch_upper_bound") is not None
            or payload.get("id_switch_upper_bound_available") is not False
            or payload.get("id_switch_upper_bound_reason")
            != "not_provided_incomplete_identity_evidence"
        ):
            raise ValueError(
                "partial identity diagnostics must not fabricate an upper bound"
            )
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            total_mapping_count=payload["total_mapping_count"],
            available_mapping_count=payload["available_mapping_count"],
            ambiguous_mapping_count=payload["ambiguous_mapping_count"],
            unavailable_mapping_count=payload["unavailable_mapping_count"],
            scored_mapping_count=payload["scored_mapping_count"],
            non_scored_mapping_count=payload["non_scored_mapping_count"],
            evaluable_mapping_count=payload["evaluable_mapping_count"],
            ambiguous_scored_mapping_count=payload[
                "ambiguous_scored_mapping_count"
            ],
            unavailable_scored_mapping_count=payload[
                "unavailable_scored_mapping_count"
            ],
            mapped_truth_not_present_mapping_count=payload[
                "mapped_truth_not_present_mapping_count"
            ],
            missing_identity_evidence_mapping_count=payload[
                "missing_identity_evidence_mapping_count"
            ],
            evaluable_mapping_coverage=_optional_float(
                payload.get("evaluable_mapping_coverage")
            ),
            evaluable_mapping_coverage_reason=_optional_reason(
                payload.get("evaluable_mapping_coverage_reason")
            ),
            evaluated_frame_count=payload["evaluated_frame_count"],
            evaluable_frame_count=payload["evaluable_frame_count"],
            evaluable_frame_coverage=_optional_float(
                payload.get("evaluable_frame_coverage")
            ),
            evaluable_frame_coverage_reason=_optional_reason(
                payload.get("evaluable_frame_coverage_reason")
            ),
            transition_opportunity_count=payload[
                "transition_opportunity_count"
            ],
            evaluable_transition_count=payload["evaluable_transition_count"],
            evaluable_transition_coverage=_optional_float(
                payload.get("evaluable_transition_coverage")
            ),
            evaluable_transition_coverage_reason=_optional_reason(
                payload.get("evaluable_transition_coverage_reason")
            ),
            lower_bound_anchor_excluded_truth_frame_count=payload[
                "lower_bound_anchor_excluded_truth_frame_count"
            ],
            lower_bound_anchor_exclusion_reason_counts=_as_mapping(
                payload.get("lower_bound_anchor_exclusion_reason_counts"),
                "lower-bound anchor exclusion reason counts",
            ),
            lower_bound_anchor_transition_count=payload[
                "lower_bound_anchor_transition_count"
            ],
            id_switch_lower_bound=_optional_int(
                payload.get("id_switch_lower_bound")
            ),
            id_switch_lower_bound_reason=_optional_reason(
                payload.get("id_switch_lower_bound_reason")
            ),
            excluded_scored_mapping_reason_counts=_as_mapping(
                payload.get("excluded_scored_mapping_reason_counts"),
                "excluded scored mapping reason counts",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope": "offline_lineage_truth_sidecar_only",
            "denominator_definitions": dict(
                _PARTIAL_IDENTITY_DIAGNOSTIC_DEFINITIONS
            ),
            "total_mapping_count": self.total_mapping_count,
            "available_mapping_count": self.available_mapping_count,
            "ambiguous_mapping_count": self.ambiguous_mapping_count,
            "unavailable_mapping_count": self.unavailable_mapping_count,
            "scored_mapping_count": self.scored_mapping_count,
            "non_scored_mapping_count": self.non_scored_mapping_count,
            "evaluable_mapping_count": self.evaluable_mapping_count,
            "ambiguous_scored_mapping_count": (
                self.ambiguous_scored_mapping_count
            ),
            "unavailable_scored_mapping_count": (
                self.unavailable_scored_mapping_count
            ),
            "mapped_truth_not_present_mapping_count": (
                self.mapped_truth_not_present_mapping_count
            ),
            "missing_identity_evidence_mapping_count": (
                self.missing_identity_evidence_mapping_count
            ),
            "evaluable_mapping_coverage": self.evaluable_mapping_coverage,
            "evaluable_mapping_coverage_available": (
                self.evaluable_mapping_coverage is not None
            ),
            "evaluable_mapping_coverage_reason": (
                self.evaluable_mapping_coverage_reason
            ),
            "evaluated_frame_count": self.evaluated_frame_count,
            "evaluable_frame_count": self.evaluable_frame_count,
            "evaluable_frame_coverage": self.evaluable_frame_coverage,
            "evaluable_frame_coverage_available": (
                self.evaluable_frame_coverage is not None
            ),
            "evaluable_frame_coverage_reason": (
                self.evaluable_frame_coverage_reason
            ),
            "transition_opportunity_count": self.transition_opportunity_count,
            "evaluable_transition_count": self.evaluable_transition_count,
            "evaluable_transition_coverage": (
                self.evaluable_transition_coverage
            ),
            "evaluable_transition_coverage_available": (
                self.evaluable_transition_coverage is not None
            ),
            "evaluable_transition_coverage_reason": (
                self.evaluable_transition_coverage_reason
            ),
            "lower_bound_anchor_excluded_truth_frame_count": (
                self.lower_bound_anchor_excluded_truth_frame_count
            ),
            "lower_bound_anchor_exclusion_reason_counts": dict(
                sorted(
                    self.lower_bound_anchor_exclusion_reason_counts.items()
                )
            ),
            "lower_bound_anchor_transition_count": (
                self.lower_bound_anchor_transition_count
            ),
            "id_switch_lower_bound": self.id_switch_lower_bound,
            "id_switch_lower_bound_available": (
                self.id_switch_lower_bound is not None
            ),
            "id_switch_lower_bound_reason": self.id_switch_lower_bound_reason,
            "id_switch_upper_bound": None,
            "id_switch_upper_bound_available": False,
            "id_switch_upper_bound_reason": (
                "not_provided_incomplete_identity_evidence"
            ),
            "excluded_scored_mapping_reason_counts": dict(
                sorted(self.excluded_scored_mapping_reason_counts.items())
            ),
        }


@dataclass(frozen=True, slots=True)
class Scalable3DIdentityEvaluation:
    """Portable evaluator artifact consumed by main and D6."""

    episode_id: str
    source_hashes: Mapping[str, str]
    frames: tuple[FrameGlobalTrackTruthMapping, ...]
    metrics: Scalable3DIdentityMetrics
    configuration: Mapping[str, Any]
    audit: Mapping[str, Any]
    partial_identity_diagnostics: (
        Scalable3DPartialIdentityDiagnostics | None
    ) = None
    schema_version: str = SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION
    policy_version: str = SCALABLE_3D_IDENTITY_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported identity evaluation schema: {self.schema_version!r}"
            )
        if self.policy_version != SCALABLE_3D_IDENTITY_POLICY_VERSION:
            raise ValueError(
                f"unsupported identity policy: {self.policy_version!r}"
            )
        object.__setattr__(
            self,
            "episode_id",
            _identifier(self.episode_id, "episode_id"),
        )
        frames = tuple(self.frames)
        if any(not isinstance(item, FrameGlobalTrackTruthMapping) for item in frames):
            raise ValueError("identity evaluation frames use an unsupported type")
        frame_indices = [item.frame_index for item in frames]
        if frame_indices != sorted(frame_indices) or len(set(frame_indices)) != len(
            frame_indices
        ):
            raise ValueError(
                "identity evaluation frame indices must be unique and ordered"
            )
        if not isinstance(self.metrics, Scalable3DIdentityMetrics):
            raise ValueError("identity evaluation metrics use an unsupported type")
        if self.metrics.evaluated_frame_count != len(frames):
            raise ValueError(
                "identity metric evaluated_frame_count does not match frames"
            )
        partial_diagnostics = self.partial_identity_diagnostics
        if partial_diagnostics is not None:
            if not isinstance(
                partial_diagnostics,
                Scalable3DPartialIdentityDiagnostics,
            ):
                raise ValueError(
                    "partial identity diagnostics use an unsupported type"
                )
            expected_partial_diagnostics = _partial_identity_diagnostics(
                {
                    frame.frame_index: frame.mappings
                    for frame in frames
                },
                {
                    frame.frame_index: frame.truth_target_ids_present
                    for frame in frames
                },
            )
            if (
                partial_diagnostics.to_dict()
                != expected_partial_diagnostics.to_dict()
            ):
                raise ValueError(
                    "partial identity diagnostics contradict frame mappings"
                )
        object.__setattr__(
            self,
            "source_hashes",
            _validated_source_hashes(
                self.source_hashes,
                required=_REQUIRED_EVALUATION_SOURCE_HASHES,
            ),
        )
        object.__setattr__(self, "frames", frames)
        object.__setattr__(
            self,
            "partial_identity_diagnostics",
            partial_diagnostics,
        )
        object.__setattr__(self, "configuration", dict(self.configuration))
        object.__setattr__(self, "audit", dict(self.audit))

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "Scalable3DIdentityEvaluation":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "policy_version",
                "hash_algorithm",
                "episode_id",
                "source_hashes",
                "configuration",
                "frames",
                "metrics",
                "audit",
                "partial_identity_diagnostics",
            },
            "identity evaluation",
        )
        if payload.get("hash_algorithm") != SCALABLE_3D_IDENTITY_HASH_ALGORITHM:
            raise ValueError("identity evaluation requires sha256 hashes")
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            policy_version=str(payload.get("policy_version", "")),
            episode_id=payload["episode_id"],
            source_hashes=_as_mapping(payload.get("source_hashes"), "source_hashes"),
            configuration=_as_mapping(
                payload.get("configuration", {}),
                "configuration",
            ),
            frames=tuple(
                FrameGlobalTrackTruthMapping.from_mapping(
                    _as_mapping(item, "evaluation frame")
                )
                for item in payload.get("frames", ())
            ),
            metrics=Scalable3DIdentityMetrics.from_mapping(
                _as_mapping(payload.get("metrics"), "metrics")
            ),
            audit=_as_mapping(payload.get("audit", {}), "audit"),
            partial_identity_diagnostics=(
                None
                if payload.get("partial_identity_diagnostics") is None
                else Scalable3DPartialIdentityDiagnostics.from_mapping(
                    _as_mapping(
                        payload.get("partial_identity_diagnostics"),
                        "partial_identity_diagnostics",
                    )
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "hash_algorithm": SCALABLE_3D_IDENTITY_HASH_ALGORITHM,
            "episode_id": self.episode_id,
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "configuration": dict(self.configuration),
            "frames": [item.to_dict() for item in self.frames],
            "metrics": self.metrics.to_dict(),
            "audit": dict(self.audit),
        }
        if self.partial_identity_diagnostics is not None:
            payload["partial_identity_diagnostics"] = (
                self.partial_identity_diagnostics.to_dict()
            )
        return payload


@dataclass(slots=True)
class _TrackFrameGroup:
    frame_index: int
    frame_timestamp: float
    global_track_id: str
    records: list[tuple[int, GlobalTrackLineageEvidence]] = field(
        default_factory=list
    )
    issues: set[str] = field(default_factory=set)
    replayed_lineage_count: int = 0

    @property
    def first_order(self) -> int:
        return min(index for index, _ in self.records)

    @property
    def refs(self) -> list[ObservationLineageRef]:
        return [
            ref
            for _, record in self.records
            for ref in record.source_observations
        ]

    @property
    def lifecycle_state(self) -> str:
        return self.records[0][1].lifecycle_state

    @property
    def association_state(self) -> str:
        return self.records[0][1].association_state


def create_scalable_3d_identity_evidence_bundle(
    *,
    episode_id: str,
    records: Iterable[GlobalTrackLineageEvidence | Mapping[str, Any]],
    online_d1_records_sha256: str,
    online_d2_records_sha256: str,
    observation_truth_labels_sha256: str,
) -> Scalable3DIdentityEvidenceBundle:
    """Create the public D2 evidence bundle without reading private tracker state."""

    return Scalable3DIdentityEvidenceBundle(
        episode_id=episode_id,
        records=tuple(records),
        source_hashes={
            "online_d1_records": online_d1_records_sha256,
            "online_d2_records": online_d2_records_sha256,
            "observation_truth_labels": observation_truth_labels_sha256,
        },
    )


def evaluate_scalable_3d_identity(
    evidence: Scalable3DIdentityEvidenceBundle | Mapping[str, Any],
    truth_labels: Iterable[
        Scalable3DObservationTruthLabel | Mapping[str, Any]
    ],
    *,
    timestamp_tolerance_s: float = 1.0e-9,
    lineage_time_window_s: float = 1.0,
    truth_presence_window_s: float | None = None,
) -> Scalable3DIdentityEvaluation:
    """Evaluate in-memory DTOs after validating their canonical source hash."""

    bundle = _coerce_bundle(evidence)
    labels = _coerce_truth_labels(truth_labels)
    canonical_truth_hash = hash_scalable_3d_observation_truth_labels(labels)
    if bundle.source_hashes["observation_truth_labels"] != canonical_truth_hash:
        raise ValueError(
            "observation truth hash mismatch; in-memory evaluation fails closed"
        )
    bundle_hash = hash_scalable_3d_identity_evidence(bundle)
    return _evaluate_scalable_3d_identity(
        bundle,
        labels,
        evidence_bundle_sha256=bundle_hash,
        timestamp_tolerance_s=timestamp_tolerance_s,
        lineage_time_window_s=lineage_time_window_s,
        truth_presence_window_s=truth_presence_window_s,
        source_verification="canonical_dto_hashes_verified",
        online_truth_isolation_verified=False,
        source_frame_timestamps=None,
        source_record_semantics_verified=False,
    )


def evaluate_scalable_3d_identity_files(
    *,
    evidence_path: str | Path,
    expected_evidence_sha256: str,
    online_d1_records_path: str | Path,
    online_d2_records_path: str | Path,
    observation_truth_labels_path: str | Path,
    timestamp_tolerance_s: float = 1.0e-9,
    lineage_time_window_s: float = 1.0,
    truth_presence_window_s: float | None = None,
) -> Scalable3DIdentityEvaluation:
    """Verify all persisted sources, then produce the evaluator artifact.

    The evidence bundle stores the expected D1, D2, and truth hashes.  Its own
    expected hash is supplied by the episode manifest.  Unsupported schemas,
    stale hashes, missing record references, and online identity leakage raise
    ``ValueError`` before any identity metric is produced.
    """

    bundle = load_scalable_3d_identity_evidence(
        evidence_path,
        expected_sha256=expected_evidence_sha256,
    )
    actual_hashes = {
        "online_d1_records": sha256_file(online_d1_records_path),
        "online_d2_records": sha256_file(online_d2_records_path),
        "observation_truth_labels": sha256_file(
            observation_truth_labels_path
        ),
    }
    for name, actual in actual_hashes.items():
        expected = bundle.source_hashes[name]
        if actual != expected:
            raise ValueError(
                f"{name} sha256 mismatch: expected {expected}, got {actual}"
            )

    d1_records = _load_online_json_records(
        online_d1_records_path,
        module="d1",
    )
    d2_records = _load_online_json_records(
        online_d2_records_path,
        module="d2",
    )
    assert_scalable_3d_online_identity_records_truth_free(
        d1_records,
        source_name="online_d1_records",
    )
    assert_scalable_3d_online_identity_records_truth_free(
        d2_records,
        source_name="online_d2_records",
    )
    source_frame_timestamps = _validate_source_record_references(
        bundle.records,
        d1_records,
        d2_records,
    )
    labels = load_scalable_3d_observation_truth_labels(
        observation_truth_labels_path,
        expected_sha256=actual_hashes["observation_truth_labels"],
    )
    return _evaluate_scalable_3d_identity(
        bundle,
        labels,
        evidence_bundle_sha256=_normalized_sha256(expected_evidence_sha256),
        timestamp_tolerance_s=timestamp_tolerance_s,
        lineage_time_window_s=lineage_time_window_s,
        truth_presence_window_s=truth_presence_window_s,
        source_verification="raw_source_hashes_and_record_sequences_verified",
        online_truth_isolation_verified=True,
        source_frame_timestamps=source_frame_timestamps,
        source_record_semantics_verified=True,
    )


def _evaluate_scalable_3d_identity(
    bundle: Scalable3DIdentityEvidenceBundle,
    labels: Sequence[Scalable3DObservationTruthLabel],
    *,
    evidence_bundle_sha256: str,
    timestamp_tolerance_s: float,
    lineage_time_window_s: float,
    truth_presence_window_s: float | None,
    source_verification: str,
    online_truth_isolation_verified: bool,
    source_frame_timestamps: Mapping[int, float] | None,
    source_record_semantics_verified: bool,
) -> Scalable3DIdentityEvaluation:
    tolerance = _nonnegative_finite(
        timestamp_tolerance_s,
        "timestamp_tolerance_s",
    )
    lineage_window = _nonnegative_finite(
        lineage_time_window_s,
        "lineage_time_window_s",
    )
    presence_window = (
        tolerance
        if truth_presence_window_s is None
        else _nonnegative_finite(
            truth_presence_window_s,
            "truth_presence_window_s",
        )
    )

    label_index: dict[str, list[Scalable3DObservationTruthLabel]] = defaultdict(list)
    for label in labels:
        label_index[label.observation_id].append(label)
    duplicate_truth_label_count = sum(
        len(items) - 1 for items in label_index.values() if len(items) > 1
    )
    conflicting_truth_label_ids = {
        observation_id
        for observation_id, items in label_index.items()
        if len(
            {
                (item.truth_target_id, item.measurement_timestamp)
                for item in items
            }
        )
        > 1
    }

    groups, frame_timestamp_conflicts = _group_evidence(bundle.records)
    _mark_frame_claim_conflicts(groups)
    lifecycle_conflicts = _mark_lifecycle_conflicts(groups)
    replay_counts = _mark_replay_conflicts(groups, tolerance=tolerance)

    frame_groups: dict[int, list[_TrackFrameGroup]] = defaultdict(list)
    for group in groups.values():
        frame_groups[group.frame_index].append(group)

    referenced_observation_ids: set[str] = set()
    mapping_by_frame: dict[int, tuple[GlobalTrackTruthMapping, ...]] = {}
    frame_timestamps = {
        _nonnegative_int(index, "source frame index"): _timestamp(
            timestamp,
            "source frame timestamp",
        )
        for index, timestamp in (source_frame_timestamps or {}).items()
    }
    unexpected_integrity_reasons: set[str] = set(frame_timestamp_conflicts)
    unexpected_integrity_reasons.update(lifecycle_conflicts)

    for frame_index in sorted(set(frame_groups) | set(frame_timestamps)):
        ordered_groups = sorted(
            frame_groups.get(frame_index, ()),
            key=lambda item: (item.first_order, item.global_track_id),
        )
        if ordered_groups:
            evidence_timestamp = ordered_groups[0].frame_timestamp
            source_timestamp = frame_timestamps.get(frame_index)
            if (
                source_timestamp is not None
                and abs(source_timestamp - evidence_timestamp) > tolerance
            ):
                unexpected_integrity_reasons.add("source_frame_timestamp_mismatch")
            frame_timestamps.setdefault(frame_index, evidence_timestamp)
        mappings: list[GlobalTrackTruthMapping] = []
        for group in ordered_groups:
            mapping = _map_track_group(
                group,
                label_index,
                tolerance=tolerance,
                lineage_window=lineage_window,
                conflicting_truth_label_ids=conflicting_truth_label_ids,
            )
            mappings.append(mapping)
            referenced_observation_ids.update(mapping.source_observation_ids)
            if (
                group.association_state not in _OBSERVED_ASSOCIATION_STATES
                and any(
                    reason != "track_not_assigned_in_frame"
                    for reason in mapping.unavailable_reasons
                )
            ):
                unexpected_integrity_reasons.update(
                    mapping.unavailable_reasons
                )
        mapping_by_frame[frame_index] = tuple(mappings)

    truth_presence_by_frame = {
        frame_index: tuple(
            sorted(
                {
                    label.truth_target_id
                    for label in labels
                    if abs(label.measurement_timestamp - frame_timestamp)
                    <= presence_window
                }
            )
        )
        for frame_index, frame_timestamp in frame_timestamps.items()
    }

    metric_blockers = set(unexpected_integrity_reasons)
    if not labels:
        metric_blockers.add("observation_truth_labels_unavailable")
    if duplicate_truth_label_count:
        metric_blockers.add("duplicate_observation_truth_labels")
    if conflicting_truth_label_ids:
        metric_blockers.add("conflicting_observation_truth_labels")
    if not any(truth_presence_by_frame.values()):
        metric_blockers.add("truth_presence_unavailable_for_d2_frames")

    for frame_index, mappings in mapping_by_frame.items():
        present = set(truth_presence_by_frame[frame_index])
        for mapping in mappings:
            if mapping.association_state not in _OBSERVED_ASSOCIATION_STATES:
                continue
            if mapping.status != "available":
                metric_blockers.update(mapping.unavailable_reasons)
                continue
            if mapping.truth_target_id not in present:
                metric_blockers.add("mapped_truth_not_present_in_frame")

    metrics = _identity_metrics(
        mapping_by_frame,
        truth_presence_by_frame,
        blockers=metric_blockers,
    )

    frames: list[FrameGlobalTrackTruthMapping] = []
    for frame_index in sorted(mapping_by_frame):
        mappings = mapping_by_frame[frame_index]
        reasons = Counter(
            reason
            for mapping in mappings
            for reason in mapping.unavailable_reasons
        )
        frame_group_items = frame_groups.get(frame_index, ())
        refs = [ref for group in frame_group_items for ref in group.refs]
        unique_lineages = {ref.source_lineage for ref in refs}
        duplicate_count = len(refs) - len(unique_lineages)
        frames.append(
            FrameGlobalTrackTruthMapping(
                frame_index=frame_index,
                frame_timestamp=frame_timestamps[frame_index],
                truth_target_ids_present=truth_presence_by_frame[frame_index],
                mappings=mappings,
                evidence_count=len(refs),
                unique_lineage_count=len(unique_lineages),
                replayed_lineage_count=sum(
                    group.replayed_lineage_count
                    for group in frame_group_items
                ),
                duplicate_lineage_count=duplicate_count,
                available_mapping_count=sum(
                    item.status == "available" for item in mappings
                ),
                ambiguous_mapping_count=sum(
                    item.status == "ambiguous" for item in mappings
                ),
                unavailable_mapping_count=sum(
                    item.status == "unavailable" for item in mappings
                ),
                reason_counts=dict(sorted(reasons.items())),
            )
        )

    partial_identity_diagnostics = _partial_identity_diagnostics(
        mapping_by_frame,
        truth_presence_by_frame,
    )
    all_mappings = [mapping for frame in frames for mapping in frame.mappings]
    all_refs = [ref for record in bundle.records for ref in record.source_observations]
    audit = {
        "source_verification": source_verification,
        "online_truth_isolation_verified": online_truth_isolation_verified,
        "source_record_semantics_verified": source_record_semantics_verified,
        "six_dimensional_track_records_verified": (
            source_record_semantics_verified
        ),
        "evidence_completeness_verified": source_record_semantics_verified,
        "identity_heuristics_used": False,
        "identity_sources_allowed": ["source_observation_lineage"],
        "identity_sources_forbidden": [
            "target_name",
            "actor_id",
            "terminal_proximity",
            "nearest_distance",
        ],
        "evidence_record_count": len(bundle.records),
        "evaluated_frame_count": len(frames),
        "truth_label_count": len(labels),
        "unique_truth_observation_count": len(label_index),
        "duplicate_truth_label_count": duplicate_truth_label_count,
        "conflicting_truth_label_count": len(conflicting_truth_label_ids),
        "lineage_evidence_count": len(all_refs),
        "unique_lineage_count": len(
            {item.source_lineage for item in all_refs}
        ),
        "replayed_lineage_count": sum(replay_counts.values()),
        "available_mapping_count": sum(
            item.status == "available" for item in all_mappings
        ),
        "ambiguous_mapping_count": sum(
            item.status == "ambiguous" for item in all_mappings
        ),
        "unavailable_mapping_count": sum(
            item.status == "unavailable" for item in all_mappings
        ),
        "unreferenced_truth_observation_count": len(
            set(label_index) - referenced_observation_ids
        ),
        "identity_metrics_blocking_reasons": sorted(metric_blockers),
        "partial_identity_diagnostics_available": True,
        "partial_identity_diagnostics_schema_version": (
            SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
        ),
    }
    source_hashes = {
        **bundle.source_hashes,
        "identity_evidence_bundle": _normalized_sha256(
            evidence_bundle_sha256
        ),
    }
    return Scalable3DIdentityEvaluation(
        episode_id=bundle.episode_id,
        source_hashes=source_hashes,
        frames=tuple(frames),
        metrics=metrics,
        partial_identity_diagnostics=partial_identity_diagnostics,
        configuration={
            "timestamp_tolerance_s": tolerance,
            "lineage_time_window_s": lineage_window,
            "truth_presence_window_s": presence_window,
            "representative_track_policy": (
                "first_assignment_in_persisted_frame_evidence_order"
            ),
            "metric_contract": "MetricsRecorder-compatible-v1",
            "partial_identity_diagnostic_contract": (
                SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
            ),
        },
        audit=audit,
    )


def _group_evidence(
    records: Sequence[GlobalTrackLineageEvidence],
) -> tuple[dict[tuple[int, str], _TrackFrameGroup], set[str]]:
    groups: dict[tuple[int, str], _TrackFrameGroup] = {}
    timestamp_by_frame: dict[int, float] = {}
    conflicting_frame_indices: set[int] = set()
    global_reasons: set[str] = set()
    for order, record in enumerate(records):
        previous_timestamp = timestamp_by_frame.get(record.frame_index)
        if (
            previous_timestamp is not None
            and abs(previous_timestamp - record.frame_timestamp) > 1.0e-12
        ):
            global_reasons.add("frame_timestamp_conflict")
            conflicting_frame_indices.add(record.frame_index)
        timestamp_by_frame.setdefault(record.frame_index, record.frame_timestamp)
        key = (record.frame_index, record.global_track_id)
        group = groups.get(key)
        if group is None:
            group = _TrackFrameGroup(
                frame_index=record.frame_index,
                frame_timestamp=record.frame_timestamp,
                global_track_id=record.global_track_id,
            )
            groups[key] = group
        else:
            group.issues.add("duplicate_track_frame_record")
            if abs(group.frame_timestamp - record.frame_timestamp) > 1.0e-12:
                group.issues.add("frame_timestamp_conflict")
        group.records.append((order, record))

    for group in groups.values():
        lifecycle_states = {record.lifecycle_state for _, record in group.records}
        association_states = {
            record.association_state for _, record in group.records
        }
        if len(lifecycle_states) > 1:
            group.issues.add("conflicting_track_lifecycle_records")
        if len(association_states) > 1:
            group.issues.add("conflicting_track_association_records")
        lineage_counts = Counter(ref.source_lineage for ref in group.refs)
        if any(count > 1 for count in lineage_counts.values()):
            group.issues.add("duplicate_lineage_within_track_frame")
        observation_lineages: dict[str, set[tuple[str, ...]]] = defaultdict(set)
        for ref in group.refs:
            observation_lineages[ref.observation_id].add(ref.source_lineage)
        if any(len(items) > 1 for items in observation_lineages.values()):
            group.issues.add("observation_lineage_conflict")
        if group.frame_index in conflicting_frame_indices:
            group.issues.add("frame_timestamp_conflict")
    return groups, global_reasons


def _mark_frame_claim_conflicts(
    groups: Mapping[tuple[int, str], _TrackFrameGroup],
) -> None:
    lineage_claims: dict[tuple[int, tuple[str, ...]], set[str]] = defaultdict(set)
    observation_claims: dict[tuple[int, str], set[str]] = defaultdict(set)
    for group in groups.values():
        for ref in group.refs:
            lineage_claims[(group.frame_index, ref.source_lineage)].add(
                group.global_track_id
            )
            observation_claims[(group.frame_index, ref.observation_id)].add(
                group.global_track_id
            )
    conflicting_lineages = {
        key for key, track_ids in lineage_claims.items() if len(track_ids) > 1
    }
    conflicting_observations = {
        key for key, track_ids in observation_claims.items() if len(track_ids) > 1
    }
    for group in groups.values():
        if any(
            (group.frame_index, ref.source_lineage) in conflicting_lineages
            for ref in group.refs
        ):
            group.issues.add("lineage_claimed_by_multiple_tracks")
        if any(
            (group.frame_index, ref.observation_id) in conflicting_observations
            for ref in group.refs
        ):
            group.issues.add("observation_claimed_by_multiple_tracks")


def _mark_lifecycle_conflicts(
    groups: Mapping[tuple[int, str], _TrackFrameGroup],
) -> set[str]:
    prior: dict[str, tuple[int, float, str]] = {}
    seen_created: set[str] = set()
    global_reasons: set[str] = set()
    for group in sorted(
        groups.values(),
        key=lambda item: (item.frame_index, item.first_order, item.global_track_id),
    ):
        association_state = group.association_state
        lifecycle_state = group.lifecycle_state
        if association_state in _OBSERVED_ASSOCIATION_STATES and not group.refs:
            group.issues.add("source_lineage_missing")
        if association_state not in _OBSERVED_ASSOCIATION_STATES and group.refs:
            group.issues.add("lineage_on_unassigned_track")
        if (
            association_state in _OBSERVED_ASSOCIATION_STATES
            and lifecycle_state not in _ACTIVE_LIFECYCLE_STATES
        ):
            group.issues.add("inactive_track_has_association_evidence")
        if association_state == "lost" and lifecycle_state != "lost":
            group.issues.add("lost_association_lifecycle_mismatch")
        if association_state == "dropped" and lifecycle_state != "dropped":
            group.issues.add("dropped_association_lifecycle_mismatch")
        if association_state == "created":
            if group.global_track_id in seen_created or group.global_track_id in prior:
                group.issues.add("duplicate_track_birth")
            seen_created.add(group.global_track_id)

        previous = prior.get(group.global_track_id)
        if previous is not None:
            previous_frame, previous_timestamp, previous_state = previous
            if group.frame_index <= previous_frame:
                group.issues.add("track_frame_order_conflict")
            if group.frame_timestamp + 1.0e-12 < previous_timestamp:
                group.issues.add("track_timestamp_regression")
            if not _valid_lifecycle_transition(previous_state, lifecycle_state):
                group.issues.add("invalid_track_lifecycle_transition")
            if previous_state == "dropped" and lifecycle_state != "dropped":
                group.issues.add("track_reappeared_after_drop")
        prior[group.global_track_id] = (
            group.frame_index,
            group.frame_timestamp,
            lifecycle_state,
        )
        global_reasons.update(
            reason
            for reason in group.issues
            if reason
            in {
                "track_frame_order_conflict",
                "track_timestamp_regression",
                "invalid_track_lifecycle_transition",
                "track_reappeared_after_drop",
                "duplicate_track_birth",
            }
        )
    return global_reasons


def _mark_replay_conflicts(
    groups: Mapping[tuple[int, str], _TrackFrameGroup],
    *,
    tolerance: float,
) -> Counter[str]:
    prior_lineage: dict[
        tuple[str, ...], tuple[str, int, int, float, str]
    ] = {}
    observation_lineages: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for group in sorted(
        groups.values(),
        key=lambda item: (item.frame_index, item.first_order, item.global_track_id),
    ):
        unique_refs: dict[tuple[str, ...], ObservationLineageRef] = {}
        for ref in group.refs:
            unique_refs.setdefault(ref.source_lineage, ref)
            known_lineages = observation_lineages[ref.observation_id]
            if known_lineages and ref.source_lineage not in known_lineages:
                group.issues.add("observation_lineage_conflict")
            known_lineages.add(ref.source_lineage)
        for lineage, ref in unique_refs.items():
            previous = prior_lineage.get(lineage)
            if previous is None:
                if ref.replay_generation > 0:
                    group.issues.add("replay_origin_missing")
                prior_lineage[lineage] = (
                    group.global_track_id,
                    ref.replay_generation,
                    group.frame_index,
                    ref.measurement_timestamp,
                    ref.observation_id,
                )
                continue
            (
                previous_track_id,
                previous_generation,
                previous_frame,
                previous_timestamp,
                previous_observation_id,
            ) = previous
            if previous_track_id != group.global_track_id:
                group.issues.add("lineage_rebound_to_different_track")
            elif group.frame_index == previous_frame:
                group.issues.add("duplicate_lineage_within_track_frame")
            elif ref.replay_generation <= previous_generation:
                reason = (
                    "duplicate_lineage_without_replay_marker"
                    if ref.replay_generation == 0
                    else "replay_generation_not_monotonic"
                )
                group.issues.add(reason)
            else:
                group.replayed_lineage_count += 1
                counts["accepted_replay"] += 1
            if (
                abs(ref.measurement_timestamp - previous_timestamp) > tolerance
                or ref.observation_id != previous_observation_id
            ):
                group.issues.add("replayed_lineage_payload_conflict")
            prior_lineage[lineage] = (
                group.global_track_id,
                max(previous_generation, ref.replay_generation),
                group.frame_index,
                ref.measurement_timestamp,
                ref.observation_id,
            )
    return counts


def _map_track_group(
    group: _TrackFrameGroup,
    label_index: Mapping[str, Sequence[Scalable3DObservationTruthLabel]],
    *,
    tolerance: float,
    lineage_window: float,
    conflicting_truth_label_ids: set[str],
) -> GlobalTrackTruthMapping:
    issues = set(group.issues)
    refs = group.refs
    unique_refs: dict[tuple[str, ...], ObservationLineageRef] = {}
    for ref in refs:
        unique_refs.setdefault(ref.source_lineage, ref)

    candidates: list[str] = []
    labeled_evidence_count = 0
    for ref in unique_refs.values():
        if ref.measurement_timestamp > group.frame_timestamp + tolerance:
            issues.add("source_observation_from_future")
        if group.frame_timestamp - ref.measurement_timestamp > lineage_window + tolerance:
            issues.add("source_observation_outside_lineage_window")
        labels = label_index.get(ref.observation_id, ())
        if not labels:
            issues.add("truth_label_missing")
            continue
        if len(labels) > 1:
            issues.add("duplicate_truth_label")
        if ref.observation_id in conflicting_truth_label_ids:
            issues.add("conflicting_truth_labels")
        matching = [
            label
            for label in labels
            if abs(label.measurement_timestamp - ref.measurement_timestamp)
            <= tolerance
        ]
        if len(matching) != len(labels) or not matching:
            issues.add("truth_label_timestamp_mismatch")
            continue
        labeled_evidence_count += 1
        candidates.extend(label.truth_target_id for label in matching)

    candidate_truth_ids = tuple(sorted(set(candidates)))
    if len(candidate_truth_ids) > 1:
        issues.add("multiple_truth_targets_for_global_track")
    if group.association_state not in _OBSERVED_ASSOCIATION_STATES:
        issues.add("track_not_assigned_in_frame")

    ambiguity_reasons = {
        "conflicting_track_lifecycle_records",
        "conflicting_track_association_records",
        "conflicting_truth_labels",
        "duplicate_lineage_within_track_frame",
        "duplicate_track_frame_record",
        "lineage_claimed_by_multiple_tracks",
        "lineage_rebound_to_different_track",
        "multiple_truth_targets_for_global_track",
        "observation_claimed_by_multiple_tracks",
        "observation_lineage_conflict",
        "replayed_lineage_payload_conflict",
    }
    if issues & ambiguity_reasons:
        status = "ambiguous"
        truth_target_id = None
    elif issues:
        status = "unavailable"
        truth_target_id = None
    elif len(candidate_truth_ids) == 1:
        status = "available"
        truth_target_id = candidate_truth_ids[0]
    else:
        status = "unavailable"
        truth_target_id = None
        issues.add("truth_mapping_evidence_unavailable")

    ordered_reasons = tuple(sorted(issues, key=_reason_sort_key))
    return GlobalTrackTruthMapping(
        global_track_id=group.global_track_id,
        lifecycle_state=group.lifecycle_state,
        association_state=group.association_state,
        status=status,
        truth_target_id=truth_target_id,
        reason=None if status == "available" else ordered_reasons[0],
        unavailable_reasons=ordered_reasons,
        candidate_truth_target_ids=candidate_truth_ids,
        source_observation_ids=tuple(
            dict.fromkeys(ref.observation_id for ref in refs)
        ),
        source_lineage_hashes=tuple(
            sorted(
                {
                    _sha256_bytes(
                        _canonical_json_bytes(list(ref.source_lineage))
                    )
                    for ref in refs
                }
            )
        ),
        evidence_count=len(refs),
        unique_lineage_count=len(unique_refs),
        labeled_evidence_count=labeled_evidence_count,
        replayed_lineage_count=group.replayed_lineage_count,
    )


def _partial_identity_diagnostics(
    mappings_by_frame: Mapping[int, Sequence[GlobalTrackTruthMapping]],
    truth_presence_by_frame: Mapping[int, Sequence[str]],
) -> Scalable3DPartialIdentityDiagnostics:
    frame_indices = sorted(set(mappings_by_frame) | set(truth_presence_by_frame))
    all_mappings = [
        mapping
        for frame_index in frame_indices
        for mapping in mappings_by_frame.get(frame_index, ())
    ]
    available_mapping_count = sum(
        mapping.status == "available" for mapping in all_mappings
    )
    ambiguous_mapping_count = sum(
        mapping.status == "ambiguous" for mapping in all_mappings
    )
    unavailable_mapping_count = sum(
        mapping.status == "unavailable" for mapping in all_mappings
    )

    scored_by_frame = {
        frame_index: tuple(
            mapping
            for mapping in mappings_by_frame.get(frame_index, ())
            if mapping.association_state in _OBSERVED_ASSOCIATION_STATES
        )
        for frame_index in frame_indices
    }
    scored_mappings = [
        mapping
        for frame_index in frame_indices
        for mapping in scored_by_frame[frame_index]
    ]
    evaluable_mapping_count = 0
    ambiguous_scored_mapping_count = 0
    unavailable_scored_mapping_count = 0
    mapped_truth_not_present_mapping_count = 0
    missing_identity_evidence_mapping_count = 0
    excluded_reason_counts: Counter[str] = Counter()
    anchor_exclusion_reason_counts: Counter[str] = Counter()
    frame_evaluable: dict[int, bool] = {}
    lower_bound_anchor_by_frame: dict[int, dict[str, str]] = {}

    for frame_index in frame_indices:
        present = set(truth_presence_by_frame.get(frame_index, ()))
        scored = scored_by_frame[frame_index]
        frame_is_evaluable = bool(present)
        tracks_by_truth: dict[str, list[str]] = defaultdict(list)
        for mapping in scored:
            mapping_is_evaluable = (
                mapping.status == "available"
                and mapping.truth_target_id is not None
                and mapping.truth_target_id in present
            )
            if mapping_is_evaluable:
                evaluable_mapping_count += 1
                tracks_by_truth[mapping.truth_target_id].append(
                    mapping.global_track_id
                )
                continue

            frame_is_evaluable = False
            if mapping.status == "ambiguous":
                ambiguous_scored_mapping_count += 1
            elif mapping.status == "unavailable":
                unavailable_scored_mapping_count += 1
            else:
                mapped_truth_not_present_mapping_count += 1
                excluded_reason_counts["mapped_truth_not_present_in_frame"] += 1
            if (
                set(mapping.unavailable_reasons)
                & _MISSING_IDENTITY_EVIDENCE_REASONS
            ):
                missing_identity_evidence_mapping_count += 1
            excluded_reason_counts.update(mapping.unavailable_reasons)

        frame_evaluable[frame_index] = frame_is_evaluable
        lower_bound_anchor_by_frame[frame_index] = {}
        for truth_id, track_ids in tracks_by_truth.items():
            unique_track_ids = tuple(dict.fromkeys(track_ids))
            if len(unique_track_ids) > 1:
                anchor_exclusion_reason_counts[
                    "multiple_evaluable_global_tracks_for_truth_frame"
                ] += 1
            elif frame_is_evaluable and len(unique_track_ids) == 1:
                lower_bound_anchor_by_frame[frame_index][truth_id] = (
                    unique_track_ids[0]
                )

    presence_frames_by_truth: dict[str, list[int]] = defaultdict(list)
    for frame_index in frame_indices:
        for truth_target_id in dict.fromkeys(
            truth_presence_by_frame.get(frame_index, ())
        ):
            presence_frames_by_truth[str(truth_target_id)].append(frame_index)

    transition_opportunity_count = 0
    evaluable_transition_count = 0
    lower_bound_anchor_transition_count = 0
    id_switch_lower_bound = 0
    for truth_target_id, presence_frames in presence_frames_by_truth.items():
        transition_opportunity_count += max(len(presence_frames) - 1, 0)
        for previous_frame, current_frame in zip(
            presence_frames,
            presence_frames[1:],
        ):
            if (
                truth_target_id
                in lower_bound_anchor_by_frame[previous_frame]
                and truth_target_id
                in lower_bound_anchor_by_frame[current_frame]
            ):
                evaluable_transition_count += 1

        anchors = [
            (
                frame_index,
                lower_bound_anchor_by_frame[frame_index][truth_target_id],
            )
            for frame_index in presence_frames
            if truth_target_id in lower_bound_anchor_by_frame[frame_index]
        ]
        lower_bound_anchor_transition_count += max(len(anchors) - 1, 0)
        id_switch_lower_bound += sum(
            previous_track_id != current_track_id
            for (_, previous_track_id), (_, current_track_id) in zip(
                anchors,
                anchors[1:],
            )
        )

    mapping_coverage, mapping_reason = _partial_coverage(
        evaluable_mapping_count,
        len(scored_mappings),
        unavailable_reason="no_scored_identity_mappings",
    )
    evaluable_frame_count = sum(frame_evaluable.values())
    frame_coverage, frame_reason = _partial_coverage(
        evaluable_frame_count,
        len(frame_indices),
        unavailable_reason="no_evaluated_identity_frames",
    )
    transition_coverage, transition_reason = _partial_coverage(
        evaluable_transition_count,
        transition_opportunity_count,
        unavailable_reason="no_truth_presence_transition_opportunities",
    )
    lower_bound_available = lower_bound_anchor_transition_count > 0
    return Scalable3DPartialIdentityDiagnostics(
        total_mapping_count=len(all_mappings),
        available_mapping_count=available_mapping_count,
        ambiguous_mapping_count=ambiguous_mapping_count,
        unavailable_mapping_count=unavailable_mapping_count,
        scored_mapping_count=len(scored_mappings),
        non_scored_mapping_count=len(all_mappings) - len(scored_mappings),
        evaluable_mapping_count=evaluable_mapping_count,
        ambiguous_scored_mapping_count=ambiguous_scored_mapping_count,
        unavailable_scored_mapping_count=unavailable_scored_mapping_count,
        mapped_truth_not_present_mapping_count=(
            mapped_truth_not_present_mapping_count
        ),
        missing_identity_evidence_mapping_count=(
            missing_identity_evidence_mapping_count
        ),
        evaluable_mapping_coverage=mapping_coverage,
        evaluable_mapping_coverage_reason=mapping_reason,
        evaluated_frame_count=len(frame_indices),
        evaluable_frame_count=evaluable_frame_count,
        evaluable_frame_coverage=frame_coverage,
        evaluable_frame_coverage_reason=frame_reason,
        transition_opportunity_count=transition_opportunity_count,
        evaluable_transition_count=evaluable_transition_count,
        evaluable_transition_coverage=transition_coverage,
        evaluable_transition_coverage_reason=transition_reason,
        lower_bound_anchor_excluded_truth_frame_count=sum(
            anchor_exclusion_reason_counts.values()
        ),
        lower_bound_anchor_exclusion_reason_counts=dict(
            anchor_exclusion_reason_counts
        ),
        lower_bound_anchor_transition_count=(
            lower_bound_anchor_transition_count
        ),
        id_switch_lower_bound=(
            id_switch_lower_bound if lower_bound_available else None
        ),
        id_switch_lower_bound_reason=(
            None
            if lower_bound_available
            else "no_evaluable_identity_transitions"
        ),
        excluded_scored_mapping_reason_counts=dict(excluded_reason_counts),
    )


def _identity_metrics(
    mappings_by_frame: Mapping[int, Sequence[GlobalTrackTruthMapping]],
    truth_presence_by_frame: Mapping[int, Sequence[str]],
    *,
    blockers: set[str],
) -> Scalable3DIdentityMetrics:
    truth_frame_count: Counter[str] = Counter()
    truth_assigned_frame_count: Counter[str] = Counter()
    stable_frame_count: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)

    if blockers:
        reason = sorted(blockers, key=_reason_sort_key)[0]
        return Scalable3DIdentityMetrics(
            available=False,
            reason=reason,
            id_switch_count=None,
            track_continuity=None,
            identity_continuity=None,
            coverage_continuity=None,
            duplicate_truth_to_track_count=None,
            confusion_matrix=None,
            evaluated_frame_count=len(mappings_by_frame),
            truth_frame_count={},
            truth_assigned_frame_count={},
            truth_identity_stable_frame_count={},
        )

    last_truth_to_track: dict[str, str] = {}
    id_switch_count = 0
    duplicate_count = 0
    for frame_index in sorted(mappings_by_frame):
        present = tuple(dict.fromkeys(truth_presence_by_frame[frame_index]))
        for truth_target_id in present:
            truth_frame_count[truth_target_id] += 1
        tracks_by_truth: dict[str, list[str]] = defaultdict(list)
        for mapping in mappings_by_frame[frame_index]:
            if (
                mapping.association_state in _OBSERVED_ASSOCIATION_STATES
                and mapping.status == "available"
                and mapping.truth_target_id is not None
            ):
                tracks_by_truth[mapping.truth_target_id].append(
                    mapping.global_track_id
                )
                confusion[mapping.truth_target_id][mapping.global_track_id] += 1

        for truth_target_id, track_ids in tracks_by_truth.items():
            if track_ids:
                truth_assigned_frame_count[truth_target_id] += 1
            unique_track_ids = list(dict.fromkeys(track_ids))
            if len(unique_track_ids) > 1:
                duplicate_count += len(unique_track_ids) - 1
            representative = unique_track_ids[0]
            previous = last_truth_to_track.get(truth_target_id)
            if previous is not None and previous != representative:
                id_switch_count += 1
            else:
                stable_frame_count[truth_target_id] += 1
            last_truth_to_track[truth_target_id] = representative

    identity_values = [
        stable_frame_count.get(truth_target_id, 0) / frame_count
        for truth_target_id, frame_count in truth_frame_count.items()
        if frame_count > 0
    ]
    coverage_values = [
        truth_assigned_frame_count.get(truth_target_id, 0) / frame_count
        for truth_target_id, frame_count in truth_frame_count.items()
        if frame_count > 0
    ]
    identity_continuity = _mean(identity_values)
    coverage_continuity = _mean(coverage_values)
    return Scalable3DIdentityMetrics(
        available=True,
        reason=None,
        id_switch_count=id_switch_count,
        track_continuity=identity_continuity,
        identity_continuity=identity_continuity,
        coverage_continuity=coverage_continuity,
        duplicate_truth_to_track_count=duplicate_count,
        confusion_matrix={
            truth_id: dict(counts)
            for truth_id, counts in sorted(confusion.items())
        },
        evaluated_frame_count=len(mappings_by_frame),
        truth_frame_count=dict(truth_frame_count),
        truth_assigned_frame_count=dict(truth_assigned_frame_count),
        truth_identity_stable_frame_count=dict(stable_frame_count),
    )


def write_scalable_3d_identity_evidence(
    path: str | Path,
    evidence: Scalable3DIdentityEvidenceBundle | Mapping[str, Any],
) -> str:
    """Write deterministic evidence JSON and return its ``sha256:`` digest."""

    bundle = _coerce_bundle(evidence)
    return _write_json(path, bundle.to_dict())


def load_scalable_3d_identity_evidence(
    path: str | Path,
    *,
    expected_sha256: str,
) -> Scalable3DIdentityEvidenceBundle:
    """Load evidence only when its externally recorded hash matches."""

    _verify_file_hash(path, expected_sha256, "identity evidence bundle")
    payload = _load_json_object(path, "identity evidence bundle")
    return Scalable3DIdentityEvidenceBundle.from_mapping(payload)


def write_scalable_3d_observation_truth_labels(
    path: str | Path,
    labels: Iterable[Scalable3DObservationTruthLabel | Mapping[str, Any]],
) -> str:
    """Write the normalized evaluator-only observation truth JSONL."""

    records = _coerce_truth_labels(labels)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical_jsonl_bytes(item.to_dict() for item in records))
    return sha256_file(output)


def load_scalable_3d_observation_truth_labels(
    path: str | Path,
    *,
    expected_sha256: str,
) -> tuple[Scalable3DObservationTruthLabel, ...]:
    """Load a hash-verified D2 or scalable-producer truth sidecar."""

    _verify_file_hash(path, expected_sha256, "observation truth labels")
    payloads = _load_jsonl_objects(path, "observation truth labels")
    return tuple(
        Scalable3DObservationTruthLabel.from_mapping(payload)
        for payload in payloads
    )


def write_scalable_3d_identity_evaluation(
    path: str | Path,
    evaluation: Scalable3DIdentityEvaluation | Mapping[str, Any],
) -> str:
    """Write a deterministic public artifact and return its SHA-256."""

    result = (
        evaluation
        if isinstance(evaluation, Scalable3DIdentityEvaluation)
        else Scalable3DIdentityEvaluation.from_mapping(
            _as_mapping(evaluation, "identity evaluation")
        )
    )
    return _write_json(path, result.to_dict())


def load_scalable_3d_identity_evaluation(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_source_hashes: Mapping[str, str] | None = None,
) -> Scalable3DIdentityEvaluation:
    """Load a public evaluator artifact with hash and provenance checks."""

    _verify_file_hash(path, expected_sha256, "identity evaluation")
    result = Scalable3DIdentityEvaluation.from_mapping(
        _load_json_object(path, "identity evaluation")
    )
    if expected_source_hashes is not None:
        expected = _validated_source_hashes(
            expected_source_hashes,
            required=set(expected_source_hashes),
        )
        for name, digest in expected.items():
            if result.source_hashes.get(name) != digest:
                raise ValueError(
                    f"identity evaluation source hash mismatch for {name}"
                )
    return result


def hash_scalable_3d_identity_evidence(
    evidence: Scalable3DIdentityEvidenceBundle | Mapping[str, Any],
) -> str:
    bundle = _coerce_bundle(evidence)
    return _sha256_bytes(_canonical_json_bytes(bundle.to_dict()) + b"\n")


def hash_scalable_3d_observation_truth_labels(
    labels: Iterable[Scalable3DObservationTruthLabel | Mapping[str, Any]],
) -> str:
    records = _coerce_truth_labels(labels)
    return _sha256_bytes(
        _canonical_jsonl_bytes(item.to_dict() for item in records)
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def assert_scalable_3d_online_identity_records_truth_free(
    records: Iterable[Mapping[str, Any]],
    *,
    source_name: str = "online_records",
) -> None:
    """Reject evaluator truth, simulator identity, or target-name leakage."""

    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = _normalized_key(raw_key)
                child_path = f"{path}.{raw_key}"
                if _forbidden_online_identity_key(key):
                    violations.append(child_path)
                    continue
                visit(child, child_path)
        elif isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    for index, record in enumerate(records):
        visit(record, f"{source_name}[{index}]")
    if violations:
        raise ValueError(
            "online identity isolation audit failed: "
            + ", ".join(sorted(set(violations)))
        )


def _load_online_json_records(
    path: str | Path,
    *,
    module: str,
) -> tuple[Mapping[str, Any], ...]:
    records = _load_jsonl_objects(path, f"online {module.upper()} records")
    source, topic, expected_schema = _ONLINE_RECORD_CONTRACTS[module]
    selected = tuple(
        record
        for record in records
        if record.get("topic") == topic
    )
    if not selected:
        raise ValueError(f"online record file contains no {module.upper()} records")
    for record in selected:
        _nonnegative_int(record.get("sequence"), f"online {source} sequence")
        if record.get("source") != source:
            raise ValueError(f"online {source} record has an invalid source owner")
        if record.get("schema_version") != expected_schema:
            raise ValueError(
                f"unsupported online {source} record schema: "
                f"{record.get('schema_version')!r}"
            )
        envelope_timestamp = _timestamp(
            record.get("timestamp"),
            f"online {source} envelope timestamp",
        )
        payload = _as_mapping(record.get("payload"), f"online {source} payload")
        payload_timestamp = _timestamp(
            payload.get("timestamp"),
            f"online {source} payload timestamp",
        )
        if abs(envelope_timestamp - payload_timestamp) > 1.0e-9:
            raise ValueError(f"online {source} envelope/payload timestamp mismatch")
        tracks = _six_state_track_index(payload, source)
        if module == "d1":
            _d1_observation_index(payload)
        else:
            _d2_identity_index(payload, tracks)
    return selected


def _validate_source_record_references(
    evidence: Sequence[GlobalTrackLineageEvidence],
    d1_records: Sequence[Mapping[str, Any]],
    d2_records: Sequence[Mapping[str, Any]],
) -> dict[int, float]:
    d1_by_sequence = _records_by_sequence(d1_records, "D1")
    d2_by_sequence = _records_by_sequence(d2_records, "D2")
    d1_observations = {
        sequence: _d1_observation_index(
            _as_mapping(record["payload"], "online D1 payload")
        )
        for sequence, record in d1_by_sequence.items()
    }
    d1_sequences_by_observation: dict[str, set[int]] = defaultdict(set)
    for sequence, observations in d1_observations.items():
        for observation_id in observations:
            d1_sequences_by_observation[observation_id].add(sequence)

    evidence_by_key: dict[tuple[int, str], GlobalTrackLineageEvidence] = {}
    for item in evidence:
        key = (item.frame_index, item.global_track_id)
        if key in evidence_by_key:
            raise ValueError("identity evidence contains duplicate frame/track records")
        evidence_by_key[key] = item

    expected_keys: set[tuple[int, str]] = set()
    frame_timestamps: dict[int, float] = {}
    for frame_index, (sequence, source_record) in enumerate(
        sorted(d2_by_sequence.items())
    ):
        payload = _as_mapping(source_record["payload"], "online D2 payload")
        tracks = _six_state_track_index(payload, "D2")
        identities = _d2_identity_index(payload, tracks)
        association = _as_mapping(payload["association"], "D2 association payload")
        frame_timestamp = _timestamp(
            association.get("timestamp"),
            "D2 association timestamp",
        )
        frame_timestamps[frame_index] = frame_timestamp
        for global_track_id, identity in identities.items():
            key = (frame_index, global_track_id)
            expected_keys.add(key)
            item = evidence_by_key.get(key)
            if item is None:
                continue
            if item.d2_record_sequence != sequence:
                raise ValueError("identity evidence D2 sequence/frame mismatch")
            if abs(item.frame_timestamp - frame_timestamp) > 1.0e-9:
                raise ValueError("identity evidence D2 frame timestamp mismatch")
            lifecycle_state, association_state, source_observations = identity
            if (
                item.lifecycle_state != lifecycle_state
                or item.association_state != association_state
            ):
                raise ValueError("identity evidence D2 lifecycle/association mismatch")
            if item.source_observations != source_observations:
                raise ValueError("identity evidence D2 source lineage mismatch")

            expected_d1_sequences = {
                source_sequence
                for observation in source_observations
                for source_sequence in d1_sequences_by_observation.get(
                    observation.observation_id,
                    (),
                )
            }
            if set(item.d1_record_sequences) != expected_d1_sequences:
                missing = expected_d1_sequences - set(item.d1_record_sequences)
                unknown = set(item.d1_record_sequences) - expected_d1_sequences
                if missing:
                    raise ValueError(
                        "identity evidence lacks matching D1 sequences: "
                        f"{sorted(missing)}"
                    )
                raise ValueError(
                    "identity evidence references unrelated D1 sequences: "
                    f"{sorted(unknown)}"
                )
            for observation in source_observations:
                candidates = (
                    d1_observations[source_sequence].get(
                        observation.observation_id,
                        (),
                    )
                    for source_sequence in expected_d1_sequences
                )
                if observation not in {
                    candidate
                    for items in candidates
                    for candidate in items
                }:
                    raise ValueError("identity evidence D1 source lineage mismatch")

    unexpected_keys = set(evidence_by_key) - expected_keys
    missing_keys = expected_keys - set(evidence_by_key)
    if unexpected_keys:
        raise ValueError(
            "identity evidence references D2-owned tracks absent from source records"
        )
    if missing_keys:
        raise ValueError(
            "identity evidence is incomplete for persisted D2 track frames"
        )
    return frame_timestamps


def _records_by_sequence(
    records: Sequence[Mapping[str, Any]],
    module: str,
) -> dict[int, Mapping[str, Any]]:
    output: dict[int, Mapping[str, Any]] = {}
    for record in records:
        sequence = _nonnegative_int(
            record.get("sequence"),
            f"persisted {module} sequence",
        )
        if sequence in output:
            raise ValueError(f"persisted {module} record sequences are not unique")
        output[sequence] = record
    return output


def _six_state_track_index(
    payload: Mapping[str, Any],
    module: str,
) -> dict[str, Mapping[str, Any]]:
    raw_tracks = _as_sequence(payload.get("tracks"), f"online {module} tracks")
    if _nonnegative_int(payload.get("track_count"), f"online {module} track_count") != len(
        raw_tracks
    ):
        raise ValueError(f"online {module} track_count does not match tracks")
    tracks: dict[str, Mapping[str, Any]] = {}
    for raw in raw_tracks:
        track = _as_mapping(raw, f"online {module} track")
        global_track_id = _identifier(
            track.get("global_track_id"),
            f"online {module} global_track_id",
        )
        if global_track_id in tracks:
            raise ValueError(f"online {module} global_track_id values are not unique")
        _finite_number_sequence(
            track.get("state_ned"),
            6,
            f"online {module} six-state track",
        )
        _finite_number_matrix(
            track.get("covariance"),
            6,
            f"online {module} 6x6 track covariance",
        )
        _timestamp(track.get("timestamp"), f"online {module} track timestamp")
        _identifier(track.get("track_state"), f"online {module} track_state")
        tracks[global_track_id] = track
    return tracks


def _d1_observation_index(
    payload: Mapping[str, Any],
) -> dict[str, tuple[ObservationLineageRef, ...]]:
    output: dict[str, list[ObservationLineageRef]] = defaultdict(list)
    for raw in _as_sequence(
        payload.get("observation_lineage"),
        "online D1 observation_lineage",
    ):
        observation = ObservationLineageRef.from_mapping(
            _as_mapping(raw, "online D1 observation lineage")
        )
        output[observation.observation_id].append(observation)
    return {key: tuple(values) for key, values in output.items()}


def _d2_identity_index(
    payload: Mapping[str, Any],
    tracks: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[str, str, tuple[ObservationLineageRef, ...]]]:
    if "id_switch_count" not in payload or "id_switch_count_available" not in payload:
        raise ValueError("online D2 record lacks explicit id_switch_count availability")
    if (
        payload["id_switch_count"] is not None
        or payload["id_switch_count_available"] is not False
    ):
        raise ValueError(
            "truth-free online D2 id_switch_count must be null and unavailable"
        )
    if payload.get("identity_lineage_policy") != (
        "d2_center_track_to_d1_source_observation_v1"
    ):
        raise ValueError("online D2 identity lineage policy is unsupported")
    association = _as_mapping(payload.get("association"), "D2 association payload")
    _timestamp(association.get("timestamp"), "D2 association timestamp")

    output: dict[
        str,
        tuple[str, str, tuple[ObservationLineageRef, ...]],
    ] = {}
    for raw in _as_sequence(
        payload.get("identity_lineage"),
        "online D2 identity_lineage",
    ):
        item = _as_mapping(raw, "online D2 identity lineage")
        _reject_unknown_keys(
            item,
            {
                "global_track_id",
                "lifecycle_state",
                "association_state",
                "source_observations",
            },
            "online D2 identity lineage",
        )
        global_track_id = _identifier(
            item.get("global_track_id"),
            "online D2 identity global_track_id",
        )
        if global_track_id in output:
            raise ValueError("online D2 identity_lineage track IDs are not unique")
        lifecycle_state = str(item.get("lifecycle_state", "")).strip().lower()
        association_state = str(item.get("association_state", "")).strip().lower()
        if lifecycle_state not in _LIFECYCLE_STATES:
            raise ValueError("online D2 identity lifecycle state is unsupported")
        if association_state not in _ASSOCIATION_STATES:
            raise ValueError("online D2 identity association state is unsupported")
        observations = tuple(
            ObservationLineageRef.from_mapping(
                _as_mapping(value, "online D2 source observation")
            )
            for value in _as_sequence(
                item.get("source_observations"),
                "online D2 source observations",
            )
        )
        output[global_track_id] = (
            lifecycle_state,
            association_state,
            observations,
        )

    if set(output) != set(tracks):
        raise ValueError(
            "online D2 identity_lineage must cover exactly the D2-owned tracks"
        )
    for global_track_id, (lifecycle_state, _, _) in output.items():
        track_state = str(tracks[global_track_id]["track_state"]).strip().lower()
        if track_state != lifecycle_state:
            raise ValueError("online D2 track and identity lifecycle mismatch")
    return output


def _coerce_bundle(
    value: Scalable3DIdentityEvidenceBundle | Mapping[str, Any],
) -> Scalable3DIdentityEvidenceBundle:
    return (
        value
        if isinstance(value, Scalable3DIdentityEvidenceBundle)
        else Scalable3DIdentityEvidenceBundle.from_mapping(
            _as_mapping(value, "identity evidence bundle")
        )
    )


def _coerce_truth_labels(
    values: Iterable[Scalable3DObservationTruthLabel | Mapping[str, Any]],
) -> tuple[Scalable3DObservationTruthLabel, ...]:
    return tuple(
        value
        if isinstance(value, Scalable3DObservationTruthLabel)
        else Scalable3DObservationTruthLabel.from_mapping(
            _as_mapping(value, "observation truth label")
        )
        for value in values
    )


def _valid_lifecycle_transition(previous: str, current: str) -> bool:
    allowed = {
        "tentative": _LIFECYCLE_STATES,
        "confirmed": {"confirmed", "engageable", "lost", "dropped"},
        "engageable": {"engageable", "lost", "dropped"},
        "lost": {"lost", "confirmed", "engageable", "dropped"},
        "dropped": {"dropped"},
    }
    return current in allowed[previous]


def _forbidden_online_identity_key(key: str) -> bool:
    collapsed = key.replace("_", "")
    if (
        key == "truth"
        or key == "truth_id"
        or key.startswith("truth_target")
        or key.startswith("truth_entity")
        or key.startswith("ground_truth")
        or key.startswith("offline_truth")
        or "groundtruth" in collapsed
        or "truthid" in collapsed
    ):
        return True
    if key in {
        "actor_id",
        "actor_name",
        "airsim_id",
        "entity_id",
        "entity_name",
        "object_id",
        "object_name",
        "target_id",
        "target_name",
    }:
        return True
    return any(
        collapsed.startswith(domain)
        and collapsed.endswith(("id", "name", "uuid", "identity"))
        for domain in ("actor", "airsim", "entity", "object", "target")
    )


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _reason_sort_key(reason: str) -> tuple[int, str]:
    priority = {
        "observation_truth_labels_unavailable": 0,
        "conflicting_observation_truth_labels": 1,
        "multiple_truth_targets_for_global_track": 2,
        "lineage_claimed_by_multiple_tracks": 3,
        "observation_claimed_by_multiple_tracks": 4,
        "lineage_rebound_to_different_track": 5,
        "duplicate_lineage_within_track_frame": 6,
        "truth_label_missing": 7,
        "truth_label_timestamp_mismatch": 8,
        "source_observation_from_future": 9,
        "source_observation_outside_lineage_window": 10,
        "source_lineage_missing": 11,
        "track_not_assigned_in_frame": 99,
    }
    return priority.get(reason, 50), reason


def _validated_source_hashes(
    source_hashes: Mapping[str, str],
    *,
    required: set[str],
) -> dict[str, str]:
    if not isinstance(source_hashes, Mapping):
        raise ValueError("source_hashes must be a mapping")
    normalized = {
        _identifier(key, "source hash name"): _normalized_sha256(value)
        for key, value in source_hashes.items()
    }
    missing = required - set(normalized)
    if missing:
        raise ValueError(f"missing required source hashes: {sorted(missing)}")
    return dict(sorted(normalized.items()))


def _normalized_sha256(value: Any) -> str:
    digest = str(value).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest):
        digest = f"sha256:{digest}"
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"invalid sha256 digest: {value!r}")
    return digest


def _verify_file_hash(path: str | Path, expected_sha256: str, name: str) -> None:
    expected = _normalized_sha256(expected_sha256)
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{name} sha256 mismatch: expected {expected}, got {actual}"
        )


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical_json_bytes(payload) + b"\n")
    return sha256_file(output)


def _load_json_object(path: str | Path, name: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {name}") from exc
    return _as_mapping(payload, name)


def _load_jsonl_objects(
    path: str | Path,
    name: str,
) -> tuple[Mapping[str, Any], ...]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot load {name}") from exc
    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid {name} JSONL line {line_number}") from exc
        records.append(_as_mapping(payload, f"{name} line {line_number}"))
    return tuple(records)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_jsonl_bytes(values: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(value) + b"\n" for value in values)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _identifier(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must be non-empty")
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _timestamp(value: Any, name: str) -> float:
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _nonnegative_finite(value: Any, name: str) -> float:
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if result < 0 or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _unit_interval(value: Any, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} must be available")
    result = float(value)
    if not isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and within [0, 1]")
    return result


def _partial_coverage(
    numerator: int,
    denominator: int,
    *,
    unavailable_reason: str,
) -> tuple[float | None, str | None]:
    if denominator == 0:
        return None, unavailable_reason
    return float(numerator / denominator), None


def _validated_partial_coverage(
    value: Any,
    reason: Any,
    *,
    numerator: int,
    denominator: int,
    unavailable_reason: str,
    name: str,
) -> tuple[float | None, str | None]:
    normalized_reason = _optional_reason(reason)
    if denominator == 0:
        if value is not None:
            raise ValueError(f"{name} must be unavailable for a zero denominator")
        if normalized_reason != unavailable_reason:
            raise ValueError(f"{name} has an invalid unavailable reason")
        return None, normalized_reason
    normalized_value = _unit_interval(value, name)
    expected = numerator / denominator
    if abs(normalized_value - expected) > 1.0e-12:
        raise ValueError(f"{name} contradicts its numerator and denominator")
    if normalized_reason is not None:
        raise ValueError(f"available {name} must not carry a reason")
    return normalized_value, None


def _optional_reason(value: Any) -> str | None:
    return None if value is None else _required_reason(value, "metric reason")


def _required_reason(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must be non-empty")
    return _identifier(value, name)


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _as_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise ValueError(f"{name} must be an array")
    return value


def _finite_number_sequence(value: Any, size: int, name: str) -> tuple[float, ...]:
    items = _as_sequence(value, name)
    if len(items) != size:
        raise ValueError(f"{name} must contain {size} finite values")
    output = tuple(float(item) for item in items)
    if not all(isfinite(item) for item in output):
        raise ValueError(f"{name} must contain {size} finite values")
    return output


def _finite_number_matrix(
    value: Any,
    size: int,
    name: str,
) -> tuple[tuple[float, ...], ...]:
    rows = _as_sequence(value, name)
    if len(rows) != size:
        raise ValueError(f"{name} must have shape {size}x{size}")
    output = tuple(
        _finite_number_sequence(row, size, name)
        for row in rows
    )
    for row_index in range(size):
        if output[row_index][row_index] < 0.0:
            raise ValueError(f"{name} diagonal must be non-negative")
        for column_index in range(row_index + 1, size):
            if abs(
                output[row_index][column_index]
                - output[column_index][row_index]
            ) > 1.0e-8:
                raise ValueError(f"{name} must be symmetric")
    return output


def _reject_unknown_keys(
    payload: Mapping[str, Any],
    allowed: set[str],
    name: str,
) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{name} contains unsupported fields: {sorted(unknown)}")


def _count_mapping(value: Any, name: str) -> dict[str, int]:
    return {
        _identifier(key, f"{name} key"): _nonnegative_int(item, f"{name} count")
        for key, item in _as_mapping(value, name).items()
    }


def _count_matrix(value: Any, name: str) -> dict[str, dict[str, int]]:
    return {
        _identifier(truth_id, f"{name} truth ID"): _count_mapping(
            track_counts,
            f"{name} track counts",
        )
        for truth_id, track_counts in _as_mapping(value, name).items()
    }


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0
