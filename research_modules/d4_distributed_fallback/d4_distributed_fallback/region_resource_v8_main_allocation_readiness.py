"""Fail-closed binding from main seed allocation to the D4 A2 v8 request.

The validator is a repository-local pre-generation gate.  It reads the
main-owned global registry and the two already frozen D4 request files, but it
does not generate data, train a model, register a candidate, or grant runtime
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_modules.scalable_3d_simulation.global_seed_registry import (
    GlobalSeedRegistryError,
    build_global_seed_registry,
    validate_seed_request,
)

from .region_resource_v8_development_contract import (
    RegionResourceV8ContractError,
    V8NoAuthorityPermissions,
    V8_REQUESTED_SEEDS,
    canonical_v8_sha256,
    load_v8_frozen_request,
)
from .region_resource_v8_dataset_writer import V8_WRITER_RESUME_STATE_SCHEMA
from .region_resource_v8_source_viability import (
    RegionResourceV8SourceViabilityError,
    V8_SOURCE_VIABILITY_AUDIT_SCHEMA,
    audit_v8_frozen_source_viability,
)


V8_MAIN_ALLOCATION_BINDING_SCHEMA = (
    "d4-region-resource-v8-main-seed-allocation-binding-v1"
)
V8_MAIN_ALLOCATION_READINESS_SCHEMA = (
    "d4-region-resource-v8-main-seed-allocation-readiness-v1"
)
V8_MAIN_ALLOCATION_BINDING_ID = (
    "d4-a2-v8-main-seed-allocation-binding-20260801-v1"
)
V8_MAIN_ALLOCATION_BINDING_STATUS = "frozen_generation_prerequisites_only"
V8_MAIN_ALLOCATION_READY_STATUS = (
    "generation_prerequisites_ready_no_data_generated"
)

V8_SOURCE_GENERATION_REQUEST_SCHEMA = (
    "d4-region-resource-v8-train-source-generation-request-readiness-v1"
)
V8_SOURCE_GENERATION_REQUEST_PERMISSIONS_SCHEMA = (
    "d4-region-resource-v8-generation-request-only-permissions-v1"
)
V8_SOURCE_GENERATION_REQUEST_ARTIFACT_ID = (
    "d4-a2-v8-train-source-generation-request-readiness-20260801-v1"
)
V8_SOURCE_GENERATION_REQUEST_STATUS = (
    "source_generation_request_ready_execution_not_authorized"
)
SOURCE_GENERATION_REQUEST_PATH = (
    "research_modules/d4_distributed_fallback/configs/"
    "region_resource_v8_train_source_generation_request_readiness_v1.json"
)
SOURCE_GENERATION_REQUEST_CONTENT_SHA256 = (
    "1d53de5ca23b2de7b06aab6a0be719ffc78c8c977bcc408775e372ad677a10c1"
)
SOURCE_GENERATION_REQUEST_FILE_SHA256 = (
    "18b595057197dda06b8b2a1ec2a357f1f4d652d2512752be83db2f1e979df1e2"
)

GLOBAL_REGISTRY_PATH = (
    "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)
GLOBAL_REGISTRY_SCHEMA = "scalable3d-global-seed-registry-v1"
GLOBAL_REGISTRY_POLICY = "scalable3d-seed-allocation-policy-v1"
GLOBAL_REGISTRY_ID = "scalable3d-learning-source-allocation-20260801-v1"
GLOBAL_REGISTRY_STATUS = "allocations_reserved_generation_not_started"
GLOBAL_REGISTRY_CONTENT_SHA256 = (
    "89d99bf064a8c0e226eead5b675f05daf70ac2d4c6f6139322502da54ab0aea7"
)
GLOBAL_REGISTRY_FILE_SHA256 = (
    "1c9778e1cbfcd5679956ac2c1fc71a1e780207c4579abdc9b129d162a252c4b6"
)

ALLOCATION_ID = "d4-a2-v8-train"
ALLOCATION_OWNER = "D4"
ALLOCATION_CANDIDATE_VERSION = "d4-a2-v8"
ALLOCATION_LIFECYCLE = "reserved"
ALLOCATION_USAGE_CLASS = "train_only"
ALLOCATION_SPLIT_POLICY = "fixed_108_cells_3_replicates_train_only_v1"
ALLOCATION_OPERATIONS = ("dataset_generation", "training")
READINESS_OPERATION = "dataset_generation"
SEED_INVENTORY_SHA256 = (
    "e1bf7b14943fee8e600a60731aee1788d36586d1e52a20da9406473ac3a4b621"
)

D4_REQUEST_ID = "d4-region-resource-v8-development-source-request-v1"
D4_REQUEST_PATH = (
    "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
    "v8_development_data_request.json"
)
D4_REQUEST_CONTENT_SHA256 = (
    "cfdb88649d70fd390204edcd891cb1826aa8aa85d2af706ebb2ed95bc46ee8aa"
)
D4_REQUEST_FILE_SHA256 = (
    "daa42fd6a980923231e244d772b20dc8d7b76ee12e1d53b15009ff346de12d38"
)
D4_MODULE_SEED_REGISTRY_ID = "d4-v8-development-train-source-request-v1"
D4_MODULE_SEED_REGISTRY_PATH = (
    "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/"
    "v8_development_seed_registry.json"
)
D4_MODULE_SEED_REGISTRY_CONTENT_SHA256 = (
    "16f8acd4457c0914a0ec9296724280fcccfe43f2667d87401464fb9a27c04550"
)
D4_MODULE_SEED_REGISTRY_FILE_SHA256 = (
    "cd40390994a6216ebb6ab3415fd467762d6900c45ad7f6ebd7ee783a9bf77015"
)
D4_MODULE_SCHEDULE_CONTENT_SHA256 = (
    "8b736f2ad6272e90fcf366969b5206039e9616fb0e1197bdb3c615e2e107f890"
)

MAIN_ALLOCATION_BINDING_PATH = (
    "research_modules/d4_distributed_fallback/configs/"
    "region_resource_v8_main_seed_allocation_binding_v1.json"
)
MAIN_ALLOCATION_BINDING_CONTENT_SHA256 = (
    "60b42f2be28f3b389cae9a299045a3457e8b549d1525d5a7102c0a3e30533a20"
)
MAIN_ALLOCATION_BINDING_FILE_SHA256 = (
    "d88a8222e383ad18c59111ab6b7f3b7b41f4929f1472ed15fadca8cc4bbdaff7"
)
V8_WRITER_RESUME_IMPLEMENTATION_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v8_dataset_writer.py"
)
V8_WRITER_RESUME_IMPLEMENTATION_FILE_SHA256 = (
    "26c34413f7449b1b5ffc9b26bf50f49ff1636be0126897e21bf43fbeb8a2204b"
)
V8_CONTRACT_IMPLEMENTATION_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v8_development_contract.py"
)
V8_CONTRACT_IMPLEMENTATION_FILE_SHA256 = (
    "a0675de43feeaecd9963949ec78c8b5dafed37fa9c511bfcc7d314c469633ea7"
)
V8_RUNTIME_EVIDENCE_IMPLEMENTATION_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v8_runtime_evidence.py"
)
V8_RUNTIME_EVIDENCE_IMPLEMENTATION_FILE_SHA256 = (
    "b8da96aef791bc45044f1670bbb57bd7ba6c57f6e2ee00d764364f9ef1796628"
)
V8_SOURCE_VIABILITY_IMPLEMENTATION_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_v8_source_viability.py"
)
V8_SOURCE_VIABILITY_IMPLEMENTATION_FILE_SHA256 = (
    "5d577a22f689f3c4cfc8755b9e9fb54f4818fb085edbace55e0dcb082ad64fc4"
)
V8_REGION_RESOURCE_POLICY_IMPLEMENTATION_PATH = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource.py"
)
V8_REGION_RESOURCE_POLICY_IMPLEMENTATION_FILE_SHA256 = (
    "1f47de6104f16c563ca6fc8cca3f1540437d77f3d3617225eef7b8b2423a78c2"
)
V8_MAIN_RUNTIME_ADAPTER_IMPLEMENTATION_PATH = (
    "research_modules/scalable_3d_simulation/learning_source_adapters.py"
)
V8_MAIN_RUNTIME_ADAPTER_IMPLEMENTATION_FILE_SHA256 = (
    "1b409de412dcfd3affb4dde254d7782804b296e013fdbab254e9b8995bfed642"
)
V8_MAIN_TREATMENT_IMPLEMENTATION_PATH = (
    "research_modules/scalable_3d_simulation/episode_treatments.py"
)
V8_MAIN_TREATMENT_IMPLEMENTATION_FILE_SHA256 = (
    "8e77b53dc1f9a5558d4b2f73e10c03f36aa292a298c76c6182169070c5e5ae19"
)

V8_GENERATION_REQUEST_PERMISSION_NAMES = (
    "source_generation_request",
    "dataset_generation_execution",
    "training",
    "validation_selection",
    "test_selection",
    "shadow",
    "assist",
    "authority",
    "assignment",
    "degradation",
    "takeover",
    "coalition",
    "runtime",
    "physical",
    "control",
    "production",
    "registration",
    "runtime_ack",
    "d3",
    "d7",
)

_BINDING_ROOT_KEYS = frozenset(
    {
        "schema",
        "binding_id",
        "status",
        "purpose",
        "global_registry",
        "allocation",
        "d4_frozen_contract",
        "generation_claims",
        "permissions",
        "content_sha256",
    }
)

_SOURCE_GENERATION_REQUEST_ROOT_KEYS = frozenset(
    {
        "schema",
        "artifact_id",
        "report_date",
        "status",
        "purpose",
        "references",
        "request_scope",
        "resume_safety",
        "permissions",
        "execution_claims",
        "content_sha256",
    }
)


class RegionResourceV8MainAllocationError(ValueError):
    """Stable fail-closed error from the main-allocation readiness gate."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(message or self.code)


