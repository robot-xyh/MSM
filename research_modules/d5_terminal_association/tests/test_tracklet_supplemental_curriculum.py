from __future__ import annotations

import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pytest

import d5_terminal_association.canonical_seed_view as canonical_module
import d5_terminal_association.tracklet_supplemental_admission as admission_module
import d5_terminal_association.tracklet_supplemental_curriculum as curriculum_module
from d5_terminal_association.canonical_seed_view import (
    EXPECTED_CONSUMER_CONTRACT,
    EXPECTED_MINIMUM_TEST_SEED_COUNT,
    EXPECTED_SPLIT_SEED,
    EXPECTED_TEST_FRACTION,
    EXPECTED_UNIT,
    EXPECTED_VALIDATION_FRACTION,
    ORDERING_COMPATIBILITY_VERSION,
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    CanonicalSeedViewError,
)
from d5_terminal_association.sparse_tracklet_graph import SparseTrackletGraphConfig
from d5_terminal_association.tracklet_dataset import (
    finalize_tracklet_dataset,
    join_offline_observation_labels,
    load_tracklet_dataset,
    stage_tracklet_dataset_episode,
)
from d5_terminal_association.tracklet_supplemental_admission import (
    TrackletCompositeAdmissionError,
    load_tracklet_composite_admission_view,
    write_tracklet_composite_admission_view,
)
from d5_terminal_association.tracklet_supplemental_curriculum import (
    SUPPLEMENTAL_SMOKE_PROFILE_VERSION,
    SupplementalGenerationConfig,
    TrackletSupplementalCurriculumError,
    generate_tracklet_supplemental_curriculum,
    load_tracklet_supplemental_curriculum,
)
from d5_terminal_association.tracklet_unlabeled_audit import (
    OFFLINE_LINEAGE_SCHEMA_VERSION,
    audit_formal_unlabeled_edges,
)


@pytest.fixture(scope="module")
def supplemental_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("tracklet-supplemental")
    training, shared = _write_registries(root / "registries")
    formal = root / "formal"
    _stage_source_dataset(formal, scenario="nominal", scale=5)
    supplemental = root / "supplemental"
    generate_tracklet_supplemental_curriculum(
        supplemental,
        formal_dataset_dir=formal,
        training_seed_registry_path=training,
        shared_seed_registry_path=shared,
        created_at_utc="2026-07-21T22:30:00Z",
        source_git_commit="a" * 40,
        source_repository_dirty=False,
        config=SupplementalGenerationConfig(
            profile_version=SUPPLEMENTAL_SMOKE_PROFILE_VERSION,
            scenario_cells=(("dense_crossing", 20),),
        ),
    )
    return {
        "root": root,
        "formal": formal,
        "supplemental": supplemental,
        "training": training,
        "shared": shared,
    }


def test_physical_curriculum_builds_dual_class_edges_without_online_truth() -> None:
    graph, offline, lineage, factors = curriculum_module._build_curriculum_frame(
        7,
        scenario="delayed_noisy",
        scale=200,
        frame_index=0,
        gate_config=SparseTrackletGraphConfig(),
    )
    joined = join_offline_observation_labels(graph, offline)
    positive, negative, unlabeled = curriculum_module._edge_balance(
        graph, joined.tracklet_labels
    )

    assert joined.labels_complete
    assert positive > 0 and negative > 0 and unlabeled == 0
    assert graph.edge_count == positive + negative
    assert graph.candidate_counts["time_gate_pass"] > 0
    assert graph.candidate_counts["epipolar_gate_pass"] > 0
    assert graph.candidate_counts["ray_gate_pass"] > 0
    assert graph.candidate_counts["reprojection_gate_pass"] > 0
    assert all(not edge.shared_global_track_ids for edge in graph.edges)
    assert all("truth" not in str(node.metadata).lower() for node in graph.nodes)
    assert all(record["evidence_kind"] == "offline_observation_truth_lineage" for record in lineage)
    assert factors["external_perturbation"] == 1
    assert factors["time_bias"] > 0


