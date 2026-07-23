from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    compare_cross_build_episodes,
    render_cross_build_equivalence_markdown,
    write_cross_build_equivalence_bundle,
)


def test_cross_build_audit_accepts_opaque_plan_ids_and_reported_diagnostics(
    tmp_path: Path,
) -> None:
    reference = _write_episode(tmp_path / "reference", plan_id="d3-plan-reference")
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        compact_truth_labels=True,
        innovation_solve_count=17,
    )

    report = compare_cross_build_episodes(reference, candidate)

    assert report["passed"] is True
    assert report["checks"]["normalized_online_payloads_equal"] is True
    assert report["checks"]["reference_plan_lineage_valid"] is True
    assert report["checks"]["candidate_plan_lineage_valid"] is True
    assert report["online_bus"]["lineage_relation_source"] == (
        "derived_from_contiguous_publication_order"
    )
    assert report["truth_artifacts"]["truth_state_equal"] is True
    assert report["allowed_performance_diagnostics"][
        "d1_association_innovation_solve_count"
    ] == {
        "reference_total": 41,
        "candidate_total": 17,
        "semantic_status": "reported_not_compared",
    }
    markdown = render_cross_build_equivalence_markdown(report)
    assert "语义等价审计通过" in markdown
    outputs = write_cross_build_equivalence_bundle(tmp_path / "report", report)
    assert outputs["json"].is_file()
    assert outputs["markdown"].is_file()


def test_cross_build_audit_rejects_guidance_business_change(tmp_path: Path) -> None:
    reference = _write_episode(tmp_path / "reference", plan_id="d3-plan-reference")
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        guidance_acceleration=2.0,
    )

    report = compare_cross_build_episodes(reference, candidate)

    assert report["passed"] is False
    assert report["checks"]["normalized_online_payloads_equal"] is False
    assert any(
        item["topic"] == "modules.d7.guidance_commands"
        and "acceleration_ned_mps2" in item["path"]
        for item in report["online_bus"]["mismatches"]
    )


def test_cross_build_audit_rejects_runtime_profile_change(tmp_path: Path) -> None:
    reference = _write_episode(
        tmp_path / "reference",
        plan_id="d3-plan-reference",
        runtime_profile_sha256="a" * 64,
    )
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        runtime_profile_sha256="b" * 64,
    )

    report = compare_cross_build_episodes(reference, candidate)

    assert report["passed"] is False
    assert report["checks"]["same_runtime_profile"] is False


def test_cross_build_audit_rejects_missing_runtime_profile(tmp_path: Path) -> None:
    reference = _write_episode(
        tmp_path / "reference",
        plan_id="d3-plan-reference",
        runtime_profile_sha256=None,
    )
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        runtime_profile_sha256=None,
    )

    report = compare_cross_build_episodes(reference, candidate)

    assert report["passed"] is False
    assert report["checks"]["same_runtime_profile"] is False


def test_cross_build_audit_fails_closed_on_tampered_ack_hash(tmp_path: Path) -> None:
    reference = _write_episode(tmp_path / "reference", plan_id="d3-plan-reference")
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        tamper_ack_hash=True,
    )

    with pytest.raises(ValueError, match="source plan payload SHA256 mismatch"):
        compare_cross_build_episodes(reference, candidate)


def test_cross_build_audit_fails_closed_on_tampered_d4_advisory_id(
    tmp_path: Path,
) -> None:
    reference = _write_episode(tmp_path / "reference", plan_id="d3-plan-reference")
    candidate = _write_episode(
        tmp_path / "candidate",
        plan_id="d3-plan-candidate",
        tamper_d4_advisory_id=True,
    )

    with pytest.raises(ValueError, match="advisory_id does not match advisory content"):
        compare_cross_build_episodes(reference, candidate)


