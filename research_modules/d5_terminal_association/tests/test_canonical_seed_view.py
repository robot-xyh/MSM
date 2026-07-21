from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

import d5_terminal_association.canonical_seed_view as canonical_module
from d5_terminal_association.active_vision_bc_training import (
    _load_behavior_cloning_dataset,
)
from d5_terminal_association.active_vision_episode_dataset import (
    LazyActiveVisionEpisodeDataset,
)
from d5_terminal_association.canonical_seed_view import (
    CanonicalSeedViewError,
    load_active_vision_canonical_seed_view,
    load_tracklet_canonical_seed_view,
    write_active_vision_canonical_seed_view,
    write_tracklet_canonical_seed_view,
)
from d5_terminal_association.tracklet_dataset import (
    LoadedEvaluatorLabels,
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    LoadedTrackletGraph,
)
from d5_terminal_association.tracklet_training_audit import _load_audit_dataset


SPLITS = ("train", "validation", "test")


@pytest.fixture()
def canonical_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    tracklet_root = tmp_path / "source-tracklet"
    active_root = tmp_path / "source-active"
    tracklet = _tracklet_source(tracklet_root)
    active = _active_source(active_root)
    registries = _write_registries(tmp_path / "registries")
    current = {"tracklet": tracklet, "active": active}

    def tracklet_loader(_: str | Path) -> LoadedTrackletDataset:
        return current["tracklet"]

    def active_loader(_: str | Path) -> LazyActiveVisionEpisodeDataset:
        return current["active"]

    monkeypatch.setattr(canonical_module, "load_tracklet_dataset", tracklet_loader)
    monkeypatch.setattr(
        canonical_module,
        "load_active_vision_episode_dataset_lazy",
        active_loader,
    )
    return {
        "tracklet_root": tracklet_root,
        "active_root": active_root,
        "training_registry": registries[0],
        "shared_registry": registries[1],
        "current": current,
    }


@pytest.mark.parametrize("consumer", ["tracklet", "active"])
def test_canonical_view_is_seed_atomic_read_only_and_60_20_20(
    canonical_fixture: dict[str, Any],
    tmp_path: Path,
    consumer: str,
) -> None:
    source_root = canonical_fixture[f"{consumer}_root"]
    before = _tree_sha256(source_root)
    view_path = tmp_path / "detached" / f"{consumer}.view.json"
    common = {
        "training_seed_registry_path": canonical_fixture["training_registry"],
        "shared_seed_registry_path": canonical_fixture["shared_registry"],
        "view_manifest_path": view_path,
    }
    if consumer == "tracklet":
        view, payload, _ = write_tracklet_canonical_seed_view(source_root, **common)
        seeds_by_split = {
            split: {item.graph.seed for item in view.split(split)} for split in SPLITS
        }
    else:
        view, payload, _ = write_active_vision_canonical_seed_view(source_root, **common)
        seeds_by_split = {
            split: {int(item["seed"]) for item in view.split_descriptors(split)}
            for split in SPLITS
        }

    assert {split: len(values) for split, values in seeds_by_split.items()} == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert not (seeds_by_split["train"] & seeds_by_split["validation"])
    assert not (seeds_by_split["train"] & seeds_by_split["test"])
    assert not (seeds_by_split["validation"] & seeds_by_split["test"])
    assert not set(range(1000, 1020)) & set().union(*seeds_by_split.values())
    assert payload["view_contract"]["complete_episode_rebucket_only"]
    assert payload["canonical_split"]["reassigned_episode_count"] > 0
    assert _tree_sha256(source_root) == before