@dataclass(frozen=True)
class V8GenerationRequestOnlyPermissions:
    source_generation_request: bool = True
    dataset_generation_execution: bool = False
    training: bool = False
    validation_selection: bool = False
    test_selection: bool = False
    shadow: bool = False
    assist: bool = False
    authority: bool = False
    assignment: bool = False
    degradation: bool = False
    takeover: bool = False
    coalition: bool = False
    runtime: bool = False
    physical: bool = False
    control: bool = False
    production: bool = False
    registration: bool = False
    runtime_ack: bool = False
    d3: bool = False
    d7: bool = False
    schema: str = V8_SOURCE_GENERATION_REQUEST_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != V8_SOURCE_GENERATION_REQUEST_PERMISSIONS_SCHEMA:
            raise ValueError("v8_generation_request_permissions_schema_mismatch")
        for name in V8_GENERATION_REQUEST_PERMISSION_NAMES:
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(
                    f"v8_generation_request_permission_not_boolean:{name}"
                )
            expected = name == "source_generation_request"
            if value is not expected:
                raise ValueError(
                    f"v8_generation_request_permission_mismatch:{name}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            **{
                name: getattr(self, name)
                for name in V8_GENERATION_REQUEST_PERMISSION_NAMES
            },
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "V8GenerationRequestOnlyPermissions":
        mapping = _strict_mapping(value, "generation_request.permissions")
        _require_exact_keys(
            mapping,
            {"schema", *V8_GENERATION_REQUEST_PERMISSION_NAMES},
            "generation_request.permissions",
        )
        return cls(**dict(mapping))


