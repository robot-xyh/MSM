from __future__ import annotations

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.airsim_adapter import (
    AirSimOfflineDetectionLabel,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.error_campaign import (
    SearchTerminalErrorConfig,
    build_search_terminal_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_error_airsim import (
    _actor_to_truth_id,
    _build_report,
    _build_replay_fixture,
    _prepare_episode_runtime,
    parse_args,
)


def test_air_sim_replay_conversion_keeps_truth_out_of_online_tracks() -> None:
    bundle = build_search_terminal_fixture(
        SearchTerminalErrorConfig(
            target_count=20,
            seed=20260820,
            navigation_mode="satellite",
            attitude_mode="normal",
            detection_mode="ideal",
            handover_mode="anonymous",
        )
    )
    fixture = bundle.handover_fixture
    truth_by_local = {label.local_track_id: label.truth_target_id for label in fixture.local_truth}
    actor_by_truth = {
        target.truth_target_id: target.actor_name for target in fixture.target_truth
    }
    labels = tuple(
        AirSimOfflineDetectionLabel(
            camera_id=track.camera_id,
            local_track_id=track.local_track_id,
            measurement_timestamp=track.measurement_timestamp,
            raw_detection_name=actor_by_truth[truth_by_local[track.local_track_id]],
        )
        for frame in fixture.frames
        for track in frame
    )

    replay = _build_replay_fixture(bundle, fixture.frames, labels)

    assert len(replay.local_truth) == 20
    assert all(
        track.metadata["detection_source"] == "simGetDetections_locked_after_search"
        for frame in replay.frames
        for track in frame
    )
    assert not any(
        "truth_target_id" in track.metadata
        for frame in replay.frames
        for track in frame
    )


def test_actor_name_alias_and_cli_scale_parsing(tmp_path) -> None:
    mapping = {"MSM_TargetActor_1": "TGT-001"}
    assert _actor_to_truth_id("MSM_TargetActor_1_2", mapping) == "TGT-001"
    args = parse_args(
        (
            "--output-dir",
            str(tmp_path / "out"),
            "--target-counts",
            "20",
            "40",
            "60",
        )
    )
    assert args.target_counts == [20, 40, 60]


def test_air_sim_runtime_resets_only_between_episodes() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def reset(self) -> None:
            self.calls.append("reset")

        def wait_for_connection(self, timeout_s: float) -> None:
            self.calls.append(("wait_for_connection", timeout_s))

    runtime = Runtime()
    _prepare_episode_runtime(
        runtime,
        reset_before_episode=False,
        connection_timeout_s=180.0,
    )
    assert runtime.calls == []

    _prepare_episode_runtime(
        runtime,
        reset_before_episode=True,
        connection_timeout_s=180.0,
    )
    assert runtime.calls == ["reset", ("wait_for_connection", 180.0)]


def test_air_sim_report_describes_only_executed_scales() -> None:
    report = _build_report(
        (
            {
                "target_count": 20,
                "profile": "satellite_normal",
                "backend": "geometry",
                "binding_precision": 1.0,
                "binding_recall": 0.9,
                "true_binding_count": 18,
                "false_binding_count": 0,
            },
        )
    )

    assert "完成20目标试验" in report
    assert "20、40、60目标依次复位" not in report
