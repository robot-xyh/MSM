from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import d5_terminal_association.active_vision_curriculum_cli as curriculum_cli
import d5_terminal_association.active_vision_curriculum_dataset as curriculum_dataset
import d5_terminal_association.canonical_seed_view as canonical_module
from d5_terminal_association.active_vision_curriculum import (
    ActiveVisionCurriculumConfig,
    build_active_vision_curriculum_episode,
)
from d5_terminal_association.active_vision_curriculum_dataset import (
    ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT,
    ActiveVisionSupplementalCurriculumError,
    generate_active_vision_supplemental_curriculum,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionDatasetValidationError,
    ActiveVisionSourceIdentityV1,
    stage_active_vision_episode_record,
    stage_active_vision_offline_labels,
    unavailable_active_vision_offline_labels,
)
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
)


CREATED_AT = "2026-07-21T12:00:00Z"
SOURCE_COMMIT = "c" * 40
GLOBAL_TRACK_ID = "CENTER-TRACK-SUPPLEMENTAL"
SPLITS = ("train", "validation", "test")


@pytest.fixture()
def small_staged_curriculum(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "small-staged-curriculum"
    generation_config = {
        "fixture": "one-seed-contract-composition",
        "global_track_id": GLOBAL_TRACK_ID,
    }
    source = ActiveVisionSourceIdentityV1(
        git_commit=SOURCE_COMMIT,
        git_dirty=False,
        config_sha256=canonical_module._sha256_json(generation_config),
    )
    config = ActiveVisionCurriculumConfig(global_track_id=GLOBAL_TRACK_ID)
    record, summary = build_active_vision_curriculum_episode(
        7,
        source_identity=source,
        config=config,
    )
    descriptor = stage_active_vision_episode_record(
        root,
        record,
        generation_config=generation_config,
    )
    labels = unavailable_active_vision_offline_labels(record)
    finalized_descriptor = stage_active_vision_offline_labels(
        root,
        record.episode_uid,
        labels,
    )
    return {
        "root": root,
        "record": record,
        "summary": summary,
        "descriptor": descriptor,
        "finalized_descriptor": finalized_descriptor,
        "labels": labels,
    }


def test_small_fixture_composes_existing_staging_and_unavailable_label_contracts(
    small_staged_curriculum: dict[str, Any],
) -> None:
    fixture = small_staged_curriculum

    assert fixture["summary"].sample_count == 12
    assert fixture["descriptor"]["offline_file"] is None
    assert fixture["finalized_descriptor"]["offline_file"].endswith(
        ".offline.json"
    )
    assert len(fixture["labels"]) == 12
    assert all(not label.reward_available for label in fixture["labels"])
    assert all(not label.outcome_available for label in fixture["labels"])
    assert all(not label.counterfactual_available for label in fixture["labels"])
    assert all(not label.causal_label_available for label in fixture["labels"])
    assert (fixture["root"] / "online").is_dir()
    assert (fixture["root"] / "offline").is_dir()


def test_full_100_seed_curriculum_is_atomic_canonical_and_fail_closed(
    tmp_path: Path,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    output = tmp_path / "supplemental-curriculum"
    tracked_json = tmp_path / "tracked" / "summary.json"
    tracked_markdown = tmp_path / "tracked" / "report.md"
    registry_hashes_before = (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )

    result = generate_active_vision_supplemental_curriculum(
        output,
        training_seed_registry_path=training_registry,
        shared_seed_registry_path=shared_registry,
        created_at_utc=CREATED_AT,
        global_track_id=GLOBAL_TRACK_ID,
        source_git_commit=SOURCE_COMMIT,
        source_repository_dirty=False,
        tracked_summary_path=tracked_json,
        tracked_markdown_path=tracked_markdown,
    )
    summary = result.summary

    assert result.output_dir == output.resolve()
    assert summary["coverage"] == {
        "episode_count": 100,
        "segment_count": 800,
        "sample_count": 1200,
        "intent_counts": {
            "hold": 200,
            "observe_target": 600,
            "reacquire": 200,
            "search_sector": 200,
        },
        "fov_mode_counts": {"wide": 1000, "zoom": 200},
        "camera_role_counts": {"interceptor": 600, "recon": 600},
    }
    assert summary["ack_fault_coverage"]["counts"] == {
        "applied": 400,
        "rejected": 400,
        "missing": 400,
    }
    assert summary["ack_fault_coverage"]["runtime_distribution_evidence"] is False
    assert summary["ack_fault_coverage"]["reward_or_outcome_evidence"] is False
    assert summary["canonical"]["split"]["seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert summary["canonical"]["split"]["episode_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert summary["canonical"]["split"]["sample_counts"] == {
        "train": 720,
        "validation": 240,
        "test": 240,
    }
    assert summary["truth_seed_and_formal_isolation"] == {
        "truth_guard_passed_episode_count": 100,
        "online_truth_identifier_count": 0,
        "training_seed_count": 100,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "reserved_seed_overlap": [],
        "synthetic_episode_count": 100,
        "non_synthetic_episode_count": 0,
        "formal_900_episode_dataset_modified": False,
    }
    assert summary["version_and_identity_audit"]["global_track_id_values"] == [
        GLOBAL_TRACK_ID
    ]
    assert summary["version_and_identity_audit"][
        "global_track_id_created_or_rebound"
    ] is False
    assert summary["admission"] == {
        "clean_source": True,
        "dirty_episode_count": 0,
        "behavior_cloning_view_available": True,
        "behavior_cloning_development_eligible": True,
        "status": "development_shadow_only",
        "synthetic_curriculum_only": True,
        "ppo_available": False,
        "online_assist_available": False,
        "online_authority_available": False,
        "camera_command_authority_available": False,
        "rule_fallback_required": True,
    }
    assert summary["audit"]["passed"] is True
    assert not (output / "_staging").exists()
    assert registry_hashes_before == (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )
    assert summary["source_binding"]["training_seed_registry_sha256"] == (
        registry_hashes_before[0]
    )
    assert summary["source_binding"]["shared_seed_registry_sha256"] == (
        registry_hashes_before[1]
    )
    assert summary["dataset"]["manifest_sha256"] == summary["canonical"][
        "readiness"
    ]["source_manifest_sha256"]
    assert json.loads(tracked_json.read_text(encoding="utf-8")) == summary
    markdown = tracked_markdown.read_text(encoding="utf-8")
    assert markdown == (
        output / "curriculum_report.md"
    ).read_text(encoding="utf-8")
    assert markdown.startswith("# D5 主动视觉补充课程报告\n")
    assert "ACK 故障注入覆盖" in markdown
    assert "每个 seed 的 `4/4/4` 确定性故障注入覆盖" in markdown
    assert "不是实际运行分布" in markdown
    assert "不替代正式 900-episode 数据集" in markdown

    canonical_seed_sets = {
        split: {
            int(item["seed"])
            for item in result.canonical_dataset.split_descriptors(split)
        }
        for split in SPLITS
    }
    assert {name: len(values) for name, values in canonical_seed_sets.items()} == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert not set(range(1000, 1020)) & set().union(*canonical_seed_sets.values())
    first_episode = next(result.canonical_dataset.iter_episodes("train"))
    assert first_episode.record.synthetic_fixture is True
    assert all(
        not label.reward_available
        and not label.outcome_available
        and not label.counterfactual_available
        and not label.causal_label_available
        for label in first_episode.offline_labels
    )
    with pytest.raises(ActiveVisionDatasetValidationError) as error:
        next(result.canonical_dataset.iter_ppo_episodes("train"))
    assert error.value.code == "ppo_reward_unavailable"


def test_curriculum_rejects_existing_destination_without_touching_it(
    tmp_path: Path,
) -> None:
    output = tmp_path / "already-present"
    output.mkdir()
    marker = output / "marker.txt"
    marker.write_text("owned by caller\n", encoding="utf-8")

    with pytest.raises(
        ActiveVisionSupplementalCurriculumError,
        match="destination already exists",
    ):
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=tmp_path / "registries" / "missing-training.json",
            shared_seed_registry_path=tmp_path / "registries" / "missing-shared.json",
            created_at_utc=CREATED_AT,
            global_track_id=GLOBAL_TRACK_ID,
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
        )

    assert marker.read_text(encoding="utf-8") == "owned by caller\n"


def test_curriculum_rejects_output_equal_to_or_inside_formal_registry_source_root(
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-900-episode-input"
    training_registry, shared_registry = _write_registries(
        formal_root,
        shared_root=formal_root / "shared_seed_split_registry",
    )
    descendant_output = formal_root / "generated" / "supplemental-curriculum"
    registry_hashes_before = (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )

    for output in (formal_root, descendant_output):
        with pytest.raises(
            ActiveVisionSupplementalCurriculumError,
            match="output_dir must be outside registry source root",
        ):
            generate_active_vision_supplemental_curriculum(
                output,
                training_seed_registry_path=training_registry,
                shared_seed_registry_path=shared_registry,
                created_at_utc=CREATED_AT,
                global_track_id=GLOBAL_TRACK_ID,
                source_git_commit=SOURCE_COMMIT,
                source_repository_dirty=False,
            )

    assert not descendant_output.exists()
    assert not descendant_output.parent.exists()
    assert registry_hashes_before == (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )


@pytest.mark.parametrize(
    ("tracked_argument", "source_name", "filename"),
    [
        ("tracked_summary_path", "training", "summary.json"),
        ("tracked_markdown_path", "shared", "report.md"),
    ],
)
def test_curriculum_rejects_tracked_outputs_inside_each_registry_source_root(
    tmp_path: Path,
    tracked_argument: str,
    source_name: str,
    filename: str,
) -> None:
    training_root = tmp_path / "training-source"
    shared_root = tmp_path / "shared-source"
    training_registry, shared_registry = _write_registries(
        training_root,
        shared_root=shared_root,
    )
    source_root = training_root if source_name == "training" else shared_root
    tracked_path = source_root / "generated" / filename
    output = tmp_path / "published" / "supplemental-curriculum"
    registry_hashes_before = (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )

    with pytest.raises(ActiveVisionSupplementalCurriculumError) as error:
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=training_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc=CREATED_AT,
            global_track_id=GLOBAL_TRACK_ID,
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
            **{tracked_argument: tracked_path},
        )

    assert tracked_argument in str(error.value)
    assert "registry source root" in str(error.value)
    assert not output.exists()
    assert not output.parent.exists()
    assert not tracked_path.exists()
    assert not tracked_path.parent.exists()
    assert registry_hashes_before == (
        _sha256_file(training_registry),
        _sha256_file(shared_registry),
    )


def test_curriculum_cleans_sibling_temporary_directory_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    output = tmp_path / "must-not-publish"
    original = curriculum_dataset.build_active_vision_curriculum_episode
    calls = 0

    def fail_on_second_seed(*args: Any, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected staging failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        curriculum_dataset,
        "build_active_vision_curriculum_episode",
        fail_on_second_seed,
    )
    with pytest.raises(RuntimeError, match="injected staging failure"):
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=training_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc=CREATED_AT,
            global_track_id=GLOBAL_TRACK_ID,
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
        )

    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.tmp-*")) == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "reserved"])
def test_curriculum_rejects_training_registry_seed_leakage_and_count_changes(
    tmp_path: Path,
    mutation: str,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    training = _read_json(training_registry)
    if mutation == "missing":
        training["training_seeds"] = training["training_seeds"][:-1]
    elif mutation == "extra":
        training["training_seeds"].append(100)
    else:
        training["training_seeds"][-1] = 1000
        training["training_seeds"].sort()
        training["overlap_count"] = 1
    training["training_seed_count"] = len(training["training_seeds"])
    _write_json(training_registry, training)
    output = tmp_path / f"reject-{mutation}"

    with pytest.raises(ActiveVisionSupplementalCurriculumError):
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=training_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc=CREATED_AT,
            global_track_id=GLOBAL_TRACK_ID,
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
        )
    assert not output.exists()


def test_curriculum_rejects_shared_registry_binding_tamper_before_staging(
    tmp_path: Path,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    shared = _read_json(shared_registry)
    shared["source"]["training_seed_registry_sha256"] = "0" * 64
    _refresh_content_hash(shared)
    _write_json(shared_registry, shared)
    output = tmp_path / "reject-shared-tamper"

    with pytest.raises(
        ActiveVisionSupplementalCurriculumError,
        match="training file SHA256 binding mismatch",
    ):
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=training_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc=CREATED_AT,
            global_track_id=GLOBAL_TRACK_ID,
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
        )
    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.tmp-*")) == []


def test_curriculum_truth_guard_fails_closed_and_cleans_temporary_output(
    tmp_path: Path,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    output = tmp_path / "reject-truth-like-center-reference"

    with pytest.raises(ActiveVisionDatasetValidationError) as error:
        generate_active_vision_supplemental_curriculum(
            output,
            training_seed_registry_path=training_registry,
            shared_seed_registry_path=shared_registry,
            created_at_utc=CREATED_AT,
            global_track_id="actor-001",
            source_git_commit=SOURCE_COMMIT,
            source_repository_dirty=False,
        )
    assert error.value.code == "center_reference_identity_forbidden"
    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.tmp-*")) == []


def test_dirty_generation_is_not_clean_and_remains_fail_closed(
    tmp_path: Path,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    result = generate_active_vision_supplemental_curriculum(
        tmp_path / "dirty-curriculum",
        training_seed_registry_path=training_registry,
        shared_seed_registry_path=shared_registry,
        created_at_utc=CREATED_AT,
        global_track_id=GLOBAL_TRACK_ID,
        source_git_commit=SOURCE_COMMIT,
        source_repository_dirty=True,
    )

    assert result.summary["admission"]["clean_source"] is False
    assert result.summary["admission"]["dirty_episode_count"] == 100
    assert result.summary["admission"][
        "behavior_cloning_development_eligible"
    ] is False
    assert result.summary["admission"]["status"] == "fail_closed_dirty_source"
    assert result.summary["admission"]["ppo_available"] is False
    assert result.summary["admission"]["online_assist_available"] is False
    assert result.summary["admission"]["online_authority_available"] is False
    assert result.summary["audit"]["passed"] is True


def test_complete_curriculum_generation_is_content_deterministic(
    tmp_path: Path,
) -> None:
    training_registry, shared_registry = _write_registries(tmp_path / "registries")
    common = {
        "training_seed_registry_path": training_registry,
        "shared_seed_registry_path": shared_registry,
        "created_at_utc": CREATED_AT,
        "global_track_id": GLOBAL_TRACK_ID,
        "source_git_commit": SOURCE_COMMIT,
        "source_repository_dirty": False,
    }

    first = generate_active_vision_supplemental_curriculum(
        tmp_path / "deterministic-first",
        **common,
    )
    second = generate_active_vision_supplemental_curriculum(
        tmp_path / "deterministic-second",
        **common,
    )

    assert second.summary == first.summary
    assert second.dataset.manifest_sha256 == first.dataset.manifest_sha256
    assert second.canonical_dataset.manifest_sha256 == (
        first.canonical_dataset.manifest_sha256
    )
    assert (second.output_dir / "curriculum_report.md").read_bytes() == (
        first.output_dir / "curriculum_report.md"
    ).read_bytes()


def test_cli_requires_explicit_identity_and_uses_git_provenance_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}
    summary = {
        "dataset": {"manifest_sha256": "1" * 64},
        "canonical": {
            "view_manifest_sha256": "2" * 64,
            "split": {"seed_counts": {"train": 60, "validation": 20, "test": 20}},
        },
        "coverage": {"episode_count": 100, "sample_count": 1200},
        "admission": {
            "status": "development_shadow_only",
            "ppo_available": False,
            "online_assist_available": False,
            "online_authority_available": False,
        },
    }

    monkeypatch.setattr(curriculum_cli, "_git_provenance", lambda: ("d" * 40, True))

    def fake_generate(output_dir: Path, **kwargs: Any) -> SimpleNamespace:
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        return SimpleNamespace(output_dir=Path(output_dir), summary=summary)

    monkeypatch.setattr(
        curriculum_cli,
        "generate_active_vision_supplemental_curriculum",
        fake_generate,
    )
    output = tmp_path / "cli-output"
    assert (
        curriculum_cli.main(
            [
                "--output-dir",
                str(output),
                "--training-seed-registry",
                str(tmp_path / "training.json"),
                "--shared-seed-registry",
                str(tmp_path / "registry.json"),
                "--created-at-utc",
                CREATED_AT,
                "--global-track-id",
                GLOBAL_TRACK_ID,
                "--tracked-summary-json",
                str(tmp_path / "summary.json"),
                "--tracked-report-markdown",
                str(tmp_path / "report.md"),
            ]
        )
        == 0
    )

    assert captured["global_track_id"] == GLOBAL_TRACK_ID
    assert captured["source_git_commit"] == "d" * 40
    assert captured["source_repository_dirty"] is True
    assert captured["tracked_summary_path"] == tmp_path / "summary.json"
    assert captured["tracked_markdown_path"] == tmp_path / "report.md"
    printed = json.loads(capsys.readouterr().out)
    assert printed["episode_count"] == 100
    assert printed["canonical_seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }


def _write_registries(
    root: Path,
    *,
    shared_root: Path | None = None,
) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    training = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": "a" * 40,
        "repository_dirty": False,
        "schedule_sha256": sha256(b"d5-curriculum-test-schedule").hexdigest(),
        "training_seed_count": ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT,
        "training_seeds": list(range(100)),
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": list(range(1000, 1020)),
        "overlap_count": 0,
    }
    training_path = root / "training_seed_registry.json"
    _write_json(training_path, training)
    assignment = canonical_module._canonical_assignment(tuple(range(100)))
    assignments = [
        {"seed": seed, "split": assignment[seed]} for seed in range(100)
    ]
    shared = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": ORDERING_COMPATIBILITY_VERSION,
        "source": {
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
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
        "training_seed_count": len(training["training_seeds"]),
        "reserved_evaluation_seed_count": len(
            training["reserved_evaluation_seeds"]
        ),
        "reserved_evaluation_seeds": training["reserved_evaluation_seeds"],
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: sorted(
                seed for seed, assigned in assignment.items() if assigned == split
            )
            for split in SPLITS
        },
        "assignments": assignments,
        "assignment_sha256": canonical_module._sha256_json(assignments),
        "consumer_contract": dict(EXPECTED_CONSUMER_CONTRACT),
    }
    _refresh_content_hash(shared)
    resolved_shared_root = shared_root or root
    shared_path = resolved_shared_root / "registry.json"
    _write_json(shared_path, shared)
    return training_path, shared_path


def _refresh_content_hash(payload: dict[str, Any]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = canonical_module._sha256_json(payload)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