@dataclass(frozen=True)
class V8MainAllocationPreGenerationReadiness:
    binding_id: str
    source_generation_request_path: str
    source_generation_request_sha256: str
    source_generation_request_content_sha256: str
    source_generation_request_artifact_id: str
    global_registry_id: str
    global_registry_content_sha256: str
    global_registry_file_sha256: str
    allocation_id: str
    allocation_seed_count: int
    allocation_seed_range: tuple[int, int]
    allocation_seed_inventory_sha256: str
    d4_request_content_sha256: str
    d4_request_file_sha256: str
    d4_module_seed_registry_content_sha256: str
    d4_module_seed_registry_file_sha256: str
    d4_module_schedule_content_sha256: str
    source_viability_audit_content_sha256: str
    source_viability_cell_evidence_sha256: str
    source_viability_episode_count: int
    source_viability_frame_count: int
    global_registry_validated: bool = True
    global_overlap_policy_validated: bool = True
    source_bindings_validated: bool = True
    d4_frozen_contract_validated: bool = True
    exact_seed_inventory_validated: bool = True
    train_only_validated: bool = True
    source_generation_request_artifact_validated: bool = True
    writer_resume_safety_validated: bool = True
    source_viability_audit_validated: bool = True
    generation_prerequisites_ready: bool = True
    source_generation_request_ready: bool = True
    main_execution_authorization: bool = False
    dataset_generation_executed: bool = False
    generated_episode_count: int = 0
    generated_sample_count: int = 0
    training_ready: bool = False
    model_ready: bool = False
    runtime_admission_ready: bool = False
    validation_seed_allocation: tuple[int, ...] = ()
    test_seed_allocation: tuple[int, ...] = ()
    generation_request_permissions: V8GenerationRequestOnlyPermissions = (
        V8GenerationRequestOnlyPermissions()
    )
    permissions: V8NoAuthorityPermissions = V8NoAuthorityPermissions()
    status: str = V8_MAIN_ALLOCATION_READY_STATUS
    schema: str = V8_MAIN_ALLOCATION_READINESS_SCHEMA
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.schema != V8_MAIN_ALLOCATION_READINESS_SCHEMA:
            raise ValueError("v8_main_allocation_readiness_schema_mismatch")
        if self.status != V8_MAIN_ALLOCATION_READY_STATUS:
            raise ValueError("v8_main_allocation_readiness_status_mismatch")
        if self.binding_id != V8_MAIN_ALLOCATION_BINDING_ID:
            raise ValueError("v8_main_allocation_readiness_binding_mismatch")
        for name in (
            "global_registry_validated",
            "global_overlap_policy_validated",
            "source_bindings_validated",
            "d4_frozen_contract_validated",
            "exact_seed_inventory_validated",
            "train_only_validated",
            "source_generation_request_artifact_validated",
            "writer_resume_safety_validated",
            "source_viability_audit_validated",
            "generation_prerequisites_ready",
            "source_generation_request_ready",
        ):
            if getattr(self, name) is not True:
                raise ValueError(f"v8_main_allocation_readiness_required_true:{name}")
        for name in (
            "main_execution_authorization",
            "dataset_generation_executed",
            "training_ready",
            "model_ready",
            "runtime_admission_ready",
        ):
            if getattr(self, name) is not False:
                raise ValueError(f"v8_main_allocation_readiness_required_false:{name}")
        if self.generated_episode_count != 0 or self.generated_sample_count != 0:
            raise ValueError("v8_main_allocation_readiness_generated_count_nonzero")
        if self.source_viability_episode_count != len(V8_REQUESTED_SEEDS):
            raise ValueError("v8_main_allocation_source_viability_count_mismatch")
        if self.source_viability_frame_count <= 0:
            raise ValueError("v8_main_allocation_source_viability_frames_missing")
        if self.validation_seed_allocation or self.test_seed_allocation:
            raise ValueError("v8_main_allocation_readiness_nontrain_seed_present")
        if self.source_generation_request_path != SOURCE_GENERATION_REQUEST_PATH:
            raise ValueError("v8_source_generation_request_path_mismatch")
        if (
            self.source_generation_request_sha256
            != SOURCE_GENERATION_REQUEST_FILE_SHA256
            or self.source_generation_request_content_sha256
            != SOURCE_GENERATION_REQUEST_CONTENT_SHA256
            or self.source_generation_request_artifact_id
            != V8_SOURCE_GENERATION_REQUEST_ARTIFACT_ID
        ):
            raise ValueError("v8_source_generation_request_identity_mismatch")
        if not isinstance(
            self.generation_request_permissions,
            V8GenerationRequestOnlyPermissions,
        ):
            raise ValueError("v8_generation_request_permissions_invalid")
        if not isinstance(self.permissions, V8NoAuthorityPermissions):
            raise ValueError("v8_main_allocation_readiness_permissions_invalid")
        expected = _binding_content_sha256(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected:
            raise ValueError("v8_main_allocation_readiness_content_hash_mismatch")
        object.__setattr__(self, "content_sha256", expected)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "binding_id": self.binding_id,
            "source_generation_request_path": (
                self.source_generation_request_path
            ),
            "source_generation_request_sha256": (
                self.source_generation_request_sha256
            ),
            "source_generation_request_content_sha256": (
                self.source_generation_request_content_sha256
            ),
            "source_generation_request_artifact_id": (
                self.source_generation_request_artifact_id
            ),
            "global_registry_id": self.global_registry_id,
            "global_registry_content_sha256": self.global_registry_content_sha256,
            "global_registry_file_sha256": self.global_registry_file_sha256,
            "allocation_id": self.allocation_id,
            "allocation_seed_count": self.allocation_seed_count,
            "allocation_seed_range": list(self.allocation_seed_range),
            "allocation_seed_inventory_sha256": (
                self.allocation_seed_inventory_sha256
            ),
            "d4_request_content_sha256": self.d4_request_content_sha256,
            "d4_request_file_sha256": self.d4_request_file_sha256,
            "d4_module_seed_registry_content_sha256": (
                self.d4_module_seed_registry_content_sha256
            ),
            "d4_module_seed_registry_file_sha256": (
                self.d4_module_seed_registry_file_sha256
            ),
            "d4_module_schedule_content_sha256": (
                self.d4_module_schedule_content_sha256
            ),
            "source_viability_audit_content_sha256": (
                self.source_viability_audit_content_sha256
            ),
            "source_viability_cell_evidence_sha256": (
                self.source_viability_cell_evidence_sha256
            ),
            "source_viability_episode_count": self.source_viability_episode_count,
            "source_viability_frame_count": self.source_viability_frame_count,
            "global_registry_validated": self.global_registry_validated,
            "global_overlap_policy_validated": (
                self.global_overlap_policy_validated
            ),
            "source_bindings_validated": self.source_bindings_validated,
            "d4_frozen_contract_validated": self.d4_frozen_contract_validated,
            "exact_seed_inventory_validated": (
                self.exact_seed_inventory_validated
            ),
            "train_only_validated": self.train_only_validated,
            "source_generation_request_artifact_validated": (
                self.source_generation_request_artifact_validated
            ),
            "writer_resume_safety_validated": (
                self.writer_resume_safety_validated
            ),
            "source_viability_audit_validated": (
                self.source_viability_audit_validated
            ),
            "generation_prerequisites_ready": (
                self.generation_prerequisites_ready
            ),
            "source_generation_request_ready": (
                self.source_generation_request_ready
            ),
            "main_execution_authorization": (
                self.main_execution_authorization
            ),
            "dataset_generation_executed": self.dataset_generation_executed,
            "generated_episode_count": self.generated_episode_count,
            "generated_sample_count": self.generated_sample_count,
            "training_ready": self.training_ready,
            "model_ready": self.model_ready,
            "runtime_admission_ready": self.runtime_admission_ready,
            "validation_seed_allocation": list(self.validation_seed_allocation),
            "test_seed_allocation": list(self.test_seed_allocation),
            "generation_request_permissions": (
                self.generation_request_permissions.to_dict()
            ),
            "permissions": self.permissions.to_dict(),
            "producer_capability": {
                "source_generation_request_path": (
                    self.source_generation_request_path
                ),
                "source_generation_request_sha256": (
                    self.source_generation_request_sha256
                ),
                "source_generation_request_ready": (
                    self.source_generation_request_ready
                ),
                "cross_process_resume_supported": (
                    self.writer_resume_safety_validated
                ),
                "all_frozen_cells_viable": (
                    self.source_viability_audit_validated
                ),
                "source_viability_audit_schema": (
                    V8_SOURCE_VIABILITY_AUDIT_SCHEMA
                ),
                "source_viability_episode_count": (
                    self.source_viability_episode_count
                ),
                "resume_state_schema": V8_WRITER_RESUME_STATE_SCHEMA,
                "main_execution_authorization": (
                    self.main_execution_authorization
                ),
                "dataset_generation_execution_authorized": False,
                "training_authorized": False,
                "validation_selection_authorized": False,
                "test_selection_authorized": False,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}


def default_v8_main_allocation_binding_path() -> Path:
    module_root = Path(__file__).resolve().parents[1]
    return module_root / "configs" / "region_resource_v8_main_seed_allocation_binding_v1.json"


def default_v8_source_generation_request_path() -> Path:
    module_root = Path(__file__).resolve().parents[1]
    return (
        module_root
        / "configs"
        / "region_resource_v8_train_source_generation_request_readiness_v1.json"
    )


def validate_v8_source_generation_request_payload(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = _strict_mapping(value, "source_generation_request")
    _require_exact_keys(
        payload,
        _SOURCE_GENERATION_REQUEST_ROOT_KEYS,
        "source_generation_request",
    )
    _validate_self_hash(payload, "source_generation_request")
    if payload["schema"] != V8_SOURCE_GENERATION_REQUEST_SCHEMA:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_schema_mismatch"
        )
    if payload["artifact_id"] != V8_SOURCE_GENERATION_REQUEST_ARTIFACT_ID:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_artifact_id_mismatch"
        )
    if payload["report_date"] != "2026-08-01":
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_report_date_mismatch"
        )
    if payload["status"] != V8_SOURCE_GENERATION_REQUEST_STATUS:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_status_mismatch"
        )
    _nonempty_string(payload["purpose"], "source_generation_request.purpose")

    references = _strict_mapping(
        payload["references"], "source_generation_request.references"
    )
    expected_references = {
        "frozen_request": {
            "role": "frozen_train_source_request",
            "request_id": D4_REQUEST_ID,
            "path": D4_REQUEST_PATH,
            "content_sha256": D4_REQUEST_CONTENT_SHA256,
            "file_sha256": D4_REQUEST_FILE_SHA256,
        },
        "schedule_registry": {
            "role": "frozen_train_schedule_and_seed_registry",
            "registry_id": D4_MODULE_SEED_REGISTRY_ID,
            "path": D4_MODULE_SEED_REGISTRY_PATH,
            "content_sha256": D4_MODULE_SEED_REGISTRY_CONTENT_SHA256,
            "schedule_content_sha256": D4_MODULE_SCHEDULE_CONTENT_SHA256,
            "file_sha256": D4_MODULE_SEED_REGISTRY_FILE_SHA256,
        },
        "main_allocation_binding": {
            "role": "main_owned_allocation_binding",
            "binding_id": V8_MAIN_ALLOCATION_BINDING_ID,
            "path": MAIN_ALLOCATION_BINDING_PATH,
            "content_sha256": MAIN_ALLOCATION_BINDING_CONTENT_SHA256,
            "file_sha256": MAIN_ALLOCATION_BINDING_FILE_SHA256,
        },
        "global_seed_registry": {
            "role": "main_owned_global_seed_registry",
            "registry_id": GLOBAL_REGISTRY_ID,
            "path": GLOBAL_REGISTRY_PATH,
            "content_sha256": GLOBAL_REGISTRY_CONTENT_SHA256,
            "file_sha256": GLOBAL_REGISTRY_FILE_SHA256,
        },
        "writer_resume_implementation": {
            "role": "d4_train_writer_cross_process_resume_implementation",
            "path": V8_WRITER_RESUME_IMPLEMENTATION_PATH,
            "resume_state_schema": V8_WRITER_RESUME_STATE_SCHEMA,
            "file_sha256": V8_WRITER_RESUME_IMPLEMENTATION_FILE_SHA256,
        },
        "v8_contract_implementation": {
            "role": "d4_v8_strict_online_offline_contract",
            "path": V8_CONTRACT_IMPLEMENTATION_PATH,
            "file_sha256": V8_CONTRACT_IMPLEMENTATION_FILE_SHA256,
        },
        "runtime_evidence_implementation": {
            "role": "d4_actual_runtime_evidence_builder",
            "path": V8_RUNTIME_EVIDENCE_IMPLEMENTATION_PATH,
            "file_sha256": V8_RUNTIME_EVIDENCE_IMPLEMENTATION_FILE_SHA256,
        },
        "source_viability_implementation": {
            "role": "d4_all_frozen_cells_pre_generation_viability_audit",
            "path": V8_SOURCE_VIABILITY_IMPLEMENTATION_PATH,
            "audit_schema": V8_SOURCE_VIABILITY_AUDIT_SCHEMA,
            "file_sha256": V8_SOURCE_VIABILITY_IMPLEMENTATION_FILE_SHA256,
        },
        "region_resource_policy_implementation": {
            "role": "d4_rule_policy_and_deterministic_projector",
            "path": V8_REGION_RESOURCE_POLICY_IMPLEMENTATION_PATH,
            "file_sha256": V8_REGION_RESOURCE_POLICY_IMPLEMENTATION_FILE_SHA256,
        },
        "main_runtime_adapter_implementation": {
            "role": "main_truth_isolated_d4_runtime_adapter",
            "path": V8_MAIN_RUNTIME_ADAPTER_IMPLEMENTATION_PATH,
            "file_sha256": V8_MAIN_RUNTIME_ADAPTER_IMPLEMENTATION_FILE_SHA256,
        },
        "main_treatment_implementation": {
            "role": "main_frozen_d4_topology_supply_and_communication_treatment",
            "path": V8_MAIN_TREATMENT_IMPLEMENTATION_PATH,
            "file_sha256": V8_MAIN_TREATMENT_IMPLEMENTATION_FILE_SHA256,
        },
    }
    if dict(references) != expected_references:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_reference_drift"
        )

    scope = _strict_mapping(
        payload["request_scope"], "source_generation_request.request_scope"
    )
    expected_scope = {
        "candidate_version": ALLOCATION_CANDIDATE_VERSION,
        "allocation_id": ALLOCATION_ID,
        "allocation_usage_class": ALLOCATION_USAGE_CLASS,
        "requested_split": "train",
        "seed_count": len(V8_REQUESTED_SEEDS),
        "seed_range": [V8_REQUESTED_SEEDS[0], V8_REQUESTED_SEEDS[-1]],
        "seed_inventory_sha256": SEED_INVENTORY_SHA256,
        "cell_count": 108,
        "replicates_per_cell": 3,
        "topology_region_counts": [8, 9, 12, 16],
        "validation_seed_allocation": [],
        "test_seed_allocation": [],
        "source_viability_audit": {
            "schema": V8_SOURCE_VIABILITY_AUDIT_SCHEMA,
            "required_episode_count": len(V8_REQUESTED_SEEDS),
            "required_full_cell_combination_count": 324,
            "required_reduced_combination_count": 108,
            "required_online_truth_use_count": 0,
            "failure_policy": "fail_closed",
        },
    }
    if dict(scope) != expected_scope:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_scope_mismatch"
        )

    resume_safety = _strict_mapping(
        payload["resume_safety"], "source_generation_request.resume_safety"
    )
    expected_resume_safety = {
        "cross_process_resume_required": True,
        "writer_resume_supported": True,
        "resume_state_schema": V8_WRITER_RESUME_STATE_SCHEMA,
        "checkpoint_commit_policy": (
            "episode_pair_then_atomic_self_hashed_sidecar"
        ),
        "resume_validation_checks": [
            "exact_staging_file_inventory",
            "contiguous_schedule_index",
            "exact_frozen_seed_order",
            "online_offline_file_sha256",
            "strict_episode_round_trip",
            "exact_clean_source_metadata",
            "all_authority_permissions_false",
        ],
        "corruption_policy": "fail_closed",
        "gap_policy": "fail_closed",
    }
    if dict(resume_safety) != expected_resume_safety:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_resume_safety_mismatch"
        )

    try:
        V8GenerationRequestOnlyPermissions.from_dict(payload["permissions"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_permissions_mismatch", str(exc)
        ) from exc

    claims = _strict_mapping(
        payload["execution_claims"],
        "source_generation_request.execution_claims",
    )
    expected_claims = {
        "main_execution_authorization": False,
        "generation_command_authorized": False,
        "generation_command": "",
        "dataset_generation_executed": False,
        "episode_generation_count": 0,
        "sample_generation_count": 0,
        "training_count": 0,
        "checkpoint_count": 0,
        "model_registration_count": 0,
        "runtime_connection_count": 0,
    }
    if dict(claims) != expected_claims:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_execution_claim_mismatch"
        )
    if payload["content_sha256"] != SOURCE_GENERATION_REQUEST_CONTENT_SHA256:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_frozen_content_sha256_mismatch"
        )
    return payload


