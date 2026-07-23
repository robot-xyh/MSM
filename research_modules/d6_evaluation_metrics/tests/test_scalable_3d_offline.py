from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from d6_evaluation_metrics.scalable_3d_offline import (
    EXPERIMENT_MATRIX_SCHEMA_VERSION,
    EXPERIMENT_MATRIX_VARIANTS,
    SCALABLE_3D_CURRENT_SCHEMA_REGISTRY,
    SCALABLE_3D_OFFLINE_EVALUATION_DATE,
    SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION,
    SCALABLE_3D_SCHEMA_REGISTRY_VERSION,
    Scalable3DOfflineEvaluationInputs,
    Scalable3DOfflineReportGenerator,
    aggregate_scalable_3d_episodes,
    discover_scalable_3d_episode_dirs,
    evaluate_scalable_3d_episode,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _write_sidecar_manifests(episode: Path) -> None:
    for name in (
        "d6_truth_isolated",
        "offline_identity",
        "offline_consistency",
        "observation_governance",
    ):
        sidecar = episode / name
        sidecar.mkdir()
        _write_json(sidecar / "manifest.json", {"schema_version": f"{name}-v1"})


def _track(index: int, *, speed_offset: float = 0.0) -> dict[str, object]:
    covariance = [[0.0] * 6 for _ in range(6)]
    for axis in range(6):
        covariance[axis][axis] = float(axis + 1 + index / 100.0)
    return {
        "global_track_id": f"GT-{index + 1:04d}",
        "timestamp": 0.8,
        "state_ned": [
            float(index),
            0.0,
            -100.0,
            speed_offset + float(index + 1),
            0.0,
            0.0,
        ],
        "covariance": covariance,
        "track_state": "confirmed",
    }


def _envelope(
    sequence: int,
    topic: str,
    timestamp: float,
    payload: dict[str, object],
    *,
    schema_version: str | None = None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": topic.split(".")[1].upper() if topic.startswith("modules.") else "SENSOR",
        "timestamp": timestamp,
        "schema_version": schema_version or f"fixture-{topic.replace('.', '-')}-v1",
        "payload": payload,
    }


def _learning_runtime(profile: str) -> tuple[dict[str, object], dict[str, str]]:
    fingerprints = {
        "d3": "a" * 64,
        "d4": "b" * 64,
        "d5": "c" * 64,
    }
    versions = {
        "d3_policy_version": "d3-scalable3d-rule-cost-v1",
        "d4_policy_version": "d4-region-resource-rule-v1",
        "d5_model_version": "d5-scalable3d-geometry-rule-v1",
    }
    modules: dict[str, dict[str, object]] = {
        "d3": {
            "requested_mode": "disabled",
            "effective_mode": "disabled",
            "bundle_requested": False,
            "bundle_loaded": False,
            "fallback_reason": None,
            "model_fingerprint": None,
        },
        "d4": {
            "requested_mode": "disabled",
            "effective_mode": "disabled",
            "bundle_requested": False,
            "bundle_loaded": False,
            "fallback_reason": None,
            "model_fingerprint": None,
            "formal_unseen_seed_count": 0,
        },
        "d5": {
            "requested_mode": "disabled",
            "effective_mode": "disabled",
            "bundle_requested": False,
            "bundle_loaded": False,
            "fallback_reason": None,
            "model_fingerprint": None,
        },
    }
    if profile == "missing_bundle":
        modules["d3"].update(
            requested_mode="shadow",
            effective_mode="rule_fallback",
            bundle_requested=True,
            fallback_reason="model_bundle_missing",
        )
        modules["d4"].update(
            requested_mode="assist",
            effective_mode="pending_runtime_shadow_gate",
            bundle_requested=True,
            fallback_reason="model_bundle_missing",
        )
        modules["d5"].update(
            requested_mode="assist",
            effective_mode="rule_fallback",
            bundle_requested=True,
            fallback_reason="bundle_missing",
        )
    elif profile == "assist_shadow":
        modules["d3"].update(
            requested_mode="shadow",
            effective_mode="shadow",
            bundle_requested=True,
            bundle_loaded=True,
            model_fingerprint=fingerprints["d3"],
        )
        modules["d4"].update(
            requested_mode="assist",
            effective_mode="pending_runtime_shadow_gate",
            bundle_requested=True,
            bundle_loaded=True,
            model_fingerprint=fingerprints["d4"],
        )
        modules["d5"].update(
            requested_mode="assist",
            effective_mode="assist",
            bundle_requested=True,
            bundle_loaded=True,
            model_fingerprint=fingerprints["d5"],
        )
        versions = {
            "d3_policy_version": f"d3-shared-edge-v1+{fingerprints['d3'][:12]}",
            "d4_policy_version": f"d4-region-graph-v1+{fingerprints['d4'][:12]}",
            "d5_model_version": f"d5-crossview-gnn-v1.0.0+{fingerprints['d5'][:12]}",
        }
    elif profile != "disabled":
        raise ValueError(f"unsupported learning fixture profile: {profile}")
    return (
        {
            "schema_version": "scalable3d-learning-runtime-v1",
            "device": "cpu",
            **modules,
            "default_rule_path_preserved": True,
        },
        versions,
    )


def _d3_payload(
    *,
    target_count: int,
    assignment_count: int,
    metadata: dict[str, object] | None = None,
    learning_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    assignments = [
        {
            "resource_id": f"INT-{index + 1:04d}",
            "global_track_id": f"GT-{index + 1:04d}",
            "coalition_id": None,
            "coalition_version": None,
            "member_role": "primary",
            "owner_node_id": "C2-CENTER",
            "regional_owner_layer": "center",
            "regional_region_id": "region-000",
            "regional_epoch": 1,
            "regional_commit_mode": "single_member_authorized",
        }
        for index in range(assignment_count)
    ]
    resolved_metadata = dict(
        metadata
        or {
            "hysteresis_state": "unchanged",
            "hysteresis_reason": "same_assignment",
            "hysteresis_reasons": ["same_assignment"],
            "hysteresis_dwell_time_s": 0.8,
            "hysteresis_min_dwell_s": 2.0,
            "hysteresis_dwell_ok": True,
        }
    )
    if learning_metadata is not None:
        resolved_metadata.update(learning_metadata)
    return {
        "timestamp": 0.8,
        "plan_id": "PLAN-0001",
        "plan_version": 1,
        "created_at": 0.2,
        "assignment_count": assignment_count,
        "target_count": target_count,
        "resource_count": max(target_count, assignment_count),
        "assignments": assignments,
        "unassigned_global_track_ids": [],
        "solver_name": "fixture_sparse_solver",
        "metadata": resolved_metadata,
    }


def _d4_payload(*, timestamp: float, lease: float, fail_closed: bool) -> dict[str, object]:
    reason = "regional_d4_authority_lease_expired" if fail_closed else "center_authorized"
    return {
        "schema": "d4-regional-failover-v1",
        "timestamp_s": timestamp,
        "scenario": {
            "node_count": 55,
            "resource_count": 50,
            "recon_count": 4,
            "region_count": 1,
            "task_count": 50,
        },
        "summary": {
            "node_count": 55,
            "resource_count": 50,
            "recon_count": 4,
            "region_count": 1,
            "task_count": 50,
            "execution_allowed_region_count": 0 if fail_closed else 1,
            "fail_closed_region_count": 1 if fail_closed else 0,
            "selected_layer_counts": {"center": 1},
        },
        "regions": [
            {
                "region_id": "region-000",
                "selected_layer": "center",
                "action": "hold" if fail_closed else "continue",
                "reason": reason,
                "ownership": {
                    "region_id": "region-000",
                    "owner_id": "C2-CENTER",
                    "owner_layer": "center",
                    "owner_role": "primary_center",
                    "plan_id": "PLAN-0001",
                    "plan_version": 1,
                    "epoch": 3,
                    "lease_expires_at_s": lease,
                    "active": not fail_closed,
                    "task_ids": ["task:GT-0001"],
                },
                "execution_allowed": not fail_closed,
                "fail_closed": fail_closed,
                "risk_factors": [],
                "task_ids": ["task:GT-0001"],
                "secondary_candidate_ids": [],
                "selected_secondary_id": None,
                "secondary_readiness": {},
                "fallback_assignments": {},
                "coalition_commits": [
                    {
                        "task_id": "task:GT-0001",
                        "global_track_id": "GT-0001",
                        "commit_required": True,
                        "state": "lease_expired" if fail_closed else "committed",
                        "coordinator_id": "C2-CENTER",
                        "required_member_ids": ["INT-0001"],
                        "acked_member_ids": [] if fail_closed else ["INT-0001"],
                        "missing_member_ids": ["INT-0001"] if fail_closed else [],
                        "lease_expires_at_s": lease,
                        "atomic_committed": not fail_closed,
                        "execution_authorized": not fail_closed,
                        "reason": reason,
                    }
                ],
                "rejection_reasons": [reason] if fail_closed else [],
            }
        ],
    }


def _write_episode(
    directory: Path,
    *,
    seed: int = 1,
    target_count: int = 50,
    resource_count: int = 50,
    recon_count: int = 4,
    dirty: bool = False,
    backlog: bool = False,
    d2_id_switch_available: bool = False,
    d4_lease_expired: bool = False,
    physical_proximity: bool = False,
    learning_profile: str = "disabled",
) -> Path:
    directory.mkdir(parents=True)
    camera_count = resource_count + recon_count
    learning_runtime, learning_versions = _learning_runtime(learning_profile)
    config = {
        "scenario_name": "misleading_2v2_label",
        "scenario_version": "explicit-scale-fixture-v1",
        "seed": seed,
        "target_count": target_count,
        "resource_count": resource_count,
        "recon_count": recon_count,
        "region_count": 1,
        "visual_enabled": True,
        **learning_versions,
        "metadata": {"learning_runtime": copy.deepcopy(learning_runtime)},
        "schema_version": "scalable3d-scenario-v1",
    }
    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_hash = hashlib.sha256(canonical).hexdigest()
    manifest = {
        "episode_id": f"fixture-s{seed}-{config_hash[:12]}",
        "git_commit": "0123456789abcdef",
        "repository_dirty": dirty,
        "config_sha256": config_hash,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": seed,
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v1",
        "d1_model_version": "d1-scalable3d-fusion-v1",
        "d2_model_version": "d2-scalable3d-association-v1",
        **learning_versions,
        "d7_model_version": "d7-scalable3d-guidance-v1",
        "threshold_version": "scalable3d-thresholds-v1",
    }
    summary = {
        "episode_id": manifest["episode_id"],
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": seed,
        "target_count": target_count,
        "resource_count": resource_count,
        "recon_count": recon_count,
        "finite_state": True,
        "online_truth_use_count": 0,
        "module_final_diagnostics": {
            "schema_version": "scalable3d-module-stack-v1",
            "learning_runtime": copy.deepcopy(learning_runtime),
            "regional_plan_rejection_reason": (
                "regional_d4_authority_lease_expired" if d4_lease_expired else None
            ),
        },
    }
    initial_d2_count = 195 if backlog else target_count
    final_d2_count = 200 if backlog else target_count
    d1_tracks = [_track(index) for index in range(target_count)]
    initial_d2_tracks = [_track(index, speed_offset=0.5) for index in range(initial_d2_count)]
    final_d2_tracks = [_track(index, speed_offset=0.5) for index in range(final_d2_count)]
    d3_learning_metadata = None
    if learning_profile != "disabled":
        d3_runtime = learning_runtime["d3"]
        assert isinstance(d3_runtime, dict)
        d3_learning_metadata = {
            "learning_mode": d3_runtime["requested_mode"],
            "learning_applied": False,
            "learning_bundle_loaded": d3_runtime["bundle_loaded"],
            "learning_fallback_reason": d3_runtime["fallback_reason"],
            "learning_shadow_only": learning_profile == "assist_shadow",
        }
    sequence = 1
    online: list[dict[str, object]] = []
    online.append(
        _envelope(
            sequence,
            "modules.d1.fused_tracks",
            0.2,
            {"timestamp": 0.2, "track_count": len(d1_tracks), "tracks": d1_tracks},
        )
    )
    sequence += 1
    online.append(
        _envelope(
            sequence,
            "modules.d2.associated_tracks",
            0.2,
            {
                "timestamp": 0.2,
                "track_count": len(initial_d2_tracks),
                "tracks": initial_d2_tracks,
                "association": {"candidate_edge_count": len(initial_d2_tracks)},
                "id_switch_count": 2 if d2_id_switch_available else None,
                "id_switch_count_available": d2_id_switch_available,
            },
        )
    )
    sequence += 1
    first_assignment_count = 195 if backlog else target_count
    online.append(
        _envelope(
            sequence,
            "modules.d3.assignment_plan",
            0.2,
            _d3_payload(
                target_count=initial_d2_count,
                assignment_count=first_assignment_count,
                learning_metadata=d3_learning_metadata,
            ),
        )
    )
    sequence += 1
    if backlog:
        online.append(
            _envelope(
                sequence,
                "modules.d2.associated_tracks",
                0.8,
                {
                    "timestamp": 0.8,
                    "track_count": 200,
                    "tracks": final_d2_tracks,
                    "association": {"candidate_edge_count": 200},
                    "id_switch_count": None,
                    "id_switch_count_available": False,
                },
            )
        )
        sequence += 1
        metadata = {
            "hysteresis_state": "held",
            "hysteresis_reason": "min_dwell_not_met",
            "hysteresis_reasons": ["min_dwell_not_met"],
            "hysteresis_dwell_time_s": 0.6,
            "hysteresis_min_dwell_s": 2.0,
            "hysteresis_dwell_ok": False,
            "hysteresis_candidate_target_ids": [f"GT-{i + 1:04d}" for i in range(200)],
            "hysteresis_held_execution_target_ids": [
                f"GT-{i + 1:04d}" for i in range(195)
            ],
            "hysteresis_pending_new_target_ids": [
                f"GT-{i + 1:04d}" for i in range(195, 200)
            ],
        }
        online.append(
            _envelope(
                sequence,
                "modules.d3.assignment_plan",
                0.8,
                _d3_payload(
                    target_count=200,
                    assignment_count=195,
                    metadata=metadata,
                    learning_metadata=d3_learning_metadata,
                ),
            )
        )
        sequence += 1
    d4_timestamp = 10.0 if d4_lease_expired else 0.8
    d4_lease = 5.0 if d4_lease_expired else 3.8
    online.append(
        _envelope(
            sequence,
            "modules.d4.regional_failover",
            d4_timestamp,
            _d4_payload(
                timestamp=d4_timestamp,
                lease=d4_lease,
                fail_closed=d4_lease_expired,
            ),
        )
    )
    sequence += 1
    online.append(
        _envelope(
            sequence,
            "modules.d5.terminal_association",
            0.8,
            {
                "timestamp": 0.8,
                "camera_batch_count": camera_count,
                "tracklet_count": 20,
                "graph_node_count": 20,
                "graph_edge_count": 40,
                "probability_source": (
                    "loaded_edge_model"
                    if learning_profile == "assist_shadow"
                    else "deterministic_geometry_rule"
                ),
                "scoring_status": (
                    "model_scored"
                    if learning_profile == "assist_shadow"
                    else (
                        "rule_fallback_model_unavailable"
                        if learning_profile == "missing_bundle"
                        else "rule_fallback_model_missing"
                    )
                ),
                "fallback_reason": (
                    None
                    if learning_profile == "assist_shadow"
                    else (
                        "bundle_missing"
                        if learning_profile == "missing_bundle"
                        else "model_missing"
                    )
                ),
                "diagnostics": {
                    "all_possible_camera_pairs": 1_431,
                    "candidate_tracklet_edges": 40,
                    "max_tracklet_candidate_edges_per_node": 8,
                    "tracklet_candidate_budget_dropped": 3,
                },
                "bindings": [
                    {
                        "cluster_key": f"cluster-{index}",
                        "global_track_id": f"GT-{index + 1:04d}",
                        "decision_state": "bound",
                        "cost": 0.1,
                        "supporting_tracklet_keys": [f"trk-{index}"],
                    }
                    for index in range(10)
                ],
            },
        )
    )
    sequence += 1
    hold = d4_lease_expired
    online.append(
        _envelope(
            sequence,
            "modules.d7.guidance_commands",
            d4_timestamp,
            {
                "timestamp": d4_timestamp,
                "command_count": 2,
                "mode_counts": {"hold" if hold else "midcourse_pn_3d": 2},
                "commands": [
                    {
                        "resource_id": f"INT-{index + 1:04d}",
                        "global_track_id": f"GT-{index + 1:04d}",
                        "plan_id": "PLAN-0001",
                        "plan_version": 1,
                        "mode": "hold" if hold else "midcourse_pn_3d",
                        "acceleration_ned_mps2": [0.0, 0.0, 0.0],
                        "command_norm_mps2": 0.0,
                        "gate_reason": (
                            "regional_d4_authority_lease_expired"
                            if hold
                            else "terminal_range_not_reached"
                        ),
                        "visual_switch_allowed": False,
                    }
                    for index in range(2)
                ],
            },
        )
    )

    proximity = (
        [
            {
                "timestamp": 0.9,
                "resource_index": 0,
                "target_index": 0,
                "resource_id": "INT-0001",
                "truth_target_id": "TGT-0001",
                "distance_m": 4.5,
            }
        ]
        if physical_proximity
        else []
    )
    labels = [
        {
            "observation_id": "obs-0001",
            "truth_entity_id": "TGT-0001",
            "measurement_timestamp": 0.2,
            "schema_version": "scalable3d-offline-truth-v1",
        }
    ]
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "scenario_config.json", config)
    _write_json(directory / "summary.json", summary)
    _write_jsonl(directory / "online_observations.jsonl", online)
    _write_jsonl(directory / "offline_proximity_intercepts.jsonl", proximity)
    _write_jsonl(directory / "offline_truth_labels.jsonl", labels)
    with (directory / "stage_timings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["stage", "call_count", "wall_time_s", "mean_wall_time_ms"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "stage": "module.d1_fusion",
                    "call_count": target_count,
                    "wall_time_s": 0.5 + seed * 0.01,
                    "mean_wall_time_ms": 10.0,
                },
                {
                    "stage": "module.d3_assignment",
                    "call_count": 2 if backlog else 1,
                    "wall_time_s": 0.2 + seed * 0.01,
                    "mean_wall_time_ms": 200.0,
                },
            ]
        )
    return directory


