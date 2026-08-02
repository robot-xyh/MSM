from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from d5_terminal_association.active_vision_a3_v3_episode_evidence import (
    A3V3BoundaryPairEvidenceV1,
    A3V3EpisodeEvidenceError,
    A3V3HardConfusionBoundaryStateV1,
    A3V3OfflineEpisodeAuditV1,
    A3V3OfflineSampleAuditV1,
    A3V3OnlineEpisodeEvidenceV1,
    A3V3OnlineSampleEvidenceV1,
    a3_v3_assignment_reference_sha256,
    a3_v3_boundary_pair_id,
    a3_v3_sample_fingerprint,
    finalize_a3_v3_frozen_partition,
    load_a3_v3_development_online_evidence,
    load_frozen_a3_v3_episode_recipes,
    stage_a3_v3_episode_evidence,
    validate_a3_v3_episode_evidence,
    write_a3_v3_source_manifest,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _boundary_states(recipe, assignment, left_sample, right_sample):
    assignment_reference = a3_v3_assignment_reference_sha256(recipe)
    geometry_family = _sha(
        f"{recipe.episode_id}:{assignment.family}:observed-geometry-family"
    )
    communication_state = _sha(
        f"{recipe.episode_id}:{assignment.family}:communication-state"
    )

    def state(camera_role: str, **overrides):
        values = {
            "assignment_reference_sha256": assignment_reference,
            "geometry_family_sha256": geometry_family,
            "communication_state_sha256": communication_state,
            "camera_role": camera_role,
            "projection_available": True,
            "projection_inside_usable_boundary": True,
            "projection_fresh": True,
            "projection_stale_or_occluded": False,
            "recon_cue_available": True,
            "gimbal_busy": False,
            "slew_available": True,
            "matched_target_evidence_retained": True,
            "legal_target_count": 2,
            "projection_quality_gap": 0.02,
            "near_tie_maximum_gap": 0.05,
        }
        values.update(overrides)
        return A3V3HardConfusionBoundaryStateV1(**values)

    left = state(left_sample.camera_role)
    right_overrides = {}
    if assignment.family == "observe_vs_reacquire_projection_boundary":
        right_overrides = {
            "projection_inside_usable_boundary": False,
            "projection_fresh": False,
            "projection_stale_or_occluded": True,
        }
    elif assignment.family == "search_vs_reacquire_cue_loss_boundary":
        right_overrides = {"recon_cue_available": False}
    elif assignment.family == "hold_vs_observe_gimbal_busy_boundary":
        right_overrides = {"gimbal_busy": True, "slew_available": False}
    elif assignment.family == "role_matched_interceptor_recon_geometry":
        assert left_sample.camera_role != right_sample.camera_role
    elif assignment.family == "multiple_legal_targets_near_tie":
        pass
    else:  # pragma: no cover - frozen protocol guards this branch
        raise AssertionError(assignment.family)
    right = state(right_sample.camera_role, **right_overrides)
    return left, right


def _valid_episode(recipe):
    samples = []
    by_window = {}
    for window_index, window in enumerate(recipe.intent_windows):
        window_samples = []
        for sample_index in range(window.minimum_unique_samples):
            frame_index = window_index * 100 + sample_index
            camera_id = (
                "CAM-I-00" if window.camera_role == "interceptor" else "CAM-R-00"
            )
            resource_id = (
                "RES-I-00" if window.camera_role == "interceptor" else "RES-R-00"
            )
            candidate_fingerprint = _sha(
                f"{recipe.episode_id}:{window.window_id}:{sample_index}:candidate"
            )
            sample_fingerprint = a3_v3_sample_fingerprint(
                recipe,
                frame_index=frame_index,
                camera_id=camera_id,
                candidate_feature_fingerprint=candidate_fingerprint,
            )
            relative_timestamp = window.start_s + (
                (sample_index + 0.5)
                * (window.end_s - window.start_s)
                / window.minimum_unique_samples
            )
            sample = A3V3OnlineSampleEvidenceV1(
                sample_fingerprint=sample_fingerprint,
                candidate_feature_fingerprint=candidate_fingerprint,
                frame_index=frame_index,
                relative_timestamp_s=relative_timestamp,
                measurement_timestamp=100.0 + relative_timestamp,
                arrival_timestamp=100.05 + relative_timestamp,
                camera_id=camera_id,
                resource_id=resource_id,
                camera_role=window.camera_role,
                window_id=window.window_id,
                intent=window.intent,
                treatment_recipe=window.treatment_recipe,
                required_control_states={
                    name: True for name in window.required_controls
                },
                global_track_id="G-001",
            )
            samples.append(sample)
            window_samples.append(sample)
        by_window[window.window_id] = window_samples

    sample_audits = []
    for index, sample in enumerate(samples):
        sample_audits.append(
            A3V3OfflineSampleAuditV1(
                sample_fingerprint=sample.sample_fingerprint,
                treatment_achieved=True,
                evaluation_available=index == 0,
                evaluation=(
                    {
                        "truth_id": "offline-TGT-1",
                        "actor_id": "Actor-1",
                        "assessment": "confirmed",
                    }
                    if index == 0
                    else None
                ),
            )
        )

    boundary_pairs = []
    for assignment in recipe.hard_confusion_assignments:
        left = by_window[assignment.window_ids[0]][0]
        right = by_window[assignment.window_ids[1]][0]
        left_state, right_state = _boundary_states(
            recipe,
            assignment,
            left,
            right,
        )
        boundary_pairs.append(
            A3V3BoundaryPairEvidenceV1(
                boundary_pair_id=a3_v3_boundary_pair_id(
                    recipe,
                    family=assignment.family,
                    left_sample_fingerprint=left.sample_fingerprint,
                    right_sample_fingerprint=right.sample_fingerprint,
                ),
                family=assignment.family,
                treatment_recipe=assignment.treatment_recipe,
                left_sample_fingerprint=left.sample_fingerprint,
                right_sample_fingerprint=right.sample_fingerprint,
                left_state=left_state,
                right_state=right_state,
                required_control_states={
                    name: True for name in assignment.required_controls
                },
                achieved=True,
            )
        )

    online = A3V3OnlineEpisodeEvidenceV1(
        recipe=recipe,
        center_global_track_ids=("G-001",),
        samples=tuple(samples),
    )
    offline = A3V3OfflineEpisodeAuditV1(
        episode_id=recipe.episode_id,
        split=recipe.split,
        allocation_id=recipe.allocation_id,
        sample_audits=tuple(sample_audits),
        boundary_pairs=tuple(boundary_pairs),
    )
    return online, offline


@pytest.fixture(scope="module")
def recipes():
    values = load_frozen_a3_v3_episode_recipes()
    assert len(values) == 104
    return values


def test_legal_minimum_episode_binds_recipe_and_detaches_truth(recipes) -> None:
    online, offline = _valid_episode(recipes[0])

    summary = validate_a3_v3_episode_evidence(online, offline)

    assert summary["unique_qualifying_sample_count"] == 96
    assert summary["coverage"]["by_window"] == {
        window.window_id: 24 for window in recipes[0].intent_windows
    }
    assert all(value == 24 for value in summary["coverage"]["by_intent"].values())
    assert all(
        window.end_s - window.start_s == 1.5
        for window in recipes[0].intent_windows
    )
    assert summary["identity"] == {
        "global_track_id_ownership": "center_read_only",
        "global_track_id_created_count": 0,
        "global_track_id_rewritten_count": 0,
        "online_truth_identity_use_count": 0,
    }
    assert all(
        "evaluation" not in sample
        for sample in online.to_dict()["samples"]
    )
    assert offline.sample_audits[0].evaluation["actor_id"] == "Actor-1"


def test_duplicate_sample_fingerprint_fails_closed(recipes) -> None:
    online, _ = _valid_episode(recipes[0])

    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="online_episode_sample_fingerprint_duplicate",
    ):
        replace(online, samples=(*online.samples, online.samples[0]))