def _write_episode(
    root: Path,
    *,
    plan_id: str,
    compact_truth_labels: bool = False,
    innovation_solve_count: int = 41,
    guidance_acceleration: float = 1.0,
    tamper_ack_hash: bool = False,
    tamper_d4_advisory_id: bool = False,
    runtime_profile_sha256: str | None = "c" * 64,
) -> Path:
    root.mkdir(parents=True)
    manifest = {
        "episode_id": "equivalence-fixture",
        "git_commit": f"commit-{plan_id}",
        "repository_dirty": False,
        "runtime_profile_sha256": runtime_profile_sha256,
    }
    scenario = {
        "scenario_name": "nominal_2v2",
        "scenario_version": "fixture-v1",
        "duration_s": 1.0,
        "seed": 7,
    }
    summary = {
        "episode_id": "equivalence-fixture",
        "scenario_name": "nominal_2v2",
        "scenario_version": "fixture-v1",
        "seed": 7,
        "target_count": 1,
        "resource_count": 1,
        "recon_count": 0,
        "simulated_duration_s": 1.0,
        "physics_step_count": 20,
        "finite_state": True,
        "online_truth_use_count": 0,
        "online_observation_count": 1,
        "online_batch_count": 1,
        "radar_observation_count": 1,
        "acoustic_observation_count": 0,
        "visual_observation_count": 0,
        "module_publication_count": 5,
        "module_publication_topic_counts": {
            "modules.d1.fused_tracks": 1,
            "modules.d3.assignment_plan": 1,
            "modules.d4.regional_failover": 1,
            "modules.d4.region_resource_advice": 1,
            "modules.d7.guidance_commands": 1,
        },
        "assignment_plan_ack_count": 1,
        "assignment_plan_binding_ack_count": 1,
        "assignment_plan_control_applied_count": 1,
        "assignment_plan_hold_count": 0,
        "camera_command_ack_count": 0,
        "camera_command_applied_count": 0,
        "camera_command_issued_count": 0,
        "camera_command_rejected_count": 0,
        "camera_command_rejection_reason_counts": {},
        "intercepted_target_count": 0,
        "wall_time_s": 99.0 if "candidate" in plan_id else 101.0,
        "module_final_diagnostics": {
            "d1_track_count": 1,
            "d2_track_count": 1,
            "d3_assignment_count": 1,
            "d5_binding_count": 1,
            "d7_command_count": 1,
        },
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "scenario_config.json", scenario)
    _write_json(root / "summary.json", summary)
    np.savez_compressed(
        root / "offline_truth_state.npz",
        timestamps=np.asarray([0.0, 1.0]),
        intruders=np.asarray([[[1.0, 2.0, -3.0]], [[2.0, 2.0, -3.0]]]),
        intruder_ids=np.asarray(["TGT-0001"]),
    )
    truth_label = {
        "schema_version": "scalable3d-offline-truth-v1",
        "observation_id": "radar-1",
        "measurement_timestamp": 0.0,
        "truth_entity_id": "TGT-0001",
    }
    separators = (",", ":") if compact_truth_labels else None
    (root / "offline_truth_labels.jsonl").write_text(
        json.dumps(truth_label, separators=separators) + "\n", encoding="utf-8"
    )
    (root / "offline_proximity_intercepts.jsonl").write_text("", encoding="utf-8")

    records = _online_records(
        plan_id=plan_id,
        innovation_solve_count=innovation_solve_count,
        guidance_acceleration=guidance_acceleration,
    )
    plan_payload = records[1]["payload"]
    guidance_payload = records[4]["payload"]
    ack = records[5]["payload"]
    ack["source_plan_payload_sha256"] = _canonical_sha256(plan_payload)
    ack["source_guidance_payload_sha256"] = _canonical_sha256(guidance_payload)
    if tamper_ack_hash:
        ack["source_plan_payload_sha256"] = "0" * 64
    if tamper_d4_advisory_id:
        records[3]["payload"]["advisory_contract"]["advisory_id"] = (
            "d4-rr-advisory-" + "0" * 64
        )
    with (root / "online_observations.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            stream.write("\n")
    return root


def _online_records(
    *,
    plan_id: str,
    innovation_solve_count: int,
    guidance_acceleration: float,
) -> list[dict[str, object]]:
    assignment = {
        "resource_id": "INT-0001",
        "global_track_id": "GT3D-000001",
        "coalition_id": "coalition-1",
        "coalition_version": 1,
        "member_role": "primary",
    }
    plan_payload = {
        "plan_id": plan_id,
        "plan_version": 1,
        "created_at": 0.5,
        "assignment_count": 1,
        "assignments": [assignment],
        "metadata": {"active_plan_owner": "center", "previous_plan_id": None},
    }
    formal_decision_payload = {
        "schema": "d4-regional-failover-v1",
        "timestamp_s": 0.5,
        "regions": [
            {
                "region_id": "region-000",
                "action": "continue_center",
                "ownership": {
                    "owner_id": "d3_central",
                    "owner_layer": "center",
                    "plan_id": plan_id,
                    "plan_version": 1,
                    "epoch": 1,
                },
            }
        ],
    }
    source_version = {
        "region_id": "region-000",
        "snapshot_id": "fixture-snapshot-p1-t0.500000",
        "snapshot_version": 1,
        "authority_digest": "",
        "owner_id": "d3_central",
        "owner_layer": "center",
        "plan_id": plan_id,
        "plan_version": 1,
        "epoch": 1,
        "lease_expires_at_s": 3.5,
        "coalition_ack_complete": True,
        "owner_active": True,
        "fault_fenced": False,
        "fault_fence_epoch": None,
    }
    authority_payload = [
        {
            "region_id": "region-000",
            "owner_id": "d3_central",
            "owner_layer": "center",
            "plan_id": plan_id,
            "plan_version": 1,
            "epoch": 1,
            "lease_expires_at_s": 3.5,
            "owner_active": True,
            "coalition_ack_complete": True,
            "committed_resources": 1,
            "fault_fenced": False,
            "fault_fence_epoch": None,
        }
    ]
    authority_digest = _canonical_sha256_ascii(authority_payload)
    source_version["authority_digest"] = authority_digest
    advisory_contract = {
        "advisory_id": "",
        "schema": "d4-region-resource-advisory-v1",
        "snapshot_id": "fixture-snapshot-p1-t0.500000",
        "snapshot_version": 1,
        "snapshot_timestamp_s": 0.5,
        "scenario_id": "nominal_2v2",
        "scenario_version": "fixture-v1",
        "seed": 7,
        "authority_digest": authority_digest,
        "created_at_s": 0.5,
        "valid_from_s": 0.5,
        "valid_until_s": 2.0,
        "source_plan_versions": [[plan_id, 1]],
        "regions": [
            {
                "source_version": source_version,
                "resources_before": 1,
                "resource_quota_delta": 0,
                "resources_after": 1,
                "protected_reserve_resources": 0,
                "protected_committed_resources": 1,
                "reserve_ratio": 0.0,
                "reconnaissance_priority": 1.0,
                "hold": False,
                "request_replan": False,
                "reasons": [],
            }
        ],
        "transfers": [],
    }
    advisory_unhashed = deepcopy(advisory_contract)
    advisory_unhashed.pop("advisory_id")
    advisory_contract["advisory_id"] = (
        "d4-rr-advisory-" + _canonical_sha256_ascii(advisory_unhashed)
    )
    decision_digest = _canonical_sha256_ascii(formal_decision_payload)
    advice_payload = {
        "formal_decision_unchanged": True,
        "formal_decision_digest_before": decision_digest,
        "formal_decision_digest_after": decision_digest,
        "advisory_contract": advisory_contract,
        "recommendation": {"authority_digest": authority_digest, "quota": 1},
    }
    guidance_payload = {
        "timestamp": 0.5,
        "command_count": 1,
        "commands": [
            {
                "resource_id": "INT-0001",
                "global_track_id": "GT3D-000001",
                "plan_id": plan_id,
                "plan_version": 1,
                "acceleration_ned_mps2": [guidance_acceleration, 0.0, 0.0],
                "mode": "midcourse_pn_3d",
            }
        ],
    }
    return [
        _record(
            1,
            "modules.d1.fused_tracks",
            {
                "tracks": [{"global_track_id": "GT3D-000001"}],
                "summary": {
                    "association_innovation_solve_count": innovation_solve_count
                },
            },
        ),
        _record(2, "modules.d3.assignment_plan", plan_payload),
        _record(3, "modules.d4.regional_failover", formal_decision_payload),
        _record(4, "modules.d4.region_resource_advice", advice_payload),
        _record(5, "modules.d7.guidance_commands", guidance_payload),
        _record(
            6,
            "runtime.assignment_plan_ack",
            {
                "plan_id": plan_id,
                "plan_version": 1,
                "decision_id": f"{plan_id}:v1",
                "source_plan_bus_sequence": 2,
                "source_plan_payload_sha256": "",
                "source_guidance_bus_sequence": 5,
                "source_guidance_payload_sha256": "",
                "accepted": True,
            },
        ),
    ]


def _record(sequence: int, topic: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "fixture-v1",
        "sequence": sequence,
        "source": "fixture",
        "timestamp": 0.5,
        "topic": topic,
        "payload": deepcopy(payload),
    }


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _canonical_sha256_ascii(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
