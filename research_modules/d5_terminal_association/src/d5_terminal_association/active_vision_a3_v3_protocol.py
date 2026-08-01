"""Frozen A3 v3 minority-intent development and held-out contracts.

This module validates protocol and source metadata only. It never opens an
episode, assigns a simulation seed, trains a model, or grants runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .active_vision_contracts import ActiveVisionIntent


ACTIVE_VISION_A3_V3_PROTOCOL_SCHEMA_VERSION = (
    "d5.active-vision-a3-minority-intent-protocol.v1"
)
ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "d5.active-vision-a3-minority-source-manifest.v1"
)
ACTIVE_VISION_A3_V3_FUTURE_LEDGER_SCHEMA_VERSION = (
    "d5.active-vision-a3-future-held-out-ledger.v1"
)
ACTIVE_VISION_A3_V3_DEFAULT_STATUS = "protocol_frozen_data_not_generated"

A3_V3_INTENTS = tuple(item.value for item in ActiveVisionIntent)
A3_V3_CAMERA_ROLES = ("interceptor", "recon")
A3_V3_SOURCE_SPLITS = ("train", "validation", "future_held_out")
A3_V3_INTENT_ROLE_CELLS = tuple(
    f"{intent}|{role}"
    for intent in A3_V3_INTENTS
    for role in A3_V3_CAMERA_ROLES
)
A3_V3_HARD_CONFUSION_SCENARIOS = (
    "observe_vs_reacquire_projection_boundary",
    "search_vs_reacquire_cue_loss_boundary",
    "hold_vs_observe_gimbal_busy_boundary",
    "role_matched_interceptor_recon_geometry",
    "multiple_legal_targets_near_tie",
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_FIELDS = (
    "shadow",
    "assist",
    "promotion",
    "ppo",
    "assignment",
    "degradation",
    "runtime",
    "production",
    "control",
    "camera_command",
    "global_track_id_create",
    "global_track_id_write",
)
_EXPECTED_AUTHORITY = {name: False for name in _AUTHORITY_FIELDS}


@dataclass(frozen=True)
class FrozenA3V3Protocol:
    """One immutable protocol file and its byte-level identity."""

    path: Path
    sha256: str
    payload: Mapping[str, Any]

    @property
    def protocol_id(self) -> str:
        return str(self.payload["protocol_id"])

    @property
    def status(self) -> str:
        return str(self.payload["status"])


def load_frozen_a3_v3_protocol(path: str | Path) -> FrozenA3V3Protocol:
    """Load and strictly validate the single frozen A3 v3 protocol."""

    protocol_path = Path(path)
    payload = _read_json(protocol_path)
    validate_frozen_a3_v3_protocol(payload)
    return FrozenA3V3Protocol(
        path=protocol_path,
        sha256=_sha256_file(protocol_path),
        payload=payload,
    )


def validate_frozen_a3_v3_protocol(payload: Mapping[str, Any]) -> None:
    """Reject any protocol that permits test feedback or authority escalation."""

    _expect_fields(
        payload,
        {
            "schema_version",
            "protocol_id",
            "status",
            "frozen_on",
            "evidence_boundary",
            "selection_contract",
            "method",
            "development",
            "gates",
            "source_request",
            "authority",
        },
        "A3 v3 protocol",
    )
    if payload.get("schema_version") != ACTIVE_VISION_A3_V3_PROTOCOL_SCHEMA_VERSION:
        raise ValueError("A3 v3 protocol schema mismatch")
    if not _non_empty_text(payload.get("protocol_id")):
        raise ValueError("A3 v3 protocol_id is unavailable")
    if payload.get("status") != ACTIVE_VISION_A3_V3_DEFAULT_STATUS:
        raise ValueError("A3 v3 protocol must remain data-not-generated")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(payload.get("frozen_on", ""))):
        raise ValueError("A3 v3 frozen_on date is invalid")

    evidence = _mapping(payload.get("evidence_boundary"), "evidence_boundary")
    _expect_fields(
        evidence,
        {
            "method_design_inputs",
            "published_v2_failure_summary_consulted",
            "v2_test_episode_or_sample_read",
            "v2_test_used_for_model_selection_calibration_or_thresholds",
            "formal_seed_1000_1019_episode_read",
        },
        "A3 v3 evidence boundary",
    )
    if evidence.get("method_design_inputs") != [
        "v2_train_structure_facts",
        "v2_validation_structure_facts",
        "published_v2_failure_summary",
    ]:
        raise ValueError("A3 v3 method design evidence boundary mismatch")
    if evidence.get("published_v2_failure_summary_consulted") is not True:
        raise ValueError("A3 v3 published failure summary declaration mismatch")
    for field in (
        "v2_test_episode_or_sample_read",
        "v2_test_used_for_model_selection_calibration_or_thresholds",
        "formal_seed_1000_1019_episode_read",
    ):
        if evidence.get(field) is not False:
            raise ValueError(f"A3 v3 forbidden evidence use: {field}")

    selection = _mapping(payload.get("selection_contract"), "selection_contract")
    expected_selection = {
        "configuration_count": 1,
        "hyperparameter_search": False,
        "best_epoch_uses": "validation_composite_loss_only",
        "calibration_uses": "validation_only",
        "confidence_threshold_uses": "frozen_constant_only",
        "test_used_for_training_model_selection_calibration_or_thresholds": False,
        "future_held_out_access": "one_shot_after_validation_pass_and_model_freeze",
        "future_held_out_maximum_access_count": 1,
        "repeat_after_future_gate_failure": False,
    }
    if selection != expected_selection:
        raise ValueError("A3 v3 selection contract mismatch")

    _validate_method(_mapping(payload.get("method"), "method"))
    _validate_development(_mapping(payload.get("development"), "development"))
    _validate_gates(_mapping(payload.get("gates"), "gates"))
    _validate_source_request(_mapping(payload.get("source_request"), "source_request"))
    _validate_authority(payload.get("authority"), "A3 v3 protocol authority")


def validate_a3_v3_source_manifest(
    protocol: FrozenA3V3Protocol,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate main-assigned seed registries and aggregate source coverage.

    Only registry and coverage metadata are consumed here. Episode payloads are
    deliberately outside this validator.
    """

    validate_frozen_a3_v3_protocol(protocol.payload)
    _expect_fields(
        manifest,
        {
            "schema_version",
            "protocol_id",
            "protocol_sha256",
            "status",
            "dataset_manifest_sha256_by_partition",
            "seed_catalogs",
            "coverage_by_split",
            "provenance",
            "identity",
            "authority",
        },
        "A3 v3 source manifest",
    )
    if manifest.get("schema_version") != ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("A3 v3 source manifest schema mismatch")
    if manifest.get("protocol_id") != protocol.protocol_id:
        raise ValueError("A3 v3 source manifest protocol_id mismatch")
    if manifest.get("protocol_sha256") != protocol.sha256:
        raise ValueError("A3 v3 source manifest protocol SHA-256 mismatch")
    if manifest.get("status") != "source_generated_not_trained":
        raise ValueError("A3 v3 source manifest status mismatch")

    bindings = _mapping(
        manifest.get("dataset_manifest_sha256_by_partition"),
        "dataset_manifest_sha256_by_partition",
    )
    _expect_fields(bindings, {"development", "future_held_out"}, "dataset bindings")
    for name, value in bindings.items():
        _require_sha256(value, f"{name} dataset manifest")

    seed_payload = _mapping(manifest.get("seed_catalogs"), "seed_catalogs")
    _expect_fields(seed_payload, set(A3_V3_SOURCE_SPLITS), "seed catalogs")
    seed_catalogs = {
        split: _strict_seed_catalog(seed_payload[split], f"{split} seeds")
        for split in A3_V3_SOURCE_SPLITS
    }
    for index, left in enumerate(A3_V3_SOURCE_SPLITS):
        for right in A3_V3_SOURCE_SPLITS[index + 1 :]:
            if set(seed_catalogs[left]) & set(seed_catalogs[right]):
                raise ValueError(f"A3 v3 seed overlap: {left}/{right}")

    request = protocol.payload["source_request"]
    prohibited = tuple(
        (int(item["start"]), int(item["end"]), str(item["reason"]))
        for item in request["prohibited_seed_ranges"]
    )
    for split, catalog in seed_catalogs.items():
        for seed in catalog:
            for start, end, reason in prohibited:
                if start <= seed <= end:
                    raise ValueError(
                        f"A3 v3 {split} seed overlaps prohibited range {start}-{end}: {reason}"
                    )

    coverage_payload = _mapping(manifest.get("coverage_by_split"), "coverage_by_split")
    _expect_fields(coverage_payload, set(A3_V3_SOURCE_SPLITS), "coverage splits")
    coverage_summary: dict[str, Any] = {}
    for split in A3_V3_SOURCE_SPLITS:
        coverage_summary[split] = _validate_split_coverage(
            split,
            _mapping(coverage_payload[split], f"{split} coverage"),
            request["coverage_minimums_by_split"][split],
            request["hard_confusion_scenarios"],
            seed_count=len(seed_catalogs[split]),
        )

    provenance = _mapping(manifest.get("provenance"), "provenance")
    expected_provenance = {
        "source_domain": "scalable_3d_point_mass_runtime",
        "synthetic_fixture_episode_count": 0,
        "v2_episode_or_sample_reuse": False,
        "v2_test_episode_or_sample_read_count": 0,
        "formal_seed_1000_1019_episode_read_count": 0,
        "online_truth_id_use_count": 0,
    }
    if provenance != expected_provenance:
        raise ValueError("A3 v3 source provenance contract mismatch")

    identity = _mapping(manifest.get("identity"), "identity")
    if identity != {
        "global_track_id_ownership": "center_read_only",
        "global_track_id_created_count": 0,
        "global_track_id_rewritten_count": 0,
    }:
        raise ValueError("A3 v3 global_track_id ownership contract mismatch")
    _validate_authority(manifest.get("authority"), "A3 v3 source authority")

    return {
        "schema_version": ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION,
        "status": "source_contract_ready_for_development_training",
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "source_manifest_sha256": _sha256_json(manifest),
        "seed_counts": {name: len(values) for name, values in seed_catalogs.items()},
        "seed_overlap_count": 0,
        "prohibited_seed_overlap_count": 0,
        "coverage": coverage_summary,
        "episode_payload_read_count": 0,
        "authority": dict(_EXPECTED_AUTHORITY),
    }


