from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningSplit,
)
from d4_distributed_fallback.region_resource_learning import (
    LearnedRegionResourcePolicy,
    snapshot_to_region_graph,
)
from d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    _PolicyIdentity,
    build_region_resource_v4_development_fixture,
)
from d4_distributed_fallback.region_resource_v6_transfer_candidate import (
    REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE,
    REGION_RESOURCE_V6_MODEL_VERSION,
    RegionResourceV6BuildConfig,
    RegionResourceV6CandidateError,
    RegionResourceV6ClassBalance,
    RegionResourceV6Permissions,
    V6EdgeTransferGraphActorCritic,
    _directed_edge_identity_signature,
    _directed_transfer_signature,
    _load_v6_model_bundle,
    _model_state_content_sha256,
    _save_v6_model_bundle,
    _v6_checkpoint_selection_key,
    _v6_edge_supervision_components,
    _validate_loaded_splits,
    build_region_resource_v6_transfer_candidate,
    derive_v6_class_balance,
)


torch = pytest.importorskip("torch")


def _balance() -> RegionResourceV6ClassBalance:
    return RegionResourceV6ClassBalance(
        train_sample_count=4,
        positive_sample_count=1,
        negative_sample_count=3,
        edge_count=4,
        positive_edge_count=1,
        zero_edge_count=3,
        positive_sample_weight=3.0,
        negative_sample_weight=1.0,
        positive_edge_weight=3.0,
        zero_edge_weight=1.0,
        raw_positive_sample_ratio=3.0,
        raw_positive_edge_ratio=3.0,
        positive_sample_weight_clipped=False,
        positive_edge_weight_clipped=False,
        train_label_inventory_sha256="a" * 64,
    )


def test_positive_transfer_edge_receives_stronger_activation_signal() -> None:
    logits = torch.zeros((2, 1), requires_grad=True)
    magnitudes = torch.full((2, 1), 0.25, requires_grad=True)
    targets = torch.tensor([[0.35], [0.0]], dtype=torch.float32)
    graph = SimpleNamespace(
        edge_count=2,
        edge_refs=(
            SimpleNamespace(transferable_resources=3),
            SimpleNamespace(transferable_resources=3),
        ),
    )
    components = _v6_edge_supervision_components(
        logits,
        magnitudes,
        graph=graph,
        edge_targets=targets,
        balance=_balance(),
        config=RegionResourceV6BuildConfig(epochs=1),
    )
    loss = (
        components["activation"]
        + components["direction_ranking"]
        + components["positive_edge_count"]
    )
    loss.backward()
    assert abs(float(logits.grad[0, 0])) > abs(float(logits.grad[1, 0]))
    assert abs(float(magnitudes.grad[0, 0])) > 0.0
    assert float(magnitudes.grad[1, 0]) == 0.0


def test_negative_activation_head_keeps_no_transfer() -> None:
    snapshot = build_region_resource_v4_development_fixture(seed=27)
    graph = snapshot_to_region_graph(snapshot)
    model = V6EdgeTransferGraphActorCritic(
        hidden_dim=8,
        message_passing_steps=1,
    )
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.edge_activation_actor[-1].bias.fill_(-5.0)
    output = model(graph)
    assert bool((output.edge_mean < 0.0).all())
    policy = LearnedRegionResourcePolicy(
        model,
        _PolicyIdentity(REGION_RESOURCE_V6_MODEL_VERSION, "0" * 64),
    )
    assert policy.recommend_raw(snapshot).transfers == ()


def test_wrong_direction_and_wrong_edge_are_not_exact_hits() -> None:
    expected = SimpleNamespace(
        transfers=(
            SimpleNamespace(
                edge_id="edge-001",
                source_region_id="region-001",
                target_region_id="region-002",
                resource_count=1,
            ),
        )
    )
    reversed_direction = SimpleNamespace(
        transfers=(
            SimpleNamespace(
                edge_id="edge-001",
                source_region_id="region-002",
                target_region_id="region-001",
                resource_count=1,
            ),
        )
    )
    wrong_edge = SimpleNamespace(
        transfers=(
            SimpleNamespace(
                edge_id="edge-002",
                source_region_id="region-001",
                target_region_id="region-002",
                resource_count=1,
            ),
        )
    )
    assert _directed_transfer_signature(expected) != (
        _directed_transfer_signature(reversed_direction)
    )
    assert _directed_transfer_signature(expected) != (
        _directed_transfer_signature(wrong_edge)
    )
    wrong_count = SimpleNamespace(
        transfers=(
            SimpleNamespace(
                edge_id="edge-001",
                source_region_id="region-001",
                target_region_id="region-002",
                resource_count=2,
            ),
        )
    )
    assert _directed_edge_identity_signature(expected) == (
        _directed_edge_identity_signature(wrong_count)
    )
    assert _directed_transfer_signature(expected) != (
        _directed_transfer_signature(wrong_count)
    )


