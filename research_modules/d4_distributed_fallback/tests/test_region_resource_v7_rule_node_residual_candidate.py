from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningSplit,
)
from d4_distributed_fallback.region_resource_learning import (
    snapshot_to_region_graph,
)
from d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    build_region_resource_v4_development_fixture,
)
from d4_distributed_fallback.region_resource_v7_rule_node_residual_candidate import (
    REGION_RESOURCE_V7_MODEL_VERSION,
    REGION_RESOURCE_V7_SOURCE_A_ID,
    REGION_RESOURCE_V7_SOURCE_B_DATASET_SHA256,
    REGION_RESOURCE_V7_SOURCE_B_ID,
    REGION_RESOURCE_V7_SOURCE_B_SPLIT_SHA256,
    RegionResourceV7BuildConfig,
    RegionResourceV7CandidateError,
    RegionResourceV7Permissions,
    RegionResourceV7TrainBalance,
    V7ModelIdentity,
    V7RuleNodeTransferResidualPolicy,
    V7TransferResidualGraphActor,
    V7TransferResidualOutput,
    _V7ResidualRecord,
    _load_v7_model_bundle,
    _model_state_content_sha256,
    _node_nontransfer_fields_equal,
    _residual_signature,
    _save_v7_model_bundle,
    _v7_checkpoint_selection_key,
    _v7_loss_components,
    _v7_m16n24_development_gate_passed,
    _validate_v7_loaded_source,
    build_region_resource_v7_rule_node_residual_candidate,
)


torch = pytest.importorskip("torch")


def _rule_policy() -> RuleRegionResourcePolicy:
    return RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=DeterministicResourceProjector(_V4_PROJECTION),
    )


def _balance() -> RegionResourceV7TrainBalance:
    return RegionResourceV7TrainBalance(
        train_sample_count=2,
        positive_frame_count=1,
        negative_frame_count=1,
        edge_count=4,
        positive_residual_edge_count=1,
        zero_residual_edge_count=3,
        positive_frame_weight=1.0,
        negative_frame_weight=1.0,
        positive_edge_weight=3.0,
        zero_edge_weight=1.0,
        source_sample_counts={
            REGION_RESOURCE_V7_SOURCE_A_ID: 1,
            REGION_RESOURCE_V7_SOURCE_B_ID: 1,
        },
        source_sample_weights={
            REGION_RESOURCE_V7_SOURCE_A_ID: 1.0,
            REGION_RESOURCE_V7_SOURCE_B_ID: 1.0,
        },
        train_label_inventory_sha256="a" * 64,
    )


def _record(
    *,
    positive: bool,
    source_id: str = REGION_RESOURCE_V7_SOURCE_A_ID,
) -> _V7ResidualRecord:
    snapshot = build_region_resource_v4_development_fixture(seed=27)
    graph = snapshot_to_region_graph(snapshot)
    baseline = _rule_policy().recommend(snapshot)
    activation = torch.zeros((graph.edge_count, 1), dtype=torch.float32)
    count = torch.zeros_like(activation)
    residual_count = 0
    if positive:
        activation[0, 0] = 1.0
        count[0, 0] = 1.0
        residual_count = 1
    return _V7ResidualRecord(
        source_id=source_id,
        source_record=SimpleNamespace(
            split=RegionLearningSplit.TRAIN,
            target_positive=positive,
            sample=SimpleNamespace(graph=graph),
            snapshot=snapshot,
            target=baseline,
        ),
        baseline=baseline,
        activation_targets=activation,
        count_targets=count,
        baseline_transfer_fractions=torch.zeros_like(activation),
        residual_edge_count=residual_count,
    )