def load_and_validate_a3_v3_source_manifest(
    protocol: FrozenA3V3Protocol,
    path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json(Path(path))
    return manifest, validate_a3_v3_source_manifest(protocol, manifest)


def validate_future_heldout_access(
    protocol: FrozenA3V3Protocol,
    *,
    development_report: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> None:
    """Authorize at most the first held-out access after development freeze."""

    validate_frozen_a3_v3_protocol(protocol.payload)
    _expect_fields(
        development_report,
        {
            "protocol_sha256",
            "source_manifest_sha256",
            "validation_gate_passed",
            "model_frozen",
            "weights_sha256",
            "calibration_sha256",
            "test_or_future_held_out_used_during_development",
            "authority",
        },
        "A3 v3 development report gate",
    )
    if development_report.get("protocol_sha256") != protocol.sha256:
        raise ValueError("A3 v3 development report protocol mismatch")
    _require_sha256(development_report.get("source_manifest_sha256"), "source manifest")
    _require_sha256(development_report.get("weights_sha256"), "development weights")
    _require_sha256(development_report.get("calibration_sha256"), "calibration")
    if development_report.get("validation_gate_passed") is not True:
        raise ValueError("A3 v3 validation gate has not passed")
    if development_report.get("model_frozen") is not True:
        raise ValueError("A3 v3 model is not frozen before held-out access")
    if development_report.get("test_or_future_held_out_used_during_development") is not False:
        raise ValueError("A3 v3 held-out data leaked into development")
    _validate_authority(
        development_report.get("authority"),
        "A3 v3 development report authority",
    )

    _expect_fields(
        ledger,
        {
            "schema_version",
            "protocol_sha256",
            "weights_sha256",
            "access_count",
            "status",
            "selection_feedback_allowed",
        },
        "A3 v3 future held-out ledger",
    )
    if ledger.get("schema_version") != ACTIVE_VISION_A3_V3_FUTURE_LEDGER_SCHEMA_VERSION:
        raise ValueError("A3 v3 future held-out ledger schema mismatch")
    if ledger.get("protocol_sha256") != protocol.sha256:
        raise ValueError("A3 v3 future held-out ledger protocol mismatch")
    if ledger.get("weights_sha256") != development_report.get("weights_sha256"):
        raise ValueError("A3 v3 future held-out ledger model mismatch")
    if ledger.get("access_count") != 0 or ledger.get("status") != "unopened":
        raise ValueError("A3 v3 future held-out set has already been accessed")
    if ledger.get("selection_feedback_allowed") is not False:
        raise ValueError("A3 v3 future held-out feedback contract mismatch")


def _validate_method(method: Mapping[str, Any]) -> None:
    _expect_fields(
        method,
        {
            "architecture",
            "candidate_encoder",
            "set_pooling",
            "intent_head_class_count",
            "candidate_rank_head",
            "legal_candidate_mask_required",
            "illegal_candidate_logit",
            "bounded_intent_fusion",
            "loss",
            "rule_fallback_required",
        },
        "A3 v3 method",
    )
    expected = {
        "architecture": "hierarchical_set_context_intent_plus_legal_candidate_ranker",
        "candidate_encoder": "shared_mlp_tanh",
        "set_pooling": "masked_mean_plus_masked_max",
        "intent_head_class_count": len(A3_V3_INTENTS),
        "candidate_rank_head": "shared_scalar",
        "legal_candidate_mask_required": True,
        "illegal_candidate_logit": "negative_infinity_before_softmax",
        "rule_fallback_required": True,
    }
    for name, value in expected.items():
        if method.get(name) != value:
            raise ValueError(f"A3 v3 method contract mismatch: {name}")

    fusion = _mapping(method.get("bounded_intent_fusion"), "bounded_intent_fusion")
    if set(fusion) != {"function", "maximum_absolute_logit_adjustment"}:
        raise ValueError("A3 v3 bounded fusion fields mismatch")
    if fusion.get("function") != "maximum_abs_times_tanh":
        raise ValueError("A3 v3 bounded fusion function mismatch")
    _bounded_positive(
        fusion.get("maximum_absolute_logit_adjustment"),
        "maximum_absolute_logit_adjustment",
        maximum=4.0,
    )

    loss = _mapping(method.get("loss"), "loss")
    expected_loss_fields = {
        "ranking",
        "intent_auxiliary",
        "intent_class_balance",
        "class_balance_split",
        "class_balance_exponent",
        "maximum_class_weight_ratio",
        "class_weight_absolute_bounds",
        "ranking_loss_weight",
        "intent_auxiliary_loss_weight",
    }
    _expect_fields(loss, expected_loss_fields, "A3 v3 loss")
    if loss.get("ranking") != "legal_candidate_cross_entropy":
        raise ValueError("A3 v3 ranking loss mismatch")
    if loss.get("intent_auxiliary") != "class_balanced_cross_entropy":
        raise ValueError("A3 v3 intent auxiliary loss mismatch")
    if loss.get("intent_class_balance") != "bounded_inverse_sqrt":
        raise ValueError("A3 v3 class balance method mismatch")
    if loss.get("class_balance_split") != "train_only":
        raise ValueError("A3 v3 class balance must use train only")
    if float(loss.get("class_balance_exponent", -1.0)) != 0.5:
        raise ValueError("A3 v3 class balance exponent mismatch")
    ratio = _bounded_positive(
        loss.get("maximum_class_weight_ratio"),
        "maximum_class_weight_ratio",
        maximum=8.0,
    )
    bounds = loss.get("class_weight_absolute_bounds")
    if bounds != [1.0 / ratio, ratio]:
        raise ValueError("A3 v3 class weight bounds mismatch")
    if float(loss.get("ranking_loss_weight", -1.0)) != 1.0:
        raise ValueError("A3 v3 ranking loss weight mismatch")
    _bounded_positive(
        loss.get("intent_auxiliary_loss_weight"),
        "intent_auxiliary_loss_weight",
        maximum=1.0,
    )


def _validate_development(development: Mapping[str, Any]) -> None:
    _expect_fields(
        development,
        {
            "optimizer",
            "best_epoch",
            "calibration",
            "proposal_confidence_floor",
        },
        "A3 v3 development",
    )
    optimizer = _mapping(development.get("optimizer"), "optimizer")
    _expect_fields(
        optimizer,
        {
            "random_seed_not_episode_seed",
            "epochs",
            "batch_size",
            "evaluation_batch_size",
            "learning_rate",
            "weight_decay",
            "hidden_dim",
            "device",
            "cpu_threads",
        },
        "A3 v3 optimizer",
    )
    for name in (
        "random_seed_not_episode_seed",
        "epochs",
        "batch_size",
        "evaluation_batch_size",
        "hidden_dim",
        "cpu_threads",
    ):
        _positive_int(optimizer.get(name), name)
    _bounded_positive(optimizer.get("learning_rate"), "learning_rate", maximum=1.0)
    weight_decay = _finite_number(optimizer.get("weight_decay"), "weight_decay")
    if weight_decay < 0.0 or weight_decay > 1.0:
        raise ValueError("A3 v3 weight_decay is out of bounds")
    if optimizer.get("device") != "cpu":
        raise ValueError("A3 v3 frozen optimizer device must be cpu")

    if development.get("best_epoch") != {
        "metric": "validation_composite_loss",
        "direction": "minimize",
        "tie_break": "earliest_epoch",
        "tie_tolerance": 1.0e-12,
        "train_weight_source": "train_only",
        "test_access": False,
    }:
        raise ValueError("A3 v3 best epoch rule mismatch")

    calibration = _mapping(development.get("calibration"), "calibration")
    _expect_fields(
        calibration,
        {
            "method",
            "fit_split",
            "objective",
            "temperature_minimum",
            "temperature_maximum",
            "temperature_grid_size",
            "tie_break",
            "test_access",
            "ece_bin_count",
        },
        "A3 v3 calibration",
    )
    if calibration.get("method") != "scalar_temperature_fixed_grid":
        raise ValueError("A3 v3 calibration method mismatch")
    if calibration.get("fit_split") != "validation":
        raise ValueError("A3 v3 calibration must use validation only")
    if calibration.get("objective") != "candidate_negative_log_likelihood":
        raise ValueError("A3 v3 calibration objective mismatch")
    minimum = _bounded_positive(
        calibration.get("temperature_minimum"),
        "temperature_minimum",
        maximum=10.0,
    )
    maximum = _bounded_positive(
        calibration.get("temperature_maximum"),
        "temperature_maximum",
        maximum=10.0,
    )
    if minimum >= maximum:
        raise ValueError("A3 v3 temperature bounds are inverted")
    if _positive_int(calibration.get("temperature_grid_size"), "temperature_grid_size") < 2:
        raise ValueError("A3 v3 temperature grid requires at least two points")
    if calibration.get("tie_break") != "lowest_temperature":
        raise ValueError("A3 v3 calibration tie break mismatch")
    if calibration.get("test_access") is not False:
        raise ValueError("A3 v3 calibration cannot access test")
    _positive_int(calibration.get("ece_bin_count"), "ece_bin_count")
    confidence_floor = _finite_number(
        development.get("proposal_confidence_floor"),
        "proposal_confidence_floor",
    )
    if not 0.0 < confidence_floor < 1.0:
        raise ValueError("A3 v3 proposal confidence floor must be in (0, 1)")


def _validate_gates(gates: Mapping[str, Any]) -> None:
    _expect_fields(gates, {"validation", "future_held_out_one_shot"}, "A3 v3 gates")
    validation = _mapping(gates.get("validation"), "validation gate")
    future = _mapping(gates.get("future_held_out_one_shot"), "future gate")
    _validate_metric_gate(validation, "validation")
    _validate_metric_gate(future, "future_held_out")
    if validation.get("data_split") != "validation":
        raise ValueError("A3 v3 development gate must use validation")
    if validation.get("required_before_model_freeze") is not True:
        raise ValueError("A3 v3 validation gate must precede model freeze")
    if future.get("data_split") != "future_held_out":
        raise ValueError("A3 v3 future gate split mismatch")
    if future.get("access_policy") != (
        "one_shot_after_validation_pass_and_model_freeze"
    ):
        raise ValueError("A3 v3 future held-out access policy mismatch")
    if future.get("maximum_access_count") != 1:
        raise ValueError("A3 v3 future held-out maximum access mismatch")
    if future.get("on_failure") != (
        "fail_closed_no_retrain_no_recalibration_no_threshold_change_no_second_access"
    ):
        raise ValueError("A3 v3 future held-out failure policy mismatch")


def _validate_metric_gate(gate: Mapping[str, Any], label: str) -> None:
    common = {
        "data_split",
        "minimum_macro_intent_recall",
        "minimum_per_intent_recall",
        "minimum_per_camera_role_exact_action_accuracy",
        "maximum_expected_calibration_error",
    }
    extra = (
        {"required_before_model_freeze"}
        if label == "validation"
        else {"access_policy", "maximum_access_count", "on_failure"}
    )
    _expect_fields(gate, common | extra, f"A3 v3 {label} metric gate")
    for field in (
        "minimum_macro_intent_recall",
        "maximum_expected_calibration_error",
    ):
        _unit_interval(gate.get(field), f"{label}.{field}")
    per_intent = _mapping(
        gate.get("minimum_per_intent_recall"),
        f"{label}.minimum_per_intent_recall",
    )
    _expect_fields(per_intent, set(A3_V3_INTENTS), f"{label} intent gates")
    for intent, value in per_intent.items():
        _unit_interval(value, f"{label}.{intent} recall")
    per_role = _mapping(
        gate.get("minimum_per_camera_role_exact_action_accuracy"),
        f"{label}.minimum_per_camera_role_exact_action_accuracy",
    )
    _expect_fields(per_role, set(A3_V3_CAMERA_ROLES), f"{label} role gates")
    for role, value in per_role.items():
        _unit_interval(value, f"{label}.{role} exact action")


def _validate_source_request(request: Mapping[str, Any]) -> None:
    _expect_fields(
        request,
        {
            "seed_assignment_owner",
            "development_seed_values",
            "future_evaluation_seed_values",
            "new_episode_generation_required",
            "whole_episode_seed_atomic",
            "synthetic_fixture_allowed",
            "online_truth_free_required",
            "global_track_id_ownership",
            "prohibited_seed_ranges",
            "required_intents",
            "required_camera_roles",
            "coverage_minimums_by_split",
            "hard_confusion_scenarios",
        },
        "A3 v3 source request",
    )
    if request.get("seed_assignment_owner") != "main":
        raise ValueError("A3 v3 episode seed assignment must remain main-owned")
    if request.get("development_seed_values") is not None:
        raise ValueError("A3 v3 development episode seeds must remain unassigned")
    if request.get("future_evaluation_seed_values") is not None:
        raise ValueError("A3 v3 future episode seeds must remain unassigned")
    expected_flags = {
        "new_episode_generation_required": True,
        "whole_episode_seed_atomic": True,
        "synthetic_fixture_allowed": False,
        "online_truth_free_required": True,
        "global_track_id_ownership": "center_read_only",
    }
    for name, value in expected_flags.items():
        if request.get(name) != value:
            raise ValueError(f"A3 v3 source request mismatch: {name}")
    if request.get("required_intents") != list(A3_V3_INTENTS):
        raise ValueError("A3 v3 required intent catalog mismatch")
    if request.get("required_camera_roles") != list(A3_V3_CAMERA_ROLES):
        raise ValueError("A3 v3 required camera role catalog mismatch")

    ranges = request.get("prohibited_seed_ranges")
    if ranges != [
        {"start": 1000, "end": 1019, "reason": "formal_reserved_evaluation"},
        {"start": 22100, "end": 22199, "reason": "a3_v2_all_splits_and_test"},
    ]:
        raise ValueError("A3 v3 prohibited seed ranges mismatch")

    minimums = _mapping(
        request.get("coverage_minimums_by_split"),
        "coverage_minimums_by_split",
    )
    _expect_fields(minimums, set(A3_V3_SOURCE_SPLITS), "coverage minimum splits")
    for split in A3_V3_SOURCE_SPLITS:
        policy = _mapping(minimums[split], f"{split} coverage policy")
        _expect_fields(
            policy,
            {"total", "per_intent", "per_camera_role", "per_intent_camera_role"},
            f"{split} coverage policy",
        )
        _validate_minimum_triplet(policy["total"], f"{split}.total", samples=True)
        _validate_minimum_triplet(
            policy["per_intent"], f"{split}.per_intent", samples=True
        )
        _validate_minimum_triplet(
            policy["per_camera_role"], f"{split}.per_camera_role", samples=True
        )
        _validate_minimum_triplet(
            policy["per_intent_camera_role"],
            f"{split}.per_intent_camera_role",
            samples=True,
        )

    scenarios = request.get("hard_confusion_scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != len(
        A3_V3_HARD_CONFUSION_SCENARIOS
    ):
        raise ValueError("A3 v3 hard confusion scenario catalog mismatch")
    ids = [item.get("id") for item in scenarios if isinstance(item, Mapping)]
    if ids != list(A3_V3_HARD_CONFUSION_SCENARIOS):
        raise ValueError("A3 v3 hard confusion scenario order mismatch")
    for item in scenarios:
        _expect_fields(
            item,
            {
                "id",
                "description",
                "minimum_unique_episodes_by_split",
                "minimum_unique_seeds_by_split",
            },
            "A3 v3 hard confusion scenario",
        )
        if not _non_empty_text(item.get("description")):
            raise ValueError("A3 v3 hard confusion description is unavailable")
        for field in (
            "minimum_unique_episodes_by_split",
            "minimum_unique_seeds_by_split",
        ):
            values = _mapping(item.get(field), field)
            _expect_fields(values, set(A3_V3_SOURCE_SPLITS), field)
            for split, value in values.items():
                _positive_int(value, f"{item['id']}.{split}.{field}")


def _validate_split_coverage(
    split: str,
    coverage: Mapping[str, Any],
    policy: Mapping[str, Any],
    scenarios: Sequence[Mapping[str, Any]],
    *,
    seed_count: int,
) -> dict[str, Any]:
    _expect_fields(
        coverage,
        {
            "total",
            "by_intent",
            "by_camera_role",
            "by_intent_camera_role",
            "hard_confusion_scenarios",
        },
        f"{split} coverage",
    )
    total = _count_triplet(coverage["total"], f"{split}.total")
    if total["unique_seeds"] != seed_count:
        raise ValueError(f"A3 v3 {split} seed coverage differs from registry")
    _require_minimums(total, policy["total"], f"{split}.total")

    by_intent = _mapping(coverage["by_intent"], f"{split}.by_intent")
    _expect_fields(by_intent, set(A3_V3_INTENTS), f"{split} intent coverage")
    for intent in A3_V3_INTENTS:
        counts = _count_triplet(by_intent[intent], f"{split}.{intent}")
        _require_minimums(counts, policy["per_intent"], f"{split}.{intent}")

    by_role = _mapping(coverage["by_camera_role"], f"{split}.by_camera_role")
    _expect_fields(by_role, set(A3_V3_CAMERA_ROLES), f"{split} role coverage")
    for role in A3_V3_CAMERA_ROLES:
        counts = _count_triplet(by_role[role], f"{split}.{role}")
        _require_minimums(counts, policy["per_camera_role"], f"{split}.{role}")

    by_cell = _mapping(
        coverage["by_intent_camera_role"],
        f"{split}.by_intent_camera_role",
    )
    _expect_fields(by_cell, set(A3_V3_INTENT_ROLE_CELLS), f"{split} intent-role coverage")
    for cell in A3_V3_INTENT_ROLE_CELLS:
        counts = _count_triplet(by_cell[cell], f"{split}.{cell}")
        _require_minimums(
            counts,
            policy["per_intent_camera_role"],
            f"{split}.{cell}",
        )

    hard = _mapping(
        coverage["hard_confusion_scenarios"],
        f"{split}.hard_confusion_scenarios",
    )
    _expect_fields(hard, set(A3_V3_HARD_CONFUSION_SCENARIOS), f"{split} hard scenarios")
    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        counts = _count_triplet(hard[scenario_id], f"{split}.{scenario_id}")
        minimum_episode_count = int(
            scenario["minimum_unique_episodes_by_split"][split]
        )
        minimum_seed_count = int(scenario["minimum_unique_seeds_by_split"][split])
        if counts["unique_episodes"] < minimum_episode_count:
            raise ValueError(
                f"A3 v3 hard scenario episode coverage below minimum: {split}.{scenario_id}"
            )
        if counts["unique_seeds"] < minimum_seed_count:
            raise ValueError(
                f"A3 v3 hard scenario seed coverage below minimum: {split}.{scenario_id}"
            )
    return {
        "total": total,
        "intent_count": len(by_intent),
        "camera_role_count": len(by_role),
        "intent_role_cell_count": len(by_cell),
        "hard_confusion_scenario_count": len(hard),
    }


def _count_triplet(value: Any, label: str) -> dict[str, int]:
    payload = _mapping(value, label)
    _expect_fields(
        payload,
        {"unique_samples", "unique_episodes", "unique_seeds"},
        label,
    )
    result = {
        name: _non_negative_int(payload[name], f"{label}.{name}")
        for name in ("unique_samples", "unique_episodes", "unique_seeds")
    }
    if result["unique_samples"] < result["unique_episodes"]:
        raise ValueError(f"A3 v3 {label} has fewer samples than episodes")
    return result


def _validate_minimum_triplet(value: Any, label: str, *, samples: bool) -> None:
    payload = _mapping(value, label)
    expected = {"minimum_unique_episodes", "minimum_unique_seeds"}
    if samples:
        expected.add("minimum_unique_samples")
    _expect_fields(payload, expected, label)
    for name, item in payload.items():
        _positive_int(item, f"{label}.{name}")


def _require_minimums(
    counts: Mapping[str, int],
    policy: Mapping[str, int],
    label: str,
) -> None:
    for noun in ("samples", "episodes", "seeds"):
        actual = int(counts[f"unique_{noun}"])
        minimum = int(policy[f"minimum_unique_{noun}"])
        if actual < minimum:
            raise ValueError(
                f"A3 v3 {label} unique {noun} below minimum: {actual} < {minimum}"
            )


def _validate_authority(value: Any, label: str) -> None:
    authority = _mapping(value, label)
    if authority != _EXPECTED_AUTHORITY:
        raise ValueError(f"{label} must keep every authority false")


def authority_false_contract() -> dict[str, bool]:
    return dict(_EXPECTED_AUTHORITY)


def _strict_seed_catalog(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"A3 v3 {label} are unavailable")
    if any(type(item) is not int or item < 0 for item in value):
        raise ValueError(f"A3 v3 {label} are invalid")
    if value != sorted(value) or len(value) != len(set(value)):
        raise ValueError(f"A3 v3 {label} must be sorted and unique")
    return tuple(value)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"A3 v3 {label} must be an object")
    return value


def _expect_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} fields mismatch: missing={missing}, extra={extra}")


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"A3 v3 {label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"A3 v3 {label} must be a non-negative integer")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"A3 v3 {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"A3 v3 {label} must be finite")
    return result


