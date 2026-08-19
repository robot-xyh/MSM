from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from dual_optical_100target_gnn.assignment import (
    probability_threshold_to_unmatched_cost,
)
from dual_optical_100target_gnn.comparison import (
    COMPARISON_SCHEMA_VERSION,
    compare_exports,
    grouped_bootstrap,
)
from dual_optical_100target_gnn.corruption import corrupt_episode
from dual_optical_100target_gnn.dataset import (
    PROTOCOL_EXPANDED_FORMAL,
    PROTOCOL_LEGACY_FORMAL,
    PROTOCOL_NONFORMAL,
    canonical_json_sha256,
    candidate_graph_fingerprint,
    prepare_dataset,
    protocol_profile,
)
from dual_optical_100target_gnn.graph import build_graph
from dual_optical_100target_gnn.loader import load_offline_labels, load_online_episode
from dual_optical_100target_gnn.schema import CORRUPTION_LEVELS, DEFAULT_SPLITS
from dual_optical_100target_gnn.training import (
    TrainingConfig,
    _validate_expanded_formal_config,
    _validate_validation_selection_contract,
    _validation_selection_key,
)


def test_expanded_formal_protocol_accepts_twenty_new_test_seeds():
    expanded = {
        "train": DEFAULT_SPLITS["train"],
        "val": DEFAULT_SPLITS["val"],
        "test": tuple(range(20260901, 20260921)),
    }
    assert protocol_profile(DEFAULT_SPLITS, 100) == PROTOCOL_LEGACY_FORMAL
    assert protocol_profile(expanded, 100) == PROTOCOL_EXPANDED_FORMAL
    assert (
        protocol_profile(
            {
                "train": tuple(reversed(expanded["train"])),
                "val": tuple(reversed(expanded["val"])),
                "test": tuple(reversed(expanded["test"])),
            },
            100,
        )
        == PROTOCOL_EXPANDED_FORMAL
    )
    assert protocol_profile({**expanded, "test": expanded["test"][:19]}, 100) == PROTOCOL_NONFORMAL
    assert (
        protocol_profile(
            {**expanded, "test": DEFAULT_SPLITS["test"] + expanded["test"]},
            100,
        )
        == PROTOCOL_NONFORMAL
    )


def test_split_overlap_is_rejected_before_episode_access(tmp_path):
    with pytest.raises(ValueError, match="must be disjoint"):
        prepare_dataset(
            {},
            tmp_path / "overlap",
            splits={"train": (1,), "val": (1,), "test": (2,)},
            expected_target_count=4,
        )


def test_candidate_fingerprint_covers_anonymous_graph_inputs(episode_factory):
    root = episode_factory(611)
    episode = load_online_episode(root)
    labels = load_offline_labels(root, episode)
    corrupted, corrupted_labels, summary = corrupt_episode(
        episode, labels, CORRUPTION_LEVELS["medium"]
    )
    graph, _, _ = build_graph(corrupted, corrupted_labels, summary)
    first = candidate_graph_fingerprint(graph)
    second = candidate_graph_fingerprint(graph)
    changed_features = graph.edge_features.copy()
    changed_features[0, 0] += np.float32(0.01)
    changed = replace(graph, edge_features=changed_features)
    assert first == second
    assert first != candidate_graph_fingerprint(changed)
    assert len(first) == 64


def test_validation_policy_tie_prefers_hybrid_then_higher_probability():
    common = {
        "macro_f1": 0.9,
        "false_association_count": 2,
        "duplicate_identity_match_count": 1,
    }
    learned = {"route": "learned", "probability_threshold": 0.9, **common}
    hybrid_loose = {"route": "hybrid", "probability_threshold": 0.7, **common}
    hybrid_strict = {"route": "hybrid", "probability_threshold": 0.9, **common}
    assert max((learned, hybrid_loose), key=_validation_selection_key) == hybrid_loose
    assert max((hybrid_loose, hybrid_strict), key=_validation_selection_key) == hybrid_strict


def test_validation_contract_ranks_only_hard_gate_eligible_policies():
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    candidates = []
    for route in ("learned", "hybrid"):
        for threshold in thresholds:
            eligible = threshold == (0.9 if route == "learned" else 0.4)
            candidates.append(
                {
                    "route": route,
                    "probability_threshold": threshold,
                    "unmatched_cost": probability_threshold_to_unmatched_cost(
                        threshold
                    ),
                    "macro_precision": 1.0 if eligible else 0.2,
                    "macro_recall": 0.01 if eligible else 0.08,
                    "macro_f1": 0.02 if eligible else 0.03,
                    "noise_macro_recall": 0.005 if eligible else 0.05,
                    "noise_conditional_precision": 1.0 if eligible else 0.2,
                    "noise_false_association_rate": 0.0 if eligible else 0.8,
                    "false_association_count": 0 if eligible else 100,
                    "duplicate_identity_match_count": 0,
                    "duplicate_track_assignment_count": 0,
                    "correct_assignment_count": 1,
                    "route_compute_latency_p95_ms": 2.0,
                    "hard_gate_eligible": eligible,
                    "hard_gate_failure_reasons": []
                    if eligible
                    else ["conditional_precision_below_0_70"],
                }
            )
    best_by_route = {
        "learned": next(
            item
            for item in candidates
            if item["route"] == "learned"
            and item["probability_threshold"] == 0.9
        ),
        "hybrid": next(
            item
            for item in candidates
            if item["route"] == "hybrid"
            and item["probability_threshold"] == 0.4
        ),
    }
    selected = best_by_route["hybrid"]
    selection = {
        "fixed_probability_threshold_candidates": thresholds,
        "hybrid_weights": {"geometry": 0.4, "learned": 0.6},
        "cost_contract": "negative_log_effective_probability_v2",
        "probability_calibration": {
            route: {"edge_count": 1} for route in ("learned", "hybrid")
        },
        "freeze_allowed": True,
        "promotion_allowed": False,
        "promotion_status": "pending_reserved_test_same_input_comparison",
        "validation_failed_closed": False,
        "validation_failure_reasons": [],
        "route_status": {
            route: {"failed_closed": False, "reason": "validated"}
            for route in ("learned", "hybrid")
        },
        "selected_route": selected["route"],
        "selected_probability_threshold": selected["probability_threshold"],
        "selected_unmatched_cost": selected["unmatched_cost"],
        "best_by_route": best_by_route,
        "candidates": candidates,
    }

    _validate_validation_selection_contract(selection)

    selection["promotion_allowed"] = True
    with pytest.raises(ValueError, match="cannot authorize scale promotion"):
        _validate_validation_selection_contract(selection)
    selection["promotion_allowed"] = False

    selection["best_by_route"]["learned"] = candidates[0]
    with pytest.raises(ValueError, match="best policy is inconsistent for learned"):
        _validate_validation_selection_contract(selection)


