from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.truth_isolated_offline import (
    REFERENCE_SCALABLE_3D_SCALES,
    TruthIsolatedEpisodeContext,
    TruthIsolatedEvaluationError,
    TruthIsolatedOfflineReportGenerator,
    adapt_d1_offline_consistency,
    adapt_d2_scalable_3d_identity,
    aggregate_truth_isolated_episode_records,
    build_truth_isolated_episode_record,
)


def _sha(character: str) -> str:
    return f"sha256:{character * 64}"


def _canonical_sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_sha(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _resign_d1(payload: dict[str, object]) -> None:
    payload.pop("content_digest", None)
    payload["content_digest"] = _canonical_sha(payload)


def _available_metric(value: float, sample_count: int = 2) -> dict[str, object]:
    return {
        "available": True,
        "value": value,
        "sample_count": sample_count,
        "reason": None,
    }


def _unavailable_metric(reason: str) -> dict[str, object]:
    return {
        "available": False,
        "value": None,
        "sample_count": 0,
        "reason": reason,
    }


def _d1_payload(
    *,
    seed: int = 7,
    scenario_id: str = "dense-crossing",
    scenario_version: str = "dense-crossing-v1",
    run_id: str = "episode-007",
    available: bool = True,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    if available:
        for index, (position_error, velocity_error, nees, nis, within) in enumerate(
            (
                (1.0, 0.5, 6.0, 2.0, True),
                (3.0, 1.5, 8.0, 4.0, False),
            )
        ):
            records.append(
                {
                    "schema_version": "d1.consistency.offline_result_record.v1",
                    "evidence_id": f"EV-{index}",
                    "observation_id": f"OBS-{index}",
                    "sensor_id": "RADAR-01",
                    "sensor_type": "radar",
                    "source_sensor_type": "radar",
                    "measurement_timestamp": float(index),
                    "arrival_timestamp": float(index) + 0.2,
                    "global_track_id": "GT-0001",
                    "truth_id": "T-0001",
                    "range_m": 750.0,
                    "range_bin": "mid",
                    "range_bin_schema_version": "d1.consistency.range_bins.v1",
                    "accepted": True,
                    "gate_decision": "accepted",
                    "innovation_dimension": 2,
                    "nis": nis,
                    "normalized_nis": nis / 2.0,
                    "nis_within_gate": within,
                    "position_error_m": position_error,
                    "velocity_error_mps": velocity_error,
                    "nees": nees,
                    "normalized_nees": nees / 6.0,
                    "availability": {
                        "truth_alignment": {"available": True, "reason": None},
                        "nees": {"available": True, "reason": None},
                        "nis_coverage": {"available": True, "reason": None},
                    },
                }
            )
        metrics = {
            "position_rmse_m": _available_metric(5.0**0.5),
            "velocity_rmse_mps": _available_metric(1.25**0.5),
            "mean_nees": _available_metric(7.0),
            "mean_normalized_nees": _available_metric(7.0 / 6.0),
            "mean_nis": _available_metric(3.0),
            "mean_normalized_nis": _available_metric(1.5),
            "nis_gate_coverage": _available_metric(0.5),
        }
        status = "available"
        failure_reasons: list[str] = []
    else:
        reason = "truth_alignment_unavailable"
        metrics = {
            name: _unavailable_metric(reason)
            for name in (
                "position_rmse_m",
                "velocity_rmse_mps",
                "mean_nees",
                "mean_normalized_nees",
                "mean_nis",
                "mean_normalized_nis",
                "nis_gate_coverage",
            )
        }
        status = "unavailable"
        failure_reasons = [reason]
    payload: dict[str, object] = {
        "schema_version": "d1.consistency.offline_result.v1",
        "record_schema_version": "d1.consistency.offline_result_record.v1",
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "run_id": run_id,
        "seed": seed,
        "status": status,
        "input_digests": {
            "online_evidence": _sha("a"),
            "truth_sidecar": _sha("b"),
            "canonical_mapping": _sha("c"),
        },
        "record_count": len(records),
        "records": records,
        "metrics": metrics,
        "failure_reasons": failure_reasons,
        "truth_usage": "offline_evaluation_only",
    }
    payload["content_digest"] = _canonical_sha(payload)
    return payload


def _d2_payload(
    *,
    episode_id: str = "episode-007",
    available: bool = True,
    truth_isolation_verified: bool = True,
    id_switch_count: int = 1,
) -> dict[str, object]:
    reason = None if available else "identity_lineage_unavailable"
    metric_values: dict[str, int | float | None] = {
        "id_switch_count": id_switch_count if available else None,
        "track_continuity": 0.8 if available else None,
        "identity_continuity": 0.8 if available else None,
        "coverage_continuity": 0.9 if available else None,
        "duplicate_truth_to_track_count": 2 if available else None,
    }
    metrics: dict[str, object] = {
        "schema_version": "d2.scalable3d_identity_metrics.v1",
        "evaluated_frame_count": 10,
        "truth_metrics_available": available,
        "truth_metrics_reason": reason,
        "continuity_available": available,
        "continuity_reason": reason,
        "confusion_matrix": (
            {"T-0001": {"GT-0001": 8, "GT-0002": 2}}
            if available
            else None
        ),
        "truth_frame_count": {"T-0001": 10} if available else {},
        "truth_assigned_frame_count": {"T-0001": 9} if available else {},
        "truth_identity_stable_frame_count": {"T-0001": 8} if available else {},
    }
    for name, value in metric_values.items():
        metrics[name] = value
        metrics[f"{name}_available"] = available
        metrics[f"{name}_reason"] = reason
    metrics["duplicate_assignment_count"] = metric_values[
        "duplicate_truth_to_track_count"
    ]
    metrics["duplicate_assignment_count_available"] = available
    metrics["duplicate_assignment_count_reason"] = reason
    return {
        "schema_version": "d2.scalable3d_identity_evaluation.v1",
        "policy_version": "d2.scalable3d_identity_policy.v1",
        "hash_algorithm": "sha256",
        "episode_id": episode_id,
        "source_hashes": {
            "online_d1_records": _sha("d"),
            "online_d2_records": _sha("e"),
            "observation_truth_labels": _sha("f"),
            "identity_evidence_bundle": _sha("0"),
        },
        "configuration": {
            "metric_contract": "MetricsRecorder-compatible-v1"
        },
        "frames": [],
        "metrics": metrics,
        "audit": {
            "source_verification": (
                "raw_source_hashes_and_record_sequences_verified"
                if truth_isolation_verified
                else "canonical_dto_hashes_verified"
            ),
            "online_truth_isolation_verified": truth_isolation_verified,
            "identity_heuristics_used": False,
            "available_mapping_count": 8,
            "ambiguous_mapping_count": 1,
            "unavailable_mapping_count": 1,
        },
    }


class _D1PublicDTO:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(self.payload))

    def aggregation_records(self) -> tuple[dict[str, object], ...]:
        input_digests = self.payload["input_digests"]
        assert isinstance(input_digests, dict)
        context = {
            "schema_version": "d1.consistency.offline_aggregation_record.v1",
            "result_record_schema_version": (
                "d1.consistency.offline_result_record.v1"
            ),
            "scenario_id": self.payload["scenario_id"],
            "scenario_version": self.payload["scenario_version"],
            "run_id": self.payload["run_id"],
            "seed": self.payload["seed"],
            "offline_result_digest": self.payload["content_digest"],
            "online_evidence_digest": input_digests["online_evidence"],
            "truth_sidecar_digest": input_digests["truth_sidecar"],
            "canonical_mapping_digest": input_digests["canonical_mapping"],
        }
        records = self.payload["records"]
        assert isinstance(records, list)
        return tuple({**record, **context} for record in records)


class _D2PublicDTO:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(self.payload))


