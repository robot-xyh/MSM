from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from d6_evaluation_metrics.canonical_seed_split_readiness import (
    audit_canonical_seed_split_readiness,
)
from d6_evaluation_metrics.learning_run_readiness import (
    FORMAL_RUNTIME_MINIMUM_FREE_BYTES,
    LEARNING_VARIANTS,
    READINESS_GATES,
    LearningRunReadinessError,
    audit_learning_run_readiness,
    build_learning_run_readiness_input,
    load_learning_run_readiness_output,
    validate_learning_run_readiness_input,
    write_learning_run_readiness_report,
)
from d6_evaluation_metrics.learning_run_source_adapters import (
    CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION,
)


_COMMIT = "1" * 40
_SCHEDULE_SHA = "2" * 64
_SPLIT_HASH = "3" * 64
_TRAINING_SEEDS = list(range(100))
_RESERVED_SEEDS = list(range(1000, 1020))
_SPLITS = ("train", "validation", "test")
_UNTRUSTED_WRAPPER_SCHEMAS = {
    "model_source": "d6.learning-run-model-source-evidence.v1",
    "frozen_unseen_seeds": "d6.learning-run-frozen-seed-evidence.v1",
    "identifiable_adoption": (
        "d6.learning-run-identifiable-adoption-evidence.v1"
    ),
    "runtime_ack": "d6.learning-run-runtime-ack-evidence.v1",
    "physical_window": "d6.learning-run-physical-window-evidence.v1",
    "same_key_r0": "d6.learning-run-same-key-r0-evidence.v1",
    "paired_non_degradation": (
        "d6.learning-run-paired-non-degradation-evidence.v1"
    ),
    "truth_use": "d6.learning-run-truth-use-evidence.v1",
    "finite_state": "d6.learning-run-finite-state-evidence.v1",
    "external_permission": (
        "d6.learning-run-external-permission-evidence.v1"
    ),
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha_json(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value) + b"\n")


def _file_reference(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "file_sha256": sha256(path.read_bytes()).hexdigest(),
    }