def test_policy_inherits_every_r0_node_field_before_projection() -> None:
    snapshot = build_region_resource_v4_development_fixture(seed=27)
    graph = snapshot_to_region_graph(snapshot)
    baseline = _rule_policy().recommend(snapshot)
    model = V7TransferResidualGraphActor(hidden_dim=8)
    baseline_counts = {
        (
            transfer.edge_id,
            transfer.source_region_id,
            transfer.target_region_id,
        ): transfer.resource_count
        for transfer in baseline.transfers
    }
    selected = graph.edge_refs[0]
    key = (
        selected.edge_id,
        selected.source_region_id,
        selected.target_region_id,
    )
    selected_count = (
        1 if baseline_counts.get(key, 0) != 1 else 2
    )

    def forward(graph_value, baseline_fractions):
        logits = torch.full((graph_value.edge_count, 1), -5.0)
        counts = torch.zeros_like(logits)
        logits[0, 0] = 5.0
        counts[0, 0] = float(selected_count)
        return V7TransferResidualOutput(
            activation_logits=logits,
            resource_counts=counts,
            frame_activation_logit=torch.tensor(5.0),
        )

    model.forward = forward
    decision = V7RuleNodeTransferResidualPolicy(
        model,
        V7ModelIdentity(REGION_RESOURCE_V7_MODEL_VERSION, "0" * 64),
        rule_policy=_rule_policy(),
    ).decide(snapshot)
    assert decision.recommendation.actions == baseline.actions
    assert _node_nontransfer_fields_equal(
        decision.recommendation,
        baseline,
    )
    actual_counts = {
        (
            transfer.edge_id,
            transfer.source_region_id,
            transfer.target_region_id,
        ): transfer.resource_count
        for transfer in decision.recommendation.transfers
    }
    assert actual_counts[key] == selected_count
    assert decision.activated_edge_keys == (key,)


@pytest.mark.parametrize(
    "field_name",
    ("resource_quota_delta", "reasons"),
)
def test_node_preservation_rejects_any_raw_action_field_change(
    field_name: str,
) -> None:
    snapshot = build_region_resource_v4_development_fixture(seed=27)
    baseline = _rule_policy().recommend(snapshot)
    actions = list(baseline.actions)
    if field_name == "resource_quota_delta":
        actions[0] = replace(
            actions[0],
            resource_quota_delta=actions[0].resource_quota_delta + 1,
        )
        actions[1] = replace(
            actions[1],
            resource_quota_delta=actions[1].resource_quota_delta - 1,
        )
    else:
        actions[0] = replace(
            actions[0],
            reasons=("unauthorized-learned-node-reason",),
        )
    changed = replace(
        baseline,
        actions=tuple(actions),
    )
    assert not _node_nontransfer_fields_equal(changed, baseline)


def test_negative_frame_gate_preserves_r0_even_with_high_edge_logit() -> None:
    snapshot = build_region_resource_v4_development_fixture(seed=29)
    graph = snapshot_to_region_graph(snapshot)
    baseline = _rule_policy().recommend(snapshot)
    model = V7TransferResidualGraphActor(hidden_dim=8)

    def forward(graph_value, baseline_fractions):
        return V7TransferResidualOutput(
            activation_logits=torch.full(
                (graph_value.edge_count, 1), 10.0
            ),
            resource_counts=torch.ones((graph_value.edge_count, 1)),
            frame_activation_logit=torch.tensor(-5.0),
        )

    model.forward = forward
    decision = V7RuleNodeTransferResidualPolicy(
        model,
        V7ModelIdentity(REGION_RESOURCE_V7_MODEL_VERSION, "0" * 64),
        rule_policy=_rule_policy(),
    ).decide(snapshot)
    assert decision.activated_edge_keys == ()
    assert decision.recommendation.actions == baseline.actions
    assert decision.recommendation.transfers == baseline.transfers


