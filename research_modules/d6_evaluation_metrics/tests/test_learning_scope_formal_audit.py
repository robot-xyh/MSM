from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping

import pytest

import d6_evaluation_metrics.learning_scope_formal_audit as audit_module

from d6_evaluation_metrics.learning_scope_formal_audit import (
    LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION,
    LearningScopeFormalAuditInputs,
    ScopeEvidenceArtifacts,
    audit_learning_scope_formal_evidence,
    write_learning_scope_formal_audit_report,
)


_COMMIT = "1" * 40
_VERSIONS = {
    "d3_policy_version": "d3-scalable3d-rule-cost-v1",
    "d4_policy_version": "d4-region-resource-rule-v1",
    "d5_model_version": "d5-crossview-gnn-v1+" + "c" * 12,
    "d5_active_vision_policy_version": "d5-active-vision-rule-v1",
}
_VARIANT_COMPONENTS = {
    "R0": (),
    "G1": ("d5_graph",),
    "A1": ("d3",),
    "A2": ("d4",),
    "A3": ("d5_active_vision",),
    "C1": ("d3", "d4", "d5_graph", "d5_active_vision"),
    "F1": ("d3", "d4", "d5_graph", "d5_active_vision"),
}
_RUNTIME_NAMES = {
    "d3": "d3",
    "d4": "d4",
    "d5_graph": "d5",
    "d5_active_vision": "d5_active_vision",
}
_SENSOR_SCHEDULE = "scalable3d-paired-sensor-random-schedule-v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _tree_inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _file_sha(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _tree_sha(root: Path) -> str:
    return _digest(_tree_inventory(root))


def _write_bundle(path: Path, component: str = "d5_graph") -> Path:
    path.mkdir(parents=True)
    _write_json(
        path / "manifest.json",
        {
            "schema_version": "formal-audit-fixture-model-bundle-v1",
            "component": component,
            "admission": {
                "g1_assist_eligible": True,
                "default_model": False,
            },
        },
    )
    (path / "weights.pt").write_bytes(b"fixture-weights")
    return path


def _bundle_descriptor(
    path: Path,
    component: str = "d5_graph",
) -> dict[str, object]:
    inventory = _tree_inventory(path)
    return {
        "component": component,
        "manifest_sha256": _file_sha(path / "manifest.json"),
        "tree_sha256": _digest(inventory),
        "file_count": len(inventory),
        "total_size_bytes": sum(
            int(item["size_bytes"]) for item in inventory
        ),
    }


def _runtime(
    variant: str,
    *,
    adoption_mode: str,
    device: str,
    component_modes: Mapping[str, str] | None = None,
) -> dict[str, object]:
    disabled = {
        "requested_mode": "disabled",
        "effective_mode": "disabled",
        "bundle_requested": False,
        "bundle_loaded": False,
        "fallback_reason": None,
        "model_fingerprint": None,
    }
    runtime: dict[str, object] = {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": device,
        "d3": dict(disabled),
        "d4": {
            **disabled,
            "formal_unseen_seed_count": 0,
        },
        "d5": dict(disabled),
        "d5_active_vision": {
            **disabled,
            "assist_admitted": False,
        },
        "default_rule_path_preserved": True,
    }
    modes = dict(component_modes or {})
    for component in _VARIANT_COMPONENTS[variant]:
        runtime_name = _RUNTIME_NAMES[component]
        effective_mode = modes.get(component, adoption_mode)
        diagnostics: dict[str, object] = {
            "requested_mode": "assist",
            "effective_mode": effective_mode,
            "bundle_requested": True,
            "bundle_loaded": True,
            "fallback_reason": (
                None if effective_mode == "assist" else "shadow_only"
            ),
            "model_fingerprint": "c" * 64,
        }
        if component == "d4":
            diagnostics["formal_unseen_seed_count"] = 0
        if component == "d5_active_vision":
            diagnostics["assist_admitted"] = effective_mode == "assist"
        runtime[runtime_name] = diagnostics
    return runtime