def _apply_producer_matrix_contract(
    episode: Path,
    *,
    variant: str = "R0",
    scenario_family: str = "nominal",
    schema: str = "scalable3d-experiment-matrix-v1",
    omit_fields: tuple[str, ...] = (),
    fallback_component: str | None = None,
    d5_binding_count: int = 10,
) -> None:
    """Rewrite a base fixture with the persisted contract emitted by main."""

    config_path = episode / "scenario_config.json"
    summary_path = episode / "summary.json"
    manifest_path = episode / "manifest.json"
    online_path = episode / "online_observations.jsonl"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    online = [
        json.loads(line)
        for line in online_path.read_text(encoding="utf-8").splitlines()
    ]
    seed = int(config["seed"])
    scale = int(config["target_count"])
    scenario_name = f"{scenario_family}_{scale}v{scale}"
    scenario_version = f"{scenario_family}-{scale}v{scale}-v1"
    required = {
        "R0": (),
        "G1": ("d5",),
        "A1": ("d3",),
        "A2": ("d4",),
        "A3": ("d5_active_vision",),
        "C1": ("d3", "d4", "d5", "d5_active_vision"),
        "F1": ("d3", "d4", "d5", "d5_active_vision"),
    }.get(variant, ())
    fingerprints = {
        "d3": "a" * 64,
        "d4": "b" * 64,
        "d5": "c" * 64,
        "d5_active_vision": "sha256:" + "d" * 64,
    }
    runtime: dict[str, object] = {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": "cpu",
        "default_rule_path_preserved": True,
    }
    for component in ("d3", "d4", "d5", "d5_active_vision"):
        enabled = component in required
        component_runtime: dict[str, object] = {
            "requested_mode": "assist" if enabled else "disabled",
            "effective_mode": "assist" if enabled else "disabled",
            "bundle_requested": enabled,
            "bundle_loaded": enabled,
            "fallback_reason": None,
            "model_fingerprint": fingerprints[component] if enabled else None,
        }
        if component == "d4":
            component_runtime["formal_unseen_seed_count"] = 20 if enabled else 0
        if component == "d5_active_vision":
            component_runtime.update(
                assist_admitted=enabled,
                model_semantic_version="1.0.0" if enabled else None,
                bundle_manifest_sha256=("e" * 64 if enabled else None),
                bundle_weights_sha256=("d" * 64 if enabled else None),
            )
        if component == fallback_component:
            component_runtime.update(
                effective_mode="rule_fallback",
                bundle_loaded=False,
                fallback_reason="model_bundle_missing",
            )
            if component == "d5_active_vision":
                component_runtime["assist_admitted"] = False
        runtime[component] = component_runtime

    metadata = dict(config.get("metadata", {}))
    metadata.update(
        {
            "catalog_version": "scalable3d-catalog-v1",
            "scenario_family": scenario_family,
            "experiment_matrix_schema": schema,
            "algorithm_variant": variant,
            "comparison_key": f"{scenario_family}|{scale}|{seed}",
            "full_system_validation": variant == "F1",
            "learning_runtime": copy.deepcopy(runtime),
        }
    )
    for field in omit_fields:
        metadata.pop(field, None)
    config.update(
        scenario_name=scenario_name,
        scenario_version=scenario_version,
        metadata=metadata,
        d3_policy_version=(
            f"d3-shared-edge-v1+{'a' * 12}"
            if "d3" in required and fallback_component != "d3"
            else "d3-scalable3d-rule-cost-v1"
        ),
        d4_policy_version=(
            f"d4-region-graph-v1+{'b' * 12}"
            if "d4" in required and fallback_component != "d4"
            else "d4-region-resource-rule-v1"
        ),
        d5_model_version=(
            f"d5-crossview-gnn-v1.0.0+{'c' * 12}"
            if "d5" in required and fallback_component != "d5"
            else "d5-scalable3d-geometry-rule-v1"
        ),
        d5_active_vision_policy_version=(
            f"d5-active-vision-v1.0.0+{'d' * 12}"
            if "d5_active_vision" in required
            and fallback_component != "d5_active_vision"
            else "d5-active-vision-rule-v1"
        ),
    )
    summary.update(
        scenario_name=scenario_name,
        scenario_version=scenario_version,
    )
    summary["module_final_diagnostics"]["learning_runtime"] = copy.deepcopy(runtime)

    for record in online:
        payload = record.get("payload", {})
        if record.get("topic") == "modules.d3.assignment_plan" and "d3" in required:
            payload.setdefault("metadata", {}).update(
                learning_mode="assist",
                learning_applied=fallback_component != "d3",
                learning_bundle_loaded=fallback_component != "d3",
                learning_fallback_reason=(
                    "model_bundle_missing" if fallback_component == "d3" else None
                ),
                learning_shadow_only=False,
            )
        if record.get("topic") == "modules.d5.terminal_association":
            bindings = list(payload.get("bindings", []))
            if d5_binding_count > len(bindings):
                bindings.extend(
                    {
                        "cluster_key": f"matrix-cluster-{index}",
                        "global_track_id": f"GT-{index + 1:04d}",
                        "decision_state": "bound",
                        "cost": 0.1,
                        "supporting_tracklet_keys": [f"matrix-trk-{index}"],
                    }
                    for index in range(len(bindings), d5_binding_count)
                )
            payload["bindings"] = bindings[:d5_binding_count]
            if "d5" in required and fallback_component != "d5":
                payload.update(
                    probability_source="loaded_edge_model",
                    scoring_status="model_scored",
                    fallback_reason=None,
                )

    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_hash = hashlib.sha256(canonical).hexdigest()
    episode_id = f"{scenario_name}-s{seed}-{config_hash[:12]}"
    manifest.update(
        episode_id=episode_id,
        config_sha256=config_hash,
        scenario_name=scenario_name,
        scenario_version=scenario_version,
        d3_policy_version=config["d3_policy_version"],
        d4_policy_version=config["d4_policy_version"],
        d5_model_version=config["d5_model_version"],
        d5_active_vision_policy_version=config[
            "d5_active_vision_policy_version"
        ],
    )
    summary["episode_id"] = episode_id
    _write_json(config_path, config)
    _write_json(summary_path, summary)
    _write_json(manifest_path, manifest)
    _write_jsonl(online_path, online)


