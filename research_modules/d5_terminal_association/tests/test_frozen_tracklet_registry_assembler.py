from __future__ import annotations

import json
from pathlib import Path

import pytest

import d5_terminal_association.frozen_tracklet_audit as audit_module
from d5_terminal_association.frozen_tracklet_audit import (
    FrozenTrackletAuditError,
    assemble_frozen_tracklet_registry,
)
from d5_terminal_association.tracklet_dataset import sha256_file, sha256_json


def test_assembler_low_auc_closes_authority_and_writes_complete_manifest(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "registry"

    evidence = _assemble(registry_fixture, output)

    assert evidence["schema_version"] == "d5.frozen-tracklet-audit-evidence.v1"
    assert set(evidence) == {
        "authority",
        "catalog",
        "evaluated_at_utc",
        "frozen_model",
        "heldout_input",
        "limitations",
        "nominal_metrics",
        "output_hashes",
        "robustness_profiles",
        "schema_version",
        "single_feature_shortcut",
        "status",
    }
    assert set(evidence["catalog"]) == {
        "candidate_edge_count",
        "episode_count",
        "node_count",
        "scenario_scale_cell_count",
        "seed_count",
        "seeds",
    }
    assert evidence["authority"] == {
        "g1": False,
        "assist": False,
        "authority": False,
        "default_model_changed": False,
        "active_visual_ppo_started": False,
    }
    assert "synthetic_heldout_single_feature_shortcut" not in evidence[
        "limitations"
    ]
    assert evidence["limitations"] == [
        "counterfactual_profiles_hold_candidate_graph_fixed",
        "d6_external_audit_required",
        "no_online_authority",
    ]
    checksums = _read_checksums(output / "SHA256SUMS")
    assert set(checksums) == {
        "FROZEN_GNN_AUDIT_REPORT_CN.md",
        "audit_evidence.json",
        "frozen_bundle_reference.json",
    }
    assert all(sha256_file(output / name) == digest for name, digest in checksums.items())
    assert (output / "frozen_bundle_reference.json").read_bytes() == (
        registry_fixture["reference"].read_bytes()
    )


def test_assembler_high_auc_adds_shortcut_blocker(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    _set_auc(registry_fixture, 0.995)

    evidence = _assemble(registry_fixture, tmp_path / "registry-high-auc")

    assert evidence["single_feature_shortcut"]["best_direction_auc"] == 0.995
    assert "synthetic_heldout_single_feature_shortcut" in evidence[
        "limitations"
    ]


def test_assembler_adds_shared_global_track_shortcut_only_when_nonzero(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    paired = _read_json(registry_fixture["paired"])
    shared = paired["feature_label_diagnostics"]["shared_global_track_count"]
    shared["near_deterministic"] = True
    shared["strata"]["1"]["edge_count"] = 2
    _write_content_json(registry_fixture["paired"], paired)
    _refresh_summary_paired_bindings(registry_fixture)

    evidence = _assemble(registry_fixture, tmp_path / "registry-shared")

    assert "shared_global_track_count_near_deterministic_shortcut" in evidence[
        "limitations"
    ]


def test_assembler_rejects_out_of_band_hash_tamper(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    original_sha = sha256_file(registry_fixture["heldout"])
    registry_fixture["heldout"].write_bytes(
        registry_fixture["heldout"].read_bytes() + b" "
    )

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(
            registry_fixture,
            tmp_path / "registry",
            expected_heldout_sha256=original_sha,
        )

    assert error.value.code == "input_sha256_mismatch.heldout"


def test_assembler_rejects_content_hash_tamper(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    heldout = _read_json(registry_fixture["heldout"])
    heldout["heldout_corpus"]["profile_version"] = "tampered-profile"
    _write_plain_json(registry_fixture["heldout"], heldout)

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, tmp_path / "registry")

    assert error.value.code == "input_content_sha256_mismatch.heldout"


def test_assembler_rejects_schema_tamper(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    summary = _read_json(registry_fixture["summary"])
    summary["schema_version"] = "d5.frozen-tracklet-audit-summary.v999"
    _write_plain_json(registry_fixture["summary"], summary)

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, tmp_path / "registry")

    assert error.value.code == "schema_mismatch.summary"


def test_assembler_rejects_lineage_tamper_even_with_current_file_hash(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    records = registry_fixture["lineage"].read_text(encoding="utf-8").splitlines()
    first = json.loads(records[0])
    first["episode_uid"] = "tampered"
    records[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    registry_fixture["lineage"].write_text(
        "\n".join(records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, tmp_path / "registry")

    assert error.value.code == "paired_lineage_sha256_mismatch"


def test_assembler_rejects_any_non_false_authority(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    summary = _read_json(registry_fixture["summary"])
    summary["authority"]["assist"] = True
    _write_plain_json(registry_fixture["summary"], summary)

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, tmp_path / "registry")

    assert error.value.code == "authority_not_closed.summary.authority.assist"


def test_assembler_rejects_incomplete_generated_manifest(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def incomplete(root: Path) -> None:
        (root / "SHA256SUMS").write_text(
            (
                f"{sha256_file(root / 'audit_evidence.json')}"
                "  audit_evidence.json\n"
            ),
            encoding="ascii",
        )

    monkeypatch.setattr(audit_module, "_write_registry_checksums", incomplete)
    output = tmp_path / "registry"

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, output)

    assert error.value.code == "registry_checksums_incomplete"
    assert not output.exists()


def test_assembler_rejects_nonempty_output_without_touching_sentinel(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
) -> None:
    output = tmp_path / "registry"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FrozenTrackletAuditError) as error:
        _assemble(registry_fixture, output)

    assert error.value.code == "registry_destination_exists"
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_assemble_registry_cli_uses_the_same_fail_closed_path(
    registry_fixture: dict[str, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "registry-cli"

    result = audit_module.main(
        [
            "assemble-registry",
            "--reference",
            str(registry_fixture["reference"]),
            "--reference-sha256",
            sha256_file(registry_fixture["reference"]),
            "--frozen-audit-summary",
            str(registry_fixture["summary"]),
            "--frozen-audit-summary-sha256",
            sha256_file(registry_fixture["summary"]),
            "--heldout-report",
            str(registry_fixture["heldout"]),
            "--heldout-report-sha256",
            sha256_file(registry_fixture["heldout"]),
            "--paired-shadow-report",
            str(registry_fixture["paired"]),
            "--paired-shadow-report-sha256",
            sha256_file(registry_fixture["paired"]),
            "--paired-lineage",
            str(registry_fixture["lineage"]),
            "--paired-lineage-sha256",
            sha256_file(registry_fixture["lineage"]),
            "--output-dir",
            str(output),
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    assert result == 0
    assert printed["status"] == "evidence_chain_closed_shadow_only"
    assert printed["authority"] is False
    assert (output / "audit_evidence.json").is_file()


@pytest.fixture
def registry_fixture(tmp_path: Path) -> dict[str, Path]:
    paths = {
        name: tmp_path / filename
        for name, filename in {
            "reference": "frozen_bundle_reference.json",
            "summary": "frozen_audit_summary.json",
            "heldout": "heldout_evaluation.json",
            "paired": "paired_shadow_report.json",
            "lineage": "paired_episode_lineage.jsonl",
        }.items()
    }
    bundle = {
        "manifest_sha256": "1" * 64,
        "weights_sha256": "2" * 64,
        "checksums_sha256": "3" * 64,
    }
    _write_plain_json(
        paths["reference"],
        {
            "schema_version": "d5.frozen-tracklet-audit-reference.v1",
            "model_id": "test-frozen-model",
            "bundle_relative_path": "ignored/model_bundle",
            "expected_hashes": bundle,
            "admission_policy": {
                "g1": False,
                "assist": False,
                "authority": False,
                "default_model": False,
            },
        },
    )
    heldout = {
        "schema_version": "d5.tracklet-heldout-model-evaluation.v1",
        "evaluated_at_utc": "2026-07-26T12:35:17Z",
        "development_model": {
            "admission_status": "development_only_fail_closed",
            "bundle_manifest_sha256": bundle["manifest_sha256"],
            "weights_sha256": bundle["weights_sha256"],
        },
        "heldout_assessment": {
            "authority_enabled": False,
            "g1_assist_eligible": False,
            "status": "pass",
        },
        "identity_and_truth_safety": {
            "global_track_id_created_or_rebound": False,
            "online_truth_feature_count": 0,
        },
        "heldout_corpus": {
            "episode_count": 2,
            "manifest_content_sha256": "4" * 64,
            "manifest_sha256": "5" * 64,
            "profile_version": "test-heldout-profile-v1",
            "scenario_scale_cell_count": 1,
            "seed_values": [1000, 1001],
        },
    }
    _write_content_json(paths["heldout"], heldout)
    lineage_records = [
        {
            "schema_version": "d5.tracklet-paired-shadow-lineage.v1",
            "episode_uid": f"episode-{index}",
        }
        for index in range(2)
    ]
    paths["lineage"].write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in lineage_records
        ),
        encoding="utf-8",
    )
    heldout_sha = sha256_file(paths["heldout"])
    heldout_content = _read_json(paths["heldout"])["content_sha256"]
    input_hashes = {
        "bundle_checksums_sha256": bundle["checksums_sha256"],
        "bundle_manifest_sha256": bundle["manifest_sha256"],
        "bundle_weights_sha256": bundle["weights_sha256"],
        "corpus_config_sha256": "6" * 64,
        "corpus_content_sha256": "4" * 64,
        "corpus_manifest_sha256": "5" * 64,
        "heldout_report_content_sha256": heldout_content,
        "heldout_report_sha256": heldout_sha,
    }
    paired = {
        "schema_version": "d5.tracklet-paired-shadow.v2",
        "evaluated_at_utc": "2026-07-26T12:35:17Z",
        "status": "pass",
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "runtime_default_changed": False,
            "paired_shadow_passed": True,
            "rule_fallback": True,
        },
        "paired_shadow_assessment": {
            "g1": False,
            "assist": False,
            "authority": False,
            "status": "pass",
        },
        "identity_and_truth_safety": {
            "g1": False,
            "assist": False,
            "authority": False,
            "global_track_id_created_or_rebound": False,
            "global_track_id_rewrite_count": 0,
            "online_truth_feature_count": 0,
            "same_camera_mutual_exclusion_violation_count": 0,
        },
        "frozen_decision": {
            "candidate_gate_changed": False,
            "temperature_reestimated": False,
            "threshold_reselected": False,
            "weights_updated": False,
        },
        "input_artifacts_unchanged": True,
        "input_hashes_before": input_hashes,
        "input_hashes_after": input_hashes,
        "input_spec": {"expected_hashes": input_hashes},
        "heldout_lineage_binding": {
            "bundle_manifest_sha256": bundle["manifest_sha256"],
            "bundle_weights_sha256": bundle["weights_sha256"],
            "corpus_manifest_sha256": "5" * 64,
            "corpus_content_sha256": "4" * 64,
            "report_used_for_predictions": False,
        },
        "paired_lineage": {
            "filename": paths["lineage"].name,
            "record_count": 2,
            "schema_version": "d5.tracklet-paired-shadow-lineage.v1",
            "sha256": sha256_file(paths["lineage"]),
        },
        "totals": {
            "candidate_edge_count": 12,
            "episode_count": 2,
            "labeled_candidate_edge_count": 12,
            "node_count": 8,
            "scenario_scale_cell_count": 1,
            "seed_count": 2,
        },
        "overall": {
            "candidate_recall": 0.98,
            "control": {
                "edge": {"f1": 0.5},
                "cluster_pairwise": {"f1": 0.45},
            },
            "model": {
                "edge": {"f1": 0.8},
                "cluster_pairwise": {
                    "f1": 0.75,
                    "false_merge_rate": 0.05,
                },
                "latency_ms": {
                    "scoring_p50": 1.0,
                    "scoring_p95": 2.0,
                },
            },
        },
        "runtime": {"max_rss_mib": 128.0},
        "runtime_fallback_probe": {"fallback_rate": 1.0},
        "feature_label_diagnostics": {
            "maximum_single_feature_auc": {
                "available": True,
                "best_direction_auc": 0.72,
                "feature": "angular_velocity_delta_rad_s",
            },
            "shared_global_track_count": {
                "near_deterministic": False,
                "strata": {
                    "0": {"edge_count": 12},
                    "1": {"edge_count": 0},
                    "other": {"edge_count": 0},
                },
            },
        },
        "robustness_profiles": [
            {
                "profile": {"profile_id": "timestamp_jitter"},
                "model": {
                    "edge": {"f1": 0.7},
                    "cluster_pairwise": {
                        "f1": 0.65,
                        "false_merge_rate": 0.1,
                    },
                },
            }
        ],
    }
    _write_content_json(paths["paired"], paired)
    _write_summary(paths, bundle)
    return paths


def _assemble(
    paths: dict[str, Path],
    output: Path,
    *,
    expected_heldout_sha256: str | None = None,
) -> dict:
    return dict(
        assemble_frozen_tracklet_registry(
            paths["reference"],
            paths["summary"],
            paths["heldout"],
            paths["paired"],
            paths["lineage"],
            output,
            expected_reference_sha256=sha256_file(paths["reference"]),
            expected_frozen_audit_summary_sha256=sha256_file(paths["summary"]),
            expected_heldout_report_sha256=(
                expected_heldout_sha256 or sha256_file(paths["heldout"])
            ),
            expected_paired_shadow_report_sha256=sha256_file(paths["paired"]),
            expected_paired_lineage_sha256=sha256_file(paths["lineage"]),
        )
    )


def _write_summary(paths: dict[str, Path], bundle: dict[str, str]) -> None:
    heldout = _read_json(paths["heldout"])
    paired = _read_json(paths["paired"])
    overall = paired["overall"]
    robustness = [
        {
            "profile_id": item["profile"]["profile_id"],
            "model_edge_f1": item["model"]["edge"]["f1"],
            "model_cluster_f1": item["model"]["cluster_pairwise"]["f1"],
            "model_cluster_false_merge_rate": item["model"]["cluster_pairwise"][
                "false_merge_rate"
            ],
        }
        for item in paired["robustness_profiles"]
    ]
    _write_plain_json(
        paths["summary"],
        {
            "schema_version": "d5.frozen-tracklet-audit-summary.v1",
            "evaluated_at_utc": paired["evaluated_at_utc"],
            "status": paired["status"],
            "model": {
                "reference_sha256": sha256_file(paths["reference"]),
                "model_id": "test-frozen-model",
                **bundle,
                "strict_load_passed": True,
                "admission": {
                    "status": "development_only_fail_closed",
                    "default_model": False,
                    "g1_assist_eligible": False,
                },
            },
            "catalog": dict(paired["totals"]),
            "heldout": {
                "status": heldout["heldout_assessment"]["status"],
                "content_sha256": heldout["content_sha256"],
                "report_file_sha256": sha256_file(paths["heldout"]),
            },
            "paired_shadow": {
                "status": paired["paired_shadow_assessment"]["status"],
                "content_sha256": paired["content_sha256"],
                "report_file_sha256": sha256_file(paths["paired"]),
                "markdown_sha256": "7" * 64,
                "lineage_sha256": sha256_file(paths["lineage"]),
                "candidate_recall": overall["candidate_recall"],
                "rule_edge_f1": overall["control"]["edge"]["f1"],
                "model_edge_f1": overall["model"]["edge"]["f1"],
                "rule_cluster_f1": overall["control"]["cluster_pairwise"]["f1"],
                "model_cluster_f1": overall["model"]["cluster_pairwise"]["f1"],
                "model_cluster_false_merge_rate": overall["model"][
                    "cluster_pairwise"
                ]["false_merge_rate"],
                "model_latency_p50_ms": overall["model"]["latency_ms"][
                    "scoring_p50"
                ],
                "model_latency_p95_ms": overall["model"]["latency_ms"][
                    "scoring_p95"
                ],
                "peak_rss_mib": paired["runtime"]["max_rss_mib"],
                "runtime_fallback_rate": paired["runtime_fallback_probe"][
                    "fallback_rate"
                ],
                "maximum_single_feature_auc": paired[
                    "feature_label_diagnostics"
                ]["maximum_single_feature_auc"],
                "robustness_profiles": robustness,
            },
            "authority": {
                "g1": False,
                "assist": False,
                "authority": False,
                "default_model_changed": False,
                "active_visual_ppo_started": False,
            },
            "limitations": ["producer_summary_is_not_authoritative"],
        },
    )


def _set_auc(paths: dict[str, Path], auc: float) -> None:
    paired = _read_json(paths["paired"])
    paired["feature_label_diagnostics"]["maximum_single_feature_auc"][
        "best_direction_auc"
    ] = auc
    _write_content_json(paths["paired"], paired)
    _refresh_summary_paired_bindings(paths)


def _refresh_summary_paired_bindings(paths: dict[str, Path]) -> None:
    bundle = _read_json(paths["reference"])["expected_hashes"]
    _write_summary(paths, bundle)


def _read_checksums(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ")
        result[name] = digest
    return result


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_content_json(path: Path, value: dict) -> None:
    payload = dict(value)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = sha256_json(payload)
    _write_plain_json(path, payload)


def _write_plain_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