def _context(
    *,
    episode_id: str = "episode-007",
    run_id: str = "episode-007",
    seed: int = 7,
    scale: int = 20,
) -> TruthIsolatedEpisodeContext:
    return TruthIsolatedEpisodeContext(
        episode_id=episode_id,
        scenario_id="dense-crossing",
        scenario_version="dense-crossing-v1",
        run_id=run_id,
        seed=seed,
        target_count=scale,
        resource_count=scale,
        recon_count=max(1, scale // 20),
        camera_count=scale + max(1, scale // 20),
    )


def test_public_dto_adapters_preserve_d1_d2_metrics() -> None:
    d1 = adapt_d1_offline_consistency(_D1PublicDTO(_d1_payload()))
    d2 = adapt_d2_scalable_3d_identity(_D2PublicDTO(_d2_payload()))

    assert d1.verification_mode == "public_dto_validated"
    assert d1.metrics["position_rmse_m"].value == pytest.approx(5.0**0.5)
    assert len(d1.sensor_range_records) == 1
    group = d1.sensor_range_records[0]
    assert group.metrics["position_rmse_m"].value == pytest.approx(5.0**0.5)
    assert group.metrics["position_rmse_m"].sample_count == 2
    assert group.metrics["nis_gate_coverage"].value == pytest.approx(0.5)
    assert group.input_hashes["canonical_mapping"] == _sha("c")

    assert d2.truth_isolation_verified is True
    assert d2.metrics["id_switch_count"].value == 1
    assert d2.metrics["id_switch_count"].available is True
    assert d2.confusion_matrix == {"T-0001": {"GT-0001": 8, "GT-0002": 2}}
    assert d2.truth_assigned_frame_count == {"T-0001": 9}
    assert d2.configuration["metric_contract"] == "MetricsRecorder-compatible-v1"


def test_d2_unverified_truth_isolation_fails_metrics_closed() -> None:
    d2 = adapt_d2_scalable_3d_identity(
        _d2_payload(truth_isolation_verified=False)
    )

    assert d2.truth_isolation_verified is False
    assert d2.metrics["id_switch_count"].value is None
    assert d2.metrics["id_switch_count"].available is False
    assert (
        d2.metrics["id_switch_count"].unavailable_reason
        == "d2_online_truth_isolation_not_verified"
    )
    assert d2.confusion_matrix is None
    assert d2.truth_frame_count == {}
    assert d2.truth_assigned_frame_count == {}


def test_d2_unavailable_metric_cannot_smuggle_zero() -> None:
    payload = _d2_payload(available=False)
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["id_switch_count"] = 0

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="unavailable D2 identity metric must be null",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_hash_verified_artifacts_and_tamper_rejection(tmp_path: Path) -> None:
    payload = _d2_payload()
    path = tmp_path / "d2_identity.json"
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected = _file_sha(path)
    source_hashes = payload["source_hashes"]
    assert isinstance(source_hashes, dict)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="path requires expected_source_hashes",
    ):
        adapt_d2_scalable_3d_identity(path, expected_sha256=expected)

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
    )
    assert record.verification_mode == "sha256_verified_artifact"
    assert record.external_file_sha256 == expected

    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(TruthIsolatedEvaluationError, match="sha256 mismatch"):
        adapt_d2_scalable_3d_identity(path, expected_sha256=expected)