def _d4_advice_payload(
    episode: Path,
    *,
    requested_mode: str = "assist",
    effective_mode: str = "shadow",
    assist_eligible: bool = False,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    inference_latency_ms: float = 2.0,
    quota_delta: int = 0,
    projection_rejections: list[str] | None = None,
    formal_mutated: bool = False,
    unseen_seed_count: int = 0,
) -> dict[str, object]:
    config = json.loads((episode / "scenario_config.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (episode / "online_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    formal = next(
        record["payload"]
        for record in reversed(records)
        if record["topic"] == "modules.d4.regional_failover"
    )
    region = formal["regions"][0]
    ownership = region["ownership"]
    timestamp = float(formal["timestamp_s"])
    d4_runtime = config["metadata"]["learning_runtime"]["d4"]
    learned = d4_runtime["bundle_loaded"] is True
    digest_before = "d" * 64
    digest_after = "e" * 64 if formal_mutated else digest_before
    payload: dict[str, object] = {
        "timestamp": timestamp,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "recommendation": {
            "schema": "d4-region-resource-recommendation-v1",
            "snapshot_id": f"fixture-s{config['seed']}-t{timestamp:.1f}",
            "scenario_id": config["scenario_name"],
            "scenario_version": config["scenario_version"],
            "seed": config["seed"],
            "authority_digest": "a" * 64,
            "created_at_s": timestamp,
            "policy_name": (
                "d4-region-resource-learned" if learned else "d4-region-resource-rule"
            ),
            "policy_version": (
                str(config["d4_policy_version"]).rsplit("+", 1)[0]
                if learned
                else "v1"
            ),
            "source": "learned" if learned else "rule",
            "confidence": 0.9,
            "actions": [
                {
                    "region_id": region["region_id"],
                    "resource_quota_delta": quota_delta,
                    "reserve_ratio": 0.1,
                    "reconnaissance_priority": 0.5,
                    "hold": False,
                    "request_replan": False,
                    "expected_owner_id": ownership["owner_id"],
                    "expected_owner_layer": ownership["owner_layer"],
                    "expected_plan_id": ownership["plan_id"],
                    "expected_plan_version": ownership["plan_version"],
                    "expected_epoch": ownership["epoch"],
                    "expected_lease_expires_at_s": ownership["lease_expires_at_s"],
                    "reasons": [],
                }
            ],
            "transfers": [],
            "projected": True,
            "fallback_reason": fallback_reason,
            "model_sha256": d4_runtime["model_fingerprint"] if learned else None,
            "projection_rejections": projection_rejections or [],
        },
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "assist_eligible": assist_eligible,
        "unseen_seed_count": unseen_seed_count,
        "inference_latency_ms": inference_latency_ms,
        "formal_decision_digest_before": digest_before,
        "formal_decision_digest_after": digest_after,
        "formal_decision_unchanged": not formal_mutated,
    }
    recommendation = payload["recommendation"]
    assert isinstance(recommendation, dict)
    snapshot_id = str(recommendation["snapshot_id"])
    authority_digest = str(recommendation["authority_digest"])
    plan_id = str(ownership["plan_id"])
    plan_version = int(ownership["plan_version"])
    resources_before = int(config["resource_count"])
    contract_without_id: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "snapshot_version": 1,
        "snapshot_timestamp_s": timestamp,
        "scenario_id": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": config["seed"],
        "authority_digest": authority_digest,
        "created_at_s": timestamp,
        "valid_from_s": timestamp,
        "valid_until_s": timestamp + 1.5,
        "source_plan_versions": [[plan_id, plan_version]],
        "projected": True,
        "projector_name": "d4-deterministic-resource-projector",
        "projector_version": "v1",
        "minimum_reserve_ratio": 0.1,
        "minimum_reserve_resources": 1,
        "advisory_ttl_s": 1.5,
        "policy_name": recommendation["policy_name"],
        "policy_version": recommendation["policy_version"],
        "source": recommendation["source"],
        "confidence": recommendation["confidence"],
        "model_sha256": recommendation["model_sha256"],
        "fallback_reason": fallback_reason,
        "total_resources_before": resources_before,
        "total_quota_delta": quota_delta,
        "total_resources_after": resources_before + quota_delta,
        "regions": [
            {
                "source_version": {
                    "region_id": region["region_id"],
                    "snapshot_id": snapshot_id,
                    "snapshot_version": 1,
                    "authority_digest": authority_digest,
                    "owner_id": ownership["owner_id"],
                    "owner_layer": ownership["owner_layer"],
                    "plan_id": plan_id,
                    "plan_version": plan_version,
                    "epoch": ownership["epoch"],
                    "lease_expires_at_s": ownership["lease_expires_at_s"],
                    "coalition_ack_complete": True,
                    "owner_active": True,
                    "fault_fenced": False,
                    "fault_fence_epoch": None,
                },
                "resources_before": resources_before,
                "resource_quota_delta": quota_delta,
                "resources_after": resources_before + quota_delta,
                "protected_reserve_resources": 1,
                "protected_committed_resources": max(resources_before - 1, 0),
                "reserve_ratio": 0.1,
                "reconnaissance_priority": 0.5,
                "hold": False,
                "request_replan": False,
                "reasons": [],
            }
        ],
        "transfers": [],
        "projection_rejections": projection_rejections or [],
        "publication_rejections": [],
        "formal_decision_required": True,
        "recommendation_schema": "d4-region-resource-recommendation-v1",
        "schema": "d4-region-resource-advisory-v1",
    }
    contract_digest = hashlib.sha256(
        json.dumps(
            contract_without_id,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload["advisory_contract"] = {
        "advisory_id": f"d4-rr-advisory-{contract_digest}",
        **contract_without_id,
    }
    return payload


def _append_d4_advice(
    episode: Path,
    payload: dict[str, object],
    *,
    schema_version: str = "d4-region-resource-advisory-runtime-v1",
) -> None:
    path = episode / "online_observations.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records.append(
        _envelope(
            max(int(record["sequence"]) for record in records) + 1,
            "modules.d4.region_resource_advice",
            float(payload["timestamp"]),
            payload,
            schema_version=schema_version,
        )
    )
    _write_jsonl(path, records)


def _append_d4_consumption(
    episode: Path,
    *,
    consumable: bool = True,
    d3_hint_applied: bool = True,
    rejection_reasons: list[str] | None = None,
    bridge_rejection_reason: str | None = None,
    envelope_schema: str = "d4-region-resource-consumption-v1",
    payload_schema: str = "d4-region-resource-consumption-v1",
    source: str = "main",
    unknown_advisory: bool = False,
    mutate_advisory_contract: bool = False,
    summary_mismatch: bool = False,
) -> None:
    path = episode / "online_observations.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    advice_record = next(
        record
        for record in reversed(records)
        if record["topic"] == "modules.d4.region_resource_advice"
    )
    advisory = copy.deepcopy(advice_record["payload"]["advisory_contract"])
    if unknown_advisory:
        advisory["advisory_id"] = "d4-rr-advisory-" + "f" * 64
    if mutate_advisory_contract:
        advisory["authority_digest"] = "f" * 64
    evaluated_at_s = float(advice_record["payload"]["timestamp"]) + 0.75
    reasons = list(rejection_reasons or [])
    payload: dict[str, object] = {
        "timestamp": evaluated_at_s,
        "advisory": advisory,
        "evaluated_at_s": evaluated_at_s,
        "current_snapshot_id": advisory["snapshot_id"],
        "current_snapshot_version": advisory["snapshot_version"],
        "current_authority_digest": advisory["authority_digest"],
        "consumable": consumable,
        "rejection_reasons": reasons,
        "schema": payload_schema,
        "bridge_rejection_reason": bridge_rejection_reason,
        "d3_hint_applied": d3_hint_applied,
    }
    record = _envelope(
        max(int(item["sequence"]) for item in records) + 1,
        "modules.d4.region_resource_consumption",
        evaluated_at_s,
        payload,
        schema_version=envelope_schema,
    )
    record["source"] = source
    records.append(record)
    _write_jsonl(path, records)

    summary_path = episode / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    diagnostics = summary.setdefault("module_final_diagnostics", {})
    diagnostics.update(
        d4_region_consumption_available=True,
        d4_region_consumable=consumable,
        d4_region_consumption_rejection_reasons=reasons,
        d4_region_hint_bridge_rejection_reason=bridge_rejection_reason,
        d3_regional_hint_applied=(
            not d3_hint_applied if summary_mismatch else d3_hint_applied
        ),
    )
    _write_json(summary_path, summary)


def test_normal_50v50_uses_explicit_scale_and_records_module_metrics(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "normal", seed=7, d2_id_switch_available=True)

    row = evaluate_scalable_3d_episode(episode)

    assert row["scenario_name"] == "misleading_2v2_label"
    assert row["target_count"] == 50
    assert row["resource_count"] == 50
    assert row["recon_count"] == 4
    assert row["camera_count"] == 54
    assert row["camera_count_source"] == (
        "producer_one_camera_per_resource_and_recon_contract"
    )
    assert row["config_hash_match"] is True
    assert row["d1_track_count"] == 50
    assert row["d2_track_count"] == 50
    assert row["d1_speed_p50_mps"] == pytest.approx(25.5)
    assert row["d2_id_switch_count"] == 2
    assert row["d3_plan_coverage_rate"] == pytest.approx(1.0)
    assert row["d4_owner_records_json"][0]["owner_node_id"] == "C2-CENTER"
    assert row["d4_commit_state_distribution_json"] == {"committed": 1}
    assert row["d5_candidate_edge_count"] == 40
    assert row["d5_graph_density"] == pytest.approx(40 / 190)
    assert row["d5_binding_count"] == 10
    assert row["d7_command_count"] == 2
    assert row["d7_hold_count"] == 0
    assert row["finite_state"] is True
    assert row["online_truth_use_count"] == 0


def test_current_schema_registry_matches_real_producer_contract(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "current_schema_contract")

    row = evaluate_scalable_3d_episode(episode)

    assert SCALABLE_3D_SCHEMA_REGISTRY_VERSION == "d6-scalable3d-schema-registry-v1"
    assert SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION == (
        "d6-scalable3d-offline-evaluation-v6"
    )
    assert SCALABLE_3D_OFFLINE_EVALUATION_DATE == "2026-07-22"
    assert row["evaluation_date"] == "2026-07-22"
    assert SCALABLE_3D_CURRENT_SCHEMA_REGISTRY == {
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v1",
        "scenario_config_schema": "scalable3d-scenario-v1",
    }
    assert row["schema_contract_registry_version"] == (
        SCALABLE_3D_SCHEMA_REGISTRY_VERSION
    )
    assert row["current_schema_registry_json"] == (
        SCALABLE_3D_CURRENT_SCHEMA_REGISTRY
    )
    assert row["current_schema_contract_match"] is True
    assert row["current_schema_contract_match_availability"] == "available"
    assert row["current_schema_contract_failure_reasons_json"] == []
    for field, expected in SCALABLE_3D_CURRENT_SCHEMA_REGISTRY.items():
        assert row[field] == expected
        assert row[f"{field}_current_contract_match"] is True
        assert row[f"{field}_current_contract_match_availability"] == "available"
        assert row[f"{field}_current_contract_match_failure_reason"] is None
        assert row["current_schema_contract_details_json"][field] == {
            "observed": expected,
            "expected_current": expected,
            "match": True,
            "status": "current",
            "reason": None,
        }
    assert row["formal_acceptance_eligible"] is True


def test_v2_posterior_governance_is_integrated_and_fails_formal_on_repeat(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "posterior_generation_repeat")
    summary_path = episode / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["module_final_diagnostics"]["observation_governance"] = {
        "schema_version": "scalable3d-observation-governance-runtime-v2",
        "d1_posterior_generation": 1,
        "d2_pending_d1_posterior_generation": None,
        "d2_consumed_d1_posterior_generation": 1,
        "d2_posterior_consumption_count": 2,
        "d2_pre_tick_posterior_merge_count": 0,
    }
    _write_json(summary_path, summary)

    online_path = episode / "online_observations.jsonl"
    records = [
        json.loads(line)
        for line in online_path.read_text(encoding="utf-8").splitlines()
    ]
    d1 = next(item for item in records if item["topic"] == "modules.d1.fused_tracks")
    d2 = next(item for item in records if item["topic"] == "modules.d2.associated_tracks")
    d1["payload"].update(
        snapshot_kind="full_posterior",
        posterior_generation=1,
    )
    d2["payload"]["source_d1_posterior_generation"] = 1
    repeated = copy.deepcopy(d2)
    repeated["sequence"] = max(int(item["sequence"]) for item in records) + 1
    repeated["timestamp"] = 0.9
    repeated["payload"]["timestamp"] = 0.9
    records.append(repeated)
    _write_jsonl(online_path, records)

    row = evaluate_scalable_3d_episode(episode)

    assert row["observation_governance_generation_integrity"] is False
    assert row["formal_acceptance_eligible"] is False
    assert any(
        "d2_source_generation_not_strictly_increasing" in reason
        for reason in row["episode_failure_reasons_json"]
    )


@pytest.mark.parametrize(
    ("field", "observed"),
    (
        ("world_schema", "scalable3d-world-v0"),
        ("bus_schema", "scalable3d-episode-bus-v9"),
        ("scenario_schema", "scalable3d-scenario-unknown"),
        (
            "online_observation_schema",
            "scalable3d-online-observation-v1",
        ),
        ("offline_truth_schema", "tampered-offline-truth-v1"),
    ),
)
def test_old_unknown_or_tampered_manifest_schema_is_descriptive_only(
    tmp_path: Path,
    field: str,
    observed: str,
) -> None:
    episode = _write_episode(tmp_path / f"mismatch_{field}")
    manifest_path = episode / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = observed
    _write_json(manifest_path, manifest)

    row = evaluate_scalable_3d_episode(episode)

    expected = SCALABLE_3D_CURRENT_SCHEMA_REGISTRY[field]
    failure = (
        f"schema_contract_mismatch:{field}:"
        f"expected={expected}:observed={observed}"
    )
    assert row[field] == observed
    assert row[f"{field}_availability"] == "available"
    assert row[f"{field}_current_contract_match"] is False
    assert row[f"{field}_current_contract_match_availability"] == "available"
    assert row[f"{field}_current_contract_match_failure_reason"] == failure
    assert row["current_schema_contract_match"] is False
    assert row["current_schema_contract_match_availability"] == "available"
    assert row["current_schema_contract_details_json"][field]["observed"] == observed
    assert row["current_schema_contract_details_json"][field]["status"] == (
        "historical_or_unknown_read_only"
    )
    assert failure in row["current_schema_contract_failure_reasons_json"]
    assert failure in row["episode_failure_reasons_json"]
    assert row["formal_acceptance_eligible"] is False


def test_missing_manifest_schema_is_unavailable_and_not_formal_acceptance(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "missing_bus_schema")
    manifest_path = episode / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["bus_schema"]
    _write_json(manifest_path, manifest)

    row = evaluate_scalable_3d_episode(episode)

    assert row["bus_schema"] is None
    assert row["bus_schema_availability"] == "unavailable"
    assert row["bus_schema_current_contract_match"] is None
    assert row["bus_schema_current_contract_match_availability"] == "unavailable"
    assert row["bus_schema_current_contract_match_unavailable_reason"] == (
        "schema_contract_unavailable:bus_schema"
    )
    assert row["current_schema_contract_match"] is None
    assert row["current_schema_contract_match_availability"] == "unavailable"
    assert row["current_schema_contract_match_unavailable_reason"] == (
        "schema_contract_fields_unavailable:bus_schema"
    )
    assert "schema_contract_unavailable:bus_schema" in row[
        "episode_failure_reasons_json"
    ]
    assert row["formal_acceptance_eligible"] is False


def test_real_producer_style_r0_matrix_contract_is_audited_without_path_inference(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "arbitrary_directory_name", seed=17)
    _apply_producer_matrix_contract(episode, variant="R0")

    row = evaluate_scalable_3d_episode(episode)

    assert EXPERIMENT_MATRIX_SCHEMA_VERSION == "scalable3d-experiment-matrix-v1"
    assert EXPERIMENT_MATRIX_VARIANTS == ("R0", "G1", "A1", "A2", "A3", "C1", "F1")
    assert row["experiment_matrix_declared"] is True
    assert row["experiment_matrix_schema"] == EXPERIMENT_MATRIX_SCHEMA_VERSION
    assert row["algorithm_variant"] == "R0"
    assert row["comparison_key"] == "nominal|50|17"
    assert row["experiment_matrix_effective_comparison_key"] == "nominal|50|17"
    assert row["experiment_matrix_effective_comparison_key_source"] == (
        "scenario_config.metadata.comparison_key"
    )
    assert row["experiment_matrix_metadata_valid"] is True
    assert row["variant_runtime_resolution_valid"] is True
    assert row["variant_execution_valid"] is True
    assert row["variant_execution_failure_reasons_json"] == []
    assert row["experiment_matrix_formal_acceptance_eligible"] is True
    assert row["experiment_matrix_evidence_class"] == "clean_formal"
    assert row["episode_evidence_status"] == "clean_formal_experiment_matrix"


def test_historical_episode_stays_evaluable_with_matrix_fields_unavailable(
    tmp_path: Path,
) -> None:
    row = evaluate_scalable_3d_episode(_write_episode(tmp_path / "historical"))

    assert row["d1_track_count"] == 50
    assert row["formal_acceptance_eligible"] is True
    assert row["experiment_matrix_declared"] is False
    assert row["algorithm_variant"] is None
    assert row["algorithm_variant_availability"] == "unavailable"
    assert row["comparison_key"] is None
    assert row["variant_execution_valid"] is None
    assert row["experiment_matrix_formal_acceptance_eligible"] is None


@pytest.mark.parametrize(
    "missing_field",
    ("experiment_matrix_schema", "algorithm_variant", "comparison_key"),
)
def test_missing_matrix_identity_field_is_unavailable_without_path_guessing(
    tmp_path: Path,
    missing_field: str,
) -> None:
    missing = _write_episode(tmp_path / f"looks_like_G1_but_missing_{missing_field}")
    _apply_producer_matrix_contract(
        missing,
        variant="R0",
        omit_fields=(missing_field,),
    )

    row = evaluate_scalable_3d_episode(missing)

    assert row[missing_field] is None
    assert row[f"{missing_field}_availability"] == "unavailable"
    assert row["variant_execution_valid"] is False
    assert row["experiment_matrix_formal_acceptance_eligible"] is False
    if missing_field == "comparison_key":
        assert row["experiment_matrix_effective_comparison_key"] == "nominal|50|1"
        assert row["experiment_matrix_effective_comparison_key_source"] == (
            "scenario_config.metadata.scenario_family+explicit_scale+seed"
        )


def test_fake_variant_cannot_pass_matrix_acceptance(tmp_path: Path) -> None:
    fake = _write_episode(tmp_path / "fake_variant")
    _apply_producer_matrix_contract(fake, variant="X9")

    fake_row = evaluate_scalable_3d_episode(fake)

    assert fake_row["algorithm_variant"] == "X9"
    assert fake_row["algorithm_variant_known"] is False
    assert fake_row["variant_execution_valid"] is False
    assert "algorithm_variant_unknown:X9" in fake_row[
        "variant_execution_failure_reasons_json"
    ]
    assert fake_row["experiment_matrix_formal_acceptance_eligible"] is False


def test_f1_is_expected_only_for_declared_full_system_scenario(tmp_path: Path) -> None:
    nominal = _write_episode(tmp_path / "nominal_f1", seed=13)
    _apply_producer_matrix_contract(nominal, variant="F1")
    high_threat = _write_episode(tmp_path / "high_threat_r0", seed=14)
    _apply_producer_matrix_contract(
        high_threat,
        variant="R0",
        scenario_family="high_threat_m_to_n",
    )

    nominal_row = evaluate_scalable_3d_episode(nominal)
    high_threat_row = evaluate_scalable_3d_episode(high_threat)
    matrix = aggregate_scalable_3d_episodes(
        [nominal_row, high_threat_row],
        bootstrap_resamples=50,
    )["experiment_matrix"]

    assert nominal_row["full_system_validation_contract_match"] is False
    assert "f1_scenario_not_full_system:nominal" in nominal_row[
        "variant_execution_failure_reasons_json"
    ]
    by_key = {
        item["comparison_key"]: item for item in matrix["completeness"]["details"]
    }
    assert by_key["nominal|50|13"]["expected_cell_count"] == 6
    assert "F1" in by_key["nominal|50|13"]["unexpected_variants"]
    assert by_key["high_threat_m_to_n|50|14"]["expected_cell_count"] == 7
    assert "F1" in by_key["high_threat_m_to_n|50|14"]["missing_variants"]


def test_loaded_variant_that_falls_back_to_rule_is_execution_invalid(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "g1_fallback")
    _apply_producer_matrix_contract(
        episode,
        variant="G1",
        fallback_component="d5",
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["experiment_matrix_metadata_valid"] is True
    assert row["variant_runtime_resolution_valid"] is False
    assert row["variant_execution_valid"] is False
    reasons = row["variant_execution_failure_reasons_json"]
    assert "variant_required_bundle_not_loaded:d5" in reasons
    assert "variant_required_assist_not_effective:d5:rule_fallback" in reasons
    assert (
        "variant_required_component_rule_fallback:d5:model_bundle_missing" in reasons
    )
    assert row["experiment_matrix_formal_acceptance_eligible"] is False


def test_a2_requires_and_accepts_valid_d4_consumption_evidence(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "a2_consumed", seed=19)
    _apply_producer_matrix_contract(episode, variant="A2")
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            effective_mode="assist",
            assist_eligible=True,
            unseen_seed_count=20,
        ),
    )
    _append_d4_consumption(episode)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_region_consumption_publication_count"] == 1
    assert row["d4_region_consumption_valid_publication_count"] == 1
    assert row["d4_region_consumption_invalid_publication_count"] == 0
    assert row["d4_region_consumption_summary_consistent"] is True
    assert row["d4_region_consumable_count"] == 1
    assert row["d4_region_d3_hint_applied_count"] == 1
    assert row["d4_advice_control_adoption_count"] == 1
    assert row["variant_component_audit_json"]["d4"][
        "adoption_evidence_valid"
    ] is True
    assert row["variant_execution_valid"] is True
    assert row["experiment_matrix_formal_acceptance_eligible"] is True


