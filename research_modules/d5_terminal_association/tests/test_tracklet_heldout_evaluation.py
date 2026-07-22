from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pytest
import torch

from d5_terminal_association.tracklet_gnn import NativeTrackletEdgeClassifier
from d5_terminal_association.tracklet_heldout_evaluation import (
    HELDOUT_EXPECTED_FRAME_COUNT,
    HELDOUT_FULL_PROFILE_VERSION,
    HELDOUT_MANIFEST_FILENAME,
    HELDOUT_RESERVED_SEEDS,
    HELDOUT_SMOKE_PROFILE_VERSION,
    HeldoutEvaluationPolicy,
    HeldoutGenerationConfig,
    TrackletHeldoutEvaluationError,
    evaluate_heldout_development_bundle,
    generate_tracklet_heldout_corpus,
    load_tracklet_heldout_corpus,
)
from d5_terminal_association.tracklet_model_bundle import (
    ModelBundleValidationError,
    write_tracklet_model_bundle,
)
from d5_terminal_association.tracklet_supplemental_curriculum import (
    FORMAL_SCENARIO_CELLS,
)


@pytest.fixture(scope="module")
def heldout_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("tracklet-heldout")
    formal = root / "formal"
    supplemental = root / "supplemental"
    formal.mkdir()
    supplemental.mkdir()
    _write_json(formal / "manifest.json", {"schema_version": "formal-test-source.v1"})
    _write_json(
        supplemental / "supplemental_manifest.json",
        {"schema_version": "supplemental-test-source.v1"},
    )
    corpus = root / "heldout"
    generate_tracklet_heldout_corpus(
        corpus,
        formal_dataset_dir=formal,
        supplemental_root=supplemental,
        created_at_utc="2026-07-21T12:00:00Z",
        source_git_commit="a" * 40,
        source_repository_dirty=True,
        config=HeldoutGenerationConfig(
            profile_version=HELDOUT_SMOKE_PROFILE_VERSION,
            seeds=(1000,),
            scenario_cells=(FORMAL_SCENARIO_CELLS[0], FORMAL_SCENARIO_CELLS[1]),
        ),
    )
    bundle = root / "development_bundle"
    _write_development_bundle(bundle)
    return {
        "root": root,
        "formal": formal,
        "supplemental": supplemental,
        "corpus": corpus,
        "bundle": bundle,
    }


def test_full_profile_is_exactly_twenty_seeds_by_forty_five_cells() -> None:
    profile = HeldoutGenerationConfig()

    assert profile.profile_version == HELDOUT_FULL_PROFILE_VERSION
    assert profile.seeds == tuple(range(1000, 1020))
    assert len(profile.scenario_cells) == 45
    assert HELDOUT_EXPECTED_FRAME_COUNT == 20 * 45 == 900
    assert profile.to_payload()["expected_frame_count"] == 900
    assert profile.to_payload()["training_split_registry_used"] is False


@pytest.mark.parametrize("seeds", [(0,), (99,), (7, 1000, 1001)])
def test_training_seed_cannot_enter_heldout_profile(seeds: tuple[int, ...]) -> None:
    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        HeldoutGenerationConfig(
            profile_version=HELDOUT_SMOKE_PROFILE_VERSION,
            seeds=seeds,
            scenario_cells=(FORMAL_SCENARIO_CELLS[0],),
        )
    assert error.value.code == "training_seed_leakage"


def test_full_profile_rejects_missing_or_extra_reserved_seed() -> None:
    with pytest.raises(TrackletHeldoutEvaluationError) as missing:
        HeldoutGenerationConfig(seeds=HELDOUT_RESERVED_SEEDS[:-1])
    assert missing.value.code == "heldout_seed_catalog_mismatch"

    with pytest.raises(TrackletHeldoutEvaluationError) as extra:
        HeldoutGenerationConfig(
            profile_version=HELDOUT_SMOKE_PROFILE_VERSION,
            seeds=HELDOUT_RESERVED_SEEDS + (1020,),
            scenario_cells=(FORMAL_SCENARIO_CELLS[0],),
        )
    assert extra.value.code == "training_seed_leakage"


def test_smoke_corpus_is_hash_bound_truth_isolated_and_heldout_only(
    heldout_fixture: dict[str, Path],
) -> None:
    corpus = load_tracklet_heldout_corpus(
        heldout_fixture["corpus"],
        require_full_profile=False,
    )

    assert len(corpus.episodes) == 2
    assert {episode.graph.seed for episode in corpus.episodes} == {1000}
    assert all(episode.evaluation_role == "held_out_evaluation" for episode in corpus.episodes)
    assert all(episode.class_balance["unlabeled_candidate_edges"] == 0 for episode in corpus.episodes)
    assert corpus.manifest["training_split_registry_used"] is False
    assert corpus.manifest["identity_and_truth_safety"]["global_track_id_created_or_rebound"] is False
    graph_path = heldout_fixture["corpus"] / "heldout_dataset" / corpus.manifest["episodes"][0]["graph_file"]
    with np.load(graph_path, allow_pickle=False) as archive:
        assert all("truth" not in name.lower() for name in archive.files)
        assert all("global" not in name.lower() for name in archive.files)


