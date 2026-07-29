from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from d5_terminal_association.active_vision_bundle import (
    ActiveVisionBundleValidationError,
    _load_active_vision_model_bundle_fixture,
    active_vision_model_fingerprint,
    load_active_vision_model_bundle,
    load_active_vision_model_bundle_for_runtime,
    write_active_vision_model_bundle,
)
from d5_terminal_association.active_vision_bc_training import (
    ActiveVisionBcConfig,
    build_behavior_cloning_feature_cache,
    evaluate_behavior_cloning_model,
    load_behavior_cloning_feature_cache,
    train_cached_behavior_cloning,
)
from d5_terminal_association.active_vision_cli import build_parser
from d5_terminal_association.active_vision_contracts import (
    ACTIVE_VISION_ACTION_SCHEMA_VERSION,
    ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION,
    ActiveVisionActionV1,
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionControllerV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionPolicyProposal,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    DeterministicLookAtScanPolicy,
    FriendlyObservationReservation,
    assert_truth_free_active_vision_payload,
    enumerate_safe_action_candidates,
    validate_active_vision_action_v1,
)
from d5_terminal_association.active_vision_corpus_audit import (
    ActiveVisionCorpusCoverageError,
)
from d5_terminal_association.active_vision_evaluation import (
    PairedShadowEpisodeResult,
    admission_report_from_manifest,
    evaluate_paired_shadow_admission,
)
from d5_terminal_association.active_vision_learning import (
    ActiveVisionActorCritic,
    ActiveVisionResearchEpisode,
    ActiveVisionTransition,
    BehaviorCloningConfig,
    ClippedPpoConfig,
    active_vision_candidate_batch,
    fit_active_vision_feature_bounds,
    split_active_vision_episode_groups,
    train_behavior_cloning,
    train_clipped_ppo,
)


NOW = 10.0


def _snapshot(
    *,
    camera_count: int = 2,
    track_ids: tuple[str, ...] = ("GT-001", "GT-002"),
    assignments_by_camera: dict[int, tuple[str, ...]] | None = None,
    plan_version: int = 4,
    coalition_version: int = 7,
    communication_version: int = 9,
    now: float = NOW,
    yaw_by_camera: dict[int, float] | None = None,
    supported_modes_by_camera: dict[int, tuple[ActiveVisionFovMode, ...]] | None = None,
    projection_timestamp: float | None = None,
    reservations: tuple[FriendlyObservationReservation, ...] = (),
) -> ActiveVisionSnapshotV1:
    assignments_by_camera = assignments_by_camera or {
        index: (track_ids[index % len(track_ids)],) for index in range(camera_count)
    }
    yaw_by_camera = yaw_by_camera or {}
    supported_modes_by_camera = supported_modes_by_camera or {}
    cameras = tuple(
        ActiveVisionCameraState(
            camera_id=f"CAM-{index}",
            resource_id=f"INT-{index}",
            state_timestamp=now,
            yaw_deg=yaw_by_camera.get(index, 0.0),
            pitch_deg=0.0,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-30.0, 30.0),
            pitch_limits_deg=(-20.0, 20.0),
            max_yaw_rate_deg_s=40.0,
            max_pitch_rate_deg_s=40.0,
            max_slew_deg_s=50.0,
            current_fov_mode=ActiveVisionFovMode.WIDE,
            supported_fov_modes=supported_modes_by_camera.get(
                index,
                (ActiveVisionFovMode.WIDE, ActiveVisionFovMode.ZOOM),
            ),
        )
        for index in range(camera_count)
    )
    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=f"INT-{camera_index}",
            camera_id=f"CAM-{camera_index}",
            global_track_id=track_id,
        )
        for camera_index, camera_targets in sorted(assignments_by_camera.items())
        for track_id in camera_targets
    )
    tracks = tuple(
        ActiveVisionTrackReference(
            global_track_id=track_id,
            track_version=3,
            measurement_timestamp=now - 0.05,
        )
        for track_id in track_ids
    )
    projections = tuple(
        ActiveVisionProjectionEvidence(
            camera_id=f"CAM-{camera_index}",
            global_track_id=track_id,
            measurement_timestamp=(
                now - 0.05 if projection_timestamp is None else projection_timestamp
            ),
            arrival_timestamp=(
                now - 0.02 if projection_timestamp is None else projection_timestamp + 0.01
            ),
            yaw_error_deg=5.0 + camera_index,
            pitch_error_deg=-2.0,
            projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
            visibility_probability=0.9,
            occlusion_fraction=0.1,
            association_confidence=0.95,
            in_fov=True,
        )
        for camera_index, camera_targets in sorted(assignments_by_camera.items())
        for track_id in camera_targets
        if track_id in track_ids
    )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=now,
        plan=ActiveVisionPlanReference(
            plan_version=plan_version,
            coalition_version=coalition_version,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=communication_version,
            plan_version=plan_version,
            coalition_version=coalition_version,
            update_timestamp=now - 0.05,
            healthy=True,
            peer_reservations=reservations,
        ),
        tracks=tracks,
        cameras=cameras,
        projections=projections,
    )


