from __future__ import annotations

import json
from pathlib import Path
import threading
import time

import pytest

from dual_optical_40target.core import RayObservation
from dual_optical_online_benchmark.contracts import BenchmarkProtocol
import dual_optical_online_benchmark.tracker_calibration as calibration_module
from dual_optical_online_benchmark.tracker_calibration import (
    PREPARATION_POLICY_VERSION,
    PREPARED_TRACKER_CACHE_SCHEMA,
    VALIDATION_RUNTIME_MEASUREMENT_POLICY,
    PreparedTrackerEpisode,
    _acceptance,
    _evaluate_candidate_grid,
    _load_prepared_cache,
    _prepared_cache_path,
    _select_candidate,
    _write_prepared_cache,
)
from dual_optical_online_benchmark.tracking import (
    BearingScanlet,
    SharedTrackerConfig,
)


def _candidate(
    *,
    name: str,
    purity: float,
    light: float,
    medium: float,
    heavy: float,
) -> dict:
    return {
        "name": name,
        "config": {"chi2_confidence": 0.99},
        "validation": {
            "median_track_purity": purity,
            "by_corruption_level": {
                "light": {
                    "mean_common_confirmed_rate": light,
                    "mean_fragments_per_real_identity": 1.1,
                },
                "medium": {
                    "mean_common_confirmed_rate": medium,
                    "mean_fragments_per_real_identity": 1.1,
                },
                "heavy": {
                    "mean_common_confirmed_rate": heavy,
                    "mean_fragments_per_real_identity": 1.1,
                },
            },
        },
    }


def test_tracker_selection_ranks_only_within_accepted_candidates() -> None:
    passing = _candidate(
        name="passing",
        purity=0.875,
        light=0.7183,
        medium=0.7000,
        heavy=0.6233,
    )
    failing = _candidate(
        name="failing_but_higher_worst_rate",
        purity=1.0,
        light=0.6883,
        medium=0.6883,
        heavy=0.6433,
    )

    selected, accepted_count = _select_candidate((failing, passing))

    assert accepted_count == 1
    assert selected["name"] == "passing"


def test_tracker_selection_still_returns_diagnostics_when_none_pass() -> None:
    first = _candidate(
        name="first",
        purity=0.90,
        light=0.60,
        medium=0.60,
        heavy=0.60,
    )
    second = _candidate(
        name="best_failed_candidate",
        purity=0.90,
        light=0.69,
        medium=0.69,
        heavy=0.65,
    )

    selected, accepted_count = _select_candidate((first, second))

    assert accepted_count == 0
    assert selected["name"] == "best_failed_candidate"


def test_continuity_acceptance_enforces_reactivation_fragmentation_and_runtime() -> None:
    validation = _candidate(
        name="candidate",
        purity=0.90,
        light=0.75,
        medium=0.72,
        heavy=0.55,
    )["validation"]
    validation.update({
        "false_reactivation_rate": 0.006,
        "baseline_false_reactivation_rate": 0.004,
        "mean_fragments_per_real_identity": 1.2,
        "baseline_mean_fragments_per_real_identity": 1.1,
        "sweep_runtime_p95_ms": 251.0,
    })

    acceptance = _acceptance(validation)

    assert acceptance["accepted"] is False
    assert set(acceptance["failure_reasons"]) >= {
        "false_reactivation_rate_absolute",
        "false_reactivation_rate_not_above_baseline",
        "fragmentation_not_above_baseline",
        "sweep_runtime_p95_ms",
    }


def _prepared(
    seed: int,
    split: str = "train",
    *,
    corruption_level: str = "light",
    episode_dir: str = "",
) -> PreparedTrackerEpisode:
    observation = RayObservation(
        detection_uid=f"anonymous-{seed}",
        camera_id="Optical_A",
        frame_index=0,
        timestamp=0.5,
        origin_ned=(0.0, -1000.0, -100.0),
        direction_ned=(1.0, 0.0, 0.0),
        bbox_xyxy=(0.0, 0.0, 1.0, 1.0),
        sweep_index=0,
        camera_yaw_deg=0.0,
        camera_pitch_deg=0.0,
        focal_length_px=25000.0,
    )
    scanlet = BearingScanlet(
        camera_id="Optical_A",
        sweep_index=0,
        timestamp=0.5,
        origin_ned=observation.origin_ned,
        direction_ned=observation.direction_ned,
        detection_uids=(observation.detection_uid,),
        bbox_area_px2=1.0,
        confidence=1.0,
        measurement_covariance_deg2=(0.001, 0.0, 0.0, 0.001),
    )
    return PreparedTrackerEpisode(
        seed=seed,
        split=split,
        corruption_level=corruption_level,
        camera_ids=("Optical_A", "Optical_B"),
        observations={("Optical_A", 0): (observation,)},
        confidence_by_uid={observation.detection_uid: 1.0},
        scanlets={("Optical_A", 0): (scanlet,)},
        scanlet_preparation_fingerprint=(
            SharedTrackerConfig().scanlet_preparation_fingerprint
        ),
        episode_dir=episode_dir,
    )


