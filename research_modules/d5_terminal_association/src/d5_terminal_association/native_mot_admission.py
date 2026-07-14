"""Native ByteTrack/BoT-SORT admission metrics for continuous image streams.

The monitor consumes completed ``YoloMotFrameResult`` objects. Optional truth
records are inspected only after the online result exists, and identities are
retained only in private evaluator state for local-ID switch counting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .yolo_mot_adapter import YoloMotFrameResult


NATIVE_MOT_BACKENDS = frozenset({"bytetrack", "botsort"})
MOT_ADMISSION_CONFIDENCE_THRESHOLDS = (0.1, 0.2, 0.3)
MOT_ADMISSION_TARGET_DISTANCES_M = (20.0, 30.0, 50.0)
MOT_ADMISSION_STAGE_FRAME_COUNTS = {
    "single_camera_screening": 100,
    "two_camera_confirmation": 200,
}


@dataclass(frozen=True)
class NativeMotAdmissionCriteria:
    """Fail-closed thresholds for promoting a native MOT backend."""

    minimum_frame_count: int = 100
    minimum_native_active_frame_rate: float = 0.95
    maximum_fallback_frame_count: int = 0
    minimum_accepted_detection_count: int = 1
    maximum_p95_latency_ms: float = 100.0
    minimum_local_continuity: float = 0.90
    maximum_terminal_local_id_switch_count: int = 1
    minimum_detector_precision: float = 0.90
    minimum_detector_recall: float = 0.80

    def __post_init__(self) -> None:
        if self.minimum_frame_count < 1:
            raise ValueError("minimum_frame_count must be positive")
        for name in (
            "minimum_native_active_frame_rate",
            "minimum_local_continuity",
            "minimum_detector_precision",
            "minimum_detector_recall",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        if self.maximum_fallback_frame_count < 0:
            raise ValueError("maximum_fallback_frame_count must be non-negative")
        if self.minimum_accepted_detection_count < 0:
            raise ValueError("minimum_accepted_detection_count must be non-negative")
        if self.maximum_p95_latency_ms < 0.0:
            raise ValueError("maximum_p95_latency_ms must be non-negative")
        if self.maximum_terminal_local_id_switch_count < 0:
            raise ValueError("maximum_terminal_local_id_switch_count must be non-negative")


@dataclass(frozen=True)
class NativeMotScenarioMetadata:
    """Scenario dimensions used by the 20/30/50 m admission grid."""

    confidence_threshold: float
    target_distance_m: float
    warmup_frame_count: int = 5
    scenario_id: str | None = None
    evaluation_stage: str = "custom"
    expected_frame_count: int | None = None

    def __post_init__(self) -> None:
        confidence = float(self.confidence_threshold)
        distance = float(self.target_distance_m)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if not np.isfinite(distance) or distance <= 0.0:
            raise ValueError("target_distance_m must be positive and finite")
        if int(self.warmup_frame_count) < 0:
            raise ValueError("warmup_frame_count must be non-negative")
        stage = str(self.evaluation_stage).strip().lower()
        if stage not in {"custom", *MOT_ADMISSION_STAGE_FRAME_COUNTS}:
            raise ValueError("unsupported MOT admission evaluation_stage")
        expected_frame_count = self.expected_frame_count
        if expected_frame_count is None:
            expected_frame_count = MOT_ADMISSION_STAGE_FRAME_COUNTS.get(stage)
        if expected_frame_count is not None and int(expected_frame_count) < 1:
            raise ValueError("expected_frame_count must be positive when provided")
        object.__setattr__(self, "confidence_threshold", confidence)
        object.__setattr__(self, "target_distance_m", distance)
        object.__setattr__(self, "warmup_frame_count", int(self.warmup_frame_count))
        object.__setattr__(self, "scenario_id", _optional_text(self.scenario_id))
        object.__setattr__(self, "evaluation_stage", stage)
        object.__setattr__(
            self,
            "expected_frame_count",
            int(expected_frame_count) if expected_frame_count is not None else None,
        )

    @property
    def standard_grid_profile(self) -> bool:
        return (
            any(
                np.isclose(self.confidence_threshold, value)
                for value in MOT_ADMISSION_CONFIDENCE_THRESHOLDS
            )
            and any(
                np.isclose(self.target_distance_m, value)
                for value in MOT_ADMISSION_TARGET_DISTANCES_M
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "target_distance_m": self.target_distance_m,
            "warmup_frame_count": self.warmup_frame_count,
            "scenario_id": self.scenario_id,
            "evaluation_stage": self.evaluation_stage,
            "expected_frame_count": self.expected_frame_count,
            "standard_grid_profile": self.standard_grid_profile,
            "truth_scoring_policy": "evaluation_only_after_online_tracking",
        }


@dataclass(frozen=True)
class NativeMotAdmissionSummary:
    """Aggregated, truth-isolated admission result for one camera stream."""

    resource_id: str
    camera_id: str
    requested_tracker_backend: str
    scenario: NativeMotScenarioMetadata
    frame_count: int
    native_active_frame_count: int
    native_active_frame_rate: float
    fallback_frame_count: int
    online_detector_box_count: int
    accepted_detection_count: int
    warmup_excluded_latency_sample_count: int
    warmup_excluded_p95_latency_ms: float | None
    local_continuity: float | None
    terminal_local_id_switch_count: int
    offline_detector_true_positive_count: int
    offline_detector_false_positive_count: int
    offline_detector_false_negative_count: int
    offline_detector_precision: float | None
    offline_detector_recall: float | None
    offline_truth_frame_count: int
    post_online_truth_frame_count: int
    legacy_metadata_truth_frame_count: int
    offline_identity_scored_frame_count: int
    native_mot_admitted: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "camera_id": self.camera_id,
            "requested_tracker_backend": self.requested_tracker_backend,
            "tracker_backend": self.requested_tracker_backend,
            "scenario": self.scenario.to_dict(),
            "admission_stage": self.scenario.evaluation_stage,
            "required_frame_count": self.scenario.expected_frame_count,
            "confidence_threshold": self.scenario.confidence_threshold,
            "target_distance_m": self.scenario.target_distance_m,
            "frame_count": self.frame_count,
            "native_active_frame_count": self.native_active_frame_count,
            "native_active_frame_rate": self.native_active_frame_rate,
            "fallback_frame_count": self.fallback_frame_count,
            "online_detector_box_count": self.online_detector_box_count,
            "online_yolo_detection_count": self.online_detector_box_count,
            "accepted_detection_count": self.accepted_detection_count,
            "online_local_track_count": self.accepted_detection_count,
            "warmup_excluded_latency_sample_count": self.warmup_excluded_latency_sample_count,
            "warmup_excluded_p95_latency_ms": self.warmup_excluded_p95_latency_ms,
            "local_continuity": self.local_continuity,
            "local_track_continuity": self.local_continuity,
            "terminal_local_id_switch_count": self.terminal_local_id_switch_count,
            "offline_detector_true_positive_count": (
                self.offline_detector_true_positive_count
            ),
            "offline_detector_false_positive_count": (
                self.offline_detector_false_positive_count
            ),
            "offline_detector_false_negative_count": (
                self.offline_detector_false_negative_count
            ),
            "offline_detector_precision": self.offline_detector_precision,
            "offline_detector_recall": self.offline_detector_recall,
            "detector_precision": self.offline_detector_precision,
            "detector_recall": self.offline_detector_recall,
            "offline_reference_box_count": (
                self.offline_detector_true_positive_count
                + self.offline_detector_false_negative_count
            ),
            "offline_reference_matched_count": (
                self.offline_detector_true_positive_count
            ),
            "offline_reference_missed_count": (
                self.offline_detector_false_negative_count
            ),
            "offline_reference_unmatched_online_count": (
                self.offline_detector_false_positive_count
            ),
            "offline_truth_frame_count": self.offline_truth_frame_count,
            "post_online_truth_frame_count": self.post_online_truth_frame_count,
            "legacy_metadata_truth_frame_count": (
                self.legacy_metadata_truth_frame_count
            ),
            "offline_identity_scored_frame_count": self.offline_identity_scored_frame_count,
            "native_mot_admitted": self.native_mot_admitted,
            "rejection_reasons": list(self.rejection_reasons),
            "iou_fallback_counts_as_native": False,
            "truth_identity_used_online": False,
            "online_truth_use_count": 0,
            "global_track_id_rewrite_count": 0,
        }


@dataclass
class _StreamState:
    scenario: NativeMotScenarioMetadata
    requested_tracker_backend: str
    frame_count: int = 0
    native_active_frame_count: int = 0
    fallback_frame_count: int = 0
    online_detector_box_count: int = 0
    accepted_detection_count: int = 0
    post_warmup_latencies_ms: list[float] = field(default_factory=list)
    previous_local_ids: frozenset[str] = frozenset()
    continuity_match_count: int = 0
    continuity_opportunity_count: int = 0
    detector_true_positive_count: int = 0
    detector_false_positive_count: int = 0
    detector_false_negative_count: int = 0
    offline_truth_frame_count: int = 0
    post_online_truth_frame_count: int = 0
    legacy_metadata_truth_frame_count: int = 0
    offline_identity_scored_frame_count: int = 0
    terminal_local_id_switch_count: int = 0
    last_local_id_by_truth_id: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _OfflineTruthRecord:
    bbox: tuple[float, float, float, float]
    truth_id: str | None


@dataclass(frozen=True)
class OfflineDetectorFrameEvaluation:
    """Truth-isolated detector score computed after an online frame result."""

    detector_box_count: int
    truth_box_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    detector_precision: float | None
    detector_recall: float | None
    iou_threshold: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector_box_count": self.detector_box_count,
            "truth_box_count": self.truth_box_count,
            "true_positive_count": self.true_positive_count,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "detector_precision": self.detector_precision,
            "detector_recall": self.detector_recall,
            "iou_threshold": self.iou_threshold,
            "evaluation_phase": "after_online_result",
            "result_mutated": False,
            "truth_identity_emitted": False,
            "truth_identity_used_online": False,
        }


class NativeMotAdmissionMonitor:
    """Accumulate native MOT quality independently for every camera stream."""

    def __init__(self, criteria: NativeMotAdmissionCriteria | None = None) -> None:
        self.criteria = criteria or NativeMotAdmissionCriteria()
        self._streams: dict[tuple[str, str], _StreamState] = {}

    def observe(
        self,
        result: "YoloMotFrameResult",
        *,
        scenario: NativeMotScenarioMetadata,
        offline_truth_detections: Any | None = None,
        offline_evaluation_iou_threshold: float | None = None,
    ) -> None:
        """Record an already-completed online result, then score offline truth."""

        key = _stream_key(result.resource_id, result.camera_id)
        requested_backend = str(
            result.metadata.get("requested_tracker_backend", result.tracker_backend)
        ).lower()
        state = self._streams.get(key)
        if state is None:
            state = _StreamState(
                scenario=scenario,
                requested_tracker_backend=requested_backend,
            )
            self._streams[key] = state
        elif state.scenario != scenario or state.requested_tracker_backend != requested_backend:
            raise ValueError("MOT stream scenario/backend changed without reset_stream()")

        state.frame_count += 1
        selection = result.metadata.get("tracker_selection", {})
        native_active = (
            bool(selection.get("native_active", False))
            and result.tracker_backend in NATIVE_MOT_BACKENDS
        )
        fallback_active = (
            bool(selection.get("fallback_active", False))
            or result.tracker_backend == "iou_fallback"
        )
        state.native_active_frame_count += int(native_active)
        state.fallback_frame_count += int(fallback_active)
        state.online_detector_box_count += int(
            result.metadata.get(
                "detector_bbox_count",
                result.metadata.get("raw_detection_count", len(result.tracks)),
            )
        )
        state.accepted_detection_count += int(
            result.metadata.get("accepted_detection_count", len(result.tracks))
        )

        latency_ms = _optional_float(result.metadata.get("processing_latency_ms"))
        if state.frame_count > scenario.warmup_frame_count and latency_ms is not None:
            state.post_warmup_latencies_ms.append(latency_ms)

        current_ids = frozenset(track.local_track_id for track in result.tracks)
        if state.previous_local_ids and current_ids:
            state.continuity_opportunity_count += min(
                len(state.previous_local_ids), len(current_ids)
            )
            state.continuity_match_count += len(state.previous_local_ids & current_ids)
        state.previous_local_ids = current_ids

        detector_evaluation = result.metadata.get("offline_detector_evaluation")
        if offline_truth_detections is not None:
            post_online_evaluation = evaluate_offline_detector_after_online(
                result,
                offline_truth_detections,
                iou_threshold=offline_evaluation_iou_threshold,
            )
            state.offline_truth_frame_count += 1
            state.post_online_truth_frame_count += 1
            state.detector_true_positive_count += post_online_evaluation.true_positive_count
            state.detector_false_positive_count += post_online_evaluation.false_positive_count
            state.detector_false_negative_count += post_online_evaluation.false_negative_count
        elif isinstance(detector_evaluation, Mapping):
            state.offline_truth_frame_count += 1
            state.legacy_metadata_truth_frame_count += 1
            state.detector_true_positive_count += int(
                detector_evaluation.get("matched_truth_box_count", 0)
            )
            state.detector_false_positive_count += int(
                detector_evaluation.get("false_positive_count", 0)
            )
            state.detector_false_negative_count += int(
                detector_evaluation.get("false_negative_count", 0)
            )

        if offline_truth_detections is not None:
            truth_records = _offline_truth_records(offline_truth_detections)
            identity_records = tuple(
                record for record in truth_records if record.truth_id is not None
            )
            if identity_records:
                state.offline_identity_scored_frame_count += 1
                for track_index, truth_index in _match_tracks_to_truth(
                    result.tracks, identity_records
                ):
                    truth_id = identity_records[truth_index].truth_id
                    if truth_id is None:  # pragma: no cover
                        continue
                    local_id = result.tracks[track_index].local_track_id
                    previous_local_id = state.last_local_id_by_truth_id.get(truth_id)
                    if previous_local_id is not None and previous_local_id != local_id:
                        state.terminal_local_id_switch_count += 1
                    state.last_local_id_by_truth_id[truth_id] = local_id

    def summary(self, resource_id: str, camera_id: str) -> NativeMotAdmissionSummary:
        key = _stream_key(resource_id, camera_id)
        state = self._streams.get(key)
        if state is None:
            raise KeyError(f"MOT stream has no admission observations: {key[0]}/{key[1]}")
        return _summarize_state(key, state, self.criteria)

    def summaries(self) -> tuple[NativeMotAdmissionSummary, ...]:
        return tuple(
            _summarize_state(key, self._streams[key], self.criteria)
            for key in sorted(self._streams)
        )

    def reset_stream(self, resource_id: str, camera_id: str) -> None:
        self._streams.pop(_stream_key(resource_id, camera_id), None)

    def reset_all_streams(self) -> None:
        self._streams.clear()


def _summarize_state(
    key: tuple[str, str],
    state: _StreamState,
    criteria: NativeMotAdmissionCriteria,
) -> NativeMotAdmissionSummary:
    native_rate = (
        state.native_active_frame_count / state.frame_count if state.frame_count else 0.0
    )
    continuity = (
        state.continuity_match_count / state.continuity_opportunity_count
        if state.continuity_opportunity_count
        else None
    )
    p95_latency = (
        float(np.percentile(state.post_warmup_latencies_ms, 95))
        if state.post_warmup_latencies_ms
        else None
    )
    precision_denominator = (
        state.detector_true_positive_count + state.detector_false_positive_count
    )
    recall_denominator = (
        state.detector_true_positive_count + state.detector_false_negative_count
    )
    precision = (
        state.detector_true_positive_count / precision_denominator
        if precision_denominator
        else None
    )
    recall = (
        state.detector_true_positive_count / recall_denominator
        if recall_denominator
        else None
    )

    reasons: list[str] = []
    if state.requested_tracker_backend not in NATIVE_MOT_BACKENDS:
        reasons.append("native_backend_not_requested")
    required_frame_count = max(
        criteria.minimum_frame_count,
        state.scenario.expected_frame_count or 0,
    )
    if state.frame_count < required_frame_count:
        reasons.append("insufficient_frame_count")
    if native_rate < criteria.minimum_native_active_frame_rate:
        reasons.append("native_active_frame_rate_below_threshold")
    if state.fallback_frame_count > criteria.maximum_fallback_frame_count:
        reasons.append("iou_fallback_frame_present")
    if state.accepted_detection_count < criteria.minimum_accepted_detection_count:
        reasons.append("accepted_detection_count_below_threshold")
    if p95_latency is None:
        reasons.append("warmup_excluded_latency_unavailable")
    elif p95_latency > criteria.maximum_p95_latency_ms:
        reasons.append("warmup_excluded_p95_latency_exceeded")
    if continuity is None:
        reasons.append("local_continuity_unavailable")
    elif continuity < criteria.minimum_local_continuity:
        reasons.append("local_continuity_below_threshold")
    if state.offline_identity_scored_frame_count == 0:
        reasons.append("terminal_local_id_switch_metric_unavailable")
    elif (
        state.terminal_local_id_switch_count
        > criteria.maximum_terminal_local_id_switch_count
    ):
        reasons.append("terminal_local_id_switch_count_exceeded")
    if state.post_online_truth_frame_count < state.frame_count:
        reasons.append("post_online_truth_frame_coverage_incomplete")
    if state.legacy_metadata_truth_frame_count:
        reasons.append("legacy_truth_metadata_not_admissible")
    if precision is None:
        reasons.append("offline_detector_precision_unavailable")
    elif precision < criteria.minimum_detector_precision:
        reasons.append("offline_detector_precision_below_threshold")
    if recall is None:
        reasons.append("offline_detector_recall_unavailable")
    elif recall < criteria.minimum_detector_recall:
        reasons.append("offline_detector_recall_below_threshold")

    return NativeMotAdmissionSummary(
        resource_id=key[0],
        camera_id=key[1],
        requested_tracker_backend=state.requested_tracker_backend,
        scenario=state.scenario,
        frame_count=state.frame_count,
        native_active_frame_count=state.native_active_frame_count,
        native_active_frame_rate=native_rate,
        fallback_frame_count=state.fallback_frame_count,
        online_detector_box_count=state.online_detector_box_count,
        accepted_detection_count=state.accepted_detection_count,
        warmup_excluded_latency_sample_count=len(state.post_warmup_latencies_ms),
        warmup_excluded_p95_latency_ms=p95_latency,
        local_continuity=continuity,
        terminal_local_id_switch_count=state.terminal_local_id_switch_count,
        offline_detector_true_positive_count=state.detector_true_positive_count,
        offline_detector_false_positive_count=state.detector_false_positive_count,
        offline_detector_false_negative_count=state.detector_false_negative_count,
        offline_detector_precision=precision,
        offline_detector_recall=recall,
        offline_truth_frame_count=state.offline_truth_frame_count,
        post_online_truth_frame_count=state.post_online_truth_frame_count,
        legacy_metadata_truth_frame_count=state.legacy_metadata_truth_frame_count,
        offline_identity_scored_frame_count=state.offline_identity_scored_frame_count,
        native_mot_admitted=not reasons,
        rejection_reasons=tuple(reasons),
    )


def evaluate_offline_detector_after_online(
    result: "YoloMotFrameResult",
    offline_truth_detections: Any,
    *,
    iou_threshold: float | None = None,
) -> OfflineDetectorFrameEvaluation:
    """Score detector boxes after online processing without mutating ``result``."""

    threshold = (
        float(iou_threshold)
        if iou_threshold is not None
        else float(result.metadata.get("offline_evaluation_iou_threshold", 0.5))
    )
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("iou_threshold must be in [0, 1]")
    truth_records = _offline_truth_records(offline_truth_detections)
    detector_bboxes = _result_detector_bboxes(result)
    matches = _match_bboxes_to_truth(
        detector_bboxes,
        truth_records,
        iou_threshold=threshold,
    )
    true_positive_count = len(matches)
    detector_count = len(detector_bboxes)
    truth_count = len(truth_records)
    return OfflineDetectorFrameEvaluation(
        detector_box_count=detector_count,
        truth_box_count=truth_count,
        true_positive_count=true_positive_count,
        false_positive_count=max(0, detector_count - true_positive_count),
        false_negative_count=max(0, truth_count - true_positive_count),
        detector_precision=(
            true_positive_count / detector_count if detector_count else None
        ),
        detector_recall=(true_positive_count / truth_count if truth_count else None),
        iou_threshold=threshold,
    )


def _offline_truth_records(raw: Any) -> tuple[_OfflineTruthRecord, ...]:
    records: list[_OfflineTruthRecord] = []
    if isinstance(raw, Mapping):
        bbox_keys = ("bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")
        if "boxes" in raw and not any(key in raw for key in bbox_keys):
            return _offline_truth_records(raw["boxes"])
        records.append(
            _OfflineTruthRecord(
                bbox=_extract_bbox(raw),
                truth_id=_offline_truth_id(raw),
            )
        )
    elif isinstance(raw, np.ndarray):
        array = np.asarray(raw, dtype=float)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        for row in array:
            records.append(_OfflineTruthRecord(bbox=_bbox(row[:4]), truth_id=None))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        if _is_bbox(raw):
            records.append(_OfflineTruthRecord(bbox=_bbox(raw), truth_id=None))
        else:
            for item in raw:
                records.extend(_offline_truth_records(item))
    else:
        records.append(
            _OfflineTruthRecord(
                bbox=_extract_bbox(raw),
                truth_id=_offline_truth_id(raw),
            )
        )
    return tuple(records)


def _match_tracks_to_truth(
    tracks: Sequence[Any],
    truth_records: Sequence[_OfflineTruthRecord],
    *,
    iou_threshold: float = 0.5,
) -> tuple[tuple[int, int], ...]:
    return _match_bboxes_to_truth(
        tuple(tuple(track.bbox) for track in tracks),
        truth_records,
        iou_threshold=iou_threshold,
    )


def _match_bboxes_to_truth(
    detector_bboxes: Sequence[tuple[float, float, float, float]],
    truth_records: Sequence[_OfflineTruthRecord],
    *,
    iou_threshold: float,
) -> tuple[tuple[int, int], ...]:
    pairs = sorted(
        (
            (_bbox_iou(bbox, truth.bbox), detector_index, truth_index)
            for detector_index, bbox in enumerate(detector_bboxes)
            for truth_index, truth in enumerate(truth_records)
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_tracks: set[int] = set()
    used_truth: set[int] = set()
    matches: list[tuple[int, int]] = []
    for iou, track_index, truth_index in pairs:
        if iou < iou_threshold:
            break
        if track_index in used_tracks or truth_index in used_truth:
            continue
        used_tracks.add(track_index)
        used_truth.add(truth_index)
        matches.append((track_index, truth_index))
    return tuple(matches)


def _result_detector_bboxes(
    result: "YoloMotFrameResult",
) -> tuple[tuple[float, float, float, float], ...]:
    raw_bboxes = result.metadata.get("detector_bboxes_xyxy")
    if raw_bboxes is not None:
        if not isinstance(raw_bboxes, Sequence) or isinstance(
            raw_bboxes, (str, bytes, bytearray)
        ):
            raise ValueError("detector_bboxes_xyxy must be a sequence of xyxy boxes")
        return tuple(_bbox(value) for value in raw_bboxes)
    return tuple(_bbox(track.bbox) for track in result.tracks if track.bbox is not None)


def _offline_truth_id(value: Any) -> str | None:
    for name in (
        "truth_id",
        "true_global_track_id",
        "truth_global_track_id",
        "offline_truth_global_id",
        "object_id",
        "actor_id",
        "actor_name",
    ):
        candidate = (
            value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
        )
        text = _optional_text(candidate)
        if text is not None:
            return text
    return None


def _extract_bbox(value: Any) -> tuple[float, float, float, float]:
    names = ("bbox", "bbox_xyxy", "xyxy", "box", "box2d", "box2D")
    if isinstance(value, Mapping):
        raw = next((value[name] for name in names if name in value), None)
    else:
        raw = next(
            (
                getattr(value, name, None)
                for name in names
                if getattr(value, name, None) is not None
            ),
            None,
        )
    if raw is None:
        raise ValueError("offline truth detection must contain an xyxy bbox")
    if isinstance(raw, Mapping) and "min" in raw and "max" in raw:
        minimum, maximum = raw["min"], raw["max"]
        return _bbox(
            (
                _coordinate(minimum, "x"),
                _coordinate(minimum, "y"),
                _coordinate(maximum, "x"),
                _coordinate(maximum, "y"),
            )
        )
    return _bbox(raw)


def _coordinate(value: Any, axis: str) -> float:
    if isinstance(value, Mapping):
        return float(value[axis])
    return float(getattr(value, axis))


def _is_bbox(value: Sequence[Any]) -> bool:
    if len(value) != 4:
        return False
    try:
        return np.asarray(value, dtype=float).shape == (4,)
    except (TypeError, ValueError):
        return False


def _bbox(value: Iterable[Any]) -> tuple[float, float, float, float]:
    array = np.asarray(tuple(value), dtype=float).reshape(-1)
    if array.shape != (4,) or not np.all(np.isfinite(array)):
        raise ValueError("bbox must contain four finite xyxy values")
    x1, y1, x2, y2 = (float(item) for item in array)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox max coordinates must not be below min coordinates")
    return x1, y1, x2, y2


def _bbox_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _stream_key(resource_id: str, camera_id: str) -> tuple[str, str]:
    resource = str(resource_id).strip()
    camera = str(camera_id).strip()
    if not resource or not camera:
        raise ValueError("resource_id and camera_id must be non-empty")
    return resource, camera


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if np.isfinite(result) else None