def test_missing_cell_fails_closed_even_if_manifest_content_hash_is_refreshed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copied = _copy_corpus(heldout_fixture["corpus"], tmp_path / "missing-cell")
    manifest_path = copied / HELDOUT_MANIFEST_FILENAME
    manifest = _read_json(manifest_path)
    manifest["episodes"].pop()
    _refresh_content_hash(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        load_tracklet_heldout_corpus(copied, require_full_profile=False)
    assert error.value.code == "heldout_episode_count_mismatch"


def test_graph_hash_tamper_fails_closed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copied = _copy_corpus(heldout_fixture["corpus"], tmp_path / "graph-tamper")
    graph = next((copied / "heldout_dataset" / "graphs").glob("*.graph.npz"))
    graph.write_bytes(graph.read_bytes() + b"tamper")

    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        load_tracklet_heldout_corpus(copied, require_full_profile=False)
    assert error.value.code in {
        "heldout_artifact_size_mismatch",
        "heldout_artifact_hash_mismatch",
    }


def test_lineage_hash_tamper_fails_closed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copied = _copy_corpus(heldout_fixture["corpus"], tmp_path / "lineage-tamper")
    lineage = copied / "evaluator" / "observation_lineage.json.gz"
    lineage.write_bytes(lineage.read_bytes() + b"tamper")

    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        load_tracklet_heldout_corpus(copied, require_full_profile=False)
    assert error.value.code in {
        "heldout_artifact_size_mismatch",
        "heldout_artifact_hash_mismatch",
    }


def test_same_camera_candidate_edge_fails_after_all_hashes_are_refreshed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copied = _copy_corpus(heldout_fixture["corpus"], tmp_path / "same-camera")
    manifest = _read_json(copied / HELDOUT_MANIFEST_FILENAME)
    descriptor = manifest["episodes"][0]
    graph_path = copied / "heldout_dataset" / descriptor["graph_file"]
    labels_path = copied / "heldout_dataset" / descriptor["labels_file"]
    arrays = _load_npz_arrays(graph_path)
    labels = _read_json(labels_path)
    truth = {item["tracklet_key"]: item["truth_entity_id"] for item in labels["labels"]}
    edge_index = arrays["edge_index"]
    tracklet_keys = [str(value) for value in arrays["tracklet_keys"].tolist()]
    cameras = [str(value) for value in arrays["camera_keys"].tolist()]
    negative_edge_number = next(
        index
        for index, (left, right) in enumerate(edge_index.T)
        if truth[tracklet_keys[int(left)]] != truth[tracklet_keys[int(right)]]
    )
    same_camera_pair = next(
        (left, right)
        for left in range(len(cameras))
        for right in range(left + 1, len(cameras))
        if cameras[left] == cameras[right]
        and truth[tracklet_keys[left]] != truth[tracklet_keys[right]]
    )
    edge_index[:, negative_edge_number] = np.asarray(same_camera_pair, dtype=np.int64)
    arrays["edge_index"] = edge_index
    _write_npz(graph_path, arrays)
    _refresh_episode_artifacts(copied, descriptor["episode_uid"])

    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        load_tracklet_heldout_corpus(copied, require_full_profile=False)
    assert error.value.code == "heldout_same_camera_candidate_edge"


def test_unlabeled_edge_fails_after_all_hashes_are_refreshed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    copied = _copy_corpus(heldout_fixture["corpus"], tmp_path / "missing-label")
    manifest = _read_json(copied / HELDOUT_MANIFEST_FILENAME)
    descriptor = manifest["episodes"][0]
    labels_path = copied / "heldout_dataset" / descriptor["labels_file"]
    labels = _read_json(labels_path)
    labels["labels"].pop()
    labels["labels_complete"] = False
    labels["candidate_recall_available"] = False
    _write_json(labels_path, labels)
    _refresh_episode_artifacts(copied, descriptor["episode_uid"])

    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        load_tracklet_heldout_corpus(copied, require_full_profile=False)
    assert error.value.code in {
        "heldout_artifact_validation_failed",
        "heldout_labels_incomplete",
        "heldout_class_balance_mismatch",
    }


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"temperature_override": 0.8}, "heldout_temperature_selection_forbidden"),
        ({"decision_threshold_override": 0.4}, "heldout_threshold_selection_forbidden"),
        ({"update_weights": True}, "heldout_weight_update_forbidden"),
    ],
)
def test_heldout_policy_rejects_calibration_threshold_or_weight_updates(
    kwargs: dict[str, Any], code: str
) -> None:
    with pytest.raises(TrackletHeldoutEvaluationError) as error:
        HeldoutEvaluationPolicy(**kwargs)
    assert error.value.code == code