def test_positive_residual_loss_updates_edge_frame_and_count_heads() -> None:
    model = V7TransferResidualGraphActor(hidden_dim=8)
    loss, _ = _v7_loss_components(
        model,
        _record(positive=True),
        balance=_balance(),
        config=RegionResourceV7BuildConfig(
            hidden_dim=8,
            epochs=1,
        ),
    )
    loss.backward()
    assert model.activation_head.bias.grad is not None
    assert abs(float(model.activation_head.bias.grad[0])) > 0.0
    assert model.count_head.bias.grad is not None
    assert abs(float(model.count_head.bias.grad[0])) > 0.0
    frame_bias = model.frame_activation_head[-1].bias.grad
    assert frame_bias is not None
    assert abs(float(frame_bias[0])) > 0.0


def test_negative_no_transfer_loss_pushes_frame_gate_down() -> None:
    model = V7TransferResidualGraphActor(hidden_dim=8)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
    loss, components = _v7_loss_components(
        model,
        _record(positive=False),
        balance=_balance(),
        config=RegionResourceV7BuildConfig(
            hidden_dim=8,
            epochs=1,
        ),
    )
    loss.backward()
    assert (
        float(components["negative_no_transfer"].detach().cpu()) > 0.0
    )
    frame_bias = model.frame_activation_head[-1].bias.grad
    assert frame_bias is not None
    assert float(frame_bias[0]) > 0.0


def test_wrong_direction_and_resource_count_change_residual_signature() -> None:
    baseline: dict[tuple[str, str, str], int] = {}
    expected = {("edge-001", "region-001", "region-002"): 1}
    reversed_direction = {
        ("edge-001", "region-002", "region-001"): 1
    }
    wrong_count = {("edge-001", "region-001", "region-002"): 2}
    assert _residual_signature(baseline, expected) != (
        _residual_signature(baseline, reversed_direction)
    )
    assert _residual_signature(baseline, expected) != (
        _residual_signature(baseline, wrong_count)
    )


def test_checkpoint_rejects_no_transfer_even_with_lower_loss() -> None:
    no_transfer = {
        "development_gate_passed": False,
        "positive_exact_projected_action_hit_count": 0,
        "correct_directed_residual_edge_hit_count": 0,
        "negative_exact_r0_action_hit_count": 11,
        "invariant_failure_count": 0,
        "negative_false_transfer_count": 0,
        "projection_rejection_count": 0,
    }
    qualifying = {
        "development_gate_passed": True,
        "positive_exact_projected_action_hit_count": 1,
        "correct_directed_residual_edge_hit_count": 1,
        "negative_exact_r0_action_hit_count": 8,
        "invariant_failure_count": 0,
        "negative_false_transfer_count": 3,
        "projection_rejection_count": 0,
    }
    assert _v7_checkpoint_selection_key(
        qualifying,
        validation_loss=10.0,
        epoch=10,
    ) > _v7_checkpoint_selection_key(
        no_transfer,
        validation_loss=0.001,
        epoch=1,
    )


def test_m16n24_gate_requires_positive_raw_negative_and_invariants() -> None:
    passing = {
        "target_negative_count": 11,
        "positive_exact_projected_action_hit_count": 1,
        "negative_exact_r0_action_hit_count": 8,
        "actor_raw_residual_activation_count": 1,
        "actor_raw_transfer_change_count": 1,
        "projection_rejection_count": 0,
        "invariant_failure_count": 0,
        "r0_node_action_preservation_failure_count": 0,
    }
    assert _v7_m16n24_development_gate_passed(passing)
    for field, value in (
        ("positive_exact_projected_action_hit_count", 0),
        ("negative_exact_r0_action_hit_count", 7),
        ("actor_raw_residual_activation_count", 0),
        ("actor_raw_transfer_change_count", 0),
        ("projection_rejection_count", 1),
        ("invariant_failure_count", 1),
        ("r0_node_action_preservation_failure_count", 1),
    ):
        failing = dict(passing)
        failing[field] = value
        assert not _v7_m16n24_development_gate_passed(failing)


