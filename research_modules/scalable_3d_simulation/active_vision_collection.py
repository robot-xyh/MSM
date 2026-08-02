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

from .models import ScenarioConfig


ACTIVE_VISION_OPERATIONAL_PROFILE_V1 = "operational_v1"
ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1 = "balanced_action_role_v1"
ACTIVE_VISION_COLLECTION_PROFILES = frozenset(
    {
        ACTIVE_VISION_OPERATIONAL_PROFILE_V1,
        ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1,
    }
)

_WINDOW_INTENTS = frozenset(
    {"observe_target", "search_sector", "hold", "reacquire"}
)
_CAMERA_ROLES = frozenset({"interceptor", "recon"})


@dataclass(frozen=True)
class ActiveVisionIntentWindowTreatment:
    """One bounded truth-free input treatment from the frozen D5 schedule."""

    window_id: str
    start_s: float
    end_s: float
    intent: str
    camera_role: str
    treatment_recipe: str
    required_controls: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("window_id", "treatment_recipe"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"active-vision {name} must be non-empty")
            object.__setattr__(self, name, value)
        start = float(self.start_s)
        end = float(self.end_s)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0.0 or end <= start:
            raise ValueError("active-vision intent window must be finite and increasing")
        intent = str(self.intent).strip().lower()
        role = str(self.camera_role).strip().lower()
        if intent not in _WINDOW_INTENTS:
            raise ValueError("unsupported active-vision window intent")
        if role not in _CAMERA_ROLES:
            raise ValueError("unsupported active-vision camera role")
        controls = tuple(str(value).strip() for value in self.required_controls)
        if not controls or any(not value for value in controls) or len(controls) != len(
            set(controls)
        ):
            raise ValueError("active-vision required controls are invalid")
        object.__setattr__(self, "start_s", start)
        object.__setattr__(self, "end_s", end)
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "camera_role", role)
        object.__setattr__(self, "required_controls", controls)

    def contains(self, timestamp_s: float) -> bool:
        timestamp = float(timestamp_s)
        return self.start_s <= timestamp < self.end_s


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
    intent_windows: tuple[ActiveVisionIntentWindowTreatment, ...] = ()
    near_tie_window_ids: tuple[str, ...] = ()

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
        windows = tuple(self.intent_windows)
        if any(
            not isinstance(item, ActiveVisionIntentWindowTreatment)
            for item in windows
        ):
            raise TypeError(
                "intent_windows must contain ActiveVisionIntentWindowTreatment"
            )
        ordered = tuple(sorted(windows, key=lambda item: (item.start_s, item.window_id)))
        if windows != ordered:
            raise ValueError("active-vision intent windows must be time ordered")
        if any(
            ordered[index].end_s > ordered[index + 1].start_s + 1.0e-12
            for index in range(max(0, len(ordered) - 1))
        ):
            raise ValueError("active-vision intent windows must not overlap")
        near_tie_window_ids = tuple(
            str(value).strip() for value in self.near_tie_window_ids
        )
        if (
            any(not value for value in near_tie_window_ids)
            or len(near_tie_window_ids) != len(set(near_tie_window_ids))
            or not set(near_tie_window_ids).issubset(
                {item.window_id for item in windows}
            )
        ):
            raise ValueError("active-vision near-tie window inventory is invalid")
        object.__setattr__(self, "intent_windows", windows)
        object.__setattr__(self, "near_tie_window_ids", near_tie_window_ids)

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(asdict(self))

    def recon_cue_suppressed(self, timestamp_s: float) -> bool:
        timestamp = float(timestamp_s)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("recon cue timestamp must be finite and non-negative")
        if self.intent_windows:
            window = self.intent_window(timestamp, camera_role="recon")
            return window is not None and window.intent == "search_sector"
        period = self.recon_cue_loss_period_s
        if period is None:
            return False
        return math.fmod(timestamp, period) < self.recon_cue_loss_duration_s

    def intent_window(
        self,
        timestamp_s: float,
        *,
        camera_role: str,
    ) -> ActiveVisionIntentWindowTreatment | None:
        timestamp = float(timestamp_s)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("active-vision window timestamp must be finite and non-negative")
        role = str(camera_role).strip().lower()
        if role not in _CAMERA_ROLES:
            raise ValueError("unsupported active-vision camera role")
        return next(
            (
                item
                for item in self.intent_windows
                if item.camera_role == role and item.contains(timestamp)
            ),
            None,
        )

    def projection_mode(self, timestamp_s: float, *, camera_role: str) -> str:
        window = self.intent_window(timestamp_s, camera_role=camera_role)
        if window is None:
            return "natural"
        return {
            "observe_target": "stable_single",
            "search_sector": "suppressed",
            "hold": "retained",
            "reacquire": "outside_boundary_single",
        }[window.intent]

    def camera_forced_busy(self, timestamp_s: float, *, camera_role: str) -> bool:
        window = self.intent_window(timestamp_s, camera_role=camera_role)
        return window is not None and window.intent == "hold"

    def near_tie_candidates_required(
        self,
        timestamp_s: float,
        *,
        camera_role: str,
    ) -> bool:
        """Whether this frozen window requires two legal center-track projections."""

        window = self.intent_window(timestamp_s, camera_role=camera_role)
        return window is not None and window.window_id in self.near_tie_window_ids

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


