from __future__ import annotations

import copy
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any

import numpy as np

from .covariance_contract import validate_online_sensor_observation
from .types import SOURCE_LINEAGE_METADATA_KEYS, SensorObservation


_DROP = object()
_STREAM_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_IDENTITY_KEY_COMPONENTS = {
    "actor",
    "identity",
    "instance",
    "mesh",
    "object",
    "segmentation",
    "truth",
}
_IDENTITY_KEYS = {
    "detection_id",
    "local_track_id",
    "target_id",
    "target_label",
    "target_name",
    "target_token",
}
_LINEAGE_KEYS = {key.lower() for key in SOURCE_LINEAGE_METADATA_KEYS}
_FRAME_INDEX_KEYS = (
    "airsim_frame_index",
    "frame_index",
    "sensor_frame_index",
    "camera_frame_index",
    "image_frame_index",
)


def anonymize_online_observations(
    observations: Iterable[SensorObservation],
    *,
    identity_tokens: Iterable[str] = (),
    stream_id: str = "online",
) -> list[SensorObservation]:
    """Return online-safe copies of scene-derived sensor observations.

    Identity tokens are taken from ``identity_tokens`` and inferred from
    identity-only metadata fields. Anonymous IDs are deterministic for a
    given input order, frame order, and ``stream_id``; they do not depend on
    actor, object, truth, or segmentation names.
    """

    items = _observation_list(observations)
    tokens = _normalize_identity_tokens(identity_tokens)
    tokens.update(_collect_identity_tokens(items))
    stream = _validated_stream_id(stream_id, tokens)

    frame_ordinals: dict[Any, int] = {}
    frame_observation_counts: defaultdict[int, int] = defaultdict(int)
    frame_lineage_ordinals: defaultdict[int, dict[Any, int]] = defaultdict(dict)
    anonymized: list[SensorObservation] = []

    for observation in items:
        frame_key = _frame_key(observation)
        frame_ordinal = frame_ordinals.setdefault(frame_key, len(frame_ordinals) + 1)
        frame_observation_counts[frame_ordinal] += 1
        observation_ordinal = frame_observation_counts[frame_ordinal]

        raw_lineage = _hashable(observation.source_lineage_key)
        lineage_ordinals = frame_lineage_ordinals[frame_ordinal]
        lineage_ordinal = lineage_ordinals.setdefault(raw_lineage, len(lineage_ordinals) + 1)

        observation_id = (
            f"{stream}-frame-{frame_ordinal:08d}-obs-{observation_ordinal:04d}"
        )
        lineage_id = f"{stream}-frame-{frame_ordinal:08d}-source-{lineage_ordinal:04d}"
        metadata = _sanitize_metadata(observation.metadata, tokens)
        metadata["source_lineage_key"] = (
            "explicit",
            "anonymous_online_source",
            stream,
            f"frame-{frame_ordinal:08d}",
            f"source-{lineage_ordinal:04d}",
        )
        metadata["lineage_id"] = lineage_id

        classification_hint = _sanitize_text(observation.classification_hint, tokens)
        quality_flags = tuple(
            sanitized
            for flag in observation.quality_flags
            if (sanitized := _sanitize_text(str(flag), tokens)) is not None
        )
        source_support = _sanitize_value(observation.source_support, tokens)
        if source_support is _DROP:
            source_support = None

        anonymized.append(
            SensorObservation(
                observation_id=observation_id,
                sensor_id=observation.sensor_id,
                modality=observation.modality,
                measurement_timestamp=observation.measurement_timestamp,
                arrival_timestamp=observation.arrival_timestamp,
                frame_id=observation.frame_id,
                measurement=observation.measurement.copy(),
                covariance=(
                    None if observation.covariance is None else observation.covariance.copy()
                ),
                classification_hint=classification_hint,
                confidence=observation.confidence,
                quality_flags=quality_flags,
                metadata=metadata,
                source_node_id=observation.source_node_id,
                target_node_id=observation.target_node_id,
                relay_node_id=observation.relay_node_id,
                link_type=observation.link_type,
                sent_timestamp=observation.sent_timestamp,
                received_timestamp=observation.received_timestamp,
                payload_kind=observation.payload_kind,
                stale_after_s=observation.stale_after_s,
                source_support=source_support,
                timestamp_uncertainty_s=observation.timestamp_uncertainty_s,
            )
        )

    assert_online_observations_identity_free(anonymized, identity_tokens=tokens)
    return anonymized