def _parent_inventory(
    paired_variant: str = "G1",
    *,
    duration_s: float = 1.0,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    plan = {
        "variants": ["R0", paired_variant],
        "scenarios": ["nominal"],
        "scales": [5],
        "seeds": [1000],
        "duration_s": duration_s,
        "formal": True,
        "allow_rule_fallback": False,
        "training_seeds": [1, 2, 3],
    }
    cells = [
        {
            "cell_id": "00000__r0__nominal__5v5__seed_1000",
            "global_index": 0,
            "variant": "R0",
            "scenario": "nominal",
            "scale": 5,
            "seed": 1000,
            "comparison_key": "nominal|5|1000",
        },
        {
            "cell_id": (
                f"00001__{paired_variant.lower()}__nominal__5v5__seed_1000"
            ),
            "global_index": 1,
            "variant": paired_variant,
            "scenario": "nominal",
            "scale": 5,
            "seed": 1000,
            "comparison_key": "nominal|5|1000",
        },
    ]
    return plan, cells


def _write_scope(
    root: Path,
    *,
    variant: str,
    bundle: Path | None = None,
    bundles: Mapping[str, Path] | None = None,
    adoption_mode: str = "assist",
    component_modes: Mapping[str, str] | None = None,
    device: str = "cpu",
    physical_available: bool = True,
    complete: bool = True,
    paired_variant: str | None = None,
    scope_name: str | None = None,
    label: str | None = None,
    source_commit: str = _COMMIT,
    parent_duration_s: float = 1.0,
    exogenous_config_sha256: str = "e" * 64,
    sensor_schedule_version: str = _SENSOR_SCHEDULE,
    d5_candidate_edge_count: int = 1,
) -> ScopeEvidenceArtifacts:
    paired_variant = paired_variant or (
        variant if variant != "R0" else "G1"
    )
    required = list(_VARIANT_COMPONENTS[variant])
    component_bundles = dict(bundles or {})
    if bundle is not None:
        component_bundles.setdefault("d5_graph", bundle)
    missing_bundles = set(required) - set(component_bundles)
    if missing_bundles:
        raise ValueError(
            f"fixture bundles missing for components: {sorted(missing_bundles)}"
        )
    execution_root = root / (scope_name or variant.lower())
    execution_root.mkdir(parents=True)
    parent_plan, full_cells = _parent_inventory(
        paired_variant,
        duration_s=parent_duration_s,
    )
    global_index = 0 if variant == "R0" else 1
    parent_cell = full_cells[global_index]
    cell = {
        **parent_cell,
        "scope_index": 0,
        "shard_index": 0,
        "shard_sequence": 0,
    }
    shard_id = "shard_000_of_001"
    descriptor = {
        "shard_index": 0,
        "shard_id": shard_id,
        "cell_count": 1,
        "scope_indices": [0],
        "global_indices": [global_index],
        "cell_ids": [cell["cell_id"]],
        "cells_sha256": _digest([cell]),
    }
    runtime = _runtime(
        variant,
        adoption_mode=adoption_mode,
        device=device,
        component_modes=component_modes,
    )
    components = {
        component: _bundle_descriptor(
            component_bundles[component],
            component,
        )
        for component in required
    }
    binding_payload = {
        "required_components": required,
        "components": components,
    }
    preflight: dict[str, object]
    if variant == "R0":
        preflight = {
            "variant": "R0",
            "status": "deterministic_no_model",
            "required_components": [],
        }
    else:
        preflight = {
            "variant": variant,
            "status": "assist_resolved",
            "required_components": required,
            "diagnostics_sha256": _digest(runtime),
            "resolved_versions": dict(_VERSIONS),
        }
    parent_sha = _digest({"plan": parent_plan, "cells": full_cells})
    plan: dict[str, object] = {
        "schema_version": (
            "scalable3d-experiment-matrix-execution-plan-v1"
        ),
        "created_at_utc": "2026-07-26T00:00:00+00:00",
        "source": {
            "git_commit": source_commit,
            "repository_dirty": False,
        },
        "parent": {
            "experiment_matrix_schema": "scalable3d-experiment-matrix-v1",
            "formal": True,
            "plan": parent_plan,
            "plan_sha256": parent_sha,
            "full_cell_count": len(full_cells),
            "full_cells": full_cells,
        },
        "base_config": {
            "schema_version": "scalable3d-scenario-v1",
            "payload": {"schema_version": "scalable3d-scenario-v1"},
            "sha256": _digest(
                {"schema_version": "scalable3d-scenario-v1"}
            ),
        },
        "learning_bundles": {
            "schema_version": (
                "scalable3d-experiment-matrix-model-bundle-binding-v1"
            ),
            **binding_payload,
            "binding_sha256": _digest(binding_payload),
            "preflight_device": device,
            "variant_preflight": {variant: preflight},
        },
        "scope": {
            "variants": [variant],
            "cell_count": 1,
            "cells_sha256": _digest([cell]),
            "cells": [cell],
        },
        "sharding": {
            "strategy": "scope_index_modulo_v1",
            "shard_count": 1,
            "shards": [descriptor],
        },
        "evidence_class": "formal_parent_scope",
    }
    plan["execution_plan_sha256"] = _digest(plan)
    plan_path = execution_root / "experiment_matrix_execution_plan.json"
    _write_json(plan_path, plan)

    cell_dir = (
        execution_root / "shards" / shard_id / "cells" / str(cell["cell_id"])
    )
    episode = cell_dir / "episode"
    episode.mkdir(parents=True)
    config: dict[str, object] = {
        "schema_version": "scalable3d-scenario-v1",
        "episode_id": f"episode-{variant.lower()}",
        "scenario_name": "nominal",
        "scenario_version": "nominal-v1",
        "seed": 1000,
        "target_count": 5,
        "resource_count": 5,
        "recon_count": 1,
        **_VERSIONS,
        "metadata": {
            "experiment_matrix_schema": (
                "scalable3d-experiment-matrix-v1"
            ),
            "scenario_family": "nominal",
            "algorithm_variant": variant,
            "comparison_key": "nominal|5|1000",
            "full_system_validation": False,
            "matrix_execution_plan_sha256": plan[
                "execution_plan_sha256"
            ],
            "matrix_parent_plan_sha256": parent_sha,
            "learning_runtime": runtime,
        },
    }
    config_bytes = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "episode_id": f"episode-{variant.lower()}",
        "scenario_name": "nominal",
        "scenario_version": "nominal-v1",
        "seed": 1000,
        "git_commit": source_commit,
        "repository_dirty": False,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v2",
        "d1_model_version": "d1-v1",
        "d2_model_version": "d2-v1",
        **_VERSIONS,
        "d7_model_version": "d7-v1",
        "threshold_version": "threshold-v1",
    }
    summary: dict[str, object] = {
        "episode_id": f"episode-{variant.lower()}",
        "scenario_name": "nominal",
        "scenario_version": "nominal-v1",
        "seed": 1000,
        "target_count": 5,
        "resource_count": 5,
        "recon_count": 1,
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "module_final_diagnostics": {
            "schema_version": "scalable3d-module-stack-v1",
            "learning_runtime": runtime,
            "online_truth_use_count": 0,
        },
    }
    if physical_available:
        summary["intercepted_target_count"] = 0
    _write_json(episode / "scenario_config.json", config)
    _write_json(episode / "manifest.json", manifest)
    _write_json(episode / "summary.json", summary)
    graph_assist = (
        "d5_graph" in required
        and runtime["d5"]["effective_mode"] == "assist"
    )
    d5_payload = {
        "timestamp": 0.5,
        "camera_batch_count": 1,
        "tracklet_count": 2,
        "graph_node_count": 2,
        "graph_edge_count": d5_candidate_edge_count,
        "probability_source": (
            "loaded_edge_model"
            if graph_assist
            else "deterministic_geometry_rule"
        ),
        "scoring_status": (
            "model_scored"
            if graph_assist
            else "rule_fallback_model_missing"
        ),
        "fallback_reason": (
            None
            if graph_assist
            else "model_missing"
        ),
        "diagnostics": {
            "candidate_tracklet_edges": d5_candidate_edge_count,
            "max_tracklet_candidate_edges_per_node": 4,
            "tracklet_candidate_budget_dropped": 0,
        },
        "bindings": [
            {
                "cluster_key": "cluster-1",
                "global_track_id": "GT-0001",
                "decision_state": "bound",
                "cost": 0.1,
                "supporting_tracklet_keys": ["CAM-1:T-1"],
            }
        ],
    }
    _write_jsonl(
        episode / "online_observations.jsonl",
        [
            {
                "sequence": 0,
                "topic": "modules.d5.terminal_association",
                "source": "D5",
                "timestamp": 0.5,
                "schema_version": "d5-scalable3d-association-v1",
                "payload": d5_payload,
            }
        ],
    )
    _write_jsonl(episode / "offline_proximity_intercepts.jsonl", [])
    (episode / "stage_timings.csv").write_text(
        "schema_version,stage,call_count,wall_time_s,mean_wall_time_ms,"
        "p50_wall_time_ms,p95_wall_time_ms,max_wall_time_ms,"
        "distribution_available,distribution_unavailable_reason\n"
        "scalable3d-stage-timings-v2,module_stack,1,0.01,10,10,10,10,"
        "true,\n",
        encoding="utf-8",
    )

    episode_relative = episode.relative_to(execution_root).as_posix()
    record: dict[str, object] = {
        "schema_version": "scalable3d-experiment-matrix-cell-result-v1",
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "parent_plan_sha256": parent_sha,
        "source_git_commit": source_commit,
        "cell": cell,
        "episode_relative_path": episode_relative,
        "episode_id": f"episode-{variant.lower()}",
        "paired_exogenous_config_sha256": exogenous_config_sha256,
        "sensor_random_schedule_version": sensor_schedule_version,
        "artifact_tree_sha256": _tree_sha(episode),
        "metrics": {
            "finite_state": True,
            "online_truth_use_count": 0,
            "real_time_factor": 1.0,
        },
        "status": "complete",
    }
    if physical_available:
        record["metrics"]["intercepted_target_count"] = 0
    if variant != "R0":
        record["learning_runtime"] = {
            "bundle_binding_sha256": plan["learning_bundles"][
                "binding_sha256"
            ],
            "diagnostics_sha256": _digest(runtime),
            "resolved_versions": dict(_VERSIONS),
        }
    result_path = cell_dir / "cell_result.json"
    _write_json(result_path, record)

    shard_dir = execution_root / "shards" / shard_id
    shard_plan = {
        "schema_version": "scalable3d-experiment-matrix-shard-plan-v1",
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "source_git_commit": source_commit,
        "parent_plan_sha256": parent_sha,
        "descriptor": descriptor,
        "cells": [cell],
        "cells_sha256": _digest([cell]),
    }
    shard_plan_path = shard_dir / "shard_plan.json"
    _write_json(shard_plan_path, shard_plan)
    progress = {
        "schema_version": (
            "scalable3d-experiment-matrix-shard-progress-v1"
        ),
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "sequence": 0,
        "cell_id": cell["cell_id"],
        "global_index": global_index,
        "scope_index": 0,
        "shard_index": 0,
        "shard_sequence": 0,
        "cell_result_relative_path": result_path.relative_to(
            execution_root
        ).as_posix(),
        "cell_result_sha256": _file_sha(result_path),
        "episode_artifact_tree_sha256": record["artifact_tree_sha256"],
    }
    progress_path = shard_dir / "progress.jsonl"
    _write_jsonl(progress_path, [progress])
    checkpoint = {
        "schema_version": (
            "scalable3d-experiment-matrix-shard-checkpoint-v1"
        ),
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "source_git_commit": source_commit,
        "shard_index": 0,
        "shard_id": shard_id,
        "expected_cell_count": 1,
        "completed_cell_count": 1,
        "next_sequence": 1,
        "status": "complete",
        "resume_count": 0,
        "recovered_checkpoint_row_count": 0,
        "progress_sha256": _file_sha(progress_path),
    }
    checkpoint_path = shard_dir / "checkpoint.json"
    _write_json(checkpoint_path, checkpoint)

    merge = execution_root / "merged_scope"
    merge.mkdir()
    manifest_path = merge / "experiment_matrix_scope_manifest.json"
    merge_manifest = {
        "schema_version": "scalable3d-experiment-matrix-scope-merge-v1",
        "source_git_commit": source_commit,
        "source_repository_dirty": False,
        "execution_plan_sha256": plan["execution_plan_sha256"],
        "parent_plan_sha256": parent_sha,
        "parent_formal": True,
        "parent_full_cell_count": len(full_cells),
        "scope_variants": [variant],
        "scope_expected_cell_count": 1,
        "scope_completed_cell_count": 1 if complete else 0,
        "scope_complete": complete,
        "formal_scope_complete": complete,
        "full_matrix_complete": False,
        "formal_matrix_complete": False,
        "legacy_full_matrix_manifest_written": False,
        "shard_strategy": "scope_index_modulo_v1",
        "shard_count": 1,
        "shards": [
            {
                "shard_index": 0,
                "shard_id": shard_id,
                "cell_count": 1,
                "shard_plan_sha256": _file_sha(shard_plan_path),
                "progress_sha256": _file_sha(progress_path),
                "checkpoint_sha256": _file_sha(checkpoint_path),
            }
        ],
        "paired_random_schedule_version": sensor_schedule_version,
        "status": "formal_scope_complete" if complete else "running",
    }
    _write_json(manifest_path, merge_manifest)
    cells_path = merge / "experiment_matrix_scope_cells.csv"
    merged_row = {
        "cell_index": global_index,
        "scope_index": 0,
        "variant": variant,
        "scenario": "nominal",
        "scale": 5,
        "seed": 1000,
        "comparison_key": "nominal|5|1000",
        "paired_exogenous_config_sha256": exogenous_config_sha256,
        "sensor_random_schedule_version": sensor_schedule_version,
        "episode_id": f"episode-{variant.lower()}",
        "episode_relative_path": episode_relative,
        "finite_state": True,
        "online_truth_use_count": 0,
        "real_time_factor": 1.0,
        "intercepted_target_count": (
            0 if physical_available else ""
        ),
        "cell_result_sha256": _file_sha(result_path),
        "episode_artifact_tree_sha256": record["artifact_tree_sha256"],
    }
    with cells_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(merged_row))
        writer.writeheader()
        writer.writerow(merged_row)
    episode_dirs_path = merge / "episode_dirs.json"
    _write_json(
        episode_dirs_path,
        {
            "schema_version": (
                "scalable3d-experiment-matrix-scope-merge-v1"
            ),
            "execution_plan_sha256": plan["execution_plan_sha256"],
            "episode_count": 1,
            "paths_relative_to_execution_root": [episode_relative],
        },
    )
    (merge / "SHA256SUMS").write_text(
        "".join(
            f"{_file_sha(path)}  {path.name}\n"
            for path in sorted(
                (manifest_path, cells_path, episode_dirs_path),
                key=lambda item: item.name,
            )
        ),
        encoding="utf-8",
    )
    return ScopeEvidenceArtifacts(
        execution_plan_path=plan_path,
        merge_dir=merge,
        label=label or variant,
    )