def test_probability_thresholds_convert_to_negative_log_cost():
    assert probability_threshold_to_unmatched_cost(0.3) == pytest.approx(
        -np.log(0.3), rel=1.0e-12
    )
    assert probability_threshold_to_unmatched_cost(0.9) == pytest.approx(
        -np.log(0.9), rel=1.0e-12
    )
    assert probability_threshold_to_unmatched_cost(0.9) < (
        probability_threshold_to_unmatched_cost(0.3)
    )
    for invalid in (0.0, 1.0, -0.1, float("nan")):
        with pytest.raises(ValueError, match=r"in \(0, 1\)"):
            probability_threshold_to_unmatched_cost(invalid)


def test_expanded_formal_training_hyperparameters_are_fixed():
    manifest = {"protocol_profile": PROTOCOL_EXPANDED_FORMAL}
    _validate_expanded_formal_config(manifest, TrainingConfig(device="cpu"))
    with pytest.raises(ValueError, match="max_epochs=80"):
        _validate_expanded_formal_config(
            manifest,
            TrainingConfig(max_epochs=79, device="cpu"),
        )


def _rows(seed_count: int = 4):
    rows = []
    for seed in range(seed_count):
        for level_index, level in enumerate(CORRUPTION_LEVELS):
            for mode, offset in (("geometry", 0.0), ("learned", 0.04), ("hybrid", 0.03)):
                rows.append(
                    {
                        "seed": seed,
                        "corruption_level": level,
                        "mode": mode,
                        "precision": 0.8 + offset,
                        "recall": 0.7 + offset - level_index * 0.01,
                        "f1": 0.75 + offset - level_index * 0.01,
                        "false_association_count": 3 if mode == "geometry" else 1,
                        "duplicate_identity_match_count": 1,
                    }
                )
    return rows


def test_bootstrap_resamples_complete_seed_groups():
    first = grouped_bootstrap(
        _rows(),
        ("geometry", "learned", "hybrid"),
        CORRUPTION_LEVELS,
        repeats=200,
        random_seed=17,
    )
    second = grouped_bootstrap(
        _rows(),
        ("geometry", "learned", "hybrid"),
        CORRUPTION_LEVELS,
        repeats=200,
        random_seed=17,
    )
    assert first == second
    assert first["seed_count"] == 4
    assert first["resampling_unit"] == "complete_seed_with_all_corruption_levels"
    assert first["paired_delta_vs_reference"]["routes"]["learned"]["macro_f1"][
        "lower_95"
    ] > 0.0


def _comparison_payload(method_family: str, method_id: str, f1: float, candidate: str):
    per_seed = [
        {
            "seed": seed,
            "macro_precision": f1,
            "macro_recall": f1,
            "macro_f1": f1,
            "false_association_count": 1 if method_family == "gnn" else 2,
            "duplicate_identity_match_count": 0,
        }
        for seed in (1, 2, 3, 4)
    ]
    payload = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "method_family": method_family,
        "method_id": method_id,
        "selected_route": method_id,
        "dataset_fingerprint_sha256": "d" * 64,
        "candidate_fingerprint_sha256": candidate,
        "test_seeds": [1, 2, 3, 4],
        "corruption_levels": list(CORRUPTION_LEVELS),
        "aggregate": {
            "macro_precision": f1,
            "macro_recall": f1,
            "macro_f1": f1,
            "false_association_count": 4 if method_family == "gnn" else 8,
            "duplicate_identity_match_count": 0,
        },
        "per_seed": per_seed,
        "latency": {
            "gpu": {"available": 1, "p50_ms": 1.0, "p95_ms": 2.0}
        },
    }
    payload["payload_fingerprint_sha256"] = canonical_json_sha256(payload)
    return payload


def test_external_comparison_requires_identical_candidates_and_paired_gain():
    gnn = _comparison_payload("gnn", "edge_gnn:hybrid", 0.92, "c" * 64)
    baseline = _comparison_payload("lightweight", "logistic", 0.88, "c" * 64)
    result = compare_exports(gnn, baseline, repeats=200, random_seed=19)
    assert result["criteria"]["macro_f1_improvement_at_least_0_02"] is True
    assert result["criteria"]["paired_f1_ci_lower_above_zero"] is True
    assert result["recommend_continue_toward_mainline"] is True

    mismatch = _comparison_payload("lightweight", "logistic", 0.88, "x" * 64)
    with pytest.raises(ValueError, match="candidate_fingerprint_sha256"):
        compare_exports(gnn, mismatch, repeats=200)
