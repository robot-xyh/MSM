from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from commitment_test_support import committed_target_track
import d3_assignment_planner.isolated_intervention_batch as batch_module
from d3_assignment_planner import (
    BATCH_CHECKSUMS_FILENAME,
    BATCH_PER_SEED_FILENAME,
    BATCH_REPORT_FILENAME,
    BATCH_RESULT_FILENAME,
    EDGE_FEATURE_NAMES,
    ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1,
    ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
    AssignmentPlanner,
    CostMatrixResult,
    CostWeights,
    PairedInterventionContractError,
    PlannerConfig,
    ResourceState,
    SharedEdgeActorCriticPolicy,
    TargetDemand,
    development_shadow_admission,
    load_isolated_intervention_batch_manifest,
    run_isolated_intervention_batch,
    save_model_bundle,
    write_anonymous_planning_frame_evidence,
)


class _FixedMToNCostModel:
    weights = CostWeights()

    def build_matrix(
        self,
        tracks,
        resources,
        timestamp,
        *,
        preserved_candidate_edges=None,
    ) -> CostMatrixResult:
        del timestamp, preserved_candidate_edges
        matrix = np.asarray(
            (
                (0.1, 0.2, 0.4),
                (0.4, 0.3, 0.1),
            ),
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(
                tuple(
                    {
                        "rule_total": float(matrix[row, column]),
                        "total": float(matrix[row, column]),
                    }
                    for column in range(matrix.shape[1])
                )
                for row in range(matrix.shape[0])
            ),
            target_ids=tuple(item.track_id for item in tracks),
            resource_ids=tuple(item.resource_id for item in resources),
            unassigned_costs=np.asarray((10.0, 10.0), dtype=float),
            target_threat_scores=(0.9, 0.5),
            reject_reasons=(
                (None, None, None),
                (None, None, None),
            ),
            candidate_mask=np.ones((2, 3), dtype=bool),
        )


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _rule_frame():
    tracks = (
        committed_target_track(
            "global-track-a",
            0.9,
            0.1,
            0.0,
            demand=TargetDemand(
                required_resource_count=2,
                primary_resource_count=2,
            ),
        ),
        committed_target_track("global-track-b", 0.5, 0.1, 0.0),
    )
    resources = tuple(ResourceState(f"resource-{index}") for index in range(3))
    config = PlannerConfig(
        enable_hysteresis=False,
        solver_name="hungarian_demand_slots",
    )
    planner = AssignmentPlanner(
        cost_model=_FixedMToNCostModel(),
        config=config,
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        expected_previous_version=previous.version,
        forced_replan=True,
        publish=False,
    )
    frame = planner.latest_planning_evidence
    assert frame.available
    assert frame.learning_state == "rule_only"
    return frame, config


def _write_bundle(
    path: Path,
    *,
    binding_changing: bool,
    reserved_seeds=ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
):
    torch = pytest.importorskip("torch")
    policy = SharedEdgeActorCriticPolicy(
        hidden_size=1,
        residual_bound=10.0,
    )
    with torch.no_grad():
        for parameter in policy.parameters():
            parameter.zero_()
        if binding_changing:
            previous_binding_index = EDGE_FEATURE_NAMES.index(
                "previous_binding"
            )
            first_layer = policy.edge_encoder[0]
            second_layer = policy.edge_encoder[2]
            first_layer.weight[0, previous_binding_index] = 2.0
            first_layer.bias[0] = -1.0
            second_layer.weight[0, 0] = 2.0
            policy.residual_mean_head.weight[0, 0] = 2.0
        policy.selection_head.bias[0] = 10.0

    manifest = save_model_bundle(
        path,
        policy,
        split_hash=_digest("split"),
        dataset_frames_sha256=_digest("dataset"),
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES), dtype=float),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES), dtype=float),
        training_results={"stage": "batch_replay_unit_fixture"},
        alpha=1.0,
        min_confidence=0.0,
        deadline_s=1.0,
        provenance={
            "repository_git_commit": "b" * 40,
            "repository_git_commit_role": "exact_training_source_commit",
            "training_worktree_state": "clean",
            "training_source_sha256": _digest("training-source"),
            "dataset_manifest_sha256": _digest("dataset-manifest"),
            "training_entrypoint": "batch_replay_unit_fixture",
            "training_date": "2026-07-26",
        },
        admission=development_shadow_admission(
            reserved_seeds
        ),
        promotion_unavailable_reason="reserved_seed_evaluation_pending",
    )
    return manifest, _file_digest(path / "manifest.json")