def _rule_action(snapshot: ActiveVisionSnapshotV1, camera_id: str = "CAM-0") -> ActiveVisionActionV1:
    return DeterministicLookAtScanPolicy().select_action(
        snapshot,
        camera_id=camera_id,
        current_timestamp=snapshot.snapshot_timestamp,
        expected_plan_version=snapshot.plan.plan_version,
        expected_coalition_version=snapshot.plan.coalition_version,
        expected_communication_version=snapshot.communication.communication_version,
    )


class _StubPolicy:
    available = True
    failure_reason = None

    def __init__(
        self,
        proposal: object,
        *,
        admitted: bool = True,
        fingerprint: str = "sha256:" + "1" * 64,
    ) -> None:
        self._proposal = proposal
        self.assist_admitted = admitted
        self.model_fingerprint = fingerprint

    def propose(self, *_: object, **__: object) -> object:
        return self._proposal


@pytest.mark.parametrize("camera_count", [1, 3, 6])
def test_rule_policy_scales_with_camera_count_and_assignment_subsets(camera_count: int) -> None:
    snapshot = _snapshot(
        camera_count=camera_count,
        track_ids=("GT-A", "GT-B", "GT-C"),
        assignments_by_camera={
            index: (() if index == camera_count - 1 else (f"GT-{'ABC'[index % 3]}",))
            for index in range(camera_count)
        },
    )

    for index in range(camera_count):
        action = _rule_action(snapshot, f"CAM-{index}")
        assigned = snapshot.assigned_target_ids(f"CAM-{index}")
        if assigned:
            assert action.target_global_track_id in assigned
            assert action.intent is ActiveVisionIntent.OBSERVE_TARGET
        else:
            assert action.target_global_track_id is None
            assert action.intent in {ActiveVisionIntent.SEARCH_SECTOR, ActiveVisionIntent.HOLD}


def test_snapshot_and_action_contracts_are_versioned_and_have_no_control_or_assignment_output() -> None:
    snapshot = _snapshot()
    action = _rule_action(snapshot)
    action_fields = {item.name for item in fields(ActiveVisionActionV1)}

    assert snapshot.schema_version == ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION
    assert action.schema_version == ACTIVE_VISION_ACTION_SCHEMA_VERSION
    assert not action_fields.intersection(
        {"velocity", "acceleration", "flight_control", "assignment", "weapon", "throttle"}
    )


def test_truth_keys_are_rejected_from_active_vision_input() -> None:
    for payload in (
        {"truth_entity_id": "entity-1"},
        {"nested": {"actor_id": "actor-1"}},
        {"opaque_alias": "TargetDrone_1"},
        SimpleNamespace(metadata={"object_name": "object-1"}),
    ):
        with pytest.raises(ValueError, match="truth/actor/object"):
            assert_truth_free_active_vision_payload(payload)


def test_global_track_ids_are_read_only_candidates_and_never_rewritten() -> None:
    snapshot = _snapshot(track_ids=("CENTER-11", "CENTER-12"))
    ids_before = tuple(item.global_track_id for item in snapshot.tracks)
    action = _rule_action(snapshot)

    assert action.target_global_track_id in ids_before
    assert tuple(item.global_track_id for item in snapshot.tracks) == ids_before
    assert action.target_global_track_id != action.camera_id