def test_matrix_completeness_keeps_missing_cells_in_fixed_denominator(
    tmp_path: Path,
) -> None:
    rows = []
    for variant, bindings in (("R0", 10), ("G1", 12), ("A1", 10)):
        episode = _write_episode(tmp_path / variant, seed=23)
        _apply_producer_matrix_contract(
            episode,
            variant=variant,
            d5_binding_count=bindings,
        )
        rows.append(evaluate_scalable_3d_episode(episode))

    aggregate = aggregate_scalable_3d_episodes(
        rows,
        bootstrap_resamples=100,
        bootstrap_rng_seed=91,
    )
    matrix = aggregate["experiment_matrix"]
    completeness = matrix["completeness"]

    assert completeness["comparison_key_count"] == 1
    assert completeness["expected_cell_count"] == 6
    assert completeness["present_expected_cell_count"] == 3
    assert completeness["execution_valid_cell_count"] == 3
    assert completeness["missing_expected_cell_count"] == 3
    assert completeness["cell_presence_rate"] == pytest.approx(0.5)
    detail = completeness["details"][0]
    assert detail["missing_variants"] == ["A2", "A3", "C1"]
    g1_pair = next(
        item
        for item in matrix["descriptive_paired_deltas_vs_r0"]
        if item["algorithm_variant"] == "G1"
    )
    assert g1_pair["expected_pair_count"] == 1
    assert g1_pair["complete_execution_pair_count"] == 1
    binding_delta = g1_pair["metric_deltas_variant_minus_r0"]["d5_binding_count"]
    assert binding_delta["mean_delta_variant_minus_r0"] == pytest.approx(2.0)
    assert binding_delta["bootstrap_availability"] == "unavailable"