def test_default_final_degree_budget_preserves_difficult_four_camera_true_pairs() -> None:
    graph, offline, _, _ = curriculum_module._build_curriculum_frame(
        5,
        scenario="delayed_noisy",
        scale=200,
        frame_index=0,
        gate_config=SparseTrackletGraphConfig(),
    )
    joined = join_offline_observation_labels(graph, offline)
    truth_by_key = {
        label.tracklet_key: label.truth_entity_id for label in joined.tracklet_labels
    }
    possible_true_pairs: set[tuple[str, str]] = set()
    for source_index, source in enumerate(graph.nodes):
        for target in graph.nodes[source_index + 1 :]:
            if source.camera_key == target.camera_key:
                continue
            if truth_by_key[source.tracklet_key] == truth_by_key[target.tracklet_key]:
                possible_true_pairs.add(tuple(sorted((source.tracklet_key, target.tracklet_key))))
    retained_pairs = {
        tuple(sorted((edge.source_tracklet_key, edge.target_tracklet_key)))
        for edge in graph.edges
    }
    retained_true_pairs = possible_true_pairs.intersection(retained_pairs)
    candidate_recall = len(retained_true_pairs) / len(possible_true_pairs)
    degrees = np.bincount(graph.edge_index.reshape(-1), minlength=graph.node_count)

    assert joined.labels_complete
    assert graph.node_count == 15
    assert graph.candidate_counts["pre_cap_edges"] == 83
    assert graph.candidate_counts["retained_edges"] == 83
    assert len(possible_true_pairs) == 15
    assert candidate_recall >= 0.95
    assert graph.candidate_counts["rejected_final_degree_cap"] == 0
    assert graph.candidate_counts["pre_cap_edges"] == graph.candidate_counts["retained_edges"]
    assert graph.candidate_counts["geometry_gate_input_edges"] == (
        graph.candidate_counts["pre_cap_edges"]
        + graph.candidate_counts["rejected_geometry_gate_total"]
    )
    assert int(degrees.max()) <= SparseTrackletGraphConfig().max_neighbors_per_node
    assert int(degrees.max()) == 12
    assert graph.candidate_counts["retained_max_degree"] == int(degrees.max())
    assert all(
        graph.nodes[edge.source_index].camera_key
        != graph.nodes[edge.target_index].camera_key
        for edge in graph.edges
    )
    assert all(not edge.shared_global_track_ids for edge in graph.edges)
    assert all("truth" not in str(node.metadata).lower() for node in graph.nodes)


def test_candidate_gate_override_is_rejected() -> None:
    with pytest.raises(TrackletSupplementalCurriculumError) as error:
        curriculum_module._build_curriculum_frame(
            1,
            scenario="dense_crossing",
            scale=20,
            frame_index=0,
            gate_config=SparseTrackletGraphConfig(max_epipolar_error_px=9.0),
        )
    assert error.value.code == "candidate_gate_override_forbidden"


def test_formal_unlabeled_audit_only_accepts_exact_bound_lineage(tmp_path: Path) -> None:
    source = tmp_path / "formal-incomplete"
    graph, offline, _, _ = curriculum_module._build_curriculum_frame(
        1,
        scenario="dense_crossing",
        scale=20,
        frame_index=0,
        gate_config=SparseTrackletGraphConfig(),
    )
    for seed in (1, 2, 3):
        stage_tracklet_dataset_episode(
            source,
            graph,
            (),
            scenario_version="dense_crossing-20v20-v1",
            seed=seed,
            episode_id=f"incomplete-{seed}",
            generation_config={"source": "test-incomplete"},
            labels_complete=False,
            candidate_recall_available=False,
        )
    finalize_tracklet_dataset(source, split_seed=9)
    report = audit_formal_unlabeled_edges(source)
    assert report["summary"]["recoverable_edge_count"] == 0
    assert report["summary"]["unavailable_edge_count"] == 3 * graph.edge_count
    assert report["summary"]["nearest_neighbor_or_track_continuity_labels_used"] == 0

    dataset = load_tracklet_dataset(source)
    first = dataset.episodes[0]
    source_index = int(first.graph.edge_index[0, 0])
    target_index = int(first.graph.edge_index[1, 0])
    by_observation = {item.observation_id: item for item in offline}
    graph_nodes = {node.tracklet_key: node for node in graph.nodes}
    records = []
    for node_index in (source_index, target_index):
        key = first.graph.tracklet_keys[node_index]
        node = graph_nodes[key]
        item = by_observation[node.source_observation_id]
        records.append(
            {
                "episode_uid": first.graph.episode_uid,
                "tracklet_key": key,
                "measurement_timestamp": float(first.graph.measurement_timestamps[node_index]),
                "source_observation_id": item.observation_id,
                "truth_entity_id": item.truth_entity_id,
                "evidence_kind": "offline_observation_truth_lineage",
            }
        )
    lineage = tmp_path / "exact-lineage.json"
    _write_json(
        lineage,
        {
            "schema_version": OFFLINE_LINEAGE_SCHEMA_VERSION,
            "source_manifest_sha256": dataset.manifest_sha256,
            "records": records,
        },
    )
    with_lineage = audit_formal_unlabeled_edges(source, offline_lineage_path=lineage)
    assert with_lineage["summary"]["recoverable_edge_count"] == 1
    assert with_lineage["summary"]["formal_source_records_rewritten"] == 0