def _complete_inputs(tmp_path: Path) -> tuple[
    LearningScopeFormalAuditInputs,
    Path,
]:
    bundle = _write_bundle(tmp_path / "bundle")
    r0 = _write_scope(tmp_path / "scopes", variant="R0", bundle=bundle)
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
    )
    return (
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
            expected_preflight_device="cpu",
        ),
        bundle,
    )


def _write_component_bundles(
    root: Path,
    variant: str,
) -> dict[str, Path]:
    return {
        component: _write_bundle(root / component, component)
        for component in _VARIANT_COMPONENTS[variant]
    }


def _variant_pair(
    tmp_path: Path,
    variant: str,
    *,
    component_modes: Mapping[str, str] | None = None,
    d5_candidate_edge_count: int = 1,
) -> tuple[LearningScopeFormalAuditInputs, dict[str, Path]]:
    bundles = _write_component_bundles(tmp_path / "bundles", variant)
    r0 = _write_scope(
        tmp_path / "scopes",
        variant="R0",
        paired_variant=variant,
        scope_name=f"r0_for_{variant.lower()}",
    )
    learned = _write_scope(
        tmp_path / "scopes",
        variant=variant,
        paired_variant=variant,
        bundles=bundles,
        component_modes=component_modes,
        d5_candidate_edge_count=d5_candidate_edge_count,
    )
    return (
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
            expected_preflight_device="cpu",
        ),
        bundles,
    )