def test_two_seed_r0_pairing_outputs_bootstrap_ci_and_separates_dirty_evidence(
    tmp_path: Path,
) -> None:
    rows = []
    episodes = []
    for seed in (31, 32):
        for variant, bindings in (("R0", 8), ("G1", 10 + seed - 31)):
            episode = _write_episode(
                tmp_path / f"{variant}_{seed}",
                seed=seed,
                dirty=(seed == 32),
            )
            _apply_producer_matrix_contract(
                episode,
                variant=variant,
                d5_binding_count=bindings,
            )
            episodes.append(episode)
            rows.append(evaluate_scalable_3d_episode(episode))

    matrix = aggregate_scalable_3d_episodes(
        rows,
        bootstrap_resamples=200,
        bootstrap_rng_seed=20260720,
    )["experiment_matrix"]
    assert matrix["clean_formal_episode_count"] == 2
    assert matrix["dirty_development_episode_count"] == 2
    descriptive = next(
        item
        for item in matrix["descriptive_paired_deltas_vs_r0"]
        if item["algorithm_variant"] == "G1"
    )
    formal = next(
        item
        for item in matrix["clean_formal_paired_deltas_vs_r0"]
        if item["algorithm_variant"] == "G1"
    )
    delta = descriptive["metric_deltas_variant_minus_r0"]["d5_binding_count"]
    assert descriptive["complete_execution_pair_count"] == 2
    assert delta["mean_delta_variant_minus_r0"] == pytest.approx(2.5)
    assert delta["bootstrap_availability"] == "available"
    assert delta["bootstrap_ci95_low"] is not None
    assert delta["bootstrap_ci95_high"] is not None
    assert formal["complete_execution_pair_count"] == 1
    assert formal["pairing_status"] == "descriptive_single_pair_no_bootstrap_ci"
    assert descriptive["causal_attribution"] is False
    g1_group = next(
        item
        for item in matrix["variant_groups"]
        if item["algorithm_variant"] == "G1"
    )
    assert g1_group["clean_formal_episode_count"] == 1
    assert g1_group["dirty_development_episode_count"] == 1
    assert "module.d1_fusion" in g1_group["stage_timing"]
    assert matrix["metric_categories"]["hard_constraints"] == [
        "d4_advice_resource_quota_conservation_violation_count",
        "d4_advice_formal_decision_mutation_count",
        "d4_region_consumption_invalid_publication_count",
        "d4_region_consumption_summary_consistent",
        "d5_active_vision_target_reference_violation_count",
        "d5_active_vision_online_truth_field_violation_count",
    ]
    assert matrix["causal_attribution"]["availability"] == "unavailable"

    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        tmp_path / "matrix_report",
        inputs=Scalable3DOfflineEvaluationInputs(tuple(episodes)),
        bootstrap_resamples=100,
        bootstrap_rng_seed=20260720,
    )
    written = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert written["experiment_matrix"]["dirty_development_episode_count"] == 2
    assert "## 算法实验矩阵" in markdown
    assert "当前没有 clean/formal 矩阵证据" not in markdown
    assert "目录名不参与变体和配对身份判断" in markdown