def test_online_truth_leak_fails_before_episode_write(recipes) -> None:
    online, _ = _valid_episode(recipes[0])
    payload = online.samples[0].to_dict()
    payload["camera_id"] = "Actor-1"

    with pytest.raises(ValueError, match="forbidden truth/actor/object identity"):
        A3V3OnlineSampleEvidenceV1.from_dict(payload)

    payload = online.samples[0].to_dict()
    payload["actor_id"] = "Actor-1"
    with pytest.raises(A3V3EpisodeEvidenceError, match="online_sample_fields_mismatch"):
        A3V3OnlineSampleEvidenceV1.from_dict(payload)


def test_missing_window_quota_and_boundary_pair_fail_closed(recipes) -> None:
    online, offline = _valid_episode(recipes[0])
    removed = online.samples[-1].sample_fingerprint
    short_online = replace(online, samples=online.samples[:-1])
    short_offline = replace(
        offline,
        sample_audits=tuple(
            item for item in offline.sample_audits if item.sample_fingerprint != removed
        ),
    )

    with pytest.raises(A3V3EpisodeEvidenceError, match="intent_window_unique_sample"):
        validate_a3_v3_episode_evidence(short_online, short_offline)

    with pytest.raises(A3V3EpisodeEvidenceError, match="boundary_pair_quota_missing"):
        validate_a3_v3_episode_evidence(
            online,
            replace(offline, boundary_pairs=offline.boundary_pairs[:-1]),
        )


