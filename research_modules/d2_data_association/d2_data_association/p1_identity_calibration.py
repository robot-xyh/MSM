"""Fixed P1 dense-crossing identity-continuity calibration matrix.

The runner is deliberately offline.  It evaluates GNN/Hungarian variants on
one frozen replay/truth suite, then runs the lightweight JPDA research adapter
only on the best GNN configuration's input.  It never changes the default
online associator.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .associators import GNNHungarianAssociator, JPDAAssociator
from .d1_offline_truth_adapter import (
    D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
    D1_OFFLINE_TRUTH_ALIGNMENT_SCHEMA_VERSION,
    load_d1_airsim_offline_truth_alignment_json,
)
from .offline_truth import (
    OfflineTruthLabel,
    load_offline_truth_labels_jsonl,
    strip_offline_truth_from_frames,
)
from .models import TrackerTruthPolicy
from .replay import load_airsim_replay_frames, run_airsim_replay_association
from .tracker import Tracker


P1_IDENTITY_MATRIX_SCHEMA_VERSION = "d2-p1-identity-calibration/v2"
P1_IDENTITY_INPUT_SCHEMA_VERSION = "d2-p1-identity-calibration-input/v1"
P1_IDENTITY_ADMISSION_POLICY_VERSION = (
    "d2-p1-identity-admission/ceiling-aware-error-reduction-v1"
)
IDENTITY_CONTINUITY_THEORETICAL_UPPER_BOUND = 1.0
MINIMUM_ID_SWITCH_REDUCTION_FRACTION = 0.30
MINIMUM_CONTINUITY_ERROR_REDUCTION_FRACTION = 0.10
LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE = 0.10
MAXIMUM_FALSE_TRACK_INCREASE_FRACTION = 0.10
_ADMISSION_NUMERICAL_TOLERANCE = 1.0e-12
GATE_THRESHOLDS = (5.99, 9.21, 13.82)
QUALITY_AWARE_OPTIONS = (False, True)
LIFECYCLE_OPTIONS = ((1, 3), (2, 5), (3, 7))
MOTION_WEIGHT_MULTIPLIERS = (0.5, 1.0, 2.0)
DEFAULT_MOTION_WEIGHT = 1.0
_LEGACY_AIRSIM_EVIDENCE_SOURCE = "airsim"
_REAL_AIRSIM_EVIDENCE_PREFIX = "real_airsim_"
SCENARIO_DIFFICULTIES = (
    "nominal",
    "tight_crossing",
    "dropout",
    "clutter",
    "delayed_noisy",
    "combined",
)
TARGET_SPACING_BY_DIFFICULTY_M = {
    "nominal": 4.0,
    "tight_crossing": 2.0,
    "dropout": 4.0,
    "clutter": 4.0,
    "delayed_noisy": 4.0,
    "combined": 2.0,
}
TARGET_SPACING_TOLERANCE_M = 1.0
_SCENARIO_DIFFICULTY_METADATA: dict[str, dict[str, Any]] = {
    "nominal": {
        "difficulty_rank": 0,
        "stressors": [],
        "target_lateral_spacing_m": 4.0,
        "description": "Nominal dense crossing without added stress injection.",
    },
    "tight_crossing": {
        "difficulty_rank": 1,
        "stressors": ["tight_crossing"],
        "target_lateral_spacing_m": 2.0,
        "description": "Approximately 2 m lateral spacing at the crossing.",
    },
    "dropout": {
        "difficulty_rank": 1,
        "stressors": ["detection_dropout"],
        "target_lateral_spacing_m": 4.0,
        "dropout_duration_s": [0.6, 1.2],
        "description": "Anonymous detections are absent around the crossing.",
    },
    "clutter": {
        "difficulty_rank": 1,
        "stressors": ["false_alarm_clutter"],
        "target_lateral_spacing_m": 4.0,
        "false_alarms_per_frame": [1, 3],
        "description": "Unlabelled false alarms are added to each frame.",
    },
    "delayed_noisy": {
        "difficulty_rank": 1,
        "stressors": ["measurement_delay", "covariance_inflation"],
        "target_lateral_spacing_m": 4.0,
        "measurement_delay_s": [0.2, 0.5],
        "covariance_scale": 3.0,
        "description": "Measurements are delayed and their covariance is inflated.",
    },
    "combined": {
        "difficulty_rank": 2,
        "stressors": [
            "tight_crossing",
            "detection_dropout",
            "false_alarm_clutter",
            "measurement_delay",
            "covariance_inflation",
        ],
        "target_lateral_spacing_m": 2.0,
        "dropout_duration_s": [0.6, 1.2],
        "false_alarms_per_frame": [1, 3],
        "measurement_delay_s": [0.2, 0.5],
        "covariance_scale": 3.0,
        "description": "All governed P1 identity stressors are active.",
    },
}


@dataclass(frozen=True, slots=True)
class IdentityMatrixConfig:
    """One governed GNN/Hungarian calibration configuration."""

    gate_threshold: float
    quality_aware_gate: bool
    lost_miss_threshold: int
    drop_miss_threshold: int
    motion_weight_multiplier: float
    base_motion_weight: float = DEFAULT_MOTION_WEIGHT

    def __post_init__(self) -> None:
        if not np.isfinite(self.gate_threshold) or self.gate_threshold <= 0.0:
            raise ValueError("gate_threshold must be positive and finite")
        if self.lost_miss_threshold <= 0:
            raise ValueError("lost_miss_threshold must be positive")
        if self.drop_miss_threshold <= self.lost_miss_threshold:
            raise ValueError("drop_miss_threshold must exceed lost_miss_threshold")
        if (
            not np.isfinite(self.motion_weight_multiplier)
            or self.motion_weight_multiplier <= 0.0
        ):
            raise ValueError("motion_weight_multiplier must be positive and finite")
        if not np.isfinite(self.base_motion_weight) or self.base_motion_weight <= 0.0:
            raise ValueError("base_motion_weight must be positive and finite")

    @property
    def motion_weight(self) -> float:
        return float(self.base_motion_weight * self.motion_weight_multiplier)

    @property
    def config_id(self) -> str:
        quality = "qa1" if self.quality_aware_gate else "qa0"
        return (
            f"gnn-g{self.gate_threshold:.2f}-{quality}"
            f"-ld{self.lost_miss_threshold}_{self.drop_miss_threshold}"
            f"-mw{self.motion_weight_multiplier:.1f}x"
        )

    @property
    def is_baseline(self) -> bool:
        return (
            np.isclose(self.gate_threshold, 9.21)
            and self.quality_aware_gate
            and self.lost_miss_threshold == 2
            and self.drop_miss_threshold == 5
            and np.isclose(self.motion_weight_multiplier, 1.0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id,
            "gate_threshold": float(self.gate_threshold),
            "quality_aware_gate": self.quality_aware_gate,
            "lost_miss_threshold": self.lost_miss_threshold,
            "drop_miss_threshold": self.drop_miss_threshold,
            "motion_weight_multiplier": float(self.motion_weight_multiplier),
            "base_motion_weight": float(self.base_motion_weight),
            "motion_weight": self.motion_weight,
            "is_baseline": self.is_baseline,
        }


@dataclass(frozen=True, slots=True)
class FrozenReplayCase:
    """One truth-isolated replay seed plus evaluator-only labels."""

    seed: int
    replay_name: str
    frames: tuple[Mapping[str, Any], ...]
    offline_truth_labels: tuple[OfflineTruthLabel | Mapping[str, Any], ...]
    evidence_source: str
    scenario_difficulty: str = "nominal"
    difficulty_metadata: Mapping[str, Any] | None = None
    offline_truth_alignment: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.replay_name:
            raise ValueError("replay_name must not be empty")
        if not self.frames:
            raise ValueError("frozen replay case must contain frames")
        if not self.evidence_source:
            raise ValueError("evidence_source must not be empty")
        _normalize_scenario_difficulty(self.scenario_difficulty)
        if self.difficulty_metadata is not None and not isinstance(
            self.difficulty_metadata, Mapping
        ):
            raise ValueError("difficulty_metadata must be a mapping when provided")
        if self.offline_truth_alignment is not None and not isinstance(
            self.offline_truth_alignment, Mapping
        ):
            raise ValueError("offline_truth_alignment must be a mapping when provided")
        alignment = self.offline_truth_alignment_summary
        if int(alignment["matched_sample_count"]) != len(self.offline_truth_labels):
            raise ValueError(
                "offline_truth_alignment matched_sample_count does not match labels"
            )
        if bool(alignment.get("online_truth_injected", False)):
            raise ValueError("offline_truth_alignment must not inject online truth")

    @property
    def normalized_scenario_difficulty(self) -> str:
        return _normalize_scenario_difficulty(self.scenario_difficulty)

    @property
    def scenario_difficulty_metadata(self) -> dict[str, Any]:
        return {
            "scenario_difficulty": self.normalized_scenario_difficulty,
            "canonical_profile": _json_ready(
                _SCENARIO_DIFFICULTY_METADATA[
                    self.normalized_scenario_difficulty
                ]
            ),
            "declared_parameters": _json_ready(dict(self.difficulty_metadata or {})),
        }

    @property
    def input_digest(self) -> str:
        clean_frames = strip_offline_truth_from_frames(self.frames)
        labels = [
            label.to_dict() if isinstance(label, OfflineTruthLabel) else dict(label)
            for label in self.offline_truth_labels
        ]
        return _stable_digest(
            {
                "frames": clean_frames,
                "offline_truth": labels,
                "offline_truth_alignment": self.offline_truth_alignment_summary,
                "scenario_difficulty_metadata": self.scenario_difficulty_metadata,
            }
        )

    @property
    def target_spacing_provenance(self) -> dict[str, Any]:
        return _case_target_spacing_provenance(self)

    @property
    def offline_truth_alignment_summary(self) -> dict[str, Any]:
        if self.offline_truth_alignment is not None:
            return _json_ready(dict(self.offline_truth_alignment))
        label_count = len(self.offline_truth_labels)
        return {
            "schema_version": D1_OFFLINE_TRUTH_ALIGNMENT_SCHEMA_VERSION,
            "source_schema_version": "direct_frozen_replay_case",
            "matching_policy": "caller_supplied_prealigned_labels",
            "availability": "complete" if label_count else "unavailable",
            "truth_metrics_input_available": bool(label_count),
            "source_sample_count": label_count,
            "matched_sample_count": label_count,
            "unmatched_sample_count": 0,
            "unmatched_reason_counts": {},
            "unmatched_samples": [],
            "online_truth_injected": False,
        }


@dataclass(slots=True)
class P1IdentityCalibrationReport:
    """JSON-ready screening, confirmation, and admission result."""

    screening: dict[str, Any]
    confirmation: dict[str, Any]
    jpda_comparison: dict[str, Any]
    decision: dict[str, Any]
    matrix_definition: dict[str, Any]
    difficulty_results: dict[str, Any]
    schema_version: str = P1_IDENTITY_MATRIX_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_online_path": "GNNHungarianAssociator",
            "default_online_path_changed": False,
            "matrix_definition": _json_ready(self.matrix_definition),
            "screening": _json_ready(self.screening),
            "confirmation": _json_ready(self.confirmation),
            "jpda_comparison": _json_ready(self.jpda_comparison),
            "decision": _json_ready(self.decision),
            "difficulty_results": _json_ready(self.difficulty_results),
        }


def fixed_identity_calibration_matrix() -> tuple[IdentityMatrixConfig, ...]:
    """Return all 54 fixed GNN/Hungarian configurations."""

    return tuple(
        IdentityMatrixConfig(
            gate_threshold=gate,
            quality_aware_gate=quality_aware,
            lost_miss_threshold=lost_threshold,
            drop_miss_threshold=drop_threshold,
            motion_weight_multiplier=motion_multiplier,
        )
        for gate in GATE_THRESHOLDS
        for quality_aware in QUALITY_AWARE_OPTIONS
        for lost_threshold, drop_threshold in LIFECYCLE_OPTIONS
        for motion_multiplier in MOTION_WEIGHT_MULTIPLIERS
    )


def run_p1_identity_calibration(
    screening_cases: Sequence[FrozenReplayCase],
    *,
    confirmation_cases: Sequence[FrozenReplayCase] | None = None,
    frozen_p95_loop_latency_budget_s: float,
) -> P1IdentityCalibrationReport:
    """Run 10-seed screening and optional 20-seed confirmation.

    Insufficient input is reported as unavailable.  The function never fills
    missing AirSim evidence with a synthetic fixture.
    """

    if (
        not np.isfinite(frozen_p95_loop_latency_budget_s)
        or frozen_p95_loop_latency_budget_s <= 0.0
    ):
        raise ValueError("frozen_p95_loop_latency_budget_s must be positive")

    matrix = fixed_identity_calibration_matrix()
    screening = _run_gnn_stage(
        screening_cases,
        required_seed_count=10,
        stage="screening_10_seed",
        configs=matrix,
    )
    best_config = _config_from_stage(screening)
    jpda_screening = _run_jpda_stage(
        screening_cases,
        required_seed_count=10,
        stage="jpda_screening_10_seed",
        best_config=best_config,
    )

    confirmation_input = tuple(confirmation_cases or ())
    confirmation = _run_gnn_stage(
        confirmation_input,
        required_seed_count=20,
        stage="confirmation_20_seed",
        configs=(baseline_identity_config(), best_config)
        if best_config is not None
        else (),
    )
    jpda_confirmation = _run_jpda_stage(
        confirmation_input,
        required_seed_count=20,
        stage="jpda_confirmation_20_seed",
        best_config=best_config,
    )

    decision = _admission_decision(
        confirmation,
        jpda_confirmation,
        latency_budget_s=float(frozen_p95_loop_latency_budget_s),
    )
    difficulty_results = {
        "screening": _difficulty_stage_summary(
            screening, jpda_screening, decision_by_difficulty=None
        ),
        "confirmation": _difficulty_stage_summary(
            confirmation,
            jpda_confirmation,
            decision_by_difficulty=decision.get("by_difficulty"),
        ),
    }
    return P1IdentityCalibrationReport(
        screening=screening,
        confirmation=confirmation,
        jpda_comparison={
            "screening": jpda_screening,
            "confirmation": jpda_confirmation,
            "same_budget_p95_loop_latency_s": float(
                frozen_p95_loop_latency_budget_s
            ),
            "research_adapter_only": True,
        },
        decision=decision,
        difficulty_results=difficulty_results,
        matrix_definition={
            "configuration_count": len(matrix),
            "gate_thresholds": list(GATE_THRESHOLDS),
            "quality_aware_gate": list(QUALITY_AWARE_OPTIONS),
            "lifecycle_lost_drop": [list(value) for value in LIFECYCLE_OPTIONS],
            "motion_weight_multipliers": list(MOTION_WEIGHT_MULTIPLIERS),
            "baseline": baseline_identity_config().to_dict(),
            "screening_required_seed_count": 10,
            "confirmation_required_seed_count": 20,
            "scenario_difficulties": {
                name: _json_ready(metadata)
                for name, metadata in _SCENARIO_DIFFICULTY_METADATA.items()
            },
            "seed_identity_key": ["scenario_difficulty", "seed"],
        },
    )


def baseline_identity_config() -> IdentityMatrixConfig:
    return IdentityMatrixConfig(
        gate_threshold=9.21,
        quality_aware_gate=True,
        lost_miss_threshold=2,
        drop_miss_threshold=5,
        motion_weight_multiplier=1.0,
    )


def scenario_difficulty_metadata(scenario_difficulty: str) -> dict[str, Any]:
    """Return the canonical, generation-independent metadata for one tier."""

    normalized = _normalize_scenario_difficulty(scenario_difficulty)
    return {
        "scenario_difficulty": normalized,
        "canonical_profile": _json_ready(
            _SCENARIO_DIFFICULTY_METADATA[normalized]
        ),
    }


def load_identity_calibration_manifest(
    path: str | Path,
) -> tuple[tuple[FrozenReplayCase, ...], float | None]:
    """Load versioned replay/truth pairs without creating fallback evidence."""

    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text())
    if payload.get("schema_version") != P1_IDENTITY_INPUT_SCHEMA_VERSION:
        raise ValueError("unsupported identity calibration manifest schema")
    evidence_source = str(payload.get("evidence_source", "")).strip()
    if not evidence_source:
        raise ValueError("manifest evidence_source must not be empty")
    cases: list[FrozenReplayCase] = []
    default_difficulty = payload.get("scenario_difficulty", "nominal")
    default_difficulty_metadata = payload.get("difficulty_metadata")
    for item in payload.get("cases", []):
        replay_path = _resolve_manifest_path(manifest_path, item["replay_path"])
        truth_path = _resolve_manifest_path(manifest_path, item["truth_path"])
        frames = tuple(load_airsim_replay_frames(replay_path))
        labels, alignment = _load_manifest_truth_sidecar(
            truth_path,
            frames=frames,
        )
        case = FrozenReplayCase(
            seed=int(item["seed"]),
            replay_name=str(item.get("replay_name", replay_path.stem)),
            frames=frames,
            offline_truth_labels=tuple(labels),
            evidence_source=evidence_source,
            scenario_difficulty=str(
                item.get("scenario_difficulty", default_difficulty)
            ),
            difficulty_metadata=item.get(
                "difficulty_metadata", default_difficulty_metadata
            ),
            offline_truth_alignment=alignment,
        )
        spacing_validation = case.target_spacing_provenance
        if not spacing_validation["valid"]:
            raise ValueError(
                "invalid target spacing provenance for "
                f"({case.normalized_scenario_difficulty}, {case.seed}): "
                f"{spacing_validation['reason']}"
            )
        cases.append(case)
    budget = payload.get("frozen_p95_loop_latency_budget_s")
    return tuple(cases), None if budget is None else float(budget)


def write_p1_identity_calibration_report(
    path: str | Path,
    report: P1IdentityCalibrationReport,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _run_gnn_stage(
    cases: Sequence[FrozenReplayCase],
    *,
    required_seed_count: int,
    stage: str,
    configs: Sequence[IdentityMatrixConfig],
) -> dict[str, Any]:
    validation = _validate_cases(cases, required_seed_count=required_seed_count)
    if not validation["available"] or not configs:
        reason = validation["unavailable_reason"]
        if not configs and reason is None:
            reason = "screening_best_gnn_unavailable"
        return {
            **validation,
            "stage": stage,
            "results": [],
            "best_config_id": None,
            "baseline_config_id": baseline_identity_config().config_id,
            "unavailable_reason": reason,
        }

    unique_configs = {config.config_id: config for config in configs}
    rows = [
        _run_associator_config(
            cases,
            config=config,
            associator_name="gnn",
        )
        for config in unique_configs.values()
    ]
    ranked = sorted(rows, key=_gnn_rank_key)
    return {
        **validation,
        "stage": stage,
        "configuration_count": len(rows),
        "results": rows,
        "best_config_id": ranked[0]["config"]["config_id"],
        "baseline_config_id": baseline_identity_config().config_id,
        "frozen_input_digest": _suite_digest(cases),
        "all_configurations_used_same_frozen_input": len(
            {row["frozen_input_digest"] for row in rows}
        )
        == 1,
        "discrimination_by_difficulty": _discrimination_by_difficulty(rows),
    }


def _run_jpda_stage(
    cases: Sequence[FrozenReplayCase],
    *,
    required_seed_count: int,
    stage: str,
    best_config: IdentityMatrixConfig | None,
) -> dict[str, Any]:
    validation = _validate_cases(cases, required_seed_count=required_seed_count)
    if best_config is None or not validation["available"]:
        reason = validation["unavailable_reason"]
        if best_config is None and reason is None:
            reason = "screening_best_gnn_unavailable"
        return {
            **validation,
            "stage": stage,
            "executed": False,
            "unavailable_reason": reason,
            "result": None,
        }
    return {
        **validation,
        "stage": stage,
        "executed": True,
        "unavailable_reason": None,
        "result": _run_associator_config(
            cases,
            config=best_config,
            associator_name="jpda",
        ),
    }


def _run_associator_config(
    cases: Sequence[FrozenReplayCase],
    *,
    config: IdentityMatrixConfig,
    associator_name: str,
) -> dict[str, Any]:
    per_seed: list[dict[str, Any]] = []
    for case in sorted(
        cases,
        key=lambda value: (
            SCENARIO_DIFFICULTIES.index(value.normalized_scenario_difficulty),
            value.seed,
        ),
    ):
        clean_frames = strip_offline_truth_from_frames(case.frames)
        if associator_name == "gnn":
            associator = GNNHungarianAssociator(
                gate_threshold=config.gate_threshold,
                motion_weight=config.motion_weight,
                quality_aware_gate=config.quality_aware_gate,
            )
        elif associator_name == "jpda":
            associator = JPDAAssociator(gate_threshold=config.gate_threshold)
        else:
            raise ValueError(f"unsupported associator_name: {associator_name}")
        tracker = Tracker(
            associator=associator,
            truth_policy=TrackerTruthPolicy.ONLINE,
            lost_miss_threshold=config.lost_miss_threshold,
            drop_miss_threshold=config.drop_miss_threshold,
        )
        report = run_airsim_replay_association(
            clean_frames,
            replay_name=f"{case.replay_name}-{associator_name}-{config.config_id}",
            tracker=tracker,
            offline_truth_labels=case.offline_truth_labels,
        )
        metrics = report.metrics
        loop_latencies = [
            float(log["runtime_seconds"]) for log in report.association_logs
        ]
        per_seed.append(
            {
                "seed": case.seed,
                "replay_name": case.replay_name,
                "evidence_source": case.evidence_source,
                "scenario_difficulty": case.normalized_scenario_difficulty,
                "scenario_difficulty_metadata": (
                    case.scenario_difficulty_metadata
                ),
                "target_spacing_provenance": case.target_spacing_provenance,
                "offline_truth_alignment": case.offline_truth_alignment_summary,
                "input_digest": case.input_digest,
                "frame_count": report.frame_count,
                "id_switch_count": _available_metric(
                    metrics, "id_switch_count", "truth_metrics_available", int
                ),
                "identity_continuity": _available_metric(
                    metrics, "identity_continuity", "continuity_available", float
                ),
                "coverage_continuity": _available_metric(
                    metrics, "coverage_continuity", "continuity_available", float
                ),
                "false_track_count": _available_metric(
                    metrics, "false_track_count", "truth_metrics_available", int
                ),
                "false_track_rate": _available_metric(
                    metrics, "false_track_rate", "truth_metrics_available", float
                ),
                "rmse": _available_metric(
                    metrics, "rmse", "truth_metrics_available", float
                ),
                "mean_initialization_latency_s": _available_metric(
                    metrics,
                    "mean_initialization_latency_s",
                    "truth_metrics_available",
                    float,
                ),
                "nis_available": bool(metrics.get("nis", {}).get("available", False)),
                "nees_available": bool(
                    metrics.get("nees", {}).get("available", False)
                ),
                "p95_loop_latency_s": (
                    float(np.percentile(loop_latencies, 95.0))
                    if loop_latencies
                    else None
                ),
                "online_truth_leakage_count": int(
                    metrics.get("online_truth_isolation_violations", 0)
                ),
            }
        )
    return {
        "associator": (
            "GNNHungarianAssociator"
            if associator_name == "gnn"
            else "JPDAAssociatorResearchAdapter"
        ),
        "config": config.to_dict(),
        "frozen_input_digest": _suite_digest(cases),
        "per_seed": per_seed,
        "aggregate": _aggregate_runs(per_seed),
        "aggregate_by_difficulty": _aggregate_runs_by_difficulty(per_seed),
    }


def _aggregate_runs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metric_keys = (
        "id_switch_count",
        "identity_continuity",
        "coverage_continuity",
        "false_track_count",
        "false_track_rate",
        "rmse",
        "mean_initialization_latency_s",
        "p95_loop_latency_s",
    )
    aggregate = {
        key: _distribution(row.get(key) for row in rows) for key in metric_keys
    }
    aggregate.update(
        {
            "seed_count": len(rows),
            "nis_available_seed_count": sum(
                bool(row.get("nis_available", False)) for row in rows
            ),
            "nees_available_seed_count": sum(
                bool(row.get("nees_available", False)) for row in rows
            ),
            "online_truth_leakage_count": sum(
                int(row.get("online_truth_leakage_count", 0)) for row in rows
            ),
            "offline_truth_alignment_availability_counts": dict(
                sorted(
                    {
                        availability: sum(
                            row.get("offline_truth_alignment", {}).get(
                                "availability", "unavailable"
                            )
                            == availability
                            for row in rows
                        )
                        for availability in ("complete", "partial", "unavailable")
                    }.items()
                )
            ),
            "offline_truth_source_sample_count": sum(
                int(
                    row.get("offline_truth_alignment", {}).get(
                        "source_sample_count", 0
                    )
                )
                for row in rows
            ),
            "offline_truth_matched_sample_count": sum(
                int(
                    row.get("offline_truth_alignment", {}).get(
                        "matched_sample_count", 0
                    )
                )
                for row in rows
            ),
            "offline_truth_unmatched_sample_count": sum(
                int(
                    row.get("offline_truth_alignment", {}).get(
                        "unmatched_sample_count", 0
                    )
                )
                for row in rows
            ),
        }
    )
    return aggregate


def _aggregate_runs_by_difficulty(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        difficulty = _normalize_scenario_difficulty(
            str(row.get("scenario_difficulty", "nominal"))
        )
        grouped.setdefault(difficulty, []).append(row)
    return {
        difficulty: _aggregate_runs(grouped[difficulty])
        for difficulty in SCENARIO_DIFFICULTIES
        if difficulty in grouped
    }


def _admission_decision(
    confirmation: Mapping[str, Any],
    jpda_confirmation: Mapping[str, Any],
    *,
    latency_budget_s: float,
) -> dict[str, Any]:
    policy = _admission_policy(latency_budget_s)
    if not confirmation.get("available", False):
        return {
            "available": False,
            "unavailable_reason": confirmation.get("unavailable_reason"),
            "selected_online_path": "baseline_gnn_hungarian",
            "default_online_path_changed": False,
            "promotion_recommended": False,
            "candidate_assessments": [],
            "by_difficulty": {},
            "policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
            "policy": policy,
        }
    rows = list(confirmation.get("results", []))
    baseline = next(
        (row for row in rows if row.get("config", {}).get("is_baseline")), None
    )
    candidates = [row for row in rows if row is not baseline]
    if jpda_confirmation.get("executed", False):
        candidates.append(jpda_confirmation["result"])
    if baseline is None:
        return {
            "available": False,
            "unavailable_reason": "baseline_confirmation_result_missing",
            "selected_online_path": "baseline_gnn_hungarian",
            "default_online_path_changed": False,
            "promotion_recommended": False,
            "candidate_assessments": [],
            "by_difficulty": {},
            "policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
            "policy": policy,
        }
    assessments = [
        _assess_candidate(candidate, baseline, latency_budget_s=latency_budget_s)
        for candidate in candidates
    ]
    difficulty_assessments = _admission_by_difficulty(
        baseline,
        candidates,
        latency_budget_s=latency_budget_s,
    )
    passing = [item for item in assessments if item["all_thresholds_passed"]]
    return {
        "available": True,
        "unavailable_reason": None,
        "selected_online_path": "baseline_gnn_hungarian",
        "default_online_path_changed": False,
        "promotion_recommended": bool(passing),
        "promotion_candidates": [item["candidate_id"] for item in passing],
        "candidate_assessments": assessments,
        "by_difficulty": difficulty_assessments,
        "policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
        "policy": policy,
        "note": "passing only recommends review; this runner never changes mainline",
    }


def _admission_policy(latency_budget_s: float) -> dict[str, Any]:
    return {
        "policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
        "minimum_id_switch_reduction_fraction": (
            MINIMUM_ID_SWITCH_REDUCTION_FRACTION
        ),
        "identity_continuity": {
            "theoretical_upper_bound": (
                IDENTITY_CONTINUITY_THEORETICAL_UPPER_BOUND
            ),
            "minimum_error_reduction_fraction": (
                MINIMUM_CONTINUITY_ERROR_REDUCTION_FRACTION
            ),
            "required_increase_formula": (
                "min(legacy_absolute_increase, "
                "baseline_headroom * minimum_error_reduction_fraction)"
            ),
            "baseline_headroom_formula": "1.0 - baseline_identity_continuity",
            "error_reduction_fraction_formula": (
                "(candidate_identity_continuity - baseline_identity_continuity) "
                "/ baseline_headroom"
            ),
            "no_headroom_rule": (
                "when baseline is 1.0, candidate must be valid and non-degrading"
            ),
            "legacy_absolute_increase": (
                LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE
            ),
            "legacy_absolute_increase_status": (
                "deprecated_v1_direct_gate_not_used_for_v2_admission"
            ),
        },
        # Kept only so v1 report consumers can identify the old frozen value.
        "minimum_identity_continuity_increase": (
            LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE
        ),
        "minimum_identity_continuity_increase_status": (
            "legacy_deprecated_not_used_for_v2_admission"
        ),
        "maximum_false_track_increase_fraction": (
            MAXIMUM_FALSE_TRACK_INCREASE_FRACTION
        ),
        "maximum_p95_loop_latency_s": latency_budget_s,
        "required_online_truth_leakage_count": 0,
        "promotion_effect": "review_recommendation_only",
        "default_online_path_changed": False,
    }


def _admission_by_difficulty(
    baseline: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    latency_budget_s: float,
) -> dict[str, Any]:
    baseline_by_difficulty = baseline.get("aggregate_by_difficulty", {})
    result: dict[str, Any] = {}
    for difficulty in SCENARIO_DIFFICULTIES:
        baseline_aggregate = baseline_by_difficulty.get(difficulty)
        if baseline_aggregate is None:
            continue
        baseline_row = {**baseline, "aggregate": baseline_aggregate}
        assessments: list[dict[str, Any]] = []
        comparison_rows = [baseline_row]
        for candidate in candidates:
            candidate_aggregate = candidate.get("aggregate_by_difficulty", {}).get(
                difficulty
            )
            if candidate_aggregate is None:
                continue
            candidate_row = {**candidate, "aggregate": candidate_aggregate}
            comparison_rows.append(candidate_row)
            assessments.append(
                _assess_candidate(
                    candidate_row,
                    baseline_row,
                    latency_budget_s=latency_budget_s,
                )
            )
        discrimination = _discrimination_assessment(comparison_rows)
        passing = [item for item in assessments if item["all_thresholds_passed"]]
        result[difficulty] = {
            "available": True,
            "scenario_still_non_discriminative": discrimination[
                "scenario_still_non_discriminative"
            ],
            "discrimination": discrimination,
            "promotion_recommended": bool(passing)
            and not discrimination["scenario_still_non_discriminative"],
            "promotion_candidates": [item["candidate_id"] for item in passing]
            if not discrimination["scenario_still_non_discriminative"]
            else [],
            "candidate_assessments": assessments,
        }
    return result


def _difficulty_stage_summary(
    gnn_stage: Mapping[str, Any],
    jpda_stage: Mapping[str, Any],
    *,
    decision_by_difficulty: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not gnn_stage.get("available", False):
        return {
            "available": False,
            "unavailable_reason": gnn_stage.get("unavailable_reason"),
            "by_difficulty": {},
        }
    rows = list(gnn_stage.get("results", []))
    baseline = next(
        (row for row in rows if row.get("config", {}).get("is_baseline")), None
    )
    best_id = gnn_stage.get("best_config_id")
    best = next(
        (row for row in rows if row.get("config", {}).get("config_id") == best_id),
        None,
    )
    jpda = jpda_stage.get("result") if jpda_stage.get("executed", False) else None
    by_difficulty: dict[str, Any] = {}
    for difficulty in gnn_stage.get("scenario_difficulties", []):
        algorithm_rows = _unique_algorithm_rows(
            row
            for row in (baseline, best, jpda)
            if row is not None
            and difficulty in row.get("aggregate_by_difficulty", {})
        )
        discrimination = _discrimination_assessment(
            [
                {**row, "aggregate": row["aggregate_by_difficulty"][difficulty]}
                for row in algorithm_rows
            ]
        )
        by_difficulty[difficulty] = {
            "scenario_difficulty_metadata": gnn_stage.get(
                "scenario_difficulty_metadata", {}
            ).get(difficulty),
            "seed_count": gnn_stage.get("seed_count_by_difficulty", {}).get(
                difficulty, 0
            ),
            "baseline_gnn": _algorithm_difficulty_summary(baseline, difficulty),
            "best_gnn": _algorithm_difficulty_summary(best, difficulty),
            "jpda_research_adapter": _algorithm_difficulty_summary(
                jpda, difficulty
            ),
            "discrimination": discrimination,
            "scenario_still_non_discriminative": discrimination[
                "scenario_still_non_discriminative"
            ],
            "admission": (decision_by_difficulty or {}).get(difficulty),
        }
    return {"available": True, "unavailable_reason": None, "by_difficulty": by_difficulty}


def _algorithm_difficulty_summary(
    row: Mapping[str, Any] | None, difficulty: str
) -> dict[str, Any] | None:
    if row is None:
        return None
    aggregate = row.get("aggregate_by_difficulty", {}).get(difficulty)
    if aggregate is None:
        return None
    return {
        "associator": row.get("associator"),
        "config_id": row.get("config", {}).get("config_id"),
        "metrics": {
            key: _json_ready(aggregate.get(key))
            for key in (
                "id_switch_count",
                "identity_continuity",
                "false_track_count",
                "false_track_rate",
                "rmse",
                "p95_loop_latency_s",
            )
        },
        "online_truth_leakage_count": int(
            aggregate.get("online_truth_leakage_count", 0)
        ),
        "offline_truth_alignment": {
            "availability_counts": _json_ready(
                aggregate.get("offline_truth_alignment_availability_counts", {})
            ),
            "source_sample_count": int(
                aggregate.get("offline_truth_source_sample_count", 0)
            ),
            "matched_sample_count": int(
                aggregate.get("offline_truth_matched_sample_count", 0)
            ),
            "unmatched_sample_count": int(
                aggregate.get("offline_truth_unmatched_sample_count", 0)
            ),
        },
        "nis_nees_availability": {
            "seed_count": int(aggregate.get("seed_count", 0)),
            "nis_available_seed_count": int(
                aggregate.get("nis_available_seed_count", 0)
            ),
            "nees_available_seed_count": int(
                aggregate.get("nees_available_seed_count", 0)
            ),
        },
    }


def _discrimination_by_difficulty(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for difficulty in SCENARIO_DIFFICULTIES:
        difficulty_rows = [
            {**row, "aggregate": row["aggregate_by_difficulty"][difficulty]}
            for row in rows
            if difficulty in row.get("aggregate_by_difficulty", {})
        ]
        if difficulty_rows:
            result[difficulty] = _discrimination_assessment(difficulty_rows)
    return result


def _discrimination_assessment(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    idsw_values = [
        _mean(row.get("aggregate", {}), "id_switch_count") for row in rows
    ]
    continuity_values = [
        _mean(row.get("aggregate", {}), "identity_continuity") for row in rows
    ]
    metrics_available = bool(rows) and all(
        value is not None for value in (*idsw_values, *continuity_values)
    )
    all_zero_idsw = metrics_available and all(
        np.isclose(float(value), 0.0) for value in idsw_values
    )
    all_perfect_continuity = metrics_available and all(
        np.isclose(float(value), 1.0) for value in continuity_values
    )
    non_discriminative = bool(
        len(rows) >= 2 and all_zero_idsw and all_perfect_continuity
    )
    return {
        "available": metrics_available,
        "algorithm_count": len(rows),
        "all_algorithms_zero_id_switch": bool(all_zero_idsw),
        "all_algorithms_perfect_identity_continuity": bool(
            all_perfect_continuity
        ),
        "scenario_still_non_discriminative": non_discriminative,
        "reason": (
            "all_evaluated_algorithms_have_zero_idsw_and_perfect_continuity"
            if non_discriminative
            else None
        ),
    }


def _unique_algorithm_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    unique: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("associator", "")),
            str(row.get("config", {}).get("config_id", "")),
        )
        unique[key] = row
    return list(unique.values())


def _assess_candidate(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    latency_budget_s: float,
) -> dict[str, Any]:
    candidate_aggregate = candidate["aggregate"]
    baseline_aggregate = baseline["aggregate"]
    candidate_idsw = _mean(candidate_aggregate, "id_switch_count")
    baseline_idsw = _mean(baseline_aggregate, "id_switch_count")
    candidate_continuity = _mean(candidate_aggregate, "identity_continuity")
    baseline_continuity = _mean(baseline_aggregate, "identity_continuity")
    candidate_false_tracks = _mean(candidate_aggregate, "false_track_count")
    baseline_false_tracks = _mean(baseline_aggregate, "false_track_count")
    candidate_latency = _p95_across_seed_p95(candidate)
    idsw_gate = _id_switch_admission_gate(candidate_idsw, baseline_idsw)
    continuity_gate = _continuity_admission_gate(
        candidate_continuity, baseline_continuity
    )
    false_track_gate = _false_track_admission_gate(
        candidate_false_tracks, baseline_false_tracks
    )
    latency_gate = _latency_admission_gate(candidate_latency, latency_budget_s)
    truth_leakage_gate = _truth_leakage_admission_gate(
        candidate_aggregate, baseline_aggregate
    )
    gates = {
        "id_switch_reduction": idsw_gate,
        "identity_continuity_ceiling_aware": continuity_gate,
        "false_track_limit": false_track_gate,
        "p95_loop_latency_budget": latency_gate,
        "truth_leakage_zero": truth_leakage_gate,
    }
    checks = {name: bool(gate["passed"]) for name, gate in gates.items()}
    return {
        "candidate_id": candidate["config"]["config_id"]
        if candidate["associator"] == "GNNHungarianAssociator"
        else "jpda-on-" + candidate["config"]["config_id"],
        "associator": candidate["associator"],
        "admission_policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
        "baseline_id_switch_mean": baseline_idsw,
        "candidate_id_switch_mean": candidate_idsw,
        "id_switch_reduction_fraction": idsw_gate["actual_reduction_fraction"],
        "baseline_identity_continuity": baseline_continuity,
        "candidate_identity_continuity": candidate_continuity,
        "identity_continuity_baseline_headroom": continuity_gate[
            "baseline_headroom"
        ],
        "identity_continuity_increase": continuity_gate["actual_increase"],
        "identity_continuity_required_increase": continuity_gate[
            "required_increase"
        ],
        "identity_continuity_headroom_reduction_fraction": continuity_gate[
            "headroom_reduction_fraction"
        ],
        "identity_continuity_error_reduction_fraction": continuity_gate[
            "headroom_reduction_fraction"
        ],
        "candidate_false_track_mean": candidate_false_tracks,
        "baseline_false_track_mean": baseline_false_tracks,
        "false_track_mean_limit": false_track_gate["maximum_candidate_mean"],
        "candidate_p95_loop_latency_s": candidate_latency,
        "gates": gates,
        "checks": checks,
        "gate_reasons": {
            name: str(gate["reason"]) for name, gate in gates.items()
        },
        "legacy_v1_identity_continuity_gate": {
            "minimum_absolute_increase": (
                LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE
            ),
            "passed": bool(
                continuity_gate["actual_increase"] is not None
                and continuity_gate["actual_increase"]
                >= LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE
            ),
            "status": "deprecated_not_used_for_v2_admission",
            "used_for_admission": False,
        },
        "all_thresholds_passed": all(checks.values()),
    }


def _id_switch_admission_gate(
    candidate_idsw: float | None,
    baseline_idsw: float | None,
) -> dict[str, Any]:
    result = {
        "passed": False,
        "reason": "metric_unavailable",
        "baseline_mean": baseline_idsw,
        "candidate_mean": candidate_idsw,
        "actual_reduction_fraction": None,
        "required_reduction_fraction": MINIMUM_ID_SWITCH_REDUCTION_FRACTION,
    }
    if not _is_finite_nonnegative(baseline_idsw) or not _is_finite_nonnegative(
        candidate_idsw
    ):
        result["reason"] = _metric_pair_reason(
            baseline_idsw, candidate_idsw, lower=0.0, upper=None
        )
        return result
    if baseline_idsw <= _ADMISSION_NUMERICAL_TOLERANCE:
        result["reason"] = "baseline_zero_no_measurable_reduction_evidence"
        return result
    reduction = (baseline_idsw - candidate_idsw) / baseline_idsw
    result["actual_reduction_fraction"] = float(reduction)
    if reduction + _ADMISSION_NUMERICAL_TOLERANCE < (
        MINIMUM_ID_SWITCH_REDUCTION_FRACTION
    ):
        result["reason"] = "insufficient_id_switch_reduction"
        return result
    result.update(passed=True, reason="required_id_switch_reduction_met")
    return result


def _continuity_admission_gate(
    candidate_continuity: float | None,
    baseline_continuity: float | None,
) -> dict[str, Any]:
    result = {
        "passed": False,
        "reason": "metric_unavailable",
        "policy_version": P1_IDENTITY_ADMISSION_POLICY_VERSION,
        "theoretical_upper_bound": IDENTITY_CONTINUITY_THEORETICAL_UPPER_BOUND,
        "baseline": baseline_continuity,
        "candidate": candidate_continuity,
        "baseline_headroom": None,
        "actual_increase": None,
        "required_increase": None,
        "headroom_reduction_fraction": None,
        "minimum_headroom_reduction_fraction": (
            MINIMUM_CONTINUITY_ERROR_REDUCTION_FRACTION
        ),
    }
    if not _is_finite_bounded(baseline_continuity, 0.0, 1.0) or not (
        _is_finite_bounded(candidate_continuity, 0.0, 1.0)
    ):
        result["reason"] = _metric_pair_reason(
            baseline_continuity,
            candidate_continuity,
            lower=0.0,
            upper=IDENTITY_CONTINUITY_THEORETICAL_UPPER_BOUND,
        )
        return result

    headroom = max(
        0.0, IDENTITY_CONTINUITY_THEORETICAL_UPPER_BOUND - baseline_continuity
    )
    actual_increase = candidate_continuity - baseline_continuity
    required_increase = min(
        LEGACY_MINIMUM_IDENTITY_CONTINUITY_INCREASE,
        headroom * MINIMUM_CONTINUITY_ERROR_REDUCTION_FRACTION,
    )
    reduction_fraction = (
        actual_increase / headroom
        if headroom > _ADMISSION_NUMERICAL_TOLERANCE
        else None
    )
    result.update(
        baseline_headroom=float(headroom),
        actual_increase=float(actual_increase),
        required_increase=float(required_increase),
        headroom_reduction_fraction=(
            None if reduction_fraction is None else float(reduction_fraction)
        ),
    )
    if actual_increase < -_ADMISSION_NUMERICAL_TOLERANCE:
        result["reason"] = "identity_continuity_degraded"
        return result
    if actual_increase + _ADMISSION_NUMERICAL_TOLERANCE < required_increase:
        result["reason"] = "insufficient_continuity_error_reduction"
        return result
    result.update(
        passed=True,
        reason=(
            "no_baseline_headroom_and_candidate_non_degrading"
            if headroom <= _ADMISSION_NUMERICAL_TOLERANCE
            else "required_continuity_error_reduction_met"
        ),
    )
    return result


def _false_track_admission_gate(
    candidate_false_tracks: float | None,
    baseline_false_tracks: float | None,
) -> dict[str, Any]:
    result = {
        "passed": False,
        "reason": "metric_unavailable",
        "baseline_mean": baseline_false_tracks,
        "candidate_mean": candidate_false_tracks,
        "maximum_increase_fraction": MAXIMUM_FALSE_TRACK_INCREASE_FRACTION,
        "maximum_candidate_mean": None,
    }
    if not _is_finite_nonnegative(
        baseline_false_tracks
    ) or not _is_finite_nonnegative(candidate_false_tracks):
        result["reason"] = _metric_pair_reason(
            baseline_false_tracks,
            candidate_false_tracks,
            lower=0.0,
            upper=None,
        )
        return result
    limit = baseline_false_tracks * (1.0 + MAXIMUM_FALSE_TRACK_INCREASE_FRACTION)
    result["maximum_candidate_mean"] = float(limit)
    if candidate_false_tracks > limit + _ADMISSION_NUMERICAL_TOLERANCE:
        result["reason"] = "false_track_growth_exceeds_limit"
        return result
    result.update(passed=True, reason="false_track_limit_met")
    return result


def _latency_admission_gate(
    candidate_latency: float | None,
    latency_budget_s: float,
) -> dict[str, Any]:
    result = {
        "passed": False,
        "reason": "metric_unavailable",
        "candidate_p95_loop_latency_s": candidate_latency,
        "maximum_p95_loop_latency_s": latency_budget_s,
    }
    if not _is_finite_nonnegative(candidate_latency):
        result["reason"] = _metric_reason(
            candidate_latency, role="candidate", lower=0.0, upper=None
        )
        return result
    if candidate_latency > latency_budget_s + _ADMISSION_NUMERICAL_TOLERANCE:
        result["reason"] = "p95_loop_latency_budget_exceeded"
        return result
    result.update(passed=True, reason="p95_loop_latency_budget_met")
    return result


def _truth_leakage_admission_gate(
    candidate_aggregate: Mapping[str, Any],
    baseline_aggregate: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = candidate_aggregate.get("online_truth_leakage_count")
    baseline = baseline_aggregate.get("online_truth_leakage_count")
    result = {
        "passed": False,
        "reason": "metric_unavailable",
        "baseline_count": baseline,
        "candidate_count": candidate,
        "required_count": 0,
    }
    if not _is_nonnegative_integer_count(baseline):
        result["reason"] = _metric_reason(
            baseline, role="baseline", lower=0.0, upper=None
        )
        return result
    if not _is_nonnegative_integer_count(candidate):
        result["reason"] = _metric_reason(
            candidate, role="candidate", lower=0.0, upper=None
        )
        return result
    if int(baseline) != 0 or int(candidate) != 0:
        result["reason"] = "online_truth_leakage_detected"
        return result
    result.update(passed=True, reason="online_truth_leakage_zero")
    return result


def _is_finite_nonnegative(value: Any) -> bool:
    return _is_finite_bounded(value, 0.0, None)


def _is_finite_bounded(
    value: Any, lower: float | None, upper: float | None
) -> bool:
    if value is None or isinstance(value, (bool, np.bool_)):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(numeric):
        return False
    if lower is not None and numeric < lower - _ADMISSION_NUMERICAL_TOLERANCE:
        return False
    if upper is not None and numeric > upper + _ADMISSION_NUMERICAL_TOLERANCE:
        return False
    return True


def _is_nonnegative_integer_count(value: Any) -> bool:
    if not _is_finite_nonnegative(value):
        return False
    numeric = float(value)
    return bool(
        np.isclose(
            numeric,
            round(numeric),
            atol=_ADMISSION_NUMERICAL_TOLERANCE,
            rtol=0.0,
        )
    )


def _metric_pair_reason(
    baseline: Any,
    candidate: Any,
    *,
    lower: float | None,
    upper: float | None,
) -> str:
    if not _is_finite_bounded(baseline, lower, upper):
        return _metric_reason(
            baseline, role="baseline", lower=lower, upper=upper
        )
    return _metric_reason(candidate, role="candidate", lower=lower, upper=upper)


def _metric_reason(
    value: Any,
    *,
    role: str,
    lower: float | None,
    upper: float | None,
) -> str:
    if value is None:
        return f"{role}_metric_unavailable"
    if isinstance(value, (bool, np.bool_)):
        return f"{role}_metric_invalid_type"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return f"{role}_metric_invalid_type"
    if not np.isfinite(numeric):
        return f"{role}_metric_not_finite"
    if lower is not None and numeric < lower - _ADMISSION_NUMERICAL_TOLERANCE:
        return f"{role}_metric_below_valid_range"
    if upper is not None and numeric > upper + _ADMISSION_NUMERICAL_TOLERANCE:
        return f"{role}_metric_above_valid_range"
    return f"{role}_metric_invalid"


def _validate_cases(
    cases: Sequence[FrozenReplayCase], *, required_seed_count: int
) -> dict[str, Any]:
    seeds = [case.seed for case in cases]
    case_keys = [
        (case.normalized_scenario_difficulty, case.seed) for case in cases
    ]
    unique_seed_count = len(set(case_keys))
    sources = sorted({case.evidence_source for case in cases})
    seeds_by_difficulty: dict[str, set[int]] = {}
    governance_digests_by_difficulty: dict[str, set[str]] = {}
    spacing_validation_by_case: dict[str, dict[str, Any]] = {}
    truth_alignment_by_case: dict[str, dict[str, Any]] = {}
    for case in cases:
        difficulty = case.normalized_scenario_difficulty
        seeds_by_difficulty.setdefault(difficulty, set()).add(case.seed)
        governance_digests_by_difficulty.setdefault(difficulty, set()).add(
            _stable_digest(_difficulty_governance_signature(case))
        )
        spacing_validation_by_case[f"{difficulty}:{case.seed}"] = (
            case.target_spacing_provenance
        )
        truth_alignment_by_case[f"{difficulty}:{case.seed}"] = (
            case.offline_truth_alignment_summary
        )
    reason = None
    if len(case_keys) != unique_seed_count:
        reason = "duplicate_seed_in_frozen_replay_suite"
    elif any(
        not validation["valid"]
        for validation in spacing_validation_by_case.values()
    ):
        invalid_key = next(
            key
            for key, validation in spacing_validation_by_case.items()
            if not validation["valid"]
        )
        reason = (
            f"invalid_target_spacing_provenance:{invalid_key}:"
            f"{spacing_validation_by_case[invalid_key]['reason']}"
        )
    elif any(len(values) > 1 for values in governance_digests_by_difficulty.values()):
        inconsistent = sorted(
            difficulty
            for difficulty, values in governance_digests_by_difficulty.items()
            if len(values) > 1
        )
        reason = "inconsistent_scenario_difficulty_metadata:" + ",".join(inconsistent)
    elif seeds_by_difficulty and any(
        len(values) < required_seed_count for values in seeds_by_difficulty.values()
    ):
        reason = "insufficient_frozen_replay_seeds_by_difficulty:" + ",".join(
            f"{difficulty}={len(seeds_by_difficulty[difficulty])}<{required_seed_count}"
            for difficulty in SCENARIO_DIFFICULTIES
            if difficulty in seeds_by_difficulty
            and len(seeds_by_difficulty[difficulty]) < required_seed_count
        )
    elif not seeds_by_difficulty and unique_seed_count < required_seed_count:
        reason = (
            f"insufficient_frozen_replay_seeds:{unique_seed_count}"
            f"<{required_seed_count}"
        )
    return {
        "available": reason is None,
        "unavailable_reason": reason,
        "required_seed_count": required_seed_count,
        "provided_seed_count": unique_seed_count,
        "seeds": sorted(set(seeds)),
        "scenario_difficulties": [
            difficulty
            for difficulty in SCENARIO_DIFFICULTIES
            if difficulty in seeds_by_difficulty
        ],
        "seed_count_by_difficulty": {
            difficulty: len(seeds_by_difficulty[difficulty])
            for difficulty in SCENARIO_DIFFICULTIES
            if difficulty in seeds_by_difficulty
        },
        "scenario_difficulty_metadata": {
            difficulty: next(
                case.scenario_difficulty_metadata
                for case in cases
                if case.normalized_scenario_difficulty == difficulty
            )
            for difficulty in SCENARIO_DIFFICULTIES
            if difficulty in seeds_by_difficulty
        },
        "target_spacing_provenance_by_case": spacing_validation_by_case,
        "offline_truth_alignment_by_case": truth_alignment_by_case,
        "offline_truth_alignment_availability_counts": {
            availability: sum(
                summary.get("availability") == availability
                for summary in truth_alignment_by_case.values()
            )
            for availability in ("complete", "partial", "unavailable")
        },
        "offline_truth_unmatched_sample_count": sum(
            int(summary.get("unmatched_sample_count", 0))
            for summary in truth_alignment_by_case.values()
        ),
        "evidence_sources": sources,
        "airsim_evidence": bool(sources)
        and all(_is_real_airsim_evidence_source(source) for source in sources),
    }


def _is_real_airsim_evidence_source(source: str) -> bool:
    """Classify governed real-AirSim evidence without accepting synthetic labels."""

    normalized = source.strip().lower()
    return normalized == _LEGACY_AIRSIM_EVIDENCE_SOURCE or normalized.startswith(
        _REAL_AIRSIM_EVIDENCE_PREFIX
    )


def _case_target_spacing_provenance(
    case: FrozenReplayCase,
) -> dict[str, Any]:
    difficulty = case.normalized_scenario_difficulty
    expected = TARGET_SPACING_BY_DIFFICULTY_M[difficulty]
    values: list[tuple[str, float]] = []
    invalid_reason: str | None = None

    def add(source: str, value: Any) -> None:
        nonlocal invalid_reason
        if value is None or invalid_reason is not None:
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            invalid_reason = f"{source}_not_numeric"
            return
        if not np.isfinite(numeric) or numeric <= 0.0:
            invalid_reason = f"{source}_not_positive_finite"
            return
        values.append((source, numeric))

    declared = dict(case.difficulty_metadata or {})
    _collect_spacing_values(declared, prefix="difficulty_metadata", add=add)
    declared_difficulty = declared.get("scenario_difficulty")
    if declared_difficulty is not None:
        try:
            normalized_declared = _normalize_scenario_difficulty(
                str(declared_difficulty)
            )
        except ValueError:
            invalid_reason = "difficulty_metadata_scenario_difficulty_invalid"
        else:
            if normalized_declared != difficulty:
                invalid_reason = "difficulty_metadata_scenario_difficulty_mismatch"

    for frame_index, frame in enumerate(case.frames):
        metadata = frame.get("replay_metadata", {})
        if not isinstance(metadata, Mapping):
            invalid_reason = f"frame_{frame_index}_replay_metadata_not_mapping"
            break
        add(
            f"frame_{frame_index}.replay_metadata.target_spacing_m",
            metadata.get("target_spacing_m"),
        )
        stress = metadata.get("d2_offline_stress_profile")
        if stress is not None:
            if not isinstance(stress, Mapping):
                invalid_reason = f"frame_{frame_index}_stress_profile_not_mapping"
                break
            stress_difficulty = stress.get("scenario_difficulty")
            if stress_difficulty is not None:
                try:
                    normalized_stress = _normalize_scenario_difficulty(
                        str(stress_difficulty)
                    )
                except ValueError:
                    invalid_reason = f"frame_{frame_index}_stress_difficulty_invalid"
                    break
                if normalized_stress != difficulty:
                    invalid_reason = f"frame_{frame_index}_stress_difficulty_mismatch"
                    break
            _collect_spacing_values(
                stress,
                prefix=f"frame_{frame_index}.d2_offline_stress_profile",
                add=add,
            )

    if invalid_reason is not None:
        return {
            "valid": False,
            "reason": invalid_reason,
            "scenario_difficulty": difficulty,
            "expected_target_spacing_m": expected,
            "sources": [source for source, _ in values],
            "values_m": [value for _, value in values],
        }
    if not values:
        required = _is_real_airsim_evidence_source(case.evidence_source)
        return {
            "valid": not required,
            "reason": "missing_real_airsim_target_spacing_provenance" if required else None,
            "scenario_difficulty": difficulty,
            "expected_target_spacing_m": expected,
            "sources": [],
            "values_m": [],
            "availability": "required_missing" if required else "unavailable_optional",
        }
    reference = values[0][1]
    if any(not np.isclose(value, reference, atol=1.0e-6) for _, value in values[1:]):
        return {
            "valid": False,
            "reason": "inconsistent_target_spacing_provenance_values",
            "scenario_difficulty": difficulty,
            "expected_target_spacing_m": expected,
            "sources": [source for source, _ in values],
            "values_m": [value for _, value in values],
        }
    if abs(reference - expected) > TARGET_SPACING_TOLERANCE_M:
        return {
            "valid": False,
            "reason": "target_spacing_outside_difficulty_tolerance",
            "scenario_difficulty": difficulty,
            "expected_target_spacing_m": expected,
            "target_spacing_tolerance_m": TARGET_SPACING_TOLERANCE_M,
            "sources": [source for source, _ in values],
            "values_m": [value for _, value in values],
        }
    return {
        "valid": True,
        "reason": None,
        "availability": "available",
        "scenario_difficulty": difficulty,
        "expected_target_spacing_m": expected,
        "target_spacing_tolerance_m": TARGET_SPACING_TOLERANCE_M,
        "resolved_target_spacing_m": reference,
        "sources": [source for source, _ in values],
        "values_m": [value for _, value in values],
    }


def _collect_spacing_values(
    value: Mapping[str, Any],
    *,
    prefix: str,
    add: Any,
) -> None:
    for key in (
        "target_spacing_m",
        "declared_target_spacing_m",
        "captured_target_spacing_m",
        "target_lateral_spacing_m",
    ):
        if key in value:
            add(f"{prefix}.{key}", value.get(key))
    for nested_key in ("profile_metadata", "d2_offline_stress_profile"):
        nested = value.get(nested_key)
        if isinstance(nested, Mapping):
            _collect_spacing_values(
                nested,
                prefix=f"{prefix}.{nested_key}",
                add=add,
            )


def _difficulty_governance_signature(case: FrozenReplayCase) -> dict[str, Any]:
    declared = dict(case.difficulty_metadata or {})
    invariant_keys = (
        "schema_version",
        "profile_id",
        "profile_version",
        "fixture_version",
        "expected_target_spacing_m",
        "target_spacing_tolerance_m",
    )
    return {
        "scenario_difficulty": case.normalized_scenario_difficulty,
        "canonical_profile": _SCENARIO_DIFFICULTY_METADATA[
            case.normalized_scenario_difficulty
        ],
        "declared_invariants": {
            key: declared[key] for key in invariant_keys if key in declared
        },
    }


def _config_from_stage(stage: Mapping[str, Any]) -> IdentityMatrixConfig | None:
    best_id = stage.get("best_config_id")
    if best_id is None:
        return None
    for row in stage.get("results", []):
        if row["config"]["config_id"] == best_id:
            config = row["config"]
            return IdentityMatrixConfig(
                gate_threshold=float(config["gate_threshold"]),
                quality_aware_gate=bool(config["quality_aware_gate"]),
                lost_miss_threshold=int(config["lost_miss_threshold"]),
                drop_miss_threshold=int(config["drop_miss_threshold"]),
                motion_weight_multiplier=float(config["motion_weight_multiplier"]),
                base_motion_weight=float(config["base_motion_weight"]),
            )
    return None


def _gnn_rank_key(row: Mapping[str, Any]) -> tuple[float, ...]:
    aggregate = row["aggregate"]
    return (
        _mean_or_inf(aggregate, "id_switch_count"),
        -_mean_or_negative_inf(aggregate, "identity_continuity"),
        _mean_or_inf(aggregate, "false_track_count"),
        _mean_or_inf(aggregate, "p95_loop_latency_s"),
        0.0 if row["config"]["is_baseline"] else 1.0,
    )


def _suite_digest(cases: Sequence[FrozenReplayCase]) -> str:
    return _stable_digest(
        {
            "cases": [
                {
                    "scenario_difficulty": case.normalized_scenario_difficulty,
                    "seed": case.seed,
                    "input_digest": case.input_digest,
                }
                for case in sorted(
                    cases,
                    key=lambda value: (
                        SCENARIO_DIFFICULTIES.index(
                            value.normalized_scenario_difficulty
                        ),
                        value.seed,
                    ),
                )
            ]
        }
    )


def _normalize_scenario_difficulty(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in SCENARIO_DIFFICULTIES:
        raise ValueError(
            "scenario_difficulty must be one of " + ", ".join(SCENARIO_DIFFICULTIES)
        )
    return normalized


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _json_ready(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _distribution(values: Sequence[Any]) -> dict[str, Any]:
    available = [float(value) for value in values if value is not None]
    if not available:
        return {
            "available": False,
            "count": 0,
            "mean": None,
            "minimum": None,
            "maximum": None,
            "p95": None,
        }
    return {
        "available": True,
        "count": len(available),
        "mean": float(np.mean(available)),
        "minimum": float(np.min(available)),
        "maximum": float(np.max(available)),
        "p95": float(np.percentile(available, 95.0)),
    }


def _available_metric(
    metrics: Mapping[str, Any],
    metric_key: str,
    availability_key: str,
    converter: type[int] | type[float],
) -> int | float | None:
    if not bool(metrics.get(availability_key, False)):
        return None
    value = metrics.get(metric_key)
    return None if value is None else converter(value)


def _mean(aggregate: Mapping[str, Any], key: str) -> float | None:
    value = aggregate.get(key, {}).get("mean")
    return None if value is None else float(value)


def _mean_or_inf(aggregate: Mapping[str, Any], key: str) -> float:
    value = _mean(aggregate, key)
    return float("inf") if value is None else value


def _mean_or_negative_inf(aggregate: Mapping[str, Any], key: str) -> float:
    value = _mean(aggregate, key)
    return float("-inf") if value is None else value


def _p95_across_seed_p95(row: Mapping[str, Any]) -> float | None:
    value = row.get("aggregate", {}).get("p95_loop_latency_s", {}).get("p95")
    return None if value is None else float(value)


def _resolve_manifest_path(manifest_path: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else manifest_path.parent / candidate


def _load_manifest_truth_sidecar(
    path: Path,
    *,
    frames: Sequence[Mapping[str, Any]],
) -> tuple[list[OfflineTruthLabel], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        labels = load_offline_truth_labels_jsonl(path)
        return labels, {
            "schema_version": D1_OFFLINE_TRUTH_ALIGNMENT_SCHEMA_VERSION,
            "source_schema_version": "d2-offline-truth-label/v1",
            "matching_policy": "prealigned_d2_labels_strict_frame_timestamp_validation",
            "availability": "complete",
            "truth_metrics_input_available": True,
            "source_sample_count": len(labels),
            "matched_sample_count": len(labels),
            "unmatched_sample_count": 0,
            "unmatched_reason_counts": {},
            "unmatched_samples": [],
            "online_truth_injected": False,
        }
    if suffix != ".json":
        raise ValueError(
            "offline truth sidecar must use .jsonl for D2 labels or .json for D1 sidecar"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("offline truth JSON sidecar must contain an object")
    schema_version = payload.get("schema_version")
    if schema_version == D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION:
        result = load_d1_airsim_offline_truth_alignment_json(
            path,
            replay_frames=frames,
        )
        return list(result.labels), dict(result.summary)
    raise ValueError(f"unsupported offline truth JSON schema: {schema_version!r}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