@pytest.mark.parametrize(
    ("seed", "reason"),
    (
        (1000, "formal_holdout"),
        (1019, "formal_holdout"),
        (3008, "prior_evaluation"),
        (3039, "prior_evaluation"),
        (5216, "independent_evaluation"),
        (5279, "independent_evaluation"),
    ),
)
def test_source_guard_rejects_forbidden_seed(
    seed: int,
    reason: str,
) -> None:
    loaded = SimpleNamespace(
        episode_records=(
            SimpleNamespace(
                split=RegionLearningSplit.TRAIN,
                source=SimpleNamespace(seed=seed),
            ),
            SimpleNamespace(
                split=RegionLearningSplit.VALIDATION,
                source=SimpleNamespace(seed=3),
            ),
        )
    )
    with pytest.raises(
        RegionResourceV7CandidateError,
        match=f"v7_{reason}_seed_read_forbidden",
    ):
        _validate_v7_loaded_source(loaded)


def test_source_guard_rejects_test_payload() -> None:
    loaded = SimpleNamespace(
        episode_records=(
            SimpleNamespace(
                split=RegionLearningSplit.TRAIN,
                source=SimpleNamespace(seed=1),
            ),
            SimpleNamespace(
                split=RegionLearningSplit.TEST,
                source=SimpleNamespace(seed=2),
            ),
        )
    )
    with pytest.raises(
        RegionResourceV7CandidateError,
        match="train_validation_only",
    ):
        _validate_v7_loaded_source(loaded)


def test_bundle_and_model_hash_are_repeatable(tmp_path: Path) -> None:
    config = RegionResourceV7BuildConfig(
        hidden_dim=8,
        epochs=1,
    )
    audit = {"content_sha256": "b" * 64}
    bundles = []
    payloads = []
    for index in range(2):
        torch.manual_seed(config.random_seed)
        model = V7TransferResidualGraphActor(hidden_dim=config.hidden_dim)
        bundle = _save_v7_model_bundle(
            model,
            tmp_path / f"bundle-{index}",
            config=config,
            training_audit=audit,
        )
        loaded, manifest = _load_v7_model_bundle(
            tmp_path / f"bundle-{index}",
            expected_model_version=config.model_version,
            expected_state_file_sha256=bundle[
                "state_dict_file_sha256"
            ],
        )
        assert manifest == bundle
        assert _model_state_content_sha256(loaded) == (
            bundle["model_state_content_sha256"]
        )
        bundles.append(bundle)
        payloads.append(
            {
                path.name: path.read_bytes()
                for path in (tmp_path / f"bundle-{index}").iterdir()
            }
        )
    assert bundles[0] == bundles[1]
    assert payloads[0] == payloads[1]


def test_permissions_identity_and_source_hashes_are_frozen() -> None:
    assert REGION_RESOURCE_V7_SOURCE_B_DATASET_SHA256 == (
        "b1295091d4d79e423e1ced02269895d486e2dbcca9d80834d5af0cc14882b42c"
    )
    assert REGION_RESOURCE_V7_SOURCE_B_SPLIT_SHA256 == (
        "c767a48b90f6e2a3f077be4f931d95102a6b2a925a2f813ca8440c8951aae332"
    )
    permissions = RegionResourceV7Permissions().to_dict()
    assert all(
        value is False
        for name, value in permissions.items()
        if name != "schema"
    )
    model = V7TransferResidualGraphActor(hidden_dim=8)
    assert not any(
        "node_actor" in name for name, _ in model.named_parameters()
    )


def test_builder_rejects_output_inside_frozen_source(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path / "region_resource_a2_executable_transfer_shadow_v4"
    )
    output = (
        source
        / "run"
        / "region_resource_a2_rule_node_transfer_residual_shadow_v7"
    )
    with pytest.raises(
        RegionResourceV7CandidateError,
        match="output_inside_source_forbidden",
    ):
        build_region_resource_v7_rule_node_residual_candidate(
            source,
            tmp_path / "m16n24",
            output,
        )