def test_missing_candidate_target_and_stale_plan_fail_closed_to_rule_action() -> None:
    snapshot = _snapshot()
    invalid = replace(_rule_action(snapshot), target_global_track_id="NOT-A-CANDIDATE")
    proposal = ActiveVisionPolicyProposal(
        action=invalid,
        confidence=0.99,
        inference_latency_ms=0.1,
        model_fingerprint="sha256:" + "1" * 64,
    )
    controller = ActiveVisionControllerV1(learned_policy=_StubPolicy(proposal))
    decision = controller.decide(
        snapshot,
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=snapshot.plan.plan_version,
        expected_coalition_version=snapshot.plan.coalition_version,
        expected_communication_version=snapshot.communication.communication_version,
        requested_mode="assist",
    )
    stale = controller.decide(
        snapshot,
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=snapshot.plan.plan_version + 1,
        expected_coalition_version=snapshot.plan.coalition_version,
        expected_communication_version=snapshot.communication.communication_version,
        requested_mode="assist",
    )

    assert decision.effective_action == decision.rule_action
    assert decision.fallback_reason == "candidate_target_missing"
    assert stale.rule_action.target_global_track_id is None
    assert stale.rule_action.intent in {ActiveVisionIntent.SEARCH_SECTOR, ActiveVisionIntent.HOLD}
    assert stale.fallback_reason == "stale_plan_version"


def test_gimbal_limits_rates_and_fov_modes_are_safety_projected() -> None:
    snapshot = _snapshot(
        yaw_by_camera={0: 29.5},
        supported_modes_by_camera={0: (ActiveVisionFovMode.WIDE,)},
    )
    rule = _rule_action(snapshot)
    yaw_violation = replace(rule, yaw_delta_deg=1.0)
    fov_violation = replace(rule, fov_mode=ActiveVisionFovMode.ZOOM)
    common = dict(
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=4,
        expected_coalition_version=7,
        expected_communication_version=9,
    )

    assert rule.yaw_delta_deg <= 0.5 + 1.0e-9
    assert validate_active_vision_action_v1(yaw_violation, snapshot, **common) == "gimbal_yaw_limit"
    assert validate_active_vision_action_v1(fov_violation, snapshot, **common) == "unsupported_fov_mode"
    assert {
        action.fov_mode
        for action in enumerate_safe_action_candidates(
            snapshot, camera_id="CAM-0", current_timestamp=NOW
        )
    } == {ActiveVisionFovMode.WIDE}

    zoom_camera = replace(
        snapshot.cameras[0],
        current_fov_mode=ActiveVisionFovMode.ZOOM,
        supported_fov_modes=(ActiveVisionFovMode.ZOOM,),
    )
    zoom_snapshot = replace(
        snapshot,
        cameras=(zoom_camera,) + snapshot.cameras[1:],
    )
    assert _rule_action(zoom_snapshot).fov_mode is ActiveVisionFovMode.ZOOM


def test_friendly_conflict_stale_evidence_and_action_timeout_fail_closed() -> None:
    reservation = FriendlyObservationReservation(
        owner_resource_id="INT-PEER",
        camera_id="CAM-PEER",
        communication_version=9,
        coalition_version=7,
        expires_timestamp=NOW + 1.0,
        global_track_id="GT-001",
    )
    snapshot = _snapshot(reservations=(reservation,))
    action = next(
        item
        for item in enumerate_safe_action_candidates(
            snapshot, camera_id="CAM-0", current_timestamp=NOW
        )
        if item.intent is ActiveVisionIntent.OBSERVE_TARGET
        and item.target_global_track_id == "GT-001"
    )
    common = dict(
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=4,
        expected_coalition_version=7,
        expected_communication_version=9,
    )
    stale_snapshot = _snapshot(projection_timestamp=NOW - 3.0)
    stale_action = next(
        item
        for item in enumerate_safe_action_candidates(
            stale_snapshot, camera_id="CAM-0", current_timestamp=NOW
        )
        if item.intent is ActiveVisionIntent.OBSERVE_TARGET
    )
    timed_out = replace(action, issued_timestamp=NOW - 1.0, expires_timestamp=NOW - 0.5)

    assert validate_active_vision_action_v1(action, snapshot, **common) == "friendly_observation_conflict"
    assert (
        validate_active_vision_action_v1(stale_action, stale_snapshot, **common)
        == "projection_evidence_stale"
    )
    assert validate_active_vision_action_v1(timed_out, snapshot, **common) == "action_timeout"


