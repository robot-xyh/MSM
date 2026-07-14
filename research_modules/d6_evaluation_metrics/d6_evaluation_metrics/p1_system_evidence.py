"""Offline P1 evidence aggregation for D1-D7 persisted summaries.

The module deliberately consumes JSON-like evidence and never imports or calls
an online producer. Missing values remain unavailable, and offline truth is
used only through aggregate evaluator metrics supplied by the producer.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import csv
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from pathlib import Path
import random
from typing import Any


P1_SYSTEM_EVIDENCE_SCHEMA_VERSION = "d6-p1-system-evidence-v1"

SOURCE_NAMES = (
    "d1_dense_crossing",
    "d2_difficulty_profiles",
    "d3_assignment_churn",
    "d4_episode_communication",
    "d5_per_primary",
    "d5_native_mot",
    "d7_per_primary",
)

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_RNG_SEED = 20260713

METRIC_NAMES = (
    # D1 governed dense-crossing replay.
    "accepted_observation_count",
    "rejected_observation_count",
    "offline_truth_sample_count",
    "dual_timestamp_coverage_rate",
    "covariance_coverage_rate",
    "source_lineage_coverage_rate",
    "d1_replay_contract_complete",
    # D2 association.
    "id_switch_count",
    "track_continuity",
    "false_track_count",
    "track_rmse",
    "p95_loop_latency_s",
    "scenario_still_non_discriminative",
    "association_admitted",
    # D3 plan and coalition stability.
    "membership_change_count",
    "membership_hold_count",
    "plan_version_churn_count",
    "coalition_version_churn_count",
    "coalition_epoch_churn_count",
    "primary_assignment_count",
    "reserve_assignment_count",
    "reserve_standby_count",
    "stale_reject_count",
    "plan_rollback_detected_count",
    # D4 communication and failover.
    "failover_count",
    "ack_count",
    "missing_ack_count",
    "rejected_ack_count",
    "lease_invalid_count",
    "owner_change_count",
    "execution_allowed_count",
    "execution_allowed_rate",
    "fail_closed_count",
    "fault_case_passed",
    "secondary_takeover_latency_s",
    "distributed_commit_latency_s",
    # D5 per-primary lock evidence.
    "per_primary_evidence_count",
    "per_primary_visible_count",
    "per_primary_associated_count",
    "independently_locked_count",
    "per_primary_lock_rate",
    "per_primary_common_lock_count",
    "common_lock_count",
    "common_lock_opportunity_count",
    "global_track_id_rewrite_count",
    # D5 native MOT admission.
    "native_active_frame_rate",
    "fallback_frame_count",
    "detector_precision",
    "detector_recall",
    "local_continuity",
    "terminal_local_id_switch_count",
    "p95_processing_latency_ms",
    "native_mot_admitted",
    # D7 terminal execution layers. These must never be promoted across layers.
    "contract_allowed_count",
    "control_allowed_count",
    "mode_switched_count",
    "physical_intercept_count",
    "per_primary_authorization_active_count",
    "coalition_visual_completion_bypassed_count",
    "bypassed_arrival_only_count",
    "case_opportunity_count",
    "pair_opportunity_count",
    "coalition_opportunity_count",
    "coalition_completion_count",
    "reserve_unauthorized_count",
    "closest_approach_m",
    # Cross-source safety evidence.
    "online_truth_use_count",
)

ROW_FIELDS = (
    "source",
    "source_schema_version",
    "family",
    "scenario_id",
    "scenario_difficulty",
    "seed",
    "resource_count",
    "target_count",
    "target_spacing_m",
    "camera_id",
    "resource_id",
    "target_id",
    "backend",
    "candidate",
    "candidate_selected",
    "profile_selection_source",
    "terminal_authorization_scope",
    "arrival_coordination_required",
    "selected_layer",
    "owner_id",
    "commit_state_counts",
    "admission_reasons",
    "failure_reasons",
    "failure_reasons_availability",
    "source_sha256",
    "producer",
    "run_id",
    "provenance",
    "evidence_path",
    *METRIC_NAMES,
    *(f"{name}_availability" for name in METRIC_NAMES),
)


@dataclass(frozen=True)
class P1SystemEvidenceInputs:
    """Persisted producer summaries accepted by the passive D6 consumer."""

    d1_dense_crossing: Any | None = None
    d2_difficulty_profiles: Any | None = None
    d3_assignment_churn: Any | None = None
    d4_episode_communication: Any | None = None
    d5_per_primary: Any | None = None
    d5_native_mot: Any | None = None
    d7_per_primary: Any | None = None


class P1SystemEvidenceReportGenerator:
    """Write CSV, JSON, Chinese Markdown, and PNG from offline summaries."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: P1SystemEvidenceInputs,
        title: str = "P1 系统证据统一汇总报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        payloads, manifest = _load_sources(inputs)
        rows = _normalize_rows(payloads, manifest)
        aggregate = _build_aggregate(rows, manifest)

        csv_path = output_dir / "p1_system_evidence_rows.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(_csv_ready(row) for row in rows)

        json_path = output_dir / "p1_system_evidence_aggregate.json"
        json_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        plot_path = output_dir / "p1_system_evidence_overview.png"
        _write_plot(rows, plot_path)

        markdown_path = output_dir / "P1_SYSTEM_EVIDENCE_REPORT.md"
        markdown_path.write_text(
            _render_markdown(aggregate, title=title, plot_name=plot_path.name),
            encoding="utf-8",
        )
        return {
            "rows_csv": csv_path,
            "aggregate_json": json_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def load_p1_system_evidence_source(source: Any) -> dict[str, Any]:
    """Load one JSON-like producer output without importing producer code."""

    if isinstance(source, (str, Path)):
        payload: Any = json.loads(Path(source).read_text(encoding="utf-8"))
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            payload = {"records": list(payload)}
    elif isinstance(source, Mapping):
        payload = dict(source)
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        payload = {"records": list(source)}
    elif hasattr(source, "to_dict"):
        payload = source.to_dict()
    elif hasattr(source, "as_dict"):
        payload = source.as_dict()
    elif is_dataclass(source):
        payload = asdict(source)
    else:
        raise TypeError(f"unsupported P1 system evidence source: {type(source)!r}")
    if not isinstance(payload, Mapping):
        raise ValueError("P1 system evidence root must be a JSON object or sequence")
    return _json_ready(dict(payload))


def _load_sources(
    inputs: P1SystemEvidenceInputs,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payloads: dict[str, dict[str, Any]] = {}
    manifest: dict[str, dict[str, Any]] = {}
    for name in SOURCE_NAMES:
        source = getattr(inputs, name)
        if source is None:
            manifest[name] = {
                "status": "unavailable",
                "schema_version": None,
                "evidence_path": None,
                "sha256": None,
                "producer": None,
                "run_id": None,
                "provenance": {},
                "reason": "summary was not provided",
            }
            continue
        payload = load_p1_system_evidence_source(source)
        payloads[name] = payload
        evidence_path = str(source) if isinstance(source, (str, Path)) else None
        source_path = Path(source) if isinstance(source, (str, Path)) else None
        provenance = _source_provenance(payload)
        manifest[name] = {
            "status": "available",
            "schema_version": _first(
                payload,
                "schema_version",
                "schema",
                "calibration_suite_version",
            ),
            "evidence_path": evidence_path,
            "sha256": _file_sha256(source_path) if source_path is not None else None,
            "producer": _first(provenance, "producer", "source", "module"),
            "run_id": _first(provenance, "run_id", "episode_id", "batch_id"),
            "provenance": provenance,
            "reason": None,
        }
    return payloads, manifest


def _normalize_rows(
    payloads: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if payload := payloads.get("d1_dense_crossing"):
        rows.extend(_normalize_d1(payload, manifest["d1_dense_crossing"]))
    if payload := payloads.get("d2_difficulty_profiles"):
        rows.extend(_normalize_d2(payload, manifest["d2_difficulty_profiles"]))
    if payload := payloads.get("d3_assignment_churn"):
        rows.extend(_normalize_d3(payload, manifest["d3_assignment_churn"]))
    if payload := payloads.get("d4_episode_communication"):
        rows.extend(_normalize_d4(payload, manifest["d4_episode_communication"]))
    if payload := payloads.get("d5_per_primary"):
        rows.extend(_normalize_d5_per_primary(payload, manifest["d5_per_primary"]))
    if payload := payloads.get("d5_native_mot"):
        rows.extend(_normalize_d5(payload, manifest["d5_native_mot"]))
    if payload := payloads.get("d7_per_primary"):
        rows.extend(_normalize_d7(payload, manifest["d7_per_primary"]))
    return rows


def _normalize_d1(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    records = _record_list(payload, ("summaries", "rows", "records", "episodes"))
    if not records:
        summary = _mapping(payload.get("summary"))
        records = [summary or dict(payload)]
    rows: list[dict[str, Any]] = []
    for item in records:
        summary = _mapping(item.get("summary")) or item
        capture = _mapping(summary.get("capture_provenance"))
        if not capture:
            capture = _mapping(item.get("capture_provenance"))
        availability = _mapping(summary.get("field_availability"))
        accepted = _optional_int(summary.get("accepted_observation_count"))
        measurement_count = _availability_count(availability, "measurement_timestamp")
        arrival_count = _availability_count(availability, "arrival_timestamp")
        covariance_count = _availability_count(availability, "covariance")
        lineage_count = _availability_count(availability, "source_lineage")
        dual_count = (
            min(measurement_count, arrival_count)
            if measurement_count is not None and arrival_count is not None
            else None
        )
        reasons = tuple(
            str(entry.get("reason"))
            for entry in _mapping_rows(summary.get("rejected_observations"))
            if entry.get("reason")
        )
        required_counts = (dual_count, covariance_count, lineage_count)
        contract_complete = (
            all(value is not None and accepted is not None and value >= accepted for value in required_counts)
            if accepted is not None
            else None
        )
        rows.append(
            _finish_row(
                {
                    "source": "d1_dense_crossing",
                    "family": "governed_dense_crossing_replay",
                    "scenario_id": _coalesce(
                        _first(capture, "scenario_id"),
                        _first(summary, "scenario_id", "scene_id"),
                    ),
                    "seed": _coalesce(capture.get("seed"), summary.get("seed")),
                    "target_count": _first(
                        summary, "offline_truth_target_count", "target_count"
                    ),
                    "target_spacing_m": _coalesce(
                        capture.get("target_spacing_m"), summary.get("target_spacing_m")
                    ),
                    "accepted_observation_count": accepted,
                    "rejected_observation_count": _optional_int(
                        summary.get("rejected_observation_count")
                    ),
                    "offline_truth_sample_count": _optional_int(
                        summary.get("offline_truth_sample_count")
                    ),
                    "dual_timestamp_coverage_rate": _coverage_rate(dual_count, accepted),
                    "covariance_coverage_rate": _coverage_rate(covariance_count, accepted),
                    "source_lineage_coverage_rate": _coverage_rate(lineage_count, accepted),
                    "d1_replay_contract_complete": contract_complete,
                    "failure_reasons": reasons,
                    "failure_reasons_availability": (
                        "available"
                        if "rejected_observations" in summary
                        or summary.get("rejected_observation_count") is not None
                        else "unavailable"
                    ),
                    "online_truth_use_count": _first(
                        summary, "online_truth_leak_count", "online_truth_use_count"
                    ),
                    "provenance": capture or _mapping(summary.get("provenance")),
                    "evidence_path": _coalesce(
                        capture.get("evidence_path"), summary.get("evidence_path")
                    ),
                },
                source,
            )
        )
    return rows


def _normalize_d5(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    records = _record_list(payload, ("summaries", "streams", "rows", "records"))
    if not records and "requested_tracker_backend" in payload:
        records = [payload]
    rows: list[dict[str, Any]] = []
    for item in records:
        scenario = _mapping(item.get("scenario"))
        online_truth = int(bool(item.get("truth_identity_used_online", False)))
        online_truth += _optional_int(item.get("online_truth_use_count")) or 0
        rows.append(
            _finish_row(
                {
                    "source": "d5_native_mot",
                    "family": "native_mot_admission",
                    "scenario_id": _coalesce(
                        _first(scenario, "scenario_id"), item.get("scenario_id")
                    ),
                    "seed": _coalesce(_first(scenario, "seed"), item.get("seed")),
                    "resource_count": item.get("resource_count"),
                    "target_count": _first(scenario, "target_count") or item.get("target_count"),
                    "camera_id": item.get("camera_id"),
                    "resource_id": item.get("resource_id"),
                    "backend": _first(item, "requested_tracker_backend", "tracker_backend"),
                    "native_active_frame_rate": item.get("native_active_frame_rate"),
                    "fallback_frame_count": item.get("fallback_frame_count"),
                    "detector_precision": item.get("offline_detector_precision"),
                    "detector_recall": item.get("offline_detector_recall"),
                    "local_continuity": item.get("local_continuity"),
                    "terminal_local_id_switch_count": item.get(
                        "terminal_local_id_switch_count"
                    ),
                    "p95_processing_latency_ms": item.get(
                        "warmup_excluded_p95_latency_ms"
                    ),
                    "native_mot_admitted": item.get("native_mot_admitted"),
                    "admission_reasons": item.get("rejection_reasons", ()),
                    "failure_reasons": item.get("rejection_reasons", ()),
                    "failure_reasons_availability": (
                        "available"
                        if "rejection_reasons" in item
                        else "unavailable"
                    ),
                    "online_truth_use_count": online_truth,
                },
                source,
            )
        )
    return rows


def _normalize_d5_per_primary(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    cooperative_rows = _cooperative_pair_rows(payload)
    if cooperative_rows:
        return [
            _normalize_d5_cooperative_pair(item, source)
            for item in cooperative_rows
        ]
    cooperative_aggregate = _cooperative_corrected_aggregate(payload)
    if cooperative_aggregate:
        return [_normalize_d5_cooperative_aggregate(cooperative_aggregate, source)]

    records = _record_list(
        payload,
        ("summaries", "per_primary", "evidence", "rows", "records"),
    )
    if not records and any(
        key in payload
        for key in ("independently_locked", "assigned_global_track_id", "resource_id")
    ):
        records = [dict(payload)]
    rows: list[dict[str, Any]] = []
    for item in records:
        independently_locked = _first(
            item, "independently_locked", "per_primary_locked", "locked"
        )
        reasons_available = any(
            key in item
            for key in ("rejection_reasons", "failure_reasons", "failure_reason")
        )
        reasons = _failure_reasons(item)
        truth_used = int(bool(_first(item, "truth_identity_used", "truth_identity_used_online")))
        truth_used += _optional_int(item.get("online_truth_use_count")) or 0
        rewrite_count = _first(
            item, "global_track_id_rewrite_count", "id_rewrite_count"
        )
        rows.append(
            _finish_row(
                {
                    "source": "d5_per_primary",
                    "family": "per_primary_terminal_association",
                    "scenario_id": _first(item, "scenario_id", "episode_id", "case_id"),
                    "seed": item.get("seed"),
                    "resource_count": item.get("resource_count"),
                    "target_count": item.get("target_count"),
                    "resource_id": item.get("resource_id"),
                    "target_id": _first(
                        item, "assigned_global_track_id", "global_track_id", "target_id"
                    ),
                    "terminal_authorization_scope": item.get(
                        "terminal_authorization_scope"
                    ),
                    "arrival_coordination_required": item.get(
                        "arrival_coordination_required"
                    ),
                    "per_primary_evidence_count": 1,
                    "independently_locked_count": (
                        int(bool(independently_locked))
                        if independently_locked is not None
                        else None
                    ),
                    "per_primary_lock_rate": (
                        float(bool(independently_locked))
                        if independently_locked is not None
                        else None
                    ),
                    "global_track_id_rewrite_count": rewrite_count,
                    "failure_reasons": reasons,
                    "failure_reasons_availability": (
                        "available" if reasons_available else "unavailable"
                    ),
                    "online_truth_use_count": truth_used,
                },
                source,
            )
        )
    return rows


def _normalize_d5_cooperative_pair(
    item: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    active_primary = bool(item.get("active_primary"))
    associated = item.get("associated") if active_primary else None
    common_lock = item.get("common_lock") if active_primary else None
    reasons = _failure_reasons(item) if active_primary else ()
    return _finish_row(
        {
            "source": "d5_per_primary",
            "family": (
                "cooperative_active_primary_association"
                if active_primary
                else "cooperative_reserve_safety"
            ),
            "scenario_id": _first(item, "case_id", "scenario_id"),
            "seed": item.get("seed"),
            "resource_count": item.get("resource_count"),
            "target_count": item.get("target_count"),
            "resource_id": item.get("resource_id"),
            "target_id": _first(item, "target_id", "global_track_id"),
            "candidate": _first(item, "profile", "candidate_id"),
            "per_primary_evidence_count": 1 if active_primary else None,
            "per_primary_visible_count": (
                int(bool(item.get("visible")))
                if active_primary and "visible" in item
                else None
            ),
            "per_primary_associated_count": (
                int(bool(associated)) if associated is not None else None
            ),
            # In this persisted AirSim schema, `associated` is emitted only
            # after D5 wrote decision_state=locked for the pair.
            "independently_locked_count": (
                int(bool(associated)) if associated is not None else None
            ),
            "per_primary_lock_rate": (
                float(bool(associated)) if associated is not None else None
            ),
            "per_primary_common_lock_count": (
                int(bool(common_lock)) if common_lock is not None else None
            ),
            "global_track_id_rewrite_count": _optional_int(
                item.get("global_track_id_rewrite_count")
            ),
            "failure_reasons": reasons,
            "failure_reasons_availability": (
                "available"
                if active_primary and "first_failure_reason" in item
                else "not_applicable" if not active_primary else "unavailable"
            ),
            "online_truth_use_count": None,
        },
        source,
    )


def _normalize_d5_cooperative_aggregate(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    pair_funnel = _mapping(_mapping(payload.get("funnels")).get("pair"))
    visible = _mapping(pair_funnel.get("visible"))
    associated = _mapping(pair_funnel.get("associated"))
    common_lock = _mapping(payload.get("common_lock"))
    checks = _mapping(_mapping(payload.get("acceptance")).get("checks"))
    rewrite = _mapping(checks.get("global_track_id_rewrite_zero"))
    return _finish_row(
        {
            "source": "d5_per_primary",
            "family": "cooperative_corrected_aggregate",
            "scenario_id": _first(
                _mapping(payload.get("primary_source")),
                "calibration_suite",
                "scenario_version",
            ),
            "per_primary_evidence_count": _optional_int(associated.get("available")),
            "per_primary_visible_count": _optional_int(visible.get("passed")),
            "per_primary_associated_count": _optional_int(associated.get("passed")),
            "independently_locked_count": _optional_int(associated.get("passed")),
            "per_primary_lock_rate": associated.get("rate"),
            "common_lock_count": _optional_int(common_lock.get("passed")),
            "common_lock_opportunity_count": _optional_int(
                common_lock.get("available")
            ),
            "global_track_id_rewrite_count": _optional_int(rewrite.get("count")),
            "failure_reasons": (),
            "failure_reasons_availability": "unavailable",
            "online_truth_use_count": None,
        },
        source,
    )


def _normalize_d2(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    direct = _record_list(payload, ("profiles", "rows", "records", "per_profile"))
    rows: list[dict[str, Any]] = []
    for item in direct:
        metrics = _mapping(item.get("metrics")) or item
        rows.append(_d2_row(item, metrics, source))
    if rows:
        return rows

    decision = _mapping(payload.get("decision"))
    for stage_name in ("screening", "confirmation"):
        stage = _mapping(payload.get(stage_name))
        for result in _mapping_rows(stage.get("results")):
            rows.extend(
                _d2_result_seed_rows(
                    result,
                    stage_name=stage_name,
                    decision=decision,
                    source=source,
                )
            )
        jpda_stage = _mapping(_mapping(payload.get("jpda_comparison")).get(stage_name))
        jpda_result = _mapping(jpda_stage.get("result"))
        if jpda_result:
            rows.extend(
                _d2_result_seed_rows(
                    jpda_result,
                    stage_name=f"jpda_{stage_name}",
                    decision=decision,
                    source=source,
                )
            )
    if rows:
        return rows

    difficulty = _mapping(payload.get("difficulty_results"))
    for stage_name, stage_payload in difficulty.items():
        by_difficulty = _mapping(_mapping(stage_payload).get("by_difficulty"))
        for profile, profile_payload in by_difficulty.items():
            profile_map = _mapping(profile_payload)
            candidates = [
                (name, _mapping(value))
                for name, value in profile_map.items()
                if isinstance(value, Mapping) and isinstance(value.get("metrics"), Mapping)
            ]
            for candidate, candidate_payload in candidates:
                admission = _mapping(profile_map.get("admission"))
                promotion_candidates = set(
                    str(value)
                    for value in _sequence(admission.get("promotion_candidates"))
                )
                candidate_id = str(
                    _first(candidate_payload, "config_id", "associator") or candidate
                )
                admitted = (
                    candidate_id in promotion_candidates
                    if admission.get("available") is True
                    else None
                )
                item = {
                    "scenario_difficulty": profile,
                    "candidate": candidate,
                    "stage": stage_name,
                    "seed_count": profile_map.get("seed_count"),
                    "metrics": candidate_payload.get("metrics"),
                    "online_truth_use_count": candidate_payload.get(
                        "online_truth_leakage_count"
                    ),
                    "association_admitted": admitted,
                    "admission_reasons": admission.get("reasons", ()),
                    "scenario_still_non_discriminative": profile_map.get(
                        "scenario_still_non_discriminative"
                    ),
                }
                rows.append(_d2_row(item, _mapping(item["metrics"]), source))
    if rows:
        return rows

    confirmation = _mapping(payload.get("confirmation"))
    for item in _mapping_rows(confirmation.get("results")):
        aggregate = _mapping(item.get("aggregate"))
        row_item = dict(item)
        row_item["scenario_difficulty"] = _first(
            item, "scenario_difficulty", "profile"
        )
        rows.append(_d2_row(row_item, aggregate, source))
    return rows


def _d2_result_seed_rows(
    result: Mapping[str, Any],
    *,
    stage_name: str,
    decision: Mapping[str, Any],
    source: Mapping[str, Any],
) -> list[dict[str, Any]]:
    config = _mapping(result.get("config"))
    candidate = str(
        _first(config, "config_id")
        or _first(result, "candidate_id", "associator")
        or "unspecified"
    )
    assessment = next(
        (
            item
            for item in _mapping_rows(decision.get("candidate_assessments"))
            if str(_first(item, "candidate_id", "config_id")) == candidate
        ),
        None,
    )
    admitted = (
        bool(assessment.get("all_thresholds_passed"))
        if assessment is not None
        else None
    )
    reasons = _d2_assessment_failure_reasons(assessment or {})
    per_seed = _mapping_rows(result.get("per_seed"))
    return [
        _d2_row(
            {
                **item,
                "stage": stage_name,
                "candidate": candidate,
                "associator": result.get("associator"),
                "association_admitted": admitted,
                "admission_reasons": reasons,
                "failure_reasons": reasons,
                "failure_reasons_availability": (
                    "available" if assessment is not None else "unavailable"
                ),
            },
            item,
            source,
        )
        for item in per_seed
    ]


def _d2_row(
    item: Mapping[str, Any], metrics: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    leakage = _metric_value(metrics.get("online_truth_leakage_count"), prefer="sum")
    if leakage is None:
        leakage = _metric_value(item.get("online_truth_use_count"), prefer="sum")
    admitted = _first(item, "association_admitted", "admitted")
    return _finish_row(
        {
            "source": "d2_difficulty_profiles",
            "family": "association_difficulty_profile",
            "scenario_id": _first(item, "scenario_id", "replay_name", "stage"),
            "scenario_difficulty": _first(
                item, "scenario_difficulty", "profile", "difficulty"
            ),
            "seed": item.get("seed"),
            "target_count": item.get("target_count"),
            "candidate": _first(item, "candidate", "config_id", "associator"),
            "id_switch_count": _metric_value(metrics.get("id_switch_count"), prefer="sum"),
            "track_continuity": _metric_value(
                _first_mapping_value(metrics, "identity_continuity", "track_continuity"),
                prefer="mean",
            ),
            "false_track_count": _metric_value(
                metrics.get("false_track_count"), prefer="sum"
            ),
            "track_rmse": _metric_value(metrics.get("rmse"), prefer="mean"),
            "p95_loop_latency_s": _metric_value(
                metrics.get("p95_loop_latency_s"), prefer="mean"
            ),
            "scenario_still_non_discriminative": item.get(
                "scenario_still_non_discriminative"
            ),
            "association_admitted": admitted,
            "admission_reasons": _first(item, "admission_reasons", "reasons") or (),
            "failure_reasons": _first(
                item, "failure_reasons", "admission_reasons", "reasons"
            ) or (),
            "failure_reasons_availability": item.get(
                "failure_reasons_availability",
                "available"
                if any(
                    key in item
                    for key in ("failure_reasons", "admission_reasons", "reasons")
                )
                else "unavailable",
            ),
            "online_truth_use_count": leakage,
        },
        source,
    )


def _normalize_d3(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    cooperative_rows = _cooperative_pair_rows(payload)
    if cooperative_rows:
        return _normalize_d3_cooperative_roles(cooperative_rows, source)

    records = _record_list(payload, ("plans", "rows", "records", "history"))
    if not records:
        records = [payload]
    metadata_records = [
        record for record in records if isinstance(record, Mapping)
    ]
    plan_versions = [_optional_int(_first(item, "plan_version", "version")) for item in metadata_records]
    coalition_versions: dict[str, list[int | None]] = {}
    coalition_epochs: dict[str, list[int | None]] = {}
    membership_changes = 0
    membership_holds = 0
    for item in metadata_records:
        metadata = _mapping(item.get("metadata"))
        change_records = _mapping_rows(metadata.get("membership_change_records"))
        membership_changes += len(change_records)
        membership_changes += _optional_int(item.get("membership_change_count")) or 0
        membership_holds += int(bool(metadata.get("membership_held", False)))
        membership_holds += _optional_int(item.get("membership_hold_count")) or 0
        coalitions = _mapping_rows(item.get("coalitions"))
        if coalitions:
            for index, coalition in enumerate(coalitions):
                coalition_id = str(
                    _first(coalition, "coalition_id", "target_id") or f"index:{index}"
                )
                coalition_versions.setdefault(coalition_id, []).append(
                    _optional_int(coalition.get("version"))
                )
                coalition_epochs.setdefault(coalition_id, []).append(
                    _optional_int(coalition.get("epoch"))
                )
        else:
            coalition_versions.setdefault("default", []).append(
                _optional_int(_first(item, "coalition_version"))
            )
            coalition_epochs.setdefault("default", []).append(
                _optional_int(_first(item, "coalition_epoch", "epoch"))
            )

    last = metadata_records[-1]
    last_metadata = _mapping(last.get("metadata"))
    scope = _first(last, "terminal_authorization_scope") or _first(
        last_metadata, "terminal_authorization_scope"
    )
    arrival = _first(last, "arrival_coordination_required")
    if arrival is None:
        arrival = _first(last_metadata, "arrival_coordination_required")
    last_assignments = _mapping_rows(last.get("assignments"))
    latest_plan_version = next(
        (version for version in reversed(plan_versions) if version is not None),
        None,
    )
    latest_records = [
        item
        for item in metadata_records
        if _optional_int(_first(item, "plan_version", "version"))
        == latest_plan_version
    ]
    role_records = last_assignments or latest_records or metadata_records
    roles_explicit = bool(last_assignments) or any("member_role" in item for item in metadata_records)
    primary_count = sum(
        str(item.get("member_role", "")).lower()
        in {"primary", "lead_primary", "support_primary"}
        for item in role_records
    )
    reserve_count = sum(
        str(item.get("member_role", "")).lower() == "reserve"
        for item in role_records
    )
    reserve_standby = sum(
        str(item.get("member_role", "")).lower() == "reserve"
        and str(item.get("activation_state", "standby")).lower() == "standby"
        and item.get("active") is not True
        for item in role_records
    )
    d3_failure_reasons = tuple(
        reason
        for item in metadata_records
        for reason in _failure_reasons(item)
        if reason
    )
    row = {
        "source": "d3_assignment_churn",
        "family": "assignment_membership_churn",
        "scenario_id": _first(payload, "scenario_id", "profile_id"),
        "seed": payload.get("seed"),
        "resource_count": _first(last, "resource_count") or payload.get("resource_count"),
        "target_count": _first(last, "target_count") or payload.get("target_count"),
        "terminal_authorization_scope": scope,
        "arrival_coordination_required": arrival,
        "membership_change_count": _prefer_explicit(
            payload.get("membership_change_count"), membership_changes
        ),
        "membership_hold_count": _prefer_explicit(
            payload.get("membership_hold_count"), membership_holds
        ),
        "plan_version_churn_count": _prefer_explicit(
            payload.get("plan_version_churn_count"), _change_count(plan_versions)
        ),
        "coalition_version_churn_count": _prefer_explicit(
            payload.get("coalition_version_churn_count"),
            sum(_change_count(values) for values in coalition_versions.values()),
        ),
        "coalition_epoch_churn_count": _prefer_explicit(
            payload.get("coalition_epoch_churn_count"),
            sum(_change_count(values) for values in coalition_epochs.values()),
        ),
        "primary_assignment_count": primary_count if roles_explicit else None,
        "reserve_assignment_count": reserve_count if roles_explicit else None,
        "reserve_standby_count": reserve_standby if roles_explicit else None,
        "stale_reject_count": _coalesce(
            payload.get("stale_reject_count"),
            _max_optional_int(item.get("stale_reject_count") for item in metadata_records),
        ),
        "plan_rollback_detected_count": _coalesce(
            payload.get("plan_rollback_detected_count"),
            int(any(bool(item.get("plan_rollback_detected")) for item in metadata_records))
            if any("plan_rollback_detected" in item for item in metadata_records)
            else None,
        ),
        "failure_reasons": d3_failure_reasons,
        "failure_reasons_availability": (
            "available"
            if any(
                any(key in item for key in ("failure_reasons", "failure_reason", "stale_reject_reason"))
                for item in metadata_records
            )
            else "unavailable"
        ),
        "online_truth_use_count": _optional_int(payload.get("online_truth_use_count")),
    }
    return [_finish_row(row, source)]


def _normalize_d3_cooperative_roles(
    records: Sequence[Mapping[str, Any]], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    by_case: dict[str, list[Mapping[str, Any]]] = {}
    for item in records:
        case_id = str(_first(item, "case_id", "scenario_id") or "unspecified")
        by_case.setdefault(case_id, []).append(item)
    rows: list[dict[str, Any]] = []
    for case_id, items in sorted(by_case.items()):
        first = items[0]
        primaries = [item for item in items if bool(item.get("active_primary"))]
        reserves = [
            item
            for item in items
            if str(item.get("member_role", "")).lower() == "reserve"
        ]
        rows.append(
            _finish_row(
                {
                    "source": "d3_assignment_churn",
                    "family": "cooperative_case_roles",
                    "scenario_id": case_id,
                    "seed": first.get("seed"),
                    "resource_count": first.get("resource_count"),
                    "target_count": first.get("target_count"),
                    "candidate": _first(first, "profile", "candidate_id"),
                    "primary_assignment_count": len(primaries),
                    "reserve_assignment_count": len(reserves),
                    "reserve_standby_count": sum(
                        not bool(item.get("active_primary")) for item in reserves
                    ),
                    "failure_reasons": (),
                    "failure_reasons_availability": "unavailable",
                    "online_truth_use_count": None,
                },
                source,
            )
        )
    return rows


def _normalize_d4(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    cases = _mapping_rows(payload.get("cases"))
    if not cases:
        cases = [payload]
    rows: list[dict[str, Any]] = []
    for case in cases:
        ticks = _mapping_rows(case.get("ticks"))
        if not ticks and "timestamp_s" in case:
            ticks = [case]
        if not ticks:
            rows.append(_normalize_d4_case_summary(case, payload, source))
            continue
        layers = [tick.get("selected_layer") for tick in ticks]
        owners = [tick.get("owner_id") for tick in ticks]
        epochs = [_optional_int(tick.get("epoch")) for tick in ticks]
        plan_versions = [_optional_int(tick.get("plan_version")) for tick in ticks]
        coalition_versions = [
            _optional_int(tick.get("coalition_version")) for tick in ticks
        ]
        states = Counter(str(tick.get("commit_state", "unknown")) for tick in ticks)
        execution_allowed = sum(bool(tick.get("execution_allowed")) for tick in ticks)
        failovers = sum(
            current != previous and current not in {None, "center"}
            for previous, current in zip(layers, layers[1:])
        )
        rows.append(
            _finish_row(
                {
                    "source": "d4_episode_communication",
                    "family": "episode_communication_failover",
                    "scenario_id": _coalesce(
                        _first(case, "scenario_id"), _first(payload, "scenario_id")
                    ),
                    "seed": _coalesce(_first(case, "seed"), payload.get("seed")),
                    "resource_count": _coalesce(
                        _first(case, "resource_count"), payload.get("resource_count")
                    ),
                    "target_count": _coalesce(
                        _first(case, "target_count"), payload.get("target_count")
                    ),
                    "selected_layer": layers[-1],
                    "owner_id": owners[-1],
                    "commit_state_counts": dict(states),
                    "failover_count": failovers,
                    "ack_count": _ack_event_count(ticks),
                    "missing_ack_count": sum(
                        len(_sequence(tick.get("missing_member_ids"))) for tick in ticks
                    ),
                    "rejected_ack_count": sum(
                        len(_sequence(tick.get("rejected_ack_reasons"))) for tick in ticks
                    ),
                    "lease_invalid_count": sum(
                        tick.get("lease_valid") is False for tick in ticks
                    ),
                    "owner_change_count": _adjacent_change_count(owners),
                    "plan_version_churn_count": _change_count(plan_versions),
                    "coalition_version_churn_count": _change_count(coalition_versions),
                    "coalition_epoch_churn_count": _change_count(epochs),
                    "execution_allowed_count": execution_allowed,
                    "execution_allowed_rate": execution_allowed / len(ticks),
                    "fail_closed_count": sum(bool(tick.get("fail_closed")) for tick in ticks),
                    "fault_case_passed": case.get("passed"),
                    "secondary_takeover_latency_s": _layer_execution_latency(
                        ticks, "secondary"
                    ),
                    "distributed_commit_latency_s": _layer_execution_latency(
                        ticks, "distributed"
                    ),
                    "failure_reasons": _d4_failure_reasons(case, ticks),
                    "failure_reasons_availability": (
                        "available"
                        if "failure_reasons" in case
                        or any("rejected_ack_reasons" in tick for tick in ticks)
                        else "unavailable"
                    ),
                    "online_truth_use_count": _optional_int(
                        case.get("online_truth_use_count")
                    ),
                },
                source,
            )
        )
    return rows


def _normalize_d4_case_summary(
    case: Mapping[str, Any],
    payload: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    layer_trace = list(_sequence(case.get("layer_trace")))
    selected_layer = _coalesce(
        _first(case, "selected_layer", "expected_layer"),
        layer_trace[-1] if layer_trace else None,
    )
    acked = _sequence(case.get("acked_member_ids"))
    missing = _sequence(case.get("missing_member_ids"))
    lease_expiry = case.get("lease_expires_at")
    execution_allowed = case.get("execution_allowed")
    fail_closed = case.get("fail_closed")
    return _finish_row(
        {
            "source": "d4_episode_communication",
            "family": "episode_communication_fault_case",
            "scenario_id": _coalesce(
                _first(case, "scenario_id"), _first(payload, "scenario_id")
            ),
            "seed": _coalesce(case.get("seed"), payload.get("seed")),
            "resource_count": _coalesce(
                case.get("resource_count"), payload.get("resource_count")
            ),
            "target_count": _coalesce(
                case.get("target_count"), payload.get("target_count")
            ),
            "selected_layer": selected_layer,
            "owner_id": case.get("owner_id"),
            "commit_state_counts": (
                {str(case.get("commit_state")): 1}
                if case.get("commit_state") is not None
                else {}
            ),
            "failover_count": _adjacent_change_count(layer_trace),
            "ack_count": len(acked) if "acked_member_ids" in case else None,
            "missing_ack_count": len(missing) if "missing_member_ids" in case else None,
            "rejected_ack_count": case.get("rejected_ack_count"),
            "lease_invalid_count": (
                int(lease_expiry is None)
                if "lease_expires_at" in case
                and selected_layer not in {None, "center"}
                else None
            ),
            "owner_change_count": case.get("owner_change_count"),
            "plan_version_churn_count": case.get("plan_version_churn_count"),
            "coalition_version_churn_count": case.get(
                "coalition_version_churn_count"
            ),
            "coalition_epoch_churn_count": case.get("coalition_epoch_churn_count"),
            "execution_allowed_count": (
                int(bool(execution_allowed))
                if execution_allowed is not None
                else None
            ),
            "execution_allowed_rate": (
                float(bool(execution_allowed))
                if execution_allowed is not None
                else None
            ),
            "fail_closed_count": (
                int(bool(fail_closed)) if fail_closed is not None else None
            ),
            "fault_case_passed": case.get("passed"),
            "secondary_takeover_latency_s": _first(
                case, "secondary_takeover_latency_s", "secondary_activation_latency_s"
            ),
            "distributed_commit_latency_s": _first(
                case, "distributed_commit_latency_s", "recovery_time_s"
            ) if selected_layer == "distributed" else None,
            "failure_reasons": _failure_reasons(case),
            "failure_reasons_availability": (
                "available"
                if any(key in case for key in ("failure_reasons", "first_failure_reason"))
                else "unavailable"
            ),
            "online_truth_use_count": case.get("online_truth_use_count"),
        },
        source,
    )


def _normalize_d7(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> list[dict[str, Any]]:
    cooperative_rows = _cooperative_pair_rows(payload)
    profile_summaries = _cooperative_profile_summaries(payload)
    if cooperative_rows or profile_summaries:
        rows = [
            _normalize_d7_cooperative_pair(item, source)
            for item in cooperative_rows
        ]
        rows.extend(
            _normalize_d7_cooperative_profile_rows(payload, profile_summaries, source)
        )
        safety = _normalize_d7_cooperative_safety(payload, source)
        if safety is not None:
            rows.append(safety)
        return rows

    records = _record_list(
        payload,
        ("summaries", "pair_diagnostics", "rows", "records", "per_seed", "pairs"),
    )
    if not records:
        records = [payload]
    rows: list[dict[str, Any]] = []
    for item in records:
        rows.append(
            _finish_row(
                {
                    "source": "d7_per_primary",
                    "family": "per_primary_terminal_layers",
                    "scenario_id": _first(item, "scenario_id", "case_id"),
                    "seed": item.get("seed"),
                    "resource_count": item.get("resource_count"),
                    "target_count": item.get("target_count"),
                    "resource_id": item.get("resource_id"),
                    "target_id": _first(item, "target_id", "assigned_global_track_id"),
                    "candidate": _first(item, "candidate_id", "profile"),
                    "terminal_authorization_scope": item.get(
                        "terminal_authorization_scope"
                    ),
                    "arrival_coordination_required": item.get(
                        "arrival_coordination_required"
                    ),
                    "contract_allowed_count": _explicit_count(
                        item,
                        count_names=(
                            "contract_allowed_count",
                            "terminal_contract_allowed_count",
                        ),
                        boolean_names=(
                            "contract_allowed",
                            "terminal_contract_reached",
                            "terminal_contract_allowed",
                        ),
                    ),
                    "control_allowed_count": _explicit_count(
                        item,
                        count_names=(
                            "control_allowed_count",
                            "terminal_switch_allowed_count",
                        ),
                        boolean_names=(
                            "control_allowed",
                            "terminal_control_reached",
                            "terminal_control_allowed",
                        ),
                    ),
                    "mode_switched_count": _explicit_count(
                        item,
                        count_names=("mode_switched_count", "mode_switch_count"),
                        boolean_names=(
                            "mode_switched",
                            "terminal_mode_reached",
                            "terminal_mode_entered",
                        ),
                    ),
                    "physical_intercept_count": _explicit_count(
                        item,
                        count_names=(
                            "physical_intercept_count",
                            "intercept_success_count",
                        ),
                        boolean_names=(
                            "physical_intercept",
                            "physical_intercept_reached",
                        ),
                    ),
                    "per_primary_authorization_active_count": item.get(
                        "per_primary_authorization_active_count"
                    ),
                    "coalition_visual_completion_bypassed_count": item.get(
                        "coalition_visual_completion_bypassed_count"
                    ),
                    "bypassed_arrival_only_count": item.get(
                        "bypassed_arrival_only_count"
                    ),
                    "pair_opportunity_count": _coalesce(
                        item.get("pair_opportunity_count"),
                        1 if _first(item, "assignment_id", "resource_id") is not None else None,
                    ),
                    "coalition_completion_count": _explicit_count(
                        item,
                        count_names=("coalition_completion_count",),
                        boolean_names=("coalition_complete",),
                    ),
                    "reserve_unauthorized_count": _coalesce(
                        item.get("reserve_unauthorized_count"),
                        int(bool(item.get("reserve_unauthorized")))
                        if "reserve_unauthorized" in item
                        else None,
                    ),
                    "closest_approach_m": _first(
                        item, "closest_approach_m", "closest_range_m"
                    ),
                    "failure_reasons": _failure_reasons(item),
                    "failure_reasons_availability": (
                        "available"
                        if any(
                            key in item
                            for key in (
                                "first_failure_reason",
                                "failure_reason",
                                "failure_reasons",
                                "rejection_reasons",
                            )
                        )
                        else "unavailable"
                    ),
                    "online_truth_use_count": item.get("online_truth_use_count"),
                },
                source,
            )
        )
    return rows


def _normalize_d7_cooperative_pair(
    item: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    active_primary = bool(item.get("active_primary"))
    reasons = _failure_reasons(item) if active_primary else ()
    return _finish_row(
        {
            "source": "d7_per_primary",
            "family": (
                "cooperative_active_primary_layers"
                if active_primary
                else "cooperative_reserve_safety"
            ),
            "scenario_id": _first(item, "case_id", "scenario_id"),
            "seed": item.get("seed"),
            "resource_count": item.get("resource_count"),
            "target_count": item.get("target_count"),
            "resource_id": item.get("resource_id"),
            "target_id": item.get("target_id"),
            "candidate": _first(item, "profile", "candidate_id"),
            "contract_allowed_count": _active_boolean_count(
                item, "contract_allowed", active=active_primary
            ),
            "control_allowed_count": _active_boolean_count(
                item, "control_allowed", active=active_primary
            ),
            "mode_switched_count": _active_boolean_count(
                item, "mode_switched", active=active_primary
            ),
            "physical_intercept_count": _active_boolean_count(
                item, "physical_intercept", active=active_primary
            ),
            "pair_opportunity_count": 1 if active_primary else None,
            "reserve_unauthorized_count": (
                int(bool(item.get("reserve_unauthorized")))
                if str(item.get("member_role", "")).lower() == "reserve"
                and "reserve_unauthorized" in item
                else None
            ),
            "closest_approach_m": (
                _first(item, "closest_approach_m", "closest_range_m")
                if active_primary
                else None
            ),
            "failure_reasons": reasons,
            "failure_reasons_availability": (
                "available"
                if active_primary and "first_failure_reason" in item
                else "not_applicable" if not active_primary else "unavailable"
            ),
            "online_truth_use_count": _optional_int(
                item.get("online_truth_use_count")
            ),
        },
        source,
    )


def _normalize_d7_cooperative_profile_rows(
    payload: Mapping[str, Any],
    summaries: Sequence[Mapping[str, Any]],
    source: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected_profile, selection_source = _cooperative_selected_profile(payload)
    resource_count, target_count = _cooperative_explicit_scale(payload)
    rows: list[dict[str, Any]] = []
    for item in summaries:
        funnel = _mapping(item.get("funnel"))
        profile = str(item.get("profile") or "unspecified")
        rows.append(
            _finish_row(
                {
                    "source": "d7_per_primary",
                    "family": "cooperative_profile_summary",
                    "scenario_id": _cooperative_scenario_id(payload),
                    "resource_count": resource_count,
                    "target_count": target_count,
                    "candidate": profile,
                    "candidate_selected": (
                        profile == selected_profile if selected_profile is not None else None
                    ),
                    "profile_selection_source": selection_source,
                    "contract_allowed_count": _optional_int(
                        funnel.get("contract_allowed")
                    ),
                    "control_allowed_count": _optional_int(
                        funnel.get("control_allowed")
                    ),
                    "mode_switched_count": _optional_int(funnel.get("mode_switched")),
                    "physical_intercept_count": _optional_int(
                        funnel.get("physical_intercept")
                    ),
                    "case_opportunity_count": _optional_int(item.get("seed_count")),
                    "pair_opportunity_count": _optional_int(
                        item.get("pair_opportunity_count")
                    ),
                    "coalition_opportunity_count": _optional_int(
                        item.get("coalition_opportunity_count")
                    ),
                    "coalition_completion_count": _optional_int(
                        item.get("coalition_completion_count")
                    ),
                    "failure_reasons": tuple(
                        str(reason)
                        for reason, count in _mapping(
                            item.get("second_primary_failure_distribution")
                        ).items()
                        for _ in range(int(count))
                    ),
                    "failure_reasons_availability": (
                        "available"
                        if "second_primary_failure_distribution" in item
                        else "unavailable"
                    ),
                    "online_truth_use_count": None,
                },
                source,
            )
        )
    return rows


def _normalize_d7_cooperative_safety(
    payload: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any] | None:
    corrected = _cooperative_corrected_aggregate(payload)
    if not corrected:
        return None
    checks = _mapping(_mapping(corrected.get("acceptance")).get("checks"))
    reserve = _mapping(checks.get("reserve_unauthorized_zero"))
    truth = _mapping(checks.get("online_truth_use_zero"))
    if not reserve and not truth:
        return None
    return _finish_row(
        {
            "source": "d7_per_primary",
            "family": "cooperative_corrected_safety",
            "scenario_id": _cooperative_scenario_id(corrected),
            "reserve_unauthorized_count": _optional_int(reserve.get("count")),
            "online_truth_use_count": _optional_int(truth.get("count")),
            "failure_reasons": (),
            "failure_reasons_availability": "unavailable",
        },
        source,
    )


def _finish_row(row: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {field: None for field in ROW_FIELDS}
    normalized.update(row)
    normalized["source_schema_version"] = source.get("schema_version")
    normalized["source_sha256"] = source.get("sha256")
    normalized["producer"] = normalized.get("producer") or source.get("producer")
    normalized["run_id"] = normalized.get("run_id") or source.get("run_id")
    normalized["provenance"] = normalized.get("provenance") or source.get(
        "provenance"
    )
    normalized["evidence_path"] = normalized.get("evidence_path") or source.get(
        "evidence_path"
    )
    normalized["failure_reasons"] = tuple(
        str(reason)
        for reason in _sequence(normalized.get("failure_reasons"))
        if str(reason).strip()
    )
    if normalized.get("failure_reasons_availability") not in {
        "available",
        "unavailable",
        "not_applicable",
    }:
        normalized["failure_reasons_availability"] = "unavailable"
    for name in METRIC_NAMES:
        availability_name = f"{name}_availability"
        explicit = normalized.get(availability_name)
        if explicit in {"unavailable", "not_applicable"}:
            normalized[name] = None
            normalized[availability_name] = explicit
        else:
            normalized[availability_name] = (
                "available" if normalized.get(name) is not None else "unavailable"
            )
    return normalized


def _build_aggregate(
    rows: Sequence[Mapping[str, Any]], manifest: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    by_source: dict[str, Any] = {}
    for source_name in SOURCE_NAMES:
        source_rows = [row for row in rows if row.get("source") == source_name]
        by_source[source_name] = {
            "row_count": len(source_rows),
            "metrics": {
                name: _metric_summary(source_rows, name) for name in METRIC_NAMES
            },
            "failure_reason_distribution": _failure_reason_summary(source_rows),
        }
    d2_rows = [row for row in rows if row.get("source") == "d2_difficulty_profiles"]
    d1_rows = [row for row in rows if row.get("source") == "d1_dense_crossing"]
    d5_rows = [row for row in rows if row.get("source") == "d5_native_mot"]
    d5_primary_rows = [row for row in rows if row.get("source") == "d5_per_primary"]
    d7_rows = [row for row in rows if row.get("source") == "d7_per_primary"]
    d7_profile_rows = [
        row
        for row in d7_rows
        if row.get("family") == "cooperative_profile_summary"
    ]
    d7_pair_rows = [
        row
        for row in d7_rows
        if row.get("family") == "cooperative_active_primary_layers"
    ]
    d7_layer_rows = d7_pair_rows or d7_profile_rows or d7_rows
    online_truth_total = _sum_available(rows, "online_truth_use_count")
    return {
        "schema_version": P1_SYSTEM_EVIDENCE_SCHEMA_VERSION,
        "offline_only": True,
        "controls_air_sim": False,
        "source_manifest": dict(manifest),
        "row_count": len(rows),
        "actual_scale_policy": "explicit_fields_only",
        "truth_policy": {
            "online_truth_allowed": False,
            "raw_truth_identifiers_exported": False,
            "online_truth_use_count": online_truth_total,
            "status": (
                "unavailable"
                if online_truth_total is None
                else "pass" if online_truth_total == 0 else "fail"
            ),
        },
        "by_source": by_source,
        "d1_by_target_spacing_m": _group_metrics(
            d1_rows,
            "target_spacing_m",
            (
                "accepted_observation_count",
                "rejected_observation_count",
                "dual_timestamp_coverage_rate",
                "covariance_coverage_rate",
                "source_lineage_coverage_rate",
                "d1_replay_contract_complete",
            ),
        ),
        "d2_by_difficulty": _group_metrics(
            d2_rows,
            "scenario_difficulty",
            ("id_switch_count", "track_continuity", "false_track_count", "track_rmse", "p95_loop_latency_s"),
        ),
        "d5_by_backend": _group_metrics(
            d5_rows,
            "backend",
            ("native_active_frame_rate", "fallback_frame_count", "detector_precision", "detector_recall", "local_continuity", "terminal_local_id_switch_count", "p95_processing_latency_ms", "native_mot_admitted"),
        ),
        "d5_per_primary": {
            name: _metric_summary(d5_primary_rows, name)
            for name in (
                "per_primary_evidence_count",
                "per_primary_visible_count",
                "per_primary_associated_count",
                "independently_locked_count",
                "per_primary_common_lock_count",
                "common_lock_count",
                "common_lock_opportunity_count",
                "global_track_id_rewrite_count",
            )
        },
        "d7_terminal_layers": {
            name: _metric_summary(d7_layer_rows, name)
            for name in (
                "contract_allowed_count",
                "control_allowed_count",
                "mode_switched_count",
                "physical_intercept_count",
            )
        },
        "d7_cooperative_closure": _d7_cooperative_closure_summary(
            d7_rows,
            d7_profile_rows,
        ),
        "metric_availability": {
            name: _availability_summary(rows, name) for name in METRIC_NAMES
        },
        "failure_reason_distribution": _failure_reason_summary(rows),
        "bootstrap": {
            "method": "percentile_mean_95_ci",
            "resamples": BOOTSTRAP_RESAMPLES,
            "rng_seed": BOOTSTRAP_RNG_SEED,
            "minimum_available_samples": 2,
        },
    }


def _group_metrics(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    names: Sequence[str],
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        value = str(row.get(key) or "unspecified")
        groups.setdefault(value, []).append(row)
    return {
        group: {
            "row_count": len(group_rows),
            "metrics": {name: _metric_summary(group_rows, name) for name in names},
        }
        for group, group_rows in sorted(groups.items())
    }


def _d7_cooperative_closure_summary(
    d7_rows: Sequence[Mapping[str, Any]],
    profile_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = [row for row in profile_rows if row.get("candidate_selected") is True]
    selected_profile = selected[0].get("candidate") if len(selected) == 1 else None
    selection_source = (
        selected[0].get("profile_selection_source") if len(selected) == 1 else None
    )
    metric_names = (
        "case_opportunity_count",
        "pair_opportunity_count",
        "coalition_opportunity_count",
        "coalition_completion_count",
    )
    return {
        "status": "available" if profile_rows else "unavailable",
        "profile_count": len(profile_rows),
        "selected_profile": selected_profile,
        "profile_selection_source": selection_source,
        "overall": {
            name: _metric_summary(profile_rows, name) for name in metric_names
        },
        "by_profile": _group_metrics(
            profile_rows,
            "candidate",
            metric_names,
        ),
        "reserve_unauthorized_count": _metric_summary(
            d7_rows, "reserve_unauthorized_count"
        ),
        "online_truth_use_count": _metric_summary(
            d7_rows, "online_truth_use_count"
        ),
    }


def _metric_summary(rows: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any]:
    values = [row.get(name) for row in rows if row.get(name) is not None]
    numeric = [float(value) for value in values if isinstance(value, (bool, int, float))]
    by_seed: dict[str, list[float]] = {}
    for row in rows:
        value = row.get(name)
        seed = row.get("seed")
        if seed is None or not isinstance(value, (bool, int, float)):
            continue
        by_seed.setdefault(str(seed), []).append(float(value))
    per_seed = [sum(seed_values) / len(seed_values) for seed_values in by_seed.values()]
    ci = _bootstrap_mean_ci(per_seed, metric_name=name)
    return {
        "status": "available" if values else "unavailable",
        "available_count": len(values),
        "unavailable_count": len(rows) - len(values),
        "sum": sum(numeric) if numeric else None,
        "mean": sum(numeric) / len(numeric) if numeric else None,
        "min": min(numeric) if numeric else None,
        "max": max(numeric) if numeric else None,
        "bootstrap_seed_count": len(per_seed),
        "bootstrap_ci95": ci,
    }


def _availability_summary(
    rows: Sequence[Mapping[str, Any]], name: str
) -> dict[str, Any]:
    available = sum(row.get(name) is not None for row in rows)
    return {
        "status": "available" if available else "unavailable",
        "available_row_count": available,
        "unavailable_row_count": len(rows) - available,
    }


def _render_markdown(
    aggregate: Mapping[str, Any], *, title: str, plot_name: str
) -> str:
    manifest = _mapping(aggregate.get("source_manifest"))
    lines = [
        f"# {title}",
        "",
        "本报告由 D6 离线消费 D1-D7 已写盘证据生成，不启动或控制 AirSim。缺失指标保持 `unavailable`，不补零；规模仅使用显式 `resource_count/target_count`，不从场景名推断。",
        "",
        f"![P1 系统证据概览]({plot_name})",
        "",
        "## 数据源状态",
        "",
        "| 数据源 | 状态 | Schema | Producer/Run | SHA256 | 证据路径/原因 |",
        "|---|---|---|---|---|---|",
    ]
    for name in SOURCE_NAMES:
        item = _mapping(manifest.get(name))
        detail = item.get("evidence_path") or item.get("reason") or "-"
        lines.append(
            f"| {name} | {item.get('status', 'unavailable')} | {item.get('schema_version') or 'NA'} | {item.get('producer') or 'NA'}/{item.get('run_id') or 'NA'} | {item.get('sha256') or 'NA'} | {detail} |"
        )

    truth = _mapping(aggregate.get("truth_policy"))
    lines.extend(
        [
            "",
            "## Truth 隔离",
            "",
            f"- 在线 truth 使用状态：`{truth.get('status')}`。",
            f"- 显式在线 truth 使用计数：`{truth.get('online_truth_use_count')}`。",
            "- D2/D5 的 precision、recall、IDSW 等 truth 指标仅来自离线评估汇总；本报告不导出 truth identity，也不回流在线控制。",
            "",
            "## D7 末端四层结果",
            "",
            "| 层级 | 可用行 | 合计 | 均值 |",
            "|---|---:|---:|---:|",
        ]
    )
    labels = {
        "contract_allowed_count": "合同允许",
        "control_allowed_count": "控制允许",
        "mode_switched_count": "模式已切换",
        "physical_intercept_count": "物理拦截",
    }
    for name, label in labels.items():
        item = _mapping(_mapping(aggregate.get("d7_terminal_layers")).get(name))
        lines.append(
            f"| {label} | {item.get('available_count', 0)} | {_display(item.get('sum'))} | {_display(item.get('mean'))} |"
        )
    d5_primary = _mapping(aggregate.get("d5_per_primary"))
    d5_labels = {
        "per_primary_evidence_count": "active-primary 证据机会",
        "per_primary_visible_count": "可见",
        "per_primary_associated_count": "D5 配准/锁定",
        "per_primary_common_lock_count": "共同锁定参与",
        "common_lock_count": "共同锁定目标/联盟",
        "global_track_id_rewrite_count": "全局 ID 改写",
    }
    lines.extend(
        [
            "",
            "四层指标只消费各自同名证据：合同允许不会被控制允许、模式切换或物理成功反推；物理成功也不会补写前置层。",
            "",
            "## D5 per-primary 证据",
            "",
            "| 指标 | 可用行 | 合计 | 均值 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, label in d5_labels.items():
        item = _mapping(d5_primary.get(name))
        lines.append(
            f"| {label} | {item.get('available_count', 0)} | {_display(item.get('sum'))} | {_display(item.get('mean'))} |"
        )

    closure = _mapping(aggregate.get("d7_cooperative_closure"))
    overall = _mapping(closure.get("overall"))
    lines.extend(
        [
            "",
            "## 协同闭环 profile 与 coalition",
            "",
            f"- 状态：`{closure.get('status', 'unavailable')}`；profile 数：`{closure.get('profile_count', 0)}`。",
            f"- 选定 profile：`{closure.get('selected_profile') or 'NA'}`；来源：`{closure.get('profile_selection_source') or 'NA'}`。",
            f"- 总 case 机会/coalition 机会/coalition 完成：`{_display(_mapping(overall.get('case_opportunity_count')).get('sum'))}` / `{_display(_mapping(overall.get('coalition_opportunity_count')).get('sum'))}` / `{_display(_mapping(overall.get('coalition_completion_count')).get('sum'))}`。",
            "",
            "| Profile | Case 机会 | Coalition 机会 | Coalition 完成 |",
            "|---|---:|---:|---:|",
        ]
    )
    for profile, item in sorted(_mapping(closure.get("by_profile")).items()):
        metrics = _mapping(_mapping(item).get("metrics"))
        lines.append(
            f"| {profile} | {_display(_mapping(metrics.get('case_opportunity_count')).get('sum'))} | {_display(_mapping(metrics.get('coalition_opportunity_count')).get('sum'))} | {_display(_mapping(metrics.get('coalition_completion_count')).get('sum'))} |"
        )
    lines.extend(
        [
            "",
            "## Bootstrap 与失败原因",
            "",
            f"- 数值指标使用逐 seed 均值做 percentile bootstrap 95% CI；resamples=`{_mapping(aggregate.get('bootstrap')).get('resamples')}`，rng seed=`{_mapping(aggregate.get('bootstrap')).get('rng_seed')}`。不足 2 个显式 seed 时 CI 保持 `unavailable`。",
            f"- 失败原因可用状态：`{_mapping(aggregate.get('failure_reason_distribution')).get('status')}`；分布：`{json.dumps(_mapping(aggregate.get('failure_reason_distribution')).get('counts', {}), ensure_ascii=False, sort_keys=True)}`。",
            "",
            "## 分模块结果",
            "",
            "| 模块证据 | 行数 | 关键可用指标数 |",
            "|---|---:|---:|",
        ]
    )
    by_source = _mapping(aggregate.get("by_source"))
    for name in SOURCE_NAMES:
        item = _mapping(by_source.get(name))
        metrics = _mapping(item.get("metrics"))
        available = sum(
            _mapping(value).get("status") == "available" for value in metrics.values()
        )
        lines.append(f"| {name} | {item.get('row_count', 0)} | {available} |")
    lines.extend(
        [
            "",
            "## 口径说明",
            "",
            "- D5 原生 MOT 的 IoU fallback 单独计数；只有 producer 明确输出 `native_mot_admitted=true` 才视为通过。",
            "- D5 per-primary 证据与 native MOT 准入分开汇总；局部锁定不会反推 D7 合同、控制、模式或物理结果。",
            "- D1 只审计已冻结 replay 的双时间戳、协方差、source lineage、spacing provenance 与在线 truth 隔离。",
            "- D2 按六类 difficulty profile 分组，`scenario_still_non_discriminative` 保持显式。",
            "- D3 分别统计 plan、coalition version、coalition epoch 与 membership churn，并保留 per-primary/arrival 配置。",
            "- D4 从逐 tick ACK、lease、epoch、owner、commit state 和 fail-closed 证据汇总，不参与接管决策。",
            "- D7 的 per-primary 授权只用于评估，不改变 D3/D4/D5/D7 在线合同。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_plot(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk_font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if cjk_font_path.exists():
        font_manager.fontManager.addfont(str(cjk_font_path))
        cjk_family = font_manager.FontProperties(fname=str(cjk_font_path)).get_name()
    else:
        cjk_family = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [cjk_family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    source_labels = ["D1", "D2", "D3", "D4", "D5锁定", "D5 MOT", "D7"]
    source_rates: list[float] = []
    for source in SOURCE_NAMES:
        source_rows = [row for row in rows if row.get("source") == source]
        available = sum(
            row.get(f"{name}_availability") == "available"
            for row in source_rows
            for name in METRIC_NAMES
        )
        total = len(source_rows) * len(METRIC_NAMES)
        source_rates.append(available / total if total else float("nan"))

    d7_rows = [row for row in rows if row.get("source") == "d7_per_primary"]
    d7_pair_rows = [
        row
        for row in d7_rows
        if row.get("family") == "cooperative_active_primary_layers"
    ]
    d7_profile_rows = [
        row
        for row in d7_rows
        if row.get("family") == "cooperative_profile_summary"
    ]
    d7_layer_rows = d7_pair_rows or d7_profile_rows or d7_rows
    layer_names = (
        "contract_allowed_count",
        "control_allowed_count",
        "mode_switched_count",
        "physical_intercept_count",
    )
    layer_values = [_sum_available(d7_layer_rows, name) for name in layer_names]
    failure_summary = _failure_reason_summary(rows)
    failure_counts = Counter(_mapping(failure_summary.get("counts")))
    top_failures = failure_counts.most_common(8)

    fig, axes = plt.subplots(1, 3, figsize=(17.5, 4.8))
    axes[0].bar(source_labels, source_rates, color="#356859")
    axes[0].set_ylim(0.0, 1.0)
    axes[0].set_ylabel("可用指标比例")
    axes[0].set_title("分模块证据可用性")
    axes[0].tick_params(axis="x", rotation=25)
    axes[0].grid(axis="y", alpha=0.25)
    bars = axes[1].bar(
        ["合同允许", "控制允许", "模式切换", "物理拦截"],
        [value if value is not None else float("nan") for value in layer_values],
        color="#d97706",
    )
    for bar, value in zip(bars, layer_values):
        if value is None:
            axes[1].text(bar.get_x() + bar.get_width() / 2, 0.02, "NA", ha="center")
    axes[1].set_title("D7 末端四层证据")
    axes[1].set_ylabel("写盘计数")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].grid(axis="y", alpha=0.25)
    if top_failures:
        labels, values = zip(*reversed(top_failures))
        axes[2].barh(labels, values, color="#9f4f36")
        axes[2].set_xlabel("次数")
    else:
        axes[2].text(0.5, 0.5, "失败原因证据不可用或无失败", ha="center", va="center")
        axes[2].set_xticks([])
        axes[2].set_yticks([])
    axes[2].set_title("失败原因分布")
    axes[2].grid(axis="x", alpha=0.25)
    fig.subplots_adjust(left=0.055, right=0.985, bottom=0.22, top=0.88, wspace=0.36)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _record_list(
    payload: Mapping[str, Any], names: Sequence[str]
) -> list[dict[str, Any]]:
    for name in names:
        value = payload.get(name)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return _mapping_rows(value)
        if isinstance(value, Mapping):
            return [dict(item) for item in value.values() if isinstance(item, Mapping)]
    return []


def _cooperative_pair_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _mapping_rows(payload.get("pair_rows"))
    if not rows:
        return []
    required = {"case_id", "profile", "resource_id", "target_id", "member_role"}
    if not all(required.issubset(item) for item in rows):
        return []
    return rows


def _cooperative_corrected_aggregate(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if str(payload.get("schema_version") or "") != "d6-cooperative-closure-v2":
        return {}
    if not isinstance(payload.get("funnels"), Mapping):
        return {}
    if not isinstance(payload.get("acceptance"), Mapping):
        return {}
    return dict(payload)


def _cooperative_profile_summaries(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    direct = _mapping_rows(payload.get("aggregates"))
    if direct and all("profile" in item for item in direct):
        return direct
    corrected = _cooperative_corrected_aggregate(payload)
    primary_source = _mapping(corrected.get("primary_source"))
    summaries = _mapping_rows(primary_source.get("aggregates"))
    if summaries and all("profile" in item for item in summaries):
        return summaries
    return []


def _cooperative_selected_profile(
    payload: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    declared = payload.get("best_candidate_profile")
    if declared is not None:
        return str(declared), "source_summary.best_candidate_profile"
    corrected = _cooperative_corrected_aggregate(payload)
    check = _mapping(
        _mapping(_mapping(corrected.get("acceptance")).get("checks")).get(
            "coalition_at_least_8_of_10"
        )
    )
    selected = check.get("selected_profile")
    if selected is not None:
        return str(selected), str(
            check.get("profile_selection_source") or "corrected_acceptance"
        )
    primary_source = _mapping(corrected.get("primary_source"))
    selected = primary_source.get("best_candidate_profile")
    if selected is not None:
        return str(selected), "primary_source.best_candidate_profile"
    return None, None


def _cooperative_explicit_scale(
    payload: Mapping[str, Any],
) -> tuple[int | None, int | None]:
    cases = _mapping_rows(payload.get("cases"))
    resource_counts = {
        value
        for item in cases
        if (value := _optional_int(item.get("resource_count"))) is not None
    }
    target_counts = {
        value
        for item in cases
        if (value := _optional_int(item.get("target_count"))) is not None
    }
    return (
        next(iter(resource_counts)) if len(resource_counts) == 1 else None,
        next(iter(target_counts)) if len(target_counts) == 1 else None,
    )


def _cooperative_scenario_id(payload: Mapping[str, Any]) -> Any:
    primary_source = _mapping(payload.get("primary_source"))
    return _coalesce(
        _first(payload, "calibration_suite", "scenario_version"),
        _first(primary_source, "calibration_suite", "scenario_version"),
    )


def _active_boolean_count(
    item: Mapping[str, Any], name: str, *, active: bool
) -> int | None:
    if not active or name not in item or item.get(name) is None:
        return None
    return int(bool(item.get(name)))


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _first_mapping_value(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _metric_value(value: Any, *, prefer: str) -> Any:
    if not isinstance(value, Mapping):
        return value
    if value.get("available") is False or value.get("status") == "unavailable":
        return None
    names = (
        (prefer, "value", "mean", "sum", "total", "max")
        if prefer == "mean"
        else (prefer, "value", "sum", "total", "mean", "max")
    )
    return _first(value, *names)


def _availability_count(
    availability: Mapping[str, Any], name: str
) -> int | None:
    item = _mapping(availability.get(name))
    if item.get("status") in {"unavailable", "not_applicable"}:
        return None
    return _optional_int(item.get("count"))


def _coverage_rate(count: int | None, opportunity_count: int | None) -> float | None:
    if count is None or opportunity_count is None or opportunity_count <= 0:
        return None
    return float(count) / float(opportunity_count)


def _source_provenance(payload: Mapping[str, Any]) -> dict[str, Any]:
    for candidate in (
        payload.get("provenance"),
        payload.get("capture_provenance"),
        _mapping(payload.get("manifest")).get("provenance"),
    ):
        if isinstance(candidate, Mapping):
            return _json_ready(dict(candidate))
    selected = {
        name: payload.get(name)
        for name in (
            "producer",
            "run_id",
            "episode_id",
            "batch_id",
            "scenario_id",
            "scenario_version",
            "matrix_version",
            "calibration_suite_version",
            "input_digest",
            "frozen_input_digest",
        )
        if payload.get(name) is not None
    }
    return _json_ready(selected)


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _failure_reasons(item: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for name in ("failure_reasons", "rejection_reasons", "admission_reasons"):
        for reason in _sequence(item.get(name)):
            if str(reason).strip():
                values.append(str(reason).strip())
    for name in (
        "first_failure_reason",
        "failure_reason",
        "stale_reject_reason",
        "terminal_contract_reject_reason",
        "terminal_control_reject_reason",
        "terminal_delivery_reason",
        "ttc_reject_reason",
    ):
        reason = item.get(name)
        if reason is not None and str(reason).strip():
            values.append(str(reason).strip())
    return tuple(dict.fromkeys(values))


def _d2_assessment_failure_reasons(
    assessment: Mapping[str, Any],
) -> tuple[str, ...]:
    reasons = list(_failure_reasons(assessment))
    checks = _mapping(assessment.get("checks"))
    reasons.extend(
        str(name)
        for name, value in checks.items()
        if isinstance(value, Mapping) and value.get("passed") is False
    )
    return tuple(dict.fromkeys(reasons))


def _d4_failure_reasons(
    case: Mapping[str, Any], ticks: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    reasons = list(_failure_reasons(case))
    reasons.extend(
        str(reason)
        for tick in ticks
        for reason in _sequence(tick.get("rejected_ack_reasons"))
        if str(reason).strip()
    )
    return tuple(dict.fromkeys(reasons))


def _layer_execution_latency(
    ticks: Sequence[Mapping[str, Any]], layer: str
) -> float | None:
    layer_ticks = [tick for tick in ticks if tick.get("selected_layer") == layer]
    if not layer_ticks:
        return None
    started = _first(layer_ticks[0], "timestamp_s", "timestamp")
    completed_tick = next(
        (tick for tick in layer_ticks if tick.get("execution_allowed") is True),
        None,
    )
    if started is None or completed_tick is None:
        return None
    completed = _first(completed_tick, "timestamp_s", "timestamp")
    if completed is None:
        return None
    return max(0.0, float(completed) - float(started))


def _explicit_count(
    item: Mapping[str, Any],
    *,
    count_names: Sequence[str],
    boolean_names: Sequence[str],
) -> Any:
    value = _first(item, *count_names)
    if value is not None:
        return value
    boolean = _first(item, *boolean_names)
    return int(bool(boolean)) if boolean is not None else None


def _max_optional_int(values: Sequence[Any] | Any) -> int | None:
    converted = [
        converted_value
        for value in values
        if (converted_value := _optional_int(value)) is not None
    ]
    return max(converted) if converted else None


def _failure_reason_summary(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    available_rows = [
        row
        for row in rows
        if row.get("failure_reasons_availability") == "available"
    ]
    counts = Counter(
        str(reason)
        for row in available_rows
        for reason in _sequence(row.get("failure_reasons"))
    )
    return {
        "status": "available" if available_rows else "unavailable",
        "available_row_count": len(available_rows),
        "unavailable_row_count": len(rows) - len(available_rows),
        "total_failure_reason_count": sum(counts.values()) if available_rows else None,
        "counts": dict(sorted(counts.items())),
    }


def _bootstrap_mean_ci(
    values: Sequence[float], *, metric_name: str
) -> dict[str, Any]:
    if len(values) < 2:
        return {
            "status": "unavailable",
            "reason": "at least two explicit seed values are required",
            "lower": None,
            "upper": None,
            "seed_count": len(values),
            "resamples": BOOTSTRAP_RESAMPLES,
            "rng_seed": BOOTSTRAP_RNG_SEED,
        }
    stable_offset = int.from_bytes(
        hashlib.sha256(metric_name.encode("utf-8")).digest()[:4], "big"
    )
    rng = random.Random(BOOTSTRAP_RNG_SEED + stable_offset)
    count = len(values)
    means = sorted(
        sum(values[rng.randrange(count)] for _ in range(count)) / count
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return {
        "status": "available",
        "reason": None,
        "lower": _percentile(means, 0.025),
        "upper": _percentile(means, 0.975),
        "seed_count": count,
        "resamples": BOOTSTRAP_RESAMPLES,
        "rng_seed": BOOTSTRAP_RNG_SEED,
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    return values[lower_index] * (1.0 - weight) + values[upper_index] * weight


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prefer_explicit(explicit: Any, derived: int) -> Any:
    return explicit if explicit is not None else derived


def _change_count(values: Sequence[Any]) -> int:
    filtered = [value for value in values if value is not None]
    return sum(current != previous for previous, current in zip(filtered, filtered[1:]))


def _adjacent_change_count(values: Sequence[Any]) -> int:
    return sum(current != previous for previous, current in zip(values, values[1:]))


def _ack_event_count(ticks: Sequence[Mapping[str, Any]]) -> int:
    message_count = sum(
        1
        for tick in ticks
        for event in _mapping_rows(tick.get("message_events"))
        if event.get("status") == "accepted"
        and str(_first(event, "message_type", "kind") or "").lower() in {"ack", "coalition_member_ack"}
    )
    if message_count:
        return message_count
    count = 0
    previous_epoch: Any = None
    previous_members: set[str] = set()
    for tick in ticks:
        epoch = tick.get("epoch")
        if epoch != previous_epoch:
            previous_epoch = epoch
            previous_members = set()
        current_members = {str(value) for value in _sequence(tick.get("acked_member_ids"))}
        count += len(current_members - previous_members)
        previous_members = current_members
    return count


def _sum_available(rows: Sequence[Mapping[str, Any]], name: str) -> float | None:
    values = [
        float(row[name])
        for row in rows
        if isinstance(row.get(name), (bool, int, float))
    ]
    return sum(values) if values else None


def _csv_ready(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (Mapping, list, tuple))
            else value
        )
        for key, value in row.items()
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    if is_dataclass(value):
        return _json_ready(asdict(value))
    return value


def _display(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