def test_initial_195_then_200_min_dwell_hold_reports_five_track_backlog(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "backlog",
        seed=8,
        target_count=200,
        resource_count=200,
        recon_count=8,
        backlog=True,
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d3_current_track_count"] == 200
    assert row["d3_plan_target_count"] == 200
    assert row["d3_assignment_count"] == 195
    assert row["d3_plan_coverage_rate"] == pytest.approx(195 / 200)
    assert row["d3_backlog_count"] == 5
    assert row["d3_min_dwell_hold_event_count"] == 1
    assert row["d3_min_dwell_backlog_max"] == 5
    assert row["d3_hysteresis_reason"] == "min_dwell_not_met"
    assert row["d3_hysteresis_reasons_json"] == {
        "min_dwell_not_met": 1,
        "same_assignment": 1,
    }


def test_missing_d2_id_switch_is_null_with_producer_reason(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "idsw_unavailable")

    row = evaluate_scalable_3d_episode(episode)

    assert row["d2_id_switch_count"] is None
    assert row["d2_id_switch_count_availability"] == "unavailable"
    assert (
        row["d2_id_switch_count_unavailable_reason"]
        == "producer_declared_id_switch_count_unavailable"
    )


def test_missing_track_covariance_is_unavailable_instead_of_zero(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "covariance_unavailable")
    online_path = episode / "online_observations.jsonl"
    records = [json.loads(line) for line in online_path.read_text(encoding="utf-8").splitlines()]
    records[0]["payload"]["tracks"][0]["covariance"] = None
    _write_jsonl(online_path, records)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d1_velocity_covariance_trace_p50"] is None
    assert row["d1_velocity_covariance_trace_p50_availability"] == "unavailable"
    assert row["d1_velocity_covariance_trace_p50_unavailable_reason"] == (
        "d1_velocity_covariance_missing_or_nonfinite"
    )
    assert row["d1_speed_p50_mps"] == pytest.approx(25.5)


def test_d4_expired_lease_and_d7_hold_reject_are_explicit(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "lease_expired", d4_lease_expired=True)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_lease_expired_region_count"] == 1
    assert row["d4_fail_closed_region_count"] == 1
    assert row["d4_commit_state_distribution_json"] == {"lease_expired": 1}
    assert row["d4_fail_closed_reasons_json"] == {
        "coalition_commit_lease_expired": 1,
        "regional_d4_authority_lease_expired": 1,
    }
    assert row["d7_hold_count"] == 2
    assert row["d7_reject_count"] == 2
    assert row["d7_reject_reason_distribution_json"] == {
        "regional_d4_authority_lease_expired": 2
    }


def test_d5_model_missing_rule_fallback_is_not_model_evidence(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "d5_fallback")

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_probability_source"] == "deterministic_geometry_rule"
    assert row["d5_scoring_status"] == "rule_fallback_model_missing"
    assert row["d5_fallback_reason"] == "model_missing"
    assert row["d5_model_fallback_event_count"] == 1
    assert row["d5_graph_edge_budget"] == 80
    assert row["d5_graph_budget_utilization"] == pytest.approx(0.5)


def test_disabled_learning_runtime_keeps_model_evidence_unavailable(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "learning_disabled")

    row = evaluate_scalable_3d_episode(episode)

    assert row["learning_runtime_schema_version"] == "scalable3d-learning-runtime-v1"
    assert row["learning_runtime_metadata_consistent"] is True
    for module in ("d3", "d4", "d5"):
        assert row[f"{module}_learning_requested_mode"] == "disabled"
        assert row[f"{module}_learning_bundle_loaded"] is False
        assert row[f"{module}_learning_model_fingerprint"] is None
        assert row[f"{module}_learning_model_fingerprint_availability"] == "unavailable"
        assert row[f"{module}_learning_model_version"] is None
    assert row["d3_learning_publication_count"] == 0
    assert row["d3_learning_applied_count"] is None
    assert row["d4_advice_publication_count"] == 0
    assert row["d4_advice_evidence_status"] == "not_expected_disabled"
    assert row["d4_advice_shadow_output_count"] is None
    assert row["d4_advice_control_adoption_count"] is None
    assert row["formal_acceptance_eligible"] is True


def test_missing_bundle_fallback_consumes_d3_d4_d5_fields_without_model_evidence(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "missing_bundle",
        learning_profile="missing_bundle",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            fallback_used=True,
            fallback_reason="bundle_validation_failed:model_bundle_missing",
            inference_latency_ms=0.0,
        ),
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d3_learning_publication_count"] == 1
    assert row["d3_learning_applied_count"] == 0
    assert row["d3_learning_fallback_event_count"] == 1
    assert row["d3_learning_fallback_reason_distribution_json"] == {
        "model_bundle_missing": 1
    }
    assert row["d4_learning_bundle_loaded"] is False
    assert row["d4_learning_model_fingerprint"] is None
    assert row["d4_learning_model_version"] is None
    assert row["d4_advice_publication_count"] == 1
    assert row["d4_advice_requested_mode_distribution_json"] == {"assist": 1}
    assert row["d4_advice_effective_mode_distribution_json"] == {"shadow": 1}
    assert row["d4_advice_fallback_count"] == 1
    assert row["d4_advice_fallback_reason_distribution_json"] == {
        "bundle_validation_failed:model_bundle_missing": 1
    }
    assert row["d4_advice_inference_latency_p50_ms"] == 0.0
    assert row["d4_advice_formal_decision_unchanged_count"] == 1
    assert row["d5_learning_bundle_loaded"] is False
    assert row["d5_model_fallback_event_count"] == 1
    assert row["d5_fallback_reason_distribution_json"] == {"bundle_missing": 1}


def test_loaded_bundle_shadow_output_is_not_control_adoption_or_physical_result(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "assist_to_shadow",
        learning_profile="assist_shadow",
        physical_proximity=True,
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            projection_rejections=["authority_fenced", "capacity_clipped"],
            inference_latency_ms=4.0,
        ),
    )

    row = evaluate_scalable_3d_episode(episode)

    for module, fingerprint in (("d3", "a" * 64), ("d4", "b" * 64), ("d5", "c" * 64)):
        assert row[f"{module}_learning_bundle_loaded"] is True
        assert row[f"{module}_learning_model_fingerprint"] == fingerprint
        assert row[f"{module}_learning_model_version_availability"] == "available"
        assert fingerprint[:12] in row[f"{module}_learning_model_version"]
    assert row["d4_advice_recommendation_output_count"] == 1
    assert row["d4_advice_shadow_output_count"] == 1
    assert row["d4_advice_assist_eligible_count"] == 0
    assert row["d4_advice_projection_rejection_count"] == 2
    assert row["d4_advice_resource_quota_conservation_violation_count"] == 0
    assert row["d4_advice_formal_decision_mutation_count"] == 0
    assert row["d4_advice_formal_decision_unchanged_count"] == 1
    assert row["d4_advice_control_adoption_count"] is None
    assert row["d4_advice_control_adoption_count_unavailable_reason"] == (
        "d4_region_consumption_publication_missing"
    )
    assert row["offline_proximity_within_5m_count"] == 1
    assert row["mission_success"] is None