def test_role_or_window_mismatch_fails_closed(recipes) -> None:
    online, _ = _valid_episode(recipes[0])
    sample = online.samples[0]

    with pytest.raises(A3V3EpisodeEvidenceError, match="window_role_or_treatment"):
        replace(
            online,
            samples=(replace(sample, camera_role="recon"), *online.samples[1:]),
        )


def test_hard_confusion_labels_are_derived_from_observed_state(recipes) -> None:
    families = {
        assignment.family
        for recipe in recipes
        for assignment in recipe.hard_confusion_assignments
    }
    checked = set()
    for family in families:
        recipe = next(
            item
            for item in recipes
            if family
            in {assignment.family for assignment in item.hard_confusion_assignments}
        )
        _, offline = _valid_episode(recipe)
        pair = next(item for item in offline.boundary_pairs if item.family == family)
        invalid_right = pair.left_state
        if family == "multiple_legal_targets_near_tie":
            invalid_right = replace(pair.right_state, legal_target_count=1)
        with pytest.raises(
            A3V3EpisodeEvidenceError,
            match="boundary_pair_achieved_not_derived_from_state",
        ):
            replace(pair, right_state=invalid_right)
        checked.add(family)
    assert checked == families


def test_boundary_state_role_and_allocation_bind_to_online_sample(recipes) -> None:
    recipe = next(
        item
        for item in recipes
        if "observe_vs_reacquire_projection_boundary"
        in {assignment.family for assignment in item.hard_confusion_assignments}
    )
    online, offline = _valid_episode(recipe)
    pair = next(
        item
        for item in offline.boundary_pairs
        if item.family == "observe_vs_reacquire_projection_boundary"
    )
    wrong_role = "recon" if pair.left_state.camera_role == "interceptor" else "interceptor"
    mismatched_role_pair = replace(
        pair,
        left_state=replace(pair.left_state, camera_role=wrong_role),
    )
    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="boundary_pair_state_camera_role_mismatch",
    ):
        validate_a3_v3_episode_evidence(
            online,
            replace(
                offline,
                boundary_pairs=tuple(
                    mismatched_role_pair if item is pair else item
                    for item in offline.boundary_pairs
                ),
            ),
        )

    wrong_allocation_pair = replace(
        pair,
        left_state=replace(
            pair.left_state,
            assignment_reference_sha256=_sha("wrong-allocation"),
        ),
        right_state=replace(
            pair.right_state,
            assignment_reference_sha256=_sha("wrong-allocation"),
        ),
    )
    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="boundary_pair_allocation_reference_mismatch",
    ):
        validate_a3_v3_episode_evidence(
            online,
            replace(
                offline,
                boundary_pairs=tuple(
                    wrong_allocation_pair if item is pair else item
                    for item in offline.boundary_pairs
                ),
            ),
        )


