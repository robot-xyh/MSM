from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

from .online_anonymization import assert_online_observations_identity_free
from .types import SensorObservation


SCAN_INPUT_CONFIG_SCHEMA_VERSION = "d1.scan_input.config.v1"
SCAN_INPUT_FRAME_SCHEMA_VERSION = "d1.scan_input.frame.v1"
SCAN_INPUT_AUDIT_EVENT_SCHEMA_VERSION = "d1.scan_input.audit_event.v1"
SCAN_INPUT_AUDIT_SUMMARY_SCHEMA_VERSION = "d1.scan_input.audit_summary.v1"
SCAN_INPUT_RESULT_SCHEMA_VERSION = "d1.scan_input.result.v1"
SCAN_INPUT_EXECUTION_CONFIG_SCHEMA_VERSION = "d1.scan_input.execution_config.v1"
SCAN_INPUT_PERFORMANCE_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.scan_input.performance_diagnostics.v2"
)
SCAN_INPUT_REFERENCE_IMPLEMENTATION = "reference_v1"
SCAN_INPUT_CANDIDATE_IMPLEMENTATION = "candidate_v2"
_SCAN_INPUT_IMPLEMENTATIONS = frozenset(
    {
        SCAN_INPUT_REFERENCE_IMPLEMENTATION,
        SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    }
)

_TIME_EPSILON_S = 1.0e-9
_SCAN_ID_METADATA_KEYS = ("scan_id", "online_batch_id")
_CONTENT_EXCLUDED_METADATA_KEYS = frozenset(
    {
        "arrival_timestamp",
        "online_batch_id",
        "received_timestamp",
        "relay_node_id",
        "scan_id",
        "sent_timestamp",
        "target_node_id",
    }
)


class ScanTimestampConflictError(ValueError):
    """Raised when one declared scan carries inconsistent timestamp identity."""


class DuplicateScanLineageError(ValueError):
    """Raised when one scan repeats an immutable observation lineage."""


@dataclass(frozen=True)
class ScanInputConfig:
    """Deterministic event-time and memory limits for scan input ordering."""

    max_lateness_s: float = 0.5
    max_buffer_residence_s: float = 5.0
    max_buffered_scans: int = 1_024
    max_buffered_observations: int = 200_000
    max_claimed_scans: int = 100_000
    max_claimed_observation_lineages: int = 2_000_000
    schema_version: str = SCAN_INPUT_CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCAN_INPUT_CONFIG_SCHEMA_VERSION:
            raise ValueError(f"unsupported scan input config schema: {self.schema_version!r}")
        for name in ("max_lateness_s", "max_buffer_residence_s"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        for name in (
            "max_buffered_scans",
            "max_buffered_observations",
            "max_claimed_scans",
            "max_claimed_observation_lineages",
        ):
            value = int(getattr(self, name))
            if value < 1:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "max_lateness_s": self.max_lateness_s,
            "max_buffer_residence_s": self.max_buffer_residence_s,
            "max_buffered_scans": self.max_buffered_scans,
            "max_buffered_observations": self.max_buffered_observations,
            "max_claimed_scans": self.max_claimed_scans,
            "max_claimed_observation_lineages": (
                self.max_claimed_observation_lineages
            ),
        }