def _build_manifest(
    root: Path,
    *,
    binding_changing: bool = True,
    bundle_reserved_seeds=ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
) -> tuple[Path, dict, Path]:
    frame, config = _rule_frame()
    bundle_dir = root / "bundle"
    bundle, bundle_manifest_sha256 = _write_bundle(
        bundle_dir,
        binding_changing=binding_changing,
        reserved_seeds=bundle_reserved_seeds,
    )
    seed_entries = []
    for seed in ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
        frame_path = root / "frames" / f"seed_{seed}" / "frame_0000.json"
        hashes = write_anonymous_planning_frame_evidence(frame_path, frame)
        seed_entries.append(
            {
                "seed": seed,
                "frames": [
                    {
                        "sequence_index": 0,
                        "timestamp_s": 1.0,
                        "path": str(frame_path.relative_to(root)),
                        "file_sha256": hashes["file_sha256"],
                        "content_sha256": hashes["content_sha256"],
                    }
                ],
            }
        )
    payload = {
        "schema_version": (
            ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1
        ),
        "batch_id": "d3-clean-test-1000-1019",
        "evaluated_at": "2026-07-26T16:00:00Z",
        "split": "test",
        "source": {
            "repository_git_commit": "a" * 40,
            "worktree_state": "clean",
        },
        "bundle": {
            "directory": str(bundle_dir.relative_to(root)),
            "manifest_sha256": bundle_manifest_sha256,
            "policy_version": bundle.policy_version,
        },
        "planner_config": asdict(config),
        "cost_weights": asdict(CostWeights()),
        "seeds": seed_entries,
    }
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, payload)
    return manifest_path, payload, bundle_dir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="ascii",
    )


def _assert_checksums(output: Path) -> None:
    lines = (output / BATCH_CHECKSUMS_FILENAME).read_text(
        encoding="ascii"
    ).splitlines()
    assert len(lines) == 3
    for line in lines:
        digest, name = line.split("  ", maxsplit=1)
        assert _file_digest(output / name) == digest


def test_batch_is_deterministic_and_cli_outputs_are_non_authoritative(
    tmp_path: Path,
    capsys,
) -> None:
    manifest_path, _, _ = _build_manifest(tmp_path / "input")
    output_a = tmp_path / "output-a"
    output_b = tmp_path / "output-b"

    result_a = run_isolated_intervention_batch(manifest_path, output_a)
    assert batch_module.main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_b),
        ]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)

    assert result_a["seed_contract"] == {
        "expected_seeds": list(ISOLATED_INTERVENTION_BATCH_SEEDS_V1),
        "seed_count": 20,
        "eligible_seed_count": 20,
        "unavailable_seed_count": 0,
    }
    assert cli_payload["publish"] is False
    assert cli_payload["production_authority"] is False
    assert all(item["status"] == "eligible_selected" for item in result_a["seeds"])
    assert all(
        item["execution_boundary"]["runtime_ack"] is False
        and item["execution_boundary"]["production_assignment_authority"]
        is False
        and item["execution_boundary"]["production_control_authority"]
        is False
        and item["safety"]["global_track_id_rewrite_count"] == 0
        for item in result_a["seeds"]
    )
    for name in (
        BATCH_RESULT_FILENAME,
        BATCH_PER_SEED_FILENAME,
        BATCH_REPORT_FILENAME,
        BATCH_CHECKSUMS_FILENAME,
    ):
        assert (output_a / name).read_bytes() == (output_b / name).read_bytes()
    _assert_checksums(output_a)
    json.loads((output_a / BATCH_RESULT_FILENAME).read_text(encoding="ascii"))


def test_no_eligible_frames_are_reported_unavailable_without_substitution(
    tmp_path: Path,
) -> None:
    manifest_path, _, _ = _build_manifest(
        tmp_path / "input",
        binding_changing=False,
    )
    result = run_isolated_intervention_batch(
        manifest_path,
        tmp_path / "output",
    )

    assert result["seed_contract"]["eligible_seed_count"] == 0
    assert result["seed_contract"]["unavailable_seed_count"] == 20
    assert all(
        item["status"] == "unavailable"
        and item["unavailable_reason"] == "no_eligible_frame"
        and item["first_eligible"] is None
        for item in result["seeds"]
    )
    assert all(
        item["bundle"]["all_frames_loaded"] is True
        and item["bundle"]["fallback_frame_count"] == 0
        for item in result["seeds"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda payload: payload["source"].update(
                {"worktree_state": "dirty"}
            ),
            "batch_source_worktree_not_clean",
        ),
        (
            lambda payload: payload["seeds"].pop(),
            "batch_seed_inventory_incomplete",
        ),
        (
            lambda payload: payload["seeds"].__setitem__(
                slice(0, 2),
                list(reversed(payload["seeds"][:2])),
            ),
            "batch_seed_inventory_invalid",
        ),
        (
            lambda payload: payload["seeds"].__setitem__(
                1,
                json.loads(json.dumps(payload["seeds"][0])),
            ),
            "batch_seed_inventory_invalid",
        ),
        (
            lambda payload: payload.update({"eligibility": True}),
            "batch_manifest_fields_mismatch",
        ),
        (
            lambda payload: payload["source"].update({"truth": "forbidden"}),
            "batch_forbidden_input_key",
        ),
        (
            lambda payload: payload["bundle"].update(
                {"manifest_sha256": _digest("wrong-bundle")}
            ),
            "batch_bundle_manifest_sha256_mismatch",
        ),
    ),
)
def test_manifest_and_lineage_fail_closed(
    tmp_path: Path,
    mutation,
    expected_code: str,
) -> None:
    manifest_path, payload, _ = _build_manifest(tmp_path / "input")
    mutation(payload)
    _write_json(manifest_path, payload)

    with pytest.raises(PairedInterventionContractError) as captured:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "output",
        )

    assert captured.value.code == expected_code
    assert not (tmp_path / "output").exists()


