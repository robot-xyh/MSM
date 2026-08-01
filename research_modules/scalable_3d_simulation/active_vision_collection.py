"""Versioned main-runtime treatments for D5 active-vision data collection.

The treatments alter only truth-free camera availability and reconnaissance-cue
delivery.  They never select an action or write a training label; D5's existing
deterministic policy remains the sole teacher-action source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping


ACTIVE_VISION_OPERATIONAL_PROFILE_V1 = "operational_v1"
ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1 = "balanced_action_role_v1"
ACTIVE_VISION_COLLECTION_PROFILES = frozenset(
    {
        ACTIVE_VISION_OPERATIONAL_PROFILE_V1,
        ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1,
    }
)


@dataclass(frozen=True)
class ActiveVisionCollectionTreatment:
    """Frozen executor and cue-delivery treatment used by one episode."""

    profile_id: str
    recon_cue_loss_period_s: float | None
    recon_cue_loss_duration_s: float
    camera_slew_rate_deg_s: float
    camera_minimum_settle_s: float
    camera_maximum_settle_s: float
    camera_fov_transition_settle_s: float

    def __post_init__(self) -> None:
        profile_id = str(self.profile_id).strip().lower()
        if profile_id not in ACTIVE_VISION_COLLECTION_PROFILES:
            raise ValueError(f"unsupported active-vision collection profile: {profile_id}")
        object.__setattr__(self, "profile_id", profile_id)
        if self.recon_cue_loss_period_s is not None:
            period = float(self.recon_cue_loss_period_s)
            if not math.isfinite(period) or period <= 0.0:
                raise ValueError("recon cue-loss period must be finite and positive")
            object.__setattr__(self, "recon_cue_loss_period_s", period)
        for name in (
            "recon_cue_loss_duration_s",
            "camera_slew_rate_deg_s",
            "camera_minimum_settle_s",
            "camera_maximum_settle_s",
            "camera_fov_transition_settle_s",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        if self.camera_slew_rate_deg_s <= 0.0:
            raise ValueError("camera_slew_rate_deg_s must be positive")
        if self.camera_maximum_settle_s < self.camera_minimum_settle_s:
            raise ValueError("maximum camera settle time must cover the minimum")
        if self.recon_cue_loss_period_s is None:
            if self.recon_cue_loss_duration_s != 0.0:
                raise ValueError("cue-loss duration requires a cue-loss period")
        elif self.recon_cue_loss_duration_s >= self.recon_cue_loss_period_s:
            raise ValueError("cue-loss duration must be shorter than its period")

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(asdict(self))

    def recon_cue_suppressed(self, timestamp_s: float) -> bool:
        timestamp = float(timestamp_s)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("recon cue timestamp must be finite and non-negative")
        period = self.recon_cue_loss_period_s
        if period is None:
            return False
        return math.fmod(timestamp, period) < self.recon_cue_loss_duration_s

    def camera_settle_seconds(
        self,
        *,
        intent: str,
        yaw_delta_deg: float,
        pitch_delta_deg: float,
        fov_changed: bool,
    ) -> float:
        """Return a bounded actuator settling interval after an applied command."""

        if self.profile_id == ACTIVE_VISION_OPERATIONAL_PROFILE_V1:
            return 0.0
        if str(intent).strip().lower() == "hold":
            return 0.0
        angular_delta = max(abs(float(yaw_delta_deg)), abs(float(pitch_delta_deg)))
        if not math.isfinite(angular_delta):
            raise ValueError("camera angular delta must be finite")
        if angular_delta <= 1.0e-9 and not bool(fov_changed):
            return 0.0
        duration = angular_delta / self.camera_slew_rate_deg_s
        if fov_changed:
            duration = max(duration, self.camera_fov_transition_settle_s)
        return min(
            self.camera_maximum_settle_s,
            max(self.camera_minimum_settle_s, duration),
        )


_TREATMENTS = {
    ACTIVE_VISION_OPERATIONAL_PROFILE_V1: ActiveVisionCollectionTreatment(
        profile_id=ACTIVE_VISION_OPERATIONAL_PROFILE_V1,
        recon_cue_loss_period_s=None,
        recon_cue_loss_duration_s=0.0,
        camera_slew_rate_deg_s=80.0,
        camera_minimum_settle_s=0.0,
        camera_maximum_settle_s=0.0,
        camera_fov_transition_settle_s=0.0,
    ),
    ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1: ActiveVisionCollectionTreatment(
        profile_id=ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1,
        recon_cue_loss_period_s=1.0,
        recon_cue_loss_duration_s=0.45,
        camera_slew_rate_deg_s=80.0,
        camera_minimum_settle_s=0.12,
        camera_maximum_settle_s=0.30,
        camera_fov_transition_settle_s=0.15,
    ),
}


def resolve_active_vision_collection_treatment(
    profile_id: str,
) -> ActiveVisionCollectionTreatment:
    normalized = str(profile_id).strip().lower()
    try:
        return _TREATMENTS[normalized]
    except KeyError as exc:
        raise ValueError(
            f"unsupported active-vision collection profile: {normalized}"
        ) from exc


__all__ = [
    "ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1",
    "ACTIVE_VISION_COLLECTION_PROFILES",
    "ACTIVE_VISION_OPERATIONAL_PROFILE_V1",
    "ActiveVisionCollectionTreatment",
    "resolve_active_vision_collection_treatment",
]