@dataclass(frozen=True)
class SensorScanFrame:
    """One atomic, identity-free observer scan on the common episode clock."""

    scan_id: str
    observations: tuple[SensorObservation, ...]
    schema_version: str = SCAN_INPUT_FRAME_SCHEMA_VERSION
    _snapshot_integrity: tuple[Any, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _source_lineage_keys: tuple[tuple[Any, ...], ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.schema_version != SCAN_INPUT_FRAME_SCHEMA_VERSION:
            raise ValueError(f"unsupported scan frame schema: {self.schema_version!r}")
        scan_id = str(self.scan_id).strip()
        if not scan_id:
            raise ValueError("scan_id must be non-empty")
        object.__setattr__(self, "scan_id", scan_id)
        observations = tuple(_snapshot_observation(item) for item in self.observations)
        if not observations:
            raise ValueError("a sensor scan frame must contain at least one observation")
        object.__setattr__(self, "observations", observations)

        # This validates covariance and recursively rejects online truth fields
        # before any source-lineage fallback is read.
        assert_online_observations_identity_free(observations)
        first = observations[0]
        if not _timestamps_are_valid(first):
            raise ScanTimestampConflictError(
                "scan arrival_timestamp must be finite and not precede measurement_timestamp"
            )

        observation_ids: set[str] = set()
        lineage_keys: set[tuple[Any, ...]] = set()
        ordered_lineage_keys: list[tuple[Any, ...]] = []
        for observation in observations:
            if not _timestamps_are_valid(observation):
                raise ScanTimestampConflictError(
                    "scan arrival_timestamp must be finite and not precede measurement_timestamp"
                )
            if observation.sensor_id != first.sensor_id:
                raise ValueError("scan observations must share sensor_id")
            if observation.modality != first.modality:
                raise ValueError("scan observations must share modality")
            if observation.frame_id != first.frame_id:
                raise ValueError("scan observations must share canonical frame_id")
            if not _same_time(
                observation.measurement_timestamp,
                first.measurement_timestamp,
            ):
                raise ScanTimestampConflictError(
                    "scan observations must share measurement_timestamp"
                )
            if not _same_time(observation.arrival_timestamp, first.arrival_timestamp):
                raise ScanTimestampConflictError(
                    "scan observations must share arrival_timestamp"
                )
            declared_scan_ids = {
                str(observation.metadata[key]).strip()
                for key in _SCAN_ID_METADATA_KEYS
                if observation.metadata.get(key) is not None
            }
            if declared_scan_ids and declared_scan_ids != {scan_id}:
                raise ScanTimestampConflictError(
                    "scan_id conflicts with observation scan metadata"
                )
            observation_id = str(observation.observation_id)
            if observation_id in observation_ids:
                raise DuplicateScanLineageError(
                    "scan contains a repeated observation_id"
                )
            observation_ids.add(observation_id)
            lineage_key = tuple(observation.source_lineage_key)
            if lineage_key in lineage_keys:
                raise DuplicateScanLineageError(
                    "scan contains a repeated source lineage"
                )
            lineage_keys.add(lineage_key)
            ordered_lineage_keys.append(lineage_key)

        source_namespaces = {_source_namespace(item) for item in observations}
        if len(source_namespaces) != 1:
            raise ValueError("scan observations must share source namespace")
        object.__setattr__(self, "_source_lineage_keys", tuple(ordered_lineage_keys))
        object.__setattr__(
            self,
            "_snapshot_integrity",
            _frame_snapshot_integrity(self),
        )

    @classmethod
    def from_observations(
        cls,
        observations: Iterable[SensorObservation],
        *,
        scan_id: str | None = None,
    ) -> "SensorScanFrame":
        items = tuple(observations)
        if not items:
            raise ValueError("a sensor scan frame must contain at least one observation")
        declared = {
            str(item.metadata[key]).strip()
            for item in items
            for key in _SCAN_ID_METADATA_KEYS
            if item.metadata.get(key) is not None
        }
        if scan_id is None:
            if len(declared) != 1:
                raise ValueError(
                    "scan_id is required when observations do not declare one common scan ID"
                )
            scan_id = declared.pop()
        return cls(scan_id=str(scan_id), observations=items)

    @property
    def sensor_id(self) -> str:
        return str(self.observations[0].sensor_id)

    @property
    def modality(self) -> str:
        return str(self.observations[0].modality)

    @property
    def frame_id(self) -> str:
        return str(self.observations[0].frame_id)

    @property
    def measurement_timestamp(self) -> float:
        return float(self.observations[0].measurement_timestamp)

    @property
    def arrival_timestamp(self) -> float:
        return float(self.observations[0].arrival_timestamp)

    @property
    def source_namespace(self) -> str:
        return _source_namespace(self.observations[0])

    @property
    def source_lineage_keys(self) -> tuple[tuple[Any, ...], ...]:
        return self._source_lineage_keys

    @property
    def scan_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.source_namespace,
            self.sensor_id,
            self.modality,
            self.frame_id,
            self.scan_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scan_id": self.scan_id,
            "sensor_id": self.sensor_id,
            "source_namespace": self.source_namespace,
            "modality": self.modality,
            "frame_id": self.frame_id,
            "working_frame": "ned",
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "observation_count": len(self.observations),
            "observation_ids": tuple(item.observation_id for item in self.observations),
            "source_lineage": tuple(
                _json_safe(item) for item in self.source_lineage_keys
            ),
            "covariance_shapes": tuple(
                tuple(np.asarray(item.covariance).shape) for item in self.observations
            ),
            "observations": tuple(
                _observation_to_dict(item) for item in self.observations
            ),
        }


@dataclass(frozen=True)
class ScanInputAuditEvent:
    """One immutable lifecycle or rejection event for a whole scan frame."""

    event_sequence: int
    outcome: str
    reason: str
    scan_id: str
    sensor_id: str | None
    modality: str | None
    measurement_timestamp: float | None
    arrival_timestamp: float | None
    observation_count: int
    received_sequence: int | None
    watermark_before: float | None
    watermark_after: float | None
    current_buffered_scan_count: int
    current_buffered_observation_count: int
    source_lineage_digest: str | None = None
    content_digest: str | None = None
    buffered: bool = False
    reordered: bool = False
    released: bool = False
    duplicate: bool = False
    replay: bool = False
    timestamp_conflict: bool = False
    too_late: bool = False
    buffer_overflow: bool = False
    buffer_expired: bool = False
    capacity_overflow: bool = False
    invalid_frame: bool = False
    schema_version: str = SCAN_INPUT_AUDIT_EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_sequence": self.event_sequence,
            "outcome": self.outcome,
            "reason": self.reason,
            "scan_id": self.scan_id,
            "sensor_id": self.sensor_id,
            "modality": self.modality,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "observation_count": self.observation_count,
            "received_sequence": self.received_sequence,
            "watermark_before": self.watermark_before,
            "watermark_after": self.watermark_after,
            "current_buffered_scan_count": self.current_buffered_scan_count,
            "current_buffered_observation_count": (
                self.current_buffered_observation_count
            ),
            "source_lineage_digest": self.source_lineage_digest,
            "content_digest": self.content_digest,
            "buffered": self.buffered,
            "reordered": self.reordered,
            "released": self.released,
            "duplicate": self.duplicate,
            "replay": self.replay,
            "timestamp_conflict": self.timestamp_conflict,
            "too_late": self.too_late,
            "buffer_overflow": self.buffer_overflow,
            "buffer_expired": self.buffer_expired,
            "capacity_overflow": self.capacity_overflow,
            "invalid_frame": self.invalid_frame,
        }


@dataclass(frozen=True)
class ScanInputAuditSummary:
    received_scan_count: int
    received_observation_count: int
    buffered_event_count: int
    reordered_scan_count: int
    released_scan_count: int
    released_observation_count: int
    rejected_scan_count: int
    rejected_observation_count: int
    duplicate_scan_count: int
    replay_scan_count: int
    timestamp_conflict_scan_count: int
    too_late_scan_count: int
    buffer_overflow_scan_count: int
    buffer_expired_scan_count: int
    capacity_overflow_scan_count: int
    invalid_frame_scan_count: int
    current_buffered_scan_count: int
    current_buffered_observation_count: int
    maximum_buffered_scan_count: int
    maximum_buffered_observation_count: int
    claimed_scan_count: int
    claimed_observation_lineage_count: int
    latest_arrival_timestamp: float | None
    maximum_seen_measurement_timestamp: float | None
    measurement_watermark: float | None
    closed: bool
    schema_version: str = SCAN_INPUT_AUDIT_SUMMARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ScanInputResult:
    released_scans: tuple[SensorScanFrame, ...]
    events: tuple[ScanInputAuditEvent, ...]
    audit: ScanInputAuditSummary
    schema_version: str = SCAN_INPUT_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "released_scans": tuple(item.to_dict() for item in self.released_scans),
            "events": tuple(item.to_dict() for item in self.events),
            "audit": self.audit.to_dict(),
        }


@dataclass(frozen=True)
class _ScanClaim:
    scan_key: tuple[str, str, str, str, str]
    lineage_digests: tuple[str, ...]
    source_lineage_digest: str
    content_digest: str
    frame_digest: str
    measurement_timestamp: float
    arrival_timestamp: float


@dataclass(frozen=True)
class _BufferedScan:
    frame: SensorScanFrame
    received_sequence: int
    source_lineage_digest: str
    content_digest: str
    frame_digest: str
    reordered_on_arrival: bool


