from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from d6_evaluation_metrics.observation_governance_calibration import (
    D1_ONLINE_METRICS,
    D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
    D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
    D2_ONLINE_METRICS,
    OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_CALIBRATION_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
    ObservationGovernanceCalibrationError,
    ObservationGovernanceCalibrationReportGenerator,
    evaluate_observation_governance_calibration,
    load_observation_governance_calibration_inputs,
    main_producer_required_json_paths,
)


PayloadMutator = Callable[[dict[str, Any]], None]


def _sha_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _file_sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _available(value: int) -> dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None}


def _online_metrics(scale: int) -> tuple[dict[str, Any], dict[str, Any]]:
    d1_values = {
        "scan_count": scale * 4,
        "current_oosm_buffer_count": scale,
        "peak_oosm_buffer_count": scale + 3,
        "oosm_buffered_count": scale * 2,
        "oosm_reordered_count": scale,
        "oosm_rejected_count": 0,
        "oosm_too_old_count": 0,
        "oosm_overflow_count": 0,
        "oosm_eviction_count": 0,
        "estimated_current_memory_bytes": scale * 128,
        "estimated_peak_memory_bytes": scale * 192,
    }
    d2_values = {
        "current_claim_count": scale,
        "peak_claim_count": scale + 5,
        "claim_eviction_count": 0,
        "claim_too_old_count": 0,
        "claim_overflow_count": 0,
        "replay_quarantine_count": 0,
        "timestamp_conflict_count": 0,
        "duplicate_coalescence_count": 0,
        "estimated_current_memory_bytes": scale * 96,
        "estimated_peak_memory_bytes": scale * 160,
    }
    assert set(d1_values) == set(D1_ONLINE_METRICS)
    assert set(d2_values) == set(D2_ONLINE_METRICS)
    return (
        {name: _available(value) for name, value in d1_values.items()},
        {name: _available(value) for name, value in d2_values.items()},
    )