def _cache_metadata(source_hash: str = "a" * 64) -> dict:
    return {
        "schema_version": PREPARED_TRACKER_CACHE_SCHEMA,
        "preparation_policy_version": PREPARATION_POLICY_VERSION,
        "protocol_fingerprint": "protocol-fingerprint",
        "raw_source_sha256": {"detections": source_hash},
        "seed": 101,
        "split": "train",
        "split_override": None,
        "corruption_level": "light",
        "expected_gimbal_pose_error": True,
        "scanlet_preparation_fingerprint": (
            SharedTrackerConfig().scanlet_preparation_fingerprint
        ),
    }


def test_prepared_cache_hits_only_after_hash_and_policy_validation(tmp_path) -> None:
    metadata = _cache_metadata()
    path = _prepared_cache_path(tmp_path, metadata)
    _write_prepared_cache(path, metadata, _prepared(101))

    loaded = _load_prepared_cache(path, metadata)

    assert loaded.cache_status == "hit"
    assert loaded.cache_key
    assert loaded.observations[("Optical_A", 0)][0].detection_uid == "anonymous-101"
    assert loaded.scanlets is not None
    assert not hasattr(loaded, "uid_truth")
    assert not hasattr(loaded, "observed_real")


def test_prepared_cache_contains_anonymous_online_data_only(tmp_path) -> None:
    metadata = _cache_metadata()
    path = _prepared_cache_path(tmp_path, metadata)
    _write_prepared_cache(path, metadata, _prepared(101))

    text = path.read_text(encoding="utf-8")

    assert "online_anonymous" in text
    assert "offline_scoring_labels" not in text
    assert "truth_id" not in text
    assert "actor_name" not in text
    assert "TARGET-REAL-001" not in text
    assert "DroneTarget_001" not in text


