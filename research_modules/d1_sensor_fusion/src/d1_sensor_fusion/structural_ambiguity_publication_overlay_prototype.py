from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from numbers import Integral, Real
from typing import Any

import numpy as np

from .types import GlobalTrack, StructuralAmbiguityEvidence


EXPERIMENTAL_CENTROID_PUBLICATION_DECISION_SCHEMA_VERSION = (
    "d1.experimental-centroid-publication-overlay-decision.v1"
)
EXPERIMENTAL_CENTROID_PUBLICATION_PROTOTYPE_STATUS = (
    "experimental_design_prototype_not_online_schema"
)
EXPERIMENTAL_CENTROID_PUBLICATION_STATE_SEMANTICS = (
    "publication_overlay_not_filter_posterior"
)

_DECISION_ID_PREFIX = "d1-experimental-centroid-decision-sha256:"
_DIGEST_PREFIX = "sha256:"
_IDENTITY_EXACT_KEYS = frozenset(
    {
        "actor",
        "actor_id",
        "actor_name",
        "offline_label",
        "target",
        "target_id",
        "target_label",
        "target_name",
        "truth",
        "truth_id",
        "truth_label",
    }
)
_IDENTITY_MARKERS = (
    "actor",
    "offline",
    "target_id",
    "target_label",
    "target_name",
    "truth",
)
_IDENTITY_ALLOWED_KEYS = frozenset({"target_node_id"})
_MATCHED_EDGE_ROLES = (
    "matched_reference",
    "maximum_matching_allowed",
)
_ALTERNATE_EDGE_ROLES = (
    "alternating_cycle",
    "maximum_matching_allowed",
)


@dataclass(frozen=True)
class ExperimentalCentroidPublicationOverlayConfig:
    """A1-only numerical policy; this is not an online FusionAdapter config."""

    max_component_size: int = 8
    centroid_gain: float = 0.5
    max_translation_m: float = 30.0
    centroid_gate_chi2: float = 16.26623619623813
    shape_gate_m2: float = 2_500.0
    shape_inflation_scale: float = 0.05
    min_position_variance_m2: float = 0.25

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_component_size, bool)
            or not isinstance(self.max_component_size, Integral)
            or int(self.max_component_size) < 2
        ):
            raise ValueError("max_component_size must be an integer of at least 2")
        object.__setattr__(self, "max_component_size", int(self.max_component_size))
        for name, minimum, maximum in (
            ("centroid_gain", 0.0, 1.0),
            ("max_translation_m", 0.0, None),
            ("centroid_gate_chi2", 0.0, None),
            ("shape_gate_m2", 0.0, None),
            ("shape_inflation_scale", 0.0, None),
            ("min_position_variance_m2", 0.0, None),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")
            number = float(value)
            if not np.isfinite(number) or number < minimum:
                raise ValueError(f"{name} must be finite and at least {minimum}")
            if name in {
                "max_translation_m",
                "centroid_gate_chi2",
                "min_position_variance_m2",
            } and number <= 0.0:
                raise ValueError(f"{name} must be positive")
            if maximum is not None and number > maximum:
                raise ValueError(f"{name} must be at most {maximum}")
            object.__setattr__(self, name, number)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_component_size": self.max_component_size,
            "centroid_gain": self.centroid_gain,
            "max_translation_m": self.max_translation_m,
            "centroid_gate_chi2": self.centroid_gate_chi2,
            "shape_gate_m2": self.shape_gate_m2,
            "shape_inflation_scale": self.shape_inflation_scale,
            "min_position_variance_m2": self.min_position_variance_m2,
        }


@dataclass(frozen=True)
class ExperimentalCentroidEvidenceDisposition:
    """Truth-free scan disposition supplied by an offline A1 caller."""

    oosm_evidence_ids: frozenset[str] = field(default_factory=frozenset)
    stale_evidence_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "oosm_evidence_ids",
            frozenset(str(item) for item in self.oosm_evidence_ids),
        )
        object.__setattr__(
            self,
            "stale_evidence_ids",
            frozenset(str(item) for item in self.stale_evidence_ids),
        )


@dataclass(frozen=True)
class ExperimentalCentroidGenerationWatermark:
    component_id: str
    max_seen_generation: int
    evidence_summary_digest: str
    last_measurement_timestamp: float

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("component_id must be non-empty")
        if (
            isinstance(self.max_seen_generation, bool)
            or int(self.max_seen_generation) < 1
        ):
            raise ValueError("max_seen_generation must be at least one")
        if not _is_digest(self.evidence_summary_digest):
            raise ValueError("evidence_summary_digest must be a SHA-256 digest")
        timestamp = float(self.last_measurement_timestamp)
        if not np.isfinite(timestamp):
            raise ValueError("last_measurement_timestamp must be finite")
        object.__setattr__(self, "max_seen_generation", int(self.max_seen_generation))
        object.__setattr__(self, "last_measurement_timestamp", timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "max_seen_generation": self.max_seen_generation,
            "evidence_summary_digest": self.evidence_summary_digest,
            "last_measurement_timestamp": self.last_measurement_timestamp,
        }


