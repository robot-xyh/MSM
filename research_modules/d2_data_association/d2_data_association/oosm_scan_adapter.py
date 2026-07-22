"""Bounded whole-scan OOSM ordering in front of the monotonic D2 tracker."""

from __future__ import annotations

import heapq
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from .models import AssociationResult
from .scalable_3d_models import Detection3D, assert_online_metadata_truth_free
from .sparse_3d import Scalable3DTracker


OOSM_SCAN_ADAPTER_SCHEMA_VERSION = "d2-whole-scan-oosm-adapter-v1"


@dataclass(frozen=True, slots=True)
class OOSMScanAdapterConfig:
    """Versioned event-time ordering limits for whole common-epoch scans."""

    config_version: str = "d2-whole-scan-oosm-policy-v1"
    max_lateness_seconds: float = 1.0
    max_buffered_scans: int = 512
    timestamp_tolerance_seconds: float = 1.0e-9
    event_log_limit: int = 256

    def __post_init__(self) -> None:
        version = str(self.config_version).strip()
        if not version:
            raise ValueError("OOSM config_version must be non-empty")
        object.__setattr__(self, "config_version", version)
        for name in ("max_lateness_seconds", "timestamp_tolerance_seconds"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        for name in ("max_buffered_scans", "event_log_limit"):
            value = int(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OOSM_SCAN_ADAPTER_SCHEMA_VERSION,
            "config_version": self.config_version,
            "max_lateness_seconds": self.max_lateness_seconds,
            "max_buffered_scans": self.max_buffered_scans,
            "timestamp_tolerance_seconds": self.timestamp_tolerance_seconds,
            "event_log_limit": self.event_log_limit,
        }


@dataclass(frozen=True, slots=True)
class OOSMScanAdapterOutcome:
    """Admission result for one submitted scan or an end-of-stream flush."""

    admitted: bool
    released_results: tuple[AssociationResult, ...]
    events: tuple[dict[str, Any], ...]
    buffered_scan_count: int
    rejection_reason_counts_frame: dict[str, int]
    rejection_reason_counts_cumulative: dict[str, int]


@dataclass(frozen=True, slots=True)
class _BufferedScan:
    scan_id: str
    sequence: int
    measurement_timestamp: float
    arrival_timestamp: float
    detections: tuple[Detection3D, ...]
    measurement_order_inversion: bool


@dataclass(slots=True)
class Scalable3DOOSMScanAdapter:
    """Sort bounded-late scans before calling a monotonic tracker.

    The adapter never rewinds a track and never replays a released state.  It
    buffers complete common-epoch scans, releases them in non-decreasing
    measurement-time order, and rejects scans outside the configured event-time
    window.  ``flush()`` is an explicit end-of-stream drain, not fixed-lag
    smoothing.
    """

    tracker: Scalable3DTracker = field(default_factory=Scalable3DTracker)
    config: OOSMScanAdapterConfig = field(default_factory=OOSMScanAdapterConfig)
    _buffer: list[tuple[float, int, _BufferedScan]] = field(
        default_factory=list, init=False
    )
    _events: deque[dict[str, Any]] = field(init=False)
    _reason_counts: Counter[str] = field(default_factory=Counter, init=False)
    _next_sequence: int = field(default=1, init=False)
    _submitted_count: int = field(default=0, init=False)
    _admitted_count: int = field(default=0, init=False)
    _released_count: int = field(default=0, init=False)
    _rejected_count: int = field(default=0, init=False)
    _measurement_order_inversion_count: int = field(default=0, init=False)
    _peak_buffered_scan_count: int = field(default=0, init=False)
    _buffered_detection_count: int = field(default=0, init=False)
    _peak_buffered_detection_count: int = field(default=0, init=False)
    _latest_arrival_timestamp: float | None = field(default=None, init=False)
    _latest_submitted_measurement_timestamp: float | None = field(
        default=None, init=False
    )
    _release_watermark: float | None = field(default=None, init=False)
    _last_released_measurement_timestamp: float | None = field(
        default=None, init=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.tracker, Scalable3DTracker):
            raise TypeError("tracker must be Scalable3DTracker")
        if not isinstance(self.config, OOSMScanAdapterConfig):
            raise TypeError("config must be OOSMScanAdapterConfig")
        self._events = deque(maxlen=self.config.event_log_limit)
        self._last_released_measurement_timestamp = self.tracker.state_timestamp

    def submit_scan(
        self,
        detections: Iterable[Detection3D],
        *,
        measurement_timestamp: float | None = None,
        arrival_timestamp: float | None = None,
        scan_id: str | None = None,
    ) -> OOSMScanAdapterOutcome:
        """Admit one complete scan and release all scans below the watermark."""

        scan = self._build_scan(
            detections,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            scan_id=scan_id,
        )
        self._submitted_count += 1
        self._next_sequence += 1
        events: list[dict[str, Any]] = []

        if (
            self._latest_arrival_timestamp is not None
            and scan.arrival_timestamp + self.config.timestamp_tolerance_seconds
            < self._latest_arrival_timestamp
        ):
            events.append(self._reject(scan, "scan_arrival_order_regression"))
            return self._outcome(False, (), events)

        previous_submitted_measurement = self._latest_submitted_measurement_timestamp
        if (
            previous_submitted_measurement is None
            or scan.measurement_timestamp > previous_submitted_measurement
        ):
            self._latest_submitted_measurement_timestamp = scan.measurement_timestamp
        self._latest_arrival_timestamp = scan.arrival_timestamp
        self._release_watermark = (
            scan.arrival_timestamp - self.config.max_lateness_seconds
        )
        released = self._release_ready("event_time_watermark")

        lateness = scan.arrival_timestamp - scan.measurement_timestamp
        if (
            lateness
            > self.config.max_lateness_seconds
            + self.config.timestamp_tolerance_seconds
        ):
            events.append(self._reject(scan, "scan_max_lateness_exceeded"))
            return self._outcome(False, released, events)

        state_timestamp = self._last_released_measurement_timestamp
        if (
            state_timestamp is not None
            and scan.measurement_timestamp + self.config.timestamp_tolerance_seconds
            < state_timestamp
        ):
            events.append(self._reject(scan, "scan_older_than_released_state"))
            return self._outcome(False, released, events)

        if scan.measurement_order_inversion:
            self._measurement_order_inversion_count += 1

        if len(self._buffer) >= self.config.max_buffered_scans:
            if self._scan_is_ready(scan):
                self._admitted_count += 1
                direct_result = self._release_scan(scan, "event_time_watermark")
                return self._outcome(True, (*released, direct_result), events)
            events.append(self._reject(scan, "scan_buffer_overflow"))
            return self._outcome(False, released, events)

        heapq.heappush(
            self._buffer,
            (scan.measurement_timestamp, scan.sequence, scan),
        )
        self._buffered_detection_count += len(scan.detections)
        self._admitted_count += 1
        self._peak_buffered_scan_count = max(
            self._peak_buffered_scan_count,
            len(self._buffer),
        )
        self._peak_buffered_detection_count = max(
            self._peak_buffered_detection_count,
            self._buffered_detection_count,
        )
        released = (*released, *self._release_ready("event_time_watermark"))
        return self._outcome(True, released, events)

    def flush(self) -> OOSMScanAdapterOutcome:
        """Drain buffered scans in order after an explicit end-of-stream signal."""

        released: list[AssociationResult] = []
        while self._buffer:
            _, _, scan = heapq.heappop(self._buffer)
            self._buffered_detection_count -= len(scan.detections)
            released.append(self._release_scan(scan, "end_of_stream_flush"))
        return self._outcome(True, tuple(released), [])

    def summary(self) -> dict[str, Any]:
        return {
            **self.config.to_dict(),
            "submitted_scan_count": self._submitted_count,
            "admitted_scan_count": self._admitted_count,
            "released_scan_count": self._released_count,
            "rejected_scan_count": self._rejected_count,
            "buffered_scan_count": len(self._buffer),
            "peak_buffered_scan_count": self._peak_buffered_scan_count,
            "buffered_detection_count": self._buffered_detection_count,
            "peak_buffered_detection_count": (
                self._peak_buffered_detection_count
            ),
            "measurement_order_inversion_count": (
                self._measurement_order_inversion_count
            ),
            "rejection_reason_counts": dict(sorted(self._reason_counts.items())),
            "latest_arrival_timestamp": self._latest_arrival_timestamp,
            "release_watermark_measurement_timestamp": self._release_watermark,
            "last_released_measurement_timestamp": (
                self._last_released_measurement_timestamp
            ),
            "state_update_order": "non_decreasing_measurement_timestamp",
            "rewind_or_fixed_lag_smoothing": False,
            "online_truth_used": False,
            "events": list(self._events),
        }

    def _build_scan(
        self,
        detections: Iterable[Detection3D],
        *,
        measurement_timestamp: float | None,
        arrival_timestamp: float | None,
        scan_id: str | None,
    ) -> _BufferedScan:
        detection_list = tuple(detections)
        if not all(isinstance(item, Detection3D) for item in detection_list):
            raise TypeError("OOSM adapter accepts only Detection3D scans")
        for detection in detection_list:
            assert_online_metadata_truth_free(detection.metadata)
        detection_ids = [item.detection_id for item in detection_list]
        if len(set(detection_ids)) != len(detection_ids):
            raise ValueError("detection_id values must be unique within a scan")

        if measurement_timestamp is None:
            if not detection_list:
                raise ValueError("empty scans require measurement_timestamp")
            measurement_timestamp = detection_list[0].measurement_timestamp
        measurement_timestamp = _finite_non_negative_timestamp(
            measurement_timestamp,
            "measurement_timestamp",
        )
        if any(
            abs(item.measurement_timestamp - measurement_timestamp)
            > self.config.timestamp_tolerance_seconds
            for item in detection_list
        ):
            raise ValueError("one OOSM scan must share a measurement epoch")

        maximum_detection_arrival = (
            max(item.arrival_timestamp for item in detection_list)
            if detection_list
            else measurement_timestamp
        )
        if arrival_timestamp is None:
            arrival_timestamp = maximum_detection_arrival
        arrival_timestamp = _finite_non_negative_timestamp(
            arrival_timestamp,
            "arrival_timestamp",
        )
        if arrival_timestamp + self.config.timestamp_tolerance_seconds < max(
            measurement_timestamp,
            maximum_detection_arrival,
        ):
            raise ValueError(
                "scan arrival_timestamp cannot precede measurement or detection arrival"
            )

        scan_identifier = (
            f"scan-{self._next_sequence:08d}"
            if scan_id is None
            else str(scan_id).strip()
        )
        if not scan_identifier:
            raise ValueError("scan_id must be non-empty")
        inversion = bool(
            self._latest_submitted_measurement_timestamp is not None
            and measurement_timestamp + self.config.timestamp_tolerance_seconds
            < self._latest_submitted_measurement_timestamp
        )
        return _BufferedScan(
            scan_id=scan_identifier,
            sequence=self._next_sequence,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            detections=detection_list,
            measurement_order_inversion=inversion,
        )

    def _scan_is_ready(self, scan: _BufferedScan) -> bool:
        return bool(
            self._release_watermark is not None
            and scan.measurement_timestamp
            <= self._release_watermark + self.config.timestamp_tolerance_seconds
        )

    def _release_ready(self, release_mode: str) -> tuple[AssociationResult, ...]:
        released: list[AssociationResult] = []
        while self._buffer and self._scan_is_ready(self._buffer[0][2]):
            _, _, scan = heapq.heappop(self._buffer)
            self._buffered_detection_count -= len(scan.detections)
            released.append(self._release_scan(scan, release_mode))
        return tuple(released)

    def _release_scan(
        self,
        scan: _BufferedScan,
        release_mode: str,
    ) -> AssociationResult:
        previous = self._last_released_measurement_timestamp
        if (
            previous is not None
            and scan.measurement_timestamp + self.config.timestamp_tolerance_seconds
            < previous
        ):
            raise RuntimeError("OOSM adapter attempted a non-monotonic state update")
        result = self.tracker.step(
            scan.detections,
            timestamp=scan.measurement_timestamp,
        )
        self._last_released_measurement_timestamp = scan.measurement_timestamp
        self._released_count += 1
        result.metadata["oosm_scan_adapter"] = {
            **self.config.to_dict(),
            "scan_id": scan.scan_id,
            "measurement_timestamp": scan.measurement_timestamp,
            "arrival_timestamp": scan.arrival_timestamp,
            "measurement_order_inversion_buffered": (
                scan.measurement_order_inversion
            ),
            "release_mode": release_mode,
            "state_timestamp_before_release": previous,
            "state_timestamp_after_release": scan.measurement_timestamp,
            "rejection_reason_counts_frame": {},
            "rejection_reason_counts_cumulative": dict(
                sorted(self._reason_counts.items())
            ),
            "rewind_or_fixed_lag_smoothing": False,
            "online_truth_used": False,
        }
        event = {
            "scan_id": scan.scan_id,
            "measurement_timestamp": scan.measurement_timestamp,
            "arrival_timestamp": scan.arrival_timestamp,
            "status": "released",
            "reason": release_mode,
            "online_truth_used": False,
        }
        self._events.append(event)
        return result

    def _reject(self, scan: _BufferedScan, reason: str) -> dict[str, Any]:
        self._rejected_count += 1
        self._reason_counts[reason] += 1
        event = {
            "scan_id": scan.scan_id,
            "measurement_timestamp": scan.measurement_timestamp,
            "arrival_timestamp": scan.arrival_timestamp,
            "status": "rejected",
            "reason": reason,
            "release_watermark_measurement_timestamp": self._release_watermark,
            "tracker_state_timestamp": self._last_released_measurement_timestamp,
            "online_truth_used": False,
        }
        self._events.append(event)
        return event

    def _outcome(
        self,
        admitted: bool,
        released: Iterable[AssociationResult],
        events: Iterable[dict[str, Any]],
    ) -> OOSMScanAdapterOutcome:
        return OOSMScanAdapterOutcome(
            admitted=bool(admitted),
            released_results=tuple(released),
            events=tuple(dict(item) for item in events),
            buffered_scan_count=len(self._buffer),
            rejection_reason_counts_frame=dict(
                sorted(
                    Counter(
                        str(item["reason"])
                        for item in events
                        if item.get("status") == "rejected"
                    ).items()
                )
            ),
            rejection_reason_counts_cumulative=dict(
                sorted(self._reason_counts.items())
            ),
        )


def _finite_non_negative_timestamp(value: float, name: str) -> float:
    timestamp = float(value)
    if not np.isfinite(timestamp) or timestamp < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return timestamp
