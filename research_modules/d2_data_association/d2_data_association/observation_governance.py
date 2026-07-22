"""Versioned observation-evidence retention policy for scalable D2 tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION = "d2-observation-claim-ledger-v2"
REPLAY_COAST_POLICY_SCHEMA_VERSION = "d2-replay-coast-policy-v1"


@dataclass(frozen=True, slots=True)
class ObservationClaimLedgerConfig:
    """Bound the replay ledger without allowing safe-window evidence reuse.

    Claims remain resident for both the configured retention interval and the
    admitted maximum lateness interval.  A claim is eligible for eviction only
    when its source measurement time is at or below ``safe_watermark``.  Future
    observations at or below that watermark are rejected before lookup, so an
    evicted old key cannot produce another hit or track birth.
    """

    config_version: str = "d2-observation-claim-policy-v2"
    retention_seconds: float = 30.0
    max_count: int = 100_000
    max_lateness_seconds: float = 5.0

    def __post_init__(self) -> None:
        version = str(self.config_version).strip()
        if not version:
            raise ValueError("observation claim config_version must be non-empty")
        object.__setattr__(self, "config_version", version)
        for name in ("retention_seconds", "max_lateness_seconds"):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        count = int(self.max_count)
        if count <= 0:
            raise ValueError("max_count must be positive")
        object.__setattr__(self, "max_count", count)

    @property
    def protected_window_seconds(self) -> float:
        """Return the conservative interval retained behind tracker time."""

        return max(self.retention_seconds, self.max_lateness_seconds)

    def safe_watermark(self, tracker_timestamp: float) -> float:
        """Return the source-time boundary behind which claims may retire."""

        timestamp = float(tracker_timestamp)
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("tracker_timestamp must be finite and non-negative")
        return timestamp - self.protected_window_seconds

    def admission_watermark(self, tracker_timestamp: float) -> float:
        """Return the oldest source-time boundary admitted for a new scan."""

        timestamp = float(tracker_timestamp)
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("tracker_timestamp must be finite and non-negative")
        return timestamp - self.max_lateness_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_CLAIM_LEDGER_SCHEMA_VERSION,
            "config_version": self.config_version,
            "retention_seconds": self.retention_seconds,
            "max_count": self.max_count,
            "max_lateness_seconds": self.max_lateness_seconds,
            "protected_window_seconds": self.protected_window_seconds,
        }


@dataclass(frozen=True, slots=True)
class ReplayCoastConfig:
    """Bound prediction-only coast for an already claimed D1 posterior.

    The grace clock is always measured from the track's last fresh measurement
    update. Replayed posteriors never move that clock, so they cannot keep a
    track alive indefinitely.
    """

    config_version: str = "d2-replay-coast-policy-v1"
    grace_seconds: float = 0.5

    def __post_init__(self) -> None:
        version = str(self.config_version).strip()
        if not version:
            raise ValueError("replay coast config_version must be non-empty")
        object.__setattr__(self, "config_version", version)
        grace = float(self.grace_seconds)
        if not np.isfinite(grace) or grace < 0.0:
            raise ValueError("grace_seconds must be finite and non-negative")
        object.__setattr__(self, "grace_seconds", grace)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPLAY_COAST_POLICY_SCHEMA_VERSION,
            "config_version": self.config_version,
            "grace_seconds": self.grace_seconds,
            "clock_source": "track_last_fresh_update_time",
            "refresh_on_replay": False,
        }