def test_assist_eligible_is_a_gate_and_formal_decision_still_remains_unchanged(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "assist_eligible",
        learning_profile="assist_shadow",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            effective_mode="assist",
            assist_eligible=True,
            unseen_seed_count=20,
        ),
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_advice_assist_eligible_count"] == 1
    assert row["d4_advice_effective_mode_distribution_json"] == {"assist": 1}
    assert row["d4_advice_formal_decision_unchanged_count"] == 1
    assert row["d4_advice_formal_decision_mutation_count"] == 0
    assert row["d4_advice_control_adoption_count"] is None


def test_rejected_d4_consumption_is_valid_zero_adoption_evidence(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "d4_consumption_rejected",
        learning_profile="assist_shadow",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            effective_mode="assist",
            assist_eligible=True,
            unseen_seed_count=20,
        ),
    )
    _append_d4_consumption(
        episode,
        consumable=False,
        d3_hint_applied=False,
        rejection_reasons=["advisory_expired"],
        bridge_rejection_reason=(
            "regional_advisory_rejected:advisory_expired"
        ),
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_region_consumption_valid_publication_count"] == 1
    assert row["d4_region_consumption_invalid_publication_count"] == 0
    assert row["d4_region_consumable_count"] == 0
    assert row["d4_region_d3_hint_applied_count"] == 0
    assert row["d4_advice_control_adoption_count"] == 0
    assert row["d4_region_consumption_rejection_reason_distribution_json"] == {
        "advisory_expired": 1
    }
    assert row[
        "d4_region_consumption_bridge_rejection_reason_distribution_json"
    ] == {"regional_advisory_rejected:advisory_expired": 1}


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("old_schema", "consumption_envelope_schema_mismatch"),
        ("unknown_advisory", "consumption_advisory_not_previously_published"),
        ("contract_mismatch", "consumption_advisory_contract_mismatch"),
    ),
)
def test_invalid_d4_consumption_contract_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    episode = _write_episode(
        tmp_path / mutation,
        learning_profile="assist_shadow",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            effective_mode="assist",
            assist_eligible=True,
            unseen_seed_count=20,
        ),
    )
    _append_d4_consumption(
        episode,
        envelope_schema=(
            "d4-region-resource-consumption-v0"
            if mutation == "old_schema"
            else "d4-region-resource-consumption-v1"
        ),
        unknown_advisory=mutation == "unknown_advisory",
        mutate_advisory_contract=mutation == "contract_mismatch",
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_region_consumption_valid_publication_count"] == 0
    assert row["d4_region_consumption_invalid_publication_count"] == 1
    assert row["d4_region_consumption_invalid_reason_distribution_json"] == {
        expected_reason: 1
    }
    assert row["d4_advice_control_adoption_count"] is None
    assert row["formal_acceptance_eligible"] is False
    assert "d4_region_consumption_payload_invalid" in row[
        "episode_failure_reasons_json"
    ]


def test_d4_consumption_summary_mismatch_fails_closed(tmp_path: Path) -> None:
    episode = _write_episode(
        tmp_path / "summary_mismatch",
        learning_profile="assist_shadow",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(
            episode,
            effective_mode="assist",
            assist_eligible=True,
            unseen_seed_count=20,
        ),
    )
    _append_d4_consumption(episode, summary_mismatch=True)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_region_consumption_valid_publication_count"] == 1
    assert row["d4_region_consumption_summary_consistent"] is False
    assert row["d4_advice_control_adoption_count"] is None
    assert row[
        "d4_advice_control_adoption_count_unavailable_reason"
    ] == "d4_region_consumption_summary_mismatch"
    assert row["formal_acceptance_eligible"] is False
    assert "d4_region_consumption_summary_mismatch" in row[
        "episode_failure_reasons_json"
    ]


def test_nonconserving_projected_advice_is_counted_and_fails_formal_evidence(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "nonconserving",
        learning_profile="assist_shadow",
    )
    _append_d4_advice(
        episode,
        _d4_advice_payload(episode, quota_delta=1),
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_advice_invalid_publication_count"] == 1
    assert row["d4_advice_resource_quota_conservation_violation_count"] == 1
    assert row["d4_advice_invalid_reason_distribution_json"] == {
        "projected_recommendation_not_resource_conserving": 1
    }
    assert row["d4_advice_shadow_output_count"] is None
    assert row["formal_acceptance_eligible"] is False


def test_tampered_digest_flag_is_invalid_and_does_not_hide_mutation(
    tmp_path: Path,
) -> None:
    episode = _write_episode(
        tmp_path / "tampered",
        learning_profile="assist_shadow",
    )
    payload = _d4_advice_payload(episode, formal_mutated=True)
    payload["formal_decision_unchanged"] = True
    payload["recommendation"]["model_sha256"] = "f" * 64
    _append_d4_advice(episode, payload)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d4_advice_invalid_publication_count"] == 1
    assert row["d4_advice_formal_decision_mutation_count"] == 1
    assert row["d4_advice_formal_decision_unchanged_count"] == 0
    assert row["d4_advice_invalid_reason_distribution_json"] == {
        "formal_decision_digest_flag_mismatch": 1
    }
    assert row["d4_advice_stale_version_evidence_count"] == 1
    assert row["d4_advice_version_evidence_issue_reasons_json"] == {
        "recommendation_model_fingerprint_mismatch": 1
    }
    assert row["d4_advice_control_adoption_count"] is None
    assert row["formal_acceptance_eligible"] is False


def test_old_advice_schema_and_missing_advice_remain_unavailable_not_zero(
    tmp_path: Path,
) -> None:
    old = _write_episode(tmp_path / "old_schema", learning_profile="assist_shadow")
    _append_d4_advice(
        old,
        _d4_advice_payload(old),
        schema_version="d4-region-resource-advisory-runtime-v0",
    )
    missing = _write_episode(
        tmp_path / "missing_advice",
        learning_profile="assist_shadow",
    )
    missing_online_path = missing / "online_observations.jsonl"
    missing_online = [
        json.loads(line)
        for line in missing_online_path.read_text(encoding="utf-8").splitlines()
    ]
    d5_missing_fallback = next(
        record
        for record in missing_online
        if record["topic"] == "modules.d5.terminal_association"
    )
    del d5_missing_fallback["payload"]["fallback_reason"]
    _write_jsonl(missing_online_path, missing_online)
    missing_version = _write_episode(
        tmp_path / "missing_version",
        learning_profile="assist_shadow",
    )
    missing_version_payload = _d4_advice_payload(missing_version)
    del missing_version_payload["recommendation"]["actions"][0][
        "expected_plan_version"
    ]
    _append_d4_advice(missing_version, missing_version_payload)

    old_row = evaluate_scalable_3d_episode(old)
    missing_row = evaluate_scalable_3d_episode(missing)
    missing_version_row = evaluate_scalable_3d_episode(missing_version)

    assert old_row["d4_advice_publication_count"] == 1
    assert old_row["d4_advice_invalid_publication_count"] == 1
    assert old_row["d4_advice_stale_version_evidence_count"] == 1
    assert old_row["d4_advice_shadow_output_count"] is None
    assert missing_row["d4_advice_publication_count"] == 0
    assert missing_row["d4_advice_shadow_output_count"] is None
    assert missing_row["d4_advice_shadow_output_count_unavailable_reason"] == (
        "d4_region_resource_advice_missing"
    )
    assert missing_row["d5_model_fallback_event_count"] is None
    assert missing_row["d5_model_fallback_event_count_availability"] == "unavailable"
    assert missing_row["formal_acceptance_eligible"] is False
    assert missing_version_row["d4_advice_missing_version_evidence_count"] == 1
    assert missing_version_row["d4_advice_version_evidence_issue_count"] == 1
    assert missing_version_row["d4_advice_shadow_output_count"] is None


def test_five_meter_evidence_does_not_imply_success_or_identity_correctness(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "physical", physical_proximity=True)

    row = evaluate_scalable_3d_episode(episode)

    assert row["offline_proximity_within_5m_count"] == 1
    assert row["offline_proximity_unique_target_count"] == 1
    assert row["offline_truth_labels_read"] is True
    assert row["offline_proximity_identity_evaluable_count"] == 0
    assert row["offline_proximity_identity_correct_count"] is None
    assert (
        row["offline_proximity_identity_correct_rate_unavailable_reason"]
        == "offline_truth_labels_lack_global_track_mapping"
    )
    assert row["mission_success"] is None
    assert row["mission_success_unavailable_reason"] == (
        "five_meter_proximity_is_not_mission_success"
    )


def test_dirty_manifest_is_descriptive_and_not_formal_evidence(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "dirty", dirty=True)
    row = evaluate_scalable_3d_episode(episode)
    aggregate = aggregate_scalable_3d_episodes(
        [row], bootstrap_resamples=100, bootstrap_rng_seed=20260720
    )

    assert row["repository_dirty"] is True
    # Finalization happens when a report bundle is generated.
    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        tmp_path / "dirty_report",
        inputs=Scalable3DOfflineEvaluationInputs((episode,)),
        bootstrap_resamples=100,
    )
    assert outputs["markdown"].is_file()
    written = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert written["repository_dirty_episode_count"] == 1
    assert written["formal_acceptance_eligible_episode_count"] == 0
    assert written["groups"][0]["inference_status"] == "descriptive_only_single_seed"
    metric = written["groups"][0]["metric_statistics"]["d1_track_count"]
    assert metric["bootstrap_ci95_low"] is None
    assert metric["bootstrap_unavailable_reason"] == "single_seed_descriptive_only"
    assert aggregate["groups"][0]["inference_status"] == "descriptive_only_single_seed"


def test_report_bundle_bootstraps_distinct_seeds_and_writes_all_artifacts(
    tmp_path: Path,
) -> None:
    first = _write_episode(
        tmp_path / "suite" / "seed_1",
        seed=1,
        learning_profile="assist_shadow",
    )
    second = _write_episode(
        tmp_path / "suite" / "seed_2",
        seed=2,
        learning_profile="assist_shadow",
    )
    _append_d4_advice(first, _d4_advice_payload(first, inference_latency_ms=1.0))
    _append_d4_advice(second, _d4_advice_payload(second, inference_latency_ms=3.0))
    discovered = discover_scalable_3d_episode_dirs(episode_roots=[tmp_path / "suite"])

    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=Scalable3DOfflineEvaluationInputs(discovered),
        bootstrap_resamples=200,
        bootstrap_rng_seed=20260720,
    )

    assert set(outputs) == {
        "per_episode_seed_csv",
        "aggregate_json",
        "module_performance_evidence",
        "markdown",
        "stage_timing_curve",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in outputs.values())
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["episode_count"] == 2
    assert aggregate["episode_evidence_status_distribution"] == {
        "descriptive_clean_source_calibration": 2
    }
    assert len(aggregate["groups"]) == 1
    group = aggregate["groups"][0]
    assert group["target_count"] == 50
    assert group["camera_count"] == 54
    assert group["seed_count"] == 2
    assert group["inference_status"] == "bootstrap_across_distinct_seed_means"
    assert (
        group["metric_statistics"]["d1_track_count"]["bootstrap_availability"]
        == "available"
    )
    assert group["metric_statistics"]["current_schema_contract_match"]["mean"] == 1.0
    assert group["d4_advice_requested_mode_distribution"] == {"assist": 2}
    assert group["d4_advice_effective_mode_distribution"] == {"shadow": 2}
    assert (
        group["metric_statistics"]["d4_advice_inference_latency_p50_ms"][
            "bootstrap_availability"
        ]
        == "available"
    )
    assert set(group["stage_timing"]) == {
        "module.d1_fusion",
        "module.d3_assignment",
    }
    assert sum(
        item["pooled_wall_time_share"] for item in group["stage_timing"].values()
    ) == pytest.approx(1.0)
    with outputs["per_episode_seed_csv"].open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert "stage__module_d1_fusion__call_count" in rows[0]
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "五米接近仅是离线物理诊断" in markdown
    assert "不从 2v2/5v5 名称推断规模" in markdown
    assert "bundle 能加载" in markdown
    assert "`assist_eligible` 不是控制生效" in markdown
    assert "control adoption 只接受通过合同与 summary 审计" in markdown
    assert "d6-scalable3d-schema-registry-v1" in markdown
    assert "schema current" in markdown
    assert "descriptive clean-source calibration" in markdown