def _positive_adoption_metrics() -> dict[str, object]:
    return {
        "variant_execution_valid": True,
        "d3_learning_applied_count_availability": "available",
        "d3_learning_applied_count": 1,
        "d4_advice_control_adoption_count_availability": "available",
        "d4_advice_control_adoption_count": 1,
        "d5_probability_source_availability": "available",
        "d5_probability_source": "loaded_edge_model",
        "d5_scoring_status_availability": "available",
        "d5_scoring_status": "model_scored",
        "d5_model_fallback_event_count_availability": "available",
        "d5_model_fallback_event_count": 0,
        "d5_candidate_edge_count_availability": "available",
        "d5_candidate_edge_count": 1,
        "d5_active_vision_assist_adopted_count_availability": "available",
        "d5_active_vision_assist_adopted_count": 1,
        "d5_active_vision_assist_applied_count_availability": "available",
        "d5_active_vision_assist_applied_count": 1,
    }


def _set_component_adoption(
    metrics: dict[str, object],
    component: str,
    *,
    availability: str,
    value: int | None,
) -> None:
    fields = {
        "d3": ("d3_learning_applied_count",),
        "d4": ("d4_advice_control_adoption_count",),
        "d5_graph": ("d5_candidate_edge_count",),
        "d5_active_vision": (
            "d5_active_vision_assist_adopted_count",
            "d5_active_vision_assist_applied_count",
        ),
    }[component]
    for field in fields:
        metrics[f"{field}_availability"] = availability
        metrics[field] = value