def bind_active_vision_recipe_treatment(
    treatment: ActiveVisionCollectionTreatment,
    config: ScenarioConfig,
) -> ActiveVisionCollectionTreatment:
    """Attach one D5 recipe's intent windows to a base actuator treatment."""

    raw_recipe = config.metadata.get("learning_source_recipe")
    if raw_recipe is None:
        return treatment
    if not isinstance(raw_recipe, Mapping):
        raise ValueError("learning_source_recipe metadata must be a mapping")
    if raw_recipe.get("module") != "D5":
        return treatment
    profile = str(raw_recipe.get("collection_profile", "")).strip().lower()
    if profile != treatment.profile_id:
        raise ValueError("D5 recipe collection profile differs from stack profile")
    raw_windows = raw_recipe.get("intent_windows")
    if not isinstance(raw_windows, (tuple, list)) or not raw_windows:
        raise ValueError("D5 recipe requires non-empty intent_windows")
    windows: list[ActiveVisionIntentWindowTreatment] = []
    for raw in raw_windows:
        if not isinstance(raw, Mapping):
            raise ValueError("D5 intent window must be a mapping")
        windows.append(
            ActiveVisionIntentWindowTreatment(
                window_id=str(raw["window_id"]),
                start_s=float(raw["start_s"]),
                end_s=float(raw["end_s"]),
                intent=str(raw["intent"]),
                camera_role=str(raw["camera_role"]),
                treatment_recipe=str(raw["treatment_recipe"]),
                required_controls=tuple(raw["required_controls"]),
            )
        )
    if abs(windows[0].start_s) > 1.0e-12 or abs(
        windows[-1].end_s - float(config.duration_s)
    ) > 1.0e-12:
        raise ValueError("D5 intent windows must cover the full episode")
    if any(
        abs(windows[index].end_s - windows[index + 1].start_s) > 1.0e-12
        for index in range(len(windows) - 1)
    ):
        raise ValueError("D5 intent windows must be contiguous")
    near_tie_window_ids: tuple[str, ...] = ()
    raw_confusions = raw_recipe.get("hard_confusion_assignments", ())
    if not isinstance(raw_confusions, (tuple, list)):
        raise ValueError("D5 hard-confusion assignments must be a sequence")
    for raw in raw_confusions:
        if not isinstance(raw, Mapping):
            raise ValueError("D5 hard-confusion assignment must be a mapping")
        if str(raw.get("family", "")).strip() != "multiple_legal_targets_near_tie":
            continue
        raw_window_ids = raw.get("window_ids")
        if not isinstance(raw_window_ids, (tuple, list)):
            raise ValueError("D5 near-tie assignment requires window_ids")
        near_tie_window_ids = tuple(str(value).strip() for value in raw_window_ids)
        break
    return ActiveVisionCollectionTreatment(
        profile_id=treatment.profile_id,
        recon_cue_loss_period_s=treatment.recon_cue_loss_period_s,
        recon_cue_loss_duration_s=treatment.recon_cue_loss_duration_s,
        camera_slew_rate_deg_s=treatment.camera_slew_rate_deg_s,
        camera_minimum_settle_s=treatment.camera_minimum_settle_s,
        camera_maximum_settle_s=treatment.camera_maximum_settle_s,
        camera_fov_transition_settle_s=treatment.camera_fov_transition_settle_s,
        intent_windows=tuple(windows),
        near_tie_window_ids=near_tie_window_ids,
    )


__all__ = [
    "ACTIVE_VISION_BALANCED_ACTION_ROLE_PROFILE_V1",
    "ACTIVE_VISION_COLLECTION_PROFILES",
    "ACTIVE_VISION_OPERATIONAL_PROFILE_V1",
    "ActiveVisionCollectionTreatment",
    "ActiveVisionIntentWindowTreatment",
    "bind_active_vision_recipe_treatment",
    "resolve_active_vision_collection_treatment",
]
