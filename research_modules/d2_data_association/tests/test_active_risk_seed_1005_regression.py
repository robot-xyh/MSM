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

    assert [item.payload["track_count"] for item in publications[:4]] == [
        5,
        6,
        6,
        5,
    ]
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
    summary = resolved.stack.d2.summary()
    assert summary["replay_quarantine_count"] >= 2
    assert summary["tentative_stale_drop_count"] == 1
    assert summary["active_track_count"] == 5
    assert episode.summary["online_truth_use_count"] == 0
    assert "TGT-" not in json.dumps(
        [item.payload for item in publications],
        sort_keys=True,
    )