def test_shadow_never_changes_rule_action_and_decision_has_required_provenance() -> None:
    snapshot = _snapshot()
    learned_action = next(
        action
        for action in enumerate_safe_action_candidates(
            snapshot, camera_id="CAM-0", current_timestamp=NOW
        )
        if action.intent is ActiveVisionIntent.HOLD
    )
    proposal = ActiveVisionPolicyProposal(
        action=learned_action,
        confidence=0.99,
        inference_latency_ms=0.2,
        model_fingerprint="sha256:" + "1" * 64,
    )
    decision = ActiveVisionControllerV1(learned_policy=_StubPolicy(proposal)).decide(
        snapshot,
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=4,
        expected_coalition_version=7,
        expected_communication_version=9,
        requested_mode="shadow",
    )

    assert decision.requested_mode is ActiveVisionRuntimeMode.SHADOW
    assert decision.effective_mode is ActiveVisionRuntimeMode.SHADOW
    assert decision.requested_action == learned_action
    assert decision.effective_action == decision.rule_action
    assert decision.inference_latency_ms >= 0.2
    assert decision.model_fingerprint == proposal.model_fingerprint
    assert decision.plan_version == 4


@pytest.mark.parametrize(
    ("proposal", "reason"),
    [
        (
            ActiveVisionPolicyProposal(
                action=None,
                confidence=0.0,
                inference_latency_ms=0.1,
                model_fingerprint="sha256:" + "1" * 64,
                ood=True,
            ),
            "model_input_ood",
        ),
        (
            ActiveVisionPolicyProposal(
                action=None,
                confidence=0.2,
                inference_latency_ms=0.1,
                model_fingerprint="sha256:" + "1" * 64,
            ),
            "model_low_confidence",
        ),
    ],
)
def test_ood_and_low_confidence_fall_back(proposal: ActiveVisionPolicyProposal, reason: str) -> None:
    snapshot = _snapshot()
    decision = ActiveVisionControllerV1(learned_policy=_StubPolicy(proposal)).decide(
        snapshot,
        camera_id="CAM-0",
        current_timestamp=NOW,
        expected_plan_version=4,
        expected_coalition_version=7,
        expected_communication_version=9,
        requested_mode="assist",
    )
    assert decision.effective_action == decision.rule_action
    assert decision.fallback_reason == reason


def test_timeout_and_non_finite_policy_output_fall_back() -> None:
    snapshot = _snapshot()
    action = _rule_action(snapshot)
    timeout_proposal = ActiveVisionPolicyProposal(
        action=action,
        confidence=0.99,
        inference_latency_ms=10.0,
        model_fingerprint="sha256:" + "1" * 64,
    )
    non_finite_proposal = SimpleNamespace(
        action=action,
        confidence=float("nan"),
        inference_latency_ms=0.1,
        model_fingerprint="sha256:" + "1" * 64,
        ood=False,
        failure_reason=None,
    )
    config = ActiveVisionSafetyConfigV1(model_inference_timeout_ms=1.0)

    for proposal, reason in (
        (timeout_proposal, "model_inference_timeout"),
        (non_finite_proposal, "model_non_finite_output"),
    ):
        decision = ActiveVisionControllerV1(
            learned_policy=_StubPolicy(proposal), safety_config=config
        ).decide(
            snapshot,
            camera_id="CAM-0",
            current_timestamp=NOW,
            expected_plan_version=4,
            expected_coalition_version=7,
            expected_communication_version=9,
            requested_mode="assist",
        )
        assert decision.effective_action == decision.rule_action
        assert decision.fallback_reason == reason