def test_existing_training_loaders_use_canonical_view_only_when_explicit(
    canonical_fixture: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracklet_view_path = tmp_path / "tracklet.view.json"
    active_view_path = tmp_path / "active.view.json"
    common = {
        "training_seed_registry_path": canonical_fixture["training_registry"],
        "shared_seed_registry_path": canonical_fixture["shared_registry"],
    }
    write_tracklet_canonical_seed_view(
        canonical_fixture["tracklet_root"],
        view_manifest_path=tracklet_view_path,
        **common,
    )
    write_active_vision_canonical_seed_view(
        canonical_fixture["active_root"],
        view_manifest_path=active_view_path,
        **common,
    )

    monkeypatch.setattr(
        "d5_terminal_association.tracklet_training_audit.load_tracklet_dataset",
        lambda _: canonical_fixture["current"]["tracklet"],
    )
    monkeypatch.setattr(
        "d5_terminal_association.active_vision_bc_training.load_active_vision_episode_dataset_lazy",
        lambda _: canonical_fixture["current"]["active"],
    )
    legacy_tracklet = _load_audit_dataset(
        canonical_fixture["tracklet_root"],
        canonical_view_manifest_path=None,
        training_seed_registry_path=None,
        shared_seed_registry_path=None,
    )
    canonical_tracklet = _load_audit_dataset(
        canonical_fixture["tracklet_root"],
        canonical_view_manifest_path=tracklet_view_path,
        training_seed_registry_path=canonical_fixture["training_registry"],
        shared_seed_registry_path=canonical_fixture["shared_registry"],
    )
    legacy_active = _load_behavior_cloning_dataset(
        canonical_fixture["active_root"],
        canonical_view_manifest_path=None,
        training_seed_registry_path=None,
        shared_seed_registry_path=None,
    )
    canonical_active = _load_behavior_cloning_dataset(
        canonical_fixture["active_root"],
        canonical_view_manifest_path=active_view_path,
        training_seed_registry_path=canonical_fixture["training_registry"],
        shared_seed_registry_path=canonical_fixture["shared_registry"],
    )

    assert {item.graph.seed for item in legacy_tracklet.split("train")} == set(range(60))
    assert {item.graph.seed for item in canonical_tracklet.split("train")} != set(range(60))
    assert {int(item["seed"]) for item in legacy_active.split_descriptors("train")} == set(
        range(60)
    )
    canonical_active_train = {
        int(item["seed"]) for item in canonical_active.split_descriptors("train")
    }
    assert canonical_active_train == set(
        json.loads(canonical_fixture["shared_registry"].read_text())["split_seed_values"][
            "train"
        ]
    )


@pytest.mark.parametrize("consumer", ["tracklet", "active"])
def test_view_binds_source_manifest_and_rejects_tamper(
    canonical_fixture: dict[str, Any],
    tmp_path: Path,
    consumer: str,
) -> None:
    view_path = tmp_path / f"{consumer}.view.json"
    common = {
        "training_seed_registry_path": canonical_fixture["training_registry"],
        "shared_seed_registry_path": canonical_fixture["shared_registry"],
        "view_manifest_path": view_path,
    }
    if consumer == "tracklet":
        write_tracklet_canonical_seed_view(canonical_fixture["tracklet_root"], **common)
    else:
        write_active_vision_canonical_seed_view(canonical_fixture["active_root"], **common)
    payload = json.loads(view_path.read_text(encoding="utf-8"))
    payload["source"]["manifest_sha256"] = "0" * 64
    _refresh_content_hash(payload)
    _write_json(view_path, payload)

    loader: Callable[..., Any] = (
        load_tracklet_canonical_seed_view
        if consumer == "tracklet"
        else load_active_vision_canonical_seed_view
    )
    with pytest.raises(CanonicalSeedViewError) as error:
        loader(canonical_fixture[f"{consumer}_root"], **common)
    assert error.value.code == "view_manifest_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("duplicate", "seed_catalog_not_canonical"),
        ("missing", "training_seed_count_mismatch"),
        ("reserved", "shared_assignment_seed_catalog_mismatch"),
        ("wrong_bucket", "shared_assignment_policy_reproduction_mismatch"),
        ("wrong_policy", "shared_registry_policy_mismatch"),
    ],
)
def test_registry_mutations_fail_closed(
    canonical_fixture: dict[str, Any],
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    training = json.loads(canonical_fixture["training_registry"].read_text())
    shared = json.loads(canonical_fixture["shared_registry"].read_text())
    training_path = canonical_fixture["training_registry"]
    if mutation == "duplicate":
        training["training_seeds"].append(99)
        training_path = tmp_path / "duplicate-training.json"
        _write_json(training_path, training)
    elif mutation == "missing":
        training["training_seeds"] = training["training_seeds"][:-1]
        training_path = tmp_path / "missing-training.json"
        _write_json(training_path, training)
    elif mutation == "reserved":
        shared["assignments"][-1]["seed"] = 1000
        _refresh_shared_registry(shared)
    elif mutation == "wrong_bucket":
        shared["assignments"][0]["split"] = "train"
        _refresh_shared_registry(shared)
    else:
        shared["policy_version"] = "unsupported-v9"
        _refresh_content_hash(shared)
    shared_path = tmp_path / f"{mutation}-shared.json"
    if mutation in {"duplicate", "missing"}:
        shared_path = canonical_fixture["shared_registry"]
    else:
        _write_json(shared_path, shared)

    with pytest.raises(CanonicalSeedViewError) as error:
        write_tracklet_canonical_seed_view(
            canonical_fixture["tracklet_root"],
            training_seed_registry_path=training_path,
            shared_seed_registry_path=shared_path,
            view_manifest_path=tmp_path / f"{mutation}.view.json",
        )
    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "dataset_seed_coverage_mismatch"),
        ("extra", "dataset_seed_coverage_mismatch"),
        ("reserved", "reserved_seed_in_dataset"),
        ("duplicate_episode", "source_episode_duplicate"),
    ],
)
def test_dataset_seed_and_episode_inventory_fail_closed(
    canonical_fixture: dict[str, Any],
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    source = canonical_fixture["current"]["active"]
    descriptors = [dict(item) for item in source.episode_descriptors]
    if mutation == "missing":
        descriptors = [item for item in descriptors if int(item["seed"]) != 99]
    elif mutation == "extra":
        descriptors[0]["seed"] = 999
    elif mutation == "reserved":
        descriptors[0]["seed"] = 1000
    else:
        descriptors.append(dict(descriptors[0]))
    canonical_fixture["current"]["active"] = replace(
        source,
        episode_descriptors=tuple(descriptors),
    )

    with pytest.raises(CanonicalSeedViewError) as error:
        write_active_vision_canonical_seed_view(
            canonical_fixture["active_root"],
            training_seed_registry_path=canonical_fixture["training_registry"],
            shared_seed_registry_path=canonical_fixture["shared_registry"],
            view_manifest_path=tmp_path / f"{mutation}.view.json",
        )
    assert error.value.code == expected_code


def test_canonical_arguments_must_be_complete(
    canonical_fixture: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="requires view manifest"):
        _load_audit_dataset(
            canonical_fixture["tracklet_root"],
            canonical_view_manifest_path="view.json",
            training_seed_registry_path=None,
            shared_seed_registry_path=None,
        )
    with pytest.raises(ValueError, match="requires view manifest"):
        _load_behavior_cloning_dataset(
            canonical_fixture["active_root"],
            canonical_view_manifest_path="view.json",
            training_seed_registry_path=None,
            shared_seed_registry_path=None,
        )


def _tracklet_source(root: Path) -> LoadedTrackletDataset:
    root.mkdir(parents=True)
    zero = "0" * 64
    descriptors: list[dict[str, Any]] = []
    episodes: list[LoadedTrackletEpisode] = []
    for seed in range(100):
        uid = f"tracklet-{seed:03d}"
        split = _legacy_split(seed)
        graph_sha = hashlib.sha256(f"graph:{seed}".encode()).hexdigest()
        labels_sha = hashlib.sha256(f"labels:{seed}".encode()).hexdigest()
        descriptors.append(
            {
                "schema_version": "d5.tracklet-episode.v1",
                "episode_uid": uid,
                "scenario_version": "fixture-5v5-v1",
                "seed": seed,
                "episode_id": f"episode-{seed}",
                "split": split,
                "graph_file": f"graphs/{uid}.npz",
                "graph_sha256": graph_sha,
                "labels_file": f"labels/{uid}.json",
                "labels_sha256": labels_sha,
                "config_sha256": zero,
                "node_count": 1,
                "edge_count": 0,
                "labels_complete": True,
                "candidate_recall_available": False,
                "class_balance": _zero_balance(),
                "hard_negative_provenance": {"source": "fixture"},
            }
        )
        graph = LoadedTrackletGraph(
            episode_uid=uid,
            scenario_version="fixture-5v5-v1",
            seed=seed,
            episode_id=f"episode-{seed}",
            node_features=np.zeros((1, 1), dtype=np.float32),
            edge_index=np.zeros((2, 0), dtype=np.int64),
            edge_features=np.zeros((0, 1), dtype=np.float32),
            tracklet_keys=(f"tracklet-{seed}",),
            camera_keys=("R0/C0",),
            measurement_timestamps=np.zeros(1),
            arrival_timestamps=np.zeros(1),
            gate_scores=np.zeros(0),
            candidate_counts={},
        )
        labels = LoadedEvaluatorLabels(
            episode_uid=uid,
            labels=(),
            labels_complete=True,
            candidate_recall_available=False,
        )
        episodes.append(
            LoadedTrackletEpisode(
                graph=graph,
                evaluator_labels=labels,
                split=split,
                graph_sha256=graph_sha,
                labels_sha256=labels_sha,
                class_balance=_zero_balance(),
                hard_negative_provenance={"source": "fixture"},
            )
        )
    manifest = {
        "schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "evaluator_label_schema_version": "d5.tracklet-evaluator-labels.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "config_sha256": zero,
        "split_sha256": "1" * 64,
        "training_set_sha256": "2" * 64,
        "hard_negative_provenance": [{"source": "fixture"}],
        "episodes": descriptors,
    }
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, manifest)
    return LoadedTrackletDataset(
        root=root,
        manifest=manifest,
        manifest_sha256=_sha256_file(manifest_path),
        episodes=tuple(episodes),
    )


