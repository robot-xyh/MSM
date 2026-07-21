from __future__ import annotations

import builtins
from collections import Counter
from dataclasses import asdict, replace
import json

import pytest

import d5_terminal_association.active_vision_curriculum as curriculum_module
from d5_terminal_association.active_vision_camera_executor import (
    ActiveVisionCameraExecutionOutcome,
)
from d5_terminal_association.active_vision_contracts import (
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionRuntimeMode,
    assert_truth_free_active_vision_payload,
    enumerate_safe_action_candidates,
)
from d5_terminal_association.active_vision_curriculum import (
    ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT,
    ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT,
    ActiveVisionCurriculumConfig,
    build_active_vision_curriculum_episode,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionSourceIdentityV1,
)


SOURCE_IDENTITY = ActiveVisionSourceIdentityV1(
    git_commit="a" * 40,
    git_dirty=False,
    config_sha256="b" * 64,
)
CONFIG = ActiveVisionCurriculumConfig(global_track_id="CENTER-TRACK-ALPHA")


def _build(seed: int = 37):
    return build_active_vision_curriculum_episode(
        seed,
        source_identity=SOURCE_IDENTITY,
        config=CONFIG,
    )


def _canonical_record_json(record: object) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def test_curriculum_exact_episode_sample_and_category_counts() -> None:
    record, summary = _build()
    intents = Counter(sample.effective_action.intent.value for sample in record.samples)
    fov_modes = Counter(sample.effective_action.fov_mode.value for sample in record.samples)
    sample_roles = tuple(
        "interceptor" if sample.camera_id == CONFIG.interceptor_camera_id else "recon"
        for sample in record.samples
    )
    roles = Counter(sample_roles)
    role_intents = Counter(
        (role, sample.effective_action.intent.value)
        for role, sample in zip(sample_roles, record.samples, strict=True)
    )
    role_fov_modes = Counter(
        (role, sample.effective_action.fov_mode.value)
        for role, sample in zip(sample_roles, record.samples, strict=True)
    )
    ack_outcomes = Counter(
        "missing"
        if sample.runtime_ack is None
        else "applied"
        if sample.runtime_ack.accepted
        else "rejected"
        for sample in record.samples
    )

    assert summary.episode_count == 1
    assert summary.segment_count == ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT == 8
    assert (
        summary.sample_count
        == len(record.samples)
        == ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT
        == 12
    )
    assert summary.camera_count == 2
    assert intents == {"hold": 2, "observe_target": 6, "reacquire": 2, "search_sector": 2}
    assert fov_modes == {"wide": 10, "zoom": 2}
    assert roles == {"interceptor": 6, "recon": 6}
    assert role_intents == {
        (role, intent): count
        for role in ("interceptor", "recon")
        for intent, count in (
            ("hold", 1),
            ("observe_target", 3),
            ("reacquire", 1),
            ("search_sector", 1),
        )
    }
    assert role_fov_modes == {
        ("interceptor", "wide"): 5,
        ("interceptor", "zoom"): 1,
        ("recon", "wide"): 5,
        ("recon", "zoom"): 1,
    }
    assert ack_outcomes == {"applied": 4, "rejected": 4, "missing": 4}
    assert summary.intent_counts == tuple(intents.items())
    assert summary.fov_mode_counts == tuple(fov_modes.items())
    assert summary.camera_role_counts == tuple(roles.items())
    assert dict(summary.ack_outcome_counts) == ack_outcomes


