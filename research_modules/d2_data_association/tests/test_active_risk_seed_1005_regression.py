from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.module_stack import IntegratedStackConfig
from research_modules.scalable_3d_simulation.orchestrator import (
    Scalable3DEpisodeRunner,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    ReservedSeedInterventionOptions,
    _make_intervention_scenario,
)
from research_modules.d2_data_association.scripts.reproduce_active_risk_seed_1005 import (
    reproduce,
)


def test_active_risk_seed_1005_stale_d1_posterior_cannot_confirm_duplicate() -> None:
    options = ReservedSeedInterventionOptions(
        scenario="nominal",
        scale=5,
        duration_s=1.1,
        intervention_kind="active_risk",
    )
    config = _make_intervention_scenario(options, seed=1005)
    resolved = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(),
        stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
    )
    episode = Scalable3DEpisodeRunner(
        resolved.config,
        module_stack=resolved.stack,
    ).run()
    publications = [
        message
        for message in episode.online_messages
        if message.topic == "modules.d2.associated_tracks"
    ]

    assert publications
    assert all(item.payload["track_count"] == 5 for item in publications)
    assert [
        item["global_track_id"] for item in publications[-1].payload["tracks"]
    ] == [
        "GT3D-000001",
        "GT3D-000002",
        "GT3D-000003",
        "GT3D-000004",
        "GT3D-000005",
    ]
    assert all(
        item["track_state"] == "confirmed"
        for item in publications[-1].payload["tracks"]
    )
    assert all(item.payload["id_switch_count"] is None for item in publications)
    assert all(
        item.payload["id_switch_count_available"] is False
        for item in publications
    )
    assert all(
        item.payload["association"]["observation_evidence_governance"][
            "global_track_id_owner"
        ]
        == "D2_center"
        for item in publications
    )
    summary = resolved.stack.d2.summary()
    assert summary["replay_quarantine_count"] >= 0
    assert summary["replay_coast_count"] == summary["replay_quarantine_count"]
    expected_replay_reason_counts = (
        {}
        if summary["replay_quarantine_count"] == 0
        else {
            "repeated_latest_observation_id": summary[
                "replay_quarantine_count"
            ]
        }
    )
    assert summary["replay_coast_reason_counts"] == expected_replay_reason_counts
    assert summary["birth_count"] == 5
    assert summary["tentative_stale_drop_count"] == 0
    assert summary["duplicate_coalescence_count"] == 0
    assert summary["active_track_count"] == 5
    assert episode.summary["online_truth_use_count"] == 0
    assert "TGT-" not in json.dumps(
        [item.payload for item in publications],
        sort_keys=True,
    )


def test_active_risk_reproduction_script_uses_current_acceptance_profile() -> None:
    report = reproduce(duration_s=2.2)

    assert report["schema_version"] == "d2.active-risk-seed1005-reproduction.v3"
    assert report["acceptance_profile"] == (
        "canonical_five_tracks_with_optional_bounded_replay_v3"
    )
    assert report["acceptance_passed"] is True
    assert report["all_frame_ids_are_canonical"] is True
    assert report["all_frames_center_owned"] is True
    assert set(report["publication_track_counts"]) == {5}
    assert report["birth_count"] == 5
    assert report["active_track_count"] == 5
    assert report["replay_quarantine_count"] >= 0
    assert report["replay_coast_count"] == report["replay_quarantine_count"]
    assert report["replay_audit_consistent"] is True
    assert report["tentative_stale_drop_count"] == 0
    assert report["duplicate_coalescence_count"] == 0
    assert report["online_truth_use_count"] == 0