def validate_v8_main_allocation_binding_payload(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = _strict_mapping(value, "binding")
    _require_exact_keys(payload, _BINDING_ROOT_KEYS, "binding")
    _validate_self_hash(payload, "binding")
    if payload["schema"] != V8_MAIN_ALLOCATION_BINDING_SCHEMA:
        raise RegionResourceV8MainAllocationError("binding_schema_mismatch")
    if payload["binding_id"] != V8_MAIN_ALLOCATION_BINDING_ID:
        raise RegionResourceV8MainAllocationError("binding_id_mismatch")
    if payload["status"] != V8_MAIN_ALLOCATION_BINDING_STATUS:
        raise RegionResourceV8MainAllocationError("binding_status_mismatch")
    _nonempty_string(payload["purpose"], "binding.purpose")

    global_registry = _strict_mapping(payload["global_registry"], "global_registry")
    _require_exact_keys(
        global_registry,
        {
            "path",
            "schema_version",
            "policy_version",
            "registry_id",
            "status",
            "content_sha256",
            "file_sha256",
        },
        "global_registry",
    )
    expected_global = {
        "path": GLOBAL_REGISTRY_PATH,
        "schema_version": GLOBAL_REGISTRY_SCHEMA,
        "policy_version": GLOBAL_REGISTRY_POLICY,
        "registry_id": GLOBAL_REGISTRY_ID,
        "status": GLOBAL_REGISTRY_STATUS,
        "content_sha256": GLOBAL_REGISTRY_CONTENT_SHA256,
        "file_sha256": GLOBAL_REGISTRY_FILE_SHA256,
    }
    if dict(global_registry) != expected_global:
        raise RegionResourceV8MainAllocationError("binding_global_registry_drift")

    allocation = _strict_mapping(payload["allocation"], "allocation")
    _require_exact_keys(
        allocation,
        {
            "allocation_id",
            "owner",
            "candidate_version",
            "lifecycle",
            "usage_class",
            "split_policy",
            "permitted_operations",
            "readiness_operation",
            "seed_count",
            "seed_range",
            "seed_inventory_sha256",
        },
        "allocation",
    )
    expected_allocation = {
        "allocation_id": ALLOCATION_ID,
        "owner": ALLOCATION_OWNER,
        "candidate_version": ALLOCATION_CANDIDATE_VERSION,
        "lifecycle": ALLOCATION_LIFECYCLE,
        "usage_class": ALLOCATION_USAGE_CLASS,
        "split_policy": ALLOCATION_SPLIT_POLICY,
        "permitted_operations": list(ALLOCATION_OPERATIONS),
        "readiness_operation": READINESS_OPERATION,
        "seed_count": len(V8_REQUESTED_SEEDS),
        "seed_range": [V8_REQUESTED_SEEDS[0], V8_REQUESTED_SEEDS[-1]],
        "seed_inventory_sha256": SEED_INVENTORY_SHA256,
    }
    if dict(allocation) != expected_allocation:
        raise RegionResourceV8MainAllocationError("binding_allocation_drift")

    frozen = _strict_mapping(payload["d4_frozen_contract"], "d4_frozen_contract")
    _require_exact_keys(
        frozen,
        {
            "request_id",
            "request_path",
            "request_content_sha256",
            "request_file_sha256",
            "module_seed_registry_id",
            "module_seed_registry_path",
            "module_seed_registry_content_sha256",
            "module_seed_registry_file_sha256",
            "module_schedule_content_sha256",
            "cell_count",
            "replicates_per_cell",
            "topology_region_counts",
            "requested_split",
            "validation_seed_allocation",
            "test_seed_allocation",
        },
        "d4_frozen_contract",
    )
    expected_frozen = {
        "request_id": D4_REQUEST_ID,
        "request_path": D4_REQUEST_PATH,
        "request_content_sha256": D4_REQUEST_CONTENT_SHA256,
        "request_file_sha256": D4_REQUEST_FILE_SHA256,
        "module_seed_registry_id": D4_MODULE_SEED_REGISTRY_ID,
        "module_seed_registry_path": D4_MODULE_SEED_REGISTRY_PATH,
        "module_seed_registry_content_sha256": (
            D4_MODULE_SEED_REGISTRY_CONTENT_SHA256
        ),
        "module_seed_registry_file_sha256": D4_MODULE_SEED_REGISTRY_FILE_SHA256,
        "module_schedule_content_sha256": D4_MODULE_SCHEDULE_CONTENT_SHA256,
        "cell_count": 108,
        "replicates_per_cell": 3,
        "topology_region_counts": [8, 9, 12, 16],
        "requested_split": "train",
        "validation_seed_allocation": [],
        "test_seed_allocation": [],
    }
    if dict(frozen) != expected_frozen:
        raise RegionResourceV8MainAllocationError("binding_d4_contract_drift")

    claims = _strict_mapping(payload["generation_claims"], "generation_claims")
    expected_claims = {
        "generation_prerequisites_only": True,
        "dataset_generation_executed": False,
        "episode_generation_count": 0,
        "sample_generation_count": 0,
        "training_ready": False,
        "training_count": 0,
        "model_ready": False,
        "model_registration_count": 0,
        "runtime_admission_ready": False,
        "runtime_connection_count": 0,
    }
    if dict(claims) != expected_claims:
        raise RegionResourceV8MainAllocationError("binding_generation_claim_drift")
    try:
        V8NoAuthorityPermissions.from_dict(payload["permissions"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionResourceV8MainAllocationError(
            "binding_permissions_not_all_false", str(exc)
        ) from exc
    return payload


def validate_v8_main_allocation_pre_generation_readiness(
    *,
    binding_path: str | Path | None = None,
    source_generation_request_path: str | Path | None = None,
    repository_root: str | Path,
) -> V8MainAllocationPreGenerationReadiness:
    """Validate all generation prerequisites without creating any artifact."""

    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise RegionResourceV8MainAllocationError("repository_root_invalid")
    generation_request_source = _resolve_repository_file(
        root,
        SOURCE_GENERATION_REQUEST_PATH,
        "source_generation_request",
    )
    if source_generation_request_path is not None:
        supplied_generation_request = _require_regular_file(
            source_generation_request_path,
            "source_generation_request",
        )
        if supplied_generation_request != generation_request_source:
            raise RegionResourceV8MainAllocationError(
                "source_generation_request_path_mismatch"
            )
    generation_request_file_sha = _sha256_file(generation_request_source)
    if generation_request_file_sha != SOURCE_GENERATION_REQUEST_FILE_SHA256:
        raise RegionResourceV8MainAllocationError(
            "source_generation_request_file_sha256_mismatch"
        )
    generation_request = validate_v8_source_generation_request_payload(
        _read_json(generation_request_source, "source_generation_request")
    )
    generation_references = _strict_mapping(
        generation_request["references"],
        "source_generation_request.references",
    )
    binding_reference = _strict_mapping(
        generation_references["main_allocation_binding"],
        "source_generation_request.references.main_allocation_binding",
    )
    source = _resolve_repository_file(
        root,
        binding_reference["path"],
        "binding",
    )
    if binding_path is not None:
        supplied_binding = _require_regular_file(binding_path, "binding")
        if supplied_binding != source:
            raise RegionResourceV8MainAllocationError("binding_path_mismatch")
    actual_binding_file_sha = _sha256_file(source)
    if actual_binding_file_sha != binding_reference["file_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "binding_file_sha256_mismatch"
        )
    binding = validate_v8_main_allocation_binding_payload(
        _read_json(source, "binding")
    )
    if binding["content_sha256"] != binding_reference["content_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "binding_frozen_content_sha256_mismatch"
        )

    writer_reference = _strict_mapping(
        generation_references["writer_resume_implementation"],
        "source_generation_request.references.writer_resume_implementation",
    )
    writer_path = _resolve_repository_file(
        root,
        writer_reference["path"],
        "writer_resume_implementation",
    )
    if _sha256_file(writer_path) != writer_reference["file_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "writer_resume_implementation_file_sha256_mismatch"
        )
    if writer_reference["resume_state_schema"] != V8_WRITER_RESUME_STATE_SCHEMA:
        raise RegionResourceV8MainAllocationError(
            "writer_resume_state_schema_mismatch"
        )
    producer_references = (
        "v8_contract_implementation",
        "runtime_evidence_implementation",
        "source_viability_implementation",
        "region_resource_policy_implementation",
        "main_runtime_adapter_implementation",
        "main_treatment_implementation",
    )
    for reference_name in producer_references:
        reference = _strict_mapping(
            generation_references[reference_name],
            f"source_generation_request.references.{reference_name}",
        )
        implementation_path = _resolve_repository_file(
            root,
            reference["path"],
            reference_name,
        )
        if _sha256_file(implementation_path) != reference["file_sha256"]:
            raise RegionResourceV8MainAllocationError(
                f"{reference_name}_file_sha256_mismatch"
            )
    global_spec = _strict_mapping(binding["global_registry"], "global_registry")
    allocation_spec = _strict_mapping(binding["allocation"], "allocation")
    frozen_spec = _strict_mapping(binding["d4_frozen_contract"], "d4_frozen_contract")

    global_path = _resolve_repository_file(
        root, global_spec["path"], "global_registry"
    )
    global_payload = _read_json(global_path, "global_registry")
    try:
        registry = build_global_seed_registry(global_payload)
    except GlobalSeedRegistryError as exc:
        raise RegionResourceV8MainAllocationError(
            f"global_registry_{exc.code}", str(exc)
        ) from exc
    if global_payload.get("status") != GLOBAL_REGISTRY_STATUS:
        raise RegionResourceV8MainAllocationError("global_registry_status_mismatch")

    try:
        allocation = registry.allocation(ALLOCATION_ID)
    except GlobalSeedRegistryError as exc:
        raise RegionResourceV8MainAllocationError(
            f"global_registry_{exc.code}", str(exc)
        ) from exc
    expected_metadata = (
        ALLOCATION_OWNER,
        ALLOCATION_CANDIDATE_VERSION,
        ALLOCATION_LIFECYCLE,
        ALLOCATION_USAGE_CLASS,
        ALLOCATION_SPLIT_POLICY,
        ALLOCATION_OPERATIONS,
    )
    actual_metadata = (
        allocation.owner,
        allocation.candidate_version,
        allocation.lifecycle,
        allocation.usage_class,
        allocation.split_policy,
        allocation.permitted_operations,
    )
    if actual_metadata != expected_metadata:
        raise RegionResourceV8MainAllocationError(
            "global_allocation_metadata_mismatch"
        )
    if allocation.seeds != V8_REQUESTED_SEEDS:
        raise RegionResourceV8MainAllocationError(
            "global_allocation_seed_inventory_mismatch"
        )
    if canonical_v8_sha256(list(allocation.seeds)) != allocation_spec[
        "seed_inventory_sha256"
    ]:
        raise RegionResourceV8MainAllocationError(
            "global_allocation_seed_inventory_hash_mismatch"
        )
    try:
        validate_seed_request(
            registry,
            allocation_id=ALLOCATION_ID,
            seeds=V8_REQUESTED_SEEDS,
            operation=READINESS_OPERATION,
            require_exact_allocation=True,
        )
    except GlobalSeedRegistryError as exc:
        raise RegionResourceV8MainAllocationError(
            f"global_allocation_{exc.code}", str(exc)
        ) from exc
    _validate_global_source_contract(allocation.source_contract, frozen_spec)
    if registry.registry_id != global_spec["registry_id"]:
        raise RegionResourceV8MainAllocationError("global_registry_id_mismatch")
    if registry.policy_version != global_spec["policy_version"]:
        raise RegionResourceV8MainAllocationError("global_registry_policy_mismatch")
    if registry.content_sha256 != global_spec["content_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "global_registry_content_sha256_mismatch"
        )

    request_path = _resolve_repository_file(
        root, frozen_spec["request_path"], "d4_request"
    )
    module_registry_path = _resolve_repository_file(
        root,
        frozen_spec["module_seed_registry_path"],
        "d4_module_seed_registry",
    )
    try:
        frozen = load_v8_frozen_request(request_path, module_registry_path)
    except (OSError, RegionResourceV8ContractError, ValueError) as exc:
        raise RegionResourceV8MainAllocationError(
            "d4_frozen_contract_invalid", str(exc)
        ) from exc
    if (
        frozen.request_id != frozen_spec["request_id"]
        or frozen.registry_id != frozen_spec["module_seed_registry_id"]
        or frozen.request_content_sha256
        != frozen_spec["request_content_sha256"]
        or frozen.registry_content_sha256
        != frozen_spec["module_seed_registry_content_sha256"]
        or frozen.registry_schedule_content_sha256
        != frozen_spec["module_schedule_content_sha256"]
        or tuple(item.seed for item in frozen.schedule) != V8_REQUESTED_SEEDS
    ):
        raise RegionResourceV8MainAllocationError(
            "d4_frozen_contract_binding_mismatch"
        )
    if len(frozen.schedule) != 324:
        raise RegionResourceV8MainAllocationError(
            "d4_frozen_schedule_episode_count_mismatch"
        )
    if any(item.split != "train" for item in frozen.schedule):
        raise RegionResourceV8MainAllocationError(
            "d4_frozen_schedule_split_mismatch"
        )
    if tuple(sorted({item.region_count for item in frozen.schedule})) != (
        8,
        9,
        12,
        16,
    ):
        raise RegionResourceV8MainAllocationError(
            "d4_frozen_schedule_region_inventory_mismatch"
        )
    try:
        source_viability = audit_v8_frozen_source_viability(frozen.schedule)
    except (RegionResourceV8SourceViabilityError, ValueError) as exc:
        raise RegionResourceV8MainAllocationError(
            "d4_source_viability_audit_failed",
            str(exc),
        ) from exc

    actual_global_file_sha = _sha256_file(global_path)
    actual_request_file_sha = _sha256_file(request_path)
    actual_module_registry_file_sha = _sha256_file(module_registry_path)
    if actual_global_file_sha != global_spec["file_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "global_registry_file_sha256_mismatch"
        )
    if actual_request_file_sha != frozen_spec["request_file_sha256"]:
        raise RegionResourceV8MainAllocationError(
            "d4_request_file_sha256_mismatch"
        )
    if (
        actual_module_registry_file_sha
        != frozen_spec["module_seed_registry_file_sha256"]
    ):
        raise RegionResourceV8MainAllocationError(
            "d4_module_seed_registry_file_sha256_mismatch"
        )

    return V8MainAllocationPreGenerationReadiness(
        binding_id=V8_MAIN_ALLOCATION_BINDING_ID,
        source_generation_request_path=SOURCE_GENERATION_REQUEST_PATH,
        source_generation_request_sha256=generation_request_file_sha,
        source_generation_request_content_sha256=(
            generation_request["content_sha256"]
        ),
        source_generation_request_artifact_id=(
            generation_request["artifact_id"]
        ),
        global_registry_id=registry.registry_id,
        global_registry_content_sha256=registry.content_sha256,
        global_registry_file_sha256=actual_global_file_sha,
        allocation_id=allocation.allocation_id,
        allocation_seed_count=len(allocation.seeds),
        allocation_seed_range=(allocation.seeds[0], allocation.seeds[-1]),
        allocation_seed_inventory_sha256=canonical_v8_sha256(
            list(allocation.seeds)
        ),
        d4_request_content_sha256=frozen.request_content_sha256,
        d4_request_file_sha256=actual_request_file_sha,
        d4_module_seed_registry_content_sha256=(
            frozen.registry_content_sha256
        ),
        d4_module_seed_registry_file_sha256=actual_module_registry_file_sha,
        d4_module_schedule_content_sha256=(
            frozen.registry_schedule_content_sha256
        ),
        source_viability_audit_content_sha256=(
            source_viability.content_sha256
        ),
        source_viability_cell_evidence_sha256=(
            source_viability.cell_evidence_sha256
        ),
        source_viability_episode_count=(
            source_viability.schedule_episode_count
        ),
        source_viability_frame_count=source_viability.audited_frame_count,
    )


def _validate_global_source_contract(
    value: Mapping[str, Any], frozen_spec: Mapping[str, Any]
) -> None:
    source = _strict_mapping(value, "global_allocation.source_contract")
    _require_exact_keys(
        source,
        {"request_id", "module_seed_registry_id", "bindings"},
        "global_allocation.source_contract",
    )
    expected = {
        "request_id": frozen_spec["request_id"],
        "module_seed_registry_id": frozen_spec["module_seed_registry_id"],
        "bindings": [
            {
                "role": "development_data_request",
                "path": frozen_spec["request_path"],
                "sha256": frozen_spec["request_file_sha256"],
            },
            {
                "role": "module_seed_request",
                "path": frozen_spec["module_seed_registry_path"],
                "sha256": frozen_spec["module_seed_registry_file_sha256"],
            },
        ],
    }
    if dict(source) != expected:
        raise RegionResourceV8MainAllocationError(
            "global_allocation_source_binding_mismatch"
        )


def _binding_content_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    return canonical_v8_sha256(payload)


def _validate_self_hash(value: Mapping[str, Any], label: str) -> None:
    digest = _sha256_string(value.get("content_sha256"), f"{label}.content_sha256")
    if _binding_content_sha256(value) != digest:
        raise RegionResourceV8MainAllocationError(
            f"{label}_content_sha256_mismatch"
        )


def _resolve_repository_file(root: Path, value: Any, label: str) -> Path:
    logical = _nonempty_string(value, f"{label}.path")
    relative = Path(logical)
    if relative.is_absolute() or ".." in relative.parts:
        raise RegionResourceV8MainAllocationError(f"{label}_path_unsafe")
    candidate = root / relative
    if candidate.is_symlink():
        raise RegionResourceV8MainAllocationError(f"{label}_symlink_forbidden")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RegionResourceV8MainAllocationError(
            f"{label}_file_unavailable", str(exc)
        ) from exc
    if not resolved.is_file():
        raise RegionResourceV8MainAllocationError(f"{label}_not_file")
    return resolved


def _require_regular_file(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise RegionResourceV8MainAllocationError(f"{label}_file_unavailable")
    return candidate.resolve()


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except RegionResourceV8MainAllocationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegionResourceV8MainAllocationError(
            f"{label}_json_read_failed", str(exc)
        ) from exc
    return _strict_mapping(value, label)


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegionResourceV8MainAllocationError(
                f"json_duplicate_key:{key}"
            )
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise RegionResourceV8MainAllocationError(f"json_nonfinite_constant:{value}")


def _strict_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionResourceV8MainAllocationError(f"{label}_not_object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], label: str
) -> None:
    if set(value) != set(expected):
        raise RegionResourceV8MainAllocationError(f"{label}_key_inventory_mismatch")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegionResourceV8MainAllocationError(f"{label}_invalid")
    return value.strip()


def _sha256_string(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RegionResourceV8MainAllocationError(f"{label}_invalid")
    return value


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RegionResourceV8MainAllocationError(
            "file_sha256_failed", str(exc)
        ) from exc
    return digest.hexdigest()


__all__ = [
    "RegionResourceV8MainAllocationError",
    "V8GenerationRequestOnlyPermissions",
    "V8MainAllocationPreGenerationReadiness",
    "default_v8_main_allocation_binding_path",
    "default_v8_source_generation_request_path",
    "validate_v8_source_generation_request_payload",
    "validate_v8_main_allocation_binding_payload",
    "validate_v8_main_allocation_pre_generation_readiness",
]