def test_curriculum_time_versions_and_sequence_are_strictly_legal() -> None:
    record, _ = _build()
    timestamps = [sample.snapshot.snapshot_timestamp for sample in record.samples]
    plan_versions = [sample.plan_version for sample in record.samples]
    coalition_versions = [sample.coalition_version for sample in record.samples]
    communication_versions = [sample.communication_version for sample in record.samples]

    assert [sample.sequence_index for sample in record.samples] == list(range(12))
    assert all(right > left for left, right in zip(timestamps, timestamps[1:]))
    assert plan_versions == [1, 2, 3, 3, 3, 4, 4, 4, 5, 6, 7, 8]
    assert coalition_versions == plan_versions
    assert communication_versions == list(range(1, 13))
    for sample in record.samples:
        snapshot = sample.snapshot
        action = sample.effective_action
        assert sample.rule_demonstration_action == action
        assert (
            action.plan_version,
            action.coalition_version,
            action.communication_version,
        ) == (
            snapshot.plan.plan_version,
            snapshot.plan.coalition_version,
            snapshot.communication.communication_version,
        )
        assert snapshot.communication.plan_version == snapshot.plan.plan_version
        assert snapshot.communication.coalition_version == snapshot.plan.coalition_version
        assert snapshot.communication.update_timestamp <= snapshot.snapshot_timestamp
        assert action.issued_timestamp == snapshot.snapshot_timestamp
        assert action.expires_timestamp > action.issued_timestamp
        assert sample.camera_feedback.camera_state.state_timestamp >= snapshot.camera(
            sample.camera_id
        ).state_timestamp
        for track in snapshot.tracks:
            assert track.measurement_timestamp <= snapshot.snapshot_timestamp
        for projection in snapshot.projections:
            assert projection.measurement_timestamp <= projection.arrival_timestamp
            assert projection.arrival_timestamp <= snapshot.snapshot_timestamp


def test_curriculum_ack_and_feedback_semantics_and_executor_command_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_execute = curriculum_module.DeterministicCameraCommandExecutor.execute
    calls: list[tuple[int, int, ActiveVisionCameraExecutionOutcome]] = []

    def checked_execute(self, snapshot, action, feedback, **kwargs):
        assert kwargs["command_version"] == action.communication_version
        result = original_execute(self, snapshot, action, feedback, **kwargs)
        if result.outcome is not ActiveVisionCameraExecutionOutcome.APPLIED:
            assert result.camera_feedback is feedback
        calls.append(
            (kwargs["command_version"], action.communication_version, result.outcome)
        )
        return result

    monkeypatch.setattr(
        curriculum_module.DeterministicCameraCommandExecutor,
        "execute",
        checked_execute,
    )
    record, _ = _build()
    last_accepted_by_camera: dict[str, int | None] = {
        CONFIG.interceptor_camera_id: None,
        CONFIG.recon_camera_id: None,
    }

    assert len(calls) == 12
    assert all(command == communication for command, communication, _ in calls)
    for sample in record.samples:
        ack = sample.runtime_ack
        previous = last_accepted_by_camera[sample.camera_id]
        if ack is None:
            assert sample.camera_feedback.last_accepted_command_version == previous
            continue
        assert ack.command_version == sample.effective_action.communication_version
        assert ack.communication_version == sample.communication_version
        if ack.accepted:
            assert ack.status_code == "applied"
            assert sample.camera_feedback.last_accepted_command_version == ack.command_version
            last_accepted_by_camera[sample.camera_id] = ack.command_version
        else:
            assert ack.status_code.startswith("rejected_")
            assert sample.camera_feedback.last_accepted_command_version == previous