def _canonical_assignment() -> dict[int, str]:
    ordered = sorted(
        _TRAINING_SEEDS,
        key=lambda seed: (
            sha256(
                f"d3_numeric_seed_atomic_split_v2|20260720\0{seed}".encode()
            ).hexdigest(),
            seed,
        ),
    )
    return {
        seed: (
            "test"
            if index < 20
            else "validation"
            if index < 40
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _split_values(assignments: dict[int, str]) -> dict[str, list[int]]:
    return {
        split: sorted(
            seed for seed, value in assignments.items() if value == split
        )
        for split in _SPLITS
    }


def _build_canonical_seed_fixture(
    root: Path,
) -> tuple[Path, Path, dict[str, dict[str, str]]]:
    generation = root / "generation"
    dataset = generation / "learning_dataset"
    assignments = _canonical_assignment()
    split_values = _split_values(assignments)
    training_registry = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "training_seed_count": 100,
        "training_seeds": _TRAINING_SEEDS,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "overlap_count": 0,
        "git_commit": _COMMIT,
        "repository_dirty": False,
        "schedule_sha256": _SCHEDULE_SHA,
    }
    training_path = generation / "training_seed_registry.json"
    _write_json(training_path, training_registry)

    assignment_rows = [
        {"seed": seed, "split": assignments[seed]}
        for seed in _TRAINING_SEEDS
    ]
    registry: dict[str, object] = {
        "schema_version": "scalable3d-shared-seed-split-registry-v1",
        "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
        "ordering_compatibility_version": "d3_numeric_seed_atomic_split_v2",
        "source": {
            "training_seed_registry_schema_version": (
                "scalable3d-training-seed-registry-v1"
            ),
            "training_seed_registry_sha256": sha256(
                training_path.read_bytes()
            ).hexdigest(),
            "git_commit": _COMMIT,
            "repository_dirty": False,
            "schedule_sha256": _SCHEDULE_SHA,
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "minimum_test_seed_count": 20,
        "training_seed_count": 100,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "training_reserved_overlap_count": 0,
        "split_seed_values": split_values,
        "assignments": assignment_rows,
        "assignment_sha256": _sha_json(assignment_rows),
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    registry["content_sha256"] = _sha_json(registry)
    registry_path = generation / "shared" / "registry.json"
    _write_json(registry_path, registry)

    d3_path = dataset / "d3_assignment" / "dataset_manifest.json"
    _write_json(
        d3_path,
        {
            "schema_version": "d3_learning_dataset_v2",
            "episode_count": 100,
            "frame_count": 200,
            "split_hash": _SPLIT_HASH,
            "split_policy_version": "d3_numeric_seed_atomic_split_v2",
            "split_policy": {
                "shared_seed_values_atomic_across_scenarios": True,
                "unit": "whole_episode_grouped_by_numeric_seed_across_scenarios",
                "split_seed": 20260720,
                "validation_fraction": 0.2,
                "test_fraction": 0.2,
            },
            "split_seed_values": split_values,
        },
    )
    d4_path = dataset / "d4_region" / "manifest.json"
    _write_json(
        d4_path,
        {
            "schema": "d4-region-learning-dataset-v1",
            "split": {
                **{
                    f"{split}_seeds": values
                    for split, values in split_values.items()
                },
                "split_sha256": _SPLIT_HASH,
            },
            "episodes": [
                {
                    "source": {"seed": seed},
                    "split": assignments[seed],
                    "frame_count": 2,
                }
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    d5_policy = {
        "shared_seed_values_atomic_across_scenarios": True,
        "unit": "whole_episode_grouped_by_scenario_version_and_seed",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
    }
    d5_graph_path = dataset / "d5_tracklet_graph" / "manifest.json"
    _write_json(
        d5_graph_path,
        {
            "schema_version": "d5.tracklet-dataset.v2",
            "split_sha256": _SPLIT_HASH,
            "split_policy": d5_policy,
            "episodes": [
                {
                    "seed": seed,
                    "split": assignments[seed],
                    "edge_count": 3,
                }
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    d5_active_path = dataset / "d5_active_vision" / "manifest.json"
    _write_json(
        d5_active_path,
        {
            "schema_version": "d5.active-vision-episode-dataset.v3",
            "split_sha256": _SPLIT_HASH,
            "split_policy": d5_policy,
            "episodes": [
                {
                    "seed": seed,
                    "split": assignments[seed],
                    "sample_count": 4,
                }
                for seed in _TRAINING_SEEDS
            ],
        },
    )
    references = {
        "training_seed_registry": _file_reference(root, training_path),
        "shared_seed_split_registry": _file_reference(root, registry_path),
        "d3_assignment_manifest": _file_reference(root, d3_path),
        "d4_region_manifest": _file_reference(root, d4_path),
        "d5_tracklet_graph_manifest": _file_reference(root, d5_graph_path),
        "d5_active_vision_manifest": _file_reference(root, d5_active_path),
    }
    return dataset, registry_path, references


def _write_seed_reference(
    root: Path,
    *,
    variant: str,
    artifacts: dict[str, dict[str, str]],
) -> dict[str, str]:
    body = {
        "schema_version": CANONICAL_SEED_SOURCE_REFERENCE_SCHEMA_VERSION,
        "variant": variant,
        "artifacts": artifacts,
    }
    payload = {**body, "content_sha256": _sha_json(body)}
    path = root / "references" / f"{variant}.json"
    _write_json(path, payload)
    return _file_reference(root, path)


def _unavailable(reason: str) -> dict[str, object]:
    return {
        "availability": False,
        "source_artifact": None,
        "reason_codes": [reason],
    }


def _storage(free_gib: int = 25) -> dict[str, object]:
    return {
        "availability": True,
        "source_class": "filesystem_disk_usage_snapshot",
        "observed_at_utc": "2026-07-27T12:00:00Z",
        "mounts": [
            {
                "path": "/evidence",
                "available_bytes": free_gib * 1024**3,
                "eligible_for_formal_output": True,
            }
        ],
        "reason_codes": [],
    }


def _partial_manifest(
    root: Path,
    *,
    free_gib: int = 25,
) -> tuple[dict[str, object], dict[str, dict[str, str]]]:
    _, _, artifacts = _build_canonical_seed_fixture(root)
    variants: dict[str, object] = {}
    for variant in LEARNING_VARIANTS:
        gates = {
            gate: _unavailable(f"{variant.lower()}_{gate}_not_supplied")
            for gate in READINESS_GATES
        }
        gates["frozen_unseen_seeds"] = {
            "availability": True,
            "source_artifact": _write_seed_reference(
                root,
                variant=variant,
                artifacts=artifacts,
            ),
            "reason_codes": [],
        }
        variants[variant] = {"variant": variant, "gates": gates}
    return (
        build_learning_run_readiness_input(
            audit_id="existing-canonical-seed-adapter-fixture",
            variants=variants,
            storage=_storage(free_gib),
        ),
        artifacts,
    )


def _rebuild_manifest(manifest: dict[str, object]) -> dict[str, object]:
    return build_learning_run_readiness_input(
        audit_id=manifest["audit_id"],
        variants=manifest["variants"],
        storage=manifest["storage"],
    )


def _rehash_content(payload: dict[str, object]) -> None:
    body = dict(payload)
    body.pop("content_sha256", None)
    payload["content_sha256"] = _sha_json(body)


def _write_untrusted_wrapper(
    root: Path,
    *,
    variant: str,
    gate_name: str,
) -> dict[str, str]:
    body = {
        "schema_version": _UNTRUSTED_WRAPPER_SCHEMAS[gate_name],
        "variant": variant,
        "records": [
            {
                "audit_passed": True,
                "granted": True,
                "adopted": True,
                "acked": True,
                "physical_window_confirmed": True,
                "same_key_r0": True,
            }
        ],
    }
    payload = {**body, "content_sha256": _sha_json(body)}
    path = root / "untrusted" / variant / f"{gate_name}.json"
    _write_json(path, payload)
    return _file_reference(root, path)


def test_existing_canonical_seed_auditor_is_the_only_positive_adapter(
    tmp_path: Path,
) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    dataset = tmp_path / "generation" / "learning_dataset"
    registry = tmp_path / "generation" / "shared" / "registry.json"
    direct = audit_canonical_seed_split_readiness(dataset, registry)
    assert direct["joint_training"]["available"] is True

    result = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )
    for variant in LEARNING_VARIANTS:
        seed_gate = result["variants"][variant]["gates"][
            "frozen_unseen_seeds"
        ]
        assert seed_gate["availability"] is True
        assert seed_gate["passed"] is True
        assert seed_gate["facts"] == {
            "evaluation_seed_count": 20,
            "training_overlap_count": 0,
            "frozen": True,
        }
        assert (
            result["variants"][variant]["formal_evidence_readiness"]["ready"]
            is None
        )
    assert result["aggregate"]["formal_evidence_ready_variant_count"] == 0
    assert all(value is False for value in result["permissions"].values())

    paths = write_learning_run_readiness_report(tmp_path / "report", result)
    assert load_learning_run_readiness_output(paths["json"]) == result


def test_ten_self_signed_wrappers_cannot_create_formal_readiness(
    tmp_path: Path,
) -> None:
    variants: dict[str, object] = {}
    for variant in LEARNING_VARIANTS:
        variants[variant] = {
            "variant": variant,
            "gates": {
                gate: {
                    "availability": True,
                    "source_artifact": _write_untrusted_wrapper(
                        tmp_path,
                        variant=variant,
                        gate_name=gate,
                    ),
                    "reason_codes": [],
                }
                for gate in READINESS_GATES
            },
        }
    manifest = build_learning_run_readiness_input(
        audit_id="self-signed-wrapper-attack",
        variants=variants,
        storage=_storage(),
    )

    result = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )
    assert result["aggregate"]["formal_evidence_ready_variant_count"] == 0
    for row in result["variants"].values():
        assert row["formal_evidence_readiness"]["ready"] is None
        assert all(
            gate["availability"] is False for gate in row["gates"].values()
        )
        assert all(
            "gate_source_schema_unsupported" in gate["reason_codes"]
            for gate in row["gates"].values()
        )


def test_manifest_self_signed_facts_are_rejected(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    gate = manifest["variants"]["A1"]["gates"]["frozen_unseen_seeds"]
    gate["facts"] = {
        "evaluation_seed_count": 20,
        "training_overlap_count": 0,
        "frozen": True,
    }
    _rehash_content(manifest)

    with pytest.raises(
        LearningRunReadinessError,
        match="readiness_fields_mismatch",
    ):
        validate_learning_run_readiness_input(manifest)


def test_outer_reference_file_tampering_is_unavailable(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["A1"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    path = tmp_path / reference["path"]
    path.write_bytes(path.read_bytes() + b"\n")

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["A1"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_file_sha256_mismatch" in gate["reason_codes"]


def test_original_producer_file_tampering_is_unavailable(
    tmp_path: Path,
) -> None:
    manifest, artifacts = _partial_manifest(tmp_path)
    training = tmp_path / artifacts["training_seed_registry"]["path"]
    training.write_bytes(training.read_bytes() + b"\n")

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["A2"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_original_file_sha256_mismatch" in gate["reason_codes"]


def test_missing_original_producer_file_is_unavailable(tmp_path: Path) -> None:
    manifest, artifacts = _partial_manifest(tmp_path)
    original = tmp_path / artifacts["d5_active_vision_manifest"]["path"]
    original.unlink()

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["A3"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_original_file_missing" in gate["reason_codes"]


def test_original_producer_path_escape_is_unavailable(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["A1"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    path = tmp_path / reference["path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifacts"]["training_seed_registry"]["path"] = "../outside.json"
    _rehash_content(payload)
    _write_json(path, payload)
    reference["file_sha256"] = sha256(path.read_bytes()).hexdigest()
    manifest = _rebuild_manifest(manifest)

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["A1"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_original_path_escape_rejected" in gate["reason_codes"]


def test_declared_outer_digest_mismatch_is_unavailable(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["G1"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    reference["file_sha256"] = "0" * 64
    manifest = _rebuild_manifest(manifest)

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["G1"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_file_sha256_mismatch" in gate["reason_codes"]


def test_unknown_source_schema_is_unavailable(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["A3"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    path = tmp_path / reference["path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "unknown.formal.schema.v99"
    _rehash_content(payload)
    _write_json(path, payload)
    reference["file_sha256"] = sha256(path.read_bytes()).hexdigest()
    manifest = _rebuild_manifest(manifest)

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["A3"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_schema_unsupported" in gate["reason_codes"]


def test_missing_source_reference_file_is_unavailable(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["F1"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    (tmp_path / reference["path"]).unlink()

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["F1"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert "gate_source_file_missing" in gate["reason_codes"]


@pytest.mark.parametrize(
    ("path_value", "reason"),
    [
        ("../outside.json", "gate_source_path_escape_rejected"),
        ("/tmp/outside.json", "gate_source_path_escape_rejected"),
        (".", "gate_source_directory_rejected"),
    ],
)
def test_reference_path_escape_and_directory_are_rejected(
    tmp_path: Path,
    path_value: str,
    reason: str,
) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    reference = manifest["variants"]["F1"]["gates"]["frozen_unseen_seeds"][
        "source_artifact"
    ]
    reference["path"] = path_value
    manifest = _rebuild_manifest(manifest)

    gate = audit_learning_run_readiness(
        manifest,
        artifact_root=tmp_path,
    )["variants"]["F1"]["gates"]["frozen_unseen_seeds"]
    assert gate["availability"] is False
    assert reason in gate["reason_codes"]


def test_missing_artifact_root_keeps_all_variants_unready(
    tmp_path: Path,
) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    result = audit_learning_run_readiness(manifest, artifact_root=None)
    assert result["aggregate"]["formal_evidence_ready_variant_count"] == 0
    assert all(
        row["formal_evidence_readiness"]["ready"] is None
        for row in result["variants"].values()
    )


def test_low_disk_only_changes_storage_and_execution_layer(
    tmp_path: Path,
) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    high = audit_learning_run_readiness(manifest, artifact_root=tmp_path)
    manifest["storage"]["mounts"][0]["available_bytes"] = 14_139_191_296
    low = audit_learning_run_readiness(
        _rebuild_manifest(manifest),
        artifact_root=tmp_path,
    )

    assert low["storage"]["minimum_free_bytes"] == (
        FORMAL_RUNTIME_MINIMUM_FREE_BYTES
    )
    assert "formal_runtime_disk_below_20_gib_threshold" in low["storage"][
        "reason_codes"
    ]
    for variant in LEARNING_VARIANTS:
        assert (
            low["variants"][variant]["model_readiness"]
            == high["variants"][variant]["model_readiness"]
        )
        assert (
            low["variants"][variant]["formal_evidence_readiness"]
            == high["variants"][variant]["formal_evidence_readiness"]
        )


def test_output_loader_rejects_authority_escalation(tmp_path: Path) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    result = audit_learning_run_readiness(manifest, artifact_root=tmp_path)
    result["permissions"]["control_authority"] = True
    _rehash_content(result)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(
        LearningRunReadinessError,
        match="readiness_output_authority_escalation_attempt",
    ):
        load_learning_run_readiness_output(path)


def test_output_loader_rejects_rehashed_summary_tampering(
    tmp_path: Path,
) -> None:
    manifest, _ = _partial_manifest(tmp_path)
    result = audit_learning_run_readiness(manifest, artifact_root=tmp_path)
    summary = result["variants"]["G1"]["model_readiness"]
    summary["fail_closed"] = False
    _rehash_content(result)
    path = tmp_path / "bad-summary.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(
        LearningRunReadinessError,
        match="readiness_output_summary_semantics_mismatch",
    ):
        load_learning_run_readiness_output(path)


def test_cli_can_be_started_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = (
        repository_root
        / "research_modules"
        / "d6_evaluation_metrics"
        / "scripts"
        / "run_learning_run_readiness_audit.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "G1/A1/A2/A3/C1/F1" in completed.stdout
