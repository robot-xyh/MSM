from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion import (
    GlobalTrack,
    TrackLevel,
    summarize_recon_cue_from_tracks,
)


def _global_track(
    track_id: str,
    position: tuple[float, float, float],
    position_variance: float,
    coverage_cell: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> GlobalTrack:
    covariance = np.diag(
        [
            position_variance,
            position_variance,
            position_variance,
            1.0,
            1.0,
            1.0,
        ]
    )
    return GlobalTrack(
        global_track_id=track_id,
        state=np.asarray([*position, 0.0, 0.0, 0.0], dtype=float),
        covariance=covariance,
        timestamp=arrival_timestamp,
        track_level=TrackLevel.COARSE,
        metadata={
            "coverage_cell": coverage_cell,
            "latest_measurement_timestamp": measurement_timestamp,
            "latest_arrival_timestamp": arrival_timestamp,
        },
    )


def test_recon_cue_summary_weights_all_targets_by_covariance() -> None:
    tracks = [
        _global_track("global_track_a", (0.0, 0.0, -80.0), 1.0, "cell-a", 10.0, 10.1),
        _global_track("global_track_b", (10.0, 0.0, -80.0), 10.0, "cell-b", 10.2, 10.3),
    ]

    summary = summarize_recon_cue_from_tracks(tracks, stale_after_s=None)
    payload = summary.to_dict()

    assert summary.track_count == 2
    assert summary.stale_count == 0
    assert summary.active_target_ids == ("global_track_a", "global_track_b")
    assert summary.coverage_cell is None
    assert summary.coverage_cells == ("cell-a", "cell-b")
    assert summary.cue_position_ned[0] == pytest.approx(10.0 / 11.0)
    assert summary.cue_position_ned[1] == pytest.approx(0.0)
    assert summary.cue_position_ned[2] == pytest.approx(-80.0)
    assert summary.measurement_timestamp == pytest.approx(10.2)
    assert summary.arrival_timestamp == pytest.approx(10.3)
    assert payload["cue_position_ned"] == pytest.approx([10.0 / 11.0, 0.0, -80.0])
    assert payload["centroid_ned"] == payload["cue_position_ned"]
    assert payload["covariance_trace"] > 0.0


def test_recon_cue_summary_filters_by_coverage_cell() -> None:
    tracks = [
        _global_track("global_track_a", (0.0, 0.0, -80.0), 1.0, "cell-a", 10.0, 10.1),
        _global_track("global_track_b", (10.0, 0.0, -80.0), 10.0, "cell-b", 10.2, 10.3),
        _global_track("global_track_c", (12.0, 2.0, -82.0), 2.0, "cell-b", 10.4, 10.5),
    ]

    summary = summarize_recon_cue_from_tracks(tracks, coverage_cell="cell-b", stale_after_s=None)

    assert summary.track_count == 2
    assert summary.total_input_count == 3
    assert summary.excluded_count == 1
    assert summary.coverage_cell == "cell-b"
    assert summary.coverage_cells == ("cell-b",)
    assert summary.active_target_ids == ("global_track_b", "global_track_c")
    assert summary.cue_position_ned[0] == pytest.approx(11.6666666667)
    assert summary.cue_position_ned[1] == pytest.approx(1.6666666667)
    assert summary.cue_position_ned[2] == pytest.approx(-81.6666666667)


def test_recon_cue_summary_uses_conservative_default_when_covariance_missing() -> None:
    tracks = [
        {
            "global_track_id": "precise_track",
            "state": [0.0, 0.0, -60.0, 0.0, 0.0, 0.0],
            "covariance": np.diag([1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
            "metadata": {
                "coverage_cell": "cell-a",
                "latest_measurement_timestamp": 3.0,
                "latest_arrival_timestamp": 3.1,
            },
        },
        {
            "global_track_id": "missing_covariance_track",
            "state": [100.0, 0.0, -60.0, 0.0, 0.0, 0.0],
            "metadata": {
                "coverage_cell": "cell-a",
                "latest_measurement_timestamp": 3.05,
                "latest_arrival_timestamp": 3.2,
            },
        },
    ]

    summary = summarize_recon_cue_from_tracks(
        tracks,
        coverage_cell="cell-a",
        stale_after_s=None,
        default_position_variance_m2=10_000.0,
    )

    assert summary.track_count == 2
    assert summary.default_covariance_count == 1
    assert "default_covariance" in summary.quality_flags
    assert summary.cue_position_ned[0] < 0.02
    assert summary.cue_position_ned[2] == pytest.approx(-60.0)
    assert summary.covariance_trace > 0.0


def test_recon_cue_summary_preserves_track_like_timestamps() -> None:
    track = {
        "global_track_id": "dict_track",
        "position_ned": [30.0, -5.0, -110.0],
        "covariance": [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 9.0]],
        "metadata": {
            "coverage_cell": "cell-high",
            "latest_measurement_timestamp": 50.25,
            "latest_arrival_timestamp": 50.4,
        },
    }

    summary = summarize_recon_cue_from_tracks([track], coverage_cell="cell-high")

    assert summary.track_count == 1
    assert summary.coverage_cell == "cell-high"
    assert summary.measurement_timestamp == pytest.approx(50.25)
    assert summary.arrival_timestamp == pytest.approx(50.4)
    assert summary.to_dict()["measurement_timestamp"] == pytest.approx(50.25)
    assert summary.to_dict()["arrival_timestamp"] == pytest.approx(50.4)