def test_d2_zero_without_frame_evidence_is_unavailable_not_zero() -> None:
    payload = _d2_payload(id_switch_count=0)
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["evaluated_frame_count"] = 0
    metrics["truth_frame_count"] = {}
    metrics["truth_assigned_frame_count"] = {}
    metrics["truth_identity_stable_frame_count"] = {}
    metrics["confusion_matrix"] = {}

    record = adapt_d2_scalable_3d_identity(payload)

    assert record.metrics["id_switch_count"].value is None
    assert record.metrics["id_switch_count"].available is False
    assert (
        record.metrics["id_switch_count"].unavailable_reason
        == "d2_evaluated_frames_unavailable"
    )
    assert record.truth_frame_count == {}


def test_d1_record_availability_cannot_be_overridden_by_a_value() -> None:
    payload = _d1_payload()
    records = payload["records"]
    assert isinstance(records, list)
    availability = records[0]["availability"]
    assert isinstance(availability, dict)
    availability["truth_alignment"] = {
        "available": False,
        "reason": "truth_alignment_unavailable",
    }
    _resign_d1(payload)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="unavailable D1 record field must be null",
    ):
        adapt_d1_offline_consistency(payload)


def test_d1_internal_digest_tamper_rejected() -> None:
    payload = _d1_payload()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    position = metrics["position_rmse_m"]
    assert isinstance(position, dict)
    position["value"] = 999.0

    with pytest.raises(TruthIsolatedEvaluationError, match="content digest mismatch"):
        adapt_d1_offline_consistency(payload)