def assert_online_observations_identity_free(
    observations: Iterable[SensorObservation],
    *,
    identity_tokens: Iterable[str] = (),
) -> None:
    """Raise ``ValueError`` when an online observation exposes identity truth."""

    items = _observation_list(observations)
    tokens = _normalize_identity_tokens(identity_tokens)
    tokens.update(_collect_identity_tokens(items))
    exposures: list[str] = []

    for index, observation in enumerate(items):
        validate_online_sensor_observation(
            observation,
            context=f"D1 online observations[{index}]",
        )
        payload = {
            "observation_id": observation.observation_id,
            "sensor_id": observation.sensor_id,
            "modality": observation.modality,
            "frame_id": observation.frame_id,
            "classification_hint": observation.classification_hint,
            "quality_flags": observation.quality_flags,
            "metadata": observation.metadata,
            "source_node_id": observation.source_node_id,
            "target_node_id": observation.target_node_id,
            "relay_node_id": observation.relay_node_id,
            "link_type": observation.link_type,
            "payload_kind": observation.payload_kind,
            "source_support": observation.source_support,
        }
        _find_identity_exposures(payload, tokens, f"observations[{index}]", exposures)

    if exposures:
        details = "; ".join(exposures[:8])
        if len(exposures) > 8:
            details += f"; and {len(exposures) - 8} more"
        raise ValueError(f"online SensorObservation identity exposure: {details}")


def _observation_list(observations: Iterable[SensorObservation]) -> list[SensorObservation]:
    items = list(observations)
    invalid = [index for index, item in enumerate(items) if not isinstance(item, SensorObservation)]
    if invalid:
        raise TypeError(
            "online observation APIs require SensorObservation instances; "
            f"invalid index(es): {invalid}"
        )
    return items


def _validated_stream_id(stream_id: str, tokens: set[str]) -> str:
    stream = str(stream_id).strip()
    if not _STREAM_ID_PATTERN.fullmatch(stream):
        raise ValueError(
            "stream_id must be 1..64 characters using letters, digits, '.', '_', or '-'"
        )
    matched = _matching_token(stream, tokens)
    if matched is not None:
        raise ValueError(f"stream_id contains identity token {matched!r}")
    return stream


def _frame_key(observation: SensorObservation) -> tuple[Any, ...]:
    for key in _FRAME_INDEX_KEYS:
        value = observation.metadata.get(key)
        if value is not None:
            return ("frame_index", key, _hashable(value))
    return ("measurement_timestamp", round(observation.measurement_timestamp, 12))


def _sanitize_metadata(metadata: Mapping[str, Any], tokens: set[str]) -> dict[str, Any]:
    sanitized = _sanitize_mapping(metadata, tokens, remove_lineage=True)
    return {} if sanitized is _DROP else sanitized


def _sanitize_mapping(
    value: Mapping[Any, Any],
    tokens: set[str],
    *,
    remove_lineage: bool = False,
) -> dict[str, Any] | object:
    sanitized: dict[str, Any] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        normalized = _normalized_key(key)
        if _is_identity_key(normalized) or _matching_token(key, tokens) is not None:
            continue
        if remove_lineage and normalized in _LINEAGE_KEYS:
            continue
        sanitized_item = _sanitize_value(item, tokens, remove_lineage=remove_lineage)
        if sanitized_item is not _DROP:
            sanitized[key] = sanitized_item
    return sanitized


def _sanitize_value(
    value: Any,
    tokens: set[str],
    *,
    remove_lineage: bool = False,
) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        sanitized = _sanitize_text(value, tokens)
        return _DROP if sanitized is None else sanitized
    if isinstance(value, bytes):
        sanitized = _sanitize_text(value.decode("utf-8", errors="replace"), tokens)
        return _DROP if sanitized is None else sanitized.encode("utf-8")
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, tokens, remove_lineage=remove_lineage)
    if isinstance(value, list):
        return [
            sanitized
            for item in value
            if (sanitized := _sanitize_value(item, tokens, remove_lineage=remove_lineage))
            is not _DROP
        ]
    if isinstance(value, tuple):
        return tuple(
            sanitized
            for item in value
            if (sanitized := _sanitize_value(item, tokens, remove_lineage=remove_lineage))
            is not _DROP
        )
    if isinstance(value, (set, frozenset)):
        sanitized = {
            item
            for raw_item in value
            if (item := _sanitize_value(raw_item, tokens, remove_lineage=remove_lineage))
            is not _DROP
        }
        return type(value)(sanitized)
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"O", "S", "U"} and _contains_identity_exposure(value, tokens):
            return _DROP
        return value.copy()
    if is_dataclass(value) and not isinstance(value, type):
        if _contains_identity_exposure(value, tokens):
            return _sanitize_mapping(
                {field.name: getattr(value, field.name) for field in fields(value)},
                tokens,
                remove_lineage=remove_lineage,
            )
        return copy.deepcopy(value)
    return copy.deepcopy(value)