def _active_source(root: Path) -> LazyActiveVisionEpisodeDataset:
    root.mkdir(parents=True)
    descriptors = []
    for seed in range(100):
        uid = f"active-{seed:03d}"
        descriptors.append(
            {
                "episode_uid": uid,
                "scenario_version": "fixture-5v5-v1",
                "seed": seed,
                "episode_id": f"episode-{seed}",
                "split": _legacy_split(seed),
                "sample_count": seed + 1,
                "online_sha256": hashlib.sha256(f"online:{seed}".encode()).hexdigest(),
                "offline_sha256": hashlib.sha256(f"offline:{seed}".encode()).hexdigest(),
            }
        )
    availability = {
        name: {"status": "unavailable", "available_sample_count": 0, "sample_count": 5050}
        for name in ("reward", "outcome", "counterfactual", "causal_label")
    }
    manifest = {
        "schema_version": "d5.active-vision-episode-dataset.v3",
        "episode_descriptor_schema_version": "d5.active-vision-episode-descriptor.v2",
        "episode_record_schema_version": "d5.active-vision-episode-record.v2",
        "sample_schema_version": "d5.active-vision-sample.v2",
        "snapshot_schema_version": "d5.active-vision-snapshot.v1",
        "action_schema_version": "d5.active-vision-action.v1",
        "camera_feedback_schema_version": "d5.active-vision-camera-feedback.v1",
        "runtime_ack_schema_version": "d5.active-vision-runtime-ack.v1",
        "offline_labels_schema_version": "d5.active-vision-offline-labels.v1",
        "offline_label_schema_version": "d5.active-vision-offline-label.v1",
        "split_sha256": "3" * 64,
        "training_set_sha256": "4" * 64,
        "availability": availability,
        "episodes": descriptors,
    }
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, manifest)
    return LazyActiveVisionEpisodeDataset(
        root=root,
        manifest=manifest,
        manifest_sha256=_sha256_file(manifest_path),
        episode_descriptors=tuple(descriptors),
    )


