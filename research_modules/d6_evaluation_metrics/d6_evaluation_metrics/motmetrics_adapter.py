"""Optional py-motmetrics benchmark over frozen offline association evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


OFFLINE_MOT_SCHEMA_VERSION = "msm-offline-mot-v1"


@dataclass(frozen=True)
class OfflineMOTFrame:
    """One offline-only frame accepted by the optional MOT evaluator.

    ``distance_matrix`` has shape ``len(truth_ids) x len(hypothesis_ids)``.
    Values are caller-defined distances; ``None`` forbids that association.
    """

    frame_id: int
    timestamp: float
    truth_ids: Sequence[str] = field(default_factory=tuple)
    hypothesis_ids: Sequence[str] = field(default_factory=tuple)
    distance_matrix: Sequence[Sequence[float | None]] = field(default_factory=tuple)
    evidence_available: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MOTMetricsResult:
    """Availability-aware result from the isolated py-motmetrics adapter."""

    status: str
    reason: str
    unavailable_reason: str | None = None
    backend: str = "py-motmetrics"
    backend_version: str | None = None
    schema_version: str = OFFLINE_MOT_SCHEMA_VERSION
    frame_count: int = 0
    idf1: float | None = None
    mota: float | None = None
    motp: float | None = None
    hota: float | None = None
    metric_availability: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_offline_mot_frames(path: str | Path) -> list[OfflineMOTFrame]:
    """Load the frozen offline truth/association JSON schema."""

    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("offline MOT fixture must be a JSON object")
    schema_version = str(raw.get("schema_version") or "")
    if schema_version != OFFLINE_MOT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported offline MOT schema {schema_version!r}; "
            f"expected {OFFLINE_MOT_SCHEMA_VERSION!r}"
        )
    if raw.get("online_use_forbidden") is not True:
        raise ValueError("offline MOT fixture must set online_use_forbidden=true")
    frames = raw.get("frames")
    if not isinstance(frames, list):
        raise ValueError("offline MOT fixture frames must be an array")
    result: list[OfflineMOTFrame] = []
    for index, payload in enumerate(frames):
        if not isinstance(payload, Mapping):
            raise ValueError(f"frame {index}: payload must be an object")
        frame = OfflineMOTFrame(
            frame_id=int(payload.get("frame_id", index)),
            timestamp=float(payload.get("timestamp", index)),
            truth_ids=tuple(str(item) for item in payload.get("truth_ids", ())),
            hypothesis_ids=tuple(
                str(item) for item in payload.get("hypothesis_ids", ())
            ),
            distance_matrix=tuple(
                tuple(value for value in row)
                for row in payload.get("distance_matrix", ())
            ),
            evidence_available=bool(payload.get("evidence_available", True)),
            metadata=dict(payload.get("metadata") or {}),
        )
        _validate_frame(frame, index=index)
        result.append(frame)
    return result


def evaluate_with_py_motmetrics(
    frames: Sequence[OfflineMOTFrame],
    *,
    motmetrics_module: Any | None = None,
) -> MOTMetricsResult:
    """Evaluate IDF1/MOTA/MOTP; HOTA is unavailable in motmetrics 1.4.0."""

    if not frames:
        return _unavailable("offline MOT frame evidence is absent")
    for index, frame in enumerate(frames):
        try:
            _validate_frame(frame, index=index)
        except (TypeError, ValueError) as exc:
            return _unavailable(f"invalid offline MOT evidence: {exc}", len(frames))
        if frame.evidence_available is False:
            return _unavailable(
                f"offline MOT evidence unavailable at frame {frame.frame_id}",
                len(frames),
            )

    backend = motmetrics_module
    if backend is None:
        try:
            backend = importlib.import_module("motmetrics")
        except (ImportError, ModuleNotFoundError) as exc:
            return _unavailable(
                f"optional dependency motmetrics is unavailable: {exc}",
                len(frames),
            )

    version = str(getattr(backend, "__version__", "unknown"))
    truth_id_map: dict[str, int] = {}
    hypothesis_id_map: dict[str, int] = {}
    accumulator = backend.MOTAccumulator(auto_id=False)
    try:
        for frame in sorted(frames, key=lambda item: (item.frame_id, item.timestamp)):
            truth_ids = _integer_ids(frame.truth_ids, truth_id_map)
            hypothesis_ids = _integer_ids(frame.hypothesis_ids, hypothesis_id_map)
            distances = [
                [math.nan if value is None else float(value) for value in row]
                for row in frame.distance_matrix
            ]
            accumulator.update(
                truth_ids,
                hypothesis_ids,
                distances,
                frameid=int(frame.frame_id),
            )
        summary = backend.metrics.create().compute(
            accumulator,
            metrics=["idf1", "mota", "motp"],
            name="episode",
        )
        values = {
            name: _summary_value(summary, name)
            for name in ("idf1", "mota", "motp")
        }
    except Exception as exc:  # pragma: no cover - backend/version specific
        return _unavailable(
            f"py-motmetrics evaluation failed: {type(exc).__name__}: {exc}",
            len(frames),
            backend_version=version,
        )

    availability = {
        name: {
            "status": "available" if values[name] is not None else "unavailable",
            "reason": (
                "computed by py-motmetrics"
                if values[name] is not None
                else "py-motmetrics returned no finite value"
            ),
        }
        for name in ("idf1", "mota", "motp")
    }
    availability["hota"] = {
        "status": "unavailable",
        "reason": "py-motmetrics 1.4.0 does not implement HOTA",
    }
    available = all(values[name] is not None for name in ("idf1", "mota", "motp"))
    return MOTMetricsResult(
        status="available" if available else "unavailable",
        reason=(
            "IDF1/MOTA/MOTP computed from frozen offline association evidence"
            if available
            else "one or more py-motmetrics outputs are unavailable"
        ),
        backend_version=version,
        frame_count=len(frames),
        idf1=values["idf1"],
        mota=values["mota"],
        motp=values["motp"],
        hota=None,
        metric_availability=availability,
        metadata={
            "offline_only": True,
            "online_use_forbidden": True,
            "truth_id_count": len(truth_id_map),
            "hypothesis_id_count": len(hypothesis_id_map),
        },
    )


def _validate_frame(frame: OfflineMOTFrame, *, index: int) -> None:
    if int(frame.frame_id) < 0:
        raise ValueError(f"frame {index}: frame_id must be non-negative")
    if len(set(frame.truth_ids)) != len(frame.truth_ids):
        raise ValueError(f"frame {index}: duplicate truth_ids")
    if len(set(frame.hypothesis_ids)) != len(frame.hypothesis_ids):
        raise ValueError(f"frame {index}: duplicate hypothesis_ids")
    if len(frame.distance_matrix) != len(frame.truth_ids):
        raise ValueError(f"frame {index}: distance_matrix truth dimension mismatch")
    for row in frame.distance_matrix:
        if len(row) != len(frame.hypothesis_ids):
            raise ValueError(
                f"frame {index}: distance_matrix hypothesis dimension mismatch"
            )
        for value in row:
            if value is None:
                continue
            parsed = float(value)
            if not math.isfinite(parsed) or parsed < 0.0:
                raise ValueError(
                    f"frame {index}: distances must be finite and non-negative"
                )


def _integer_ids(values: Sequence[str], mapping: dict[str, int]) -> list[int]:
    result: list[int] = []
    for value in values:
        text = str(value)
        if text not in mapping:
            mapping[text] = len(mapping) + 1
        result.append(mapping[text])
    return result


def _summary_value(summary: Any, metric: str) -> float | None:
    value: Any
    if isinstance(summary, Mapping):
        nested = summary.get("episode", summary)
        value = nested.get(metric) if isinstance(nested, Mapping) else None
    elif hasattr(summary, "loc"):
        value = summary.loc["episode", metric]
    else:
        value = None
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _unavailable(
    reason: str,
    frame_count: int = 0,
    *,
    backend_version: str | None = None,
) -> MOTMetricsResult:
    return MOTMetricsResult(
        status="unavailable",
        reason=reason,
        unavailable_reason=reason,
        backend_version=backend_version,
        frame_count=frame_count,
        metric_availability={
            name: {"status": "unavailable", "reason": reason}
            for name in ("idf1", "mota", "motp", "hota")
        },
        metadata={"offline_only": True, "online_use_forbidden": True},
    )
