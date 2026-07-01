"""Simulated cooperative identity and friend-tag handling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from .models import IdentityClaim, LocalVisualTrack


def bbox_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Intersection-over-union for `(x_min, y_min, x_max, y_max)` boxes."""

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


class IdentityChecker:
    """Parse and evaluate simulated OpenDroneID/cooperative friend claims.

    The checker only supports positive cooperative confirmation. Missing,
    stale, unsigned, or spoof-suspected claims do not classify unknown objects.
    """

    def __init__(
        self,
        friendly_platform_ids: Iterable[str] | None = None,
        max_age_s: float = 2.0,
    ) -> None:
        self.friendly_platform_ids = set(friendly_platform_ids or [])
        self.max_age_s = float(max_age_s)

    def parse_claims(
        self,
        raw_messages: Iterable[Mapping[str, Any]],
        current_time: float,
    ) -> list[IdentityClaim]:
        """Parse simulated identity messages into normalized claims.

        Expected message keys are intentionally simple for offline simulation:
        `platform_id`, `protocol`/`claim_type`, `timestamp`,
        `associated_local_track_id`/`local_track_id`, `center_px`, `bbox`,
        `is_friend`, and `signature_valid`.
        """

        claims: list[IdentityClaim] = []
        for raw in raw_messages:
            platform_id = str(raw.get("platform_id") or raw.get("uas_id") or raw.get("id") or "")
            if not platform_id:
                continue
            timestamp = float(raw.get("timestamp", current_time))
            age = current_time - timestamp
            claim_type = str(raw.get("claim_type") or raw.get("protocol") or "remote_id").lower()
            signature_valid = bool(raw.get("signature_valid", raw.get("signed", False)))
            explicit_friend = bool(raw.get("is_friend", raw.get("friend", False)))
            trusted = platform_id in self.friendly_platform_ids or bool(raw.get("trusted", False))
            is_friend = explicit_friend or trusted

            if age > self.max_age_s:
                auth_state = "stale"
            elif bool(raw.get("spoof_suspected", False)):
                auth_state = "spoof_suspected"
            elif is_friend and not signature_valid:
                auth_state = "spoof_suspected"
            elif is_friend and signature_valid and (trusted or not self.friendly_platform_ids):
                auth_state = "verified"
            else:
                auth_state = "unverified"

            claims.append(
                IdentityClaim(
                    platform_id=platform_id,
                    claim_type=claim_type,
                    auth_state=auth_state,
                    associated_local_track_id=raw.get("associated_local_track_id")
                    or raw.get("local_track_id"),
                    center_px=raw.get("center_px"),
                    bbox=raw.get("bbox"),
                    timestamp=timestamp,
                    is_friend=is_friend,
                    metadata=dict(raw),
                )
            )
        return claims

    def claim_overlaps_local(
        self,
        claim: IdentityClaim,
        local_track: LocalVisualTrack,
        center_threshold_px: float = 20.0,
        iou_threshold: float = 0.05,
    ) -> bool:
        """Return true when a claim refers to or overlaps a local visual track."""

        if claim.associated_local_track_id == local_track.local_track_id:
            return True
        if claim.bbox is not None and local_track.bbox is not None:
            if bbox_iou(claim.bbox, local_track.bbox) >= iou_threshold:
                return True
        if claim.center_px is not None:
            distance = float(np.linalg.norm(claim.center_px - local_track.center_px))
            if distance <= center_threshold_px:
                return True
        return False

    def friend_conflict_state(
        self,
        local_track: LocalVisualTrack,
        claims: Iterable[IdentityClaim],
        center_threshold_px: float = 20.0,
        iou_threshold: float = 0.05,
    ) -> str:
        """Classify identity overlap for association decisions."""

        best_nonverified = "none"
        for claim in claims:
            if not self.claim_overlaps_local(claim, local_track, center_threshold_px, iou_threshold):
                continue
            if claim.is_friend and claim.auth_state == "verified":
                return "verified_friend_overlap"
            if claim.auth_state == "spoof_suspected":
                best_nonverified = "spoof_suspected_overlap"
            elif claim.is_friend and claim.auth_state in {"stale", "unverified"}:
                best_nonverified = "unverified_friend_overlap"
        return best_nonverified
