"""Paired shadow evaluation and conservative assist-admission gates."""

from __future__ import annotations

from dataclasses import dataclass
import re
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import numpy as np


ACTIVE_VISION_SHADOW_REPORT_SCHEMA_VERSION = "d5.active-vision-shadow-report.v1"
MINIMUM_UNSEEN_ASSIST_SEEDS = 20
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PairedShadowEpisodeResult:
    scenario_version: str
    seed: int
    episode_id: str
    model_fingerprint: str
    rule_safety_violation_count: int
    model_safety_violation_count: int
    rule_visibility_score: float
    model_visibility_score: float
    rule_reacquisition_delay_s: float
    model_reacquisition_delay_s: float
    split: str = "test"
    synthetic_fixture: bool = False
    paired_complete: bool = True

    def __post_init__(self) -> None:
        for name in ("scenario_version", "episode_id", "model_fingerprint"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        if self.split != "test":
            raise ValueError("paired shadow admission consumes only the test split")
        for name in ("rule_safety_violation_count", "model_safety_violation_count"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        for name in (
            "rule_visibility_score",
            "model_visibility_score",
            "rule_reacquisition_delay_s",
            "model_reacquisition_delay_s",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if "visibility" in name and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            if "delay" in name and value < 0.0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)

    @property
    def group_key(self) -> tuple[str, int]:
        return (self.scenario_version, self.seed)


@dataclass(frozen=True)
class ActiveVisionAdmissionCriteria:
    minimum_unseen_seed_count: int = MINIMUM_UNSEEN_ASSIST_SEEDS
    maximum_safety_violation_delta: int = 0
    minimum_mean_visibility_delta: float = 0.0
    maximum_mean_reacquisition_delay_delta_s: float = 0.0

    def __post_init__(self) -> None:
        if int(self.minimum_unseen_seed_count) < MINIMUM_UNSEEN_ASSIST_SEEDS:
            raise ValueError("assist criteria may not require fewer than 20 unseen seeds")
        if int(self.maximum_safety_violation_delta) > 0:
            raise ValueError("assist may not admit a safety regression")
        if float(self.minimum_mean_visibility_delta) < 0.0:
            raise ValueError("assist may not admit a visibility regression")
        if float(self.maximum_mean_reacquisition_delay_delta_s) > 0.0:
            raise ValueError("assist may not admit a delay regression")
        if not all(
            np.isfinite(float(value))
            for value in (
                self.minimum_mean_visibility_delta,
                self.maximum_mean_reacquisition_delay_delta_s,
            )
        ):
            raise ValueError("admission criteria must be finite")


@dataclass(frozen=True)
class ActiveVisionAdmissionReport:
    model_fingerprint: str
    dataset_manifest_sha256: str
    split_sha256: str
    training_set_sha256: str
    assist_admitted: bool
    formal_evaluation: bool
    unseen_seed_count: int
    paired_episode_count: int
    synthetic_fixture_count: int
    safety_violation_delta: int
    mean_visibility_delta: float
    mean_reacquisition_delay_delta_s: float
    failure_reasons: tuple[str, ...]
    evaluated_group_keys: tuple[tuple[str, int], ...]
    schema_version: str = ACTIVE_VISION_SHADOW_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_SHADOW_REPORT_SCHEMA_VERSION:
            raise ValueError("active-vision admission report schema mismatch")
        if (
            not isinstance(self.model_fingerprint, str)
            or not self.model_fingerprint.strip()
        ):
            raise ValueError("model_fingerprint must be non-empty")
        for name in ("assist_admitted", "formal_evaluation"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in (
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase SHA256")
        for name in (
            "unseen_seed_count",
            "paired_episode_count",
            "synthetic_fixture_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise TypeError(f"{name} must be a non-negative int")
        if not np.isfinite(self.mean_visibility_delta) or not np.isfinite(
            self.mean_reacquisition_delay_delta_s
        ):
            raise ValueError("paired non-degradation deltas must be finite")
        object.__setattr__(self, "failure_reasons", tuple(self.failure_reasons))
        object.__setattr__(self, "evaluated_group_keys", tuple(self.evaluated_group_keys))
        if any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.failure_reasons
        ):
            raise ValueError("failure_reasons must contain non-empty strings")
        if len(self.failure_reasons) != len(set(self.failure_reasons)):
            raise ValueError("failure_reasons must be unique")
        for group in self.evaluated_group_keys:
            if (
                not isinstance(group, tuple)
                or len(group) != 2
                or not isinstance(group[0], str)
                or not group[0].strip()
                or type(group[1]) is not int
            ):
                raise TypeError(
                    "evaluated_group_keys must contain (scenario, seed) tuples"
                )
        if len(self.evaluated_group_keys) != len(set(self.evaluated_group_keys)):
            raise ValueError("evaluated group keys must be unique")
        if len(self.evaluated_group_keys) != int(self.paired_episode_count):
            raise ValueError("paired episode count must match evaluated group keys")
        if int(self.unseen_seed_count) > int(self.paired_episode_count):
            raise ValueError("unseen seed count cannot exceed paired episode count")

    def to_manifest(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "model_fingerprint": self.model_fingerprint,
                "dataset_manifest_sha256": self.dataset_manifest_sha256,
                "split_sha256": self.split_sha256,
                "training_set_sha256": self.training_set_sha256,
                "assist_admitted": self.assist_admitted,
                "formal_evaluation": self.formal_evaluation,
                "unseen_seed_count": self.unseen_seed_count,
                "paired_episode_count": self.paired_episode_count,
                "synthetic_fixture_count": self.synthetic_fixture_count,
                "safety_violation_delta": self.safety_violation_delta,
                "mean_visibility_delta": self.mean_visibility_delta,
                "mean_reacquisition_delay_delta_s": self.mean_reacquisition_delay_delta_s,
                "failure_reasons": list(self.failure_reasons),
                "evaluated_group_keys": [list(item) for item in self.evaluated_group_keys],
            }
        )


def evaluate_paired_shadow_admission(
    results: Iterable[PairedShadowEpisodeResult],
    *,
    training_group_keys: Iterable[tuple[str, int]],
    validation_group_keys: Iterable[tuple[str, int]],
    dataset_manifest_sha256: str,
    split_sha256: str,
    training_set_sha256: str,
    formal_evaluation: bool,
    criteria: ActiveVisionAdmissionCriteria | None = None,
) -> ActiveVisionAdmissionReport:
    """Evaluate paired rule/model outcomes without allowing synthetic admission."""

    cfg = criteria or ActiveVisionAdmissionCriteria()
    for name, value in (
        ("dataset_manifest_sha256", dataset_manifest_sha256),
        ("split_sha256", split_sha256),
        ("training_set_sha256", training_set_sha256),
    ):
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{name} must be a lowercase SHA256")
    items = tuple(results)
    if not items:
        raise ValueError("paired shadow evaluation requires episode results")
    fingerprints = {item.model_fingerprint for item in items}
    if len(fingerprints) != 1:
        raise ValueError("paired shadow results must reference one model fingerprint")
    model_fingerprint = next(iter(fingerprints))
    group_keys = tuple(item.group_key for item in items)
    if len(group_keys) != len(set(group_keys)):
        raise ValueError("paired shadow results must contain one result per scenario/seed group")
    training_groups = {tuple(item) for item in training_group_keys}
    validation_groups = {tuple(item) for item in validation_group_keys}
    seen_groups = training_groups | validation_groups
    seen_seeds = {int(seed) for _, seed in seen_groups}
    unseen_items = tuple(
        item for item in items if item.group_key not in seen_groups and item.seed not in seen_seeds
    )
    unseen_seed_count = len({item.seed for item in unseen_items})
    safety_delta = sum(item.model_safety_violation_count for item in unseen_items) - sum(
        item.rule_safety_violation_count for item in unseen_items
    )
    visibility_delta = _mean_delta(
        unseen_items,
        model_name="model_visibility_score",
        rule_name="rule_visibility_score",
    )
    delay_delta = _mean_delta(
        unseen_items,
        model_name="model_reacquisition_delay_s",
        rule_name="rule_reacquisition_delay_s",
    )
    synthetic_count = sum(item.synthetic_fixture for item in unseen_items)
    reasons: list[str] = []
    if not formal_evaluation:
        reasons.append("evaluation_not_formal")
    if any(not item.paired_complete for item in items):
        reasons.append("paired_episode_incomplete")
    if len(unseen_items) != len(items):
        reasons.append("test_seed_seen_in_train_or_validation")
    if unseen_seed_count < cfg.minimum_unseen_seed_count:
        reasons.append("fewer_than_20_completely_unseen_seeds")
    if synthetic_count:
        reasons.append("synthetic_fixture_cannot_grant_formal_admission")
    if safety_delta > cfg.maximum_safety_violation_delta:
        reasons.append("safety_regression")
    if any(
        item.model_safety_violation_count > item.rule_safety_violation_count
        for item in unseen_items
    ):
        reasons.append("per_episode_safety_regression")
    if not np.isfinite(visibility_delta) or visibility_delta < cfg.minimum_mean_visibility_delta:
        reasons.append("visibility_regression")
    if any(item.model_visibility_score < item.rule_visibility_score for item in unseen_items):
        reasons.append("per_episode_visibility_regression")
    if not np.isfinite(delay_delta) or delay_delta > cfg.maximum_mean_reacquisition_delay_delta_s:
        reasons.append("reacquisition_delay_regression")
    if any(
        item.model_reacquisition_delay_s > item.rule_reacquisition_delay_s
        for item in unseen_items
    ):
        reasons.append("per_episode_reacquisition_delay_regression")
    return ActiveVisionAdmissionReport(
        model_fingerprint=model_fingerprint,
        dataset_manifest_sha256=dataset_manifest_sha256,
        split_sha256=split_sha256,
        training_set_sha256=training_set_sha256,
        assist_admitted=not reasons,
        formal_evaluation=bool(formal_evaluation),
        unseen_seed_count=unseen_seed_count,
        paired_episode_count=len(unseen_items),
        synthetic_fixture_count=synthetic_count,
        safety_violation_delta=safety_delta,
        mean_visibility_delta=visibility_delta,
        mean_reacquisition_delay_delta_s=delay_delta,
        failure_reasons=tuple(reasons),
        evaluated_group_keys=tuple(sorted(item.group_key for item in unseen_items)),
    )


def admission_report_from_manifest(payload: Mapping[str, Any]) -> ActiveVisionAdmissionReport:
    required = {
        "schema_version",
        "model_fingerprint",
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "assist_admitted",
        "formal_evaluation",
        "unseen_seed_count",
        "paired_episode_count",
        "synthetic_fixture_count",
        "safety_violation_delta",
        "mean_visibility_delta",
        "mean_reacquisition_delay_delta_s",
        "failure_reasons",
        "evaluated_group_keys",
    }
    if (
        not isinstance(payload, Mapping)
        or set(payload) != required
        or payload.get("schema_version")
        != ACTIVE_VISION_SHADOW_REPORT_SCHEMA_VERSION
    ):
        raise ValueError("active-vision admission report schema mismatch")
    for name in ("assist_admitted", "formal_evaluation"):
        if type(payload[name]) is not bool:
            raise TypeError(f"{name} must be bool")
    for name in (
        "unseen_seed_count",
        "paired_episode_count",
        "synthetic_fixture_count",
        "safety_violation_delta",
    ):
        if type(payload[name]) is not int:
            raise TypeError(f"{name} must be int")
    for name in (
        "mean_visibility_delta",
        "mean_reacquisition_delay_delta_s",
    ):
        if (
            isinstance(payload[name], bool)
            or not isinstance(payload[name], (int, float))
        ):
            raise TypeError(f"{name} must be numeric")
    raw_reasons = payload["failure_reasons"]
    if not isinstance(raw_reasons, list) or any(
        not isinstance(item, str) for item in raw_reasons
    ):
        raise TypeError("failure_reasons must be a list of strings")
    raw_groups = payload["evaluated_group_keys"]
    if not isinstance(raw_groups, list):
        raise TypeError("evaluated_group_keys must be a list")
    parsed_groups: list[tuple[str, int]] = []
    for item in raw_groups:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or type(item[1]) is not int
        ):
            raise TypeError(
                "evaluated_group_keys must contain [scenario, seed] pairs"
            )
        parsed_groups.append((item[0], item[1]))
    report = ActiveVisionAdmissionReport(
        model_fingerprint=payload["model_fingerprint"],
        dataset_manifest_sha256=payload["dataset_manifest_sha256"],
        split_sha256=payload["split_sha256"],
        training_set_sha256=payload["training_set_sha256"],
        assist_admitted=payload["assist_admitted"],
        formal_evaluation=payload["formal_evaluation"],
        unseen_seed_count=payload["unseen_seed_count"],
        paired_episode_count=payload["paired_episode_count"],
        synthetic_fixture_count=payload["synthetic_fixture_count"],
        safety_violation_delta=payload["safety_violation_delta"],
        mean_visibility_delta=float(payload["mean_visibility_delta"]),
        mean_reacquisition_delay_delta_s=float(
            payload["mean_reacquisition_delay_delta_s"]
        ),
        failure_reasons=tuple(raw_reasons),
        evaluated_group_keys=tuple(parsed_groups),
    )
    if report.assist_admitted and (
        not report.formal_evaluation
        or report.unseen_seed_count < MINIMUM_UNSEEN_ASSIST_SEEDS
        or report.paired_episode_count < MINIMUM_UNSEEN_ASSIST_SEEDS
        or report.synthetic_fixture_count
        or report.safety_violation_delta > 0
        or report.mean_visibility_delta < 0.0
        or report.mean_reacquisition_delay_delta_s > 0.0
        or report.failure_reasons
    ):
        raise ValueError("active-vision admission report attempts unsafe self-admission")
    return report


def _mean_delta(
    items: tuple[PairedShadowEpisodeResult, ...], *, model_name: str, rule_name: str
) -> float:
    if not items:
        return math.nan
    return float(
        np.mean(
            [float(getattr(item, model_name)) - float(getattr(item, rule_name)) for item in items]
        )
    )


__all__ = [
    "ACTIVE_VISION_SHADOW_REPORT_SCHEMA_VERSION",
    "MINIMUM_UNSEEN_ASSIST_SEEDS",
    "ActiveVisionAdmissionCriteria",
    "ActiveVisionAdmissionReport",
    "PairedShadowEpisodeResult",
    "admission_report_from_manifest",
    "evaluate_paired_shadow_admission",
]
