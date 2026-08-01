from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from d5_terminal_association.active_vision_a3_v3_protocol import (
    A3_V3_CAMERA_ROLES,
    A3_V3_HARD_CONFUSION_SCENARIOS,
    A3_V3_INTENTS,
    A3_V3_INTENT_ROLE_CELLS,
    ACTIVE_VISION_A3_V3_DEFAULT_STATUS,
    ACTIVE_VISION_A3_V3_FUTURE_LEDGER_SCHEMA_VERSION,
    ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION,
    authority_false_contract,
    load_frozen_a3_v3_protocol,
    validate_a3_v3_source_manifest,
    validate_future_heldout_access,
)
from d5_terminal_association.active_vision_a3_v3_training import (
    HierarchicalIntentLegalCandidateRanker,
    bounded_class_balanced_intent_weights,
    fit_validation_temperature,
    hierarchical_intent_ranking_loss,
    run_a3_v3_training_entry,
    train_a3_v3_hierarchical_model,
)
from d5_terminal_association.active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = (
    MODULE_ROOT / "configs" / "a3_v3_minority_intent_protocol_20260801.json"
)
AUTHORITY_KEYS = tuple(authority_false_contract())


def _protocol_payload() -> dict[str, object]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _write_protocol(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _counts(samples: int, episodes: int, seeds: int) -> dict[str, int]:
    return {
        "unique_samples": samples,
        "unique_episodes": episodes,
        "unique_seeds": seeds,
    }


def _minimum_counts(policy: dict[str, int]) -> dict[str, int]:
    return _counts(
        policy["minimum_unique_samples"],
        policy["minimum_unique_episodes"],
        policy["minimum_unique_seeds"],
    )


def _source_manifest(protocol) -> dict[str, object]:
    request = protocol.payload["source_request"]
    catalogs = {
        "train": list(range(30000, 30048)),
        "validation": list(range(31000, 31024)),
        "future_held_out": list(range(32000, 32032)),
    }
    coverage: dict[str, object] = {}
    for split, catalog in catalogs.items():
        policy = request["coverage_minimums_by_split"][split]
        hard = {}
        for scenario in request["hard_confusion_scenarios"]:
            episodes = scenario["minimum_unique_episodes_by_split"][split]
            seeds = scenario["minimum_unique_seeds_by_split"][split]
            hard[scenario["id"]] = _counts(max(episodes, seeds), episodes, seeds)
        total = _minimum_counts(policy["total"])
        total["unique_seeds"] = len(catalog)
        coverage[split] = {
            "total": total,
            "by_intent": {
                intent: _minimum_counts(policy["per_intent"])
                for intent in A3_V3_INTENTS
            },
            "by_camera_role": {
                role: _minimum_counts(policy["per_camera_role"])
                for role in A3_V3_CAMERA_ROLES
            },
            "by_intent_camera_role": {
                cell: _minimum_counts(policy["per_intent_camera_role"])
                for cell in A3_V3_INTENT_ROLE_CELLS
            },
            "hard_confusion_scenarios": hard,
        }
    return {
        "schema_version": ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "status": "source_generated_not_trained",
        "dataset_manifest_sha256_by_partition": {
            "development": "a" * 64,
            "future_held_out": "b" * 64,
        },
        "seed_catalogs": catalogs,
        "coverage_by_split": coverage,
        "provenance": {
            "source_domain": "scalable_3d_point_mass_runtime",
            "synthetic_fixture_episode_count": 0,
            "v2_episode_or_sample_reuse": False,
            "v2_test_episode_or_sample_read_count": 0,
            "formal_seed_1000_1019_episode_read_count": 0,
            "online_truth_id_use_count": 0,
        },
        "identity": {
            "global_track_id_ownership": "center_read_only",
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
        },
        "authority": authority_false_contract(),
    }


def test_frozen_protocol_loads_without_assigning_episode_seeds() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)

    assert protocol.status == ACTIVE_VISION_A3_V3_DEFAULT_STATUS
    assert protocol.payload["source_request"]["seed_assignment_owner"] == "main"
    assert protocol.payload["source_request"]["development_seed_values"] is None
    assert protocol.payload["source_request"]["future_evaluation_seed_values"] is None
    assert protocol.payload["selection_contract"]["configuration_count"] == 1
    assert protocol.payload["selection_contract"]["calibration_uses"] == (
        "validation_only"
    )
    assert not any(protocol.payload["authority"].values())