def _sanitize_text(value: str | None, tokens: set[str]) -> str | None:
    if value is None:
        return None
    sanitized = str(value)
    for token in sorted(tokens, key=len, reverse=True):
        sanitized = re.sub(re.escape(token), "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"[ \t]+", " ", sanitized)
    sanitized = re.sub(r"([_:/|,;=\-])(?:[ \t]*\1)+", r"\1", sanitized)
    sanitized = sanitized.strip(" \t\r\n_:,/|;=-")
    return sanitized or None


def _normalize_identity_tokens(identity_tokens: Iterable[str]) -> set[str]:
    if isinstance(identity_tokens, bytes):
        identity_tokens = (identity_tokens.decode("utf-8", errors="replace"),)
    elif isinstance(identity_tokens, str):
        identity_tokens = (identity_tokens,)
    return {
        token
        for value in identity_tokens
        if (token := str(value).strip())
    }


def _collect_identity_tokens(observations: Iterable[SensorObservation]) -> set[str]:
    tokens: set[str] = set()

    def visit(value: Any, identity_context: bool = False) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                context = identity_context or _is_identity_key(_normalized_key(str(raw_key)))
                visit(item, context)
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                visit(item, identity_context)
            return
        if is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                context = identity_context or _is_identity_key(_normalized_key(field.name))
                visit(getattr(value, field.name), context)
            return
        if identity_context and isinstance(value, (str, bytes)):
            token = (
                value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
            ).strip()
            if token:
                tokens.add(token)

    for observation in observations:
        visit(observation.metadata)
    return tokens


def _find_identity_exposures(
    value: Any,
    tokens: set[str],
    path: str,
    exposures: list[str],
) -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = f"{path}.{key}"
            if _is_identity_key(_normalized_key(key)):
                exposures.append(f"identity key at {item_path}")
            matched = _matching_token(key, tokens)
            if matched is not None:
                exposures.append(f"identity token {matched!r} in key at {item_path}")
            _find_identity_exposures(item, tokens, item_path, exposures)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            _find_identity_exposures(item, tokens, f"{path}[{index}]", exposures)
        return
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"O", "S", "U"}:
            for index, item in enumerate(value.reshape(-1).tolist()):
                _find_identity_exposures(item, tokens, f"{path}[{index}]", exposures)
        return
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            field_path = f"{path}.{field.name}"
            if _is_identity_key(_normalized_key(field.name)):
                exposures.append(f"identity key at {field_path}")
            _find_identity_exposures(getattr(value, field.name), tokens, field_path, exposures)
        return
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        matched = _matching_token(value, tokens)
        if matched is not None:
            exposures.append(f"identity token {matched!r} in value at {path}")


def _contains_identity_exposure(value: Any, tokens: set[str]) -> bool:
    exposures: list[str] = []
    _find_identity_exposures(value, tokens, "value", exposures)
    return bool(exposures)


def _matching_token(value: str, tokens: set[str]) -> str | None:
    normalized = value.casefold()
    for token in sorted(tokens, key=len, reverse=True):
        if token.casefold() in normalized:
            return token
    return None


def _normalized_key(key: str) -> str:
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key.strip())
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _is_identity_key(normalized_key: str) -> bool:
    if normalized_key in _IDENTITY_KEYS or normalized_key.endswith("_offline_only"):
        return True
    components = set(normalized_key.split("_"))
    return bool(components & _IDENTITY_KEY_COMPONENTS)


def _hashable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return ("ndarray", value.shape, tuple(value.reshape(-1).tolist()))
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _hashable(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_hashable(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value