@dataclass(frozen=True)
class ExperimentalCentroidPublicationState:
    """Bounded immutable A1 generation registry."""

    watermarks: tuple[ExperimentalCentroidGenerationWatermark, ...] = ()
    max_entries: int = 1_024
    retention_horizon_s: float = 2.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_entries, bool)
            or not isinstance(self.max_entries, Integral)
            or int(self.max_entries) < 1
        ):
            raise ValueError("max_entries must be a positive integer")
        horizon = float(self.retention_horizon_s)
        if not np.isfinite(horizon) or horizon <= 0.0:
            raise ValueError("retention_horizon_s must be finite and positive")
        normalized = tuple(
            sorted(self.watermarks, key=lambda item: _text_key(item.component_id))
        )
        component_ids = tuple(item.component_id for item in normalized)
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("generation watermarks must have unique component_id")
        if len(normalized) > int(self.max_entries):
            raise ValueError("generation watermarks exceed max_entries")
        object.__setattr__(self, "watermarks", normalized)
        object.__setattr__(self, "max_entries", int(self.max_entries))
        object.__setattr__(self, "retention_horizon_s", horizon)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_entries": self.max_entries,
            "retention_horizon_s": self.retention_horizon_s,
            "watermarks": [item.to_dict() for item in self.watermarks],
        }


@dataclass(frozen=True)
class ExperimentalCentroidMemberOverlayV1:
    """Detached member overlay for the A1 design prototype."""

    source_key: str
    opaque_member_track_token: str
    base_track_revision: str
    base_state_digest: str
    base_covariance_digest: str
    delta_position_ned: np.ndarray
    delta_position_covariance: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "source_key",
            "opaque_member_track_token",
            "base_track_revision",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        for name in ("base_state_digest", "base_covariance_digest"):
            if not _is_digest(getattr(self, name)):
                raise ValueError(f"{name} must be a SHA-256 digest")
        delta = np.asarray(self.delta_position_ned, dtype=float)
        covariance = np.asarray(self.delta_position_covariance, dtype=float)
        if delta.shape != (3,) or not np.isfinite(delta).all():
            raise ValueError("delta_position_ned must be finite shape (3,)")
        if covariance.shape != (3, 3) or not np.isfinite(covariance).all():
            raise ValueError(
                "delta_position_covariance must be finite shape (3, 3)"
            )
        if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-10):
            raise ValueError("delta_position_covariance must be symmetric")
        covariance = 0.5 * (covariance + covariance.T)
        if float(np.linalg.eigvalsh(covariance)[0]) < -1.0e-9:
            raise ValueError("delta_position_covariance must be PSD")
        delta = delta.copy()
        covariance = covariance.copy()
        delta.setflags(write=False)
        covariance.setflags(write=False)
        object.__setattr__(self, "delta_position_ned", delta)
        object.__setattr__(self, "delta_position_covariance", covariance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "opaque_member_track_token": self.opaque_member_track_token,
            "base_track_revision": self.base_track_revision,
            "base_state_digest": self.base_state_digest,
            "base_covariance_digest": self.base_covariance_digest,
            "delta_position_ned": self.delta_position_ned.tolist(),
            "delta_position_covariance": (
                self.delta_position_covariance.tolist()
            ),
        }