class ScanInputOrganizer:
    """Bounded scan-level event-time organizer placed before D1 fusion.

    Scans are received in nondecreasing arrival order. Unique frames are held
    until their measurement time is strictly behind the event-time watermark
    ``max_seen_measurement_time - max_lateness_s``. Too-late or structurally
    conflicted frames are rejected atomically and never appear in
    ``released_scans``.

    Measurement and arrival timestamps must already use one common episode
    clock, and observations must already satisfy D1's canonical frame contract.
    This class does not estimate clock offsets or external frame transforms.

    This class only organizes scan input. It does not implement fixed-lag
    Kalman smoothing, state rollback, or measurement-history propagation.
    """

    def __init__(
        self,
        config: ScanInputConfig | None = None,
        *,
        implementation: str = SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    ) -> None:
        self.config = config or ScanInputConfig()
        selected_implementation = str(implementation).strip()
        if selected_implementation not in _SCAN_INPUT_IMPLEMENTATIONS:
            raise ValueError(
                "implementation must be one of "
                f"{sorted(_SCAN_INPUT_IMPLEMENTATIONS)!r}"
            )
        self.implementation = selected_implementation
        self._buffer: list[_BufferedScan] = []
        self._current_buffered_observation_count = 0
        self._scan_claims: dict[tuple[str, str, str, str, str], _ScanClaim] = {}
        self._lineage_claims: dict[str, _ScanClaim] = {}
        self._latest_arrival_timestamp: float | None = None
        self._maximum_seen_measurement_timestamp: float | None = None
        self._measurement_watermark: float | None = None
        self._closed = False
        self._event_sequence = 0
        self._received_sequence = 0

        self._received_scan_count = 0
        self._received_observation_count = 0
        self._buffered_event_count = 0
        self._reordered_scan_count = 0
        self._released_scan_count = 0
        self._released_observation_count = 0
        self._rejected_scan_count = 0
        self._rejected_observation_count = 0
        self._duplicate_scan_count = 0
        self._replay_scan_count = 0
        self._timestamp_conflict_scan_count = 0
        self._too_late_scan_count = 0
        self._buffer_overflow_scan_count = 0
        self._buffer_expired_scan_count = 0
        self._capacity_overflow_scan_count = 0
        self._invalid_frame_scan_count = 0
        self._maximum_buffered_scan_count = 0
        self._maximum_buffered_observation_count = 0
        self._validated_frame_reuse_count = 0
        self._mutated_frame_rebuild_count = 0
        self._iterable_frame_build_count = 0
        self._organizer_observation_snapshot_count = 0
        self._claim_build_count = 0
        self._claim_observation_count = 0
        self._cached_source_lineage_reuse_count = 0
        self._source_lineage_reconstruction_count = 0
        self._lineage_sort_key_construction_count = 0
        self._buffer_partition_pass_count = 0
        self._buffer_partition_item_visit_count = 0
        self._buffered_observation_count_cache_read_count = 0
        self._buffered_observation_count_rescan_count = 0
        self._buffered_observation_count_rescan_item_visit_count = 0

    def ingest(
        self,
        scan: SensorScanFrame | Iterable[SensorObservation],
        *,
        scan_id: str | None = None,
    ) -> ScanInputResult:
        """Receive one full scan and return only scans safe to pass downstream."""

        if isinstance(scan, SensorScanFrame):
            if scan_id is not None and str(scan_id) != scan.scan_id:
                raise ValueError("scan_id must not override a SensorScanFrame identity")
            if _frame_snapshot_is_intact(scan):
                # SensorScanFrame construction already creates an alias-free,
                # read-only observation snapshot and validates truth, covariance,
                # timestamps, frame identity, and lineage.
                self._validated_frame_reuse_count += 1
                return self._ingest_frame(scan)
            self._mutated_frame_rebuild_count += 1
            self._organizer_observation_snapshot_count += len(scan.observations)
            try:
                validated = SensorScanFrame(
                    scan_id=scan.scan_id,
                    observations=scan.observations,
                    schema_version=scan.schema_version,
                )
            except (ScanTimestampConflictError, DuplicateScanLineageError, ValueError) as exc:
                return self._reject_invalid_input(scan.observations, scan.scan_id, exc)
            return self._ingest_frame(validated)

        items = tuple(scan)
        self._iterable_frame_build_count += 1
        self._organizer_observation_snapshot_count += len(items)
        try:
            frame = SensorScanFrame.from_observations(items, scan_id=scan_id)
        except (ScanTimestampConflictError, DuplicateScanLineageError, ValueError) as exc:
            return self._reject_invalid_input(items, scan_id, exc)
        return self._ingest_frame(frame)

    def advance_arrival_time(self, arrival_timestamp: float) -> ScanInputResult:
        """Advance the arrival clock so buffered residence limits remain bounded."""

        if self._closed:
            raise RuntimeError("scan input organizer is closed")
        timestamp = float(arrival_timestamp)
        if not np.isfinite(timestamp):
            raise ValueError("arrival_timestamp must be finite")
        if (
            self._latest_arrival_timestamp is not None
            and timestamp < self._latest_arrival_timestamp - _TIME_EPSILON_S
        ):
            raise ValueError("arrival time must be nondecreasing")
        self._latest_arrival_timestamp = timestamp
        events = self._expire_buffer(timestamp)
        return self._result((), events)

    def close(self) -> ScanInputResult:
        """Close the stream and release the finite, still-valid tail in event order."""

        if self._closed:
            return self._result((), ())
        if self.implementation == SCAN_INPUT_CANDIDATE_IMPLEMENTATION:
            released, events = self._release_partitioned_scans(
                tuple(self._buffer),
                (),
                remaining_observation_count=0,
                reason="end_of_stream",
            )
        else:
            released, events = self._release_scans(
                tuple(self._buffer),
                "end_of_stream",
            )
        self._closed = True
        return self._result(released, events)

    def audit_summary(self) -> ScanInputAuditSummary:
        current_observations = self._buffered_observation_count()
        return ScanInputAuditSummary(
            received_scan_count=self._received_scan_count,
            received_observation_count=self._received_observation_count,
            buffered_event_count=self._buffered_event_count,
            reordered_scan_count=self._reordered_scan_count,
            released_scan_count=self._released_scan_count,
            released_observation_count=self._released_observation_count,
            rejected_scan_count=self._rejected_scan_count,
            rejected_observation_count=self._rejected_observation_count,
            duplicate_scan_count=self._duplicate_scan_count,
            replay_scan_count=self._replay_scan_count,
            timestamp_conflict_scan_count=self._timestamp_conflict_scan_count,
            too_late_scan_count=self._too_late_scan_count,
            buffer_overflow_scan_count=self._buffer_overflow_scan_count,
            buffer_expired_scan_count=self._buffer_expired_scan_count,
            capacity_overflow_scan_count=self._capacity_overflow_scan_count,
            invalid_frame_scan_count=self._invalid_frame_scan_count,
            current_buffered_scan_count=len(self._buffer),
            current_buffered_observation_count=current_observations,
            maximum_buffered_scan_count=self._maximum_buffered_scan_count,
            maximum_buffered_observation_count=(
                self._maximum_buffered_observation_count
            ),
            claimed_scan_count=len(self._scan_claims),
            claimed_observation_lineage_count=len(self._lineage_claims),
            latest_arrival_timestamp=self._latest_arrival_timestamp,
            maximum_seen_measurement_timestamp=(
                self._maximum_seen_measurement_timestamp
            ),
            measurement_watermark=self._measurement_watermark,
            closed=self._closed,
        )

    def performance_diagnostics(self) -> dict[str, int | str]:
        """Return bounded operation counts and the selected A/B implementation."""

        return {
            "schema_version": SCAN_INPUT_PERFORMANCE_DIAGNOSTICS_SCHEMA_VERSION,
            "implementation": self.implementation,
            "validated_frame_reuse_count": self._validated_frame_reuse_count,
            "mutated_frame_rebuild_count": self._mutated_frame_rebuild_count,
            "iterable_frame_build_count": self._iterable_frame_build_count,
            "organizer_observation_snapshot_count": (
                self._organizer_observation_snapshot_count
            ),
            "claim_build_count": self._claim_build_count,
            "claim_observation_count": self._claim_observation_count,
            "cached_source_lineage_reuse_count": (
                self._cached_source_lineage_reuse_count
            ),
            "source_lineage_reconstruction_count": (
                self._source_lineage_reconstruction_count
            ),
            "lineage_sort_key_construction_count": (
                self._lineage_sort_key_construction_count
            ),
            "buffer_partition_pass_count": self._buffer_partition_pass_count,
            "buffer_partition_item_visit_count": (
                self._buffer_partition_item_visit_count
            ),
            "buffered_observation_count_cache_read_count": (
                self._buffered_observation_count_cache_read_count
            ),
            "buffered_observation_count_rescan_count": (
                self._buffered_observation_count_rescan_count
            ),
            "buffered_observation_count_rescan_item_visit_count": (
                self._buffered_observation_count_rescan_item_visit_count
            ),
        }

    def execution_config(self) -> dict[str, Any]:
        """Return the non-semantic execution selection for main/D6 manifests."""

        return {
            "schema_version": SCAN_INPUT_EXECUTION_CONFIG_SCHEMA_VERSION,
            "implementation": self.implementation,
            "candidate_is_default": True,
            "reference_implementation": SCAN_INPUT_REFERENCE_IMPLEMENTATION,
            "candidate_implementation": SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
            "event_time_config": self.config.to_dict(),
        }

    def _ingest_frame(self, frame: SensorScanFrame) -> ScanInputResult:
        if self._closed:
            raise RuntimeError("scan input organizer is closed")
        self._received_sequence += 1
        received_sequence = self._received_sequence
        self._received_scan_count += 1
        self._received_observation_count += len(frame.observations)
        watermark_before = self._measurement_watermark

        if (
            self._latest_arrival_timestamp is not None
            and frame.arrival_timestamp
            < self._latest_arrival_timestamp - _TIME_EPSILON_S
        ):
            event = self._terminal_rejection_event(
                frame,
                received_sequence,
                reason="arrival_timestamp_regressed",
                watermark_before=watermark_before,
                timestamp_conflict=True,
            )
            return self._result((), (event,))

        self._latest_arrival_timestamp = frame.arrival_timestamp
        events = list(self._expire_buffer(frame.arrival_timestamp))
        claim = self._build_claim(frame)
        duplicate = False
        replay = False
        timestamp_conflict = False

        prior_scan_claim = self._scan_claims.get(frame.scan_key)
        overlapping_claims = {
            self._lineage_claims[lineage]
            for lineage in claim.lineage_digests
            if lineage in self._lineage_claims
        }
        if prior_scan_claim is not None:
            if claim.frame_digest == prior_scan_claim.frame_digest:
                duplicate = True
            elif claim.content_digest == prior_scan_claim.content_digest:
                replay = True
            else:
                timestamp_conflict = True
        elif overlapping_claims:
            if (
                len(overlapping_claims) == 1
                and next(iter(overlapping_claims)).source_lineage_digest
                == claim.source_lineage_digest
                and next(iter(overlapping_claims)).content_digest == claim.content_digest
            ):
                replay = True
            else:
                timestamp_conflict = True

        too_late = (
            watermark_before is not None
            and frame.measurement_timestamp
            < watermark_before - _TIME_EPSILON_S
        )
        if duplicate or replay or timestamp_conflict or too_late:
            if timestamp_conflict:
                reason = "timestamp_or_payload_conflict"
            elif replay:
                reason = "source_payload_replay"
            elif duplicate:
                reason = "duplicate_scan"
            else:
                reason = "measurement_time_before_watermark"
            events.append(
                self._terminal_rejection_event(
                    frame,
                    received_sequence,
                    reason=reason,
                    watermark_before=watermark_before,
                    source_lineage_digest=claim.source_lineage_digest,
                    content_digest=claim.content_digest,
                    duplicate=duplicate,
                    replay=replay,
                    timestamp_conflict=timestamp_conflict,
                    too_late=too_late,
                )
            )
            return self._result((), events)

        unique_lineage_count = sum(
            lineage not in self._lineage_claims for lineage in claim.lineage_digests
        )
        claim_capacity_exceeded = (
            len(self._scan_claims) + 1 > self.config.max_claimed_scans
            or len(self._lineage_claims) + unique_lineage_count
            > self.config.max_claimed_observation_lineages
        )
        if claim_capacity_exceeded:
            events.append(
                self._terminal_rejection_event(
                    frame,
                    received_sequence,
                    reason="claim_registry_capacity_exceeded",
                    watermark_before=watermark_before,
                    source_lineage_digest=claim.source_lineage_digest,
                    content_digest=claim.content_digest,
                    capacity_overflow=True,
                )
            )
            return self._result((), events)

        candidate_maximum = frame.measurement_timestamp
        if self._maximum_seen_measurement_timestamp is not None:
            candidate_maximum = max(
                candidate_maximum,
                self._maximum_seen_measurement_timestamp,
            )
        candidate_watermark = candidate_maximum - self.config.max_lateness_s
        if self.implementation == SCAN_INPUT_CANDIDATE_IMPLEMENTATION:
            ready, remaining, remaining_observation_count = self._partition_buffer(
                candidate_watermark
            )
        else:
            self._buffer_partition_pass_count += 1
            self._buffer_partition_item_visit_count += len(self._buffer)
            ready = ()
            remaining = tuple(
                item
                for item in self._buffer
                if not _strictly_before(
                    item.frame.measurement_timestamp,
                    candidate_watermark,
                )
            )
            remaining_observation_count = sum(
                len(item.frame.observations) for item in remaining
            )
        prospective_scan_count = len(remaining) + 1
        prospective_observation_count = (
            remaining_observation_count + len(frame.observations)
        )
        buffer_overflow = (
            prospective_scan_count > self.config.max_buffered_scans
            or prospective_observation_count > self.config.max_buffered_observations
        )
        if buffer_overflow:
            self._register_claim(claim)
            events.append(
                self._terminal_rejection_event(
                    frame,
                    received_sequence,
                    reason="buffer_capacity_exceeded",
                    watermark_before=watermark_before,
                    source_lineage_digest=claim.source_lineage_digest,
                    content_digest=claim.content_digest,
                    buffer_overflow=True,
                )
            )
            return self._result((), events)

        reordered = (
            self._maximum_seen_measurement_timestamp is not None
            and frame.measurement_timestamp
            < self._maximum_seen_measurement_timestamp - _TIME_EPSILON_S
        )
        buffered = _BufferedScan(
            frame=frame,
            received_sequence=received_sequence,
            source_lineage_digest=claim.source_lineage_digest,
            content_digest=claim.content_digest,
            frame_digest=claim.frame_digest,
            reordered_on_arrival=reordered,
        )
        self._register_claim(claim)
        self._maximum_seen_measurement_timestamp = candidate_maximum
        self._measurement_watermark = candidate_watermark

        # Release scans closed by the candidate watermark before admitting the
        # boundary frame. This keeps the physical buffer within the configured
        # count limits throughout the operation, not only after it returns.
        if self.implementation == SCAN_INPUT_CANDIDATE_IMPLEMENTATION:
            released, release_events = self._release_partitioned_scans(
                ready,
                remaining,
                remaining_observation_count=remaining_observation_count,
                reason="watermark_released",
            )
        else:
            self._buffer_partition_pass_count += 1
            self._buffer_partition_item_visit_count += len(self._buffer)
            ready = tuple(
                item
                for item in self._buffer
                if _strictly_before(
                    item.frame.measurement_timestamp,
                    self._measurement_watermark,
                )
            )
            released, release_events = self._release_scans(
                ready,
                "watermark_released",
            )
        events.extend(release_events)

        self._buffer.append(buffered)
        self._current_buffered_observation_count += len(frame.observations)
        self._buffered_event_count += 1
        if reordered:
            self._reordered_scan_count += 1
        self._update_maximum_buffer_counts()
        events.append(
            self._event_for_buffered(
                buffered,
                watermark_before=watermark_before,
            )
        )
        return self._result(released, events)

    def _reject_invalid_input(
        self,
        observations: tuple[Any, ...],
        scan_id: str | None,
        error: Exception,
    ) -> ScanInputResult:
        if self._closed:
            raise RuntimeError("scan input organizer is closed")
        self._received_sequence += 1
        self._received_scan_count += 1
        self._received_observation_count += len(observations)
        self._rejected_scan_count += 1
        self._rejected_observation_count += len(observations)
        timestamp_conflict = isinstance(error, ScanTimestampConflictError)
        duplicate = isinstance(error, DuplicateScanLineageError)
        if timestamp_conflict:
            self._timestamp_conflict_scan_count += 1
        if duplicate:
            self._duplicate_scan_count += 1
        self._invalid_frame_scan_count += 1
        self._event_sequence += 1
        event = ScanInputAuditEvent(
            event_sequence=self._event_sequence,
            outcome="rejected",
            reason=f"invalid_scan_frame:{type(error).__name__}",
            scan_id="unresolved" if scan_id is None else str(scan_id),
            sensor_id=None,
            modality=None,
            measurement_timestamp=None,
            arrival_timestamp=None,
            observation_count=len(observations),
            received_sequence=self._received_sequence,
            watermark_before=self._measurement_watermark,
            watermark_after=self._measurement_watermark,
            current_buffered_scan_count=len(self._buffer),
            current_buffered_observation_count=self._buffered_observation_count(),
            duplicate=duplicate,
            timestamp_conflict=timestamp_conflict,
            invalid_frame=True,
        )
        return self._result((), (event,))

    def _expire_buffer(self, arrival_timestamp: float) -> tuple[ScanInputAuditEvent, ...]:
        expired = tuple(
            item
            for item in self._buffer
            if arrival_timestamp - item.frame.arrival_timestamp
            > self.config.max_buffer_residence_s + _TIME_EPSILON_S
        )
        events: list[ScanInputAuditEvent] = []
        for item in expired:
            self._buffer.remove(item)
            self._current_buffered_observation_count -= len(
                item.frame.observations
            )
            events.append(
                self._terminal_rejection_event(
                    item.frame,
                    item.received_sequence,
                    reason="buffer_residence_limit_exceeded",
                    watermark_before=self._measurement_watermark,
                    source_lineage_digest=item.source_lineage_digest,
                    content_digest=item.content_digest,
                    buffer_expired=True,
                )
            )
        return tuple(events)

    def _release_scans(
        self,
        scans: tuple[_BufferedScan, ...],
        reason: str,
    ) -> tuple[tuple[SensorScanFrame, ...], tuple[ScanInputAuditEvent, ...]]:
        ordered = tuple(
            sorted(
                scans,
                key=lambda item: (
                    item.frame.measurement_timestamp,
                    item.received_sequence,
                ),
            )
        )
        for item in ordered:
            self._buffer.remove(item)
        self._current_buffered_observation_count -= sum(
            len(item.frame.observations) for item in ordered
        )
        return self._emit_released_scans(ordered, reason)

    def _release_partitioned_scans(
        self,
        ready: tuple[_BufferedScan, ...],
        remaining: tuple[_BufferedScan, ...],
        *,
        remaining_observation_count: int,
        reason: str,
    ) -> tuple[tuple[SensorScanFrame, ...], tuple[ScanInputAuditEvent, ...]]:
        ordered = tuple(
            sorted(
                ready,
                key=lambda item: (
                    item.frame.measurement_timestamp,
                    item.received_sequence,
                ),
            )
        )
        self._buffer = list(remaining)
        self._current_buffered_observation_count = int(
            remaining_observation_count
        )
        return self._emit_released_scans(ordered, reason)

    def _emit_released_scans(
        self,
        ordered: tuple[_BufferedScan, ...],
        reason: str,
    ) -> tuple[tuple[SensorScanFrame, ...], tuple[ScanInputAuditEvent, ...]]:
        released: list[SensorScanFrame] = []
        events: list[ScanInputAuditEvent] = []
        for item in ordered:
            self._released_scan_count += 1
            self._released_observation_count += len(item.frame.observations)
            self._event_sequence += 1
            events.append(
                ScanInputAuditEvent(
                    event_sequence=self._event_sequence,
                    outcome="released",
                    reason=reason,
                    scan_id=item.frame.scan_id,
                    sensor_id=item.frame.sensor_id,
                    modality=item.frame.modality,
                    measurement_timestamp=item.frame.measurement_timestamp,
                    arrival_timestamp=item.frame.arrival_timestamp,
                    observation_count=len(item.frame.observations),
                    received_sequence=item.received_sequence,
                    watermark_before=self._measurement_watermark,
                    watermark_after=self._measurement_watermark,
                    current_buffered_scan_count=len(self._buffer),
                    current_buffered_observation_count=(
                        self._buffered_observation_count()
                    ),
                    source_lineage_digest=item.source_lineage_digest,
                    content_digest=item.content_digest,
                    released=True,
                )
            )
            released.append(item.frame)
        return tuple(released), tuple(events)

    def _event_for_buffered(
        self,
        item: _BufferedScan,
        *,
        watermark_before: float | None,
    ) -> ScanInputAuditEvent:
        self._event_sequence += 1
        return ScanInputAuditEvent(
            event_sequence=self._event_sequence,
            outcome="buffered",
            reason=(
                "within_lateness_window_reordered"
                if item.reordered_on_arrival
                else "within_lateness_window"
            ),
            scan_id=item.frame.scan_id,
            sensor_id=item.frame.sensor_id,
            modality=item.frame.modality,
            measurement_timestamp=item.frame.measurement_timestamp,
            arrival_timestamp=item.frame.arrival_timestamp,
            observation_count=len(item.frame.observations),
            received_sequence=item.received_sequence,
            watermark_before=watermark_before,
            watermark_after=self._measurement_watermark,
            current_buffered_scan_count=len(self._buffer),
            current_buffered_observation_count=self._buffered_observation_count(),
            source_lineage_digest=item.source_lineage_digest,
            content_digest=item.content_digest,
            buffered=True,
            reordered=item.reordered_on_arrival,
        )

    def _terminal_rejection_event(
        self,
        frame: SensorScanFrame,
        received_sequence: int,
        *,
        reason: str,
        watermark_before: float | None,
        source_lineage_digest: str | None = None,
        content_digest: str | None = None,
        duplicate: bool = False,
        replay: bool = False,
        timestamp_conflict: bool = False,
        too_late: bool = False,
        buffer_overflow: bool = False,
        buffer_expired: bool = False,
        capacity_overflow: bool = False,
    ) -> ScanInputAuditEvent:
        self._rejected_scan_count += 1
        self._rejected_observation_count += len(frame.observations)
        self._duplicate_scan_count += int(duplicate)
        self._replay_scan_count += int(replay)
        self._timestamp_conflict_scan_count += int(timestamp_conflict)
        self._too_late_scan_count += int(too_late)
        self._buffer_overflow_scan_count += int(buffer_overflow)
        self._buffer_expired_scan_count += int(buffer_expired)
        self._capacity_overflow_scan_count += int(capacity_overflow)
        self._event_sequence += 1
        return ScanInputAuditEvent(
            event_sequence=self._event_sequence,
            outcome="rejected",
            reason=reason,
            scan_id=frame.scan_id,
            sensor_id=frame.sensor_id,
            modality=frame.modality,
            measurement_timestamp=frame.measurement_timestamp,
            arrival_timestamp=frame.arrival_timestamp,
            observation_count=len(frame.observations),
            received_sequence=received_sequence,
            watermark_before=watermark_before,
            watermark_after=self._measurement_watermark,
            current_buffered_scan_count=len(self._buffer),
            current_buffered_observation_count=self._buffered_observation_count(),
            source_lineage_digest=source_lineage_digest,
            content_digest=content_digest,
            duplicate=duplicate,
            replay=replay,
            timestamp_conflict=timestamp_conflict,
            too_late=too_late,
            buffer_overflow=buffer_overflow,
            buffer_expired=buffer_expired,
            capacity_overflow=capacity_overflow,
        )

    def _register_claim(self, claim: _ScanClaim) -> None:
        self._scan_claims[claim.scan_key] = claim
        for lineage in claim.lineage_digests:
            self._lineage_claims[lineage] = claim

    def _build_claim(self, frame: SensorScanFrame) -> _ScanClaim:
        """Build the immutable claim used by duplicate and replay governance."""

        observation_count = len(frame.observations)
        self._claim_build_count += 1
        self._claim_observation_count += observation_count
        if self.implementation == SCAN_INPUT_REFERENCE_IMPLEMENTATION:
            self._source_lineage_reconstruction_count += observation_count
            self._lineage_sort_key_construction_count += 2 * observation_count
            return _reference_claim_for_frame(frame)
        self._cached_source_lineage_reuse_count += observation_count
        self._lineage_sort_key_construction_count += observation_count
        return _claim_for_frame(frame)

    def _partition_buffer(
        self,
        watermark: float,
    ) -> tuple[
        tuple[_BufferedScan, ...],
        tuple[_BufferedScan, ...],
        int,
    ]:
        ready: list[_BufferedScan] = []
        remaining: list[_BufferedScan] = []
        remaining_observation_count = 0
        self._buffer_partition_pass_count += 1
        self._buffer_partition_item_visit_count += len(self._buffer)
        for item in self._buffer:
            if _strictly_before(item.frame.measurement_timestamp, watermark):
                ready.append(item)
            else:
                remaining.append(item)
                remaining_observation_count += len(item.frame.observations)
        return (
            tuple(ready),
            tuple(remaining),
            remaining_observation_count,
        )

    def _update_maximum_buffer_counts(self) -> None:
        self._maximum_buffered_scan_count = max(
            self._maximum_buffered_scan_count,
            len(self._buffer),
        )
        self._maximum_buffered_observation_count = max(
            self._maximum_buffered_observation_count,
            self._buffered_observation_count(),
        )

    def _buffered_observation_count(self) -> int:
        if self.implementation == SCAN_INPUT_CANDIDATE_IMPLEMENTATION:
            self._buffered_observation_count_cache_read_count += 1
            return self._current_buffered_observation_count
        self._buffered_observation_count_rescan_count += 1
        self._buffered_observation_count_rescan_item_visit_count += len(
            self._buffer
        )
        return sum(len(item.frame.observations) for item in self._buffer)

    def _result(
        self,
        released: Iterable[SensorScanFrame],
        events: Iterable[ScanInputAuditEvent],
    ) -> ScanInputResult:
        return ScanInputResult(
            released_scans=tuple(released),
            events=tuple(events),
            audit=self.audit_summary(),
        )