def _research_episodes(count: int = 8) -> tuple[ActiveVisionResearchEpisode, ...]:
    episodes: list[ActiveVisionResearchEpisode] = []
    for seed in range(count):
        snapshot = _snapshot(now=NOW + seed)
        selected = _rule_action(snapshot)
        episodes.append(
            ActiveVisionResearchEpisode(
                scenario_version="active-vision-unit-v1",
                seed=seed,
                episode_id="episode-a",
                transitions=(
                    ActiveVisionTransition(
                        snapshot=snapshot,
                        camera_id="CAM-0",
                        selected_action=selected,
                        reward=1.0,
                        done=True,
                    ),
                ),
                synthetic_fixture=True,
            )
        )
    return tuple(episodes)


def test_whole_seed_split_behavior_cloning_and_native_clipped_ppo_smoke() -> None:
    episodes = _research_episodes()
    dataset = split_active_vision_episode_groups(episodes, split_seed=33)
    duplicate_group_splits = {
        episode.group_key: dataset.split_by_group[episode.group_key] for episode in episodes
    }

    assert set(duplicate_group_splits.values()) == {"train", "validation", "test"}
    assert dataset.manifest()["split_policy"]["edge_or_transition_level_random_split"] is False
    bc = train_behavior_cloning(
        dataset,
        config=BehaviorCloningConfig(seed=7, epochs=1, hidden_dim=8),
    )
    ppo = train_clipped_ppo(
        bc.model,
        dataset.split("train"),
        config=ClippedPpoConfig(seed=7, epochs=1),
    )

    assert bc.transition_count == len(dataset.split("train"))
    assert np.all(np.isfinite(bc.epoch_losses))
    assert ppo.transition_count == len(dataset.split("train"))
    assert np.all(np.isfinite(ppo.epoch_losses))


def test_split_keeps_shared_seed_values_atomic_across_scenarios() -> None:
    base = _research_episodes()
    episodes = tuple(
        replace(
            episode,
            scenario_version=scenario,
            episode_id=f"episode-{episode.seed}-{scenario}",
        )
        for episode in base
        for scenario in ("active-vision-small-v1", "active-vision-large-v1")
    ) + (
        replace(
            base[3],
            scenario_version="active-vision-small-v1",
            episode_id="episode-3-repeat",
        ),
    )

    forward = split_active_vision_episode_groups(episodes, split_seed=91)
    reversed_input = split_active_vision_episode_groups(reversed(episodes), split_seed=91)

    assert dict(forward.split_by_group) == dict(reversed_input.split_by_group)
    assert forward.split_sha256 == reversed_input.split_sha256
    assert forward.training_set_sha256 == reversed_input.training_set_sha256
    assert forward.manifest()["schema_version"] == "d5.active-vision-dataset.v2"
    assert (
        forward.manifest()["split_policy"]["shared_seed_values_atomic_across_scenarios"]
        is True
    )

    splits_by_seed: dict[int, set[str]] = {}
    for episode in episodes:
        splits_by_seed.setdefault(episode.seed, set()).add(
            forward.split_by_group[episode.group_key]
        )
    assert all(len(splits) == 1 for splits in splits_by_seed.values())
    seeds_by_split = {
        split: {episode.seed for episode in forward.split(split)}
        for split in ("train", "validation", "test")
    }
    assert all(seeds_by_split.values())
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["train"])
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["validation"])
    assert seeds_by_split["train"].isdisjoint(seeds_by_split["validation"])


def test_split_fails_closed_with_fewer_than_three_unique_seed_values() -> None:
    base = _research_episodes(2)
    repeated = tuple(
        replace(
            episode,
            scenario_version=scenario,
            episode_id=f"episode-{episode.seed}-{scenario}",
        )
        for episode in base
        for scenario in ("active-vision-small-v1", "active-vision-large-v1")
    )

    with pytest.raises(ValueError, match="at least three unique seed values"):
        split_active_vision_episode_groups(repeated)