def test_default_entry_is_data_not_generated_and_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "must_not_exist"

    report = run_a3_v3_training_entry(PROTOCOL_PATH)

    assert report["status"] == ACTIVE_VISION_A3_V3_DEFAULT_STATUS
    assert report["training_started"] is False
    assert report["weights_written"] is False
    assert report["episode_payload_read_count"] == 0
    assert not output.exists()
    with pytest.raises(ValueError, match="source manifest is required"):
        run_a3_v3_training_entry(
            PROTOCOL_PATH,
            output_dir=output,
            execute_training=True,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["selection_contract"].__setitem__(
                "test_used_for_training_model_selection_calibration_or_thresholds",
                True,
            ),
            "selection contract mismatch",
        ),
        (
            lambda payload: payload["selection_contract"].__setitem__(
                "configuration_count", 2
            ),
            "selection contract mismatch",
        ),
        (
            lambda payload: payload["selection_contract"].__setitem__(
                "calibration_uses", "test"
            ),
            "selection contract mismatch",
        ),
        (
            lambda payload: payload["development"]["calibration"].__setitem__(
                "fit_split", "test"
            ),
            "calibration must use validation only",
        ),
    ],
)
def test_protocol_rejects_test_tuning_multiple_configs_and_test_calibration(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    payload = _protocol_payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        load_frozen_a3_v3_protocol(_write_protocol(tmp_path, payload))


@pytest.mark.parametrize("authority_key", AUTHORITY_KEYS)
def test_protocol_rejects_every_true_authority(
    tmp_path: Path,
    authority_key: str,
) -> None:
    payload = _protocol_payload()
    payload["authority"][authority_key] = True

    with pytest.raises(ValueError, match="every authority false"):
        load_frozen_a3_v3_protocol(_write_protocol(tmp_path, payload))


def test_source_contract_accepts_new_disjoint_main_assigned_seed_metadata() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)

    evidence = validate_a3_v3_source_manifest(protocol, manifest)

    assert evidence["status"] == "source_contract_ready_for_development_training"
    assert evidence["seed_counts"] == {
        "train": 48,
        "validation": 24,
        "future_held_out": 32,
    }
    assert evidence["seed_overlap_count"] == 0
    assert evidence["episode_payload_read_count"] == 0
    assert evidence["coverage"]["train"]["intent_role_cell_count"] == 8
    assert evidence["coverage"]["future_held_out"][
        "hard_confusion_scenario_count"
    ] == len(A3_V3_HARD_CONFUSION_SCENARIOS)
    assert not any(evidence["authority"].values())


def test_source_contract_rejects_missing_minority_intent() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)
    manifest["coverage_by_split"]["train"]["by_intent"]["observe_target"] = (
        _counts(0, 0, 0)
    )

    with pytest.raises(ValueError, match="train.observe_target unique samples below"):
        validate_a3_v3_source_manifest(protocol, manifest)


def test_source_contract_rejects_missing_camera_role() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)
    manifest["coverage_by_split"]["validation"]["by_camera_role"]["recon"] = (
        _counts(0, 0, 0)
    )

    with pytest.raises(ValueError, match="validation.recon unique samples below"):
        validate_a3_v3_source_manifest(protocol, manifest)


def test_source_contract_rejects_development_future_seed_overlap() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)
    manifest["seed_catalogs"]["future_held_out"][0] = manifest["seed_catalogs"][
        "train"
    ][0]
    manifest["seed_catalogs"]["future_held_out"].sort()

    with pytest.raises(ValueError, match="seed overlap: train/future_held_out"):
        validate_a3_v3_source_manifest(protocol, manifest)


@pytest.mark.parametrize(
    "catalog",
    [list(range(1000, 1032)), list(range(22100, 22132))],
)
def test_source_contract_rejects_formal_or_v2_seed_overlap(catalog: list[int]) -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)
    manifest["seed_catalogs"]["future_held_out"] = catalog

    with pytest.raises(ValueError, match="overlaps prohibited range"):
        validate_a3_v3_source_manifest(protocol, manifest)


def test_source_contract_rejects_true_authority_and_global_id_mutation() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    manifest = _source_manifest(protocol)
    manifest["authority"]["camera_command"] = True

    with pytest.raises(ValueError, match="every authority false"):
        validate_a3_v3_source_manifest(protocol, manifest)

    manifest = _source_manifest(protocol)
    manifest["identity"]["global_track_id_rewritten_count"] = 1
    with pytest.raises(ValueError, match="global_track_id ownership"):
        validate_a3_v3_source_manifest(protocol, manifest)


def test_future_heldout_gate_is_one_shot_and_never_selection_feedback() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    report = {
        "protocol_sha256": protocol.sha256,
        "source_manifest_sha256": "a" * 64,
        "validation_gate_passed": True,
        "model_frozen": True,
        "weights_sha256": "b" * 64,
        "calibration_sha256": "c" * 64,
        "test_or_future_held_out_used_during_development": False,
        "authority": authority_false_contract(),
    }
    ledger = {
        "schema_version": ACTIVE_VISION_A3_V3_FUTURE_LEDGER_SCHEMA_VERSION,
        "protocol_sha256": protocol.sha256,
        "weights_sha256": "b" * 64,
        "access_count": 0,
        "status": "unopened",
        "selection_feedback_allowed": False,
    }

    validate_future_heldout_access(
        protocol,
        development_report=report,
        ledger=ledger,
    )

    ledger["access_count"] = 1
    ledger["status"] = "consumed_passed"
    with pytest.raises(ValueError, match="already been accessed"):
        validate_future_heldout_access(
            protocol,
            development_report=report,
            ledger=ledger,
        )


