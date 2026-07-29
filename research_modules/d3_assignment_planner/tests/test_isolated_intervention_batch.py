from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from commitment_test_support import committed_target_track
import d3_assignment_planner.isolated_intervention_batch as batch_module
from d3_assignment_planner import (
    A1_BATCH_CANDIDATES_FILENAME,
    A1_BATCH_RESULT_FILENAME,
    A1_BATCH_SELECTIONS_FILENAME,
    A1_ISOLATED_INTERVENTION_BATCH_LOADER_SCHEMA_V1,
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
    build_a1_intervention_preregistration,
    canonical_runtime_payload_sha256,
    development_shadow_admission,
    load_a1_intervention_preregistration_file,
    load_a1_isolated_intervention_batch,
    load_isolated_intervention_batch_manifest,
    run_a1_isolated_intervention_batch,
    run_isolated_intervention_batch,
    save_model_bundle,
    validate_a1_isolated_intervention_batch,
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


def _rule_frame(timestamp_s: float = 1.0):
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
        timestamp=timestamp_s,
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
    frame_timestamps: tuple[float, ...] = (1.0,),
) -> tuple[Path, dict, Path]:
    if not frame_timestamps:
        raise ValueError("frame_timestamps must not be empty")
    frames = tuple(_rule_frame(value) for value in frame_timestamps)
    config = frames[0][1]
    bundle_dir = root / "bundle"
    bundle, bundle_manifest_sha256 = _write_bundle(
        bundle_dir,
        binding_changing=binding_changing,
        reserved_seeds=bundle_reserved_seeds,
    )
    seed_entries = []
    for seed in ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
        frame_entries = []
        for sequence_index, (frame, _) in enumerate(frames):
            frame_path = (
                root
                / "frames"
                / f"seed_{seed}"
                / f"frame_{sequence_index:04d}.json"
            )
            hashes = write_anonymous_planning_frame_evidence(
                frame_path,
                frame,
            )
            frame_entries.append(
                {
                    "sequence_index": sequence_index,
                    "timestamp_s": frame_timestamps[sequence_index],
                    "path": str(frame_path.relative_to(root)),
                    "file_sha256": hashes["file_sha256"],
                    "content_sha256": hashes["content_sha256"],
                }
            )
        seed_entries.append(
            {
                "seed": seed,
                "frames": frame_entries,
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


def _write_a1_preregistration(
    root: Path,
    manifest_payload: dict,
    bundle_dir: Path,
    *,
    evaluation_seeds=ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
    sequence_index_max: int | None = None,
    timestamp_s_max: float | None = None,
) -> Path:
    state_dict_sha256 = json.loads(
        (bundle_dir / "manifest.json").read_text(encoding="utf-8")
    )["state_dict"]["sha256"]
    frame_references = [
        frame
        for seed in manifest_payload["seeds"]
        for frame in seed["frames"]
    ]
    registration = build_a1_intervention_preregistration(
        experiment_id="a1-isolated-batch-unit",
        experiment_version="v1",
        policy_artifact_sha256=state_dict_sha256,
        evaluation_seeds=evaluation_seeds,
        sequence_index_min=0,
        sequence_index_max=(
            max(item["sequence_index"] for item in frame_references)
            if sequence_index_max is None
            else sequence_index_max
        ),
        timestamp_s_min=0.0,
        timestamp_s_max=(
            max(item["timestamp_s"] for item in frame_references)
            if timestamp_s_max is None
            else timestamp_s_max
        ),
        max_abs_cost_correction=20.0,
        max_rule_cost_difference=100.0,
        max_relative_rule_cost_difference=100.0,
        max_binding_change_count=3,
        high_threat_threshold=0.7,
    )
    path = root / "a1_preregistration.json"
    _write_json(path, registration.to_dict())
    return path


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


def _assert_a1_checksums(output: Path) -> None:
    lines = (output / BATCH_CHECKSUMS_FILENAME).read_text(
        encoding="ascii"
    ).splitlines()
    assert len(lines) == 6
    names = set()
    for line in lines:
        digest, name = line.split("  ", maxsplit=1)
        names.add(name)
        assert _file_digest(output / name) == digest
    assert {
        BATCH_RESULT_FILENAME,
        BATCH_PER_SEED_FILENAME,
        BATCH_REPORT_FILENAME,
        A1_BATCH_RESULT_FILENAME,
        A1_BATCH_CANDIDATES_FILENAME,
        A1_BATCH_SELECTIONS_FILENAME,
    } == names


_A1_CHECKSUMMED_FILENAMES = (
    BATCH_RESULT_FILENAME,
    BATCH_PER_SEED_FILENAME,
    BATCH_REPORT_FILENAME,
    A1_BATCH_RESULT_FILENAME,
    A1_BATCH_CANDIDATES_FILENAME,
    A1_BATCH_SELECTIONS_FILENAME,
)


@pytest.fixture(scope="module")
def strict_loader_artifact(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("a1-strict-loader")
    manifest_path, payload, bundle_dir = _build_manifest(
        root / "input",
        frame_timestamps=(1.0, 2.0),
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
    )
    output = root / "output"
    run_a1_isolated_intervention_batch(
        manifest_path,
        preregistration_path,
        output,
    )
    return output


def _copy_strict_loader_artifact(
    source: Path,
    target: Path,
) -> Path:
    output = target / "output"
    shutil.copytree(source, output)
    return output


def _refresh_content_sha256(payload: dict) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = canonical_runtime_payload_sha256(payload)


def _rewrite_a1_checksums(output: Path) -> None:
    text = "".join(
        f"{_file_digest(output / name)}  {name}\n"
        for name in _A1_CHECKSUMMED_FILENAMES
    )
    (output / BATCH_CHECKSUMS_FILENAME).write_text(
        text,
        encoding="ascii",
    )


def _rewrite_a1_result(
    output: Path,
    mutation,
) -> None:
    path = output / A1_BATCH_RESULT_FILENAME
    payload = json.loads(path.read_text(encoding="ascii"))
    mutation(payload)
    _refresh_content_sha256(payload)
    _write_json(path, payload)
    _rewrite_a1_checksums(output)


def _rewrite_candidate_inventory(
    output: Path,
    mutation,
) -> None:
    path = output / A1_BATCH_CANDIDATES_FILENAME
    payload = json.loads(path.read_text(encoding="ascii"))
    mutation(payload["records"][0])
    _refresh_content_sha256(payload["records"][0])
    _refresh_content_sha256(payload)
    _write_json(path, payload)

    result_path = output / A1_BATCH_RESULT_FILENAME
    result = json.loads(result_path.read_text(encoding="ascii"))
    result["candidate_contract"]["inventory_content_sha256"] = payload[
        "content_sha256"
    ]
    _refresh_content_sha256(result)
    _write_json(result_path, result)
    _rewrite_a1_checksums(output)


def _rewrite_selection_inventory(
    output: Path,
    mutation,
) -> None:
    path = output / A1_BATCH_SELECTIONS_FILENAME
    payload = json.loads(path.read_text(encoding="ascii"))
    mutation(payload["records"][0])
    _refresh_content_sha256(payload["records"][0])
    _refresh_content_sha256(payload)
    _write_json(path, payload)

    result_path = output / A1_BATCH_RESULT_FILENAME
    result = json.loads(result_path.read_text(encoding="ascii"))
    result["selection_contract"]["inventory_content_sha256"] = payload[
        "content_sha256"
    ]
    _refresh_content_sha256(result)
    _write_json(result_path, result)
    _rewrite_a1_checksums(output)


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


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "target_truth_id",
        "actor_truth_id",
        "resource_actor_name",
        "target_object_id",
    ),
)
def test_nested_frame_identity_metadata_fails_closed_before_hash_acceptance(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    manifest_path, payload, _ = _build_manifest(tmp_path / "input")
    frame_reference = payload["seeds"][0]["frames"][0]
    frame_path = manifest_path.parent / frame_reference["path"]
    frame_payload = json.loads(frame_path.read_text(encoding="ascii"))
    frame_payload["planning_frame"]["effective_matrix_result"]["metadata"][
        forbidden_key
    ] = "must-not-be-read"
    _write_json(frame_path, frame_payload)
    frame_reference["file_sha256"] = _file_digest(frame_path)
    _write_json(manifest_path, payload)

    with pytest.raises(PairedInterventionContractError) as captured:
        run_isolated_intervention_batch(
            manifest_path,
            tmp_path / "output",
        )

    assert captured.value.code == "batch_forbidden_input_key"
    assert not (tmp_path / "output").exists()


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


def test_a1_batch_is_deterministic_and_selects_first_synthetic_frame(
    tmp_path: Path,
    capsys,
) -> None:
    manifest_path, payload, bundle_dir = _build_manifest(
        tmp_path / "input",
        frame_timestamps=(1.0, 2.0),
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
    )
    output_a = tmp_path / "a1-output-a"
    output_b = tmp_path / "a1-output-b"

    result_a = run_a1_isolated_intervention_batch(
        manifest_path,
        preregistration_path,
        output_a,
    )
    assert batch_module.main(
        [
            "--manifest",
            str(manifest_path),
            "--a1-preregistration",
            str(preregistration_path),
            "--output",
            str(output_b),
        ]
    ) == 0
    console = json.loads(capsys.readouterr().out)

    assert result_a["candidate_contract"]["candidate_count"] == 40
    assert result_a["selection_contract"] == {
        "seed_count": 20,
        "selected_seed_count": 20,
        "no_safe_discrete_intervention_seed_count": 0,
        "inventory_content_sha256": result_a["selection_contract"][
            "inventory_content_sha256"
        ],
    }
    assert console["selected_seed_count"] == 20
    assert console["candidate_file"] == A1_BATCH_CANDIDATES_FILENAME
    assert console["selection_file"] == A1_BATCH_SELECTIONS_FILENAME
    assert console["publish"] is False
    assert console["runtime_ack"] is False
    assert console["physical_window_available"] is False
    assert console["production_authority"] is False

    candidates = json.loads(
        (output_a / A1_BATCH_CANDIDATES_FILENAME).read_text(
            encoding="ascii"
        )
    )
    selections = json.loads(
        (output_a / A1_BATCH_SELECTIONS_FILENAME).read_text(
            encoding="ascii"
        )
    )
    assert candidates["record_count"] == 40
    assert selections["record_count"] == 20
    assert all(item["selected"] for item in selections["records"])
    assert all(
        item["selected_sequence_index"] == 0
        and item["selected_timestamp_s"] == 1.0
        for item in selections["records"]
    )
    assert all(
        item["execution_boundary"]["publish"] is False
        and item["execution_boundary"]["runtime_ack"] is False
        and item["execution_boundary"]["physical_window_available"] is False
        and item["execution_boundary"]["physical_outcome_available"] is False
        and item["execution_boundary"]["r0_pair_available"] is False
        and item["plan_published"] is False
        and item["runtime_ack"] is False
        and item["physical_window_available"] is False
        and item["r0_pair_available"] is False
        for item in candidates["records"] + selections["records"]
    )
    for path in output_a.iterdir():
        assert path.read_bytes() == (output_b / path.name).read_bytes()
    _assert_a1_checksums(output_a)


def test_a1_batch_zero_eligible_is_fail_closed(
    tmp_path: Path,
) -> None:
    manifest_path, payload, bundle_dir = _build_manifest(
        tmp_path / "input",
        binding_changing=False,
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
    )
    output = tmp_path / "output"

    result = run_a1_isolated_intervention_batch(
        manifest_path,
        preregistration_path,
        output,
    )
    candidates = json.loads(
        (output / A1_BATCH_CANDIDATES_FILENAME).read_text(
            encoding="ascii"
        )
    )["records"]
    selections = json.loads(
        (output / A1_BATCH_SELECTIONS_FILENAME).read_text(
            encoding="ascii"
        )
    )["records"]

    assert result["selection_contract"]["selected_seed_count"] == 0
    assert (
        result["selection_contract"][
            "no_safe_discrete_intervention_seed_count"
        ]
        == 20
    )
    assert all(
        item["selected"] is False
        and item["reason"] == "no_safe_discrete_intervention"
        and item["selected_candidate_content_sha256"] is None
        for item in selections
    )
    assert all(
        item["assignment_changed"] is False
        and item["selected_for_paired_evaluation"] is False
        and (
            "assignment_unchanged" in item["reason_codes"]
            or "safety_shell_rejected" in item["reason_codes"]
        )
        and item["execution_boundary"]["publish"] is False
        and item["execution_boundary"]["runtime_ack"] is False
        and item["plan_published"] is False
        and item["runtime_ack"] is False
        and item["physical_window_available"] is False
        and item["r0_pair_available"] is False
        for item in candidates
    )
    _assert_a1_checksums(output)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda payload: payload.update({"truth_id": "forbidden"}),
            "batch_forbidden_input_key",
        ),
        (
            lambda payload: payload.update(
                {
                    "max_abs_cost_correction": (
                        payload["max_abs_cost_correction"] + 1.0
                    )
                }
            ),
            "a1_batch_preregistration_invalid",
        ),
    ),
)
def test_a1_batch_preregistration_truth_and_tamper_fail_closed(
    tmp_path: Path,
    mutation,
    expected_code: str,
) -> None:
    manifest_path, payload, bundle_dir = _build_manifest(
        tmp_path / "input"
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
    )
    registration_payload = json.loads(
        preregistration_path.read_text(encoding="ascii")
    )
    mutation(registration_payload)
    _write_json(preregistration_path, registration_payload)

    with pytest.raises(PairedInterventionContractError) as captured:
        run_a1_isolated_intervention_batch(
            manifest_path,
            preregistration_path,
            tmp_path / "output",
        )

    assert captured.value.code == expected_code
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("registration_kwargs", "expected_code"),
    (
        (
            {
                "evaluation_seeds": tuple(range(1000, 1019)),
            },
            "a1_batch_preregistration_seed_scope_mismatch",
        ),
        (
            {
                "sequence_index_max": 0,
            },
            "a1_batch_preregistration_frame_scope_mismatch",
        ),
    ),
)
def test_a1_batch_preregistration_scope_is_rejected(
    tmp_path: Path,
    registration_kwargs,
    expected_code: str,
) -> None:
    manifest_path, payload, bundle_dir = _build_manifest(
        tmp_path / "input",
        frame_timestamps=(1.0, 2.0),
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
        **registration_kwargs,
    )
    assert load_a1_intervention_preregistration_file(
        preregistration_path
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        run_a1_isolated_intervention_batch(
            manifest_path,
            preregistration_path,
            tmp_path / "output",
        )

    assert captured.value.code == expected_code
    assert not (tmp_path / "output").exists()


def test_a1_public_strict_loader_revalidates_complete_non_authoritative_batch(
    strict_loader_artifact: Path,
) -> None:
    loaded = load_a1_isolated_intervention_batch(strict_loader_artifact)
    revalidated = validate_a1_isolated_intervention_batch(
        strict_loader_artifact
    )

    assert (
        loaded.schema_version
        == A1_ISOLATED_INTERVENTION_BATCH_LOADER_SCHEMA_V1
    )
    assert len(loaded.candidates) == 40
    assert len(loaded.selections) == 20
    assert loaded.file_sha256s == revalidated.file_sha256s
    assert loaded.batch_result["content_sha256"] == revalidated.batch_result[
        "content_sha256"
    ]
    assert loaded.plan_published is False
    assert loaded.runtime_ack is False
    assert loaded.physical_window_available is False
    assert loaded.r0_pair_available is False
    assert loaded.production_admission_granted is False
    assert loaded.production_assignment_authority is False
    assert loaded.production_control_authority is False


def test_a1_public_strict_loader_accepts_zero_selection_as_unavailable(
    tmp_path: Path,
) -> None:
    manifest_path, payload, bundle_dir = _build_manifest(
        tmp_path / "input",
        binding_changing=False,
    )
    preregistration_path = _write_a1_preregistration(
        manifest_path.parent,
        payload,
        bundle_dir,
    )
    output = tmp_path / "output"
    run_a1_isolated_intervention_batch(
        manifest_path,
        preregistration_path,
        output,
    )

    loaded = load_a1_isolated_intervention_batch(output)

    assert len(loaded.candidates) == 20
    assert len(loaded.selections) == 20
    assert all(item["selected"] is False for item in loaded.selections)
    assert loaded.batch_result["selection_contract"][
        "selected_seed_count"
    ] == 0
    assert loaded.production_admission_granted is False


def test_a1_public_strict_loader_rejects_byte_tamper(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    path = output / A1_BATCH_CANDIDATES_FILENAME
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_checksum_mismatch"


def test_a1_public_strict_loader_rejects_missing_file(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    (output / BATCH_REPORT_FILENAME).unlink()

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_directory_layout_invalid"


def test_a1_public_strict_loader_rejects_checksum_path_escape(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    checksum_path = output / BATCH_CHECKSUMS_FILENAME
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    digest, _ = lines[0].split("  ", maxsplit=1)
    lines[0] = f"{digest}  ../{BATCH_RESULT_FILENAME}"
    checksum_path.write_text("\n".join(lines) + "\n", encoding="ascii")

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_checksum_path_invalid"


def test_a1_public_strict_loader_rejects_output_path_escape(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(
        output,
        lambda payload: payload["output_files"].update(
            {"a1_candidates": f"../{A1_BATCH_CANDIDATES_FILENAME}"}
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_output_layout_invalid"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda payload: payload.update(
                {"schema_version": "d3.a1-unsupported.v999"}
            ),
            "a1_batch_loader_result_schema_unsupported",
        ),
        (
            lambda payload: payload.update(
                {"input_manifest_sha256": _digest("different-input-manifest")}
            ),
            "a1_batch_loader_legacy_lineage_mismatch",
        ),
    ),
)
def test_a1_public_strict_loader_rejects_top_schema_and_input_lineage(
    strict_loader_artifact: Path,
    tmp_path: Path,
    mutation,
    expected_code: str,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(output, mutation)

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == expected_code


def test_a1_public_strict_loader_rejects_model_summary_mismatch(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(
        output,
        lambda payload: payload["bundle"].update(
            {"manifest_sha256": _digest("different-model-manifest")}
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_bundle_summary_mismatch"


def test_a1_public_strict_loader_rejects_unknown_field(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(
        output,
        lambda payload: payload.update({"unknown_loader_claim": False}),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_result_fields_mismatch"


def test_a1_public_strict_loader_rejects_unknown_candidate_reason(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_candidate_inventory(
        output,
        lambda record: record.update(
            {"reason_codes": ["caller_declared_safe"]}
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert (
        captured.value.code
        == "a1_batch_loader_candidate_reason_code_unsupported"
    )


def test_a1_public_strict_loader_rejects_nonfinite_candidate(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    path = output / A1_BATCH_CANDIDATES_FILENAME
    payload = json.loads(path.read_text(encoding="ascii"))
    payload["records"][0]["max_abs_cost_correction"] = float("nan")
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=True,
        )
        + "\n",
        encoding="ascii",
    )
    _rewrite_a1_checksums(output)

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "batch_nonfinite_value"


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "terminal_truth_id",
        "camera_actor_name",
        "detected_object_id",
    ),
)
def test_a1_public_strict_loader_rejects_online_identity_fields(
    strict_loader_artifact: Path,
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_candidate_inventory(
        output,
        lambda record: record.update({forbidden_key: "offline-only"}),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "batch_forbidden_input_key"


def test_a1_public_strict_loader_rejects_authority_escalation(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(
        output,
        lambda payload: payload["execution_boundary"].update(
            {"publish": True}
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_authority_boundary_invalid"


def test_a1_public_strict_loader_rejects_candidate_count_mismatch(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_a1_result(
        output,
        lambda payload: payload["candidate_contract"].update(
            {
                "candidate_count": (
                    payload["candidate_contract"]["candidate_count"] + 1
                )
            }
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_candidate_contract_mismatch"


def test_a1_public_strict_loader_rejects_selection_count_mismatch(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_selection_inventory(
        output,
        lambda record: record.update(
            {
                "policy_evaluated_count": (
                    record["policy_evaluated_count"] + 1
                )
            }
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert (
        captured.value.code
        == "a1_batch_loader_selection_stage_count_mismatch"
    )


def test_a1_public_strict_loader_rejects_candidate_seed_outside_scope(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_candidate_inventory(
        output,
        lambda record: record.update({"seed": 999}),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert captured.value.code == "a1_batch_loader_candidate_seed_outside_scope"


def test_a1_public_strict_loader_rejects_candidate_frame_outside_scope(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_candidate_inventory(
        output,
        lambda record: record.update({"sequence_index": 99}),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert (
        captured.value.code
        == "a1_batch_loader_candidate_outside_preregistration"
    )


def test_a1_public_strict_loader_rejects_plan_version_discontinuity(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)

    def mutate(record: dict) -> None:
        record["treatment_plan_version"] = (
            record["previous_plan_version"] + 2
        )

    _rewrite_candidate_inventory(output, mutate)

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert (
        captured.value.code
        == "a1_batch_loader_candidate_plan_version_lineage_invalid"
    )


def test_a1_public_strict_loader_rejects_frame_digest_summary_mismatch(
    strict_loader_artifact: Path,
    tmp_path: Path,
) -> None:
    output = _copy_strict_loader_artifact(strict_loader_artifact, tmp_path)
    _rewrite_candidate_inventory(
        output,
        lambda record: record.update(
            {"input_file_sha256": _digest("different-frame-file")}
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        load_a1_isolated_intervention_batch(output)

    assert (
        captured.value.code
        == "a1_batch_loader_candidate_frame_summary_mismatch"
    )