def _claim_for_frame(frame: SensorScanFrame) -> _ScanClaim:
    safe_lineages = tuple(_json_safe(item) for item in frame.source_lineage_keys)
    lineage_sort_keys = tuple(
        _canonical_json_safe(item) for item in safe_lineages
    )
    lineage_digests = tuple(
        _digest_canonical_json(item) for item in lineage_sort_keys
    )
    source_lineage_digest = _digest_json_safe(sorted(lineage_digests))
    decorated_records: list[
        tuple[str, dict[str, Any], dict[str, Any]]
    ] = []
    for observation, safe_lineage, lineage_sort_key in zip(
        frame.observations,
        safe_lineages,
        lineage_sort_keys,
    ):
        content_metadata = {
            str(key): value
            for key, value in observation.metadata.items()
            if str(key) not in _CONTENT_EXCLUDED_METADATA_KEYS
        }
        content_record = _json_safe(
            {
                "sensor_id": observation.sensor_id,
                "modality": observation.modality,
                "measurement_timestamp": observation.measurement_timestamp,
                "frame_id": observation.frame_id,
                "measurement": observation.measurement,
                "covariance": observation.covariance,
                "classification_hint": observation.classification_hint,
                "confidence": observation.confidence,
                "quality_flags": observation.quality_flags,
                "source_node_id": observation.source_node_id,
                "payload_kind": observation.payload_kind,
                "metadata": content_metadata,
            }
        )
        content_record["source_lineage"] = safe_lineage
        frame_only_record = _json_safe(
            {
                "observation_id": observation.observation_id,
                "arrival_timestamp": observation.arrival_timestamp,
                "target_node_id": observation.target_node_id,
                "relay_node_id": observation.relay_node_id,
                "sent_timestamp": observation.sent_timestamp,
                "received_timestamp": observation.received_timestamp,
                "scan_id": frame.scan_id,
            }
        )
        decorated_records.append(
            (
                lineage_sort_key,
                content_record,
                {
                    **content_record,
                    **frame_only_record,
                },
            )
        )
    decorated_records.sort(key=lambda item: item[0])
    content_records = [item[1] for item in decorated_records]
    frame_records = [item[2] for item in decorated_records]
    content_digest = _digest_json_safe(content_records)
    return _ScanClaim(
        scan_key=frame.scan_key,
        lineage_digests=lineage_digests,
        source_lineage_digest=source_lineage_digest,
        content_digest=content_digest,
        frame_digest=_digest_json_safe(frame_records),
        measurement_timestamp=frame.measurement_timestamp,
        arrival_timestamp=frame.arrival_timestamp,
    )


