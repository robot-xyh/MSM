#!/usr/bin/env python3
"""Run the pre-registered same-commit D1 publication-metadata A/B matrix."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MATRIX_SCHEMA_VERSION = "scalable3d-d1-publication-metadata-multiseed-matrix-v1"
EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-multiseed-evidence-v1"
)
REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_multiseed_evaluation.v1"
)
V2_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-matrix-v1"
)
V2_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-evidence-v1"
)
V2_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_v2_multiseed_evaluation.v1"
)
CV_MOTION_MODEL_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-cv-motion-model-cache-multiseed-matrix-v1"
)
CV_MOTION_MODEL_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-cv-motion-model-cache-multiseed-evidence-v1"
)
CV_MOTION_MODEL_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_cv_motion_model_cache_multiseed_evaluation.v1"
)
OPAQUE_SOURCE_IDENTITY_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-opaque-source-identity-cache-multiseed-matrix-v1"
)
OPAQUE_SOURCE_IDENTITY_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-opaque-source-identity-cache-multiseed-evidence-v1"
)
OPAQUE_SOURCE_IDENTITY_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1"
)
ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-online-batch-frame-multiseed-matrix-v1"
)
ONLINE_BATCH_FRAME_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-online-batch-frame-multiseed-evidence-v1"
)
ONLINE_BATCH_FRAME_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_online_batch_frame_multiseed_evaluation.v1"
)
ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION = (
    "scalable3d-online-truth-guard-multiseed-matrix-v1"
)
ONLINE_TRUTH_GUARD_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-online-truth-guard-multiseed-evidence-v1"
)
ONLINE_TRUTH_GUARD_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.online_truth_guard_multiseed_evaluation.v1"
)
STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-structured-jacobian-multiseed-matrix-v1"
)
STRUCTURED_JACOBIAN_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-structured-jacobian-multiseed-evidence-v1"
)
STRUCTURED_JACOBIAN_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_structured_jacobian_multiseed_evaluation.v1"
)
ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-association-sparse-prefilter-multiseed-matrix-v1"
)
ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-association-sparse-prefilter-multiseed-evidence-v1"
)
ASSOCIATION_SPARSE_PREFILTER_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_association_sparse_prefilter_multiseed_evaluation.v1"
)
REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-replay-prefix-summary-multiseed-matrix-v1"
)
REPLAY_PREFIX_SUMMARY_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-replay-prefix-summary-multiseed-evidence-v1"
)
REPLAY_PREFIX_SUMMARY_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_replay_prefix_summary_multiseed_evaluation.v1"
)
_ARMS = ("reference", "candidate")
_V1_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_track_copy_v1",
    "candidate": "immutable_shared_v1",
}
_V2_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_track_copy_v1",
    "candidate": "immutable_shared_v2",
}
_CV_MOTION_MODEL_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_prediction_build_v1",
    "candidate": "bounded_exact_lru_v1",
}
_OPAQUE_SOURCE_IDENTITY_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_publication_build_v1",
    "candidate": "bounded_generation_lru_v1",
}
_ONLINE_BATCH_FRAME_EXPECTED_IMPLEMENTATIONS = {
    "reference": "convert_then_frame_v1",
    "candidate": "closed_immutable_batch_to_frame_v1",
}
_ONLINE_TRUTH_GUARD_EXPECTED_IMPLEMENTATIONS = {
    "reference": "generic_recursive_v1",
    "candidate": "builtin_specialized_recursive_v2",
}
_STRUCTURED_JACOBIAN_EXPECTED_IMPLEMENTATIONS = {
    "reference": "dense_output_probe_v1",
    "candidate": "known_dimension_structural_columns_v1",
}
_ASSOCIATION_SPARSE_PREFILTER_EXPECTED_IMPLEMENTATIONS = {
    "reference": "disabled_v1",
    "candidate": "modality_conservative_quadratic_bound_v1",
}
_REPLAY_PREFIX_SUMMARY_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_checkpoint_prefix_rebuild_v1",
    "candidate": "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
}
_D1_IMPLEMENTATION_IDS = {
    "per_track_copy_v1": (
        "d1.publication_metadata.per_track_audit_copy.v1"
    ),
    "immutable_shared_v1": (
        "d1.publication_metadata.immutable_shared_audit.v1"
    ),
    "immutable_shared_v2": (
        "d1.publication_metadata.immutable_shared_audit.v2"
    ),
    "per_prediction_build_v1": (
        "d1.fusion.cv_motion_model.per_prediction_build.v1"
    ),
    "bounded_exact_lru_v1": (
        "d1.fusion.cv_motion_model.bounded_exact_lru.v1"
    ),
    "per_publication_build_v1": (
        "d1.publication.opaque_source_identity.per_publication_build.v1"
    ),
    "bounded_generation_lru_v1": (
        "d1.publication.opaque_source_identity.bounded_generation_lru.v1"
    ),
    "convert_then_frame_v1": (
        "d1.online_batch_frame.convert_then_frame.v1"
    ),
    "closed_immutable_batch_to_frame_v1": (
        "d1.online_batch_frame."
        "closed_immutable_batch_final_frame_validation.v1"
    ),
    "dense_output_probe_v1": (
        "d1.ekf.numerical_jacobian.dense_output_probe.v1"
    ),
    "known_dimension_structural_columns_v1": (
        "d1.ekf.numerical_jacobian."
        "known_dimension_structural_columns.v1"
    ),
    "disabled_v1": (
        "d1.fusion.association_sparse_prefilter.disabled.v1"
    ),
    "modality_conservative_quadratic_bound_v1": (
        "d1.fusion.association_sparse_prefilter."
        "modality_conservative_quadratic_bound.v1"
    ),
    "per_checkpoint_prefix_rebuild_v1": (
        "d1.fusion.replay_prefix.per_checkpoint_rebuild.v1"
    ),
    "fixed_lag_checkpoint_prefix_cumulative_summary_v1": (
        "d1.fusion.replay_prefix."
        "frozen_cumulative_summary_lazy_evidence_ranges.v1"
    ),
}
_MATRIX_SPECS = {
    MATRIX_SCHEMA_VERSION: {
        "expected_implementations": _V1_EXPECTED_IMPLEMENTATIONS,
        "evidence_manifest_schema_version": (
            EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-publication-metadata-implementation",
        "validation_kind": "publication_metadata_v1",
        "treatment_field": "d1_publication_metadata_implementation",
    },
    V2_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": _V2_EXPECTED_IMPLEMENTATIONS,
        "evidence_manifest_schema_version": (
            V2_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            V2_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": (
            "d1.publication_audit_tree.v2"
        ),
        "selector_flag": "--d1-publication-metadata-implementation",
        "validation_kind": "publication_metadata_v2",
        "treatment_field": "d1_publication_metadata_implementation",
    },
    CV_MOTION_MODEL_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _CV_MOTION_MODEL_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            CV_MOTION_MODEL_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            CV_MOTION_MODEL_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-cv-motion-model-implementation",
        "validation_kind": "cv_motion_model_cache",
        "treatment_field": "d1_cv_motion_model_implementation",
    },
    OPAQUE_SOURCE_IDENTITY_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _OPAQUE_SOURCE_IDENTITY_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            OPAQUE_SOURCE_IDENTITY_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            OPAQUE_SOURCE_IDENTITY_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": (
            "--d1-opaque-source-identity-implementation"
        ),
        "validation_kind": "opaque_source_identity_cache",
        "treatment_field": (
            "d1_opaque_source_identity_implementation"
        ),
    },
    ONLINE_BATCH_FRAME_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _ONLINE_BATCH_FRAME_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            ONLINE_BATCH_FRAME_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            ONLINE_BATCH_FRAME_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-online-batch-frame-implementation",
        "validation_kind": "online_batch_frame_handoff",
        "treatment_field": "d1_online_batch_frame_implementation",
    },
    ONLINE_TRUTH_GUARD_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _ONLINE_TRUTH_GUARD_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            ONLINE_TRUTH_GUARD_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            ONLINE_TRUTH_GUARD_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--online-truth-guard-implementation",
        "validation_kind": "online_truth_guard",
        "treatment_field": "online_truth_guard_implementation",
    },
    STRUCTURED_JACOBIAN_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _STRUCTURED_JACOBIAN_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            STRUCTURED_JACOBIAN_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            STRUCTURED_JACOBIAN_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": (
            "--d1-structured-numerical-jacobian-implementation"
        ),
        "validation_kind": "structured_numerical_jacobian",
        "treatment_field": (
            "d1_structured_numerical_jacobian_implementation"
        ),
    },
    ASSOCIATION_SPARSE_PREFILTER_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _ASSOCIATION_SPARSE_PREFILTER_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            ASSOCIATION_SPARSE_PREFILTER_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            ASSOCIATION_SPARSE_PREFILTER_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": (
            "--d1-association-sparse-prefilter-implementation"
        ),
        "validation_kind": "association_sparse_prefilter",
        "treatment_field": (
            "d1_association_sparse_prefilter_implementation"
        ),
    },
    REPLAY_PREFIX_SUMMARY_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _REPLAY_PREFIX_SUMMARY_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            REPLAY_PREFIX_SUMMARY_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            REPLAY_PREFIX_SUMMARY_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-replay-prefix-summary-implementation",
        "validation_kind": "replay_prefix_summary",
        "treatment_field": "d1_replay_prefix_summary_implementation",
    },
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_RUN_FLAGS = {
    "--config",
    "--drone-count",
    "--target-count",
    "--recon-count",
    "--duration",
    "--seed",
    "--output",
    "--d1-publication-metadata-implementation",
    "--d1-cv-motion-model-implementation",
    "--d1-cv-motion-model-cache-capacity",
    "--d1-opaque-source-identity-implementation",
    "--d1-opaque-source-identity-cache-capacity",
    "--d1-online-batch-frame-implementation",
    "--d1-structured-numerical-jacobian-implementation",
    "--d1-association-sparse-prefilter-implementation",
    "--d1-replay-prefix-summary-implementation",
    "--online-truth-guard-implementation",
}


def _matrix_spec(matrix: Mapping[str, Any]) -> Mapping[str, Any]:
    schema_version = matrix.get("schema_version")
    spec = _MATRIX_SPECS.get(schema_version)
    if spec is None:
        raise ValueError("unsupported matrix schema_version")
    return spec


def load_matrix(path: str | Path) -> dict[str, Any]:
    """Load and fail-closed validate the pre-registered evidence matrix."""

    matrix_path = Path(path).expanduser().resolve()
    value = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matrix must be a JSON object")
    spec = _matrix_spec(value)
    _required_text(value.get("experiment_id"), "experiment_id")
    if value.get("same_clean_commit_required") is not True:
        raise ValueError("matrix must require one clean commit for both arms")
    for field in ("target_count", "resource_count", "recon_count"):
        _positive_int(value.get(field), field)
    cooldown_s = _finite_float(value.get("cooldown_s"), "cooldown_s")
    if cooldown_s < 0.0:
        raise ValueError("cooldown_s must be nonnegative")
    _positive_int(value.get("bootstrap_resamples"), "bootstrap_resamples")
    _nonnegative_int(value.get("bootstrap_seed"), "bootstrap_seed")

    implementations = value.get("arm_implementations")
    if implementations != spec["expected_implementations"]:
        expected = spec["expected_implementations"]
        raise ValueError(
            "arm_implementations must bind "
            f"{expected['reference']} and {expected['candidate']}"
        )

    flags = value.get("run_flags")
    if not isinstance(flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in flags
    ):
        raise ValueError("run_flags must be a non-empty string list")
    if any(flag in _FORBIDDEN_RUN_FLAGS for flag in flags):
        raise ValueError("run_flags must not override matrix dimensions or arm")
    if "--integrated-stack" not in flags:
        raise ValueError("run_flags must enable --integrated-stack")

    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    case_ids: set[str] = set()
    group_seed_pairs: set[tuple[str, int]] = set()
    short_seeds: set[int] = set()
    long_seeds: set[int] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("each case must be an object")
        case_id = _required_text(item.get("case_id"), "case_id")
        if case_id in case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        group = _required_text(item.get("group"), "group")
        if group not in {"short", "long"}:
            raise ValueError(f"unsupported group: {group}")
        seed = _nonnegative_int(item.get("seed"), "seed")
        if (group, seed) in group_seed_pairs:
            raise ValueError(f"duplicate group/seed: {group}/{seed}")
        group_seed_pairs.add((group, seed))
        duration_s = _finite_float(item.get("duration_s"), "duration_s")
        if duration_s <= 0.0:
            raise ValueError("duration_s must be positive")
        arm_order = item.get("arm_order")
        if (
            not isinstance(arm_order, list)
            or len(arm_order) != 2
            or set(arm_order) != set(_ARMS)
        ):
            raise ValueError("arm_order must contain reference and candidate")
        (short_seeds if group == "short" else long_seeds).add(seed)
    if not long_seeds.issubset(short_seeds):
        raise ValueError("every long seed must have a matching short case")

    gates = value.get("admission_gates")
    if not isinstance(gates, dict) or not gates:
        raise ValueError("admission_gates must be a non-empty object")
    boundary = value.get("evidence_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("evidence_boundary must be an object")
    if boundary.get("same_source_commit_for_both_arms") is not True:
        raise ValueError("evidence boundary must require the same source commit")
    if (
        boundary.get("only_allowed_runtime_treatment_difference")
        != spec["treatment_field"]
    ):
        raise ValueError(
            "evidence boundary must isolate the registered runtime treatment"
        )
    if (
        boundary.get("reference_implementation")
        != implementations["reference"]
        or boundary.get("candidate_implementation")
        != implementations["candidate"]
    ):
        raise ValueError(
            "evidence boundary implementations must match arm_implementations"
        )
    contract_version = spec["publication_audit_contract_version"]
    if contract_version is not None:
        if (
            boundary.get("candidate_publication_audit_contract_version")
            != contract_version
        ):
            raise ValueError(
                "v2 evidence boundary must bind the publication audit contract"
            )
        if (
            boundary.get(
                "d2_content_audit_required_before_identity_reuse"
            )
            is not True
        ):
            raise ValueError(
                "v2 evidence boundary must require D2 content audit before "
                "identity reuse"
            )
        if (
            gates.get("all_pairs_d2_publication_metadata_audit_valid")
            is not True
        ):
            raise ValueError(
                "v2 admission gates must require valid D2 publication audit"
            )
        for field in (
            "maximum_short_d2_association_mean_increase_pct",
            "maximum_long_d2_association_mean_increase_pct",
        ):
            if _finite_float(gates.get(field), field) < 0.0:
                raise ValueError(f"{field} must be nonnegative")
    if spec["validation_kind"] == "cv_motion_model_cache":
        if boundary.get("cache_key_policy") != "exact_dt_process_noise":
            raise ValueError(
                "CV motion-model evidence must freeze the exact cache key"
            )
        if boundary.get("cache_capacity") != 128:
            raise ValueError(
                "CV motion-model evidence must freeze cache_capacity=128"
            )
        if boundary.get("matrix_values_are_read_only") is not True:
            raise ValueError(
                "CV motion-model evidence must require read-only matrices"
            )
        required_gates = {
            "all_pairs_cv_motion_model_cache_audit_valid": True,
            "minimum_candidate_model_build_reduction_pct": 95.0,
            "minimum_candidate_cache_hit_ratio_pct": 95.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"CV motion-model admission gate {field} must be "
                    f"{expected}"
                )
    if spec["validation_kind"] == "opaque_source_identity_cache":
        if boundary.get("cache_key_policy") != (
            "publisher_node_id_publisher_epoch_track_id"
        ):
            raise ValueError(
                "opaque source-identity evidence must freeze the cache key"
            )
        if boundary.get("cache_capacity") != 1_024:
            raise ValueError(
                "opaque source-identity evidence must freeze "
                "cache_capacity=1024"
            )
        if boundary.get("source_only_publication") is not True:
            raise ValueError(
                "opaque source-identity evidence must use source-only "
                "publication"
            )
        if boundary.get("structural_ambiguity_hold_enabled") is not False:
            raise ValueError(
                "opaque source-identity evidence must keep hold disabled"
            )
        required_gates = {
            "all_pairs_opaque_source_identity_cache_audit_valid": True,
            "short_minimum_d1_fusion_improvement_pct": 5.0,
            "long_minimum_d1_fusion_improvement_pct": 5.0,
            "short_minimum_core_wall_improvement_pct": 2.0,
            "long_minimum_core_wall_improvement_pct": 2.0,
            "minimum_candidate_identity_build_reduction_pct": 95.0,
            "minimum_candidate_cache_hit_ratio_pct": 95.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"opaque source-identity admission gate {field} must be "
                    f"{expected}"
                )
    if spec["validation_kind"] == "online_batch_frame_handoff":
        if boundary.get("diagnostics_schema_version") != (
            "d1.online_batch_frame_handoff_diagnostics.v1"
        ):
            raise ValueError(
                "online batch-frame evidence must bind diagnostics schema v1"
            )
        for field in (
            "full_raw_batch_identity_check_preserved",
            "final_readonly_frame_check_preserved",
            "candidate_default_off",
            "candidate_all_runtime_batches_must_use_closed_handoff",
        ):
            if boundary.get(field) is not True:
                raise ValueError(
                    f"online batch-frame evidence must require {field}"
                )
        if boundary.get("raw_source_absolute_immutability_claimed") is not False:
            raise ValueError(
                "online batch-frame evidence must not claim absolute raw "
                "source immutability"
            )
        required_gates = {
            "all_pairs_online_batch_frame_audit_valid": True,
            "short_minimum_scan_input_improvement_pct": 20.0,
            "long_minimum_scan_input_improvement_pct": 20.0,
            "short_minimum_core_wall_improvement_pct": 2.0,
            "long_minimum_core_wall_improvement_pct": 2.0,
            "minimum_candidate_duplicate_check_reduction_pct": 95.0,
            "minimum_candidate_closed_handoff_ratio_pct": 99.0,
            "maximum_candidate_reference_fallback_count": 0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"online batch-frame admission gate {field} must be "
                    f"{expected}"
                )
    if spec["validation_kind"] == "online_truth_guard":
        if (
            boundary.get("truth_guard_diagnostics_schema_version")
            != "scalable3d-online-truth-guard-diagnostics-v1"
        ):
            raise ValueError(
                "truth-guard evidence must bind diagnostics schema v1"
            )
        required_gates = {
            "all_pairs_truth_guard_audit_valid": True,
            "short_minimum_publication_bus_improvement_pct": 10.0,
            "long_minimum_publication_bus_improvement_pct": 10.0,
            "short_minimum_core_wall_improvement_pct": 0.5,
            "long_minimum_core_wall_improvement_pct": 0.5,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"truth-guard admission gate {field} must be {expected}"
                )
    if spec["validation_kind"] == "structured_numerical_jacobian":
        if (
            boundary.get("structured_jacobian_diagnostics_schema_version")
            != "d1.structured_numerical_jacobian_diagnostics.v1"
        ):
            raise ValueError(
                "structured-Jacobian evidence must bind diagnostics schema v1"
            )
        required_gates = {
            "all_pairs_structured_jacobian_audit_valid": True,
            "short_minimum_d1_fusion_improvement_pct": 2.0,
            "long_minimum_d1_fusion_improvement_pct": 2.0,
            "short_minimum_core_wall_improvement_pct": 0.5,
            "long_minimum_core_wall_improvement_pct": 0.5,
            "minimum_candidate_measurement_evaluation_reduction_pct": 35.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"structured-Jacobian admission gate {field} must be "
                    f"{expected}"
                )
    if spec["validation_kind"] == "association_sparse_prefilter":
        if (
            boundary.get("execution_config_schema_version")
            != "d1.association_sparse_prefilter_execution_config.v1"
        ):
            raise ValueError(
                "association sparse-prefilter evidence must bind execution "
                "config schema v1"
            )
        if (
            boundary.get("diagnostics_schema_version")
            != "d1.association_sparse_prefilter_diagnostics.v2"
        ):
            raise ValueError(
                "association sparse-prefilter evidence must bind diagnostics "
                "schema v2"
            )
        for field in (
            "candidate_default_off",
            "uncertified_pairs_fail_open",
            "exact_residual_semantics_preserved",
            "exact_association_gate_unchanged",
            "truth_dependent_inputs_forbidden",
        ):
            if boundary.get(field) is not True:
                raise ValueError(
                    "association sparse-prefilter evidence must require "
                    f"{field}"
                )
        required_gates = {
            "all_pairs_association_sparse_prefilter_audit_valid": True,
            "all_pairs_exact_gate_pass_counts_equal": True,
            "short_minimum_d1_fusion_improvement_pct": 1.0,
            "long_minimum_d1_fusion_improvement_pct": 1.0,
            "short_minimum_core_wall_improvement_pct": 0.25,
            "long_minimum_core_wall_improvement_pct": 0.25,
            "minimum_candidate_non_radar_exact_solve_reduction_pct": 20.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    "association sparse-prefilter admission gate "
                    f"{field} must be {expected}"
                )
    if spec["validation_kind"] == "replay_prefix_summary":
        if (
            boundary.get("execution_config_schema_version")
            != "d1.fixed_lag_replay_prefix_summary_execution_config.v1"
        ):
            raise ValueError(
                "replay-prefix evidence must bind execution config schema v1"
            )
        if (
            boundary.get("diagnostics_schema_version")
            != "d1.fixed_lag_replay_prefix_summary_diagnostics.v1"
        ):
            raise ValueError(
                "replay-prefix evidence must bind diagnostics schema v1"
            )
        if (
            boundary.get("summary_schema_version")
            != "d1.fixed_lag_replay_prefix_summary.v1"
        ):
            raise ValueError(
                "replay-prefix evidence must bind summary schema v1"
            )
        for field in (
            "candidate_default_off",
            "truth_dependent_inputs_forbidden",
            "complete_trusted_checkpoint_prefix_required",
            "checkpoint_mutations_advance_revision",
            "offline_evidence_materializes_pending_ledger",
        ):
            if boundary.get(field) is not True:
                raise ValueError(
                    f"replay-prefix evidence must require {field}"
                )
        for field in (
            "fixed_lag_window_changed",
            "checkpoint_audit_semantics_changed",
            "consistency_evidence_semantics_changed",
        ):
            if boundary.get(field) is not False:
                raise ValueError(
                    f"replay-prefix evidence must freeze {field}=false"
                )
        required_gates = {
            "all_pairs_replay_prefix_summary_audit_valid": True,
            "all_pairs_consistency_evidence_records_digest_equal": True,
            "all_pairs_existing_operation_counts_equal": True,
            "short_minimum_d1_fusion_improvement_pct": 1.0,
            "long_minimum_d1_fusion_improvement_pct": 1.0,
            "short_minimum_core_wall_improvement_pct": 0.25,
            "long_minimum_core_wall_improvement_pct": 0.25,
            "minimum_candidate_lazy_materialization_reduction_pct": 20.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"replay-prefix admission gate {field} must be {expected}"
                )
    return value


def build_episode_command(
    worktree: str | Path,
    matrix: Mapping[str, Any],
    case: Mapping[str, Any],
    arm: str,
    output_dir: str | Path,
) -> list[str]:
    """Build one arm command with an explicit registered implementation."""

    if arm not in _ARMS:
        raise ValueError(f"unsupported arm: {arm}")
    worktree_path = Path(worktree).expanduser().resolve()
    entrypoint = (
        worktree_path
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_episode.py"
    )
    if not entrypoint.is_file():
        raise ValueError(f"run_episode.py unavailable: {entrypoint}")
    command = [
        "python3",
        str(entrypoint),
        *[str(flag) for flag in matrix["run_flags"]],
        str(_matrix_spec(matrix)["selector_flag"]),
        str(matrix["arm_implementations"][arm]),
    ]
    validation_kind = str(_matrix_spec(matrix)["validation_kind"])
    if validation_kind == "cv_motion_model_cache":
        command.extend(
            (
                "--d1-cv-motion-model-cache-capacity",
                str(int(matrix["evidence_boundary"]["cache_capacity"])),
            )
        )
    elif validation_kind == "opaque_source_identity_cache":
        command.extend(
            (
                "--d1-opaque-source-identity-cache-capacity",
                str(int(matrix["evidence_boundary"]["cache_capacity"])),
            )
        )
    command.extend(
        (
        "--duration",
        _format_float(float(case["duration_s"])),
        "--seed",
        str(int(case["seed"])),
        "--drone-count",
        str(int(matrix["resource_count"])),
        "--target-count",
        str(int(matrix["target_count"])),
        "--recon-count",
        str(int(matrix["recon_count"])),
        "--output",
        str(Path(output_dir).expanduser().resolve()),
        )
    )
    return command


def planned_evidence_manifest(
    matrix_path: str | Path,
    matrix: Mapping[str, Any],
    source_worktree: str | Path,
    source_commit: str,
    output_root: str | Path,
) -> dict[str, Any]:
    """Bind cases, arms, implementation identities and paths for D6."""

    if _COMMIT_RE.fullmatch(str(source_commit)) is None:
        raise ValueError("source_commit must be a full lowercase Git commit")
    root = Path(output_root).expanduser().resolve()
    worktree = Path(source_worktree).expanduser().resolve()
    spec = _matrix_spec(matrix)
    cases: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        case_root = root / str(case["case_id"])
        arms: dict[str, Any] = {}
        for arm in _ARMS:
            episode_dir = case_root / f"{arm}_episode"
            arm_record = {
                "arm": arm,
                "expected_implementation": matrix["arm_implementations"][arm],
                "validation_kind": spec["validation_kind"],
                "expected_commit": source_commit,
                "episode_dir": str(episode_dir),
                "resource_path": str(case_root / f"{arm}_resource_usage.txt"),
                "stdout_path": str(case_root / f"{arm}_stdout.log"),
                "stderr_path": str(case_root / f"{arm}_stderr.log"),
                "command": build_episode_command(
                    worktree,
                    matrix,
                    case,
                    arm,
                    episode_dir,
                ),
                "status": "pending",
                "return_code": None,
            }
            if spec["validation_kind"] == "online_truth_guard":
                arm_record["expected_truth_guard_implementation"] = (
                    matrix["arm_implementations"][arm]
                )
            else:
                arm_record["expected_d1_implementation_id"] = (
                    _D1_IMPLEMENTATION_IDS[
                        matrix["arm_implementations"][arm]
                    ]
                )
            arms[arm] = arm_record
        cases.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "seed": case["seed"],
                "duration_s": case["duration_s"],
                "arm_order": list(case["arm_order"]),
                "arms": arms,
                "d6_evaluation_status": "pending",
            }
        )
    manifest = {
        "schema_version": spec["evidence_manifest_schema_version"],
        "experiment_id": matrix["experiment_id"],
        "matrix_path": str(Path(matrix_path).expanduser().resolve()),
        "matrix_sha256": _file_sha256(
            Path(matrix_path).expanduser().resolve()
        ),
        "matrix": matrix,
        "source_worktree": str(worktree),
        "source_commit": source_commit,
        "source_repository_dirty": False,
        "output_root": str(root),
        "required_d6_evaluator_schema_version": (
            spec["required_d6_evaluator_schema_version"]
        ),
        "status": "planned",
        "started_at_utc": None,
        "completed_at_utc": None,
        "cases": cases,
    }
    contract_version = spec["publication_audit_contract_version"]
    if contract_version is not None:
        manifest["publication_audit_contract_version"] = contract_version
    if spec["validation_kind"] == "cv_motion_model_cache":
        manifest["cv_motion_model_cache_capacity"] = int(
            matrix["evidence_boundary"]["cache_capacity"]
        )
        manifest["cv_motion_model_cache_diagnostics_schema_version"] = (
            "d1.cv_motion_model_cache_diagnostics.v1"
        )
    if spec["validation_kind"] == "opaque_source_identity_cache":
        manifest["opaque_source_identity_cache_capacity"] = int(
            matrix["evidence_boundary"]["cache_capacity"]
        )
        manifest[
            "opaque_source_identity_cache_diagnostics_schema_version"
        ] = "d1.opaque_source_identity_cache_diagnostics.v1"
    if spec["validation_kind"] == "online_batch_frame_handoff":
        manifest["online_batch_frame_diagnostics_schema_version"] = (
            "d1.online_batch_frame_handoff_diagnostics.v1"
        )
    if spec["validation_kind"] == "online_truth_guard":
        manifest["truth_guard_diagnostics_schema_version"] = (
            "scalable3d-online-truth-guard-diagnostics-v1"
        )
    if spec["validation_kind"] == "structured_numerical_jacobian":
        manifest["structured_jacobian_diagnostics_schema_version"] = (
            "d1.structured_numerical_jacobian_diagnostics.v1"
        )
    if spec["validation_kind"] == "association_sparse_prefilter":
        manifest[
            "association_sparse_prefilter_execution_config_schema_version"
        ] = "d1.association_sparse_prefilter_execution_config.v1"
        manifest[
            "association_sparse_prefilter_diagnostics_schema_version"
        ] = "d1.association_sparse_prefilter_diagnostics.v2"
    if spec["validation_kind"] == "replay_prefix_summary":
        manifest[
            "replay_prefix_summary_execution_config_schema_version"
        ] = "d1.fixed_lag_replay_prefix_summary_execution_config.v1"
        manifest[
            "replay_prefix_summary_diagnostics_schema_version"
        ] = "d1.fixed_lag_replay_prefix_summary_diagnostics.v1"
        manifest[
            "replay_prefix_summary_schema_version"
        ] = "d1.fixed_lag_replay_prefix_summary.v1"
    return manifest


def run_matrix(
    matrix_path: str | Path,
    source_worktree: str | Path,
    output_root: str | Path,
    *,
    resume: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Run all episode arms; semantic and admission decisions remain D6-owned."""

    matrix = load_matrix(matrix_path)
    spec = _matrix_spec(matrix)
    expected_cache_capacity = (
        int(matrix["evidence_boundary"]["cache_capacity"])
        if spec["validation_kind"] in {
            "cv_motion_model_cache",
            "opaque_source_identity_cache",
        }
        else None
    )
    worktree = Path(source_worktree).expanduser().resolve()
    source_commit = _validate_source_worktree(worktree)
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "evidence_manifest.json"
    planned = planned_evidence_manifest(
        matrix_path,
        matrix,
        worktree,
        source_commit,
        root,
    )
    manifest = planned
    if resume and manifest_path.is_file():
        existing = _read_mapping(manifest_path)
        _validate_resume_manifest(existing, planned)
        manifest = existing
    manifest["status"] = "dry_run" if dry_run else "running"
    manifest["started_at_utc"] = (
        manifest.get("started_at_utc") or _utc_now()
    )
    _write_json_atomic(manifest_path, manifest)

    for case in manifest["cases"]:
        for arm in case["arm_order"]:
            record = case["arms"][arm]
            if resume and _episode_matches(
                Path(record["episode_dir"]),
                expected_commit=source_commit,
                expected_implementation=str(record["expected_implementation"]),
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                target_count=int(matrix["target_count"]),
                resource_count=int(matrix["resource_count"]),
                recon_count=int(matrix["recon_count"]),
                require_v2_audit=(
                    matrix.get("schema_version") == V2_MATRIX_SCHEMA_VERSION
                ),
                validation_kind=str(spec["validation_kind"]),
                expected_cache_capacity=expected_cache_capacity,
            ):
                record["status"] = "reused"
                record["return_code"] = 0
                _write_json_atomic(manifest_path, manifest)
                continue
            if dry_run:
                record["status"] = "planned"
                continue
            record["status"] = "running"
            record["started_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            try:
                _run_arm(record, worktree)
                if not _episode_matches(
                    Path(record["episode_dir"]),
                    expected_commit=source_commit,
                    expected_implementation=str(
                        record["expected_implementation"]
                    ),
                    seed=int(case["seed"]),
                    duration_s=float(case["duration_s"]),
                    target_count=int(matrix["target_count"]),
                    resource_count=int(matrix["resource_count"]),
                    recon_count=int(matrix["recon_count"]),
                    require_v2_audit=(
                        matrix.get("schema_version")
                        == V2_MATRIX_SCHEMA_VERSION
                    ),
                    validation_kind=str(spec["validation_kind"]),
                    expected_cache_capacity=expected_cache_capacity,
                ):
                    raise RuntimeError(
                        "completed episode failed implementation or provenance "
                        "validation"
                    )
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                manifest["status"] = "interrupted"
                manifest["failure"] = {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "error_type": "KeyboardInterrupt",
                    "error": "matrix execution interrupted by operator",
                }
                raise
            except Exception as exc:
                manifest["status"] = "failed"
                manifest["failure"] = {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                raise
            finally:
                _write_json_atomic(manifest_path, manifest)
            if float(matrix["cooldown_s"]) > 0.0:
                time.sleep(float(matrix["cooldown_s"]))
        if not dry_run:
            case["d6_evaluation_status"] = "episodes_complete_pending_d6"
            _write_json_atomic(manifest_path, manifest)

    manifest["status"] = (
        "dry_run" if dry_run else "episodes_complete_pending_d6"
    )
    manifest["completed_at_utc"] = _utc_now()
    _write_json_atomic(manifest_path, manifest)
    return manifest


def _run_arm(record: dict[str, Any], worktree: Path) -> None:
    episode_dir = Path(record["episode_dir"])
    if episode_dir.exists():
        raise FileExistsError(
            f"episode output already exists; use --resume: {episode_dir}"
        )
    episode_dir.parent.mkdir(parents=True, exist_ok=True)
    command = [str(item) for item in record["command"]]
    timed_command = [
        "/usr/bin/time",
        "--verbose",
        "--output",
        str(record["resource_path"]),
        *command,
    ]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    with Path(record["stdout_path"]).open(
        "w", encoding="utf-8"
    ) as stdout, Path(record["stderr_path"]).open(
        "w", encoding="utf-8"
    ) as stderr:
        completed = subprocess.run(
            timed_command,
            cwd=worktree,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    record["return_code"] = int(completed.returncode)
    record["completed_at_utc"] = _utc_now()
    record["status"] = (
        "complete" if completed.returncode == 0 else "failed"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"episode command failed with {completed.returncode}: "
            f"{' '.join(command)}"
        )


def _validate_source_worktree(worktree: Path) -> str:
    if not worktree.is_dir():
        raise ValueError(f"source worktree unavailable: {worktree}")
    entrypoint = (
        worktree
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_episode.py"
    )
    if not entrypoint.is_file():
        raise ValueError(f"run_episode.py unavailable: {entrypoint}")
    commit = _git_output(worktree, "rev-parse", "HEAD")
    if _COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("source worktree HEAD is not a full Git commit")
    if _git_output(worktree, "status", "--porcelain"):
        raise ValueError("source worktree must be clean for formal evidence")
    return commit


def _validate_resume_manifest(
    existing: Mapping[str, Any],
    planned: Mapping[str, Any],
) -> None:
    for field in (
        "schema_version",
        "experiment_id",
        "matrix_sha256",
        "matrix",
        "source_commit",
        "source_worktree",
        "output_root",
        "required_d6_evaluator_schema_version",
    ):
        if existing.get(field) != planned.get(field):
            raise ValueError(f"resume manifest mismatch: {field}")
    existing_cases = [
        (
            item.get("case_id"),
            item.get("group"),
            item.get("seed"),
            item.get("duration_s"),
            item.get("arm_order"),
        )
        for item in existing.get("cases", [])
        if isinstance(item, Mapping)
    ]
    planned_cases = [
        (
            item.get("case_id"),
            item.get("group"),
            item.get("seed"),
            item.get("duration_s"),
            item.get("arm_order"),
        )
        for item in planned["cases"]
    ]
    if existing_cases != planned_cases:
        raise ValueError("resume manifest case matrix mismatch")


def _episode_matches(
    episode_dir: Path,
    *,
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
    require_v2_audit: bool = False,
    validation_kind: str = "publication_metadata_v1",
    expected_cache_capacity: int | None = None,
) -> bool:
    try:
        manifest = _read_mapping(episode_dir / "manifest.json")
        config = _read_mapping(episode_dir / "scenario_config.json")
        summary = _read_mapping(episode_dir / "summary.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if validation_kind == "cv_motion_model_cache":
        return _cv_motion_model_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            expected_cache_capacity=expected_cache_capacity,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "opaque_source_identity_cache":
        return _opaque_source_identity_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            expected_cache_capacity=expected_cache_capacity,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "online_batch_frame_handoff":
        return _online_batch_frame_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "online_truth_guard":
        return _online_truth_guard_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "structured_numerical_jacobian":
        return _structured_numerical_jacobian_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "association_sparse_prefilter":
        return _association_sparse_prefilter_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind == "replay_prefix_summary":
        return _replay_prefix_summary_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind not in {
        "publication_metadata_v1",
        "publication_metadata_v2",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    diagnostics = summary.get("d1_publication_metadata_diagnostics")
    expected_d1_implementation_id = _D1_IMPLEMENTATION_IDS.get(
        expected_implementation
    )
    if expected_d1_implementation_id is None:
        return False
    expected_candidate = expected_implementation in {
        "immutable_shared_v1",
        "immutable_shared_v2",
    }
    operation_counts = (
        diagnostics.get("operation_counts")
        if isinstance(diagnostics, Mapping)
        else None
    )
    implementation_operations_match = (
        isinstance(operation_counts, Mapping)
        and int(
            operation_counts.get(
                "global_track_metadata_materialization_count",
                0,
            )
        )
        > 0
    )
    if expected_candidate:
        implementation_operations_match = (
            implementation_operations_match
            and int(
                operation_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            == 0
            and int(
                operation_counts.get("shared_audit_value_reuse_count", 0)
            )
            > 0
        )
    else:
        implementation_operations_match = (
            implementation_operations_match
            and int(
                operation_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            > 0
            and int(
                operation_counts.get("shared_audit_value_reuse_count", 0)
            )
            == 0
        )
    contract_match = True
    if expected_implementation == "immutable_shared_v2":
        contract_match = (
            diagnostics.get("publication_audit_contract_version")
            == "d1.publication_audit_tree.v2"
            and _v2_d2_audit_matches(summary, candidate=True)
        )
    elif (
        expected_implementation == "per_track_copy_v1"
        and require_v2_audit
    ):
        contract_match = (
            diagnostics.get("publication_audit_contract_version") is None
            and _v2_d2_audit_matches(summary, candidate=False)
        )
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and isinstance(runtime_profile, Mapping)
        and runtime_profile.get("d1_publication_metadata_implementation")
        == expected_implementation
        and isinstance(diagnostics, Mapping)
        and diagnostics.get("implementation_id")
        == expected_d1_implementation_id
        and diagnostics.get("immutable_shared_publication_metadata")
        is expected_candidate
        and implementation_operations_match
        and contract_match
        and summary.get("d1_publication_metadata_implementation")
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _cv_motion_model_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    expected_cache_capacity: int | None,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    if expected_cache_capacity is None:
        return False
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = expected_implementation == "bounded_exact_lru_v1"
    if expected_implementation not in {
        "per_prediction_build_v1",
        "bounded_exact_lru_v1",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get("d1_cv_motion_model_cache_diagnostics")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    diagnostics = summary.get("d1_cv_motion_model_cache_diagnostics")
    final = summary.get("module_final_diagnostics")
    final_diagnostics = (
        final.get("d1_cv_motion_model_cache_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_diagnostics = governance.get(
        "d1_cv_motion_model_cache_diagnostics"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_diagnostics,
            diagnostics,
            final,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    if (
        initial_diagnostics.get("schema_version")
        != "d1.cv_motion_model_cache_diagnostics.v1"
        or initial_diagnostics.get("implementation_id") != expected_id
        or initial_diagnostics.get("candidate_enabled") is not candidate
        or initial_diagnostics.get("cache_capacity")
        != expected_cache_capacity
        or initial_diagnostics.get("cache_entry_count") != 0
        or initial_diagnostics.get("operation_counts") != {}
    ):
        return False
    if (
        diagnostics != final_diagnostics
        or diagnostics != governance_diagnostics
        or diagnostics.get("schema_version")
        != "d1.cv_motion_model_cache_diagnostics.v1"
        or diagnostics.get("implementation_id") != expected_id
        or diagnostics.get("candidate_enabled") is not candidate
        or diagnostics.get("cache_capacity") != expected_cache_capacity
    ):
        return False
    if not _cv_motion_model_operation_counts_match(
        diagnostics,
        candidate=candidate,
        expected_cache_capacity=expected_cache_capacity,
    ):
        return False
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and runtime_configuration.get(
            "d1_cv_motion_model_implementation"
        )
        == expected_implementation
        and runtime_configuration.get(
            "d1_cv_motion_model_cache_capacity"
        )
        == expected_cache_capacity
        and summary.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and final.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and governance.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _cv_motion_model_operation_counts_match(
    diagnostics: Mapping[str, Any],
    *,
    candidate: bool,
    expected_cache_capacity: int,
) -> bool:
    operations = diagnostics.get("operation_counts")
    if not isinstance(operations, Mapping):
        return False
    names = (
        "prediction_request_count",
        "model_build_count",
        "nonpositive_dt_reference_bypass_count",
        "nonfinite_reference_bypass_count",
        "cache_hit_count",
        "cache_miss_count",
        "cache_eviction_count",
        "peak_entry_count",
    )
    counts: dict[str, int] = {}
    for name in names:
        value = operations.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        counts[name] = int(value)
    entry_count = diagnostics.get("cache_entry_count")
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 0
        or entry_count > expected_cache_capacity
        or counts["peak_entry_count"] > expected_cache_capacity
    ):
        return False
    requests = counts["prediction_request_count"]
    nonpositive = counts["nonpositive_dt_reference_bypass_count"]
    nonfinite = counts["nonfinite_reference_bypass_count"]
    if requests <= 0:
        return False
    if candidate:
        return (
            counts["cache_hit_count"] > 0
            and counts["cache_miss_count"] > 0
            and counts["model_build_count"]
            == counts["cache_miss_count"] + nonfinite
            and requests
            == (
                nonpositive
                + nonfinite
                + counts["cache_hit_count"]
                + counts["cache_miss_count"]
            )
        )
    return (
        entry_count == 0
        and counts["cache_hit_count"] == 0
        and counts["cache_miss_count"] == 0
        and counts["cache_eviction_count"] == 0
        and counts["peak_entry_count"] == 0
        and requests == nonpositive + counts["model_build_count"]
    )


def _opaque_source_identity_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    expected_cache_capacity: int | None,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    if expected_cache_capacity is None:
        return False
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = expected_implementation == "bounded_generation_lru_v1"
    if expected_implementation not in {
        "per_publication_build_v1",
        "bounded_generation_lru_v1",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get(
            "d1_opaque_source_identity_cache_diagnostics"
        )
        if isinstance(runtime_profile, Mapping)
        else None
    )
    diagnostics = summary.get(
        "d1_opaque_source_identity_cache_diagnostics"
    )
    final = summary.get("module_final_diagnostics")
    final_diagnostics = (
        final.get("d1_opaque_source_identity_cache_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_diagnostics = governance.get(
        "d1_opaque_source_identity_cache_diagnostics"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_diagnostics,
            diagnostics,
            final,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    expected_schema = "d1.opaque_source_identity_cache_diagnostics.v1"
    if (
        initial_diagnostics.get("schema_version") != expected_schema
        or initial_diagnostics.get("implementation_id") != expected_id
        or initial_diagnostics.get("candidate_enabled") is not candidate
        or initial_diagnostics.get("cache_capacity")
        != expected_cache_capacity
        or initial_diagnostics.get("cache_entry_count") != 0
        or initial_diagnostics.get("operation_counts") != {}
        or not _all_true(initial_diagnostics.get("conservation"))
    ):
        return False
    if (
        diagnostics != final_diagnostics
        or diagnostics != governance_diagnostics
        or diagnostics.get("schema_version") != expected_schema
        or diagnostics.get("implementation_id") != expected_id
        or diagnostics.get("candidate_enabled") is not candidate
        or diagnostics.get("cache_capacity") != expected_cache_capacity
        or not _all_true(diagnostics.get("conservation"))
    ):
        return False
    if not _opaque_source_identity_operation_counts_match(
        diagnostics,
        candidate=candidate,
        expected_cache_capacity=expected_cache_capacity,
    ):
        return False
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get(
            "d1_opaque_source_identity_implementation"
        )
        == expected_implementation
        and runtime_configuration.get(
            "d1_opaque_source_identity_implementation"
        )
        == expected_implementation
        and runtime_configuration.get(
            "d1_opaque_source_identity_cache_capacity"
        )
        == expected_cache_capacity
        and runtime_configuration.get("d1_publish_opaque_source_key") is True
        and runtime_configuration.get(
            "d1_d2_structural_ambiguity_hold_enabled"
        )
        is False
        and summary.get(
            "d1_opaque_source_identity_implementation"
        )
        == expected_implementation
        and final.get("d1_opaque_source_identity_implementation")
        == expected_implementation
        and governance.get(
            "d1_opaque_source_identity_implementation"
        )
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _opaque_source_identity_operation_counts_match(
    diagnostics: Mapping[str, Any],
    *,
    candidate: bool,
    expected_cache_capacity: int,
) -> bool:
    operations = diagnostics.get("operation_counts")
    if not isinstance(operations, Mapping):
        return False
    names = (
        "request_count",
        "cache_hit_count",
        "cache_miss_count",
        "identity_build_count",
        "cache_eviction_count",
        "reference_bypass_count",
        "peak_entry_count",
        "generation_invalidation_count",
        "generation_invalidated_entry_count",
        "explicit_reset_count",
        "explicit_reset_entry_count",
    )
    counts: dict[str, int] = {}
    for name in names:
        value = operations.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        counts[name] = int(value)
    entry_count = diagnostics.get("cache_entry_count")
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 0
        or entry_count > expected_cache_capacity
        or counts["peak_entry_count"] > expected_cache_capacity
        or counts["request_count"] <= 0
        or counts["request_count"]
        != (
            counts["cache_hit_count"]
            + counts["cache_miss_count"]
            + counts["reference_bypass_count"]
        )
        or counts["identity_build_count"]
        != counts["cache_miss_count"] + counts["reference_bypass_count"]
        or counts["cache_eviction_count"] > counts["cache_miss_count"]
    ):
        return False
    if candidate:
        return (
            counts["cache_hit_count"] > 0
            and counts["cache_miss_count"] > 0
            and counts["reference_bypass_count"] == 0
            and entry_count > 0
        )
    return (
        entry_count == 0
        and counts["cache_hit_count"] == 0
        and counts["cache_miss_count"] == 0
        and counts["cache_eviction_count"] == 0
        and counts["peak_entry_count"] == 0
        and counts["reference_bypass_count"] == counts["request_count"]
    )


def _online_batch_frame_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = (
        expected_implementation
        == "closed_immutable_batch_to_frame_v1"
    )
    if expected_implementation not in {
        "convert_then_frame_v1",
        "closed_immutable_batch_to_frame_v1",
    }:
        return False
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_execution_config = (
        runtime_profile.get("d1_online_batch_frame_execution_config")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    final = summary.get("module_final_diagnostics")
    if not all(
        isinstance(item, Mapping)
        for item in (
            runtime_profile,
            runtime_configuration,
            initial_execution_config,
            final,
        )
    ):
        return False
    summary_execution_config = summary.get(
        "d1_online_batch_frame_execution_config"
    )
    final_execution_config = final.get(
        "d1_online_batch_frame_execution_config"
    )
    governance_execution_config = governance.get(
        "d1_online_batch_frame_execution_config"
    )
    diagnostics = summary.get("d1_online_batch_frame_diagnostics")
    final_diagnostics = final.get("d1_online_batch_frame_diagnostics")
    governance_diagnostics = governance.get(
        "d1_online_batch_frame_diagnostics"
    )
    if not all(
        isinstance(item, Mapping)
        for item in (
            summary_execution_config,
            final_execution_config,
            governance_execution_config,
            diagnostics,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    if not all(
        _online_batch_frame_execution_config_matches(
            item,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
        )
        for item in (
            initial_execution_config,
            summary_execution_config,
            final_execution_config,
            governance_execution_config,
        )
    ):
        return False
    if not all(
        _online_batch_frame_diagnostics_match(
            item,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
        )
        for item in (
            diagnostics,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    if not (
        dict(diagnostics) == dict(final_diagnostics)
        == dict(governance_diagnostics)
        and dict(summary_execution_config)
        == dict(final_execution_config)
        == dict(governance_execution_config)
    ):
        return False
    return bool(
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get(
            "d1_online_batch_frame_implementation"
        )
        == expected_implementation
        and runtime_configuration.get(
            "d1_online_batch_frame_implementation"
        )
        == expected_implementation
        and summary.get("d1_online_batch_frame_implementation")
        == expected_implementation
        and final.get("d1_online_batch_frame_implementation")
        == expected_implementation
        and governance.get("d1_online_batch_frame_implementation")
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _online_batch_frame_execution_config_matches(
    execution_config: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
) -> bool:
    return bool(
        execution_config.get("schema_version")
        == "d1.online_batch_frame_handoff_diagnostics.v1"
        and execution_config.get("implementation")
        == expected_implementation
        and execution_config.get("implementation_id")
        == expected_implementation_id
        and execution_config.get("candidate_default_enabled") is False
        and execution_config.get("public_validation_bypass_available") is False
        and execution_config.get(
            "raw_source_absolute_immutability_claimed"
        )
        is False
        and execution_config.get("candidate_contract")
        == (
            "full_raw_batch_identity_check_then_structural_eligibility_"
            "check_then_deep_snapshot_then_full_readonly_frame_check"
        )
    )


def _online_batch_frame_diagnostics_match(
    diagnostics: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
    candidate: bool,
) -> bool:
    if not _online_batch_frame_execution_config_matches(
        diagnostics,
        expected_implementation=expected_implementation,
        expected_implementation_id=expected_implementation_id,
    ):
        return False
    operations = diagnostics.get("operation_counts")
    conservation = diagnostics.get("conservation")
    if not isinstance(operations, Mapping) or not isinstance(
        conservation,
        Mapping,
    ):
        return False
    operation_names = (
        "request_count",
        "successful_build_count",
        "rejected_build_count",
        "reference_request_count",
        "candidate_request_count",
        "reference_path_execution_count",
        "candidate_closed_handoff_count",
        "candidate_reference_fallback_count",
        "candidate_raw_rejection_count",
        "candidate_resource_rejection_count",
        "snapshot_structure_check_count",
        "snapshot_structure_eligible_count",
        "snapshot_structure_ineligible_count",
        "snapshot_structure_error_count",
        "closed_payload_snapshot_attempt_count",
        "closed_payload_snapshot_success_count",
        "closed_payload_snapshot_failure_count",
        "raw_batch_identity_check_count",
        "raw_measurement_identity_check_count",
        "converted_observation_collection_check_count",
        "frame_final_identity_check_count",
        "measurement_conversion_count",
        "output_observation_count",
    )
    counts: dict[str, int] = {}
    for name in operation_names:
        value = operations.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        counts[name] = int(value)
    conservation_names = (
        "request_partition",
        "result_partition",
        "reference_path_partition",
        "candidate_path_partition",
        "snapshot_structure_check_partition",
        "closed_payload_snapshot_partition",
        "closed_handoff_uses_successful_snapshot",
        "raw_batch_check_accounting",
        "candidate_never_skips_final_frame_check",
    )
    if any(conservation.get(name) is not True for name in conservation_names):
        return False
    request_count = counts["request_count"]
    common_match = bool(
        request_count > 0
        and counts["successful_build_count"] == request_count
        and counts["rejected_build_count"] == 0
        and counts["raw_batch_identity_check_count"] == request_count
        and counts["frame_final_identity_check_count"] == request_count
        and counts["measurement_conversion_count"]
        == counts["output_observation_count"]
        and counts["output_observation_count"] > 0
    )
    if not common_match:
        return False
    if candidate:
        return bool(
            counts["candidate_request_count"] == request_count
            and counts["reference_request_count"] == 0
            and counts["reference_path_execution_count"] == 0
            and counts["candidate_closed_handoff_count"] == request_count
            and counts["candidate_reference_fallback_count"] == 0
            and counts["candidate_raw_rejection_count"] == 0
            and counts["candidate_resource_rejection_count"] == 0
            and counts["snapshot_structure_check_count"] == request_count
            and counts["snapshot_structure_eligible_count"] == request_count
            and counts["snapshot_structure_ineligible_count"] == 0
            and counts["snapshot_structure_error_count"] == 0
            and counts["closed_payload_snapshot_attempt_count"]
            == request_count
            and counts["closed_payload_snapshot_success_count"]
            == request_count
            and counts["closed_payload_snapshot_failure_count"] == 0
            and counts["raw_measurement_identity_check_count"] == 0
            and counts["converted_observation_collection_check_count"] == 0
        )
    return bool(
        counts["reference_request_count"] == request_count
        and counts["candidate_request_count"] == 0
        and counts["reference_path_execution_count"] == request_count
        and counts["candidate_closed_handoff_count"] == 0
        and counts["candidate_reference_fallback_count"] == 0
        and counts["candidate_raw_rejection_count"] == 0
        and counts["candidate_resource_rejection_count"] == 0
        and counts["snapshot_structure_check_count"] == 0
        and counts["snapshot_structure_eligible_count"] == 0
        and counts["snapshot_structure_ineligible_count"] == 0
        and counts["snapshot_structure_error_count"] == 0
        and counts["closed_payload_snapshot_attempt_count"] == 0
        and counts["closed_payload_snapshot_success_count"] == 0
        and counts["closed_payload_snapshot_failure_count"] == 0
        and counts["raw_measurement_identity_check_count"]
        == counts["output_observation_count"]
        and counts["converted_observation_collection_check_count"]
        == request_count
    )


def _structured_numerical_jacobian_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = (
        expected_implementation
        == "known_dimension_structural_columns_v1"
    )
    if expected_implementation not in {
        "dense_output_probe_v1",
        "known_dimension_structural_columns_v1",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get(
            "d1_structured_numerical_jacobian_diagnostics"
        )
        if isinstance(runtime_profile, Mapping)
        else None
    )
    diagnostics = summary.get(
        "d1_structured_numerical_jacobian_diagnostics"
    )
    final = summary.get("module_final_diagnostics")
    final_diagnostics = (
        final.get("d1_structured_numerical_jacobian_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_diagnostics = governance.get(
        "d1_structured_numerical_jacobian_diagnostics"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_diagnostics,
            diagnostics,
            final,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    expected_schema = "d1.structured_numerical_jacobian_diagnostics.v1"
    if (
        initial_diagnostics.get("schema_version") != expected_schema
        or initial_diagnostics.get("implementation_id") != expected_id
        or initial_diagnostics.get("candidate_enabled") is not candidate
        or initial_diagnostics.get("operation_counts") != {}
        or initial_diagnostics.get("conservation")
        != {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        }
    ):
        return False
    if (
        diagnostics != final_diagnostics
        or diagnostics != governance_diagnostics
        or diagnostics.get("schema_version") != expected_schema
        or diagnostics.get("implementation_id") != expected_id
        or diagnostics.get("candidate_enabled") is not candidate
        or diagnostics.get("conservation")
        != {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        }
        or not _structured_jacobian_operation_counts_match(
            diagnostics,
            candidate=candidate,
        )
    ):
        return False
    selector_field = (
        "d1_structured_numerical_jacobian_implementation"
    )
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get(selector_field) == expected_implementation
        and runtime_configuration.get(selector_field)
        == expected_implementation
        and summary.get(selector_field) == expected_implementation
        and final.get(selector_field) == expected_implementation
        and governance.get(selector_field) == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _structured_jacobian_operation_counts_match(
    diagnostics: Mapping[str, Any],
    *,
    candidate: bool,
) -> bool:
    operations = diagnostics.get("operation_counts")
    if not isinstance(operations, Mapping):
        return False
    names = (
        "jacobian_attempt_count",
        "jacobian_success_count",
        "jacobian_failure_count",
        "reference_call_count",
        "structured_candidate_call_count",
        "output_probe_evaluation_count",
        "output_probe_elision_count",
        "inactive_state_column_elision_count",
        "measurement_function_evaluation_count",
    )
    counts: dict[str, int] = {}
    for name in names:
        value = operations.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        counts[name] = int(value)
    attempts = counts["jacobian_attempt_count"]
    if (
        attempts <= 0
        or counts["jacobian_success_count"] != attempts
        or counts["jacobian_failure_count"] != 0
        or counts["measurement_function_evaluation_count"] <= 0
    ):
        return False
    if candidate:
        return (
            counts["reference_call_count"] == 0
            and counts["structured_candidate_call_count"] == attempts
            and counts["output_probe_evaluation_count"] == 0
            and counts["output_probe_elision_count"] == attempts
            and counts["inactive_state_column_elision_count"] > 0
            and counts["measurement_function_evaluation_count"]
            < 13 * attempts
        )
    return (
        counts["reference_call_count"] == attempts
        and counts["structured_candidate_call_count"] == 0
        and counts["output_probe_evaluation_count"] == attempts
        and counts["output_probe_elision_count"] == 0
        and counts["inactive_state_column_elision_count"] == 0
        and counts["measurement_function_evaluation_count"]
        == 13 * attempts
    )


def _association_sparse_prefilter_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = (
        expected_implementation
        == "modality_conservative_quadratic_bound_v1"
    )
    if expected_implementation not in {
        "disabled_v1",
        "modality_conservative_quadratic_bound_v1",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_execution_config = (
        runtime_profile.get(
            "d1_association_sparse_prefilter_execution_config"
        )
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get("d1_association_sparse_prefilter_diagnostics")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    diagnostics = summary.get(
        "d1_association_sparse_prefilter_diagnostics"
    )
    summary_execution_config = summary.get(
        "d1_association_sparse_prefilter_execution_config"
    )
    final = summary.get("module_final_diagnostics")
    final_diagnostics = (
        final.get("d1_association_sparse_prefilter_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    final_execution_config = (
        final.get("d1_association_sparse_prefilter_execution_config")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_diagnostics = governance.get(
        "d1_association_sparse_prefilter_diagnostics"
    )
    governance_execution_config = governance.get(
        "d1_association_sparse_prefilter_execution_config"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_execution_config,
            initial_diagnostics,
            summary_execution_config,
            diagnostics,
            final,
            final_execution_config,
            final_diagnostics,
            governance_execution_config,
            governance_diagnostics,
        )
    ):
        return False
    execution_configs = (
        initial_execution_config,
        summary_execution_config,
        final_execution_config,
        governance_execution_config,
    )
    if not all(
        _association_sparse_prefilter_execution_config_matches(
            item,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
        )
        for item in execution_configs
    ):
        return False
    if initial_diagnostics.get("total_counts") != {
        "candidate_pair_count": 0,
        "conservative_prefilter_rejection_count": 0,
        "exact_gate_pass_count": 0,
        "exact_innovation_solve_count": 0,
        "fallback_count": 0,
    }:
        return False
    if not _association_sparse_prefilter_diagnostics_match(
        initial_diagnostics,
        expected_implementation=expected_implementation,
        expected_implementation_id=expected_id,
        candidate=candidate,
        require_workload=False,
    ):
        return False
    if (
        diagnostics != final_diagnostics
        or diagnostics != governance_diagnostics
        or not _association_sparse_prefilter_diagnostics_match(
            diagnostics,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
            require_workload=True,
        )
    ):
        return False
    selector_field = "d1_association_sparse_prefilter_implementation"
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get(selector_field) == expected_implementation
        and runtime_configuration.get(selector_field)
        == expected_implementation
        and summary.get(selector_field) == expected_implementation
        and final.get(selector_field) == expected_implementation
        and governance.get(selector_field) == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _association_sparse_prefilter_execution_config_matches(
    execution_config: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
    candidate: bool,
) -> bool:
    return (
        execution_config.get("schema_version")
        == "d1.association_sparse_prefilter_execution_config.v1"
        and execution_config.get("selector") == expected_implementation
        and execution_config.get("selected_implementation_id")
        == expected_implementation_id
        and execution_config.get("candidate_enabled") is candidate
        and execution_config.get("candidate_default_enabled") is False
        and execution_config.get("default_selector") == "disabled_v1"
        and execution_config.get("rollback_selector") == "disabled_v1"
        and execution_config.get("truth_dependent_inputs") is False
        and execution_config.get("exact_association_gate_changed") is False
    )


def _association_sparse_prefilter_diagnostics_match(
    diagnostics: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
    candidate: bool,
    require_workload: bool,
) -> bool:
    if (
        diagnostics.get("schema_version")
        != "d1.association_sparse_prefilter_diagnostics.v2"
        or diagnostics.get("selector") != expected_implementation
        or diagnostics.get("selected_implementation_id")
        != expected_implementation_id
        or diagnostics.get("candidate_enabled") is not candidate
    ):
        return False
    execution_config = diagnostics.get("execution_config")
    if (
        not isinstance(execution_config, Mapping)
        or not _association_sparse_prefilter_execution_config_matches(
            execution_config,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_implementation_id,
            candidate=candidate,
        )
    ):
        return False
    modality_order = (
        "radar",
        "lidar",
        "acoustic",
        "acoustic_3d",
        "eo",
        "other",
    )
    if tuple(diagnostics.get("modality_order", ())) != modality_order:
        return False
    modality_counts = diagnostics.get("modality_counts")
    total_counts = diagnostics.get("total_counts")
    conservation = diagnostics.get("conservation")
    if (
        not isinstance(modality_counts, Mapping)
        or set(modality_counts) != set(modality_order)
        or not isinstance(total_counts, Mapping)
        or not isinstance(conservation, Mapping)
        or conservation.get("all_counter_bounds_hold") is not True
        or conservation.get("fixed_modality_bucket_count") is not True
    ):
        return False
    fields = (
        "candidate_pair_count",
        "conservative_prefilter_rejection_count",
        "exact_innovation_solve_count",
        "exact_gate_pass_count",
        "fallback_count",
    )
    sums = {field: 0 for field in fields}
    for modality in modality_order:
        counts = modality_counts.get(modality)
        if not isinstance(counts, Mapping):
            return False
        values: dict[str, int] = {}
        for field in fields:
            value = counts.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                return False
            values[field] = int(value)
            sums[field] += int(value)
        if (
            values["conservative_prefilter_rejection_count"]
            > values["candidate_pair_count"]
            or values["exact_innovation_solve_count"]
            > values["candidate_pair_count"]
            or values["exact_gate_pass_count"]
            > values["exact_innovation_solve_count"]
            or values["fallback_count"] > values["candidate_pair_count"]
        ):
            return False
    if any(total_counts.get(field) != sums[field] for field in fields):
        return False
    non_radar_rejections = sum(
        int(
            modality_counts[modality][
                "conservative_prefilter_rejection_count"
            ]
        )
        for modality in ("lidar", "acoustic", "acoustic_3d", "eo")
    )
    if candidate:
        treatment_match = (
            not require_workload or non_radar_rejections > 0
        )
    else:
        treatment_match = non_radar_rejections == 0
    return (
        treatment_match
        and (
            not require_workload
            or int(total_counts["candidate_pair_count"]) > 0
        )
    )


def _replay_prefix_summary_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = (
        expected_implementation
        == "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
    )
    if expected_implementation not in {
        "per_checkpoint_prefix_rebuild_v1",
        "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
    }:
        return False

    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_execution_config = (
        runtime_profile.get("d1_replay_prefix_summary_execution_config")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get("d1_replay_prefix_summary_diagnostics")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    summary_execution_config = summary.get(
        "d1_replay_prefix_summary_execution_config"
    )
    diagnostics = summary.get("d1_replay_prefix_summary_diagnostics")
    final = summary.get("module_final_diagnostics")
    final_execution_config = (
        final.get("d1_replay_prefix_summary_execution_config")
        if isinstance(final, Mapping)
        else None
    )
    final_diagnostics = (
        final.get("d1_replay_prefix_summary_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
        online_evidence = _read_mapping(
            episode_dir
            / "offline_consistency"
            / "online_evidence.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_execution_config = governance.get(
        "d1_replay_prefix_summary_execution_config"
    )
    governance_diagnostics = governance.get(
        "d1_replay_prefix_summary_diagnostics"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_execution_config,
            initial_diagnostics,
            summary_execution_config,
            diagnostics,
            final,
            final_execution_config,
            final_diagnostics,
            governance_execution_config,
            governance_diagnostics,
            online_evidence,
        )
    ):
        return False

    execution_configs = (
        initial_execution_config,
        summary_execution_config,
        final_execution_config,
        governance_execution_config,
    )
    if not all(
        _replay_prefix_summary_execution_config_matches(
            item,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
        )
        for item in execution_configs
    ):
        return False
    if not _replay_prefix_summary_diagnostics_match(
        initial_diagnostics,
        expected_implementation=expected_implementation,
        expected_implementation_id=expected_id,
        candidate=candidate,
        require_workload=False,
        require_materialized=True,
    ):
        return False
    if (
        diagnostics != governance_diagnostics
        or not _replay_prefix_summary_diagnostics_match(
            diagnostics,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
            require_workload=True,
            require_materialized=True,
        )
        or not _replay_prefix_summary_diagnostics_match(
            final_diagnostics,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_id,
            candidate=candidate,
            require_workload=True,
            require_materialized=False,
        )
    ):
        return False

    record_count = online_evidence.get("record_count")
    records_digest = online_evidence.get("records_digest")
    if (
        online_evidence.get("schema_version")
        != "d1.consistency.online_evidence_bundle.v1"
        or isinstance(record_count, bool)
        or not isinstance(record_count, int)
        or record_count <= 0
        or not isinstance(records_digest, str)
        or _SHA256_RE.fullmatch(records_digest) is None
    ):
        return False

    selector_field = "d1_replay_prefix_summary_implementation"
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get(selector_field) == expected_implementation
        and runtime_configuration.get(selector_field)
        == expected_implementation
        and summary.get(selector_field) == expected_implementation
        and final.get(selector_field) == expected_implementation
        and governance.get(selector_field) == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _replay_prefix_summary_execution_config_matches(
    execution_config: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
    candidate: bool,
) -> bool:
    return (
        execution_config.get("schema_version")
        == "d1.fixed_lag_replay_prefix_summary_execution_config.v1"
        and execution_config.get("selector") == expected_implementation
        and execution_config.get("selected_implementation_id")
        == expected_implementation_id
        and execution_config.get("candidate_enabled") is candidate
        and execution_config.get("candidate_default_enabled") is False
        and execution_config.get("default_selector")
        == "per_checkpoint_prefix_rebuild_v1"
        and execution_config.get("rollback_selector")
        == "per_checkpoint_prefix_rebuild_v1"
        and execution_config.get("summary_schema_version")
        == "d1.fixed_lag_replay_prefix_summary.v1"
        and _float_equal(execution_config.get("buffer_horizon_s"), 6.0)
        and execution_config.get("truth_dependent_inputs") is False
        and execution_config.get("fixed_lag_window_changed") is False
        and execution_config.get("checkpoint_audit_semantics_changed")
        is False
        and execution_config.get("consistency_evidence_semantics_changed")
        is False
    )


def _replay_prefix_summary_diagnostics_match(
    diagnostics: Mapping[str, Any],
    *,
    expected_implementation: str,
    expected_implementation_id: str,
    candidate: bool,
    require_workload: bool,
    require_materialized: bool,
) -> bool:
    if (
        diagnostics.get("schema_version")
        != "d1.fixed_lag_replay_prefix_summary_diagnostics.v1"
        or diagnostics.get("selector") != expected_implementation
        or diagnostics.get("selected_implementation_id")
        != expected_implementation_id
    ):
        return False
    execution_config = diagnostics.get("execution_config")
    operation_counts = diagnostics.get("operation_counts")
    fallback_reasons = diagnostics.get("fallback_reasons")
    materialization_reasons = diagnostics.get("materialization_reasons")
    conservation = diagnostics.get("conservation")
    pending_count = diagnostics.get("pending_consistency_ledger_count")
    if (
        not isinstance(execution_config, Mapping)
        or not _replay_prefix_summary_execution_config_matches(
            execution_config,
            expected_implementation=expected_implementation,
            expected_implementation_id=expected_implementation_id,
            candidate=candidate,
        )
        or not isinstance(operation_counts, Mapping)
        or not isinstance(fallback_reasons, Mapping)
        or not isinstance(materialization_reasons, Mapping)
        or not isinstance(conservation, Mapping)
        or isinstance(pending_count, bool)
        or not isinstance(pending_count, int)
        or pending_count < 0
        or any(value is not True for value in conservation.values())
    ):
        return False
    for counts in (
        operation_counts,
        fallback_reasons,
        materialization_reasons,
    ):
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in counts.values()
        ):
            return False
    if require_materialized and pending_count != 0:
        return False

    attempts = int(operation_counts.get("summary_attempt_count", 0))
    hits = int(operation_counts.get("summary_hit_count", 0))
    fallbacks = int(operation_counts.get("summary_fallback_count", 0))
    reused = int(
        operation_counts.get("summary_reused_checkpoint_count", 0)
    )
    logical_refreshes = int(
        operation_counts.get(
            "lazy_consistency_refresh_logical_record_count",
            0,
        )
    )
    materialized_records = int(
        operation_counts.get(
            "lazy_consistency_materialized_record_count",
            0,
        )
    )
    if (
        attempts != hits + fallbacks
        or fallbacks != sum(int(value) for value in fallback_reasons.values())
        or hits > attempts
        or reused < hits
        or materialized_records > logical_refreshes
    ):
        return False
    if candidate:
        if not require_workload:
            return True
        append_revision_advances = int(
            operation_counts.get("append_only_revision_advance_count", 0)
        )
        append_pending_preservations = int(
            operation_counts.get(
                "append_only_pending_preservation_count",
                0,
            )
        )
        snapshot_projections = int(
            operation_counts.get("public_snapshot_projection_count", 0)
        )
        snapshot_projected_records = int(
            operation_counts.get(
                "public_snapshot_projected_record_count",
                0,
            )
        )
        append_materializations = int(
            materialization_reasons.get("checkpoint_suffix_appended", 0)
        ) + int(
            materialization_reasons.get(
                "checkpoint_suffix_append_incompatible",
                0,
            )
        )
        workload_valid = (
            attempts > 0
            and hits > 0
            and reused > 0
            and logical_refreshes > 0
            and append_revision_advances > 0
            and append_pending_preservations > 0
            and snapshot_projections > 0
            and snapshot_projected_records > 0
            and append_materializations == 0
        )
        if require_materialized:
            return workload_valid and materialized_records > 0
        return workload_valid
    return (
        pending_count == 0
        and hits == 0
        and reused == 0
        and logical_refreshes == 0
        and materialized_records == 0
    )


def _online_truth_guard_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    if expected_implementation not in {
        "generic_recursive_v1",
        "builtin_specialized_recursive_v2",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    diagnostics = summary.get("online_truth_guard_diagnostics")
    online_path = episode_dir / "online_observations.jsonl"
    if (
        not isinstance(runtime_profile, Mapping)
        or not isinstance(diagnostics, Mapping)
        or not online_path.is_file()
    ):
        return False
    candidate = (
        expected_implementation == "builtin_specialized_recursive_v2"
    )
    try:
        online_message_count = _nonempty_line_count(online_path)
        validation_count = int(diagnostics.get("validation_count"))
    except (OSError, TypeError, ValueError):
        return False
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get("online_truth_guard_implementation")
        == expected_implementation
        and summary.get("online_truth_guard_implementation")
        == expected_implementation
        and diagnostics.get("schema_version")
        == "scalable3d-online-truth-guard-diagnostics-v1"
        and diagnostics.get("implementation") == expected_implementation
        and diagnostics.get("candidate_enabled") is candidate
        and validation_count == online_message_count
        and validation_count > 0
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _v2_d2_audit_matches(
    summary: Mapping[str, Any],
    *,
    candidate: bool,
) -> bool:
    audit = summary.get("d2_publication_metadata_audit")
    if not isinstance(audit, Mapping):
        return False
    if (
        audit.get("schema_version")
        != "scalable3d-d2-publication-metadata-audit-v1"
    ):
        return False
    batch_count = audit.get("batch_count")
    latest = audit.get("latest")
    totals = audit.get("totals")
    if (
        isinstance(batch_count, bool)
        or not isinstance(batch_count, int)
        or batch_count <= 0
        or not isinstance(latest, Mapping)
        or not isinstance(totals, Mapping)
    ):
        return False
    required = (
        "metadata_count",
        "shared_subtree_full_audit_count",
        "shared_subtree_builtin_equivalent_reuse_count",
        "immutable_v2_contract_validation_count",
        "immutable_v2_full_content_audit_count",
        "immutable_v2_identity_reuse_count",
        "immutable_v2_contract_rejection_count",
    )
    for counts in (latest, totals):
        if any(
            isinstance(counts.get(key), bool)
            or not isinstance(counts.get(key), int)
            or int(counts[key]) < 0
            for key in required
        ):
            return False
    if any(int(totals[key]) < int(latest[key]) for key in required):
        return False
    if int(totals["metadata_count"]) <= 0:
        return False
    full_audit_count = int(totals["shared_subtree_full_audit_count"])
    builtin_reuse_count = int(
        totals["shared_subtree_builtin_equivalent_reuse_count"]
    )
    validation_count = int(
        totals["immutable_v2_contract_validation_count"]
    )
    v2_content_audit_count = int(
        totals["immutable_v2_full_content_audit_count"]
    )
    identity_reuse_count = int(
        totals["immutable_v2_identity_reuse_count"]
    )
    rejection_count = int(
        totals["immutable_v2_contract_rejection_count"]
    )
    if candidate:
        return (
            validation_count > 0
            and validation_count == v2_content_audit_count
            and full_audit_count == v2_content_audit_count
            and identity_reuse_count > 0
            and builtin_reuse_count == 0
            and rejection_count == 0
        )
    return (
        full_audit_count > 0
        and builtin_reuse_count > 0
        and validation_count == 0
        and v2_content_audit_count == 0
        and identity_reuse_count == 0
        and rejection_count == 0
    )


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"git {' '.join(args)} failed in {root}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _nonempty_line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as stream:
        return sum(1 for line in stream if line.strip())


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_float(value: float) -> str:
    return format(value, ".15g")


def _required_text(value: Any, field: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise ValueError(f"{field} must be non-empty")
    return result


def _positive_int(value: Any, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(value)


def _finite_float(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field} must be finite numeric")
    return float(value)


def _float_equal(value: Any, expected: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and math.isclose(
            float(value),
            float(expected),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )


def _all_true(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is True for item in value.values())
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=(
            ROOT
            / "research_modules"
            / "scalable_3d_simulation"
            / "configs"
            / "d1_publication_metadata_multiseed_v1.json"
        ),
    )
    parser.add_argument(
        "--source-worktree",
        type=Path,
        default=ROOT,
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_matrix(
        args.matrix,
        args.source_worktree,
        args.output_root,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    print(f"status={result['status']}")
    print(
        "evidence_manifest="
        f"{(args.output_root / 'evidence_manifest.json').resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