def _build_batch(
    root: Path,
    *,
    scales: tuple[int, ...] = (20,),
    seeds: tuple[int, ...] | None = None,
    sidecar_available: bool = True,
    manifest_mutator: PayloadMutator | None = None,
    online_mutator: PayloadMutator | None = None,
    sidecar_mutator: PayloadMutator | None = None,
    d1_metric_mutator: PayloadMutator | None = None,
) -> tuple[Any, dict[str, Path]]:
    if seeds is None:
        seeds = tuple(10_000 + scale for scale in scales)
    assert len(seeds) == len(scales)
    descriptors: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for index, (scale, seed) in enumerate(zip(scales, seeds, strict=True)):
        episode_id = f"long-governance-s{scale}-seed{seed}"
        episode = {
            "episode_id": episode_id,
            "scale": scale,
            "target_count": scale,
            "resource_count": scale + index,
            "seed": seed,
            "duration_s": 120.0 + index,
        }
        config_hash = _sha_text(f"config-{scale}-{seed}")
        manifest = {
            "schema_version": OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
            "episode": dict(episode),
            "provenance": {
                "producer": "main-scalable3d-runtime",
                "git_commit": "a" * 40,
                "repository_dirty": False,
                "evidence_tier": "formal",
                "config_sha256": config_hash,
                "world_schema": "scalable3d-world-v1",
                "bus_schema": "scalable3d-episode-bus-v1",
                "scenario_schema": "scalable3d-scenario-v1",
                "online_observation_schema": "scalable3d-observation-v1",
                "d1_scan_oosm_audit_schema": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
                "d2_claim_ledger_audit_schema": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
            },
            "online_truth_use_count": 0,
        }
        if manifest_mutator is not None:
            manifest_mutator(manifest)
        manifest_path = root / episode_id / "observation_governance_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_hash = _file_sha(manifest_path)

        d1_metrics, d2_metrics = _online_metrics(scale)
        if d1_metric_mutator is not None:
            d1_metric_mutator(d1_metrics)
        online = {
            "schema_version": OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
            "episode": dict(episode),
            "provenance": {
                "producer": "main-scalable3d-runtime",
                "git_commit": "a" * 40,
                "config_sha256": config_hash,
                "episode_manifest_sha256": manifest_hash,
                "source_bus_sha256": _sha_text(f"bus-{scale}-{seed}"),
                "source_bus_schema": "scalable3d-episode-bus-v1",
            },
            "online_truth_use_count": 0,
            "d1_scan_oosm_audit": {
                "schema_version": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
                "metrics": d1_metrics,
            },
            "d2_claim_ledger_audit": {
                "schema_version": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
                "metrics": d2_metrics,
            },
        }
        if online_mutator is not None:
            online_mutator(online)
        online_path = root / episode_id / "observation_governance_online_audit.json"
        _write_json(online_path, online)
        online_hash = _file_sha(online_path)

        if sidecar_available:
            sidecar = {
                "schema_version": OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION,
                "evaluator_only": True,
                "online_consumed": False,
                "episode": dict(episode),
                "provenance": {
                    "producer": "offline-truth-evaluator",
                    "evaluator_git_commit": "b" * 40,
                    "config_sha256": config_hash,
                    "truth_schema": "scalable3d-offline-truth-v1",
                    "truth_artifact_sha256": _sha_text(f"truth-{scale}-{seed}"),
                    "episode_manifest_sha256": manifest_hash,
                    "online_audit_sha256": online_hash,
                },
                "metrics": {
                    "near_neighbor_recall": {
                        "availability": "available",
                        "numerator": scale - 1,
                        "denominator": scale,
                        "reason": None,
                    },
                    "false_suppression_rate": {
                        "availability": "available",
                        "numerator": 0,
                        "denominator": scale,
                        "reason": None,
                    },
                    "erroneous_coalescence_rate": {
                        "availability": "available",
                        "numerator": 0,
                        "denominator": max(1, scale // 2),
                        "reason": None,
                    },
                    "confirmation_latency_s": {
                        "availability": "available",
                        "samples_s": [0.0, 0.25 + index * 0.01],
                        "reason": None,
                    },
                },
            }
            if sidecar_mutator is not None:
                sidecar_mutator(sidecar)
            sidecar_path = root / episode_id / "observation_governance_evaluator_sidecar.json"
            _write_json(sidecar_path, sidecar)
            sidecar_descriptor = {
                "availability": "available",
                "artifact": {
                    "path": str(sidecar_path.relative_to(root)),
                    "sha256": _file_sha(sidecar_path),
                },
                "reason": None,
            }
            paths[f"sidecar_{scale}"] = sidecar_path
        else:
            sidecar_descriptor = {
                "availability": "unavailable",
                "artifact": None,
                "reason": "evaluator_only_sidecar_not_produced",
            }

        descriptors.append(
            {
                "episode": dict(episode),
                "manifest_artifact": {
                    "path": str(manifest_path.relative_to(root)),
                    "sha256": manifest_hash,
                },
                "online_audit_artifact": {
                    "path": str(online_path.relative_to(root)),
                    "sha256": online_hash,
                },
                "evaluator_sidecar": sidecar_descriptor,
            }
        )
        paths[f"manifest_{scale}"] = manifest_path
        paths[f"online_{scale}"] = online_path

    spec = {
        "schema_version": OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
        "created_at_utc": "2026-07-22T00:00:00Z",
        "producer": "main-scalable3d-orchestrator",
        "admission_policy": "formal_only",
        "expected_scales": list(scales),
        "episodes": descriptors,
    }
    spec_path = root / "observation_governance_calibration_input.json"
    _write_json(spec_path, spec)
    paths["input"] = spec_path
    inputs = load_observation_governance_calibration_inputs(
        spec_path,
        expected_sha256=_file_sha(spec_path),
    )
    return inputs, paths


def test_available_batch_writes_csv_json_markdown_and_preserves_true_zero(
    tmp_path: Path,
) -> None:
    inputs, _ = _build_batch(tmp_path, scales=(20, 50), seeds=(120, 150))
    output = tmp_path / "report"
    paths = ObservationGovernanceCalibrationReportGenerator().write_report_bundle(
        output,
        inputs=inputs,
        bootstrap_resamples=100,
        bootstrap_rng_seed=7,
    )

    assert set(paths) == {"per_seed_csv", "aggregate_json", "markdown"}
    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == OBSERVATION_GOVERNANCE_CALIBRATION_SCHEMA_VERSION
    assert aggregate["episode_count"] == 2
    assert aggregate["truth_isolation"]["online_truth_use_count"] == 0
    scale20 = aggregate["scales"][0]
    false_suppression = scale20["evaluator_ratio_metrics"]["false_suppression_rate"]
    assert false_suppression["availability"] == "available"
    assert false_suppression["sample_count"] == 20
    assert false_suppression["rate"] == 0.0
    assert false_suppression["bootstrap_ci95"] == {
        "lower": 0.0,
        "upper": 0.0,
        "resamples": 100,
        "rng_seed": 102030,
    }
    with paths["per_seed_csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["d2_replay_quarantine_count"] == "0"
    assert rows[0]["d2_replay_quarantine_count_availability"] == "available"
    assert rows[0]["false_suppression_rate"] == "0.0"
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Main 写盘合同" in markdown
    assert "D6 只读取 episode 结束后的公共制品" in markdown


def test_unavailable_sidecar_remains_null_not_zero(tmp_path: Path) -> None:
    inputs, _ = _build_batch(tmp_path, sidecar_available=False)
    result = evaluate_observation_governance_calibration(
        inputs,
        bootstrap_resamples=50,
    )
    row = result.per_seed_records[0]
    assert row["near_neighbor_recall"] is None
    assert row["near_neighbor_recall_availability"] == "unavailable"
    assert row["confirmation_latency_s"] is None
    assert row["confirmation_latency_s_sample_count"] == 0
    ratio = result.aggregate["scales"][0]["evaluator_ratio_metrics"][
        "near_neighbor_recall"
    ]
    assert ratio["availability"] == "unavailable"
    assert ratio["rate"] is None
    assert ratio["bootstrap_ci95"] is None


def test_available_zero_and_unavailable_online_metric_are_distinct(
    tmp_path: Path,
) -> None:
    def make_eviction_unavailable(metrics: dict[str, Any]) -> None:
        metrics["oosm_eviction_count"] = {
            "availability": "unavailable",
            "value": None,
            "reason": "producer_counter_not_instrumented",
        }

    inputs, _ = _build_batch(tmp_path, d1_metric_mutator=make_eviction_unavailable)
    result = evaluate_observation_governance_calibration(inputs, bootstrap_resamples=25)
    row = result.per_seed_records[0]
    assert row["d1_oosm_eviction_count"] is None
    assert row["d1_oosm_eviction_count_availability"] == "unavailable"
    assert row["d1_oosm_overflow_count"] == 0
    assert row["d1_oosm_overflow_count_availability"] == "available"


def test_dynamic_20_50_100_200_scales_are_aggregated_without_baseline_hardcode(
    tmp_path: Path,
) -> None:
    inputs, _ = _build_batch(
        tmp_path,
        scales=(20, 50, 100, 200),
        seeds=(20_001, 50_001, 100_001, 200_001),
    )
    result = evaluate_observation_governance_calibration(
        inputs,
        bootstrap_resamples=20,
    )
    assert [item["scale"] for item in result.aggregate["scales"]] == [20, 50, 100, 200]
    assert [row["d2_current_claim_count"] for row in result.per_seed_records] == [20, 50, 100, 200]


def test_nonbaseline_dynamic_scales_are_supported(tmp_path: Path) -> None:
    inputs, _ = _build_batch(tmp_path, scales=(7, 37), seeds=(7001, 37001))
    result = evaluate_observation_governance_calibration(
        inputs,
        bootstrap_resamples=20,
    )
    assert [item["scale"] for item in result.aggregate["scales"]] == [7, 37]


def test_tampered_online_artifact_is_rejected(tmp_path: Path) -> None:
    inputs, paths = _build_batch(tmp_path)
    paths["online_20"].write_text("{}\n", encoding="utf-8")
    with pytest.raises(ObservationGovernanceCalibrationError, match="artifact_sha256_mismatch"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_dirty_formal_source_is_rejected(tmp_path: Path) -> None:
    def dirty(payload: dict[str, Any]) -> None:
        payload["provenance"]["repository_dirty"] = True

    inputs, _ = _build_batch(tmp_path, manifest_mutator=dirty)
    with pytest.raises(ObservationGovernanceCalibrationError, match="dirty_formal_source"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_online_truth_identity_key_is_rejected_even_with_fresh_hashes(
    tmp_path: Path,
) -> None:
    def leak(payload: dict[str, Any]) -> None:
        payload["d2_claim_ledger_audit"]["truth_target_id"] = "TGT-0001"

    inputs, _ = _build_batch(tmp_path, online_mutator=leak)
    with pytest.raises(ObservationGovernanceCalibrationError, match="online_truth_leakage"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_inconsistent_scale_across_artifacts_is_rejected(tmp_path: Path) -> None:
    def change_scale(payload: dict[str, Any]) -> None:
        payload["episode"]["scale"] = 21
        payload["episode"]["target_count"] = 21

    inputs, _ = _build_batch(tmp_path, online_mutator=change_scale)
    with pytest.raises(ObservationGovernanceCalibrationError, match="episode_identity_mismatch"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_duplicate_seed_is_rejected_across_scales(tmp_path: Path) -> None:
    inputs, _ = _build_batch(tmp_path, scales=(20, 50), seeds=(1234, 1234))
    with pytest.raises(ObservationGovernanceCalibrationError, match="duplicate_seed"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_missing_schema_provenance_is_rejected(tmp_path: Path) -> None:
    def remove_config(payload: dict[str, Any]) -> None:
        del payload["provenance"]["config_sha256"]

    inputs, _ = _build_batch(tmp_path, manifest_mutator=remove_config)
    with pytest.raises(ObservationGovernanceCalibrationError, match="missing_required_field"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_evaluator_sidecar_must_be_offline_and_hash_bound(tmp_path: Path) -> None:
    def consume_online(payload: dict[str, Any]) -> None:
        payload["online_consumed"] = True

    inputs, _ = _build_batch(tmp_path, sidecar_mutator=consume_online)
    with pytest.raises(ObservationGovernanceCalibrationError, match="sidecar_online_consumed"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_unavailable_metric_cannot_carry_false_zero(tmp_path: Path) -> None:
    def invalid(metrics: dict[str, Any]) -> None:
        metrics["oosm_eviction_count"] = {
            "availability": "unavailable",
            "value": 0,
            "reason": "not_instrumented",
        }

    inputs, _ = _build_batch(tmp_path, d1_metric_mutator=invalid)
    with pytest.raises(ObservationGovernanceCalibrationError, match="unavailable_metric_has_value"):
        evaluate_observation_governance_calibration(inputs, bootstrap_resamples=20)


def test_public_required_paths_include_all_governance_families() -> None:
    paths = main_producer_required_json_paths()
    assert any("current_claim_count" in value for value in paths)
    assert any("oosm_reordered_count" in value for value in paths)
    assert any("near_neighbor_recall" in value for value in paths)
    assert any("confirmation_latency_s" in value for value in paths)