def _reference_claim_for_frame(frame: SensorScanFrame) -> _ScanClaim:
    """Frozen pre-task implementation for explicit semantic and timing A/B."""

    source_lineage_keys = tuple(
        tuple(item.source_lineage_key) for item in frame.observations
    )
    safe_lineages = tuple(
        _json_safe_reference(item) for item in source_lineage_keys
    )
    lineage_digests = tuple(
        _digest_json_safe(item) for item in safe_lineages
    )
    source_lineage_digest = _digest_json_safe(sorted(lineage_digests))
    content_records: list[dict[str, Any]] = []
    frame_records: list[dict[str, Any]] = []
    for observation, safe_lineage in zip(
        frame.observations,
        safe_lineages,
    ):
        content_metadata = {
            str(key): value
            for key, value in observation.metadata.items()
            if str(key) not in _CONTENT_EXCLUDED_METADATA_KEYS
        }
        content_record = _json_safe_reference(
            {
                "sensor_id": observation.sensor_id,
                "modality": observation.modality,
                "measurement_timestamp": observation.measurement_timestamp,
                "frame_id": observation.frame_id,
                "measurement": observation.measurement,
                "covariance": observation.covariance,
                "classification_hint": observation.classification_hint,
                "confidence": observation.confidence,
                "quality_flags": observation.quality_flags,
                "source_node_id": observation.source_node_id,
                "payload_kind": observation.payload_kind,
                "metadata": content_metadata,
            }
        )
        content_record["source_lineage"] = safe_lineage
        content_records.append(content_record)
        frame_only_record = _json_safe_reference(
            {
                "observation_id": observation.observation_id,
                "arrival_timestamp": observation.arrival_timestamp,
                "target_node_id": observation.target_node_id,
                "relay_node_id": observation.relay_node_id,
                "sent_timestamp": observation.sent_timestamp,
                "received_timestamp": observation.received_timestamp,
                "scan_id": frame.scan_id,
            }
        )
        frame_records.append(
            {
                **content_record,
                **frame_only_record,
            }
        )
    content_records.sort(key=_json_safe_record_lineage_sort_key)
    frame_records.sort(key=_json_safe_record_lineage_sort_key)
    content_digest = _digest_json_safe(content_records)
    return _ScanClaim(
        scan_key=frame.scan_key,
        lineage_digests=lineage_digests,
        source_lineage_digest=source_lineage_digest,
        content_digest=content_digest,
        frame_digest=_digest_json_safe(frame_records),
        measurement_timestamp=frame.measurement_timestamp,
        arrival_timestamp=frame.arrival_timestamp,
    )