def test_smoke_producer_is_truth_isolated_hash_bound_and_not_admissible(
    supplemental_fixture: dict[str, Path],
) -> None:
    result = load_tracklet_supplemental_curriculum(
        supplemental_fixture["supplemental"], require_full_profile=False
    )
    assert result.summary["episode_count"] == 100
    assert result.summary["label_availability_ratio"] == 1.0
    assert result.summary["class_balance"]["negative_candidate_edges"] >= 100
    assert result.summary["class_balance"]["unlabeled_candidate_edges"] == 0
    assert result.summary["duplicate_violation_count"] == 0
    first_graph = result.dataset.root / result.dataset.manifest["episodes"][0]["graph_file"]
    with np.load(first_graph, allow_pickle=False) as archive:
        assert all("truth" not in name.lower() for name in archive.files)
        assert all("entity" not in name.lower() for name in archive.files)
    with pytest.raises(TrackletSupplementalCurriculumError) as error:
        load_tracklet_supplemental_curriculum(supplemental_fixture["supplemental"])
    assert error.value.code == "supplemental_profile_not_full"


def test_reserved_seed_registry_fails_before_generation(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    training = _read_json(supplemental_fixture["training"])
    training["training_seeds"][-1] = 1000
    training["training_seeds"].sort()
    training["overlap_count"] = 1
    broken_training = tmp_path / "training.json"
    _write_json(broken_training, training)
    with pytest.raises((TrackletSupplementalCurriculumError, canonical_module.CanonicalSeedViewError)):
        generate_tracklet_supplemental_curriculum(
            tmp_path / "must-not-exist",
            formal_dataset_dir=supplemental_fixture["formal"],
            training_seed_registry_path=broken_training,
            shared_seed_registry_path=supplemental_fixture["shared"],
            created_at_utc="2026-07-21T22:30:00Z",
            source_git_commit="a" * 40,
            source_repository_dirty=False,
            config=SupplementalGenerationConfig(
                profile_version=SUPPLEMENTAL_SMOKE_PROFILE_VERSION,
                scenario_cells=(("dense_crossing", 20),),
            ),
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_duplicate_graph_and_edge_material_is_detected(
    supplemental_fixture: dict[str, Path],
) -> None:
    dataset = load_tracklet_dataset(supplemental_fixture["formal"])
    audit = curriculum_module._duplicate_audit(dataset, dataset)
    assert audit["violation_count"] > 0
    assert audit["formal_episode_uid_overlap"]
    assert audit["formal_graph_content_fingerprint_overlap"]
    assert audit["formal_edge_content_fingerprint_overlap"]


def test_hash_tamper_fails_closed(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copy = tmp_path / "hash-tamper"
    shutil.copytree(supplemental_fixture["supplemental"], copy)
    manifest = _read_json(copy / "supplemental_manifest.json")
    graph_item = next(item for item in manifest["artifact_inventory"] if item["path"].endswith(".graph.npz"))
    graph_path = copy / graph_item["path"]
    graph_path.write_bytes(graph_path.read_bytes() + b"tamper")
    with pytest.raises(TrackletSupplementalCurriculumError) as error:
        load_tracklet_supplemental_curriculum(copy, require_full_profile=False)
    assert error.value.code in {
        "supplemental_artifact_size_mismatch",
        "supplemental_artifact_hash_mismatch",
    }


def test_candidate_gate_manifest_lowering_fails_even_with_refreshed_hash(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copy = tmp_path / "gate-lowering"
    shutil.copytree(supplemental_fixture["supplemental"], copy)
    manifest_path = copy / "supplemental_manifest.json"
    manifest = _read_json(manifest_path)
    manifest["candidate_gate"]["config"]["max_epipolar_error_px"] = 9.0
    _refresh_content_hash(manifest)
    _write_json(manifest_path, manifest)
    with pytest.raises(TrackletSupplementalCurriculumError) as error:
        load_tracklet_supplemental_curriculum(copy, require_full_profile=False)
    assert error.value.code == "candidate_gate_lowered_or_changed"


def test_missing_label_fails_closed(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copy = tmp_path / "missing-label"
    shutil.copytree(supplemental_fixture["supplemental"], copy)
    manifest = _read_json(copy / "supplemental_manifest.json")
    label_item = next(item for item in manifest["artifact_inventory"] if item["path"].endswith(".labels.json"))
    label_path = copy / label_item["path"]
    payload = _read_json(label_path)
    payload["labels"] = payload["labels"][:-1]
    payload["labels_complete"] = False
    payload["candidate_recall_available"] = False
    _write_json(label_path, payload)
    _refresh_inventory_item(manifest, copy, label_item["path"])
    _refresh_inventory_and_manifest(manifest)
    _write_json(copy / "supplemental_manifest.json", manifest)
    with pytest.raises(TrackletSupplementalCurriculumError):
        load_tracklet_supplemental_curriculum(copy, require_full_profile=False)


def test_negative_label_forgery_is_rejected_after_hash_refresh(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copy = tmp_path / "forged-negative"
    shutil.copytree(supplemental_fixture["supplemental"], copy)
    manifest = _read_json(copy / "supplemental_manifest.json")
    lineage_rel = manifest["evaluator_lineage"]["file"]
    lineage_path = copy / lineage_rel
    with gzip.open(lineage_path, "rt", encoding="utf-8") as stream:
        lineage = json.load(stream)
    lineage["records"][0]["truth_entity_id"] = "eval-forged"
    _write_gzip_json(lineage_path, lineage)
    manifest["evaluator_lineage"]["sha256"] = _sha256_file(lineage_path)
    _refresh_inventory_item(manifest, copy, lineage_rel)
    _refresh_inventory_and_manifest(manifest)
    _write_json(copy / "supplemental_manifest.json", manifest)
    with pytest.raises(TrackletSupplementalCurriculumError) as error:
        load_tracklet_supplemental_curriculum(copy, require_full_profile=False)
    assert error.value.code == "negative_edge_label_forgery"


def test_split_registry_tamper_is_rejected(
    supplemental_fixture: dict[str, Path], tmp_path: Path
) -> None:
    shared = _read_json(supplemental_fixture["shared"])
    shared["assignments"][0]["split"] = "train"
    shared["assignment_sha256"] = canonical_module._sha256_json(shared["assignments"])
    _refresh_content_hash(shared)
    broken = tmp_path / "shared.json"
    _write_json(broken, shared)
    with pytest.raises(CanonicalSeedViewError) as error:
        canonical_module.write_tracklet_canonical_seed_view(
            supplemental_fixture["formal"],
            training_seed_registry_path=supplemental_fixture["training"],
            shared_seed_registry_path=broken,
            view_manifest_path=tmp_path / "view.json",
        )
    assert error.value.code in {
        "shared_assignment_policy_reproduction_mismatch",
        "shared_split_seed_values_mismatch",
    }


def test_composite_view_rejects_formal_source_change(
    supplemental_fixture: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_loader = curriculum_module.load_tracklet_supplemental_curriculum

    def load_smoke(path: str | Path):
        return original_loader(path, require_full_profile=False)

    monkeypatch.setattr(admission_module, "load_tracklet_supplemental_curriculum", load_smoke)
    view = tmp_path / "detached" / "admission.json"
    write_tracklet_composite_admission_view(
        formal_dataset_dir=supplemental_fixture["formal"],
        supplemental_root=supplemental_fixture["supplemental"],
        training_seed_registry_path=supplemental_fixture["training"],
        shared_seed_registry_path=supplemental_fixture["shared"],
        view_manifest_path=view,
    )
    formal_copy = tmp_path / "changed-formal"
    shutil.copytree(supplemental_fixture["formal"], formal_copy)
    graph = next((formal_copy / "graphs").glob("*.graph.npz"))
    graph.write_bytes(graph.read_bytes() + b"changed")
    with pytest.raises((TrackletCompositeAdmissionError, ValueError)):
        load_tracklet_composite_admission_view(
            formal_dataset_dir=formal_copy,
            supplemental_root=supplemental_fixture["supplemental"],
            training_seed_registry_path=supplemental_fixture["training"],
            shared_seed_registry_path=supplemental_fixture["shared"],
            view_manifest_path=view,
        )


def _stage_source_dataset(root: Path, *, scenario: str, scale: int) -> None:
    for seed in range(100):
        graph, offline, _, _ = curriculum_module._build_curriculum_frame(
            seed,
            scenario=scenario,
            scale=scale,
            frame_index=0,
            gate_config=SparseTrackletGraphConfig(),
        )
        joined = join_offline_observation_labels(graph, offline)
        stage_tracklet_dataset_episode(
            root,
            graph,
            joined.tracklet_labels,
            scenario_version=f"{scenario}-{scale}v{scale}-v1",
            seed=seed,
            episode_id=f"formal-fixture-{seed:03d}",
            generation_config={"source": "test-formal-fixture-v1"},
            labels_complete=True,
            candidate_recall_available=True,
        )
    finalize_tracklet_dataset(root, split_seed=20260720)


def _write_registries(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    training = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": sha256(b"d5-tracklet-supplemental-test").hexdigest(),
        "training_seed_count": 100,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }
    training_path = root / "training.json"
    _write_json(training_path, training)
    assignment = canonical_module._canonical_assignment(tuple(range(100)))
    assignments = [{"seed": seed, "split": assignment[seed]} for seed in range(100)]
    shared = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": ORDERING_COMPATIBILITY_VERSION,
        "source": {
            "training_seed_registry_schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
            "training_seed_registry_sha256": _sha256_file(training_path),
            "git_commit": training["git_commit"],
            "repository_dirty": training["repository_dirty"],
            "schedule_sha256": training["schedule_sha256"],
        },
        "unit": EXPECTED_UNIT,
        "split_seed": EXPECTED_SPLIT_SEED,
        "validation_fraction": EXPECTED_VALIDATION_FRACTION,
        "test_fraction": EXPECTED_TEST_FRACTION,
        "minimum_test_seed_count": EXPECTED_MINIMUM_TEST_SEED_COUNT,
        "training_seed_count": 100,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: sorted(seed for seed, value in assignment.items() if value == split)
            for split in ("train", "validation", "test")
        },
        "assignments": assignments,
        "assignment_sha256": canonical_module._sha256_json(assignments),
        "consumer_contract": dict(EXPECTED_CONSUMER_CONTRACT),
    }
    _refresh_content_hash(shared)
    shared_path = root / "shared.json"
    _write_json(shared_path, shared)
    return training_path, shared_path


def _refresh_inventory_item(manifest: dict[str, Any], root: Path, relative: str) -> None:
    item = next(value for value in manifest["artifact_inventory"] if value["path"] == relative)
    path = root / relative
    item["size_bytes"] = path.stat().st_size
    item["sha256"] = _sha256_file(path)


def _refresh_inventory_and_manifest(manifest: dict[str, Any]) -> None:
    manifest["artifact_inventory_sha256"] = curriculum_module._sha256_json(
        {"artifacts": manifest["artifact_inventory"]}
    )
    _refresh_content_hash(manifest)


def _write_gzip_json(path: Path, value: dict[str, Any]) -> None:
    raw = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as stream:
        stream.write(raw)
    path.write_bytes(buffer.getvalue())


def _refresh_content_hash(value: dict[str, Any]) -> None:
    value.pop("content_sha256", None)
    value["content_sha256"] = canonical_module._sha256_json(value)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