def test_detection_truth_is_opened_only_after_all_tracker_updates(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "episode"
    label_path = root / "truth" / "detection_truth.csv"
    label_path.parent.mkdir(parents=True)
    label_path.write_text(
        "detection_uid,truth_id\nanonymous-101,TARGET-REAL-001\n",
        encoding="utf-8",
    )
    protocol = BenchmarkProtocol()
    update_count = 0
    accesses: list[tuple[str, int]] = []
    original_update = calibration_module.SharedBearingTracker.update_scanlets
    original_read_csv = calibration_module._read_csv

    def recording_update(self, sweep_index, scanlets):
        nonlocal update_count
        result = original_update(self, sweep_index, scanlets)
        update_count += 1
        accesses.append(("tracker_update", update_count))
        return result

    def recording_read_csv(path: Path):
        if path.name == "detection_truth.csv":
            accesses.append(("detection_truth_open", update_count))
        return original_read_csv(path)

    monkeypatch.setattr(
        calibration_module.SharedBearingTracker,
        "update_scanlets",
        recording_update,
    )
    monkeypatch.setattr(calibration_module, "_read_csv", recording_read_csv)

    result = calibration_module.evaluate_prepared_tracker_episode(
        _prepared(
            101,
            corruption_level="none",
            episode_dir=str(root),
        ),
        protocol,
        SharedTrackerConfig(),
    )

    expected_updates = len(("Optical_A", "Optical_B")) * protocol.revolution_count
    truth_accesses = [item for item in accesses if item[0] == "detection_truth_open"]
    assert update_count == expected_updates
    assert truth_accesses == [("detection_truth_open", expected_updates)]
    assert accesses[-1] == truth_accesses[0]
    assert result["online_truth_used"] is False
    assert result["truth_opened_after_tracking"] is True


def test_prepared_cache_invalidates_on_source_hash_or_content_change(tmp_path) -> None:
    metadata = _cache_metadata()
    path = _prepared_cache_path(tmp_path, metadata)
    _write_prepared_cache(path, metadata, _prepared(101))

    with pytest.raises(ValueError, match="metadata mismatch"):
        _load_prepared_cache(path, _cache_metadata("b" * 64))

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["content"]["online_anonymous"]["seed"] = 999
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash mismatch"):
        _load_prepared_cache(path, metadata)


def _fake_tracker_row(prepared, protocol, config):
    del protocol
    time.sleep(0.002 * (4 - prepared.seed))
    return {
        "seed": prepared.seed,
        "split": prepared.split,
        "corruption_level": prepared.corruption_level,
        "median_track_purity": 0.90,
        "common_confirmed_rate": 0.75,
        "mean_fragments_per_real_identity": 1.0,
        "reactivation_count": 1,
        "false_reactivation_count": 0,
        "false_reactivation_rate": 0.0,
        "sweep_runtime_p95_ms": float(config.chi2_gate),
    }


def test_parallel_candidate_replay_preserves_serial_grid_order(monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_module,
        "evaluate_prepared_tracker_episode",
        _fake_tracker_row,
    )
    prepared = (_prepared(1), _prepared(2), _prepared(3, "validation"))
    configs = (
        SharedTrackerConfig(),
        SharedTrackerConfig(chi2_confidence=0.995),
    )

    serial = _evaluate_candidate_grid(
        prepared, BenchmarkProtocol(), configs, max_workers=1
    )
    parallel = _evaluate_candidate_grid(
        prepared, BenchmarkProtocol(), configs, max_workers=4
    )

    assert [row["seed"] for row in parallel[0]["rows"]] == [1, 2, 3]
    assert [item["tracker_fingerprint"] for item in parallel] == [
        config.fingerprint for config in configs
    ]
    assert parallel == serial


def test_parallel_quality_replay_uses_isolated_validation_latency(
    monkeypatch,
) -> None:
    active = 0
    lock = threading.Lock()

    def contention_sensitive_row(prepared, protocol, config):
        del protocol
        nonlocal active
        with lock:
            active += 1
            contended = active > 1
        time.sleep(0.01)
        with lock:
            active -= 1
        return {
            "seed": prepared.seed,
            "split": prepared.split,
            "corruption_level": prepared.corruption_level,
            "median_track_purity": 0.90,
            "common_confirmed_rate": 0.75,
            "mean_fragments_per_real_identity": 1.0,
            "reactivation_count": 1,
            "false_reactivation_count": 0,
            "false_reactivation_rate": 0.0,
            "sweep_runtime_p95_ms": 1000.0 if contended else 100.0,
            "online_truth_used": False,
            "truth_opened_after_tracking": True,
            "config_gate": float(config.chi2_gate),
        }

    monkeypatch.setattr(
        calibration_module,
        "evaluate_prepared_tracker_episode",
        contention_sensitive_row,
    )
    protocol = BenchmarkProtocol()
    prepared = (
        _prepared(1, "train", corruption_level="light"),
        _prepared(3, "validation", corruption_level="light"),
    )
    configs = (
        SharedTrackerConfig(),
        SharedTrackerConfig(chi2_confidence=0.995),
    )

    candidates = _evaluate_candidate_grid(
        prepared, protocol, configs, max_workers=4
    )

    for candidate in candidates:
        assert candidate["validation"]["sweep_runtime_p95_ms"] == 100.0
        validation_rows = [
            row for row in candidate["rows"] if row["split"] == "validation"
        ]
        assert validation_rows
        assert all(
            row["runtime_measurement_policy"]
            == VALIDATION_RUNTIME_MEASUREMENT_POLICY
            for row in validation_rows
        )


def test_parallel_candidate_replay_propagates_worker_failure(monkeypatch) -> None:
    def fail_on_second(prepared, protocol, config):
        del protocol, config
        if prepared.seed == 2:
            raise RuntimeError("candidate replay failed")
        return _fake_tracker_row(prepared, BenchmarkProtocol(), SharedTrackerConfig())

    monkeypatch.setattr(
        calibration_module,
        "evaluate_prepared_tracker_episode",
        fail_on_second,
    )
    with pytest.raises(RuntimeError, match="candidate replay failed"):
        _evaluate_candidate_grid(
            (_prepared(1), _prepared(2)),
            BenchmarkProtocol(),
            (SharedTrackerConfig(),),
            max_workers=4,
        )


@pytest.mark.parametrize("workers", [0, 5])
def test_parallel_candidate_replay_rejects_unsafe_worker_counts(workers: int) -> None:
    with pytest.raises(ValueError, match="one to four workers"):
        _evaluate_candidate_grid(
            (_prepared(1),),
            BenchmarkProtocol(),
            (SharedTrackerConfig(),),
            max_workers=workers,
        )