def test_batch_root_discovery_excludes_sidecar_manifest_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "batch"
    first = _write_episode(root / "20v20" / "seed_1", seed=1, target_count=20)
    second = _write_episode(root / "50v50" / "seed_2", seed=2, target_count=50)
    _write_sidecar_manifests(first)
    _write_sidecar_manifests(second)

    discovered = discover_scalable_3d_episode_dirs(episode_roots=[root])

    assert discovered == (first.resolve(), second.resolve())
    assert all(path.name.startswith("seed_") for path in discovered)


def test_batch_root_discovery_keeps_episode_with_missing_online_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "batch_with_incomplete_episode"
    complete = _write_episode(root / "20v20" / "seed_1", seed=1, target_count=20)
    incomplete = _write_episode(root / "20v20" / "seed_2", seed=2, target_count=20)
    (incomplete / "online_observations.jsonl").unlink()
    _write_sidecar_manifests(complete)
    _write_sidecar_manifests(incomplete)

    discovered = discover_scalable_3d_episode_dirs(episode_roots=[root])

    assert discovered == (complete.resolve(), incomplete.resolve())
    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        tmp_path / "incomplete_report",
        inputs=Scalable3DOfflineEvaluationInputs(discovered),
        bootstrap_resamples=50,
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["episode_count"] == 2
    with outputs["per_episode_seed_csv"].open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    incomplete_row = next(row for row in rows if row["seed"] == "2")
    assert incomplete_row["online_truth_field_violation_count"] == ""
    assert (
        incomplete_row["online_truth_field_violation_count_availability"]
        == "unavailable"
    )
    assert incomplete_row["episode_evidence_status"] == (
        "descriptive_or_incomplete_evidence"
    )


def test_explicit_episode_directory_remains_supported_with_sidecars(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "explicit" / "seed_3", seed=3)
    _write_sidecar_manifests(episode)

    discovered = discover_scalable_3d_episode_dirs(episode_dirs=[episode])

    assert discovered == (episode.resolve(),)
    row = evaluate_scalable_3d_episode(discovered[0])
    assert row["episode_evidence_status"] == (
        "descriptive_clean_source_calibration"
    )


def test_missing_online_records_remain_unavailable_during_status_finalization(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "missing_online_records")
    (episode / "online_observations.jsonl").unlink()

    row = evaluate_scalable_3d_episode(episode)

    assert row["online_truth_field_violation_count"] is None
    assert row["online_truth_field_violation_count_availability"] == "unavailable"
    assert row["online_truth_field_violation_count_unavailable_reason"] == (
        "artifact_missing:online_observations.jsonl"
    )
    assert row["formal_acceptance_eligible"] is False
    assert row["episode_evidence_status"] == "descriptive_or_incomplete_evidence"


def test_none_summary_count_remains_unavailable_not_zero(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "none_summary_count")
    summary_path = episode / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["online_truth_use_count"] = None
    _write_json(summary_path, summary)

    row = evaluate_scalable_3d_episode(episode)

    assert row["online_truth_use_count"] is None
    assert row["online_truth_use_count_availability"] == "unavailable"
    assert row["online_truth_use_count_unavailable_reason"] == (
        "summary_online_truth_use_count_invalid"
    )
    assert row["formal_acceptance_eligible"] is False


def test_cli_accepts_episode_root_and_generates_bundle(tmp_path: Path) -> None:
    root = tmp_path / "cli_suite"
    _write_episode(root / "seed_3", seed=3)
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_scalable_3d_offline_evaluation.py"
    )
    output = tmp_path / "cli_report"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--episode-root",
            str(root),
            "--output-dir",
            str(output),
            "--bootstrap-resamples",
            "50",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "aggregate_json:" in completed.stdout
    assert (output / "scalable_3d_offline_aggregate.json").is_file()


def test_cli_accepts_explicit_episode_directory(tmp_path: Path) -> None:
    episode = _write_episode(tmp_path / "explicit_cli" / "seed_4", seed=4)
    _write_sidecar_manifests(episode)
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_scalable_3d_offline_evaluation.py"
    )
    output = tmp_path / "explicit_cli_report"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--episode-dir",
            str(episode),
            "--output-dir",
            str(output),
            "--bootstrap-resamples",
            "50",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "aggregate_json:" in completed.stdout
    aggregate = json.loads(
        (output / "scalable_3d_offline_aggregate.json").read_text(encoding="utf-8")
    )
    assert aggregate["episode_count"] == 1
    assert aggregate["episode_evidence_status_distribution"] == {
        "descriptive_clean_source_calibration": 1
    }