def _frame_snapshot_integrity(frame: SensorScanFrame) -> tuple[Any, ...]:
    source_lineage_keys = frame.source_lineage_keys
    return (
        frame.scan_id,
        frame.schema_version,
        id(frame.observations),
        id(source_lineage_keys),
        source_lineage_keys,
        tuple(_observation_snapshot_integrity(item) for item in frame.observations),
    )


def _frame_snapshot_is_intact(frame: SensorScanFrame) -> bool:
    expected = getattr(frame, "_snapshot_integrity", None)
    try:
        return expected is not None and expected == _frame_snapshot_integrity(frame)
    except (AttributeError, TypeError, ValueError):
        return False


def _observation_snapshot_integrity(
    observation: SensorObservation,
) -> tuple[Any, ...]:
    covariance = observation.covariance
    return (
        id(observation),
        observation.observation_id,
        observation.sensor_id,
        observation.modality,
        observation.measurement_timestamp,
        observation.arrival_timestamp,
        observation.frame_id,
        _array_snapshot_integrity(observation.measurement),
        None if covariance is None else _array_snapshot_integrity(covariance),
        observation.classification_hint,
        observation.confidence,
        tuple(observation.quality_flags),
        id(observation.metadata),
        isinstance(observation.metadata, MappingProxyType),
        observation.source_node_id,
        observation.target_node_id,
        observation.relay_node_id,
        observation.link_type,
        observation.sent_timestamp,
        observation.received_timestamp,
        observation.payload_kind,
        observation.stale_after_s,
        id(observation.source_support),
        (
            observation.source_support is None
            or isinstance(observation.source_support, MappingProxyType)
        ),
        observation.timestamp_uncertainty_s,
    )