def test_development_bundle_evaluation_keeps_all_authority_closed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    weights_before = _sha256_file(heldout_fixture["bundle"] / "weights.pt")
    manifest_before = _sha256_file(heldout_fixture["bundle"] / "manifest.json")
    report = evaluate_heldout_development_bundle(
        heldout_fixture["corpus"],
        heldout_fixture["bundle"],
        tmp_path / "evaluation",
        evaluated_at_utc="2026-07-21T12:10:00Z",
        policy=HeldoutEvaluationPolicy(latency_repeats=1),
        require_full_profile=False,
    )

    assert report["heldout_corpus"]["episode_count"] == 2
    assert report["frozen_decision"]["temperature_or_threshold_selection_performed"] is False
    assert report["frozen_decision"]["weight_update_performed"] is False
    assert report["layers"]["paired_shadow"] == {"status": "not_run", "passed": False}
    authority = report["layers"]["g1_assist_authority"]
    assert authority["g1_assist_eligible"] is False
    assert authority["assist_enabled"] is False
    assert authority["authority_enabled"] is False
    assert _sha256_file(heldout_fixture["bundle"] / "weights.pt") == weights_before
    assert _sha256_file(heldout_fixture["bundle"] / "manifest.json") == manifest_before


def test_bundle_weight_hash_tamper_fails_closed(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    bundle = tmp_path / "tampered-bundle"
    shutil.copytree(heldout_fixture["bundle"], bundle)
    (bundle / "weights.pt").write_bytes((bundle / "weights.pt").read_bytes() + b"tamper")
    with pytest.raises(ModelBundleValidationError) as error:
        evaluate_heldout_development_bundle(
            heldout_fixture["corpus"],
            bundle,
            tmp_path / "must-not-exist",
            evaluated_at_utc="2026-07-21T12:10:00Z",
            policy=HeldoutEvaluationPolicy(latency_repeats=1),
            require_full_profile=False,
        )
    assert error.value.code == "weights_sha_mismatch"
    assert not (tmp_path / "must-not-exist").exists()


def test_producer_and_evaluator_reject_output_overlap(
    heldout_fixture: dict[str, Path], tmp_path: Path
) -> None:
    with pytest.raises(TrackletHeldoutEvaluationError) as producer:
        generate_tracklet_heldout_corpus(
            heldout_fixture["formal"] / "nested-output",
            formal_dataset_dir=heldout_fixture["formal"],
            supplemental_root=heldout_fixture["supplemental"],
            created_at_utc="2026-07-21T12:00:00Z",
            source_git_commit="a" * 40,
            source_repository_dirty=True,
            config=HeldoutGenerationConfig(
                profile_version=HELDOUT_SMOKE_PROFILE_VERSION,
                seeds=(1000,),
                scenario_cells=(FORMAL_SCENARIO_CELLS[0],),
            ),
        )
    assert producer.value.code == "output_source_overlap"

    with pytest.raises(TrackletHeldoutEvaluationError) as evaluator:
        evaluate_heldout_development_bundle(
            heldout_fixture["corpus"],
            heldout_fixture["bundle"],
            heldout_fixture["corpus"] / "evaluation",
            evaluated_at_utc="2026-07-21T12:10:00Z",
            require_full_profile=False,
        )
    assert evaluator.value.code == "output_source_overlap"


def _write_development_bundle(root: Path) -> None:
    torch.manual_seed(7)
    write_tracklet_model_bundle(
        root,
        NativeTrackletEdgeClassifier(hidden_dim=8, message_passing_steps=1),
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_config_sha256="d" * 64,
        calibration_temperature=1.0,
        decision_threshold=0.6,
        validation_results={"f1": {"available": True, "value": 0.8}},
        admission_status="development_only_fail_closed",
        readiness_audit_sha256="e" * 64,
    )


def _copy_corpus(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _refresh_episode_artifacts(root: Path, episode_uid: str) -> None:
    manifest_path = root / HELDOUT_MANIFEST_FILENAME
    manifest = _read_json(manifest_path)
    descriptor = next(item for item in manifest["episodes"] if item["episode_uid"] == episode_uid)
    descriptor_path = root / "heldout_dataset" / "episodes" / f"{episode_uid}.episode.json"
    graph_path = root / "heldout_dataset" / descriptor["graph_file"]
    labels_path = root / "heldout_dataset" / descriptor["labels_file"]
    descriptor["graph_sha256"] = _sha256_file(graph_path)
    descriptor["labels_sha256"] = _sha256_file(labels_path)
    _write_json(descriptor_path, descriptor)
    for relative in (
        graph_path.relative_to(root).as_posix(),
        labels_path.relative_to(root).as_posix(),
        descriptor_path.relative_to(root).as_posix(),
    ):
        item = next(value for value in manifest["artifact_inventory"] if value["path"] == relative)
        path = root / relative
        item["sha256"] = _sha256_file(path)
        item["size_bytes"] = path.stat().st_size
    manifest["artifact_inventory_sha256"] = _sha256_json(
        {"artifacts": manifest["artifact_inventory"]}
    )
    _refresh_content_hash(manifest)
    _write_json(manifest_path, manifest)


def _load_npz_arrays(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: np.array(archive[key], copy=True) for key in archive.files}


def _write_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with path.open("wb") as handle:
        np.savez_compressed(handle, **arrays)


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


def _refresh_content_hash(value: dict[str, Any]) -> None:
    value.pop("content_sha256", None)
    value["content_sha256"] = _sha256_json(value)


def _sha256_json(value: Any) -> str:
    raw = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