def _patch_learned_offline_metrics(
    monkeypatch: pytest.MonkeyPatch,
    overrides: Mapping[str, object],
) -> None:
    original = audit_module.evaluate_scalable_3d_episode

    def evaluate_with_overrides(episode_dir: str | Path) -> dict[str, object]:
        row = original(episode_dir)
        config = json.loads(
            (Path(episode_dir) / "scenario_config.json").read_text(
                encoding="utf-8"
            )
        )
        variant = config["metadata"]["algorithm_variant"]
        if variant != "R0":
            row.update(overrides)
        return row

    monkeypatch.setattr(
        audit_module,
        "evaluate_scalable_3d_episode",
        evaluate_with_overrides,
    )


def test_complete_g1_scope_with_r0_pair_passes_and_writes_report(
    tmp_path: Path,
) -> None:
    inputs, bundle = _complete_inputs(tmp_path)

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles={"d5_graph": bundle},
    )

    assert result["schema_version"] == LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION
    assert result["verdict"] == "pass"
    assert result["formal_evidence_eligible"] is True
    assert result["model_promotion"]["allowed"] is False
    assert result["learned_scope"]["accepted_cell_count"] == 1
    assert result["r0_pairing"]["available_pair_count"] == 1
    assert result["r0_pairing"]["all_required_pairs_non_degraded"] is True
    assert (
        result["learned_scope"]["cells"][0]["assist_adoption_status"]
        == "actual_assist_adopted"
    )

    paths = write_learning_scope_formal_audit_report(
        tmp_path / "report",
        result,
    )
    assert all(path.is_file() for path in paths.values())
    assert "不授予模型晋级" in paths["markdown"].read_text(
        encoding="utf-8"
    )


