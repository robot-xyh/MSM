"""Build the main-owned scalable learning seed registry.

This command allocates seeds only.  It does not create an episode, read a
formal payload, train a model or grant runtime authority.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from research_modules.scalable_3d_simulation.global_seed_registry import (
    GLOBAL_SEED_REGISTRY_POLICY_VERSION,
    GLOBAL_SEED_REGISTRY_SCHEMA_VERSION,
    build_global_seed_registry,
    registry_content_sha256,
    validate_registry_source_contracts,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "configs/scalable_learning_global_seed_registry_v1.json"
)


def _binding(role: str, relative_path: str) -> dict[str, str]:
    path = REPOSITORY_ROOT / relative_path
    return {
        "role": role,
        "path": relative_path,
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }


def _allocation(
    *,
    allocation_id: str,
    owner: str,
    candidate_version: str,
    usage_class: str,
    split_policy: str,
    operations: list[str],
    seeds: range,
    source_contract: dict[str, Any],
) -> dict[str, Any]:
    values = list(seeds)
    return {
        "allocation_id": allocation_id,
        "owner": owner,
        "candidate_version": candidate_version,
        "lifecycle": "reserved",
        "usage_class": usage_class,
        "split_policy": split_policy,
        "permitted_operations": operations,
        "seed_count": len(values),
        "seeds": values,
        "source_contract": source_contract,
    }


def build_payload() -> dict[str, Any]:
    d3_bindings = [
        _binding(
            "data_contract",
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_data_contract_v1.json",
        ),
        _binding(
            "development_data_request",
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_development_data_request_v1.json",
        ),
        _binding(
            "seed_exclusion_registry",
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_seed_exclusion_registry_v1.json",
        ),
    ]
    d4_bindings = [
        _binding(
            "development_data_request",
            "research_modules/d4_distributed_fallback/reports/"
            "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
            "v8_development_data_request.json",
        ),
        _binding(
            "module_seed_request",
            "research_modules/d4_distributed_fallback/reports/"
            "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
            "v8_development_seed_registry.json",
        ),
    ]
    d5_bindings = [
        _binding(
            "minority_intent_protocol",
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol_20260801.json",
        ),
        _binding(
            "protocol_schema",
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol.schema.json",
        ),
        _binding(
            "source_manifest_schema",
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_source_manifest.schema.json",
        ),
    ]

    payload: dict[str, Any] = {
        "schema_version": GLOBAL_SEED_REGISTRY_SCHEMA_VERSION,
        "policy_version": GLOBAL_SEED_REGISTRY_POLICY_VERSION,
        "registry_id": "scalable3d-learning-source-allocation-20260801-v1",
        "status": "allocations_reserved_generation_not_started",
        "protected_seed_sets": [
            {
                "set_id": "legacy-learning-train-v1",
                "purpose": "prior_scalable_training_source",
                "seeds": list(range(0, 100)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
            {
                "set_id": "formal-evaluation-v1",
                "purpose": "formal_evaluation_payload",
                "seeds": list(range(1000, 1020)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": False,
            },
            {
                "set_id": "d4-prior-design-and-evaluation-v5-v7",
                "purpose": "prior_d4_design_development_and_evaluation_sources",
                "seeds": [
                    *range(3000, 3040),
                    *range(4000, 4080),
                    *range(5200, 5280),
                ],
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
            {
                "set_id": "d3-a1-v2-evaluation",
                "purpose": "prior_d3_source_independent_evaluation",
                "seeds": list(range(20000, 20100)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
            {
                "set_id": "d5-a3-v1-corpus",
                "purpose": "prior_d5_source_independent_corpus",
                "seeds": list(range(21000, 21100)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
            {
                "set_id": "d5-a3-development-probe",
                "purpose": "prior_dirty_development_probe",
                "seeds": list(range(21900, 21910)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
            {
                "set_id": "d5-a3-abandoned-v2-attempt",
                "purpose": "abandoned_non_finalized_source",
                "seeds": list(range(22000, 22028)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": False,
            },
            {
                "set_id": "d5-a3-v2-corpus",
                "purpose": "prior_d5_balanced_action_role_corpus",
                "seeds": list(range(22100, 22200)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": True,
            },
        ],
        "allocations": [
            _allocation(
                allocation_id="d3-a1-v3-all-splits",
                owner="D3",
                candidate_version="d3-a1-v3",
                usage_class="train_validation_test",
                split_policy="whole_seed_60_20_20_v1",
                operations=["dataset_generation"],
                seeds=range(23000, 23300),
                source_contract={
                    "contract_id": (
                        "d3-a1-source-independent-v3-data-contract-20260801-v1"
                    ),
                    "request_id": (
                        "d3-a1-source-independent-v3-development-data-request-"
                        "20260801-v1"
                    ),
                    "bindings": d3_bindings,
                },
            ),
            _allocation(
                allocation_id="d5-a3-v3-train",
                owner="D5",
                candidate_version="d5-a3-v3",
                usage_class="train_only",
                split_policy="whole_episode_train_v1",
                operations=["dataset_generation", "training"],
                seeds=range(24000, 24048),
                source_contract={
                    "protocol_id": (
                        "a3_v3_hierarchical_intent_legal_candidate_ranking_20260801"
                    ),
                    "split": "train",
                    "bindings": d5_bindings,
                },
            ),
            _allocation(
                allocation_id="d5-a3-v3-validation",
                owner="D5",
                candidate_version="d5-a3-v3",
                usage_class="validation_only",
                split_policy="whole_episode_validation_v1",
                operations=["dataset_generation", "validation"],
                seeds=range(24048, 24072),
                source_contract={
                    "protocol_id": (
                        "a3_v3_hierarchical_intent_legal_candidate_ranking_20260801"
                    ),
                    "split": "validation",
                    "bindings": d5_bindings,
                },
            ),
            _allocation(
                allocation_id="d5-a3-v3-future-held-out",
                owner="D5",
                candidate_version="d5-a3-v3",
                usage_class="test_only",
                split_policy="whole_episode_one_shot_future_held_out_v1",
                operations=["dataset_generation", "test"],
                seeds=range(24072, 24104),
                source_contract={
                    "protocol_id": (
                        "a3_v3_hierarchical_intent_legal_candidate_ranking_20260801"
                    ),
                    "split": "future_held_out",
                    "maximum_evaluation_access_count": 1,
                    "bindings": d5_bindings,
                },
            ),
            _allocation(
                allocation_id="d4-a2-v8-train",
                owner="D4",
                candidate_version="d4-a2-v8",
                usage_class="train_only",
                split_policy="fixed_108_cells_3_replicates_train_only_v1",
                operations=["dataset_generation", "training"],
                seeds=range(28100, 28424),
                source_contract={
                    "request_id": "d4-region-resource-v8-development-source-request-v1",
                    "module_seed_registry_id": (
                        "d4-v8-development-train-source-request-v1"
                    ),
                    "bindings": d4_bindings,
                },
            ),
        ],
        "unallocated_requests": [],
        "generation_state": {
            "episode_generation_started": False,
            "sample_generation_started": False,
            "training_started": False,
            "formal_seed_payload_read": False,
            "module_readiness_required": True,
        },
    }
    payload["content_sha256"] = registry_content_sha256(payload)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_payload()
    build_global_seed_registry(payload)
    if args.check:
        stored = json.loads(args.output.read_text(encoding="ascii"))
        if stored != payload:
            raise RuntimeError("stored global seed registry does not reproduce")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="ascii",
        )
    registry = build_global_seed_registry(payload)
    validate_registry_source_contracts(registry, repository_root=REPOSITORY_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