def _write_bundle(
    path: Path,
    snapshot: ActiveVisionSnapshotV1,
    *,
    bundle_profile: str = "research_candidate",
) -> None:
    torch.manual_seed(4)
    model = ActiveVisionActorCritic(hidden_dim=8)
    episode = ActiveVisionResearchEpisode(
        scenario_version="bundle-unit-v1",
        seed=1,
        episode_id="episode-a",
        transitions=(
            ActiveVisionTransition(
                snapshot=snapshot,
                camera_id="CAM-0",
                selected_action=_rule_action(snapshot),
                done=True,
            ),
        ),
        synthetic_fixture=True,
    )
    bounds = fit_active_vision_feature_bounds((episode,))
    write_active_vision_model_bundle(
        path,
        model,
        feature_bounds=bounds,
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_method="behavior_cloning",
        training_config={"seed": 4},
        validation_results={"status": "unit_smoke_not_admission"},
        bundle_profile=bundle_profile,
    )


def _rewrite_checksums(bundle: Path) -> None:
    manifest_sha = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    weights_sha = hashlib.sha256((bundle / "weights.pt").read_bytes()).hexdigest()
    (bundle / "SHA256SUMS").write_text(
        f"{manifest_sha}  manifest.json\n{weights_sha}  weights.pt\n",
        encoding="ascii",
    )