def test_curriculum_uses_controller_rule_policy_and_existing_safe_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_decide = curriculum_module.ActiveVisionControllerV1.decide
    original_select = curriculum_module.DeterministicLookAtScanPolicy.select_action
    calls = Counter()

    def checked_decide(self, *args, **kwargs):
        calls["controller"] += 1
        return original_decide(self, *args, **kwargs)

    def checked_select(self, *args, **kwargs):
        calls["rule_policy"] += 1
        return original_select(self, *args, **kwargs)

    monkeypatch.setattr(curriculum_module.ActiveVisionControllerV1, "decide", checked_decide)
    monkeypatch.setattr(
        curriculum_module.DeterministicLookAtScanPolicy,
        "select_action",
        checked_select,
    )
    record, _ = _build()

    assert calls == {"controller": 12, "rule_policy": 12}
    for sample in record.samples:
        assert sample.requested_mode is ActiveVisionRuntimeMode.DISABLED
        assert sample.effective_mode is ActiveVisionRuntimeMode.DISABLED
        assert sample.requested_action is None
        assert sample.fallback_reason == "learning_disabled"
        candidates = enumerate_safe_action_candidates(
            sample.snapshot,
            camera_id=sample.camera_id,
            current_timestamp=sample.effective_action.issued_timestamp,
        )
        assert sample.effective_action.action_key in {item.action_key for item in candidates}

    assert [sample.effective_action.intent for sample in record.samples] == [
        ActiveVisionIntent.HOLD,
        ActiveVisionIntent.HOLD,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.OBSERVE_TARGET,
        ActiveVisionIntent.REACQUIRE,
        ActiveVisionIntent.REACQUIRE,
        ActiveVisionIntent.SEARCH_SECTOR,
        ActiveVisionIntent.SEARCH_SECTOR,
    ]
    assert [sample.effective_action.fov_mode for sample in record.samples] == [
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.ZOOM,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.ZOOM,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.WIDE,
    ]


def test_curriculum_object_and_serialization_are_deterministic() -> None:
    first_record, first_summary = _build(73)
    second_record, second_summary = _build(73)

    assert first_record == second_record
    assert first_summary == second_summary
    assert _canonical_record_json(first_record) == _canonical_record_json(second_record)
    assert first_summary.to_json() == second_summary.to_json()
    assert json.loads(first_summary.to_json()) == first_summary.to_payload()


def test_curriculum_preserves_caller_owned_global_track_id_and_truth_guard() -> None:
    record, _ = _build()
    online_payload = asdict(record)

    assert_truth_free_active_vision_payload(record)
    assert not {"reward", "counterfactual_reward", "causal_label"}.intersection(
        _nested_keys(online_payload)
    )
    assert {
        track.global_track_id
        for sample in record.samples
        for track in sample.snapshot.tracks
    } == {CONFIG.global_track_id}
    assert {
        assignment.global_track_id
        for sample in record.samples
        for assignment in sample.snapshot.plan.assignments
    } == {CONFIG.global_track_id}
    assert {
        projection.global_track_id
        for sample in record.samples
        for projection in sample.snapshot.projections
    } == {CONFIG.global_track_id}
    assert {
        action.target_global_track_id
        for sample in record.samples
        for action in (sample.rule_demonstration_action, sample.effective_action)
        if action.target_global_track_id is not None
    } == {CONFIG.global_track_id}

    with pytest.raises(ValueError, match="forbidden truth/actor/object identity"):
        replace(CONFIG, interceptor_camera_id="actor-001")


def test_curriculum_does_not_mutate_inputs_or_write_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_before = asdict(SOURCE_IDENTITY)
    config_before = asdict(CONFIG)

    def reject_open(*args: object, **kwargs: object) -> object:
        raise AssertionError("in-memory curriculum attempted a file write")

    monkeypatch.setattr(builtins, "open", reject_open)
    record, summary = _build()

    assert len(record.samples) == summary.sample_count
    assert asdict(SOURCE_IDENTITY) == source_before
    assert asdict(CONFIG) == config_before


@pytest.mark.parametrize("seed", [0, 1, 2**127 + 29])
def test_curriculum_accepts_any_non_negative_integer_seed(seed: int) -> None:
    record, summary = _build(seed)

    assert record.seed == summary.seed == seed
    assert record.episode_id.endswith(f"-{seed}")
    assert len(record.samples) == 12


@pytest.mark.parametrize("seed", [-1, -10])
def test_curriculum_rejects_negative_seed(seed: int) -> None:
    with pytest.raises(ValueError, match="seed must be a non-negative integer"):
        _build(seed)


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_nested_keys(item))
        return keys
    if isinstance(value, (list, tuple)):
        keys: set[str] = set()
        for item in value:
            keys.update(_nested_keys(item))
        return keys
    return set()