def test_checkpoint_rejects_all_no_transfer_despite_lower_loss() -> None:
    all_no_transfer = {
        "nondegenerate_checkpoint": False,
        "positive_exact_projected_action_hit_rate": 0.0,
        "correct_directed_transfer_edge_hit_rate": 0.0,
        "negative_exact_baseline_action_hit_rate": 1.0,
        "no_transfer_bias": 1.0,
        "projection_rejection_count": 0,
        "invalid_executable_difference_count": 0,
    }
    executable = {
        "nondegenerate_checkpoint": True,
        "positive_exact_projected_action_hit_rate": 0.5,
        "correct_directed_transfer_edge_hit_rate": 0.5,
        "negative_exact_baseline_action_hit_rate": 0.8,
        "no_transfer_bias": 0.5,
        "projection_rejection_count": 0,
        "invalid_executable_difference_count": 0,
    }
    assert _v6_checkpoint_selection_key(
        executable,
        validation_loss=10.0,
        epoch=10,
    ) > _v6_checkpoint_selection_key(
        all_no_transfer,
        validation_loss=0.001,
        epoch=1,
    )


def test_train_weights_reject_validation_labels() -> None:
    validation_record = SimpleNamespace(
        split=RegionLearningSplit.VALIDATION
    )
    with pytest.raises(
        RegionResourceV6CandidateError,
        match="v6_balance_fit_requires_train_only",
    ):
        derive_v6_class_balance(
            (validation_record,),
            split=RegionLearningSplit.VALIDATION,
        )


@pytest.mark.parametrize("forbidden_seed", (1000, 1019, 3008, 3039))
def test_loaded_split_guard_rejects_holdout_and_external_evaluation(
    forbidden_seed: int,
) -> None:
    loaded = SimpleNamespace(
        episode_records=(
            SimpleNamespace(
                split=RegionLearningSplit.TRAIN,
                source=SimpleNamespace(seed=forbidden_seed),
            ),
            SimpleNamespace(
                split=RegionLearningSplit.VALIDATION,
                source=SimpleNamespace(seed=3),
            ),
        )
    )
    with pytest.raises(
        RegionResourceV6CandidateError,
        match=(
            "formal_holdout_seed_read_forbidden"
            if forbidden_seed < 3000
            else "source_evaluation_seed_read_forbidden"
        ),
    ):
        _validate_loaded_splits(loaded)


def test_bundle_build_and_model_hash_are_repeatable(tmp_path: Path) -> None:
    config = RegionResourceV6BuildConfig(
        hidden_dim=8,
        message_passing_steps=1,
        epochs=1,
    )
    audit = {"content_sha256": "b" * 64}
    bundles = []
    for index in range(2):
        torch.manual_seed(config.random_seed)
        model = V6EdgeTransferGraphActorCritic(
            hidden_dim=config.hidden_dim,
            message_passing_steps=config.message_passing_steps,
        )
        bundle = _save_v6_model_bundle(
            model,
            tmp_path / f"bundle-{index}",
            config=config,
            training_audit=audit,
        )
        loaded_model, loaded_manifest = _load_v6_model_bundle(
            tmp_path / f"bundle-{index}",
            expected_model_version=config.model_version,
            expected_state_file_sha256=bundle[
                "state_dict_file_sha256"
            ],
        )
        assert loaded_manifest["content_sha256"] == bundle["content_sha256"]
        assert _model_state_content_sha256(loaded_model) == (
            bundle["model_state_content_sha256"]
        )
        bundles.append(bundle)
    assert bundles[0] == bundles[1]


def test_permissions_and_confidence_floor_remain_closed() -> None:
    assert REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE == 0.60
    permissions = RegionResourceV6Permissions().to_dict()
    assert all(
        value is False
        for name, value in permissions.items()
        if name != "schema"
    )


def test_builder_rejects_output_inside_frozen_v4(tmp_path: Path) -> None:
    source = tmp_path / "region_resource_a2_executable_transfer_shadow_v4"
    output = source / "region_resource_a2_edge_transfer_shadow_v6"
    with pytest.raises(
        RegionResourceV6CandidateError,
        match="v6_candidate_output_inside_frozen_v4_forbidden",
    ):
        build_region_resource_v6_transfer_candidate(source, output)
