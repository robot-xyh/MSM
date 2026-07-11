"""Center-owned registration of local tracks to canonical global track IDs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import count
from typing import Iterable, Mapping

import numpy as np
from scipy.optimize import linear_sum_assignment

from .cross_node_metrics import CrossNodeRegistryMetrics
from .cross_node_models import (
    BindingHistoryEvent,
    CanonicalTrackSnapshot,
    CorrelationStatus,
    CrossNodeAssociationResult,
    FusionAction,
    FusionDirective,
    PropagatedSourceTrack,
    RejectedSourceTrack,
    SourceTrackKey,
    SourceTrackSummary,
    TrackToTrackMatch,
)
from .models import govern_covariance


LARGE_TRACK_TO_TRACK_COST = 1.0e12


@dataclass(frozen=True, slots=True)
class CrossNodeAssignmentBatch:
    """One-source Hungarian result against the current canonical registry."""

    matches: tuple[TrackToTrackMatch, ...]
    unmatched_source_track_keys: tuple[SourceTrackKey, ...]
    cost_matrix: np.ndarray
    distance_matrix: np.ndarray


@dataclass(slots=True)
class CrossNodeTrackAssociator:
    """Covariance-aware track-to-track GNN/Hungarian associator."""

    gate_threshold: float = 16.812
    unknown_correlation_covariance_scale: float = 2.0
    continuity_bias: float = 4.0
    process_noise_acceleration: float = 1.0
    large_cost: float = LARGE_TRACK_TO_TRACK_COST

    def __post_init__(self) -> None:
        if self.gate_threshold <= 0.0:
            raise ValueError("gate_threshold must be positive")
        if self.unknown_correlation_covariance_scale < 1.0:
            raise ValueError(
                "unknown_correlation_covariance_scale must be at least 1"
            )
        if self.continuity_bias < 0.0:
            raise ValueError("continuity_bias must be non-negative")
        if self.process_noise_acceleration < 0.0:
            raise ValueError("process_noise_acceleration must be non-negative")

    def propagate_source_track(
        self,
        summary: SourceTrackSummary,
        fusion_timestamp: float,
    ) -> PropagatedSourceTrack:
        fusion_timestamp = float(fusion_timestamp)
        if fusion_timestamp < summary.measurement_timestamp:
            raise ValueError("fusion_timestamp cannot precede measurement_timestamp")
        state, covariance = _propagate_cv_state(
            summary.ned_state,
            summary.ned_covariance,
            fusion_timestamp - summary.measurement_timestamp,
            self.process_noise_acceleration,
        )
        return PropagatedSourceTrack(
            summary=summary,
            fusion_timestamp=fusion_timestamp,
            ned_state=state,
            ned_covariance=covariance,
        )

    def associate(
        self,
        canonical_tracks: Iterable[CanonicalTrackSnapshot],
        source_tracks: Iterable[PropagatedSourceTrack],
        *,
        authoritative_bindings: Mapping[SourceTrackKey, str] | None = None,
    ) -> CrossNodeAssignmentBatch:
        """Associate one source node's tracks to canonical tracks.

        A one-source batch enforces one-to-one assignment.  The registry calls
        this method once per source node, which permits one canonical target to
        bind one tracklet from each of many observers.
        """

        canonical_list = list(canonical_tracks)
        source_list = list(source_tracks)
        if len({item.summary.source_node_id for item in source_list}) > 1:
            raise ValueError("associate() accepts tracks from exactly one source node")
        bindings = dict(authoritative_bindings or {})
        shape = (len(canonical_list), len(source_list))
        costs = np.full(shape, self.large_cost, dtype=float)
        distances = np.full(shape, np.inf, dtype=float)

        for row, canonical in enumerate(canonical_list):
            for column, source in enumerate(source_list):
                distance = self._mahalanobis_squared(canonical, source)
                distances[row, column] = distance
                if distance > self.gate_threshold:
                    continue
                cost = distance
                if bindings.get(source.summary.source_key) == canonical.canonical_id:
                    cost = max(0.0, cost - self.continuity_bias)
                costs[row, column] = cost

        matches: list[TrackToTrackMatch] = []
        matched_columns: set[int] = set()
        if canonical_list and source_list:
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows, columns, strict=True):
                if costs[row, column] >= self.large_cost:
                    continue
                source_key = source_list[column].summary.source_key
                matches.append(
                    TrackToTrackMatch(
                        canonical_id=canonical_list[row].canonical_id,
                        source_track_key=source_key,
                        mahalanobis_squared=float(distances[row, column]),
                        assignment_cost=float(costs[row, column]),
                    )
                )
                matched_columns.add(int(column))

        return CrossNodeAssignmentBatch(
            matches=tuple(matches),
            unmatched_source_track_keys=tuple(
                item.summary.source_key
                for column, item in enumerate(source_list)
                if column not in matched_columns
            ),
            cost_matrix=costs,
            distance_matrix=distances,
        )

    def _mahalanobis_squared(
        self,
        canonical: CanonicalTrackSnapshot,
        source: PropagatedSourceTrack,
    ) -> float:
        residual = source.ned_state - canonical.ned_state
        summary = source.summary
        if summary.correlation_status == CorrelationStatus.EXACT_KNOWN_CORRELATION:
            cross_covariance = summary.known_cross_covariance
            if cross_covariance is None:
                raise ValueError("exact correlation requires cross covariance")
            difference_covariance = (
                canonical.ned_covariance
                + source.ned_covariance
                - cross_covariance
                - cross_covariance.T
            )
        elif summary.correlation_status == CorrelationStatus.UNKNOWN_CORRELATION:
            difference_covariance = self.unknown_correlation_covariance_scale * (
                canonical.ned_covariance + source.ned_covariance
            )
        else:
            return float("inf")
        governed, _ = govern_covariance(
            difference_covariance,
            (6, 6),
            "track-to-track difference covariance",
        )
        return float(residual.T @ np.linalg.pinv(governed) @ residual)


@dataclass(slots=True)
class _CanonicalEntry:
    canonical_id: str
    fusion_timestamp: float
    ned_state: np.ndarray
    ned_covariance: np.ndarray
    quality: float
    representative_source_key: SourceTrackKey
    bindings: dict[SourceTrackKey, SourceTrackSummary] = field(default_factory=dict)


@dataclass(slots=True)
class CrossNodeTrackRegistry:
    """Register many namespaced source tracklets under canonical target IDs."""

    associator: CrossNodeTrackAssociator = field(
        default_factory=CrossNodeTrackAssociator
    )
    canonical_id_prefix: str = "GT"
    metrics: CrossNodeRegistryMetrics = field(default_factory=CrossNodeRegistryMetrics)
    _id_counter: count = field(default_factory=lambda: count(1), init=False)
    _canonicals: dict[str, _CanonicalEntry] = field(default_factory=dict, init=False)
    _source_bindings: dict[SourceTrackKey, str] = field(
        default_factory=dict, init=False
    )
    _latest_source_tracks: dict[SourceTrackKey, SourceTrackSummary] = field(
        default_factory=dict, init=False
    )
    _seen_payloads: set[tuple[object, ...]] = field(default_factory=set, init=False)
    _seen_lineages: set[tuple[str, ...]] = field(default_factory=set, init=False)
    _history: list[BindingHistoryEvent] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.canonical_id_prefix = str(self.canonical_id_prefix).strip()
        if not self.canonical_id_prefix:
            raise ValueError("canonical_id_prefix must be non-empty")

    @property
    def binding_history(self) -> tuple[BindingHistoryEvent, ...]:
        return tuple(self._history)

    @property
    def source_bindings(self) -> dict[SourceTrackKey, str]:
        return dict(self._source_bindings)

    def process_batch(
        self,
        source_tracks: Iterable[SourceTrackSummary],
        *,
        fusion_timestamp: float,
    ) -> CrossNodeAssociationResult:
        """Register a truth-free batch at one common fusion epoch."""

        fusion_timestamp = float(fusion_timestamp)
        if not np.isfinite(fusion_timestamp):
            raise ValueError("fusion_timestamp must be finite")
        summaries = sorted(
            source_tracks,
            key=lambda item: (
                item.source_node_id,
                item.local_track_id,
                item.local_epoch,
                item.measurement_timestamp,
            ),
        )
        if any(item.arrival_timestamp > fusion_timestamp for item in summaries):
            raise ValueError("fusion_timestamp cannot precede a payload arrival")

        self._propagate_canonicals_to(fusion_timestamp)
        rejected: list[RejectedSourceTrack] = []
        accepted: list[SourceTrackSummary] = []
        batch_events: list[BindingHistoryEvent] = []
        directives: list[FusionDirective] = []
        matches: list[TrackToTrackMatch] = []
        created_ids: list[str] = []
        accepted_source_keys: set[SourceTrackKey] = set()

        for summary in summaries:
            rejection_reason = (
                "repeated_source_track_in_batch"
                if summary.source_key in accepted_source_keys
                else self._duplicate_rejection_reason(summary)
            )
            if rejection_reason is not None:
                rejection = RejectedSourceTrack(
                    source_track_key=summary.source_key,
                    payload_id=summary.payload_id,
                    reason=rejection_reason,
                )
                rejected.append(rejection)
                directive = FusionDirective(
                    canonical_id=self._source_bindings.get(summary.source_key),
                    source_track_key=summary.source_key,
                    action=FusionAction.REJECT_DUPLICATE_INFORMATION,
                    reason=rejection_reason,
                )
                directives.append(directive)
                event = BindingHistoryEvent(
                    fusion_timestamp=fusion_timestamp,
                    source_track_key=summary.source_key,
                    canonical_id=self._source_bindings.get(summary.source_key),
                    previous_canonical_id=self._source_bindings.get(summary.source_key),
                    event="rejected_duplicate",
                    reason=rejection_reason,
                )
                self._history.append(event)
                batch_events.append(event)
                self.metrics.record_duplicate_rejection()
                continue
            self._seen_payloads.add(summary.payload_fingerprint)
            self._seen_lineages.add(summary.lineage_fingerprint)
            accepted_source_keys.add(summary.source_key)
            self.metrics.record_accepted_payload(
                measurement_timestamp=summary.measurement_timestamp,
                arrival_timestamp=summary.arrival_timestamp,
                fusion_timestamp=fusion_timestamp,
            )
            accepted.append(summary)

        summaries_by_source: dict[str, list[SourceTrackSummary]] = defaultdict(list)
        for summary in accepted:
            summaries_by_source[summary.source_node_id].append(summary)

        for source_node_id in sorted(summaries_by_source):
            group = summaries_by_source[source_node_id]
            propagated_by_key = {
                summary.source_key: self.associator.propagate_source_track(
                    summary,
                    fusion_timestamp,
                )
                for summary in group
            }
            assignment = self.associator.associate(
                self._snapshots(fusion_timestamp),
                propagated_by_key.values(),
                authoritative_bindings=self._source_bindings,
            )
            match_by_key = {
                match.source_track_key: match for match in assignment.matches
            }

            for summary in group:
                propagated = propagated_by_key[summary.source_key]
                match = match_by_key.get(summary.source_key)
                if match is None:
                    canonical_id = self._create_canonical(propagated)
                    created_ids.append(canonical_id)
                    distance = None
                    reason = "no_existing_canonical_within_gate"
                else:
                    canonical_id = match.canonical_id
                    distance = match.mahalanobis_squared
                    reason = "hungarian_match_within_mahalanobis_gate"
                    matches.append(match)
                directive, event = self._bind(
                    summary,
                    propagated,
                    canonical_id,
                    fusion_timestamp=fusion_timestamp,
                    mahalanobis_squared=distance,
                    reason=reason,
                )
                directives.append(directive)
                batch_events.append(event)

        bindings = self._active_bindings()
        return CrossNodeAssociationResult(
            fusion_timestamp=fusion_timestamp,
            canonical_bindings=bindings,
            canonical_snapshots=self._snapshots(fusion_timestamp, active_only=True),
            matches=tuple(matches),
            created_canonical_ids=tuple(created_ids),
            rejected_source_tracks=tuple(rejected),
            fusion_directives=tuple(directives),
            history_events=tuple(batch_events),
            metrics=self.metrics.summary(),
        )

    def _duplicate_rejection_reason(
        self,
        summary: SourceTrackSummary,
    ) -> str | None:
        if summary.correlation_status == CorrelationStatus.DUPLICATE_INFORMATION:
            return "declared_duplicate_information"
        if summary.payload_fingerprint in self._seen_payloads:
            return "duplicate_payload"
        if summary.lineage_fingerprint in self._seen_lineages:
            return "duplicate_lineage"
        previous = self._latest_source_tracks.get(summary.source_key)
        if (
            previous is not None
            and summary.measurement_timestamp <= previous.measurement_timestamp
        ):
            return "stale_or_replayed_source_track"
        return None

    def _create_canonical(self, source: PropagatedSourceTrack) -> str:
        canonical_id = f"{self.canonical_id_prefix}-{next(self._id_counter):06d}"
        summary = source.summary
        self._canonicals[canonical_id] = _CanonicalEntry(
            canonical_id=canonical_id,
            fusion_timestamp=source.fusion_timestamp,
            ned_state=source.ned_state.copy(),
            ned_covariance=source.ned_covariance.copy(),
            quality=summary.quality,
            representative_source_key=summary.source_key,
        )
        return canonical_id

    def _bind(
        self,
        summary: SourceTrackSummary,
        propagated: PropagatedSourceTrack,
        canonical_id: str,
        *,
        fusion_timestamp: float,
        mahalanobis_squared: float | None,
        reason: str,
    ) -> tuple[FusionDirective, BindingHistoryEvent]:
        source_key = summary.source_key
        previous_canonical_id = self._source_bindings.get(source_key)
        entry = self._canonicals[canonical_id]
        reference_keys = tuple(
            sorted(key for key in entry.bindings if key != source_key)
        )

        if previous_canonical_id is not None and previous_canonical_id != canonical_id:
            previous_entry = self._canonicals.get(previous_canonical_id)
            if previous_entry is not None:
                previous_entry.bindings.pop(source_key, None)
            self.metrics.record_id_switch()
            event_name = "rebound"
        elif previous_canonical_id == canonical_id:
            event_name = "reaffirmed"
        elif entry.bindings:
            event_name = "bound"
        else:
            event_name = "created"

        self._source_bindings[source_key] = canonical_id
        self._latest_source_tracks[source_key] = summary
        entry.bindings[source_key] = summary
        if (
            entry.representative_source_key == source_key
            or summary.quality > entry.quality
        ):
            entry.ned_state = propagated.ned_state.copy()
            entry.ned_covariance = propagated.ned_covariance.copy()
            entry.fusion_timestamp = fusion_timestamp
            entry.quality = summary.quality
            entry.representative_source_key = source_key

        if not reference_keys:
            action = FusionAction.NO_FUSION_SINGLE_SOURCE
            directive_reason = "canonical_has_no_independent_peer_track"
        elif summary.correlation_status == CorrelationStatus.EXACT_KNOWN_CORRELATION:
            action = FusionAction.REQUEST_EXACT_CORRELATED_FUSION
            directive_reason = "cross_covariance_available; numerical fusion owned_by_D1"
        else:
            action = FusionAction.REQUEST_COVARIANCE_INTERSECTION
            directive_reason = "unknown_correlation; request conservative CI from D1"
        directive = FusionDirective(
            canonical_id=canonical_id,
            source_track_key=source_key,
            action=action,
            reason=directive_reason,
            reference_source_track_keys=reference_keys,
        )
        event = BindingHistoryEvent(
            fusion_timestamp=fusion_timestamp,
            source_track_key=source_key,
            canonical_id=canonical_id,
            previous_canonical_id=previous_canonical_id,
            event=event_name,
            reason=reason,
            mahalanobis_squared=mahalanobis_squared,
        )
        self._history.append(event)
        return directive, event

    def _propagate_canonicals_to(self, fusion_timestamp: float) -> None:
        for entry in self._canonicals.values():
            if fusion_timestamp < entry.fusion_timestamp:
                raise ValueError("registry fusion timestamps must be monotonic")
            entry.ned_state, entry.ned_covariance = _propagate_cv_state(
                entry.ned_state,
                entry.ned_covariance,
                fusion_timestamp - entry.fusion_timestamp,
                self.associator.process_noise_acceleration,
            )
            entry.fusion_timestamp = fusion_timestamp

    def _active_bindings(self) -> dict[str, tuple[SourceTrackKey, ...]]:
        return {
            canonical_id: tuple(sorted(entry.bindings))
            for canonical_id, entry in sorted(self._canonicals.items())
            if entry.bindings
        }

    def _snapshots(
        self,
        fusion_timestamp: float,
        *,
        active_only: bool = False,
    ) -> tuple[CanonicalTrackSnapshot, ...]:
        return tuple(
            CanonicalTrackSnapshot(
                canonical_id=canonical_id,
                fusion_timestamp=fusion_timestamp,
                ned_state=entry.ned_state.copy(),
                ned_covariance=entry.ned_covariance.copy(),
                quality=entry.quality,
                representative_source_key=entry.representative_source_key,
                source_track_keys=tuple(sorted(entry.bindings)),
            )
            for canonical_id, entry in sorted(self._canonicals.items())
            if entry.bindings or not active_only
        )


def _propagate_cv_state(
    state: np.ndarray,
    covariance: np.ndarray,
    delta_time: float,
    acceleration_noise: float,
) -> tuple[np.ndarray, np.ndarray]:
    transition = np.eye(6, dtype=float)
    transition[:3, 3:] = np.eye(3, dtype=float) * delta_time
    process_noise = np.zeros((6, 6), dtype=float)
    if delta_time > 0.0 and acceleration_noise > 0.0:
        q = acceleration_noise**2
        process_noise[:3, :3] = np.eye(3) * q * delta_time**4 / 4.0
        process_noise[:3, 3:] = np.eye(3) * q * delta_time**3 / 2.0
        process_noise[3:, :3] = process_noise[:3, 3:].T
        process_noise[3:, 3:] = np.eye(3) * q * delta_time**2
    propagated_state = transition @ state
    propagated_covariance = transition @ covariance @ transition.T + process_noise
    propagated_covariance, _ = govern_covariance(
        propagated_covariance,
        (6, 6),
        "propagated NED covariance",
    )
    return propagated_state, propagated_covariance
