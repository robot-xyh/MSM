from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import d2_data_association.scalable_3d_identity_blocker_pack as pack_module

from d2_data_association import (
    FormalIdentityAuditScope,
    FormalIdentityBlockerAuditError,
    discover_formal_identity_audit_scope,
)


_COMMIT = "8" * 40


def test_cli_help_uses_documented_repo_root_pythonpath() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = (
        ".:research_modules/d2_data_association"
    )

    result = subprocess.run(
        [
            sys.executable,
            "research_modules/d2_data_association/scripts/"
            "run_scalable_3d_identity_blocker_audit.py",
            "--help",
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--execution-root" in result.stdout
    assert "--episode-root" in result.stdout


def _encoded(value) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encoded(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_formal_scope(root: Path) -> tuple[Path, str]:
    execution_root = root / "formal"
    execution_root.mkdir()
    cells = []
    reasons = (
        ["multiple_truth_targets_for_global_track"] * 27
        + ["source_observation_outside_lineage_window"] * 9
        + [None]
    )
    for index, reason in enumerate(reasons):
        if index < 4:
            scale = 100
        elif index < 27:
            scale = 200
        else:
            scale = 5
        scenario = (
            "nominal"
            if index < 27 or reason is None
            else "delayed_noisy"
        )
        cells.append(
            {
                "cell_id": (
                    f"{index:05d}__r0__{scenario}__"
                    f"{scale}v{scale}__seed_{1000 + index}"
                ),
                "comparison_key": f"{scenario}|{scale}|{1000 + index}",
                "global_index": index,
                "scale": scale,
                "scenario": scenario,
                "scope_index": index,
                "seed": 1000 + index,
                "shard_index": 0,
                "shard_sequence": index,
                "variant": "R0",
            }
        )
    descriptor = {
        "cell_count": len(cells),
        "cell_ids": [cell["cell_id"] for cell in cells],
        "cells_sha256": _canonical_digest(cells),
        "global_indices": [cell["global_index"] for cell in cells],
        "scope_indices": [cell["scope_index"] for cell in cells],
        "shard_id": "shard_000_of_001",
        "shard_index": 0,
    }
    plan = {
        "schema_version": "scalable3d-experiment-matrix-execution-plan-v1",
        "source": {"git_commit": _COMMIT, "repository_dirty": False},
        "parent": {"formal": True, "full_cell_count": len(cells)},
        "scope": {
            "variants": ["R0"],
            "cell_count": len(cells),
            "cells_sha256": _canonical_digest(cells),
            "cells": cells,
        },
        "sharding": {
            "strategy": "scope_index_modulo_v1",
            "shard_count": 1,
            "shards": [descriptor],
        },
    }
    plan_sha = _canonical_digest(plan)
    plan["execution_plan_sha256"] = plan_sha
    plan_path = execution_root / "experiment_matrix_execution_plan.json"
    plan_file_sha = _write_json(plan_path, plan)
    (execution_root / "EXECUTION_PLAN_SHA256").write_text(
        f"{plan_file_sha}  experiment_matrix_execution_plan.json\n",
        encoding="utf-8",
    )

    shard_dir = execution_root / "shards" / "shard_000_of_001"
    progress = []
    for index, (cell, reason) in enumerate(zip(cells, reasons, strict=True)):
        cell_dir = shard_dir / "cells" / cell["cell_id"]
        episode_dir = cell_dir / "episode"
        episode_id = f"fixture-{cell['cell_id']}"
        _write_json(
            episode_dir / "manifest.json",
            {
                "episode_id": episode_id,
                "git_commit": _COMMIT,
                "repository_dirty": False,
                "seed": cell["seed"],
            },
        )
        identity_evaluation_path = (
            episode_dir / "offline_identity" / "identity_evaluation.json"
        )
        identity_evaluation_sha = _write_json(
            identity_evaluation_path,
            {"episode_id": episode_id, "fixture": True},
        )
        identity_manifest_path = (
            episode_dir / "offline_identity" / "manifest.json"
        )
        identity_manifest_sha = _write_json(
            identity_manifest_path,
            {
                "schema_version": (
                    "scalable3d-offline-identity-evaluation-manifest-v2"
                ),
                "episode_id": episode_id,
                "source_hashes": {
                    "identity_evaluation": (
                        f"sha256:{identity_evaluation_sha}"
                    )
                },
            },
        )
        d6_record_path = (
            episode_dir / "d6_truth_isolated" / "episode_record.json"
        )
        d6_record_sha = _write_json(
            d6_record_path,
            {
                "schema_version": "d6.scalable3d_truth_isolated_episode.v1",
                "context": {
                    "episode_id": episode_id,
                    "seed": cell["seed"],
                    "target_count": cell["scale"],
                    "resource_count": cell["scale"],
                },
                "d2_identity": {
                    "episode_id": episode_id,
                    "id_switch_count": 0 if reason is None else None,
                    "id_switch_count_availability": (
                        "available" if reason is None else "unavailable"
                    ),
                    "id_switch_count_unavailable_reason": (
                        None if reason is None else reason
                    ),
                },
            },
        )
        _write_json(
            episode_dir / "d6_truth_isolated" / "manifest.json",
            {
                "schema_version": (
                    "scalable3d-d6-truth-isolated-manifest-v1"
                ),
                "episode_id": episode_id,
                "source_hashes": {
                    "offline_identity_manifest": (
                        f"sha256:{identity_manifest_sha}"
                    ),
                    "offline_identity_evaluation": (
                        f"sha256:{identity_evaluation_sha}"
                    ),
                },
                "output_hashes": {
                    "episode_record": f"sha256:{d6_record_sha}"
                },
            },
        )
        cell_result_path = cell_dir / "cell_result.json"
        cell_result_sha = _write_json(
            cell_result_path,
            {
                "schema_version": (
                    "scalable3d-experiment-matrix-cell-result-v1"
                ),
                "cell": cell,
                "episode_id": episode_id,
                "episode_relative_path": (
                    "shards/shard_000_of_001/cells/"
                    f"{cell['cell_id']}/episode"
                ),
                "execution_plan_sha256": plan_sha,
                "source_git_commit": _COMMIT,
                "status": "complete",
                "artifact_tree_sha256": "a" * 64,
            },
        )
        progress.append(
            {
                "schema_version": (
                    "scalable3d-experiment-matrix-shard-progress-v1"
                ),
                "cell_id": cell["cell_id"],
                "cell_result_relative_path": (
                    "shards/shard_000_of_001/cells/"
                    f"{cell['cell_id']}/cell_result.json"
                ),
                "cell_result_sha256": cell_result_sha,
                "episode_artifact_tree_sha256": "a" * 64,
                "execution_plan_sha256": plan_sha,
                "global_index": cell["global_index"],
                "scope_index": cell["scope_index"],
                "sequence": index,
                "shard_index": 0,
                "shard_sequence": index,
            }
        )

    shard_dir.mkdir(parents=True, exist_ok=True)
    progress_path = shard_dir / "progress.jsonl"
    progress_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in progress
        ),
        encoding="utf-8",
    )
    _write_json(
        shard_dir / "shard_plan.json",
        {
            "schema_version": "scalable3d-experiment-matrix-shard-plan-v1",
            "execution_plan_sha256": plan_sha,
            "source_git_commit": _COMMIT,
            "descriptor": descriptor,
            "cells": cells,
            "cells_sha256": _canonical_digest(cells),
        },
    )
    _write_json(
        shard_dir / "checkpoint.json",
        {
            "schema_version": (
                "scalable3d-experiment-matrix-shard-checkpoint-v1"
            ),
            "execution_plan_sha256": plan_sha,
            "source_git_commit": _COMMIT,
            "shard_id": "shard_000_of_001",
            "shard_index": 0,
            "expected_cell_count": len(cells),
            "completed_cell_count": len(cells),
            "next_sequence": len(cells),
            "status": "complete",
            "progress_sha256": _file_digest(progress_path),
        },
    )
    return execution_root, plan_sha


def test_execution_root_discovers_current_cells_layout_and_exact_36(
    tmp_path: Path,
) -> None:
    execution_root, plan_sha = _build_formal_scope(tmp_path)

    scope = discover_formal_identity_audit_scope(
        execution_root,
        expected_source_git_commit=_COMMIT,
        expected_execution_plan_sha256=plan_sha,
        expected_completed_episode_count=37,
        expected_strict_unavailable_episode_count=36,
    )

    assert scope.completed_episode_count == 37
    assert len(scope.strict_unavailable_references) == 36
    assert Counter(
        ref.strict_identity_metrics_reason
        for ref in scope.strict_unavailable_references
    ) == {
        "multiple_truth_targets_for_global_track": 27,
        "source_observation_outside_lineage_window": 9,
    }
    assert sum(
        ref.scale == 100
        and ref.strict_identity_metrics_reason
        == "multiple_truth_targets_for_global_track"
        for ref in scope.strict_unavailable_references
    ) == 4
    assert sum(
        ref.scale == 200
        and ref.strict_identity_metrics_reason
        == "multiple_truth_targets_for_global_track"
        for ref in scope.strict_unavailable_references
    ) == 23
    assert all(
        ref.episode_dir.parent.name == ref.cell_id
        and ref.episode_dir.name == "episode"
        and ref.episode_dir.parent.parent.name == "cells"
        for ref in scope.strict_unavailable_references
    )


def test_execution_root_fails_closed_on_identity_source_hash_mismatch(
    tmp_path: Path,
) -> None:
    execution_root, plan_sha = _build_formal_scope(tmp_path)
    target = next(
        execution_root.glob(
            "shards/*/cells/*/episode/offline_identity/identity_evaluation.json"
        )
    )
    target.write_text('{"tampered":true}\n', encoding="utf-8")

    with pytest.raises(
        FormalIdentityBlockerAuditError,
        match="source_artifact_sha256_mismatch",
    ):
        discover_formal_identity_audit_scope(
            execution_root,
            expected_source_git_commit=_COMMIT,
            expected_execution_plan_sha256=plan_sha,
            expected_completed_episode_count=37,
            expected_strict_unavailable_episode_count=36,
        )


def test_lineage_events_do_not_pollute_multi_truth_report(
    tmp_path: Path,
) -> None:
    scope = FormalIdentityAuditScope(
        execution_root=tmp_path,
        archive_root=None,
        source_git_commit=_COMMIT,
        execution_plan_sha256="a" * 64,
        execution_plan_file_sha256="b" * 64,
        planned_episode_count=2,
        completed_episode_count=2,
        completed_shard_count=1,
        references=(),
        strict_unavailable_references=(),
        shard_audits=(),
        archive_adapter_mode="directory_only",
    )
    case_rows = [
        {
            "cell_id": f"cell-{index}",
            "episode_id": f"episode-{index}",
            "scenario": "nominal",
            "scale": 200,
            "strict_identity_metrics_reason": reason,
            "blocker_mapping_event_count": 1,
            "case_json_relative_path": f"cases/cell-{index}.json",
            "case_json_sha256": "sha256:" + "c" * 64,
            "case_csv_relative_path": f"cases/cell-{index}.csv",
            "case_csv_sha256": "sha256:" + "d" * 64,
            "producer_replay_verified": True,
            "source_hashes_verified": True,
            "episode_identity_verified": True,
            "online_truth_isolation_verified": True,
        }
        for index, reason in enumerate(
            (
                "multiple_truth_targets_for_global_track",
                "source_observation_outside_lineage_window",
            )
        )
    ]
    event_rows = [
        {
            "reason": "multiple_truth_targets_for_global_track",
            "causal_classification": (
                "newest_observation_introduced_new_truth"
            ),
            "commitment_reason": "fresh_original_observation_accepted",
            "modality_transition": "radar->camera",
            "newest_sensor_ids": "CAM-RECON-008",
            "scenario": "nominal",
            "scale": 200,
        },
        {
            "reason": "source_observation_outside_lineage_window",
            "causal_classification": "historical_lineage_only_stale",
            "commitment_reason": "lineage_window_audit_only",
            "modality_transition": "radar->radar",
            "newest_sensor_ids": "CAM-INT-0055",
            "scenario": "nominal",
            "scale": 200,
            "oldest_source_age_seconds": 1.1,
            "newest_source_age_seconds": 0.4,
            "commitment_source_age_seconds": 0.4,
        },
    ]

    aggregate = pack_module._aggregate_pack(
        scope,
        case_rows=case_rows,
        event_rows=event_rows,
        case_payloads=(),
        source_artifacts={},
    )
    grouped = aggregate["reason_grouped_event_counts"]
    multi_truth = grouped[
        "multiple_truth_targets_for_global_track"
    ]

    assert aggregate["sensor_modality_transition_event_counts"] == {
        "radar->camera": 1,
        "radar->radar": 1,
    }
    assert aggregate["newest_sensor_event_counts"] == {
        "CAM-INT-0055": 1,
        "CAM-RECON-008": 1,
    }
    assert multi_truth["sensor_modality_transition_event_counts"] == {
        "radar->camera": 1,
    }
    assert multi_truth["newest_sensor_event_counts"] == {
        "CAM-RECON-008": 1,
    }
    assert multi_truth["commitment_reason_event_counts"] == {
        "fresh_original_observation_accepted": 1,
    }

    report_path = tmp_path / "report.md"
    pack_module._write_chinese_report(report_path, aggregate)
    report = report_path.read_text(encoding="utf-8")
    multi_truth_section = report.split(
        "## 一航迹多真值",
        maxsplit=1,
    )[1].split("## 谱系超窗", maxsplit=1)[0]
    assert "radar->camera` 1" in multi_truth_section
    assert "CAM-RECON-008` 1" in multi_truth_section
    assert "fresh_original_observation_accepted=1" in multi_truth_section
    assert "radar->radar" not in multi_truth_section
    assert "CAM-INT-0055" not in multi_truth_section
    assert "lineage_window_audit_only" not in multi_truth_section