def test_missing_r0_is_unavailable_and_fail_closed(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(learned_scope=learned),
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert result["r0_pairing"]["availability"] == "unavailable"
    assert "r0_scope_evidence_missing" in result["blockers"]
    pair = result["r0_pairing"]["pairs"][0]
    assert pair["availability"] == "unavailable"
    assert pair["non_degraded"] is None


def test_shadow_or_fallback_is_not_actual_adoption(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    r0 = _write_scope(tmp_path / "scopes", variant="R0", bundle=bundle)
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
        adoption_mode="shadow",
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
        ),
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    cell = result["learned_scope"]["cells"][0]
    assert cell["assist_adoption_status"] == "unavailable_or_not_adopted"
    assert any(
        "cell_learning_component_not_assist:d5_graph" in reason
        or "cell_actual_assist_not_adopted:d5_graph" in reason
        for reason in cell["failure_reasons"]
    )


def test_bundle_tree_tamper_fails_before_admission(tmp_path: Path) -> None:
    inputs, bundle = _complete_inputs(tmp_path)
    (bundle / "weights.pt").write_bytes(b"tampered")

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert "model_bundle_binding_mismatch:d5_graph" in result["blockers"]
    assert result["learned_scope"]["bundle_binding_status"] == "fail_closed"


def test_preflight_device_mismatch_fails_closed(tmp_path: Path) -> None:
    inputs, bundle = _complete_inputs(tmp_path)
    mismatched = LearningScopeFormalAuditInputs(
        learned_scope=inputs.learned_scope,
        r0_scopes=inputs.r0_scopes,
        expected_preflight_device="cuda:0",
    )

    result = audit_learning_scope_formal_evidence(
        mismatched,
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert "model_bundle_preflight_device_mismatch" in result["blockers"]


def test_missing_physical_result_remains_unavailable(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    r0 = _write_scope(tmp_path / "scopes", variant="R0", bundle=bundle)
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
        physical_available=False,
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
        ),
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    cell = result["learned_scope"]["cells"][0]
    assert cell["physical_result_status"] == "unavailable"
    assert "cell_episode_physical_result_missing" in cell["failure_reasons"]
    pair = result["r0_pairing"]["pairs"][0]
    assert pair["availability"] == "unavailable"
    assert pair["non_degraded"] is None


def test_incomplete_scope_merge_fails_closed(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    r0 = _write_scope(tmp_path / "scopes", variant="R0", bundle=bundle)
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
        complete=False,
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
        ),
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert any(
        reason.startswith("scope_merge_field_mismatch:")
        for reason in result["blockers"]
    )


@pytest.mark.parametrize(
    "tamper_kind",
    ("content", "declared_digest"),
)
def test_execution_plan_content_or_digest_tamper_fails_closed(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    inputs, bundle = _complete_inputs(tmp_path)
    plan_path = inputs.learned_scope.execution_plan_path
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if tamper_kind == "content":
        plan["created_at_utc"] = "2026-07-26T01:00:00+00:00"
    else:
        plan["execution_plan_sha256"] = "f" * 64
    _write_json(plan_path, plan)

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert "execution_plan_digest_mismatch" in result["blockers"]


@pytest.mark.parametrize(
    ("tamper_kind", "expected_blocker"),
    (
        (
            "merge_checksum",
            "scope_merge_checksum_mismatch:"
            "experiment_matrix_scope_manifest.json",
        ),
        (
            "progress",
            "scope_merge_shard_digest_mismatch:"
            "shard_000_of_001:progress_sha256",
        ),
        (
            "checkpoint",
            "scope_merge_shard_digest_mismatch:"
            "shard_000_of_001:checkpoint_sha256",
        ),
        ("episode_tree", "cell_episode_artifact_tree_mismatch"),
    ),
)
def test_persisted_scope_artifact_tamper_fails_closed(
    tmp_path: Path,
    tamper_kind: str,
    expected_blocker: str,
) -> None:
    inputs, bundle = _complete_inputs(tmp_path)
    learned = inputs.learned_scope
    execution_root = learned.execution_plan_path.parent
    if tamper_kind == "merge_checksum":
        checksum = learned.merge_dir / "SHA256SUMS"
        lines = checksum.read_text(encoding="utf-8").splitlines()
        lines = [
            (
                "0" * 64 + line[64:]
                if line.endswith(
                    "experiment_matrix_scope_manifest.json"
                )
                else line
            )
            for line in lines
        ]
        checksum.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper_kind == "progress":
        path = (
            execution_root
            / "shards"
            / "shard_000_of_001"
            / "progress.jsonl"
        )
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    elif tamper_kind == "checkpoint":
        path = (
            execution_root
            / "shards"
            / "shard_000_of_001"
            / "checkpoint.json"
        )
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    else:
        path = next(
            execution_root.glob(
                "shards/*/cells/*/episode/summary.json"
            )
        )
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles={"d5_graph": bundle},
    )

    assert result["verdict"] == "fail_closed"
    assert expected_blocker in result["blockers"]


def test_duplicate_r0_comparison_key_is_unavailable_and_fail_closed(
    tmp_path: Path,
) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
    )
    r0_a = _write_scope(
        tmp_path / "scopes",
        variant="R0",
        scope_name="r0_a",
        label="R0-a",
    )
    r0_b = _write_scope(
        tmp_path / "scopes",
        variant="R0",
        scope_name="r0_b",
        label="R0-b",
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0_a, r0_b),
        ),
        model_bundles={"d5_graph": bundle},
    )

    pair = result["r0_pairing"]["pairs"][0]
    assert result["verdict"] == "fail_closed"
    assert pair["availability"] == "unavailable"
    assert pair["non_degraded"] is None
    assert pair["unavailable_reason"] == "r0_comparison_duplicated"
    assert (
        "r0_comparison_duplicated:nominal|5|1000:G1"
        in result["blockers"]
    )