@dataclass(frozen=True)
class ExperimentalCentroidPublicationDecisionV1:
    """A1 decision record; explicitly not a current online publication schema."""

    decision_id: str
    decision: str
    reject_reason: str | None
    evidence_id: str
    component_id: str
    component_generation: int
    publisher_node_id: str
    publisher_epoch: str
    sensor_id: str
    scan_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    state_valid_timestamp: float
    published_at: float
    base_publication_revision: str
    base_publication_digest: str
    evidence_summary_digest: str
    prototype_config_digest: str
    overlay_valid_for_publication_id: str
    member_overlays: tuple[ExperimentalCentroidMemberOverlayV1, ...]
    centroid_nis: float | None = None
    shape_mismatch_m2: float | None = None
    schema_version: str = EXPERIMENTAL_CENTROID_PUBLICATION_DECISION_SCHEMA_VERSION
    prototype_status: str = EXPERIMENTAL_CENTROID_PUBLICATION_PROTOTYPE_STATUS
    state_semantics: str = EXPERIMENTAL_CENTROID_PUBLICATION_STATE_SEMANTICS
    cross_covariance_available: bool = False
    mutates_filter_history: bool = False

    def __post_init__(self) -> None:
        if self.decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be accepted or rejected")
        if self.decision == "accepted":
            if self.reject_reason is not None or not self.member_overlays:
                raise ValueError("accepted decisions require non-empty overlays")
        elif self.reject_reason is None or self.member_overlays:
            raise ValueError("rejected decisions require a reason and empty overlays")
        if not self.decision_id.startswith(_DECISION_ID_PREFIX):
            raise ValueError("decision_id has an invalid prefix")
        if not _is_digest(self.base_publication_digest):
            raise ValueError("base_publication_digest must be a SHA-256 digest")
        if not _is_digest(self.evidence_summary_digest):
            raise ValueError("evidence_summary_digest must be a SHA-256 digest")
        if not _is_digest(self.prototype_config_digest):
            raise ValueError("prototype_config_digest must be a SHA-256 digest")
        if self.cross_covariance_available or self.mutates_filter_history:
            raise ValueError("A1 cannot expose cross covariance or mutate history")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prototype_status": self.prototype_status,
            "decision_id": self.decision_id,
            "decision": self.decision,
            "reject_reason": self.reject_reason,
            "evidence_id": self.evidence_id,
            "component_id": self.component_id,
            "component_generation": self.component_generation,
            "publisher_node_id": self.publisher_node_id,
            "publisher_epoch": self.publisher_epoch,
            "sensor_id": self.sensor_id,
            "scan_id": self.scan_id,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "state_valid_timestamp": self.state_valid_timestamp,
            "published_at": self.published_at,
            "base_publication_revision": self.base_publication_revision,
            "base_publication_digest": self.base_publication_digest,
            "evidence_summary_digest": self.evidence_summary_digest,
            "prototype_config_digest": self.prototype_config_digest,
            "state_semantics": self.state_semantics,
            "overlay_valid_for_publication_id": (
                self.overlay_valid_for_publication_id
            ),
            "member_overlays": [item.to_dict() for item in self.member_overlays],
            "centroid_nis": self.centroid_nis,
            "shape_mismatch_m2": self.shape_mismatch_m2,
            "cross_covariance_available": self.cross_covariance_available,
            "mutates_filter_history": self.mutates_filter_history,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class ExperimentalCentroidPublicationEvaluation:
    decisions: tuple[ExperimentalCentroidPublicationDecisionV1, ...]
    next_state: ExperimentalCentroidPublicationState

    def to_dict(self) -> dict[str, Any]:
        return {
            "prototype_status": EXPERIMENTAL_CENTROID_PUBLICATION_PROTOTYPE_STATUS,
            "decisions": [item.to_dict() for item in self.decisions],
            "next_state": self.next_state.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class _TrackDescriptor:
    track: GlobalTrack
    source_key: str | None
    member_token: str | None
    track_digest: str
    state_digest: str
    covariance_digest: str


@dataclass(frozen=True)
class _EvidenceEnvelope:
    evidence: StructuralAmbiguityEvidence | None
    evidence_id: str
    component_id: str
    generation: int
    publisher_node_id: str
    publisher_epoch: str
    sensor_id: str
    scan_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    state_valid_timestamp: float
    published_at: float
    summary_digest: str
    invalid_reason: str | None

    @property
    def component_key(self) -> tuple[Any, ...]:
        return (
            self.published_at,
            self.state_valid_timestamp,
            self.measurement_timestamp,
            self.arrival_timestamp,
            _text_key(self.publisher_node_id),
            _text_key(self.publisher_epoch),
            _text_key(self.sensor_id),
            _text_key(self.scan_id),
            _text_key(self.component_id),
            self.generation,
            _text_key(self.evidence_id),
            _text_key(self.summary_digest),
        )


def evaluate_experimental_centroid_publication_overlays(
    canonical_tracks: Sequence[GlobalTrack],
    evidence_items: Sequence[StructuralAmbiguityEvidence],
    *,
    state: ExperimentalCentroidPublicationState | None = None,
    config: ExperimentalCentroidPublicationOverlayConfig | None = None,
    disposition: ExperimentalCentroidEvidenceDisposition | None = None,
    base_publication_revision: str | None = None,
    overlay_valid_for_publication_id: str | None = None,
) -> ExperimentalCentroidPublicationEvaluation:
    """Evaluate A1 overlays without touching tracks, filters, or history."""

    state = state or ExperimentalCentroidPublicationState()
    config = config or ExperimentalCentroidPublicationOverlayConfig()
    disposition = disposition or ExperimentalCentroidEvidenceDisposition()
    envelopes = tuple(sorted(
        (_normalize_evidence(item) for item in evidence_items),
        key=lambda item: item.component_key,
    ))
    descriptors, base_digest, base_error = _describe_tracks(canonical_tracks)
    revision = (
        str(base_publication_revision).strip()
        if base_publication_revision is not None
        else f"experimental-publication-{base_digest}"
    )
    if not revision:
        raise ValueError("base_publication_revision must be non-empty")
    publication_id = (
        str(overlay_valid_for_publication_id).strip()
        if overlay_valid_for_publication_id is not None
        else revision
    )
    if not publication_id:
        raise ValueError("overlay_valid_for_publication_id must be non-empty")
    config_digest = _digest(config.to_dict())

    reference_time = max(
        (item.published_at for item in envelopes),
        default=0.0,
    )
    watermark_map = {
        item.component_id: item
        for item in state.watermarks
        if item.last_measurement_timestamp
        >= reference_time - state.retention_horizon_s - 1.0e-12
    }

    same_generation_groups: dict[tuple[str, int], list[_EvidenceEnvelope]] = {}
    full_key_groups: dict[tuple[Any, ...], list[_EvidenceEnvelope]] = {}
    member_groups: dict[tuple[str, str], set[tuple[str, int, str]]] = {}
    for envelope in envelopes:
        group_key = (envelope.component_id, envelope.generation)
        same_generation_groups.setdefault(group_key, []).append(envelope)
        full_key_groups.setdefault(envelope.component_key[:-1], []).append(envelope)
        if envelope.evidence is not None:
            marker = (
                envelope.component_id,
                envelope.generation,
                envelope.evidence_id,
            )
            for member in envelope.evidence.member_states:
                member_groups.setdefault(
                    (member.source_key, member.opaque_member_track_token),
                    set(),
                ).add(marker)

    batch_reason: dict[int, str] = {}
    for group in full_key_groups.values():
        if len(group) > 1:
            reason = (
                "generation_summary_conflict"
                if len({item.summary_digest for item in group}) > 1
                else "duplicate_component_key"
            )
            batch_reason.update({id(item): reason for item in group})
    conflicting_markers = {
        marker
        for markers in member_groups.values()
        if len(markers) > 1
        for marker in markers
    }
    for envelope in envelopes:
        marker = (
            envelope.component_id,
            envelope.generation,
            envelope.evidence_id,
        )
        if marker in conflicting_markers:
            batch_reason.setdefault(id(envelope), "conflicting_component_membership")

    admission_reasons: dict[tuple[str, int], str | None] = {}
    ordered_groups = sorted(
        same_generation_groups.items(),
        key=lambda item: item[1][0].component_key,
    )
    for group_key, group in ordered_groups:
        representative = group[0]
        if (
            representative.evidence is None
            or representative.generation < 1
            or not np.isfinite(representative.measurement_timestamp)
        ):
            admission_reasons[group_key] = "invalid_evidence_contract"
            continue
        if (
            representative.measurement_timestamp
            < reference_time - state.retention_horizon_s - 1.0e-12
        ):
            admission_reasons[group_key] = "evidence_outside_generation_window"
            continue
        summaries = sorted({item.summary_digest for item in group})
        group_digest = (
            summaries[0]
            if len(summaries) == 1
            else _digest({"conflicting_summaries": summaries})
        )
        watermark = watermark_map.get(representative.component_id)
        if watermark is not None:
            if representative.generation < watermark.max_seen_generation:
                admission_reasons[group_key] = "regressed_evidence_generation"
                continue
            if representative.generation == watermark.max_seen_generation:
                admission_reasons[group_key] = (
                    "duplicate_evidence_generation"
                    if group_digest == watermark.evidence_summary_digest
                    else "generation_summary_conflict"
                )
                continue
        elif len(watermark_map) >= state.max_entries:
            admission_reasons[group_key] = (
                "generation_registry_capacity_reached"
            )
            continue
        watermark_map[representative.component_id] = (
            ExperimentalCentroidGenerationWatermark(
                component_id=representative.component_id,
                max_seen_generation=representative.generation,
                evidence_summary_digest=group_digest,
                last_measurement_timestamp=max(
                    representative.measurement_timestamp,
                    (
                        watermark.last_measurement_timestamp
                        if watermark is not None
                        else representative.measurement_timestamp
                    ),
                ),
            )
        )
        admission_reasons[group_key] = None

    decisions: list[ExperimentalCentroidPublicationDecisionV1] = []
    for envelope in envelopes:
        reason = (
            envelope.invalid_reason
            or batch_reason.get(id(envelope))
            or admission_reasons.get(
                (envelope.component_id, envelope.generation)
            )
            or base_error
        )
        overlays: tuple[ExperimentalCentroidMemberOverlayV1, ...] = ()
        centroid_nis: float | None = None
        shape_mismatch: float | None = None
        if reason is None and envelope.evidence_id in disposition.oosm_evidence_ids:
            reason = "oosm_scan"
        if reason is None and envelope.evidence_id in disposition.stale_evidence_ids:
            reason = "stale_scan"
        if reason is None:
            assert envelope.evidence is not None
            overlays, centroid_nis, shape_mismatch, reason = (
                _build_component_overlays(
                    envelope.evidence,
                    descriptors,
                    config,
                )
            )
        decisions.append(
            _make_decision(
                envelope,
                reason=reason,
                overlays=overlays,
                centroid_nis=centroid_nis,
                shape_mismatch_m2=shape_mismatch,
                base_publication_revision=revision,
                base_publication_digest=base_digest,
                prototype_config_digest=config_digest,
                overlay_valid_for_publication_id=publication_id,
            )
        )

    decisions.sort(key=lambda item: _decision_sort_key(item))
    next_state = ExperimentalCentroidPublicationState(
        watermarks=tuple(watermark_map.values()),
        max_entries=state.max_entries,
        retention_horizon_s=state.retention_horizon_s,
    )
    return ExperimentalCentroidPublicationEvaluation(
        decisions=tuple(decisions),
        next_state=next_state,
    )


def assemble_experimental_centroid_shadow_tracks(
    canonical_tracks: Sequence[GlobalTrack],
    decisions: (
        ExperimentalCentroidPublicationDecisionV1
        | Sequence[ExperimentalCentroidPublicationDecisionV1]
        | ExperimentalCentroidPublicationEvaluation
    ),
) -> Sequence[GlobalTrack]:
    """Apply accepted overlays to detached DTO copies.

    With no accepted decision, or on any validation mismatch, the exact input
    sequence object is returned. The function never rebuilds a rejected path.
    """

    if isinstance(decisions, ExperimentalCentroidPublicationEvaluation):
        decision_items = decisions.decisions
    elif isinstance(decisions, ExperimentalCentroidPublicationDecisionV1):
        decision_items = (decisions,)
    else:
        decision_items = tuple(decisions)
    accepted = tuple(item for item in decision_items if item.decision == "accepted")
    if not accepted:
        return canonical_tracks

    descriptors, base_digest, error = _describe_tracks(canonical_tracks)
    if error is not None:
        return canonical_tracks
    if any(item.base_publication_digest != base_digest for item in accepted):
        return canonical_tracks
    by_member: dict[tuple[str, str], list[_TrackDescriptor]] = {}
    for descriptor in descriptors:
        if descriptor.source_key is not None and descriptor.member_token is not None:
            by_member.setdefault(
                (descriptor.source_key, descriptor.member_token),
                [],
            ).append(descriptor)

    overlays: dict[tuple[str, str], ExperimentalCentroidMemberOverlayV1] = {}
    for decision in accepted:
        for overlay in decision.member_overlays:
            key = (overlay.source_key, overlay.opaque_member_track_token)
            if key in overlays:
                return canonical_tracks
            candidates = by_member.get(key, ())
            if len(candidates) != 1:
                return canonical_tracks
            descriptor = candidates[0]
            if (
                overlay.base_track_revision != descriptor.track_digest
                or overlay.base_state_digest != descriptor.state_digest
                or overlay.base_covariance_digest
                != descriptor.covariance_digest
            ):
                return canonical_tracks
            overlays[key] = overlay

    shadow_tracks: list[GlobalTrack] = []
    for descriptor in descriptors:
        track = descriptor.track
        copied = GlobalTrack(
            global_track_id=track.global_track_id,
            state=track.state.copy(),
            covariance=track.covariance.copy(),
            timestamp=track.timestamp,
            track_level=track.track_level,
            source_support=deepcopy(track.source_support),
            identity_likelihood=deepcopy(track.identity_likelihood),
            last_nis=track.last_nis,
            metadata=deepcopy(track.metadata),
        )
        key = (descriptor.source_key, descriptor.member_token)
        overlay = overlays.get(key)
        if overlay is not None:
            copied.state[:3] += overlay.delta_position_ned
            copied.covariance[:3, :3] += (
                overlay.delta_position_covariance
            )
            if (
                not np.isfinite(copied.state).all()
                or not np.isfinite(copied.covariance).all()
                or float(np.linalg.eigvalsh(copied.covariance)[0]) < -1.0e-8
            ):
                return canonical_tracks
        shadow_tracks.append(copied)
    return tuple(shadow_tracks)


def _build_component_overlays(
    evidence: StructuralAmbiguityEvidence,
    descriptors: tuple[_TrackDescriptor, ...],
    config: ExperimentalCentroidPublicationOverlayConfig,
) -> tuple[
    tuple[ExperimentalCentroidMemberOverlayV1, ...],
    float | None,
    float | None,
    str | None,
]:
    member_count = evidence.member_count
    if member_count != evidence.observation_count:
        return (), None, None, "unbalanced_component"
    if member_count < 2:
        return (), None, None, "component_too_small"
    if member_count > config.max_component_size:
        return (), None, None, "component_exceeds_k_max"
    if evidence.free_row_count:
        return (), None, None, "free_row_present"
    if evidence.free_column_count:
        return (), None, None, "free_column_present"
    if evidence.maximum_matching_cardinality != member_count:
        return (), None, None, "maximum_matching_not_full"
    if not _is_pure_alternating_cycle(evidence):
        return (), None, None, "component_not_pure_alternating_cycle"
    if evidence.frame_id != "NED" or evidence.cross_covariance_available:
        return (), None, None, "evidence_frame_or_cross_covariance_invalid"

    by_member: dict[tuple[str, str], list[_TrackDescriptor]] = {}
    for descriptor in descriptors:
        if descriptor.source_key is not None and descriptor.member_token is not None:
            by_member.setdefault(
                (descriptor.source_key, descriptor.member_token),
                [],
            ).append(descriptor)
    matched_descriptors: list[_TrackDescriptor] = []
    for member in evidence.member_states:
        candidates = by_member.get(
            (member.source_key, member.opaque_member_track_token),
            (),
        )
        if not candidates:
            return (), None, None, "member_track_missing"
        if len(candidates) != 1:
            return (), None, None, "member_track_duplicate"
        descriptor = candidates[0]
        if abs(descriptor.track.timestamp - evidence.published_at) > 1.0e-9:
            return (), None, None, "base_publication_timestamp_mismatch"
        matched_descriptors.append(descriptor)

    member_positions = np.stack(
        [item.state[:3] for item in evidence.member_states],
        axis=0,
    )
    observation_positions = np.stack(
        [item.position_ned for item in evidence.observations],
        axis=0,
    )
    predicted_centroid = np.mean(member_positions, axis=0)
    observed_centroid = np.mean(observation_positions, axis=0)
    innovation = observed_centroid - predicted_centroid
    member_shape = (
        (member_positions - predicted_centroid).T
        @ (member_positions - predicted_centroid)
        / member_count
    )
    observation_shape = (
        (observation_positions - observed_centroid).T
        @ (observation_positions - observed_centroid)
        / member_count
    )
    shape_mismatch = float(
        np.linalg.norm(observation_shape - member_shape, ord="fro")
    )
    if not np.isfinite(shape_mismatch):
        return (), None, None, "nonfinite_input"
    if shape_mismatch > config.shape_gate_m2 + 1.0e-12:
        return (), None, shape_mismatch, "shape_gate_rejected"

    centroid_covariance = sum(
        (
            np.asarray(item.covariance[:3, :3], dtype=float)
            for item in evidence.member_states
        ),
        start=np.zeros((3, 3), dtype=float),
    ) / float(member_count * member_count)
    centroid_covariance += sum(
        (
            np.asarray(item.covariance_ned, dtype=float)
            for item in evidence.observations
        ),
        start=np.zeros((3, 3), dtype=float),
    ) / float(member_count * member_count)
    centroid_covariance = 0.5 * (
        centroid_covariance + centroid_covariance.T
    )
    if not np.isfinite(centroid_covariance).all():
        return (), None, shape_mismatch, "nonfinite_input"
    if float(np.linalg.eigvalsh(centroid_covariance)[0]) < -1.0e-8:
        return (), None, shape_mismatch, "centroid_covariance_not_psd"
    innovation_covariance = (
        centroid_covariance
        + config.min_position_variance_m2 * np.eye(3)
    )
    try:
        centroid_nis = float(
            innovation.T @ np.linalg.pinv(innovation_covariance) @ innovation
        )
    except np.linalg.LinAlgError:
        return (), None, shape_mismatch, "centroid_innovation_solve_failed"
    if not np.isfinite(centroid_nis):
        return (), None, shape_mismatch, "nonfinite_input"
    if centroid_nis > config.centroid_gate_chi2 + 1.0e-12:
        return (), centroid_nis, shape_mismatch, "centroid_gate_rejected"

    innovation_norm = float(np.linalg.norm(innovation))
    clipped = innovation
    if innovation_norm > config.max_translation_m:
        clipped = innovation * (config.max_translation_m / innovation_norm)
    delta_position = config.centroid_gain * clipped
    delta_covariance = (
        config.centroid_gain**2 * centroid_covariance
        + (
            config.shape_inflation_scale * shape_mismatch
            + config.min_position_variance_m2
        )
        * np.eye(3)
    )
    delta_covariance = 0.5 * (delta_covariance + delta_covariance.T)
    if (
        not np.isfinite(delta_position).all()
        or not np.isfinite(delta_covariance).all()
        or float(np.linalg.eigvalsh(delta_covariance)[0]) < -1.0e-8
    ):
        return (), centroid_nis, shape_mismatch, "nonfinite_or_non_psd_overlay"

    pairs = sorted(
        zip(evidence.member_states, matched_descriptors, strict=True),
        key=lambda item: (
            _text_key(item[0].source_key),
            _text_key(item[0].opaque_member_track_token),
        ),
    )
    overlays = tuple(
        ExperimentalCentroidMemberOverlayV1(
            source_key=member.source_key,
            opaque_member_track_token=member.opaque_member_track_token,
            base_track_revision=descriptor.track_digest,
            base_state_digest=descriptor.state_digest,
            base_covariance_digest=descriptor.covariance_digest,
            delta_position_ned=delta_position,
            delta_position_covariance=delta_covariance,
        )
        for member, descriptor in pairs
    )
    return overlays, centroid_nis, shape_mismatch, None


def _is_pure_alternating_cycle(
    evidence: StructuralAmbiguityEvidence,
) -> bool:
    if evidence.component_kinds != ("alternating_cycle",):
        return False
    members = {
        item.opaque_member_track_token for item in evidence.member_states
    }
    observations = {
        item.observation_evidence_key for item in evidence.observations
    }
    if len(evidence.candidate_edges) != 2 * len(members):
        return False
    member_neighbors = {item: set() for item in members}
    observation_neighbors = {item: set() for item in observations}
    matched_members: set[str] = set()
    matched_observations: set[str] = set()
    alternate_members: set[str] = set()
    alternate_observations: set[str] = set()
    for edge in evidence.candidate_edges:
        if (
            edge.opaque_member_track_token not in member_neighbors
            or edge.observation_evidence_key not in observation_neighbors
        ):
            return False
        member_neighbors[edge.opaque_member_track_token].add(
            edge.observation_evidence_key
        )
        observation_neighbors[edge.observation_evidence_key].add(
            edge.opaque_member_track_token
        )
        if edge.edge_roles == _MATCHED_EDGE_ROLES:
            matched_members.add(edge.opaque_member_track_token)
            matched_observations.add(edge.observation_evidence_key)
        elif edge.edge_roles == _ALTERNATE_EDGE_ROLES:
            alternate_members.add(edge.opaque_member_track_token)
            alternate_observations.add(edge.observation_evidence_key)
        else:
            return False
    if (
        any(len(items) != 2 for items in member_neighbors.values())
        or any(len(items) != 2 for items in observation_neighbors.values())
        or matched_members != members
        or matched_observations != observations
        or alternate_members != members
        or alternate_observations != observations
    ):
        return False

    first = ("member", next(iter(sorted(members, key=_text_key))))
    visited = {first}
    pending = [first]
    while pending:
        kind, token = pending.pop()
        neighbors = (
            (("observation", item) for item in member_neighbors[token])
            if kind == "member"
            else (("member", item) for item in observation_neighbors[token])
        )
        for neighbor in neighbors:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return len(visited) == len(members) + len(observations)


def _normalize_evidence(
    evidence: StructuralAmbiguityEvidence,
) -> _EvidenceEnvelope:
    if not isinstance(evidence, StructuralAmbiguityEvidence):
        raise TypeError("evidence_items must contain StructuralAmbiguityEvidence")
    safe = {
        "evidence_id": _safe_text(evidence.evidence_id),
        "component_id": _safe_text(evidence.component_id),
        "generation": _safe_int(evidence.component_generation),
        "publisher_node_id": _safe_text(evidence.publisher_node_id),
        "publisher_epoch": _safe_text(evidence.publisher_epoch),
        "sensor_id": _safe_text(evidence.sensor_id),
        "scan_id": _safe_text(evidence.scan_id),
        "measurement_timestamp": _safe_float(evidence.measurement_timestamp),
        "arrival_timestamp": _safe_float(evidence.arrival_timestamp),
        "state_valid_timestamp": _safe_float(evidence.state_valid_timestamp),
        "published_at": _safe_float(evidence.published_at),
    }
    try:
        normalized = StructuralAmbiguityEvidence.from_dict(evidence.to_dict())
        summary = _digest(normalized.to_dict())
        reason = None
    except (TypeError, ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        normalized = None
        message = str(exc).lower()
        reason = (
            "nonfinite_input"
            if "finite" in message or "nan" in message or "inf" in message
            else "invalid_evidence_contract"
        )
        summary = _digest(
            {
                "invalid_evidence": safe,
                "reject_reason": reason,
            }
        )
    return _EvidenceEnvelope(
        evidence=normalized,
        evidence_id=safe["evidence_id"],
        component_id=safe["component_id"],
        generation=safe["generation"],
        publisher_node_id=safe["publisher_node_id"],
        publisher_epoch=safe["publisher_epoch"],
        sensor_id=safe["sensor_id"],
        scan_id=safe["scan_id"],
        measurement_timestamp=safe["measurement_timestamp"],
        arrival_timestamp=safe["arrival_timestamp"],
        state_valid_timestamp=safe["state_valid_timestamp"],
        published_at=safe["published_at"],
        summary_digest=summary,
        invalid_reason=reason,
    )


def _describe_tracks(
    tracks: Sequence[GlobalTrack],
) -> tuple[tuple[_TrackDescriptor, ...], str, str | None]:
    descriptors: list[_TrackDescriptor] = []
    fallback: list[dict[str, str]] = []
    error: str | None = None
    seen_global_ids: set[str] = set()
    for track in tracks:
        if not isinstance(track, GlobalTrack):
            raise TypeError("canonical_tracks must contain GlobalTrack")
        source_key = (
            str(track.metadata.get("source_key"))
            if isinstance(track.metadata, Mapping)
            and track.metadata.get("source_key") is not None
            else None
        )
        member_token = (
            str(track.metadata.get("opaque_member_track_token"))
            if isinstance(track.metadata, Mapping)
            and track.metadata.get("opaque_member_track_token") is not None
            else None
        )
        fallback.append(
            {
                "global_track_id": _safe_text(track.global_track_id),
                "source_key": source_key or "",
                "opaque_member_track_token": member_token or "",
            }
        )
        try:
            global_track_id = str(track.global_track_id)
            if not global_track_id:
                raise ValueError("global_track_id must be non-empty")
            if global_track_id in seen_global_ids:
                raise ValueError("duplicate global_track_id")
            seen_global_ids.add(global_track_id)
            state = np.asarray(track.state, dtype=float)
            covariance = np.asarray(track.covariance, dtype=float)
            if state.shape != (6,) or covariance.shape != (6, 6):
                raise ValueError("GlobalTrack state/covariance shape is invalid")
            if not np.isfinite(state).all() or not np.isfinite(covariance).all():
                raise FloatingPointError("GlobalTrack contains nonfinite input")
            if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-10):
                raise ValueError("GlobalTrack covariance is not symmetric")
            if float(np.linalg.eigvalsh(covariance)[0]) < -1.0e-9:
                raise ValueError("GlobalTrack covariance is not PSD")
            timestamp = float(track.timestamp)
            if not np.isfinite(timestamp):
                raise FloatingPointError("GlobalTrack timestamp is nonfinite")
            if _contains_forbidden_identity_metadata(track.metadata):
                raise PermissionError("forbidden identity metadata")
            frame_id = (
                str(track.metadata.get("frame_id", "ned")).strip().upper()
                if isinstance(track.metadata, Mapping)
                else ""
            )
            if frame_id != "NED":
                raise ValueError("GlobalTrack must use NED")
            last_nis = None if track.last_nis is None else float(track.last_nis)
            if last_nis is not None and not np.isfinite(last_nis):
                raise FloatingPointError("GlobalTrack last_nis is nonfinite")
            payload = {
                "global_track_id": global_track_id,
                "state": state.tolist(),
                "covariance": covariance.tolist(),
                "timestamp": timestamp,
                "track_level": (
                    track.track_level.value
                    if isinstance(track.track_level, Enum)
                    else str(track.track_level)
                ),
                "source_support": track.source_support,
                "identity_likelihood": track.identity_likelihood,
                "last_nis": last_nis,
                "metadata": track.metadata,
            }
            track_digest = _digest(payload)
            descriptors.append(
                _TrackDescriptor(
                    track=track,
                    source_key=source_key,
                    member_token=member_token,
                    track_digest=track_digest,
                    state_digest=_digest(state.tolist()),
                    covariance_digest=_digest(covariance.tolist()),
                )
            )
        except PermissionError:
            error = error or "forbidden_identity_metadata"
        except (FloatingPointError, OverflowError):
            error = error or "nonfinite_input"
        except (TypeError, ValueError, np.linalg.LinAlgError):
            error = error or "canonical_publication_invalid"
    if error is not None:
        return (), _digest({"invalid_publication_members": sorted(
            fallback,
            key=lambda item: (
                _text_key(item["global_track_id"]),
                _text_key(item["source_key"]),
                _text_key(item["opaque_member_track_token"]),
            ),
        )}), error
    digest_descriptors = sorted(
        descriptors,
        key=lambda item: (
            _text_key(item.source_key or ""),
            _text_key(item.member_token or ""),
            _text_key(item.track.global_track_id),
            _text_key(item.track_digest),
        )
    )
    base_digest = _digest(
        [
            {
                "track_digest": item.track_digest,
                "source_key": item.source_key,
                "opaque_member_track_token": item.member_token,
            }
            for item in digest_descriptors
        ]
    )
    return tuple(descriptors), base_digest, None


def _make_decision(
    envelope: _EvidenceEnvelope,
    *,
    reason: str | None,
    overlays: tuple[ExperimentalCentroidMemberOverlayV1, ...],
    centroid_nis: float | None,
    shape_mismatch_m2: float | None,
    base_publication_revision: str,
    base_publication_digest: str,
    prototype_config_digest: str,
    overlay_valid_for_publication_id: str,
) -> ExperimentalCentroidPublicationDecisionV1:
    decision = "rejected" if reason is not None else "accepted"
    if reason is not None:
        overlays = ()
        centroid_nis = None
        shape_mismatch_m2 = None
    payload = {
        "schema_version": EXPERIMENTAL_CENTROID_PUBLICATION_DECISION_SCHEMA_VERSION,
        "prototype_status": EXPERIMENTAL_CENTROID_PUBLICATION_PROTOTYPE_STATUS,
        "decision": decision,
        "reject_reason": reason,
        "evidence_id": envelope.evidence_id,
        "component_id": envelope.component_id,
        "component_generation": envelope.generation,
        "publisher_node_id": envelope.publisher_node_id,
        "publisher_epoch": envelope.publisher_epoch,
        "sensor_id": envelope.sensor_id,
        "scan_id": envelope.scan_id,
        "measurement_timestamp": envelope.measurement_timestamp,
        "arrival_timestamp": envelope.arrival_timestamp,
        "state_valid_timestamp": envelope.state_valid_timestamp,
        "published_at": envelope.published_at,
        "base_publication_revision": base_publication_revision,
        "base_publication_digest": base_publication_digest,
        "evidence_summary_digest": envelope.summary_digest,
        "prototype_config_digest": prototype_config_digest,
        "state_semantics": EXPERIMENTAL_CENTROID_PUBLICATION_STATE_SEMANTICS,
        "overlay_valid_for_publication_id": overlay_valid_for_publication_id,
        "member_overlays": [item.to_dict() for item in overlays],
        "centroid_nis": centroid_nis,
        "shape_mismatch_m2": shape_mismatch_m2,
        "cross_covariance_available": False,
        "mutates_filter_history": False,
    }
    decision_id = _DECISION_ID_PREFIX + hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return ExperimentalCentroidPublicationDecisionV1(
        decision_id=decision_id,
        decision=decision,
        reject_reason=reason,
        evidence_id=envelope.evidence_id,
        component_id=envelope.component_id,
        component_generation=envelope.generation,
        publisher_node_id=envelope.publisher_node_id,
        publisher_epoch=envelope.publisher_epoch,
        sensor_id=envelope.sensor_id,
        scan_id=envelope.scan_id,
        measurement_timestamp=envelope.measurement_timestamp,
        arrival_timestamp=envelope.arrival_timestamp,
        state_valid_timestamp=envelope.state_valid_timestamp,
        published_at=envelope.published_at,
        base_publication_revision=base_publication_revision,
        base_publication_digest=base_publication_digest,
        evidence_summary_digest=envelope.summary_digest,
        prototype_config_digest=prototype_config_digest,
        overlay_valid_for_publication_id=overlay_valid_for_publication_id,
        member_overlays=overlays,
        centroid_nis=centroid_nis,
        shape_mismatch_m2=shape_mismatch_m2,
    )


def _decision_sort_key(
    decision: ExperimentalCentroidPublicationDecisionV1,
) -> tuple[Any, ...]:
    return (
        decision.published_at,
        decision.state_valid_timestamp,
        decision.measurement_timestamp,
        decision.arrival_timestamp,
        _text_key(decision.publisher_node_id),
        _text_key(decision.publisher_epoch),
        _text_key(decision.sensor_id),
        _text_key(decision.scan_id),
        _text_key(decision.component_id),
        decision.component_generation,
        _text_key(decision.evidence_id),
        _text_key(decision.evidence_summary_digest),
        _text_key(decision.decision_id),
    )


def _contains_forbidden_identity_metadata(value: object) -> bool:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower()
            if key not in _IDENTITY_ALLOWED_KEYS and (
                key in _IDENTITY_EXACT_KEYS
                or any(marker in key for marker in _IDENTITY_MARKERS)
            ):
                return True
            if _contains_forbidden_identity_metadata(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_identity_metadata(item) for item in value)
    return False


def _canonical_json_bytes(value: Any) -> bytes:
    normalized = _canonicalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, np.ndarray):
        return _canonicalize(value.tolist())
    if isinstance(value, np.generic):
        return _canonicalize(value.item())
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        if not np.isfinite(number):
            raise ValueError("canonical payload contains nonfinite input")
        return number
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key in sorted(value, key=lambda item: _text_key(str(item))):
            key = str(raw_key)
            if key in normalized:
                raise ValueError("canonical mapping has duplicate string keys")
            normalized[key] = _canonicalize(value[raw_key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonicalize(item) for item in value]
        return sorted(items, key=_canonical_json_bytes)
    raise TypeError(f"unsupported canonical payload type: {type(value).__name__}")


def _digest(value: Any) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _is_digest(value: object) -> bool:
    text = str(value)
    digest = text[len(_DIGEST_PREFIX) :] if text.startswith(_DIGEST_PREFIX) else ""
    return len(digest) == 64 and all(item in "0123456789abcdef" for item in digest)


def _text_key(value: str) -> bytes:
    return str(value).encode("utf-8")


def _safe_text(value: object) -> str:
    if isinstance(value, (str, Integral, Real)):
        return str(value)
    return f"<invalid:{type(value).__name__}>"


def _safe_int(value: object) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return result if result >= 0 else 0


def _safe_float(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if np.isfinite(result) else 0.0