def test_out_of_order_frame_reference_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload, _ = _build_manifest(tmp_path / "input")
    first = dict(payload["seeds"][0]["frames"][0])
    first["sequence_index"] = 1
    second = dict(first)
    second["path"] = payload["seeds"][1]["frames"][0]["path"]
    second["file_sha256"] = payload["seeds"][1]["frames"][0]["file_sha256"]
    second["content_sha256"] = payload["seeds"][1]["frames"][0][
        "content_sha256"
    ]
    payload["seeds"][0]["frames"] = [first, second]
    _write_json(manifest_path, payload)

    with pytest.raises(PairedInterventionContractError) as captured:
        load_isolated_intervention_batch_manifest(manifest_path)

    assert captured.value.code == "batch_frame_order_invalid"


def test_bundle_reserved_seed_contract_is_required(tmp_path: Path) -> None:
    manifest_path, _, _ = _build_manifest(
        tmp_path / "input",
        bundle_reserved_seeds=tuple(range(2000, 2020)),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "output",
        )

    assert captured.value.code == "batch_bundle_reserved_seed_contract_invalid"
    assert not (tmp_path / "output").exists()


def test_frame_hash_schema_and_nonfinite_values_fail_closed(
    tmp_path: Path,
) -> None:
    manifest_path, payload, _ = _build_manifest(tmp_path / "input")
    payload["seeds"][0]["frames"][0]["file_sha256"] = _digest("wrong-frame")
    _write_json(manifest_path, payload)
    with pytest.raises(PairedInterventionContractError) as hash_error:
        run_isolated_intervention_batch(manifest_path, tmp_path / "hash-output")
    assert hash_error.value.code == "batch_frame_file_sha256_mismatch"

    manifest_path, payload, _ = _build_manifest(tmp_path / "schema-input")
    frame_reference = payload["seeds"][0]["frames"][0]
    frame_path = manifest_path.parent / frame_reference["path"]
    frame_payload = json.loads(frame_path.read_text(encoding="ascii"))
    frame_payload["schema_version"] = "unsupported"
    _write_json(frame_path, frame_payload)
    frame_reference["file_sha256"] = _file_digest(frame_path)
    _write_json(manifest_path, payload)
    with pytest.raises(PairedInterventionContractError) as schema_error:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "schema-output",
        )
    assert schema_error.value.code == "batch_frame_file_schema_unsupported"

    manifest_path, payload, _ = _build_manifest(tmp_path / "finite-input")
    payload["planner_config"]["delta"] = float("nan")
    manifest_path.write_text(
        json.dumps(payload, allow_nan=True),
        encoding="ascii",
    )
    with pytest.raises(PairedInterventionContractError) as finite_error:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "finite-output",
        )
    assert finite_error.value.code == "batch_nonfinite_value"


def test_nonempty_output_and_second_publication_fail_closed(
    tmp_path: Path,
) -> None:
    manifest_path, _, _ = _build_manifest(tmp_path / "input")
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("keep", encoding="ascii")

    with pytest.raises(PairedInterventionContractError) as captured:
        run_isolated_intervention_batch(manifest_path, nonempty)
    assert captured.value.code == "batch_output_not_empty"
    assert (nonempty / "keep.txt").read_text(encoding="ascii") == "keep"

    output = tmp_path / "output"
    run_isolated_intervention_batch(manifest_path, output)
    original_hashes = {
        path.name: _file_digest(path) for path in output.iterdir()
    }
    with pytest.raises(PairedInterventionContractError) as second:
        run_isolated_intervention_batch(manifest_path, output)
    assert second.value.code == "batch_output_not_empty"
    assert {
        path.name: _file_digest(path) for path in output.iterdir()
    } == original_hashes


def test_input_change_during_replay_prevents_publication(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path, payload, _ = _build_manifest(tmp_path / "input")
    changed_path = manifest_path.parent / payload["seeds"][0]["frames"][0]["path"]
    original = batch_module.replay_isolated_learning_intervention_frame
    changed = False

    def mutate_after_replay(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed_path.write_bytes(changed_path.read_bytes() + b"\n")
            changed = True
        return result

    monkeypatch.setattr(
        batch_module,
        "replay_isolated_learning_intervention_frame",
        mutate_after_replay,
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "output",
        )

    assert captured.value.code == "batch_input_changed_during_replay"
    assert not (tmp_path / "output").exists()