@pytest.mark.parametrize(
    ("r0_kwargs", "expected_reason"),
    (
        (
            {"source_commit": "2" * 40},
            "r0_source_commit_mismatch",
        ),
        (
            {"parent_duration_s": 2.0},
            "r0_parent_plan_mismatch",
        ),
        (
            {"exogenous_config_sha256": "d" * 64},
            "r0_exogenous_config_mismatch",
        ),
        (
            {"sensor_schedule_version": "paired-schedule-v2"},
            "r0_sensor_schedule_version_mismatch",
        ),
    ),
)
def test_r0_lineage_mismatch_is_unavailable_and_fail_closed(
    tmp_path: Path,
    r0_kwargs: Mapping[str, object],
    expected_reason: str,
) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    learned = _write_scope(
        tmp_path / "scopes",
        variant="G1",
        bundle=bundle,
    )
    r0 = _write_scope(
        tmp_path / "scopes",
        variant="R0",
        scope_name="r0_mismatch",
        **r0_kwargs,
    )

    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=learned,
            r0_scopes=(r0,),
        ),
        model_bundles={"d5_graph": bundle},
    )

    pair = result["r0_pairing"]["pairs"][0]
    assert result["verdict"] == "fail_closed"
    assert pair["availability"] == "unavailable"
    assert pair["non_degraded"] is None
    assert expected_reason in pair["failure_reasons"]
    assert (
        f"{expected_reason}:nominal|5|1000:G1"
        in result["blockers"]
    )


