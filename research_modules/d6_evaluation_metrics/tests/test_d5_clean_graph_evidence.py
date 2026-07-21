from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import pytest

from d6_evaluation_metrics import (
    D5_CLEAN_GRAPH_CRITERIA,
    D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION,
    D5CleanGraphArtifact,
    D5CleanGraphEvidenceError,
    D5CleanGraphEvidenceInputs,
    audit_d5_clean_graph_evidence,
    load_d5_clean_graph_evidence_inputs,
    write_d5_clean_graph_evidence_report,
)


_SPLIT_SEEDS = {
    "train": list(range(60)),
    "validation": list(range(60, 80)),
    "test": list(range(80, 100)),
}
_SEED_COUNTS = {name: len(values) for name, values in _SPLIT_SEEDS.items()}


@dataclass(frozen=True)
class _Fixture:
    inputs: D5CleanGraphEvidenceInputs
    paths: dict[str, Path]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _with_content_sha(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha_bytes(_canonical_bytes(result))
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _balance(episode_count: int) -> dict[str, int]:
    return {
        "candidate_edges": episode_count * 2,
        "positive_candidate_edges": episode_count,
        "negative_candidate_edges": episode_count,
        "unlabeled_candidate_edges": 0,
    }


def _dataset(prefix: str) -> dict[str, Any]:
    episodes = []
    for split, seeds in _SPLIT_SEEDS.items():
        for seed in seeds:
            episodes.append(
                {
                    "episode_uid": f"{prefix}-{seed}",
                    "seed": seed,
                    "split": split,
                    "labels_complete": True,
                    "candidate_recall_available": True,
                    "edge_count": 2,
                    "class_balance": _balance(1),
                }
            )
    return {
        "schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "evaluator_label_schema_version": "d5.tracklet-evaluator-labels.v1",
        "split_policy": {
            "edge_level_random_split": False,
            "shared_seed_values_atomic_across_scenarios": True,
            "unit": "whole_episode_grouped_by_scenario_version_and_seed",
            "split_seed": 20260720,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
        },
        "episodes": episodes,
        "class_balance_by_split": {
            split: _balance(len(seeds)) for split, seeds in _SPLIT_SEEDS.items()
        },
        "candidate_recall_availability": {
            "status": "available",
            "available_episode_count": 100,
            "episode_count": 100,
        },
    }


def _canonical_view(source_sha256: str) -> dict[str, Any]:
    return _with_content_sha(
        {
            "schema_version": "d5.canonical-seed-split-view.v1",
            "consumer": "tracklet_graph",
            "source": {"manifest_sha256": source_sha256},
            "view_contract": {
                "source_manifest_modified": False,
                "source_artifacts_modified": False,
                "complete_episode_rebucket_only": True,
                "sample_copy_allowed": False,
                "online_offline_content_rewrite_allowed": False,
                "default_legacy_loader_unchanged": True,
            },
            "canonical_split": {
                "seed_counts": _SEED_COUNTS,
                "seed_values": _SPLIT_SEEDS,
                "reserved_evaluation_seed_overlap": [],
            },
        }
    )


def _admission_flags() -> dict[str, Any]:
    return {
        "full_sample_audit_required": True,
        "g1_assist_allowed": False,
        "global_track_id_created_or_rebound": False,
        "model_training_performed": False,
        "producer_complete": True,
        "pt_generated": False,
    }


def _readiness(training_sha256: str) -> dict[str, Any]:
    selected = {
        "episode_count": 200,
        "candidate_edge_count": 400,
        "unlabeled_candidate_edge_count": 0,
        "label_availability_ratio": 1.0,
        "seed_counts": _SEED_COUNTS,
        "reserved_evaluation_seed_overlap": [],
        "training_set_sha256": training_sha256,
    }
    return {
        "schema_version": "d5.tracklet-composite-admission-readiness.v1",
        "criteria": deepcopy(dict(D5_CLEAN_GRAPH_CRITERIA)),
        "data_support_readiness": {
            "existing_gate_results": [{"name": "clean_labels", "passed": True}],
            "passed": True,
            "status": "pass",
            "label_availability_100_percent": True,
        },
        "training_readiness": {
            "passed": True,
            "status": "pass",
            "failure_reasons": [],
        },
        "promotion_readiness": {
            "g1_assist_eligible": False,
            "model_training_performed": False,
            "pt_generated": False,
            "passed": False,
            "status": "awaiting_new_model_evidence",
        },
        "identity_safety": {
            "deterministic_rule_fallback_preserved": True,
            "geometry_gate_preserved": True,
            "global_track_id_rewrite_allowed": False,
            "same_camera_mutual_exclusion_preserved": True,
            "model_output": "same_target_probability_on_existing_candidate_edges_only",
        },
        "selected_corpus": selected,
        "split_summaries": {
            split: {
                "positive_candidate_edges": len(seeds) * 2,
                "negative_candidate_edges": len(seeds) * 2,
                "unlabeled_candidate_edges": 0,
            }
            for split, seeds in _SPLIT_SEEDS.items()
        },
    }


def _artifact(path: Path) -> D5CleanGraphArtifact:
    return D5CleanGraphArtifact(path=path, sha256=_sha_file(path))


def _build_fixture(root: Path) -> _Fixture:
    paths = {
        "supplemental_summary": root / "supplemental_summary.json",
        "composite_admission": root / "composite_admission.json",
        "composite_view": root / "composite_view.json",
        "formal_canonical_view": root / "formal_view.json",
        "supplemental_canonical_view": root / "supplemental_view.json",
        "supplemental_manifest": root / "supplemental_manifest.json",
        "supplemental_dataset_manifest": root / "supplemental_dataset.json",
        "formal_source_manifest": root / "formal_dataset.json",
    }
    _write_json(paths["formal_source_manifest"], _dataset("formal"))
    _write_json(paths["supplemental_dataset_manifest"], _dataset("supplemental"))
    formal_sha = _sha_file(paths["formal_source_manifest"])
    supplemental_dataset_sha = _sha_file(paths["supplemental_dataset_manifest"])

    _write_json(
        paths["formal_canonical_view"],
        _canonical_view(formal_sha),
    )
    _write_json(
        paths["supplemental_canonical_view"],
        _canonical_view(supplemental_dataset_sha),
    )

    supplemental_manifest = _with_content_sha(
        {
            "schema_version": "d5.tracklet-supplemental-manifest.v1",
            "source": {"git_commit": "1" * 40, "repository_dirty": False},
            "formal_source": {
                "manifest_sha256": formal_sha,
                "modified": False,
            },
            "dataset": {
                "manifest_sha256": supplemental_dataset_sha,
                "episode_count": 100,
                "candidate_edge_count": 200,
                "class_balance": _balance(100),
            },
            "admission": _admission_flags(),
            "seed_registries": {
                "canonical_seed_counts": _SEED_COUNTS,
                "reserved_evaluation_seeds": list(range(1000, 1020)),
                "reserved_seed_overlap": [],
            },
        }
    )
    _write_json(paths["supplemental_manifest"], supplemental_manifest)
    supplemental_manifest_sha = _sha_file(paths["supplemental_manifest"])

    training_sha = "a" * 64
    readiness = _readiness(training_sha)
    composite_view = _with_content_sha(
        {
            "schema_version": "d5.tracklet-composite-admission-view.v1",
            "selection_policy_version": "d5-tracklet-complete-label-source-selection-v1",
            "source_contract": {
                "complete_seed_atomic_split_required": True,
                "reserved_seed_allowed": False,
                "sample_copy_allowed": False,
                "source_artifact_modified": False,
                "source_label_backfill_allowed": False,
                "source_manifest_modified": False,
            },
            "sources": {
                "formal_source_modified": False,
                "supplemental_source_modified": False,
                "supplemental_source_repository_dirty": False,
                "formal_manifest_sha256": formal_sha,
                "supplemental_manifest_sha256": supplemental_manifest_sha,
            },
            "canonical_subviews": {
                "formal": {
                    "file": paths["formal_canonical_view"].name,
                    "file_sha256": _sha_file(paths["formal_canonical_view"]),
                    "content_sha256": json.loads(
                        paths["formal_canonical_view"].read_text(encoding="utf-8")
                    )["content_sha256"],
                },
                "supplemental": {
                    "file": paths["supplemental_canonical_view"].name,
                    "file_sha256": _sha_file(paths["supplemental_canonical_view"]),
                    "content_sha256": json.loads(
                        paths["supplemental_canonical_view"].read_text(
                            encoding="utf-8"
                        )
                    )["content_sha256"],
                },
            },
            "selection": deepcopy(readiness["selected_corpus"]),
            "readiness": readiness,
        }
    )
    _write_json(paths["composite_view"], composite_view)
    composite_view_sha = _sha_file(paths["composite_view"])

    composite_admission = deepcopy(readiness)
    composite_admission.update(
        {
            "view_manifest_sha256": composite_view_sha,
            "view_content_sha256": composite_view["content_sha256"],
            "sources": {
                "formal_manifest_sha256": formal_sha,
                "supplemental_manifest_sha256": supplemental_manifest_sha,
                "formal_source_modified": False,
                "supplemental_source_modified": False,
                "supplemental_source_repository_dirty": False,
            },
        }
    )
    _write_json(
        paths["composite_admission"],
        _with_content_sha(composite_admission),
    )

    summary = _with_content_sha(
        {
            "schema_version": "d5.tracklet-supplemental-summary.v1",
            "source_repository_dirty": False,
            "canonical_seed_counts": _SEED_COUNTS,
            "unique_seed_count": 100,
            "manifest_sha256": supplemental_manifest_sha,
            "dataset_manifest_sha256": supplemental_dataset_sha,
            "formal_manifest_sha256": formal_sha,
            "scenario_scale_cell_count": 45,
            "episode_count": 100,
            "candidate_edge_count": 200,
            "class_balance": _balance(100),
            "label_availability_ratio": 1.0,
            "admission": _admission_flags(),
        }
    )
    _write_json(paths["supplemental_summary"], summary)
    inputs = D5CleanGraphEvidenceInputs(
        **{name: _artifact(path) for name, path in paths.items()}
    )
    return _Fixture(inputs=inputs, paths=paths)


def _mutate_json_artifact(
    fixture: _Fixture,
    name: str,
    mutation: Callable[[dict[str, Any]], None],
) -> D5CleanGraphEvidenceInputs:
    path = fixture.paths[name]
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    if "content_sha256" in payload:
        payload = _with_content_sha(payload)
    _write_json(path, payload)
    return replace(fixture.inputs, **{name: _artifact(path)})


def _attach_model_bundle(
    fixture: _Fixture,
    *,
    cell_count: int = 45,
    extra_report_field: bool = False,
) -> D5CleanGraphEvidenceInputs:
    weights = fixture.paths["supplemental_summary"].parent / "model.pt"
    config = fixture.paths["supplemental_summary"].parent / "model_config.json"
    report_path = fixture.paths["supplemental_summary"].parent / "model_report.json"
    weights.write_bytes(b"synthetic-contract-test-weights")
    _write_json(config, {"model": "contract-test"})
    metrics = {
        "precision": 0.98,
        "recall": 0.96,
        "f1": 0.97,
        "candidate_recall": 0.99,
        "false_merge_rate": 0.005,
        "ece": 0.02,
    }
    report: dict[str, Any] = {
        "schema_version": "d5.tracklet-graph-model-evaluation.v1",
        "evaluation_date": "2026-07-21",
        "model_id": "synthetic-contract-test-only",
        "weights_sha256": _sha_file(weights),
        "config_sha256": _sha_file(config),
        "training_source_sha256": "a" * 64,
        "test_seed_values": _SPLIT_SEEDS["test"],
        "test_metrics": metrics,
        "cell_metrics": [
            {
                "cell_id": f"cell-{index:02d}",
                "scenario": "contract-test",
                "scale": index + 1,
                "sample_count": 10,
                **metrics,
            }
            for index in range(cell_count)
        ],
        "latency": {
            "device": "synthetic-test-device",
            "sample_count": 100,
            "p50_ms": 10.0,
            "p95_ms": 20.0,
            "max_ms": 30.0,
        },
    }
    if extra_report_field:
        report["g1_allowed"] = True
    _write_json(report_path, _with_content_sha(report))
    return replace(
        fixture.inputs,
        model_report=_artifact(report_path),
        model_weights=_artifact(weights),
        model_config=_artifact(config),
    )


def _assert_error(code: str, callable_: Callable[[], object]) -> None:
    with pytest.raises(D5CleanGraphEvidenceError) as caught:
        callable_()
    assert caught.value.code == code


def test_clean_data_is_complete_but_model_and_promotion_remain_closed(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    result = audit_d5_clean_graph_evidence(fixture.inputs)

    layers = result["evidence_layers"]
    assert layers["data_support"]["status"] == "complete"
    assert layers["training_source"]["status"] == "complete"
    assert layers["internal_model_test"]["status"] == "unavailable"
    assert layers["held_out_seed"]["status"] == "unavailable"
    assert layers["paired_shadow"]["status"] == "unavailable"
    assert result["data_summary"]["reserved_seed_overlap"] == []
    assert result["data_summary"]["unlabeled_candidate_edge_count"] == 0
    assert result["admission"] == {
        "clean_data_supported": True,
        "training_source_supported": True,
        "model_promotion_allowed": False,
        "g1_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "formal_ppo_reward_available": False,
        "causal_claim_available": False,
        "counterfactual_available": False,
        "status": "data_ready_model_admission_closed",
        "promotion_blockers": [
            "internal_model_test_unavailable",
            "held_out_seed_evaluation_unavailable",
            "same_seed_paired_shadow_unavailable",
            "g1_assist_authority_not_admitted",
        ],
    }


def test_input_spec_and_cli_are_hash_bound(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    spec = tmp_path / "inputs.json"
    _write_json(spec, fixture.inputs.to_dict())
    loaded = load_d5_clean_graph_evidence_inputs(
        spec,
        expected_sha256=_sha_file(spec),
    )
    assert loaded.resolved() == fixture.inputs.resolved()

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_d5_clean_graph_evidence.py"
    )
    output_dir = tmp_path / "report"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--inputs-json",
            str(spec),
            "--inputs-sha256",
            _sha_file(spec),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "d5_clean_graph_evidence.json").is_file()
    assert (output_dir / "D5_CLEAN_GRAPH_EVIDENCE_CN.md").is_file()

    _assert_error(
        "input_specification_sha256_mismatch",
        lambda: load_d5_clean_graph_evidence_inputs(
            spec,
            expected_sha256="0" * 64,
        ),
    )


def test_artifact_file_hash_tamper_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    with fixture.paths["supplemental_summary"].open("ab") as stream:
        stream.write(b" ")
    _assert_error(
        "supplemental_summary_sha256_mismatch",
        lambda: audit_d5_clean_graph_evidence(fixture.inputs),
    )


def test_dirty_source_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _mutate_json_artifact(
        fixture,
        "supplemental_summary",
        lambda value: value.update(source_repository_dirty=True),
    )
    _assert_error(
        "dirty_training_source",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_source_rewrite_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["view_contract"]["source_manifest_modified"] = True

    inputs = _mutate_json_artifact(
        fixture,
        "formal_canonical_view",
        mutate,
    )
    _assert_error(
        "source_rewrite_detected",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_reserved_seed_leakage_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["canonical_split"]["seed_values"]["test"][0] = 1000

    inputs = _mutate_json_artifact(
        fixture,
        "formal_canonical_view",
        mutate,
    )
    _assert_error(
        "reserved_seed_leakage",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_unlabeled_edge_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["class_balance"]["positive_candidate_edges"] -= 1
        value["class_balance"]["unlabeled_candidate_edges"] = 1

    inputs = _mutate_json_artifact(
        fixture,
        "supplemental_summary",
        mutate,
    )
    _assert_error(
        "clean_edge_support_incomplete",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_lowered_admission_threshold_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["criteria"]["minimum_test_precision"] = 0.90

    inputs = _mutate_json_artifact(
        fixture,
        "composite_admission",
        mutate,
    )
    _assert_error(
        "admission_threshold_contract_mismatch",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_partial_model_bundle_is_rejected_before_audit(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    report = tmp_path / "model_report.json"
    _write_json(report, {})
    with pytest.raises(ValueError, match="must be supplied together"):
        replace(fixture.inputs, model_report=_artifact(report))


@pytest.mark.parametrize(
    ("cell_count", "extra_report_field", "expected_code"),
    [
        (44, False, "model_cell_count_mismatch"),
        (45, True, "object_keys_mismatch"),
    ],
)
def test_forged_or_incomplete_model_report_fails_closed(
    tmp_path: Path,
    cell_count: int,
    extra_report_field: bool,
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_model_bundle(
        fixture,
        cell_count=cell_count,
        extra_report_field=extra_report_field,
    )
    _assert_error(
        expected_code,
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_complete_synthetic_internal_test_does_not_open_external_gates(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    result = audit_d5_clean_graph_evidence(_attach_model_bundle(fixture))

    assert result["evidence_layers"]["internal_model_test"]["status"] == "complete"
    assert result["evidence_layers"]["held_out_seed"]["status"] == "unavailable"
    assert result["evidence_layers"]["paired_shadow"]["status"] == "unavailable"
    assert result["admission"]["model_promotion_allowed"] is False
    assert result["admission"]["g1_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False
    assert result["admission"]["rule_fallback_required"] is True
    assert result["admission"]["formal_ppo_reward_available"] is False


def test_report_writer_does_not_mutate_inputs(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    before = {name: _sha_file(path) for name, path in fixture.paths.items()}
    outputs = write_d5_clean_graph_evidence_report(
        fixture.inputs,
        tmp_path / "output",
    )
    after = {name: _sha_file(path) for name, path in fixture.paths.items()}
    assert before == after
    assert set(outputs) == {"json", "markdown"}
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "模型内部测试" in markdown
    assert "unavailable" in markdown
    assert "G1、辅助模式和控制权限保持关闭" in markdown


def test_input_spec_schema_is_explicit() -> None:
    assert D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION == "d6.d5-clean-graph-inputs.v1"
