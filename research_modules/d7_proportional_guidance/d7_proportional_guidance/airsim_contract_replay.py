"""Offline audit of D7 contract rejection effects in AirSim control logs."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable


AIRSIM_CONTRACT_REPLAY_BOUNDARY = (
    "d7_offline_airsim_contract_replay_no_control_or_truth_identity_use"
)
P1_COOPERATIVE_REJECT_REASONS = (
    "coalition_window_closed",
    "coalition_not_activated",
    "d4_owner_missing",
)


@dataclass(frozen=True)
class ContractRejectImpact:
    reason: str
    sample_count: int
    affected_resource_ids: tuple[str, ...]
    contiguous_segment_count: int
    visual_png_enabled_count: int
    terminal_contract_allowed_count: int
    radar_pn_fallback_count: int
    other_guidance_law_counts: dict[str, int]
    minimum_range_m: float | None


@dataclass(frozen=True)
class AirSimContractReplayAnalysis:
    schema: str
    boundary: str
    record_count: int
    reason_impacts: tuple[ContractRejectImpact, ...]
    plan_identity_change_count: int
    plan_version_regression_count: int
    physical_pair_success_count: int | None
    coalition_completion_count: int | None
    online_truth_use_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_impacts"] = [asdict(row) for row in self.reason_impacts]
        return payload


def analyze_airsim_contract_replay(
    control_commands_csv: str | Path,
    intercept_summary_json: str | Path | None = None,
    *,
    reasons: Iterable[str] = P1_COOPERATIVE_REJECT_REASONS,
) -> AirSimContractReplayAnalysis:
    """Measure how selected contract rejections affected D7 control output."""

    rows = _read_rows(control_commands_csv)
    summary = _read_summary(intercept_summary_json)
    reason_impacts = tuple(
        _impact_for_reason(rows, str(reason)) for reason in reasons
    )
    identity_changes = 0
    version_regressions = 0
    previous_by_resource: dict[tuple[str, str], tuple[str, int]] = {}
    for row in rows:
        resource_id = row.get("resource_id", "")
        resource_key = (row.get("episode_id", ""), resource_id)
        identity = (row.get("plan_id", ""), _int(row.get("plan_version"), default=0))
        previous = previous_by_resource.get(resource_key)
        if previous is not None and identity != previous:
            identity_changes += 1
            if identity[1] < previous[1]:
                version_regressions += 1
        previous_by_resource[resource_key] = identity

    return AirSimContractReplayAnalysis(
        schema="d7.airsim_contract_replay.v1",
        boundary=AIRSIM_CONTRACT_REPLAY_BOUNDARY,
        record_count=len(rows),
        reason_impacts=reason_impacts,
        plan_identity_change_count=identity_changes,
        plan_version_regression_count=version_regressions,
        physical_pair_success_count=_optional_int(
            summary.get("pair_physical_success_count", summary.get("success_count"))
        ),
        coalition_completion_count=_optional_int(summary.get("coalition_completion_count")),
        online_truth_use_count=sum(
            _bool(row.get("truth_identity_online_use")) for row in rows
        ),
    )


def _impact_for_reason(
    rows: list[dict[str, str]],
    reason: str,
) -> ContractRejectImpact:
    selected = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("terminal_contract_reject_reason", "") == reason
    ]
    laws = Counter(row.get("guidance_law", "") for _, row in selected)
    ranges = []
    for _, row in selected:
        range_m = _float(row.get("range_m"))
        if range_m is not None:
            ranges.append(range_m)
    return ContractRejectImpact(
        reason=reason,
        sample_count=len(selected),
        affected_resource_ids=tuple(
            sorted({row.get("resource_id", "") for _, row in selected if row.get("resource_id")})
        ),
        contiguous_segment_count=_segment_count(selected),
        visual_png_enabled_count=sum(
            _bool(row.get("visual_png_enabled"))
            or row.get("guidance_law", "") in {"png_vm", "png_ttc"}
            for _, row in selected
        ),
        terminal_contract_allowed_count=sum(
            _bool(row.get("terminal_contract_allowed")) for _, row in selected
        ),
        radar_pn_fallback_count=laws.pop("radar_pn", 0),
        other_guidance_law_counts={
            law: count for law, count in sorted(laws.items()) if law
        },
        minimum_range_m=min(ranges) if ranges else None,
    )


def _segment_count(selected: list[tuple[int, dict[str, str]]]) -> int:
    if not selected:
        return 0
    segments = 0
    previous_by_resource: dict[tuple[str, str], float] = {}
    for _, row in selected:
        resource_id = row.get("resource_id", "")
        resource_key = (row.get("episode_id", ""), resource_id)
        timestamp_s = _float(row.get("timestamp_s")) or 0.0
        previous = previous_by_resource.get(resource_key)
        if previous is None or timestamp_s - previous > 0.15:
            segments += 1
        previous_by_resource[resource_key] = timestamp_s
    return segments


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _read_summary(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("intercept summary must contain a JSON object")
    return payload


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _int(value: Any, *, default: int) -> int:
    return default if value in {None, ""} else int(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
