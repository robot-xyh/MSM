from __future__ import annotations

import json
from pathlib import Path

from research_modules.scalable_3d_simulation.identity_commitment_gate import (
    compare_identity_commitment_gate,
    render_identity_commitment_gate_markdown,
    write_identity_commitment_gate_bundle,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _d3_plan(
    *,
    timestamp: float,
    version: int,
    target_ids: tuple[str, ...],
    rejected_target_ids: tuple[str, ...] = (),
    forced_replan: bool = False,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "topic": "modules.d3.assignment_plan",
        "payload": {
            "timestamp": timestamp,
            "plan_version": version,
            "assignment_count": len(target_ids),
            "assignments": [
                {
                    "resource_id": f"INT-{index:02d}",
                    "global_track_id": target_id,
                }
                for index, target_id in enumerate(target_ids, start=1)
            ],
            "metadata": {
                "identity_commitment_forced_replan": forced_replan,
                "identity_commitment_replan_reason": (
                    "previous_target_identity_uncommitted"
                    if forced_replan
                    else None
                ),
                "identity_commitment_hysteresis_bypassed": forced_replan,
                "identity_commitment_rejected_target_ids": list(
                    rejected_target_ids
                ),
            },
        },
    }


def _episode(
    root: Path,
    *,
    runtime_profile: str,
    include_d7_violation: bool = False,
) -> Path:
    root.mkdir(parents=True)
    _write_json(
        root / "manifest.json",
        {
            "episode_id": root.name,
            "git_commit": "abc123",
            "repository_dirty": False,
            "scenario_version": "200v200-test-v1",
            "seed": 1100,
            "config_sha256": "config-sha",
            "runtime_profile_sha256": runtime_profile,
        },
    )
    _write_json(
        root / "summary.json",
        {
            "resource_count": 200,
            "target_count": 200,
            "recon_count": 2,
            "simulated_duration_s": 2.2,
            "finite_state": True,
            "online_truth_use_count": 0,
            "real_time_factor": 0.2,
            "module_final_diagnostics": {
                "d1_track_count": 202,
                "d2_track_count": 201,
                "d3_assignment_count": 2,
                "d3_identity_commitment_binding_hold_count": 1,
                "d3_identity_commitment_binding_hold_event_count": 1,
                "d1_fusion_association": {
                    "neutral_centroid_candidate_component_count": 2,
                    "neutral_centroid_applied_component_count": 0,
                    "neutral_centroid_applied_member_count": 0,
                    "neutral_centroid_rejected_component_count": 2,
                    "neutral_centroid_rejection_reasons": {
                        "oosm_scan": 1,
                        "unbalanced_component": 1,
                    },
                    "max_neutral_centroid_translation_m": 0.0,
                },
            },
        },
    )
    _write_json(
        root / "offline_identity" / "identity_evaluation.json",
        {
            "metrics": {
                "id_switch_count": 3,
                "id_switch_count_available": True,
                "track_continuity": 0.82,
                "track_continuity_available": True,
                "coverage_continuity": 0.83,
                "coverage_continuity_available": True,
                "duplicate_assignment_count": 0,
            },
            "audit": {
                "available_mapping_count": 1491,
                "unavailable_mapping_count": 218,
                "uncommitted_mapping_count": 76,
                "identity_commitment_coverage": 0.95,
                "uncommitted_source_binding_violation_count": 0,
                "uncommitted_candidate_binding_violation_count": 0,
                "online_truth_isolation_verified": True,
            },
        },
    )
    messages = [
        _d3_plan(
            timestamp=0.75,
            version=1,
            target_ids=("G-1", "G-2", "G-3"),
        ),
        _d3_plan(
            timestamp=1.0,
            version=2,
            target_ids=("G-1", "G-2"),
            rejected_target_ids=("G-3",),
            forced_replan=True,
        ),
        {
            "timestamp": 1.0,
            "topic": "modules.d5.active_vision",
            "payload": {
                "commands": [{"target_global_track_id": "G-1"}],
            },
        },
        {
            "timestamp": 1.05,
            "topic": "modules.d5.terminal_association",
            "payload": {"bindings": [{"global_track_id": "G-2"}]},
        },
        {
            "timestamp": 1.0,
            "topic": "modules.d7.guidance_commands",
            "payload": {
                "commands": [
                    {
                        "global_track_id": (
                            "G-3" if include_d7_violation else "G-1"
                        )
                    }
                ]
            },
        },
        _d3_plan(
            timestamp=2.0,
            version=3,
            target_ids=("G-1", "G-2"),
            rejected_target_ids=("G-3",),
        ),
    ]
    (root / "online_observations.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in messages
        ),
        encoding="utf-8",
    )
    (root / "offline_truth_labels.jsonl").write_text(
        '{"truth":"same"}\n',
        encoding="utf-8",
    )
    (root / "offline_truth_state.npz").write_bytes(b"same-state")
    return root


def test_clean_pair_passes_contract_but_does_not_promote_algorithm(
    tmp_path: Path,
) -> None:
    control = _episode(tmp_path / "control", runtime_profile="control")
    candidate = _episode(
        tmp_path / "candidate",
        runtime_profile="candidate",
    )

    report = compare_identity_commitment_gate(control, candidate)

    assert report["passed"] is True
    assert report["contract_gate_passed"] is True
    assert report["algorithm_promotion_allowed"] is False
    assert report["algorithm_promotion_reason"] == "zero_effective_treatment"
    assert report["control"]["forced_replan"]["plan_version"] == 2
    assert report["control"]["downstream_violations"] == {
        "d3_assignments": (),
        "d5_active_vision": (),
        "d5_terminal_bindings": (),
        "d7_guidance": (),
    }
    markdown = render_identity_commitment_gate_markdown(report)
    assert "身份承诺下游准入复核" in markdown
    assert "算法晋级：`不允许`" in markdown

    paths = write_identity_commitment_gate_bundle(
        tmp_path / "report",
        report,
    )
    assert paths["json"].is_file()
    assert paths["markdown"].is_file()


def test_uncommitted_d7_continuation_fails_contract_gate(
    tmp_path: Path,
) -> None:
    control = _episode(tmp_path / "control", runtime_profile="control")
    candidate = _episode(
        tmp_path / "candidate",
        runtime_profile="candidate",
        include_d7_violation=True,
    )

    report = compare_identity_commitment_gate(control, candidate)

    assert report["passed"] is False
    assert "candidate:d7_guidance_continued_for_uncommitted_target" in (
        report["violations"]
    )
    assert "本次审计未通过下游安全合同" in (
        render_identity_commitment_gate_markdown(report)
    )
