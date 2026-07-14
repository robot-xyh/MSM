"""Object-class normalization for visual association costs.

Affiliation is deliberately outside this module. A detector label such as
``intruder`` is normalized only as an object-class alias for ``uav``; it does
not constitute hostile identity evidence.
"""

from __future__ import annotations

import re


_UNKNOWN_ALIASES = {"", "unknown", "unclassified", "unspecified"}
_UAV_ALIASES = {
    "drone",
    "intruder",
    "intruder_drone",
    "intruder_uav",
    "uas",
    "uav",
    "uav_drone",
    "uav_intruder",
    "unmanned_aerial_vehicle",
    "unmanned_aircraft_system",
}
_UAV_COMPACT_ALIASES = {alias.replace("_", "") for alias in _UAV_ALIASES}


def canonical_object_class(value: object) -> str:
    """Return a stable object class without inferring friend/hostile status."""

    text = "" if value is None else str(value).strip().casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if normalized in _UNKNOWN_ALIASES:
        return "unknown"
    if normalized in _UAV_ALIASES or normalized.replace("_", "") in _UAV_COMPACT_ALIASES:
        return "uav"
    return normalized or "unknown"


def object_classes_match(left: object, right: object) -> bool:
    """Compare object classes after normalization.

    Unknown handling remains the caller's policy because terminal association
    treats unknown as neutral while cross-view fusion applies a small penalty.
    """

    return canonical_object_class(left) == canonical_object_class(right)