@pytest.mark.parametrize(
    ("variant", "component", "adoption_state"),
    [
        (variant, component, state)
        for variant, component in (
            ("A1", "d3"),
            ("A2", "d4"),
            ("A3", "d5_active_vision"),
        )
        for state in ("bundle_loaded_only", "shadow", "zero_adoption")
    ],
)
def test_single_component_loaded_shadow_or_zero_adoption_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    component: str,
    adoption_state: str,
) -> None:
    component_modes = (
        {component: "shadow"}
        if adoption_state == "shadow"
        else None
    )
    inputs, bundles = _variant_pair(
        tmp_path,
        variant,
        component_modes=component_modes,
    )
    metrics = _positive_adoption_metrics()
    if adoption_state == "bundle_loaded_only":
        _set_component_adoption(
            metrics,
            component,
            availability="unavailable",
            value=None,
        )
    elif adoption_state == "zero_adoption":
        _set_component_adoption(
            metrics,
            component,
            availability="available",
            value=0,
        )
    _patch_learned_offline_metrics(monkeypatch, metrics)

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles=bundles,
    )

    cell = result["learned_scope"]["cells"][0]
    assert result["verdict"] == "fail_closed"
    assert cell["assist_adoption_status"] == "unavailable_or_not_adopted"
    if adoption_state == "shadow":
        assert (
            f"cell_learning_component_not_assist:{component}"
            in cell["failure_reasons"]
        )
    else:
        assert (
            f"cell_actual_assist_not_adopted:{component}"
            in cell["failure_reasons"]
        )


@pytest.mark.parametrize("variant", ("C1", "F1"))
@pytest.mark.parametrize(
    "missing_component",
    ("d3", "d4", "d5_graph", "d5_active_vision"),
)
def test_composite_variant_missing_any_required_adoption_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    missing_component: str,
) -> None:
    inputs, bundles = _variant_pair(tmp_path, variant)
    metrics = _positive_adoption_metrics()
    _set_component_adoption(
        metrics,
        missing_component,
        availability="available",
        value=0,
    )
    _patch_learned_offline_metrics(monkeypatch, metrics)

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles=bundles,
    )

    cell = result["learned_scope"]["cells"][0]
    assert result["verdict"] == "fail_closed"
    assert cell["assist_adoption_status"] == "unavailable_or_not_adopted"
    assert (
        f"cell_actual_assist_not_adopted:{missing_component}"
        in cell["failure_reasons"]
    )


def test_d5_graph_zero_candidate_edges_is_not_actual_adoption(
    tmp_path: Path,
) -> None:
    inputs, bundles = _variant_pair(
        tmp_path,
        "G1",
        d5_candidate_edge_count=0,
    )

    result = audit_learning_scope_formal_evidence(
        inputs,
        model_bundles=bundles,
    )

    cell = result["learned_scope"]["cells"][0]
    assert result["verdict"] == "fail_closed"
    assert cell["assist_adoption_status"] == "unavailable_or_not_adopted"
    assert (
        "cell_actual_assist_not_adopted:d5_graph"
        in cell["failure_reasons"]
    )