def test_hierarchical_ranker_masks_illegal_candidates_and_bounds_correction() -> None:
    model = HierarchicalIntentLegalCandidateRanker(
        hidden_dim=8,
        maximum_absolute_logit_adjustment=1.25,
    )
    features = torch.zeros((2, 3, len(ACTIVE_VISION_FEATURE_NAMES)))
    mask = torch.tensor([[True, True, False], [True, False, False]])
    candidate_intents = torch.tensor([[0, 1, 3], [2, 0, 0]])

    output = model(features, mask, candidate_intents)

    assert torch.isneginf(output.candidate_logits[0, 2])
    assert torch.isneginf(output.candidate_logits[1, 1:]).all()
    assert output.legal_intent_mask.tolist() == [
        [True, True, False, False],
        [False, False, True, False],
    ]
    assert float(
        torch.max(torch.abs(output.bounded_intent_adjustment)).detach()
    ) <= 1.25
    assert torch.argmax(output.candidate_logits, dim=1).tolist()[1] == 0


def test_class_balanced_auxiliary_loss_upweights_minority_and_is_finite() -> None:
    labels = np.asarray([0] * 100 + [1] * 4 + [2] * 20 + [3] * 40, dtype=np.int64)
    profile = bounded_class_balanced_intent_weights(
        labels,
        intent_count=4,
        exponent=0.5,
        maximum_weight_ratio=4.0,
    )
    weights = np.asarray(profile["weight_by_code"])
    model = HierarchicalIntentLegalCandidateRanker(
        hidden_dim=8,
        maximum_absolute_logit_adjustment=1.25,
    )
    features = torch.zeros((2, 4, len(ACTIVE_VISION_FEATURE_NAMES)))
    mask = torch.ones((2, 4), dtype=torch.bool)
    candidate_intents = torch.tensor([[0, 1, 2, 3], [0, 1, 2, 3]])
    output = model(features, mask, candidate_intents)
    losses = hierarchical_intent_ranking_loss(
        output,
        selected_indices=torch.tensor([0, 1]),
        candidate_intents=candidate_intents,
        class_weights=torch.as_tensor(weights, dtype=torch.float32),
        intent_auxiliary_loss_weight=0.75,
    )

    assert weights[1] > weights[0]
    assert np.min(weights) >= 0.25
    assert np.max(weights) <= 4.0
    assert profile["training_sample_weight_mean"] == pytest.approx(1.0)
    assert torch.isfinite(losses["composite_loss"])


def test_class_balanced_weights_reject_missing_minority_intent() -> None:
    with pytest.raises(ValueError, match="minority intent missing"):
        bounded_class_balanced_intent_weights(
            np.asarray([0, 0, 1, 1, 2], dtype=np.int64),
            intent_count=4,
            exponent=0.5,
            maximum_weight_ratio=4.0,
        )


def test_temperature_fit_is_bounded_fixed_grid_validation_contract() -> None:
    logits = np.asarray([[3.0, 1.0], [2.0, 0.0], [0.0, 2.0]], dtype=np.float64)
    selected = np.asarray([0, 1, 1], dtype=np.int64)

    result = fit_validation_temperature(
        logits,
        selected,
        minimum=0.5,
        maximum=5.0,
        grid_size=181,
    )

    assert result["fit_split"] == "validation"
    assert result["test_access"] is False
    assert 0.5 <= result["temperature"] <= 5.0
    assert result["temperature_grid_size"] == 181


def test_training_api_rejects_test_or_future_split_before_model_initialization() -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)

    with pytest.raises(ValueError, match="train and validation only"):
        train_a3_v3_hierarchical_model(
            {},
            {"train": object(), "validation": object(), "test": object()},
            protocol=protocol,
        )
    with pytest.raises(ValueError, match="train and validation only"):
        train_a3_v3_hierarchical_model(
            {},
            {
                "train": object(),
                "validation": object(),
                "future_held_out": object(),
            },
            protocol=protocol,
        )


def test_protocol_and_source_schemas_are_valid_json_objects() -> None:
    for name in (
        "a3_v3_minority_intent_protocol.schema.json",
        "a3_v3_minority_source_manifest.schema.json",
    ):
        payload = json.loads((MODULE_ROOT / "configs" / name).read_text(encoding="utf-8"))
        assert payload["type"] == "object"
        assert payload["additionalProperties"] is False