def _write_registries(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    training = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": "b" * 64,
        "training_seed_count": 100,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }
    training_path = root / "training.json"
    _write_json(training_path, training)
    assignment = canonical_module._canonical_assignment(tuple(range(100)))
    assignments = [
        {"seed": seed, "split": assignment[seed]} for seed in range(100)
    ]
    shared = {
        "schema_version": "scalable3d-shared-seed-split-registry-v1",
        "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
        "ordering_compatibility_version": "d3_numeric_seed_atomic_split_v2",
        "source": {
            "training_seed_registry_schema_version": "scalable3d-training-seed-registry-v1",
            "training_seed_registry_sha256": _sha256_file(training_path),
            "git_commit": training["git_commit"],
            "repository_dirty": False,
            "schedule_sha256": training["schedule_sha256"],
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "minimum_test_seed_count": 20,
        "training_seed_count": 100,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: sorted(seed for seed, name in assignment.items() if name == split)
            for split in SPLITS
        },
        "assignments": assignments,
        "assignment_sha256": canonical_module._sha256_json(assignments),
        "consumer_contract": canonical_module.EXPECTED_CONSUMER_CONTRACT,
    }
    _refresh_content_hash(shared)
    shared_path = root / "shared.json"
    _write_json(shared_path, shared)
    return training_path, shared_path


def _legacy_split(seed: int) -> str:
    return "train" if seed < 60 else "validation" if seed < 80 else "test"


def _zero_balance() -> dict[str, int]:
    return {
        "candidate_edges": 0,
        "positive_candidate_edges": 0,
        "negative_candidate_edges": 0,
        "unlabeled_candidate_edges": 0,
    }


def _refresh_shared_registry(value: dict[str, Any]) -> None:
    value["assignment_sha256"] = canonical_module._sha256_json(value["assignments"])
    value["split_seed_values"] = {
        split: sorted(
            int(item["seed"]) for item in value["assignments"] if item["split"] == split
        )
        for split in SPLITS
    }
    _refresh_content_hash(value)


def _refresh_content_hash(value: dict[str, Any]) -> None:
    value.pop("content_sha256", None)
    value["content_sha256"] = canonical_module._sha256_json(value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