def test_missing_artifacts_keep_explicit_id_switch_unavailable() -> None:
    record = build_truth_isolated_episode_record(
        _context(),
        d1_result=None,
        d2_evaluation=None,
    )

    payload = record.to_dict()
    assert payload["d2_identity"]["id_switch_count"] is None
    assert (
        payload["d2_identity"]["id_switch_count_availability"]
        == "unavailable"
    )
    assert (
        payload["d2_identity"]["id_switch_count_unavailable_reason"]
        == "d2_identity_evaluation_artifact_missing"
    )


def test_context_alignment_rejects_cross_episode_mix() -> None:
    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="D2 identity episode_id",
    ):
        build_truth_isolated_episode_record(
            _context(),
            d1_result=_d1_payload(),
            d2_evaluation=_d2_payload(episode_id="different-episode"),
        )


def test_reference_scales_are_dynamic_and_all_supported() -> None:
    records = []
    for seed, scale in enumerate(REFERENCE_SCALABLE_3D_SCALES, start=1):
        episode_id = f"episode-{scale}"
        context = _context(
            episode_id=episode_id,
            run_id=episode_id,
            seed=seed,
            scale=scale,
        )
        records.append(
            build_truth_isolated_episode_record(
                context,
                d1_result=_d1_payload(
                    seed=seed,
                    run_id=episode_id,
                ),
                d2_evaluation=_d2_payload(episode_id=episode_id),
            )
        )

    summary = aggregate_truth_isolated_episode_records(
        records,
        bootstrap_resamples=50,
    )

    assert summary.scale_values == REFERENCE_SCALABLE_3D_SCALES
    assert all(summary.reference_scale_coverage.values())
    assert len(summary.groups) == len(REFERENCE_SCALABLE_3D_SCALES)
    assert all(
        "d2.id_switch_count" in group["metrics"] for group in summary.groups
    )


def test_report_bundle_writes_csv_json_and_chinese_markdown(tmp_path: Path) -> None:
    available = build_truth_isolated_episode_record(
        _context(),
        d1_result=_D1PublicDTO(_d1_payload()),
        d2_evaluation=_D2PublicDTO(_d2_payload(id_switch_count=0)),
    )
    missing_context = _context(
        episode_id="episode-008",
        run_id="episode-008",
        seed=8,
    )
    missing = build_truth_isolated_episode_record(
        missing_context,
        d1_result=None,
        d2_evaluation=None,
    )

    paths = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        tmp_path,
        records=(available, missing),
        bootstrap_resamples=50,
    )

    assert set(paths) == {
        "per_seed_csv",
        "d1_sensor_range_per_seed_csv",
        "aggregate_json",
        "markdown",
    }
    with paths["per_seed_csv"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["d2_id_switch_count"] == "0"
    assert rows[1]["d2_id_switch_count"] == ""
    assert rows[1]["d2_id_switch_count_availability"] == "unavailable"

    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    idsw = aggregate["groups"][0]["metrics"]["d2.id_switch_count"]
    assert idsw["availability"] == "available"
    assert idsw["mean"] == 0.0
    assert idsw["unavailability_reason_distribution"] == {
        "d2_identity_evaluation_artifact_missing": 1
    }
    assert aggregate["groups"][0]["d2_confusion_matrices_by_episode"] == [
        {
            "episode_id": "episode-007",
            "confusion_matrix": {"T-0001": {"GT-0001": 8, "GT-0002": 2}},
        }
    ]
    provenance = aggregate["groups"][0]["source_provenance_by_episode"]
    assert provenance[0]["d2_source_hashes"]["online_d1_records"] == _sha("d")
    assert provenance[1]["d2_truth_metric_evidence_verified"] is False
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "D6 未重新构造航迹与真值映射" in markdown
    assert "缺证据时不会写成零" in markdown
    assert "单 seed 分组只给描述统计" in markdown
    assert "## 来源摘要" in markdown
    assert "online_d1_records=`sha256:" in markdown