def _array_snapshot_integrity(value: np.ndarray) -> tuple[Any, ...]:
    array = np.asarray(value)
    return (
        id(value),
        tuple(array.shape),
        tuple(array.strides),
        array.dtype.str,
        bool(array.flags.writeable),
    )


def _snapshot_observation(observation: SensorObservation) -> SensorObservation:
    """Return an alias-free, read-only snapshot without pickling mappings."""

    if not isinstance(observation, SensorObservation):
        raise TypeError("scan observations must be SensorObservation instances")

    snapshot = SensorObservation(
        observation_id=observation.observation_id,
        sensor_id=observation.sensor_id,
        modality=observation.modality,
        measurement_timestamp=observation.measurement_timestamp,
        arrival_timestamp=observation.arrival_timestamp,
        frame_id=observation.frame_id,
        measurement=np.array(observation.measurement, dtype=float, copy=True),
        covariance=(
            None
            if observation.covariance is None
            else np.array(observation.covariance, dtype=float, copy=True)
        ),
        classification_hint=observation.classification_hint,
        confidence=observation.confidence,
        quality_flags=tuple(observation.quality_flags),
        # SensorObservation normalizes top-level communication fields during
        # construction. A shallow dict is sufficient here; the recursive,
        # alias-free freeze happens after that normalization.
        metadata=dict(observation.metadata),
        source_node_id=observation.source_node_id,
        target_node_id=observation.target_node_id,
        relay_node_id=observation.relay_node_id,
        link_type=observation.link_type,
        sent_timestamp=observation.sent_timestamp,
        received_timestamp=observation.received_timestamp,
        payload_kind=observation.payload_kind,
        stale_after_s=observation.stale_after_s,
        source_support=(
            None
            if observation.source_support is None
            else dict(observation.source_support)
        ),
        timestamp_uncertainty_s=observation.timestamp_uncertainty_s,
    )
    snapshot.measurement = _readonly_array_copy(snapshot.measurement)
    if snapshot.covariance is not None:
        snapshot.covariance = _readonly_array_copy(snapshot.covariance)
    snapshot.metadata = _freeze_snapshot_mapping(snapshot.metadata)
    if snapshot.source_support is not None:
        snapshot.source_support = MappingProxyType(
            {str(key): int(value) for key, value in snapshot.source_support.items()}
        )
    return snapshot