def _write_active_vision_loader_fixture(
    bundle: Path,
    snapshot: ActiveVisionSnapshotV1,
    model: ActiveVisionActorCritic,
    report: object,
) -> None:
    episode = ActiveVisionResearchEpisode(
        scenario_version="bundle-unit-v1",
        seed=1,
        episode_id="episode-a",
        transitions=(
            ActiveVisionTransition(
                snapshot=snapshot,
                camera_id="CAM-0",
                selected_action=_rule_action(snapshot),
                done=True,
            ),
        ),
        synthetic_fixture=True,
    )
    write_active_vision_model_bundle(
        bundle,
        model,
        feature_bounds=fit_active_vision_feature_bounds((episode,)),
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_method="behavior_cloning",
        training_config={"seed": 23},
        validation_results={"status": "unit_contract_only"},
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"] = {
        "status": "assist_admitted",
        "assist_admitted": True,
        "report": dict(report.to_manifest()),
    }
    manifest["runtime_policy"].update(
        {
            "status": "assist_admitted",
            "allowed_runtime_modes": ["shadow", "assist"],
            "assist_admitted": True,
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _rewrite_checksums(bundle)


def test_bundle_round_trip_sha_tamper_schema_and_ood_fail_closed(tmp_path: Path) -> None:
    snapshot = _snapshot()
    valid = tmp_path / "valid"
    _write_bundle(valid, snapshot)
    loaded = load_active_vision_model_bundle(valid)
    assert loaded.available is True
    assert loaded.assist_admitted is False
    assert loaded.manifest["schema_version"] == "d5.active-vision-model-bundle.v5"
    assert loaded.manifest["dataset_schema_version"] == "d5.active-vision-episode-dataset.v3"
    assert loaded.model_fingerprint == active_vision_model_fingerprint(loaded.model)

    changed = _snapshot(camera_count=3)
    proposal = loaded.propose(changed, camera_id="CAM-0", current_timestamp=NOW)
    assert proposal.ood is True
    assert proposal.failure_reason == "model_input_ood"

    tampered = tmp_path / "tampered"
    _write_bundle(tampered, snapshot)
    weights = tampered / "weights.pt"
    weights.write_bytes(weights.read_bytes() + b"tamper")
    runtime = load_active_vision_model_bundle_for_runtime(tampered)
    assert runtime.available is False
    assert runtime.failure_reason == "bundle_weights_sha_mismatch"

    wrong_schema = tmp_path / "wrong-schema"
    _write_bundle(wrong_schema, snapshot)
    manifest_path = wrong_schema / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "d5.active-vision-model-bundle.invalid"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(wrong_schema)
    with pytest.raises(ActiveVisionBundleValidationError) as exc_info:
        load_active_vision_model_bundle(wrong_schema)
    assert exc_info.value.code == "bundle_schema_mismatch"


def test_development_bundle_is_shadow_only_and_assist_fails_closed(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "development-shadow"
    _write_bundle(bundle, _snapshot(), bundle_profile="development_shadow_only")

    shadow = load_active_vision_model_bundle_for_runtime(
        bundle,
        requested_mode=ActiveVisionRuntimeMode.SHADOW,
    )
    assist = load_active_vision_model_bundle_for_runtime(
        bundle,
        requested_mode=ActiveVisionRuntimeMode.ASSIST,
    )

    assert shadow.available is True
    assert shadow.runtime_status == "development_shadow_only"
    assert shadow.assist_admitted is False
    assert shadow.ppo_enabled is False
    assert shadow.rule_fallback_required is True
    assert assist.available is False
    assert assist.failure_reason == "bundle_assist_not_admitted"


class _TinyActiveVisionDataset:
    def __init__(
        self,
        episodes_by_split: dict[str, tuple[ActiveVisionResearchEpisode, ...]],
    ) -> None:
        self._episodes_by_split = episodes_by_split
        self.episode_descriptors = tuple(
            {
                "scenario_version": episode.scenario_version,
                "seed": episode.seed,
                "episode_id": episode.episode_id,
                "split": split,
                "sample_count": len(episode.transitions),
                "synthetic_fixture": episode.synthetic_fixture,
            }
            for split, episodes in episodes_by_split.items()
            for episode in episodes
        )
        self.manifest_sha256 = "d" * 64
        self.manifest = {
            "schema_version": "d5.active-vision-episode-dataset.v3",
            "split_sha256": "e" * 64,
            "training_set_sha256": "f" * 64,
            "availability": {
                name: {
                    "status": "unavailable",
                    "sample_count": len(self.episode_descriptors),
                    "available_sample_count": 0,
                }
                for name in ("outcome", "reward", "counterfactual", "causal_label")
            },
        }

    def split_descriptors(self, split: str) -> tuple[dict[str, object], ...]:
        return tuple(
            item for item in self.episode_descriptors if item["split"] == split
        )

    def iter_behavior_cloning_episodes(self, split: str):
        return iter(self._episodes_by_split[split])


def test_cached_behavior_cloning_fails_closed_before_training_on_legacy_sparse_corpus(
    tmp_path: Path,
) -> None:
    base = _research_episodes(7)
    scales = ("5v5", "50v50", "200v200", "5v5", "50v50", "200v200", "5v5")
    episodes = tuple(
        replace(
            episode,
            scenario_version=f"active-vision-{scale}-v1",
            episode_id=f"episode-{index}",
        )
        for index, (episode, scale) in enumerate(zip(base, scales))
    )
    dataset = _TinyActiveVisionDataset(
        {
            "train": episodes[:3],
            "validation": episodes[3:5],
            "test": episodes[5:],
        }
    )

    manifest, audit, manifest_sha = build_behavior_cloning_feature_cache(
        dataset,
        tmp_path / "cache",
    )
    loaded_manifest, caches, loaded_sha = load_behavior_cloning_feature_cache(
        tmp_path / "cache"
    )
    config = ActiveVisionBcConfig(
        seed=17,
        epochs=1,
        batch_size=2,
        evaluation_batch_size=2,
        hidden_dim=8,
        cpu_threads=1,
        latency_samples=1,
        latency_warmup=0,
    )
    with pytest.raises(
        ActiveVisionCorpusCoverageError,
        match="training corpus failed closed",
    ):
        train_cached_behavior_cloning(
            loaded_manifest,
            caches,
            config=config,
        )

    assert loaded_sha == manifest_sha
    assert manifest["splits"]["train"]["sample_count"] == 3
    assert audit["sample_count"] == 7
    assert audit["whole_seed_split_atomic"] is True
    assert audit["class_imbalance"]["hold_positive_sample_count"] == 0
    corpus = audit["training_corpus_audit"]
    assert corpus["training_gate"]["development_training_allowed"] is False
    assert "hold_demonstration_missing" in corpus["training_gate"]["failure_reasons"]
    assert "recon_camera_training_data_missing" in corpus["training_gate"][
        "failure_reasons"
    ]
    assert "reserved_seed_evidence_unavailable" in corpus["training_gate"][
        "failure_reasons"
    ]
    assert corpus["collection_plan"]["requests"]


def _paired_results(
    *,
    synthetic: bool,
    fingerprint: str = "sha256:" + "d" * 64,
) -> tuple[PairedShadowEpisodeResult, ...]:
    return tuple(
        PairedShadowEpisodeResult(
            scenario_version="held-out-active-vision-v1",
            seed=100 + index,
            episode_id="episode-a",
            model_fingerprint=fingerprint,
            rule_safety_violation_count=0,
            model_safety_violation_count=0,
            rule_visibility_score=0.8,
            model_visibility_score=0.81,
            rule_reacquisition_delay_s=1.0,
            model_reacquisition_delay_s=0.9,
            synthetic_fixture=synthetic,
        )
        for index in range(20)
    )


def test_paired_shadow_requires_20_unseen_non_synthetic_non_degrading_seeds() -> None:
    seen = (("training-v1", 1), ("validation-v1", 2))
    admitted = evaluate_paired_shadow_admission(
        _paired_results(synthetic=False),
        training_group_keys=seen[:1],
        validation_group_keys=seen[1:],
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        formal_evaluation=True,
    )
    synthetic = evaluate_paired_shadow_admission(
        _paired_results(synthetic=True),
        training_group_keys=seen[:1],
        validation_group_keys=seen[1:],
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        formal_evaluation=True,
    )

    assert admitted.assist_admitted is True
    assert admitted.unseen_seed_count == 20
    assert admitted.safety_violation_delta == 0
    assert admitted.mean_visibility_delta > 0.0
    assert admitted.mean_reacquisition_delay_delta_s < 0.0
    assert synthetic.assist_admitted is False
    assert "synthetic_fixture_cannot_grant_formal_admission" in synthetic.failure_reasons


def test_active_vision_production_writer_blocks_bare_admission_report(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    torch.manual_seed(23)
    model = ActiveVisionActorCritic(hidden_dim=8)
    fingerprint = active_vision_model_fingerprint(model)
    report = evaluate_paired_shadow_admission(
        _paired_results(synthetic=False, fingerprint=fingerprint),
        training_group_keys=(("training-v1", 1),),
        validation_group_keys=(("validation-v1", 2),),
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        formal_evaluation=True,
    )
    production = tmp_path / "production"
    with pytest.raises(ValueError, match="evidence assembler is unavailable"):
        write_active_vision_model_bundle(
            production,
            model,
            feature_bounds=fit_active_vision_feature_bounds(
                (
                    ActiveVisionResearchEpisode(
                        scenario_version="bundle-unit-v1",
                        seed=1,
                        episode_id="episode-a",
                        transitions=(
                            ActiveVisionTransition(
                                snapshot=snapshot,
                                camera_id="CAM-0",
                                selected_action=_rule_action(snapshot),
                                done=True,
                            ),
                        ),
                        synthetic_fixture=True,
                    ),
                )
            ),
            dataset_manifest_sha256="a" * 64,
            split_sha256="b" * 64,
            training_set_sha256="c" * 64,
            training_method="behavior_cloning",
            training_config={"seed": 23},
            validation_results={"status": "unit_contract_only"},
            admission_report=report,
        )
    assert not production.exists()

    bundle = tmp_path / "private-loader-fixture"
    _write_active_vision_loader_fixture(bundle, snapshot, model, report)
    parsed = _load_active_vision_model_bundle_fixture(bundle)
    runtime = load_active_vision_model_bundle_for_runtime(
        bundle,
        requested_mode=ActiveVisionRuntimeMode.ASSIST,
    )
    assert parsed.available is True
    assert parsed.assist_admitted is True
    assert runtime.available is False
    assert (
        runtime.failure_reason
        == "bundle_admission_evidence_assembler_unavailable"
    )

    payload = dict(report.to_manifest())
    payload["formal_evaluation"] = "true"
    with pytest.raises(TypeError, match="formal_evaluation must be bool"):
        admission_report_from_manifest(payload)

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"]["report"]["assist_admitted"] = "true"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _rewrite_checksums(bundle)
    with pytest.raises(ActiveVisionBundleValidationError) as exc_info:
        _load_active_vision_model_bundle_fixture(bundle)
    assert exc_info.value.code == "admission_invalid"


def test_library_default_is_disabled_but_cli_default_is_shadow() -> None:
    assert ActiveVisionControllerV1().default_mode is ActiveVisionRuntimeMode.DISABLED
    assert build_parser().parse_args([]).mode == ActiveVisionRuntimeMode.SHADOW.value