def _bounded_positive(value: Any, label: str, *, maximum: float) -> float:
    result = _finite_number(value, label)
    if not 0.0 < result <= maximum:
        raise ValueError(f"A3 v3 {label} must be in (0, {maximum}]")
    return result


def _unit_interval(value: Any, label: str) -> float:
    result = _finite_number(value, label)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"A3 v3 {label} must be in [0, 1]")
    return result


def _require_sha256(value: Any, label: str) -> str:
    token = str(value)
    if _SHA256_PATTERN.fullmatch(token) is None:
        raise ValueError(f"A3 v3 {label} SHA-256 is invalid")
    return token


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {token}")
            ),
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load A3 v3 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"A3 v3 JSON object expected: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ACTIVE_VISION_A3_V3_DEFAULT_STATUS",
    "ACTIVE_VISION_A3_V3_FUTURE_LEDGER_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_V3_PROTOCOL_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION",
    "A3_V3_CAMERA_ROLES",
    "A3_V3_HARD_CONFUSION_SCENARIOS",
    "A3_V3_INTENTS",
    "A3_V3_INTENT_ROLE_CELLS",
    "A3_V3_SOURCE_SPLITS",
    "FrozenA3V3Protocol",
    "authority_false_contract",
    "load_and_validate_a3_v3_source_manifest",
    "load_frozen_a3_v3_protocol",
    "validate_a3_v3_source_manifest",
    "validate_frozen_a3_v3_protocol",
    "validate_future_heldout_access",
]