def _readonly_array_copy(value: Any) -> np.ndarray:
    result = np.array(value, dtype=float, copy=True)
    result.setflags(write=False)
    return result


def _freeze_snapshot_mapping(value: Mapping[Any, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _freeze_snapshot_value(item) for key, item in value.items()}
    )


def _freeze_snapshot_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_snapshot_mapping(value)
    if isinstance(value, np.ndarray):
        result = value.copy()
        result.setflags(write=False)
        return result
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                item.name: _freeze_snapshot_value(getattr(value, item.name))
                for item in fields(value)
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_snapshot_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_snapshot_value(item) for item in value)
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    raise TypeError(
        "scan metadata snapshot has unsupported type: "
        f"{type(value).__name__}"
    )


def _timestamps_are_valid(observation: SensorObservation) -> bool:
    measurement = float(observation.measurement_timestamp)
    arrival = float(observation.arrival_timestamp)
    return (
        np.isfinite(measurement)
        and np.isfinite(arrival)
        and arrival + _TIME_EPSILON_S >= measurement
    )


def _record_lineage_sort_key(record: Mapping[str, Any]) -> str:
    return json.dumps(
        _json_safe(record["source_lineage"]),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_safe_record_lineage_sort_key(record: Mapping[str, Any]) -> str:
    return json.dumps(
        record["source_lineage"],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _same_time(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= _TIME_EPSILON_S


def _strictly_before(left: float, right: float | None) -> bool:
    return right is not None and float(left) < float(right) - _TIME_EPSILON_S


def _source_namespace(observation: SensorObservation) -> str:
    return str(
        observation.source_node_id
        or observation.metadata.get("source_node_id")
        or observation.sensor_id
    )


def _digest(payload: Any) -> str:
    return _digest_json_safe(_json_safe(payload))


def _digest_json_safe(payload: Any) -> str:
    return _digest_canonical_json(_canonical_json_safe(payload))


def _canonical_json_safe(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest_canonical_json(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _observation_to_dict(observation: SensorObservation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "sensor_id": observation.sensor_id,
        "modality": observation.modality,
        "measurement_timestamp": observation.measurement_timestamp,
        "arrival_timestamp": observation.arrival_timestamp,
        "frame_id": observation.frame_id,
        "measurement": _json_safe(observation.measurement),
        "covariance": _json_safe(observation.covariance),
        "classification_hint": observation.classification_hint,
        "confidence": observation.confidence,
        "quality_flags": _json_safe(observation.quality_flags),
        "metadata": _json_safe(observation.metadata),
        "source_node_id": observation.source_node_id,
        "target_node_id": observation.target_node_id,
        "relay_node_id": observation.relay_node_id,
        "link_type": observation.link_type,
        "sent_timestamp": observation.sent_timestamp,
        "received_timestamp": observation.received_timestamp,
        "payload_kind": observation.payload_kind,
        "stale_after_s": observation.stale_after_s,
        "source_support": _json_safe(observation.source_support),
        "timestamp_uncertainty_s": observation.timestamp_uncertainty_s,
        "source_lineage": _json_safe(observation.source_lineage_key),
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("scan digest input contains non-finite float")
        return value
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, np.ndarray):
        if value.ndim > 0 and value.dtype.kind in {"b", "i", "u", "f"}:
            if value.dtype.kind == "f" and not bool(np.isfinite(value).all()):
                raise ValueError("scan digest input contains non-finite float")
            return value.tolist()
        return [_json_safe(item) for item in value.tolist()]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_safe(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe(item) for item in value), key=repr)
    raise TypeError(f"scan digest input has unsupported type: {type(value).__name__}")


def _json_safe_reference(value: Any) -> Any:
    """Frozen recursive ndarray conversion used only by the A/B reference."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("scan digest input contains non-finite float")
        return value
    if isinstance(value, np.generic):
        return _json_safe_reference(value.item())
    if isinstance(value, Enum):
        return _json_safe_reference(value.value)
    if isinstance(value, np.ndarray):
        return [_json_safe_reference(item) for item in value.tolist()]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_safe_reference(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_reference(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe_reference(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_json_safe_reference(item) for item in value),
            key=repr,
        )
    raise TypeError(f"scan digest input has unsupported type: {type(value).__name__}")