def test_frozen_split_staging_and_future_isolation(
    tmp_path: Path,
    recipes,
) -> None:
    development_dir = tmp_path / "development"
    future_dir = tmp_path / "future_held_out"
    train_online, train_offline = _valid_episode(recipes[0])
    future_recipe = next(item for item in recipes if item.split == "future_held_out")
    future_online, future_offline = _valid_episode(future_recipe)

    train_descriptor = stage_a3_v3_episode_evidence(
        development_dir=development_dir,
        future_held_out_dir=future_dir,
        online=train_online,
        offline=train_offline,
    )
    future_descriptor = stage_a3_v3_episode_evidence(
        development_dir=development_dir,
        future_held_out_dir=future_dir,
        online=future_online,
        offline=future_offline,
    )

    assert train_descriptor["partition"] == "development"
    assert future_descriptor["partition"] == "future_held_out"
    assert (development_dir / train_descriptor["online_file"]).is_file()
    assert (future_dir / future_descriptor["online_file"]).is_file()
    development_manifest = finalize_a3_v3_frozen_partition(
        development_dir,
        partition="development",
        expected_recipes=(recipes[0],),
    )
    future_manifest = finalize_a3_v3_frozen_partition(
        future_dir,
        partition="future_held_out",
        expected_recipes=(future_recipe,),
    )
    assert development_manifest["split_catalogs"] == {"train": [24000], "validation": []}
    assert future_manifest["split_catalogs"] == {
        "future_held_out": [future_recipe.seed]
    }
    assert development_manifest["schedule_complete"] is False
    assert future_manifest["schedule_complete"] is False
    assert development_manifest["usage_contract"]["training_splits"] == ["train"]
    assert development_manifest["usage_contract"]["threshold_selection_splits"] == [
        "validation"
    ]
    assert future_manifest["usage_contract"] == {
        "training_splits": [],
        "model_fitting_splits": [],
        "model_selection_splits": [],
        "calibration_splits": [],
        "threshold_selection_splits": [],
        "evaluation_splits": ["future_held_out"],
        "future_held_out_training_allowed": False,
        "future_held_out_model_fitting_allowed": False,
        "future_held_out_model_selection_allowed": False,
        "future_held_out_calibration_allowed": False,
        "future_held_out_threshold_selection_allowed": False,
        "future_held_out_access_mode": (
            "one_shot_after_validation_pass_and_model_freeze"
        ),
        "future_held_out_maximum_access_count": 1,
    }
    assert len(load_a3_v3_development_online_evidence(development_dir)) == 1
    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="development_loader_future_held_out_forbidden",
    ):
        load_a3_v3_development_online_evidence(future_dir)

    output = tmp_path / "source_manifest.json"
    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="source_manifest_partition_schedule_incomplete",
    ):
        write_a3_v3_source_manifest(
            output,
            development_manifest_path=development_dir / "manifest.json",
            future_held_out_manifest_path=future_dir / "manifest.json",
        )
    assert not output.exists()


def test_global_track_id_is_center_read_only(recipes) -> None:
    online, _ = _valid_episode(recipes[0])

    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="identity_authority_violation",
    ):
        replace(online, global_track_id_created_count=1)

    with pytest.raises(
        A3V3EpisodeEvidenceError,
        match="unknown_center_global_track_id",
    ):
        replace(online, center_global_track_ids=())

    with pytest.raises(ValueError, match="forbidden truth/actor/object identity"):
        replace(online, center_global_track_ids=("Actor-1",))
