"""Offline calibration for D1 pre-commit EO association-risk evidence."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    ASSOCIATION_RISK_CLASSIFICATION_CRITERIA,
    ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION,
    AssociationRiskClassificationEvidence,
    AssociationRiskEvidence,
)


D1_ASSOCIATION_RISK_CALIBRATION_SCHEMA = (
    "scalable3d-d1-association-risk-calibration-v1"
)
D1_ASSOCIATION_RISK_COMPOSITE_PROFILE = (
    "d1-eo-pathological-projection-composite-development-v2"
)
D1_ASSOCIATION_RISK_REPORT = "D1_ASSOCIATION_RISK_CALIBRATION_CN.md"
D1_ASSOCIATION_RISK_SUMMARY = "d1_association_risk_calibration.json"
D1_ASSOCIATION_RISK_ROWS = "d1_association_risk_evidence.csv"
D1_ASSOCIATION_RISK_MANIFEST = "manifest.json"
D1_ASSOCIATION_RISK_VALIDATION_ROLES = frozenset(
    {"development", "held_out"}
)
_REPORT_CHECK_LABELS = {
    "multiple_gate_candidates": "至少两个门内候选",
    "selected_projection_out_of_frame": "选中投影位于画面外",
    "plausible_in_frame_alternative": "存在画面内保留候选",
    "bbox_area_within_limit": "检测框面积不大于4平方像素",
    "confidence_within_limit": "检测置信度不大于0.10",
}
_REPORT_REASON_LABELS = {
    "multiple_truth_targets_for_global_track": "单条全局航迹关联多个真值目标",
    "required_composite_criteria_not_met": "复合判据未全部满足",
    "raw_risk_evidence_missing": "缺少对应原始风险证据",
}


@dataclass(frozen=True, slots=True)
class AssociationRiskCalibrationCase:
    """One completed development episode and its offline failure labels."""

    case_id: str
    episode_dir: Path
    expected_failure_events: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        case_id = str(self.case_id).strip()
        if not case_id:
            raise ValueError("case_id must be non-empty")
        if not isinstance(self.episode_dir, Path):
            raise TypeError("episode_dir must be a pathlib.Path")
        events: list[tuple[str, float]] = []
        for sensor_id, timestamp in self.expected_failure_events:
            sensor = str(sensor_id).strip()
            value = float(timestamp)
            if not sensor or not _finite(value) or value < 0.0:
                raise ValueError("expected failure events require sensor and timestamp")
            events.append((sensor, value))
        if len(set(events)) != len(events):
            raise ValueError("expected_failure_events must be unique")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "episode_dir", self.episode_dir.expanduser().resolve())
        object.__setattr__(self, "expected_failure_events", tuple(events))


@dataclass(frozen=True, slots=True)
class AssociationRiskCompositeProfile:
    """Truth-free feature thresholds for a shadow-only composite warning."""

    profile_version: str = D1_ASSOCIATION_RISK_COMPOSITE_PROFILE
    maximum_assignment_margin: float = 2.0
    maximum_selected_forward_depth_m: float = 5.0
    minimum_selected_condition_number: float = 1.0e6
    maximum_bbox_area_px2: float = 4.0
    maximum_confidence: float = 0.10
    required_checks: tuple[str, ...] = (
        "multiple_gate_candidates",
        "selected_projection_out_of_frame",
        "plausible_in_frame_alternative",
        "bbox_area_within_limit",
        "confidence_within_limit",
    )

    def __post_init__(self) -> None:
        if self.profile_version != D1_ASSOCIATION_RISK_COMPOSITE_PROFILE:
            raise ValueError("unsupported composite profile version")
        for name in (
            "maximum_assignment_margin",
            "maximum_selected_forward_depth_m",
            "minimum_selected_condition_number",
            "maximum_bbox_area_px2",
            "maximum_confidence",
        ):
            value = float(getattr(self, name))
            if not _finite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        if self.maximum_confidence > 1.0:
            raise ValueError("maximum_confidence must not exceed one")
        required = tuple(str(value).strip() for value in self.required_checks)
        supported = {
            "multiple_gate_candidates",
            "selected_projection_out_of_frame",
            "plausible_in_frame_alternative",
            "assignment_margin_within_limit",
            "selected_depth_within_limit",
            "selected_innovation_ill_conditioned",
            "bbox_area_within_limit",
            "confidence_within_limit",
        }
        if not required or len(set(required)) != len(required):
            raise ValueError("required_checks must be non-empty and unique")
        if any(value not in supported for value in required):
            raise ValueError("required_checks contain an unsupported check")
        object.__setattr__(self, "required_checks", required)

    def classify(self, evidence: AssociationRiskEvidence) -> tuple[bool, dict[str, bool]]:
        selected = next(edge for edge in evidence.candidate_edges if edge.selected)
        alternatives = tuple(edge for edge in evidence.candidate_edges if not edge.selected)
        checks = {
            "multiple_gate_candidates": evidence.valid_candidate_count >= 2,
            "selected_projection_out_of_frame": not selected.projection_in_frame,
            "plausible_in_frame_alternative": any(
                edge.projection_in_frame for edge in alternatives
            ),
            "assignment_margin_within_limit": (
                evidence.assignment_margin is not None
                and evidence.assignment_margin <= self.maximum_assignment_margin
            ),
            "selected_depth_within_limit": (
                selected.forward_depth_m <= self.maximum_selected_forward_depth_m
            ),
            "selected_innovation_ill_conditioned": (
                selected.innovation_covariance_condition_number
                >= self.minimum_selected_condition_number
            ),
            "bbox_area_within_limit": (
                evidence.bbox_area_px2 is not None
                and evidence.bbox_area_px2 <= self.maximum_bbox_area_px2
            ),
            "confidence_within_limit": (
                evidence.confidence <= self.maximum_confidence
            ),
        }
        return all(checks[name] for name in self.required_checks), checks


def run_d1_association_risk_calibration(
    output_dir: str | Path,
    *,
    cases: Iterable[AssociationRiskCalibrationCase],
    profile: AssociationRiskCompositeProfile | None = None,
    timestamp_tolerance_s: float = 1.0e-9,
    validation_role: str = "development",
    require_online_classifications: bool = False,
) -> Mapping[str, Path]:
    """Evaluate shadow evidence without feeding labels or decisions online."""

    resolved_cases = tuple(cases)
    if not resolved_cases:
        raise ValueError("at least one calibration case is required")
    if any(not isinstance(case, AssociationRiskCalibrationCase) for case in resolved_cases):
        raise TypeError("cases must contain AssociationRiskCalibrationCase values")
    if len({case.case_id for case in resolved_cases}) != len(resolved_cases):
        raise ValueError("case_id values must be unique")
    tolerance = float(timestamp_tolerance_s)
    if not _finite(tolerance) or tolerance < 0.0:
        raise ValueError("timestamp_tolerance_s must be finite and non-negative")
    role = str(validation_role).strip().lower()
    if role not in D1_ASSOCIATION_RISK_VALIDATION_ROLES:
        raise ValueError(
            "validation_role must be one of "
            f"{sorted(D1_ASSOCIATION_RISK_VALIDATION_ROLES)}"
        )
    if not isinstance(require_online_classifications, bool):
        raise TypeError("require_online_classifications must be a bool")
    if role == "held_out" and not require_online_classifications:
        raise ValueError(
            "held_out validation requires persisted online classifications"
        )
    active_profile = profile or AssociationRiskCompositeProfile()
    if not isinstance(active_profile, AssociationRiskCompositeProfile):
        raise TypeError("profile must be an AssociationRiskCompositeProfile")

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.partial-", dir=destination.parent)
    )
    try:
        summary, rows, source_files = _calibrate(
            resolved_cases,
            profile=active_profile,
            timestamp_tolerance_s=tolerance,
            validation_role=role,
            require_online_classifications=require_online_classifications,
        )
        summary_path = _write_json(staging / D1_ASSOCIATION_RISK_SUMMARY, summary)
        rows_path = _write_rows(staging / D1_ASSOCIATION_RISK_ROWS, rows)
        report_path = _write_report(staging / D1_ASSOCIATION_RISK_REPORT, summary)
        manifest = {
            "schema_version": D1_ASSOCIATION_RISK_CALIBRATION_SCHEMA,
            "created_at_utc": _utc_timestamp(),
            "producer": "main-scalable3d-offline-d1-association-risk-calibration",
            "online_decision_applied": False,
            "online_truth_used": False,
            "validation_role": role,
            "require_online_classifications": (
                require_online_classifications
            ),
            "source_files": source_files,
            "outputs": {
                D1_ASSOCIATION_RISK_SUMMARY: _sha256_file(summary_path),
                D1_ASSOCIATION_RISK_ROWS: _sha256_file(rows_path),
                D1_ASSOCIATION_RISK_REPORT: _sha256_file(report_path),
            },
        }
        manifest_path = _write_json(staging / D1_ASSOCIATION_RISK_MANIFEST, manifest)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "manifest": destination / D1_ASSOCIATION_RISK_MANIFEST,
        "summary": destination / D1_ASSOCIATION_RISK_SUMMARY,
        "rows": destination / D1_ASSOCIATION_RISK_ROWS,
        "report": destination / D1_ASSOCIATION_RISK_REPORT,
    }


def _calibrate(
    cases: tuple[AssociationRiskCalibrationCase, ...],
    *,
    profile: AssociationRiskCompositeProfile,
    timestamp_tolerance_s: float,
    validation_role: str,
    require_online_classifications: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    case_summaries: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    aggregate_reasons: Counter[str] = Counter()
    expected_event_count = 0
    flagged_expected_event_count = 0
    control_case_count = 0
    warned_control_case_count = 0
    online_classification_record_count = 0
    online_classification_profile_match_count = 0
    online_classification_complete_case_count = 0
    missed_failure_reason_counts: Counter[str] = Counter()

    for case in cases:
        case_row_start = len(rows)
        loaded = _load_case(case)
        evidence_items = loaded["evidence"]
        classifications_by_evidence = loaded["classifications_by_evidence"]
        if require_online_classifications and (
            len(classifications_by_evidence) != len(evidence_items)
        ):
            raise ValueError(
                f"{case.case_id}: persisted online classifications are incomplete"
            )
        expected_events = case.expected_failure_events
        expected_event_count += len(expected_events)
        is_control = not expected_events
        control_case_count += int(is_control)
        flagged_event_keys: set[tuple[str, float]] = set()
        case_warning_count = 0

        for evidence in evidence_items:
            flagged, checks = profile.classify(evidence)
            expected_criteria = _classification_criteria(checks)
            online_classification = classifications_by_evidence.get(
                evidence.evidence_id
            )
            online_matches_profile = (
                online_classification is not None
                and online_classification.profile_version
                == ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION
                and online_classification.classification
                == ("positive" if flagged else "negative")
                and online_classification.matched_criteria
                == tuple(
                    criterion
                    for criterion in ASSOCIATION_RISK_CLASSIFICATION_CRITERIA
                    if expected_criteria[criterion]
                )
                and online_classification.unmatched_criteria
                == tuple(
                    criterion
                    for criterion in ASSOCIATION_RISK_CLASSIFICATION_CRITERIA
                    if not expected_criteria[criterion]
                )
            )
            online_classification_record_count += int(
                online_classification is not None
            )
            online_classification_profile_match_count += int(
                online_matches_profile
            )
            matched_expected = _matches_expected_event(
                evidence,
                expected_events,
                timestamp_tolerance_s=timestamp_tolerance_s,
            )
            if flagged:
                case_warning_count += 1
                for sensor_id, timestamp in expected_events:
                    if (
                        evidence.sensor_id == sensor_id
                        and abs(evidence.measurement_timestamp - timestamp)
                        <= timestamp_tolerance_s
                    ):
                        flagged_event_keys.add((sensor_id, timestamp))
            aggregate_reasons.update(evidence.risk_reasons)
            selected = next(edge for edge in evidence.candidate_edges if edge.selected)
            alternatives = tuple(
                edge for edge in evidence.candidate_edges if not edge.selected
            )
            rows.append(
                {
                    "case_id": case.case_id,
                    "evidence_id": evidence.evidence_id,
                    "sensor_id": evidence.sensor_id,
                    "measurement_timestamp": evidence.measurement_timestamp,
                    "arrival_timestamp": evidence.arrival_timestamp,
                    "risk_reasons": "|".join(evidence.risk_reasons),
                    "valid_candidate_count": evidence.valid_candidate_count,
                    "assignment_margin": evidence.assignment_margin,
                    "bbox_area_px2": evidence.bbox_area_px2,
                    "confidence": evidence.confidence,
                    "selected_nis": selected.nis,
                    "selected_forward_depth_m": selected.forward_depth_m,
                    "selected_projection_in_frame": selected.projection_in_frame,
                    "selected_condition_number": (
                        selected.innovation_covariance_condition_number
                    ),
                    "selected_raw_pixel_residual_norm": (
                        selected.raw_pixel_residual_norm
                    ),
                    "selected_projection_ellipse_major_axis_px": (
                        selected.projection_ellipse_major_axis_px
                    ),
                    "in_frame_alternative_count": sum(
                        int(edge.projection_in_frame) for edge in alternatives
                    ),
                    "composite_warning": flagged,
                    "online_classification_available": (
                        online_classification is not None
                    ),
                    "online_classification": (
                        None
                        if online_classification is None
                        else online_classification.classification
                    ),
                    "online_classification_matches_profile": (
                        online_matches_profile
                    ),
                    "matches_expected_failure_event": matched_expected,
                    **{f"check_{name}": value for name, value in checks.items()},
                }
            )

        flagged_expected_event_count += len(flagged_event_keys)
        warned_control_case_count += int(is_control and case_warning_count > 0)
        missed_failure_event_diagnostics = (
            _missed_failure_event_diagnostics(
                rows[case_row_start:],
                expected_events,
                flagged_event_keys,
                required_checks=profile.required_checks,
                timestamp_tolerance_s=timestamp_tolerance_s,
            )
        )
        for diagnostic in missed_failure_event_diagnostics:
            missed_failure_reason_counts.update(
                diagnostic["unmatched_required_checks"]
                or (diagnostic["reason"],)
            )
        identity = loaded["identity"]
        online_complete = (
            len(classifications_by_evidence) == len(evidence_items)
            and all(
                classifications_by_evidence[evidence.evidence_id].profile_version
                == ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION
                for evidence in evidence_items
            )
        )
        online_classification_complete_case_count += int(online_complete)
        case_summaries.append(
            {
                "case_id": case.case_id,
                "episode_dir": str(case.episode_dir),
                "episode_id": loaded["manifest"].get("episode_id"),
                "expected_failure_events": [
                    {"sensor_id": sensor_id, "measurement_timestamp": timestamp}
                    for sensor_id, timestamp in expected_events
                ],
                "strict_identity_metrics_available": identity["available"],
                "strict_identity_metrics_reason": identity["reason"],
                "evidence_count": len(evidence_items),
                "composite_warning_count": case_warning_count,
                "online_classification_count": len(
                    classifications_by_evidence
                ),
                "online_classification_complete": online_complete,
                "expected_failure_event_count": len(expected_events),
                "flagged_expected_failure_event_count": len(flagged_event_keys),
                "missed_failure_event_diagnostics": (
                    missed_failure_event_diagnostics
                ),
                "reason_counts": dict(
                    sorted(Counter(
                        reason
                        for evidence in evidence_items
                        for reason in evidence.risk_reasons
                    ).items())
                ),
            }
        )
        source_files.extend(loaded["source_files"])

    evidence_count = len(rows)
    warning_count = sum(int(row["composite_warning"]) for row in rows)
    unexpected_warning_count = sum(
        int(row["composite_warning"] and not row["matches_expected_failure_event"])
        for row in rows
    )
    positive_case_count = len(cases) - control_case_count
    failed_event_recall = (
        None
        if expected_event_count == 0
        else flagged_expected_event_count / expected_event_count
    )
    control_warning_rate = (
        None
        if control_case_count == 0
        else warned_control_case_count / control_case_count
    )
    count_sufficient = positive_case_count >= 10 and control_case_count >= 20
    performance_sufficient = bool(
        failed_event_recall is not None
        and failed_event_recall >= 0.90
        and control_warning_rate is not None
        and control_warning_rate <= 0.05
    )
    shadow_review_sufficient = count_sufficient and performance_sufficient
    online_classifier_complete = bool(
        online_classification_record_count == evidence_count
        and online_classification_profile_match_count == evidence_count
        and online_classification_complete_case_count == len(cases)
    )
    held_out_validation_available = bool(
        validation_role == "held_out"
        and require_online_classifications
        and online_classifier_complete
        and shadow_review_sufficient
    )
    evidence_class = (
        "held_out_offline_shadow_validation"
        if validation_role == "held_out"
        else "development_offline_shadow_calibration"
    )
    return (
        {
            "schema_version": D1_ASSOCIATION_RISK_CALIBRATION_SCHEMA,
            "evidence_class": evidence_class,
            "validation_role": validation_role,
            "require_online_classifications": (
                require_online_classifications
            ),
            "online_truth_used": False,
            "online_decision_applied": False,
            "d1_posterior_changed": False,
            "d2_enforcement_changed": False,
            "profile": asdict(profile),
            "timestamp_tolerance_s": timestamp_tolerance_s,
            "case_count": len(cases),
            "positive_case_count": positive_case_count,
            "control_case_count": control_case_count,
            "evidence_count": evidence_count,
            "warning_count": warning_count,
            "online_classification_record_count": (
                online_classification_record_count
            ),
            "online_classification_profile_match_count": (
                online_classification_profile_match_count
            ),
            "online_classification_complete_case_count": (
                online_classification_complete_case_count
            ),
            "online_classifier_complete": online_classifier_complete,
            "unexpected_warning_count": unexpected_warning_count,
            "reason_counts": dict(sorted(aggregate_reasons.items())),
            "failed_event_recall": failed_event_recall,
            "expected_failure_event_count": expected_event_count,
            "flagged_expected_failure_event_count": flagged_expected_event_count,
            "passing_control_warning_rate": control_warning_rate,
            "warned_control_case_count": warned_control_case_count,
            "missed_failure_reason_counts": dict(
                sorted(missed_failure_reason_counts.items())
            ),
            "sample_sufficiency": {
                "sufficient_for_shadow_classification_review": (
                    shadow_review_sufficient
                ),
                "sufficient_for_enforcement": False,
                "minimum_positive_cases": 10,
                "minimum_control_cases": 20,
                "minimum_failed_event_recall": 0.90,
                "maximum_passing_control_warning_rate": 0.05,
                "count_requirement_met": count_sufficient,
                "performance_requirement_met": performance_sufficient,
                "held_out_independent_validation_available": (
                    held_out_validation_available
                ),
                "reason": (
                    "held_out_online_classification_validation_passed"
                    if held_out_validation_available
                    else (
                        "development_source_reuse_requires_held_out_validation"
                        if shadow_review_sufficient
                        and validation_role == "development"
                        else (
                            "online_classification_contract_incomplete"
                            if shadow_review_sufficient
                            and not online_classifier_complete
                            else "count_or_performance_requirement_not_met"
                        )
                    )
                ),
            },
            "recommendation": (
                "held_out_supports_d1_shadow_classification_not_enforcement"
                if held_out_validation_available
                else (
                    "eligible_for_d1_shadow_classification_review_not_enforcement"
                    if shadow_review_sufficient
                    and validation_role == "development"
                    else "remain_raw_shadow_collect_more_failure_and_control_episodes"
                )
            ),
            "cases": case_summaries,
        },
        rows,
        source_files,
    )


def _load_case(case: AssociationRiskCalibrationCase) -> dict[str, Any]:
    required = {
        "manifest": case.episode_dir / "manifest.json",
        "summary": case.episode_dir / "summary.json",
        "governance": case.episode_dir / "observation_governance_audit.json",
        "identity": case.episode_dir / "offline_identity" / "identity_evaluation.json",
        "d1_records": case.episode_dir / "offline_identity" / "online_d1_records.jsonl",
    }
    for path in required.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    manifest = _load_json(required["manifest"])
    summary = _load_json(required["summary"])
    governance = _load_json(required["governance"])
    identity_payload = _load_json(required["identity"])
    configuration = manifest.get("runtime_profile", {}).get("configuration", {})
    if configuration.get("d1_association_risk_evidence_shadow_enabled") is not True:
        raise ValueError(f"{case.case_id}: D1 risk shadow is not enabled")
    if configuration.get("d1_publish_opaque_source_key") is not False:
        raise ValueError(f"{case.case_id}: opaque source publication confounds calibration")
    if summary.get("finite_state") is not True:
        raise ValueError(f"{case.case_id}: episode state is not finite")
    if int(summary.get("online_truth_use_count", -1)) != 0:
        raise ValueError(f"{case.case_id}: online truth isolation failed")
    audit = governance.get("d1_association_risk_evidence_audit")
    if not isinstance(audit, Mapping):
        raise ValueError(f"{case.case_id}: risk evidence audit is missing")
    if (
        audit.get("enabled") is not True
        or audit.get("mode") != "shadow"
        or audit.get("decision") != "evidence_only"
        or audit.get("online_truth_used") is not False
    ):
        raise ValueError(f"{case.case_id}: invalid shadow audit contract")

    evidence: list[AssociationRiskEvidence] = []
    classifications: list[AssociationRiskClassificationEvidence] = []
    with required["d1_records"].open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                raise ValueError(
                    f"{case.case_id}: invalid D1 payload at line {line_number}"
                )
            items = payload.get("association_risk_evidence", ())
            count = payload.get("association_risk_evidence_count", len(items))
            if int(count) != len(items):
                raise ValueError(
                    f"{case.case_id}: risk evidence count mismatch at line {line_number}"
                )
            evidence.extend(
                AssociationRiskEvidence.from_dict(item) for item in items
            )
            classification_items = payload.get(
                "association_risk_classifications",
                (),
            )
            classification_count = payload.get(
                "association_risk_classification_count",
                len(classification_items),
            )
            if int(classification_count) != len(classification_items):
                raise ValueError(
                    f"{case.case_id}: risk classification count mismatch "
                    f"at line {line_number}"
                )
            classifications.extend(
                AssociationRiskClassificationEvidence.from_dict(item)
                for item in classification_items
            )
    if int(audit.get("evidence_count", -1)) != len(evidence):
        raise ValueError(f"{case.case_id}: episode risk evidence audit mismatch")
    classifications_by_evidence = {
        item.evidence_id: item for item in classifications
    }
    if len(classifications_by_evidence) != len(classifications):
        raise ValueError(f"{case.case_id}: duplicate online risk classification")
    evidence_ids = {item.evidence_id for item in evidence}
    if not set(classifications_by_evidence).issubset(evidence_ids):
        raise ValueError(
            f"{case.case_id}: classification references unknown raw evidence"
        )
    if classifications:
        classification_audit = governance.get(
            "d1_association_risk_classification_audit"
        )
        if not isinstance(classification_audit, Mapping):
            raise ValueError(
                f"{case.case_id}: risk classification audit is missing"
            )
        if (
            classification_audit.get("enabled") is not True
            or classification_audit.get("mode") != "shadow"
            or classification_audit.get("decision") != "evidence_only"
            or classification_audit.get("online_truth_used") is not False
            or classification_audit.get("posterior_update_applied") is not False
            or int(
                classification_audit.get(
                    "published_classification_count",
                    -1,
                )
            )
            != len(classifications)
        ):
            raise ValueError(
                f"{case.case_id}: invalid shadow classification audit contract"
            )
    metrics = identity_payload.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError(f"{case.case_id}: strict identity metrics are missing")
    identity = {
        "available": bool(metrics.get("truth_metrics_available")),
        "reason": metrics.get("truth_metrics_reason"),
    }
    return {
        "manifest": manifest,
        "identity": identity,
        "evidence": tuple(evidence),
        "classifications_by_evidence": classifications_by_evidence,
        "source_files": [
            {
                "case_id": case.case_id,
                "role": role,
                "path": str(path),
                "sha256": _sha256_file(path),
            }
            for role, path in sorted(required.items())
        ],
    }


def _matches_expected_event(
    evidence: AssociationRiskEvidence,
    expected_events: tuple[tuple[str, float], ...],
    *,
    timestamp_tolerance_s: float,
) -> bool:
    return any(
        evidence.sensor_id == sensor_id
        and abs(evidence.measurement_timestamp - timestamp) <= timestamp_tolerance_s
        for sensor_id, timestamp in expected_events
    )


def _classification_criteria(checks: Mapping[str, bool]) -> dict[str, bool]:
    return {
        "valid_candidate_count_gte_2": bool(
            checks["multiple_gate_candidates"]
        ),
        "selected_projection_out_of_frame": bool(
            checks["selected_projection_out_of_frame"]
        ),
        "retained_alternative_projection_in_frame": bool(
            checks["plausible_in_frame_alternative"]
        ),
        "bbox_area_px2_lte_4_0": bool(
            checks["bbox_area_within_limit"]
        ),
        "confidence_lte_0_10": bool(
            checks["confidence_within_limit"]
        ),
    }


def _missed_failure_event_diagnostics(
    rows: list[Mapping[str, Any]],
    expected_events: tuple[tuple[str, float], ...],
    flagged_events: set[tuple[str, float]],
    *,
    required_checks: tuple[str, ...],
    timestamp_tolerance_s: float,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for sensor_id, timestamp in expected_events:
        if (sensor_id, timestamp) in flagged_events:
            continue
        candidates = [
            row
            for row in rows
            if row["sensor_id"] == sensor_id
            and abs(float(row["measurement_timestamp"]) - timestamp)
            <= timestamp_tolerance_s
        ]
        if not candidates:
            diagnostics.append(
                {
                    "sensor_id": sensor_id,
                    "measurement_timestamp": timestamp,
                    "reason": "raw_risk_evidence_missing",
                    "unmatched_required_checks": [],
                    "candidate_evidence_count": 0,
                    "selected_evidence_id": None,
                }
            )
            continue
        ranked = sorted(
            candidates,
            key=lambda row: (
                sum(
                    not bool(row[f"check_{name}"])
                    for name in required_checks
                ),
                str(row["evidence_id"]),
            ),
        )
        selected = ranked[0]
        unmatched = [
            name
            for name in required_checks
            if not bool(selected[f"check_{name}"])
        ]
        diagnostics.append(
            {
                "sensor_id": sensor_id,
                "measurement_timestamp": timestamp,
                "reason": "required_composite_criteria_not_met",
                "unmatched_required_checks": unmatched,
                "candidate_evidence_count": len(candidates),
                "selected_evidence_id": selected["evidence_id"],
            }
        )
    return diagnostics


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> Path:
    fieldnames = list(rows[0]) if rows else ["case_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_report(path: Path, summary: Mapping[str, Any]) -> Path:
    recall = summary["failed_event_recall"]
    warning_rate = summary["passing_control_warning_rate"]
    held_out = summary["validation_role"] == "held_out"
    sufficiency = summary["sample_sufficiency"]
    if held_out:
        title = "# D1 光电关联风险独立留出验证"
        boundary_statement = (
            "本次结果来自独立留出集，只验证已冻结的在线影子分类器。风险证据没有改变 "
            "D1 后验，也没有触发 D2 阻断。"
        )
        if sufficiency["held_out_independent_validation_available"]:
            conclusion = (
                "独立留出集通过样本数量和性能门，仅支持继续开展 D1 影子分类复核。"
                "该结果不授权 D2 强制阻断。"
            )
        elif sufficiency["count_requirement_met"]:
            conclusion = (
                "独立留出集达到样本数量下限，但未通过性能门。分类器继续默认关闭并保持"
                "影子证据模式，不得启用 D2 强制阻断。"
            )
        else:
            conclusion = (
                "独立留出集未达到样本数量下限。分类器继续默认关闭并保持影子证据模式，"
                "不得启用 D2 强制阻断。"
            )
    else:
        title = "# D1 光电关联风险影子校准"
        boundary_statement = (
            "本次结果仅用于离线开发校准。风险证据没有改变 D1 后验，也没有触发 "
            "D2 阻断。"
        )
        conclusion = (
            "当前结果只支持进入 D1 影子分类复核。样本来自同一冻结开发来源，缺少独立"
            "留出验证，不得启用 D2 强制阻断。"
            if sufficiency["sufficient_for_shadow_classification_review"]
            else "当前样本量或区分度不足。继续保留原始影子证据并扩充独立样本。"
        )
    lines = [
        title,
        "",
        "## 结论",
        "",
        boundary_statement,
        (
            f"共检查 {summary['case_count']} 个仿真样本、{summary['evidence_count']} 条风险证据，"
            f"候选复合规则触发 {summary['warning_count']} 次。"
        ),
        (
            "本批次未持久化在线分类记录。"
            if not summary["online_classifier_complete"]
            else (
                "在线影子分类记录与离线复算逐条一致，"
                f"共 {summary['online_classification_record_count']} 条。"
            )
        ),
        (
            "故障事件召回率为待计算。"
            if recall is None
            else f"已标注故障事件召回率为 {recall:.3f}。"
        ),
        (
            "通过对照告警率为待计算。"
            if warning_rate is None
            else f"通过对照 episode 告警率为 {warning_rate:.3f}。"
        ),
        "",
        conclusion,
        "",
        "## 分样本结果",
        "",
        "| 样本 | 严格身份可用 | 身份阻断原因 | 风险证据 | 复合告警 | 标注故障事件命中 |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for case in summary["cases"]:
        lines.append(
            "| {case_id} | {available} | {reason} | {evidence} | {warning} | {hit} |".format(
                case_id=case["case_id"],
                available="是" if case["strict_identity_metrics_available"] else "否",
                reason=_REPORT_REASON_LABELS.get(
                    case["strict_identity_metrics_reason"],
                    case["strict_identity_metrics_reason"] or "无",
                ),
                evidence=case["evidence_count"],
                warning=case["composite_warning_count"],
                hit=case["flagged_expected_failure_event_count"],
            )
        )
    lines.extend(
        [
            "",
            "## 漏检诊断",
            "",
        ]
    )
    missed = [
        (case, diagnostic)
        for case in summary["cases"]
        for diagnostic in case["missed_failure_event_diagnostics"]
    ]
    if not missed:
        lines.append("已标注故障事件均被复合规则命中。")
    else:
        lines.extend(
            [
                "| 样本 | 传感器 | 量测时刻/s | 原因 | 未满足条件 |",
                "| --- | --- | ---: | --- | --- |",
            ]
        )
        for case, diagnostic in missed:
            checks = diagnostic["unmatched_required_checks"]
            lines.append(
                "| {case_id} | {sensor_id} | {timestamp:.3f} | {reason} | {checks} |".format(
                    case_id=case["case_id"],
                    sensor_id=diagnostic["sensor_id"],
                    timestamp=diagnostic["measurement_timestamp"],
                    reason=_REPORT_REASON_LABELS.get(
                        diagnostic["reason"],
                        diagnostic["reason"],
                    ),
                    checks=(
                        "、".join(
                            _REPORT_CHECK_LABELS.get(check, check)
                            for check in checks
                        )
                        if checks
                        else "无原始风险证据"
                    ),
                )
            )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "复合规则只读取时间戳、候选竞争、投影几何、创新协方差、检测框面积和置信度。",
            "真值标签只在本离线校准器中计算召回率，不进入在线生产链路。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
